"""O agente das Notas — fiscaliza, revisa e prepara o Tabelionato de Notas.

    «Agente notas: esse agente eh responsavel por fiscalizar, revisar,
     resolver problemas, praticar atos, e tudo mais que o tabelionato de notas
     demande» — o oficial, 09/10/2026

O QUE ELE FAZ, E ONDE CADA COISA MORA
    fiscalizar  `REGRAS` — regras objetivas, cada uma com o artigo ao lado, que
                entram na conferência diária do gestor (07:30, 14:00, 14:30)
                pelo gancho `gestor_conferencia.MODULOS_DE_AGENTE`. Viram achado
                na fila do oficial e, quando o defeito pode dar dano a terceiro,
                tarefa para quem responde pelo setor.
    revisar     `revisar_minuta` — o que falta antes de lavrar cada ato EM
                LAVRATURA, pela natureza dele: imóvel, inventário, divórcio,
                procuração. É a mesma lista que vira a tarefa da qualificação.
    resolver    cada achado diz o que fazer e em que tela; o que for resolvido
                sai da lista sozinho na conferência seguinte, e a tarefa fecha
                quando a lista zera (é o mecanismo do gestor, e não um segundo).
    praticar    prepara: a minuta revisada, a carga da CENSEC conferida ato a
                ato, o livro conferido contra si mesmo. **Quem lança no livro,
                sela e cobra é a escrevente, pela tela de sempre** — lá estão a
                numeração, o selo, as custas e a auditoria; um atalho daqui
                pularia os quatro.
    relatar     `escrever_relatorio` — o painel do dia das Notas, em
                `relatorios/notas_AAAA-MM-DD.html`, ao lado do relatório do
                gestor.

O LIMITE É DA NORMA, E NÃO DE CAUTELA
    Código de Normas TJMA, art. 171: a IA pode assistir «na redação, análise e
    revisão de atos notariais» e na triagem de documentos, sempre
    supervisionada; art. 169, IV: nenhuma decisão automatizada substitui a
    análise humana em ato que envolva manifestação de vontade ou validação
    jurídica. Por isso este módulo **não lança, não sela, não cobra, não apaga
    e não envia a Central** — e há teste que varre os nomes públicos.

    Art. 176: os critérios têm de ser auditáveis. Por isso cada regra daqui é
    código com o artigo ao lado, e não opinião de modelo de linguagem: a mesma
    pergunta dá a mesma resposta amanhã. (A leitura por IA dos textos continua
    sendo a do gestor, `gestor_leitura`, e não se repete aqui.)

O QUE FOI MEDIDO ANTES DE ESCREVER (produção, só leitura, 09/10/2026)
    11 atos de livro fora do acervo: 6 lavrados, 5 em lavratura. Nenhuma
    remessa à CENSEC registrada em `nt_remessas`. A escritura 778 (divórcio)
    sem `tipo_cesdi` — iria à central errada. A mesma 778 com o termo 5522,
    e o contador fixado em 5723 cinco dias depois por ordem do oficial: entre
    um e outro há 200 termos sem ato no sistema. Três rascunhos de procuração
    (787, 789, 790) vazios ou com as mesmas partes de procurações já lavradas.
"""
from __future__ import annotations

import html
import re
import sqlite3
import unicodedata
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

import gestor_conferencia as GC

#: O corte de 10/09/2026 é o do gestor: ato anterior não vira cobrança
#: (ordem do oficial). Um número só na casa — importado, e não copiado.
CORTE = GC.IMPLANTACAO

SETOR_QUALIFICACAO = "NOTAS_QUALIFICACAO"   # Beatriz (substituto: o oficial)
SETOR_OPERACIONAL = "NOTAS"                 # Carla (substituta: Beatriz)

#: Rascunho vazio depois disto já não é «está sendo escrito».
DIAS_RASCUNHO_VAZIO = 2
#: Rascunho com texto parado depois disto merece a pergunta.
DIAS_RASCUNHO_PARADO = 30
#: O PDF assinado entra depois da lavratura; uma semana é folga de sobra.
DIAS_SEM_PDF_ASSINADO = 7
#: Art. 799, III: trinta dias sem as assinaturas, a escritura é incompleta.
DIAS_ESCRITURA_INCOMPLETA = 30

FUND_CENSEC = ("Código de Normas TJMA, art. 785 (alimentar a CENSEC nos prazos) e "
               "Provimento CNJ 149/2023, art. 267 (quinzenas)")
FUND_NUMERACAO = ("Código de Normas TJMA, art. 792 (numeração contínua, que não se "
                  "interrompe) e art. 795, § 2º (escrituração seguida, sem claros)")
FUND_LIVROS = ("Código de Normas TJMA, art. 788, § 2º (livros simultâneos só com "
               "autorização da Corregedoria, sem paralisar um deles por mais de 8 dias)")
FUND_ANOTACAO = ("Código de Normas TJMA, art. 831 (anotar imediatamente à margem do "
                 "ato originário) e art. 832")
FUND_CNIB = ("Provimento CNJ 39/2014, art. 14 (consulta prévia à CNIB e o código "
             "hash consignado no ato)")
FUND_IMPOSTO = ("Código de Normas TJMA, art. 798, § 3º (certificar o pagamento do "
                "imposto de transmissão) e art. 791, VIII")
FUND_DOI = "Código de Normas TJMA, art. 797 e art. 800, VII (referência à DOI no ato)"
FUND_INVENTARIO = ("Código de Normas TJMA, arts. 811 (X, XI e XIII), 812 e 818, V "
                   "(testamento, CENSEC/RCTO e advogado)")
FUND_DIVORCIO = "Código de Normas TJMA, arts. 824 a 827 (advogado e documentos)"
FUND_QUALIFICACAO = ("Código de Normas TJMA, art. 798, V (nome e qualificação das "
                     "partes) e art. 791, I")
FUND_TEXTO = ("Código de Normas TJMA, art. 795, § 2º (sem claros ou espaços em "
              "branco)")
FUND_INCOMPLETA = ("Código de Normas TJMA, art. 799, III e IV (trinta dias sem as "
                   "assinaturas: escritura incompleta; vedado traslado ou certidão)")


# ------------------------------------------------------------------ ajudantes

def _sem_acento(texto) -> str:
    """MAIÚSCULAS sem acento — a forma em que se compara palavra de norma."""
    t = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in t if not unicodedata.combining(c)).upper()


def _plano(teor) -> str:
    """O teor sem marcação HTML, com os espaços colapsados."""
    t = re.sub(r"<[^>]+>", " ", str(teor or ""))
    t = html.unescape(t)
    return re.sub(r"\s+", " ", t).strip()


def _dia(valor) -> date | None:
    return GC._dia(valor)


def _tem_tabela(con: sqlite3.Connection, nome: str) -> bool:
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                       (nome,)).fetchone() is not None


