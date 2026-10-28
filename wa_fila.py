"""A fila do WhatsApp por setor: etiquetas, responsável, transferência e prazo.

    «no mesmo pacote: ETIQUETAS (várias por conversa, edição manual),
     SETOR/RESPONSÁVEL da conversa, TRANSFERÊNCIA entre setores e PRAZO/TEMPO
     DE RESPOSTA (painel)» — decisão do oficial, 26/10/2026.

O QUE ESTE MÓDULO FAZ
    - ETIQUETAS: várias por conversa (`wa_etiqueta`). A automática, posta pela
      palavra-chave na chegada (`wa_balcao.classificar`), entra com origem
      `auto`; a que a pessoa põe na tela, com origem `manual`. Tirar é apagar a
      linha — e fica o evento de quem tirou.
    - SETOR E RESPONSÁVEL: a conversa é de um setor (`wa_schema.SETORES`) e,
      se alguém a pegou, de uma pessoa (`users.id`). Sem setor = ATENDIMENTO.
    - TRANSFERÊNCIA: trocar o setor (e, se quiser, o responsável) deixa um
      evento com de/para, quem e a nota. A transferência não apaga nada.
    - PASSAGEM PARA PESSOA e DEVOLUÇÃO À IA: o modo da conversa
      (`wa_schema.MODO_IA` / `MODO_PESSOA`). Quem passa é o atendente
      (`wa_atendente`) ou a pessoa, pelo botão; quem devolve é sempre a pessoa.
    - PRAZO: «esperando desde» é a mensagem do cliente mais antiga que ainda
      não teve resposta depois dela; passou do prazo da casa
      (`prazo_resposta_minutos`, padrão `PRAZO_PADRAO_MINUTOS`), está vencida.
      O painel junta isso por setor e mede o tempo da primeira resposta dos
      últimos dias — separando a da IA da da pessoa.

O QUE ELE NÃO FAZ
    Não fala com a rede, não envia nada e não chama IA. Só lê e grava no banco
    de quem chamou, dentro da transação de quem chamou.

O RELÓGIO É TEXTO ISO («AAAA-MM-DDTHH:MM:SS»), o mesmo de `db.now()`; a conta
de minutos é feita aqui, no Python, e não no banco.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any
from unicodedata import normalize

from bd_nativo import banco

import wa_schema as WA

PRAZO_PADRAO_MINUTOS = 30
DIAS_DO_PAINEL = 7
TAMANHO_DA_ETIQUETA = 40

AUTO = "auto"
MANUAL = "manual"

EV_TRANSFERENCIA = "transferencia"
EV_PASSAGEM = "passagem"
EV_DEVOLUCAO = "devolucao_ia"
EV_ETIQUETA_POSTA = "etiqueta_posta"
EV_ETIQUETA_TIRADA = "etiqueta_tirada"
EV_RESPONSAVEL = "responsavel"
EV_RETOMADA = "retomada"
EV_SEM_RESPONSAVEL_NA_VOLTA = "sem_responsavel_na_volta"
EV_SETOR_PELO_ASSUNTO = "setor_pelo_assunto"

# O RESPONSÁVEL NA VOLTA DA RESOLVIDA (decisão do oficial, 27/10/2026): até 7
# dias depois de resolvida, quem atendeu ainda lembra do caso, e a conversa
# volta para ele («Minhas»). Passado isso, volta sem responsável («Sem
# responsável»), e o setor fica. Conta pelo `resolvida_em`; nas resolvidas de
# antes da coluna, pelo `atualizado_em`. A regra é uma só: a entrada do
# cliente e o «Reativar conversa» chamam `retomar`.
DIAS_COM_O_MESMO_RESPONSAVEL = 7

# A ABA «RESOLVIDAS» MOSTRA AS MAIS RECENTES (27/10/2026): nada se apaga, e as
# resolvidas se acumulam. A lista traz só estas; a contagem da aba diz o total.
LIMITE_DAS_RESOLVIDAS = 100

# AS ABAS DA LISTA, na ordem da tela; «sem» é a que abre por padrão.
ABAS = (("sem", "Sem responsável"), ("minhas", "Minhas"), ("todas", "Todas"),
        ("resolvidas", "Resolvidas"))
ABA_PADRAO = "sem"

ROTULO_DO_EVENTO = {
    EV_TRANSFERENCIA: "transferida",
    EV_PASSAGEM: "passada para pessoa",
    EV_DEVOLUCAO: "devolvida à IA",
    EV_ETIQUETA_POSTA: "etiqueta posta",
    EV_ETIQUETA_TIRADA: "etiqueta tirada",
    EV_RESPONSAVEL: "responsável",
    EV_RETOMADA: "atendimento retomado",
    EV_SEM_RESPONSAVEL_NA_VOLTA: "voltou sem responsável",
    EV_SETOR_PELO_ASSUNTO: "setor pelo assunto",
}

# AS PALAVRAS QUE DIZEM O SETOR — UMA TABELA SÓ (27/10/2026, segunda revisão do
# #73). As etiquetas por palavra-chave repetiam o setor e nenhum relatório as
# lia; agora a palavra define o setor na chegada (`definir_setor_pelo_assunto`)
# e o atendente com IA lê a MESMA tabela para os assuntos sensíveis
# (`wa_atendente.assunto_sensivel`). Os três sensíveis vêm primeiro, com os
# padrões que o atendente já usava — a ordem é a de antes. Sem acento e em
# minúscula: o texto é comparado por `_sem_acento`. «certidão» sozinha não
# entra: serve a vários setores.
SETOR_POR_PALAVRA: tuple[tuple[str, str, re.Pattern], ...] = (
    ("PROTESTO", "assunto de protesto", re.compile(
        r"\b(protest\w*|cenprot|cra|intimac\w*)\b")),
    ("RCPN", "assunto de registro civil", re.compile(
        r"\b(nascimento|casamento|obito|registro civil|habilitac\w*|divorci\w*|"
        r"natimort\w*|registrar (meu|minha|o|a) (filh\w*|bebe)|"
        r"uniao estavel|certidao de (nascimento|casamento|obito))\b")),
    ("GESTAO", "reclamação", re.compile(
        r"\b(reclama\w*|ouvidoria|denunci\w*|procon|corregedoria|absurdo|"
        r"descaso|pessim\w*|desrespeit\w*|processar voces)\b")),
    ("NOTAS", "assunto de notas", re.compile(
        r"\b(escritura\w*|procurac\w*|testamento\w*|ata notarial|"
        r"reconhecimento de firma|reconhecer (a )?firma|autenticac\w*)\b")),
    ("RI", "assunto de registro de imóveis", re.compile(
        r"\b(matricula\w*|imove(l|is)|registro de imoveis|usucapiao|averbac\w*)\b")),
    ("RCPJ_RTD", "assunto de títulos e documentos ou pessoa jurídica", re.compile(
        r"\b(contrato social|estatuto\w*|ata de assembleia|titulos e documentos)\b")),
)
# Os que vão a uma pessoa sem passar pela IA (a regra do atendente, de antes).
SETORES_SENSIVEIS = ("PROTESTO", "RCPN", "GESTAO")

_ISO = "%Y-%m-%dT%H:%M:%S"


def _dt(valor: Any) -> datetime | None:
    texto = str(valor or "").strip().replace(" ", "T")[:19]
    try:
        return datetime.strptime(texto, _ISO)
    except ValueError:
        return None


def minutos_entre(desde: Any, ate: Any) -> int | None:
    """Minutos inteiros de `desde` até `ate`, ou None se uma data não lê."""
    a, b = _dt(desde), _dt(ate)
    if a is None or b is None:
        return None
    return max(0, int((b - a).total_seconds() // 60))


def normalizar_etiqueta(texto: Any) -> str:
    """Minúscula, sem acento, com `_` no lugar de espaço. Vazio = inválida.

    Sem acento de propósito, como as sete de fábrica (`wa_schema.ETIQUETAS`):
    «certidão» e «certidao» seriam duas etiquetas que ninguém distingue.
    """
    n = normalize("NFD", str(texto or ""))
    t = "".join(c for c in n if not (0x300 <= ord(c) <= 0x36F)).lower().strip()
    t = re.sub(r"[^a-z0-9]+", "_", t).strip("_")
    return t[:TAMANHO_DA_ETIQUETA]


def _sem_acento(texto: Any) -> str:
    n = normalize("NFD", str(texto or ""))
    return "".join(c for c in n if not (0x300 <= ord(c) <= 0x36F)).lower()


def setores_pelo_texto(texto: Any) -> list[tuple[str, str, str]]:
    """[(setor, motivo, palavra)] — um por setor que a mensagem cita, na ordem
    da tabela `SETOR_POR_PALAVRA`. Só calcula."""
    t = _sem_acento(texto)
    achados = []
    for setor, motivo, padrao in SETOR_POR_PALAVRA:
        m = padrao.search(t)
        if m:
            achados.append((setor, motivo, m.group(0)))
    return achados


def setor_pela_mensagem(texto: Any) -> tuple[str, str] | None:
    """(setor, palavra) quando a mensagem cita UM setor só. Dois ou mais, ou
    nenhum: None — melhor não adivinhar, e a conversa fica no Atendimento."""
    achados = setores_pelo_texto(texto)
    if len(achados) != 1:
        return None
    return achados[0][0], achados[0][2]


def cor_do_setor(setor: Any) -> str:
    """A cor do setor na lista: a do módulo do sistema (`modulos.MODULOS`). O
    Atendimento usa o azul do sistema (`--accent`) e a Gestão o cinza do ADM,
    porque não têm módulo próprio."""
    import modulos as MOD
    cores = {m["chave"]: m["cor"] for m in MOD.MODULOS}
    s = setor_valido(setor) or WA.SETOR_PADRAO
    if s == "GESTAO":
        return cores.get("ADM", "#6c6f7a")
    return cores.get(s, "#0675df")


def iniciais(nome: Any, numero: Any = "") -> str:
    """As iniciais do círculo: a primeira e a última palavra do nome; sem
    nome, «#» e os dois últimos dígitos do número."""
    partes = [p for p in str(nome or "").replace(".", " ").split()
              if len(p) > 2 or p.isupper()]
    if partes:
        return (partes[0][0] + (partes[-1][0] if len(partes) > 1 else "")).upper()
    return "#" + str(numero or "")[-2:]


