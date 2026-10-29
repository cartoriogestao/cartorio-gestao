"""
O selo do Protesto conferido ANTES de lavrar, e a situação que pede um ato.

Ordem do oficial, 29/10/2026: «precisamos revisar os processos para nao
permitir que a mao de obra erre». Medido na produção no mesmo dia (só
leitura): cinco atos do Protesto desfeitos por «Selo não emitido», quatro
deles porque não havia item marcado — e o título 9614 ficou PAGO sem
pagamento válido.

O QUE ELES CONFEREM
    - sem item, todo ato que sela é recusado ANTES, com frase de balcão e
      sendo `ValueError` (regra da casa: erro de regra não é HTTP 500);
    - com item, passa; os atos sem selo próprio, o selo digitado à mão e o
      robô (que não pede selo) não são conferidos — é o espelho da rota;
    - a lista de itens só se pede quando o ato vai mesmo selar;
    - a rota usa a MESMA lista de atos sem selo e a MESMA régua de itens que
      o selo usa depois — uma régua só;
    - não há afirmação expressa que vença esta trava (selo isento também sai
      por item);
    - a conferência acha o título cuja situação não tem o ato válido, diz se o
      ato foi desfeito ou se veio assim do acervo, e não escreve nada.

Documentos fictícios só, de `tests/fixtures/anti_vazamento/`.
"""
from __future__ import annotations

import ast
import inspect
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import ato_selado as AS                          # noqa: E402
import protesto_selo_previo as PSELO             # noqa: E402
from bd_nativo import banco as nativo            # noqa: E402
from nucleo_schema import init_nucleo_schema     # noqa: E402
from pt_schema import init_pt_schema             # noqa: E402

AGORA = "2026-10-29T09:00:00"
ATOS_QUE_SELAM = ("INTIMACAO", "PROTESTO", "PAGAMENTO", "DESISTENCIA",
                  "CANCELAMENTO")


# ------------------------------------------------- a recusa antes de lavrar


@pytest.mark.parametrize("ato", ATOS_QUE_SELAM)
def test_sem_item_o_ato_que_sela_e_recusado_antes(ato):
    with pytest.raises(PSELO.SeloSemItemError) as erro:
        PSELO.conferir_antes_de_lavrar(ato, [])
    texto = str(erro.value)
    assert "nada foi gravado" in texto
    assert PSELO.O_ATO[ato] in texto
    assert "Cobrar no caixa" in texto        # diz o que fazer
    # REGRA DA CASA: erro de regra é ValueError, com mensagem pronta — e é da
    # família que as rotas do Protesto já tratam como recusa.
    assert isinstance(erro.value, ValueError)
    assert isinstance(erro.value, AS.AtoError)


@pytest.mark.parametrize("ato", ATOS_QUE_SELAM)
def test_com_item_o_ato_passa(ato):
    PSELO.conferir_antes_de_lavrar(ato, ["17.4"])
    PSELO.conferir_antes_de_lavrar(ato, lambda: ["17.2", "17.4"])


@pytest.mark.parametrize("ato", sorted(PSELO.ATOS_SEM_SELO_PROPRIO))
def test_o_ato_sem_selo_proprio_nao_e_conferido(ato):
    PSELO.conferir_antes_de_lavrar(ato, [])


def test_o_selo_digitado_e_o_robo_nao_sao_conferidos():
    """É o espelho da rota: o selo digitado à mão dispensa o pedido, e o robô
    não pede selo (o ato dele fica pendente). Nenhum dos dois é desfeito
    depois por falta de item — então também não se recusa antes."""
    PSELO.conferir_antes_de_lavrar("PAGAMENTO", [], selo_digitado=True)
    PSELO.conferir_antes_de_lavrar("PAGAMENTO", [], selo_automatico=False)


def test_a_lista_de_itens_so_se_pede_quando_o_ato_sela():
    perguntas = []

    def itens():
        perguntas.append(1)
        return []

    PSELO.conferir_antes_de_lavrar("APONTAMENTO", itens)
    PSELO.conferir_antes_de_lavrar("PAGAMENTO", itens, selo_digitado=True)
    assert perguntas == []
    with pytest.raises(PSELO.SeloSemItemError):
        PSELO.conferir_antes_de_lavrar("PAGAMENTO", itens)
    assert perguntas == [1]


