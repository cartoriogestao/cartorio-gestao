"""A FILA DE CORREÇÕES DE OFÍCIO — decisão do oficial, 29/10/2026.

    a leitura do banco fica livre para os robôs e os agentes; a escrita é feita
    apenas pelo sistema, com usuário; correção de ofício vai por uma fila: o
    agente ou a escrevente PROPÕE, o oficial APROVA com afirmação expressa, e
    o SERVIDOR executa.

O QUE ESTES TESTES GUARDAM
    - propor não altera nada fora da fila (nem a prévia, nem a proposta);
    - o robô propõe pela conta dele, e nunca aprova — nem pela rota, nem pelo
      domínio, nem com o papel errado;
    - o MANAGER não aprova;
    - aprovar sem a afirmação expressa é recusado, e nada muda;
    - o «antes» que mudou entre a proposta e a aprovação dá FALHOU, e nada se
      executa; a conferência que não fecha desfaz a execução inteira;
    - cada tipo do catálogo executa e audita — e o caso das duas parcelas do
      mesmo protocolo (29/10/2026) se refaz pela fila, em duas propostas;
    - a pendência que o roteiro do Protesto lê.

NOMES: `mario` é o oficial (ADMIN), `beatriz` a gerente (MANAGER) e `carla` a
escrevente (USER) — sem nome real da equipe. Documentos só da lista dos
fictícios (`tests/fixtures/anti_vazamento/documentos_ficticios.txt`).
"""
from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import correcoes_de_oficio as CDO  # noqa: E402
import identidade_do_robo as IDR  # noqa: E402
import protesto_selo_previo as PSELO  # noqa: E402
from bd_nativo import banco  # noqa: E402

SENHA = "Senha#12345"
AGORA = "2026-10-29T15:00:00"
MOTIVO = ("O pagamento foi lançado no título errado; a Central confirma o outro "
          "título pago desde agosto.")
AFIRMACAO = ("Afirmo, sob minha responsabilidade, que conferi a prova juntada e que "
             "esta correção de ofício deve ser executada como proposta.")
URL = "/administrativo/correcoes-de-oficio"


# ------------------------------------------------------------- a casa


def _pessoas(db) -> dict:
    ids = {
        "mario": db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN"),
        "beatriz": db.create_user("beatriz", "BEATRIZ EXEMPLO", SENHA, "MANAGER"),
        "carla": db.create_user("carla", "CARLA EXEMPLO", SENHA, "USER"),
        "robo": db.create_user("robo_protesto", "Robo do Protesto", SENHA, "USER",
                               eh_robo=1),
    }
    with db.transaction() as con:
        IDR.definir_responsavel_do_robo(con, ids["robo"], ids["mario"])
    return {nome: db.get_user(uid) for nome, uid in ids.items()}


def _titulo(db, situacao: str, numero: str, *, apresentante: str = "237",
            cedente: str = "CREDORA EXEMPLO LTDA") -> int:
    with db.transaction() as con:
        return int(banco(con).escrever(
            """INSERT INTO pt_titulos (especie, numero_titulo, protocolo,
                   valor_centavos, saldo_centavos, situacao, origem, origem_chave,
                   apresentante_codigo, cedente_nome, cedente_uf, criado_em)
               VALUES ('DMI', %s, %s, 10000, 10000, %s, 'CRA', %s, %s, %s, 'MA', %s)
               RETURNING id""",
            (numero, "2610290001", situacao, f"teste:{numero}", apresentante,
             cedente, AGORA))[0]["id"])


def _ato(db, titulo_id: int, tipo: str, *, cancelado: bool = False,
         detalhe: str = "{}", data: str = "2026-08-11") -> int:
    with db.transaction() as con:
        return int(banco(con).escrever(
            """INSERT INTO pt_atos (titulo_id, tipo, data_ato, detalhe_json, origem,
                   cancelado, motivo_cancelamento, criado_em, criado_por)
               VALUES (%s, %s, %s, %s, 'MANUAL', %s, %s, %s, 'MARIO EXEMPLO DOS SANTOS')
               RETURNING id""",
            (titulo_id, tipo, data, detalhe, 1 if cancelado else 0,
             "Selo não emitido: teste." if cancelado else None, AGORA))[0]["id"])


def _devedor(db, titulo_id: int) -> int:
    with db.transaction() as con:
        return int(banco(con).escrever(
            """INSERT INTO pt_devedores (titulo_id, nome, documento_tipo,
                   documento_numero, endereco, cep, cidade, uf)
               VALUES (%s, 'DEVEDOR EXEMPLO', 'CPF', '00000000191', 'RUA ANTIGA, 1',
                       '65000000', 'CIDADE EXEMPLO', 'MA')
               RETURNING id""", (titulo_id,))[0]["id"])


