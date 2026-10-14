"""A MINUTA DO ATO DO RI — o ato escrito que ainda não foi lavrado.

    «aquela av 4, 5 e 6 não podem ficar como atos prontos, precisam ficar
     como atos para serem revistos e lavrados» — o oficial, 15/09/2026

O QUE FEZ ISTO NASCER
    A importação das minutas em `.docx` (a pasta «minutas para finalizar»)
    entrou lavrando: os AV-04, AV-05 e AV-06 da matrícula 3.110 nasceram
    **como ato definitivo** — tomaram número, entraram na corrente de hash e
    encerraram a ficha —, e ficaram **sem selo**. O que o oficial esperava era
    o contrário: texto pronto esperando revisão, e a lavratura só depois, pela
    tela de sempre, com selo e custas.

A REGRA DA CASA QUE ISTO RESPEITA
    «O rascunho do ato do RI não mora em `ri_atos`»: ali todo ato é definitivo
    ao entrar, tomando o número e entrando na corrente. Um ato «meio lavrado»
    naquela tabela é um ato que existe e não devia — ou ocupa número alheio,
    ou quebra a corrente ao ser apagado.

O QUE ESTE MÓDULO **NÃO** FAZ, e é o que o separa de `ri_atos`
    Não numera, não entra na corrente de hash, não sela e não cobra. Nada
    disso acontece antes de a minuta virar ato — e quem a transforma é a
    **mesma rota de lavrar de sempre**, com os campos já preenchidos. Duas
    portas para lavrar seriam duas versões da regra que numera e sela, e elas
    divergiriam no primeiro conserto.

    Por isso aqui não há função que lavre: há teste que varre os nomes
    públicos procurando `lavrar`, `selar`, `numerar` e `cobrar`.
"""
from __future__ import annotations

import re
import sqlite3

A_REVISAR = "A_REVISAR"
LAVRADA = "LAVRADA"
DESCARTADA = "DESCARTADA"

SITUACOES = {
    A_REVISAR: "A revisar e lavrar",
    LAVRADA: "Lavrada",
    DESCARTADA: "Descartada",
}

TIPOS = {"R": "R — registro", "AV": "AV — averbação"}

# De onde a minuta veio. `DESFEITO_DE_ATO` é a que voltou de um ato que não
# devia ter sido lavrado — e `origem_chave` guarda qual era, porque aquele
# número já esteve ocupado e quem conferir depois precisa saber disso.
IMPORTACAO = "IMPORTACAO"
DESFEITO_DE_ATO = "DESFEITO_DE_ATO"
MANUAL = "MANUAL"

MINIMO_DO_TEOR = 20


class MinutaError(ValueError):
    """Impedimento de regra, com mensagem pronta para o balcão."""


def _texto(v) -> str:
    return str(v or "").strip()


# Marcação de modelo Jinja que ninguém resolveu: `{{ rotulo }}`, `{% if %}`.
_MARCA_DE_MODELO = re.compile(r"\{\{[^{}]{0,80}\}\}|\{%[^%]{0,80}%\}|\{\{|\{%")


def marcador_de_modelo(teor) -> str | None:
    """O primeiro marcador de modelo cru no teor, ou None. Só LÊ.

    NASCEU DE 11 MINUTAS DA CNIB, 06/10/2026: o teor saiu de
    `ri_cnib.teor_preparado` com `{{ rotulo }}` e `{{ protocolo_frase }}` por
    resolver, e nada no caminho recusou — nem a minuta ao ser gravada, nem a
    rota de lavrar, que grava o teor como vem. O `[COLCHETE]` é campo que o
    escrevente preenche; o `{{ }}` não é de ninguém: é o motor de modelo que
    não rodou. Por isso este recusa, e o colchete não.
    """
    achado = _MARCA_DE_MODELO.search(str(teor or ""))
    return achado.group(0) if achado else None


