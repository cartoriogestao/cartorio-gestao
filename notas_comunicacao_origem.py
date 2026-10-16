"""A comunicação à serventia que lavrou a procuração substabelecida.

O RELATO #129 — 10/10/2026, vindo da inspeção da Corregedoria
    «Criar obrigação mediante aviso persistente para comunicação comprovada ou
     anotação de envio de ofício para o cartório responsável pela procuração
     quando do ato de substabelecimento» — o oficial, na tela notas_atos.

    E a observação da inspeção, transcrita: «Substabelecimento de Procuração
    Livro nº 02 — Verificado que se trata de substabelecimento de procuração
    oriunda de serventia diversa (4º Ofício Extrajudicial de Imperatriz/MA)
    que consta no último ato do livro vigente (fls. 003), entretanto, não há
    comprovação de comunicação à serventia que emitiu a procuração
    substabelecida.»

O QUE A NORMA MANDA — lido no PDF, e não de memória
    Código de Normas do TJMA (Provimento 28/2026), Seção X do Capítulo IV, art.
    831, § 1º — lido em 14/10/2026 em «AA Código de normas TJMA
    atualizado.pdf», página 214 do arquivo:

        «Se o ato revogatório ou de renúncia e o de substabelecimento versarem
         sobre atos lavrados em outra serventia, será imediatamente comunicado,
         por quaisquer meio de comunicação, desde que tenha comprovante de
         recebimento, ao tabelião que lavrou o instrumento revogado ou o
         mandato substabelecido, mediante o pagamento pelo interessado da
         despesa postal da carta registrada.»

    O caput (o ato DESTA casa anota-se à margem, sem ônus e sem selo) já mora
    em `notas_anotacoes`. Este módulo é o § 1º, que até hoje não tinha onde
    morar: `agente_notas.regra_anotacao_a_margem` dizia, com razão, que «o
    sistema não tem onde guardar o comprovante — cobrar o que não se pode
    registrar seria cobrar para sempre».

A OBRIGAÇÃO É LINHA, E NÃO SÓ LENTE — e a razão é a palavra «persistente»
    O resto da casa mede pendência na hora (`inacabados`). Aqui isso não basta:
    medida pelos campos `anterior_*`, a obrigação sumiria no dia em que alguém
    apagasse o nome do cartório de origem, sem providência nenhuma. O relato
    pede o contrário — **o aviso só some com a providência**. Então ela nasce
    como linha (`nt_comunicacoes_origem`, uma por ato) e só muda de situação
    por uma das duas portas abaixo. A lente (`inacabados`) lê esta linha, e não
    os campos do ato.

AS DUAS PORTAS DE BAIXA, e nenhuma terceira
    (a) COMPROVANTE — o arquivo do comprovante de recebimento, guardado em
        `attachments` (a mesma tabela de anexo da casa), com o sha256 copiado
        para a linha: o rastro sobrevive ao arquivo.
    (b) OFÍCIO — a anotação do envio: data, meio, número do ofício ou
        rastreio, e quem enviou. Os quatro são exigidos; anotação sem um deles
        é o «ok» que não responde à correição.

    A porta (b) baixa a obrigação porque o oficial a pediu assim. **E a norma
    pede comprovante de RECEBIMENTO** — por isso, baixada por ofício, a tela
    continua oferecendo juntar o comprovante quando ele chegar, e diz que ele
    falta. Não reabre, e não esconde.

NÃO SE APAGA E NÃO SE REABRE
    Não há função de apagar nem de reabrir: a obrigação cumprida é a prova de
    que se cumpriu. Quem baixou, quando e por qual porta fica na linha — e a
    rota grava a mesma coisa na auditoria.

QUANDO NASCE
    - na lavratura do substabelecimento, na mesma transação do lançamento,
      se a procuração já está informada como de outra serventia;
    - quando a serventia de origem é informada na tela de um substabelecimento
      já lavrado (é por aí que o oficial alcança o ato antigo);
    - por botão, na ficha de um substabelecimento já lavrado que tem os dados
      de origem e ainda não tem a obrigação — o caso do acervo, que **não vira
      atraso sozinho**: alguém olha e decide lançá-la.
"""
from __future__ import annotations

