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


# ------------------------------------------ o texto comum aos dois modelos
# A redação é a do precedente medido (relato #127, 15/10/2026): averbações 361,
# 431 e 433 desta casa e as três do E-Ofício guardadas em `tbCN_Generica`
# («AV 01/6.412», «AV-01/18.042»). Todas dizem «venho retificar X, que na época
# do registro foi grafado erroneamente como sendo “Y” ao invés de Z», e todas
# fecham com o Artigo 110 e «retificando o assento». O modelo da data (09/10) e o
# genérico de erro material montam por AQUI, para não haver duas redações da
# mesma averbação divergindo no primeiro conserto.
_PARTICIPIO = {"A": "foi grafada", "AS": "foram grafadas",
               "O": "foi grafado", "OS": "foram grafados"}

ABERTURA_DE_OFICIO = ("de ofício, por se tratar de erro que não exige qualquer "
                      "indagação para a constatação imediata de necessidade de sua correção")


def _sem_aspas(texto: Any) -> str:
    return str(texto or "").strip().strip("“”\"«»'").strip()


def _participio(campo: str) -> str | None:
    """A concordância sai do artigo que o escrevente escreveu («A DATA», «O NOME»).
    Sem artigo não se adivinha o gênero: o texto usa «constou», que não concorda."""
    primeira = (campo.split() or [""])[0].upper()
    return _PARTICIPIO.get(primeira)


def _uma_correcao(c: dict, *, na_lista: bool) -> str:
    campo = str(c["campo"]).strip().upper()
    # Os dois valores entre aspas — decisão do oficial, 15/10/2026 (relato #127):
    # «grafado erroneamente como sendo “Y” ao invés de “Z”».
    errado, correto = _sem_aspas(c["errado"]), _sem_aspas(c["correto"])
    part = _participio(campo)
    if na_lista:
        if part:
            return (f"{campo}, {part.split(' ', 1)[1]} erroneamente como sendo "
                    f"“{errado}” ao invés de “{correto}”")
        return f"{campo}, que constou erroneamente como “{errado}” ao invés de “{correto}”"
    if part:
        return (f"{campo} deste assento, que na época do registro {part} erroneamente "
                f"como sendo “{errado}” ao invés de “{correto}”")
    return (f"{campo} deste assento, que na época do registro constou erroneamente "
            f"como “{errado}” ao invés de “{correto}”")


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
        return "RETIFICAÇÃO " + partes[0]
    return "RETIFICAÇÃO " + ", ".join(partes[:-1]) + " E " + partes[-1]


def _abertura(v: dict) -> str:
    if v.get("requerente_tipo") == "parte":
        txt = ("após requerimento feito pela parte interessada, "
               f"{str(v.get('requerente_nome') or '').strip()}")
        dreq = _iso(v.get("data_requerimento"))
        return txt + (f", em {data_curta(dreq)}" if dreq else "")
    return ABERTURA_DE_OFICIO


def _teor_retificacao(v: dict, correcoes: list[dict], *, provas: str = "",
                      constar: str = "a redação correta") -> str:
    """Monta o teor da averbação de retificação (art. 110) para uma ou mais correções.
    Só monta texto; quem confere e lança é o escrevente, na tela padrão."""
    dav = _iso(v["data_averbacao"])
    if len(correcoes) == 1:
        miolo = "venho retificar " + _uma_correcao(correcoes[0], na_lista=False)
    else:
        itens = [_uma_correcao(c, na_lista=True) for c in correcoes]
        miolo = ("venho retificar os seguintes elementos deste assento, que na época do "
                 "registro constaram com erro: " + "; ".join(itens[:-1]) + "; e " + itens[-1])
    provas = str(provas or "").strip().rstrip(".")
    sub = str(v["subscritor_nome"]).strip()
    funcao = str(v.get("subscritor_funcao") or "").strip()
    assinatura = f"Eu, {sub}, {funcao}, o subscrevi." if funcao else f"Eu, {sub}, o subscrevi."
    return (
        f"AVERBAÇÃO {str(v['numero_av']).strip()} – {_titulo(correcoes)}: "
        f"Em {data_por_extenso(dav)}, "
        f"{_abertura(v)}, {miolo}"
        f"{', conforme ' + provas if provas else ''}; diante disto faço constar {constar}, "
        f"dando cumprimento ao {str(v['fundamento']).strip()}, retificando o assento. "
        f"O referido é verdade e dou fé. "
        f"{(v.get('cidade') or CIDADE_PADRAO).strip()}, {data_curta(dav)}. {assinatura}"
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
    # Desde 15/10/2026 (relato #127) este modelo é um caso pronto do genérico de
    # erro material: uma correção só, «A DATA DO REGISTRO». Saiu letra por letra
    # igual ao de 09/10 até a decisão do oficial do mesmo dia 15/10: o título
    # passou a «RETIFICAÇÃO DA DATA DO REGISTRO» e a data correta, a ir entre
    # aspas. O teste que compara a frase inteira guarda a forma nova.
    v = dict(v, data_requerimento="")
    correcao = {"campo": "A DATA DO REGISTRO", "errado": v["data_como_consta"],
                "correto": f"{data_por_extenso(correta)} ({data_curta(correta)})"}
    teor = _teor_retificacao(v, [correcao], provas=v["elementos_prova"],
                             constar="a data correta do registro")
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
        "fundamento": FUNDAMENTO_PADRAO,
        "data_averbacao": date.today().isoformat(),
        "cidade": cidade_da_casa(con),
        "subscritor_nome": usuario.get("nome") or "",
        "subscritor_funcao": usuario.get("funcao") or "",
    }


def _montar_erro_material(v: dict, assento: dict) -> dict:
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
    teor = _teor_retificacao(v, correcoes, provas=str(v.get("documentos") or ""))
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


def montar(slug: str, valores: dict, assento: dict) -> dict:
    m = modelo(slug)
    esp = str(assento.get("especie") or "").upper()
    if esp not in m["especies"]:
        raise ModeloErro(f"Este modelo não serve para assento de {esp or '?'}.")
    return m["montar"](valores, assento)
