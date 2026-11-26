"""O andamento dos títulos do RI no «Acompanhamento de Títulos» do ONR.

    Pedido de 26/10/2026: enviar o andamento das prenotações ao Acompanhamento
    Registral do ONR (manual do WSOficio 4.43, cap. 3.2).

O QUE ISTO É
    O apresentante consulta na Central o que aconteceu com o título que deixou
    no balcão: prenotado, nota de exigência, reingresso, registrado. Quem
    escreve esse andamento é a serventia, pelo serviço `acompanhamentotitulos
    .asmx` do WSOficio. O transporte é o de `onr_wsoficio` (o mesmo que já
    responde as certidões em produção); este módulo decide O QUE sobe.

O RISCO QUE GOVERNA O DESENHO
    Andamento errado na Central é PUBLICIDADE INDEVIDA: um «título registrado»
    que não foi, uma nota de exigência de outro título, ficam à vista de quem
    consulta. Por isso:

    1. **SÓ SOBE FATO GRAVADO.** Cada gancho (`anotar_*`) roda DENTRO da
       transação que grava o fato — a prenotação, a nota, o reingresso, a
       prorrogação, a dúvida, a amarração do ato. Se o fato não entra, a linha
       da fila também não entra. Nada aqui é digitado numa tela.
    2. **A FILA É IDEMPOTENTE POR EVENTO** (`chave` única: `PRENOTADO:
       ri_protocolos:12`, `EXIGENCIA:ri_notas_devolutivas:5`...). O mesmo fato
       anotado duas vezes é uma linha só.
    3. **O ENVIO É FORA DE TRANSAÇÃO E CONFERE O FATO DE NOVO** antes de cada
       chamada (`conferir_o_fato`): a nota apagada, o ato desfeito, o ato sem
       selo não sobem — o primeiro e o segundo saem da fila como ANULADO, com
       o motivo; o terceiro espera o selo. É a mesma régua do RI: o ato que o
       selador recusou é suspenso, e «registrado» na Central seria mentira.
    4. **SÓ COM O ENVIO LIGADO** (`onr_acompanhamento_ligado`, desligado de
       fábrica). Quem manda é o botão da tela e, desde a A008 (26/11/2026), o
       processo `RI_ONR_ACOMPANHAMENTO` da central de automação, que chama
       `enviar_pendentes` POR DENTRO (e não pela rota: `selo_robo` veda as
       rotas ao robô), e só com «pode agir».

AS TRAVAS DO ENVIO, A008 (26/11/2026)
    O ONR avisa o apresentante por e-mail ou SMS a cada andamento. Por isso,
    antes de cada chamada, `avaliar` decide se o evento sobe, espera (e por
    quê, com a frase na ficha do protocolo) ou sai da fila:
    - **ATRASADO**: o que já estava na fila quando a rotina ganhou o poder de
      enviar (`travar_atrasados`) não sai sozinho; espera o ADMIN liberar,
      em lote ou por título (`liberar_atrasados`, auditado).
    - **CARÊNCIA**: na rotina, só sobe o que está há mais de N horas na fila
      (2 de fábrica), para a exclusão da nota pela tela ainda valer.
    - **EXIGÊNCIA**: sobe o texto inteiro (decisão do oficial de 26/10) só
      se REVISADA («revisada por … em …», `marcar_revisada`); a sem nenhuma
      exigência no texto e a com frase de rascunho ficam BLOQUEADAS com o
      motivo. O texto curto (`CHAVE_TEXTO_CURTO`) está pronto e DESLIGADO.
    - **REGISTRADO REPETIDO**: um andamento por (protocolo, ato, matrícula);
      o repetido sai como ANULADO, com o motivo. Ato desfeito ou cancelado
      continua ANULADO pela conferência do fato.
    - **CADASTRO**: nome do apresentante com e-mail dentro, prazo anterior à
      data da nota ou da prenotação, falta de e-mail e de telefone: o evento
      fica ESPERANDO DADO, com a frase de correção.
    - **SEM «PRENOTADO»**: título que ainda não está no ONR e cuja fila não
      tem a prenotação (os anteriores à fila) precisa de DECISÃO: nada dele
      sobe. O evento retroativo (`anotar_prenotacao_retroativa`) está pronto
      e DESLIGADO (`CHAVE_RETROATIVO`).

DECISÕES DO OFICIAL, 26/10/2026
    - **O ambiente de fábrica é a PRODUÇÃO** («acho que podemos ir direto pra
      produção»): o WSOficio já responde em produção nesta casa (certidões,
      ofícios, penhora). O ambiente do acompanhamento passou a ter chave
      PRÓPRIA (`onr_acompanhamento_ambiente`) — antes ele seguia a das
      certidões, e uma casa com as certidões em homologação mandaria o
      andamento para lá sem ninguém ter escolhido isso. O ENVIO continua
      nascendo DESLIGADO: quem liga é o oficial, na tela, que mostra em letras
      grandes em que ambiente o clique vai cair.
    - **A nota de exigência é publicada ao interessado** («sim»): o texto
      inteiro da nota — o número, a data, cada exigência, a fundamentação e o
      prazo — vai no `DescricaoStatus` do status 7, que é o campo que o manual
      manda usar («a nota de devolução deve ser informada nesse campo», 3.2.8
      e 3.2.12) e que é `text`, sem teto. Ver `descricao_da_nota`.
      **O PDF da nota NÃO sobe**: nenhum dos nove métodos do Acompanhamento
      (3.2) tem campo de anexo, e os serviços de anexo do WSOficio são de
      outros pedidos (certidão, BDLight) e recebem um LINK — esta casa não tem
      endereço público. O que falta medir está em `NOTA_SEM_ANEXO`.

O QUE NÃO SE ACOMPANHA, E POR QUÊ (declarado, e não esquecido)
    - **Título entregue (8)**: o sistema não grava a entrega do título ao
      apresentante. O `ENTREGUE` do protocolo geral (`caixa_protocolo`) é o
      encerramento do ATENDIMENTO sem pagamento — outra coisa. Sem fato
      gravado, não sobe.
    - **Dúvida julgada procedente/improcedente (10, 11)**: o sistema não grava
      o julgamento da dúvida. Sobe só a suscitação (9), que é a suspensão do
      prazo pelo motivo «DUVIDA» (`ri_prenotacao_prazo`).
    - **O acervo**: prenotação importada do E-Ofício não passou por gancho
      nenhum — e não deve: o E-Ofício já respondia (ou não) por ela.

O CONTRATO, CONFERIDO EM 26/11/2026 (A008)
    - A ordem dos campos de `InsertTituloAT` e `InsertStatusAT` (e dos outros
      sete métodos) é a do manual 4.43, cap. 3.2, E a do WSDL de produção
      (`acompanhamentotitulos.asmx?WSDL`, lido por GET nesse dia: os nove
      `*_WSReq` batem campo a campo com `onr_wsoficio.CAMPOS`).
    - O elemento de entrada é `oRequest` (WSDL: `InsertTituloAT/oRequest` do
      tipo `InsertTituloAT_WSReq`), o mesmo dos outros serviços.
    - O formato da data: o manual escreve «aaaa-mm-ddhh:mm:ss» e diz
      string(19); o WSDL só diz `string`. Dez da data mais oito da hora são
      dezoito: o décimo nono é o espaço que a extração do PDF comeu. Vai
      `AAAA-MM-DD HH:MM:SS` — e é a CHAMADA DE PROVA que confirma.
    - No WSDL, `ValorDeposito` e `ValorEmolumentos` são `decimal` com
      minOccurs=1, embora o manual os diga opcionais; não vão (o .NET os lê
      como zero). A prova confirma também isso.
"""
from __future__ import annotations

import json
import logging
import re
import time
import unicodedata
from typing import Any, Callable

import onr_wsoficio as WS
from bd_nativo import banco