def _colunas(con: sqlite3.Connection, tabela: str) -> set[str]:
    """As colunas da tabela, lidas do cursor — sem PRAGMA (teto zero)."""
    cur = con.execute(f"SELECT * FROM {tabela} LIMIT 0")
    return {d[0] for d in cur.description}


def _pronto(con: sqlite3.Connection) -> bool:
    """O banco tem as Notas com as colunas que estas regras leem?

    Banco sem as Notas não é defeito para cobrar: é instalação que não usa a
    atribuição. A regra devolve lista vazia — e não NAO_MEDIU, que é para
    regra que QUEBROU.
    """
    if not (_tem_tabela(con, "nt_atos") and _tem_tabela(con, "nt_ato_partes")):
        return False
    return {"termo", "lancado_em", "tipo_cesdi"} <= _colunas(con, "nt_atos")


def _nome(tipo) -> str:
    """O nome do tipo de ato como a casa o escreve — «Procuração», e não
    «Procuracao»: o rótulo vem de `notas_schema.TIPOS_ATO`, que já existe."""
    from notas_schema import TIPOS_ATO
    t = (tipo or "").upper()
    return TIPOS_ATO.get(t, t.capitalize() or "Ato").replace(" pública", "")


def _rotulo_ato(a) -> str:
    tipo = _nome(a["tipo"])
    if a["livro"] and a["folha"]:
        onde = f"livro {a['livro']}, fl. {a['folha']}"
        if a["termo"]:
            onde += f", termo {a['termo']}"
    else:
        onde = "ainda sem livro"
    return f"{tipo} {a['id']} ({onde})"


def _partes(con: sqlite3.Connection, ato_id: int) -> list[sqlite3.Row]:
    return con.execute(
        """SELECT * FROM nt_ato_partes WHERE ato_id = ? ORDER BY ordem, id""",
        (ato_id,)).fetchall()


def _documento_ruim(doc) -> str | None:
    """«falta» ou «não fecha o dígito» — ou None se o documento serve."""
    from notas_partes import documento_valido, so_digitos
    d = so_digitos(doc)
    if not d:
        return "sem CPF/CNPJ"
    if documento_valido(d) is False:
        return f"CPF/CNPJ {d} não fecha o dígito verificador"
    return None


#: Palavras que, na natureza ou no teor, dizem que o ato trata de imóvel.
_IMOVEL = re.compile(r"IMOVE|COMPRA E VENDA|DOAC|PERMUT|DACAO|INVENTARI|PARTILHA|"
                     r"ADJUDICA|USUFRUTO|AFORAMENTO|ENFITEU|CESSAO .*HEREDIT|"
                     r"MATRICULA|HIPOTEC|ALIENACAO FIDUCI")
#: Atos que transmitem — e por isso cobram o imposto de transmissão.
_TRANSMITE = re.compile(r"COMPRA|VENDA|DOAC|PERMUT|DACAO|CESSAO|INVENTARI|PARTILHA|"
                        r"ADJUDICA|TRANSMISS")
_INVENTARIO = re.compile(r"INVENTARI|PARTILHA|ADJUDICA|SOBREPARTILHA")
_DIVORCIO = re.compile(r"DIVORCI|SEPARACAO|SEPARAC|RESTABELECIMENTO DA SOCIEDADE")
#: Natureza que a CESDI recebe — e a CEP não (notas_censec.separar).
_CESDI = re.compile(r"DIVORCI|SEPARAC|INVENTARI|PARTILHA|SOBREPARTILHA|ADJUDICA")


def _trata_de_imovel(a) -> bool:
    if a["com_imovel"] or a["doi_transacao"] is not None:
        return True
    return bool(_IMOVEL.search(_sem_acento(a["natureza"])))


def _claros_no_texto(teor) -> list[str]:
    """Marcas de texto por terminar — art. 795, § 2º: sem claros nem brancos.

    O traço de assinatura NÃO conta: «______» sozinho na linha é o lugar de
    assinar, e está certo. O que conta é o claro **depois de dois pontos**
    («consignado: _»), o marcador de modelo e o trecho ainda destacado em
    amarelo — este último foi pedido pela própria substituta na nota da 786
    («preencher todos os trechos amarelos … retirar os destaques»).
    """
    bruto = str(teor or "")
    plano = _plano(bruto)
    achados = []
    if re.search(r":\s*_+(?=[\s.;,)]|$)", plano):
        achados.append("claro a preencher depois de dois-pontos («…: _»)")
    if re.search(r"\[\s*COMPLETAR|\{\{|\bX{3,}\b|\?{3,}", plano, re.IGNORECASE):
        achados.append("marcador de modelo ou «[COMPLETAR]» ainda no texto")
    if re.search(r"background(?:-color)?\s*:\s*(?:yellow|#ff0\b|#ffff00|"
                 r"rgb\(\s*255\s*,\s*255\s*,\s*0\s*\))|<mark\b", bruto, re.IGNORECASE):
        achados.append("trecho ainda destacado em amarelo")
    return achados


# --------------------------------------------------------------- a revisão

