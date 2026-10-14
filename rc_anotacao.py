"""As ANOTAÇÕES do Registro Civil, e as comunicações que elas geram.

    «vamos seguir no desenvolvimento do nosso módulo maduro e completo de RCPN»
    — o oficial, 29/08/2026

O QUE É, EM UMA FRASE
    Quando esta casa lavra um casamento ou um óbito, **os assentos anteriores
    daquela pessoa têm de ser anotados** — o casamento no nascimento, o óbito no
    nascimento e no casamento. Se o assento anterior é daqui, anota-se aqui; se
    é de outra serventia, **manda-se comunicação**. E há **cinco dias** para
    fazer isso.

A NORMA, LIDA NO CÓDIGO DE NORMAS DO TJMA — Seção XIII, arts. 367 a 372
    Está no `Código de normas TJMA atualizado.pdf`, que está na casa. Cada regra
    abaixo traz o artigo ao lado, como em `us_tjma` e `rt_tjma`.

É O TERCEIRO PRAZO DA CASA QUE NINGUÉM DE FORA COBRA
    O primeiro foi o do SIGEF (30 dias, art. 620 § 2º); o segundo, a relação
    mensal da Junta Militar (Lei 4.375/1964). Este é o mais curto — **cinco
    dias** — e o mais frequente: nasce em **todo** casamento e em **todo** óbito.

    Os três têm a mesma forma: obrigação **da serventia**, que nasce depois do
    ato — com o cliente já fora do balcão — e que **não tem ninguém do lado de
    fora esperando**. É exatamente o tipo de prazo que se perde.

O QUE ESTE MÓDULO NÃO FAZ
    **Não anota sozinho no assento de outra pessoa.** A anotação é ato do
    registro — vai à margem do assento, com remissão recíproca — e o art. 370
    manda **conferir a compatibilidade dos atos registrários antes**. Um
    programa que anotasse sozinho estaria decidindo que dois assentos são da
    mesma pessoa, que é justamente o que o oficial tem de conferir.

    Ele **diz o que se deve**, prepara o texto, e registra o que foi feito.
"""
from __future__ import annotations

import sqlite3
from typing import Any


class AnotacaoError(ValueError):
    """Erro de regra, com mensagem pronta para o balcao."""


# ------------------------------------------------------------------- a norma

SECAO = {"secao": "XIII", "titulo": "Das Anotações", "do": 367, "ao": 372}

# Art. 372 — O QUE SE ANOTA ONDE. **Medido no artigo, e nao suposto.**
#
# «O obito devera ser anotado, com as remissoes reciprocas, nos assentos de
#  casamento e nascimento. Paragrafo unico. O casamento sera anotado no registro
#  de nascimento e nos registros anteriores de casamento.»
#
# Note a assimetria, que e da norma: o obito vai para DOIS assentos; o casamento
# vai para o nascimento e para os casamentos ANTERIORES — nao para obito nenhum,
# porque quem casa esta vivo.
O_QUE_SE_ANOTA: dict[str, tuple[str, ...]] = {
    "OBITO": ("NASCIMENTO", "CASAMENTO"),
    "CASAMENTO": ("NASCIMENTO", "CASAMENTO"),
    "CASAMENTO_RELIGIOSO": ("NASCIMENTO", "CASAMENTO"),

    # AS TRES DO LIVRO E TAMBEM ANOTAM, e o artigo e outro — 328, § 2o:
    #
    # «Compete ao registrador civil de pessoas naturais que proceder ao registro
    #  da sentenca no Livro "E" comunicar tal fato ao registrador civil do
    #  nascimento e/ou casamento do emancipado, interditado ou ausente, que
    #  anotara tais circunstancias nos assentos primitivos.»
    #
    # EU AS TINHA DEIXADO DE FORA, e foi a minha propria saida de conferencia
    # que mostrou: ao listar as especies, `INTERDICAO` aparecia como «nenhuma —
    # e o registro primitivo», o que e falso. Ela nao e primitiva coisa nenhuma:
    # e uma sentenca que muda a capacidade de quem ja tem nascimento lavrado.
    "INTERDICAO": ("NASCIMENTO", "CASAMENTO"),
    "EMANCIPACAO": ("NASCIMENTO", "CASAMENTO"),
    "AUSENCIA": ("NASCIMENTO", "CASAMENTO"),
}

