"""Assinador A3 em PROCESSO ISOLADO — núcleo compartilhado (A3-0/A3-1).

NUNCA importar este arquivo pelo Flask/waitress. Só via:
  python.exe a3_assinador_filho.py <entrada.json> <saida.json>

Reaproveita o padrão medido de crc_a3_assinador.py: ctypes PKCS#11 direto
na DLL (sem PyKCS11). Segfault mata só este processo.

Contrato de entrada (JSON):
  op: "listar" | "assinar_pdf" | "assinar_bytes"
  driver: caminho da DLL (obrigatório)
  pin: só em assinar_* (nunca em argv; o chamador apaga o arquivo)
  mensagem_b64 / pdf_b64: bytes a assinar
  thumbprint: opcional (SHA1 hex do cert DER) para escolher o certificado

Saída de sucesso (JSON):
  listar → {"certificados":[...], "driver": "..."}
  assinar_* → {"cms_b64"|"assinatura_b64", "certificado_b64", "mecanismo",
               "subject", "thumbprint", "formato"}

Erro explicável → saida.json.erro com {"erro": "..."}.
Segfault → nenhum arquivo (o chamador trata).
"""
from __future__ import annotations

import base64
import hashlib
import json
import sys
from typing import Any

# ---------------------------------------------------------------------------
# PKCS#11 via ctypes (cópia do núcleo de crc_a3_assinador — sem PyKCS11)
# ---------------------------------------------------------------------------
import ctypes

CK_BYTE = ctypes.c_ubyte
CK_BBOOL = CK_BYTE
CK_ULONG = ctypes.c_ulong
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

_MOTIVOS: dict[int, str] = {
    CKR_PIN_INCORRECT: "PIN incorreto",
    CKR_PIN_LOCKED: "PIN bloqueado — o token exige desbloqueio",
    CKR_TOKEN_NOT_PRESENT: "o token foi removido durante a operação",
}


def _explicar(rv: int) -> str:
    conhecido = _MOTIVOS.get(rv)
    return f"{conhecido} (código 0x{rv:08X})" if conhecido else f"código 0x{rv:08X}"


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


CKO_CERTIFICATE = 0x00000001
CKO_PRIVATE_KEY = 0x00000003
CKA_CLASS = 0x00000000
CKA_ID = 0x00000102
CKA_VALUE = 0x00000011
CKA_LABEL = 0x00000003
CKU_USER = 0x00000001
CKF_RW_SESSION = 0x00000002
CKF_SERIAL_SESSION = 0x00000004
CKM_SHA256_RSA_PKCS = 0x00000040


class Pkcs11Error(RuntimeError):
    pass


