"""Os papéis do CAIXA têm o que a lei e as normas exigem? — a matriz do LT06.

O PEDIDO DO OFICIAL (20/10/2026)
    «os modelos têm de abarcar o que a LEI e as NORMAS exigem». A matriz desta
    atribuição está em `docs/REQUISITOS_LEGAIS.md`, seção «Caixa e protocolo
    geral (LT06)»; este arquivo é ela em forma de teste.

DOIS LADOS DE CADA ELEMENTO
    1. O PAPEL MONTADO com um contexto COMPLETO (serventia, pessoa e valores de
       ensaio — nada de pessoa real) traz o rótulo E o valor do elemento.
       Contexto completo é a condição: com ele, elemento que não sai é defeito
       do modelo, e não falta de dado.
    2. O PADRÃO DA CASA (`modelos_padrao/caixa/*.txt`, o texto de fábrica que
       a subida carrega na base) tem o marcador do campo. Elemento que o
       modelo não tem é DEFEITO DO MODELO — consertado no padrão, com o ouro,
       ou marcado `xfail(strict=True)` com o artigo.

    O Livro de Controle de Depósito Prévio não é modelo editável: é a tela do
    livro (`livro_deposito_previo` + o template). Ele entra na matriz pelo
    mesmo caminho — o livro montado tem a coluna de cada inciso do art. 198.

FONTES, na ordem de prevalência: Lei 6.015/1973 (LRP), Lei 8.935/1994, o
Código Nacional de Normas (Prov. CNJ 149/2023) e o Código de
Normas Extrajudicial do MA (Prov. COGEX 28/2026), os dois em
`migracao-pg/referencia/`.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest
from jinja2.sandbox import SandboxedEnvironment

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

PASTA = RAIZ / "modelos_padrao" / "caixa"

SV = {
    "unit_name": "Ofício Único de Cidade Exemplo/MA",
    "serventia_titulo": "Oficial e Tabelião",
    "serventia_titular": "Mario Exemplo dos Santos",
    "serventia_cnpj": "00.000.042/0001-22",
    "ri_cns": "000000",
    "serventia_telefone": "(99) 3000-0000",
    "endereco_completo": "Rua de Exemplo, 100, CEP 65000-000, Cidade Exemplo-MA",
    "cidade_uf": "Cidade Exemplo/MA",
}
ITENS = [
    {"codigo_ato": "13.18", "descricao": "Autenticação de cópia, por página",
     "quantidade": 2, "base_calculo": None, "emolumentos": "11,00",
     "valor_total": "12,42", "quitado": 1},
    {"codigo_ato": "14.5.1", "descricao": "Certidão em breve relato",
     "quantidade": 1, "base_calculo": None, "emolumentos": "40,00",
     "valor_total": "45,36", "quitado": 0},
]
FUNDOS = {"emolumentos": "51,00", "ferc": "2,04", "fadep": "1,54", "femp": "1,60",
          "ferrfis": "1,60"}
PROTOCOLO = {
    "numero": "2026.10.77", "interessado": "CLIENTE DE EXEMPLO DA SILVA",
    "atribuicao": "RCPN", "assunto": "Certidão e cópias autenticadas",
    "documento_descricao": "Requerimento assinado", "documento_tipo": "RG",
    "documento_numero": "000000", "hora": "09:15", "previsao_entrega": "2026-10-27",
    "observacao": "Entregar ao próprio interessado", "tipo": "ORCAMENTO",
}


def _contexto(chave: str) -> dict:
    """O contexto COMPLETO de cada papel — o mesmo nome de variável da rota."""
    comum = {"sv": SV, "emitido_por": "ELISA EXEMPLO ESCREVENTE", "funcao": "Escrevente",
             "documento": "***.982.247-**", "telefone": "(**) *****-7777"}
    if chave == "CAIXA_RECIBO":
        return comum | {
            "r": {"numero": 12, "ano": 2026, "pagador": PROTOCOLO["interessado"],
                  "valor_total": "57,78", "valor_extenso":
                  "cinquenta e sete reais e setenta e oito centavos",
                  "protocolo_numero": PROTOCOLO["numero"], "forma_pagamento": "PIX",
                  "observacao": None, "hash_recibo": "ab12cd34ef56ab78" + "0" * 48},
            "itens": ITENS, "fundos": FUNDOS, "tem_fundos": True,
            "lancamento": "41/2026", "observacao": "", "data_extenso": "20/10/2026",
            "agora": "20/10/2026 10:00"}
    if chave == "CAIXA_RECEPCAO":
        return comum | {
            "p": PROTOCOLO, "itens": ITENS,
            "soma": {"total": "57,78", "total_centavos": 5778},
            "pendente": {"total": "45,36", "total_centavos": 4536},
            "email": "c***@exemplo.invalid", "observacao": PROTOCOLO["observacao"],
            "data": "20/10/2026", "previsao": "27/10/2026"}
    if chave == "CAIXA_ORCAMENTO":
        return comum | {
            "p": PROTOCOLO, "itens": ITENS,
            "soma": {"total": "57,78", **FUNDOS},
            "extenso": "cinquenta e sete reais e setenta e oito centavos",
            "orcamento": True, "vigencia": "99001", "data": "20/10/2026",
            "email": "c***@exemplo.invalid",
            "aviso": (PASTA / "CAIXA_ORCAMENTO__aviso.txt").read_text(encoding="utf-8")}
    raise KeyError(chave)


def _padrao(chave: str) -> str:
    return (PASTA / f"{chave}.txt").read_text(encoding="utf-8")


def _montar(chave: str) -> str:
    html = SandboxedEnvironment(autoescape=False).from_string(_padrao(chave)).render(
        **_contexto(chave))
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


# A MATRIZ. Cada elemento: (papel, elemento, artigo, o que o papel montado diz,
# o marcador que o padrão tem de ter).
MATRIZ = [
    # ---------------------------------------------------------- o recibo
    ("CAIXA_RECIBO", "identificação da serventia (nome, CNS, CNPJ, endereço)",
     "CN-MA art. 87, IX; art. 12, II (prática da casa: o CN-MA não lista)",
     [SV["unit_name"], "CNS 000000", f"CNPJ {SV['serventia_cnpj']}", SV["endereco_completo"]],
     ["sv.unit_name", "sv.ri_cns", "sv.serventia_cnpj", "sv.endereco_completo"]),
    ("CAIXA_RECIBO", "o titular da serventia",
     "Lei 8.935/1994, arts. 20 e 21 (o titular responde pelo serviço)",
     [f"{SV['serventia_titulo']}: {SV['serventia_titular']}"],
     ["sv.serventia_titular"]),
    ("CAIXA_RECIBO", "número do recibo e exercício", "CN-MA art. 115, II (número e data do recibo)",
     ["RECIBO Nº 12/2026"], ["r.numero", "r.ano"]),
    ("CAIXA_RECIBO", "quem pagou e o documento", "CN-MA art. 87, IX",
     [f"Recebemos de: {PROTOCOLO['interessado']}", "CPF/CNPJ sob o nº ***.982.247-**"],
     ["r.pagador", "documento"]),
    ("CAIXA_RECIBO", "valor recebido, em algarismo e por extenso",
     "CN-MA art. 87, IX e XVI; LRP art. 14, parágrafo único",
     ["R$ 57,78 (cinquenta e sete reais e setenta e oito centavos)"],
     ["r.valor_total", "r.valor_extenso"]),
    ("CAIXA_RECIBO", "discriminação por ato: código da tabela, ato, emolumentos e total",
     "LRP art. 14, parágrafo único; CN-MA art. 87, XVI; art. 952",
     ["Autenticação de cópia, por página 13.18 11,00 12,42",
      "Certidão em breve relato 14.5.1 40,00 45,36"],
     ["i.descricao", "i.codigo_ato", "i.emolumentos", "i.valor_total"]),
    ("CAIXA_RECIBO", "os fundos e acréscimos legais separados dos emolumentos",
     "CN-MA art. 12, IV; art. 881, § 1º (FERJ/FERC, FEMP, FADEP, FERRFIS)",
     ["emolumentos R$ 51,00", "FERC R$ 2,04", "FADEP R$ 1,54", "FEMP R$ 1,60",
      "FERRFIS R$ 1,60"],
     ["fundos.emolumentos", "fundos.ferc", "fundos.fadep", "fundos.femp", "fundos.ferrfis"]),
    ("CAIXA_RECIBO", "o protocolo a que se refere", "CN-MA art. 33",
     [f"Referente ao protocolo nº {PROTOCOLO['numero']}"], ["r.protocolo_numero"]),
    ("CAIXA_RECIBO", "forma de pagamento", "CN-MA art. 927, parágrafo único",
     ["Forma de pagamento: PIX"], ["r.forma_pagamento"]),
    ("CAIXA_RECIBO", "local e data", "CN-MA art. 115, II",
     ["Cidade Exemplo/MA, 20/10/2026"], ["sv.cidade_uf", "data_extenso"]),
    ("CAIXA_RECIBO", "quem emitiu, e em que qualidade", "Lei 8.935/1994, art. 20",
     ["ELISA EXEMPLO ESCREVENTE", "Escrevente"], ["emitido_por", "funcao"]),
    ("CAIXA_RECIBO", "conferência da via (impressão digital)", "prática da casa (via reimpressa = a mesma)",
     ["Conferência: ab12cd34ef56ab78"], ["r.hash_recibo"]),
    # ------------------------------------------- o comprovante de recepção
    ("CAIXA_RECEPCAO", "identificação da serventia", "CN-MA art. 33",
     [SV["unit_name"], "CNS 000000"], ["sv.unit_name", "sv.ri_cns"]),
    ("CAIXA_RECEPCAO", "número de ordem do protocolo", "CN-MA art. 33; LRP art. 175, I",
     [f"PROTOCOLO DE RECEPÇÃO Nº {PROTOCOLO['numero']}"], ["p.numero"]),
    ("CAIXA_RECEPCAO", "o apresentante e o documento dele", "LRP art. 175, III",
     [PROTOCOLO["interessado"], "***.982.247-**"], ["p.interessado", "documento"]),
    ("CAIXA_RECEPCAO", "data e hora da recepção", "CN-MA art. 33 (data e hora); LRP art. 175, II",
     ["Recebido em 20/10/2026 às 09:15"], ["data", "p.hora"]),
    ("CAIXA_RECEPCAO", "o que foi apresentado e para quê", "LRP art. 175, IV; CN-MA art. 894",
     ["Certidão e cópias autenticadas", "Requerimento assinado", "RG nº 000000", "RCPN"],
     ["p.assunto", "p.documento_descricao", "p.documento_tipo", "p.atribuicao"]),
    ("CAIXA_RECEPCAO", "previsão de entrega", "CN-MA art. 447, § 4º; art. 974, § 1º",
     ["Previsão de entrega 27/10/2026"], ["previsao"]),
    ("CAIXA_RECEPCAO", "os atos previstos e os valores, e o que falta pagar",
     "LRP art. 14, parágrafo único; CN-MA art. 197",
     ["13.18 Autenticação de cópia, por página 2 12,42 (quitado)", "TOTAL: R$ 57,78",
      "a quitar: R$ 45,36"],
     ["i.codigo_ato", "i.valor_total", "soma.total", "pendente.total"]),
    ("CAIXA_RECEPCAO", "assinatura de quem recebeu e do apresentante", "Lei 8.935/1994, art. 20",
     ["ELISA EXEMPLO ESCREVENTE", "Apresentante"], ["emitido_por"]),
    # ------------------------------------------------------- o orçamento
    ("CAIXA_ORCAMENTO", "o aviso de que é MERO CÁLCULO, e não ato praticado",
     "LRP art. 12, parágrafo único; CN-MA art. 450, § 5º",
     ["CÁLCULO DE EMOLUMENTOS Nº 2026.10.77", "MERO CÁLCULO DE EMOLUMENTOS",
      "NÃO representa a prática de ato"], ["aviso", "orcamento"]),
    ("CAIXA_ORCAMENTO", "cada ato com código, base de cálculo e total",
     "CN-MA art. 87, VIII; art. 88, II", ["13.18 Autenticação de cópia, por página 2 — 12,42"],
     ["i.codigo_ato", "i.base_calculo", "i.valor_total"]),
    ("CAIXA_ORCAMENTO", "a composição: emolumentos e cada fundo",
     "CN-MA art. 881, § 1º; CNN art. 228-U, IV",
     ["emolumentos R$ 51,00", "FERC R$ 2,04", "FADEP R$ 1,54", "FEMP R$ 1,60",
      "FERRFIS R$ 1,60"],
     ["soma.emolumentos", "soma.ferc", "soma.fadep", "soma.femp", "soma.ferrfis"]),
    ("CAIXA_ORCAMENTO", "total em algarismo e por extenso, e a vigência da tabela",
     "CN-MA art. 87, VII e VIII",
     ["TOTAL: R$ 57,78 (cinquenta e sete reais e setenta e oito centavos)",
      "vigência 99001"], ["soma.total", "extenso", "vigencia"]),
]


def _id(linha) -> str:
    return f"{linha[0]}-{re.sub(r'[^a-z]+', '_', linha[1].lower())[:40]}"


LINHAS = [pytest.param(*linha, id=_id(linha)) for linha in MATRIZ]


@pytest.mark.parametrize("papel,elemento,artigo,no_papel,marcadores", LINHAS)
def test_o_papel_montado_traz_o_elemento_exigido(papel, elemento, artigo, no_papel,
                                                 marcadores):
    texto = _montar(papel)
    for trecho in no_papel:
        assert trecho in texto, f"{papel}: falta «{trecho}» ({elemento} — {artigo})"


@pytest.mark.parametrize("papel,elemento,artigo,no_papel,marcadores", LINHAS)
def test_o_padrao_da_casa_tem_o_campo_do_elemento(papel, elemento, artigo, no_papel,
                                                  marcadores):
    corpo = _padrao(papel)
    ficha = json.loads((PASTA / f"{papel}.json").read_text(encoding="utf-8"))
    for marcador in marcadores:
        assert re.search(r"\b" + re.escape(marcador) + r"\b", corpo), \
            f"{papel}: o padrão não tem o campo «{marcador}» ({elemento} — {artigo})"
        assert marcador.split(".")[0] in ficha["campos"] or marcador.startswith("i."), \
            f"{papel}: a ficha não declara «{marcador.split('.')[0]}»"


@pytest.mark.parametrize("papel", sorted({linha[0] for linha in MATRIZ}))
def test_o_papel_completo_nao_tem_marcador_sobrando_nem_none(papel):
    texto = _montar(papel)
    for sobra in ("{{", "}}", "{%", "%}", "None"):
        assert sobra not in texto, f"{papel}: sobrou «{sobra}»"


# ------------------------------------- o Livro de Controle de Depósito Prévio
#
# Não é modelo editável: é a tela do livro. A matriz é a do art. 198 do CN-MA
# — cada inciso tem a sua coluna no papel e o seu dado no livro montado.

ART_198 = [
    ("I", "I — protocolo ou pedido", "protocolo",
     "número do protocolo do título ou do pedido de serviço"),
    ("II", "II — data", "data", "data do depósito"),
    ("III", "III — valor", "valor", "valor depositado"),
    ("IV", "IV — conversão em emolumentos", "conversoes",
     "data da conversão em emolumentos, com a identificação do ato praticado"),
    ("V", "V — devolução", "devolucoes",
     "data da devolução, com a justificativa, quando o ato não for praticado"),
    ("VI", "VI — orçamento", "orcamento",
     "descrição completa do orçamento, inclusive seus acréscimos"),
]


@pytest.fixture
def livro_com_deposito(cg_casa):
    """Um depósito com protocolo e serviço, convertido em parte e devolvido."""
    import caixa_depositos as DEP
    import caixa_protocolo as CXP
    import livro_deposito_previo as LDP
    from bd_nativo import banco
    db = cg_casa["db"]
    with db.transaction() as con:
        bd = banco(con)
        bd.escrever("""INSERT INTO cx_servicos (codigo, codigo_tj, descricao, ativo)
                       VALUES (990103, '16.24.1', 'Certidão negativa de imóvel', 1)""")
        # O PREÇO DO SERVIÇO NA TABELA VIGENTE (LD06). O orçamento do art. 198,
        # VI, é com os acréscimos — e sem o preço da tabela não há orçamento
        # completo a guardar. Vigência e valores de ENSAIO, inventados.
        bd.escrever("""INSERT INTO cx_vigencias (codigo, descricao, vigente, servicos,
                                                 faixas, importado_em)
                       VALUES (99001, 'Vigência de ensaio do LD06', 1, 1, 0,
                               '2026-10-20') ON CONFLICT (codigo) DO NOTHING""")
        bd.escrever("UPDATE cx_vigencias SET vigente = 0 WHERE codigo <> 99001")
        bd.escrever("""INSERT INTO cx_servico_valores (servico, vigencia, emolumentos,
                                                      ferc, fadep, femp, ferrfis, total)
                       VALUES (990103, 99001, '35,00', '1,40', '1,05', '1,12', '1,12',
                               '39,69')""")
        p = CXP.abrir(bd, data_abertura="2026-10-20", agora="2026-10-20T09:00:00",
                      atribuicao="RI", interessado="CLIENTE DE EXEMPLO DA SILVA")
        d = DEP.criar(bd, valor_centavos=10000, depositante="CLIENTE DE EXEMPLO DA SILVA",
                      agora="2026-10-20T09:00:00", protocolo_id=p["protocolo_id"],
                      servico_codigo=990103)
        for acao, detalhes in (("DEPOSITO_PREVIO_USADO",
                                {"usado": "30,00", "protocolo": p["numero"]}),
                               ("DEPOSITO_PREVIO_DEVOLVIDO",
                                {"valor": "70,00", "motivo": "Título devolvido"})):
            bd.escrever("""INSERT INTO audit_logs (ts, action, entity_type, entity_id, details)
                           VALUES ('2026-10-21T10:00:00', %s, 'DEPOSITO', %s, %s)""",
                        (acao, d["id"], json.dumps(detalhes)))
        bd.escrever("UPDATE cx_depositos SET saldo = '0,00', encerrado = 1 WHERE id = %s",
                    (d["id"],))
    with db.connect() as con:
        return LDP.livro(con)["linhas"][0]


@pytest.mark.parametrize("inciso,coluna,chave,o_que", [
    pytest.param(*linha, id=f"art_198_{linha[0]}") for linha in ART_198])
def test_o_livro_de_deposito_previo_tem_a_coluna_de_cada_inciso_do_art_198(
        inciso, coluna, chave, o_que, livro_com_deposito):
    template = (RAIZ / "templates" / "livro_deposito_previo.html").read_text(encoding="utf-8")
    assert f"<th>{coluna}</th>" in template, f"art. 198, {inciso}: falta a coluna"
    assert livro_com_deposito[chave], f"art. 198, {inciso} ({o_que}): o livro veio vazio"


@pytest.mark.parametrize("inciso", ["I", "II", "III", "IV", "V"])
def test_o_deposito_completo_nao_tem_falta_nos_incisos_que_o_sistema_guarda(
        inciso, livro_com_deposito):
    faltas = [f for f in livro_com_deposito["faltas"] if f.startswith(f"{inciso} —")]
    assert not faltas, faltas


def test_o_deposito_guarda_o_orcamento_completo_do_art_198_vi(livro_com_deposito):
    """CN-MA art. 198, VI: o depósito guardava no máximo UM serviço do
    catálogo, e a descrição completa do orçamento, com os acréscimos, não
    ficava em lugar nenhum. Consertado no LD06 (`cx_depositos.orcamento`)."""
    assert not [f for f in livro_com_deposito["faltas"] if f.startswith("VI —")]
    # os acréscimos são os fundos, item a item, e a soma (art. 881, § 1º)
    for trecho in ("16.24.1", "emolumentos R$ 35,00", "FERC R$ 1,40", "FADEP R$ 1,05",
                   "FEMP R$ 1,12", "FERRFIS R$ 1,12", "Total do orçamento: R$ 39,69"):
        assert trecho in livro_com_deposito["orcamento"], trecho
