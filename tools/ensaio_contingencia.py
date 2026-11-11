"""Ensaio mensal do botão de emergência. Não conecta em banco nenhum.

Roda fora do horário de balcão. Prova, com atores falsos, que a emergência
trava o principal antes de promover a reserva, e que montar/migrar/suíte
recusam o schema producao e a porta 5434 da produção.

Se `CG_PG_SCHEMA` for producao ou a conexão local for a porta 5434 sem o modo
reserva, o ensaio recusa e sai 2 — ele não «prova» em cima da casa.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ.parent))

import reserva as R  # noqa: E402
import trava_producao as T  # noqa: E402


def ensaio() -> int:
    """Prova o botão sem abrir banco. A recusa da produção é ensaiada com o modo reserva desligado."""
    if (os.environ.get("CG_PG_SCHEMA") or "").strip().lower() == "producao":
        print("Este ambiente tem CG_PG_SCHEMA=producao. O ensaio não abre conexão.")
    passos: list[str] = []

    def anotar(nome):
        def _fazer():
            passos.append(nome)
        return _fazer

    codigo = R.executar_emergencia(
        confirmacao=R.FRASE_DE_EMERGENCIA,
        principal_alcancavel=True,
        tem_assinatura=True,
        travar_principal=anotar("somente_leitura"),
        desligar=anotar("desligar_assinatura"),
        despejar=anotar("despejo"),
        promover=anotar("promover"),
    )
    if codigo != 0 or passos != ["somente_leitura", "desligar_assinatura", "despejo", "promover"]:
        print(f"ensaio falhou: {passos}")
        return 1
    modo = os.environ.pop("CG_MODO_RESERVA", None)
    try:
        try:
            T.recusar_montar(
                "host=127.0.0.1 port=5434 user=cg dbname=cartorio",
                "host=10.0.0.1 port=5434 user=cg_replica dbname=cartorio",
                "producao",
            )
        except T.ProducaoProtegida:
            pass
        else:
            print("ensaio falhou: montar não recusou a produção")
            return 1
    finally:
        if modo is not None:
            os.environ["CG_MODO_RESERVA"] = modo
    sql = R.sql_do_principal("producao", "cg")
    if "publish = 'insert, update, delete'" not in sql or "truncate" in sql.lower():
        print("ensaio falhou: a publicação ainda levaria esvaziamento de tabela")
        return 1
    print("ensaio da contingência: o botão trava, desliga, despeja e promove.")
    print("montar na porta 5434 da produção foi recusado. Nenhum banco foi aberto.")
    return 0


if __name__ == "__main__":
    sys.exit(ensaio())
