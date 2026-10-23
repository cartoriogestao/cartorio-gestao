from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from datetime import date

from database import Database


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "test.sqlite3")
        self.uid = self.db.create_user("admin", "Administrador", "SenhaForte123", "ADMIN")

    def tearDown(self):
        self.tmp.cleanup()

    def test_auth(self):
        self.assertIsNotNone(self.db.authenticate("admin", "SenhaForte123"))
        self.assertIsNone(self.db.authenticate("admin", "errada"))

    def test_password_policy_default_is_six_without_complexity(self):
        uid = self.db.create_user("simples", "Usuário Simples", "abcdef", "USER")
        self.assertIsNotNone(self.db.authenticate("simples", "abcdef"))
        with self.assertRaises(ValueError):
            self.db.create_user("curta", "Senha Curta", "abcde", "USER")

    def test_password_policy_can_be_changed_in_settings(self):
        self.db.set_settings({
            "password_min_length": "4",
            "password_require_digit": "1",
        })
        with self.assertRaises(ValueError):
            self.db.create_user("semnumero", "Sem Número", "abcd", "USER")
        uid = self.db.create_user("comnumero", "Com Número", "abc1", "USER")
        self.assertIsNotNone(self.db.authenticate("comnumero", "abc1"))

    def test_inspection_seed_and_deadlines(self):
        iid = self.db.seed_inspection()
        tasks = [t for t in self.db.list_tasks(limit=2000) if t["inspection_id"] == iid]
        self.assertGreaterEqual(len(tasks), 70)
        self.assertTrue(all(t["due_date"] is None for t in tasks))
        self.db.set_inspection_start_date(iid, "2026-08-13", self.uid)
        tasks = [t for t in self.db.list_tasks(limit=2000) if t["inspection_id"] == iid]
        self.assertTrue(all(t["due_date"] for t in tasks))

    def test_expediente_protocol(self):
        eid = self.db.create_expediente({"source":"Malote Digital","subject":"Teste","category":"Para Cumprimento","received_at":"2026-08-12"}, self.uid)
        row = self.db.get_expediente(eid)
        self.assertTrue(row["internal_protocol"].startswith("EXP-"))

    def test_recurring_task(self):
        rid = self.db.create_recurrence({"title":"Rotina", "frequency":"MONTHLY", "next_due_date":date.today().isoformat(), "lead_days":5}, self.uid)
        self.assertEqual(self.db.ensure_recurring_tasks(), 1)
        self.assertTrue(any(t["recurrence_id"] == rid for t in self.db.list_tasks(limit=2000)))

    def test_checklist(self):
        template = self.db.list_checklist_templates()[0]
        run = self.db.start_checklist(template["id"], "REF", self.uid)
        _, items = self.db.get_checklist_run(run)
        self.db.save_checklist_run(run, {i["id"] for i in items}, {i["id"]:"" for i in items}, True)
        self.assertEqual(self.db.get_checklist_run(run)[0]["status"], "CONCLUIDO")


if __name__ == "__main__":
    unittest.main()


# ====================================================================
# A VERIFICAÇÃO EM DUAS ETAPAS (LG02, 19/10/2026) — `dois_fatores.py`.
#
# Moram aqui, ao lado de `test_auth`, porque é o login que elas guardam — e
# porque este arquivo roda na conferência do lote. Os vetores são os OFICIAIS
# das RFCs (4226, apêndice D; 6238, apêndice B): o algoritmo foi escrito na
# casa, sem `pyotp`, e são eles que provam que um aplicativo autenticador de
# verdade gera o mesmo código.
# ====================================================================

import re

import pytest

import dois_fatores as DF
import dois_fatores_web as DFW
from bd_nativo import banco

SENHA = "Senha#12345"
# Um instante fixo e longe do agora: o relógio do teste é este, e não o da máquina.
T0 = 1_800_000_000.0

RFC_4226 = ["755224", "287082", "359152", "969429", "338314",
            "254676", "287922", "162583", "399871", "520489"]

RFC_6238 = [  # instante, SHA-1, SHA-256, SHA-512 (oito dígitos)
    (59, "94287082", "46119246", "90693936"),
    (1111111109, "07081804", "68084774", "25091201"),
    (1111111111, "14050471", "67062674", "99943326"),
    (1234567890, "89005924", "91819424", "93441116"),
    (2000000000, "69279037", "90698825", "38618901"),
    (20000000000, "65353130", "77737706", "47863826"),
]
CHAVE_SHA1 = b"12345678901234567890"
CHAVE_SHA256 = b"12345678901234567890123456789012"
CHAVE_SHA512 = b"1234567890" * 6 + b"1234"


class _Relogio:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture
def relogio(monkeypatch):
    r = _Relogio(T0)
    monkeypatch.setattr(DF, "relogio", r)
    return r


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _senha(c, usuario, senha=SENHA, proximo=""):
    token = _token(c.get("/login").get_data(as_text=True))
    url = "/login" + (f"?next={proximo}" if proximo else "")
    return c.post(url, data={"username": usuario, "password": senha,
                             "csrf_token": token})


def _post(c, url, tela, **dados):
    dados["csrf_token"] = _token(c.get(tela).get_data(as_text=True))
    return c.post(url, data=dados)


def _ativar(db, uid, dados, instante=T0):
    """Ativa pelo módulo, como se o celular tivesse lido o QR. Devolve a chave e os códigos."""
    with db.transaction() as con:
        segredo = DF.iniciar(con, uid, pasta=dados)
        codigos = DF.confirmar(con, uid, DF.totp(segredo, instante), pasta=dados,
                               instante=instante)
    return segredo, codigos


def _rastro(db):
    with db.connect() as con:
        return banco(con).ler("SELECT action, details FROM audit_logs ORDER BY id")


# ------------------------------------------------------------ o algoritmo

def test_o_hotp_bate_com_os_vetores_da_rfc_4226():
    assert [DF.hotp(CHAVE_SHA1, i) for i in range(10)] == RFC_4226


@pytest.mark.parametrize("instante,sha1,sha256,sha512", RFC_6238)
def test_o_totp_bate_com_os_vetores_da_rfc_6238_nos_tres_algoritmos(instante, sha1, sha256, sha512):
    assert DF.totp(CHAVE_SHA1, instante, 8, "sha1") == sha1
    assert DF.totp(CHAVE_SHA256, instante, 8, "sha256") == sha256
    assert DF.totp(CHAVE_SHA512, instante, 8, "sha512") == sha512


def test_a_chave_vai_e_volta_em_base32_e_o_qr_leva_o_que_o_aplicativo_pede():
    chave = DF.novo_segredo()
    assert len(chave) == 20
    assert DF.de_base32(DF.em_base32(chave)) == chave
    assert DF.de_base32(DF.chave_agrupada(chave).lower()) == chave
    endereco = DF.endereco_do_aplicativo(chave, "escrevente.teste")
    assert endereco.startswith("otpauth://totp/Cartorio%20Gestao:escrevente.teste?")
    for parte in (f"secret={DF.em_base32(chave)}", "algorithm=SHA1", "digits=6", "period=30"):
        assert parte in endereco
    assert DF.qr_em_svg(endereco).startswith("<svg")


def test_o_codigo_vale_um_passo_para_cada_lado_e_nao_dois():
    chave = DF.novo_segredo()
    for desvio in (-30, 0, 30):
        assert DF.passo_aceito(chave, DF.totp(chave, T0 + desvio), T0) is not None
    for desvio in (-60, 60):
        assert DF.passo_aceito(chave, DF.totp(chave, T0 + desvio), T0) is None
    assert DF.passo_aceito(chave, "12345", T0) is None


def test_o_mesmo_codigo_nao_vale_duas_vezes():
    chave = DF.novo_segredo()
    passo = DF.passo_aceito(chave, DF.totp(chave, T0), T0)
    assert passo == DF.passo_de(T0)
    assert DF.passo_aceito(chave, DF.totp(chave, T0), T0, ultimo_passo=passo) is None
    assert DF.passo_aceito(chave, DF.totp(chave, T0 + 30), T0, ultimo_passo=passo) == passo + 1


def test_os_codigos_de_recuperacao_sao_dez_diferentes_e_nenhum_se_le_como_do_aplicativo():
    codigos = DF.novos_codigos_de_recuperacao()
    assert len(codigos) == DF.QUANTOS_CODIGOS == 10
    assert len(set(codigos)) == 10
    assert all(DF.parece_recuperacao(c) for c in codigos)
    assert all(DF.parece_recuperacao(c.upper().replace("-", " ")) for c in codigos)
    assert not DF.parece_recuperacao("123456")


# ------------------------------------------------------------ o banco

def test_o_segredo_fica_cifrado_no_banco_e_nao_abre_na_linha_de_outro_usuario(cg_casa):
    db, dados = cg_casa["db"], cg_casa["dados"]
    uid = db.create_user("escrevente.um", "ESCREVENTE UM DE TESTE", SENHA, "USER")
    outro = db.create_user("escrevente.dois", "ESCREVENTE DOIS DE TESTE", SENHA, "USER")
    with db.transaction() as con:
        segredo = DF.iniciar(con, uid, pasta=dados)
    with db.connect() as con:
        cifrado = banco(con).valor(
            "SELECT segredo_cifrado FROM dois_fatores WHERE user_id = %s", (uid,))
        assert DF.segredo_pendente(con, uid, dados) == segredo
    assert DF.em_base32(segredo) not in cifrado and segredo.hex() not in cifrado
    assert DF.decifrar(cifrado, uid, dados) == segredo
    assert DF.decifrar(cifrado, outro, dados) is None
    # A chave mora fora do banco, na pasta de dados — onde o backup não vai.
    assert (dados / DF.NOME_DA_CHAVE).exists()


def test_ativar_exige_o_primeiro_codigo_e_guarda_os_dez_codigos_so_em_hash(cg_casa, relogio):
    db, dados = cg_casa["db"], cg_casa["dados"]
    uid = db.create_user("escrevente.um", "ESCREVENTE UM DE TESTE", SENHA, "USER")
    with db.transaction() as con:
        segredo = DF.iniciar(con, uid, pasta=dados)
    with pytest.raises(DF.DoisFatoresError):
        with db.transaction() as con:
            DF.confirmar(con, uid, DF.totp(segredo, T0 + 600), pasta=dados)
    with db.connect() as con:
        assert DF.situacao(con, uid)["estado"] == DF.PENDENTE
    with db.transaction() as con:
        codigos = DF.confirmar(con, uid, DF.totp(segredo, T0), pasta=dados)
    with db.connect() as con:
        sit = DF.situacao(con, uid)
        guardados = banco(con).ler(
            "SELECT sal, hash FROM dois_fatores_recuperacao WHERE user_id = %s ORDER BY id",
            (uid,))
    assert sit["estado"] == DF.ATIVO and sit["restantes"] == 10
    texto = repr(guardados)
    assert not any(DF.normalizar_codigo(c) in texto or c in texto for c in codigos)
    # Ativa não recomeça por cima: trocar de celular é desativar antes.
    with pytest.raises(DF.DoisFatoresError):
        with db.transaction() as con:
            DF.iniciar(con, uid, pasta=dados)


def test_o_codigo_de_recuperacao_entra_uma_vez_so(cg_casa, relogio):
    db, dados = cg_casa["db"], cg_casa["dados"]
    uid = db.create_user("escrevente.um", "ESCREVENTE UM DE TESTE", SENHA, "USER")
    _, codigos = _ativar(db, uid, dados)
    with db.transaction() as con:
        primeira = DF.conferir(con, uid, codigos[3].upper(), pasta=dados)
    with db.transaction() as con:
        segunda = DF.conferir(con, uid, codigos[3], pasta=dados)
    assert primeira["ok"] and primeira["meio"] == DF.RECUPERACAO and primeira["restantes"] == 9
    assert not segunda["ok"] and segunda["motivo"] == "codigo"


