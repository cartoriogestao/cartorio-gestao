"""Os avisos de andamento ao cliente — o sim, os três andamentos, a fila e as telas.

O QUE ESTES TESTES PROVAM
    - sem o consentimento do cliente, nada sai — nem com o andamento de pé;
    - o consentimento grava quem e quando, e desmarcar não apaga;
    - o protesto não aceita consentimento e nunca gera aviso;
    - cada andamento sai UMA vez por canal e destino, pelo e-mail da automação
      (trocado aqui por um falso: nenhum e-mail de verdade sai dos testes);
    - a mensagem leva o número e o andamento, e não o nome nem o documento;
    - sem SMTP o aviso fica PENDENTE_CONFIG e sai quando configurar — se o
      andamento ainda for verdade; se não for, é DESCARTADO;
    - o WhatsApp fica registrado como PENDENTE_CONFIG e nunca é enviado;
    - a exigência, o pronto para retirar e o prazo de N dias úteis;
    - o processo vem pelo catálogo da automação, desligado;
    - as telas abrem, gravam com auditoria, e o AUDITOR não grava.
"""
from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import andamento_avisos as AA  # noqa: E402
import andamento_schema as AS  # noqa: E402
import automacao as AU  # noqa: E402
import automacao_avisos as AV  # noqa: E402
import automacao_processos as PROC  # noqa: E402
import automacao_schema as SCH  # noqa: E402
from bd_nativo import banco  # noqa: E402

SENHA = "Senha#12345"
SEG = datetime(2026, 10, 26, 9, 0)        # uma segunda-feira
EMAIL_CLIENTE = "beatriz.exemplo@exemplo.invalid"
INTERESSADO = "BEATRIZ EXEMPLO DE TESTE"
DOCUMENTO = "000.000.001-91"


@pytest.fixture
def casa(cg_casa, monkeypatch, tmp_path_factory):
    db = cg_casa["db"]
    monkeypatch.setenv("CG_COFRE_AUTOMACAO", str(tmp_path_factory.mktemp("cofre") / "cofre.json"))
    cg_casa["app"].extensions["backup_checked"] = True
    if not db.list_users():
        db.create_user("mario", "Mario Exemplo", SENHA, "ADMIN")
    with db.transaction() as con:
        AU.semear(con, SEG)
    enviados: list[dict] = []
    # NENHUM e-mail de verdade: o envio da automação vira um gravador.
    monkeypatch.setitem(AV.ENVIO, "email", lambda cfg, senha, **k: enviados.append(
        {"para": list(cfg["destinos"]), **k}))
    cg_casa["enviados"] = enviados
    return cg_casa


def _smtp(db):
    with db.transaction() as con:
        SCH.gravar_config(con, SCH.CHAVE_SMTP_HOST, "smtp.exemplo.invalid")
        SCH.gravar_config(con, SCH.CHAVE_SMTP_REMETENTE, "avisos@exemplo.invalid")


def _protocolo(db, numero="2026.10.001", atribuicao="NOTAS", ri_protocolo_id=None) -> int:
    with db.transaction() as con:
        return int(banco(con).escrever(
            """INSERT INTO cx_protocolos (numero, data_abertura, atribuicao, interessado,
                   interessado_documento, telefone, email, situacao, ri_protocolo_id, criado_em)
               VALUES (%s,'2026-10-20',%s,%s,%s,'(99) 99999-0000',%s,'ABERTO',%s,
                       '2026-10-20T10:00:00') RETURNING id""",
            (numero, atribuicao, INTERESSADO, DOCUMENTO, EMAIL_CLIENTE, ri_protocolo_id))[0]["id"])