def _um(db, sql: str, args=()) -> dict | None:
    with db.connect() as con:
        return banco(con).um(sql, args)


def _ler(db, sql: str, args=()) -> list[dict]:
    with db.connect() as con:
        return banco(con).ler(sql, args)


def _foto(db) -> str:
    """O Protesto inteiro, para provar que nada mudou."""
    return json.dumps([_ler(db, f"SELECT * FROM {t} ORDER BY id")
                       for t in ("pt_titulos", "pt_atos", "pt_devedores")],
                      default=str, sort_keys=True)


def _propor(db, quem: dict, tipo: str, parametros: dict, **kw) -> dict:
    with db.transaction() as con:
        return CDO.propor(con, tipo=tipo, parametros=parametros, motivo=MOTIVO,
                          quem=quem, agora=AGORA, **kw)


def _aprovar(db, quem: dict, correcao_id: int, *, afirmo=True,
             afirmacao=AFIRMACAO) -> dict:
    with db.transaction() as con:
        return CDO.aprovar(con, correcao_id, aprovador=quem, afirmo=afirmo,
                           afirmacao=afirmacao, agora=AGORA)


def _auditoria(db, acao: str) -> list[dict]:
    return _ler(db, "SELECT * FROM audit_logs WHERE action = %s ORDER BY id", (acao,))


def _situacao(db, titulo_id: int) -> str:
    return _um(db, "SELECT situacao FROM pt_titulos WHERE id = %s", (titulo_id,))["situacao"]


def _pago_sem_pagamento(db, numero: str) -> int:
    """O título que ficou PAGO com o pagamento desfeito pelo selo."""
    t = _titulo(db, "PAGO", numero)
    _ato(db, t, "APONTAMENTO")
    _ato(db, t, "PAGAMENTO", cancelado=True)
    return t


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe o csrf_token"
    return achado.group(1)


def _entrar(cg_casa, login: str):
    from conftest import cg_login
    c = cg_casa["app"].test_client()
    cg_login(c, login, SENHA)
    return c


# ------------------------------------------------------- propor não altera nada


def test_propor_nao_altera_nada_fora_da_fila(cg_casa):
    db = cg_casa["db"]
    p = _pessoas(db)
    t1 = _titulo(db, "PROTESTADO", "P1/1")
    _ato(db, t1, "APONTAMENTO")
    protesto = _ato(db, t1, "PROTESTO")
    t2 = _pago_sem_pagamento(db, "P2/1")
    t3 = _titulo(db, "PAGO", "P3/1")
    _ato(db, t3, "APONTAMENTO")
    pagamento = _ato(db, t3, "PAGAMENTO")
    antes = _foto(db)
    feitas = [
        _propor(db, p["carla"], "PT_ATO_SEM_EFEITO", {"ato_ids": [protesto]}),
        _propor(db, p["carla"], "PT_SITUACAO_SUSTENTADA", {"titulo_ids": [t2]}),
        _propor(db, p["carla"], "PT_CADASTRO_DO_TITULO",
                {"titulo_ids": [t1], "campos": {"cedente_uf": "PI"}}),
        _propor(db, p["carla"], "PT_ATO_DE_CORRECAO",
                {"ato_origem_id": pagamento, "titulo_id": t1}),
    ]
    assert [r["ok"] for r in feitas] == [True] * 4, [r["recusas"] for r in feitas]
    assert _foto(db) == antes, "propor mexeu no Protesto"
    linhas = _ler(db, "SELECT * FROM correcoes_de_oficio ORDER BY id")
    assert [x["situacao"] for x in linhas] == [CDO.PROPOSTA] * 4
    assert all(x["proposta_por"] == "carla" and x["antes_json"] for x in linhas)
    # cada proposta vira tarefa do oficial (o primeiro ADMIN), e é auditada
    tarefas = _ler(db, "SELECT * FROM tasks WHERE source_type = %s ORDER BY id",
                   (CDO.ORIGEM_DA_TAREFA,))
    assert len(tarefas) == 4
    assert {x["assigned_user_id"] for x in tarefas} == {p["mario"]["id"]}
    assert [x["tarefa_id"] for x in linhas] == [x["id"] for x in tarefas]
    assert len(_auditoria(db, CDO.ACAO_PROPOSTA)) == 4
    # o número da proposta vai no «depois» (o motivo no ato), e não o marcador
    depois = json.loads(linhas[0]["depois_json"])
    assert f"nº {linhas[0]['id']}," in depois["atos"][str(protesto)]["motivo_cancelamento"]


