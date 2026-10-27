"""A chave do oficial que assina os pacotes de atualização (`.cgu`).

QUEM RODA ESTE PROGRAMA É O OFICIAL, e a senha é digitada por ele — ela não
aparece na tela, não vai a arquivo nenhum e não passa por ninguém.

    python tools\\chave_de_atualizacao.py gerar --saida E:\\chave_cartorio.pem
    python tools\\chave_de_atualizacao.py mostrar --chave E:\\chave_cartorio.pem

`gerar` cria o par de chaves: a PRIVADA vai, cifrada pela senha, para o arquivo
de `--saida` (o ideal é um pendrive guardado com o oficial); a PÚBLICA é
impressa na tela — ela não é segredo — e, com `--instalacao <pasta do
programa>`, gravada no arquivo de chaves daquela instalação
(`chaves_de_atualizacao.json`), que é o que ela passa a aceitar.

    python tools\\chave_de_atualizacao.py cadastrar --chave E:\\chave_cartorio.pem ^
        --instalacao "C:\\Program Files\\CartorioGestao"

`cadastrar` faz só a segunda metade, para uma chave que já existe (outra
máquina, ou instalação nova da mesma serventia).

RECUSA gravar a chave privada dentro das árvores do projeto ou da pasta de
dados do sistema: as duas viajam (git, pacote, backup), e a chave que viaja
deixa de ser só do oficial. E nunca sobrescreve uma chave que já existe —
perder a chave antiga é perder a capacidade de assinar como antes.

Se a chave for perdida: gera-se outra e cadastra-se a pública nova (a antiga
sai da lista). Se for ROUBADA: o mesmo, e já — quem a tem assina pacotes que
esta instalação aceitaria.
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import assinatura_da_atualizacao as ASS   # noqa: E402

SENHA_MINIMA = 12


def pastas_proibidas() -> list[Path]:
    """Onde a chave privada não pode morar: o que o git, o pacote ou o backup levam."""
    proibidas = [RAIZ]
    for p in RAIZ.parents:                       # a casa inteira do projeto
        if p.name == "CartorioGestao":
            proibidas.append(p)
            break
    base = os.environ.get("CARTORIO_GESTAO_DATA") or os.path.join(
        os.environ.get("PROGRAMDATA", r"C:\ProgramData"), "CartorioGestao")
    proibidas.append(Path(base))
    return [p.resolve() for p in proibidas]


def _dentro(caminho: Path, pasta: Path) -> bool:
    try:
        caminho.resolve().relative_to(pasta)
        return True
    except ValueError:
        return False


def gerar(saida: Path, senha: str) -> tuple[str, str]:
    """Cria o par e grava a privada cifrada. Devolve (id, pública em base64)."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519
    import base64

    if len(senha) < SENHA_MINIMA:
        raise SystemExit(f"A senha precisa ter pelo menos {SENHA_MINIMA} caracteres.")
    for pasta in pastas_proibidas():
        if _dentro(saida, pasta):
            raise SystemExit(
                f"Recusado: {saida} fica dentro de {pasta}, que vai para o git, "
                "para o pacote ou para o backup. Grave a chave fora — o ideal é "
                "um pendrive guardado com o oficial.")
    if saida.exists():
        raise SystemExit(f"Recusado: {saida} já existe. Esta ferramenta nunca "
                         "sobrescreve uma chave.")
    privada = ed25519.Ed25519PrivateKey.generate()
    pem = privada.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.BestAvailableEncryption(senha.encode("utf-8")))
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_bytes(pem)
    crua = ASS.publica_crua(privada)
    return ASS.id_da_chave(crua), base64.b64encode(crua).decode("ascii")


def main(argv: list[str] | None = None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except AttributeError:
            pass
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="acao", required=True)
    g = sub.add_parser("gerar", help="cria a chave do oficial")
    g.add_argument("--saida", required=True, type=Path)
    g.add_argument("--instalacao", type=Path,
                   help="pasta do programa instalado: grava ali a parte pública")
    m = sub.add_parser("mostrar", help="mostra a parte pública de uma chave")
    m.add_argument("--chave", required=True, type=Path)
    c = sub.add_parser("cadastrar", help="grava a parte pública numa instalação")
    c.add_argument("--chave", required=True, type=Path)
    c.add_argument("--instalacao", required=True, type=Path)
    a = ap.parse_args(argv)

    if a.acao == "gerar":
        senha = getpass.getpass("Senha da chave (não aparece na tela): ")
        if senha != getpass.getpass("Repita a senha: "):
            print("As duas senhas não conferem. Nada foi gravado.")
            return 1
        chave_id, publica = gerar(a.saida, senha)
        print(f"\nChave privada gravada em {a.saida} (cifrada pela senha).")
    else:
        senha = getpass.getpass("Senha da chave: ")
        privada = ASS.carregar_privada(a.chave.read_bytes(), senha.encode("utf-8"))
        import base64
        crua = ASS.publica_crua(privada)
        chave_id, publica = ASS.id_da_chave(crua), base64.b64encode(crua).decode("ascii")
    print(f"\nA parte PÚBLICA (não é segredo): {chave_id} = {publica}")
    instalacao = getattr(a, "instalacao", None)
    if instalacao:
        arquivo = ASS.gravar_chave_na_instalacao(
            chave_id, publica, Path(instalacao) / ASS.ARQUIVO_DAS_CHAVES.name)
        print(f"Cadastrada em {arquivo} — esta instalação passa a aceitar os "
              f"pacotes assinados por esta chave.")
    else:
        print("Para a instalação aceitá-la, rode de novo com --instalacao "
              "<pasta do programa> (ou use `cadastrar`).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
