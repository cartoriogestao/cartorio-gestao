"""A COBRANÇA DOS CLIENTES — o boleto (com Pix) que o protocolo manda ao banco.

POR QUE EXISTE (27/10/2026)
    Pedido do oficial: «vamos criar integração também com a Unicred» e, ao
    escolher para quê, marcou tudo — receber dos clientes, pagar despesas,
    extrato e conferência, «e o que mais a API fornecer». Depois: «crie o
    módulo do Inter junto com o da Unicred». Os dois bancos emitem boleto
    registrado pela API; este módulo é o que os dois têm em comum, e cada
    banco fala pelo seu adaptador (`cobranca_inter`, `cobranca_unicred`).

    PAGAR E O EXTRATO SÃO DE `despesas_inter`, E SÓ DO INTER. A documentação
    da Unicred que o oficial juntou (sete PDFs do portal, 27/10/2026) é TODA
    de cobrança — emissão, consulta, PDF, baixa, abatimento e protesto
    automático. Não há uma linha sobre pagar boleto, Pix de saída ou extrato
    da conta. Escrever isso sem contrato seria inventar endereço de dinheiro;
    a tela da configuração diz o que falta pedir ao gerente.

O CICLO
    A_EMITIR → EMITINDO → ABERTA → RECEBIDA → LANCADA
     cadastrar   banco     CIP     o banco    depósito no caixa
    Fora do caminho: FALHOU (o banco recusou a emissão), CANCELADA (pedida
    por nós), BAIXADA (o banco baixou: prazo vencido, protesto, ou marcada
    como recebida FORA do banco).

    O dinheiro pago vira DEPÓSITO PRÉVIO do protocolo (`caixa_depositos.criar`),
    com número próprio, orçamento congelado e saldo. Os itens do protocolo
    não se quitam nesse passo: quem atende usa o saldo depois.

    **PARCELA EXPRESS ENTRA SOZINHA NO CAIXA GERAL** (oficial, 05/11/2026).
    Pix, boleto ou cartão confirmado pela Parcela vira depósito no caixa
    geral da serventia (`OPERADOR_DO_CAIXA_GERAL`), não no caixa de um
    escrevente. Sem esse caixa aberto hoje, a cobrança fica RECEBIDA até a
    abertura, e entra quando ele abre. Não há clique «lançar no meu caixa»
    para a Parcela. Inter e Unicred seguem no clique de quem está com o
    próprio caixa aberto.

    **«MARCADO COMO RECEBIDO» NÃO É RECEBIDO.** O Inter tem a situação
    MARCADO_RECEBIDO: alguém marcou no Internet Banking que recebeu por fora.
    O dinheiro NÃO passou pela conta, e lançá-lo como depósito faria o caixa
    contar duas vezes o que o cliente pagou em espécie. Vira BAIXADA, com a
    frase.

AS TRAVAS
    - nasce DESLIGADA e no ambiente de TESTE;
    - a emissão não segura transação do banco de dados durante a rede: marca
      EMITINDO antes, fala com o banco, grava a resposta depois;
    - o mesmo `seu_numero` não vai duas vezes ao mesmo banco no mesmo
      ambiente (`UNIQUE`), e o reenvio de quem ficou sem resposta só acontece
      depois de PROCURAR a cobrança no banco;
    - cobrança emitida num ambiente nunca é consultada no outro.

PostgreSQL nativo, pelo `bd_nativo`. Dinheiro em centavos, `bigint`. Data e
hora se calculam no Python (regra da casa).
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import date, datetime, timedelta
from typing import Any

import cpf_cnpj
from bd_nativo import banco
from caixa_schema import centavos, reais

A_EMITIR = "A_EMITIR"
EMITINDO = "EMITINDO"
ABERTA = "ABERTA"
RECEBIDA = "RECEBIDA"
LANCADA = "LANCADA"
FALHOU = "FALHOU"
CANCELADA = "CANCELADA"
BAIXADA = "BAIXADA"

SITUACOES = {
    A_EMITIR: "A emitir",
    EMITINDO: "Emitindo no banco",
    ABERTA: "Aberta — esperando o pagamento",
    RECEBIDA: "Paga — ainda não entrou no caixa",
    LANCADA: "Lançada no caixa",
    FALHOU: "O banco recusou",
    CANCELADA: "Cancelada",
    BAIXADA: "Baixada pelo banco",
}
#: As que ainda podem mudar sozinhas, do lado do banco.
EM_ABERTO = (EMITINDO, ABERTA)

INTER = "INTER"
UNICRED = "UNICRED"
PARCELA = "PARCELA"
BANCOS = {INTER: "Banco Inter", UNICRED: "Unicred",
          PARCELA: "Parcela Express (Pix, boleto e cartão)"}
AMBIENTES = {"sandbox": "Teste (homologação do banco, sem dinheiro de verdade)",
             "producao": "Produção (dinheiro de verdade)"}

# O QUE CADA BANCO DEIXA FAZER, MEDIDO NA DOCUMENTAÇÃO (27/10/2026). A tela
# só oferece o botão que o banco tem: oferecer e recusar depois ensina o
# balcão a desconfiar da tela.
RECURSOS = {
    INTER: {"cancelar", "pdf", "pix"},
    UNICRED: {"cancelar", "pdf", "abatimento", "protesto_automatico"},
    PARCELA: {"cancelar", "pix", "cartao", "boleto"},
}

#: Quanto a casa espera a cobrança sem resposta aparecer no banco antes de
#: dizer que falhou. Cada ida ao banco tem 30 s; quinze minutos sobram.
PRAZO_DE_ESPERA = timedelta(minutes=15)
LIMITE_SEU_NUMERO = 15
#: O Inter recusa abaixo de R$ 2,50 (`valorNominal.minimum`); a Unicred, zero.
MINIMO = {INTER: 250, UNICRED: 1, PARCELA: 1}
UFS = ["AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO"]

PADRAO: dict[str, str] = {
    "cobranca_ligada": "0",
    "cobranca_banco": INTER,
    "cobranca_ambiente": "sandbox",
    "cobranca_dias_vencimento": "3",
    # Dias corridos depois do vencimento em que o boleto ainda se paga (Inter:
    # `numDiasAgenda`, de 0 a 60). Depois disso o banco o expira.
    "cobranca_dias_apos_vencimento": "30",
    "cobranca_mensagem": "Emolumentos do protocolo {protocolo}. Não receber após o prazo.",
}
ROTULOS = {
    "cobranca_ligada": "Emissão de cobrança ligada",
    "cobranca_banco": "Banco da cobrança",
    "cobranca_ambiente": "Ambiente",
    "cobranca_dias_vencimento": "Vencimento padrão (dias corridos a partir de hoje)",
    "cobranca_dias_apos_vencimento": "Dias para pagar depois do vencimento",
    "cobranca_mensagem": "Mensagem impressa no boleto ({protocolo} vira o número)",
}

SCHEMA: tuple[tuple[str, str], ...] = (
    ("cb_cobrancas", """
        CREATE TABLE IF NOT EXISTS cb_cobrancas (
            id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            banco TEXT NOT NULL CHECK (banco IN ('INTER', 'UNICRED', 'PARCELA')),
            link_pagamento TEXT NOT NULL DEFAULT '',
            forma_pedida TEXT NOT NULL DEFAULT '',
            ambiente TEXT NOT NULL,
            situacao TEXT NOT NULL CHECK (situacao IN (
                'A_EMITIR', 'EMITINDO', 'ABERTA', 'RECEBIDA', 'LANCADA',
                'FALHOU', 'CANCELADA', 'BAIXADA')),
            protocolo_id bigint,
            seu_numero TEXT,
            valor bigint NOT NULL CHECK (valor > 0),
            vencimento TEXT NOT NULL,
            dias_apos_vencimento integer NOT NULL DEFAULT 0,
            pagador_nome TEXT NOT NULL,
            pagador_documento TEXT NOT NULL,
            pagador_email TEXT NOT NULL DEFAULT '',
            pagador_endereco TEXT NOT NULL DEFAULT '{}',
            mensagem TEXT NOT NULL DEFAULT '',
            banco_id TEXT,
            nosso_numero TEXT NOT NULL DEFAULT '',
            linha_digitavel TEXT NOT NULL DEFAULT '',
            codigo_barras TEXT NOT NULL DEFAULT '',
            pix_copia_e_cola TEXT NOT NULL DEFAULT '',
            banco_status TEXT NOT NULL DEFAULT '',
            banco_motivo TEXT NOT NULL DEFAULT '',
            valor_recebido bigint,
            data_pagamento TEXT,
            forma_recebida TEXT NOT NULL DEFAULT '',
            abatimento bigint NOT NULL DEFAULT 0,
            deposito_id bigint,
            pedido TEXT NOT NULL DEFAULT '',
            pdf_guardado integer NOT NULL DEFAULT 0,
            erro TEXT NOT NULL DEFAULT '',
            enviada_em TEXT,
            consultada_em TEXT,
            criada_em TEXT NOT NULL,
            criada_por TEXT NOT NULL,
            cancelada_em TEXT,
            cancelada_por TEXT,
            motivo_cancelamento TEXT NOT NULL DEFAULT ''
        )"""),
    # O MESMO SEU NÚMERO NÃO VAI DUAS VEZES AO MESMO BANCO NO MESMO AMBIENTE.
    # A trava mora no banco de dados: duas abas do navegador no mesmo minuto
    # não emitem dois boletos para o mesmo cliente.
    ("ux_cb_cobrancas_seu_numero", """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_cb_cobrancas_seu_numero
            ON cb_cobrancas (banco, ambiente, seu_numero) WHERE seu_numero IS NOT NULL"""),
    ("ix_cb_cobrancas_situacao",
     "CREATE INDEX IF NOT EXISTS ix_cb_cobrancas_situacao ON cb_cobrancas (situacao, id)"),
    ("ix_cb_cobrancas_protocolo",
     "CREATE INDEX IF NOT EXISTS ix_cb_cobrancas_protocolo ON cb_cobrancas (protocolo_id)"),
    ("cb_eventos", """
        CREATE TABLE IF NOT EXISTS cb_eventos (
            id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            cobranca_id bigint NOT NULL REFERENCES cb_cobrancas(id),
            quando TEXT NOT NULL,
            operacao TEXT NOT NULL,
            resultado TEXT NOT NULL,
            mensagem TEXT NOT NULL DEFAULT '',
            usuario TEXT NOT NULL DEFAULT ''
        )"""),
    ("ix_cb_eventos_cobranca",
     "CREATE INDEX IF NOT EXISTS ix_cb_eventos_cobranca ON cb_eventos (cobranca_id, id)"),
)


class CobrancaError(ValueError):
    """Impedimento de regra, com a frase pronta para a tela."""


def init_cobranca_schema(con) -> None:
    """Cria as tabelas e os índices que faltarem. Idempotente."""
    bd = banco(con)
    for nome, comando in SCHEMA:
        if not bd.tem_tabela(nome):
            bd.escrever(comando)
    if bd.tem_tabela("cb_cobrancas") and not bd.tem_coluna("cb_cobrancas", "link_pagamento"):
        bd.escrever("ALTER TABLE cb_cobrancas ADD COLUMN link_pagamento TEXT NOT NULL DEFAULT ''")
    if bd.tem_tabela("cb_cobrancas") and not bd.tem_coluna("cb_cobrancas", "forma_pedida"):
        bd.escrever("ALTER TABLE cb_cobrancas ADD COLUMN forma_pedida TEXT NOT NULL DEFAULT ''")
    if bd.tem_tabela("cb_cobrancas"):
        definicao = bd.um(
            """SELECT pg_get_constraintdef(oid) AS definicao
                 FROM pg_constraint
                WHERE conname = 'cb_cobrancas_banco_check'""")
        texto = str((definicao or {}).get("definicao") or "")
        if texto and "PARCELA" not in texto:
            bd.escrever("ALTER TABLE cb_cobrancas DROP CONSTRAINT cb_cobrancas_banco_check")
            bd.escrever(
                """ALTER TABLE cb_cobrancas ADD CONSTRAINT cb_cobrancas_banco_check
                   CHECK (banco IN ('INTER', 'UNICRED', 'PARCELA'))""")


# ------------------------------------------------------------- auxiliares

def digitos(valor: Any) -> str:
    return re.sub(r"\D", "", str(valor or ""))


def _texto(valor: Any, limite: int = 500) -> str:
    limpo = re.sub(r"[\x00-\x1f\x7f]", " ", str(valor or ""))
    return " ".join(limpo.split())[:limite]


def _carimbo(quando: datetime) -> str:
    return quando.replace(tzinfo=None, microsecond=0).isoformat(timespec="seconds")


def _data(valor: Any, rotulo: str) -> str:
    texto = str(valor or "").strip()[:10]
    try:
        return date.fromisoformat(texto).isoformat()
    except ValueError as erro:
        raise CobrancaError(f"{rotulo} não é uma data válida (AAAA-MM-DD).") from erro


def _evento(bd, cobranca_id: int, operacao: str, resultado: str, mensagem: str,
            usuario: str, quando: str) -> None:
    bd.escrever(
        """INSERT INTO cb_eventos (cobranca_id, quando, operacao, resultado, mensagem, usuario)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (int(cobranca_id), quando, operacao, resultado, _texto(mensagem, 1000), usuario or ""))


