"""A versão do programa na reserva: a decisão, o pacote e a troca da pasta."""
from __future__ import annotations

import io
import sys
import tarfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import reserva_versao as RV  # noqa: E402


def _arvore(pasta: Path, versao: str, requisitos: str = "flask\n") -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "VERSAO.txt").write_text(versao + "\n", encoding="utf-8")
    (pasta / "app.py").write_text(f'VERSION = "{versao}"\n', encoding="utf-8")
    (pasta / "requirements.txt").write_text(requisitos, encoding="utf-8")
    cache = pasta / "__pycache__"
    cache.mkdir()
    (cache / "app.pyc").write_bytes(b"\x00")


def _tar(destino: Path, versao: str, requisitos: str = "flask\n") -> None:
    raiz = destino.parent / f"montar-{versao}"
    if raiz.exists():
        import shutil
        shutil.rmtree(raiz)
    _arvore(raiz, versao, requisitos)
    with tarfile.open(destino, "w:gz") as tar:
        tar.add(raiz, arcname=f"cartorio-gestao-{versao}")


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


def test_a_url_e_a_etiqueta_e_nada_mais():
    assert RV.url_da_versao("3.7.17").endswith("/v3.7.17.tar.gz")
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
        return _Resposta("https://evil.example/pacote.tar.gz", b"x" * 2000)

    with pytest.raises(ValueError, match="GitHub"):
        RV.baixar_pacote("3.7.17", tmp_path / "p.tar.gz", abrir=abrir)
    assert not (tmp_path / "p.tar.gz").exists()


def test_baixar_recusa_pacote_grande(tmp_path, monkeypatch):
    monkeypatch.setattr(RV, "TAMANHO_MAXIMO", 100)

    def abrir(pedido, timeout):
        return _Resposta("https://codeload.github.com/cartoriogestao/x", b"x" * 250)

    with pytest.raises(ValueError, match="200 MB"):
        RV.baixar_pacote("3.7.17", tmp_path / "p.tar.gz", abrir=abrir)


def test_extrair_recusa_caminho_que_sai(tmp_path):
    arquivo = tmp_path / "mau.tar.gz"
    with tarfile.open(arquivo, "w:gz") as tar:
        info = tarfile.TarInfo("../fora.txt")
        info.size = 1
        tar.addfile(info, io.BytesIO(b"x"))
    with pytest.raises(ValueError, match="recusado"):
        RV.extrair(arquivo, tmp_path / "out", "3.7.17")
    assert not (tmp_path / "fora.txt").exists()


def test_extrair_recusa_atalho(tmp_path):
    arquivo = tmp_path / "atalho.tar.gz"
    with tarfile.open(arquivo, "w:gz") as tar:
        info = tarfile.TarInfo("cartorio-gestao-3.7.17/link")
        info.type = tarfile.SYMTYPE
        info.linkname = "/etc/passwd"
        tar.addfile(info)
    with pytest.raises(ValueError, match="recusado"):
        RV.extrair(arquivo, tmp_path / "out", "3.7.17")


def test_extrair_confere_o_numero(tmp_path):
    arquivo = tmp_path / "ok.tar.gz"
    _tar(arquivo, "3.7.17")
    raiz = RV.extrair(arquivo, tmp_path / "out", "3.7.17")
    assert (raiz / "app.py").read_text(encoding="utf-8").strip() == 'VERSION = "3.7.17"'
    with pytest.raises(ValueError, match="principal"):
        RV.extrair(arquivo, tmp_path / "out2", "3.7.16")


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


def _baixar_de_teste(versao, destino, requisitos="flask\nnovo\n"):
    _tar(destino, versao, requisitos)


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


def test_aplica_e_reinicia_quando_o_esquema_ja_chegou(tmp_path, capsys):
    sistema = tmp_path / "sistema"
    _arvore(sistema, "3.7.14", "flask\n")
    passos = []

    def instalar(pasta):
        passos.append(("pip", (pasta / "requirements.txt").read_text(encoding="utf-8")))

    def reiniciar():
        passos.append("reinicia")

    codigo = RV.executar(
        sistema, "3.7.17", "3.7.14", True,
        baixar=_baixar_de_teste, instalar=instalar, reiniciar=reiniciar)
    assert codigo == 0
    assert (sistema / "VERSAO.txt").read_text(encoding="utf-8").strip() == "3.7.17"
    assert passos == [("pip", "flask\nnovo\n"), "reinicia"]
    assert not (tmp_path / "versao-reiniciar.txt").exists()
    assert "3.7.14 -> 3.7.17" in capsys.readouterr().out


def test_servico_que_nao_sobe_fica_para_a_volta_seguinte(tmp_path, capsys):
    sistema = tmp_path / "sistema"
    _arvore(sistema, "3.7.14", "flask\n")
    reinicios = {"n": 0}

    def reiniciar():
        reinicios["n"] += 1
        if reinicios["n"] == 1:
            raise RuntimeError("launchctl")

    assert RV.executar(
        sistema, "3.7.17", "3.7.14", True,
        baixar=_baixar_de_teste, instalar=lambda pasta: None, reiniciar=reiniciar) == 1
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
