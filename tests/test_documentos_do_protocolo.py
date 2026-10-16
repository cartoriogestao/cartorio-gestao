"""Os documentos do protocolo, e o ato que precisa vê-los — relato #25.

A FRASE DO OFICIAL:

    «protocolo geral e do RI precisa ter mais funções, como anexar documentos.
     protocolo precisa permitir anexar documentos e visualizar esses
     documentos. E o ato em que se vincula a esse determinado protocolo precisa
     poder visualizar os documentos anexos ao protocolo, **até para facilitar a
     lavratura do ato**»

A SEGUNDA FRASE É QUE MANDA NO DESENHO. Guardar arquivo é a parte fácil — a
tabela `attachments` já existe e já serve expediente e tarefa, com 20 arquivos
guardados. O que ele pediu é que o **título apresentado** esteja à vista de quem
está escrevendo a averbação: quem lavra tem o papel na mão e o teor em branco na
frente, e ir a outra tela buscar a escritura é largar o que está escrevendo.

O QUE SE MEDIU EM 29/08/2026
    `attachments` é genérica (`entity_type` + `entity_id`) e tinha **20
    arquivos, todos de EXPEDIENTE**. A prenotação do RI **não tinha anexo
    nenhum** — nem tabela própria, nem uso da genérica.
"""
from __future__ import annotations

import glob
import io as _io
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ri_documentos as RDOC

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa):
    """App/DB compartilhados do modulo (conftest); setup de dominio por teste."""
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


def _matricula(con, numero="4010"):
    cur = con.execute(
        """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao,
               tipo_ficha, criado_em)
           VALUES (?, '2', '2', 'ATIVA', 'ESTRUTURADA', '2026-08-29T09:00')""",
        (numero,))
    return int(cur.lastrowid)


def _prenotacao(con, *, numero=11534, situacao="ABERTO", ato_id=None):
    cur = con.execute(
        """INSERT INTO ri_protocolos (numero, livro, data_prenotacao,
               apresentante, situacao, ato_id, criado_em)
           VALUES (?, '1A', '2026-08-29', 'FULANO DE TAL', ?, ?,
                   '2026-08-29T09:00')""", (numero, situacao, ato_id))
    return int(cur.lastrowid)


def _ato(con, matricula_id, *, numero=1, prenotacao=None):
    from ri_schema import hash_ato
    h = hash_ato("4010", "R", numero, "2026-08-29", "x", None)
    cur = con.execute(
        """INSERT INTO ri_atos (matricula_id, tipo, numero, data_ato, teor,
               teor_formato, cancelado, acervo, origem, prenotacao,
               hash_ato, lavrado_em)
           VALUES (?, 'R', ?, '2026-08-29', 'x', 'texto', 0, 0, 'MANUAL', ?,
                   ?, '2026-08-29T09:00')""",
        (matricula_id, numero, prenotacao, h))
    return int(cur.lastrowid)


def _anexar(casa, protocolo_id, *, nome="escritura.pdf", descricao="a escritura"):
    html = casa["cliente"].get(
        f"/registro-imoveis/protocolo/{protocolo_id}").get_data(as_text=True)
    return casa["cliente"].post(
        f"/registro-imoveis/prenotacao/{protocolo_id}/documento",
        data={"csrf_token": _token(html), "descricao": descricao,
              "documento": (_io.BytesIO(b"%PDF-1.4 o titulo"), nome)},
        content_type="multipart/form-data", follow_redirects=True)


# ------------------------------------------- anexar e ver na prenotação


def test_a_prenotacao_recebe_e_mostra_o_documento(casa):
    con = _con(casa)
    with con:
        pid = _prenotacao(con)
    r = _anexar(casa, pid)
    assert "anexado a prenotacao" in r.get_data(as_text=True)
    docs = RDOC.documentos_de(_con(casa), RDOC.ENTIDADE_RI, pid)
    assert [d["original_name"] for d in docs] == ["escritura.pdf"]
    assert docs[0]["description"] == "a escritura"


def test_o_documento_vai_para_a_mesma_tabela_do_expediente(casa):
    """Uma segunda tabela de anexo faria dois lugares para procurar o mesmo
    papel — e no dia em que alguém pedisse «todos os documentos deste
    cliente», seriam duas consultas que ninguém lembraria de somar."""
    con = _con(casa)
    with con:
        pid = _prenotacao(con)
    _anexar(casa, pid)
    r = _con(casa).execute(
        "SELECT entity_type, entity_id FROM attachments").fetchone()
    assert r["entity_type"] == "RI_PROTOCOLO"
    assert r["entity_id"] == pid


def test_anexar_sem_escolher_arquivo_e_recusado(casa):
    con = _con(casa)
    with con:
        pid = _prenotacao(con)
    html = casa["cliente"].get(
        f"/registro-imoveis/protocolo/{pid}").get_data(as_text=True)
    r = casa["cliente"].post(
        f"/registro-imoveis/prenotacao/{pid}/documento",
        data={"csrf_token": _token(html)}, follow_redirects=True)
    assert "Escolha o arquivo" in r.get_data(as_text=True)
    assert _con(casa).execute(
        "SELECT COUNT(*) c FROM attachments").fetchone()["c"] == 0


# ------------------------------------------- as duas pontes até o ato