def revisar_minuta(con: sqlite3.Connection, ato) -> list[dict]:
    """O que falta antes de lavrar este ato. Só lê.

    Cada item é {item, fundamento}. A lista é OBJETIVA — o que se confere no
    banco e no texto —, e não substitui a qualificação: diz onde olhar. O
    juízo sobre o negócio continua sendo de quem lavra (art. 169, IV).
    """
    if isinstance(ato, int):
        ato = con.execute("SELECT * FROM nt_atos WHERE id = ?", (ato,)).fetchone()
    if ato is None:
        return []
    itens: list[dict] = []

    def falta(texto: str, fundamento: str) -> None:
        itens.append({"item": texto, "fundamento": fundamento})

    partes = _partes(con, ato["id"])
    natureza = _sem_acento(ato["natureza"])
    plano = _sem_acento(_plano(ato["teor"]))
    imovel = _trata_de_imovel(ato)

    if not (ato["teor"] or "").strip():
        falta("o ato ainda não tem texto (teor)", FUND_TEXTO)
    if not partes:
        falta("nenhuma parte cadastrada no ato", FUND_QUALIFICACAO)
    sem_papel = []
    for p in partes:
        ruim = _documento_ruim(p["documento"])
        if ruim:
            falta(f"{p['nome']}: {ruim}", FUND_QUALIFICACAO)
        if not (p["qualificacao"] or "").strip():
            sem_papel.append(p["nome"])
    if sem_papel:
        falta("partes sem qualificação (outorgante, outorgado, vendedor…): "
              + ", ".join(sem_papel), FUND_QUALIFICACAO)

    for claro in _claros_no_texto(ato["teor"]):
        falta(f"o texto tem {claro}", FUND_TEXTO)

    if imovel and (ato["tipo"] or "").upper() == "ESCRITURA":
        if "CNIB" not in plano:
            falta("consultar a CNIB e consignar no texto o resultado e o código hash",
                  FUND_CNIB)
        elif re.search(r"CNIB[^.]{0,120}:\s*_", plano):
            falta("o resultado da consulta à CNIB está em branco no texto", FUND_CNIB)
        if _TRANSMITE.search(natureza) and not re.search(
                r"IMPOSTO DE TRANSMISS|\bITBI\b|\bITCD\b|\bITCMD\b", plano):
            falta("certificar o pagamento do imposto de transmissão (valor, guia e data)",
                  FUND_IMPOSTO)
        if not re.search(r"\bDOI\b|DECLARACAO SOBRE OPERAC", plano):
            falta("fazer constar a referência à emissão da DOI", FUND_DOI)
        if ato["doi_transacao"] is None:
            falta("escolher na ficha o tipo de operação da DOI", FUND_DOI)
        sem_lado = [p["nome"] for p in partes
                    if not (p["doi_lado"] if "doi_lado" in p.keys() else None)
                    and not p["testemunha"]]
        if partes and sem_lado and len(sem_lado) == len(partes):
            falta("nenhuma parte marcada como alienante ou adquirente para a DOI",
                  FUND_DOI)
        if ato["valor_transacao"] is None:
            falta("informar o valor declarado do negócio (a CENSEC e a DOI exigem)",
                  FUND_CENSEC)

    qualificacoes = " ".join(_sem_acento(p["qualificacao"]) for p in partes)
    if _INVENTARIO.search(natureza):
        if not re.search(r"RCTO|CENSEC|TESTAMENT", plano):
            falta("certidão da CENSEC/RCTO e declaração de inexistência de testamento",
                  FUND_INVENTARIO)
        if "ADVOGAD" not in qualificacoes and "ADVOGAD" not in plano:
            falta("o inventário exige advogado no ato", FUND_INVENTARIO)
    if _DIVORCIO.search(natureza):
        if "ADVOGAD" not in qualificacoes and "ADVOGAD" not in plano:
            falta("separação e divórcio exigem advogado (OAB, seção e UF)", FUND_DIVORCIO)
    if _CESDI.search(natureza) and ato["tipo_cesdi"] is None:
        falta("marcar o tipo de ato da CESDI — sem ele o ato vai à central errada",
              FUND_CENSEC)

    nota = _sem_acento(ato["observacao"])
    if re.search(r"NAO LANCAR|PENDENCIA|A COMPLETAR|ANTES DA LAVRATURA", nota):
        falta("há nota pré-lavratura com pendências — ler a anotação antes de lançar",
              "anotação de lavratura da própria ficha")
    return itens


# --------------------------------------------------------------- as regras

def _quinzenas(desde: str, hoje: date) -> list[tuple[int, int, int]]:
    """As quinzenas do corte até hoje, inclusive a corrente."""
    d = _dia(desde) or hoje
    saida = []
    while d <= hoje:
        q = 1 if d.day <= 15 else 2
        if (d.year, d.month, q) not in saida:
            saida.append((d.year, d.month, q))
        d = d.replace(day=16) if q == 1 else (
            date(d.year + (d.month == 12), d.month % 12 + 1, 1))
    return saida


#: O nome da parte que o `notas_censec` põe na frente do motivo (09/10/2026).
_PARTE_NO_MOTIVO = re.compile(r"^(?P<nome>[^:]+): (?P<resto>qualificação .+)$")


def regra_censec_por_ato(con: sqlite3.Connection, hoje: date) -> list[dict]:
    """Cada ato lavrado que a carga da CENSEC recusaria — e por quê.

    A regra «CENSEC» do gestor diz que a QUINZENA não foi enviada; esta diz
    QUAL ATO trava o envio e o que falta nele. A conta é a mesma da tela
    (`notas_censec.separar`), para a tarefa não dizer uma coisa e o arquivo
    outra.

    **O DIVÓRCIO SEM O TIPO DA CESDI VAI À CENTRAL ERRADA.** `separar` manda à
    CEP toda escritura sem `tipo_cesdi` — e a 778, divórcio, está assim. Os
    impedimentos da CEP sobre ela seriam ruído (ela nem devia estar lá): o que
    se diz é o que de fato falta, o tipo da CESDI.
    """
    if not _pronto(con):
        return []
    import notas_censec as NC
    saida, vistos = [], set()
    for (ano, mes, q) in _quinzenas(CORTE, hoje):
        for central in ("CESDI", "RCTO", "CEP"):
            sep = NC.separar(con, central, ano, mes, q)
            prazo = _dia(sep["prazo"])
            for imp in sep["impedidos"]:
                a = imp["ato"]
                if GC.antes_do_corte(a["data"]) or a["id"] in vistos:
                    continue
                vistos.add(a["id"])
                # A mesma recusa em três partes é UMA pendência com três nomes:
                # repetida, ela empurra para fora da tela a que importa.
                #
                # 13/10/2026: desde 09/10 o `notas_censec` escreve o NOME da parte
                # dentro do motivo («A: qualificação '(em branco)' não corresponde…»),
                # e a contagem deixou de juntar — cada parte virava uma linha. O nome
                # sai do texto antes de contar e volta no fim, junto dos outros.
                contagem: dict[str, int] = {}
                nomes: dict[str, list[str]] = {}
                for p in imp["problemas"]:
                    motivo = str(p["motivo"])
                    quem = ""
                    m = _PARTE_NO_MOTIVO.match(motivo) if p["campo"] == "partes.qualidade" else None
                    if m:
                        quem, motivo = m.group("nome"), m.group("resto")
                    texto = f"{p['campo']}: {motivo}"
                    for antiga in ("qualificação None não corresponde",
                                   "qualificação '(em branco)' não corresponde"):
                        texto = texto.replace(antiga, "parte sem qualificação — não corresponde")
                    contagem[texto] = contagem.get(texto, 0) + 1
                    if quem:
                        nomes.setdefault(texto, []).append(quem)
                motivos = [(t if n == 1 else f"{t} ({n} partes)")
                           + (f" — {'; '.join(nomes[t])}" if nomes.get(t) else "")
                           for t, n in contagem.items()]
                destino = central
                if (central == "CEP" and a.get("tipo_cesdi") is None
                        and _CESDI.search(_sem_acento(a.get("natureza")))):
                    destino = "CESDI"
                    motivos = [f"a natureza («{a.get('natureza')}») é da CESDI, e o ato "
                               "está sem o tipo da CESDI — marcar o tipo; depois a "
                               "conferência dirá o resto"]
                gravidade = "VENCIDO" if prazo and hoje > prazo else "PRAZO"
                quando = _dia(a["data"])
                saida.append(GC._achado(
                    f"NOTAS_CENSEC:nt_atos:{a['id']}:{destino}", "NOTAS_CENSEC",
                    gravidade, SETOR_QUALIFICACAO,
                    f"{_nome(a.get('tipo'))} {a['id']} de "
                    f"{quando:%d/%m/%Y} — a carga da {destino} recusaria" if quando else
                    f"Ato {a['id']} — a carga da {destino} recusaria",
                    "; ".join(motivos[:8]), prazo, FUND_CENSEC))
    return saida


