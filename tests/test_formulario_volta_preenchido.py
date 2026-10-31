"""O rascunho reabre em todas as telas, e a recusa do servidor não apaga o que foi digitado.

    «salvei um rascunho, mas não tenho como abrir ele no sistema»  — o oficial, 09/09/2026

O QUE ELES DEFENDEM
    Três defeitos do mesmo tipo: o que a pessoa digitou se perdia sem ela pedir.

    1. O botão «Salvar rascunho» estava em onze telas, e só três sabiam reabrir. Nas outras, «abrir» levava
       ao formulário em branco.
    2. O rascunho guardava só o primeiro valor de um nome repetido: o segundo devedor e as outras partes sumiam.
    3. A recusa do servidor redirecionava para a tela em branco.

    O risco do conserto é mudar a tela de quem só abre o formulário, ou o que vai ao gravar. Por isso aqui se
    cobra também que, sem nada digitado, o molde saia como sempre saiu.

    Tudo aqui roda sem banco, com os moldes de verdade sobre uma moldura vazia. O caminho inteiro, com o sistema
    de pé, está em `test_rascunho_abrir.py` e nos arquivos de cada tela, e roda na máquina do balcão.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from types import SimpleNamespace

import flask
import jinja2
import pytest
from werkzeug.datastructures import ImmutableMultiDict, MultiDict

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import rascunho_de_tela as R                                    # noqa: E402

_AMBIENTE = jinja2.Environment(autoescape=True, loader=jinja2.ChoiceLoader([
    jinja2.DictLoader({"base.html": "{% block heading %}{% endblock %}{% block content %}{% endblock %}",
                       "_serventia.html": ""}),
    jinja2.FileSystemLoader(str(RAIZ / "templates"))]))
_AMBIENTE.filters["centavos_reais"] = str
_AMBIENTE.filters["forte"] = lambda texto: texto


def _url(rota, **campos):
    return f"/{rota}" + (f"?rascunho_id={campos['rascunho_id']}" if campos.get("rascunho_id") else "")


_AMBIENTE.globals["url_for"] = _url


def _montar(molde: str, **contexto) -> str:
    padrao = {"csrf_token": "t", "VERSION": "1", "sv": {}, "session": {}, "fmt_date": str}
    return _AMBIENTE.get_template(molde).render(**{**padrao, **contexto})


def _form(*pares) -> MultiDict:
    return MultiDict(pares)


# ------------------------------------------------------------------- o que o rascunho guarda

def test_o_que_vem_uma_vez_continua_plano():
    dados = R.dados_do_envio(ImmutableMultiDict([("nome", "Ana Exemplo"), ("_tela", "x"), ("_titulo", "y")]))
    assert dados == {"nome": "Ana Exemplo"}


def test_o_nome_repetido_guarda_todos_na_ordem_e_com_o_vazio():
    """O documento vazio do primeiro devedor é o que mantém o do segundo no segundo."""
    dados = R.dados_do_envio(ImmutableMultiDict([
        ("devedor_nome", "Ana Exemplo"), ("devedor_nome", "João Modelo"),
        ("devedor_documento", ""), ("devedor_documento", "00000000191")]))
    assert dados["_repetidos"] == {"devedor_nome": ["Ana Exemplo", "João Modelo"],
                                   "devedor_documento": ["", "00000000191"]}


def test_quem_le_dados_recebe_um_texto_o_primeiro_preenchido():
    """É o que os leitores sempre receberam, quando o valor vazio nem chegava à rota."""
    dados = R.dados_do_envio(ImmutableMultiDict([
        ("devedor_documento", ""), ("devedor_documento", "00000000191"), ("vazio", ""), ("vazio", " ")]))
    assert dados["devedor_documento"] == "00000000191"
    assert dados["vazio"] == ""


def test_o_formulario_de_um_rascunho_antigo_tem_um_valor_por_nome():
    form = R.formulario({"dados": {"devedor_nome": "Ana Exemplo", "numero": 7, "nada": None}, "repetidos": {}})
    assert form.getlist("devedor_nome") == ["Ana Exemplo"]
    assert form.get("numero") == "7" and form.get("nada") == ""


def test_o_formulario_de_um_rascunho_novo_devolve_as_posicoes():
    form = R.formulario({"dados": {"devedor_documento": "00000000191", "numero": "1"},
                         "repetidos": {"devedor_documento": ["", "00000000191"]}})
    assert form.getlist("devedor_documento") == ["", "00000000191"]
    assert form.get("numero") == "1"


def test_ler_tira_a_chave_dos_repetidos_de_dados(monkeypatch):
    """Quem lê `dados` como dicionário plano não pode encontrar uma lista lá dentro."""
    guardado = {"id": 1, "tela": "t", "dados_json": '{"a": "1", "_repetidos": {"a": ["1", "2"]}}'}
    monkeypatch.setattr(R, "banco", lambda con: SimpleNamespace(um=lambda *_: guardado))
    lido = R.ler(None, 1)
    assert lido["dados"] == {"a": "1"} and lido["repetidos"] == {"a": ["1", "2"]}


@pytest.mark.parametrize("bruto", ["{isto nao e json", "[1, 2]", "null"])
def test_ler_o_que_nao_e_dicionario_avisa_e_nao_derruba(monkeypatch, bruto):
    guardado = {"id": 1, "tela": "t", "dados_json": bruto}
    monkeypatch.setattr(R, "banco", lambda con: SimpleNamespace(um=lambda *_: guardado))
    lido = R.ler(None, 1)
    assert lido["dados"] == {} and lido["repetidos"] == {} and lido["ilegivel"] is True


# ------------------------------------------------------------------- o ajudante das rotas

class _Db:
    def connect(self):
        return self

    def __enter__(self):
        return None

    def __exit__(self, *_):
        return False


@pytest.fixture(autouse=True)
def _nenhum_virou_ato(monkeypatch):
    """O rascunho que virou ato tem o seu arquivo: `test_rascunho_sai_ao_lavrar.py`."""
    monkeypatch.setattr(R, "o_ato_do_rascunho", lambda con, i: None)


def _app():
    app = flask.Flask(__name__)
    app.secret_key = "para o aviso"
    return app


def _lido(tela="t", chave="", **extra):
    return {"id": 3, "tela": tela, "chave": chave, "dados": {"a": "1"}, "repetidos": {"b": ["1", "2"]}, **extra}


def test_sem_rascunho_a_tela_recebe_o_formulario_do_pedido():
    with _app().test_request_context("/x"):
        form, rid = R.para_a_tela(_Db(), "t", "outra")
        assert rid is None and form is flask.request.form and not form


def test_abrindo_o_rascunho_da_tela(monkeypatch):
    monkeypatch.setattr(R, "ler", lambda con, i: {**_lido(), "dados": {"a": "1", "b": "1"}})
    with _app().test_request_context("/x?rascunho_id=3"):
        form, rid = R.para_a_tela(_Db(), "t", "outra")
        assert rid == 3 and form.get("a") == "1" and form.getlist("b") == ["1", "2"]
        assert "não é ato" in str(flask.get_flashed_messages())


def test_rascunho_de_outra_tela_e_recusado_e_nao_vaza(monkeypatch):
    monkeypatch.setattr(R, "ler", lambda con, i: _lido(tela="outra_tela"))
    with _app().test_request_context("/x?rascunho_id=3"):
        form, rid = R.para_a_tela(_Db(), "t", "Este rascunho não é daqui.")
        assert rid is None and not form
        assert flask.get_flashed_messages(with_categories=True) == [("danger", "Este rascunho não é daqui.")]


def test_a_chave_tem_de_ser_a_do_rascunho(monkeypatch):
    """A averbação guardada de uma pessoa não abre na ficha de outra."""
    monkeypatch.setattr(R, "ler", lambda con, i: _lido(chave="/rcpn/1/averbar"))
    with _app().test_request_context("/x?rascunho_id=3"):
        assert R.para_a_tela(_Db(), "t", "outra", chave="/rcpn/2/averbar")[1] is None
    with _app().test_request_context("/x?rascunho_id=3"):
        assert R.para_a_tela(_Db(), "t", "outra", chave="/rcpn/1/averbar")[1] == 3


def test_rascunho_que_nao_existe_avisa(monkeypatch):
    def nao_acha(con, i):
        raise R.RascunhoError("Não achei o rascunho #3.")
    monkeypatch.setattr(R, "ler", nao_acha)
    with _app().test_request_context("/x?rascunho_id=3"):
        assert R.para_a_tela(_Db(), "t", "outra")[1] is None
        assert "Não achei" in str(flask.get_flashed_messages())


def test_rascunho_ilegivel_abre_em_branco_e_salvar_nao_escreve_por_cima(monkeypatch):
    monkeypatch.setattr(R, "ler", lambda con, i: {**_lido(), "dados": {}, "ilegivel": True})
    with _app().test_request_context("/x?rascunho_id=3"):
        form, rid = R.para_a_tela(_Db(), "t", "outra")
        assert rid is None and not form
        assert "Não consegui ler" in str(flask.get_flashed_messages())


def test_no_post_vale_o_que_foi_digitado_e_o_rascunho_continua_aberto(monkeypatch):
    """A recusa volta com o que está na tela, e salvar de novo atualiza o mesmo rascunho."""
    monkeypatch.setattr(R, "ler", lambda con, i: _lido())
    with _app().test_request_context("/x?rascunho_id=3", method="POST", data={"a": "digitado"}):
        form, rid = R.para_a_tela(_Db(), "t", "outra")
        assert rid == 3 and form.get("a") == "digitado"
        assert not flask.get_flashed_messages()


def test_no_post_o_endereco_de_outra_tela_nao_vira_rascunho_aberto(monkeypatch):
    monkeypatch.setattr(R, "ler", lambda con, i: _lido(tela="outra_tela"))
    with _app().test_request_context("/x?rascunho_id=3", method="POST", data={"a": "digitado"}):
        assert R.para_a_tela(_Db(), "t", "outra")[1] is None


# ------------------------------------------------------------------- a lista não promete o que não cumpre

def _rota_que_existe(rota, **campos):
    if rota == "rcpn_lancamento_novo":
        raise LookupError(rota)
    return f"/{rota}?rascunho_id={campos['rascunho_id']}"


def test_a_lista_abre_pela_rota_da_tela():
    assert R.endereco_de_abrir({"id": 5, "tela": "notas_ato_novo", "chave": ""}, _rota_que_existe) == "/notas_ato_novo?rascunho_id=5"


def test_a_tela_que_nao_existe_mais_fica_sem_link():
    assert R.endereco_de_abrir({"id": 5, "tela": "rcpn_lancamento_novo", "chave": ""}, _rota_que_existe) is None


@pytest.mark.parametrize("volta", ["/rcpn/7/averbar", "/rcpn/7/anotar", "/rcpn/7/retificar"])
def test_o_lancamento_do_civil_guarda_o_endereco_e_abre_por_ele(volta):
    chave = R.chave_da_tela(R.TELA_DO_LANCAMENTO, volta)
    assert chave == volta
    assert R.endereco_de_abrir({"id": 5, "tela": R.TELA_DO_LANCAMENTO, "chave": chave}, _rota_que_existe) == f"{volta}?rascunho_id=5"


@pytest.mark.parametrize("chave", ["", "//fora.exemplo/rcpn/1/averbar", "/rcpn/1/cancelar", "/rcpn/x/averbar", "javascript:alert(1)"])
def test_o_lancamento_com_outra_chave_nao_vira_link(chave):
    assert R.endereco_de_abrir({"id": 5, "tela": R.TELA_DO_LANCAMENTO, "chave": chave}, _rota_que_existe) is None


def test_a_chave_das_outras_telas_continua_a_que_veio():
    assert R.chave_da_tela("notas_ato_novo", "/notas/atos/novo", " 12 ") == "12"
    assert R.chave_da_tela(R.TELA_DO_LANCAMENTO, "/rcpn/1/cancelar", "") == ""


# ------------------------------------------------------------------- toda tela que salva sabe reabrir

def _telas_que_salvam() -> dict[str, str]:
    achadas = {}
    for molde in (RAIZ / "templates").glob("*.html"):
        if molde.name == "_rascunho.html":
            continue
        fonte = molde.read_text(encoding="utf-8")
        for chamada in re.findall(r"salvar_rascunho\(\s*'(\w+)'.*?\)\s*\}\}", fonte, re.S):
            achadas[chamada] = molde.name
    return achadas


def test_a_lista_de_telas_que_salvam_nao_encolheu():
    assert len(_telas_que_salvam()) >= 11


@pytest.mark.parametrize("molde", sorted(set(_telas_que_salvam().values())))
def test_a_macro_recebe_o_rascunho_aberto(molde):
    """Sem isto, salvar de novo cria um segundo rascunho, em vez de atualizar o primeiro."""
    fonte = (RAIZ / "templates" / molde).read_text(encoding="utf-8")
    chamada = re.search(r"salvar_rascunho\(\s*'\w+'.*?\)\s*\}\}", fonte, re.S).group(0)
    assert "rascunho_id=rascunho_id" in chamada


def _corpo_da_rota(endpoint: str) -> str:
    for arquivo in RAIZ.glob("*_web.py"):
        fonte = arquivo.read_text(encoding="utf-8")
        achou = re.search(rf"^    def {endpoint}\(.*?(?=^    @app\.route|\Z)", fonte, re.S | re.M)
        if achou:
            return achou.group(0)
    raise AssertionError(f"não achei a rota {endpoint}")


@pytest.mark.parametrize("tela", sorted(set(_telas_que_salvam()) - {R.TELA_DO_LANCAMENTO}))
def test_toda_rota_que_salva_le_o_rascunho(tela):
    """«Abrir» leva a `url_for(tela, rascunho_id=...)`. Rota que não o lê abre em branco, e foi esse o defeito."""
    assert "rascunho_id" in _corpo_da_rota(tela), f"{tela} salva e não reabre"


def test_o_lancamento_do_civil_le_o_rascunho_na_funcao_das_tres_rotas():
    fonte = (RAIZ / "atribuicoes_web.py").read_text(encoding="utf-8")
    trecho = fonte[fonte.index("def _rcpn_tela_lancamento("):fonte.index('@app.route("/rcpn/<int:assento_id>/averbar")')]
    assert "RASC.para_a_tela" in trecho and "chave=" in trecho


@pytest.mark.parametrize("rota", ["rascunho_salvar", "rascunho_salvar_e_abrir_processo"])
def test_as_duas_rotas_de_salvar_guardam_os_repetidos(rota):
    corpo = _corpo_da_rota(rota)
    assert "RASC.dados_do_envio(request.form)" in corpo
    assert "request.form.items()" not in corpo


def test_guardar_o_rascunho_nao_escolhe_o_protocolo_em_atendimento():
    """Ele leva o protocolo marcado na tela, e rascunho não é ato: quem passa a atender é o envio do ato."""
    fonte = (RAIZ / "gratuidade_comprovante_web.py").read_text(encoding="utf-8")
    gancho = fonte[fonte.index("def _protocolo_do_selo_escolhido"):fonte.index("def _seletor_do_selo")]
    assert '"rascunho_salvar"' in gancho and '"rascunho_salvar_e_abrir_processo"' in gancho


def test_o_script_leva_o_vazio_e_deixa_o_arquivo_de_fora():
    fonte = (RAIZ / "static" / "rascunho.js").read_text(encoding="utf-8")
    assert "valor instanceof File" in fonte
    assert "!String(valor).trim()" not in fonte, "tirar o vazio embaralha quem é quem nos campos repetidos"


# ------------------------------------------------------------------- título novo do Protesto

def _protesto(form=None, novo=False, rascunho_id=None):
    return _montar("atrib_protesto_novo.html", layout_novo=novo, especies=[], tipos_protesto={}, motivos={"1": "Falta de pagamento"},
                   endossos={}, moedas={"1": "Real"}, ufs=["MA", "PI"], cidade_da_casa="CIDADE EXEMPLO", uf_da_casa="MA",
                   form=form if form is not None else MultiDict(), rascunho_id=rascunho_id, csrf_token="t")


def _inputs(html: str, nome: str) -> list[str]:
    return re.findall(rf'<input name="{nome}"[^>]*>', html)


def test_sem_nada_digitado_o_devedor_sai_como_sempre_saiu():
    html = _protesto()
    assert all("value=" not in c for c in _inputs(html, "devedor_documento") + _inputs(html, "devedor_endereco")
               + _inputs(html, "devedor_bairro") + _inputs(html, "devedor_cep"))
    assert '<input name="devedor_cidade" value="CIDADE EXEMPLO">' in html and '<input name="devedor_cidade" value="">' in html
    assert html.count('<option value="MA" selected>') == 2 and '<option value="CNPJ" selected' not in html


def test_a_recusa_devolve_cada_campo_na_posicao_dele():
    html = _protesto(_form(("devedor_nome", "Ana Exemplo"), ("devedor_nome", "João Modelo"),
                           ("devedor_documento", ""), ("devedor_documento", "00000000191"),
                           ("devedor_documento_tipo", "CPF"), ("devedor_documento_tipo", "CNPJ"),
                           ("devedor_endereco", "Rua Um"), ("devedor_endereco", "Rua Dois"),
                           ("devedor_bairro", "Centro"), ("devedor_bairro", ""),
                           ("devedor_cep", ""), ("devedor_cep", "65000000"),
                           ("devedor_cidade", ""), ("devedor_cidade", "CIDADE B"),
                           ("devedor_uf", "PI"), ("devedor_uf", "MA")))
    documentos = _inputs(html, "devedor_documento")
    assert "value=" not in documentos[0] and 'value="00000000191"' in documentos[1]
    assert 'value="Rua Um"' in _inputs(html, "devedor_endereco")[0] and 'value="Rua Dois"' in _inputs(html, "devedor_endereco")[1]
    assert 'value="Centro"' in _inputs(html, "devedor_bairro")[0] and "value=" not in _inputs(html, "devedor_bairro")[1]
    assert "value=" not in _inputs(html, "devedor_cep")[0] and 'value="65000000"' in _inputs(html, "devedor_cep")[1]
    assert '<input name="devedor_cidade" value="">' in html, "a cidade que a pessoa apagou não volta com o valor de fábrica"
    assert '<input name="devedor_cidade" value="CIDADE B">' in html
    assert html.count('<option value="CNPJ" selected>') == 1
    assert html.index('<option value="PI" selected>') < html.index('<option value="MA" selected>')


@pytest.mark.parametrize("campo", ["devedor_nome", "devedor_documento", "devedor_endereco", "devedor_bairro", "devedor_cep", "devedor_cidade"])
def test_o_segundo_devedor_recolhido_abre_com_qualquer_campo_dele(campo):
    """Só com o documento ou o endereço, gravar ignora o devedor, e quem digitou tem de ver isso."""
    html = _protesto(_form((campo, ""), (campo, "algo")), novo=True)
    assert '<details class="cg-segundo-devedor" open>' in html


def test_o_tipo_de_documento_sozinho_nao_abre_o_segundo_devedor():
    html = _protesto(_form(("devedor_documento_tipo", "CPF"), ("devedor_documento_tipo", "CPF"), ("devedor_nome", "Ana Exemplo")), novo=True)
    assert '<details class="cg-segundo-devedor"><summary>' in html


def test_o_endereco_do_formulario_leva_o_rascunho_aberto():
    assert 'action="/protesto_titulo_novo?rascunho_id=9"' in _protesto(novo=True, rascunho_id=9)
    assert 'action="/protesto_titulo_novo"' in _protesto(novo=True)
    assert 'name="_rascunho_id" value="9"' in _protesto(rascunho_id=9)
    assert "_rascunho_id" not in _protesto()


# ------------------------------------------------------------------- selo e dinheiro

_RECEITA = {"itens": [{"preco": 100, "servico": 77, "codigo_tj": "16.45", "descricao": "Garantia", "vezes": 1, "motivo": ""},
                      {"preco": 200, "servico": 78, "codigo_tj": "16.46", "descricao": "Outro", "vezes": 1, "motivo": ""}],
            "medido_em": "2026", "por_faixa": [], "total_centavos": 300}


def _livro3(form=None, novo=False, partes=None, rascunho_id=None):
    return _montar("atrib_livro3_novo.html", layout_novo=novo, naturezas={"CEDULA": "Cédula"}, form=form if form is not None else MultiDict(),
                   itens_tabela=[("16.45", "Garantia")], papeis=[("EMITENTE", "Emitente"), ("CREDOR", "Credor")],
                   partes_digitadas=partes or [{}, {}], receita=_RECEITA, caixa={"id": 1, "data": "2026-10-31"},
                   protocolos=[{"id": 5, "numero": "n", "interessado": "Ana Exemplo"}, {"id": 6, "numero": "m", "interessado": "Carla"}],
                   rascunho_id=rascunho_id)


def test_sem_nada_digitado_o_quadro_de_cobranca_sai_como_sempre_saiu():
    html = _livro3()
    assert "<details>" in html.replace(" open", "") and "<details open>" not in html
    assert " checked" not in html and '<input name="pagador">' in html
    assert '<input name="selo" placeholder="AVESVD000000..." pattern="[A-Za-z0-9]*">' in html
    assert re.search(r'<option value="5">\s*n', html)


def test_o_rascunho_volta_com_o_selo_o_protocolo_e_a_cobranca():
    """O corpo que vai ao gravar é o que iria digitando: nada do dinheiro se perde calado, em quadro fechado."""
    html = _livro3(_form(("selo", "AVESVD000000"), ("protocolo_id", "6"), ("cobrar", "78"), ("pagador", "Ana Exemplo"), ("forma_pagamento", "PIX")))
    assert 'value="AVESVD000000"' in html
    assert re.search(r'<option value="6" selected>', html) and not re.search(r'<option value="5" selected>', html)
    assert "<details open>" in html, "fechado, a pessoa não veria o que vai ser cobrado"
    marcadas = re.findall(r'name="cobrar" value="(\d+)"[^>]*checked', html, re.S)
    assert marcadas == ["78"]
    assert 'value="Ana Exemplo"' in html and '<option value="PIX" selected>' in html


def test_o_protocolo_escolhido_aqui_nao_diz_que_ele_esta_sem_itens():
    """`protocolo_escolhido` traz a lista de itens; o `form` só marca a caixa."""
    assert "não tem mais" not in _livro3(_form(("protocolo_id", "6")))


def test_sem_caixa_aberto_a_cobranca_marcada_continua_sem_ir():
    html = _montar("atrib_livro3_novo.html", layout_novo=False, naturezas={}, form=_form(("cobrar", "78")), itens_tabela=[], papeis=[],
                   partes_digitadas=[{}], receita=_RECEITA, caixa=None, protocolos=[], rascunho_id=None)
    assert re.search(r'name="cobrar" value="78"\s+disabled', html.replace("\r\n", "\n"))


def _registro(form=None, rascunho_id=None):
    declaracoes = {"TD_C": SimpleNamespace(quadro="Livro C", campos=[("extrato", "Extrato")])}
    return _montar("atrib_registro_novo.html", series=[{"codigo": "TD_C", "nome": "C", "atribuicao": "RTD"}],
                   form=form if form is not None else MultiDict(), declaracoes_do_termo=declaracoes, enquadramento_sugerido="", rotulos_enquadramento={},
                   receita=_RECEITA, caixa={"id": 1, "data": "x"}, protocolos=[], rascunho_id=rascunho_id)


def test_as_declaracoes_do_termo_voltam_abertas_so_se_trazem_algo():
    assert '<details style="grid-column:1/-1">' in _registro()
    html = _registro(_form(("declaracao_extrato", "o extrato")))
    assert '<details style="grid-column:1/-1" open>' in html and 'value="o extrato"' in html


# ------------------------------------------------------------------- as outras telas

_NORMA = SimpleNamespace(
    INSTITUTOS=[{"chave": "RETIFICACAO", "nome": "Retificação", "o_que": "c", "artigo": "a", "requisito": "r"},
                {"chave": "SUPRIMENTO", "nome": "Suprimento", "o_que": "l", "artigo": "a", "requisito": "r"}],
    FORMAS_DO_PEDIDO=[{"chave": "ESCRITO", "nome": "Escrito", "inciso": "I", "exige": ""},
                      {"chave": "VERBAL", "nome": "Verbal", "inciso": "III", "exige": "t"}],
    QUEM_ASSINA=("o próprio interessado", "procurador"), PRAZO_DECISAO_DIAS_UTEIS=10)


def _ret_civil(form=None, rascunho_id=None):
    return _montar("rcpn_retificacao_nova.html", layout_novo=False, norma=_NORMA, form=form if form is not None else MultiDict(), rascunho_id=rascunho_id)


def test_a_retificacao_do_civil_sem_nada_digitado():
    html = _ret_civil()
    assert re.search(r'value="RETIFICACAO"\s+checked', html) and re.search(r'value="ESCRITO"\s+checked', html)
    assert not re.search(r'value="SUPRIMENTO"\s+checked', html) and not re.search(r'value="VERBAL"\s+checked', html)
    assert '<input type="text" name="requerente_nome" size="40" required>' in html


def test_a_retificacao_do_civil_volta_preenchida():
    html = _ret_civil(_form(("instituto", "SUPRIMENTO"), ("forma", "VERBAL"), ("termo_verbal", "o termo"), ("requerente_nome", "Ana Exemplo"),
                            ("requerente_documento", "00000000191"), ("assinado_por", "procurador"), ("o_que_se_pede", "o pedido"),
                            ("assento_descricao", "Livro A-1")), rascunho_id=4)
    assert re.search(r'value="SUPRIMENTO"\s+checked', html) and re.search(r'value="VERBAL"\s+checked', html)
    assert not re.search(r'value="RETIFICACAO"\s+checked', html)
    for trecho in (">o termo</textarea>", 'value="Ana Exemplo"', 'value="00000000191"', '<option value="procurador" selected>',
                   ">o pedido</textarea>", 'value="Livro A-1"', 'name="_rascunho_id" value="4"'):
        assert trecho in html, trecho


def _ret_ri(form=None, rascunho_id=None):
    return _montar("ri_retificacao_nova.html", layout_novo=False, matriculas=[{"id": 1, "numero": "10", "livro": "2"}, {"id": 2, "numero": "11", "livro": "2"}],
                   especies={"A": "Área", "G": "Georreferenciada"}, fundamentos={"I": "De ofício", "II": "A requerimento"},
                   form=form if form is not None else MultiDict(), rascunho_id=rascunho_id)


def test_a_retificacao_do_ri_sem_nada_digitado():
    html = _ret_ri()
    assert 'name="rural" value="1" checked' in html and 'name="rural" value="0" checked' not in html
    assert '<input name="numero" required placeholder="1/2026">' in html and "<option>CREA</option>" in html
    assert '<option value="1">10 (livro 2)</option>' in html


def test_a_retificacao_do_ri_volta_preenchida():
    html = _ret_ri(_form(("numero", "1/2026"), ("matricula_id", "2"), ("especie", "G"), ("fundamento", "II"), ("rural", "0"),
                         ("requerente_nome", "Ana Exemplo"), ("profissional_conselho", "CAU"), ("sigef_codigo", "ABC")), rascunho_id=2)
    for trecho in ('value="1/2026"', '<option value="2" selected>', '<option value="G" selected>', '<option value="II" selected>',
                   'name="rural" value="0" checked', 'value="Ana Exemplo"', "<option selected>CAU</option>", 'value="ABC"',
                   'name="_rascunho_id" value="2"'):
        assert trecho in html, trecho
    assert 'name="rural" value="1" checked' not in html


def _notas(form=None, rascunho_id=None):
    return _montar("notas_ato_novo.html", familia=None, familia_chave="", TIPOS_ATO={"ESCRITURA": "Escritura", "ATA": "Ata"}, modelos=[],
                   modelo_escolhido="", previsoes={}, hoje="2026-10-31", form=form, rascunho_id=rascunho_id)


def test_as_notas_sem_nada_digitado():
    html = _notas()
    assert '<option value="ESCRITURA">' in html and " selected>" not in html
    assert 'name="data" value="2026-10-31"' in html
    assert '<input name="interessado">' in html and '<input name="natureza">' in html


def test_as_notas_voltam_preenchidas():
    html = _notas(_form(("tipo", "ATA"), ("data", "2026-09-20"), ("interessado", "Ana Exemplo"), ("natureza", "Ata de ensaio")), rascunho_id=3)
    for trecho in ('<option value="ATA" selected>', 'name="data" value="2026-09-20"', 'value="Ana Exemplo"', 'value="Ata de ensaio"',
                   'name="_rascunho_id" value="3"'):
        assert trecho in html, trecho


def _lancamento(form=None, rascunho_id=None, pre=None):
    return _montar("atrib_rcpn_lancamento_novo.html", tipo="AVERBACAO", rotulos={"AVERBACAO": "Averbação"},
                   assento={"id": 1, "nome": "Ana Exemplo", "especie": "NASCIMENTO", "serie": "A"}, receita=_RECEITA, caixa={"id": 1, "data": "x"},
                   protocolos=[{"id": 5, "numero": "n", "interessado": "i"}], gratuidades=[{"codigo": "G1", "rotulo": "g"}],
                   naturezas_averbacao=[{"codigo_form": "NAT", "rotulo": "nat"}], form=form, rascunho_id=rascunho_id,
                   session={"rcpn_averbacao_preenchida": pre} if pre else {})


def test_o_lancamento_sem_nada_digitado():
    html = _lancamento()
    assert 'id="bloco-gratuidade" style="display:none;margin-top:10px"' in html
    assert 'id="selo_gratuito" value=""' in html and '<input name="selo">' in html and "<details>" in html


def test_o_lancamento_volta_preenchido_e_o_endereco_leva_o_rascunho():
    html = _lancamento(_form(("teor", "o teor inteiro"), ("fundamento", "o fundamento"), ("natureza_averbacao", "NAT"), ("selo", "SELO1"),
                             ("ato_gratuito", "1"), ("gratuidade_codigo", "G1"), ("motivo_gratuidade", "o motivo"), ("selo_gratuito", "1")), rascunho_id=8)
    for trecho in (">o teor inteiro</textarea>", 'value="o fundamento"', 'value="NAT" selected', 'value="SELO1"', 'value="G1" selected',
                   'value="o motivo"', 'id="selo_gratuito" value="1"', 'style="display:block;margin-top:10px"', 'action="/rcpn_lancar?rascunho_id=8"'):
        assert trecho in html, trecho
    assert re.search(r'id="ato_gratuito" checked', html)


def test_o_preenchimento_do_modelo_vem_antes_do_rascunho():
    html = _lancamento(_form(("teor", "do rascunho")), pre={"assento_id": 1, "teor": "do modelo", "fundamento": "f", "natureza": "NAT"})
    assert ">do modelo</textarea>" in html and "do rascunho" not in html


@pytest.mark.parametrize("campo, valor", [("rural_urbano", "URBANO"), ("area_unidade", "alqueire"),
                                          ("aberta_nome", "Pessoa que saiu da lista")])
def test_o_valor_gravado_fora_da_lista_continua_na_caixa(campo, valor):
    """Sem isto, gravar a correção de outro campo apagava o valor sem ninguém pedir."""
    html = _editar(m={campo: valor})
    assert re.search(rf'<option(?: value="{valor}")? selected>{valor}', html), campo


def test_o_valor_da_lista_nao_ganha_opcao_repetida():
    html = _editar(m={"rural_urbano": "R", "area_unidade": "ha"})
    assert html.count(">Rural</option>") == 1
    assert html.count(">ha</option>") == 1
    assert '<option value="R" selected>R</option>' not in html


def _editar(**extra):
    m = {"id": 3, "numero": "4100", "tipo_ficha": "ESTRUTURADA", "aberta_nome": "Mario Exemplo", "rural_urbano": "U", "area_unidade": "m2"}
    return _montar("ri_editar.html", layout_novo=False, m={**m, **extra.pop("m", {})}, versao_edicao="v",
                   delegatarios=[{"grupo": "Ofício", "nome": "Mario Exemplo", "titulo": "Oficial"}], **extra)


def test_a_correcao_sem_recusa_sai_como_sempre_saiu():
    html = _editar()
    assert 'certificação SIGEF...">' in html and "não está no cadastro" not in html


def test_a_correcao_recusada_devolve_o_motivo_e_mostra_o_nome_fora_da_lista():
    """Sem a linha do nome, a caixa cairia em «não informado», e gravar de novo apagaria o nome sem ninguém pedir."""
    html = _editar(m={"aberta_nome": "Pessoa de Fora", "logradouro": "Rua Digitada"}, aberta_recusada="Pessoa de Fora", motivo_digitado="o motivo digitado")
    assert '<option value="Pessoa de Fora" selected>Pessoa de Fora — não está no cadastro</option>' in html
    assert 'value="o motivo digitado"' in html and 'value="Rua Digitada"' in html


def _prenotar(form=None, novo=False, de_cx=None):
    return _montar("ri_protocolo.html", layout_novo=novo, rows=[], restam={}, espera_acao=lambda: [], de_cx=de_cx, busca="", situacao="",
                   hoje="2026-10-31", prazo=20, prazo_reurb=40, NATUREZAS_SAUIN=["Hipoteca"], MOTIVOS_DA_GRATUIDADE_DO_RI=[],
                   resumo={"total": 1, "abertos": 0, "vencidos": 0, "sem_apresentante": 0}, form=form)


def test_a_prenotacao_sem_nada_digitado():
    html = _prenotar()
    assert 'id="prenot_bloco_gratuidade" class="span2" style="display:none"' in html
    assert "Este selo será COBRADO" in html and 'id="prenot_reurb" value=""' in html
    assert "selected" not in html.split('name="livro_destino"')[1].split("</select>")[0]


@pytest.mark.parametrize("novo", [False, True])
def test_a_prenotacao_recusada_volta_preenchida(novo):
    html = _prenotar(_form(("livro_destino", "3"), ("matricula_numero", "8001"), ("apresentante", "Ana Exemplo"), ("apresentante_documento", "00000000191"),
                           ("natureza_titulo", "Hipoteca"), ("telefone", "123"), ("email", "ana@exemplo.invalid"), ("documento_descricao", "escritura"),
                           ("objeto", "o objeto"), ("anotacao", "a anotação"), ("reurb_tipo", "S"), ("reurb", "1"), ("isento", "1"), ("motivo_isencao", "o motivo")), novo=novo)
    for trecho in ('<option value="3" selected>', 'value="8001"', 'value="Ana Exemplo"', 'value="00000000191"', 'value="Hipoteca"', 'value="123"',
                   'value="ana@exemplo.invalid"', 'value="escritura"', ">o objeto</textarea>", 'value="a anotação"', '<option value="S" selected>',
                   'id="prenot_reurb" value="1"', "Este selo será ISENTO", 'style="display:block"', 'value="o motivo" required'):
        assert trecho in html, trecho
    assert re.search(r'id="prenot_isento" checked', html)


def test_a_prenotacao_vinda_do_protocolo_geral_prefere_o_que_foi_digitado():
    geral = {"id": 7, "numero": "2026.10.7", "interessado": "Beatriz", "interessado_documento": "00000000191", "telefone": "(00) 0000-0000", "email": "b@exemplo.invalid"}
    assert 'value="Beatriz"' in _prenotar(de_cx=geral)
    html = _prenotar(_form(("apresentante", "Ana Exemplo"), ("telefone", "")), de_cx=geral)
    assert 'value="Ana Exemplo"' in html and 'value="Beatriz"' not in html
    assert 'name="cx_protocolo_id" value="7"' in html
    assert 'placeholder="(99) 99999-9999" value=""' in html, "o telefone que a pessoa apagou não volta sozinho"


# ------------------------------------------------------------------- o molde sem `form`

@pytest.mark.parametrize("montar", [lambda: _montar("rcpn_retificacao_nova.html", layout_novo=False, norma=_NORMA),
                                    lambda: _montar("ri_retificacao_nova.html", layout_novo=False, matriculas=[], especies={}, fundamentos={}),
                                    lambda: _prenotar(None),
                                    lambda: _notas(None),
                                    lambda: _lancamento(None)])
def test_o_molde_abre_mesmo_sem_receber_o_formulario(montar):
    assert "<form" in montar()
