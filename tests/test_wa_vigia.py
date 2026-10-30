"""O balcão do WhatsApp que funciona sozinho (29/10/2026).

    «preciso que o whatsapp seja mais funcional, preciso que atualize em tempo
     real […], receba arquivos enviados na conversa, configure a IA para fazer
     o primeiro atendimento, passando para atendente quando houver justo
     motivo» — o oficial

O vigia (`wa_vigia`), os arquivos (`wa_midia`), o horário (`wa_horario`), a
rotina (`wa_rotina`), a hora do cliente e a entrega (`wa_balcao`), e a
passagem por arquivo e por insistência (`wa_atendente`).

NADA AQUI FALA COM A META NEM COM PROVEDOR DE IA DE VERDADE: os transportes são
falsos, e um guarda faz qualquer saída de rede de verdade estourar o teste. Só
dados fictícios.
"""
from __future__ import annotations

import itertools
import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

import agente_provedores as PROV  # noqa: E402
import wa_atendente as AT  # noqa: E402
import wa_balcao as WA  # noqa: E402
import wa_fila as FILA  # noqa: E402
import wa_horario as HOR  # noqa: E402
import wa_midia as MIDIA  # noqa: E402
import wa_rotina as ROTINA  # noqa: E402
import wa_schema as SCH  # noqa: E402
import wa_transcricao as TRANSC  # noqa: E402
import wa_vigia as VIGIA  # noqa: E402
from bd_nativo import banco  # noqa: E402

CHEGOU = "2026-10-28T19:30:00"          # quarta-feira, depois do expediente
AGORA = "2026-10-28T20:00:00"
HORARIO = "seg-sex 08:00-12:00 13:00-17:00\nsab 08:00-12:00"


@pytest.fixture(autouse=True)
def _sem_rede(monkeypatch):
    def proibido(*a, **k):
        raise AssertionError("o teste tentou falar com a rede de verdade")
    monkeypatch.setattr(PROV, "_turno", proibido)
    monkeypatch.setattr(TRANSC, "_https", proibido)
    monkeypatch.setattr(MIDIA, "_https", proibido)
    monkeypatch.setattr(WA, "_http_post_json", proibido)


class Graph:
    """O falso do envio: guarda o que iria e devolve um id único."""
    _ids = itertools.count(1)

    def __init__(self):
        self.enviados = []

    def __call__(self, url, payload, headers):
        self.enviados.append({"url": url, "payload": payload})
        return 200, json.dumps({"messages": [{"id": f"wamid.vigia-{next(Graph._ids)}"}]})


@pytest.fixture()
def casa(cg_casa):
    return {"db": cg_casa["db"], "pasta": cg_casa["dados"], "app": cg_casa["app"]}


def _gravar(db, **valores):
    with db.transaction() as con:
        for chave, valor in valores.items():
            WA.gravar_config(con, chave, valor)


def _token_e_telefone(db):
    _gravar(db, **{SCH.CHAVE_TOKEN: "token-de-teste", SCH.CHAVE_PHONE: "123456789"})


def _entrada(db, *, meta_id, texto="olá", wa_id="5599900000101", quando=CHEGOU, msg=None):
    m = msg or {"from": wa_id, "id": meta_id, "type": "text", "text": {"body": texto}}
    with db.transaction() as con:
        r = WA.aplicar_entrada(con, {"messages": [m]}, agora=quando)
    return r["conversa_ids"][0] if r["conversa_ids"] else None


def _um(db, sql, args=()):
    with db.connect() as con:
        return banco(con).um(sql, args)


# ------------------------------------------------------------- o horário (só calcula)


def test_o_horario_se_le_e_diz_quando_abre():
    regra = HOR.ler(HORARIO)
    assert regra[0] == [(480, 720), (780, 1020)] and regra[5] == [(480, 720)]
    assert 6 not in regra                                         # domingo fechado
    quarta = datetime(2026, 10, 28, 20, 0)
    assert not HOR.aberto(regra, quarta)
    assert HOR.aberto(regra, datetime(2026, 10, 28, 9, 0))
    assert not HOR.aberto(regra, datetime(2026, 10, 28, 12, 30))  # almoço
    assert HOR.proxima_abertura(regra, quarta) == datetime(2026, 10, 29, 8, 0)
    assert HOR.quando_abre(regra, quarta) == "amanhã (quinta) às 8h"
    assert HOR.quando_abre(regra, datetime(2026, 10, 28, 12, 30)) == "hoje às 13h"
    assert HOR.fechou_em(regra, quarta) == datetime(2026, 10, 28, 17, 0)
    assert HOR.descrever(regra) == ("segunda a sexta, das 8h às 12h e das 13h às 17h; "
                                    "sábado, das 8h às 12h")
    assert HOR.ler("") == {} and HOR.aberto({}, quarta)           # sem horário = aberto