def regra_livros(con: sqlite3.Connection, hoje: date) -> list[dict]:
    """O livro conferido contra si mesmo, só no que este sistema lançou.

    Três perguntas da correição: dois atos na mesma folha, termo repetido, e
    termo que pula. O acervo fica de fora — as folhas dele vieram como texto,
    e acusar setenta anos de livro seria o alarme que soa sempre.

    **O TERMO QUE MAIS IMPORTA É O DO CONTADOR.** Se o maior termo em uso do
    contador (`nt_termos.maior_em_uso`) passa do maior termo de ato lançado
    pelo sistema, há termos «em uso» sem ato aqui: ou foram lavrados por fora,
    ou o termo do ato está errado. Medido em 09/10/2026: escritura 778 com o
    termo 5522 e o contador dizendo 5722 em uso.
    """
    if not _pronto(con) or not _tem_tabela(con, "nt_livros"):
        return []
    from notas_livro import inteiro

    def faixa(r):
        i = inteiro(r["folha_inicial_num"]) or inteiro(r["folha"])
        f = inteiro(r["folha_final_num"]) or inteiro(r["folha_final"]) or i
        return (i, f) if i else None

    saida = []
    atos = con.execute(
        """SELECT * FROM nt_atos WHERE situacao <> 'EM_LAVRATURA'
              AND lancado_em IS NOT NULL AND livro_id IS NOT NULL""").fetchall()

    # dois atos na mesma folha do mesmo livro
    por_livro: dict[int, list] = {}
    for a in atos:
        por_livro.setdefault(a["livro_id"], []).append(a)
    for livro_id, lista in por_livro.items():
        outros = con.execute(
            """SELECT id, folha, folha_final, folha_inicial_num, folha_final_num
                 FROM nt_atos WHERE livro_id = ? AND situacao <> 'EM_LAVRATURA'""",
            (livro_id,)).fetchall()
        for a in lista:
            fa = faixa(a)
            if not fa:
                continue
            for o in outros:
                if o["id"] == a["id"]:
                    continue
                fo = faixa(o)
                if fo and fo[0] <= fa[1] and fa[0] <= fo[1]:
                    par = tuple(sorted((a["id"], o["id"])))
                    chave = f"NOTAS_LIVRO:nt_atos:{par[1]}:FOLHA:{par[0]}"
                    if any(x["chave"] == chave for x in saida):
                        continue
                    saida.append(GC._achado(
                        chave, "NOTAS_LIVRO", "CRITICO", SETOR_OPERACIONAL,
                        f"Livro {a['livro']}: os atos {par[0]} e {par[1]} ocupam a "
                        f"mesma folha ({fa[0]}–{fa[1]} × {fo[0]}–{fo[1]})",
                        "Conferir no livro físico qual ato está na folha e corrigir a "
                        "do outro pela tela do livro.", None, FUND_NUMERACAO))

    # termo repetido e termo do contador sem ato
    if _tem_tabela(con, "nt_termos"):
        contador = {r["serie"]: r for r in con.execute("SELECT * FROM nt_termos")}
        series: dict[str, list] = {}
        for a in atos:
            if a["termo"] is not None:
                series.setdefault(a["serie"] or a["tipo"], []).append(a)
        for serie, lista in series.items():
            termos: dict[int, list] = {}
            for a in lista:
                termos.setdefault(int(a["termo"]), []).append(a["id"])
            for termo, ids in termos.items():
                if len(ids) > 1:
                    saida.append(GC._achado(
                        f"NOTAS_LIVRO:nt_atos:{max(ids)}:TERMO:{termo}", "NOTAS_LIVRO",
                        "CRITICO", SETOR_OPERACIONAL,
                        f"{_nome(serie)}: o termo {termo} está em {len(ids)} atos "
                        f"({', '.join(map(str, sorted(ids)))})",
                        "Dois atos com o mesmo termo no livro: conferir no papel qual é "
                        "o certo.", None, FUND_NUMERACAO))
            maior_ato = max(termos)
            c = contador.get(serie)
            em_uso = int(c["maior_em_uso"] or 0) if c else 0
            if em_uso > maior_ato:
                ultimo = max(lista, key=lambda r: int(r["termo"]))
                saida.append(GC._achado(
                    f"NOTAS_LIVRO:nt_atos:{ultimo['id']}:CONTADOR:{serie}", "NOTAS_LIVRO",
                    "ATENCAO", SETOR_OPERACIONAL,
                    f"{_nome(serie)}: o contador diz que o termo {em_uso} está em "
                    f"uso, e o último ato lançado pelo sistema é o termo {maior_ato}",
                    f"Termos {maior_ato + 1} a {em_uso} ({em_uso - maior_ato}) sem ato no "
                    f"sistema. O contador foi fixado em {c['fixado_em'] or '?'} por "
                    f"«{c['fixado_por'] or '?'}» ({c['observacao'] or 'sem observação'}). "
                    "Conferir no livro físico: ou esses "
                    f"termos foram lavrados por fora (e o ato precisa ser cadastrado), "
                    f"ou o termo do ato {ultimo['id']} ({_rotulo_ato(ultimo)}) está "
                    "errado — decisão do oficial.", None, FUND_NUMERACAO))

    # mais de um livro aberto da mesma espécie
    abertos: dict[str, list] = {}
    for r in con.execute("""SELECT * FROM nt_livros WHERE COALESCE(ativo,1) = 1
                               AND COALESCE(encerrado,0) = 0"""):
        abertos.setdefault(r["tipo"], []).append(r)
    for tipo, livros in abertos.items():
        if len(livros) > 1:
            nomes = ", ".join(f"Livro {l['numero']} (folha {l['folha_atual']})"
                              for l in livros)
            saida.append(GC._achado(
                f"NOTAS_LIVRO:DOIS_ABERTOS:{tipo}", "NOTAS_LIVRO", "ATENCAO",
                SETOR_OPERACIONAL,
                f"{len(livros)} livros de {_nome(tipo).lower()} abertos ao mesmo tempo",
                f"{nomes}. Livros simultâneos só com autorização da Corregedoria; sem "
                "ela, encerrar ou desativar o que não está em uso.", None, FUND_LIVROS))
    return saida


