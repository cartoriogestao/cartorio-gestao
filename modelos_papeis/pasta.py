"""A pasta dos padrões — o texto de fábrica de cada papel, FORA do código.

    «Não deveríamos ter modelos no código; deveriam estar no banco, para editar
     com mais facilidade.» — o oficial, 19/10/2026 (LF06A).

UM ARQUIVO POR PAPEL, E TEXTO, E NÃO BANCO BINÁRIO
    `modelos_padrao/<pasta>/<CHAVE>.txt` é o corpo **exatamente** como ele saía
    da constante do módulo — os mesmos bytes, conferidos pelo teste-ouro —, e
    `<CHAVE>.json` é a ficha dele (chave, atribuição, nome, formato, o que é e
    os claros que o padrão usa). Texto, porque o git mostra a diferença de cada
    vírgula: quem mudar o padrão numa versão nova deixa o rastro à vista.

    O `.odt` de um papel que for formulário vai como está (`<CHAVE>.odt`), e o
    corpo dele vira base64 — a base é de texto.

A PEÇA (`<CHAVE>__<peca>.txt`)
    A REGRA que decide se uma frase entra (edital × pessoal, plural, gêmeos) é
    do código; o TEXTO da frase pode morar aqui, como peça do papel. Sem `.json`
    próprio ela herda a ficha do papel.

QUEM LÊ ESTA PASTA
    · `modelos_papeis` (o catálogo), para a ficha de cada papel da tela;
    · `modelos_da_casa.carregar_base`, que a copia para a base auxiliar do
      PostgreSQL (schema `modelos_padrao`) e é de lá que os papéis leem.

    Esta leitura **não toca banco**: ela só lê arquivo e calcula.
"""
from __future__ import annotations

import base64
import hashlib
import json
import string
from pathlib import Path
from typing import Any

PASTA_DOS_PADROES = Path(__file__).resolve().parent.parent / "modelos_padrao"

JINJA = "JINJA"
CHAVES = "CHAVES"
ODT = "ODT"
FORMATOS = (JINJA, CHAVES, ODT)

# O separador da peça. Dois sublinhados porque um só já aparece dentro das
# chaves (`RI_CERTIDAO_ONUS`), e a peça tem de se separar sem adivinhação.
SEPARADOR_DE_PECA = "__"

# A FORMA DA PASTA ENTRA NA MARCA: mudou a maneira de ler (um campo novo na
# base, outra regra de peça), a base se recarrega mesmo sem arquivo novo.
VERSAO_DA_LEITURA = "1"

_CACHE: dict[str, dict] = {}


def impressao_digital(dados: bytes) -> str:
    """O sha256 do corpo. É ela que diz «o padrão mudou» — o texto não precisa
    ser comparado letra a letra para isso."""
    return hashlib.sha256(dados).hexdigest()


def chave_normal(chave: Any) -> str:
    """`ri_certidao__Edital` → `RI_CERTIDAO__edital`. O papel em maiúsculas,
    como o catálogo; a peça em minúsculas, como o nome do arquivo."""
    papel, sep, peca = str(chave or "").strip().partition(SEPARADOR_DE_PECA)
    return papel.upper() + (sep + peca.lower() if sep else "")


def _texto(caminho: Path) -> str:
    """O corpo do `.txt`, com `\\r\\n` desfeito.

    **O TEXTO DE FÁBRICA NUNCA TEVE `\\r`**: o Python desfazia as quebras do
    código-fonte (que é CRLF em boa parte da casa) ao ler a constante. Um git
    com `autocrlf` no Windows poria `\\r\\n` na cópia da pasta — o
    `.gitattributes` já impede, e esta linha é a segunda trava: sem ela o termo
    sairia com um `\\r` em cada linha e a impressão digital mudaria sozinha.
    """
    return caminho.read_bytes().decode("utf-8").replace("\r\n", "\n")


def _campos(corpo: str, formato: str) -> list[str]:
    """Os claros que o padrão USA — medidos no texto, e não declarados à mão."""
    if formato == CHAVES:
        vistos: list[str] = []
        try:
            for _, campo, _, _ in string.Formatter().parse(corpo):
                if campo and campo not in vistos:
                    vistos.append(campo)
        except ValueError:
            pass
        return vistos
    if formato == JINJA:
        import re

        from jinja2 import Environment, TemplateSyntaxError, meta
        try:
            nomes = meta.find_undeclared_variables(Environment().parse(corpo))
        except TemplateSyntaxError:
            return []
        # `{% set x = ... %}` dentro de um `{% if %}` o Jinja ainda conta como
        # claro; não é: é conta do próprio modelo.
        locais = set(re.findall(r"{%-?\s*set\s+([A-Za-z_]\w*)", corpo))
        return sorted(nomes - locais)
    return []


def _ficha(caminho: Path) -> dict:
    return json.loads(caminho.read_bytes().decode("utf-8"))


