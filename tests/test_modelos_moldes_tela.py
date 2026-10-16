"""A TELA dos papéis das certidões — Administrativo → Modelos.

    «Atualizar esses modelos no modulo de modelos, para poder editar por la»
                                            — o oficial, 10/09/2026

**BURACO DE TELA NÃO APARECE EM TESTE DE DOMÍNIO.** Os 15 de
`test_modelos_moldes.py` provam a regra; estes provam que existe por onde
usá-la — que é o defeito que mais se repetiu neste projeto (função pronta que
nenhuma tela chama, seis vezes).
"""
from __future__ import annotations

import glob
import io
import re
import sys
import zipfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import modelos_moldes as MOLDES

SENHA = "Senha#12345"
MOLDE_NASC = RAIZ / "modelos" / "certidao_nascimento_modelo.odt"
tem_o_molde = pytest.mark.skipif(
    not MOLDE_NASC.is_file(), reason="o molde .odt não está nesta instalação")


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

def _tela(casa) -> str:
    r = casa["cliente"].get("/modelos")
    assert r.status_code == 200
    return r.get_data(as_text=True)


def _enviar(casa, arquivo: bytes, *, chave="RC_MOLDE_NASCIMENTO",
            nome="molde.odt", acao="enviar"):
    html = _tela(casa)
    dados = {"csrf_token": _token(html), "chave": chave, "acao": acao}
    if arquivo is not None:
        dados["arquivo"] = (io.BytesIO(arquivo), nome)
    return casa["cliente"].post("/modelos/molde", data=dados,
                                content_type="multipart/form-data",
                                follow_redirects=True).get_data(as_text=True)


# --------------------------------------------------------------- a tela


@tem_o_molde
def test_a_tela_oferece_os_tres_papeis(casa):
    """Sem esta linha o oficial não teria por onde chegar neles — e o pedido
    era justamente «poder editar por la»."""
    html = _tela(casa)
    for m in MOLDES.MOLDES:
        assert m["nome"] in html, m["chave"]
    assert "/modelos/molde/RC_MOLDE_NASCIMENTO/baixar" in html


@tem_o_molde
def test_a_tela_avisa_que_a_atualizacao_apagaria_o_ajuste_no_arquivo(casa):
    """**A RAZÃO DE PASSAR PELA TELA TEM DE ESTAR ESCRITA NELA.**

    A linha 55 do `ATUALIZAR_SISTEMA.cmd` copia a pasta `modelos` inteira por
    cima (`/E`). Quem ajustasse o `.odt` instalado perderia o trabalho na
    atualização seguinte **sem aviso** — e não desconfiaria, porque a certidão
    continua saindo, só sem o ajuste. A tela diz isso antes de qualquer botão.
    """
    html = _tela(casa)
    assert "atualização" in html
    assert "apagado" in html or "apagada" in html


@tem_o_molde
def test_baixar_entrega_o_odt_que_vale_hoje(casa):
    r = casa["cliente"].get("/modelos/molde/RC_MOLDE_NASCIMENTO/baixar")
    assert r.status_code == 200
    assert r.data == MOLDE_NASC.read_bytes()
    assert "opendocument.text" in r.headers["Content-Type"]
    assert ".odt" in r.headers["Content-Disposition"]


@tem_o_molde
def test_enviar_grava_e_a_certidao_passa_a_sair_nele(casa):
    marca = "PAPEL AJUSTADO PELA CASA"
    ajustado = _trocar(MOLDE_NASC.read_bytes(),
                       "CERTIDÃO DE NASCIMENTO", marca)
    html = _enviar(casa, ajustado, nome="meu_papel.odt")
    assert "gravado" in html.lower()
    assert "ajustado por esta casa" in html

    r = casa["cliente"].get("/modelos/molde/RC_MOLDE_NASCIMENTO/baixar")
    assert r.data == ajustado
    assert "meu_papel.odt" in r.headers["Content-Disposition"]


