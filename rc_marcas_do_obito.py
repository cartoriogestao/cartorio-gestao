"""As quatro marcas do assento de óbito — e o que cada uma OBRIGA.

DE ONDE VEIO ISTO
    Do print do «Registro de Óbito» do E-Ofício, lido em 30/08/2026. Na aba
    «Dados do Falecido» há quatro caixas soltas, sem explicação nenhuma na
    tela:

        [x] Possui Filho   [ ] Eleitor   [ ] Desconhecido   [x] Possui Bens

    **ELAS NÃO SÃO ESTATÍSTICA: SÃO GATILHOS.** Cada uma corresponde a uma
    obrigação que nasce no momento do assento e vence depois dele. Marcar
    «Eleitor» é o que faz a comunicação ao TRE existir; deixar em branco é o
    que faz ela não existir — e ninguém descobre a falta, porque não há falta
    visível: há um campo não preenchido.

O QUE ESTE MÓDULO MUDA NO NOSSO DESENHO, E É UMA CORREÇÃO
    Até aqui as nossas comunicações eram descobertas por **varredura**: o
    módulo de comunicações passava nos assentos e deduzia quem alcançava.
    Isso funciona para o que se deduz do próprio dado — a idade do falecido,
    por exemplo, que a Junta Militar usa.

    Mas **«era eleitor» e «deixou bens» não se deduzem de assento nenhum**.
    São coisas que o declarante diz no balcão, com a família na frente, e que
    depois viram telefonema — ou não viram nada. O E-Ofício pergunta na hora,
    e está certo.

    Por isso aqui a marca é **três estados, e não dois**: SIM, NÃO e
    **NÃO PERGUNTADO**. Uma caixa desmarcada significa as duas últimas ao
    mesmo tempo, e é a ambiguidade que faz a obrigação sumir calada. É a mesma
    razão dos marcadores do SIRC (`nomeIgnorado`) e do `Ignorar Hora` da tela
    de nascimento: **o vazio nunca pode querer dizer duas coisas.**
"""
from __future__ import annotations

import sqlite3
from typing import Any

SIM = "SIM"
NAO = "NAO"
NAO_PERGUNTADO = ""

ESTADOS: dict[str, str] = {
    SIM: "Sim",
    NAO: "Não",
    NAO_PERGUNTADO: "Não perguntado",
}

# A ESPECIE A QUE ELAS PERTENCEM. Nascimento e casamento não as têm.
ESPECIE = "OBITO"


MARCAS: tuple[dict, ...] = (
    {
        "chave": "obito_eleitor",
        "rotulo": "Era eleitor",
        "pergunta": "O falecido era eleitor?",
        # O QUE ELA OBRIGA — e este é o campo que justifica o módulo existir.
        "obriga": "comunicar o óbito à Justiça Eleitoral",
        "artigo": "art. 71, § 3º, do Código Eleitoral; Resolução Conjunta "
                  "CNJ/TSE — o meio oficial é o INFODIP",
        "prazo": "mensal, até o dia 15 do mês seguinte",
        "porque_importa": "eleitor morto que não é comunicado **continua na "
                          "folha de votação** — e a família responde por "
                          "ausência às urnas de quem já morreu",
        "pendencia_da_casa": "o cadastro desta serventia no **INFODIP**, no "
                             "TRE, ainda não foi feito",
    },
    {
        "chave": "obito_possui_bens",
        "rotulo": "Deixou bens",
        "pergunta": "O falecido deixou bens a inventariar?",
        "obriga": "nada de imediato — mas orienta o balcão sobre o inventário",
        "artigo": "arts. 610 a 673 do CPC; art. 1.784 do Código Civil",
        "prazo": "o inventário abre-se em **dois meses** (CPC, art. 611)",
        "porque_importa": "a família costuma descobrir o prazo depois de "
                          "vencido, e a multa do ITCMD já correu",
        "pendencia_da_casa": "",
    },
    {
        "chave": "obito_possui_filho",
        "rotulo": "Deixou filhos",
        "pergunta": "O falecido deixou filhos?",
        "obriga": "nada de imediato — interessa à sucessão e ao INSS",
        "artigo": "art. 1.829 do Código Civil",
        "porque_importa": "é a primeira pergunta de quem vai pedir pensão por "
                          "morte, e a certidão não a responde",
        "prazo": "",
        "pendencia_da_casa": "",
    },
    {
        "chave": "obito_desconhecido",
        "rotulo": "Pessoa não identificada",
        "pergunta": "O falecido é pessoa não identificada?",
        "obriga": "lavrar com as características que houver, e **comunicar à "
                  "autoridade policial**",
        "artigo": "art. 81 da Lei nº 6.015/1973",
        "prazo": "",
        "porque_importa": "o assento de desconhecido tem **teor próprio** e "
                          "não pode usar o modelo comum — e o nome, quando "
                          "vier, entra por averbação",
        "pendencia_da_casa": "",
    },
)

