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
    assert "não decide o ato" in texto
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
    assert "Atendimento do cartório" not in corpo
    assert "peço ao escrevente" not in corpo
    assert "não registra empresa" in modelo.chamadas[0]["sistema"]
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
    assert "Vou passar ao escrevente de Registro Civil." in corpo
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
    assert "passo para o escrevente" in graph.enviados[0]["payload"]["text"]["body"]
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


def test_a_chave_vazia_liga_o_escrevente_e_o_zero_fica_desligado(casa):
    db = casa["db"]
    _cfg(db)
    with db.connect() as con:
        assert AT.configuracao(con)["escrevente"] is False
    with db.transaction() as con:
        assert AT.adotar_escrevente_se_vazio(con) is True
    with db.connect() as con:
        assert AT.configuracao(con)["escrevente"] is True
    with db.transaction() as con:
        assert AT.adotar_escrevente_se_vazio(con) is False
        AT.gravar_configuracao(
            con, {"ia_ligada": "1", "provedor": "claude"},
            por="MARIO EXEMPLO", agora=AGORA)
    assert _um(db, "SELECT valor FROM wa_config WHERE chave=%s",
               (SCH.CHAVE_IA_ESCREVENTE,))["valor"] == "0"
    with db.connect() as con:
        assert AT.configuracao(con)["escrevente"] is False
    with db.transaction() as con:
        assert AT.adotar_escrevente_se_vazio(con) is False


def test_titulo_de_dominio_e_do_registro_de_imoveis():
    import wa_fila as FILA
    setores = [s for s, _m, _p in FILA.setores_pelo_texto(
        "quero registrar um título de domínio do INCRA")]
    assert "RI" in setores


def test_o_encaminhamento_leva_o_fato_e_nao_repete_o_cardapio():
    decisao = {
        "caso": AT.CASO_PEDIDO, "razao": AT.RAZAO_INSISTENCIA,
        "motivo": "o cliente seguiu escrevendo depois de 10 respostas automáticas",
        "resposta": AT.TEXTO_PEDIDO,
        "pedido": {"setor": "RI", "servico": "registro_imovel",
                   "resumo": "o cliente seguiu escrevendo depois de 10 respostas automáticas"},
    }
    assunto = "quero registrar um título de domínio do INCRA no imóvel"
    ido = AT.completar_encaminhamento(decisao, assunto=assunto, ultimo="")
    assert ido["pedido"]["resumo"].startswith("quero registrar")
    assert "Me diga o serviço" not in ido["resposta"]
    assert ido["resposta"] == "Vou passar ao escrevente de Registro de Imóveis."
    de_novo = AT.completar_encaminhamento(
        {"caso": AT.CASO_PEDIDO, "razao": AT.RAZAO_INSISTENCIA,
         "resposta": AT.TEXTO_PEDIDO,
         "pedido": {"setor": "RI", "servico": "registro_imovel",
                    "resumo": "o cliente seguiu escrevendo depois de 10 respostas automáticas"}},
        assunto=assunto, ultimo=ido["resposta"])
    assert de_novo["resposta"] == "" and de_novo["ja_avisado"] is True


def test_a_resposta_do_modelo_fica_e_o_audio_sem_texto_pede_para_escrever():
    boa = {
        "caso": AT.CASO_PEDIDO, "razao": AT.RAZAO_PEDIDO,
        "resposta": "O escrevente vê o título e te diz o caminho.",
        "pedido": {"setor": "RI", "servico": "registro_imovel",
                   "resumo": "Quer registrar título de domínio."},
    }
    ficou = AT.completar_encaminhamento(boa, assunto="outra coisa qualquer aqui", ultimo="")
    assert ficou["resposta"].startswith("O escrevente vê")
    assert ficou["pedido"]["resumo"].startswith("Quer registrar")
    audio = {
        "caso": AT.CASO_PEDIDO, "razao": AT.RAZAO_FALHA,
        "motivo": "mensagem sem texto (anexo, ou áudio sem transcrição)",
        "resposta": AT.TEXTO_PEDIDO,
        "pedido": {"setor": "ATENDIMENTO", "servico": "orientacao",
                   "resumo": "mensagem sem texto"},
    }
    pedido = AT.completar_encaminhamento(audio, assunto="", ultimo="")
    assert "ouvir" in pedido["resposta"].lower()
    assert "Me diga o serviço" not in pedido["resposta"]


