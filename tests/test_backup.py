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