def regra_anotacao_a_margem(con: sqlite3.Connection, hoje: date) -> list[dict]:
    """Revogação, renúncia e substabelecimento lavrados sem a anotação à margem.

    Procuração revogada que continua «limpa» no livro é a procuração que o
    procurador usa amanhã com a certidão desta casa na mão — dano a terceiro
    na forma mais direta (art. 831: anotar IMEDIATAMENTE).

    Só o ato anterior DESTA casa entra: o de outra serventia se comunica por
    carta (§ 1º), e o sistema não tem onde guardar o comprovante — cobrar o que
    não se pode registrar seria cobrar para sempre.
    """
    if not _pronto(con) or not _tem_tabela(con, "nt_ato_anotacoes"):
        return []
    from notas_schema import ATO_PEDE_ANOTACAO
    tipos = tuple(ATO_PEDE_ANOTACAO)
    saida = []
    for a in con.execute(
            f"""SELECT * FROM nt_atos WHERE situacao = 'LAVRADO' AND data >= ?
                   AND tipo IN ({','.join('?' * len(tipos))})""", (CORTE, *tipos)):
        if a["anterior_ato_id"]:
            anotado = con.execute(
                """SELECT 1 FROM nt_ato_anotacoes WHERE ato_id = ?
                      AND (ato_relacionado_id = ? OR ato_relacionado_id IS NULL)
                      AND tipo = ?""",
                (a["anterior_ato_id"], a["id"], ATO_PEDE_ANOTACAO[a["tipo"]])).fetchone()
            if anotado:
                continue
            detalhe = (f"Anotar à margem do ato {a['anterior_ato_id']} a "
                       f"{_nome(a['tipo']).lower()} lavrada no ato {a['id']} — sem ônus e "
                       "sem selo.")
            gravidade = "VENCIDO"
        elif a["anterior_cns"] or a["anterior_livro"]:
            # Ato de outra serventia: comunica-se por carta (§ 1º). Desde o
            # relato #129 (14/10/2026) há onde guardar o comprovante — a
            # obrigação ABERTA em `nt_comunicacoes_origem` vira achado.
            aberta = (_tem_tabela(con, "nt_comunicacoes_origem") and con.execute(
                """SELECT destinatario FROM nt_comunicacoes_origem
                   WHERE ato_id = ? AND situacao = 'ABERTA'""",
                (a["id"],)).fetchone())
            if not aberta:
                continue
            saida.append(GC._achado(
                f"NOTAS_COMUNICACAO_ORIGEM:nt_atos:{a['id']}", "NOTAS_ANOTACAO",
                "VENCIDO", SETOR_QUALIFICACAO,
                f"{_rotulo_ato(a)} sem a comunicação à serventia de origem",
                f"Comunicar {aberta['destinatario']} e, na ficha do ato, juntar o "
                "comprovante de recebimento ou anotar o envio do ofício "
                "(art. 831, § 1º).", None, FUND_ANOTACAO))
            continue
        else:
            detalhe = ("O ato não diz qual procuração alcança (livro, folha ou o ato "
                       "desta casa): sem isso a anotação à margem não tem onde ser feita.")
            gravidade = "ATENCAO"
        saida.append(GC._achado(
            f"NOTAS_ANOTACAO:nt_atos:{a['id']}", "NOTAS_ANOTACAO", gravidade,
            SETOR_QUALIFICACAO, f"{_rotulo_ato(a)} sem a anotação à margem do ato anterior",
            detalhe, None, FUND_ANOTACAO))
    return saida


def regra_escritura_de_imovel(con: sqlite3.Connection, hoje: date) -> list[dict]:
    """Escritura de imóvel JÁ LAVRADA sem CNIB, imposto ou DOI no texto.

    Três coisas que o texto da escritura tem de dizer e que se conferem por
    palavra. A ausência da CNIB é a grave: escritura sobre bem indisponível é
    o dano que o Provimento 39 existe para impedir.
    """
    if not _pronto(con):
        return []
    saida = []
    for a in con.execute(
            """SELECT * FROM nt_atos WHERE situacao = 'LAVRADO' AND tipo = 'ESCRITURA'
                  AND data >= ? AND lancado_em IS NOT NULL""", (CORTE,)):
        if not _trata_de_imovel(a):
            continue
        plano = _sem_acento(_plano(a["teor"]))
        natureza = _sem_acento(a["natureza"])
        faltas, gravidade = [], "ATENCAO"
        if "CNIB" not in plano:
            faltas.append("não menciona a consulta à CNIB nem o código hash")
            gravidade = "CRITICO"
        if _TRANSMITE.search(natureza) and not re.search(
                r"IMPOSTO DE TRANSMISS|\bITBI\b|\bITCD\b|\bITCMD\b", plano):
            faltas.append("não certifica o pagamento do imposto de transmissão")
            gravidade = "CRITICO"
        if not re.search(r"\bDOI\b|DECLARACAO SOBRE OPERAC", plano):
            faltas.append("não faz referência à emissão da DOI")
        if not faltas:
            continue
        saida.append(GC._achado(
            f"NOTAS_IMOVEL:nt_atos:{a['id']}", "NOTAS_IMOVEL", gravidade,
            SETOR_QUALIFICACAO, f"{_rotulo_ato(a)} — escritura de imóvel incompleta no texto",
            "; ".join(faltas) + ". Ato lavrado se corrige por escritura de "
            "retificação/rerratificação (ou, se erro material evidente da serventia, "
            "art. 795, § 8º).", None, "; ".join((FUND_CNIB, FUND_IMPOSTO, FUND_DOI))))
    return saida


def regra_minutas(con: sqlite3.Connection, hoje: date) -> list[dict]:
    """Cada ato EM LAVRATURA com texto — o que falta antes de lançar no livro.

    É a revisão (`revisar_minuta`) virando fila. Rascunho vazio fica para a
    regra dos rascunhos: aqui só entra quem já começou a ser escrito.
    """
    if not _pronto(con):
        return []
    saida = []
    for a in con.execute(
            """SELECT * FROM nt_atos WHERE situacao = 'EM_LAVRATURA'
                  AND teor IS NOT NULL AND length(teor) > 200"""):
        itens = revisar_minuta(con, a)
        if not itens:
            continue
        saida.append(GC._achado(
            f"NOTAS_MINUTA:nt_atos:{a['id']}", "NOTAS_MINUTA", "ATENCAO",
            SETOR_QUALIFICACAO,
            f"{_rotulo_ato(a)} — {len(itens)} ponto(s) antes de lavrar",
            "; ".join(i["item"] for i in itens), None,
            "; ".join(sorted({i["fundamento"] for i in itens}))))
    return saida


