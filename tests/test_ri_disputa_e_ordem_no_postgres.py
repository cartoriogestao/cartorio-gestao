"""O que o BEGIN IMMEDIATE do SQLite segurava no RI, e o PostgreSQL não.

RESSALVAS DA REVISÃO DO LOTE L059 (17/10/2026), consertadas no L059R. No
SQLite a rota abria `BEGIN IMMEDIATE` e ninguém mais escrevia até ela acabar;
no PostgreSQL a transação é de cada um, e o que se lê para depois gravar
precisa de trava (`bd.travar`) ou de `SELECT ... FOR UPDATE`.

O QUE ESTES TESTES GUARDAM:

  1. **Dois atos da mesma prenotação:** o segundo não rouba o elo do
     primeiro (`amarrar_prenotacao`). O elo é a prioridade do título — Lei
     6.015/1973, art. 186.
  2. **Dois arquivamentos da mesma prenotação:** o segundo diz «já
     encerrada», e não «encerrou».
  3. **Ato lavrado por outro balcão no meio da lavratura:** o número e o hash
     anterior se releem dentro da trava. Na ficha estruturada o ato toma o
     número seguinte; na de acervo, o número digitado é recusado.
  4. **A ordem dos NULL:** o SQLite punha o NULL no começo da ordem crescente,
     e o PostgreSQL o põe no fim. O indicador real continua como era.
  5. **A ordem das digitalizações** se renumera sob a trava
     `ri_imagens.ordem`.

DUAS CONEXÕES NO MESMO BANCO são dois balcões: a segunda roda numa thread e
fica parada enquanto a primeira não confirma — é a disputa de verdade, e não
uma simulação dela.
"""
from __future__ import annotations

import ast
import re
import sqlite3
import sys
import tempfile
import textwrap
import threading
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

import banco_pg  # noqa: E402
import bd_nativo  # noqa: E402
import ri_web  # noqa: E402
from bd_nativo import banco  # noqa: E402

WEB = RAIZ / "ri_web.py"


# ------------------------------------------------------- as funções soltas

def _funcoes(*nomes: str) -> dict:
    """As funções de dentro de `registrar_rotas`, tiradas do fonte.

    Elas moram dentro da fábrica de rotas e só usam `banco` — e, desde o
    LD10, `numero_digitado`, a régua do tamanho do protocolo digitado, que mora
    no módulo; executar o fonte delas num espaço próprio é o que
    `test_arquivamento_encerra_prenotacao` já faz. E, desde 26/10/2026, o
    `ACOMP` (`onr_acompanhamento`): `amarrar_prenotacao` anota o «Título
    registrado» na fila do ONR — o gancho nunca derruba a amarração —, com a
    hora de `db.now()` (estático em `Database`).
    """
    from database import Database
    fonte = WEB.read_text(encoding="utf-8")
    ns: dict = {"banco": banco, "numero_digitado": ri_web.numero_digitado,
                "ACOMP": ri_web.ACOMP, "db": Database}
    for no in ast.walk(ast.parse(fonte)):
        if isinstance(no, ast.FunctionDef) and no.name in nomes:
            trecho = " " * no.col_offset + ast.get_source_segment(fonte, no)
            exec(textwrap.dedent(trecho), ns)
    faltam = [n for n in nomes if n not in ns]
    assert not faltam, f"não achei no ri_web.py: {faltam}"
    return ns


def _banco_de_dois_balcoes() -> str:
    """O caminho de um banco de teste em que se abrem DUAS conexões."""
    arquivo = Path(tempfile.mkdtemp(prefix="cg_teste_")) / "teste.sqlite3"
    banco_pg.registrar_banco(arquivo)
    return str(arquivo)


