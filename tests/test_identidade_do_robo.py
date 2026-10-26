"""Todo robô diz quem é e a mando de quem age — 26/10/2026, ETAPA 1.

Ordem do oficial: «obrigação de todo robô se identificar e dizer a mando de quem
está agindo», sem «marca contra robô». Guarda-se:

- a regra «avisar ou recusar» mora num lugar só (`identidade_do_robo.decidir`);
- a linha sem usuário e sem identificação GRAVA (etapa 1) e é contada;
- conta de robô sai com o nome dele e o do responsável; sem responsável, avisa;
- quem grava por programa declara `agente` e `a_mando_de`;
- o VARREDOR: nenhum `INSERT INTO audit_logs` do repositório fica fora da
  função da casa, e nenhum `db.log(None, ...)` grava sem dizer quem é;
- a tela de usuários escolhe o responsável; a conferência do gestor avisa;
- a corrente de hash continua fechando com as colunas novas.

Testes escritos e NÃO executados na máquina do balcão (sobrecarga, ordem do
oficial de 26/10/2026); a suíte roda na máquina do merge. Nomes fictícios:
mario, beatriz, carla e o robô «robo_exemplo».
"""
from __future__ import annotations

import ast
import re
import sys
from datetime import date
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import identidade_do_robo as IDR   # noqa: E402
from bd_nativo import banco        # noqa: E402

SENHA = "Senha#12345"


# ------------------------------------------------------------ a regra única

def test_a_regra_avisar_ou_recusar_mora_num_lugar_so():
    assert IDR.MODO == IDR.MODO_AVISAR, "etapa 1: o banco só avisa"
    for situacao in (IDR.PESSOA, IDR.ROBO, IDR.AGENTE):
        assert IDR.decidir(situacao) == IDR.GRAVAR
        assert IDR.decidir(situacao, IDR.MODO_RECUSAR) == IDR.GRAVAR
    for situacao in IDR.EM_FALTA:
        assert IDR.decidir(situacao) == IDR.AVISAR
        assert IDR.decidir(situacao, IDR.MODO_RECUSAR) == IDR.RECUSAR


def test_a_migracao_so_acrescenta_coluna():
    for tabela, coluna, tipo in IDR.MIGRACOES:
        t = tipo.upper()
        assert "NOT NULL" not in t or "DEFAULT" in t
        assert "PRIMARY KEY" not in t and "UNIQUE" not in t
    assert {(t, c) for t, c, _ in IDR.MIGRACOES} == {
        ("users", "robo_responsavel_id"), ("audit_logs", "agente"),
        ("audit_logs", "a_mando_de")}


def test_a_frase_da_tela():
    assert IDR.frase(None, "MARIO") == ""
    assert IDR.frase("robo_exemplo", "BEATRIZ") == \
        "praticado pelo agente robo_exemplo, a mando de BEATRIZ"
    assert "sem dizer a mando de quem" in IDR.frase("robo_exemplo", None)


def test_o_modulo_nao_le_texto_procurando_robo():
    """«Nada de marca contra robô»: a identidade é a declarada, nunca adivinhada."""
    fonte = (RAIZ / "identidade_do_robo.py").read_text(encoding="utf-8")
    codigo = ast.parse(fonte)
    # o docstring se exclui pelo NÓ (a prosa pode citar a palavra para dizer
    # que não a procura); o que conta é o literal que o código usa
    docstrings = {id(no.body[0].value) for no in ast.walk(codigo)
                  if isinstance(no, (ast.Module, ast.FunctionDef, ast.ClassDef))
                  and no.body and isinstance(no.body[0], ast.Expr)
                  and isinstance(no.body[0].value, ast.Constant)}
    literais = [n.value.lower() for n in ast.walk(codigo)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)
                and id(n) not in docstrings]
    for palavra in ("grok", "claude", "chatgpt", "bot", "deepseek"):
        assert not any(re.search(rf"\b{palavra}\b", s) for s in literais), palavra
    assert "eh_rotulo_de_maquina" not in fonte


