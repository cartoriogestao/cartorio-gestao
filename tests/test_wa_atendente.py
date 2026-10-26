"""O atendente com IA do WhatsApp, as etiquetas, o setor e o painel (26/10/2026).

NADA AQUI FALA COM A META NEM COM PROVEDOR DE IA DE VERDADE. Os transportes são
falsos, e um guarda automático faz qualquer saída de rede de verdade estourar
o teste: `agente_provedores._turno`, `wa_transcricao._https` e
`wa_balcao._http_post_json` são trocados por funções que levantam.

A identificação do protocolo usa `acompanhamento_cliente.consultar`, módulo de
outra passada: aqui ele é injetado em `sys.modules` (um falso), e o teste da
ausência dele o tira de lá.
"""
from __future__ import annotations

import json
import re
import sys
import types
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import agente_provedores as PROV  # noqa: E402
import wa_atendente as AT  # noqa: E402
import wa_balcao as WA  # noqa: E402
import wa_fila as FILA  # noqa: E402
import wa_schema as SCH  # noqa: E402
import wa_transcricao as TRANSC  # noqa: E402
from bd_nativo import banco  # noqa: E402

SENHA = "Senha#12345"
LIGADO_EM = "2026-10-26T09:00:00"
CHEGOU = "2026-10-26T09:30:00"
AGORA = "2026-10-26T10:00:00"
TEXTO_BASE = ("HORÁRIO: segunda a sexta, das 8 às 17 horas.\n"
              "ENDEREÇO: Rua Exemplo, 100, Centro.\n"
              "DOCUMENTOS — RECONHECIMENTO DE FIRMA: documento de identidade original.\n")


# ------------------------------------------------------------- os guardas


@pytest.fixture(autouse=True)
def _sem_rede(monkeypatch):
    def proibido(*a, **k):
        raise AssertionError("o teste tentou falar com a rede de verdade")
    monkeypatch.setattr(PROV, "_turno", proibido)
    monkeypatch.setattr(TRANSC, "_https", proibido)
    monkeypatch.setattr(WA, "_http_post_json", proibido)


@pytest.fixture()
def portal(monkeypatch):
    """O falso do portal do cliente: um protocolo só, com um código só."""
    vistos = []

    def consultar(con, numero, codigo):
        vistos.append((numero, codigo))
        if numero == "12345" and codigo == "ABC123":
            return {"numero": "12345", "situacao_publica": "em análise",
                    "previsao": "30/10/2026", "atualizado_em": "2026-10-25T16:00:00",
                    "atribuicao": "Registro de Imóveis"}
        return None
    modulo = types.ModuleType("acompanhamento_cliente")
    modulo.consultar = consultar
    monkeypatch.setitem(sys.modules, "acompanhamento_cliente", modulo)
    return vistos


class Graph:
    """O falso da Graph: guarda o que iria e devolve um id."""

    def __init__(self, status=200):
        self.enviados = []
        self.status = status

    def __call__(self, url, payload, headers):
        self.enviados.append({"url": url, "payload": payload})
        return self.status, json.dumps({"messages": [{"id": f"wamid.out-{len(self.enviados)}"}]})


class Modelo:
    """O falso do provedor: devolve a decisão que o teste mandou."""

    def __init__(self, decisao=None, texto=None):
        self.chamadas = []
        self.decisao = decisao
        self.texto = texto

    def __call__(self, pasta, **k):
        self.chamadas.append(k)
        texto = self.texto if self.texto is not None else json.dumps(self.decisao)
        return {"texto": texto, "entrada": 1000, "saida": 50, "modelo": "falso-1",
                "chamadas": [], "parou": "end_turn"}


# ------------------------------------------------------------- o preparo


def _cfg(db, **extra):
    valores = {SCH.CHAVE_IA_LIGADA: "1", SCH.CHAVE_IA_LIGADA_EM: LIGADO_EM,
               SCH.CHAVE_IA_LIGADA_POR: "MARIO EXEMPLO",
               SCH.CHAVE_TEXTO_BASE: TEXTO_BASE, SCH.CHAVE_IA_PROVEDOR: "claude",
               SCH.CHAVE_IA_PRECO_ENTRADA: "1", SCH.CHAVE_IA_PRECO_SAIDA: "5",
               SCH.CHAVE_TOKEN: "token-de-teste", SCH.CHAVE_PHONE: "123456789"}
    valores.update(extra)
    with db.transaction() as con:
        for chave, valor in valores.items():
            WA.gravar_config(con, chave, valor)


