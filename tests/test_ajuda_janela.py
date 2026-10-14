"""
Testes da JANELA DA AJUDA em toda tela, e da lista de problemas.

POR QUE TELA, E NAO SO DOMINIO
    "Buraco de tela nao aparece em teste de dominio" e a licao que ja se
    repetiu cinco vezes neste projeto. E aqui ela vale duas vezes: o pedido era
    que a ajuda existisse **em todas as telas e modulos** — e isso nao se prova
    olhando uma funcao. Prova-se varrendo as telas, como o teste do menu faz.

O QUE ELES CONFEREM
      - A JANELA APARECE EM TODA TELA, varrida uma por uma;
      - ELA APARECE TAMBEM PARA QUEM NAO PODE CONSULTAR, so que sem o
        formulario de perguntar: avisar problema nao gasta e nao manda nada
        para fora, e quem topa com o defeito e o balcao;
      - SEM JAVASCRIPT ela continua sendo um link para a tela inteira, ja com a
        tela de origem no endereco;
      - A TELA QUE ESTOURA VIRA PROBLEMA sozinha, e o escrevente ve uma pagina
        que diz o que fazer, e nao um erro cru;
      - O MAPA DESTA INSTALACAO VAI JUNTO da pergunta — e o que separa uma
        resposta sobre "cartorio" em tese de uma sobre esta casa;
      - O RELATORIO baixa, fica em disco e marca o que foi mandado;
      - A LISTA DE PROBLEMAS e de quem responde pela serventia.
"""
from __future__ import annotations

import glob
import re
import sqlite3
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.lento  # varre todas as rotas/telas; fica na suite completa

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

SENHA = "Senha#12345"