def ler_pasta(pasta: Path | None = None) -> dict:
    """A pasta inteira, lida e conferida. Só lê arquivo e calcula.

    Devolve ``{"padroes": {chave: {...}}, "problemas": [...], "marca": str}``.
    Cada padrão traz `chave`, `atribuicao`, `nome`, `formato`, `explica`,
    `campos`, `corpo`, `impressao_digital`, `arquivo` (relativo à raiz do
    programa), `pasta` e `peca_de`.

    **ARQUIVO TORTO NÃO DERRUBA A CASA**: vira linha em `problemas`, e o papel
    dele fica de fora — quem o pedir recebe «padrão X não carregado». Um `.json`
    quebrado não pode impedir os outros quarenta papéis de sair.
    """
    raiz = Path(pasta or PASTA_DOS_PADROES).resolve()
    chave_cache = str(raiz)
    if chave_cache in _CACHE:
        return _CACHE[chave_cache]

    padroes: dict[str, dict] = {}
    problemas: list[str] = []
    marca = hashlib.sha256(f"leitura:{VERSAO_DA_LEITURA}\n".encode())
    # SÓ O QUE ESTA LEITURA USA entra na marca: um `.DS_Store` do Finder ou o
    # `Thumbs.db` do Windows recarregaria a base à toa a cada subida.
    arquivos = sorted(
        p for p in raiz.rglob("*")
        if p.is_file() and p.suffix in (".txt", ".json", ".odt")
        and not p.name.startswith(".")) if raiz.is_dir() else []
    if not arquivos:
        problemas.append(f"A pasta dos padrões não existe ou está vazia: {raiz}")
    for arq in arquivos:
        rel = arq.relative_to(raiz).as_posix()
        dados = arq.read_bytes()
        if arq.suffix == ".txt":
            dados = dados.replace(b"\r\n", b"\n")
        marca.update(f"{rel}|{impressao_digital(dados)}\n".encode())

    fichas = {p.stem: p for p in arquivos if p.suffix == ".json"}
    for arq in arquivos:
        if arq.suffix not in (".txt", ".odt"):
            continue
        rel = (Path(raiz.name) / arq.relative_to(raiz)).as_posix()
        chave = chave_normal(arq.stem)
        papel, sep, _ = chave.partition(SEPARADOR_DE_PECA)
        try:
            if arq.stem in fichas:
                ficha = _ficha(fichas[arq.stem])
            elif sep and papel in fichas:
                pai = _ficha(fichas[papel])
                pai.pop("campos", None)          # os claros da peça são os dela
                ficha = {**pai, "chave": chave,
                         "nome": f"{pai.get('nome', papel)} — peça «{chave.split(SEPARADOR_DE_PECA, 1)[1]}»",
                         "explica": ""}
            else:
                problemas.append(f"{rel}: falta a ficha {arq.stem}.json")
                continue
        except (ValueError, OSError) as erro:
            problemas.append(f"{rel}: ficha ilegível ({erro})")
            continue
        if chave_normal(ficha.get("chave")) != chave:
            problemas.append(f"{rel}: a ficha diz chave «{ficha.get('chave')}», e o "
                             f"arquivo se chama {arq.stem}")
            continue
        formato = str(ficha.get("formato") or JINJA).upper()
        if formato not in FORMATOS:
            problemas.append(f"{rel}: formato «{formato}» não existe ({', '.join(FORMATOS)})")
            continue
        if (arq.suffix == ".odt") != (formato == ODT):
            problemas.append(f"{rel}: formato {formato} com arquivo {arq.suffix}")
            continue
        if arq.suffix == ".odt":
            bruto = arq.read_bytes()
            corpo = base64.b64encode(bruto).decode("ascii")
            digital = impressao_digital(bruto)
        else:
            # UTF-8 TORTO TAMBÉM É ARQUIVO TORTO (LF06B, 19/10/2026): sem esta
            # guarda, um `.txt` salvo em Latin-1 por um editor derrubava a
            # leitura da pasta inteira — e com ela todos os papéis da casa.
            try:
                corpo = _texto(arq)
            except UnicodeDecodeError as erro:
                problemas.append(f"{rel}: não é UTF-8 ({erro.reason}, byte {erro.start})")
                continue
            digital = impressao_digital(corpo.encode("utf-8"))
        if not corpo.strip():
            problemas.append(f"{rel}: corpo vazio — folha em branco não é padrão")
            continue
        campos = ficha.get("campos")
        padroes[chave] = {
            "chave": chave,
            "atribuicao": str(ficha.get("atribuicao") or ""),
            "nome": str(ficha.get("nome") or chave),
            "formato": formato,
            "explica": str(ficha.get("explica") or ""),
            "campos": list(campos) if isinstance(campos, list) else _campos(corpo, formato),
            "corpo": corpo,
            "impressao_digital": digital,
            "arquivo": rel,
            "pasta": arq.parent.name,
            "peca_de": papel if sep else None,
        }

    lida = {"padroes": padroes, "problemas": problemas, "marca": marca.hexdigest()}
    _CACHE[chave_cache] = lida
    return lida


def esquecer() -> None:
    """Joga fora a leitura guardada — para quem acabou de mexer na pasta."""
    _CACHE.clear()


def completar(pasta: str, entrada: dict, atribuicao: str) -> dict:
    """A linha do catálogo: o que é do CÓDIGO (`entrada`) com a ficha da pasta.

    **A FICHA MORA NUM LUGAR SÓ.** Nome, formato e explicação estavam escritos
    aqui e passaram para o `.json` ao lado do texto — duas cópias divergiriam
    no primeiro conserto, e é a lição da `normalizar_nome`. O que fica no
    `modelos_papeis/<atribuição>.py` é o que só o código sabe: a ordem da tela,
    o nome antigo da constante (`padrao`), o marcador do miolo.

    Sem a ficha (pacote incompleto) o papel continua na lista, com a chave por
    nome — e a tela e a emissão dizem que o padrão não foi carregado.
    """
    lida = ler_pasta()
    p = lida["padroes"].get(entrada["chave"], {})
    linha = {"chave": entrada["chave"],
             "atribuicao": p.get("atribuicao") or atribuicao,
             "nome": p.get("nome") or entrada["chave"],
             "formato": p.get("formato") or JINJA,
             "explica": p.get("explica") or "",
             "campos": list(p.get("campos") or ()),
             "arquivo": p.get("arquivo") or
             f"{PASTA_DOS_PADROES.name}/{pasta}/{entrada['chave']}.txt",
             "pasta": pasta}
    return {**linha, **entrada}
