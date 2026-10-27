"""Os termos de encerramento diário do mês, num PDF só, para o delegatário assinar.

    «junta tudo para assinar no final do mês, ainda que tenha encerramento
     diário; assinatura num PDF único assinado digitalmente» — o oficial,
     23/10/2026, sobre os Livros de Protocolo do RCPJ e do RTD

O ENCERRAMENTO DIÁRIO CONTINUA MANUAL, TODO DIA
    Decisão do oficial no mesmo dia: o termo de cada dia nasce no dia, pela
    tela de sempre (`escrituracao.encerrar_o_dia`), com quem encerrou e quando
    — inclusive o dia sem movimento. Este módulo **não escreve termo nenhum, e
    não encerra dia em lote**: junta os que já existem, na ordem do livro, e
    põe o conjunto na fila de assinatura da casa (`as_documentos`). Encerrar o
    mês inteiro de uma vez, no fim dele, seria exatamente o que a rotina
    diária existe para evitar.

O MÊS SÓ SE JUNTA INTEIRO
    O PDF afirma que aqueles são os termos do mês. Com um dia útil sem termo
    ele afirmaria um livro sem buraco que tem buraco — e é o buraco que a
    correição procura. Por isso `gerar` recusa enquanto houver dia útil (ou dia
    com movimento) sem encerramento, e diz quais.

DEPOIS DE ASSINADO, O MÊS FECHA
    Encerrar mais um dia daquele mês depois da assinatura faria existir um
    termo que o delegatário não assinou ao lado dos que assinou. Quem recusa é
    `escrituracao.encerrar_o_dia`, que pergunta a `mes_assinado`.

QUAIS LIVROS
    Os protocolos do RCPJ e do RTD, que foi o que o oficial pediu. A
    configuração `encerramento_mensal_series` muda a lista (o Protesto também é
    livro diário); série que não for diária é recusada.

O QUE ELE NÃO FAZ
    Não assina. Quem assina é o A3 do delegatário, fora do processo, pelo
    serviço local (`assinar_com_a3`) — o mesmo caminho do instrumento de
    protesto. Aqui só se confere que o PDF de dentro do pacote assinado é,
    byte a byte, o que a casa gerou.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from typing import Any, Callable

import livro_nucleo as LN
from bd_nativo import banco

ENTIDADE = "nu_encerramentos_mensais"
CHAVE_DAS_SERIES = "encerramento_mensal_series"
SERIES_PADRAO = ("PJ_PROTOCOLO", "TD_PROTOCOLO")

MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro")


class EncerramentoMensalError(ValueError):
    """Erro de regra, com mensagem pronta para o balcão."""


# ------------------------------------------------------------ o mês e os dias


def competencia(texto: Any) -> tuple[int, int]:
    """«2026-10» → (2026, 10). Recusa o que não for mês."""
    t = str(texto or "").strip()[:7]
    try:
        ano, mes = int(t[:4]), int(t[5:7])
        if t[4] != "-" or not 1 <= mes <= 12 or ano < 2000:
            raise ValueError
    except (ValueError, IndexError):
        raise EncerramentoMensalError(
            f"«{texto}» não é um mês. Use o formato AAAA-MM.") from None
    return ano, mes


def nome_do_mes(comp: str) -> str:
    ano, mes = competencia(comp)
    return f"{MESES[mes - 1]} de {ano}"


def dias_do_mes(comp: str) -> list[date]:
    ano, mes = competencia(comp)
    dia = date(ano, mes, 1)
    saida = []
    while dia.month == mes:
        saida.append(dia)
        dia += timedelta(days=1)
    return saida


def mes_anterior(hoje: str) -> str:
    """O mês que acabou: é o que a tela oferece para juntar."""
    primeiro = date.fromisoformat(str(hoje)[:8] + "01")
    return (primeiro - timedelta(days=1)).isoformat()[:7]


def series(get_setting: Callable[[str, str], Any] | None = None) -> tuple[str, ...]:
    """Os livros que o PDF do mês junta. A configuração muda a lista.

    **SÉRIE QUE NÃO É DIÁRIA É RECUSADA**, e não ignorada: encerramento do dia
    só existe em livro diário, e um código digitado errado deixaria o livro
    pedido de fora do PDF sem ninguém saber.
    """
    bruto = ""
    if get_setting is not None:
        bruto = str(get_setting(CHAVE_DAS_SERIES, "") or "").strip()
    codigos = tuple(c.strip().upper() for c in bruto.replace(";", ",").split(",")
                    if c.strip()) or SERIES_PADRAO
    for c in codigos:
        if c not in LN.SERIES:
            raise EncerramentoMensalError(
                f"A configuração «{CHAVE_DAS_SERIES}» cita a série «{c}», que "
                f"não existe.")
        if not LN.SERIES[c].diario:
            raise EncerramentoMensalError(
                f"A configuração «{CHAVE_DAS_SERIES}» cita «{LN.SERIES[c].nome}», "
                f"que não é livro diário — ele não tem encerramento do dia.")
    return codigos


# ---------------------------------------------------------------- o que falta


def pendencias(con: Any, comp: str, *, series_do_mes: tuple[str, ...],
               e_dia_util: Callable[[date], bool], hoje: str) -> list[dict]:
    """Os dias do mês que ainda não têm termo de encerramento. SÓ LÊ.

    São dois motivos, e os dois entram: o **dia útil** sem termo (o livro
    diário se encerra todo dia, com ou sem movimento) e o **dia com
    movimento** sem termo, mesmo fora do dia útil — protocolo lançado num
    sábado também tem de estar encerrado. Hoje e o que ainda não chegou não
    contam: o dia de hoje se encerra no fim dele.
    """
    bd = banco(con)
    ultimo = str(hoje)[:10]
    inicio, fim = f"{comp}-01", f"{comp}-31"
    saida = []
    for codigo in series_do_mes:
        feitos = {r["dia"] for r in bd.ler(
            """SELECT dia FROM nu_encerramentos_diarios
                WHERE serie=%s AND dia BETWEEN %s AND %s""",
            (codigo, inicio, fim))}
        com_movimento = {r["dia"] for r in bd.ler(
            """SELECT DISTINCT dia FROM nu_livros
                WHERE serie=%s AND dia BETWEEN %s AND %s""",
            (codigo, inicio, fim))}
        nome = LN.SERIES[codigo].nome
        for d in dias_do_mes(comp):
            iso = d.isoformat()
            if iso >= ultimo or iso in feitos:
                continue
            if iso in com_movimento:
                saida.append({"serie": codigo, "nome": nome, "dia": iso,
                              "motivo": "dia com protocolo e sem termo"})
            elif e_dia_util(d):
                saida.append({"serie": codigo, "nome": nome, "dia": iso,
                              "motivo": "dia útil sem termo"})
    return saida


def termos(con: Any, comp: str, series_do_mes: tuple[str, ...]) -> list[dict]:
    """Os termos diários do mês, livro a livro e dia a dia. SÓ LÊ."""
    bd = banco(con)
    saida = []
    for codigo in series_do_mes:
        saida.extend(bd.ler(
            """SELECT id, serie, dia, quantidade, primeiro, ultimo, teor,
                      encerrado_em, encerrado_por
                 FROM nu_encerramentos_diarios
                WHERE serie=%s AND dia BETWEEN %s AND %s
                ORDER BY dia, id""",
            (codigo, f"{comp}-01", f"{comp}-31")))
    return saida


# ------------------------------------------------------------------- o papel


def _esc(texto: Any) -> str:
    return (str(texto if texto is not None else "").replace("&", "&amp;")
            .replace("<", "&lt;").replace(">", "&gt;"))


def montar_html(comp: str, lista: list[dict], series_do_mes: tuple[str, ...],
                sv: dict) -> str:
    """O papel do mês: cabeçalho da serventia, um bloco por livro, cada termo
    diário como foi escrito, e o fecho para a assinatura digital.

    O TEOR DE CADA DIA VAI COMO ESTÁ GRAVADO. Reescrever aqui faria o PDF
    assinado dizer coisa diferente do que o sistema guardou no dia.
    """
    partes = [
        f'<p align="center"><b>{_esc(sv.get("unit_name"))}</b></p>',
        f'<p align="center">{_esc(sv.get("serventia_titulo"))}: '
        f'{_esc(sv.get("serventia_titular"))}</p>',
        f'<p align="center">CNS {_esc(sv.get("ri_cns"))} — '
        f'{_esc(sv.get("endereco_completo"))}</p>',
        "<p></p>",
        f'<p align="center"><b>TERMOS DE ENCERRAMENTO DIÁRIO — '
        f'{_esc(nome_do_mes(comp).upper())}</b></p>',
        "<p></p>",
    ]
    for codigo in series_do_mes:
        do_livro = [t for t in lista if t["serie"] == codigo]
        partes.append(f"<p><b>{_esc(LN.SERIES[codigo].nome)}</b> — "
                      f"{len(do_livro)} termo(s)</p>")
        if not do_livro:
            partes.append("<p>Nenhum termo neste mês.</p>")
        for t in do_livro:
            partes.append(
                f"<p>{_esc(t['teor'])} <i>(encerrado em "
                f"{_esc(str(t['encerrado_em'])[:16])} por "
                f"{_esc(t['encerrado_por'] or 'usuário não gravado')})</i></p>")
        partes.append("<p></p>")
    partes += [
        f"<p>Reúno neste documento os {len(lista)} termo(s) de encerramento "
        f"diário acima, lavrados no sistema nos dias a que se referem, e os "
        f"assino digitalmente.</p>",
        "<p></p>",
        f'<p align="center">{_esc(sv.get("serventia_titular"))}</p>',
        f'<p align="center">{_esc(sv.get("serventia_titulo"))}</p>',
        '<p align="center">Documento assinado digitalmente com certificado '
        'ICP-Brasil.</p>',
    ]
    return "".join(partes)


def _impressao(comp: str, lista: list[dict], html: str) -> str:
    """O sha256 do que vai ser assinado: os termos (id e teor) e o papel."""
    corpo = json.dumps([[t["id"], t["teor"]] for t in lista],
                       ensure_ascii=False)
    return hashlib.sha256(f"{comp}\n{corpo}\n{html}".encode("utf-8")).hexdigest()


def _ids(lista: list[dict]) -> str:
    return json.dumps([int(t["id"]) for t in lista])


# -------------------------------------------------------------- gerar e ler


def mensal(con: Any, comp_ou_id: Any) -> dict | None:
    """O mês juntado, com a situação da assinatura. SÓ LÊ."""
    bd = banco(con)
    if isinstance(comp_ou_id, int):
        linha = bd.um(f"SELECT * FROM {ENTIDADE} WHERE id=%s", (comp_ou_id,))
    else:
        linha = bd.um(f"SELECT * FROM {ENTIDADE} WHERE competencia=%s",
                      (str(comp_ou_id)[:7],))
    if not linha:
        return None
    d = dict(linha)
    doc = None
    if bd.tem_tabela("as_documentos"):
        doc = bd.um("""SELECT assinado_em, assinado_por_nome, caminho_documento,
                              caminho_assinado
                         FROM as_documentos WHERE entidade=%s AND entidade_id=%s""",
                    (ENTIDADE, int(d["id"])))
    doc = dict(doc) if doc else {}
    d["assinado_em"] = doc.get("assinado_em")
    d["assinado_por"] = doc.get("assinado_por_nome")
    d["caminho_documento"] = doc.get("caminho_documento")
    d["caminho_assinado"] = doc.get("caminho_assinado")
    d["series_lista"] = tuple(s for s in (d.get("series") or "").split(",") if s)
    d["nome_do_mes"] = nome_do_mes(d["competencia"])
    return d


def lista_de_meses(con: Any, limite: int = 24) -> list[dict]:
    """Os meses já juntados, do mais novo. SÓ LÊ."""
    bd = banco(con)
    return [mensal(bd, int(r["id"])) for r in bd.ler(
        f"SELECT id FROM {ENTIDADE} ORDER BY competencia DESC LIMIT %s",
        (int(limite),))]


def mes_assinado(con: Any, serie: str, dia: str) -> str | None:
    """A competência, se o mês daquele dia já foi assinado para aquela série.

    É a pergunta de `escrituracao.encerrar_o_dia` antes de encerrar: depois da
    assinatura, o mês não recebe mais termo. SÓ LÊ.
    """
    bd = banco(con)
    if not (bd.tem_tabela(ENTIDADE) and bd.tem_tabela("as_documentos")):
        return None
    linha = bd.um(
        f"""SELECT m.competencia, m.series FROM {ENTIDADE} m
              JOIN as_documentos d ON d.entidade=%s AND d.entidade_id=m.id
             WHERE m.competencia=%s AND d.assinado_em IS NOT NULL""",
        (ENTIDADE, str(dia)[:7]))
    if linha and serie in (linha["series"] or "").split(","):
        return linha["competencia"]
    return None


def gerar(con: Any, comp: str, *, series_do_mes: tuple[str, ...],
          e_dia_util: Callable[[date], bool], hoje: str, sv: dict, agora: str,
          usuario: str | None = None) -> dict:
    """Junta os termos do mês e põe o conjunto na fila de assinatura. ESCREVE.

    Só mês que já terminou, inteiro, e ainda não assinado. Juntar de novo um
    mês que espera assinatura refaz o papel: é o caso de um termo esquecido
    que foi lavrado depois.
    """
    competencia(comp)
    comp = str(comp)[:7]
    if comp >= str(hoje)[:7]:
        raise EncerramentoMensalError(
            f"O mês de {nome_do_mes(comp)} ainda não terminou. Os termos do mês "
            f"se juntam a partir do primeiro dia do mês seguinte.")
    falta = pendencias(con, comp, series_do_mes=series_do_mes,
                       e_dia_util=e_dia_util, hoje=hoje)
    if falta:
        amostra = ", ".join(f"{p['dia']} ({p['nome']})" for p in falta[:6])
        mais = f" e mais {len(falta) - 6}" if len(falta) > 6 else ""
        raise EncerramentoMensalError(
            f"Faltam {len(falta)} encerramento(s) diário(s) em "
            f"{nome_do_mes(comp)}: {amostra}{mais}. Encerre esses dias antes de "
            f"juntar o mês — o PDF afirma que o livro não tem buraco.")
    lista = termos(con, comp, series_do_mes)
    if not lista:
        raise EncerramentoMensalError(
            f"Não há termo de encerramento diário em {nome_do_mes(comp)}.")
    bd = banco(con)
    ja = mensal(bd, comp)
    if ja and ja.get("assinado_em"):
        raise EncerramentoMensalError(
            f"O mês de {nome_do_mes(comp)} já foi assinado em "
            f"{ja['assinado_em']}. Ele não se refaz.")
    html = montar_html(comp, lista, series_do_mes, sv)
    impressao = _impressao(comp, lista, html)
    texto_series = ",".join(series_do_mes)
    titulo = f"Termos de encerramento diário — {nome_do_mes(comp)}"
    if ja:
        mensal_id = int(ja["id"])
        bd.escrever(
            f"""UPDATE {ENTIDADE} SET series=%s, termos_json=%s, quantidade=%s,
                      html=%s, sha256=%s, gerado_em=%s, gerado_por=%s
                WHERE id=%s""",
            (texto_series, _ids(lista), len(lista), html, impressao, agora,
             usuario, mensal_id))
        bd.escrever(
            """UPDATE as_documentos SET titulo=%s, sha256_documento=%s,
                      criado_em=%s, criado_por=%s
                WHERE entidade=%s AND entidade_id=%s""",
            (titulo, impressao, agora, usuario, ENTIDADE, mensal_id))
    else:
        mensal_id = int(bd.escrever(
            f"""INSERT INTO {ENTIDADE}(competencia, series, termos_json,
                      quantidade, html, sha256, gerado_em, gerado_por)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (comp, texto_series, _ids(lista), len(lista), html, impressao,
             agora, usuario))[0]["id"])
        bd.escrever(
            """INSERT INTO as_documentos(entidade, entidade_id, titulo,
                      sha256_documento, criado_em, criado_por)
               VALUES (%s,%s,%s,%s,%s,%s)""",
            (ENTIDADE, mensal_id, titulo, impressao, agora, usuario))
    return {"id": mensal_id, "competencia": comp, "quantidade": len(lista),
            "sha256": impressao, "refeito": bool(ja)}