# --------------------------------------------------------------- o varredor

_INSERT = re.compile(r"insert\s+into\s+audit_logs\b", re.I)

#: Quem fica de fora, e por quê. Lista curta e com motivo.
FORA = {
    # o único lugar que escreve a linha: a função da casa
    "identidade_do_robo.py": "é a função da casa",
    # script antigo que abre o SQLite direto (`sqlite3.connect`): a casa roda no
    # PostgreSQL e ele não roda mais; fica declarado em vez de consertado.
    "tools/marcar_problema_atendido.py": "script do SQLite, aposentado na prática",
}


def _fontes():
    for p in sorted(list(RAIZ.glob("*.py")) + list(RAIZ.glob("tools/*.py"))):
        yield p.relative_to(RAIZ).as_posix(), p.read_text(encoding="utf-8", errors="replace")


def test_todo_insert_em_audit_logs_passa_pela_funcao_da_casa():
    achados = []
    vistos = 0
    for rel, texto in _fontes():
        try:
            arvore = ast.parse(texto)
        except SyntaxError:
            continue
        for no in ast.walk(arvore):
            if isinstance(no, ast.Constant) and isinstance(no.value, str) \
                    and _INSERT.search(no.value):
                vistos += 1
                if rel in FORA:
                    continue
                # quem escreve à mão tem de, no mínimo, declarar o agente
                if "agente" not in no.value or "a_mando_de" not in no.value:
                    achados.append(f"{rel}:{no.lineno}")
    assert vistos >= 2, "o varredor parou de achar o próprio INSERT da casa"
    assert not achados, ("INSERT INTO audit_logs fora de identidade_do_robo.registrar "
                         "e sem agente/a_mando_de: " + ", ".join(achados))


def test_quem_grava_sem_usuario_pelo_db_log_diz_quem_e():
    """`db.log(None, ...)` sem `agente=` é a linha que a etapa 2 vai recusar."""
    achados = []
    for rel, texto in _fontes():
        try:
            arvore = ast.parse(texto)
        except SyntaxError:
            continue
        for no in ast.walk(arvore):
            if (isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)
                    and no.func.attr == "log" and no.args
                    and isinstance(no.args[0], ast.Constant) and no.args[0].value is None):
                nomes = {k.arg for k in no.keywords}
                tem_desembrulho = any(k.arg is None for k in no.keywords)
                if not ({"agente", "a_mando_de"} <= nomes or tem_desembrulho):
                    achados.append(f"{rel}:{no.lineno}")
    assert not achados, "db.log(None, ...) sem agente/a_mando_de: " + ", ".join(achados)


# ------------------------------------------------------------- no banco

def _pessoas(db):
    mario = db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    beatriz = db.create_user("beatriz", "BEATRIZ EXEMPLO", SENHA, "USER")
    carla = db.create_user("carla", "CARLA EXEMPLO", SENHA, "USER")
    robo = db.create_user("robo_exemplo", "Robo Exemplo", SENHA, "USER", eh_robo=1)
    return mario, beatriz, carla, robo


def _linha(db, action):
    with db.connect() as con:
        return banco(con).um(
            "SELECT * FROM audit_logs WHERE action=%s ORDER BY id DESC LIMIT 1", (action,))


def test_as_colunas_nascem_com_o_banco(cg_casa):
    with cg_casa["db"].connect() as con:
        bd = banco(con)
        for tabela, coluna, _ in IDR.MIGRACOES:
            assert bd.tem_coluna(tabela, coluna), f"{tabela}.{coluna}"