@tem_o_molde
def test_a_tela_recusa_marcador_que_o_codigo_nao_preenche(casa):
    """E o recado diz **qual** marcador, porque é ele que a pessoa tem de
    achar no LibreOffice."""
    torto = _trocar(MOLDE_NASC.read_bytes(),
                    "@nomenascido", "@nome_do_registrado")
    html = _enviar(casa, torto)
    assert "@nome_do_registrado" in html
    assert "ajustado por esta casa" not in html   # nada foi gravado


def test_a_tela_recusa_arquivo_que_nao_e_odt(casa):
    html = _enviar(casa, b"isto nao e um zip")
    assert ".odt" in html
    assert "ajustado por esta casa" not in html


def test_enviar_sem_escolher_arquivo_avisa_em_vez_de_estourar(casa):
    """Erro de regra não é HTTP 500 — e clicar em «Enviar» com o campo vazio
    é o engano mais fácil de cometer aqui."""
    html = _enviar(casa, None)
    assert "Escolha o arquivo" in html


@tem_o_molde
def test_voltar_ao_papel_do_pacote(casa):
    _enviar(casa, _trocar(MOLDE_NASC.read_bytes(),
                          "CERTIDÃO DE NASCIMENTO", "OUTRA COISA"))
    html = _enviar(casa, None, acao="restaurar")
    assert "pacote" in html
    r = casa["cliente"].get("/modelos/molde/RC_MOLDE_NASCIMENTO/baixar")
    assert r.data == MOLDE_NASC.read_bytes()


