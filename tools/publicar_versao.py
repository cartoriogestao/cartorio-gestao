"""Publicar uma versão no GitHub, para o botão «Baixar e atualizar» da tela de atualizações.

Oficial, 02/11/2026: a atualização sai do GitHub, com a senha do oficial, sem escolher arquivo nem colar SHA.
Esta ferramenta é o outro lado: roda NA MÁQUINA DO OFICIAL, onde está a chave de assinatura, e faz o que
antes eram passos à mão:

    python tools/publicar_versao.py --versao 3.7.12 --desde v3.7.11 --chave E:\\chave_cartorio.pem

1. monta o pacote a partir da etiqueta `v<versão>` (uma cópia limpa dela, e não a pasta de trabalho);
2. `--desde`: só o que mudou desde a versão anterior — o atualizador da 3.7.8 recusa o pacote completo;
3. assina com a chave do oficial: **a senha da chave é pedida aqui, e só ele a digita**;
4. publica a «Release» `v<versão>` com o `.cgu` e o `.cgu.sha256`, e as novidades da versão como texto.

Sem `--chave` o pacote sai sem assinatura, e a instalação que tem chave cadastrada o recusa: serve só para
ensaio. `--sem-publicar` monta e assina sem mandar ao GitHub.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
REPOSITORIO = "cartoriogestao/cartorio-gestao"


def novidades_da_versao(texto: str, versao: str) -> str:
    """O trecho de `docs/NOVIDADES.md` da versão, do título dela até o da anterior. Só calcula."""
    m = re.search(rf"^## {re.escape(versao)}\b.*?$(.*?)(?=^## \d|\Z)", texto, re.S | re.M)
    return m.group(0).strip() if m else f"Cartório Gestão {versao}"


def _rodar(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(list(args), cwd=cwd, check=True, capture_output=True, text=True).stdout


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--versao", required=True, help="a versão a publicar; a etiqueta v<versão> precisa existir")
    ap.add_argument("--desde", required=True, help="a etiqueta da versão anterior (ex.: v3.7.9)")
    ap.add_argument("--chave", type=Path, default=None, help="a chave de assinatura do oficial (.pem)")
    ap.add_argument("--gh", default="gh", help="o programa gh (GitHub CLI), já autenticado")
    ap.add_argument("--repositorio", default=REPOSITORIO)
    ap.add_argument("--saida", type=Path, default=None, help="pasta onde deixar o pacote (padrão: temporária)")
    ap.add_argument("--sem-publicar", action="store_true", help="monta e assina, sem mandar ao GitHub")
    args = ap.parse_args(argv)

    etiqueta = f"v{args.versao}"
    _rodar("git", "rev-parse", "--verify", f"{etiqueta}^{{commit}}", cwd=RAIZ)
    _rodar("git", "rev-parse", "--verify", f"{args.desde}^{{commit}}", cwd=RAIZ)
    saida = args.saida or Path(tempfile.mkdtemp(prefix="publicar_"))
    saida.mkdir(parents=True, exist_ok=True)
    pacote = saida / f"CartorioGestao-{args.versao}.cgu"
    with tempfile.TemporaryDirectory(prefix="etiqueta_") as td:
        copia = Path(td) / "copia"
        _rodar("git", "worktree", "add", "--detach", str(copia), etiqueta, cwd=RAIZ)
        try:
            comando = [sys.executable, str(copia / "tools" / "criar_atualizacao.py"), str(copia),
                       "--version", args.versao, "--min-version", args.desde.lstrip("v"),
                       "--desde", args.desde, "--output", str(pacote), "--sem-versionar"]
            if args.chave:
                comando += ["--assinar", str(args.chave)]
            # Sem capturar: a senha da chave é pedida pelo `criar_atualizacao`, no terminal do oficial.
            subprocess.run(comando, check=True)
            novidades = novidades_da_versao((copia / "docs" / "NOVIDADES.md").read_text(encoding="utf-8"),
                                            args.versao)
        finally:
            _rodar("git", "worktree", "remove", "--force", str(copia), cwd=RAIZ)
    sha = hashlib.sha256(pacote.read_bytes()).hexdigest()
    arquivo_sha = pacote.with_name(pacote.name + ".sha256")
    arquivo_sha.write_text(f"{sha}  {pacote.name}\n", encoding="ascii")
    notas = saida / "novidades.md"
    notas.write_text(novidades + "\n", encoding="utf-8")
    print(pacote)
    print(sha)
    if args.sem_publicar:
        print("Não publicado (--sem-publicar).")
        return 0
    existe = subprocess.run([args.gh, "release", "view", etiqueta, "-R", args.repositorio],
                            capture_output=True).returncode == 0
    if existe:
        _rodar(args.gh, "release", "upload", etiqueta, str(pacote), str(arquivo_sha), "--clobber",
               "-R", args.repositorio)
    else:
        _rodar(args.gh, "release", "create", etiqueta, str(pacote), str(arquivo_sha),
               "--title", f"Cartório Gestão {args.versao}", "--notes-file", str(notas),
               "--verify-tag", "-R", args.repositorio)
    print(f"Publicada: {etiqueta} em {args.repositorio}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
