"""A NOTIFICAÇÃO EXTRAJUDICIAL DO RTD — do registro à certidão, com as diligências.

    «Notificação extrajudicial no RTD (frequente): registro, diligência,
     certidão de notificação positiva/negativa, prazos.»       — LG04, 19/10/2026

O QUE HAVIA, MEDIDO EM 19/10/2026
    O caminho genérico do RTD inteiro — protocolo (`rg_titulo.receber`),
    qualificação, registro no Livro B (`rg_registro.abrir_registro`), selo e
    custas do registro —, e **nada da notificação**: nenhuma tabela de
    diligência, nenhuma certidão positiva ou negativa, nenhum prazo. A
    notificação era a palavra «notificação» escrita no campo `natureza`. Os
    caminhos de selo dela existiam só no contrato (`selador.py`), sem envelope
    e sem tela, e a casa nunca selou por eles.

A NORMA — Código de Normas do MA (Prov. COGEX 28/2026), arts. 986 a 993
    art. 986 §4   a diligência se faz **entre 6h e 20h**, todos os dias, **menos
                  domingo e feriado**;
    art. 987      a **primeira** diligência, em **até 10 dias** da apresentação;
    art. 987 §1   decorridos 30 dias, **averba-se** o resultado, positivo ou
                  negativo;
    art. 987 §2   o resultado NEGATIVO só se certifica depois de **no mínimo três
                  diligências, em dias e horários alternados**;
    art. 987 §3   depois das três, diligência a mais **só a pedido** do
                  apresentante, e cobrada (item 15.8.1.1);
    art. 988 §2   **não se dá certidão de notificação antes do registro**;
    arts. 986 §2, 987 §4, 989 §5   a certidão é **averbada à margem** do
                  registro;
    art. 992      a via entregue a **procurador com poderes específicos** para
                  receber notificação vale como notificação efetivada.

UMA LINHA POR DESTINATÁRIO, E NÃO POR DOCUMENTO
    A tabela de custas cobra a notificação **por destinatário** (15.8 e 15.8.1),
    e cada destinatário tem as suas diligências, o seu resultado e a sua
    certidão. Uma linha com três destinatários obrigaria a dizer «positiva» de
    um documento que foi entregue a dois e não achou o terceiro.

A DILIGÊNCIA COBRADA NÃO É A IDA — e é por isso que são duas tabelas
    O item 15.8.1 é «diligência … **por destinatário, até o limite de 03
    (três)**»: um preço cobre as três primeiras idas. Da quarta em diante, cada
    ida é um 15.8.1.1. As IDAS (`rg_notificacao_idas`) são o que a norma conta
    — dia, hora, resultado —; a DILIGÊNCIA (`rg_notificacao_diligencias`) é o
    ato que se cobra e se sela. Se fossem uma tabela só, a segunda e a terceira
    ida ficariam para sempre na lista de «atos sem selo» (`ato_selado.
    atos_sem_selo`), sem selo nenhum para receber — o alarme que soa sempre.

    A ZONA RURAL é outro item, o 15.8.1.2, «cobrado do apresentante, por» — o
    texto da tabela importada termina aí, e o resto (quilômetro, pela forma
    dos outros itens de deslocamento) **é pergunta ao oficial**; a quantidade
    que vai ao selo é a distância informada.

O SELO, POR ANALOGIA, E POR QUE ISSO NÃO É SELO INVENTADO
    `/selo/rtdpj/diligencia/zona-urbana`, `/diligencia/fora-zona-urbana`,
    `/acima-tres-diligencias` e `/certidao-notificacao` estão no contrato e a
    casa **nunca** os usou: não há envelope medido. O envelope sai na forma do
    `atos-em-geral` do RTD (`ato_selado.envelope_do_rtdpj` — escrevente, partes,
    quantidade, ato), que é a forma que esta casa manda em 49 selos do RTD, e a
    certidão leva, além dela, o número do registro (`registroAverbacao`) e o
    livro, que o nome do esquema dela pede (`RtdpjComMatriculaRegistroAverbacao`).
    **É forma por analogia, a conferir na homologação.** Se o aparelho recusar,
    nada se inventa: a diligência ou a certidão fica **suspensa** — regra da
    casa, 16/09/2026 —, aparece na ficha com o motivo, e se sela de novo pelo
    botão. A certidão não sai enquanto houver diligência com selo suspenso.

O QUE FICOU PARA DEPOIS
    A notificação por **carta com AR** (art. 990) e por **edital** (art. 991):
    cada uma tem prazo e prova próprios (o aviso que volta, as três
    publicações), e ligá-las pela metade faria a tela certificar o que ninguém
    conferiu. Hoje a notificação aqui é a PESSOAL; a coluna `forma` existe para
    elas. E a requisição a registrador de outro município (art. 989).

PostgreSQL nativo, pelo `bd_nativo`. Datas calculadas no Python.
"""
from __future__ import annotations

import hashlib
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable

import modelos_da_casa as MODELOS
from bd_nativo import banco

# A atribuição — o mesmo código de `rg_titulo.RTD` e de `rg_registros.atribuicao`.
RTD = 4


class NotificacaoError(ValueError):
    """Recusa de regra, com a frase pronta para o balcão."""


# ----------------------------------------------------------------- o esquema

SCHEMA = (
    # A NOTIFICAÇÃO, UMA POR DESTINATÁRIO. Nasce do título protocolado (a
    # diligência corre desde a apresentação — art. 987) ou do registro; a
    # certidão só sai quando há registro (art. 988 §2), venha ele daqui ou do
    # título.
    """CREATE TABLE IF NOT EXISTS rg_notificacoes (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    titulo_id bigint REFERENCES rg_titulos(id),
    registro_id bigint REFERENCES rg_registros(id),
    destinatario_nome text NOT NULL,
    destinatario_documento text,
    endereco text NOT NULL,
    zona text NOT NULL DEFAULT 'URBANA',      -- URBANA | RURAL
    distancia_km integer,                     -- a rural: a quantidade do 15.8.1.2
    forma text NOT NULL DEFAULT 'PESSOAL',    -- PESSOAL (AR e edital: depois)
    apresentado_em text NOT NULL,
    prazo_primeira text NOT NULL,             -- apresentado_em + 10 dias (art. 987)
    situacao text NOT NULL DEFAULT 'EM_DILIGENCIA',
    resultado_em text,
    resultado_por text,
    averbacao_ato_id bigint REFERENCES rg_atos(id),
    averbada_em text,
    averbada_por text,
    observacao text,
    criado_em text NOT NULL,
    criado_por text,
    CHECK (titulo_id IS NOT NULL OR registro_id IS NOT NULL)
)""",
    "CREATE INDEX IF NOT EXISTS ix_rg_notificacoes_situacao "
    "ON rg_notificacoes(situacao, apresentado_em)",
    "CREATE INDEX IF NOT EXISTS ix_rg_notificacoes_registro "
    "ON rg_notificacoes(registro_id)",
    "CREATE INDEX IF NOT EXISTS ix_rg_notificacoes_titulo "
    "ON rg_notificacoes(titulo_id)",
    # A DILIGÊNCIA COBRADA — o ato que tem selo e lançamento. Ver o cabeçalho:
    # a primeira cobre até três idas; cada ida a mais, a pedido, é outra.
    """CREATE TABLE IF NOT EXISTS rg_notificacao_diligencias (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    notificacao_id bigint NOT NULL REFERENCES rg_notificacoes(id),
    codigo_tj text NOT NULL,
    caminho text NOT NULL,
    quantidade integer NOT NULL DEFAULT 1,
    idas_cobertas integer NOT NULL DEFAULT 1,
    selo text,
    selo_situacao text NOT NULL DEFAULT 'PENDENTE',  -- PENDENTE | SELADO | SUSPENSO
    selo_motivo text,
    lancamento_id bigint,
    criado_em text NOT NULL,
    criado_por text
)""",
    "CREATE INDEX IF NOT EXISTS ix_rg_notificacao_diligencias_notif "
    "ON rg_notificacao_diligencias(notificacao_id)",
    # A IDA — o que a norma conta: o dia, a hora, o endereço e o que se achou.
    """CREATE TABLE IF NOT EXISTS rg_notificacao_idas (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    notificacao_id bigint NOT NULL REFERENCES rg_notificacoes(id),
    diligencia_id bigint NOT NULL REFERENCES rg_notificacao_diligencias(id),
    numero integer NOT NULL,
    data text NOT NULL,
    hora text NOT NULL,
    turno text NOT NULL,
    endereco text NOT NULL,
    resultado text NOT NULL,
    observacao text,
    a_pedido integer NOT NULL DEFAULT 0,
    feita_por text,
    criado_em text NOT NULL,
    UNIQUE (notificacao_id, numero)
)""",
    "CREATE INDEX IF NOT EXISTS ix_rg_notificacao_idas_notif "
    "ON rg_notificacao_idas(notificacao_id, numero)",
    # A CERTIDÃO — número por exercício, teor congelado e impressão digital,
    # como as outras certidões da casa (`nt_certidoes`, `at_certidoes`).
    """CREATE TABLE IF NOT EXISTS rg_notificacao_certidoes (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    notificacao_id bigint NOT NULL REFERENCES rg_notificacoes(id),
    numero integer NOT NULL,
    ano integer NOT NULL,
    tipo text NOT NULL,                       -- POSITIVA | NEGATIVA
    teor text NOT NULL,
    hash_certidao text NOT NULL,
    selo text,
    selo_situacao text NOT NULL DEFAULT 'PENDENTE',
    selo_motivo text,
    lancamento_id bigint,
    emitida_em text NOT NULL,
    emitida_por text,
    UNIQUE (numero, ano)
)""",
    "CREATE INDEX IF NOT EXISTS ix_rg_notificacao_certidoes_notif "
    "ON rg_notificacao_certidoes(notificacao_id)",
)