CHAVES = tuple(m["chave"] for m in MARCAS)


class MarcaError(ValueError):
    """Erro de marca, em português de balcão."""


def marca(chave: str) -> dict:
    for m in MARCAS:
        if m["chave"] == chave:
            return m
    raise MarcaError(
        f"Não existe a marca «{chave}». As que existem: "
        + ", ".join(CHAVES) + ".")


def normalizar(valor: Any) -> str:
    """Um dos três estados. **Qualquer outra coisa vira NÃO PERGUNTADO.**

    Não levanta erro de propósito: valor estranho vindo de formulário antigo
    ou de carga deve cair no estado que **pede para ser perguntado de novo**,
    e não num «não» que ninguém disse.
    """
    v = ("" if valor is None else str(valor)).strip().upper()
    if v in ("SIM", "S", "1", "TRUE", "T"):
        return SIM
    if v in ("NAO", "NÃO", "N", "0", "FALSE", "F"):
        return NAO
    return NAO_PERGUNTADO


def do_assento(assento: dict) -> list[dict]:
    """As quatro marcas de um assento, com o estado de cada uma. Só lê."""
    fora = []
    for m in MARCAS:
        estado = normalizar(assento.get(m["chave"]))
        fora.append({**m, "estado": estado,
                     "estado_nome": ESTADOS[estado],
                     "perguntada": estado != NAO_PERGUNTADO})
    return fora


def o_que_falta_perguntar(assento: dict) -> list[dict]:
    """As marcas que ninguém respondeu ainda.

    **É A LISTA QUE FAZ A DIFERENÇA ENTRE «NÃO» E «NÃO PERGUNTEI».** Sem ela,
    um assento em que ninguém perguntou nada parece um assento em que tudo foi
    respondido com «não».
    """
    return [m for m in do_assento(assento) if not m["perguntada"]]


def obrigacoes_abertas(assento: dict) -> list[dict]:
    """O que este assento passou a dever por causa das marcas com SIM."""
    return [m for m in do_assento(assento)
            if m["estado"] == SIM and m["obriga"]
            and not m["obriga"].startswith("nada")]


def assentos_com_marca_por_perguntar(con: sqlite3.Connection,
                                     limite: int = 500) -> list[dict]:
    """Os óbitos em que alguma das quatro não foi perguntada. Só lê.

    O ACERVO NÃO ENTRA: ninguém vai telefonar para a família de um óbito de
    2009 para perguntar se o falecido era eleitor. A pergunta é do balcão, com
    o declarante na frente — depois dele, ela não se responde mais.
    """
    con.row_factory = sqlite3.Row
    colunas = ", ".join(f"a.{c}" for c in CHAVES)
    fora = []
    for linha in con.execute(
            f"""SELECT a.id, a.especie, a.numero, a.nome, a.data_ato, {colunas}
                  FROM rc_assentos a
                 WHERE UPPER(COALESCE(a.especie,'')) = ?
                   AND COALESCE(a.origem,'') <> 'EOFICIO'
                   AND COALESCE(a.situacao,'ATIVO') <> 'CANCELADO'
              ORDER BY a.data_ato IS NULL, a.data_ato DESC, a.id DESC
                 LIMIT ?""", (ESPECIE, limite)):
        d = dict(linha)
        faltam = o_que_falta_perguntar(d)
        if faltam:
            d["faltam"] = faltam
            fora.append(d)
    return fora


