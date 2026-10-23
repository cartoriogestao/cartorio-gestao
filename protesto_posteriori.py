"""O EMOLUMENTO A POSTERIORI DO PROTESTO — quem paga, quando, e por qual tabela.

Lote LG05 (19/10/2026). O termo desta casa escreve «pagamento a posteriori» em
**1.105 dos 1.132** protestos medidos (`protesto_termo`), e até aqui o sistema
cobrava todo ato do mesmo jeito: o item marcado entrava no caixa na hora, pela
tabela do dia. Para o título diferido isso erra duas vezes — cobra de quem a
norma dispensa, e cobra pela tabela errada.

A REGRA É DO CÓDIGO DE NORMAS DO MARANHÃO (Prov. COGEX 28/2026), art. 925:

    § 11 — o título de banco, financeira ou pessoa jurídica fiscalizada pelo
           Sistema Financeiro Nacional «independe de depósito ou pagamento
           prévio dos emolumentos», e os valores «serão exigidos dos
           interessados, de acordo com a tabela (...) vigente na data:
             I  — da protocolização, quando da desistência do pedido do
                  protesto, do pagamento elisivo do protesto ou do aceite ou
                  devolução de devedor; e
             II — do pedido de cancelamento do registro do protesto ou da
                  recepção de ordem judicial para a sustação ou cancelamento».
    § 12 — vale também (I) para concessionária regulada, decisão judicial
           transitada em julgado e certidão de dívida ativa de ente público; e
           (II) para QUALQUER pessoa, se o vencimento do título não passa de um
           ano no dia da apresentação.
    caput — fora disso, «facultada a exigência do depósito prévio».

O QUE ESTE MÓDULO FAZ COM ISSO
    `regime()` diz se o título é DIFERIDO ou ANTECIPADO, e por quê.
    `cobranca_do_ato()` diz, para cada ato, se o item marcado entra no caixa
    agora ou fica devido, quem paga e **a data da tabela**. É a resposta que a
    rota de lançar consulta antes de cobrar:

      protocolização, intimação, protesto (diferido) — o item SELA o ato e
          fica DEVIDO em `pt_emolumentos_diferidos`; não entra no caixa;
      pagamento e desistência (diferido) — cobra o que se marcou E o que ficou
          devido, pela tabela da PROTOCOLIZAÇÃO (§ 11, I);
      cancelamento (diferido) — cobra o que se marcou e o devido, pela tabela
          do DIA DO PEDIDO (§ 11, II);
      certidão — nunca é diferida: quem pede paga, pela tabela do dia (art. 950);
      título antecipado — tudo como era: o que se marca entra, pela tabela do dia.

O SELO NÃO MUDA, E ISSO É DE PROPÓSITO. O ato diferido continua selado na hora,
pelos itens marcados — é o selo que o aparelho devolve com a marca «Diferido»
(53 no razão, `selo.MARCAS_DO_SELO`). O que muda é o caixa.

A PRESUNÇÃO DA CENTRAL É PRESUNÇÃO. Título que chegou pela CRA ou pela CENPROT
é tratado como diferido porque quem apresenta pela Central é banco, financeira
ou ente conveniado (§ 11 e § 12, I) — mas isso não está no dado do título. O
balcão pode decidir o contrário em `definir_regime`, antes do primeiro ato, e a
decisão fica no rastro.

O QUE AINDA NÃO FAZ
    A ordem judicial (§ 11, II, «recepção de ordem judicial») não cobra aqui:
    sustação e efeito suspensivo não selam nem cobram nesta casa (ver
    `atribuicoes_web.protesto_lancar`). E o rateio do art. 951 — o emolumento
    do protesto diferido é de quem o lavrou, ou do FERJ na vacância — é conta
    do caixa e do Livro Diário Auxiliar, e não deste módulo.
"""
from __future__ import annotations

from datetime import date
from typing import Any

import ato_selado as AS
from bd_nativo import banco

REGIMES = ("DIFERIDO", "ANTECIPADO")

# CN-MA art. 925, § 12, I: decisão judicial transitada em julgado e certidão
# da dívida ativa. São as espécies do contrato da CRA que SÃO isso pelo nome —
# e não as que costumam vir de banco: «cédula de crédito bancário» diz quem
# emitiu, e não quem apresenta.
ESPECIES_DE_ENTE_PUBLICO_OU_JUDICIAL: dict[str, str] = {
    "CDA": "certidão da dívida ativa",
    "SJ": "sentença judicial",
    "TJD": "título executivo judicial definitivo",
    "CRJ": "certidão de crédito judicial",
    "CCJ": "carta de crédito judicial",
    "CDT": "certidão de débito do tribunal",
}

