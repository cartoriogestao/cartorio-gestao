"""Selo da notificação (item 16.23), prenotação e protocolo — 03/11/2026.

A notificação da retificação saía impressa sem selo, e a ficha não gravava
a prenotação nem o protocolo de recepção. O usucapião sela pelo mesmo caminho.
"""
from __future__ import annotations

import io
import re
import sqlite3
import sys
import zipfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import notificacao_selo as NS                                    # noqa: E402
import retificacao as RT                                         # noqa: E402
import rt_tjma as NORMA                                          # noqa: E402
from protocolo_de_teste import _protocolo_pago                   # noqa: E402

SENHA = "Senha#12345"
AGORA = "2026-08-29T09:00"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa):
    db = cg_casa["db"]
    c = cg_casa["cliente"]
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c.post("/login",
           data={"username": "mario", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return cg_casa


def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _matricula(casa, numero="3315", livro="2S"):
    con = _con(casa)
    with con:
        cur = con.execute(
            """INSERT INTO ri_matriculas (numero, livro, situacao, criado_em)
               VALUES (?, ?, 'ATIVA', ?)""", (numero, livro, AGORA))
    return int(cur.lastrowid)


def _abrir_processo(casa, matricula_id, numero="1/2026"):
    html = casa["cliente"].get(
        "/registro-imoveis/retificacoes/nova").get_data(as_text=True)
    casa["cliente"].post(
        "/registro-imoveis/retificacoes/nova",
        data={"csrf_token": _token(html), "numero": numero,
              "matricula_id": str(matricula_id),
              "especie": NORMA.GEORREFERENCIADA,
              "fundamento": NORMA.A_REQUERIMENTO, "rural": "1",
              "requerente_nome": "ANTONIO JARDINEIRO PEREIRA"},
        follow_redirects=True)
    linha = _con(casa).execute(
        "SELECT id FROM rt_processos WHERE numero = ?", (numero,)).fetchone()
    assert linha, "o processo não abriu"
    return int(linha["id"])


def _anotar(casa, pid, nome="JOAO DA MATA", documento=""):
    html = casa["cliente"].get(
        f"/registro-imoveis/retificacoes/{pid}").get_data(as_text=True)
    return casa["cliente"].post(
        f"/registro-imoveis/retificacoes/{pid}/confrontante",
        data={"csrf_token": _token(html), "nome": nome, "documento": documento,
              "papel": RT.CONFRONTANTE, "divisa_afetada": "1",
              "endereco": "Rua da Divisa, 10, Cidade Exemplo/MA"},
        follow_redirects=True)


def _notificar(casa, pid, cid, quando="2026-11-03"):
    html = casa["cliente"].get(
        f"/registro-imoveis/retificacoes/{pid}").get_data(as_text=True)
    return casa["cliente"].post(
        f"/registro-imoveis/retificacoes/{pid}/notificar",
        data={"csrf_token": _token(html), "confrontante_id": str(cid),
              "forma": "PESSOAL", "quando": quando, "prazo_ate": "2026-11-24"},
        follow_redirects=True)


def _protocolo(casa):
    con = _con(casa)
    with con:
        feito = _protocolo_pago(con, codigos=[NS.CODIGO], quantidade=1,
                                atribuicao="RI")
    con.close()
    return feito


def _ligar_protocolo(casa, pid, numero):
    html = casa["cliente"].get(
        f"/registro-imoveis/retificacoes/{pid}").get_data(as_text=True)
    return casa["cliente"].post(
        f"/registro-imoveis/retificacoes/{pid}/atendimento",
        data={"csrf_token": _token(html), "protocolo_busca": numero},
        follow_redirects=True)


def _odt(casa, pid, cid):
    r = casa["cliente"].get(
        f"/registro-imoveis/retificacoes/{pid}/notificacao/{cid}?formato=odt")
    assert r.status_code == 200, r.status_code
    xml = zipfile.ZipFile(io.BytesIO(r.data)).read("content.xml").decode("utf-8")
    return xml


# ------------------------------------------------ data, duplicado, exclusão


def test_data_futura_nao_notifica(casa):
    mid = _matricula(casa)
    pid = _abrir_processo(casa, mid)
    saida = _anotar(casa, pid)
    cid = _con(casa).execute(
        "SELECT id FROM rt_confrontantes WHERE processo_id = ?", (pid,)).fetchone()["id"]
    pagina = _notificar(casa, pid, cid, quando="2099-01-01").get_data(as_text=True)
    assert "não pode ser futura" in pagina
    linha = _con(casa).execute(
        "SELECT notificado_em FROM rt_confrontantes WHERE id = ?", (cid,)).fetchone()
    assert not linha["notificado_em"]
    assert "Confrontante anotado" in saida.get_data(as_text=True)


def test_confrontante_repetido_avisa_e_grava(casa):
    mid = _matricula(casa)
    pid = _abrir_processo(casa, mid)
    _anotar(casa, pid, nome="JOAO DA MATA", documento="00000000191")
    pagina = _anotar(casa, pid, nome="Joao da Mata", documento="000.000.001-91"
                     ).get_data(as_text=True)
    assert "mesmo CPF" in pagina or "mesmo nome" in pagina
    assert _con(casa).execute(
        "SELECT COUNT(*) FROM rt_confrontantes WHERE processo_id = ?",
        (pid,)).fetchone()[0] == 2


def test_exclusao_antes_da_notificacao_e_negada_depois(casa):
    mid = _matricula(casa)
    pid = _abrir_processo(casa, mid)
    _anotar(casa, pid)
    cid = int(_con(casa).execute(
        "SELECT id FROM rt_confrontantes WHERE processo_id = ?", (pid,)).fetchone()["id"])
    html = casa["cliente"].get(
        f"/registro-imoveis/retificacoes/{pid}").get_data(as_text=True)
    feito = casa["cliente"].post(
        f"/registro-imoveis/retificacoes/{pid}/confrontante/{cid}/excluir",
        data={"csrf_token": _token(html)}, follow_redirects=True)
    assert "excluído" in feito.get_data(as_text=True)
    assert _con(casa).execute(
        "SELECT COUNT(*) FROM rt_confrontantes WHERE processo_id = ?",
        (pid,)).fetchone()[0] == 0
    anda = _con(casa).execute(
        "SELECT o_que FROM rt_andamento WHERE processo_id = ? AND tipo = ?",
        (pid, "CONFRONTANTE_EXCLUIDO")).fetchone()
    assert anda and "excluído" in anda["o_que"]

    _anotar(casa, pid, nome="MARIA DA MATA")
    cid = int(_con(casa).execute(
        "SELECT id FROM rt_confrontantes WHERE processo_id = ?", (pid,)).fetchone()["id"])
    _notificar(casa, pid, cid)
    html = casa["cliente"].get(
        f"/registro-imoveis/retificacoes/{pid}").get_data(as_text=True)
    recusa = casa["cliente"].post(
        f"/registro-imoveis/retificacoes/{pid}/confrontante/{cid}/excluir",
        data={"csrf_token": _token(html)}, follow_redirects=True).get_data(as_text=True)
    assert "não se exclui" in recusa
    assert _con(casa).execute(
        "SELECT COUNT(*) FROM rt_confrontantes WHERE id = ?", (cid,)).fetchone()[0] == 1


# ------------------------------------------------ prenotação e protocolo


def test_prenotacao_vencida_e_protocolo_entram_no_processo(casa):
    mid = _matricula(casa)
    pid = _abrir_processo(casa, mid)
    con = _con(casa)
    with con:
        con.execute(
            """INSERT INTO ri_protocolos
               (numero, livro, data_prenotacao, matricula_id, matricula_numero,
                data_limite, situacao, criado_em)
               VALUES (9001, '1A', '2020-01-10', ?, '3315', '2020-02-10',
                       'ABERTO', ?)""", (mid, AGORA))
        pre_id = con.execute("SELECT id FROM ri_protocolos WHERE numero = 9001"
                             ).fetchone()["id"]
    lista = casa["cliente"].get(
        "/registro-imoveis/retificacoes/prenotacoes",
        query_string={"matricula_id": str(mid)}).get_json()
    assert lista["itens"][0]["id"] == pre_id
    assert lista["itens"][0]["vencida"] is True
    assert "vencida" in lista["itens"][0]["rotulo"]

    protocolo = _protocolo(casa)
    html = casa["cliente"].get(
        f"/registro-imoveis/retificacoes/{pid}").get_data(as_text=True)
    casa["cliente"].post(
        f"/registro-imoveis/retificacoes/{pid}/atendimento",
        data={"csrf_token": _token(html), "prenotacao_id": str(pre_id),
              "protocolo_busca": protocolo["numero"]},
        follow_redirects=True)
    linha = _con(casa).execute(
        "SELECT prenotacao_id, prenotacao, protocolo_id FROM rt_processos WHERE id = ?",
        (pid,)).fetchone()
    assert int(linha["prenotacao_id"]) == int(pre_id)
    assert str(linha["prenotacao"]) == "9001"
    assert int(linha["protocolo_id"]) == int(protocolo["protocolo_id"])
    anda = _con(casa).execute(
        "SELECT o_que FROM rt_andamento WHERE processo_id = ? AND tipo = ?",
        (pid, "ATENDIMENTO")).fetchone()
    assert anda and "9001" in anda["o_que"] and protocolo["numero"] in anda["o_que"]
    ficha = casa["cliente"].get(
        f"/registro-imoveis/retificacoes/{pid}").get_data(as_text=True)
    assert "9001" in ficha and protocolo["numero"] in ficha


def test_a_previa_sem_selo_nao_e_impressao_final(casa):
    mid = _matricula(casa)
    pid = _abrir_processo(casa, mid)
    _anotar(casa, pid)
    cid = int(_con(casa).execute(
        "SELECT id FROM rt_confrontantes WHERE processo_id = ?", (pid,)).fetchone()["id"])
    _notificar(casa, pid, cid)
    xml = _odt(casa, pid, cid)
    assert "SEM SELO" in xml and "NÃO ENTREGAR" in xml
    linha = _con(casa).execute(
        "SELECT impresso_em, selo FROM rt_confrontantes WHERE id = ?", (cid,)).fetchone()
    assert not linha["impresso_em"] and not linha["selo"]


# ------------------------------------------------ o selo


@pytest.fixture()
def bancada(casa):
    from selador_de_bancada import ligar_o_selador
    with ligar_o_selador(casa, protocolo_pago=False) as aparelho:
        yield casa, aparelho


def _notificacao_pronta(casa):
    mid = _matricula(casa, "3316", "2S")
    pid = _abrir_processo(casa, mid, numero="2/2026")
    _anotar(casa, pid, nome="PEDRO DA CERCA")
    cid = int(_con(casa).execute(
        "SELECT id FROM rt_confrontantes WHERE processo_id = ?", (pid,)).fetchone()["id"])
    _notificar(casa, pid, cid)
    protocolo = _protocolo(casa)
    _ligar_protocolo(casa, pid, protocolo["numero"])
    return pid, cid, protocolo


def _selar(casa, pid, cid, **extra):
    html = casa["cliente"].get(
        f"/registro-imoveis/retificacoes/{pid}").get_data(as_text=True)
    dados = {"csrf_token": _token(html)}
    dados.update(extra)
    return casa["cliente"].post(
        f"/registro-imoveis/retificacoes/{pid}/confrontante/{cid}/selar",
        data=dados, follow_redirects=True)


def test_humano_sela_e_o_segundo_selo_nao_sai(bancada):
    casa, aparelho = bancada
    pid, cid, protocolo = _notificacao_pronta(casa)
    pagina = _selar(casa, pid, cid).get_data(as_text=True)
    assert "Notificação selada" in pagina, pagina[pagina.find("flash"):pagina.find("flash") + 400]
    linha = _con(casa).execute(
        "SELECT selo, selo_item, selo_por FROM rt_confrontantes WHERE id = ?",
        (cid,)).fetchone()
    assert linha["selo"] and linha["selo_item"] == "16.23"
    assert linha["selo_por"]
    usadas = _con(casa).execute(
        "SELECT quantidade_usada FROM cx_protocolo_atos WHERE id = ?",
        (protocolo["itens"][0],)).fetchone()[0]
    assert int(usadas) == 1
    pedidos = [p for p in aparelho.pedidos if p["caminho"].endswith(NS.CAMINHO)]
    assert pedidos and "16.23" in pedidos[-1]["corpo"]

    de_novo = _selar(casa, pid, cid).get_data(as_text=True)
    assert "já tem selo" in de_novo
    usadas = _con(casa).execute(
        "SELECT quantidade_usada FROM cx_protocolo_atos WHERE id = ?",
        (protocolo["itens"][0],)).fetchone()[0]
    assert int(usadas) == 1

    xml = _odt(casa, pid, cid)
    assert linha["selo"] in xml
    assert "NÃO ENTREGAR" not in xml
    impresso = _con(casa).execute(
        "SELECT impresso_em FROM rt_confrontantes WHERE id = ?", (cid,)).fetchone()[0]
    assert impresso


def test_selo_que_falha_devolve_a_unidade_e_deixa_a_notificacao(bancada):
    casa, aparelho = bancada
    pid, cid, protocolo = _notificacao_pronta(casa)
    aparelho.recusar_com = (400, {"message": "recusado pelo aparelho"})
    pagina = _selar(casa, pid, cid).get_data(as_text=True)
    assert "NÃO saiu" in pagina
    linha = _con(casa).execute(
        "SELECT selo, notificado_em, teor_expedido FROM rt_confrontantes WHERE id = ?",
        (cid,)).fetchone()
    assert not linha["selo"] and linha["notificado_em"] and linha["teor_expedido"]
    usadas = _con(casa).execute(
        "SELECT coalesce(quantidade_usada, 0) FROM cx_protocolo_atos WHERE id = ?",
        (protocolo["itens"][0],)).fetchone()[0]
    assert int(usadas) == 0


def test_robo_recebe_403_ao_selar(casa):
    casa["db"].create_user("robo_ret", "Robo da Retificacao", SENHA, "USER", eh_robo=1)
    c = casa["app"].test_client()
    c.post("/login",
           data={"username": "robo_ret", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    token = _token(c.get("/").get_data(as_text=True))
    r = c.post("/registro-imoveis/retificacoes/1/confrontante/1/selar",
               data={"csrf_token": token})
    assert r.status_code == 403
    r2 = c.post("/usucapiao/1/notificacao/1/selar", data={"csrf_token": token})
    assert r2.status_code == 403


def test_usucapiao_sela_pelo_mesmo_item(bancada):
    """O movimento de notificação do usucapião gasta o mesmo 16.23."""
    casa, aparelho = bancada
    import usucapiao as US
    con = _con(casa)
    with con:
        pid = US.autuar(con, numero="US-1/2026", modalidade="ORDINARIA",
                        agora=AGORA, requerente_nome="JOAO BATISTA", usuario="mario")
        US.notificar(
            con, pid, destinatario="MARIA DAS DORES",
            destinatario_papel="Confrontante ao norte",
            endereco="Rua do Comércio, 45", forma="PESSOAL",
            prazo_chave="CONFRONTANTE", agora=AGORA,
            serventia={"oficial": "MARIO EXEMPLO", "cargo": "Oficial",
                       "nome": "Serventia de Cidade Exemplo/MA"},
            hoje_extenso="Cidade Exemplo, 3 de novembro de 2026",
            usuario="mario")
        con.commit()
    mid = con.execute(
        "SELECT id FROM us_movimentos WHERE processo_id = ? AND tipo = 'NOTIFICACAO'",
        (pid,)).fetchone()["id"]
    protocolo = _protocolo(casa)
    with con:
        con.execute("UPDATE us_processos SET protocolo_id = ? WHERE id = ?",
                    (protocolo["protocolo_id"], pid))
        con.execute(
            "UPDATE cx_protocolo_atos SET gratuito = 1, quitado = 0 WHERE id = ?",
            (protocolo["itens"][0],))
        con.commit()
    html = casa["cliente"].get(f"/usucapiao/{pid}").get_data(as_text=True)
    r = casa["cliente"].post(
        f"/usucapiao/{pid}/notificacao/{mid}/selar",
        data={"csrf_token": _token(html), "isento": "1",
              "motivo_isencao": "REURB-S"},
        follow_redirects=True)
    html = r.get_data(as_text=True)
    avisos = re.findall(r'class="flash[^"]*"[^>]*>(.*?)<button', html, re.S)
    assert "Notificação selada" in html, avisos
    selo = con.execute("SELECT selo, selo_item FROM us_movimentos WHERE id = ?",
                       (mid,)).fetchone()
    assert selo["selo"] and selo["selo_item"] == "16.23"
    assert any("16.23" in p["corpo"] and "REURB-S" in p["corpo"].upper()
               for p in aparelho.pedidos)