LOG = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS onr_at_titulos (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    ambiente TEXT NOT NULL,
    protocolo_id bigint NOT NULL,
    protocolo_numero TEXT NOT NULL,
    id_titulo_onr bigint NOT NULL,
    como TEXT NOT NULL,
    cadastrado_em TEXT NOT NULL,
    cadastrado_por TEXT,
    UNIQUE(ambiente, protocolo_id)
);
CREATE TABLE IF NOT EXISTS onr_at_eventos (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    protocolo_id bigint NOT NULL,
    chave TEXT NOT NULL UNIQUE,
    evento TEXT NOT NULL,
    id_tipo_status integer NOT NULL,
    data_status TEXT NOT NULL,
    descricao TEXT NOT NULL,
    origem_tabela TEXT NOT NULL,
    origem_id bigint NOT NULL,
    situacao TEXT NOT NULL DEFAULT 'PENDENTE',
    ambiente TEXT,
    id_status_onr bigint,
    tentativas integer NOT NULL DEFAULT 0,
    ultimo_erro TEXT,
    ultima_tentativa_em TEXT,
    enviado_em TEXT,
    enviado_por TEXT,
    motivo_fim TEXT,
    criado_em TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_onr_at_eventos_fila
    ON onr_at_eventos(situacao, protocolo_id, data_status, id);
"""

#: As colunas que nasceram depois da tabela (A008, 26/11/2026) — só
#: `ALTER TABLE ADD COLUMN`, como em `onr_certidoes_auto.MIGRACOES`.
#:   atrasado      1 = já estava na fila quando a rotina ganhou o poder de
#:                 enviar (`travar_atrasados`): só sai com a liberação.
#:   liberado_*    quem liberou o atrasado, e quando (ADMIN, auditado).
#:   revisado_*    quem revisou a exigência, e quando (ADMIN/MANAGER).
#:   espera        por que o pendente não subiu na última rodada (`ESPERAS`).
MIGRACOES = (("atrasado", "INTEGER NOT NULL DEFAULT 0"), ("liberado_em", "TEXT"),
             ("liberado_por", "TEXT"), ("revisado_em", "TEXT"), ("revisado_por", "TEXT"),
             ("espera", "TEXT"))

#: O evento da casa → o tipo de status do manual (3.2.1). Só os que têm fato
#: gravado que os sustente — ver o cabeçalho.
EVENTOS = {
    "PRENOTADO": 4,
    "EXIGENCIA": 7,
    "REINGRESSO": 1,
    "PRORROGADO": 15,
    "DUVIDA": 9,
    "REGISTRADO": 6,
}

#: PENDENTE → ENVIADO. ANULADO: o fato deixou de existir antes de subir.
#: DESCARTADO: quem responde pela casa decidiu, com motivo, que não sobe.
SITUACOES = ("PENDENTE", "ENVIADO", "ANULADO", "DESCARTADO")

#: Liga e desliga o ENVIO (a fila se anota sempre: é local). Desligado de fábrica.
CHAVE_LIGADO = "onr_acompanhamento_ligado"
#: O ambiente do acompanhamento — chave PRÓPRIA desde 26/10/2026 (decisão do
#: oficial: «ir direto pra produção»). Vazia, é a PRODUÇÃO. Até essa data
#: era a chave das certidões (`onr_certidoes_ambiente`), e ela não manda
#: mais aqui: a escolha de um serviço não pode mudar o destino do outro.
CHAVE_AMBIENTE = "onr_acompanhamento_ambiente"
#: O ambiente de fábrica (decisão do oficial em 26/10/2026).
AMBIENTE_DE_FABRICA = WS.PRODUCAO

#: O que o contrato do Acompanhamento NÃO oferece para a nota, e fica a medir
#: na primeira chamada de produção: (1) campo de anexo — nenhum dos nove
#: métodos do cap. 3.2 tem; o PDF da nota fica no balcão; (2) teto real do
#: `DescricaoStatus` — o manual diz `text`, sem tamanho, e o WSDL do serviço
#: não está na casa para confirmar.
NOTA_SEM_ANEXO = ("O Acompanhamento de Títulos (manual 4.43, cap. 3.2) não tem campo de "
                  "anexo: sobe o status 7 com o texto inteiro da nota; o PDF não sobe")

#: Tamanhos do manual (3.2.8) — o que passa é cortado com reticências, e não
#: recusado: o nome inteiro está no livro; a Central mostra o começo.
TAMANHO = {"ApresentanteNome": 120, "ApresentanteEmail": 120, "InteressadoNome": 120,
           "NaturezaTitulo": 150}


#: A008 (26/11/2026). O texto CURTO da exigência («Nota de exigência nº N, de
#: dd/mm/aaaa. Prazo: dd/mm/aaaa.»), sem revisão — pronto e DESLIGADO: muda a
#: decisão do oficial de 26/10 (publicar a nota inteira), e o titular ainda
#: não decidiu.
CHAVE_TEXTO_CURTO = "onr_acompanhamento_exigencia_texto_curto"
#: A008. O evento retroativo de prenotação para o título que nasceu antes da
#: fila — pronto e DESLIGADO, até o titular decidir.
CHAVE_RETROATIVO = "onr_acompanhamento_prenotacao_retroativa"
#: A008. Quando a rotina ganhou o poder de enviar (o marco dos atrasados).
CHAVE_AUTO_DESDE = "onr_acompanhamento_auto_desde"

#: Frases de rascunho que não podem chegar ao apresentante (A007, § 3). A
#: comparação é sem acento e sem caixa, e pega as variantes que a fila de
#: 26/11/2026 mostrou («não consta do acervo recebido», «deve ser conferida
#: pelo oficial», «por não constarem das fontes»).
FRASES_DE_RASCUNHO = ("a conferir pelo oficial", "a conferência fica a cargo do oficial",
                      "não constam das fontes")
_RASCUNHO = (re.compile(r"\ba conferir pelo oficial"),
             re.compile(r"\bdeve(m)? ser conferid[ao]s? pelo oficial"),
             re.compile(r"\bconferencia fica a cargo do oficial"),
             re.compile(r"\bnao consta(m|rem)? d[ao]s? (fontes|acervo)"))

#: Por que o pendente não subiu. As duas primeiras não se gravam na linha:
#: a marca dela (`atrasado`, `criado_em`) já diz.
ESPERAS = {
    "ATRASADO": "atrasado, aguardando a liberação do titular",
    "CARENCIA": "na carência (a nota ainda pode ser excluída pela tela)",
    "SELO": "esperando o selo do ato",
    "DECISAO": "precisa de decisão (o título não tem o «prenotado» na fila)",
    "BLOQUEIO": "exigência bloqueada",
    "REVISAO": "exigência aguardando revisão",
    "DADO": "esperando dado do cadastro",
    "RECUSA": "recusado pelo ONR",
}


class AcompanhamentoError(ValueError):
    """Recusa com a frase pronta para o balcão."""


def init_schema(con) -> None:
    bd = banco(con)
    bd.escrever(SCHEMA)
    for coluna, tipo in MIGRACOES:
        if not bd.tem_coluna("onr_at_eventos", coluna):
            bd.escrever(f"ALTER TABLE onr_at_eventos ADD COLUMN {coluna} {tipo}")


# ------------------------------------------------------------- as datas

def data_do_onr(data: Any, hora: Any = None) -> str:
    """`AAAA-MM-DD HH:MM:SS` — string(19) do manual (ver o cabeçalho)."""
    texto = str(data or "").strip().replace("T", " ")
    m = re.match(r"(\d{4}-\d{2}-\d{2})(?:\s+(\d{2}:\d{2}(?::\d{2})?))?", texto)
    if not m:
        raise AcompanhamentoError(f"Data que não sei mandar ao ONR: «{data}».")
    h = m.group(2) or str(hora or "").strip() or "00:00:00"
    if len(h) == 5:
        h += ":00"
    return f"{m.group(1)} {h[:8]}"


def _data_br(iso: Any) -> str:
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(iso or ""))
    return f"{m.group(3)}/{m.group(2)}/{m.group(1)}" if m else str(iso or "")


# ------------------------------------------------------- a fila (os ganchos)

def _protocolo(bd, protocolo_id: int) -> dict | None:
    return bd.um("SELECT * FROM ri_protocolos WHERE id=%s", (int(protocolo_id),))


def _nao_antes_do_protocolo(data_status: str, p: dict) -> str:
    """A data do status não pode ser anterior à do protocolo (erro 34)."""
    try:
        inicio = data_do_onr(p.get("data_prenotacao"), p.get("hora"))
    except AcompanhamentoError:
        return data_status
    return max(data_status, inicio)


def anotar_na_fila(con, *, protocolo_id: int, evento: str, chave: str, data_status: str,
               descricao: str, origem_tabela: str, origem_id: int, agora: str,
               atrasado: bool = False) -> bool:
    """Anota UM fato na fila. Idempotente pela `chave`: devolve False quando
    o fato já estava anotado. Roda dentro da transação do fato."""
    if evento not in EVENTOS:
        raise AcompanhamentoError(f"Evento «{evento}» não tem status no Acompanhamento.")
    init_schema(con)
    linhas = banco(con).escrever(
        """INSERT INTO onr_at_eventos (protocolo_id, chave, evento, id_tipo_status,
               data_status, descricao, origem_tabela, origem_id, situacao, criado_em,
               atrasado)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'PENDENTE',%s,%s)
           ON CONFLICT (chave) DO NOTHING RETURNING id""",
        (int(protocolo_id), chave, evento, EVENTOS[evento], data_status,
         descricao.strip(), origem_tabela, int(origem_id), agora, 1 if atrasado else 0))
    return bool(linhas)


def _sem_derrubar(nome: str, faz: Callable[[Any], bool], con) -> bool:
    """O GANCHO NUNCA DERRUBA O FATO. Andamento que não se anotou é andamento
    que falta na Central; prenotação que não se gravou é prioridade perdida.
    O SAVEPOINT desfaz só a anotação e a transação de fora segue viva."""
    try:
        with banco(con).ponto_de_retorno("onr_acompanhamento") as bd:
            return bool(faz(bd))
    except Exception:                                   # noqa: BLE001
        LOG.exception("Acompanhamento do ONR: o gancho %s não se anotou", nome)
        return False


def anotar_prenotacao(con, protocolo_id: int, *, agora: str, atrasado: bool = False) -> bool:
    """«Título prenotado» (4). Chamado na transação que grava a prenotação."""
    def faz(bd):
        p = _protocolo(bd, protocolo_id)
        if not p:
            return False
        limite = (f" Prazo da prenotação: {_data_br(p.get('data_limite'))}."
                  if p.get("data_limite") else "")
        return anotar_na_fila(
            bd, protocolo_id=p["id"], evento="PRENOTADO",
            chave=f"PRENOTADO:ri_protocolos:{p['id']}",
            data_status=data_do_onr(p["data_prenotacao"], p.get("hora")),
            descricao=(f"Título prenotado sob o nº {p['numero']} do Livro 1 "
                       f"(Protocolo) em {_data_br(p['data_prenotacao'])}"
                       f"{', às ' + str(p['hora'])[:5] if p.get('hora') else ''}.{limite}"),
            origem_tabela="ri_protocolos", origem_id=p["id"], agora=agora, atrasado=atrasado)
    return _sem_derrubar("prenotacao", faz, con)


def anotar_prenotacao_retroativa(con, protocolo_id: int, *, agora: str) -> bool:
    """O «prenotado» do título que nasceu ANTES da fila (A008, 26/11/2026).

    PRONTO E DESLIGADO: só anota com `CHAVE_RETROATIVO` = 1 (decisão do
    titular). O fato é a prenotação de verdade, com a data dela — a mesma
    chave do gancho, e não um evento novo. Nasce ATRASADO quando a rotina já
    tem o marco: é andamento velho, e sai na liberação do título, junto com o
    resto dele. Não derruba nada: quem chama é o botão do ADMIN."""
    bd = banco(con)
    if _setting(bd, CHAVE_RETROATIVO, "0") != "1":
        raise AcompanhamentoError("O evento retroativo de prenotação está desligado. É decisão "
                                  "do titular: ligue a opção nesta tela antes.")
    init_schema(con)
    p = _protocolo(bd, protocolo_id)
    if not p:
        raise AcompanhamentoError("Essa prenotação não existe neste banco.")
    if bd.valor("SELECT COUNT(*) FROM onr_at_eventos WHERE protocolo_id=%s AND evento='PRENOTADO'",
                (int(protocolo_id),)):
        raise AcompanhamentoError("Este título já tem o «prenotado» na fila (ou ele foi "
                                  "descartado): nada a anotar.")
    marco = bool(_setting(bd, CHAVE_AUTO_DESDE, ""))
    return anotar_prenotacao(con, int(protocolo_id), agora=agora, atrasado=marco)


def _exigencias(texto: Any) -> list[str]:
    try:
        lista = json.loads(texto or "[]")
    except (TypeError, ValueError):
        lista = [texto]
    if not isinstance(lista, list):
        lista = [lista]
    return [str(e).strip() for e in lista if str(e or "").strip()]


def descricao_da_nota(nota: dict) -> str:
    """O texto da nota de exigência como vai à Central. O manual manda: «a
    nota de devolução deve ser informada nesse campo» (3.2.8 e 3.2.12).

    PUBLICADA AO INTERESSADO por decisão do oficial em 26/10/2026 («sim»):
    vai INTEIRA, sem corte — o campo é
    `text` —, porque nota pela metade na Central faria o apresentante voltar
    ao balcão sem a exigência que faltou ler."""
    linhas = [f"Nota de exigência nº {nota['numero']}, de {_data_br(nota['data_nota'])}."]
    linhas += [f"{i}. {e}" for i, e in enumerate(_exigencias(nota.get("exigencias")), 1)]
    if str(nota.get("fundamentacao") or "").strip():
        linhas.append(f"Fundamentação: {str(nota['fundamentacao']).strip()}")
    if nota.get("prazo_ate"):
        linhas.append(f"Prazo da prenotação: {_data_br(nota['prazo_ate'])}.")
    return "\n".join(linhas)


def anotar_nota_de_exigencia(con, nota_id: int, *, agora: str) -> bool:
    """«Nota de exigência» (7). Na transação que grava a nota devolutiva."""
    def faz(bd):
        n = bd.um("SELECT * FROM ri_notas_devolutivas WHERE id=%s", (int(nota_id),))
        p = _protocolo(bd, n["protocolo_id"]) if n else None
        if not n or not p:
            return False
        quando = data_do_onr(n["emitida_em"]) if n.get("emitida_em") else data_do_onr(n["data_nota"])
        return anotar_na_fila(
            bd, protocolo_id=p["id"], evento="EXIGENCIA",
            chave=f"EXIGENCIA:ri_notas_devolutivas:{n['id']}",
            data_status=_nao_antes_do_protocolo(quando, p),
            descricao=descricao_da_nota(n),
            origem_tabela="ri_notas_devolutivas", origem_id=n["id"], agora=agora)
    return _sem_derrubar("nota", faz, con)


def anotar_reingresso(con, nota_id: int, *, agora: str) -> bool:
    """«Título com reingresso» (1). Só o reingresso DENTRO do prazo — o de fora
    não volta à mesma prenotação (`ri_web.ri_reingresso`), e chamá-lo de
    reingresso na Central seria dizer que o título voltou à fila quando não
    voltou. Na transação que grava o reingresso."""
    def faz(bd):
        n = bd.um("SELECT * FROM ri_notas_devolutivas WHERE id=%s", (int(nota_id),))
        if not n or n.get("situacao") != "CUMPRIDA" or not n.get("data_reingresso"):
            return False
        p = _protocolo(bd, n["protocolo_id"])
        if not p:
            return False
        dia = str(n["data_reingresso"])[:10]
        quando = data_do_onr(agora) if dia == str(agora)[:10] else data_do_onr(dia)
        return anotar_na_fila(
            bd, protocolo_id=p["id"], evento="REINGRESSO",
            chave=f"REINGRESSO:ri_notas_devolutivas:{n['id']}",
            data_status=_nao_antes_do_protocolo(quando, p),
            descricao=(f"Título reapresentado em {_data_br(dia)}, com as exigências "
                       f"da nota nº {n['numero']}, dentro do prazo da prenotação."),
            origem_tabela="ri_notas_devolutivas", origem_id=n["id"], agora=agora)
    return _sem_derrubar("reingresso", faz, con)


def anotar_prorrogacao(con, protocolo_id: int, *, de: Any, para: Any, dias: int,
                       agora: str) -> bool:
    """«Prorrogado o prazo da prenotação» (15). É a retomada da contagem depois
    da suspensão (`ri_prenotacao_prazo.retomar`), que empurra `data_limite`.
    Sem dia a mais não há prorrogação, e nada sobe."""
    if not dias or not para or str(para) == str(de or ""):
        return False

    def faz(bd):
        p = _protocolo(bd, protocolo_id)
        if not p:
            return False
        return anotar_na_fila(
            bd, protocolo_id=p["id"], evento="PRORROGADO",
            chave=f"PRORROGADO:ri_protocolos:{p['id']}:{str(para)[:10]}",
            data_status=_nao_antes_do_protocolo(data_do_onr(agora), p),
            descricao=(f"Prazo da prenotação prorrogado de {_data_br(de)} para "
                       f"{_data_br(para)} ({int(dias)} dia(s) útil(eis) em que esteve suspenso)."),
            origem_tabela="ri_protocolos", origem_id=p["id"], agora=agora)
    return _sem_derrubar("prorrogacao", faz, con)


def anotar_duvida(con, protocolo_id: int, *, agora: str) -> bool:
    """«Suscitação de dúvida» (9): a suspensão do prazo pelo motivo DUVIDA."""
    def faz(bd):
        p = _protocolo(bd, protocolo_id)
        if not p or p.get("prazo_suspenso_motivo") != "DUVIDA":
            return False
        desde = str(p.get("prazo_suspenso_desde") or agora)[:10]
        return anotar_na_fila(
            bd, protocolo_id=p["id"], evento="DUVIDA",
            chave=f"DUVIDA:ri_protocolos:{p['id']}:{desde}",
            data_status=_nao_antes_do_protocolo(data_do_onr(agora), p),
            descricao=(f"Suscitada dúvida ao juízo competente em {_data_br(desde)}; "
                       "o prazo da prenotação fica suspenso até a decisão."),
            origem_tabela="ri_protocolos", origem_id=p["id"], agora=agora)
    return _sem_derrubar("duvida", faz, con)


def _rotulo_do_ato(ato: dict) -> str:
    try:
        return f"{ato['tipo']}-{int(ato['numero'])}"
    except (TypeError, ValueError, KeyError):
        return str(ato.get("tipo") or "ato")


def anotar_registro(con, protocolo_id: int, *, ato_id: int, agora: str) -> bool:
    """«Título registrado» (6): o ato lavrado que citou esta prenotação, quando
    ela está ABERTA — a mesma condição em que `amarrar_prenotacao` amarra (o
    primeiro ato) ou reconhece (os seguintes). Na transação do ato.

    Sobe só depois do SELO (`conferir_o_fato`): ato que o selador recusa é
    suspenso, e o «registrado» já teria ido."""
    def faz(bd):
        p = _protocolo(bd, protocolo_id)
        ato = bd.um("""SELECT a.*, m.numero AS matricula_numero FROM ri_atos a
                        LEFT JOIN ri_matriculas m ON m.id = a.matricula_id
                        WHERE a.id=%s""", (int(ato_id),))
        if not p or not ato or p.get("situacao") != "ABERTO":
            return False
        dia = str(ato.get("data_ato") or agora)[:10]
        quando = data_do_onr(agora) if dia == str(agora)[:10] else data_do_onr(dia)
        return anotar_na_fila(
            bd, protocolo_id=p["id"], evento="REGISTRADO",
            chave=f"REGISTRADO:ri_atos:{ato['id']}",
            data_status=_nao_antes_do_protocolo(quando, p),
            descricao=(f"Título registrado: ato {_rotulo_do_ato(ato)} na matrícula "
                       f"{ato.get('matricula_numero') or '—'}, em {_data_br(dia)}."),
            origem_tabela="ri_atos", origem_id=ato["id"], agora=agora)
    return _sem_derrubar("registro", faz, con)


# ------------------------------------------------------- conferir antes de subir

def conferir_o_fato(bd, ev: dict) -> tuple[str, str]:
    """('SOBE', '') | ('ESPERA', motivo) | ('ANULA', motivo). Só LÊ.

    O fato se confere de novo na hora de subir, e não só na hora de anotar:
    entre um e outro o ato pode ter sido desfeito, a nota apagada, o selo
    recusado. O que não existe mais não vai à Central."""
    tabela, oid = ev["origem_tabela"], int(ev["origem_id"])
    if not _protocolo(bd, ev["protocolo_id"]):
        return "ANULA", "a prenotação não existe mais neste banco"
    if tabela == "ri_notas_devolutivas":
        n = bd.um("SELECT situacao FROM ri_notas_devolutivas WHERE id=%s", (oid,))
        if not n:
            return "ANULA", "a nota devolutiva não existe mais"
        if ev["evento"] == "REINGRESSO" and n["situacao"] != "CUMPRIDA":
            return "ANULA", "o reingresso deixou de constar na nota"
        return "SOBE", ""
    if tabela == "ri_atos":
        cols = "id, cancelado" + (", selo_texto" if bd.tem_coluna("ri_atos", "selo_texto") else "")
        ato = bd.um(f"SELECT {cols} FROM ri_atos WHERE id=%s", (oid,))
        if not ato:
            return "ANULA", "o ato foi desfeito (não existe mais no livro)"
        if int(ato.get("cancelado") or 0):
            return "ANULA", "o ato está cancelado"
        if "selo_texto" in ato and not str(ato.get("selo_texto") or "").strip():
            return "ESPERA", "o ato ainda não tem selo — sobe quando for selado"
        return "SOBE", ""
    return "SOBE", ""


# ----------------------------------------------------- os campos do título

def _digitos(v: Any) -> str:
    return re.sub(r"\D", "", str(v or ""))


def _cortar(campo: str, valor: Any) -> str:
    texto = re.sub(r"\s+", " ", str(valor or "")).strip()
    teto = TAMANHO.get(campo)
    if teto and len(texto) > teto:
        texto = texto[:teto - 1].rstrip() + "…"
    return texto


def telefone_do_onr(telefone: Any) -> tuple[str, str] | None:
    """(DDD, número) — ou None quando não dá para separar sem adivinhar."""
    d = _digitos(telefone)
    if d.startswith("55") and len(d) in (12, 13):
        d = d[2:]
    if d.startswith("0") and len(d) in (11, 12):
        d = d[1:]
    if len(d) not in (10, 11):
        return None
    return d[:2], d[2:]


def campos_do_titulo(p: dict, ev: dict) -> dict:
    """Os campos do `InsertTituloAT` — o título como está NESTE banco, e o
    evento da fila como status inicial. Recusa (`AcompanhamentoError`) o que
    o manual exige e a prenotação não tem: melhor a fila esperar com a frase
    do que o ONR recusar com um código.

    DECISÕES DESTA PASSADA, para o oficial conferir:
      - `InteressadoNome` é o APRESENTANTE: a prenotação não guarda
        interessado à parte, e o protocolo geral desta casa faz o mesmo
        (`caixa_protocolo.abrir(interessado=apresentante)`).
      - `DataPrevisaoEntrega` é o fim do prazo da prenotação (`data_limite`).
      - `ModoNotificacaoStatus` é «E» quando há e-mail e «S» quando só há
        telefone: **o ONR avisa o apresentante a cada status** por esse meio.
      - Valores de depósito e de emolumentos não vão (são opcionais)."""
    numero = _digitos(p.get("numero"))
    if not numero or len(numero) > 11:
        raise AcompanhamentoError(f"O número do protocolo «{p.get('numero')}» não cabe no ONR "
                                  "(até 11 algarismos).")
    apresentante = _cortar("ApresentanteNome", p.get("apresentante"))
    if not apresentante:
        raise AcompanhamentoError("A prenotação não tem o nome do apresentante — corrija na "
                                  "ficha do protocolo antes de mandar ao ONR.")
    natureza = _cortar("NaturezaTitulo", p.get("natureza_titulo"))
    if not natureza:
        raise AcompanhamentoError("A prenotação não tem a natureza do título — o ONR a exige "
                                  "(erro 18). Corrija na ficha do protocolo.")
    if not p.get("data_limite"):
        raise AcompanhamentoError("A prenotação não tem prazo (data limite) — é dele que sai "
                                  "a previsão de entrega que o ONR exige.")
    email = _cortar("ApresentanteEmail", p.get("email"))
    fone = telefone_do_onr(p.get("telefone"))
    if email:
        modo = "E"
    elif fone:
        modo = "S"
    else:
        raise AcompanhamentoError("Sem e-mail nem telefone (com DDD) do apresentante: o ONR "
                                  "exige um meio de avisá-lo (erros 19 a 21).")
    doc = _digitos(p.get("apresentante_documento"))
    doc = doc if len(doc) in (11, 14) else ""
    data_protocolo = data_do_onr(p["data_prenotacao"], p.get("hora"))
    campos = {
        "Protocolo": numero,
        "ApresentanteNome": apresentante,
        "ApresentanteEmail": email or None,
        "ApresentanteDDDTelefone": fone[0] if (fone and modo == "S") else None,
        "ApresentanteNumeroTelefone": fone[1] if (fone and modo == "S") else None,
        "ApresentanteCPFCNPJ": doc or None,
        "DataProtocolo": data_protocolo,
        "DataPrevisaoEntrega": data_do_onr(p["data_limite"], "23:59:59"),
        "ModoNotificacaoStatus": modo,
        "InteressadoNome": apresentante,
        "InteressadoCPFCNPJ": doc or None,
        "NaturezaTitulo": natureza,
        "TipoSolicitacao": 1,                      # 1 = Prenotação (manual 3.2.8)
        "IDTipoStatus": int(ev["id_tipo_status"]),
        "DataStatus": max(ev["data_status"], data_protocolo),
        "DescricaoStatus": ev["descricao"],
    }
    return {k: v for k, v in campos.items() if v is not None}


# ------------------------------------------------------------- o envio

def ligado(get_setting) -> bool:
    return str(get_setting(CHAVE_LIGADO, "0") or "0").strip() == "1"


def ambiente(get_setting) -> str:
    """O ambiente do acompanhamento. Vazio ou desconhecido é a PRODUÇÃO —
    o padrão de fábrica que o oficial escolheu em 26/10/2026."""
    valor = str(get_setting(CHAVE_AMBIENTE, AMBIENTE_DE_FABRICA) or AMBIENTE_DE_FABRICA)
    valor = valor.strip().upper()
    return valor if valor in WS.BASE else AMBIENTE_DE_FABRICA


def _pendentes(con, protocolo_id: int | None = None) -> list[dict]:
    """A fila INTEIRA dos pendentes, na ordem de cada título. Sem `LIMIT`: o
    limite da rodada conta CHAMADAS ao ONR, e não linhas lidas — senão cem
    atrasados no topo da fila calariam para sempre o evento novo de baixo."""
    init_schema(con)
    filtro, args = ("AND protocolo_id=%s", (int(protocolo_id),)) if protocolo_id else ("", ())
    return banco(con).ler(
        f"""SELECT * FROM onr_at_eventos WHERE situacao='PENDENTE' {filtro}
             ORDER BY protocolo_id, data_status, id LIMIT 5000""", args)


def _id_do_onr(r: dict, campo: str) -> int | None:
    try:
        return int(str(r.get(campo) or "").strip())
    except ValueError:
        return None


# ------------------------------------------------- as travas (A008, 26/11/2026)

def _setting(bd, chave: str, padrao: str = "") -> str:
    """A configuração da casa, lida na conexão que já está aberta. Banco sem
    a tabela (o de teste do domínio) é o padrão de fábrica."""
    if not bd.tem_tabela("settings"):
        return padrao
    linha = bd.um("SELECT value FROM settings WHERE key=%s", (chave,))
    return str(linha["value"]).strip() if linha and linha["value"] is not None else padrao


def texto_curto_ligado(bd) -> bool:
    return _setting(bd, CHAVE_TEXTO_CURTO, "0") == "1"


def _sem_acento(texto: Any) -> str:
    nfkd = unicodedata.normalize("NFKD", str(texto or ""))
    return " ".join("".join(c for c in nfkd if not unicodedata.combining(c)).lower().split())


def bloqueio_da_exigencia(descricao: Any) -> str:
    """'' quando a exigência pode subir; senão, o motivo, para a tela.

    Duas coisas não vão ao apresentante (A007, § 3): a «nota» sem nenhuma
    exigência no texto (só o cabeçalho, ou uma frase solta sem número) e o
    rascunho que ficou na nota («a conferir pelo oficial»...)."""
    texto = str(descricao or "")
    if not any(re.match(r"^\s*\d+\.\s+\S", linha) for linha in texto.splitlines()):
        return ("a nota não tem nenhuma exigência no texto — corrija a nota (ou exclua-a e "
                "emita de novo) ou descarte este andamento com o motivo")
    plano = _sem_acento(texto)
    for padrao in _RASCUNHO:
        achado = padrao.search(plano)
        if achado:
            return (f"o texto tem frase de rascunho («{achado.group(0)}») — iria ao "
                    "apresentante. Corrija a nota (ou exclua-a e emita de novo) antes de "
                    "mandar ao ONR")
    return ""


def descricao_curta(descricao: Any) -> str:
    """O texto CURTO da exigência, tirado do próprio texto da fila (a mesma
    fonte do texto inteiro): «Nota de exigência nº N, de dd/mm/aaaa. Prazo:
    dd/mm/aaaa.». Só vai com `CHAVE_TEXTO_CURTO` ligada."""
    texto = str(descricao or "")
    m = re.search(r"Nota de exigência nº\s*(\S+), de (\d{2}/\d{2}/\d{4})", texto)
    if not m:
        return texto.splitlines()[0].strip() if texto.strip() else ""
    prazo = re.search(r"Prazo da prenotação:\s*(\d{2}/\d{2}/\d{4})", texto)
    return (f"Nota de exigência nº {m.group(1)}, de {m.group(2)}."
            + (f" Prazo: {prazo.group(1)}." if prazo else ""))


def texto_que_sobe(ev: dict, *, texto_curto: bool) -> str:
    """O `DescricaoStatus` que vai ao ONR — o da fila, ou o curto da exigência."""
    if ev.get("evento") == "EXIGENCIA" and texto_curto:
        return descricao_curta(ev.get("descricao"))
    return str(ev.get("descricao") or "")


_REGISTRO = re.compile(r"ato (\S+) na matrícula (\S+?),")


def chave_do_registro(ev: dict) -> tuple | None:
    """(protocolo, ato, matrícula) do «Título registrado», tirada do texto que
    o gancho escreveu (`anotar_registro`) — que fica certo mesmo quando o ato
    foi desfeito e não existe mais no livro."""
    if ev.get("evento") != "REGISTRADO":
        return None
    m = _REGISTRO.search(str(ev.get("descricao") or ""))
    return (int(ev["protocolo_id"]), m.group(1), m.group(2)) if m else None


def _registro_repetido(bd, ev: dict) -> str:
    """O motivo, quando o mesmo (protocolo, ato, matrícula) já foi ENVIADO."""
    chave = chave_do_registro(ev)
    if not chave:
        return ""
    for outro in bd.ler("""SELECT id, protocolo_id, evento, descricao FROM onr_at_eventos
                            WHERE protocolo_id=%s AND evento='REGISTRADO' AND situacao='ENVIADO'
                              AND id<>%s""", (int(ev["protocolo_id"]), int(ev["id"]))):
        if chave_do_registro(outro) == chave:
            return (f"repete o andamento já enviado (ato {chave[1]} na matrícula {chave[2]}): "
                    "um «registrado» por ato e matrícula")
    return ""


def _tem_prenotado(bd, protocolo_id: int) -> bool:
    return bool(bd.valor("""SELECT COUNT(*) FROM onr_at_eventos WHERE protocolo_id=%s
                             AND evento='PRENOTADO' AND situacao IN ('PENDENTE','ENVIADO')""",
                         (int(protocolo_id),)))


_EMAIL_NO_TEXTO = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_DATA_BR = r"(\d{2})/(\d{2})/(\d{4})"


def _iso_de_br(m) -> str:
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"


SEM_MEIO_DE_AVISAR = ("Sem e-mail nem telefone (com DDD) do apresentante: o ONR exige um meio "
                      "de avisá-lo (erros 19 a 21). Corrija na ficha do protocolo.")


def pendencias_do_cadastro(p: dict, ev: dict, *, titulo_no_onr: bool) -> list[str]:
    """As frases de correção do que o cadastro tem de errado PARA ESTE envio.

    Só o que o ONR não recusaria e que ficaria errado na Central (o nome com
    o e-mail dentro, a data incoerente) ou que ele recusaria com um número
    (sem meio de avisar). O título já cadastrado no ONR não manda o nome de
    novo: aí só conta o texto do próprio andamento."""
    frases = []
    if not titulo_no_onr:
        if _EMAIL_NO_TEXTO.search(str(p.get("apresentante") or "")):
            frases.append("O nome do apresentante tem um e-mail dentro: tire o e-mail do nome "
                          "na ficha do protocolo (o e-mail vai no campo próprio).")
        if not str(p.get("email") or "").strip() and not telefone_do_onr(p.get("telefone")):
            frases.append(SEM_MEIO_DE_AVISAR)
        limite, inicio = str(p.get("data_limite") or "")[:10], str(p.get("data_prenotacao") or "")[:10]
        if limite and inicio and limite < inicio:
            frases.append(f"O prazo da prenotação ({_data_br(limite)}) é anterior à própria "
                          f"prenotação ({_data_br(inicio)}): corrija o prazo na ficha do protocolo.")
    if ev.get("evento") == "EXIGENCIA":
        texto = str(ev.get("descricao") or "")
        de = re.search(r"Nota de exigência nº\s*\S+, de " + _DATA_BR, texto)
        prazo = re.search(r"Prazo da prenotação:\s*" + _DATA_BR, texto)
        if de and prazo and _iso_de_br(prazo) < _iso_de_br(de):
            frases.append(f"A nota diz prazo da prenotação {prazo.group(0).split(':')[-1].strip()}, "
                          f"anterior à data da própria nota ({de.group(0).rsplit(' ', 1)[-1]}): "
                          "exclua a nota e emita de novo com o prazo certo, ou descarte este "
                          "andamento com o motivo.")
    return frases


def avaliar(bd, ev: dict, *, titulo: dict | None, p: dict | None = None,
            texto_curto: bool = False, criado_ate: str | None = None,
            forcar: bool = False, tem_prenotado: bool | None = None) -> dict:
    """O que fazer com UM pendente agora. Só LÊ.

    Devolve {acao: SOBE|ESPERA|ANULA, espera: chave de `ESPERAS`, frase,
    texto (o que sobe), campos (do `InsertTituloAT`, se o título é novo)}.
    `forcar` é a chamada de prova: o ADMIN escolheu este título, viu o que
    sobe e confirmou — vale como a liberação do atrasado e dispensa a
    carência; as outras travas continuam."""
    def espera(chave: str, frase: str = "") -> dict:
        return {"acao": "ESPERA", "espera": chave, "frase": frase or ESPERAS[chave],
                "texto": "", "campos": None}

    if int(ev.get("atrasado") or 0) and not ev.get("liberado_em") and not forcar:
        return espera("ATRASADO")
    if criado_ate and str(ev.get("criado_em") or "") > criado_ate and not forcar:
        return espera("CARENCIA")
    veredito, motivo = conferir_o_fato(bd, ev)
    if veredito == "ANULA":
        return {"acao": "ANULA", "espera": "", "frase": motivo, "texto": "", "campos": None}
    if veredito == "ESPERA":
        return espera("SELO", motivo)
    repetido = _registro_repetido(bd, ev)
    if repetido:
        return {"acao": "ANULA", "espera": "", "frase": repetido, "texto": "", "campos": None}
    pid = int(ev["protocolo_id"])
    p = p if p is not None else _protocolo(bd, pid)
    if titulo is None and ev["evento"] != "PRENOTADO":
        if not (tem_prenotado if tem_prenotado is not None else _tem_prenotado(bd, pid)):
            return espera("DECISAO", "Precisa de decisão: o título ainda não está no ONR e a "
                                     "fila não tem o «prenotado» dele (a prenotação é anterior "
                                     "à fila). Nada dele sobe até o titular decidir.")
    if ev["evento"] == "EXIGENCIA":
        bloqueio = bloqueio_da_exigencia(ev.get("descricao"))
        if bloqueio:
            return espera("BLOQUEIO", f"Exigência bloqueada: {bloqueio}.")
        if not texto_curto and not ev.get("revisado_em"):
            return espera("REVISAO", "Exigência aguardando revisão: o texto inteiro vai ao "
                                     "apresentante, e só sobe depois de alguém marcar "
                                     "«revisada».")
    frases = pendencias_do_cadastro(p or {}, ev, titulo_no_onr=titulo is not None)
    if frases:
        return espera("DADO", "Esperando dado: " + " ".join(frases))
    texto = texto_que_sobe(ev, texto_curto=texto_curto)
    campos = None
    if titulo is None:
        try:
            campos = campos_do_titulo(p, dict(ev, descricao=texto))
        except AcompanhamentoError as erro:
            return espera("DADO", f"Esperando dado: {erro}")
    return {"acao": "SOBE", "espera": "", "frase": "", "texto": texto, "campos": campos}


def _feito() -> dict:
    return {"enviados": 0, "esperando": 0, "recusados": 0, "anulados": 0, "titulos_novos": 0,
            "parou": "", "atrasados": 0, "em_carencia": 0, "por_espera": {},
            "recusas": [], "no_limite": False, "tempo_esgotado": False}


def enviar_pendentes(db, sessao_de: Callable[[], Any], *, amb: str, quem: str,
                     agora: Callable[[], str], limite: int = 100,
                     criado_ate: str | None = None, prazo_s: float | None = None,
                     so_protocolo: int | None = None, forcar: bool = False,
                     relogio: Callable[[], float] = time.monotonic) -> dict:
    """Manda a fila ao ONR, um evento por chamada, NA ORDEM de cada título.

    A REDE NUNCA DENTRO DE TRANSAÇÃO: lê a fila, chama o ONR, e só então abre
    uma transação curta para gravar o que ele respondeu. Se a gravação
    falhar depois de o ONR aceitar, a próxima rodada manda de novo e o ONR
    responde 501 com o mesmo identificador — que é aproveitado.

    Evento de um título que espera ou é recusado SEGURA os seguintes daquele
    título (o andamento sobe em ordem); os outros títulos seguem. Falha de
    transporte ou de login (que não é recusa do ONR sobre o evento) para a
    rodada inteira: é da ligação, e não do evento.

    A008 (26/11/2026): cada evento passa por `avaliar` (as travas). `limite`
    conta CHAMADAS ao ONR; `prazo_s` para a rodada antes do `timeout_s` do
    processo; `criado_ate` é a carência (só a rotina a usa); `so_protocolo`
    com `forcar` é a chamada de prova de um título."""
    with db.connect() as con:
        fila = _pendentes(con, so_protocolo)
        curto = texto_curto_ligado(banco(con))
    feito = _feito()
    if not fila:
        return feito
    sessao = None
    travados: set[int] = set()
    inicio, tentados = relogio(), 0
    for ev in fila:
        pid = int(ev["protocolo_id"])
        if pid in travados:
            continue
        if tentados >= limite:
            feito["no_limite"] = True
            break
        if prazo_s is not None and relogio() - inicio > prazo_s:
            feito["tempo_esgotado"] = True
            break
        with db.connect() as con:
            bd = banco(con)
            p = _protocolo(bd, pid)
            titulo = bd.um("SELECT * FROM onr_at_titulos WHERE ambiente=%s AND protocolo_id=%s",
                           (amb, pid))
            v = avaliar(bd, ev, titulo=titulo, p=p, texto_curto=curto, criado_ate=criado_ate,
                        forcar=forcar)
        if v["acao"] == "ANULA":
            with db.transaction() as con:
                banco(con).escrever(
                    """UPDATE onr_at_eventos SET situacao='ANULADO', motivo_fim=%s, espera=NULL,
                           ultima_tentativa_em=%s WHERE id=%s AND situacao='PENDENTE'""",
                    (v["frase"], agora(), ev["id"]))
            feito["anulados"] += 1
            continue
        if v["acao"] == "ESPERA":
            chave = v["espera"]
            feito["por_espera"][chave] = feito["por_espera"].get(chave, 0) + 1
            if chave == "ATRASADO":
                feito["atrasados"] += 1
            elif chave == "CARENCIA":
                feito["em_carencia"] += 1
            else:
                feito["esperando"] += 1
                _anotar_erro(db, ev, v["frase"], agora(), conta=False, espera=chave)
            travados.add(pid)
            continue
        tentados += 1
        try:
            if sessao is None:
                sessao = sessao_de()
            if titulo is None:
                try:
                    r = sessao.cadastrar_titulo_no_acompanhamento(v["campos"])
                    id_titulo, como = _id_do_onr(r, "IDTitulo"), "CADASTRADO"
                    id_status = _id_do_onr(r, "IDStatus")
                except WS.WSOficioRecusou as e:
                    # 501: o protocolo já está cadastrado para esta serventia, e o
                    # ONR devolve o IDTitulo. Aproveita-se, e o status vai à parte.
                    if str(e.codigo) != "501" or not _id_do_onr(e.resposta, "IDTitulo"):
                        raise
                    id_titulo, como, id_status = _id_do_onr(e.resposta, "IDTitulo"), "JA_EXISTIA", None
                if not id_titulo:
                    raise WS.WSOficioError("O ONR aceitou o título e não devolveu o IDTitulo.")
                with db.transaction() as con:
                    init_schema(con)
                    banco(con).escrever(
                        """INSERT INTO onr_at_titulos (ambiente, protocolo_id, protocolo_numero,
                               id_titulo_onr, como, cadastrado_em, cadastrado_por)
                           VALUES (%s,%s,%s,%s,%s,%s,%s)
                           ON CONFLICT (ambiente, protocolo_id) DO NOTHING""",
                        (amb, pid, str(p["numero"]), id_titulo, como, agora(), quem))
                feito["titulos_novos"] += 1
                if como == "JA_EXISTIA":
                    id_status = _mandar_status(sessao, id_titulo, ev, v["texto"])
            else:
                id_status = _mandar_status(sessao, int(titulo["id_titulo_onr"]), ev, v["texto"])
        except WS.WSOficioRecusou as e:
            _anotar_erro(db, ev, str(e), agora(), conta=True, espera="RECUSA")
            feito["recusados"] += 1
            feito["recusas"].append({"evento_id": ev["id"], "protocolo_id": pid,
                                     "protocolo_numero": str((p or {}).get("numero") or ""),
                                     "evento": ev["evento"], "codigo": str(e.codigo),
                                     "texto": str(e.descricao or "")[:200]})
            travados.add(pid)
            continue
        except WS.WSOficioError as e:
            _anotar_erro(db, ev, str(e), agora(), conta=True, espera=None)
            feito["parou"] = str(e)
            break
        with db.transaction() as con:
            banco(con).escrever(
                """UPDATE onr_at_eventos SET situacao='ENVIADO', ambiente=%s, id_status_onr=%s,
                       enviado_em=%s, enviado_por=%s, tentativas=tentativas+1,
                       ultima_tentativa_em=%s, ultimo_erro=NULL, espera=NULL
                    WHERE id=%s AND situacao='PENDENTE'""",
                (amb, id_status, agora(), quem, agora(), ev["id"]))
        feito["enviados"] += 1
    return feito


def _mandar_status(sessao, id_titulo: int, ev: dict, texto: str | None = None) -> int | None:
    """`InsertStatusAT`; o 501 («status já cadastrado») traz o IDStatus, e o
    evento conta como enviado — foi a rodada anterior que o mandou."""
    try:
        r = sessao.cadastrar_status_no_acompanhamento(
            id_titulo, tipo_status=int(ev["id_tipo_status"]),
            data_status=ev["data_status"], descricao=texto if texto is not None else ev["descricao"])
        return _id_do_onr(r, "IDStatus")
    except WS.WSOficioRecusou as e:
        if str(e.codigo) == "501" and _id_do_onr(e.resposta, "IDStatus"):
            return _id_do_onr(e.resposta, "IDStatus")
        raise


def _anotar_erro(db, ev: dict, erro: str, quando: str, *, conta: bool,
                 espera: str | None = None) -> None:
    with db.transaction() as con:
        init_schema(con)
        banco(con).escrever(
            f"""UPDATE onr_at_eventos SET ultimo_erro=%s, ultima_tentativa_em=%s, espera=%s
                   {', tentativas=tentativas+1' if conta else ''}
                 WHERE id=%s AND situacao='PENDENTE'""",
            (erro[:1000], quando, espera, ev["id"]))


# ------------------------------------------- a rotina e as decisões (A008)

def travar_atrasados(db, *, agora: str) -> int:
    """O MARCO DOS ATRASADOS — uma vez só, na primeira rodada em que a rotina
    pode enviar: tudo o que já está PENDENTE vira ATRASADO e espera a
    liberação do titular. Devolve quantos marcou (0 quando o marco já existe).

    Não «ao ligar o processo» na tela, porque ligar sem «pode agir» só mede:
    o que importa é o primeiro momento em que a rotina pode mandar sozinha."""
    with db.transaction() as con:
        init_schema(con)
        bd = banco(con)
        if _setting(bd, CHAVE_AUTO_DESDE, ""):
            return 0
        bd.escrever("""UPDATE onr_at_eventos SET atrasado=1
                        WHERE situacao='PENDENTE' AND COALESCE(atrasado,0)=0""")
        n = max(0, int(bd.linhas_afetadas or 0))
        bd.escrever("""INSERT INTO settings(key, value) VALUES (%s, %s)
                       ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
                    (CHAVE_AUTO_DESDE, agora))
    return n


