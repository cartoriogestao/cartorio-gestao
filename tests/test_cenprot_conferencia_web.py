"""As TELAS da conferência CENPROT × sistema e a trava do protesto (29/10/2026).

O QUE ESTES TESTES GUARDAM, E QUE O DE DOMÍNIO NÃO ALCANÇA
      - a tela existe, está no menu e no painel do Protesto, e abre SEM falar
        com a rede (a Central de mentira estoura se for chamada);
      - todo formulário dela manda o `csrf_token`;
      - a ficha recusa protestar o título que a Central dá por pago — e o ato
        não nasce;
      - com a afirmação expressa ele nasce, e a afirmação fica no
        `detalhe_json` do ato e na auditoria (`AFIRMACAO_EXPRESSA`);
      - o lote «A protestar» recusa o mesmo título e manda afirmar na ficha;
      - o título de banco continua sendo protestado como sempre, sem rede.

Números de pedido e documentos fictícios.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import cenprot_api as API  # noqa: E402
import cenprot_conferencia as C  # noqa: E402
from bd_nativo import banco as nativo  # noqa: E402

SENHA = "Senha#12345"
CPF = "00000000191"
TEXTO = ("Afirmo, sob minha responsabilidade, que conferi o pedido no portal "
         "da CENPROT e que o título não foi pago pelo devedor.")
MOTIVO = "Cenário de teste: tríduo vencido"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def s(cg_casa):
    bd = cg_casa["db"]
    bd.create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    bd.set_settings({"modulo_protesto_alcance": "TODOS"})
    c = cg_casa["app"].test_client()
    c.post("/login",
           data={"username": "tabeliao", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {"app": cg_casa["app"], "c": c, "db": bd}


def central(monkeypatch, respostas: dict) -> list:
    chamadas: list = []

    def falsa(ambiente=None, *, numero="", data="", pasta=None):
        chamadas.append(numero)
        r = respostas.get(numero)
        if isinstance(r, Exception):
            raise r
        return [] if r is None else [r]

    monkeypatch.setattr(API, "pedidos_de_protesto", falsa)
    return chamadas


def pedido(numero="9900001", *, status="Apontado / em andamento") -> dict:
    return {"dados_pedido": {"cd_pedido_protesto": int(numero),
                             "ds_status": status, "ocorrencia": "",
                             "ds_ocorrencia": "", "dt_ocorrencia": "2026-10-27",
                             "nm_nr_protocolo": "2608310001",
                             "dados_titulo": {"nm_nr_titulo": "84713/1",
                                              "vl_titulo": 1482.78}},
            "devedor": {"nm_devedor": "DEVEDOR FICTICIO",
                        "nm_nr_identificacao": "000.000.001-91"},
            "dados_cedente": {"nm_cedente": "CREDOR FICTICIO"}}


def intimado(s, *, cenprot=True, numero="84713/1",
             protocolo="2608310001") -> int:
    """Um título intimado em agosto (tríduo vencido), gravado direto."""
    agora = s["db"].now()
    with s["db"].transaction() as con:
        bd = nativo(con)
        tid = int(bd.escrever(
            """INSERT INTO pt_titulos(especie, numero_titulo, nosso_numero,
                   valor_centavos, saldo_centavos, situacao, protocolo,
                   origem, origem_chave, apresentante_codigo, criado_em,
                   motivo_protesto, cedente_nome)
               VALUES ('DMI',%s,'00200000991',148278,148278,'INTIMADO',%s,
                       %s,%s,%s,%s,'1','CREDOR FICTICIO') RETURNING id""",
            (numero, protocolo, "CENPROT" if cenprot else "CRA",
             "CENPROT-PEDIDO:9900001" if cenprot else f"CRA:9:{numero}",
             "TAB" if cenprot else "001", agora))[0]["id"])
        bd.escrever("""INSERT INTO pt_devedores(titulo_id, nome, documento_tipo,
                           documento_numero) VALUES (%s,'DEVEDOR FICTICIO','CPF',%s)""",
                    (tid, CPF))
        for tipo, data, det in (("APONTAMENTO", "2026-08-18", "{}"),
                                ("INTIMACAO", "2026-08-20", '{"modo": "EDITAL"}')):
            bd.escrever("""INSERT INTO pt_atos(titulo_id, tipo, data_ato,
                               detalhe_json, origem, criado_em)
                           VALUES (%s,%s,%s,%s,'MANUAL',%s)""",
                        (tid, tipo, data, det, agora))
    return tid


def _ler(s, sql, parametros=None) -> list[dict]:
    with s["db"].connect() as con:
        return [dict(r) for r in nativo(con).ler(sql, parametros)]


def _lancar(s, tid, **campos):
    html = s["c"].get(f"/protesto/{tid}").get_data(as_text=True)
    return s["c"].post(f"/protesto/{tid}/lancar",
                       data={"csrf_token": _token(html), "ato": "PROTESTO",
                             "motivo_atraso": MOTIVO, **campos},
                       follow_redirects=True).get_data(as_text=True)


def _protestos(s, tid) -> list[dict]:
    return _ler(s, "SELECT * FROM pt_atos WHERE titulo_id=%s AND tipo='PROTESTO'",
                (tid,))


# ------------------------------------------------------------- a tela


def test_a_tela_abre_sem_falar_com_a_rede_e_esta_no_menu(s, monkeypatch):
    central(monkeypatch, {"9900001": AssertionError("a tela falou com a rede")})
    intimado(s)
    r = s["c"].get("/protesto/cenprot/conferencia")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Conferência CENPROT × sistema" in html          # o item do menu
    assert "a Central ainda não foi consultada" in html
    formularios = re.findall(r"<form[^>]*method=[\"']post[\"'].*?</form>",
                             html, re.DOTALL | re.IGNORECASE)
    assert len(formularios) >= 2, "consultar e registrar a liquidação"
    for f in formularios:
        assert "csrf_token" in f


def test_o_painel_do_protesto_leva_a_conferencia(s):
    import protesto_roteiro as PR
    botoes = [b["tela"] for e in PR.ETAPAS_DO_DIA for b in e["botoes"]]
    assert "protesto_cenprot_conferencia" in botoes
    html = s["c"].get("/protesto/roteiro").get_data(as_text=True)
    assert 'href="/protesto/cenprot/conferencia"' in html


def test_consultar_pela_tela_mostra_a_divergencia_e_o_caminho(s, monkeypatch):
    tid = intimado(s)
    chamadas = central(monkeypatch, {"9900001": pedido(status="Pago")})
    tela = s["c"].get("/protesto/cenprot/conferencia").get_data(as_text=True)
    html = s["c"].post("/protesto/cenprot/conferencia/consultar",
                       data={"csrf_token": _token(tela)},
                       follow_redirects=True).get_data(as_text=True)
    assert chamadas == ["9900001"]
    assert f'id="titulo-{tid}"' in html and "DIVERGE" in html
    assert "NÃO PROTESTE" in html


def test_o_numero_que_nao_se_le_nao_derruba_a_tela(s, monkeypatch):
    central(monkeypatch, {})
    tela = s["c"].get("/protesto/cenprot/conferencia").get_data(as_text=True)
    r = s["c"].post("/protesto/cenprot/conferencia/consultar",
                    data={"csrf_token": _token(tela), "titulo_id": "²"},
                    follow_redirects=True)
    assert r.status_code == 200


# ------------------------------------------------------------- a trava


def test_a_ficha_recusa_protestar_o_que_a_central_da_por_pago(s, monkeypatch):
    tid = intimado(s)
    central(monkeypatch, {"9900001": pedido(status="Pago")})
    html = _lancar(s, tid)
    assert "Protesto NÃO lavrado" in html
    assert _protestos(s, tid) == []
    # A ficha mostra a caixa da afirmação para o título de origem CENPROT.
    ficha = s["c"].get(f"/protesto/{tid}").get_data(as_text=True)
    assert 'name="afirmo"' in ficha and 'name="afirmacao"' in ficha


def test_com_a_afirmacao_o_texto_vai_ao_ato_e_a_auditoria(s, monkeypatch):
    tid = intimado(s)
    central(monkeypatch, {"9900001": pedido(status="Pago")})
    _lancar(s, tid, afirmo="1", afirmacao=TEXTO)
    [rastro] = _ler(s, """SELECT * FROM audit_logs WHERE action=%s
                           AND entity_type='pt_titulos' AND entity_id=%s""",
                    (C.ACAO_DA_AUDITORIA, tid))
    det = json.loads(rastro["details"])
    assert det["regra"] == C.REGRA_DIVERGENTE and det["afirmacao"] == TEXTO
    assert det["o_que_faltava"]
    [p] = _protestos(s, tid)
    detalhe = json.loads(p["detalhe_json"])
    assert detalhe[C.CHAVE_NO_DETALHE][0]["afirmacao"] == TEXTO


def test_o_titulo_de_banco_nao_passa_pela_central(s, monkeypatch):
    tid = intimado(s, cenprot=False, numero="555/1", protocolo="2608310002")
    chamadas = central(monkeypatch, {})
    ficha = s["c"].get(f"/protesto/{tid}").get_data(as_text=True)
    assert 'name="afirmo"' not in ficha
    _lancar(s, tid)
    assert chamadas == []
    assert len(_protestos(s, tid)) == 1


def test_o_lote_recusa_e_manda_afirmar_na_ficha(s, monkeypatch):
    tid = intimado(s)
    banco_tid = intimado(s, cenprot=False, numero="555/1", protocolo="2608310002")
    central(monkeypatch, {"9900001": pedido(status="Pago")})
    tela = s["c"].get("/protesto/a-protestar").get_data(as_text=True)
    html = s["c"].post("/protesto/a-protestar/lavrar",
                       data={"csrf_token": _token(tela),
                             "titulo_id": [str(tid), str(banco_tid)],
                             f"motivo_atraso_{tid}": MOTIVO,
                             f"motivo_atraso_{banco_tid}": MOTIVO},
                       follow_redirects=True).get_data(as_text=True)
    assert "abra a ficha" in html
    assert _protestos(s, tid) == []
    # O de banco, na mesma leva, sai como sempre — um não derruba o outro.
    assert len(_protestos(s, banco_tid)) == 1