def test_o_horario_que_nao_se_le_diz_a_linha():
    with pytest.raises(HOR.HorarioErro, match="Linha 2"):
        HOR.ler("seg-sex 08:00-17:00\nfoo 08:00-12:00")
    with pytest.raises(HOR.HorarioErro, match="termina antes"):
        HOR.ler("seg 17:00-08:00")
    assert HOR.ler_ou_vazio("qualquer coisa") == {}


def test_a_hora_da_mensagem_e_a_do_cliente_e_nao_a_da_puxada():
    escrita = datetime(2026, 10, 28, 23, 10)
    msg = {"timestamp": str(int(escrita.timestamp()))}
    assert WA.quando_da_meta(msg, "2026-10-29T06:00:00") == "2026-10-28T23:10:00"
    assert WA.quando_da_meta({}, "2026-10-29T06:00:00") == "2026-10-29T06:00:00"
    futura = {"timestamp": str(int(datetime(2026, 10, 30).timestamp()))}
    assert WA.quando_da_meta(futura, "2026-10-29T06:00:00") == "2026-10-29T06:00:00"


# ------------------------------------------------------------- a entrega e o aviso


def test_a_entrega_so_avanca_e_guarda_o_motivo_da_falha(casa):
    db = casa["db"]
    cid = _entrada(db, meta_id="wamid.v-1")
    with db.transaction() as con:
        WA.gravar_saida(con, cid, "Bom dia!", "wamid.saiu-1", autor="MARIO", agora=AGORA)

    def status(situacao, **extra):
        corpo = {"entry": [{"changes": [{"value": {"statuses": [
            {"id": "wamid.saiu-1", "status": situacao, **extra}]}}]}]}
        with db.transaction() as con:
            return WA.aplicar_entrada(con, corpo, agora=AGORA)["entregas"]

    assert status("delivered") == 1
    assert status("sent") == 0                       # aviso atrasado não desfaz
    assert status("read") == 1
    assert _um(db, "SELECT entrega FROM wa_mensagem WHERE meta_id='wamid.saiu-1'")[
        "entrega"] == "read"
    # «FAILED» NÃO DESFAZ O QUE CHEGOU (29/10/2026, decisão do oficial): até o #94
    # este teste esperava o «failed» por cima do «read».
    assert status("failed", errors=[{"title": "Mensagem não entregue"}]) == 0
    assert _um(db, "SELECT entrega FROM wa_mensagem WHERE meta_id='wamid.saiu-1'")[
        "entrega"] == "read"
    # depois de só «saiu», a falha ainda é gravada, com o motivo
    with db.transaction() as con:
        WA.gravar_saida(con, cid, "Outra.", "wamid.saiu-2", autor="MARIO", agora=AGORA)
    corpo = {"entry": [{"changes": [{"value": {"statuses": [
        {"id": "wamid.saiu-2", "status": "sent"}]}}]}]}
    with db.transaction() as con:
        WA.aplicar_entrada(con, corpo, agora=AGORA)
    corpo["entry"][0]["changes"][0]["value"]["statuses"][0].update(
        status="failed", errors=[{"title": "Mensagem não entregue"}])
    with db.transaction() as con:
        assert WA.aplicar_entrada(con, corpo, agora=AGORA)["entregas"] == 1
    m = _um(db, "SELECT entrega, entrega_erro FROM wa_mensagem WHERE meta_id='wamid.saiu-2'")
    assert m["entrega"] == "failed" and "não entregue" in m["entrega_erro"]


def test_o_aviso_automatico_nao_tira_a_conversa_do_alerta(casa):
    db = casa["db"]
    cid = _entrada(db, meta_id="wamid.v-2")
    with db.transaction() as con:
        WA.gravar_saida(con, cid, "Sua mensagem foi passada.", "wamid.av-1",
                        autor="ia", agora=AGORA, tipo=ROTINA.TIPO_AVISO)
    with db.connect() as con:
        assert FILA.nao_respondidas(con, usuario_id=None) == 1
        c = banco(con).um("SELECT status FROM wa_conversa WHERE id=%s", (cid,))
    assert c["status"] == SCH.ABERTA                 # não virou «aguardando»
    with db.transaction() as con:
        WA.gravar_saida(con, cid, "Respondido.", "wamid.av-2", autor="MARIO", agora=AGORA)
    with db.connect() as con:
        assert FILA.nao_respondidas(con, usuario_id=None) == 0


