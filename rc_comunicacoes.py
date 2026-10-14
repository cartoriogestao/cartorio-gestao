"""As comunicações MENSAIS de óbito — art. 226 do Código de Normas do TJMA.

    «o cartório está precisando do sistema pronto e amadurecido para o quanto
     antes» — o oficial, 29/08/2026

A OBRIGAÇÃO, NA LETRA DO ARTIGO

    «Art. 226. O oficial de registro civil deverá comunicar, **até o 5º (quinto)
     dia útil do mês subsequente**, os registros de óbitos lavrados no mês
     anterior, aos seguintes órgãos:
       I  - juiz(íza) eleitoral, em relação aos **maiores de 16 anos**, para
            cancelamento das inscrições de alistamento eleitoral, **sob as penas
            do art. 293 do Código Eleitoral**;
       II - Ministério da Economia, nos mesmos termos do art. 52, § 3º, da Lei
            nº 6.015/1973;
       III- Receita Federal, nos termos do art. 80, parágrafo único, da mesma
            Lei;
       IV - Instituto de Identificação do Maranhão, nos mesmos termos.»

    E o § 2º: «A omissão ao cumprimento do disposto no § 1º sujeita o(a)
    delegatário(a) à responsabilização prevista nos termos da Lei.»

E HÁ UMA QUINTA, QUE NÃO ESTÁ NO CÓDIGO DE NORMAS
    A **Junta de Serviço Militar**, pela Lei 4.375/1964: «Os oficiais do
    Registro Civil deverão remeter, **mensalmente**, às respectivas
    Circunscrições de Recrutamento, relações, em modelos regulamentares, dos
    **óbitos de nacionais do sexo masculino, de dezessete a quarenta e cinco
    anos de idade, inclusive**, registrados no mês anterior.»

    Ela não aparece no Código de Normas do TJMA, e por isso quase se perdeu:
    quem lê só o Código não a encontra.

É O QUARTO PRAZO DA CASA QUE NINGUÉM DE FORA COBRA
    Depois do SIGEF (30 dias), das anotações (5 dias) e da relação militar. Só
    que este **se repete todo mês** e vale para **cinco destinos** — e a norma
    diz, com todas as letras, que a omissão responsabiliza o delegatário.

    Medido em 29/08/2026: o acervo tem óbitos em **cinco meses de 2026** —
    abril (7), maio (2), junho (4), julho (13) e agosto (2). São **28 óbitos** e
    até **25 remessas** possivelmente pendentes.

O QUE ESTE MÓDULO NÃO FAZ
    **Não envia.** Cada órgão recebe por um caminho próprio — ofício, sistema,
    malote —, e nenhum deles está medido. Ele **monta a relação, guarda o que
    saiu e cobra o prazo**; quem manda é a pessoa, e registra o protocolo.

    É a mesma decisão do edital do usucapião: até haver integração medida, o
    sistema faz o que se pode fazer com verdade.
"""
from __future__ import annotations

import sqlite3
from typing import Any


class ComunicacaoError(ValueError):
    """Erro de regra, com mensagem pronta para o balcao."""


# ------------------------------------------------------------- os cinco destinos
#
# CADA UM TEM UM FILTRO PROPRIO, e os filtros sao da norma — nao meus.
#
# O eleitoral alcanca os **maiores de 16 anos**, que e a idade em que se pode
# alistar; a Junta Militar, os **homens de 17 a 45**, que e a faixa da
# conscricao. Os outros tres alcancam todos.
#
# Mandar a lista inteira para o juiz eleitoral seria mandar o nome de criancas
# para cancelar alistamento que nunca existiu; mandar so os maiores de 16 para a
# Receita seria esconder dela metade dos obitos.

TODOS = "TODOS"
MAIORES_DE_16 = "MAIORES_DE_16"
HOMENS_17_A_45 = "HOMENS_17_A_45"

