"""As telas mais altas com uso real, no layout novo: o que espera em cima, nenhum campo perdido.

O QUE ELES DEFENDEM
    Medido em 01/11/2026, com dado: a ficha do devedor no Protesto passava de 5 mil px com poucos títulos, e na
    produção há devedor com 33; as anotações devidas davam uma tela inteira por pendência, e há 10 esperando. No
    layout novo, cada título ou pendência vira uma linha que já diz o que há, e só o mais urgente abre.

    A armadilha é a mesma de toda tela recolhida: a linha fechada precisa dizer o que espera, e quem continua no
    layout antigo tem de ver a tela de sempre, com os mesmos formulários.

    Tudo aqui monta o molde de verdade sobre uma moldura vazia, sem banco e sem o sistema de pé.
"""
from __future__ import annotations

from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

import jinja2

import rc_anotacao as ANOT

RAIZ = Path(__file__).resolve().parent.parent


def _url(rota, **args):
    return "/" + rota + "".join(f"/{k}={v}" for k, v in sorted(args.items()))


def _data(valor):
    return f"{valor[8:10]}/{valor[5:7]}/{valor[:4]}" if valor else "—"


def _montar(molde: str, **contexto) -> str:
    env = jinja2.Environment(autoescape=True, loader=jinja2.ChoiceLoader([
        jinja2.DictLoader({"base.html": "{% block heading %}{% endblock %}{% block content %}{% endblock %}"}),
        jinja2.FileSystemLoader(str(RAIZ / "templates"), encoding="utf-8")]))
    env.filters["centavos_reais"] = lambda v: f"{(v or 0) / 100:.2f}".replace(".", ",")
    return env.get_template(molde).render(url_for=_url, csrf_token="t", fmt_date=_data, **contexto)


class _Leitor(HTMLParser):
    """Anota os formulários, os quadros, e se as caixas fecham na ordem."""

    CAIXAS = {"details", "summary", "section", "div", "form", "table"}
    CAMPOS = {"input", "select", "textarea", "button"}

    def __init__(self):
        super().__init__()
        self.pilha, self.tortas, self.quadros = [], [], {}
        self.campos, self.form = Counter(), None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form":
            self.form = a.get("action", "")
            self.campos[("form", self.form, a.get("method", ""))] += 1
        if tag in self.CAMPOS and a.get("name"):
            self.campos[(self.form, tag, a["name"], a.get("type", ""), a.get("value", ""), "required" in a)] += 1
        if tag == "details" and "cg-quadro" in (a.get("class") or ""):
            self.quadros[a.get("id")] = "open" in a
        if tag in self.CAIXAS:
            self.pilha.append(tag)

    def handle_endtag(self, tag):
        if tag == "form":
            self.form = None
        if tag in self.CAIXAS and (not self.pilha or self.pilha.pop() != tag):
            self.tortas.append(tag)


def _ler(html: str) -> _Leitor:
    leitor = _Leitor()
    leitor.feed(html)
    return leitor


def _antes(html: str, *trechos):
    """Os trechos aparecem nesta ordem."""
    posicoes = [html.index(t) for t in trechos]
    assert posicoes == sorted(posicoes), trechos


def _resumo_do_quadro(html: str, id_do_quadro: str) -> str:
    inicio = html.index(f'id="{id_do_quadro}"')
    return html[html.index("<summary>", inicio):html.index("</summary>", inicio)]


# ---------------------------------------------------------------- /protesto/devedores/<id>

def _titulo(id_, **campos):
    return {"id": id_, "numero_titulo": f"T-{id_}", "situacao": "APONTADO", "sustado": False, "alertas": [],
            "protocolo": 100 + id_, "especie": "DM", "saldo_centavos": 150000, "valor_centavos": 150000,
            "data_vencimento": "2026-10-10", "cedente_nome": "Credor Exemplo", "prazo_limite": "2026-11-05",
            "dias_para_o_prazo": 4, "em_andamento": True, "protesto_a_partir_de": "2026-11-06", "protesto": None,
            "intimacoes": [], "avisos": [], "postagens": [], "pagamentos": [], "boletos": [], **campos}


