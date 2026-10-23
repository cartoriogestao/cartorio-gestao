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

O TEXTO MORA EM `modelos_padrao/rcpn/` DESDE O LF06C (19/10/2026): o papel
`RC_AVERBACAO_RETIFICACAO` e as frases dele como pecas
(`RC_AVERBACAO_RETIFICACAO__de_oficio`, `__uma`, `__assinatura`...), editaveis
na tela de Modelos. Aqui fica a REGRA que escolhe a frase - de oficio ou a
requerimento, uma correcao ou varias, a concordancia pelo artigo digitado - e a
cola entre elas. O texto lancado em `rc_atos.teor` nao muda: ja e da averbacao.
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import date, datetime
from typing import Any, Callable

import rc_textos as TEXTOS
from bd_nativo import banco

MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro")

# O papel no catálogo; as frases são peças dele (`<CHAVE>__<peça>`).
CHAVE_DO_PAPEL = "RC_AVERBACAO_RETIFICACAO"
# Os nomes que guardavam texto até o LF06C e continuam respondendo, pelo
# `__getattr__` do fim do módulo, com o padrão da peça.
_PECAS_DE_ANTES = {"FUNDAMENTO_PADRAO": "RC_AVERBACAO_RETIFICACAO__fundamento",
                   "ABERTURA_DE_OFICIO": "RC_AVERBACAO_RETIFICACAO__de_oficio"}
# Vazia desde 09/10/2026 (sanitização): a cidade vem de `settings` —
# ver `cidade_da_casa`.
CIDADE_PADRAO = ""
CHAVE_DA_SESSAO = "rcpn_averbacao_preenchida"


def cidade_da_casa(con: sqlite3.Connection) -> str:
    """«Cidade/UF» desta serventia, de `settings`. Só lê; sem tabela, vazio."""
    try:
        s = {r["key"]: r["value"] for r in banco(con).ler(
            "SELECT key, value FROM settings WHERE key IN ('ri_cidade','ri_uf') "
            "ORDER BY key")}
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
    n = banco(con).valor(
        "SELECT COUNT(*) FROM rc_atos WHERE assento_id=%s "
        "AND tipo IN ('AVERBACAO','RETIFICACAO')", (assento["id"],))
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
    linhas = banco(con).ler(
        "SELECT numero, data_ato FROM rc_assentos "
        "WHERE serie=%s AND (COALESCE(livro_volume,'')='' OR COALESCE(%s,'')='' "
        "OR livro_volume=%s) "
        "AND numero BETWEEN %s AND %s AND id<>%s "
        "AND COALESCE(data_ato,'')<>'' "
        "AND UPPER(COALESCE(situacao,''))<>'CANCELADO' ORDER BY numero, id",
        (assento.get("serie"), assento.get("livro_volume"), assento.get("livro_volume"),
         termo - raio,
         termo + raio, assento["id"]))
    antes = [r for r in linhas if int(r["numero"]) < termo][-quantos:]
    depois = [r for r in linhas if int(r["numero"]) > termo][:quantos]
    return [{"termo": int(r["numero"]), "data": data_curta(r["data_ato"])}
            for r in antes + depois]


def _prova_sugerida(con: sqlite3.Connection, assento: dict) -> str:
    """A sugestão do campo «Elementos de prova». A frase de cada prova é peça
    do papel; o que entra (vizinhos achados, nascimento com data) é daqui."""
    partes = []
    viz = termos_vizinhos(con, assento)
    if viz:
        lista = "; ".join(_peca("prova_termo", termo=_termo_formatado(v["termo"]),
                                data=v["data"])
                          for v in viz)
        partes.append(_peca("prova_termos_vizinhos", lista=lista))
    if str(assento.get("especie") or "").upper() == "NASCIMENTO" and assento.get("data_fato"):
        partes.append(_peca("prova_data_de_nascimento",
                            data=data_curta(assento["data_fato"])))
    return " e ".join(partes)


# ------------------------------------------ o texto comum aos dois modelos
# A redação é a do precedente medido (relato #127, 15/10/2026): averbações 361,
# 431 e 433 desta casa e as três do E-Ofício guardadas em `tbCN_Generica`
# («AV 01/6.412», «AV-01/18.042»). Todas dizem «venho retificar X, que na época
# do registro foi grafado erroneamente como sendo “Y” ao invés de Z», e todas
# fecham com o Artigo 110 e «retificando o assento». O modelo da data (09/10) e o
# genérico de erro material montam por AQUI, para não haver duas redações da
# mesma averbação divergindo no primeiro conserto. Desde o LF06C essa redação
# mora no papel `RC_AVERBACAO_RETIFICACAO` e nas peças dele.
_PARTICIPIO = {"A": "foi grafada", "AS": "foram grafadas",
               "O": "foi grafado", "OS": "foram grafados"}