def _recusa_marcador_de_modelo(teor: str) -> None:
    marca = marcador_de_modelo(teor)
    if marca:
        raise MinutaError(
            f"O teor traz «{marca}», que é marcação de modelo não preenchida — "
            f"no livro sairia assim, literalmente. Troque pelo texto do ato "
            f"(o rótulo AV-N/matrícula, a frase do protocolo) antes de gravar.")


def criar(con: sqlite3.Connection, *, matricula_id: int, tipo: str, teor: str,
          agora: str, numero_pretendido=None, data_pretendida=None,
          natureza_titulo=None, protocolo=None, prenotacao=None,
          modelo_codigo=None, origem: str = MANUAL, origem_chave=None,
          observacao=None, usuario=None) -> int:
    """Guarda uma minuta. ESCREVE. Devolve o id.

    O TEOR É O QUE ELA É. Minuta sem texto não é minuta: é uma linha vazia
    esperando alguém lembrar do que ela era.
    """
    tipo = _texto(tipo).upper()
    if tipo not in TIPOS:
        raise MinutaError(
            f"«{tipo or '(em branco)'}» não é tipo de ato. São dois: R (registro) "
            f"e AV (averbação).")
    teor = _texto(teor)
    if len(teor) < MINIMO_DO_TEOR:
        raise MinutaError(
            "O teor da minuta não pode ficar em branco — é ele que vai ser "
            "revisado e lavrado.")
    _recusa_marcador_de_modelo(teor)
    numero = None
    if _texto(numero_pretendido):
        try:
            numero = int(numero_pretendido)
        except (TypeError, ValueError):
            raise MinutaError(
                f"O número pretendido «{numero_pretendido}» não é um número.")
        if numero <= 0:
            raise MinutaError("O número pretendido tem de ser maior que zero.")

    cur = con.execute(
        """INSERT INTO ri_minutas
           (matricula_id, tipo, numero_pretendido, data_pretendida, teor,
            natureza_titulo, protocolo, prenotacao, modelo_codigo,
            origem, origem_chave, observacao, situacao, criado_em, criado_por)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (int(matricula_id), tipo, numero, _texto(data_pretendida) or None, teor,
         _texto(natureza_titulo) or None, _texto(protocolo) or None,
         _texto(prenotacao) or None, _texto(modelo_codigo) or None,
         _texto(origem) or MANUAL, _texto(origem_chave) or None,
         _texto(observacao) or None, A_REVISAR, agora, usuario))
    return int(cur.lastrowid)


def atualizar(con: sqlite3.Connection, minuta_id: int, *, teor: str,
              agora: str, tipo=None, numero_pretendido=None,
              data_pretendida=None, natureza_titulo=None, protocolo=None,
              prenotacao=None, partes=None, usuario=None) -> int | None:
    """Guarda a revisão da minuta SEM lavrar. ESCREVE.

    POR QUE ISTO EXISTE: revisar pode levar mais de uma sentada. Sem esta
    função, a correção de uma vírgula só existia dentro do formulário de
    lavrar — quem saísse da tela perdia o trabalho e teria de redigitar, ou
    lavraria com o erro dentro. E ato lavrado não se edita: o conserto seria
    uma averbação.

    E ELA NÃO LAVRA NADA. A minuta continua `A_REVISAR`, sem número tomado,
    fora da corrente de hash e sem selo — quem a transforma em ato é a tela de
    lavrar de sempre.

    NÃO SE REVISA O QUE JÁ VIROU ATO. Depois de lavrada, a minuta é a
    procedência do que está no livro: mudar o texto dela faria a prova
    discordar do ato que saiu dela.

    AS PARTES VÃO JUNTO, E ELAS FALTAVAM AQUI — relato #86, 18/09/2026. A
    ficha manda as partes no MESMO formulário (é o `formaction` que separa
    «guardar» de «lavrar»), e esta função gravava teor, número, natureza,
    protocolo e prenotação — e deixava os blocos de parte de fora. Quem
    acrescentasse a quarta parte e clicasse em **Guardar revisão** perdia o que
    digitou: a minuta reabria com as partes antigas, e o defeito é o mesmo que
    fez a AV-05 da 3.110 voltar sem dono em 15/09 — só que pela porta do meio.

    `partes=None` QUER DIZER «A TELA NÃO MEXEU NISTO», e não «esvazie» — a
    mesma régua dos outros campos aqui. Quem chama sem partes (o `tools/` da
    importação, um teste de teor) não apaga as que estavam guardadas; quem
    manda a lista manda a lista inteira, e ela substitui o que havia, que é o
    que `guardar_partes` já faz.

    Devolve quantas partes ficaram gravadas quando a lista foi mandada, e
    `None` quando ninguém mexeu nelas.
    """
    m = uma(con, minuta_id)
    if not m:
        raise MinutaError("Minuta não encontrada.")
    if m["situacao"] != A_REVISAR:
        raise MinutaError(
            "Esta minuta já saiu da fila de revisão — o que está no livro não "
            "se corrige mudando a minuta, e sim por averbação.")

    teor = _texto(teor)
    if len(teor) < MINIMO_DO_TEOR:
        raise MinutaError(
            "O teor da minuta não pode ficar em branco — é ele que vai ser "
            "revisado e lavrado.")
    _recusa_marcador_de_modelo(teor)

    tipo_novo = _texto(tipo).upper() or m["tipo"]
    if tipo_novo not in TIPOS:
        raise MinutaError(
            f"«{tipo_novo}» não é tipo de ato. São dois: R (registro) e "
            f"AV (averbação).")

    numero = m["numero_pretendido"]
    if numero_pretendido is not None:
        bruto = _texto(numero_pretendido)
        if not bruto:
            numero = None
        else:
            try:
                numero = int(bruto)
            except (TypeError, ValueError):
                raise MinutaError(
                    f"O número pretendido «{numero_pretendido}» não é um número.")
            if numero <= 0:
                raise MinutaError(
                    "O número pretendido tem de ser maior que zero.")

    # O QUE NÃO FOI MANDADO NÃO SE APAGA. `None` aqui quer dizer «a tela não
    # mexeu neste campo», e não «esvazie». Tratar os dois como a mesma coisa
    # faria uma revisão do teor limpar a natureza do título sem ninguém pedir.
    def _ou_o_que_havia(novo, chave):
        return m[chave] if novo is None else (_texto(novo) or None)

    con.execute(
        """UPDATE ri_minutas SET teor=?, tipo=?, numero_pretendido=?,
               data_pretendida=?, natureza_titulo=?, protocolo=?, prenotacao=?,
               atualizado_em=?, atualizado_por=? WHERE id=?""",
        (teor, tipo_novo, numero,
         _ou_o_que_havia(data_pretendida, "data_pretendida"),
         _ou_o_que_havia(natureza_titulo, "natureza_titulo"),
         _ou_o_que_havia(protocolo, "protocolo"),
         _ou_o_que_havia(prenotacao, "prenotacao"),
         agora, usuario, int(minuta_id)))

    # AS PARTES DA REVISÃO, E ELAS VÊM DEPOIS DO RESTO DE PROPÓSITO: no mesmo
    # `with` da rota, um erro de tipo de ato ou de número derruba tudo — e a
    # lista de partes não pode ter sido trocada por uma revisão que recusou.
    if partes is not None:
        return guardar_partes(con, int(minuta_id), partes)
    return None


def listar(con: sqlite3.Connection, matricula_id: int, *,
           situacao: str | None = A_REVISAR) -> list[dict]:
    """As minutas daquela ficha. Só LÊ."""
    sql = "SELECT * FROM ri_minutas WHERE matricula_id=?"
    args: list = [int(matricula_id)]
    if situacao:
        sql += " AND situacao=?"
        args.append(situacao)
    sql += " ORDER BY COALESCE(numero_pretendido, 999999), id"
    return [dict(r) for r in con.execute(sql, args)]


def uma(con: sqlite3.Connection, minuta_id: int) -> dict | None:
    """Uma minuta pelo id. Só LÊ."""
    r = con.execute("SELECT * FROM ri_minutas WHERE id=?",
                    (int(minuta_id),)).fetchone()
    return dict(r) if r else None


def quantas_a_revisar(con: sqlite3.Connection,
                      matricula_id: int | None = None) -> int:
    """Quantas esperam revisão. Só LÊ — para a ficha e para a lista do dia."""
    sql = "SELECT COUNT(*) FROM ri_minutas WHERE situacao=?"
    args: list = [A_REVISAR]
    if matricula_id is not None:
        sql += " AND matricula_id=?"
        args.append(int(matricula_id))
    return int(con.execute(sql, args).fetchone()[0])


def marcar_lavrada(con: sqlite3.Connection, minuta_id: int, *, ato_id: int,
                   agora: str, usuario=None) -> None:
    """Amarra a minuta ao ato que saiu dela. ESCREVE.

    A MINUTA NÃO SE APAGA AO VIRAR ATO. Ela é a prova de que aquele texto
    existia antes, e de onde ele veio — e é por ela que se responde «este ato
    saiu de qual minuta?». Apagar seria perder a procedência justamente no
    momento em que ela passa a valer.
    """
    con.execute(
        """UPDATE ri_minutas SET situacao=?, ato_id=?, atualizado_em=?,
               atualizado_por=? WHERE id=?""",
        (LAVRADA, int(ato_id), agora, usuario, int(minuta_id)))


def descartar(con: sqlite3.Connection, minuta_id: int, *, motivo: str,
              agora: str, usuario=None) -> None:
    """Tira a minuta da fila sem lavrar. ESCREVE.

    EXIGE MOTIVO ESCRITO, como a dispensa do usucapião e a reabertura da
    matrícula: descartar é decisão, e decisão sem motivo escrito é decisão que
    ninguém confere depois. E **descartada não some**: fica na tabela com o
    motivo, porque a pergunta que aparece meses depois é «e aquela averbação
    que estava para sair?».
    """
    motivo = _texto(motivo)
    if len(motivo) < 10:
        raise MinutaError(
            "Escreva o motivo do descarte com pelo menos dez letras — «não "
            "serve» não explica nada a quem ler depois.")
    m = uma(con, minuta_id)
    if not m:
        raise MinutaError("Minuta não encontrada.")
    if m["situacao"] == LAVRADA:
        raise MinutaError(
            "Esta minuta já virou ato — o que se desfaz agora é o ato, por "
            "averbação, e não a minuta.")
    con.execute(
        """UPDATE ri_minutas SET situacao=?, observacao=?, atualizado_em=?,
               atualizado_por=? WHERE id=?""",
        (DESCARTADA,
         ((m["observacao"] + "\n") if m["observacao"] else "")
         + f"DESCARTADA: {motivo}",
         agora, usuario, int(minuta_id)))


# ----------------------------------------------------------- as partes


def guardar_partes(con, minuta_id: int, partes) -> int:
    """Guarda as partes que vao junto com esta minuta. ESCREVE.

    NASCEU DE UM ESTRAGO MEDIDO em 15/09/2026: a AV-05 da 3.110 voltou a
    minuta sem as duas partes dela — porque nao havia onde guarda-las — e o
    selo recusou o ato relavrado dizendo «Os nomes das partes devem ser
    informados». O texto sobrevivia a ida e volta; quem era dono, nao.

    SUBSTITUI O QUE ESTAVA LA, e nao acrescenta: guardar a revisao e dizer
    «e isto», e nao «mais isto». Duas listas somadas dariam nomes repetidos
    num registro publico.

    Devolve quantas entraram.
    """
    con.execute("DELETE FROM ri_minuta_partes WHERE minuta_id=?",
                (int(minuta_id),))
    entraram = 0
    for ordem, p in enumerate(partes or []):
        nome = str((p or {}).get("nome") or "").strip()
        if not nome:
            # PARTE SEM NOME NAO E PARTE. A tela manda linhas em branco
            # quando o operador nao preenche todas, e guardar uma linha
            # vazia faria a proxima lavratura oferecer um nome que nao
            # existe.
            continue
        con.execute(
            """INSERT INTO ri_minuta_partes
               (minuta_id, nome, documento_tipo, documento_numero,
                qualificacao, papel, ordem)
               VALUES (?,?,?,?,?,?,?)""",
            (int(minuta_id), nome,
             (p.get("documento_tipo") or None),
             (str(p.get("documento_numero") or "").strip() or None),
             (str(p.get("qualificacao") or "").strip() or None),
             (str(p.get("papel") or "").strip() or None), ordem))
        entraram += 1
    return entraram


def partes(con, minuta_id: int) -> list[dict]:
    """As partes desta minuta, na ordem em que foram guardadas. So LE."""
    return [dict(r) for r in con.execute(
        """SELECT nome, documento_tipo, documento_numero, qualificacao, papel
             FROM ri_minuta_partes WHERE minuta_id=? ORDER BY ordem, id""",
        (int(minuta_id),))]


# ------------------------------------- o ato que volta porque o selo nao saiu


class SeloNaoSaiu(MinutaError):
    """O ato foi suspenso e voltou a ser minuta. Nao e defeito: e o caminho."""


def voltar_do_ato(con, ato_id: int, *, agora: str, por: str | None = None,
                  motivo: str = "") -> dict:
    """Desfaz um ato recem-lavrado e o guarda como minuta. ESCREVE.

    ORDEM DO OFICIAL EM 16/09/2026: «selo recusado suspende ato (fica salvo
    como minuta para lavrar de novo)».

    ISTO INVERTE UMA REGRA ESCRITA DESDE AGOSTO — «selo recusado nao derruba
    ato que ja existe» — e a inversao e dele, com os fatos na mao. O que a
    regra antiga produziu esta medido: os AV-04, AV-05 e AV-06 da 3.110
    nasceram lavrados e sem selo, entraram na corrente de hash, um deles
    encerrou a ficha, e desfazer aquilo custou tres ferramentas e dois dias.

      **O QUE MUDA NA PRATICA, e ele sabe:** um ato so passa a existir depois
      de o selo sair. Com o aparelho fora do ar, o balcao nao lavra — o
      trabalho fica guardado na minuta, com o teor e as partes, e se lavra
      quando ele voltar. Nada se perde; o que nao acontece e o ato meio
      pronto no livro.

    O QUE ELA GUARDA, e e o que faltava: teor, natureza, protocolo,
    prenotacao, o numero pretendido — **e as PARTES**. Sem elas o ato
    relavrado nasce sem dono, o envelope recusa («Os nomes das partes devem
    ser informados») e o circulo nunca fecha. Foi exatamente o que aconteceu
    com a AV-05 em 15/09, e `ri_minuta_partes` nasceu disso.

    AS TRES RECUSAS, e cada uma protege alguma coisa
      1. **Ato com selo nao volta.** Selo pago amarrado a um ato que deixa de
         existir e selo orfao, e minuta nao tem onde guarda-lo. Se o selo
         saiu, nao ha o que suspender.
      2. **So a CAUDA da corrente de hash.** `hash_anterior` de cada ato e o
         `hash_ato` do anterior: tirar um do meio deixaria o seguinte
         apontando para um hash que nao existe mais.
      3. **Ato com dinheiro no caixa nao volta.** Dinheiro que entrou sai por
         estorno, que deixa rastro.

    E ELA NAO DEVOLVE A UNIDADE DO PROTOCOLO, de proposito: quem sabe fazer
    isso e `caixa_protocolo`, e o `ato_id` sozinho nao diz quantas unidades
    aquele ato gastou. Quem chama devolve, e a rota o faz — o mesmo desenho
    da ferramenta que desfaz em lote.

    Devolve `{"minuta_id", "partes", "reaproveitou"}`.
    """
    a = con.execute("SELECT * FROM ri_atos WHERE id=?", (int(ato_id),)).fetchone()
    if not a:
        raise MinutaError("O ato não existe mais — nada a suspender.")
    rotulo = f"{a['tipo']}-{int(a['numero']):02d}"

    if str(a["selo_texto"] or "").strip():
        raise MinutaError(
            f"O ato {rotulo} tem selo ({a['selo_texto'][:28]}…) e por isso "
            f"não se suspende: selo pago amarrado a ato que deixa de existir "
            f"é selo órfão.")
    depois = con.execute(
        "SELECT COUNT(*) FROM ri_atos WHERE matricula_id=? AND id>?",
        (a["matricula_id"], int(ato_id))).fetchone()[0]
    if depois:
        raise MinutaError(
            f"O ato {rotulo} não é o último da ficha — há {depois} ato(s) "
            f"depois dele. Tirar um do meio deixaria o seguinte apontando "
            f"para um hash que não existe mais.")
    no_caixa = con.execute(
        """SELECT COUNT(*) FROM cx_lancamentos
            WHERE origem='ATO' AND origem_chave LIKE ?""",
        (f"ri_atos:{int(ato_id)}:%",)).fetchone()[0]
    if no_caixa:
        raise MinutaError(
            f"O ato {rotulo} tem {no_caixa} lançamento(s) no caixa. Dinheiro "
            f"que entrou sai por estorno, que deixa rastro — e não por aqui.")

    # A MINUTA DE ONDE ELE SAIU VOLTA PARA A FILA, em vez de nascer outra:
    # duas minutas para o mesmo ato na mesma ficha, e quem a abrisse nao
    # saberia qual revisar.
    de_onde = con.execute(
        "SELECT id FROM ri_minutas WHERE ato_id=? ORDER BY id LIMIT 1",
        (int(ato_id),)).fetchone()
    nota = (f"Suspensa em {agora[:10]}: o ato {rotulo} foi lavrado e o selo "
            f"não saiu" + (f" — {motivo}" if motivo else "") +
            ". O texto e as partes ficaram guardados para lavrar de novo.")

    if de_onde:
        minuta_id = int(de_onde["id"])
        con.execute(
            """UPDATE ri_minutas
                  SET situacao=?, ato_id=NULL, teor=?, natureza_titulo=?,
                      protocolo=?, prenotacao=?, numero_pretendido=?,
                      data_pretendida=?, atualizado_em=?, atualizado_por=?,
                      observacao=COALESCE(observacao || char(10), '') || ?
                WHERE id=?""",
            (A_REVISAR, a["teor"], a["natureza_titulo"], a["protocolo"],
             a["prenotacao"], a["numero"], a["data_ato"], agora, por, nota,
             minuta_id))
        reaproveitou = True
    else:
        cur = con.execute(
            """INSERT INTO ri_minutas
               (matricula_id, tipo, numero_pretendido, data_pretendida, teor,
                natureza_titulo, protocolo, prenotacao, modelo_codigo,
                origem, origem_chave, observacao, situacao, criado_em,
                criado_por)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (a["matricula_id"], a["tipo"], a["numero"], a["data_ato"],
             a["teor"], a["natureza_titulo"], a["protocolo"], a["prenotacao"],
             a["modelo_codigo"], DESFEITO_DE_ATO,
             f"ri_atos:{int(ato_id)} {rotulo}", nota, A_REVISAR, agora, por))
        minuta_id = int(cur.lastrowid)
        reaproveitou = False

    # AS PARTES VAO JUNTO — e sem isto o ato relavrado nasce sem dono.
    quantas = guardar_partes(con, minuta_id, [
        dict(r) for r in con.execute(
            """SELECT nome, documento_tipo, documento_numero, qualificacao,
                      papel FROM ri_partes WHERE ato_id=? ORDER BY id""",
            (int(ato_id),))])

    con.execute("DELETE FROM ri_partes WHERE ato_id=?", (int(ato_id),))
    # A NOTA DE REVISAO FICA NA FICHA: `ato_id` NULL e nota da matricula.
    con.execute("UPDATE ri_revisoes SET ato_id=NULL WHERE ato_id=?",
                (int(ato_id),))
    con.execute("DELETE FROM ri_atos WHERE id=?", (int(ato_id),))
    return {"minuta_id": minuta_id, "partes": quantas,
            "reaproveitou": reaproveitou, "rotulo": rotulo}
