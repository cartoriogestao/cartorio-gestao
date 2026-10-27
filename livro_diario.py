"""O Livro Diário Auxiliar da Receita e da Despesa — arts. 188, II, e 190 a 207 do
Código de Normas do MA.

POR QUE EXISTE (LG08, 19/10/2026)
    É livro obrigatório de TODA serventia (art. 188, II). Medido no código em
    19/10/2026: não existia, e não havia sequer onde lançar uma despesa — o
    relatório financeiro (`gestor_financeiro`) diz isso na própria docstring,
    e a agenda do oficial (`oficial_obrigacoes`) tinha o livro como pergunta
    «a confirmar», porque nenhum documento desta casa dava o prazo. O Código
    de Normas dá: gerado mensalmente até o 5º dia útil do mês seguinte (art.
    205) e encaminhado até o primeiro dia útil de maio (art. 207).

A RECEITA SAI DO SELO, E NÃO DO CAIXA
    O art. 190, I, manda lançar a receita «no dia da prática do ato,
    separadamente, por especialidade e individualmente por ato», com o código
    do ato, o tipo e o código do selo e os valores discriminados. O caixa não
    sabe o dia da prática: ele sabe o dia em que o dinheiro entrou, e mistura
    depósito prévio, troco e uso de depósito na mesma natureza (medido em
    06/10/2026, `gestor_financeiro`). O SELO sabe: `sd_selos.usado_em` é o dia
    em que o ato ficou pronto, e o texto do selo declara ato, emolumentos e
    fundos — «o número confiável deles é o que o SELO declara». É dele que a
    receita sai, um selo por linha.

    Receita, para o livro, é EMOLUMENTO (art. 191): fundo e imposto não são
    receita da serventia, e por isso aparecem em coluna própria e ficam fora
    da receita bruta. Selo ISENTO aparece (o ato foi praticado) com o valor
    que teria, mas não soma receita; selo DIFERIDO também não — o emolumento
    diferido entra como receita no pagamento (arts. 193 e 204), e isso o
    sistema não sabe: a tela diz quantos houve. Selo do ambiente de
    homologação não é ato praticado e não entra.

    O FERJ (art. 190, I, k) é a exceção: ele não está no selo, porque não é
    cobrado por cima — são 12% que saem de DENTRO do emolumento e a serventia
    recolhe por guia. A coluna dele se calcula do emolumento de cada ato, com o
    percentual configurado (`custas.percentual_ferj`), e não mexe na receita.

A DESPESA SE LANÇA AQUI
    No dia do efetivo pagamento, com descrição detalhada, espécie e número do
    documento e valor (art. 190, II). Não se edita nem se apaga: despesa
    lançada errada se ANULA, com o motivo, e a linha continua no histórico.

GERAR O MÊS TRAVA O MÊS (arts. 205 e 206)
    «O Livro Diário Auxiliar da Receita e da Despesa será gerado mensalmente,
    até o 5º (quinto) dia útil do mês subsequente» e «é vedada a nova geração
    do Livro Diário Auxiliar, salvo para retificação necessária, que deverá ser
    circunstanciada, mantendo-se o histórico dos lançamentos retificados».

    Por isso gerar GRAVA uma fotografia do mês (`ld_geracoes.conteudo`, com o
    hash), e a impressão sai dessa fotografia, e não do movimento de hoje.
    Gerar de novo só com o motivo da retificação, e a versão anterior fica
    guardada. Se o movimento mudar depois de gerado (um selo cancelado, uma
    despesa anulada), a tela AVISA que o livro gerado e o movimento divergem —
    quem decide retificar é o oficial.

O QUE O SISTEMA NÃO TEM, E O LIVRO DIZ QUE NÃO TEM
    `FORA_DO_SISTEMA` lista o que o art. 190 pede e não há onde ler aqui. Sai
    impresso no próprio livro: livro que omite coluna sem dizer parece livro
    com a coluna zerada.

PostgreSQL nativo, pelo `bd_nativo` (MANUAL_DA_CONVERSAO). Dinheiro em
centavos, `bigint`. Data e hora se calculam no Python (regra da casa).
"""
from __future__ import annotations

import calendar
import hashlib
import json
import re
from datetime import date
from typing import Any