def _prenotacao(db, numero=900001, limite="2026-11-20", situacao="ABERTO") -> int:
    with db.transaction() as con:
        return int(banco(con).escrever(
            """INSERT INTO ri_protocolos (numero, livro, data_prenotacao, apresentante,
                   apresentante_documento, data_limite, situacao, telefone, email, criado_em)
               VALUES (%s,'1A','2026-10-20',%s,%s,%s,%s,'(99) 99999-0000',%s,
                       '2026-10-20T10:00:00') RETURNING id""",
            (numero, INTERESSADO, DOCUMENTO, limite, situacao, EMAIL_CLIENTE))[0]["id"])


def _nota(db, protocolo_id) -> int:
    with db.transaction() as con:
        banco(con).escrever("UPDATE ri_protocolos SET situacao='DEVOLVIDO' WHERE id=%s",
                            (protocolo_id,))
        return int(banco(con).escrever(
            """INSERT INTO ri_notas_devolutivas (protocolo_id, numero, data_nota, exigencias,
                   situacao, emitida_em) VALUES (%s,1,'2026-10-26','["certidão de ônus"]',
                   'ABERTA','2026-10-26T08:00:00') RETURNING id""", (protocolo_id,))[0]["id"])


def _consentir(db, origem, origem_id, canal=AS.EMAIL):
    with db.transaction() as con:
        return AA.consentir(con, origem, origem_id, canal, quem="Mario Exemplo", agora=SEG)


def _pronto(db, cx_id):
    with db.transaction() as con:
        AA.marcar_pronto(con, cx_id, quem="Mario Exemplo", agora=SEG)


def _rodar(db, tmp_path, quando=SEG, **parametros):
    ctx = PROC.Contexto(db=db, agora=quando, pasta_dados=tmp_path, raiz=RAIZ,
                        processo={"codigo": "AVISOS_ANDAMENTO", "parametros": parametros})
    return AA.rodar(ctx)


def _avisos(db):
    with db.connect() as con:
        return banco(con).ler("SELECT * FROM av_avisos ORDER BY id")


# ------------------------------------------------------------------ o sim do cliente


def test_sem_consentimento_nada_sai(casa, tmp_path):
    db = casa["db"]
    _smtp(db)
    cx = _protocolo(db)
    _pronto(db, cx)
    r = _rodar(db, tmp_path)
    assert r["situacao"] == SCH.OK
    assert _avisos(db) == [] and casa["enviados"] == []


def test_o_consentimento_grava_quem_e_quando_e_desmarcar_nao_apaga(casa):
    db = casa["db"]
    cx = _protocolo(db)
    c = _consentir(db, AS.PROTOCOLO_GERAL, cx)
    assert c["destino"] == EMAIL_CLIENTE and c["registrado_por"] == "Mario Exemplo"
    assert c["registrado_em"].startswith("2026-10-26T09:00")
    assert _consentir(db, AS.PROTOCOLO_GERAL, cx)["id"] == c["id"]      # clique repetido
    with db.transaction() as con:
        AA.revogar(con, AS.PROTOCOLO_GERAL, cx, AS.EMAIL, quem="Beatriz", agora=SEG)
        todos = AA.consentimentos(con, AS.PROTOCOLO_GERAL, cx)
    assert len(todos) == 1 and todos[0]["ativo"] == 0
    assert todos[0]["revogado_por"] == "Beatriz"


def test_sem_endereco_nao_se_consente(casa):
    db = casa["db"]
    cx = _protocolo(db)
    with db.transaction() as con:
        banco(con).escrever("UPDATE cx_protocolos SET email=NULL WHERE id=%s", (cx,))
    with pytest.raises(AA.AndamentoError, match="não tem e-mail"):
        _consentir(db, AS.PROTOCOLO_GERAL, cx)


