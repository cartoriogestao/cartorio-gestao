"""O PROVEDOR DA NFS-e — quem recebe a DPS e devolve a nota.

POR QUE É UMA CAMADA (LG01, 19/10/2026)
    Hoje a prefeitura usa o EMISSOR NACIONAL (Sefin Nacional / ADN, gov.br/nfse
    — confirmado pelo oficial em 19/10), e é o único provedor que precisa
    funcionar. Mas município troca de sistema por decreto, e o dia em que a
    prefeitura contratar um emissor próprio não pode ser o dia de reescrever o
    caixa. Por isso o resto do sistema só conhece as cinco perguntas daqui —
    emitir, consultar a DPS, consultar a nota, cancelar e baixar o DANFSe — e
    um provedor novo é uma classe a mais em `PROVEDORES`, e mais nada.

O TRANSPORTE É SEPARADO DO PROVEDOR, E ISSO É O QUE PERMITE TESTAR
    O provedor monta o pedido e lê a resposta; quem leva e traz é o
    `transporte` — uma função `(método, endereço, corpo) -> Resposta`. Na
    produção é o HTTPS com o certificado A1 (`transporte_https`, autenticação
    mútua, como a Sefin exige). No teste é um servidor FALSO, na memória, que
    confere a DPS contra o leiaute e nunca abre rede.

O QUE VOLTA COMO ERRO, E O QUE NÃO VOLTA
    `Recusa` é a Sefin dizendo «não» com os códigos dela: o dado está errado e
    reenviar igual não adianta. `Indisponivel` é a rede, o prazo ou o servidor
    fora do ar: a DPS fica na fila e o reenvio é seguro, porque o `Id` dela é
    o mesmo (`nfse_dps.id_da_dps`). **Nenhuma das duas carrega senha, chave
    ou o corpo do pedido** — só o código e a frase curta da resposta.

OS ENDEREÇOS
    Os da documentação técnica do emissor nacional conhecida em 19/10/2026.
    **Conferir no texto oficial (gov.br/nfse → Documentação técnica) antes de
    ligar a produção.** A homologação é a «produção restrita» da Sefin, que não
    gera nota com valor fiscal — e é por ela que a casa começa.
"""
from __future__ import annotations

import base64
import gzip
import json
import re
import secrets
import ssl
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from lxml import etree

import nfse_dps as DPS

NACIONAL = "nacional"

ENDERECOS: dict[str, dict[str, dict[str, str]]] = {
    NACIONAL: {
        "homologacao": {
            "sefin": "https://sefin.producaorestrita.nfse.gov.br/SefinNacional",
            "adn": "https://adn.producaorestrita.nfse.gov.br",
        },
        "producao": {
            "sefin": "https://sefin.nfse.gov.br/SefinNacional",
            "adn": "https://adn.nfse.gov.br",
        },
    },
}

# OS CÓDIGOS DE «ESTA DPS JÁ VIROU NOTA». Conferir na homologação: a casa
# não depende só deles — antes de reenviar uma DPS que já saiu uma vez, ela
# PERGUNTA pela DPS (`consultar_dps`), e só manda de novo se a Sefin não a
# conhece.
CODIGOS_DE_DPS_JA_EMITIDA = frozenset({"E0014"})

PRAZO_SEGUNDOS = 30
LIMITE_DA_MENSAGEM = 300


class ProvedorError(RuntimeError):
    """Falha do provedor, com a frase curta que pode ir à tela e ao rastro."""


class Recusa(ProvedorError):
    """A Sefin recusou. `codigos` traz os códigos dela (E0014...)."""

    def __init__(self, mensagem: str, codigos: tuple[str, ...] = ()):
        super().__init__(mensagem)
        self.codigos = tuple(codigos)

    @property
    def ja_emitida(self) -> bool:
        return bool(CODIGOS_DE_DPS_JA_EMITIDA.intersection(self.codigos))


class Indisponivel(ProvedorError):
    """Rede, prazo ou servidor fora do ar. Reenviar a mesma DPS é seguro."""


@dataclass
class Resposta:
    status: int
    corpo: Any = None             # dict (JSON) ou bytes (PDF)
    tipo: str = ""


Transporte = Callable[[str, str, Any], Resposta]


@dataclass
class Emitida:
    chave: str
    numero: str = ""
    xml: str = ""
    alertas: list[str] = field(default_factory=list)