def liberar_atrasados(con, *, quem: str, agora: str, protocolo_id: int | None = None) -> int:
    """O titular libera os atrasados — todos, ou os de um título. Quem chama
    audita. Liberado não é enviado: a rotina o leva, com as outras travas."""
    init_schema(con)
    filtro, args = ("AND protocolo_id=%s", (int(protocolo_id),)) if protocolo_id else ("", ())
    bd = banco(con)
    bd.escrever(f"""UPDATE onr_at_eventos SET liberado_em=%s, liberado_por=%s
                     WHERE situacao='PENDENTE' AND atrasado=1 AND liberado_em IS NULL {filtro}""",
                (agora, quem, *args))
    return max(0, int(bd.linhas_afetadas or 0))


def marcar_revisada(con, evento_id: int, *, quem: str, agora: str) -> dict:
    """«Revisada por … em …» — a exigência de texto inteiro pode subir.
    Recusa a bloqueada: o rascunho e a nota vazia se corrigem na nota."""
    init_schema(con)
    bd = banco(con)
    ev = bd.um("SELECT * FROM onr_at_eventos WHERE id=%s", (int(evento_id),))
    if not ev or ev["evento"] != "EXIGENCIA":
        raise AcompanhamentoError("Só a nota de exigência se marca como revisada.")
    if ev["situacao"] != "PENDENTE":
        raise AcompanhamentoError(f"Essa exigência já está {ev['situacao'].lower()}.")
    if ev.get("revisado_em"):
        raise AcompanhamentoError(f"Essa exigência já foi revisada por {ev.get('revisado_por')}.")
    bloqueio = bloqueio_da_exigencia(ev["descricao"])
    if bloqueio:
        raise AcompanhamentoError(f"Não dá para marcar como revisada: {bloqueio}.")
    if not (quem or "").strip():
        raise AcompanhamentoError("Quem revisou precisa estar identificado.")
    bd.escrever("""UPDATE onr_at_eventos SET revisado_em=%s, revisado_por=%s
                    WHERE id=%s AND situacao='PENDENTE'""", (agora, quem.strip(), int(evento_id)))
    return dict(ev)


