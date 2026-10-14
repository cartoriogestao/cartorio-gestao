"""OS PEDIDOS DE ATO DO RI — em que pé está cada título, numa tela só.

    «como podemos melhorar a organizacao dos processos protocolados, quero ter
     uma relacao mais clara e acompanhamento dos pedidos de atos, para saber
     melhor o que esta pendente de qualificacao e o que esta pendente de
     registro ou lavratura. Ja temos os expedientes pra isso, mas nao eh claro
     e organizado o suficiente e precisa de um cadastro especifico, gostaria de
     uma integracao melhor com o protocolo geral e protocolo do ri»
    — o oficial, 12/10/2026

O QUE SE MEDIU NA PRODUÇÃO ANTES DE ESCREVER (12/10/2026, só leitura)

| | |
|---|---|
| expedientes | **33**, todos do Malote Digital ou do PJe — circulares, portarias, ofícios. **Nenhum é pedido de cliente**: é por isso que a tela não servia para isto |
| prenotações abertas | **31** — e **nenhuma** diz se o título está a qualificar, em exigência ou apto |
| `ri_notas_devolutivas` | **zero** linhas: as notas eram feitas em Word, na pasta 15 do Proton |
| protocolo geral do RI × prenotação | **22** protocolos gerais do RI, **2** ligados; das 31 abertas, **1** com protocolo geral |

AS QUATRO DECISÕES DELE, NO MESMO DIA
    painel próprio (os Expedientes ficam para o que chega do Malote e do PJe);
    o protocolo geral nasce sozinho ao prenotar; a prenotação vencida é
    MARCADA e espera decisão — nada se encerra sozinho; e só o RI primeiro.

A ETAPA SE CALCULA; SÓ A QUALIFICAÇÃO SE GRAVA
    É a regra de `inacabados.py` — uma lente, e não uma segunda gaveta. Uma
    coluna «etapa» em `ri_protocolos` seria um segundo lugar dizendo o que o ato
    lavrado, a nota devolutiva e o prazo já dizem, e ela divergiria no primeiro
    ato lavrado por outra tela. O que NÃO existia em lugar nenhum era a decisão
    de qualificar: a positiva não tinha onde ficar, e a negativa era só a nota.
    `ri_qualificacoes` guarda essa decisão, na forma de `rg_qualificacoes` do
    RTD/RCPJ — **uma linha por qualificação, com a ordem**, porque o título volta
    com exigência, é requalificado, e sobrescrever a primeira decisão apagaria a
    razão pela qual ele voltou.

DUAS PALAVRAS, E NÃO TRÊS: POSITIVA e NEGATIVA
    O vocabulário é o do RTD/RCPJ. A negativa **é** a nota devolutiva — por
    isso ela não se grava por aqui: quem a grava é a rota da nota, na mesma
    transação, apontando `nota_id`. Duas portas para emitir exigência seriam
    duas versões da nota.

O QUE ESTE MÓDULO NÃO FAZ
    Não lavra, não numera, não sela, não cobra e não encerra prenotação. A
    vencida aparece marcada; quem decide é a pessoa, pela tela que já encerra
    com motivo escrito.
"""
from __future__ import annotations

import re
import sqlite3
from datetime import date
from typing import Any, Mapping

from ri_schema import dias_uteis_entre, normalizar_busca


class PedidoError(ValueError):
    """Erro de regra, com mensagem pronta para o balcão."""


POSITIVA = "POSITIVA"
NEGATIVA = "NEGATIVA"

#: As etapas, na ordem em que o título anda. A ordem é a do painel.
#:
#: QUEM MAIS LÊ ISTO (12/10/2026): o módulo de Processos do agente de
#: produtividade — `processo_pasta.etapa_do_ri` chama `etapa(p, ultima, hoje)`
#: e `qualificacoes_de(con, id)`, e tira o nome daqui como (código, nome,
#: explicação). Mudar uma das três assinaturas quebra a lista de Processos;
#: o guarda é `tests/test_processos_lista.py::test_a_etapa_do_ri_vem_da_regua_do_agente_do_ri`.
ETAPAS: tuple[tuple[str, str, str], ...] = (
    ("SEM_PRENOTACAO", "No balcão, sem prenotação",
     "Protocolo geral do RI aberto e ainda sem prenotação. Título que vai a "
     "registro se prenota; certidão e orçamento se encerram no protocolo geral."),
    ("A_QUALIFICAR", "A qualificar",
     "Prenotação correndo e nenhuma qualificação registrada — ou o título "
     "reingressou com as exigências cumpridas e espera nova qualificação."),
    ("EM_EXIGENCIA", "Em exigência",
     "Nota devolutiva emitida. A prenotação continua correndo enquanto o "
     "apresentante cumpre as exigências."),
    ("APTO", "Apto para registro",
     "Qualificação positiva e ato ainda não lavrado."),
    ("REGISTRADO", "Registrado — falta arquivar",
     "O ato já foi lavrado; falta o arquivamento do título e a entrega."),
    ("VENCIDA", "Vencida — decidir",
     "O prazo da prenotação acabou sem registro. Nada se encerra sozinho: "
     "quem decide encerra por decurso de prazo ou registra o que houve."),
)
ROTULO_DA_ETAPA = {chave: rotulo for chave, rotulo, _ in ETAPAS}

