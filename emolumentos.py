"""
Tabela de emolumentos do TJMA, importada do E-Oficio.

POR QUE IMPORTAR EM VEZ DE DIGITAR
    A tabela muda por ato normativo e por exercicio. O E-Oficio a mantem
    atualizada e e ele quem conversa com o selador do tribunal. Uma copia
    editavel a mao aqui seria uma segunda verdade — e, no dia em que as duas
    divergissem, ninguem saberia qual esta certa.

COMO A TABELA E ORGANIZADA NA ORIGEM
    tbServico         catalogo dos atos: descricao e codigo do TJ. O valor que
                      esta nesta tabela e HISTORICO e nao serve: para o
                      servico 56 ela diz 22,20 quando a vigencia atual e 31,14.
    tbServico_Tabela  o valor de cada ato em cada vigencia. E a fonte boa.
    tbTabelas         os atos cobrados por FAIXA do valor do negocio — compra
                      e venda, hipoteca, e o que mais depender do preco.

OS FUNDOS, E COMO DESCOBRI O QUE CADA UM E
    A origem chama as colunas de FERMOJUPI, MP, DP e FERRFIS. O selo do TJMA
    imprime FERC, FEMP, FADEP e FERRFIS. A ligacao foi feita conferindo um
    selo real desta serventia contra a tabela:

        emolumento   16.878,39
        FERC            506,35  =  3% do emolumento   -> FERMOJUPI
        FADEP           675,14  =  4%                 -> curValor_DP  (Defensoria)
        FEMP            675,14  =  4%                 -> curValor_MP  (Ministerio Publico)
        FERRFIS         168,78  =  1%                 -> curvalor_ferrfis
        total        18.903,80  =  emolumento x 1,12

    Os quatro bateram ao centavo, e a soma tambem. Como FADEP e FEMP tem o
    mesmo percentual, a distincao entre eles vem do NOME da coluna de origem,
    nao do valor — MP para o Ministerio Publico, DP para a Defensoria. Se um
    dia sairem trocados no recibo, e aqui que se corrige.

    O nome FERC tambem esta no C11.INI da serventia, em [SELOFISCAL], onde
    "Fermoju=3,00" aparece com "Descricao=FERC".
"""
from __future__ import annotations

import json
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any

from caixa_schema import centavos, reais

# Percentual de cada fundo sobre o emolumento. Serve para CONFERIR o que veio
# importado, nunca para substituir: o valor que vale e o da tabela.
PERCENTUAIS = {"ferc": 0.03, "fadep": 0.04, "femp": 0.04, "ferrfis": 0.01}

# intCodigoTabela do E-Oficio -> item da tabela do TJMA que ele contem.
#
# ESTE MAPA JA ME ENGANOU UMA VEZ. Eu tinha chamado a tabela interna 4 de
# "Registro de Imoveis", porque os codigos comecam com 15 e eu supus que 15
# fosse o RI. Nao e: na Resolucao-GP 143/2025, a Tabela XV e o Registro Civil
# de Pessoas Juridicas, e o Registro de Imoveis e a Tabela XVI.
#
# O erro tem consequencia pratica. Conferindo o selo de um registro real
# (matricula 4012, valor declarado de R$ 2.145.446,27) contra a tabela errada,
# o emolumento parecia R$ 491,64 menor do que o cobrado, e eu quase reportei
# cobranca a maior. Pela tabela certa — 16.3.28 — bate exatamente:
# R$ 16.878,39 de emolumento e R$ 18.903,80 de total.
#
# O rotulo abaixo foi conferido contra o texto da Resolucao, nao deduzido.
#
# E AS QUATRO ULTIMAS DIZIAM APENAS «Registro de Imoveis» — quatro rotulos
# iguais numa caixa de escolha, achado em 21/09/2026 ao orcar uma cedula de
# credito bancario. Quem precisa da faixa do credito rural (a 9) nao tinha como
# distinguir da dos registros torrens (a 6): o balcao escolheria pelo numero do
# item, que e' justamente o que ele ainda nao sabe quando esta procurando.
#
# Os quatro nomes sao os da **descricao do proprio item** em `cx_servicos`
# (codigos 859, 1441 e os cabecalhos de 16.11 e 16.45), lidos no banco — nao
# foram redigidos por mim.
TABELAS_FAIXA = {
    1: "17.1 — Protesto: registro de protesto",
    2: "17.4 — Protesto: cancelamento",
    3: "13.1 — Notas: escritura com valor declarado",
    4: "15.2 — Registro Civil de Pessoas Jurídicas",
    5: "16.3 — Registro de Imóveis: registro com valor declarado",
    6: "16.9 — Registro de Imóveis: registros torrens com valor declarado",
    7: "16.11 — Registro de Imóveis: registro completo de bem de família",
    8: "16.16 — Registro de Imóveis: casa própria por cooperativa habitacional",
    9: "16.45 — Registro de Imóveis: garantia real do crédito rural "
       "(penhor cedular, hipoteca e alienação fiduciária de cédula)",
}