def test_a_previa_nao_grava_nem_a_fila(cg_casa):
    db = cg_casa["db"]
    p = _pessoas(db)
    t = _pago_sem_pagamento(db, "PV/1")
    antes = _foto(db)
    with db.connect() as con:
        r = CDO.propor(con, tipo="PT_SITUACAO_SUSTENTADA", parametros={"titulo_ids": [t]},
                       motivo=MOTIVO, quem=p["carla"], agora=AGORA, previa=True)
    assert r["ok"] and r["id"] is None
    assert r["depois"]["titulos"][str(t)]["situacao"] == "APONTADO"
    assert _foto(db) == antes
    assert _um(db, "SELECT count(*) AS n FROM correcoes_de_oficio")["n"] == 0
    assert _um(db, "SELECT count(*) AS n FROM tasks WHERE source_type = %s",
               (CDO.ORIGEM_DA_TAREFA,))["n"] == 0


def test_o_auditor_nao_propoe_e_o_motivo_e_obrigatorio(cg_casa):
    db = cg_casa["db"]
    p = _pessoas(db)
    fiscal = db.get_user(db.create_user("fiscal", "AUDITOR EXEMPLO", SENHA, "AUDITOR"))
    t = _pago_sem_pagamento(db, "PA/1")
    r = _propor(db, fiscal, "PT_SITUACAO_SUSTENTADA", {"titulo_ids": [t]})
    assert not r["ok"] and "confere" in r["recusas"][0]
    with db.transaction() as con:
        r = CDO.propor(con, tipo="PT_SITUACAO_SUSTENTADA", parametros={"titulo_ids": [t]},
                       motivo="curto", quem=p["carla"], agora=AGORA)
    assert not r["ok"] and "motivo" in r["recusas"][0]


# ---------------------------------------------------------- o catálogo é fechado


def test_o_catalogo_e_fechado_e_o_campo_fora_da_lista_e_recusado(cg_casa):
    db = cg_casa["db"]
    p = _pessoas(db)
    t = _titulo(db, "APONTADO", "CF/1")
    r = _propor(db, p["carla"], "SQL_LIVRE", {"sql": "UPDATE pt_titulos SET situacao='PAGO'"})
    assert not r["ok"] and "catálogo" in r["recusas"][0]
    r = _propor(db, p["carla"], "PT_CADASTRO_DO_TITULO",
                {"itens": [{"tabela": "pt_titulos", "id": t,
                            "campos": {"numero_titulo": "X", "situacao": "PAGO"}}]})
    assert not r["ok"] and "lista fechada" in r["recusas"][0]
    r = _propor(db, p["carla"], "PT_CADASTRO_DO_TITULO",
                {"itens": [{"tabela": "users", "id": 1, "campos": {"role": "ADMIN"}}]})
    assert not r["ok"] and "catálogo" in r["recusas"][0]
    assert _um(db, "SELECT count(*) AS n FROM correcoes_de_oficio")["n"] == 0


def test_a_lista_fechada_do_cadastro_nao_tem_o_que_identifica_o_titulo():
    permitidos = {c for lista in CDO.CAMPOS_DO_CADASTRO.values() for c, _ in lista}
    for proibido in ("numero_titulo", "protocolo", "situacao", "valor_centavos",
                     "saldo_centavos", "origem", "origem_chave", "apresentante_codigo",
                     "nome", "documento_numero", "titulo_id", "id"):
        assert proibido not in permitidos, proibido
    assert set(CDO.CATALOGO) == {"PT_ATO_SEM_EFEITO", "PT_SITUACAO_SUSTENTADA",
                                 "PT_CADASTRO_DO_TITULO", "PT_ATO_DE_CORRECAO"}
    assert CDO.TIPOS_QUE_SE_COPIAM == ("PAGAMENTO",)


# ------------------------------------------------------ quem aprova, e quem não


