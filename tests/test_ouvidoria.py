"""A OUVIDORIA E A PESQUISA DE SATISFAÇÃO (26/10/2026).

O QUE SE PROVA AQUI
    - a manifestação ganha número contínuo por ano, prazo pela configuração e
      uma TAREFA para o responsável, sem a identificação de quem se manifestou;
    - anônima não grava identificação, nem a que a tela tenha mandado;
    - a identificação só abre na ficha, para quem pode, e cada abertura fica na
      auditoria; na denúncia, nem o relato aparece para o balcão;
    - responder conclui a tarefa; encaminhar leva a tarefa junto;
    - o AUDITOR vê e não grava; o prazo só o oficial configura;
    - a página da pesquisa nasce FECHADA, grava sem login quando aberta, não
      guarda hora nem aparelho, aceita o convite assinado (uma avaliação por
      protocolo) e ignora o convite adulterado;
    - o convite de protocolo vai SÓ AO CLIENTE (decisão do oficial, 26/10): a
      tela do balcão nunca mostra o link nem o QR com token; o convite entra na
      fila de envio para o telefone e o e-mail do protocolo; protocolo sem
      contato não gera convite;
    - o prazo padrão da ouvidoria é de 30 dias (decisão do oficial, 26/10);
    - os números aparecem no painel do oficial, e não no do balcão.

Equipe fictícia (mario, beatriz, carla). Nada de dado real de pessoa.
"""
from __future__ import annotations

import re
import sys
from datetime import date, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ouvidoria as OU                       # noqa: E402
import satisfacao as SAT                     # noqa: E402
from bd_nativo import banco                  # noqa: E402

SENHA = "Senha#12345"
NOME_FICTICIO = "FULANO DE TAL EXEMPLO"
DOC_FICTICIO = "000.000.000-00"


def _entrar(casa, usuario: str, nome: str, papel: str):
    casa["db"].create_user(usuario, nome, SENHA, papel)
    c = casa["app"].test_client()
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"',
                      c.get("/login").get_data(as_text=True)).group(1)
    c.post("/login", data={"username": usuario, "password": SENHA, "csrf_token": token},
           follow_redirects=True)
    return c


def _token(c) -> str:
    with c.session_transaction() as s:
        return s["csrf_token"]


def _post(c, url: str, **dados):
    return c.post(url, data={"csrf_token": _token(c), **dados})


def _id(casa, usuario: str) -> int:
    with casa["db"].connect() as con:
        return int(banco(con).um("SELECT id FROM users WHERE username=%s", (usuario,))["id"])


def _uma(casa, sql: str, args=()):
    with casa["db"].connect() as con:
        return banco(con).um(sql, args)


def _equipe(casa):
    oficial = _entrar(casa, "mario", "MARIO EXEMPLO DOS SANTOS", "ADMIN")
    balcao = _entrar(casa, "beatriz", "BEATRIZ EXEMPLO", "USER")
    auditor = _entrar(casa, "carla", "CARLA EXEMPLO", "AUDITOR")
    return oficial, balcao, auditor


def _registrar(casa, c, responsavel: str = "beatriz", **extra):
    dados = {"tipo": "RECLAMACAO", "canal": "BALCAO", "setor": "RCPN",
             "responsavel_id": str(_id(casa, responsavel)),
             "assunto": "Demora na certidão", "relato": "A pessoa esperou duas horas no balcão.",
             "nome": NOME_FICTICIO, "documento": DOC_FICTICIO, "contato": "(00) 0000-0000"}
    dados.update(extra)
    return _post(c, "/administrativo/ouvidoria", **dados)


# ------------------------------------------------------------------ ouvidoria


