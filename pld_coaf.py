"""PLD/FTP — o que esta casa deve comunicar ao COAF, e o controle disso.

    «precisamos construir o envio automático para o COAF nos casos que se
     enquadrar a determinação de comunicação pelo código nacional de normas»
                                                    — o oficial, 08/10/2026

A NORMA, LIDA NO PDF QUE ESTÁ NA CASA (`provimento 149 cnj.pdf`, redação do
Provimento CN 161/2024) E NO CÓDIGO DO TJMA:

    DUAS ESPÉCIES DE COMUNICAÇÃO (CNN, art. 151):
      II — INDEPENDENTEMENTE DE ANÁLISE: pagamento ou recebimento EM ESPÉCIE, ou
           por TÍTULO AO PORTADOR, de valor igual ou superior a R$ 100.000,00 —
           Notas (art. 171), Registro de Imóveis (art. 161), RTD/RCPJ (art. 163)
           e Protesto (art. 159). Seleção em até 30 dias da operação; depois,
           comunicação em 24 horas (art. 151, § 1º).
      I  — DEPOIS DE ANÁLISE COM ESPECIAL ATENÇÃO, se a conclusão for de indício:
           as hipóteses do art. 162 (RI; e das Notas pelo art. 172), do art. 164
           (RTD/RCPJ), do art. 160 (Protesto) e os sinais do art. 155-A. Análise
           em até 60 dias; comunicação em 24 horas (art. 151, § 2º). A análise
           se DOCUMENTA, comunique-se ou não (art. 141, § 3º).

    «MOEDA CORRENTE» NÃO É ESPÉCIE — CNN, art. 140, VII, e TJMA, art. 476, III:
    espécie só quando explicitamente discriminada no título. Medido em
    08/10/2026: 28 das 49 escrituras desta casa dizem «moeda corrente» ou
    «dinheiro» no teor; tratar isso como dinheiro vivo mandaria ao COAF quase
    todas as escrituras.

    SIGILO (CNN, art. 154; TJMA, art. 954, parágrafo único): nada disto é do
    balcão. As telas são só do ADMIN, e a auditoria guarda o número do caso, e
    não o nome de ninguém.

    NÃO OCORRÊNCIA (CNN, art. 153): ano civil sem comunicação → declaração à
    Corregedoria-Geral até 31 de janeiro do ano seguinte.

    GUARDA (TJMA, art. 434, § 4º, «h»): recibos e cópias das comunicações ao
    SISCOAF ficam arquivados — o recibo se anexa ao caso.

O QUE ESTE MÓDULO FAZ, E O QUE NÃO
    - SELECIONA sozinho, lendo o teor dos atos lavrados (a seleção é dever da
      serventia, art. 141), e mostra o trecho de onde tirou cada caso.
    - PREPARA o texto da comunicação com o que o art. 154-A exige: motivos,
      dados da operação e das pessoas, e as fontes.
    - CONTA os prazos e REGISTRA o envio (número do COAF e recibo), ou a
      decisão fundamentada de não comunicar.
    - NÃO ENVIA SOZINHO, e as duas razões estão medidas (08/10/2026, página
      «Integração e Webservice» do COAF): (1) o leiaute XML do segmento de
      notários e registradores só se baixa DENTRO do Siscoaf, por usuário
      habilitado, no menu «Comunicar em Lote» — e esta serventia ainda não está
      habilitada; (2) o webservice exige cada chamada ASSINADA com o e-CPF de
      quem está habilitado, e o A3 desta casa derruba o processo que o carrega
      (`assinatura_digital.py`). Escrever o XML sem o leiaute seria inventar
      formato num arquivo que vai a um órgão de inteligência financeira.
    - NÃO DECIDE se há indício: a seleção aponta, quem conclui é o oficial de
      cumprimento (art. 144).
"""
from __future__ import annotations

import re
import sqlite3
from datetime import date, datetime, timedelta
from typing import Any

LIMITE_ESPECIE_CENTAVOS = 100_000_00          # R$ 100.000,00 — arts. 159, 161, 163, 171
DIAS_PARA_SELECIONAR = 30                     # art. 151, § 1º
DIAS_PARA_ANALISAR = 60                       # art. 151, § 2º
MINIMO_DA_FUNDAMENTACAO = 30                  # letras: decisão de não comunicar
CORTE_PADRAO = "2025-01-01"                   # cobre as escrituras de 2025 que a inspeção apontou

