"""Responde «dá para atualizar agora?» — e só isso.

    «o que falta para eu poder atualizar?» — o oficial, 16/09/2026

POR QUE ISTO EXISTE. Há **duas passadas escrevendo esta árvore ao mesmo
tempo**, e o `ATUALIZAR_SISTEMA.cmd` copia o que estiver no disco no instante
em que roda. Em 16/09/2026, às 20h36, uma edição deixou **cinco telas com
`{% endif %}` sobrando** — todas equilibradas no pacote da véspera. Aplicar
naquele minuto levaria cinco telas de HTTP 500 para a máquina do balcão.

O QUE ELE CONFERE, E POR QUE SÃO ESSAS DUAS COISAS
--------------------------------------------------
  1. **Todo módulo compila** — `py_compile` em cada `.py`. Um `IndentationError`
     no meio de um arquivo não derruba uma tela: derruba o **sistema inteiro**,
     porque o `app.py` não carrega. Já aconteceu aqui (ver `logs/servidor.log`).
  2. **Toda tela desenha** — cada `.html` passa pelo Jinja com os filtros
     declarados pelo próprio `app.py` registrados.

**O AMBIENTE TEM DE SER O DO APP, e esta é a parte que se erra.** Um `Environment`
cru acusa `No filter named 'forte'` em doze telas que estão perfeitas — os
filtros da casa (`|forte`, `|filesize`, `|centavos_reais`, `|fromjson`) são
registrados no `create_app`. **Varredor que acusa quem está certo é pior que
varredor nenhum**: quem o roda aprende a ignorá-lo, e no dia do defeito de
verdade ele passa batido.

Os nomes dos filtros da casa (`|forte`, `|filesize`, `|centavos_reais`,
`|fromjson`) são extraídos dos decoradores `@app.template_filter` no código.
Assim a conferência não sobe banco, rotas e serviços só para analisar HTML — e
também não mantém uma segunda lista que envelheceria.

O QUE ELE **NÃO** RESPONDE, e é honesto dizer: se o que está escrito nas telas
e nos módulos está CERTO. Ele responde que está **inteiro** — que nada ficou
pela metade. A suíte é que diz se está certo, e ela roda quando o oficial pede.

    python tools\\conferir_antes_de_atualizar.py
"""
from __future__ import annotations

import argparse
import ast
from concurrent.futures import ThreadPoolExecutor
import hashlib
import pathlib
import sys
import tokenize

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

RAIZ = pathlib.Path(__file__).resolve().parent.parent
FERRAMENTAS = pathlib.Path(__file__).resolve().parent
if str(FERRAMENTAS) not in sys.path:
    sys.path.insert(0, str(FERRAMENTAS))


def arquivos_do_pacote() -> list[tuple[pathlib.Path, str]]:
    import criar_atualizacao
    return criar_atualizacao.todos_os_arquivos(RAIZ)


def _digest(arquivo: pathlib.Path) -> bytes:
    resumo = hashlib.sha256()
    with arquivo.open("rb") as origem:
        for bloco in iter(lambda: origem.read(1024 * 1024), b""):
            resumo.update(bloco)
    return resumo.digest()


def impressao_do_pacote(
    arquivos: list[tuple[pathlib.Path, str]] | None = None,
) -> str:
    """SHA-256 do nome e conteudo de tudo que o atualizador levaria."""
    arquivos = arquivos if arquivos is not None else arquivos_do_pacote()
    resumo = hashlib.sha256()
    # Muitos arquivos pequenos: as leituras de disco se sobrepoem, sem mudar a
    # ordem deterministica em que os digests entram na impressao final.
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(arquivos)))) as grupo:
        digests = grupo.map(_digest, (arquivo for arquivo, _ in arquivos))
        pares = zip(arquivos, digests)
        for (_arquivo, destino), digest in pares:
            resumo.update(destino.encode("utf-8"))
            resumo.update(b"\0sha256\0")
            resumo.update(digest)
            resumo.update(b"\0")
    return resumo.hexdigest()


def estado_do_pacote(
    arquivos: list[tuple[pathlib.Path, str]] | None = None,
) -> dict[str, tuple[int, int]]:
    """Detector rapido de mudanca durante a conferencia, sem reler conteudo."""
    estado = {}
    fonte = arquivos if arquivos is not None else arquivos_do_pacote()
    for arquivo, destino in fonte:
        stat = arquivo.stat()
        estado[destino] = (stat.st_size, stat.st_mtime_ns)
    return estado


def modulos_do_pacote() -> list[pathlib.Path]:
    """Todos os Python que realmente viajariam, pela regua do empacotador."""
    arquivos = arquivos_do_pacote()
    return [
        arquivo for arquivo, destino in arquivos
        if pathlib.PurePosixPath(destino).suffix.lower() == ".py"
    ]


def modulos_que_nao_compilam(
    modulos: list[pathlib.Path] | None = None,
) -> list[tuple[str, str]]:
    ruins = []
    for f in modulos if modulos is not None else modulos_do_pacote():
        try:
            with tokenize.open(f) as origem:
                codigo = origem.read()
            compile(codigo, str(f), "exec", flags=ast.PyCF_ONLY_AST, dont_inherit=True)
        except (SyntaxError, UnicodeError) as erro:
            ruins.append((f.name, f"{type(erro).__name__}: {erro}"[:110]))
        except Exception as erro:                            # noqa: BLE001
            ruins.append((f.name, f"{type(erro).__name__}: {erro}"[:110]))
    return ruins


