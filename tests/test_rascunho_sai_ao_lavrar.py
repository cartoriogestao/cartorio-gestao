"""Quando o ato grava, o rascunho sai da lista sozinho.

    «Sim, sair sozinho»  — o oficial, 31/10/2026, sobre o rascunho que continuava na lista depois de lavrado

O QUE ELES DEFENDEM
    O rascunho lavrado ficava na lista, e alguém podia abri-lo e lavrar de novo. Lavrar duas vezes o mesmo
    registro não se desfaz com um clique, e por isso quatro coisas têm de valer juntas:

    1. Sai só quando o ato ficou de pé. Se o selo falha e o ato é desfeito, ele é a única cópia do digitado.
    2. Sai só o rascunho daquela tela: o número no endereço pode ser o de outro.
    3. Fica uma marca, sem dado de cliente. O mesmo registro de um arquivo não volta à fila depois de lavrado.
    4. Quem volta pelo navegador, ou tem o rascunho aberto noutra aba, vai para o ato, e nada se grava de novo.

    Os primeiros rodam sem banco. Os do fim abrem o sistema, e rodam na máquina do balcão.
"""
from __future__ import annotations

import json
import re
import sys
from contextlib import contextmanager
from pathlib import Path

import flask
import pytest
from werkzeug.exceptions import HTTPException

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import rascunho_de_tela as R                                    # noqa: E402

AGORA = "2026-10-31T10:00:00"


class _Bd:
    """O que as funções enxergam do banco: a lista de rascunhos e as marcas."""

    def __init__(self, *rascunhos):
        self.rascunhos = {r["id"]: r for r in rascunhos}
        self.marcas = {}

    def um(self, sql, parametros=()):
        chave = parametros[0]
        if "rascunhos_que_viraram_ato" in sql:
            if "chave =" in sql:
                return next((m for m in self.marcas.values() if m["chave"] == chave), None)
            return self.marcas.get(chave)
        if "chave =" in sql:
            return next((r for r in self.rascunhos.values() if r["chave"] == chave), None)
        return self.rascunhos.get(chave)

    def escrever(self, sql, parametros=()):
        if sql.lstrip().startswith("DELETE"):
            self.rascunhos.pop(parametros[0], None)
            return
        self.marcas[parametros[0]] = dict(
            zip(("rascunho_id", "tela", "chave", "endereco", "em", "por"), parametros))

    def tem_tabela(self, _nome):
        return True


class _Db:
    def __init__(self, falha=False):
        self.falha = falha

    def now(self):
        return AGORA

    @contextmanager
    def transaction(self):
        if self.falha:
            raise RuntimeError("banco fora do ar")
        yield None

    @contextmanager
    def connect(self):
        yield None


class _Auditoria:
    def __init__(self):
        self.linhas = []

    def __call__(self, *args):
        self.linhas.append(args)


def _app():
    app = flask.Flask(__name__)
    app.secret_key = "para o aviso"
    app.add_url_rule("/rascunhos", "rascunhos", lambda: "")
    return app


def _rascunho(id_=3, tela="t", chave=""):
    return {"id": id_, "tela": tela, "chave": chave}


@pytest.fixture()
def bd(monkeypatch):
    b = _Bd(_rascunho())
    monkeypatch.setattr(R, "banco", lambda con: b)
    return b


# ------------------------------------------------------------------- de onde vem o número do rascunho

@pytest.mark.parametrize("endereco, corpo, esperado", [
    ("/x", {}, None),
    ("/x?rascunho_id=3", {}, 3),
    ("/x", {"_rascunho_id_tela": "4"}, 4),
    ("/x?rascunho_id=3", {"_rascunho_id_tela": "4"}, 4),
    ("/x?rascunho_id=abc", {"_rascunho_id_tela": "²"}, None),
])
def test_o_rascunho_vem_do_campo_ou_do_endereco(endereco, corpo, esperado):
    with _app().test_request_context(endereco, method="POST", data=corpo):
        assert R.do_envio() == esperado


def test_o_campo_nunca_entra_no_que_o_rascunho_guarda():
    """Começa com sublinhado de propósito: guardado, ele reabriria apontando para si mesmo."""
    with _app().test_request_context("/x", method="POST", data={R.CAMPO_DO_RASCUNHO: "3", "nome": "ANA"}):
        assert R.dados_do_envio(flask.request.form) == {"nome": "ANA"}


# --------------------------------------------------------------------------- quando o ato fica de pé

