"""As três telas longas no layout novo: o que espera em cima, o resto recolhido, nenhum campo perdido.

O QUE ELES DEFENDEM
    `/inacabados`, a CTP e o formulário do termo eram telas de rolar milhares de pixels. No layout
    novo a lista do que espera abre a tela, cada ato da CTP é um quadro recolhido, e «Ver como fica»
    responde acima dos campos. Nada disso pode mudar regra nem perder campo, e quem continua no
    layout antigo tem de ver a tela de sempre.

    A armadilha é a da CTP: um campo com valor recusado dentro de quadro recolhido faz o navegador
    recusar o envio sem dizer onde. O script do evento `invalid` abre o quadro. O formulário do termo
    foge dela de outro jeito: nenhum campo dele fica recolhido.

    A primeira parte monta os moldes de verdade sobre uma moldura vazia, e roda em qualquer máquina.
    A segunda usa o sistema de pé, e roda na máquina do balcão.
"""
from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path

import jinja2
import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))


def _montar(molde: str, **contexto) -> str:
    """O molde de verdade sobre uma moldura vazia: o que se confere aqui é o conteúdo da tela."""
    fonte = (RAIZ / "templates" / molde).read_text(encoding="utf-8")
    env = jinja2.Environment(autoescape=True, loader=jinja2.DictLoader({
        "base.html": "{% block content %}{% endblock %}", molde: fonte}))
    env.filters["forte"] = lambda texto: texto
    return env.get_template(molde).render(url_for=lambda rota, **_: f"/{rota}", csrf_token="t", **contexto)


class _Leitor(HTMLParser):
    """Anota os campos, os que moram em quadro recolhido, e se as caixas fecham na ordem."""

    CAIXAS = {"details", "summary", "section", "div", "form", "table"}
    CAMPOS = {"input", "select", "textarea"}

    def __init__(self):
        super().__init__()
        self.pilha, self.campos, self.recolhidos, self.tortas = [], [], [], []

    def handle_starttag(self, tag, attrs):
        nome = dict(attrs).get("name")
        if tag in self.CAMPOS and nome:
            self.campos.append(nome)
            if "details" in self.pilha:
                self.recolhidos.append(nome)
        if tag in self.CAIXAS:
            self.pilha.append(tag)

    def handle_endtag(self, tag):
        if tag in self.CAIXAS and (not self.pilha or self.pilha.pop() != tag):
            self.tortas.append(tag)


def _ler(html: str) -> _Leitor:
    leitor = _Leitor()
    leitor.feed(html)
    return leitor


# ---------------------------------------------------------------- /inacabados

def _item(chave, rotulo, parado=False, erro=None):
    return {"chave": chave, "fonte": f"Fonte {chave}", "atribuicao": "Notas", "tabela": "nt_atos",
            "id": None if erro else 7, "rotulo": rotulo, "quando": "2026-10-01", "dias": None if erro else 3,
            "parado": parado, "tela": "tela_do_ato", "parametro": "ato_id", "anotacao": None, "erro": erro}


def _inacabados(novo=True, itens=(), fonte=None):
    chaves = sorted({i["chave"] for i in itens}) or ["a"]
    return _montar(
        "inacabados.html", layout_novo=novo, itens=list(itens), fonte_escolhida=fonte,
        atribuicao="", so_parados=False, atribuicoes=["Notas"],
        resumo=[{"chave": c, "fonte": f"Fonte {c}", "atribuicao": "Notas", "quantos": 1, "parados": 0,
                 "erro": None, "ligada": True, "dias": 7} for c in chaves],
        config={c: {"terminou": "quando termina"} for c in chaves})


def _grupos(html: str) -> list:
    return [(fonte, bool(aberto)) for aberto, fonte
            in re.findall(r"data-cg-inac-grupo( open)?>\s*<summary>(Fonte \w+)", html)]


def test_a_fonte_com_parado_vem_antes_e_so_a_primeira_abre():
    html = _inacabados(itens=[_item("a", "Mario"), _item("b", "Beatriz", parado=True),
                              _item("c", "Carla", parado=True)])
    assert _grupos(html) == [("Fonte b", True), ("Fonte c", False), ("Fonte a", False)]


def test_o_que_ninguem_espera_nao_abre_sozinho():
    html = _inacabados(itens=[_item("a", "Mario"), _item("b", "Beatriz")])
    assert _grupos(html) == [("Fonte a", False), ("Fonte b", False)]