class Modulo:
    def __init__(self, caminho: str) -> None:
        try:
            self._dll = ctypes.WinDLL(caminho)
        except OSError as exc:
            raise Pkcs11Error(f"o driver não carregou: {exc}") from exc

        def f(nome: str, restype, argtypes):
            try:
                fn = getattr(self._dll, nome)
            except AttributeError as exc:
                raise Pkcs11Error(
                    f"o driver não exporta a função {nome} — não é um "
                    f"módulo PKCS#11 válido") from exc
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
        try:
            self._finalize(None)
        except Exception:
            pass

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
        try:
            self._logout(CK_SESSION_HANDLE(sessao))
        except Exception:
            pass

    def achar_objetos(self, sessao: int, *, classe: int,
                      id_: bytes | None = None, limite: int = 32) -> list[int]:
        buffers: list = []
        classe_buf = CK_ULONG(classe)
        buffers.append(classe_buf)
        campos = [CK_ATTRIBUTE(
            type=CKA_CLASS,
            pValue=ctypes.cast(ctypes.pointer(classe_buf), ctypes.c_void_p),
            ulValueLen=ctypes.sizeof(CK_ULONG))]
        if id_ is not None:
            id_buf = ctypes.create_string_buffer(id_, len(id_))
            buffers.append(id_buf)
            campos.append(CK_ATTRIBUTE(
                type=CKA_ID,
                pValue=ctypes.cast(id_buf, ctypes.c_void_p),
                ulValueLen=len(id_)))
        modelo = (CK_ATTRIBUTE * len(campos))(*campos)
        rv = self._find_init(CK_SESSION_HANDLE(sessao), modelo,
                             CK_ULONG(len(campos)))
        if rv != CKR_OK:
            raise Pkcs11Error(f"C_FindObjectsInit falhou: {_explicar(rv)}")
        try:
            achados = (CK_OBJECT_HANDLE * limite)()
            conta = CK_ULONG(0)
            rv = self._find(CK_SESSION_HANDLE(sessao), achados,
                            CK_ULONG(limite), ctypes.byref(conta))
            if rv != CKR_OK:
                raise Pkcs11Error(f"C_FindObjects falhou: {_explicar(rv)}")
            return [achados[i] for i in range(conta.value)]
        finally:
            self._find_final(CK_SESSION_HANDLE(sessao))

    def achar_objeto(self, sessao: int, *, classe: int,
                     id_: bytes | None = None) -> int | None:
        lista = self.achar_objetos(sessao, classe=classe, id_=id_, limite=1)
        return lista[0] if lista else None

    def ler_atributo(self, sessao: int, objeto: int, tipo: int) -> bytes:
        campo = CK_ATTRIBUTE(type=tipo, pValue=None, ulValueLen=0)
        rv = self._get_attr(CK_SESSION_HANDLE(sessao), CK_OBJECT_HANDLE(objeto),
                            ctypes.byref(campo), CK_ULONG(1))
        if rv != CKR_OK or campo.ulValueLen in (0, 0xFFFFFFFF):
            raise Pkcs11Error(
                f"C_GetAttributeValue (tamanho) falhou: {_explicar(rv)}")
        tamanho = campo.ulValueLen
        buf = ctypes.create_string_buffer(tamanho)
        campo2 = CK_ATTRIBUTE(
            type=tipo,
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


# ---------------------------------------------------------------------------
# Certificado / CMS
# ---------------------------------------------------------------------------

def _thumbprint_sha1(cert_der: bytes) -> str:
    return hashlib.sha1(cert_der).hexdigest().upper()


def _subject_do_cert(cert_der: bytes) -> str:
    try:
        from asn1crypto import x509
        cert = x509.Certificate.load(cert_der)
        return cert.subject.human_friendly
    except Exception:
        return "(assunto não lido)"


def _erro(saida_path: str, mensagem: str) -> None:
    with open(saida_path + ".erro", "w", encoding="utf-8") as f:
        json.dump({"erro": mensagem}, f, ensure_ascii=False)


def _escolher_cert(sessao: int, modulo: Modulo,
                   thumbprint: str | None) -> tuple[int, bytes, bytes]:
    """Devolve (handle_cert, cert_der, cka_id)."""
    objs = modulo.achar_objetos(sessao, classe=CKO_CERTIFICATE, limite=32)
    if not objs:
        raise Pkcs11Error("o token não tem certificado nenhum")

    desejado = (thumbprint or "").strip().upper().replace(":", "").replace(" ", "")
    escolhido = None
    cert_der = b""
    cert_id = b""
    for obj in objs:
        try:
            der = modulo.ler_atributo(sessao, obj, CKA_VALUE)
        except Pkcs11Error:
            continue
        tp = _thumbprint_sha1(der)
        if desejado and tp != desejado:
            continue
        try:
            cid = modulo.ler_atributo(sessao, obj, CKA_ID)
        except Pkcs11Error:
            cid = b""
        escolhido = obj
        cert_der = der
        cert_id = cid
        if desejado:
            break
        # sem thumbprint: pega o primeiro
        break

    if escolhido is None:
        raise Pkcs11Error(
            "nenhum certificado no token corresponde ao thumbprint pedido"
            if desejado else "o token não tem certificado nenhum")
    return escolhido, cert_der, cert_id


def _op_listar(modulo: Modulo) -> dict[str, Any]:
    slots = modulo.slots_com_token()
    if not slots:
        return {"certificados": [], "aviso": "nenhum token conectado nesta máquina"}

    certs: list[dict[str, str]] = []
    for slot in slots:
        sessao = modulo.abrir_sessao(slot)
        try:
            objs = modulo.achar_objetos(sessao, classe=CKO_CERTIFICATE, limite=32)
            for obj in objs:
                try:
                    der = modulo.ler_atributo(sessao, obj, CKA_VALUE)
                except Pkcs11Error:
                    continue
                label = ""
                try:
                    label = modulo.ler_atributo(sessao, obj, CKA_LABEL).decode(
                        "utf-8", errors="replace")
                except Exception:
                    pass
                certs.append({
                    "subject": _subject_do_cert(der),
                    "thumbprint": _thumbprint_sha1(der),
                    "label": label,
                    "slot": str(slot),
                })
        finally:
            modulo.fechar_sessao(sessao)
    return {"certificados": certs}


def _op_assinar(modulo: Modulo, pin: str, dados: bytes,
                thumbprint: str | None, *,
                cades_anexado: bool | None = None) -> dict[str, Any]:
    """`cades_anexado` (13/10/2026): None = assinatura crua, como antes;
    True/False = CAdES-BES anexado/destacado — o token assina os ATRIBUTOS
    (`cades.bytes_a_assinar`), e o envelope é conferido antes de sair daqui."""
    if not pin:
        raise Pkcs11Error(
            "digite o PIN do certificado antes de assinar — ele não fica "
            "guardado em lugar nenhum")

    slots = modulo.slots_com_token()
    if not slots:
        raise Pkcs11Error("nenhum token conectado nesta máquina")

    sessao = modulo.abrir_sessao(slots[0])
    try:
        try:
            modulo.login(sessao, pin)
        except Pkcs11Error as exc:
            raise Pkcs11Error(f"o PIN foi recusado pelo token: {exc}") from exc

        try:
            _cert_obj, cert_der, cert_id = _escolher_cert(
                sessao, modulo, thumbprint)
            chave = modulo.achar_objeto(
                sessao, classe=CKO_PRIVATE_KEY,
                id_=cert_id if cert_id else None)
            if chave is None:
                # fallback: primeira chave privada
                chave = modulo.achar_objeto(sessao, classe=CKO_PRIVATE_KEY)
            if chave is None:
                raise Pkcs11Error(
                    "achei o certificado, e a chave privada correspondente "
                    "não apareceu no token")

            if cades_anexado is None:
                assinatura = modulo.assinar(
                    sessao, chave, CKM_SHA256_RSA_PKCS, dados)
            else:
                import cades
                cms_cades = cades.assinar(
                    dados, cert_der,
                    lambda b: modulo.assinar(sessao, chave, CKM_SHA256_RSA_PKCS, b),
                    anexado=cades_anexado)
                assinatura = b""
        except Pkcs11Error:
            raise
        finally:
            modulo.logout(sessao)
    finally:
        modulo.fechar_sessao(sessao)

    if cades_anexado is not None:
        return {
            "cms_b64": base64.b64encode(cms_cades).decode("ascii"),
            "x_signature_b64": base64.b64encode(cms_cades).decode("ascii"),
            "certificado_b64": base64.b64encode(cert_der).decode("ascii"),
            "mecanismo": "CKM_SHA256_RSA_PKCS",
            "subject": _subject_do_cert(cert_der),
            "thumbprint": _thumbprint_sha1(cert_der),
            "formato": "CAdES-BES-anexado" if cades_anexado else "CAdES-BES-destacado",
        }
    out: dict[str, Any] = {
        "assinatura_b64": base64.b64encode(assinatura).decode("ascii"),
        "certificado_b64": base64.b64encode(cert_der).decode("ascii"),
        "mecanismo": "CKM_SHA256_RSA_PKCS",
        "subject": _subject_do_cert(cert_der),
        "thumbprint": _thumbprint_sha1(cert_der),
        "formato": "assinatura_crua",
    }
    return out


def main(entrada_path: str, saida_path: str) -> int:
    with open(entrada_path, "r", encoding="utf-8") as f:
        pedido = json.load(f)

    op = str(pedido.get("op") or "assinar_bytes").strip().lower()
    driver = pedido.get("driver") or ""
    if not driver:
        _erro(saida_path, "driver PKCS#11 não informado")
        return 1

    try:
        modulo = Modulo(driver)
    except Pkcs11Error as exc:
        _erro(saida_path, str(exc))
        return 1

    try:
        if op == "listar":
            resultado = _op_listar(modulo)
            resultado["driver"] = driver
        elif op == "assinar_cades":
            # 13/10/2026: o X-Signature do CCN, e o .p7s de PDF quando pedido
            # assim. O envelope sai CONFERIDO (`cades.assinar` confere antes
            # de devolver) — envelope que não confere não sai do processo.
            b64 = pedido.get("payload_b64") or ""
            if not b64 and pedido.get("payload_utf8"):
                b64 = base64.b64encode(str(pedido["payload_utf8"]).encode("utf-8")).decode("ascii")
            if not b64:
                _erro(saida_path, "nenhum dado para assinar (payload_b64/payload_utf8 vazio)")
                return 1
            resultado = _op_assinar(
                modulo, pedido.get("pin") or "", base64.b64decode(b64),
                pedido.get("thumbprint"),
                cades_anexado=bool(pedido.get("anexado", True)))
            resultado["driver"] = driver
        elif op in ("assinar_pdf", "assinar_bytes"):
            pin = pedido.get("pin") or ""
            if op == "assinar_pdf":
                b64 = pedido.get("pdf_b64") or ""
            else:
                b64 = pedido.get("mensagem_b64") or ""
            if not b64:
                _erro(saida_path, "nenhum dado para assinar (pdf_b64/mensagem_b64 vazio)")
                return 1
            dados = base64.b64decode(b64)
            thumb = pedido.get("thumbprint")
            # O .p7s do PDF passou a ser CAdES-BES anexado (13/10/2026): o
            # envelope de antes assinava o PDF cru e não conferia.
            resultado = _op_assinar(
                modulo, pin, dados, thumb,
                cades_anexado=True if op == "assinar_pdf" else None)
            resultado["driver"] = driver
        else:
            _erro(saida_path, f"operação desconhecida: {op}")
            return 1
    except (Pkcs11Error, ValueError) as exc:      # ValueError: cades.CadesError
        _erro(saida_path, str(exc))
        return 1
    finally:
        modulo.fechar()

    with open(saida_path, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    try:
        codigo = main(sys.argv[1], sys.argv[2])
    except Exception as exc:  # noqa: BLE001 — isolado; contrato do processo
        _erro(sys.argv[2], f"erro inesperado no assinador: {exc}")
        codigo = 1
    sys.exit(codigo)
