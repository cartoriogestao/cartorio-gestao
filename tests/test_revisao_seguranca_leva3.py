"""A leva 3 dos consertos da revisão de segurança da 3.7.0 — 22/10/2026.

M2 (caixa: conferência de quem gere, estorno de caixa fechado a duas pessoas,
a cadeia de hash verificada), M3 (caminho de rede e programa de fora das
pastas de programas), M12/M8 (importação só de quem gere), M5 (o `.venv` de
Downloads não volta), M10 (o aviso da IA no malote), M11 (WhatsApp só em
https; código da ponte do CCN de uso único e com validade) e A9 (os isentos
do dia). Cada prova fica onde a regra mora.
"""
from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


# ------------------------------------------------------------------- M2: caixa

def test_a_conferencia_do_caixa_e_de_quem_gere(cg_casa):
    from conftest import cg_login
    db = cg_casa["db"]
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    db.create_user("carla", "CARLA EXEMPLO", SENHA, "USER")
    # o caixa FECHADO de outra pessoa: as recusas «não achei», «ainda aberto» e
    # «próprio caixa» vêm antes da do papel, e nenhuma delas é a desta prova
    from bd_nativo import banco
    with db.connect() as con:
        caixa_id = banco(con).escrever(
            """INSERT INTO cx_caixas(data, operador_nome, aberto_em, situacao, fechado_em)
               VALUES (%s, %s, %s, 'FECHADO', %s) RETURNING id""",
            ("2026-10-22", "MARIO EXEMPLO DOS SANTOS", "2026-10-22T08:00:00",
             "2026-10-22T18:00:00"))[0]["id"]
        con.commit()
    c = cg_casa["app"].test_client()
    cg_login(c, "carla", SENHA)
    tela = c.get("/caixa").get_data(as_text=True)
    r = c.post("/caixa", data={"csrf_token": _token(tela), "acao": "conferir",
                               "caixa_id": str(caixa_id)}, follow_redirects=True)
    assert "do oficial ou do gerente" in r.get_data(as_text=True)
    with db.connect() as con:
        assert banco(con).valor("SELECT conferido_em FROM cx_caixas WHERE id=%s",
                                (caixa_id,)) is None


def test_o_estorno_de_caixa_fechado_exige_outra_pessoa(cg_casa):
    import caixa_web as CW
    db = cg_casa["db"]
    mario = db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    beatriz = db.create_user("beatriz", "BEATRIZ EXEMPLO DE SOUZA", SENHA, "MANAGER")
    db.create_user("carla", "CARLA EXEMPLO", SENHA, "USER")
    # USER não estorna caixa fechado, nem com aprovador
    assert "oficial ou do gerente" in CW.segunda_assinatura_do_estorno(
        db, papel="USER", usuario_id=3, aprovador="mario", senha=SENHA)
    # ADMIN sozinho não basta
    assert "OUTRA pessoa" in CW.segunda_assinatura_do_estorno(
        db, papel="ADMIN", usuario_id=mario, aprovador="", senha="")
    # o aprovador não pode ser ele mesmo
    assert "outra pessoa" in CW.segunda_assinatura_do_estorno(
        db, papel="ADMIN", usuario_id=mario, aprovador="mario", senha=SENHA)
    # senha errada, ou aprovador USER, não aprova
    assert "não reconhecido" in CW.segunda_assinatura_do_estorno(
        db, papel="ADMIN", usuario_id=mario, aprovador="beatriz", senha="errada")
    assert "não reconhecido" in CW.segunda_assinatura_do_estorno(
        db, papel="ADMIN", usuario_id=mario, aprovador="carla", senha=SENHA)
    # gerente aprova o estorno do oficial, e vice-versa
    assert CW.segunda_assinatura_do_estorno(
        db, papel="ADMIN", usuario_id=mario, aprovador="beatriz", senha=SENHA) == ""
    assert CW.segunda_assinatura_do_estorno(
        db, papel="MANAGER", usuario_id=beatriz, aprovador="mario", senha=SENHA) == ""


