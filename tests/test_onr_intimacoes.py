"""A leitura da e-Intimação do ONR e a ligação com os avisos da A005.

Sem rede: a sessão do WSOfício é trocada por uma de mentira, que só responde as
duas leituras (`ListStatusIN` e `ListPedidosIN`). Dados inventados.
"""
from __future__ import annotations

import re
import sys
from datetime import date, datetime
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import onr_intimacoes as IN                                         # noqa: E402
import onr_pedidos_avisos as AV                                     # noqa: E402
import onr_wsoficio as WS                                           # noqa: E402
from bd_nativo import banco                                         # noqa: E402

SENHA = "Senha#12345"
HOJE = date(2026, 11, 27)                      # sexta-feira
AGORA = datetime(2026, 11, 27, 10, 0)
STATUS = [{"IDStatus": 1, "NomeStatus": "Em aberto"},
          {"IDStatus": 2, "NomeStatus": "Aguardando pagamento do devedor"},
          {"IDStatus": 3, "NomeStatus": "Intimado"},
          {"IDStatus": 4, "NomeStatus": "Reaberto"}]


class SessaoDeMentira:
    """Responde só as leituras; qualquer outra chamada derruba o teste."""

    def __init__(self, pedidos, *, falha=None):
        self.pedidos, self.falha, self.chamadas = pedidos, falha, []

    def status_da_intimacao(self):
        self.chamadas.append("ListStatusIN")
        if self.falha:
            raise WS.WSOficioError(self.falha)
        return STATUS

    def pedidos_da_intimacao(self, **kw):
        self.chamadas.append("ListPedidosIN")
        return {"qtde_registros": len(self.pedidos), "qtde_paginas": 1, "pedidos": self.pedidos}

    def __getattr__(self, nome):
        pytest.fail(f"a leitura chamou {nome}, que não é leitura da lista")


def _pedido(ident, status, *, data_status="2026-11-25T09:00:00", protocolo=None):
    return {"IDPedido": ident, "Protocolo": protocolo or f"IN-TESTE-{ident}",
            "Solicitante": "BANCO DE EXEMPLO", "IDStatus": status,
            "DataPedido": "2026-11-20T08:00:00", "DataStatus": data_status}


def _ler(db, sessao, quando=AGORA):
    return IN.ler(db, WS.PRODUCAO, hoje=quando.date(), agora=lambda: quando.isoformat(),
                  sessao=sessao)


def _abertos(db):
    with db.connect() as con:
        return {(r["fonte"], r["protocolo"]): dict(r) for r in banco(con).ler(
            "SELECT * FROM onr_pedidos_avisos WHERE encerrado_em IS NULL")}


def _verificar(db, quando=AGORA):
    return AV.verificar_os_pedidos(db, agora=quando, tem_credencial_saec=lambda: False)


# ------------------------------------------------------------------ só calcula


def test_a_sugestao_pelo_nome_pega_so_a_vez_da_casa():
    status = [{"id_status": s["IDStatus"], "nome": s["NomeStatus"]} for s in STATUS]
    assert IN.sugerir_parados(status) == {1, 4}


def test_a_regra_recusa_status_que_o_onr_nao_tem():
    status = [{"id_status": 1, "nome": "Em aberto"}]
    assert IN.guardar_regra(["1"], status) == "1"
    with pytest.raises(IN.IntimacaoOnrError):
        IN.guardar_regra(["9"], status)
    with pytest.raises(IN.IntimacaoOnrError):
        IN.guardar_regra([], status)


# ------------------------------------------------------------------ a leitura