_ABERTAS = ("ABERTO", "DEVOLVIDO")


def _digitos(v: Any) -> str:
    return re.sub(r"\D", "", str(v or ""))


def _campo(linha: Mapping | None, chave: str) -> Any:
    if linha is None:
        return None
    try:
        return linha[chave]
    except (KeyError, IndexError):
        return None


def _vencida(p: Mapping, hoje: str) -> bool:
    """Prazo acabado e não suspenso. A data é texto ISO, e se compara como texto."""
    limite = _campo(p, "data_limite")
    if not limite or _campo(p, "prazo_suspenso_desde"):
        return False
    return str(limite)[:10] < hoje[:10]


def etapa(p: Mapping, ultima: Mapping | None, hoje: str) -> str:
    """Em que etapa está a prenotação `p`. SÓ LÊ.

    A ORDEM DAS PERGUNTAS É A REGRA:
      1. ato lavrado vem antes do prazo — o título registrado com a prenotação
         já vencida (11.548 e 11.565 na produção) não é «vencida», é ato que
         falta arquivar;
      2. o prazo vem antes da qualificação — título apto com o prazo acabado
         não pode mais ser registrado por esta prenotação;
      3. DEVOLVIDO é a nota devolutiva aberta;
      4. a última qualificação decide entre apto e a qualificar. Negativa com a
         prenotação ABERTA é reingresso: volta a qualificar.
    """
    if _campo(p, "ato_id"):
        return "REGISTRADO"
    if _vencida(p, hoje):
        return "VENCIDA"
    if _campo(p, "situacao") == "DEVOLVIDO":
        return "EM_EXIGENCIA"
    if ultima is not None and _campo(ultima, "resultado") == POSITIVA:
        return "APTO"
    return "A_QUALIFICAR"


def qualificacoes_de(con: sqlite3.Connection, protocolo_id: int) -> list[dict]:
    """As qualificações de uma prenotação, da primeira à última. SÓ LÊ."""
    con.row_factory = sqlite3.Row
    return [dict(r) for r in con.execute(
        """SELECT * FROM ri_qualificacoes WHERE protocolo_id=?
           ORDER BY ordem""", (int(protocolo_id),))]


def _prenotacao(con: sqlite3.Connection, protocolo_id: int) -> sqlite3.Row:
    con.row_factory = sqlite3.Row
    p = con.execute("SELECT * FROM ri_protocolos WHERE id=?",
                    (int(protocolo_id),)).fetchone()
    if not p:
        raise PedidoError(f"Não achei a prenotação id {protocolo_id}.")
    return p


