"""OS LIVROS DO RCPJ E DO RTD — cada um com a sua aba, como a lei os nomeia.

    «Não temos aba do livro de protocolo, nem nos demais livros obrigatórios, nos
     termos da Lei 6015, código nacional de normas e código de normas do TJMA.»
                                                       — o oficial, 01/11/2026

O QUE A NORMA MANDA TER
    RCPJ: Livro A e Livro B (Lei 6.015/1973, art. 116), Livro de Protocolo com 300
    folhas (CN-MA art. 403) e índices cronológico e alfabético com as partes, os
    intervenientes e os cônjuges (CN-MA art. 404).

    RTD: Livro A, protocolo; Livro B, trasladação integral; Livro C, inscrição por
    extração; Livro D, indicador pessoal; Livro E, indicador real dos bens móveis;
    Livro F, registro facultativo para conservação; e Livro G, indicador dos
    apresentantes do Livro F (Lei 6.015/1973, art. 132, com a Lei 14.382/2022; CN-MA
    art. 963). O CN-MA lista só A a D: o E, o F e o G vêm da lei federal, e é por isso
    que cada aba cita a fonte dela.

O QUE ESTAVA AQUI ANTES
    Os lugares nos livros existiam (`livro_nucleo`, `nu_lugares`) e as telas mostravam
    título por situação e registro por atribuição. Livro nenhum se abria como livro:
    quem perguntasse «o que foi protocolado no dia 11?» não tinha onde olhar. E os
    indicadores não tinham de onde sair: o registro guardava só o requerente.

ESTE MÓDULO LÊ O QUE FOI LANÇADO, e o que ele escreve é cadastro em volta do registro
(as partes e os bens). Não lavra, não numera, não sela e não cobra: quem lavra continua
sendo `rg_registro`, pelas rotas de sempre. O livro é montado do que o ato gravou, e o
que o ato não guardou aparece como «não consta», como nos livros do Protesto.
"""
from __future__ import annotations

from typing import Any

import cpf_cnpj as DOC
import escrituracao as ESC
import livro_nucleo as LN
import rg_registro as RG
import rg_titulo as TIT
from bd_nativo import banco
from pt_schema import normalizar_nome

RCPJ, RTD = TIT.RCPJ, TIT.RTD

PROTOCOLO = "protocolo"
ATOS = "atos"
INDICE = "indice"
INDICADOR_REAL = "indicador_real"
INDICADOR_F = "indicador_f"
AUXILIAR = "auxiliar"

# OS PAPÉIS SUGERIDOS NA TELA. É sugestão (`datalist`), e não vocabulário fechado: a
# parte de um contrato de RTD pode ter qualquer nome que o contrato der a ela.
PAPEIS_SUGERIDOS = (
    "Requerente", "Representante legal", "Sócio", "Diretor", "Presidente", "Cônjuge",
    "Interveniente", "Contratante", "Contratado", "Credor", "Devedor", "Cedente",
    "Cessionário", "Locador", "Locatário", "Notificante", "Notificado", "Apresentante",
)
ESPECIES_DE_BEM = ("Veículo", "Máquina ou equipamento", "Semovente", "Embarcação", "Outro")

# Marca que o E-Ofício deixou no lugar do nome em linhas antigas (`tbRegistroTD`,
# medido em 01/11/2026). No indicador, seria uma «pessoa» chamada Apresentante.
NOMES_QUE_NAO_SAO_NOME = {"apresentante", "requerente", "nao informado"}

POR_PAGINA = 50
MINIMO_DO_MOTIVO = 10


class LivroDoRegistroError(ValueError):
    """Impedimento de regra, com mensagem pronta para a tela."""


def _livro(chave: str, curto: str, nome: str, fonte: str, tipo: str, explica: str,
           serie: str | None = None) -> dict:
    return {"chave": chave, "curto": curto, "nome": nome, "fonte": fonte, "tipo": tipo,
            "explica": explica, "serie": serie}


