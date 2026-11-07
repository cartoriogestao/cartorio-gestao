"""AS CHAVES DA INSTALAÇÃO VÃO PARA A RESERVA — cifradas para ela, pela própria réplica.

O PROBLEMA (07/11/2026)
    A réplica leva o banco, e a sincronia leva a pasta de arquivos. Ficavam de fora os
    segredos da pasta de dados do principal:

        secret.key   assina as sessões e os códigos dos links impressos (lote, pesquisa)
        cofre.key    abre os *.cred
        *.cred       as senhas das integrações e a chave que cifra, NO BANCO, os códigos de
                     acompanhamento dos protocolos (`acompanhamento_cliente`)

    Sem eles, o banco do Mac chega inteiro, mas no dia em que a reserva assume, as integrações
    perdem as senhas e os códigos entregues aos clientes deixam de abrir.

COMO VAI (pedido do oficial: «pela rede, criptografado pelas duas instâncias»)
    - Na instalação, a reserva sorteia um par de chaves X25519. A PRIVADA nunca sai do Mac
      (`CG_RESERVA_CHAVE`, chmod 600). A PÚBLICA vai ao principal no SQL de instalação
      (`settings.reserva_chave_publica`).
    - O principal, de 5 em 5 minutos (`iniciar_vigia`), junta os arquivos, cifra-os PARA a
      pública da reserva e grava o pacote na tabela `reserva_pacote` — só quando algo mudou.
    - A réplica leva a tabela ao Mac como leva qualquer outra (pela conexão SSL).
    - A sincronia do Mac (`tools/reserva.py chaves`) abre o pacote com a privada e grava os
      arquivos na pasta de dados de lá.

O QUE ISTO GARANTE
    O pacote só abre com a privada do Mac. Nem o principal o abre depois de gravado. Quem
    copiar o banco, um backup diário ou o tráfego da réplica leva bytes que não abrem.
    A cifra é ECIES: X25519 com uma chave efêmera por pacote, HKDF-SHA256 e AES-256-GCM.

O QUE NÃO GARANTE
    Quem tem o disco do Mac tem a privada e, portanto, os segredos. É o mesmo de hoje com o
    disco do principal, onde os segredos já moram.
"""
from __future__ import annotations

import base64
import fnmatch
import hashlib
import json
import logging
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

LOG = logging.getLogger("cartorio.reserva_chaves")

CHAVE_PUBLICA = "reserva_chave_publica"   # em settings, no principal
TABELA = "reserva_pacote"
#: Os segredos da pasta de dados que vão. O `pgpass.conf` é do PostgreSQL do Windows (o Mac tem
#: o seu); o certificado `.pfx` fica de fora: assinatura no Mac é outra conversa.
PADROES = ("secret.key", "*.key", "*.cred")
FORA = frozenset({"pgpass.conf"})
#: Rótulo da cifra (dado associado): um pacote de outro uso não abre como este.
ROTULO = b"cartorio-gestao/reserva/pacote/v1"
INTERVALO_S = 300
#: Um arquivo de segredo tem bytes, não megas: o que passar disto não é segredo, e não vai.
TAMANHO_MAXIMO = 1 << 20


# ------------------------------------------------------------------ o par de chaves (Mac)

def gerar_par(caminho: Path) -> str:
    """Sorteia a privada da reserva em `caminho`, se ainda não houver, e devolve a pública."""
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
    from cryptography.hazmat.primitives import serialization as SER
    caminho = Path(caminho)
    if not caminho.exists():
        caminho.parent.mkdir(parents=True, exist_ok=True)
        bruto = X25519PrivateKey.generate().private_bytes(
            SER.Encoding.Raw, SER.PrivateFormat.Raw, SER.NoEncryption())
        fd = os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="ascii") as f:
            f.write(base64.b64encode(bruto).decode("ascii") + "\n")
    return publica_de(caminho)


def _privada(caminho: Path):
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
    bruto = base64.b64decode(Path(caminho).read_text(encoding="ascii").strip())
    return X25519PrivateKey.from_private_bytes(bruto)


def _cru(publica) -> bytes:
    from cryptography.hazmat.primitives import serialization as SER
    return publica.public_bytes(SER.Encoding.Raw, SER.PublicFormat.Raw)


def publica_de(caminho: Path) -> str:
    return base64.b64encode(_cru(_privada(caminho).public_key())).decode("ascii")


def publica_valida(texto: str) -> bool:
    try:
        return len(base64.b64decode(texto, validate=True)) == 32
    except (ValueError, TypeError):
        return False


# ------------------------------------------------------------------ a cifra

def _chave_de_sessao(compartilhado: bytes, efemera: bytes, destino: bytes) -> bytes:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                info=ROTULO + efemera + destino).derive(compartilhado)


def cifrar(arquivos: dict[str, bytes], publica_b64: str) -> str:
    """O pacote: base64 de efêmera(32) + nonce(12) + cifra. Só a privada da reserva abre."""
    from cryptography.hazmat.primitives.asymmetric.x25519 import (X25519PrivateKey,
                                                                   X25519PublicKey)
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    destino = base64.b64decode(publica_b64, validate=True)
    efemera = X25519PrivateKey.generate()
    efemera_cru = _cru(efemera.public_key())
    chave = _chave_de_sessao(efemera.exchange(X25519PublicKey.from_public_bytes(destino)),
                             efemera_cru, destino)
    claro = json.dumps({n: base64.b64encode(b).decode("ascii")
                        for n, b in sorted(arquivos.items())}).encode("utf-8")
    nonce = os.urandom(12)
    return base64.b64encode(efemera_cru + nonce + AESGCM(chave).encrypt(nonce, claro, ROTULO)
                            ).decode("ascii")