def test_o_aviso_de_fora_do_horario_sai_uma_vez_por_periodo(casa):
    db = casa["db"]
    _token_e_telefone(db)
    _gravar(db, **{SCH.CHAVE_HORARIO: HORARIO, SCH.CHAVE_FORA_HORARIO_LIGADO: "1"})
    cid = _entrada(db, meta_id="wamid.v-3")
    graph = Graph()
    assert ROTINA.avisar_fora_do_horario(db, agora=AGORA, http_post=graph) == 1
    corpo = graph.enviados[0]["payload"]["text"]["body"]
    assert "amanhã (quinta) às 8h" in corpo and "segunda a sexta" in corpo
    _entrada(db, meta_id="wamid.v-4", texto="alô?", quando="2026-10-28T21:00:00")
    assert ROTINA.avisar_fora_do_horario(db, agora="2026-10-28T21:05:00", http_post=graph) == 0
    assert len(graph.enviados) == 1
    with db.connect() as con:
        assert FILA.nao_respondidas(con, usuario_id=None) == 1     # continua esperando
    saida = _um(db, "SELECT tipo, autor FROM wa_mensagem WHERE conversa_id=%s "
                    "AND direcao='out'", (cid,))
    assert saida["tipo"] == ROTINA.TIPO_AVISO


def test_com_a_ia_ligada_o_aviso_espera_a_ia_olhar(casa):
    db = casa["db"]
    _token_e_telefone(db)
    _gravar(db, **{SCH.CHAVE_HORARIO: HORARIO, SCH.CHAVE_FORA_HORARIO_LIGADO: "1",
                   SCH.CHAVE_IA_LIGADA: "1", SCH.CHAVE_IA_LIGADA_EM: "2026-10-28T08:00:00"})
    _entrada(db, meta_id="wamid.v-5")
    graph = Graph()
    assert ROTINA.avisar_fora_do_horario(db, agora=AGORA, http_post=graph) == 0
    assert graph.enviados == []


def test_o_aviso_de_fora_do_horario_recusa_chave_desconhecida(casa):
    db = casa["db"]
    with pytest.raises(ROTINA.RotinaErro, match="só aceita"):
        with db.transaction() as con:
            ROTINA.gravar(con, {"horario": HORARIO, "fora_texto": "Volte {amanha}."})
    with pytest.raises(ROTINA.RotinaErro, match="horário não foi gravado"):
        with db.transaction() as con:
            ROTINA.gravar(con, {"horario": "segunda o dia todo"})
    with pytest.raises(ROTINA.RotinaErro, match="10 a 600"):
        with db.transaction() as con:
            ROTINA.gravar(con, {"vigia_segundos": "3"})


def test_a_conversa_parada_se_resolve_e_o_rastro_diz_por_que(casa):
    db = casa["db"]
    cid = _entrada(db, meta_id="wamid.v-6", quando="2026-10-20T10:00:00")
    with db.transaction() as con:
        WA.gravar_saida(con, cid, "Pronto.", "wamid.v-6-out", autor="MARIO",
                        agora="2026-10-20T10:05:00")
    _gravar(db, **{SCH.CHAVE_ENCERRAR_DIAS: "3"})
    assert ROTINA.encerrar_paradas(db, agora=AGORA) == 1
    c = _um(db, "SELECT status FROM wa_conversa WHERE id=%s", (cid,))
    assert c["status"] == SCH.RESOLVIDA
    ev = _um(db, "SELECT tipo, nota FROM wa_evento WHERE conversa_id=%s ORDER BY id DESC "
                 "LIMIT 1", (cid,))
    assert ev["tipo"] == FILA.EV_ENCERRADA and "3 dia" in ev["nota"]
    _gravar(db, **{SCH.CHAVE_ENCERRAR_DIAS: "0"})
    assert ROTINA.encerrar_paradas(db, agora=AGORA) == 0


# ------------------------------------------------------------- os arquivos


def _foto(meta_id, wa_id="5599900000102"):
    return {"from": wa_id, "id": meta_id, "type": "image",
            "image": {"id": "midia-foto-1", "mime_type": "image/jpeg",
                      "caption": "segue o documento"}}


