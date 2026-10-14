from __future__ import annotations

import hashlib

from tools.conferir_atualizacao import digests_dos


def test_hashes_paralelos_sao_os_sha256_dos_mesmos_arquivos(tmp_path):
    primeiro = tmp_path / "a.txt"
    segundo = tmp_path / "pasta" / "b.bin"
    segundo.parent.mkdir()
    primeiro.write_bytes(b"primeiro")
    segundo.write_bytes(bytes(range(256)) * 32)
    arquivos = [(primeiro, "a.txt"), (segundo, "pasta/b.bin")]

    assert digests_dos(arquivos) == {
        "a.txt": hashlib.sha256(primeiro.read_bytes()).hexdigest(),
        "pasta/b.bin": hashlib.sha256(segundo.read_bytes()).hexdigest(),
    }


def test_hashes_de_lista_vazia_nao_abrem_executor():
    assert digests_dos([]) == {}