def test_o_protesto_nao_aceita_consentimento_e_nunca_avisa(casa, tmp_path):
    db = casa["db"]
    _smtp(db)
    cx = _protocolo(db, atribuicao="PROTESTO")
    with pytest.raises(AA.AndamentoError, match="sigilo"):
        _consentir(db, AS.PROTOCOLO_GERAL, cx)
    # nem com um consentimento posto por fora a rodada o considera
    with db.transaction() as con:
        banco(con).escrever(
            """INSERT INTO av_consentimentos (origem, origem_id, canal, destino, ativo,
                   registrado_em) VALUES (%s,%s,'EMAIL',%s,1,'2026-10-26T09:00:00')""",
            (AS.PROTOCOLO_GERAL, cx, EMAIL_CLIENTE))
    _pronto(db, cx)
    _rodar(db, tmp_path)
    assert _avisos(db) == [] and casa["enviados"] == []


# ------------------------------------------------------------------ os andamentos


def test_pronto_para_retirar_sai_uma_vez_e_so_com_o_status(casa, tmp_path):
    db = casa["db"]
    _smtp(db)
    cx = _protocolo(db)
    _consentir(db, AS.PROTOCOLO_GERAL, cx)
    _pronto(db, cx)
    r = _rodar(db, tmp_path)
    assert r["situacao"] == SCH.OK
    assert len(casa["enviados"]) == 1
    email = casa["enviados"][0]
    assert email["para"] == [EMAIL_CLIENTE]
    assert "2026.10.001" in email["assunto"] and "pronto para retirar" in email["assunto"]
    for proibido in (INTERESSADO, DOCUMENTO, "BEATRIZ"):
        assert proibido not in email["corpo"] and proibido not in email["assunto"]
    _rodar(db, tmp_path)                                     # de novo: nada
    assert len(casa["enviados"]) == 1
    (a,) = _avisos(db)
    assert a["situacao"] == AS.ENVIADO and a["evento"] == AS.PRONTO and a["enviado_em"]


def test_sem_smtp_espera_e_sai_quando_configurar(casa, tmp_path):
    db = casa["db"]
    cx = _protocolo(db)
    _consentir(db, AS.PROTOCOLO_GERAL, cx)
    _pronto(db, cx)
    r = _rodar(db, tmp_path)
    assert r["situacao"] == SCH.AVISO and "Configure o SMTP" in r["relato"]
    (a,) = _avisos(db)
    assert a["situacao"] == AS.PENDENTE_CONFIG and casa["enviados"] == []
    _smtp(db)
    _rodar(db, tmp_path)
    assert len(casa["enviados"]) == 1 and _avisos(db)[0]["situacao"] == AS.ENVIADO


def test_o_que_deixou_de_ser_verdade_e_descartado(casa, tmp_path):
    """Aviso atrasado sobre fato que passou é pior que aviso nenhum."""
    db = casa["db"]
    cx = _protocolo(db)
    _consentir(db, AS.PROTOCOLO_GERAL, cx)
    _pronto(db, cx)
    _rodar(db, tmp_path)                                     # sem SMTP: espera
    with db.transaction() as con:
        banco(con).escrever("UPDATE cx_protocolos SET situacao='ENTREGUE' WHERE id=%s", (cx,))
    _smtp(db)
    _rodar(db, tmp_path)
    assert casa["enviados"] == [] and _avisos(db)[0]["situacao"] == AS.DESCARTADO


def test_desmarcar_tira_da_fila(casa, tmp_path):
    db = casa["db"]
    cx = _protocolo(db)
    _consentir(db, AS.PROTOCOLO_GERAL, cx)
    _pronto(db, cx)
    _rodar(db, tmp_path)
    with db.transaction() as con:
        AA.revogar(con, AS.PROTOCOLO_GERAL, cx, AS.EMAIL, quem="Mario Exemplo", agora=SEG)
    _smtp(db)
    _rodar(db, tmp_path)
    assert casa["enviados"] == [] and _avisos(db)[0]["situacao"] == AS.DESCARTADO