def test_a_fonte_que_nao_deu_para_medir_fica_aberta_e_nao_conta_como_item():
    html = _inacabados(itens=[_item("a", "Mario"), _item("z", "", erro="a consulta falhou")])
    assert _grupos(html) == [("Fonte z", True), ("Fonte a", False)]
    assert "não deu para medir" in html and "a consulta falhou" in html
    assert "<strong>1</strong> em aberto" in html


def test_a_fonte_escolhida_abre_e_tem_o_caminho_de_volta():
    html = _inacabados(itens=[_item("a", "Mario")], fonte={"nome": "Fonte a", "chave": "a"})
    assert _grupos(html) == [("Fonte a", True)]
    assert "Ver todas as fontes" in html


@pytest.mark.parametrize("novo", [True, False])
def test_a_anotacao_do_item_continua_na_tabela(novo):
    anotado = dict(_item("a", "Mario"), anotacao={"texto": "esperando o papel", "responsavel": "Beatriz", "ate": "2026-11-05"})
    html = _inacabados(novo=novo, itens=[anotado])
    assert "esperando o papel" in html and "com Beatriz" in html and "até 2026-11-05" in html


def test_no_novo_a_lista_vem_antes_da_configuracao():
    html = _inacabados(itens=[_item("a", "Mario")])
    assert html.index("Mario") < html.index("Por onde ela olha") < html.index("Moldar o que fica")


def test_a_lista_vazia_aponta_para_onde_a_fonte_esta_nesta_ordem():
    html = _inacabados()
    assert "Nada em aberto por aqui" in html
    assert "confira abaixo, em «Por onde ela olha»" in html
    assert "confira acima" not in html


def test_no_antigo_a_lista_continua_depois_da_configuracao():
    html = _inacabados(novo=False, itens=[_item("a", "Mario")])
    assert "<details" not in html and "<style" not in html
    assert (html.index("medida na hora") < html.index("Por onde ela olha")
            < html.index("Moldar o que fica") < html.index("Tudo") < html.index("Mario"))
    assert "<th>Fonte</th>" in html
    assert "confira acima se a fonte" in _inacabados(novo=False)


# ---------------------------------------------------------------- CTP

def _linha(n, pendencias=(), doi=(), incluir=True, operacao="11", natureza="Compra e venda"):
    return {"ato": {"id": n, "data_ato": "2026-10-01", "natureza_titulo": natureza},
            "m": {"numero": 100 + n, "rural_urbano": "U"}, "partes": [], "dados": {"operacao": operacao},
            "incluir": incluir, "pendencias": list(pendencias), "entra": not pendencias, "origem_sugestao": "",
            "doi": {}, "doi_pendencias": list(doi), "acervo": False, "rotulo": f"R-{n}"}


def _ctp(novo=True, linhas=(), fechada=False, remessas=()):
    return _montar(
        "ri_ctp.html", layout_novo=novo, user={"role": "ADMIN"}, fmt_date=str, competencia="2026-10",
        meses=[], linhas=list(linhas), remessa={}, remessas=list(remessas), fechada=fechada, cns="000",
        ibge="0", prontos=0, com_pendencia=0, TIPO_OPERACAO={"11": "Compra e venda"},
        FORMA_PAGAMENTO={"1": "À vista"}, TIPO_IMOVEL_CTP={"71": "Terreno"}, MOTIVO_SEM_NI={"1": "Não consta"},
        TIPO_PARTE={"1": "Total"}, NATUREZA_TITULO_DOI={"1": "Escritura"})


def _quadros(html: str) -> list:
    return [(rotulo, bool(aberto)) for aberto, rotulo in re.findall(
        r'<details class="panel cg-ctp-quadro"( open)?>\s*<summary class="panel-head">\s*<span>\s*<strong>([^<]+)',
        html)]


REMESSA = {"competencia": "2026-09", "situacao": "FECHADA", "sem_transacoes": False, "quantidade": 1,
           "gerado_em": "2026-10-01", "conteudo": "", "arquivo_nome": ""}


def test_abre_so_o_primeiro_ato_que_espera():
    html = _ctp(linhas=[_linha(1), _linha(2, pendencias=["falta o valor"]), _linha(3, doi=["falta a folha"])])
    assert _quadros(html) == [("R-1", False), ("R-2", True), ("R-3", False)]


def test_o_que_falta_so_para_a_doi_tambem_espera_e_aparece_no_resumo():
    html = _ctp(linhas=[_linha(1), _linha(2, doi=["falta a folha"])])
    assert _quadros(html) == [("R-1", False), ("R-2", True)]
    assert "1 para a DOI" in html