def init_rg_notificacao_schema(con: Any) -> None:
    """Cria as tabelas e os índices, se faltarem. Idempotente.

    Cada índice é `CREATE INDEX IF NOT EXISTS` por si, e não depende de a
    tabela ser nova: tabela que já existia também ganha o índice.
    """
    bd = banco(con)
    for comando in SCHEMA:
        bd.escrever(comando)


# ------------------------------------------------------------- o vocabulário

ZONAS = {"URBANA": "Zona urbana", "RURAL": "Zona rural"}

SITUACOES = {
    "EM_DILIGENCIA": "Em diligência",
    "POSITIVA": "Notificado",
    "NEGATIVA": "Não localizado — resultado negativo",
}

# O QUE A IDA ACHOU. Os três primeiros efetivam a notificação; os outros a
# frustram. A RECUSA EFETIVA: o destinatário foi achado e ficou ciente — o que
# ele recusou foi a via, e a certidão diz isso com as letras dela.
RESULTADOS = {
    "ENTREGUE": "Entregue ao destinatário",
    "ENTREGUE_PROCURADOR": "Entregue a procurador com poderes específicos (art. 992)",
    "RECUSOU": "Destinatário recusou receber a via",
    "NAO_LOCALIZADO": "Não localizado no endereço",
    "AUSENTE": "Ausente — ninguém atendeu",
    "MUDOU_SE": "Mudou-se / desconhecido no local",
    "ENDERECO_INEXISTENTE": "Endereço inexistente ou insuficiente",
}
EFETIVAM = frozenset({"ENTREGUE", "ENTREGUE_PROCURADOR", "RECUSOU"})

# A PEÇA DA CERTIDÃO POSITIVA QUE CADA RESULTADO ESCOLHE — a regra é daqui, a
# frase é do catálogo.
PECA_DO_RESULTADO = {
    "ENTREGUE": "entregue",
    "ENTREGUE_PROCURADOR": "procurador",
    "RECUSOU": "recusou",
}

# OS TURNOS, para dizer o que é «horário alternado» (art. 987 §2). A norma não
# define; a régua escrita aqui é: o dia de diligência (6h às 20h, art. 986 §4)
# partido em três, e duas idas seguidas nunca no mesmo turno. Ir sempre às 9h
# seria ir três vezes na hora em que o destinatário trabalha — que é o que a
# alternância existe para evitar.
TURNOS = (("MANHA", "06:00", "11:59"), ("TARDE", "12:00", "17:59"),
          ("NOITE", "18:00", "20:00"))
NOME_DO_TURNO = {"MANHA": "manhã", "TARDE": "tarde", "NOITE": "noite"}

HORA_MAIS_CEDO = "06:00"
HORA_MAIS_TARDE = "20:00"
DIAS_PARA_A_PRIMEIRA = 10        # art. 987, caput
DIAS_PARA_AVERBAR = 30           # art. 987, § 1º
IDAS_PARA_A_NEGATIVA = 3         # art. 987, § 2º

# OS ITENS, conferidos na tabela de 2026 (`tests/custas_reais.json`):
#   15.8.1    diligência em zona urbana, por destinatário, até 3 — R$ 31,14
#   15.8.1.1  acima de 3, por diligência extra solicitada      — R$ 29,06
#   15.8.1.2  diligência em zona rural, cobrada do apresentante — R$ 2,95
#   15.8.2    certidão à margem do registro, por destinatário   — R$ 47,84
ITEM_DILIGENCIA_URBANA = "15.8.1"
ITEM_DILIGENCIA_EXTRA = "15.8.1.1"
ITEM_DILIGENCIA_RURAL = "15.8.1.2"
ITEM_CERTIDAO = "15.8.2"

CAMINHO_DILIGENCIA_URBANA = "/selo/rtdpj/diligencia/zona-urbana"
CAMINHO_DILIGENCIA_RURAL = "/selo/rtdpj/diligencia/fora-zona-urbana"
CAMINHO_DILIGENCIA_EXTRA = "/selo/rtdpj/acima-tres-diligencias"
CAMINHO_CERTIDAO = "/selo/rtdpj/certidao-notificacao"

# OS PAPÉIS. Os dois são do catálogo (Administrativo → Modelos): o que a
# certidão afirma é do oficial que a assina.
CHAVE_POSITIVA = "RTD_CERTIDAO_NOTIFICACAO_POSITIVA"
CHAVE_NEGATIVA = "RTD_CERTIDAO_NOTIFICACAO_NEGATIVA"
CHAVE_DO_TIPO = {"POSITIVA": CHAVE_POSITIVA, "NEGATIVA": CHAVE_NEGATIVA}
CLAROS = {
    CHAVE_POSITIVA: ("onde", "destinatario", "documento", "endereco",
                     "data_da_notificacao", "hora_da_notificacao", "como",
                     "cidade", "data_extenso"),
    CHAVE_NEGATIVA: ("onde", "destinatario", "documento", "endereco",
                     "quantas", "diligencias", "cidade", "data_extenso"),
}


# ------------------------------------------------------------ as réguas puras


def _texto(v: Any) -> str:
    return str(v or "").strip()


def _dia(v: Any) -> date:
    try:
        return date.fromisoformat(_texto(v)[:10])
    except ValueError as erro:
        raise NotificacaoError(
            f"Data inválida: {_texto(v) or '(vazia)'}. Use dia/mês/ano.") from erro


def _hora(v: Any) -> str:
    """`9:5` → `09:05`. Recusa o que não é hora."""
    bruto = _texto(v)[:5]
    try:
        h, m = bruto.split(":")
        h, m = int(h), int(m)
    except ValueError as erro:
        raise NotificacaoError(
            f"Hora inválida: {bruto or '(vazia)'}. Use horas:minutos.") from erro
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise NotificacaoError(f"Hora inválida: {bruto}.")
    return f"{h:02d}:{m:02d}"


def br(d: Any) -> str:
    """`2026-10-19` → `19/10/2026`. Só calcula."""
    s = _texto(d)[:10]
    return f"{s[8:10]}/{s[5:7]}/{s[0:4]}" if len(s) == 10 else s


def turno(hora: Any) -> str:
    """O turno daquela hora — MANHA, TARDE ou NOITE. Só calcula."""
    h = _hora(hora)
    for nome, de, ate in TURNOS:
        if de <= h <= ate:
            return nome
    raise NotificacaoError(
        f"Às {h} não se faz diligência: a norma permite das 6h às 20h "
        f"(CN-MA, art. 986, § 4º).")


