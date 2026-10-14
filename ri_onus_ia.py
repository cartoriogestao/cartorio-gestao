"""A certidão de ônus POSITIVA ou NEGATIVA — e a IA que sugere qual das duas.

    «precisamos ajustar o modelo de certidao de onus para contemplar tanto a
     positiva e a negativa, podemos incluir a api da ia para fazer a sugestao
     de qual certidao se trata para aquela matricula e escolher o teor
     correto» — o oficial, 13/10/2026

O QUE ESTAVA ERRADO, MEDIDO
    O tipo se chamava «Certidão negativa de ônus reais» e o título saía assim
    mesmo quando a matrícula tinha hipoteca. E a lista de ônus (`ri_onus`) só
    olha `ri_atos` — e 1.979 das 1.985 fichas desta casa são ACERVO, com os atos
    escritos DENTRO do teor. Medido na produção em 13/10/2026: **1.144** fichas
    trazem palavra de ônus no teor (hipoteca, penhora, cédula, usufruto,
    indisponibilidade…), e em **1.073** delas a regra do sistema não acha ônus
    nenhum — a certidão sairia «NADA CONSTA». Parte disso é ônus já cancelado
    (440 falam em cancelamento ou baixa) ou a frase «livre e desembaraçado»;
    separar um do outro é leitura, e é para isso que a IA entra.

O PRECEDENTE DA CASA, e é ele que o texto imita
    A pasta «1. RI/CERTIDÕES/certidões antigas/ÔNUS» do Proton tem 258
    negativas e 70 positivas. As de 2024 (Karem, Leidiane) dizem:
      «CERTIDÃO DE POSITIVA DE ÔNUS E NEGATIVA DE REGISTRO DE AÇÕES REAIS E
       PESSOAIS REIPERSECUTÓRIAS» … «HÁ ÔNUS REAIS, assim caracterizados:
       a) R-02/2.914 (Protocolo n° 9837). Cidade Exemplo-MA, … Registra-se …»
    — o ato que grava o imóvel vai TRANSCRITO, e não resumido. Na negativa:
      «LIVRE E DESEMBARAÇADO DE TODOS ÔNUS REAIS, LEGAIS OU CONVENCIONAIS».
    São DUAS perguntas no mesmo papel — ônus, e citação de ações reais ou
    pessoais reipersecutórias — e cada uma é positiva ou negativa.

A IA SUGERE; QUEM ESCOLHE É O ESCREVENTE, e três guardas sustentam isso:
    1. O TRECHO QUE A IA APONTA TEM DE ESTAR ESCRITO NA FICHA, palavra por
       palavra (só espaço e caixa se ignoram). Trecho que não está não pode ser
       marcado: certidão que «transcreve» texto que o livro não tem é o carimbo
       que mente na forma mais cara.
    2. NEGATIVA SOBRE ÔNUS QUE O SISTEMA CONHECE (ato lavrado com natureza de
       ônus e não cancelado) É RECUSADA — ali não há dúvida a decidir.
    3. NEGATIVA CONTRA A SUGESTÃO DA IA exige justificativa escrita (dez letras,
       a régua das recusas da casa), e ela fica gravada na certidão.
    Sem chave da IA, ou com `settings.onus_ia = '0'`, a sugestão não existe e a
    escolha continua sendo do escrevente — o balcão não para.

ESTE MÓDULO NÃO EMITE, NÃO NUMERA, NÃO SELA E NÃO COBRA. Quem emite é a rota de
sempre (`ri_emitir_certidao`); aqui mora a decisão do texto e a leitura da IA.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import sqlite3
import threading
import unicodedata
from datetime import datetime
from pathlib import Path

POSITIVA, NEGATIVA = "POSITIVA", "NEGATIVA"
RESULTADOS = (POSITIVA, NEGATIVA)
ONUS, ACAO = "ONUS", "ACAO"
CHAVE_LIGADA = "onus_ia"
MINIMO_DA_JUSTIFICATIVA = 10
MAXIMO_DE_SAIDA = 8000
LIMITE_DO_DOSSIE = 150_000
MINUTOS_PARA_DESISTIR = 10

#: Natureza SAUIN (`ri_naturezas`) que é AÇÃO, e não ônus: citação de ação real
#: ou pessoal reipersecutória, premonitória e ajuizamento de execução. As três
#: estão em `ri_onus.CODIGOS_DE_ONUS`; a certidão da casa as separa.
CODIGOS_DE_ACAO = frozenset({30, 100, 101})
_TERMOS_DE_ACAO = ("CITACAO", "PREMONIT", "AJUIZAMENTO DE EXECUCAO")

_ROTULO_NO_COMECO = re.compile(
    r"^\s*(?:R|AV)\s*[-.]?\s*\d+\s*(?:/\s*[\d.]+)?\s*(?:\([^)]{0,80}\))?\s*[-–—:.]*\s*",
    re.I)
_ROTULO_EM_QUALQUER_LUGAR = re.compile(r"\b(?:R|AV)\s*[-.]?\s*\d+\s*/\s*[\d.]+", re.I)

SCHEMA = """
CREATE TABLE IF NOT EXISTS ri_onus_sugestoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    matricula_id INTEGER NOT NULL,
    hash_ficha TEXT NOT NULL,
    dossie TEXT NOT NULL,
    situacao TEXT NOT NULL DEFAULT 'PENDENTE',   -- PENDENTE | LENDO | PRONTA | ERRO
    pedido_em TEXT NOT NULL,
    pedido_por TEXT,
    terminado_em TEXT,
    provedor TEXT,
    modelo TEXT,
    resultado_json TEXT,
    erro TEXT,
    tokens_entrada INTEGER,
    tokens_saida INTEGER
);
CREATE INDEX IF NOT EXISTS ix_ri_onus_sugestoes_matricula
    ON ri_onus_sugestoes (matricula_id, hash_ficha);