def _entrada(db, texto, *, meta_id, wa_id="5599900000001", quando=CHEGOU, msg=None):
    m = msg or {"from": wa_id, "id": meta_id, "type": "text", "text": {"body": texto}}
    with db.transaction() as con:
        r = WA.aplicar_entrada(con, {"messages": [m]}, agora=quando)
    return r["conversa_ids"][0] if r["conversa_ids"] else None


def _rodar(db, pasta, **k):
    k.setdefault("http_post", Graph())
    k.setdefault("conversar", Modelo({"acao": "pessoa", "motivo": "padrão do teste"}))
    return AT.rodada(db, agora=AGORA, pasta_de_dados=pasta, **k)


def _um(db, sql, args=()):
    with db.connect() as con:
        return banco(con).um(sql, args)


def _ler(db, sql, args=()):
    with db.connect() as con:
        return banco(con).ler(sql, args)


@pytest.fixture()
def casa(cg_casa):
    return {"db": cg_casa["db"], "pasta": cg_casa["dados"], "app": cg_casa["app"],
            "c": cg_casa["c"]}


# ---------------------------------------------- as regras sem banco nenhum


def test_identificacao_pede_os_dois_e_nao_toma_palavra_por_codigo():
    assert AT.identificacao("protocolo 12345 código ABC123") == ("12345", "ABC123")
    assert AT.identificacao("Protocolo nº 2026.10.35, codigo de acompanhamento X7K2P9") \
        == ("2026.10.35", "X7K2P9")
    assert AT.identificacao("protocolo 12345") is None
    assert AT.identificacao("o código está no recibo, protocolo 12345") is None


def test_a_resposta_so_sai_com_numero_que_esta_no_texto_base():
    assert AT.resposta_cabe_no_texto_base(
        "Atendemos de segunda a sexta, das 8 às 17 horas.", TEXTO_BASE) == ""
    assert "número" in AT.resposta_cabe_no_texto_base(
        "Atendemos das 7 às 18 horas.", TEXTO_BASE)
    assert "dinheiro" in AT.resposta_cabe_no_texto_base("Custa R$ 10.", TEXTO_BASE)
    assert "ocultado" in AT.resposta_cabe_no_texto_base(
        "Olá [PESSOA_01], tudo bem?", TEXTO_BASE)
    assert AT.resposta_cabe_no_texto_base("", TEXTO_BASE)


def test_assunto_sensivel_e_pedido_de_pessoa():
    assert AT.assunto_sensivel("tenho um título protestado")[0] == "PROTESTO"
    assert AT.assunto_sensivel("quero a certidão de nascimento")[0] == "RCPN"
    assert AT.assunto_sensivel("quero fazer uma reclamação")[0] == "GESTAO"
    assert AT.assunto_sensivel("qual o horário?") is None
    assert AT.pede_pessoa("quero falar com uma pessoa")
    assert AT.pede_pessoa("ATENDENTE")
    assert not AT.pede_pessoa("qual o endereço?")


def test_custo_do_audio_por_minuto():
    assert TRANSC.custo_do_audio(30, 0.006) == 0.003
    assert TRANSC.custo_do_audio(30, None) is None


# ---------------------------------------------- o interruptor e a janela


def test_desligado_de_fabrica_nao_faz_nada(casa):
    db = casa["db"]
    _entrada(db, "qual o horário?", meta_id="wamid.f1")
    modelo, graph = Modelo({"acao": "responder"}), Graph()
    r = AT.rodada(db, agora=AGORA, pasta_de_dados=casa["pasta"], conversar=modelo,
                  http_post=graph)
    assert r["desligado"] is True
    assert modelo.chamadas == [] and graph.enviados == []
    with db.connect() as con:
        assert AT.configuracao(con)["ia_ligada"] is False


def test_so_responde_o_que_chegou_depois_de_ligado(casa):
    db = casa["db"]
    _cfg(db)
    _entrada(db, "qual o horário?", meta_id="wamid.antes", quando="2026-10-26T08:00:00")
    modelo = Modelo({"acao": "responder", "tipo": "duvida",
                     "resposta": "Das 8 às 17 horas."})
    r = _rodar(db, casa["pasta"], conversar=modelo)
    assert r["conversas"] == [] and modelo.chamadas == []


# ---------------------------------------------- os quatro casos


