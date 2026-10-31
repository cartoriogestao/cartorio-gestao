"""As telas longas de dinheiro, chave e automação no layout novo: o que espera em cima, o resto recolhido.

O QUE ELES DEFENDEM
    Carnê-leão e a configuração dele, NFS-e, as chaves que cobram a equipe, automação, selador e a ajuda
    eram telas de rolar milhares de pixels. No layout novo cada grupo é um quadro recolhido, com o título
    dizendo como está, e o que espera ação abre a tela. Nada disso pode mudar regra nem perder campo, quem
    continua no layout antigo tem de ver a tela de sempre, e **segredo não sobe para o título do quadro**.

    A armadilha mais cara aqui é a das caixas «Afirmo» das chaves de cobrança: sem elas o servidor recusa.
    Elas têm de morar no mesmo quadro do botão, à vista de quem grava.

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

ENSAIO_SENHA = "ENSAIO-senha-que-nao-sobe"
ENSAIO_USUARIO = "ensaio.usuario@exemplo.com.br"
ENSAIO_DESTINO = "mario@exemplo.com.br"
ENSAIO_SERVIDOR = "smtp.ensaio.exemplo.com.br"
ENSAIO_DOCUMENTO = "00000000191"
ENSAIO_TITULAR = "Ana Exemplo"
ENSAIO_IMPRESSAO = "AB:CD:EF:12:34"
ENSAIO_CHAVE_MASCARADA = "sk-…9f3a"
ENSAIO_CREDENCIAL = "credencial-do-cofre-de-ensaio"


def _montar(molde: str, **contexto) -> str:
    """O molde de verdade sobre uma moldura vazia: o que se confere aqui é o conteúdo da tela."""
    env = jinja2.Environment(autoescape=True, loader=jinja2.ChoiceLoader([
        jinja2.DictLoader({"base.html": "{% block content %}{% endblock %}",
                           "_serventia.html": "<section>TIMBRE DA SERVENTIA</section>"}),
        jinja2.FileSystemLoader(str(RAIZ / "templates"), encoding="utf-8")]))
    return env.get_template(molde).render(url_for=lambda rota, **_: f"/{rota}", csrf_token="t", **contexto)


class _Leitor(HTMLParser):
    """Anota os títulos dos quadros e os formulários, e se as caixas fecham na ordem."""

    CAIXAS = {"details", "summary", "section", "div", "form", "table", "tbody", "thead"}

    def __init__(self):
        super().__init__()
        self.pilha, self.tortas, self.quadros, self.formularios = [], [], [], []
        self.no_titulo = None
        self.form = None
        self.select = None
        self.textarea = None

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "details":
            self.quadros.append({"id": d.get("id"), "aberto": "open" in d, "titulo": "",
                                 "dentro": "details" in self.pilha})
        if tag == "summary":
            self.no_titulo = self.quadros[-1] if self.quadros else None
        if tag == "form":
            self.form = {"action": d.get("action"), "method": d.get("method"), "enctype": d.get("enctype"), "campos": []}
            self.formularios.append(self.form)
        if self.form is not None:
            if tag == "input":
                self.form["campos"].append(("input", d.get("name"), d.get("type"), d.get("value"), "checked" in d,
                                            "disabled" in d, "required" in d))
            elif tag == "select":
                self.select = ["select", d.get("name"), "required" in d, []]
                self.form["campos"].append(self.select)
            elif tag == "option" and self.select is not None:
                self.select[3].append((d.get("value"), "selected" in d))
            elif tag == "textarea":
                self.textarea = ["textarea", d.get("name"), "required" in d, ""]
                self.form["campos"].append(self.textarea)
            elif tag == "button":
                self.form["campos"].append(("button", d.get("name"), d.get("value"), d.get("type")))
        if tag in self.CAIXAS:
            self.pilha.append(tag)

    def handle_endtag(self, tag):
        if tag == "summary":
            self.no_titulo = None
        elif tag == "form":
            self.form = None
        elif tag == "select":
            self.select = None
        elif tag == "textarea":
            self.textarea = None
        if tag in self.CAIXAS and (not self.pilha or self.pilha.pop() != tag):
            self.tortas.append(tag)

    def handle_data(self, data):
        if self.no_titulo is not None:
            self.no_titulo["titulo"] += data
        if self.textarea is not None:
            self.textarea[3] += data

    def quadro(self, ident: str) -> dict:
        return next(q for q in self.quadros if q["id"] == ident)

    def ordem(self) -> list:
        return [q["id"] for q in self.quadros if q["id"]]

    def formularios_em_ordem_fixa(self) -> list:
        return sorted(repr(f) for f in self.formularios)


def _ler(html: str) -> _Leitor:
    leitor = _Leitor()
    leitor.feed(html)
    return leitor


def _corpo_do_quadro(html: str, ident: str) -> str:
    """O HTML entre a abertura do quadro e o fim dele, contando os quadros de dentro."""
    inicio = html.index(f'id="{ident}"')
    pos, nivel = inicio, 1
    while nivel:
        abre, fecha = html.find("<details", pos + 1), html.find("</details>", pos + 1)
        if abre != -1 and abre < fecha:
            nivel, pos = nivel + 1, abre
        else:
            nivel, pos = nivel - 1, fecha
    return html[inicio:pos]


def _reais(centavos) -> str:
    return f"{centavos / 100:.2f}".replace(".", ",")


def _percentual(bp) -> str:
    return f"{bp / 100:.2f}".replace(".", ",")


# ---------------------------------------------------------------- carnê-leão

CATEGORIAS = {"CUSTEIO": ("Custeio da serventia", True), "PESSOAL": ("Remuneração dos prepostos", True),
              "PESSOAL_TITULAR": ("Gasto pessoal", False), "OUTRAS": ("Outras", None)}


def _despesa(n, dedutivel=None, origem="Livro Diário"):
    return {"id": n, "dia": f"2026-09-{n:02d}", "descricao": f"ENSAIO-despesa {n}", "documento": f"NF {n}", "valor": 1000 * n,
            "origem": origem, "categoria_despesa": "", "sugerida": "CUSTEIO" if dedutivel is None else "",
            "sugere_dedutivel": True if dedutivel is None else None,
            "categoria_fiscal": "" if dedutivel is None else "CUSTEIO", "dedutivel": dedutivel,
            "marcado_por": "Mario" if dedutivel is not None else "", "marcado_em": ""}


def _receita(n, origem="Caixa"):
    return {"dia": f"2026-09-{n:02d}", "origem": origem, "id": n, "descricao": f"ENSAIO-receita {n}", "documento": "",
            "valor": 50000, "sem_discriminacao": 0, "fundos_estimados": 0}


def _apuracao(despesas=(), receitas=(), outras=(), avisos=(), imposto=23238):
    tabela = {"id": 1, "descricao": "ENSAIO-tabela", "vigencia_inicio": "2026-01-01", "fonte": "ENSAIO-fonte"}
    return {"competencia": "2026-09", "modo_deposito": "NO_USO", "receitas": list(receitas), "outras_entradas": list(outras),
            "caixa": 100, "deposito_na_conta": 0, "avulsas": 0, "receita": 695200, "sem_discriminacao": 0, "fundos_estimados": 0,
            "fundos": {"forma": "X", "percentual": "28,5"}, "deposito": {"recebido": 0, "convertido": 0, "devolvido": 0},
            "selo": {"receita": 690000, "atos": 3, "diferidos": 0, "isentos": 0, "sem_valor": 0}, "despesas": list(despesas),
            "dedutiveis": 268145, "nao_dedutiveis": 0, "a_classificar": 0, "excesso_anterior": 0, "base": 427055, "excesso": 0,
            "tabela": tabela if imposto is not None else None,
            "calculo": ({"faixa": 4, "aliquota_bp": 2250, "deduzir": 67549, "reducao": 0, "imposto_da_tabela": imposto}
                        if imposto is not None else None),
            "imposto": imposto, "avisos": list(avisos)}


def _carne(novo=True, despesas=(), receitas=(), outras=(), avisos=(), ano=(), imposto=23238, prazo=None, cfg=None):
    from datetime import date
    return _montar(
        "carne_leao.html", layout_novo=novo, a=_apuracao(despesas, receitas, outras, avisos, imposto),
        mes="2026-09", ano=list(ano), cfg=cfg if cfg is not None else {"carne_leao_lista_conferida": ""},
        prazo=prazo if prazo is not None else (date(2026, 10, 30), "referência 09/2026"),
        categorias=CATEGORIAS, modos={"NO_USO": "Quando o ato é praticado"}, aviso_lista="ENSAIO-aviso da lista",
        aviso_leiaute="ENSAIO-aviso do leiaute", reais=_reais, percentual=_percentual, hoje="2026-10-30")


CARNE_CHEIO = dict(despesas=[_despesa(1, True), _despesa(2), _despesa(3, True), _despesa(4), _despesa(5, None, "Avulso") | {"dedutivel": True, "categoria_fiscal": "CUSTEIO"}],
                   receitas=[_receita(1), _receita(2, "Avulso")],
                   outras=[{"id": 7, "dia": "2026-09-11", "descricao": "ENSAIO-outra entrada", "valor": 15000}],
                   avisos=["2 despesa(s) do mês ainda sem marcação", "1 «outra entrada» no caixa"],
                   ano=[{"competencia": "2026-09", "receita": 1, "selo": 1, "dedutiveis": 1, "excesso_anterior": 0, "a_classificar": 300, "base": 1, "imposto": 1}])


def test_despesa_a_classificar_abre_o_quadro_dela_antes_dos_numeros():
    leitor = _ler(_carne(**CARNE_CHEIO))
    assert leitor.ordem().index("despesas") < leitor.ordem().index("cl-numeros")
    assert leitor.quadro("despesas")["aberto"] and "2 a classificar" in leitor.quadro("despesas")["titulo"]
    assert not leitor.quadro("cl-numeros")["aberto"]


@pytest.mark.parametrize("novo", [True, False])
def test_despesa_sem_sugestao_nao_vem_marcada_com_a_primeira_opcao(novo):
    sem_sugestao = {**_despesa(1), "sugerida": "", "sugere_dedutivel": None}
    html = _carne(novo=novo, despesas=[sem_sugestao])
    assert html.count('<option value="">— escolha —</option>') == 2


@pytest.mark.parametrize("novo", [True, False])
def test_despesa_com_sugestao_continua_vindo_com_a_sugestao(novo):
    html = _carne(novo=novo, despesas=[_despesa(1)])
    assert '<option value="">— escolha —</option>' not in html
    assert re.search(r'<option value="1"\s+selected>dedutível</option>', html)


def test_a_despesa_a_classificar_vem_primeiro_na_lista():
    html = _carne(**CARNE_CHEIO)
    assert html.index("ENSAIO-despesa 2") < html.index("ENSAIO-despesa 1<")
    assert html.index("ENSAIO-despesa 4") < html.index("ENSAIO-despesa 1<")


def test_com_pendencia_as_ja_marcadas_e_as_receitas_ficam_num_quadro_de_dentro():
    html = _carne(**CARNE_CHEIO)
    leitor = _ler(html)
    assert leitor.quadro("cl-marcadas")["dentro"] and not leitor.quadro("cl-marcadas")["aberto"]
    assert "3 despesa(s)" in leitor.quadro("cl-marcadas")["titulo"]
    assert "ENSAIO-despesa 1<" in _corpo_do_quadro(html, "cl-marcadas")
    assert "ENSAIO-despesa 2" not in _corpo_do_quadro(html, "cl-marcadas")
    assert leitor.quadro("cl-as-receitas")["dentro"] and not leitor.quadro("cl-as-receitas")["aberto"]
    assert 'name="motivo"' in _corpo_do_quadro(html, "cl-as-receitas")


def test_sem_pendencia_nao_ha_quadro_de_dentro():
    leitor = _ler(_carne(despesas=[_despesa(1, True)], receitas=[_receita(1)]))
    assert "cl-marcadas" not in leitor.ordem() and "cl-as-receitas" not in leitor.ordem()


def test_a_despesa_ja_marcada_guarda_o_formulario_num_quadro_de_mudar():
    html = _carne(despesas=[_despesa(1, True)])
    assert "Mudar a marcação" in html
    assert 'name="categoria_fiscal"' in _corpo_do_quadro(html, "despesas")
    assert "Mudar a marcação" not in _carne(despesas=[_despesa(1)])


def test_sem_pendencia_abre_o_mes_em_numeros_primeiro():
    leitor = _ler(_carne(despesas=[_despesa(1, True)], receitas=[_receita(1)]))
    assert leitor.ordem()[:3] == ["cl-numeros", "despesas", "receitas"]
    assert leitor.quadro("cl-numeros")["aberto"]
    assert not leitor.quadro("despesas")["aberto"] and not leitor.quadro("receitas")["aberto"]
    assert "todas marcadas" in leitor.quadro("despesas")["titulo"]


def test_a_outra_entrada_sem_resposta_abre_as_receitas_e_vem_antes_da_tabela_delas():
    html = _carne(receitas=[_receita(1)], outras=CARNE_CHEIO["outras"], despesas=[_despesa(1, True)])
    leitor = _ler(html)
    assert leitor.ordem()[0] == "receitas" and leitor.quadro("receitas")["aberto"]
    assert html.index("É receita do titular") < html.index("ENSAIO-receita 1")


def test_o_aviso_do_mes_fica_a_vista_uma_vez_so():
    html = _carne(**CARNE_CHEIO)
    assert html.count("2 despesa(s) do mês ainda sem marcação") == 1
    assert html.index("2 despesa(s) do mês ainda sem marcação") < html.index("<details")
    assert html.index("Próximo prazo cadastrado") < html.index("<details")


@pytest.mark.parametrize("novo", [True, False])
def test_os_enderecos_para_onde_as_rotas_voltam_continuam(novo):
    html = _carne(novo=novo, **CARNE_CHEIO)
    for ancora in ("despesas", "receitas", "avulso"):
        assert f'id="{ancora}"' in html, ancora


def test_sem_tabela_o_titulo_diz_que_o_imposto_nao_foi_calculado():
    leitor = _ler(_carne(imposto=None))
    assert "imposto não calculado" in leitor.quadro("cl-numeros")["titulo"]


def test_no_antigo_a_ordem_do_carne_leao_continua_a_de_sempre():
    html = _carne(novo=False, **CARNE_CHEIO)
    ordem = ["O que esta conta é", "Próximo prazo cadastrado", "O mês em números", "2 despesa(s) do mês",
             "As duas receitas", "Receitas do mês", "ENSAIO-receita 1", "É receita do titular",
             "Despesas pagas no mês", "ENSAIO-despesa 1<", "ENSAIO-despesa 2", "Lançar no livro-caixa", "O ano de 2026"]
    posicoes = [html.index(texto) for texto in ordem]
    assert posicoes == sorted(posicoes), ordem


# ---------------------------------------------------------------- configuração do carnê-leão

def _tabela(n, vigencia, anulada=False, reducao=None):
    return {"id": n, "descricao": f"ENSAIO-tabela {n}", "vigencia_inicio": vigencia, "fonte": "ENSAIO-fonte",
            "cadastrada_por": "Mario", "cadastrada_em": "2026-09-30T10:00:00", "reducao": reducao,
            "anulada_em": "2026-09-30T11:00:00" if anulada else None, "motivo_anulacao": "ENSAIO-digitada errada" if anulada else "",
            "faixas": [{"ate": 242880, "aliquota_bp": 0, "deduzir": 0}, {"ate": None, "aliquota_bp": 2750, "deduzir": 90873}]}


def _carne_cfg(novo=True, tabelas=(), cfg=None):
    return _montar(
        "carne_leao_configuracao.html", layout_novo=novo, tabelas=list(tabelas),
        cfg=cfg if cfg is not None else {"carne_leao_prazo_regra": "ULTIMO_DIA_UTIL", "carne_leao_prazo_dia": "", "carne_leao_prazo_fonte": "ENSAIO-fonte",
                                         "carne_leao_fundos_forma": "A", "carne_leao_fundos_percentual": "28,5", "carne_leao_lista_conferida": ""},
        modos={"NO_USO": "Quando o ato é praticado"}, regras={"": "Não cadastrado", "ULTIMO_DIA_UTIL": "Último dia útil do mês seguinte"},
        formas_fundos={"A": "Sobre o emolumento"}, nacionais=[{"descricao": "ENSAIO-nacional", "vigencia_inicio": "2026-01-01", "fonte": "ENSAIO-fonte"}],
        categorias=CATEGORIAS, aviso_lista="ENSAIO-aviso da lista", reais=_reais, percentual=_percentual)


def test_sem_tabela_ativa_a_nacional_abre_em_primeiro_lugar():
    html = _carne_cfg()
    leitor = _ler(html)
    assert leitor.ordem()[0] == "cl-nacional" and leitor.quadro("cl-nacional")["aberto"]
    assert html.index("Nenhuma tabela ativa") < html.index("<details")


def test_tabela_toda_anulada_conta_como_sem_tabela():
    leitor = _ler(_carne_cfg(tabelas=[_tabela(3, "2024-02-01", anulada=True)]))
    assert leitor.ordem()[0] == "cl-nacional"
    assert "0 ativa(s) · 1 anulada(s)" in leitor.quadro("cl-tabelas")["titulo"]


def test_com_tabela_ativa_tudo_fica_recolhido_e_cada_tabela_e_um_quadro():
    html = _carne_cfg(tabelas=[_tabela(1, "2026-01-01"), _tabela(3, "2024-02-01", anulada=True)])
    leitor = _ler(html)
    assert not any(q["aberto"] for q in leitor.quadros)
    assert "já cadastrada" in leitor.quadro("cl-nacional")["titulo"]
    assert leitor.quadro("cl-tabela-1")["dentro"] and "anulada" in leitor.quadro("cl-tabela-3")["titulo"]
    assert "ENSAIO-digitada errada" in _corpo_do_quadro(html, "cl-tabela-3")
    assert 'name="tabela_id"' in _corpo_do_quadro(html, "cl-tabela-1")


def test_o_titulo_do_prazo_diz_quando_falta_a_fonte():
    leitor = _ler(_carne_cfg(cfg={"carne_leao_prazo_regra": "ULTIMO_DIA_UTIL", "carne_leao_prazo_fonte": "", "carne_leao_fundos_percentual": "28,5"}))
    assert "sem a fonte" in leitor.quadro("cl-prazo")["titulo"]


def test_no_antigo_a_ordem_da_configuracao_continua_a_de_sempre():
    html = _carne_cfg(novo=False, tabelas=[_tabela(1, "2026-01-01")])
    ordem = ["Prazo e fundos", "Lista de categorias dedutíveis", "Tabelas progressivas mensais", "A tabela nacional", "Cadastrar uma tabela"]
    posicoes = [html.index(texto) for texto in ordem]
    assert posicoes == sorted(posicoes), ordem
    assert "Nenhuma tabela ativa" not in _carne_cfg(novo=False)
    assert "Nenhuma tabela cadastrada" in _carne_cfg(novo=False)


# ---------------------------------------------------------------- NFS-e

CFG_NFSE = {"nfse_ligada": "1", "nfse_provedor": "nacional", "nfse_ambiente": "homologacao", "nfse_municipio": "2100000",
            "nfse_prestador_documento": ENSAIO_DOCUMENTO, "nfse_inscricao_municipal": "123", "nfse_codigo_tributacao": "210101",
            "nfse_codigo_municipal": "", "nfse_aliquota": "", "nfse_optante_simples": "1", "nfse_regime_especial": "4", "nfse_serie": "1",
            "nfse_exige_endereco": "1", "nfse_inicio": "", "nfse_percentual_ferj": "12,00", "nfse_codigo_nbs": "113040000",
            "nfse_convenio_ativo": "", "nfse_ibscbs_cst": "", "nfse_ibscbs_classificacao": "", "nfse_ibscbs_indicador_operacao": ""}
FALTAS_NFSE = ["A emissão de NFS-e está desligada (Gestor → NFS-e).", "Falta o código IBGE do município.",
               "Falta o CNPJ/CPF do prestador.", "Falta o certificado A1 da serventia."]
CERTIFICADO_BOM = {"titular": ENSAIO_TITULAR, "valido_ate": "2027-01-01", "vencido": False}


def _nfse(novo=True, cfg=None, faltas=(), avisos=(), certificado=None, parametros=None):
    return _montar(
        "nfse_gestor.html", layout_novo=novo, cfg=cfg if cfg is not None else dict(CFG_NFSE),
        rotulos={k: f"Rótulo {k}" for k in CFG_NFSE}, certificado=certificado, faltas=list(faltas),
        ambientes={"homologacao": "Homologação", "producao": "Produção"}, avisos=list(avisos),
        convenios={"": "Não conferido", "1": "Ativo", "0": "Não ativo"}, parametros=parametros,
        parametros_texto="{}", regimes={"4": "Notário ou registrador"}, opcoes_simples={"1": "Não optante"}, provedores=["nacional"])


def test_o_que_falta_abre_a_tela_e_abre_o_quadro_de_onde_vem():
    html = _nfse(cfg=CFG_NFSE | {"nfse_ligada": "0"}, faltas=FALTAS_NFSE, avisos=["ENSAIO-a conferir"])
    leitor = _ler(html)
    assert html.index("O que falta") < html.index("A conferir") < html.index("<details")
    assert leitor.ordem()[0] == "nfse-certificado"
    assert all(leitor.quadro(q)["aberto"] for q in ("nfse-certificado", "nfse-emissao", "nfse-prestador"))
    assert not any(leitor.quadro(q)["aberto"] for q in ("nfse-tributacao", "nfse-nota", "nfse-ibscbs", "nfse-parametros"))
    assert "DESLIGADA" in leitor.quadro("nfse-emissao")["titulo"]
    assert "falta o CNPJ/CPF" in leitor.quadro("nfse-prestador")["titulo"]


def test_sem_falta_tudo_fica_recolhido_e_o_certificado_vem_por_ultimo():
    leitor = _ler(_nfse(certificado=CERTIFICADO_BOM))
    assert not any(q["aberto"] for q in leitor.quadros)
    assert leitor.ordem()[-1] == "nfse-certificado"
    assert "válido até 2027-01-01" in leitor.quadro("nfse-certificado")["titulo"]


def test_o_certificado_vencido_ou_ilegivel_abre_o_quadro_dele():
    for certificado, frase in ((CERTIFICADO_BOM | {"vencido": True}, "vencido em"),
                               ({"titular": "", "valido_ate": "", "vencido": True, "erro": "ENSAIO-erro"}, "não deu para ler")):
        leitor = _ler(_nfse(certificado=certificado))
        assert leitor.quadro("nfse-certificado")["aberto"] and frase in leitor.quadro("nfse-certificado")["titulo"]


def test_o_titulo_nao_mostra_documento_nem_titular():
    leitor = _ler(_nfse(certificado=CERTIFICADO_BOM))
    titulos = " ".join(q["titulo"] for q in leitor.quadros)
    assert ENSAIO_DOCUMENTO not in titulos and ENSAIO_TITULAR not in titulos


def test_os_dados_fiscais_continuam_um_formulario_so():
    leitor = _ler(_nfse())
    formulario = next(f for f in leitor.formularios if any(c[1] == "nfse_ligada" for c in f["campos"]))
    nomes = {c[1] for c in formulario["campos"] if c[0] != "button"} - {"csrf_token", "acao"}
    assert nomes == set(CFG_NFSE)
    assert sum(1 for f in leitor.formularios if any(c[1] == "nfse_serie" for c in f["campos"])) == 1


def test_a_palavra_que_abre_o_quadro_esta_na_falta_de_verdade():
    """O quadro abre por uma palavra da falta: quem mudar a frase da falta tem de olhar o molde."""
    fonte = (RAIZ / "nfse.py").read_text(encoding="utf-8")
    assert "Falta o código IBGE do município." in fonte
    assert "Falta o CNPJ/CPF do prestador." in fonte
    assert "Falta o código de tributação nacional" in fonte
    custas = (RAIZ / "custas.py").read_text(encoding="utf-8")
    assert "Percentual do FERJ ilegível" in custas and "O percentual do FERJ fica entre" in custas


def test_no_antigo_a_ordem_da_nfse_continua_a_de_sempre():
    html = _nfse(novo=False, faltas=FALTAS_NFSE, avisos=["ENSAIO-a conferir"])
    ordem = ["emissor nacional", "O que falta", "A conferir", "Dados fiscais", "Reforma tributária", "Parâmetros do município", "Certificado A1"]
    posicoes = [html.index(texto) for texto in ordem]
    assert posicoes == sorted(posicoes), ordem


# ---------------------------------------------------------------- as chaves que cobram a equipe

def _chave(n, valor=None, padrao="14:00"):
    return {"chave": f"chave_de_ensaio_{n}", "nome": f"ENSAIO-chave {n}", "tipo": "HORA", "valor": valor, "padrao": padrao,
            "vale": valor or padrao, "cobra": "ENSAIO-cobra", "afrouxar": "ENSAIO-afrouxar", "opcoes": []}


QUADRO_COBRANCA = {"chaves": [_chave(1), _chave(2, "15:37"), _chave(3, "14:00"), _chave(4, "")],
                   "turnos": [{"id": 1, "login": "mario", "nome": "Mario", "papel": "ADMIN", "chave": "caixa_turno:mario", "turno": "18:00-23:30"},
                              {"id": 2, "login": "beatriz", "nome": "Beatriz", "papel": "USER", "chave": "caixa_turno:beatriz", "turno": ""}],
                   "fora": [("selo_trava_caixa", "ENSAIO-razão")], "fim_do_expediente": "14:00", "regra_da_afirmacao": "ENSAIO-regra da afirmação"}
HISTORICO = {"dias": 90, "desde": "2026-08-01", "cortado": False, "medido": True, "linhas": [
    {"id": 1, "ts": "2026-10-20T10:00:00", "quem": "Mario", "agente": "", "a_mando_de": "", "chave": "chave_de_ensaio_2", "nome": "ENSAIO-chave 2",
     "de": "14:00", "para": "15:37", "o_que": "ALTERADA", "acao": "X", "afrouxa": True, "motivo": "", "afirmacao": "ENSAIO-afirmação"},
    {"id": 2, "ts": "2026-10-21T10:00:00", "quem": "Beatriz", "agente": "", "a_mando_de": "", "chave": "chave_de_ensaio_1", "nome": "ENSAIO-chave 1",
     "de": "", "para": "99:99", "o_que": "RECUSADA", "acao": "X", "afrouxa": False, "motivo": "ENSAIO-motivo", "afirmacao": ""}]}


def _cobranca(novo=True, admin=True, hist=HISTORICO):
    return _montar("config_de_cobranca.html", layout_novo=novo, q=QUADRO_COBRANCA, hist=hist if admin else None, e_admin=admin)


def test_para_quem_altera_o_aviso_e_alterar_abrem_a_tela():
    html = _cobranca()
    leitor = _ler(html)
    assert leitor.ordem()[0] == "alterar" and leitor.quadro("alterar")["aberto"]
    assert html.index("Estas configurações cobram a equipe") < html.index("<details")
    assert not leitor.quadro("cob-valem-agora")["aberto"]
    assert not leitor.quadro("historico")["aberto"] and not leitor.quadro("turnos")["aberto"]


@pytest.mark.parametrize("quadro,botao", [("alterar", "Alterar"), ("turnos", "Gravar o turno")])
def test_a_caixa_afirmo_mora_no_mesmo_quadro_do_botao_e_antes_dele(quadro, botao):
    corpo = _corpo_do_quadro(_cobranca(), quadro)
    assert corpo.count('name="afirmo"') == 1 and corpo.count('name="afirmacao"') == 1
    assert "ENSAIO-regra da afirmação" in corpo
    assert corpo.index('name="afirmo"') < corpo.index(f">{botao}</button>")


def test_para_quem_so_le_abre_o_que_vale_agora_e_nao_ha_formulario():
    html = _cobranca(admin=False)
    leitor = _ler(html)
    assert leitor.ordem() == ["cob-valem-agora", "turnos", "cob-fora"]
    assert leitor.quadro("cob-valem-agora")["aberto"]
    assert not leitor.formularios and "Só o oficial altera" in html


def test_o_titulo_conta_e_nao_mostra_o_valor():
    leitor = _ler(_cobranca())
    assert "4 configurações · 2 diferente(s) do padrão" in leitor.quadro("cob-valem-agora")["titulo"]
    assert "1 com turno próprio" in leitor.quadro("turnos")["titulo"]
    assert "2 registro(s) · 1 recusada(s)" in leitor.quadro("historico")["titulo"]
    titulos = " ".join(q["titulo"] for q in leitor.quadros)
    assert "15:37" not in titulos and "18:00" not in titulos


def test_o_filtro_do_historico_volta_para_o_quadro_dele():
    html = _cobranca()
    assert 'action="/configuracoes_cobranca#historico"' in html and 'id="historico"' in html


def test_no_antigo_a_ordem_das_chaves_continua_a_de_sempre():
    html = _cobranca(novo=False)
    ordem = ["Estas configurações cobram a equipe", "ENSAIO-cobra", "Alterar uma configuração", "Turno por operador",
             "Histórico", "O que tem o mesmo papel"]
    posicoes = [html.index(texto) for texto in ordem]
    assert posicoes == sorted(posicoes), ordem


# ---------------------------------------------------------------- automação

def _processo(**extra):
    return {"id": 1, "codigo": "ENSAIO", "nome": "ENSAIO-processo", "descricao": "ENSAIO-descrição", "ativo": 1, "tipo": "FUNCAO", "timeout_s": 300,
            "pode_agir": 0, "alerta_desde": None, "alerta_situacao": None, "pedido_manual_em": None, "setor": "GESTAO", "alvo": "x:y",
            "agenda": {"dias": [0], "horarios": ["08:00"]}, "max_tentativas": 1, "responsavel_user_id": None,
            "canais": {"PAINEL": True, "EMAIL": False}, "lembrar_a_cada_h": None, "usa_credencial": None, "robo_oficial": None} | extra


def _rodada(n, situacao="ok", classe="ok"):
    return {"id": n, "iniciada_em": "2026-10-29T08:00:00", "disparo": "AGENDA", "selo": {"classe": classe, "texto": situacao}, "relato": "ENSAIO-relato"}


def _auto(novo=True, papel="ADMIN", p=None, historico=()):
    return _montar(
        "automacao_processo.html", layout_novo=novo, p=p or _processo(), historico=list(historico), batida={"parado": False},
        agenda_texto="toda segunda às 08:00", catalogo=["x:y"], tipos=["FUNCAO"], nome_do_tipo={"FUNCAO": "Verificação"},
        canais=["PAINEL", "EMAIL"], nome_do_canal={"PAINEL": "painel e sino", "EMAIL": "e-mail"}, dias=["seg", "ter"],
        usuarios=[{"id": 1, "full_name": "Mario"}], credenciais=[{"nome": ENSAIO_CREDENCIAL, "nome_do_tipo": "Senha"}],
        parametros_json="{}", selo=lambda _s: {"classe": "critica", "texto": "erro"}, user={"role": papel})


def test_a_situacao_e_rodar_agora_ficam_fora_dos_quadros():
    html = _auto()
    assert html.index("Rodar agora") < html.index("<details")
    leitor = _ler(html)
    assert leitor.ordem() == ["au-pode-agir", "au-editar", "au-rodadas"]
    assert not any(q["aberto"] for q in leitor.quadros)


def test_as_rodadas_abrem_com_problema_em_aberto():
    leitor = _ler(_auto(p=_processo(alerta_desde="2026-10-29T08:00:00", alerta_situacao="ERRO"), historico=[_rodada(9, "erro", "critica")]))
    assert leitor.quadro("au-rodadas")["aberto"] and "última: erro em 2026-10-29 08:00" in leitor.quadro("au-rodadas")["titulo"]


def test_para_quem_so_consulta_as_rodadas_vem_abertas_e_nao_ha_editar():
    leitor = _ler(_auto(papel="MANAGER", historico=[_rodada(9)]))
    assert leitor.ordem() == ["au-rodadas"] and leitor.quadro("au-rodadas")["aberto"]
    assert not leitor.formularios


def test_o_titulo_do_editar_nao_mostra_o_nome_da_credencial():
    leitor = _ler(_auto(p=_processo(usa_credencial=ENSAIO_CREDENCIAL)))
    titulo = leitor.quadro("au-editar")["titulo"]
    assert "usa credencial do cofre" in titulo and "avisa por painel e sino" in titulo
    assert ENSAIO_CREDENCIAL not in titulo


def test_o_titulo_diz_se_o_processo_pode_agir_sozinho():
    assert "só lê e propõe" in _ler(_auto()).quadro("au-pode-agir")["titulo"]
    assert "grava sem esperar" in _ler(_auto(p=_processo(pode_agir=1))).quadro("au-pode-agir")["titulo"]


def test_o_link_do_malote_continua_na_situacao():
    html = _auto(p=_processo(codigo="MALOTE_CIENCIA_DIARIA"))
    assert html.index("/malote_robo_codigo") < html.index("<details")


CFG_AUTO = {"smtp_host": ENSAIO_SERVIDOR, "smtp_porta": "587", "smtp_seguranca": "STARTTLS", "smtp_usuario": ENSAIO_USUARIO, "smtp_remetente": "",
            "email_destino": f"{ENSAIO_DESTINO}, ana@exemplo.com.br", "whatsapp_destino": "99000000000", "email_resumo_hora": "8", "lembrar_a_cada_h": "4",
            "backup_estado_caminho": "ESTADO_DE_ENSAIO.json", "cnib_minutas_log_caminho": ""}


def _aviso(situacao="ENVIADO"):
    return {"criado_em": "2026-10-29T08:00:00", "canal": "EMAIL", "motivo": "ALERTA", "situacao": situacao, "destino": ENSAIO_DESTINO, "erro": None}


def _auto_cfg(novo=True, cfg=None, ultimos=(), senha_guardada=True, batida=None):
    return _montar("automacao_configuracao.html", layout_novo=novo, cfg=cfg if cfg is not None else dict(CFG_AUTO), batida=batida or {"hora": "10:00"},
                   seguranca=["STARTTLS", "SSL"], ultimos=list(ultimos), senha_guardada=senha_guardada, nome_do_canal={"EMAIL": "e-mail"})


def test_o_despachante_fica_a_vista_e_o_formulario_e_um_so():
    html = _auto_cfg()
    assert html.index("rodando") < html.index("<details")
    leitor = _ler(html)
    assert leitor.ordem() == ["au-smtp", "au-whatsapp", "au-lembretes", "au-avisos"]
    assert not any(q["aberto"] for q in leitor.quadros)
    formulario = next(f for f in leitor.formularios if any(c[1] == "smtp_host" for c in f["campos"]))
    assert {"smtp_senha", "whatsapp_destino", "email_resumo_hora", "cnib_minutas_log_caminho"} <= {c[1] for c in formulario["campos"]}


def test_o_titulo_do_smtp_diz_como_esta_sem_mostrar_endereco_nem_usuario():
    leitor = _ler(_auto_cfg())
    titulos = " ".join(q["titulo"] for q in leitor.quadros)
    assert "servidor informado · senha guardada · 2 destino(s)" in titulos
    assert "resumo do dia a partir das 8 h · lembra a cada 4 h" in titulos
    for segredo in (ENSAIO_SERVIDOR, ENSAIO_USUARIO, ENSAIO_DESTINO, "99000000000", "ESTADO_DE_ENSAIO"):
        assert segredo not in titulos, segredo
    assert "sem servidor · sem senha · sem destino" in _ler(_auto_cfg(cfg={}, senha_guardada=False)).quadro("au-smtp")["titulo"]


def test_os_ultimos_avisos_abrem_quando_o_mais_novo_falhou():
    assert _ler(_auto_cfg(ultimos=[_aviso("FALHOU"), _aviso()])).quadro("au-avisos")["aberto"]
    leitor = _ler(_auto_cfg(ultimos=[_aviso(), _aviso("FALHOU")]))
    assert not leitor.quadro("au-avisos")["aberto"] and "1 com falha" in leitor.quadro("au-avisos")["titulo"]


# ---------------------------------------------------------------- selador

ESTADO_PRONTO = {"configurado": True, "ambiente": "PRODUCAO", "base_url": "https://192.0.2.10:443", "base_homologacao": None, "base_em_uso": "https://192.0.2.10:443",
                 "auth_url": None, "auth_em_uso": "https://192.0.2.10:443/auth", "na_rede_local": True, "usuario": ENSAIO_USUARIO, "tem_credencial": True,
                 "credencial_em": "2026-10-01", "origem": "MANUAL", "atualizado_em": "2026-10-01", "atualizado_por": "Mario", "ultimo_teste_em": "2026-10-02",
                 "ultimo_teste_ok": True, "ultimo_teste_mensagem": "", "pronto": True, "faltas": []}
ESTADO_SEM_NADA = ESTADO_PRONTO | {"base_url": None, "base_em_uso": None, "usuario": None, "tem_credencial": False, "pronto": False,
                                   "ultimo_teste_em": None, "faltas": ["Falta o endereço do selador.", "Faltam o usuário e a senha do selador."]}
CERTIFICADO_FIXO = {"sha256": "abc", "legivel": ENSAIO_IMPRESSAO, "assunto": "ENSAIO-assunto", "fixado_em": "2026-10-01", "fixado_por": "Mario"}
SEM_CERTIFICADO = {"sha256": None, "legivel": "", "assunto": None, "fixado_em": None, "fixado_por": None}


def _selador(novo=True, estado=ESTADO_PRONTO, certificado=CERTIFICADO_FIXO, orfaos=()):
    return _montar("selador_config.html", layout_novo=novo, estado=estado, certificado=certificado, orfaos=list(orfaos), ambientes=["PRODUCAO", "HOMOLOGACAO"],
                   tem_acervo=False, espacos=["selo"], endpoints=100, padrao_de_fabrica="https://exemplo.invalid", fmt_dt=str)


def test_o_que_falta_e_testar_abrem_a_tela_e_preencher_vem_antes_do_certificado():
    html = _selador(estado=ESTADO_SEM_NADA, certificado=SEM_CERTIFICADO)
    leitor = _ler(html)
    assert html.index("Falta para o sistema poder selar") < html.index("Testar a conexão") < html.index("<details")
    assert leitor.ordem()[:3] == ["sel-agora", "sel-preencher", "sel-certificado"]
    assert leitor.quadro("sel-preencher")["aberto"] and leitor.quadro("sel-certificado")["aberto"]


def test_com_tudo_no_lugar_so_a_situacao_fica_aberta():
    html = _selador()
    leitor = _ler(html)
    assert html.index("Tudo no lugar") < html.index("<details")
    assert [q["id"] for q in leitor.quadros if q["aberto"]] == ["sel-agora"]
    assert leitor.ordem().index("sel-certificado") < leitor.ordem().index("sel-preencher")


def test_o_titulo_do_selador_nao_mostra_usuario_nem_impressao_digital():
    html = _selador(orfaos=[{"numero": "ENSAIO-SELO", "atribuicao": "RI", "referencia": "", "obtido_em": "x", "obtido_por": "Mario"}])
    leitor = _ler(html)
    titulos = " ".join(q["titulo"] for q in leitor.quadros)
    assert ENSAIO_USUARIO not in titulos and ENSAIO_IMPRESSAO not in titulos and "192.0.2.10" not in titulos
    assert "certificado conferido" in titulos and "usuário e senha gravados" in titulos
    assert "1 selo(s)" in leitor.quadro("sel-orfaos")["titulo"]
    assert ENSAIO_USUARIO in _corpo_do_quadro(html, "sel-agora") and ENSAIO_IMPRESSAO in _corpo_do_quadro(html, "sel-agora")


def test_apagar_a_credencial_continua_pedindo_confirmacao():
    html = _selador()
    assert "return confirm(" in _corpo_do_quadro(html, "sel-apagar")
    assert 'id="sel-apagar"' not in _selador(estado=ESTADO_SEM_NADA, certificado=SEM_CERTIFICADO)


def test_no_antigo_a_ordem_do_selador_continua_a_de_sempre():
    html = _selador(novo=False, estado=ESTADO_SEM_NADA, certificado=SEM_CERTIFICADO)
    ordem = ["não está na internet", "Como está agora", "Falta para o sistema poder selar", "Conferir o certificado", "Testar a conexão",
             "Preencher à mão", "Selos obtidos e não usados"]
    posicoes = [html.index(texto) for texto in ordem]
    assert posicoes == sorted(posicoes), ordem


# ---------------------------------------------------------------- ajuda

def _provedor(ident, chave=True):
    return {"id": ident, "nome": f"ENSAIO-{ident}", "familia": "x", "endereco": "https://exemplo.invalid", "modelos": {"PADRAO": "m1", "FORTE": "m2"},
            "tem_chave": chave, "mascarada": ENSAIO_CHAVE_MASCARADA if chave else "", "vem_da_ajuda": False}


def _ajuda(novo=True, tem_chave=True, provedores=None, historicas=()):
    provedores = provedores if provedores is not None else [_provedor("um"), _provedor("dois", chave=False)]
    return _montar(
        "ajuda_configurar.html", layout_novo=novo, tem_chave=tem_chave, provedores=provedores, historicas=list(historicas),
        acesso={"perfis_lista": ["ADMIN"], "todos_os_perfis": ["ADMIN", "USER"], "so_o_administrador": True, "alterada_em": None},
        quadro={"restam": 40, "teto": 50, "consultas": 10, "falhas": 0, "tokens": 5, "teto_de_tokens": 100, "restam_tokens": 95, "entrada": 3, "saida": 2,
                "historicas_sem_protecao": 0, "sem_provedor": 0},
        escolha={"provedor": "um", "provedor_nome": "ENSAIO-um", "modelo": "m1", "modelos": {"PADRAO": {"id": "m1", "rotulo": "Modelo um"}}, "escolha_em": None, "escolha_por": None},
        caminho_da_chave="ENSAIO-arquivo.cred", teto=50, teto_de_tokens=100,
        mapa={"quantas_telas": 300, "quantas_tabelas": 200, "quantos_arquivos": 100, "menu": [1, 2]})


def test_com_chave_tudo_fica_recolhido_e_o_timbre_vai_para_o_fim():
    html = _ajuda()
    leitor = _ler(html)
    assert not any(q["aberto"] for q in leitor.quadros) and "A chave da API ainda não foi informada" not in html
    assert html.index("<details") < html.index("TIMBRE DA SERVENTIA")
    assert "1 de 2 informadas" in leitor.quadro("aj-chaves")["titulo"]
    assert "restam 40 de 50 consultas" in leitor.quadro("aj-uso")["titulo"]


def test_o_provedor_em_uso_sem_chave_avisa_no_alto_e_abre_as_chaves():
    html = _ajuda(tem_chave=False, provedores=[_provedor("um", chave=False)])
    assert html.index("A chave da API ainda não foi informada") < html.index("<details")
    assert 'href="#aj-chaves"' in html and _ler(html).quadro("aj-chaves")["aberto"]


def test_o_titulo_nao_mostra_a_chave_nem_mascarada():
    html = _ajuda()
    assert ENSAIO_CHAVE_MASCARADA not in " ".join(q["titulo"] for q in _ler(html).quadros)
    assert ENSAIO_CHAVE_MASCARADA in _corpo_do_quadro(html, "aj-chaves")


def test_no_antigo_o_timbre_continua_no_alto():
    html = _ajuda(novo=False)
    assert html.index("TIMBRE DA SERVENTIA") < html.index("Quem responde") < html.index("As chaves de API")
    assert "A chave da API ainda não foi informada" not in _ajuda(novo=False, tem_chave=False)


# ---------------------------------------------------------------- todas juntas

TELAS = {
    "carne_cheio": lambda novo: _carne(novo=novo, **CARNE_CHEIO),
    "carne_vazio": lambda novo: _carne(novo=novo),
    "carne_cfg_cheio": lambda novo: _carne_cfg(novo=novo, tabelas=[_tabela(1, "2026-01-01"), _tabela(3, "2024-02-01", anulada=True)]),
    "carne_cfg_vazio": lambda novo: _carne_cfg(novo=novo),
    "nfse_faltando": lambda novo: _nfse(novo=novo, faltas=FALTAS_NFSE, avisos=["ENSAIO-a conferir"]),
    "nfse_pronta": lambda novo: _nfse(novo=novo, certificado=CERTIFICADO_BOM, parametros={"consultado_em": "2026-10-01T10:00:00", "ambiente": "homologacao", "municipio": "2100000"}),
    "cobranca_admin": lambda novo: _cobranca(novo=novo),
    "cobranca_gerente": lambda novo: _cobranca(novo=novo, admin=False),
    "auto_admin": lambda novo: _auto(novo=novo, historico=[_rodada(9)]),
    "auto_gerente": lambda novo: _auto(novo=novo, papel="MANAGER", historico=[_rodada(9)]),
    "auto_cfg": lambda novo: _auto_cfg(novo=novo, ultimos=[_aviso()]),
    "selador_pronto": lambda novo: _selador(novo=novo),
    "selador_sem_nada": lambda novo: _selador(novo=novo, estado=ESTADO_SEM_NADA, certificado=SEM_CERTIFICADO),
    "ajuda": lambda novo: _ajuda(novo=novo),
    "ajuda_sem_chave": lambda novo: _ajuda(novo=novo, tem_chave=False, historicas=[{"id": 1, "perguntada_em": "2026-10-01T10:00:00", "perguntada_por": "Mario", "referencia": "x", "onde": ""}]),
}


@pytest.mark.parametrize("tela", sorted(TELAS))
def test_os_dois_layouts_mandam_os_mesmos_campos(tela):
    """Formulário por formulário: o mesmo endereço, os mesmos campos, na mesma ordem, com os mesmos valores."""
    novo, antigo = _ler(TELAS[tela](True)), _ler(TELAS[tela](False))
    assert novo.formularios_em_ordem_fixa() == antigo.formularios_em_ordem_fixa()


@pytest.mark.parametrize("tela", sorted(TELAS))
@pytest.mark.parametrize("novo", [True, False])
def test_as_caixas_fecham_na_ordem(tela, novo):
    leitor = _ler(TELAS[tela](novo))
    assert not leitor.pilha and not leitor.tortas, (leitor.pilha, leitor.tortas)


@pytest.mark.parametrize("tela", sorted(TELAS))
def test_no_antigo_nao_entra_quadro_estilo_nem_script(tela):
    html = TELAS[tela](False)
    assert "<details" not in html and "<style" not in html and "<script" not in html and "cg-" not in html


@pytest.mark.parametrize("tela", sorted(TELAS))
def test_no_novo_vem_o_script_que_abre_o_quadro_do_campo_recusado(tela):
    html = TELAS[tela](True)
    assert 'addEventListener("invalid"' in html and "details.panel.cg-quadro" in html


@pytest.mark.parametrize("tela", sorted(TELAS))
def test_todo_quadro_de_primeiro_nivel_tem_titulo_e_nota(tela):
    """O título do quadro diz como ele está, sem abrir."""
    html = TELAS[tela](True)
    for resumo in re.findall(r'<details class="panel cg-quadro" id="[^"]+"[^>]*>\s*<summary>(.*?)</summary>', html, re.S):
        assert "<small>" in resumo, resumo


def test_os_moldes_nao_tocam_em_regra_nem_em_rota():
    """Só layout: nenhum molde desta frente passou a postar para outro endereço."""
    for nome, rotas in (("carne_leao.html", {"carne_leao_anular", "carne_leao_outra_entrada", "carne_leao_marcar", "carne_leao_lancar"}),
                        ("config_de_cobranca.html", {"configuracoes_cobranca_alterar"}),
                        ("nfse_gestor.html", {"nfse_gestor"})):
        texto = (RAIZ / "templates" / nome).read_text(encoding="utf-8")
        assert rotas <= set(re.findall(r"url_for\('(\w+)'", texto)), nome


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


CAMINHOS_ADMIN = ["/administrativo/carne-leao", "/administrativo/carne-leao?mes=2026-09", "/administrativo/carne-leao/configuracao",
                  "/administrativo/gestor/nfse", "/configuracoes/cobranca", "/automacao/1", "/automacao/configuracao", "/selador", "/ajuda/configurar"]
CAMINHOS_GERENTE = ["/configuracoes/cobranca", "/automacao/1", "/selador"]


def _campos_da_tela(html: str) -> list:
    """Só o conteúdo da tela: na moldura antiga, as barras de aviso ficam no mesmo `<main>`, e têm campos."""
    inicio = html.find('<div class="content">')
    inicio = inicio if inicio >= 0 else html.index("<main")
    return sorted(re.findall(r'\bname="(\w+)"', html[inicio:html.rindex("</main>")]))


@pytest.mark.parametrize("papel,caminho", [("ADMIN", c) for c in CAMINHOS_ADMIN] + [("MANAGER", c) for c in CAMINHOS_GERENTE])
def test_a_tela_abre_nos_dois_layouts_com_os_mesmos_campos(cg_app, papel, caminho):
    c = _entrar(cg_app, f"fin_{papel.lower()}", papel)
    _layout(c, "antigo")
    antigo = c.get(caminho)
    _layout(c, "novo")
    novo = c.get(caminho)
    assert antigo.status_code == novo.status_code == 200, (caminho, antigo.status_code, novo.status_code)
    html_antigo, html_novo = antigo.get_data(as_text=True), novo.get_data(as_text=True)
    assert "cg-quadro" not in html_antigo and "cg-quadro" in html_novo
    assert html_novo.count("<details") == html_novo.count("</details>")
    assert _campos_da_tela(html_antigo) == _campos_da_tela(html_novo)


def test_gravar_a_nfse_com_os_quadros_fechados_grava_todos_os_campos(cg_app):
    d = cg_app.extensions["db"]
    c = _entrar(cg_app, "fin_nfse")
    _layout(c, "novo")
    html = c.get("/administrativo/gestor/nfse").get_data(as_text=True)
    assert not re.search(r'id="nfse-ibscbs"[^>]*\bopen\b', html)
    dados = {"csrf_token": _token(html), "acao": "configuracao", "nfse_provedor": "nacional", "nfse_ambiente": "homologacao",
             "nfse_optante_simples": "1", "nfse_regime_especial": "4", "nfse_serie": "7", "nfse_ibscbs_cst": "000", "nfse_ibscbs_classificacao": "000001"}
    assert c.post("/administrativo/gestor/nfse", data=dados).status_code == 302
    assert d.get_setting("nfse_serie", "") == "7"
    assert d.get_setting("nfse_ibscbs_cst", "") == "000"
    novo = c.get("/administrativo/gestor/nfse").get_data(as_text=True)
    assert "CST 000" in re.search(r'id="nfse-ibscbs".*?</summary>', novo, re.S).group(0)
