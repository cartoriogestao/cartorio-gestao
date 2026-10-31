"""Todo papel do catálogo se grava: o texto de fábrica não pode ser recusado pela conferência.

O QUE ELES DEFENDEM
    Até 30/10/2026, 21 papéis não se gravavam, entre eles o cabeçalho e as certidões do RI: o boneco
    da conferência não conhecia as variáveis deles, e a tela dizia «'serventia' is undefined». O risco
    do conserto é o contrário: aprovar erro de digitação. A parte de baixo usa o sistema de pé, e roda
    na outra máquina.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from unittest import mock

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import modelos_elementos as ELEM  # noqa: E402

CABECALHO = "RI_CABECALHO"


def _padrao_do_arquivo(chave: str) -> str:
    """O texto de fábrica lido da pasta, sem depender da base de padrões."""
    import modelos_da_casa as CASA
    return (CASA.PASTA.ler_pasta()["padroes"].get(chave) or {}).get("corpo") or ""


def _sem_banco():
    """A conferência lê o padrão e o formato; aqui eles vêm da pasta, sem banco."""
    import modelos_da_casa as CASA
    return mock.patch.object(CASA, "padrao_de", _padrao_do_arquivo)


def _conferir(chave: str, texto: str) -> str:
    with _sem_banco():
        return ELEM.conferir("RI", chave, ELEM.CORPO, texto)


def test_o_cabecalho_de_fabrica_passa():
    assert _conferir(CABECALHO, _padrao_do_arquivo(CABECALHO)) == ""


def test_erro_de_digitacao_no_nome_continua_recusado():
    assert "serventa" in _conferir(CABECALHO, "{{ serventa.cidade }}")


def test_erro_de_forma_continua_recusado():
    assert _conferir(CABECALHO, "{% if serventia.cidade %}sem fechar")
    assert _conferir(CABECALHO, "{{ serventia.cidade")


@pytest.mark.parametrize("texto", [
    "{{ serventia.cidade|upper }}", "{% for x in serventia.itens %}{{ x.nome }}{% endfor %}",
    "{{ serventia.a.b.c }}", "{{ serventia.valor|round(2) }}", "{{ serventia.valor + 1 }}",
    "{% if serventia.x > 1 %}a{% endif %}", "{{ serventia.lista|length }}", "{{ serventia['x'] }}",
])
def test_o_que_o_padrao_usa_se_monta(texto):
    assert _conferir(CABECALHO, texto) == ""


def test_papel_sem_chave_do_catalogo_continua_so_com_o_boneco():
    with _sem_banco():
        assert "serventia" in ELEM.conferir("RI", "", ELEM.CORPO, "{{ serventia.cidade }}")


def test_o_valor_de_ensaio_nao_vira_porta():
    """Atributo com sublinhado o ambiente restrito recusa, igual à hora de emitir."""
    assert _conferir(CABECALHO, "{{ serventia.cidade.__class__.__mro__ }}")


def test_todo_papel_do_catalogo_se_grava_com_o_texto_de_fabrica():
    """A medição que achou o defeito, para o papel novo não nascer assim."""
    import modelos_da_casa as CASA
    recusados = []
    with _sem_banco():
        for c in CASA.CATALOGO:
            corpo = _padrao_do_arquivo(c["chave"])
            if not corpo:
                continue
            ruim = ELEM.conferir(ELEM.atribuicao_do_ato(c["chave"]), c["chave"], ELEM.CORPO, corpo)
            if ruim:
                recusados.append((c["chave"], ruim[:60]))
    assert not recusados, recusados


# ------------------------------------------------------------- com o sistema de pé


def _token(html: str) -> str:
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


def test_a_tela_grava_e_volta_ao_padrao(cg_app):
    d = cg_app.extensions["db"]
    try:
        d.create_user("modelos_gravar", "Operador Exemplo", "Senha#12345", "ADMIN")
    except Exception:                                              # noqa: BLE001
        pass
    c = cg_app.test_client()
    c.post("/login", data={"username": "modelos_gravar", "password": "Senha#12345",
                           "csrf_token": _token(c.get("/login").get_data(as_text=True))}, follow_redirects=True)
    tela = c.get(f"/modelos?editar={CABECALHO}").get_data(as_text=True)
    token = _token(tela)
    corpo = re.search(r'name="corpo"[^>]*>(.*?)</textarea>', tela, re.S).group(1)
    import html as HTML
    corpo = HTML.unescape(corpo)
    volta = c.post("/modelos", data={"chave": CABECALHO, "corpo": corpo + "<p>ensaio</p>", "acao": "salvar",
                                     "csrf_token": token}, follow_redirects=True).get_data(as_text=True)
    assert "Modelo gravado" in volta and "ensaio" in volta and "undefined" not in volta
    desfeito = c.post("/modelos", data={"chave": CABECALHO, "corpo": "", "acao": "restaurar",
                                        "csrf_token": token}, follow_redirects=True).get_data(as_text=True)
    assert "voltou ao padrão" in desfeito
    typo = c.post("/modelos", data={"chave": CABECALHO, "corpo": "{{ serventa.cidade }}", "acao": "salvar",
                                    "csrf_token": token}, follow_redirects=True).get_data(as_text=True)
    assert "não foi gravado" in typo or "serventa" in typo
