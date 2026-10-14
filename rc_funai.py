"""A comunicação à FUNAI — art. 253, § 2º, e o prazo é «imediatamente».

    «§ 2° O oficial deverá comunicar **imediatamente** à FUNAI o assento de
     nascimento do indígena, para as providências necessárias ao **registro
     administrativo**.»

É O ÚNICO PRAZO DA CASA QUE NÃO SE CONTA EM DIAS
    Os outros oito destinos têm número — um dia útil, cinco dias, dia 8. Este
    diz «imediatamente», e prazo sem número é prazo que ninguém sente vencer.
    Por isso o módulo conta **os dias desde o assento** e mostra o número: não
    para afirmar um vencimento que a norma não deu, mas para que «imediatamente»
    deixe de ser palavra e passe a ser um número que cresce na tela.

POR QUE ISTO IMPORTA MAIS DO QUE O NÚMERO SUGERE
    São quatro casos no acervo — e **três são de 2026**. A comunicação existe
    para o **registro administrativo de nascimento de indígena (RANI)**, que é o
    documento com que a pessoa se apresenta à FUNAI a vida inteira. Não é
    estatística: é o papel de alguém.

O QUE SE MEDIU, E O QUE NÃO SE MEDIU
    Medido no acervo: `strRacaCor` traz «Indigena» em **4 dos 193** nascimentos,
    e está **em branco em 178**. Os quatro só aparecem porque alguém preencheu o
    campo — o que quer dizer que a lista deste módulo é do que o sistema **sabe**,
    e não necessariamente de tudo o que aconteceu.

    **NÃO MEDIDO, E POR ISSO NÃO SE PREENCHE SOZINHO: a etnia e a aldeia.** Nos
    quatro casos o sobrenome é «KRIKATI», e é tentador tirar dali a etnia — o
    § 1º até permite que o povo seja lançado como sobrenome. **Mas permite a
    pedido do declarante**, e não obriga: um indígena registrado sem esse
    sobrenome existiria e o programa o daria como de etnia nenhuma, ou pior,
    tiraria de um sobrenome comum uma etnia que não é. O acervo **não tem coluna
    de etnia nem de aldeia**. Quem as escreve é quem atendeu o declarante.
"""
from __future__ import annotations

import sqlite3
from typing import Any


class FunaiError(ValueError):
    """Erro de regra, com mensagem pronta para o balcao."""


ARTIGO = "art. 253, § 2º, do Código de Normas do TJMA"
PRAZO = "imediatamente"

# A norma NAO da numero. Este e o ponto a partir do qual a tela chama a atencao —
# **e ele e da casa, e nao da norma**, o que esta escrito na tela.
DIAS_PARA_CHAMAR_ATENCAO = 5

PARA_QUE_SERVE = (
    "registro administrativo de nascimento de indígena (RANI), que é o documento "
    "com que a pessoa se apresenta à FUNAI a vida inteira")

# O que o acervo escreve, e o que o balcao pode vir a escrever. **Compara-se sem
# acento e sem caixa**: o acervo guarda «Indigena», sem acento, e alguem vai
# digitar «Indígena».
COR_INDIGENA = ("INDIGENA", "INDÍGENA")

# O que o oficio precisa dizer e o sistema NAO SABE — pergunta-se, nao se deduz.
O_QUE_SE_PERGUNTA: tuple[dict, ...] = (
    {"campo": "etnia",
     "rotulo": "Povo, etnia, grupo, clã ou família indígena",
     "porque": "o § 1º permite que o povo seja lançado como sobrenome **a pedido "
               "do declarante** — permite, não obriga. Tirar a etnia do sobrenome "
               "acertaria os quatro casos desta casa e erraria o primeiro que "
               "chegasse sem ele"},
    {"campo": "aldeia",
     "rotulo": "Aldeia ou comunidade",
     "porque": "não há coluna de aldeia no acervo nem no assento; quem a sabe é "
               "quem atendeu o declarante"},
)