import re
import sqlite3
from datetime import date
from typing import Any

from notas_anotacoes import _mesma_serventia

#: Os atos que fazem nascer a obrigação. O § 1º do art. 831 alcança também a
#: REVOGAÇÃO e a RENÚNCIA de mandato lavrado em outra serventia; o relato #129
#: pediu o substabelecimento, e alargar é decisão do oficial — uma linha aqui.
TIPOS_QUE_COMUNICAM = ("SUBSTABELECIMENTO",)

#: Ato nessas situações não está no livro (ou deixou de valer): não comunica.
SITUACOES_FORA = ("EM_LAVRATURA", "CANCELADO", "SEM_EFEITO")

#: Por onde o ofício pode ter ido. «Quaisquer meio de comunicação, desde que
#: tenha comprovante de recebimento» — a lista é de conveniência da tela, e
#: «OUTRO» existe porque a norma não fecha os meios.
MEIOS = {
    "CARTA_REGISTRADA": "Carta registrada com AR (Correios)",
    "MALOTE_DIGITAL": "Malote Digital",
    "EMAIL": "E-mail com confirmação de leitura",
    "ENTREGA_EM_MAOS": "Entregue em mãos, com recibo",
    "OUTRO": "Outro meio (descrever na observação)",
}

PROVIDENCIAS = {
    "COMPROVANTE": "Comunicação comprovada (comprovante juntado)",
    "OFICIO": "Envio do ofício anotado",
}

FUNDAMENTO = "Código de Normas TJMA (Prov. 28/2026), art. 831, § 1º"

#: Tipo de anexo do comprovante. Próprio, e não `NT_ATO`: a rota que retira
#: anexo do ato confere `entity_type == 'NT_ATO'`, e o comprovante de uma
#: obrigação cumprida não pode sair da lista por aquele botão.
TIPO_DO_ANEXO = "NT_COMUNICACAO_ORIGEM"


class ComunicacaoError(ValueError):
    """Regra violada. A rota trata com flash, não com HTTP 500."""


