# -*- coding: utf-8 -*-
"""Modelos de averbacao RCPN com FORMULARIO PROPRIO (HOTFIX-2026-10-09-04).

Pedido da Debora em 09/10/2026 09:42: "crie um modelo de averbacao, com
formulario proprio, para esse caso da Amanda, deixar pronto para quando vier
mais casos parecidos". O caso-tipo e o termo antigo cujo teor tem ERRO MATERIAL
NA DATA DO REGISTRO (Nair da Silva Garcez, L14 fls 157 termo 13706: o teor
diz "dezoito de abril de dois mil", a data correta e 18/04/2001).

O QUE ESTE MODULO FAZ: so MONTA TEXTO. Nao grava nada, nao lavra e nao sela.
O texto montado vai preenchido para a tela padrao de averbacao
(/rcpn/<id>/averbar), e o escrevente confere, corrige e lanca por la. O selo
sai no lancamento normal, como em qualquer averbacao.

A REDACAO E A DA CASA, medida na averbacao 361 (assento 8318, 24/09/2026,
Elisa): "AVERBACAO 01/629 - RETIFICACAO: Em 24 de Setembro de 2026, apos
requerimento feito pela parte interessada, venho retificar ..., que na epoca
do registro foi gravado erroneamente como sendo X ao inves de Y ... dando
cumprimento ao Artigo 110, §§1º e 3º, da Lei 6.015/1973, retificando o
assento. O referido e verdade e dou fe. Cidade Exemplo/MA, 24/09/2026."

PARA ACRESCENTAR OUTRO MODELO: novo item em MODELOS com `campos` e uma funcao
`montar`. A tela e a rota servem a todos os modelos do catalogo.
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import date, datetime
from typing import Any, Callable

MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro")

FUNDAMENTO_PADRAO = "Artigo 110, §§1º e 3º, da Lei 6.015/1973"
# Vazia desde 09/10/2026 (sanitização): a cidade vem de `settings` —
# ver `cidade_da_casa`.
CIDADE_PADRAO = ""
CHAVE_DA_SESSAO = "rcpn_averbacao_preenchida"


def cidade_da_casa(con: sqlite3.Connection) -> str:
    """«Cidade/UF» desta serventia, de `settings`. Só lê; sem tabela, vazio."""
    try:
        s = dict(con.execute(
            "SELECT key, value FROM settings WHERE key IN ('ri_cidade','ri_uf')").fetchall())
    except sqlite3.Error:
        return CIDADE_PADRAO
    cidade, uf = (s.get("ri_cidade") or "").strip(), (s.get("ri_uf") or "").strip()
    return "/".join(p for p in (cidade, uf) if p) or CIDADE_PADRAO


class ModeloErro(ValueError):
    """Campo obrigatorio ausente ou invalido no formulario do modelo."""


# ------------------------------------------------------------------ datas
def _iso(valor: Any) -> date | None:
    texto = str(valor or "").strip()[:10]
    if not texto:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(texto, fmt).date()
        except ValueError:
            continue
    return None


def data_curta(valor: Any) -> str:
    d = _iso(valor)
    return d.strftime("%d/%m/%Y") if d else ""


def data_por_extenso(valor: Any) -> str:
    """"24 de Setembro de 2026" - o formato da averbacao 361."""
    d = _iso(valor)
    if not d:
        return ""
    return f"{d.day} de {MESES[d.month - 1].capitalize()} de {d.year}"


# ---------------------------------------------------------- sugestoes
def _dados(assento: dict) -> dict:
    try:
        return json.loads(assento.get("dados_json") or "{}") or {}
    except (TypeError, ValueError):
        return {}


def _termo_formatado(numero: Any) -> str:
    try:
        return f"{int(numero):,}".replace(",", ".")
    except (TypeError, ValueError):
        return str(numero or "").strip()


def proximo_numero_av(con: sqlite3.Connection, assento: dict) -> str:
    """"02/13.706": ordem da averbacao / termo. So sugestao - o campo e editavel."""
    n = con.execute(
        "SELECT COUNT(*) FROM rc_atos WHERE assento_id=? "
        "AND tipo IN ('AVERBACAO','RETIFICACAO')", (assento["id"],)).fetchone()[0]
    return f"{int(n) + 1:02d}/{_termo_formatado(assento.get('numero'))}"


def termos_vizinhos(con: sqlite3.Connection, assento: dict, *, raio: int = 6,
                    quantos: int = 2) -> list[dict]:
    """Termos vizinhos da MESMA serie (o termo e continuo por serie), com data de
    registro. O acervo importado grava `livro_volume` vazio: vazio nao exclui;
    livro preenchido e diferente exclui. So LE."""
    try:
        termo = int(assento.get("numero"))
    except (TypeError, ValueError):
        return []
    linhas = con.execute(
        "SELECT numero, data_ato FROM rc_assentos "
        "WHERE serie=? AND (COALESCE(livro_volume,'')='' OR COALESCE(?,'')='' "
        "OR livro_volume=?) "
        "AND numero BETWEEN ? AND ? AND id<>? "
        "AND COALESCE(data_ato,'')<>'' "
        "AND UPPER(COALESCE(situacao,''))<>'CANCELADO' ORDER BY numero",
        (assento.get("serie"), assento.get("livro_volume"), assento.get("livro_volume"),
         termo - raio,
         termo + raio, assento["id"])).fetchall()
    antes = [r for r in linhas if int(r[0]) < termo][-quantos:]
    depois = [r for r in linhas if int(r[0]) > termo][:quantos]
    return [{"termo": int(r[0]), "data": data_curta(r[1])} for r in antes + depois]


def _prova_sugerida(con: sqlite3.Connection, assento: dict) -> str:
    partes = []
    viz = termos_vizinhos(con, assento)
    if viz:
        lista = "; ".join(f"termo {_termo_formatado(v['termo'])}, de {v['data']}"
                          for v in viz)
        partes.append(f"a sequência dos termos vizinhos ({lista})")
    if str(assento.get("especie") or "").upper() == "NASCIMENTO" and assento.get("data_fato"):
        partes.append("a data de nascimento do registrando, "
                      f"{data_curta(assento['data_fato'])}, constante do próprio assento")
    return " e ".join(partes)


# ------------------------------------------------- modelo 1: data do registro
def _sugestoes_data_registro(con: sqlite3.Connection, assento: dict,
                             usuario: dict) -> dict:
    dados = _dados(assento)
    return {
        "numero_av": proximo_numero_av(con, assento),
        "data_como_consta": str(dados.get("data_registro_teor") or "").strip(),
        "data_correta": str(assento.get("data_ato") or "")[:10],
        "requerente_tipo": "oficio",
        "requerente_nome": "",
        "elementos_prova": _prova_sugerida(con, assento),
        "fundamento": FUNDAMENTO_PADRAO,
        "data_averbacao": date.today().isoformat(),
        "cidade": cidade_da_casa(con),
        "subscritor_nome": usuario.get("nome") or "",
        "subscritor_funcao": usuario.get("funcao") or "",
    }


def _montar_data_registro(v: dict, assento: dict) -> dict:
    faltam = [rot for chave, rot in (
        ("numero_av", "Número da averbação"),
        ("data_como_consta", "Data do registro como consta"),
        ("data_correta", "Data correta do registro"),
        ("elementos_prova", "Elementos de prova"),
        ("fundamento", "Fundamento legal"),
        ("data_averbacao", "Data da averbação"),
        ("subscritor_nome", "Quem subscreve"),
    ) if not str(v.get(chave) or "").strip()]
    if v.get("requerente_tipo") == "parte" and not str(v.get("requerente_nome") or "").strip():
        faltam.append("Nome do requerente")
    if faltam:
        raise ModeloErro("Preencha: " + ", ".join(faltam) + ".")
    correta, dav = _iso(v["data_correta"]), _iso(v["data_averbacao"])
    if not correta:
        raise ModeloErro("Data correta do registro inválida.")
    if not dav:
        raise ModeloErro("Data da averbação inválida.")
    if v.get("requerente_tipo") == "parte":
        abertura = ("após requerimento feito pela parte interessada, "
                    f"{v['requerente_nome'].strip()}")
    else:
        abertura = ("de ofício, por se tratar de erro que não exige qualquer "
                    "indagação para a constatação imediata de necessidade de sua correção")
    sub = v["subscritor_nome"].strip()
    funcao = str(v.get("subscritor_funcao") or "").strip()
    assinatura = f"Eu, {sub}, {funcao}, o subscrevi." if funcao else f"Eu, {sub}, o subscrevi."
    teor = (
        f"AVERBAÇÃO {v['numero_av'].strip()} – RETIFICAÇÃO: Em {data_por_extenso(dav)}, "
        f"{abertura}, venho retificar A DATA DO REGISTRO deste assento, que na época "
        f"do registro foi grafada erroneamente como sendo “{v['data_como_consta'].strip()}” "
        f"ao invés de {data_por_extenso(correta)} ({data_curta(correta)}), conforme "
        f"{v['elementos_prova'].strip().rstrip('.')}; diante disto faço constar a data "
        f"correta do registro, dando cumprimento ao {v['fundamento'].strip()}, "
        f"retificando o assento. O referido é verdade e dou fé. "
        f"{(v.get('cidade') or CIDADE_PADRAO).strip()}, {data_curta(dav)}. {assinatura}"
    )
    return {"teor": teor,
            "fundamento": f"Art. 110 da Lei 6.015/1973 - erro na data do registro "
                          f"(de “{v['data_como_consta'].strip()}” para {data_curta(correta)})",
            "natureza": "retificacao"}


CAMPOS_DATA_REGISTRO: tuple[dict, ...] = (
    {"nome": "numero_av", "rotulo": "Número da averbação", "tipo": "text",
     "ajuda": "ordem/termo, ex.: 01/13.706"},
    {"nome": "data_como_consta", "rotulo": "Data do registro como consta no termo",
     "tipo": "text", "ajuda": "copie como está no papel, ex.: dezoito de abril de dois mil"},
    {"nome": "data_correta", "rotulo": "Data correta do registro", "tipo": "date",
     "ajuda": ""},
    {"nome": "elementos_prova", "rotulo": "Elementos de prova", "tipo": "textarea",
     "ajuda": "termos vizinhos do mesmo livro, DNV, documento apresentado etc."},
    {"nome": "requerente_tipo", "rotulo": "Requerente", "tipo": "select",
     "opcoes": (("oficio", "De ofício (o próprio cartório)"),
                ("parte", "A requerimento da parte interessada")), "ajuda": ""},
    {"nome": "requerente_nome", "rotulo": "Nome do requerente (se for a parte)",
     "tipo": "text", "ajuda": ""},
    {"nome": "fundamento", "rotulo": "Fundamento legal", "tipo": "text",
     "ajuda": "padrão da casa"},
    {"nome": "data_averbacao", "rotulo": "Data da averbação", "tipo": "date", "ajuda": ""},
    {"nome": "cidade", "rotulo": "Cidade do fecho", "tipo": "text", "ajuda": ""},
    {"nome": "subscritor_nome", "rotulo": "Quem subscreve", "tipo": "text", "ajuda": ""},
    {"nome": "subscritor_funcao", "rotulo": "Função de quem subscreve", "tipo": "text",
     "ajuda": "ex.: Escrevente Autorizada"},
)

MODELOS: dict[str, dict] = {
    "retificacao-data-registro": {
        "slug": "retificacao-data-registro",
        "nome": "Retificação — erro na data do registro",
        "descricao": ("Termo antigo com erro material na data do registro "
                      "(art. 110 da Lei 6.015/1973). Ex.: teor diz «dois mil» e o "
                      "registro é de 2001."),
        "especies": ("NASCIMENTO", "CASAMENTO", "OBITO"),
        "campos": CAMPOS_DATA_REGISTRO,
        "sugestoes": _sugestoes_data_registro,
        "montar": _montar_data_registro,
    },
}


# ------------------------------------------------------------- publico
def listar(especie: Any = "") -> list[dict]:
    esp = str(especie or "").strip().upper()
    return [{"slug": m["slug"], "nome": m["nome"], "descricao": m["descricao"]}
            for m in MODELOS.values() if not esp or esp in m["especies"]]


def modelo(slug: str) -> dict:
    m = MODELOS.get(str(slug or ""))
    if not m:
        raise ModeloErro("Modelo de averbação desconhecido.")
    return m


def sugestoes(con: sqlite3.Connection, slug: str, assento: dict,
              usuario: dict | None = None) -> dict:
    return modelo(slug)["sugestoes"](con, assento, usuario or {})


def valores_do_formulario(slug: str, form: Any) -> dict:
    return {c["nome"]: str(form.get(c["nome"]) or "").strip()
            for c in modelo(slug)["campos"]}


def montar(slug: str, valores: dict, assento: dict) -> dict:
    m = modelo(slug)
    esp = str(assento.get("especie") or "").upper()
    if esp not in m["especies"]:
        raise ModeloErro(f"Este modelo não serve para assento de {esp or '?'}.")
    return m["montar"](valores, assento)