def _texto(v: Any) -> str:
    """O valor como texto, e vazio quando não há.

    NUNCA `str(v or "")`: ele come o `0` junto com o `None`. E nunca o padrão do
    `get`, que só vale quando a chave falta — numa linha de banco ela existe
    sempre.
    """
    if v is None:
        return ""
    return str(v).strip()


def _sem_acento(t: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", t)
                   if unicodedata.category(c) != "Mn")


def e_indigena(cor: Any) -> bool:
    """Se a cor/raça declarada é indígena. Só calcula.

    COMPARA SEM ACENTO E SEM CAIXA: o acervo guarda «Indigena» e o balcão vai
    digitar «Indígena». `UPPER` do SQLite é ASCII e não resolveria isto — é a
    mesma armadilha que deixou o CNIB sem achar ninguém por nome.
    """
    return _sem_acento(_texto(cor)).upper() in {_sem_acento(x)
                                                for x in COR_INDIGENA}


def dias_desde(data_ato: Any, *, hoje: str) -> int | None:
    """Quantos dias corridos desde o assento. Só calcula.

    **CORRIDOS, E NÃO ÚTEIS** — e a diferença não é descuido: os prazos em dias
    úteis desta casa (SIRC, art. 226, CRC) são assim porque **o artigo qualifica**.
    O art. 253, § 2º não qualifica coisa nenhuma: ele diz «imediatamente». Contar
    em dias úteis seria emprestar a esta obrigação uma folga que a norma não deu.

    Devolve `None` quando não dá para contar, e `None` **não vira zero**: zero
    diria «foi hoje», que é afirmação, e não saber é outra coisa.
    """
    from datetime import date

    def _data(bruto: str) -> date | None:
        bruto = _texto(bruto)[:10]
        if len(bruto) != 10 or bruto[4] != "-" or bruto[7] != "-":
            return None
        try:
            return date(int(bruto[:4]), int(bruto[5:7]), int(bruto[8:10]))
        except ValueError:
            return None

    de, ate = _data(data_ato), _data(hoje)
    if de is None or ate is None:
        return None
    return (ate - de).days


def pendentes(con: sqlite3.Connection, *, hoje: str = "",
              limite: int = 500) -> list[dict]:
    """Os nascimentos de indígena que a FUNAI ainda não recebeu. Só lê.

    **DO MAIS ANTIGO PARA O MAIS NOVO**, porque o prazo é «imediatamente»: o que
    está esperando há mais tempo é o que mais destoa da palavra da norma.

    A comparação da cor **não é feita no SQL**. `UPPER` do SQLite é ASCII, e
    «Indígena» com acento não casaria com «INDIGENA» — a mesma armadilha que
    deixou o CNIB sem achar ninguém por nome, e a busca do Protesto antes dela.
    A consulta traz os nascimentos e quem decide é `e_indigena`, em Python.
    """
    con.row_factory = sqlite3.Row
    linhas = con.execute(
        # NAO SE PEDE `a.folha`: LIVRO E FOLHA MORAM NO ATO, e nao no assento —
        # quem ocupa face do livro e o ATO. Eu pedi `a.folha` aqui e a consulta
        # estourou; quem me avisou foi o **painel**, que em vez de dizer «zero
        # pendencias» disse **por que** nao mediu. Era exatamente para isso que
        # ele nao engole erro — e ele se provou no primeiro dia.
        """SELECT a.id, a.nome, a.numero, a.livro_volume,
                  a.data_ato, a.data_fato, a.cor_raca, a.matricula
             FROM rc_assentos a
        LEFT JOIN rc_funai f ON f.assento_id = a.id
            WHERE a.especie = 'NASCIMENTO'
              AND COALESCE(a.situacao, 'ATIVO') <> 'CANCELADO'
              AND a.cor_raca IS NOT NULL AND TRIM(a.cor_raca) <> ''
              AND f.id IS NULL
         ORDER BY a.data_ato IS NULL, a.data_ato, a.id
            LIMIT ?""", (limite,)).fetchall()
    saida = []
    for linha in linhas:
        d = dict(linha)
        if not e_indigena(d.get("cor_raca")):
            continue
        d["dias"] = dias_desde(d.get("data_ato"), hoje=hoje) if hoje else None
        d["chama_atencao"] = bool(
            d["dias"] is not None and d["dias"] >= DIAS_PARA_CHAMAR_ATENCAO)
        saida.append(d)
    return saida


