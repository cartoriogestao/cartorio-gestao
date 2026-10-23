"""O agente financeiro e das gratuidades — o selo do sistema, o selo do TJ e o saldo do aparelho.

    «Agente financeiro e gratuidades: esse agente fiscalizara a regularidade
     financeira dos atos do cartorio, comparando os selos emitidos no sistema,
     os selos emitidos no portal do selo e as gratuidades comprovadas ou
     pendentes.»                                       — o oficial, 09/10/2026

SÃO TRÊS FONTES, E CADA UMA RESPONDE A UMA PERGUNTA DIFERENTE
    | fonte                          | o que responde                              |
    |--------------------------------|---------------------------------------------|
    | `sd_selos` (o razão da casa)   | o que o sistema diz que pediu e usou        |
    | o Portal do Selo (TJMA)        | o que o Tribunal tem registrado de cada selo|
    | o saldo do aparelho            | quanto saiu do estoque, com ou sem sistema  |

O LADO DO TJ É A CONSULTA PÚBLICA, E ELA FOI MEDIDA EM 09/10/2026
    `GET https://selo.tjma.jus.br/portal-selo/portal-cidadao/selos/consulta/<selo>`
    — sem login, a mesma que o QR do carimbo abre. Responde JSON com o selo
    inteiro: item, valores, escrevente, `cancelado` e `dataCancelado`, e para o
    isento `infoIsento{isento, motivoGratuitoIsento}` mais **`deferido`,
    `indeferido`, `motivoIndeferimento` e `prazoMaximoParaRecorrer`** — o TJ
    analisa cada gratuidade, e é isso que «comprovada ou pendente» quer dizer
    do lado de lá. Selo que não existe volta **HTTP 400, «O selo informado no
    campo "txSelo" é inválido»** (medido com um código inventado). Outra passada
    usou a mesma consulta no mesmo dia, num script avulso, com 1,5 s entre os
    pedidos (`tmp/selos_tj_20261009/consulta_tj.py`): o espaço aqui é o mesmo.

    O QUE A MEDIÇÃO NÃO FECHOU, E FICA DITO: o retrato de «gratuidade em
    análise» foi visto em **um** selo isento — e ele estava cancelado
    (`deferido` e `indeferido` os dois falsos). Um isento ativo foi visto
    **deferido**. A regra lê: isento, não cancelado, nem deferido nem indeferido
    = EM_ANALISE. A consulta dos 553 selos desde o corte foi feita em 09/10 e o
    resultado não pôde ser lido nesta passada (a leitura da produção foi barrada
    pela permissão da sessão); a primeira rodada dirá quantos são.

O SALDO DO APARELHO É O QUE PEGA O SELO QUE NÃO PASSOU PELO SISTEMA
    A listagem completa do portal exige login (`ma.portalselo.com.br`), que esta
    casa não tem automatizado. Mas o selador devolve `saldoRemanescente` a cada
    selo — em reais. Entre dois selos seguidos do sistema o saldo cai o preço do
    selo; **o que cair a mais saiu do aparelho por fora** (outro programa, outra
    máquina). Medido em 09/10/2026 nos 549 selos desde o corte: as quedas são
    múltiplos de R$ 0,45, sem nenhuma recarga no período, e somaram R$ 165,60 a
    mais que o explicado — da ordem de 368 selos. Quem os tirou o agente NÃO
    sabe: o Protesto ainda é praticado no E-Ofício (gestor_protesto), mas a
    leitura ao vivo do E-Ofício não foi autorizada nesta passada. Por isso o
    achado diz «a explicar», e não «emitido indevidamente».

    O CUSTO DE CADA SELO NÃO SE SUPÕE: MEDE-SE NO PRÓPRIO PERÍODO. É a queda
    mais frequente entre dois selos seguidos da mesma classe (pago, isento). Se
    a classe não tiver pares bastantes para isso, a conta vira NAO_MEDIU — o
    zero com cara de medição é o defeito que o gestor existe para não ter.

O QUE VIRA TAREFA, E POR QUÊ (ordem do oficial de 06/10: só o que pode gerar
responsabilidade civil, art. 22 da Lei 8.935)
    - selo do ato que o TJ **não conhece**, ou que o TJ **cancelou** com o ato
      vivo no sistema: o papel que o usuário levou para casa tem selo inválido;
    - gratuidade **indeferida** pelo TJ: tem prazo de recurso, e quem decide
      recorrer ou recolher é o oficial — vai para a Gestão, e aparece em «o que
      só você decide» no despacho.
    O resto (valor ou isenção divergente, cancelado só no sistema, gratuidade em
    análise, selos fora do sistema) é dinheiro da casa: vai ao relatório e aos
    achados, sem tarefa.

O CORTE DE 10/09/2026 VALE AQUI COMO NO RESTO DO GESTOR.

O QUE NÃO FAZ
    Não sela, não cancela selo (nem aqui nem no portal), não cobra, não mexe em
    ato. A consulta ao portal grava só em `ge_portal_selos`; `conferir` só lê.
"""
from __future__ import annotations

import html
import json
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable

import gestor_conferencia as GC
from bd_nativo import banco

