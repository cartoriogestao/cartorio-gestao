"""O `Modulo` PKCS#11 por `ctypes` — a troca que consertou o assinador A3.

O ACHADO DE 10/09/2026
    O oficial tentou o primeiro envio de verdade da carga da CRC e levou «o
    processo do assinador A3 não devolveu nada». Isolado por partes, o
    crash acontecia sempre em `PyKCS11.load()`, com os dois drivers desta
    casa, **com ou sem token conectado** — ou seja, nem token de verdade
    ajudaria. Chamadas cruas por `ctypes.WinDLL` (carregar a DLL,
    `C_GetFunctionList`, `C_Initialize`, `C_GetSlotList`) funcionaram todas,
    sem crash. O defeito era da extensão C do `PyKCS11`, não do driver.

O QUE ESTES TESTES GUARDAM
    - driver inexistente recusa com `Pkcs11Error`, e não com `OSError` cru;
    - `_explicar` traduz os códigos conhecidos, e não estoura nos
      desconhecidos.

**ESTE ARQUIVO NUNCA CHAMA `Modulo(...)` COM UM DRIVER REAL** — isso
carregaria a DLL do fabricante dentro do processo do pytest, e é
exatamente o que a arquitetura inteira deste projeto existe para evitar
fora de um processo isolado. `test_crc_a3.py` já cobre o caminho real,
de ponta a ponta, passando por `crc_a3.assinar()` — que isola em
subprocesso — em vez de por aqui.

O QUE ESTE MÓDULO NÃO TESTA
    Carregar os drivers de verdade, login, busca de certificado e
    assinatura — isso exige um token físico conectado, e só se prova no
    servidor real, isolado em subprocesso. Ver `test_crc_a3.py` e o
    cabeçalho de `crc_a3_assinador.py`.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import crc_a3_assinador as ASSINADOR


def test_driver_inexistente_recusa_com_pkcs11error():
    with pytest.raises(ASSINADOR.Pkcs11Error, match="nao carregou"):
        ASSINADOR.Modulo("driver_que_nao_existe.dll")


def test_explicar_conhece_pin_incorreto():
    texto = ASSINADOR._explicar(ASSINADOR.CKR_PIN_INCORRECT)
    assert "PIN incorreto" in texto
    assert "0x000000A0" in texto


def test_explicar_codigo_desconhecido_nao_estoura():
    texto = ASSINADOR._explicar(0x12345678)
    assert "0x12345678" in texto