def test_o_whatsapp_fica_registrado_e_nunca_sai(casa, tmp_path):
    db = casa["db"]
    _smtp(db)
    cx = _protocolo(db)
    c = _consentir(db, AS.PROTOCOLO_GERAL, cx, canal=AS.WHATSAPP)
    assert c["destino"] == "99999990000"
    _pronto(db, cx)
    r = _rodar(db, tmp_path)
    (a,) = _avisos(db)
    assert a["canal"] == AS.WHATSAPP and a["situacao"] == AS.PENDENTE_CONFIG
    assert "Meta" in a["erro"] and casa["enviados"] == []
    assert r["situacao"] == SCH.OK and "1 por WhatsApp" in r["relato"]


def test_a_exigencia_chega_a_quem_consentiu_no_protocolo_ligado(casa, tmp_path):
    db = casa["db"]
    _smtp(db)
    ri = _prenotacao(db)
    cx = _protocolo(db, atribuicao="RI", ri_protocolo_id=ri)
    _consentir(db, AS.PROTOCOLO_GERAL, cx)
    _nota(db, ri)
    _rodar(db, tmp_path)
    (a,) = _avisos(db)
    assert a["evento"] == AS.EXIGENCIA and a["origem"] == AS.PRENOTACAO
    assert len(casa["enviados"]) == 1
    assert "900001" in casa["enviados"][0]["assunto"]
    assert "exigência" in casa["enviados"][0]["assunto"]
    assert "certidão de ônus" not in casa["enviados"][0]["corpo"]      # o teor não sai


def test_a_exigencia_geral_fora_do_ri_tambem_avisa(casa, tmp_path):
    # 27/10/2026: só a nota devolutiva do RI gerava aviso; a nota de exigência
    # do balcão (aqui, nas Notas) passa a avisar pela leitura única do #39.
    import caixa_exigencia as CXE
    db = casa["db"]
    _smtp(db)
    cx = _protocolo(db, numero="2026.10.077", atribuicao="NOTAS")
    _consentir(db, AS.PROTOCOLO_GERAL, cx)
    with db.transaction() as con:
        CXE.abrir(con, cx, texto="Trazer a certidão de casamento atualizada.",
                  agora="2026-10-26T08:00:00", atribuicao="NOTAS", quem="carla")
    _rodar(db, tmp_path)
    (a,) = _avisos(db)
    assert a["evento"] == AS.EXIGENCIA and a["origem"] == AS.PROTOCOLO_GERAL
    assert len(casa["enviados"]) == 1
    assert "certidão de casamento" not in casa["enviados"][0]["corpo"]  # o teor não sai
    assert "prenotação" not in casa["enviados"][0]["corpo"].lower()    # corpo próprio
    assert "2026.10.077" in casa["enviados"][0]["corpo"]


def test_o_prazo_avisa_a_n_dias_corridos_e_respeita_a_suspensao(casa, tmp_path):
    db = casa["db"]
    _smtp(db)
    perto = _prenotacao(db, numero=900002, limite="2026-10-29")        # 3 dias corridos
    longe = _prenotacao(db, numero=900003, limite="2026-11-27")
    suspensa = _prenotacao(db, numero=900004, limite="2026-10-28")
    with db.transaction() as con:
        banco(con).escrever("""UPDATE ri_protocolos SET prazo_suspenso_desde='2026-10-21',
                                      prazo_suspenso_motivo='DUVIDA' WHERE id=%s""", (suspensa,))
    for p in (perto, longe, suspensa):
        _consentir(db, AS.PRENOTACAO, p)
    _rodar(db, tmp_path, dias_antes=5)
    avisos = _avisos(db)
    assert [a["origem_id"] for a in avisos] == [perto]
    corpo = casa["enviados"][0]["corpo"]
    assert "29/10/2026" in corpo and "faltam 3 dia(s)" in corpo
    # com N = 2, a de 3 dias ainda não estaria na janela
    with db.connect() as con:
        assert not AA.eventos_vigentes(con, hoje=SEG.date(), dias_antes=2,
                                       eventos=[AS.PRAZO])