def test_a_leitura_grava_a_tabela_de_status_e_os_pedidos_e_so_le(cg_casa):
    db = cg_casa["db"]
    s = SessaoDeMentira([_pedido(11, 1), _pedido(12, 3)])
    r = _ler(db, s)
    assert r["situacao"] == "OK" and r["listados"] == 2 and r["novos"] == 2
    assert s.chamadas == ["ListStatusIN", "ListPedidosIN"]
    with db.connect() as con:
        assert len(IN.status_lidos(con, WS.PRODUCAO)) == 4
        p = banco(con).um("SELECT * FROM onr_in_pedidos WHERE id_pedido=11")
    assert p["data_status"] == "2026-11-25T09:00:00" and p["id_status"] == 1
    # O status mudou no ONR: a segunda leitura conta.
    r = _ler(db, SessaoDeMentira([_pedido(11, 3), _pedido(12, 3)]))
    assert r["novos"] == 0 and r["mudaram"] == 1


def test_o_onr_fora_do_ar_grava_a_leitura_com_erro(cg_casa):
    db = cg_casa["db"]
    r = _ler(db, SessaoDeMentira([], falha="o ONR não respondeu"))
    assert r["situacao"] == "ERRO" and "não respondeu" in r["erro"]
    with db.connect() as con:
        assert IN.ultima_leitura(con, WS.PRODUCAO) is None
        assert IN.ultima_leitura(con, WS.PRODUCAO, boa=False)["situacao"] == "ERRO"


def test_parados_pela_sugestao_e_pela_configuracao(cg_casa):
    db = cg_casa["db"]
    with db.connect() as con:
        assert IN.parados(con, WS.PRODUCAO, db.get_setting, agora=AGORA) is None   # nada lido
    _ler(db, SessaoDeMentira([_pedido(21, 1), _pedido(22, 2), _pedido(23, 3), _pedido(24, 4)]))
    with db.connect() as con:
        lista = IN.parados(con, WS.PRODUCAO, db.get_setting, agora=AGORA)
    assert sorted(p["id_pedido"] for p in lista) == [21, 24]
    db.set_settings({IN.CHAVE_STATUS_PARADOS: "2"})
    with db.connect() as con:
        lista = IN.parados(con, WS.PRODUCAO, db.get_setting, agora=AGORA)
        regra = IN.regra_dos_parados(con, WS.PRODUCAO, db.get_setting)
    assert [p["id_pedido"] for p in lista] == [22] and regra["de_onde"] == "CONFIGURADO"


# ------------------------------------------------------------------ a ligação com a A005


def test_a_intimacao_parada_vira_faixa_e_some_quando_anda(cg_casa):
    db = cg_casa["db"]
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    esc = db.create_user("escrevente1", "ESCREVENTE EXEMPLO", SENHA, "USER")
    db.set_settings({AV.CHAVE_RESPONSAVEL: str(esc)})
    _ler(db, SessaoDeMentira([_pedido(31, 1, data_status="2026-11-25T09:00:00"),
                              _pedido(32, 1, data_status="2026-11-27T08:00:00"),
                              _pedido(33, 3)]))
    r = _verificar(db)
    assert "INTIMACAO" not in r["nao_medidas"]
    av = _abertos(db)
    assert av[("INTIMACAO", "IN-TESTE-31")]["nivel"] == AV.FAIXA        # 25/11 → 27/11: 2 dias úteis
    assert av[("INTIMACAO", "IN-TESTE-32")]["nivel"] == AV.SIMPLES      # chegou hoje
    assert ("INTIMACAO", "IN-TESTE-33") not in av                       # intimado: andou
    assert av[("INTIMACAO", "IN-TESTE-31")]["endpoint"] == "onr_intimacao_ficha"
    assert av[("INTIMACAO", "IN-TESTE-31")]["user_id"] == esc
    # O pedido andou no ONR: na verificação seguinte, o aviso some.
    _ler(db, SessaoDeMentira([_pedido(31, 3), _pedido(32, 1, data_status="2026-11-27T08:00:00")]))
    _verificar(db)
    assert set(k for k in _abertos(db) if k[0] == "INTIMACAO") == {("INTIMACAO", "IN-TESTE-32")}


