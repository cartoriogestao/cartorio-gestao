"""Somente leitura no PRINCIPAL enquanto a reserva assumiu.

Dois servidores gravando dariam o mesmo número duas vezes. O botão de
emergência, se ainda alcança o Windows, marca esta trava. Ela mora fora do
schema publicado (`public.cg_contingencia`), então a réplica não a copia para
o Mac — a reserva precisa continuar podendo gravar depois de promovida.

Sem a tabela, sem o arquivo e sem a variável, nada muda.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

CHAVE = "escrita"
VALOR = "somente_leitura"
AVISO = ("Contingência: este servidor está somente leitura. "
         "Os lançamentos estão na reserva até o oficial mandar a volta.")
FORMULARIOS_QUE_ENTRAM = frozenset({"login", "login_dois_fatores", "logout"})


def bloqueia_escrita(method: str, endpoint: str | None) -> bool:
    """Formulário recusado enquanto a casa está somente leitura. Entrar e sair passam."""
    if method in {"GET", "HEAD", "OPTIONS"}:
        return False
    return endpoint not in FORMULARIOS_QUE_ENTRAM

_CACHE = {"ate": 0.0, "valor": False}


def arquivo() -> Path | None:
    pasta = (os.environ.get("CARTORIO_GESTAO_DATA") or "").strip()
    if not pasta:
        return None
    return Path(pasta) / "somente_leitura"


def pelo_ambiente() -> bool:
    if (os.environ.get("CG_SOMENTE_LEITURA") or "").strip() == "1":
        return True
    marca = arquivo()
    return bool(marca and marca.is_file())


def ativo(db=None) -> bool:
    """O principal não deve gravar? Ambiente e arquivo valem na hora; o banco, por cinco segundos."""
    if pelo_ambiente():
        return True
    agora = time.monotonic()
    if agora < _CACHE["ate"]:
        return bool(_CACHE["valor"])
    valor = False
    if db is not None:
        valor = _no_banco(db)
    _CACHE["ate"] = agora + 5
    _CACHE["valor"] = valor
    return valor


def esquecer() -> None:
    """O teste não herda a leitura do teste anterior."""
    _CACHE["ate"] = 0.0
    _CACHE["valor"] = False


def _no_banco(db) -> bool:
    try:
        with db.connect() as con:
            linha = con.execute(
                "SELECT valor FROM public.cg_contingencia WHERE chave=?",
                (CHAVE,),
            ).fetchone()
    except Exception:  # noqa: BLE001 — tabela ausente é o dia normal
        return False
    if not linha:
        return False
    valor = linha["valor"] if hasattr(linha, "keys") else linha[0]
    return str(valor or "") == VALOR


def sql_de_travar() -> str:
    """O que o botão grava no principal. Idempotente."""
    return (
        "CREATE TABLE IF NOT EXISTS public.cg_contingencia ("
        "chave text PRIMARY KEY, valor text NOT NULL, desde timestamptz NOT NULL DEFAULT now());"
        "\nINSERT INTO public.cg_contingencia(chave, valor) VALUES "
        f"('{CHAVE}', '{VALOR}') ON CONFLICT (chave) DO UPDATE "
        "SET valor = EXCLUDED.valor, desde = now();"
    )


def sql_de_soltar() -> str:
    return f"DELETE FROM public.cg_contingencia WHERE chave = '{CHAVE}';"