def _devedor(novo=True, titulos=None):
    if titulos is None:
        titulos = [
            _titulo(1, alertas=[{"codigo": "VENCE_HOJE", "rotulo": "Vence hoje", "frase": "É hoje.", "detalhe": "", "base": "art. 1"}]),
            _titulo(2, sustado=True),
            _titulo(3, situacao="PAGO", em_andamento=False, prazo_limite=None, dias_para_o_prazo=None),
        ]
    p = {"nomes": ["Ana Exemplo"], "sem_documento": False, "documento_tipo": "CPF", "documento_formatado": "000.000.001-91",
         "resumo": {"titulos": len(titulos), "em_andamento": 2, "valor_em_aberto_centavos": 300000, "protestados": 0, "alertas": 1},
         "titulos": titulos}
    return _montar("protesto_devedor.html", layout_novo=novo, p=p)


def test_devedor_cada_titulo_e_uma_linha_e_so_o_mais_urgente_abre():
    leitor = _ler(_devedor())
    assert leitor.quadros == {"titulo-1": True, "titulo-2": False, "titulo-3": False}
    assert not leitor.tortas and not leitor.pilha


def test_devedor_a_linha_fechada_diz_o_que_ha():
    html = _devedor()
    primeira = _resumo_do_quadro(html, "titulo-1")
    assert "Título T-1" in primeira and "APONTADO" in primeira and "1500,00" in primeira
    assert "prazo 05/11/2026" in primeira and "Vence hoje" in primeira and "critica" in primeira
    assert "SUSTADO" in _resumo_do_quadro(html, "titulo-2")
    # Título que já saiu de andamento não tem prazo a cumprir.
    assert "prazo" not in _resumo_do_quadro(html, "titulo-3")


def test_devedor_o_que_estava_na_ficha_continua_dentro_de_cada_titulo():
    html = _devedor()
    for id_ in (1, 2, 3):
        assert f"/protesto_titulo/titulo_id={id_}" in html
    assert html.count("Intimações") == 3 and html.count("Pagamentos e boletos") == 3
    _antes(html, "titulo-3", "cg-quadros:")


def test_devedor_no_antigo_nada_sai_do_lugar():
    html = _devedor(novo=False)
    assert "cg-quadro" not in html and "<details" not in html and "cg-quadros:" not in html
    assert html.count('<section class="cartao">') == 3
    assert "alerta(s)" not in html
    assert not _ler(html).tortas


def test_devedor_sem_titulo_nao_quebra():
    for novo in (True, False):
        assert "Nenhum título deste devedor." in _devedor(novo=novo, titulos=[])


# ---------------------------------------------------------------- /rcpn/anotacoes

def _pendencia(id_, **campos):
    return {"id": id_, "especie": "OBITO", "especie_alvo": "NASCIMENTO", "numero": 10 + id_,
            "nome": f"Pessoa Exemplo {id_}", "data_ato": "2026-10-20", **campos}


def _anotacoes(novo=True, devendo=None, vencidas=()):
    devendo = [_pendencia(1), _pendencia(2)] if devendo is None else devendo
    return _montar("rcpn_anotacoes.html", layout_novo=novo, norma=ANOT, devendo=devendo,
                   vencidas=[{"id": i} for i in vencidas], ids_vencidas=set(vencidas))


def test_anotacoes_o_que_esta_devendo_vem_antes_da_explicacao():
    html = _anotacoes()
    _antes(html, "O prazo é de", "Anotar o obito", "Por que existe este prazo", "O que a norma exige")
    assert _ler(html).quadros == {"anotacao-1": True, "anotacao-2": False,
                                  "anotacoes-por-que": False, "anotacoes-norma": False}


def test_anotacoes_a_linha_diz_quem_e_e_se_passou_do_prazo():
    html = _anotacoes(vencidas=[2])
    assert "Termo 11, Pessoa Exemplo 1, lavrado em 20/10/2026" in _resumo_do_quadro(html, "anotacao-1")
    assert "fora do prazo" not in _resumo_do_quadro(html, "anotacao-1")
    assert "fora do prazo" in _resumo_do_quadro(html, "anotacao-2")


def test_anotacoes_sem_data_nao_inventa():
    assert "(sem data)" in _resumo_do_quadro(_anotacoes(devendo=[_pendencia(1, data_ato=None)]), "anotacao-1")


