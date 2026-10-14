"""
Testes das TELAS do agente do sistema.

POR QUE TELA, E NAO SO DOMINIO
    "Buraco de tela nao aparece em teste de dominio" e a licao que se repetiu
    seis vezes nesta casa — e com o agente ela vale mais que nunca: um agente
    com dez ferramentas prontas e nenhuma tela e um agente que ninguem usa. O
    que estes testes provam e que **o oficial consegue chegar nele**.

O QUE ELES CONFEREM
      - o ADMIN entra; o escrevente NAO — nem pela tela, nem mandando POST
        direto na rota;
      - o menu mostra o agente SO para o ADMIN, e nao para o gerente: aqui a
        regua e mais estreita que a da ajuda, e e de proposito;
      - SEM CHAVE o pedido nao vira sessao: recusa antes de gravar, para nao
        deixar na lista uma sessao que nunca falou com ninguem;
      - A CHAVE VAI PARA O ARQUIVO, e nao para o banco;
      - CAMPO VAZIO NAO APAGA NADA — quem apaga e o botao que diz que apaga;
      - A ESCRITA NASCE DESLIGADA, e so liga por clique;
      - o teto digitado na tela e PRESO no limite duro, e a tela diz o que
        passou a valer;
      - GET nao grava nada;
      - a sessao desenhada na tela mostra o que se pediu e o que as ferramentas
        devolveram.
"""
from __future__ import annotations

import glob
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _sessao(tmp_path, papel: str = "ADMIN"):
    from app import create_app
    from database import Database

    dados = tmp_path / "dados"
    # `parents`: o teste do menu cria uma sessão por papel, cada uma na sua
    # pasta — mesmo usuário em dois bancos diferentes, e não duas vezes no
    # mesmo banco.
    dados.mkdir(parents=True, exist_ok=True)
    app = create_app({"DATA_DIR": str(dados)})
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


def _pasta(s) -> Path:
    return s["dados"]


# ------------------------------------------------------- quem entra


def test_o_administrador_ve_o_console(admin, monkeypatch):
    import agente_web
    monkeypatch.setattr(agente_web, "AGENTE_VISIVEL", True)
    html = admin["c"].get("/agente").get_data(as_text=True)
    assert "Pedir ao agente" in html
    # e o menu do sistema leva ate ele
    menu = admin["c"].get("/").get_data(as_text=True)
    assert "Agente do sistema" in menu


def test_o_agente_saiu_da_tela_por_ordem_do_oficial(admin):
    """06/10/2026: «desativar o modulo de agente do sistema. apenas nao aparecer
    mais». Nem o menu, nem o «configurar», nem a gaveta — e nada se apagou."""
    menu = admin["c"].get("/").get_data(as_text=True)
    assert "Agente do sistema" not in menu and "Agente — configurar" not in menu
    assert "agente.js" not in menu and "agente-chamar" not in menu
    assert admin["c"].get("/agente").status_code == 200    # a rota continua, só do ADMIN


def test_o_escrevente_nao_ve_o_console(tmp_path):
    s = _sessao(tmp_path, "USER")
    resposta = s["c"].get("/agente")
    assert resposta.status_code == 403
    assert "permissão" in resposta.get_data(as_text=True)


def test_o_gerente_tambem_nao_ve(tmp_path):
    """**A RÉGUA AQUI É MAIS ESTREITA QUE A DA AJUDA**, e é de propósito.

    A ajuda abre para o gerente porque saber o que está quebrado é de quem
    responde pela serventia. O agente não é «saber»: é ter permissão de mudar o
    sistema, e essa fica com quem responde por ele.
    """
    s = _sessao(tmp_path, "MANAGER")
    assert s["c"].get("/agente").status_code == 403


def test_o_menu_esconde_o_agente_de_quem_nao_pode(tmp_path):
    for papel in ("USER", "MANAGER"):
        s = _sessao(tmp_path / papel, papel)
        menu = s["c"].get("/").get_data(as_text=True)
        assert "Agente do sistema" not in menu, f"{papel} viu o agente no menu"
        # e a tela de configuração, que também é do admin, também não abre
        assert s["c"].get("/agente/configurar").status_code == 403