def quantas_pendentes(con: sqlite3.Connection) -> int:
    return len(assentos_com_marca_por_perguntar(con, limite=100000))


def responder(con: sqlite3.Connection, assento_id: int, respostas: dict) -> dict:
    """Grava as respostas do balcão. ESCREVE — e só nas quatro colunas.

    **NÃO APAGA RESPOSTA JÁ DADA COM UM VAZIO.** Se o formulário vier sem uma
    das marcas, a que estava lá fica: um POST que perde campo por engano — o
    navegador que não enviou, o escrevente que voltou a página — não pode
    transformar «ele respondeu que não» de volta em «ninguém perguntou». Para
    desfazer uma resposta é preciso dizer explicitamente `NAO_PERGUNTADO`.

    Recebe a conexão de fora, dentro de `db.transaction()`, como manda a casa.
    """
    atual = con.execute(
        f"SELECT {', '.join(CHAVES)} FROM rc_assentos WHERE id=?",
        (assento_id,)).fetchone()
    if atual is None:
        raise MarcaError(f"Não achei o assento nº {assento_id}.")
    atual = dict(atual)

    mudou: dict[str, str] = {}
    for chave in CHAVES:
        if chave not in respostas:
            continue
        novo = normalizar(respostas[chave])
        velho = normalizar(atual.get(chave))
        if novo == NAO_PERGUNTADO and velho != NAO_PERGUNTADO:
            # Vazio não apaga o que já foi respondido — ver a docstring.
            continue
        if novo != velho:
            mudou[chave] = novo
    if mudou:
        con.execute(
            "UPDATE rc_assentos SET "
            + ", ".join(f"{c}=?" for c in mudou)
            + " WHERE id=?", (*mudou.values(), assento_id))
    return {"mudou": mudou, "quantas": len(mudou)}


def apagar_resposta(con: sqlite3.Connection, assento_id: int,
                    chave: str) -> None:
    """Desfaz uma resposta, voltando ao «não perguntado». ESCREVE.

    Existe para que `responder` possa recusar o vazio sem deixar o balcão sem
    saída: quem marcou por engano precisa de um caminho, e o caminho é DIZER
    que quer desfazer — não é o silêncio de um campo que não veio.
    """
    marca(chave)                                   # recusa chave inventada
    con.execute(f"UPDATE rc_assentos SET {chave}=? WHERE id=?",
                (NAO_PERGUNTADO, assento_id))


def eleitores_a_comunicar(con: sqlite3.Connection,
                          limite: int = 500) -> list[dict]:
    """Os óbitos de eleitores — a lista que a Justiça Eleitoral espera.

    **ELA SÓ EXISTE PORQUE ALGUÉM MARCOU A CAIXA.** Não há como deduzir de um
    assento que o falecido votava; por isso esta lista mede exatamente o que
    foi perguntado, e a de cima mede o que não foi.
    """
    con.row_factory = sqlite3.Row
    return [dict(r) for r in con.execute(
        """SELECT id, especie, numero, nome, data_ato, data_fato
             FROM rc_assentos
            WHERE UPPER(COALESCE(especie,'')) = ?
              AND UPPER(COALESCE(obito_eleitor,'')) = 'SIM'
              AND COALESCE(situacao,'ATIVO') <> 'CANCELADO'
         ORDER BY data_ato IS NULL, data_ato DESC, id DESC LIMIT ?""",
        (ESPECIE, limite))]