def test_duvida_pelo_texto_base_sai_com_rodape_e_fica_registrada(casa):
    db = casa["db"]
    _cfg(db)
    cid = _entrada(db, "Bom dia, qual o horário de vocês?", meta_id="wamid.d1")
    modelo = Modelo({"acao": "responder", "tipo": "duvida",
                     "resposta": "Atendemos de segunda a sexta, das 8 às 17 horas.",
                     "setor": "ATENDIMENTO", "motivo": "horário"})
    graph = Graph()
    r = _rodar(db, casa["pasta"], conversar=modelo, http_post=graph)
    assert r["conversas"][0]["caso"] == AT.CASO_DUVIDA
    assert len(graph.enviados) == 1
    corpo = graph.enviados[0]["payload"]["text"]["body"]
    assert "das 8 às 17 horas" in corpo and "Resposta automática" in corpo
    chamada = modelo.chamadas[0]
    assert chamada["finalidade"] == "wa_atendente" and chamada["mascarado"] is True
    assert TEXTO_BASE.strip().splitlines()[0] in chamada["sistema"]
    saida = _um(db, "SELECT * FROM wa_mensagem WHERE conversa_id=%s AND direcao='out'",
                (cid,))
    assert saida["autor"] == AT.AUTOR_IA and saida["meta_id"] == "wamid.out-1"
    reg = _um(db, "SELECT * FROM wa_ia_registro WHERE conversa_id=%s", (cid,))
    assert reg["enviado"] == 1 and reg["caso"] == AT.CASO_DUVIDA
    assert reg["tokens_entrada"] == 1000 and reg["custo_usd"] == pytest.approx(0.00125)
    assert "horário" in reg["lido"]
    entrada = _um(db, "SELECT ia_situacao FROM wa_mensagem WHERE meta_id='wamid.d1'")
    assert entrada["ia_situacao"] == SCH.IA_RESPONDIDA


def test_resposta_com_numero_inventado_nao_sai_e_passa_para_pessoa(casa):
    db = casa["db"]
    _cfg(db)
    cid = _entrada(db, "abre sábado?", meta_id="wamid.d2")
    modelo = Modelo({"acao": "responder", "tipo": "duvida",
                     "resposta": "Sim, sábado das 9 às 12."})
    graph = Graph()
    _rodar(db, casa["pasta"], conversar=modelo, http_post=graph)
    assert graph.enviados == []
    c = _um(db, "SELECT modo, setor FROM wa_conversa WHERE id=%s", (cid,))
    assert c["modo"] == SCH.MODO_PESSOA and c["setor"] == "ATENDIMENTO"
    reg = _um(db, "SELECT * FROM wa_ia_registro WHERE conversa_id=%s", (cid,))
    assert reg["caso"] == AT.CASO_PASSAGEM and "texto-base" in reg["motivo"]


def _tabela_de_teste(db):
    with db.transaction() as con:
        bd = banco(con)
        bd.escrever("""INSERT INTO cx_vigencias (codigo, descricao, vigente, inicio,
                           importado_em) VALUES (990001, 'Tabela de teste', 1,
                           '2026-01-01', '2026-01-01') ON CONFLICT DO NOTHING""")
        bd.escrever("""INSERT INTO cx_servicos (codigo, codigo_tj, descricao, ativo)
                       VALUES (990001, '99.9.1', 'Ato de teste', 1)
                       ON CONFLICT DO NOTHING""")
        bd.escrever("""INSERT INTO cx_servico_valores (servico, vigencia, emolumentos,
                           ferc, femp, fadep, ferrfis, total)
                       VALUES (990001, 990001, '10,00', '1,00', '0,50', '0,50',
                               '0,00', '12,00') ON CONFLICT DO NOTHING""")


def test_valor_sai_do_calculo_da_casa_como_estimativa(casa):
    import ato_selado as ATO
    from caixa_schema import reais
    db = casa["db"]
    _tabela_de_teste(db)
    _cfg(db, **{SCH.CHAVE_VALORES: "99.9.1 | Ato de teste"})
    _entrada(db, "quanto custa o ato de teste?", meta_id="wamid.v1")
    modelo = Modelo({"acao": "responder", "tipo": "valor", "valor_id": 1,
                     "resposta": ""})
    graph = Graph()
    _rodar(db, casa["pasta"], conversar=modelo, http_post=graph)
    corpo = graph.enviados[0]["payload"]["text"]["body"]
    with db.connect() as con:
        conta = ATO.calcular_custas(con, servico=990001, data=AGORA[:10])
    assert "ESTIMATIVA" in corpo
    assert f"R$ {reais(conta['total_devido_centavos'])}" in corpo
    with db.connect() as con:
        assert "Ato de teste" in AT.instrucao(AT.configuracao(con))


def test_valor_fora_da_lista_passa_para_pessoa(casa):
    db = casa["db"]
    _cfg(db, **{SCH.CHAVE_VALORES: ""})
    cid = _entrada(db, "quanto custa uma escritura?", meta_id="wamid.v2")
    graph = Graph()
    _rodar(db, casa["pasta"], conversar=Modelo({"acao": "responder", "tipo": "valor",
                                                 "valor_id": 7}), http_post=graph)
    assert graph.enviados == []
    assert _um(db, "SELECT modo FROM wa_conversa WHERE id=%s", (cid,))["modo"] == "pessoa"


