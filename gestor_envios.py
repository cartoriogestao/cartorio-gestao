"""O registro do que saiu para cada Central — o que faltava à casa inteira.

Medido em 02/10/2026: nada no sistema dizia o que já tinha ido ao SIRC, à
CENSEC, ao IBGE ou à DOI. Este módulo grava o envio (feito pelo sistema ou pelo
portal da Central) com o protocolo, e é esse registro que faz o achado da
conferência sumir. **Sem protocolo não há registro**: «mandei» sem número não
prova nada numa correição.

CADA CENTRAL TEM A SUA CHAVE, e o formato é conferido aqui, porque a regra que
cobra procura exatamente essa chave — um envio gravado com a chave torta não
apagaria cobrança nenhuma, e ninguém saberia por quê.
"""
from __future__ import annotations

import re
import sqlite3
from datetime import datetime

from bd_nativo import banco
from gestor_schema import init_gestor_schema


class EnvioError(ValueError):
    """Erro de regra, com mensagem pronta para o balcão."""


_REF_ASSENTO = re.compile(r"^rc_(assentos|atos):\d+(:\d{4}-\d{2}-\d{2})?$")
_MES = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

#: central -> (campo que identifica, formato, exemplo)
CENTRAIS = {
    "SIRC": ("referencia", _REF_ASSENTO, "rc_assentos:8266:2026-09-15"),
    "SIRC_CANCELAMENTO": ("referencia", re.compile(r"^rc_assentos:\d+$"),
                          "rc_assentos:1231"),
    "FUNAI": ("referencia", re.compile(r"^rc_assentos:\d+$"), "rc_assentos:8273"),
    "OBITO_TRE": ("competencia", _MES, "2026-09"),
    "OBITO_ME": ("competencia", _MES, "2026-09"),
    "OBITO_RFB": ("competencia", _MES, "2026-09"),
    "OBITO_IIMA": ("competencia", _MES, "2026-09"),
    "JUNTA_MILITAR": ("competencia", _MES, "2026-09"),
    "IBGE": ("competencia", re.compile(r"^\d{4}-T[1-4]$"), "2026-T3"),
    "CENSEC": ("competencia", re.compile(r"^\d{4}-(0[1-9]|1[0-2])-Q[12]$"),
               "2026-09-Q2"),
    "DOI": ("competencia", _MES, "2026-08"),
}
CANAIS = ("API", "PORTAL", "EMAIL", "OFICIO", "MANUAL")


