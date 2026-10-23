"""A PROVA DAS VARREDURAS DO LD01 — que as 6.224 montagens mudaram só pelas regras.

O ouro do LF06C (`ouro_lf06c_termos.py`) guarda das varreduras só a contagem e
o sha256 das saídas (`varre.nascimento`, `varre.casamento`, `varre.obito`).
O LD01 (21/10/2026) mudou de propósito os termos que elas montam, e o resumo
novo está em `tests/test_modelos_da_casa.py` (`_LD01_VARREDURAS`). Um sha256
novo, sozinho, não diz POR QUE mudou: este script refaz as varreduras caso a
caso, na árvore de antes do LD01 e na de agora, aplica a cada caso de antes as
regras do LD01 e exige que dê o caso de agora — sem nenhum caso de fora.

As regras, as mesmas de `test_modelos_da_casa._ld01_regras`:

    nascimento   os claros novos `frase_natimorto` e `testemunhas` (vazios, ou
                 « morta» no natimorto, que passa a dizer «nasceu morta»)
    casamento    o claro novo `frase_da_celebracao` (vazio: os casos não têm
                 data do fato) e, com a habilitação desta casa e a data dos
                 proclamas, a frase «Os proclamas foram publicados nesta
                 serventia em …»
    óbito        o termo no feminino (a falecida é MARIA DE EXEMPLO) e o sexo
                 dela na qualificação

Uso (o Python sem `CG_PG_DSN`: os padrões saem da pasta de cada árvore):

    git archive 71f21f4 | tar -x -C /tmp/antes_do_ld01
    python -B ld01_varreduras.py /tmp/antes_do_ld01
"""
from __future__ import annotations

import collections
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

PASTA = Path(__file__).resolve().parent
RAIZ = PASTA.parent.parent.parent
VARREDURAS = ("varre.nascimento", "varre.casamento", "varre.obito")

_COLHER = r'''
import importlib.util, json, sys
raiz, saida, fixture = sys.argv[1:4]
sys.path.insert(0, raiz); sys.path.insert(0, raiz + "/tests")
espec = importlib.util.spec_from_file_location("termos", fixture)
T = importlib.util.module_from_spec(espec); espec.loader.exec_module(T)
T._varre = lambda casos: (lambda: [T._tenta(c) for c in casos()])
f = T.chamadas()
json.dump({k: json.loads(json.dumps(f[k](), ensure_ascii=False, sort_keys=True,
                                    default=repr))
           for k in %r}, open(saida, "w"), ensure_ascii=False)
''' % (VARREDURAS,)

_FEMININO = (("Não era eleitor.", "Não era eleitora."),
             ("Era eleitor.", "Era eleitora."),
             ("Filho de ", "Filha de "), ("Sepultado em ", "Sepultada em "))


def colher(raiz: Path) -> dict:
    """As saídas caso a caso das três varreduras, naquela árvore."""
    with tempfile.TemporaryDirectory() as tmp:
        saida = Path(tmp) / "casos.json"
        subprocess.run([sys.executable, "-B", "-c", _COLHER, str(raiz), str(saida),
                        str(PASTA / "ouro_lf06c_termos.py")], check=True, cwd=tmp)
        return json.loads(saida.read_text(encoding="utf-8"))


def _nascimento(a, d, conta):
    valores, texto = json.loads(json.dumps(a[1]))
    nati = d[1][0].get("frase_natimorto")
    assert nati in ("", " morta"), nati
    valores.update(frase_natimorto=nati, testemunhas="")
    if nati:
        conta["nascimento: «nasceu morta» (natimorto)"] += 1
        assert texto.count("nasceu uma criança") == 1
        texto = texto.replace("nasceu uma criança", "nasceu morta uma criança")
    return ["ok", [valores, texto]]


def _casamento(a, d, conta):
    valores, texto = json.loads(json.dumps(a[1]))
    valores["frase_da_celebracao"] = ""
    nova = d[1][0]["frase_habilitacao"]
    if valores["frase_habilitacao"] != nova:
        assert valores["frase_habilitacao"] == "." and re.fullmatch(
            r"\. Os proclamas foram publicados nesta serventia em [0-9/]+\.", nova)
        conta["casamento: os proclamas desta casa"] += 1
        assert texto.count(". E, não havendo impedimento") == 1
        texto = texto.replace(". E, não havendo impedimento",
                              f". {nova[2:]} E, não havendo impedimento")
        valores["frase_habilitacao"] = nova
    return ["ok", [valores, texto]]


def _obito(a, d, conta):
    valores, texto = json.loads(json.dumps(a[1]))
    for chave, valor in list(valores.items()):
        if isinstance(valor, str):
            for velho, novo in _FEMININO:
                valor = valor.replace(velho, novo)
            valores[chave] = valor
    qualificacao = valores["falecido_qualificacao"]
    valores["falecido_qualificacao"] = qualificacao + ", do sexo feminino"
    for velho, novo in _FEMININO:
        texto = texto.replace(velho, novo)
    assert texto.count(qualificacao + ".") == 1
    texto = texto.replace(qualificacao + ".", qualificacao + ", do sexo feminino.")
    conta["óbito: no feminino, com o sexo"] += 1
    return ["ok", [valores, texto]]


REGRAS = {"varre.nascimento": _nascimento, "varre.casamento": _casamento,
          "varre.obito": _obito}


def provar(raiz_de_antes: Path) -> int:
    antes, agora = colher(raiz_de_antes), colher(RAIZ)
    conta: collections.Counter = collections.Counter()
    fora = 0
    for nome, regra in REGRAS.items():
        for a, d in zip(antes[nome], agora[nome], strict=True):
            if (regra(a, d, conta) if a[0] == "ok" else a) != d:
                fora += 1
        print(f"{nome}: {len(antes[nome])} casos")
    for o_que, quantos in sorted(conta.items()):
        print(f"   {quantos:5d}  {o_que}")
    print(f"{fora} caso(s) que as regras não explicam")
    return 1 if fora else 0


if __name__ == "__main__":
    raise SystemExit(provar(Path(sys.argv[1]).resolve()))