def _segundo_balcao(caminho: str, chamar) -> tuple[threading.Thread, dict]:
    """Roda `chamar(con)` noutra conexão e noutra thread, e confirma."""
    resposta: dict = {}

    def rodar():
        con = sqlite3.connect(caminho)
        try:
            resposta["r"] = chamar(con)
            con.commit()
        except Exception as erro:  # noqa: BLE001 — o teste mostra qual foi
            resposta["erro"] = erro
        finally:
            con.close()

    t = threading.Thread(target=rodar, daemon=True)
    t.start()
    # O segundo chega enquanto o primeiro ainda não confirmou.
    t.join(1.0)
    return t, resposta


def test_dois_atos_da_mesma_prenotacao_o_segundo_nao_rouba_o_elo():
    amarrar = _funcoes("amarrar_prenotacao")["amarrar_prenotacao"]
    caminho = _banco_de_dois_balcoes()
    con = sqlite3.connect(caminho)
    con.executescript(
        """
        CREATE TABLE ri_protocolos (
            id INTEGER PRIMARY KEY, numero INTEGER NOT NULL, situacao TEXT,
            ato_id INTEGER, matricula_id INTEGER);
        INSERT INTO ri_protocolos VALUES (1, 11546, 'ABERTO', NULL, NULL);
        """)
    con.commit()

    primeiro = amarrar(con, "11546", matricula_id=7, ato_id=101)
    assert primeiro.get("amarrou"), primeiro
    t, resposta = _segundo_balcao(
        caminho, lambda c: amarrar(c, "11546", matricula_id=7, ato_id=202))
    con.commit()
    t.join(15)
    assert not t.is_alive(), "o segundo balcão ficou preso"
    assert "erro" not in resposta, resposta.get("erro")

    elo = con.execute("SELECT ato_id FROM ri_protocolos WHERE id=1").fetchone()[0]
    con.close()
    assert elo == 101, (
        "o segundo ato sobrescreveu o elo da prenotação — a prioridade do "
        "primeiro título se perdeu")
    assert resposta["r"].get("ja_tinha_ato") is True, resposta["r"]


def test_o_protocolo_de_digitos_demais_nao_acha_e_nao_derruba():
    """Ressalva 6 do L059, conferida: o `int()` grande vai como numeric."""
    amarrar = _funcoes("amarrar_prenotacao")["amarrar_prenotacao"]
    con = sqlite3.connect(_banco_de_dois_balcoes())
    con.executescript(
        """
        CREATE TABLE ri_protocolos (
            id INTEGER PRIMARY KEY, numero INTEGER NOT NULL, situacao TEXT,
            ato_id INTEGER, matricula_id INTEGER);
        INSERT INTO ri_protocolos VALUES (1, 11546, 'ABERTO', NULL, NULL);
        """)
    r = amarrar(con, "9" * 40, matricula_id=7, ato_id=101)
    con.close()
    assert r == {"achou": False, "numero": "9" * 40}


def test_dois_arquivamentos_da_mesma_prenotacao_o_segundo_le_ja_encerrada():
    encerrar = _funcoes("encerrar_prenotacao_do_ato_apos_arquivamento")[
        "encerrar_prenotacao_do_ato_apos_arquivamento"]
    caminho = _banco_de_dois_balcoes()
    con = sqlite3.connect(caminho)
    con.executescript(
        """
        CREATE TABLE ri_protocolos (
            id INTEGER PRIMARY KEY, numero INTEGER, situacao TEXT,
            situacao_anterior TEXT,
            encerrado_em TEXT, encerrado_por TEXT,
            motivo_encerramento TEXT, obs_encerramento TEXT);
        CREATE TABLE ri_atos (id INTEGER PRIMARY KEY, protocolo TEXT);
        INSERT INTO ri_protocolos (id, numero, situacao, situacao_anterior)
        VALUES (1, 11546, 'ABERTO', NULL);
        INSERT INTO ri_atos VALUES (10, '11546');
        INSERT INTO ri_atos VALUES (11, '11.546');
        """)
    con.commit()

    primeiro = encerrar(con, 10)
    assert primeiro.get("encerrou") is True, primeiro
    t, resposta = _segundo_balcao(caminho, lambda c: encerrar(c, 11))
    con.commit()
    t.join(15)
    con.close()
    assert not t.is_alive(), "o segundo balcão ficou preso"
    assert "erro" not in resposta, resposta.get("erro")
    assert resposta["r"].get("ja_encerrada") is True, (
        "o segundo arquivamento contou ao balcão que encerrou uma prenotação "
        f"que o primeiro já tinha encerrado: {resposta['r']}")
    assert resposta["r"].get("encerrou") is not True


