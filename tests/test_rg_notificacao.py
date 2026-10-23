"""A notificação extrajudicial do RTD — `rg_notificacao.py` (LG04).

O QUE ESTES TESTES PROTEGEM, artigo por artigo do Código de Normas do MA:

    art. 986 § 4º   diligência das 6h às 20h, nunca domingo nem feriado
    art. 987        a primeira em até 10 dias da apresentação — o atraso
                    aparece na lista
    art. 987 § 2º   negativa só com três idas frustradas em dias E turnos
                    alternados
    art. 987 § 3º   a quarta ida só a pedido, e cobrada à parte (15.8.1.1)
    art. 988 § 2º   nada de certidão antes do registro
    art. 986 § 2º   a certidão se averba à margem do registro

E O DA CASA: o selo que não sai SUSPENDE (e não some), a certidão leva número
do exercício e selo, toda escrita fica em `audit_logs`, e cada tela tem o seu
papel — anônimo vai ao login, papel errado é 403, POST sem CSRF é 400.

Dados fictícios. O selador não existe no banco de teste: o selo que sai é o
`selador_cliente.selar` trocado por um que grava no razão como o de verdade.
"""
from __future__ import annotations

import re
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import rg_notificacao as N
import rg_registro as RG
from bd_nativo import banco
from conftest import cg_login

SENHA = "Senha#12345"
SV = {"unit_name": "SERVENTIA DE EXEMPLO", "ri_cns": "000000",
      "ri_cidade": "Cidade Exemplo", "ri_uf": "MA",
      "serventia_titular": "FULANO DE EXEMPLO",
      "serventia_titulo": "Oficial de Registro"}
EXTENSO = "dezenove dias do mês de outubro de dois mil e vinte e seis"


# --------------------------------------------------------------- o preparo


def _dias_de_diligencia(quantos: int) -> list[str]:
    """Dias passados em que a norma deixa diligenciar — sem domingo e sem
    feriado nacional —, do mais antigo para o mais novo, todos antes de hoje."""
    from ri_schema import feriados_nacionais
    dias, d = [], date.today() - timedelta(days=1)
    while len(dias) < quantos:
        if d.weekday() != 6 and d not in feriados_nacionais(d.year):
            dias.append(d.isoformat())
        d -= timedelta(days=1)
    return sorted(dias)


@pytest.fixture()
def casa(cg_casa):
    db = cg_casa["db"]
    db.create_user("oficial", "FULANO DE EXEMPLO", SENHA, "ADMIN")
    db.create_user("balcao", "BELTRANO DE EXEMPLO", SENHA, "USER")
    db.create_user("auditor", "CICLANO DE EXEMPLO", SENHA, "AUDITOR")
    return cg_casa


def _logado(casa, quem: str = "oficial"):
    c = casa["app"].test_client()
    cg_login(c, quem, SENHA)
    return c


def _token(c, url: str) -> str:
    html = c.get(url).get_data(as_text=True)
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, f"{url} não trouxe csrf_token"
    return achado.group(1)


def _titulo(db, apresentado: str) -> int:
    with db.transaction() as con:
        return int(banco(con).escrever(
            """INSERT INTO rg_titulos(atribuicao, data_apresentacao, apresentante,
                   natureza, criado_em)
               VALUES (4, %s, 'EMPRESA DE EXEMPLO LTDA', 'Notificação', %s)
               RETURNING id""", (apresentado, apresentado + "T09:00:00"))[0]["id"])


def _registrar(db, titulo_id: int) -> int:
    with db.transaction() as con:
        r = RG.abrir_registro(con, serie="TD_B", sv=SV, agora=db.now(),
                              data_extenso=EXTENSO,
                              natureza="Notificação extrajudicial",
                              requerente_nome="EMPRESA DE EXEMPLO LTDA",
                              teor="Texto de exemplo da notificação.")
        banco(con).escrever("UPDATE rg_titulos SET registro_id = %s WHERE id = %s",
                            (r["registro_id"], titulo_id))
    return r["registro_id"]


def _notificacao(db, titulo_id: int, **extra) -> int:
    campos = {"destinatario_nome": "FULANO DE EXEMPLO",
              "destinatario_documento": "00000000191",
              "endereco": "Rua de Exemplo, 100, Centro"}
    campos.update(extra)
    with db.transaction() as con:
        return N.abrir(con, titulo_id=titulo_id, agora=db.now(),
                       usuario="FULANO DE EXEMPLO", **campos)