AUTOMATICA = "AUTOMATICA"
ANALISE = "ANALISE"

SITUACOES = {
    "A_COMUNICAR": "a comunicar",
    "A_ANALISAR": "a analisar",
    "COMUNICADA": "comunicada",
    "NAO_COMUNICAR": "analisada — sem comunicação",
    "DESCARTADA": "seleção errada",
}

FUNDAMENTO_DA_ESPECIE = {
    "NOTAS": "CNN, art. 171 c/c art. 151, II",
    "RI": "CNN, art. 161 c/c art. 151, II",
    "RTD": "CNN, art. 163 c/c art. 151, II",
    "RCPJ": "CNN, art. 163 c/c art. 151, II",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS pld_casos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    atribuicao TEXT NOT NULL,             -- NOTAS | RI | RTD | RCPJ
    tabela TEXT NOT NULL,                 -- nt_atos | ri_atos | rg_registros
    ato_id INTEGER NOT NULL,
    hipotese TEXT NOT NULL,               -- chave da regra que selecionou
    especie TEXT NOT NULL,                -- AUTOMATICA | ANALISE
    fundamento TEXT NOT NULL,
    descricao TEXT NOT NULL,
    data_operacao TEXT,
    valor_centavos INTEGER,
    trecho TEXT,
    situacao TEXT NOT NULL,
    selecionado_em TEXT NOT NULL,
    analise TEXT,
    analisado_por TEXT,
    analisado_em TEXT,
    texto_comunicacao TEXT,
    numero_coaf TEXT,
    comunicada_em TEXT,
    comunicada_por TEXT,
    UNIQUE (tabela, ato_id, hipotese)
);
"""


class PldError(ValueError):
    """Erro de regra, com a frase pronta para quem opera."""


def init_schema(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA)


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _tem_tabela(con, nome: str) -> bool:
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                       (nome,)).fetchone() is not None


def texto_plano(teor: Any) -> str:
    import html
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", str(teor or ""))).split())


# --------------------------------------------------------------- o dinheiro

_VALOR = re.compile(r"R\$\s*([\d.]{1,15},\d{2})")

#: ESPÉCIE EXPLÍCITA — e só ela (TJMA, art. 476, III). «Moeda corrente»,
#: «moeda de curso legal» e «dinheiro» sozinho NÃO entram.
_ESPECIE = re.compile(
    r"(?i)\b(em\s+esp[ée]cie|dinheiro\s+em\s+esp[ée]cie|dinheiro\s+vivo|"
    r"t[íi]tulos?(\s+de\s+cr[ée]dito)?(\s+emitidos?)?\s+ao\s+portador)\b")
#: «NUMERÁRIO» SAIU NA PRIMEIRA MEDIÇÃO (08/10/2026): os dois estatutos de
#: associação desta casa dizem «fixar o limite máximo de numerário que poderá
#: ser mantido em caixa» — é regra de tesouraria, e não pagamento.
#: Só as negações francas: «sem» e «nem» ficaram de fora porque «sem prejuízo»
#: e companhia são comuns nas escrituras, e uma negação lida errado APAGA um
#: caso de comunicação obrigatória — o erro caro.
_NEGACAO = re.compile(r"(?i)\b(n[ãa]o|nenhum\w*|jamais|inexist\w*)\b[^.;]{0,40}$")


def centavos(texto: str) -> int:
    return int(texto.replace(".", "").replace(",", ""))


def reais(c: int | None) -> str:
    if c is None:
        return "—"
    inteiro, cent = divmod(int(c), 100)
    return "R$ " + f"{inteiro:,}".replace(",", ".") + f",{cent:02d}"


def mencoes_de_especie(texto: str) -> list[dict]:
    """Cada menção explícita a espécie/portador, com o valor mais próximo dela.

    O valor é o «R$» mais perto da menção, num raio de 250 letras — é como as
    escrituras desta casa escrevem («a quantia de R$ 150.000,00, paga em
    espécie»). Sem valor por perto, `valor` vem None, e o caso vai a ANÁLISE
    em vez de virar comunicação automática por um número inventado.
    """
    achados = []
    for m in _ESPECIE.finditer(texto):
        antes = texto[max(0, m.start() - 60):m.start()]
        negada = bool(_NEGACAO.search(antes))
        perto = []
        for v in _VALOR.finditer(texto, max(0, m.start() - 250), m.end() + 250):
            distancia = m.start() - v.end() if v.end() <= m.start() else v.start() - m.end()
            perto.append((abs(distancia), centavos(v.group(1))))
        valor = min(perto)[1] if perto else None
        inicio, fim = max(0, m.start() - 160), min(len(texto), m.end() + 160)
        achados.append({"valor": valor, "negada": negada,
                        "trecho": ("…" if inicio else "") + texto[inicio:fim] +
                                  ("…" if fim < len(texto) else "")})
    return achados


def maior_valor(texto: str) -> int | None:
    valores = [centavos(v) for v in _VALOR.findall(texto)]
    return max(valores) if valores else None


# --------------------------------------------------------------- as regras

_PROCURACAO_AMPLA = re.compile(
    r"(?i)(irrevog[áa]ve|irretrat[áa]ve|isent[ao]s?\s+de\s+presta[çc][ãa]o\s+de\s+contas|"
    r"em\s+causa\s+pr[óo]pria)")
_GESTAO = re.compile(
    r"(?i)(gest[ãa]o|administra[çr]|ger[êe]ncia|movimenta[rç]\w*\s+(de\s+)?conta|"
    r"conta[s]?\s+banc[áa]ria|sociedade|empresa)")
_DOACAO = re.compile(r"(?i)\bdoa[çc][ãa]o\b")
#: A GARANTIA QUE SE CONSTITUI, e não a que se menciona. Medido em 08/10/2026:
#: o título de domínio da matrícula 4017 diz «autorizada a constituição de
#: hipoteca em garantia de financiamentos concedidos por entidades de crédito»
#: — é cláusula de autorização, e a primeira versão a tomou por empréstimo
#: entre particulares.
_GARANTIA = re.compile(
    r"(?i)\b(em\s+hipoteca|hipoteca\s+(de\s+)?(primeiro|segundo|1|2)|"
    r"d[áa]\w*\s+em\s+(primeira\s+|segunda\s+)?hipoteca|"
    r"aliena[çc][ãa]o\s+fiduci[áa]ria\s+(em\s+garantia|do\s+im[óo]vel|do\s+bem)|"
    r"(constitu\w+|institu\w+)\s+(a\s+)?(hipoteca|aliena[çc][ãa]o\s+fiduci[áa]ria)\s+"
    r"(em\s+favor|a\s+favor|ao\s+credor|aos\s+credores))")
_INSTITUICAO = re.compile(
    r"(?i)(banco|caixa\s+econ[ôo]mica|cooperativa|financeira|\bs\s?/\s?a\b|\bs\.a\.|"
    r"cr[ée]dito\s+rural|bndes|pronaf|entidades?\s+de\s+cr[ée]dito|"
    r"institui[çc][ãoõ]\w*\s+financeir|agente\s+financeiro|c[ée]dula\s+(rural|de\s+cr[ée]dito))")
_COMPRA_E_VENDA = re.compile(r"(?i)compra\s+e\s+venda")


def _caso(atribuicao, tabela, ato_id, hipotese, especie, fundamento, descricao,
          data_operacao, valor, trecho, situacao) -> dict:
    return {"atribuicao": atribuicao, "tabela": tabela, "ato_id": ato_id,
            "hipotese": hipotese, "especie": especie, "fundamento": fundamento,
            "descricao": descricao, "data_operacao": data_operacao,
            "valor_centavos": valor, "trecho": (trecho or "")[:900],
            "situacao": situacao}


def casos_do_texto(atribuicao: str, tabela: str, ato_id: int, data_operacao: str,
                   texto: str, *, tipo: str = "", valor_declarado: int | None = None
                   ) -> list[dict]:
    """As hipóteses que o teor de UM ato aciona. Só calcula."""
    saida: list[dict] = []
    # 1. ESPÉCIE OU PORTADOR — a comunicação que independe de análise.
    for m in mencoes_de_especie(texto):
        if m["negada"]:
            continue
        if m["valor"] is None:
            saida.append(_caso(
                atribuicao, tabela, ato_id, "ESPECIE_SEM_VALOR", ANALISE,
                FUNDAMENTO_DA_ESPECIE.get(atribuicao, "CNN, art. 151"),
                "O teor menciona pagamento em espécie ou título ao portador, e não "
                "achei o valor perto da menção — confira no título se é igual ou "
                "superior a R$ 100.000,00.", data_operacao, None, m["trecho"],
                "A_ANALISAR"))
            break
        if m["valor"] >= LIMITE_ESPECIE_CENTAVOS:
            saida.append(_caso(
                atribuicao, tabela, ato_id, "ESPECIE_100MIL", AUTOMATICA,
                FUNDAMENTO_DA_ESPECIE.get(atribuicao, "CNN, art. 151, II"),
                f"Pagamento em espécie ou por título ao portador de {reais(m['valor'])}, "
                f"igual ou superior a R$ 100.000,00: comunica-se independentemente de "
                f"análise.", data_operacao, m["valor"], m["trecho"], "A_COMUNICAR"))
            break
    # 2. AS QUE PEDEM ANÁLISE COM ESPECIAL ATENÇÃO.
    tipo = (tipo or "").upper()
    if atribuicao == "NOTAS" and tipo.startswith("PROCURACAO") and \
            _PROCURACAO_AMPLA.search(texto) and _GESTAO.search(texto):
        m = _PROCURACAO_AMPLA.search(texto)
        saida.append(_caso(
            atribuicao, tabela, ato_id, "PROCURACAO_AMPLA", ANALISE,
            "CNN, art. 155-A, XVI c/c art. 151, I",
            "Procuração com poderes de gestão ou de movimentação, em caráter "
            "irrevogável, irretratável, em causa própria ou isenta de prestação de "
            "contas.", data_operacao, None, texto[max(0, m.start() - 200):m.end() + 200],
            "A_ANALISAR"))
    valor = valor_declarado or maior_valor(texto)
    if atribuicao in ("NOTAS", "RI") and _DOACAO.search(texto) and \
            valor is not None and valor >= LIMITE_ESPECIE_CENTAVOS:
        m = _DOACAO.search(texto)
        saida.append(_caso(
            atribuicao, tabela, ato_id, "DOACAO_100MIL", ANALISE,
            "CNN, art. 162, I" + (" c/c art. 172" if atribuicao == "NOTAS" else ""),
            f"Doação de imóvel com valor de {reais(valor)}: confira se o donatário tem "
            f"vínculo familiar aparente com o doador.", data_operacao, valor,
            texto[max(0, m.start() - 200):m.end() + 200], "A_ANALISAR"))
    g = _GARANTIA.search(texto)
    if atribuicao in ("NOTAS", "RI") and g and not _INSTITUICAO.search(texto):
        saida.append(_caso(
            atribuicao, tabela, ato_id, "GARANTIA_ENTRE_PARTICULARES", ANALISE,
            "CNN, art. 162, II" + (" c/c art. 172" if atribuicao == "NOTAS" else ""),
            "Hipoteca ou alienação fiduciária sem instituição financeira no texto: "
            "confira se é empréstimo entre particulares.", data_operacao, valor,
            texto[max(0, g.start() - 200):g.end() + 200], "A_ANALISAR"))
    return saida


# --------------------------------------------------------------- a seleção

def _atos(con: sqlite3.Connection, desde: str):
    """(atribuicao, tabela, id, data, texto, tipo, valor_declarado) dos atos lavrados."""
    if _tem_tabela(con, "nt_atos"):
        for r in con.execute(
                """SELECT id, data, teor, tipo, valor_transacao FROM nt_atos
                    WHERE situacao <> 'EM_LAVRATURA' AND data >= ?""", (desde,)):
            yield "NOTAS", "nt_atos", r[0], r[1], texto_plano(r[2]), r[3], \
                (int(r[4]) if str(r[4] or "").isdigit() else None)
    if _tem_tabela(con, "ri_atos"):
        for r in con.execute(
                """SELECT id, data_ato, teor, tipo, base_calculo_centavos FROM ri_atos
                    WHERE COALESCE(cancelado, 0) = 0 AND data_ato >= ?""", (desde,)):
            yield "RI", "ri_atos", r[0], r[1], texto_plano(r[2]), r[3], r[4]
    if _tem_tabela(con, "rg_registros"):
        for r in con.execute(
                """SELECT id, criado_em, teor, atribuicao FROM rg_registros
                    WHERE criado_em >= ?""", (desde,)):
            # `atribuicao` é número aqui: 3 = RCPJ, 4 = RTD (rg_schema).
            yield {3: "RCPJ", 4: "RTD"}.get(r[3], "RTD"), "rg_registros", r[0], \
                (r[1] or "")[:10], \
                texto_plano(r[2]), "", None


def _transmissoes_sucessivas(con: sqlite3.Connection, desde: str) -> list[dict]:
    """Duas compras e vendas na mesma matrícula em menos de um ano (art. 162, V)."""
    if not _tem_tabela(con, "ri_atos"):
        return []
    por_matricula: dict[int, list] = {}
    for mid, aid, data_ato, teor in con.execute(
            """SELECT matricula_id, id, data_ato, teor FROM ri_atos
                WHERE COALESCE(cancelado, 0) = 0 AND tipo = 'R' AND data_ato IS NOT NULL
                ORDER BY matricula_id, data_ato"""):
        if _COMPRA_E_VENDA.search(texto_plano(teor)):
            por_matricula.setdefault(mid, []).append((aid, data_ato, texto_plano(teor)))
    saida = []
    for lista in por_matricula.values():
        for (a1, d1, t1), (a2, d2, t2) in zip(lista, lista[1:]):
            try:
                dias = (date.fromisoformat(d2[:10]) - date.fromisoformat(d1[:10])).days
            except ValueError:
                continue
            if d2 >= desde and 0 <= dias <= 365:
                v1, v2 = maior_valor(t1), maior_valor(t2)
                diferenca = ""
                if v1 and v2:
                    diferenca = f" Valores: {reais(v1)} e {reais(v2)}."
                saida.append(_caso(
                    "RI", "ri_atos", a2, "TRANSMISSAO_SUCESSIVA", ANALISE,
                    "CNN, art. 162, V c/c art. 151, I",
                    f"Segunda compra e venda do mesmo imóvel em {dias} dia(s).{diferenca} "
                    f"Confira se o período e a diferença de valor são anormais.",
                    d2[:10], v2, t2[:600], "A_ANALISAR"))
    return saida


def selecionar(con: sqlite3.Connection, *, desde: str = CORTE_PADRAO) -> dict:
    """Lê os atos lavrados desde `desde` e grava os casos novos. ESCREVE.

    Idempotente: o mesmo ato e a mesma hipótese não entram duas vezes, e o
    caso já analisado nunca é tocado por uma seleção nova.
    """
    init_schema(con)
    novos = 0
    vistos = 0
    candidatos: list[dict] = []
    for atrib, tabela, aid, data_op, texto, tipo, valor in _atos(con, desde):
        vistos += 1
        candidatos += casos_do_texto(atrib, tabela, aid, (data_op or "")[:10], texto,
                                     tipo=tipo, valor_declarado=valor)
    candidatos += _transmissoes_sucessivas(con, desde)
    for c in candidatos:
        cur = con.execute(
            """INSERT OR IGNORE INTO pld_casos (atribuicao, tabela, ato_id, hipotese,
                   especie, fundamento, descricao, data_operacao, valor_centavos, trecho,
                   situacao, selecionado_em)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (c["atribuicao"], c["tabela"], c["ato_id"], c["hipotese"], c["especie"],
             c["fundamento"], c["descricao"], c["data_operacao"], c["valor_centavos"],
             c["trecho"], c["situacao"], _agora()))
        novos += cur.rowcount
    return {"atos_lidos": vistos, "selecionados": len(candidatos), "novos": novos}