def test_linha_sem_ninguem_grava_e_e_contada(cg_casa):
    db = cg_casa["db"]
    IDR.CONTADOR.clear()
    db.log(None, "script", "TESTE_SEM_IDENTIDADE", "TESTE", None, {"x": 1})
    linha = _linha(db, "TESTE_SEM_IDENTIDADE")
    assert linha is not None, "etapa 1: grava mesmo sem identidade"
    assert linha["agente"] is None and linha["a_mando_de"] is None
    assert IDR.CONTADOR[(IDR.SEM_IDENTIFICACAO, "TESTE_SEM_IDENTIDADE", "TESTE")] == 1
    with db.connect() as con:
        c = IDR.conferencia(con, date.today())
    assert c["medido"]
    assert any(s["action"] == "TESTE_SEM_IDENTIDADE" and s["entity_type"] == "TESTE"
               for s in c["sem_identificacao"])
    assert c["total_sem_identificacao"] >= 1


def test_rotina_diz_quem_e_e_responde_o_primeiro_admin(cg_casa):
    db = cg_casa["db"]
    _pessoas(db)
    db.log(None, "SISTEMA", "TESTE_ROTINA", "TESTE", None, None,
           agente="rotina de teste", a_mando_de=IDR.PELO_RESPONSAVEL)
    linha = _linha(db, "TESTE_ROTINA")
    assert linha["agente"] == "rotina de teste"
    assert linha["a_mando_de"] == "MARIO EXEMPLO DOS SANTOS"
    with db.connect() as con:
        c = IDR.conferencia(con, date.today())
    assert not any(s["action"] == "TESTE_ROTINA" for s in c["sem_identificacao"])


def test_o_responsavel_configurado_vale_e_robo_nao_responde(cg_casa):
    db = cg_casa["db"]
    mario, beatriz, carla, robo = _pessoas(db)
    db.set_settings({IDR.CHAVE_RESPONSAVEL: str(carla)})
    with db.connect() as con:
        r = IDR.responsavel_das_rotinas(con)
    assert r == {"id": carla, "nome": "CARLA EXEMPLO", "configurado": True}
    # um robô gravado à mão na configuração não responde: volta o primeiro ADMIN
    db.set_settings({IDR.CHAVE_RESPONSAVEL: str(robo)})
    with db.connect() as con:
        r = IDR.responsavel_das_rotinas(con)
        assert r["id"] == mario and not r["configurado"]
        with pytest.raises(ValueError):
            IDR.validar_responsavel_das_rotinas(con, robo)


def test_conta_de_robo_sai_com_o_nome_dele_e_o_do_responsavel(cg_casa):
    db = cg_casa["db"]
    mario, beatriz, carla, robo = _pessoas(db)
    with db.transaction() as con:
        IDR.definir_responsavel_do_robo(con, robo, beatriz)
    db.log(robo, "robo_exemplo", "TESTE_DO_ROBO", "TESTE", None, None)
    linha = _linha(db, "TESTE_DO_ROBO")
    assert linha["user_id"] == robo
    assert linha["agente"] == "Robo Exemplo"
    assert linha["a_mando_de"] == "BEATRIZ EXEMPLO"
    # e a pessoa que age por si não ganha agente
    db.log(beatriz, "beatriz", "TESTE_DA_PESSOA", "TESTE", None, None)
    pessoa = _linha(db, "TESTE_DA_PESSOA")
    assert pessoa["agente"] is None and pessoa["a_mando_de"] is None


def test_robo_sem_responsavel_entra_e_fica_com_o_aviso(cg_casa):
    db = cg_casa["db"]
    mario, beatriz, carla, robo = _pessoas(db)
    db.log(robo, "robo_exemplo", "TESTE_ROBO_SOLTO", "TESTE", None, None)
    linha = _linha(db, "TESTE_ROBO_SOLTO")
    assert linha["agente"] == "Robo Exemplo" and linha["a_mando_de"] is None
    with db.connect() as con:
        c = IDR.conferencia(con, date.today())
    sem = [r for r in c["robos_sem_responsavel"] if r["id"] == robo]
    assert sem and sem[0]["linhas"] >= 1