def _ida(db, nid, dia, hora, resultado="NAO_LOCALIZADO", **extra):
    with db.transaction() as con:
        return N.registrar_ida(con, nid, data=dia, hora=hora,
                               resultado=resultado, agora=db.now(),
                               usuario="FULANO DE EXEMPLO", **extra)


@pytest.fixture()
def selo_que_sai(casa, monkeypatch):
    """O selador de mentira: grava no razão como o de verdade e devolve o selo."""
    import selador
    import selador_cliente as CL
    casa["db"].set_settings({"selo_tabela_custas_em": "2026-01-01"})
    pedidos = []

    def falso_selar(con, pasta, caminho, dados, *, referencia, atribuicao,
                    agora, cns, tentativa=1, usuario=None, **_):
        numero = f"SELOEXEMPLO{len(pedidos) + 1:04d}"
        pedidos.append({"caminho": caminho, "dados": dados, "ref": referencia})
        banco(con).escrever(
            """INSERT INTO sd_selos(numero, texto, sid, caminho, atribuicao,
                   referencia, ambiente, obtido_em, obtido_por)
               VALUES (%s,%s,%s,%s,%s,%s,'HOMOLOGACAO',%s,%s)""",
            (numero, "SELO DE EXEMPLO", f"sid-{numero}", caminho, atribuicao,
             str(referencia), agora, usuario))
        return [selador.SeloGerado(numero=numero, texto="SELO DE EXEMPLO")]

    monkeypatch.setattr(CL, "selar", falso_selar)
    return pedidos


@pytest.fixture()
def protocolo_pago(casa):
    """O balcão já recebeu: protocolo pago com a diligência e a certidão.

    Desde o LX16 o selo PAGO só sai com protocolo e pagamento
    (`ato_selado.cobrir_o_selo`). Estes testes falam da notificação, e não
    do caixa: montam o que o balcão monta, pelo helper único
    `protocolo_de_teste`, em vez de desligar a trava.
    """
    from protocolo_de_teste import atender_protocolo_pago
    with casa["db"].transaction() as con:
        return atender_protocolo_pago(
            con, usuario="FULANO DE EXEMPLO",
            codigos=(N.ITEM_DILIGENCIA_URBANA, N.ITEM_CERTIDAO))


# ----------------------------------------------------- as réguas da norma


def test_domingo_nao_tem_diligencia():
    with pytest.raises(N.NotificacaoError, match="domingo"):
        N.conferir_dia_e_hora("2026-10-04", "10:00")


def test_feriado_nacional_nao_tem_diligencia():
    with pytest.raises(N.NotificacaoError, match="feriado"):
        N.conferir_dia_e_hora("2026-10-12", "10:00")


def test_feriado_local_da_configuracao_tambem_impede():
    with pytest.raises(N.NotificacaoError, match="feriado"):
        N.conferir_dia_e_hora("2026-10-13", "10:00",
                              feriados_locais={date(2026, 10, 13)})


def test_antes_das_seis_e_depois_das_vinte_horas_nao_se_diligencia():
    for hora in ("05:59", "20:01", "23:00"):
        with pytest.raises(N.NotificacaoError, match="6h às 20h"):
            N.conferir_dia_e_hora("2026-10-05", hora)


def test_sabado_e_as_vinte_horas_em_ponto_valem():
    assert N.conferir_dia_e_hora("2026-10-03", "20:00") == (
        "2026-10-03", "20:00", "NOITE")
    assert N.conferir_dia_e_hora("2026-10-05", "06:00")[2] == "MANHA"


def test_o_prazo_da_primeira_diligencia_e_de_dez_dias_corridos():
    assert N.prazo_da_primeira("2026-10-01") == "2026-10-11"


def _i(numero, dia, hora, resultado="NAO_LOCALIZADO"):
    return {"numero": numero, "data": dia, "hora": hora,
            "turno": N.turno(hora), "resultado": resultado}


def test_negativa_com_duas_diligencias_e_recusada():
    motivo = N.negativa_cabe([_i(1, "2026-10-02", "09:00"),
                              _i(2, "2026-10-03", "14:00")])
    assert "no mínimo 3" in motivo