DESTINOS: tuple[dict, ...] = (
    {"chave": "ELEITORAL",
     "nome": "Juiz(íza) Eleitoral",
     "artigo": "art. 226, I, do Código de Normas do TJMA",
     "quem": MAIORES_DE_16,
     "porque": "para cancelamento das inscrições de alistamento eleitoral",
     "aviso": "sob as penas do art. 293 do Código Eleitoral",
     "onde": "O meio oficial é o INFODIP, do TSE (Resolução Conjunta CNJ/TSE "
             "nº 6/2020) — o cadastro se faz no TRE."},
    {"chave": "ECONOMIA",
     "nome": "Ministério da Economia",
     "artigo": "art. 226, II — art. 52, § 3º, da Lei 6.015/1973",
     "quem": TODOS,
     "porque": "para os fins do art. 52, § 3º, da Lei de Registros Públicos",
     "aviso": "",
     "onde": ""},
    {"chave": "RECEITA",
     "nome": "Receita Federal do Brasil",
     "artigo": "art. 226, III — art. 80, parágrafo único, da Lei 6.015/1973",
     "quem": TODOS,
     "porque": "para os fins do art. 80, parágrafo único, da Lei de Registros "
               "Públicos",
     "aviso": "",
     "onde": ""},
    {"chave": "IDENTIFICACAO",
     "nome": "Instituto de Identificação do Maranhão",
     "artigo": "art. 226, IV — art. 80, parágrafo único, da Lei 6.015/1973",
     "quem": TODOS,
     "porque": "para os fins do art. 80, parágrafo único, da Lei de Registros "
               "Públicos",
     "aviso": "",
     "onde": ""},
    {"chave": "JUNTA_MILITAR",
     "nome": "Circunscrição de Recrutamento (Junta de Serviço Militar)",
     "artigo": "Lei 4.375/1964 — Lei do Serviço Militar",
     "quem": HOMENS_17_A_45,
     "porque": "relação dos óbitos de nacionais do sexo masculino, de dezessete "
               "a quarenta e cinco anos de idade, inclusive",
     "aviso": "",
     "onde": "NÃO está no Código de Normas do TJMA — quem lê só o Código não a "
             "encontra."},
)

POR_CHAVE = {d["chave"]: d for d in DESTINOS}

# Art. 226, caput. **DIAS UTEIS**, e desta vez o artigo qualifica — ao contrario
# do prazo das anotacoes (cinco dias, sem qualificar) e do SIGEF (trinta).
#
# Nao se conta aqui: quem conta dia util e `ri_schema.soma_dias_uteis`, que
# conhece os feriados desta comarca e ja serve a prenotacao, o edital do
# usucapiao e a retificacao. Uma segunda contagem divergiria.
# **O QUE VEIO DO ACERVO NAO SE COMUNICA.** A comunicacao de um obito de 2009 era
# devida em 2009, pelo E-Oficio — e nao em 2026, porque alguem o digitou. Ver
# `meses_com_obito`.
ORIGEM_QUE_NAO_SE_COMUNICA = "EOFICIO"

PRAZO_DIAS_UTEIS = 5
ARTIGO_DO_PRAZO = "art. 226, caput"

# Art. 226, § 1o, III — e ele nao e detalhe: e o que se mostra numa correicao.
ARQUIVO_MINIMO_ANOS = 2
ARTIGO_DO_ARQUIVO = "art. 226, § 1º, III"

TEXTO_DO_ARQUIVO = (
    "A comunicação de óbito deverá ser arquivada em meio físico ou virtual na "
    "serventia, organizada por períodos mensais, pelo prazo mínimo de dois "
    "anos. Após o decurso do prazo legal, as comunicações somente poderão ser "
    "incineradas ou descartadas após comunicação ao(à) juiz(íza) da vara de "
    "registros públicos.")

TEXTO_DA_OMISSAO = (
    "A omissão ao cumprimento sujeita o(a) delegatário(a) à responsabilização "
    "prevista nos termos da Lei (art. 226, § 2º).")


def _texto(v: Any) -> str:
    return str(v or "").strip()


