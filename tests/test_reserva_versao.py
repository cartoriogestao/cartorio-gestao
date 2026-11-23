"""A versão do programa na reserva: a decisão, o pacote e a troca da pasta."""
from __future__ import annotations

import base64
import hashlib
import json
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import assinatura_da_atualizacao as ASS  # noqa: E402
import reserva_versao as RV  # noqa: E402

ed25519 = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.ed25519")


def _arvore(pasta: Path, versao: str, requisitos: str = "flask\n") -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "VERSAO.txt").write_text(versao + "\n", encoding="utf-8")
    (pasta / "app.py").write_text(f'VERSION = "{versao}"\n', encoding="utf-8")
    (pasta / "requirements.txt").write_text(requisitos, encoding="utf-8")
    cache = pasta / "__pycache__"
    cache.mkdir()
    (cache / "app.pyc").write_bytes(b"\x00")


def _cgu(destino: Path, versao: str, privada=None, *, requisitos="flask\nnovo\n", extras=None,
         apagar=(), min_version="0") -> Path:
    """Um `.cgu` como o da release: só o que mudou, assinado por `privada` (None: sem assinatura)."""
    arquivos = {"VERSAO.txt": f"{versao}\n".encode(), "app.py": f'VERSION = "{versao}"\n'.encode(),
                "requirements.txt": requisitos.encode(), **(extras or {})}
    manifesto = json.dumps({
        "product": "CartorioGestao", "format": 1, "version": versao, "min_version": min_version,
        "notes": "", "run_pip": False, "delete": list(apagar),
        "files": [{"path": rel, "sha256": hashlib.sha256(dados).hexdigest()}
                  for rel, dados in arquivos.items()]}).encode()
    with zipfile.ZipFile(destino, "w") as pacote:
        pacote.writestr("update_manifest.json", manifesto)
        if privada is not None:
            pacote.writestr(ASS.NOME_NO_PACOTE, json.dumps(ASS.assinar(manifesto, privada)))
        for rel, dados in arquivos.items():
            pacote.writestr(f"payload/{rel}", dados)
    return destino


@pytest.fixture
def chave(monkeypatch):
    """A chave do oficial, cadastrada nesta instalação de teste."""
    privada = ed25519.Ed25519PrivateKey.generate()
    crua = ASS.publica_crua(privada)
    monkeypatch.setattr(ASS, "CHAVES_CONFIAVEIS", {ASS.id_da_chave(crua): base64.b64encode(crua).decode()})
    monkeypatch.setattr(ASS, "CHAVES_ILEGIVEIS", "")
    return privada


class _Banco:
    def __init__(self):
        self.s: dict[str, str] = {}
        self.escritas = 0

    def get_setting(self, chave, padrao=""):
        return self.s.get(chave, padrao)

    def set_settings(self, valores):
        self.escritas += 1
        self.s.update(valores)


def test_a_publicacao_so_grava_quando_o_numero_muda():
    banco = _Banco()
    assert RV.publicar(banco, "3.7.17") is True
    assert RV.publicar(banco, "3.7.17") is False
    assert banco.escritas == 1
    assert banco.s[RV.CHAVE] == "3.7.17"


def test_versao_fora_do_formato_nao_grava():
    banco = _Banco()
    with pytest.raises(ValueError):
        RV.publicar(banco, "3.7.17; rm -rf")
    assert banco.escritas == 0


def test_nove_e_menor_que_dezessete():
    assert RV.decisao("3.7.9", "3.7.17", True) == "aplicar"
    assert RV.decisao("3.7.17", "3.7.9", True) == "recua"


@pytest.mark.parametrize("local, principal, esquema, escolha", [
    ("3.7.17", "3.7.17", True, "em_dia"),
    ("3.7.14", "", True, "sem_publicacao"),
    ("3.7.14", "ainda-nao", False, "sem_publicacao"),
    ("3.7.17", "3.7.14", True, "recua"),
    ("3.7.14", "3.7.17", False, "espera"),
    ("", "3.7.17", True, "aplicar"),
    ("3.7.14", "3.7.17", True, "aplicar"),
])
def test_a_decisao(local, principal, esquema, escolha):
    assert RV.decisao(local, principal, esquema) == escolha


