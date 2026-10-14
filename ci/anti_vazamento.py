"""Anti-vazamento: impede que dado real da serventia ou de pessoas entre no repositorio.

DUAS CAMADAS
    1. DETECTORES GENERICOS (valem para qualquer serventia, ficam no repo):
       - CPF e CNPJ com digito verificador VALIDO (formatados; sem mascara so
         quando ha a palavra cpf/cnpj por perto);
       - CNS em contexto (rotulo «CNS» seguido de 6 digitos, com ou sem
         espaco, dois-pontos ou hifen);
       - codigo de selo no formato TJMA (`selo.CODIGO_SELO`:
         5-7 letras + CNS de 6 digitos + 14-20 alfanumericos);
       - caminho de perfil de usuario Windows (`C:\\Users\\<nome>`);
       - arquivos proibidos por nome (*.cred, *.key, secret.key, *.sqlite3,
         *.db, *.pfx, *.p12, selos_reais.json, tmp_*, .env, denylist.local).
       Excecao: documentos FICTICIOS declarados em
       `tests/fixtures/anti_vazamento/documentos_ficticios.txt`.

    2. DENY-LIST NOMINAL DA CASA (nomes, cidade, CNS, CNPJ, IP, pasta do
       usuario): NUNCA no repositorio. Fica em `ci/denylist.local.txt`
       (gitignored), preenchida pela Auditoria no SERVIDOR. No GitHub Actions
       a mesma lista vira o secret `CG_DENYLIST_LOCAL`, cadastrado pelo oficial
       na publicacao; o workflow escreve o arquivo local a partir dele.
       O repositorio so traz `ci/denylist.example.txt`, com placeholders.

    Formato da deny-list: uma entrada por linha; `#` comenta; literal e
    comparado sem diferenciar maiusculas e sem acento; prefixo `re:` = regex.

SAIDA
    Nunca imprime o dado achado por inteiro: CPF sai mascarado, item da
    deny-list sai pelo NUMERO da linha da lista — o log da CI e publico.

USO
    python ci/anti_vazamento.py                 # varre a arvore (ou git ls-files se houver .git)
    python ci/anti_vazamento.py --modo arvore   # forca a arvore inteira
    python ci/anti_vazamento.py --raiz CAMINHO --denylist-local OUTRO.txt
"""
from __future__ import annotations

import argparse
import fnmatch
import os
import re
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

RAIZ_PADRAO = Path(__file__).resolve().parent.parent
DENYLIST_LOCAL = Path("ci") / "denylist.local.txt"
DENYLIST_EXEMPLO = Path("ci") / "denylist.example.txt"
FICTICIOS = Path("tests") / "fixtures" / "anti_vazamento" / "documentos_ficticios.txt"
ENV_DENYLIST = "CG_DENYLIST_LOCAL"

EXTENSOES_VARRIDAS = {
    ".py", ".js", ".html", ".htm", ".md", ".txt", ".json", ".toml", ".yml",
    ".yaml", ".ini", ".cfg", ".css", ".ps1", ".cmd", ".bat", ".xml", ".csv",
    ".sql", ".j2", ".jinja",
}
PASTAS_IGNORADAS = {
    ".git", "backups_patch", "venv", ".venv", "__pycache__", "node_modules",
    ".pytest_cache", ".ruff_cache", "tmp", "build", "dist", "runtime",
}
# Arquivos que POR DEFINICAO contem exemplos sinteticos de vazamento (para
# testar o proprio detector) ou a lista local. Relativos a raiz, com /.
CAMINHOS_IGNORADOS = (
    "tests/fixtures/anti_vazamento/*",
    "ci/denylist.local.txt",
    "ci/denylist.example.txt",
)
ARQUIVOS_PROIBIDOS = (
    "*.cred", "*.key", "secret.key", "secret_key", "*.secret", "*.pem",
    "*.pfx", "*.p12", "*.sqlite3", "*.sqlite", "*.db", "selos_reais.json",
    "selador_reais.json", "tmp_*", ".env", "denylist.local.txt",
)
ARQUIVOS_PERMITIDOS = (".env.example", "denylist.example.txt")