def cobranca(con, cobranca_id: int) -> dict | None:
    return banco(con).um("SELECT * FROM cb_cobrancas WHERE id = %s", (int(cobranca_id),))


def eventos(con, cobranca_id: int) -> list[dict]:
    return banco(con).ler("SELECT * FROM cb_eventos WHERE cobranca_id = %s ORDER BY id",
                          (int(cobranca_id),))


def centavos_do_banco(valor: Any) -> int | None:
    """«1234.56» ou 1234.56 (os dois bancos falam com PONTO decimal) → centavos.

    Não é `caixa_schema.centavos`, que lê à brasileira: lá «1.234» é mil
    duzentos e trinta e quatro reais, aqui é um real e vinte e três. O Inter
    declara `valorTotalRecebido` como texto «^\\d{1,10}\\.\\d{2}$» e o exemplo
    dele o traz como número — as duas formas chegam.
    """
    from decimal import Decimal, InvalidOperation
    if valor is None or valor == "":
        return None
    try:
        return int((Decimal(str(valor).strip()) * 100).to_integral_value())
    except (InvalidOperation, ValueError):
        return None


def linhas_da_mensagem(texto: Any, *, largura: int, maximo: int) -> list[str]:
    """A mensagem do boleto em linhas do tamanho que o banco aceita. Só calcula.

    Inter: cinco linhas de 78; Unicred: seis de 80. Quebra na palavra; o que
    não cabe fica de fora, e a tela mostra o limite.
    """
    import textwrap
    return textwrap.wrap(_texto(texto, largura * maximo), width=largura)[:maximo]


