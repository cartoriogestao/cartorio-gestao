"""As telas dos pedidos da CRA — o clique do dia traz DP, CP e AC (29/10/2026).

Buraco de tela não aparece em teste de domínio. Estes conferem o caminho do
balcão: o MESMO botão da remessa traz as três consultas depois dela, pela
MESMA porta (`cra21_web._trazer`); o resultado aparece na mesma tela, com a
linha que conta as consultas desde 14/10; a pendência aparece na ficha do
título e na lista, e sai dela com o motivo registrado.

A REDE É SIMULADA em todos — nenhuma chamada sai para a CRA. Dados fictícios.
"""
from __future__ import annotations

import json
import sqlite3

from test_protesto_aviso_web import _con, _token, s  # noqa: F401
from test_protesto_cra_pedidos import (NADA_CP, NADA_DP, SV, CPF, CNPJ,
                                       xml_de_atributos)


def _titulo(s, *, protocolo: str, numero: str, situacao: str) -> int:
    import protesto as PT
    from database import Database
    db = Database(s["banco"])
    agora = db.now()
    with db.transaction() as con:
        con.row_factory = sqlite3.Row
        tid = PT.cadastrar_titulo(con, {
            "apresentante_codigo": "001",
            "apresentante_nome": "BANCO DE EXEMPLO SA", "especie": "DMI",
            "numero_titulo": numero, "nosso_numero": f"N{numero}",
            "data_emissao": "2026-09-01", "data_vencimento": "2026-10-01",
            "valor": "221.00", "saldo": "221.00",
            "praca_protesto": "CIDADE EXEMPLO",
            "cedente": {"nome": "LOJA DE EXEMPLO", "documento": CNPJ},
            "devedores": [{"nome": "EMPRESA DE EXEMPLO LTDA", "CPF": CPF,
                           "enderecos": [{"endereco": "RUA DE EXEMPLO, 10",
                                          "cidade": "Cidade Exemplo",
                                          "uf": "MA"}]}],
        }, origem="CRA", origem_chave=f"lote:{protocolo}", agora=agora)
        PT.lancar_apontamento(con, tid, sv=SV, agora=agora, data_extenso="x")
        con.execute("UPDATE pt_titulos SET protocolo=?, situacao=? WHERE id=?",
                    (protocolo, situacao, tid))
    return tid


def _a_cra(monkeypatch, respostas: dict) -> list:
    """Simula a CRA na porta comum. `pendentes` levanta a recusa de sempre."""
    import cra21_api as API
    import cra21_web as CRAW
    chamadas: list = []

    def trazer(qual, nome, amb, com_imagem=False):
        chamadas.append((qual, nome))
        r = respostas.get(qual, API.CraRecusou(
            "A CRA informou: não existe remessa (código 0003)"))
        if isinstance(r, BaseException):
            raise r
        return r
    monkeypatch.setattr(CRAW, "_trazer", trazer)
    return chamadas


def _clicar(s):
    tela = s["c"].get("/protesto/remessas").get_data(as_text=True)
    return s["c"].post("/protesto/remessas/da-cra",
                       data={"csrf_token": _token(tela), "o_que": "pendentes"},
                       follow_redirects=True)


def test_o_clique_da_remessa_traz_dp_cp_e_ac_depois_dela(s, monkeypatch):
    chamadas = _a_cra(monkeypatch, {"desistencias": NADA_DP,
                                    "cancelamentos": NADA_CP,
                                    "autorizacoes": NADA_CP})
    r = _clicar(s)
    assert r.status_code == 200
    assert [q for q, _ in chamadas] == ["pendentes", "desistencias",
                                        "cancelamentos", "autorizacoes"]
    assert [n[:5] for _, n in chamadas[1:]] == ["DP000", "CP000", "AC000"]
    html = r.get_data(as_text=True)
    # A remessa que não veio não impediu as três, e as três aparecem na tela.
    assert "0003" in html
    assert "Desistências (DP): nada veio" in html
    assert "data-cra-pedidos-do-dia" in html
    with _con(s) as con:
        assert con.execute(
            "SELECT COUNT(*) FROM pt_cra_consultas").fetchone()[0] == 3
        # A AUDITORIA QUE O ROTEIRO LÊ: `cra_baixar` com o `o_que` de cada
        # uma — inclusive quando nada veio.
        o_que = [json.loads(x[0])["o_que"] for x in con.execute(
            "SELECT details FROM audit_logs WHERE action='cra_baixar' "
            "ORDER BY id").fetchall()]
    assert o_que == ["desistencias", "cancelamentos", "autorizacoes"]