def test_andamento_so_com_numero_e_codigo_e_sem_ia(casa, portal):
    db = casa["db"]
    _cfg(db)
    cid = _entrada(db, "protocolo 12345 código ABC123", meta_id="wamid.a1")
    modelo, graph = Modelo({"acao": "pessoa"}), Graph()
    r = _rodar(db, casa["pasta"], conversar=modelo, http_post=graph)
    assert r["conversas"][0]["caso"] == AT.CASO_ANDAMENTO
    assert modelo.chamadas == [], "o andamento não passa pelo modelo"
    corpo = graph.enviados[0]["payload"]["text"]["body"]
    assert "em análise" in corpo and "Previsão: 30/10/2026" in corpo
    reg = _um(db, "SELECT lido, respondido FROM wa_ia_registro WHERE conversa_id=%s",
              (cid,))
    assert "ABC123" not in reg["lido"], "o código não fica no registro"
    assert portal == [("12345", "ABC123")]


def test_identificacao_errada_nao_diz_qual_errou_e_tem_limite(casa, portal):
    db = casa["db"]
    _cfg(db)
    wa = "5599900000077"
    textos = []
    for n in range(AT.TENTATIVAS_POR_DIA):
        errado = ("protocolo 99999 código ABC123" if n % 2 == 0
                  else "protocolo 12345 código ZZZ999")
        _entrada(db, errado, meta_id=f"wamid.e{n}", wa_id=wa)
        graph = Graph()
        _rodar(db, casa["pasta"], http_post=graph)
        textos.append(graph.enviados[0]["payload"]["text"]["body"])
    assert len(set(textos)) == 1, "número inexistente e código errado respondem igual"
    assert AT.TEXTO_NAO_CONFERE in textos[0]
    cid = _entrada(db, "protocolo 12345 código ABC123", meta_id="wamid.e-ultima", wa_id=wa)
    graph = Graph()
    _rodar(db, casa["pasta"], http_post=graph)
    assert graph.enviados == []
    assert _um(db, "SELECT modo FROM wa_conversa WHERE id=%s", (cid,))["modo"] == "pessoa"
    assert len(portal) == AT.TENTATIVAS_POR_DIA, "a sexta tentativa nem consulta"


def test_sem_o_modulo_do_portal_o_andamento_passa_para_pessoa(casa, monkeypatch):
    db = casa["db"]
    _cfg(db)
    monkeypatch.setitem(sys.modules, "acompanhamento_cliente", None)
    cid = _entrada(db, "protocolo 12345 código ABC123", meta_id="wamid.sem")
    graph = Graph()
    _rodar(db, casa["pasta"], http_post=graph)
    assert graph.enviados == []
    reg = _um(db, "SELECT motivo FROM wa_ia_registro WHERE conversa_id=%s", (cid,))
    assert "não está instalada" in reg["motivo"]


def test_pedir_andamento_sem_codigo_recebe_o_jeito_de_pedir(casa):
    db = casa["db"]
    _cfg(db)
    _entrada(db, "meu protocolo já está pronto?", meta_id="wamid.p1")
    modelo, graph = Modelo({"acao": "pessoa"}), Graph()
    _rodar(db, casa["pasta"], conversar=modelo, http_post=graph)
    assert modelo.chamadas == []
    assert AT.TEXTO_PEDE_IDENTIFICACAO in graph.enviados[0]["payload"]["text"]["body"]


# ---------------------------------------------- o que passa para pessoa


def test_protesto_passa_para_o_setor_sem_subir_a_ia(casa):
    db = casa["db"]
    _cfg(db)
    cid = _entrada(db, "recebi uma intimação de protesto", meta_id="wamid.s1")
    modelo, graph = Modelo({"acao": "responder"}), Graph()
    _rodar(db, casa["pasta"], conversar=modelo, http_post=graph)
    assert modelo.chamadas == [] and graph.enviados == []
    c = _um(db, "SELECT modo, setor FROM wa_conversa WHERE id=%s", (cid,))
    assert (c["modo"], c["setor"]) == ("pessoa", "PROTESTO")
    ev = _um(db, "SELECT * FROM wa_evento WHERE conversa_id=%s AND tipo=%s",
             (cid, FILA.EV_PASSAGEM))
    assert ev["para_setor"] == "PROTESTO" and ev["por"] == "atendente com IA"