import custas
import selo as SL
from bd_nativo import banco
from caixa_schema import centavos, reais
# A ESPECIALIDADE DO SELO é a régua do relatório financeiro, e não uma segunda:
# duas tabelas de «IMOVEL é RI» divergiriam na primeira atribuição nova.
from gestor_financeiro import _ATRIB_DO_SELO as ESPECIALIDADE_DO_SELO
from ri_schema import soma_dias_uteis

# Os fundos que o SELO declara, na ordem dele; o ISS só aparece quando o selo
# o declara.
FUNDOS_DO_SELO: tuple[tuple[str, str], ...] = (
    ("FERC", "FERC"),
    ("FADP", "FADEP"),
    ("FEMP", "FEMP"),
    ("FERRFIS", "FERRFIS"),
    ("ISS", "ISSQN"),
)

# O FERJ DO ART. 190, I, k, NÃO É O FERC — correção do oficial em 25/10/2026:
# «ferj e ferc são diferentes. ferj é uns 12%, ferc é 3%, mas não abate dos
# emolumentos». Até aqui a coluna do FERC se chamava «FERJ (FERC no selo)», e
# o comentário dizia que os dois eram o mesmo fundo. Não são: o FERC são os 3%
# cobrados por cima do emolumento, que o selo declara; o FERJ é a taxa de
# fiscalização de 12% que sai de DENTRO do emolumento, e o selo não o traz.
# Por isso ele não se lê: se calcula, ato por ato, com a régua de `custas`
# (a mesma da NFS-e), e o percentual usado vai gravado no livro.
FERJ = "FERJ"
FUNDOS: tuple[tuple[str, str], ...] = ((FERJ, "FERJ"),) + FUNDOS_DO_SELO

NORMAL, ISENTO, DIFERIDO = "Normal", "Isento", "Diferido"

# O que o art. 190 pede e o sistema não tem de onde ler. Sai no livro.
FORA_DO_SISTEMA: tuple[str, ...] = (
    "ISSQN por ato (art. 190, I, l): só quando o texto do selo o declara; o "
    "sistema não guarda o imposto do ato.",
    "Número e folha do livro (art. 190, I, g) e base legal do valor (I, h): o "
    "selo não os traz; a referência do ato vai na coluna «Protocolo/ato».",
    "Ressarcimento de atos gratuitos, renda mínima e serviços autorizados "
    "(art. 190, III, b a d; art. 192): não há onde lançar no sistema.",
    "Emolumento diferido (arts. 193 e 204): entra como receita no pagamento; "
    "o sistema só conta quantos selos diferidos houve.",
    # O ESPAÇO DO IMPOSTO DE RENDA (VII) mudou de frase em 26/10/2026: a conta
    # do titular passou a existir (`carne_leao`), mas é PESSOAL e só do ADMIN,
    # e por isso não se imprime no livro da serventia.
    "Espaços de intervenção e interinidade (art. 190, V e VI): não se aplicam "
    "ao delegatário titular. O do imposto de renda (VII) não sai neste livro: "
    "a apuração mensal do titular fica em Administrativo → Carnê-leão, só para "
    "o oficial.",
)

MINIMO_DO_TEXTO = 10
LIMITE = 300
TRAVA = "ld_geracoes.competencia"

# Dígito ASCII, e não `\d`: o `\d` do Python aceita «٢٠٢٦», que o `int()` lê
# mas que o texto ISO de `usado_em` nunca iguala — o mês sairia vazio.
_COMPETENCIA = re.compile(r"([0-9]{4})-([0-9]{2})")


class DiarioError(ValueError):
    """Impedimento de regra, com a frase pronta para a tela."""


# ---------------------------------------------------------------- esquema

SCHEMA: tuple[tuple[str, str], ...] = (
    ("ld_despesas", """
        CREATE TABLE IF NOT EXISTS ld_despesas (
            id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            data TEXT NOT NULL,
            descricao TEXT NOT NULL,
            documento_especie TEXT NOT NULL,
            documento_numero TEXT NOT NULL DEFAULT '',
            valor bigint NOT NULL CHECK (valor > 0),
            lancado_em TEXT NOT NULL,
            lancado_por TEXT NOT NULL,
            anulada_em TEXT,
            anulada_por TEXT NOT NULL DEFAULT '',
            motivo_anulacao TEXT NOT NULL DEFAULT ''
        )"""),
    ("ix_ld_despesas_data",
     "CREATE INDEX IF NOT EXISTS ix_ld_despesas_data ON ld_despesas (data, id)"),
    ("ld_geracoes", """
        CREATE TABLE IF NOT EXISTS ld_geracoes (
            id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            competencia TEXT NOT NULL,
            versao bigint NOT NULL,
            gerado_em TEXT NOT NULL,
            gerado_por TEXT NOT NULL,
            motivo TEXT NOT NULL DEFAULT '',
            receita_bruta bigint NOT NULL,
            despesas bigint NOT NULL,
            receita_liquida bigint NOT NULL,
            conteudo TEXT NOT NULL,
            hash TEXT NOT NULL
        )"""),
    ("ux_ld_geracoes_versao",
     "CREATE UNIQUE INDEX IF NOT EXISTS ux_ld_geracoes_versao "
     "ON ld_geracoes (competencia, versao)"),
)