def destino(chave: str) -> dict:
    d = POR_CHAVE.get(_texto(chave).upper())
    if not d:
        raise ComunicacaoError(
            f"«{chave}» não é um destino da comunicação mensal. Os cinco são: "
            + ", ".join(f"{x['chave']} ({x['nome']})" for x in DESTINOS) + ".")
    return dict(d)


def alcanca(d: dict, obito: dict) -> bool:
    """Se este óbito entra na relação deste destino. Só calcula.

    O FILTRO E DA NORMA, e por isso mora junto do destino e nao numa consulta
    escrita a mao em cada lugar.
    """
    quem = d.get("quem", TODOS)
    if quem == TODOS:
        return True
    idade = obito.get("idade")
    try:
        idade = int(idade)
    except (TypeError, ValueError):
        # SEM IDADE NAO SE FILTRA, E ELE ENTRA. Deixar de fora quem nao tem
        # idade seria esconder um obito do orgao por falta de um campo — e o
        # § 2o responsabiliza quem omite. Ele entra, e a lista o marca.
        return True
    if quem == MAIORES_DE_16:
        return idade >= 16
    if quem == HOMENS_17_A_45:
        sexo = _texto(obito.get("sexo")).upper()[:1]
        return sexo == "M" and 17 <= idade <= 45
    return True


def obitos_do_mes(con: sqlite3.Connection, competencia: str) -> list[dict]:
    """Os óbitos lavrados no mês, com o que a relação precisa. Só lê.

    `competencia` é `AAAA-MM`. A comparação é por FAIXA de texto, e não por
    recorte no SQL: função sobre a coluna não usa o índice, e o teto de
    portabilidade recusa recorte de texto no SQL — módulo novo entra com zero.
    """
    comp = _texto(competencia)
    if len(comp) != 7 or comp[4] != "-":
        raise ComunicacaoError(
            "A competência é o mês, no formato AAAA-MM — por exemplo 2026-07.")
    con.row_factory = sqlite3.Row
    return [dict(r) for r in con.execute(
        """SELECT a.id, a.numero, a.nome, a.data_ato, a.data_fato, a.matricula,
                  a.numero_do, a.livro_volume,
                  p.sexo, p.documento_numero, p.data_nascimento
             FROM rc_assentos a
             LEFT JOIN rc_pessoas p
                    ON p.assento_id = a.id AND p.papel = 'FALECIDO'
            WHERE a.especie = 'OBITO'
              AND COALESCE(a.data_ato, '') >= ?
              AND COALESCE(a.data_ato, '') < ?
         ORDER BY a.data_ato, a.id""",
        (comp + "-01", comp + "-32"))]


def relacao(con: sqlite3.Connection, competencia: str, chave: str) -> dict:
    """A relação de um destino, num mês. Só lê.

    Devolve **quem entra e quem ficou de fora, com o motivo** — porque a lista
    que só mostra quem entra deixa quem confere sem saber se faltou alguém.
    """
    d = destino(chave)
    todos = obitos_do_mes(con, competencia)
    dentro, fora = [], []
    for o in todos:
        o = dict(o)
        o["idade"] = _idade_no_obito(o)
        (dentro if alcanca(d, o) else fora).append(o)
    return {"destino": d, "competencia": competencia,
            "entram": dentro, "ficam_de_fora": fora,
            "quantos": len(dentro), "quantos_no_mes": len(todos)}


def _idade_no_obito(o: dict) -> int | None:
    """A idade no dia do óbito, dos dois campos que existem. Só calcula.

    **DESCONTA O ANIVERSARIO**, e isso e conserto de um defeito medido do
    E-Oficio: ele fazia `ano do obito − ano do nascimento` e mandava ao IBGE a
    idade **um ano a mais** para quem morreu antes do aniversario — em 3 dos 11
    obitos comparaveis.
    """
    nasc, morte = _texto(o.get("data_nascimento")), _texto(o.get("data_fato"))
    if len(nasc) < 10 or len(morte) < 10:
        return None
    try:
        anos = int(morte[:4]) - int(nasc[:4])
        if morte[5:10] < nasc[5:10]:
            anos -= 1
        return anos if 0 <= anos < 130 else None
    except ValueError:
        return None