def _curta(texto: Any) -> str:
    return " ".join(str(texto or "").split())[:LIMITE_DA_MENSAGEM]


def comprimir(xml: bytes) -> str:
    """O XML como a Sefin pede: GZip e Base64."""
    return base64.b64encode(gzip.compress(xml)).decode("ascii")


def descomprimir(texto: str) -> bytes:
    return gzip.decompress(base64.b64decode(texto))


def numero_da_nfse(xml: bytes | str) -> str:
    """O número da NFS-e (`nNFSe`), lido do XML que a Sefin devolveu."""
    if not xml:
        return ""
    try:
        raiz = etree.fromstring(xml.encode("utf-8") if isinstance(xml, str) else xml)
    except etree.XMLSyntaxError:
        return ""
    achado = raiz.find(f".//{{{DPS.NS}}}nNFSe")
    return (achado.text or "").strip() if achado is not None else ""


def _erros(corpo: Any) -> tuple[str, tuple[str, ...]]:
    """Os erros que a Sefin devolve, em frase curta e lista de códigos."""
    if not isinstance(corpo, dict):
        return "", ()
    itens = corpo.get("erros") or corpo.get("Erros") or []
    if isinstance(itens, dict):
        itens = [itens]
    codigos, frases = [], []
    for item in itens if isinstance(itens, list) else []:
        if not isinstance(item, dict):
            continue
        codigo = str(item.get("Codigo") or item.get("codigo") or "").strip()
        frase = str(item.get("Descricao") or item.get("descricao") or "").strip()
        if codigo:
            codigos.append(codigo)
        frases.append(f"{codigo} {frase}".strip())
    return _curta("; ".join(f for f in frases if f)), tuple(codigos)


class ProvedorNacional:
    """O emissor nacional: Sefin Nacional (DPS, eventos) e ADN (DANFSe)."""

    nome = NACIONAL

    def __init__(self, ambiente: str, transporte: Transporte):
        if ambiente not in ENDERECOS[NACIONAL]:
            raise ProvedorError(f"Ambiente desconhecido: «{ambiente}».")
        self.ambiente = ambiente
        self.enderecos = ENDERECOS[NACIONAL][ambiente]
        self._transporte = transporte

    def _chamar(self, metodo: str, url: str, corpo: Any = None) -> Resposta:
        try:
            resposta = self._transporte(metodo, url, corpo)
        except ProvedorError:
            raise
        except (OSError, TimeoutError, ValueError) as erro:
            # O nome da exceção, e não a mensagem: a mensagem do `ssl` pode
            # trazer o caminho do arquivo da chave.
            raise Indisponivel(f"Sem resposta do emissor nacional "
                               f"({type(erro).__name__}).") from erro
        if resposta.status >= 500 or resposta.status in (408, 429):
            raise Indisponivel(f"O emissor nacional respondeu HTTP {resposta.status}. "
                               f"A DPS fica na fila para reenviar.")
        return resposta

    def emitir(self, dps_assinada: bytes) -> Emitida:
        r = self._chamar("POST", f"{self.enderecos['sefin']}/nfse",
                         {"dpsXmlGZipB64": comprimir(dps_assinada)})
        if r.status in (200, 201) and isinstance(r.corpo, dict) and r.corpo.get("chaveAcesso"):
            xml = r.corpo.get("nfseXmlGZipB64") or ""
            texto = descomprimir(xml).decode("utf-8") if xml else ""
            alertas = [_curta(f"{a.get('Codigo', '')} {a.get('Descricao', '')}")
                       for a in (r.corpo.get("alertas") or []) if isinstance(a, dict)]
            return Emitida(chave=str(r.corpo["chaveAcesso"]),
                           numero=numero_da_nfse(texto), xml=texto, alertas=alertas)
        frase, codigos = _erros(r.corpo)
        raise Recusa(frase or f"O emissor nacional recusou a DPS (HTTP {r.status}).",
                     codigos)

    def consultar_dps(self, id_dps: str) -> str | None:
        """A chave da NFS-e que aquela DPS gerou, ou None se não gerou nenhuma."""
        r = self._chamar("GET", f"{self.enderecos['sefin']}/dps/{id_dps}")
        if r.status == 404:
            return None
        if r.status == 200 and isinstance(r.corpo, dict):
            return str(r.corpo.get("chaveAcesso") or "") or None
        frase, codigos = _erros(r.corpo)
        raise Recusa(frase or f"Consulta da DPS recusada (HTTP {r.status}).", codigos)

    def consultar(self, chave: str) -> Emitida:
        r = self._chamar("GET", f"{self.enderecos['sefin']}/nfse/{chave}")
        if r.status == 200 and isinstance(r.corpo, dict):
            xml = r.corpo.get("nfseXmlGZipB64") or ""
            texto = descomprimir(xml).decode("utf-8") if xml else ""
            return Emitida(chave=str(r.corpo.get("chaveAcesso") or chave),
                           numero=numero_da_nfse(texto), xml=texto)
        frase, codigos = _erros(r.corpo)
        raise Recusa(frase or f"Consulta da NFS-e recusada (HTTP {r.status}).", codigos)

    def cancelar(self, chave: str, evento_assinado: bytes) -> None:
        r = self._chamar("POST", f"{self.enderecos['sefin']}/nfse/{chave}/eventos",
                         {"pedidoRegistroEventoXmlGZipB64": comprimir(evento_assinado)})
        if r.status in (200, 201):
            return
        frase, codigos = _erros(r.corpo)
        raise Recusa(frase or f"O cancelamento foi recusado (HTTP {r.status}).", codigos)

    def danfse(self, chave: str) -> bytes:
        r = self._chamar("GET", f"{self.enderecos['adn']}/danfse/{chave}")
        if r.status == 200 and isinstance(r.corpo, (bytes, bytearray)) \
                and bytes(r.corpo[:5]) == b"%PDF-":
            return bytes(r.corpo)
        raise Recusa(f"O DANFSe não veio (HTTP {r.status}).")