def test_agente_com_a_conta_de_uma_pessoa_diz_que_foi_a_mando_dela(cg_casa):
    """O malote age com a conta de quem o oficial designou: a linha diz isso."""
    db = cg_casa["db"]
    mario, beatriz, carla, robo = _pessoas(db)
    with db.transaction() as con:
        IDR.registrar(con, ts=db.now(), user_id=beatriz, username="beatriz",
                      action="TESTE_MALOTE", entity_type="TASK", entity_id=None,
                      details={"a": 1}, agente="agente do malote")
    linha = _linha(db, "TESTE_MALOTE")
    assert linha["agente"] == "agente do malote"
    assert linha["a_mando_de"] == "BEATRIZ EXEMPLO"


def test_o_responsavel_do_robo_e_pessoa_ativa(cg_casa):
    db = cg_casa["db"]
    mario, beatriz, carla, robo = _pessoas(db)
    outro = db.create_user("robo_dois", "Robo Dois", SENHA, "USER", eh_robo=1)
    db.set_user_active(carla, False)
    with db.transaction() as con:
        for resp in (outro, carla, robo):
            with pytest.raises(ValueError), banco(con).ponto_de_retorno("t_resp"):
                IDR.definir_responsavel_do_robo(con, robo, resp)
        with pytest.raises(ValueError), banco(con).ponto_de_retorno("t_pessoa"):
            IDR.definir_responsavel_do_robo(con, beatriz, mario)  # pessoa responde por si
        IDR.definir_responsavel_do_robo(con, robo, mario)
        IDR.definir_responsavel_do_robo(con, robo, None)          # limpar vale


def test_etapa_2_recusa_no_mesmo_lugar(cg_casa, monkeypatch):
    """A etapa 2 é trocar UMA constante; nada mais muda."""
    db = cg_casa["db"]
    _pessoas(db)
    monkeypatch.setattr(IDR, "MODO", IDR.MODO_RECUSAR)
    with pytest.raises(IDR.SemIdentificacao):
        db.log(None, "script", "TESTE_RECUSADO", "TESTE", None, None)
    assert _linha(db, "TESTE_RECUSADO") is None
    db.log(None, "SISTEMA", "TESTE_ACEITO", "TESTE", None, None,
           agente="rotina", a_mando_de=IDR.PELO_RESPONSAVEL)
    assert _linha(db, "TESTE_ACEITO") is not None


def test_a_corrente_de_hash_fecha_com_as_colunas_novas(cg_casa):
    import auditoria_cadeia as AC
    db = cg_casa["db"]
    _pessoas(db)
    db.log(None, "SISTEMA", "CADEIA_COM_AGENTE", "TESTE", None, {"y": 1},
           agente="rotina", a_mando_de=IDR.PELO_RESPONSAVEL)
    with db.connect() as con:
        linhas = banco(con).ler(
            """SELECT id, ts, user_id, username_snapshot, action, entity_type, entity_id,
                      details, ip_address, hash_anterior, hash_linha
                 FROM audit_logs ORDER BY id""")
    assert AC.divergencias(linhas) == []


def test_login_recusado_e_gravado_pelo_servidor(cg_casa):
    from conftest import cg_login
    db = cg_casa["db"]
    _pessoas(db)
    cg_login(cg_casa["c"], "mario", "senha-errada")
    with db.connect() as con:
        linha = banco(con).um(
            "SELECT * FROM audit_logs WHERE user_id IS NULL AND action ILIKE %s "
            "ORDER BY id DESC LIMIT 1", ("%LOGIN%",))
    assert linha is not None
    assert linha["agente"] == IDR.AGENTE_SERVIDOR
    assert linha["a_mando_de"] == "MARIO EXEMPLO DOS SANTOS"


def test_o_robo_logado_pratica_com_a_identidade_da_conta(cg_casa):
    from conftest import cg_login
    db = cg_casa["db"]
    mario, beatriz, carla, robo = _pessoas(db)
    with db.transaction() as con:
        IDR.definir_responsavel_do_robo(con, robo, beatriz)
    cg_login(cg_casa["c"], "robo_exemplo", SENHA)
    linha = _linha(db, "LOGIN_SUCCESS")
    assert linha["user_id"] == robo
    assert linha["agente"] == "Robo Exemplo"
    assert linha["a_mando_de"] == "BEATRIZ EXEMPLO"