def test_registrar_abre_tarefa_sem_a_identificacao(cg_casa):
    oficial, balcao, _ = _equipe(cg_casa)
    r = _registrar(cg_casa, balcao)
    assert r.status_code == 302
    m = _uma(cg_casa, "SELECT * FROM ou_manifestacoes")
    hoje = date.today()
    assert m["numero"] == f"OUV-{hoje.year}/0001"
    assert m["prazo"] == (hoje + timedelta(days=OU.PRAZO_PADRAO_DIAS)).isoformat()
    assert m["nome"] == NOME_FICTICIO
    t = _uma(cg_casa, "SELECT * FROM tasks WHERE id=%s", (m["tarefa_id"],))
    assert t["source_type"] == "OUVIDORIA"
    assert t["source_ref"] == f"OUVIDORIA:{m['id']}"
    assert t["assigned_user_id"] == _id(cg_casa, "beatriz")
    assert t["due_date"] == m["prazo"]
    assert NOME_FICTICIO not in (t["description"] or "")
    assert DOC_FICTICIO not in (t["description"] or "")
    # a segunda do ano toma o número seguinte
    _registrar(cg_casa, balcao, assunto="Outra")
    assert _uma(cg_casa, "SELECT MAX(numero) n FROM ou_manifestacoes")["n"].endswith("/0002")


def test_anonima_nao_grava_identificacao(cg_casa):
    _, balcao, _ = _equipe(cg_casa)
    _registrar(cg_casa, balcao, anonima="1")
    m = _uma(cg_casa, "SELECT * FROM ou_manifestacoes")
    assert m["anonima"] == 1
    assert (m["nome"], m["documento"], m["contato"]) == ("", "", "")


def test_recusa_sem_relato_e_sem_tipo(cg_casa):
    _, balcao, _ = _equipe(cg_casa)
    _registrar(cg_casa, balcao, relato="curto")
    _registrar(cg_casa, balcao, tipo="")
    assert _uma(cg_casa, "SELECT COUNT(*) n FROM ou_manifestacoes")["n"] == 0


def test_identificacao_so_abre_na_ficha_e_fica_na_auditoria(cg_casa):
    oficial, balcao, auditor = _equipe(cg_casa)
    _registrar(cg_casa, oficial, responsavel="mario")
    mid = _uma(cg_casa, "SELECT id FROM ou_manifestacoes")["id"]
    assert NOME_FICTICIO not in oficial.get("/administrativo/ouvidoria").get_data(as_text=True)
    ficha = oficial.get(f"/administrativo/ouvidoria/{mid}").get_data(as_text=True)
    assert NOME_FICTICIO not in ficha and "Mostrar a identificação" in ficha
    aberta = oficial.get(f"/administrativo/ouvidoria/{mid}?identificacao=1").get_data(as_text=True)
    assert NOME_FICTICIO in aberta
    assert _uma(cg_casa, "SELECT COUNT(*) n FROM audit_logs WHERE action='OUVIDORIA_IDENTIFICACAO_VISTA'")["n"] == 1
    # o balcão que não é o responsável não vê, nem pedindo
    for c in (balcao, auditor):
        txt = c.get(f"/administrativo/ouvidoria/{mid}?identificacao=1").get_data(as_text=True)
        assert NOME_FICTICIO not in txt and DOC_FICTICIO not in txt


def test_denuncia_reserva_o_teor(cg_casa):
    oficial, balcao, auditor = _equipe(cg_casa)
    _registrar(cg_casa, oficial, responsavel="mario", tipo="DENUNCIA",
               assunto="Cobrança indevida", relato="Relato reservado da denúncia, com detalhes.")
    m = _uma(cg_casa, "SELECT * FROM ou_manifestacoes")
    t = _uma(cg_casa, "SELECT * FROM tasks WHERE id=%s", (m["tarefa_id"],))
    assert "Cobrança indevida" not in t["description"]
    for c in (balcao, auditor):
        assert "Relato reservado" not in c.get(f"/administrativo/ouvidoria/{m['id']}").get_data(as_text=True)
        assert "Cobrança indevida" not in c.get("/administrativo/ouvidoria").get_data(as_text=True)
    assert "Relato reservado" in oficial.get(f"/administrativo/ouvidoria/{m['id']}").get_data(as_text=True)