def test_o_ato_de_pe_tira_o_rascunho_e_deixa_so_a_marca(bd):
    auditoria = _Auditoria()
    with _app().test_request_context("/x?rascunho_id=3", method="POST"):
        R.saiu_com_o_ato(_Db(), auditoria, "t", "/ato/9", "mario")
        recados = flask.get_flashed_messages(with_categories=True)
    assert bd.rascunhos == {}
    assert bd.marcas[3] == {"rascunho_id": 3, "tela": "t", "chave": "", "endereco": "/ato/9", "em": AGORA, "por": "mario"}
    assert auditoria.linhas == [("RASCUNHO_VIROU_ATO", "rascunhos_de_tela", 3, {"tela": "t", "ato": "/ato/9"})]
    assert recados[0][0] == "info" and "#3 saiu da lista" in recados[0][1]


def test_sem_rascunho_aberto_nada_acontece(bd):
    auditoria = _Auditoria()
    with _app().test_request_context("/x", method="POST"):
        R.saiu_com_o_ato(_Db(), auditoria, "t", "/ato/9", "mario")
        assert flask.get_flashed_messages() == []
    assert 3 in bd.rascunhos and bd.marcas == {} and auditoria.linhas == []


@pytest.mark.parametrize("tela, chave", [("outra_tela", None), ("t", "/rcpn/2/averbar")])
def test_o_rascunho_de_outra_tela_ou_de_outro_assento_nao_sai(bd, tela, chave):
    """O número no endereço pode ser o de outro rascunho: gravar um ato não apaga o trabalho alheio."""
    auditoria = _Auditoria()
    with _app().test_request_context("/x?rascunho_id=3", method="POST"):
        R.saiu_com_o_ato(_Db(), auditoria, tela, "/ato/9", "mario", chave=chave)
        assert flask.get_flashed_messages() == []
    assert 3 in bd.rascunhos and bd.marcas == {} and auditoria.linhas == []


def test_o_rascunho_que_nao_existe_mais_nao_derruba_o_ato(bd):
    with _app().test_request_context("/x?rascunho_id=8", method="POST"):
        R.saiu_com_o_ato(_Db(), _Auditoria(), "t", "/ato/9", "mario")
        assert flask.get_flashed_messages() == []
    assert bd.marcas == {}


def test_a_falha_ao_tirar_vira_aviso_e_o_ato_continua(bd):
    """O ato já está gravado: mostrar a tela de erro faria a pessoa achar que não saiu, e lavrar de novo."""
    auditoria = _Auditoria()
    with _app().test_request_context("/x?rascunho_id=3", method="POST"):
        R.saiu_com_o_ato(_Db(falha=True), auditoria, "t", "/ato/9", "mario")
        recados = flask.get_flashed_messages(with_categories=True)
    assert recados[0][0] == "warning" and "O ato foi gravado" in recados[0][1] and "#3" in recados[0][1]
    assert auditoria.linhas == []


def test_a_marca_nao_guarda_dado_de_cliente():
    """O rascunho tem nome, filiação e endereço dentro, e isso agora mora no ato."""
    tabela = R.SCHEMA[R.SCHEMA.index("CREATE TABLE IF NOT EXISTS rascunhos_que_viraram_ato"):]
    colunas = tabela[tabela.index("(") + 1:tabela.index(");")]
    assert "dados_json" not in colunas and "titulo" not in colunas


def test_o_esquema_se_parte_em_comandos_inteiros():
    """`init_rascunho_schema` parte por «;»: um ponto e vírgula em comentário quebraria a abertura do banco."""
    comandos = ["\n".join(l for l in c.splitlines() if not l.strip().startswith("--")).strip()
                for c in R.SCHEMA.split(";")]
    assert all(c.startswith(("CREATE TABLE IF NOT EXISTS", "CREATE INDEX IF NOT EXISTS")) for c in comandos if c)
    assert sum("rascunhos_que_viraram_ato" in c for c in comandos) == 2


# ----------------------------------------------------------------------------- quem volta ao rascunho

@pytest.mark.parametrize("metodo", ["GET", "POST"])
def test_quem_volta_ao_rascunho_que_virou_ato_vai_para_o_ato(bd, metodo):
    bd.marcas[3] = {"rascunho_id": 3, "endereco": "/ato/9"}
    with _app().test_request_context("/x?rascunho_id=3", method=metodo):
        with pytest.raises(HTTPException) as saida:
            R.barrar_se_ja_virou_ato(_Db())
        assert "já virou ato" in flask.get_flashed_messages()[0]
    assert saida.value.get_response().headers["Location"] == "/ato/9"