def decifrar(pacote: str, privada: Path) -> dict[str, bytes]:
    """Abre o pacote com a privada da reserva. Pacote alterado ou de outra chave: ValueError."""
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PublicKey
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    bruto = base64.b64decode(pacote, validate=True)
    if len(bruto) < 32 + 12 + 16:
        raise ValueError("pacote curto demais")
    efemera, nonce, cifra = bruto[:32], bruto[32:44], bruto[44:]
    minha = _privada(privada)
    chave = _chave_de_sessao(minha.exchange(X25519PublicKey.from_public_bytes(efemera)),
                             efemera, _cru(minha.public_key()))
    try:
        claro = AESGCM(chave).decrypt(nonce, cifra, ROTULO)
    except InvalidTag as erro:
        raise ValueError("o pacote não abre com a chave desta reserva") from erro
    return {n: base64.b64decode(b) for n, b in json.loads(claro).items()}


# ------------------------------------------------------------------ os arquivos

def e_segredo(nome: str) -> bool:
    """O nome é de um segredo que viaja? Só nome simples, sem pasta, e dos padrões."""
    if not nome or nome in FORA or nome != Path(nome).name or nome.startswith("."):
        return False
    return any(fnmatch.fnmatchcase(nome, p) for p in PADROES)


def juntar(pasta: Path) -> dict[str, bytes]:
    """Os segredos da pasta de dados (só o primeiro nível, como o cofre os grava)."""
    pasta = Path(pasta)
    achados: dict[str, bytes] = {}
    if not pasta.is_dir():
        return achados
    for item in sorted(pasta.iterdir()):
        if item.is_file() and not item.is_symlink() and e_segredo(item.name) \
                and item.stat().st_size <= TAMANHO_MAXIMO:
            achados[item.name] = item.read_bytes()
    return achados


def impressao(arquivos: dict[str, bytes], publica_b64: str) -> str:
    """O resumo do que foi cifrado: muda se um arquivo ou a chave da reserva mudar."""
    h = hashlib.sha256(publica_b64.encode("ascii"))
    for nome, conteudo in sorted(arquivos.items()):
        h.update(nome.encode("utf-8") + b"\0" + hashlib.sha256(conteudo).digest())
    return h.hexdigest()


def gravar(pasta: Path, arquivos: dict[str, bytes]) -> list[str]:
    """Grava os segredos na pasta de dados da reserva (chmod 600, troca atômica)."""
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    gravados = []
    for nome, conteudo in sorted(arquivos.items()):
        if not e_segredo(nome):
            LOG.warning("pacote da reserva: %r não é nome de segredo; ignorado", nome)
            continue
        temporario = pasta / f".{nome}.recebendo"
        fd = os.open(temporario, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(conteudo)
        os.replace(temporario, pasta / nome)
        gravados.append(nome)
    return gravados


# ------------------------------------------------------------------ o principal publica

def publicar(db: Any, pasta_dados: Path) -> str:
    """No principal: cifra os segredos para a reserva e grava o pacote, se algo mudou.

    Devolve «sem reserva» (não há chave pública em settings), «em dia» ou «publicado».
    """
    publica = (db.get_setting(CHAVE_PUBLICA, "") or "").strip()
    if not publica:
        return "sem reserva"
    if not publica_valida(publica):
        raise ValueError(f"settings.{CHAVE_PUBLICA} não é uma chave pública X25519")
    arquivos = juntar(pasta_dados)
    resumo = impressao(arquivos, publica)
    from bd_nativo import banco
    with db.transaction() as con:
        bd = banco(con)
        bd.escrever(f"CREATE TABLE IF NOT EXISTS {TABELA} ("
                    "id INTEGER PRIMARY KEY, impressao TEXT NOT NULL, "
                    "pacote TEXT NOT NULL, gerado_em TEXT NOT NULL)")
        atual = bd.um(f"SELECT impressao FROM {TABELA} WHERE id = 1")
        if atual and atual["impressao"] == resumo:
            return "em dia"
        bd.escrever(
            f"INSERT INTO {TABELA}(id, impressao, pacote, gerado_em) VALUES (1, %s, %s, %s) "
            "ON CONFLICT (id) DO UPDATE SET impressao = EXCLUDED.impressao, "
            "pacote = EXCLUDED.pacote, gerado_em = EXCLUDED.gerado_em",
            (resumo, cifrar(arquivos, publica), datetime.now().isoformat(timespec="seconds")))
    LOG.info("reserva: pacote de chaves publicado (%d arquivo(s))", len(arquivos))
    return "publicado"


def iniciar_vigia(db: Any, pasta_dados: Path, intervalo: int = INTERVALO_S) -> threading.Thread:
    """O vigia do principal: publica ao subir e de `intervalo` em `intervalo` segundos.

    Sem a chave da reserva em settings, cada volta é uma leitura de settings e nada mais.
    Falha aqui não derruba o servidor: fica no log e a volta seguinte tenta de novo.
    """
    def volta():
        while True:
            try:
                publicar(db, pasta_dados)
            except Exception:                                    # noqa: BLE001
                LOG.exception("reserva: o pacote de chaves não saiu")
            time.sleep(intervalo)
    t = threading.Thread(target=volta, name="reserva-chaves", daemon=True)
    t.start()
    return t