def test_a_cadeia_do_caixa_fecha_e_acusa_o_que_foi_mexido():
    import compliance as C
    import caixa_schema as CXS

    def linha(i, caixa, ano, valor, anterior, natureza="RECEBIMENTO", desc="x", historico=None):
        h = CXS.hash_lancamento(caixa, "2026-10-22", natureza, valor, desc, anterior)
        return {"id": i, "caixa_id": caixa, "ano": ano, "numero": i, "data": "2026-10-22",
                "natureza": natureza, "valor": valor, "descricao": desc,
                "historico": historico, "hash_lancamento": h}

    l1 = linha(1, 7, 2026, "10,00", None)
    l2 = linha(2, 7, 2026, "20,00", l1["hash_lancamento"])
    # a grafia do protocolo: o anterior é o último do ANO, mesmo noutro caixa
    l3 = linha(3, 8, 2026, "30,00", l2["hash_lancamento"])
    assert C.divergencias_da_cadeia_do_caixa([l1, l2, l3]) == []
    # editado pela tela: o valor mudou, o histórico guarda o de antes — fecha
    l2_editado = dict(l2, valor="25,00",
                      historico='[{"em": "x", "por": "y", "antes": {"valor": "20,00", '
                                '"natureza": "RECEBIMENTO", "descricao": "x"}}]')
    assert C.divergencias_da_cadeia_do_caixa([l1, l2_editado, l3]) == []
    # mexido por fora: o valor mudou e não há histórico — acusa
    l2_mexido = dict(l2, valor="2,00")
    fora = C.divergencias_da_cadeia_do_caixa([l1, l2_mexido, l3])
    assert [f["id"] for f in fora] == [2]
    # e `desde` não esconde o anterior: o 1 fica fora da janela e o 2 fecha
    assert C.divergencias_da_cadeia_do_caixa([l1, l2, l3], desde="2026-10-22") == []


def test_a_regra_da_cadeia_esta_registrada_no_compliance():
    import compliance as C
    assert "CAIXA_CADEIA" in dict(C.REGRAS)


# --------------------------------------------------------------- M3: caminhos

def test_caminho_de_rede_nao_entra_nas_configuracoes(cg_casa_logada):
    c = cg_casa_logada["c"]
    tela = c.get("/configuracoes").get_data(as_text=True)
    r = c.post("/configuracoes", data={"csrf_token": _token(tela),
                                       "archive_root": r"\\maquina\arquivos"},
               follow_redirects=True)
    assert "Caminho de rede não é aceito" in r.get_data(as_text=True)
    assert cg_casa_logada["db"].get_setting("archive_root", "") != r"\\maquina\arquivos"


def test_programa_configurado_so_das_pastas_de_programas(tmp_path, monkeypatch):
    import impressao_pdf as IP
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "Program Files"))
    monkeypatch.setenv("ProgramFiles(x86)", str(tmp_path / "Program Files (x86)"))
    monkeypatch.setenv("ProgramW6432", str(tmp_path / "Program Files"))
    bom = tmp_path / "Program Files" / "Google" / "Chrome" / "Application" / "chrome.exe"
    assert IP.programa_configurado_confiavel(bom, IP.NOMES_DO_CHROME)
    assert not IP.programa_configurado_confiavel(tmp_path / "Downloads" / "chrome.exe",
                                                 IP.NOMES_DO_CHROME)
    assert not IP.programa_configurado_confiavel(
        tmp_path / "Program Files" / "x" / "qualquer.exe", IP.NOMES_DO_CHROME)
    # e o caminho configurado fora das pastas é ignorado — vale a detecção
    monkeypatch.setattr(IP, "CAMINHOS_CHROME", ())
    monkeypatch.setattr(IP.shutil, "which", lambda *_: None)
    fora = tmp_path / "Downloads" / "chrome.exe"
    fora.parent.mkdir()
    fora.write_bytes(b"x")
    assert IP.onde_esta_o_chrome(lambda k, p="": str(fora)) is None


# ---------------------------------------------------- M12 / M8: importação