ORIGENS_DA_CENTRAL = ("CRA", "CENPROT")

# QUANDO O ATO DO TÍTULO DIFERIDO SE COBRA. Os três primeiros são o
# «procedimento» (art. 951, § 3º: intimação, diligência, arquivamento e a
# certidão); os outros três são os desfechos que o § 11 nomeia.
MOMENTO_DO_ATO: dict[str, str] = {
    "APONTAMENTO": "PROCEDIMENTO",
    "INTIMACAO": "PROCEDIMENTO",
    "PROTESTO": "PROCEDIMENTO",
    "PAGAMENTO": "PROTOCOLIZACAO",
    "DESISTENCIA": "PROTOCOLIZACAO",
    "CANCELAMENTO": "PEDIDO",
}

QUEM_PAGA: dict[str, str] = {
    "APONTAMENTO": "o apresentante",
    "INTIMACAO": "o apresentante",
    "PROTESTO": "o apresentante",
    "PAGAMENTO": "o devedor",
    "DESISTENCIA": "o apresentante",
    "CANCELAMENTO": "quem pede o cancelamento",
    "CERTIDAO": "quem pede a certidão",
}

FUNDAMENTO_DIFERIDO = ("CN-MA (Prov. COGEX 28/2026), art. 925, § 11 — "
                       "independe de depósito ou pagamento prévio")
FUNDAMENTO_PROTOCOLIZACAO = ("CN-MA, art. 925, § 11, I — tabela vigente na data "
                             "da protocolização")
FUNDAMENTO_PEDIDO = ("CN-MA, art. 925, § 11, II — tabela vigente na data do "
                     "pedido de cancelamento")
FUNDAMENTO_ANTECIPADO = ("CN-MA, art. 925, caput — emolumento pago no ato, "
                         "facultado o depósito prévio")
FUNDAMENTO_CERTIDAO = ("CN-MA, art. 950 — certidão a quem pede, pagos os "
                       "emolumentos da busca e da expedição")


class PosterioriError(ValueError):
    """Impedimento de regra, com mensagem pronta para o balcão."""


def _dia(valor: Any) -> date | None:
    try:
        return date.fromisoformat(str(valor or "")[:10])
    except ValueError:
        return None


def _um_ano_depois(d: date) -> date:
    """O mesmo dia do ano seguinte; 29/02 vira 28/02 (o ano não tem o dia)."""
    try:
        return d.replace(year=d.year + 1)
    except ValueError:
        return d.replace(year=d.year + 1, day=28)


def data_da_protocolizacao(con, titulo_id: int) -> str | None:
    """O dia do apontamento que vale, ou None se o título não foi apontado.

    É a data que o § 11, I manda usar na tabela. O apontamento cancelado (selo
    que não saiu) não conta: aquele ato não existiu.
    """
    linha = banco(con).um(
        """SELECT data_ato FROM pt_atos
            WHERE titulo_id=%s AND tipo='APONTAMENTO' AND cancelado=0
            ORDER BY id LIMIT 1""", (int(titulo_id),))
    return str(linha["data_ato"])[:10] if linha and linha["data_ato"] else None


