"""AS DESPESAS DA SERVENTIA — do cadastro ao Livro Diário, passando pelo banco.

POR QUE EXISTE (24/10/2026)
    Pedido do oficial: «cadastro de despesas do cartório e, depois de
    autorizadas dentro do sistema, o pagamento sair automático; com isso o
    sistema já geraria o relatório das despesas, poderia cadastrar no SIAFERJ
    e gerar o livro caixa». O Livro Diário Auxiliar (`livro_diario`) já
    existia, mas a despesa só entrava nele à mão, depois de paga. Faltava o
    caminho de antes: cadastrar, autorizar, pagar e conferir no extrato.

O CICLO, E QUEM FAZ CADA PASSO
    AGUARDANDO_AUTORIZACAO → AUTORIZADA → ENVIADA → PAGA → CONCILIADA
        cadastrar         autorizar     pagar     banco    extrato
    Fora do caminho: FALHOU (o banco recusou; o ADMIN devolve à autorização
    ou cancela), CANCELADA, e PAGA_FORA (paga em dinheiro ou noutra conta,
    registrada à mão pelo ADMIN).

    - CADASTRAR nunca autoriza nem paga — com uma exceção decidida pelo
      oficial (abaixo).
    - AUTORIZAR é do ADMIN, e de mais ninguém (decisão de 24/10/2026: «só
      você»). Quem cadastrou não autoriza pelo fato de ter cadastrado.
    - PAGAR é de `despesas_inter` e roda no despachante da automação.
    - O LIVRO DIÁRIO só recebe a despesa quando o débito aparece no EXTRATO
      (art. 190, II: «no dia do efetivo pagamento»). Pagamento pedido não é
      pagamento feito: um boleto pode ficar agendado, aguardando aprovação no
      banco, ou voltar com erro.

A REGRA DAS GUIAS (decisão do oficial, 24/10/2026)
    As guias que o robô da automação baixa do Portal do Selo (FERJ, FERC e
    demais fundos) podem nascer AUTORIZADAS sem ele, quando as três condições
    se cumprem juntas: a origem é o robô do Portal do Selo, o valor da guia é
    igual ao que o sistema calculou dos selos (`valor_esperado_centavos`), e
    fica dentro do teto das guias. Falhou uma, a guia espera o oficial. O
    robô nunca chama `autorizar`: quem aplica a regra é este módulo.

GUIA DE FUNDO NÃO É DESPESA (decisão do oficial, 24/10/2026)
    O fundo não é receita da serventia (art. 191 do CN-MA; `livro_diario`
    deixa os fundos fora da receita bruta). Pagar a guia é REPASSE: entra no
    relatório e na contabilidade, é conciliado no extrato como qualquer
    pagamento, e NÃO vira linha de despesa no Livro Diário. A natureza sai
    da categoria, e não de quem cadastra.

AS TRAVAS DO DINHEIRO
    A API do Inter paga sem perguntar ao banco (conforme a configuração da
    conta), e por isso as travas moram aqui:
    - o pagamento automático nasce DESLIGADO e no ambiente de TESTE;
    - teto por pagamento e teto por dia, que nascem baixos e o oficial ajusta;
      despesa acima do teto só sai se o ADMIN marcou, ao autorizar, que
      autoriza acima do teto;
    - o código de pagamento é LIDO e conferido: o boleto traz valor e
      vencimento dentro da linha digitável, e o Pix copia e cola traz o valor
      e um CRC — valor que não bate é recusa, e não aviso;
    - a despesa autorizada não muda: mudar valor, código ou favorecido
      devolve à autorização.

PostgreSQL nativo, pelo `bd_nativo`. Dinheiro em centavos, `bigint`. Data e
hora se calculam no Python (regra da casa).
"""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

import cpf_cnpj
from bd_nativo import banco
from caixa_schema import reais

AGUARDANDO = "AGUARDANDO_AUTORIZACAO"
AUTORIZADA = "AUTORIZADA"
ENVIADA = "ENVIADA"
PAGA = "PAGA"
CONCILIADA = "CONCILIADA"
FALHOU = "FALHOU"
CANCELADA = "CANCELADA"
PAGA_FORA = "PAGA_FORA"

SITUACOES = {
    AGUARDANDO: "Aguardando a autorização do oficial",
    AUTORIZADA: "Autorizada — o pagamento sai na próxima rodada",
    ENVIADA: "Enviada ao banco",
    PAGA: "Paga pelo banco — falta conferir no extrato",
    CONCILIADA: "Paga e conferida no extrato",
    FALHOU: "O banco não pagou — veja o motivo",
    CANCELADA: "Cancelada",
    PAGA_FORA: "Paga fora do banco (registrada à mão)",
}

DESPESA, REPASSE = "DESPESA", "REPASSE_DE_FUNDO"
NATUREZAS = {DESPESA: "Despesa da serventia (vai ao Livro Diário)",
             REPASSE: "Repasse de fundo (fora do Livro Diário)"}

