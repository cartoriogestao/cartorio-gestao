"""
Testes do pacote de backup.

O QUE ELES DEFENDEM
    A regra que o diário do projeto registra desde a primeira tentativa, e que
    até hoje NÃO ESTAVA NO CÓDIGO: backup interrompido não pode deixar arquivo
    com o nome definitivo. Backup que mente é pior que backup que falta.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import zipfile
from pathlib import Path

import pytest


pytestmark = pytest.mark.lento  # gate rapido: pytest -m "not lento" — referencia acervo_eoficio ou sqlite de producao
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import backup as BKP          # noqa: E402


class BancoFalso:
    """O mínimo que `gerar_pacote` precisa: uma cópia consistente do SQLite."""

    def __init__(self, caminho: Path, quebrar: bool = False):
        self.caminho = caminho
        self.quebrar = quebrar
        con = sqlite3.connect(caminho)
        con.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
        con.execute("INSERT INTO t(v) VALUES ('a matrícula 2576')")
        con.commit()
        con.close()

    def backup_database(self, destino: Path) -> Path:
        if self.quebrar:
            raise OSError("disco cheio, por exemplo")
        origem = sqlite3.connect(self.caminho)
        alvo = sqlite3.connect(destino)
        try:
            origem.backup(alvo)
        finally:
            alvo.close()
            origem.close()
        return destino


@pytest.fixture()
def cenario(tmp_path):
    db = BancoFalso(tmp_path / "cartorio.sqlite3")
    arquivos = tmp_path / "arquivos"
    (arquivos / "ri" / "fichas").mkdir(parents=True)
    (arquivos / "ri" / "fichas" / "00002576.0001").write_bytes(b"II*\x00ficha")
    (arquivos / "ri" / "fichas" / "00002576.0002").write_bytes(b"II*\x00outra")
    return db, arquivos, tmp_path / "backups"


# ------------------------------------------------------------ o essencial

def test_gera_e_confere(cenario):
    db, arquivos, destino = cenario
    pacote = BKP.gerar_pacote(db, destino / "b.zip", arquivos)
    assert pacote.is_file()
    assert BKP.conferir(pacote) is None


def test_o_banco_e_as_digitalizacoes_entram(cenario):
    db, arquivos, destino = cenario
    pacote = BKP.gerar_pacote(db, destino / "b.zip", arquivos)
    with zipfile.ZipFile(pacote) as zf:
        nomes = zf.namelist()
    assert BKP.NOME_BANCO in nomes
    assert BKP.NOME_MANIFESTO in nomes
    assert any("00002576.0001" in n for n in nomes)


def test_backup_so_do_banco_nao_leva_as_digitalizacoes(cenario):
    db, arquivos, destino = cenario
    pacote = BKP.gerar_pacote(db, destino / "b.zip", arquivos, com_arquivos=False)
    with zipfile.ZipFile(pacote) as zf:
        nomes = zf.namelist()
    assert BKP.NOME_BANCO in nomes
    assert not any(n.startswith("arquivos/") for n in nomes)
    assert BKP.resumo(pacote)["tipo"] == "banco"


# ------------------------------------- a regra que o diário já registrava

def test_backup_interrompido_nao_ganha_o_nome_definitivo(cenario):
    # É O TESTE QUE FALTAVA. A primeira tentativa do projeto gravou direto no
    # nome final, foi interrompida, e deixou 158 MB de arquivo corrompido com
    # cara de backup bom.
    db, arquivos, destino = cenario
    db.quebrar = True
    alvo = destino / "b.zip"
    with pytest.raises(OSError):
        BKP.gerar_pacote(db, alvo, arquivos)
    assert not alvo.exists(), "o nome definitivo não pode existir"


def test_pacote_que_nao_passa_na_conferencia_fica_como_parcial(cenario, monkeypatch):
    db, arquivos, destino = cenario
    alvo = destino / "b.zip"
    monkeypatch.setattr(BKP, "conferir", lambda p: "corrompido de propósito")
    with pytest.raises(BKP.BackupInvalido):
        BKP.gerar_pacote(db, alvo, arquivos)
    assert not alvo.exists()
    assert (destino / "b.zip.parcial").is_file(), "o parcial fica para exame"


def test_o_parcial_de_uma_tentativa_anterior_nao_atrapalha(cenario):
    db, arquivos, destino = cenario
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "b.zip.parcial").write_bytes(b"lixo de uma tentativa antiga")
    pacote = BKP.gerar_pacote(db, destino / "b.zip", arquivos)
    assert BKP.conferir(pacote) is None
    assert not (destino / "b.zip.parcial").exists()


def test_os_parciais_esquecidos_sao_listados(cenario):
    _, _, destino = cenario
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "a.zip.parcial").write_bytes(b"x")
    (destino / "b.zip.parcial").write_bytes(b"y")
    (destino / "c.zip").write_bytes(b"z")
    assert len(BKP.parciais(destino)) == 2


# --------------------------------------------------------- a conferência

def test_conferir_acusa_zip_truncado(tmp_path):
    ruim = tmp_path / "ruim.zip"
    ruim.write_bytes(b"PK\x03\x04 e nada mais")
    assert BKP.conferir(ruim) is not None


def test_conferir_acusa_arquivo_vazio(tmp_path):
    vazio = tmp_path / "vazio.zip"
    vazio.write_bytes(b"")
    assert "vazio" in BKP.conferir(vazio)


def test_conferir_acusa_ausencia(tmp_path):
    assert "não existe" in BKP.conferir(tmp_path / "nao_existe.zip")


def test_conferir_acusa_banco_faltando(tmp_path):
    sem_banco = tmp_path / "sem.zip"
    with zipfile.ZipFile(sem_banco, "w") as zf:
        zf.writestr(BKP.NOME_MANIFESTO, "{}")
    assert "banco não está" in BKP.conferir(sem_banco)


def test_conferir_pega_corrupcao_silenciosa(cenario):
    # O caso que só o SHA-256 pega: o zip abre, o banco está lá, e mesmo assim
    # o conteúdo não é o que foi gravado.
    db, arquivos, destino = cenario
    pacote = BKP.gerar_pacote(db, destino / "b.zip", arquivos)
    with zipfile.ZipFile(pacote) as zf:
        manifesto = zf.read(BKP.NOME_MANIFESTO)
        outros = {n: zf.read(n) for n in zf.namelist() if n != BKP.NOME_BANCO}
    adulterado = destino / "adulterado.zip"
    with zipfile.ZipFile(adulterado, "w") as zf:
        for n, dados in outros.items():
            zf.writestr(n, dados)
        zf.writestr(BKP.NOME_BANCO, b"um banco que nao e o que o manifesto diz")
    assert manifesto
    assert "SHA-256" in BKP.conferir(adulterado)


def test_o_acervo_do_eoficio_entra_no_backup_completo(cenario, tmp_path):
    # ELE QUASE FICOU DE FORA. Mora na pasta de dados, ao lado do banco, e não
    # dentro de `arquivos`, que era a única pasta varrida — 364 MB com a cópia
    # integral do sistema antigo não entrariam no backup.
    db, arquivos, destino = cenario
    acervo = tmp_path / "acervo_eoficio.sqlite3"
    acervo.write_bytes(b"SQLite format 3\x00" + b"acervo do E-Oficio" * 100)
    pacote = BKP.gerar_pacote(db, destino / "b.zip", arquivos, acervo=acervo)
    with zipfile.ZipFile(pacote) as zf:
        nomes = zf.namelist()
        manifesto = json.loads(zf.read(BKP.NOME_MANIFESTO).decode("utf-8"))
    assert "acervo/acervo_eoficio.sqlite3" in nomes
    assert manifesto["acervo_eoficio"] is True
    assert manifesto["acervo_sha256"]


def test_o_acervo_nao_entra_no_backup_diario(cenario, tmp_path):
    # É cópia de um banco que não muda mais: repetir 364 MB todo dia gastaria
    # disco sem aumentar proteção nenhuma.
    db, arquivos, destino = cenario
    acervo = tmp_path / "acervo_eoficio.sqlite3"
    acervo.write_bytes(b"SQLite format 3\x00")
    pacote = BKP.gerar_pacote(db, destino / "b.zip", arquivos,
                              com_arquivos=False, acervo=acervo)
    with zipfile.ZipFile(pacote) as zf:
        assert not any(n.startswith("acervo/") for n in zf.namelist())
        assert json.loads(zf.read(BKP.NOME_MANIFESTO).decode("utf-8"))["acervo_eoficio"] is False


def test_sem_acervo_o_backup_segue_normal(cenario, tmp_path):
    db, arquivos, destino = cenario
    pacote = BKP.gerar_pacote(db, destino / "b.zip", arquivos,
                              acervo=tmp_path / "nao_existe.sqlite3")
    assert BKP.conferir(pacote) is None


def test_o_resumo_conta_o_que_tem_dentro(cenario):
    db, arquivos, destino = cenario
    r = BKP.resumo(BKP.gerar_pacote(db, destino / "b.zip", arquivos))
    assert r["problema"] is None
    assert r["tipo"] == "completo"
    assert r["arquivos"] == 2
    assert r["bytes"] > 0


# =====================================================================
# LX14 (19/10/2026) — segredos, backup e logs: o que a auditoria LS03 só
# relatou (A7, A8, A9, M1, M8, M9, M11, B1, B6) e o M5 do LS01.
#
# AS PROVAS MORAM AQUI, E NÃO EM `test_seguranca_ls03.py`: a integração roda
# só os testes da lista do lote, e este é o arquivo dela. O tema é um só —
# o que sai do servidor dentro do backup e dos logs, e quem lê o que fica.
# =====================================================================

import logging          # noqa: E402
import re               # noqa: E402

import cofre_cred as COFRE          # noqa: E402
import permissao_local as PERM      # noqa: E402

SENHA_DA_CIFRA = "cifra-de-teste-1234"
SENHA_DO_LOGIN = "Senha#12345"


def _sem_cifra_antigo(cenario_, destino_nome="antigo.zip"):
    """Um pacote como os de antes do LX14: zip, manifesto sem a chave
    `cifrado`. É o que a casa tem guardado hoje, e tem de continuar abrindo."""
    db, arquivos, destino = cenario_
    pacote = BKP.gerar_pacote(db, destino / "base.zip", arquivos)
    with zipfile.ZipFile(pacote) as zf:
        conteudo = {n: zf.read(n) for n in zf.namelist()}
    manifesto = json.loads(conteudo[BKP.NOME_MANIFESTO].decode("utf-8"))
    manifesto.pop("cifrado", None)
    conteudo[BKP.NOME_MANIFESTO] = json.dumps(manifesto).encode("utf-8")
    antigo = destino / destino_nome
    with zipfile.ZipFile(antigo, "w", zipfile.ZIP_DEFLATED) as zf:
        for n, dados in conteudo.items():
            zf.writestr(n, dados)
    return antigo


# ------------------------------------------- A7: a cifra do pacote

def test_sem_senha_o_pacote_continua_sendo_o_zip_de_sempre(cenario):
    db, arquivos, destino = cenario
    pacote = BKP.gerar_pacote(db, destino / "b.zip", arquivos)
    assert not BKP.e_cifrado(pacote)
    with zipfile.ZipFile(pacote) as zf:
        assert json.loads(zf.read(BKP.NOME_MANIFESTO))["cifrado"] is False


def test_com_senha_o_pacote_sai_cifrado_com_o_mesmo_nome_e_abre_de_volta(cenario, tmp_path):
    db, arquivos, destino = cenario
    pacote = BKP.gerar_pacote(db, destino / "backup_banco_2026-10-19.zip", arquivos,
                              senha_da_cifra=SENHA_DA_CIFRA)
    assert pacote.name == "backup_banco_2026-10-19.zip"
    assert BKP.e_cifrado(pacote)
    assert not zipfile.is_zipfile(pacote), "cifrado não pode abrir como zip"
    assert b"matr\xc3\xadcula 2576" not in pacote.read_bytes()
    assert BKP.parciais(destino) == [], "não sobra parcial do caminho"
    assert BKP.conferir(pacote, SENHA_DA_CIFRA) is None
    claro = BKP.abrir(pacote, tmp_path / "restaurar" / "pacote.zip", SENHA_DA_CIFRA)
    with zipfile.ZipFile(claro) as zf:
        assert BKP.NOME_BANCO in zf.namelist()
        assert json.loads(zf.read(BKP.NOME_MANIFESTO))["cifrado"] is True
    assert BKP.resumo(pacote, SENHA_DA_CIFRA)["arquivos"] == 2


def test_a_restauracao_abre_o_pacote_antigo_sem_cifra(cenario, tmp_path):
    # É O CAMINHO DE VOLTA DA VIRADA: nada pode impedir de abrir um backup
    # feito antes desta versão.
    antigo = _sem_cifra_antigo(cenario)
    claro = BKP.abrir(antigo, tmp_path / "restaurar" / "pacote.zip")
    assert claro.read_bytes() == antigo.read_bytes()
    assert BKP.conferir(claro) is None
    assert BKP.main(["conferir", str(antigo)]) == 0


def test_conferir_o_cifrado_sem_a_senha_diz_que_falta_a_senha_e_nao_que_presta(cenario):
    db, arquivos, destino = cenario
    pacote = BKP.gerar_pacote(db, destino / "b.zip", arquivos,
                              senha_da_cifra=SENHA_DA_CIFRA)
    assert "senha" in BKP.conferir(pacote)


def test_senha_errada_nao_abre_e_nao_deixa_zip_com_cara_de_bom(cenario, tmp_path):
    db, arquivos, destino = cenario
    pacote = BKP.gerar_pacote(db, destino / "b.zip", arquivos,
                              senha_da_cifra=SENHA_DA_CIFRA)
    saida = tmp_path / "restaurar" / "pacote.zip"
    with pytest.raises(BKP.BackupInvalido, match="senha não abre"):
        BKP.abrir(pacote, saida, "outra-senha-qualquer")
    assert not saida.exists()


def test_pacote_cifrado_truncado_e_recusado_ate_no_limite_de_um_bloco(tmp_path):
    # Tirar o último bloco inteiro deixa o arquivo terminando num bloco BOM:
    # só a marca de «último», que entra na autenticação, mostra que faltou.
    origem = tmp_path / "origem.bin"
    origem.write_bytes(b"x" * (2 * BKP.BLOCO_DA_CIFRA + 10))
    cifrado = BKP.cifrar_arquivo(origem, tmp_path / "c.bin", SENHA_DA_CIFRA)
    bruto = cifrado.read_bytes()
    no_limite = tmp_path / "limite.bin"
    no_limite.write_bytes(bruto[:-(4 + 10 + 16)])
    with pytest.raises(BKP.BackupInvalido, match="antes do último bloco"):
        BKP.decifrar_arquivo(no_limite, tmp_path / "s1", SENHA_DA_CIFRA)
    no_meio = tmp_path / "meio.bin"
    no_meio.write_bytes(bruto[:-5])
    with pytest.raises(BKP.BackupInvalido, match="truncado"):
        BKP.decifrar_arquivo(no_meio, tmp_path / "s2", SENHA_DA_CIFRA)
    assert BKP.decifrar_arquivo(cifrado, tmp_path / "s3",
                                SENHA_DA_CIFRA).read_bytes() == origem.read_bytes()


def test_cifrado_que_nao_devolve_o_zip_conferido_fica_como_parcial(cenario, monkeypatch):
    db, arquivos, destino = cenario
    monkeypatch.setattr(BKP, "_sha256_decifrado", lambda p, s: "outra coisa")
    alvo = destino / "b.zip"
    with pytest.raises(BKP.BackupInvalido, match="não devolve o zip conferido"):
        BKP.gerar_pacote(db, alvo, arquivos, senha_da_cifra=SENHA_DA_CIFRA)
    assert not alvo.exists()
    assert (destino / "b.zip.cifrado.parcial").is_file()


def test_a_senha_da_cifra_mora_cifrada_no_cofre_e_tem_minimo(tmp_path):
    with pytest.raises(BKP.BackupInvalido, match="12"):
        BKP.guardar_senha_da_cifra(tmp_path, "curta")
    assert BKP.situacao_da_cifra(tmp_path) == "desligada"
    BKP.guardar_senha_da_cifra(tmp_path, SENHA_DA_CIFRA)
    assert BKP.situacao_da_cifra(tmp_path) == "ligada"
    assert SENHA_DA_CIFRA.encode() not in (tmp_path / COFRE.BACKUP).read_bytes()
    assert BKP.senha_da_cifra(tmp_path) == SENHA_DA_CIFRA
    # sem a chave do cofre, a senha não abre — e a tela tem de dizer
    (tmp_path / COFRE.NOME_DA_CHAVE).unlink()
    assert BKP.situacao_da_cifra(tmp_path) == "perdida"
    assert BKP.senha_da_cifra(tmp_path) == ""


def test_a_linha_de_comando_abre_o_cifrado_com_a_senha_do_cofre(cenario, tmp_path):
    db, arquivos, destino = cenario
    dados = tmp_path / "dados"
    BKP.guardar_senha_da_cifra(dados, SENHA_DA_CIFRA)
    pacote = BKP.gerar_pacote(db, destino / "b.zip", arquivos,
                              senha_da_cifra=SENHA_DA_CIFRA)
    saida = tmp_path / "saida.zip"
    assert BKP.main(["abrir", str(pacote), str(saida),
                     "--pasta-de-dados", str(dados)]) == 0
    assert BKP.conferir(saida) is None


# ------------------------------------- A7 e B6: quem lê a pasta das cópias

class _Rodar:
    """O `subprocess.run` de mentira: anota o comando e responde o combinado."""

    def __init__(self, whoami_ok=True, icacls_codigo=0):
        self.chamadas = []
        self.whoami_ok, self.icacls_codigo = whoami_ok, icacls_codigo

    def __call__(self, comando, **_):
        import types
        self.chamadas.append(list(comando))
        if comando[0] == "whoami":
            return types.SimpleNamespace(
                returncode=0 if self.whoami_ok else 1,
                stdout='"servidor\\\\exemplo","S-1-5-21-1-2-3-1001"\n', stderr="")
        return types.SimpleNamespace(returncode=self.icacls_codigo,
                                     stdout="", stderr="Acesso negado.")


def test_no_windows_a_pasta_das_copias_fica_so_com_o_servico_os_admins_e_o_processo(tmp_path):
    rodar = _Rodar()
    assert PERM.restringir(tmp_path, pasta=True, rodar=rodar, windows=True,
                           de_novo=True) is None
    icacls = [c for c in rodar.chamadas if c[0] == "icacls"]
    assert icacls == [[
        "icacls", str(tmp_path), "/inheritance:r", "/grant:r",
        "*S-1-5-18:(OI)(CI)F", "*S-1-5-32-544:(OI)(CI)F",
        "*S-1-5-21-1-2-3-1001:(OI)(CI)F"]]


def test_icacls_que_falha_vira_aviso_e_o_backup_sai_assim_mesmo(tmp_path, monkeypatch, caplog):
    import pasta_das_copias as PC
    rodar = _Rodar(icacls_codigo=5)
    monkeypatch.setattr(PERM, "_e_windows", lambda: True)
    monkeypatch.setattr(PERM.subprocess, "run", rodar)
    monkeypatch.setattr(PERM, "_FEITOS", set())
    caplog.set_level(logging.WARNING, logger="cartorio.permissoes")
    pasta = PC.pasta_de_backups(tmp_path, str(tmp_path / "copias_fora"))
    assert pasta.is_dir()
    assert any("PERMISSAO NAO AJUSTADA" in r.getMessage() for r in caplog.records)


def test_sem_descobrir_a_conta_do_processo_a_heranca_nao_e_tirada(tmp_path):
    rodar = _Rodar(whoami_ok=False)
    problema = PERM.restringir(tmp_path, pasta=True, rodar=rodar, windows=True,
                               de_novo=True)
    assert "whoami" in problema
    assert not [c for c in rodar.chamadas if c[0] == "icacls"]


@pytest.mark.skipif(sys.platform.startswith("win"), reason="permissão POSIX")
def test_fora_do_windows_os_segredos_da_pasta_de_dados_ficam_so_do_dono(tmp_path):
    import os
    import stat
    (tmp_path / "logs").mkdir()
    nomes = ("secret.key", "cofre.key", "cnib.cred", "pgpass.conf",
             "logs/servidor.log")
    for nome in nomes:
        (tmp_path / nome).write_text("x")
        os.chmod(tmp_path / nome, 0o644)
    (tmp_path / "cartorio_gestao.sqlite3").write_text("")
    os.chmod(tmp_path / "cartorio_gestao.sqlite3", 0o644)
    assert PERM.proteger_segredos(tmp_path) == []
    for nome in nomes:
        assert stat.S_IMODE((tmp_path / nome).stat().st_mode) == 0o600, nome
    assert stat.S_IMODE((tmp_path / "cartorio_gestao.sqlite3").stat().st_mode) == 0o644


# ------------------------- A8: os segredos dos robôs e do WhatsApp no cofre

def _segredos_no_banco(db, robo: str = "", wa: str = "") -> None:
    """Grava DIRETO na coluna, como fazia a versão de antes — ou como volta
    com um backup antigo restaurado. **ESCREVE.**"""
    from bd_nativo import banco
    with db.transaction() as con:
        bd = banco(con)
        if robo:
            bd.escrever("UPDATE robo_config SET valor = %s WHERE chave = 'api_key_grok'",
                        (robo,))
        if wa:
            bd.escrever("UPDATE wa_config SET valor = %s WHERE chave = 'access_token'",
                        (wa,))


def _coluna(db, tabela: str, chave: str) -> str:
    from bd_nativo import banco
    with db.connect() as con:
        return banco(con).valor(f"SELECT valor FROM {tabela} WHERE chave = %s",
                                (chave,)) or ""


def _subir_de_novo(db) -> None:
    import robo_schema
    import wa_schema
    with db.transaction() as con:
        robo_schema.init_robo_schema(con)
        wa_schema.init_wa_schema(con)


def test_a_subida_tira_as_chaves_da_coluna_e_as_guarda_cifradas_no_cofre(cg_casa):
    import robo_schema as RS
    import wa_balcao as WB
    db, dados = cg_casa["db"], cg_casa["dados"]
    _segredos_no_banco(db, robo="sk-robo-de-teste-0001", wa="EAAB-token-de-teste-0002")
    _subir_de_novo(db)
    assert _coluna(db, "robo_config", "api_key_grok") == ""
    assert _coluna(db, "wa_config", "access_token") == ""
    with db.connect() as con:
        assert RS.api_key_do_provedor(con, "grok") == "sk-robo-de-teste-0001"
        assert WB.ler_config(con, "access_token") == "EAAB-token-de-teste-0002"
    assert b"sk-robo-de-teste" not in (dados / COFRE.ROBOS).read_bytes()
    assert b"EAAB-token" not in (dados / COFRE.WHATSAPP).read_bytes()
    # IDEMPOTENTE: subir de novo não muda nada
    antes = (dados / COFRE.ROBOS).read_bytes()
    _subir_de_novo(db)
    assert (dados / COFRE.ROBOS).read_bytes() == antes


def test_backup_antigo_restaurado_nao_troca_a_chave_nova_pela_velha(cg_casa):
    import robo_schema as RS
    db = cg_casa["db"]
    with db.transaction() as con:
        RS.gravar_config(con, RS.CHAVE_GROK, "sk-nova-de-teste")
    assert _coluna(db, "robo_config", "api_key_grok") == ""
    _segredos_no_banco(db, robo="sk-velha-do-backup")
    _subir_de_novo(db)
    assert _coluna(db, "robo_config", "api_key_grok") == ""
    with db.connect() as con:
        assert RS.api_key_do_provedor(con, "grok") == "sk-nova-de-teste"


def test_cofre_que_nao_grava_deixa_o_segredo_onde_estava(cg_casa, monkeypatch):
    db = cg_casa["db"]
    _segredos_no_banco(db, wa="EAAB-fica-no-banco")

    def disco_cheio(*a, **k):
        raise OSError("disco cheio, por exemplo")
    monkeypatch.setattr(COFRE, "gravar", disco_cheio)
    _subir_de_novo(db)
    assert _coluna(db, "wa_config", "access_token") == "EAAB-fica-no-banco"


def _entrar(cg_casa, papel: str = "ADMIN", login: str = "tabeliao"):
    db, c = cg_casa["db"], cg_casa["app"].test_client()
    db.create_user(login, "MARIO EXEMPLO DOS SANTOS", SENHA_DO_LOGIN, papel)
    html = c.get("/login").get_data(as_text=True)
    csrf = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)
    c.post("/login", data={"username": login, "password": SENHA_DO_LOGIN,
                           "csrf_token": csrf}, follow_redirects=True)
    return c


def _csrf(c, caminho: str) -> str:
    html = c.get(caminho).get_data(as_text=True)
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


def test_as_telas_dizem_so_configurado_sem_pedaco_do_segredo(cg_casa):
    import robo_schema as RS
    import wa_balcao as WB
    db = cg_casa["db"]
    with db.transaction() as con:
        RS.gravar_config(con, RS.CHAVE_GROK, "sk-tela-de-teste-WXYZ")
        WB.gravar_config(con, "access_token", "EAAB-tela-de-teste-QRST")
        WB.gravar_config(con, "verify_token", "verifica-de-teste-LMNO")
    c = _entrar(cg_casa)
    robos = c.get("/robos/config").get_data(as_text=True)
    zap = c.get("/whatsapp/config").get_data(as_text=True)
    assert "Configurada: sim" in robos and "WXYZ" not in robos
    assert "Configurado: sim" in zap
    for pedaco in ("QRST", "LMNO", "verifica-de-teste"):
        assert pedaco not in zap, pedaco


def test_a_tela_do_whatsapp_grava_no_cofre_e_o_campo_vazio_nao_apaga(cg_casa):
    import wa_balcao as WB
    db = cg_casa["db"]
    c = _entrar(cg_casa)
    campos = {"verify_token": "verifica-oficial", "phone_number_id": "123",
              "access_token": "EAAB-pela-tela", "app_secret": "",
              "caixa_url": "", "caixa_segredo": "caixa-pela-tela"}
    c.post("/whatsapp/config", data={"csrf_token": _csrf(c, "/whatsapp/config"),
                                     **campos})
    for chave in ("verify_token", "access_token", "caixa_segredo"):
        assert _coluna(db, "wa_config", chave) == "", chave
    assert _coluna(db, "wa_config", "phone_number_id") == "123"
    # «guardar» de novo com o campo vazio não apaga o verify_token...
    c.post("/whatsapp/config", data={"csrf_token": _csrf(c, "/whatsapp/config"),
                                     **{**campos, "verify_token": "",
                                        "access_token": "", "caixa_segredo": ""}})
    with db.connect() as con:
        assert WB.verify_token_salvo(con) == "verifica-oficial"
        assert WB.ler_config(con, "access_token") == "EAAB-pela-tela"
    # ...e a caixa «apagar» volta ao de teste
    c.post("/whatsapp/config", data={"csrf_token": _csrf(c, "/whatsapp/config"),
                                     **{**campos, "verify_token": "",
                                        "apagar_verify_token": "1"}})
    with db.connect() as con:
        assert WB.verify_token_salvo(con) == "cartorio-teste"


# --------------------------- A7: a tela liga a cifra e escolhe o acervo

def test_a_tela_liga_a_cifra_e_o_backup_baixado_sai_cifrado(cg_casa, monkeypatch):
    from bd_nativo import banco
    db, dados = cg_casa["db"], cg_casa["dados"]
    falso = BancoFalso(dados / "falso_do_backup.sqlite3")
    monkeypatch.setattr(db, "backup_database", falso.backup_database)
    c = _entrar(cg_casa)
    r = c.post("/configuracoes/backup-protecao", data={
        "csrf_token": _csrf(c, "/configuracoes"), "acao": "senha",
        "senha": SENHA_DA_CIFRA, "confirmacao": SENHA_DA_CIFRA},
        follow_redirects=True)
    html = r.get_data(as_text=True)
    assert "Cifra: ligada" in html and SENHA_DA_CIFRA not in html
    baixado = c.post("/backup", data={"csrf_token": _csrf(c, "/configuracoes")})
    assert baixado.status_code == 200
    assert baixado.data.startswith(BKP.MAGIA_DA_CIFRA)
    with db.connect() as con:
        detalhes = [str(l["details"]) for l in banco(con).ler(
            "SELECT details FROM audit_logs WHERE action = 'BACKUP_CIFRA' ORDER BY id")]
    assert detalhes and all(SENHA_DA_CIFRA not in d for d in detalhes)
    assert SENHA_DA_CIFRA not in str(db.get_settings())


def test_confirmacao_diferente_nao_liga_a_cifra(cg_casa):
    c = _entrar(cg_casa)
    c.post("/configuracoes/backup-protecao", data={
        "csrf_token": _csrf(c, "/configuracoes"), "acao": "senha",
        "senha": SENHA_DA_CIFRA, "confirmacao": SENHA_DA_CIFRA + "x"})
    assert BKP.situacao_da_cifra(cg_casa["dados"]) == "desligada"


def test_o_acervo_so_sai_do_completo_quando_a_casa_escolhe(cg_casa, monkeypatch):
    db, dados = cg_casa["db"], cg_casa["dados"]
    falso = BancoFalso(dados / "falso_do_backup.sqlite3")
    monkeypatch.setattr(db, "backup_database", falso.backup_database)
    (dados / "acervo_eoficio.sqlite3").write_bytes(b"SQLite format 3\x00acervo")
    c = _entrar(cg_casa)

    def nomes_do_completo():
        baixado = c.post("/backup", data={"csrf_token": _csrf(c, "/configuracoes")})
        destino = dados / "baixado.zip"
        destino.write_bytes(baixado.data)
        with zipfile.ZipFile(destino) as zf:
            return zf.namelist()

    assert "acervo/acervo_eoficio.sqlite3" in nomes_do_completo()   # de fábrica
    c.post("/configuracoes/backup-protecao", data={
        "csrf_token": _csrf(c, "/configuracoes"), "acao": "acervo",
        "backup_completo_sem_acervo": "on"})
    assert not any(n.startswith("acervo/") for n in nomes_do_completo())


def test_a_protecao_do_backup_e_so_do_admin(cg_casa):
    c = _entrar(cg_casa, papel="MANAGER", login="gerente")
    r = c.post("/configuracoes/backup-protecao", data={
        "csrf_token": _csrf(c, "/"), "acao": "senha",
        "senha": SENHA_DA_CIFRA, "confirmacao": SENHA_DA_CIFRA})
    assert r.status_code == 403
    assert BKP.situacao_da_cifra(cg_casa["dados"]) == "desligada"


# ---------------- M8: o endereço para onde vai a senha do selador

def test_o_manager_nao_troca_o_endereco_para_onde_a_senha_do_selador_vai(cg_casa):
    from bd_nativo import banco
    db = cg_casa["db"]
    admin = _entrar(cg_casa)
    local = "https://192.0.2.10:443"
    admin.post("/selador", data={"csrf_token": _csrf(admin, "/selador"),
                                 "acao": "gravar", "base_url": local,
                                 "ambiente": "PRODUCAO", "usuario": "selo.teste"})
    gerente = _entrar(cg_casa, papel="MANAGER", login="gerente")
    html = gerente.post("/selador", data={
        "csrf_token": _csrf(gerente, "/selador"), "acao": "gravar",
        "base_url": "https://servidor-de-fora.example", "ambiente": "PRODUCAO",
        "usuario": "selo.teste"}, follow_redirects=True).get_data(as_text=True)
    assert "só do ADMIN" in html
    with db.connect() as con:
        assert banco(con).valor("SELECT base_url FROM sd_config WHERE id = 1") == local
    # o resto da tela segue do MANAGER: mesmo endereço, outro usuário
    gerente.post("/selador", data={"csrf_token": _csrf(gerente, "/selador"),
                                   "acao": "gravar", "base_url": local,
                                   "ambiente": "PRODUCAO", "usuario": "outro.usuario"})
    with db.connect() as con:
        assert banco(con).valor("SELECT usuario FROM sd_config WHERE id = 1") == "outro.usuario"


# ------------------- M9: a auditoria que cai no log, e a da lista de fraude

def test_a_auditoria_que_cai_no_servidor_log_vai_mascarada(cg_casa, monkeypatch, caplog):
    db = cg_casa["db"]

    def travado():
        raise sqlite3.OperationalError("database is locked")
    monkeypatch.setattr(db, "connect", travado)
    caplog.set_level(logging.ERROR, logger="cartorio.auditoria")
    db.log(None, "SISTEMA", "TESTE_LX14", "TESTE", None,
           {"documento": "000.000.050-70", "senha": "segredo-do-teste-lx14",
            "teor": "T" * 3000})
    texto = " ".join(r.getMessage() for r in caplog.records)
    assert "AUDITORIA NAO GRAVADA" in texto
    assert "000.000.050-70" not in texto and "00000005070" not in texto
    assert "segredo-do-teste-lx14" not in texto
    assert "T" * 600 not in texto


def test_o_documento_da_lista_de_fraude_vai_mascarado_na_auditoria(cg_casa):
    from bd_nativo import banco
    c = _entrar(cg_casa)
    c.post("/fraudes/incluir", data={
        "csrf_token": _csrf(c, "/fraudes"), "papel": "VITIMA",
        "origem": "Ofício de teste", "nome": "FULANO DE TESTE",
        "documento": "000.000.050-70"})
    with cg_casa["db"].connect() as con:
        assert banco(con).valor("SELECT count(*) AS n FROM fr_alertas") == 1
        detalhes = banco(con).valor(
            "SELECT details FROM audit_logs WHERE action = 'FRAUDE_INCLUIR' "
            "ORDER BY id DESC LIMIT 1")
    assert "FULANO DE TESTE" in detalhes
    assert "000.000.050-70" not in detalhes and "00000005070" not in detalhes


# --------------- M11: a resposta da autenticação não vai para a mensagem

@pytest.mark.parametrize("modulo", ["onr_api", "cnib_api"])
def test_autenticacao_sem_token_diz_os_campos_e_nao_o_corpo(modulo, monkeypatch):
    import importlib
    api = importlib.import_module(modulo)
    corpo = {"refresh_token": "segredo-que-nao-sai-0003", "token_type": "Bearer"}
    monkeypatch.setattr(api, "_TOKENS", {})
    monkeypatch.setattr(api, "credencial", lambda *a, **k: ("id-teste", "seg-teste"))
    monkeypatch.setattr(api, "_bater_cru", lambda *a, **k: {
        "status": 200, "json": corpo, "texto": json.dumps(corpo)})
    erro = {"onr_api": "OnrError", "cnib_api": "CnibError"}[modulo]
    with pytest.raises(getattr(api, erro)) as achado:
        api.token("PRODUCAO")
    assert "segredo-que-nao-sai" not in str(achado.value)
    assert "refresh_token" in str(achado.value)


# ------------------ M1: o comando em curso das outras conexões

def _ctx_do_agente(cg_casa):
    import agente_ferramentas as FER
    return FER.Contexto(db=cg_casa["db"], raiz=Path(BKP.__file__).resolve().parent,
                        pasta_de_dados=cg_casa["dados"], agora="2026-10-19T10:00:00",
                        usuario="MARIO EXEMPLO DOS SANTOS", sessao_id=1,
                        versao="teste", app=cg_casa["app"])


@pytest.mark.parametrize("consulta", [
    "SELECT pid, query FROM pg_stat_activity ORDER BY pid",
    "SELECT s.q FROM (SELECT pid, query AS q FROM pg_stat_activity) AS s",
    "SELECT a FROM pg_stat_activity AS a",
    "SELECT pg_stat_get_activity(NULL) AS x",
    "SELECT pg_stat_get_backend_activity(1) AS x",
])
def test_o_agente_nao_le_o_comando_em_curso_das_outras_conexoes(cg_casa, consulta):
    import agente_ferramentas as FER
    r = FER.executar(_ctx_do_agente(cg_casa), "consultar_banco", {"consulta": consulta})
    assert r["erro"] is True, r["conteudo"]


def test_quem_trava_quem_continua_respondendo_sem_a_query(cg_casa):
    import agente_ferramentas as FER
    r = FER.executar(_ctx_do_agente(cg_casa), "consultar_banco", {
        "consulta": "SELECT pid, state, wait_event_type, wait_event, query_start "
                    "FROM pg_stat_activity ORDER BY pid"})
    assert r["erro"] is False, r["conteudo"]