TAMANHO_MAXIMO = 2_000_000  # bytes; acima disso e dump, nao codigo


# ------------------------------------------------------------ DV

def so_digitos(texto: str) -> str:
    return "".join(c for c in str(texto or "") if c.isdigit())


def cpf_valido(numero: str) -> bool:
    n = so_digitos(numero)
    if len(n) != 11 or n == n[0] * 11:
        return False
    for corte in (9, 10):
        soma = sum(int(n[i]) * ((corte + 1) - i) for i in range(corte))
        if (soma * 10) % 11 % 10 != int(n[corte]):
            return False
    return True


def cnpj_valido(numero: str) -> bool:
    n = so_digitos(numero)
    if len(n) != 14 or n == n[0] * 14:
        return False
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6] + pesos1
    for pesos, corte in ((pesos1, 12), (pesos2, 13)):
        resto = sum(int(n[i]) * pesos[i] for i in range(corte)) % 11
        if (0 if resto < 2 else 11 - resto) != int(n[corte]):
            return False
    return True


def mascarar(numero: str) -> str:
    n = so_digitos(numero)
    if len(n) <= 4:
        return "*" * len(n)
    return n[:2] + "*" * (len(n) - 4) + n[-2:]


# ------------------------------------------------------------ listas

def normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in sem_acento if not unicodedata.combining(c)).casefold()


@dataclass(frozen=True)
class Entrada:
    numero: int          # linha na deny-list (e o que sai no log)
    regex: re.Pattern
    literal: bool        # True: compara no texto normalizado (sem acento/caixa)


def carregar_denylist(texto_ou_caminho) -> list[Entrada]:
    """Le a deny-list (caminho ou texto). Linha vazia e `#` sao ignoradas."""
    if isinstance(texto_ou_caminho, Path):
        if not texto_ou_caminho.is_file():
            return []
        texto = texto_ou_caminho.read_text(encoding="utf-8")
    else:
        texto = str(texto_ou_caminho or "")
    entradas: list[Entrada] = []
    for i, linha in enumerate(texto.splitlines(), start=1):
        bruto = linha.strip()
        if not bruto or bruto.startswith("#"):
            continue
        if bruto.startswith("re:"):
            entradas.append(Entrada(i, re.compile(bruto[3:].strip(), re.IGNORECASE), False))
        else:
            entradas.append(Entrada(i, re.compile(re.escape(normalizar(bruto))), True))
    return entradas


def carregar_ficticios(caminho: Path) -> set[str]:
    """Documentos FICTICIOS permitidos (so digitos). `#` comenta."""
    if not caminho.is_file():
        return set()
    out = set()
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        bruto = linha.split("#", 1)[0].strip()
        if bruto:
            out.add(so_digitos(bruto) or bruto.upper())
    return out


# ------------------------------------------------------------ detectores

RX_CPF_FORMATADO = re.compile(r"(?<![\d.])\d{3}\.\d{3}\.\d{3}-\d{2}(?![\d])")
RX_CNPJ_FORMATADO = re.compile(r"(?<![\d.])\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}(?![\d])")
RX_DOC_COM_ROTULO = re.compile(
    r"(?i)\b(cpf|cnpj)\b[^0-9\n]{0,20}?(?<!\d)(\d{11}|\d{14})(?!\d)")
RX_CNS_CONTEXTO = re.compile(r"(?i)\bcns[\s:=\-_\"'`#nº°.]{0,6}(\d{6})(?!\d)")
# Mesmo formato de `selo.CODIGO_SELO`, sem ancoras.
RX_SELO_TJMA = re.compile(r"(?<![A-Z0-9])([A-Z]{5,7})(\d{6})([A-Z0-9]{14,20})(?![A-Z0-9])")
RX_PERFIL_WINDOWS = re.compile(r"(?i)\b[A-Z]:[\\/]{1,2}Users[\\/]{1,2}([^\\/\s\"'<>]+)")
PERFIS_GENERICOS = {"public", "default", "usuario", "usuário", "<usuario>",
                    "fulano", "exemplo", "user", "%username%", "$env:username"}


