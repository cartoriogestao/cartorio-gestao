"""Publicacao no NAS: nada definitivo antes do hash; local so sai apos confirmar."""
import shutil
import json
from datetime import datetime, timedelta
from sqlite3.dbapi2 import connect as conectar_sqlite
import zipfile
from pathlib import Path

import pytest
import backup as B
import permissao_local


@pytest.fixture
def rede(tmp_path, monkeypatch):
    class Banco:
        db_path = tmp_path / "banco-ficticio.sqlite3"
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
    monkeypatch.setenv("CARTORIO_GESTAO_COPIAS", str(tmp_path / "nas"))
    destino = tmp_path / "nas" / "backups" / "backup.zip"
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
    destino.parent.mkdir(parents=True)
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


@pytest.mark.parametrize("nome", ["../fora.zip", "../backups-maliciosos/f.zip", "arquivo:fluxo.zip", "backup.exe"])
def test_destino_fora_da_raiz_ou_nome_invalido_e_recusado(rede, nome):
    db, arquivos, destino, area = rede
    with pytest.raises(B.BackupInvalido):
        B.gerar_pacote(db, destino.parent / nome, arquivos)
    assert not area.exists()


def test_destino_unc_exige_raiz_administrativa(rede, monkeypatch):
    db, arquivos, destino, area = rede
    monkeypatch.delenv("CARTORIO_GESTAO_COPIAS")
    with pytest.raises(B.BackupInvalido, match="raiz administrativa"):
        B.gerar_pacote(db, destino, arquivos)
    assert not area.exists()


@pytest.mark.parametrize("nome", ["backup_pre_atualizacao_3.7.19_para_../../fora_20261116.zip", "backup_pre_atualizacao_3.7.19_para_versao:fluxo_20261116.zip"])
def test_nome_da_versao_nao_cria_caminho_ou_fluxo(rede, nome):
    db, arquivos, destino, area = rede
    with pytest.raises(B.BackupInvalido):
        B.gerar_pacote(db, destino.parent / nome, arquivos)
    assert not area.exists()


def _guardar_para_retomar(rede, monkeypatch):
    db, arquivos, destino, area = rede
    original = B._publicar_pacote
    def falhar(local, destino):
        raise OSError("rede ficticia indisponivel")
    monkeypatch.setattr(B, "_publicar_pacote", falhar)
    with pytest.raises(B.BackupInvalido):
        B.gerar_pacote(db, destino, arquivos)
    monkeypatch.setattr(B, "_publicar_pacote", original)
    return next(area.glob("envio-backup-*/*.zip"))


def test_retomada_confere_pacote_sem_refazer_banco_e_limpa_apos_copia(rede, monkeypatch):
    db, arquivos, destino, area = rede
    local = _guardar_para_retomar(rede, monkeypatch)
    esperado = B._sha256(local)
    def proibido(*a, **k):
        pytest.fail("nao deve recriar o banco ao retomar pacote completo")
    monkeypatch.setattr(db, "backup_database", proibido)
    B.gerar_pacote(db, destino, arquivos)
    assert B._sha256(destino) == esperado and list(area.iterdir()) == []


# O valor do `created_at` se calcula DENTRO do teste: com o relógio no parâmetro, cada
# processo do xdist coletava um teste com outro nome, e a suíte da CI nem começava.
HA_DOIS_DIAS = "ha-dois-dias"


@pytest.mark.parametrize("chave,valor", [("origem_banco", "banco-diferente"), ("archive_root", "acervo-diferente"), ("app", "aplicativo-diferente"), ("version", "versao-diferente"), ("created_at", HA_DOIS_DIAS)])
def test_retomada_recusa_origem_ou_pacote_antigo(rede, monkeypatch, chave, valor):
    if valor == HA_DOIS_DIAS:
        valor = (datetime.now() - timedelta(days=2)).isoformat()
    db, arquivos, destino, area = rede
    local = _guardar_para_retomar(rede, monkeypatch)
    with zipfile.ZipFile(local) as z:
        conteudos = {n:z.read(n) for n in z.namelist()}
    meta = json.loads(conteudos[B.NOME_MANIFESTO]);meta[chave]=valor
    conteudos[B.NOME_MANIFESTO]=json.dumps(meta).encode()
    with zipfile.ZipFile(local, "w") as z:
        for n,d in conteudos.items():z.writestr(n,d)
    assert B._completo_para_retomar(area, db, arquivos, "CartorioGestao", "") is None


def test_pouco_espaco_recusa_antes_de_criar_pacote(rede, monkeypatch):
    db, arquivos, destino, area = rede
    from types import SimpleNamespace
    monkeypatch.setattr(shutil, "disk_usage", lambda p: SimpleNamespace(free=1))
    with pytest.raises(B.BackupInvalido, match="espaco local insuficiente"):
        B.gerar_pacote(db, destino, arquivos)
    assert not destino.exists() and list(area.iterdir()) == []


def test_retomada_nao_exige_espaco_para_segundo_completo(rede, monkeypatch):
    db, arquivos, destino, area = rede
    _guardar_para_retomar(rede, monkeypatch)
    from types import SimpleNamespace
    monkeypatch.setattr(shutil, "disk_usage", lambda p: SimpleNamespace(free=1))
    B.gerar_pacote(db, destino, arquivos)
    assert destino.exists() and list(area.iterdir()) == []


def test_pacote_legado_so_pode_ser_retomado_na_propria_producao(rede, monkeypatch):
    db, arquivos, destino, area = rede
    local = _guardar_para_retomar(rede, monkeypatch)
    with zipfile.ZipFile(local) as z:
        conteudos = {n:z.read(n) for n in z.namelist()}
    meta=json.loads(conteudos[B.NOME_MANIFESTO]);meta.pop("origem_banco")
    conteudos[B.NOME_MANIFESTO]=json.dumps(meta).encode()
    with zipfile.ZipFile(local, "w") as z:
        for n,d in conteudos.items():z.writestr(n,d)
    assert B._completo_para_retomar(area, db, arquivos, "CartorioGestao", "") is None
    import os
    db.db_path=Path(os.environ["PROGRAMDATA"])/"CartorioGestao"/"cartorio_gestao.sqlite3"
    assert B._completo_para_retomar(area, db, arquivos, "CartorioGestao", "")==local


def test_hash_cobre_blocos_grandes_e_cauda(tmp_path):
    import hashlib
    conteudo=(b"conteudo-ficticio-" * 530000)+b"cauda"
    arquivo=tmp_path / "hash-ficticio.bin"
    arquivo.write_bytes(conteudo)
    assert B._sha256(arquivo)==hashlib.sha256(conteudo).hexdigest()


def test_manifesto_invalido_preservado_sem_ser_adotado(rede, monkeypatch):
    db, arquivos, destino, area = rede
    local = _guardar_para_retomar(rede, monkeypatch)
    with zipfile.ZipFile(local, "w") as z:z.writestr(B.NOME_MANIFESTO,"[]")
    assert B._completo_para_retomar(area, db, arquivos, "CartorioGestao", "") is None
    assert local.exists()


def test_retomada_registra_agente_e_mandante(rede, monkeypatch):
    db, arquivos, destino, area = rede
    _guardar_para_retomar(rede, monkeypatch)
    registros=[]
    monkeypatch.setattr(db,"log",lambda *a, **k:registros.append((a,k)),raising=False)
    B.gerar_pacote(db, destino, arquivos)
    assert registros and registros[0][0][2]=="BACKUP_ENVIO_RETOMADO"
    assert registros[0][1]["agente"] and registros[0][1]["a_mando_de"]