def precisam_de_decisao(con, *, amb: str) -> list[dict]:
    """Os títulos com andamento pendente que ainda não estão no ONR e não têm
    o «prenotado» na fila — os anteriores à fila. Nada deles sobe."""
    init_schema(con)
    return banco(con).ler(
        """SELECT e.protocolo_id, p.numero AS protocolo_numero, p.data_prenotacao,
                  COUNT(*) AS pendentes
             FROM onr_at_eventos e LEFT JOIN ri_protocolos p ON p.id = e.protocolo_id
            WHERE e.situacao='PENDENTE'
              AND NOT EXISTS (SELECT 1 FROM onr_at_titulos t
                               WHERE t.protocolo_id=e.protocolo_id AND t.ambiente=%s)
              AND NOT EXISTS (SELECT 1 FROM onr_at_eventos x
                               WHERE x.protocolo_id=e.protocolo_id AND x.evento='PRENOTADO'
                                 AND x.situacao IN ('PENDENTE','ENVIADO'))
            GROUP BY e.protocolo_id, p.numero, p.data_prenotacao
            ORDER BY p.numero""", (amb,))


def registros_repetidos(con) -> dict:
    """Quantos «registrado» (pendentes e enviados) repetem (protocolo, ato,
    matrícula) — a medida que a A007 pediu. Os que a conferência anularia
    (ato desfeito ou cancelado) contam à parte: esses saem pela conferência,
    e não pela regra da repetição."""
    init_schema(con)
    bd = banco(con)
    linhas = bd.ler("""SELECT * FROM onr_at_eventos WHERE evento='REGISTRADO'
                        AND situacao IN ('PENDENTE','ENVIADO') ORDER BY protocolo_id, data_status, id""")
    vistos: set = set()
    total, repetidos, anulariam = len(linhas), 0, 0
    for ev in linhas:
        if conferir_o_fato(bd, ev)[0] == "ANULA":
            anulariam += 1
            continue
        chave = chave_do_registro(ev)
        if chave in vistos:
            repetidos += 1
        elif chave:
            vistos.add(chave)
    return {"registrados": total, "repetidos": repetidos, "anulariam": anulariam,
            "unicos": len(vistos)}


