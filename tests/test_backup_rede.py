"""Publicacao no NAS: nada definitivo antes do hash; local so sai apos confirmar."""
import shutil
from sqlite3.dbapi2 import connect as conectar_sqlite
import zipfile
from pathlib import Path

import pytest
import backup as B
import permissao_local


@pytest.fixture
def rede(tmp_path, monkeypatch):
    class Banco:
        def backup_database(self, destino):
            con = conectar_sqlite(destino)
            con.execute("CREATE TABLE exemplo (id INTEGER)")
            con.execute("INSERT INTO exemplo VALUES (1)")
            con.commit()
            con.close()
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path / "programdata"))
    monkeypatch.setattr(permissao_local, "restringir", lambda *a, **k: None)
    monkeypatch.setattr(B, "_destino_de_rede", lambda p: True)
    arquivos = tmp_path / "arquivos"
    arquivos.mkdir()
    (arquivos / "ficcao.txt").write_text("documento ficticio", encoding="utf-8")
    destino = tmp_path / "nas" / "backup.zip"
    area = tmp_path / "programdata" / "CartorioGestaoOperacao" / "backups_temporarios"
    return Banco(), arquivos, destino, area


def test_unc_e_identificado_sem_afetar_destino_local():
    assert B._destino_de_rede(Path(r"\\servidor\backups\b.zip"))
    assert not B._destino_de_rede(Path("C:/backups/b.zip"))


def test_zip_so_e_montado_no_programdata_e_local_so_sai_apos_hash(rede, monkeypatch):
    db, arquivos, destino, area = rede
    original_zip = zipfile.ZipFile
    gravados = []
    def zip_observado(file, mode="r", *a, **k):
        if mode == "w":
            gravados.append(Path(file))
            assert area in Path(file).parents
        return original_zip(file, mode, *a, **k)
    monkeypatch.setattr(zipfile, "ZipFile", zip_observado)
    hash_original = B._sha256
    conferidos = []
    def hash_observado(p):
        if Path(p).name == "backup.zip.parcial":
            assert list(area.glob("envio-backup-*/backup.zip"))
            assert not destino.exists()
            conferidos.append(Path(p))
        return hash_original(p)
    monkeypatch.setattr(B, "_sha256", hash_observado)
    assert B.gerar_pacote(db, destino, arquivos) == destino
    assert gravados and conferidos
    assert B.conferir(destino) is None
    assert list(area.iterdir()) == []


@pytest.mark.parametrize("senha", [None, "senha-ficticia-somente-teste"])
def test_pacote_transferido_abre_com_e_sem_cifra(rede, senha):
    db, arquivos, destino, area = rede
    B.gerar_pacote(db, destino, arquivos, senha_da_cifra=senha)
    assert B.e_cifrado(destino) == bool(senha)
    assert B.conferir(destino, senha) is None
    assert list(area.iterdir()) == []


def test_erro_de_copia_preserva_local_e_backup_anterior(rede, monkeypatch):
    db, arquivos, destino, area = rede
    destino.parent.mkdir()
    destino.write_bytes(b"backup anterior ficticio")
    def falhar(local, alvo):
        alvo.with_suffix(".zip.parcial").write_bytes(b"interrompido")
        raise OSError("rede caiu")
    monkeypatch.setattr(B, "_publicar_pacote", falhar)
    with pytest.raises(B.BackupInvalido, match="area local preservada"):
        B.gerar_pacote(db, destino, arquivos)
    assert destino.read_bytes() == b"backup anterior ficticio"
    locais = list(area.glob("envio-backup-*/backup.zip"))
    assert len(locais) == 1 and B.conferir(locais[0]) is None


def test_corrupcao_no_nas_nao_publica_nem_apaga_local(rede, monkeypatch):
    db, arquivos, destino, area = rede
    hash_original = B._sha256
    def corromper(p):
        if Path(p) == destino.with_suffix(".zip.parcial"):
            return "0" * 64
        return hash_original(p)
    monkeypatch.setattr(B, "_sha256", corromper)
    with pytest.raises(B.BackupInvalido, match="SHA-256"):
        B.gerar_pacote(db, destino, arquivos)
    assert not destino.exists()
    assert list(area.glob("envio-backup-*/backup.zip"))


def test_nao_grava_backup_se_area_local_nao_ficar_privada(rede, monkeypatch):
    db, arquivos, destino, area = rede
    monkeypatch.setattr(permissao_local, "restringir", lambda *a, **k: "falha ficticia")
    with pytest.raises(B.BackupInvalido, match="proteger"):
        B.gerar_pacote(db, destino, arquivos)
    assert not destino.exists() and not list(area.iterdir())


def test_falha_na_limpeza_nao_perde_registro_do_backup_valido(rede, monkeypatch, caplog):
    db, arquivos, destino, area = rede
    original = shutil.rmtree
    def falhar(path, *a, **k):
        if Path(path).name.startswith("envio-backup-"):
            raise OSError("arquivo ocupado ficticio")
        return original(path, *a, **k)
    monkeypatch.setattr(shutil, "rmtree", falhar)
    assert B.gerar_pacote(db, destino, arquivos) == destino
    assert B.conferir(destino) is None
    assert "nao foi possivel limpar" in caplog.text
    assert list(area.glob("envio-backup-*/backup.zip"))
