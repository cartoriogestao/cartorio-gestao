"""Os moldes do layout novo, lidos sem subir nada: o que dá para cobrar antes de abrir a tela.

O QUE DEFENDE
    A casa de ensaio só vê a ficha no estado que foi semeado, e um quadro que só aparece em outro
    estado passa por ela. Aqui se lê o molde inteiro: toda fase que o molde cita tem de existir no
    módulo da ficha, todo quadro recolhido tem fechamento e as ferramentas dele, e o que o projeto
    combinou para fases e passos vale em todos, e não só nos que têm teste próprio.

SÓ LÊ O CÓDIGO: não importa o app e não abre banco.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import jinja2
import pytest

RAIZ = Path(__file__).resolve().parent.parent
TELAS = RAIZ / "templates"
ESTATICOS = RAIZ / "static"

#: Ficha em fases ou abas -> o módulo puro que diz as fases dela.
FICHAS = {
    "notas_ato.html": ["notas_fases.py"],
    "ri_ficha.html": ["ri_abas.py"],
    "_ri_conferencia.html": ["caixa_abas.py"],
    "_rc_digitalizacao.html": ["rc_abas.py"],
    "ri_protocolo_ver.html": ["ri_fases_prenotacao.py"],
    "rcpn_habilitacao.html": ["habilitacao_fases.py"],
    "atrib_rcpn_ficha.html": ["rc_abas.py"],
    "caixa_protocolo.html": ["caixa_abas.py"],
    "usucapiao_ficha.html": ["usucapiao_abas.py"],
    "atrib_livro3_ficha.html": ["ra_abas.py"],
    "atrib_protesto_ficha.html": ["protesto_fases.py"],
    "rcpj_rtd_titulo.html": ["rg_titulo_fases.py"],
    "rcpj_rtd_fiduciaria.html": ["rg_fiduciaria.py"],
}


def _ler(nome: str) -> str:
    return (TELAS / nome).read_text(encoding="utf-8-sig")


def _moldes() -> list[str]:
    return sorted(p.name for p in TELAS.glob("*.html"))


def _sem_comentario(texto: str) -> str:
    return re.sub(r"\{#.*?#\}", "", texto, flags=re.S)


def _textos_do_modulo(arquivo: str) -> set[str]:
    """Toda palavra entre aspas do módulo: as chaves das fases estão entre elas."""
    arvore = ast.parse((RAIZ / arquivo).read_text(encoding="utf-8"))
    return {no.value for no in ast.walk(arvore) if isinstance(no, ast.Constant) and isinstance(no.value, str)}


def test_todo_molde_compila():
    env = jinja2.Environment(extensions=[])
    ruins = []
    for nome in _moldes():
        try:
            env.parse(_ler(nome))
        except jinja2.TemplateSyntaxError as erro:
            ruins.append(f"{nome}:{erro.lineno}: {erro.message}")
    assert not ruins, ruins


def test_a_lista_de_fichas_nao_esqueceu_ninguem():
    """Ficha nova em fases entra aqui, com o módulo dela. Sem isso, o guarda abaixo não a vê."""
    com_fase = {nome for nome in _moldes() if re.search(r'data-fase="', _sem_comentario(_ler(nome)))} - {"_fases.html"}
    assert com_fase == set(FICHAS), sorted(com_fase ^ set(FICHAS))


@pytest.mark.parametrize("molde", sorted(FICHAS))
def test_toda_fase_que_o_molde_cita_existe_no_modulo_da_ficha(molde):
    """Quadro de fase que não existe fica escondido para sempre, e sem erro nenhum."""
    citadas = set(re.findall(r'data-fase="([a-z_]+)"', _sem_comentario(_ler(molde))))
    existem = set().union(*(_textos_do_modulo(m) for m in FICHAS[molde]))
    assert citadas, f"{molde}: o guarda deixou de achar as fases"
    assert citadas <= existem, sorted(citadas - existem)


@pytest.mark.parametrize("modulo", sorted({m for ms in FICHAS.values() for m in ms}))
def test_a_ficha_da_conta_do_formato_que_a_regua_le(modulo):
    """`_fases.html` lê `fases`, `apoio`, `foco` e `inicial`: faltando um, a régua sai torta."""
    textos = _textos_do_modulo(modulo)
    assert {"fases", "apoio", "foco", "inicial"} <= textos, modulo


def _usa_quadros(nome: str) -> bool:
    return "_quadros_recolhidos.html" in _ler(nome) and nome != "_quadros_recolhidos.html"


def test_quem_usa_os_quadros_chama_as_ferramentas():
    sem = [n for n in _moldes() if _usa_quadros(n) and "ferramentas()" not in _sem_comentario(_ler(n))]
    assert not sem, f"quadro sem o script: o campo inválido num quadro fechado trava o botão: {sem}"


def test_os_quadros_cabem_em_varias_telas():
    """O guarda de cima pode deixar de achar: são 25 telas em 31/10/2026."""
    assert sum(1 for n in _moldes() if _usa_quadros(n)) >= 20


def test_todo_quadro_que_abre_fecha():
    """`abre(...)` abre um `<details>`, e quem fecha é o molde: esquecer um torce a tela inteira."""
    ruins = []
    for nome in _moldes():
        if not _usa_quadros(nome):
            continue
        texto = _sem_comentario(_ler(nome))
        abertos = len(re.findall(r"\babre\(", texto)) + len(re.findall(r"<details\b", texto))
        fechados = len(re.findall(r"</details>", texto)) + len(re.findall(r"\bfecha\(", texto))
        if abertos != fechados and "{% if layout_novo %}</details>" not in texto:
            ruins.append(f"{nome}: {abertos} abrem, {fechados} fecham")
    assert not ruins, ruins


def test_formulario_em_passos_tem_os_pedacos():
    """A régua, os blocos e o script. A barra de gravar se cobra com a tela aberta, na varredura."""
    ruins = []
    for nome in _moldes():
        texto = _sem_comentario(_ler(nome))
        if "data-cg-passos" not in texto or nome == "_passos_e_gravar.html":
            continue
        if "fases.js" not in texto and "abre_ficha" not in texto and "_passos_e_gravar.html" not in texto:
            ruins.append(f"{nome}: sem o script")
        if 'data-passo="' not in texto:
            ruins.append(f"{nome}: régua sem bloco")
    assert not ruins, ruins


def test_a_regua_das_fichas_so_sai_no_layout_novo():
    """Quem continua no antigo não recebe régua: o molde pergunta antes de chamar a conta."""
    ruins = []
    for nome in sorted(set(FICHAS) - {"_ri_conferencia.html", "_rc_digitalizacao.html"}):
        texto = _sem_comentario(_ler(nome))
        if "layout_novo" not in texto:
            ruins.append(nome)
    assert not ruins, ruins


#: Classe que é só marca, sem regra de propósito: a prenotação a lê com o olho, no HTML.
SO_DE_MARCA = {"cg-pren-espera"}
#: Classe montada na hora, que o leitor de moldes não enxerga: `cg-g-{{ cor }}`, no sino.
MONTADAS = {"cg-g-av", "cg-g-pe"}


def _classes_da_casca_nos_moldes() -> set[str]:
    achadas: set[str] = set()
    for nome in _moldes():
        texto = _ler(nome)
        for m in re.finditer(r'class="([^"]*)"', texto):
            achadas |= set(re.findall(r"\bcg-[a-z0-9-]+", re.sub(r"\{\{.*?\}\}|\{%.*?%\}", " ", m.group(1))))
    return achadas


def test_toda_classe_da_casca_tem_estilo_ou_script():
    """Classe sem regra é componente sem aparência: acontece ao renomear de um lado só."""
    definidas = (ESTATICOS / "casca.css").read_text(encoding="utf-8")
    definidas += "".join(p.read_text(encoding="utf-8") for p in (ESTATICOS / "casca.js", ESTATICOS / "fases.js"))
    for nome in _moldes():
        definidas += "".join(re.findall(r"<style.*?</style>", _ler(nome), flags=re.S))
        definidas += "".join(re.findall(r"<script.*?</script[^>]*>", _ler(nome), flags=re.S | re.I))
    sem = sorted(c for c in _classes_da_casca_nos_moldes() - SO_DE_MARCA if not re.search(rf"{re.escape(c)}\b", definidas))
    assert not sem, f"classes sem regra nem script: {sem}"


def test_o_css_da_casca_nao_tem_classe_que_ninguem_usa():
    """O contrário: regra que sobrou de um renome engana quem for mexer."""
    css = (ESTATICOS / "casca.css").read_text(encoding="utf-8")
    declaradas = set(re.findall(r"\.(cg-[a-z0-9-]+)", css)) - MONTADAS
    usadas = _classes_da_casca_nos_moldes()
    fontes = "".join(p.read_text(encoding="utf-8") for p in (ESTATICOS / "casca.js", ESTATICOS / "fases.js"))
    fontes += "".join(_ler(n) for n in _moldes())
    orfas = sorted(c for c in declaradas - usadas if not re.search(rf"\b{re.escape(c)}\b", fontes))
    assert not orfas, orfas


def test_o_link_para_as_configuracoes_olha_o_papel():
    """Configurações é só do oficial. O aviso que manda ir lá costuma sair num estado que a casa de ensaio
    não semeia, como a credencial que falta: por isso se lê o molde, além de abrir a tela."""
    ruins = []
    for nome in _moldes():
        if nome == "base.html":        # o menu antigo, que já pergunta antes
            continue
        linhas = _ler(nome).splitlines()
        for n, linha in enumerate(linhas, 1):
            if "url_for('settings')" in linha and "user.role" not in " ".join(linhas[max(0, n - 3):n]):
                ruins.append(f"{nome}:{n}")
    assert not ruins, ruins


def test_os_scripts_do_layout_novo_nao_montam_endereco():
    """O CodeQL recusou isso no WhatsApp (PR #94): o script só aciona o que o servidor pôs na página."""
    for arquivo in ("casca.js", "fases.js"):
        texto = (ESTATICOS / arquivo).read_text(encoding="utf-8")
        assert not re.search(r"location\.(href|assign|replace)\s*[=(]", texto), arquivo
        assert "innerHTML" not in texto, arquivo


def test_a_suite_tem_como_passar_pela_moldura_nova():
    """`CG_TESTE_MOLDURA=novo` leva a suíte inteira para a casca: é a última conferência antes de limpar."""
    conftest = (RAIZ / "tests" / "conftest.py").read_text(encoding="utf-8")
    assert 'CG_TESTE_MOLDURA' in conftest and '_navegacao_web.PADRAO_DE_FABRICA = ' in conftest