def feriados_do_ano(ano: int, locais: Iterable[date] = ()) -> set[date]:
    """Os feriados que impedem a diligência: os nacionais (a régua do núcleo,
    `ri_schema.feriados_nacionais`) e os locais da configuração."""
    from ri_schema import feriados_nacionais
    return feriados_nacionais(ano) | set(locais)


def conferir_dia_e_hora(dia: Any, hora: Any, *,
                        feriados_locais: Iterable[date] = ()) -> tuple[str, str, str]:
    """A ida pode ter sido naquele dia e hora? Devolve `(data, hora, turno)`.

    **Domingo e feriado, nunca; e só das 6h às 20h** (CN-MA, art. 986, § 4º).
    O sábado vale: a norma diz «diariamente … exceto aos domingos e feriados».
    """
    d = _dia(dia)
    h = _hora(hora)
    if d.weekday() == 6:
        raise NotificacaoError(
            f"{br(d.isoformat())} é domingo, e não se faz diligência de "
            f"notificação no domingo (CN-MA, art. 986, § 4º).")
    if d in feriados_do_ano(d.year, feriados_locais):
        raise NotificacaoError(
            f"{br(d.isoformat())} é feriado, e não se faz diligência de "
            f"notificação no feriado (CN-MA, art. 986, § 4º). Se não é feriado "
            f"nesta comarca, corrija a lista em Administrativo → Configurações.")
    if not (HORA_MAIS_CEDO <= h <= HORA_MAIS_TARDE):
        raise NotificacaoError(
            f"Às {h} não se faz diligência: a norma permite das 6h às 20h "
            f"(CN-MA, art. 986, § 4º).")
    return d.isoformat(), h, turno(h)


def prazo_da_primeira(apresentado_em: Any) -> str:
    """Até quando a primeira ida tem de acontecer (art. 987, caput). Só calcula.

    **Dias corridos**: a norma diz «prazo máximo de 10 (dez) dias», sem «úteis»,
    e onde ela quer dia útil ela escreve.
    """
    return (_dia(apresentado_em) + timedelta(days=DIAS_PARA_A_PRIMEIRA)).isoformat()


def averbar_ate(resultado_em: Any) -> str | None:
    """Até quando o resultado se averba (art. 987, § 1º). Só calcula."""
    if not _texto(resultado_em):
        return None
    return (_dia(resultado_em) + timedelta(days=DIAS_PARA_AVERBAR)).isoformat()


def negativa_cabe(idas: list[dict]) -> str:
    """Já se pode certificar o resultado negativo? ``""`` se sim; senão, o porquê.

    **Três idas frustradas, no mínimo, em dias E horários alternados** (CN-MA,
    art. 987, § 2º). A régua desta casa para «alternado», escrita porque a norma
    não a escreve: cada ida frustrada em DIA DIFERENTE das outras, e duas idas
    seguidas NUNCA no mesmo turno (`TURNOS`). Três idas às 9h de três dias
    diferentes não alternam o horário; três idas no mesmo dia não alternam o dia.
    """
    frustradas = sorted((i for i in idas if i["resultado"] not in EFETIVAM),
                        key=lambda i: (i["data"], i["hora"], i["numero"]))
    if len(frustradas) < IDAS_PARA_A_NEGATIVA:
        return (f"O resultado negativo só se certifica depois de no mínimo "
                f"{IDAS_PARA_A_NEGATIVA} diligências frustradas (CN-MA, art. 987, "
                f"§ 2º). Há {len(frustradas)}.")
    dias = [i["data"] for i in frustradas]
    if len(set(dias)) < len(dias):
        return ("Há duas diligências frustradas no mesmo dia, e a norma pede "
                "dias alternados (CN-MA, art. 987, § 2º): faça a próxima noutro "
                "dia.")
    for antes, depois in zip(frustradas, frustradas[1:]):
        if antes["turno"] == depois["turno"]:
            return (f"As diligências {antes['numero']}ª e {depois['numero']}ª "
                    f"foram as duas pela {NOME_DO_TURNO[antes['turno']]}, e a "
                    f"norma pede horários alternados (CN-MA, art. 987, § 2º): "
                    f"faça a próxima noutro turno.")
    return ""


def item_da_ida(numero: int, zona: str) -> tuple[str, str] | None:
    """O item e o caminho do selo que a ida de número `numero` faz nascer.

    `None` para a segunda e a terceira: o 15.8.1 da primeira as cobre («por
    destinatário, até o limite de 03»). Da quarta em diante, uma diligência
    extra cada (15.8.1.1, art. 987, § 3º).
    """
    if numero == 1:
        if zona == "RURAL":
            return ITEM_DILIGENCIA_RURAL, CAMINHO_DILIGENCIA_RURAL
        return ITEM_DILIGENCIA_URBANA, CAMINHO_DILIGENCIA_URBANA
    if numero <= IDAS_PARA_A_NEGATIVA:
        return None
    return ITEM_DILIGENCIA_EXTRA, CAMINHO_DILIGENCIA_EXTRA


def alertas(n: dict, *, hoje: str) -> list[str]:
    """O que está atrasado nesta notificação, em frase. Só calcula.

    GET não escreve: o alerta é conta feita na hora da tela, e não marca no
    banco.
    """
    saida = []
    primeira = n.get("primeira_ida")
    if n["situacao"] == "EM_DILIGENCIA" and not primeira and hoje > n["prazo_primeira"]:
        saida.append(f"A primeira diligência devia ter sido feita até "
                     f"{br(n['prazo_primeira'])} (CN-MA, art. 987).")
    if primeira and primeira > n["prazo_primeira"]:
        saida.append(f"A primeira diligência foi feita em {br(primeira)}, depois "
                     f"do prazo de {br(n['prazo_primeira'])} (CN-MA, art. 987).")
    limite = averbar_ate(n.get("resultado_em"))
    if limite and not n.get("averbacao_ato_id") and hoje > limite:
        saida.append(f"O resultado devia estar averbado à margem do registro "
                     f"até {br(limite)} (CN-MA, art. 987, § 1º).")
    if n.get("selos_suspensos"):
        saida.append("Há selo suspenso nesta notificação: sele de novo na ficha.")
    return saida


# --------------------------------------------------------------- as consultas


def _destino(con: Any, *, titulo_id: Any = None, registro_id: Any = None) -> dict:
    """O título e/ou o registro de onde a notificação nasce. Recusa o que não é RTD."""
    bd = banco(con)
    titulo = registro = None
    if _texto(titulo_id):
        titulo = bd.um("SELECT * FROM rg_titulos WHERE id = %s", (int(titulo_id),))
        if not titulo:
            raise NotificacaoError("Título não encontrado.")
        if int(titulo["atribuicao"]) != RTD:
            raise NotificacaoError(
                "Este título é do RCPJ. Notificação extrajudicial é do Registro "
                "de Títulos e Documentos.")
        if titulo["registro_id"] and not _texto(registro_id):
            registro_id = titulo["registro_id"]
    if _texto(registro_id):
        registro = bd.um("SELECT * FROM rg_registros WHERE id = %s",
                         (int(registro_id),))
        if not registro:
            raise NotificacaoError("Registro não encontrado.")
        if int(registro["atribuicao"]) != RTD:
            raise NotificacaoError(
                "Este registro é do RCPJ. Notificação extrajudicial é do "
                "Registro de Títulos e Documentos.")
    if not titulo and not registro:
        raise NotificacaoError(
            "Diga de que título ou de que registro do RTD é a notificação.")
    return {"titulo": titulo, "registro": registro}


def registro_da(con: Any, n: dict) -> dict | None:
    """O registro da notificação — o dela, ou o que o título dela ganhou depois."""
    bd = banco(con)
    rid = n.get("registro_id")
    if not rid and n.get("titulo_id"):
        rid = bd.valor("SELECT registro_id FROM rg_titulos WHERE id = %s",
                       (int(n["titulo_id"]),))
    if not rid:
        return None
    return bd.um(
        """SELECT r.*, a.folha AS folha_do_registro,
                  (SELECT numero FROM nu_livros WHERE id = a.livro_id) AS livro_numero
             FROM rg_registros r
             LEFT JOIN rg_atos a ON a.registro_id = r.id AND a.tipo = 'REGISTRO'
            WHERE r.id = %s
            ORDER BY a.id LIMIT 1""", (int(rid),))


