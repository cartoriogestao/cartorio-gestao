"""A lista de títulos do Protesto: pendentes, filtros, ordens e o próximo passo.

Pedido do oficial em 14/10/2026, o primeiro dia do protesto no sistema: «não
consigo ver, filtrar e ordenar os títulos realmente pendentes… preciso que
tudo esteja integrado e seja um fluxo natural o recebimento do título,
intimação, protesto».

Os títulos são semeados direto no banco — a tela só consulta —, um em cada
ponto do fluxo: recebido, apontado sem aviso, apontado com aviso na rua,
intimado (na fila do «A protestar»), intimado e sustado, protestado e pago.
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

import protesto_lista as L  # noqa: E402

SENHA = "Senha#12345"
HOJE = "2026-10-14"
CHAVE = "21070010141361701260910"     # 23 dígitos, a forma medida


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _titulo(con, *, numero, situacao, devedor, doc="", saldo=10000,
            protocolo=None, apres=("", ""), criado="2026-08-01T09:00:00",
            chave=None) -> int:
    cur = con.execute(
        """INSERT INTO pt_titulos(especie, numero_titulo, protocolo,
               valor_centavos, saldo_centavos, situacao, origem, origem_chave,
               apresentante_codigo, apresentante_nome, chave_cenprot,
               criado_em)
           VALUES ('DMI',?,?,?,?,?,'CRA',?,?,?,?,?)""",
        (numero, protocolo, saldo, saldo, situacao, f"t:{numero}",
         apres[0] or None, apres[1] or None, chave, criado))
    tid = int(cur.lastrowid)
    con.execute(
        """INSERT INTO pt_devedores(titulo_id, nome, documento_tipo,
               documento_numero, nome_norm)
           VALUES (?,?,'CPF',?,?)""",
        (tid, devedor, doc or None, devedor.lower()))
    return tid


def _ato(con, tid, tipo, data, *, ordem=None, detalhe="{}"):
    con.execute(
        """INSERT INTO pt_atos(titulo_id, tipo, numero_ordem, data_ato,
               detalhe_json, origem, criado_em)
           VALUES (?,?,?,?,?,'MANUAL',?)""",
        (tid, tipo, ordem, data, detalhe, data + "T09:00:00"))


def _semear(banco: Path) -> dict:
    con = sqlite3.connect(banco)
    ids = {}
    with con:
        ids["recebido"] = _titulo(
            con, numero="T1", situacao="RECEBIDO", devedor="ANA RECEBIDA",
            criado="2026-10-10T10:00:00",
            apres=("1LV", "EQUATORIAL MARANHAO"))
        ids["apontado"] = _titulo(
            con, numero="T2", situacao="APONTADO", devedor="BRUNO APONTADO",
            doc="12345678901", saldo=50000, protocolo="2610010001",
            apres=("987", "SECRETARIA DA FAZENDA DO ESTADO DO MA"),
            chave=CHAVE)
        _ato(con, ids["apontado"], "APONTAMENTO", "2026-10-01", ordem=101)
        ids["avisado"] = _titulo(
            con, numero="T3", situacao="APONTADO", devedor="CARLA AVISADA",
            protocolo="2610020001")
        _ato(con, ids["avisado"], "APONTAMENTO", "2026-10-02", ordem=102)
        con.execute(
            """INSERT INTO pt_avisos(titulo_id, numero, ano, devedor_nome,
                   situacao, emitido_em, criado_em)
               VALUES (?,7,2026,'CARLA AVISADA','EMITIDO',
                       '2026-10-03T10:00:00','2026-10-03T10:00:00')""",
            (ids["avisado"],))
        ids["intimado"] = _titulo(
            con, numero="T4", situacao="INTIMADO", devedor="DANIEL INTIMADO",
            saldo=20000, protocolo="2609200001")
        _ato(con, ids["intimado"], "APONTAMENTO", "2026-09-20", ordem=103)
        _ato(con, ids["intimado"], "INTIMACAO", "2026-10-04",
             detalhe='{"modo": "EDITAL"}')
        ids["sustado"] = _titulo(
            con, numero="T5", situacao="INTIMADO", devedor="ELIAS SUSTADO",
            protocolo="2609210001")
        _ato(con, ids["sustado"], "APONTAMENTO", "2026-09-21", ordem=104)
        _ato(con, ids["sustado"], "INTIMACAO", "2026-10-05",
             detalhe='{"modo": "EDITAL"}')
        _ato(con, ids["sustado"], "SUSTACAO", "2026-10-06",
             detalhe='{"juizo": "1ª VARA CÍVEL", "processo": "0800123-45"}')
        ids["protestado"] = _titulo(
            con, numero="T6", situacao="PROTESTADO", devedor="EVA PROTESTADA",
            protocolo="2608010001")
        _ato(con, ids["protestado"], "APONTAMENTO", "2026-08-01", ordem=90)
        ids["pago"] = _titulo(
            con, numero="T7", situacao="PAGO", devedor="FABIO PAGOU",
            protocolo="2608020001")
        _ato(con, ids["pago"], "APONTAMENTO", "2026-08-02", ordem=91)
    con.close()
    return ids


@pytest.fixture(scope="module")
def casa(tmp_path_factory):
    from app import create_app
    from database import Database

    dados = tmp_path_factory.mktemp("protesto_lista") / "dados"
    dados.mkdir()
    app = create_app({"DATA_DIR": str(dados)})
    banco = Path(glob.glob(f"{dados}/*.sqlite3")[0])
    db = Database(banco)
    db.create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    db.set_settings({"modulo_protesto_ligado": "1"})
    ids = _semear(banco)
    return {"app": app, "banco": banco, "ids": ids}


def _cliente(casa):
    c = casa["app"].test_client()
    c.post("/login",
           data={"username": "tabeliao", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return c


def _con(casa):
    con = sqlite3.connect(f"file:{casa['banco']}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _listar(casa, **args):
    con = _con(casa)
    try:
        return L.listar(con, L.ler_filtro(args), hoje=HOJE)
    finally:
        con.close()


def _numeros(r):
    return [l["numero_titulo"] for l in r["linhas"]]


# ------------------------------------------------------------- o domínio


def test_abre_nos_pendentes_do_mais_antigo_para_o_mais_novo(casa):
    r = _listar(casa)
    # Entrada = data do apontamento; o recebido entra pela data do cadastro.
    assert _numeros(r) == ["T4", "T5", "T2", "T3", "T1"]
    assert r["vistas"] == {"pendentes": 5, "encerrados": 2, "todos": 7}


def test_encerrados_e_todos_tem_as_suas_vistas(casa):
    assert set(_numeros(_listar(casa, vista="encerrados"))) == {"T6", "T7"}
    assert len(_listar(casa, vista="todos")["linhas"]) == 7


def test_o_proximo_passo_sai_do_estado_de_cada_titulo(casa):
    r = _listar(casa)
    passo = {l["numero_titulo"]: l["proximo"] for l in r["linhas"]}
    assert passo["T1"]["passo"] == "apontar"
    # Com a chave do CENPROT, a intimação digital é oferecida; sem ela, não.
    assert passo["T2"]["passo"] == "intimar"
    assert "intimação digital" in passo["T2"]["texto"]
    assert passo["T3"]["passo"] == "entrega"
    assert "7/2026" in passo["T3"]["texto"]
    # A régua do «A protestar»: contagem, e não juízo.
    assert passo["T4"]["passo"] == "protestar"
    assert passo["T4"]["dias"] == 10
    assert "10 dia(s)" in passo["T4"]["texto"]
    # A ordem judicial vem antes de tudo, com o juízo e o processo.
    assert passo["T5"]["passo"] == "sustado"
    assert "1ª VARA CÍVEL" in passo["T5"]["texto"]
    assert "0800123-45" in passo["T5"]["texto"]


def test_o_proximo_passo_nao_julga_o_prazo(casa):
    r = _listar(casa)
    for l in r["linhas"]:
        texto = (l["proximo"] or {}).get("texto", "").lower()
        for palavra in ("vencido", "venceu", "atrasado", "fora do prazo"):
            assert palavra not in texto


def test_titulo_encerrado_nao_tem_proximo_passo(casa):
    r = _listar(casa, vista="encerrados")
    assert all(l["proximo"] is None for l in r["linhas"])


def test_colunas_numero_do_apontamento_e_chave(casa):
    r = _listar(casa)
    linha = {l["numero_titulo"]: l for l in r["linhas"]}
    assert linha["T2"]["numero_apontamento"] == 101
    assert linha["T1"]["numero_apontamento"] is None
    assert linha["T2"]["tem_chave"] is True
    assert linha["T3"]["tem_chave"] is False


def test_filtro_sustado_pergunta_pelo_ato(casa):
    assert _numeros(_listar(casa, situacao="SUSTADO")) == ["T5"]


def test_filtro_por_situacao_dentro_da_vista(casa):
    assert _numeros(_listar(casa, situacao="APONTADO")) == ["T2", "T3"]
    # Situação encerrada sem vista escolhida abre na vista que a contém.
    assert _numeros(_listar(casa, situacao="PAGO")) == ["T7"]


def test_filtro_por_apresentante_pelo_codigo_ou_pelo_nome(casa):
    assert _numeros(_listar(casa, apresentante="1LV")) == ["T1"]
    assert _numeros(_listar(casa, apresentante="fazenda")) == ["T2"]


def test_filtro_de_entrada_inclui_o_ultimo_dia(casa):
    assert _numeros(_listar(casa, de="2026-10-01", ate="2026-10-02")) == [
        "T2", "T3"]
    # O recebido tem hora no carimbo (2026-10-10T10:00): «até 10/10» o inclui.
    assert "T1" in _numeros(_listar(casa, de="2026-10-10", ate="2026-10-10"))


def test_busca_pelo_devedor_com_documento_mascarado(casa):
    assert _numeros(_listar(casa, q="123.456.789-01")) == ["T2"]


def test_busca_sem_vista_procura_em_todos(casa):
    # «Fulano tem protesto?» — a resposta está nos encerrados.
    r = _listar(casa, q="eva")
    assert _numeros(r) == ["T6"]


def test_ordem_por_valor_e_por_dias(casa):
    assert _numeros(_listar(casa, ordem="valor"))[0] == "T2"
    dias = _numeros(_listar(casa, ordem="dias", dir="desc"))
    # Mais dias primeiro; quem não foi intimado vai para o fim.
    assert dias[:2] == ["T4", "T5"]
    asc = _numeros(_listar(casa, ordem="dias", dir="asc"))
    assert asc[:2] == ["T5", "T4"]


def test_ordem_e_filtro_desconhecidos_nao_viram_sql(casa):
    f = L.ler_filtro({"ordem": "id; DROP TABLE pt_titulos", "dir": "x",
                      "situacao": "NADA", "de": "ontem"})
    assert f["ordem"] == "entrada" and f["dir"] == "asc"
    assert f["situacao"] == "" and f["de"] == ""


def test_params_leva_a_escolha_e_omite_o_padrao():
    f = L.ler_filtro({"vista": "encerrados", "apresentante": "1LV"})
    p = L.params(f, pagina=2)
    assert p == {"vista": "encerrados", "apresentante": "1LV", "pagina": 2}
    clique = L.ordenar_por(f, "valor")
    assert clique["ordem"] == "valor" and clique["dir"] == "desc"
    assert "pagina" not in clique
    de_novo = L.ordenar_por(L.ler_filtro(clique), "valor")
    assert de_novo["dir"] == "asc"


# ------------------------------------------------------------- a tela


def test_a_tela_abre_nos_pendentes_com_o_numero_de_cada_vista(casa):
    html = _cliente(casa).get("/protesto").get_data(as_text=True)
    assert "Pendentes (5)" in html
    assert "Encerrados (2)" in html
    assert "Todos (7)" in html
    assert "ANA RECEBIDA" in html
    assert "EVA PROTESTADA" not in html
    for coluna in ("Protocolo", "Nº apont.", "Entrada", "Apresentante",
                   "Devedor", "Espécie", "Valor", "Situação", "CENPROT",
                   "Próximo passo"):
        assert coluna in html


def test_a_tela_leva_ao_lugar_de_cada_passo(casa):
    html = _cliente(casa).get("/protesto").get_data(as_text=True)
    assert 'href="/protesto/a-protestar"' in html
    assert 'href="/protesto/avisos"' in html
    assert "1ª VARA CÍVEL" in html
    assert f'href="/protesto/{casa["ids"]["recebido"]}"' in html


def test_os_cabecalhos_ordenam_sem_perder_o_filtro(casa):
    html = _cliente(casa).get(
        "/protesto?vista=todos&apresentante=1LV").get_data(as_text=True)
    cabecalho = re.search(r'href="([^"]*ordem=valor[^"]*)"', html)
    assert cabecalho, "o cabeçalho «Valor» não é clicável"
    alvo = cabecalho.group(1).replace("&amp;", "&")
    assert "vista=todos" in alvo and "apresentante=1LV" in alvo


def test_a_volta_da_ficha_reabre_o_ultimo_filtro(casa):
    c = _cliente(casa)
    c.get("/protesto?vista=encerrados")
    html = c.get("/protesto").get_data(as_text=True)
    assert "último filtro" in html
    assert "EVA PROTESTADA" in html
    # «Limpar» manda a vista no endereço, e por isso não cai nesta volta.
    html = c.get("/protesto?vista=pendentes").get_data(as_text=True)
    assert "EVA PROTESTADA" not in html
    assert "último filtro" not in html


def test_a_ficha_tem_o_caminho_de_volta(casa):
    c = _cliente(casa)
    html = c.get(f"/protesto/{casa['ids']['apontado']}").get_data(as_text=True)
    assert 'href="/protesto"' in html


def test_filtro_vazio_diz_onde_mais_procurar(casa):
    html = _cliente(casa).get(
        "/protesto?vista=pendentes&q=FABIO").get_data(as_text=True)
    assert "Nada aqui" in html
    assert "vista=todos" in html


def test_get_da_lista_nao_grava_no_banco(casa):
    con = sqlite3.connect(casa["banco"])
    antes = con.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
    _cliente(casa).get("/protesto?vista=todos&ordem=dias")
    depois = con.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
    con.close()
    # O login grava auditoria; a lista não acrescenta nada além dele.
    assert depois - antes <= 1


def test_o_sql_novo_nao_aumenta_o_acoplamento():
    """Módulo novo entra com zero — a regra de `tests/test_portabilidade.py`."""
    import ast
    arvore = ast.parse((RAIZ / "protesto_lista.py").read_text(encoding="utf-8"))
    docstrings = {id(n.body[0].value) for n in ast.walk(arvore)
                  if isinstance(n, (ast.Module, ast.FunctionDef))
                  and n.body and isinstance(n.body[0], ast.Expr)
                  and isinstance(n.body[0].value, ast.Constant)}
    for no in ast.walk(arvore):
        if (isinstance(no, ast.Constant) and isinstance(no.value, str)
                and id(no) not in docstrings):
            texto = no.value.lower()
            for proibido in ("substr(", "||", "strftime(", "julianday(",
                             "pragma"):
                assert proibido not in texto, (proibido, no.value[:60])