def abrir_para_analise(con: sqlite3.Connection, *, referencia: str, data_operacao: str,
                       motivo: str, valor_centavos: int | None = None,
                       atribuicao: str = "NOTAS") -> int:
    """Um caso aberto à mão, para o que a seleção não alcança. ESCREVE.

    O caso concreto que pediu isto: as dez escrituras de compra e venda de
    2025–2026 que a inspeção 0000524 mandou reanalisar NÃO ESTÃO NO SISTEMA —
    medido em 08/10/2026, a carga das Notas vai até 2022 e o que se lavrou
    aqui começa em agosto de 2026. Elas existem no acervo do E-Ofício, pelo
    selo; por isso a referência é texto livre (selo, livro, folha).
    """
    init_schema(con)
    referencia = " ".join((referencia or "").split())
    if len(referencia) < 5:
        raise PldError("Diga qual é o ato: selo, livro e folha, ou o número do registro.")
    try:
        date.fromisoformat((data_operacao or "")[:10])
    except ValueError:
        raise PldError("Informe a data do ato (é dela que conta o prazo).") from None
    if len(" ".join((motivo or "").split())) < 10:
        raise PldError("Diga por que o caso vai à análise.")
    proximo = con.execute(
        "SELECT COALESCE(MAX(ato_id), 0) + 1 FROM pld_casos WHERE tabela='manual'"
    ).fetchone()[0]
    cur = con.execute(
        """INSERT INTO pld_casos (atribuicao, tabela, ato_id, hipotese, especie,
               fundamento, descricao, data_operacao, valor_centavos, trecho, situacao,
               selecionado_em)
           VALUES (?, 'manual', ?, 'MANUAL', ?, ?, ?, ?, ?, ?, 'A_ANALISAR', ?)""",
        (atribuicao, proximo, ANALISE, "CNN, art. 141, §§ 1º a 3º c/c art. 151, I",
         " ".join(motivo.split()), data_operacao[:10], valor_centavos, referencia,
         _agora()))
    return int(cur.lastrowid)


