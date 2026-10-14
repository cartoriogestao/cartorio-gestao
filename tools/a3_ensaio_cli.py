"""Ensaio A3 pela linha de comando — sem reiniciar :8899.

Chama o serviço local em 127.0.0.1:8766 via assinar_com_a3.

Exemplos (no servidor de sandbox, pasta sistema):
  py -3 tools/a3_ensaio_cli.py saude
  py -3 tools/a3_ensaio_cli.py certs
  py -3 tools/a3_ensaio_cli.py assinar caminho\\teste.pdf
      (pede o PIN no prompt; não passa por argv)

Não grava PIN. Não fala com CCN/e-Notariado.
"""
from __future__ import annotations

import getpass
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import assinar_com_a3 as A3


def _cmd_saude() -> int:
    try:
        dados = A3.status_do_servico()
    except A3.AssinarComA3Error as exc:
        print(f"FORA: {exc}")
        return 1
    print("OK serviço", dados.get("servico"), "porta", dados.get("porta"))
    print("driver em uso:", dados.get("driver") or dados.get("erro_driver"))
    cands = dados.get("candidatos") or []
    print(f"candidatos no disco ({len(cands)}):")
    for c in cands:
        print(f"  - {c.get('nome')}  [{c.get('origem')}]  {c.get('caminho')}")
    print(json.dumps(dados, ensure_ascii=False, indent=2))
    return 0


def _cmd_certs() -> int:
    try:
        lista = A3.listar_certificados()
    except A3.AssinarComA3Error as exc:
        print(f"ERRO: {exc}")
        return 1
    if not lista:
        print("Nenhum certificado (token ausente ou lista vazia).")
        return 0
    for i, c in enumerate(lista, 1):
        print(f"{i}. {c.get('subject')}")
        print(f"   thumbprint: {c.get('thumbprint')}")
        if c.get("label"):
            print(f"   label: {c.get('label')}")
    return 0


def _cmd_assinar(caminho: str) -> int:
    path = Path(caminho)
    if not path.is_file():
        print(f"arquivo não encontrado: {caminho}")
        return 1
    pdf = path.read_bytes()
    pin = getpass.getpass("PIN do token A3 (não fica gravado): ")
    try:
        resultado = A3.assinar_pdf(pdf, pin)
    except A3.AssinarComA3Error as exc:
        print(f"ERRO: {exc}")
        return 1
    finally:
        pin = ""
    print("OK formato=", resultado.get("formato"))
    print("subject=", resultado.get("subject"))
    print("thumbprint=", resultado.get("thumbprint"))
    cms = resultado.get("cms_b64")
    if cms:
        out = path.with_suffix(path.suffix + ".p7s")
        import base64
        out.write_bytes(base64.b64decode(cms))
        print("CMS gravado em", out)
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd = argv[1].lower()
    if cmd == "saude":
        return _cmd_saude()
    if cmd in ("certs", "certificados"):
        return _cmd_certs()
    if cmd == "assinar":
        if len(argv) < 3:
            print("uso: a3_ensaio_cli.py assinar <arquivo.pdf>")
            return 2
        return _cmd_assinar(argv[2])
    print(f"comando desconhecido: {cmd}")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