def setor_valido(setor: Any) -> str:
    s = str(setor or "").strip().upper()
    return s if s in WA.SETORES else ""


def nome_do_setor(setor: Any) -> str:
    return WA.SETORES.get(setor_valido(setor) or WA.SETOR_PADRAO, str(setor or ""))


def prazo_minutos(con: Any) -> int:
    linha = banco(con).um("SELECT valor FROM wa_config WHERE chave=%s",
                          (WA.CHAVE_PRAZO_MINUTOS,))
    try:
        valor = int(str((linha or {}).get("valor") or "").strip())
    except ValueError:
        return PRAZO_PADRAO_MINUTOS
    return valor if valor > 0 else PRAZO_PADRAO_MINUTOS


# ------------------------------------------------------------- os eventos


def _evento(con: Any, conversa_id: int, tipo: str, *, quando: str,
            por: str = "", de_setor: str | None = None,
            para_setor: str | None = None, responsavel_id: int | None = None,
            nota: str = "") -> None:
    banco(con).escrever(
        """INSERT INTO wa_evento (conversa_id, quando, tipo, de_setor,
                                  para_setor, responsavel_id, por, nota)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
        (int(conversa_id), quando, tipo, de_setor, para_setor, responsavel_id,
         (por or "")[:80], (nota or "")[:500]))


def eventos(con: Any, conversa_id: int) -> list[dict]:
    linhas = banco(con).ler(
        """SELECT e.*, u.full_name AS responsavel_nome
             FROM wa_evento e LEFT JOIN users u ON u.id = e.responsavel_id
            WHERE e.conversa_id=%s ORDER BY e.id""", (int(conversa_id),))
    return [dict(r) for r in linhas]


# ------------------------------------------------------------- as etiquetas


def etiquetas(con: Any, conversa_id: int) -> list[dict]:
    return [dict(r) for r in banco(con).ler(
        """SELECT etiqueta, origem, criado_em, criado_por FROM wa_etiqueta
            WHERE conversa_id=%s ORDER BY etiqueta""", (int(conversa_id),))]


def por_etiqueta(con: Any, conversa_id: int, etiqueta: str, *,
                 origem: str = MANUAL, por: str = "", quando: str) -> bool:
    """Põe a etiqueta. Devolve se ela é nova. A repetida não duplica."""
    et = normalizar_etiqueta(etiqueta)
    if not et:
        return False
    bd = banco(con)
    novas = bd.escrever(
        """INSERT INTO wa_etiqueta (conversa_id, etiqueta, origem, criado_em,
                                    criado_por)
           VALUES (%s, %s, %s, %s, %s)
           ON CONFLICT (conversa_id, etiqueta) DO NOTHING RETURNING id""",
        (int(conversa_id), et, origem, quando, (por or "")[:80]))
    if novas and origem == MANUAL:
        _evento(con, conversa_id, EV_ETIQUETA_POSTA, quando=quando, por=por,
                nota=et)
    return bool(novas)


def tirar_etiqueta(con: Any, conversa_id: int, etiqueta: str, *,
                   por: str = "", quando: str) -> bool:
    et = normalizar_etiqueta(etiqueta)
    if not et:
        return False
    tiradas = banco(con).escrever(
        "DELETE FROM wa_etiqueta WHERE conversa_id=%s AND etiqueta=%s "
        "RETURNING id", (int(conversa_id), et))
    if tiradas:
        _evento(con, conversa_id, EV_ETIQUETA_TIRADA, quando=quando, por=por,
                nota=et)
    return bool(tiradas)


# ------------------------------------------- setor, responsável e modo


def _conversa(con: Any, conversa_id: int) -> dict | None:
    return banco(con).um("SELECT * FROM wa_conversa WHERE id=%s",
                         (int(conversa_id),))


def transferir(con: Any, conversa_id: int, para_setor: str, *,
               responsavel_id: int | None = None, por: str = "",
               nota: str = "", quando: str) -> dict:
    """Troca o setor (e o responsável, se veio). Deixa o evento de/para.

    O responsável que não é do novo setor não fica: transferir sem dizer quem
    pega devolve a conversa ao setor, sem dono — é o que «transferir» quer
    dizer no balcão.
    """
    destino = setor_valido(para_setor)
    if not destino:
        raise ValueError("Setor desconhecido: escolha um da lista.")
    c = _conversa(con, conversa_id)
    if not c:
        raise ValueError("Conversa não encontrada.")
    de = setor_valido(c.get("setor")) or WA.SETOR_PADRAO
    if responsavel_id is not None and not banco(con).um(
            "SELECT id FROM users WHERE id=%s AND active=1", (int(responsavel_id),)):
        raise ValueError("Responsável não encontrado entre os usuários ativos.")
    banco(con).escrever(
        """UPDATE wa_conversa SET setor=%s, responsavel_id=%s, atualizado_em=%s
            WHERE id=%s""", (destino, responsavel_id, quando, int(conversa_id)))
    _evento(con, conversa_id, EV_TRANSFERENCIA, quando=quando, por=por,
            de_setor=de, para_setor=destino, responsavel_id=responsavel_id,
            nota=nota)
    return {"de": de, "para": destino, "responsavel_id": responsavel_id}


def assumir(con: Any, conversa_id: int, usuario_id: int, *, por: str = "",
            quando: str) -> None:
    """A pessoa pega a conversa para si (fica responsável, setor mantido)."""
    banco(con).escrever(
        "UPDATE wa_conversa SET responsavel_id=%s, atualizado_em=%s WHERE id=%s",
        (int(usuario_id), quando, int(conversa_id)))
    _evento(con, conversa_id, EV_RESPONSAVEL, quando=quando, por=por,
            responsavel_id=int(usuario_id))


def passar_para_pessoa(con: Any, conversa_id: int, *, setor: str = "",
                       motivo: str = "", por: str = "", quando: str) -> str:
    """Tira a conversa da IA e a marca para o setor. Devolve o setor marcado.

    Setor vazio ou desconhecido mantém o da conversa (ou o ATENDIMENTO).
    """
    c = _conversa(con, conversa_id) or {}
    atual = setor_valido(c.get("setor")) or WA.SETOR_PADRAO
    destino = setor_valido(setor) or atual
    banco(con).escrever(
        """UPDATE wa_conversa SET modo=%s, setor=%s, passagem_motivo=%s,
                  status=%s, atualizado_em=%s
            WHERE id=%s""",
        (WA.MODO_PESSOA, destino, (motivo or "")[:300], WA.ABERTA, quando,
         int(conversa_id)))
    _evento(con, conversa_id, EV_PASSAGEM, quando=quando, por=por,
            de_setor=atual, para_setor=destino, nota=motivo)
    return destino


def devolver_a_ia(con: Any, conversa_id: int, *, por: str = "",
                  quando: str) -> None:
    banco(con).escrever(
        """UPDATE wa_conversa SET modo=%s, passagem_motivo=NULL, atualizado_em=%s
            WHERE id=%s""", (WA.MODO_IA, quando, int(conversa_id)))
    _evento(con, conversa_id, EV_DEVOLUCAO, quando=quando, por=por)


def retomar(con: Any, conversa: dict, *, desde_id: int, quando: str,
            por: str = "", motivo: str = "") -> dict:
    """A RESOLVIDA QUE VOLTA — pelo cliente ou pelo «Reativar conversa». ESCREVE.

    `conversa` é a linha COMO ESTAVA, ainda resolvida. Ela volta aberta e para
    a IA (como sempre voltou), sem nada apagado, e o atendimento atual começa
    em `desde_id`: a tela mostra dali em diante e guarda o resto atrás de «Ver
    histórico». O responsável fica até `DIAS_COM_O_MESMO_RESPONSAVEL` dias
    depois de resolvida; passado isso, sai, e o evento diz por quê.
    """
    cid = int(conversa["id"])
    responsavel = conversa.get("responsavel_id")
    base = _dt(conversa.get("resolvida_em")) or _dt(conversa.get("atualizado_em"))
    agora = _dt(quando)
    saiu = bool(responsavel and base and agora
                and agora - base > timedelta(days=DIAS_COM_O_MESMO_RESPONSAVEL))
    if saiu:
        responsavel = None
        _evento(con, cid, EV_SEM_RESPONSAVEL_NA_VOLTA, quando=quando, por=por,
                nota=f"voltou sem responsável: resolvida havia mais de "
                     f"{DIAS_COM_O_MESMO_RESPONSAVEL} dias")
    banco(con).escrever(
        """UPDATE wa_conversa
              SET status=%s, modo=NULL, passagem_motivo=NULL, resolvida_em=NULL,
                  atendimento_desde_id=%s, responsavel_id=%s, atualizado_em=%s
            WHERE id=%s""",
        (WA.ABERTA, int(desde_id), responsavel, quando, cid))
    _evento(con, cid, EV_RETOMADA, quando=quando, por=por, nota=motivo)
    return {"responsavel_id": responsavel, "saiu_o_responsavel": saiu}


def definir_setor_pelo_assunto(con: Any, conversa_id: int, texto: Any, *,
                               quando: str, na_retomada: bool = False) -> str | None:
    """O SETOR PELA PALAVRA DA MENSAGEM QUE CHEGOU. ESCREVE. Devolve o setor
    gravado, ou None.

    Fora da retomada, só age na conversa SEM setor (nova, ou que nunca foi
    transferida nem passada): nunca muda o setor que uma pessoa ou a IA
    escolheu. NA RETOMADA de uma resolvida, a mensagem nova abre outro
    atendimento, e o setor dela vale mesmo que a conversa tivesse outro. O
    evento diz de qual para qual, e por qual palavra.
    """
    achado = setor_pela_mensagem(texto)
    if not achado:
        return None
    c = _conversa(con, conversa_id) or {}
    antes = setor_valido(c.get("setor"))
    setor, palavra = achado
    if antes == setor or (antes and not na_retomada):
        return None
    banco(con).escrever("UPDATE wa_conversa SET setor=%s WHERE id=%s",
                        (setor, int(conversa_id)))
    caminho = (f"{nome_do_setor(antes)} → " if antes else "") + nome_do_setor(setor)
    _evento(con, conversa_id, EV_SETOR_PELO_ASSUNTO, quando=quando,
            por="palavra da mensagem", de_setor=antes or None, para_setor=setor,
            nota=f"setor pelo assunto: {caminho} (palavra «{palavra}»)")
    return setor


def usuarios_ativos(con: Any) -> list[dict]:
    return [dict(r) for r in banco(con).ler(
        """SELECT id, username, full_name FROM users
            WHERE active=1 AND role <> 'AUDITOR' ORDER BY full_name""")]


# ------------------------------------------------------------- o prazo


_ESPERANDO_DESDE = """
    (SELECT min(m.criado_em) FROM wa_mensagem m
      WHERE m.conversa_id = c.id AND m.direcao = 'in'
        AND m.id > COALESCE((SELECT max(o.id) FROM wa_mensagem o
                              WHERE o.conversa_id = c.id
                                AND o.direcao = 'out'), 0))"""


def _filtros(con: Any, *, agora: str, setor: str, etiqueta: str,
             so_vencidas: bool) -> tuple[list[str], list]:
    """As condições comuns da lista e da contagem das abas (no banco)."""
    filtro, args = [], []
    s = setor_valido(setor)
    if s:
        filtro.append("COALESCE(NULLIF(c.setor, ''), %s) = %s")
        args += [WA.SETOR_PADRAO, s]
    et = normalizar_etiqueta(etiqueta)
    if et:
        filtro.append("EXISTS (SELECT 1 FROM wa_etiqueta e "
                      "WHERE e.conversa_id = c.id AND e.etiqueta = %s)")
        args.append(et)
    if so_vencidas:
        # O MESMO CORTE DO `vencida` DE CADA LINHA, no banco: esperando desde
        # antes de agora menos o prazo (as datas são texto ISO, comparáveis).
        limite = _dt(agora)
        corte = ((limite - timedelta(minutes=prazo_minutos(con))).strftime(_ISO)
                 if limite else agora)
        filtro.append(f"c.status <> %s AND {_ESPERANDO_DESDE} < %s")
        args += [WA.RESOLVIDA, corte]
    return filtro, args


def _da_aba(aba: str, usuario_id: int | None) -> tuple[str, list]:
    if aba == "resolvidas":
        return "c.status = %s", [WA.RESOLVIDA]
    if aba == "sem":
        return "c.status <> %s AND c.responsavel_id IS NULL", [WA.RESOLVIDA]
    if aba == "minhas":
        return "c.status <> %s AND c.responsavel_id = %s", [WA.RESOLVIDA,
                                                           int(usuario_id or 0)]
    return "c.status <> %s", [WA.RESOLVIDA]                   # «todas» as abertas


def nao_respondidas(con: Any, *, usuario_id: int | None) -> int:
    """QUANTAS CONVERSAS ESPERAM RESPOSTA — o alerta do atalho (27/10/2026).

    Não é «não lida»: o sistema não guarda leitura. É a régua do «esperando N
    min» da lista (`_ESPERANDO_DESDE`): há mensagem do cliente depois da última
    saída, de pessoa ou da IA. Só as que são de quem vê ou de ninguém — as
    condições das abas «Sem responsável» e «Minhas» (`_da_aba`); a de outro
    responsável não conta. Conta a CONVERSA: cinco mensagens seguidas do mesmo
    cliente são uma pessoa esperando. Uma consulta, no banco."""
    sem, args_sem = _da_aba("sem", usuario_id)
    minhas, args_minhas = _da_aba("minhas", usuario_id)
    r = banco(con).um(
        f"""SELECT COUNT(*) AS n FROM wa_conversa c
             WHERE (({sem}) OR ({minhas}))
               AND {_ESPERANDO_DESDE} IS NOT NULL""",
        (*args_sem, *args_minhas)) or {}
    return int(r.get("n") or 0)


def rotulo_do_atalho(n: int) -> dict:
    """O que o atalho mostra, pronto: o número do alerta («99+» acima de 99) e
    o rótulo por extenso do link. A rota e o template usam esta função, e o
    JavaScript só copia o que vem dela."""
    n = int(n or 0)
    if n <= 0:
        rotulo = "WhatsApp"
    elif n == 1:
        rotulo = "WhatsApp: 1 conversa esperando resposta"
    else:
        rotulo = f"WhatsApp: {n} conversas esperando resposta"
    return {"n": n, "texto": "99+" if n > 99 else str(n), "rotulo": rotulo}


def contar_por_aba(con: Any, *, agora: str, usuario_id: int | None,
                   setor: str = "", etiqueta: str = "",
                   so_vencidas: bool = False) -> dict[str, int]:
    """Quantas conversas há em cada aba, com os mesmos filtros. UMA consulta,
    no banco: as resolvidas se acumulam e não se trazem para contar."""
    filtro, args = _filtros(con, agora=agora, setor=setor, etiqueta=etiqueta,
                            so_vencidas=so_vencidas)
    onde = ("WHERE " + " AND ".join(filtro)) if filtro else ""
    r = banco(con).um(
        f"""SELECT
              COALESCE(SUM(CASE WHEN c.status <> %s AND c.responsavel_id IS NULL
                                THEN 1 ELSE 0 END), 0) AS sem,
              COALESCE(SUM(CASE WHEN c.status <> %s AND c.responsavel_id = %s
                                THEN 1 ELSE 0 END), 0) AS minhas,
              COALESCE(SUM(CASE WHEN c.status <> %s THEN 1 ELSE 0 END), 0) AS todas,
              COALESCE(SUM(CASE WHEN c.status = %s THEN 1 ELSE 0 END), 0) AS resolvidas
              FROM wa_conversa c {onde}""",
        (WA.RESOLVIDA, WA.RESOLVIDA, int(usuario_id or 0), WA.RESOLVIDA,
         WA.RESOLVIDA, *args)) or {}
    return {aba: int(r.get(aba) or 0) for aba, _ in ABAS}


def listar(con: Any, *, agora: str, setor: str = "", etiqueta: str = "",
           so_abertas: bool = False, so_vencidas: bool = False,
           aba: str = "", usuario_id: int | None = None) -> list[dict]:
    """A fila com setor, responsável, etiquetas e quanto o cliente espera.

    `vencida` = esperando há mais que o prazo da casa. Conversa resolvida não
    vence: quem a resolveu decidiu que não há o que responder.

    `aba` (27/10/2026) filtra NO BANCO: «sem», «minhas», «todas» (as abertas)
    ou «resolvidas» — estas da mais recente para a mais antiga, e só as
    `LIMITE_DAS_RESOLVIDAS` + 1 primeiras (a de sobra diz que há mais). Sem
    `aba`, a lista é a de antes.
    """
    bd = banco(con)
    filtro, args = _filtros(con, agora=agora, setor=setor, etiqueta=etiqueta,
                            so_vencidas=so_vencidas)
    if so_abertas:
        filtro.append("c.status <> %s")
        args.append(WA.RESOLVIDA)
    ordem, limite = "c.atualizado_em DESC, c.id DESC", ""
    if aba:
        condicao, mais = _da_aba(aba, usuario_id)
        filtro.append(condicao)
        args += mais
        if aba == "resolvidas":
            ordem = ("COALESCE(NULLIF(c.resolvida_em, ''), c.atualizado_em) DESC, "
                     "c.id DESC")
            limite = f"LIMIT {LIMITE_DAS_RESOLVIDAS + 1}"
    onde = ("WHERE " + " AND ".join(filtro)) if filtro else ""
    linhas = bd.ler(
        f"""SELECT c.id, c.wa_id, c.nome, c.etiqueta, c.status, c.rascunho,
                   c.auto_ok, c.atualizado_em, c.setor, c.modo,
                   c.responsavel_id, c.passagem_motivo,
                   c.resolvida_em, c.atendimento_desde_id,
                   u.full_name AS responsavel_nome,
                   (SELECT m.texto FROM wa_mensagem m
                     WHERE m.conversa_id=c.id
                     ORDER BY m.id DESC LIMIT 1) AS ultimo_texto,
                   {_ESPERANDO_DESDE} AS esperando_desde
              FROM wa_conversa c LEFT JOIN users u ON u.id = c.responsavel_id
              {onde}
             ORDER BY {ordem} {limite}""", tuple(args))
    prazo = prazo_minutos(con)
    tags: dict[int, list[str]] = {}
    for r in bd.ler("SELECT conversa_id, etiqueta FROM wa_etiqueta "
                    "ORDER BY etiqueta"):
        tags.setdefault(int(r["conversa_id"]), []).append(r["etiqueta"])
    saida = []
    for r in linhas:
        d = dict(r)
        d["setor"] = setor_valido(d.get("setor")) or WA.SETOR_PADRAO
        d["setor_nome"] = WA.SETORES[d["setor"]]
        d["modo"] = d.get("modo") or WA.MODO_IA
        d["etiquetas"] = tags.get(int(d["id"]), [])
        espera = (minutos_entre(d.get("esperando_desde"), agora)
                  if d["status"] != WA.RESOLVIDA else None)
        d["esperando_min"] = espera
        d["vencida"] = espera is not None and espera > prazo
        if so_vencidas and not d["vencida"]:
            continue
        saida.append(d)
    return saida


def _primeiras_respostas(con: Any, desde: str) -> list[dict]:
    """Para cada mensagem do cliente que abriu uma espera desde `desde`, a
    primeira resposta depois dela e quem respondeu (`ia` ou a pessoa)."""
    bd = banco(con)
    msgs = bd.ler(
        """SELECT m.id, m.conversa_id, m.direcao, m.criado_em, m.autor,
                  COALESCE(NULLIF(c.setor, ''), %s) AS setor
             FROM wa_mensagem m JOIN wa_conversa c ON c.id = m.conversa_id
            WHERE m.criado_em >= %s AND m.direcao IN ('in', 'out')
            ORDER BY m.conversa_id, m.id""", (WA.SETOR_PADRAO, desde))
    saida, aberta = [], {}
    for m in msgs:
        cid = int(m["conversa_id"])
        if m["direcao"] == "in":
            aberta.setdefault(cid, m)
        elif cid in aberta:
            pergunta = aberta.pop(cid)
            saida.append({
                "setor": setor_valido(pergunta["setor"]) or WA.SETOR_PADRAO,
                "minutos": minutos_entre(pergunta["criado_em"], m["criado_em"]),
                "por_ia": (m.get("autor") or "") == "ia",
            })
    return saida


def painel(con: Any, *, agora: str, dias: int = DIAS_DO_PAINEL) -> dict:
    """O painel do prazo: por setor, o que está aberto, com pessoa, esperando
    e vencido agora; e o tempo da primeira resposta nos últimos `dias`. SÓ LÊ."""
    fila = listar(con, agora=agora, so_abertas=True)
    prazo = prazo_minutos(con)
    setores = {s: {"setor": s, "nome": n, "abertas": 0, "com_pessoa": 0,
                   "esperando": 0, "vencidas": 0, "maior_espera": None,
                   "respostas_pessoa": 0, "media_pessoa": None,
                   "respostas_ia": 0, "media_ia": None}
               for s, n in WA.SETORES.items()}
    for c in fila:
        s = setores[c["setor"]]
        s["abertas"] += 1
        if c["modo"] == WA.MODO_PESSOA:
            s["com_pessoa"] += 1
        if c["esperando_min"] is not None:
            s["esperando"] += 1
            s["maior_espera"] = max(s["maior_espera"] or 0, c["esperando_min"])
        if c["vencida"]:
            s["vencidas"] += 1
    inicio = _dt(agora) or datetime.now()
    desde = (inicio - timedelta(days=dias)).strftime(_ISO)
    somas: dict[tuple[str, bool], list[int]] = {}
    for r in _primeiras_respostas(con, desde):
        if r["minutos"] is not None:
            somas.setdefault((r["setor"], r["por_ia"]), []).append(r["minutos"])
    for (setor, por_ia), lista in somas.items():
        chave = "ia" if por_ia else "pessoa"
        setores[setor][f"respostas_{chave}"] = len(lista)
        setores[setor][f"media_{chave}"] = round(sum(lista) / len(lista))
    linhas = list(setores.values())
    total = {k: sum(s[k] for s in linhas)
             for k in ("abertas", "com_pessoa", "esperando", "vencidas",
                       "respostas_pessoa", "respostas_ia")}
    return {"setores": linhas, "total": total, "prazo": prazo, "dias": dias,
            "vencidas": [c for c in fila if c["vencida"]]}
