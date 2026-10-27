"""O AJUDANTE QUE ASSINA COM O A3 — roda em PROCESSO SEPARADO, sempre.

Isto e o "caminho 2" que `DOCUMENTACAO/ASSINATURA_DIGITAL_A3.md` ja previa e
declarava "nao se constroi hoje": um processo a parte que carrega o driver
PKCS#11, pede o PIN e devolve a assinatura — e que um segfault ali mata so
ele, e nao o balcao inteiro.

**O FATO QUE NAO MUDOU**: carregar `eTPKCS11.dll` ou `IDPrimePKCS1164.dll`
dentro do processo do Flask/waitress DERRUBA O SERVIDOR. Este arquivo por
isso NUNCA E IMPORTADO pelo `app.py` — ele so existe para ser invocado como
`python.exe crc_a3_assinador.py <entrada> <saida>`, pelo `subprocess.run` de
`crc_a3.py`, no mesmo padrao ja usado para isolar o LibreOffice em
`impressao_pdf.py`.

**E O CULPADO NAO ERA O DRIVER: ERA A BIBLIOTECA — medido em 10/09/2026,**
no dia em que o oficial tentou o primeiro envio de verdade e levou
«o processo do assinador A3 nao devolveu nada». A versao anterior deste
arquivo usava `PyKCS11`, e o crash reproduziu **sempre**, com os dois
drivers, com ou sem token conectado, em `pkcs11.load()` — a primeira
chamada que ela faz. Isolado por partes:

  - `ctypes.WinDLL(caminho)` carrega a DLL **sem crash**;
  - `dll.C_GetFunctionList(...)` chamada crua, **sem crash**, `rv=0`;
  - `dll.C_Initialize(None)` chamada crua (por nome, exportada direto da
    DLL — nao pela tabela de funcoes), **sem crash**, `rv=0`;
  - `dll.C_GetSlotList(...)` chamada crua, **sem crash**, devolve os slots
    de verdade (12 leitores nesta maquina, 0 com token no momento medido).

**A DLL FUNCIONA. QUEM QUEBRAVA ERA A EXTENSAO C DO `PyKCS11`** — muito
provavelmente por nao respeitar o `#pragma pack(1)` que os cabecalhos do
PKCS#11 exigem no Windows para `CK_FUNCTION_LIST` (confirmado a mao: o
ponteiro de `C_Initialize` fica no byte 2 da struct, sem preenchimento —
tratar como se estivesse no byte 8, alinhado a ponteiro, aponta para o
meio de outra funcao e e exatamente o tipo de erro que produz um acesso
invalido). **Este arquivo para de depender do `PyKCS11` e fala com a DLL
direto, pelas funcoes exportadas por nome** — que sao as mesmas chamadas
`dll.C_Initialize`, `dll.C_GetSlotList` etc. que a medicao acima confirmou
que funcionam nesta maquina, com os dois drivers.

O CONTRATO DOS DOIS ARQUIVOS (NAO MUDOU)
    ENTRADA (JSON, apagado pelo chamador logo depois de ler): `{"driver":
    caminho da DLL, "pin": PIN do token, "mensagem_b64": bytes a assinar, em
    base64}`.

    SAIDA (JSON, so escrita se a assinatura deu certo): `{"assinatura_b64":
    ..., "certificado_b64": ..., "mecanismo": "CKM_SHA256_RSA_PKCS"}`.

    **Se este processo morrer (segfault, timeout), a SAIDA simplesmente NAO
    EXISTE** — e e assim que o chamador diferencia "funcionou" de "quebrou":
    pelo ARQUIVO, nunca pelo codigo de saida. Mesma regra de
    `impressao_pdf._tentar()`: "nao olha o codigo de retorno; quem responde e
    o arquivo existir".

O PIN NUNCA VAI NA LINHA DE COMANDO — apareceria na lista de processos do
Windows para qualquer um ver. Ele vai no arquivo de entrada, que o chamador
cria com permissao so do usuario, le uma vez e apaga.

ESTE ARQUIVO NAO DECIDE QUEM PODE ASSINAR NEM O QUE SE ASSINA — so assina o
que mandarem assinar. A pergunta "isto pode ir para a CRC" e de quem chama.

**A CONFERIR**: isto foi medido nesta maquina de desenvolvimento, com os
dois drivers instalados e SEM token fisico conectado (0 de 12 leitores com
token no momento da medicao). O caminho de login e assinatura, com um
token de verdade, so se confere no servidor real, com o certificado do
delegatario.
"""
from __future__ import annotations