def test_a_url_e_o_pacote_da_release_e_nada_mais():
    assert RV.url_da_versao("3.7.17").endswith("/releases/download/v3.7.17/CartorioGestao-3.7.17.cgu")
    with pytest.raises(ValueError):
        RV.url_da_versao("3.7.17/../outra")


class _Resposta:
    def __init__(self, url, dados):
        self._url = url
        self._dados = dados

    def geturl(self):
        return self._url

    def read(self, n):
        pedaco, self._dados = self._dados[:n], self._dados[n:]
        return pedaco

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_baixar_recusa_outro_hospedeiro(tmp_path):
    def abrir(pedido, timeout):
        return _Resposta("https://evil.example/pacote.cgu", b"x" * 2000)

    with pytest.raises(ValueError, match="GitHub"):
        RV.baixar_pacote("3.7.17", tmp_path / "p.cgu", abrir=abrir)
    assert not (tmp_path / "p.cgu").exists()


def test_baixar_recusa_pacote_grande(tmp_path, monkeypatch):
    monkeypatch.setattr(RV, "TAMANHO_MAXIMO", 100)

    def abrir(pedido, timeout):
        return _Resposta("https://release-assets.githubusercontent.com/x", b"x" * 250)

    with pytest.raises(ValueError, match="100 MB"):
        RV.baixar_pacote("3.7.17", tmp_path / "p.cgu", abrir=abrir)


def test_baixar_aceita_o_deposito_atual_das_releases(tmp_path):
    def abrir(pedido, timeout):
        return _Resposta("https://release-assets.githubusercontent.com/x", b"x" * 2000)

    RV.baixar_pacote("3.7.17", tmp_path / "p.cgu", abrir=abrir)
    assert (tmp_path / "p.cgu").stat().st_size == 2000


def _instalada(tmp_path: Path) -> Path:
    sistema = tmp_path / "sistema"
    _arvore(sistema, "3.7.14", "flask\n")
    (sistema / RV.ARQUIVO_DAS_CHAVES).write_text('{"chaves": {}}', encoding="utf-8")
    (sistema / "fica.py").write_text("x = 1\n", encoding="utf-8")
    (sistema / "sai.py").write_text("x = 2\n", encoding="utf-8")
    return sistema


def test_a_versao_nova_e_a_atual_mais_o_pacote_e_a_chave_fica(tmp_path, chave):
    sistema = _instalada(tmp_path)
    pacote = _cgu(tmp_path / "p.cgu", "3.7.17", chave, extras={"tools/novo.py": b"y = 1\n"},
                  apagar=["sai.py"])
    assert RV.executar(sistema, "3.7.17", "3.7.14", True, baixar=lambda _v, d: d.write_bytes(pacote.read_bytes()),
                       instalar=lambda pasta: None, reiniciar=lambda: None) == 0
    assert (sistema / "VERSAO.txt").read_text(encoding="utf-8").strip() == "3.7.17"
    assert (sistema / RV.ARQUIVO_DAS_CHAVES).read_text(encoding="utf-8") == '{"chaves": {}}'
    assert (sistema / "fica.py").is_file() and (sistema / "tools" / "novo.py").is_file()
    assert not (sistema / "sai.py").exists()


def _recusa(tmp_path, capsys, pacote, frase):
    sistema = _instalada(tmp_path)

    def nao_reinicia():
        raise AssertionError("pacote recusado não reinicia nada")

    assert RV.executar(sistema, "3.7.17", "3.7.14", True, baixar=lambda _v, d: d.write_bytes(pacote.read_bytes()),
                       instalar=lambda pasta: None, reiniciar=nao_reinicia) == 1
    saida = capsys.readouterr().out
    assert "não troquei o código" in saida and frase in saida
    assert (sistema / "VERSAO.txt").read_text(encoding="utf-8").strip() == "3.7.14"
    assert (sistema / RV.ARQUIVO_DAS_CHAVES).is_file()