def test_a_foto_do_cliente_e_baixada_e_guardada(casa, tmp_path):
    db = casa["db"]
    _token_e_telefone(db)
    _entrada(db, meta_id="wamid.f-1", msg=_foto("wamid.f-1"))
    chamadas = []

    def https(host, metodo, caminho, corpo=None, cabecalhos=None, prazo=60):
        chamadas.append(host)
        if host == "graph.facebook.com":
            return 200, json.dumps({"url": "https://lookaside.fbsbx.com/m?id=1",
                                    "mime_type": "image/jpeg", "file_size": 9}).encode()
        if host == "lookaside.fbsbx.com":
            return 200, b"\xff\xd8foto-falsa"
        raise AssertionError(host)
    r = MIDIA.baixar_pendentes(db, pasta_arquivos=tmp_path, agora=AGORA, https=https)
    assert r["baixados"] == 1 and chamadas == ["graph.facebook.com", "lookaside.fbsbx.com"]
    m = _um(db, "SELECT * FROM wa_mensagem WHERE meta_id='wamid.f-1'")
    assert m["midia_situacao"] == SCH.MIDIA_OK and m["arquivo_nome"].endswith(".jpg")
    assert Path(m["arquivo_caminho"]).read_bytes() == b"\xff\xd8foto-falsa"
    assert Path(m["arquivo_caminho"]).parent == (tmp_path / "whatsapp" / "2026-10").resolve()
    assert MIDIA.como_mostrar(dict(m)) == "foto"
    # a segunda volta não baixa de novo
    assert MIDIA.baixar_pendentes(db, pasta_arquivos=tmp_path, agora=AGORA,
                                  https=https)["baixados"] == 0


def test_o_arquivo_que_nao_baixa_fica_com_erro_e_volta_pelo_botao(casa, tmp_path):
    db = casa["db"]
    _token_e_telefone(db)
    _entrada(db, meta_id="wamid.f-2", msg=_foto("wamid.f-2"))

    def https(host, metodo, caminho, corpo=None, cabecalhos=None, prazo=60):
        return 404, b"{}"
    r = MIDIA.baixar_pendentes(db, pasta_arquivos=tmp_path, agora=AGORA, https=https)
    assert r == {"baixados": 0, "erros": 1, "adiados": 0}     # o 404 é definitivo
    m = _um(db, "SELECT id, midia_situacao, arquivo_erro FROM wa_mensagem "
                "WHERE meta_id='wamid.f-2'")
    assert m["midia_situacao"] == SCH.MIDIA_ERRO and "HTTP 404" in m["arquivo_erro"]
    # não tenta sozinho de novo a cada volta
    assert MIDIA.baixar_pendentes(db, pasta_arquivos=tmp_path, agora=AGORA,
                                  https=https)["erros"] == 0
    with db.transaction() as con:
        assert MIDIA.tentar_de_novo(con, int(m["id"]))
    assert _um(db, "SELECT midia_situacao FROM wa_mensagem WHERE id=%s",
               (int(m["id"]),))["midia_situacao"] is None


def test_o_endereco_da_midia_fora_da_meta_nao_leva_o_token():
    enviados = []

    def https(host, metodo, caminho, corpo=None, cabecalhos=None, prazo=60):
        enviados.append(host)
        return 200, json.dumps({"url": "https://fora.exemplo.invalid/x"}).encode()
    with pytest.raises(MIDIA.MidiaErro, match="fora dela"):
        MIDIA.baixar("token", "midia-1", https=https)
    assert enviados == ["graph.facebook.com"]


def test_o_envio_de_arquivo_confere_tipo_e_tamanho():
    assert MIDIA.conferir_envio("certidao.pdf", 1000) == ("document", "application/pdf")
    assert MIDIA.conferir_envio("foto.JPG", 1000) == ("image", "image/jpeg")
    with pytest.raises(MIDIA.MidiaErro, match="não aceita"):
        MIDIA.conferir_envio("programa.exe", 1000)
    with pytest.raises(MIDIA.MidiaErro, match="até 5 MB"):
        MIDIA.conferir_envio("foto.png", 6 * 1024 * 1024)
    assert MIDIA.tipo_para_servir({"arquivo_nome": "a.svg"}) == ("application/octet-stream",
                                                                  False)
    assert MIDIA.tipo_para_servir({"arquivo_nome": "a.pdf"}) == ("application/pdf", True)


# ------------------------------------------------------------- a IA e o justo motivo


def _ia_ligada(db):
    _token_e_telefone(db)
    _gravar(db, **{SCH.CHAVE_IA_LIGADA: "1", SCH.CHAVE_IA_LIGADA_EM: "2026-10-28T08:00:00",
                   SCH.CHAVE_TEXTO_BASE: "HORÁRIO: segunda a sexta, das 8 às 17 horas.",
                   SCH.CHAVE_IA_PROVEDOR: "claude"})


class Modelo:
    def __init__(self, decisao):
        self.chamadas = []
        self.decisao = decisao

    def __call__(self, pasta, **k):
        self.chamadas.append(k)
        return {"texto": json.dumps(self.decisao), "entrada": 10, "saida": 5,
                "modelo": "falso-1", "chamadas": [], "parou": "end_turn"}