def test_responder_conclui_a_tarefa_e_encaminhar_leva_junto(cg_casa):
    oficial, balcao, _ = _equipe(cg_casa)
    _registrar(cg_casa, oficial, responsavel="mario")
    m = _uma(cg_casa, "SELECT * FROM ou_manifestacoes")
    _post(oficial, f"/administrativo/ouvidoria/{m['id']}/encaminhar",
          responsavel_id=str(_id(cg_casa, "beatriz")), motivo="É do setor dela")
    t = _uma(cg_casa, "SELECT * FROM tasks WHERE id=%s", (m["tarefa_id"],))
    assert t["assigned_user_id"] == _id(cg_casa, "beatriz")
    # agora a responsável é ela, e é ela quem responde
    r = _post(balcao, f"/administrativo/ouvidoria/{m['id']}/responder",
              resposta="Pedimos desculpas; a certidão ficou pronta no mesmo dia.")
    assert r.status_code == 302
    m2 = _uma(cg_casa, "SELECT * FROM ou_manifestacoes")
    assert m2["situacao"] == "RESPONDIDA" and m2["respondida_por"] == _id(cg_casa, "beatriz")
    assert _uma(cg_casa, "SELECT status FROM tasks WHERE id=%s", (m["tarefa_id"],))["status"] == "CONCLUIDA"
    # respondida não se responde de novo
    _post(balcao, f"/administrativo/ouvidoria/{m['id']}/responder", resposta="Outra resposta qualquer.")
    assert _uma(cg_casa, "SELECT resposta FROM ou_manifestacoes")["resposta"].startswith("Pedimos")


def test_quem_nao_e_responsavel_nao_trata(cg_casa):
    oficial, balcao, auditor = _equipe(cg_casa)
    _registrar(cg_casa, oficial, responsavel="mario")
    mid = _uma(cg_casa, "SELECT id FROM ou_manifestacoes")["id"]
    assert _post(balcao, f"/administrativo/ouvidoria/{mid}/responder",
                 resposta="Resposta de quem não é o responsável.").status_code == 403
    assert _post(auditor, f"/administrativo/ouvidoria/{mid}/encerrar",
                 motivo="Auditor não encerra nada").status_code == 403


def test_auditor_ve_e_nao_registra(cg_casa):
    _, _, auditor = _equipe(cg_casa)
    assert auditor.get("/administrativo/ouvidoria").status_code == 200
    assert auditor.get("/administrativo/ouvidoria/relatorio").status_code == 200
    assert _registrar(cg_casa, auditor, responsavel="carla").status_code == 403


def test_prazo_configuravel_so_pelo_oficial(cg_casa):
    oficial, balcao, _ = _equipe(cg_casa)
    assert _post(balcao, "/administrativo/ouvidoria/configuracao", prazo_dias="10").status_code == 403
    _post(oficial, "/administrativo/ouvidoria/configuracao", prazo_dias="999")
    assert cg_casa["db"].get_setting(OU.CHAVE_PRAZO, "") == ""
    _post(oficial, "/administrativo/ouvidoria/configuracao", prazo_dias="10")
    _registrar(cg_casa, balcao)
    m = _uma(cg_casa, "SELECT * FROM ou_manifestacoes")
    assert m["prazo_dias"] == 10
    assert m["prazo"] == (date.today() + timedelta(days=10)).isoformat()
    # a tela diz de onde vem o padrão: decisão do oficial (26/10/2026)
    assert "decisão do oficial em 26/10/2026" in \
        oficial.get("/administrativo/ouvidoria").get_data(as_text=True)


def test_o_prazo_padrao_e_de_30_dias(cg_casa):
    """DECISÃO DO OFICIAL EM 26/10/2026: «30 dias». Sem configuração gravada,
    a manifestação nasce com 30 dias corridos de prazo."""
    assert OU.PRAZO_PADRAO_DIAS == 30
    assert OU.prazo_em_dias(cg_casa["db"].get_setting) == 30
    _, balcao, _ = _equipe(cg_casa)
    _registrar(cg_casa, balcao)
    m = _uma(cg_casa, "SELECT * FROM ou_manifestacoes")
    assert m["prazo_dias"] == 30
    assert m["prazo"] == (date.today() + timedelta(days=30)).isoformat()


def test_relatorio_conta_sem_identificar(cg_casa):
    oficial, balcao, _ = _equipe(cg_casa)
    _registrar(cg_casa, balcao)
    _registrar(cg_casa, balcao, tipo="ELOGIO", canal="WHATSAPP", assunto="Elogio ao balcão")
    txt = oficial.get("/administrativo/ouvidoria/relatorio").get_data(as_text=True)
    assert "Elogio" in txt and "WhatsApp" in txt
    assert NOME_FICTICIO not in txt
    with cg_casa["db"].connect() as con:
        r = OU.relatorio(con, de=date.today().isoformat(), ate=date.today().isoformat())
    assert r["total"] == 2 and r["em_aberto"] == 2