def quantas_pendentes(con: sqlite3.Connection) -> int:
    """Quantas esperam. Só lê — serve ao painel e ao aviso."""
    return len(pendentes(con))


def montar(con: sqlite3.Connection, assento_id: int, *, serventia: dict,
           etnia: str = "", aldeia: str = "") -> dict:
    """O ofício à FUNAI. Calcula, NÃO grava.

    **A ETNIA E A ALDEIA NÃO SE DEDUZEM DO NOME.** O § 1º permite que o povo seja
    lançado como sobrenome *a pedido do declarante*; quem não pediu não o tem no
    nome, e um sobrenome comum não é etnia. Vindo vazias, o ofício sai com o
    lugar marcado — que é honesto — em vez de sair com uma afirmação inventada
    sobre a origem de uma criança.
    """
    con.row_factory = sqlite3.Row
    a = con.execute("SELECT * FROM rc_assentos WHERE id = ?",
                    (assento_id,)).fetchone()
    if not a:
        raise FunaiError("Esse assento não existe.")
    a = dict(a)
    if _texto(a.get("especie")).upper() != "NASCIMENTO":
        raise FunaiError(
            "A comunicação do art. 253, § 2º é do assento de NASCIMENTO de "
            "indígena — este assento é de outra espécie.")
    if not e_indigena(a.get("cor_raca")):
        raise FunaiError(
            "Este assento não está declarado como de pessoa indígena. Se for, "
            "corrija a cor/raça do assento antes de comunicar — o ofício afirma "
            "à FUNAI uma coisa que tem de estar no livro.")

    # O LUGAR NO LIVRO SAI DA MESMA FUNCAO DA CERTIDAO, e nao de uma consulta
    # nova aqui. Duas consultas para a mesma pergunta divergem no primeiro
    # conserto — e a que ficasse velha poria o oficio a citar folha errada num
    # papel que vai a um orgao federal. Foi aqui que eu quase escrevi a segunda.
    import rc_certidao
    onde = rc_certidao.lugar_do_assento(con, assento_id)

    faltando = [x["rotulo"] for x, valor in
                ((O_QUE_SE_PERGUNTA[0], etnia), (O_QUE_SE_PERGUNTA[1], aldeia))
                if not _texto(valor)]

    corpo = (
        f"{_texto(serventia.get('nome')) or 'SERVENTIA'}\n"
        f"CNS {_texto(serventia.get('cns'))}\n\n"
        "À FUNDAÇÃO NACIONAL DOS POVOS INDÍGENAS — FUNAI\n\n"
        "Comunicação de assento de nascimento de pessoa indígena, na forma do "
        "art. 253, § 2º, do Código de Normas da Corregedoria Geral da Justiça "
        "do Estado do Maranhão, para as providências necessárias ao registro "
        "administrativo.\n\n"
        f"Nome: {_texto(a.get('nome')) or '[COMPLETAR: nome]'}\n"
        f"Data do nascimento: {_texto(a.get('data_fato')) or '[COMPLETAR]'}\n"
        f"Data do assento: {_texto(a.get('data_ato')) or '[COMPLETAR]'}\n"
        f"Livro: {_texto(onde.get('livro')) or _texto(a.get('livro_volume')) or 'A'}   "
        f"Folha: {_texto(onde.get('folha')) or '[COMPLETAR: folha]'}   "
        f"Termo: {_texto(onde.get('termo')) or _texto(a.get('numero')) or '[COMPLETAR]'}\n"
        f"Matrícula: {_texto(a.get('matricula')) or '[COMPLETAR: matrícula]'}\n"
        f"Povo, etnia, grupo, clã ou família indígena: "
        f"{_texto(etnia) or '[COMPLETAR: a etnia, que o sistema não deduz]'}\n"
        f"Aldeia ou comunidade: "
        f"{_texto(aldeia) or '[COMPLETAR: a aldeia, que o sistema não guarda]'}\n")
    return {"assento_id": assento_id, "teor": corpo, "faltando": faltando,
            "nome": a.get("nome")}