def endereco(c: Mapping[str, Any]) -> dict:
    try:
        lido = json.loads(c.get("pagador_endereco") or "{}")
    except ValueError:
        return {}
    return lido if isinstance(lido, dict) else {}


# ---------------------------------------------------------- a configuração

def configuracao(con) -> dict[str, str]:
    """O que está gravado, sobre o padrão. Só LÊ."""
    gravado = {r["key"]: r["value"] for r in banco(con).ler(
        "SELECT key, value FROM settings WHERE key = ANY(%s) ORDER BY key", (list(PADRAO),))}
    return {k: (gravado.get(k) if gravado.get(k) is not None else v) for k, v in PADRAO.items()}


def gravar_configuracao(con, valores: Mapping[str, Any]) -> dict[str, tuple[str, str]]:
    """Grava a configuração (só ADMIN, na rota). ESCREVE. Devolve o que mudou."""
    novo = {k: _texto(valores.get(k, PADRAO[k]), 200) for k in PADRAO}
    novo["cobranca_ligada"] = "1" if str(valores.get("cobranca_ligada") or "") in ("1", "on") else "0"
    if novo["cobranca_banco"] not in BANCOS:
        raise CobrancaError("Banco desconhecido.")
    if novo["cobranca_ambiente"] not in AMBIENTES:
        raise CobrancaError("Ambiente desconhecido.")
    for chave, maximo in (("cobranca_dias_vencimento", 365), ("cobranca_dias_apos_vencimento", 60)):
        if not novo[chave].isdigit() or int(novo[chave]) > maximo:
            raise CobrancaError(f"{ROTULOS[chave]}: informe um número de 0 a {maximo}.")
    bd = banco(con)
    antes = configuracao(bd)
    mudou = {k: (antes[k], v) for k, v in novo.items() if antes[k] != v}
    for chave, valor in novo.items():
        bd.escrever("INSERT INTO settings (key, value) VALUES (%s, %s) "
                    "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", (chave, valor))
    return mudou


# ------------------------------------------------------- o que se cobra

