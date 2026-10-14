"""Baixa UMA remessa pendente da CRA em homologação e preserva a resposta.

Uso deliberadamente manual: a consulta pode mudar o estado remoto. Não há
retentativa automática, importação de títulos, confirmação ou retorno.
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path


RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

import centrais_cred as CRED  # noqa: E402
import cra21_api as CRA  # noqa: E402


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("uso: baixar_remessa_cra_homologacao.py NOME_ARQUIVO PASTA_PRIVADA")
    nome, pasta_texto = sys.argv[1:]
    pasta = Path(pasta_texto).resolve()
    if not pasta.is_dir():
        raise SystemExit("Pasta privada de destino nao existe")
    if not CRED.tem(CRED.CRA, CRED.HOMOLOGACAO):
        raise SystemExit("Credencial de homologacao nao configurada")

    # A Central pode considerar a remessa baixada mesmo se a rede cair depois
    # de receber o pedido. Repetir automaticamente seria perder essa evidência.
    CRA.TENTATIVAS_DE_REDE = 0
    instante = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = f"cra_homologacao_pendentes_{instante}"
    valores = {"userArq": nome, "downloadImagem": CRA.SO_CONFERIR_A_IMAGEM}
    resposta = CRA._bater(CRED.HOMOLOGACAO, "RemessaPendente", valores)
    bruto = resposta.encode("utf-8")
    destino = pasta / f"{base}.soap.xml"
    with destino.open("xb") as arquivo:
        arquivo.write(bruto)

    metadados = {
        "instante_local": instante,
        "ambiente": CRED.HOMOLOGACAO,
        "operacao": "RemessaPendente",
        "userArq": nome,
        "downloadImagem": CRA.SO_CONFERIR_A_IMAGEM,
        "bytes_soap": len(bruto),
        "sha256_soap": hashlib.sha256(bruto).hexdigest(),
        "arquivo_soap": destino.name,
        "retentativas": 0,
        "titulos_importados": 0,
    }
    try:
        conteudo = CRA.ler_resposta(resposta, "baixar remessas pendentes")
    except CRA.CraError as erro:
        metadados["resposta_interpretada"] = "recusa_ou_formato_inesperado"
        metadados["motivo"] = str(erro)[:300]
    else:
        extraido = conteudo.encode("utf-8")
        with (pasta / f"{base}.return.txt").open("xb") as arquivo:
            arquivo.write(extraido)
        metadados.update({
            "resposta_interpretada": "return_extraido",
            "bytes_return": len(extraido),
            "sha256_return": hashlib.sha256(extraido).hexdigest(),
            "arquivo_return": f"{base}.return.txt",
        })
    with (pasta / f"{base}.metadata.json").open("x", encoding="utf-8") as arquivo:
        json.dump(metadados, arquivo, ensure_ascii=False, indent=2)
    print(json.dumps(metadados, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