def test_anotacoes_as_duas_molduras_mandam_os_mesmos_campos():
    novo, antigo = _ler(_anotacoes()), _ler(_anotacoes(novo=False))
    assert novo.campos == antigo.campos
    assert novo.campos[("/rcpn_anotacao_resolver/pendencia_id=1", "input", "acao", "hidden", "COMUNICAR", False)] == 1
    assert not novo.tortas and not novo.pilha and not antigo.tortas


def test_anotacoes_no_antigo_nada_sai_do_lugar():
    html = _anotacoes(novo=False)
    assert "cg-quadro" not in html and "cg-quadros:" not in html
    _antes(html, "Quando esta casa lavra", "Anotar o obito", "O que a norma exige")


def test_anotacoes_sem_pendencia_diz_e_a_norma_continua_ao_alcance():
    html = _anotacoes(devendo=[])
    assert "Nenhuma anotação pendente." in html
    assert _ler(html).quadros == {"anotacoes-por-que": False, "anotacoes-norma": False}


# ---------------------------------------------------------------- /selo/conferencia

def _conferencia(novo=True, trava=True, **listas):
    dados = {"liberados": [], "gratuitos": [], "aguardando": [], "pagos_sem_cobertura": [], "pagos_cortados": False,
             "pagos_limite": 500, **listas}
    return _montar("selo_conferencia.html", layout_novo=novo, trava_ligada=trava, eh_admin=True, prazo=30,
                   desde="2026-10-01", **dados)


def _selo_pago(n):
    return {"numero": f"SELO{n}", "rotulo": "ato", "ato_id": n, "obtido_por": "Mario", "obtido_em": "2026-10-02T10:00:00"}


def _aguardando(n):
    return {"tabela": "nt_atos", "ato_id": n, "usuario": "Mario", "desde": "2026-10-02"}


def test_conferencia_a_lista_com_gente_abre_e_a_vazia_fica_fechada():
    leitor = _ler(_conferencia(aguardando=[_aguardando(1), _aguardando(2)]))
    assert leitor.quadros == {"trava": False, "conferencia-liberados": False, "conferencia-gratuidades": False,
                              "conferencia-aguardando": True, "conferencia-pagos": False}
    assert not leitor.tortas and not leitor.pilha


def test_conferencia_a_trava_desligada_nao_fica_fechada():
    assert _ler(_conferencia(trava=False)).quadros["trava"] is True
    assert "DESLIGADA" in _resumo_do_quadro(_conferencia(trava=False), "trava")
    assert "LIGADA" in _resumo_do_quadro(_conferencia(trava=True), "trava")


def test_conferencia_o_titulo_conta_o_que_ha_mesmo_fechado():
    html = _conferencia(aguardando=[_aguardando(1), _aguardando(2)], pagos_sem_cobertura=[_selo_pago(1)])
    assert "2 ato(s)" in _resumo_do_quadro(html, "conferencia-aguardando")
    assert "1 selo(s)" in _resumo_do_quadro(html, "conferencia-pagos")
    assert "desde 01/10/2026" in _resumo_do_quadro(html, "conferencia-pagos")
    # A lista dos pagos só serve para conferir, e pode chegar ao limite: fica fechada mesmo com selo.
    assert _ler(html).quadros["conferencia-pagos"] is False


def test_conferencia_a_lista_cortada_avisa_no_titulo():
    html = _conferencia(pagos_sem_cobertura=[_selo_pago(1)], pagos_cortados=True)
    assert "1 ou mais selo(s)" in _resumo_do_quadro(html, "conferencia-pagos")


def test_conferencia_a_ancora_de_configuracoes_continua_existindo():
    assert 'id="trava"' in _conferencia(novo=True) and 'id="trava"' in _conferencia(novo=False)


def test_conferencia_as_duas_molduras_mandam_os_mesmos_campos():
    for trava in (True, False):
        novo, antigo = _ler(_conferencia(trava=trava)), _ler(_conferencia(novo=False, trava=trava))
        assert novo.campos == antigo.campos
        assert not antigo.tortas and not antigo.pilha


def test_conferencia_no_antigo_nada_sai_do_lugar():
    html = _conferencia(novo=False)
    assert "cg-quadro" not in html and "cg-quadros:" not in html
    assert html.count('<section class="card">') == 5