def conferir_antes_de_assinar(con: Any, mensal_id: int) -> dict:
    """O mês como está agora tem de ser o mês que foi juntado. SÓ LÊ.

    Entre juntar e assinar pode ter entrado um termo daquele mês; assinar o
    papel antigo deixaria esse termo fora do que o delegatário assinou.
    """
    bd = banco(con)
    m = mensal(bd, int(mensal_id))
    if not m:
        raise EncerramentoMensalError("Mês não encontrado.")
    if m.get("assinado_em"):
        raise EncerramentoMensalError(
            f"O mês de {m['nome_do_mes']} já está assinado.")
    if _ids(termos(bd, m["competencia"], m["series_lista"])) != m["termos_json"]:
        raise EncerramentoMensalError(
            f"Os termos de {m['nome_do_mes']} mudaram depois que o mês foi "
            f"juntado. Junte o mês de novo antes de assinar.")
    return m


def guardar_assinatura(con: Any, mensal_id: int, *, pdf: bytes, p7s: bytes,
                       pasta_de_arquivos: Any, agora: str,
                       usuario: str | None = None) -> dict:
    """Guarda o PDF do mês e o pacote assinado. ESCREVE, e grava os arquivos.

    **CONFERE ANTES DE GUARDAR**: o PDF de dentro do pacote tem de ser, byte a
    byte, o PDF que a casa acabou de gerar. É a régua do instrumento de
    protesto (`protesto_instrumento.guardar_assinatura`).
    """
    from pathlib import Path

    import assinatura_digital as ASD
    bd = banco(con)
    m = conferir_antes_de_assinar(bd, mensal_id)
    resultado = ASD.conferir(bytes(p7s), documento=bytes(pdf))
    if not resultado.get("serve"):
        raise EncerramentoMensalError(
            "A assinatura não confere com o PDF do mês: "
            + (ASD.por_que_nao_serve(resultado) or "motivo não identificado")
            + ". Nada foi guardado.")
    quem = resultado.get("quem_assinou") or {}
    destino = Path(pasta_de_arquivos) / "Livros" / "Encerramentos mensais"
    destino.mkdir(parents=True, exist_ok=True)
    base = destino / f"encerramentos-diarios-{m['competencia']}"
    base.with_suffix(".pdf").write_bytes(bytes(pdf))
    base.with_suffix(".p7s").write_bytes(bytes(p7s))
    bd.escrever(
        """UPDATE as_documentos
              SET caminho_documento=%s, tamanho_documento=%s,
                  caminho_assinado=%s, sha256_assinado=%s, assinado_em=%s,
                  assinado_por_nome=%s, assinado_por_cpf=%s, recebido_por=%s
            WHERE entidade=%s AND entidade_id=%s""",
        (str(base.with_suffix(".pdf")), len(pdf), str(base.with_suffix(".p7s")),
         hashlib.sha256(bytes(p7s)).hexdigest(), agora, quem.get("nome"),
         quem.get("cpf"), usuario, ENTIDADE, int(mensal_id)))
    if not bd.linhas_afetadas:
        raise EncerramentoMensalError(
            "Este mês não está na fila de assinatura da casa — junte-o de novo.")
    return {"id": int(mensal_id), "competencia": m["competencia"],
            "assinado_por": quem.get("nome")}