# AS CATEGORIAS, e a natureza de cada uma. As de despesa seguem o art. 8º do
# Provimento CNJ 45/2015 (despesas do serviço delegado); as de repasse são os
# fundos do selo (`atribuicoes.FUNDOS`).
CATEGORIAS: dict[str, tuple[str, str]] = {
    "LOCACAO": ("Locação do imóvel", DESPESA),
    "CONCESSIONARIAS": ("Energia, água, telefone e internet", DESPESA),
    "PESSOAL": ("Salários dos prepostos", DESPESA),
    "ENCARGOS": ("Encargos trabalhistas e previdenciários dos prepostos", DESPESA),
    "PLANO_SAUDE": ("Plano de saúde coletivo", DESPESA),
    "MATERIAIS": ("Material de expediente e consumo", DESPESA),
    "INFORMATICA": ("Informática, sistemas e certificados", DESPESA),
    "MOVEIS_EQUIPAMENTOS": ("Móveis e equipamentos", DESPESA),
    "OBRAS": ("Obras e manutenção do imóvel", DESPESA),
    "LIMPEZA_SEGURANCA": ("Limpeza e segurança", DESPESA),
    "ARQUIVO_SEGURANCA": ("Arquivo de segurança e digitalização", DESPESA),
    "CURSOS": ("Cursos e treinamento", DESPESA),
    "ASSESSORIA": ("Assessoria jurídica, contábil e de engenharia", DESPESA),
    "ISS": ("ISS sobre os emolumentos", DESPESA),
    "TARIFAS": ("Tarifas bancárias", DESPESA),
    "OUTRAS": ("Outras despesas do serviço", DESPESA),
    "FUNDO_FERJ": ("Guia do FERJ", REPASSE),
    "FUNDO_FERC": ("Guia do FERC", REPASSE),
    "FUNDO_FADEP": ("Guia do FADEP", REPASSE),
    "FUNDO_FEMP": ("Guia do FEMP", REPASSE),
    "FUNDO_FERRFIS": ("Guia do FERRFIS", REPASSE),
    # O REPASSE AO APRESENTANTE DO TÍTULO PAGO (29/10/2026): o boleto que o robô
    # emite no portal da CRA (`protesto_repasse_portal`). É dinheiro de
    # terceiro que passou pela casa — não é despesa da serventia —, e por isso
    # fica fora do Livro Diário e do SIAFERJ, como o repasse de fundo.
    "REPASSE_APRESENTANTE": ("Repasse ao apresentante — título pago no Protesto",
                             REPASSE),
}

BOLETO, ARRECADACAO, PIX_COPIA_E_COLA, PIX_CHAVE, MANUAL = (
    "BOLETO", "ARRECADACAO", "PIX_COPIA_E_COLA", "PIX_CHAVE", "MANUAL")
FORMAS = {
    BOLETO: "Boleto bancário (linha digitável de 47 dígitos)",
    ARRECADACAO: "Conta, guia ou tributo (código de 48 dígitos começando por 8)",
    PIX_COPIA_E_COLA: "Pix copia e cola",
    PIX_CHAVE: "Pix por chave",
    MANUAL: "Pago fora do banco (dinheiro, outra conta)",
}

ORIGEM_PORTAL_SELO = "AUTOMACAO:PORTAL_SELO"

# A CONFIGURAÇÃO, COM O PADRÃO DE QUEM NUNCA MEXEU. Mora em `settings`. O
# pagamento automático nasce DESLIGADO e no SANDBOX, e os tetos nascem baixos
# (decisão do oficial: «eu defino na tela depois»).
PADRAO: dict[str, str] = {
    "despesas_pagamento_ligado": "0",
    "despesas_ambiente": "sandbox",
    "despesas_teto_por_pagamento": "1000,00",
    "despesas_teto_por_dia": "3000,00",
    "despesas_teto_guia": "1000,00",
    "despesas_regra_guias_ligada": "1",
}
ROTULOS: dict[str, str] = {
    "despesas_pagamento_ligado": "Pagamento automático ligado",
    "despesas_ambiente": "Ambiente do banco",
    "despesas_teto_por_pagamento": "Teto por pagamento (R$)",
    "despesas_teto_por_dia": "Teto por dia (R$)",
    "despesas_teto_guia": "Teto das guias autorizadas pela regra (R$)",
    "despesas_regra_guias_ligada": "Guias do Portal do Selo com valor conferido nascem autorizadas",
}
AMBIENTES = {"sandbox": "Teste (sandbox do Inter, sem dinheiro de verdade)",
             "producao": "Produção (dinheiro de verdade)"}

ENTIDADE_DO_ANEXO = "DESPESA"
EXTENSOES = (".pdf", ".png", ".jpg", ".jpeg", ".xml")
MINIMO_DA_DESCRICAO = 10

SCHEMA: tuple[tuple[str, str], ...] = (
    ("dp_despesas", """
        CREATE TABLE IF NOT EXISTS dp_despesas (
            id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            situacao TEXT NOT NULL CHECK (situacao IN (
                'AGUARDANDO_AUTORIZACAO', 'AUTORIZADA', 'ENVIADA', 'PAGA',
                'CONCILIADA', 'FALHOU', 'CANCELADA', 'PAGA_FORA')),
            natureza TEXT NOT NULL CHECK (natureza IN ('DESPESA', 'REPASSE_DE_FUNDO')),
            categoria TEXT NOT NULL,
            descricao TEXT NOT NULL,
            beneficiario_nome TEXT NOT NULL,
            beneficiario_documento TEXT NOT NULL DEFAULT '',
            valor bigint NOT NULL CHECK (valor > 0),
            vencimento TEXT NOT NULL,
            forma TEXT NOT NULL,
            codigo TEXT NOT NULL DEFAULT '',
            codigo_barras TEXT NOT NULL DEFAULT '',
            documento_especie TEXT NOT NULL,
            documento_numero TEXT NOT NULL DEFAULT '',
            origem TEXT NOT NULL,
            chave_origem TEXT,
            valor_esperado bigint,
            divergencia TEXT NOT NULL DEFAULT '',
            cadastrada_em TEXT NOT NULL,
            cadastrada_por TEXT NOT NULL,
            autorizada_em TEXT,
            autorizada_por TEXT,
            autorizada_pela_regra TEXT NOT NULL DEFAULT '',
            acima_do_teto integer NOT NULL DEFAULT 0,
            ambiente TEXT,
            enviada_em TEXT,
            data_pagamento TEXT,
            tentativas integer NOT NULL DEFAULT 0,
            banco_codigo TEXT,
            banco_status TEXT NOT NULL DEFAULT '',
            banco_e2e TEXT,
            mensagem TEXT NOT NULL DEFAULT '',
            paga_em TEXT,
            extrato_id TEXT,
            ld_despesa_id bigint,
            cancelada_em TEXT,
            cancelada_por TEXT,
            motivo_cancelamento TEXT NOT NULL DEFAULT ''
        )"""),
    # A MESMA GUIA NÃO ENTRA DUAS VEZES, e a trava mora no banco: o robô roda
    # toda segunda, e a segunda rodada do mesmo dia acha a primeira.
    ("ux_dp_despesas_origem", """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_dp_despesas_origem
            ON dp_despesas (origem, chave_origem) WHERE chave_origem IS NOT NULL"""),
    ("ix_dp_despesas_situacao",
     "CREATE INDEX IF NOT EXISTS ix_dp_despesas_situacao ON dp_despesas (situacao, id)"),
    ("dp_eventos", """
        CREATE TABLE IF NOT EXISTS dp_eventos (
            id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            despesa_id bigint NOT NULL REFERENCES dp_despesas(id),
            quando TEXT NOT NULL,
            operacao TEXT NOT NULL,
            resultado TEXT NOT NULL,
            mensagem TEXT NOT NULL DEFAULT '',
            usuario TEXT NOT NULL DEFAULT ''
        )"""),
    ("ix_dp_eventos_despesa",
     "CREATE INDEX IF NOT EXISTS ix_dp_eventos_despesa ON dp_eventos (despesa_id, id)"),
)


