"""O ASSINADOR A3 EM PROCESSO ISOLADO — a mesma regra de `impressao_pdf.py`.

O QUE ESTES TESTES GUARDAM
    - **código de saída não é prova; o arquivo existir é** — o mesmo
      princípio medido em `impressao_pdf._tentar()`, agora para o assinador;
    - **PIN vazio nem chega a abrir um processo filho** — recusa antes de
      gastar o tempo de subir o `python.exe` e tentar carregar o driver;
    - **driver que não existe recusa por arquivo de erro**, e o processo
      principal deste teste continua vivo para provar isso;
    - **contra os drivers REAIS desta máquina** (`eTPKCS11.dll`,
      `IDPrimePKCS1164.dll`), sem token conectado: `AssinaturaA3Error` chega
      limpo, com «nenhum token conectado nesta máquina» — e não mais por
      sobreviver a um crash. Até 10/09/2026 o `crc_a3_assinador.py` usava
      `PyKCS11`, que **quebrava sempre** nestes dois drivers, com ou sem
      token, na primeira chamada (`pkcs11.load()`) — medido com
      `ctypes.WinDLL` cru: a DLL carrega bem, `C_GetFunctionList` e
      `C_Initialize` chamados por fora respondem `CKR_OK`. O defeito era da
      extensão C do `PyKCS11`, e não do driver do fabricante nem do token.
      O assinador foi reescrito para chamar as funções PKCS#11 direto pelo
      nome exportado da DLL, sem passar pela tabela `CK_FUNCTION_LIST` —
      ver o cabeçalho de `crc_a3_assinador.py`.

O QUE ESTE MÓDULO NÃO TESTA
    Assinatura de verdade, contra um token físico conectado — isso só se
    prova no servidor real, com o certificado do delegatário. Ver o
    cabeçalho de `crc_a3.py`.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import crc_a3 as A3


def test_pin_vazio_recusa_sem_abrir_processo():
    with pytest.raises(A3.AssinaturaA3Error, match="PIN"):
        A3.assinar(b"o que for", driver="qualquer.dll", pin="")


def test_driver_inexistente_recusa_por_arquivo_de_erro():
    with pytest.raises(A3.AssinaturaA3Error, match="n[aã]o conseguiu assinar"):
        A3.assinar(b"teste", driver="driver_que_nao_existe.dll", pin="1234")


@pytest.mark.parametrize("nome", A3.DRIVERS_CONHECIDOS)
def test_driver_disponivel_so_olha_nunca_carrega(nome):
    """Só confere o arquivo no disco — não carrega a DLL neste processo.
    Se a máquina não tiver o driver instalado, `None` é a resposta certa,
    e não uma exceção."""
    achado = A3.driver_disponivel(nome)
    assert achado is None or achado.name == nome


@pytest.mark.parametrize("nome", A3.DRIVERS_CONHECIDOS)
def test_isolamento_recusa_limpo_sem_token(nome):
    """Contra os drivers reais desta máquina, sem token conectado: recusa
    limpa, com «nenhum token conectado» — e o processo principal deste
    teste continua vivo para provar isso, isolado ou não.

    **Isto não prova mais isolamento contra crash** — o crash que motivou
    a arquitetura de processo separado era da extensão `PyKCS11`, e o
    assinador não a usa mais. O isolamento continua existindo porque o
    driver do FABRICANTE ainda pode falhar de um jeito que nenhuma
    biblioteca evita — é por isso que ele fica.

    Pula sozinho se o driver não estiver instalado nesta máquina.
    """
    if A3.driver_disponivel(nome) is None:
        pytest.skip(f"{nome} não está instalado nesta máquina")
    with pytest.raises(A3.AssinaturaA3Error, match="nenhum token"):
        A3.assinar(b"teste de isolamento", driver=nome, pin="000000")
