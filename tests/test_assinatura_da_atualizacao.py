"""A atualização segura (12/10/2026): o pacote diz quem o fez e de onde saiu.

Três coisas protegidas aqui:
- a ASSINATURA: com chave cadastrada, só passa o pacote assinado pelo oficial,
  e qualquer byte mudado no manifesto depois da assinatura derruba o pacote;
- a TRANSIÇÃO: sem chave cadastrada, o pacote sem assinatura passa como antes
  (a produção de hoje não pode ficar sem como se atualizar);
- o VERSIONAMENTO: o empacotador grava o commit, escreve-o no manifesto, põe a
  etiqueta com o SHA-256 do pacote e recusa reempacotar a mesma versão.
Nada aqui toca o git da casa: o repositório é criado em tmp_path.
"""
from __future__ import annotations

import base64
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

ed25519 = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.ed25519")

import assinatura_da_atualizacao as ASS   # noqa: E402
import update_manager as UM               # noqa: E402


def _par():
    privada = ed25519.Ed25519PrivateKey.generate()
    crua = ASS.publica_crua(privada)
    return privada, {ASS.id_da_chave(crua): base64.b64encode(crua).decode()}


def _pacote(caminho: Path, *, versao="3.6.2", privada=None, mexer=None) -> Path:
    dados = b'VERSION = "%s"\n' % versao.encode()
    manifesto = {"product": "CartorioGestao", "format": 1, "version": versao,
                 "min_version": "0", "notes": "", "run_pip": False,
                 "files": [{"path": "app.py",
                            "sha256": hashlib.sha256(dados).hexdigest()}],
                 "delete": []}
    m = json.dumps(manifesto, indent=2).encode()
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr("update_manifest.json", mexer(m) if mexer else m)
        if privada is not None:
            z.writestr(ASS.NOME_NO_PACOTE, json.dumps(ASS.assinar(m, privada)))
        z.writestr("payload/app.py", dados)
    return caminho


# ------------------------------------------------------------- a assinatura

def test_o_manifesto_assinado_confere_com_a_chave_cadastrada():
    privada, chaves = _par()
    m = b'{"x": 1}'
    r = ASS.conferir(m, json.dumps(ASS.assinar(m, privada)).encode(), chaves)
    assert r["situacao"] == "ASSINADO"


def test_um_byte_mudado_depois_de_assinar_derruba_a_assinatura():
    privada, chaves = _par()
    assinatura = json.dumps(ASS.assinar(b'{"x": 1}', privada)).encode()
    with pytest.raises(ASS.AssinaturaRecusada, match="não confere"):
        ASS.conferir(b'{"x": 2}', assinatura, chaves)


def test_chave_que_a_instalacao_nao_conhece_e_recusada():
    _, chaves = _par()
    outra, _ = _par()
    m = b"{}"
    with pytest.raises(ASS.AssinaturaRecusada, match="não reconhece"):
        ASS.conferir(m, json.dumps(ASS.assinar(m, outra)).encode(), chaves)


def test_com_chave_cadastrada_o_pacote_sem_assinatura_e_recusado():
    _, chaves = _par()
    with pytest.raises(ASS.AssinaturaRecusada, match="não é assinado"):
        ASS.conferir(b"{}", None, chaves)


def test_sem_chave_cadastrada_o_pacote_sem_assinatura_passa_e_se_diz_nao_assinado():
    assert ASS.conferir(b"{}", None, {})["situacao"] == "NAO_ASSINADO"


# ------------------------------------------------------------ no atualizador

def test_o_atualizador_aceita_o_pacote_assinado(tmp_path, monkeypatch):
    privada, chaves = _par()
    monkeypatch.setattr(ASS, "CHAVES_CONFIAVEIS", chaves)
    pacote = _pacote(tmp_path / "p.cgu", privada=privada)
    meta = UM.validate_and_stage(pacote, tmp_path / "stage", "3.6.1")
    assert meta["assinatura"]["situacao"] == "ASSINADO"


def test_o_atualizador_recusa_o_manifesto_mexido_antes_de_escrever_qualquer_arquivo(
        tmp_path, monkeypatch):
    privada, chaves = _par()
    monkeypatch.setattr(ASS, "CHAVES_CONFIAVEIS", chaves)
    pacote = _pacote(tmp_path / "p.cgu", privada=privada,
                     mexer=lambda m: m.replace(b'"notes": ""', b'"notes": "x"'))
    with pytest.raises(UM.UpdateError, match="não confere"):
        UM.validate_and_stage(pacote, tmp_path / "stage", "3.6.1")
    assert not (tmp_path / "stage" / "3.6.2").exists()