def _preencher(texto: str, chave: str, /, **claros: Any) -> str:
    """O texto com os claros preenchidos. Só calcula.

    Claro que o papel não sabe preencher — um ajuste da casa com
    `{nome_do_pai}` — é recusa com o nome do texto, que a tela mostra, e não
    `KeyError` com o cliente no balcão.
    """
    try:
        return texto.format(**claros)
    except (KeyError, IndexError, ValueError) as erro:
        validos = ", ".join("{" + c + "}" for c in claros) or "nenhum"
        raise ModeloErro(
            f"O texto «{chave}» (Administrativo → Modelos) tem um claro que "
            f"este papel não preenche: {erro}. Claros que valem ali: {validos}."
        ) from erro


def _peca(nome: str, /, **claros: Any) -> str:
    """A frase `nome` do papel, com os claros preenchidos. Só lê.

    Sem conexão: dentro de `rc_textos.lendo_da_casa`, que a rota abre com a
    conexão da casa, vale o ajuste da casa; fora dele, o padrão da base. Nem
    as sugestões, que recebem `con`, a passam aqui: ela serve para ler o
    assento, e quem as pede fora da rota (uma ferramenta, um banco montado só
    com `rc_assentos`) não tem a tabela dos modelos para a busca única.
    """
    chave = f"{CHAVE_DO_PAPEL}__{nome}"
    return _preencher(TEXTOS.texto(chave), chave, **claros)


def _sem_aspas(texto: Any) -> str:
    return str(texto or "").strip().strip("“”\"«»'").strip()


def _participio(campo: str) -> str | None:
    """A concordância sai do artigo que o escrevente escreveu («A DATA», «O NOME»).
    Sem artigo não se adivinha o gênero: o texto usa «constou», que não concorda."""
    primeira = (campo.split() or [""])[0].upper()
    return _PARTICIPIO.get(primeira)


def _uma_correcao(c: dict, *, na_lista: bool) -> str:
    """A frase de uma correção: sozinha («venho retificar X deste assento…») ou
    como item da lista de várias («X, grafada erroneamente…»). Sem artigo, a
    peça `…_sem_artigo`, com «constou», que não concorda."""
    campo = str(c["campo"]).strip().upper()
    # Os dois valores entre aspas — decisão do oficial, 15/10/2026 (relato #127):
    # «grafado erroneamente como sendo “Y” ao invés de “Z”».
    valores = {"elemento": campo, "errado": _sem_aspas(c["errado"]),
               "correto": _sem_aspas(c["correto"])}
    part = _participio(campo)
    if na_lista:
        if part:
            return _peca("item", participio=part.split(" ", 1)[1], **valores)
        return _peca("item_sem_artigo", **valores)
    if part:
        return _peca("uma", participio=part, **valores)
    return _peca("uma_sem_artigo", **valores)


_CONTRACAO = {"A": "DA", "AS": "DAS", "O": "DO", "OS": "DOS"}


def _do_elemento(campo: str) -> str:
    """«O NOME DA GENITORA» vira «DO NOME DA GENITORA»; sem artigo, «DE …»."""
    palavras = campo.strip().upper().split()
    if palavras and palavras[0] in _CONTRACAO:
        return " ".join([_CONTRACAO[palavras[0]]] + palavras[1:])
    return " ".join(["DE"] + palavras)


def _titulo(correcoes: list[dict]) -> str:
    """O título diz o que se retifica, como no E-Ofício («RETIFICAÇÃO DO NOME DA
    MÃE DO REGISTRADO», AV-01/18.042) — decisão do oficial, 15/10/2026. Com mais
    de uma correção os elementos se juntam: «… DO NOME DO REGISTRADO E DA DATA DE
    NASCIMENTO»."""
    partes = [_do_elemento(str(c["campo"])) for c in correcoes]
    if len(partes) == 1:
        return _peca("titulo", elementos=partes[0])
    return _peca("titulo", elementos=", ".join(partes[:-1]) + " E " + partes[-1])


def _abertura(v: dict) -> str:
    """De ofício ou a requerimento da parte (com a data, se houver e valer)."""
    if v.get("requerente_tipo") == "parte":
        txt = _peca("a_requerimento",
                    requerente=str(v.get("requerente_nome") or "").strip())
        dreq = _iso(v.get("data_requerimento"))
        return txt + (_peca("data_do_requerimento", data_requerimento=data_curta(dreq))
                      if dreq else "")
    return _peca("de_oficio")