def test_o_email_que_falhou_tenta_de_novo_ate_o_limite(casa, tmp_path, monkeypatch):
    db = casa["db"]
    _smtp(db)

    def falha(*a, **k):
        raise OSError("servidor fora do ar")
    monkeypatch.setitem(AV.ENVIO, "email", falha)
    cx = _protocolo(db)
    _consentir(db, AS.PROTOCOLO_GERAL, cx)
    _pronto(db, cx)
    rodadas = [_rodar(db, tmp_path, max_tentativas=3) for _ in range(4)]
    (a,) = _avisos(db)
    assert a["situacao"] == AS.FALHOU and a["tentativas"] == 3     # a 4ª não tenta
    assert "servidor fora do ar" in a["erro"]
    assert rodadas[0]["situacao"] == SCH.AVISO and "1 falha(s)" in rodadas[0]["relato"]


# ------------------------------------------------------------------ o processo e o texto


def test_o_processo_vem_pelo_catalogo_e_nasce_desligado(casa):
    with casa["db"].connect() as con:
        p = AU.por_codigo(con, "AVISOS_ANDAMENTO")
    assert p and not p["ativo"] and not p["pode_agir"]
    assert p["alvo"] == "andamento_avisos:rodar"
    assert p["parametros"]["dias_antes"] == AA.DIAS_ANTES_PADRAO
    assert p["agenda"]["intervalo_min"] == 15


def test_o_padrao_de_fabrica_avisa_com_7_dias_corridos(casa):
    """«7 dias corridos» — decisão do oficial em 26/10/2026 (era 5 dias úteis).

    Escrito e NÃO executado nesta máquina (sobrecarga, ordem do oficial).
    """
    from datetime import timedelta
    assert AA.DIAS_ANTES_PADRAO == 7
    hoje = SEG.date()
    a_7 = _prenotacao(casa["db"], numero=900011,
                      limite=(hoje + timedelta(days=7)).isoformat())
    a_8 = _prenotacao(casa["db"], numero=900012,
                      limite=(hoje + timedelta(days=8)).isoformat())
    with casa["db"].connect() as con:
        vig = AA.eventos_vigentes(con, hoje=hoje, eventos=[AS.PRAZO])     # sem dias_antes
    ids = {v["origem_id"] for v in vig.values()}
    assert a_7 in ids and a_8 not in ids
    assert AA._parametros({})[0] == 7


def test_o_texto_da_casa_vale_e_o_ajuste_torto_cai_no_padrao(casa):
    import modelos_da_casa as MOD
    assert AA.conferir(MOD.padrao_de(AA.MODELO)) == ""
    assert "'cpf'" in AA.conferir("===PRONTO===\nOla {cpf}")
    info = {"numero": "2026.10.009", "data_limite": None, "dias": None}
    assunto, corpo = AA.textos(AS.PRONTO, info, {"unit_name": "SERVENTIA DE EXEMPLO"})
    assert assunto == "SERVENTIA DE EXEMPLO: o protocolo nº 2026.10.009 está pronto para retirar"
    assert "Telefone: —" in corpo and "{" not in corpo


# ------------------------------------------------------------------ as telas


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _entrar(casa, usuario, papel):
    from tests.conftest import cg_login
    if usuario != "mario":
        casa["db"].create_user(usuario, f"{usuario.title()} Exemplo", SENHA, papel)
    c = casa["app"].test_client()
    cg_login(c, usuario, SENHA)
    return c