# --------------------------------------------------------------- os prazos

def prazo(caso: dict) -> dict:
    """Até quando, e se já passou. Conta da data da operação (art. 151, §§ 1º e 2º)."""
    try:
        base = date.fromisoformat((caso.get("data_operacao") or "")[:10])
    except ValueError:
        return {"limite": None, "vencido": None, "dias": None}
    dias = DIAS_PARA_SELECIONAR if caso["especie"] == AUTOMATICA else DIAS_PARA_ANALISAR
    limite = base + timedelta(days=dias)
    falta = (limite - date.today()).days
    return {"limite": limite.isoformat(), "vencido": falta < 0, "dias": falta}


# --------------------------------------------------------------- a comunicação

def _ato(con: sqlite3.Connection, tabela: str, ato_id: int, caso: dict | None = None) -> dict:
    con.row_factory = sqlite3.Row
    if tabela == "manual":
        return {"rotulo": (caso or {}).get("trecho") or "ato do acervo",
                "data": (caso or {}).get("data_operacao"), "teor": "", "partes": []}
    if tabela == "nt_atos":
        a = con.execute("SELECT * FROM nt_atos WHERE id=?", (ato_id,)).fetchone()
        partes = con.execute(
            """SELECT nome, documento, qualificacao, estado_civil, profissao, endereco
                 FROM nt_ato_partes WHERE ato_id=? AND COALESCE(testemunha,0)=0
                ORDER BY ordem, id""", (ato_id,)).fetchall()
        rotulo = (f"{a['tipo']} — livro {a['livro'] or '—'}, folha {a['folha'] or '—'}"
                  + (f", termo {a['termo']}" if 'termo' in a.keys() and a['termo'] else ""))
        return {"rotulo": rotulo, "data": a["data"], "teor": texto_plano(a["teor"]),
                "partes": [dict(p) for p in partes]}
    if tabela == "ri_atos":
        a = con.execute(
            """SELECT a.*, m.numero matricula FROM ri_atos a
                 JOIN ri_matriculas m ON m.id = a.matricula_id WHERE a.id=?""",
            (ato_id,)).fetchone()
        partes = con.execute(
            """SELECT nome, documento_numero documento, qualificacao, papel
                 FROM ri_partes WHERE ato_id=? ORDER BY id""", (ato_id,)).fetchall()
        return {"rotulo": f"{a['tipo']}-{a['numero']} da matrícula {a['matricula']}",
                "data": a["data_ato"], "teor": texto_plano(a["teor"]),
                "partes": [dict(p) for p in partes]}
    a = con.execute("SELECT * FROM rg_registros WHERE id=?", (ato_id,)).fetchone()
    return {"rotulo": f"{a['atribuicao']} registro {a['numero']}", "data": a["criado_em"],
            "teor": texto_plano(a["teor"]),
            "partes": [{"nome": a["requerente_nome"], "documento": a["requerente_documento"],
                        "qualificacao": "requerente"}]}