def inconsistencia_de_versao() -> str | None:
    """Compara o carimbo instalado com a versão que o app responderá."""
    try:
        declarada = (RAIZ / "VERSAO.txt").read_text(encoding="utf-8").strip()
        arvore = ast.parse((RAIZ / "app.py").read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeError) as erro:
        return f"não foi possível ler a versão: {erro}"
    versao_app = None
    for no in arvore.body:
        if not isinstance(no, (ast.Assign, ast.AnnAssign)):
            continue
        alvos = no.targets if isinstance(no, ast.Assign) else [no.target]
        valor = no.value
        if (any(isinstance(alvo, ast.Name) and alvo.id == "VERSION" for alvo in alvos)
                and isinstance(valor, ast.Constant)
                and isinstance(valor.value, str)):
            versao_app = valor.value.strip()
            break
    if not declarada:
        return "VERSAO.txt está vazio"
    if versao_app is None:
        return "app.py não declara VERSION como texto literal"
    if versao_app != declarada:
        return f"VERSAO.txt declara {declarada}, mas app.py responde {versao_app}"
    return None


def telas_que_nao_desenham() -> tuple[int, list[tuple[str, str]]]:
    """Compila no Jinja com os filtros declarados pelo app, sem subir o DB.

    Os nomes nao ficam duplicados aqui: sao extraidos dos decoradores
    ``@app.template_filter`` do proprio app.py. Assim um filtro novo entra
    automaticamente, mas um filtro digitado errado numa tela continua falhando.
    """
    from jinja2 import Environment, FileSystemLoader

    arvore = ast.parse((RAIZ / "app.py").read_text(encoding="utf-8"))
    filtros = set()
    for no in ast.walk(arvore):
        if not isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorador in no.decorator_list:
            if not isinstance(decorador, ast.Call) or not decorador.args:
                continue
            funcao = decorador.func
            nome = decorador.args[0]
            if (isinstance(funcao, ast.Attribute)
                    and funcao.attr == "template_filter"
                    and isinstance(nome, ast.Constant)
                    and isinstance(nome.value, str)):
                filtros.add(nome.value)

    env = Environment(loader=FileSystemLoader(str(RAIZ / "templates")))
    identidade = lambda valor, *args, **kwargs: valor
    for nome in filtros:
        env.filters[nome] = identidade

    telas = sorted((RAIZ / "templates").rglob("*.html"))
    ruins = []
    for t in telas:
        nome = str(t.relative_to(RAIZ / "templates")).replace("\\", "/")
        try:
            env.get_template(nome)
        except Exception as erro:                            # noqa: BLE001
            ruins.append((nome, f"{type(erro).__name__}: {erro}"[:110]))
    return len(telas), ruins


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fingerprint-out", type=pathlib.Path)
    ap.add_argument("--expect-fingerprint", type=pathlib.Path)
    args = ap.parse_args(argv)

    if args.expect_fingerprint:
        try:
            esperado = args.expect_fingerprint.read_text(encoding="ascii").strip()
        except OSError as erro:
            print(f"ERRO: nao foi possivel ler a impressao da pre-conferencia: {erro}")
            return 1
        atual = impressao_do_pacote()
        if atual != esperado:
            print("ERRO: a arvore mudou depois da pre-conferencia.")
            print("  Nao e seguro instalar uma versao diferente da que foi validada.")
            return 1
        print("Arvore inalterada desde a pre-conferencia.")
        return 0

    print("CONFERINDO A ÁRVORE ANTES DE ATUALIZAR")
    print(f"  pasta: {RAIZ}")
    print()

    arquivos_antes = arquivos_do_pacote()
    estado_antes = estado_do_pacote(arquivos_antes)

    modulos = [
        arquivo for arquivo, destino in arquivos_antes
        if pathlib.PurePosixPath(destino).suffix.lower() == ".py"
    ]
    ruins = modulos_que_nao_compilam(modulos)
    quantos = len(modulos)
    print(f"módulos que compilam: {quantos - len(ruins)} de {quantos}")
    for nome, erro in ruins:
        print(f"   ✗ {nome}: {erro}")

    total, telas = telas_que_nao_desenham()
    print(f"telas que desenham:   {total - len(telas)} de {total}")
    for nome, erro in telas:
        print(f"   ✗ {nome}: {erro}")

    versao_ruim = inconsistencia_de_versao()
    if versao_ruim:
        print(f"versão inconsistente: ✗ {versao_ruim}")
    else:
        print("versão consistente:    sim")

    print()
    arquivos_depois = arquivos_do_pacote()
    estado_depois = estado_do_pacote(arquivos_depois)
    mudou_durante = estado_antes != estado_depois
    if mudou_durante:
        print("A ARVORE MUDOU DURANTE A CONFERENCIA.")
        print("  Aguarde as edicoes terminarem e execute novamente.")
    if ruins or telas or versao_ruim or mudou_durante:
        print("NÃO ATUALIZE AINDA.")
        print("  O que está torto viaja junto: o `ATUALIZAR_SISTEMA.cmd` copia o")
        print("  que estiver no disco na hora em que roda. Tela que não desenha")
        print("  vira HTTP 500 no balcão; módulo que não compila derruba o")
        print("  sistema inteiro ao subir.")
        return 1
    if args.fingerprint_out:
        impressao_depois = impressao_do_pacote(arquivos_depois)
        args.fingerprint_out.parent.mkdir(parents=True, exist_ok=True)
        args.fingerprint_out.write_text(impressao_depois + "\n", encoding="ascii")
    print("PODE ATUALIZAR: tudo compila e toda tela desenha.")
    print("  Isto não diz que está CERTO — diz que está INTEIRO.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