def test_documento_do_cliente_passa_para_pessoa_sem_subir_a_ia(casa):
    db = casa["db"]
    _ia_ligada(db)
    cid = _entrada(db, meta_id="wamid.ia-1", msg=_foto("wamid.ia-1"))
    modelo = Modelo({"acao": "responder", "tipo": "duvida", "resposta": "ok"})
    AT.rodada(db, agora=AGORA, pasta_de_dados=casa["pasta"], conversar=modelo,
              http_post=Graph())
    assert modelo.chamadas == []
    c = _um(db, "SELECT modo, passagem_motivo FROM wa_conversa WHERE id=%s", (cid,))
    assert c["modo"] == SCH.MODO_PESSOA and "arquivo" in c["passagem_motivo"]


def test_o_cliente_que_insiste_depois_das_respostas_automaticas_vai_para_pessoa(casa):
    db = casa["db"]
    _ia_ligada(db)
    cid = _entrada(db, meta_id="wamid.ia-2", texto="e o horário?")
    with db.transaction() as con:
        for n in range(AT.RESPOSTAS_ANTES_DE_PESSOA):
            banco(con).escrever(
                """INSERT INTO wa_ia_registro (conversa_id, wa_id, quando, caso, enviado)
                   VALUES (%s, %s, %s, %s, 1)""",
                (cid, "5599900000101", f"2026-10-28T19:0{n}:00", AT.CASO_DUVIDA))
    modelo = Modelo({"acao": "responder", "tipo": "duvida", "resposta": "Das 8 às 17."})
    AT.rodada(db, agora=AGORA, pasta_de_dados=casa["pasta"], conversar=modelo,
              http_post=Graph())
    assert modelo.chamadas == []
    c = _um(db, "SELECT modo, passagem_motivo FROM wa_conversa WHERE id=%s", (cid,))
    assert c["modo"] == SCH.MODO_PESSOA and "seguiu escrevendo" in c["passagem_motivo"]


def test_o_aviso_de_passagem_diz_o_horario_e_nao_conta_como_resposta(casa):
    db = casa["db"]
    _ia_ligada(db)
    _gravar(db, **{SCH.CHAVE_IA_AVISO_PASSAGEM: "1", SCH.CHAVE_HORARIO: HORARIO})
    _entrada(db, meta_id="wamid.ia-3", texto="quero falar com uma pessoa")
    graph = Graph()
    AT.rodada(db, agora=AGORA, pasta_de_dados=casa["pasta"],
              conversar=Modelo({"acao": "pessoa"}), http_post=graph)
    corpo = graph.enviados[0]["payload"]["text"]["body"]
    assert "amanhã (quinta) às 8h" in corpo and "ATENDENTE" not in corpo
    with db.connect() as con:
        assert FILA.nao_respondidas(con, usuario_id=None) == 1


# ------------------------------------------------------------- a volta do vigia


def test_a_volta_aplica_e_um_passo_que_falha_nao_para_os_outros(casa, tmp_path, monkeypatch):
    db = casa["db"]
    _gravar(db, **{SCH.CHAVE_CAIXA_URL: "https://caixa.exemplo/pendentes",
                   SCH.CHAVE_CAIXA_SEGREDO: "segredo-teste"})
    item = {"id": "c-1", "payload": {"messages": [
        {"from": "5599900000103", "id": "wamid.c-1", "type": "text",
         "text": {"body": "bom dia"}}]}}

    def http_get(url, segredo, timeout=8):
        return 200, json.dumps([item])
    confirmados = []

    def http_post(url, segredo_ou_payload, corpo_ou_headers):
        confirmados.append(url)
        return 200, "{}"

    def quebra(*a, **k):
        raise RuntimeError("falso")
    monkeypatch.setattr(MIDIA, "baixar_pendentes", quebra)
    rodou = []
    monkeypatch.setattr(AT, "rodada", lambda db, **k: rodou.append(1) or {"conversas": []})
    r = VIGIA.um_ciclo(db, pasta_dados=casa["pasta"], pasta_arquivos=tmp_path, agora=AGORA,
                       http_get=http_get, http_post=http_post)
    assert r["aplicadas"] == 1 and confirmados and confirmados[0].endswith("/ack")
    assert r["erros"] == ["arquivos: RuntimeError"] and rodou == [1]


def test_o_vigia_sem_caixa_postal_so_espera(casa):
    db = casa["db"]
    assert VIGIA.segundos_da_volta(db) is None
    _gravar(db, **{SCH.CHAVE_CAIXA_URL: "https://caixa.exemplo/pendentes"})
    assert VIGIA.segundos_da_volta(db) == ROTINA.VIGIA_PADRAO_S
    _gravar(db, **{SCH.CHAVE_VIGIA_SEGUNDOS: "0"})
    assert VIGIA.segundos_da_volta(db) is None