def idas(con: Any, notificacao_id: int) -> list[dict]:
    return banco(con).ler(
        "SELECT * FROM rg_notificacao_idas WHERE notificacao_id = %s "
        "ORDER BY numero, id", (int(notificacao_id),))


def diligencias(con: Any, notificacao_id: int) -> list[dict]:
    return banco(con).ler(
        "SELECT * FROM rg_notificacao_diligencias WHERE notificacao_id = %s "
        "ORDER BY id", (int(notificacao_id),))


def certidoes(con: Any, notificacao_id: int) -> list[dict]:
    return banco(con).ler(
        "SELECT * FROM rg_notificacao_certidoes WHERE notificacao_id = %s "
        "ORDER BY id", (int(notificacao_id),))


def notificacao(con: Any, notificacao_id: int) -> dict:
    n = banco(con).um("SELECT * FROM rg_notificacoes WHERE id = %s",
                      (int(notificacao_id),))
    if not n:
        raise NotificacaoError("Notificação não encontrada.")
    return n


def _preso(con: Any, notificacao_id: int) -> dict:
    """A notificação com a linha presa até o fim da transação. ESCREVE.

    Quem confere a situação e o número da ida e grava em seguida lê por aqui:
    duas idas lançadas ao mesmo tempo achariam as duas o mesmo número.
    """
    bd = banco(con)
    bd._escrita()
    n = bd.um("SELECT * FROM rg_notificacoes WHERE id = %s FOR UPDATE",
              (int(notificacao_id),))
    if not n:
        raise NotificacaoError("Notificação não encontrada.")
    return n


def lista(con: Any, *, hoje: str, situacao: Any = None,
          registro_id: Any = None) -> list[dict]:
    """As notificações, com o que falta e o que atrasou. Só LÊ."""
    onde, args = [], []
    if _texto(situacao):
        onde.append("n.situacao = %s")
        args.append(_texto(situacao))
    if _texto(registro_id):
        onde.append("(n.registro_id = %s OR t.registro_id = %s)")
        args += [int(registro_id), int(registro_id)]
    sql = f"""
        SELECT n.*, t.numero AS titulo_numero,
               COALESCE(n.registro_id, t.registro_id) AS registro_efetivo,
               (SELECT min(i.data) FROM rg_notificacao_idas i
                 WHERE i.notificacao_id = n.id) AS primeira_ida,
               (SELECT count(*) FROM rg_notificacao_idas i
                 WHERE i.notificacao_id = n.id) AS quantas_idas,
               (SELECT count(*) FROM rg_notificacao_diligencias d
                 WHERE d.notificacao_id = n.id
                   AND d.selo_situacao <> 'SELADO') AS selos_suspensos
          FROM rg_notificacoes n
          LEFT JOIN rg_titulos t ON t.id = n.titulo_id
         {'WHERE ' + ' AND '.join(onde) if onde else ''}
         ORDER BY n.apresentado_em DESC, n.id DESC
         LIMIT 300"""
    saida = []
    for linha in banco(con).ler(sql, args):
        linha = dict(linha)
        linha["quantas_idas"] = int(linha["quantas_idas"] or 0)
        linha["selos_suspensos"] = int(linha["selos_suspensos"] or 0)
        linha["alertas"] = alertas(linha, hoje=hoje)
        saida.append(linha)
    return saida


# ----------------------------------------------------------------- a escrita


def abrir(con: Any, *, destinatario_nome: Any, endereco: Any, agora: str,
          titulo_id: Any = None, registro_id: Any = None,
          destinatario_documento: Any = None, zona: Any = "URBANA",
          distancia_km: Any = None, observacao: Any = None,
          usuario: Any = None) -> int:
    """Abre a notificação de UM destinatário. ESCREVE.

    A data da apresentação é a do título (é dela que corre o prazo da primeira
    diligência — art. 987); sem título, a do registro.
    """
    nome = _texto(destinatario_nome)
    if len(nome) < 3:
        raise NotificacaoError("Escreva o nome de quem se notifica.")
    lugar = _texto(endereco)
    if len(lugar) < 5:
        raise NotificacaoError(
            "Escreva o endereço onde a diligência vai ser feita — é ele que a "
            "certidão diz.")
    z = _texto(zona).upper() or "URBANA"
    if z not in ZONAS:
        raise NotificacaoError("A zona é urbana ou rural.")
    km = None
    if z == "RURAL":
        try:
            km = int(_texto(distancia_km))
        except ValueError:
            km = 0
        if km < 1:
            raise NotificacaoError(
                "Na zona rural a diligência se cobra pela distância (item "
                "15.8.1.2): informe quantos quilômetros.")
    origem = _destino(con, titulo_id=titulo_id, registro_id=registro_id)
    titulo, registro = origem["titulo"], origem["registro"]
    apresentado = (_texto(titulo["data_apresentacao"])[:10] if titulo
                   else _texto(registro["criado_em"])[:10])
    novo = banco(con).escrever(
        """INSERT INTO rg_notificacoes(titulo_id, registro_id,
               destinatario_nome, destinatario_documento, endereco, zona,
               distancia_km, apresentado_em, prazo_primeira, observacao,
               criado_em, criado_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           RETURNING id""",
        (int(titulo["id"]) if titulo else None,
         int(registro["id"]) if registro else None,
         nome, _texto(destinatario_documento) or None, lugar, z, km,
         apresentado, prazo_da_primeira(apresentado),
         _texto(observacao) or None, agora, _texto(usuario) or None))
    return int(novo[0]["id"])


def registrar_ida(con: Any, notificacao_id: int, *, data: Any, hora: Any,
                  resultado: Any, agora: str, endereco: Any = None,
                  observacao: Any = None, a_pedido: bool = False,
                  feriados_locais: Iterable[date] = (),
                  usuario: Any = None) -> dict:
    """Registra uma ida ao destinatário. ESCREVE.

    Devolve `{"ida_id", "numero", "diligencia_id"}` — `diligencia_id` é a
    diligência COBRADA que esta ida fez nascer (a primeira, e cada extra), ou
    `None` quando a ida está coberta pela primeira. Quem chama pede o selo
    dela DEPOIS da transação.
    """
    n = _preso(con, notificacao_id)
    if n["situacao"] != "EM_DILIGENCIA":
        raise NotificacaoError(
            f"Esta notificação já tem resultado ({SITUACOES[n['situacao']]}): "
            f"não se faz outra diligência.")
    r = _texto(resultado).upper()
    if r not in RESULTADOS:
        raise NotificacaoError("Diga o que a diligência achou.")
    dia, h, t = conferir_dia_e_hora(data, hora, feriados_locais=feriados_locais)
    if dia < _texto(n["apresentado_em"])[:10]:
        raise NotificacaoError(
            f"A diligência não pode ser anterior à apresentação "
            f"({br(n['apresentado_em'])}).")
    if dia > _texto(agora)[:10]:
        raise NotificacaoError(
            "Registra-se a diligência que já foi feita: a data é futura.")
    obs = _texto(observacao)
    if r == "ENTREGUE_PROCURADOR" and len(obs) < 5:
        raise NotificacaoError(
            "Entrega a procurador vale só com poderes específicos para receber "
            "notificações (CN-MA, art. 992): escreva na observação quem é e de "
            "que instrumento vêm os poderes.")
    bd = banco(con)
    numero = int(bd.valor(
        "SELECT count(*) AS n FROM rg_notificacao_idas WHERE notificacao_id = %s",
        (int(notificacao_id),)) or 0) + 1
    if numero > IDAS_PARA_A_NEGATIVA and not a_pedido:
        raise NotificacaoError(
            f"Já houve {IDAS_PARA_A_NEGATIVA} diligências. A {numero}ª só se "
            f"faz a pedido do apresentante, e é cobrada à parte (CN-MA, art. "
            f"987, § 3º; item 15.8.1.1): marque que ele pediu.")
    item = item_da_ida(numero, n["zona"])
    if item:
        codigo, caminho = item
        quantidade = (int(n["distancia_km"] or 1)
                      if codigo == ITEM_DILIGENCIA_RURAL else 1)
        diligencia_id = int(bd.escrever(
            """INSERT INTO rg_notificacao_diligencias(notificacao_id, codigo_tj,
                   caminho, quantidade, idas_cobertas, criado_em, criado_por)
               VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (int(notificacao_id), codigo, caminho, quantidade,
             IDAS_PARA_A_NEGATIVA if numero == 1 else 1, agora,
             _texto(usuario) or None))[0]["id"])
        cobradora, nova = diligencia_id, diligencia_id
    else:
        cobradora = int(bd.valor(
            """SELECT id FROM rg_notificacao_diligencias
                WHERE notificacao_id = %s ORDER BY id LIMIT 1""",
            (int(notificacao_id),)))
        nova = None
    ida_id = int(bd.escrever(
        """INSERT INTO rg_notificacao_idas(notificacao_id, diligencia_id, numero,
               data, hora, turno, endereco, resultado, observacao, a_pedido,
               feita_por, criado_em)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (int(notificacao_id), cobradora, numero, dia, h, t,
         _texto(endereco) or n["endereco"], r, obs or None,
         1 if a_pedido else 0, _texto(usuario) or None, agora))[0]["id"])
    if r in EFETIVAM:
        bd.escrever(
            """UPDATE rg_notificacoes SET situacao = 'POSITIVA',
                   resultado_em = %s, resultado_por = %s WHERE id = %s""",
            (dia, _texto(usuario) or None, int(notificacao_id)))
    return {"ida_id": ida_id, "numero": numero, "diligencia_id": nova,
            "positiva": r in EFETIVAM}