URL_CONSULTA = "https://selo.tjma.jus.br/portal-selo/portal-cidadao/selos/consulta/{}"
#: O espaço entre dois pedidos ao portal — o mesmo do script de 09/10/2026.
ESPERA_ENTRE_PEDIDOS = 1.5
#: Quantos selos uma rodada consulta. A rodada roda três vezes por dia; o
#: atraso inicial (≈ 600 selos desde o corte) se paga no primeiro dia.
TETO_POR_RODADA = 300
#: Selo achado e ativo é reconsultado depois de tantos dias (o TJ pode
#: cancelá-lo por fora), enquanto tiver menos de JANELA_DE_RECONSULTA dias.
DIAS_ENTRE_RECONSULTAS = 7
JANELA_DE_RECONSULTA = 90
#: O portal pode demorar a conhecer o selo recém-gerado: só se acusa «fora do
#: portal» o selo obtido há pelo menos tantos dias.
DIAS_PARA_O_PORTAL = 2
#: A conta do saldo só vale com pares bastantes para achar o custo de cada classe.
MIN_PARES_DA_CLASSE = 10
#: Tabelas de ato que guardam a marca de isenção da casa ao lado do selo.
TABELAS_COM_ISENTO = ("ri_atos", "ri_certidoes", "ra_atos")
FONTE = "Portal do Selo — TJMA (consulta pública)"

#: Medidas e relatadas, sem tarefa (dinheiro da casa — ordem de 06/10/2026).
REGRAS_SEM_TAREFA = frozenset({
    "FISCAL_PORTAL_SEM_RESPOSTA", "FISCAL_CANCELADO_SO_NO_SISTEMA",
    "FISCAL_VALOR_DIVERGENTE", "FISCAL_ISENCAO_DIVERGENTE",
    "FISCAL_GRATUIDADE_SEM_MOTIVO", "FISCAL_GRATUIDADE_EM_ANALISE",
    "FISCAL_SELOS_FORA_DO_SISTEMA", "FISCAL_ISENTOS_DO_DIA",
})

ROTULOS = {
    "FISCAL_SELO_FORA_DO_PORTAL": "Selo de ato que o Portal do Selo não conhece",
    "FISCAL_CANCELADO_NO_PORTAL": "Selo cancelado no TJ com o ato vivo no sistema",
    "FISCAL_GRATUIDADE_INDEFERIDA": "Gratuidade indeferida pelo TJ — recorrer ou recolher",
    "FISCAL_CANCELADO_SO_NO_SISTEMA": "Selo cancelado no sistema e ativo no TJ",
    "FISCAL_VALOR_DIVERGENTE": "Valor do selo diferente do que o TJ registrou",
    "FISCAL_ISENCAO_DIVERGENTE": "Isenção diferente entre o sistema e o TJ",
    "FISCAL_GRATUIDADE_SEM_MOTIVO": "Gratuidade sem motivo registrado no TJ",
    "FISCAL_GRATUIDADE_EM_ANALISE": "Gratuidades aguardando análise do TJ",
    "FISCAL_SELOS_FORA_DO_SISTEMA": "Selos que saíram do aparelho sem passar pelo sistema",
    "FISCAL_PORTAL_SEM_RESPOSTA": "Selos ainda não conferidos no Portal do Selo",
    "FISCAL_ISENTOS_DO_DIA": "Selos que saíram isentos ou gratuitos no dia",
}


# ----------------------------------------------------------------- miúdos

def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _dia(texto) -> date | None:
    bruto = str(texto or "").strip()
    if len(bruto) >= 10 and bruto[2] == "/" and bruto[5] == "/":
        try:
            return date(int(bruto[6:10]), int(bruto[3:5]), int(bruto[:2]))
        except ValueError:
            return None
    return GC._dia(bruto)


def _br(d: date | None) -> str:
    return d.strftime("%d/%m/%Y") if d else "—"


def _ordem(obtido_em) -> str:
    """A carga do acervo grava a hora com espaço e este sistema com «T»: na
    mesma data, comparar os dois textos crus embaralha a ordem."""
    return str(obtido_em or "").replace(" ", "T")


def _isento_no_texto(texto) -> bool:
    import selo as SL
    marcas = " ".join(SL.ler_texto(texto or "").get("marcas") or []).upper()
    return "ISENT" in marcas


def _total_no_texto(texto) -> float | None:
    import selo as SL
    return SL.ler_texto(texto or "").get("total")


def _tem_tabela(con, nome: str) -> bool:
    return banco(con).tem_tabela(nome)


# ------------------------------------------------------- a resposta do portal