ARTIGO_DO_QUE_SE_ANOTA = "art. 372"

# E o art. 328, § 3o acrescenta uma SEGUNDA comunicacao, que so existe nas tres
# do Livro E: «Efetuados o registro no Livro "E" e a(s) anotacao(oes) nos
# assentos de nascimento e/ou casamento, cada oficial comunicara, no prazo de 05
# (cinco) dias, ao JUIZ que a determinou, sob pena de responsabilidade
# administrativa.»
#
# Ela nao entra na tabela de pendencias porque nao e anotacao em assento nenhum
# — e aviso ao juizo. Fica declarada para a tela dizer, que e onde ela importa.
AVISAR_O_JUIZ = {
    "artigo": "art. 328, § 3º",
    "especies": ("INTERDICAO", "EMANCIPACAO", "AUSENCIA"),
    "prazo_dias": 5,
    "o_que": "Feitos o registro no Livro E e as anotações, cada oficial "
             "comunica ao JUIZ que a determinou, em 5 dias, sob pena de "
             "responsabilidade administrativa.",
}

# Art. 367 — O PRAZO, e ele conta do ato.
PRAZO_DIAS = 5
ARTIGO_DO_PRAZO = "art. 367"

TEXTO_DO_ART_367 = (
    "Sempre que o oficial de registro ou preposto autorizado fizer algum "
    "registro ou averbação, deverá, no prazo de cinco dias, anotá-lo nos atos "
    "anteriores, com remissões recíprocas, se lançados na serventia, ou fará "
    "comunicação, com resumo do assento, à serventia onde estiverem os "
    "registros primitivos.")

# Art. 369 — O QUE A ANOTACAO TEM DE CONTER. Os tres incisos, na ordem.
CONTEUDO_DA_ANOTACAO: tuple[dict, ...] = (
    {"inciso": "I", "artigo": "art. 369, I", "o_que": "A data da anotação"},
    {"inciso": "II", "artigo": "art. 369, II",
     "o_que": "A indicação do registro ou averbação promovida"},
    {"inciso": "III", "artigo": "art. 369, III",
     "o_que": "A serventia, o livro, a folha e o número do registro"},
)

QUEM_SUBSCREVE = {
    "artigo": "art. 369, parágrafo único",
    "o_que": "A anotação será subscrita APENAS pelo oficial de registro ou "
             "preposto autorizado.",
}

# Art. 370 — CONFERIR ANTES, e e por isso que este modulo nao anota sozinho.
CONFERIR_ANTES = {
    "artigo": "art. 370",
    "o_que": "Antes de proceder à anotação, incumbe ao oficial observar a "
             "COMPATIBILIDADE dos atos registrários. Sendo necessário, "
             "solicitará informações às serventias envolvidas.",
}

