"""Retificação, restauração e suprimento do Registro Civil — o processo.

A REGRA QUE MANDA NO DESENHO
    **Não se decide sem a consulta à CRC.** O art. 348, § 2º a torna *condição
    de validade da decisão*, e por isso `decidir()` recusa quando ela não existe
    — com a frase pronta para o balcão, e não com um aviso que se pode ignorar.

    É a mesma forma da análise por conferir no usucapião: lá, `decidir()` recusa
    fechar o processo apoiado em análise que ninguém leu.

E A QUE MANDA NO DINHEIRO
    **«Erro imputável à serventia» não é caixinha de marcar.** O art. 353 a
    transforma em gratuidade, comunicação ao **FERC e ao FERJ** — os dois — e
    cobrança contra **o delegatário titular da época**, uma pessoa nomeada.
    Marcá-la exige fundamento escrito, e marcar **abre as duas comunicações**.

O QUE ESTE MÓDULO NÃO FAZ
    **Não decide se o erro é da serventia** — é juízo do oficial, com efeito
    sobre o patrimônio de terceiro. **Não consulta a CRC** — ele registra o que
    o oficial consultou; a consulta é integração que este sistema ainda não tem.
    **Não lavra o ato** — quem lavra é a tela do RCPN, que tem o livro, o selo e
    os emolumentos.
"""
from __future__ import annotations

import sqlite3
from typing import Any

import ri_schema
import rr_tjma as NORMA


class RetificacaoRcpnError(ValueError):
    """Erro de regra, com mensagem pronta para o balcao."""


# AS FASES, na ordem em que acontecem. **Nao se pula**: cada uma protege
# alguem — o interessado que precisa do termo assinado, o titular do assento
# duplicado que a CRC revela, o delegatario de ontem que o art. 353 cobra.
FASES: tuple[dict, ...] = (
    {"chave": "PROTOCOLO", "nome": "Protocolo",
     "o_que": "o requerimento entrou, e ainda pode faltar documento"},
    {"chave": "INSTRUCAO", "nome": "Instrução",
     "o_que": "o pedido está devidamente instruído — **é daqui que o prazo "
              "conta**"},
    {"chave": "CONSULTA_CRC", "nome": "Consulta à CRC",
     "o_que": "art. 348, § 2º — condição de validade da decisão"},
    {"chave": "DECISAO", "nome": "Decisão",
     "o_que": "fundamentada, em até 10 dias úteis da instrução"},
    {"chave": "ATO", "nome": "Ato",
     "o_que": "lançado no **livro corrente**, com remissões recíprocas"},
)

CHAVES_DAS_FASES = tuple(f["chave"] for f in FASES)

DECISOES = ("DEFERIDO", "INDEFERIDO", "JUDICIAL")

FUNDOS = tuple(x["sigla"] for x in NORMA.ERRO_DA_SERVENTIA["comunicar"])


def _texto(v: Any) -> str:
    """O valor como texto, e vazio quando não há. Nunca `str(v or "")`."""
    if v is None:
        return ""
    return str(v).strip()


def _exigir(con: sqlite3.Connection, processo_id: int) -> dict:
    con.row_factory = sqlite3.Row
    linha = con.execute("SELECT * FROM rr_processos WHERE id = ?",
                        (int(processo_id),)).fetchone()
    if not linha:
        raise RetificacaoRcpnError("Esse processo não existe.")
    return dict(linha)


def proximo_numero(con: sqlite3.Connection, ano: int) -> int:
    """O próximo número do exercício. Só lê.

    A NUMERAÇÃO É POR ANO, como a das certidões — e o `UNIQUE(numero, ano)`
    guarda o resto.
    """
    linha = con.execute(
        "SELECT MAX(CAST(numero AS INTEGER)) FROM rr_processos WHERE ano = ?",
        (int(ano),)).fetchone()
    return int(linha[0] or 0) + 1


