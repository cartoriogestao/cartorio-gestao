"""Os pedidos do ONR parados avisam a escrevente, e não a Checklist do dia (A005).

Dados inventados: protocolos «S-TESTE-…», «EP-…», pessoas «ESCREVENTE EXEMPLO».
"""
from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import onr_pedidos_avisos as AV                                     # noqa: E402
from bd_nativo import banco                                         # noqa: E402

TERCA = datetime(2026, 11, 24, 10, 0)          # 24/11/2026, terça-feira
SENHA = "Senha#12345"


# ------------------------------------------------------------------ a escala (só calcula)

def test_primeiro_dia_e_aviso_simples_e_o_segundo_dia_util_e_faixa():
    assert AV.escala(date(2026, 11, 24), date(2026, 11, 24))["nivel"] == AV.SIMPLES
    e = AV.escala(date(2026, 11, 23), date(2026, 11, 24))
    assert e["nivel"] == AV.FAIXA and e["dias_uteis"] == 1


def test_fim_de_semana_nao_conta_e_o_pedido_do_sabado_comeca_na_segunda():
    # Chegou no sábado: segunda é o 1º dia útil (simples), terça o 2º (faixa).
    sabado = date(2026, 11, 21)
    assert AV.escala(sabado, date(2026, 11, 22))["nivel"] == AV.SIMPLES     # domingo
    e = AV.escala(sabado, date(2026, 11, 23))
    assert e["nivel"] == AV.SIMPLES and e["primeiro_dia"] == date(2026, 11, 23)
    assert AV.escala(sabado, date(2026, 11, 24))["nivel"] == AV.FAIXA
    # Chegou na sexta: sábado e domingo continuam no 1º dia.
    sexta = date(2026, 11, 27)
    assert AV.escala(sexta, date(2026, 11, 29))["nivel"] == AV.SIMPLES
    assert AV.escala(sexta, date(2026, 11, 30))["nivel"] == AV.FAIXA


def test_feriado_nacional_e_local_nao_contam():
    # 20/11 (sexta) é feriado nacional: o pedido de quinta só vira faixa na segunda.
    quinta = date(2026, 11, 19)
    assert AV.escala(quinta, date(2026, 11, 20))["nivel"] == AV.SIMPLES
    assert AV.escala(quinta, date(2026, 11, 22))["nivel"] == AV.SIMPLES
    assert AV.escala(quinta, date(2026, 11, 23))["nivel"] == AV.FAIXA
    # Feriado local de Configurações (o calendário da casa).
    local = AV.feriados_da_casa(lambda chave, padrao="": "2026-11-25  # feriado de exemplo")
    assert AV.escala(date(2026, 11, 24), date(2026, 11, 25), local)["nivel"] == AV.SIMPLES
    assert AV.escala(date(2026, 11, 24), date(2026, 11, 26), local)["nivel"] == AV.FAIXA


# ------------------------------------------------------------------ os dados inventados

def _certidao(db, protocolo, *, data_pedido, situacao="NOVO", status="Em aberto",
              ambiente="PRODUCAO", matricula="1234"):
    with db.transaction() as con:
        return banco(con).escrever(
            """INSERT INTO onr_cert_pedidos (ambiente, protocolo, tipo_certidao, data_pedido,
                   status_onr, matricula_numero, dados_json, xml_pedido, situacao,
                   recebido_em, atualizado_em)
               VALUES (%s,%s,'3',%s,%s,%s,'{}','<PEDIDO_CERTIDAO/>',%s,%s,%s) RETURNING id""",
            (ambiente, protocolo, data_pedido, status, matricula, situacao,
             data_pedido, data_pedido))[0]["id"]


def _preparo(db, pedido_id, etapa):
    with db.transaction() as con:
        banco(con).escrever(
            "INSERT INTO onr_cert_auto (pedido_id, etapa, criado_em, atualizado_em) "
            "VALUES (%s,%s,'2026-11-23T08:00:00','2026-11-23T08:00:00')", (pedido_id, etapa))


def _titulo(db, contrato, *, remessa, situacao="A_PRENOTAR", status=1):
    with db.transaction() as con:
        return banco(con).escrever(
            """INSERT INTO onr_ep_pedidos (ambiente, id_contrato, protocolo, id_status, data_remessa,
                   situacao, xml_lista, recebido_em, atualizado_em)
               VALUES ('PRODUCAO',%s,%s,%s,%s,%s,'<x/>',%s,%s) RETURNING id""",
            (contrato, f"EP-{contrato}", status, remessa, situacao,
             remessa + "T08:00:00", remessa + "T08:00:00"))[0]["id"]


def _mudar(db, sql, args):
    with db.transaction() as con:
        banco(con).escrever(sql, args)