# --------------------------------------------------------------- as situações

PENDENTE = "PENDENTE"
ENVIADA = "ENVIADA"
DISPENSADA = "DISPENSADA"

SITUACOES = (PENDENTE, ENVIADA, DISPENSADA)

NOME_DA_SITUACAO = {
    PENDENTE: "Pendente",
    ENVIADA: "Enviada, com protocolo",
    DISPENSADA: "Dispensada, com motivo escrito",
}

MINIMO_DO_MOTIVO = 10


def _exigir(con: sqlite3.Connection, comunicacao_id: int) -> dict:
    con.row_factory = sqlite3.Row
    r = con.execute("SELECT * FROM rc_comunicacoes WHERE id = ?",
                    (comunicacao_id,)).fetchone()
    if not r:
        raise ComunicacaoError("Não achei essa comunicação.")
    return dict(r)


def declarar_mes(con: sqlite3.Connection, competencia: str, *, agora: str,
                 prazo_ate: str = "", usuario: str | None = None) -> list[int]:
    """Abre as cinco comunicações de um mês. ESCREVE.

    ABRE AS CINCO, MESMO AS VAZIAS — e isso é deliberado. Um mês sem óbito
    algum continua devendo a resposta a cada órgão: o próprio SIRC tem
    «declaração de inexistência de movimento» por web service, e o art. 225,
    § 3º manda comunicar o fato. **Comunicação que não se abre por estar vazia
    é comunicação que ninguém lembra de mandar.**

    REPETÍVEL: `UNIQUE(destino, competencia)` e `INSERT OR IGNORE`. Rodar duas
    vezes o mesmo mês não duplica a obrigação.

    `prazo_ate` VEM PRONTO, de quem conta dia útil — `ri_schema.soma_dias_uteis`,
    que conhece os feriados desta comarca. Contar aqui seria uma segunda
    contagem, e num prazo divergir por um dia é perder o prazo.
    """
    comp = _texto(competencia)
    if len(comp) != 7 or comp[4] != "-":
        raise ComunicacaoError(
            "A competência é o mês, no formato AAAA-MM — por exemplo 2026-07.")
    novas = []
    for d in DESTINOS:
        cur = con.execute(
            """INSERT OR IGNORE INTO rc_comunicacoes (destino, competencia,
                   situacao, prazo_ate, criado_em, criado_por)
               VALUES (?,?,?,?,?,?)""",
            (d["chave"], comp, PENDENTE, _texto(prazo_ate) or None, agora,
             usuario))
        if cur.rowcount:
            novas.append(int(cur.lastrowid))
    return novas