def abrir(con: sqlite3.Connection, *, instituto: str, forma: str,
          requerente_nome: str, o_que_se_pede: str, ano: int, agora: str,
          por: str, assento_id: int | None = None,
          assento_descricao: str = "", requerente_documento: str = "",
          assinado_por: str = "", termo_verbal: str = "") -> int:
    """Abre o processo. GRAVA — chame dentro de `transaction()`.

    **O PEDIDO VERBAL EXIGE O TERMO NA HORA.** O art. 348, § 1º, III manda
    reduzi-lo a termo *imediatamente*, colhendo a assinatura do declarante — e
    sem o termo o pedido não existe no papel. Quem chega ao balcão dizendo «meu
    nome está errado na certidão» está formulando um requerimento, e mandá-lo
    voltar com petição é negar o que a norma permite.

    **O ASSENTO É OPCIONAL, e isso é o suprimento.** Ali o assento não existe —
    é o que se supre. Exigi-lo travaria justamente o instituto para o qual ele
    não existe.
    """
    NORMA.instituto(instituto)
    NORMA.forma(forma)
    if not _texto(requerente_nome):
        raise RetificacaoRcpnError("Diga quem está pedindo.")
    if not _texto(o_que_se_pede):
        raise RetificacaoRcpnError(
            "Escreva o que se pede — é o que a decisão vai responder.")
    if forma == "VERBAL" and not _texto(termo_verbal):
        raise RetificacaoRcpnError(
            "O pedido verbal deve ser imediatamente reduzido a termo, com a "
            "assinatura do declarante (art. 348, § 1º, III). Escreva o termo "
            "antes de abrir o processo.")
    if instituto != "SUPRIMENTO" and not assento_id \
            and not _texto(assento_descricao):
        raise RetificacaoRcpnError(
            "Diga de que assento se trata — pelo registro no sistema ou "
            "descrevendo onde ele está no livro de papel. Só no suprimento o "
            "assento ainda não existe.")

    numero = proximo_numero(con, ano)
    cur = con.execute(
        """INSERT INTO rr_processos (numero, ano, instituto, forma, fase,
               situacao, assento_id, assento_descricao, requerente_nome,
               requerente_documento, assinado_por, o_que_se_pede,
               termo_verbal, termo_verbal_em, protocolado_em, criado_em,
               criado_por, atualizado_em)
           VALUES (?,?,?,?,'PROTOCOLO','EM_ANDAMENTO',?,?,?,?,?,?,?,?,?,?,?,?)""",
        (str(numero), int(ano), instituto, forma, assento_id,
         _texto(assento_descricao), _texto(requerente_nome),
         _texto(requerente_documento), _texto(assinado_por),
         _texto(o_que_se_pede), _texto(termo_verbal),
         agora if _texto(termo_verbal) else None,
         agora, agora, por, agora))
    processo_id = int(cur.lastrowid)
    _andar(con, processo_id, f"Processo aberto — {instituto.lower()}", agora,
           por)
    return processo_id


def _andar(con: sqlite3.Connection, processo_id: int, o_que: str, quando: str,
           quem: str) -> None:
    con.execute(
        """INSERT INTO rr_andamento (processo_id, quando, o_que, quem)
           VALUES (?,?,?,?)""", (int(processo_id), quando, o_que, quem))


def instruir(con: sqlite3.Connection, processo_id: int, *, agora: str,
             por: str) -> dict:
    """Marca o pedido como devidamente instruído. GRAVA.

    **É DAQUI QUE O PRAZO CONTA**, e não do dia em que o interessado apareceu —
    o § 3º diz «contados do protocolo do requerimento **devidamente
    instruído**». Contar da chegada poria o oficial em atraso por falta de
    documento que o requerente ainda não trouxe.

    O prazo sai de `ri_schema.soma_dias_uteis`, o contador de dias úteis da
    casa — porque o § 3º **qualifica**: «10 (dez) dias úteis».
    """
    processo = _exigir(con, processo_id)
    if _texto(processo["instruido_em"]):
        raise RetificacaoRcpnError(
            "Este pedido já está marcado como instruído. O prazo dos 10 dias "
            "úteis já está correndo.")
    # `soma_dias_uteis` RECEBE E DEVOLVE `date`, e nao texto — conferido na
    # assinatura dela, e nao suposto: passar `"2026-08-20"` estoura com
    # «can only concatenate str». O banco guarda texto, e a conversao mora aqui,
    # num lugar so.
    from datetime import date
    bruto = agora[:10]
    if len(bruto) != 10 or bruto[4] != "-" or bruto[7] != "-":
        raise RetificacaoRcpnError(
            "Não deu para ler a data de hoje para contar o prazo.")
    inicio = date(int(bruto[:4]), int(bruto[5:7]), int(bruto[8:10]))
    prazo = ri_schema.soma_dias_uteis(
        inicio, NORMA.PRAZO_DECISAO_DIAS_UTEIS).isoformat()
    con.execute(
        """UPDATE rr_processos SET instruido_em=?, prazo_ate=?, fase='INSTRUCAO',
               atualizado_em=? WHERE id=?""",
        (agora, prazo, agora, int(processo_id)))
    _andar(con, processo_id,
           f"Pedido devidamente instruído — o prazo vai até {prazo}", agora,
           por)
    return {"prazo_ate": prazo}