def regra_rascunhos(con: sqlite3.Connection, hoje: date) -> list[dict]:
    """Rascunho vazio, rascunho já substituído e rascunho parado.

    **O SUBSTITUÍDO SE RECONHECE PELAS PARTES.** Medido em 09/10/2026: o
    rascunho 787 (02/10) tem as mesmas partes da procuração 788, lavrada em
    08/10. Ele não é trabalho pendente — é sobra, e ocupa a lista de quem
    procura o que fazer. Quem apaga é a escrevente, pelo botão «Apagar
    rascunho» (que guarda o teor na auditoria); o agente só aponta.
    """
    if not _pronto(con):
        return []
    saida = []
    for a in con.execute("SELECT * FROM nt_atos WHERE situacao = 'EM_LAVRATURA'"):
        desde = _dia(a["data"]) or _dia((a["criado_em"] or "")[:10]) or hoje
        dias = (hoje - desde).days
        docs = {re.sub(r"\D", "", p["documento"] or "") for p in _partes(con, a["id"])}
        docs.discard("")
        texto = (a["teor"] or "").strip()
        motivo = None
        if docs:
            for l in con.execute(
                    """SELECT id, data, livro, folha, termo, tipo FROM nt_atos
                        WHERE situacao = 'LAVRADO' AND tipo = ? AND data >= ? AND id <> ?""",
                    (a["tipo"], a["data"], a["id"])):
                ldocs = {re.sub(r"\D", "", p["documento"] or "")
                         for p in _partes(con, l["id"])}
                if docs <= ldocs:
                    motivo = (f"as partes são as mesmas da {_nome(l['tipo']).lower()} "
                              f"{l['id']}, "
                              f"lavrada em {_dia(l['data']):%d/%m/%Y} (livro {l['livro']}, "
                              f"fl. {l['folha']}) — provavelmente já substituído")
                    break
        if motivo is None and not texto and dias >= DIAS_RASCUNHO_VAZIO:
            motivo = f"rascunho sem texto há {dias} dias"
        if motivo is None and texto and dias >= DIAS_RASCUNHO_PARADO:
            motivo = f"rascunho parado há {dias} dias"
        if motivo is None:
            continue
        saida.append(GC._achado(
            f"NOTAS_RASCUNHO:nt_atos:{a['id']}", "NOTAS_RASCUNHO", "ATENCAO",
            SETOR_QUALIFICACAO, f"{_nome(a['tipo'])} {a['id']} em "
            f"lavratura: {motivo}",
            "Se não vai ser lavrado, apagar pelo botão «Apagar rascunho» na ficha do ato "
            "(o texto fica guardado na auditoria); se vai, completar.", None, ""))
    return saida


def regra_pdf_assinado(con: sqlite3.Connection, hoje: date) -> list[dict]:
    """Ato lançado há mais de uma semana sem o PDF assinado anexado.

    O PDF assinado é a prova de que o ato foi assinado por quem devia — pedido
    do oficial («gerar e receber o upload do pdf assinado após a lavratura e
    selo»). Passados trinta dias, a pergunta muda de natureza: escritura sem
    as assinaturas é incompleta, e dela não sai traslado nem certidão.
    """
    if not _pronto(con) or not _tem_tabela(con, "attachments"):
        return []
    saida = []
    for a in con.execute(
            """SELECT * FROM nt_atos WHERE situacao = 'LAVRADO' AND data >= ?
                  AND lancado_em IS NOT NULL""", (CORTE,)):
        lancado = _dia((a["lancado_em"] or "")[:10])
        if not lancado or (hoje - lancado).days < DIAS_SEM_PDF_ASSINADO:
            continue
        tem = con.execute(
            """SELECT 1 FROM attachments WHERE entity_type = 'NT_ATO' AND entity_id = ?
                  AND lower(COALESCE(description,'')) LIKE '%assinad%'""",
            (a["id"],)).fetchone()
        if tem:
            continue
        dias = (hoje - lancado).days
        incompleta = (a["tipo"] or "").upper() == "ESCRITURA" and \
            dias >= DIAS_ESCRITURA_INCOMPLETA
        saida.append(GC._achado(
            f"NOTAS_PDF:nt_atos:{a['id']}", "NOTAS_PDF", "ATENCAO", SETOR_OPERACIONAL,
            f"{_rotulo_ato(a)} lançado há {dias} dias sem o PDF assinado",
            ("Conferir se todas as partes assinaram. Passados 30 dias sem as assinaturas, "
             "a escritura é declarada incompleta e dela não se extrai traslado nem "
             "certidão. " if incompleta else "")
            + "Anexar o PDF assinado na ficha do ato («PDF assinado do ato»).",
            None, FUND_INCOMPLETA if incompleta else ""))
    return saida


#: A ordem é a de aperto: o que pode dar dano primeiro.
REGRAS: tuple[tuple[str, Callable], ...] = (
    ("NOTAS_ANOTACAO", regra_anotacao_a_margem),
    ("NOTAS_IMOVEL", regra_escritura_de_imovel),
    ("NOTAS_LIVRO", regra_livros),
    ("NOTAS_CENSEC", regra_censec_por_ato),
    ("NOTAS_MINUTA", regra_minutas),
    ("NOTAS_RASCUNHO", regra_rascunhos),
    ("NOTAS_PDF", regra_pdf_assinado),
)

#: O nome da regra como o balcão lê no título da tarefa.
ROTULOS = {
    "NOTAS_ANOTACAO": "Notas — revogação/substabelecimento sem anotação à margem",
    "NOTAS_IMOVEL": "Notas — escritura de imóvel sem CNIB, imposto ou DOI no texto",
    "NOTAS_LIVRO": "Notas — livro: folha, termo ou livro aberto em duplicidade",
    "NOTAS_CENSEC": "Notas — atos que a carga da CENSEC recusaria",
    "NOTAS_MINUTA": "Notas — minutas: o que falta antes de lavrar",
    "NOTAS_RASCUNHO": "Notas — rascunhos vazios, parados ou já substituídos",
    "NOTAS_PDF": "Notas — atos lançados sem o PDF assinado",
}

#: Ordem do oficial de 06/10/2026: só vira tarefa o que pode gerar
#: responsabilidade civil (art. 22 da Lei 8.935). Rascunho sobrando e PDF por
#: anexar são controle interno: ficam no relatório, e não viram tarefa.
REGRAS_SEM_TAREFA = frozenset({"NOTAS_RASCUNHO", "NOTAS_PDF"})

#: «Onde abrir» de quem não tem ato próprio.
TELA = {
    "NOTAS_CENSEC": ("Notas → Remessas às Centrais", "/notas/remessas"),
    "NOTAS_LIVRO": ("Notas → Livros", "/notas/livros"),
}