def _texto(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _data(v: Any, rotulo: str, hoje: str) -> str:
    bruto = _texto(v)[:10]
    try:
        d = date.fromisoformat(bruto)
    except ValueError:
        raise ComunicacaoError(f"Informe a {rotulo} (dd/mm/aaaa).") from None
    if d.isoformat() > hoje[:10]:
        raise ComunicacaoError(f"A {rotulo} não pode ser depois de hoje.")
    return d.isoformat()


# ------------------------------------------------------------- a regra

def _de_outra_serventia(ato: dict, sv: dict) -> bool:
    """A procuração é de OUTRA serventia, AFIRMADO — e não por silêncio.

    A régua é a de `notas_anotacoes._mesma_serventia`, e não uma parecida: as
    duas respondem à mesma pergunta, e duas réguas divergem no primeiro
    conserto. Só que lá o silêncio conta a favor de «é daqui» (o acervo não
    trouxe o CNS), e aqui o silêncio **não** faz nascer obrigação: sem nome nem
    CNS do cartório de origem, o ato já está na lista das anotações
    pendentes como «o ato anterior não foi informado».
    """
    if ato.get("anterior_ato_id"):
        return False                      # vinculado a ato DESTA casa
    if not (_texto(ato.get("anterior_cns")) or _texto(ato.get("anterior_cartorio"))):
        return False
    return not _mesma_serventia(ato, sv or {})


def devida(ato: Any, sv: dict) -> bool:
    """Este ato deve a comunicação do art. 831, § 1º? Só lê."""
    a = dict(ato)
    return ((a.get("tipo") or "").upper() in TIPOS_QUE_COMUNICAM
            and (a.get("situacao") or "") not in SITUACOES_FORA
            and _de_outra_serventia(a, sv))


def _destinatario(a: dict) -> str:
    partes = [_texto(a.get("anterior_cartorio")) or "serventia não nomeada"]
    lugar = "/".join(x for x in (_texto(a.get("anterior_cidade")),
                                 _texto(a.get("anterior_uf"))) if x)
    if lugar:
        partes.append(lugar)
    return " — ".join(partes)


def do_ato(con: sqlite3.Connection, ato_id: int) -> dict | None:
    """A obrigação deste ato, se nasceu. Só lê."""
    linha = con.execute("SELECT * FROM nt_comunicacoes_origem WHERE ato_id=?",
                        (ato_id,)).fetchone()
    if not linha:
        return None
    d = dict(linha)
    d["aberta"] = d["situacao"] == "ABERTA"
    d["falta_comprovante"] = (d["situacao"] == "CUMPRIDA"
                              and not d.get("comprovante_attachment_id"))
    return d


# ------------------------------------------------------------- nascer

def abrir(con: sqlite3.Connection, ato_id: int, sv: dict, agora: str,
          por: str | None, como: str) -> dict | None:
    """Faz nascer a obrigação, se o ato a deve e ela ainda não existe. GRAVA.

    Devolve a obrigação NOVA, ou None quando não nasceu (não é devida, ou já
    existia). Roda dentro da transação de quem chama — no lançamento, é a
    mesma do livro: se a obrigação falhar, o lançamento volta junto.
    """
    ato = con.execute("SELECT * FROM nt_atos WHERE id=?", (ato_id,)).fetchone()
    if not ato:
        raise ComunicacaoError("Ato não encontrado.")
    a = dict(ato)
    if not devida(a, sv) or do_ato(con, ato_id):
        return None
    con.execute(
        """INSERT INTO nt_comunicacoes_origem
               (ato_id, situacao, destinatario, destinatario_cns,
                procuracao_livro, procuracao_folha, procuracao_data,
                nascida_em, nascida_por, nascida_como)
           VALUES (?, 'ABERTA', ?,?,?,?,?,?,?,?)""",
        (ato_id, _destinatario(a), _texto(a.get("anterior_cns")) or None,
         _texto(a.get("anterior_livro")) or None,
         _texto(a.get("anterior_folha")) or None,
         _texto(a.get("anterior_data")) or None,
         agora, por, como))
    return do_ato(con, ato_id)


def informar_origem(con: sqlite3.Connection, ato_id: int, dados: dict,
                    sv: dict, agora: str, por: str | None) -> dict:
    """Grava, no ato, de onde veio a procuração substabelecida. GRAVA.

    São os campos `anterior_*`, que já existiam para a CENSEC e nenhuma tela
    escrevia — a ficha dizia «aqui registre os dados do ato anterior» sem
    oferecer onde. Com o ato já lavrado, a obrigação nasce no mesmo passo.

    O QUE ELE RECUSA
      - ato que não é dos que comunicam;
      - ato vinculado a uma procuração DESTA casa — ali a anotação é à margem;
      - mudar a origem depois de a obrigação ter sido cumprida: o comprovante
        e o ofício falam daquele destinatário;
      - fazer a obrigação aberta sumir dizendo que a origem é esta casa — o
        aviso só some com a providência.
    """
    ato = con.execute("SELECT * FROM nt_atos WHERE id=?", (ato_id,)).fetchone()
    if not ato:
        raise ComunicacaoError("Ato não encontrado.")
    a = dict(ato)
    if (a.get("tipo") or "").upper() not in TIPOS_QUE_COMUNICAM:
        raise ComunicacaoError("Só o substabelecimento informa aqui a serventia "
                               "de origem da procuração.")
    if a.get("anterior_ato_id"):
        raise ComunicacaoError(
            "Este ato está vinculado a uma procuração desta serventia: a "
            "providência é a anotação à margem, e não comunicação a outro "
            "cartório.")
    cartorio = _texto(dados.get("cartorio"))
    if len(cartorio) < 5:
        raise ComunicacaoError("Informe o nome da serventia que lavrou a "
                               "procuração (por exemplo, «4º Ofício "
                               "Extrajudicial de Imperatriz/MA»).")
    cns = re.sub(r"\D", "", _texto(dados.get("cns")))
    novo = {
        "anterior_cartorio": cartorio,
        "anterior_cns": cns or None,
        "anterior_cidade": _texto(dados.get("cidade")) or None,
        "anterior_uf": _texto(dados.get("uf")).upper()[:2] or None,
        "anterior_livro": _texto(dados.get("livro")) or None,
        "anterior_folha": _texto(dados.get("folha")) or None,
        "anterior_data": (_data(dados.get("data"), "data da procuração", agora)
                          if _texto(dados.get("data")) else None),
    }
    existente = do_ato(con, ato_id)
    if existente and not existente["aberta"]:
        raise ComunicacaoError(
            "A comunicação já foi cumprida para "
            f"«{existente['destinatario']}». A origem não muda depois disso: o "
            "comprovante e o ofício falam daquele destinatário.")
    if existente and not _de_outra_serventia({**a, **novo}, sv):
        raise ComunicacaoError(
            "Há uma obrigação de comunicação aberta para este ato, e ela não "
            "some trocando a origem para esta serventia. Se o ato foi lançado "
            "com a origem errada, baixe a obrigação pela anotação do ofício, "
            "explicando na observação.")
    con.execute(
        """UPDATE nt_atos SET anterior_cartorio=?, anterior_cns=?,
               anterior_cidade=?, anterior_uf=?, anterior_livro=?,
               anterior_folha=?, anterior_data=? WHERE id=?""",
        (novo["anterior_cartorio"], novo["anterior_cns"], novo["anterior_cidade"],
         novo["anterior_uf"], novo["anterior_livro"], novo["anterior_folha"],
         novo["anterior_data"], ato_id))
    if existente:
        # Ainda aberta: o destinatário acompanha a correção, que é o que vai
        # no ofício. Depois de cumprida, a recusa acima já barrou.
        a2 = {**a, **novo}
        con.execute(
            """UPDATE nt_comunicacoes_origem SET destinatario=?,
                   destinatario_cns=?, procuracao_livro=?, procuracao_folha=?,
                   procuracao_data=? WHERE ato_id=?""",
            (_destinatario(a2), novo["anterior_cns"], novo["anterior_livro"],
             novo["anterior_folha"], novo["anterior_data"], ato_id))
    nasceu = abrir(con, ato_id, sv, agora, por, "TELA")
    return {"ato_id": ato_id, "antes": {k: a.get(k) for k in novo},
            "depois": novo, "obrigacao_nasceu": bool(nasceu)}


# ------------------------------------------------------------- baixar

def _aberta_ou_recusa(con: sqlite3.Connection, ato_id: int) -> dict:
    ob = do_ato(con, ato_id)
    if not ob:
        raise ComunicacaoError(
            "Este ato não tem obrigação de comunicação. Informe antes a "
            "serventia de origem da procuração.")
    return ob


def baixar_por_oficio(con: sqlite3.Connection, ato_id: int, *, data: str,
                      meio: str, numero: str, enviado_por: str, agora: str,
                      por: str | None, observacao: str = "") -> dict:
    """Porta (b): a anotação do envio do ofício. GRAVA.

    Os quatro campos são exigidos — data, meio, número do ofício ou do
    rastreio, e quem enviou. Faltando um, a anotação não diz o que a correição
    pergunta, e é recusada.
    """
    ob = _aberta_ou_recusa(con, ato_id)
    if not ob["aberta"]:
        raise ComunicacaoError("Esta obrigação já foi baixada "
                               f"em {ob['cumprida_em'][:10]}, por "
                               f"{ob['cumprida_por'] or '—'}.")
    meio = _texto(meio).upper()
    if meio not in MEIOS:
        raise ComunicacaoError("Escolha por que meio o ofício foi enviado.")
    if not _texto(numero):
        raise ComunicacaoError("Informe o número do ofício ou o código de "
                               "rastreio — é por ele que se acha o envio depois.")
    if not _texto(enviado_por):
        raise ComunicacaoError("Informe quem enviou o ofício.")
    if meio == "OUTRO" and len(_texto(observacao)) < 5:
        raise ComunicacaoError("Com «outro meio», descreva na observação qual.")
    quando = _data(data, "data do envio", agora)
    con.execute(
        """UPDATE nt_comunicacoes_origem SET situacao='CUMPRIDA',
               providencia='OFICIO', cumprida_em=?, cumprida_por=?,
               envio_data=?, envio_meio=?, envio_numero=?, envio_por=?,
               observacao=?
           WHERE ato_id=? AND situacao='ABERTA'""",
        (agora, por, quando, meio, _texto(numero), _texto(enviado_por),
         _texto(observacao) or None, ato_id))
    return do_ato(con, ato_id)


def juntar_comprovante(con: sqlite3.Connection, ato_id: int, *,
                       attachment_id: int, recebido_em: str, agora: str,
                       por: str | None, observacao: str = "") -> dict:
    """Porta (a): o comprovante de recebimento. GRAVA.

    Baixa a obrigação aberta; na obrigação já baixada por ofício, completa o
    que a norma pede (comprovante de RECEBIMENTO) sem mexer em quem baixou nem
    quando. Comprovante já juntado não se troca.
    """
    ob = _aberta_ou_recusa(con, ato_id)
    if ob.get("comprovante_attachment_id"):
        raise ComunicacaoError("O comprovante desta comunicação já foi juntado.")
    anexo = con.execute("SELECT * FROM attachments WHERE id=?",
                        (attachment_id,)).fetchone()
    if (not anexo or anexo["entity_type"] != TIPO_DO_ANEXO
            or int(anexo["entity_id"]) != int(ob["id"])):
        raise ComunicacaoError("O arquivo do comprovante não pertence a esta "
                               "obrigação.")
    quando = _data(recebido_em, "data do recebimento", agora)
    obs = _texto(observacao)
    if ob["aberta"]:
        con.execute(
            """UPDATE nt_comunicacoes_origem SET situacao='CUMPRIDA',
                   providencia='COMPROVANTE', cumprida_em=?, cumprida_por=?,
                   observacao=?
               WHERE ato_id=? AND situacao='ABERTA'""",
            (agora, por, obs or None, ato_id))
    elif obs:
        con.execute(
            """UPDATE nt_comunicacoes_origem SET observacao =
                   CASE WHEN observacao IS NULL THEN ? ELSE observacao END
               WHERE ato_id=?""", (obs, ato_id))
    con.execute(
        """UPDATE nt_comunicacoes_origem SET comprovante_attachment_id=?,
               comprovante_sha256=?, comprovante_nome=?, comprovante_recebido_em=?,
               comprovante_em=?, comprovante_por=?
           WHERE ato_id=?""",
        (int(attachment_id), anexo["sha256"], anexo["original_name"], quando,
         agora, por, ato_id))
    return do_ato(con, ato_id)


# ------------------------------------------------------------- a lista

def pendentes(con: sqlite3.Connection) -> list[dict]:
    """As obrigações abertas, a mais antiga primeiro. Só lê.

    É a lista que a correição pede — «há comprovação de comunicação à
    serventia que emitiu a procuração substabelecida?» —, e a mesma que a
    lente dos inacabados (`NOTAS_COMUNICACAO_ORIGEM`) mostra no painel.
    """
    return [dict(r) for r in con.execute(
        """SELECT c.*, a.tipo, a.livro, a.folha, a.termo, a.data data_ato,
                  a.interessado
           FROM nt_comunicacoes_origem c JOIN nt_atos a ON a.id = c.ato_id
           WHERE c.situacao = 'ABERTA'
           ORDER BY c.nascida_em, c.id""")]