def test_cinco_codigos_errados_travam_e_nem_o_certo_entra_ate_passar_o_prazo(cg_casa, relogio):
    db, dados = cg_casa["db"], cg_casa["dados"]
    uid = db.create_user("escrevente.um", "ESCREVENTE UM DE TESTE", SENHA, "USER")
    segredo, _ = _ativar(db, uid, dados)
    relogio.t = T0 + 30
    errado = str((int(DF.totp(segredo, relogio.t)) + 1) % 1_000_000).zfill(6)
    resultados = []
    for _ in range(DF.MAX_FALHAS):
        with db.transaction() as con:
            resultados.append(DF.conferir(con, uid, errado, pasta=dados))
    assert [r["motivo"] for r in resultados] == ["codigo"] * 4 + ["bloqueado"]
    assert resultados[-1]["bloqueou_agora"]
    with db.transaction() as con:
        travado = DF.conferir(con, uid, DF.totp(segredo, relogio.t), pasta=dados)
    assert not travado["ok"] and travado["motivo"] == "bloqueado"
    relogio.t = T0 + DF.BLOQUEIO_MINUTOS * 60 + 60
    with db.transaction() as con:
        depois = DF.conferir(con, uid, DF.totp(segredo, relogio.t), pasta=dados)
    assert depois["ok"] and depois["meio"] == DF.TOTP


def test_sem_o_arquivo_da_chave_o_codigo_de_recuperacao_ainda_entra(cg_casa, relogio):
    """Máquina nova, backup restaurado: a chave do cofre não veio, e ninguém fica trancado."""
    db, dados = cg_casa["db"], cg_casa["dados"]
    uid = db.create_user("escrevente.um", "ESCREVENTE UM DE TESTE", SENHA, "USER")
    segredo, codigos = _ativar(db, uid, dados)
    (dados / DF.NOME_DA_CHAVE).unlink()
    with db.transaction() as con:
        pelo_app = DF.conferir(con, uid, DF.totp(segredo, T0 + 30), pasta=dados)
    with db.transaction() as con:
        pela_recuperacao = DF.conferir(con, uid, codigos[0], pasta=dados)
    assert not pelo_app["ok"] and pelo_app["cofre_ilegivel"]
    assert pela_recuperacao["ok"] and pela_recuperacao["meio"] == DF.RECUPERACAO


# ------------------------------------------------------------ as telas

def test_o_login_sem_verificacao_continua_o_de_sempre(cg_casa):
    db, c = cg_casa["db"], cg_casa["c"]
    db.create_user("escrevente.um", "ESCREVENTE UM DE TESTE", SENHA, "USER")
    r = _senha(c, "escrevente.um")
    assert r.status_code == 302 and r.headers["Location"].endswith("/")
    assert c.get("/").status_code == 200
    assert [x["action"] for x in _rastro(db)].count("LOGIN_SUCCESS") == 1


def test_com_a_verificacao_ativa_a_senha_sozinha_nao_abre_tela_nenhuma(cg_casa, relogio):
    db, c, dados = cg_casa["db"], cg_casa["c"], cg_casa["dados"]
    uid = db.create_user("escrevente.um", "ESCREVENTE UM DE TESTE", SENHA, "USER")
    segredo, codigos = _ativar(db, uid, dados)
    r = _senha(c, "escrevente.um", proximo="/tarefas")
    assert r.status_code == 302 and "/login/dois-fatores" in r.headers["Location"]
    assert "/login" in c.get("/").headers.get("Location", "")
    assert "/login" in c.get("/conta/dois-fatores").headers.get("Location", "")
    tela = "/login/dois-fatores"
    r = _post(c, tela, tela, codigo="000000" if DF.totp(segredo, T0 + 30) != "000000" else "111111")
    assert "/login/dois-fatores" in r.headers["Location"]
    r = _post(c, tela, tela, codigo=DF.totp(segredo, T0 + 30))
    assert r.status_code == 302 and r.headers["Location"].endswith("/tarefas")
    assert c.get("/").status_code == 200
    rastro = _rastro(db)
    acoes = [x["action"] for x in rastro]
    assert "LOGIN_DOIS_FATORES_PEDIDO" in acoes and "LOGIN_DOIS_FATORES_FALHA" in acoes
    sucesso = [x for x in rastro if x["action"] == "LOGIN_SUCCESS"]
    assert len(sucesso) == 1 and '"TOTP"' in sucesso[0]["details"]
    # O rastro conta o que houve, e não dá o meio de repetir.
    tudo = repr(rastro)
    assert DF.em_base32(segredo) not in tudo
    assert DF.totp(segredo, T0 + 30) not in tudo
    assert not any(cod in tudo for cod in codigos)


def test_a_meia_sessao_morre_em_cinco_minutos(cg_casa, relogio):
    db, c, dados = cg_casa["db"], cg_casa["c"], cg_casa["dados"]
    uid = db.create_user("escrevente.um", "ESCREVENTE UM DE TESTE", SENHA, "USER")
    segredo, _ = _ativar(db, uid, dados)
    _senha(c, "escrevente.um")
    token = _token(c.get("/login/dois-fatores").get_data(as_text=True))
    relogio.t = T0 + DF.PRAZO_DO_SEGUNDO_PASSO + 1
    r = c.post("/login/dois-fatores",
               data={"codigo": DF.totp(segredo, relogio.t), "csrf_token": token})
    assert r.headers["Location"].endswith("/login")
    assert "/login" in c.get("/").headers.get("Location", "")


def test_o_papel_exigido_pelo_gestor_cadastra_o_celular_na_entrada(cg_casa, relogio):
    db, c, dados = cg_casa["db"], cg_casa["c"], cg_casa["dados"]
    uid = db.create_user("oficial.teste", "OFICIAL DE TESTE", SENHA, "ADMIN")
    db.set_settings({DF.CHAVE_DA_EXIGENCIA: '["ADMIN"]'})
    r = _senha(c, "oficial.teste")
    assert "/login/dois-fatores/cadastrar" in r.headers["Location"]
    tela = "/login/dois-fatores/cadastrar"
    # O GET não grava: a chave só nasce no clique.
    assert "Gerar a chave" in c.get(tela).get_data(as_text=True)
    with db.connect() as con:
        assert DF.situacao(con, uid)["estado"] == DF.NENHUM
    _post(c, tela, tela, acao="iniciar")
    html = c.get(tela).get_data(as_text=True)
    assert "<svg" in html
    with db.connect() as con:
        segredo = DF.segredo_pendente(con, uid, dados)
    assert DF.chave_agrupada(segredo) in html
    assert "/login" in c.get("/").headers.get("Location", "")
    r = _post(c, tela, tela, acao="confirmar", codigo=DF.totp(segredo, T0))
    assert r.status_code == 200 and r.headers["Cache-Control"] == "no-store"
    assert len(re.findall(r"<li><code>[a-z0-9]{5}-[a-z0-9]{5}</code></li>",
                          r.get_data(as_text=True))) == 10
    assert c.get("/").status_code == 200
    with db.connect() as con:
        assert DF.situacao(con, uid)["estado"] == DF.ATIVO
    acoes = [x["action"] for x in _rastro(db)]
    assert "LOGIN_DOIS_FATORES_CADASTRO_EXIGIDO" in acoes and "DOIS_FATORES_ATIVADO" in acoes


def test_desativar_pede_a_senha_e_o_codigo_e_so_a_senha_nao_basta(cg_casa, relogio):
    db, c, dados = cg_casa["db"], cg_casa["c"], cg_casa["dados"]
    uid = db.create_user("escrevente.um", "ESCREVENTE UM DE TESTE", SENHA, "USER")
    segredo, _ = _ativar(db, uid, dados)
    _senha(c, "escrevente.um")
    _post(c, "/login/dois-fatores", "/login/dois-fatores", codigo=DF.totp(segredo, T0 + 30))
    relogio.t = T0 + 30
    tela, url = "/conta/dois-fatores", "/conta/dois-fatores/desativar"
    _post(c, url, tela, senha=SENHA, codigo="")
    _post(c, url, tela, senha="errada", codigo=DF.totp(segredo, T0 + 60))
    with db.connect() as con:
        assert DF.situacao(con, uid)["estado"] == DF.ATIVO
    _post(c, url, tela, senha=SENHA, codigo=DF.totp(segredo, T0 + 60))
    with db.connect() as con:
        assert DF.situacao(con, uid)["estado"] == DF.NENHUM
        assert banco(con).valor("SELECT count(*) AS n FROM dois_fatores_recuperacao "
                                "WHERE user_id = %s", (uid,)) == 0
    acoes = [x["action"] for x in _rastro(db)]
    assert acoes.count("DOIS_FATORES_DESATIVAR_RECUSADO") == 2
    assert "DOIS_FATORES_DESATIVADO" in acoes


def test_a_conta_ativa_pela_propria_tela_e_o_get_nao_grava(cg_casa, relogio):
    db, c = cg_casa["db"], cg_casa["c"]
    uid = db.create_user("escrevente.um", "ESCREVENTE UM DE TESTE", SENHA, "USER")
    _senha(c, "escrevente.um")
    tela = "/conta/dois-fatores"
    assert "Ativar a verificação" in c.get(tela).get_data(as_text=True)
    with db.connect() as con:
        assert DF.situacao(con, uid)["estado"] == DF.NENHUM
    _post(c, "/conta/dois-fatores/iniciar", tela)
    with db.connect() as con:
        segredo = DF.segredo_pendente(con, uid, cg_casa["dados"])
    r = _post(c, "/conta/dois-fatores/confirmar", tela, codigo=DF.totp(segredo, T0))
    assert r.headers["Cache-Control"] == "no-store"
    assert r.get_data(as_text=True).count("<li><code>") == 10
    assert "Ativa" in c.get(tela).get_data(as_text=True)


def test_so_o_admin_abre_a_tela_do_gestor_e_zerar_pede_a_senha_dele_e_o_motivo(cg_casa, relogio):
    db, c, dados = cg_casa["db"], cg_casa["c"], cg_casa["dados"]
    db.create_user("oficial.teste", "OFICIAL DE TESTE", SENHA, "ADMIN")
    alvo = db.create_user("escrevente.um", "ESCREVENTE UM DE TESTE", SENHA, "USER")
    _ativar(db, alvo, dados)
    outro = cg_casa["app"].test_client()
    _senha(outro, "escrevente.um")
    assert outro.get("/administrativo/gestor/dois-fatores").status_code == 302  # falta o código
    _senha(c, "oficial.teste")
    tela = "/administrativo/gestor/dois-fatores"
    assert "escrevente.um" in c.get(tela).get_data(as_text=True)
    _post(c, tela + "/exigir", tela, papel_ADMIN="1", papel_MANAGER="1")
    assert DF.papeis_exigidos(db.get_setting) == ["ADMIN", "MANAGER"]
    _post(c, tela + "/zerar", tela, user_id=str(alvo), motivo="", senha=SENHA)
    _post(c, tela + "/zerar", tela, user_id=str(alvo), motivo="perdeu o celular", senha="errada")
    with db.connect() as con:
        assert DF.situacao(con, alvo)["estado"] == DF.ATIVO
    _post(c, tela + "/zerar", tela, user_id=str(alvo), motivo="perdeu o celular", senha=SENHA)
    with db.connect() as con:
        assert DF.situacao(con, alvo)["estado"] == DF.NENHUM
    rastro = _rastro(db)
    acoes = [x["action"] for x in rastro]
    assert "DOIS_FATORES_EXIGENCIA_ALTERADA" in acoes
    assert "DOIS_FATORES_ZERAR_RECUSADO" in acoes
    zerado = [x for x in rastro if x["action"] == "DOIS_FATORES_ZERADO_PELO_GESTOR"]
    assert len(zerado) == 1 and "perdeu o celular" in zerado[0]["details"]