# ------------------------------------------------------------- as telas


@pytest.fixture()
def s(cg_casa):
    from test_wa_balcao import _sessao
    return _sessao(cg_casa)


def test_o_alerta_traz_a_ultima_mensagem_para_o_aviso_do_windows(s):
    from test_wa_balcao import _payload
    s["c"].post("/whatsapp/webhook", data=json.dumps(_payload("preciso de certidão",
                                                               meta_id="wamid.t-1")),
                content_type="application/json", headers={"X-Wa-Test": "1"})
    dados = s["c"].get("/whatsapp/nao-respondidas").get_json()
    assert dados["n"] == 1 and dados["ultima"]["trecho"] == "preciso de certidão"
    assert dados["ultima"]["nome"] == "Fulano da Silva"
    html = s["c"].get("/whatsapp").get_data(as_text=True)
    assert "data-wa-avisos" in html and "data-wa-ligar-avisos" in html


def test_o_arquivo_da_conversa_abre_na_tela_e_baixa(s, tmp_path):
    bd = s["bd"]
    cid = _entrada(bd, meta_id="wamid.t-2", msg=_foto("wamid.t-2"))
    foto = tmp_path / "foto.jpg"
    foto.write_bytes(b"\xff\xd8foto")
    with bd.transaction() as con:
        mid = int(banco(con).um("SELECT id FROM wa_mensagem WHERE meta_id='wamid.t-2'")["id"])
        banco(con).escrever(
            "UPDATE wa_mensagem SET midia_situacao=%s, arquivo_nome=%s, arquivo_caminho=%s "
            "WHERE id=%s", (SCH.MIDIA_OK, "foto.jpg", str(foto), mid))
    r = s["c"].get(f"/whatsapp/midia/{mid}")
    assert r.status_code == 200 and r.mimetype == "image/jpeg"
    assert "attachment" not in (r.headers.get("Content-Disposition") or "")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    r = s["c"].get(f"/whatsapp/midia/{mid}?baixar=1")
    assert "attachment" in r.headers["Content-Disposition"]
    html = s["c"].get(f"/whatsapp/{cid}").get_data(as_text=True)
    assert f'src="/whatsapp/midia/{mid}"' in html
    sem = _entrada(bd, meta_id="wamid.t-3")
    sem_id = _um(bd, "SELECT id FROM wa_mensagem WHERE meta_id='wamid.t-3'")["id"]
    assert sem and s["c"].get(f"/whatsapp/midia/{sem_id}").status_code == 404


def test_a_rotina_do_balcao_so_grava_o_que_se_le(s):
    from test_wa_balcao import _token
    token = _token(s["c"].get("/whatsapp/atendente").get_data(as_text=True))
    r = s["c"].post("/whatsapp/balcao", data={"csrf_token": token, "horario": "toda hora"},
                    follow_redirects=True)
    assert "Nada foi guardado" in r.get_data(as_text=True)
    r = s["c"].post("/whatsapp/balcao", data={
        "csrf_token": token, "horario": HORARIO, "fora_ligado": "1",
        "respostas": "bom dia | Bom dia, {nome}!", "vigia_segundos": "15",
        "encerrar_dias": "5"}, follow_redirects=True)
    assert "Rotina do balcão guardada" in r.get_data(as_text=True)
    with s["bd"].connect() as con:
        cfg = ROTINA.config(con)
    assert cfg["vigia_segundos"] == 15 and cfg["encerrar_dias"] == 5 and cfg["fora_ligado"]
    assert cfg["respostas"] == [{"atalho": "bom dia", "texto": "Bom dia, {nome}!"}]



# ===================================================================
# AS DIFERENÇAS DO ROTEIRO DE ANEXOS E ENTREGA, SOBRE O #94 (29/10/2026)
# ===================================================================

DEPOIS = "2026-10-28T20:03:00"       # passada a espera entre as tentativas
MAIS_DEPOIS = "2026-10-28T20:06:00"


def _https_que_responde(*respostas):
    """Um `https` falso que, na Graph, responde na ordem dada: um número é o
    HTTP do endereço; "ok" entrega o endereço e o arquivo; uma exceção sobe."""
    fila = list(respostas)

    def https(host, metodo, caminho, corpo=None, cabecalhos=None, prazo=60):
        if host == "lookaside.fbsbx.com":
            return 200, b"\xff\xd8foto-falsa"
        r = fila.pop(0)
        if isinstance(r, BaseException):
            raise r
        if r == "ok":
            return 200, json.dumps({"url": "https://lookaside.fbsbx.com/m?id=1",
                                    "mime_type": "image/jpeg", "file_size": 9}).encode()
        return int(r), b"{}"
    return https