def certificar_negativa(con: Any, notificacao_id: int, *, agora: str,
                        usuario: Any = None) -> None:
    """Dá o resultado NEGATIVO, se a norma deixa (art. 987, § 2º). ESCREVE."""
    n = _preso(con, notificacao_id)
    if n["situacao"] != "EM_DILIGENCIA":
        raise NotificacaoError(
            f"Esta notificação já tem resultado ({SITUACOES[n['situacao']]}).")
    motivo = negativa_cabe(idas(con, notificacao_id))
    if motivo:
        raise NotificacaoError(motivo)
    banco(con).escrever(
        """UPDATE rg_notificacoes SET situacao = 'NEGATIVA', resultado_em = %s,
               resultado_por = %s WHERE id = %s""",
        (_texto(agora)[:10], _texto(usuario) or None, int(notificacao_id)))


def _onde(registro: dict) -> str:
    """«sob o nº 12 do Livro B do Registro de Títulos e Documentos»."""
    import livro_nucleo as LN
    try:
        livro = LN.serie(registro["serie"]).nome
    except Exception:                                    # noqa: BLE001
        livro = f"Livro {registro['serie']}"
    numero = registro.get("numero")
    volume = _texto(registro.get("livro_numero") or registro.get("volume"))
    partes = [f"sob o nº {numero}" if numero else "", f"do {livro}"]
    if volume:
        partes.append(f"(volume {volume})")
    return " ".join(p for p in partes if p)


def _documento(n: dict) -> str:
    doc = _texto(n.get("destinatario_documento"))
    return f", CPF/CNPJ {doc}" if doc else ""


def proximo_numero(con: Any, ano: int) -> int:
    """O número da certidão no exercício. A trava vem ANTES de ler o maior."""
    bd = banco(con)
    bd.travar("rg_notificacao_certidoes.numero")
    maior = bd.valor(
        "SELECT max(numero) AS n FROM rg_notificacao_certidoes WHERE ano = %s",
        (int(ano),))
    return int(maior or 0) + 1


def hash_certidao(numero: int, ano: int, tipo: str, teor: str, agora: str) -> str:
    base = f"RTD-NOTIFICACAO|{numero}|{ano}|{tipo}|{agora}|{teor}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def montar_teor(con: Any, n: dict, registro: dict, lista_de_idas: list[dict], *,
                sv: dict, data_extenso: str) -> tuple[str, str]:
    """`(tipo, teor)` da certidão, pelo papel do catálogo. Só LÊ.

    Com `con`: vale o ajuste da casa (`texto_do_papel`). A regra — que peça
    entra, e a lista das idas — é daqui; a frase é do papel.
    """
    tipo = n["situacao"]
    chave = CHAVE_DO_TIPO[tipo]
    comum = {"onde": _onde(registro), "destinatario": n["destinatario_nome"],
             "documento": _documento(n), "endereco": n["endereco"],
             "cidade": _texto(sv.get("ri_cidade")) or "—",
             "data_extenso": data_extenso}
    if tipo == "POSITIVA":
        efetiva = next(i for i in lista_de_idas if i["resultado"] in EFETIVAM)
        peca = f"{chave}__{PECA_DO_RESULTADO[efetiva['resultado']]}"
        valores = {**comum, "data_da_notificacao": br(efetiva["data"]),
                   "hora_da_notificacao": efetiva["hora"],
                   "como": MODELOS.texto_do_papel(con, peca)}
    else:
        frase = MODELOS.texto_do_papel(con, f"{chave}__ida")
        frustradas = [i for i in lista_de_idas if i["resultado"] not in EFETIVAM]
        itens = [MODELOS.preencher(f"{chave}__ida", frase, {
            "ordem": i["numero"], "data": br(i["data"]), "hora": i["hora"],
            "resultado": RESULTADOS[i["resultado"]].lower()}) for i in frustradas]
        valores = {**comum, "quantas": len(frustradas),
                   "diligencias": "; ".join(itens)}
    texto = MODELOS.texto_do_papel(con, chave)
    return tipo, MODELOS.preencher(chave, texto, valores)


