"""ATÉ ONDE CADA MÓDULO VAI — e o Protesto de volta para o oficial.

Ordem dele em 01/09/2026, na mesma noite em que mandou desligá-lo:
*«reabilite o protesto para o administrador, permitindo um botão em
configurações habilitar para todos usuarios»*.

**A PERGUNTA MUDOU, E NÃO SÓ A RESPOSTA.** Era um interruptor — ligado ou
desligado — e virou **alcance**: `NINGUEM`, `ADMIN`, `TODOS`. Por isso este
arquivo substitui o `test_modulo_desligado.py`: o nome dizia o que ele já não
guarda.

O QUE ESTES TESTES GUARDAM
      - **de fábrica o Protesto é do oficial**, e não de todos nem de ninguém;
      - **a guarda é no servidor**, e sabe quem está batendo: tirar o link e
        deixar a rota de pé esconde a porta sem trancá-la;
      - **o ADMIN nunca se tranca do lado de fora** — quem muda o alcance é
        ele, e `NINGUEM` não o alcança;
      - **a frase muda com o alcance**: «fechado para todos» e «só para o
        oficial» pedem providências diferentes de quem lê;
      - **a marca da versão anterior não se perde** — quem já tinha ligado o
        módulo na 3.6.61 continua com ele aberto;
      - **o dado nunca sai do banco**, em nenhum dos três alcances.
"""
from __future__ import annotations

import contextlib
import glob
import os
import re
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import modulos as MOD
import modulos_ligados as MODLIG

DADOS = str(Path(tempfile.gettempdir()) /
            ("test_mod_alcance_" + os.environ.get("PYTEST_XDIST_WORKER", "solo")))

SEM_CONFIG = lambda chave, padrao=None: padrao


def config(**linhas):
    """Um `get_setting` de mentira, com as linhas que se quer."""
    return lambda chave, padrao=None: linhas.get(chave, padrao)


@pytest.fixture(scope="module")
def app():
    from app import create_app
    Path(DADOS).mkdir(parents=True, exist_ok=True)
    return create_app({"DATA_DIR": DADOS})


@pytest.fixture(scope="module")
def banco(app):
    from database import Database
    return Database(Path(glob.glob(f"{DADOS}/*.sqlite3")[0]))