def test_sem_o_endereco_do_ato_vai_para_a_lista(bd):
    """É o caso do botão do processo, que sabe que o ato existe e não sabe onde."""
    bd.marcas[3] = {"rascunho_id": 3, "endereco": None}
    with _app().test_request_context("/x?rascunho_id=3"):
        with pytest.raises(HTTPException) as saida:
            R.barrar_se_ja_virou_ato(_Db())
    assert saida.value.get_response().headers["Location"] == "/rascunhos"


@pytest.mark.parametrize("endereco", ["/x", "/x?rascunho_id=3", "/x?rascunho_id=8"])
def test_o_rascunho_vivo_e_o_apagado_a_mao_nao_barram(bd, endereco):
    """Jogar fora um papel não diz que o ato existe: quem digitava continua gravando."""
    with _app().test_request_context(endereco, method="POST"):
        R.barrar_se_ja_virou_ato(_Db())
        assert flask.get_flashed_messages() == []


def test_a_tela_de_ato_tambem_barra(bd):
    """É `para_a_tela`, e por isso as oito telas que a chamam não precisam lembrar."""
    bd.marcas[3] = {"rascunho_id": 3, "endereco": "/ato/9"}
    with _app().test_request_context("/x?rascunho_id=3", method="POST"):
        with pytest.raises(HTTPException):
            R.para_a_tela(_Db(), "t", "outra")


def test_apagar_a_mao_nao_deixa_marca(bd):
    """Quem joga fora quer poder trazer o registro de novo: a marca é só do que virou ato."""
    R.apagar(None, 3)
    assert 3 not in bd.rascunhos and bd.marcas == {}


# ------------------------------------------------------------------------------------ a fila de arquivos

def test_o_registro_do_arquivo_nao_volta_depois_de_lavrado(bd):
    bd.rascunhos[3]["chave"] = "arquivo:dnv-1"
    assert R.chave_ja_recebida(None, "arquivo:dnv-1")
    R.virou_ato(None, 3, endereco="/rcpn/1", agora=AGORA, por="mario")
    assert bd.rascunhos == {}
    assert R.chave_ja_recebida(None, "arquivo:dnv-1")
    assert not R.chave_ja_recebida(None, "arquivo:dnv-2")


def test_o_registro_apagado_a_mao_pode_voltar(bd):
    bd.rascunhos[3]["chave"] = "arquivo:dnv-1"
    R.apagar(None, 3)
    assert not R.chave_ja_recebida(None, "arquivo:dnv-1")


def test_a_fila_e_a_previa_perguntam_a_mesma_funcao():
    fonte = (RAIZ / "importar_padrao.py").read_text(encoding="utf-8")
    assert fonte.count("RASC.chave_ja_recebida(con") == 2
    assert 'SELECT id FROM rascunhos_de_tela WHERE chave' not in fonte


# ----------------------------------------------------------------------------------- as onze telas

def _telas_que_salvam() -> set[str]:
    achadas = set()
    for molde in (RAIZ / "templates").glob("*.html"):
        if molde.name != "_rascunho.html":
            achadas |= set(re.findall(r"salvar_rascunho\(\s*'(\w+)'", molde.read_text(encoding="utf-8")))
    return achadas


def _corpo_da_rota(endpoint: str) -> str:
    for arquivo in RAIZ.glob("*_web.py"):
        achou = re.search(rf"^    def {endpoint}\(.*?(?=^    @app\.route|\Z)",
                          arquivo.read_text(encoding="utf-8"), re.S | re.M)
        if achou:
            return achou.group(0)
    raise AssertionError(f"não achei a rota {endpoint}")


TELAS = sorted(_telas_que_salvam() - {R.TELA_DO_LANCAMENTO})


def test_a_lista_de_telas_nao_encolheu():
    assert len(TELAS) >= 10


@pytest.mark.parametrize("tela", TELAS)
def test_toda_tela_que_salva_tira_o_rascunho_ao_gravar(tela):
    """Tela nova com o botão de salvar entra aqui sozinha, e fica vermelha até tirar o rascunho."""
    assert re.search(rf'saiu_com_o_ato\(\s*db,\s*audit,\s*"{tela}"', _corpo_da_rota(tela)), tela