def test_o_robo_propoe_pela_rota_e_nao_aprova(cg_casa):
    db = cg_casa["db"]
    p = _pessoas(db)
    t = _pago_sem_pagamento(db, "PR/1")
    robo = _entrar(cg_casa, "robo_protesto")
    token = _token(robo.get(f"{URL}/nova?tipo=PT_SITUACAO_SUSTENTADA").get_data(as_text=True))
    antes = _foto(db)
    r = robo.post(f"{URL}/propor", headers={"X-CSRF-Token": token},
                  json={"tipo": "PT_SITUACAO_SUSTENTADA", "parametros": {"titulo_ids": [t]},
                        "motivo": MOTIVO})
    assert r.status_code == 200, r.get_data(as_text=True)
    corpo = r.get_json()
    assert corpo["ok"] and corpo["id"]
    linha = _um(db, "SELECT * FROM correcoes_de_oficio WHERE id = %s", (corpo["id"],))
    # a conta de robô se identifica sozinha, e diz a mando de quem
    assert linha["agente"] == "Robo do Protesto"
    assert linha["a_mando_de"] == "MARIO EXEMPLO DOS SANTOS"
    assert linha["proposta_por_id"] == p["robo"]["id"]
    # aprovar e recusar: 403 — fora da lista do robô
    for acao, campos in (("aprovar", {"afirmo": "1", "afirmacao": AFIRMACAO}),
                         ("recusar", {"motivo_da_recusa": "não quero esta correção"})):
        resposta = robo.post(f"{URL}/{corpo['id']}/{acao}",
                             data={"csrf_token": token, **campos})
        assert resposta.status_code == 403, acao
    assert robo.get(URL).status_code == 403
    assert robo.get(f"{URL}/{corpo['id']}").status_code == 200
    assert _um(db, "SELECT situacao FROM correcoes_de_oficio WHERE id = %s",
               (corpo["id"],))["situacao"] == CDO.PROPOSTA
    assert _foto(db) == antes


def test_o_dominio_recusa_o_robo_com_qualquer_papel(cg_casa):
    db = cg_casa["db"]
    p = _pessoas(db)
    t = _pago_sem_pagamento(db, "RD/1")
    feita = _propor(db, p["carla"], "PT_SITUACAO_SUSTENTADA", {"titulo_ids": [t]})
    robo_admin = dict(p["robo"], role="ADMIN")       # o papel errado não salva
    r = _aprovar(db, robo_admin, feita["id"])
    assert not r["ok"] and "robô" in r["recusa"]
    with db.transaction() as con:
        r = CDO.recusar(con, feita["id"], aprovador=robo_admin,
                        motivo="recusa feita pelo robô", agora=AGORA)
    assert not r["ok"] and "robô" in r["recusa"]
    assert _situacao(db, t) == "PAGO"
    assert _um(db, "SELECT situacao FROM correcoes_de_oficio WHERE id = %s",
               (feita["id"],))["situacao"] == CDO.PROPOSTA


def test_o_manager_nao_aprova(cg_casa):
    db = cg_casa["db"]
    p = _pessoas(db)
    t = _pago_sem_pagamento(db, "MG/1")
    feita = _propor(db, p["carla"], "PT_SITUACAO_SUSTENTADA", {"titulo_ids": [t]})
    r = _aprovar(db, p["beatriz"], feita["id"])
    assert not r["ok"] and "ADMIN" in r["recusa"]
    gerente = _entrar(cg_casa, "beatriz")
    token = _token(gerente.get(f"{URL}/{feita['id']}").get_data(as_text=True))
    resposta = gerente.post(f"{URL}/{feita['id']}/aprovar",
                            data={"csrf_token": token, "afirmo": "1", "afirmacao": AFIRMACAO})
    assert resposta.status_code == 403
    assert _situacao(db, t) == "PAGO"


def test_aprovar_sem_afirmacao_e_recusado_e_nada_muda(cg_casa):
    db = cg_casa["db"]
    p = _pessoas(db)
    t = _pago_sem_pagamento(db, "AF/1")
    feita = _propor(db, p["carla"], "PT_SITUACAO_SUSTENTADA", {"titulo_ids": [t]})
    antes = _foto(db)
    for afirmo, texto in ((False, ""), (False, AFIRMACAO), (True, ""),
                          (True, "Afirmo que sim.")):
        r = _aprovar(db, p["mario"], feita["id"], afirmo=afirmo, afirmacao=texto)
        assert not r["ok"] and r["situacao"] is None, (afirmo, texto)
        assert "Afirmo" in r["recusa"]
    assert _foto(db) == antes
    assert _um(db, "SELECT situacao FROM correcoes_de_oficio WHERE id = %s",
               (feita["id"],))["situacao"] == CDO.PROPOSTA
    assert _auditoria(db, CDO.ACAO_EXECUTADA) == []


# --------------------------------------------------- o antes que mudou: FALHOU