def ler_resposta(numero: str, status: int, corpo: str) -> dict:
    """O que o portal disse, na forma de `ge_portal_selos`. Não grava."""
    linha = {"numero": numero, "situacao": "ERRO", "cancelado": None,
             "data_cancelado": None, "isento": None, "motivo_isencao": None,
             "analise": None, "motivo_indeferimento": None, "prazo_recurso": None,
             "codigo_ato": None, "valor_ato": None, "emolumento": None,
             "valor_selo": None, "escrevente": None, "data_selo": None,
             "erro": None, "bruto": (corpo or "")[:20000]}
    if status == 400 and "inválido" in (corpo or "").lower():
        linha["situacao"] = "NAO_ACHADO"
        return linha
    if status != 200:
        linha["erro"] = f"HTTP {status}"
        return linha
    try:
        j = json.loads(corpo or "")
    except ValueError as erro:
        linha["erro"] = f"resposta que não é JSON: {erro}"
        return linha
    s = j.get("selo") if isinstance(j, dict) and isinstance(j.get("selo"), dict) else j
    if not isinstance(s, dict) or not s.get("codSelo"):
        linha["erro"] = "resposta sem o selo"
        return linha
    if str(s["codSelo"]).strip().upper() != numero.strip().upper():
        linha["erro"] = f"o portal devolveu outro selo ({s['codSelo']})"
        return linha
    cta = s.get("codAtoTabelaAto") or {}
    info = s.get("infoIsento") or {}
    isento = bool(info.get("isento"))
    cancelado = bool(s.get("cancelado"))
    if not isento:
        analise = None
    elif cancelado:
        analise = "CANCELADA"
    elif s.get("indeferido") is True:
        analise = "INDEFERIDA"
    elif s.get("deferido") is True:
        analise = "DEFERIDA"
    else:
        analise = "EM_ANALISE"
    linha.update({
        "situacao": "ACHADO", "cancelado": int(cancelado),
        "data_cancelado": s.get("dataCancelado"), "isento": int(isento),
        "motivo_isencao": (info.get("motivoGratuitoIsento") or "").strip() or None,
        "analise": analise,
        "motivo_indeferimento": (s.get("motivoIndeferimento") or "").strip() or None,
        "prazo_recurso": s.get("prazoMaximoParaRecorrer"),
        "codigo_ato": s.get("codigoAto") or cta.get("codigoAto"),
        "valor_ato": cta.get("valorAto"), "emolumento": cta.get("emolumento"),
        "valor_selo": cta.get("valorSelo"), "escrevente": s.get("escrevente"),
        "data_selo": " ".join(x for x in (s.get("dataSelo"), s.get("horaSelo")) if x) or None,
    })
    return linha


def _buscar_no_portal(numero: str) -> tuple[int, str]:
    pedido = urllib.request.Request(
        URL_CONSULTA.format(numero),
        headers={"Accept": "application/json",
                 "User-Agent": "CartorioGestao-gestor-fiscal/1.0"})
    try:
        with urllib.request.urlopen(pedido, timeout=30) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as erro:
        return erro.code, erro.read().decode("utf-8", "replace")


def _a_consultar(con, hoje: date) -> list[str]:
    """Os selos que a rodada deve perguntar ao portal, na ordem da urgência."""
    hoje_txt = hoje.isoformat()
    reconsulta = (hoje - timedelta(days=DIAS_ENTRE_RECONSULTAS)).isoformat()
    janela = (hoje - timedelta(days=JANELA_DE_RECONSULTA)).isoformat()
    fila = []
    for r in banco(con).ler(
            """SELECT s.numero, s.obtido_em, s.cancelado_em, p.consultado_em,
                      p.situacao, p.analise, p.cancelado
                 FROM sd_selos s LEFT JOIN ge_portal_selos p ON p.numero = s.numero
                WHERE s.obtido_em >= %s AND COALESCE(s.ambiente, 'PRODUCAO') = 'PRODUCAO'
                ORDER BY s.id""",
            (GC.IMPLANTACAO,)):
        if r["consultado_em"] is None:
            prioridade = 0
        elif str(r["consultado_em"])[:10] >= hoje_txt:
            continue
        elif r["situacao"] == "ERRO":
            prioridade = 1
        elif r["situacao"] == "NAO_ACHADO":
            prioridade = 2
        elif r["analise"] == "EM_ANALISE":
            prioridade = 3
        elif r["cancelado_em"] and not r["cancelado"]:
            prioridade = 4
        elif (str(r["consultado_em"])[:10] < reconsulta
              and _ordem(r["obtido_em"])[:10] >= janela):
            prioridade = 5
        else:
            continue
        fila.append((prioridade, _ordem(r["obtido_em"]), r["numero"]))
    return [n for _p, _o, n in sorted(fila)]


def consultar_portal(con, hoje: date, *, teto: int = TETO_POR_RODADA,
                     espera: float = ESPERA_ENTRE_PEDIDOS,
                     buscar: Callable[[str], tuple[int, str]] | None = None,
                     dormir: Callable[[float], None] = time.sleep) -> dict:
    """Pergunta ao Portal do Selo pelos selos da fila e grava o que ele disse.
    Fala com a rede; cada resposta se grava na hora, para uma queda no meio não
    perder o que já se consultou."""
    from gestor_schema import init_gestor_schema
    # O esquema nativo não confirma sozinho (o `executescript` confirmava): sem
    # o commit, a trava única da ponte ficava presa durante a ida à rede.
    with con:
        init_gestor_schema(con)
    bd = banco(con)
    buscar = buscar or _buscar_no_portal
    fila = _a_consultar(bd, hoje)
    feito = Counter()
    for i, numero in enumerate(fila[:max(0, int(teto))]):
        if i and espera:
            dormir(espera)
        try:
            status, corpo = buscar(numero)
            linha = ler_resposta(numero, status, corpo)
        except Exception as erro:                       # noqa: BLE001
            linha = ler_resposta(numero, 0, "")
            linha["erro"] = f"{type(erro).__name__}: {erro}"
        linha["consultado_em"] = _agora()
        colunas = list(linha)
        # A linha leva todas as colunas da tabela e a chave é o número (não há
        # id): regravar por cima é o mesmo que o REPLACE fazia.
        with con:
            bd.escrever(
                f"INSERT INTO ge_portal_selos ({', '.join(colunas)}) "
                f"VALUES ({', '.join(['%s'] * len(colunas))}) "
                f"ON CONFLICT (numero) DO UPDATE SET "
                f"{', '.join(f'{c} = EXCLUDED.{c}' for c in colunas if c != 'numero')}",
                [linha[c] for c in colunas])
        feito[linha["situacao"]] += 1
    return {"na_fila": len(fila), "consultados": sum(feito.values()), **dict(feito)}