def montar_comunicacao(con: sqlite3.Connection, caso_id: int) -> str:
    """O texto do campo «Informações adicionais» do Siscoaf (CNN, art. 154-A).

    Os três itens que o artigo exige, nessa ordem: os MOTIVOS, os DADOS da
    operação e das pessoas, e as FONTES. É um rascunho: quem comunica relê,
    completa e responde por ele.
    """
    c = caso(con, caso_id)
    a = _ato(con, c["tabela"], c["ato_id"], c)
    pessoas = "\n".join(
        f"- {p.get('nome') or '—'}, {p.get('documento') or 'sem documento no cadastro'}"
        f"{', ' + p['qualificacao'] if p.get('qualificacao') else ''}"
        f"{', ' + p['estado_civil'] if p.get('estado_civil') else ''}"
        f"{', ' + p['profissao'] if p.get('profissao') else ''}"
        f"{', ' + p['endereco'] if p.get('endereco') else ''}"
        for p in a["partes"]) or "- (o ato não tem partes cadastradas — complete)"
    motivo = (c["descricao"] if c["especie"] == AUTOMATICA else
              (c["analise"] or "[ESCREVA A ANÁLISE: por que se concluiu pelo indício]"))
    return (
        f"1. MOTIVOS ({c['fundamento']}):\n{motivo}\n\n"
        f"2. DADOS DA OPERAÇÃO:\nAto: {a['rotulo']}, de {(a['data'] or '')[:10]}.\n"
        f"Valor: {reais(c['valor_centavos'])}.\n"
        f"Trecho do título: «{c['trecho']}»\n\n"
        f"Pessoas envolvidas:\n{pessoas}\n\n"
        f"3. FONTES: teor do ato lavrado ({a['rotulo']}), e o título e os documentos "
        f"apresentados pelas partes e arquivados na serventia.")