# ------------------------------------------------------- a lavratura

@pytest.fixture()
def casa(cg_casa_logada):
    from selador_de_bancada import ligar_o_selador
    with ligar_o_selador(cg_casa_logada):
        yield cg_casa_logada


def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela nao trouxe csrf_token"
    return achado.group(1)


def _ficha(casa, *, numero: str, tipo_ficha: str, **colunas) -> int:
    con = _con(casa)
    with con:
        nomes = ", ".join(["numero", "livro", "livro_norm", "situacao",
                           "tipo_ficha", "teor", "criado_em", *colunas])
        valores = [numero, "2", "2", "ATIVA", tipo_ficha,
                   "Imóvel de teste.", "2026-09-16T08:00", *colunas.values()]
        mid = con.execute(
            f"INSERT INTO ri_matriculas ({nomes}) VALUES "
            f"({', '.join(['?'] * len(valores))})", valores).lastrowid
    con.close()
    return int(mid)


def _outro_balcao_lavra_no_meio(casa, monkeypatch, mid: int) -> None:
    """Grava R-01 na ficha DEPOIS de a rota conferir o número, e ANTES de ela
    abrir a transação: o ponto em que o SQLite a deixava sozinha."""
    original = ri_web.RIMIN.marcador_de_modelo

    def no_meio(teor):
        monkeypatch.setattr(ri_web.RIMIN, "marcador_de_modelo", original)
        outro = _con(casa)
        with outro:
            outro.execute(
                """INSERT INTO ri_atos (matricula_id, tipo, numero, data_ato,
                       teor, teor_formato, cancelado, acervo, origem,
                       hash_ato, lavrado_em)
                   VALUES (?, 'R', 1, '2026-09-16', 'R-01 do outro balcão.',
                           'texto', 0, 0, 'MANUAL', 'hash-do-outro-balcao',
                           '2026-09-16T09:00:00')""", (mid,))
        outro.close()
        return original(teor)

    monkeypatch.setattr(ri_web.RIMIN, "marcador_de_modelo", no_meio)


def _lavrar_av_01(casa, mid: int, token: str, *, com_selo: bool):
    return casa["cliente"].post(
        f"/registro-imoveis/{mid}/atos",
        data={"csrf_token": token, "tipo": "AV", "numero": "1",
              "data_ato": "2026-09-16", "teor": "AV-01 averbação de teste.",
              "natureza_titulo": "Compra e venda",
              "codigo_tj": "16.3" if com_selo else "",
              "base_calculo": "1000,00" if com_selo else ""},
        follow_redirects=True)


def _atos(casa, mid: int) -> list[dict]:
    con = _con(casa)
    linhas = [dict(r) for r in con.execute(
        """SELECT tipo, numero, hash_anterior FROM ri_atos
            WHERE matricula_id=? ORDER BY id""", (mid,))]
    con.close()
    return linhas


def test_na_ficha_estruturada_o_ato_toma_o_numero_seguinte_ao_do_outro_balcao(
        casa, monkeypatch):
    mid = _ficha(casa, numero="4100", tipo_ficha="ESTRUTURADA")
    token = _token(casa["cliente"].get(f"/registro-imoveis/{mid}")
                   .get_data(as_text=True))
    _outro_balcao_lavra_no_meio(casa, monkeypatch, mid)

    _lavrar_av_01(casa, mid, token, com_selo=True)

    atos = _atos(casa, mid)
    assert [(a["tipo"], a["numero"]) for a in atos] == [("R", 1), ("AV", 2)], (
        f"dois atos com o mesmo número na mesma ficha: {atos}")
    assert atos[1]["hash_anterior"] == "hash-do-outro-balcao", (
        "a corrente de hash bifurcou: o ato novo não aponta para o que foi "
        "lavrado antes dele")


