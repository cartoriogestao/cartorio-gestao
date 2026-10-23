"""A COMUNICAÇÃO DE VENDA DE VEÍCULO AO DETRAN — o ato que vem depois da firma.

    «Comunicação de venda de veículo (Notas): reconhecimento de firma no
     CRV/ATPV e comunicação ao DETRAN quando exigida.»  — LG04, item 3

O QUE JÁ EXISTIA, E O QUE FALTAVA
    A FIRMA existia: o reconhecimento em documento de transferência de veículo
    é o item 13.17.3 (serviço 414), com a placa em `nt_reconhecimentos`, e
    1.342 selos medidos pelo caminho do reconhecimento. Por AUTENTICIDADE,
    obrigatoriamente — CN-MA (Prov. COGEX 28/2026), art. 865, II, e, se quem
    vende é empresa, por representante legal (III). A regra mora no
    reconhecimento (`notas_web`); aqui ela só é CONFERIDA: comunicação ligada a
    um reconhecimento por semelhança é recusada.

    A COMUNICAÇÃO não existia em lugar nenhum. O contrato do selador tinha o
    caminho (`/selo/notas/comunicacao-transferencia-veiculo`, esquema
    `ComunicacaoTransferenciaVeiculo`), o E-Ofício tinha o ato 209
    («Comunicação Eletrônica de Transferência de Veículo») e a tabela de 2026
    tem o item **13.22** — «Comunicação eletrônica de transferência de
    veículo», serviço 421, R$ 7,17 de emolumento. Nenhuma tela, tabela ou
    fila o usava.

«QUANDO EXIGIDA» — A COMUNICAÇÃO SE PEDE NO BALCÃO
    Nem todo reconhecimento de veículo vira comunicação: quem pede é a parte,
    e quem decide se cabe é quem atende. Por isso ela é um ato à parte, que
    PODE apontar para o reconhecimento (e herda dele a placa e o vendedor), e
    não um efeito automático da firma.

A INTEGRAÇÃO COM O DETRAN NASCE DESLIGADA, E SEM LEIAUTE
    Não há leiaute oficial do DETRAN-MA nesta casa — nem contrato, nem
    endereço, nem exemplo. Inventar um seria o «número inventado» que
    `centrais_cred` proíbe: quem o usasse acharia que comunicou sem ter
    comunicado. Por isso:

      * o transporte é uma INTERFACE (`Transporte.enviar(comunicacao,
        credencial, ambiente)`); o de fábrica (`TransporteNaoConfigurado`)
        RECUSA com frase clara até o oficial trazer o contrato;
      * o `TransporteFalso` é o serviço de mentira dos testes (sem rede), e é
        com ele que se prova o caminho inteiro em homologação;
      * desligada (o padrão, `settings[detran_comunicacao_ligada] = '0'`), a
        tela registra À MÃO o protocolo que o portal do DETRAN deu
        (`COMUNICADA_A_MAO`) — que é como a casa comunica hoje;
      * o ambiente padrão é HOMOLOGAÇÃO, e no sandbox
        (`centrais_trava_sandbox.e_sandbox`) a produção é recusada.

A CREDENCIAL MORA FORA DO BANCO E FORA DO LOG
    No arquivo `detran.cred`, na MESMA pasta e no MESMO formato dos `.cred`
    de `centrais_cred` (`pasta_de_dados()`, JSON por ambiente). Ela não entrou
    na tabela daquele módulo porque lá a lista das Centrais é contada por
    teste e desenha a tela de credenciais das Centrais — acrescentar o DETRAN
    sem o leiaute dele seria oferecer na tela uma Central que não funciona.
    Quando o contrato chegar, o lugar dela é lá. A senha nunca vai para
    `audit_logs`, para a mensagem de erro nem para o HTML: `_sem_segredo`
    apaga o que o transporte devolver com ela dentro.

O SELO VEM ANTES DE COMUNICAR
    O ato é a comunicação, e ato sem selo não se pratica (regra da casa desde
    16/09/2026). Então o selo sai primeiro; se não sair, nada se comunica e a
    tela diz por quê. Comunicação recusada pelo DETRAN depois do selo pode ser
    reenviada: a referência do selo é a da comunicação, e o SID devolve o
    mesmo selo em vez de comprar outro. O envelope segue, por analogia, a
    forma da autenticação (escrevente, quantidade, ato) com as partes — o
    caminho nunca foi usado pela casa, e a forma se confere na homologação.

PostgreSQL nativo, pelo `bd_nativo`.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

import cpf_cnpj as CPFDOC
from bd_nativo import banco
from seguranca_web import numero_digitado

CAMINHO_DO_SELO = "/selo/notas/comunicacao-transferencia-veiculo"
# Tabela de 2026: «Comunicação eletrônica de transferência de veículo».
ITEM = "13.22"
# O reconhecimento de firma em documento de veículo (13.17.3).
SERVICO_DA_FIRMA_DE_VEICULO = 414

DOCUMENTOS = {
    "CRV": "CRV — Certificado de Registro de Veículo",
    "ATPV": "ATPV — Autorização para Transferência (papel)",
    "ATPV_E": "ATPV-e — Autorização para Transferência eletrônica",
}

SITUACOES = {
    "REGISTRADA": "Registrada — ainda não comunicada",
    "ENVIADA": "Enviada ao DETRAN — aguardando resposta",
    "CONFIRMADA": "Confirmada pelo DETRAN",
    "RECUSADA": "Recusada pelo DETRAN",
    "COMUNICADA_A_MAO": "Comunicada no portal do DETRAN (protocolo à mão)",
}
COMUNICADAS = ("ENVIADA", "CONFIRMADA", "COMUNICADA_A_MAO")
# Quanto tempo uma comunicação fica ENVIADA (reservada para a ida à rede)
# antes de se admitir que a ida morreu no meio — servidor derrubado com a
# resposta a caminho. Antes disso, outro clique é recusado; depois, vale
# mandar de novo ou registrar o protocolo à mão. Folga larga sobre o prazo
# de qualquer transporte, para não liberar uma ida que ainda está viva.
PRAZO_DA_IDA_MINUTOS = 10

HOMOLOGACAO, PRODUCAO = "HOMOLOGACAO", "PRODUCAO"
AMBIENTES = (HOMOLOGACAO, PRODUCAO)
CHAVE_LIGADA = "detran_comunicacao_ligada"
CHAVE_AMBIENTE = "detran_ambiente"
ARQUIVO_DA_CREDENCIAL = "detran.cred"

SCHEMA = (
    """CREATE TABLE IF NOT EXISTS nt_comunicacoes_veiculo (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    reconhecimento_id bigint REFERENCES nt_reconhecimentos(id),
    documento text NOT NULL,              -- CRV | ATPV | ATPV_E
    placa text NOT NULL,
    renavam text NOT NULL,                -- onze dígitos
    vendedor_nome text NOT NULL,
    vendedor_documento text NOT NULL,
    comprador_nome text NOT NULL,
    comprador_documento text NOT NULL,
    data_venda text NOT NULL,
    valor_centavos bigint,
    municipio text,
    uf text,
    situacao text NOT NULL DEFAULT 'REGISTRADA',
    protocolo_detran text,
    comunicada_em text,
    comunicada_por text,
    ambiente text,
    tentativas integer NOT NULL DEFAULT 0,
    ultimo_erro text,
    selo text,
    lancamento_id bigint,
    criado_em text NOT NULL,
    criado_por text
)""",
    "CREATE INDEX IF NOT EXISTS ix_nt_com_veiculo_situacao "
    "ON nt_comunicacoes_veiculo(situacao, id)",
    "CREATE INDEX IF NOT EXISTS ix_nt_com_veiculo_rec "
    "ON nt_comunicacoes_veiculo(reconhecimento_id)",
    # Quando a ida à rede foi reservada (ver `PRAZO_DA_IDA_MINUTOS`).
    "ALTER TABLE nt_comunicacoes_veiculo ADD COLUMN IF NOT EXISTS enviada_em text",
)


class DetranError(ValueError):
    """Recusa de regra ou de transporte, com a frase pronta para o balcão."""


def init_nt_veiculo_detran_schema(con: Any) -> None:
    """Cria a tabela, se faltar. Idempotente — roda em toda subida."""
    bd = banco(con)
    for comando in SCHEMA:
        bd.escrever(comando)


def _texto(valor: Any) -> str:
    return str(valor or "").strip()


def _digitos(valor: Any) -> str:
    return "".join(c for c in str(valor or "") if c.isdigit())


# ----------------------------------------------------------------- conferir

PLACA = re.compile(r"^[A-Z]{3}[0-9][A-Z0-9][0-9]{2}$")


def placa_normal(valor: Any) -> str:
    """`abc-1d23` → `ABC1D23`. Aceita a antiga (ABC1234) e a do Mercosul."""
    return re.sub(r"[^A-Z0-9]", "", _texto(valor).upper())


def renavam_valido(valor: Any) -> bool:
    """O dígito verificador do RENAVAM. Só calcula.

    A regra pública do DENATRAN: o número tem onze dígitos (os antigos, de
    nove, ganham dois zeros à esquerda); os dez primeiros se multiplicam por
    3, 2, 9, 8, 7, 6, 5, 4, 3, 2, a soma vezes dez se divide por onze, e o
    resto é o dígito — dez vira zero. Conferir no texto oficial do DENATRAN se
    a regra mudar.
    """
    d = _digitos(valor)
    if len(d) == 9:
        d = "00" + d
    if len(d) != 11 or d == d[0] * 11:
        return False
    soma = sum(int(c) * p for c, p in zip(d[:10], (3, 2, 9, 8, 7, 6, 5, 4, 3, 2)))
    resto = (soma * 10) % 11
    return (0 if resto == 10 else resto) == int(d[10])


def _documento_da_parte(rotulo: str, valor: Any) -> str:
    doc = _digitos(valor)
    if not doc:
        raise DetranError(f"Informe o CPF ou CNPJ do {rotulo}.")
    if CPFDOC.documento_valido(doc) is not True:
        raise DetranError(f"{rotulo.capitalize()}: "
                          f"{CPFDOC.mensagem_documento_invalido(doc)}")
    return doc


def _centavos(valor: Any) -> int | None:
    texto = _texto(valor)
    if not texto:
        return None
    from caixa_schema import centavos
    try:
        return int(centavos(texto))
    except Exception as erro:                              # noqa: BLE001
        raise DetranError("Valor da venda: escreva como 25.000,00.") from erro


def reconhecimento_da_venda(con: Any, reconhecimento_id: Any) -> dict:
    """O reconhecimento a que a comunicação se liga, conferido. Só LÊ.

    Ele tem de existir, não estar cancelado, ser de documento de veículo
    (13.17.3) e por AUTENTICIDADE — CN-MA art. 865, II. Ligar a comunicação a
    uma firma por semelhança seria o sistema dar por boa a transferência que a
    norma diz que não se faz assim.

    O NÚMERO VEM DA TELA (`?reconhecimento_id=` e o campo do formulário), e o
    que não é número de até 18 dígitos é o «não encontrado» do número que não
    existe — LD13, 21/10/2026: o «abc» no formulário, e o «²» e os 5.000
    dígitos no endereço, caíam no `int()` e davam 500.
    """
    r = banco(con).um("SELECT * FROM nt_reconhecimentos WHERE id = %s",
                      (numero_digitado(reconhecimento_id),))
    if not r:
        raise DetranError("Reconhecimento de firma não encontrado.")
    if int(r.get("cancelado") or 0):
        raise DetranError("O reconhecimento de firma está cancelado.")
    if int(r.get("servico_codigo") or 0) != SERVICO_DA_FIRMA_DE_VEICULO:
        raise DetranError(
            "O reconhecimento não é de documento de veículo (item 13.17.3).")
    if _texto(r.get("especie")).upper() != "AUTENTICIDADE":
        raise DetranError(
            "A firma em documento de transferência de veículo é reconhecida "
            "por AUTENTICIDADE (Código de Normas do MA, art. 865, II). Este "
            "reconhecimento é por semelhança.")
    partes = banco(con).ler(
        """SELECT nome, documento, papel FROM nt_reconhecimento_partes
            WHERE reconhecimento_id = %s ORDER BY id""", (int(r["id"]),))
    return dict(r, partes=partes)


def registrar(con: Any, *, documento: Any, placa: Any, renavam: Any,
              vendedor_nome: Any, vendedor_documento: Any,
              comprador_nome: Any, comprador_documento: Any,
              data_venda: Any, valor: Any = None, municipio: Any = None,
              uf: Any = None, reconhecimento_id: Any = None,
              agora: str | None = None, usuario: Any = None) -> int:
    """Registra o pedido de comunicação. ESCREVE, na transação de quem chama.

    Tudo o que o DETRAN recusaria se confere aqui, com a parte no balcão:
    placa, RENAVAM, os dois documentos e a data. Recusa de leiaute que chega
    depois, pela rede, é a parte indo embora sem saber que não comunicou.
    """
    doc = _texto(documento).upper().replace("-", "_")
    if doc not in DOCUMENTOS:
        raise DetranError("Escolha o documento: CRV, ATPV ou ATPV-e.")
    p = placa_normal(placa)
    if not PLACA.match(p):
        raise DetranError(f"Placa inválida: «{_texto(placa)}». Use ABC1234 "
                          f"ou ABC1D23.")
    ren = _digitos(renavam)
    if len(ren) == 9:
        ren = "00" + ren
    if not renavam_valido(ren):
        raise DetranError("RENAVAM inválido: confira os onze dígitos.")
    vend = _texto(vendedor_nome)
    comp = _texto(comprador_nome)
    if not vend or not comp:
        raise DetranError("Informe o nome do vendedor e o do comprador.")
    vend_doc = _documento_da_parte("vendedor", vendedor_documento)
    comp_doc = _documento_da_parte("comprador", comprador_documento)
    if vend_doc == comp_doc:
        raise DetranError("Vendedor e comprador com o mesmo documento.")
    dia = _texto(data_venda)[:10]
    try:
        quando = date.fromisoformat(dia)
    except ValueError as erro:
        raise DetranError("Data da venda: informe o dia.") from erro
    if quando > date.today():
        raise DetranError("A data da venda não pode ser futura.")
    rec_id = None
    if _texto(reconhecimento_id):
        rec_id = int(reconhecimento_da_venda(con, reconhecimento_id)["id"])
    novo = banco(con).escrever(
        """INSERT INTO nt_comunicacoes_veiculo(reconhecimento_id, documento,
               placa, renavam, vendedor_nome, vendedor_documento,
               comprador_nome, comprador_documento, data_venda,
               valor_centavos, municipio, uf, situacao, criado_em, criado_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'REGISTRADA',%s,%s)
           RETURNING id""",
        (rec_id, doc, p, ren, vend, vend_doc, comp, comp_doc, dia,
         _centavos(valor), _texto(municipio) or None,
         _texto(uf).upper()[:2] or None,
         agora or datetime.now().isoformat(timespec="seconds"),
         _texto(usuario) or None))
    return int(novo[0]["id"])


def comunicacao(con: Any, com_id: int) -> dict | None:
    return banco(con).um("SELECT * FROM nt_comunicacoes_veiculo WHERE id = %s",
                         (int(com_id),))


def listar(con: Any, limite: int = 50) -> list[dict]:
    return banco(con).ler(
        "SELECT * FROM nt_comunicacoes_veiculo ORDER BY id DESC LIMIT %s",
        (int(limite),))


# ------------------------------------------------- a configuração e o segredo

def ligada(get_setting) -> bool:
    """A integração está ligada? O padrão de fábrica é NÃO."""
    return _texto(get_setting(CHAVE_LIGADA, "0")) == "1"


def ambiente(get_setting) -> str:
    """O ambiente em uso. O padrão de fábrica é HOMOLOGAÇÃO."""
    qual = _texto(get_setting(CHAVE_AMBIENTE, HOMOLOGACAO)).upper()
    return qual if qual in AMBIENTES else HOMOLOGACAO


def _caminho_da_credencial(pasta: Any = None) -> Path:
    import centrais_cred as CRED
    return Path(pasta) if pasta else CRED.pasta_de_dados() / ARQUIVO_DA_CREDENCIAL


def _ler_arquivo(caminho: Path) -> dict:
    if not caminho.is_file():
        return {}
    try:
        return json.loads(caminho.read_text(encoding="utf-8-sig")) or {}
    except (OSError, ValueError):
        return {}


def gravar_credencial(*, usuario: Any, senha: Any, ambiente_: Any,
                      pasta: Any = None) -> Path:
    """Guarda o par do DETRAN naquele ambiente. ESCREVE EM DISCO, e não no
    banco — o backup do banco sai da casa, e a senha não pode ir junto. Não
    apaga o outro ambiente: quem grava a produção continua testando."""
    u, s = _texto(usuario), _texto(senha)
    if not u or not s:
        raise DetranError("Informe o usuário e a senha do DETRAN.")
    onde = _texto(ambiente_).upper()
    if onde not in AMBIENTES:
        raise DetranError("Ambiente desconhecido.")
    destino = _caminho_da_credencial(pasta)
    destino.parent.mkdir(parents=True, exist_ok=True)
    guardado = _ler_arquivo(destino)
    guardado[onde] = {"usuario": u, "senha": s}
    destino.write_text(json.dumps(guardado, ensure_ascii=False),
                       encoding="utf-8")
    return destino


def tem_credencial(ambiente_: Any, pasta: Any = None) -> bool:
    """Existe? **Não devolve a senha** — é o que a tela usa para o «✓»."""
    par = _ler_arquivo(_caminho_da_credencial(pasta)).get(
        _texto(ambiente_).upper()) or {}
    return bool(_texto(par.get("usuario")) and _texto(par.get("senha")))


def _credencial(ambiente_: Any, pasta: Any = None) -> dict:
    """O par em claro. Só `comunicar` chama — e só para entregar ao
    transporte, que vai autenticar. Qualquer outro uso é vazamento."""
    par = _ler_arquivo(_caminho_da_credencial(pasta)).get(
        _texto(ambiente_).upper()) or {}
    if not (_texto(par.get("usuario")) and _texto(par.get("senha"))):
        raise DetranError(
            f"Falta a credencial do DETRAN para {ambiente_.lower()}: grave-a "
            f"em Notas → Comunicação de veículo → Configuração.")
    return {"usuario": _texto(par["usuario"]), "senha": _texto(par["senha"])}


def _sem_segredo(texto: Any, credencial: dict | None) -> str:
    """O recado do transporte sem a senha dentro. A mensagem vai para a
    tela, para `ultimo_erro` e para `audit_logs`: senha que aparece numa
    delas aparece nas três."""
    saida = str(texto or "")
    for segredo in ((credencial or {}).get("senha"),):
        if segredo:
            saida = saida.replace(str(segredo), "***")
    return saida[:500]


# ---------------------------------------------------------------- o transporte

@dataclass(frozen=True)
class Resultado:
    """O que o DETRAN respondeu: aceitou (com protocolo) ou recusou."""

    aceito: bool
    protocolo: str | None = None
    mensagem: str = ""


class Transporte(Protocol):
    def enviar(self, comunicacao: dict, credencial: dict,
               ambiente: str) -> Resultado: ...


class TransporteNaoConfigurado:
    """O de fábrica: recusa. Ver o cabeçalho — não há leiaute na casa."""

    def enviar(self, comunicacao: dict, credencial: dict,
               ambiente: str) -> Resultado:
        raise DetranError(
            "O leiaute do DETRAN não está configurado neste sistema: não há "
            "contrato nem endereço do serviço. Comunique no portal do DETRAN "
            "e registre o protocolo à mão, ou desligue a integração.")


class TransporteFalso:
    """O serviço de mentira, para testes e ensaio. NÃO FALA COM A REDE.

    Guarda o que recebeu (`recebidas`) e devolve protocolo `HML-<n>`; com
    `recusar` preenchido, devolve a recusa com aquela mensagem.
    """

    def __init__(self, *, recusar: str | None = None):
        self.recusar = recusar
        self.recebidas: list[tuple[dict, dict, str]] = []

    def enviar(self, comunicacao: dict, credencial: dict,
               ambiente: str) -> Resultado:
        self.recebidas.append((dict(comunicacao), dict(credencial), ambiente))
        if self.recusar:
            return Resultado(aceito=False, mensagem=self.recusar)
        return Resultado(aceito=True,
                         protocolo=f"HML-{len(self.recebidas):06d}",
                         mensagem="aceito")


# O transporte em uso. Troca-se quando o contrato do DETRAN chegar; os testes
# põem aqui o `TransporteFalso`.
TRANSPORTE: Transporte = TransporteNaoConfigurado()


def _corpo_para_o_detran(c: dict) -> dict:
    """O que se manda — os dados do veículo e das partes, sem nada da casa."""
    return {"documento": c["documento"], "placa": c["placa"],
            "renavam": c["renavam"], "data_venda": c["data_venda"],
            "valor_centavos": c.get("valor_centavos"),
            "vendedor": {"nome": c["vendedor_nome"],
                         "documento": c["vendedor_documento"]},
            "comprador": {"nome": c["comprador_nome"],
                          "documento": c["comprador_documento"]},
            "municipio": c.get("municipio"), "uf": c.get("uf")}


def enviar(db, com_id: int, *, get_setting, agora: str | None = None,
           usuario: Any = None, transporte: Transporte | None = None,
           pasta_da_credencial: Any = None) -> dict:
    """Manda ao DETRAN pelo transporte. FALA COM A REDE (ou com o falso).

    Recusa, sem tocar na rede: integração desligada (o padrão), produção no
    sandbox, credencial que falta. Tudo isso é decisão de quem configura, e
    não falha do DETRAN. A resposta grava protocolo e situação; a recusa grava
    o motivo (sem a senha) e conta a tentativa.
    """
    agora = agora or datetime.now().isoformat(timespec="seconds")
    if not ligada(get_setting):
        raise DetranError(
            "A integração com o DETRAN está desligada (é o padrão). Comunique "
            "no portal do DETRAN e registre o protocolo à mão.")
    onde = ambiente(get_setting)
    import centrais_trava_sandbox as SANDBOX
    if onde == PRODUCAO and SANDBOX.e_sandbox():
        raise DetranError(
            "Este é o sandbox: a comunicação ao DETRAN de produção é recusada "
            "aqui. Use a homologação.")
    # A RESERVA: uma transação curta, com a linha presa, confere a situação e
    # marca ENVIADA. Sem ela, dois cliques (ou dois balcões) mandavam a mesma
    # venda duas vezes ao DETRAN, e a segunda resposta escrevia por cima da
    # primeira — CONFIRMADA virando RECUSADA, o protocolo à mão também. A rede
    # fica FORA da transação: nada de linha presa esperando o DETRAN.
    with db.transaction() as con:
        bd = banco(con)
        c = _presa(bd, com_id)
        _conferir_antes_de_comunicar(c, agora)
        credencial = _credencial(onde, pasta_da_credencial)
        antes = c["situacao"]
        bd.escrever(
            """UPDATE nt_comunicacoes_veiculo SET situacao = 'ENVIADA',
                   enviada_em = %s, ambiente = %s
                WHERE id = %s""",
            (agora, onde, int(com_id)))
    meio = transporte or TRANSPORTE
    try:
        r = meio.enviar(_corpo_para_o_detran(c), credencial, onde)
    except DetranError:
        # O transporte recusou antes de falar com o DETRAN (o de fábrica faz
        # isso sempre): nada foi, e a reserva se desfaz.
        _desfazer_a_reserva(db, com_id, antes)
        raise
    except Exception as erro:                              # noqa: BLE001
        r = Resultado(aceito=False, mensagem=f"o DETRAN não respondeu: {erro}")
    except BaseException:
        _desfazer_a_reserva(db, com_id, antes)
        raise
    mensagem = _sem_segredo(r.mensagem, credencial)
    # O FECHO só vale sobre a própria reserva. Se ela venceu o prazo e outro
    # balcão já comunicou por cima, a resposta atrasada não apaga o que ele fez.
    with db.transaction() as con:
        if r.aceito and _texto(r.protocolo):
            gravou = banco(con).escrever(
                """UPDATE nt_comunicacoes_veiculo SET situacao = 'CONFIRMADA',
                       protocolo_detran = %s, comunicada_em = %s,
                       comunicada_por = %s, ambiente = %s,
                       tentativas = tentativas + 1, ultimo_erro = NULL
                    WHERE id = %s AND situacao = 'ENVIADA' AND enviada_em = %s
                RETURNING id""",
                (_texto(r.protocolo), agora, _texto(usuario) or None, onde,
                 int(com_id), agora))
        else:
            gravou = banco(con).escrever(
                """UPDATE nt_comunicacoes_veiculo SET situacao = 'RECUSADA',
                       ambiente = %s, tentativas = tentativas + 1,
                       ultimo_erro = %s
                    WHERE id = %s AND situacao = 'ENVIADA' AND enviada_em = %s
                RETURNING id""",
                (onde, mensagem or "recusado sem motivo", int(com_id), agora))
    if not gravou:
        mensagem = (f"{mensagem} — resposta não gravada: a comunicação já "
                    "tinha sido resolvida por outro caminho.").strip(" —")
    return {"aceito": bool(r.aceito and _texto(r.protocolo)),
            "protocolo": _texto(r.protocolo) or None, "ambiente": onde,
            "mensagem": mensagem}


def _presa(bd, com_id: int) -> dict | None:
    """A comunicação com a linha presa até o fim da transação. Para quem
    confere a situação e grava em cima (envio e protocolo à mão)."""
    bd._escrita()
    return bd.um("SELECT * FROM nt_comunicacoes_veiculo WHERE id = %s "
                 "FOR UPDATE", (int(com_id),))


def _ida_viva(c: dict, agora: str) -> bool:
    """ENVIADA há menos que o prazo: a ida à rede ainda pode responder."""
    if c.get("situacao") != "ENVIADA":
        return False
    try:
        desde = datetime.fromisoformat(_texto(c.get("enviada_em")))
        ate = datetime.fromisoformat(_texto(agora))
    except ValueError:
        return False
    return ate - desde < timedelta(minutes=PRAZO_DA_IDA_MINUTOS)


def _conferir_antes_de_comunicar(c: dict | None, agora: str) -> None:
    """As recusas comuns ao envio e ao protocolo à mão, na ordem de sempre.
    Chame com a linha PRESA (`_presa`)."""
    if not c:
        raise DetranError("Comunicação não encontrada.")
    if c["situacao"] in ("CONFIRMADA", "COMUNICADA_A_MAO"):
        raise DetranError("Esta venda já foi comunicada.")
    if _ida_viva(c, agora):
        raise DetranError(
            "Esta venda está sendo enviada ao DETRAN agora. Espere a resposta "
            "e abra a comunicação de novo.")
    if not _texto(c.get("selo")):
        raise DetranError("A comunicação ainda não tem selo — sele antes.")


def _desfazer_a_reserva(db, com_id: int, antes: str) -> None:
    """Volta a situação de antes da reserva, se ela ainda for a mesma ENVIADA.
    Só para quando NADA foi ao DETRAN — senão a resposta se perderia."""
    with db.transaction() as con:
        banco(con).escrever(
            "UPDATE nt_comunicacoes_veiculo SET situacao = %s, enviada_em = NULL "
            "WHERE id = %s AND situacao = 'ENVIADA'", (antes, int(com_id)))


def registrar_protocolo_a_mao(con: Any, com_id: int, *, protocolo: Any,
                              agora: str, usuario: Any) -> None:
    """O protocolo que o portal do DETRAN deu, digitado. ESCREVE.

    É como a casa comunica enquanto a integração está desligada. Exige o
    selo antes, pela mesma razão do envio: o ato é a comunicação. A linha
    fica presa da conferência à gravação: um envio pela rede que corra junto
    espera, e não troca o protocolo à mão por RECUSADA.
    """
    numero = _texto(protocolo)
    if len(numero) < 4:
        raise DetranError("Informe o protocolo que o portal do DETRAN deu.")
    _conferir_antes_de_comunicar(_presa(banco(con), com_id), agora)
    banco(con).escrever(
        """UPDATE nt_comunicacoes_veiculo SET situacao = 'COMUNICADA_A_MAO',
               protocolo_detran = %s, comunicada_em = %s, comunicada_por = %s,
               ultimo_erro = NULL
            WHERE id = %s""",
        (numero, agora, _texto(usuario) or None, int(com_id)))


# -------------------------------------------------------------------- o selo

def envelope(*, codigo_tj: Any, escrevente: Any, versao_tabela: Any,
             partes: list[dict]) -> dict:
    """O corpo de `/selo/notas/comunicacao-transferencia-veiculo`. Só calcula.

    Por analogia — ver o cabeçalho: a forma da autenticação (escrevente,
    quantidade, ato), que vai pelo mesmo campo `dadosSelo`, com as partes da
    venda em `partes.parteAto`.
    """
    faltando = [o for o, v in (("o item da tabela de custas", codigo_tj),
                               ("o escrevente", escrevente),
                               ("a versão da tabela de custas", versao_tabela))
                if not _texto(v)]
    if faltando:
        raise DetranError(
            f"O selo da comunicação não sai sem {', '.join(faltando)}.")
    return {
        "escrevente": _texto(escrevente),
        "quantidade": 1,
        "partes": {"nomePartes": [],
                   "parteAto": [{"nome": _texto(p.get("nome")),
                                 "documento": _digitos(p.get("documento"))}
                                for p in partes]},
        "ato": {"codigo": _texto(codigo_tj),
                "codigoTabelaCusta": _texto(versao_tabela)},
    }


def selar(db, pasta_de_dados: Any, com_id: int, *, escrevente: Any,
          data_da_tabela: Any, cns: Any, agora: str | None = None) -> dict:
    """O selo da comunicação, ANTES de comunicar. FALA COM A REDE.

    Nunca estoura: a falha volta como motivo e fica em `ultimo_erro`.
    """
    import ato_selado as AS
    agora = agora or datetime.now().isoformat(timespec="seconds")
    with db.connect() as con:
        c = comunicacao(con, com_id)
    if not c:
        return {"selado": False, "motivo": "Comunicação não encontrada."}
    if _texto(c.get("selo")):
        return {"selado": True, "numero": c["selo"], "ja_tinha": True}
    try:
        corpo = envelope(
            codigo_tj=ITEM, escrevente=escrevente,
            versao_tabela=AS.versao_da_tabela_de_custas(CAMINHO_DO_SELO,
                                                        data_da_tabela),
            partes=[{"nome": c["vendedor_nome"],
                     "documento": c["vendedor_documento"]},
                    {"nome": c["comprador_nome"],
                     "documento": c["comprador_documento"]}])
    except DetranError as erro:
        r = {"selado": False, "motivo": str(erro)}
    else:
        r = AS.selar_o_ato_lavrado(
            db, pasta_de_dados, tabela="nt_comunicacoes_veiculo",
            ato_id=int(com_id), tipo="COMUNICACAO_VEICULO", atribuicao="NOTAS",
            agora=agora, cns=cns, usuario=_texto(escrevente) or None,
            dados=corpo, caminho=CAMINHO_DO_SELO,
            referencia=f"nt_comunicacoes_veiculo:{int(com_id)}:{ITEM}:1")
    if not r.get("selado"):
        with db.transaction() as con:
            banco(con).escrever(
                "UPDATE nt_comunicacoes_veiculo SET ultimo_erro = %s "
                "WHERE id = %s",
                (f"selo: {r.get('motivo') or 'não saiu'}"[:500], int(com_id)))
    return r


def preco(con: Any, *, data: Any = None) -> dict | None:
    """Quanto custa o item 13.22 pela tabela do dia. `None` sem tabela."""
    import ato_selado as AS
    servico = AS.servico_do_codigo_tj(con, ITEM)
    if not servico:
        return None
    try:
        conta = AS.calcular_custas(con, servico=int(servico["codigo"]),
                                   data=data)
    except AS.AtoError:
        return None
    return {"codigo_tj": ITEM, "servico": int(servico["codigo"]),
            "descricao": servico.get("descricao"), "total": conta["total"],
            "total_centavos": conta["total_centavos"]}


# --------------------------------------------------------------------- telas

QUEM_OPERA = ("ADMIN", "MANAGER", "USER")
QUEM_LE = ("ADMIN", "MANAGER", "USER", "AUDITOR")
# LIGAR A INTEGRAÇÃO E GUARDAR A SENHA É DE QUEM RESPONDE PELA SERVENTIA.
QUEM_CONFIGURA = ("ADMIN",)


def registrar_rotas(app, db, login_required, roles_required, audit) -> None:
    """Pendura as telas da comunicação de venda de veículo."""
    from flask import (abort, flash, redirect, render_template, request,
                       url_for)

    usuario_nome = app.extensions["usuario_nome"]

    def _campo(nome: str) -> str:
        return (request.form.get(nome) or "").strip()

    @app.route("/notas/veiculos")
    @login_required
    @roles_required(*QUEM_LE)
    def notas_veiculos():
        """A lista e o formulário. Só LÊ — o reconhecimento só preenche."""
        rec_id = (request.args.get("reconhecimento_id") or "").strip()
        sugestao: dict = {}
        with db.connect() as con:
            if rec_id.isdigit():
                try:
                    r = reconhecimento_da_venda(con, rec_id)
                    vend = (r["partes"] or [{}])[0]
                    sugestao = {"reconhecimento_id": r["id"],
                                "placa": r.get("veiculo_placa") or "",
                                "vendedor_nome": vend.get("nome") or "",
                                "vendedor_documento": vend.get("documento") or ""}
                except DetranError as erro:
                    flash(str(erro), "danger")
            ultimas = listar(con)
            valor = preco(con)
        return render_template(
            "notas_veiculos.html", ultimas=ultimas, sugestao=sugestao,
            preco=valor, DOCUMENTOS=DOCUMENTOS, SITUACOES=SITUACOES,
            ligada=ligada(db.get_setting), ambiente=ambiente(db.get_setting))

    @app.route("/notas/veiculos/nova", methods=["POST"])
    @login_required
    @roles_required(*QUEM_OPERA)
    def notas_veiculo_nova():
        try:
            with db.transaction() as con:
                cid = registrar(
                    con, documento=_campo("documento"), placa=_campo("placa"),
                    renavam=_campo("renavam"),
                    vendedor_nome=_campo("vendedor_nome"),
                    vendedor_documento=_campo("vendedor_documento"),
                    comprador_nome=_campo("comprador_nome"),
                    comprador_documento=_campo("comprador_documento"),
                    data_venda=_campo("data_venda"), valor=_campo("valor"),
                    municipio=_campo("municipio"), uf=_campo("uf"),
                    reconhecimento_id=_campo("reconhecimento_id") or None,
                    agora=db.now(), usuario=usuario_nome())
        except DetranError as erro:
            flash(str(erro), "danger")
            return redirect(url_for("notas_veiculos"))
        audit("NT_COMUNICACAO_VEICULO_REGISTRADA", "nt_comunicacoes_veiculo",
              cid, {"documento": _campo("documento").upper(),
                    "reconhecimento_id": _campo("reconhecimento_id") or None})
        flash(f"Comunicação nº {cid} registrada. Sele e comunique.", "success")
        return redirect(url_for("notas_veiculo", com_id=cid))

    @app.route("/notas/veiculos/<int:com_id>")
    @login_required
    @roles_required(*QUEM_LE)
    def notas_veiculo(com_id: int):
        with db.connect() as con:
            c = comunicacao(con, com_id)
        if not c:
            abort(404)
        return render_template(
            "notas_veiculo.html", c=c, DOCUMENTOS=DOCUMENTOS,
            SITUACOES=SITUACOES, ligada=ligada(db.get_setting),
            ambiente=ambiente(db.get_setting))

    @app.route("/notas/veiculos/<int:com_id>/comunicar", methods=["POST"])
    @login_required
    @roles_required(*QUEM_OPERA)
    def notas_veiculo_comunicar(com_id: int):
        """Sela (se falta) e comunica: pelo transporte, ligado; à mão, não.

        O SELO PRIMEIRO, e sem ele nada se comunica — ver o cabeçalho.
        """
        import selo_robo as SR
        if SR.exige_humano_para_selar():
            abort(403)
        volta = redirect(url_for("notas_veiculo", com_id=com_id))
        with db.connect() as con:
            c = comunicacao(con, com_id)
        if not c:
            abort(404)
        if not _texto(c.get("selo")):
            r = selar(db, Path(app.config["DATA_DIR"]), com_id,
                      escrevente=usuario_nome(),
                      data_da_tabela=db.get_setting("selo_tabela_custas_em", ""),
                      cns=db.get_setting("ri_cns", ""))
            if not r.get("selado"):
                audit("NT_COMUNICACAO_VEICULO_SELO_FALHOU",
                      "nt_comunicacoes_veiculo", com_id,
                      {"motivo": r.get("motivo")})
                flash("A venda NÃO foi comunicada: o selo não saiu. Motivo: "
                      f"{r.get('motivo')}. Corrija o selo e tente de novo.",
                      "danger")
                return volta
            audit("NT_COMUNICACAO_VEICULO_SELADA", "nt_comunicacoes_veiculo",
                  com_id, {"selo": r.get("numero")})
        if ligada(db.get_setting):
            try:
                resultado = enviar(db, com_id, get_setting=db.get_setting,
                                   usuario=usuario_nome())
            except DetranError as erro:
                flash(str(erro), "danger")
                return volta
            audit("NT_COMUNICACAO_VEICULO_ENVIADA", "nt_comunicacoes_veiculo",
                  com_id, {"aceito": resultado["aceito"],
                           "protocolo": resultado["protocolo"],
                           "ambiente": resultado["ambiente"],
                           "mensagem": resultado["mensagem"]})
            if resultado["aceito"]:
                flash(f"DETRAN ({resultado['ambiente'].lower()}) recebeu: "
                      f"protocolo {resultado['protocolo']}.", "success")
            else:
                flash(f"O DETRAN recusou: {resultado['mensagem']}", "danger")
            return volta
        try:
            with db.transaction() as con:
                registrar_protocolo_a_mao(con, com_id,
                                          protocolo=_campo("protocolo"),
                                          agora=db.now(),
                                          usuario=usuario_nome())
        except DetranError as erro:
            flash(str(erro), "danger")
            return volta
        audit("NT_COMUNICACAO_VEICULO_A_MAO", "nt_comunicacoes_veiculo",
              com_id, {"protocolo": _campo("protocolo")})
        flash("Comunicação registrada com o protocolo do portal do DETRAN.",
              "success")
        return volta

    @app.route("/notas/veiculos/configuracao", methods=["GET", "POST"])
    @login_required
    @roles_required(*QUEM_CONFIGURA)
    def notas_veiculo_configuracao():
        """Ligar, escolher o ambiente e guardar a credencial. GET só lê.

        A credencial vai para o arquivo, e o rastro diz QUE se gravou — nunca
        o quê.
        """
        if request.method == "POST":
            acao = _campo("acao")
            if acao == "credencial":
                onde = _campo("ambiente").upper()
                try:
                    gravar_credencial(usuario=_campo("usuario"),
                                      senha=request.form.get("senha"),
                                      ambiente_=onde)
                except DetranError as erro:
                    flash(str(erro), "danger")
                    return redirect(url_for("notas_veiculo_configuracao"))
                audit("NT_DETRAN_CREDENCIAL_GRAVADA", "settings", None,
                      {"ambiente": onde})
                flash("Credencial do DETRAN gravada fora do banco.", "success")
                return redirect(url_for("notas_veiculo_configuracao"))
            novo_ambiente = _campo("ambiente").upper()
            if novo_ambiente not in AMBIENTES:
                flash("Ambiente desconhecido.", "danger")
                return redirect(url_for("notas_veiculo_configuracao"))
            novo = "1" if request.form.get("ligada") == "1" else "0"
            antes = {"ligada": ligada(db.get_setting),
                     "ambiente": ambiente(db.get_setting)}
            db.set_settings({CHAVE_LIGADA: novo, CHAVE_AMBIENTE: novo_ambiente})
            audit("NT_DETRAN_CONFIGURADO", "settings", None,
                  {"antes": antes, "depois": {"ligada": novo == "1",
                                              "ambiente": novo_ambiente}})
            flash("Configuração do DETRAN gravada.", "success")
            return redirect(url_for("notas_veiculo_configuracao"))
        return render_template(
            "notas_veiculo_configuracao.html", ligada=ligada(db.get_setting),
            ambiente=ambiente(db.get_setting), AMBIENTES=AMBIENTES,
            credenciais={a: tem_credencial(a) for a in AMBIENTES})