def test_negativa_com_tres_em_dias_e_turnos_alternados_e_aceita():
    assert N.negativa_cabe([_i(1, "2026-10-02", "09:00"),
                            _i(2, "2026-10-03", "14:00"),
                            _i(3, "2026-10-05", "19:00")]) == ""


def test_tres_no_mesmo_turno_nao_alternam_o_horario():
    motivo = N.negativa_cabe([_i(1, "2026-10-02", "09:00"),
                              _i(2, "2026-10-03", "10:30"),
                              _i(3, "2026-10-05", "15:00")])
    assert "horários alternados" in motivo


def test_duas_no_mesmo_dia_nao_alternam_o_dia():
    motivo = N.negativa_cabe([_i(1, "2026-10-02", "09:00"),
                              _i(2, "2026-10-02", "19:00"),
                              _i(3, "2026-10-05", "14:00")])
    assert "mesmo dia" in motivo


def test_so_a_primeira_e_as_extras_sao_cobradas():
    assert N.item_da_ida(1, "URBANA") == ("15.8.1", N.CAMINHO_DILIGENCIA_URBANA)
    assert N.item_da_ida(1, "RURAL") == ("15.8.1.2", N.CAMINHO_DILIGENCIA_RURAL)
    assert N.item_da_ida(2, "URBANA") is None
    assert N.item_da_ida(3, "URBANA") is None
    assert N.item_da_ida(4, "URBANA") == ("15.8.1.1", N.CAMINHO_DILIGENCIA_EXTRA)


# --------------------------------------------------------- o domínio no banco


def test_a_notificacao_do_rcpj_e_recusada(casa):
    db = casa["db"]
    with db.transaction() as con:
        tid = int(banco(con).escrever(
            """INSERT INTO rg_titulos(atribuicao, data_apresentacao, criado_em)
               VALUES (3, '2026-10-01', '2026-10-01T09:00:00') RETURNING id""")[0]["id"])
    with pytest.raises(N.NotificacaoError, match="RCPJ"):
        _notificacao(db, tid)


def test_a_quarta_diligencia_so_a_pedido_do_apresentante(casa):
    db = casa["db"]
    dias = _dias_de_diligencia(4)
    nid = _notificacao(db, _titulo(db, dias[0]))
    for k, (dia, hora) in enumerate(zip(dias[:3], ("09:00", "14:00", "19:00"))):
        _ida(db, nid, dia, hora)
    with pytest.raises(N.NotificacaoError, match="a pedido"):
        _ida(db, nid, dias[3], "10:00")
    r = _ida(db, nid, dias[3], "10:00", a_pedido=True)
    assert r["numero"] == 4 and r["diligencia_id"]
    with db.connect() as con:
        itens = [d["codigo_tj"] for d in N.diligencias(con, nid)]
    # a primeira cobre três; a quarta é outra diligência cobrada
    assert itens == ["15.8.1", "15.8.1.1"]


def test_certidao_antes_do_registro_e_recusada(casa):
    db = casa["db"]
    dias = _dias_de_diligencia(1)
    nid = _notificacao(db, _titulo(db, dias[0]))
    _ida(db, nid, dias[0], "10:00", resultado="ENTREGUE")
    with db.transaction() as con:
        banco(con).escrever(
            "UPDATE rg_notificacao_diligencias SET selo_situacao='SELADO' "
            "WHERE notificacao_id = %s", (nid,))
    with pytest.raises(N.NotificacaoError, match="art. 988"):
        with db.transaction() as con:
            N.emitir_certidao(con, nid, agora=db.now(), sv=SV,
                              data_extenso=EXTENSO)


def test_entrega_a_procurador_exige_dizer_os_poderes(casa):
    db = casa["db"]
    dias = _dias_de_diligencia(1)
    nid = _notificacao(db, _titulo(db, dias[0]))
    with pytest.raises(N.NotificacaoError, match="art. 992"):
        _ida(db, nid, dias[0], "10:00", resultado="ENTREGUE_PROCURADOR")


# --------------------------------------------------------------- as telas


def test_anonimo_vai_ao_login(casa):
    assert casa["app"].test_client().get("/rcpj-rtd/notificacoes").status_code == 302