# Art. 371 e art. 366, paragrafo unico — POR ONDE A COMUNICACAO VAI, e a ordem
# e da norma: **a CRC vem primeiro**.
#
# O art. 366 diz, do cancelamento: «A comunicacao (...) devera ser feita por
# meio eletronico, atraves da Central de Informacoes de Registro Civil das
# Pessoas Naturais (CRC Nacional)». E o art. 226, § 1o, I, do obito: «dar-se-a
# primeiramente pelo sistema CRC (...) ou, alternativamente, por malote digital
# (Sistema HERMES) (...) ou, em caso de falha desse sistema, quaisquer outros
# meios, desde que haja confirmacao de recebimento».
POR_ONDE_COMUNICAR: tuple[dict, ...] = (
    {"canal": "CRC", "artigo": "art. 226, § 1º, I; art. 366, parágrafo único",
     "o_que": "Pela Central de Informações do Registro Civil (CRC Nacional) — "
              "é o caminho de primeira escolha, por determinação do Provimento "
              "46/2015 do CNJ"},
    {"canal": "MALOTE", "artigo": "art. 226, § 1º, I",
     "o_que": "Por malote digital (Sistema HERMES), do Provimento 25/2012 do "
              "CNJ — alternativa à CRC"},
    {"canal": "CARTA", "artigo": "art. 371",
     "o_que": "Por carta relacionada em protocolo, ou outro meio eletrônico "
              "seguro — e, em caso de falha dos anteriores, qualquer meio "
              "DESDE QUE HAJA CONFIRMAÇÃO DE RECEBIMENTO"},
)

CANAIS = tuple(x["canal"] for x in POR_ONDE_COMUNICAR)

# Art. 371, paragrafo unico — A PARTE PODE TRAZER A CERTIDAO.
#
# **E isso e uma porta de entrada, e nao so uma curiosidade**: a anotacao se faz
# a pedido do interessado, a vista de certidao atualizada, «ainda que a
# comunicacao nao tenha sido recebida». O balcao precisa saber disso, porque a
# pessoa chega com a certidao na mao e o escrevente pode achar que tem de
# esperar o oficio.
A_PEDIDO_DA_PARTE = {
    "artigo": "art. 371, parágrafo único",
    "prazo_da_certidao_dias": 90,
    "o_que": "A anotação pode ser feita a requerimento da parte interessada, à "
             "vista do original ou fotocópia autenticada da certidão "
             "atualizada (prazo de 90 dias), AINDA QUE A COMUNICAÇÃO NÃO TENHA "
             "SIDO RECEBIDA.",
}

# Art. 285 — e ele acrescenta uma coisa que nenhum dos outros diz.
CERTIFICAR_NA_HABILITACAO = {
    "artigo": "art. 285, parágrafo único",
    "o_que": "A comunicação ou anotação à margem do registro de nascimento "
             "deve ser CERTIFICADA NOS AUTOS DE HABILITAÇÃO.",
}


def artigos_citados() -> list[str]:
    """Todo artigo que este módulo cita. Só calcula — serve para conferir."""
    import re
    fontes: list[Any] = [QUEM_SUBSCREVE, CONFERIR_ANTES, A_PEDIDO_DA_PARTE,
                         CERTIFICAR_NA_HABILITACAO, AVISAR_O_JUIZ,
                         {"artigo": ARTIGO_DO_PRAZO},
                         {"artigo": ARTIGO_DO_QUE_SE_ANOTA}]
    fontes.extend(CONTEUDO_DA_ANOTACAO)
    fontes.extend(POR_ONDE_COMUNICAR)
    vistos = set()
    for item in fontes:
        for m in re.finditer(r"art\.\s*(\d+)", str(item.get("artigo", ""))):
            vistos.add(int(m.group(1)))
    return [f"art. {n}" for n in sorted(vistos)]


# --------------------------------------------------------------- as situações

PENDENTE = "PENDENTE"
ANOTADA = "ANOTADA"          # o assento anterior é daqui, e foi anotado
COMUNICADA = "COMUNICADA"    # é de outra serventia, e a comunicação saiu
DISPENSADA = "DISPENSADA"    # não há assento anterior a anotar

SITUACOES = (PENDENTE, ANOTADA, COMUNICADA, DISPENSADA)

NOME_DA_SITUACAO = {
    PENDENTE: "Pendente",
    ANOTADA: "Anotada no assento desta serventia",
    COMUNICADA: "Comunicada à serventia de origem",
    DISPENSADA: "Dispensada, com motivo escrito",
}

MINIMO_DO_MOTIVO = 10


def _texto(v: Any) -> str:
    return str(v or "").strip()