def a_pagar_do_protocolo(con, protocolo_id: int) -> dict:
    """O protocolo e quanto dele falta pagar. Só LÊ.

    A soma é dos itens AINDA NÃO QUITADOS e não gratuitos, menos o saldo dos
    depósitos prévios do protocolo — e é SUGESTÃO: quem emite confere. Um
    boleto do valor errado é o cliente pagando o que não deve, e a recusa do
    caixa só chega quando ele voltar.
    """
    bd = banco(con)
    p = bd.um("SELECT * FROM cx_protocolos WHERE id = %s", (int(protocolo_id),))
    if not p:
        raise CobrancaError(f"Protocolo {protocolo_id} não encontrado.")
    itens = bd.ler(
        """SELECT valor_total FROM cx_protocolo_atos
            WHERE protocolo_id = %s AND coalesce(quitado, 0) = 0
              AND coalesce(gratuito, 0) = 0""", (int(protocolo_id),))
    devido = sum(centavos(i["valor_total"] or "0") for i in itens)
    saldo = 0
    if bd.tem_tabela("cx_depositos"):
        saldo = sum(centavos(r["saldo"] or "0") for r in bd.ler(
            "SELECT saldo FROM cx_depositos WHERE protocolo_id = %s", (int(protocolo_id),)))
    abertas = bd.ler(
        "SELECT id, situacao, valor FROM cb_cobrancas WHERE protocolo_id = %s "
        "AND situacao = ANY(%s) ORDER BY id",
        (int(protocolo_id), [A_EMITIR, EMITINDO, ABERTA, RECEBIDA]))
    return {"protocolo": p, "itens": len(itens), "devido": devido, "saldo_depositos": saldo,
            "sugerido": max(0, devido - saldo), "cobrancas_abertas": abertas}


def conferir_pagador(pagador: Mapping[str, Any]) -> dict:
    """O pagador como os dois bancos aceitam. Só calcula. Recusa o que não sairia.

    Os dois exigem nome, documento, endereço, cidade, UF e CEP (Inter:
    `PagadorBase.required`; Unicred: «Obrigatório: Sim» no dicionário). Os
    tamanhos são o MENOR dos dois, para que a mesma cobrança sirva aos dois.
    """
    doc = digitos(pagador.get("documento"))
    if cpf_cnpj.documento_valido(doc) is not True:
        raise CobrancaError("O CPF ou CNPJ do pagador não confere. O banco recusa boleto "
                            "sem documento válido.")
    nome = _texto(pagador.get("nome"), 40)
    if not nome:
        raise CobrancaError("Informe o nome do pagador.")
    end = {
        "logradouro": _texto(pagador.get("logradouro"), 60),
        "numero": _texto(pagador.get("numero"), 5),
        "complemento": _texto(pagador.get("complemento"), 30),
        "bairro": _texto(pagador.get("bairro"), 40),
        "cidade": _texto(pagador.get("cidade"), 50),
        "uf": _texto(pagador.get("uf"), 2).upper(),
        "cep": digitos(pagador.get("cep")),
    }
    faltam = [r for k, r in (("logradouro", "endereço"), ("cidade", "cidade"), ("uf", "UF"))
              if not end[k]]
    if faltam:
        raise CobrancaError("Falta no endereço do pagador: " + ", ".join(faltam) +
                            ". O boleto registrado exige o endereço.")
    if end["uf"] not in UFS:
        raise CobrancaError(f"UF «{end['uf']}» não existe.")
    if len(end["cep"]) != 8:
        raise CobrancaError("O CEP do pagador tem de ter 8 dígitos.")
    email = _texto(pagador.get("email"), 50)
    if email and not re.fullmatch(r"[A-Za-z0-9._-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", email):
        # A Unicred só aceita ponto, arroba, hífen e sublinhado (dicionário da emissão).
        raise CobrancaError("O e-mail do pagador não está num formato que o banco aceita.")
    return {"nome": nome, "documento": doc, "email": email, "endereco": end,
            "tipo": "FISICA" if len(doc) == 11 else "JURIDICA"}


FORMAS_NA_MAQUINA = ("PIX", "CREDITO", "DEBITO")
FORMAS_DE_DENTRO = frozenset({"GRATUITO", "DEPOSITO_PREVIO"})
CIENCIA_DO_POR_FORA = (
    "Os próximos pagamentos serão recebidos dentro do sistema, "
    "nas formas que ele oferece."
)


def instituicao_ligada(cfg: Mapping[str, Any]) -> str:
    """O nome da instituição de pagamento, se a emissão está ligada. Senão, vazio."""
    if str(cfg.get("cobranca_ligada") or "") != "1":
        return ""
    return BANCOS.get(str(cfg.get("cobranca_banco") or ""), "")


def conferir_pagamento_por_fora(forma: str, cfg: Mapping[str, Any], *,
                                afirmo: Any, afirmacao: Any,
                                ciencia: Any) -> dict | None:
    """Recusa quitar por fora sem a afirmação e a ciência. Só calcula.

    Gratuito e depósito prévio não são dinheiro novo por fora. Sem instituição
    ligada, o balcão quita como antes.
    """
    import afirmacoes_expressas as AFX
    instituicao = instituicao_ligada(cfg)
    if not instituicao:
        return None
    if str(forma or "").strip().upper() in FORMAS_DE_DENTRO:
        return None
    try:
        texto = AFX.validar(
            afirmo, afirmacao,
            por_que=f"Pagamento por fora de {instituicao}.")
    except AFX.AfirmacaoError as erro:
        raise CobrancaError(str(erro)) from erro
    if not ciencia:
        raise CobrancaError("Marque a ciência: " + CIENCIA_DO_POR_FORA)
    return {"afirmacao": texto, "instituicao": instituicao,
            "ciencia": CIENCIA_DO_POR_FORA}