def test_a_certidao_sela_sempre_e_tem_a_frase_dela():
    with pytest.raises(PSELO.SeloSemItemError) as erro:
        PSELO.conferir_antes_de_lavrar("NEGATIVA", [], tabela="pt_certidoes")
    assert str(erro.value).startswith("Certidão NÃO emitida, e nada foi gravado")
    # «Apontamento» não é palavra da certidão: lá não há atos sem selo.
    with pytest.raises(PSELO.SeloSemItemError):
        PSELO.conferir_antes_de_lavrar("APONTAMENTO", [], tabela="pt_certidoes")


def test_o_protocolo_escolhido_sem_item_livre_diz_isso():
    """Quem escolheu o protocolo e não marcou item precisa saber que o
    protocolo é que está vazio — senão marca de novo o mesmo protocolo."""
    with pytest.raises(PSELO.SeloSemItemError) as erro:
        PSELO.conferir_antes_de_lavrar("CANCELAMENTO", [],
                                       protocolo_escolhido=True)
    assert "protocolo escolhido não tem item livre" in str(erro.value)
    with pytest.raises(PSELO.SeloSemItemError) as erro:
        PSELO.conferir_antes_de_lavrar("CANCELAMENTO", [])
    assert "protocolo escolhido" not in str(erro.value)


def test_nao_ha_afirmacao_expressa_que_venca_esta_trava():
    """MEDIDO, e não gosto (29/10/2026): o Protesto não tem gratuidade no
    lançamento, e os 12 selos isentos do Protesto no razão saíram COM o
    código do item. Lavrar sem item é pedir um selo que não pode sair — a
    afirmação não mudaria o que o aparelho precisa receber. Se um dia a
    conferência ganhar um caminho para vencê-la, este teste obriga a
    decisão a ser revista, e não esquecida."""
    parametros = inspect.signature(PSELO.conferir_antes_de_lavrar).parameters
    assert not [p for p in parametros if "afirm" in p]
    fonte = (RAIZ / "protesto_selo_previo.py").read_text(encoding="utf-8")
    assert "NÃO HÁ AFIRMAÇÃO EXPRESSA QUE VENÇA ESTA TRAVA" in fonte


def test_a_rota_le_a_mesma_lista_e_a_mesma_regua_do_selo():
    """Duas réguas para «há item?» divergiriam no primeiro conserto: a recusa
    diria uma coisa e o selo faria outra."""
    fonte = (RAIZ / "atribuicoes_web.py").read_text(encoding="utf-8")
    assert "atos_sem_selo_proprio = PSELO.ATOS_SEM_SELO_PROPRIO" in fonte
    # o selo (depois), o ato e a certidão (antes): a mesma função
    assert fonte.count("_itens_do_selo_do_protesto(con,") >= 3
    assert fonte.count("PSELO.conferir_antes_de_lavrar(") == 2


# ---------------------------------------- a situação sem o ato que a sustenta


def banco() -> sqlite3.Connection:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    init_nucleo_schema(con)
    init_pt_schema(con)
    return con


def _titulo(con, situacao: str, *, chave: str, numero: str) -> int:
    return int(nativo(con).escrever(
        """INSERT INTO pt_titulos(especie, numero_titulo, protocolo,
               valor_centavos, saldo_centavos, situacao, origem, origem_chave,
               criado_em)
           VALUES ('DMI', %s, %s, 10000, 10000, %s, 'CRA', %s, %s)
           RETURNING id""",
        (numero, "2610290001", situacao, chave, AGORA))[0]["id"])


def _ato(con, titulo_id: int, tipo: str, *, cancelado: bool = False,
         motivo: str | None = None) -> int:
    return int(nativo(con).escrever(
        """INSERT INTO pt_atos(titulo_id, tipo, data_ato, detalhe_json, origem,
               cancelado, motivo_cancelamento, criado_em)
           VALUES (%s, %s, %s, '{}', 'MANUAL', %s, %s, %s) RETURNING id""",
        (titulo_id, tipo, AGORA[:10], 1 if cancelado else 0, motivo,
         AGORA))[0]["id"])