# ------------------------------------------------------------- o que se deve


def o_que_o_ato_gera(especie: str) -> tuple[str, ...]:
    """As espécies de assento que este ato obriga a anotar. Só calcula.

    SAI DO ART. 372, e não de uma lista minha. Espécie que não gera anotação
    devolve vazio — e isso é resposta, não omissão: um nascimento não anota nada
    em lugar nenhum, porque é ele o registro primitivo.
    """
    return O_QUE_SE_ANOTA.get(_texto(especie).upper(), ())


def pendencias_do_assento(con: sqlite3.Connection, assento_id: int) -> list[dict]:
    con.row_factory = sqlite3.Row
    return [dict(r) for r in con.execute(
        """SELECT * FROM rc_anotacoes WHERE assento_id = ?
            ORDER BY id""", (assento_id,))]


def declarar(con: sqlite3.Connection, assento_id: int, *, agora: str,
             usuario: str | None = None) -> list[int]:
    """Abre as pendências de anotação que o ato gerou. ESCREVE.

    CHAMADA AO LAVRAR, e não depois. O prazo do art. 367 conta do ato; declarar
    a pendência mais tarde faria o relógio começar atrasado — que é o mesmo que
    não ter relógio.

    REPETÍVEL POR CONSTRUÇÃO: `UNIQUE(assento_id, especie_alvo)` e
    `INSERT OR IGNORE`. Lavrar, corrigir e salvar de novo não pode multiplicar a
    obrigação.
    """
    con.row_factory = sqlite3.Row
    a = con.execute("SELECT * FROM rc_assentos WHERE id = ?",
                    (assento_id,)).fetchone()
    if not a:
        raise AnotacaoError(f"Não achei o assento nº {assento_id}.")

    novas = []
    for alvo in o_que_o_ato_gera(a["especie"]):
        cur = con.execute(
            """INSERT OR IGNORE INTO rc_anotacoes (assento_id, especie_alvo,
                   situacao, criado_em, criado_por)
               VALUES (?,?,?,?,?)""",
            (assento_id, alvo, PENDENTE, agora, usuario))
        if cur.rowcount:
            novas.append(int(cur.lastrowid))
    return novas


def resumo_do_assento(con: sqlite3.Connection, assento_id: int) -> str:
    """O «resumo do assento» que o art. 367 manda ir junto da comunicação.

    O ARTIGO PEDE RESUMO, E NÃO O TEOR INTEIRO — e a diferença importa: o teor
    traz a qualificação de todo mundo, e mandá-lo a outra serventia é espalhar
    dado pessoal que ela não precisa para anotar à margem.

    O que vai é o que o art. 369 exige do outro lado: que ato foi, quando, e
    onde ele está — serventia, livro, folha e número.
    """
    con.row_factory = sqlite3.Row
    a = con.execute("SELECT * FROM rc_assentos WHERE id = ?",
                    (assento_id,)).fetchone()
    if not a:
        raise AnotacaoError(f"Não achei o assento nº {assento_id}.")
    a = dict(a)
    partes = [f"{a.get('especie', '')} registrado sob o termo "
              f"nº {a.get('numero', '')}"]
    if a.get("livro_volume"):
        partes.append(f"livro {a['livro_volume']}")
    if a.get("data_ato"):
        partes.append(f"lavrado em {a['data_ato']}")
    if a.get("data_fato"):
        partes.append(f"o fato deu-se em {a['data_fato']}")
    if a.get("nome"):
        partes.append(f"de {a['nome']}")
    if a.get("matricula"):
        partes.append(f"matrícula {a['matricula']}")
    return ", ".join(partes) + "."