# ------------------------------------------------------ o saldo do aparelho

def saldo_do_aparelho(con, desde: str, ate: str | None = None) -> dict:
    """As quedas do saldo do selador entre dois selos seguidos do sistema.

    Devolve o custo medido de cada classe, os pares lidos, as recargas e, por
    dia, quanto caiu a mais do que os selos do sistema explicam. `nao_mediu`
    traz o motivo quando a conta não fecha — e então os dias vêm vazios."""
    linhas = [r for r in banco(con).ler(
        """SELECT numero, obtido_em, saldo_remanescente, texto FROM sd_selos
            WHERE obtido_em >= %s AND saldo_remanescente IS NOT NULL
              AND COALESCE(ambiente, 'PRODUCAO') = 'PRODUCAO'
            ORDER BY id""", (desde,))]
    linhas.sort(key=lambda r: (_ordem(r["obtido_em"]), r["numero"]))
    pares, recargas = [], []
    anterior = None
    for r in linhas:
        if anterior is not None:
            queda = round(float(anterior["saldo_remanescente"]) - float(r["saldo_remanescente"]), 2)
            if queda < 0:
                recargas.append({"de": anterior["saldo_remanescente"],
                                 "para": r["saldo_remanescente"], "em": _ordem(r["obtido_em"])})
            else:
                classe = "isento" if _isento_no_texto(r["texto"]) else "pago"
                pares.append((classe, queda, _ordem(r["obtido_em"])[:10]))
        anterior = r
    saida = {"selos": len(linhas), "pares": len(pares), "recargas": recargas,
             "custo": {}, "fora_da_conta": {}, "dias": {}, "nao_mediu": None}
    for classe in ("pago", "isento"):
        quedas = [q for c, q, _d in pares if c == classe]
        if not quedas:
            continue
        valor, vezes = Counter(quedas).most_common(1)[0]
        if len(quedas) < MIN_PARES_DA_CLASSE or vezes < 0.3 * len(quedas):
            # Sem um preço que se repita a classe não se mede — e os pares
            # dela saem da conta, em vez de entrarem com um preço suposto.
            saida["fora_da_conta"][classe] = (
                f"{len(quedas)} par(es), o valor mais comum em {vezes}")
            continue
        saida["custo"][classe] = valor
    if saida["custo"].get("pago", 0) <= 0:
        motivo = saida["fora_da_conta"].get("pago", "nenhum selo pago no período")
        saida["nao_mediu"] = f"o preço de um selo pago não se mediu ({motivo})"
        return saida
    preco = saida["custo"]["pago"]
    for classe, queda, dia in pares:
        if (ate and dia > ate) or classe not in saida["custo"]:
            continue
        sobra = round(queda - saida["custo"][classe], 2)
        if sobra <= 0.004:
            continue
        d = saida["dias"].setdefault(dia, {"selos": 0, "valor": 0.0})
        d["selos"] += max(1, round(sobra / preco))
        d["valor"] = round(d["valor"] + sobra, 2)
    return saida


# --------------------------------------------------------------- a regra

def _selos_conferidos(con):
    return banco(con).ler(
        """SELECT s.numero, s.obtido_em, s.usado_em, s.cancelado_em, s.motivo_cancelamento,
                  s.tabela, s.ato_id, s.texto, s.obtido_por,
                  p.situacao, p.cancelado, p.data_cancelado, p.isento, p.motivo_isencao,
                  p.analise, p.motivo_indeferimento, p.prazo_recurso, p.codigo_ato,
                  p.valor_ato, p.escrevente, p.consultado_em
             FROM sd_selos s JOIN ge_portal_selos p ON p.numero = s.numero
            WHERE s.obtido_em >= %s AND COALESCE(s.ambiente, 'PRODUCAO') = 'PRODUCAO'
              AND p.situacao IN ('ACHADO', 'NAO_ACHADO')
            ORDER BY s.id""", (GC.IMPLANTACAO,))


def _isento_na_casa(con, tabela, ato_id):
    if tabela not in TABELAS_COM_ISENTO or ato_id is None or not _tem_tabela(con, tabela):
        return None
    if not GC._coluna_existe(con, tabela, "isento"):
        return None
    r = banco(con).um(f"SELECT isento FROM {tabela} WHERE id = %s", (ato_id,))
    return None if r is None or r["isento"] is None else bool(r["isento"])


def _onde(r) -> str:
    return f"{r['tabela']} {r['ato_id']}" if r["tabela"] else "sem ato amarrado"