def medir(con, *, amb: str, criado_ate: str | None = None,
          acumulado_antes_de: str | None = None) -> dict:
    """A fotografia da fila para a rotina e para a tela. Só LÊ.

    Cada pendente passa por `avaliar` (sem o encadeamento por título da
    rodada): quantos subiriam, quantos esperam e por quê, quantos estão na
    fila desde antes de `acumulado_antes_de` (1 dia útil), as recusas que o
    ONR deu e não foram resolvidas."""
    init_schema(con)
    bd = banco(con)
    curto = texto_curto_ligado(bd)
    protocolos: dict[int, dict | None] = {}
    titulos: dict[int, dict | None] = {}
    prenotados: dict[int, bool] = {}
    out = {"pendentes": 0, "subiriam": 0, "por_espera": {}, "acumulando": 0,
           "mais_antigo": None, "recusas": [], "esperando_dado": [], "texto_curto": curto}
    for ev in _pendentes(con):
        pid = int(ev["protocolo_id"])
        if pid not in protocolos:
            protocolos[pid] = _protocolo(bd, pid)
            titulos[pid] = bd.um("SELECT * FROM onr_at_titulos WHERE ambiente=%s AND protocolo_id=%s",
                                 (amb, pid))
            prenotados[pid] = _tem_prenotado(bd, pid)
        out["pendentes"] += 1
        v = avaliar(bd, ev, titulo=titulos[pid], p=protocolos[pid], texto_curto=curto,
                    criado_ate=criado_ate, tem_prenotado=prenotados[pid])
        numero = str((protocolos[pid] or {}).get("numero") or pid)
        if v["acao"] == "SOBE":
            out["subiriam"] += 1
        elif v["acao"] == "ESPERA":
            out["por_espera"][v["espera"]] = out["por_espera"].get(v["espera"], 0) + 1
            if v["espera"] == "DADO":
                out["esperando_dado"].append({"protocolo_id": pid, "protocolo_numero": numero,
                                              "evento": ev["evento"], "frase": v["frase"]})
        if ev.get("espera") == "RECUSA":
            out["recusas"].append({"protocolo_id": pid, "protocolo_numero": numero,
                                   "evento": ev["evento"], "erro": str(ev.get("ultimo_erro") or "")})
        atrasado = int(ev.get("atrasado") or 0) and not ev.get("liberado_em")
        if (acumulado_antes_de and not atrasado and v["acao"] != "ANULA"
                and str(ev.get("criado_em") or "") < acumulado_antes_de):
            out["acumulando"] += 1
        criado = str(ev.get("criado_em") or "")
        if criado and (out["mais_antigo"] is None or criado < out["mais_antigo"]):
            out["mais_antigo"] = criado
    out["precisam_de_decisao"] = precisam_de_decisao(con, amb=amb)
    return out


