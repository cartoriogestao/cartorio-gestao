"""A leva 2 dos consertos da revisão de segurança da 3.7.0 — 22/10/2026.

Achados A6 (robô), M6 (`.cred` perde a ACL), M7 (o filtro deixava `form`,
`formaction` e `url(http://…)`), A8 (o Chrome das folhas com rede), M9 (CPF
em claro na auditoria; exportação sem registro) e os interruptores de A13 e
M19. Cada teste prova a regra onde ela mora, sem rede e sem o aparelho.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


# ------------------------------------------------------------------ A6: robô

def test_robo_nao_pode_ser_admin_nem_gerente(cg_casa):
    db = cg_casa["db"]
    for papel in ("ADMIN", "MANAGER"):
        with pytest.raises(ValueError, match="USER ou AUDITOR"):
            db.create_user(f"robo_{papel.lower()}", "Robo de Exemplo", SENHA,
                           papel, eh_robo=1)
    assert db.create_user("robo_user", "Robo de Exemplo", SENHA, "USER", eh_robo=1)


def test_o_robo_nao_entra_nas_rotas_de_gente(cg_casa):
    """Com a credencial do robô, usuários, configurações e caixa respondem
    403; a tela de entrada continua abrindo, e um USER de verdade entra."""
    from conftest import cg_login
    db = cg_casa["db"]
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    db.create_user("robo_rcpn", "Robo Nascimento RCPN", SENHA, "USER", eh_robo=1)
    c = cg_casa["app"].test_client()
    cg_login(c, "robo_rcpn", SENHA)
    assert c.get("/").status_code == 200
    for rota in ("/usuarios", "/configuracoes", "/caixa", "/atualizacoes"):
        assert c.get(rota).status_code == 403, rota
    # e o POST também — a rota de gente não grava para máquina
    assert c.post("/caixa", data={"csrf_token": _token(
        c.get("/").get_data(as_text=True))}).status_code == 403


def test_o_selo_nao_sai_em_nome_de_maquina():
    import ato_selado as AS
    from test_ato_selado import banco as banco_de_teste, SELO_BOM, CNS, AGORA
    con = banco_de_teste()
    with pytest.raises(AS.AtoError, match="máquina"):
        AS.registrar_selo_obtido_a_mao(
            con, SELO_BOM, tabela="pt_atos", ato_id=1, atribuicao="PROTESTO",
            agora=AGORA, cns=CNS, usuario="Robo Nascimento RCPN")


def test_o_nome_de_fallback_nao_vem_do_cadastro():
    """Sem substituta nem oficial configurados, a resposta é «ninguém» — e
    não o primeiro usuário da lista."""
    import nome_humano as NOMEHUM

    class _Db:
        def get_setting(self, chave, padrao=""):
            return ""

        def list_users(self, active_only=True):
            return [{"full_name": "FULANO QUE ESTAVA NO ALTO", "username": "fulano"}]

    assert NOMEHUM.fallbacks_da_casa(_Db()) == []
    assert NOMEHUM.nome_humano_para_ato("Robo X", *NOMEHUM.fallbacks_da_casa(_Db())) == ""


# ------------------------------------------------------------------ M6: .cred

def test_a_credencial_gravada_fica_so_do_servico_na_hora(tmp_path, monkeypatch):
    import permissao_local as PERM
    import centrais_cred as CRED
    chamadas = []
    monkeypatch.setattr(PERM, "restringir",
                        lambda caminho, **k: chamadas.append((str(caminho), k)) or None)
    destino = CRED.gravar(CRED.CRA, usuario="u", senha="s", pasta=tmp_path)
    assert chamadas and chamadas[-1][0] == str(destino)
    assert chamadas[-1][1].get("de_novo") is True
    CRED.gravar_token(CRED.ONRTDPJ, token="t", pasta=tmp_path)
    assert len(chamadas) == 2


def test_o_pfx_esta_entre_os_segredos_da_pasta():
    import permissao_local as PERM
    assert "*.pfx" in PERM.SEGREDOS_DA_PASTA


# -------------------------------------------------------------- M7: o filtro

def test_o_filtro_tira_form_formaction_e_action():
    import html_sem_script as HSS
    saida = HSS.limpar('<p>a</p><button form="f1" formaction="https://fora/x">ok</button>'
                       '<form action="https://fora/y"><input name="q"></form>')
    assert "formaction" not in saida
    assert 'form="f1"' not in saida
    assert "fora/y" not in saida
    assert "<button" in saida and "ok" in saida


def test_no_css_so_imagem_embutida_e_endereco_relativo():
    import html_sem_script as HSS
    fica = HSS.limpar('<p style="background:url(data:image/png;base64,iVBOR=)">a</p>'
                      '<p style="background:url(imagens/x.png)">b</p>')
    assert "data:image/png;base64,iVBOR=" in fica
    assert "url(imagens/x.png)" in fica
    sai = HSS.limpar('<p style="background:url(http://fora/x.png)">c</p>'
                     '<style>p{background-image:image-set("https://fora/y.png" 1x)}</style>')
    # o endereço de fora não sobrevive: no atributo o estilo inteiro cai, e no
    # <style> ele vira fragmento («#…»), que o navegador não vai buscar
    assert "url(http://fora" not in sai and "fora/x.png" not in sai
    assert '"https://fora' not in sai
    assert "#https://fora" in sai


# ----------------------------------------------------------- A8: Chrome sem rede

def test_o_chrome_das_folhas_sai_sem_rede(monkeypatch, tmp_path):
    import impressao_pdf as IP
    visto = {}

    def falso_run(comando, **k):
        visto["comando"] = list(comando)
        for arg in comando:
            if str(arg).startswith("--print-to-pdf="):
                Path(str(arg).split("=", 1)[1]).write_bytes(b"%PDF-1.4 falso")
        return None

    monkeypatch.setattr(IP, "onde_esta_o_chrome", lambda get_setting=None: tmp_path / "chrome.exe")
    monkeypatch.setattr(IP.subprocess, "run", falso_run)
    assert IP.pdf_de_html_chrome("<p>folha</p>", nome="teste").startswith(b"%PDF")
    assert "--proxy-server=127.0.0.1:1" in visto["comando"]
    assert "--host-rules=MAP * ~NOTFOUND" in visto["comando"]


# ---------------------------------------------------------------- M9: auditoria

def test_toda_exportacao_fica_na_auditoria(cg_casa_logada):
    from bd_nativo import banco
    c = cg_casa_logada["c"]
    assert c.get("/relatorios/tarefas.csv").status_code == 200
    with cg_casa_logada["db"].connect() as con:
        linha = banco(con).um(
            "SELECT details FROM audit_logs WHERE action = 'EXPORTACAO' "
            "ORDER BY id DESC LIMIT 1")
    assert linha, "a exportação não ficou na auditoria"
    assert "tasks_csv" in str(linha["details"])
    assert "tarefas.csv" in str(linha["details"])


def test_o_cpf_nao_fica_em_claro_na_auditoria(cg_casa):
    from bd_nativo import banco
    db = cg_casa["db"]
    db.log(None, "teste", "TESTE_MASCARA", "TESTE", 1,
           {"cpf": "123.456.789-01", "parte": {"documento": "12345678901"},
            "selo": "12345678901", "hash": "a12345678901b", "nome": "FULANO"})
    with db.connect() as con:
        linha = banco(con).um(
            "SELECT details FROM audit_logs WHERE action = 'TESTE_MASCARA' "
            "ORDER BY id DESC LIMIT 1")
    detalhes = str(linha["details"])
    assert "123.456.789-01" not in detalhes and "12345678901\"" not in detalhes.split('"selo"')[0]
    assert "*********01" in detalhes
    # o que NÃO é documento fica como estava: selo, hash, nome
    assert '"selo": "12345678901"' in detalhes
    assert '"hash": "a12345678901b"' in detalhes
    assert "FULANO" in detalhes


# ------------------------------------------------------- A13 / M19: interruptores

def test_o_envio_automatico_da_censec_respeita_o_interruptor():
    import censec_automatico as CA
    from datetime import date

    class _Db:
        def __init__(self, valor):
            self.valor = valor

        def get_setting(self, chave, padrao=""):
            return self.valor if chave == CA.CHAVE_DO_INTERRUPTOR else padrao

        def connect(self):
            raise AssertionError("desligado não pode nem olhar o banco")

    saida = CA.enviar(_Db("DESLIGADO"), date(2026, 10, 22), cns="000000")
    assert saida == [{"situacao": "DESLIGADO",
                      "motivo": "envio automático desligado nas configurações"}]
    assert CA.envio_ligado(_Db("")) is True
    assert CA.envio_ligado(_Db("LIGADO")) is True


def test_a_tela_de_configuracoes_guarda_os_dois_interruptores(cg_casa_logada):
    c = cg_casa_logada["c"]
    tela = c.get("/configuracoes").get_data(as_text=True)
    assert 'name="censec_envio_automatico"' in tela
    assert 'name="rtdpj_corrigir_automatico"' in tela
    # desmarcar os dois e salvar: ficam DESLIGADO
    dados = {"csrf_token": _token(tela)}
    r = c.post("/configuracoes", data=dados, follow_redirects=True)
    assert r.status_code == 200
    db = cg_casa_logada["db"]
    assert db.get_setting("censec_envio_automatico", "") == "DESLIGADO"
    assert db.get_setting("rtdpj_corrigir_automatico", "") == "DESLIGADO"