def test_o_usuario_comum_nao_abre_a_tela_do_gestor(cg_casa):
    db, c = cg_casa["db"], cg_casa["c"]
    db.create_user("escrevente.um", "ESCREVENTE UM DE TESTE", SENHA, "USER")
    _senha(c, "escrevente.um")
    assert c.get("/administrativo/gestor/dois-fatores").status_code == 403
    assert c.get("/conta/dois-fatores").status_code == 200


def test_o_destino_depois_do_codigo_nao_leva_para_fora_do_sistema():
    assert DFW.destino_seguro("/tarefas", "/") == "/tarefas"
    for fora in ("https://exemplo.invalid/", "//exemplo.invalid", "/\\exemplo.invalid", ""):
        assert DFW.destino_seguro(fora, "/") == "/"


def test_os_papeis_da_tela_do_gestor_sao_os_da_casa():
    from app import ROLES
    assert list(DFW.PAPEIS) == ROLES


def test_codigos_novos_pedem_senha_e_codigo_e_os_antigos_deixam_de_valer(cg_casa, relogio):
    db, c, dados = cg_casa["db"], cg_casa["c"], cg_casa["dados"]
    uid = db.create_user("escrevente.um", "ESCREVENTE UM DE TESTE", SENHA, "USER")
    segredo, antigos = _ativar(db, uid, dados)
    _senha(c, "escrevente.um")
    _post(c, "/login/dois-fatores", "/login/dois-fatores", codigo=DF.totp(segredo, T0 + 30))
    relogio.t = T0 + 30
    tela, url = "/conta/dois-fatores", "/conta/dois-fatores/codigos"
    assert "<li><code>" not in _post(c, url, tela, senha="errada",
                                     codigo=DF.totp(segredo, T0 + 60)).get_data(as_text=True)
    r = _post(c, url, tela, senha=SENHA, codigo=DF.totp(segredo, T0 + 60))
    novos = re.findall(r"<li><code>([a-z0-9-]+)</code></li>", r.get_data(as_text=True))
    assert len(novos) == 10 and not set(novos) & set(antigos)
    with db.transaction() as con:
        assert not DF.conferir(con, uid, antigos[0], pasta=dados)["ok"]
    with db.transaction() as con:
        assert DF.conferir(con, uid, novos[0], pasta=dados)["ok"]
    assert "DOIS_FATORES_CODIGOS_NOVOS" in [x["action"] for x in _rastro(db)]


# ------------------------------------------------------------ a trava (LX20)
#
# Ressalvas da revisão do LG02. Com a ponte, `db.transaction()` já abre com a
# trava única e nada corre junto; por isso a corrida se prova com conexões do
# psycopg SEM a ponte, como a transação vai ficar quando ela sair.

import contextlib
import threading
import time


def _psycopg_puro(schema, *, autocommit=False):
    import psycopg
    import banco_pg
    pg = psycopg.connect(banco_pg.dsn(), autocommit=autocommit)
    pg.execute(f'SET search_path TO "{schema}", public')
    if not autocommit:
        pg.commit()
    return pg


def test_desativar_e_trocar_os_codigos_ao_mesmo_tempo_nao_travam_nem_deixam_codigo_orfao(
        cg_casa, relogio, monkeypatch):
    """A conta trocando de códigos e o Gestor zerando a mesma conta. A troca
    já prendeu a linha e vai apagar os códigos velhos; o zerar chega no meio.
    Sem o `FOR UPDATE` no começo do `desativar`, ele apagava os códigos antes
    e esperava a linha, a troca esperava os códigos dele: deadlock."""
    db, dados = cg_casa["db"], cg_casa["dados"]
    uid = db.create_user("escrevente.um", "ESCREVENTE UM DE TESTE", SENHA, "USER")
    _ativar(db, uid, dados)
    with db.connect() as con:
        schema = con.schema
    um, dois = _psycopg_puro(schema), _psycopg_puro(schema)
    vigia = _psycopg_puro(schema, autocommit=True)
    pid_dois = banco(dois).valor("SELECT pg_backend_pid() AS pid")
    chegou, siga = threading.Event(), threading.Event()
    original = DF.banco

    def banco_que_para(con):
        bd = original(con)
        if con is um:
            rodar = bd._rodar

            def _rodar(sql, parametros=None):
                if sql.startswith("DELETE FROM dois_fatores_recuperacao"):
                    chegou.set()
                    siga.wait(20)
                return rodar(sql, parametros)
            bd._rodar = _rodar
        return bd

    monkeypatch.setattr(DF, "banco", banco_que_para)
    prontos = DF.preparar_codigos()
    erros: dict = {}

    def em_fio(nome, conexao, faz):
        def corpo():
            try:
                faz()
                conexao.commit()
            except Exception as erro:  # o teste confere que não houve
                erros[nome] = erro
                conexao.rollback()
        fio = threading.Thread(target=corpo)
        fio.start()
        return fio

    try:
        troca = em_fio("troca", um, lambda: DF.trocar_codigos(um, uid, prontos=prontos))
        assert chegou.wait(20), "a troca não chegou a apagar os códigos"
        zerar = em_fio("zerar", dois, lambda: DF.desativar(dois, uid))
        for _ in range(200):          # o zerar tem de estar ESPERANDO
            if banco(vigia).valor("SELECT count(*) AS n FROM pg_locks "
                                  "WHERE pid = %s AND NOT granted", (pid_dois,)):
                break
            time.sleep(0.05)
        siga.set()
        troca.join(30)
        zerar.join(30)
    finally:
        siga.set()
        for c in (um, dois, vigia):
            c.close()
    assert erros == {}
    with db.connect() as con:
        assert DF.situacao(con, uid)["estado"] == DF.NENHUM
        assert banco(con).valor("SELECT count(*) AS n FROM dois_fatores_recuperacao "
                                "WHERE user_id = %s", (uid,)) == 0


def test_nenhum_pbkdf2_dos_codigos_roda_dentro_da_transacao_da_rota(
        cg_casa, relogio, monkeypatch):
    """A transação da rota abre com a trava de escrita do banco inteiro: os
    dez PBKDF2 da ativação, os da conferência de um código de recuperação e
    os da troca de códigos rodavam lá dentro, e a casa toda esperava. Agora
    se calcula fora e só se grava dentro."""
    db, c = cg_casa["db"], cg_casa["c"]
    uid = db.create_user("escrevente.um", "ESCREVENTE UM DE TESTE", SENHA, "USER")
    _senha(c, "escrevente.um")
    tela = "/conta/dois-fatores"
    _post(c, "/conta/dois-fatores/iniciar", tela)
    with db.connect() as con:
        segredo = DF.segredo_pendente(con, uid, cg_casa["dados"])

    aberta: list = []
    transacoes: list = []
    original = db.transaction

    @contextlib.contextmanager
    def transacao_vigiada():
        with original() as con:
            transacoes.append(1)
            aberta.append(1)
            try:
                yield con
            finally:
                aberta.pop()

    calculos = {"dentro": 0, "fora": 0}
    hash_original = DF.hash_do_codigo

    def hash_vigiado(codigo, sal):
        calculos["dentro" if aberta else "fora"] += 1
        return hash_original(codigo, sal)

    monkeypatch.setattr(db, "transaction", transacao_vigiada)
    monkeypatch.setattr(DF, "hash_do_codigo", hash_vigiado)

    r = _post(c, "/conta/dois-fatores/confirmar", tela, codigo=DF.totp(segredo, T0))
    codigos = re.findall(r"<li><code>([a-z0-9-]+)</code></li>", r.get_data(as_text=True))
    assert len(codigos) == 10
    relogio.t = T0 + 30
    r = _post(c, "/conta/dois-fatores/codigos", tela, senha=SENHA, codigo=codigos[0])
    novos = re.findall(r"<li><code>([a-z0-9-]+)</code></li>", r.get_data(as_text=True))
    assert len(novos) == 10 and not set(novos) & set(codigos)
    assert transacoes, "as rotas não passaram pela transação vigiada"
    assert calculos["fora"] >= 21 and calculos["dentro"] == 0, calculos


def test_codigo_errado_nao_chama_preparar_codigos_em_nenhuma_das_tres_rotas(
        cg_casa, relogio, monkeypatch):
    """LX20 #1: as três rotas calculavam os dez PBKDF2 antes de conferir o
    código, e POST com código errado gastava a CPU do servidor sem limite. O
    TOTP, que é barato, vem primeiro; e a conta bloqueada não chega lá nem
    com o código certo."""
    db, c, dados = cg_casa["db"], cg_casa["c"], cg_casa["dados"]
    chamadas: list = []
    original = DF.preparar_codigos

    def preparar_vigiado(*a, **k):
        chamadas.append(1)
        return original(*a, **k)

    monkeypatch.setattr(DF, "preparar_codigos", preparar_vigiado)

    def errado(segredo, instante):
        return str((int(DF.totp(segredo, instante)) + 1) % 1_000_000).zfill(6)

    # 1. A ativação pela própria tela.
    uid = db.create_user("escrevente.um", "ESCREVENTE UM DE TESTE", SENHA, "USER")
    _senha(c, "escrevente.um")
    tela = "/conta/dois-fatores"
    _post(c, "/conta/dois-fatores/iniciar", tela)
    with db.connect() as con:
        segredo = DF.segredo_pendente(con, uid, dados)
    _post(c, "/conta/dois-fatores/confirmar", tela, codigo=errado(segredo, T0))
    assert "O código não confere" in c.get(tela).get_data(as_text=True)
    assert chamadas == [], "código errado calculou os dez PBKDF2"
    r = _post(c, "/conta/dois-fatores/confirmar", tela, codigo=DF.totp(segredo, T0))
    assert r.get_data(as_text=True).count("<li><code>") == 10 and len(chamadas) == 1

    # 2. A troca de códigos: errado não chega lá; bloqueada, nem o certo.
    relogio.t = T0 + 30
    url = "/conta/dois-fatores/codigos"
    for _ in range(DF.MAX_FALHAS):
        _post(c, url, tela, senha=SENHA, codigo=errado(segredo, relogio.t))
    with db.connect() as con:
        assert DF.situacao(con, uid)["bloqueado_ate"], "cinco erros não bloquearam"
    _post(c, url, tela, senha=SENHA, codigo=DF.totp(segredo, relogio.t))
    assert len(chamadas) == 1

    # 3. A ativação obrigatória, na meia-sessão do login.
    alvo = db.create_user("oficial.teste", "OFICIAL DE TESTE", SENHA, "ADMIN")
    db.set_settings({DF.CHAVE_DA_EXIGENCIA: '["ADMIN"]'})
    outro = cg_casa["app"].test_client()
    _senha(outro, "oficial.teste")
    cadastro = "/login/dois-fatores/cadastrar"
    _post(outro, cadastro, cadastro, acao="iniciar")
    with db.connect() as con:
        chave = DF.segredo_pendente(con, alvo, dados)
    _post(outro, cadastro, cadastro, acao="confirmar", codigo=errado(chave, relogio.t))
    assert len(chamadas) == 1
    with db.connect() as con:
        assert DF.situacao(con, alvo)["estado"] == DF.PENDENTE
    _post(outro, cadastro, cadastro, acao="confirmar", codigo=DF.totp(chave, relogio.t))
    assert len(chamadas) == 2
    with db.connect() as con:
        assert DF.situacao(con, alvo)["estado"] == DF.ATIVO