def test_a_falha_aparece_em_vermelho_e_nao_derruba_as_outras(s, monkeypatch):
    import cra21_api as API
    _a_cra(monkeypatch, {"desistencias": API.CraRecusou("SOAP fault"),
                         "cancelamentos": NADA_CP, "autorizacoes": NADA_CP})
    html = _clicar(s).get_data(as_text=True)
    assert 'class="flash danger"' in html
    assert "Desistências (DP) — falhou" in html
    assert "Cancelamentos (CP): nada veio" in html
    with _con(s) as con:
        assert con.execute("SELECT COUNT(*) FROM audit_logs "
                           "WHERE action='cra_baixar_falha'").fetchone()[0] == 1


def test_a_tela_da_remessa_diz_quantas_consultas_desde_14_10(s):
    html = s["c"].get("/protesto/remessas").get_data(as_text=True)
    assert "data-contagem-desde-a-virada" in html
    assert "Desde 14/10/2026" in html


def test_o_protestado_desistido_vem_grave_na_tela_e_na_ficha(s, monkeypatch):
    tid = _titulo(s, protocolo="2610200002", numero="NF-1002/1",
                  situacao="PROTESTADO")
    dp = xml_de_atributos("sustacao", "DP0012910.261", [
        ("2610200002", "NF-1002/1", "EMPRESA DE EXEMPLO LTDA", 22100)])
    _a_cra(monkeypatch, {"desistencias": dp, "cancelamentos": NADA_CP,
                         "autorizacoes": NADA_CP})
    html = _clicar(s).get_data(as_text=True)
    assert "JÁ PROTESTADO" in html
    lista = s["c"].get("/protesto/cra/pedidos").get_data(as_text=True)
    assert "data-grave" in lista and "GRAVE" in lista
    ficha = s["c"].get(f"/protesto/{tid}").get_data(as_text=True)
    assert "data-pedidos-cra" in ficha
    assert "PROTESTADO" in ficha


def test_o_cancelamento_vira_pendencia_e_sai_com_o_motivo(s, monkeypatch):
    tid = _titulo(s, protocolo="2610200020", numero="C-1",
                  situacao="PROTESTADO")
    cp = xml_de_atributos("sustacao", "CP0012910.261", [
        ("2610200020", "C-1", "EMPRESA DE EXEMPLO LTDA", 5000)])
    _a_cra(monkeypatch, {"desistencias": NADA_DP, "cancelamentos": cp,
                         "autorizacoes": NADA_CP})
    _clicar(s)
    with _con(s) as con:
        pid = con.execute("SELECT id FROM pt_cra_pedidos").fetchone()[0]
        assert con.execute("SELECT COUNT(*) FROM pt_atos WHERE tipo="
                           "'CANCELAMENTO'").fetchone()[0] == 0
    ficha = s["c"].get(f"/protesto/{tid}").get_data(as_text=True)
    assert f"/protesto/cra/pedidos/{pid}/tratar" in ficha
    r = s["c"].post(f"/protesto/cra/pedidos/{pid}/tratar",
                    data={"csrf_token": _token(ficha), "voltar": "ficha",
                          "motivo": "O devedor desistiu de cancelar agora"},
                    follow_redirects=True)
    assert r.status_code == 200 and "Registrado" in r.get_data(as_text=True)
    with _con(s) as con:
        linha = con.execute("SELECT estado, motivo FROM pt_cra_pedidos "
                            "WHERE id=?", (pid,)).fetchone()
        assert linha[0] == "TRATADO"
        assert con.execute("SELECT COUNT(*) FROM audit_logs WHERE action="
                           "'PROTESTO_CRA_PEDIDO_TRATADO'").fetchone()[0] == 1
    lista = s["c"].get("/protesto/cra/pedidos").get_data(as_text=True)
    assert "Nada do que veio da CRA espera a casa agora" in lista


def test_a_resposta_guardada_se_baixa_como_chegou(s, monkeypatch):
    _a_cra(monkeypatch, {"desistencias": NADA_DP, "cancelamentos": NADA_CP,
                         "autorizacoes": NADA_CP})
    _clicar(s)
    with _con(s) as con:
        cid = con.execute("SELECT MIN(id) FROM pt_cra_consultas").fetchone()[0]
    r = s["c"].get(f"/protesto/cra/consultas/{cid}/arquivo")
    assert r.status_code == 200
    assert "attachment" in r.headers["Content-Disposition"]
    assert "0006" in r.get_data(as_text=True)
    assert s["c"].get("/protesto/cra/consultas/999999/arquivo").status_code == 404


def test_a_lista_dos_pedidos_esta_no_menu_e_abre_vazia(s):
    html = s["c"].get("/protesto").get_data(as_text=True)
    assert "/protesto/cra/pedidos" in html
    lista = s["c"].get("/protesto/cra/pedidos")
    assert lista.status_code == 200
    assert "Nada do que veio da CRA espera a casa agora" in lista.get_data(
        as_text=True)