def init_livro_diario_schema(con) -> None:
    """Cria as tabelas e os índices que faltarem. Idempotente."""
    bd = banco(con)
    for nome, comando in SCHEMA:
        if not bd.tem_tabela(nome):
            bd.escrever(comando)


# ------------------------------------------------------------- auxiliares


def _texto(valor: Any, limite: int = LIMITE) -> str:
    return " ".join(str(valor or "").split())[:limite]


def competencia(valor: Any) -> str:
    """'AAAA-MM' conferido. Mês fora de 1 a 12 não é competência."""
    m = _COMPETENCIA.fullmatch(str(valor or "").strip()[:7])
    if not m or not 1 <= int(m.group(2)) <= 12 or int(m.group(1)) < 1:
        raise DiarioError("Informe o mês no formato AAAA-MM.")
    return m.group(0)


def _limites(comp: str) -> tuple[str, str]:
    """O primeiro dia do mês e o primeiro do mês seguinte — o intervalo que o
    texto ISO de `usado_em` e `data` compara certo, com hora ou sem."""
    ano, mes = int(comp[:4]), int(comp[5:7])
    seguinte = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
    return f"{comp}-01", f"{seguinte[0]:04d}-{seguinte[1]:02d}-01"


def prazo_de_geracao(comp: str, feriados_locais: set[date] | None = None) -> date:
    """O 5º dia útil do mês seguinte (art. 205). Só calcula."""
    ano, mes = int(comp[:4]), int(comp[5:7])
    ultimo = date(ano, mes, calendar.monthrange(ano, mes)[1])
    return soma_dias_uteis(ultimo, 5, feriados_locais)


def _cent(valor: Any) -> int | None:
    """Reais lidos do selo (float) em centavos. None continua None: «não sei»
    não é zero (`selo.ler_texto`)."""
    if valor is None:
        return None
    return int(round(float(valor) * 100))


def _dia(valor: Any, *, hoje: str) -> str:
    texto = str(valor or "").strip()[:10]
    try:
        dia = date.fromisoformat(texto)
    except ValueError as erro:
        raise DiarioError("A data do pagamento não é uma data válida.") from erro
    if dia.isoformat() > hoje:
        raise DiarioError(
            "A data do pagamento está no futuro: a despesa se lança no dia do "
            "efetivo pagamento (art. 190, II).")
    return dia.isoformat()


# ---------------------------------------------------------------- despesas