def test_o_antes_alterado_entre_a_proposta_e_a_aprovacao_da_falhou(cg_casa):
    db = cg_casa["db"]
    p = _pessoas(db)
    t = _pago_sem_pagamento(db, "AN/1")
    feita = _propor(db, p["carla"], "PT_SITUACAO_SUSTENTADA", {"titulo_ids": [t]})
    # outro balcão relança o pagamento, válido, antes de o oficial decidir
    _ato(db, t, "PAGAMENTO")
    r = _aprovar(db, p["mario"], feita["id"])
    assert not r["ok"] and r["situacao"] == CDO.FALHOU
    assert "mudou" in r["falha"] and "atos_validos" in r["falha"]
    assert _situacao(db, t) == "PAGO", "a fila executou sobre um antes que não era o dela"
    linha = _um(db, "SELECT * FROM correcoes_de_oficio WHERE id = %s", (feita["id"],))
    assert linha["situacao"] == CDO.FALHOU and linha["falha"] == r["falha"]
    assert linha["decidida_por"] == "mario" and linha["afirmacao"]
    assert len(_auditoria(db, CDO.ACAO_FALHOU)) == 1
    assert _auditoria(db, CDO.ACAO_EXECUTADA) == []
    assert _um(db, "SELECT status FROM tasks WHERE id = %s",
               (linha["tarefa_id"],))["status"] == "CONCLUIDA"
    # e não se decide duas vezes
    assert "já foi decidida" in _aprovar(db, p["mario"], feita["id"])["recusa"]


def test_a_conferencia_que_nao_fecha_desfaz_a_execucao(cg_casa, monkeypatch):
    db = cg_casa["db"]
    p = _pessoas(db)
    t = _pago_sem_pagamento(db, "CO/1")
    feita = _propor(db, p["carla"], "PT_SITUACAO_SUSTENTADA", {"titulo_ids": [t]})
    monkeypatch.setattr(CDO.CATALOGO["PT_SITUACAO_SUSTENTADA"], "conferir_execucao",
                        lambda *a, **k: ["forçado pelo teste"])
    r = _aprovar(db, p["mario"], feita["id"])
    assert r["situacao"] == CDO.FALHOU and "conferência" in r["falha"]
    assert _situacao(db, t) == "PAGO", "o SAVEPOINT não desfez a execução"
    assert _auditoria(db, CDO.ACAO_EXECUTADA) == []


# ---------------------------------------------------- cada tipo executa e audita


def test_a_situacao_volta_a_que_os_atos_sustentam(cg_casa):
    """O caso do título que ficou PAGO com o pagamento desfeito pelo selo."""
    db = cg_casa["db"]
    p = _pessoas(db)
    t = _pago_sem_pagamento(db, "ST/1")
    feita = _propor(db, p["carla"], "PT_SITUACAO_SUSTENTADA", {"titulo_ids": [t]})
    r = _aprovar(db, p["mario"], feita["id"])
    assert r["ok"], r
    assert _situacao(db, t) == "APONTADO"
    with db.connect() as con:
        assert PSELO.situacao_sem_ato(con, t) is None
    [executada] = _auditoria(db, CDO.ACAO_EXECUTADA)
    assert (executada["entity_type"], executada["entity_id"]) == ("pt_titulos", t)
    detalhe = json.loads(executada["details"])
    assert detalhe["antes"] == {"situacao": "PAGO"}
    assert detalhe["depois"] == {"situacao": "APONTADO"}
    assert detalhe["correcao_de_oficio"] == feita["id"]
    [afirmada] = _auditoria(db, CDO.ACAO_DA_AFIRMACAO)
    contrato = json.loads(afirmada["details"])
    assert set(contrato) == {"regra", "afirmacao", "o_que_faltava"}
    assert contrato["regra"] == CDO.REGRA_DA_AFIRMACAO
    assert executada["user_id"] == p["mario"]["id"]
    linha = _um(db, "SELECT * FROM correcoes_de_oficio WHERE id = %s", (feita["id"],))
    assert linha["situacao"] == CDO.APROVADA_EXECUTADA
    assert _um(db, "SELECT status FROM tasks WHERE id = %s",
               (linha["tarefa_id"],))["status"] == "CONCLUIDA"