def regime(con, titulo_id: int) -> dict:
    """DIFERIDO ou ANTECIPADO, com o porquê e o fundamento. Só LÊ.

    A ordem das perguntas é a da força da prova: o que o balcão decidiu; a
    espécie que é, pelo nome, de ente público ou de juízo (§ 12, I); a origem
    pela Central (§ 11, presunção); o vencimento de até um ano (§ 12, II). O
    que sobra é o caput — depósito prévio facultado.
    """
    bd = banco(con)
    tit = bd.um(
        """SELECT id, especie, origem, data_vencimento, emolumento_regime,
                  criado_em
             FROM pt_titulos WHERE id=%s""", (int(titulo_id),))
    if not tit:
        raise PosterioriError(f"Título {titulo_id} não encontrado.")
    protocolizado = data_da_protocolizacao(bd, titulo_id)
    apresentacao = protocolizado or str(tit["criado_em"] or "")[:10]
    base = {"titulo_id": int(tit["id"]), "data_da_protocolizacao": protocolizado,
            "data_da_apresentacao": apresentacao or None}

    escolhido = str(tit["emolumento_regime"] or "").strip().upper()
    if escolhido in REGIMES:
        return {**base, "regime": escolhido, "por": "BALCAO",
                "motivo": "decidido no balcão, antes do primeiro ato",
                "fundamento": (FUNDAMENTO_DIFERIDO if escolhido == "DIFERIDO"
                               else FUNDAMENTO_ANTECIPADO)}

    especie = str(tit["especie"] or "").strip().upper()
    if especie in ESPECIES_DE_ENTE_PUBLICO_OU_JUDICIAL:
        return {**base, "regime": "DIFERIDO", "por": "ESPECIE",
                "motivo": (f"a espécie é {ESPECIES_DE_ENTE_PUBLICO_OU_JUDICIAL[especie]}"
                           f" ({especie})"),
                "fundamento": "CN-MA, art. 925, § 12, I"}

    if str(tit["origem"] or "").strip().upper() in ORIGENS_DA_CENTRAL:
        return {**base, "regime": "DIFERIDO", "por": "CENTRAL",
                "motivo": (f"veio pela {str(tit['origem']).upper()} — quem "
                           f"apresenta pela Central é banco, financeira ou ente "
                           f"conveniado (presunção; o balcão pode corrigir)"),
                "fundamento": FUNDAMENTO_DIFERIDO}

    vencimento = _dia(tit["data_vencimento"])
    dia_apresentacao = _dia(apresentacao)
    if vencimento and dia_apresentacao and dia_apresentacao <= _um_ano_depois(vencimento):
        return {**base, "regime": "DIFERIDO", "por": "VENCIMENTO",
                "motivo": (f"vencido em {vencimento.strftime('%d/%m/%Y')}, há "
                           f"menos de um ano da apresentação"),
                "fundamento": "CN-MA, art. 925, § 12, II"}

    motivo = ("vencimento não informado" if not vencimento
              else f"vencido em {vencimento.strftime('%d/%m/%Y')}, há mais de "
                   f"um ano da apresentação")
    return {**base, "regime": "ANTECIPADO", "por": "DEPOSITO_PREVIO",
            "motivo": motivo, "fundamento": FUNDAMENTO_ANTECIPADO}


def cobranca_do_ato(con, titulo_id: int | None, tipo: str, *,
                    hoje: str) -> dict:
    """Como o ato `tipo` se cobra neste título. Só LÊ.

    Devolve `diferir` (o item marcado fica devido, e não entra no caixa),
    `cobra_diferidos` (este é o desfecho que cobra o que ficou devido),
    `data_da_tabela` (a data que vai a `ato_selado.cobrar(data_do_ato=)`),
    `quem_paga`, `fundamento` e uma `frase` para a tela.

    A CERTIDÃO NÃO TEM TÍTULO e não se difere: `titulo_id` pode vir None.
    """
    tipo = str(tipo or "").strip().upper()
    hoje = str(hoje)[:10]
    if tipo == "CERTIDAO":
        return {"tipo": tipo, "regime": None, "diferir": False,
                "cobra_diferidos": False, "data_da_tabela": hoje,
                "quem_paga": QUEM_PAGA["CERTIDAO"],
                "fundamento": FUNDAMENTO_CERTIDAO,
                "frase": ("A certidão não se difere: quem pede paga, pela "
                          "tabela de hoje.")}
    reg = regime(con, titulo_id)
    momento = MOMENTO_DO_ATO.get(tipo)
    saida = {"tipo": tipo, "regime": reg["regime"], "diferir": False,
             "cobra_diferidos": False, "data_da_tabela": hoje,
             "quem_paga": QUEM_PAGA.get(tipo), "momento": momento}
    if reg["regime"] != "DIFERIDO" or momento is None:
        return {**saida, "fundamento": FUNDAMENTO_ANTECIPADO,
                "frase": "O que se marcar entra no caixa agora, pela tabela de hoje."}
    if momento == "PROCEDIMENTO":
        return {**saida, "diferir": True, "data_da_tabela": None,
                "quem_paga": "quem der o desfecho (devedor, apresentante ou "
                             "quem pedir o cancelamento)",
                "fundamento": FUNDAMENTO_DIFERIDO,
                "frase": ("Emolumento a posteriori: os itens marcados selam este "
                          "ato e ficam devidos — não entram no caixa agora.")}
    if momento == "PROTOCOLIZACAO":
        data = reg["data_da_protocolizacao"] or hoje
        return {**saida, "cobra_diferidos": True, "data_da_tabela": data,
                "fundamento": FUNDAMENTO_PROTOCOLIZACAO,
                "frase": (f"Cobra-se o que se marcar e o que ficou devido, pela "
                          f"tabela de {_br(data)} (protocolização); paga "
                          f"{QUEM_PAGA[tipo]}.")}
    return {**saida, "cobra_diferidos": True, "data_da_tabela": hoje,
            "fundamento": FUNDAMENTO_PEDIDO,
            "frase": (f"Cobra-se o que se marcar e o que ficou devido, pela "
                      f"tabela de {_br(hoje)} (dia do pedido de cancelamento).")}


