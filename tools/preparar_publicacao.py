"""Prepara a publicação no GitHub: a árvore pública vira um commit, com etiqueta.

    python tools\\preparar_publicacao.py                 # destino padrão: CartorioGestao\\PUBLICACAO\\repositorio
    python tools\\preparar_publicacao.py --destino D:\\cg-publico

O QUE FAZ, NESTA ORDEM, E PARA NO PRIMEIRO PROBLEMA
    1. gera a árvore pública com `tools/exportar_publico.py --gerar` (a lista do
       que entra, os moldes sem quem os salvou);
    2. RECUSA se o portão anti-vazamento achar qualquer coisa — publicar só com
       zero achados;
    3. no destino, um repositório git SÓ DO PÚBLICO (`main`), separado do git
       privado da casa (`VERSIONAMENTO\\casa.git`, que tem os dados da serventia
       e nunca vai ao GitHub): grava a versão como um commit e põe a etiqueta
       `vX.Y.Z` — recusando versão que já tem etiqueta com outro conteúdo;
    4. imprime os comandos para o oficial enviar.

O QUE NÃO FAZ: não cria repositório no GitHub, não guarda senha nem token, e
**não envia nada** — `git push` é do oficial (decisão de 10/10/2026: «vou
publicar, depois, na conta do github do cartorio gestao»).

QUAL ÁRVORE SE PUBLICA: a deste programa. Rodado do INSTALAR, publica a versão
que está na produção — o recomendado: o público recebe versões lançadas, e não o
trabalho em andamento do SANDBOX.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import tools.exportar_publico as EXP   # noqa: E402

AUTOR = ["-c", "user.name=Cartório Gestão",
         "-c", "user.email=publicacao@cartorio-gestao.invalid"]


def destino_padrao() -> Path:
    for pai in RAIZ.parents:
        if pai.name == "CartorioGestao":
            return pai / "PUBLICACAO" / "repositorio"
    return RAIZ.parent / "PUBLICACAO" / "repositorio"


def _git(destino: Path, *args: str, ok: bool = False) -> str:
    # BYTES, e não `text=True` (o `\r` que o Windows põe no que vai ao git).
    r = subprocess.run(["git", "-C", str(destino), "-c", "core.autocrlf=false",
                        *AUTOR, *args], capture_output=True)
    if r.returncode and not ok:
        raise SystemExit("git " + " ".join(args[:2]) + " falhou: "
                         + r.stderr.decode("utf-8", "replace").strip())
    return r.stdout.decode("utf-8", "replace").strip()


def _denylists_da_casa() -> list[Path]:
    """As deny-lists locais das árvores irmãs (INSTALAR e SANDBOX)."""
    achadas = []
    for pai in RAIZ.parents:
        if pai.name == "CartorioGestao":
            for rel in ("SERVIDOR/INSTALAR_CARTORIO_GESTAO", "SANDBOX/sistema"):
                d = pai / rel / "ci" / "denylist.local.txt"
                if d.is_file():
                    achadas.append(d)
            break
    return achadas


def _entradas(arq: Path) -> set[str]:
    return {linha.strip() for linha in arq.read_text(encoding="utf-8").splitlines()
            if linha.strip() and not linha.lstrip().startswith("#")}


def conferir_denylist() -> bool:
    """A deny-list desta árvore é a mais completa da casa?

    23/10/2026: a v3.7.1 saiu do INSTALAR com três nomes da equipe dentro, e
    o portão daqui disse «zero achados». A deny-list do INSTALAR tinha 34
    linhas e a do SANDBOX, 43 — os primeiros nomes acrescentados em 14/10
    nunca chegaram ao INSTALAR. Portão com lista velha é o carimbo que mente:
    responde zero sobre o que não procurou. Por isso: sem deny-list, recusa;
    com uma árvore irmã guardando entrada que esta não tem, recusa.
    """
    import hashlib
    minha = RAIZ / "ci" / "denylist.local.txt"
    if not minha.is_file():
        print("RECUSADO: sem ci/denylist.local.txt o portão não procura os nomes da casa.")
        return False
    linhas = _entradas(minha)
    sha = hashlib.sha256(minha.read_bytes()).hexdigest()
    print(f"deny-list: {len(linhas)} entradas, SHA-256 {sha[:16]}…")
    for outra in _denylists_da_casa():
        if outra.resolve() == minha.resolve():
            continue
        faltam = _entradas(outra) - linhas
        if faltam:
            print(f"RECUSADO: a deny-list de {outra.parent.parent} tem {len(faltam)} "
                  "entrada(s) que a desta árvore não tem. Copie a mais completa e "
                  "rode de novo.")
            return False
    return True


def main(argv: list[str] | None = None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except AttributeError:
            pass
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--destino", type=Path, default=None)
    a = ap.parse_args(argv)
    destino = (a.destino or destino_padrao()).resolve()
    versao = (RAIZ / "VERSAO.txt").read_text(encoding="utf-8").strip()

    print(f"Publicação da versão {versao} (árvore: {RAIZ})\n")
    if not conferir_denylist():
        return 1
    if EXP.main(["--gerar", str(destino)]) != 0:
        print("\nNADA FOI GRAVADO no repositório público: o portão achou o que "
              "não pode sair. Resolva os achados acima e rode de novo.")
        return 1

    if not (destino / ".git").is_dir():
        _git(destino, "init", "-q", "-b", "main")
    # A marca do exportador é da máquina, não do projeto.
    exclude = destino / ".git" / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    if ".exportado_publico" not in (exclude.read_text(encoding="utf-8")
                                    if exclude.is_file() else ""):
        with exclude.open("a", encoding="utf-8") as f:
            f.write("\n.exportado_publico\n")

    etiqueta = f"v{versao}"
    _git(destino, "add", "-A")
    tem_historico = _git(destino, "rev-parse", "--verify", "-q", "HEAD", ok=True)
    mudou = not tem_historico or _git(destino, "diff", "--cached", "--name-only",
                                      "HEAD", ok=True)
    if _git(destino, "tag", "--list", etiqueta):
        if mudou:
            raise SystemExit(
                f"A etiqueta {etiqueta} já existe no repositório público com outro "
                "conteúdo. Uma versão publicada não muda: suba a versão.")
        print(f"\nA versão {versao} já está publicada localmente, sem mudança.")
    else:
        if mudou:
            _git(destino, "commit", "-q", "-m",
                 f"Cartório Gestão {versao}\n\nÁrvore pública gerada por "
                 "tools/exportar_publico.py, com o portão anti-vazamento em zero.")
        _git(destino, "tag", "-a", etiqueta, "-m", f"Cartório Gestão {versao}")
        print(f"\nGravado: commit {_git(destino, 'rev-parse', '--short', 'HEAD')} "
              f"e etiqueta {etiqueta} em {destino}")

    remoto = _git(destino, "remote", "get-url", "origin", ok=True)
    print("\nPARA ENVIAR (quem envia é o oficial):")
    if not remoto:
        print("  1. no GitHub, crie o repositório VAZIO (sem README, sem licença);")
        print(f'  2. git -C "{destino}" remote add origin https://github.com/<conta>/<repositorio>.git')
    print(f'  {"3." if not remoto else "1."} git -C "{destino}" push -u origin main --tags')
    print("  O login do GitHub é digitado por você, na hora do envio.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
