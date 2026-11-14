"""O CONHECIMENTO DO SUPERUSUÁRIO — a memória e o diário, um só para todas as
portas (Telegram, tela do sistema, app do Claude).

POR QUE EXISTE — 12/11/2026, pedido do oficial: «tudo com conhecimento que se
acumule e nada fique avulso, [que ele] saiba tudo que já foi feito de
importante». O operador nasce a cada pedido e morre no fim; sem isto, cada
conversa começaria do zero e cada porta teria a sua história.

    <dados>/operador/conhecimento/
        MEMORIA.md               o que vale daqui para a frente: como a casa
                                 está montada, o que o oficial prefere, a
                                 armadilha que já custou caro. Curta, e
                                 carregada inteira no começo de cada conversa.
        diario/AAAA-MM.jsonl     uma linha por pedido atendido, venha de onde
                                 vier: o pedido, a resposta, o relatório, o
                                 custo. Quem escreve é o programa, não o
                                 modelo — por isso nada fica de fora.
        comandos/AAAA-MM.jsonl   os comandos de shell de cada pedido. Nunca
                                 saem do servidor.
        de_outros/<servidor>/    a memória e o diário do outro servidor,
                                 trazidos pelo repositório privado.

O QUE ENTRA NA CONVERSA SOZINHO (`contexto`): a situação do servidor, a
memória, os últimos pedidos e o que está pendente. O resto se procura:
`python operador/conhecimento.py procurar <termo>`.

O QUE SAI DO SERVIDOR (`exportar_para`): a memória e o diário MASCARADOS
(`ajuda_privacidade`), para o repositório privado, de onde o outro servidor os
traz. O trecho que a máscara recusar fica no servidor, com a marca de que ficou.

Só a biblioteca padrão.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import intervencao as INT  # noqa: E402

#: Quanto da memória entra no começo de cada conversa (caracteres).
LIMITE_DA_MEMORIA = 12000
LIMITE_DA_MEMORIA_ALHEIA = 4000
#: Quantos pedidos recentes entram no começo de cada conversa.
ENTRADAS_NO_CONTEXTO = 12
#: Quanto de cada resposta o diário guarda.
LIMITE_DA_RESPOSTA = 12000
FICOU = "[ficou no servidor: a máscara de dados pessoais recusou este trecho]"


def pasta() -> Path:
    alvo = INT.base() / "conhecimento"
    alvo.mkdir(parents=True, exist_ok=True)
    return alvo


# ---------------------------------------------------------------- a memória

def arquivo_da_memoria() -> Path:
    return pasta() / "MEMORIA.md"


def _cabecalho() -> str:
    return (f"# Memória do superusuário — servidor {INT.servidor()}\n\n"
            "O que vale daqui para a frente, uma linha por fato. Entra inteira "
            "no começo de cada conversa: mantenha curta, apague o que venceu.\n\n")


def ler_memoria() -> str:
    try:
        return arquivo_da_memoria().read_text(encoding="utf-8")
    except OSError:
        return ""


def lembrar(texto: str) -> str:
    """Acrescenta um fato à memória. Devolve a linha escrita, ou "" se o fato
    já estava lá."""
    texto = " ".join(str(texto or "").split())
    if not texto:
        raise ValueError("Diga o que é para lembrar.")
    atual = ler_memoria() or _cabecalho()
    if texto in atual:
        return ""
    linha = f"- {INT._agora()[:10]} — {texto}"
    arquivo_da_memoria().write_text(atual.rstrip("\n") + "\n" + linha + "\n",
                                    encoding="utf-8", newline="\n")
    return linha


# ------------------------------------------------------------------ o diário

def _acrescentar(arquivo: Path, dados: dict) -> None:
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    with arquivo.open("a", encoding="utf-8", newline="\n") as saida:
        saida.write(json.dumps(dados, ensure_ascii=False) + "\n")


def _ler_jsonl(arquivo: Path) -> list[dict]:
    lidas = []
    try:
        linhas = arquivo.read_text(encoding="utf-8").splitlines()
    except OSError:
        return lidas
    for linha in linhas:
        try:
            dados = json.loads(linha)
        except ValueError:
            continue
        if isinstance(dados, dict):
            lidas.append(dados)
    return lidas


def anotar(porta: str, pedido: str, resposta: str, *, relatorio: dict | None = None,
           comandos: int = 0, custo: float | None = None, sessao: str = "",
           arquivos: list[str] | None = None, numero: str = "",
           quando: str | None = None) -> dict:
    """Uma linha no diário: um pedido atendido, por qualquer porta."""
    entrada = {
        "quando": quando or INT._agora(), "servidor": INT.servidor(),
        "porta": str(porta or "app"), "numero": str(numero or ""),
        "pedido": str(pedido or "").strip()[:4000],
        "resposta": str(resposta or "").strip()[:LIMITE_DA_RESPOSTA],
        "relatorio": relatorio or None, "comandos": int(comandos or 0),
        "custo_usd": custo, "sessao": str(sessao or ""),
        "arquivos": list(arquivos or []),
    }
    _acrescentar(pasta() / "diario" / f"{entrada['quando'][:7]}.jsonl", entrada)
    return entrada


def guardar_comandos(pedido: str, lista: list[dict]) -> None:
    """Os comandos de shell de um pedido, no registro do mês. Só neste servidor."""
    if lista:
        agora = INT._agora()
        _acrescentar(pasta() / "comandos" / f"{agora[:7]}.jsonl",
                     {"quando": agora, "pedido": str(pedido or "")[:300], "comandos": lista})


def entradas(limite: int | None = None, *, de: Path | None = None) -> list[dict]:
    """Os pedidos do diário, do mais antigo ao mais novo. Com `limite`, só os
    últimos. `de` é a pasta `diario` de outro servidor."""
    lidas: list[dict] = []
    for arquivo in sorted((de or pasta() / "diario").glob("*.jsonl"), reverse=True):
        lidas = _ler_jsonl(arquivo) + lidas
        if limite and len(lidas) >= limite:
            break
    return lidas[-limite:] if limite else lidas


def outros() -> list[str]:
    """Os outros servidores cujo conhecimento já chegou aqui."""
    raiz = pasta() / "de_outros"
    return sorted(p.name for p in raiz.iterdir() if p.is_dir()) if raiz.is_dir() else []


def _uma_linha(entrada: dict, tamanho: int = 240) -> str:
    pedido = " ".join(str(entrada.get("pedido") or "").split())[:160]
    resposta = " ".join(str(entrada.get("resposta") or "").split())[:tamanho]
    relatorio = entrada.get("relatorio") or {}
    rabo = f" [relatório {relatorio.get('id')}]" if relatorio.get("id") else ""
    return (f"- {str(entrada.get('quando') or '')[:16].replace('T', ' ')} · "
            f"{entrada.get('servidor') or '?'}/{entrada.get('porta') or '?'} · "
            f"pedido: {pedido} → {resposta}{rabo}")


def procurar(termo: str, limite: int = 40) -> list[str]:
    """Onde o termo aparece: na memória e no diário, daqui e dos outros
    servidores. O mais novo primeiro."""
    alvo = str(termo or "").strip().lower()
    if not alvo:
        return []
    achados = []
    memorias = [("memória", ler_memoria())]
    diarios = [entradas()]
    for nome in outros():
        raiz = pasta() / "de_outros" / nome
        try:
            memorias.append((f"memória de {nome}", (raiz / "MEMORIA.md").read_text(encoding="utf-8")))
        except OSError:
            pass
        diarios.append(entradas(de=raiz / "diario"))
    for rotulo, texto in memorias:
        achados += [f"{rotulo}: {linha.strip()}" for linha in texto.splitlines()
                    if alvo in linha.lower()]
    for diario in diarios:
        for entrada in reversed(diario):
            if alvo in (str(entrada.get("pedido")) + " " + str(entrada.get("resposta"))).lower():
                achados.append(_uma_linha(entrada, 400))
    return achados[:limite]


# ---------------------------------------------------------------- o contexto

def _encurtada(texto: str, limite: int) -> str:
    """A memória comprida entra pelo começo e pelo fim: o começo é o que a
    casa é, o fim é o que se aprendeu por último."""
    if len(texto) <= limite:
        return texto
    return texto[:2000] + "\n[... o meio ficou de fora: a memória passou do tamanho ...]\n" \
        + texto[-(limite - 2000):]


def contexto() -> str:
    """O que o operador recebe sozinho no começo de cada conversa, por
    qualquer porta: onde está, o que sabe, o que foi feito por último e o que
    está pendente."""
    partes = [
        "# O que você já sabe — carregado sozinho no começo da conversa", "",
        f"Servidor: {INT.servidor().upper()} — {INT.situacao()}. "
        f"Agora: {INT._agora()[:16].replace('T', ' ')}.", "",
        "## Memória", "",
        _encurtada(ler_memoria().strip(), LIMITE_DA_MEMORIA)
        or "(vazia ainda — o que valer daqui para a frente, guarde com `lembrar`)", "",
    ]
    for nome in outros():
        raiz = pasta() / "de_outros" / nome
        try:
            alheia = (raiz / "MEMORIA.md").read_text(encoding="utf-8").strip()
        except OSError:
            alheia = ""
        if alheia:
            partes += [f"## Memória do servidor {nome}", "",
                       _encurtada(alheia, LIMITE_DA_MEMORIA_ALHEIA), ""]
    ultimas = entradas(ENTRADAS_NO_CONTEXTO)
    if ultimas:
        partes += ["## Os últimos pedidos deste servidor, de todas as portas", ""]
        partes += [_uma_linha(e) for e in ultimas] + [""]
    for nome in outros():
        alheias = entradas(5, de=pasta() / "de_outros" / nome / "diario")
        if alheias:
            partes += [f"## Os últimos pedidos do servidor {nome}", ""]
            partes += [_uma_linha(e) for e in alheias] + [""]
    pendentes = [d["id"] for d in INT.listar()
                 if d.get("fechada_em") and not d.get("exportada_em")]
    aberta = INT.atual()
    if pendentes or aberta:
        partes += ["## Pendências", ""]
        if pendentes:
            partes.append("- Relatórios por exportar: " + ", ".join(pendentes[-20:]))
        if aberta:
            partes.append(f"- Intervenção aberta: {aberta.name}")
        partes.append("")
    partes.append("O que for mais antigo se acha com `procurar <termo>` (memória "
                  "e diário, deste servidor e do outro).")
    return "\n".join(partes)


# ---------------------------------------------------------------- a exportação

def _mascarado(texto: str, mascarar) -> str:
    try:
        return mascarar(texto)
    except Exception:  # noqa: BLE001 — a máscara recusou: o trecho não sai
        return FICOU


def exportar_para(repositorio: Any, mascarar) -> list[str]:
    """Leva a memória e o diário (os dois últimos meses) para
    `<repositório>/conhecimento/<servidor>/`, MASCARADOS, linha a linha — a
    linha que a máscara recusar sai trocada pela marca de que ficou."""
    alvo = Path(repositorio) / "conhecimento" / INT.servidor()
    (alvo / "diario").mkdir(parents=True, exist_ok=True)
    feitos = []
    memoria = ler_memoria()
    if memoria:
        linhas = [_mascarado(linha, mascarar) if linha.strip() else linha
                  for linha in memoria.splitlines()]
        (alvo / "MEMORIA.md").write_text("\n".join(linhas) + "\n", encoding="utf-8",
                                         newline="\n")
        feitos.append("MEMORIA.md")
    for arquivo in sorted((pasta() / "diario").glob("*.jsonl"))[-2:]:
        linhas = []
        for entrada in _ler_jsonl(arquivo):
            copia = {k: v for k, v in entrada.items() if k != "sessao"}
            for campo in ("pedido", "resposta"):
                if copia.get(campo):
                    copia[campo] = _mascarado(str(copia[campo]), mascarar)
            linhas.append(json.dumps(copia, ensure_ascii=False))
        (alvo / "diario" / arquivo.name).write_text("\n".join(linhas) + "\n",
                                                    encoding="utf-8", newline="\n")
        feitos.append(f"diario/{arquivo.name}")
    return feitos


def trazer_de(repositorio: Any) -> list[str]:
    """Traz o conhecimento dos OUTROS servidores, do repositório privado para
    `de_outros/`. Devolve de quem trouxe."""
    origem = Path(repositorio) / "conhecimento"
    trazidos = []
    if not origem.is_dir():
        return trazidos
    for raiz in sorted(origem.iterdir()):
        if raiz.is_dir() and raiz.name != INT.servidor():
            shutil.copytree(raiz, pasta() / "de_outros" / raiz.name, dirs_exist_ok=True)
            trazidos.append(raiz.name)
    return trazidos


# ------------------------------------------------------------- linha de comando

def main(argv: list[str] | None = None) -> int:
    for saida in (sys.stdout, sys.stderr):
        try:
            saida.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass
    ap = argparse.ArgumentParser(prog="operador/conhecimento.py",
                                 description="A memória e o diário do superusuário.")
    sub = ap.add_subparsers(dest="comando", required=True)
    sub.add_parser("lembrar").add_argument("texto")
    sub.add_parser("procurar").add_argument("termo")
    sub.add_parser("diario").add_argument("quantos", nargs="?", type=int, default=15)
    sub.add_parser("memoria")
    sub.add_parser("contexto")
    a = ap.parse_args(argv)
    INT.carregar_ambiente()
    if a.comando == "lembrar":
        try:
            print(lembrar(a.texto) or "Já estava na memória.")
        except ValueError as falha:
            print(f"RECUSADO: {falha}", file=sys.stderr)
            return 2
    elif a.comando == "procurar":
        print("\n".join(procurar(a.termo)) or "Nada com esse termo, nem na memória nem no diário.")
    elif a.comando == "diario":
        print("\n".join(_uma_linha(e, 400) for e in entradas(a.quantos)) or "O diário está vazio.")
    elif a.comando == "memoria":
        print(ler_memoria() or "(vazia)")
    elif a.comando == "contexto":
        print(contexto())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