def _br(dia: str) -> str:
    d = _dia(dia)
    return d.strftime("%d/%m/%Y") if d else str(dia or "—")


# ---------------------------------------------------------- o que fica devido


def diferir(con, *, titulo_id: int, ato_id: int, tipo_ato: str,
            itens: list[dict], data_do_ato: str, agora: str,
            usuario: str | None = None) -> dict:
    """Registra os itens que o ato deve e não cobrou. ESCREVE.

    `itens` traz `servico`, `quantidade` e `descricao`. O preço se confere
    AQUI, pela tabela do dia do ato, e não só no desfecho: item que a tabela
    não tem estoura agora, e a transação do ato volta inteira — a mesma regra
    da cobrança recusada. Descobrir no pagamento, meses depois, que o item não
    existia seria deixar o devedor esperando no balcão.

    O mesmo item no mesmo ato não se registra duas vezes (UNIQUE(ato_id,
    servico)): ele seria cobrado duas vezes no desfecho.
    """
    bd = banco(con)
    total = 0
    registrados = 0
    for item in itens:
        servico = int(item["servico"])
        quantidade = max(1, int(item.get("quantidade") or 1))
        conta = AS.calcular_custas(con, servico=servico, data=data_do_ato,
                                   quantidade=quantidade)
        novo = bd.escrever(
            """INSERT INTO pt_emolumentos_diferidos(titulo_id, ato_id, tipo_ato,
                   servico, quantidade, descricao, data_do_ato, criado_em,
                   criado_por)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (ato_id, servico) DO NOTHING
               RETURNING id""",
            (int(titulo_id), int(ato_id), str(tipo_ato).upper(), servico,
             quantidade, item.get("descricao") or conta.get("descricao"),
             str(data_do_ato)[:10], agora, usuario))
        if novo:
            registrados += 1
            total += int(conta.get("total_centavos") or 0)
    return {"registrados": registrados, "estimado_centavos": total}


def pendentes(con, titulo_id: int) -> list[dict]:
    """O que o título deve a posteriori, item por item. Só LÊ.

    O item de ato cancelado não entra: o selo que não saiu desfez o ato, e com
    ele o emolumento.
    """
    return banco(con).ler(
        """SELECT d.*, a.tipo AS tipo_do_ato, a.data_ato
             FROM pt_emolumentos_diferidos d
             JOIN pt_atos a ON a.id = d.ato_id
            WHERE d.titulo_id=%s AND d.situacao='PENDENTE' AND a.cancelado=0
            ORDER BY d.id""", (int(titulo_id),))


def estimar(con, itens: list[dict], *, data_da_tabela: str) -> dict:
    """Quanto o devido custa pela tabela daquela data. Só LÊ.

    Item que a tabela daquela data não tem vem com `preco=None` e o motivo, e
    não some: sumir seria cobrar a menos sem ninguém ver.
    """
    total = 0
    saida = []
    for item in itens:
        d = dict(item)
        try:
            conta = AS.calcular_custas(con, servico=int(d["servico"]),
                                       data=data_da_tabela,
                                       quantidade=int(d.get("quantidade") or 1))
            d["preco"] = int(conta.get("total_centavos") or 0)
            d["motivo"] = None
            total += d["preco"]
        except AS.AtoError as erro:
            d["preco"] = None
            d["motivo"] = str(erro)
        saida.append(d)
    return {"itens": saida, "total_centavos": total}