def test_ato_sem_operacao_e_sem_natureza_espera_e_o_que_nao_e_transacao_nao():
    html = _ctp(linhas=[_linha(1, operacao="", natureza="Averbação"), _linha(2, operacao="", natureza="")])
    assert _quadros(html) == [("R-1", False), ("R-2", True)]


def test_ato_excluido_a_pedido_nao_abre_sozinho():
    html = _ctp(linhas=[_linha(1, pendencias=["falta o valor"], incluir=False), _linha(2)])
    assert _quadros(html) == [("R-1", False), ("R-2", False)]


def test_um_ato_so_ja_vem_aberto():
    assert _quadros(_ctp(linhas=[_linha(1)])) == [("R-1", True)]


def test_a_competencia_fechada_vem_toda_recolhida():
    html = _ctp(linhas=[_linha(1, pendencias=["falta o valor"]), _linha(2)], fechada=True)
    assert _quadros(html) == [("R-1", False), ("R-2", False)]


def test_ato_unico_de_competencia_fechada_abre_para_consulta():
    assert _quadros(_ctp(linhas=[_linha(1)], fechada=True)) == [("R-1", True)]


def test_o_campo_recolhido_continua_no_formulario_de_gravar():
    """Campo em quadro fechado vai no POST. Um formulário por ato faria o outro ato perder o digitado."""
    html = _ctp(linhas=[_linha(1), _linha(2)])
    assert html.count('<form method="post">') == 1
    assert html.index('<form method="post">') < html.index("i2_operacao") < html.index('value="salvar"')
    assert {"i1_operacao", "i1_data_negocio", "incluir_1", "i2_operacao"} <= set(_ler(html).recolhidos)


def test_o_campo_recusado_abre_o_quadro_dele():
    novo, antigo = _ctp(linhas=[_linha(1)]), _ctp(novo=False, linhas=[_linha(1)])
    assert 'addEventListener("invalid"' in novo and 'closest("details")' in novo
    assert novo.index('addEventListener("invalid"') > novo.index('value="salvar"')
    assert "addEventListener" not in antigo


def test_o_aviso_da_censec_fica_a_vista_ate_a_primeira_remessa():
    antes = _ctp(linhas=[_linha(1)])
    assert antes.index("Confira duas coisas") < antes.index('class="filters"')
    depois = _ctp(linhas=[_linha(1)], remessas=[REMESSA])
    assert depois.index("Sobre esta carga") < depois.index("Confira duas coisas")
    assert depois.index("Sobre esta carga") < depois.index("Carga mensal para a")


def test_as_remessas_ficam_recolhidas_com_a_contagem():
    html = _ctp(linhas=[_linha(1)], remessas=[REMESSA, REMESSA])
    assert re.search(r"<summary[^>]*><span>Remessas</span><span[^>]*>2</span></summary>", html)


def test_no_antigo_o_quadro_continua_aberto_e_os_avisos_em_cima():
    html = _ctp(novo=False, linhas=[_linha(1), _linha(2, doi=["falta a folha"])], remessas=[REMESSA])
    assert "<details" not in html and "cg-ctp-quadro" not in html and "<style" not in html
    assert html.count('<section class="panel">') == 4
    assert html.index("Carga mensal para a") < html.index("Confira duas coisas") < html.index('class="filters"')
    assert "para a DOI</span>" not in html


# ---------------------------------------------------------------- o formulário do termo

CAMPOS_DO_TERMO = [
    {"nome": "nome", "rotulo": "Nome", "de_onde": "o documento", "exigido": True, "artigo": "art. 1", "tipo": "", "ajuda": ""},
    {"nome": "sexo", "rotulo": "Sexo", "de_onde": "", "exigido": False, "artigo": "", "tipo": "sexo", "ajuda": ""},
    {"nome": "frase_gemeo", "rotulo": "Frase", "de_onde": "", "exigido": False, "artigo": "", "tipo": "", "ajuda": "uma ajuda"},
    {"nome": "escrevente", "rotulo": "Quem assina", "de_onde": "", "exigido": True, "artigo": "", "tipo": "", "ajuda": ""},
    {"nome": "sem_ajuda", "rotulo": "Sem ajuda", "de_onde": "", "exigido": False, "artigo": "", "tipo": "", "ajuda": ""},
]