def previa_da_prova(con, protocolo_id: int, *, amb: str) -> dict:
    """A CHAMADA DE PROVA DE 1 TÍTULO — o que vai subir, exatamente. Só LÊ.

    Percorre os pendentes do título na ordem em que subiriam, como a rodada
    faria com `forcar` (o ADMIN escolheu o título: vale como liberação e
    dispensa a carência). O primeiro que SOBE é o que a prova manda; um que
    ESPERA antes dele segura a prova, com a frase. O que seria ANULADO sai
    pela conferência, e a tela diz isso antes."""
    init_schema(con)
    bd = banco(con)
    p = _protocolo(bd, protocolo_id)
    if not p:
        raise AcompanhamentoError("Essa prenotação não existe neste banco.")
    titulo = bd.um("SELECT * FROM onr_at_titulos WHERE ambiente=%s AND protocolo_id=%s",
                   (amb, int(protocolo_id)))
    curto = texto_curto_ligado(bd)
    anulados, vai, segura = [], None, None
    for ev in _pendentes(con, protocolo_id):
        v = avaliar(bd, ev, titulo=titulo, p=p, texto_curto=curto, forcar=True)
        if v["acao"] == "ANULA":
            anulados.append({"evento": ev, "motivo": v["frase"]})
            continue
        if v["acao"] == "ESPERA":
            segura = {"evento": ev, "frase": v["frase"], "espera": v["espera"]}
            break
        metodo = "InsertTituloAT" if titulo is None else "InsertStatusAT"
        if titulo is None:
            campos = dict(v["campos"])
        else:
            campos = {"IDTitulo": int(titulo["id_titulo_onr"]),
                      "IDTipoStatus": int(ev["id_tipo_status"]),
                      "DataStatus": ev["data_status"], "DescricaoStatus": v["texto"]}
        ordem = [c for c in WS.CAMPOS[metodo] if c != "Hash"]
        vai = {"evento": ev, "metodo": metodo, "rotulo": rotulo_do_status(ev["id_tipo_status"]),
               "campos": [(c, campos[c]) for c in ordem if campos.get(c) is not None],
               "envelope": WS.envelope(metodo, dict(campos, Hash="(calculado na hora)"))
                             .decode("utf-8")}
        break
    return {"protocolo": p, "titulo": titulo, "ambiente": amb, "vai": vai, "segura": segura,
            "anulados": anulados, "texto_curto": curto}


