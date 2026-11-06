"""Todo `EMOL.<nome>` que um módulo usa existe no `emolumentos.py`.

RELATOS #160 E #161 (05/11/2026). O `caixa_web.py` passou a chamar
`EMOL.aviso_do_revogado` (#306), e uma cópia em que o `caixa_web.py` chegou
sem o `emolumentos.py` correspondente fez o protocolo do caixa estourar com
`AttributeError` em todo item acrescentado pela tabela: o balcão não
conseguia pôr o 16.3 no protocolo. Nada acusava a falta antes de alguém
clicar.

O teste lê os arquivos (AST), não os importa: o que se confere é o par de
arquivos que vai junto, e a leitura não abre banco nem roda nada do módulo.
"""
from __future__ import annotations

import ast
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def _nomes_definidos(fonte: str) -> set[str]:
    """O que o módulo expõe no nível de cima: def, class, atribuição, import."""
    nomes: set[str] = set()
    for no in ast.parse(fonte).body:
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            nomes.add(no.name)
        elif isinstance(no, ast.Assign):
            for alvo in no.targets:
                for n in ast.walk(alvo):
                    if isinstance(n, ast.Name):
                        nomes.add(n.id)
        elif isinstance(no, ast.AnnAssign) and isinstance(no.target, ast.Name):
            nomes.add(no.target.id)
        elif isinstance(no, (ast.Import, ast.ImportFrom)):
            for a in no.names:
                nomes.add((a.asname or a.name).split(".")[0])
    return nomes


def _apelidos_do_emolumentos(arvore: ast.AST) -> set[str]:
    """Os nomes com que o arquivo importa o módulo (`EMOL`, `emolumentos`...)."""
    apelidos: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            for a in no.names:
                if a.name == "emolumentos":
                    apelidos.add(a.asname or a.name)
    return apelidos


def faltando(pasta: Path) -> dict[str, list[str]]:
    """{arquivo: [nomes usados que o emolumentos.py da pasta não tem]}."""
    definidos = _nomes_definidos(
        (pasta / "emolumentos.py").read_text(encoding="utf-8"))
    falta: dict[str, list[str]] = {}
    for arquivo in sorted(pasta.glob("*.py")):
        if arquivo.name == "emolumentos.py":
            continue
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
        apelidos = _apelidos_do_emolumentos(arvore)
        if not apelidos:
            continue
        usados = {
            no.attr for no in ast.walk(arvore)
            if isinstance(no, ast.Attribute)
            and isinstance(no.value, ast.Name) and no.value.id in apelidos
        }
        ausentes = sorted(usados - definidos)
        if ausentes:
            falta[arquivo.name] = ausentes
    return falta


def test_todo_nome_usado_do_emolumentos_existe():
    assert faltando(RAIZ) == {}


def test_o_caixa_usa_o_aviso_do_revogado_e_ele_existe():
    """O caso do relato: o par caixa_web/emolumentos tem de andar junto."""
    caixa = (RAIZ / "caixa_web.py").read_text(encoding="utf-8")
    assert "EMOL.aviso_do_revogado" in caixa
    assert "aviso_do_revogado" in _nomes_definidos(
        (RAIZ / "emolumentos.py").read_text(encoding="utf-8"))


def test_acusa_o_caixa_novo_com_o_emolumentos_velho(tmp_path):
    """Reproduz a cópia parcial: o caixa chama o que o emolumentos não tem."""
    (tmp_path / "emolumentos.py").write_text(
        "from caixa_schema import centavos\n\n"
        "def calcular_item(con, **kw):\n    return None\n",
        encoding="utf-8")
    (tmp_path / "caixa_web.py").write_text(
        "import emolumentos as EMOL\n\n"
        "def rota(item):\n"
        "    EMOL.calcular_item(None)\n"
        "    EMOL.centavos('1,00')\n"
        "    return EMOL.aviso_do_revogado(item['codigo_tj'], item['descricao'])\n",
        encoding="utf-8")
    (tmp_path / "outro.py").write_text("import json\n", encoding="utf-8")
    assert faltando(tmp_path) == {"caixa_web.py": ["aviso_do_revogado"]}