# As rotas que nao sao tela — a mesma lista que o teste do menu usa, pelo
# mesmo motivo: elas devolvem arquivo ou redirecionam, e nao tem `<nav>`.
NAO_SAO_TELA = {"static", "login", "logout", "setup", "health"}


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _sessao(tmp_path, papel: str = "ADMIN", com_rota_que_estoura: bool = False):
    from app import create_app
    from database import Database

    dados = tmp_path / "dados"
    dados.mkdir(parents=True)
    app = create_app({"DATA_DIR": str(dados)})

    if com_rota_que_estoura:
        # A ROTA TEM DE ENTRAR ANTES DA PRIMEIRA REQUISICAO — depois dela o
        # Flask nao aceita mais. Ela existe para provar o que acontece quando
        # QUALQUER tela estoura, sem precisar quebrar uma tela de verdade.
        def estoura():
            {}["numero_do_titulo"]                     # noqa: B018
        app.add_url_rule("/tela-que-estoura", "tela_que_estoura", estoura)

    banco = Path(glob.glob(f"{dados}/*.sqlite3")[0])
    Database(banco).create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS",
                                SENHA, papel)
    c = app.test_client()
    c.post("/login",
           data={"username": "tabeliao", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {"app": app, "c": c, "banco": banco, "dados": dados}


@pytest.fixture()
def admin(tmp_path):
    return _sessao(tmp_path, "ADMIN")


def _con(s) -> sqlite3.Connection:
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    return con


# ------------------------------------------- a janela existe em toda tela


def test_a_janela_aparece_em_TODA_tela(admin):
    """O pedido era «em todas as telas e modulos», e isso se varre.

    Ligada tela a tela, a proxima que alguem criasse nasceria sem ajuda — e
    sem aviso nenhum de que nasceu. Por isso ela mora no `base.html`, e por
    isso este teste percorre as telas em vez de conferir uma lista.
    """
    vistas = 0
    for regra in sorted(admin["app"].url_map.iter_rules(), key=lambda r: str(r)):
        if regra.endpoint in NAO_SAO_TELA or "<" in str(regra) \
                or "GET" not in (regra.methods or set()):
            continue
        r = admin["c"].get(str(regra))
        if r.status_code != 200 or not r.mimetype.startswith("text/html"):
            continue
        html = r.get_data(as_text=True)
        if "<nav>" not in html:
            continue
        assert "ajuda-caixa" in html, f"{regra} ficou sem a janela da ajuda"
        vistas += 1
    assert vistas > 15, f"conferi só {vistas} telas — o teste não vê o sistema"


def test_a_janela_aparece_para_quem_NAO_pode_consultar(tmp_path):
    """Avisar problema nao gasta e nao manda nada para fora.

    Quem topa com o defeito e o balcao, e o balcao nao pode ficar sem poder
    avisar por causa de uma regra que existe para outra coisa.
    """
    s = _sessao(tmp_path, "USER")
    html = s["c"].get("/caixa").get_data(as_text=True)
    assert "ajuda-caixa" in html
    assert "Avisar um problema desta tela" in html
    # ... mas sem o formulario de perguntar, que gasta e manda dado para fora.
    assert "data-ajuda-perguntar" not in html
    assert "ainda não está liberado para o seu perfil" in html


def test_sem_javascript_o_botao_e_um_link_para_a_tela_inteira(admin):
    """O sistema roda em rede local, e o que precisa de script e o que some."""
    html = admin["c"].get("/caixa").get_data(as_text=True)
    assert 'href="/ajuda?onde=caixa"' in html


def test_a_tela_inteira_chega_sabendo_de_onde_a_duvida_veio(admin):
    """Campo que o operador tem de preencher e campo que fica vazio."""
    html = admin["c"].get("/ajuda?onde=protesto_titulos").get_data(as_text=True)
    assert 'name="onde" value="protesto_titulos"' in html


def test_abrir_telas_nao_grava_problema_nenhum(admin):
    """GET nao abre transacao de escrita — nem para a janela."""
    for url in ("/", "/caixa", "/notas", "/registro-imoveis"):
        admin["c"].get(url)
    con = _con(admin)
    assert con.execute(
        "SELECT COUNT(*) c FROM aj_problemas").fetchone()["c"] == 0
    con.close()


# ------------------------------------------------ avisar um problema


def test_o_escrevente_avisa_um_problema(tmp_path):
    """Defeito que NAO estoura o programa — o botao que nao faz nada — e o que
    maquina nenhuma percebe sozinha."""
    s = _sessao(tmp_path, "USER")
    html = s["c"].get("/caixa").get_data(as_text=True)
    r = s["c"].post("/ajuda/problema",
                    data={"csrf_token": _token(html), "formato": "json",
                          "titulo": "o botão de lançar não faz nada",
                          "detalhe": "cliquei três vezes", "onde": "caixa",
                          "caminho": "/caixa"})
    assert r.get_json()["ok"] is True
    con = _con(s)
    linha = con.execute("SELECT * FROM aj_problemas").fetchone()
    assert linha["origem"] == "RELATADO"
    assert linha["onde"] == "caixa"
    assert linha["ultimo_usuario"] == "MARIO EXEMPLO DOS SANTOS"
    con.close()


def test_sem_javascript_avisar_problema_volta_para_a_tela_de_onde_saiu(tmp_path):
    s = _sessao(tmp_path, "USER")
    html = s["c"].get("/caixa").get_data(as_text=True)
    r = s["c"].post("/ajuda/problema",
                    data={"csrf_token": _token(html),
                          "titulo": "o botão não faz nada",
                          "onde": "caixa", "caminho": "/caixa"})
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/caixa")


def test_o_endereco_de_volta_nao_sai_da_casa(tmp_path):
    """Redirecionar para o que o navegador disser e porta para levar o operador
    autenticado a um endereco estranho."""
    s = _sessao(tmp_path, "USER")
    html = s["c"].get("/caixa").get_data(as_text=True)
    r = s["c"].post("/ajuda/problema",
                    data={"csrf_token": _token(html), "titulo": "algo",
                          "caminho": "//exemplo.invalido/roubar"})
    assert "exemplo.invalido" not in r.headers["Location"]


def test_a_marca_aparece_na_tela_onde_o_problema_aconteceu(admin):
    """Quem topa hoje com o defeito que outro topou ontem merece saber que nao
    e ele que esta fazendo errado."""
    html = admin["c"].get("/caixa").get_data(as_text=True)
    admin["c"].post("/ajuda/problema",
                    data={"csrf_token": _token(html), "formato": "json",
                          "titulo": "o botão não faz nada", "onde": "caixa",
                          "caminho": "/caixa"})
    no_caixa = admin["c"].get("/caixa").get_data(as_text=True)
    assert "ajuda-marca" in no_caixa
    assert "Já houve problema nesta tela" in no_caixa
    # E NAO nas outras: aviso que aparece em toda parte e aviso que ninguem le.
    assert "ajuda-marca" not in admin["c"].get("/notas").get_data(as_text=True)


# ------------------------------------------ a tela que estoura se anota


def test_a_tela_que_estoura_vira_problema_sozinha(tmp_path):
    """Ate aqui, o unico registro do defeito era a lembranca de quem estava no
    balcao — que em dia de movimento e o que se perde primeiro."""
    s = _sessao(tmp_path, "ADMIN", com_rota_que_estoura=True)
    r = s["c"].get("/tela-que-estoura")
    assert r.status_code == 500
    texto = r.get_data(as_text=True)
    # O ESCREVENTE LE UMA PAGINA QUE DIZ O QUE FAZER, e nao um erro cru.
    assert "NADA foi gravado pela metade" in texto
    # O JARGAO NAO CHEGA AO BALCAO. `KeyError` na cara de quem acabou de levar
    # um erro e jargao de programador em cima de susto; ele fica no titulo do
    # problema, que e de quem conserta.
    assert "KeyError" not in texto
    assert "O sistema deu erro nesta tela" in texto

    con = _con(s)
    linha = con.execute("SELECT * FROM aj_problemas").fetchone()
    assert linha["origem"] == "ERRO_DE_TELA"
    assert linha["onde"] == "tela_que_estoura"
    assert linha["caminho"] == "/tela-que-estoura"
    assert "KeyError" in linha["titulo"]
    assert linha["ultimo_usuario"] == "tabeliao"
    con.close()


def test_a_mesma_tela_estourando_de_novo_nao_vira_linha_nova(tmp_path):
    s = _sessao(tmp_path, "ADMIN", com_rota_que_estoura=True)
    s["c"].get("/tela-que-estoura")
    s["c"].get("/tela-que-estoura")
    s["c"].get("/tela-que-estoura")
    con = _con(s)
    linhas = con.execute("SELECT * FROM aj_problemas").fetchall()
    assert len(linhas) == 1
    assert linhas[0]["vezes"] == 3
    con.close()


# --------------------------------------------- o mapa vai junto da pergunta


def test_o_mapa_desta_instalacao_vai_junto_da_pergunta(admin, monkeypatch):
    """Sem ele a resposta fala do cartorio em tese, e nao deste.

    E ninguem confere isso olhando a tela: o que sai fica em `enviado`, e e
    ali que este teste procura.
    """
    import agente_provedores as PROV

    recebido = {}

    # A ESPIÃ OLHA O `sistema`, que é a instrução sanitizada — o mapa da
    # instalação vai dentro dela. Antes espiava o `pacote`; a montagem mudou de
    # transporte, e o que se confere continua sendo o mesmo: o que SAI.
    def falso(pasta, *, sistema, conversa, **resto):
        recebido["instrucao"] = sistema
        return {"texto": "A tela é essa aí.", "modelo": "claude-sonnet-5",
                "entrada": 10, "saida": 5}

    monkeypatch.setattr(PROV, "conversar", falso)
    html = admin["c"].get("/caixa").get_data(as_text=True)
    r = admin["c"].post("/ajuda/janela",
                        data={"csrf_token": _token(html), "formato": "json",
                              "pergunta": "onde lanço um depósito prévio?",
                              "assunto": "USO", "onde": "caixa"})
    assert r.get_json()["ok"] is True
    assert "O MAPA DESTA INSTALAÇÃO" in recebido["instrucao"]
    assert "caixa_web.py" in recebido["instrucao"]
    # **A FATIA DA TELA VAI INTEIRA**, e é ela que responde «onde fica isto»:
    # o depósito prévio aparece entre as telas irmãs da tela em que o balcão
    # estava. Por isso a pergunta sai da tela do caixa, e não de uma tela
    # qualquer — de onde o mapa teria de ser procurado na lista inteira.
    assert "Depósito prévio" in recebido["instrucao"]

    # **A LINHA DO MENU, ESSA, PODE ESTAR FORA — E ISSO PASSOU A SER
    # CONFERIDO COMO REGRA, E NÃO COMO TEXTO.** Medido em 14/09/2026: o mapa
    # ficou em 8.962 dos 9.000 caracteres do teto e o corte caiu entre
    # «Protocolos parados» e «Depósito prévio» — a entrada do depósito é a
    # 108ª das 141 do menu. Não é defeito do mapa: o corte é dele, é por
    # tamanho (é a conta do mês) e vem DITO no próprio texto.
    #
    # O defeito que este teste guarda é o outro, e é o que continua valendo:
    # o endereço sumir **em silêncio**. O mapa que encolhe calado faz a ajuda
    # responder que a tela não existe — porque a instrução diz, com todas as
    # letras, que tela que não está ali não existe.
    import ajuda_mapa as MAPA

    if "Depósito prévio — /caixa/depositos" not in recebido["instrucao"]:
        assert MAPA.AVISO_DO_CORTE in recebido["instrucao"], (
            "o endereço do depósito prévio não está no mapa e o mapa não diz "
            "que cortou — é assim que a ajuda volta a inventar nome de tela, "
            "e isso não dá erro nenhum na tela")

    # E O QUE SAIU FICA GUARDADO INTEIRO — instrução e pergunta.
    con = _con(admin)
    linha = con.execute("SELECT * FROM aj_consultas").fetchone()
    assert "O MAPA DESTA INSTALAÇÃO" in linha["enviado"]
    assert "depósito prévio" in linha["enviado"]
    con.close()


def test_a_janela_recusa_quem_nao_pode_consultar(tmp_path):
    """A tela esconde o formulario por educacao; o dominio recusa por dever."""
    s = _sessao(tmp_path, "USER")
    html = s["c"].get("/caixa").get_data(as_text=True)
    r = s["c"].post("/ajuda/janela",
                    data={"csrf_token": _token(html), "formato": "json",
                          "pergunta": "uma dúvida", "onde": "caixa"})
    dados = r.get_json()
    assert dados["ok"] is False
    assert "liberada" in dados["erro"]
    con = _con(s)
    assert con.execute(
        "SELECT COUNT(*) c FROM aj_consultas").fetchone()["c"] == 0
    con.close()


# ------------------------------------------------- a lista de problemas


def test_a_gestao_da_lista_e_de_quem_responde_pela_serventia(tmp_path):
    """O CONTRATO MUDOU EM 23/09/2026 — relato #87, decisão do oficial.

    Até ali este teste cobrava que o balcão NÃO abrisse a lista (302/403). Agora
    ele abre e vê só os problemas que ele mesmo relatou (o resto está em
    `test_problema_87_meus_problemas.py`); o que continua sendo de quem responde
    pela serventia é a GESTÃO dela — conferir a casa e o relatório.
    """
    s = _sessao(tmp_path, "USER")
    lista = s["c"].get("/ajuda/problemas")
    assert lista.status_code == 200
    assert "Conferir a casa" not in lista.get_data(as_text=True)
    assert s["c"].post("/ajuda/problemas/conferir").status_code in (302, 400, 403)
    g = _sessao(tmp_path / "outro", "MANAGER")
    assert g["c"].get("/ajuda/problemas").status_code == 200
    assert "Conferir a casa" in g["c"].get("/ajuda/problemas").get_data(as_text=True)


def test_conferir_a_casa_anota_o_que_achou(admin):
    """Ela mede o que a casa ja sabe medir, e escreve o que encontrou."""
    con = _con(admin)
    con.execute("""INSERT INTO nu_implantacao(chave, tipo, titulo, motivo,
                       situacao, declarada_em)
                   VALUES ('numeracao:PT_PROTESTO','NUMERO','o próximo número',
                           'o acervo não tem coluna com ele','ABERTA',
                           '2026-08-26T10:00:00')""")
    con.commit()
    con.close()

    html = admin["c"].get("/ajuda/problemas").get_data(as_text=True)
    r = admin["c"].post("/ajuda/problemas/conferir",
                        data={"csrf_token": _token(html)},
                        follow_redirects=True)
    assert r.status_code == 200
    con = _con(admin)
    linha = con.execute(
        "SELECT * FROM aj_problemas WHERE origem='CONFERENCIA'").fetchone()
    assert linha is not None
    assert "esperando o oficial informar" in linha["titulo"]
    con.close()


def test_o_relatorio_baixa_fica_em_disco_e_marca_o_que_foi(admin):
    """O arquivo fica na maquina alem de baixar: e o que salva o dia em que o
    navegador perde o arquivo, ou em que quem baixou nao e quem vai mandar."""
    html = admin["c"].get("/caixa").get_data(as_text=True)
    admin["c"].post("/ajuda/problema",
                    data={"csrf_token": _token(html), "formato": "json",
                          "titulo": "o botão não faz nada", "onde": "caixa",
                          "caminho": "/caixa"})

    html = admin["c"].get("/ajuda/problemas").get_data(as_text=True)
    r = admin["c"].post("/ajuda/problemas/relatorio",
                        data={"csrf_token": _token(html)})
    assert r.status_code == 200
    texto = r.get_data(as_text=True)
    assert "# Problemas do CartorioGestao" in texto
    assert "o botão não faz nada" in texto
    assert "caixa_web.py" in texto          # onde se conserta

    guardados = list((admin["dados"] / "relatorios").glob("PROBLEMAS_*.md"))
    assert len(guardados) == 1

    con = _con(admin)
    assert con.execute(
        "SELECT situacao FROM aj_problemas").fetchone()["situacao"] == "RELATADO"
    relatorio = con.execute("SELECT * FROM aj_relatorios").fetchone()
    assert relatorio["quantos"] == 1
    assert len(relatorio["sha256"]) == 64
    con.close()


def test_marcar_resolvido_pede_a_linha_de_explicacao(admin):
    """Problema fechado sem explicacao volta a ser misterio na proxima vez."""
    html = admin["c"].get("/caixa").get_data(as_text=True)
    admin["c"].post("/ajuda/problema",
                    data={"csrf_token": _token(html), "formato": "json",
                          "titulo": "o botão não faz nada", "onde": "caixa"})
    html = admin["c"].get("/ajuda/problemas").get_data(as_text=True)
    assert "O que resolveu isto?" in html
    admin["c"].post("/ajuda/problemas/1/situacao",
                    data={"csrf_token": _token(html),
                          "nota": "era o cabo da impressora"},
                    follow_redirects=True)
    con = _con(admin)
    linha = con.execute("SELECT * FROM aj_problemas").fetchone()
    assert linha["situacao"] == "RESOLVIDO"
    assert "cabo" in linha["fechado_nota"]
    con.close()


def test_a_tela_de_problemas_diz_que_o_relatorio_sai_sanitizado(admin):
    """Quem manda dado para fora tem direito de saber o que esta mandando."""
    html = admin["c"].get("/ajuda/problemas").get_data(as_text=True)
    assert "segredos substituídos" in html


def test_a_consulta_de_quem_nao_pode_devolve_recusa_e_nao_erro(tmp_path):
    """UM DEFEITO QUE ESTE TRABALHO ACHOU, e que estava de pe.

    A rota que mostra uma consulta antiga recusava quem nao tem perfil com
    `redirect(url_for("index"))` — e nao existe rota chamada `index` neste
    sistema. O `url_for` estourava, e a recusa virava HTTP 500 na cara de quem
    ela recusava.

    Nenhum dos quinze testes daquele modulo passava por aqui: todos entravam
    como ADMIN, e o ADMIN nunca e recusado. E o caminho de recusa e justamente
    o que ninguem exercita a mao.
    """
    s = _sessao(tmp_path, "USER")
    r = s["c"].get("/ajuda/1", follow_redirects=False)
    assert r.status_code == 302, "a recusa tem de redirecionar, e nao estourar"
    assert r.headers["Location"].endswith("/")


# --------------------------------------------------------- o script


def test_o_script_da_janela_e_servido_e_esta_em_toda_tela(admin):
    """Ele mora no `base.html`, como a lupa — e pela mesma razao."""
    html = admin["c"].get("/caixa").get_data(as_text=True)
    assert "ajuda.js" in html
    assert admin["c"].get("/static/ajuda.js").status_code == 200


def test_a_resposta_de_fora_nao_desenha_na_tela():
    """O que volta da API e texto de FORA.

    Escrever texto de fora como HTML e deixar a resposta desenhar na tela do
    cartorio. Por isso ela entra por `textContent`, e nunca por `innerHTML`.
    """
    js = (RAIZ / "static" / "ajuda.js").read_text(encoding="utf-8")
    assert "textContent" in js
    assert "innerHTML" not in js


def test_a_janela_nao_depende_de_evento_escrito_no_html():
    """`onclick` no HTML e comportamento que ninguem acha ao procurar.

    E, mais que isso: com `onclick`, tirar o script deixaria um botao morto —
    em vez do link que continua levando a tela inteira.
    """
    janela = (RAIZ / "templates" / "_ajuda.html").read_text(encoding="utf-8")
    assert "onclick" not in janela
    assert "<script" not in janela


# ------------------------------------------------- as vistas da lista
# RELATO #82, de 17/09/2026 — «separar itens concluidos dos itens em aberto».
#
# A REGUA E' DO MODULO, e ja' esta' provada em `test_ajuda_problemas.py`. Aqui se
# prova o CAMINHO, que e' onde o defeito de tela mora: o botao leva a vista
# pedida, o numero ao lado dele e' o da vista, a palavra desconhecida cai na
# padrao COM A TELA DIZENDO QUAL VALE, e agir sobre um problema devolve para a
# vista de onde se agiu — e nao para a lista inteira.


def _abrir_problemas(admin, quais: list[tuple[str, str]]) -> dict[str, int]:
    """Abre problemas pela tela e devolve o id de cada um, pelo titulo."""
    c = admin["c"]
    token = _token(c.get("/caixa").get_data(as_text=True))
    for titulo, onde in quais:
        c.post("/ajuda/problema",
               data={"csrf_token": token, "formato": "json",
                     "titulo": titulo, "onde": onde})
    con = _con(admin)
    ids = {l["titulo"]: l["id"]
           for l in con.execute("SELECT id, titulo FROM aj_problemas")}
    con.close()
    return ids


def test_a_lista_separa_o_que_foi_resolvido(admin):
    """O relato #82, medido na producao: 65 resolvidos afogavam 17 abertos.

    Quem abria a tela para saber o que havia para fazer lia primeiro o que ja'
    estava feito.
    """
    c = admin["c"]
    ids = _abrir_problemas(admin, [("o numero sai errado", "caixa"),
                                   ("o botao nao faz nada", "notas")])
    html = c.get("/ajuda/problemas").get_data(as_text=True)
    c.post(f"/ajuda/problemas/{ids['o botao nao faz nada']}/situacao",
           data={"csrf_token": _token(html),
                 "nota": "era o cabo da impressora, que foi trocado"},
           follow_redirects=True)

    abertos = c.get("/ajuda/problemas").get_data(as_text=True)
    abertos = abertos.split("modo-botao ativo")[1]      # so' a tabela de baixo
    assert "o numero sai errado" in abertos
    assert "o botao nao faz nada" not in abertos

    resolvidos = c.get("/ajuda/problemas?vista=resolvidos").get_data(as_text=True)
    resolvidos = resolvidos.split("modo-botao ativo")[1]
    assert "o botao nao faz nada" in resolvidos
    assert "o numero sai errado" not in resolvidos

    todos = c.get("/ajuda/problemas?vista=todos").get_data(as_text=True)
    todos = todos.split("modo-botao ativo")[1]
    assert "o numero sai errado" in todos and "o botao nao faz nada" in todos


def test_o_numero_ao_lado_do_botao_e_o_da_vista(admin):
    """Contar a tabela inteira embaixo de «Em aberto» mente sobre o filtro.

    O numero ao lado do botao e' lido como «quantos tem ai' dentro» — e nao
    como «quantos existem no sistema».
    """
    c = admin["c"]
    ids = _abrir_problemas(admin, [("o numero sai errado", "caixa"),
                                   ("o botao nao faz nada", "notas")])
    html = c.get("/ajuda/problemas").get_data(as_text=True)
    c.post(f"/ajuda/problemas/{ids['o botao nao faz nada']}/situacao",
           data={"csrf_token": _token(html),
                 "nota": "era o cabo da impressora, que foi trocado"},
           follow_redirects=True)

    html = c.get("/ajuda/problemas?vista=todos").get_data(as_text=True)
    assert "Em aberto (1)" in html
    assert "Resolvidos (1)" in html
    assert "Todos (2)" in html


def test_a_vista_desconhecida_cai_na_padrao_e_a_tela_diz_qual_vale(admin):
    """Um favorito antigo, ou um `?vista=` digitado a mao, nao e' erro.

    Mas a queda TEM DE FICAR A' VISTA: sem o botao aceso, quem chegou por um
    endereco torto leria a lista como se fosse a que ele pediu.
    """
    html = admin["c"].get("/ajuda/problemas?vista=concluidos").get_data(as_text=True)
    assert "modo-botao ativo" in html, "nenhum botao aceso: a queda ficou muda"
    assert "Em aberto" in html.split("modo-botao ativo")[1][:200], (
        "caiu na padrao, mas a tela nao diz isso")
    assert "concluidos" not in html, "o valor pedido vazou para a tela"


def test_agir_sobre_um_problema_volta_para_a_mesma_vista(admin):
    """Quem estava nos resolvidos e abre um de volta nao pode cair nos abertos.

    Cair na lista inteira faria a pessoa perder o lugar onde estava — e o
    problema que ela acabou de mexer nao estaria mais ali para ela conferir.
    """
    c = admin["c"]
    ids = _abrir_problemas(admin, [("o botao nao faz nada", "notas")])
    pid = ids["o botao nao faz nada"]
    html = c.get("/ajuda/problemas?vista=resolvidos").get_data(as_text=True)

    r = c.post(f"/ajuda/problemas/{pid}/situacao",
               data={"csrf_token": _token(html), "vista": "resolvidos",
                     "nota": "era o cabo da impressora, que foi trocado"},
               follow_redirects=False)
    assert r.status_code == 302
    assert "vista=resolvidos" in r.headers["Location"], (
        "o clique saiu dos resolvidos e a volta foi para outra vista")

    # E o mesmo vale ao reabrir: quem estava nos resolvidos continua la'.
    html = c.get("/ajuda/problemas?vista=resolvidos").get_data(as_text=True)
    r = c.post(f"/ajuda/problemas/{pid}/situacao",
               data={"csrf_token": _token(html), "vista": "resolvidos",
                     "acao": "reabrir"},
               follow_redirects=False)
    assert r.status_code == 302
    assert "vista=resolvidos" in r.headers["Location"]


def test_fechar_sem_a_nota_volta_para_a_linha_e_nao_fecha(admin):
    """A recusa e' do modulo, mas quem mostra a frase e' a tela.

    E a frase tem de aparecer AO LADO da linha: no alto de oitenta problemas,
    quem levou a recusa nao saberia a qual deles ela se refere.
    """
    c = admin["c"]
    pid = _abrir_problemas(admin, [("o botao nao faz nada", "notas")])[
        "o botao nao faz nada"]
    html = c.get("/ajuda/problemas").get_data(as_text=True)

    r = c.post(f"/ajuda/problemas/{pid}/situacao",
               data={"csrf_token": _token(html), "nota": "ok"},
               follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["Location"].endswith(f"#problema-{pid}"), (
        "a recusa sem ancora larga quem clicou no alto da lista")

    con = _con(admin)
    linha = con.execute("SELECT situacao, fechado_nota FROM aj_problemas"
                        " WHERE id=?", (pid,)).fetchone()
    con.close()
    assert linha["situacao"] == "ABERTO", "a recusa fechou o que ela recusou"
    assert not linha["fechado_nota"]


def test_toda_acao_da_linha_leva_a_vista_junto():
    """São quatro formulários na tabela, e a vista tem de viajar em todos.

    Esquecer um deles faria justamente aquele botão jogar quem clicou na lista
    inteira — e o defeito só apareceria em quem usa aquele botão, que é a pior
    forma de um defeito de tela existir. O `diagnosticar` nem sequer é
    desenhado sem chave da API: por isso a conferência é na FONTE, e não na
    página montada.
    """
    fonte = (RAIZ / "templates" / "ajuda_problemas.html").read_text(encoding="utf-8")
    da_linha = [b for b in re.findall(r"<form\b.*?</form>", fonte,
                                      flags=re.DOTALL)
                if any(rota in b for rota in
                       ("ajuda_problema_nota_dev", "ajuda_problema_diagnosticar",
                        "ajuda_problema_situacao"))]
    assert len(da_linha) >= 4, "sumiu formulário de ação da linha"
    for bloco in da_linha:
        assert 'name="vista"' in bloco, (
            "este formulário não leva a vista: quem clicar nele cai na lista "
            "inteira em vez de voltar para onde estava")


def test_a_palavra_fora_do_vocabulario_nao_se_disfarca_de_resolvido(admin):
    """O #77 estava gravado «FECHADO», e a tela o pintava de verde.

    A cadeia de distintivos terminava num `else`, e o `else` recebia qualquer
    palavra — de modo que a lista afirmava «resolvido» sobre um estado que o
    sistema nao conhece. Agora ela aparece COMO E', e a tela diz que a palavra
    esta' fora do vocabulario.
    """
    c = admin["c"]
    pid = _abrir_problemas(admin, [("a que veio de fora", "antiga")])[
        "a que veio de fora"]
    con = _con(admin)
    con.execute("UPDATE aj_problemas SET situacao='FECHADO' WHERE id=?", (pid,))
    con.commit()
    con.close()

    html = c.get("/ajuda/problemas?vista=todos").get_data(as_text=True)
    assert "FECHADO" in html, "a lista escondeu a palavra que nao conhece"
    assert "fora do vocabul" in html, (
        "a tela mostrou a palavra desconhecida sem dizer que e' desconhecida")
    assert "veja em «Todos»" in html, (
        "a linha nao esta' em vista nenhuma: a tela tem de dizer onde ve-la")

    # E A VISTA PADRAO NAO A MOSTRA, DE PROPOSITO: ela afirma o que ainda pede
    # alguma coisa, e o sistema nao sabe se uma palavra desconhecida pede.
    so_abertos = c.get("/ajuda/problemas").get_data(as_text=True)
    assert "a que veio de fora" not in so_abertos