import base64
import ctypes
import json
import sys

# ---------------------------------------------------------------- os tipos
#
# Os cabecalhos do PKCS#11 usam `#pragma pack(1)` no Windows: as structs
# abaixo NAO tem preenchimento nenhum entre os campos. `CK_ULONG` e
# "unsigned long" em C — no Windows isso e SEMPRE 4 bytes, mesmo em
# processo de 64 bits (modelo LLP64); `ctypes.c_ulong` mapeia exatamente
# para isso, e nao para o tamanho de um ponteiro.

CK_BYTE = ctypes.c_ubyte
CK_BBOOL = CK_BYTE
CK_ULONG = ctypes.c_ulong
CK_LONG = ctypes.c_long
CK_RV = CK_ULONG
CK_SLOT_ID = CK_ULONG
CK_SESSION_HANDLE = CK_ULONG
CK_OBJECT_HANDLE = CK_ULONG
CK_USER_TYPE = CK_ULONG
CK_ATTRIBUTE_TYPE = CK_ULONG
CK_MECHANISM_TYPE = CK_ULONG
CK_FLAGS = CK_ULONG
CK_VOID_PTR = ctypes.c_void_p

CKR_OK = 0x00000000
CKR_PIN_INCORRECT = 0x000000A0
CKR_PIN_LOCKED = 0x000000A4
CKR_TOKEN_NOT_PRESENT = 0x000000E0

# Nomes so para as mensagens de erro darem uma pista — nao e lista fechada.
_MOTIVOS_CONHECIDOS: dict[int, str] = {
    CKR_PIN_INCORRECT: "PIN incorreto",
    CKR_PIN_LOCKED: "PIN bloqueado — o token exige desbloqueio",
    CKR_TOKEN_NOT_PRESENT: "o token foi removido durante a operacao",
}


def _explicar(rv: int) -> str:
    conhecido = _MOTIVOS_CONHECIDOS.get(rv)
    return f"{conhecido} (codigo 0x{rv:08X})" if conhecido else f"codigo 0x{rv:08X}"


class CK_ATTRIBUTE(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("type", CK_ATTRIBUTE_TYPE),
               ("pValue", CK_VOID_PTR),
               ("ulValueLen", CK_ULONG)]


class CK_MECHANISM(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("mechanism", CK_MECHANISM_TYPE),
               ("pParameter", CK_VOID_PTR),
               ("ulParameterLen", CK_ULONG)]


# Constantes do vocabulario do PKCS#11 v2.20+, estaveis entre fabricantes.
CKO_CERTIFICATE = 0x00000001
CKO_PRIVATE_KEY = 0x00000003
CKA_CLASS = 0x00000000
CKA_ID = 0x00000102
CKA_VALUE = 0x00000011
CKU_USER = 0x00000001
CKF_RW_SESSION = 0x00000002
CKF_SERIAL_SESSION = 0x00000004
CKM_SHA256_RSA_PKCS = 0x00000040


class Pkcs11Error(RuntimeError):
    """Uma chamada PKCS#11 devolveu erro (nunca crash — crash mata o processo
    antes de chegar aqui)."""