def test_o_escrevente_mandando_POST_direto_tambem_e_recusado(tmp_path):
    """A tela esconde por educação; a ROTA recusa por dever.

    Este teste não passa por tela nenhuma: manda o POST como faria quem
    digitasse a URL. E confere que a recusa **não deixou rastro** — sessão
    gravada para quem não podia pedir seria trabalho feito para ninguém.
    """
    s = _sessao(tmp_path, "USER")
    html = s["c"].get("/").get_data(as_text=True)
    resposta = s["c"].post("/agente/pedir",
                           data={"csrf_token": _token(html),
                                 "pedido": "quero isto"})
    assert resposta.status_code == 403
    con = _con(s)
    assert con.execute(
        "SELECT COUNT(*) c FROM ag_sessoes").fetchone()["c"] == 0
    con.close()


# ------------------------------------------------- o pedido sem chave


def test_sem_chave_o_pedido_nao_vira_sessao(admin):
    """Recusa ANTES de gravar: sessão sem chave é linha na lista que nunca falou
    com ninguém, e quem a visse procuraria o que ela disse."""
    html = admin["c"].get("/agente").get_data(as_text=True)
    resposta = admin["c"].post(
        "/agente/pedir",
        data={"csrf_token": _token(html),
              "pedido": "veja o que a conferência mede sobre o selo"},
        follow_redirects=True)
    texto = resposta.get_data(as_text=True)
    # A RECUSA É DO DOMÍNIO, e diz onde a chave mora — a frase é conferida
    # inteira: um recado que só dissesse «sem chave» deixaria quem não sabe
    # procurando onde informá-la.
    assert "Não há chave do DeepSeek informada" in texto
    assert "fora do banco" in texto
    con = _con(admin)
    assert con.execute(
        "SELECT COUNT(*) c FROM ag_sessoes").fetchone()["c"] == 0
    con.close()


def test_pedido_vazio_e_recusado_sem_gastar_turno(admin):
    html = admin["c"].get("/agente").get_data(as_text=True)
    resposta = admin["c"].post("/agente/pedir",
                               data={"csrf_token": _token(html), "pedido": "  "},
                               follow_redirects=True)
    assert "pedido vazio" in resposta.get_data(as_text=True)


def test_a_tela_diz_que_sem_chave_ele_nao_responde(admin):
    """O aviso aparece ANTES do clique, e nao depois do erro."""
    html = admin["c"].get("/agente").get_data(as_text=True)
    assert "ainda não tem chave informada" in html


# ------------------------------------------------------------- a chave


def _gravar_chave(s, provedor="deepseek", chave="sk-teste-12345678"):
    html = s["c"].get("/agente/configurar").get_data(as_text=True)
    return s["c"].post("/agente/configurar",
                       data={"csrf_token": _token(html), "acao": "chave",
                             "provedor": provedor, "api_key": chave},
                       follow_redirects=True)


def test_a_chave_vai_para_o_arquivo_e_nao_para_o_banco(admin):
    """**O BANCO VAI NO BACKUP, E O BACKUP SAI DA SERVENTIA.**"""
    import agente_provedores as PROV

    _gravar_chave(admin)
    arquivo = PROV.caminho_da_credencial(_pasta(admin))
    assert arquivo.exists(), "a chave não foi para o arquivo"
    assert "sk-teste-12345678" in arquivo.read_text(encoding="utf-8")
    # e o banco não sabe dela — nem no valor da config, nem no arquivo todo
    con = _con(admin)
    valores = [r["valor"] for r in con.execute(
        "SELECT valor FROM ag_config")]
    con.close()
    assert not any("sk-teste" in v for v in valores)
    assert b"sk-teste-12345678" not in Path(admin["banco"]).read_bytes()


def test_a_chave_gravada_aparece_mascarada(admin):
    _gravar_chave(admin)
    html = admin["c"].get("/agente/configurar").get_data(as_text=True)
    assert "5678" in html
    assert "sk-teste-12345678" not in html