def registrar_consulta_crc(con: sqlite3.Connection, processo_id: int, *,
                           o_que_se_procurou: str, resultado: str,
                           achou_duplicidade: bool = False,
                           achou_ato_em_outra_serventia: bool = False,
                           protocolo: str = "", agora: str,
                           por: str) -> int:
    """Registra a consulta obrigatória à CRC. GRAVA.

    **ESTE SISTEMA NÃO CONSULTA A CRC** — ele registra o que o oficial
    consultou. A consulta é integração que ainda não existe, e um botão que
    dissesse «consultado» sem consultar seria pior que não ter botão: ele
    responderia, e responderia errado.

    **E não se registra consulta sem dizer o que se achou.** «ok» não responde à
    pergunta que a correição faz, e é o que um campo solto receberia.
    """
    _exigir(con, processo_id)
    if not _texto(o_que_se_procurou):
        raise RetificacaoRcpnError(
            "Diga o que foi procurado na CRC — nome, data, filiação. É isso que "
            "permite conferir a consulta depois.")
    if not _texto(resultado):
        raise RetificacaoRcpnError(
            "Escreva o que a CRC devolveu. «Consultado» não responde à pergunta "
            "que a correição faz.")
    cur = con.execute(
        """INSERT INTO rr_consultas_crc (processo_id, consultada_em,
               o_que_se_procurou, achou_duplicidade,
               achou_ato_em_outra_serventia, resultado, protocolo, criado_em,
               criado_por)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (int(processo_id), agora, _texto(o_que_se_procurou),
         1 if achou_duplicidade else 0,
         1 if achou_ato_em_outra_serventia else 0, _texto(resultado),
         _texto(protocolo), agora, por))
    con.execute("UPDATE rr_processos SET fase='CONSULTA_CRC', atualizado_em=? "
                "WHERE id=?", (agora, int(processo_id)))
    aviso = ""
    if achou_duplicidade:
        aviso = (" — DUPLICIDADE: o art. 365 manda comunicar imediatamente ao "
                 "juiz corregedor, com bloqueio cautelar do registro mais "
                 "recente")
    _andar(con, processo_id, f"Consulta à CRC registrada{aviso}", agora, por)
    return int(cur.lastrowid)


def consultas(con: sqlite3.Connection, processo_id: int) -> list[dict]:
    """As consultas à CRC daquele processo. Só lê."""
    con.row_factory = sqlite3.Row
    return [dict(x) for x in con.execute(
        "SELECT * FROM rr_consultas_crc WHERE processo_id=? ORDER BY id",
        (int(processo_id),))]


def o_que_falta_para_decidir(con: sqlite3.Connection,
                             processo_id: int) -> list[str]:
    """O que impede a decisão. Só lê — e a tela mostra antes do botão.

    **A CONSULTA À CRC É A PRIMEIRA DA LISTA**, porque é a única que a norma
    chama de obrigatória.
    """
    processo = _exigir(con, processo_id)
    faltas = []
    if not consultas(con, processo_id):
        faltas.append(
            "a consulta obrigatória à CRC (art. 348, § 2º) — sem ela a decisão "
            "sai sem o que a norma exige")
    if not _texto(processo["instruido_em"]):
        faltas.append(
            "marcar o pedido como devidamente instruído — é daí que o prazo "
            "conta")
    if processo["forma"] == "VERBAL" and not _texto(processo["termo_verbal"]):
        faltas.append(
            "o termo do pedido verbal, com a assinatura do declarante "
            "(art. 348, § 1º, III)")
    return faltas


def decidir(con: sqlite3.Connection, processo_id: int, *, decisao: str,
            fundamento: str, agora: str, por: str,
            erro_da_serventia: bool = False,
            erro_fundamento: str = "") -> dict:
    """A decisão fundamentada do oficial. GRAVA.

    **RECUSA SEM A CONSULTA À CRC.** O art. 348, § 2º a torna condição de
    validade: decidir sem consultar é decidir sem o que a norma exige. Não é um
    aviso que se pode ignorar — é recusa, como a do usucapião sobre análise que
    ninguém leu.

    **E RECUSA SEM FUNDAMENTO**, porque o § 3º diz «de forma fundamentada».
    Decisão sem fundamento é a que se desfaz depois.

    **MARCAR «ERRO DA SERVENTIA» ABRE AS DUAS COMUNICAÇÕES** do art. 353 — FERC
    e FERJ —, e exige fundamento próprio: a marca gera gratuidade e uma cobrança
    contra **o delegatário titular da época**, que é uma pessoa nomeada.
    """
    processo = _exigir(con, processo_id)
    if decisao not in DECISOES:
        raise RetificacaoRcpnError(
            f"«{decisao}» não é uma decisão: deferido, indeferido ou remessa ao "
            "juiz corregedor.")
    if len(_texto(fundamento)) < 20:
        raise RetificacaoRcpnError(
            "A decisão é fundamentada por exigência do art. 348, § 3º. "
            "Escreva o porquê — decisão sem fundamento é a que se desfaz "
            "depois.")
    faltas = o_que_falta_para_decidir(con, processo_id)
    if faltas:
        raise RetificacaoRcpnError(
            "Ainda não dá para decidir. Falta: " + "; ".join(faltas) + ".")
    if _texto(processo["decidido_em"]):
        raise RetificacaoRcpnError(
            "Este processo já foi decidido. Rever decisão é ato novo, e não "
            "reescrita da que saiu.")
    if erro_da_serventia and len(_texto(erro_fundamento)) < 20:
        raise RetificacaoRcpnError(
            "Dizer que o erro é imputável à serventia torna o ato gratuito, "
            "manda comunicar ao FERC e ao FERJ e faz o FERJ cobrar do "
            "delegatário titular da época. Escreva o fundamento — isso é juízo "
            "seu, e não uma caixinha.")

    con.execute(
        """UPDATE rr_processos SET decidido_em=?, decisao=?, fundamento=?,
               decidido_por=?, erro_da_serventia=?, erro_fundamento=?,
               fase='DECISAO', situacao=?, atualizado_em=? WHERE id=?""",
        (agora, decisao, _texto(fundamento), por,
         1 if erro_da_serventia else 0, _texto(erro_fundamento),
         "EM_ANDAMENTO" if decisao == "DEFERIDO" else decisao, agora,
         int(processo_id)))
    _andar(con, processo_id, f"Decisão: {decisao.lower()}", agora, por)

    abertas = []
    if erro_da_serventia:
        for fundo in FUNDOS:
            con.execute(
                """INSERT OR IGNORE INTO rr_comunicacoes_353 (processo_id,
                       fundo, situacao, criado_em, criado_por)
                   VALUES (?,?,'PENDENTE',?,?)""",
                (int(processo_id), fundo, agora, por))
            abertas.append(fundo)
        _andar(con, processo_id,
               "Erro imputável à serventia — ato gratuito, e comunicação "
               "devida ao FERC e ao FERJ (art. 353)", agora, por)
    return {"decisao": decisao, "comunicacoes_abertas": abertas}


def registrar_comunicacao_353(con: sqlite3.Connection, processo_id: int, *,
                              fundo: str, teor: str, agora: str, por: str,
                              canal: str = "", protocolo: str = "") -> None:
    """Registra que a comunicação ao FERC ou ao FERJ saiu. GRAVA.

    O TEOR CONGELA, com sha256 — é o papel que a serventia afirma ter mandado, e
    dele depende o ressarcimento.
    """
    import hashlib
    if fundo not in FUNDOS:
        raise RetificacaoRcpnError(
            f"«{fundo}» não é um dos fundos do art. 353: FERC e FERJ.")
    if not _texto(teor):
        raise RetificacaoRcpnError("Não dá para registrar sem o ofício.")
    atualizado = con.execute(
        """UPDATE rr_comunicacoes_353
              SET situacao='ENVIADA', teor=?, hash_teor=?, enviada_em=?,
                  canal=?, protocolo=?
            WHERE processo_id=? AND fundo=? AND situacao<>'ENVIADA'""",
        (teor, hashlib.sha256(teor.encode("utf-8")).hexdigest(), agora,
         _texto(canal), _texto(protocolo), int(processo_id), fundo)).rowcount
    # `rowcount` E RESPOSTA; «deu certo» E SUPOSICAO. O recibo da DOI dizia
    # «registrado» com zero linhas mudadas, e o escrevente ia embora achando que
    # a obrigacao estava cumprida.
    if not atualizado:
        raise RetificacaoRcpnError(
            f"Não há comunicação pendente ao {fundo} neste processo — ou ela já "
            "foi registrada, ou o erro não foi imputado à serventia.")
    _andar(con, processo_id, f"Comunicação ao {fundo} registrada", agora, por)


def comunicacoes_353(con: sqlite3.Connection, processo_id: int) -> list[dict]:
    """As comunicações do art. 353 daquele processo. Só lê."""
    con.row_factory = sqlite3.Row
    return [dict(x) for x in con.execute(
        "SELECT * FROM rr_comunicacoes_353 WHERE processo_id=? ORDER BY fundo",
        (int(processo_id),))]


def registrar_ato(con: sqlite3.Connection, processo_id: int, *, ato_id: int,
                  agora: str, por: str, assento_novo_id: int | None = None
                  ) -> None:
    """Amarra o processo ao ato que saiu dele. GRAVA.

    **CONFERE QUE O ATO EXISTE.** Sem isso batia na chave estrangeira e virava
    HTTP 500 no fim de um processo de dias — foi o defeito que o teste de tela do
    usucapião pegou, e a lição está registrada.

    **E O ATO VAI NO LIVRO CORRENTE** (art. 348, § 4º), com remissões recíprocas
    ao assento original. Quem lavra é a tela do RCPN; aqui só se amarra.
    """
    processo = _exigir(con, processo_id)
    if processo["decisao"] != "DEFERIDO":
        raise RetificacaoRcpnError(
            "Só o pedido deferido produz ato. Este está "
            f"«{_texto(processo['decisao']).lower() or 'sem decisão'}».")
    existe = con.execute("SELECT id FROM rc_atos WHERE id=?",
                         (int(ato_id),)).fetchone()
    if not existe:
        raise RetificacaoRcpnError(
            "Esse ato não existe. Lavre o ato na ficha do assento e depois "
            "amarre-o a este processo.")
    con.execute(
        """UPDATE rr_processos SET ato_id=?, assento_novo_id=?, fase='ATO',
               situacao='CONCLUIDO', atualizado_em=? WHERE id=?""",
        (int(ato_id), assento_novo_id, agora, int(processo_id)))
    _andar(con, processo_id, "Ato lançado e amarrado ao processo", agora, por)


def proximos_passos(con: sqlite3.Connection, processo_id: int) -> list[str]:
    """O que fazer agora. Só lê.

    NUM RITO DE DIAS, «E AGORA?» É A PERGUNTA QUE MAIS SE REPETE — e ela merece
    resposta na tela, e não na cabeça de quem lembra. É a forma do usucapião.
    """
    processo = _exigir(con, processo_id)
    passos: list[str] = []
    if processo["situacao"] == "CONCLUIDO":
        return ["Processo concluído — o ato já está amarrado."]
    if processo["forma"] == "VERBAL" and not _texto(processo["termo_verbal"]):
        passos.append("Reduzir o pedido verbal a termo, com a assinatura do "
                      "declarante (art. 348, § 1º, III).")
    if not _texto(processo["instruido_em"]):
        passos.append("Marcar o pedido como devidamente instruído — o prazo de "
                      "10 dias úteis conta daí.")
    if not consultas(con, processo_id):
        passos.append("Registrar a consulta obrigatória à CRC (art. 348, § 2º) "
                      "— sem ela não se decide.")
    if not _texto(processo["decidido_em"]):
        if not passos:
            passos.append("Decidir, de forma fundamentada.")
    elif processo["decisao"] == "DEFERIDO" and not processo["ato_id"]:
        passos.append("Lavrar o ato no **livro corrente**, com remissões "
                      "recíprocas ao assento original (art. 348, § 4º), e "
                      "amarrá-lo a este processo.")
    pendentes = [x["fundo"] for x in comunicacoes_353(con, processo_id)
                 if x["situacao"] != "ENVIADA"]
    if pendentes:
        passos.append("Comunicar ao " + " e ao ".join(pendentes) +
                      " (art. 353), para o ressarcimento.")
    return passos or ["Nada pendente neste momento."]


def em_andamento(con: sqlite3.Connection, limite: int = 300) -> list[dict]:
    """Os processos abertos, do prazo mais apertado para o mais folgado. Só lê."""
    con.row_factory = sqlite3.Row
    return [dict(x) for x in con.execute(
        """SELECT * FROM rr_processos
            WHERE COALESCE(situacao,'') NOT IN ('CONCLUIDO','INDEFERIDO',
                                                'JUDICIAL')
         ORDER BY prazo_ate IS NULL, prazo_ate LIMIT ?""", (limite,))]


def fora_do_prazo(con: sqlite3.Connection, *, hoje: str) -> list[dict]:
    """Os que passaram dos 10 dias úteis sem decisão. Só lê."""
    return [x for x in em_andamento(con)
            if _texto(x["prazo_ate"]) and x["prazo_ate"] < hoje
            and not _texto(x["decidido_em"])]


def quantas_pendentes(con: sqlite3.Connection) -> int:
    """Quantos processos esperam. Só lê — serve ao painel."""
    return len(em_andamento(con))