# ------------------------------------------------------------------ pesquisa


def _abrir_pagina(casa, oficial):
    _post(oficial, "/administrativo/satisfacao/pagina", aberta="1")
    assert SAT.pagina_aberta(casa["db"].get_setting)


def _anonimo(casa):
    c = casa["app"].test_client()
    c.get("/satisfacao")  # a sessão anônima ganha o token de formulário
    return c


def test_pagina_nasce_fechada_e_so_o_oficial_abre(cg_casa):
    oficial, balcao, _ = _equipe(cg_casa)
    c = _anonimo(cg_casa)
    assert c.get("/satisfacao").status_code == 404
    assert _post(c, "/satisfacao", nota="5").status_code == 404
    assert _post(balcao, "/administrativo/satisfacao/pagina", aberta="1").status_code == 403
    _abrir_pagina(cg_casa, oficial)
    assert c.get("/satisfacao").status_code == 200


def test_avaliacao_anonima_sem_hora_e_sem_aparelho(cg_casa):
    oficial, _, _ = _equipe(cg_casa)
    _abrir_pagina(cg_casa, oficial)
    c = _anonimo(cg_casa)
    r = _post(c, "/satisfacao", nota="4", comentario="Atendimento rápido.")
    assert r.status_code == 200 and "Obrigado" in r.get_data(as_text=True)
    s = _uma(cg_casa, "SELECT * FROM ou_satisfacao")
    assert s["nota"] == 4 and s["dia"] == date.today().isoformat()
    assert s["atendente_id"] is None and s["protocolo_chave"] is None and s["origem"] == "BALCAO"
    assert set(s) == {"id", "dia", "nota", "comentario", "origem", "atendente_id",
                      "atribuicao", "protocolo_chave"}
    assert _post(c, "/satisfacao", nota="9").status_code == 400
    # sem o token de formulário, recusa
    assert c.post("/satisfacao", data={"nota": "5"}).status_code == 400


def test_convite_do_protocolo_vincula_e_vale_uma_vez(cg_casa):
    oficial, balcao, _ = _equipe(cg_casa)
    _abrir_pagina(cg_casa, oficial)
    _protocolo(cg_casa, "2026.10.900", _id(cg_casa, "beatriz"))
    tela = _pedir_convite(balcao, "2026.10.900")
    assert _token_da_tela(tela) is None
    token = _link_do_cliente(cg_casa, "2026.10.900")
    c = _anonimo(cg_casa)
    assert _post(c, "/satisfacao", nota="5", t=token).status_code == 200
    s = _uma(cg_casa, "SELECT * FROM ou_satisfacao")
    assert s["origem"] == "CONVITE" and s["atendente_id"] == _id(cg_casa, "beatriz")
    assert s["atribuicao"] == "RCPN" and s["protocolo_chave"]
    assert "2026.10.900" not in s["protocolo_chave"]
    assert _post(c, "/satisfacao", nota="1", t=token).status_code == 400
    assert "já foi avaliado" in c.get(f"/satisfacao?t={token}").get_data(as_text=True)
    assert _uma(cg_casa, "SELECT COUNT(*) n FROM ou_satisfacao")["n"] == 1
    # o relatório mostra a média por atendente
    txt = oficial.get("/administrativo/satisfacao").get_data(as_text=True)
    assert "BEATRIZ EXEMPLO" in txt and "5.00" in txt


def test_convite_adulterado_entra_sem_vinculo(cg_casa):
    oficial, _, _ = _equipe(cg_casa)
    _abrir_pagina(cg_casa, oficial)
    falso = SAT.assinar_convite("outro-segredo", atendente_id=_id(cg_casa, "mario"))
    c = _anonimo(cg_casa)
    assert _post(c, "/satisfacao", nota="3", t=falso).status_code == 200
    s = _uma(cg_casa, "SELECT * FROM ou_satisfacao")
    assert s["atendente_id"] is None and s["origem"] == "BALCAO"