class DespesaError(ValueError):
    """Impedimento de regra, com a frase pronta para a tela."""


def init_despesas_schema(con) -> None:
    """Cria as tabelas e os índices que faltarem. Idempotente."""
    bd = banco(con)
    for nome, comando in SCHEMA:
        if not bd.tem_tabela(nome):
            bd.escrever(comando)


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
        raise DespesaError(f"{rotulo} não é uma data válida (AAAA-MM-DD).") from erro


def _so_digitos(texto: str) -> bool:
    return bool(texto) and all("0" <= c <= "9" for c in texto)


def _parte_inteira(texto: str) -> str | None:
    """«1.234.567» ou «1234567» → «1234567»; o resto, None. Só calcula."""
    grupos = texto.split(".")
    if len(grupos) == 1:
        return texto if _so_digitos(texto) else None
    if not (_so_digitos(grupos[0]) and len(grupos[0]) <= 3):
        return None
    if not all(_so_digitos(g) and len(g) == 3 for g in grupos[1:]):
        return None
    return "".join(grupos)


def centavos_da_tela(valor: Any) -> int:
    """«1.234,56» → 123456. Recusa o que não é dinheiro em vez de adivinhar.

    Aceita «1.234,56», «1234,56», «1234.56» e «1.234». **SEM EXPRESSÃO
    REGULAR** (27/10/2026): a que havia aqui recuava em polinômio com uma fila
    de zeros (alerta do CodeQL), e o valor vem do formulário."""
    if isinstance(valor, int):
        return valor
    texto = str(valor or "").strip().replace("R$", "").strip()
    if not texto:
        return 0
    inteiro, virgula, frac = texto.partition(",")
    if virgula:
        ok = _so_digitos(frac) and len(frac) <= 2
    else:
        antes, ponto, depois = texto.partition(".")
        if (ponto and "." not in depois and _so_digitos(antes)
                and _so_digitos(depois) and len(depois) <= 2):
            inteiro, frac = antes, depois          # «1234.56»
        ok = True
    inteiro = _parte_inteira(inteiro) if ok else None
    if inteiro is None:
        raise DespesaError(f"Valor ilegível: «{valor}». Use 1.234,56.")
    return int(inteiro) * 100 + int((frac + "00")[:2])


# ------------------------------------------------- o boleto e a guia de convênio
#
# A LINHA DIGITÁVEL DIZ O VALOR, e às vezes o vencimento: conferir isso antes
# de pagar é o que impede pagar o boleto de outro valor colado por engano. As
# regras são as do padrão FEBRABAN (boleto bancário: 47 dígitos na linha, 44
# no código de barras; arrecadação — contas, guias, tributos: 48 e 44,
# começando por 8). Conferidas contra os códigos de exemplo do sandbox do
# Inter (especificação da API Banking, 24/10/2026), em `tests/test_despesas.py`.

# O FATOR DE VENCIMENTO conta dias desde 07/10/1997 e chegou a 9999 em
# 21/02/2025; a partir de 22/02/2025 recomeçou em 1000. O mesmo fator aponta
# para duas datas, e quem decide é o vencimento informado.
_BASE_FATOR = date(1997, 10, 7)
_BASE_FATOR_NOVA = date(2025, 2, 22) - timedelta(days=1000)


def _mod10(numero: str) -> int:
    soma, peso = 0, 2
    for d in reversed(numero):
        p = int(d) * peso
        soma += p // 10 + p % 10
        peso = 1 if peso == 2 else 2
    return (10 - soma % 10) % 10


def _mod11_bancario(numero: str) -> int:
    soma, peso = 0, 2
    for d in reversed(numero):
        soma += int(d) * peso
        peso = 2 if peso == 9 else peso + 1
    dv = 11 - soma % 11
    return 1 if dv in (0, 10, 11) else dv


def _mod11_arrecadacao(numero: str) -> int:
    soma, peso = 0, 2
    for d in reversed(numero):
        soma += int(d) * peso
        peso = 2 if peso == 9 else peso + 1
    resto = soma % 11
    if resto in (0, 1):
        return 0
    if resto == 10:
        return 1
    return 11 - resto


def _dv_arrecadacao(numero: str, ident: str) -> int:
    return _mod10(numero) if ident in "67" else _mod11_arrecadacao(numero)