#: regra → (por que existe, [passos]) — o texto didático da tarefa.
GUIA = {
    "NOTAS_ANOTACAO": (
        "Quando se lavra revogação, renúncia ou substabelecimento de procuração "
        "desta casa, o ato originário tem de ser anotado à margem IMEDIATAMENTE "
        "(Código de Normas TJMA, art. 831). Sem a anotação, a certidão da "
        "procuração sai como se ela valesse.",
        ["Abra o ato pelo «Onde abrir».",
         "Na ficha do ato ORIGINÁRIO, lance a anotação à margem (sem ônus e sem selo).",
         "Se o ato não diz qual procuração alcança, complete livro e folha do anterior."]),
    "NOTAS_IMOVEL": (
        "A escritura de imóvel tem de trazer no texto a consulta à CNIB com o "
        "código hash (Provimento CNJ 39/2014, art. 14), a certificação do imposto "
        "de transmissão (art. 798, § 3º) e a referência à DOI (art. 800, VII).",
        ["Leia o texto do ato e confirme o que falta.",
         "Ato já lavrado: a correção é por escritura de retificação/rerratificação, "
         "ou, se for erro material evidente da serventia, pela retificação do art. 795, § 8º.",
         "Leve ao oficial antes de qualquer traslado."]),
    "NOTAS_LIVRO": (
        "O livro tem de responder sozinho à correição: nenhuma folha com dois atos, "
        "nenhum termo repetido e numeração contínua (arts. 792 e 795, § 2º).",
        ["Confira no livro físico o que o item diz.",
         "Folha ou termo errado no sistema: corrija pela tela do livro (Notas → Livros).",
         "Diferença entre o contador e os atos: leve ao oficial — decidir qual número "
         "vale é dele."]),
    "NOTAS_CENSEC": (
        "Todo ato de Notas tem de ir à CENSEC na quinzena (art. 785; Provimento CNJ "
        "149/2023). Os itens abaixo estão lavrados e a carga os recusaria pelo motivo "
        "indicado — sem corrigir, a quinzena não fecha.",
        ["Abra cada ato e complete o que o detalhe diz (qualidade das partes, "
         "natureza da CENSEC, valor, tipo da CESDI…).",
         "Depois gere a carga em Notas → Remessas às Centrais e envie pelo portal.",
         "Registre o envio em Administrativo → Envios às Centrais."]),
    "NOTAS_MINUTA": (
        "Antes de lançar no livro, a conferência lista o que ainda falta na minuta — "
        "partes, texto, CNIB, imposto, DOI, testamento, advogado. É a revisão do "
        "agente das Notas (Código de Normas TJMA, art. 171, I): aponta onde olhar; "
        "quem qualifica e lavra é a escrevente.",
        ["Abra a minuta pelo «Onde abrir».",
         "Resolva cada ponto ou registre na anotação de lavratura por que ele não se aplica.",
         "Só então lance no livro."]),
}


# ------------------------------------------------------- o encaixe no gestor

def conferir(con: sqlite3.Connection, hoje: date) -> list[dict]:
    """Todas as regras das Notas — é o que a conferência do gestor chama.

    Regra que quebra vira NAO_MEDIU com o NOME DELA, e as outras seguem: um
    defeito na conta da CENSEC não pode calar a da anotação à margem. (A ponte
    do gestor também apanha, mas ali o erro levaria o nome do agente inteiro.)
    """
    con.row_factory = sqlite3.Row
    achados: list[dict] = []
    for nome, regra in REGRAS:
        try:
            achados.extend(regra(con, hoje))
        except Exception as erro:            # noqa: BLE001 — o erro vai à fila
            achados.append(GC._achado(
                f"NAO_MEDIU:{nome}", nome, "NAO_MEDIU", "TI",
                f"A conferência «{nome}» não conseguiu medir",
                f"{type(erro).__name__}: {erro}", None, ""))
    return achados


def registrar_na_didatica() -> None:
    """Põe o texto didático e as telas das Notas em `gestor_didatica`.

    Os rótulos e a lista do que não vira tarefa entram em `gestor_rotina`
    explicitamente (como os do agente de cargas do RI); isto aqui é só o texto
    da tarefa, que mora num dicionário de outro módulo.
    """
    try:
        import gestor_didatica as D
    except ImportError:
        return
    for k, v in GUIA.items():
        D.GUIA.setdefault(k, v)
    for k, v in TELA.items():
        D.TELA.setdefault(k, v)


# ------------------------------------------------------------- o relatório

def painel(con: sqlite3.Connection, hoje: date) -> dict:
    """Tudo o que o relatório das Notas mostra. Só lê."""
    con.row_factory = sqlite3.Row
    dados: dict = {"hoje": hoje, "pronto": _pronto(con)}
    if not dados["pronto"]:
        return dados
    dados["achados"] = conferir(con, hoje)
    dados["minutas"] = []
    for a in con.execute("""SELECT * FROM nt_atos WHERE situacao = 'EM_LAVRATURA'
                              ORDER BY data, id"""):
        dados["minutas"].append({"ato": a, "itens": revisar_minuta(con, a),
                                 "partes": len(_partes(con, a["id"]))})
    dados["livros"] = []
    if _tem_tabela(con, "nt_livros"):
        import notas_livro as NL
        for l in con.execute("""SELECT * FROM nt_livros WHERE COALESCE(ativo,1)=1
                                   AND COALESCE(encerrado,0)=0 ORDER BY tipo, id"""):
            ultimo = con.execute(
                """SELECT max(data) FROM nt_atos WHERE livro_id = ?""", (l["id"],)
            ).fetchone()[0]
            dados["livros"].append({"livro": l, "folha_livre": NL.folha_livre(con, l),
                                    "ultimo_ato": ultimo})
    dados["termos"] = list(con.execute("SELECT * FROM nt_termos ORDER BY serie")) \
        if _tem_tabela(con, "nt_termos") else []
    import notas_censec as NC
    dados["censec"] = []
    for (ano, mes, q) in _quinzenas(CORTE, hoje):
        linha = {"quinzena": f"{q}ª de {mes:02d}/{ano}"}
        for central in ("CEP", "CESDI", "RCTO"):
            sep = NC.separar(con, central, ano, mes, q)
            linha[central] = (len(sep["aptos"]), len(sep["impedidos"]))
            linha["prazo"] = sep["prazo"]
        enviada = con.execute(
            """SELECT count(*) FROM nt_remessas WHERE ano_referencia = ?
                  AND mes_referencia = ? AND quinzena = ?
                  AND situacao IN ('ENVIADA','CONFIRMADA')""", (ano, mes, q)
        ).fetchone()[0] if (_tem_tabela(con, "nt_remessas")
                            and "quinzena" in _colunas(con, "nt_remessas")) else 0
        linha["enviada"] = enviada
        dados["censec"].append(linha)
    inicio = (hoje - timedelta(days=30)).isoformat()
    dados["balcao"] = {
        "reconhecimentos": con.execute(
            "SELECT count(*) FROM nt_reconhecimentos WHERE data >= ? AND cancelado = 0",
            (inicio,)).fetchone()[0],
        "autenticacoes": con.execute(
            "SELECT count(*) FROM nt_autenticacoes WHERE data >= ? AND cancelado = 0",
            (inicio,)).fetchone()[0],
        "atos_lavrados": con.execute(
            "SELECT count(*) FROM nt_atos WHERE situacao = 'LAVRADO' AND data >= ?",
            (inicio,)).fetchone()[0],
    }
    return dados


_COR = {"CRITICO": "#b00020", "VENCIDO": "#b00020", "NAO_MEDIU": "#6a1b9a",
        "PRAZO": "#c45100", "ATENCAO": "#5f6368"}