def test_o_codigo_achado_fora_so_entra_se_ainda_valer_quando_a_transacao_grava(cg_casa, relogio):
    """Ler o código fora da trava não abre brecha: quem decide é o UPDATE com
    `usado_em = ''`. Gasto no meio (outra aba), ou de um jogo já trocado, não
    entra; e o bloqueado nem é calculado."""
    db, dados = cg_casa["db"], cg_casa["dados"]
    uid = db.create_user("escrevente.um", "ESCREVENTE UM DE TESTE", SENHA, "USER")
    _, codigos = _ativar(db, uid, dados)
    with db.connect() as con:
        achado = DF.achar_codigo(con, uid, codigos[1])
        assert achado and DF.achar_codigo(con, uid, "zzzzz-zzzzz") == 0
        assert DF.achar_codigo(con, uid, "123456") == 0
    with db.transaction() as con:
        assert DF.conferir(con, uid, codigos[1], pasta=dados, achado=achado)["ok"]
    with db.transaction() as con:
        segunda = DF.conferir(con, uid, codigos[1], pasta=dados, achado=achado)
    assert not segunda["ok"] and segunda["motivo"] == "codigo"
    with db.connect() as con:
        achado = DF.achar_codigo(con, uid, codigos[2])
    with db.transaction() as con:
        novos = DF.trocar_codigos(con, uid)
    with db.transaction() as con:
        assert not DF.conferir(con, uid, codigos[2], pasta=dados, achado=achado)["ok"]
    with db.transaction() as con:
        banco(con).escrever("UPDATE dois_fatores SET bloqueado_ate = '2999-01-01T00:00:00' "
                            "WHERE user_id = %s", (uid,))
    with db.connect() as con:
        assert DF.achar_codigo(con, uid, novos[0]) == 0


# ------------------------------------------- as outras ressalvas da 2ª leva (LX20)

RAIZ_DO_SISTEMA = Path(__file__).resolve().parents[1]


def test_a_baixa_e_o_avisei_da_barra_fixa_so_voltam_para_caminho_desta_casa():
    """Ressalva da revisão do LX17: `next=/\\fora.exemplo` passava pela régua
    própria do `_destino`, e o navegador lê `\\` como `/` — `//fora.exemplo`."""
    import nu_avisos_web as NAW
    padrao = "/painel"
    assert NAW._destino({"next": "/avisos?aba=2"}, padrao) == "/avisos?aba=2"
    for fora in ("/\\fora.exemplo", "//fora.exemplo", "https://fora.exemplo/",
                 "javascript:alert(1)", "/\t/fora.exemplo", "/\\/fora.exemplo", ""):
        assert NAW._destino({"next": fora}, padrao) == padrao, fora


def test_a_tela_da_leitura_do_rcpn_nao_troca_mais_a_fabrica_de_linhas_da_conexao():
    """Ressalva da revisão do LX13: as duas rotas do rascunho ainda punham a
    fábrica de linhas do SQLite na conexão da ponte, que o `bd_nativo` já
    devolve como dict (critério 1 do MANUAL_DA_CONVERSAO)."""
    fonte = (RAIZ_DO_SISTEMA / "rc_leitura_web.py").read_text(encoding="utf-8")
    assert ("row_" + "factory") not in fonte
    assert "import sqlite3" not in fonte


def test_o_historico_do_balcao_nao_entrega_a_leitura_de_ninguem_a_quem_esta_sem_nome(cg_casa):
    """Observação da revisão do LX13: `lista(so_de=...)` casava nome vazio com
    toda leitura gravada com `criada_por = ''`, enquanto a ficha (`e_de`) não."""
    import rc_leitura_documentos as LEIT
    db = cg_casa["db"]
    uid = db.create_user("escrevente.um", "ESCREVENTE UM DE TESTE", SENHA, "USER")
    with db.transaction() as con:
        bd = banco(con)
        LEIT.init_schema(bd)
        ids = [bd.escrever(
            "INSERT INTO rc_leituras (especie, arquivos_json, criada_em, criada_por) "
            "VALUES ('NASCIMENTO', '[]', '2026-10-20T10:00:00', %s) RETURNING id",
            (por,))[0]["id"] for por in ("", "ESCREVENTE UM DE TESTE", "OUTRA MESA")]
        anexada = bd.escrever(
            "INSERT INTO rc_leituras (especie, arquivos_json, criada_em, criada_por) "
            "VALUES ('OBITO', '[]', '2026-10-20T11:00:00', '') RETURNING id")[0]["id"]
        bd.escrever(
            "INSERT INTO attachments (entity_type, entity_id, original_name, stored_name, "
            "stored_path, sha256, size_bytes, uploaded_by, uploaded_at) "
            "VALUES ('RC_LEITURA', %s, 'dnv.pdf', 'x.pdf', 'x.pdf', 'aa', 1, %s, "
            "'2026-10-20T11:00:00')", (anexada, uid))
    with db.connect() as con:
        sem_nome = [x["id"] for x in LEIT.lista(con, so_de=("", uid))]
        com_nome = [x["id"] for x in LEIT.lista(con, so_de=("ESCREVENTE UM DE TESTE", uid))]
    assert sem_nome == [anexada]
    assert com_nome == [anexada, ids[1]]


def test_o_pacote_cifrado_que_pede_scrypt_sem_fim_e_recusado_antes_de_derivar_a_chave(
        tmp_path, monkeypatch):
    """Observação da revisão do LX14: `n`, `r`, `p` e o bloco vêm do cabeçalho
    e eram usados antes de a senha ser conferida; um pacote fabricado com `n`
    enorme fazia o `abrir` gastar memória e CPU antes de recusar."""
    import json as _json
    import backup
    claro = tmp_path / "claro.zip"
    claro.write_bytes(b"conteudo de teste " * 100)
    cifrado = backup.cifrar_arquivo(claro, tmp_path / "pacote.cgb", "senha de teste longa")
    volta = bytearray()
    backup._decifrar(cifrado, "senha de teste longa", volta.extend)
    assert bytes(volta) == claro.read_bytes()

    derivou: list = []
    aes_original = backup._aes
    monkeypatch.setattr(backup, "_aes", lambda *a: derivou.append(a) or aes_original(*a))
    bruto = cifrado.read_bytes()
    inicio = len(backup.MAGIA_DA_CIFRA)
    fim = bruto.index(b"\n", inicio)
    meta = _json.loads(bruto[inicio:fim])
    for campo, valor in (("n", 2 ** 30), ("r", 1024), ("p", 64), ("bloco", 2 ** 31)):
        forjado = dict(meta, **{campo: valor})
        alvo = tmp_path / f"forjado_{campo}.cgb"
        alvo.write_bytes(bruto[:inicio] + _json.dumps(forjado, sort_keys=True).encode()
                         + bruto[fim:])
        with pytest.raises(backup.BackupInvalido, match="fora do que"):
            backup._decifrar(alvo, "senha de teste longa", lambda _b: None)
    assert derivou == []


# ====================================================================
# LX20 — a ressalva do LX12 (tetos de entrada) fechada com teste.
#
# A revisão do LX12 apontou duas pontas soltas:
#
# 1. `request.max_content_length = teto` (o teto do POST sem login, no
#    `before_request` do `app.py`) só funciona do Flask 3.1 em diante; o
#    `requirements.txt` aceitava o 3.0, em que a mesma linha dá 500 em todo POST
#    sem login — o próprio login.
# 2. `TetoExcedido` sem conversão em `modelos_moldes.marcadores_de`,
#    `gestor_cargas_ri._converter_uma` e `ri_digitalizacao.paginas_png` /
#    `miniatura_png`. Medido chamador a chamador: os da digitalização e o da
#    carga do ONR já apanham `ValueError` (ou `Exception`) antes da rota — a
#    varredura abaixo prova e passa a vigiar. O que estava solto de verdade era
#    o molde cujo índice mente (a recusa escapava de `conferir` e a tela dizia só
#    «Não deu para gravar o papel») e a página gigante no MEIO do PDF da
#    matrícula, recusada depois de as imagens velhas já terem sido apagadas.
#
# Os dados são os fictícios da casa: nenhum nome ou documento de gente real.
# ====================================================================

import ast
import io
import re
import struct
import sys
import zipfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

SENHA = "Senha#12345"


def _lx20t_token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _lx20t_pdf(alturas: list[float], *, largura: float = 595) -> bytes:
    import pymupdf
    doc = pymupdf.open()
    for altura in alturas:
        doc.new_page(width=largura, height=altura)
    try:
        return doc.tobytes()
    finally:
        doc.close()


def _lx20t_odt_que_mente(*, declarado: int = 200) -> bytes:
    """Um `.odt` cujo índice diz que o `content.xml` tem `declarado` bytes,
    e ele traz cem mil — a zip-bomba que passa por `conferir_pacote` (que só
    lê o índice) e só se revela na leitura."""
    xml = ('<?xml version="1.0" encoding="UTF-8"?><office:document-content>'
           '<office:body>@MATRICULA' + " " * 100_000
           + '</office:body></office:document-content>')
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        z.writestr("content.xml", xml)
    bruto = bytearray(saida.getvalue())
    verdade = struct.pack("<I", len(xml.encode()))
    trocas = 0
    i = bruto.find(verdade)
    while i != -1:                  # o cabeçalho local e o diretório central
        bruto[i:i + 4] = struct.pack("<I", declarado)
        trocas += 1
        i = bruto.find(verdade, i + 4)
    assert trocas == 2
    return bytes(bruto)


# ------------------------------------------------ 1. o piso do Flask


def test_o_requirements_exige_o_flask_que_aceita_o_teto_gravado_no_pedido():
    """No 3.0, `Request.max_content_length` é só leitura: o `before_request`
    que grava o teto do POST sem login daria 500 no login de todo mundo."""
    linhas = [l.strip() for l in (RAIZ / "requirements.txt").read_text(
        encoding="utf-8").splitlines()]
    flask = [l for l in linhas if re.match(r"(?i)flask\s*[<>=]", l)]
    assert flask == ["Flask>=3.1,<4"]


def test_o_flask_instalado_aceita_gravar_o_teto_no_pedido():
    from importlib.metadata import version
    maior, menor = (int(x) for x in version("flask").split(".")[:2])
    assert (maior, menor) >= (3, 1)
    from flask import Flask, request
    app = Flask(__name__)
    with app.test_request_context("/", method="POST"):
        request.max_content_length = 10
        assert request.max_content_length == 10


@pytest.fixture()
def _lx20t_casa(cg_casa):
    """Com um usuário: sem nenhum, toda rota vai para o `/setup`."""
    cg_casa["db"].create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    return cg_casa


class _Lx20tContador(io.BytesIO):
    """O corpo do pedido, contando quanto o servidor leu dele."""
    lidos = 0

    def read(self, n=-1):
        pedaco = super().read(n)
        self.lidos += len(pedaco)
        return pedaco

    def readline(self, n=-1):
        pedaco = super().readline(n)
        self.lidos += len(pedaco)
        return pedaco

    def readinto(self, b):
        n = super().readinto(b)
        self.lidos += n or 0
        return n


def _lx20t_em_pedacos(c, corpo: bytes):
    """POST no `/login` em pedaços (`Transfer-Encoding: chunked`): sem
    `Content-Length`, o teto do `before_request` não tem como recusar antes de
    ler. Devolve a resposta e quantos bytes o servidor leu."""
    fonte = _Lx20tContador(corpo)
    r = c.post("/login", input_stream=fonte,
               content_type="application/x-www-form-urlencoded",
               headers={"Transfer-Encoding": "chunked"},
               environ_overrides={"wsgi.input_terminated": True})
    return r, fonte.lidos