def test_as_duas_parcelas_se_refazem_pela_fila(cg_casa):
    """O caso de 29/10/2026: o pagamento da parcela 1 lançado na parcela 2, e a
    parcela 1 protestada. Pela fila são duas propostas: a cópia do pagamento
    para a parcela 1 (tipo 4) e os três atos sem efeito (tipo 1)."""
    db = cg_casa["db"]
    p = _pessoas(db)
    p1 = _titulo(db, "PROTESTADO", "DP/1")
    _ato(db, p1, "APONTAMENTO")
    intimacao = _ato(db, p1, "INTIMACAO")
    protesto = _ato(db, p1, "PROTESTO")
    p2 = _titulo(db, "PAGO", "DP/2")
    _ato(db, p2, "APONTAMENTO")
    pagamento = _ato(db, p2, "PAGAMENTO", data="2026-08-11",
                     detalhe='{"forma_pagamento": "PIX", "valor_pago_centavos": 10000}')

    copia = _propor(db, p["carla"], "PT_ATO_DE_CORRECAO",
                    {"ato_origem_id": pagamento, "titulo_id": p1})
    assert copia["ok"], copia["recusas"]
    assert any("continua válido" in a for a in copia["avisos"])
    r = _aprovar(db, p["mario"], copia["id"])
    assert r["ok"], r
    novo = _um(db, "SELECT * FROM pt_atos WHERE id = %s", (r["resultado"]["ato_novo_id"],))
    assert (novo["titulo_id"], novo["tipo"], novo["origem"]) == (p1, "PAGAMENTO", "CORRECAO")
    assert str(novo["data_ato"]) == "2026-08-11"
    assert novo["origem_chave"] == f"correcao_de_oficio:{copia['id']}"
    detalhe = json.loads(novo["detalhe_json"])
    assert detalhe["correcao_de"] == pagamento
    assert detalhe["correcao_de_oficio"] == copia["id"]
    assert detalhe["forma_pagamento"] == "PIX"
    assert _situacao(db, p1) == "PAGO"

    sem_efeito = _propor(db, p["carla"], "PT_ATO_SEM_EFEITO",
                         {"ato_ids": [protesto, intimacao, pagamento]})
    assert sem_efeito["ok"], sem_efeito["recusas"]
    r = _aprovar(db, p["mario"], sem_efeito["id"])
    assert r["ok"], r
    for aid in (protesto, intimacao, pagamento):
        ato = _um(db, "SELECT cancelado, motivo_cancelamento FROM pt_atos WHERE id = %s", (aid,))
        assert ato["cancelado"] == 1
        assert ato["motivo_cancelamento"].startswith(
            f"TORNADO SEM EFEITO — correção de ofício nº {sem_efeito['id']},")
    assert _situacao(db, p1) == "PAGO"
    assert _situacao(db, p2) == "APONTADO"
    with db.connect() as con:
        assert PSELO.situacao_sem_ato(con, p1) is None
        assert PSELO.situacao_sem_ato(con, p2) is None
    tocadas = {(a["entity_type"], a["entity_id"]) for a in _auditoria(db, CDO.ACAO_EXECUTADA)}
    assert tocadas == {("pt_atos", novo["id"]), ("pt_titulos", p1),
                       ("pt_atos", protesto), ("pt_atos", intimacao),
                       ("pt_atos", pagamento), ("pt_titulos", p2)}
    assert len(_auditoria(db, CDO.ACAO_DA_AFIRMACAO)) == 2


def test_a_copia_recusa_o_que_nao_tem_precedente(cg_casa):
    db = cg_casa["db"]
    p = _pessoas(db)
    t1 = _titulo(db, "PAGO", "CP/1")
    _ato(db, t1, "APONTAMENTO")
    ja_pago = _ato(db, t1, "PAGAMENTO")
    t2 = _titulo(db, "PROTESTADO", "CP/2")
    protesto = _ato(db, t2, "PROTESTO")
    t3 = _titulo(db, "PAGO", "CP/3")
    _ato(db, t3, "PAGAMENTO")
    # protesto não se copia (livro, folha e selo)
    r = _propor(db, p["carla"], "PT_ATO_DE_CORRECAO",
                {"ato_origem_id": protesto, "titulo_id": t1})
    assert not r["ok"] and "PAGAMENTO" in r["recusas"][0]
    # o destino que já tem pagamento válido não recebe outro
    r = _propor(db, p["carla"], "PT_ATO_DE_CORRECAO",
                {"ato_origem_id": ja_pago, "titulo_id": t3})
    assert not r["ok"] and any("já tem PAGAMENTO" in x for x in r["recusas"])
    # e o mesmo título se lança pela ficha
    r = _propor(db, p["carla"], "PT_ATO_DE_CORRECAO",
                {"ato_origem_id": ja_pago, "titulo_id": t1})
    assert not r["ok"] and any("OUTRO título" in x for x in r["recusas"])


def test_o_ato_ja_sem_efeito_nao_se_propoe_de_novo(cg_casa):
    db = cg_casa["db"]
    p = _pessoas(db)
    t = _titulo(db, "APONTADO", "SE/1")
    desfeito = _ato(db, t, "PAGAMENTO", cancelado=True)
    r = _propor(db, p["carla"], "PT_ATO_SEM_EFEITO", {"ato_ids": [desfeito, 999999]})
    assert not r["ok"]
    assert any("já está sem efeito" in x for x in r["recusas"])
    assert any("999999 não existe" in x for x in r["recusas"])