def relatorio_html(con: sqlite3.Connection, hoje: date) -> str:
    """O painel do dia das Notas, numa página que se abre no navegador."""
    d = painel(con, hoje)
    e = html.escape
    out = ["<!doctype html><meta charset='utf-8'><title>Notas — "
           f"{hoje:%d/%m/%Y}</title>",
           "<style>body{font:14px/1.45 system-ui,Segoe UI,sans-serif;margin:24px;"
           "color:#1f1f1f;max-width:1100px}h1{font-size:22px}h2{font-size:17px;"
           "margin-top:28px;border-bottom:1px solid #ddd;padding-bottom:4px}"
           "table{border-collapse:collapse;width:100%}td,th{border:1px solid #e0e0e0;"
           "padding:5px 7px;text-align:left;vertical-align:top}th{background:#f6f6f6}"
           ".g{font-weight:600;font-size:12px}.m{color:#5f6368;font-size:12px}</style>",
           f"<h1>Tabelionato de Notas — painel do agente, {hoje:%d/%m/%Y}</h1>",
           "<p class='m'>Gerado pelo agente das Notas. Ele confere, revisa e prepara; "
           "não lança no livro, não sela, não cobra e não envia nada a Central "
           "(Código de Normas TJMA, arts. 169, IV e 171). Critérios em código, com o "
           "artigo ao lado (art. 176).</p>"]
    if not d["pronto"]:
        out.append("<p>Este banco não tem as tabelas das Notas.</p>")
        return "".join(out)

    out.append("<h2>O que a conferência achou</h2>")
    if not d["achados"]:
        out.append("<p>Nada a apontar.</p>")
    else:
        out.append("<table><tr><th>Gravidade</th><th>Item</th><th>O que fazer</th>"
                   "<th>Prazo</th><th>Fundamento</th></tr>")
        ordem = list(GC.GRAVIDADES)
        for a in sorted(d["achados"], key=lambda x: (ordem.index(x["gravidade"])
                                                     if x["gravidade"] in ordem else 9,
                                                     x["regra"], x["chave"])):
            sem = " <span class='m'>(só relatório)</span>" \
                if a["regra"] in REGRAS_SEM_TAREFA else ""
            out.append(
                f"<tr><td class='g' style='color:{_COR.get(a['gravidade'], '#333')}'>"
                f"{e(a['gravidade'])}</td><td><b>{e(ROTULOS.get(a['regra'], a['regra']))}"
                f"</b>{sem}<br>{e(a['titulo'])}</td><td>{e(a['detalhe'] or '')}</td>"
                f"<td>{e(a['prazo'] or '')}</td><td class='m'>{e(a['fundamento'] or '')}"
                "</td></tr>")
        out.append("</table>")

    out.append("<h2>Minutas em lavratura — a revisão</h2>")
    if not d["minutas"]:
        out.append("<p>Nenhum ato em lavratura.</p>")
    for m in d["minutas"]:
        a = m["ato"]
        out.append(f"<p><b>{e(_rotulo_ato(a))}</b> — {e(a['natureza'] or 'sem natureza')}"
                   f", aberta em {e(a['data'] or '?')} por {e(a['lavrado_nome'] or '?')}, "
                   f"{m['partes']} parte(s), texto com {len(a['teor'] or '')} caracteres.</p>")
        if m["itens"]:
            out.append("<ul>" + "".join(
                f"<li>{e(i['item'])} <span class='m'>— {e(i['fundamento'])}</span></li>"
                for i in m["itens"]) + "</ul>")
        else:
            out.append("<p class='m'>Nada objetivo a apontar.</p>")

    out.append("<h2>Livros abertos</h2><table><tr><th>Livro</th><th>Próxima folha"
               "</th><th>Capacidade</th><th>Último ato</th></tr>")
    for l in d["livros"]:
        lv = l["livro"]
        out.append(f"<tr><td>{e(lv['tipo'])} {e(str(lv['numero']))}</td>"
                   f"<td>{l['folha_livre']}</td><td>{e(str(lv['folhas'] or ''))}</td>"
                   f"<td>{e(l['ultimo_ato'] or '—')}</td></tr>")
    out.append("</table><table style='margin-top:8px'><tr><th>Série</th><th>Próximo "
               "termo</th><th>Maior em uso</th><th>Fixado</th></tr>")
    for t in d["termos"]:
        out.append(f"<tr><td>{e(t['serie'])}</td><td>{t['proximo']}</td>"
                   f"<td>{t['maior_em_uso'] or ''}</td><td class='m'>"
                   f"{e(t['fixado_em'] or '')} {e(t['fixado_por'] or '')}</td></tr>")
    out.append("</table>")

    out.append("<h2>CENSEC por quinzena</h2><table><tr><th>Quinzena</th><th>Prazo</th>"
               "<th>CEP (aptos/impedidos)</th><th>CESDI</th><th>RCTO</th>"
               "<th>Remessa registrada</th></tr>")
    for c in d["censec"]:
        out.append(f"<tr><td>{e(c['quinzena'])}</td><td>{e(c['prazo'])}</td>"
                   + "".join(f"<td>{c[x][0]} / {c[x][1]}</td>"
                             for x in ("CEP", "CESDI", "RCTO"))
                   + f"<td>{'sim' if c['enviada'] else 'não'}</td></tr>")
    out.append("</table><p class='m'>Quinzena sem ato e sem remessa: a CENSEC pede a "
               "declaração de que não houve ato — o gestor cobra pela regra «CENSEC».</p>")

    b = d["balcao"]
    out.append(f"<h2>Últimos 30 dias</h2><p>{b['atos_lavrados']} ato(s) de livro "
               f"lavrado(s), {b['reconhecimentos']} reconhecimento(s) de firma, "
               f"{b['autenticacoes']} autenticação(ões).</p>")
    return "".join(out)


def escrever_relatorio(con: sqlite3.Connection, hoje: date, pasta: Path) -> Path:
    """Grava `notas_AAAA-MM-DD.html` na pasta dos relatórios. Só lê o banco."""
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / f"notas_{hoje.isoformat()}.html"
    caminho.write_bytes(relatorio_html(con, hoje).encode("utf-8"))
    return caminho


def main(argv=None) -> int:
    """Roda o painel contra um banco (só leitura) — para conferir à mão."""
    import argparse
    import sys
    p = argparse.ArgumentParser(description="Painel do agente das Notas (só lê).")
    p.add_argument("--banco", required=True)
    p.add_argument("--hoje", default=date.today().isoformat())
    p.add_argument("--saida", required=True, help="pasta onde gravar o HTML")
    a = p.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:                                   # noqa: BLE001
        pass
    con = sqlite3.connect(f"file:{a.banco}?mode=ro", uri=True, timeout=60)
    con.row_factory = sqlite3.Row
    try:
        caminho = escrever_relatorio(con, _dia(a.hoje) or date.today(), Path(a.saida))
    finally:
        con.close()
    print(caminho)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