def lancar_despesa(con, *, hoje: str, agora: str, por: str, data: Any,
                   descricao: Any, documento_especie: Any, valor: Any,
                   documento_numero: Any = "") -> int:
    """Lança uma despesa (art. 190, II). ESCREVE. Devolve o id."""
    descricao = _texto(descricao)
    if len(descricao) < MINIMO_DO_TEXTO:
        raise DiarioError(
            "Descreva a despesa em detalhe (art. 190, II, b): o que foi pago e "
            "a quem.")
    especie = _texto(documento_especie, 80)
    if not especie:
        raise DiarioError(
            "Informe a espécie do documento que comprova a despesa (nota "
            "fiscal, recibo, guia…) — art. 190, II, c.")
    cent = centavos(valor)
    if cent <= 0:
        raise DiarioError("Informe um valor maior que zero.")
    novo = banco(con).escrever(
        """INSERT INTO ld_despesas (data, descricao, documento_especie,
               documento_numero, valor, lancado_em, lancado_por)
           VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (_dia(data, hoje=hoje), descricao, especie, _texto(documento_numero, 80),
         cent, agora, _texto(por) or "?"))
    return int(novo[0]["id"])


def anular_despesa(con, despesa_id: int, *, agora: str, por: str, motivo: Any) -> dict:
    """Anula a despesa, com o motivo. A linha fica. ESCREVE."""
    motivo = _texto(motivo, 1000)
    if len(motivo) < MINIMO_DO_TEXTO:
        raise DiarioError(
            f"Diga por que a despesa está sendo anulada (pelo menos "
            f"{MINIMO_DO_TEXTO} letras).")
    bd = banco(con)
    bd._escrita()
    linha = bd.um("SELECT * FROM ld_despesas WHERE id = %s FOR UPDATE", (despesa_id,))
    if not linha:
        raise DiarioError("Despesa não encontrada.")
    if linha["anulada_em"]:
        raise DiarioError("Esta despesa já está anulada.")
    bd.escrever(
        """UPDATE ld_despesas SET anulada_em = %s, anulada_por = %s,
                  motivo_anulacao = %s WHERE id = %s""",
        (agora, _texto(por) or "?", motivo, despesa_id))
    return {"id": int(linha["id"]), "data": linha["data"], "valor": int(linha["valor"])}


def despesas_do_mes(con, comp: str, *, com_anuladas: bool = False) -> list[dict]:
    """As despesas do mês, na ordem do pagamento. Só LÊ."""
    inicio, fim = _limites(competencia(comp))
    filtro = "" if com_anuladas else " AND anulada_em IS NULL"
    return banco(con).ler(
        "SELECT * FROM ld_despesas WHERE data >= %s AND data < %s" + filtro
        + " ORDER BY data, id", (inicio, fim))


# ---------------------------------------------------------------- receitas


def _descricoes(bd) -> dict[str, str]:
    """O nome do ato pelo código da tabela do TJMA — o primeiro serviço com
    aquele código. O selo traz o código; o nome é do catálogo da casa."""
    if not bd.tem_tabela("cx_servicos"):
        return {}
    saida: dict[str, str] = {}
    for x in bd.ler("""SELECT codigo_tj, descricao FROM cx_servicos
                        WHERE codigo_tj IS NOT NULL ORDER BY codigo_tj, codigo"""):
        saida.setdefault(str(x["codigo_tj"]).strip(), x["descricao"] or "")
    return saida


def receitas_do_mes(con, comp: str, pct_ferj: int | None = None) -> list[dict]:
    """Um selo usado no mês por linha, com o que ele declara e o FERJ que sai
    do emolumento dele (`pct_ferj` em centésimos de ponto; sem ele, o da
    casa). Só LÊ."""
    inicio, fim = _limites(competencia(comp))
    bd = banco(con)
    if not bd.tem_tabela("sd_selos"):
        return []
    if pct_ferj is None:
        pct_ferj = custas.percentual_ferj_da_casa(bd)
    nomes = _descricoes(bd)
    saida = []
    for s in bd.ler(
            """SELECT id, numero, texto, atribuicao, referencia, tabela, ato_id, usado_em
                 FROM sd_selos
                WHERE usado_em >= %s AND usado_em < %s
                  AND cancelado_em IS NULL AND ambiente = 'PRODUCAO'
                ORDER BY usado_em, id""", (inicio, fim)):
        lido = SL.ler_texto(s["texto"] or "")
        marcas = " ".join(lido.get("marcas") or []).upper()
        tipo = ISENTO if "ISENT" in marcas else DIFERIDO if "DIFERID" in marcas else NORMAL
        fundos = lido.get("fundos") or {}
        emol = _cent(lido.get("emolumentos"))
        ato = lido.get("ato") or ""
        referencia = _texto(s["referencia"], 80) or (
            f"{s['tabela']} {s['ato_id']}" if s["tabela"] else "")
        saida.append({
            "dia": str(s["usado_em"])[:10],
            "especialidade": ESPECIALIDADE_DO_SELO.get(s["atribuicao"] or "",
                                                       s["atribuicao"] or "?"),
            "ato": ato,
            "descricao": nomes.get(ato, ""),
            "tipo": tipo,
            "selo": s["numero"],
            "referencia": referencia,
            "emolumentos": emol,
            # Selo sem valor não tem de onde tirar o FERJ: «—», e não zero.
            "fundos": {FERJ: (None if emol is None
                              else custas.ferj_do_emolumento(emol, pct_ferj)),
                       **{f: _cent(fundos.get(f)) for f, _ in FUNDOS_DO_SELO}},
            "sem_valor": emol is None,
            # Receita é o emolumento do ato praticado e cobrado (art. 191).
            "receita": (emol or 0) if tipo == NORMAL else 0,
        })
    return saida


# --------------------------------------------------------------- apuração


def apurar(con, comp: str) -> dict:
    """O livro do mês: dia a dia, com totais diários e acumulados, e o
    demonstrativo mensal (art. 190, III e IV). Só LÊ.

    O resultado é JSON puro (texto e inteiro): é ele que a geração grava.
    """
    comp = competencia(comp)
    pct_ferj = custas.percentual_ferj_da_casa(con)
    receitas = receitas_do_mes(con, comp, pct_ferj)
    despesas = [{"dia": d["data"], "id": int(d["id"]), "descricao": d["descricao"],
                 "documento": " ".join(x for x in (d["documento_especie"],
                                                   d["documento_numero"]) if x),
                 "valor": int(d["valor"])}
                for d in despesas_do_mes(con, comp)]
    dias = sorted({r["dia"] for r in receitas} | {d["dia"] for d in despesas})
    acumulada_receita = acumulada_despesa = 0
    acumulados_fundos = {f: 0 for f, _ in FUNDOS}
    livro = []
    for dia in dias:
        rec = [r for r in receitas if r["dia"] == dia]
        rec.sort(key=lambda r: (r["especialidade"], r["selo"]))
        des = [d for d in despesas if d["dia"] == dia]
        receita_dia = sum(r["receita"] for r in rec)
        fundos_dia = {f: sum((r["fundos"][f] or 0) for r in rec if r["tipo"] == NORMAL)
                      for f, _ in FUNDOS}
        despesa_dia = sum(d["valor"] for d in des)
        acumulada_receita += receita_dia
        acumulada_despesa += despesa_dia
        for f in acumulados_fundos:
            acumulados_fundos[f] += fundos_dia[f]
        livro.append({
            "dia": dia, "receitas": rec, "despesas": des,
            "receita_dia": receita_dia, "fundos_dia": fundos_dia,
            "despesa_dia": despesa_dia,
            "receita_acumulada": acumulada_receita,
            "despesa_acumulada": acumulada_despesa,
            "fundos_acumulados": dict(acumulados_fundos),
            # «Transporte dos valores diários para o dia seguinte» (art. 190,
            # III, h): o saldo do mês até aqui.
            "transporte": acumulada_receita - acumulada_despesa,
        })
    por_especialidade: dict[str, int] = {}
    for r in receitas:
        por_especialidade[r["especialidade"]] = (
            por_especialidade.get(r["especialidade"], 0) + r["receita"])
    return {
        "competencia": comp,
        "dias": livro,
        "por_especialidade": dict(sorted(por_especialidade.items())),
        "atos": len(receitas),
        "isentos": sum(1 for r in receitas if r["tipo"] == ISENTO),
        "diferidos": sum(1 for r in receitas if r["tipo"] == DIFERIDO),
        "sem_valor": sum(1 for r in receitas if r["sem_valor"]),
        "fundos": acumulados_fundos,
        # O percentual com que a coluna do FERJ foi calculada, em centésimos
        # de ponto: a fotografia gerada diz com que régua saiu.
        "ferj_percentual": pct_ferj,
        "receita_bruta": acumulada_receita,
        "despesas": acumulada_despesa,
        "receita_liquida": acumulada_receita - acumulada_despesa,
    }


def _hash(conteudo: dict) -> str:
    texto = json.dumps(conteudo, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _sem_ferj(conteudo: dict) -> dict:
    """A apuração na forma de antes da coluna do FERJ (25/10/2026): sem o
    percentual e sem a chave FERJ nos fundos. Só calcula, sobre uma cópia.

    Serve para uma pergunta só: o livro gerado antes da correção confere com
    o movimento de hoje? O hash dele foi tirado sem o FERJ, e comparar com a
    apuração nova acusaria «o movimento mudou» num mês em que nada mudou."""
    velho = json.loads(json.dumps(conteudo))
    velho.pop("ferj_percentual", None)
    velho["fundos"].pop(FERJ, None)
    for dia in velho["dias"]:
        dia["fundos_dia"].pop(FERJ, None)
        dia["fundos_acumulados"].pop(FERJ, None)
        for r in dia["receitas"]:
            r["fundos"].pop(FERJ, None)
    return velho


# ---------------------------------------------------------------- geração


def gerar(con, comp: Any, *, hoje: str, agora: str, por: str, motivo: Any = "") -> dict:
    """Grava a fotografia do mês (art. 205). A segunda vez só com motivo, e a
    anterior fica guardada (art. 206). ESCREVE.

    A trava é por assunto e vem ANTES de ler a última versão: dois cliques em
    «gerar» não fazem duas versões 1.
    """
    comp = competencia(comp)
    if comp >= str(hoje)[:7]:
        raise DiarioError(
            f"O mês {comp[5:7]}/{comp[:4]} ainda não acabou. O livro se gera "
            f"depois do último dia do mês (art. 205).")
    motivo = _texto(motivo, 2000)
    bd = banco(con)
    bd.travar(TRAVA)
    ultima = bd.um(
        """SELECT versao, hash FROM ld_geracoes WHERE competencia = %s
            ORDER BY versao DESC LIMIT 1""", (comp,))
    if ultima and len(motivo) < MINIMO_DO_TEXTO:
        raise DiarioError(
            f"O livro de {comp[5:7]}/{comp[:4]} já foi gerado. Gerar de novo é "
            f"retificação, e ela tem de ser circunstanciada (art. 206): "
            f"escreva o que muda e por quê.")
    conteudo = apurar(bd, comp)
    versao = int(ultima["versao"]) + 1 if ultima else 1
    novo = bd.escrever(
        """INSERT INTO ld_geracoes (competencia, versao, gerado_em, gerado_por,
               motivo, receita_bruta, despesas, receita_liquida, conteudo, hash)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (comp, versao, agora, _texto(por) or "?", motivo if ultima else "",
         conteudo["receita_bruta"], conteudo["despesas"], conteudo["receita_liquida"],
         json.dumps(conteudo, ensure_ascii=False, sort_keys=True), _hash(conteudo)))
    return {"id": int(novo[0]["id"]), "competencia": comp, "versao": versao,
            "receita_bruta": conteudo["receita_bruta"],
            "despesas": conteudo["despesas"]}