def test_o_lancamento_do_civil_tira_o_rascunho_do_mesmo_assento():
    assert re.search(r"saiu_com_o_ato\(\s*db,\s*audit,\s*RASC\.TELA_DO_LANCAMENTO,.*?chave=_chave_do_lancamento",
                     _corpo_da_rota("rcpn_lancar"), re.S)


@pytest.mark.parametrize("rota, falhou", [
    ("rcpn_assento_novo", "RCPN_ASSENTO_NAO_LAVRADO_SELO_FALHOU"),
    ("rcpn_lancar", "RCPN_ATO_NAO_LAVRADO_SELO_FALHOU"),
    ("rcpj_rtd_registro_novo", "RG_REGISTRO_NAO_ABERTO_SELO_FALHOU"),
])
def test_onde_o_selo_desfaz_o_ato_o_rascunho_so_sai_depois_dele(rota, falhou):
    corpo = _corpo_da_rota(rota)
    assert corpo.index(falhou) < corpo.index("saiu_com_o_ato(")


@pytest.mark.parametrize("rota", ["rcpn_assento_novo", "rcpn_lancar", "rcpn_habilitacao_nova", "ri_nova_matricula"])
def test_as_rotas_sem_para_a_tela_barram_por_conta_propria(rota):
    corpo = _corpo_da_rota(rota)
    assert corpo.index("barrar_se_ja_virou_ato(db)") < corpo.index("with db.transaction()")


def test_as_outras_telas_barram_por_para_a_tela():
    fonte = (RAIZ / "rascunho_de_tela.py").read_text(encoding="utf-8")
    corpo = fonte[fonte.index("def para_a_tela("):fonte.index("def chave_da_tela(")]
    assert corpo.index("barrar_se_ja_virou_ato(db)") < corpo.index('request.args.get("rascunho_id"')


# ---------------------------------------------------------------- o rascunho até o botão de lavrar

def test_o_assento_leva_o_rascunho_ate_a_conferencia():
    """Os botões da conferência têm endereço fixo: sem o campo, o rascunho não saberia que virou ato."""
    fonte = (RAIZ / "templates" / "atrib_rcpn_novo.html").read_text(encoding="utf-8")
    assert "rascunho_id = rascunho_id or form.get('_rascunho_id_tela')" in fonte
    assert 'name="_rascunho_id_tela" value="{{ rascunho_id }}"' in fonte


def test_os_tres_botoes_da_conferencia_devolvem_o_campo():
    """Eles reenviam `form.items()` tirando uma lista de nomes: o campo não pode entrar nela."""
    fonte = (RAIZ / "templates" / "rcpn_conferencia.html").read_text(encoding="utf-8")
    assert fonte.count("form.items()") >= 3
    assert "_rascunho" not in fonte


# ------------------------------------------------------------------- quem dependia da linha dele

def test_a_pasta_do_processo_nao_oferece_apagar_o_que_ja_saiu():
    fonte = (RAIZ / "templates" / "task_detail.html").read_text(encoding="utf-8")
    assert re.search(r"\{% if v\.rascunho %\}<label[^>]*><input[^>]*apagar_rascunho", fonte)


def test_o_processo_deixa_a_marca_ao_apagar_e_nao_um_delete_solto():
    fonte = (RAIZ / "processo_pasta.py").read_text(encoding="utf-8")
    assert "DELETE FROM rascunhos_de_tela" not in fonte
    assert "RASC.virou_ato(bd" in fonte
    assert "não tem como saber sozinho" not in fonte


def test_a_lista_diz_que_ele_sai_sozinho():
    fonte = (RAIZ / "templates" / "rascunhos.html").read_text(encoding="utf-8")
    assert "sai desta lista sozinho" in fonte


# ------------------------------------------------------------------- com o sistema de pé, no balcão

def _token(c, url):
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', c.get(url).get_data(as_text=True)).group(1)


def _um(db, sql, args=()):
    with db.connect() as con:
        return con.execute(sql, args).fetchone()


def _rascunho_das_notas(db) -> int:
    with db.transaction() as con:
        R.init_rascunho_schema(con)
        return R.salvar(con, tela="notas_ato_novo", dados={"tipo": "ESCRITURA", "interessado": "ANA EXEMPLO"},
                        titulo="Escritura — ANA EXEMPLO", agora=AGORA, por="mario")["id"]