def _foto_da_vez(db, meta_id):
    _token_e_telefone(db)
    _entrada(db, meta_id=meta_id, msg=_foto(meta_id))
    return _um(db, "SELECT id FROM wa_mensagem WHERE meta_id=%s", (meta_id,))["id"]


def test_um_503_volta_a_fila_e_a_passada_seguinte_baixa(casa, tmp_path):
    db = casa["db"]
    mid = _foto_da_vez(db, "wamid.p-1")
    https = _https_que_responde(503, "ok")
    r = MIDIA.baixar_pendentes(db, pasta_arquivos=tmp_path, agora=AGORA, https=https)
    assert r == {"baixados": 0, "erros": 0, "adiados": 1}
    m = _um(db, "SELECT midia_situacao, midia_tentativas, arquivo_erro FROM wa_mensagem "
                "WHERE id=%s", (mid,))
    assert m["midia_situacao"] is None and m["midia_tentativas"] == 1 and not m["arquivo_erro"]
    # antes da espera, a passada não tenta de novo
    assert MIDIA.baixar_pendentes(db, pasta_arquivos=tmp_path, agora=AGORA,
                                  https=https)["adiados"] == 0
    r = MIDIA.baixar_pendentes(db, pasta_arquivos=tmp_path, agora=DEPOIS, https=https)
    assert r["baixados"] == 1
    m = _um(db, "SELECT midia_situacao, arquivo_erro, arquivo_caminho FROM wa_mensagem "
                "WHERE id=%s", (mid,))
    assert m["midia_situacao"] == SCH.MIDIA_OK and m["arquivo_erro"] is None
    assert Path(m["arquivo_caminho"]).read_bytes() == b"\xff\xd8foto-falsa"


def test_tres_erros_passageiros_viram_erro_e_o_botao_zera(casa, tmp_path):
    db = casa["db"]
    mid = _foto_da_vez(db, "wamid.p-2")
    https = _https_que_responde(503, OSError("a rede caiu"), 429, "ok")
    for quando in (AGORA, DEPOIS):
        assert MIDIA.baixar_pendentes(db, pasta_arquivos=tmp_path, agora=quando,
                                      https=https)["adiados"] == 1
    r = MIDIA.baixar_pendentes(db, pasta_arquivos=tmp_path, agora=MAIS_DEPOIS, https=https)
    assert r == {"baixados": 0, "erros": 1, "adiados": 0}
    m = _um(db, "SELECT midia_situacao, midia_tentativas, arquivo_erro FROM wa_mensagem "
                "WHERE id=%s", (mid,))
    assert m["midia_situacao"] == SCH.MIDIA_ERRO and m["midia_tentativas"] == 3
    assert "HTTP 429" in m["arquivo_erro"] and "3 tentativas" in m["arquivo_erro"]
    with db.transaction() as con:
        assert MIDIA.tentar_de_novo(con, int(mid))
    m = _um(db, "SELECT midia_situacao, midia_tentativas FROM wa_mensagem WHERE id=%s", (mid,))
    assert m["midia_situacao"] is None and m["midia_tentativas"] == 0
    assert MIDIA.baixar_pendentes(db, pasta_arquivos=tmp_path, agora=MAIS_DEPOIS,
                                  https=https)["baixados"] == 1


def test_o_4xx_da_graph_e_definitivo_na_hora(casa, tmp_path):
    db = casa["db"]
    mid = _foto_da_vez(db, "wamid.p-3")
    r = MIDIA.baixar_pendentes(db, pasta_arquivos=tmp_path, agora=AGORA,
                               https=_https_que_responde(400))
    assert r == {"baixados": 0, "erros": 1, "adiados": 0}
    assert _um(db, "SELECT midia_situacao FROM wa_mensagem WHERE id=%s",
               (mid,))["midia_situacao"] == SCH.MIDIA_ERRO


def _saida_com_status(db, meta_id, *avisos, wa_id="5599900000201"):
    cid = _entrada(db, meta_id=f"in-{meta_id}", wa_id=wa_id)
    with db.transaction() as con:
        WA.gravar_saida(con, cid, "Respondido.", meta_id, autor="MARIO", agora=AGORA)
    for status, extra in avisos:
        corpo = {"entry": [{"changes": [{"value": {"statuses": [
            {"id": meta_id, "status": status, **extra}]}}]}]}
        with db.transaction() as con:
            WA.aplicar_entrada(con, corpo, agora=AGORA)
    return cid