@dataclass(frozen=True)
class Achado:
    arquivo: str
    linha: int
    tipo: str
    detalhe: str   # ja mascarado — seguro para log publico

    def __str__(self) -> str:
        return f"{self.arquivo}:{self.linha}: [{self.tipo}] {self.detalhe}"


def _linha_de(texto: str, pos: int) -> int:
    return texto.count("\n", 0, pos) + 1


def varrer_texto(texto: str, *, arquivo: str = "<texto>",
                 denylist: list[Entrada] | None = None,
                 ficticios: set[str] | None = None) -> list[Achado]:
    """Todos os achados num texto. Nao le disco."""
    ficticios = ficticios or set()
    achados: list[Achado] = []

    def doc(tipo: str, numero: str, pos: int) -> None:
        d = so_digitos(numero)
        if d in ficticios:
            return
        ok = cpf_valido(d) if len(d) == 11 else cnpj_valido(d)
        if ok:
            achados.append(Achado(arquivo, _linha_de(texto, pos), tipo,
                                  f"{tipo} com DV valido {mascarar(d)}"))

    for m in RX_CPF_FORMATADO.finditer(texto):
        doc("CPF", m.group(0), m.start())
    for m in RX_CNPJ_FORMATADO.finditer(texto):
        doc("CNPJ", m.group(0), m.start())
    for m in RX_DOC_COM_ROTULO.finditer(texto):
        numero = m.group(2)
        doc("CPF" if len(numero) == 11 else "CNPJ", numero, m.start(2))

    for m in RX_CNS_CONTEXTO.finditer(texto):
        cns = m.group(1)
        if cns not in ficticios and cns != "000000":
            achados.append(Achado(arquivo, _linha_de(texto, m.start()), "CNS",
                                  f"CNS em contexto {mascarar(cns)}"))
    for m in RX_SELO_TJMA.finditer(texto):
        prefixo, cns, ident = m.groups()
        if not (any(c.isdigit() for c in ident) and any(c.isalpha() for c in ident)):
            continue
        if cns in ficticios or cns == "000000" or m.group(0) in ficticios:
            continue
        achados.append(Achado(arquivo, _linha_de(texto, m.start()), "SELO",
                              f"codigo de selo TJMA {prefixo}{mascarar(cns)}…"))
    for m in RX_PERFIL_WINDOWS.finditer(texto):
        nome = m.group(1).strip().casefold()
        if nome in PERFIS_GENERICOS or nome.startswith(("<", "{", "%", "$")):
            continue
        achados.append(Achado(arquivo, _linha_de(texto, m.start()), "PERFIL_WINDOWS",
                              "caminho C:\\Users\\<perfil real>"))

    if denylist:
        # `normalizar` preserva as quebras de linha, entao a contagem de linha bate.
        norm = normalizar(texto)
        for e in denylist:
            alvo = norm if e.literal else texto
            for m in e.regex.finditer(alvo):
                achados.append(Achado(arquivo, _linha_de(alvo, m.start()), "DENYLIST",
                                      f"entrada #{e.numero} da deny-list local"))
    return achados


def arquivo_proibido(caminho_relativo: str) -> bool:
    nome = caminho_relativo.replace("\\", "/").rsplit("/", 1)[-1]
    if nome in ARQUIVOS_PERMITIDOS:
        return False
    return any(fnmatch.fnmatch(nome, padrao) for padrao in ARQUIVOS_PROIBIDOS)


# ------------------------------------------------------------ arvore