def test_as_telas_abrem_numa_casa_vazia(casa):
    c = _logado(casa)
    assert c.get("/rcpj-rtd/notificacoes").status_code == 200
    assert c.get("/rcpj-rtd/notificacoes/nova").status_code == 200


def test_post_sem_csrf_e_recusado(casa):
    db = casa["db"]
    dias = _dias_de_diligencia(1)
    nid = _notificacao(db, _titulo(db, dias[0]))
    c = _logado(casa)
    r = c.post(f"/rcpj-rtd/notificacao/{nid}/diligencia",
               data={"data": dias[0], "hora": "10:00", "resultado": "AUSENTE"})
    assert r.status_code == 400


def test_auditor_le_mas_nao_registra_diligencia(casa):
    db = casa["db"]
    dias = _dias_de_diligencia(1)
    nid = _notificacao(db, _titulo(db, dias[0]))
    c = _logado(casa, "auditor")
    url = f"/rcpj-rtd/notificacao/{nid}"
    assert c.get(url).status_code == 200
    r = c.post(f"{url}/diligencia", data={
        "csrf_token": _token(c, url), "data": dias[0], "hora": "10:00",
        "resultado": "AUSENTE"})
    assert r.status_code == 403


def test_o_balcao_nao_certifica_a_negativa(casa):
    db = casa["db"]
    dias = _dias_de_diligencia(1)
    nid = _notificacao(db, _titulo(db, dias[0]))
    c = _logado(casa, "balcao")
    url = f"/rcpj-rtd/notificacao/{nid}"
    r = c.post(f"{url}/negativa", data={"csrf_token": _token(c, url)})
    assert r.status_code == 403


def test_domingo_volta_como_aviso_e_nao_grava(casa):
    db = casa["db"]
    domingo = date.today() - timedelta(days=(date.today().weekday() + 1) % 7 or 7)
    nid = _notificacao(db, _titulo(db, (domingo - timedelta(days=3)).isoformat()))
    c = _logado(casa)
    url = f"/rcpj-rtd/notificacao/{nid}"
    r = c.post(f"{url}/diligencia", data={
        "csrf_token": _token(c, url), "data": domingo.isoformat(),
        "hora": "10:00", "resultado": "AUSENTE"}, follow_redirects=True)
    assert "domingo" in r.get_data(as_text=True)
    with db.connect() as con:
        assert N.idas(con, nid) == []


def test_o_selo_que_nao_sai_suspende_a_diligencia_e_fica_no_rastro(
        casa, protocolo_pago):
    """Sem o aparelho, a ida fica registrada e a diligência SUSPENSA — e a
    certidão não sai enquanto ela não for selada.

    Com o protocolo pago, para a falha ser a do APARELHO — sem ele, quem
    suspendia era a trava do selo pago, e o teste passava pelo motivo errado.
    """
    db = casa["db"]
    dias = _dias_de_diligencia(1)
    tid = _titulo(db, dias[0])
    _registrar(db, tid)
    nid = _notificacao(db, tid)
    c = _logado(casa)
    url = f"/rcpj-rtd/notificacao/{nid}"
    r = c.post(f"{url}/diligencia", data={
        "csrf_token": _token(c, url), "data": dias[0], "hora": "10:00",
        "resultado": "ENTREGUE"}, follow_redirects=True)
    assert "SEM SELO" in r.get_data(as_text=True)
    with db.connect() as con:
        bd = banco(con)
        d = N.diligencias(con, nid)
        assert [x["selo_situacao"] for x in d] == ["SUSPENSO"]
        assert bd.valor("SELECT count(*) AS n FROM audit_logs WHERE action = %s",
                        ("RG_NOTIFICACAO_SELO_SUSPENSO",)) == 1
        assert bd.valor("SELECT count(*) AS n FROM audit_logs WHERE action = %s",
                        ("RG_NOTIFICACAO_DILIGENCIA",)) == 1
    with pytest.raises(N.NotificacaoError, match="selo suspenso"):
        with db.transaction() as con:
            N.emitir_certidao(con, nid, agora=db.now(), sv=SV,
                              data_extenso=EXTENSO)