def test_teto_por_aparelho(cg_casa, monkeypatch):
    import ouvidoria_web
    monkeypatch.setattr(ouvidoria_web, "TETO_POR_APARELHO", 2)
    oficial, _, _ = _equipe(cg_casa)
    _abrir_pagina(cg_casa, oficial)
    c = _anonimo(cg_casa)
    ip = {"REMOTE_ADDR": "10.9.9.9"}
    codigos = [c.post("/satisfacao", data={"csrf_token": _token(c), "nota": "5"},
                      environ_base=ip).status_code for _ in range(3)]
    assert codigos == [200, 200, 429]


# ------------------------------------------------------------------ painel


def test_numeros_no_painel_do_oficial_e_nao_do_balcao(cg_casa):
    oficial, balcao, _ = _equipe(cg_casa)
    _registrar(cg_casa, balcao)
    assert "Ouvidoria e satisfação" in oficial.get("/").get_data(as_text=True)
    assert "Ouvidoria e satisfação" not in balcao.get("/").get_data(as_text=True)
    assert "Ouvidoria e satisfação" in oficial.get("/relatorios").get_data(as_text=True)


# ---------------------------------- o avaliado não avalia a si mesmo (26/10)
#
# Revisão de segurança de 26/10/2026, achado MÉDIO do PR #23: o escrevente
# gerava o convite de QUALQUER protocolo com ele mesmo como atendente — e o
# link do tablet «comigo como atendente» —, e assim avaliava a si mesmo e
# tomava o lugar da avaliação do cliente.


TELEFONE_FICTICIO = "(99) 90000-0000"
EMAIL_FICTICIO = "cliente@exemplo.invalid"


def _protocolo(casa, numero: str, criado_por: int | None, *,
               telefone: str | None = TELEFONE_FICTICIO, email: str | None = EMAIL_FICTICIO):
    with casa["db"].transaction() as con:
        banco(con).escrever(
            "INSERT INTO cx_protocolos (numero, data_abertura, atribuicao, telefone, email, "
            "criado_em, criado_por) VALUES (%s, %s, 'RCPN', %s, %s, %s, %s)",
            (numero, date.today().isoformat(), telefone, email, casa["db"].now(), criado_por))


def _token_da_tela(html: str) -> str | None:
    """Qualquer link de convite (com token) que a tela tenha mostrado."""
    achado = re.search(r"/satisfacao\?t=([^\"&<]+)", html)
    return achado.group(1) if achado else None


def _pedir_convite(c, numero: str) -> str:
    """O escrevente pede o convite: o POST põe na fila e a tela volta."""
    _post(c, "/administrativo/satisfacao/convite", protocolo=numero)
    return c.get(f"/administrativo/satisfacao/convite?protocolo={numero}").get_data(as_text=True)


def _fila(casa, numero: str) -> list[dict]:
    with casa["db"].connect() as con:
        return [dict(x) for x in banco(con).ler(
            "SELECT f.* FROM ou_satisfacao_convites f JOIN cx_protocolos p "
            "ON p.id = f.protocolo_id WHERE p.numero = %s ORDER BY f.id", (numero,))]


def _link_do_cliente(casa, numero: str) -> str:
    """O que o CLIENTE recebe: o envio monta o link na hora, a partir da linha
    da fila (protocolo, atendente, atribuição) — a fila não guarda token."""
    linha = _fila(casa, numero)[0]
    return SAT.assinar_convite(casa["app"].config["SECRET_KEY"],
                               atendente_id=linha["atendente_id"],
                               protocolo_id=linha["protocolo_id"],
                               atribuicao=linha["atribuicao"])


def test_escrevente_nao_gera_convite_do_protocolo_de_outro(cg_casa):
    oficial, balcao, _ = _equipe(cg_casa)
    _abrir_pagina(cg_casa, oficial)
    _protocolo(cg_casa, "2026.10.901", _id(cg_casa, "mario"))
    r = _post(balcao, "/administrativo/satisfacao/convite", protocolo="2026.10.901")
    assert r.status_code in (302, 303)
    tela = balcao.get("/administrativo/satisfacao/convite?protocolo=2026.10.901",
                      follow_redirects=True).get_data(as_text=True)
    assert _token_da_tela(tela) is None
    assert "aberto por outro atendente" in tela
    assert _fila(cg_casa, "2026.10.901") == []