def _barras_do_bancario(linha: str) -> str:
    """47 dígitos da linha → 44 do código de barras, conferindo os DV dos campos."""
    c1, c2, c3 = linha[0:10], linha[10:21], linha[21:32]
    for campo in (c1, c2, c3):
        if _mod10(campo[:-1]) != int(campo[-1]):
            raise DespesaError("A linha digitável do boleto tem um dígito errado "
                               "(confira a digitação).")
    return linha[0:4] + linha[32] + linha[33:47] + c1[4:9] + c2[0:10] + c3[0:10]


def _barras_da_arrecadacao(linha: str) -> str:
    ident = linha[2]
    blocos = [linha[i:i + 12] for i in range(0, 48, 12)]
    for b in blocos:
        if _dv_arrecadacao(b[:11], ident) != int(b[11]):
            raise DespesaError("O código da conta/guia tem um dígito errado "
                               "(confira a digitação).")
    return "".join(b[:11] for b in blocos)


def ler_codigo_de_barras(texto: Any) -> dict:
    """O que a linha digitável (ou o código de barras) diz. Só calcula.

    Devolve `tipo` (BOLETO ou ARRECADACAO), `barras` (44 dígitos),
    `valor_centavos` (None quando o código não traz valor) e `vencimentos`
    (as datas que o fator pode querer dizer; vazio quando não há fator).
    """
    d = digitos(texto)
    if len(d) == 48 and d[0] == "8":
        barras = _barras_da_arrecadacao(d)
    elif len(d) == 47:
        barras = _barras_do_bancario(d)
    elif len(d) == 44:
        barras = d
    else:
        raise DespesaError("O código de pagamento tem de ter 47 dígitos (boleto), 48 "
                           "(conta, guia ou tributo) ou 44 (código de barras lido).")
    if barras[0] == "8":
        ident = barras[2]
        if ident not in "6789":
            raise DespesaError("Código de arrecadação com identificador de valor desconhecido.")
        if _dv_arrecadacao(barras[:3] + barras[4:], ident) != int(barras[3]):
            raise DespesaError("O código da conta/guia não confere (dígito verificador geral).")
        valor = int(barras[4:15]) if ident in "68" else None
        return {"tipo": ARRECADACAO, "barras": barras, "valor_centavos": valor or None,
                "vencimentos": []}
    if _mod11_bancario(barras[:4] + barras[5:]) != int(barras[4]):
        raise DespesaError("O código do boleto não confere (dígito verificador geral).")
    fator, valor = int(barras[5:9]), int(barras[9:19])
    vencimentos = []
    if fator >= 1000:
        vencimentos = sorted({_BASE_FATOR + timedelta(days=fator),
                              _BASE_FATOR_NOVA + timedelta(days=fator)})
    return {"tipo": BOLETO, "barras": barras, "valor_centavos": valor or None,
            "vencimentos": [v.isoformat() for v in vencimentos]}


# ------------------------------------------------------------ o Pix copia e cola

def _crc16(dados: bytes) -> str:
    """CRC16-CCITT (0x1021, início 0xFFFF): o do padrão EMV do Pix (BR Code)."""
    crc = 0xFFFF
    for byte in dados:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return f"{crc:04X}"


def _tlv(texto: str) -> dict[str, str]:
    campos, i = {}, 0
    while i + 4 <= len(texto):
        tag, tam = texto[i:i + 2], texto[i + 2:i + 4]
        if not tam.isdigit():
            raise DespesaError("O Pix copia e cola está corrompido.")
        n = int(tam)
        campos[tag] = texto[i + 4:i + 4 + n]
        i += 4 + n
    if i != len(texto):
        raise DespesaError("O Pix copia e cola está corrompido.")
    return campos


def ler_pix_copia_e_cola(texto: Any) -> dict:
    """Confere o CRC e devolve `valor_centavos` (None se em aberto), nome e cidade."""
    payload = str(texto or "").strip()
    if len(payload) < 30 or not payload.startswith("000201"):
        raise DespesaError("Isto não parece um Pix copia e cola (deve começar por 000201).")
    corpo, crc = payload[:-4], payload[-4:].upper()
    if not corpo.endswith("6304") or _crc16(corpo.encode("utf-8")) != crc:
        raise DespesaError("O Pix copia e cola não confere (CRC): copie de novo, inteiro.")
    campos = _tlv(payload)
    conta = _tlv(campos.get("26", "")) if campos.get("26") else {}
    if conta.get("00", "").lower() != "br.gov.bcb.pix":
        raise DespesaError("O copia e cola não é de um Pix.")
    valor = None
    if campos.get("54"):
        try:
            valor = round(float(campos["54"]) * 100)
        except ValueError as erro:
            raise DespesaError("O valor dentro do Pix copia e cola está ilegível.") from erro
    return {"valor_centavos": valor, "nome": campos.get("59", ""),
            "cidade": campos.get("60", ""), "chave": conta.get("01", ""),
            "dinamico": bool(conta.get("25"))}


# ----------------------------------------------------------- a configuração

def configuracao(con) -> dict[str, str]:
    """O que está gravado, sobre o padrão. Só LÊ."""
    gravado = {r["key"]: r["value"] for r in banco(con).ler(
        "SELECT key, value FROM settings WHERE key = ANY(%s) ORDER BY key", (list(PADRAO),))}
    return {k: (gravado.get(k) if gravado.get(k) is not None else v) for k, v in PADRAO.items()}


def tetos(cfg: Mapping[str, str]) -> dict[str, int]:
    return {"pagamento": centavos_da_tela(cfg.get("despesas_teto_por_pagamento") or "0"),
            "dia": centavos_da_tela(cfg.get("despesas_teto_por_dia") or "0"),
            "guia": centavos_da_tela(cfg.get("despesas_teto_guia") or "0")}