def test_leitura_velha_nao_mede_e_nao_encerra_aviso(cg_casa):
    db = cg_casa["db"]
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    _ler(db, SessaoDeMentira([_pedido(41, 1)]))
    _verificar(db)
    assert ("INTIMACAO", "IN-TESTE-41") in _abertos(db)
    # Dois dias sem leitura boa: a e-Intimação fica «não medida», e o aviso não some.
    r = _verificar(db, datetime(2026, 11, 30, 10, 0))
    assert "INTIMACAO" in r["nao_medidas"]
    assert ("INTIMACAO", "IN-TESTE-41") in _abertos(db)


# ------------------------------------------------------------------ o processo e as telas


def test_o_processo_nasce_desligado_e_so_le():
    import automacao as AUTO
    import automacao_processos as PROC
    (cat,) = IN.CATALOGO
    ag = AUTO.normalizar_agenda(cat["agenda"])
    assert ag["dias"] == [0, 1, 2, 3, 4] and ag["intervalo_min"] == 60
    assert not AUTO._slots_do_dia(ag, date(2026, 11, 29))              # domingo
    assert "ativo" not in cat and "pode_agir" not in cat
    sementes = {s["codigo"]: s for s in PROC.sementes_de_outros_modulos()}
    assert sementes[IN.CODIGO_DO_PROCESSO]["alvo"] == "onr_intimacoes:rodada_das_intimacoes"
    # Só leituras do WSOfício: nenhuma escrita presa aparece neste módulo.
    codigo = (RAIZ / "onr_intimacoes.py").read_text(encoding="utf-8")
    for metodo in WS.ESPERAM_O_PODE_DO_TITULAR:
        assert metodo not in codigo, metodo


def _entrar(c, login):
    from conftest import cg_login
    cg_login(c, login, SENHA)


def test_as_telas_mostram_os_pedidos_e_o_admin_marca_os_status(cg_casa):
    db, c = cg_casa["db"], cg_casa["c"]
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    _ler(db, SessaoDeMentira([_pedido(51, 1), _pedido(52, 3)]))
    _entrar(c, "mario")
    html = c.get("/ri/onr/intimacoes").get_data(as_text=True)
    assert "IN-TESTE-51" in html and "Sugestão pelo nome do status" in html
    assert "a vez é da casa" in html
    with db.connect() as con:
        pid = banco(con).valor("SELECT id FROM onr_in_pedidos WHERE id_pedido=51")
    ficha = c.get(f"/ri/onr/intimacoes/{pid}").get_data(as_text=True)
    assert "IN-TESTE-51" in ficha and "nada é respondido" in ficha
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
    r = c.post("/ri/onr/intimacoes/regra", data={"csrf_token": csrf, "status": ["3"]})
    assert r.status_code == 302 and db.get_setting(IN.CHAVE_STATUS_PARADOS, "") == "3"
    r = c.post("/ri/onr/intimacoes/regra", data={"csrf_token": csrf, "status": ["77"]})
    assert db.get_setting(IN.CHAVE_STATUS_PARADOS, "") == "3"           # recusado
    r = c.post("/ri/onr/intimacoes/regra", data={"csrf_token": csrf, "acao": "sugestao"})
    assert db.get_setting(IN.CHAVE_STATUS_PARADOS, "") == ""


def test_o_escrevente_ve_mas_nao_muda_a_regra(cg_casa):
    db, c = cg_casa["db"], cg_casa["c"]
    db.create_user("escrevente1", "ESCREVENTE EXEMPLO", SENHA, "USER")
    _ler(db, SessaoDeMentira([_pedido(61, 1)]))
    _entrar(c, "escrevente1")
    html = c.get("/ri/onr/intimacoes").get_data(as_text=True)
    assert "IN-TESTE-61" in html and "Gravar os status parados" not in html
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
    r = c.post("/ri/onr/intimacoes/regra", data={"csrf_token": csrf, "status": ["1"]})
    assert r.status_code in (302, 403) and db.get_setting(IN.CHAVE_STATUS_PARADOS, "") == ""