def _regras_dos_selos(con, hoje: date) -> list[dict]:
    saida, em_analise = [], defaultdict(list)
    limite_portal = (hoje - timedelta(days=DIAS_PARA_O_PORTAL)).isoformat()
    for r in _selos_conferidos(con):
        num, setor = r["numero"], GC.setor_da_tabela(r["tabela"])
        obtido = _ordem(r["obtido_em"])[:10]
        if r["situacao"] == "NAO_ACHADO":
            if (obtido <= limite_portal and not r["cancelado_em"]
                    and r["usado_em"] and r["tabela"]):
                saida.append(GC._achado(
                    f"FISCAL_FORA:{num}", "FISCAL_SELO_FORA_DO_PORTAL", "CRITICO", setor,
                    f"Selo {num} ({_onde(r)}) não existe no Portal do Selo",
                    f"Obtido em {_br(_dia(obtido))} por {r['obtido_por'] or '—'}; o portal "
                    "responde «selo inválido». O papel entregue com ele não confere no TJ: "
                    "apurar com quem mantém o selador e, se for o caso, selar de novo.",
                    None, FONTE))
            continue
        cancelado_tj, cancelado_aqui = bool(r["cancelado"]), bool(r["cancelado_em"])
        if cancelado_tj and not cancelado_aqui and r["tabela"]:
            saida.append(GC._achado(
                f"FISCAL_CANCELADO_TJ:{num}", "FISCAL_CANCELADO_NO_PORTAL", "CRITICO", setor,
                f"Selo {num} ({_onde(r)}) está CANCELADO no TJ e vivo no sistema",
                f"Cancelado no portal em {r['data_cancelado'] or 'data não informada'}. "
                "O ato aparece selado para a casa e o selo não vale para quem confere: "
                "registrar o cancelamento no sistema e selar de novo.", None, FONTE))
        elif cancelado_aqui and not cancelado_tj:
            saida.append(GC._achado(
                f"FISCAL_CANCELADO_LOCAL:{num}", "FISCAL_CANCELADO_SO_NO_SISTEMA", "ATENCAO",
                setor, f"Selo {num} cancelado no sistema e ATIVO no Portal do Selo",
                f"Cancelado aqui em {_br(_dia(r['cancelado_em']))}: "
                f"{r['motivo_cancelamento'] or 'sem motivo'}. O TJ continua contando este "
                "selo (e os fundos dele): cancelar também no portal, ou religar ao ato.",
                None, FONTE))
        if cancelado_tj or cancelado_aqui:
            continue
        total = _total_no_texto(r["texto"])
        if total is not None and r["valor_ato"] is not None \
                and abs(float(total) - float(r["valor_ato"])) > 0.009:
            saida.append(GC._achado(
                f"FISCAL_VALOR:{num}", "FISCAL_VALOR_DIVERGENTE", "ATENCAO", setor,
                f"Selo {num}: o sistema guarda R$ {GC._brl(float(total))} e o TJ registrou "
                f"R$ {GC._brl(float(r['valor_ato']))}",
                f"{_onde(r)}, item {r['codigo_ato'] or '—'}.", None, FONTE))
        isento_tj = bool(r["isento"])
        marcas = {"texto do selo": _isento_no_texto(r["texto"]),
                  "ato na casa": _isento_na_casa(con, r["tabela"], r["ato_id"])}
        divergem = [k for k, v in marcas.items() if v is not None and v != isento_tj]
        if divergem:
            saida.append(GC._achado(
                f"FISCAL_ISENCAO:{num}", "FISCAL_ISENCAO_DIVERGENTE", "ATENCAO", setor,
                f"Selo {num}: o TJ diz {'isento' if isento_tj else 'pago'} e o "
                f"{' e o '.join(divergem)} diz o contrário",
                f"{_onde(r)}, item {r['codigo_ato'] or '—'}.", None, FONTE))
        if not isento_tj:
            continue
        if not r["motivo_isencao"]:
            saida.append(GC._achado(
                f"FISCAL_SEM_MOTIVO:{num}", "FISCAL_GRATUIDADE_SEM_MOTIVO", "ATENCAO", setor,
                f"Selo isento {num} sem motivo da gratuidade no TJ",
                f"{_onde(r)}. É o motivo que a correição lê para saber por que não se cobrou.",
                None, FONTE))
        if r["analise"] == "INDEFERIDA":
            prazo = _dia(r["prazo_recurso"])
            gravidade = "PRAZO" if prazo and prazo >= hoje else "CRITICO"
            saida.append(GC._achado(
                f"FISCAL_INDEFERIDA:{num}", "FISCAL_GRATUIDADE_INDEFERIDA", gravidade, "GESTAO",
                f"Gratuidade do selo {num} INDEFERIDA pelo TJ "
                f"(R$ {GC._brl(float(r['valor_ato'] or 0))})",
                f"Motivo da isenção: {r['motivo_isencao'] or '—'}. Motivo do indeferimento: "
                f"{r['motivo_indeferimento'] or '—'}. Prazo para recorrer: "
                f"{_br(prazo) if prazo else (r['prazo_recurso'] or 'não informado')}. "
                f"{_onde(r)}, escrevente {r['escrevente'] or '—'}. Decidir: recorrer ou "
                "recolher os emolumentos e fundos.", prazo, FONTE))
        elif r["analise"] == "EM_ANALISE":
            em_analise[obtido[:7]].append(r)
    for mes, linhas in sorted(em_analise.items()):
        valor = sum(float(x["valor_ato"] or 0) for x in linhas)
        saida.append(GC._achado(
            f"FISCAL_ANALISE:{mes}", "FISCAL_GRATUIDADE_EM_ANALISE", "ATENCAO", "GESTAO",
            f"{len(linhas)} gratuidade(s) de {mes[5:]}/{mes[:4]} aguardando análise do TJ "
            f"(R$ {GC._brl(valor)} em atos)",
            "Lista selo a selo no relatório fiscal do mês.", None, FONTE))
    return saida