def gravar_configuracao(con, valores: Mapping[str, Any]) -> dict[str, tuple[str, str]]:
    """Grava a configuração (só ADMIN, na rota). ESCREVE. Devolve o que mudou."""
    novo = {k: _texto(valores.get(k, PADRAO[k]), 40) for k in PADRAO}
    for chave in ("despesas_pagamento_ligado", "despesas_regra_guias_ligada"):
        novo[chave] = "1" if str(valores.get(chave) or "") in ("1", "on") else "0"
    if novo["despesas_ambiente"] not in AMBIENTES:
        raise DespesaError("Ambiente desconhecido.")
    for chave in ("despesas_teto_por_pagamento", "despesas_teto_por_dia", "despesas_teto_guia"):
        if centavos_da_tela(novo[chave]) <= 0:
            raise DespesaError(f"{ROTULOS[chave]}: informe um valor maior que zero.")
        novo[chave] = reais(centavos_da_tela(novo[chave]))
    bd = banco(con)
    antes = configuracao(bd)
    for chave, valor in novo.items():
        bd.escrever("INSERT INTO settings (key, value) VALUES (%s, %s) "
                    "ON CONFLICT (key) DO UPDATE SET value = excluded.value", (chave, valor))
    return {k: (antes[k], v) for k, v in novo.items() if antes[k] != v}


# ----------------------------------------------------------------- o rastro

def _evento(bd, despesa_id: int, operacao: str, resultado: str, mensagem: str,
            usuario: str, quando: str) -> None:
    bd.escrever(
        """INSERT INTO dp_eventos (despesa_id, quando, operacao, resultado, mensagem, usuario)
           VALUES (%s, %s, %s, %s, %s, %s)""",
        (int(despesa_id), quando, operacao, resultado, _texto(mensagem, 1000), usuario or ""))


def despesa(con, despesa_id: int) -> dict | None:
    return banco(con).um("SELECT * FROM dp_despesas WHERE id = %s", (int(despesa_id),))


def eventos(con, despesa_id: int) -> list[dict]:
    return banco(con).ler("SELECT * FROM dp_eventos WHERE despesa_id = %s ORDER BY id",
                          (int(despesa_id),))


# ---------------------------------------------------------------- cadastrar

def conferir_pagamento(forma: str, codigo: Any, valor_centavos: int,
                       vencimento: str) -> dict:
    """O código de pagamento lido e conferido contra o valor e o vencimento. Só calcula."""
    if forma == MANUAL:
        return {"codigo": "", "barras": "", "avisos": []}
    if forma in (BOLETO, ARRECADACAO):
        lido = ler_codigo_de_barras(codigo)
        if lido["tipo"] != forma:
            raise DespesaError(f"O código informado é de {FORMAS[lido['tipo']].lower()}, "
                               f"e não de {FORMAS[forma].lower()}.")
        if lido["valor_centavos"] is not None and lido["valor_centavos"] != valor_centavos:
            raise DespesaError(
                f"O código de pagamento diz R$ {reais(lido['valor_centavos'])} e a despesa "
                f"diz R$ {reais(valor_centavos)}. Confira qual dos dois está certo.")
        if lido["vencimentos"] and vencimento not in lido["vencimentos"]:
            raise DespesaError(
                "O vencimento informado não bate com o que o boleto diz "
                f"({' ou '.join(_br(v) for v in lido['vencimentos'])}).")
        return {"codigo": digitos(codigo), "barras": lido["barras"], "avisos": []}
    if forma == PIX_COPIA_E_COLA:
        lido = ler_pix_copia_e_cola(codigo)
        if lido["valor_centavos"] is not None and lido["valor_centavos"] != valor_centavos:
            raise DespesaError(
                f"O Pix diz R$ {reais(lido['valor_centavos'])} e a despesa diz "
                f"R$ {reais(valor_centavos)}.")
        return {"codigo": str(codigo).strip(), "barras": "", "avisos": [], "pix": lido}
    if forma == PIX_CHAVE:
        chave = _texto(codigo, 77)
        if not chave:
            raise DespesaError("Informe a chave Pix do favorecido.")
        return {"codigo": chave, "barras": "", "avisos": []}
    raise DespesaError("Forma de pagamento desconhecida.")


def _br(dia: str) -> str:
    try:
        return date.fromisoformat(dia).strftime("%d/%m/%Y")
    except ValueError:
        return dia


