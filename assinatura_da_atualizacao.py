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
    não é segredo. Ela mora na pasta do PROGRAMA instalado (que já é de
    confiança), no arquivo `chaves_de_atualizacao.json` ao lado deste módulo, e
    não na pasta de dados, onde quem conseguisse escrever acrescentaria a sua.
    **Lista vazia = modo de transição**: o pacote sem assinatura é aceito, e a
    tela diz que ele não é assinado. Com uma chave cadastrada, pacote sem
    assinatura ou com assinatura que não confere é RECUSADO. **Arquivo de
    chaves que existe e não se lê recusa TODO pacote**: cair no modo de
    transição por um arquivo estragado seria abrir a porta que ele fecha.

A CHAVE É DA INSTALAÇÃO, E NÃO DO CÓDIGO PÚBLICO — 27/10/2026
    Até a 3.7.5 a chave pública de UMA serventia vinha escrita aqui, e quem
    baixasse o projeto do GitHub herdava uma instalação que só aceitava pacote
    assinado por ela. Agora cada instalação cadastra a própria:
    `tools/chave_de_atualizacao.py gerar --saida <pendrive>\\chave.pem
    --instalacao "<pasta do programa>"` grava a pública no arquivo. O pacote
    `.cgu` nunca leva esse arquivo, e por isso nunca o troca.

O QUE ESTE MÓDULO NÃO FAZ
    Não guarda nem lê chave privada de lugar nenhum por conta própria: quem
    assina passa o caminho do arquivo, e a senha é digitada por quem assina.
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

ALGORITMO = "Ed25519"
NOME_NO_PACOTE = "update_manifest.sig.json"

#: O arquivo das chaves públicas aceitas por ESTA instalação — ao lado do código.
ARQUIVO_DAS_CHAVES = Path(__file__).resolve().with_name("chaves_de_atualizacao.json")

# As chaves públicas aceitas, por id → chave pública em base64 (32 bytes crus).
# Preenchidas no fim deste módulo, a partir de `ARQUIVO_DAS_CHAVES`
# (`carregar_chaves_da_instalacao`). Sem arquivo, vazio: modo de transição.
CHAVES_CONFIAVEIS: dict[str, str] = {}
#: Por que o arquivo de chaves não se leu — e, enquanto houver motivo aqui,
#: nenhum pacote é aceito (ver `conferir`).
CHAVES_ILEGIVEIS: str = ""


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
    if chaves is None and CHAVES_ILEGIVEIS:
        raise AssinaturaRecusada(
            f"O arquivo das chaves de atualização desta instalação não se lê "
            f"({CHAVES_ILEGIVEIS}). Nenhum pacote é aceito até ele ser corrigido "
            f"— cadastre a chave de novo com tools/chave_de_atualizacao.py.")
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


# -------------------------------------------- as chaves desta instalação


def carregar_chaves_da_instalacao(arquivo: Path | None = None) -> tuple[dict[str, str], str]:
    """As chaves do arquivo da instalação: `(chaves, motivo_se_ilegivel)`. SÓ LÊ.

    Sem arquivo: `({}, "")` — modo de transição. Arquivo que existe e não se lê,
    ou chave que não é Ed25519 de 32 bytes, ou id que não é o da chave: `({}, motivo)`,
    e `conferir` recusa tudo. Cada id tem de ser o `id_da_chave` da pública que
    ele nomeia — um id trocado à mão faria a tela dizer de quem é a assinatura
    errado.
    """
    arquivo = Path(arquivo or ARQUIVO_DAS_CHAVES)
    if not arquivo.is_file():
        return {}, ""
    try:
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
        if not isinstance(dados, dict) or not isinstance(dados.get("chaves"), dict):
            return {}, "falta o objeto «chaves»"
        saida: dict[str, str] = {}
        for chave_id, publica in dados["chaves"].items():
            crua = base64.b64decode(str(publica), validate=True)
            if len(crua) != 32:
                return {}, f"a chave {chave_id} não tem 32 bytes"
            if id_da_chave(crua) != str(chave_id):
                return {}, f"o id {chave_id} não é o da chave que ele nomeia"
            saida[str(chave_id)] = str(publica)
        return saida, ""
    except (OSError, ValueError) as exc:
        return {}, f"ilegível: {exc}"


def gravar_chave_na_instalacao(chave_id: str, publica: str,
                               arquivo: Path | None = None) -> Path:
    """Acrescenta uma chave pública ao arquivo da instalação. ESCREVE.

    Não apaga as que já estão (troca de chave é acrescentar a nova e, depois,
    tirar a velha à mão). Recusa arquivo que não se lê, em vez de sobrescrevê-lo.
    """
    arquivo = Path(arquivo or ARQUIVO_DAS_CHAVES)
    chaves, motivo = carregar_chaves_da_instalacao(arquivo)
    if motivo:
        raise AssinaturaRecusada(
            f"O arquivo {arquivo} existe e não se lê ({motivo}); conserte-o à "
            f"mão antes de cadastrar outra chave.")
    crua = base64.b64decode(publica, validate=True)
    if len(crua) != 32 or id_da_chave(crua) != chave_id:
        raise AssinaturaRecusada("A chave pública informada não confere com o id.")
    chaves[chave_id] = publica
    arquivo.write_text(json.dumps({"algoritmo": ALGORITMO, "chaves": chaves},
                                  ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
    return arquivo


CHAVES_CONFIAVEIS, CHAVES_ILEGIVEIS = carregar_chaves_da_instalacao()