def emitir_certidao(con: Any, notificacao_id: int, *, agora: str, sv: dict,
                    data_extenso: str, usuario: Any = None) -> dict:
    """Emite a certidão de notificação, positiva ou negativa. ESCREVE.

    **NÃO SE DÁ ANTES DO REGISTRO** (CN-MA, art. 988, § 2º): a notificação que
    nasceu do título protocolado espera o título ser registrado. E não sai com
    diligência de selo suspenso: certidão de diligência que não tem selo
    certificaria ato que a fiscalização não vê.

    A trava do número vem ANTES da linha da notificação, como em
    `rg_livro_contabil.autenticar` (assunto primeiro, linha depois): a regra
    de ordem é uma só na casa, e quem a segue não se cruza com quem a segue.
    `proximo_numero` pega a mesma trava de novo — na mesma transação, é a
    mesma.
    """
    banco(con).travar("rg_notificacao_certidoes.numero")
    n = _preso(con, notificacao_id)
    if n["situacao"] not in ("POSITIVA", "NEGATIVA"):
        raise NotificacaoError(
            "A notificação ainda está em diligência: a certidão diz o "
            "resultado, e ele ainda não existe.")
    registro = registro_da(con, n)
    if not registro:
        raise NotificacaoError(
            "O documento ainda não foi registrado, e não se fornece certidão "
            "de notificação antes do registro (CN-MA, art. 988, § 2º). Registre "
            "o título primeiro.")
    pendentes = [d for d in diligencias(con, notificacao_id)
                 if d["selo_situacao"] != "SELADO"]
    if pendentes:
        raise NotificacaoError(
            "Há diligência com o selo suspenso nesta notificação: sele-a de "
            "novo antes de certificar.")
    if certidoes(con, notificacao_id):
        raise NotificacaoError(
            "A certidão desta notificação já foi emitida: reimprima a que existe.")
    try:
        tipo, teor = montar_teor(con, n, registro, idas(con, notificacao_id),
                                 sv=sv, data_extenso=data_extenso)
    except MODELOS.ModeloError as erro:
        raise NotificacaoError(str(erro)) from erro
    ano = int(_texto(agora)[:4])
    numero = proximo_numero(con, ano)
    impressao = hash_certidao(numero, ano, tipo, teor, agora)
    novo = banco(con).escrever(
        """INSERT INTO rg_notificacao_certidoes(notificacao_id, numero, ano,
               tipo, teor, hash_certidao, emitida_em, emitida_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (int(notificacao_id), numero, ano, tipo, teor, impressao, agora,
         _texto(usuario) or None))
    return {"certidao_id": int(novo[0]["id"]), "numero": numero, "ano": ano,
            "tipo": tipo, "teor": teor, "hash": impressao,
            "registro": registro}


def averbar(con: Any, notificacao_id: int, *, sv: dict, agora: str,
            data_extenso: str, usuario: Any = None) -> dict:
    """Averba o resultado à margem do registro, pela certidão. ESCREVE.

    **A AVERBAÇÃO É A DO RTD QUE JÁ EXISTE** (`rg_registro.lancar_averbacao`):
    ato próprio, em folha nova, como todo ato deste livro (`rg_schema`). O
    teor é a peça `…__averbacao` do papel da certidão. Sem certidão não se
    averba: o que se averba é a certidão (CN-MA, art. 986, § 2º).
    """
    import rg_registro as RG
    n = _preso(con, notificacao_id)
    if n["averbacao_ato_id"]:
        raise NotificacaoError("O resultado desta notificação já está averbado.")
    emitidas = certidoes(con, notificacao_id)
    if not emitidas:
        raise NotificacaoError(
            "Emita a certidão de notificação primeiro: é ela que se averba à "
            "margem do registro (CN-MA, art. 986, § 2º).")
    registro = registro_da(con, n)
    certidao = emitidas[-1]
    lista_de_idas = idas(con, notificacao_id)
    chave = f"{CHAVE_DO_TIPO[certidao['tipo']]}__averbacao"
    valores = {"destinatario": n["destinatario_nome"], "documento": _documento(n),
               "endereco": n["endereco"],
               "certidao": f"{certidao['numero']}/{certidao['ano']}",
               "cidade": _texto(sv.get("ri_cidade")) or "—",
               "data_extenso": data_extenso}
    if certidao["tipo"] == "POSITIVA":
        efetiva = next(i for i in lista_de_idas if i["resultado"] in EFETIVAM)
        valores["data_da_notificacao"] = br(efetiva["data"])
    else:
        valores["quantas"] = len([i for i in lista_de_idas
                                  if i["resultado"] not in EFETIVAM])
    try:
        teor = MODELOS.preencher(chave, MODELOS.texto_do_papel(con, chave), valores)
    except MODELOS.ModeloError as erro:
        raise NotificacaoError(str(erro)) from erro
    lugar = RG.lancar_averbacao(con, int(registro["id"]), teor=teor, sv=sv,
                                agora=agora, data_extenso=data_extenso,
                                usuario=_texto(usuario) or None)
    banco(con).escrever(
        """UPDATE rg_notificacoes SET averbacao_ato_id = %s, averbada_em = %s,
               averbada_por = %s WHERE id = %s""",
        (int(lugar["ato_id"]), agora, _texto(usuario) or None,
         int(notificacao_id)))
    return lugar


# ------------------------------------------------------------------- o selo


def envelope(*, caminho: str, codigo_tj: str, escrevente: Any, versao_tabela: Any,
             destinatario: dict, quantidade: int = 1,
             registro: dict | None = None) -> dict:
    """O pedido de selo da diligência ou da certidão. Só calcula.

    **FORMA POR ANALOGIA, A CONFERIR NA HOMOLOGAÇÃO** — ver o cabeçalho. A
    base é o `atos-em-geral` do RTD (`ato_selado.envelope_do_rtdpj`); a
    certidão acrescenta o livro e o número do registro, que o nome do esquema
    dela (`RtdpjComMatriculaRegistroAverbacao`) pede.
    """
    import ato_selado as AS
    dados = AS.envelope_do_rtdpj(
        caminho=AS.CAMINHO_RTDPJ_GERAL, codigo_tj=codigo_tj,
        escrevente=escrevente, versao_tabela=versao_tabela,
        partes=[destinatario], quantidade=quantidade)
    if caminho == CAMINHO_CERTIDAO and registro:
        dados["livro"] = _texto(registro.get("livro_numero") or registro["serie"])
        dados["registroAverbacao"] = _texto(registro.get("numero"))
    return dados


def preco(con: Any, codigo_tj: str, *, quantidade: int = 1,
          data: Any = None) -> dict:
    """Quanto custa o item, pela tabela importada. Só LÊ. Nunca estoura.

    O item que a tabela não tem aparece COM o motivo, e não some: sumir seria
    cobrar a menos sem ninguém ver (a régua de `ato_selado.receita_de_custas`).
    """
    import ato_selado as AS
    servico = AS.servico_do_codigo_tj(con, codigo_tj)
    if not servico:
        return {"codigo_tj": codigo_tj, "preco": None,
                "motivo": "não está na tabela de emolumentos importada"}
    try:
        conta = AS.calcular_custas(con, servico=servico["codigo"], data=data,
                                   quantidade=quantidade)
    except AS.AtoError as erro:
        return {"codigo_tj": codigo_tj, "servico": servico["codigo"],
                "preco": None, "motivo": str(erro)}
    return {"codigo_tj": codigo_tj, "servico": servico["codigo"],
            "descricao": servico["descricao"],
            "preco": conta["total_devido_centavos"], "motivo": None}


def __getattr__(nome: str):
    """O texto de fábrica dos papéis, pelo nome — lido da base, e não daqui."""
    if nome in ("MODELO_CERTIDAO_NOTIFICACAO_POSITIVA",
                "MODELO_CERTIDAO_NOTIFICACAO_NEGATIVA"):
        return MODELOS.constante_antiga(__name__, nome)
    raise AttributeError(f"module {__name__!r} has no attribute {nome!r}")


# ------------------------------------------------------------------- as telas


def registrar_rotas(app, db, login_required, roles_required, audit) -> None:
    """Pendura as telas da notificação no app já construído.

    **OS NOMES COMEÇAM COM `rcpj_rtd`**: a guarda de módulo decide pelo prefixo
    (`modulos.modulo_da_tela`), e rota fora dele sairia do menu e do alcance
    do RCPJ/RTD.
    """
    from flask import abort, flash, redirect, render_template, request, url_for

    import ato_selado as AS
    import livro_nucleo as LN
    import rg_registro as RG
    import rg_web as RGW
    import selo_robo as SR
    from ri_schema import ler_feriados_locais
    from ri_web import data_por_extenso
    from serventia import dados as dados_serventia

    QUEM_LE = (*RGW.QUEM_OPERA, "AUDITOR")
    RECUSAS = (NotificacaoError, RG.RgError, LN.LivroError, AS.AtoError,
               MODELOS.ModeloError)
    usuario_nome = app.extensions["usuario_nome"]

    # O conferidor dos dois papéis (CHAVES): a tela de Modelos recusa o claro
    # que a certidão não preenche, e quem grava confere com a mesma régua.
    import modelos_elementos as ELEM
    conferidores = app.extensions.setdefault("conferidores_de_modelo", {})
    for _chave, _claros in CLAROS.items():
        conferidores[_chave] = (
            lambda corpo, _c=_claros: MODELOS.conferir_claros(corpo, _c))
        ELEM.CONFERIDORES[_chave] = conferidores[_chave]

    def agora() -> str:
        return db.now()

    def hoje() -> str:
        return agora()[:10]

    def sv() -> dict:
        return dados_serventia(db.get_settings)

    def extenso() -> str:
        return data_por_extenso(date.fromisoformat(hoje()))

    def _campo(nome: str) -> str:
        return (request.form.get(nome) or "").strip()

    def _caixa_aberto(con) -> dict | None:
        return banco(con).um(
            """SELECT * FROM cx_caixas
                WHERE operador_nome = %s AND situacao = 'ABERTO'
                ORDER BY data DESC, id LIMIT 1""", (usuario_nome(),))

    def _cobrar_se_pedido(con, tabela: str, ato_id: int, codigo_tj: str,
                          quantidade: int) -> str:
        """Lança o item no caixa, se o operador marcou. ESCREVE.

        A régua de `rg_web._cobrar_se_pedido`: sem caixa aberto não se cobra —
        lançamento sem caixa não aparece na gaveta de ninguém.
        """
        if not request.form.get("cobrar"):
            return ""
        caixa = _caixa_aberto(con)
        if not caixa:
            raise AS.AtoError(
                "Você não tem caixa aberto, e sem caixa o lançamento não "
                "aparece na conferência do dia. Abra o caixa em "
                "Administrativo → Caixa — ou registre sem marcar cobrança, e "
                "cobre depois.")
        servico = AS.servico_do_codigo_tj(con, codigo_tj)
        if not servico:
            raise AS.AtoError(
                f"O item {codigo_tj} não está na tabela de emolumentos "
                f"importada: não há como lançar o valor.")
        r = AS.cobrar(con, tabela=tabela, ato_id=ato_id,
                      servico=int(servico["codigo"]), agora=agora(),
                      hoje=hoje(), hora=agora()[11:16],
                      caixa_id=int(caixa["id"]), quantidade=quantidade,
                      pagador=_campo("pagador") or None,
                      descricao=f"NOTIFICAÇÃO RTD — {tabela}")
        from caixa_schema import reais
        return f" Lançado no caixa: R$ {reais(r['total_centavos'])}."

    def _selar(tabela: str, ato_id: int) -> str:
        """Pede o selo da diligência ou da certidão, DEPOIS do ato. FALA COM A REDE.

        Falhou, SUSPENDE (regra da casa, 16/09/2026): a linha fica `SUSPENSO`
        com o motivo, a ficha o mostra e oferece selar de novo. Nada de número
        inventado.
        """
        if not SR.pode_selar_automatico():
            return SR.recado_pendente_selo()
        with db.connect() as con:
            bd = banco(con)
            linha = bd.um(f"SELECT * FROM {tabela} WHERE id = %s", (int(ato_id),))
            n = notificacao(con, int(linha["notificacao_id"]))
            registro = registro_da(con, n) if tabela.endswith("certidoes") else None
        if tabela == "rg_notificacao_certidoes":
            caminho, codigo, quantidade = CAMINHO_CERTIDAO, ITEM_CERTIDAO, 1
        else:
            caminho, codigo = linha["caminho"], linha["codigo_tj"]
            quantidade = int(linha["quantidade"] or 1)
        versao = AS.versao_da_tabela_de_custas(
            caminho, db.get_setting("selo_tabela_custas_em", ""))
        if not versao:
            resposta = {"selado": False, "motivo": (
                "falta dizer de que data é a tabela de custas em vigor, em "
                "Administrativo → Configurações")}
        else:
            dados = envelope(
                caminho=caminho, codigo_tj=codigo, escrevente=usuario_nome(),
                versao_tabela=versao, quantidade=quantidade, registro=registro,
                destinatario={"nome": n["destinatario_nome"],
                              "documento": n["destinatario_documento"] or ""})
            resposta = AS.selar_o_ato_lavrado(
                db, Path(app.config["DATA_DIR"]), tabela=tabela, ato_id=ato_id,
                tipo="NOTIFICACAO", atribuicao="RTD", agora=agora(),
                cns=sv().get("ri_cns"), usuario=usuario_nome(), dados=dados,
                caminho=caminho, referencia=f"{tabela}:{int(ato_id)}")
        with db.transaction() as con:
            banco(con).escrever(
                f"""UPDATE {tabela} SET selo_situacao = %s, selo_motivo = %s
                     WHERE id = %s""",
                ("SELADO" if resposta["selado"] else "SUSPENSO",
                 None if resposta["selado"] else str(resposta["motivo"]),
                 int(ato_id)))
        if resposta["selado"]:
            audit("RG_NOTIFICACAO_SELO", tabela, ato_id,
                  {"selo": resposta["numero"], "caminho": caminho})
            return f" Selo {resposta['numero']}."
        audit("RG_NOTIFICACAO_SELO_SUSPENSO", tabela, ato_id,
              {"motivo": str(resposta["motivo"]), "caminho": caminho})
        return (f" SEM SELO — o ato ficou suspenso até selar: "
                f"{resposta['motivo']}")

    @app.route("/rcpj-rtd/notificacoes")
    @login_required
    @roles_required(*QUEM_LE)
    def rcpj_rtd_notificacoes():
        """A lista, com os prazos. GET não escreve: o alerta é conta da hora."""
        situacao = (request.args.get("situacao") or "").strip()
        with db.connect() as con:
            linhas = lista(con, hoje=hoje(), situacao=situacao or None,
                           registro_id=request.args.get("registro_id") or None)
        return render_template("rcpj_rtd_notificacoes.html", linhas=linhas,
                               SITUACOES=SITUACOES, situacao=situacao,
                               ZONAS=ZONAS, br=br)

    @app.route("/rcpj-rtd/notificacoes/nova", methods=["GET", "POST"])
    @login_required
    @roles_required(*RGW.QUEM_OPERA)
    def rcpj_rtd_notificacao_nova():
        """Um destinatário por notificação — a tabela cobra por destinatário."""
        titulo_id = request.values.get("titulo_id") or None
        registro_id = request.values.get("registro_id") or None
        if request.method == "POST":
            try:
                with db.transaction() as con:
                    nid = abrir(
                        con, titulo_id=titulo_id, registro_id=registro_id,
                        destinatario_nome=_campo("destinatario_nome"),
                        destinatario_documento=_campo("destinatario_documento"),
                        endereco=_campo("endereco"), zona=_campo("zona"),
                        distancia_km=_campo("distancia_km"),
                        observacao=_campo("observacao"), agora=agora(),
                        usuario=usuario_nome())
            except RECUSAS as erro:
                flash(str(erro), "danger")
                return redirect(url_for("rcpj_rtd_notificacao_nova",
                                        titulo_id=titulo_id or "",
                                        registro_id=registro_id or ""))
            audit("RG_NOTIFICACAO_ABERTA", "rg_notificacoes", nid,
                  {"titulo_id": titulo_id, "registro_id": registro_id})
            flash("Notificação aberta. A primeira diligência vai até o prazo "
                  "que a ficha mostra (CN-MA, art. 987).", "success")
            return redirect(url_for("rcpj_rtd_notificacao", notificacao_id=nid))
        with db.connect() as con:
            bd = banco(con)
            titulos = bd.ler(
                """SELECT id, numero, data_apresentacao, apresentante, natureza
                     FROM rg_titulos WHERE atribuicao = %s
                    ORDER BY id DESC LIMIT 40""", (RTD,))
            registros = bd.ler(
                """SELECT id, numero, serie, natureza, requerente_nome
                     FROM rg_registros WHERE atribuicao = %s
                    ORDER BY id DESC LIMIT 40""", (RTD,))
        return render_template("rcpj_rtd_notificacao_nova.html", titulos=titulos,
                               registros=registros, titulo_id=titulo_id or "",
                               registro_id=registro_id or "", ZONAS=ZONAS)

    @app.route("/rcpj-rtd/notificacao/<int:notificacao_id>")
    @login_required
    @roles_required(*QUEM_LE)
    def rcpj_rtd_notificacao(notificacao_id: int):
        """A ficha: as idas, as diligências cobradas, o resultado e a certidão."""
        with db.connect() as con:
            try:
                n = dict(notificacao(con, notificacao_id))
            except NotificacaoError:
                abort(404)
            lista_de_idas = idas(con, notificacao_id)
            cobradas = diligencias(con, notificacao_id)
            emitidas = certidoes(con, notificacao_id)
            registro = registro_da(con, n)
            n["primeira_ida"] = min((i["data"] for i in lista_de_idas), default=None)
            n["selos_suspensos"] = sum(1 for d in cobradas
                                       if d["selo_situacao"] != "SELADO")
            proxima = item_da_ida(len(lista_de_idas) + 1, n["zona"])
            precos = {codigo: preco(con, codigo, data=hoje()) for codigo in
                      (ITEM_DILIGENCIA_URBANA, ITEM_DILIGENCIA_EXTRA,
                       ITEM_DILIGENCIA_RURAL, ITEM_CERTIDAO)}
        return render_template(
            "rcpj_rtd_notificacao.html", n=n, idas=lista_de_idas,
            diligencias=cobradas, certidoes=emitidas, registro=registro,
            alertas=alertas(n, hoje=hoje()), SITUACOES=SITUACOES,
            RESULTADOS=RESULTADOS, ZONAS=ZONAS, NOME_DO_TURNO=NOME_DO_TURNO,
            negativa_motivo=negativa_cabe(lista_de_idas),
            proxima=proxima, precos=precos, hoje=hoje(), br=br,
            averbar_ate=averbar_ate(n.get("resultado_em")),
            pede_pedido=len(lista_de_idas) >= IDAS_PARA_A_NEGATIVA)

    @app.route("/rcpj-rtd/notificacao/<int:notificacao_id>/diligencia",
               methods=["POST"])
    @login_required
    @roles_required(*RGW.QUEM_OPERA)
    def rcpj_rtd_notificacao_diligencia(notificacao_id: int):
        """Registra a ida; a que nasce cobrada pede o selo depois da transação."""
        feriados = ler_feriados_locais(db.get_setting("ri_feriados_locais", ""))
        try:
            with db.transaction() as con:
                r = registrar_ida(
                    con, notificacao_id, data=_campo("data"), hora=_campo("hora"),
                    resultado=_campo("resultado"), endereco=_campo("endereco"),
                    observacao=_campo("observacao"),
                    a_pedido=bool(request.form.get("a_pedido")),
                    feriados_locais=feriados, agora=agora(),
                    usuario=usuario_nome())
                recado = ""
                if r["diligencia_id"]:
                    d = banco(con).um(
                        "SELECT * FROM rg_notificacao_diligencias WHERE id = %s",
                        (r["diligencia_id"],))
                    recado = _cobrar_se_pedido(
                        con, "rg_notificacao_diligencias", r["diligencia_id"],
                        d["codigo_tj"], int(d["quantidade"]))
        except RECUSAS as erro:
            flash(str(erro), "danger")
            return redirect(url_for("rcpj_rtd_notificacao",
                                    notificacao_id=notificacao_id))
        audit("RG_NOTIFICACAO_DILIGENCIA", "rg_notificacao_idas", r["ida_id"],
              {"notificacao_id": notificacao_id, "numero": r["numero"],
               "resultado": _campo("resultado")})
        if r["diligencia_id"]:
            recado += _selar("rg_notificacao_diligencias", r["diligencia_id"])
        flash(f"{r['numero']}ª diligência registrada.{recado}",
              "success" if "SEM SELO" not in recado else "warning")
        return redirect(url_for("rcpj_rtd_notificacao",
                                notificacao_id=notificacao_id))

    @app.route("/rcpj-rtd/notificacao/<int:notificacao_id>/negativa",
               methods=["POST"])
    @login_required
    @roles_required(*RGW.QUEM_QUALIFICA)
    def rcpj_rtd_notificacao_negativa(notificacao_id: int):
        """Certificar que não se achou é decisão de quem qualifica."""
        try:
            with db.transaction() as con:
                certificar_negativa(con, notificacao_id, agora=agora(),
                                    usuario=usuario_nome())
        except RECUSAS as erro:
            flash(str(erro), "danger")
        else:
            audit("RG_NOTIFICACAO_NEGATIVA", "rg_notificacoes", notificacao_id, {})
            flash("Resultado negativo registrado. Emita a certidão.", "success")
        return redirect(url_for("rcpj_rtd_notificacao",
                                notificacao_id=notificacao_id))

    @app.route("/rcpj-rtd/notificacao/<int:notificacao_id>/certidao",
               methods=["POST"])
    @login_required
    @roles_required(*RGW.QUEM_QUALIFICA)
    def rcpj_rtd_notificacao_certidao(notificacao_id: int):
        """Emite, numera e congela; o selo sai depois da transação."""
        try:
            with db.transaction() as con:
                c = emitir_certidao(con, notificacao_id, agora=agora(), sv=sv(),
                                    data_extenso=extenso(),
                                    usuario=usuario_nome())
                recado = _cobrar_se_pedido(con, "rg_notificacao_certidoes",
                                           c["certidao_id"], ITEM_CERTIDAO, 1)
        except RECUSAS as erro:
            flash(str(erro), "danger")
            return redirect(url_for("rcpj_rtd_notificacao",
                                    notificacao_id=notificacao_id))
        audit("RG_NOTIFICACAO_CERTIDAO", "rg_notificacao_certidoes",
              c["certidao_id"], {"numero": c["numero"], "ano": c["ano"],
                                 "tipo": c["tipo"], "hash": c["hash"]})
        recado += _selar("rg_notificacao_certidoes", c["certidao_id"])
        flash(f"Certidão de notificação {c['tipo'].lower()} nº "
              f"{c['numero']}/{c['ano']} emitida.{recado}",
              "success" if "SEM SELO" not in recado else "warning")
        return redirect(url_for("rcpj_rtd_notificacao_certidao_ver",
                                certidao_id=c["certidao_id"]))

    @app.route("/rcpj-rtd/notificacao/certidao/<int:certidao_id>")
    @login_required
    @roles_required(*QUEM_LE)
    def rcpj_rtd_notificacao_certidao_ver(certidao_id: int):
        """A certidão emitida, como foi congelada — para ler e imprimir.

        O SELO SAI CONFERÍVEL NO PAPEL — LT05, 20/10/2026. A página mostrava
        só o número do selo: sem o QR e o endereço da consulta (CN-MA, art.
        132), sem o que o selo declara de emolumentos e sem quem expediu. O
        teor congelado não muda; o que entra é desenhado na impressão, como no
        resto da casa (`selo_no_papel`, `notas_selo.marca_do_selo`).
        """
        import notas_selo as NSELO
        import selo_no_papel as SNPAPEL
        with db.connect() as con:
            bd = banco(con)
            c = bd.um(
                "SELECT * FROM rg_notificacao_certidoes WHERE id = %s",
                (int(certidao_id),))
            if not c:
                abort(404)
            n = notificacao(con, int(c["notificacao_id"]))
            selo = _texto(c["selo"])
            texto_do_selo = _texto(bd.valor(
                "SELECT texto FROM sd_selos WHERE numero = %s ORDER BY id LIMIT 1",
                (selo,))) if selo else ""
        marca = NSELO.marca_do_selo(selo)
        return render_template(
            "rcpj_rtd_notificacao_certidao.html", c=c, n=n, sv=sv(),
            marca=marca, consulta=SNPAPEL.link_de_consulta(selo, texto_do_selo),
            valores=SNPAPEL.linha_de_valores(texto_do_selo), br=br)

    @app.route("/rcpj-rtd/notificacao/<int:notificacao_id>/averbar",
               methods=["POST"])
    @login_required
    @roles_required(*RGW.QUEM_QUALIFICA)
    def rcpj_rtd_notificacao_averbar(notificacao_id: int):
        """A averbação à margem do registro — ato do livro, de quem qualifica."""
        try:
            with db.transaction() as con:
                lugar = averbar(con, notificacao_id, sv=sv(), agora=agora(),
                                data_extenso=extenso(), usuario=usuario_nome())
        except RECUSAS as erro:
            flash(str(erro), "danger")
        else:
            audit("RG_NOTIFICACAO_AVERBADA", "rg_notificacoes", notificacao_id,
                  {"ato_id": lugar["ato_id"], "folha": lugar.get("folha")})
            flash("Resultado averbado à margem do registro, em ato próprio do "
                  "livro. O selo da averbação se pede na ficha do registro, "
                  "como o das outras.", "success")
        return redirect(url_for("rcpj_rtd_notificacao",
                                notificacao_id=notificacao_id))

    @app.route("/rcpj-rtd/notificacao/selar/<tabela>/<int:ato_id>",
               methods=["POST"])
    @login_required
    @roles_required(*RGW.QUEM_OPERA)
    def rcpj_rtd_notificacao_selar(tabela: str, ato_id: int):
        """Sela de novo o que ficou suspenso. Só as duas tabelas desta tela."""
        if tabela not in ("rg_notificacao_diligencias", "rg_notificacao_certidoes"):
            abort(404)
        with db.connect() as con:
            linha = banco(con).um(
                f"SELECT notificacao_id, selo_situacao FROM {tabela} WHERE id = %s",
                (int(ato_id),))
        if not linha:
            abort(404)
        if linha["selo_situacao"] == "SELADO":
            flash("Este ato já está selado.", "info")
        else:
            recado = _selar(tabela, ato_id)
            flash(recado.strip(),
                  "success" if "SEM SELO" not in recado else "warning")
        return redirect(url_for("rcpj_rtd_notificacao",
                                notificacao_id=linha["notificacao_id"]))