PROVEDORES: dict[str, type] = {NACIONAL: ProvedorNacional}


def provedor(nome: str, ambiente: str, transporte: Transporte):
    """O provedor configurado. Nome desconhecido é erro, e não o nacional."""
    classe = PROVEDORES.get(str(nome or "").strip().lower())
    if classe is None:
        raise ProvedorError(f"Provedor de NFS-e desconhecido: «{nome}». "
                            f"Os que existem: {', '.join(sorted(PROVEDORES))}.")
    return classe(ambiente, transporte)


# ------------------------------------------------------------ o HTTPS de verdade

def _contexto_tls(certificado: DPS.CertificadoA1) -> ssl.SSLContext:
    """O TLS com o A1 do lado do cliente — a Sefin autentica pelo certificado.

    O `ssl` só lê chave de ARQUIVO. Ela vai para uma pasta temporária CIFRADA
    com uma senha de uso único, é lida, e a pasta some antes de qualquer
    conexão: a chave do A1 nunca fica em claro no disco.
    """
    from cryptography.hazmat.primitives import serialization

    contexto = ssl.create_default_context()
    senha = secrets.token_urlsafe(24).encode("ascii")
    with tempfile.TemporaryDirectory(prefix="cg_nfse_") as pasta:
        chave = Path(pasta) / "chave.pem"
        cert = Path(pasta) / "cert.pem"
        chave.write_bytes(certificado.chave.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.BestAvailableEncryption(senha)))
        cert.write_bytes(certificado.certificado.public_bytes(serialization.Encoding.PEM))
        contexto.load_cert_chain(str(cert), str(chave), password=senha)
    return contexto


def transporte_https(certificado: DPS.CertificadoA1,
                     prazo: int = PRAZO_SEGUNDOS) -> Transporte:
    """O transporte da produção e da homologação. Abre rede: não roda em teste."""
    contexto = _contexto_tls(certificado)

    def chamar(metodo: str, url: str, corpo: Any = None) -> Resposta:
        dados = json.dumps(corpo).encode("utf-8") if corpo is not None else None
        pedido = urllib.request.Request(url, data=dados, method=metodo, headers={
            "Content-Type": "application/json", "Accept": "application/json, application/pdf"})
        try:
            with urllib.request.urlopen(pedido, timeout=prazo, context=contexto) as r:
                status, tipo, bruto = r.status, r.headers.get("Content-Type", ""), r.read()
        except urllib.error.HTTPError as erro:
            status, tipo, bruto = erro.code, erro.headers.get("Content-Type", ""), erro.read()
        if re.search(r"json", tipo or "", re.I):
            try:
                return Resposta(status, json.loads(bruto.decode("utf-8") or "{}"), tipo)
            except ValueError:
                return Resposta(status, {}, tipo)
        return Resposta(status, bruto, tipo)

    return chamar