def test_campo_de_chave_em_branco_nao_apaga_nada(admin):
    """**O CAMPO VAZIO É A ARMADILHA DESTE FORMULÁRIO.**

    `gravar_chave` recebe vazio como ordem de apagar — é assim que se desliga um
    provedor. Se o campo em branco chegasse até lá, quem abrisse a tela e
    salvasse outra coisa apagaria a chave sem saber.
    """
    import agente_provedores as PROV

    _gravar_chave(admin)
    html = admin["c"].get("/agente/configurar").get_data(as_text=True)
    resposta = admin["c"].post("/agente/configurar",
                               data={"csrf_token": _token(html),
                                     "acao": "chave", "provedor": "deepseek",
                                     "api_key": ""},
                               follow_redirects=True)
    assert "nada foi gravado e nada foi apagado" in resposta.get_data(as_text=True)
    assert PROV.tem_chave(_pasta(admin), "deepseek")


def test_apagar_a_chave_e_por_botao_proprio(admin):
    import agente_provedores as PROV

    _gravar_chave(admin)
    html = admin["c"].get("/agente/configurar").get_data(as_text=True)
    admin["c"].post("/agente/configurar",
                    data={"csrf_token": _token(html), "acao": "apagar_chave",
                          "provedor": "deepseek"}, follow_redirects=True)
    assert not PROV.tem_chave(_pasta(admin), "deepseek")


def test_a_chave_da_ajuda_e_emprestada_para_a_anthropic(admin):
    """A casa já informou a chave do Claude na Ajuda; pedir de novo seria pedir
    duas vezes a mesma coisa — e alguém acabaria gravando a errada."""
    import agente_provedores as PROV

    (_pasta(admin) / PROV.ARQUIVO_DA_AJUDA).write_text(
        '{"api_key": "sk-ant-da-ajuda"}', encoding="utf-8")
    assert PROV.tem_chave(_pasta(admin), "claude")
    html = admin["c"].get("/agente/configurar").get_data(as_text=True)
    assert "emprestada" in html


# ------------------------------------------------------------ a escrita


def test_a_escrita_nasce_desligada(admin):
    """**CAPACIDADE NASCE DESLIGADA** — a mesma regra da ajuda."""
    import agente_schema as AGS

    con = _con(admin)
    assert AGS.escrita_ligada(con) is False
    con.close()
    html = admin["c"].get("/agente").get_data(as_text=True)
    assert "escrita desligada" in html


def test_ligar_a_escrita_pela_tela(admin):
    import agente_schema as AGS

    html = admin["c"].get("/agente/configurar").get_data(as_text=True)
    resposta = admin["c"].post(
        "/agente/configurar",
        data={"csrf_token": _token(html), "acao": "config",
              "provedor_padrao": "deepseek", "modelo_padrao": "deepseek-chat",
              "teto_de_turnos": "10", "teto_de_sessoes": "5",
              "escrita_ligada": "on"}, follow_redirects=True)
    assert "escrita LIGADA" in resposta.get_data(as_text=True)
    con = _con(admin)
    assert AGS.escrita_ligada(con) is True
    assert AGS.teto_de_turnos(con) == 10
    con.close()
    # e o aviso do console passa a dizer que ela está ligada
    assert "A escrita está LIGADA" in admin["c"].get("/agente") \
        .get_data(as_text=True)


def test_o_teto_digitado_e_preso_no_limite(admin):
    """Quem digita 900 na tela não pode achar que tem 900.

    Prender calado e DIZER o que valeu é melhor que recusar: a tela mostra o
    número que passou a valer, e a diferença fica visível em vez de virar um
    erro que ninguém sabe explicar.
    """
    import agente_schema as AGS

    html = admin["c"].get("/agente/configurar").get_data(as_text=True)
    resposta = admin["c"].post(
        "/agente/configurar",
        data={"csrf_token": _token(html), "acao": "config",
              "teto_de_turnos": "900", "teto_de_sessoes": "900"},
        follow_redirects=True)
    texto = resposta.get_data(as_text=True)
    assert f"até {AGS.TETO_MAXIMO_DE_TURNOS} turnos" in texto
    con = _con(admin)
    assert AGS.teto_de_turnos(con) == AGS.TETO_MAXIMO_DE_TURNOS
    assert AGS.teto_de_sessoes(con) == AGS.TETO_MAXIMO_DE_SESSOES
    con.close()