def test_o_post_anonimo_em_pedacos_nao_e_lido_alem_do_teto(_lx20t_casa, monkeypatch):
    """O corpo em pedaços não diz o tamanho: quem o segura é o teto gravado
    no pedido (`request.max_content_length`), na leitura. Medido no Werkzeug
    3.1: o formulário para no teto e o resto nem se lê — o token, que não
    chegou, recusa com 400. Sem a linha, o corpo inteiro era lido; no Flask
    3.0, a linha dava 500."""
    monkeypatch.setenv("CG_TETO_CORPO_ANONIMO_BYTES", "1000")
    c = _lx20t_casa["app"].test_client()
    r, lidos = _lx20t_em_pedacos(c, b"username=mario&password=" + b"x" * 50_000)
    assert r.status_code in (400, 413)
    assert lidos <= 1000


def test_o_post_anonimo_pequeno_sem_content_length_continua_entrando(_lx20t_casa, monkeypatch):
    monkeypatch.setenv("CG_TETO_CORPO_ANONIMO_BYTES", "100000")
    c = _lx20t_casa["app"].test_client()
    token = _lx20t_token(c.get("/login").get_data(as_text=True))
    corpo = f"username=mario&password={SENHA}&csrf_token={token}".encode()
    corpo = corpo.replace(b"#", b"%23")
    r, _ = _lx20t_em_pedacos(c, corpo)
    assert r.status_code == 302 and "/login" not in r.headers["Location"]


# ------------------------------------------------ 2. o molde cujo índice mente


def test_o_molde_cujo_indice_mente_volta_como_recusa_e_nao_como_excecao():
    import modelos_moldes as MOLDES
    erro = MOLDES.conferir("RC_MOLDE_NASCIMENTO", _lx20t_odt_que_mente())
    assert erro and "índice do pacote não confere" in erro


def test_o_teto_estourado_na_leitura_do_molde_volta_com_a_frase_do_teto(monkeypatch):
    """O corte de `ler_membro` (leitura além do teto) também é recusa, com a
    frase que diz o teto — e não exceção solta."""
    import modelos_moldes as MOLDES
    import tetos_de_entrada as TETO

    def _corta(pacote, nome):
        raise TETO.TetoExcedido("«content.xml» passa do teto ao abrir.")
    monkeypatch.setattr(MOLDES.TETO, "ler_membro", _corta)
    assert MOLDES.conferir("RC_MOLDE_NASCIMENTO", _lx20t_odt_que_mente()) == (
        "«content.xml» passa do teto ao abrir.")


def test_a_tela_de_modelos_mostra_por_que_recusou_o_molde_que_mente(_lx20t_casa):
    c = _lx20t_casa["cliente"]
    c.post("/login", data={"username": "mario", "password": SENHA,
                           "csrf_token": _lx20t_token(c.get("/login").get_data(as_text=True))})
    html = c.get("/modelos").get_data(as_text=True)
    r = c.post("/modelos/molde", data={
        "csrf_token": _lx20t_token(html), "chave": "RC_MOLDE_NASCIMENTO",
        "acao": "enviar", "arquivo": (io.BytesIO(_lx20t_odt_que_mente()), "molde.odt")},
        content_type="multipart/form-data", follow_redirects=True)
    assert r.status_code == 200
    texto = r.get_data(as_text=True)
    assert "índice do pacote não confere" in texto
    assert "Não deu para gravar o papel" not in texto


# ------------------------------------------------ 3. a matrícula com meia ficha


def test_a_pagina_gigante_no_meio_do_pdf_nao_apaga_as_imagens_velhas_da_matricula(
        monkeypatch, tmp_path):
    """O teto de páginas já vinha antes de apagar; o de área, só dentro de
    `pagina_em_tiff` — a 2ª página recusada deixava a ficha com a 1ª nova e
    sem as outras velhas."""
    import gestor_cargas_ri as G
    monkeypatch.setenv("CG_TETO_PIXELS_POR_PAGINA", "5000000")
    pdf = tmp_path / "m.pdf"
    pdf.write_bytes(_lx20t_pdf([842, 842 * 20]))
    pasta = tmp_path / "csl2" / "00000000"
    pasta.mkdir(parents=True)
    velhas = [pasta / f"00000007.000{i}" for i in (1, 2, 3)]
    for v in velhas:
        v.write_bytes(b"II*\x00velha")
    with pytest.raises(ValueError, match="grande demais"):
        G._converter_uma(pdf, tmp_path / "csl2", 7)
    assert [v.read_bytes() for v in velhas] == [b"II*\x00velha"] * 3
    assert sorted(p.name for p in pasta.iterdir()) == [v.name for v in velhas]


# ------------------------------------------------ 4. ninguém deixa o teto virar 500

#: Quem levanta `TetoExcedido` (um `ValueError`) a partir de arquivo do balcão.
_LX20T_SEMENTES = {"paginas_png", "miniatura_png", "marcadores_de",
                   "_converter_uma", "pagina_em_tiff"}
_LX20T_APANHA = {"ValueError", "Exception", "BaseException", "TetoExcedido"}