def test_escrevente_nao_gera_convite_de_protocolo_sem_quem_o_abriu(cg_casa):
    oficial, balcao, _ = _equipe(cg_casa)
    _abrir_pagina(cg_casa, oficial)
    _protocolo(cg_casa, "2026.10.902", None)
    _post(balcao, "/administrativo/satisfacao/convite", protocolo="2026.10.902")
    tela = balcao.get("/administrativo/satisfacao/convite?protocolo=2026.10.902").get_data(as_text=True)
    assert _token_da_tela(tela) is None
    assert "não registra quem o atendeu" in tela
    assert _fila(cg_casa, "2026.10.902") == []


def test_oficial_gera_o_convite_de_outrem_com_quem_atendeu_e_nao_com_ele(cg_casa):
    oficial, _, _ = _equipe(cg_casa)
    _abrir_pagina(cg_casa, oficial)
    _protocolo(cg_casa, "2026.10.903", _id(cg_casa, "beatriz"))
    _protocolo(cg_casa, "2026.10.904", None)
    tela = _pedir_convite(oficial, "2026.10.903")
    assert "BEATRIZ EXEMPLO" in tela
    # nem o oficial vê o link: ele vai só ao cliente
    assert _token_da_tela(tela) is None
    assert {x["atendente_id"] for x in _fila(cg_casa, "2026.10.903")} == {_id(cg_casa, "beatriz")}
    c = _anonimo(cg_casa)
    assert _post(c, "/satisfacao", nota="4",
                 t=_link_do_cliente(cg_casa, "2026.10.903")).status_code == 200
    s = _uma(cg_casa, "SELECT * FROM ou_satisfacao ORDER BY id DESC LIMIT 1")
    assert s["atendente_id"] == _id(cg_casa, "beatriz") and s["protocolo_chave"]
    # o do acervo, sem quem o abriu: sai sem atendente
    _pedir_convite(oficial, "2026.10.904")
    assert _post(c, "/satisfacao", nota="2",
                 t=_link_do_cliente(cg_casa, "2026.10.904")).status_code == 200
    s = _uma(cg_casa, "SELECT * FROM ou_satisfacao ORDER BY id DESC LIMIT 1")
    assert s["atendente_id"] is None and s["protocolo_chave"]


def test_link_do_tablet_nao_leva_atendente(cg_casa):
    oficial, balcao, _ = _equipe(cg_casa)
    _abrir_pagina(cg_casa, oficial)
    tela = balcao.get("/administrativo/satisfacao/convite?balcao=1").get_data(as_text=True)
    assert _token_da_tela(tela) is None and "/satisfacao" in tela
    assert "comigo como atendente" not in tela


def test_relatorio_por_atendente_so_conta_o_convite_de_protocolo(cg_casa):
    """O link «com atendente» gerado antes do conserto continua válido por 30
    dias; a avaliação dele não pode entrar na média de ninguém."""
    oficial, _, _ = _equipe(cg_casa)
    _abrir_pagina(cg_casa, oficial)
    antigo = SAT.assinar_convite(cg_casa["app"].config["SECRET_KEY"],
                                 atendente_id=_id(cg_casa, "beatriz"))
    c = _anonimo(cg_casa)
    assert _post(c, "/satisfacao", nota="5", t=antigo).status_code == 200
    with cg_casa["db"].connect() as con:
        r = SAT.relatorio(con, de=date.today().isoformat(), ate=date.today().isoformat())
    assert [a["atendente_id"] for a in r["por_atendente"]] == [None]
    assert "sem vínculo" in r["por_atendente"][0]["nome"]


def test_protocolo_aberto_no_balcao_grava_quem_o_abriu(cg_casa):
    _, balcao, _ = _equipe(cg_casa)
    r = _post(balcao, "/caixa/protocolos", acao="novo", interessado="FULANO DE TAL EXEMPLO",
              telefone="(00) 0000-0000", atribuicao="RCPN")
    assert r.status_code in (302, 303)
    p = _uma(cg_casa, "SELECT criado_por FROM cx_protocolos WHERE interessado = %s",
             ("FULANO DE TAL EXEMPLO",))
    assert p["criado_por"] == _id(cg_casa, "beatriz")


# --------------------------- o link vai só ao cliente (decisão de 26/10/2026)


