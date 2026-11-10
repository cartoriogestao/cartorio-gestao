"""Orquestração estreita do Malote: fila, responsáveis e estado, sem segredo."""
from __future__ import annotations

import json
import re
from datetime import datetime

import automacao as AU
from bd_nativo import banco

CODIGO = "MALOTE_CIENCIA_DIARIA"
ROTAS = ("RI_NOTAS", "RI_NOTAS_MANUAL", "DIGITALIZACAO", "RCPN", "PROTESTO_LIVRO_E")
CONFIG = "malote_distribuicao"
SCHEMA = """CREATE TABLE IF NOT EXISTS mt_pedidos_locais (
    chave TEXT PRIMARY KEY,
    processo_id bigint NOT NULL REFERENCES au_processos(id),
    usuario_id bigint NOT NULL REFERENCES users(id),
    anterior bigint NOT NULL,
    criado_em TEXT NOT NULL
)"""


class FluxoMaloteError(ValueError):
    """Recusa da fila ou da distribuição, pronta para a tela."""


def init_schema(con) -> None:
    banco(con).escrever(SCHEMA)


def distribuicao(con) -> dict:
    bruto = banco(con).valor("SELECT value FROM settings WHERE key=%s", (CONFIG,))
    try:
        valor = json.loads(bruto or "{}")
        return valor if isinstance(valor, dict) else {}
    except (TypeError, ValueError):
        return {}


def conferir_distribuicao(con, valor: dict | None = None) -> dict:
    valor = distribuicao(con) if valor is None else valor
    ativos = {int(r["id"]) for r in banco(con).ler("SELECT id FROM users WHERE active=1")}
    saida = {}
    for rota in ROTAS:
        r = valor.get(rota) or {}
        try:
            principal, substituto = int(r.get("principal") or 0), int(r.get("substituto") or 0)
        except (ValueError, TypeError):
            raise FluxoMaloteError("Confira o responsável e o substituto de " + rota + ".") from None
        if principal not in ativos or substituto not in ativos or principal == substituto:
            raise FluxoMaloteError("Escolha pessoas ativas e distintas para " + rota + ".")
        saida[rota] = {"principal": principal, "substituto": substituto}
    return saida


def responsaveis(con, resultado: dict) -> tuple[int, int] | None:
    """A IA escolhe atribuição/natureza; a configuração escolhe as pessoas."""
    if not distribuicao(con):
        return None
    setor, natureza = resultado.get("setor"), resultado.get("natureza")
    if natureza == "DIGITALIZACAO":
        rota = "DIGITALIZACAO"
    elif setor == "PROTESTO" or (setor == "RCPN" and natureza == "LIVRO_E"):
        rota = "PROTESTO_LIVRO_E"
    elif setor == "RCPN":
        rota = "RCPN"
    elif setor in {"RI", "RI_QUALIFICACAO", "NOTAS", "NOTAS_QUALIFICACAO"}:
        manual = natureza == "MANUAL" or (not natureza and setor in {"RI", "NOTAS"})
        rota = "RI_NOTAS_MANUAL" if manual else "RI_NOTAS"
    else:
        return None
    r = conferir_distribuicao(con)[rota]
    return r["principal"], r["substituto"]


def pedir(con, *, chave: str, usuario_id: int, usuario: str, modo: str) -> dict:
    """Pedido idempotente e sem alterar ativo/pode_agir. Não executa rede."""
    if modo not in {"consultar", "executar"} or not re.fullmatch(r"[A-Za-z0-9_.:-]{8,80}", chave or ""):
        raise FluxoMaloteError("Pedido do agente local inválido.")
    bd = banco(con)
    bd.travar("malote.pedido.local")
    p = AU.por_codigo(con, CODIGO)
    if not p:
        raise FluxoMaloteError("O processo do Malote não está cadastrado.")
    # Consulta não pode mudar de significado por uma configuração paralela.
    if modo == "consultar" and p["pode_agir"]:
        raise FluxoMaloteError("O processo está autorizado a dar ciência. Use executar para solicitar uma rodada.")
    if modo == "executar":
        if not p["ativo"] or not p["pode_agir"]:
            raise FluxoMaloteError("Ligue o processo e autorize a ciência na tela antes de solicitar a execução.")
        if not p["parametros"].get("triar_recebidos"):
            raise FluxoMaloteError("Configure a triagem dos recebidos antes de executar o fluxo completo.")
        conferir_distribuicao(con)
    key = str(usuario_id) + ":" + chave
    antigo = bd.um("SELECT * FROM mt_pedidos_locais WHERE chave=%s", (key,))
    if antigo:
        return {"pedido": chave, "anterior": int(antigo["anterior"]), "repetido": True}
    if p.get("pedido_manual_em") or bd.um("SELECT id FROM au_execucoes WHERE processo_id=%s AND situacao='RODANDO'", (p["id"],)):
        raise FluxoMaloteError("Há uma rodada pedida ou em execução. Aguarde o resultado antes de pedir outra.")
    anterior = int(bd.valor("SELECT COALESCE(MAX(id),0) FROM au_execucoes WHERE processo_id=%s", (p["id"],)) or 0)
    AU.pedir_rodada(con, p["id"], usuario=usuario)
    bd.escrever("INSERT INTO mt_pedidos_locais (chave,processo_id,usuario_id,anterior,criado_em) VALUES (%s,%s,%s,%s,%s)",
                (key, p["id"], usuario_id, anterior, datetime.now().isoformat(timespec="seconds")))
    return {"pedido": chave, "anterior": anterior, "repetido": False}


def estado(con) -> dict:
    """Estado mínimo para o modelo; sem nomes, conteúdo de documentos ou cofre."""
    p = AU.por_codigo(con, CODIGO)
    if not p:
        return {"versao_fluxo": 1, "processo": None}
    ultimas = AU.execucoes(con, p["id"], limite=10)
    def retrato(e):
        erro = (str(e.get("erro") or "") + " " + str(e.get("relato") or "")).lower()
        return {"id": e["id"], "situacao": e["situacao"], "disparo": e.get("disparo"), "iniciada_em": e["iniciada_em"],
                "terminada_em": e.get("terminada_em"),
                "fluxo_com_triagem": any(isinstance(a, dict) and a.get("acao") == "triagem_malote" and a.get("concluida") for a in e.get("acoes", [])),
                "precisa_mfa": "dois fatores" in erro,
                "cofre_trancado": "cofre" in erro and "trancado" in erro}
    try:
        conferir_distribuicao(con)
        distribuida = True
    except FluxoMaloteError:
        distribuida = False
    return {"versao_fluxo": 1, "processo": {"id": p["id"], "ativo": p["ativo"],
            "pode_agir": p["pode_agir"], "triagem": bool(p["parametros"].get("triar_recebidos")),
            "responsaveis_configurados": distribuida, "pedido_pendente": bool(p.get("pedido_manual_em"))},
            "despachante_parado": AU.batida_do_despachante(con)["parado"],
            "execucoes": [retrato(e) for e in ultimas]}
