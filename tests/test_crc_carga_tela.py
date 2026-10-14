"""A tela da carga da CRC.

POR QUE SEPARADO
    `test_crc_carga.py` prova que o **módulo** monta e retém. Este prova que a
    **tela chama o módulo** — nono caso, neste projeto, em que essa diferença
    importa.
"""
from __future__ import annotations

import glob
import re
import sqlite3
import sys
from pathlib import Path

import pytest
from werkzeug.datastructures import MultiDict

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

SENHA = "Senha#12345"
AGORA = "2026-08-20T09:00"
M32 = "00000001552026100002269100086802"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa):
    """App/DB compartilhados do modulo (conftest); setup de dominio por teste."""
    db = cg_casa["db"]
    c = cg_casa["cliente"]
    db.create_user("jean", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    db.set_settings({"serventia_cns": "000000"})
    c.post("/login",
           data={"username": "jean", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return cg_casa

def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _liso(t: str) -> str:
    return " ".join((t or "").split())


def _nascimento(casa, nome="MARIA ÍSIS", *, numero=1, matricula=M32):
    con = _con(casa)
    with con:
        cur = con.execute(
            """INSERT INTO rc_assentos (serie, especie, numero, nome, data_ato,
                   data_fato, situacao, origem, criado_em, matricula)
               VALUES ('RC_A','NASCIMENTO',?,?,?,?,'ATIVO','SISTEMA',?,?)""",
            (numero, nome, "2026-08-20", "2026-08-18", AGORA, matricula))
        aid = int(cur.lastrowid)
        con.execute(
            """INSERT INTO rc_pessoas (assento_id, papel, nome, nome_norm,
                   sexo, criado_em) VALUES (?,?,?,?,?,?)""",
            (aid, "REGISTRADO", nome, nome.lower(), "F", AGORA))
    return aid


def _abrir(casa, url="/rcpn/crc"):
    r = casa["cliente"].get(url)
    assert r.status_code == 200, f"{url} não abriu ({r.status_code})"
    return _liso(r.get_data(as_text=True))


def _campos(html, ids):
    """O formulario com o campo `assento` REPETIDO.

    PRECISA DE `MultiDict`: o cliente de teste do Werkzeug so aceita repeticao
    assim — uma lista de pares ele tenta ler como dicionario e estoura com
    «list object has no attribute items».

    E a repeticao e o ponto: a tela manda uma caixa marcada por assento, e o
    modulo recebe a lista inteira. Um teste que mandasse um so nao provaria que
    a tela sabe mandar varios.
    """
    campos = MultiDict([("csrf_token", _token(html))])
    for i in ids:
        campos.add("assento", str(i))
    return campos


def _montar(casa, ids):
    html = casa["cliente"].get("/rcpn/crc").get_data(as_text=True)
    return casa["cliente"].post("/rcpn/crc", data=_campos(html, ids),
                                follow_redirects=True)


# ------------------------------------------------ a tela explica


def test_a_tela_diz_por_que_a_crc_vem_primeiro(casa):
    html = _abrir(casa)
    assert "art. 243" in html
    assert "primeiramente pelo sistema CRC" in html


def test_a_tela_oferece_o_envio_pelo_web_service(casa):
    """Desde 10/09/2026 a tela envia de verdade, assinado com o A3 — o
    modelo por upload (sem assinatura) continua ao lado, para quando a
    Central estiver fora do ar ou o A3 não estiver disponível."""
    html = _abrir(casa)
    assert "web service" in html
    assert "certificado A3" in html


def test_a_tela_diz_que_os_vocabularios_estao_todos_preenchidos(casa):
    """**A LISTA ESVAZIOU EM 10/09/2026, E A TELA DIZ ISSO.**

    Ela listava cinco campos que «ainda não sabemos preencher, porque o manual
    manda ver o XSD e ele não veio junto». **O XSD veio** — está no PDF do
    manual v2.6, na pasta da casa, com 344 enumerações dentro.

    Com a lista vazia, o bloco antigo sairia com a frase e uma lista em branco,
    terminando num ponto solto: **pior que não ter bloco**, porque a frase
    afirma que falta algo e não diz o quê. Agora ela diz o contrário, que é o
    fato, e conta o que o conserto alcançou.
    """
    html = _abrir(casa)
    assert "vocabulário fechado estão preenchidos" in html
    assert "REGIMECASAMENTO" not in html
    # E o que ela conta tem de ser o que se mediu, e não «melhorias».
    assert "não é gêmeo" in html or "não</em> é gêmeo" in html
    assert "VIOLENTA" in html
    # A frase «escolher por semelhança seria assinar por quem preencheu» era do
    # bloco antigo, e ela volta sozinha no dia em que houver campo sem
    # vocabulário — o modelo guarda os dois lados.


# ------------------------------------------------ montar


def test_a_tela_monta_o_xml(casa):
    aid = _nascimento(casa)
    r = _montar(casa, [aid])
    html = _liso(r.get_data(as_text=True))
    assert "1 registro(s) no arquivo" in html
    assert "CARGAREGISTROS" in html


def test_a_tela_mostra_o_retido_com_o_motivo(casa):
    """Mandar só o que deu certo produziria um arquivo bem formado e incompleto
    — e a Central o aceitaria."""
    bom = _nascimento(casa)
    ruim = _nascimento(casa, "SEM MATRÍCULA", numero=2, matricula=None)
    r = _montar(casa, [bom, ruim])
    html = _liso(r.get_data(as_text=True))
    assert "1 registro(s) no arquivo" in html
    assert "1 ficaram de fora" in html
    assert "SEM MATRÍCULA" in html
    assert "matrícula de 32 dígitos" in html


def test_montar_sem_escolher_nada_avisa(casa):
    html = casa["cliente"].get("/rcpn/crc").get_data(as_text=True)
    r = casa["cliente"].post("/rcpn/crc",
                             data={"csrf_token": _token(html)},
                             follow_redirects=True)
    assert "Escolha ao menos um assento" in _liso(r.get_data(as_text=True))


def test_a_tela_marca_quem_esta_sem_matricula(casa):
    _nascimento(casa, "SEM MATRÍCULA", matricula=None)
    html = _abrir(casa)
    assert "sem matrícula" in html


# ------------------------------------------------ o arquivo


def test_o_arquivo_sai_em_utf8(casa):
    aid = _nascimento(casa, "MARIA ÍSIS DA CONCEIÇÃO")
    html = casa["cliente"].get("/rcpn/crc").get_data(as_text=True)
    r = casa["cliente"].post("/rcpn/crc/arquivo",
                             data=_campos(html, [aid]))
    assert r.status_code == 200
    assert r.mimetype == "application/xml"
    assert "crc-carga-" in r.headers["Content-Disposition"]
    texto = r.data.decode("utf-8")
    assert "MARIA ÍSIS DA CONCEIÇÃO" in texto
    assert "<CNS>000000</CNS>" in texto


def test_o_arquivo_sem_escolha_volta_avisando(casa):
    html = casa["cliente"].get("/rcpn/crc").get_data(as_text=True)
    r = casa["cliente"].post("/rcpn/crc/arquivo",
                             data={"csrf_token": _token(html)},
                             follow_redirects=True)
    assert "Escolha ao menos um assento" in _liso(r.get_data(as_text=True))


def test_montar_nao_grava_nada(casa):
    """Montar o arquivo não muda nada no banco — o que muda é o envio, e este
    sistema não envia."""
    aid = _nascimento(casa)
    antes = dict(_con(casa).execute(
        "SELECT * FROM rc_assentos WHERE id=?", (aid,)).fetchone())
    _montar(casa, [aid])
    depois = dict(_con(casa).execute(
        "SELECT * FROM rc_assentos WHERE id=?", (aid,)).fetchone())
    assert antes == depois


def test_a_carga_esta_no_menu(casa):
    assert "Carga da CRC" in _abrir(casa)


def test_a_tela_explica_por_que_o_numero_e_grande(casa):
    """**MESMO NÚMERO, DUAS TELAS, SENTIDOS OPOSTOS.** Na produção as duas
    devolviam 243: no SIRC era defeito (prazo de um dia útil sobre registro de
    1955); aqui é o esperado, porque a carga é *justamente* a subida do acervo
    histórico à Central.

    Sem esta frase, quem abrir a tela vai achar que está com 243 dias de
    trabalho atrasado.
    """
    html = _abrir(casa)
    assert "não é atraso" in html or "e não atraso" in html
    assert "carga do acervo histórico" in html or "acervo histórico" in html
