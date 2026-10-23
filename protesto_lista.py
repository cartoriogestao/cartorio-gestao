"""A lista de títulos do Protesto — o que está PENDENTE, e o próximo passo.

PEDIDO DO OFICIAL, 14/10/2026, primeiro dia do protesto no sistema:
«não consigo ver, filtrar e ordenar os títulos realmente pendentes… preciso
que tudo esteja integrado e seja um fluxo natural o recebimento do título,
intimação, protesto».

A lista genérica das atribuições (`atribuicoes_web._listar`) mostrava os 1.374
títulos do acervo em ordem de `id DESC`, e os 28 que ainda pedem alguma coisa
ficavam afogados entre os 1.346 que já acabaram — medido na produção em
14/10/2026: 28 APONTADOS, 1.100 PROTESTADOS, 190 PAGOS, 56 CANCELADOS.

O QUE ESTE MÓDULO FAZ, E O QUE ELE NÃO FAZ
    Ele LÊ. Separa as vistas (pendentes, encerrados, todos), filtra, ordena,
    pagina e diz o **próximo passo** de cada pendente — e o próximo passo sai
    das funções que já decidem isso noutras telas (`protesto.esperando_protesto`,
    `protesto.sustacao_revogada`, `protesto.sustacao_em_vigor`,
    `protesto_aviso.do_titulo`), e não de regra reescrita aqui.

    **O PRAZO NÃO SE JULGA.** Para o intimado a lista conta os dias desde a
    intimação (`protesto._dias_entre`, a mesma régua da tela «A protestar») e
    oferece o caminho; quem diz se o tríduo venceu é quem assina — decisão do
    oficial de 24/08/2026.

SUSTADO NÃO É SITUAÇÃO, É ORDEM
    `pt_titulos.situacao` não tem SUSTADO: a sustação é ato (`pt_atos`), e vale
    a última palavra do Juízo (sustação × revogação). Por isso o filtro
    «SUSTADO» pergunta pelo ato, e não pela coluna.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta
from typing import Any, Mapping

from bd_nativo import banco
import protesto as PT
import protesto_aviso as AV
from pt_schema import normalizar_nome

# O fluxo em aberto: RECEBIDO -> APONTADO -> INTIMADO. O que passou daí
# acabou para esta lista — o protestado ainda pode ser cancelado, mas isso é
# pedido do devedor, e não trabalho que o cartório tenha de lembrar.
SITUACOES_PENDENTES = ("RECEBIDO", "APONTADO", "INTIMADO")
SITUACOES_ENCERRADAS = ("PROTESTADO", "PAGO", "DESISTIDO", "CANCELADO")

# O FILTRO QUE NÃO É SITUAÇÃO. Fica no mesmo seletor porque o balcão pensa
# nele como situação («está sustado»), mas a consulta pergunta pelo ato.
FILTRO_SUSTADO = "SUSTADO"

VISTAS: dict[str, dict] = {
    "pendentes": {"rotulo": "Pendentes",
                  "situacoes": SITUACOES_PENDENTES},
    "encerrados": {"rotulo": "Encerrados",
                   "situacoes": SITUACOES_ENCERRADAS},
    "todos": {"rotulo": "Todos",
              "situacoes": SITUACOES_PENDENTES + SITUACOES_ENCERRADAS},
}
VISTA_PADRAO = "pendentes"

# AS ORDENS. A expressão é de lista fechada — nada do endereço vira SQL.
# `padrao` é a direção do primeiro clique: o que faz sentido ver primeiro.
ORDENS: dict[str, dict] = {
    "entrada": {"rotulo": "Entrada", "padrao": "asc",
                "sql": "y.data_entrada {d}, y.id {d}"},
    "protocolo": {"rotulo": "Protocolo", "padrao": "asc",
                  "sql": "(y.protocolo IS NULL), y.protocolo {d}, y.id {d}"},
    "devedor": {"rotulo": "Devedor", "padrao": "asc",
                "sql": "(y.devedor_ordem IS NULL), y.devedor_ordem {d}, y.id"},
    "valor": {"rotulo": "Valor", "padrao": "desc",
              "sql": "y.saldo_centavos {d}, y.id"},
    # MAIS DIAS = INTIMAÇÃO MAIS ANTIGA, e por isso a direção se inverte na
    # data. Quem não foi intimado vai para o fim nas duas direções.
    "dias": {"rotulo": "Dias desde a intimação", "padrao": "desc",
             "sql": "(y.data_intimacao IS NULL), y.data_intimacao {inv}, y.id"},
}
ORDEM_PADRAO = {"pendentes": ("entrada", "asc"),
                "encerrados": ("entrada", "desc"),
                "todos": ("entrada", "desc")}

POR_PAGINA = 50

# Uma linha por título, com o que a lista precisa já calculado. É SUBCONSULTA
# e não JOIN: cada título tem um apontamento, várias intimações e vários
# devedores, e o JOIN multiplicaria as linhas.
_BASE = """
SELECT x.*, COALESCE(x.data_apontamento, x.criado_em) AS data_entrada
  FROM (
    SELECT t.id, t.numero_titulo, t.nosso_numero, t.protocolo, t.especie,
           t.valor_centavos, t.saldo_centavos, t.situacao, t.origem,
           t.apresentante_codigo, t.apresentante_nome, t.cedente_nome,
           t.chave_cenprot, t.criado_em,
           (SELECT a.numero_ordem FROM pt_atos a
             WHERE a.titulo_id = t.id AND a.tipo = 'APONTAMENTO'
               AND a.cancelado = 0
             ORDER BY a.id LIMIT 1) AS numero_apontamento,
           (SELECT a.data_ato FROM pt_atos a
             WHERE a.titulo_id = t.id AND a.tipo = 'APONTAMENTO'
               AND a.cancelado = 0
             ORDER BY a.id LIMIT 1) AS data_apontamento,
           (SELECT MAX(a.data_ato) FROM pt_atos a
             WHERE a.titulo_id = t.id AND a.tipo = 'INTIMACAO'
               AND a.cancelado = 0) AS data_intimacao,
           (SELECT a.tipo FROM pt_atos a
             WHERE a.titulo_id = t.id AND a.cancelado = 0
               AND a.tipo IN ('SUSTACAO', 'REVOGACAO_SUSTACAO')
             ORDER BY a.id DESC LIMIT 1) AS ultima_ordem,
           (SELECT string_agg(d.nome::text, ' · ' ORDER BY d.id) FROM pt_devedores d
             WHERE d.titulo_id = t.id) AS devedores,
           (SELECT MIN(COALESCE(d.nome_norm, d.nome)) FROM pt_devedores d
             WHERE d.titulo_id = t.id) AS devedor_ordem
      FROM pt_titulos t
  ) x