def test_com_o_aviso_ligado_o_cliente_sabe_da_passagem(casa):
    db = casa["db"]
    _cfg(db, **{SCH.CHAVE_IA_AVISO_PASSAGEM: "1"})
    _entrada(db, "quero falar com uma pessoa", meta_id="wamid.s2")
    graph = Graph()
    _rodar(db, casa["pasta"], http_post=graph)
    assert "Atendimento (balcão)" in graph.enviados[0]["payload"]["text"]["body"]


def test_dado_pessoal_nao_sobe(casa):
    db = casa["db"]
    _cfg(db)
    cid = _entrada(db, "meu CPF é 123.456.789-00, qual o horário?", meta_id="wamid.s3")
    modelo = Modelo({"acao": "responder"})
    _rodar(db, casa["pasta"], conversar=modelo)
    assert modelo.chamadas == []
    reg = _um(db, "SELECT lido, motivo FROM wa_ia_registro WHERE conversa_id=%s", (cid,))
    assert "123.456.789-00" not in (reg["lido"] or "")
    assert "dado pessoal" in reg["motivo"]


def test_conversa_com_pessoa_nao_recebe_ia_e_devolver_religa(casa):
    db = casa["db"]
    _cfg(db)
    cid = _entrada(db, "qual o horário?", meta_id="wamid.h1")
    with db.transaction() as con:
        FILA.passar_para_pessoa(con, cid, motivo="teste", por="beatriz", quando=CHEGOU)
    modelo = Modelo({"acao": "responder", "tipo": "duvida", "resposta": "Das 8 às 17."})
    r = _rodar(db, casa["pasta"], conversar=modelo)
    assert r["conversas"][0]["caso"] == "com_pessoa" and modelo.chamadas == []
    with db.transaction() as con:
        FILA.devolver_a_ia(con, cid, por="beatriz", quando=AGORA)
    _entrada(db, "e o endereço?", meta_id="wamid.h2", quando="2026-10-26T09:40:00")
    _rodar(db, casa["pasta"], conversar=Modelo({"acao": "responder", "tipo": "duvida",
                                                 "resposta": "Rua Exemplo, 100."}))
    assert _um(db, "SELECT count(*) AS n FROM wa_mensagem WHERE conversa_id=%s "
                   "AND autor='ia'", (cid,))["n"] == 1


def test_duas_rodadas_nao_respondem_a_mesma_pergunta(casa):
    db = casa["db"]
    _cfg(db)
    _entrada(db, "qual o horário?", meta_id="wamid.r1")
    modelo = Modelo({"acao": "responder", "tipo": "duvida", "resposta": "Das 8 às 17."})
    graph = Graph()
    _rodar(db, casa["pasta"], conversar=modelo, http_post=graph)
    _rodar(db, casa["pasta"], conversar=modelo, http_post=graph)
    assert len(graph.enviados) == 1 and len(modelo.chamadas) == 1


def test_envio_que_falha_passa_para_pessoa(casa):
    db = casa["db"]
    _cfg(db)
    cid = _entrada(db, "qual o horário?", meta_id="wamid.r2")
    _rodar(db, casa["pasta"], http_post=Graph(status=400),
           conversar=Modelo({"acao": "responder", "tipo": "duvida",
                             "resposta": "Das 8 às 17."}))
    assert _um(db, "SELECT modo FROM wa_conversa WHERE id=%s", (cid,))["modo"] == "pessoa"
    reg = _um(db, "SELECT enviado, erro FROM wa_ia_registro WHERE conversa_id=%s", (cid,))
    assert reg["enviado"] == 0 and reg["erro"]


# ---------------------------------------------- o áudio


def _audio(wa_id, meta_id):
    return {"from": wa_id, "id": meta_id, "type": "audio",
            "audio": {"id": "midia-teste-1", "mime_type": "audio/ogg; codecs=opus"}}