"""

INSTRUCAO = """Você ajuda o Registro de Imóveis de uma serventia do Maranhão a emitir a \
CERTIDÃO DE ÔNUS de uma matrícula. Você recebe a matrícula inteira: o teor da ficha \
(que, nas fichas antigas, traz os atos R e AV escritos dentro dele) e os atos lavrados \
no sistema, cada um marcado se está cancelado.

A certidão responde DUAS perguntas, e cada uma é POSITIVA ou NEGATIVA:
1. ÔNUS REAIS VIGENTES sobre o imóvel: hipoteca (inclusive cedular), alienação \
fiduciária, penhor registrado na matrícula, penhora, arresto, sequestro, \
indisponibilidade, usufruto, uso, habitação, servidão, enfiteuse, anticrese, \
superfície, concessão de direito real de uso, compromisso ou promessa de compra e venda \
registrado, bem de família, cláusulas de inalienabilidade, impenhorabilidade ou \
incomunicabilidade, fideicomisso, caução, bloqueio. A NOTÍCIA DE PENHOR averbada na \
matrícula (penhor rural, pecuário ou cedular registrado no Livro 3, com os bens \
localizados no imóvel) TAMBÉM É ÔNUS e entra na certidão — por decisão do oficial; não \
a trate como cautela nem como dúvida.
2. AÇÕES: registro de citação de ação real ou pessoal reipersecutória, averbação \
premonitória ou de ajuizamento de execução.

NÃO É ÔNUS VIGENTE: o que foi cancelado, baixado, quitado ou extinto por ato \
posterior (averbação de cancelamento, de quitação, de baixa, de extinção do usufruto \
por morte, de liberação); a frase «livre e desembaraçado de ônus» de uma compra e \
venda; ônus que gravava OUTRO imóvel ou outra matrícula; a menção histórica de ônus \
na matrícula de origem que não foi transportado para esta.

Para cada ônus ou ação VIGENTE, copie em «trecho» o texto do ato EXATAMENTE como \
está escrito no material recebido, do rótulo (ex.: «R-02/2.914») até o fim daquele \
ato — sem corrigir, resumir, completar ou trocar palavra. O trecho vai transcrito numa \
certidão, e o sistema confere letra por letra; trecho que não estiver escrito será \
descartado. Se o ato for muito longo, copie do rótulo até o fim do primeiro parágrafo.