def _lx20t_apanha(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return True
    tipos = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
    for t in tipos:
        nome = t.attr if isinstance(t, ast.Attribute) else getattr(t, "id", "")
        if nome in _LX20T_APANHA:
            return True
    return False


def _lx20t_e_rota(func) -> bool:
    for d in func.decorator_list:
        alvo = d.func if isinstance(d, ast.Call) else d
        if isinstance(alvo, ast.Attribute) and alvo.attr in ("route", "get", "post"):
            return True
    return False


def _lx20t_soltos(fontes: dict[str, str]) -> list[str]:
    """As ROTAS por onde a recusa de teto subiria sem `except` — direto ou por
    função intermediária que também não apanha (propaga pelo nome, até
    parar). Devolve `arquivo:rota <- chamada`."""
    chamadas: list[tuple[str, ast.AST, str]] = []   # (arquivo, função, chamado)

    def visitar(no, arquivo, funcao, protegido):
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for filho in no.body:
                visitar(filho, arquivo, no, False)
            return
        if isinstance(no, ast.Try):
            cobre = any(_lx20t_apanha(h) for h in no.handlers)
            for filho in no.body:
                visitar(filho, arquivo, funcao, protegido or cobre)
            for filho in [*no.handlers, *no.orelse, *no.finalbody]:
                visitar(filho, arquivo, funcao, protegido)
            return
        if isinstance(no, ast.Call) and funcao is not None and not protegido:
            f = no.func
            nome = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
            if nome:
                chamadas.append((arquivo, funcao, nome))
        for filho in ast.iter_child_nodes(no):
            visitar(filho, arquivo, funcao, protegido)

    for arquivo, texto in fontes.items():
        visitar(ast.parse(texto), arquivo, None, False)

    sobem = set(_LX20T_SEMENTES)
    while True:
        novos = {f.name for _, f, nome in chamadas if nome in sobem} - sobem
        if not novos:
            break
        sobem |= novos
    return sorted({f"{arq}:{f.name} <- {nome}" for arq, f, nome in chamadas
                   if nome in sobem and _lx20t_e_rota(f)})


def test_a_varredura_acha_a_rota_que_deixaria_o_teto_virar_500():
    """A régua se prova antes de valer: rota que chama a digitalização sem
    `except` — direto ou por um ajudante — aparece; a que apanha, não."""
    fonte = (
        "def ajudante(c):\n"
        "    return paginas_png(c)\n"
        "def registrar(app):\n"
        "    @app.route('/a')\n"
        "    def a():\n"
        "        return ajudante(1)\n"
        "    @app.route('/b')\n"
        "    def b():\n"
        "        try:\n"
        "            return RDIGI.miniatura_png(1)\n"
        "        except ValueError:\n"
        "            return ''\n")
    assert _lx20t_soltos({"x.py": fonte}) == ["x.py:a <- ajudante"]


def test_nenhuma_rota_deixa_a_recusa_de_teto_da_digitalizacao_virar_500():
    """Medido no LX20: todos os chamadores (ri_web, atribuicoes_web,
    rc_digitalizacao_web, ra_digitalizacao_web, certidao_folhas, a carga do
    ONR, a tela de Modelos) apanham `ValueError`/`Exception` antes da rota.
    Este teste vigia o próximo que chegar."""
    fontes = {p.name: p.read_text(encoding="utf-8") for p in sorted(RAIZ.glob("*.py"))}
    assert _lx20t_soltos(fontes) == []


# ====================================================================
# LX20 — as ressalvas do LG04 que conferiam a situação sem prender a linha.
#
# O QUE ESTES TESTES PROTEGEM
#
#     a venda ao DETRAN        dois cliques em «Comunicar» mandavam a mesma venda
#                              duas vezes, e a segunda resposta escrevia por cima
#                              da primeira (CONFIRMADA virando RECUSADA, o
#                              protocolo à mão também). Agora a ida é reservada
#                              (ENVIADA) numa transação curta, a rede fica fora,
#                              e o fecho só vale sobre a própria reserva
#     o protocolo à mão        prende a linha da conferência à gravação
#     o tipo do testamento     «já foi ao RCTO?» e a troca vão na mesma transação,
#                              com o ato preso; a remessa que se registra prende
#                              os mesmos atos (`NC.separar(..., para_gravar=True)`)
#     a certidão de notificação  a trava do número vem antes da linha, como no
#                              resto da casa
#
# Com a ponte, o `BEGIN IMMEDIATE` deixa um escritor por vez no banco inteiro e
# esconde a falta da trava; por isso os testes de linha presa olham o PostgreSQL
# por outra conexão, sem a ponte. Dados fictícios; ninguém fala com o DETRAN.
# ====================================================================

import sys
import threading
import time
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import banco_pg
import bd_nativo
import notas_censec as NC
import notas_web
import nt_veiculo_detran as V
import rg_notificacao as RN
from bd_nativo import banco
from conftest import cg_login

SENHA = "Senha#12345"
AGORA = "2026-10-19T10:00:00"
HOJE = "2026-10-19"
CPF_VENDEDOR = "00000000191"
CPF_COMPRADOR = "11144477735"

sem_a_ponte = pytest.mark.skipif(
    not banco_pg.ativo(), reason="a linha presa só se vê no PostgreSQL")


def _lx20n_psycopg_puro(casa, *, autocommit=False):
    """Uma conexão do psycopg no schema do teste, SEM a ponte."""
    import psycopg
    pg = psycopg.connect(banco_pg.dsn(), autocommit=autocommit)
    pg.execute(f'SET search_path TO "{banco_pg.schema_do_caminho(casa["banco"])}", public')
    if not autocommit:
        pg.commit()
    return pg


def _lx20n_presa(vigia, tabela: str, linha_id: int) -> bool:
    """A linha está presa por outra transação? (FOR UPDATE NOWAIT da vigia)."""
    import psycopg
    try:
        vigia.execute(f"SELECT id FROM {tabela} WHERE id = %s FOR UPDATE NOWAIT",
                      (int(linha_id),))
    except psycopg.errors.LockNotAvailable:
        return True
    return False


def _lx20n_ao_mesmo_tempo(casa, primeira, segunda):
    """A `primeira` grava e ainda não confirmou; a `segunda` chega no meio,
    por outra conexão. Devolve o erro da segunda (None se ela passou)."""
    um, dois = _lx20n_psycopg_puro(casa), _lx20n_psycopg_puro(casa)
    vigia = _lx20n_psycopg_puro(casa, autocommit=True)
    pid = banco(dois).valor("SELECT pg_backend_pid() AS pid")
    primeira(um)
    saida: dict = {}

    def no_fio():
        try:
            segunda(dois)
            dois.commit()
        except Exception as erro:  # o teste confere qual
            saida["erro"] = erro
            dois.rollback()

    fio = threading.Thread(target=no_fio)
    fio.start()
    for _ in range(200):          # a segunda tem de estar ESPERANDO
        if banco(vigia).valor(
                "SELECT count(*) AS n FROM pg_locks WHERE pid=%s AND NOT granted",
                (pid,)):
            break
        time.sleep(0.05)
    um.commit()
    fio.join(30)
    for c in (um, dois, vigia):
        c.close()
    return saida.get("erro")


# ------------------------------------------------------------ o DETRAN

@pytest.fixture()
def _lx20n_detran(cg_casa, tmp_path):
    """Uma comunicação já selada, a integração ligada e a credencial em tmp."""
    db = cg_casa["db"]
    cred = tmp_path / V.ARQUIVO_DA_CREDENCIAL
    V.gravar_credencial(usuario="usuario.teste", senha="senha-de-teste",
                        ambiente_=V.HOMOLOGACAO, pasta=cred)
    with db.transaction() as con:
        cid = int(banco(con).escrever(
            """INSERT INTO nt_comunicacoes_veiculo(documento, placa, renavam,
                   vendedor_nome, vendedor_documento, comprador_nome,
                   comprador_documento, data_venda, selo, criado_em)
               VALUES ('ATPV_E', 'ABC1D23', '00639884962', 'FULANO DE TAL EXEMPLO',
                       %s, 'BELTRANO DE EXEMPLO', %s, '2026-10-10',
                       'COMVEI0000000001', %s) RETURNING id""",
            (CPF_VENDEDOR, CPF_COMPRADOR, AGORA))[0]["id"])
    config = {V.CHAVE_LIGADA: "1", V.CHAVE_AMBIENTE: V.HOMOLOGACAO}
    return {"casa": cg_casa, "db": db, "cid": cid, "cred": cred,
            "get_setting": lambda chave, padrao=None: config.get(chave, padrao)}


class _Lx20nDetranLento(V.TransporteFalso):
    """O falso que segura a resposta até o teste soltar — a ida «na rede»."""

    def __init__(self):
        super().__init__()
        self.chegou, self.soltar = threading.Event(), threading.Event()

    def enviar(self, comunicacao, credencial, ambiente):
        self.chegou.set()
        assert self.soltar.wait(30), "o teste não soltou a resposta"
        return super().enviar(comunicacao, credencial, ambiente)


def _lx20n_enviar_no_fio(d, transporte, agora=AGORA):
    saida: dict = {}

    def ir():
        try:
            saida["r"] = V.enviar(d["db"], d["cid"], get_setting=d["get_setting"],
                                  agora=agora, usuario="BALCAO UM",
                                  transporte=transporte,
                                  pasta_da_credencial=d["cred"])
        except Exception as erro:  # o teste confere qual
            saida["erro"] = erro

    fio = threading.Thread(target=ir)
    fio.start()
    assert transporte.chegou.wait(30), "a primeira ida não chegou à rede"
    return fio, saida


def _lx20n_comunicacao(d) -> dict:
    with d["db"].connect() as con:
        return V.comunicacao(con, d["cid"])


def test_o_segundo_clique_em_comunicar_nao_manda_a_venda_de_novo_ao_detran(_lx20n_detran):
    d = _lx20n_detran
    lento = _Lx20nDetranLento()
    fio, saida = _lx20n_enviar_no_fio(d, lento)
    try:
        assert _lx20n_comunicacao(d)["situacao"] == "ENVIADA"
        with pytest.raises(V.DetranError, match="sendo enviada ao DETRAN agora"):
            V.enviar(d["db"], d["cid"], get_setting=d["get_setting"],
                     agora=AGORA, usuario="BALCAO DOIS", transporte=lento,
                     pasta_da_credencial=d["cred"])
    finally:
        lento.soltar.set()
        fio.join(30)
    assert "erro" not in saida, saida
    assert len(lento.recebidas) == 1
    com = _lx20n_comunicacao(d)
    assert (com["situacao"], com["protocolo_detran"], com["tentativas"]) == (
        "CONFIRMADA", "HML-000001", 1)


def test_o_protocolo_a_mao_nao_entra_com_a_venda_a_caminho_do_detran(_lx20n_detran):
    """Antes, o à mão gravava COMUNICADA_A_MAO e a resposta da rede, chegando
    depois, trocava-o por CONFIRMADA (ou RECUSADA) — dois protocolos, um só
    valendo, e não o que o balcão digitou."""
    d = _lx20n_detran
    lento = _Lx20nDetranLento()
    fio, saida = _lx20n_enviar_no_fio(d, lento)
    try:
        with pytest.raises(V.DetranError, match="sendo enviada ao DETRAN agora"):
            with d["db"].transaction() as con:
                V.registrar_protocolo_a_mao(con, d["cid"], protocolo="PORTAL-77",
                                            agora=AGORA, usuario="BALCAO DOIS")
    finally:
        lento.soltar.set()
        fio.join(30)
    com = _lx20n_comunicacao(d)
    assert (com["situacao"], com["protocolo_detran"]) == ("CONFIRMADA", "HML-000001")


def test_a_resposta_atrasada_nao_apaga_o_protocolo_dado_depois_do_prazo(_lx20n_detran):
    """A ida que passou do prazo é dada por morta e o balcão comunica à mão;
    se ela responder depois, a resposta não escreve por cima."""
    d = _lx20n_detran
    lento = _Lx20nDetranLento()
    fio, saida = _lx20n_enviar_no_fio(d, lento)
    try:
        depois = "2026-10-19T10:15:00"          # passado o prazo da ida (10 min)
        with d["db"].transaction() as con:
            V.registrar_protocolo_a_mao(con, d["cid"], protocolo="PORTAL-77",
                                        agora=depois, usuario="BALCAO DOIS")
    finally:
        lento.soltar.set()
        fio.join(30)
    com = _lx20n_comunicacao(d)
    assert (com["situacao"], com["protocolo_detran"]) == ("COMUNICADA_A_MAO", "PORTAL-77")
    assert saida["r"]["aceito"] and "não gravada" in saida["r"]["mensagem"]


def test_a_ida_que_morreu_no_meio_se_manda_de_novo_passado_o_prazo(_lx20n_detran):
    d = _lx20n_detran
    with d["db"].transaction() as con:
        banco(con).escrever(
            "UPDATE nt_comunicacoes_veiculo SET situacao = 'ENVIADA', enviada_em = %s "
            "WHERE id = %s", (AGORA, d["cid"]))
    falso = V.TransporteFalso()
    with pytest.raises(V.DetranError, match="sendo enviada"):
        V.enviar(d["db"], d["cid"], get_setting=d["get_setting"],
                 agora="2026-10-19T10:05:00", transporte=falso,
                 pasta_da_credencial=d["cred"])
    r = V.enviar(d["db"], d["cid"], get_setting=d["get_setting"],
                 agora="2026-10-19T10:30:00", transporte=falso,
                 pasta_da_credencial=d["cred"])
    assert r["aceito"] and len(falso.recebidas) == 1
    assert _lx20n_comunicacao(d)["situacao"] == "CONFIRMADA"


def test_a_recusa_do_transporte_antes_da_rede_desfaz_a_reserva(_lx20n_detran):
    d = _lx20n_detran
    with d["db"].transaction() as con:
        banco(con).escrever("UPDATE nt_comunicacoes_veiculo SET situacao = 'RECUSADA' "
                            "WHERE id = %s", (d["cid"],))
    with pytest.raises(V.DetranError, match="leiaute"):
        V.enviar(d["db"], d["cid"], get_setting=d["get_setting"], agora=AGORA,
                 transporte=V.TransporteNaoConfigurado(),
                 pasta_da_credencial=d["cred"])
    com = _lx20n_comunicacao(d)
    assert (com["situacao"], com["enviada_em"]) == ("RECUSADA", None)


@sem_a_ponte
def test_dois_protocolos_a_mao_ao_mesmo_tempo_nao_passam_os_dois(_lx20n_detran):
    """Sem a linha presa, o segundo passava pela conferência e trocava o
    protocolo do primeiro pelo dele."""
    d = _lx20n_detran

    def a_mao(numero):
        return lambda c: V.registrar_protocolo_a_mao(
            c, d["cid"], protocolo=numero, agora=AGORA, usuario="BALCAO")

    erro = _lx20n_ao_mesmo_tempo(d["casa"], a_mao("PORTAL-1"), a_mao("PORTAL-2"))
    assert isinstance(erro, V.DetranError), erro
    assert "já foi comunicada" in str(erro)
    assert _lx20n_comunicacao(d)["protocolo_detran"] == "PORTAL-1"


# ------------------------------------------------------- o tipo do testamento

def _lx20n_testamento(db, tipo_testamento=4) -> int:
    with db.transaction() as con:
        bd = banco(con)
        ato_id = int(bd.escrever(
            """INSERT INTO nt_atos (tipo, serie, data, situacao, livro, folha,
                   termo, tipo_testamento, teor, teor_formato, origem, criado_em)
               VALUES ('TESTAMENTO', 'TESTAMENTO', %s, 'LAVRADO', 'T-1', '7', 1,
                       %s, '<p>TEOR DE EXEMPLO DO TESTAMENTO.</p>', 'html',
                       'MANUAL', %s) RETURNING id""",
            (HOJE, tipo_testamento, AGORA))[0]["id"])
        bd.escrever(
            """INSERT INTO nt_ato_partes (ato_id, nome, documento, qualificacao,
                   testemunha, ordem, criado_em)
               VALUES (%s, 'FULANO DE EXEMPLO', %s, 'TESTADOR', 0, 1, %s)""",
            (ato_id, CPF_COMPRADOR, AGORA))
    return ato_id


@sem_a_ponte
def test_a_ficha_confere_o_rcto_e_troca_o_tipo_com_o_ato_preso(cg_casa, monkeypatch):
    """O «já foi ao RCTO?» e o UPDATE rodam com a linha do ato presa — a mesma
    que a remessa prende ao registrar. Lido fora, a remessa separada no meio
    levava um tipo e a ficha ficava com outro."""
    db, c = cg_casa["db"], cg_casa["c"]
    db.create_user("tabeliao", "TABELIAO DE EXEMPLO", SENHA, "ADMIN")
    cg_login(c, "tabeliao", SENHA)
    ato_id = _lx20n_testamento(db)
    vigia = _lx20n_psycopg_puro(cg_casa, autocommit=True)
    visto: dict = {}

    class Espia(bd_nativo.Banco):
        def _rodar(self, sql, parametros=None):
            if "AS ja FROM nt_remessa_itens" in sql:
                visto["conferencia"] = _lx20n_presa(vigia, "nt_atos", ato_id)
            elif "SET tipo_testamento" in sql:
                visto["troca"] = _lx20n_presa(vigia, "nt_atos", ato_id)
            return super()._rodar(sql, parametros)

    import re
    html = c.get(f"/notas/atos/{ato_id}").get_data(as_text=True)
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)
    monkeypatch.setattr(notas_web, "banco", Espia)
    try:
        c.post(f"/notas/atos/{ato_id}",
               data={"acao": "tipo_testamento", "tipo_testamento": "6",
                     "csrf_token": token})
    finally:
        vigia.close()
    assert visto == {"conferencia": True, "troca": True}
    with db.connect() as con:
        assert banco(con).valor("SELECT tipo_testamento FROM nt_atos WHERE id = %s",
                                (ato_id,)) == 6