def test_audio_e_baixado_transcrito_registrado_e_respondido(casa):
    db = casa["db"]
    _cfg(db, **{SCH.CHAVE_AUDIO_LIGADO: "1"})
    PROV.gravar_chave(casa["pasta"], "gpt", "sk-teste-0123456789abcdef")
    cid = _entrada(db, "", meta_id="wamid.au1", msg=_audio("5599900000055", "wamid.au1"))
    m = _um(db, "SELECT tipo, midia_id FROM wa_mensagem WHERE meta_id='wamid.au1'")
    assert (m["tipo"], m["midia_id"]) == ("audio", "midia-teste-1")
    chamadas = []

    def https(host, metodo, caminho, corpo=None, cabecalhos=None, prazo=60):
        chamadas.append(host)
        if host == "graph.facebook.com":
            return 200, json.dumps({"url": "https://lookaside.fbsbx.com/media?mid=1",
                                    "mime_type": "audio/ogg; codecs=opus"}).encode()
        if host == "lookaside.fbsbx.com":
            return 200, b"OggS-audio-falso"
        if host == "api.openai.com":
            assert b'name="model"' in corpo and b"OggS-audio-falso" in corpo
            return 200, json.dumps({"text": "qual o horário de vocês?",
                                    "duration": 30}).encode()
        raise AssertionError(host)
    modelo = Modelo({"acao": "responder", "tipo": "duvida", "resposta": "Das 8 às 17."})
    graph = Graph()
    r = _rodar(db, casa["pasta"], conversar=modelo, http_post=graph, https=https)
    assert r["audios"] == 1
    assert chamadas == ["graph.facebook.com", "lookaside.fbsbx.com", "api.openai.com"]
    m = _um(db, "SELECT transcricao FROM wa_mensagem WHERE meta_id='wamid.au1'")
    assert m["transcricao"] == "qual o horário de vocês?"
    reg = _um(db, "SELECT * FROM wa_ia_registro WHERE conversa_id=%s AND caso=%s",
              (cid, AT.CASO_AUDIO))
    assert reg["segundos_audio"] == 30 and reg["custo_usd"] == pytest.approx(0.003)
    assert "horário" in modelo.chamadas[0]["conversa"][0]["texto"]
    assert len(graph.enviados) == 1
    assert "audio" in [e["etiqueta"] for e in _ler(
        db, "SELECT etiqueta FROM wa_etiqueta WHERE conversa_id=%s", (cid,))]


def test_midia_fora_da_meta_nao_leva_o_token(casa):
    enviados = []

    def https(host, metodo, caminho, corpo=None, cabecalhos=None, prazo=60):
        enviados.append(host)
        return 200, json.dumps({"url": "https://fora.exemplo.invalid/x"}).encode()
    with pytest.raises(TRANSC.TranscricaoErro):
        TRANSC.baixar_audio("token", "midia-1", https=https)
    assert enviados == ["graph.facebook.com"]


def test_audio_desligado_nao_transcreve(casa):
    db = casa["db"]
    _cfg(db)
    _entrada(db, "", meta_id="wamid.au2", msg=_audio("5599900000056", "wamid.au2"))
    graph = Graph()
    r = _rodar(db, casa["pasta"], http_post=graph)
    assert r["audios"] == 0
    reg = _um(db, "SELECT motivo FROM wa_ia_registro ORDER BY id DESC LIMIT 1")
    assert "sem texto" in reg["motivo"]


# ---------------------------------------------- a fila: etiquetas, setor e prazo


def test_varias_etiquetas_setor_transferencia_e_prazo(casa):
    db = casa["db"]
    cid = _entrada(db, "preciso de certidão", meta_id="wamid.f-1")
    with db.connect() as con:
        assert [e["etiqueta"] for e in FILA.etiquetas(con, cid)] == ["certidao"]
    with db.transaction() as con:
        assert FILA.por_etiqueta(con, cid, "Urgente Hoje", por="beatriz", quando=AGORA)
        assert not FILA.por_etiqueta(con, cid, "urgente_hoje", por="beatriz", quando=AGORA)
        assert FILA.tirar_etiqueta(con, cid, "certidao", por="beatriz", quando=AGORA)
        FILA.transferir(con, cid, "RI", por="beatriz", nota="é matrícula", quando=AGORA)
        with pytest.raises(ValueError):
            FILA.transferir(con, cid, "NAO_EXISTE", quando=AGORA)
    with db.connect() as con:
        assert [e["etiqueta"] for e in FILA.etiquetas(con, cid)] == ["urgente_hoje"]
        ev = [e for e in FILA.eventos(con, cid) if e["tipo"] == FILA.EV_TRANSFERENCIA][0]
        assert (ev["de_setor"], ev["para_setor"]) == ("ATENDIMENTO", "RI")
        fila = FILA.listar(con, agora="2026-10-26T10:15:00", setor="RI")
        assert [c["id"] for c in fila] == [cid]
        assert fila[0]["esperando_min"] == 45 and fila[0]["vencida"] is True
        assert FILA.listar(con, agora=AGORA, etiqueta="urgente_hoje")[0]["id"] == cid
        p = FILA.painel(con, agora="2026-10-26T10:15:00")
    ri = [s for s in p["setores"] if s["setor"] == "RI"][0]
    assert ri["abertas"] == 1 and ri["vencidas"] == 1