class Modulo:
    """As poucas chamadas do PKCS#11 que este arquivo precisa, direto na DLL
    pelo nome exportado — SEM passar pela tabela `CK_FUNCTION_LIST`, que e
    onde o `PyKCS11` quebrava. Ver o cabecalho do modulo."""

    def __init__(self, caminho: str) -> None:
        carregar = getattr(ctypes, "WinDLL", None)
        if carregar is None:   # fora do Windows o ctypes nem tem WinDLL
            raise Pkcs11Error("o driver nao carregou: o assinador A3 so roda no Windows")
        try:
            self._dll = carregar(caminho)
        except OSError as exc:
            raise Pkcs11Error(f"o driver nao carregou: {exc}") from exc

        def f(nome: str, restype, argtypes):
            try:
                fn = getattr(self._dll, nome)
            except AttributeError as exc:
                raise Pkcs11Error(
                    f"o driver nao exporta a funcao {nome} — nao e um "
                    f"modulo PKCS#11 valido") from exc
            fn.restype = restype
            fn.argtypes = argtypes
            return fn

        self._initialize = f("C_Initialize", CK_RV, [ctypes.c_void_p])
        self._finalize = f("C_Finalize", CK_RV, [ctypes.c_void_p])
        self._get_slot_list = f(
            "C_GetSlotList", CK_RV,
            [CK_BBOOL, ctypes.POINTER(CK_SLOT_ID), ctypes.POINTER(CK_ULONG)])
        self._open_session = f(
            "C_OpenSession", CK_RV,
            [CK_SLOT_ID, CK_FLAGS, ctypes.c_void_p, ctypes.c_void_p,
             ctypes.POINTER(CK_SESSION_HANDLE)])
        self._close_session = f("C_CloseSession", CK_RV, [CK_SESSION_HANDLE])
        self._login = f(
            "C_Login", CK_RV,
            [CK_SESSION_HANDLE, CK_USER_TYPE, ctypes.c_char_p, CK_ULONG])
        self._logout = f("C_Logout", CK_RV, [CK_SESSION_HANDLE])
        self._find_init = f(
            "C_FindObjectsInit", CK_RV,
            [CK_SESSION_HANDLE, ctypes.POINTER(CK_ATTRIBUTE), CK_ULONG])
        self._find = f(
            "C_FindObjects", CK_RV,
            [CK_SESSION_HANDLE, ctypes.POINTER(CK_OBJECT_HANDLE), CK_ULONG,
             ctypes.POINTER(CK_ULONG)])
        self._find_final = f("C_FindObjectsFinal", CK_RV, [CK_SESSION_HANDLE])
        self._get_attr = f(
            "C_GetAttributeValue", CK_RV,
            [CK_SESSION_HANDLE, CK_OBJECT_HANDLE,
             ctypes.POINTER(CK_ATTRIBUTE), CK_ULONG])
        self._sign_init = f(
            "C_SignInit", CK_RV,
            [CK_SESSION_HANDLE, ctypes.POINTER(CK_MECHANISM), CK_OBJECT_HANDLE])
        self._sign = f(
            "C_Sign", CK_RV,
            [CK_SESSION_HANDLE, ctypes.c_char_p, CK_ULONG,
             ctypes.c_void_p, ctypes.POINTER(CK_ULONG)])

        rv = self._initialize(None)
        if rv != CKR_OK:
            raise Pkcs11Error(f"C_Initialize falhou: {_explicar(rv)}")

    def fechar(self) -> None:
        self._finalize(None)

    def slots_com_token(self) -> list[int]:
        conta = CK_ULONG(0)
        rv = self._get_slot_list(CK_BBOOL(1), None, ctypes.byref(conta))
        if rv != CKR_OK:
            raise Pkcs11Error(f"C_GetSlotList falhou: {_explicar(rv)}")
        if not conta.value:
            return []
        vetor = (CK_SLOT_ID * conta.value)()
        rv = self._get_slot_list(CK_BBOOL(1), vetor, ctypes.byref(conta))
        if rv != CKR_OK:
            raise Pkcs11Error(f"C_GetSlotList falhou: {_explicar(rv)}")
        return list(vetor)

    def abrir_sessao(self, slot: int) -> int:
        h = CK_SESSION_HANDLE(0)
        rv = self._open_session(
            CK_SLOT_ID(slot), CK_FLAGS(CKF_SERIAL_SESSION | CKF_RW_SESSION),
            None, None, ctypes.byref(h))
        if rv != CKR_OK:
            raise Pkcs11Error(f"C_OpenSession falhou: {_explicar(rv)}")
        return h.value

    def fechar_sessao(self, sessao: int) -> None:
        self._close_session(CK_SESSION_HANDLE(sessao))

    def login(self, sessao: int, pin: str) -> None:
        pin_bytes = pin.encode("utf-8")
        rv = self._login(CK_SESSION_HANDLE(sessao), CK_USER_TYPE(CKU_USER),
                         pin_bytes, CK_ULONG(len(pin_bytes)))
        if rv != CKR_OK:
            raise Pkcs11Error(f"C_Login falhou: {_explicar(rv)}")

    def logout(self, sessao: int) -> None:
        self._logout(CK_SESSION_HANDLE(sessao))

    def achar_objeto(self, sessao: int, *,
                     classe: int, id_: bytes | None = None) -> int | None:
        # **OS BUFFERS TEM DE FICAR VIVOS ATE A CHAMADA C** — um `CK_ULONG`
        # ou `create_string_buffer` temporario seria coletado pelo GC do
        # Python antes de `C_FindObjectsInit` ler o ponteiro, e o valor lido
        # do outro lado seria lixo. `buffers` os segura.
        buffers: list = []

        classe_buf = CK_ULONG(classe)
        buffers.append(classe_buf)
        campos = [CK_ATTRIBUTE(type=CKA_CLASS,
                               pValue=ctypes.cast(ctypes.pointer(classe_buf),
                                                  ctypes.c_void_p),
                               ulValueLen=ctypes.sizeof(CK_ULONG))]
        if id_ is not None:
            id_buf = ctypes.create_string_buffer(id_, len(id_))
            buffers.append(id_buf)
            campos.append(CK_ATTRIBUTE(
                type=CKA_ID,
                pValue=ctypes.cast(id_buf, ctypes.c_void_p),
                ulValueLen=len(id_)))
        modelo = (CK_ATTRIBUTE * len(campos))(*campos)

        rv = self._find_init(CK_SESSION_HANDLE(sessao), modelo, CK_ULONG(len(campos)))
        if rv != CKR_OK:
            raise Pkcs11Error(f"C_FindObjectsInit falhou: {_explicar(rv)}")
        try:
            achados = (CK_OBJECT_HANDLE * 1)()
            conta = CK_ULONG(0)
            rv = self._find(CK_SESSION_HANDLE(sessao), achados, CK_ULONG(1),
                            ctypes.byref(conta))
            if rv != CKR_OK:
                raise Pkcs11Error(f"C_FindObjects falhou: {_explicar(rv)}")
            return achados[0] if conta.value else None
        finally:
            self._find_final(CK_SESSION_HANDLE(sessao))

    def ler_atributo(self, sessao: int, objeto: int, tipo: int) -> bytes:
        campo = CK_ATTRIBUTE(type=tipo, pValue=None, ulValueLen=0)
        rv = self._get_attr(CK_SESSION_HANDLE(sessao), CK_OBJECT_HANDLE(objeto),
                            ctypes.byref(campo), CK_ULONG(1))
        if rv != CKR_OK or campo.ulValueLen in (0, 0xFFFFFFFF):
            raise Pkcs11Error(
                f"C_GetAttributeValue (tamanho) falhou: {_explicar(rv)}")
        tamanho = campo.ulValueLen
        buf = ctypes.create_string_buffer(tamanho)
        campo2 = CK_ATTRIBUTE(type=tipo,
                              pValue=ctypes.cast(buf, ctypes.c_void_p),
                              ulValueLen=tamanho)
        rv = self._get_attr(CK_SESSION_HANDLE(sessao), CK_OBJECT_HANDLE(objeto),
                            ctypes.byref(campo2), CK_ULONG(1))
        if rv != CKR_OK:
            raise Pkcs11Error(
                f"C_GetAttributeValue (valor) falhou: {_explicar(rv)}")
        return buf.raw[:tamanho]

    def assinar(self, sessao: int, chave: int, mecanismo: int,
               dados: bytes) -> bytes:
        mec = CK_MECHANISM(mechanism=mecanismo, pParameter=None,
                           ulParameterLen=0)
        rv = self._sign_init(CK_SESSION_HANDLE(sessao), ctypes.byref(mec),
                             CK_OBJECT_HANDLE(chave))
        if rv != CKR_OK:
            raise Pkcs11Error(f"C_SignInit falhou: {_explicar(rv)}")
        tamanho = CK_ULONG(0)
        rv = self._sign(CK_SESSION_HANDLE(sessao), dados, CK_ULONG(len(dados)),
                        None, ctypes.byref(tamanho))
        if rv != CKR_OK:
            raise Pkcs11Error(f"C_Sign (tamanho) falhou: {_explicar(rv)}")
        buf = ctypes.create_string_buffer(tamanho.value)
        rv = self._sign(CK_SESSION_HANDLE(sessao), dados, CK_ULONG(len(dados)),
                        ctypes.cast(buf, ctypes.c_void_p), ctypes.byref(tamanho))
        if rv != CKR_OK:
            raise Pkcs11Error(f"C_Sign falhou: {_explicar(rv)}")
        return buf.raw[:tamanho.value]