def anotar_aqui(con: sqlite3.Connection, pendencia_id: int, *,
                assento_alvo_id: int, agora: str,
                usuario: str | None = None) -> dict:
    """Registra que o assento anterior, DESTA serventia, foi anotado. ESCREVE.

    **NÃO ESCREVE NO ASSENTO ALVO.** A anotação vai à margem, e o art. 370 manda
    o oficial conferir a compatibilidade dos atos antes — um programa que
    anotasse sozinho estaria decidindo que dois assentos são da mesma pessoa,
    que é justamente o que ele tem de conferir.

    O que se grava aqui é **que ele conferiu e anotou**, com a data e com qual
    assento — que é o rastro que a correição procura.
    """
    p = _exigir(con, pendencia_id)
    if p["situacao"] != PENDENTE:
        raise AnotacaoError(
            f"Esta anotação já está como {NOME_DA_SITUACAO.get(p['situacao'], p['situacao'])}.")
    con.row_factory = sqlite3.Row
    if not con.execute("SELECT 1 FROM rc_assentos WHERE id = ?",
                       (assento_alvo_id,)).fetchone():
        raise AnotacaoError(
            f"Não achei o assento nº {assento_alvo_id} nesta serventia. Se o "
            "registro anterior é de outra casa, o caminho é a comunicação.")
    if int(assento_alvo_id) == int(p["assento_id"]):
        raise AnotacaoError(
            "O assento não se anota nele mesmo — a anotação vai no registro "
            "ANTERIOR da pessoa.")

    con.execute(
        """UPDATE rc_anotacoes SET situacao = ?, assento_alvo_id = ?,
               resolvida_em = ?, resolvida_por = ? WHERE id = ?""",
        (ANOTADA, int(assento_alvo_id), agora, usuario, pendencia_id))
    return {"situacao": ANOTADA}


def comunicar(con: sqlite3.Connection, pendencia_id: int, *, canal: str,
              serventia: str, agora: str, protocolo: str = "",
              usuario: str | None = None) -> dict:
    """Registra a comunicação à serventia onde está o registro primitivo.

    O CANAL SAI DA NORMA, e a ordem é dela: **a CRC vem primeiro** (Provimento
    46/2015 do CNJ), o malote digital é a alternativa, e qualquer outro meio só
    «em caso de falha desse sistema, desde que haja **confirmação de
    recebimento**».

    Por isso o protocolo é exigido: sem ele não há confirmação, e comunicação
    sem confirmação é a que ninguém prova ter mandado.
    """
    p = _exigir(con, pendencia_id)
    if p["situacao"] != PENDENTE:
        raise AnotacaoError(
            f"Esta anotação já está como {NOME_DA_SITUACAO.get(p['situacao'], p['situacao'])}.")
    canal = _texto(canal).upper()
    if canal not in CANAIS:
        raise AnotacaoError(
            f"«{canal}» não é um caminho de comunicação. Os que a norma prevê, "
            "nesta ordem: "
            + "; ".join(f"{x['canal']} ({x['artigo']})"
                        for x in POR_ONDE_COMUNICAR) + ".")
    if not _texto(serventia):
        raise AnotacaoError(
            "Diga a qual serventia a comunicação foi enviada — é ela que tem o "
            "registro primitivo.")
    if not _texto(protocolo):
        raise AnotacaoError(
            "Guarde o protocolo ou o comprovante de recebimento. A norma exige "
            "confirmação de recebimento (art. 226, § 1º, I), e comunicação sem "
            "confirmação é a que ninguém prova ter mandado.")

    con.execute(
        """UPDATE rc_anotacoes SET situacao = ?, canal = ?,
               serventia_destino = ?, protocolo = ?, resolvida_em = ?,
               resolvida_por = ? WHERE id = ?""",
        (COMUNICADA, canal, _texto(serventia), _texto(protocolo), agora,
         usuario, pendencia_id))
    return {"situacao": COMUNICADA}