def cadastrar(con, *, agora: datetime, por: str, banco_codigo: str, ambiente: str,
              protocolo_id: int | None, valor_centavos: int, vencimento: Any,
              pagador: Mapping[str, Any], mensagem: str = "",
              dias_apos_vencimento: int = 0, forma_pedida: str = "") -> int:
    """Cadastra a cobrança A_EMITIR. ESCREVE. Não fala com o banco."""
    if banco_codigo not in BANCOS:
        raise CobrancaError("Banco desconhecido.")
    if ambiente not in AMBIENTES:
        raise CobrancaError("Ambiente desconhecido.")
    valor = int(valor_centavos or 0)
    if valor < MINIMO[banco_codigo]:
        raise CobrancaError(f"O {BANCOS[banco_codigo]} não emite boleto abaixo de "
                            f"R$ {reais(MINIMO[banco_codigo])}.")
    venc = _data(vencimento, "O vencimento")
    if venc < agora.date().isoformat():
        raise CobrancaError("O vencimento não pode ser anterior a hoje: os dois bancos recusam.")
    if not 0 <= int(dias_apos_vencimento) <= 60:
        raise CobrancaError("Os dias para pagar depois do vencimento vão de 0 a 60.")
    forma = str(forma_pedida or "").strip().upper()
    if forma and forma not in (*FORMAS_NA_MAQUINA, "BOLETO"):
        raise CobrancaError("A forma é Pix, crédito ou débito na maquininha, ou boleto.")
    p = conferir_pagador(pagador)
    bd = banco(con)
    if protocolo_id is not None and not bd.um("SELECT id FROM cx_protocolos WHERE id = %s",
                                              (int(protocolo_id),)):
        raise CobrancaError(f"Protocolo {protocolo_id} não encontrado.")
    quando = _carimbo(agora)
    novo = bd.escrever(
        """INSERT INTO cb_cobrancas
           (banco, ambiente, situacao, protocolo_id, valor, vencimento,
            dias_apos_vencimento, pagador_nome, pagador_documento, pagador_email,
            pagador_endereco, mensagem, criada_em, criada_por, forma_pedida)
           VALUES (%s,%s,'A_EMITIR',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (banco_codigo, ambiente, protocolo_id, valor, venc, int(dias_apos_vencimento),
         p["nome"], p["documento"], p["email"],
         json.dumps(p["endereco"], ensure_ascii=False), _texto(mensagem, 400), quando, por,
         forma))
    cid = int(novo[0]["id"])
    # O SEU NÚMERO É O NÚMERO DESTA LINHA, e não o do protocolo: um protocolo
    # pode ter um segundo boleto depois de o primeiro vencer, e os dois bancos
    # usam o seu número para recusar duplicata. «CG» diz de onde veio quando
    # aparece no extrato do banco.
    bd.escrever("UPDATE cb_cobrancas SET seu_numero = %s WHERE id = %s",
                (f"CG{cid}"[:LIMITE_SEU_NUMERO], cid))
    _evento(bd, cid, "CADASTRAR", "OK", f"R$ {reais(valor)}, vencimento {venc}", por, quando)
    return cid


# ------------------------------------------------- o que o banco respondeu

def marcar_emitindo(con, cobranca_id: int, *, por: str, agora: datetime) -> dict:
    """Prende a linha e marca EMITINDO ANTES da rede. ESCREVE. Devolve a cobrança.

    É a ordem de `despesas_inter.pagar`: se a resposta do banco se perder, a
    linha diz que foi enviada, e a próxima rodada PROCURA antes de reenviar.
    """
    bd = banco(con)
    bd._escrita()
    c = bd.um("SELECT * FROM cb_cobrancas WHERE id = %s FOR UPDATE", (int(cobranca_id),))
    if not c:
        raise CobrancaError("Cobrança não encontrada.")
    if c["situacao"] != A_EMITIR:
        raise CobrancaError(f"Esta cobrança está «{SITUACOES[c['situacao']]}»: só se emite "
                            f"a que está a emitir.")
    quando = _carimbo(agora)
    bd.escrever("UPDATE cb_cobrancas SET situacao = 'EMITINDO', enviada_em = %s, erro = '' "
                "WHERE id = %s", (quando, int(cobranca_id)))
    _evento(bd, int(cobranca_id), "EMITIR", "ENVIADA", "", por, quando)
    return {**c, "situacao": EMITINDO, "enviada_em": quando}


def gravar_resposta(con, cobranca_id: int, r: Mapping[str, Any], *, por: str,
                    agora: datetime, operacao: str = "CONSULTAR") -> str:
    """Grava o que o adaptador leu do banco. ESCREVE. Devolve a situação nova.

    `r` é a forma COMUM dos dois adaptadores: situacao (uma das nossas),
    banco_id, nosso_numero, linha_digitavel, codigo_barras, pix_copia_e_cola,
    banco_status, banco_motivo, valor_recebido, data_pagamento, forma_recebida.
    Campo ausente não apaga o que já se sabia — a Unicred só manda a linha
    digitável depois do registro na CIP, e uma consulta anterior não a tem.
    """
    bd = banco(con)
    bd._escrita()
    c = bd.um("SELECT * FROM cb_cobrancas WHERE id = %s FOR UPDATE", (int(cobranca_id),))
    if not c:
        raise CobrancaError("Cobrança não encontrada.")
    nova = str(r.get("situacao") or c["situacao"])
    if nova not in SITUACOES:
        nova = c["situacao"]
    # O QUE JÁ FOI LANÇADO OU CANCELADO AQUI NÃO VOLTA POR CONSULTA. O banco
    # pode demorar a refletir o cancelamento, e a consulta seguinte ressuscitaria
    # a cobrança; o depósito lançado é fato do caixa.
    if c["situacao"] in (LANCADA, CANCELADA) and nova != c["situacao"]:
        nova = c["situacao"]
    campos = {"situacao": nova, "consultada_em": _carimbo(agora)}
    for k in ("banco_id", "nosso_numero", "linha_digitavel", "codigo_barras",
              "pix_copia_e_cola", "banco_status", "banco_motivo", "data_pagamento",
              "forma_recebida", "link_pagamento"):
        if r.get(k):
            campos[k] = _texto(r[k], 1000 if k == "link_pagamento" else 600)
    if r.get("valor_recebido") is not None:
        campos["valor_recebido"] = int(r["valor_recebido"])
    if r.get("erro"):
        campos["erro"] = _texto(r["erro"], 600)
    sets = ", ".join(f"{k} = %s" for k in campos)
    bd.escrever(f"UPDATE cb_cobrancas SET {sets} WHERE id = %s",
                (*campos.values(), int(cobranca_id)))
    if nova != c["situacao"] or operacao != "CONSULTAR":
        _evento(bd, int(cobranca_id), operacao, nova,
                r.get("erro") or r.get("banco_motivo") or r.get("banco_status") or "",
                por, _carimbo(agora))
    # A Parcela paga não espera clique: entra no caixa geral se ele estiver
    # aberto hoje. Sem ele, continua RECEBIDA até a abertura.
    if c["banco"] == PARCELA and nova == RECEBIDA and not c["deposito_id"]:
        if entrar_no_caixa_geral(con, cobranca_id, por=por, agora=agora):
            nova = LANCADA
    return nova


def em_espera(c: Mapping[str, Any], agora: datetime) -> bool:
    """A cobrança enviada ainda está no prazo de aparecer no banco?"""
    try:
        enviada = datetime.fromisoformat(str(c.get("enviada_em") or ""))
    except ValueError:
        return False
    return agora.replace(tzinfo=None) - enviada < PRAZO_DE_ESPERA


# --------------------------------------------------------- o que o balcão faz

def cancelar_local(con, cobranca_id: int, *, por: str, agora: datetime, motivo: str) -> None:
    """Cancela a que NUNCA chegou ao banco (A_EMITIR ou FALHOU). ESCREVE.

    A que está no banco se cancela PELO banco (`cobranca_inter.cancelar` e
    `cobranca_unicred.cancelar`): cancelar só aqui deixaria um boleto vivo,
    que o cliente pagaria e o caixa não acharia.
    """
    motivo = _texto(motivo, 50)
    if len(motivo) < 5:
        raise CobrancaError("Escreva o motivo do cancelamento.")
    bd = banco(con)
    bd._escrita()
    c = bd.um("SELECT situacao FROM cb_cobrancas WHERE id = %s FOR UPDATE", (int(cobranca_id),))
    if not c:
        raise CobrancaError("Cobrança não encontrada.")
    if c["situacao"] not in (A_EMITIR, FALHOU):
        raise CobrancaError("Esta cobrança está no banco: o cancelamento vai pelo banco.")
    marcar_cancelada(bd, cobranca_id, por=por, agora=agora, motivo=motivo)


def marcar_cancelada(con, cobranca_id: int, *, por: str, agora: datetime, motivo: str) -> None:
    bd = banco(con)
    quando = _carimbo(agora)
    bd.escrever("""UPDATE cb_cobrancas SET situacao = 'CANCELADA', cancelada_em = %s,
                       cancelada_por = %s, motivo_cancelamento = %s WHERE id = %s""",
                (quando, por, _texto(motivo, 200), int(cobranca_id)))
    _evento(bd, int(cobranca_id), "CANCELAR", "OK", motivo, por, quando)


def caixa_aberto(con, operador: str) -> dict | None:
    """O caixa aberto do operador — a mesma pergunta de `caixa_web.caixa_aberto`."""
    return banco(con).um(
        """SELECT * FROM cx_caixas WHERE operador_nome = %s AND situacao = 'ABERTO'
            ORDER BY data DESC LIMIT 1""", (operador,))


#: O caixa da serventia, não o de um escrevente. Pix, boleto e cartão da
#: Parcela entram aqui. Uma linha por dia (`UNIQUE` de data + operador).
OPERADOR_DO_CAIXA_GERAL = "CAIXA GERAL"


def caixa_geral_de_hoje(con, hoje: date) -> dict | None:
    """O caixa geral aberto na data `hoje`. O de ontem, ainda aberto, não vale:
    dinheiro de dois dias na mesma gaveta é o que a conferência não fecha."""
    return banco(con).um(
        """SELECT * FROM cx_caixas
            WHERE operador_nome = %s AND situacao = 'ABERTO' AND data = %s
            ORDER BY id DESC LIMIT 1""",
        (OPERADOR_DO_CAIXA_GERAL, hoje.isoformat()))


def _data_do_pagamento(texto: Any, hoje: date) -> date:
    try:
        return date.fromisoformat(str(texto or "")[:10])
    except ValueError:
        return hoje


def _depositar_cobranca(con, c: Mapping[str, Any], *, caixa_id: int, por: str,
                        agora: datetime) -> dict:
    """A cobrança paga vira depósito prévio. Não quita item. ESCREVE."""
    import caixa_depositos as DEP
    bd = banco(con)
    valor = int(c["valor_recebido"] or 0)
    if valor <= 0:
        raise CobrancaError("O banco não informou o valor recebido. Atualize a cobrança antes.")
    forma = str(c["forma_recebida"] or "").upper()
    if forma not in ("PIX", "BOLETO", "CARTAO"):
        forma = "BOLETO"
    hoje = agora.date()
    feito = DEP.criar(
        bd, valor_centavos=valor, depositante=c["pagador_nome"],
        documento=c["pagador_documento"], agora=_carimbo(agora), forma_pagamento=forma,
        caixa_id=int(caixa_id), protocolo_id=c["protocolo_id"],
        observacao=(f"Cobrança {c['seu_numero']} paga no {BANCOS[c['banco']]} em "
                    f"{c['data_pagamento'] or '?'} ({forma.lower()})."),
        hoje=hoje, data_do_deposito=_data_do_pagamento(c.get("data_pagamento"), hoje))
    bd.escrever("UPDATE cb_cobrancas SET situacao = 'LANCADA', deposito_id = %s WHERE id = %s",
                (int(feito["id"]), int(c["id"])))
    _evento(bd, int(c["id"]), "LANCAR_NO_CAIXA", "OK",
            f"depósito prévio {feito['numero']}, R$ {reais(valor)}", por, _carimbo(agora))
    return feito


def entrar_no_caixa_geral(con, cobranca_id: int, *, por: str, agora: datetime) -> dict | None:
    """A Parcela paga entra no caixa geral de hoje. Sem ele, fica pendente.

    Devolve o depósito, ou None quando ainda não há caixa geral aberto hoje,
    quando o valor não veio, ou quando a cobrança não é da Parcela. Não quita
    os itens do protocolo. Não usa o caixa de um escrevente.
    """
    bd = banco(con)
    bd._escrita()
    c = bd.um("SELECT * FROM cb_cobrancas WHERE id = %s FOR UPDATE", (int(cobranca_id),))
    if not c or c["banco"] != PARCELA:
        return None
    if c["situacao"] != RECEBIDA or c["deposito_id"]:
        return None
    caixa = caixa_geral_de_hoje(con, agora.date())
    if not caixa or int(c["valor_recebido"] or 0) <= 0:
        return None
    return _depositar_cobranca(con, c, caixa_id=int(caixa["id"]), por=por, agora=agora)


def recolher_no_caixa_geral(con, *, por: str, agora: datetime) -> list[dict]:
    """As Parcela já pagas entram no caixa geral que acabou de abrir. ESCREVE.

    Sem caixa geral aberto hoje, não faz nada: continuam RECEBIDA. Não quita itens.
    """
    if not caixa_geral_de_hoje(con, agora.date()):
        return []
    ids = [int(r["id"]) for r in banco(con).ler(
        """SELECT id FROM cb_cobrancas
            WHERE banco = %s AND situacao = %s AND deposito_id IS NULL
            ORDER BY id""", (PARCELA, RECEBIDA))]
    feitos = []
    for cobranca_id in ids:
        feito = entrar_no_caixa_geral(con, cobranca_id, por=por, agora=agora)
        if feito:
            feitos.append(feito)
    return feitos


def lancar_no_caixa(con, cobranca_id: int, *, por: str, agora: datetime,
                    caixa_id: int | None) -> dict:
    """A cobrança paga no Inter ou na Unicred vira depósito no caixa de quem clica.

    A Parcela não passa por aqui: ela entra sozinha no caixa geral. O depósito
    é `caixa_depositos.criar`. Não quita os itens.

    SEM CAIXA ABERTO NÃO SE LANÇA: o depósito entraria fora do dia e a
    conferência não bateria.
    """
    bd = banco(con)
    bd._escrita()
    c = bd.um("SELECT * FROM cb_cobrancas WHERE id = %s FOR UPDATE", (int(cobranca_id),))
    if not c:
        raise CobrancaError("Cobrança não encontrada.")
    if c["banco"] == PARCELA:
        raise CobrancaError(
            "O pagamento da Parcela entra sozinho no caixa geral da serventia. "
            "Não se lança no caixa de quem está atendendo.")
    if c["situacao"] != RECEBIDA:
        raise CobrancaError("Só se lança no caixa a cobrança que o banco diz que foi paga.")
    if c["deposito_id"]:
        raise CobrancaError("Esta cobrança já foi lançada no caixa.")
    if not caixa_id:
        raise CobrancaError("Abra o seu caixa antes de lançar: o depósito entra no caixa do dia.")
    return _depositar_cobranca(con, c, caixa_id=int(caixa_id), por=por, agora=agora)


# ------------------------------------------------- os pedidos ao banco

# O QUE O BALCÃO PEDE E O BANCO FAZ DEPOIS. Com o cofre da automação
# instalado, a tela NÃO lê a credencial (o cofre recusa `ler` dentro de uma
# requisição web), e quem fala com o banco é o despachante. Então o pedido se
# grava aqui, e quem o executa é `cobranca_banco.executar_pedido` — na hora,
# quando não há cofre; na próxima rodada, quando há. Um pedido por vez: o
# segundo esperaria o resultado do primeiro, e as instruções da Unicred
# recusam «já existe uma instrução sendo executada para o mesmo título».
PEDIDOS = {
    "CANCELAR": "cancelar no banco",
    "ABATIMENTO": "conceder abatimento",
    "CANCELAR_ABATIMENTO": "cancelar o abatimento",
    "PROTESTO": "ajustar o protesto automático",
}


def pedir(con, cobranca_id: int, acao: str, dados: Mapping[str, Any], *, por: str,
          agora: datetime) -> None:
    """Grava o pedido ao banco. ESCREVE. Recusa o que o banco não faria."""
    if acao not in PEDIDOS:
        raise CobrancaError("Pedido desconhecido.")
    bd = banco(con)
    bd._escrita()
    c = bd.um("SELECT * FROM cb_cobrancas WHERE id = %s FOR UPDATE", (int(cobranca_id),))
    if not c:
        raise CobrancaError("Cobrança não encontrada.")
    recurso = {"CANCELAR": "cancelar", "ABATIMENTO": "abatimento",
               "CANCELAR_ABATIMENTO": "abatimento", "PROTESTO": "protesto_automatico"}[acao]
    if recurso not in RECURSOS[c["banco"]]:
        raise CobrancaError(f"O {BANCOS[c['banco']]} não oferece «{PEDIDOS[acao]}» pela API.")
    if c["situacao"] != ABERTA or not c["banco_id"]:
        raise CobrancaError("Só se pede ao banco sobre a cobrança aberta.")
    if c["pedido"]:
        raise CobrancaError("Já há um pedido esperando o banco para esta cobrança.")
    if acao == "CANCELAR" and len(_texto(dados.get("motivo"), 50)) < 5:
        raise CobrancaError("Escreva o motivo do cancelamento.")
    if acao in ("ABATIMENTO", "CANCELAR_ABATIMENTO") and \
            len(_texto(dados.get("justificativa"), 200)) < 5:
        raise CobrancaError("Escreva a justificativa: a Unicred a exige.")
    if acao == "ABATIMENTO" and not 0 < int(dados.get("valor") or 0) < int(c["valor"]):
        raise CobrancaError("O abatimento tem de ser maior que zero e menor que o valor do boleto.")
    if acao == "CANCELAR_ABATIMENTO" and not int(c["abatimento"] or 0):
        raise CobrancaError("Esta cobrança não tem abatimento pedido.")
    pedido = {"acao": acao, **{k: v for k, v in dados.items()}, "por": por,
              "em": _carimbo(agora)}
    bd.escrever("UPDATE cb_cobrancas SET pedido = %s WHERE id = %s",
                (json.dumps(pedido, ensure_ascii=False), int(cobranca_id)))
    _evento(bd, int(cobranca_id), "PEDIDO", acao, PEDIDOS[acao], por, _carimbo(agora))


def pedido(c: Mapping[str, Any]) -> dict | None:
    try:
        lido = json.loads(c.get("pedido") or "")
    except ValueError:
        return None
    return lido if isinstance(lido, dict) and lido.get("acao") in PEDIDOS else None


def encerrar_pedido(con, cobranca_id: int, *, resultado: str, mensagem: str, por: str,
                    agora: datetime) -> None:
    """Tira o pedido da fila, com o que o banco disse. ESCREVE."""
    bd = banco(con)
    bd.escrever("UPDATE cb_cobrancas SET pedido = '' WHERE id = %s", (int(cobranca_id),))
    _evento(bd, int(cobranca_id), "PEDIDO", resultado, mensagem, por, _carimbo(agora))


def com_pedido(con, *, banco_codigo: str, ambiente: str) -> list[dict]:
    return banco(con).ler(
        """SELECT * FROM cb_cobrancas WHERE banco = %s AND ambiente = %s AND pedido <> ''
            ORDER BY id""", (banco_codigo, ambiente))


def a_emitir(con, *, banco_codigo: str, ambiente: str) -> list[dict]:
    return banco(con).ler(
        """SELECT * FROM cb_cobrancas WHERE banco = %s AND ambiente = %s
              AND situacao = 'A_EMITIR' ORDER BY id""", (banco_codigo, ambiente))


def sem_pdf(con, *, banco_codigo: str, ambiente: str) -> list[dict]:
    return banco(con).ler(
        """SELECT * FROM cb_cobrancas WHERE banco = %s AND ambiente = %s
              AND situacao = 'ABERTA' AND pdf_guardado = 0 ORDER BY id""",
        (banco_codigo, ambiente))


# O PDF DO BOLETO SE GUARDA, e mora fora do banco de dados. O banco o gera
# sob demanda, mas com o cofre instalado a tela não fala com o banco — e o
# balcão precisa imprimir o boleto na hora em que o cliente está na frente.
# O abatimento apaga o guardado: o valor impresso mudou.
def caminho_do_pdf(pasta: Any, cobranca_id: int):
    from pathlib import Path
    return Path(pasta) / "cobranca" / f"boleto_{int(cobranca_id)}.pdf"


def guardar_pdf(con, cobranca_id: int, conteudo: bytes, *, pasta: Any) -> None:
    """Grava o PDF na pasta de dados e marca a linha. ESCREVE (disco e banco)."""
    if not conteudo.startswith(b"%PDF-"):
        raise CobrancaError("O banco não devolveu um PDF.")
    alvo = caminho_do_pdf(pasta, cobranca_id)
    alvo.parent.mkdir(parents=True, exist_ok=True)
    temporario = alvo.with_suffix(".tmp")
    temporario.write_bytes(conteudo)
    temporario.replace(alvo)
    banco(con).escrever("UPDATE cb_cobrancas SET pdf_guardado = 1 WHERE id = %s",
                        (int(cobranca_id),))


def esquecer_pdf(con, cobranca_id: int, *, pasta: Any) -> None:
    try:
        caminho_do_pdf(pasta, cobranca_id).unlink(missing_ok=True)
    except OSError:
        pass
    banco(con).escrever("UPDATE cb_cobrancas SET pdf_guardado = 0 WHERE id = %s",
                        (int(cobranca_id),))


def registrar_abatimento(con, cobranca_id: int, *, valor_centavos: int, por: str,
                         agora: datetime, codigo_instrucao: str) -> None:
    """Grava o abatimento pedido ao banco (Unicred). ESCREVE.

    A instrução é ASSÍNCRONA: o 201 diz que o banco recebeu, e não que aplicou.
    O valor fica anotado como PEDIDO, e quem confirma é a consulta seguinte.
    """
    bd = banco(con)
    bd.escrever("UPDATE cb_cobrancas SET abatimento = %s WHERE id = %s",
                (int(valor_centavos), int(cobranca_id)))
    _evento(bd, int(cobranca_id), "ABATIMENTO",
            "PEDIDO" if valor_centavos else "CANCELAMENTO_PEDIDO",
            f"R$ {reais(valor_centavos)} — instrução {codigo_instrucao}", por, _carimbo(agora))


# ----------------------------------------------------------------- listas

def lista(con, *, situacao: str = "", limite: int = 300) -> list[dict]:
    bd = banco(con)
    if situacao and situacao in SITUACOES:
        return bd.ler(
            """SELECT c.*, p.numero AS protocolo_numero FROM cb_cobrancas c
                 LEFT JOIN cx_protocolos p ON p.id = c.protocolo_id
                WHERE c.situacao = %s ORDER BY c.id DESC LIMIT %s""", (situacao, int(limite)))
    return bd.ler(
        """SELECT c.*, p.numero AS protocolo_numero FROM cb_cobrancas c
             LEFT JOIN cx_protocolos p ON p.id = c.protocolo_id
            ORDER BY c.id DESC LIMIT %s""", (int(limite),))


def contagem(con) -> dict[str, int]:
    return {r["situacao"]: int(r["n"]) for r in banco(con).ler(
        "SELECT situacao, count(*) AS n FROM cb_cobrancas GROUP BY situacao")}


def para_acompanhar(con, *, banco_codigo: str, ambiente: str) -> list[dict]:
    """As que o banco ainda pode mudar, DESTE banco e DESTE ambiente."""
    return banco(con).ler(
        """SELECT * FROM cb_cobrancas WHERE banco = %s AND ambiente = %s
              AND situacao = ANY(%s) ORDER BY id""",
        (banco_codigo, ambiente, list(EM_ABERTO)))
