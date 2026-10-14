"""A assinatura A3 da carga da CRC — chamada em PROCESSO ISOLADO, sempre.

Este é o "caminho 2" que `DOCUMENTACAO/ASSINATURA_DIGITAL_A3.md` já previa e
declarava "não se constrói hoje, e o motivo está medido": carregar o driver
PKCS#11 do token dentro do processo do Flask/waitress DERRUBA O SERVIDOR
(segmentation fault medido nos dois drivers desta casa, código de saída 139).

**ESTE MÓDULO NUNCA CARREGA O DRIVER.** Quem carrega é `crc_a3_assinador.py`,
um processo `python.exe` à parte, chamado por `subprocess.run` — o mesmo
padrão que já isola o LibreOffice em `impressao_pdf.py`: **não se olha o
código de saída** (um segfault sai com um código que não é exceção nenhuma do
Python); **quem responde é o arquivo de saída existir**.

O PIN NÃO SE GUARDA EM LUGAR NENHUM — nem no banco, nem em `.cred`, nem em
log. Ele é pedido ao delegatário na hora de assinar, passado ao processo
filho por um arquivo temporário de permissão só do usuário, e apagado (com o
resto da entrada) assim que a chamada termina — dando certo ou não.

O QUE ESTE MÓDULO NÃO FAZ
    Não monta o envelope SOAP nem chama a CRC — isso depende do WSDL real,
    que ainda não foi medido (ver `crc_carga.py`). Ele só assina bytes que
    outro módulo decide o que são.
"""
from __future__ import annotations

import base64
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

# Medido em `DOCUMENTACAO/ASSINATURA_DIGITAL_A3.md` — os dois drivers
# instalados nesta casa. Não são os únicos que existem no mundo; são os que
# esta serventia tem.
DRIVERS_CONHECIDOS = ("eTPKCS11.dll", "IDPrimePKCS1164.dll")

# Segundos até desistir do processo filho. Carregar um driver PKCS#11 e
# assinar é operação local, rápida quando funciona — o teto é generoso só
# para não confundir "está pensando" com "quebrou".
PRAZO_SEGUNDOS = 30

_ASSINADOR = Path(__file__).with_name("crc_a3_assinador.py")


class AssinaturaA3Error(ValueError):
    """Erro de regra, com mensagem pronta para o balcão."""


def assinar(mensagem: bytes, *, driver: str, pin: str) -> dict[str, Any]:
    """Assina `mensagem` com o A3, num processo à parte. Não grava nada.

    Devolve `{"assinatura_b64", "certificado_b64", "mecanismo"}`. Levanta
    `AssinaturaA3Error` — nunca deixa a exceção do subprocesso vazar crua —
    quando o token recusa, o driver não carrega, ou o processo simplesmente
    não voltou (segfault).

    **O PIN NÃO FICA NO ARGV**: ele vai dentro do arquivo de entrada, que
    nasce com permissão só do usuário e é apagado no `finally`, dando certo
    ou não.
    """
    if not pin:
        raise AssinaturaA3Error(
            "digite o PIN do certificado antes de assinar — ele não fica "
            "guardado em lugar nenhum, e é pedido a cada assinatura")

    with tempfile.TemporaryDirectory(prefix="cg_crc_a3_") as pasta:
        area = Path(pasta)
        entrada = area / "entrada.json"
        saida = area / "saida.json"
        entrada.write_text(json.dumps({
            "driver": driver,
            "pin": pin,
            "mensagem_b64": base64.b64encode(mensagem).decode("ascii"),
        }), encoding="utf-8")

        try:
            subprocess.run(
                [sys.executable, str(_ASSINADOR), str(entrada), str(saida)],
                capture_output=True, timeout=PRAZO_SEGUNDOS, check=False)
        except (subprocess.TimeoutExpired, OSError):
            # Também cobre o segfault: o processo morre, o `subprocess.run`
            # devolve o controle (com ou sem exceção conforme a plataforma),
            # e o arquivo de saída simplesmente não existe — testado abaixo.
            pass
        finally:
            entrada.unlink(missing_ok=True)

        erro_path = area / "saida.json.erro"
        if erro_path.exists():
            detalhe = json.loads(erro_path.read_text(encoding="utf-8"))
            raise AssinaturaA3Error(
                f"o assinador A3 não conseguiu assinar: {detalhe.get('erro')}")

        if not saida.exists() or saida.stat().st_size == 0:
            raise AssinaturaA3Error(
                "o processo do assinador A3 não devolveu nada — se o token "
                "não estiver conectado ou o driver tiver travado, é isto "
                "que acontece. O servidor continua de pé: só este processo "
                "à parte foi afetado")

        return json.loads(saida.read_text(encoding="utf-8"))


def driver_disponivel(nome: str) -> Path | None:
    """Onde este driver está no Windows, se estiver — só olha, não carrega.

    Procura em `System32` (64 bits) e `SysWOW64` (32 bits), que é onde o
    instalador de cada fabricante costuma registrar o PKCS#11. **Não abre o
    arquivo, não faz `ctypes.CDLL` nele** — abrir a DLL é exatamente o passo
    que dá segfault, e esta função só serve para a tela dizer "encontrado"
    antes de pedir o PIN.
    """
    windir = Path(sys.prefix).anchor + "Windows"
    for pasta in ("System32", "SysWOW64"):
        candidato = Path(windir) / pasta / nome
        if candidato.exists():
            return candidato
    return None