def caso(con: sqlite3.Connection, caso_id: int) -> dict:
    init_schema(con)
    con.row_factory = sqlite3.Row
    r = con.execute("SELECT * FROM pld_casos WHERE id=?", (caso_id,)).fetchone()
    if r is None:
        raise PldError("Caso não encontrado.")
    return dict(r) | {"prazo": prazo(dict(r))}


def casos(con: sqlite3.Connection, situacao: str | None = None) -> list[dict]:
    init_schema(con)
    con.row_factory = sqlite3.Row
    if situacao:
        linhas = con.execute("SELECT * FROM pld_casos WHERE situacao=? ORDER BY data_operacao",
                             (situacao,)).fetchall()
    else:
        linhas = con.execute("SELECT * FROM pld_casos ORDER BY data_operacao DESC").fetchall()
    return [dict(r) | {"prazo": prazo(dict(r))} for r in linhas]


def resumo(con: sqlite3.Connection) -> dict:
    init_schema(con)
    contagem = dict(con.execute(
        "SELECT situacao, COUNT(*) FROM pld_casos GROUP BY situacao").fetchall())
    vencidos = sum(1 for c in casos(con) if c["situacao"] in ("A_COMUNICAR", "A_ANALISAR")
                   and c["prazo"]["vencido"])
    return {"por_situacao": contagem, "vencidos": vencidos}


