"""O OURO DO LF06C — o que os papéis do Registro Civil eram ANTES de o texto sair do código.

Um arquivo por grupo de módulos (`ouro_lf06c_<grupo>.py`, com as chamadas) e
o ouro gravado ao lado (`LF06C_<grupo>.json`). Cada grupo foi gravado na árvore
do commit 2c41e90, ANTES de qualquer linha do LF06C naquele grupo — exportada
intocada com `git archive` —, pelo `gerar()` abaixo. Sem dado real de pessoa:
os nomes são «DE EXEMPLO» e o CPF é o de teste.

    funcoes[nome]   o que o montador devolvia com aquele contexto de teste
    textos[nome]    as constantes de texto que viraram peça (o valor de antes)

**NÃO SE REGERA.** Depois do LF06C o texto mora em `modelos_padrao/rcpn/`, e
`gerar()` leria a pasta: o teste passaria a comparar a pasta com ela mesma. O
gerador recusa a árvore que já tem `rc_textos.py` (o módulo nasceu no LF06C).
Para conferir o gerador, exporte o commit 2c41e90 (`git archive 2c41e90`).

`chamadas()` de cada grupo é a mesma lista que o gerador usou; o teste a refaz
depois da mudança e compara saída por saída.

Na linha de comando (o Python sem `CG_PG_DSN`, e então os padrões saem da
pasta — os mesmos bytes da base):

    python -B ouro_lf06c.py gerar <grupo> <raiz-de-antes>
    python -B ouro_lf06c.py conferir <grupo> <raiz>
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

PASTA = Path(__file__).resolve().parent
COMMIT_DE_ANTES = "2c41e90"
GRUPOS = ("termos", "certidoes", "anotacao_crc", "averbacao", "comunicacoes",
          "habilitacao")

# Os papéis que o LF06C pôs no catálogo. O ouro do LF06A cobre os 41 de
# antes; estes doze não tinham constante — o texto era montado no código — e
# o que prova que nada mudou neles é o `funcoes` dos grupos acima.
PAPEIS_NOVOS = (
    "RC_QUALIFICACAO", "RC_CERTIDAO_RESUMO", "RC_CERTIDAO_INTEIRO_TEOR",
    "RC_ANOTACAO_CRC_COMPACTA", "RC_ANOTACAO_CRC_COMPLETA",
    "RC_ANOTACAO_CRC_FE_PUBLICA", "RC_AVERBACAO_RETIFICACAO",
    "RC_COMUNICACAO_OBITOS", "RC_OFICIO_FUNAI", "RC_EDITAL_PROCLAMAS",
    "RC_EDITAL_PROCLAMAS_FOLHA", "RC_CERTIDAO_HABILITACAO",
)


def normal(valor):
    """A forma com que o valor foi gravado (tupla vira lista, chave ordenada)."""
    return json.loads(json.dumps(valor, ensure_ascii=False, sort_keys=True,
                                 default=repr))


def tenta(f):
    try:
        return {"ok": f()}
    except Exception as erro:  # noqa: BLE001 — o erro também é saída
        return {"erro": f"{type(erro).__name__}: {erro}"}


def _grupo(grupo: str):
    if grupo not in GRUPOS:
        raise SystemExit(f"grupo desconhecido: {grupo} (são {', '.join(GRUPOS)})")
    espec = importlib.util.spec_from_file_location(
        f"ouro_lf06c_{grupo}", PASTA / f"ouro_lf06c_{grupo}.py")
    mod = importlib.util.module_from_spec(espec)
    espec.loader.exec_module(mod)
    return mod


def arquivo(grupo: str) -> Path:
    return PASTA / f"LF06C_{grupo}.json"


def chamadas(grupo: str) -> dict:
    return _grupo(grupo).chamadas()


def textos(grupo: str) -> dict:
    mod = _grupo(grupo)
    return mod.textos() if hasattr(mod, "textos") else {}


def saidas(grupo: str) -> dict:
    return {nome: normal(tenta(f)) for nome, f in chamadas(grupo).items()}


def gerar(grupo: str, raiz: Path) -> None:
    """Grava o ouro do grupo. SÓ NA ÁRVORE DE ANTES — ver o cabeçalho."""
    raiz = Path(raiz).resolve()
    if (raiz / "rc_textos.py").exists():
        raise SystemExit(f"{raiz} já é a árvore do LF06C: o ouro se grava na de antes.")
    sys.path.insert(0, str(raiz))
    funcoes = saidas(grupo)
    arquivo(grupo).write_text(json.dumps(
        {"_como": ("Gerado ANTES do LF06C, na árvore do commit "
                   f"{COMMIT_DE_ANTES} exportada intocada, por "
                   f"tests/fixtures/modelos_ouro/ouro_lf06c.py gerar {grupo}. "
                   "Não regerar: depois da mudança o texto mora na pasta dos "
                   "padrões, e regerar faria o teste comparar a pasta com ela "
                   "mesma."),
         "commit": COMMIT_DE_ANTES, "grupo": grupo,
         "funcoes": funcoes, "textos": normal(textos(grupo))},
        ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def ouro(grupo: str) -> dict:
    return json.loads(arquivo(grupo).read_text(encoding="utf-8"))


def conferir(grupo: str, raiz: Path) -> list[str]:
    """Os nomes cuja saída mudou desde o ouro (lista vazia: nada mudou)."""
    sys.path.insert(0, str(Path(raiz).resolve()))
    antes = ouro(grupo)["funcoes"]
    depois = saidas(grupo)
    return sorted(n for n in set(antes) | set(depois)
                  if antes.get(n) != depois.get(n))


if __name__ == "__main__":
    acao, grupo, raiz = sys.argv[1:4]
    if acao == "gerar":
        gerar(grupo, Path(raiz))
        print(f"{grupo}: {len(ouro(grupo)['funcoes'])} saídas gravadas")
    elif acao == "conferir":
        mudaram = conferir(grupo, Path(raiz))
        print(f"{grupo}: {len(mudaram)} saída(s) diferente(s) do ouro")
        for nome in mudaram:
            print("  ", nome)
        raise SystemExit(1 if mudaram else 0)
    else:
        raise SystemExit("uso: ouro_lf06c.py gerar|conferir <grupo> <raiz>")