# ------------------------------------------------------------- as telas

def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def test_a_tela_de_usuarios_cria_robo_com_responsavel(cg_casa_logada):
    db, c = cg_casa_logada["db"], cg_casa_logada["c"]
    beatriz = db.create_user("beatriz", "BEATRIZ EXEMPLO", SENHA, "USER")
    tela = c.get("/usuarios").get_data(as_text=True)
    assert "Identidade dos robôs e das rotinas" in tela
    assert "Responsável pelas rotinas automáticas" in tela
    r = c.post("/usuarios", data={
        "csrf_token": _token(tela), "action": "create", "full_name": "Robo Exemplo",
        "username": "robo_exemplo", "role": "USER", "password": SENHA,
        "eh_robo": "1", "robo_responsavel_id": str(beatriz)}, follow_redirects=True)
    assert r.status_code == 200
    with db.connect() as con:
        robo = banco(con).um("SELECT * FROM users WHERE username='robo_exemplo'")
    assert robo["eh_robo"] == 1 and robo["robo_responsavel_id"] == beatriz


def test_a_tela_de_usuarios_recusa_robo_como_responsavel(cg_casa_logada):
    db, c = cg_casa_logada["db"], cg_casa_logada["c"]
    robo = db.create_user("robo_exemplo", "Robo Exemplo", SENHA, "USER", eh_robo=1)
    outro = db.create_user("robo_dois", "Robo Dois", SENHA, "USER", eh_robo=1)
    tela = c.get("/usuarios").get_data(as_text=True)
    c.post("/usuarios", data={"csrf_token": _token(tela), "action": "eh_robo",
                              "user_id": str(robo), "eh_robo": "1",
                              "robo_responsavel_id": str(outro)})
    with db.connect() as con:
        assert banco(con).valor(
            "SELECT robo_responsavel_id FROM users WHERE id=%s", (robo,)) is None
    tela = c.get("/usuarios").get_data(as_text=True)
    assert "sem responsável" in tela


def test_a_tela_grava_o_responsavel_pelas_rotinas(cg_casa_logada):
    db, c = cg_casa_logada["db"], cg_casa_logada["c"]
    carla = db.create_user("carla", "CARLA EXEMPLO", SENHA, "USER")
    tela = c.get("/usuarios").get_data(as_text=True)
    c.post("/usuarios", data={"csrf_token": _token(tela),
                              "action": "responsavel_rotinas",
                              "responsavel_rotinas": str(carla)})
    assert db.get_setting(IDR.CHAVE_RESPONSAVEL, "") == str(carla)


def test_a_trilha_de_auditoria_mostra_o_agente(cg_casa_logada):
    db, c = cg_casa_logada["db"], cg_casa_logada["c"]
    db.log(None, "SISTEMA", "TESTE_NA_TRILHA", "TESTE", None, None,
           agente="rotina de teste", a_mando_de=IDR.PELO_RESPONSAVEL)
    html = c.get("/auditoria").get_data(as_text=True)
    assert "rotina de teste, a mando de MARIO EXEMPLO DOS SANTOS" in html


def test_a_conferencia_do_gestor_avisa_ao_oficial(cg_casa):
    import gestor_conferencia as GC
    db = cg_casa["db"]
    mario, beatriz, carla, robo = _pessoas(db)
    db.log(None, "script", "TESTE_GESTOR", "TESTE", None, None)
    with db.connect() as con:
        achados = GC.regra_identidade_dos_robos(con, date.today())
    chaves = {a["chave"] for a in achados}
    assert "IDENTIDADE:sem_identificacao" in chaves
    assert f"IDENTIDADE:robo:{robo}" in chaves
    assert all(a["setor"] == "GESTAO" and a["gravidade"] == "ATENCAO" for a in achados)
    assert ("IDENTIDADE_DOS_ROBOS", GC.regra_identidade_dos_robos) in GC.REGRAS