def _formulario(novo=True, **mais):
    contexto = dict(
        modelo={"nome": "Termo de exemplo", "livro": "A", "artigo": "art. 2", "conferido_no_papel": False, "fonte": "A norma."},
        campos=CAMPOS_DO_TERMO, valores={}, montado="", em_branco=[],
        tipos=[{"chave": "NASCIMENTO", "nome": "Teor um", "quando": "sempre", "porque_falta": ""}],
        tem_texto=lambda _tipo: True, conta={"prontos": 1, "total": 4}, conferindo=None, aviso_conf="",
        numero_conf="", faltas=[], vem_de_fora=("escrevente",), conferivel=True, aviso_corpo="",
        slug_novo="nascimento", chave_do_catalogo="RC_TERMO_NASCIMENTO")
    contexto.update(mais)
    return _montar("rcpn_formulario.html", layout_novo=novo, **contexto)


def test_ver_como_fica_responde_acima_dos_campos_so_no_novo():
    novo = _formulario(montado="O TERMO MONTADO", em_branco=["nome"])
    assert novo.index("Como o termo fica") < novo.index("O TERMO MONTADO") < novo.index('name="nome"')
    assert "Ainda em branco:" in novo
    antigo = _formulario(novo=False, montado="O TERMO MONTADO")
    assert antigo.index('name="nome"') < antigo.index("Como o termo fica")


@pytest.mark.parametrize("novo", [True, False])
def test_a_regex_dos_relatos_continua_achando_o_termo(novo):
    html = _formulario(novo=novo, montado="O TERMO MONTADO")
    assert re.search(r"Como o termo fica</h2>\s*<pre[^>]*>O TERMO MONTADO</pre>", html)


def test_nenhum_campo_do_termo_fica_recolhido():
    """O único campo em quadro recolhido é o número da conferência, com o botão dele ao lado."""
    assert _ler(_formulario()).recolhidos == ["assento"]


def test_a_explicacao_do_campo_fica_a_um_clique_sem_se_perder():
    html = _formulario()
    assert html.count("<summary>De onde vem</summary>") == 3
    assert "o documento" in html and "uma ajuda" in html and "Vem de quem está na tela" in html


@pytest.mark.parametrize("novo", [True, False])
def test_quem_assina_continua_sem_se_digitar(novo):
    assert re.search(r'name="escrevente"[^>]*readonly', _formulario(novo=novo))


@pytest.mark.parametrize("novo", [True, False])
def test_as_saidas_da_tela_continuam(novo):
    html = _formulario(novo=novo)
    assert "Lavrar um registro com este termo" in html and "Mudar o texto deste termo" in html


def test_a_conferencia_com_numero_abre_acima_dos_campos():
    html = _formulario(numero_conf="12", aviso_conf="Não achei este assento.")
    assert re.search(r"<details[^>]* open>\s*<summary>Conferir com um assento real", html)
    assert html.index("Não achei este assento.") < html.index('name="nome"')


def test_sem_numero_a_conferencia_fica_recolhida_abaixo_dos_campos():
    html = _formulario()
    assert not re.search(r"<details[^>]* open>", html)
    assert html.index('name="nome"') < html.index("Conferir com um assento real")


def test_o_que_diz_que_o_modelo_tem_defeito_nunca_fica_recolhido():
    html = _formulario(faltas=["um claro sem campo"], aviso_corpo="o texto não fecha")
    primeiro_quadro = html.index("<details")
    assert html.index("O modelo e o formulário não batem") < primeiro_quadro
    assert html.index("O texto editado deste termo tem um erro") < primeiro_quadro


def test_no_novo_o_que_nao_e_do_dia_fica_recolhido():
    html = _formulario()
    for titulo in ("Conferir com um assento real", "Os teores deste ato", "De onde vêm este texto e estes campos"):
        assert re.search(r"<details class=\"panel cg-termo-grupo\">\s*<summary>" + titulo, html), titulo
    assert "Livro A" in html and "art. 2" in html


def test_no_antigo_a_ordem_continua_a_de_sempre():
    html = _formulario(novo=False, montado="O TERMO MONTADO", faltas=["um claro sem campo"])
    assert "<details" not in html and "<style" not in html and "cg-termo" not in html
    ordem = ["Livro A", "O modelo e o formulário não batem", 'name="nome"', "Ver como fica", "E agora?",
             "Como o termo fica", "Conferir com um assento real", "Os teores deste ato", "Os campos deste formulário"]
    posicoes = [html.index(texto) for texto in ordem]
    assert posicoes == sorted(posicoes), ordem


# ---------------------------------------------------------------- as três juntas

