"""
Expurgo de ato de Registro de Imoveis lavrado em teste.

POR QUE ISTO EXISTE, E POR QUE NAO E O "CANCELAR"
    O sistema ja tem cancelamento de ato, e ele esta certo para o que se
    propoe: em registro publico nao se apaga assento, e o cancelamento e ele
    proprio um ato, com numero, data e teor. Aquele caminho serve para o ato
    que FOI praticado e depois se desconstitui.

    Este caminho serve para outra coisa. Em 18/08/2026 a serventia lavrou os
    primeiros atos no sistema novo, ainda em teste, e um deles nao devia ter
    existido. O selo foi cancelado no tribunal — ou seja, para o Estado aquele
    ato nao ocorreu. Lavrar uma averbacao de cancelamento seria escrever na
    ficha, para sempre, que houve um ato onde nao houve: a averbacao afirmaria
    um fato falso, e ainda sairia riscada em toda certidao de inteiro teor
    daquela matricula, pelos proximos cinquenta anos.

    Entao o expurgo remove. E, porque remover assento e grave, ele so remove
    com trava, com motivo e com ATA DE OCORRENCIA: um texto que fica gravado no
    banco dizendo o que saiu, de onde, quando, por ordem de quem, com que
    fundamento e com que selo cancelado no tribunal. O ato sai da ficha e passa
    a existir na ata — que e onde ele deve existir, porque foi um evento de
    implantacao de sistema, nao um ato de registro.

AS TRAVAS, E POR QUE CADA UMA
    1. So ato de origem MANUAL. Ato do acervo do E-Oficio nao se expurga: ele
       nao foi lavrado aqui, e apagar o que veio de fora e perder historia sem
       ter como recuperar.
    2. So o ULTIMO ato da matricula. O hash de cada ato inclui o hash do
       anterior; tirar um ato do meio quebraria a conferencia de todos os
       posteriores em silencio. Querendo tirar dois, tira-se de tras para a
       frente, um por vez, e cada um gera a sua ata.
    3. Ato nao cancelado, e que nao cancelou outro. Ato que cancelou outro
       deixaria o cancelado apontando para o vazio.
    4. Nenhuma certidao NAO CANCELADA pode citar o ato. Certidao expedida
       congela o teor e circula no mundo: se ela afirma o ato, o ato nao pode
       simplesmente desaparecer da ficha — ou se cancela a certidao primeiro,
       ou nao se expurga.
    5. Nenhuma remessa FECHADA da CTP nem ENTREGUE da DOI pode conter o ato.
       O que foi transmitido ao Estado nao se desfaz por aqui.

O QUE ELE NAO FAZ
    Nao cancela selo. Selo se cancela no selador do TJMA, por gente. Este
    modulo apenas EXIGE que o numero do selo cancelado seja informado, e o
    grava na ata — para que a conferencia futura consiga ligar as duas pontas.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from ri_odt import rotulo_ato


class ExpurgoError(ValueError):
    """Impedimento de regra, com mensagem pronta para a tela."""


# ------------------------------------------------------------------ leitura


def _linha(con: sqlite3.Connection, sql: str, params: tuple = ()) -> sqlite3.Row | None:
    con.row_factory = sqlite3.Row
    return con.execute(sql, params).fetchone()


def _linhas(con: sqlite3.Connection, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    con.row_factory = sqlite3.Row
    return list(con.execute(sql, params))


def impedimentos(con: sqlite3.Connection, ato_id: int) -> list[str]:
    """Tudo o que impede o expurgo deste ato, em portugues de balcao.

    Devolve lista vazia quando pode expurgar. Nao levanta excecao: quem chama
    pode querer MOSTRAR os impedimentos antes de tentar.
    """
    ato = _linha(con, "SELECT * FROM ri_atos WHERE id=?", (ato_id,))
    if not ato:
        return ["Este ato não existe mais."]

    m = _linha(con, "SELECT * FROM ri_matriculas WHERE id=?", (ato["matricula_id"],))
    rotulo = rotulo_ato(ato["tipo"], ato["numero"], m["numero"] if m else "?")
    razoes: list[str] = []

    if (ato["origem"] or "").upper() != "MANUAL":
        razoes.append(
            f"O {rotulo} veio do acervo (origem {ato['origem']}). "
            f"Ato importado não se expurga: ele não foi lavrado aqui.")

    ultimo = _linha(con, """SELECT id FROM ri_atos WHERE matricula_id=?
                            ORDER BY id DESC LIMIT 1""", (ato["matricula_id"],))
    if ultimo and int(ultimo["id"]) != int(ato_id):
        posteriores = _linhas(con, """SELECT tipo, numero FROM ri_atos
                                      WHERE matricula_id=? AND id>? ORDER BY id""",
                              (ato["matricula_id"], ato_id))
        nomes = ", ".join(f"{r['tipo']}-{r['numero']:02d}" for r in posteriores)
        razoes.append(
            f"O {rotulo} não é o último ato da matrícula. Depois dele vêm: {nomes}. "
            f"A conferência de integridade encadeia cada ato ao anterior — tirar um "
            f"ato do meio quebraria a de todos os seguintes. Expurgue de trás para a "
            f"frente, um por vez.")

    if ato["cancelado"]:
        razoes.append(
            f"O {rotulo} já está cancelado por averbação. O que foi cancelado na ficha "
            f"não se expurga: a averbação de cancelamento ficaria apontando para o vazio.")

    dependente = _linha(con, "SELECT id, tipo, numero FROM ri_atos WHERE cancelado_por_ato_id=?",
                        (ato_id,))
    if dependente:
        razoes.append(
            f"O {rotulo} é a averbação que cancelou o "
            f"{dependente['tipo']}-{dependente['numero']:02d}. Expurgá-la deixaria aquele "
            f"ato marcado como cancelado por uma averbação que não existe mais.")

    for c in _linhas(con, """SELECT id, numero, ano, tipo FROM ri_certidoes
                             WHERE matricula_id=? AND COALESCE(cancelada,0)=0
                               AND COALESCE(corpo,'') <> ''""",
                     (ato["matricula_id"],)):
        corpo = _linha(con, "SELECT corpo FROM ri_certidoes WHERE id=?", (c["id"],))["corpo"]
        if rotulo and rotulo in (corpo or ""):
            razoes.append(
                f"A certidão {c['numero']}/{c['ano']} transcreve o {rotulo} e não está "
                f"cancelada. Certidão expedida congela o teor e circula no mundo: cancele "
                f"a certidão antes, ou não expurgue o ato.")

    fechadas = _linhas(con, """SELECT r.competencia FROM ri_ctp_remessas r
                               JOIN ri_ctp_itens i ON i.competencia = r.competencia
                               WHERE i.ato_id=? AND UPPER(COALESCE(r.situacao,''))='FECHADA'""",
                       (ato_id,))
    for r in fechadas:
        razoes.append(
            f"O {rotulo} entrou na CTP da competência {r['competencia']}, que está fechada. "
            f"O que foi transmitido ao Estado não se desfaz por aqui.")

    entregues = _linhas(con, """SELECT r.competencia FROM ri_doi_remessas r
                                JOIN ri_ctp_itens i ON i.competencia = r.competencia
                                WHERE i.ato_id=? AND UPPER(COALESCE(r.situacao,''))='ENTREGUE'""",
                        (ato_id,))
    for r in entregues:
        razoes.append(
            f"O {rotulo} entrou na DOI da competência {r['competencia']}, já entregue à "
            f"Receita Federal. O que foi transmitido não se desfaz por aqui.")

    return razoes


def levantar(con: sqlite3.Connection, ato_id: int) -> dict[str, Any]:
    """O que sairia, sem gravar nada. E o que a tela mostra antes de confirmar."""
    ato = _linha(con, "SELECT * FROM ri_atos WHERE id=?", (ato_id,))
    if not ato:
        raise ExpurgoError("Este ato não existe.")
    m = _linha(con, "SELECT * FROM ri_matriculas WHERE id=?", (ato["matricula_id"],))
    partes = _linhas(con, "SELECT * FROM ri_partes WHERE ato_id=?", (ato_id,))
    itens_ctp = _linhas(con, "SELECT competencia FROM ri_ctp_itens WHERE ato_id=?", (ato_id,))
    return {
        "ato": dict(ato),
        "matricula": dict(m) if m else None,
        "rotulo": rotulo_ato(ato["tipo"], ato["numero"], m["numero"] if m else "?"),
        "partes": [dict(p) for p in partes],
        "competencias_ctp": [r["competencia"] for r in itens_ctp],
        "impedimentos": impedimentos(con, ato_id),
    }


# --------------------------------------------------------------------- ata


def texto_da_ata(*, rotulo: str, ato: dict, matricula: dict, sv: dict,
                 data_extenso: str, motivo: str, selo_cancelado: str | None,
                 usuario: str | None, partes: list[dict] | None = None) -> str:
    """A ata de ocorrencia — o documento que passa a guardar o que saiu da ficha.

    Escrita para ser lida por quem nao estava aqui: um corregedor daqui a dez
    anos tem de conseguir reconstruir o que houve so com esta ata.
    """
    unidade = sv.get("unit_name") or "Serventia Extrajudicial"
    cns = sv.get("ri_cns") or ""
    cidade = sv.get("ri_cidade") or matricula.get("cidade") or ""
    uf = sv.get("ri_uf") or matricula.get("uf") or "MA"

    linhas = [
        "ATA DE OCORRÊNCIA — EXPURGO DE ATO LAVRADO EM TESTE DE SISTEMA",
        "",
        f"{unidade}" + (f" — CNS {cns}" if cns else ""),
        f"{cidade}/{uf}, {data_extenso}.",
        "",
        "1. DO QUE SE TRATA",
        "",
        "Durante a implantação do sistema Cartório Gestão, e antes de sua entrada "
        "definitiva em operação, foi lavrado no sistema o ato abaixo identificado, "
        "cujo selo de fiscalização foi cancelado junto ao Tribunal de Justiça do "
        "Estado do Maranhão. Cancelado o selo, o ato não subsistiu como ato de "
        "registro. Lavra-se esta ata para que dele reste memória íntegra fora da "
        "ficha, e para que a ficha não afirme ato que não houve.",
        "",
        "2. DO ATO EXPURGADO",
        "",
        f"   Ato ................. {rotulo}",
        f"   Matrícula ........... nº {matricula.get('numero')}"
        + (f", Livro {matricula.get('livro')}" if matricula.get("livro") else ""),
        f"   Data do ato ......... {ato.get('data_ato') or '—'}",
        f"   Natureza ............ {ato.get('natureza_titulo') or '—'}",
        f"   Prenotação .......... {ato.get('prenotacao') or ato.get('protocolo') or '—'}",
        f"   Lavrado em .......... {ato.get('lavrado_em') or '—'}",
        f"   Praticado por ....... {ato.get('lavrado_nome') or '—'}"
        + (f", {ato.get('lavrado_titulo')}" if ato.get("lavrado_titulo") else ""),
        f"   Emolumentos ......... {ato.get('emolumentos') or '—'}",
        f"   Selo no sistema ..... {ato.get('selo_texto') or '—'}",
        f"   Selo cancelado ...... {selo_cancelado or '—'}",
        f"   Hash de integridade . {ato.get('hash_ato') or '—'}",
    ]

    if partes:
        linhas += ["", "   Partes que constavam do ato:"]
        for p in partes:
            doc = (f"{p.get('documento_tipo') or ''} {p.get('documento_numero') or ''}").strip()
            papel = p.get("papel") or "sem papel informado"
            linhas.append(f"   - {p.get('nome')} ({doc or 'sem documento'}) — {papel}")

    linhas += [
        "",
        "3. DO FUNDAMENTO",
        "",
        f"   {motivo}",
        "",
        "4. DO TEOR INTEGRAL DO ATO EXPURGADO",
        "",
        "   Transcreve-se abaixo, na íntegra e sem alteração, o teor que constava "
        "do ato, para que nada se perca:",
        "",
    ]
    for pedaco in (ato.get("teor") or "").splitlines() or ["(o ato não tinha teor)"]:
        linhas.append(f"   {pedaco}")

    linhas += [
        "",
        "5. DO REGISTRO DESTA OCORRÊNCIA",
        "",
        "O ato foi removido da ficha da matrícula. Esta ata, o evento de auditoria "
        "correspondente e o cancelamento do selo junto ao Tribunal são, em conjunto, "
        "a prova do que houve. O número do ato volta a estar disponível na matrícula.",
        "",
        f"Lançada por: {usuario or 'não identificado'}.",
        f"{cidade}/{uf}, {data_extenso}.",
    ]
    return "\n".join(linhas)


# ------------------------------------------------------------------ escrita


def expurgar(con: sqlite3.Connection, ato_id: int, *, sv: dict, agora: str,
             data_extenso: str, motivo: str, selo_cancelado: str | None = None,
             usuario: str | None = None) -> dict[str, Any]:
    """Remove o ato e grava a ata. Roda DENTRO de uma transacao de quem chama.

    Nao chama audit(): auditoria abre transacao propria, e chamada aqui dentro
    travaria o banco. Quem chama audita depois de fechar.
    """
    motivo = (motivo or "").strip()
    if len(motivo) < 15:
        raise ExpurgoError(
            "Escreva o fundamento do expurgo com pelo menos quinze letras. "
            "Esta é a única explicação que vai restar do ato.")

    dados = levantar(con, ato_id)
    if dados["impedimentos"]:
        raise ExpurgoError(" ".join(dados["impedimentos"]))

    ato, m = dados["ato"], dados["matricula"]
    ata = texto_da_ata(
        rotulo=dados["rotulo"], ato=ato, matricula=m, sv=sv,
        data_extenso=data_extenso, motivo=motivo,
        selo_cancelado=(selo_cancelado or "").strip() or None,
        usuario=usuario, partes=dados["partes"],
    )

    con.execute(
        """INSERT INTO ri_expurgos
           (matricula_id, matricula_numero, ato_rotulo, ato_tipo, ato_numero,
            ato_data, ato_natureza, ato_selo, selo_cancelado, ato_hash,
            ato_teor, partes_json, motivo, ata, expurgado_em, expurgado_por)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (m["id"], m["numero"], dados["rotulo"], ato["tipo"], int(ato["numero"]),
         ato["data_ato"], ato["natureza_titulo"], ato["selo_texto"],
         (selo_cancelado or "").strip() or None, ato["hash_ato"],
         ato["teor"], json.dumps(dados["partes"], ensure_ascii=False, default=str),
         motivo, ata, agora, usuario),
    )
    expurgo_id = int(con.execute("SELECT last_insert_rowid()").fetchone()[0])

    # As partes do ato saem com ele. As partes da matricula que nao pertencem a
    # ato nenhum ficam: elas descrevem a titularidade, nao este ato.
    con.execute("DELETE FROM ri_partes WHERE ato_id=?", (ato_id,))
    # Item de CTP so sai quando a competencia nao esta fechada — e isso a trava
    # ja garantiu acima.
    con.execute("DELETE FROM ri_ctp_itens WHERE ato_id=?", (ato_id,))
    con.execute("DELETE FROM ri_atos WHERE id=?", (ato_id,))

    return {"expurgo_id": expurgo_id, "rotulo": dados["rotulo"],
            "matricula_id": m["id"], "matricula_numero": m["numero"],
            "ata": ata, "selo_no_sistema": ato["selo_texto"],
            "selo_cancelado": (selo_cancelado or "").strip() or None}