def test_failed_depois_de_entregue_nao_muda(casa):
    db = casa["db"]
    _saida_com_status(db, "wamid.e-1", ("delivered", {}),
                      ("failed", {"errors": [{"code": 131026, "title": "Undeliverable"}]}))
    m = _um(db, "SELECT entrega, entrega_erro FROM wa_mensagem WHERE meta_id='wamid.e-1'")
    assert m["entrega"] == "delivered" and m["entrega_erro"] is None


def test_as_frases_prontas_da_falha():
    assert WA.rotulo_da_entrega("failed", "131047: Re-engagement message")["marca"] == (
        "⚠ não chegou: passaram as 24 horas: use «Reabrir com o modelo»")
    assert WA.rotulo_da_entrega("failed", "131026: Message undeliverable")["titulo"] == (
        "o número não recebe mensagens do WhatsApp")
    # código desconhecido mostra o texto da Meta; o registro antigo, sem código, também
    assert WA.rotulo_da_entrega("failed", "131000: Something went wrong")["titulo"] == (
        "Something went wrong")
    assert WA.rotulo_da_entrega("failed", "Mensagem não entregue")["titulo"] == (
        "Mensagem não entregue")
    assert WA.rotulo_da_entrega("read", None) == {"entrega": "read", "marca": "✓✓",
                                                   "titulo": "o cliente leu"}
    assert WA.rotulo_da_entrega(None)["marca"] == ""


def test_o_balao_mostra_a_frase_do_131047_e_guarda_o_codigo(s):
    db = s["bd"]
    cid = _saida_com_status(db, "wamid.e-2", ("failed", {"errors": [
        {"code": 131047, "title": "Re-engagement message"}]}))
    assert _um(db, "SELECT entrega_erro FROM wa_mensagem WHERE meta_id='wamid.e-2'")[
        "entrega_erro"].startswith("131047: ")
    html = s["c"].get(f"/whatsapp/{cid}").get_data(as_text=True)
    assert "⚠ não chegou: passaram as 24 horas: use «Reabrir com o modelo»" in html
    assert 'data-wa-entrega="failed"' in html


def test_o_novas_traz_a_entrega_das_enviadas_ao_vivo(s):
    db = s["bd"]
    cid = _saida_com_status(db, "wamid.e-3")
    tela = s["c"].get(f"/whatsapp/{cid}").get_data(as_text=True)
    mid = _um(db, "SELECT id FROM wa_mensagem WHERE meta_id='wamid.e-3'")["id"]
    # o span existe mesmo antes do primeiro aviso, para o JS só trocar o atributo
    assert f'data-wa-entrega-de="{mid}" data-wa-entrega=""' in tela
    ultimo = _um(db, "SELECT max(id) AS n FROM wa_mensagem WHERE conversa_id=%s", (cid,))["n"]
    antes = s["c"].get(f"/whatsapp/{cid}/novas?depois={ultimo}").get_json()["entregas"]
    assert antes == [{"id": mid, "token": "", "entrega": "", "marca": "", "titulo": ""}]
    corpo = {"entry": [{"changes": [{"value": {"statuses": [
        {"id": "wamid.e-3", "status": "read"}]}}]}]}
    with db.transaction() as con:
        WA.aplicar_entrada(con, corpo, agora=AGORA)
    depois = s["c"].get(f"/whatsapp/{cid}/novas?depois={ultimo}").get_json()
    assert depois["html"] == ""                    # nada novo para desenhar...
    assert depois["entregas"] == [{"id": mid, "token": "", "entrega": "read", "marca": "✓✓",
                                   "titulo": "o cliente leu"}]   # ...mas a entrega anda
    js = (Path(__file__).resolve().parent.parent / "static" / "whatsapp_chat.js").read_text(
        encoding="utf-8")
    trecho = js[js.index("function atualizarEntregas"):js.index("function atualizarEstado")]
    assert "data-wa-entrega" in trecho and "textContent" in trecho
    assert "innerHTML" not in trecho


def test_o_cartao_da_lista_marca_nao_entregue(s):
    db = s["bd"]
    falhou = _saida_com_status(db, "wamid.e-4", ("failed", {"errors": [
        {"code": 131026, "title": "Undeliverable"}]}), wa_id="5599900000204")
    chegou = _saida_com_status(db, "wamid.e-5", ("delivered", {}), wa_id="5599900000205")
    html = s["c"].get("/whatsapp?aba=todas").get_data(as_text=True)
    import re
    cartoes = {int(i): c for i, c in re.findall(
        r'href="/whatsapp/(\d+)[^"]*"(.*?)</a>', html, re.S)}
    assert 'data-wa-etq="nao-entregue">não entregue</span>' in cartoes[falhou]
    assert "não entregue" not in cartoes[chegou]
