"""RELATO #50 — a data do depósito prévio.

A frase do oficial, de 11/09/2026, na tela do depósito:

    «NESTE CAMPO DE DEPÓSITO PRÉVIO DEVE CONTER DATA DO DEPÓSITO.
     INFORMAÇÕES DO TIPO DE SERVIÇO»

A DATA. A peça já existia inteira: `cx_depositos.data` é coluna desde sempre e
`criar(hoje=...)` já aceitava a data. **O que faltava era a tela pedi-la** — ela
gravava sempre a de hoje, e o caso comum é o contrário: o cliente deixa o
dinheiro na sexta e o balcão registra na segunda.

A SEGUNDA METADE («informações do tipo de serviço») **já está construída**, e
tem arquivo próprio: `tests/test_relato_50_tipo_de_servico.py`. Esta nota dizia
que ela não estava, e continuou dizendo depois de ela existir — o carimbo que
mente, na forma mais barata de consertar: a frase estava desatualizada e quem a
lesse planejaria trabalho feito.

O QUE ESTES TESTES PROVAM, E A ORDEM IMPORTA:

1. a tela pede a data (sem isso o resto não chega);
2. a data do papel é a que fica gravada;
3. **o lançamento no caixa continua sendo o do dia em que o dinheiro entrou** —
   a gaveta conta o dinheiro quando ele entra, e lançar com a data do papel
   mexeria no caixa de um dia já conferido;
4. data impossível é recusada com frase, e não com HTTP 500;
5. sem data informada, vale hoje — o caminho de quem não mexe no campo.
"""
from __future__ import annotations

import re
import sqlite3
from datetime import date, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

OPERADOR = "MARIO EXEMPLO DOS SANTOS"


def _token(c, rota: str = "/caixa/depositos") -> str:
    html = c.get(rota).get_data(as_text=True)
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela do depósito prévio não trouxe csrf_token"
    return achado.group(1)


def _registrar(c, **campos):
    corpo = {"csrf_token": _token(c), "acao": "novo",
             "depositante": "CONSTRUTORA ALFA LTDA", "valor": "450,00"}
    corpo.update(campos)
    return c.post("/caixa/depositos", data=corpo, follow_redirects=True)


def _depositos(banco) -> list[dict]:
    con = sqlite3.connect(str(banco))
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute("SELECT * FROM cx_depositos")]
    finally:
        con.close()


def _lancamentos(banco) -> list[dict]:
    con = sqlite3.connect(str(banco))
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(
            "SELECT * FROM cx_lancamentos WHERE natureza='DEPOSITO_PREVIO'")]
    finally:
        con.close()


def _abrir_caixa(banco) -> None:
    con = sqlite3.connect(str(banco))
    con.execute("""INSERT INTO cx_caixas (data, operador_nome, situacao,
                                          saldo_inicial, aberto_em)
                   VALUES (?, ?, 'ABERTO', '0,00', ?)""",
                (date.today().isoformat(), OPERADOR, "2026-09-15T10:00:00"))
    con.commit()
    con.close()


# ------------------------------------------------------------- a tela

def test_a_tela_pede_a_data_do_deposito(cg_casa_logada):
    """A tela gravava a data de hoje sem perguntar. O campo é o que faz o resto
    existir — sem ele, a data do papel nunca chega ao banco."""
    html = cg_casa_logada["c"].get("/caixa/depositos").get_data(as_text=True)
    assert 'name="data"' in html, "a tela do depósito não pede a data"
    assert 'type="date"' in html, "o campo da data não é um campo de data"
    assert date.today().isoformat() in html, \
        "o campo da data não abre preenchido com hoje"


def test_a_tela_diz_que_a_data_e_a_do_papel(cg_casa_logada):
    """Data de papel que o sistema não explica é data que o operador não sabe se
    pode mudar."""
    html = cg_casa_logada["c"].get("/caixa/depositos").get_data(as_text=True)
    assert "comprovante" in html


# --------------------------------------------------------- o domínio