def enviar_prova(db, sessao_de: Callable[[], Any], *, amb: str, quem: str,
                 agora: Callable[[], str], protocolo_id: int, evento_id: int) -> dict:
    """Manda a chamada de prova: UM evento, o que a prévia mostrou. Se a fila
    mudou entre a prévia e o clique (outro evento seria o primeiro), recusa."""
    with db.connect() as con:
        previa = previa_da_prova(con, protocolo_id, amb=amb)
    if not previa["vai"]:
        raise AcompanhamentoError(previa["segura"]["frase"] if previa["segura"]
                                  else "Este título não tem nada a subir.")
    if int(previa["vai"]["evento"]["id"]) != int(evento_id):
        raise AcompanhamentoError("A fila deste título mudou desde a prévia: confira de novo o "
                                  "que vai subir antes de confirmar. Nada foi enviado.")
    feito = enviar_pendentes(db, sessao_de, amb=amb, quem=quem, agora=agora, limite=1,
                             so_protocolo=int(protocolo_id), forcar=True)
    feito["evento_id"] = int(evento_id)
    return feito


def opcao(con, chave: str, ligar: bool) -> None:
    """As duas opções que o titular ainda não decidiu (texto curto da
    exigência, prenotação retroativa). Quem chama é a tela do ADMIN, e audita."""
    if chave not in (CHAVE_TEXTO_CURTO, CHAVE_RETROATIVO):
        raise AcompanhamentoError("Essa opção não é do acompanhamento.")
    banco(con).escrever("""INSERT INTO settings(key, value) VALUES (%s, %s)
                           ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
                        (chave, "1" if ligar else "0"))


def descartar(con, evento_id: int, *, motivo: str, quem: str, agora: str) -> dict:
    """Tira da fila, com motivo, o que quem responde pela casa decidiu que
    não sobe. Só PENDENTE: o que já subiu se corrige no ONR, e não aqui."""
    init_schema(con)
    bd = banco(con)
    ev = bd.um("SELECT * FROM onr_at_eventos WHERE id=%s", (int(evento_id),))
    if not ev:
        raise AcompanhamentoError("Esse andamento não está na fila.")
    if ev["situacao"] != "PENDENTE":
        raise AcompanhamentoError(f"Esse andamento já está {ev['situacao'].lower()}: só se "
                                  "descarta o que ainda não foi enviado.")
    if len((motivo or "").strip()) < 10:
        raise AcompanhamentoError("Escreva por que este andamento não vai ao ONR (pelo menos "
                                  "dez letras) — é o que explica a ausência dele na Central.")
    bd.escrever("""UPDATE onr_at_eventos SET situacao='DESCARTADO', motivo_fim=%s,
                       ultima_tentativa_em=%s WHERE id=%s""",
                (f"{motivo.strip()} — {quem}" if quem else motivo.strip(), agora,
                 int(evento_id)))
    return dict(ev)


# ------------------------------------------------------------- as telas

def rotulo_do_status(id_tipo_status: Any) -> str:
    try:
        return WS.TIPO_STATUS_AT.get(int(id_tipo_status), str(id_tipo_status))
    except (TypeError, ValueError):
        return str(id_tipo_status or "")


def _anotar_avaliacao(bd, eventos: list[dict], *, amb: str) -> None:
    """Põe em cada PENDENTE o que a próxima rodada faria com ele, e por quê
    (`avaliacao`: acao, espera, frase). Só LÊ; protocolo e título uma vez
    por título."""
    curto = texto_curto_ligado(bd)
    cache: dict[int, tuple] = {}
    for ev in eventos:
        if ev.get("situacao") != "PENDENTE":
            ev["avaliacao"] = None
            continue
        pid = int(ev["protocolo_id"])
        if pid not in cache:
            cache[pid] = (_protocolo(bd, pid),
                          bd.um("SELECT * FROM onr_at_titulos WHERE ambiente=%s AND protocolo_id=%s",
                                (amb, pid)),
                          _tem_prenotado(bd, pid))
        p, titulo, prenotado = cache[pid]
        v = avaliar(bd, ev, titulo=titulo, p=p, texto_curto=curto, tem_prenotado=prenotado)
        ev["avaliacao"] = {"acao": v["acao"], "espera": v["espera"], "frase": v["frase"],
                           "rotulo": ESPERAS.get(v["espera"], "")}
        ev["bloqueio"] = (bloqueio_da_exigencia(ev["descricao"])
                          if ev["evento"] == "EXIGENCIA" else "")


def _avaliar_sem_derrubar(bd, eventos: list[dict], *, amb: str) -> None:
    """A trava na tela é informação: se a conta quebrar, a ficha e a fila abrem
    sem ela (o SAVEPOINT segura a transação no PostgreSQL)."""
    try:
        with bd.ponto_de_retorno("onr_avaliacao") as b:
            _anotar_avaliacao(b, eventos, amb=amb)
    except Exception:                                   # noqa: BLE001
        LOG.exception("Acompanhamento do ONR: não deu para avaliar a fila na tela")
        for ev in eventos:
            ev["avaliacao"], ev["bloqueio"] = None, ""


def _amb_do_banco(bd) -> str:
    return ambiente(lambda chave, padrao=None: _setting(bd, chave, padrao or ""))


def da_prenotacao(con, protocolo_id: int, *, amb: str | None = None) -> dict:
    """O que foi (e o que vai ser) mandado ao ONR sobre UMA prenotação, e a
    marca dos enviados cujo fato deixou de existir — esses estão na Central
    e não deviam: corrigir lá é decisão de quem responde pela casa. Desde a
    A008, cada pendente traz a trava que o segura, com a frase de correção."""
    init_schema(con)
    bd = banco(con)
    eventos = bd.ler("""SELECT * FROM onr_at_eventos WHERE protocolo_id=%s
                         ORDER BY data_status, id""", (int(protocolo_id),))
    for ev in eventos:
        ev["rotulo"] = rotulo_do_status(ev["id_tipo_status"])
        ev["fato_sumiu"] = ""
        if ev["situacao"] == "ENVIADO":
            veredito, motivo = conferir_o_fato(bd, ev)
            ev["fato_sumiu"] = motivo if veredito == "ANULA" else ""
    _avaliar_sem_derrubar(bd, eventos, amb=amb or _amb_do_banco(bd))
    titulos = bd.ler("SELECT * FROM onr_at_titulos WHERE protocolo_id=%s ORDER BY id",
                     (int(protocolo_id),))
    return {"eventos": eventos, "titulos": titulos}


def painel(con, *, todos: bool = False, limite: int = 300, amb: str | None = None) -> dict:
    """A fila: pendentes primeiro; com `todos`, também o que já foi. Desde a
    A008, cada pendente traz a trava que o segura (`avaliacao`)."""
    init_schema(con)
    bd = banco(con)
    amb = amb or _amb_do_banco(bd)
    filtro = "" if todos else "WHERE e.situacao='PENDENTE'"
    eventos = bd.ler(
        f"""SELECT e.*, p.numero AS protocolo_numero, p.apresentante
              FROM onr_at_eventos e LEFT JOIN ri_protocolos p ON p.id = e.protocolo_id
              {filtro}
             ORDER BY CASE WHEN e.situacao='PENDENTE' THEN 0 ELSE 1 END,
                      e.protocolo_id, e.data_status, e.id
             LIMIT %s""", (int(limite),))
    for ev in eventos:
        ev["rotulo"] = rotulo_do_status(ev["id_tipo_status"])
    _avaliar_sem_derrubar(bd, eventos, amb=amb)
    contagem = {s: 0 for s in SITUACOES}
    for linha in bd.ler("SELECT situacao, COUNT(*) AS n FROM onr_at_eventos GROUP BY situacao"):
        contagem[linha["situacao"]] = int(linha["n"])
    atrasados = int(bd.valor("""SELECT COUNT(*) FROM onr_at_eventos WHERE situacao='PENDENTE'
                                 AND atrasado=1 AND liberado_em IS NULL""") or 0)
    return {"eventos": eventos, "contagem": contagem, "atrasados": atrasados,
            "auto_desde": _setting(bd, CHAVE_AUTO_DESDE, ""),
            "texto_curto": texto_curto_ligado(bd),
            "retroativo": _setting(bd, CHAVE_RETROATIVO, "0") == "1",
            "precisam_de_decisao": precisam_de_decisao(con, amb=amb)}