TRES_TELAS = {
    "inacabados": lambda novo: _inacabados(novo=novo, itens=[_item("a", "Mario"), _item("b", "Beatriz", parado=True)]),
    "ctp": lambda novo: _ctp(novo=novo, linhas=[_linha(1), _linha(2, pendencias=["falta o valor"])], remessas=[REMESSA]),
    "formulario": lambda novo: _formulario(novo=novo, montado="O TERMO MONTADO", numero_conf="12"),
}


@pytest.mark.parametrize("tela", sorted(TRES_TELAS))
def test_os_dois_layouts_mandam_os_mesmos_campos(tela):
    """Reordenar é só no novo. Campo que some de um layout é dado que deixa de chegar à rota."""
    novo, antigo = _ler(TRES_TELAS[tela](True)), _ler(TRES_TELAS[tela](False))
    assert sorted(novo.campos) == sorted(antigo.campos)


@pytest.mark.parametrize("tela", sorted(TRES_TELAS))
@pytest.mark.parametrize("novo", [True, False])
def test_as_caixas_fecham_na_ordem(tela, novo):
    leitor = _ler(TRES_TELAS[tela](novo))
    assert not leitor.pilha and not leitor.tortas, (leitor.pilha, leitor.tortas)


# ------------------------------------------------------------- com o sistema de pé

def _token(html: str) -> str:
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


def _entrar(app, usuario: str, papel: str = "ADMIN"):
    d = app.extensions["db"]
    try:
        d.create_user(usuario, "Operador Exemplo", "Senha#12345", papel)
    except Exception:                                              # noqa: BLE001
        pass
    c = app.test_client()
    c.post("/login", data={"username": usuario, "password": "Senha#12345",
                           "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return c


def _layout(c, qual: str) -> None:
    c.post("/preferencias/layout", data={
        "layout": qual, "next": "/", "csrf_token": _token(c.get("/").get_data(as_text=True))})


CAMINHOS = ["/inacabados", "/inacabados?so_parados=1", "/rcpn/formulario/NASCIMENTO", "/rcpn/formulario/CASAMENTO",
            "/rcpn/formulario/OBITO", "/rcpn/formulario/LIVRO_E", "/rcpn/formulario/OBITO?assento=999999"]
CAMINHO_DA_CTP = "/registro-imoveis/ctp?competencia=2026-10"


@pytest.mark.parametrize("papel,caminho", [("ADMIN", c) for c in (*CAMINHOS, CAMINHO_DA_CTP)]
                         + [("USER", c) for c in CAMINHOS] + [("AUDITOR", CAMINHO_DA_CTP)])
def test_a_tela_abre_nos_dois_layouts(cg_app, papel, caminho):
    """Cada papel só nas telas que ele já abria: o balcão não abre a CTP, e o auditor só abre a CTP."""
    c = _entrar(cg_app, f"longas_{papel.lower()}", papel)
    for qual in ("novo", "antigo"):
        _layout(c, qual)
        assert c.get(caminho).status_code == 200, (caminho, papel, qual)


def test_na_tela_de_pe_ver_como_fica_responde_acima_dos_campos(cg_app):
    c = _entrar(cg_app, "longas_ver")
    _layout(c, "novo")
    pagina = c.get("/rcpn/formulario/CASAMENTO").get_data(as_text=True)
    html = c.post("/rcpn/formulario/CASAMENTO", data={
        "csrf_token": _token(pagina), "acao": "ver"}).get_data(as_text=True)
    assert html.index("Como o termo fica") < html.index('name="acao"')


def test_na_tela_de_pe_a_lista_vem_antes_da_configuracao_so_no_novo(cg_app):
    c = _entrar(cg_app, "longas_lista")
    _layout(c, "novo")
    html = c.get("/inacabados").get_data(as_text=True)
    corpo = html[html.index("O que começou e não terminou</h1>"):]
    assert corpo.index("em aberto") < corpo.index("<summary>Por onde ela olha") < corpo.index("<summary>Moldar o que fica")
    _layout(c, "antigo")
    html = c.get("/inacabados").get_data(as_text=True)
    assert "<summary>Por onde ela olha" not in html and "cg-inac-grupo" not in html
    assert html.index("Moldar o que fica") < re.search(r"Tudo\s*\(\d+\)", html).start()


def test_na_tela_de_pe_a_ctp_so_tem_o_script_no_novo(cg_app):
    c = _entrar(cg_app, "longas_ctp")
    _layout(c, "novo")
    assert 'addEventListener("invalid"' in c.get("/registro-imoveis/ctp?competencia=2026-10").get_data(as_text=True)
    _layout(c, "antigo")
    assert 'addEventListener("invalid"' not in c.get("/registro-imoveis/ctp?competencia=2026-10").get_data(as_text=True)