# A que o Registro de Imoveis recorre por padrao.
TABELA_RI = 5

# Tabela 16.9 (faixas por valor do imovel).
TABELA_RI_16_9 = 6

# Itens cujo preco NAO e o valor fixo do servico: usam a tabela 16.9 com a
# BASE pela metade do valor do imovel (texto do item na tabela TJMA).
# Sem este corte, o caixa e o selo cobram a faixa cheia.
SERVICOS_TJ_BASE_METADE_NA_16_9 = frozenset({
    "16.22.4.1",
})


def _norm(texto: Any) -> str:
    s = "" if texto is None else str(texto)
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn").upper()


def _cent(v: Any) -> int:
    """Numero da origem vem como float; aqui vira centavo inteiro."""
    if v is None:
        return 0
    if isinstance(v, (int, float)):
        return int(round(float(v) * 100))
    return centavos(v)


def _ler(caminho: Path):
    with caminho.open(encoding="utf-8", errors="replace") as fh:
        for linha in fh:
            linha = linha.strip()
            if linha:
                yield json.loads(linha)


def importar(con, pasta_caixa: Path, pasta_ri: Path | None = None) -> dict:
    """Carrega servicos, valores por vigencia e faixas.

    Substitui a tabela inteira a cada carga: e copia de uma fonte externa, nao
    cadastro proprio. Guardar sobras de uma carga velha so criaria divergencia.
    """
    rel: dict[str, Any] = {"servicos": 0, "valores": 0, "faixas": 0,
                           "vigencias": [], "vigente": None, "avisos": []}

    arq_serv = Path(pasta_caixa) / "dom_servico.jsonl"
    arq_val = Path(pasta_caixa) / "dom_servico_tabela.jsonl"
    if not arq_serv.exists() or not arq_val.exists():
        raise FileNotFoundError(
            "Faltam dom_servico.jsonl e dom_servico_tabela.jsonl. "
            "Rode o EXPORTAR_CAIXA.cmd.")

    con.execute("DELETE FROM cx_servico_valores")
    con.execute("DELETE FROM cx_faixas")
    con.execute("DELETE FROM cx_servicos")
    con.execute("DELETE FROM cx_vigencias")

    # As vigencias entram PRIMEIRO, antes dos valores que apontam para elas.
    #
    # Na primeira versao eu as gravava no fim, quando ja sabia quantos itens
    # cada uma tinha — e a carga morria com "FOREIGN KEY constraint failed".
    # O teste nao pegou porque o SQLite so cobra chave estrangeira quando
    # `PRAGMA foreign_keys` esta ligado, e no banco em memoria do teste ele
    # estava desligado. No banco da serventia esta ligado, e ali doeu.
    arq_faixa = Path(pasta_ri or pasta_caixa) / "dom_tabelas.jsonl"
    vigencias: set[int] = set()
    for arquivo in (arq_val, arq_faixa):
        if arquivo.exists():
            for r in _ler(arquivo):
                v = r.get("intCodigoVigencia")
                if v is not None:
                    vigencias.add(int(v))
    # O PERIODO de cada vigencia, quando o export o trouxer.
    #
    # POR QUE ISTO IMPORTA. Antes daqui a vigencia era so um numero, e a atual
    # era "a de maior codigo". Funcionava por sorte — o E-Oficio numera em
    # ordem —, mas nao respondia a pergunta que aparece toda semana no balcao:
    # quanto custava este ato no dia em que ele foi praticado. Relavrar ato de
    # marco de 2023 pela tabela de 2026 e cobranca a maior, e reimprimir
    # recibo de 2024 pela de 2026 e recibo que nao confere com o caixa.
    periodos: dict[int, tuple[str | None, str | None, str | None]] = {}
    arq_vig = Path(pasta_caixa) / "dom_vigencia.jsonl"
    if arq_vig.exists():
        for r in _ler(arq_vig):
            codigo = r.get("intChave")
            if codigo is None:
                continue
            periodos[int(codigo)] = (
                str(r.get("dtmPeriodo1") or "")[:10] or None,
                str(r.get("dtmPeriodo2") or "")[:10] or None,
                (r.get("strDescricao") or None))
            vigencias.add(int(codigo))
    else:
        rel["avisos"].append(
            "Sem dom_vigencia.jsonl: as vigências ficaram sem período, e o "
            "cálculo por data do ato vai recorrer à tabela corrente. Rode a "
            "versão nova do EXPORTAR_CAIXA.ps1 para trazer os períodos.")

    # A vigencia CORRENTE e a que contem hoje. So quando nenhum periodo casa
    # e que se volta ao antigo "a de maior codigo" — e isso fica no aviso, em
    # vez de passar em silencio.
    hoje = date.today().isoformat()
    vigente = next(
        (c for c, (ini, fim, _) in sorted(periodos.items(), reverse=True)
         if ini and ini <= hoje and (not fim or fim >= hoje)), None)
    if vigente is None:
        vigente = max(vigencias) if vigencias else None
        if periodos:
            rel["avisos"].append(
                f"Nenhuma vigência contém {hoje}; foi marcada como corrente a "
                f"de maior código ({vigente}). A tabela do exercício pode não "
                f"ter sido publicada ainda.")
    for v in sorted(vigencias):
        ini, fim, descricao = periodos.get(v, (None, None, None))
        con.execute(
            """INSERT OR REPLACE INTO cx_vigencias
               (codigo, descricao, vigente, servicos, faixas, importado_em,
                inicio, fim)
               VALUES (?,?,?,0,0, datetime('now','localtime'), ?,?)""",
            (v, descricao or f"Vigência {v}", 1 if v == vigente else 0,
             ini, fim))

    for r in _ler(arq_serv):
        con.execute(
            """INSERT OR REPLACE INTO cx_servicos
               (codigo, codigo_tj, descricao, descricao_norm, grupo, tipo_selo,
                id_tj, ativo, emolumento, selo_fiscal, observacao)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (r.get("intCodigoServico"), (r.get("strCodigoTJ") or "").strip() or None,
             r.get("strDescricao"), _norm(r.get("strDescricao")),
             r.get("intGrupo"), r.get("intTipoSelo"), r.get("intID_TJ"),
             1 if r.get("bitAtivo") else 0,
             1 if r.get("bitEmolumento") else 0,
             1 if r.get("bitSeloFiscal") else 0,
             r.get("strObs")))
        rel["servicos"] += 1

    # Valor que aponta para ato inexistente no catalogo. Ha exatamente um na
    # base da serventia — o servico 707 — e ele derrubava a carga inteira com
    # "FOREIGN KEY constraint failed". Uma linha solta na origem nao pode
    # impedir a atualizacao da tabela: fica de fora e e reportada.
    catalogo = {r[0] for r in con.execute("SELECT codigo FROM cx_servicos")}
    orfaos: list[int] = []

    for r in _ler(arq_val):
        vig = r.get("intCodigoVigencia")
        if vig is None:
            continue
        codigo = r.get("intCodigoServico")
        if codigo not in catalogo:
            orfaos.append(codigo)
            continue
        emol = _cent(r.get("curValor"))
        ferc = _cent(r.get("curFERMOJUPI"))
        femp = _cent(r.get("curValor_MP"))
        fadep = _cent(r.get("curValor_DP"))
        ferrfis = _cent(r.get("curvalor_ferrfis"))
        con.execute(
            """INSERT OR REPLACE INTO cx_servico_valores
               (servico, vigencia, emolumentos, ferc, femp, fadep, ferrfis,
                total, id_tj)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (r.get("intCodigoServico"), vig, reais(emol), reais(ferc), reais(femp),
             reais(fadep), reais(ferrfis),
             reais(emol + ferc + femp + fadep + ferrfis), r.get("intID_TJ")))
        rel["valores"] += 1

    # Faixas por valor do negocio — vieram na exportacao do RI.
    if arq_faixa.exists():
        for r in _ler(arq_faixa):
            vig = r.get("intCodigoVigencia")
            if vig is None:
                continue
            emol = _cent(r.get("curValor"))
            ferc = _cent(r.get("curFERMOJUPI"))
            femp = _cent(r.get("curValor_MP"))
            fadep = _cent(r.get("curValor_DP"))
            ferrfis = _cent(r.get("curvalor_ferrfis"))
            con.execute(
                """INSERT INTO cx_faixas
                   (tabela, vigencia, de, ate, codigo_tj, emolumentos, ferc,
                    femp, fadep, ferrfis, total, id_tj)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (r.get("intCodigoTabela"), vig, reais(_cent(r.get("curDe"))),
                 reais(_cent(r.get("curAte"))),
                 (r.get("strCodigoTJ") or "").strip() or None,
                 reais(emol), reais(ferc), reais(femp), reais(fadep), reais(ferrfis),
                 reais(emol + ferc + femp + fadep + ferrfis), r.get("intID_TJ")))
            rel["faixas"] += 1
    else:
        rel["avisos"].append(
            "dom_tabelas.jsonl não encontrado: os atos cobrados por faixa de "
            "valor não foram importados.")

    # Agora que os itens estao gravados, atualiza a contagem de cada vigencia.
    # A vigencia de maior codigo e a atual: e como o E-Oficio as numera — as
    # antigas vao de 3 a 11, as novas na faixa 10013 em diante.
    for v in sorted(vigencias):
        con.execute(
            """UPDATE cx_vigencias SET
                 servicos = (SELECT COUNT(*) FROM cx_servico_valores WHERE vigencia=?),
                 faixas   = (SELECT COUNT(*) FROM cx_faixas WHERE vigencia=?)
               WHERE codigo=?""", (v, v, v))
    rel["vigencias"] = sorted(vigencias)
    rel["vigente"] = vigente
    rel["ignorados"] = len(orfaos)
    if orfaos:
        distintos = sorted({o for o in orfaos if o is not None})
        rel["avisos"].append(
            f"{len(orfaos)} valor(es) ficaram de fora: apontam para ato que não "
            f"existe no catálogo do E-Ofício (código "
            f"{', '.join(str(d) for d in distintos[:6])}"
            f"{'…' if len(distintos) > 6 else ''}).")
    rel["conferencia"] = conferir_fundos(con, vigente) if vigente else {}
    return rel


def conferir_fundos(con, vigencia: int, tolerancia_centavos: int = 1) -> dict:
    """Confere os fundos importados contra o percentual conhecido.

    Nao corrige nada. Se a tabela do tribunal mudar um percentual, quero que a
    divergencia apareca como numero na tela — e nao que o sistema recalcule por
    conta propria e esconda a mudanca.
    """
    fora: list[dict] = []
    total = 0
    for r in con.execute(
            """SELECT servico, emolumentos, ferc, femp, fadep, ferrfis
               FROM cx_servico_valores WHERE vigencia=?""", (vigencia,)):
        total += 1
        emol = centavos(r[1])
        if emol <= 0:
            continue
        for i, fundo in enumerate(("ferc", "femp", "fadep", "ferrfis"), start=2):
            esperado = int(round(emol * PERCENTUAIS[fundo]))
            achado = centavos(r[i])
            if abs(esperado - achado) > tolerancia_centavos:
                fora.append({"servico": r[0], "fundo": fundo,
                             "esperado": reais(esperado), "importado": reais(achado)})
    return {"conferidos": total, "divergentes": len(fora), "exemplos": fora[:12]}


def valor_do_servico(con, codigo_servico: int, vigencia: int | None = None) -> dict | None:
    """Quanto custa um ato hoje, com os fundos discriminados."""
    if vigencia is None:
        linha = con.execute("SELECT codigo FROM cx_vigencias WHERE vigente=1").fetchone()
        if not linha:
            return None
        vigencia = linha[0]
    r = con.execute(
        """SELECT s.codigo, s.codigo_tj, s.descricao, v.emolumentos, v.ferc,
                  v.femp, v.fadep, v.ferrfis, v.total, v.vigencia
           FROM cx_servico_valores v JOIN cx_servicos s ON s.codigo = v.servico
           WHERE v.servico=? AND v.vigencia=?""", (codigo_servico, vigencia)).fetchone()
    if not r:
        return None
    return dict(zip(("codigo", "codigo_tj", "descricao", "emolumentos", "ferc",
                     "femp", "fadep", "ferrfis", "total", "vigencia"), r))


def faixa_por_valor(con, valor: Any, tabela: int = TABELA_RI,
                    vigencia: int | None = None) -> dict | None:
    """Acha a faixa em que cai o valor do negocio.

    A comparacao e feita em CENTAVOS INTEIROS. Em ponto flutuante, um negocio
    de exatamente 7.396,72 poderia cair na faixa de cima por arredondamento —
    e a diferenca de emolumento entre duas faixas nao e pequena.
    """
    if vigencia is None:
        linha = con.execute("SELECT codigo FROM cx_vigencias WHERE vigente=1").fetchone()
        if not linha:
            return None
        vigencia = linha[0]
    alvo = centavos(valor)
    for r in con.execute(
            """SELECT de, ate, codigo_tj, emolumentos, ferc, femp, fadep,
                      ferrfis, total
               FROM cx_faixas WHERE vigencia=? AND tabela=?""", (vigencia, tabela)):
        if centavos(r[0]) <= alvo <= centavos(r[1]):
            achado = dict(zip(("de", "ate", "codigo_tj", "emolumentos", "ferc",
                               "femp", "fadep", "ferrfis", "total"), r))
            achado["vigencia"] = vigencia
            return achado
    # Acima do teto da tabela: devolve a ultima faixa, marcada, porque o
    # calculo dali em diante costuma ter regra propria no ato normativo.
    ultima = con.execute(
        """SELECT de, ate, codigo_tj, emolumentos, ferc, femp, fadep, ferrfis, total
           FROM cx_faixas WHERE vigencia=? AND tabela=?
           ORDER BY CAST(REPLACE(REPLACE(ate,'.',''),',','.') AS REAL) DESC LIMIT 1""",
        (vigencia, tabela)).fetchone()
    if not ultima:
        return None
    achado = dict(zip(("de", "ate", "codigo_tj", "emolumentos", "ferc", "femp",
                       "fadep", "ferrfis", "total"), ultima))
    achado["vigencia"] = vigencia
    achado["acima_do_teto"] = True
    return achado


def calcular_item(con, servico: int | None = None, tabela: int | None = None,
                  base: Any = None, quantidade: int = 1,
                  vigencia: int | None = None, imoveis: int = 1) -> dict | None:
    """Quanto custa um item, pela tabela do tribunal.

    Dois caminhos, e o item diz qual usou:
      `servico`  ato de valor fixo — busca em cx_servico_valores;
      `tabela` + `base`  ato que depende do valor do negocio — busca a faixa.

    A quantidade multiplica emolumento e fundos. Nao ha arredondamento no
    meio: tudo em centavos inteiros, e a divisao so aparece na tela.

    `imoveis` E' O ITEM 16.31, e so vale no caminho da FAIXA. Quando a mesma
    garantia esta estipulada em mais de um imovel, a base de cada registro e' o
    valor do negocio **dividido pelo numero de imoveis** — e sao N registros,
    um por imovel, cada um com o seu selo.

    NAO SE DIVIDE PELO NUMERO DE GARANTIAS. Hipoteca, penhor e alienacao
    fiduciaria da mesma cedula sao cobrados **cada um sobre o valor cheio**; o
    que se divide e' cada garantia pelos imoveis em que ELA esta. E' a leitura
    do item 16.31 (que fala em «dois ou mais imoveis forem dados em garantia»)
    lido com o 16.29 («mais de um registro em razao do mesmo titulo, os
    emolumentos serao cobrados separadamente»).

    No caminho do SERVICO nao ha o que dividir: ali quem escolheu a faixa foi
    quem digitou o codigo, e nao a base.
    """
    quantidade = max(1, int(quantidade or 1))
    imoveis = max(1, int(imoveis or 1))
    base_do_negocio = centavos(base) if base else 0
    sobra = 0
    if imoveis > 1 and tabela is not None and servico is None:
        # Em CENTAVOS INTEIROS, como a comparacao das faixas. Em ponto
        # flutuante, uma divisao por tres poria a base do lado errado da
        # fronteira de uma faixa.
        por_imovel, sobra = divmod(base_do_negocio, imoveis)
        base = reais(por_imovel)
        quantidade *= imoveis
    achado = None
    origem = ""
    # 16.22.4.1 e companhia: o servico na tabela tem total zero; o preco real
    # sai da faixa 16.9 com metade do valor do imovel. Se o balcao mandar o
    # codigo do servico + a base cheia, cortamos aqui — nao no clique.
    codigo_tj_servico = None
    if servico is not None:
        achado = valor_do_servico(con, servico, vigencia)
        origem = "TABELA"
        if achado:
            codigo_tj_servico = str(achado.get("codigo_tj") or "").strip()
        if codigo_tj_servico in SERVICOS_TJ_BASE_METADE_NA_16_9:
            # Base cheia em reais (o balcao digita o valor do imovel);
            # a faixa 16.9 recebe a metade, como manda o item.
            base_cheia = _cent(base) / 100.0
            if base_cheia > 0:
                achado = faixa_por_valor(
                    con, base_cheia / 2.0, TABELA_RI_16_9, vigencia)
                origem = "FAIXA_METADE_16.9"
                if achado is not None:
                    achado = dict(achado)
                    achado["codigo_tj"] = codigo_tj_servico
                    achado["descricao"] = (
                        (achado.get("descricao") or "")
                        + " (base 1/2 do valor do imovel, tabela 16.9)"
                    )
    elif tabela is not None:
        achado = faixa_por_valor(con, base, tabela, vigencia)
        origem = "FAIXA"
    if not achado:
        return None

    campos = ("emolumentos", "ferc", "femp", "fadep", "ferrfis")
    valores = {c: centavos(achado.get(c)) * quantidade for c in campos}
    total = sum(valores.values())
    return {
        "origem_valor": origem,
        "servico_codigo": servico,
        "tabela": tabela,
        "codigo_tj": achado.get("codigo_tj"),
        "descricao": achado.get("descricao") or TABELAS_FAIXA.get(tabela, ""),
        "quantidade": quantidade,
        "base_calculo": reais(centavos(base)) if base else None,
        "faixa": (f"de R$ {achado['de']} até R$ {achado['ate']}"
                  if achado.get("de") else None),
        "acima_do_teto": achado.get("acima_do_teto", False),
        "vigencia": achado.get("vigencia", vigencia),
        # O 16.31: quantos imoveis, qual era o valor do negocio antes de
        # dividir, e os centavos que a divisao nao coube. A sobra e' declarada
        # em vez de espalhada — quem confere a conta precisa saber que a soma
        # das bases nao fecha com o contrato por esses centavos.
        "imoveis": imoveis,
        "base_do_negocio": reais(base_do_negocio) if base_do_negocio else None,
        "sobra_centavos": sobra,
        **{c: reais(v) for c, v in valores.items()},
        "total": reais(total),
        "total_centavos": total,
    }


# Os itens da tabela que sao REGISTRO DE GARANTIA REAL, para o teto do art. 37.
# O 16.13.1 esta aqui porque o texto dele manda para o 16.45 («por cada registro
# das garantias reais ou gravames decorrentes de cedula ... os emolumentos serao
# os mesmos do item 16.45»).
ITENS_DE_GARANTIA_REAL = ("16.45", "16.13.1")


def teto_geral(con, vigencia: int | None = None) -> int:
    """O limite maximo de emolumentos do art. 37 da Lei 9.109/2009, em centavos.

    NAO E' NUMERO ESCRITO AQUI, e a razao e' a mesma da constante de custas do
    Protesto: ele muda por Resolucao a cada exercicio, e um numero no codigo
    faria a virada da tabela exigir versao nova do sistema.

    Ele sai da ULTIMA FAIXA DA TABELA 16.3, que e' onde o TJMA o escreve — e
    isso foi conferido, nao deduzido: a faixa `16.3.36` da vigencia 10022 traz
    **R$ 21.380,93** de emolumento, que e' exatamente o valor do art. 2o da
    Resolucao-GP 143/2025. Devolve 0 quando nao ha faixa (instalacao sem a
    tabela importada), e quem chama trata isso como «nao da' para conferir».
    """
    if vigencia is None:
        linha = con.execute(
            "SELECT codigo FROM cx_vigencias WHERE vigente=1").fetchone()
        if not linha:
            return 0
        vigencia = linha[0]
    ultima = con.execute(
        """SELECT emolumentos FROM cx_faixas WHERE vigencia=? AND tabela=?
           ORDER BY CAST(REPLACE(REPLACE(ate,'.',''),',','.') AS REAL) DESC
           LIMIT 1""", (vigencia, TABELA_RI)).fetchone()
    return centavos(ultima[0]) if ultima else 0


def garantias_acima_do_teto(itens: list[dict], teto: int) -> dict | None:
    """Os registros de garantia deste protocolo passam do teto do art. 37?

    **MEDE E AVISA; NAO CORTA NADA.** O item 16.31 diz que a soma dos registros
    das garantias observa o teto, e **como ele se conta esta em disputa aberta
    entre os colegas**: se o teto vale para cada tipo de garantia (hipoteca de
    um lado, penhor do outro — e ai' uma cedula com duas garantias tem dois
    tetos) ou para a soma de todos os registros do mesmo titulo. Ha oficio na
    corregedoria sobre isso.

    Cortar sozinho por uma das duas leituras seria o sistema decidindo tese
    juridica no lugar de quem assina. O que ele faz e' por o numero na frente
    de quem decide — a mesma regra do CNIB e do usucapiao.

    Devolve `None` quando nao ha o que avisar (sem teto medido, sem registro de
    garantia, ou a soma abaixo do teto).
    """
    if teto <= 0:
        return None
    da_garantia = [i for i in itens
                   if str(i.get("codigo_ato") or i.get("codigo_tj") or "")
                   .startswith(ITENS_DE_GARANTIA_REAL)]
    if not da_garantia:
        return None
    soma = sum(centavos(i.get("emolumentos")) for i in da_garantia)
    if soma <= teto:
        return None
    return {
        "registros": len(da_garantia),
        "emolumentos": reais(soma),
        "teto": reais(teto),
        "excesso": reais(soma - teto),
        # O teto e' de EMOLUMENTO; o que o cliente pagaria com os quatro fundos
        # e' outro numero, e e' esse que ele le' no orcamento. O acrescimo sai
        # de `PERCENTUAIS`, e nao de um «1,12» escrito aqui: o dia em que um
        # fundo mudar de percentual, o numero acompanha.
        "total_no_teto": reais(
            teto + sum(round(teto * p) for p in PERCENTUAIS.values())),
    }


def somar_itens(itens: list[dict]) -> dict:
    """Soma emolumentos, fundos e total de uma lista de itens."""
    campos = ("emolumentos", "ferc", "femp", "fadep", "ferrfis")
    soma = {c: 0 for c in campos}
    total = 0
    for i in itens:
        for c in campos:
            soma[c] += centavos(i.get(c))
        total += centavos(i.get("valor_total") or i.get("total"))
    return {**{c: reais(v) for c, v in soma.items()},
            "total": reais(total), "total_centavos": total}



# O balcao digita «2a via» / «segunda via» / «certidao nascimento»; a tabela
# do TJMA diz «Das certidoes: Com uma folha» (14.5.1). Sem estes aliases a
# busca devolve zero — e o protocolo de 2a via de nascimento fica com 0 itens.
# 14.5.2 = folha acrescida; 14.6.x = buscas (quando o pedido pede periodo).
CODIGOS_ALIAS_CERTIDAO_RCPN = (
    "14.5.1", "14.5.2",
    "14.6.1", "14.6.2", "14.6.3", "14.6.4",
    "14.6.5", "14.6.6", "14.6.7", "14.6.8",
)


def _termo_compacto_alias(termo_norm: str) -> str:
    """Tira o/a/grau e '2A' para casar «2a via» com «2 via»."""
    s = (termo_norm or "")
    for ch in ("\u00aa", "\u00ba", "\u00b0", "."):
        s = s.replace(ch, "")
    s = s.replace("2A", "2")
    while "  " in s:
        s = s.replace("  ", " ")
    return s.strip()


def _codigos_alias_busca(termo: str) -> tuple[str, ...]:
    """Codigos TJ a forcar na busca quando o termo e o nome da casa."""
    n = _termo_compacto_alias(_norm(termo))
    if not n:
        return ()
    pediu_via = ("SEGUNDA VIA" in n) or ("2 VIA" in n)
    pediu_cert_nasc = (
        "CERTIDAO NASCIMENTO" in n
        or "CERTIDAO DE NASCIMENTO" in n
        or ("CERTIDAO" in n and "NASCIMENTO" in n)
    )
    # «nascimento» sozinho: o balcao quer a certidao (14.5.1), nao o servico
    # inativo «1o via nascimento/obito/casamento» (713) sem preco.
    pediu_nascimento = (
        n == "NASCIMENTO"
        or n.endswith(" NASCIMENTO")
        or n.startswith("NASCIMENTO ")
    )
    if pediu_via or pediu_cert_nasc or pediu_nascimento:
        return CODIGOS_ALIAS_CERTIDAO_RCPN
    return ()


def buscar(con, termo: str, vigencia: int | None = None, limite: int = 60) -> list[dict]:
    """Busca por codigo do TJ ou por palavra da descricao.

    UM CODIGO DO TJ, UMA LINHA — e isto nao e' arrumacao de tela: era o que
    impedia o balcao de achar o ato. Medido em 21/09/2026 no banco da casa: dos
    1.317 servicos, **273 codigos do TJ aparecem mais de uma vez** (o mesmo
    `16.45.23` esta nos servicos 732, 1064 e 1506), e **so um de cada tem preco
    na vigencia** — os outros vem com `total` vazio e o clique neles devolve
    «Nao encontrei esse ato na tabela vigente», que manda conferir o codigo
    justamente quando ele esta certo.

    E o triplo de linhas estourava o limite ANTES do ato pedido: procurando
    `16.45` com o limite de 30 da tela, a lista parava no `16.45.18` — o
    `16.45.23`, que e' o da cedula de R$ 695 mil que o balcao estava orcando,
    **nao aparecia de jeito nenhum**.

    Fica a linha que TEM preco na vigencia. Isso nao esconde ato nenhum:
    medido no mesmo dia, **nenhum** codigo do TJ tem dois precos na vigencia —
    logo a escolha nunca decide entre dois valores.

    NAO LISTA ativo=0 NEM total NULL — medido em 24/09/2026: o servico 713
    («1o via nascimento/obito/casamento») inativo e sem preco aparecia em
    «nascimento» e o clique devolvia «Nao encontrei esse ato na tabela
    vigente». Sem preco nao ha o que acrescentar ao protocolo.

    ALIASES DE 2a VIA: «2 via» / «2a via» / «segunda via» / «certidao
    nascimento» mapeiam para 14.5.1 (e 14.5.2 / 14.6.x da casa). A descricao
    do TJ e «Das certidoes: Com uma folha» — sem alias a busca devolve zero.
    """
    if vigencia is None:
        linha = con.execute("SELECT codigo FROM cx_vigencias WHERE vigente=1").fetchone()
        vigencia = linha[0] if linha else None
    termo = (termo or "").strip()
    if not termo:
        return []
    like = f"%{_norm(termo)}%"
    aliases = _codigos_alias_busca(termo)
    # SEM `LIMIT` NO SQL: o corte vem DEPOIS de juntar as repetidas, senao ele
    # cortaria contando linhas que a tela nem vai mostrar. A tabela inteira tem
    # pouco mais de mil servicos, e a consulta ja filtra pelo termo.
    if aliases:
        ph = ",".join("?" * len(aliases))
        sql = f"""SELECT s.codigo, s.codigo_tj, s.descricao, v.emolumentos, v.total,
                  s.ativo
           FROM cx_servicos s
           LEFT JOIN cx_servico_valores v
                  ON v.servico = s.codigo AND v.vigencia = ?
           WHERE s.descricao_norm LIKE ? OR s.codigo_tj LIKE ?
              OR s.codigo_tj IN ({ph})
           ORDER BY s.ativo DESC, s.codigo_tj, s.codigo"""
        params = (vigencia, like, f"%{termo}%", *aliases)
    else:
        sql = """SELECT s.codigo, s.codigo_tj, s.descricao, v.emolumentos, v.total,
                  s.ativo
           FROM cx_servicos s
           LEFT JOIN cx_servico_valores v
                  ON v.servico = s.codigo AND v.vigencia = ?
           WHERE s.descricao_norm LIKE ? OR s.codigo_tj LIKE ?
           ORDER BY s.ativo DESC, s.codigo_tj, s.codigo"""
        params = (vigencia, like, f"%{termo}%")
    linhas = con.execute(sql, params).fetchall()
    achados: list[dict] = []
    por_codigo: dict[str, int] = {}
    for r in linhas:
        item = dict(zip(("codigo", "codigo_tj", "descricao", "emolumentos",
                         "total", "ativo"), r))
        # Sem ativo e sem preco: listar e convidar o clique que falha.
        if not item.get("ativo"):
            continue
        if item.get("total") is None:
            continue
        codigo_tj = item["codigo_tj"]
        # Sem codigo do TJ nao ha o que juntar: cada linha e' ela mesma.
        if not codigo_tj:
            achados.append(item)
            continue
        ja = por_codigo.get(codigo_tj)
        if ja is None:
            por_codigo[codigo_tj] = len(achados)
            achados.append(item)
        elif achados[ja]["total"] is None and item["total"] is not None:
            achados[ja] = item
    return achados[:limite]