def registrar(con: sqlite3.Connection, central: str, *, protocolo: str,
              registrado_por: str, competencia: str = "",
              referencias: tuple[str, ...] | list[str] = (),
              canal: str = "PORTAL", enviado_em: str = "",
              recibo_caminho: str = "", mensagem: str = "",
              origem: str = "BALCAO") -> list[int]:
    """Grava o envio. Uma linha por referência, para o achado sumir item a item."""
    central = (central or "").strip().upper()
    if central not in CENTRAIS:
        raise EnvioError(f"Central desconhecida: {central!r}.")
    if not (protocolo or "").strip():
        raise EnvioError("Sem protocolo não há registro de envio.")
    if canal not in CANAIS:
        raise EnvioError(f"Canal desconhecido: {canal!r}.")
    if not (registrado_por or "").strip():
        raise EnvioError("Diga quem registra o envio.")
    campo, formato, exemplo = CENTRAIS[central]
    if campo == "referencia":
        refs = [r.strip() for r in referencias if r and r.strip()]
        if not refs:
            raise EnvioError(f"{central} se registra por ato: diga as referências "
                             f"(ex.: {exemplo}).")
        valores = [("", r) for r in refs]
    else:
        valores = [(competencia.strip(), "")]
    for comp, ref in valores:
        alvo = ref or comp
        if not formato.match(alvo):
            raise EnvioError(f"{central}: «{alvo}» fora do formato (ex.: {exemplo}).")
    init_gestor_schema(con)
    agora = datetime.now().isoformat(timespec="seconds")
    ids = []
    bd = banco(con)
    for comp, ref in valores:
        ids.append(bd.escrever(
            """INSERT INTO ge_envios (central, competencia, referencia, canal,
                   protocolo, recibo_caminho, quantos, mensagem, enviado_em,
                   registrado_em, registrado_por, origem)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (central, comp or None, ref or None, canal, protocolo.strip(),
             recibo_caminho or None, len(valores), mensagem or None,
             enviado_em or agora, agora, registrado_por.strip(), origem))[0]["id"])
    con.commit()
    return ids


# ------------------------------------------------- a tela de registrar envios
#
# QUEM REGISTRA NÃO DIGITA A CHAVE. «rc_assentos:8266:2026-09-15» é o que a
# regra procura, e ninguém no balcão escreve isso sem errar; a tela mostra o
# que a conferência cobra e a pessoa marca o que mandou. A chave sai do próprio
# achado — a mesma que a regra vai procurar amanhã.

#: o começo da chave do achado -> a Central em que se registra
CENTRAL_DA_CHAVE = {
    "SIRC": "SIRC", "SIRC_CANC": "SIRC_CANCELAMENTO", "FUNAI": "FUNAI",
    "OBITO_TRE": "OBITO_TRE", "OBITO_ME": "OBITO_ME", "OBITO_RFB": "OBITO_RFB",
    "OBITO_IIMA": "OBITO_IIMA", "JUNTA_MILITAR": "JUNTA_MILITAR",
    "IBGE": "IBGE", "CENSEC": "CENSEC", "DOI": "DOI",
}

NOME_DA_CENTRAL = {
    "SIRC": "SIRC (INSS)", "SIRC_CANCELAMENTO": "SIRC — cancelamento de termo",
    "FUNAI": "FUNAI", "OBITO_TRE": "Óbitos — Justiça Eleitoral",
    "OBITO_ME": "Óbitos — Ministério da Economia", "OBITO_RFB": "Óbitos — Receita Federal",
    "OBITO_IIMA": "Óbitos — Instituto de Identificação do MA",
    "JUNTA_MILITAR": "Óbitos — Junta de Serviço Militar", "IBGE": "IBGE (mapa trimestral)",
    "CENSEC": "CENSEC (quinzena)", "DOI": "DOI (Receita Federal)",
}


def central_da_chave(chave: str) -> tuple[str, str] | None:
    """(central, referência ou competência) de um achado; None se não é envio."""
    prefixo, _, alvo = (chave or "").partition(":")
    central = CENTRAL_DA_CHAVE.get(prefixo)
    return (central, alvo) if central and alvo else None


def _tem_tabela(con, nome: str) -> bool:
    return banco(con).tem_tabela(nome)


def pendentes(con: sqlite3.Connection) -> list[dict]:
    """O que a conferência cobra e se resolve registrando o envio. Só LÊ.

    `ja_registrado` marca o que alguém registrou depois da última rodada: o
    achado só fecha quando a conferência roda de novo, e sem a marca a pessoa
    registraria duas vezes achando que não pegou.
    """
    if not _tem_tabela(con, "ge_achados"):
        return []
    feitos: set[tuple[str, str]] = set()
    if _tem_tabela(con, "ge_envios"):
        for e in banco(con).ler(
                "SELECT central, competencia, referencia FROM ge_envios "
                "WHERE COALESCE(situacao,'') <> 'REJEITADO' ORDER BY id"):
            feitos.add((e["central"], e["referencia"] or e["competencia"] or ""))
    saida = []
    for r in banco(con).ler(
            """SELECT chave, titulo, detalhe, prazo, gravidade, setor FROM ge_achados
                WHERE resolvido_em IS NULL ORDER BY prazo NULLS FIRST, chave"""):
        par = central_da_chave(r["chave"])
        if par is None:
            continue
        central, alvo = par
        saida.append({"chave": r["chave"], "central": central, "alvo": alvo,
                      "titulo": r["titulo"], "detalhe": r["detalhe"], "prazo": r["prazo"],
                      "gravidade": r["gravidade"], "setor": r["setor"],
                      "ja_registrado": (central, alvo) in feitos})
    return saida


def recentes(con: sqlite3.Connection, limite: int = 40) -> list[dict]:
    if not _tem_tabela(con, "ge_envios"):
        return []
    cols = ("central", "competencia", "referencia", "canal", "protocolo",
            "registrado_em", "registrado_por")
    return banco(con).ler(
        f"SELECT {', '.join(cols)} FROM ge_envios ORDER BY id DESC LIMIT %s", (limite,))


def registrar_pelas_chaves(con: sqlite3.Connection, chaves, *, protocolo: str,
                           registrado_por: str, canal: str = "PORTAL",
                           mensagem: str = "") -> int:
    """Registra o envio dos achados marcados. Devolve quantas linhas gravou.

    TUDO SE CONFERE ANTES DE GRAVAR A PRIMEIRA: `registrar` confirma a cada
    chamada, e uma marcação com uma chave torta no meio gravaria metade —
    a pessoa não saberia qual metade.
    """
    if not chaves:
        raise EnvioError("Marque o que foi enviado.")
    por_central: dict[str, list[str]] = {}
    for chave in chaves:
        par = central_da_chave(chave)
        if par is None:
            raise EnvioError(f"«{chave}» não é envio a uma Central.")
        por_central.setdefault(par[0], []).append(par[1])
    if not (protocolo or "").strip():
        raise EnvioError("Sem protocolo não há registro de envio.")
    for central, alvos in por_central.items():
        formato, exemplo = CENTRAIS[central][1], CENTRAIS[central][2]
        for alvo in alvos:
            if not formato.match(alvo):
                raise EnvioError(f"{central}: «{alvo}» fora do formato (ex.: {exemplo}).")
    gravadas = 0
    for central, alvos in por_central.items():
        if CENTRAIS[central][0] == "referencia":
            gravadas += len(registrar(con, central, protocolo=protocolo,
                                      registrado_por=registrado_por, referencias=alvos,
                                      canal=canal, mensagem=mensagem))
        else:
            for comp in alvos:
                gravadas += len(registrar(con, central, protocolo=protocolo,
                                          registrado_por=registrado_por, competencia=comp,
                                          canal=canal, mensagem=mensagem))
    return gravadas