def dispensar(con: sqlite3.Connection, pendencia_id: int, *, motivo: str,
              agora: str, usuario: str | None = None) -> dict:
    """Marca que não há assento anterior a anotar. EXIGE MOTIVO ESCRITO.

    DISPENSAR É DECISÃO DO OFICIAL; IGNORAR NÃO É — e o caso real é comum:
    falecido que nunca teve casamento, ou nascimento registrado no exterior. O
    que não pode é a pendência sumir sem ninguém dizer por quê.
    """
    p = _exigir(con, pendencia_id)
    if p["situacao"] != PENDENTE:
        raise AnotacaoError(
            f"Esta anotação já está como {NOME_DA_SITUACAO.get(p['situacao'], p['situacao'])}.")
    if len(_texto(motivo)) < MINIMO_DO_MOTIVO:
        raise AnotacaoError(
            "Para dispensar, escreva o motivo — «não há casamento anterior», "
            "«nascimento registrado no exterior». "
            f"Ao menos {MINIMO_DO_MOTIVO} letras.")
    con.execute(
        """UPDATE rc_anotacoes SET situacao = ?, motivo = ?, resolvida_em = ?,
               resolvida_por = ? WHERE id = ?""",
        (DISPENSADA, _texto(motivo), agora, usuario, pendencia_id))
    return {"situacao": DISPENSADA}


def _exigir(con: sqlite3.Connection, pendencia_id: int) -> dict:
    con.row_factory = sqlite3.Row
    r = con.execute("SELECT * FROM rc_anotacoes WHERE id = ?",
                    (pendencia_id,)).fetchone()
    if not r:
        raise AnotacaoError("Não achei essa pendência de anotação.")
    return dict(r)


# ------------------------------------------------------------------ as listas


def pendentes(con: sqlite3.Connection, limite: int = 500) -> list[dict]:
    """O que a casa deve anotar ou comunicar, do mais antigo para o mais novo.

    **DO MAIS ANTIGO PARA O MAIS NOVO**, e é o contrário da ordem das outras
    listas deste sistema. Aqui o que importa é o prazo: quem está há mais tempo
    esperando é quem está mais perto de estourar os cinco dias.
    """
    con.row_factory = sqlite3.Row
    return [dict(r) for r in con.execute(
        """SELECT n.*, a.especie, a.numero, a.nome, a.data_ato
             FROM rc_anotacoes n
             JOIN rc_assentos a ON a.id = n.assento_id
            WHERE n.situacao = ?
         ORDER BY a.data_ato, n.id LIMIT ?""", (PENDENTE, limite))]


def quantas_pendentes(con: sqlite3.Connection) -> int:
    con.row_factory = sqlite3.Row
    return int(con.execute(
        "SELECT COUNT(*) FROM rc_anotacoes WHERE situacao = ?",
        (PENDENTE,)).fetchone()[0])


def fora_do_prazo(con: sqlite3.Connection, *, hoje: str) -> list[dict]:
    """As que já passaram dos cinco dias. Só lê.

    NÃO CONTA DIA ÚTIL, e é deliberado: o art. 367 escreve «no prazo de cinco
    dias», sem qualificar — inventar «úteis» daria à serventia mais prazo do que
    a norma deu. É a mesma decisão do prazo de 30 dias do SIGEF.

    A comparação é de texto de data (`AAAA-MM-DD`), que ordena igual à data —
    e assim o cálculo do vencimento não vira uma segunda contagem no SQL.
    """
    from datetime import date, timedelta
    try:
        limite = (date.fromisoformat(str(hoje)[:10])
                  - timedelta(days=PRAZO_DIAS)).isoformat()
    except ValueError:
        return []
    con.row_factory = sqlite3.Row
    return [dict(r) for r in con.execute(
        """SELECT n.*, a.especie, a.numero, a.nome, a.data_ato
             FROM rc_anotacoes n
             JOIN rc_assentos a ON a.id = n.assento_id
            WHERE n.situacao = ? AND COALESCE(a.data_ato, '') <> ''
              AND a.data_ato < ?
         ORDER BY a.data_ato, n.id""", (PENDENTE, limite))]