# --------------------------------------------------------------- as decisões

def concluir_analise(con: sqlite3.Connection, caso_id: int, *, comunicar: bool,
                     fundamentacao: str, usuario: str) -> None:
    """A análise documentada (art. 141, § 3º). ESCREVE."""
    c = caso(con, caso_id)
    if c["situacao"] in ("COMUNICADA",):
        raise PldError("Este caso já foi comunicado; a análise não se refaz.")
    texto = " ".join((fundamentacao or "").split())
    if len(texto) < MINIMO_DA_FUNDAMENTACAO:
        raise PldError(
            f"Escreva a análise com os elementos objetivos que levaram à conclusão "
            f"(pelo menos {MINIMO_DA_FUNDAMENTACAO} letras) — ela fica à disposição da "
            f"Corregedoria, comunique-se ou não (CNN, art. 141, § 3º).")
    if c["especie"] == AUTOMATICA and not comunicar:
        raise PldError(
            "Pagamento em espécie ou ao portador de R$ 100.000,00 ou mais se comunica "
            "independentemente de análise (CNN, art. 151, II). Se a seleção leu errado o "
            "título, use «a seleção leu errado», dizendo o que o título diz de fato.")
    con.execute(
        """UPDATE pld_casos SET analise=?, analisado_por=?, analisado_em=?, situacao=?
            WHERE id=?""",
        (texto, usuario, _agora(), "A_COMUNICAR" if comunicar else "NAO_COMUNICAR",
         caso_id))


