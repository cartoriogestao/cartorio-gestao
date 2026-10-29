"""O SELO QUE FALTOU num ato do Protesto, emitido depois, pelo item que já está
pago no protocolo.

O CASO, medido na produção em 29/10/2026 (só leitura): o pagamento do título
9614 (ato 4131, protocolo de atendimento 2026.10.149) foi lavrado pela ficha às
19h56. Saíram SETE selos — 17.2, 17.10.1, 17.7 e quatro do 17.9, cada um com a
sua cobertura CONFIRMADA —, e o do item 17.4.5 falhou: a auditoria tem
`SELO_RESERVA_ESTORNADA` com a referência `pt_atos:4131:17.4.5:1`, o item 32842
e o motivo «o selador falhou ou recusou». É o defeito do ato 4127: o selo foi
pedido pela FAIXA (17.4.5), e o aparelho só conhece o ITEM (17.4). O PR #109
passou a mandar o item; o 4131 ficou com o item pago, sem o selo, e o Protesto
não tinha «selar depois».

O QUE ESTE MÓDULO FAZ
    - `itens_sem_selo`: os itens PAGOS do protocolo do ato que ainda não têm
      selo confirmado, conferindo `cx_selo_coberturas` CONFIRMADA (e o razão
      `sd_selos`) contra as unidades de cada item. Só LÊ.
    - `pendencias`: a mesma conta para o painel e a ficha — a obrigação
      «falta o selo do item X — emita na ficha», que entra em
      `protesto_selo_previo.pendencias_do_selo`. Só LÊ.
    - `preparar` / `concluir` / `desfazer`: as três escritas da ação «Emitir o
      selo que faltou». O PEDIDO AO APARELHO É DA ROTA, fora de transação, pelo
      mesmo caminho do lançamento (`atribuicoes_web._selar_o_protesto`), já com
      a conversão faixa→item do #109.

O ITEM É DO ATO SÓ COM RASTRO, e não por estar no mesmo protocolo. «O normal é
um protocolo para todo o trabalho pedido pelo cliente» (o oficial, 11/09/2026):
o protocolo de dois pagamentos traz os itens dos dois, e o item do título que
ainda não se lavrou não é «selo que faltou» do primeiro. Rastro é: a ligação do
item a este ato (`cx_item_do_ato`, `usado_por_*`), uma cobertura deste ato com
o item, ou a tentativa de selo deste ato que o aparelho recusou com o item na
reserva (`SELO_RESERVA_ESTORNADA`). O 4131/17.4.5 tem só a última — e basta.

COMO SE EMITE, E POR QUE ASSIM
    O selo pago procura o item ligado ao ato (`ato_selado.cobrir_o_selo`, passo
    1). `preparar` liga o item ao ato com a marca do quadro do selo
    (`caixa_protocolo.ORIGEM_QUADRO`), SEM gastar a unidade; a rota pede o selo;
    `concluir` gasta a unidade só depois de o selo sair, e `desfazer` tira a
    ligação se ele não saiu. Falha do selador não muda nada: nem o item, nem o
    caixa, nem o ato. A cobertura e o `sd_selos` gravam-se como no lançamento
    normal, pela mesma trava — e nenhum ato novo se lavra, nem se cobra de novo.

AS TRAVAS: robô não emite, e só o oficial (ADMIN) em pessoa; ato cancelado não
se sela; item que já tem selo não se sela de novo; item que não está pago no
protocolo é recusado. Todas antes de qualquer escrita, com frase de balcão. E
o código que o caminho do ato nunca selou (o 17.4.5 do cancelamento 4106, que o
aparelho recusou) só se pede de novo com afirmação expressa — a régua do selo
prévio, e não uma nova.
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime
from typing import Any

import ato_selado as AS
import caixa_protocolo as CXP
import protesto_selo_previo as PSELO
from bd_nativo import banco

TABELA = "pt_atos"

#: A auditoria da emissão — com o ato, o item e o selo. FORA da transação,
#: como todo `audit` da casa.
ACAO_DA_AUDITORIA = "SELO_EMITIDO_DEPOIS"

#: A espécie da obrigação em `protesto_selo_previo.pendencias_do_selo`.
ESPECIE = PSELO.ESPECIE_ITEM_SEM_SELO

#: Quem emite: o oficial, em pessoa. Nem o substituto (MANAGER) nem o robô —
#: o selo pede o dinheiro do cliente ao aparelho, fora do lançamento.
PAPEL_QUE_EMITE = "ADMIN"

#: A tentativa de selo que o aparelho recusou deixa esta linha na auditoria,
#: com a referência, o item e o motivo (`ato_selado._estornar_reserva`).
ACAO_DA_RESERVA_ESTORNADA = "SELO_RESERVA_ESTORNADA"

#: As situações da cobertura que contam como «já tem selo» — a confirmada, e a
#: reservada de um pedido em voo (pedir de novo pagaria duas vezes).
COBERTURA_QUE_CONTA = (AS.CONFIRMADA, AS.RESERVADA)

#: A ligação que `preparar` deixa sem unidade é de uma emissão em andamento.
#: Passado o prazo da reserva do selo, ela é sobra de um clique que caiu.
PRAZO_DA_EMISSAO_EM_SEGUNDOS = AS.PRAZO_DA_RESERVA_EM_SEGUNDOS

LIMITE_DA_LISTA = 200


class SeloQueFaltouError(ValueError):
    """Impedimento da emissão, com frase pronta para o balcão."""


# ======================================================= a conta (só lê)


def _o_ato(tipo: Any) -> str:
    return PSELO.O_ATO.get(str(tipo or "").strip().upper(), "o ato")


def _int(valor: Any, padrao: int = 0) -> int:
    try:
        return int(valor)
    except (TypeError, ValueError):
        return padrao


def _quantidade(item: dict) -> int:
    """Quantas unidades o item tem — a mesma regra do caixa: sem quantidade,
    uma."""
    n = _int(item.get("quantidade"), 1)
    return n if n > 0 else 1


def _ato(bd, ato_id: int) -> dict | None:
    return bd.um(
        """SELECT a.*, t.numero_titulo, t.protocolo AS protocolo_do_titulo
             FROM pt_atos a JOIN pt_titulos t ON t.id = a.titulo_id
            WHERE a.id = %s""", (int(ato_id),))


def _cancelado(ato: dict) -> bool:
    return _int(ato.get("cancelado")) != 0


def _sela(ato: dict) -> bool:
    """O ato é dos que selam na ficha, e tem caminho de selo? Só calcula."""
    tipo = str(ato.get("tipo") or "").strip().upper()
    return (tipo in PSELO.TIPOS_QUE_SELAM
            and tipo not in PSELO.ATOS_SEM_SELO_PROPRIO
            and bool(AS.caminho_do_ato(TABELA, tipo)))


def _tentativas(bd, ato_id: int) -> list[dict]:
    """As tentativas de selo deste ato que o aparelho recusou, com o item da
    reserva. Só LÊ."""
    if not bd.tem_tabela("audit_logs"):
        return []
    saida = []
    for r in bd.ler(
            """SELECT ts, details FROM audit_logs
                WHERE action = %s AND entity_type = %s AND entity_id = %s
                ORDER BY id""",
            (ACAO_DA_RESERVA_ESTORNADA, TABELA, int(ato_id))):
        try:
            d = json.loads(r.get("details") or "{}")
        except ValueError:
            d = {}
        if not isinstance(d, dict):
            continue
        saida.append({"quando": str(r.get("ts") or ""),
                      "item_id": _int(d.get("item_id"), 0) or None,
                      "referencia": str(d.get("referencia") or ""),
                      "motivo": str(d.get("motivo") or "")})
    return saida


def _protocolos_do_ato(bd, ato: dict, tentativas: list[dict]) -> list[int]:
    """Os protocolos do balcão ligados a este ato, por qualquer rastro. Só LÊ."""
    ato_id = int(ato["id"])
    ids: set[int] = set()
    if ato.get("protocolo_id"):
        ids.add(int(ato["protocolo_id"]))
    consultas = []
    if bd.tem_tabela("cx_item_do_ato"):
        consultas.append(("""SELECT DISTINCT protocolo_id FROM cx_item_do_ato
                              WHERE tabela = %s AND ato_id = %s""",
                          (TABELA, ato_id)))
    if bd.tem_tabela("cx_selo_coberturas"):
        consultas.append(("""SELECT DISTINCT protocolo_id FROM cx_selo_coberturas
                              WHERE tabela = %s AND ato_id = %s
                                AND protocolo_id IS NOT NULL""",
                          (TABELA, ato_id)))
    if bd.tem_tabela("cx_protocolo_atos"):
        consultas.append(("""SELECT DISTINCT protocolo_id FROM cx_protocolo_atos
                              WHERE usado_por_tabela = %s AND usado_por_ato_id = %s""",
                          (TABELA, ato_id)))
        do_estorno = [t["item_id"] for t in tentativas if t["item_id"]]
        if do_estorno:
            consultas.append(("""SELECT DISTINCT protocolo_id FROM cx_protocolo_atos
                                  WHERE id = ANY(%s)""", (do_estorno,)))
    if bd.tem_tabela("cx_lancamentos"):
        consultas.append(("""SELECT DISTINCT protocolo_id FROM cx_lancamentos
                              WHERE origem = 'ATO' AND origem_chave LIKE %s
                                AND protocolo_id IS NOT NULL
                                AND coalesce(estornado, 0) = 0""",
                          (f"{TABELA}:{ato_id}:%",)))
    for sql, args in consultas:
        for r in bd.ler(sql, args):
            if r.get("protocolo_id") is not None:
                ids.add(int(r["protocolo_id"]))
    return sorted(ids)


def _codigo_da_referencia(referencia: Any) -> str | None:
    """`pt_atos:4131:17.2:1` → `17.2`; a referência sem código → None."""
    partes = [p.strip() for p in str(referencia or "").split(":")]
    return partes[2] if len(partes) >= 3 and partes[2] else None


def quadro_do_ato(con, ato_id: int) -> dict | None:
    """Cada item dos protocolos do ato, com a conta das unidades. Só LÊ.

    Devolve `{ato, caminho, itens}` — ou None quando o ato não existe. Cada
    item diz se está pago, se é gratuito, se tem rastro neste ato, quantas
    unidades outros atos já levaram (`outros`), quantas têm cobertura deste ato
    (`cobertos`) e quantas sobram sem selo (`livres`). O que é pendência é o
    item pago, com rastro e com unidade livre (`itens_sem_selo`).
    """
    bd = banco(con)
    ato = _ato(bd, ato_id)
    if not ato:
        return None
    ato_id = int(ato["id"])
    caminho = AS.caminho_do_ato(TABELA, ato.get("tipo"))
    tentativas = _tentativas(bd, ato_id)
    quadro = {"ato": ato, "caminho": caminho, "tentativas": tentativas,
              "itens": []}
    if not caminho or not bd.tem_tabela("cx_protocolo_atos"):
        return quadro
    protocolos = _protocolos_do_ato(bd, ato, tentativas)
    if not protocolos:
        return quadro
    itens = bd.ler(
        """SELECT i.*, p.numero AS protocolo_numero,
                  p.situacao AS protocolo_situacao,
                  p.atribuicao AS protocolo_atribuicao
             FROM cx_protocolo_atos i
             JOIN cx_protocolos p ON p.id = i.protocolo_id
            WHERE i.protocolo_id = ANY(%s)
              AND i.codigo_ato IS NOT NULL AND btrim(i.codigo_ato) <> ''
            ORDER BY i.id""", (protocolos,))
    if not itens:
        return quadro
    ids = [int(i["id"]) for i in itens]
    rastro = (bd.ler("""SELECT item_id, tabela, ato_id, unidades, origem
                          FROM cx_item_do_ato WHERE item_id = ANY(%s)""", (ids,))
              if bd.tem_tabela("cx_item_do_ato") else [])
    coberturas = (bd.ler("""SELECT item_id, tabela, ato_id, referencia, situacao
                              FROM cx_selo_coberturas
                             WHERE item_id = ANY(%s)""", (ids,))
                  if bd.tem_tabela("cx_selo_coberturas") else [])
    deste = (TABELA, ato_id)
    # OS CÓDIGOS QUE JÁ SAÍRAM EM SELO POR ESTE CAMINHO — a régua do selo
    # prévio (`protesto_selo_previo`): o item fora dela o aparelho já recusou
    # uma vez, e pedir de novo só com afirmação expressa.
    servem = PSELO._servem_ao_caminho(bd, caminho, TABELA)
    for it in itens:
        iid = int(it["id"])
        meus = [r for r in rastro if int(r["item_id"]) == iid]
        cobs = [c for c in coberturas if int(c["item_id"]) == iid
                and str(c.get("situacao") or "") in COBERTURA_QUE_CONTA]
        usado_por = (str(it.get("usado_por_tabela") or ""),
                     _int(it.get("usado_por_ato_id"), 0))
        # O QUE OUTROS ATOS JÁ LEVARAM DESTE ITEM: a maior das três contas,
        # porque cada caminho da casa deixa um rastro diferente (a unidade
        # gasta, a cobertura sem unidade, o rastro antigo de um ato só).
        outros = max(
            sum(_int(r.get("unidades")) for r in meus
                if (str(r["tabela"]), int(r["ato_id"])) != deste),
            sum(1 for c in cobs
                if (str(c.get("tabela") or ""), _int(c.get("ato_id"))) != deste),
            1 if usado_por[0] and usado_por != deste else 0)
        cobertos = sum(1 for c in cobs
                       if (str(c.get("tabela") or ""), _int(c.get("ato_id"))) == deste)
        # A UNIDADE QUE O QUADRO DO SELO JÁ GASTOU PARA ESTE ATO e que ainda
        # não tem selo: ligada à mão («Para selar este ato falta»), ela já saiu
        # do saldo do item — a emissão não a gasta de novo.
        preconsumidas = max(0, sum(
            _int(r.get("unidades")) for r in meus
            if (str(r["tabela"]), int(r["ato_id"])) == deste
            and str(r.get("origem") or "") != CXP.ORIGEM_SELO) - cobertos)
        falhou = [t for t in tentativas if t["item_id"] == iid]
        rastro_deste = (
            any((str(r["tabela"]), int(r["ato_id"])) == deste for r in meus)
            or cobertos > 0 or usado_por == deste or bool(falhou))
        gratuito = CXP.item_gratuito(it, bd)
        codigo = str(it["codigo_ato"]).strip()
        codigo_selo = PSELO.codigo_para_o_selo(codigo, caminho)
        quadro["itens"].append({
            "item_id": iid, "codigo": codigo,
            "codigo_selo": codigo_selo, "serve": codigo_selo in servem,
            "protocolo_id": int(it["protocolo_id"]),
            "protocolo_numero": it.get("protocolo_numero"),
            "valor_total": it.get("valor_total"),
            "quantidade": _quantidade(it),
            "pago": CXP.item_pago(it) and not gratuito,
            "gratuito": gratuito,
            "do_ato": rastro_deste,
            "outros": outros, "cobertos": cobertos,
            "preconsumidas": preconsumidas,
            "livres": max(0, _quantidade(it) - outros - cobertos),
            "tentativa": falhou[-1] if falhou else None,
        })
    _abater_os_selos_sem_cobertura(bd, quadro)
    return quadro


def _abater_os_selos_sem_cobertura(bd, quadro: dict) -> None:
    """O selo do ato que não passou por cobertura com item também é selo.

    O de antes da trava (19/10/2026), o coberto pelo lançamento do próprio ato,
    o da trava desligada: todos estão no razão (`sd_selos`) com a referência
    `pt_atos:<ato>:<código>:<n>`, e nenhum tem `item_id` na cobertura. Cada um
    abate uma unidade livre do mesmo código de selo; o que não diz o código (a
    referência antiga, de um ato só) abate de qualquer um. Na dúvida, o item
    sai da lista: pedir selo para quem já tem é o erro que custa dinheiro.
    """
    if not bd.tem_tabela("sd_selos"):
        return
    ato_id = int(quadro["ato"]["id"])
    caminho = quadro["caminho"]
    por_codigo: Counter = Counter()
    sem_codigo = 0
    for s in bd.ler("""SELECT referencia FROM sd_selos
                        WHERE tabela = %s AND ato_id = %s
                          AND cancelado_em IS NULL""", (TABELA, ato_id)):
        codigo = _codigo_da_referencia(s.get("referencia"))
        if codigo:
            por_codigo[PSELO.codigo_para_o_selo(codigo, caminho)] += 1
        else:
            sem_codigo += 1
    cobertos: Counter = Counter()
    for linha in quadro["itens"]:
        cobertos[linha["codigo_selo"]] += linha["cobertos"]
    candidatos = [x for x in quadro["itens"] if x["do_ato"] and x["livres"] > 0]
    for codigo, n in por_codigo.items():
        sobra = max(0, n - cobertos[codigo])
        for linha in candidatos:
            if not sobra:
                break
            if linha["codigo_selo"] == codigo and linha["livres"] > 0:
                tira = min(sobra, linha["livres"])
                linha["livres"] -= tira
                sobra -= tira
    for linha in candidatos:
        if not sem_codigo:
            break
        tira = min(sem_codigo, linha["livres"])
        linha["livres"] -= tira
        sem_codigo -= tira


def itens_sem_selo(con, ato_id: int) -> list[dict]:
    """Os itens PAGOS no protocolo deste ato que ainda não têm selo. Só LÊ.

    Ato cancelado, ato do acervo e ato que não sela não têm lista: não há o
    que emitir neles. Cada linha diz quantas unidades faltam (`livres`).
    """
    quadro = quadro_do_ato(con, ato_id)
    if not quadro:
        return []
    ato = quadro["ato"]
    if (_cancelado(ato) or not _sela(ato)
            or str(ato.get("origem") or "") == AS.MARCA_DO_ACERVO):
        return []
    return [x for x in quadro["itens"]
            if x["do_ato"] and x["pago"] and x["livres"] > 0]


def _data_br(texto: Any) -> str:
    bruto = str(texto or "")[:10]
    if len(bruto) == 10 and bruto[4] == "-" and bruto[7] == "-":
        return f"{bruto[8:10]}/{bruto[5:7]}/{bruto[0:4]}"
    return bruto or "data não gravada"


def _candidatos(bd, titulo_id: int | None) -> list[int]:
    """Os atos que PODEM ter item pago sem selo — o filtro largo, em SQL. Só
    LÊ. A conta de verdade é a de `itens_sem_selo`, ato por ato.

    PARTE DAS TABELAS PEQUENAS, e não de todos os atos: a tentativa que o
    aparelho recusou (a auditoria do estorno) e o item ligado ao ato com
    unidade sem cobertura. Medido na produção em 30/10/2026: a primeira forma,
    que olhava cada ato do Protesto, levava 376 ms na tela da lista; esta,
    menos de 20.
    """
    if not bd.tem_tabela("cx_protocolo_atos"):
        return []
    tem_cobertura = bd.tem_tabela("cx_selo_coberturas")
    cobertos = ("""(SELECT count(*) FROM cx_selo_coberturas c
                     WHERE c.item_id = i.id AND c.situacao = ANY(%s))"""
                if tem_cobertura else "0")
    com_cobertura = [list(COBERTURA_QUE_CONTA)] if tem_cobertura else []
    partes: list[str] = []
    args: list[Any] = []
    if bd.tem_tabela("audit_logs"):
        partes.append("""SELECT entity_id AS ato_id FROM audit_logs
                          WHERE action = %s AND entity_type = %s""")
        args += [ACAO_DA_RESERVA_ESTORNADA, TABELA]
    if bd.tem_tabela("cx_item_do_ato"):
        partes.append(f"""SELECT v.ato_id FROM cx_item_do_ato v
                            JOIN cx_protocolo_atos i ON i.id = v.item_id
                           WHERE v.tabela = %s
                             AND coalesce(i.quantidade, 1) > {cobertos}""")
        args += [TABELA, *com_cobertura]
    partes.append(f"""SELECT i.usado_por_ato_id FROM cx_protocolo_atos i
                       WHERE i.usado_por_tabela = %s
                         AND coalesce(i.quantidade, 1) > {cobertos}""")
    args += [TABELA, *com_cobertura]
    filtro = ""
    if titulo_id is not None:
        filtro = " AND a.titulo_id = %s"
    tipos = ",".join(["%s"] * len(PSELO.TIPOS_QUE_SELAM))
    sql = f"""SELECT a.id FROM pt_atos a
               WHERE a.id IN ({" UNION ".join(partes)})
                 AND coalesce(a.cancelado, 0) = 0
                 AND coalesce(a.origem, '') <> %s
                 AND a.tipo IN ({tipos}){filtro}
               ORDER BY a.id"""
    args += [AS.MARCA_DO_ACERVO, *PSELO.TIPOS_QUE_SELAM]
    if titulo_id is not None:
        args.append(int(titulo_id))
    return [int(r["id"]) for r in bd.ler(sql, args)]


def atos_com_item_sem_selo(con, *, titulo_id: int | None = None,
                           limite: int = LIMITE_DA_LISTA) -> list[dict]:
    """Os atos do Protesto com item pago sem selo confirmado. Só LÊ.

    Uma linha por ato, com os itens que faltam. É a medição do PR e a fonte das
    pendências: o 4131, com o 17.4.5, é o caso que a fez nascer.
    """
    bd = banco(con)
    saida = []
    for ato_id in _candidatos(bd, titulo_id):
        faltam = itens_sem_selo(bd, ato_id)
        if not faltam:
            continue
        ato = _ato(bd, ato_id)
        saida.append({"ato": ato, "itens": faltam})
        if len(saida) >= max(1, int(limite)):
            break
    return saida


def explicacao(ato: dict, item: dict) -> str:
    """A frase da obrigação, pronta para o roteiro e a ficha. Só calcula."""
    frase = (f"falta o selo do item {item['codigo']} — emita na ficha («Emitir "
             f"o selo que faltou»): {_o_ato(ato.get('tipo'))} (ato {ato['id']}, "
             f"de {_data_br(ato.get('criado_em'))}) tem o item pago no "
             f"protocolo {item.get('protocolo_numero') or item['protocolo_id']}")
    if item["livres"] > 1:
        frase += f", {item['livres']} unidades sem selo"
    if item["codigo_selo"] != item["codigo"]:
        frase += f"; o selo sai como {item['codigo_selo']}, o item do Tribunal"
    if item.get("tentativa"):
        t = item["tentativa"]
        frase += (f"; o aparelho recusou em {_data_br(t['quando'])}"
                  + (f" ({t['motivo']})" if t.get("motivo") else ""))
    if not item.get("serve", True):
        frase += (f"; atenção: o código {item['codigo_selo']} nunca saiu em "
                  f"selo por este caminho — pedir de novo só com afirmação "
                  "expressa, e o aparelho pode recusar outra vez")
    return frase + "."


def fora_do_caminho(item: dict, caminho: Any) -> str:
    """O que falta quando o código do item não serve ao caminho — a frase da
    afirmação expressa, no texto da regra do selo prévio. Só calcula."""
    recusou = (", e o aparelho já recusou o pedido dele uma vez"
               if item.get("tentativa") else "")
    return (f"o item {item['codigo']} (selo {item['codigo_selo']}) não saiu em "
            f"selo por este caminho ({caminho}){recusou}")


def pendencias(con, *, titulo_id: int | None = None,
               limite: int = LIMITE_DA_LISTA) -> list[dict]:
    """As obrigações «item pago sem selo», no contrato de
    `protesto_selo_previo.pendencias_do_selo`. Só LÊ.

    Uma linha por item, com `titulo_id`, `numero_titulo`, `protocolo` (o do
    título, como as outras linhas) e `explicacao` — o que o roteiro mostra.
    """
    saida = []
    for achado in atos_com_item_sem_selo(con, titulo_id=titulo_id,
                                         limite=limite):
        ato = achado["ato"]
        for item in achado["itens"]:
            saida.append({
                "especie": ESPECIE,
                "titulo_id": int(ato["titulo_id"]), "tipo": str(ato["tipo"]),
                "numero_titulo": ato.get("numero_titulo"),
                "protocolo": ato.get("protocolo_do_titulo"),
                "ato": _o_ato(ato.get("tipo")),
                "ato_id": int(ato["id"]), "quando": str(ato.get("criado_em") or ""),
                "quando_br": _data_br(ato.get("criado_em")),
                "motivo": (f"o item {item['codigo']} está pago no protocolo "
                           f"{item.get('protocolo_numero') or item['protocolo_id']} "
                           "e o selo dele não saiu"),
                "quem_tentou": str(ato.get("criado_por") or "") or "não gravado",
                "tentativas": 1 if item.get("tentativa") else 0,
                "item_id": item["item_id"], "codigo": item["codigo"],
                "codigo_selo": item["codigo_selo"], "serve": item["serve"],
                "o_que_falta": ("" if item["serve"] else
                                fora_do_caminho(item, AS.caminho_do_ato(
                                    TABELA, ato.get("tipo")))),
                "protocolo_do_item": item.get("protocolo_numero"),
                "unidades": item["livres"],
                "explicacao": explicacao(ato, item),
            })
    return saida


def referencia_livre(con, ato_id: int, codigo_selo: str) -> str:
    """A referência do selo novo: `pt_atos:<ato>:<código>:<n>`, com o menor `n`
    que não tem cobertura nem selo deste ato. Só LÊ.

    É dela que sai o SID, e é o SID que faz o aparelho devolver o selo que já
    existe em vez de vender outro: a referência de um selo que já está no ato
    devolveria o mesmo selo, e o item ficaria sem o dele.
    """
    bd = banco(con)
    for n in range(1, 1000):
        ref = f"{TABELA}:{int(ato_id)}:{str(codigo_selo).strip()}:{n}"
        grafias = AS.grafias_da_referencia(ref)
        if bd.tem_tabela("cx_selo_coberturas") and bd.um(
                "SELECT 1 AS um FROM cx_selo_coberturas WHERE referencia = ANY(%s)",
                (grafias,)):
            continue
        if bd.tem_tabela("sd_selos") and bd.um(
                """SELECT 1 AS um FROM sd_selos
                    WHERE referencia = ANY(%s) AND cancelado_em IS NULL
                      AND ato_id IS NOT NULL""", (grafias,)):
            continue
        return ref
    raise SeloQueFaltouError(
        f"Não achei referência livre para o selo {codigo_selo} do ato "
        f"{ato_id}. Fale com o desenvolvimento.")


# ======================================================= a emissão (escreve)


def _vencida(criado_em: Any, agora: Any) -> bool:
    try:
        antes = datetime.fromisoformat(str(criado_em or "")[:19])
        depois = datetime.fromisoformat(str(agora or "")[:19])
    except ValueError:
        return True
    return (depois - antes).total_seconds() > PRAZO_DA_EMISSAO_EM_SEGUNDOS


def _recusa_do_item(quadro: dict, item_id: int) -> tuple[dict | None, str | None]:
    """O item escolhido e, se não serve, por quê. Só calcula."""
    ato = quadro["ato"]
    linha = next((x for x in quadro["itens"] if x["item_id"] == int(item_id)),
                 None)
    if linha is None:
        return None, (f"O item {item_id} não é de protocolo deste ato "
                      f"({_o_ato(ato.get('tipo'))}, ato {ato['id']}). O selo que "
                      "faltou sai só pelo item pago do próprio atendimento.")
    onde = f"no protocolo {linha.get('protocolo_numero') or linha['protocolo_id']}"
    if linha["gratuito"]:
        return linha, (f"O item {linha['codigo']} {onde} é gratuito: item "
                       "gratuito não paga selo pago. Nada foi pedido ao selador.")
    if not linha["pago"]:
        return linha, (f"O item {linha['codigo']} não está pago {onde}: o selo "
                       "pago só sai com o item pago. Quite o item no caixa e "
                       "volte aqui. Nada foi pedido ao selador.")
    if not linha["do_ato"]:
        return linha, (f"O item {linha['codigo']} {onde} não tem rastro neste "
                       "ato — nem ligação, nem tentativa de selo. Ele pode ser de "
                       "outro ato do mesmo protocolo; ligue-o pelo quadro do selo "
                       "se for mesmo deste. Nada foi pedido ao selador.")
    if linha["livres"] <= 0:
        return linha, (f"O item {linha['codigo']} {onde} já tem selo confirmado "
                       "(neste ato, ou em outro do mesmo protocolo), ou o pedido "
                       "dele está em andamento: não se sela de novo. Nada foi "
                       "pedido ao selador.")
    return linha, None


def preparar(con, *, ato_id: int, item_id: Any, papel: Any, eh_robo: Any,
             usuario: Any, agora: str, titulo_id: int | None = None,
             afirmo: Any = False, afirmacao: Any = "") -> dict:
    """Confere tudo e liga o item ao ato, sem gastar a unidade. ESCREVE.

    Dentro da transação da rota, ANTES do pedido ao aparelho. A recusa não
    escreve nada. Devolve o preparo: o ato, o item, o código do selo (a faixa
    já convertida), a referência livre e o que `desfazer` precisa saber.

    O CÓDIGO QUE O CAMINHO NÃO CONHECE pede afirmação expressa — a régua do
    selo prévio (`protesto_selo_previo.REGRA_ITEM_FORA_DO_CAMINHO`): o
    aparelho já o recusou uma vez, e pedir de novo é insistir. A afirmação
    aceita vai no preparo, para a rota a gravar na auditoria e no ato.
    """
    if eh_robo:
        raise SeloQueFaltouError(
            "Robô não emite selo. O selo que faltou é emitido pelo oficial, em "
            "pessoa, na ficha do título.")
    if str(papel or "").strip().upper() != PAPEL_QUE_EMITE:
        raise SeloQueFaltouError(
            "Só o oficial (ADMIN) emite o selo que faltou. Avise-o: a "
            "pendência está na ficha do título.")
    if item_id is None or not str(item_id).strip().isdigit():
        raise SeloQueFaltouError(
            "Escolha o item do protocolo cujo selo faltou.")
    item_id = int(item_id)
    bd = banco(con)
    if not bd.tem_tabela("cx_item_do_ato"):
        raise SeloQueFaltouError(
            "Esta instalação não tem a ligação do ato ao item do protocolo "
            "(a trava do selo pago). Fale com o desenvolvimento.")
    # UMA EMISSÃO POR ATO DE CADA VEZ: dois cliques leriam «sem selo» juntos.
    bd.travar(f"{TABELA}:{int(ato_id)}:selo_que_faltou")
    quadro = quadro_do_ato(bd, ato_id)
    if not quadro:
        raise SeloQueFaltouError("Ato não encontrado.")
    ato = quadro["ato"]
    if titulo_id is not None and int(ato["titulo_id"]) != int(titulo_id):
        raise SeloQueFaltouError("Este ato é de outro título.")
    if _cancelado(ato):
        motivo = str(ato.get("motivo_cancelamento") or "").strip().rstrip(".")
        raise SeloQueFaltouError(
            f"{_o_ato(ato.get('tipo')).capitalize()} (ato {ato['id']}) está "
            f"cancelado{f' ({motivo})' if motivo else ''}: ato cancelado não "
            "se sela. Se ele deve existir, lance-o de novo pela ficha.")
    if str(ato.get("origem") or "") == AS.MARCA_DO_ACERVO:
        raise SeloQueFaltouError(
            "Este ato veio do acervo do E-Ofício: o selo dele é o de lá, e não "
            "se compra outro hoje.")
    if not _sela(ato):
        raise SeloQueFaltouError(
            f"{_o_ato(ato.get('tipo')).capitalize()} não pede selo próprio: não "
            "há selo que faltou.")
    bd.um("SELECT id FROM cx_protocolo_atos WHERE id = %s FOR UPDATE",
          (item_id,))
    linha, recusa = _recusa_do_item(quadro, item_id)
    if recusa:
        raise SeloQueFaltouError(recusa)
    afirmada = None
    if not linha["serve"]:
        o_que = fora_do_caminho(linha, quadro["caminho"])
        try:
            texto = PSELO.validar_afirmacao(afirmo, afirmacao, robo=bool(eh_robo))
        except PSELO.SituacaoError as metade:
            raise SeloQueFaltouError(
                f"Selo NÃO pedido, e nada foi gravado: {o_que}. {metade}") from None
        if texto is None:
            raise SeloQueFaltouError(
                f"Selo NÃO pedido, e nada foi gravado: {o_que}. Se o item serve "
                "mesmo para este ato, marque «Afirmo» e escreva por quê (pelo "
                f"menos {PSELO.MINIMO_DE_LETRAS_DA_AFIRMACAO} letras, começando "
                f"por «{PSELO.MODELO_DA_AFIRMACAO}»); se não serve, acerte o item "
                "no caixa.")
        afirmada = {"regra": PSELO.REGRA_ITEM_FORA_DO_CAMINHO,
                    "afirmacao": texto, "o_que_faltava": o_que}
    # A LIGAÇÃO SEM UNIDADE É A MARCA DA EMISSÃO EM ANDAMENTO. Já existindo
    # sem unidade e dentro do prazo, é outro clique no meio do pedido.
    criada = bd.escrever(
        """INSERT INTO cx_item_do_ato
               (item_id, protocolo_id, tabela, ato_id, unidades, origem,
                criado_em, criado_por)
           VALUES (%s, %s, %s, %s, 0, %s, %s, %s)
           ON CONFLICT (tabela, ato_id, item_id, origem) DO NOTHING
           RETURNING id""",
        (item_id, linha["protocolo_id"], TABELA, int(ato["id"]),
         CXP.ORIGEM_QUADRO, agora, usuario))
    ligacao_id = int(criada[0]["id"]) if criada else None
    if not criada:
        ja = bd.um("""SELECT id, unidades, criado_em FROM cx_item_do_ato
                       WHERE tabela = %s AND ato_id = %s AND item_id = %s
                         AND origem = %s""",
                   (TABELA, int(ato["id"]), item_id, CXP.ORIGEM_QUADRO))
        if ja and _int(ja.get("unidades")) == 0:
            if not _vencida(ja.get("criado_em"), agora):
                raise SeloQueFaltouError(
                    f"O selo do item {linha['codigo']} já está sendo emitido "
                    "(outra aba ou outro clique). Espere o primeiro terminar e "
                    "confira a ficha.")
            # A SOBRA DE UM CLIQUE QUE CAIU vira desta emissão: se o selo não
            # sair, ela sai junto, e a ficha volta a como estava antes dela.
            ligacao_id = int(ja["id"])
    aguardando_antes = bool(bd.tem_tabela("cx_selo_aguardando") and bd.um(
        "SELECT 1 AS um FROM cx_selo_aguardando WHERE tabela = %s AND ato_id = %s",
        (TABELA, int(ato["id"]))))
    return {
        "ato_id": int(ato["id"]), "titulo_id": int(ato["titulo_id"]),
        "tipo": str(ato["tipo"]), "caminho": quadro["caminho"],
        "item_id": item_id, "codigo": linha["codigo"],
        "codigo_selo": linha["codigo_selo"],
        "protocolo_id": linha["protocolo_id"],
        "protocolo_numero": linha.get("protocolo_numero"),
        "referencia": referencia_livre(bd, ato["id"], linha["codigo_selo"]),
        "ligacao_id": ligacao_id,
        "aguardando_antes": aguardando_antes,
        "afirmacao": afirmada,
        # a unidade só se gasta se a ligação à mão já não a gastou
        "consumir": linha["preconsumidas"] == 0,
    }


def concluir(con, preparo: dict, *, agora: str, usuario: Any) -> int:
    """O selo saiu: a unidade do item se gasta, na ligação que `preparar`
    deixou, e a afirmação expressa (se houve) vai ao `detalhe_json` do ato.
    ESCREVE. Devolve quantas unidades se gastaram (uma, ou zero se o saldo
    acabou no meio — o selo vale do mesmo jeito, e a rota diz)."""
    if preparo.get("afirmacao"):
        PSELO.anotar_afirmacao_no_ato(con, int(preparo["ato_id"]),
                                      preparo["afirmacao"], quem=str(usuario or ""),
                                      agora=agora)
    if not preparo.get("consumir", True):
        return 0
    return CXP.consumir_item(con, int(preparo["item_id"]),
                             ato_id=int(preparo["ato_id"]), tabela=TABELA,
                             agora=agora, quantas=1, origem=CXP.ORIGEM_QUADRO,
                             quem=usuario)


def _coberto_agora(bd, preparo: dict) -> bool:
    if not bd.tem_tabela("cx_selo_coberturas"):
        return False
    return bool(bd.um(
        """SELECT 1 AS um FROM cx_selo_coberturas
            WHERE referencia = ANY(%s) AND situacao = %s""",
        (AS.grafias_da_referencia(preparo["referencia"]), AS.CONFIRMADA)))


def desfazer(con, preparo: dict, *, agora: str, usuario: Any) -> bool:
    """O selo não saiu: tira a ligação que `preparar` deixou e a marca de
    «aguardando cobertura» que a falha possa ter posto. ESCREVE.

    Devolve True quando desfez. O caso raro em que a cobertura já está
    CONFIRMADA (o selo saiu e só a amarração ao ato falhou) não se desfaz: o
    pagamento já foi usado, e a unidade se gasta — devolve False.
    """
    bd = banco(con)
    if _coberto_agora(bd, preparo):
        concluir(con, preparo, agora=agora, usuario=usuario)
        return False
    if preparo.get("ligacao_id"):
        bd.escrever("DELETE FROM cx_item_do_ato WHERE id = %s AND unidades = 0",
                    (int(preparo["ligacao_id"]),))
    if not preparo.get("aguardando_antes") and bd.tem_tabela("cx_selo_aguardando"):
        bd.escrever("DELETE FROM cx_selo_aguardando WHERE tabela = %s AND ato_id = %s",
                    (TABELA, int(preparo["ato_id"])))
    return True


def para_a_auditoria(preparo: dict, selado: dict, unidades: int) -> dict:
    """O que vai em `SELO_EMITIDO_DEPOIS`: o ato, o item e o selo. Só calcula."""
    return {"ato_id": preparo["ato_id"], "titulo_id": preparo["titulo_id"],
            "tipo": preparo["tipo"], "item_id": preparo["item_id"],
            "codigo_do_item": preparo["codigo"],
            "codigo_do_selo": preparo["codigo_selo"],
            "protocolo": preparo.get("protocolo_numero"),
            "referencia": preparo["referencia"],
            "caminho": selado.get("caminho") or preparo["caminho"],
            "selo": selado.get("numero"), "selos": selado.get("numeros") or [],
            "unidades_gastas": int(unidades),
            "afirmacao_expressa": preparo.get("afirmacao"),
            "sem_ato_novo": True, "sem_cobranca_nova": True}