def test_a_tela_de_configurar_mostra_os_provedores(admin):
    """DeepSeek é a razão de o seletor existir — e o pedido do oficial."""
    html = admin["c"].get("/agente/configurar").get_data(as_text=True)
    for nome in ("DeepSeek", "Claude", "GPT", "Grok"):
        assert nome in html, f"o provedor {nome} não aparece na tela"


def test_a_tela_diz_que_ele_nao_toca_em_ato(admin):
    """É a frase que sustenta a permissão de escrever."""
    html = admin["c"].get("/agente").get_data(as_text=True)
    assert "Não há ferramenta que toque em ato" in html


# ------------------------------------------------------- GET não grava


def test_GET_nao_grava_nada(admin):
    """Tela de leitura que grava fica presa no `busy_timeout` enquanto outro
    balcão lavra — e nenhuma das duas telas precisa escrever para aparecer."""
    con = _con(admin)
    antes = [tuple(r) for r in con.execute("SELECT * FROM ag_config")]
    con.close()
    for _ in range(2):
        admin["c"].get("/agente")
        admin["c"].get("/agente/configurar")
    con = _con(admin)
    assert con.execute(
        "SELECT COUNT(*) c FROM ag_sessoes").fetchone()["c"] == 0
    depois = [tuple(r) for r in con.execute("SELECT * FROM ag_config")]
    con.close()
    assert antes == depois


# --------------------------------------------------- a sessão desenhada


def test_a_sessao_mostra_o_que_se_pediu_e_o_que_voltou(admin):
    """**A CONVERSA DESENHADA SAI DA MESMA TABELA QUE O AGENTE LÊ.**

    Aqui a sessão é montada à mão, sem rede: o que se prova é a tela, que é
    justamente o que teste de domínio não alcança.
    """
    import agente_schema as AGS

    con = _con(admin)
    AGS.init_agente_schema(con)
    sessao_id = AGS.abrir_sessao(
        con, titulo="o selo não responde", pedido="o selo não responde",
        provedor="deepseek", modelo="deepseek-chat",
        agora="2026-09-14T10:00:00", criada_por="MARIO EXEMPLO DOS SANTOS")
    AGS.registrar_passo(con, sessao_id, ordem=1, tipo=AGS.PEDIDO,
                        conteudo="o selo não responde",
                        agora="2026-09-14T10:00:00")
    AGS.registrar_passo(con, sessao_id, ordem=2, tipo=AGS.FERRAMENTA,
                        ferramenta="estado_do_sistema",
                        chamada_id="call_1", argumentos='{"o_que": "selo"}',
                        agora="2026-09-14T10:00:01")
    AGS.registrar_passo(con, sessao_id, ordem=3, tipo=AGS.RESULTADO,
                        ferramenta="estado_do_sistema", chamada_id="call_1",
                        conteudo="o selador respondeu pela última vez às 09:58",
                        agora="2026-09-14T10:00:02")
    AGS.registrar_mudanca(con, sessao_id, ferramenta="anotar_no_problema",
                          alvo="problema 12", antes="aberto", depois="com nota",
                          agora="2026-09-14T10:00:03", criada_por="tabeliao")
    AGS.atualizar_sessao(con, sessao_id, estado=AGS.CONCLUIDA, turnos=3,
                         tokens_de_entrada=1200, tokens_de_saida=340,
                         erro="", agora="2026-09-14T10:00:04")
    con.commit()
    con.close()

    html = admin["c"].get(f"/agente/sessao/{sessao_id}").get_data(as_text=True)
    assert "o selo não responde" in html
    assert "estado_do_sistema" in html
    assert "o selador respondeu pela última vez" in html
    assert "anotar_no_problema" in html
    # o gasto aparece: oficial que não vê o preço não pode decidir sobre ele
    assert "1200" in html and "340" in html
    assert "terminou" in html
    # e o que ele mudou volta com um clique
    assert "desfazer" in html


def test_sessao_que_nao_existe_e_recusada_com_recado(admin):
    resposta = admin["c"].get("/agente/sessao/9999", follow_redirects=True)
    assert "Não achei a sessão #9999" in resposta.get_data(as_text=True)