def test_as_telas_marcam_o_consentimento_e_o_pronto_com_auditoria(casa):
    db = casa["db"]
    cx = _protocolo(db)
    c = _entrar(casa, "mario", "ADMIN")
    url = f"/andamento/protocolo-geral/{cx}"
    html = c.get(url).get_data(as_text=True)
    assert "O cliente autorizou" in html and "sem modelo aprovado pela Meta" in html
    r = c.post(url, data={"csrf_token": _token(html), "acao": "consentir", "canal": "EMAIL"})
    assert r.status_code == 302
    r = c.post(url, data={"csrf_token": _token(html), "acao": "pronto"})
    assert r.status_code == 302
    with db.connect() as con:
        assert AA.ativos(con, AS.PROTOCOLO_GERAL, cx)[AS.EMAIL]["registrado_por"]
        assert AA.registro(con, AS.PROTOCOLO_GERAL, cx)["pronto_retirar_em"]
        acoes = {a["action"] for a in banco(con).ler(
            "SELECT action FROM audit_logs WHERE entity_type='PROTOCOLO' AND entity_id=%s",
            (cx,))}
    assert {"ANDAMENTO_CONSENTIR", "ANDAMENTO_PRONTO"} <= acoes
    assert "pronto para retirar" in c.get(f"/caixa/protocolos/{cx}").get_data(as_text=True)
    fila = c.get("/andamento").get_data(as_text=True)
    assert "Avisos de andamento ao cliente" in fila and "desligada" in fila
    assert "Avisos ao cliente (andamento)" in c.get("/").get_data(as_text=True)


def test_a_tela_da_prenotacao_abre_e_o_auditor_nao_grava(casa):
    db = casa["db"]
    ri = _prenotacao(db)
    c = _entrar(casa, "carla", "AUDITOR")
    url = f"/andamento/prenotacao/{ri}"
    html = c.get(url).get_data(as_text=True)
    assert "prenotação" in html.lower()
    r = c.post(url, data={"csrf_token": _token(html), "acao": "consentir", "canal": "EMAIL"})
    assert r.status_code == 403
    with db.connect() as con:
        assert AA.ativos(con, AS.PRENOTACAO, ri) == {}
    assert c.get("/andamento").status_code == 403


# ------------------------------------------- revisão de segurança de 26/10/2026 (M1)
#
# O texto do aviso sai sozinho ao cliente, do remetente da serventia, sem
# ninguém ler antes. Duas travas: só o gestor grava o papel, e o texto não pode
# trazer pagamento, valor, endereço de internet, telefone nem e-mail à mão.


@pytest.mark.parametrize("trecho", [
    "acesse https://exemplo.invalid/pague",
    "veja em www.exemplo.invalid",
    "visite golpe-exemplo.com agora",
    "pague antes no PIX",
    "faça o pagamento antes de retirar",
    "o valor é R$ 50,00",
    "segue o boleto",
    "faça um depósito na conta",
    "faça um deposito na conta",
    "faça uma transferência",
    "ligue (99) 99999-0000",
    "ligue 9999990000",
    "escreva para golpe@exemplo.invalid",
])
def test_o_texto_que_sai_sozinho_nao_traz_pagamento_nem_contato_a_mao(trecho):
    erro = AA.conferir(f"===PRONTO===\nOlá. {trecho}\n{{assinatura}}")
    assert "sai sozinho ao cliente" in erro, trecho


def test_o_padrao_e_os_claros_da_serventia_continuam_valendo():
    import modelos_da_casa as MOD
    assert AA.conferir(MOD.padrao_de(AA.MODELO)) == ""
    assert AA.conferir("===ASSINATURA===\n{serventia}\nTelefone: {telefone} - "
                       "E-mail: {email}") == ""


def test_claro_com_atributo_e_recusado():
    """B3: o `str.format` resolveria `{numero.__class__}`; a régua da casa não deixa."""
    assert AA.conferir("===PRONTO===\nOla {numero.__class__}") != ""