def test_o_caminho_inteiro_lavra_uma_vez_so(cg_casa_logada):
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    rid = _rascunho_das_notas(db)
    endereco = f"/notas/atos/novo?rascunho_id={rid}"
    corpo = {"csrf_token": _token(c, endereco), "tipo": "ESCRITURA", "interessado": "ANA EXEMPLO"}

    r = c.post(endereco, data=corpo)
    assert r.status_code == 302 and "/notas/atos/" in r.headers["Location"]
    ato = r.headers["Location"]
    assert _um(db, "SELECT COUNT(*) FROM rascunhos_de_tela WHERE id=?", (rid,))[0] == 0
    marca = _um(db, "SELECT tela, endereco FROM rascunhos_que_viraram_ato WHERE rascunho_id=?", (rid,))
    assert marca[0] == "notas_ato_novo" and ato.endswith(marca[1])
    assert f"rascunho_id={rid}" not in c.get("/rascunhos").get_data(as_text=True)

    atos = _um(db, "SELECT COUNT(*) FROM nt_atos")[0]
    de_novo = c.post(endereco, data=corpo)
    assert de_novo.status_code == 302 and de_novo.headers["Location"] == ato
    assert _um(db, "SELECT COUNT(*) FROM nt_atos")[0] == atos

    abrir = c.get(endereco)
    assert abrir.status_code == 302 and abrir.headers["Location"] == ato


def test_o_rascunho_de_outra_tela_no_endereco_nao_sai(cg_casa_logada):
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    with db.transaction() as con:
        R.init_rascunho_schema(con)
        rid = R.salvar(con, tela="protesto_titulo_novo", dados={"cedente_nome": "ANA EXEMPLO"},
                       titulo="Título — ANA EXEMPLO", agora=AGORA, por="mario")["id"]
    corpo = {"csrf_token": _token(c, "/notas/atos/novo"), "tipo": "ESCRITURA"}
    assert c.post(f"/notas/atos/novo?rascunho_id={rid}", data=corpo).status_code == 302
    assert _um(db, "SELECT COUNT(*) FROM rascunhos_de_tela WHERE id=?", (rid,))[0] == 1


def test_o_arquivo_importado_de_novo_nao_traz_o_que_ja_virou_ato(cg_casa_logada):
    import importar_padrao as IMPP
    db = cg_casa_logada["db"]
    texto = json.dumps({"formato": IMPP.FORMATO, "versao": IMPP.VERSAO, "especie": "RCPN_ASSENTO",
                        "de_onde_veio": "DNVs digitalizadas",
                        "registros": [{"chave": "dnv-1", "especie": "NASCIMENTO", "nome": "PRIMEIRO EXEMPLO",
                                       "data_fato": "2026-10-01", "dnv": "30-11111111-1", "hora_fato": "08:00",
                                       "pessoas": [{"papel": "REGISTRADO", "nome": "PRIMEIRO EXEMPLO", "sexo": "M"},
                                                   {"papel": "MAE", "nome": "MAE EXEMPLO", "sexo": "F"},
                                                   {"papel": "PAI", "nome": "PAI EXEMPLO", "sexo": "M"},
                                                   {"papel": "AVO_MATERNA", "nome": "AVO EXEMPLO", "sexo": "F"}]}]},
                       ensure_ascii=False)
    with db.transaction() as con:
        rid = IMPP.para_rascunhos(con, texto, agora=AGORA, por="mario")["criados"][0]["rascunho_id"]
        R.virou_ato(con, rid, endereco="/rcpn/1", agora=AGORA, por="mario")
        de_novo = IMPP.para_rascunhos(con, texto, agora=AGORA, por="mario")
    assert de_novo["criados"] == [] and de_novo["ja_na_fila"] == ["dnv-1"]


def test_a_pasta_do_processo_aponta_para_o_ato(cg_casa_logada):
    import processo_pasta as PASTA
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    rid = _rascunho_das_notas(db)
    r = c.post(f"/rascunhos/{rid}/processo", data={"csrf_token": _token(c, "/rascunhos")})
    tid = int(re.search(r"/tarefas/(\d+)", r.headers["Location"]).group(1))
    with db.transaction() as con:
        R.virou_ato(con, rid, endereco="/notas/atos/77", agora=AGORA, por="mario")
    with db.connect() as con:
        vinculo = next(v for v in PASTA.vinculos(con, tid) if v["tabela"] == "rascunhos_de_tela")
    assert "já virou ato" in vinculo["rotulo"] and vinculo["ato_url"] == "/notas/atos/77"
    html = c.get(f"/tarefas/{tid}").get_data(as_text=True)
    assert 'href="/notas/atos/77"' in html and 'name="apagar_rascunho"' not in html
    assert "O ato foi lavrado: concluir o processo" in html