def _teor_retificacao(v: dict, correcoes: list[dict], *, provas: str = "",
                      constar: str | None = None, modelo: str | None = None) -> str:
    """Monta o teor da averbação de retificação (art. 110) para uma ou mais correções.
    Só monta texto; quem confere e lança é o escrevente, na tela padrão.

    `modelo` é o corpo do papel `RC_AVERBACAO_RETIFICACAO` lido pela busca única
    por quem tem a conexão; sem ele, `rc_textos.texto` (o ajuste da casa dentro
    de `lendo_da_casa`, senão o padrão da base). `constar` sem valor é a peça
    «a redação correta»."""
    dav = _iso(v["data_averbacao"])
    if len(correcoes) == 1:
        correcao = _uma_correcao(correcoes[0], na_lista=False)
    else:
        itens = [_uma_correcao(c, na_lista=True) for c in correcoes]
        correcao = _peca("varias", itens="; ".join(itens[:-1]) + "; e " + itens[-1])
    provas = str(provas or "").strip().rstrip(".")
    sub = str(v["subscritor_nome"]).strip()
    funcao = str(v.get("subscritor_funcao") or "").strip()
    assinatura = (_peca("assinatura", subscritor=sub, funcao=funcao) if funcao
                  else _peca("assinatura_sem_funcao", subscritor=sub))
    return _preencher(
        modelo or TEXTOS.texto(CHAVE_DO_PAPEL), CHAVE_DO_PAPEL,
        numero_av=str(v["numero_av"]).strip(),
        titulo=_titulo(correcoes),
        data_por_extenso=data_por_extenso(dav),
        abertura=_abertura(v),
        correcao=correcao,
        conforme=_peca("conforme", provas=provas) if provas else "",
        constar=_peca("constar") if constar is None else constar,
        fundamento=str(v["fundamento"]).strip(),
        cidade=(v.get("cidade") or CIDADE_PADRAO).strip(),
        data=data_curta(dav),
        assinatura=assinatura,
    )


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
        "fundamento": _peca("fundamento"),
        "data_averbacao": date.today().isoformat(),
        "cidade": cidade_da_casa(con),
        "subscritor_nome": usuario.get("nome") or "",
        "subscritor_funcao": usuario.get("funcao") or "",
    }


def _montar_data_registro(v: dict, assento: dict, *, modelo: str | None = None) -> dict:
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
    # Desde 15/10/2026 (relato #127) este modelo é um caso pronto do genérico de
    # erro material: uma correção só, «A DATA DO REGISTRO». Saiu letra por letra
    # igual ao de 09/10 até a decisão do oficial do mesmo dia 15/10: o título
    # passou a «RETIFICAÇÃO DA DATA DO REGISTRO» e a data correta, a ir entre
    # aspas. O teste que compara a frase inteira guarda a forma nova.
    v = dict(v, data_requerimento="")
    correcao = {"campo": "A DATA DO REGISTRO", "errado": v["data_como_consta"],
                "correto": f"{data_por_extenso(correta)} ({data_curta(correta)})"}
    teor = _teor_retificacao(v, [correcao], provas=v["elementos_prova"],
                             constar=_peca("constar_data_registro"), modelo=modelo)
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

# ------------------------------------------- modelo 2: erro material genérico
# Relato #127 (09/10/2026, balcão): «deixar o modelo mais genérico, para caber
# para mais casos de erros materiais». O precedente mostra o que mais se corrige
# nesta casa — sobrenome de genitor e avós (AV 01/6.412), nome da mãe
# (AV-01/18.042, av. 433), naturalidade e genitora numa só averbação (av. 361) —
# e por isso cabe mais de uma correção no mesmo ato.
LINHAS_DE_CORRECAO = 5
LIMITE_DO_FUNDAMENTO = 2000

# Todas as espécies que têm assento a retificar — decisão do oficial, 15/10/2026:
# nascimento, casamento (e o religioso, que é casamento noutro livro), óbito,
# natimorto e as do Livro E. Proclamas fica de fora: é edital, não assento.
ESPECIES_DO_ERRO_MATERIAL = (
    "NASCIMENTO", "CASAMENTO", "CASAMENTO_RELIGIOSO", "OBITO", "NATIMORTO",
    "AUSENCIA", "INTERDICAO", "TUTELA", "EMANCIPACAO", "UNIAO_ESTAVEL",
    "OPCAO_NACIONALIDADE", "OUTRO",
)