def cobrar_pendentes(con, titulo_id: int, *, ato_do_desfecho_id: int,
                     data_da_tabela: str, caixa_id: int, agora: str, hoje: str,
                     hora: str, protocolo_id: int | None = None,
                     pagador: str | None = None,
                     forma_pagamento: str | None = None,
                     usuario: str | None = None) -> dict:
    """Lança no caixa o que ficou devido, no desfecho. ESCREVE.

    CADA ITEM SE COBRA NO ATO QUE O DEVIA, e não no ato do desfecho: a chave
    do lançamento é `pt_atos:<ato que deveu>:<item>`, e é ela que impede a
    segunda cobrança (`ato_selado.cobrar`). A ficha mostra o cobrado na linha
    da protocolização, que é onde ele nasceu.

    AS LINHAS FICAM PRESAS (FOR UPDATE) da leitura à gravação: dois desfechos
    ao mesmo tempo — o pagamento no balcão e a desistência que chegou pela
    Central — leriam os dois a mesma pendência.
    """
    bd = banco(con)
    bd._escrita()
    linhas = bd.ler(
        """SELECT d.* FROM pt_emolumentos_diferidos d
             JOIN pt_atos a ON a.id = d.ato_id
            WHERE d.titulo_id=%s AND d.situacao='PENDENTE' AND a.cancelado=0
            ORDER BY d.id
            FOR UPDATE OF d""", (int(titulo_id),))
    total = 0
    for d in linhas:
        r = AS.cobrar(con, tabela="pt_atos", ato_id=int(d["ato_id"]),
                      servico=int(d["servico"]),
                      quantidade=int(d["quantidade"] or 1), agora=agora,
                      hoje=hoje, hora=hora, caixa_id=caixa_id,
                      protocolo_id=protocolo_id, pagador=pagador,
                      forma_pagamento=forma_pagamento,
                      descricao=f"{d['tipo_ato']} a posteriori — pt_atos",
                      data_do_ato=data_da_tabela, usuario_id=None)
        bd.escrever(
            """UPDATE pt_emolumentos_diferidos
                  SET situacao='COBRADO', cobrado_no_ato_id=%s, lancamento_id=%s,
                      data_da_tabela=%s, cobrado_em=%s, cobrado_por=%s
                WHERE id=%s""",
            (int(ato_do_desfecho_id), r["lancamento_id"], str(data_da_tabela)[:10],
             agora, usuario, int(d["id"])))
        total += int(r["total_centavos"] or 0)
    return {"itens": len(linhas), "total_centavos": total}


# ---------------------------------------------------------------- o balcão


def definir_regime(con, titulo_id: int, escolha: str | None, *,
                   motivo: str) -> dict:
    """O balcão decide o regime, ou devolve à regra. ESCREVE.

    SÓ ANTES DO PRIMEIRO ATO. O regime diz quem paga a protocolização; mudar
    depois dela faria o mesmo ato ser devido e cobrado, ou nenhum dos dois. O
    motivo é obrigatório e vai para o rastro (`audit_logs`), por quem chama.
    """
    import protesto as PT
    valor = str(escolha or "").strip().upper() or None
    if valor is not None and valor not in REGIMES:
        raise PosterioriError(
            f"Regime desconhecido: {escolha!r}. Os que existem são "
            f"{', '.join(REGIMES)}, ou vazio para a regra decidir.")
    if len(str(motivo or "").strip()) < 5:
        raise PosterioriError(
            "Escreva por que o regime dos emolumentos muda — é o que a "
            "conferência lê depois.")
    bd = banco(con)
    tit = PT.titulo_para_gravar(bd, titulo_id)
    if not tit:
        raise PosterioriError(f"Título {titulo_id} não encontrado.")
    lancado = bd.valor(
        "SELECT count(*) AS n FROM pt_atos WHERE titulo_id=%s AND cancelado=0",
        (int(titulo_id),))
    if int(lancado or 0):
        raise PosterioriError(
            f"O título {tit['numero_titulo']} já tem ato lançado — o regime dos "
            f"emolumentos se decide antes da protocolização, e não depois.")
    bd.escrever("UPDATE pt_titulos SET emolumento_regime=%s WHERE id=%s",
                (valor, int(titulo_id)))
    return {"titulo_id": int(titulo_id), "regime": valor,
            "motivo": str(motivo).strip()}


def resumo_para_a_ficha(con, titulo_id: int, *, hoje: str) -> dict:
    """O quadro do emolumento a posteriori, para a ficha do título. Só LÊ."""
    reg = regime(con, titulo_id)
    devidos = pendentes(con, titulo_id)
    por_ato = {t: cobranca_do_ato(con, titulo_id, t, hoje=hoje)
               for t in MOMENTO_DO_ATO}
    previsto = reg["data_da_protocolizacao"] or str(hoje)[:10]
    lancados = banco(con).valor(
        "SELECT count(*) AS n FROM pt_atos WHERE titulo_id=%s AND cancelado=0",
        (int(titulo_id),))
    return {**reg, "pendentes": estimar(con, devidos, data_da_tabela=previsto),
            "por_ato": por_ato, "pode_mudar": not int(lancados or 0)}