def _verificar(db, agora=TERCA, **kw):
    kw.setdefault("tem_credencial_saec", lambda: False)
    return AV.verificar_os_pedidos(db, agora=agora, **kw)


def _abertos(db):
    with db.connect() as con:
        return {(r["fonte"], r["protocolo"]): dict(r) for r in banco(con).ler(
            "SELECT * FROM onr_pedidos_avisos WHERE encerrado_em IS NULL")}


def _pessoas(db):
    admin = db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    escrevente = db.create_user("escrevente1", "ESCREVENTE EXEMPLO", SENHA, "USER")
    return admin, escrevente


# ------------------------------------------------------------------ a verificação

def test_primeiro_dia_simples_segundo_dia_faixa_e_andamento_some(cg_casa):
    db = cg_casa["db"]
    admin, escrevente = _pessoas(db)
    db.set_settings({AV.CHAVE_RESPONSAVEL: str(escrevente)})
    hoje = _certidao(db, "S-TESTE-1", data_pedido="2026-11-24T09:00:00")
    ontem = _certidao(db, "S-TESTE-2", data_pedido="2026-11-23T09:00:00")
    t = _titulo(db, 501, remessa="2026-11-23")

    r = _verificar(db)
    av = _abertos(db)
    assert av[("CERTIDAO", "S-TESTE-1")]["nivel"] == AV.SIMPLES
    assert av[("CERTIDAO", "S-TESTE-2")]["nivel"] == AV.FAIXA
    assert av[("EPROTOCOLO", "EP-501")]["nivel"] == AV.FAIXA
    assert {a["user_id"] for a in av.values()} == {escrevente}
    assert av[("CERTIDAO", "S-TESTE-2")]["desde"] == "2026-11-23"
    assert r["novos"] == 3 and r["faixas"] == 2 and r["responsavel"]["de_onde"] == "CONFIGURADO"
    assert "SAEC" in r["nao_medidas"] and "INTIMACAO" in r["nao_medidas"]

    # No dia seguinte, o do 1º dia vira faixa.
    _verificar(db, agora=datetime(2026, 11, 25, 9, 0))
    assert _abertos(db)[("CERTIDAO", "S-TESTE-1")]["nivel"] == AV.FAIXA

    # Andamento: anexo guardado (PRONTO), título prenotado no ONR. Os dois somem.
    _mudar(db, "UPDATE onr_cert_pedidos SET situacao='PRONTO' WHERE id=%s", (ontem,))
    _mudar(db, "UPDATE onr_ep_pedidos SET situacao='EM_ANDAMENTO', id_status=3 WHERE id=%s", (t,))
    r = _verificar(db, agora=datetime(2026, 11, 25, 9, 30))
    assert set(_abertos(db)) == {("CERTIDAO", "S-TESTE-1")}
    assert r["encerrados"] == 2
    with db.connect() as con:
        motivo = banco(con).valor("SELECT motivo_encerramento FROM onr_pedidos_avisos "
                                  "WHERE protocolo='S-TESTE-2'")
    assert motivo == AV.MOTIVO_ANDOU
    assert hoje


def test_etapas_do_robo_e_quem_espera_o_cliente(cg_casa):
    db = cg_casa["db"]
    _pessoas(db)
    a = _certidao(db, "S-TESTE-CUSTAS", data_pedido="2026-11-23T09:00:00",
                  status="Informar valor dos emolumentos")
    _preparo(db, a, "CUSTAS_A_APROVAR")
    b = _certidao(db, "S-TESTE-PAGTO", data_pedido="2026-11-23T09:00:00",
                  status="Aguardando pagamento")
    _preparo(db, b, "AGUARDANDO_PAGAMENTO")
    c = _certidao(db, "S-TESTE-EMITIDA", data_pedido="2026-11-23T09:00:00")
    _preparo(db, c, "A_ASSINAR")
    d = _certidao(db, "S-TESTE-REVISAR", data_pedido="2026-11-23T09:00:00")
    _preparo(db, d, "A_REVISAR")
    _certidao(db, "S-TESTE-HOMOLOG", data_pedido="2026-11-23T09:00:00", ambiente="HOMOLOGACAO")
    _titulo(db, 777, remessa="2026-11-23", status=100)          # prazo suspenso: de fora
    _verificar(db)
    av = _abertos(db)
    assert set(av) == {("CERTIDAO", "S-TESTE-CUSTAS"), ("CERTIDAO", "S-TESTE-REVISAR")}
    assert av[("CERTIDAO", "S-TESTE-CUSTAS")]["endpoint"] == "onr_auto_pedido"
    assert "custas a aprovar" in av[("CERTIDAO", "S-TESTE-CUSTAS")]["descricao"]