def _sem_resposta(con, hoje: date) -> list[dict]:
    limite = (hoje - timedelta(days=1)).isoformat()
    pendentes = [r["obtido_em"] for r in banco(con).ler(
        """SELECT s.obtido_em FROM sd_selos s
             LEFT JOIN ge_portal_selos p ON p.numero = s.numero
            WHERE s.obtido_em >= %s AND COALESCE(s.ambiente, 'PRODUCAO') = 'PRODUCAO'
              AND (p.numero IS NULL OR p.situacao = 'ERRO')
            ORDER BY s.id""", (GC.IMPLANTACAO,))
        if _ordem(r["obtido_em"])[:10] < limite]
    if not pendentes:
        return []
    mais_velho = min(_ordem(x)[:10] for x in pendentes)
    return [GC._achado(
        "FISCAL_SEM_RESPOSTA", "FISCAL_PORTAL_SEM_RESPOSTA", "NAO_MEDIU", "TI",
        f"{len(pendentes)} selo(s) ainda sem conferência no Portal do Selo",
        f"O mais antigo é de {_br(_dia(mais_velho))}. A consulta ao portal não respondeu "
        "ou ainda não chegou neles; enquanto isso, nada se afirma sobre esses selos.",
        None, FONTE)]


def _regras_do_saldo(con, hoje: date) -> list[dict]:
    s = saldo_do_aparelho(con, GC.IMPLANTACAO)
    if s["nao_mediu"]:
        return [GC._achado(
            "FISCAL_SALDO:NAO_MEDIU", "FISCAL_SELOS_FORA_DO_SISTEMA", "NAO_MEDIU", "GESTAO",
            "O saldo do selador não deu para medir os selos tirados por fora",
            s["nao_mediu"], None, "saldo devolvido pelo selador a cada selo")]
    por_mes = defaultdict(lambda: {"selos": 0, "valor": 0.0, "dias": 0})
    for dia, d in s["dias"].items():
        m = por_mes[dia[:7]]
        m["selos"] += d["selos"]
        m["valor"] = round(m["valor"] + d["valor"], 2)
        m["dias"] += 1
    return [GC._achado(
        f"FISCAL_FORA_DO_SISTEMA:{mes}", "FISCAL_SELOS_FORA_DO_SISTEMA", "ATENCAO", "GESTAO",
        f"{m['selos']} selo(s) saíram do aparelho em {mes[5:]}/{mes[:4]} sem passar pelo "
        f"sistema (R$ {GC._brl(m['valor'])} de saldo)",
        f"Em {m['dias']} dia(s). Preço medido de um selo: R$ "
        f"{GC._brl(s['custo']['pago'])}. Quem os tirou não se sabe daqui — o Protesto ainda "
        "é praticado no sistema antigo. A lista por dia está no relatório fiscal.",
        None, "saldo devolvido pelo selador a cada selo")
        for mes, m in sorted(por_mes.items()) if m["selos"]]


def _isentos_do_dia(bd, hoje: date) -> list[dict]:
    """Os selos que saíram ISENTOS ou GRATUITOS no dia, para o oficial ler.

    Revisão de segurança da 3.7.0 (22/10/2026, A9): a gratuidade NÃO trava —
    regra do oficial de 19/10 — e por isso é a porta que a trava do selo pago
    não fecha; o que a fecha é alguém ler, todo dia, o que saiu isento. Sem
    tarefa: é relato, e o oficial decide.
    """
    de = hoje.isoformat()
    ate = date.fromordinal(hoje.toordinal() + 1).isoformat()
    linhas = bd.ler("""SELECT numero, tabela, ato_id, atribuicao, obtido_por, texto
                         FROM sd_selos
                        WHERE obtido_em >= %s AND obtido_em < %s
                          AND cancelado_em IS NULL
                        ORDER BY obtido_em""", (de, ate))
    isentos = [r for r in linhas if _isento_no_texto(r.get("texto"))]
    if not isentos:
        return []
    detalhe = "; ".join(
        f"{r['numero']} ({r.get('tabela') or '?'}:{r.get('ato_id') or '?'}, "
        f"{r.get('obtido_por') or 'sem escrevente'})" for r in isentos[:30])
    if len(isentos) > 30:
        detalhe += f"; … e mais {len(isentos) - 30}"
    return [GC._achado(f"FISCAL:ISENTOS:{de}", "FISCAL_ISENTOS_DO_DIA", "ATENCAO",
                       "FISCAL", f"{len(isentos)} selo(s) isento(s) em {hoje:%d/%m/%Y}",
                       detalhe,
                       fundamento="Isenção se confere todo dia: a gratuidade não "
                                  "passa pela trava do selo pago.")]


def conferir(con, hoje: date) -> list[dict]:
    """Tudo o que o agente financeiro aponta. SÓ LÊ (o que o portal disse já
    está em `ge_portal_selos`). Cada parte que quebra vira NAO_MEDIU."""
    bd = banco(con)
    if not _tem_tabela(bd, "ge_portal_selos") or not _tem_tabela(bd, "sd_selos"):
        return [GC._achado("FISCAL:SEM_TABELA", "FISCAL_PORTAL_SEM_RESPOSTA", "NAO_MEDIU",
                           "TI", "O agente financeiro não achou as tabelas dos selos",
                           "Falta sd_selos ou ge_portal_selos neste banco.")]
    achados = []
    for nome, parte in (("FISCAL_SELOS", _regras_dos_selos),
                        ("FISCAL_PORTAL_SEM_RESPOSTA", _sem_resposta),
                        ("FISCAL_SELOS_FORA_DO_SISTEMA", _regras_do_saldo),
                        ("FISCAL_ISENTOS_DO_DIA", _isentos_do_dia)):
        try:
            achados.extend(parte(bd, hoje))
        except Exception as erro:                       # noqa: BLE001
            achados.append(GC._achado(
                f"NAO_MEDIU:{nome}", nome, "NAO_MEDIU", "TI",
                f"A conferência fiscal «{nome}» não conseguiu medir",
                f"{type(erro).__name__}: {erro}"))
    return achados