def test_a_ligacao_gravada_vem_antes_do_numero_digitado(casa):
    """`ri_protocolos.ato_id` foi escrito pela máquina ao lavrar;
    `ri_atos.prenotacao` é texto que alguém digitou. Invertida, a ordem daria a
    resposta errada no dia em que o número fosse digitado trocado num ato que
    já tem amarração boa."""
    con = _con(casa)
    with con:
        mid = _matricula(con)
        # o ato aponta, pelo TEXTO, para uma prenotação errada
        aid = _ato(con, mid, prenotacao="9999")
        certa = _prenotacao(con, numero=1111, ato_id=aid)
        _prenotacao(con, numero=9999)
    achada = RDOC.prenotacao_do_ato(_con(casa), aid)
    # 1111 e não '1111': `ri_protocolos.numero` é coluna INTEGER, e a afinidade
    # do SQLite converte na entrada. Comparar com texto aqui procuraria o que
    # não está lá.
    assert achada["numero"] == 1111
    assert achada["ligacao"] == "gravada"
    assert achada["id"] == certa


def test_sem_ligacao_gravada_vale_o_numero_do_ato(casa):
    """Os 784 atos do acervo têm `ato_id` nulo — sem esta reserva, o acervo
    inteiro ficaria sem documento."""
    con = _con(casa)
    with con:
        mid = _matricula(con)
        # o ato traz o número com PONTO DE MILHAR, como o escrevente digitou
        # num dos 12 atos reais desta casa — e a coluna é INTEGER
        aid = _ato(con, mid, prenotacao="11.534")
        _prenotacao(con, numero=11534)
    achada = RDOC.prenotacao_do_ato(_con(casa), aid)
    assert achada["numero"] == 11534
    assert achada["ligacao"] == "pelo número"


def test_ato_sem_prenotacao_nao_fala_de_prenotacao(casa):
    """Tela que fala de prenotação para ato que não tem uma é ruído — e ruído é
    o que faz ninguém ler o aviso que importa."""
    con = _con(casa)
    with con:
        mid = _matricula(con)
        aid = _ato(con, mid)
    visao = RDOC.documentos_para_lavrar(_con(casa), aid)
    assert visao == {"prenotacao": None, "documentos": [], "ligacao": None}


def test_o_ato_enxerga_o_documento_da_prenotacao_dele(casa):
    """É o pedido inteiro numa linha."""
    con = _con(casa)
    with con:
        mid = _matricula(con)
        aid = _ato(con, mid)
        pid = _prenotacao(con, ato_id=aid)
    _anexar(casa, pid, nome="itbi.pdf", descricao="guia do ITBI")
    visao = RDOC.documentos_para_lavrar(_con(casa), aid)
    assert [d["original_name"] for d in visao["documentos"]] == ["itbi.pdf"]


# ------------------------------------------- a tela de quem lavra


def test_a_ficha_nao_repete_documentos_das_prenotacoes_abertas(casa):
    """Relato #85: o bloco «Documentos das prenotações abertas» saiu da ficha.
    O anexo continua na tela do protocolo (relato #25)."""
    con = _con(casa)
    with con:
        mid = _matricula(con)
        pid = _prenotacao(con, situacao="ABERTO")
    _anexar(casa, pid, nome="escritura.pdf", descricao="compra e venda")
    ficha = casa["cliente"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    assert "Documentos das prenotações abertas" not in ficha
    protocolo = casa["cliente"].get(
        f"/registro-imoveis/protocolo/{pid}").get_data(as_text=True)
    assert "escritura.pdf" in protocolo
    assert "compra e venda" in protocolo


# ------------------------------------------- o módulo só lê


def test_o_modulo_dos_documentos_nao_grava_nada():
    """Quem guarda é `db.add_attachment`, pelo caminho que já existia e que já
    serve o expediente e a tarefa."""
    codigo = (RAIZ / "ri_documentos.py").read_text(encoding="utf-8")
    assert "INSERT " not in codigo
    assert "UPDATE " not in codigo
    assert "DELETE " not in codigo


def test_o_lugar_de_guardar_e_do_catalogo(casa):
    """`entity_type` inventado espalharia anexo por nomes que ninguém procura
    depois."""
    with pytest.raises(RDOC.DocumentoError) as e:
        RDOC.documentos_de(_con(casa), "QUALQUER_COISA", 1)
    assert "não é um lugar onde eu saiba guardar" in str(e.value)


def test_o_zero_nao_e_prenotacao(casa):
    """Medido: três atos desta casa trazem `'0'` em `prenotacao` — é o campo em
    branco que alguém preencheu com zero. Tratado como número, ele acharia o
    protocolo zero se algum dia existisse um."""
    con = _con(casa)
    with con:
        mid = _matricula(con)
        aid = _ato(con, mid, prenotacao="0")
        _prenotacao(con, numero=0)
    assert RDOC.prenotacao_do_ato(_con(casa), aid) is None

# ------------------------------------------- layout (relato ajuda #60)


def test_documentos_do_titulo_nao_ficam_no_heading():
    """Relato #60 (Carla, 15/09/2026): painel Documentos do titulo
    estava em block heading (virava .page-heading no topbar).
    Heading so tem h1; painel fica no content apos a barra de acoes.
    """
    tpl = (RAIZ / "templates" / "ri_protocolo_ver.html").read_text(encoding="utf-8")
    hm = re.search(r"(?s)\{% block heading %\}(.*?)\{% endblock %\}", tpl)
    assert hm, "block heading ausente"
    heading = hm.group(1)
    assert "<h1>" in heading
    assert "Documentos do" not in heading
    assert "<section" not in heading
    assert 'name="documento"' not in heading
    cm = re.search(r"(?s)\{% block content %\}(.*?)\{% endblock %\}", tpl)
    assert cm, "block content ausente"
    body = cm.group(1)
    assert "Documentos do" in body
    assert 'name="documento"' in body
    assert "Comprovante de prenota" in body
    assert body.index("Comprovante de prenota") < body.index("Documentos do")
    assert "REGRESS" in tpl and "#60" in tpl