# Sugestões da lista do campo. O artigo vai junto porque é dele que sai a
# concordância do texto («foi grafada» / «foi grafado»).
ELEMENTOS_COMUNS = (
    "O NOME DO REGISTRADO", "O NOME DA REGISTRADA", "O SOBRENOME DO REGISTRADO",
    "A DATA DE NASCIMENTO", "A HORA DE NASCIMENTO", "O LOCAL DE NASCIMENTO",
    "A NATURALIDADE", "O SEXO", "O NOME DO GENITOR", "O NOME DA GENITORA",
    "OS NOMES DOS AVÓS PATERNOS", "OS NOMES DOS AVÓS MATERNOS",
    "O NOME DO CÔNJUGE", "A PROFISSÃO", "O ESTADO CIVIL", "O DOMICÍLIO",
    "A DATA DO ÓBITO", "O LOCAL DO ÓBITO", "A DATA DO REGISTRO",
)


def _correcoes_preenchidas(v: dict) -> list[dict]:
    """As linhas com alguma coisa escrita; linha pela metade é recusada dizendo qual."""
    saida, faltas = [], []
    for i, c in enumerate(v.get("correcoes") or [], start=1):
        campo, errado, correto = (str(c.get(k) or "").strip()
                                  for k in ("campo", "errado", "correto"))
        if not (campo or errado or correto):
            continue
        falta = [rot for val, rot in ((campo, "o elemento"), (errado, "onde se lê"),
                                      (correto, "leia-se")) if not val]
        if falta:
            faltas.append(f"correção {i} sem {', '.join(falta)}")
        else:
            saida.append({"campo": campo, "errado": errado, "correto": correto})
    if faltas:
        raise ModeloErro("Complete: " + "; ".join(faltas) + ".")
    return saida


def _sugestoes_erro_material(con: sqlite3.Connection, assento: dict,
                             usuario: dict) -> dict:
    return {
        "numero_av": proximo_numero_av(con, assento),
        "correcoes": [],
        "requerente_tipo": "oficio",
        "requerente_nome": "",
        "data_requerimento": "",
        "documentos": "",
        "fundamento": _peca("fundamento"),
        "data_averbacao": date.today().isoformat(),
        "cidade": cidade_da_casa(con),
        "subscritor_nome": usuario.get("nome") or "",
        "subscritor_funcao": usuario.get("funcao") or "",
    }


def _montar_erro_material(v: dict, assento: dict, *, modelo: str | None = None) -> dict:
    faltam = [rot for chave, rot in (
        ("numero_av", "Número da averbação"),
        ("fundamento", "Fundamento legal"),
        ("data_averbacao", "Data da averbação"),
        ("subscritor_nome", "Quem subscreve"),
    ) if not str(v.get(chave) or "").strip()]
    if v.get("requerente_tipo") == "parte" and not str(v.get("requerente_nome") or "").strip():
        faltam.append("Nome do requerente")
    correcoes = _correcoes_preenchidas(v)
    if not correcoes:
        faltam.append("ao menos uma correção (elemento, onde se lê, leia-se)")
    if faltam:
        raise ModeloErro("Preencha: " + ", ".join(faltam) + ".")
    if not _iso(v["data_averbacao"]):
        raise ModeloErro("Data da averbação inválida.")
    if str(v.get("data_requerimento") or "").strip() and not _iso(v["data_requerimento"]):
        raise ModeloErro("Data do requerimento inválida.")
    teor = _teor_retificacao(v, correcoes, provas=str(v.get("documentos") or ""),
                             modelo=modelo)
    resumo = "; ".join(f"{c['campo'].upper()} (de “{_sem_aspas(c['errado'])}” para "
                       f"“{_sem_aspas(c['correto'])}”)" for c in correcoes)
    fundamento = f"Art. 110 da Lei 6.015/1973 - erro material: {resumo}"
    # Limite largo (decisão do oficial, 15/10/2026): o destino é `rc_atos.fundamento`,
    # TEXT sem tamanho, e o campo da tela de lançamento não tem maxlength — o corte de
    # 300 da primeira versão cortava a quinta correção ao meio.
    if len(fundamento) > LIMITE_DO_FUNDAMENTO:
        fundamento = fundamento[:LIMITE_DO_FUNDAMENTO - 1].rstrip() + "…"
    return {"teor": teor, "fundamento": fundamento, "natureza": "retificacao"}