@sem_a_ponte
def test_a_remessa_que_se_registra_prende_os_atos_e_a_conferencia_nao(cg_casa):
    db = cg_casa["db"]
    ato_id = _lx20n_testamento(db)
    quinzena = 2 if int(HOJE[8:10]) > 15 else 1
    um = _lx20n_psycopg_puro(cg_casa)
    vigia = _lx20n_psycopg_puro(cg_casa, autocommit=True)
    try:
        NC.separar(um, "RCTO", 2026, 10, quinzena)
        assert not _lx20n_presa(vigia, "nt_atos", ato_id)
        um.rollback()
        carga = NC.gerar(um, "RCTO", 2026, 10, quinzena, "999999")
        assert ato_id in [x["ato"]["id"] for x in carga["aptos"] + carga["impedidos"]]
        assert _lx20n_presa(vigia, "nt_atos", ato_id)
        um.rollback()
        assert not _lx20n_presa(vigia, "nt_atos", ato_id)
    finally:
        um.close()
        vigia.close()


# ------------------------------------------------- a certidão de notificação

def test_a_certidao_de_notificacao_trava_o_numero_antes_de_prender_a_linha(cg_casa,
                                                                         monkeypatch):
    """Assunto primeiro, linha depois — a ordem de `rg_livro_contabil.autenticar`
    e do resto da casa. A ordem invertida é a receita do deadlock."""
    comandos: list[str] = []

    class Espia(bd_nativo.Banco):
        def _rodar(self, sql, parametros=None):
            if "pg_advisory_xact_lock" in sql:
                comandos.append(f"trava:{parametros[0]}")
            elif "FOR UPDATE" in sql:
                comandos.append("linha")
            return super()._rodar(sql, parametros)

    monkeypatch.setattr(RN, "banco", Espia)
    with pytest.raises(RN.NotificacaoError, match="não encontrada"):
        with cg_casa["db"].transaction() as con:
            RN.emitir_certidao(con, 987654321, agora=AGORA, sv={},
                               data_extenso="dezenove de outubro de 2026")
    assert comandos[:2] == ["trava:rg_notificacao_certidoes.numero", "linha"]


# ====================================================================
# LX20 — as ressalvas da revisão do LX16 (selo pago × protocolo/caixa).
#
# O QUE ESTES TESTES PROTEGEM
#     - o relatório «selos pagos sem cobertura» não perde o selo descoberto que
#       vem depois de muitos cobertos (o LIMIT era aplicado antes do filtro), e a
#       tela diz quando ficou selo de fora;
#     - o débito do depósito não fica gravado quando o selo não sai (a unidade
#       que não se gasta no passo 3, e a cobertura que não cobre);
#     - as ações do quadro (ligar, usar depósito, diferir) só valem para item do
#       protocolo que o escrevente está atendendo — ou já ligado ao ato —, com o
#       protocolo aberto e o ato existente; `item_id` com texto é 400, e não 500.
# ====================================================================

import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

import ato_selado as AS                         # noqa: E402
import caixa_protocolo as CXP                   # noqa: E402
from bd_nativo import banco as _lx20s_banco     # noqa: E402

_LX20S_AGORA = "2026-10-19T10:00:00"
_LX20S_ESCREVENTE = "FULANA DE EXEMPLO"
_LX20S_PAGO = {"ato": {"codigo": "16.1", "codigoTabelaCusta": "0320260101"},
               "escrevente": _LX20S_ESCREVENTE}
_LX20S_ABERTAS: list = []


@pytest.fixture(autouse=True)
def _lx20s_fechar_as_conexoes():
    """Conexão esquecida segura trava e vaga no servidor."""
    yield
    while _LX20S_ABERTAS:
        try:
            _LX20S_ABERTAS.pop().close()
        except Exception:                      # noqa: BLE001
            pass


def _lx20s_casa():
    """Protesto, razão, caixa e a trava do selo — o banco de `test_selo_e_caixa`."""
    from banco_de_teste import conexao_de_teste
    from caixa_schema import init_caixa_schema
    from nucleo_schema import init_nucleo_schema
    from pt_schema import init_pt_schema
    from selador_config import init_selador_schema
    con = conexao_de_teste()
    _LX20S_ABERTAS.append(con)
    init_nucleo_schema(con)
    init_pt_schema(con)
    init_selador_schema(con)
    bd = _lx20s_banco(con)
    bd.escrever("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    bd.escrever("""CREATE TABLE IF NOT EXISTS audit_logs (
        id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY, ts TEXT NOT NULL,
        user_id INTEGER, username_snapshot TEXT, action TEXT NOT NULL,
        entity_type TEXT, entity_id INTEGER, details TEXT, ip_address TEXT)""")
    for tabela in ("users", "ri_protocolos", "ri_matriculas"):
        bd.escrever(f"CREATE TABLE IF NOT EXISTS {tabela} (id INTEGER PRIMARY KEY)")
    init_caixa_schema(con)
    AS.init_trava_do_selo_schema(con)
    bd.escrever("""INSERT INTO pt_titulos(especie, numero_titulo, situacao, origem, criado_em)
                   VALUES ('DMI','84713/1','APONTADO','MANUAL',%s)""", (_LX20S_AGORA,))
    for _ in range(3):
        bd.escrever("""INSERT INTO pt_atos(titulo_id, tipo, data_ato, origem, criado_em)
                       VALUES (1,'APONTAMENTO',%s,'MANUAL',%s)""", (_LX20S_AGORA, _LX20S_AGORA))
    con.commit()
    return con


class _Lx20sDb:
    """O `db` da casa sobre a conexão do teste: transação que confirma ou volta."""

    def __init__(self, con):
        self.con = con

    @contextmanager
    def transaction(self):
        try:
            yield self.con
            self.con.commit()
        except BaseException:
            self.con.rollback()
            raise

    @contextmanager
    def connect(self):
        yield self.con

    def now(self):
        return _LX20S_AGORA

    def get_setting(self, chave, padrao=""):
        return padrao

    def list_users(self, active_only=True):
        return []


@pytest.fixture()
def _lx20s_aparelho(monkeypatch):
    """O dublê do aparelho: grava no razão e conta os pedidos."""
    import selador
    import selador_cliente as CL
    pedidos = []

    def falso_selar(con, pasta, caminho, dados, *, referencia, atribuicao,
                    agora, cns, tentativa=1, usuario=None, **_):
        numero = f"SELOEXEMPLO{len(pedidos) + 1:04d}"
        pedidos.append(str(referencia))
        _lx20s_banco(con).escrever(
            """INSERT INTO sd_selos(numero, texto, sid, caminho, atribuicao,
                   referencia, ambiente, obtido_em, obtido_por)
               VALUES (%s,'Selo pago',%s,%s,%s,%s,'HOMOLOGACAO',%s,%s)""",
            (numero, f"sid-{numero}", caminho, atribuicao, str(referencia),
             agora, usuario))
        return [selador.SeloGerado(numero=numero, texto="Selo pago")]

    monkeypatch.setattr(CL, "selar", falso_selar)
    return pedidos


def _lx20s_selar(con, *, ato_id=1):
    return AS.selar_o_ato_lavrado(
        _Lx20sDb(con), "/tmp", tabela="pt_atos", ato_id=ato_id, tipo="APONTAMENTO",
        atribuicao="PROTESTO", agora=_LX20S_AGORA, cns="000000",
        usuario=_LX20S_ESCREVENTE, dados=dict(_LX20S_PAGO),
        caminho="/selo/protesto/titulo")


def _lx20s_protocolo(con, *, atribuicao="PROTESTO"):
    feito = CXP.abrir(con, data_abertura="2026-10-19", agora=_LX20S_AGORA,
                      atribuicao=atribuicao, interessado="CLIENTE DE EXEMPLO")
    con.commit()
    return feito


def _lx20s_item(con, protocolo_id, *, codigo="16.1", valor="80,00", quitado=0,
                quantidade=1):
    novo = _lx20s_banco(con).escrever(
        """INSERT INTO cx_protocolo_atos (protocolo_id, descricao, codigo_ato,
               quantidade, valor_total, quitado)
           VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
        (protocolo_id, f"Item {codigo}", codigo, quantidade, valor, quitado))
    con.commit()
    return int(novo[0]["id"])


def _lx20s_deposito(con, protocolo_id, valor="100,00", numero="DP2026.10.1"):
    novo = _lx20s_banco(con).escrever(
        """INSERT INTO cx_depositos (numero, data, depositante, valor, saldo,
               protocolo_id, criado_em)
           VALUES (%s,'2026-10-18','CLIENTE DE EXEMPLO',%s,%s,%s,%s) RETURNING id""",
        (numero, valor, valor, protocolo_id, _LX20S_AGORA))
    con.commit()
    return int(novo[0]["id"])


def _lx20s_saldo(con, deposito_id):
    from caixa_schema import centavos
    return centavos(_lx20s_banco(con).valor(
        "SELECT saldo FROM cx_depositos WHERE id = %s", (deposito_id,)))


def _lx20s_item_lido(con, item_id):
    return _lx20s_banco(con).um("SELECT * FROM cx_protocolo_atos WHERE id = %s",
                                (item_id,))


def _lx20s_selos_cobertos_e_um_descoberto(con, cobertos: int) -> None:
    """`cobertos` selos pagos e cobertos, e depois deles um sem cobertura."""
    bd = _lx20s_banco(con)
    bd.escrever(
        """INSERT INTO sd_selos (numero, texto, tabela, ato_id, obtido_em, obtido_por)
           SELECT 'SELOCOBERTO' || lpad(n::text, 4, '0'), 'Selo pago', 'pt_atos',
                  1000 + n, '2026-10-02T10:00:00', %s
             FROM generate_series(1, %s) AS n""", (_LX20S_ESCREVENTE, cobertos))
    bd.escrever(
        """INSERT INTO cx_selo_coberturas (referencia, tabela, ato_id, forma, criado_em)
           SELECT 'pt_atos:' || (1000 + n), 'pt_atos', 1000 + n, %s, %s
             FROM generate_series(1, %s) AS n""",
        (AS.FORMA_ITEM_PAGO, _LX20S_AGORA, cobertos))
    bd.escrever(
        """INSERT INTO sd_selos (numero, texto, tabela, ato_id, obtido_em, obtido_por)
           VALUES ('SELODESCOBERTO1', 'Selo pago', 'pt_atos', 999, '2026-10-03T10:00:00', %s)""",
        (_LX20S_ESCREVENTE,))
    con.commit()


# ------------------------------- achado 1: o LIMIT vinha antes do filtro


def test_o_relatorio_de_pagos_sem_cobertura_acha_o_descoberto_atras_de_muitos_cobertos():
    con = _lx20s_casa()
    _lx20s_selos_cobertos_e_um_descoberto(con, cobertos=250)
    achados = AS.selos_pagos_sem_cobertura(con, "2026-10-01", limite=3)
    assert [s["numero"] for s in achados] == ["SELODESCOBERTO1"], (
        "os cobertos ocuparam o limite e o selo sem pagamento sumiu do relatório")


def test_o_limite_do_relatorio_conta_so_os_descobertos_e_guarda_a_ordem():
    con = _lx20s_casa()
    bd = _lx20s_banco(con)
    for numero, quando in (("SELOSEMPAGAR0002", "2026-10-05T10:00:00"),
                           ("SELOSEMPAGAR0001", "2026-10-04T10:00:00"),
                           ("SELOSEMPAGAR0003", "2026-10-06T10:00:00")):
        bd.escrever("""INSERT INTO sd_selos (numero, texto, tabela, ato_id, obtido_em,
                           obtido_por) VALUES (%s,'Selo pago','pt_atos',1,%s,%s)""",
                    (numero, quando, _LX20S_ESCREVENTE))
    con.commit()
    assert [s["numero"] for s in AS.selos_pagos_sem_cobertura(con, "2026-10-01", limite=2)] == [
        "SELOSEMPAGAR0001", "SELOSEMPAGAR0002"]