@pytest.fixture()
def casa():
    con = banco()
    ids = {}
    # O 9614: o pagamento foi desfeito pelo selo, e o título ficou PAGO.
    ids["desfeito"] = t = _titulo(con, "PAGO", chave="t:desfeito", numero="T1")
    _ato(con, t, "APONTAMENTO")
    ids["ato_desfeito"] = _ato(con, t, "PAGAMENTO", cancelado=True,
                               motivo="Selo não emitido: sem item.")
    # Os quatro do acervo: a carga trouxe PAGO sem o ato de pagamento.
    ids["acervo"] = t = _titulo(con, "PAGO", chave="tbAvisoProtesto:7",
                                numero="T2")
    _ato(con, t, "APONTAMENTO")
    # Protestado sem protesto nenhum, e não é do acervo.
    ids["sem_ato"] = _titulo(con, "PROTESTADO", chave="t:sem", numero="T3")
    # OS QUE ESTÃO EM ORDEM, e não podem aparecer:
    t = _titulo(con, "CANCELADO", chave="t:refeito", numero="T4")
    _ato(con, t, "CANCELAMENTO", cancelado=True, motivo="Selo não emitido: x")
    _ato(con, t, "CANCELAMENTO")                    # lançado de novo, válido
    t = _titulo(con, "DESISTIDO", chave="t:retirada", numero="T5")
    _ato(con, t, "RETIRADA")                        # a retirada sustenta
    _titulo(con, "RECEBIDO", chave="t:recebido", numero="T6")  # não pede ato
    t = _titulo(con, "PAGO", chave="t:pago", numero="T7")
    _ato(con, t, "PAGAMENTO")
    ids["em_ordem"] = t
    return con, ids


def test_a_conferencia_acha_a_situacao_sem_ato_e_diz_por_que(casa):
    con, ids = casa
    achados = {x["titulo_id"]: x for x in PSELO.titulos_sem_ato_que_sustente(con)}
    assert set(achados) == {ids["desfeito"], ids["acervo"], ids["sem_ato"]}

    desfeito = achados[ids["desfeito"]]
    assert desfeito["origem"] == "DESFEITO"
    assert desfeito["desfeito_id"] == ids["ato_desfeito"]
    assert desfeito["ato_esperado"] == "pagamento"
    assert "Selo não emitido: sem item" in desfeito["explicacao"]
    assert "continuou PAGO" in desfeito["explicacao"]

    assert achados[ids["acervo"]]["origem"] == "ACERVO"
    assert "carga do E-Ofício" in achados[ids["acervo"]]["explicacao"]
    assert achados[ids["sem_ato"]]["origem"] == "SEM_ATO"
    assert achados[ids["sem_ato"]]["ato_esperado"] == "protesto"


def test_a_conferencia_de_um_titulo_so_serve_a_ficha(casa):
    con, ids = casa
    assert PSELO.situacao_sem_ato(con, ids["desfeito"])["origem"] == "DESFEITO"
    assert PSELO.situacao_sem_ato(con, ids["em_ordem"]) is None


def test_a_conferencia_tem_teto(casa):
    con, _ids = casa
    assert len(PSELO.titulos_sem_ato_que_sustente(con, limite=1)) == 1


def test_toda_situacao_que_pede_ato_e_conferida():
    """A régua não pode esquecer uma situação: as finais e as do caminho.
    RECEBIDO é a única que não pede ato — é o título antes de qualquer um."""
    import protesto as PT
    pedem = set(PT.SITUACOES_TITULO) - {"RECEBIDO"}
    assert set(PSELO.ATO_QUE_SUSTENTA) == pedem
    for tipos in PSELO.ATO_QUE_SUSTENTA.values():
        assert set(tipos) <= set(PT.TIPOS_ATO)


def _literais_sem_docstring(caminho: Path) -> list[str]:
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    docstrings = {id(n.body[0].value) for n in ast.walk(arvore)
                  if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef))
                  and n.body and isinstance(n.body[0], ast.Expr)
                  and isinstance(n.body[0].value, ast.Constant)}
    return [no.value for no in ast.walk(arvore)
            if isinstance(no, ast.Constant) and isinstance(no.value, str)
            and id(no) not in docstrings]


def test_a_conferencia_so_le():
    """«Não corrija dado da produção; só mostre.» O módulo não tem comando
    que escreva — o conserto do título é decisão do oficial."""
    for texto in _literais_sem_docstring(RAIZ / "protesto_selo_previo.py"):
        alto = texto.upper()
        for comando in ("INSERT ", "UPDATE ", "DELETE ", "ALTER ", "DROP "):
            assert comando not in alto, (comando, texto[:60])


def test_o_sql_novo_nao_aumenta_o_acoplamento():
    """Módulo novo entra com zero — a regra de `tests/test_portabilidade.py`."""
    for texto in _literais_sem_docstring(RAIZ / "protesto_selo_previo.py"):
        baixo = texto.lower()
        for proibido in ("substr(", "||", "strftime(", "julianday(", "pragma"):
            assert proibido not in baixo, (proibido, texto[:60])