def test_a_data_do_papel_e_a_que_fica_gravada(cg_casa_logada):
    """O caso comum: dinheiro deixado na sexta, registrado na segunda."""
    sexta = (date.today() - timedelta(days=3)).isoformat()
    _registrar(cg_casa_logada["c"], data=sexta)
    d = _depositos(cg_casa_logada["banco"])
    assert len(d) == 1, "o depósito não foi gravado"
    assert d[0]["data"] == sexta


def test_sem_data_informada_vale_hoje(cg_casa_logada):
    """Quem não mexe no campo — que abre preenchido — não digita nada."""
    _registrar(cg_casa_logada["c"])
    assert _depositos(cg_casa_logada["banco"])[0]["data"] == date.today().isoformat()


def test_o_lancamento_no_caixa_e_o_do_dia_do_dinheiro(cg_casa_logada):
    """**A parte que não podia ser esquecida.**

    A data do papel vai para o depósito; o lançamento no caixa continua sendo o
    do dia em que o dinheiro entrou. Lançar com a data do papel mexeria no caixa
    de um dia já conferido — que é justamente o que a conferência do caixa
    existe para impedir.
    """
    banco = cg_casa_logada["banco"]
    _abrir_caixa(banco)
    antiga = (date.today() - timedelta(days=5)).isoformat()

    _registrar(cg_casa_logada["c"], data=antiga)

    assert _depositos(banco)[0]["data"] == antiga
    lanc = _lancamentos(banco)
    assert len(lanc) == 1, "o depósito não entrou no movimento do caixa"
    assert lanc[0]["data"] == date.today().isoformat(), \
        "o lançamento no caixa ficou com a data do papel"
    assert lanc[0]["data"] != antiga


def test_a_frase_da_tela_lembra_a_data_informada(cg_casa_logada):
    """Registrar o papel de sexta na segunda e ler «registrado» sem a data faria
    o operador conferir o campo de novo, sem saber se o sistema entendeu."""
    antiga = (date.today() - timedelta(days=5)).isoformat()
    r = _registrar(cg_casa_logada["c"], data=antiga)
    html = r.get_data(as_text=True)
    dia = f"{antiga[8:10]}/{antiga[5:7]}/{antiga[:4]}"
    assert dia in html, f"a frase não lembra a data informada ({dia})"


def test_data_impossivel_e_recusada_com_frase_no_balcao(cg_casa_logada):
    """Erro de regra não é HTTP 500: a recusa é no balcão, com o cliente na
    frente, e nada é gravado pela metade."""
    r = _registrar(cg_casa_logada["c"], data="31/02/2026")
    assert _depositos(cg_casa_logada["banco"]) == [], \
        "gravou depósito com data impossível"
    assert "não é uma data válida" in r.get_data(as_text=True)


def test_o_dominio_aceita_a_data_do_papel_e_numera_pelo_dia_do_registro(cg_db):
    """A peça no domínio, sem passar pela tela.

    A numeração de controle (`DP<ano>.<mes>.<sequencial>`) continua saindo do
    dia do registro: ela é o número que o cliente cita quando volta, e renumerar
    por causa de um papel de outra data embaralharia a série do mês.
    """
    import caixa_depositos as DEP

    with cg_db.transaction() as con:
        feito = DEP.criar(
            con, valor_centavos=1000, depositante="FULANO DE TAL",
            agora="2026-09-15T10:00:00",
            hoje=date(2026, 9, 15), data_do_deposito=date(2026, 9, 12))

    assert feito["data"] == "2026-09-12"
    assert feito["numero"].startswith("DP2026.09."), \
        "a numeração deixou de ser a do mês do registro"


def test_a_caixa_o_ri_e_a_tela_da_data_seguem_uma_criacao_so():
    """A criação do depósito vive em `caixa_depositos.py`, e o parâmetro novo
    não pode ter virado um segundo caminho em outra tela."""
    caixa = (RAIZ / "caixa_web.py").read_text(encoding="utf-8")
    ri = (RAIZ / "ri_web.py").read_text(encoding="utf-8")
    assert "DEP.criar(" in caixa and "DEP.criar(" in ri
    for nome, codigo in (("caixa_web", caixa), ("ri_web", ri)):
        assert "INSERT INTO cx_depositos" not in codigo, \
            f"{nome} voltou a criar depósito por fora do módulo"