def test_a_conferencia_diz_quando_ficou_selo_sem_cobertura_de_fora(monkeypatch):
    import gratuidade_comprovante_web as GCW
    con = _lx20s_casa()
    _lx20s_selos_cobertos_e_um_descoberto(con, cobertos=2)
    _lx20s_banco(con).escrever(
        """INSERT INTO sd_selos (numero, texto, tabela, ato_id, obtido_em, obtido_por)
           VALUES ('SELODESCOBERTO2', 'Selo pago', 'pt_atos', 998, '2026-10-04T10:00:00', %s)""",
        (_LX20S_ESCREVENTE,))
    con.commit()
    monkeypatch.setattr(GCW, "LIMITE_DOS_PAGOS", 1)
    # A lista das gratuidades lê os anexos, que este banco não tem: não é o assunto.
    monkeypatch.setattr(GCW.GC, "sem_comprovante_por_escrevente", lambda con, hoje: [])
    app, telas = _lx20s_app(monkeypatch, con, papel="ADMIN")
    with app.test_client() as c:
        _lx20s_logado(c)
        assert c.get("/selo/conferencia").status_code == 200
    dados = telas[-1][1]
    assert [s["numero"] for s in dados["pagos_sem_cobertura"]] == ["SELODESCOBERTO1"]
    assert dados["pagos_cortados"] is True and dados["pagos_limite"] == 1
    html = (RAIZ / "templates" / "selo_conferencia.html").read_text(encoding="utf-8")
    assert "pagos_cortados" in html and "pagos_limite" in html


# -------------------------- achado 3: débito gravado sem o selo sair


def test_a_unidade_que_nao_se_gasta_no_atendimento_nao_deixa_o_deposito_debitado(
        _lx20s_aparelho, monkeypatch):
    con = _lx20s_casa()
    p = _lx20s_protocolo(con)
    item = _lx20s_item(con, p["protocolo_id"], quitado=0, quantidade=1)
    dep = _lx20s_deposito(con, p["protocolo_id"], valor="100,00")
    CXP.atender(con, usuario=_LX20S_ESCREVENTE, protocolo=p["numero"], agora=_LX20S_AGORA)
    con.commit()
    monkeypatch.setattr(CXP, "consumir_item", lambda *a, **k: 0)
    r = _lx20s_selar(con)
    assert r["selado"] is False and _lx20s_aparelho == []
    assert _lx20s_saldo(con, dep) == 10000, "o depósito pagou um selo que não saiu"
    assert int(_lx20s_item_lido(con, item)["quitado"] or 0) == 0


def test_a_cobertura_que_nao_cobre_volta_tudo_o_que_tentou_gravar(_lx20s_aparelho, monkeypatch):
    con = _lx20s_casa()

    def cobre_pela_metade(con, **_):
        _lx20s_banco(con).escrever(
            "INSERT INTO settings (key, value) VALUES ('lx20_rastro_da_cobertura', 'gravou')")
        return {"coberto": False, "quadro": {}}

    monkeypatch.setattr(AS, "cobrir_o_selo", cobre_pela_metade)
    r = _lx20s_selar(con)
    assert r["selado"] is False and r.get("aguardando_cobertura") is True
    # A chave vai como parâmetro: escrita literal ao lado de «key =» o
    # gitleaks a lia como chave de API (23/10/2026).
    assert _lx20s_banco(con).valor(
        "SELECT value FROM settings WHERE key = %s", ("lx20_rastro_da_cobertura",)) is None
    # O «aguardando cobertura» vai na transação dele, e fica.
    assert _lx20s_banco(con).valor(
        "SELECT count(*) AS n FROM cx_selo_aguardando WHERE tabela = 'pt_atos' AND ato_id = 1") == 1


# ------------------- achado 4: as ações do quadro abertas a qualquer item


def _lx20s_app(monkeypatch, con, *, papel="USER", usuario=_LX20S_ESCREVENTE):
    """As rotas do selo × caixa num Flask sem a casa; a tela só anota o que ia mostrar."""
    from flask import Flask
    import gratuidade_comprovante_web as GCW
    telas = []
    monkeypatch.setattr(GCW, "render_template",
                        lambda nome, **dados: telas.append((nome, dados)) or "ok")
    app = Flask(__name__, template_folder=str(RAIZ / "templates"))
    app.secret_key = "teste"
    app.extensions.update({
        "usuario_nome": lambda: usuario, "usuario_papel": lambda: papel,
        "usuario_id": lambda: 1,
        "current_user": lambda: {"full_name": usuario, "username": "fulana"}})
    sem = (lambda *a, **k: (lambda f: f))
    GCW.registrar_rotas_do_selo_e_caixa(app, _Lx20sDb(con), lambda f: f, sem,
                                        lambda *a, **k: None)
    return app, telas


def _lx20s_logado(c):
    with c.session_transaction() as s:
        s["user_id"] = 1


def _lx20s_dois_protocolos(con):
    """O que o escrevente atende (com depósito) e o de outro cliente (com depósito)."""
    meu = _lx20s_protocolo(con)
    meu_item = _lx20s_item(con, meu["protocolo_id"], quantidade=2)
    meu_dep = _lx20s_deposito(con, meu["protocolo_id"], numero="DP2026.10.1")
    outro = _lx20s_protocolo(con)
    outro_item = _lx20s_item(con, outro["protocolo_id"], quantidade=2)
    outro_dep = _lx20s_deposito(con, outro["protocolo_id"], numero="DP2026.10.2")
    CXP.atender(con, usuario=_LX20S_ESCREVENTE, protocolo=meu["numero"], agora=_LX20S_AGORA)
    con.commit()
    return {"meu": meu, "meu_item": meu_item, "meu_dep": meu_dep,
            "outro": outro, "outro_item": outro_item, "outro_dep": outro_dep}


@pytest.mark.parametrize("rota", ["vincular", "deposito", "diferir"])
def test_item_id_que_nao_e_numero_e_recusado_sem_erro_500(monkeypatch, rota):
    con = _lx20s_casa()
    app, _ = _lx20s_app(monkeypatch, con)
    with app.test_client() as c:
        _lx20s_logado(c)
        r = c.post(f"/selo/cobertura/{rota}?tabela=pt_atos&ato_id=1",
                   data={"item_id": "abc"})
    assert r.status_code == 400


def test_o_deposito_de_outro_protocolo_nao_paga_item_pela_tela_do_selo(monkeypatch):
    con = _lx20s_casa()
    d = _lx20s_dois_protocolos(con)
    app, _ = _lx20s_app(monkeypatch, con)
    with app.test_client() as c:
        _lx20s_logado(c)
        c.post("/selo/cobertura/deposito?tabela=pt_atos&ato_id=1",
               data={"item_id": str(d["outro_item"])})
    assert _lx20s_saldo(con, d["outro_dep"]) == 10000
    assert int(_lx20s_item_lido(con, d["outro_item"])["quitado"] or 0) == 0


def test_o_deposito_paga_o_item_do_protocolo_que_o_escrevente_atende(monkeypatch):
    con = _lx20s_casa()
    d = _lx20s_dois_protocolos(con)
    app, _ = _lx20s_app(monkeypatch, con)
    with app.test_client() as c:
        _lx20s_logado(c)
        r = c.post("/selo/cobertura/deposito?tabela=pt_atos&ato_id=1",
                   data={"item_id": str(d["meu_item"])})
    assert r.status_code == 302
    assert _lx20s_saldo(con, d["meu_dep"]) == 2000
    assert int(_lx20s_item_lido(con, d["meu_item"])["quitado"] or 0) == 1


def test_item_de_protocolo_encerrado_nao_se_paga_nem_se_liga(monkeypatch):
    con = _lx20s_casa()
    d = _lx20s_dois_protocolos(con)
    _lx20s_banco(con).escrever("UPDATE cx_protocolos SET situacao = 'CANCELADO' WHERE id = %s",
                               (d["meu"]["protocolo_id"],))
    con.commit()
    app, _ = _lx20s_app(monkeypatch, con)
    with app.test_client() as c:
        _lx20s_logado(c)
        c.post("/selo/cobertura/deposito?tabela=pt_atos&ato_id=1",
               data={"item_id": str(d["meu_item"])})
        c.post("/selo/cobertura/vincular?tabela=pt_atos&ato_id=1",
               data={"item_id": str(d["meu_item"])})
    item = _lx20s_item_lido(con, d["meu_item"])
    assert _lx20s_saldo(con, d["meu_dep"]) == 10000
    assert int(item["quitado"] or 0) == 0 and int(item["quantidade_usada"] or 0) == 0


def test_ligar_o_ato_so_gasta_unidade_do_protocolo_em_atendimento(monkeypatch):
    con = _lx20s_casa()
    d = _lx20s_dois_protocolos(con)
    app, _ = _lx20s_app(monkeypatch, con)
    with app.test_client() as c:
        _lx20s_logado(c)
        c.post("/selo/cobertura/vincular?tabela=pt_atos&ato_id=1",
               data={"item_id": str(d["outro_item"])})
        c.post("/selo/cobertura/vincular?tabela=pt_atos&ato_id=2",
               data={"item_id": str(d["meu_item"])})
    assert int(_lx20s_item_lido(con, d["outro_item"])["quantidade_usada"] or 0) == 0
    assert int(_lx20s_item_lido(con, d["meu_item"])["quantidade_usada"] or 0) == 1


def test_diferir_item_de_outro_protocolo_e_recusado(monkeypatch):
    con = _lx20s_casa()
    d = _lx20s_dois_protocolos(con)
    app, _ = _lx20s_app(monkeypatch, con)
    with app.test_client() as c:
        _lx20s_logado(c)
        c.post("/selo/cobertura/diferir?tabela=pt_atos&ato_id=1",
               data={"item_id": str(d["outro_item"]), "quem_paga": "DEVEDOR DE EXEMPLO",
                     "quando": "2026-11-30", "motivo": "Protesto a posteriori, paga no fim"})
        c.post("/selo/cobertura/diferir?tabela=pt_atos&ato_id=1",
               data={"item_id": str(d["meu_item"]), "quem_paga": "DEVEDOR DE EXEMPLO",
                     "quando": "2026-11-30", "motivo": "Protesto a posteriori, paga no fim"})
    assert not _lx20s_item_lido(con, d["outro_item"])["diferido_quem"]
    assert _lx20s_item_lido(con, d["meu_item"])["diferido_quem"] == "DEVEDOR DE EXEMPLO"


def test_o_deposito_nao_se_amarra_a_ato_que_nao_existe(monkeypatch):
    con = _lx20s_casa()
    d = _lx20s_dois_protocolos(con)
    app, _ = _lx20s_app(monkeypatch, con)
    with app.test_client() as c:
        _lx20s_logado(c)
        c.post("/selo/cobertura/deposito?tabela=pt_atos&ato_id=9999",
               data={"item_id": str(d["meu_item"])})
    assert _lx20s_saldo(con, d["meu_dep"]) == 10000
    assert int(_lx20s_item_lido(con, d["meu_item"])["quitado"] or 0) == 0


def test_o_item_ja_ligado_ao_ato_vale_mesmo_fora_do_atendimento(monkeypatch):
    """O quadro mostra primeiro o item ligado ao ato — pode ser de outro protocolo."""
    con = _lx20s_casa()
    d = _lx20s_dois_protocolos(con)
    assert CXP.consumir_item(con, d["outro_item"], ato_id=1, tabela="pt_atos",
                             agora=_LX20S_AGORA) == 1
    con.commit()
    app, _ = _lx20s_app(monkeypatch, con)
    with app.test_client() as c:
        _lx20s_logado(c)
        c.post("/selo/cobertura/deposito?tabela=pt_atos&ato_id=1",
               data={"item_id": str(d["outro_item"])})
    assert _lx20s_saldo(con, d["outro_dep"]) == 2000