def registrar_envio(con: sqlite3.Connection, assento_id: int, *, agora: str,
                    por: str, teor: str, canal: str = "", protocolo: str = "",
                    etnia: str = "", aldeia: str = "") -> int:
    """Registra que a comunicação saiu. GRAVA — chame dentro de `transaction()`.

    **AVISO SEM SAÍDA É AVISO QUE FICA PARA SEMPRE**, e na terceira vez ninguém
    lê mais. É esta função que tira o nascimento da lista.

    **O TEOR CONGELA**, como o da certidão, o do edital e o das comunicações do
    art. 226: é o papel que a serventia afirma ter mandado, e numa correição é
    ele que se mostra. Remontá-lo depois faria o que se mostra discordar do que
    foi enviado.
    """
    if not _texto(teor):
        raise FunaiError("Não dá para registrar comunicação sem o ofício.")
    ja = con.execute("SELECT id FROM rc_funai WHERE assento_id = ?",
                     (assento_id,)).fetchone()
    if ja:
        raise FunaiError(
            "Este nascimento já foi comunicado à FUNAI. Se precisar comunicar "
            "de novo, o caminho é um ofício novo, e não apagar o que saiu.")
    import hashlib
    cur = con.execute(
        """INSERT INTO rc_funai (assento_id, situacao, teor, hash_teor,
               etnia, aldeia, enviada_em, canal, protocolo, criado_em,
               criado_por)
           VALUES (?,'ENVIADA',?,?,?,?,?,?,?,?,?)""",
        (assento_id, teor,
         hashlib.sha256(teor.encode("utf-8")).hexdigest(),
         _texto(etnia), _texto(aldeia), agora, _texto(canal),
         _texto(protocolo), agora, por))
    return int(cur.lastrowid)


def dispensar(con: sqlite3.Connection, assento_id: int, *, motivo: str,
              agora: str, por: str) -> int:
    """Dispensa a comunicação, COM MOTIVO ESCRITO. GRAVA.

    Dispensar é decisão do oficial; ignorar não é. E o que se escreveu **fica**,
    como no usucapião e nas anotações: engano se conserta à vista.
    """
    if len(_texto(motivo)) < 10:
        raise FunaiError(
            "Escreva por que esta comunicação não é devida — quem ler daqui a "
            "cinco anos precisa saber, e é isso que uma correição pergunta.")
    ja = con.execute("SELECT id FROM rc_funai WHERE assento_id = ?",
                     (assento_id,)).fetchone()
    if ja:
        raise FunaiError("Este nascimento já saiu da lista.")
    cur = con.execute(
        """INSERT INTO rc_funai (assento_id, situacao, motivo, criado_em,
               criado_por, resolvida_por)
           VALUES (?,'DISPENSADA',?,?,?,?)""",
        (assento_id, _texto(motivo), agora, por, por))
    return int(cur.lastrowid)


def historico(con: sqlite3.Connection, limite: int = 200) -> list[dict]:
    """O que já saiu e o que foi dispensado. Só lê."""
    con.row_factory = sqlite3.Row
    return [dict(x) for x in con.execute(
        """SELECT f.*, a.nome, a.numero, a.data_ato
             FROM rc_funai f
             JOIN rc_assentos a ON a.id = f.assento_id
         ORDER BY f.criado_em DESC LIMIT ?""", (limite,)).fetchall()]