def _entrar(app, banco, usuario, papel):
    with contextlib.suppress(Exception):
        banco.create_user(usuario, "Operador", "Senha#12345", papel)
    c = app.test_client()
    pega = lambda h: re.search(r'name="csrf_token"[^>]*value="([^"]+)"', h).group(1)
    c.post("/login", data={"username": usuario, "password": "Senha#12345",
                           "csrf_token": pega(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return c


@pytest.fixture(scope="module")
def oficial(app, banco):
    return _entrar(app, banco, "alc_adm", "ADMIN")


@pytest.fixture(scope="module")
def escrevente(app, banco):
    return _entrar(app, banco, "alc_usr", "USER")


@pytest.fixture
def de_fabrica(banco):
    """Sem linha em `settings` — que é como a atualização chega ao servidor."""
    with banco.connect() as con:
        con.execute("DELETE FROM settings WHERE key IN "
                    "('modulo_protesto_alcance','modulo_protesto_ligado')")
        con.commit()
    yield


# ------------------------------------------------- a regra, sem tela


def test_de_fabrica_o_protesto_e_do_oficial():
    """Nem de todos nem de ninguém: o alcance do meio, que ele pediu."""
    assert MODLIG.alcance(SEM_CONFIG, "PROTESTO") == MODLIG.ADMIN
    assert MODLIG.pode_entrar(SEM_CONFIG, "PROTESTO", "ADMIN") is True
    assert MODLIG.pode_entrar(SEM_CONFIG, "PROTESTO", "USER") is False
    assert MODLIG.pode_entrar(SEM_CONFIG, "PROTESTO", None) is False


def test_o_alcance_TODOS_abre_para_o_balcao():
    c = config(modulo_protesto_alcance="TODOS")
    assert MODLIG.pode_entrar(c, "PROTESTO", "USER") is True
    # Só o Protesto: a Apostila de Haia (LG03) tem alcance próprio, e de
    # fábrica fechado — abrir um não pode abrir o outro. O sandbox cobra
    # `escondidos == frozenset()`, que é a casa sem a Apostila; aqui o menu
    # esconde dela, e de mais nada.
    assert "PROTESTO" not in MODLIG.escondidos(c, "USER")
    assert MODLIG.escondidos(c, "USER") == frozenset({"APOSTILA"})


def test_o_alcance_NINGUEM_fecha_ate_para_o_oficial():
    """É o único em que ele também não entra — e por isso a tela de
    configurações continua sendo dele: lá é que se desfaz."""
    c = config(modulo_protesto_alcance="NINGUEM")
    assert MODLIG.pode_entrar(c, "PROTESTO", "ADMIN") is False
    assert MODLIG.pode_entrar(c, "PROTESTO", "USER") is False


def test_o_gerente_nao_entra_no_alcance_do_oficial():
    """«Para o administrador» foi o que ele escreveu. Ampliar por conta
    própria seria decidir por ele — e é uma palavra em `PAPEIS_DO_ALCANCE` se
    ele quiser o gerente junto."""
    assert MODLIG.pode_entrar(SEM_CONFIG, "PROTESTO", "MANAGER") is False


def test_os_outros_sete_modulos_sao_de_todos():
    """Fechar um não pode fechar os vizinhos."""
    for m in MOD.MODULOS:
        if m["chave"] != "PROTESTO":
            assert MODLIG.alcance(SEM_CONFIG, m["chave"]) == MODLIG.TODOS
            assert MODLIG.pode_entrar(SEM_CONFIG, m["chave"], "USER") is True


def test_valor_estranho_na_configuracao_cai_no_de_fabrica():
    """Linha escrita à mão, ou de uma versão futura, não pode abrir o módulo
    por acidente."""
    assert MODLIG.alcance(config(modulo_protesto_alcance="SEI_LA"),
                          "PROTESTO") == MODLIG.ADMIN


def test_a_marca_da_versao_anterior_nao_se_perde():
    """**A 3.6.61 gravava `modulo_protesto_ligado`.** Se o oficial já a aplicou
    e marcou a caixa, aquele `1` quer dizer «abre para todos» — e a atualização
    desfazer a decisão dele seria a tela apagando o que ele decidiu."""
    assert MODLIG.alcance(config(modulo_protesto_ligado="1"),
                          "PROTESTO") == MODLIG.TODOS
    assert MODLIG.alcance(config(modulo_protesto_ligado="0"),
                          "PROTESTO") == MODLIG.NINGUEM
    # E a chave nova manda sobre a antiga.
    assert MODLIG.alcance(config(modulo_protesto_ligado="1",
                                 modulo_protesto_alcance="ADMIN"),
                          "PROTESTO") == MODLIG.ADMIN


def test_a_regra_de_qual_modulo_e_a_de_modulos_py():
    """UMA RÉGUA, E NÃO DUAS PARECIDAS — a lição da `normalizar_nome`."""
    for endpoint in ("protesto_titulos", "protesto_painel", "protesto_cenprot"):
        assert MOD.modulo_da_tela(endpoint) == "PROTESTO"
        assert MODLIG.pode_entrar(SEM_CONFIG, MOD.modulo_da_tela(endpoint),
                                  "USER") is False
    for endpoint in ("ri_matriculas", "notas_cartoes", "rcpn_assentos",
                     "caixa", "nucleo_livros"):
        assert MODLIG.pode_entrar(SEM_CONFIG, MOD.modulo_da_tela(endpoint),
                                  "USER") is True


def test_a_frase_muda_com_o_alcance():
    """«Fechado para todos» e «só do oficial» pedem providências diferentes de
    quem lê — a segunda diz a quem pedir."""
    fechado = MODLIG.motivo("PROTESTO", MODLIG.NINGUEM)
    so_dele = MODLIG.motivo("PROTESTO", MODLIG.ADMIN)
    assert fechado != so_dele
    assert "continuam guardados" in fechado
    assert "apenas para o oficial" in so_dele
    assert "todos os usuários" in so_dele


# ------------------------------------------------- e na tela


def test_o_oficial_entra_e_ve_o_grupo(oficial, de_fabrica):
    assert oficial.get("/protesto").status_code == 200
    html = oficial.get("/").get_data(as_text=True)
    nav = html[html.find("<nav>"):html.find("</nav>")]
    assert "<summary>Protesto</summary>" in nav


def test_o_escrevente_nao_entra_e_nao_ve(escrevente, de_fabrica):
    """**A GUARDA É NO SERVIDOR.** Este é o teste que impede o favorito de
    entrar — o menu some por educação, a rota recusa por dever."""
    html = escrevente.get("/").get_data(as_text=True)
    nav = html[html.find("<nav>"):html.find("</nav>")]
    assert "<summary>Protesto</summary>" not in nav
    r = escrevente.get("/protesto", follow_redirects=True)
    assert r.status_code == 200
    corpo = r.get_data(as_text=True)
    assert "apenas para o oficial" in corpo
    assert "Títulos protestados" not in corpo


def test_liberar_para_todos_abre_para_o_escrevente(escrevente, banco):
    """O botão que ele pediu, provado do lado de quem ele libera."""
    banco.set_settings({"modulo_protesto_alcance": "TODOS"})
    try:
        assert escrevente.get("/protesto").status_code == 200
        html = escrevente.get("/").get_data(as_text=True)
        nav = html[html.find("<nav>"):html.find("</nav>")]
        assert "<summary>Protesto</summary>" in nav
    finally:
        with banco.connect() as con:
            con.execute("DELETE FROM settings "
                        "WHERE key='modulo_protesto_alcance'")
            con.commit()


def test_a_tela_de_configuracoes_oferece_os_tres(oficial):
    html = oficial.get("/configuracoes").get_data(as_text=True)
    assert 'name="modulo_protesto_alcance"' in html
    for valor in ("ADMIN", "TODOS", "NINGUEM"):
        assert f'value="{valor}"' in html


def test_fechar_para_todos_nao_apaga_o_que_estava_lavrado(banco):
    """FECHAR MÓDULO NUNCA APAGA ATO — ato lavrado é livro."""
    banco.set_settings({"modulo_protesto_alcance": "NINGUEM"})
    try:
        with banco.connect() as con:
            for tabela in ("pt_titulos", "pt_atos", "pt_instrumentos"):
                con.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()
    finally:
        with banco.connect() as con:
            con.execute("DELETE FROM settings "
                        "WHERE key='modulo_protesto_alcance'")
            con.commit()


# ------------------------------------------- a função que fica de fora
#
# 21/10/2026 — ordem do oficial, ao abrir o Protesto inteiro às escreventes:
# «[NOME] eh auxiliar, nao era pra poder». O auxiliar tem o mesmo papel
# (USER) da escrevente; quem separa é a função cadastrada.


def test_a_auxiliar_fica_de_fora_mesmo_com_o_protesto_aberto_a_todos():
    ler = config(modulo_protesto_alcance="TODOS")
    assert MODLIG.pode_entrar(ler, "PROTESTO", "USER", "Escrevente Autorizada")
    assert not MODLIG.pode_entrar(ler, "PROTESTO", "USER", "Auxiliar")
    assert not MODLIG.pode_entrar(ler, "PROTESTO", "MANAGER", "AUXILIAR")
    assert "PROTESTO" in MODLIG.escondidos(ler, "USER", "auxiliar")


def test_a_auxiliar_com_acento_ou_com_complemento_tambem_fica_de_fora():
    """«Auxiliar», «AUXILIAR», «auxiliar» e «Auxiliar de cartório» são a mesma
    função: a régua tira o acento e a caixa e olha o começo."""
    ler = config(modulo_protesto_alcance="TODOS")
    for funcao in ("Áuxiliar", " auxiliar ", "Auxiliar de cartório"):
        assert not MODLIG.pode_entrar(ler, "PROTESTO", "USER", funcao), funcao
    # E a escrevente que tem «auxiliar» no meio do nome da função não cai.
    assert MODLIG.pode_entrar(ler, "PROTESTO", "USER", "Escrevente auxiliar")


def test_o_admin_auxiliar_nunca_fica_de_fora():
    """A conta do analista de sistemas é ADMIN com função de auxiliar."""
    ler = config(modulo_protesto_alcance="TODOS")
    assert MODLIG.pode_entrar(ler, "PROTESTO", "ADMIN", "Auxiliar")
    assert "PROTESTO" not in MODLIG.escondidos(ler, "ADMIN", "Auxiliar")


def test_funcao_em_branco_nao_fecha_e_os_outros_modulos_nao_mudam():
    ler = config(modulo_protesto_alcance="TODOS")
    assert MODLIG.pode_entrar(ler, "PROTESTO", "USER", None)
    assert MODLIG.pode_entrar(ler, "PROTESTO", "USER", "")
    for m in MOD.MODULOS:
        if m["chave"] != "PROTESTO":
            assert MODLIG.pode_entrar(ler, m["chave"], "USER", "Auxiliar")


def test_a_funcao_nao_abre_o_que_o_alcance_fecha():
    """A guarda da função só TIRA: com o Protesto do oficial, a escrevente
    continua de fora, com a frase do alcance, e não a da função."""
    assert not MODLIG.pode_entrar(SEM_CONFIG, "PROTESTO", "USER", "Escrevente")
    assert "apenas para o oficial" in MODLIG.motivo(
        "PROTESTO", MODLIG.ADMIN, "USER", "Escrevente")


def test_a_frase_diz_por_que_a_auxiliar_nao_entra():
    frase = MODLIG.motivo("PROTESTO", "TODOS", "USER", "Auxiliar")
    assert "auxiliar" in frase
    assert "oficial" in frase


def test_auxiliar_de_cartorio_em_qualquer_caixa_e_com_espaco_fica_de_fora():
    """Revisão do LH06 (conferida no LH08): a régua é «a função COMEÇA por
    AUXILIAR», depois de tirar acento, caixa e o branco das pontas — tabulação
    e espaço duro inclusive, que é o que sobra de cadastro colado de planilha.
    Por isso «AUXILIAR DE CARTÓRIO» fica de fora, e com ela tudo o que começa
    pela palavra («Auxiliares», «Auxiliar administrativo»). A regra é a da
    ordem do oficial e não mudou: este teste só a deixa escrita."""
    ler = config(modulo_protesto_alcance="TODOS")
    for funcao in ("AUXILIAR DE CARTÓRIO", "  auxiliar de cartório  ",
                   "aUxIlIaR", "\tAUXILIAR\n", " Auxiliar",
                   "Auxiliares", "Auxiliar administrativo"):
        assert MODLIG.fora_pela_funcao("PROTESTO", "USER", funcao), repr(funcao)
        assert not MODLIG.pode_entrar(ler, "PROTESTO", "USER", funcao), repr(funcao)
        assert "PROTESTO" in MODLIG.escondidos(ler, "USER", funcao), repr(funcao)
        assert "a função de auxiliar não o opera" in MODLIG.motivo(
            "PROTESTO", "TODOS", "USER", funcao), repr(funcao)
    # A palavra no meio não fecha: é a escrevente, e não a auxiliar.
    for funcao in ("Escrevente auxiliar", "ESCREVENTE AUXILIAR DE CARTÓRIO"):
        assert MODLIG.pode_entrar(ler, "PROTESTO", "USER", funcao), repr(funcao)


def _de_funcao(app, banco, usuario, papel, funcao):
    """Entra com a conta e grava a função dela, como a tela Usuários grava."""
    cliente = _entrar(app, banco, usuario, papel)
    with banco.connect() as con:
        con.execute("UPDATE users SET funcao=? WHERE username=?",
                    (funcao, usuario))
        con.commit()
    return cliente


def _token_da_casa(cliente) -> str:
    html = cliente.get("/").get_data(as_text=True)
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


@pytest.fixture
def aberto_a_todos(banco):
    banco.set_settings({"modulo_protesto_alcance": "TODOS"})
    yield
    with banco.connect() as con:
        con.execute("DELETE FROM settings WHERE key='modulo_protesto_alcance'")
        con.commit()


def test_a_auxiliar_nao_entra_pela_tela_nem_pelo_favorito(app, banco,
                                                         aberto_a_todos):
    aux = _de_funcao(app, banco, "alc_aux", "USER", "Auxiliar")
    html = aux.get("/").get_data(as_text=True)
    nav = html[html.find("<nav>"):html.find("</nav>")]
    assert "<summary>Protesto</summary>" not in nav
    for endereco in ("/protesto", "/protesto/cra/api", "/protesto/cenprot/pendencias"):
        corpo = aux.get(endereco, follow_redirects=True).get_data(as_text=True)
        assert "a função de auxiliar não o opera" in corpo, endereco


@pytest.mark.parametrize("funcao", ["  AUXILIAR DE CARTÓRIO ", "auxiliar"])
def test_a_auxiliar_cadastrada_em_maiusculas_ou_com_espaco_nao_entra_pela_tela(
        app, banco, aberto_a_todos, funcao):
    """A função vem da tela Usuários como foi digitada: a guarda do
    `before_request` a lê do banco a cada pedido e a compara pela mesma régua."""
    aux = _de_funcao(app, banco, "alc_aux_caixa", "USER", funcao)
    r = aux.get("/protesto")
    assert r.status_code == 302, (funcao, r.status_code)
    assert urlsplit(r.headers["Location"]).path == "/", r.headers["Location"]
    corpo = aux.get("/").get_data(as_text=True)
    assert "a função de auxiliar não o opera" in corpo, funcao
    nav = corpo[corpo.find("<nav>"):corpo.find("</nav>")]
    assert "<summary>Protesto</summary>" not in nav


# AS ROTAS QUE ESCREVEM NA CENTRAL OU ASSINAM COM O A3 — abertas ao USER em
# 21/10/2026 (eram de ADMIN/MANAGER, e assinar era só do ADMIN). A auxiliar
# bate na guarda da função ANTES de chegar a elas; a escrevente chega.
ROTAS_DA_ORDEM = (
    "/protesto/instrumentos/987654/assinar",
    "/protesto/cenprot/pendencias/enviar",
    "/protesto/cenprot/emolumentos/enviar",
    "/protesto/cenprot-xml/gerar",
    "/protesto/cenprot-xml/apresentantes",
    "/protesto/cenprot-xml/apresentantes/acervo",
    "/protesto/avisos/987654/resolve",
    "/protesto/avisos/987654/base-cenprot/consultar",
    "/protesto/avisos/987654/base-cenprot/cadastrar",
    "/protesto/resolve/enviar",
)


@pytest.mark.parametrize("endereco", ROTAS_DA_ORDEM)
def test_a_auxiliar_nao_assina_instrumento_nem_envia_a_cenprot(
        app, banco, aberto_a_todos, endereco):
    aux = _de_funcao(app, banco, "alc_aux", "USER", "Auxiliar")
    r = aux.post(endereco, data={"csrf_token": _token_da_casa(aux)})
    # De volta ao início, pela guarda do `before_request` — e não pela rota.
    assert r.status_code == 302, (endereco, r.status_code)
    assert urlsplit(r.headers["Location"]).path == "/", r.headers["Location"]
    corpo = aux.get("/").get_data(as_text=True)
    assert "a função de auxiliar não o opera" in corpo, endereco


@pytest.mark.parametrize("papel,funcao", [("USER", "Escrevente Autorizada"),
                                          ("USER", None),
                                          ("ADMIN", "Auxiliar")])
@pytest.mark.parametrize("endereco", ROTAS_DA_ORDEM)
def test_a_escrevente_e_o_admin_auxiliar_chegam_as_rotas_da_ordem(
        app, banco, aberto_a_todos, endereco, papel, funcao):
    """Chegar é passar pelas duas guardas — a do módulo e a do papel: o que a
    rota responde depois (404 do instrumento que não existe, a frase da
    Central sem credencial) já é dela. Antes de 21/10/2026, 403."""
    usuario = f"alc_{papel.lower()}_{(funcao or 'sem').split()[0].lower()}"
    cliente = _de_funcao(app, banco, usuario, papel, funcao)
    r = cliente.post(endereco, data={"csrf_token": _token_da_casa(cliente)})
    assert r.status_code != 403, (endereco, papel, funcao)
    if r.status_code == 302:     # a rota manda de volta à tela dela, não ao início
        assert urlsplit(r.headers["Location"]).path != "/", r.headers["Location"]
    corpo = cliente.get("/").get_data(as_text=True)
    assert "a função de auxiliar não o opera" not in corpo


def test_o_instrumento_a_assinar_chega_a_rota_so_para_quem_nao_e_auxiliar(
        app, banco, aberto_a_todos):
    """O 404 é a própria rota dizendo que o instrumento 987654 não existe —
    prova de que a escrevente passou pelas guardas. A auxiliar volta ao
    início com a frase, sem a rota abrir nada."""
    endereco = "/protesto/instrumentos/987654/assinar"
    escrevente = _de_funcao(app, banco, "alc_esc", "USER", "Escrevente")
    assert escrevente.post(endereco, data={
        "csrf_token": _token_da_casa(escrevente)}).status_code == 404
    admin_aux = _de_funcao(app, banco, "alc_adm_aux", "ADMIN", "Auxiliar")
    assert admin_aux.post(endereco, data={
        "csrf_token": _token_da_casa(admin_aux)}).status_code == 404
    aux = _de_funcao(app, banco, "alc_aux", "USER", "Auxiliar")
    assert aux.post(endereco, data={
        "csrf_token": _token_da_casa(aux)}).status_code == 302


def test_a_auxiliar_nao_baixa_pelo_endereco_o_anexo_do_protesto(
        app, banco, aberto_a_todos, tmp_path):
    """A porta dos fundos da mesma tela: o comprovante do aviso se baixa por
    `/arquivo/<id>`, que é do Administrativo. Quem não abre a tela dos avisos
    não baixa o que ela oferece."""
    aux = _de_funcao(app, banco, "alc_aux", "USER", "Auxiliar")
    escrevente = _de_funcao(app, banco, "alc_esc", "USER", "Escrevente")
    arquivo = tmp_path / "comprovante.pdf"
    arquivo.write_bytes(b"%PDF-1.4 comprovante de teste")
    with banco.connect() as con:
        uid = con.execute("SELECT id FROM users WHERE username='alc_esc'"
                          ).fetchone()["id"]
    anexo = banco.add_attachment("PT_AVISO", 987654, {
        "original_name": "comprovante.pdf", "stored_name": "comprovante.pdf",
        "stored_path": str(arquivo), "sha256": "0" * 64,
        "size_bytes": arquivo.stat().st_size}, uid)
    try:
        assert escrevente.get(f"/arquivo/{anexo}").status_code == 200
        assert aux.get(f"/arquivo/{anexo}").status_code == 404
        assert aux.get(f"/arquivo/{anexo}/ver").status_code == 404
    finally:
        banco.delete_attachment(anexo)