def test_a_importacao_do_acervo_continua_aberta_ao_user_por_ordem_dele(cg_casa):
    """M12/M8 NÃO foi aplicado: o oficial decidiu em 11/10/2026 «manter abertas»
    as cargas ao perfil USER (`test_livro3_importar_do_acervo.py`), e a leva 3
    as fechou sem saber da ordem. Voltou no mesmo dia; o risco fica declarado
    no relatório da revisão, para ele decidir com o fato na mão."""
    app = cg_casa["app"]
    for rota in ("rcpn_importar_acervo", "livro3_importar_do_acervo",
                 "importar_padrao_tela", "rcpn_importar"):
        vista = app.view_functions.get(rota)
        if vista is None:
            continue
        assert "USER" in getattr(vista, "papeis_exigidos", ()), rota


# ---------------------------------------------------------------- M5: o .venv

def test_o_instalador_nao_reaproveita_venv_do_perfil():
    texto = (RAIZ / "installer" / "instalar_servidor.ps1").read_text(encoding="utf-8")
    assert "NAO SE REAPROVEITA .venv" in texto
    assert "if($false){" in texto


# --------------------------------------------------------------- M10: malote

def test_a_tarefa_do_malote_avisa_que_o_texto_e_da_ia():
    import gestor_expedientes as GE
    from datetime import date
    corpo = GE._corpo({"id": 1}, {"resumo": "pede certidão", "o_que_fazer": "emitir"},
                      None, date(2026, 10, 22))
    assert "escritos pela IA" in corpo
    assert "não é ordem da casa" in corpo


# -------------------------------------------------- M11: WhatsApp e ponte do CCN

def test_o_whatsapp_nao_manda_o_segredo_por_http(monkeypatch):
    import wa_puxar as WP
    monkeypatch.setattr(WP.WA, "ler_config",
                        lambda con, chave: "http://caixa.exemplo/puxar")
    r = WP.puxar_pendentes(None)
    assert r["ok"] is False and "https" in r["motivo"]


def test_o_codigo_do_lote_do_ccn_e_de_uso_unico_e_vence():
    import ccn_envio as CE
    agora = datetime(2026, 10, 22, 12, 0)
    aberto = {"situacao": "GERADO", "gerado_em": "2026-10-22T10:00:00"}
    assert CE.recusa_do_lote(aberto, agora) == ""
    assert "já usado" in CE.recusa_do_lote(dict(aberto, situacao="CONCLUIDO"), agora)
    assert "vencido" in CE.recusa_do_lote(dict(aberto, gerado_em="2026-10-20T10:00:00"), agora)


def test_o_codigo_da_consulta_do_ccn_e_de_uso_unico_e_vence():
    import ccn_consulta as CQ
    agora = datetime(2026, 10, 22, 12, 0)
    pedida = {"situacao": "PEDIDA", "pedida_em": "2026-10-22T10:00:00", "respondida_em": None}
    assert CQ.recusa_da_consulta(pedida, agora) == ""
    assert "já usado" in CQ.recusa_da_consulta(dict(pedida, respondida_em="2026-10-22T11:00:00"), agora)
    assert "vencido" in CQ.recusa_da_consulta(dict(pedida, pedida_em="2026-10-20T10:00:00"), agora)


# ---------------------------------------------------------- A9: isentos do dia

def test_os_isentos_do_dia_viram_relato_para_o_oficial():
    import gestor_fiscal as GF
    from datetime import date

    class _Bd:
        def ler(self, sql, args=None):
            assert args == ("2026-10-22", "2026-10-23")
            return [{"numero": "SELOA", "tabela": "nt_atos", "ato_id": 1, "atribuicao": "NOTAS",
                     "obtido_por": "FULANA", "texto": "Total R$ 0,00 Selo Isento"},
                    {"numero": "SELOB", "tabela": "nt_atos", "ato_id": 2, "atribuicao": "NOTAS",
                     "obtido_por": "FULANA", "texto": "Total R$ 80,00 Emol R$ 60,00"}]

    achados = GF._isentos_do_dia(_Bd(), date(2026, 10, 22))
    assert len(achados) == 1
    assert achados[0]["regra"] == "FISCAL_ISENTOS_DO_DIA"
    assert "SELOA" in achados[0]["detalhe"] and "SELOB" not in achados[0]["detalhe"]
    assert "FISCAL_ISENTOS_DO_DIA" in GF.REGRAS_SEM_TAREFA
    assert "FISCAL_ISENTOS_DO_DIA" in GF.ROTULOS