LIVROS: dict[int, tuple[dict, ...]] = {
    RCPJ: (
        _livro("protocolo", "Protocolo", "Livro de Protocolo do RCPJ",
               "CN-MA art. 403", PROTOCOLO,
               "Todos os títulos apresentados a registro ou averbação, na ordem de chegada.",
               serie="PJ_PROTOCOLO"),
        _livro("a", "Livro A", "Livro A — pessoas jurídicas",
               "Lei 6.015/1973, art. 116, I; CN-MA art. 402, I e II", ATOS,
               "Atos constitutivos, estatutos e contratos, e as averbações deles.",
               serie="PJ_A"),
        _livro("b", "Livro B", "Livro B — matrículas",
               "Lei 6.015/1973, art. 116, II; CN-MA art. 402, III", ATOS,
               "Matrícula de oficinas impressoras, jornais, periódicos, radiodifusão e "
               "agências de notícias.", serie="PJ_B"),
        _livro("indice", "Índices", "Índices cronológico e alfabético",
               "CN-MA art. 404", INDICE,
               "Todos os registros, averbações e arquivamentos, com as partes, os "
               "intervenientes e os cônjuges."),
    ),
    RTD: (
        _livro("a", "Livro A", "Livro A — Protocolo",
               "Lei 6.015/1973, art. 132, I; CN-MA arts. 963, I, e 966", PROTOCOLO,
               "Todos os títulos, documentos e papéis apresentados, diariamente.",
               serie="TD_PROTOCOLO"),
        _livro("b", "Livro B", "Livro B — Registro integral",
               "Lei 6.015/1973, art. 132, II; CN-MA art. 963, II", ATOS,
               "Trasladação integral de títulos e documentos.", serie="TD_B"),
        _livro("auxiliar", "Auxiliar do B", "Livro Auxiliar do Livro B",
               "CN-MA art. 964", AUXILIAR,
               "Facultativo, para quem não adota escrituração eletrônica: as cópias dos títulos "
               "registrados no Livro B, na numeração dele. Cada linha diz quantas cópias há."),
        _livro("c", "Livro C", "Livro C — Inscrição por extrato",
               "Lei 6.015/1973, art. 132, III; CN-MA arts. 963, III e § 4º, e 981", ATOS,
               "Inscrição por extração. O CN-MA dispensa este livro de quem adota sistema "
               "informatizado (art. 963, § 4º); ele fica aqui para quem o usar.",
               serie="TD_C"),
        _livro("d", "Livro D", "Livro D — Indicador Pessoal",
               "Lei 6.015/1973, art. 132, IV; CN-MA art. 963, IV e § 5º", INDICE,
               "Os nomes de todas as partes e dos cônjuges, com CPF ou CNPJ. É dele que "
               "sai a certidão pelo nome (art. 963, § 3º)."),
        _livro("e", "Livro E", "Livro E — Indicador Real dos bens móveis",
               "Lei 6.015/1973, art. 132, V", INDICADOR_REAL,
               "Os bens móveis que figuram nos livros, com a identificação, os números de "
               "ordem e os ônus."),
        _livro("f", "Livro F", "Livro F — Registro facultativo para conservação",
               "Lei 6.015/1973, arts. 127, VII, 127-A e 132, VI; CN-MA art. 957, §§ 4º e 5º",
               ATOS, "Só conserva e autentica data e conteúdo: não dá publicidade nem "
               "eficácia contra terceiros (art. 957, § 5º).", serie="TD_F"),
        _livro("g", "Livro G", "Livro G — Indicador dos apresentantes do Livro F",
               "Lei 6.015/1973, art. 132, VII", INDICADOR_F,
               "O número do registro, o nome e o CPF ou CNPJ de quem apresentou ao Livro F."),
    ),
}


def livros_de(atribuicao: int) -> tuple[dict, ...]:
    """As abas de uma atribuição. Só monta."""
    return LIVROS[int(atribuicao)]