def _erro(saida_path: str, mensagem: str) -> None:
    # Erro que dá para explicar (PIN errado, driver não achado, sem
    # certificado) grava um arquivo de erro — e não a saída de sucesso.
    # Segfault não passa por aqui: ele mata o processo antes desta linha
    # rodar, e por isso a saída (nem a de erro) nunca aparece.
    with open(saida_path + ".erro", "w", encoding="utf-8") as f:
        json.dump({"erro": mensagem}, f)


def main(entrada_path: str, saida_path: str) -> int:
    with open(entrada_path, "r", encoding="utf-8") as f:
        pedido = json.load(f)

    driver = pedido["driver"]
    pin = pedido["pin"]
    mensagem = base64.b64decode(pedido["mensagem_b64"])

    try:
        modulo = Modulo(driver)
    except Pkcs11Error as exc:
        _erro(saida_path, str(exc))
        return 1

    try:
        slots = modulo.slots_com_token()
        if not slots:
            _erro(saida_path, "nenhum token conectado nesta maquina")
            return 1

        sessao = modulo.abrir_sessao(slots[0])
        try:
            try:
                modulo.login(sessao, pin)
            except Pkcs11Error as exc:
                _erro(saida_path, f"o PIN foi recusado pelo token: {exc}")
                return 1

            try:
                cert_obj = modulo.achar_objeto(sessao, classe=CKO_CERTIFICATE)
                if cert_obj is None:
                    _erro(saida_path, "o token nao tem certificado nenhum")
                    return 1
                cert_der = modulo.ler_atributo(sessao, cert_obj, CKA_VALUE)
                cert_id = modulo.ler_atributo(sessao, cert_obj, CKA_ID)

                chave = modulo.achar_objeto(
                    sessao, classe=CKO_PRIVATE_KEY, id_=cert_id)
                if chave is None:
                    _erro(saida_path,
                          "achei o certificado, e a chave privada "
                          "correspondente nao apareceu no token")
                    return 1

                assinatura = modulo.assinar(
                    sessao, chave, CKM_SHA256_RSA_PKCS, mensagem)
            except Pkcs11Error as exc:
                _erro(saida_path, f"o token recusou assinar: {exc}")
                return 1
        finally:
            modulo.logout(sessao)
            modulo.fechar_sessao(sessao)
    finally:
        modulo.fechar()

    with open(saida_path, "w", encoding="utf-8") as f:
        json.dump({
            "assinatura_b64": base64.b64encode(assinatura).decode("ascii"),
            "certificado_b64": base64.b64encode(cert_der).decode("ascii"),
            "mecanismo": "CKM_SHA256_RSA_PKCS",
        }, f)
    return 0


if __name__ == "__main__":
    # Segfault continua sendo o risco residual (driver de fabricante,
    # totalmente fora do controle deste projeto) — e por isso um `except
    # Exception` aqui não captura o caso que mais importa. Ele existe só
    # para os erros que SÃO exceção (PIN errado, JSON malformado, arquivo
    # ausente, retorno de erro do PKCS#11).
    try:
        codigo = main(sys.argv[1], sys.argv[2])
    except Exception as exc:  # noqa: BLE001 — isolado, e é o próprio contrato
        _erro(sys.argv[2], f"erro inesperado no assinador: {exc}")
        codigo = 1
    sys.exit(codigo)