def test_na_ficha_de_acervo_o_numero_tomado_no_meio_e_recusado(casa, monkeypatch):
    mid = _ficha(casa, numero="4101", tipo_ficha="ACERVO")
    token = _token(casa["cliente"].get(f"/registro-imoveis/{mid}")
                   .get_data(as_text=True))
    _outro_balcao_lavra_no_meio(casa, monkeypatch, mid)

    r = _lavrar_av_01(casa, mid, token, com_selo=False)

    assert [(a["tipo"], a["numero"]) for a in _atos(casa, mid)] == [("R", 1)], (
        "a ficha de acervo ficou com R-01 e AV-01")
    assert "O número 1 já está ocupado nesta matrícula pelo ato R-01" in \
        r.get_data(as_text=True)


# ------------------------------------------------------- a ordem dos NULL

def test_o_indicador_real_poe_a_ficha_sem_bairro_na_frente_como_o_sqlite(casa):
    sem_bairro = _ficha(casa, numero="4102", tipo_ficha="ESTRUTURADA")
    centro = _ficha(casa, numero="4103", tipo_ficha="ESTRUTURADA",
                    bairro="CENTRO", logradouro="RUA A")
    vazio = _ficha(casa, numero="4104", tipo_ficha="ESTRUTURADA",
                   bairro="", logradouro="")
    html = casa["cliente"].get("/registro-imoveis/indicador-real") \
        .get_data(as_text=True)
    html = re.sub(r'<div role="alert".*?</div>', "", html, flags=re.S)
    vistas = [int(x) for x in re.findall(r'"/registro-imoveis/(\d+)"', html)]
    vistas = [i for i in vistas if i in (sem_bairro, centro, vazio)]
    assert vistas == [sem_bairro, vazio, centro], vistas


# ------------------------------------------------- a ordem das digitalizações

def test_reordenar_e_excluir_digitalizacao_travam_a_ordem(casa, monkeypatch):
    mid = _ficha(casa, numero="4105", tipo_ficha="ESTRUTURADA")
    con = _con(casa)
    with con:
        ids = [int(con.execute(
            """INSERT INTO ri_imagens (matricula_id, nome_arquivo, ordem,
                                       ficha_digitalizada)
               VALUES (?, ?, ?, 1)""", (mid, f"pagina-{n}", n)).lastrowid)
               for n in (1, 2, 3)]
    con.close()

    chaves: list[str] = []
    travar = bd_nativo.Banco.travar

    def anotar(self, chave):
        chaves.append(chave)
        return travar(self, chave)

    monkeypatch.setattr(bd_nativo.Banco, "travar", anotar)
    for dados in ({"acao": "subir", "imagem_id": ids[2]},
                  {"acao": "excluir", "imagem_id": ids[0]}):
        token = _token(casa["cliente"].get(f"/registro-imoveis/{mid}")
                       .get_data(as_text=True))
        chaves.clear()
        casa["cliente"].post(f"/registro-imoveis/{mid}/imagens",
                             data={"csrf_token": token, **dados},
                             follow_redirects=True)
        assert "ri_imagens.ordem" in chaves, (dados["acao"], chaves)

    con = _con(casa)
    ordem = [(r["nome_arquivo"], r["ordem"]) for r in con.execute(
        "SELECT nome_arquivo, ordem FROM ri_imagens WHERE matricula_id=? "
        "ORDER BY ordem", (mid,))]
    con.close()
    assert ordem == [("pagina-3", 1), ("pagina-2", 2)], ordem
