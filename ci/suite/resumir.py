"""O comentário que o PR recebe quando a suíte falha (10/11/2026).

    python3 ci/suite/resumir.py <pasta de saída da suíte>   → Markdown na saída padrão

AGRUPA AS FALHAS PELA CAUSA, sem IA. Em 10/11/2026, 294 testes caíram de uma vez
por um motivo só (a semente do layout); uma lista de 294 linhas esconde isso, e
um resumo de modelo de linguagem só reescrevia o que o pytest já dizia, com o
risco de errar com convicção. Aqui a conta é exata: as falhas se juntam pela
mensagem de erro, normalizada, e cada grupo mostra quantos testes e quais.

A fonte é o `junit.xml` do pytest, onde a mensagem vem inteira (o resumo curto do
terminal a corta em 80 colunas). Ele vem do código do PR — é DADO NÃO CONFIÁVEL:
recusa-se XML com DOCTYPE/ENTITY e arquivo grande demais, e tudo o que vai para o
comentário passa por `sem_crases`, dentro de bloco de código.

Só a biblioteca padrão: roda no executor, fora do contêiner, com o Python do Mac.
"""
from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from collections import OrderedDict
from pathlib import Path

LIMITE_DO_JUNIT = 30 * 1024 * 1024
GRUPOS_NO_COMENTARIO = 10
EXEMPLOS_POR_GRUPO = 3
LINHAS_DO_PRIMEIRO_ERRO = 30


def sem_crases(texto: str) -> str:
    """O texto vai dentro de bloco de código: crase tripla dele não pode fechá-lo."""
    return str(texto).replace("```", "ˋˋˋ")


def assinatura(mensagem: str) -> str:
    """A causa de uma falha, sem o que muda de teste para teste. Só calcula.

    Primeira linha da mensagem; números, ids hexadecimais e caminhos temporários
    viram marcadores — «assert 1050 == 1000» e «assert 7 == 5» são a mesma causa
    só se o resto da frase for igual.
    """
    linha = (mensagem or "").strip().splitlines()[0] if (mensagem or "").strip() else "(sem mensagem)"
    linha = re.sub(r"/(?:private/)?(?:var|tmp)/\S+", "<tmp>", linha)
    linha = re.sub(r"\b0x[0-9a-fA-F]+\b", "<hex>", linha)
    linha = re.sub(r"\b[0-9a-f]{12,}\b", "<hex>", linha)
    linha = re.sub(r"\d+", "<n>", linha)
    return linha[:300]


def falhas_do_junit(caminho: Path) -> list[tuple[str, str, str]]:
    """[(tipo, teste, mensagem)] do junit.xml. Lista vazia se não houver arquivo legível."""
    if not caminho.exists() or caminho.stat().st_size > LIMITE_DO_JUNIT:
        return []
    bruto = caminho.read_bytes()
    if b"<!DOCTYPE" in bruto or b"<!ENTITY" in bruto:
        return []
    try:
        raiz = ET.fromstring(bruto)
    except ET.ParseError:
        return []
    falhas = []
    for caso in raiz.iter("testcase"):
        for marca, tipo in (("failure", "FALHOU"), ("error", "ERRO")):
            for item in caso.findall(marca):
                teste = f"{caso.get('classname', '')}::{caso.get('name', '')}"
                falhas.append((tipo, teste, item.get("message") or (item.text or "")))
    return falhas


def grupos(falhas: list[tuple[str, str, str]]) -> list[tuple[str, int, list[str]]]:
    """[(causa, quantos, testes)] do maior grupo para o menor. Só calcula."""
    por_causa: "OrderedDict[str, list[str]]" = OrderedDict()
    for tipo, teste, mensagem in falhas:
        por_causa.setdefault(f"{tipo}: {assinatura(mensagem)}", []).append(teste)
    return sorted(((c, len(t), t) for c, t in por_causa.items()), key=lambda g: -g[1])


def primeiro_erro(log: str) -> list[str]:
    """As linhas `E   …` do primeiro bloco de erro do relatório do pytest."""
    linhas, dentro = [], False
    for linha in log.splitlines():
        if linha.startswith("E   "):
            linhas.append(linha.rstrip())
            dentro = True
        elif dentro:
            break
    return linhas[:LINHAS_DO_PRIMEIRO_ERRO]


def comentario(pasta: Path) -> str:
    situacao = (pasta / "situacao.txt").read_text(encoding="utf-8", errors="replace").strip() \
        if (pasta / "situacao.txt").exists() else "sem situação"
    log = (pasta / "suite.log").read_text(encoding="utf-8", errors="replace") \
        if (pasta / "suite.log").exists() else ""
    falhas = falhas_do_junit(pasta / "junit.xml")
    partes = ["### A suíte falhou", "", f"`{sem_crases(situacao)[:300]}`", ""]
    if falhas:
        lista = grupos(falhas)
        partes.append(f"**{len(falhas)} teste(s) caíram, por {len(lista)} causa(s) distinta(s):**")
        partes.append("")
        for causa, quantos, testes in lista[:GRUPOS_NO_COMENTARIO]:
            exemplos = ", ".join(f"`{sem_crases(t)[:150]}`" for t in testes[:EXEMPLOS_POR_GRUPO])
            mais = f" e mais {quantos - EXEMPLOS_POR_GRUPO}" if quantos > EXEMPLOS_POR_GRUPO else ""
            partes += [f"- **{quantos}×** `{sem_crases(causa)}`", f"  - {exemplos}{mais}"]
        if len(lista) > GRUPOS_NO_COMENTARIO:
            partes.append(f"- … e mais {len(lista) - GRUPOS_NO_COMENTARIO} causa(s) no relatório do executor.")
        partes.append("")
    erro = primeiro_erro(log)
    if erro:
        partes += ["**O primeiro erro, como o pytest o mostrou:**", "", "```",
                   *[sem_crases(l)[:300] for l in erro], "```", ""]
    if not falhas and not erro:
        partes += ["O relatório não traz teste falho: a falha foi da infraestrutura da suíte.", ""]
    partes.append("<sub>Este PR fica fora da fila de merge até a suíte passar.</sub>")
    return "\n".join(partes)


if __name__ == "__main__":
    print(comentario(Path(sys.argv[1])))
