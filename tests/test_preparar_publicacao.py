"""tools/preparar_publicacao.py: a árvore pública vira commit com etiqueta — e só
com o portão em zero. O exportador é trocado por um falso, porque o que se
testa aqui é o que vem depois dele: o repositório só do público.
"""
from __future__ import annotations

import subprocess

import pytest

import tools.preparar_publicacao as PP


def _git(destino, *args):
    return subprocess.run(["git", "-C", str(destino), *args], capture_output=True,
                          text=True, check=True).stdout.strip()


@pytest.fixture
def raiz(tmp_path, monkeypatch):
    r = tmp_path / "raiz"
    r.mkdir()
    (r / "VERSAO.txt").write_bytes(b"9.9.1\n")
    monkeypatch.setattr(PP, "RAIZ", r)
    return r


def _exportador(conteudo: dict[str, bytes], volta: int = 0):
    def main(argv):
        assert argv[0] == "--gerar"
        from pathlib import Path
        destino = Path(argv[1])
        destino.mkdir(parents=True, exist_ok=True)
        for nome, dados in conteudo.items():
            (destino / nome).write_bytes(dados)
        (destino / ".exportado_publico").write_bytes(b"marca da maquina")
        return volta
    return main


def test_portao_com_achado_nao_grava_nada(raiz, tmp_path, monkeypatch, capsys):
    destino = tmp_path / "pub"
    monkeypatch.setattr(PP.EXP, "main", _exportador({"a.py": b"x\n"}, volta=1))
    assert PP.main(["--destino", str(destino)]) == 1
    assert not (destino / ".git").exists()
    assert "NADA FOI GRAVADO" in capsys.readouterr().out


def test_grava_commit_e_etiqueta_e_nao_leva_a_marca(raiz, tmp_path, monkeypatch, capsys):
    destino = tmp_path / "pub"
    monkeypatch.setattr(PP.EXP, "main", _exportador({"a.py": b"x\r\n"}))
    assert PP.main(["--destino", str(destino)]) == 0
    assert _git(destino, "tag", "--list") == "v9.9.1"
    arquivos = _git(destino, "ls-files").splitlines()
    assert arquivos == ["a.py"]
    # o fim de linha viaja como está
    assert _git(destino, "show", "HEAD:a.py") == "x"
    assert subprocess.run(["git", "-C", str(destino), "cat-file", "-p", "HEAD:a.py"],
                          capture_output=True).stdout == b"x\r\n"
    saida = capsys.readouterr().out
    assert "push -u origin main --tags" in saida
    assert "remote add origin" in saida


def test_repetir_sem_mudanca_nao_cria_commit(raiz, tmp_path, monkeypatch, capsys):
    destino = tmp_path / "pub"
    monkeypatch.setattr(PP.EXP, "main", _exportador({"a.py": b"x\n"}))
    PP.main(["--destino", str(destino)])
    antes = _git(destino, "rev-parse", "HEAD")
    assert PP.main(["--destino", str(destino)]) == 0
    assert _git(destino, "rev-parse", "HEAD") == antes
    assert "já está publicada" in capsys.readouterr().out


def test_mesma_versao_com_outro_conteudo_e_recusada(raiz, tmp_path, monkeypatch):
    destino = tmp_path / "pub"
    monkeypatch.setattr(PP.EXP, "main", _exportador({"a.py": b"x\n"}))
    PP.main(["--destino", str(destino)])
    monkeypatch.setattr(PP.EXP, "main", _exportador({"a.py": b"y\n"}))
    with pytest.raises(SystemExit, match="suba a versão"):
        PP.main(["--destino", str(destino)])


def test_versao_nova_vira_segundo_commit(raiz, tmp_path, monkeypatch):
    destino = tmp_path / "pub"
    monkeypatch.setattr(PP.EXP, "main", _exportador({"a.py": b"x\n"}))
    PP.main(["--destino", str(destino)])
    (raiz / "VERSAO.txt").write_bytes(b"9.9.2\n")
    monkeypatch.setattr(PP.EXP, "main", _exportador({"a.py": b"y\n"}))
    assert PP.main(["--destino", str(destino)]) == 0
    assert _git(destino, "tag", "--list").splitlines() == ["v9.9.1", "v9.9.2"]
    assert _git(destino, "rev-list", "--count", "HEAD") == "2"