def montar(con: sqlite3.Connection, comunicacao_id: int, *,
           serventia: dict) -> dict:
    """O texto da relação, montado. Só calcula — NÃO grava.

    Ver como fica é barato; **congelar acontece uma vez**, quando ela sai — e o
    art. 226, § 1º, III manda guardá-la por dois anos, organizada por mês.
    """
    c = _exigir(con, comunicacao_id)
    r = relacao(con, c["competencia"], c["destino"])
    d = r["destino"]

    linhas = []
    for i, o in enumerate(r["entram"], 1):
        pedaco = [f"{i}. {o.get('nome') or '(sem nome)'}"]
        if o.get("numero"):
            pedaco.append(f"termo nº {o['numero']}")
        if o.get("livro_volume"):
            pedaco.append(f"livro {o['livro_volume']}")
        if o.get("data_fato"):
            pedaco.append(f"falecido em {o['data_fato']}")
        if o.get("idade") is not None:
            pedaco.append(f"{o['idade']} anos")
        else:
            # SEM IDADE ELE ENTRA, E A LISTA DIZ ISSO. Omitir a falta faria o
            # orgao receber a linha sem saber que o dado nao existe.
            pedaco.append("idade não informada no assento")
        if o.get("documento_numero"):
            pedaco.append(f"CPF {o['documento_numero']}")
        if o.get("numero_do"):
            pedaco.append(f"DO nº {o['numero_do']}")
        if o.get("matricula"):
            pedaco.append(f"matrícula {o['matricula']}")
        linhas.append(", ".join(pedaco) + ".")

    corpo = "\n".join(linhas) if linhas else (
        "Nada consta: nenhum óbito nesta competência alcança este destino.")

    aviso = f" — {d['aviso']}" if d.get("aviso") else ""
    texto = (
        f"{serventia.get('nome', '')}\n"
        f"{serventia.get('cidade', '')}/{serventia.get('uf', '')}\n\n"
        f"COMUNICAÇÃO MENSAL DE ÓBITOS — {c['competencia']}\n"
        f"Destinatário: {d['nome']}\n"
        f"Fundamento: {d['artigo']}\n\n"
        f"Comunicamos, {d['porque']}, os óbitos lavrados nesta serventia na "
        f"competência {c['competencia']}{aviso}:\n\n"
        f"{corpo}\n\n"
        f"Total: {r['quantos']} de {r['quantos_no_mes']} óbito(s) lavrados no "
        f"mês.\n\n"
        f"{serventia.get('cidade', '')}/{serventia.get('uf', '')}.\n\n"
        f"_________________________________\n"
        f"{serventia.get('registrador', '')}\n"
        f"{serventia.get('titulo', '')}\n")
    return {"texto": texto, **r}


def registrar_envio(con: sqlite3.Connection, comunicacao_id: int, *,
                    canal: str, protocolo: str, quando: str, agora: str,
                    serventia: dict, usuario: str | None = None) -> dict:
    """Congela o teor e registra que a comunicação saiu. ESCREVE.

    **O TEOR FICA GUARDADO INTEIRO**, e não só o nome do arquivo: o art. 226,
    § 1º, III manda arquivá-la por **dois anos, organizada por períodos
    mensais**, e é ela que se mostra numa correição. Guardar só a marca de
    «enviada» seria dizer que se cumpriu sem poder mostrar o quê.
    """
    import hashlib

    c = _exigir(con, comunicacao_id)
    if c["situacao"] != PENDENTE:
        raise ComunicacaoError(
            "Esta comunicação já está como "
            f"{NOME_DA_SITUACAO.get(c['situacao'], c['situacao'])}.")
    if not _texto(protocolo):
        raise ComunicacaoError(
            "Guarde o protocolo ou o comprovante. Sem ele não há como mostrar, "
            "numa correição, que a comunicação saiu — e o art. 226, § 2º "
            "responsabiliza quem omite.")

    montado = montar(con, comunicacao_id, serventia=serventia)
    texto = montado["texto"]
    con.execute(
        """UPDATE rc_comunicacoes SET situacao = ?, teor = ?, quantos = ?,
               hash_teor = ?, enviada_em = ?, canal = ?, protocolo = ?,
               resolvida_por = ? WHERE id = ?""",
        (ENVIADA, texto, montado["quantos"],
         hashlib.sha256(texto.encode("utf-8")).hexdigest(), quando,
         _texto(canal) or None, _texto(protocolo), usuario, comunicacao_id))
    return {"situacao": ENVIADA, "quantos": montado["quantos"]}


def dispensar(con: sqlite3.Connection, comunicacao_id: int, *, motivo: str,
              agora: str, usuario: str | None = None) -> dict:
    """Dispensa a comunicação de um mês, com motivo escrito. ESCREVE.

    DISPENSAR É DECISÃO DO OFICIAL; IGNORAR NÃO É. E o art. 226, § 2º
    responsabiliza a omissão — então o que não sai tem de dizer por quê.
    """
    c = _exigir(con, comunicacao_id)
    if c["situacao"] != PENDENTE:
        raise ComunicacaoError(
            "Esta comunicação já está como "
            f"{NOME_DA_SITUACAO.get(c['situacao'], c['situacao'])}.")
    if len(_texto(motivo)) < MINIMO_DO_MOTIVO:
        raise ComunicacaoError(
            "Para dispensar, escreva o motivo — e lembre que o art. 226, § 2º "
            "responsabiliza a omissão. "
            f"Ao menos {MINIMO_DO_MOTIVO} letras.")
    con.execute(
        """UPDATE rc_comunicacoes SET situacao = ?, motivo = ?,
               resolvida_por = ? WHERE id = ?""",
        (DISPENSADA, _texto(motivo), usuario, comunicacao_id))
    return {"situacao": DISPENSADA}


