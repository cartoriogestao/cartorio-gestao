"""Trava da produção — o que a suíte e as ferramentas não podem apagar.

Em 11/11/2026 um pytest herdou `CG_PG_SCHEMA=producao` e `CG_TEST_BACKEND=pg`.
`schema_do_caminho` devolve esse nome para qualquer arquivo, e o conftest
executou `DROP SCHEMA producao`. O papel do banco é dono do schema e não é
superusuário: o `DROP` passou; o `SET session_replication_role` não.

A reserva no Mac também usa a porta 5434 e o schema `producao`, de propósito
(`reserva.env`). Lá `CG_MODO_RESERVA=1` e o destino é o loopback: o `montar`
precisa poder recriar a reserva. No Windows, 127.0.0.1:5434 é a produção.
"""
from __future__ import annotations

import os
import re
from urllib.parse import unquote, urlparse

PORTA_DA_PRODUCAO = 5434
SCHEMAS_PROTEGIDOS = frozenset({"producao", "public"})


class ProducaoProtegida(RuntimeError):
    """A operação apagaria ou recriaria o banco da casa."""


def _modo_reserva() -> bool:
    return (os.environ.get("CG_MODO_RESERVA") or "").strip() == "1"


def _loopback(host: str) -> bool:
    return host.lower() in {"", "localhost", "127.0.0.1", "::1"}


def host_e_porta(dsn: str) -> tuple[str, int | None]:
    """Host e porta de uma conexão libpq ou URL, sem devolver usuário nem senha."""
    texto = (dsn or "").strip()
    if not texto:
        return "", None
    if "://" in texto:
        uri = urlparse(texto)
        return (uri.hostname or "").lower(), uri.port
    partes: dict[str, str] = {}
    for item in re.split(r"\s+", texto):
        if "=" not in item:
            continue
        chave, _, valor = item.partition("=")
        partes[chave.strip().lower()] = unquote(valor.strip().strip("'\""))
    host = (partes.get("host") or partes.get("hostaddr") or "").lower()
    bruto = partes.get("port") or ""
    try:
        porta = int(bruto) if bruto else None
    except ValueError:
        porta = None
    return host, porta


def schema_protegido(schema: str) -> bool:
    return (schema or "").strip().lower() in SCHEMAS_PROTEGIDOS


def porta_da_producao(dsn: str) -> bool:
    _, porta = host_e_porta(dsn)
    return porta == PORTA_DA_PRODUCAO


def reserva_local(dsn: str) -> bool:
    """O destino é o PostgreSQL da reserva neste Mac (loopback, porta 5434, modo reserva)."""
    host, _ = host_e_porta(dsn)
    return _modo_reserva() and _loopback(host) and porta_da_producao(dsn)


def mesmo_servidor(a: str, b: str) -> bool:
    ha, pa = host_e_porta(a)
    hb, pb = host_e_porta(b)
    if not ha or not hb or pa is None or pb is None:
        return False
    return ha == hb and pa == pb


def exigir_schema_de_teste(schema: str) -> None:
    """A suíte só segue sem schema fixo, ou com um schema `cg_…`.

    Vazio é o caminho normal: cada teste ganha `cg_` mais o hash do arquivo
    temporário. `producao` é a recusa que faltou em 11/11/2026.
    """
    nome = (schema or "").strip()
    if not nome:
        return
    if nome.lower() == "producao" or not nome.startswith("cg_"):
        raise ProducaoProtegida(
            f"a suíte não roda com CG_PG_SCHEMA={nome}: "
            "só um schema de teste (cg_…) ou nenhum")


def exigir_schema_descartavel(schema: str, *, origem: str) -> None:
    """DROP, DELETE em massa e `session_replication_role` só em schema `cg_…`."""
    nome = (schema or "").strip()
    if nome.lower() == "producao" or not nome.startswith("cg_"):
        raise ProducaoProtegida(
            f"{origem}: recuso apagar ou recriar o schema {nome or '(vazio)'}")


def recusar_montar(local: str, principal: str, schema: str) -> None:
    """`montar` recria o schema no DESTINO. O destino não pode ser o principal."""
    if mesmo_servidor(local, principal):
        raise ProducaoProtegida(
            "montar: o destino é o mesmo servidor do principal")
    if reserva_local(local):
        return
    if schema_protegido(schema) or porta_da_producao(local):
        raise ProducaoProtegida(
            "montar: recuso apagar schema na porta 5434 da produção "
            f"(schema {schema or '(nenhum)'})")


def recusar_migrar(schema: str, dsn: str) -> None:
    """A migração com `--recriar` não recria a produção nem a porta 5434 dela."""
    if schema_protegido(schema) or porta_da_producao(dsn):
        raise ProducaoProtegida(
            "migrar: recuso recriar o schema "
            f"{schema or '(nenhum)'} na porta 5434 da produção")


def recusar_emergencia_no_principal(local: str, principal: str) -> None:
    """O botão de emergência desliga a assinatura e despeja a RESERVA, não o principal."""
    if mesmo_servidor(local, principal):
        raise ProducaoProtegida(
            "emergencia: a conexão local é a do principal")
    if not reserva_local(local) and porta_da_producao(local):
        raise ProducaoProtegida(
            "emergencia: a porta 5434 sem CG_MODO_RESERVA=1 é a produção")