def test_o_ajuste_torto_ja_gravado_nao_sai(casa):
    """O que entrou por fora da conferência é medido de novo na hora de mandar."""
    db = casa["db"]
    with db.transaction() as con:
        banco(con).escrever(
            """INSERT INTO mo_elementos (atribuicao, ato, parte, corpo, ativo,
                   atualizado_em, atualizado_por)
               VALUES ('CAIXA', %s, 'CORPO', %s, 1, '2026-10-26T09:00:00', 'teste')""",
            (AA.MODELO, "===PRONTO===\nPara retirar, pague antes no PIX.\n{assinatura}"))
    info = {"numero": "2026.10.009", "data_limite": None, "dias": None}
    with db.connect() as con:
        _, corpo = AA.textos(AS.PRONTO, info, {"unit_name": "SERVENTIA DE EXEMPLO"}, con)
    assert "PIX" not in corpo and "pronto para ser retirado" in corpo


def test_so_o_gestor_grava_o_papel_que_vai_sozinho_ao_cliente():
    import modelos_da_casa as MOD
    assert AA.MODELO in MOD.PAPEIS_SO_DO_GESTOR
    # o convite da pesquisa também sai sozinho ao cliente (27/10/2026)
    assert "OUVIDORIA_CONVITE_PESQUISA" in MOD.PAPEIS_SO_DO_GESTOR
    assert MOD.recusa_ao_gravar("USER", [AA.MODELO])
    assert MOD.recusa_ao_gravar("AUDITOR", [AA.MODELO])
    assert MOD.recusa_ao_gravar("MANAGER", [AA.MODELO]) == ""
    assert MOD.recusa_ao_gravar("ADMIN", [AA.MODELO]) == ""
    assert MOD.recusa_ao_gravar("USER", ["RI_CABECALHO"]) == ""   # os outros: a régua geral


def _csrf(cliente) -> str:
    with cliente.session_transaction() as s:
        return s["csrf_token"]


def _ajuste_gravado(db) -> str | None:
    with db.connect() as con:
        linha = banco(con).um(
            "SELECT corpo FROM mo_elementos WHERE ato=%s AND parte='CORPO' AND ativo=1",
            (AA.MODELO,))
    return linha["corpo"] if linha else None


def test_o_escrevente_recebe_403_mesmo_se_a_regra_geral_abrir(casa, monkeypatch):
    """A trava do papel vale sozinha: abrir `QUEM_GRAVA` ao USER não a desliga."""
    import modelos_da_casa as MOD
    import modelos_elementos_web as MEW
    import modelos_web as MW
    monkeypatch.setattr(MW, "QUEM_GRAVA", ("ADMIN", "MANAGER", "USER"))
    monkeypatch.setattr(MEW, "QUEM_GRAVA", ("ADMIN", "MANAGER", "USER"))
    c = _entrar(casa, "beatriz", "USER")
    c.get("/modelos")
    corpo = MOD.padrao_de(AA.MODELO).replace("Olá.", "Bom dia.")
    r = c.post("/modelos", data={"csrf_token": _csrf(c), "chave": AA.MODELO,
                                 "corpo": corpo, "acao": "salvar"})
    assert r.status_code == 403 and "só o oficial ou o gerente" in r.get_data(as_text=True)
    # nem pelo submódulo do Caixa, no papel ou na atribuição inteira
    for ato in (AA.MODELO, ""):
        r = c.post("/caixa/modelos", data={"csrf_token": _csrf(c), "ato": ato,
                                           "parte": "ENCERRAMENTO", "corpo": "pague no pix"})
        assert r.status_code == 403
    assert _ajuste_gravado(casa["db"]) is None


def test_o_gerente_grava_o_papel(casa):
    import modelos_da_casa as MOD
    c = _entrar(casa, "carla", "MANAGER")
    c.get("/modelos")
    corpo = MOD.padrao_de(AA.MODELO).replace("Olá.", "Bom dia.")
    r = c.post("/modelos", data={"csrf_token": _csrf(c), "chave": AA.MODELO,
                                 "corpo": corpo, "acao": "salvar"})
    assert r.status_code == 302
    assert "Bom dia." in (_ajuste_gravado(casa["db"]) or "")