def cadastrar(con, *, agora: datetime, por: str, origem: str, chave_origem: str | None,
              beneficiario_nome: Any, beneficiario_documento: Any, valor_centavos: int,
              vencimento: Any, forma: str, codigo: Any, descricao: Any, categoria: str,
              documento_especie: Any, documento_numero: Any = "",
              valor_esperado_centavos: int | None = None,
              anexo: tuple[str, bytes] | None = None, pasta_anexos: Path | None = None,
              usuario_id: int | None = None) -> int:
    """Cadastra a despesa. ESCREVE. Devolve o id. Nunca paga.

    Idempotente por (origem, chave_origem): a mesma guia cadastrada duas
    vezes devolve o id da primeira, sem mexer nela.

    Nasce AGUARDANDO a autorização do oficial — salvo a regra das guias
    (docstring do módulo), que só vale para a origem do robô do Portal do Selo.
    """
    bd = banco(con)
    origem = _texto(origem, 60) or "MANUAL"
    chave_origem = _texto(chave_origem, 120) or None
    if chave_origem:
        ja = bd.um("SELECT id FROM dp_despesas WHERE origem = %s AND chave_origem = %s",
                   (origem, chave_origem))
        if ja:
            return int(ja["id"])
    if categoria not in CATEGORIAS:
        raise DespesaError("Escolha a categoria da despesa.")
    natureza = CATEGORIAS[categoria][1]
    descricao = _texto(descricao)
    if len(descricao) < MINIMO_DA_DESCRICAO:
        raise DespesaError("Descreva a despesa em detalhe (art. 190, II, b do CN-MA): o que "
                           "é e a que se refere.")
    nome = _texto(beneficiario_nome, 150)
    if not nome:
        raise DespesaError("Informe o favorecido (quem recebe o pagamento).")
    documento = digitos(beneficiario_documento)
    if documento and cpf_cnpj.documento_valido(documento) is not True:
        raise DespesaError("O CPF/CNPJ do favorecido não confere.")
    valor = int(valor_centavos)
    if valor <= 0:
        raise DespesaError("Informe um valor maior que zero.")
    vencimento = _data(vencimento, "O vencimento")
    especie = _texto(documento_especie, 80)
    if not especie:
        raise DespesaError("Informe a espécie do documento que comprova a despesa (nota "
                           "fiscal, recibo, guia, boleto…) — art. 190, II, c do CN-MA.")
    if forma not in FORMAS:
        raise DespesaError("Escolha a forma de pagamento.")
    lido = conferir_pagamento(forma, codigo, valor, vencimento)
    divergencia = ""
    if valor_esperado_centavos is not None and int(valor_esperado_centavos) != valor:
        divergencia = (f"O sistema calculou R$ {reais(int(valor_esperado_centavos))} e a "
                       f"guia traz R$ {reais(valor)}.")
    quando = _carimbo(agora)
    cfg = configuracao(bd)
    regra = ""
    if (origem == ORIGEM_PORTAL_SELO and natureza == REPASSE
            and cfg.get("despesas_regra_guias_ligada") == "1"
            and valor_esperado_centavos is not None and not divergencia
            and valor <= tetos(cfg)["guia"]):
        regra = (f"Regra das guias: valor conferido com o calculado dos selos e dentro do "
                 f"teto de R$ {reais(tetos(cfg)['guia'])}.")
    situacao = AUTORIZADA if regra else AGUARDANDO
    novo = bd.escrever(
        """INSERT INTO dp_despesas (situacao, natureza, categoria, descricao, beneficiario_nome,
               beneficiario_documento, valor, vencimento, forma, codigo, codigo_barras,
               documento_especie, documento_numero, origem, chave_origem, valor_esperado,
               divergencia, cadastrada_em, cadastrada_por, autorizada_em, autorizada_por,
               autorizada_pela_regra)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                   %s, %s, %s, %s) RETURNING id""",
        (situacao, natureza, categoria, descricao, nome, documento, valor, vencimento, forma,
         lido["codigo"], lido["barras"], especie, _texto(documento_numero, 80), origem,
         chave_origem, valor_esperado_centavos, divergencia, quando, _texto(por, 120) or "?",
         quando if regra else None, "regra das guias" if regra else None, regra))
    despesa_id = int(novo[0]["id"])
    _evento(bd, despesa_id, "CADASTRAR", "ok",
            f"{CATEGORIAS[categoria][0]} — R$ {reais(valor)}"
            + (f" — {divergencia}" if divergencia else ""), por, quando)
    if regra:
        _evento(bd, despesa_id, "AUTORIZAR", "ok", regra, "regra das guias", quando)
    if anexo and anexo[1]:
        guardar_anexo(con, despesa_id, nome_arquivo=anexo[0], conteudo=anexo[1],
                      pasta=pasta_anexos, usuario_id=usuario_id, agora=quando)
    return despesa_id


def guardar_anexo(con, despesa_id: int, *, nome_arquivo: str, conteudo: bytes,
                  pasta: Path | None, usuario_id: int | None, agora: str) -> int:
    """O documento da despesa (nota, guia, boleto, recibo), em `attachments`. ESCREVE."""
    if pasta is None:
        raise DespesaError("Não há pasta de arquivos configurada para guardar o documento.")
    nome_arquivo = Path(nome_arquivo or "").name
    if not nome_arquivo.lower().endswith(EXTENSOES):
        raise DespesaError("Documento em PDF, imagem (JPG, PNG) ou XML.")
    sha = hashlib.sha256(conteudo).hexdigest()
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"despesa_{int(despesa_id)}_{sha[:10]}{Path(nome_arquivo).suffix.lower()}"
    destino.write_bytes(conteudo)
    novo = banco(con).escrever(
        "INSERT INTO attachments(entity_type, entity_id, original_name, stored_name, "
        "stored_path, sha256, size_bytes, description, uploaded_by, uploaded_at) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        (ENTIDADE_DO_ANEXO, int(despesa_id), nome_arquivo, destino.name, str(destino), sha,
         len(conteudo), f"Documento da despesa {int(despesa_id)}", usuario_id, agora))
    return int(novo[0]["id"])


def anexos(con, despesa_id: int) -> list[dict]:
    return banco(con).ler(
        "SELECT * FROM attachments WHERE entity_type = %s AND entity_id = %s ORDER BY id",
        (ENTIDADE_DO_ANEXO, int(despesa_id)))


# ------------------------------------------------- autorizar, cancelar, corrigir

def _prender(bd, despesa_id: int) -> dict:
    bd._escrita()
    linha = bd.um("SELECT * FROM dp_despesas WHERE id = %s FOR UPDATE", (int(despesa_id),))
    if not linha:
        raise DespesaError("Despesa não encontrada.")
    return linha