def _gravar(con: sqlite3.Connection, protocolo_id: int, *, resultado: str,
            fundamentacao: str | None, nota_id: int | None, quem: str | None,
            usuario_id: int | None, agora: str) -> dict:
    ultima = con.execute(
        "SELECT MAX(ordem) FROM ri_qualificacoes WHERE protocolo_id=?",
        (int(protocolo_id),)).fetchone()[0]
    ordem = int(ultima or 0) + 1
    cur = con.execute(
        """INSERT INTO ri_qualificacoes
           (protocolo_id, ordem, resultado, fundamentacao, nota_id,
            data_qualificacao, qualificada_por, criado_em, criado_por)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (int(protocolo_id), ordem, resultado,
         (fundamentacao or "").strip() or None,
         int(nota_id) if nota_id else None,
         agora[:10], (quem or "").strip() or None, agora, usuario_id))
    return {"id": int(cur.lastrowid), "ordem": ordem, "resultado": resultado}


def qualificar_positiva(con: sqlite3.Connection, protocolo_id: int, *,
                        fundamentacao: str | None, quem: str | None,
                        usuario_id: int | None, agora: str) -> dict:
    """Registra que o título está apto para registro. GRAVA.

    NÃO LAVRA NADA: quem lavra é a tela do ato, com número, selo e custas. Isto
    só põe por escrito a decisão de que o título pode ir ao livro.

    TRÊS RECUSAS, e cada uma diz o que fazer:
      - prenotação encerrada ou cancelada não se qualifica;
      - em exigência (DEVOLVIDO), registra-se o reingresso antes — sem ele a
        qualificação positiva passaria por cima da nota que está aberta;
      - vencida, decide-se antes: registrar com prenotação vencida é registrar
        sem a prioridade que ela dava.
    """
    p = _prenotacao(con, protocolo_id)
    situacao = p["situacao"]
    if situacao not in _ABERTAS:
        raise PedidoError(
            f"A prenotação {p['numero']} está {str(situacao).lower()} — não se "
            f"qualifica título de prenotação que não está correndo.")
    if p["ato_id"]:
        raise PedidoError(
            f"A prenotação {p['numero']} já tem ato lavrado. A qualificação "
            f"vem antes do registro, e ele já saiu.")
    if situacao == "DEVOLVIDO":
        raise PedidoError(
            f"A prenotação {p['numero']} está em exigência. Registre o "
            f"reingresso na nota devolutiva antes de qualificar de novo.")
    if _vencida(p, agora[:10]):
        raise PedidoError(
            f"A prenotação {p['numero']} venceu em {p['data_limite']} sem "
            f"registro. Decida antes — encerrar por decurso do prazo, ou "
            f"suspender o prazo se houver hipótese do TJMA 452, § 3º.")
    return _gravar(con, protocolo_id, resultado=POSITIVA,
                   fundamentacao=fundamentacao, nota_id=None, quem=quem,
                   usuario_id=usuario_id, agora=agora)


def registrar_negativa(con: sqlite3.Connection, protocolo_id: int, *,
                       nota_id: int, fundamentacao: str | None,
                       quem: str | None, usuario_id: int | None,
                       agora: str) -> dict:
    """A qualificação negativa É a nota devolutiva. GRAVA.

    Chamada pela rota da nota, DENTRO da transação que a emite: nota sem a
    linha de qualificação faria o painel dizer «a qualificar» de um título que
    já foi devolvido.
    """
    _prenotacao(con, protocolo_id)
    return _gravar(con, protocolo_id, resultado=NEGATIVA,
                   fundamentacao=fundamentacao, nota_id=nota_id, quem=quem,
                   usuario_id=usuario_id, agora=agora)


def _anotacoes(con: sqlite3.Connection, tabela: str) -> dict[int, dict]:
    """Quem está cuidando e o que falta — a anotação de `inacabados`. SÓ LÊ."""
    try:
        return {int(r["item_id"]): dict(r) for r in con.execute(
            """SELECT item_id, texto, responsavel, ate FROM ex_anotacoes
               WHERE tabela=?""", (tabela,))}
    except sqlite3.OperationalError as erro:
        if "no such table" in str(erro):
            return {}
        raise


def _sugerir_pares(pedidos: list[dict]) -> None:
    """Protocolo geral sem prenotação × prenotação sem protocolo geral, pelo nome.

    MEDIDO NA PRODUÇÃO EM 12/10/2026: ELIAS BISPO DOS SANTOS está no protocolo
    geral 2026.08.172 sem prenotação, e na prenotação 11554 sem protocolo geral
    — o mesmo pedido em duas pontas que nunca se ligaram. (Eu tinha escrito
    «EDILSON, idem», e a medição desmentiu: a prenotação dele, 11571, JÁ tem o
    geral 2026.09.23; o 2026.09.22 é um segundo geral dele, sem prenotação — o
    caso de geral repetido, que se encerra no protocolo geral, e não se liga.)

    **É SUGESTÃO, E NÃO LIGAÇÃO.** O vínculo nasce de escolha humana — é a regra
    de `caixa_protocolo.vincular_ri` —, porque homônimo é a regra, e não a
    exceção. Aqui só se aponta onde conferir.
    """
    gerais = [x for x in pedidos if x["tipo"] == "PROTOCOLO_GERAL"]
    soltas = [x for x in pedidos if x["tipo"] == "PRENOTACAO" and not x["geral_id"]]
    por_nome: dict[str, list[dict]] = {}
    for g in gerais:
        chave = normalizar_busca(g.get("apresentante"))
        if chave:
            por_nome.setdefault(chave, []).append(g)
    for p in soltas:
        chave = normalizar_busca(p.get("apresentante"))
        for g in por_nome.get(chave, []) if chave else []:
            p.setdefault("pares", []).append(
                {"id": g["id"], "numero": g["numero"]})
            g.setdefault("pares", []).append(
                {"id": p["id"], "numero": p["numero"]})


def listar(con: sqlite3.Connection, *, hoje: date,
           feriados: set[date] | None = None) -> dict:
    """Os pedidos em andamento, cada um com a sua etapa. SÓ LÊ.

    São duas fontes: as prenotações que estão correndo (ABERTO e DEVOLVIDO) e
    os protocolos gerais do RI abertos que ainda não têm prenotação. **O acervo
    do E-Ofício não entra pelo protocolo geral** — eram 21 mil atendimentos
    antigos, e a regra de `inacabados` já os separa pela origem. Pela
    prenotação ele entra, e de propósito: as treze abertas sem apresentante
    vieram de lá, e estão vencidas esperando decisão.
    """
    con.row_factory = sqlite3.Row
    iso = hoje.isoformat()

    prenot = [dict(r) for r in con.execute(
        """SELECT * FROM ri_protocolos WHERE situacao IN ('ABERTO','DEVOLVIDO')
           ORDER BY numero""")]
    ids = [p["id"] for p in prenot]

    ultimas: dict[int, dict] = {}
    for r in con.execute(
            """SELECT protocolo_id, ordem, resultado, data_qualificacao,
                      qualificada_por
               FROM ri_qualificacoes ORDER BY protocolo_id, ordem"""):
        ultimas[int(r["protocolo_id"])] = dict(r)

    geral: dict[int, dict] = {}
    for r in con.execute(
            """SELECT id, numero, ri_protocolo_id FROM cx_protocolos
               WHERE ri_protocolo_id IS NOT NULL ORDER BY id"""):
        geral.setdefault(int(r["ri_protocolo_id"]), dict(r))

    saldo: dict[int, int] = {}
    from caixa_schema import centavos
    for r in con.execute(
            """SELECT ri_protocolo_id, saldo, encerrado FROM cx_depositos
               WHERE ri_protocolo_id IS NOT NULL"""):
        if not r["encerrado"]:
            pid = int(r["ri_protocolo_id"])
            saldo[pid] = saldo.get(pid, 0) + centavos(r["saldo"])

    minutas: dict[str, int] = {}
    for r in con.execute(
            """SELECT protocolo, prenotacao FROM ri_minutas
               WHERE situacao='A_REVISAR'"""):
        chave = _digitos(r["protocolo"]) or _digitos(r["prenotacao"])
        if chave:
            minutas[chave] = minutas.get(chave, 0) + 1

    anot_p = _anotacoes(con, "ri_protocolos")
    anot_c = _anotacoes(con, "cx_protocolos")

    pedidos: list[dict] = []
    for p in prenot:
        ultima = ultimas.get(p["id"])
        e = etapa(p, ultima, iso)
        restam = None
        if p.get("data_limite") and not p.get("prazo_suspenso_desde"):
            try:
                restam = dias_uteis_entre(
                    hoje, date.fromisoformat(str(p["data_limite"])[:10]),
                    feriados)
            except ValueError:
                restam = None
        g = geral.get(p["id"])
        pedidos.append({
            "tipo": "PRENOTACAO",
            "etapa": e,
            "id": p["id"],
            "numero": p["numero"],
            "livro": p.get("livro"),
            "data": p.get("data_prenotacao"),
            "data_limite": p.get("data_limite"),
            "restam": restam,
            "prazo_suspenso": bool(p.get("prazo_suspenso_desde")),
            "apresentante": p.get("apresentante"),
            "telefone": p.get("telefone"),
            "email": p.get("email"),
            "titulo": p.get("natureza_titulo") or p.get("objeto"),
            "matricula": p.get("matricula_numero"),
            "ato_id": p.get("ato_id"),
            "geral_id": g["id"] if g else None,
            "geral_numero": g["numero"] if g else None,
            "saldo_deposito": saldo.get(p["id"]),
            "minutas": minutas.get(_digitos(p["numero"]), 0),
            "ultima": ultima,
            "reingresso": (e == "A_QUALIFICAR" and ultima is not None
                           and ultima.get("resultado") == NEGATIVA),
            "anotacao": anot_p.get(p["id"]),
        })

    for r in con.execute(
            """SELECT * FROM cx_protocolos
               WHERE atribuicao='RI' AND ri_protocolo_id IS NULL
                 AND COALESCE(origem,'') <> 'EOFICIO'
                 AND COALESCE(situacao,'') NOT IN ('ENTREGUE','CANCELADO')
               ORDER BY data_abertura, id"""):
        c = dict(r)
        pedidos.append({
            "tipo": "PROTOCOLO_GERAL",
            "etapa": "SEM_PRENOTACAO",
            "id": c["id"],
            "numero": c["numero"],
            "data": c.get("data_abertura"),
            "apresentante": c.get("interessado"),
            "telefone": c.get("telefone"),
            "email": c.get("email"),
            "titulo": c.get("assunto") or c.get("observacao"),
            "situacao_geral": c.get("situacao"),
            "orcamento": str(c.get("tipo") or "").upper() == "ORCAMENTO",
            "geral_id": c["id"],
            "geral_numero": c["numero"],
            "anotacao": anot_c.get(c["id"]),
        })

    _sugerir_pares(pedidos)

    contagem = {chave: 0 for chave, _, _ in ETAPAS}
    for item in pedidos:
        contagem[item["etapa"]] += 1
    return {"pedidos": pedidos, "contagem": contagem,
            "prenotacoes": len(ids)}
