"""O atendimento do escrevente no WhatsApp (10/11/2026).

A IA responde com o ofício, a base da casa e a norma, e quando a pessoa quer
o serviço feito abre um pedido para o escrevente. A conversa não passa para
pessoa. Sem a chave `ia_escrevente`, o comportamento de antes continua — isso
está em `test_wa_atendente` e `test_wa_triagem`.

Nada aqui fala com provedor nem com a Meta. O conhecimento injetado nos casos
de decisão é fixo, para o número permitido ser o do teste; um caso lê a base
de verdade.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

import wa_atendente as AT  # noqa: E402
import wa_conhecimento as CONHEC  # noqa: E402
import wa_pedido as PEDIDO  # noqa: E402
import wa_schema as SCH  # noqa: E402
from test_wa_atendente import (AGORA, CHEGOU, SENHA, TEXTO_BASE, Graph, Modelo,  # noqa: E402
                               _cfg, _entrada, _entrar, _rodar, _token, _um, casa)

CONHECIMENTO = ("A apresentação do título não se recusa por falta de informação, "
                "art. 12 da lei de registros.")


def _ligar(db, **extra):
    _cfg(db, **{SCH.CHAVE_IA_ESCREVENTE: "1", **extra})


def _fixar_conhecimento(monkeypatch, texto=CONHECIMENTO):
    monkeypatch.setattr(AT.CONHEC, "para_o_atendimento", lambda *a, **k: texto)


def test_o_conhecimento_de_verdade_traz_o_oficio_e_a_norma():
    texto = CONHEC.para_o_atendimento("certidão de nascimento", setor="RCPN")
    assert "escrevente" in texto.lower()
    assert "Registro Civil" in texto
    assert "não decidem o ato" in texto
    # A base normativa entra com a citação. Sem ela, a IA não tem lei para citar.
    assert "=== A NORMA PERTINENTE" in texto
    assert "art." in texto.lower()


def test_pedir_abre_pedido_e_a_conversa_fica_com_a_ia(casa, monkeypatch):
    db = casa["db"]
    _ligar(db)
    _fixar_conhecimento(monkeypatch)
    cid = _entrada(db, "quero protestar um título", meta_id="wamid.e1")
    modelo = Modelo({"acao": "pedir", "setor": "PROTESTO", "servico": "protesto",
                     "resposta": "O escrevente do protesto faz o apontamento, art. 12.",
                     "resumo": "Quer apontar um título."})
    graph = Graph()
    _rodar(db, casa["pasta"], conversar=modelo, http_post=graph)
    assert len(modelo.chamadas) == 1
    assert "OFÍCIO" in modelo.chamadas[0]["sistema"]
    assert "art. 12" in modelo.chamadas[0]["sistema"]
    corpo = graph.enviados[0]["payload"]["text"]["body"]
    assert "art. 12" in corpo and "99" not in corpo
    c = _um(db, "SELECT modo, setor FROM wa_conversa WHERE id=%s", (cid,))
    assert (c["modo"] or SCH.MODO_IA) == SCH.MODO_IA
    assert c["setor"] == "PROTESTO"
    pedido = _um(db, "SELECT * FROM wa_pedido WHERE conversa_id=%s", (cid,))
    assert pedido["servico"] == "protesto" and pedido["situacao"] == PEDIDO.ABERTO
    assert pedido["resumo"] == "Quer apontar um título."
    assert _um(db, "SELECT count(*) AS n FROM wa_evento WHERE conversa_id=%s AND tipo=%s",
               (cid, "pedido_escrevente"))["n"] == 1


def test_numero_inventado_nao_sai_e_o_pedido_ainda_abre(casa, monkeypatch):
    db = casa["db"]
    _ligar(db)
    _fixar_conhecimento(monkeypatch)
    cid = _entrada(db, "quanto tempo leva a certidão?", meta_id="wamid.e2")
    modelo = Modelo({"acao": "pedir", "setor": "RCPN", "servico": "certidao_civil",
                     "resposta": "Fica pronto em 99 dias.",
                     "resumo": "Quer certidão; a IA inventou prazo."})
    graph = Graph()
    _rodar(db, casa["pasta"], conversar=modelo, http_post=graph)
    corpo = graph.enviados[0]["payload"]["text"]["body"]
    assert "99" not in corpo
    assert "Anotei o seu pedido" in corpo
    assert _um(db, "SELECT situacao FROM wa_pedido WHERE conversa_id=%s",
               (cid,))["situacao"] == PEDIDO.ABERTO


def test_encaminhar_antigo_neste_modo_tambem_e_pedido(casa, monkeypatch):
    db = casa["db"]
    _ligar(db)
    _fixar_conhecimento(monkeypatch)
    cid = _entrada(db, "recebi uma intimação de protesto", meta_id="wamid.e3")
    _rodar(db, casa["pasta"], conversar=Modelo(
        {"acao": "encaminhar", "setor": "PROTESTO", "razao": "caso_concreto",
         "resumo": "Recebeu intimação."}))
    c = _um(db, "SELECT modo FROM wa_conversa WHERE id=%s", (cid,))
    assert (c["modo"] or SCH.MODO_IA) == SCH.MODO_IA
    assert _um(db, "SELECT count(*) AS n FROM wa_pedido WHERE conversa_id=%s",
               (cid,))["n"] == 1


def test_dado_pessoal_nao_sobe_e_o_pedido_nao_repete_o_cpf(casa, monkeypatch):
    db = casa["db"]
    _ligar(db)
    _fixar_conhecimento(monkeypatch)
    cid = _entrada(db, "meu CPF é 123.456.789-00, quero uma certidão", meta_id="wamid.e4")
    modelo = Modelo({"acao": "responder", "resposta": "Das 8 às 17."})
    graph = Graph()
    _rodar(db, casa["pasta"], conversar=modelo, http_post=graph)
    assert modelo.chamadas == []
    corpo = graph.enviados[0]["payload"]["text"]["body"]
    assert "123.456.789-00" not in corpo
    reg = _um(db, "SELECT lido, motivo FROM wa_ia_registro WHERE conversa_id=%s", (cid,))
    assert "123.456.789-00" not in (reg["lido"] or "")
    pedido = _um(db, "SELECT resumo FROM wa_pedido WHERE conversa_id=%s", (cid,))
    assert "123.456.789-00" not in pedido["resumo"]
    assert (_um(db, "SELECT modo FROM wa_conversa WHERE id=%s", (cid,))["modo"]
            or SCH.MODO_IA) == SCH.MODO_IA


def test_quem_pede_pessoa_continua_com_a_ia(casa, monkeypatch):
    db = casa["db"]
    _ligar(db)
    _fixar_conhecimento(monkeypatch)
    cid = _entrada(db, "quero falar com uma pessoa", meta_id="wamid.e5")
    modelo = Modelo({"acao": "encaminhar"})
    graph = Graph()
    _rodar(db, casa["pasta"], conversar=modelo, http_post=graph)
    assert modelo.chamadas == []
    assert "Este WhatsApp é o atendimento" in graph.enviados[0]["payload"]["text"]["body"]
    assert _um(db, "SELECT count(*) AS n FROM wa_pedido WHERE conversa_id=%s", (cid,))["n"] == 0
    assert (_um(db, "SELECT modo FROM wa_conversa WHERE id=%s", (cid,))["modo"]
            or SCH.MODO_IA) == SCH.MODO_IA


def test_o_mesmo_servico_nao_abre_dois_pedidos(casa, monkeypatch):
    db = casa["db"]
    _ligar(db)
    _fixar_conhecimento(monkeypatch)
    cid = _entrada(db, "quero reconhecer firma", meta_id="wamid.e6")
    modelo = Modelo({"acao": "pedir", "setor": "NOTAS", "servico": "firma",
                     "resposta": "O escrevente reconhece a firma no balcão, art. 12.",
                     "resumo": "Primeira frase."})
    graph = Graph()
    _rodar(db, casa["pasta"], conversar=modelo, http_post=graph)
    _entrada(db, "é da firma mesmo", meta_id="wamid.e7", quando=AGORA)
    modelo.decisao = {"acao": "pedir", "setor": "NOTAS", "servico": "firma",
                      "resposta": "Sigo com o reconhecimento de firma, art. 12.",
                      "resumo": "Segunda frase."}
    _rodar(db, casa["pasta"], conversar=modelo, http_post=graph)
    assert _um(db, "SELECT count(*) AS n FROM wa_pedido WHERE conversa_id=%s",
               (cid,))["n"] == 1
    assert _um(db, "SELECT resumo FROM wa_pedido WHERE conversa_id=%s",
               (cid,))["resumo"] == "Segunda frase."


def test_a_tela_lista_o_pedido_e_o_escrevente_marca_feito(casa, monkeypatch):
    db, app = casa["db"], casa["app"]
    _ligar(db)
    _fixar_conhecimento(monkeypatch)
    cid = _entrada(db, "quero uma certidão de nascimento", meta_id="wamid.e8")
    _rodar(db, casa["pasta"], conversar=Modelo(
        {"acao": "pedir", "setor": "RCPN", "servico": "certidao_civil",
         "resposta": "O escrevente emite a certidão, art. 12.",
         "resumo": "Certidão de nascimento."}))
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    db.create_user("beatriz", "BEATRIZ EXEMPLO", SENHA, "USER")
    admin = _entrar(app, "mario")
    html = admin.get("/whatsapp/atendente").get_data(as_text=True)
    assert "Atendimento do escrevente" in html
    assert "Pedidos para o escrevente" in html
    assert "Certidão de nascimento." in html
    assert "norma(s)" in html
    beatriz = _entrar(app, "beatriz")
    tela = beatriz.get(f"/whatsapp/{cid}").get_data(as_text=True)
    assert "data-wa-pedidos" in tela and "Certidão de nascimento." in tela
    pedido = _um(db, "SELECT id FROM wa_pedido WHERE conversa_id=%s", (cid,))
    r = beatriz.post(f"/whatsapp/pedido/{pedido['id']}/feito", data={
        "csrf_token": _token(tela), "volta": str(cid)})
    assert r.status_code in (302, 303)
    assert _um(db, "SELECT situacao, feito_por FROM wa_pedido WHERE id=%s",
               (pedido["id"],))["situacao"] == PEDIDO.FEITO
    assert "BEATRIZ EXEMPLO" in _um(
        db, "SELECT feito_por FROM wa_pedido WHERE id=%s", (pedido["id"],))["feito_por"]
    de_novo = admin.get("/whatsapp/atendente").get_data(as_text=True)
    assert "Certidão de nascimento." not in de_novo


def test_sem_texto_base_a_duvida_ainda_sobe_quando_o_escrevente_esta_ligado(casa, monkeypatch):
    db = casa["db"]
    _ligar(db, **{SCH.CHAVE_TEXTO_BASE: ""})
    _fixar_conhecimento(monkeypatch)
    _entrada(db, "como funciona o registro de imóvel?", meta_id="wamid.e9")
    modelo = Modelo({"acao": "responder", "tipo": "duvida",
                     "resposta": "O escrevente lavra no registro, art. 12."})
    graph = Graph()
    _rodar(db, casa["pasta"], conversar=modelo, http_post=graph)
    assert len(modelo.chamadas) == 1
    assert "art. 12" in graph.enviados[0]["payload"]["text"]["body"]