# ------------------------------------------------------------- o relatório

def apurar_mes(con, ano: int, mes: int) -> dict:
    comp = f"{ano:04d}-{mes:02d}"
    bd = banco(con)
    linhas = bd.ler(
        """SELECT s.numero, s.obtido_em, s.cancelado_em, s.tabela, s.ato_id, s.obtido_por,
                  p.situacao, p.cancelado, p.isento, p.motivo_isencao, p.analise,
                  p.motivo_indeferimento, p.prazo_recurso, p.codigo_ato, p.valor_ato,
                  p.emolumento, p.escrevente
             FROM sd_selos s LEFT JOIN ge_portal_selos p ON p.numero = s.numero
            WHERE s.obtido_em ILIKE %s AND s.obtido_em >= %s
              AND COALESCE(s.ambiente, 'PRODUCAO') = 'PRODUCAO'
            ORDER BY s.id""",
        (comp + "%", GC.IMPLANTACAO))
    situacao = Counter(r["situacao"] or "SEM_CONSULTA" for r in linhas)
    gratuidade = defaultdict(lambda: {"qtd": 0, "valor": 0.0, "emol": 0.0})
    motivos = defaultdict(lambda: {"qtd": 0, "valor": 0.0})
    lista = []
    for r in linhas:
        if r["situacao"] != "ACHADO" or not r["isento"]:
            continue
        g = gratuidade[r["analise"] or "—"]
        g["qtd"] += 1
        g["valor"] += float(r["valor_ato"] or 0)
        g["emol"] += float(r["emolumento"] or 0)
        if r["analise"] != "CANCELADA":
            m = motivos[(r["motivo_isencao"] or "(sem motivo)").upper()]
            m["qtd"] += 1
            m["valor"] += float(r["valor_ato"] or 0)
        if r["analise"] in ("INDEFERIDA", "EM_ANALISE"):
            lista.append(r)
    saldo = saldo_do_aparelho(bd, GC.IMPLANTACAO)
    dias = {d: v for d, v in saldo["dias"].items() if d.startswith(comp)}
    return {"comp": comp, "total": len(linhas), "situacao": dict(situacao),
            "cancelados_tj": sum(1 for r in linhas if r["cancelado"]),
            "cancelados_aqui": sum(1 for r in linhas if r["cancelado_em"]),
            "gratuidade": dict(gratuidade), "motivos": dict(motivos),
            "lista": sorted(lista, key=lambda r: _ordem(r["obtido_em"])),
            "saldo": saldo, "dias": dict(sorted(dias.items()))}


