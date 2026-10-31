"""Abrir título de Protesto, abrir matrícula, novo registro do Livro 3 e corrigir a matrícula, em passos.

O QUE ELES DEFENDEM
    Cada uma dessas telas era um formulário de dois a três monitores de altura, com o botão de gravar
    lá embaixo. No layout novo elas são passos, e continuam sendo UM formulário só. O risco de dividir é
    um campo ficar sem passo: ele sumiria da tela sem erro nenhum. O outro é o botão de gravar morar num
    passo: quem está em outro não acharia. E quem continua no layout antigo tem de ver a tela de sempre.

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
from werkzeug.datastructures import MultiDict

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))


def _montar(molde: str, **contexto) -> str:
    """O molde de verdade sobre uma moldura vazia: o que se confere aqui é o conteúdo da tela."""
    env = jinja2.Environment(autoescape=True, loader=jinja2.ChoiceLoader([
        jinja2.DictLoader({"base.html": "{% block content %}{% endblock %}"}),
        jinja2.FileSystemLoader(str(RAIZ / "templates"))]))
    env.filters["centavos_reais"] = str
    env.globals["url_for"] = lambda rota, **campos: f"/{rota}" + (f"/{campos['filename']}" if "filename" in campos else "")
    return env.get_template(molde).render(csrf_token="t", sv={}, VERSION="1", **contexto)


class _Leitor(HTMLParser):
    """Anota, de cada campo do formulário do ato, o passo em que mora e se está na barra ou recolhido."""

    CAIXAS = {"details", "summary", "section", "div", "form", "table", "label", "nav", "select", "span", "template"}
    CAMPOS = {"input", "select", "textarea"}

    def __init__(self):
        super().__init__()
        self.pilha, self.tortas, self.campos, self.portas, self.blocos, self.botoes = [], [], [], [], set(), []

    def _dentro(self, tag):
        return any(p[0] == tag for p in self.pilha)

    def _do_ato(self):
        return next((p[1] for p in self.pilha if p[0] == "form"), None)

    def _passo(self):
        return next((p[1]["data-passo"] for p in reversed(self.pilha) if "data-passo" in p[1]), None)

    def _na_barra(self):
        return any("cg-gravar" in (p[1].get("class") or "") for p in self.pilha)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "data-passo" in a:
            self.blocos.add(a["data-passo"])
        if "data-passo-ir" in a:
            self.portas.append(a["data-passo-ir"])
        form = self._do_ato()
        de_rascunho = form is not None and "data-rascunho" in form
        if form is not None and not de_rascunho and not self._dentro("template"):
            if tag in self.CAMPOS and a.get("name"):
                self.campos.append({"nome": a["name"], "tipo": a.get("type", tag), "passo": self._passo(),
                                    "barra": self._na_barra(), "recolhido": self._dentro("details"),
                                    "obrigatorio": "required" in a or "pattern" in a})
            if tag == "button" and a.get("type") != "button":
                self.botoes.append({"passo": self._passo(), "barra": self._na_barra(), "classe": a.get("class", "")})
        if tag in self.CAIXAS:
            self.pilha.append((tag, a))

    def handle_endtag(self, tag):
        if tag in self.CAIXAS and (not self.pilha or self.pilha.pop()[0] != tag):
            self.tortas.append(tag)


def _ler(html: str) -> _Leitor:
    leitor = _Leitor()
    leitor.feed(html)
    return leitor


def _nomes(html: str) -> list[str]:
    return [c["nome"] for c in _ler(html).campos]


# ------------------------------------------------------------------- os moldes, com o que a rota entrega

def _protesto(novo=True, form=None):
    esp = [{"codigo": "DMI", "rotulo": "Duplicata", "vezes": 10, "desta_casa": True, "no_esquema": True},
           {"codigo": "NP", "rotulo": "Nota promissória", "vezes": 0, "desta_casa": False, "no_esquema": True}]
    return _montar("atrib_protesto_novo.html", layout_novo=novo, especies=esp, tipos_protesto={"1": "Comum"},
                   motivos={"1": "Falta de pagamento"}, endossos={"1": "Mandato"}, moedas={"1": "Real"},
                   ufs=["MA", "PI"], cidade_da_casa="CIDADE EXEMPLO", uf_da_casa="MA", form=form or MultiDict())


def _nova(novo=True, e_acervo=False, form=None, do_arquivo=None, rascunho_id=None):
    return _montar("ri_nova.html", layout_novo=novo, livro="2", proximo=4100, e_acervo=e_acervo,
                   do_arquivo=do_arquivo, rascunho_id=rascunho_id, form=form if form is not None else MultiDict())


def _livro3(novo=True, form=None, partes=None, protocolos=None):
    return _montar("atrib_livro3_novo.html", layout_novo=novo, naturezas={"CEDULA": "Cédula"}, form=form or MultiDict(),
                   itens_tabela=[("16.45", "Garantia")], papeis=[("EMITENTE", "Emitente"), ("CREDOR", "Credor")],
                   partes_digitadas=partes or [{}, {}], receita={"itens": [{"preco": 100, "servico": "X", "codigo_tj": "16.45",
                                                                         "descricao": "Garantia", "vezes": 1, "motivo": ""}],
                                                                "medido_em": "2026", "por_faixa": [], "total_centavos": 100},
                   caixa={"id": 1, "data": "2026-10-30"},
                   protocolos=protocolos if protocolos is not None else [{"id": 1, "numero": "1", "interessado": "Ana Exemplo"}])


def _editar(novo=True, tipo_ficha="ESTRUTURADA"):
    m = {"id": 3, "numero": "4100", "tipo_ficha": tipo_ficha, "aberta_nome": "Mario Exemplo", "rural_urbano": "U", "area_unidade": "m2"}
    return _montar("ri_editar.html", layout_novo=novo, m=m, versao_edicao="abc", campos=[],
                   delegatarios=[{"grupo": "Ofício", "nome": "Mario Exemplo", "titulo": "Oficial", "tratamento": "o"}])


TELAS = {
    "protesto": _protesto,
    "matricula": _nova,
    "matricula_de_acervo": lambda novo=True: _nova(novo, e_acervo=True),
    "livro3": _livro3,
    "editar": _editar,
    "editar_acervo": lambda novo=True: _editar(novo, tipo_ficha="ACERVO"),
}
ULTIMO = {"protesto": "apresentante", "matricula": "abertura", "matricula_de_acervo": "abertura", "livro3": "selo"}


# ------------------------------------------------------------------- nenhum campo se perde

@pytest.mark.parametrize("tela", sorted(TELAS))
def test_os_dois_layouts_mandam_os_mesmos_campos_na_mesma_ordem(tela):
    novo, antigo = _nomes(TELAS[tela](True)), _nomes(TELAS[tela](False))
    assert len(novo) > 15, "o leitor deixou de achar os campos"
    assert novo == antigo


@pytest.mark.parametrize("tela", sorted(TELAS))
@pytest.mark.parametrize("novo", [True, False])
def test_as_caixas_fecham_na_ordem(tela, novo):
    leitor = _ler(TELAS[tela](novo))
    assert not leitor.tortas and not leitor.pilha


@pytest.mark.parametrize("tela", sorted(TELAS))
def test_todo_campo_tem_passo_e_todo_passo_tem_porta(tela):
    """Campo sem passo fica à vista em todos, e bloco sem porta fica escondido para sempre."""
    leitor = _ler(TELAS[tela](True))
    sem_passo = [c["nome"] for c in leitor.campos if c["tipo"] != "hidden" and c["passo"] is None and not c["barra"]]
    assert not sem_passo
    assert leitor.blocos == set(leitor.portas)
    assert len(leitor.portas) == len(set(leitor.portas)) >= 3


@pytest.mark.parametrize("tela", sorted(TELAS))
def test_o_botao_de_gravar_fica_fora_dos_passos_na_barra_presa(tela):
    leitor = _ler(TELAS[tela](True))
    assert len(leitor.botoes) == 1
    assert leitor.botoes[0]["passo"] is None and leitor.botoes[0]["barra"]
    assert "primary" in leitor.botoes[0]["classe"]


@pytest.mark.parametrize("tela", sorted(TELAS))
def test_sem_o_script_nao_aparece_botao_que_nao_faz_nada(tela):
    html = TELAS[tela](True)
    if "data-passo-avancar>" in html:
        assert 'class="cg-passos-fim" hidden data-cg-passos-fim' in html
    assert "fases.js" in html


# ------------------------------------------------------------------- o que cada tela pede

@pytest.mark.parametrize("tela", sorted(ULTIMO))
def test_o_ultimo_passo_e_o_ultimo_da_regua(tela):
    assert _ler(TELAS[tela](True)).portas[-1] == ULTIMO[tela]


def test_o_selo_e_a_cobranca_do_livro3_ficam_no_ultimo_passo():
    por_nome = {c["nome"]: c["passo"] for c in _ler(_livro3()).campos}
    for nome in ("natureza_titulo", "codigo_tj", "base_calculo", "selo", "protocolo_id", "cobrar", "pagador",
                 "forma_pagamento", "gerar_arquivamento", "folhas_arquivamento"):
        assert por_nome[nome] == "selo", nome


def test_a_matricula_diz_do_selo_no_ultimo_passo():
    for html in (_nova(), _nova(e_acervo=True)):
        trecho = re.search(r'<div class="notice small span2" data-passo="(\w+)">\s*(O selo do Registro|Ficha de acervo)', html)
        assert trecho and trecho.group(1) == "abertura"


def test_ficha_de_acervo_nao_tem_o_passo_do_proprietario():
    assert "proprietario" not in _ler(_nova(e_acervo=True)).portas
    assert 'name="proprietario_nome"' not in _nova(e_acervo=True)
    assert 'class="cg-acao-aviso' not in _nova(e_acervo=True)
    assert "proprietario" in _ler(_nova()).portas


def test_a_barra_avisa_de_quem_ficou_vazio_por_estar_em_outro_passo():
    """O botão está à vista desde o primeiro passo: o que não é obrigatório pode ficar para trás."""
    assert "O proprietário ainda está vazio" in _nova()
    assert "#form-do-ato:has([name=proprietario_nome]:placeholder-shown)" in _nova()
    assert 'placeholder="nome completo de quem figura como dono na abertura"' in _nova()
    assert "O apresentante ainda está vazio" in _protesto()
    assert "#form-do-ato:valid:has([name=apresentante_nome]:placeholder-shown)" in _protesto()
    assert 'placeholder="O credor, ou quem o representa"' in _protesto()
    assert "O item da tabela ainda está vazio" in _livro3()


def test_antes_do_ultimo_passo_quem_chama_a_atencao_e_avancar():
    regra = (RAIZ / "templates" / "_passos_e_gravar.html").read_text(encoding="utf-8")
    assert ".cg-gravar:has(.cg-passos-fim:not([hidden]) [data-passo-avancar]:not([hidden])) button:not([type=button])" in regra


def test_o_motivo_da_correcao_fica_na_barra_e_nao_num_passo():
    """É obrigatório: num passo fechado, o botão parece não fazer nada."""
    motivo = next(c for c in _ler(_editar()).campos if c["nome"] == "motivo")
    assert motivo["barra"] and motivo["passo"] is None


def test_a_correcao_nao_tem_numero_e_nao_tem_avancar():
    html = _editar()
    assert "cg-fase-n" not in html and "data-passo-avancar>" not in html
    assert 'id="form-da-retificacao"' in html and 'data-cg-passos="form-da-retificacao"' in html


@pytest.mark.parametrize("tela", ["protesto", "matricula", "livro3", "editar"])
def test_o_passo_guardado_e_o_desta_tela(tela):
    """`fases.js` guarda o passo por id e endereço do formulário: sem endereço, três telas dividiriam a guarda."""
    assert re.search(r'<form method="post"[^>]* action="/[a-z0-9_]+"', TELAS[tela](True))


# ------------------------------------------------------------------- o segundo devedor recolhido

def test_o_segundo_devedor_vem_recolhido_e_o_primeiro_nao():
    campos = _ler(_protesto()).campos
    nomes = [c for c in campos if c["nome"] == "devedor_nome"]
    assert [c["recolhido"] for c in nomes] == [False, True]
    assert '<details class="cg-segundo-devedor"><summary>' in _protesto()


def test_nada_recolhido_pode_ser_recusado_pelo_navegador():
    """Campo inválido em quadro fechado: o navegador recusa e não tem onde pôr o foco."""
    for tela in TELAS:
        for c in _ler(TELAS[tela](True)).campos:
            if c["recolhido"]:
                assert not c["obrigatorio"], (tela, c["nome"])


def test_o_segundo_devedor_volta_aberto_quando_a_tela_o_trazia():
    form = MultiDict([("devedor_nome", "João Modelo"), ("devedor_nome", "Ana Exemplo")])
    assert '<details class="cg-segundo-devedor" open>' in _protesto(form=form)
    assert 'value="Ana Exemplo"' in _protesto(form=form)
    so_um = MultiDict([("devedor_nome", "João Modelo"), ("devedor_nome", " ")])
    assert '<details class="cg-segundo-devedor"><summary>' in _protesto(form=so_um)


# ------------------------------------------------------------------- o preenchimento e o rascunho

def test_a_matricula_preenchida_pela_importacao_traz_os_valores_em_todos_os_passos():
    valores = {"logradouro": "RUA DAS FLORES", "descricao_perimetro": "Perímetro do arquivo", "teor": "Teor do arquivo",
               "proprietario_nome": "Ana Exemplo", "rural_urbano": "R"}
    html = _nova(form=valores, do_arquivo={"chave": "V-1", "de_onde_veio": "Vizinha", "sem_campo_na_tela": [], "valores": valores})
    assert "Esta tela veio preenchida a partir de um arquivo" in html
    assert 'value="RUA DAS FLORES"' in html and 'value="Ana Exemplo"' in html
    assert "Perímetro do arquivo</textarea>" in html and "Teor do arquivo</textarea>" in html
    assert 'value="R" selected' in html
    assert "data-cg-passos" in html


def test_a_importacao_continua_lendo_os_campos_do_molde():
    """`importar_padrao.campos_da_tela` lê os `name=` do arquivo do molde: eles não podem sair dele."""
    fonte = (RAIZ / "templates" / "ri_nova.html").read_text(encoding="utf-8")
    achados = set(re.findall(r'name="([a-z0-9_]+)"', fonte))
    for nome in ("logradouro", "area_valor", "descricao_perimetro", "teor", "proprietario_nome", "cib", "folha"):
        assert nome in achados, nome
    assert 'name="' not in (RAIZ / "templates" / "_passos_e_gravar.html").read_text(encoding="utf-8")


def test_a_barra_nao_se_passa_pelo_bloco_do_rascunho():
    """`test_rascunho_em_todo_ato` acusa quem tem o atributo da macro sem chamar a macro."""
    assert "data-rascunho" not in (RAIZ / "templates" / "_passos_e_gravar.html").read_text(encoding="utf-8")


@pytest.mark.parametrize("tela", ["protesto", "matricula", "livro3"])
def test_o_rascunho_fica_fora_do_formulario_do_ato(tela):
    """Formulário dentro de formulário não existe, e o rascunho é um formulário à parte."""
    html = TELAS[tela](True)
    assert html.count("data-rascunho data-do-ato") == 1
    assert html.index("data-rascunho data-do-ato") < html.index('id="form-do-ato"')
    assert "rascunho_salvar" in html and "Salvar rascunho e continuar depois" in html


def test_o_rascunho_que_reabre_continua_sabendo_de_onde_veio():
    html = _nova(rascunho_id=7)
    assert 'name="_rascunho_id_tela" value="7"' in html
    assert 'name="_rascunho_id" value="7"' in html


# ------------------------------------------------------------------- o layout antigo

@pytest.mark.parametrize("tela", sorted(TELAS))
def test_no_antigo_nada_disso_aparece(tela):
    html = TELAS[tela](False)
    for marca in ("<style", "data-cg-passos", "cg-gravar", "cg-acao", "data-passo-ir", "fases.js", "<details class=\"cg-segundo"):
        assert marca not in html, marca
    assert ' action="/' not in re.search(r'<form method="post" class="[^"]+"[^>]*>', html).group(0)


def test_no_antigo_o_rascunho_continua_depois_do_aviso():
    assert _protesto(False).index("93% dos títulos") < _protesto(False).index("data-rascunho")
    assert _livro3(False).index("art. 178") < _livro3(False).index("data-rascunho")
    assert _nova(False).index('<section class="panel">') < _nova(False).index("data-rascunho")
    assert "<br><br>" in _protesto(False)


def test_no_antigo_os_botoes_continuam_como_eram():
    assert '<button class="button">Cadastrar título</button>' in _protesto(False)
    assert '<div class="actions" style="grid-column:1/-1">' in _protesto(False)
    assert '<button class="button">Registrar no Livro 3</button>' in _livro3(False)
    assert '<div class="span2"><button class="primary">Abrir matrícula</button></div>' in _nova(False)
    assert '<div class="span2"><button class="primary">Salvar alterações</button></div>' in _editar(False)
    assert "<strong>\n        Segundo devedor" in _protesto(False).replace("\r\n", "\n")


# ------------------------------------------------------------------- com o sistema de pé

def _token(html: str) -> str:
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


def _entrar(app, usuario: str):
    d = app.extensions["db"]
    try:
        d.create_user(usuario, "Operador Exemplo", "Senha#12345", "ADMIN")
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


def _campos_do_ato(html: str) -> list[str]:
    inicio = html.index('id="form-do-ato"')
    return re.findall(r'name="([^"]+)"', html[inicio:html.index("</form>", inicio)])


@pytest.mark.parametrize("endereco", ["/protesto/novo", "/registro-imoveis/nova", "/livro3/novo"])
def test_as_duas_molduras_mandam_os_mesmos_campos(cg_app, endereco):
    c = _entrar(cg_app, "passos_a")
    _layout(c, "antigo")
    antigo = c.get(endereco).get_data(as_text=True)
    assert "data-cg-passos" not in antigo
    _layout(c, "novo")
    novo = c.get(endereco).get_data(as_text=True)
    assert "data-cg-passos" in novo and "cg-gravar" in novo
    assert _campos_do_ato(antigo) == _campos_do_ato(novo)
    assert len(_campos_do_ato(novo)) > 15, "o varredor deixou de achar os campos"
    _layout(c, "antigo")
