"""Hotfix de 16/10/2026: nenhuma pasta padrão mora no E-Ofício (C:\\ARPNET).

A cargas do RCPN era ESCRITA lá — e a suíte, rodada no servidor, gravava
arquivos de serventia fictícia na pasta de onde o balcão sobe as cargas.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import pastas_da_casa as PDC  # noqa: E402


def test_nenhum_modulo_aponta_para_a_pasta_do_eoficio():
    achados = []
    for p in sorted(RAIZ.glob("*.py")) + sorted((RAIZ / "tools").glob("*.py")):
        if p.name == "pastas_da_casa.py":
            continue
        for n, linha in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if re.search(r"ARPNET", linha, re.I):
                achados.append(f"{p.name}:{n}: {linha.strip()[:80]}")
    assert not achados, "caminho do E-Ofício de volta no código:\n" + "\n".join(achados)


def test_as_cargas_do_rcpn_ficam_ao_lado_do_banco(tmp_path):
    banco = tmp_path / "cartorio_gestao.sqlite3"
    assert PDC.cargas_rcpn(banco=banco) == tmp_path / "arquivos" / "rcpn" / "cargas"
    assert PDC.cargas_rcpn(banco=banco, archive_root=str(tmp_path / "x")) == tmp_path / "x" / "rcpn" / "cargas"


def test_a_pasta_do_agente_de_cargas_nao_sai_do_banco_do_teste(cg_casa):
    import sqlite3
    import gestor_cargas_rcpn as G
    con = sqlite3.connect(cg_casa["banco"])
    try:
        pasta = G.pasta(con, Path(cg_casa["banco"]))
    finally:
        con.close()
    assert Path(cg_casa["banco"]).parent in pasta.parents


def test_o_de_para_dos_caminhos_antigos(tmp_path):
    assert PDC.novo_caminho(r"C:\ARPNET\C11\CARGAS_RCPN", tmp_path) == tmp_path / "rcpn" / "cargas"
    assert PDC.novo_caminho(r"C:\ARPNET\C11\ONR\IMAGENS", tmp_path) == tmp_path / "eoficio" / "ONR_IMAGENS"
    assert PDC.novo_caminho(r"c:\arpnet\cra\Remessa", tmp_path) == tmp_path / "eoficio" / "CRA" / "Remessa"
    assert PDC.novo_caminho(r"D:\outra\coisa", tmp_path) is None
