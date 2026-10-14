"""A assinatura do pacote de atualização (`.cgu`) — quem o fez, e não só o que ele traz.

POR QUE NÃO BASTA O SHA-256
    O manifesto do `.cgu` já confere cada arquivo pelo SHA-256, e a tela pede o
    SHA-256 do pacote «recebido por um canal separado». Isso prova que o arquivo
    chegou inteiro; **não prova quem o montou**: qualquer um que monte um `.cgu`
    bem formado e diga o SHA-256 dele passa pelas duas conferências. A
    assinatura fecha isso — o pacote só é aceito se foi assinado pela chave
    privada do oficial, que ninguém mais tem (12/10/2026, «quero mais segurança
    nas atualizações»).

COMO
    Ed25519, pela biblioteca `cryptography` que o servidor já tem. O que se
    assina é o **manifesto inteiro, byte a byte** — e o manifesto traz o
    SHA-256 de cada arquivo, que o atualizador já confere um a um. Assinar o
    manifesto é, portanto, assinar o pacote. A assinatura viaja num membro
    próprio do zip (`NOME_NO_PACOTE`), com o id da chave que assinou.

QUEM CONFIA EM QUEM
    `CHAVES_CONFIAVEIS` é a lista das chaves PÚBLICAS aceitas — chave pública
    não é segredo, e mora no código instalado (que já é de confiança), e não na
    pasta de dados, onde quem conseguisse escrever acrescentaria a sua.
    **Lista vazia = modo de transição**: o pacote sem assinatura é aceito, e a
    tela diz que ele não é assinado. Com uma chave cadastrada, pacote sem
    assinatura ou com assinatura que não confere é RECUSADO.

O QUE ESTE MÓDULO NÃO FAZ
    Não guarda nem lê chave privada de lugar nenhum por conta própria: quem
    assina passa o caminho do arquivo, e a senha é digitada por quem assina.
"""
from __future__ import annotations

import base64
import hashlib
import json

ALGORITMO = "Ed25519"
NOME_NO_PACOTE = "update_manifest.sig.json"

# As chaves públicas aceitas, por id → chave pública em base64 (32 bytes crus).
# Vazio até o oficial gerar a sua (`tools/chave_de_atualizacao.py gerar`).
CHAVES_CONFIAVEIS: dict[str, str] = {}


class AssinaturaRecusada(ValueError):
    """O pacote não traz a assinatura que esta instalação exige."""


def _cripto():
    try:
        from cryptography.hazmat.primitives.asymmetric import ed25519
        from cryptography.hazmat.primitives import serialization
    except ImportError as exc:   # pragma: no cover - o servidor tem a biblioteca
        raise AssinaturaRecusada(
            "A biblioteca `cryptography` não está instalada, e sem ela a "
            "assinatura do pacote não se confere. A atualização foi recusada."
        ) from exc
    return ed25519, serialization


def id_da_chave(publica_crua: bytes) -> str:
    """Um nome curto e estável para a chave: o começo do SHA-256 dela."""
    return hashlib.sha256(publica_crua).hexdigest()[:16]


def publica_crua(privada) -> bytes:
    _, serialization = _cripto()
    return privada.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw)


def carregar_privada(pem: bytes, senha: bytes):
    """A chave privada a partir do arquivo PEM cifrado e da senha."""
    ed25519, serialization = _cripto()
    try:
        chave = serialization.load_pem_private_key(pem, password=senha)
    except (ValueError, TypeError) as exc:
        raise AssinaturaRecusada(
            "Não foi possível abrir a chave de assinatura: a senha não confere "
            "ou o arquivo não é uma chave do Cartório Gestão.") from exc
    if not isinstance(chave, ed25519.Ed25519PrivateKey):
        raise AssinaturaRecusada("A chave informada não é Ed25519.")
    return chave


def assinar(manifesto: bytes, privada) -> dict:
    """A assinatura do manifesto, pronta para entrar no pacote."""
    crua = publica_crua(privada)
    return {
        "algoritmo": ALGORITMO,
        "chave": id_da_chave(crua),
        "chave_publica": base64.b64encode(crua).decode("ascii"),
        "assinatura": base64.b64encode(privada.sign(manifesto)).decode("ascii"),
        "manifesto_sha256": hashlib.sha256(manifesto).hexdigest(),
    }


def conferir(manifesto: bytes, assinatura_json: bytes | None,
             chaves: dict[str, str] | None = None) -> dict:
    """Confere a assinatura do manifesto contra as chaves confiáveis.

    Devolve `{"situacao": "ASSINADO", "chave": id}` quando confere, ou
    `{"situacao": "NAO_ASSINADO"}` quando não há chave cadastrada e o pacote
    não traz assinatura (o modo de transição). Recusa em todos os outros casos.
    """
    chaves = CHAVES_CONFIAVEIS if chaves is None else chaves
    if assinatura_json is None:
        if chaves:
            raise AssinaturaRecusada(
                "O pacote não é assinado, e esta instalação só aceita pacotes "
                "assinados pelo oficial. Peça o pacote assinado.")
        return {"situacao": "NAO_ASSINADO"}
    try:
        dados = json.loads(assinatura_json.decode("utf-8"))
        algoritmo = dados["algoritmo"]
        chave_id = str(dados["chave"])
        assinatura = base64.b64decode(dados["assinatura"], validate=True)
    except (ValueError, KeyError, TypeError) as exc:
        raise AssinaturaRecusada("A assinatura do pacote está ilegível.") from exc
    if algoritmo != ALGORITMO:
        raise AssinaturaRecusada(f"Algoritmo de assinatura não aceito: {algoritmo}.")
    if not chaves:
        # Assinado, mas a instalação ainda não cadastrou chave nenhuma: a
        # assinatura não pode ser conferida contra quem quer que seja. Não se
        # recusa (é o modo de transição), e não se afirma que é do oficial.
        return {"situacao": "NAO_ASSINADO", "chave": chave_id,
                "observacao": "assinado, mas esta instalação não tem chave "
                              "cadastrada para conferir"}
    if chave_id not in chaves:
        raise AssinaturaRecusada(
            "O pacote foi assinado por uma chave que esta instalação não "
            "reconhece. A atualização foi recusada.")
    ed25519, _ = _cripto()
    try:
        publica = ed25519.Ed25519PublicKey.from_public_bytes(
            base64.b64decode(chaves[chave_id]))
        publica.verify(assinatura, manifesto)
    except Exception as exc:   # InvalidSignature e chave mal cadastrada
        raise AssinaturaRecusada(
            "A assinatura do pacote não confere: ele foi alterado depois de "
            "assinado, ou não foi assinado pelo oficial. A atualização foi "
            "recusada.") from exc
    return {"situacao": "ASSINADO", "chave": chave_id}