def pendentes(con: sqlite3.Connection, limite: int = 500) -> list[dict]:
    """O que a casa deve, da competência mais antiga para a mais nova.

    DO MAIS ANTIGO PARA O MAIS NOVO, como as anotações — e pelo mesmo motivo:
    aqui o que importa é o prazo, e quem está há mais tempo esperando é quem
    está mais perto de estourá-lo.
    """
    con.row_factory = sqlite3.Row
    return [dict(r) for r in con.execute(
        """SELECT * FROM rc_comunicacoes WHERE situacao = ?
         ORDER BY competencia, destino LIMIT ?""", (PENDENTE, limite))]


def quantas_pendentes(con: sqlite3.Connection) -> int:
    con.row_factory = sqlite3.Row
    return int(con.execute(
        "SELECT COUNT(*) FROM rc_comunicacoes WHERE situacao = ?",
        (PENDENTE,)).fetchone()[0])


def meses_com_obito(con: sqlite3.Connection) -> list[dict]:
    """As competências que têm óbito lavrado **por esta casa**. Só lê.

    O MÊS SAI EM PYTHON, e não com recorte de texto no SQL: o teto de
    portabilidade recusa recorte no SQL, e módulo novo entra com zero.

    **E O QUE VEIO DO ACERVO NÃO ENTRA.** Achado no ensaio contra a produção em
    30/08/2026: sem este filtro a lista devolvia **oito meses**, o mais antigo de
    **março de 2009** — e a comunicação daquele óbito era devida em 2009, pelo
    E-Ofício. Digitar hoje não faz nascer obrigação de hoje, e oito meses vezes
    cinco destinos dariam **quarenta comunicações «em atraso»** que ninguém tem
    como fazer.

    > Era o mesmo defeito do SIRC, no mesmo dia e por baixo da mesma pergunta —
    > e por isso nasceu `tests/test_o_acervo_nao_vira_atraso.py`, que varre a
    > classe inteira em vez de consertar um módulo por vez.
    """
    con.row_factory = sqlite3.Row
    contas: dict[str, int] = {}
    for r in con.execute(
            """SELECT data_ato AS d FROM rc_assentos
                WHERE especie = 'OBITO' AND COALESCE(data_ato, '') <> ''
                  AND COALESCE(origem, '') <> ?""",
            (ORIGEM_QUE_NAO_SE_COMUNICA,)):
        comp = str(r["d"])[:7]
        contas[comp] = contas.get(comp, 0) + 1
    return [{"competencia": k, "obitos": v} for k, v in sorted(contas.items())]


def meses_sem_comunicacao(con: sqlite3.Connection) -> list[dict]:
    """As competências com óbito que ainda não têm as cinco comunicações.

    É A LISTA QUE DIZ O TAMANHO DO ATRASO. Medido no acervo em 29/08/2026:
    cinco meses de 2026 com óbito — abril, maio, junho, julho e agosto —, e
    cinco destinos cada, dão até 25 remessas.
    """
    con.row_factory = sqlite3.Row
    faltando = []
    for m in meses_com_obito(con):
        quantas = int(con.execute(
            "SELECT COUNT(*) FROM rc_comunicacoes WHERE competencia = ?",
            (m["competencia"],)).fetchone()[0])
        if quantas < len(DESTINOS):
            faltando.append({**m, "abertas": quantas,
                             "faltam": len(DESTINOS) - quantas})
    return faltando