def autorizar(con, despesa_id: int, *, agora: datetime, por: str, papel: str,
              acima_do_teto: bool = False, motivo_divergencia: Any = "") -> dict:
    """Autoriza o pagamento. Só ADMIN (decisão do oficial, 24/10/2026). ESCREVE."""
    if papel != "ADMIN":
        raise DespesaError("Só o oficial (ADMIN) autoriza despesa.")
    bd = banco(con)
    d = _prender(bd, despesa_id)
    if d["situacao"] != AGUARDANDO:
        raise DespesaError(f"Esta despesa está «{SITUACOES[d['situacao']]}» e não espera "
                           f"autorização.")
    if d["forma"] == MANUAL:
        raise DespesaError("Despesa paga fora do banco não se autoriza: registre o pagamento.")
    motivo = _texto(motivo_divergencia, 500)
    if d["divergencia"] and len(motivo) < MINIMO_DA_DESCRICAO:
        raise DespesaError(f"Há divergência de valor ({d['divergencia']}). Diga por que o "
                           f"pagamento está certo assim.")
    cfg = configuracao(bd)
    if int(d["valor"]) > tetos(cfg)["pagamento"] and not acima_do_teto:
        raise DespesaError(
            f"R$ {reais(int(d['valor']))} passa do teto por pagamento "
            f"(R$ {reais(tetos(cfg)['pagamento'])}). Marque «autorizo acima do teto» "
            f"para este pagamento, ou mude o teto na configuração.")
    quando = _carimbo(agora)
    bd.escrever(
        """UPDATE dp_despesas SET situacao = 'AUTORIZADA', autorizada_em = %s,
                  autorizada_por = %s, acima_do_teto = %s WHERE id = %s""",
        (quando, _texto(por, 120), 1 if acima_do_teto else 0, int(despesa_id)))
    _evento(bd, despesa_id, "AUTORIZAR", "ok",
            ("acima do teto; " if acima_do_teto else "") + (motivo or ""), por, quando)
    return despesa(bd, despesa_id)


def devolver(con, despesa_id: int, *, agora: datetime, por: str, papel: str,
             motivo: Any) -> dict:
    """Devolve à autorização (desautoriza, ou recoloca a que FALHOU). ESCREVE."""
    if papel != "ADMIN":
        raise DespesaError("Só o oficial (ADMIN) mexe na autorização.")
    motivo = _texto(motivo, 500)
    if len(motivo) < MINIMO_DA_DESCRICAO:
        raise DespesaError("Diga o motivo.")
    bd = banco(con)
    d = _prender(bd, despesa_id)
    if d["situacao"] not in (AUTORIZADA, FALHOU):
        raise DespesaError("Só volta à autorização a despesa autorizada e ainda não enviada, "
                           "ou a que o banco não pagou.")
    quando = _carimbo(agora)
    bd.escrever("""UPDATE dp_despesas SET situacao = 'AGUARDANDO_AUTORIZACAO',
                          autorizada_em = NULL, autorizada_por = NULL,
                          autorizada_pela_regra = '', acima_do_teto = 0 WHERE id = %s""",
                (int(despesa_id),))
    _evento(bd, despesa_id, "DEVOLVER", "ok", motivo, por, quando)
    return despesa(bd, despesa_id)


def cancelar(con, despesa_id: int, *, agora: datetime, por: str, papel: str,
             motivo: Any) -> dict:
    """Cancela a despesa que ainda não foi ao banco. A linha fica. ESCREVE."""
    if papel not in ("ADMIN", "MANAGER"):
        raise DespesaError("Só o oficial ou o gerente cancelam despesa.")
    motivo = _texto(motivo, 500)
    if len(motivo) < MINIMO_DA_DESCRICAO:
        raise DespesaError("Diga por que a despesa está sendo cancelada.")
    bd = banco(con)
    d = _prender(bd, despesa_id)
    if d["situacao"] not in (AGUARDANDO, AUTORIZADA, FALHOU):
        raise DespesaError("Despesa enviada ao banco não se cancela aqui: cancele o "
                           "agendamento no banco e registre o que aconteceu.")
    quando = _carimbo(agora)
    bd.escrever("""UPDATE dp_despesas SET situacao = 'CANCELADA', cancelada_em = %s,
                          cancelada_por = %s, motivo_cancelamento = %s WHERE id = %s""",
                (quando, _texto(por, 120), motivo, int(despesa_id)))
    _evento(bd, despesa_id, "CANCELAR", "ok", motivo, por, quando)
    return despesa(bd, despesa_id)


def registrar_pago_fora(con, despesa_id: int, *, agora: datetime, hoje: str, por: str,
                        papel: str, data_pagamento: Any) -> dict:
    """A despesa paga sem o banco (dinheiro, outra conta). ESCREVE, e lança no Livro Diário."""
    import livro_diario as LD
    if papel != "ADMIN":
        raise DespesaError("Só o oficial (ADMIN) registra pagamento feito fora do banco.")
    bd = banco(con)
    d = _prender(bd, despesa_id)
    if d["situacao"] not in (AGUARDANDO, AUTORIZADA, FALHOU):
        raise DespesaError("Esta despesa já foi ao banco ou foi encerrada.")
    dia = _data(data_pagamento, "A data do pagamento")
    quando = _carimbo(agora)
    ld_id = None
    if d["natureza"] == DESPESA:
        try:
            ld_id = LD.lancar_despesa(
                con, hoje=hoje, agora=quando, por=por, data=dia,
                descricao=f"{d['descricao']} — {d['beneficiario_nome']}",
                documento_especie=d["documento_especie"], valor=reais(int(d["valor"])),
                documento_numero=d["documento_numero"])
        except LD.DiarioError as erro:
            raise DespesaError(str(erro)) from erro
    bd.escrever("""UPDATE dp_despesas SET situacao = 'PAGA_FORA', paga_em = %s,
                          ld_despesa_id = %s WHERE id = %s""", (dia, ld_id, int(despesa_id)))
    _evento(bd, despesa_id, "PAGO_FORA", "ok", f"pago em {_br(dia)}", por, quando)
    return despesa(bd, despesa_id)


# --------------------------------------------------------------- as listas

