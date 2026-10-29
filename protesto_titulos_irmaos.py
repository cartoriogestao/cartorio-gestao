"""Os TÍTULOS IRMÃOS do Protesto — os que dividem o mesmo protocolo.

O CASO QUE MOTIVOU, 29/10/2026 (produção). Duas parcelas do mesmo devedor, do
mesmo credor, com o MESMO protocolo e o mesmo valor (R$ 230,00): a /1 vencida
em maio e a /2 vencida em junho. O devedor pagou UMA parcela; o pagamento foi
lançado na /2, e era da /1 (a liquidação na CENPROT foi feita no pedido da /1).
**A /1 foi intimada por edital e PROTESTADA estando paga; a /2 ficou «paga»
sem ter sido paga.** Nada na tela mostrava que o protocolo tinha dois títulos,
e nada pedia a quem lançava que dissesse QUAL dos dois estava no papel.

Ordem do oficial, no mesmo dia: «trabalhamos com mão de obra muito propensa a
erros [...] não deixando a escrevente cometer erros. Se insistir em algo que é
erro, precisa afirmar expressamente e deixar log.»

O QUE É IRMÃO, MEDIDO NA PRODUÇÃO (29/10/2026, só leitura)
    **Irmão é título com o mesmo protocolo.** São 35 protocolos com dois
    títulos cada (70 de 1.413):
      - 32 são o MESMO título com dois devedores — a CDA da Fazenda Nacional
        (apresentante 901) com o devedor e o corresponsável: mesmo número,
        mesmo vencimento, mesmo valor, devedores diferentes. A CRA manda duas
        linhas, e a casa sempre guardou dois títulos (o E-Ofício fazia igual);
      - 2 são o mesmo título com o mesmo devedor nas duas linhas;
      - 1 é o caso das parcelas: números e vencimentos diferentes.
    A ALTERNATIVA FOI MEDIDA E NÃO ENTROU: «mesmo devedor + mesmo credor +
    mesmo valor, em aberto» dá **zero** grupos entre os títulos que ainda se
    pagam (recebido, apontado ou intimado). E «mesmo credor» não se mede hoje:
    o apresentante da CRA é o BANCO, e o cedente gravado está errado em quase
    todo o acervo (ver a conferência, abaixo).

A TRAVA — pagamento, desistência e cancelamento
    Quando o título tem irmão EM ABERTO que se DISTINGUE dele (número ou
    vencimento diferentes), quem lança tem de dizer qual título está no PAPEL
    — o comprovante, o boleto, o pedido do credor, a carta de anuência —
    digitando o número e o vencimento que estão nele. A conferência compara
    com os títulos do protocolo:
      - bate com ESTE título → passa, e a conferência fica gravada no ato;
      - bate com o IRMÃO → recusa, dizendo que o papel é do irmão e onde
        lançar. **É exatamente o erro do caso real**: na ficha da /2, com o
        papel da /1 na mão, quem digita o que está no papel digita «/1» e o
        vencimento de maio, e o sistema não deixa lançar na /2;
      - não bate com nenhum → recusa, listando os títulos do protocolo.
    POR QUE DIGITAR, E NÃO MARCAR. Uma caixa já marcada, ou uma lista com o
    título da ficha em primeiro lugar, é clicada por reflexo — e o reflexo foi
    o erro. Digitar o número E o vencimento obriga a ler o papel; e os dois
    juntos, porque parcelas costumam diferir só no sufixo («/1», «/2»).
    O IRMÃO IDÊNTICO NÃO TRAVA: o corresponsável da CDA tem o mesmo número, o
    mesmo vencimento e o mesmo valor — nenhum papel distingue os dois, e pedir
    a conferência ali seria o alarme que soa sempre. Ele aparece no quadro dos
    irmãos e, se as situações divergirem, na conferência.
    OS CANAIS AUTOMÁTICOS NÃO PASSAM POR AQUI: a baixa do boleto se prende ao
    nosso número do boleto, e a desistência da CRA vem no arquivo. A trava é
    da ficha, onde quem escolhe o título é uma pessoa.

A TRAVA DO PROTESTO — decisão do oficial, 29/10/2026
    O PROTESTO TRAVA quando um irmão de vencimento POSTERIOR está PAGO com o
    MESMO valor. É a assinatura do caso: a /2 «paga» e a /1, anterior e de
    mesmo valor, indo a protesto — o pagamento lançado na /2 era da /1. Não há
    papel a digitar aqui (quem vai a protesto não trouxe comprovante): a trava
    se vence SÓ com afirmação expressa, regra própria
    («PROTESTO_IRMAO_POSTERIOR_PAGO»), gravada no ato e na auditoria. Vale na
    ficha e no lote «A protestar»; no lote o travado SAI da seleção, com o
    motivo à vista, e só se protesta pela ficha, afirmando.
    Medido em 29/10/2026: entre os títulos intimados (os que podem ir a
    protesto), ela pega ZERO — o caso já foi corrigido. Antes da correção
    pegaria a /1.

A AFIRMAÇÃO EXPRESSA — o contrato comum da casa (29/10/2026)
    A trava se vence só com a caixa `afirmo` marcada E o texto `afirmacao`
    com pelo menos 30 letras («Afirmo, sob minha responsabilidade, que…»). O
    texto vai ao `detalhe_json` do ato, e a rota grava, FORA da transação,
    `audit("AFIRMACAO_EXPRESSA", "pt_titulos", titulo_id, {"regra": ...,
    "afirmacao": ..., "o_que_faltava": ...})`. **A fórmula não conta nas
    trinta letras**: sem isso, a frase-modelo sozinha passaria. **Robô não
    afirma**: a afirmação é de uma pessoa, sob a responsabilidade dela.

A CONFERÊNCIA — só lê, não corrige
    1. Irmãos com situações que não se explicam juntas (um pago e o outro
       protestado com o mesmo valor; pago o de vencimento posterior e o
       anterior em aberto; um pago e o outro sem intimação; o mesmo título
       com situações diferentes para cada devedor). Medido em 29/10/2026:
       **zero** — o caso das parcelas já foi corrigido por ordem do oficial,
       e antes da correção ele teria aparecido em duas regras.
    2. Títulos cujo CEDENTE diverge do registro de origem (o registro de 600
       posições da remessa, o teor do pedido da CENPROT, ou a linha do
       E-Ofício). Medido em 29/10/2026: **1.404 de 1.407** títulos com
       registro de origem — 487 com o cedente vazio e 917 com outro nome. A
       CAUSA, medida no acervo: a carga lia o cedente em `tbPessoa` pelo
       código do cedente, e o código é de `tbCedente` (a razão social de
       `tbCedente` bate com o registro da CRA em 1.100 de 1.403). Isto NÃO se
       conserta aqui: a conferência mostra, e o conserto do dado e da carga é
       decisão do oficial.
       E O DADO FOI CONSERTADO NO MESMO DIA, por fora deste módulo: às 15h41
       a correção da carga (auditoria `PROTESTO_CORRECAO_CEDENTE_CARGA`,
       1.409 linhas). Medido depois dela: sobra **1** — a /1 do caso, que
       entrou pelo pedido da CENPROT e se confere contra a linha do E-Ofício.
       A conferência continua: é ela que diz se a correção pegou, e pega o
       próximo.
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime
from collections.abc import Iterable
from typing import Any

import afirmacoes_expressas as AFX
import protesto as PT
import protesto_arquivo as PA
from bd_nativo import banco


class TituloIrmaoError(PT.ProtestoError):
    """A trava dos irmãos recusou, com a frase pronta para o balcão."""


# Os atos da ficha que exigem dizer QUAL título está no papel. São os três em
# que o papel nomeia um título: o comprovante (pagamento), o pedido do credor
# (desistência) e a carta de anuência ou a ordem (cancelamento).
ATOS_COM_TRAVA = ("PAGAMENTO", "DESISTENCIA", "CANCELAMENTO")

# Irmão EM ABERTO é o que ainda pode ser objeto do mesmo papel. O PROTESTADO
# entra: o comprovante pode ser do protestado (pago ao credor), e a carta de
# anuência de um protesto é o caso típico de dois protestos no protocolo.
SITUACOES_EM_ABERTO = ("RECEBIDO", "APONTADO", "INTIMADO", "PROTESTADO")

# O código da regra na auditoria `AFIRMACAO_EXPRESSA`: a do papel (pagamento,
# desistência, cancelamento) e a do protesto, que são duas decisões
# diferentes e se contam separadas.
REGRA = "PROTESTO_IRMAO_EM_ABERTO"
REGRA_PROTESTO = "PROTESTO_IRMAO_POSTERIOR_PAGO"

# O contrato comum da afirmação expressa (29/10/2026) — a régua mora em
# `afirmacoes_expressas` desde a integração.
MINIMO_DE_LETRAS = AFX.MINIMO_DE_LETRAS
FORMULA = AFX.MODELO

O_ATO = {"PAGAMENTO": "o pagamento", "DESISTENCIA": "a desistência",
         "CANCELAMENTO": "o cancelamento", "PROTESTO": "o protesto"}
# Onde se confere, com a preposição: «confira NO comprovante».
NO_PAPEL = {"PAGAMENTO": "no comprovante ou no boleto do pagamento",
            "DESISTENCIA": "no pedido de desistência do credor",
            "CANCELAMENTO": "na carta de anuência ou na ordem judicial"}

# De onde veio o registro de origem do cedente, como a tela o diz.
DE_ONDE = {"REMESSA": "a remessa da CRA (registro de 600 posições)",
           "PEDIDO": "o pedido da CENPROT",
           "ACERVO": "a linha do E-Ofício (tbSDT)"}


# ------------------------------------------------------------ as réguas


def _numero(v: Any) -> str:
    """O número do título reduzido ao que se compara: letras e algarismos, sem
    zeros à esquerda. «350574/1», «350574-1» e «0350574/1» dão o mesmo."""
    s = re.sub(r"[^0-9A-Z]", "", str(v or "").upper())
    return s.lstrip("0")


def _vencimento(v: Any) -> str:
    """A data em AAAA-MM-DD, ou "" quando não é data (o título sem
    vencimento, como a CDA, chega com marca e não com data)."""
    s = str(v or "").strip()
    for formato, tamanho in (("%Y-%m-%d", 10), ("%d/%m/%Y", 10)):
        try:
            return datetime.strptime(s[:tamanho], formato).date().isoformat()
        except ValueError:
            continue
    return ""


def _br(iso: Any) -> str:
    v = _vencimento(iso)
    return f"{v[8:10]}/{v[5:7]}/{v[0:4]}" if v else "sem vencimento"


def _reais(centavos: Any) -> str:
    c = int(centavos or 0)
    inteiro = f"{abs(c) // 100:,}".replace(",", ".")
    return f"R$ {'-' if c < 0 else ''}{inteiro},{abs(c) % 100:02d}"


def _nome(v: Any) -> str:
    """O nome sem acento, sem pontuação, em maiúsculas — a régua do cedente."""
    s = unicodedata.normalize("NFKD", str(v or "")).encode(
        "ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", " ", s).strip().upper()


def _mesmo_nome(gravado: Any, origem: Any) -> bool:
    """O MESMO NOME, MESMO TRUNCADO: o campo da CRA tem 45 posições, e a
    razão social inteira não cabe nele. Um ser começo do outro basta."""
    a, b = _nome(gravado), _nome(origem)
    return bool(a and b) and (a.startswith(b) or b.startswith(a))


def _chave(t: dict) -> tuple[str, str]:
    """O que distingue um título do irmão no papel: número e vencimento."""
    return _numero(t.get("numero_titulo")), _vencimento(t.get("data_vencimento"))


def _rotulo(t: dict) -> str:
    return (f"{t.get('numero_titulo') or 'sem número'} (vencimento "
            f"{_br(t.get('data_vencimento'))}, {_reais(t.get('valor_centavos'))}, "
            f"{t.get('situacao')})")


def _marcas(n: int) -> str:
    return ",".join(["%s"] * n)


# ------------------------------------------------------------ os irmãos


def _titulos_dos_protocolos(bd, protocolos: list[str]) -> list[dict]:
    """Os títulos de cada protocolo, com devedores e o último ato. Só LÊ."""
    if not protocolos:
        return []
    titulos = [dict(r) for r in bd.ler(
        f"""SELECT id, protocolo, numero_titulo, nosso_numero, data_vencimento,
                   valor_centavos, saldo_centavos, situacao, especie,
                   apresentante_codigo
              FROM pt_titulos
             WHERE protocolo IN ({_marcas(len(protocolos))})
             ORDER BY protocolo, id""", tuple(protocolos))]
    if not titulos:
        return []
    ids = [t["id"] for t in titulos]
    devedores: dict[int, list[dict]] = {}
    for d in bd.ler(
            f"""SELECT titulo_id, nome, documento_numero FROM pt_devedores
                 WHERE titulo_id IN ({_marcas(len(ids))}) ORDER BY id""",
            tuple(ids)):
        devedores.setdefault(int(d["titulo_id"]), []).append(dict(d))
    ultimo: dict[int, dict] = {}
    for a in bd.ler(
            f"""SELECT titulo_id, id, tipo, data_ato FROM pt_atos
                 WHERE cancelado = 0 AND titulo_id IN ({_marcas(len(ids))})
                 ORDER BY id""", tuple(ids)):
        ultimo[int(a["titulo_id"])] = {"tipo": a["tipo"],
                                       "data": str(a["data_ato"] or "")[:10]}
    for t in titulos:
        devs = devedores.get(int(t["id"]), [])
        t["devedores"] = [d["nome"] for d in devs if d.get("nome")]
        t["documentos"] = sorted({re.sub(r"\D", "", d.get("documento_numero") or "")
                                  for d in devs} - {""})
        t["ultimo_ato"] = ultimo.get(int(t["id"]))
        t["vencimento_br"] = _br(t.get("data_vencimento"))
        t["valor_br"] = _reais(t.get("valor_centavos"))
    return titulos


def _sinais(este: dict, irmao: dict) -> list[str]:
    """O que o irmão diz sobre ESTE título, em frase de balcão. Só calcula."""
    sinais = []
    identico = _chave(este) == _chave(irmao)
    if identico:
        sinais.append("é o mesmo título (mesmo número e vencimento), com "
                      "outro devedor ou outra linha da remessa")
        if (irmao["situacao"] != este["situacao"]
                and int(irmao.get("valor_centavos") or 0)
                == int(este.get("valor_centavos") or 0)):
            sinais.append(f"e está {irmao['situacao']}, enquanto este está "
                          f"{este['situacao']}")
        return sinais
    if irmao["situacao"] == "PAGO" and este["situacao"] != "PAGO":
        if int(irmao.get("valor_centavos") or 0) == int(este.get("valor_centavos") or 0):
            sinais.append("está PAGO, com o mesmo valor deste: confira se o "
                          "pagamento não era deste título")
        vi, ve = _vencimento(irmao.get("data_vencimento")), _vencimento(
            este.get("data_vencimento"))
        if vi and ve and vi > ve and este["situacao"] in SITUACOES_EM_ABERTO:
            sinais.append("o de vencimento POSTERIOR está pago e este, "
                          "anterior, não — o devedor costuma pagar primeiro o "
                          "mais antigo")
    return sinais


def _grupos_de(bd, titulo_ids: Iterable[Any]) -> dict[int, tuple[dict, list[dict]]]:
    """Para cada título pedido: ele mesmo e os OUTROS títulos do protocolo,
    cada um com o que sinaliza sobre ele. Só LÊ."""
    ids = sorted({int(i) for i in titulo_ids if str(i).strip().isdigit()})
    if not ids:
        return {}
    deles = {int(r["id"]): str(r["protocolo"] or "").strip() for r in bd.ler(
        f"SELECT id, protocolo FROM pt_titulos WHERE id IN ({_marcas(len(ids))})",
        tuple(ids))}
    protocolos = sorted({p for p in deles.values() if p})
    por_protocolo: dict[str, list[dict]] = {}
    for t in _titulos_dos_protocolos(bd, protocolos):
        por_protocolo.setdefault(str(t["protocolo"]).strip(), []).append(t)
    saida: dict[int, tuple[dict, list[dict]]] = {}
    for tid, p in deles.items():
        grupo = por_protocolo.get(p) or []
        este = next((t for t in grupo if int(t["id"]) == tid), None)
        if este is None:
            continue
        outros = [{**t,
                   "em_aberto": t["situacao"] in SITUACOES_EM_ABERTO,
                   "distinguivel": _chave(t) != _chave(este),
                   "mesmo_devedor": bool(t["documentos"])
                                    and t["documentos"] == este["documentos"],
                   "sinais": _sinais(este, t)}
                  for t in grupo if int(t["id"]) != tid]
        if outros:
            saida[tid] = (este, outros)
    return saida


def irmaos_de_varios(con, titulo_ids: Iterable[Any]) -> dict[int, list[dict]]:
    """Os irmãos de cada título pedido: id → lista dos OUTROS títulos do mesmo
    protocolo, com número, vencimento, valor, situação, último ato e o que cada
    um sinaliza sobre o título pedido. Só LÊ.

    Título sem protocolo não tem irmão: o protocolo nasce no apontamento, e
    antes dele não há o que dividir.
    """
    return {tid: outros
            for tid, (_, outros) in _grupos_de(banco(con), titulo_ids).items()}


def _trava_do_protesto(este: dict, irmaos: list[dict]) -> dict | None:
    """A trava do protesto (decisão do oficial, 29/10/2026): um irmão de
    vencimento POSTERIOR está PAGO com o MESMO valor deste. Só calcula.

    Sem vencimento deste ou do irmão não há «posterior» a medir, e a regra
    não se aplica — ela é a assinatura das parcelas, que vencem em datas.
    """
    ve = _vencimento(este.get("data_vencimento"))
    if not ve:
        return None
    valor = int(este.get("valor_centavos") or 0)
    pagos = [i for i in irmaos
             if i["situacao"] == "PAGO"
             and _vencimento(i.get("data_vencimento")) > ve
             and int(i.get("valor_centavos") or 0) == valor]
    if not pagos:
        return None
    motivo = (
        f"O irmão {'; '.join(_rotulo(i) for i in pagos)} — mesmo protocolo "
        f"{este['protocolo']}, vencimento POSTERIOR e o mesmo valor deste — "
        f"está PAGO, e este ({_rotulo(este)}) iria a protesto. É a assinatura "
        f"do caso de 29/10/2026: o pagamento lançado no irmão era deste. "
        f"Confira no comprovante qual dos dois foi pago antes de protestar.")
    return {"regra": REGRA_PROTESTO, "motivo": motivo, "irmaos": pagos}


def travas_do_protesto(con, titulo_ids: Iterable[Any]) -> dict[int, dict]:
    """Os títulos que NÃO vão a protesto sem afirmação expressa: id → a trava
    (regra, motivo e os irmãos pagos). Só LÊ. É o que tira o título da
    seleção do lote «A protestar»."""
    saida: dict[int, dict] = {}
    for tid, (este, outros) in _grupos_de(banco(con), titulo_ids).items():
        trava = _trava_do_protesto(este, outros)
        if trava:
            saida[tid] = trava
    return saida


def quadro_da_ficha(con, titulo_id: int) -> dict | None:
    """O quadro «Títulos irmãos» da ficha: este título e os irmãos lado a lado,
    e se a trava vale. None quando o título não tem irmão. Só LÊ."""
    achado = _grupos_de(banco(con), [titulo_id]).get(int(titulo_id))
    if not achado:
        return None
    este, irmaos = achado
    travam = [i for i in irmaos if i["em_aberto"] and i["distinguivel"]]
    return {"protocolo": este["protocolo"], "este": este,
            "irmaos": irmaos, "trava": bool(travam), "travam": travam,
            "atos_com_trava": ATOS_COM_TRAVA,
            "trava_protesto": _trava_do_protesto(este, irmaos),
            "minimo_de_letras": MINIMO_DE_LETRAS, "formula": FORMULA}


# ------------------------------------------------------------ a trava


def _letras(texto: Any) -> int:
    """Quantas LETRAS a afirmação tem ALÉM da fórmula. Sem tirar a fórmula, a
    frase-modelo sozinha («Afirmo, sob minha responsabilidade, que») já teria
    as trinta letras, e a afirmação passaria sem dizer nada. A régua é a do
    contrato (`afirmacoes_expressas.letras_alem_da_frase`)."""
    return AFX.letras_alem_da_frase(texto)


def _afirmacao(afirmo: bool, afirmacao: Any, *, por_robo: bool,
               o_que_faltava: str, ato: str) -> str | None:
    """A afirmação expressa, conferida — o texto, ou None se não foi feita.
    Recusa a afirmação pela metade, e a do robô."""
    texto = str(afirmacao or "").strip()
    if not afirmo and not texto:
        return None
    if por_robo:
        raise TituloIrmaoError(
            "Robô não faz afirmação expressa: ela é de uma pessoa, sob a "
            "responsabilidade dela. Lance este ato com o usuário de quem "
            "conferiu o papel. Nada foi lançado.")
    valido = AFX.texto_valido(texto) if afirmo else None
    if not valido:
        raise TituloIrmaoError(
            f"Para lançar {O_ATO.get(ato, 'o ato')} assim mesmo, marque "
            f"«Afirmo» E escreva a afirmação com pelo menos {MINIMO_DE_LETRAS} "
            f"letras além de «{FORMULA}…» — o que você conferiu e por que este "
            f"é o título certo. O que faltava: {o_que_faltava} Nada foi "
            f"lançado.")
    # A FRASE INTEIRA FICA GRAVADA: a tela comum da casa mostra a abertura
    # fora da caixa de texto, e quem escreve só o resto afirmou a frase toda
    # (`afirmacoes_expressas.texto_valido` a põe na frente).
    return valido


def _bate(t: dict, numero: str, vencimento: str) -> bool:
    numeros = {_numero(t.get("numero_titulo")), _numero(t.get("nosso_numero"))} - {""}
    if numero not in numeros:
        return False
    venc = _vencimento(t.get("data_vencimento"))
    return not venc or venc == vencimento


def conferir_e_anotar(con, titulo_id: int, ato: str, ato_id: int, *,
                      numero: Any = None, vencimento: Any = None,
                      afirmo: bool = False, afirmacao: Any = None,
                      por_robo: bool = False, quem: str | None = None,
                      agora: str | None = None,
                      situacao_antes: str | None = None) -> dict | None:
    """A trava dos irmãos, DEPOIS de o domínio aceitar o ato e ANTES de a
    transação confirmar. ESCREVE no `detalhe_json` do ato.

    Chamada na mesma transação em que o ato acabou de ser lançado: a recusa
    (`TituloIrmaoError`, que é `ProtestoError`) desfaz tudo — o ato, o lugar
    no livro, a situação. E as recusas do próprio domínio (título sustado,
    protestado que não se paga...) vêm antes desta, que é como devem vir.
    `situacao_antes` é a do título antes do ato: é ela que a frase mostra,
    porque o ato ainda não valeu.

    Devolve None quando a trava não vale (outro ato, ou nenhum irmão em
    aberto que se distinga deste); senão, o que ficou gravado no ato —
    `titulo_conferido` ou `afirmacao_expressa`. Quem chama grava a auditoria
    da afirmação FORA da transação.

    NO PROTESTO a trava é outra (decisão do oficial, 29/10/2026): o irmão de
    vencimento posterior pago com o mesmo valor. Ali não há papel a digitar, e
    ela se vence só com a afirmação — regra `REGRA_PROTESTO`. O lote não
    afirma: chamado sem `afirmo`, recusa, e o título se protesta pela ficha.
    """
    if ato == "PROTESTO":
        return _conferir_o_protesto(con, titulo_id, ato_id, afirmo=afirmo,
                                    afirmacao=afirmacao, por_robo=por_robo,
                                    quem=quem, agora=agora,
                                    situacao_antes=situacao_antes)
    if ato not in ATOS_COM_TRAVA:
        return None
    quadro = quadro_da_ficha(con, titulo_id)
    if not quadro or not quadro["trava"]:
        return None
    este, irmaos, protocolo = quadro["este"], quadro["irmaos"], quadro["protocolo"]
    if situacao_antes:
        este = {**este, "situacao": situacao_antes}
    travam = quadro["travam"]
    n, v = _numero(numero), _vencimento(vencimento)
    precisa_venc = bool(_vencimento(este.get("data_vencimento")))
    lista = "; ".join(_rotulo(t) for t in [este, *irmaos])
    papel = NO_PAPEL.get(ato, "no papel")

    falta: str | None = None
    conselho = (
        "Se, conferido o papel, você tem certeza de que é este título, marque "
        "«Afirmo» e escreva por quê — a afirmação fica gravada no ato, com o "
        "seu nome.")
    if not n or (precisa_venc and not v):
        falta = (
            f"Este título tem irmão em aberto no mesmo protocolo {protocolo}: "
            f"{'; '.join(_rotulo(t) for t in travam)}. Antes de lançar "
            f"{O_ATO[ato]}, confira {papel} QUAL título é, e digite no "
            f"quadro «Qual título está no papel?» o número e o vencimento que "
            f"estão NO PAPEL — não os da tela.")
        conselho = (
            "Se o papel não traz número nem vencimento, marque «Afirmo» e "
            "escreva por que este é o título certo — a afirmação fica gravada "
            "no ato, com o seu nome.")
    else:
        bate_este = _bate(este, n, v)
        batem_irmaos = [t for t in irmaos if t["distinguivel"] and _bate(t, n, v)]
        if bate_este and batem_irmaos:
            falta = (
                f"O número e o vencimento digitados servem a mais de um título "
                f"do protocolo {protocolo} ({lista}). Digite o número do título "
                f"como está no papel — com a parcela, se houver —, e não o nosso "
                f"número.")
        elif not bate_este and batem_irmaos:
            irmao = batem_irmaos[0]
            falta = (
                f"O número e o vencimento digitados são do título "
                f"{_rotulo(irmao)} — o IRMÃO deste no protocolo {protocolo} —, "
                f"e não deste ({_rotulo(este)}). {O_ATO[ato].capitalize()} vai "
                f"na ficha do {irmao['numero_titulo']}: abra-o pelo quadro "
                f"«Títulos irmãos» desta ficha.")
        elif not bate_este:
            falta = (
                f"O número e o vencimento digitados ({numero or '—'}, "
                f"{_br(v) if v else 'sem vencimento'}) não conferem com nenhum "
                f"título do protocolo {protocolo}. Os títulos dele são: {lista}. "
                f"Confira {papel} e digite de novo.")

    detalhe: dict[str, Any]
    if falta is None:
        detalhe = {"titulo_conferido": {
            "numero": str(numero or "").strip(), "vencimento": v or None,
            "protocolo": protocolo,
            "irmaos_em_aberto": [_rotulo(t) for t in travam],
            "por": quem, "em": agora}}
    else:
        texto = _afirmacao(afirmo, afirmacao, por_robo=por_robo,
                           o_que_faltava=falta, ato=ato)
        if texto is None:
            raise TituloIrmaoError(f"{falta} {conselho} Nada foi lançado.")
        detalhe = {"afirmacao_expressa": {
            "regra": REGRA, "afirmacao": texto, "o_que_faltava": falta,
            "ato": ato, "por": quem, "em": agora}}
    return _gravar_no_ato(con, ato_id, detalhe)


def _gravar_no_ato(con, ato_id: int, detalhe: dict) -> dict:
    """Junta a conferência ao `detalhe_json` do ato, sem apagar o que o
    domínio já gravou ali. ESCREVE."""
    bd = banco(con)
    linha = bd.um("SELECT detalhe_json FROM pt_atos WHERE id=%s", (int(ato_id),))
    try:
        atual = json.loads((linha or {}).get("detalhe_json") or "{}")
    except (TypeError, ValueError):
        atual = {}
    if not isinstance(atual, dict):
        atual = {}
    atual.update(detalhe)
    bd.escrever("UPDATE pt_atos SET detalhe_json=%s WHERE id=%s",
                (json.dumps(atual, ensure_ascii=False), int(ato_id)))
    return detalhe


def _conferir_o_protesto(con, titulo_id: int, ato_id: int, *, afirmo: bool,
                         afirmacao: Any, por_robo: bool, quem: str | None,
                         agora: str | None,
                         situacao_antes: str | None) -> dict | None:
    """A trava do protesto: o irmão de vencimento posterior PAGO com o mesmo
    valor. Vence só com a afirmação expressa. ESCREVE no ato quando vence."""
    achado = _grupos_de(banco(con), [titulo_id]).get(int(titulo_id))
    if not achado:
        return None
    este, irmaos = achado
    if situacao_antes:
        este = {**este, "situacao": situacao_antes}
    trava = _trava_do_protesto(este, irmaos)
    if not trava:
        return None
    falta = trava["motivo"]
    texto = _afirmacao(afirmo, afirmacao, por_robo=por_robo,
                       o_que_faltava=falta, ato="PROTESTO")
    if texto is None:
        raise TituloIrmaoError(
            f"{falta} O protesto deste título só se lavra pela FICHA, com "
            f"afirmação expressa — marque «Afirmo» e escreva por que este é o "
            f"título certo; fica gravada no ato e na auditoria, com o seu "
            f"nome. Nada foi lavrado.")
    af = {"regra": REGRA_PROTESTO, "afirmacao": texto, "o_que_faltava": falta,
          "ato": "PROTESTO", "por": quem, "em": agora}
    # NO ATO DO PROTESTO A CHAVE `afirmacao_expressa` É DA PROVA DA INTIMAÇÃO
    # (`protesto.lancar_protesto`, 29/10/2026). As duas travas podem ser
    # vencidas no mesmo ato, e gravar por cima apagaria a outra: a dos irmãos
    # fica ao lado, com nome próprio. A rota recebe a de sempre e audita.
    _gravar_no_ato(con, ato_id, {"afirmacao_expressa_irmaos": af})
    return {"afirmacao_expressa": af}


# ------------------------------------------------------------ a conferência


def _incoerencias_do_grupo(grupo: list[dict]) -> list[str]:
    """As frases do que não se explica junto num protocolo. Só calcula."""
    frases: list[str] = []
    pagos = [t for t in grupo if t["situacao"] == "PAGO"]
    for p in pagos:
        for o in grupo:
            if o is p:
                continue
            mesmo_valor = (int(o.get("valor_centavos") or 0)
                           == int(p.get("valor_centavos") or 0))
            if o["situacao"] == "PROTESTADO" and mesmo_valor:
                frases.append(
                    f"{p['numero_titulo']} está PAGO e {o['numero_titulo']} "
                    f"está PROTESTADO, com o mesmo valor ({p['valor_br']}): "
                    f"confira se o pagamento não era do protestado.")
            vp, vo = _vencimento(p.get("data_vencimento")), _vencimento(
                o.get("data_vencimento"))
            if (vp and vo and vp > vo and o["situacao"] in SITUACOES_EM_ABERTO):
                frases.append(
                    f"{p['numero_titulo']} (vencimento {p['vencimento_br']}) "
                    f"está PAGO e {o['numero_titulo']}, de vencimento ANTERIOR "
                    f"({o['vencimento_br']}), continua {o['situacao']}: confira "
                    f"no comprovante qual dos dois foi pago.")
            if o["situacao"] in ("RECEBIDO", "APONTADO"):
                frases.append(
                    f"{p['numero_titulo']} está PAGO e {o['numero_titulo']} "
                    f"nem foi intimado ({o['situacao']}).")
    for i, a in enumerate(grupo):
        for b in grupo[i + 1:]:
            if (_chave(a) == _chave(b) and a["situacao"] != b["situacao"]
                    and int(a.get("valor_centavos") or 0)
                    == int(b.get("valor_centavos") or 0)):
                frases.append(
                    f"O mesmo título ({a['numero_titulo']}, vencimento "
                    f"{a['vencimento_br']}) está {a['situacao']} numa linha e "
                    f"{b['situacao']} na outra: a mesma dívida não costuma ter "
                    f"dois desfechos.")
    return list(dict.fromkeys(frases))


def irmaos_incoerentes(con) -> dict:
    """Os protocolos com mais de um título, e os que têm situações que não se
    explicam juntas. Só LÊ."""
    bd = banco(con)
    protocolos = [str(r["protocolo"]).strip() for r in bd.ler(
        """SELECT protocolo FROM pt_titulos
            WHERE protocolo IS NOT NULL AND protocolo <> ''
            GROUP BY protocolo HAVING COUNT(*) > 1
            ORDER BY protocolo""")]
    grupos: dict[str, list[dict]] = {}
    for t in _titulos_dos_protocolos(bd, protocolos):
        grupos.setdefault(str(t["protocolo"]).strip(), []).append(t)
    incoerentes = []
    for p, grupo in grupos.items():
        frases = _incoerencias_do_grupo(grupo)
        if frases:
            incoerentes.append({"protocolo": p, "titulos": grupo,
                                "frases": frases})
    return {"protocolos": len(grupos), "incoerentes": incoerentes}


# O CEDENTE NO REGISTRO DE ORIGEM. As colunas do E-Ofício (`tbSDT`) são os
# campos do registro da remessa na ordem do layout — a mesma correspondência
# de `protesto_cenprot_xml.registro_da_cra`, que lê `Campo01..Campo30` de
# `protesto_arquivo.TITULO_NA_REMESSA[:30]`. Calculada daqui, e não escrita.
_COLUNA_NO_ACERVO = {c.nome: f"Campo{i:02d}"
                     for i, c in enumerate(PA.TITULO_NA_REMESSA[:30], start=1)}
_CAMPOS_DO_CEDENTE = ("cedente_nome", "cedente_nome_2")


def _do_acervo_em_lote(acervo) -> dict[str, dict]:
    """As linhas da remessa que o E-Ofício guardou, por protocolo: só os nomes
    do cedente e do sacador. UMA leitura para a casa inteira — título a título
    seriam 1.400 consultas ao arquivo. Só LÊ. A primeira linha de cada
    protocolo vale, como em `registro_da_cra` (`ORDER BY intChave`)."""
    if acervo is None:
        return {}
    colunas = [_COLUNA_NO_ACERVO[c] for c in _CAMPOS_DO_CEDENTE
               if c in _COLUNA_NO_ACERVO]
    if len(colunas) != len(_CAMPOS_DO_CEDENTE):
        return {}
    saida: dict[str, dict] = {}
    try:
        linhas = acervo.execute(
            f"SELECT intProtocolo, {', '.join(colunas)} FROM tbSDT "
            f"ORDER BY intChave").fetchall()
    except Exception:                                    # noqa: BLE001
        # acervo sem a tabela (instalação nova, ou outro arquivo): não há
        # registro de origem por aqui, e a conferência diz quantos ficaram sem
        return {}
    for linha in linhas:
        prot = linha[0]
        if prot is None:
            continue
        try:
            chave = str(int(float(prot)))
        except (TypeError, ValueError):
            continue
        saida.setdefault(chave, {c: str(linha[i + 1] or "").strip()
                                 for i, c in enumerate(_CAMPOS_DO_CEDENTE)})
    return saida


def _registro_de_origem(bd, titulo: dict, acervo_em_lote: dict,
                        remessas: dict) -> tuple[dict | None, str | None]:
    """O registro de origem do título e de onde ele veio. Só LÊ.

    A ORDEM É A DE `protesto_cenprot_xml.registro_da_cra`: a remessa que este
    sistema recebeu, o pedido da CENPROT, a linha do E-Ofício. A remessa se lê
    UMA vez por arquivo (`remessas`), e não uma vez por título.
    """
    chave = str(titulo.get("origem_chave") or "").strip()
    if titulo.get("remessa_id") and chave.startswith("CRA:"):
        rid = int(titulo["remessa_id"])
        if rid not in remessas:
            linha = bd.um("SELECT conteudo FROM pt_remessas WHERE id = %s", (rid,))
            try:
                remessas[rid] = PA.ler(linha["conteudo"]) if linha else None
            except Exception:                            # noqa: BLE001
                remessas[rid] = None
        lido = remessas[rid]
        try:
            posicao = int(chave.rsplit(":", 1)[1])
        except ValueError:
            posicao = 0
        if lido is not None and 0 < posicao <= len(lido.titulos):
            return lido.titulos[posicao - 1], "REMESSA"
    import cenprot_pendencias as PEND
    if chave.startswith(PEND.PREFIXO_DA_ORIGEM_DO_PEDIDO):
        teor = PEND.teor_do_pedido(
            bd, chave[len(PEND.PREFIXO_DA_ORIGEM_DO_PEDIDO):])
        if teor is not None:
            return PEND.registro_do_pedido(teor), "PEDIDO"
    protocolo = str(titulo.get("protocolo") or "").strip()
    if protocolo in acervo_em_lote:
        return acervo_em_lote[protocolo], "ACERVO"
    return None, None


def _confere_cedente(gravado: Any, registro: dict) -> tuple[bool, list[str]]:
    nomes = list(dict.fromkeys(
        str(registro.get(c) or "").strip() for c in _CAMPOS_DO_CEDENTE
        if str(registro.get(c) or "").strip()))
    return any(_mesmo_nome(gravado, n) for n in nomes), nomes


def cedentes_divergentes(con, acervo=None) -> dict:
    """Os títulos cujo cedente gravado não é o do registro de origem. Só LÊ.

    Compara com o nome do cedente E com o do sacador do registro (o campo do
    sacador é onde o cedente às vezes vem), sem acento, sem pontuação e
    admitindo o corte das 45 posições da CRA. Registro de origem sem nome
    nenhum não conta como divergência: não há com o que conferir.
    """
    bd = banco(con)
    em_lote = _do_acervo_em_lote(acervo)
    remessas: dict[int, Any] = {}
    divergentes, conferidos, sem_registro = [], 0, 0
    for t in bd.ler(
            """SELECT id, numero_titulo, protocolo, situacao, origem,
                      origem_chave, remessa_id, cedente_nome
                 FROM pt_titulos ORDER BY id"""):
        t = dict(t)
        registro, de_onde = _registro_de_origem(bd, t, em_lote, remessas)
        if registro is None:
            sem_registro += 1
            continue
        confere, nomes = _confere_cedente(t.get("cedente_nome"), registro)
        if not nomes:
            sem_registro += 1
            continue
        conferidos += 1
        if not confere:
            divergentes.append({**t, "nomes_na_origem": nomes,
                                "de_onde": DE_ONDE.get(de_onde, de_onde),
                                "origem_do_registro": de_onde})
    return {"conferidos": conferidos, "sem_registro": sem_registro,
            "divergentes": divergentes,
            "vazios": sum(1 for d in divergentes
                          if not str(d.get("cedente_nome") or "").strip())}


def cedente_da_origem(con, titulo: dict, acervo=None) -> dict | None:
    """O cedente do registro de origem DESTE título, para a ficha. Só LÊ.
    None quando não há registro de origem com nome."""
    bd = banco(con)
    em_lote: dict[str, dict] = {}
    protocolo = str((titulo or {}).get("protocolo") or "").strip()
    if acervo is not None and protocolo.isdigit():
        colunas = [_COLUNA_NO_ACERVO[c] for c in _CAMPOS_DO_CEDENTE]
        try:
            linha = acervo.execute(
                f"SELECT {', '.join(colunas)} FROM tbSDT "
                f"WHERE intProtocolo = :protocolo ORDER BY intChave LIMIT 1",
                {"protocolo": int(protocolo)}).fetchone()
        except Exception:                                # noqa: BLE001
            linha = None
        if linha is not None:
            em_lote[protocolo] = {c: str(linha[i] or "").strip()
                                  for i, c in enumerate(_CAMPOS_DO_CEDENTE)}
    registro, de_onde = _registro_de_origem(bd, dict(titulo or {}), em_lote, {})
    if registro is None:
        return None
    confere, nomes = _confere_cedente((titulo or {}).get("cedente_nome"), registro)
    if not nomes:
        return None
    return {"confere": confere, "nomes": nomes,
            "de_onde": DE_ONDE.get(de_onde, de_onde)}


def resumo_para_o_painel(con, acervo=None) -> dict:
    """A linha do painel do protesto: quantos irmãos incoerentes e quantos
    cedentes divergentes. Só LÊ."""
    irm = irmaos_incoerentes(con)
    ced = cedentes_divergentes(con, acervo)
    return {"protocolos": irm["protocolos"],
            "irmaos_incoerentes": len(irm["incoerentes"]),
            "cedentes_divergentes": len(ced["divergentes"]),
            "cedentes_conferidos": ced["conferidos"],
            "cedentes_sem_registro": ced["sem_registro"]}


# A ORIGEM DE CADA PENDÊNCIA, como o roteiro do protesto a lê. O roteiro
# ignora a linha com origem «ACERVO» — o cedente que só se confere contra a
# linha do E-Ofício, e que estava errado em quase todo o acervo (1.404 de
# 1.407 em 29/10/2026, antes da correção das 15h41): no roteiro do dia ele
# afogaria o resto. Ele continua na conferência inteira, em «Conferência dos
# títulos».
ORIGEM_IRMAOS = "IRMAOS"


def pendencias_dos_irmaos(con) -> list[dict]:
    """O que o ROTEIRO DO PROTESTO mostra como pendência desta conferência. Só
    LÊ.

    O CONTRATO COM O ROTEIRO (29/10/2026): ele chama esta função pelo nome,
    passando só a conexão, e lê de cada linha `titulo_id`, `numero_titulo`,
    `protocolo`, `explicacao` (o que falta conferir, curto) e `origem`.
    Uma linha por título:
      - de cada protocolo com irmãos em situações que não se explicam juntas
        (origem «IRMAOS»);
      - de cada título cujo cedente diverge do registro de origem que está NO
        SISTEMA — a remessa da CRA ou o pedido da CENPROT (origem «REMESSA»
        ou «PEDIDO»). Sem a conexão do acervo, a linha do E-Ofício não entra:
        quem a lê é a conferência inteira.
    """
    linhas: list[dict] = []
    for g in irmaos_incoerentes(con)["incoerentes"]:
        mais = len(g["frases"]) - 1
        explicacao = (f"Irmãos do protocolo {g['protocolo']}: {g['frases'][0]}"
                      + (f" (e mais {mais} ponto(s) na conferência)" if mais else ""))
        for t in g["titulos"]:
            linhas.append({"titulo_id": int(t["id"]),
                           "numero_titulo": t["numero_titulo"],
                           "protocolo": g["protocolo"],
                           "explicacao": explicacao,
                           "origem": ORIGEM_IRMAOS})
    for d in cedentes_divergentes(con, None)["divergentes"]:
        gravado = str(d.get("cedente_nome") or "").strip() or "vazio"
        linhas.append({
            "titulo_id": int(d["id"]), "numero_titulo": d["numero_titulo"],
            "protocolo": d.get("protocolo"),
            "explicacao": (f"O cedente gravado ({gravado}) não é o de "
                           f"{d['de_onde']} ({' / '.join(d['nomes_na_origem'])}): "
                           f"confira antes do aviso e do instrumento."),
            "origem": d["origem_do_registro"]})
    return linhas