def test_painel_separa_a_resposta_da_ia_da_da_pessoa(casa):
    db = casa["db"]
    cid = _entrada(db, "oi", meta_id="wamid.t1", quando="2026-10-26T09:00:00")
    with db.transaction() as con:
        WA.gravar_saida(con, cid, "olá", "wamid.o1", autor="ia",
                        agora="2026-10-26T09:02:00")
    _entrada(db, "e agora?", meta_id="wamid.t2", quando="2026-10-26T09:10:00")
    with db.transaction() as con:
        WA.gravar_saida(con, cid, "resposta", "wamid.o2", autor="BEATRIZ EXEMPLO",
                        agora="2026-10-26T09:30:00")
        p = FILA.painel(con, agora=AGORA)
    at = [s for s in p["setores"] if s["setor"] == "ATENDIMENTO"][0]
    assert (at["media_ia"], at["respostas_ia"]) == (2, 1)
    assert (at["media_pessoa"], at["respostas_pessoa"]) == (20, 1)


def test_conversa_resolvida_que_volta_volta_para_a_ia(casa):
    db = casa["db"]
    cid = _entrada(db, "oi", meta_id="wamid.v-1")
    with db.transaction() as con:
        FILA.passar_para_pessoa(con, cid, por="carla", quando=CHEGOU)
        WA.resolver(con, cid, agora=CHEGOU)
    _entrada(db, "voltei", meta_id="wamid.v-2", quando="2026-10-26T09:50:00")
    assert _um(db, "SELECT modo FROM wa_conversa WHERE id=%s", (cid,))["modo"] is None


# ---------------------------------------------- as telas


def _token(html):
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado
    return achado.group(1)


def _entrar(app, usuario):
    c = app.test_client()
    c.post("/login", data={"username": usuario, "password": SENHA,
                           "csrf_token": _token(c.get("/login").get_data(as_text=True))})
    return c


def test_telas_do_atendente_do_painel_e_da_conversa(casa):
    db, app = casa["db"], casa["app"]
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    db.create_user("beatriz", "BEATRIZ EXEMPLO", SENHA, "USER")
    cid = _entrada(db, "qual o horário?", meta_id="wamid.tela1")
    admin = _entrar(app, "mario")
    html = admin.get("/whatsapp/atendente").get_data(as_text=True)
    assert "DESLIGADO" in html and "áudio inteiro" in html
    r = admin.post("/whatsapp/atendente", data={
        "csrf_token": _token(html), "ia_ligada": "1", "texto_base": TEXTO_BASE,
        "valores": "", "provedor": "claude", "prazo_minutos": "20"})
    assert r.status_code in (302, 303)
    with db.connect() as con:
        cfg = AT.configuracao(con)
    assert cfg["ia_ligada"] and cfg["texto_base_por"] == "MARIO EXEMPLO DOS SANTOS"
    assert cfg["ia_ligada_em"] and cfg["prazo_minutos"] == 20
    balcao = _entrar(app, "beatriz")
    tok = _token(balcao.get("/whatsapp/atendente").get_data(as_text=True))
    assert balcao.post("/whatsapp/atendente", data={"csrf_token": tok}).status_code == 403
    assert balcao.get("/whatsapp/painel").status_code == 200
    tela = balcao.get(f"/whatsapp/{cid}").get_data(as_text=True)
    tok = _token(tela)
    assert balcao.post(f"/whatsapp/{cid}/etiqueta",
                       data={"csrf_token": tok, "etiqueta": "retorno"}).status_code == 302
    assert balcao.post(f"/whatsapp/{cid}/transferir",
                       data={"csrf_token": tok, "setor": "NOTAS"}).status_code == 302
    assert balcao.post(f"/whatsapp/{cid}/assumir",
                       data={"csrf_token": tok}).status_code == 302
    assert balcao.post(f"/whatsapp/{cid}/passar",
                       data={"csrf_token": tok, "setor": "NOTAS"}).status_code == 302
    assert balcao.post(f"/whatsapp/{cid}/devolver",
                       data={"csrf_token": tok}).status_code == 302
    c = _um(db, "SELECT setor, modo, responsavel_id FROM wa_conversa WHERE id=%s", (cid,))
    assert c["setor"] == "NOTAS" and c["modo"] == "ia" and c["responsavel_id"]
    tela = balcao.get(f"/whatsapp/{cid}").get_data(as_text=True)
    assert "retorno" in tela and "Histórico da conversa" in tela
    lista = balcao.get("/whatsapp?setor=NOTAS").get_data(as_text=True)
    assert "retorno" in lista


def test_a_tela_nao_mostra_pedaco_da_chave(casa):
    db, app = casa["db"], casa["app"]
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    PROV.gravar_chave(casa["pasta"], "claude", "sk-ant-segredo-XYZW9876")
    html = _entrar(app, "mario").get("/whatsapp/atendente").get_data(as_text=True)
    assert "9876" not in html and "segredo" not in html