def test_o_atualizador_exige_assinatura_quando_ha_chave(tmp_path, monkeypatch):
    _, chaves = _par()
    monkeypatch.setattr(ASS, "CHAVES_CONFIAVEIS", chaves)
    with pytest.raises(UM.UpdateError, match="não é assinado"):
        UM.validate_and_stage(_pacote(tmp_path / "p.cgu"), tmp_path / "stage", "3.6.1")


def test_na_transicao_o_pacote_sem_assinatura_continua_entrando(tmp_path, monkeypatch):
    monkeypatch.setattr(ASS, "CHAVES_CONFIAVEIS", {})
    meta = UM.validate_and_stage(_pacote(tmp_path / "p.cgu"), tmp_path / "stage", "3.6.1")
    assert meta["assinatura"]["situacao"] == "NAO_ASSINADO"


# ----------------------------------------------------- a ferramenta da chave

def test_a_chave_nao_se_grava_dentro_do_projeto():
    import tools.chave_de_atualizacao as CH
    with pytest.raises(SystemExit, match="Recusado"):
        CH.gerar(RAIZ / "nao_grave_aqui.pem", "senha-bem-comprida-123")
    assert not (RAIZ / "nao_grave_aqui.pem").exists()


def test_a_chave_gerada_abre_com_a_senha_e_nao_sem_ela(tmp_path, monkeypatch):
    import tools.chave_de_atualizacao as CH
    monkeypatch.setattr(CH, "pastas_proibidas", lambda: [])
    destino = tmp_path / "chave.pem"
    chave_id, publica = CH.gerar(destino, "senha-bem-comprida-123")
    privada = ASS.carregar_privada(destino.read_bytes(), b"senha-bem-comprida-123")
    assert ASS.id_da_chave(ASS.publica_crua(privada)) == chave_id
    with pytest.raises(ASS.AssinaturaRecusada):
        ASS.carregar_privada(destino.read_bytes(), b"senha-errada-qualquer")
    with pytest.raises(SystemExit, match="já existe"):
        CH.gerar(destino, "senha-bem-comprida-123")


# --------------------------------------------- o empacotador e o versionamento

@pytest.mark.skipif(shutil.which("git") is None, reason="precisa do git")
def test_o_empacotador_grava_o_commit_etiqueta_e_recusa_a_mesma_versao(tmp_path):
    casa = tmp_path / "CartorioGestao"
    git_dir = casa / "VERSIONAMENTO" / "casa.git"
    subprocess.run(["git", "init", "-q", "--bare", str(git_dir)], check=True)
    origem = casa / "SERVIDOR" / "INSTALAR_CARTORIO_GESTAO"
    origem.mkdir(parents=True)
    (origem / "VERSAO.txt").write_text("9.9.1", encoding="utf-8")
    (origem / "app.py").write_text('VERSION = "9.9.1"\n', encoding="utf-8")
    saida = tmp_path / "p.cgu"
    cmd = [sys.executable, str(RAIZ / "tools" / "criar_atualizacao.py"), str(origem),
           "--version", "9.9.1", "--min-version", "0", "--output", str(saida),
           "--notes", "teste"]
    r = subprocess.run(cmd, capture_output=True)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")

    def git(*a):
        return subprocess.run(["git", f"--git-dir={git_dir}", *a], capture_output=True,
                              check=True).stdout.decode().strip()

    commit = git("rev-parse", "main")
    with zipfile.ZipFile(saida) as z:
        manifesto = json.loads(z.read("update_manifest.json"))
    assert manifesto["source_commit"] == commit
    sha = hashlib.sha256(saida.read_bytes()).hexdigest()
    assert sha in git("tag", "-n9", "v9.9.1") or sha in git("cat-file", "-p", "v9.9.1")
    assert git("rev-parse", "v9.9.1^{commit}") == commit

    # a mesma versão de novo: recusada, e nenhum pacote novo sai
    saida.unlink()
    r2 = subprocess.run(cmd, capture_output=True)
    assert r2.returncode != 0
    assert "ja foi empacotada" in (r2.stdout + r2.stderr).decode("utf-8", "replace")
    assert not saida.exists()
