"""O Provimento CNJ 74/2018 está revogado — nenhum fundamento o cita como vigente.

POR QUE ESTE ARQUIVO EXISTE
    O Provimento CN/CNJ 213/2026 (art. 26) revogou o 74/2018. A conferência
    do gestor ainda dava o 74/2018 como fundamento do backup e do disco, e o
    texto ia para o achado e para a tarefa (`legal_ref`) que a equipe lê.
    Fundamento revogado numa cobrança é cobrança sem base: na correição, é a
    primeira coisa que se aponta.

O QUE ELE GUARDA
    - nenhum `.py` de produção, e nenhuma tela, cita o 74/2018 sem dizer na
      mesma linha que ele foi revogado (o texto «Provimento CN 213/2026 (que
      revogou o 74/2018)» é o modo certo de lembrar dele);
    - a procura reconhece as formas em que a citação aparece (o teste não
      passa por não achar nada);
    - as duas regras que citavam o 74/2018 agora citam o 213/2026.
"""
from __future__ import annotations

import os
import re
import shutil
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

# «74/2018», «74/18», «Provimento CNJ 74», «Prov. nº 74», «n. 74, de 31 de
# julho de 2018». O `\b` depois do 74 deixa de fora o 740, o 749...
CITA_O_74 = re.compile(
    r"\b74\s*/\s*(?:20)?18\b"
    r"|\bprov(?:imento|\.)\s*(?:cn[\w/-]*\s*)?(?:n[º°o.]*\s*)?74\b"
    r"|\b74,?\s+de\s+31\s+de\s+julho\s+de\s+2018",
    re.IGNORECASE)
REVOGADO = re.compile(r"revog", re.IGNORECASE)

# Fora da produção: os testes (este arquivo cita o 74 de propósito), o
# ambiente virtual e o que o Python ou o git deixam na pasta. A poda é na
# descida: na cópia principal o `.venv` mora dentro da raiz.
FORA = {"tests", "__pycache__", "venv", "node_modules", "build", "dist"}


def _fontes_de_producao() -> list[Path]:
    saida = []
    for pasta, subpastas, nomes in os.walk(RAIZ):
        subpastas[:] = [d for d in subpastas if d not in FORA and not d.startswith(".")]
        saida.extend(Path(pasta) / n for n in nomes if n.endswith(".py"))
    return sorted(saida)


def _cita_como_vigente(linha: str) -> bool:
    return bool(CITA_O_74.search(linha)) and not REVOGADO.search(linha)


def _citacoes_vigentes(arquivos) -> list[str]:
    saida = []
    for p in arquivos:
        texto = p.read_text(encoding="utf-8", errors="replace")
        for n, linha in enumerate(texto.splitlines(), 1):
            if _cita_como_vigente(linha):
                saida.append(f"{p.relative_to(RAIZ)}:{n}: {linha.strip()}")
    return saida


def test_a_procura_acha_a_citacao_antiga_e_aceita_a_que_diz_revogado():
    for antiga in ('None, "Provimento CNJ 74/2018")]',
                   "Provimento CN/CNJ n. 74, de 31 de julho de 2018",
                   "conforme o Prov. nº 74",
                   "Provimento 74/18"):
        assert _cita_como_vigente(antiga), antiga
    for certa in ('None, "Provimento CN 213/2026 (que revogou o 74/2018)")]',
                  "Provimento CNJ 39/2014",
                  "Provimento CNJ 149/2023",
                  "Provimento CNJ 740/2018"):
        assert not _cita_como_vigente(certa), certa


def test_nenhum_py_de_producao_cita_o_74_2018_como_vigente():
    fontes = _fontes_de_producao()
    assert len(fontes) > 300, "a procura não achou o código — a raiz mudou?"
    assert _citacoes_vigentes(fontes) == [], (
        "O Provimento CNJ 74/2018 foi revogado pelo CN/CNJ 213/2026 (art. 26). "
        "Cite o dispositivo equivalente do 213/2026 ou, sem equivalente claro, "
        "«Provimento CN 213/2026 (que revogou o 74/2018)».")


def test_nenhuma_tela_cita_o_74_2018_como_vigente():
    telas = sorted([*(RAIZ / "templates").rglob("*.html"),
                    *(RAIZ / "static").rglob("*.js")])
    assert telas, "a procura não achou as telas"
    assert _citacoes_vigentes(telas) == []


def test_backup_e_disco_fundamentam_no_213_2026(tmp_path, monkeypatch):
    import gestor_conferencia as GC
    monkeypatch.delenv("CARTORIO_GESTAO_COPIAS", raising=False)
    con = conexao_de_teste()
    try:
        con.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
        backup = GC.regra_backup(con, date(2026, 10, 19), tmp_path)
    finally:
        con.close()
    assert [a["regra"] for a in backup] == ["BACKUP"], "sem backup nenhum, a regra acusa"
    assert backup[0]["fundamento"] == "Provimento CN/CNJ 213/2026, art. 12, § 3º, I, e § 10"

    # 1 GB livre: abaixo do crítico. A regra não olha o banco.
    monkeypatch.setattr(shutil, "disk_usage",
                        lambda _: SimpleNamespace(total=500 * 1024 ** 3,
                                                  used=499 * 1024 ** 3, free=1024 ** 3))
    disco = GC.regra_disco(None, date(2026, 10, 19), tmp_path)
    assert [a["regra"] for a in disco] == ["DISCO"]
    assert disco[0]["fundamento"] == "Provimento CN 213/2026 (que revogou o 74/2018)"