# ------------------------------- o teto e o tamanho (revisão de segurança, 26/10/2026)


def _usos_do_audio(db, quantos):
    """`quantos` transcrições já registradas hoje (o dia de AGORA)."""
    import ia_uso as USO
    with db.transaction() as con:
        USO.init_ia_schema(con)
        banco(con).escrever(
            """INSERT INTO ia_uso (quando, modulo, finalidade, resultado)
               SELECT %s, 'wa_atendente', %s, 'ok' FROM generate_series(1, %s)""",
            (AGORA, AT.FINALIDADE_AUDIO, int(quantos)))


def _https_do_audio(chamadas):
    def https(host, metodo, caminho, corpo=None, cabecalhos=None, prazo=60):
        chamadas.append(host)
        if host == "graph.facebook.com":
            return 200, json.dumps({"url": "https://lookaside.fbsbx.com/media?mid=1",
                                    "mime_type": "audio/ogg; codecs=opus"}).encode()
        if host == "lookaside.fbsbx.com":
            return 200, b"OggS-audio-falso"
        raise AssertionError(host)
    return https


def test_audio_passado_o_teto_do_dia_nao_e_baixado_nem_transcrito(casa):
    """O achado ALTA: `wa_audio` já em 200 hoje → nenhum `https` chamado."""
    import ia_catalogo as CAT
    db = casa["db"]
    _cfg(db, **{SCH.CHAVE_AUDIO_LIGADO: "1"})
    _usos_do_audio(db, CAT.teto_diario(AT.FINALIDADE_AUDIO))
    _entrada(db, "", meta_id="wamid.au7", msg=_audio("5599900000057", "wamid.au7"))
    chamadas, transcritos = [], []
    r = _rodar(db, casa["pasta"], https=_https_do_audio(chamadas),
               transcrever=lambda *a, **k: transcritos.append(a) or {})
    assert r["audios"] == 0 and chamadas == [] and transcritos == []
    m = _um(db, "SELECT transcricao FROM wa_mensagem WHERE meta_id='wamid.au7'")
    assert m["transcricao"] is None                     # nem chegou a ser pego


def test_o_teto_do_audio_vale_no_meio_da_rodada(casa, monkeypatch):
    import ia_catalogo as CAT
    db = casa["db"]
    monkeypatch.setitem(CAT.CHAMADAS_POR_DIA, AT.FINALIDADE_AUDIO, 1)
    _cfg(db, **{SCH.CHAVE_AUDIO_LIGADO: "1"})
    _entrada(db, "", meta_id="wamid.au8", msg=_audio("5599900000058", "wamid.au8"))
    _entrada(db, "", meta_id="wamid.au9", msg=_audio("5599900000059", "wamid.au9"))
    chamadas = []

    def transcrever(pasta, audio, mime, **k):
        _usos_do_audio(db, 1)                # o transporte de verdade registra o uso
        return {"texto": "qual o horário?", "segundos": 10, "custo_usd": 0.001,
                "modelo": "falso-1"}
    r = _rodar(db, casa["pasta"], https=_https_do_audio(chamadas), transcrever=transcrever)
    assert r["audios"] == 1
    assert chamadas == ["graph.facebook.com", "lookaside.fbsbx.com"]


def test_mensagem_longa_demais_vai_para_pessoa_sem_subir(casa):
    db = casa["db"]
    _cfg(db)
    longa = "Bom dia, tenho uma dúvida sobre o atendimento. " * 60
    assert len(longa) > AT.TAMANHO_DA_PERGUNTA
    _entrada(db, longa, meta_id="wamid.longa1", wa_id="5599900000060")
    modelo = Modelo({"acao": "responder", "tipo": "duvida", "resposta": "Das 8 às 17."})
    _rodar(db, casa["pasta"], conversar=modelo)
    assert modelo.chamadas == []
    reg = _um(db, "SELECT motivo, enviado FROM wa_ia_registro ORDER BY id DESC LIMIT 1")
    assert "longa demais" in reg["motivo"] and not reg["enviado"]


def test_o_pedido_ao_modelo_leva_um_limite_de_envio_proprio(casa):
    db = casa["db"]
    _cfg(db)
    _entrada(db, "qual o horário de vocês?", meta_id="wamid.lim1", wa_id="5599900000061")
    modelo = Modelo({"acao": "responder", "tipo": "duvida", "resposta": "Das 8 às 17."})
    _rodar(db, casa["pasta"], conversar=modelo)
    limite = modelo.chamadas[0]["limite_de_envio"]
    assert limite < PROV.LIMITE_DE_ENVIO
    assert limite == len(modelo.chamadas[0]["sistema"].encode("utf-8")) + AT.FOLGA_DO_PEDIDO