def test_pacote_sem_assinatura_nao_entra(tmp_path, capsys, chave):
    _recusa(tmp_path, capsys, _cgu(tmp_path / "p.cgu", "3.7.17"), "não é assinado")


def test_pacote_de_outra_chave_nao_entra(tmp_path, capsys, chave):
    outra = ed25519.Ed25519PrivateKey.generate()
    _recusa(tmp_path, capsys, _cgu(tmp_path / "p.cgu", "3.7.17", outra), "não")


def test_sem_chave_cadastrada_a_reserva_nao_troca_sozinha(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(ASS, "CHAVES_CONFIAVEIS", {})
    monkeypatch.setattr(ASS, "CHAVES_ILEGIVEIS", "")
    assinado = _cgu(tmp_path / "p.cgu", "3.7.17", ed25519.Ed25519PrivateKey.generate())
    _recusa(tmp_path, capsys, assinado, "assinatura conferida")


@pytest.mark.parametrize("mexe", [{"extras": {RV.ARQUIVO_DAS_CHAVES: b"{}"}},
                                  {"apagar": [RV.ARQUIVO_DAS_CHAVES]}])
def test_pacote_que_mexe_na_chave_nao_entra(tmp_path, capsys, chave, mexe):
    _recusa(tmp_path, capsys, _cgu(tmp_path / "p.cgu", "3.7.17", chave, **mexe), "chave de atualização")


def test_reserva_mais_velha_que_o_min_version_nao_troca(tmp_path, capsys, chave):
    _recusa(tmp_path, capsys, _cgu(tmp_path / "p.cgu", "3.7.17", chave, min_version="3.7.15"), "3.7.15")


def test_pacote_de_outra_versao_nao_entra(tmp_path, capsys, chave):
    _recusa(tmp_path, capsys, _cgu(tmp_path / "p.cgu", "3.7.16", chave), "principal está na 3.7.17")


def test_o_instalador_nao_apaga_a_chave():
    instalador = Path(__file__).resolve().parent.parent / "installer" / "macos" / "instalar_reserva.sh"
    assert "--exclude chaves_de_atualizacao.json" in instalador.read_text(encoding="utf-8")


def test_trocar_deixa_a_anterior_e_tira_o_cache(tmp_path):
    origem = tmp_path / "origem"
    destino = tmp_path / "sistema"
    _arvore(origem, "3.7.17", "flask\nnovo\n")
    _arvore(destino, "3.7.14", "flask\n")
    assert RV.trocar(origem, destino) is True
    assert (destino / "VERSAO.txt").read_text(encoding="utf-8").strip() == "3.7.17"
    assert (tmp_path / "sistema.anterior" / "VERSAO.txt").read_text(encoding="utf-8").strip() == "3.7.14"
    assert not (destino / "__pycache__").exists()


def test_trocar_nao_mexe_em_repositorio_git(tmp_path):
    origem = tmp_path / "origem"
    destino = tmp_path / "sistema"
    _arvore(origem, "3.7.17")
    _arvore(destino, "3.7.14")
    (destino / ".git").mkdir()
    with pytest.raises(RuntimeError, match="git"):
        RV.trocar(origem, destino)
    assert (destino / "VERSAO.txt").read_text(encoding="utf-8").strip() == "3.7.14"


def test_trocar_desfaz_se_a_nova_nao_entra(tmp_path, monkeypatch):
    origem = tmp_path / "origem"
    destino = tmp_path / "sistema"
    _arvore(origem, "3.7.17")
    _arvore(destino, "3.7.14")
    original = Path.rename
    chamadas = {"n": 0}

    def rename(self, alvo):
        chamadas["n"] += 1
        if chamadas["n"] == 2:
            raise OSError("disco cheio")
        return original(self, alvo)

    monkeypatch.setattr(Path, "rename", rename)
    with pytest.raises(OSError):
        RV.trocar(origem, destino)
    assert (destino / "VERSAO.txt").read_text(encoding="utf-8").strip() == "3.7.14"
    assert not (tmp_path / "sistema.anterior").exists()


@pytest.fixture
def baixar_assinado(chave):
    return lambda versao, destino: _cgu(destino, versao, chave)


def test_espera_o_esquema_e_nao_baixa(tmp_path, capsys):
    sistema = tmp_path / "sistema"
    _arvore(sistema, "3.7.14")

    def baixar(*_args):
        raise AssertionError("não era para baixar")

    assert RV.executar(sistema, "3.7.17", "3.7.14", False, baixar=baixar) == 0
    assert "ESPERA o esquema" in capsys.readouterr().out
    assert (sistema / "VERSAO.txt").read_text(encoding="utf-8").strip() == "3.7.14"


def test_nao_desce_e_nao_baixa(tmp_path, capsys):
    sistema = tmp_path / "sistema"
    _arvore(sistema, "3.7.17")

    def baixar(*_args):
        raise AssertionError("não era para baixar")

    assert RV.executar(sistema, "3.7.14", "3.7.17", True, baixar=baixar) == 0
    assert "não desço" in capsys.readouterr().out


def test_aplica_e_reinicia_quando_o_esquema_ja_chegou(tmp_path, capsys, baixar_assinado):
    sistema = tmp_path / "sistema"
    _arvore(sistema, "3.7.14", "flask\n")
    passos = []

    def instalar(pasta):
        passos.append(("pip", (pasta / "requirements.txt").read_text(encoding="utf-8")))

    def reiniciar():
        passos.append("reinicia")

    codigo = RV.executar(
        sistema, "3.7.17", "3.7.14", True,
        baixar=baixar_assinado, instalar=instalar, reiniciar=reiniciar)
    assert codigo == 0
    assert (sistema / "VERSAO.txt").read_text(encoding="utf-8").strip() == "3.7.17"
    assert passos == [("pip", "flask\nnovo\n"), "reinicia"]
    assert not (tmp_path / "versao-reiniciar.txt").exists()
    assert "3.7.14 -> 3.7.17" in capsys.readouterr().out


def test_servico_que_nao_sobe_fica_para_a_volta_seguinte(tmp_path, capsys, baixar_assinado):
    sistema = tmp_path / "sistema"
    _arvore(sistema, "3.7.14", "flask\n")
    reinicios = {"n": 0}

    def reiniciar():
        reinicios["n"] += 1
        if reinicios["n"] == 1:
            raise RuntimeError("launchctl")

    assert RV.executar(
        sistema, "3.7.17", "3.7.14", True,
        baixar=baixar_assinado, instalar=lambda pasta: None, reiniciar=reiniciar) == 1
    assert (tmp_path / "versao-reiniciar.txt").read_text(encoding="utf-8").strip() == "3.7.17"

    def baixar(*_args):
        raise AssertionError("a versão já está no disco")

    assert RV.executar(
        sistema, "3.7.17", "3.7.17", True,
        baixar=baixar, instalar=lambda pasta: None, reiniciar=reiniciar) == 0
    assert reinicios["n"] == 2
    assert not (tmp_path / "versao-reiniciar.txt").exists()
    assert "serviço reiniciado" in capsys.readouterr().out


def test_o_comando_nao_roda_fora_da_reserva(monkeypatch, capsys):
    import reserva as R
    monkeypatch.delenv("CG_MODO_RESERVA", raising=False)
    monkeypatch.setenv("CG_RESERVA_LOCAL_DSN", "host=127.0.0.1 port=1 user=cg dbname=nada")
    monkeypatch.setenv("CG_RESERVA_PRINCIPAL_DSN", "host=127.0.0.1 port=1 user=cg_replica dbname=nada")
    assert R.main(["versao"]) == 2
    assert "só roda no servidor reserva" in capsys.readouterr().out