def test_falar_com_o_tabeliao_abre_pedido_da_gestao():
    assert AT.pede_o_tabeliao("quero falar com o tabelião")
    assert AT.pede_o_tabeliao("me passa para o oficial")
    assert not AT.pede_o_tabeliao("quero falar com o escrevente")
    assert not AT.pede_o_tabeliao("o tabelião assinou a escritura")
    assert not AT.pede_o_tabeliao("quero uma certidão do oficial de registro")
    d = AT._virar_pedido({
        "passar": "GESTAO", "razao": AT.RAZAO_PEDIU_PESSOA,
        "resumo": AT.RESUMO_DO_TABELIAO, "caso": "duvida", "resposta": "",
    })
    assert d["caso"] == AT.CASO_PEDIDO
    assert d["pedido"]["setor"] == "GESTAO"
    assert d["pedido"]["servico"] == "orientacao"
    assert d["resposta"] == "Vou avisar o tabelião."
    assert "Gestão" not in d["resposta"]
    repetido = AT.completar_encaminhamento(
        d, assunto="quero falar com o tabelião e registrar o imóvel",
        ultimo="Vou avisar o tabelião.")
    assert repetido["resposta"] == "" and repetido["ja_avisado"] is True
    assert repetido["pedido"]["setor"] == "GESTAO"
    texto = AT._relato_da_tarefa(AT.RESUMO_DO_TABELIAO, "quero registrar o imóvel " * 20)
    assert texto.startswith("Pediu para falar com o tabelião.")
    assert "registrar o imóvel" in texto
    assert "Vou avisar o tabelião." in AT.instrucao_do_escrevente(
        {"texto_base": "", "valores": []}, "")


def test_falar_com_o_escrevente_abre_o_pedido_do_setor():
    assert AT.pede_pessoa("quero falar com o escrevente")
    assert not AT.pede_o_tabeliao("quero falar com o escrevente")
    d = AT._virar_pedido({
        "passar": "RI", "razao": AT.RAZAO_PEDIU_PESSOA,
        "resumo": "Pediu para falar com o escrevente.",
    })
    assert d["pedido"]["setor"] == "RI"
    assert d["resposta"] == "Vou passar ao escrevente de Registro de Imóveis."
    assert "Pode falar comigo" not in d["resposta"]


def test_o_historico_guarda_o_numero_da_matricula_e_abre_tarefa(casa, monkeypatch):
    db = casa["db"]
    _ligar(db)
    _fixar_conhecimento(monkeypatch)
    cid = _entrada(db, "quero registrar um título de domínio do INCRA no imóvel",
                   meta_id="wamid.e10")
    _rodar(db, casa["pasta"], conversar=Modelo(
        {"acao": "pedir", "setor": "RI", "servico": "registro_imovel",
         "resposta": "Vou ver com o escrevente do imóvel.",
         "resumo": "Quer registrar título de domínio do INCRA."}), http_post=Graph())
    pedido = _um(db, "SELECT * FROM wa_pedido WHERE conversa_id=%s", (cid,))
    tarefa = _um(db, "SELECT * FROM tasks WHERE source_ref=%s",
                 (f"wa_pedido:{pedido['id']}",))
    assert tarefa["source_type"] == "WHATSAPP"
    assert "INCRA" in (tarefa["description"] or "")
    _entrada(db, "o número da matrícula é 45 e a nacionalidade pode ser a da opção",
             meta_id="wamid.e11", quando=AGORA)
    modelo = Modelo(texto="sem json")
    graph = Graph()
    _rodar(db, casa["pasta"], conversar=modelo, http_post=graph)
    assert modelo.chamadas and modelo.chamadas[0]["maximo_de_saida"] == AT.SAIDA_DO_ESCREVENTE
    subiu = modelo.chamadas[0]["conversa"][0]["texto"]
    assert "45" in subiu
    assert "HISTÓRICO É O ATENDIMENTO" in modelo.chamadas[0]["sistema"]
    corpo = graph.enviados[-1]["payload"]["text"]["body"]
    assert "Me diga o serviço" not in corpo
    assert "Registro de Imóveis" in corpo
    pedido = _um(db, "SELECT resumo FROM wa_pedido WHERE conversa_id=%s", (cid,))
    assert "45" in pedido["resumo"] or "nacionalidade" in pedido["resumo"]
    assert "formato" not in pedido["resumo"]