def relatorio_html(con, ano: int, mes: int, hoje: date) -> str:
    r = apurar_mes(banco(con), ano, mes)
    e = html.escape
    parcial = (ano, mes) == (hoje.year, hoje.month)
    st = r["situacao"]
    nomes = {"DEFERIDA": "deferida (comprovada)", "INDEFERIDA": "INDEFERIDA",
             "EM_ANALISE": "em análise (pendente)", "CANCELADA": "selo cancelado"}
    linhas_g = "".join(
        f"<tr><td>{e(nomes.get(k, k))}</td><td class=n>{v['qtd']}</td>"
        f"<td class=n>R$ {GC._brl(v['valor'])}</td><td class=n>R$ {GC._brl(v['emol'])}</td></tr>"
        for k, v in sorted(r["gratuidade"].items())) or "<tr><td colspan=4>nenhuma</td></tr>"
    linhas_m = "".join(
        f"<tr><td>{e(k)}</td><td class=n>{v['qtd']}</td><td class=n>R$ {GC._brl(v['valor'])}</td></tr>"
        for k, v in sorted(r["motivos"].items(), key=lambda kv: -kv[1]["qtd"])) \
        or "<tr><td colspan=3>nenhum</td></tr>"
    linhas_l = "".join(
        "<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td class=n>R$ {}</td>"
        "<td>{}</td></tr>".format(
            e(x["numero"]), _br(_dia(_ordem(x["obtido_em"])[:10])), e(x["codigo_ato"] or "—"),
            e(x["escrevente"] or x["obtido_por"] or "—"), e(x["motivo_isencao"] or "—"),
            GC._brl(float(x["valor_ato"] or 0)),
            e(("INDEFERIDA — " + (x["motivo_indeferimento"] or "") + " · prazo "
               + str(x["prazo_recurso"] or "—")) if x["analise"] == "INDEFERIDA" else "em análise"))
        for x in r["lista"]) or "<tr><td colspan=7>nenhuma</td></tr>"
    saldo = r["saldo"]
    if saldo["nao_mediu"]:
        bloco_saldo = f"<p class=aviso>Não deu para medir: {e(saldo['nao_mediu'])}.</p>"
    else:
        dias = "".join(
            f"<tr><td>{_br(_dia(d))}</td><td class=n>{v['selos']}</td>"
            f"<td class=n>R$ {GC._brl(v['valor'])}</td></tr>" for d, v in r["dias"].items()) \
            or "<tr><td colspan=3>nenhum — todo selo que saiu do aparelho passou pelo sistema</td></tr>"
        custo = ", ".join(f"{k}: R$ {GC._brl(v)}" for k, v in saldo["custo"].items())
        recargas = len(saldo["recargas"])
        fora = "".join(f" Os selos {e(k)}s ficaram fora da conta ({e(v)}): não têm um preço "
                       "que se repita." for k, v in saldo["fora_da_conta"].items())
        bloco_saldo = (
            f"<p><small>Preço medido de cada selo no período ({custo}), sobre "
            f"{saldo['pares']} pares de selos seguidos; {recargas} recarga(s) do saldo "
            f"no período (pares com recarga não entram na conta).{fora}</small></p>"
            f"<table><tr><th>Dia</th><th>Selos por fora</th><th>Saldo a mais</th></tr>{dias}</table>"
            "<p><small>«Por fora» quer dizer: o saldo do aparelho caiu mais do que os selos do "
            "sistema explicam. Quem os tirou o agente não sabe — o Protesto ainda é praticado "
            "no sistema antigo, que sela no mesmo aparelho.</small></p>")
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Fiscal {mes:02d}/{ano}</title><style>
body{{font:14px system-ui,sans-serif;margin:16px;color:#222;background:#fff;max-width:960px}}
table{{border-collapse:collapse;min-width:320px;margin:4px 0 14px}}td,th{{border-bottom:1px solid #ddd;padding:5px 10px;text-align:left}}
td.n{{text-align:right;font-variant-numeric:tabular-nums}}small{{color:#555}}
.aviso{{background:#fff7e0;border-left:4px solid #c80;padding:8px 12px}}
</style></head><body>
<h1>Agente financeiro e gratuidades — {mes:02d}/{ano}{' (parcial, até ' + hoje.strftime('%d/%m') + ')' if parcial else ''}</h1>
<p><small>Compara o razão dos selos do sistema com a consulta pública do Portal do Selo (TJMA) e com o
saldo do selador. Só leitura. Selos a partir de {_br(_dia(GC.IMPLANTACAO))}.</small></p>

<h2>1. Selos do sistema × Portal do Selo</h2>
<table>
<tr><td>Selos obtidos pelo sistema no mês</td><td class=n>{r['total']}</td></tr>
<tr><td>Conferidos no portal (o TJ conhece)</td><td class=n>{st.get('ACHADO', 0)}</td></tr>
<tr><td><b>Que o portal NÃO conhece</b></td><td class=n><b>{st.get('NAO_ACHADO', 0)}</b></td></tr>
<tr><td>Ainda sem resposta do portal</td><td class=n>{st.get('SEM_CONSULTA', 0) + st.get('ERRO', 0)}</td></tr>
<tr><td>Cancelados no TJ</td><td class=n>{r['cancelados_tj']}</td></tr>
<tr><td>Cancelados no sistema</td><td class=n>{r['cancelados_aqui']}</td></tr>
</table>
<p><small>Cada divergência, selo a selo, está nos achados do gestor do dia.</small></p>

<h2>2. Gratuidades — o que o TJ disse de cada uma</h2>
<table><tr><th>Situação no TJ</th><th>Selos</th><th>Valor dos atos</th><th>Emolumentos</th></tr>{linhas_g}</table>
<p><small>«Valor dos atos» é o que se teria cobrado: a base de qualquer compensação.</small></p>
<h3>Por motivo declarado</h3>
<table><tr><th>Motivo</th><th>Selos</th><th>Valor</th></tr>{linhas_m}</table>
<h3>Indeferidas e em análise</h3>
<table><tr><th>Selo</th><th>Data</th><th>Item</th><th>Escrevente</th><th>Motivo</th><th>Valor</th><th>Situação</th></tr>{linhas_l}</table>

<h2>3. Selos que saíram do aparelho sem passar pelo sistema</h2>
{bloco_saldo}

<h2>4. O que este relatório não mede</h2>
<ul>
<li>Selo emitido no portal por outro caminho e nunca visto pelo sistema: só a listagem com login
(ma.portalselo.com.br) o diria, nome a nome. O saldo do aparelho (seção 3) dá o número, não o nome.</li>
<li>O papel que comprova a gratuidade (declaração, decisão judicial) arquivado na casa: o sistema guarda o
motivo, não o documento.</li>
<li>Se o lançamento de gratuidade foi feito no caixa: o caixa desta casa é lançado à mão e não amarra selo.</li>
</ul>
</body></html>"""


def escrever_relatorio(con, hoje: date, pasta: Path) -> list[Path]:
    """Grava o relatório fiscal do mês corrente e do anterior (se depois do corte)."""
    pasta.mkdir(parents=True, exist_ok=True)
    meses = {(hoje.year, hoje.month)}
    anterior = hoje.replace(day=1) - timedelta(days=1)
    if anterior.isoformat()[:7] >= GC.IMPLANTACAO[:7]:
        meses.add((anterior.year, anterior.month))
    feitos = []
    for ano, mes in sorted(meses):
        caminho = pasta / f"fiscal_{ano:04d}-{mes:02d}.html"
        caminho.write_text(relatorio_html(con, ano, mes, hoje), encoding="utf-8")
        feitos.append(caminho)
    return feitos