CAMPOS_ERRO_MATERIAL: tuple[dict, ...] = (
    {"nome": "numero_av", "rotulo": "Número da averbação", "tipo": "text",
     "ajuda": "ordem/termo, ex.: 01/13.706"},
    {"nome": "correcoes", "rotulo": "O que está errado no assento", "tipo": "correcoes",
     "linhas": LINHAS_DE_CORRECAO, "sugestoes": ELEMENTOS_COMUNS,
     "ajuda": "uma linha por correção; escreva o elemento com o artigo (A DATA, O NOME)"},
    {"nome": "requerente_tipo", "rotulo": "Origem", "tipo": "select",
     "opcoes": (("oficio", "De ofício (o próprio cartório)"),
                ("parte", "A requerimento da parte interessada")), "ajuda": ""},
    {"nome": "requerente_nome", "rotulo": "Nome do requerente (se for a parte)",
     "tipo": "text", "ajuda": ""},
    {"nome": "data_requerimento", "rotulo": "Data do requerimento (se houver)",
     "tipo": "date", "ajuda": ""},
    {"nome": "documentos", "rotulo": "Documento comprobatório (opcional)", "tipo": "textarea",
     "ajuda": "ex.: certidão de nascimento da genitora e RG, cujas cópias ficam arquivadas"},
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
    "retificacao-erro-material": {
        "slug": "retificacao-erro-material",
        "nome": "Retificação de erro material (art. 110)",
        "descricao": ("Erro material em qualquer elemento do assento — nome, sobrenome, "
                      "data, local, filiação, avós etc. —, uma ou mais correções na "
                      "mesma averbação (art. 110 da Lei 6.015/1973)."),
        "especies": ESPECIES_DO_ERRO_MATERIAL,
        "campos": CAMPOS_ERRO_MATERIAL,
        "sugestoes": _sugestoes_erro_material,
        "montar": _montar_erro_material,
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


# `montar` recebe `modelo=` (o corpo do papel, como os outros montadores do
# catálogo), e lá dentro esse nome esconde a função acima.
_modelo_do_slug = modelo


def sugestoes(con: sqlite3.Connection, slug: str, assento: dict,
              usuario: dict | None = None) -> dict:
    return modelo(slug)["sugestoes"](con, assento, usuario or {})


def valores_do_formulario(slug: str, form: Any) -> dict:
    valores: dict[str, Any] = {}
    for c in modelo(slug)["campos"]:
        if c["tipo"] == "correcoes":
            # Linhas numeradas (correcao_campo_1, correcao_errado_1, …): a tela
            # devolve todas, inclusive as vazias, para redesenhar o que se digitou.
            valores[c["nome"]] = [
                {k: str(form.get(f"correcao_{k}_{i}") or "").strip()
                 for k in ("campo", "errado", "correto")}
                for i in range(1, int(c.get("linhas") or LINHAS_DE_CORRECAO) + 1)]
        else:
            valores[c["nome"]] = str(form.get(c["nome"]) or "").strip()
    return valores


def montar(slug: str, valores: dict, assento: dict, *,
           modelo: str | None = None) -> dict:
    """O teor, o fundamento e a natureza da averbação. Só calcula.

    `modelo` é o corpo do papel `RC_AVERBACAO_RETIFICACAO` que vale na casa,
    lido por quem tem a conexão; sem ele, o de `rc_textos.texto` — o padrão da
    base, ou o ajuste da casa dentro de `lendo_da_casa`."""
    m = _modelo_do_slug(slug)
    esp = str(assento.get("especie") or "").upper()
    if esp not in m["especies"]:
        raise ModeloErro(f"Este modelo não serve para assento de {esp or '?'}.")
    return m["montar"](valores, assento, modelo=modelo)


def __getattr__(nome: str):
    """Os nomes antigos do texto de fábrica, lidos da base dos padrões.

    O TEXTO SAIU DESTE MÓDULO NO LF06C (19/10/2026) e mora em
    `modelos_padrao/rcpn/`. `FUNDAMENTO_PADRAO` e `ABERTURA_DE_OFICIO` viraram
    peças do papel e respondem o padrão delas; `TEOR_DA_RETIFICACAO` é o nome
    do papel no catálogo. Nome que não é de papel continua `AttributeError`.
    """
    if nome.startswith("__"):
        raise AttributeError(nome)
    import modelos_da_casa as _MODELOS
    if nome in _PECAS_DE_ANTES:
        return _MODELOS.padrao_de(_PECAS_DE_ANTES[nome])
    return _MODELOS.constante_antiga(__name__, nome)