def _ignorado(rel: str) -> bool:
    return any(fnmatch.fnmatch(rel, p) for p in CAMINHOS_IGNORADOS)


def listar_arquivos(raiz: Path, modo: str = "auto") -> list[str]:
    """Caminhos relativos (com /). `git` usa `git ls-files` (respeita .gitignore)."""
    if modo in ("auto", "git") and (raiz / ".git").exists():
        saida = subprocess.run(["git", "ls-files", "-z"], cwd=raiz,
                               capture_output=True, check=True).stdout
        return [p for p in saida.decode("utf-8").split("\0") if p]
    if modo == "git":
        raise SystemExit("modo git pedido, mas nao ha .git em " + str(raiz))
    out = []
    for base, pastas, arquivos in os.walk(raiz):
        pastas[:] = [p for p in pastas if p not in PASTAS_IGNORADAS]
        for nome in arquivos:
            if ".bak" in nome:
                continue
            rel = os.path.relpath(os.path.join(base, nome), raiz).replace("\\", "/")
            out.append(rel)
    return out


def varrer_arvore(raiz: Path, *, modo: str = "auto",
                  denylist: list[Entrada] | None = None,
                  ficticios: set[str] | None = None) -> list[Achado]:
    raiz = Path(raiz)
    achados: list[Achado] = []
    for rel in listar_arquivos(raiz, modo):
        if _ignorado(rel):
            continue
        if arquivo_proibido(rel):
            achados.append(Achado(rel, 0, "ARQUIVO_PROIBIDO", "arquivo que nao pode ir para o repo"))
            continue
        if Path(rel).suffix.lower() not in EXTENSOES_VARRIDAS:
            continue
        caminho = raiz / rel
        try:
            if caminho.stat().st_size > TAMANHO_MAXIMO:
                achados.append(Achado(rel, 0, "ARQUIVO_GRANDE", "texto > 2 MB (dump?)"))
                continue
            texto = caminho.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        achados.extend(varrer_texto(texto, arquivo=rel, denylist=denylist, ficticios=ficticios))
    return achados


def denylist_ativa(raiz: Path, caminho: Path | None = None) -> list[Entrada]:
    """A deny-list local (arquivo) ou do ambiente (secret da CI)."""
    alvo = caminho or (raiz / DENYLIST_LOCAL)
    if alvo.is_file():
        return carregar_denylist(alvo)
    return carregar_denylist(os.environ.get(ENV_DENYLIST, ""))


def main(argv: list[str] | None = None) -> int:
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001, S110
            pass
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--raiz", default=str(RAIZ_PADRAO))
    p.add_argument("--modo", choices=("auto", "git", "arvore"), default="auto")
    p.add_argument("--denylist-local")
    p.add_argument("--max", type=int, default=200, help="quantos achados listar")
    a = p.parse_args(argv)
    raiz = Path(a.raiz).resolve()
    deny = denylist_ativa(raiz, Path(a.denylist_local) if a.denylist_local else None)
    fict = carregar_ficticios(raiz / FICTICIOS)
    print(f"raiz {raiz} | deny-list local: {len(deny)} entrada(s) | ficticios: {len(fict)}")
    if not deny:
        print("AVISO: sem deny-list local (ci/denylist.local.txt ou $CG_DENYLIST_LOCAL) — "
              "so os detectores genericos rodaram.")
    achados = varrer_arvore(raiz, modo=a.modo, denylist=deny, ficticios=fict)
    for ach in achados[: a.max]:
        print(ach)
    if len(achados) > a.max:
        print(f"... e mais {len(achados) - a.max}")
    por_tipo: dict[str, int] = {}
    for ach in achados:
        por_tipo[ach.tipo] = por_tipo.get(ach.tipo, 0) + 1
    print("RESUMO:", ", ".join(f"{k}={v}" for k, v in sorted(por_tipo.items())) or "limpo")
    return 1 if achados else 0


if __name__ == "__main__":
    raise SystemExit(main())