@tem_o_molde
def test_o_escrevente_nao_troca_o_papel_da_certidao(casa):
    """**SÓ ADMIN E GERENTE**, e o motivo não é hierarquia: este arquivo é a
    forma de um documento que a serventia assina, e uma coluna fora do lugar
    aqui sai em toda certidão daquela espécie até alguém reparar. É a mesma
    guarda da tela dos modelos de texto."""
    casa["db"].create_user("elisa", "Elisa Exemplo Lima", SENHA, "USER")
    c = casa["app"].test_client()
    c.post("/login",
           data={"username": "elisa", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    assert c.get("/modelos/molde/RC_MOLDE_NASCIMENTO/baixar",
                 follow_redirects=True).status_code in (200, 403)
    # o que importa: ele não grava
    r = c.post("/modelos/molde",
               data={"chave": "RC_MOLDE_NASCIMENTO", "acao": "restaurar"},
               follow_redirects=True)
    assert b"Papel gravado" not in r.data


@tem_o_molde
def test_A_CERTIDAO_EMITIDA_SAI_NO_PAPEL_QUE_A_CASA_ENVIOU(casa):
    """**A PONTA QUE FALTAVA, e ela é a que importa.**

    Gravar o papel na tela e a certidão continuar saindo no do pacote seria o
    defeito de sempre deste projeto pelo pior lado: a tela dizendo «gravado» e
    o programa imprimindo outra coisa. Os testes de domínio provam que
    `arquivo_da_certidao` sabe usar `molde_bytes`; **este prova que a ROTA o
    passa** — que é o pedaço que nenhum teste de mesa alcança.

    Ele percorre o caminho inteiro: envia o papel pela tela de Modelos, lavra
    o assento, emite a certidão e abre o `.odt` que saiu.
    """
    marca = "PAPEL AJUSTADO PELA CASA"
    ajustado = _trocar(MOLDE_NASC.read_bytes(),
                       "CERTIDÃO DE NASCIMENTO", marca)
    assert "gravado" in _enviar(casa, ajustado).lower()

    assento_id = _semear_assento(casa)
    _emitir(casa, assento_id)
    con = _con(casa)
    linha = con.execute("SELECT id FROM rc_certidoes").fetchone()
    con.close()
    assert linha, ("a certidão não foi emitida — o ensaio não chegou à parte "
                   "que ele mede")

    r = casa["cliente"].get(f"/rcpn/certidoes/{linha['id']}/odt?formato=odt")
    assert r.status_code == 200
    with zipfile.ZipFile(io.BytesIO(r.get_data())) as z:
        texto = z.read("content.xml").decode("utf-8")
    assert marca in texto, "a certidão saiu no papel do pacote, e não no ajustado"


@tem_o_molde
def test_sem_papel_ajustado_a_certidao_sai_no_do_pacote(casa):
    """O outro lado do mesmo caminho — e é o de hoje, e o de qualquer
    instalação que nunca tenha enviado nada. **Documento que não sai é pior
    que documento sem o ajuste novo.**"""
    assento_id = _semear_assento(casa)
    _emitir(casa, assento_id)
    con = _con(casa)
    linha = con.execute("SELECT id FROM rc_certidoes").fetchone()
    con.close()
    assert linha
    r = casa["cliente"].get(f"/rcpn/certidoes/{linha['id']}/odt?formato=odt")
    with zipfile.ZipFile(io.BytesIO(r.get_data())) as z:
        texto = z.read("content.xml").decode("utf-8")
    assert "CERTIDÃO DE NASCIMENTO" in texto


# ------------------------------------------------------------- o cenário
#
# O assento e a folha são os de `test_rc_certidao_web.py` — o mesmo caso, com
# a mesma razão: `origem='EOFICIO'` com ato de REGISTRO sem selo cai na guarda
# `FOLHA_SEGURANCA_OBRIGATORIA_CERT` de 09/09/2026, que exige a folha
# escolhida.


def _con(casa):
    import sqlite3
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _semear_assento(casa) -> int:
    con = _con(casa)
    with con:
        con.execute(
            """INSERT INTO rc_assentos(serie, especie, numero, matricula, nome,
                   data_ato, data_fato, dados_json, situacao, origem,
                   criado_em)
               VALUES ('RC_A','NASCIMENTO',19552,
                       '000000015519971000111270010385 01','JOÃO DA SILVA',
                       '2020-01-20','2020-01-15','{"strSexo": "Masculino"}',
                       'ATIVO','EOFICIO','2026-09-10T09:00:00')""")
        aid = con.execute("SELECT id FROM rc_assentos").fetchone()["id"]
        con.execute(
            """INSERT INTO rc_atos(assento_id, tipo, folha, numero_ordem,
                   rotulo, data_ato, origem, criado_em)
               VALUES (?,'REGISTRO',127,19552,'127','2020-01-20','EOFICIO',
                       '2026-09-10T09:00:00')""", (aid,))
        for papel, quem, ordem in (("PAI", "JOSÉ DA SILVA", 1),
                                   ("MAE", "MARIA DAS GRAÇAS SILVA", 2)):
            con.execute(
                """INSERT INTO rc_pessoas(assento_id, papel, nome, ordem,
                       origem, criado_em)
                   VALUES (?,?,?,?,'EOFICIO','2026-09-10T09:00:00')""",
                (aid, papel, quem, ordem))
    con.close()
    return aid


def _folha(casa) -> str:
    con = _con(casa)
    codigo = "9999999"
    with con:
        con.execute(
            """INSERT INTO pp_remessas(fornecedor, codigo_de, codigo_ate,
                   quantas, recebida_em)
               VALUES ('TESTE', ?, ?, 1, '2026-09-10T00:00:00')""",
            (codigo, codigo))
        rid = con.execute(
            "SELECT id FROM pp_remessas ORDER BY id DESC LIMIT 1").fetchone()["id"]
        con.execute(
            "INSERT INTO pp_folhas(codigo, remessa_id, situacao, criada_em) "
            "VALUES (?,?,'EM BRANCO','2026-09-10T00:00:00')", (codigo, rid))
    con.close()
    return codigo


def _emitir(casa, assento_id: int):
    html = casa["cliente"].get(f"/rcpn/{assento_id}").get_data(as_text=True)
    return casa["cliente"].post(
        f"/rcpn/{assento_id}/certidao",
        data={"csrf_token": _token(html), "requerente": "A MÃE",
              "finalidade": "INSS", "folha_seguranca": _folha(casa)},
        follow_redirects=True)


def _trocar(base: bytes, de: str, para: str) -> bytes:
    fora = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(base)) as zin, \
            zipfile.ZipFile(fora, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            dados = zin.read(item.filename)
            if item.filename == "content.xml":
                dados = dados.decode("utf-8").replace(de, para).encode("utf-8")
            zout.writestr(item, dados)
    return fora.getvalue()