def livro_pedido(atribuicao: int, chave: str | None) -> dict:
    """A aba pedida; chave que não existe abre a primeira, que é o Protocolo."""
    livros = livros_de(atribuicao)
    return next((x for x in livros if x["chave"] == str(chave or "")), livros[0])


def _texto(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _so_dia(v: Any) -> str:
    return _texto(v)[:10]


def _ate_o_fim(dia: str) -> str:
    # O `z` passa de qualquer hora gravada depois da data, nos dois formatos da casa
    # («2026-09-11T23:11:59» e «2026-09-11 23:11:59»), e a comparação segue de texto.
    return f"{dia}z" if dia else dia


def nome_de_serie(serie: str | None) -> str:
    try:
        return LN.serie(serie).nome if serie else ""
    except (KeyError, ValueError, LN.LivroError):
        return _texto(serie)


# ------------------------------------------------------------- o protocolo


def _lancamento_do_titulo(con, titulo: dict) -> str:
    """Onde o título foi lançado. CN-MA art. 968: «anotada no Protocolo a referência
    ao número de ordem sob o qual foi efetuado o registro ou a averbação». Só LÊ.

    Vem do que a máquina gravou: o registro aberto pelo título, e os atos que gastaram
    os itens do protocolo dele. Nada se deduz de nome ou de data.
    """
    bd = banco(con)
    partes: list[str] = []
    vistos: set[int] = set()
    if titulo.get("registro_id"):
        for a in bd.ler(
                """SELECT a.id, a.tipo, a.numero_ordem, a.rotulo, a.folha, r.serie
                     FROM rg_atos a JOIN rg_registros r ON r.id = a.registro_id
                    WHERE r.titulo_id = %s AND a.tipo = 'REGISTRO' ORDER BY a.id""",
                (int(titulo["id"]),)):
            vistos.add(int(a["id"]))
            partes.append(f"Registro n. {a['numero_ordem'] or '?'}, "
                          f"{nome_de_serie(a['serie'])}, fl. {a['rotulo'] or a['folha'] or '?'}")
    for a in TIT.atos_do_protocolo(con, int(titulo["id"])):
        if int(a["id"]) in vistos:
            continue
        rotulo = {"REGISTRO": "Registro", "AVERBACAO": "Averbação",
                  "CANCELAMENTO": "Cancelamento"}.get(a["tipo"], a["tipo"])
        partes.append(f"{rotulo} n. {a['numero_ordem'] or '?'} no registro n. "
                      f"{a['registro_numero'] or '?'}, {nome_de_serie(a['serie'])}")
    if not partes and titulo.get("registro_id"):
        linha = bd.um("SELECT numero, serie FROM rg_registros WHERE id=%s",
                      (int(titulo["registro_id"]),))
        if linha:
            partes.append(f"Registro n. {linha['numero'] or '?'}, "
                          f"{nome_de_serie(linha['serie'])}")
    return "; ".join(partes)


def motivo_da_pendencia(con, titulo: dict) -> str:
    """Por que o título ainda não saiu. CN-MA art. 970. Só LÊ."""
    situacao = titulo.get("situacao")
    aberto = TIT.sobrestamento_aberto(con, int(titulo["id"]))
    if aberto:
        return f"sobrestado: {TIT.SOBRESTAR_POR.get(aberto['tipo'], aberto['tipo'])}"
    if situacao == TIT.APRESENTADO:
        return "aguarda qualificação"
    if situacao == TIT.QUALIFICADO:
        return "qualificado, aguarda a lavratura"
    if situacao == TIT.EXIGENCIA:
        ultima = TIT.ultima_qualificacao(con, int(titulo["id"]))
        exigencia = _texto((ultima or {}).get("exigencias")).split("\n")[0][:120]
        return f"com exigência: {exigencia}" if exigencia else "com exigência"
    return ""


def linhas_do_protocolo(con, atribuicao: int, *, de: str = "", ate: str = "",
                        busca: str = "") -> list[dict]:
    """O Livro de Protocolo no período, com as colunas do CN-MA art. 966. Só LÊ.

    Número de ordem, data, natureza, espécie de lançamento, apresentante — e, do art.
    968, a referência ao lançamento. O mais recente em cima, como as listas da casa.
    """
    onde, param = ["atribuicao = %s"], [int(atribuicao)]
    if de:
        onde.append("data_apresentacao >= %s")
        param.append(de)
    if ate:
        onde.append("data_apresentacao <= %s")
        param.append(ate)
    procura = normalizar_nome(busca) if _texto(busca) else ""
    saida = []
    for t in banco(con).ler(
            f"""SELECT * FROM rg_titulos WHERE {' AND '.join(onde)}
                 ORDER BY data_apresentacao DESC, numero DESC, id DESC""", param):
        t = dict(t)
        if procura and procura not in (normalizar_nome(t.get("apresentante")) or "") \
                and procura not in (normalizar_nome(t.get("natureza")) or "") \
                and _texto(busca) != _texto(t.get("numero")):
            continue
        t["especie_rotulo"] = TIT.ESPECIES_DE_LANCAMENTO.get(_texto(t.get("especie_lancamento")), "")
        t["situacao_rotulo"] = TIT.SITUACOES.get(t["situacao"], t["situacao"]).split(" —")[0]
        t["lancamento"] = _lancamento_do_titulo(con, t)
        t["pendencia"] = motivo_da_pendencia(con, t)
        saida.append(t)
    return saida


def pendentes_ao_fim_do_dia(con, atribuicao: int, dia: str) -> list[dict]:
    """Os títulos apresentados até o dia que continuam sem lançamento. Só LÊ.

    CN-MA art. 970: o termo de encerramento diário relaciona, «pelos respectivos
    números de ordem, todos os títulos apresentados que permanecerem com o registro ou
    a averbação pendentes, acompanhados da indicação dos motivos do adiamento».
    """
    saida = []
    for t in banco(con).ler(
            """SELECT * FROM rg_titulos
                WHERE atribuicao = %s AND data_apresentacao <= %s
                  AND situacao NOT IN ('REGISTRADO','DEVOLVIDO','CANCELADO')
                ORDER BY numero, id""", (int(atribuicao), dia)):
        saida.append({"id": int(t["id"]), "numero": t["numero"],
                      "motivo": motivo_da_pendencia(con, dict(t))})
    return saida


def dias_sem_termo(con, serie: str | None) -> list[str]:
    """Os dias com movimento e sem termo de encerramento. Só LÊ."""
    return list(ESC.dias_sem_encerrar(con, serie)) if serie else []


def anotacao_no_titulo(titulo: dict) -> str:
    """O texto que se reproduz no título. CN-MA art. 966, §§ 1º e 2º. Só monta."""
    dia = _so_dia(titulo.get("data_apresentacao"))
    data = f"{dia[8:10]}/{dia[5:7]}/{dia[:4]}" if len(dia) == 10 else "../../...."
    fim = {"INTEGRAL": "registro integral", "EXTRATO": "registro por extrato",
           "AVERBACAO": "averbação"}.get(_texto(titulo.get("especie_lancamento")),
                                         "registro (ou averbação)")
    return f"Protocolizado em {data} sob n. {titulo.get('numero') or '____'}, para {fim}."


def frase_dos_pendentes(con, serie: str, dia: str) -> str:
    """A frase que o termo do dia leva. Vazia na série que não é de RCPJ ou RTD: o
    Protesto também encerra o dia, e lá a regra é outra. Só LÊ."""
    atribuicao = {"PJ_PROTOCOLO": RCPJ, "TD_PROTOCOLO": RTD}.get(serie)
    if atribuicao is None or not banco(con).tem_tabela("rg_titulos"):
        return ""
    pendentes = pendentes_ao_fim_do_dia(con, atribuicao, dia)
    if not pendentes:
        return "Não há título com registro ou averbação pendente."
    lista = "; ".join(f"n. {p['numero']} ({p['motivo']})" for p in pendentes)
    return f"Permanecem pendentes, com o motivo do adiamento: {lista}."


# ---------------------------------------------------------------- os livros


def atos_do_livro(con, serie: str, *, de: str = "", ate: str = "", busca: str = "",
                  pagina: int = 1) -> dict:
    """Os atos lançados numa série, com lugar, data e selo. Só LÊ.

    O acervo do E-Ofício entra junto: é o mesmo livro, e o volume de papel de cada
    linha está em `volume`.
    """
    onde, param = ["r.serie = %s"], [serie]
    if de:
        onde.append("a.data_ato >= %s")
        param.append(de)
    if ate:
        onde.append("a.data_ato <= %s")
        param.append(_ate_o_fim(ate))
    texto = _texto(busca)
    if texto:
        if texto.isdigit():
            onde.append("(a.numero_ordem = %s OR r.numero = %s)")
            param += [int(texto), int(texto)]
        else:
            onde.append("(r.requerente_nome ILIKE %s OR r.natureza ILIKE %s)")
            param += [f"%{texto}%", f"%{texto}%"]
    filtro = " AND ".join(onde)
    bd = banco(con)
    total = int(bd.valor(
        f"""SELECT COUNT(*) n FROM rg_atos a
              JOIN rg_registros r ON r.id = a.registro_id WHERE {filtro}""", param))
    pagina = max(1, int(pagina or 1))
    linhas = bd.ler(
        f"""SELECT a.id, a.tipo, a.data_ato, a.numero_ordem, a.rotulo, a.folha, a.selo,
                   a.origem, a.registro_id, r.numero AS registro_numero, r.volume,
                   r.requerente_nome, r.natureza, r.situacao
              FROM rg_atos a JOIN rg_registros r ON r.id = a.registro_id
             WHERE {filtro}
             ORDER BY a.id DESC LIMIT %s OFFSET %s""",
        param + [POR_PAGINA, (pagina - 1) * POR_PAGINA])
    return {"linhas": [dict(x) for x in linhas], "total": total, "pagina": pagina,
            "paginas": max(1, -(-total // POR_PAGINA))}


def _e_nome(nome: Any) -> bool:
    return bool(_texto(nome)) and (normalizar_nome(nome) or "") not in NOMES_QUE_NAO_SAO_NOME


def entradas_do_indicador(con, *, atribuicao: int | None = None,
                          series: tuple[str, ...] = ()) -> list[dict]:
    """Uma linha por pessoa em cada registro: as partes, e o requerente. Só LÊ.

    O REQUERENTE ENTRA SE NÃO ESTIVER ENTRE AS PARTES. Ele é o nome que o registro
    sempre guardou, e sem ele os registros que ninguém detalhou sumiriam do indicador —
    que é o que responde à certidão pelo nome.
    """
    onde, param = [], []
    if atribuicao is not None:
        onde.append("r.atribuicao = %s")
        param.append(int(atribuicao))
    if series:
        onde.append("r.serie = ANY(%s)")
        param.append(list(series))
    filtro = (" AND " + " AND ".join(onde)) if onde else ""
    bd = banco(con)
    registros = bd.ler(
        f"""SELECT r.id, r.atribuicao, r.serie, r.numero, r.volume, r.natureza, r.situacao,
                   r.requerente_nome, r.requerente_documento,
                   (SELECT MIN(a.data_ato) FROM rg_atos a WHERE a.registro_id = r.id) AS data_ato
              FROM rg_registros r WHERE 1=1{filtro} ORDER BY r.id""", param)
    partes: dict[int, list[dict]] = {}
    for p in bd.ler(
            f"""SELECT p.* FROM rg_partes p JOIN rg_registros r ON r.id = p.registro_id
                 WHERE p.retirada_em IS NULL{filtro} ORDER BY p.id""", param):
        partes.setdefault(int(p["registro_id"]), []).append(dict(p))
    saida = []
    for r in registros:
        comum = {"registro_id": int(r["id"]), "atribuicao": r["atribuicao"],
                 "serie": r["serie"], "numero": r["numero"], "volume": r["volume"],
                 "natureza": r["natureza"], "situacao": r["situacao"],
                 "data_ato": _so_dia(r["data_ato"])}
        doRegistro = partes.get(int(r["id"]), [])
        nomes = {p["nome_norm"] for p in doRegistro}
        for p in doRegistro:
            saida.append({**comum, "nome": p["nome"], "nome_norm": p["nome_norm"],
                          "documento": p["documento"] or "", "papel": p["papel"] or ""})
        if _e_nome(r["requerente_nome"]):
            norma = normalizar_nome(r["requerente_nome"]) or ""
            if norma not in nomes:
                saida.append({**comum, "nome": _texto(r["requerente_nome"]), "nome_norm": norma,
                              "documento": DOC.so_digitos(r["requerente_documento"]),
                              "papel": "Requerente"})
    return saida


def indicador_pessoal(con, *, atribuicao: int | None = None, series: tuple[str, ...] = (),
                      busca: str = "", ordem: str = "alfabetica") -> list[dict]:
    """O índice das pessoas. CN-MA arts. 404 e 963, IV. Só LÊ.

    Procura pelo nome, sem acento nem caixa, e pelo documento inteiro. Na ordem
    alfabética as linhas da mesma pessoa saem juntas; na cronológica, a mais nova em
    cima — o art. 404 pede as duas.
    """
    texto = _texto(busca)
    digitos = DOC.so_digitos(texto)
    procura = normalizar_nome(texto) if texto else ""
    linhas = []
    for e in entradas_do_indicador(con, atribuicao=atribuicao, series=series):
        if texto and not (procura in e["nome_norm"]
                          or (len(digitos) >= 11 and digitos == e["documento"])):
            continue
        e["documento_formatado"] = DOC.formatar_documento(e["documento"]) if e["documento"] else ""
        e["serie_nome"] = nome_de_serie(e["serie"])
        linhas.append(e)
    if ordem == "cronologica":
        linhas.sort(key=lambda x: (x["data_ato"], x["registro_id"]), reverse=True)
    else:
        linhas.sort(key=lambda x: (x["nome_norm"], x["data_ato"]))
    return linhas


def indicador_real(con, *, busca: str = "") -> list[dict]:
    """Os bens móveis do Livro E, com o número de ordem de cada lançamento. Só LÊ."""
    texto = _texto(busca)
    procura = normalizar_nome(texto) if texto else ""
    saida = []
    for b in banco(con).ler(
            """SELECT b.*, r.serie, r.numero, r.volume, r.situacao AS registro_situacao
                 FROM rg_bens b JOIN rg_registros r ON r.id = b.registro_id
                WHERE r.atribuicao = %s ORDER BY b.identificacao, b.id""", (RTD,)):
        b = dict(b)
        if procura and procura not in (normalizar_nome(b["descricao"]) or "") \
                and procura not in (normalizar_nome(b.get("identificacao")) or ""):
            continue
        b["serie_nome"] = nome_de_serie(b["serie"])
        saida.append(b)
    return saida


def copias_do_livro_b(con, *, busca: str = "", pagina: int = 1) -> dict:
    """O Livro B, com as cópias anexadas a cada ato. CN-MA art. 964. Só LÊ."""
    pedido = atos_do_livro(con, "TD_B", busca=busca, pagina=pagina)
    ids = [int(x["id"]) for x in pedido["linhas"]]
    contas = {}
    if ids:
        contas = {int(r["entity_id"]): int(r["n"]) for r in banco(con).ler(
            """SELECT entity_id, COUNT(*) n FROM attachments
                WHERE entity_type = 'RG_ATO' AND entity_id = ANY(%s) GROUP BY entity_id""", (ids,))}
    for x in pedido["linhas"]:
        x["copias"] = contas.get(int(x["id"]), 0)
    return pedido


def quantos_no_livro(con, livro: dict, atribuicao: int) -> int | None:
    """O número ao lado da aba: quantos lançamentos há. Só LÊ."""
    bd = banco(con)
    if livro["tipo"] == PROTOCOLO:
        return int(bd.valor("SELECT COUNT(*) n FROM rg_titulos WHERE atribuicao=%s",
                            (int(atribuicao),)))
    if livro["tipo"] == ATOS:
        return int(bd.valor(
            """SELECT COUNT(*) n FROM rg_atos a JOIN rg_registros r ON r.id=a.registro_id
                WHERE r.serie=%s""", (livro["serie"],)))
    if livro["tipo"] == INDICADOR_REAL:
        return int(bd.valor("SELECT COUNT(*) n FROM rg_bens WHERE baixado_em IS NULL"))
    return None


def lugar_do_livro(con, serie: str | None) -> dict | None:
    """O livro aberto daquela série, para a aba dizer onde o próximo ato cai. Só LÊ."""
    if not serie:
        return None
    linha = banco(con).um(
        """SELECT id, numero, folha_atual, folhas, dia FROM nu_livros
            WHERE serie=%s AND COALESCE(encerrado,0)=0 ORDER BY id DESC LIMIT 1""", (serie,))
    return dict(linha) if linha else None


# ----------------------------------------------------- as partes e os bens


def partes_do_registro(con, registro_id: int) -> list[dict]:
    """As partes do registro, com as retiradas no fim. Só LÊ."""
    return [dict(x) for x in banco(con).ler(
        """SELECT * FROM rg_partes WHERE registro_id=%s
            ORDER BY (retirada_em IS NOT NULL), id""", (int(registro_id),))]


def bens_do_registro(con, registro_id: int) -> list[dict]:
    """Os bens móveis do registro. Só LÊ."""
    return [dict(x) for x in banco(con).ler(
        """SELECT * FROM rg_bens WHERE registro_id=%s
            ORDER BY (baixado_em IS NOT NULL), id""", (int(registro_id),))]


def _registro_ou_recusa(con, registro_id: int) -> dict:
    registro = RG.registro(con, int(registro_id))
    if not registro:
        raise LivroDoRegistroError(f"Registro {registro_id} não encontrado.")
    return registro


def incluir_parte(con, registro_id: int, *, nome: str, documento: str | None = None,
                  papel: str | None = None, participacao: str | None = None,
                  doi_lado: str | None = None, agora: str, usuario: str | None = None,
                  origem: str = "MANUAL", origem_chave: str | None = None) -> dict:
    """Põe uma pessoa no indicador daquele registro. ESCREVE.

    **NÃO É ATO E NÃO MUDA TEOR.** É o cadastro em volta do registro, como o requerente:
    o teor continua sendo o que o livro diz, e quem lê o título é quem diz quem são as
    partes. Documento que não fecha o dígito é recusado aqui, com o cliente na frente: é
    por ele que o indicador acha a pessoa sem homônimo.
    """
    _registro_ou_recusa(con, registro_id)
    limpo = _texto(nome)
    if not limpo:
        raise LivroDoRegistroError("Informe o nome da parte.")
    digitos = DOC.so_digitos(documento)
    if digitos and DOC.documento_valido(digitos) is False:
        raise LivroDoRegistroError(DOC.mensagem_documento_invalido(digitos))
    bd = banco(con)
    norma = normalizar_nome(limpo) or ""
    ja = bd.um(
        """SELECT id FROM rg_partes WHERE registro_id=%s AND nome_norm=%s
              AND COALESCE(papel,'')=%s AND retirada_em IS NULL""",
        (int(registro_id), norma, _texto(papel)))
    if ja:
        raise LivroDoRegistroError(
            f"{limpo} já está neste registro com o papel «{_texto(papel) or 'sem papel'}».")
    linha = bd.escrever(
        """INSERT INTO rg_partes(registro_id, nome, nome_norm, documento, papel, participacao,
               doi_lado, origem, origem_chave, criado_em, criado_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (int(registro_id), limpo, norma, digitos or None, _texto(papel) or None,
         _texto(participacao).replace(",", ".") or None, _texto(doi_lado).upper() or None, origem,
         origem_chave, agora, usuario))
    return {"parte_id": int(linha[0]["id"]), "registro_id": int(registro_id), "nome": limpo}


def retirar_parte(con, registro_id: int, parte_id: int, *, motivo: str, agora: str,
                  usuario: str | None = None) -> dict:
    """Tira a pessoa do indicador, com o motivo escrito. ESCREVE. A linha fica."""
    razao = _texto(motivo)
    if len(razao) < MINIMO_DO_MOTIVO:
        raise LivroDoRegistroError("Escreva o motivo com pelo menos dez letras.")
    bd = banco(con)
    parte = bd.um("SELECT * FROM rg_partes WHERE id=%s AND registro_id=%s",
                  (int(parte_id), int(registro_id)))
    if not parte:
        raise LivroDoRegistroError("Esta parte não é deste registro.")
    if parte["retirada_em"]:
        raise LivroDoRegistroError("Esta parte já foi retirada.")
    bd.escrever(
        "UPDATE rg_partes SET retirada_em=%s, retirada_por=%s, retirada_motivo=%s WHERE id=%s",
        (agora, usuario, razao, int(parte_id)))
    return {"parte_id": int(parte_id), "nome": parte["nome"], "motivo": razao}


def incluir_bem(con, registro_id: int, *, descricao: str, identificacao: str | None = None,
                especie: str | None = None, onus: str | None = None, agora: str,
                usuario: str | None = None) -> dict:
    """Lança um bem móvel no Livro E. ESCREVE. Só o RTD tem esse livro."""
    registro = _registro_ou_recusa(con, registro_id)
    if int(registro["atribuicao"]) != RTD:
        raise LivroDoRegistroError(
            "O Livro E é do Registro de Títulos e Documentos; este registro é do RCPJ.")
    texto = _texto(descricao)
    if not texto:
        raise LivroDoRegistroError("Descreva o bem: o que é, marca, modelo.")
    linha = banco(con).escrever(
        """INSERT INTO rg_bens(registro_id, especie, descricao, identificacao, onus,
               criado_em, criado_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (int(registro_id), _texto(especie) or None, texto, _texto(identificacao) or None,
         _texto(onus) or None, agora, usuario))
    return {"bem_id": int(linha[0]["id"]), "registro_id": int(registro_id)}


def baixar_bem(con, registro_id: int, bem_id: int, *, motivo: str, agora: str,
               usuario: str | None = None) -> dict:
    """Dá baixa no bem, com o motivo escrito. ESCREVE. A linha fica no Livro E."""
    razao = _texto(motivo)
    if len(razao) < MINIMO_DO_MOTIVO:
        raise LivroDoRegistroError("Escreva o motivo com pelo menos dez letras.")
    bd = banco(con)
    bem = bd.um("SELECT * FROM rg_bens WHERE id=%s AND registro_id=%s",
                (int(bem_id), int(registro_id)))
    if not bem:
        raise LivroDoRegistroError("Este bem não é deste registro.")
    if bem["baixado_em"]:
        raise LivroDoRegistroError("Este bem já teve baixa.")
    bd.escrever("UPDATE rg_bens SET baixado_em=%s, baixado_por=%s, baixa_motivo=%s WHERE id=%s",
                (agora, usuario, razao, int(bem_id)))
    return {"bem_id": int(bem_id), "motivo": razao}