def test_o_cadastro_em_lote_so_onde_o_valor_e_o_esperado(cg_casa):
    """O precedente do cedente da carga do acervo: um valor por título, e só
    onde o valor de hoje é o que a carga errada gravou."""
    db = cg_casa["db"]
    p = _pessoas(db)
    a = _titulo(db, "APONTADO", "CD/1", cedente="DEVEDOR TROCADO")
    b = _titulo(db, "APONTADO", "CD/2", cedente="DEVEDOR TROCADO")
    mexido = _titulo(db, "APONTADO", "CD/3", cedente="ALGUEM CORRIGIU")
    itens = [{"tabela": "pt_titulos", "id": i,
              "campos": {"cedente_nome": "CREDORA CERTA LTDA",
                         "cedente_documento": "00.000.001/0000-55"},
              "esperado": {"cedente_nome": "DEVEDOR TROCADO"}} for i in (a, b, mexido)]
    r = _propor(db, p["carla"], "PT_CADASTRO_DO_TITULO", {"itens": itens})
    assert not r["ok"] and f"pt_titulos {mexido}" in r["recusas"][0]
    r = _propor(db, p["carla"], "PT_CADASTRO_DO_TITULO", {"itens": itens[:2]})
    assert r["ok"], r["recusas"]
    assert _aprovar(db, p["mario"], r["id"])["ok"]
    for tid in (a, b):
        t = _um(db, "SELECT cedente_nome, cedente_documento FROM pt_titulos WHERE id = %s",
                (tid,))
        assert (t["cedente_nome"], t["cedente_documento"]) == (
            "CREDORA CERTA LTDA", "00.000.001/0000-55")
    assert _um(db, "SELECT cedente_nome FROM pt_titulos WHERE id = %s",
               (mexido,))["cedente_nome"] == "ALGUEM CORRIGIU"
    auditadas = _auditoria(db, CDO.ACAO_EXECUTADA)
    assert {x["entity_id"] for x in auditadas} == {a, b}
    assert json.loads(auditadas[0]["details"])["antes"]["cedente_nome"] == "DEVEDOR TROCADO"


def test_o_apresentante_so_no_titulo_tab_e_o_endereco_do_devedor(cg_casa):
    db = cg_casa["db"]
    p = _pessoas(db)
    tab = _titulo(db, "APONTADO", "AP/1", apresentante="TAB")
    banco_ = _titulo(db, "APONTADO", "AP/2", apresentante="237")
    devedor = _devedor(db, tab)
    campos = {"apresentante_nome": "APRESENTANTE EXEMPLO LTDA",
              "apresentante_documento": "00.000.001/0000-55", "apresentante_tipo": "1"}
    r = _propor(db, p["carla"], "PT_CADASTRO_DO_TITULO",
                {"titulo_ids": [banco_], "campos": campos})
    assert not r["ok"] and "cadastro dos apresentantes" in r["recusas"][0]
    r = _propor(db, p["carla"], "PT_CADASTRO_DO_TITULO",
                {"titulo_ids": [tab], "devedor_ordem": 1,
                 "campos": {**campos, "devedor_endereco": "RUA NOVA, 2",
                            "devedor_cep": "65.000-001"}})
    assert r["ok"], r["recusas"]
    assert _aprovar(db, p["mario"], r["id"])["ok"]
    t = _um(db, "SELECT apresentante_nome, apresentante_documento, apresentante_tipo "
                "FROM pt_titulos WHERE id = %s", (tab,))
    assert (t["apresentante_documento"], t["apresentante_tipo"]) == ("00000001000055", "1")
    d = _um(db, "SELECT endereco, cep FROM pt_devedores WHERE id = %s", (devedor,))
    assert (d["endereco"], d["cep"]) == ("RUA NOVA, 2", "65000001")
    tocadas = {(a["entity_type"], a["entity_id"]) for a in _auditoria(db, CDO.ACAO_EXECUTADA)}
    assert tocadas == {("pt_titulos", tab), ("pt_devedores", devedor)}


def test_recusar_exige_motivo_e_a_proposta_fica_no_historico(cg_casa):
    db = cg_casa["db"]
    p = _pessoas(db)
    t = _pago_sem_pagamento(db, "RC/1")
    feita = _propor(db, p["carla"], "PT_SITUACAO_SUSTENTADA", {"titulo_ids": [t]})
    with db.transaction() as con:
        r = CDO.recusar(con, feita["id"], aprovador=p["mario"], motivo="não", agora=AGORA)
    assert not r["ok"]
    with db.transaction() as con:
        r = CDO.recusar(con, feita["id"], aprovador=p["mario"],
                        motivo="o pagamento vai ser relançado pela ficha", agora=AGORA)
    assert r["ok"]
    assert _situacao(db, t) == "PAGO"
    with db.connect() as con:
        recusadas = CDO.listar(con, situacao=CDO.RECUSADA)["linhas"]
    assert [x["id"] for x in recusadas] == [feita["id"]]
    assert len(_auditoria(db, CDO.ACAO_RECUSADA)) == 1