def test_escrevente_nao_ve_o_link_e_o_convite_vai_para_o_contato_do_protocolo(cg_casa):
    """«Link vai só ao cliente»: o escrevente pede o convite do protocolo que
    abriu; a tela não mostra link nem QR com token — só que o convite foi
    registrado —, e a fila guarda um convite por canal, para o telefone e o
    e-mail DO PROTOCOLO, sem token nenhum."""
    oficial, balcao, _ = _equipe(cg_casa)
    _abrir_pagina(cg_casa, oficial)
    _protocolo(cg_casa, "2026.10.910", _id(cg_casa, "beatriz"))
    antes = balcao.get("/administrativo/satisfacao/convite?protocolo=2026.10.910")
    assert antes.status_code == 200
    assert _token_da_tela(antes.get_data(as_text=True)) is None
    assert _fila(cg_casa, "2026.10.910") == [], "o GET não grava"
    r = _post(balcao, "/administrativo/satisfacao/convite", protocolo="2026.10.910")
    assert r.status_code in (302, 303)
    tela = balcao.get("/administrativo/satisfacao/convite?protocolo=2026.10.910").get_data(as_text=True)
    assert _token_da_tela(tela) is None
    assert "Convite para o cliente registrado em" in tela
    # nem o telefone nem o e-mail do cliente aparecem na tela do balcão
    assert "90000" not in tela and EMAIL_FICTICIO not in tela
    fila = _fila(cg_casa, "2026.10.910")
    assert {(x["canal"], x["destino"]) for x in fila} == {
        ("WHATSAPP", "99900000000"), ("EMAIL", EMAIL_FICTICIO)}
    assert all(x["situacao"] == "NA_FILA" and x["atendente_id"] == _id(cg_casa, "beatriz")
               and x["criado_por"] == _id(cg_casa, "beatriz") for x in fila)
    # a fila não guarda link nem token
    for x in fila:
        assert "satisfacao" not in " ".join(str(v) for v in x.values())
    # o segundo pedido não duplica
    _post(balcao, "/administrativo/satisfacao/convite", protocolo="2026.10.910")
    assert len(_fila(cg_casa, "2026.10.910")) == 2
    # a auditoria leva os canais, e não o contato
    a = _uma(cg_casa, "SELECT details FROM audit_logs WHERE action = %s",
             ("SATISFACAO_CONVITE_NA_FILA",))
    assert a and "WHATSAPP" in str(a["details"]) and EMAIL_FICTICIO not in str(a["details"])
    # o oficial vê, no relatório, quantos esperam
    assert "Convites na fila de envio ao cliente: <strong>2</strong>" in \
        oficial.get("/administrativo/satisfacao").get_data(as_text=True)


def test_protocolo_sem_telefone_nem_email_nao_gera_convite(cg_casa):
    oficial, balcao, _ = _equipe(cg_casa)
    _abrir_pagina(cg_casa, oficial)
    _protocolo(cg_casa, "2026.10.911", _id(cg_casa, "beatriz"), telefone="", email=None)
    tela = balcao.get("/administrativo/satisfacao/convite?protocolo=2026.10.911").get_data(as_text=True)
    assert "não se gera convite para ele" in tela
    assert "Enviar o convite ao cliente" not in tela
    _post(balcao, "/administrativo/satisfacao/convite", protocolo="2026.10.911")
    assert _fila(cg_casa, "2026.10.911") == []
    # telefone sem DDD e e-mail torto também não servem
    _protocolo(cg_casa, "2026.10.912", _id(cg_casa, "beatriz"), telefone="0000-0000",
               email="sem-arroba")
    _post(balcao, "/administrativo/satisfacao/convite", protocolo="2026.10.912")
    assert _fila(cg_casa, "2026.10.912") == []


def test_so_o_canal_que_o_protocolo_tem(cg_casa):
    """Só e-mail no protocolo: o convite vai só por e-mail."""
    oficial, balcao, _ = _equipe(cg_casa)
    _abrir_pagina(cg_casa, oficial)
    _protocolo(cg_casa, "2026.10.913", _id(cg_casa, "beatriz"), telefone=None)
    _pedir_convite(balcao, "2026.10.913")
    assert [(x["canal"], x["destino"]) for x in _fila(cg_casa, "2026.10.913")] == [
        ("EMAIL", EMAIL_FICTICIO)]