Responda SÓ com JSON, sem texto em volta:
{"onus": "POSITIVA" | "NEGATIVA", "acoes": "POSITIVA" | "NEGATIVA", \
"itens": [{"categoria": "ONUS" | "ACAO", "ato": "R-02/2.914", \
"natureza": "Hipoteca cedular de 1º grau", "trecho": "..."}], \
"cancelados": [{"ato": "R-03/2.914", "cancelado_por": "AV-05/2.914"}], \
"parecer": "uma ou duas frases dizendo por que é positiva ou negativa, e o que deixou dúvida"}
Na dúvida sobre se um ônus está vigente, INCLUA-O em itens e diga a dúvida no parecer: \
quem emite confere. Não invente: se o texto não permite concluir, diga no parecer."""


class OnusError(ValueError):
    """Erro de regra, com a frase pronta para o balcão."""


# ------------------------------------------------------------------ texto

def normalizar(texto) -> str:
    """Sem HTML, com as entidades traduzidas e o espaço colapsado."""
    sem_tags = html.unescape(re.sub(r"<[^>]+>", " ", str(texto or "")))
    return " ".join(sem_tags.split())


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto or "")
                   if unicodedata.category(c) != "Mn").upper()


def _comparavel(texto: str) -> str:
    """A régua do «está escrito na ficha»: só espaço e caixa se ignoram."""
    return normalizar(texto).casefold()


def esta_escrito(trecho: str, texto_da_ficha: str) -> bool:
    alvo = _comparavel(trecho)
    return bool(alvo) and alvo in _comparavel(texto_da_ficha)


def sem_rotulo(texto: str) -> str:
    """«R-2/4101 - HIPOTECA de 1º grau.» → «HIPOTECA de 1º grau.» — o rótulo
    já sai em negrito na linha da certidão, e repeti-lo seria ruído."""
    return _ROTULO_NO_COMECO.sub("", normalizar(texto), count=1).strip()


def rotulo_do_trecho(texto: str) -> str:
    m = _ROTULO_EM_QUALQUER_LUGAR.search(normalizar(texto)[:120])
    return re.sub(r"\s+", "", m.group(0)).upper() if m else ""


def _ato_do_rotulo(rotulo: str) -> str:
    """«R-02/2.914» e «R-2» são o mesmo ato: «R2». Vazio quando não há rótulo."""
    m = re.match(r"\s*(R|AV)\s*[-.]?\s*0*(\d+)", rotulo or "", re.I)
    return f"{m.group(1).upper()}{m.group(2)}" if m else ""


def titulo(resultado_onus, resultado_acoes) -> str:
    """O título do papel, na forma das certidões que a casa emitiu em 2024 —
    sem o «DE» que sobrava em «CERTIDÃO DE POSITIVA DE ÔNUS»."""
    o = POSITIVA if resultado_onus == POSITIVA else NEGATIVA
    a = POSITIVA if resultado_acoes == POSITIVA else NEGATIVA
    return (f"Certidão {o.lower()} de ônus e {a.lower()} de registro de ações "
            "reais e pessoais reipersecutórias")


# ------------------------------------------------------- o que o sistema sabe

def _campo(ato, chave):
    try:
        return ato[chave]
    except (KeyError, IndexError, TypeError):
        return None


def categoria(ato) -> str:
    """ÔNUS ou AÇÃO — a natureza estruturada decide; sem ela, a palavra."""
    import ri_onus
    codigo = ri_onus.codigo_da_natureza(_campo(ato, "natureza_titulo"))
    if codigo is not None and codigo not in ri_onus.CODIGOS_SEM_SENTIDO:
        return ACAO if codigo in CODIGOS_DE_ACAO else ONUS
    alvo = _sem_acento(f"{_campo(ato, 'natureza_titulo') or ''} "
                       f"{normalizar(_campo(ato, 'teor'))[:300]}")
    return ACAO if any(t in alvo for t in _TERMOS_DE_ACAO) else ONUS


def item_do_ato(a: dict) -> dict:
    """Um ato que `ri_onus.onus_vigentes` devolveu, na forma da linha da certidão."""
    return {
        "chave": f"ATO:{_campo(a, 'id')}",
        "origem": "SISTEMA",
        "categoria": categoria(a),
        "rotulo": _campo(a, "rotulo") or f"{_campo(a, 'tipo') or ''}-{_campo(a, 'numero') or ''}",
        "natureza": _campo(a, "natureza_titulo") or "",
        "data_extenso": _campo(a, "data_extenso") or "",
        "data_ato": _campo(a, "data_ato") or "",
        "texto": sem_rotulo(_campo(a, "teor")),
        "conferir": bool(_campo(a, "conferir")),
        "literal": True,
    }


def padrao_do_sistema(onus_vigentes: list[dict]) -> dict:
    """O que a certidão diz quando ninguém escolheu: o que `ri_onus` acha nos
    atos lavrados. É o comportamento de antes — e é por isso que a tela nova
    obriga a escolher (o campo `onus_formulario`), em vez de cair aqui calada."""
    itens = [item_do_ato(a) for a in onus_vigentes or []]
    do_onus = [i for i in itens if i["categoria"] == ONUS]
    das_acoes = [i for i in itens if i["categoria"] == ACAO]
    return {"resultado_onus": POSITIVA if do_onus else NEGATIVA,
            "resultado_acoes": POSITIVA if das_acoes else NEGATIVA,
            "itens_onus": do_onus, "itens_acoes": das_acoes,
            "onus_justificativa": "", "onus_escolhido_por": "SISTEMA"}


# --------------------------------------------------------------- a ficha

def texto_da_ficha(con: sqlite3.Connection, matricula_id: int) -> str:
    """Tudo o que a ficha diz: o teor e o teor de cada ato. É contra isto que o
    trecho se confere."""
    m = con.execute("SELECT teor FROM ri_matriculas WHERE id = ?",
                    (matricula_id,)).fetchone()
    partes = [normalizar(m[0]) if m else ""]
    partes += [normalizar(t) for (t,) in con.execute(
        "SELECT teor FROM ri_atos WHERE matricula_id = ? ORDER BY numero, id",
        (matricula_id,))]
    return "\n".join(p for p in partes if p)


def hash_da_ficha(con: sqlite3.Connection, matricula_id: int) -> str:
    """A identidade do que a IA leu: ato novo ou cancelado depois é outra ficha."""
    h = hashlib.sha256()
    m = con.execute("SELECT teor FROM ri_matriculas WHERE id = ?",
                    (matricula_id,)).fetchone()
    h.update(normalizar(m[0] if m else "").encode("utf-8"))
    for tipo, numero, cancelado, teor in con.execute(
            """SELECT tipo, numero, COALESCE(cancelado, 0), teor FROM ri_atos
                WHERE matricula_id = ? ORDER BY numero, id""", (matricula_id,)):
        h.update(f"|{tipo}-{numero}-{cancelado}|{normalizar(teor)}".encode("utf-8"))
    return h.hexdigest()


def dossie(con: sqlite3.Connection, matricula_id: int) -> str:
    m = con.execute("SELECT numero, livro, teor FROM ri_matriculas WHERE id = ?",
                    (matricula_id,)).fetchone()
    if m is None:
        raise OnusError("Matrícula não encontrada.")
    partes = [f"MATRÍCULA nº {m[0]} (livro {m[1] or '2'})", "",
              "TEOR DA FICHA:", normalizar(m[2]) or "(sem teor)", "",
              "ATOS LAVRADOS NO SISTEMA:"]
    atos = con.execute(
        """SELECT tipo, numero, data_ato, natureza_titulo, COALESCE(cancelado, 0), teor
             FROM ri_atos WHERE matricula_id = ? ORDER BY numero, id""",
        (matricula_id,)).fetchall()
    if not atos:
        partes.append("(nenhum — os atos desta ficha estão escritos no teor acima)")
    for tipo, numero, data_ato, natureza, cancelado, teor in atos:
        marca = " [CANCELADO]" if cancelado else ""
        partes.append(f"{tipo}-{numero} ({data_ato or '—'}; natureza: {natureza or '—'})"
                      f"{marca}: {normalizar(teor)}")
    return "\n".join(partes)[:LIMITE_DO_DOSSIE]


# ---------------------------------------------------------------- a leitura

def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _tem_tabela(con, nome: str) -> bool:
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                       (nome,)).fetchone() is not None


def init_schema(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA)


def no_sandbox(con: sqlite3.Connection) -> bool:
    """Esta instalação é o SANDBOX? As duas réguas da casa: a variável de
    ambiente (`centrais_trava_sandbox.e_sandbox`) e o caminho do banco
    (`nu_avisos_gestao.banco_e_sandbox`) — basta uma."""
    import centrais_trava_sandbox as TRAVA
    if TRAVA.e_sandbox():
        return True
    try:
        from nu_avisos_gestao import banco_e_sandbox
        return bool(banco_e_sandbox(con))
    except (ImportError, sqlite3.Error):
        return False


def ligada(con: sqlite3.Connection, pasta_dados: Path) -> bool:
    """Com a chave do provedor da revisão prévia e sem `onus_ia = '0'`.

    **NO SANDBOX NUNCA** — ordem do oficial em 13/10/2026: «nao quero ia na
    sandbox». Ali a escolha positiva/negativa é sempre manual."""
    import agente_provedores as AP
    import revisao_previa as RP
    if no_sandbox(con):
        return False
    if _tem_tabela(con, "settings"):
        linha = con.execute("SELECT value FROM settings WHERE key = ?",
                            (CHAVE_LIGADA,)).fetchone()
        if linha and str(linha[0]).strip() == "0":
            return False
    return AP.tem_chave(pasta_dados, RP.PROVEDOR)


def pedir(con: sqlite3.Connection, matricula_id: int, *, usuario: str = "") -> tuple[int, bool]:
    """(id, nova). A mesma ficha já lida (ou lendo) não se lê de novo."""
    init_schema(con)
    h = hash_da_ficha(con, matricula_id)
    ja = con.execute(
        """SELECT id FROM ri_onus_sugestoes WHERE matricula_id = ? AND hash_ficha = ?
              AND situacao IN ('PENDENTE','LENDO','PRONTA') ORDER BY id DESC""",
        (matricula_id, h)).fetchone()
    if ja:
        return int(ja[0]), False
    cur = con.execute(
        """INSERT INTO ri_onus_sugestoes (matricula_id, hash_ficha, dossie, pedido_em,
               pedido_por) VALUES (?,?,?,?,?)""",
        (matricula_id, h, dossie(con, matricula_id), _agora(), usuario or None))
    return int(cur.lastrowid), True


def _resultado(valor) -> str:
    return POSITIVA if str(valor or "").strip().upper() == POSITIVA else NEGATIVA


def ler_resposta(texto: str, texto_da_ficha_: str) -> dict:
    """O JSON da IA, com cada trecho conferido contra a ficha."""
    m = re.search(r"\{.*\}", texto or "", re.S)
    if not m:
        raise ValueError("a resposta não trouxe JSON")
    d = json.loads(m.group(0))
    itens = []
    for i in d.get("itens") or []:
        if not isinstance(i, dict):
            continue
        trecho = normalizar(i.get("trecho"))
        itens.append({
            "categoria": ACAO if str(i.get("categoria", "")).upper() == ACAO else ONUS,
            "ato": normalizar(i.get("ato"))[:40] or rotulo_do_trecho(trecho),
            "natureza": normalizar(i.get("natureza"))[:160],
            "trecho": trecho,
            "literal": esta_escrito(trecho, texto_da_ficha_),
        })
    cancelados = [{"ato": normalizar(c.get("ato"))[:40],
                   "cancelado_por": normalizar(c.get("cancelado_por"))[:40]}
                  for c in d.get("cancelados") or [] if isinstance(c, dict)]
    return {"onus": _resultado(d.get("onus")), "acoes": _resultado(d.get("acoes")),
            "itens": itens, "cancelados": cancelados,
            "parecer": normalizar(d.get("parecer"))[:800]}


def executar(banco: Path, pasta_dados: Path, sugestao_id: int, conversar=None) -> None:
    """Lê. FALA COM A REDE, com conexão própria e fora de transação de escrita —
    a mesma forma de `revisao_previa.executar`, com o mesmo provedor e modelo."""
    import agente_provedores as AP
    import revisao_previa as RP
    from gestor_expedientes import desmascarar
    conversar = conversar or AP.conversar
    con = sqlite3.connect(str(banco), timeout=30)
    try:
        init_schema(con)
        linha = con.execute("SELECT dossie, matricula_id FROM ri_onus_sugestoes WHERE id = ?",
                            (sugestao_id,)).fetchone()
        if linha is None:
            return
        con.execute("UPDATE ri_onus_sugestoes SET situacao='LENDO', provedor=?, modelo=? "
                    "WHERE id=?", (RP.PROVEDOR, RP.MODELO, sugestao_id))
        con.commit()
        try:
            seguro, mapa = RP.preparar_para_ia(con, linha[0])
            resposta = conversar(pasta_dados, provedor=RP.PROVEDOR, sistema=INSTRUCAO,
                                 conversa=[{"tipo": "user", "texto": seguro}],
                                 ferramentas=[], modelo=RP.MODELO,
                                 maximo_de_saida=MAXIMO_DE_SAIDA)
            texto = desmascarar(resposta.get("texto") or "", mapa)
            r = ler_resposta(texto, texto_da_ficha(con, int(linha[1])))
            con.execute(
                """UPDATE ri_onus_sugestoes SET situacao='PRONTA', terminado_em=?,
                       resultado_json=?, modelo=?, tokens_entrada=?, tokens_saida=?
                    WHERE id=?""",
                (_agora(), json.dumps(r, ensure_ascii=False),
                 resposta.get("modelo") or RP.MODELO, resposta.get("entrada"),
                 resposta.get("saida"), sugestao_id))
        except Exception as erro:                       # noqa: BLE001 — vai à tabela
            con.execute("UPDATE ri_onus_sugestoes SET situacao='ERRO', terminado_em=?, "
                        "erro=? WHERE id=?",
                        (_agora(), f"{type(erro).__name__}: {str(erro)[:300]}", sugestao_id))
        con.commit()
    finally:
        con.close()


def ler_em_segundo_plano(banco: Path, pasta_dados: Path, sugestao_id: int) -> None:
    threading.Thread(target=executar, args=(Path(banco), Path(pasta_dados), sugestao_id),
                     daemon=True, name=f"onus-ia-{sugestao_id}").start()


def _situacao_viva(situacao: str, pedido_em: str | None) -> str:
    """Leitura que passa do prazo sem terminar é tratada como ERRO na tela —
    o servidor pode ter sido reiniciado no meio, e «lendo» para sempre trava
    quem espera."""
    if situacao not in ("PENDENTE", "LENDO") or not pedido_em:
        return situacao
    try:
        idade = (datetime.now() - datetime.fromisoformat(pedido_em)).total_seconds()
    except ValueError:
        return situacao
    return "ERRO" if idade > MINUTOS_PARA_DESISTIR * 60 else situacao


def ultima(con: sqlite3.Connection, matricula_id: int) -> dict | None:
    """A sugestão mais nova desta matrícula. SÓ LÊ — e não cria a tabela, porque
    é chamada pela tela da ficha (GET não abre transação de escrita).

    `vale` diz se ela foi feita sobre a ficha COMO ESTÁ: ato lavrado ou
    cancelado depois dela muda a ficha, e a sugestão velha não decide nada."""
    if not _tem_tabela(con, "ri_onus_sugestoes"):
        return None
    r = con.execute(
        """SELECT id, situacao, resultado_json, erro, pedido_em, pedido_por, hash_ficha,
                  terminado_em
             FROM ri_onus_sugestoes WHERE matricula_id = ? ORDER BY id DESC LIMIT 1""",
        (matricula_id,)).fetchone()
    if r is None:
        return None
    resultado = json.loads(r[2]) if r[2] else {}
    return {"id": r[0], "situacao": _situacao_viva(r[1], r[4]), "erro": r[3],
            "pedido_em": r[4], "pedido_por": r[5], "terminado_em": r[7],
            "vale": r[6] == hash_da_ficha(con, matricula_id), **resultado}


def itens_da_sugestao(sugestao: dict | None) -> list[dict]:
    """Os itens da IA na forma da linha da certidão. Só os de sugestão PRONTA e
    feita sobre a ficha como ela está."""
    if not sugestao or sugestao.get("situacao") != "PRONTA" or not sugestao.get("vale"):
        return []
    saida = []
    for n, i in enumerate(sugestao.get("itens") or [], start=1):
        saida.append({
            "chave": f"IA:{n}", "origem": "IA", "categoria": i.get("categoria") or ONUS,
            "rotulo": i.get("ato") or rotulo_do_trecho(i.get("trecho") or ""),
            "natureza": i.get("natureza") or "", "data": "",
            "texto": sem_rotulo(i.get("trecho") or ""), "trecho": i.get("trecho") or "",
            "conferir": False, "literal": bool(i.get("literal")),
        })
    return saida


# --------------------------------------------------------- a escolha do balcão

def painel(con: sqlite3.Connection, matricula_id: int, onus_vigentes: list[dict],
           pasta_dados: Path | None = None) -> dict:
    """O que a tela da ficha mostra no quadro da certidão de ônus. SÓ LÊ."""
    sistema = [item_do_ato(a) for a in onus_vigentes or []]
    sugestao = ultima(con, matricula_id)
    da_ia = itens_da_sugestao(sugestao)
    # O QUE VEM MARCADO: o que o sistema sabe (ato lavrado com natureza de
    # ônus, ou pela palavra — este com o aviso de conferir) e o que a IA
    # apontou e está escrito na ficha. Item da IA que repete um ato do sistema
    # (mesmo rótulo) não aparece duas vezes.
    do_sistema = {_ato_do_rotulo(i["rotulo"]) for i in sistema} - {""}
    da_ia = [i for i in da_ia if _ato_do_rotulo(i["rotulo"]) not in do_sistema]
    sugerido = {"onus": None, "acoes": None, "por": ""}
    if sugestao and sugestao.get("situacao") == "PRONTA" and sugestao.get("vale"):
        sugerido = {"onus": sugestao.get("onus"), "acoes": sugestao.get("acoes"), "por": "IA"}
    elif sistema:
        padrao = padrao_do_sistema(onus_vigentes)
        sugerido = {"onus": padrao["resultado_onus"] if any(
                        i["categoria"] == ONUS for i in sistema) else None,
                    "acoes": padrao["resultado_acoes"] if any(
                        i["categoria"] == ACAO for i in sistema) else None,
                    "por": "SISTEMA"}
    ligada_ = False
    if pasta_dados is not None:
        try:
            ligada_ = ligada(con, pasta_dados)
        except Exception:                                # noqa: BLE001 — só a tela
            ligada_ = False
    return {"sistema": sistema, "ia": da_ia, "sugestao": sugestao,
            "sugerido": sugerido, "ia_ligada": ligada_,
            "no_sandbox": no_sandbox(con)}


def _justificativa_basta(texto: str) -> bool:
    return len(re.sub(r"[^A-Za-zÀ-ÿ]", "", texto or "")) >= MINIMO_DA_JUSTIFICATIVA


def decidir(*, texto_da_ficha_: str, onus_vigentes: list[dict], sugestao: dict | None,
            resultado_onus, resultado_acoes, marcados, manual_onus: str = "",
            manual_acao: str = "", justificativa: str = "") -> dict:
    """A escolha do escrevente, conferida. Devolve o que o miolo da certidão lê,
    ou recusa com a frase pronta. NÃO GRAVA NADA."""
    ro = str(resultado_onus or "").strip().upper()
    ra = str(resultado_acoes or "").strip().upper()
    if ro not in RESULTADOS:
        raise OnusError("Escolha se a certidão é POSITIVA ou NEGATIVA de ônus. "
                        "Nada foi emitido.")
    if ra not in RESULTADOS:
        raise OnusError("Escolha se há ou não registro de citação de ações reais ou "
                        "pessoais reipersecutórias. Nada foi emitido.")

    sistema = [item_do_ato(a) for a in onus_vigentes or []]
    candidatos = {i["chave"]: i for i in sistema + itens_da_sugestao(sugestao)}
    escolhidos: list[dict] = []
    for chave in marcados or []:
        item = candidatos.get(str(chave))
        if item is None:
            continue
        if not item["literal"]:
            raise OnusError(
                f"O trecho que a IA indicou para {item['rotulo'] or 'um dos ônus'} não está "
                "escrito na ficha, palavra por palavra — ele não vai a uma certidão. "
                "Desmarque-o e, se o ônus existe, cole o texto do ato no campo de "
                "transcrição. Nada foi emitido.")
        escolhidos.append(item)
    for texto, cat in ((manual_onus, ONUS), (manual_acao, ACAO)):
        for bloco in [b for b in re.split(r"\n\s*\n", texto or "") if normalizar(b)]:
            if not esta_escrito(bloco, texto_da_ficha_):
                raise OnusError(
                    "A transcrição colada não está escrita na ficha desta matrícula, "
                    "palavra por palavra. A certidão transcreve o livro: copie o texto "
                    "do ato como ele está no teor. Nada foi emitido.")
            escolhidos.append({"chave": "MANUAL", "origem": "MANUAL", "categoria": cat,
                               "rotulo": rotulo_do_trecho(bloco), "natureza": "",
                               "data": "", "texto": sem_rotulo(bloco),
                               "conferir": False, "literal": True})

    for cat, res, nome in ((ONUS, ro, "ônus"), (ACAO, ra, "registro de ação")):
        do_sistema = [i for i in sistema if i["categoria"] == cat and not i["conferir"]]
        escolhidos_da_cat = [i for i in escolhidos if i["categoria"] == cat]
        if res == NEGATIVA and do_sistema:
            raise OnusError(
                f"A ficha tem {nome} lavrado no sistema e não cancelado "
                f"({', '.join(i['rotulo'] for i in do_sistema)}): a certidão não pode "
                f"ser negativa. Se ele já foi cancelado, averbe o cancelamento antes. "
                "Nada foi emitido.")
        if res == NEGATIVA and escolhidos_da_cat:
            raise OnusError(
                f"Marcou {nome} para transcrever e escolheu NEGATIVA — as duas coisas "
                "não cabem no mesmo papel. Nada foi emitido.")
        if res == POSITIVA and not escolhidos_da_cat:
            raise OnusError(
                f"Certidão POSITIVA de {nome} precisa de ao menos um ato transcrito: "
                "marque o ato ou cole o texto dele. Nada foi emitido.")

    vale = bool(sugestao and sugestao.get("situacao") == "PRONTA" and sugestao.get("vale"))
    contra_a_ia = [nome for chave, res, nome in (("onus", ro, "ônus"), ("acoes", ra, "ações"))
                   if vale and sugestao.get(chave) == POSITIVA and res == NEGATIVA]
    just = normalizar(justificativa)
    if contra_a_ia and not _justificativa_basta(just):
        raise OnusError(
            f"A IA leu a ficha e sugeriu POSITIVA de {' e de '.join(contra_a_ia)}. Para "
            "emitir NEGATIVA, escreva por que (ex.: «hipoteca R-2 cancelada pela AV-5»). "
            "A justificativa fica gravada na certidão. Nada foi emitido.")

    return {"resultado_onus": ro, "resultado_acoes": ra,
            "itens_onus": [i for i in escolhidos if i["categoria"] == ONUS],
            "itens_acoes": [i for i in escolhidos if i["categoria"] == ACAO],
            "onus_justificativa": just if contra_a_ia else "",
            "onus_sugestao_id": sugestao.get("id") if vale else None,
            "onus_escolhido_por": "BALCAO"}