def test_responsavel_vazio_vai_ao_admin_e_inativo_tambem(cg_casa):
    db = cg_casa["db"]
    admin, escrevente = _pessoas(db)
    _certidao(db, "S-TESTE-9", data_pedido="2026-11-24T09:00:00")
    r = _verificar(db)
    assert r["responsavel"] == {"user_id": admin, "nome": "MARIO EXEMPLO DOS SANTOS",
                                "de_onde": "ADMIN", "motivo": "a configuração está vazia"}
    assert _abertos(db)[("CERTIDAO", "S-TESTE-9")]["user_id"] == admin
    assert "o ADMIN (a configuração está vazia)" in AV.relato(r)
    # Configurada e depois desativada: volta ao ADMIN, e o relato diz por quê.
    db.set_settings({AV.CHAVE_RESPONSAVEL: str(escrevente)})
    _mudar(db, "UPDATE users SET active=0 WHERE id=%s", (escrevente,))
    r = _verificar(db)
    assert r["responsavel"]["de_onde"] == "ADMIN" and "não está ativo" in r["responsavel"]["motivo"]


def test_fonte_que_nao_se_mediu_nao_encerra_aviso(cg_casa):
    db = cg_casa["db"]
    _pessoas(db)
    saec = {"dados": [
        {"id": 41, "protocolo": "AT-41", "status": 1, "tipoAtendimento": 1,
         "dataCadastro": "2026-11-23 10:00:00", "usuarioNome": "PESSOA DE FORA"},
        {"id": 42, "protocolo": "AT-42", "status": 4, "dataCadastro": "2026-11-20 10:00:00"}],
        "totalPaginas": 1}
    chamadas = []

    def buscar(**kw):
        chamadas.append(kw)
        return saec if kw["status"] == 1 else {"dados": []}

    _verificar(db, tem_credencial_saec=lambda: True, buscar_saec=buscar)
    av = _abertos(db)
    assert set(av) == {("SAEC", "AT-41")} and av[("SAEC", "AT-41")]["nivel"] == AV.FAIXA
    assert "PESSOA" not in av[("SAEC", "AT-41")]["descricao"]          # sem nome de quem pediu
    assert {c["status"] for c in chamadas} == {1, 5, 11}

    # O ONR caiu: o SAEC não se mediu, e o aviso dele fica.
    def caiu(**kw):
        raise RuntimeError("o ONR não respondeu")
    r = _verificar(db, tem_credencial_saec=lambda: True, buscar_saec=caiu)
    assert "SAEC" in r["nao_medidas"] and ("SAEC", "AT-41") in _abertos(db)
    # Mediu de novo e o atendimento foi respondido: some.
    _verificar(db, tem_credencial_saec=lambda: True, buscar_saec=lambda **kw: {"dados": []})
    assert not _abertos(db)


# ------------------------------------------------------------------ o processo

def test_o_processo_nasce_desligado_a_cada_30_min_e_nao_cobra_o_admin(cg_casa, monkeypatch):
    import automacao as AUTO
    import automacao_processos as PROC
    (cat,) = AV.CATALOGO
    ag = AUTO.normalizar_agenda(cat["agenda"])
    assert ag["dias"] == [0, 1, 2, 3, 4] and ag["intervalo_min"] == 30
    assert not AUTO._slots_do_dia(ag, date(2026, 11, 22))                  # domingo
    assert "ativo" not in cat and "pode_agir" not in cat
    sementes = {s["codigo"]: s for s in PROC.sementes_de_outros_modulos()}
    assert sementes[AV.CODIGO_DO_PROCESSO]["alvo"] == "onr_pedidos_avisos:rodada_dos_avisos"

    db = cg_casa["db"]
    _pessoas(db)
    _certidao(db, "S-TESTE-5", data_pedido="2026-11-23T09:00:00")
    import onr_api as API
    monkeypatch.setattr(API, "tem_credencial", lambda *a, **k: False)

    class Ctx:
        pasta_dados = cg_casa["dados"]
        agora = TERCA
    Ctx.db = db
    r = AV.rodada_dos_avisos(Ctx())
    # Pedido parado é trabalho da escrevente: o processo fica OK (AVISO abriria
    # tarefa para o responsável do processo, o admin).
    assert r["situacao"] == "OK"
    assert "1 pedido(s) do ONR parado(s), 1 com a faixa vermelha" in r["relato"]
    assert "S-TESTE" not in r["relato"]


# ------------------------------------------------------------------ as telas

def _entrar(c, login):
    from conftest import cg_login
    cg_login(c, login, SENHA)