def listar(con, *, situacao: str | None = None, mes: str | None = None,
           limite: int = 300, cadastrada_por: str | None = None) -> list[dict]:
    """As despesas, as mais novas primeiro. Só LÊ.

    `cadastrada_por` é a lista de quem só cadastra (o perfil USER, 28/10/2026):
    ele vê as que cadastrou, e não a folha de pagamento da casa.
    """
    filtros, parametros = [], []
    if cadastrada_por is not None:
        filtros.append("cadastrada_por = %s")
        parametros.append(cadastrada_por)
    if situacao:
        filtros.append("situacao = %s")
        parametros.append(situacao)
    if mes:
        inicio, fim = _limites_do_mes(mes)
        filtros.append("vencimento >= %s AND vencimento < %s")
        parametros += [inicio, fim]
    onde = (" WHERE " + " AND ".join(filtros)) if filtros else ""
    return banco(con).ler(f"SELECT * FROM dp_despesas{onde} ORDER BY id DESC LIMIT %s",
                          (*parametros, int(limite)))


def _limites_do_mes(mes: str) -> tuple[str, str]:
    try:
        inicio = datetime.strptime(mes, "%Y-%m").date()
    except ValueError as erro:
        raise DespesaError("O mês é AAAA-MM.") from erro
    fim = date(inicio.year + (inicio.month == 12), inicio.month % 12 + 1, 1)
    return inicio.isoformat(), fim.isoformat()


def contagem(con, *, cadastrada_por: str | None = None) -> dict[str, int]:
    if cadastrada_por is not None:
        return {r["situacao"]: int(r["n"]) for r in banco(con).ler(
            "SELECT situacao, count(*) AS n FROM dp_despesas WHERE cadastrada_por = %s "
            "GROUP BY situacao", (cadastrada_por,))}
    return {r["situacao"]: int(r["n"]) for r in banco(con).ler(
        "SELECT situacao, count(*) AS n FROM dp_despesas GROUP BY situacao")}


def pagas_hoje(con, hoje: str) -> int:
    """O total já enviado ao banco no dia (para o teto por dia). Só LÊ."""
    inicio = date.fromisoformat(hoje)
    fim = inicio + timedelta(days=1)
    return int(banco(con).valor(
        """SELECT COALESCE(sum(valor), 0) AS t FROM dp_despesas
            WHERE enviada_em >= %s AND enviada_em < %s
              AND situacao IN ('ENVIADA', 'PAGA', 'CONCILIADA')""",
        (inicio.isoformat(), fim.isoformat())) or 0)


# ------------------------------------------------- o relatório e o SIAFERJ

def relatorio_do_mes(con, mes: str) -> dict:
    """O que se pagou no mês (pela data do pagamento), por natureza e categoria. Só LÊ.

    Entram as pagas e conferidas no extrato e as pagas fora do banco. A paga
    pelo banco e ainda não conferida aparece à parte: o débito pode não ter
    acontecido.
    """
    inicio, fim = _limites_do_mes(mes)
    linhas = banco(con).ler(
        """SELECT * FROM dp_despesas
            WHERE situacao IN ('CONCILIADA', 'PAGA_FORA') AND paga_em >= %s AND paga_em < %s
            ORDER BY paga_em, id""", (inicio, fim))
    a_conferir = banco(con).ler(
        """SELECT * FROM dp_despesas WHERE situacao IN ('ENVIADA', 'PAGA')
            ORDER BY vencimento, id""")
    por_categoria: dict[str, int] = {}
    total = {DESPESA: 0, REPASSE: 0}
    for d in linhas:
        por_categoria[d["categoria"]] = por_categoria.get(d["categoria"], 0) + int(d["valor"])
        total[d["natureza"]] += int(d["valor"])
    return {"mes": mes, "linhas": linhas, "a_conferir": a_conferir,
            "por_categoria": sorted(por_categoria.items(), key=lambda x: -x[1]),
            "total": total}


#: O cabeçalho do relatório em CSV, para a contabilidade.
CABECALHO_DO_CSV = ("data_pagamento", "natureza", "categoria", "descricao", "favorecido",
                    "documento_favorecido", "especie_documento", "numero_documento",
                    "valor", "forma", "situacao")


def linhas_do_csv(rel: Mapping[str, Any]) -> list[tuple]:
    """As linhas do relatório em CSV (vírgula decimal). A tela entrega pelo
    `csv_seguro`, que põe tudo entre aspas e desarma fórmula — o «;» dentro do
    campo já não precisa virar vírgula."""
    return [(d["paga_em"], d["natureza"], CATEGORIAS.get(d["categoria"], ("?",))[0],
             d["descricao"], d["beneficiario_nome"], d["beneficiario_documento"],
             d["documento_especie"], d["documento_numero"],
             reais(int(d["valor"])).replace(".", ""), d["forma"], d["situacao"])
            for d in rel["linhas"]]


def lancamentos_para_o_siaferj(rel: Mapping[str, Any]) -> list[dict]:
    """As despesas do mês nas colunas do art. 190, II, prontas para o SIAFERJ-WEB.

    O SIAFERJ-WEB (TJMA) não publica API nem layout de importação (pesquisado
    em 24/10/2026): o lançamento é na tela, até o dia 10 (Res.-GP 74/2023,
    art. 2º). Esta lista é o que se digita lá, uma linha por despesa, na
    ordem do pagamento. O repasse de fundo não entra: não é despesa.
    """
    return [{"data": _br(d["paga_em"]),
             "descricao": f"{d['descricao']} — {d['beneficiario_nome']}",
             "documento": " nº ".join(x for x in (d["documento_especie"],
                                                  d["documento_numero"]) if x),
             "valor": reais(int(d["valor"]))}
            for d in rel["linhas"] if d["natureza"] == DESPESA]

