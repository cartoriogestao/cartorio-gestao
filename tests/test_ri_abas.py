"""As abas da ficha da matrícula: a conta da régua, e o que a ficha não pode perder.

O QUE ELES DEFENDEM
    Que o que espera ação aparece primeiro, sem o acervo virar alarme, e que nenhum quadro fica
    fora de alcance. Quadro sem aba, ou numa aba que não aparece, some da tela sem erro nenhum.

    Tudo aqui lê arquivo e faz conta. O que precisa do sistema de pé está em
    `tests/test_ficha_matricula_web.py`.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ri_abas as RA  # noqa: E402

FICHA = (RAIZ / "templates" / "ri_ficha.html").read_text(encoding="utf-8-sig")


def _ato(numero=1, **campos) -> dict:
    return {"id": numero, "tipo": "R", "numero": numero, "origem": "MANUAL", "selo_texto": "X",
            "cancelado": 0, "data_ato": "2026-10-30", "natureza_titulo": "Compra e venda", **campos}


def _chaves(r: dict) -> list[str]:
    return [x["chave"] for x in r["apoio"]]


def _aba(r: dict, chave: str) -> dict:
    return next(x for x in r["apoio"] if x["chave"] == chave)


def test_a_ficha_abre_no_resumo():
    assert RA.abas_da_matricula({})["inicial"] == RA.RESUMO


def test_quem_veio_lavrar_abre_em_novo_ato():
    assert RA.abas_da_matricula({}, foco=RA.NOVO_ATO)["inicial"] == RA.NOVO_ATO
    assert RA.abas_da_matricula({}, foco="nada")["inicial"] == RA.RESUMO


def test_nao_ha_fase_numerada():
    """A matrícula é registro vivo: ninguém termina a aba Partes."""
    assert RA.abas_da_matricula({})["fases"] == []


def test_aba_de_lista_vazia_nao_aparece():
    vazia = _chaves(RA.abas_da_matricula({}))
    assert RA.ATOS not in vazia and RA.PROTOCOLOS not in vazia
    cheia = _chaves(RA.abas_da_matricula({}, atos=[_ato()], protocolos=[{"id": 1}]))
    assert RA.ATOS in cheia and RA.PROTOCOLOS in cheia


def test_as_abas_que_guardam_formulario_ficam_sempre():
    """Revisar abre nota; Partes inclui; Certidões emite; Novo ato tem rascunho."""
    assert {RA.RESUMO, RA.TEOR, RA.PARTES, RA.CERTIDOES, RA.REVISAR, RA.NOVO_ATO} <= set(
        _chaves(RA.abas_da_matricula({})))


def test_no_maximo_oito_subabas():
    r = RA.abas_da_matricula({}, atos=[_ato()], protocolos=[{"id": 1}])
    assert len(r["apoio"]) <= 8


def test_ato_sem_selo_espera_acao_e_marca_a_aba():
    r = RA.abas_da_matricula({}, atos=[_ato(1), _ato(2, selo_texto="")])
    assert r["espera"][0] == {"texto": "R-02 lavrado e sem selo", "ir": "selar-ato-2", "botao": "Selar"}
    assert _aba(r, RA.ATOS)["alerta"] == 1


def test_o_acervo_nao_vira_alarme():
    """Ato do acervo não tem selo: é o caso comum, e cobrar seria o alarme que soa sempre."""
    assert RA.o_que_espera([_ato(origem="EOFICIO", selo_texto="")]) == []


def test_ato_cancelado_nao_pede_selo():
    assert RA.o_que_espera([_ato(selo_texto="", cancelado=1)]) == []


def test_o_quadro_so_sai_quando_ha_o_que_fazer():
    assert RA.abas_da_matricula({}, atos=[_ato()])["espera"] == []


def test_revisao_minuta_rascunho_e_certidao_entram_no_que_espera():
    r = RA.abas_da_matricula({}, revisoes_abertas=[1, 2], minutas=[1], rascunho={"tipo": "AV"},
                             certidoes_aguardando_selo={7})
    assert [i["ir"] for i in r["espera"]] == [RA.CERTIDOES, RA.REVISAR, "minutas-para-lavrar", RA.NOVO_ATO]
    assert _aba(r, RA.REVISAR)["alerta"] == 2


def test_so_o_dono_de_hoje_e_proprietario():
    """Quem vendeu continua em `partes`: dizer que é dono seria a ficha mentindo."""
    partes = [{"nome": "ANA EXEMPLO", "proprietario_ativo": 1}, {"nome": "JOÃO MODELO", "proprietario_ativo": 0}]
    assert RA.proprietarios(partes) == ["ANA EXEMPLO"]


def test_ultimos_atos_do_mais_novo_ao_mais_antigo():
    r = RA.abas_da_matricula({}, atos=[_ato(n) for n in (1, 2, 3, 4)])
    assert [x["rotulo"] for x in r["ultimos"]] == ["R-04", "R-03", "R-02"]


# ----------------------------------------------------------- o que a ficha não pode perder

def _sem_comentarios(html: str) -> str:
    return re.sub(r"\{#.*?#\}", "", html, flags=re.S)


def test_todo_quadro_da_ficha_diz_em_que_aba_mora():
    corpo = _sem_comentarios(FICHA[FICHA.index("{% block content %}"):])
    abertos = re.findall(r"<(?:section|details)\b[^>]*\bclass=\"panel[^>]*>", corpo)
    assert len(abertos) >= 15, "o varredor deixou de achar os quadros"
    sem_aba = [t for t in abertos if "data-fase" not in t]
    assert sem_aba == [], sem_aba


def test_a_aba_dos_quadros_existe_na_regua():
    possiveis = {RA.RESUMO, RA.ATOS, RA.TEOR, RA.PARTES, RA.PROTOCOLOS, RA.CERTIDOES, RA.REVISAR, RA.NOVO_ATO}
    literais = set(re.findall(r'data-fase="([a-z-]+)"', FICHA))
    assert literais == possiveis, literais ^ possiveis


def test_toda_aba_tem_endereco_na_pagina():
    for chave in (RA.RESUMO, RA.ATOS, RA.TEOR, RA.PARTES, RA.PROTOCOLOS, RA.CERTIDOES, RA.REVISAR, RA.NOVO_ATO):
        assert f'id="{chave}"' in FICHA, chave


def test_os_alvos_do_que_espera_existem():
    assert 'id="minutas-para-lavrar"' in FICHA
    assert 'id="selar-ato-{{ a.id }}"' in FICHA


def test_quem_continua_no_layout_antigo_nao_recebe_nada():
    assert "{% set f = abas_da_ficha() if layout_novo else none %}" in FICHA
    assert FICHA.rstrip().endswith("{% if f %}</div>{% endif %}\n{% endblock %}".replace("\n", "\r\n")) or \
        FICHA.rstrip().endswith("{% if f %}</div>{% endif %}\n{% endblock %}")
    assert "{% if abrir_form or mn or f %} open{% endif %}" in FICHA


# ----------------------------------------------------------- os passos do novo ato

def _filhos_do_formulario() -> list[tuple[str, dict]]:
    """As tags logo abaixo do formulário de lavrar, com as duas pontas de cada `if`."""
    from html.parser import HTMLParser
    ini = FICHA.rfind("<form", 0, FICHA.index('id="form-lavrar-ato"'))
    trecho = _sem_comentarios(FICHA[ini:FICHA.index("</form>", ini) + 7])
    vazias = {"input", "br", "hr", "img", "meta", "link", "option"}
    achadas = []

    class Leitor(HTMLParser):
        fundo = 0

        def handle_starttag(self, tag, attrs):
            if self.fundo == 1:
                achadas.append((tag, dict(attrs)))
            if tag not in vazias:
                self.fundo += 1

        def handle_endtag(self, tag):
            if tag not in vazias:
                self.fundo -= 1
    Leitor().feed(trecho)
    return achadas


def test_todo_bloco_do_formulario_tem_passo():
    """Bloco sem passo fica à vista em todos; passo errado esconde o campo de quem procura."""
    filhos = _filhos_do_formulario()
    assert len(filhos) >= 25, "o varredor deixou de achar os blocos"
    sem_passo = [(t, a.get("id") or a.get("name") or a.get("class")) for t, a in filhos
                 if "data-passo" not in a and t not in ("script", "datalist", "nav")
                 and a.get("type") != "hidden" and "data-cg-passos-fim" not in a]
    assert sem_passo == [], sem_passo


def test_os_campos_obrigatorios_estao_em_passos_que_existem():
    passos = {a["data-passo"] for _t, a in _filhos_do_formulario() if "data-passo" in a}
    assert passos == {"protocolo", "ato", "selo", "partes", "lavrar"}, passos


def test_o_botao_de_lavrar_e_o_ultimo_passo():
    """Ordem de 07/10: tudo o que o clique leva se preenche antes dele."""
    trecho = FICHA[FICHA.index('<button class="primary">Lavrar ato</button>') - 80:]
    assert 'data-passo="lavrar"' in trecho[:120]


def test_o_campo_invalido_abre_o_passo_dele():
    """Sem isto, o navegador recusa o envio em silêncio: não há onde pôr o foco."""
    script = (RAIZ / "static" / "fases.js").read_text(encoding="utf-8")
    assert 'addEventListener("invalid"' in script and "reportValidity" in script


def test_os_passos_so_existem_no_layout_novo():
    linha = FICHA.index("data-cg-passos=")
    assert FICHA.rfind("{% if f %}", 0, linha) > FICHA.rfind("{% endif %}", 0, linha)


def test_a_regra_do_selo_e_a_mesma_da_ficha():
    """A lista «Ato(s) desta ficha sem selo» usa estes três filtros: a conta tem de bater."""
    linha = next(x for x in FICHA.splitlines() if "set _sem_selo" in x)
    for filtro in ("selectattr('origem', 'equalto', 'MANUAL')", "rejectattr('selo_texto')", "rejectattr('cancelado')"):
        assert filtro in linha, filtro