# --------------------------------------------------------- o roteiro e o painel


def test_a_pendencia_do_roteiro_tem_o_contrato_e_some_com_a_decisao(cg_casa):
    db = cg_casa["db"]
    p = _pessoas(db)
    t = _pago_sem_pagamento(db, "PD/1")
    feita = _propor(db, p["carla"], "PT_SITUACAO_SUSTENTADA", {"titulo_ids": [t]})
    with db.connect() as con:
        [linha] = CDO.pendentes(con)
        assert CDO.contar(con) == 1
    assert {"titulo_id", "numero_titulo", "protocolo", "explicacao"} <= set(linha)
    assert (linha["titulo_id"], linha["numero_titulo"], linha["protocolo"]) == (
        t, "PD/1", "2610290001")
    assert f"nº {feita['id']}" in linha["explicacao"]
    assert _aprovar(db, p["mario"], feita["id"])["ok"]
    with db.connect() as con:
        assert CDO.pendentes(con) == []
        assert CDO.contar(con) == 0


def test_as_telas_da_fila(cg_casa):
    db = cg_casa["db"]
    _pessoas(db)
    t = _pago_sem_pagamento(db, "TL/1")
    carla = _entrar(cg_casa, "carla")
    tela = carla.get(f"{URL}/nova?tipo=PT_SITUACAO_SUSTENTADA").get_data(as_text=True)
    dados = {"csrf_token": _token(tela), "tipo": "PT_SITUACAO_SUSTENTADA",
             "titulo_ids": str(t), "motivo": MOTIVO}
    previa = carla.post(f"{URL}/propor", data={**dados, "acao": "previa"})
    assert previa.status_code == 200 and "Prévia — nada foi gravado" in previa.get_data(as_text=True)
    assert _um(db, "SELECT count(*) AS n FROM correcoes_de_oficio")["n"] == 0
    r = carla.post(f"{URL}/propor", content_type="multipart/form-data",
                   data={**dados, "acao": "propor",
                         "anexos": (io.BytesIO(b"%PDF-1.4 prova"), "prova.pdf")})
    assert r.status_code == 302
    correcao_id = int(r.headers["Location"].rstrip("/").rsplit("/", 1)[1])
    assert len(db.get_attachments(CDO.ENTIDADE_DO_ANEXO, correcao_id)) == 1
    ficha = carla.get(f"{URL}/{correcao_id}").get_data(as_text=True)
    assert "prova.pdf" in ficha and "Aprovar e executar" not in ficha
    # o oficial vê o contador no painel, decide pela ficha, e a escrevente não
    painel_dela = carla.get("/").get_data(as_text=True)
    assert "esperando a sua decisão" not in painel_dela
    mario = _entrar(cg_casa, "mario")
    assert "esperando a sua decisão" in mario.get("/").get_data(as_text=True)
    assert mario.get(URL).status_code == 200
    assert mario.get(f"{URL}?atribuicao=PROTESTO").status_code == 200
    ficha = mario.get(f"{URL}/{correcao_id}").get_data(as_text=True)
    assert "Aprovar e executar" in ficha
    r = mario.post(f"{URL}/{correcao_id}/aprovar",
                   data={"csrf_token": _token(ficha), "afirmo": "1", "afirmacao": AFIRMACAO})
    assert r.status_code == 302
    assert _situacao(db, t) == "APONTADO"
    for aba in CDO.SITUACOES:
        assert mario.get(f"{URL}?aba={aba}").status_code == 200


def test_o_robo_alcanca_so_as_tres_rotas_de_propor():
    import rotas_do_robo as RR
    import selo_robo as SR
    for rota in ("correcoes_de_oficio_nova", "correcoes_de_oficio_propor",
                 "correcoes_de_oficio_ficha"):
        assert SR.rota_permitida_ao_robo(rota), rota
    for rota in ("correcoes_de_oficio_aprovar", "correcoes_de_oficio_recusar",
                 "correcoes_de_oficio_anexar", "correcoes_de_oficio_lista"):
        assert not SR.rota_permitida_ao_robo(rota), rota
    assert set(RR.DA_FILA_DE_CORRECOES) <= RR.ROTAS_PERMITIDAS_AO_ROBO


@pytest.mark.parametrize("tipo", sorted(CDO.CATALOGO))
def test_todo_tipo_tem_formulario_e_atribuicao(tipo):
    t = CDO.CATALOGO[tipo]
    assert t.atribuicao in CDO.NOME_DA_ATRIBUICAO
    assert t.rotulo and t.descricao and t.campos and t.alvo_tabela