def descartar(con: sqlite3.Connection, caso_id: int, *, motivo: str, usuario: str) -> None:
    """A seleção leu errado o título (ex.: o valor achado não era o pago em espécie)."""
    c = caso(con, caso_id)
    if c["situacao"] == "COMUNICADA":
        raise PldError("Caso comunicado não se descarta.")
    texto = " ".join((motivo or "").split())
    if len(texto) < MINIMO_DA_FUNDAMENTACAO:
        raise PldError(f"Diga o que o título diz de fato (pelo menos "
                       f"{MINIMO_DA_FUNDAMENTACAO} letras) — o descarte fica documentado.")
    con.execute("""UPDATE pld_casos SET analise=?, analisado_por=?, analisado_em=?,
                       situacao='DESCARTADA' WHERE id=?""",
                (texto, usuario, _agora(), caso_id))


def guardar_texto(con: sqlite3.Connection, caso_id: int, texto: str) -> None:
    caso(con, caso_id)
    con.execute("UPDATE pld_casos SET texto_comunicacao=? WHERE id=?",
                ((texto or "").strip() or None, caso_id))


def registrar_envio(con: sqlite3.Connection, caso_id: int, *, numero_coaf: str,
                    data_envio: str, usuario: str) -> None:
    """O que o Siscoaf devolveu. ESCREVE. Sem número, não se dá por comunicado."""
    c = caso(con, caso_id)
    if c["situacao"] != "A_COMUNICAR":
        raise PldError("Só se registra envio de caso que está «a comunicar».")
    numero = (numero_coaf or "").strip()
    if not re.search(r"\d", numero):
        raise PldError("Informe o número que o Siscoaf devolveu para a comunicação — "
                       "é ele que prova o envio.")
    try:
        date.fromisoformat((data_envio or "")[:10])
    except ValueError:
        raise PldError("Informe a data do envio.") from None
    con.execute("""UPDATE pld_casos SET numero_coaf=?, comunicada_em=?, comunicada_por=?,
                       situacao='COMUNICADA' WHERE id=?""",
                (numero, data_envio[:10], usuario, caso_id))


# --------------------------------------------------------------- o ano sem nada

def nao_ocorrencia(con: sqlite3.Connection, ano: int, sv: dict | None = None) -> dict:
    """Se o ano pede a comunicação de não ocorrência (CNN, art. 153), e o texto.

    Pede quando o ano NÃO teve comunicação e não sobra caso pendente dele — caso
    a comunicar ou a analisar ainda pode virar comunicação, e declarar «nada»
    antes de concluí-lo seria declarar o que não se sabe.
    """
    init_schema(con)
    inicio, fim = f"{ano}-01-01", f"{ano}-12-31"
    comunicadas = con.execute(
        """SELECT COUNT(*) FROM pld_casos WHERE situacao='COMUNICADA'
              AND data_operacao BETWEEN ? AND ?""", (inicio, fim)).fetchone()[0]
    pendentes = con.execute(
        """SELECT COUNT(*) FROM pld_casos WHERE situacao IN ('A_COMUNICAR','A_ANALISAR')
              AND data_operacao BETWEEN ? AND ?""", (inicio, fim)).fetchone()[0]
    sv = sv or {}
    texto = (
        f"COMUNICAÇÃO DE NÃO OCORRÊNCIA — CNN (Provimento CNJ 149/2023), art. 153.\n\n"
        f"À Corregedoria-Geral da Justiça do Estado do Maranhão.\n\n"
        f"{sv.get('serventia_titulo') or 'O titular'} da {sv.get('unit_name') or 'serventia'}, "
        f"CNS {sv.get('cns') or '______'}, na qualidade de oficial de cumprimento, "
        f"comunica que, ao longo do ano civil de {ano}, não foi identificada nenhuma "
        f"operação, proposta de operação ou situação que devesse ser comunicada à "
        f"Unidade de Inteligência Financeira (Coaf) na forma do art. 151 do Código "
        f"Nacional de Normas.\n\n"
        f"{sv.get('ri_cidade') or '__________'}/{sv.get('ri_uf') or '__'}, ____ de "
        f"janeiro de {ano + 1}.\n\n_________________________________\n"
        f"{sv.get('serventia_titular') or ''}")
    return {"ano": ano, "comunicadas": comunicadas, "pendentes": pendentes,
            "cabe": comunicadas == 0 and pendentes == 0,
            "prazo": f"{ano + 1}-01-31", "texto": texto}
