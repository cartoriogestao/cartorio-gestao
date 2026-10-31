"""As telas longas do administrador em quadros recolhidos, no layout novo.

O QUE ELES DEFENDEM
    Projeto do novo layout, 30/10/2026. O risco é configuração sumir, campo deixar de ser enviado por
    estar num quadro fechado, ou o navegador recusar o envio sem dizer onde. A parte de baixo usa o
    sistema de pé, e roda na outra máquina.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

TELAS = RAIZ / "templates"
MOLDES = ("settings.html", "importar_padrao.html", "gestor_ia.html", "nucleo_numeracao.html")
# O formulário geral das Configurações. Quem tirar um campo daqui tem de dizer por quê.
CAMPOS_DO_FORMULARIO_GERAL = {
    "csrf_token", "unit_name", "ri_registrador", "ri_substituta", "ri_cidade", "ri_uf", "archive_root",
    "pastas_de_importacao", "backup_dir", "malote_pasta", "gratuidade_pasta", "alert_days",
    "session_timeout_minutes", "session_absolute_hours", "network_host", "network_port", "discovery_enabled",
    "discovery_port", "backup_retencao_dias", "auto_backup", "require_backup_assignee",
    "impressao_formato_padrao", "modulo_protesto_alcance", "censec_envio_automatico",
    "rtdpj_corrigir_automatico", "password_min_length", "password_require_upper", "password_require_lower",
    "password_require_digit", "categories", "sources", "sectors",
}


def _ler(nome: str) -> str:
    return (TELAS / nome).read_text(encoding="utf-8-sig")


def _formulario_geral(html: str) -> str:
    inicio = html.index('<form method="post" class="form-grid">')
    return html[inicio:html.index("</form>", inicio)]


def test_o_formulario_geral_e_um_so_e_leva_todos_os_campos():
    corpo = _formulario_geral(_ler("settings.html"))
    assert "<form" not in corpo[1:]
    assert set(re.findall(r'\bname="(\w+)"', corpo)) == CAMPOS_DO_FORMULARIO_GERAL


def test_todo_campo_que_a_rota_le_esta_no_formulario():
    """Campo que a rota lê e o formulário não manda é configuração que se apaga ao salvar."""
    fonte = (RAIZ / "app.py").read_text(encoding="utf-8")
    rota = fonte[fonte.index("def settings():"):fonte.index("def configuracoes_cra_envio")]
    lidos = set(re.findall(r'request\.form\.get\(\s*"(\w+)"', rota)) | set(re.findall(r'"(\w+)" in request\.form', rota))
    assert lidos and lidos <= CAMPOS_DO_FORMULARIO_GERAL, lidos - CAMPOS_DO_FORMULARIO_GERAL


@pytest.mark.parametrize("molde", MOLDES)
def test_cada_quadro_fecha(molde):
    texto = _ler(molde)
    assert texto.count("abre(") + texto.count("<details") == texto.count("</details>"), molde
    assert "ferramentas()" in texto, molde


def test_o_campo_invalido_abre_o_quadro_e_o_endereco_tambem():
    texto = _ler("_quadros_recolhidos.html")
    assert 'addEventListener("invalid"' in texto and "abrirEmVolta(ev.target); }, true)" in texto
    assert 'addEventListener("hashchange", doEndereco)' in texto


def test_os_enderecos_que_outras_telas_usam_continuam():
    texto = _ler("settings.html")
    assert "abre('cfg-centrais'" in texto and 'id="cfg-centrais"' in texto
    for tela in ("centrais_status.html", "gestor_protesto_integracoes.html"):
        assert "#cfg-centrais" in _ler(tela), tela


def test_o_envio_a_cra_nao_fica_dentro_da_ajuda_recolhida():
    texto = _ler("settings.html")
    assert texto.index("{{ envio_a_cra }}<details") < texto.index("cfg-centrais-ajuda")


def test_o_que_espera_acao_vem_antes_no_layout_novo():
    ia = _ler("gestor_ia.html")
    assert ia.index("{% if layout_novo and sem_dados %}{{ os_fornecedores }}") < ia.index("abre('ia-cautelas'")
    assert ia.count("{{ os_fornecedores }}") == 2
    numeracao = _ler("nucleo_numeracao.html")
    assert numeracao.index("esperam o número que só você pode dizer") < numeracao.index("abre('num-' ~ numero")
    assert numeracao.index("abre('num-' ~ numero") < numeracao.index("abre('num-como-funciona'")
    configuracoes = _ler("settings.html")
    assert configuracoes.index("Centrais sem credencial") < configuracoes.index("abre('cfg-unidade'")
    importar = _ler("importar_padrao.html")
    assert importar.index('<form method="post" class="card"') < importar.index("abre('imp-arquivo'")


def test_a_nota_das_rotinas_diz_o_que_a_rotina_faz():
    """Sem a chave gravada, a rotina roda: a nota não pode dizer «desligada» sem ela estar."""
    texto = _ler("settings.html")
    assert "s.get('censec_envio_automatico') == 'DESLIGADO'" in texto
    assert "s.get('rtdpj_corrigir_automatico') == 'DESLIGADO'" in texto


def test_o_layout_antigo_continua_com_o_que_tinha():
    texto = _ler("settings.html")
    assert '<nav class="notice cfg-indice"' in texto
    assert '<section class="panel" id="cfg-centrais">' in texto
    assert "{{ 'cg-cfg-geral' if layout_novo else 'panel' }}" in texto


# ------------------------------------------------------------- com o sistema de pé


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


def _campos_da_tela(html: str) -> list:
    """Só o conteúdo da tela: na moldura antiga, as barras de aviso ficam no mesmo `<main>`, e têm campos."""
    inicio = html.find('<div class="content">')
    inicio = inicio if inicio >= 0 else html.index("<main")
    return sorted(re.findall(r'\bname="(\w+)"', html[inicio:html.rindex("</main>")]))


@pytest.mark.parametrize("caminho", ["/configuracoes", "/importar-padrao", "/administrativo/gestor/ia", "/nucleo/numeracao"])
def test_os_quadros_so_saem_no_layout_novo(cg_app, caminho):
    c = _entrar(cg_app, "quadros_a")
    _layout(c, "antigo")
    antigo = c.get(caminho).get_data(as_text=True)
    assert "cg-quadro" not in antigo
    _layout(c, "novo")
    novo = c.get(caminho).get_data(as_text=True)
    assert "cg-quadro" in novo
    assert novo.count("<details") == novo.count("</details>")
    # O MESMO FORMULÁRIO NOS DOIS: nenhum campo some, nem no recolhido.
    assert _campos_da_tela(antigo) == _campos_da_tela(novo)


def test_salvar_com_tudo_recolhido_grava_o_mesmo(cg_app):
    d = cg_app.extensions["db"]
    c = _entrar(cg_app, "quadros_b")
    _layout(c, "novo")
    html = c.get("/configuracoes").get_data(as_text=True)
    corpo = _formulario_geral(html)
    assert 'class="panel cg-quadro" id="cfg-senhas"' in corpo and "open" not in re.search(
        r'id="cfg-senhas"[^>]*>', corpo).group(0)
    dados = {"csrf_token": _token(html), "unit_name": "Serventia de Ensaio", "alert_days": "9",
             "session_timeout_minutes": "720", "password_min_length": "8", "network_port": "8765",
             "discovery_port": "8766", "categories": "Uma", "sources": "Duas", "sectors": "Tres"}
    assert c.post("/configuracoes", data=dados).status_code == 302
    assert d.get_setting("alert_days", "") == "9"
    assert d.get_setting("password_min_length", "") == "8"


def test_a_cifra_perdida_avisa_no_alto_e_abre_o_quadro(cg_app, monkeypatch):
    import backup as BKP

    monkeypatch.setattr(BKP, "situacao_da_cifra", lambda _pasta: "perdida")
    c = _entrar(cg_app, "quadros_d")
    _layout(c, "novo")
    html = c.get("/configuracoes").get_data(as_text=True)
    assert html.index("A senha da cifra do backup não abre") < html.index('id="cfg-unidade"')
    assert re.search(r'id="cfg-backup-protecao"[^>]*\bopen\b', html)


def test_quem_nao_e_administrador_continua_sem_abrir_as_configuracoes(cg_app):
    d = cg_app.extensions["db"]
    try:
        d.create_user("quadros_c", "Operador Exemplo", "Senha#12345", "USER")
    except Exception:                                              # noqa: BLE001
        pass
    c = cg_app.test_client()
    c.post("/login", data={"username": "quadros_c", "password": "Senha#12345",
                           "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    assert c.get("/configuracoes").status_code == 403