def geracoes(con, comp: str) -> list[dict]:
    """As versões geradas do mês, a mais nova primeiro. Só LÊ."""
    return banco(con).ler(
        """SELECT id, competencia, versao, gerado_em, gerado_por, motivo,
                  receita_bruta, despesas, receita_liquida, hash
             FROM ld_geracoes WHERE competencia = %s
            ORDER BY versao DESC""", (competencia(comp),))


def geracao(con, geracao_id: int) -> dict | None:
    """Uma versão gerada, com a fotografia lida de volta. Só LÊ."""
    linha = banco(con).um("SELECT * FROM ld_geracoes WHERE id = %s", (geracao_id,))
    if not linha:
        return None
    linha["livro"] = json.loads(linha["conteudo"])
    linha["integra"] = _hash(linha["livro"]) == linha["hash"]
    return linha


def situacao_do_mes(con, comp: str, *, hoje: str,
                    feriados_locais: set[date] | None = None) -> dict:
    """Se o mês foi gerado, se no prazo, e se o movimento mudou depois. Só LÊ."""
    comp = competencia(comp)
    prazo = prazo_de_geracao(comp, feriados_locais)
    versoes = geracoes(con, comp)
    primeira = versoes[-1] if versoes else None
    ultima = versoes[0] if versoes else None
    mudou = antes_do_ferj = False
    if ultima:
        atual = apurar(con, comp)
        if _hash(atual) != ultima["hash"]:
            # Gerado antes da coluna do FERJ e com o mesmo movimento: não é
            # movimento que mudou, é o livro que saiu com a coluna errada (o
            # FERC sob o rótulo do FERJ). Retificar é decisão do oficial.
            antes_do_ferj = _hash(_sem_ferj(atual)) == ultima["hash"]
            mudou = not antes_do_ferj
    return {
        "competencia": comp,
        "prazo": prazo.isoformat(),
        "aberto": comp >= str(hoje)[:7],
        "gerado": bool(versoes),
        "versoes": len(versoes),
        "no_prazo": bool(primeira) and str(primeira["gerado_em"])[:10] <= prazo.isoformat(),
        "atrasado": not versoes and comp < str(hoje)[:7] and str(hoje)[:10] > prazo.isoformat(),
        "movimento_mudou": mudou,
        "gerado_antes_do_ferj": antes_do_ferj,
    }


def em_reais(cent: Any) -> str:
    """Centavos na forma da tela; None é «—», e não zero."""
    return "—" if cent is None else reais(int(cent))