"""

# Os parâmetros que a lista entende — e só eles viajam na paginação, na
# ordenação e na volta da ficha.
CAMPOS_DO_FILTRO = ("vista", "situacao", "apresentante", "de", "ate", "q",
                    "ordem", "dir", "vista_atual")


def _data(valor: Any) -> str:
    """`AAAA-MM-DD` ou vazio. Data inválida não filtra — e não estoura."""
    texto = str(valor or "").strip()[:10]
    try:
        return date.fromisoformat(texto).isoformat()
    except ValueError:
        return ""


def ler_filtro(args: Mapping[str, Any]) -> dict:
    """O filtro a partir do endereço, já limpo. Não lê banco.

    QUEM PROCURA UM NOME QUER O TÍTULO ONDE ELE ESTIVER. A pergunta do guichê
    é «fulano tem protesto?» — e protesto é justamente o que a vista
    «Pendentes» esconde. Por isso, sem vista escolhida, a busca e o filtro de
    situação encerrada abrem na vista que contém a resposta.
    """
    def campo(nome: str) -> str:
        return str(args.get(nome) or "").strip()

    q = campo("q")
    situacao = campo("situacao").upper()
    validas = set(VISTAS["todos"]["situacoes"]) | {FILTRO_SUSTADO}
    if situacao not in validas:
        situacao = ""

    vista = campo("vista").lower()
    # A ABA EM QUE A PESSOA ESTAVA VALE PARA O FILTRO SEM TERMO, e não para a
    # busca — 21/10/2026. O formulário mandava a vista escondida, e o oficial
    # procurou «900001» na aba «Pendentes»: o título pago estava em
    # «Encerrados», a aba contava 1 e a lista mostrava vazio. Com termo, a
    # busca abre em «Todos», que é a promessa do parágrafo acima; a aba
    # escolhida por CLIQUE (`vista` no endereço) continua mandando.
    if vista not in VISTAS and not q:
        vista = campo("vista_atual").lower()
    if vista not in VISTAS:
        if situacao in SITUACOES_ENCERRADAS:
            vista = "encerrados"
        elif situacao:
            vista = "pendentes"
        elif q:
            vista = "todos"
        else:
            vista = VISTA_PADRAO
    # Situação que não cabe na vista some, em vez de dar lista vazia calada.
    if situacao and situacao != FILTRO_SUSTADO \
            and situacao not in VISTAS[vista]["situacoes"]:
        situacao = ""
    if situacao == FILTRO_SUSTADO and vista == "encerrados":
        situacao = ""

    ordem = campo("ordem").lower()
    direcao = campo("dir").lower()
    if ordem not in ORDENS:
        ordem, direcao = ORDEM_PADRAO[vista]
    if direcao not in ("asc", "desc"):
        direcao = ORDENS[ordem]["padrao"]

    return {"vista": vista, "situacao": situacao,
            "apresentante": campo("apresentante"),
            "de": _data(args.get("de")), "ate": _data(args.get("ate")),
            "q": q, "ordem": ordem, "dir": direcao}


def params(filtro: Mapping[str, Any], **mudar) -> dict:
    """Os parâmetros do endereço, sem os vazios e sem os padrões. Não lê banco.

    É o que a paginação, os cabeçalhos clicáveis e a volta da ficha usam: a
    escolha viaja inteira, e o endereço continua curto.
    """
    f = {**{k: filtro.get(k) for k in CAMPOS_DO_FILTRO}, **mudar}
    padrao = ORDEM_PADRAO.get(f.get("vista") or VISTA_PADRAO,
                              ORDEM_PADRAO[VISTA_PADRAO])
    saida = {}
    for k in CAMPOS_DO_FILTRO + ("pagina",):
        v = f.get(k)
        if v in (None, "", 1) and k == "pagina":
            continue
        if v in (None, ""):
            continue
        saida[k] = v
    # A vista vai sempre: sem ela, o endereço sem nada volta ao padrão — e a
    # volta da ficha reabriria «Pendentes» quando se estava em «Encerrados».
    if (saida.get("ordem"), saida.get("dir")) == padrao:
        saida.pop("ordem", None)
        saida.pop("dir", None)
    return saida


def ordenar_por(filtro: Mapping[str, Any], ordem: str) -> dict:
    """Os parâmetros do clique no cabeçalho: mesma coluna inverte, outra
    coluna começa pela direção natural dela. Volta à página 1."""
    if filtro.get("ordem") == ordem:
        direcao = "asc" if filtro.get("dir") == "desc" else "desc"
    else:
        direcao = ORDENS[ordem]["padrao"]
    return params(filtro, ordem=ordem, dir=direcao, pagina=None)


def _onde(filtro: Mapping[str, Any], *, com_vista: bool,
          com_situacao: bool) -> tuple[str, list]:
    """O WHERE sobre a linha calculada `y`. Só monta texto."""
    onde: list[str] = []
    p: list[Any] = []
    if com_vista:
        sits = VISTAS[filtro["vista"]]["situacoes"]
        onde.append(f"y.situacao IN ({','.join(['%s'] * len(sits))})")
        p += list(sits)
    if com_situacao and filtro.get("situacao"):
        if filtro["situacao"] == FILTRO_SUSTADO:
            onde.append("y.ultima_ordem = 'SUSTACAO'")
        else:
            onde.append("y.situacao = %s")
            p.append(filtro["situacao"])
    if filtro.get("apresentante"):
        onde.append("(y.apresentante_codigo = %s OR y.apresentante_nome ILIKE %s)")
        p += [filtro["apresentante"], f"%{filtro['apresentante']}%"]
    if filtro.get("de"):
        onde.append("y.data_entrada >= %s")
        p.append(filtro["de"])
    if filtro.get("ate"):
        # MENOR QUE O DIA SEGUINTE, e não menor-ou-igual: `criado_em` tem hora
        # (`2026-09-14T12:11:38`), e `<= '2026-09-14'` deixaria o dia de fora.
        seguinte = (date.fromisoformat(filtro["ate"])
                    + timedelta(days=1)).isoformat()
        onde.append("y.data_entrada < %s")
        p.append(seguinte)
    termo = filtro.get("q") or ""
    if termo:
        like = f"%{termo}%"
        campos = ["y.numero_titulo ILIKE %s", "y.nosso_numero ILIKE %s",
                  "y.protocolo ILIKE %s", "y.cedente_nome ILIKE %s",
                  "y.apresentante_nome ILIKE %s", "y.chave_cenprot ILIKE %s"]
        p += [like] * len(campos)
        # O DEVEDOR MORA NOUTRA TABELA, e é por ele que o balcão procura.
        devedor = ["d.nome ILIKE %s", "d.documento_numero ILIKE %s"]
        p += [like, like]
        norm = normalizar_nome(termo)
        if norm:
            devedor.append("d.nome_norm ILIKE %s")
            p.append(f"%{norm}%")
        # CPF/CNPJ DIGITADO COM PONTO E TRAÇO acha o documento guardado só
        # com dígitos.
        digitos = "".join(c for c in termo if c.isdigit())
        if len(digitos) >= 5 and digitos != termo:
            devedor.append("d.documento_numero ILIKE %s")
            p.append(f"%{digitos}%")
        campos.append("EXISTS (SELECT 1 FROM pt_devedores d "
                      "WHERE d.titulo_id = y.id AND ("
                      + " OR ".join(devedor) + "))")
        onde.append("(" + " OR ".join(campos) + ")")
    return (" WHERE " + " AND ".join(onde)) if onde else "", p


def _contar_vistas(con: sqlite3.Connection, filtro: Mapping[str, Any]) -> dict:
    """Quantos títulos em cada vista, COM os outros filtros. Só LÊ.

    A mesma régua que filtra a lista conta o botão — contagem que não
    acompanha o filtro é o carimbo que mente sobre o próprio filtro (é a
    regra da lista de problemas da ajuda, relato #82).
    """
    onde, p = _onde(filtro, com_vista=False, com_situacao=False)
    por_situacao = {r["situacao"]: int(r["n"]) for r in banco(con).ler(
        f"SELECT y.situacao, COUNT(*) AS n FROM ({_BASE}) y{onde} "
        f"GROUP BY y.situacao", p)}
    vistas = {chave: sum(por_situacao.get(s, 0) for s in v["situacoes"])
              for chave, v in VISTAS.items()}
    # O que está fora das sete palavras ainda é título: aparece em «Todos».
    fora = sum(n for s, n in por_situacao.items()
               if s not in VISTAS["todos"]["situacoes"])
    vistas["todos"] += fora
    return {"vistas": vistas, "por_situacao": por_situacao}


def apresentantes(con: sqlite3.Connection, limite: int = 200) -> list[dict]:
    """Os apresentantes que já mandaram título, do que mais manda. Só LÊ."""
    return banco(con).ler(
        """SELECT apresentante_codigo AS codigo, apresentante_nome AS nome,
                  COUNT(*) AS n
             FROM pt_titulos
            WHERE apresentante_nome IS NOT NULL AND apresentante_nome <> ''
            GROUP BY apresentante_codigo, apresentante_nome
            ORDER BY n DESC, apresentante_nome, apresentante_codigo
            LIMIT %s""", (int(limite),))


def _detalhe(linha: Any) -> dict:
    try:
        return json.loads(linha or "{}") or {}
    except (TypeError, ValueError):
        return {}


def proximo_passo(con: sqlite3.Connection, linha: Mapping[str, Any], *,
                  hoje: str, na_fila: set, revogados: dict) -> dict | None:
    """O que falta fazer com o título, dito do estado dele. Só LÊ.

    Devolve `{"passo", "texto", ...}` — `passo` é a palavra que a tela usa para
    saber aonde levar o clique. Título encerrado não tem próximo passo: None.

    QUEM DECIDE É O DOMÍNIO QUE JÁ EXISTE: a fila do «A protestar»
    (`na_fila`, de `esperando_protesto`), a sustação revogada
    (`revogados`, de `sustacao_revogada`), a ordem em vigor
    (`sustacao_em_vigor`) e os avisos do título (`protesto_aviso.do_titulo`).
    """
    situacao = str(linha.get("situacao") or "")
    if situacao not in SITUACOES_PENDENTES:
        return None
    tid = int(linha["id"])

    # A ORDEM JUDICIAL VEM ANTES DE TUDO — Lei 9.492/1997, art. 17: o título
    # sustado fica à disposição do Juízo, e nenhum passo do fluxo cabe.
    if linha.get("ultima_ordem") == "SUSTACAO":
        ordem = PT.sustacao_em_vigor(con, tid) or {}
        onde = " · ".join(x for x in (str(ordem.get("juizo") or "").strip(),
                                      str(ordem.get("processo") or "").strip())
                          if x)
        return {"passo": "sustado",
                "texto": (f"Sustado por ordem judicial"
                          f"{(' — ' + onde) if onde else ''}"
                          f", desde {ordem.get('data_ato') or '—'}. "
                          f"À disposição do Juízo."),
                "acao": "Ver a ordem na ficha"}

    if tid in revogados:
        dias = revogados[tid]
        return {"passo": "protestar",
                "texto": (f"Sustação revogada"
                          f"{'' if dias is None else f' há {dias} dia(s)'}"
                          f" — protesto sem nova intimação (art. 17, § 2º)."),
                "dias": dias, "acao": "A protestar"}

    if situacao == "RECEBIDO":
        return {"passo": "apontar",
                "texto": "Recebido e ainda não apontado.",
                "acao": "Apontar"}

    if situacao == "APONTADO":
        return _passo_do_apontado(con, tid, linha)

    # INTIMADO
    dias = PT._dias_entre(linha.get("data_intimacao"), hoje)
    quantos = "dia não informado" if dias is None else f"{dias} dia(s)"
    if tid in na_fila:
        return {"passo": "protestar",
                "texto": (f"Intimado em {linha.get('data_intimacao') or '—'}"
                          f" — {quantos} desde a intimação."),
                "dias": dias, "acao": "A protestar"}
    return {"passo": "ficha",
            "texto": (f"Intimado em {linha.get('data_intimacao') or '—'}"
                      f" ({quantos}), e há ato lançado depois da intimação"
                      f" — confira na ficha."),
            "dias": dias, "acao": "Ver a ficha"}


def _passo_do_apontado(con: sqlite3.Connection, tid: int,
                       linha: Mapping[str, Any]) -> dict:
    """Apontado: falta intimar — e o aviso que já saiu diz em que pé está."""
    digital = banco(con).um(
        """SELECT id, estado, enviada_em FROM rs_intimacoes
            WHERE titulo_id = %s ORDER BY id DESC LIMIT 1""",
        (tid,))
    avisos = [a for a in AV.do_titulo(con, tid)
              if str(a.get("situacao") or "") != "CANCELADO"]
    aviso = avisos[0] if avisos else None

    if aviso and aviso.get("situacao") == "EMITIDO":
        return {"passo": "entrega",
                "texto": (f"Aviso {aviso.get('numero')}/{aviso.get('ano')} "
                          f"emitido em {str(aviso.get('emitido_em') or '')[:10]}"
                          f" — registrar a entrega."),
                "acao": "Avisos"}
    if aviso and aviso.get("situacao") == "NAO_ENTREGUE":
        motivo = AV.motivo_rotulo(aviso.get("motivo"))
        return {"passo": "edital",
                "texto": (f"Aviso {aviso.get('numero')}/{aviso.get('ano')} "
                          f"não entregue ({motivo}) — publicar o edital."),
                "acao": "Avisos"}
    if digital is not None:
        estado = str(digital["estado"] or "sem resposta ainda")
        return {"passo": "digital", "intimacao_id": int(digital["id"]),
                "texto": (f"Intimação digital enviada em "
                          f"{str(digital['enviada_em'] or '')[:10]} — estado "
                          f"na Central: {estado}."),
                "acao": "Acompanhar"}
    if aviso:
        # ENTREGUE ou EDITAL e o título ainda APONTADO: a intimação deveria ter
        # nascido junto. Não se adivinha — manda conferir.
        return {"passo": "ficha",
                "texto": (f"Aviso {aviso.get('numero')}/{aviso.get('ano')} "
                          f"está {str(aviso.get('situacao')).lower()}, mas o "
                          f"título segue apontado — confira a intimação."),
                "acao": "Ver a ficha"}
    tem_chave = bool(linha.get("tem_chave"))
    return {"passo": "intimar",
            "texto": ("Apontado e ainda sem intimação — emitir o aviso"
                      + (", publicar edital ou mandar a intimação digital."
                         if tem_chave else " ou publicar edital.")),
            "acao": "Intimar"}


def tem_chave_cenprot(valor: Any) -> bool:
    """A chave única do CENPROT tem 23 dígitos — `resolve_api.TAMANHO_DA_CHAVE`."""
    return len("".join(c for c in str(valor or "") if c.isdigit())) == 23


def listar(con: sqlite3.Connection, filtro: Mapping[str, Any], *,
           hoje: str, pagina: int = 1,
           por_pagina: int = POR_PAGINA) -> dict:
    """A página da lista, com as contagens e o próximo passo. Só LÊ."""
    onde, p = _onde(filtro, com_vista=True, com_situacao=True)
    o = ORDENS[filtro["ordem"]]
    d = "DESC" if filtro["dir"] == "desc" else "ASC"
    inv = "ASC" if d == "DESC" else "DESC"
    ordem_sql = o["sql"].format(d=d, inv=inv)

    bd = banco(con)
    total = int(bd.valor(f"SELECT COUNT(*) FROM ({_BASE}) y{onde}", p))
    paginas = max(1, -(-total // por_pagina))
    pagina = min(max(1, int(pagina)), paginas)
    linhas = bd.ler(
        f"SELECT y.* FROM ({_BASE}) y{onde} ORDER BY {ordem_sql} "
        f"LIMIT %s OFFSET %s", (*p, por_pagina, (pagina - 1) * por_pagina))

    # AS DUAS FILAS DA TELA «A PROTESTAR», lidas uma vez e só se a página
    # tiver quem precise delas.
    na_fila: set = set()
    revogados: dict = {}
    if any(l["situacao"] == "INTIMADO" for l in linhas):
        na_fila = {int(t["id"]) for t in
                   PT.esperando_protesto(con, hoje=hoje, limite=100000)}
    if any(l.get("ultima_ordem") == "REVOGACAO_SUSTACAO" for l in linhas):
        revogados = {int(t["id"]): t.get("dias_desde_a_revogacao")
                     for t in PT.sustacao_revogada(con, hoje=hoje,
                                                   limite=100000)}

    for l in linhas:
        l["tem_chave"] = tem_chave_cenprot(l.get("chave_cenprot"))
        l["dias_desde_a_intimacao"] = (
            PT._dias_entre(l.get("data_intimacao"), hoje)
            if l.get("data_intimacao") else None)
        l["proximo"] = proximo_passo(con, l, hoje=hoje, na_fila=na_fila,
                                     revogados=revogados)

    contagens = _contar_vistas(con, filtro)
    return {"linhas": linhas, "total": total, "pagina": pagina,
            "paginas": paginas, "vistas": contagens["vistas"],
            "por_situacao": contagens["por_situacao"],
            "acervo_vazio": not bd.um(
                "SELECT 1 AS um FROM pt_titulos ORDER BY id LIMIT 1")}