def test_a_faixa_na_tela_dela_o_simples_e_o_admin_nao_ve(cg_casa):
    db, c = cg_casa["db"], cg_casa["c"]
    admin, escrevente = _pessoas(db)
    db.set_settings({AV.CHAVE_RESPONSAVEL: str(escrevente)})
    velho = _certidao(db, "S-TESTE-VELHO", data_pedido="2026-11-23T09:00:00")
    _certidao(db, "S-TESTE-NOVO", data_pedido="2026-11-24T09:00:00")
    _verificar(db)
    _entrar(c, "escrevente1")
    html = c.get("/").get_data(as_text=True)
    assert 'data-onr-pedidos-aviso="faixa"' in html and "S-TESTE-VELHO" in html
    assert "parado desde 23/11/2026" in html
    assert f"/ri/onr/certidoes/{velho}" in html                         # um clique até o pedido
    assert 'data-onr-pedidos-aviso="simples"' in html and "S-TESTE-NOVO" in html
    # Em outra tela qualquer a faixa continua.
    assert 'data-onr-pedidos-aviso="faixa"' in c.get("/ri/onr/pedidos-parados").get_data(as_text=True)

    # O andamento faz a faixa sumir na verificação seguinte.
    _mudar(db, "UPDATE onr_cert_pedidos SET situacao='ENVIADO'", ())
    _verificar(db)
    assert "data-onr-pedidos-aviso" not in c.get("/").get_data(as_text=True)

    # O ADMIN não é quem recebe: não vê faixa.
    _certidao(db, "S-TESTE-OUTRO", data_pedido="2026-11-23T09:00:00")
    _verificar(db)
    c2 = cg_casa["app"].test_client()
    _entrar(c2, "mario")
    assert "data-onr-pedidos-aviso" not in c2.get("/").get_data(as_text=True)


def test_o_item_saiu_da_checklist_e_a_medicao_fica_na_tela_dos_avisos(cg_casa):
    import gestor_checklist as GCK
    db, c = cg_casa["db"], cg_casa["c"]
    admin, escrevente = _pessoas(db)
    # O aviso é dela: na tela do admin não há faixa, e a checklist não lista o pedido.
    db.set_settings({AV.CHAVE_RESPONSAVEL: str(escrevente)})
    _certidao(db, "S-TESTE-CHK", data_pedido="2026-11-23T09:00:00")
    _titulo(db, 902, remessa="2026-11-23")
    _verificar(db)
    m = GCK.montar(db, date(2026, 11, 24), papel="ADMIN")
    texto = repr({k: m[k] for k in ("achados", "fora", "itens")})
    assert "S-TESTE-CHK" not in texto and "EP-902" not in texto
    assert not any("ONR_PEDIDO" in str(a["regra"]) for lista in m["achados"].values()
                   for a in lista)
    _entrar(c, "mario")
    assert "S-TESTE-CHK" not in c.get("/administrativo/gestor/checklist").get_data(as_text=True)
    # A medição continua à vista do admin e do gestor, na tela dos avisos.
    tela = c.get("/ri/onr/pedidos-parados").get_data(as_text=True)
    assert "S-TESTE-CHK" in tela and "EP-902" in tela and "faixa vermelha" in tela


def test_a_configuracao_grava_e_passa_os_avisos_abertos(cg_casa):
    import re
    db, c = cg_casa["db"], cg_casa["c"]
    admin, escrevente = _pessoas(db)
    _certidao(db, "S-TESTE-CFG", data_pedido="2026-11-24T09:00:00")
    _verificar(db)
    assert _abertos(db)[("CERTIDAO", "S-TESTE-CFG")]["user_id"] == admin
    _entrar(c, "mario")
    html = c.get("/configuracoes").get_data(as_text=True)
    assert 'id="cfg-onr-pedidos"' in html and "ESCREVENTE EXEMPLO" in html
    csrf = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
    r = c.post("/configuracoes/onr-pedidos-responsavel",
               data={"csrf_token": csrf, "user_id": str(escrevente)})
    assert r.status_code == 302
    assert db.get_setting(AV.CHAVE_RESPONSAVEL, "") == str(escrevente)
    assert _abertos(db)[("CERTIDAO", "S-TESTE-CFG")]["user_id"] == escrevente
    # Quem não é ADMIN não muda.
    c3 = cg_casa["app"].test_client()
    _entrar(c3, "escrevente1")
    html3 = c3.get("/ri/onr/pedidos-parados").get_data(as_text=True)
    csrf3 = re.search(r'name="csrf_token" value="([^"]+)"', html3).group(1)
    r = c3.post("/configuracoes/onr-pedidos-responsavel", data={"csrf_token": csrf3, "user_id": ""})
    assert r.status_code in (302, 403) and db.get_setting(AV.CHAVE_RESPONSAVEL, "") == str(escrevente)


@pytest.mark.parametrize("valor", ["abc", "999999"])
def test_a_configuracao_recusa_quem_nao_e_pessoa_ativa(cg_casa, valor):
    db = cg_casa["db"]
    _pessoas(db)
    with db.connect() as con, pytest.raises(AV.AvisosOnrError):
        AV.guardar_responsavel(con, valor)