def test_a_certidao_positiva_sai_com_numero_selo_e_averbacao(casa, protocolo_pago,
                                                             selo_que_sai):
    db = casa["db"]
    dias = _dias_de_diligencia(1)
    tid = _titulo(db, dias[0])
    rid = _registrar(db, tid)
    nid = _notificacao(db, tid)
    c = _logado(casa)
    url = f"/rcpj-rtd/notificacao/{nid}"
    c.post(f"{url}/diligencia", data={
        "csrf_token": _token(c, url), "data": dias[0], "hora": "10:00",
        "resultado": "ENTREGUE"})
    r = c.post(f"{url}/certidao", data={"csrf_token": _token(c, url)},
               follow_redirects=True)
    assert r.status_code == 200
    with db.connect() as con:
        cert = N.certidoes(con, nid)
        assert len(cert) == 1 and cert[0]["tipo"] == "POSITIVA"
        assert cert[0]["numero"] == 1 and cert[0]["selo_situacao"] == "SELADO"
        assert cert[0]["selo"].startswith("SELOEXEMPLO")
        assert "FULANO DE EXEMPLO" in cert[0]["teor"]
        assert "entregando-lhe uma via" in cert[0]["teor"]
        assert N.diligencias(con, nid)[0]["selo_situacao"] == "SELADO"
    caminhos = [p["caminho"] for p in selo_que_sai]
    assert caminhos == [N.CAMINHO_DILIGENCIA_URBANA, N.CAMINHO_CERTIDAO]
    assert selo_que_sai[1]["dados"]["ato"]["codigo"] == "15.8.2"
    # e a certidão se averba à margem do registro, em ato próprio
    c.post(f"{url}/averbar", data={"csrf_token": _token(c, url)})
    with db.connect() as con:
        n = N.notificacao(con, nid)
        assert n["averbacao_ato_id"]
        averb = banco(con).um("SELECT * FROM rg_atos WHERE id = %s",
                              (n["averbacao_ato_id"],))
        assert averb["tipo"] == "AVERBACAO" and averb["registro_id"] == rid
        assert "AVERBAÇÃO DE NOTIFICAÇÃO" in averb["teor"]


def test_a_negativa_com_tres_idas_alternadas_sai_pela_tela(casa, protocolo_pago,
                                                            selo_que_sai):
    db = casa["db"]
    dias = _dias_de_diligencia(3)
    tid = _titulo(db, dias[0])
    _registrar(db, tid)
    nid = _notificacao(db, tid)
    for dia, hora in zip(dias, ("09:00", "14:00", "19:00")):
        _ida(db, nid, dia, hora)
    with db.transaction() as con:      # a primeira, selada como se o aparelho
        banco(con).escrever(            # tivesse respondido
            "UPDATE rg_notificacao_diligencias SET selo_situacao='SELADO', "
            "selo='SELOEXEMPLO9999' WHERE notificacao_id = %s", (nid,))
    c = _logado(casa)
    url = f"/rcpj-rtd/notificacao/{nid}"
    c.post(f"{url}/negativa", data={"csrf_token": _token(c, url)})
    c.post(f"{url}/certidao", data={"csrf_token": _token(c, url)})
    with db.connect() as con:
        assert N.notificacao(con, nid)["situacao"] == "NEGATIVA"
        cert = N.certidoes(con, nid)
        assert [x["tipo"] for x in cert] == ["NEGATIVA"]
        assert "nas 3 diligências" in cert[0]["teor"]
        assert banco(con).valor(
            "SELECT count(*) AS n FROM audit_logs WHERE action = %s",
            ("RG_NOTIFICACAO_CERTIDAO",)) == 1


def test_o_atraso_da_primeira_diligencia_aparece_na_lista(casa):
    db = casa["db"]
    velho = (date.today() - timedelta(days=20)).isoformat()
    _notificacao(db, _titulo(db, velho))
    html = _logado(casa).get("/rcpj-rtd/notificacoes").get_data(as_text=True)
    assert "devia ter sido feita até" in html


def test_a_ficha_do_registro_do_rtd_leva_a_notificacao(casa):
    db = casa["db"]
    dias = _dias_de_diligencia(1)
    rid = _registrar(db, _titulo(db, dias[0]))
    html = _logado(casa).get(f"/rcpj-rtd/{rid}").get_data(as_text=True)
    assert "Notificar destinatário" in html
