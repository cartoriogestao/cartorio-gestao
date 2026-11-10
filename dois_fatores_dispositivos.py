"""Dispositivos lembrados: comprovante aleatório, revogável, válido por 30 dias.

O banco guarda apenas o hash do comprovante. A senha continua obrigatória.
Não altera o prazo das sessões nem substitui código nas operações de segurança.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets

from bd_nativo import banco

DIAS = 30
SEGUNDOS = DIAS * 24 * 60 * 60
COOKIE = "__Host-cg_dispositivo"
_FORMATO = re.compile(r"[A-Za-z0-9_-]{43}\Z")


def versao(con, uid: int, *, travar: bool = False) -> str:
    """Vincula a autorização à senha, papel e ativação atuais da conta."""
    bd = banco(con)
    if travar:
        bd._escrita()
    linha = bd.um(
        "SELECT u.password_hash, u.role, u.active, d.segredo_cifrado, d.ativado_em "
        "FROM users u JOIN dois_fatores d ON d.user_id = u.id "
        "WHERE u.id = %s AND d.situacao = 'ATIVO'" +
        (" FOR UPDATE OF u, d" if travar else ""), (uid,))
    if not linha or not linha["active"]:
        return ""
    conteudo = json.dumps([str(linha[k]) for k in
                          ("password_hash", "role", "segredo_cifrado", "ativado_em")])
    return hashlib.sha256(conteudo.encode()).hexdigest()


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def emitir(con, uid: int, *, esperada: str, agora: float) -> str:
    """Só após TOTP válido; recusa se a credencial mudou durante a conferência."""
    bd = banco(con)
    atual = versao(con, uid, travar=True)
    if not esperada or atual != esperada:
        return ""
    token = secrets.token_urlsafe(32)
    bd.escrever("DELETE FROM dois_fatores_dispositivos WHERE user_id = %s "
                "AND expira_em <= %s", (uid, agora))
    # Limita o acúmulo: no máximo dez navegadores por conta.
    bd.escrever("DELETE FROM dois_fatores_dispositivos WHERE user_id = %s "
                "AND token_hash NOT IN (SELECT token_hash FROM dois_fatores_dispositivos "
                "WHERE user_id = %s ORDER BY expira_em DESC, token_hash LIMIT 9)", (uid, uid))
    bd.escrever("INSERT INTO dois_fatores_dispositivos "
                "(token_hash, user_id, versao, expira_em) VALUES (%s, %s, %s, %s)",
                (_hash(token), uid, atual, agora + SEGUNDOS))
    return token


def confere(con, uid: int, token: str, *, agora: float, agora_iso: str) -> bool:
    """Só lê. Validade absoluta; o uso não renova os 30 dias."""
    if not isinstance(token, str) or not _FORMATO.fullmatch(token):
        return False
    bd = banco(con)
    atual = versao(con, uid)
    if not atual:
        return False
    return bool(bd.um(
        "SELECT t.token_hash FROM dois_fatores_dispositivos t "
        "JOIN dois_fatores d ON d.user_id = t.user_id "
        "WHERE t.user_id = %s AND t.token_hash = %s AND t.versao = %s "
        "AND t.expira_em > %s AND d.situacao = 'ATIVO' "
        "AND (d.bloqueado_ate = '' OR d.bloqueado_ate <= %s)",
        (uid, _hash(token), atual, agora, agora_iso)))


def revogar(con, uid: int) -> None:
    """Esquece todos os navegadores desta conta, na transação de quem chama."""
    bd = banco(con)
    bd._escrita()
    bd.um("SELECT user_id FROM dois_fatores WHERE user_id = %s FOR UPDATE", (uid,))
    bd.escrever("DELETE FROM dois_fatores_dispositivos WHERE user_id = %s", (uid,))
