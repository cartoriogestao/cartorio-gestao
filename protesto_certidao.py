"""
A certidao de protesto — buscar pelo nome, dizer o que ha, e assinar.

E O QUE O BALCAO MAIS PEDE, e por muito tempo nao teve como responder: ate
25/08/2026 a carga do acervo trazia os 1.366 titulos e NENHUM devedor, e
certidao de protesto se pede pelo nome e pelo CPF de quem foi protestado.

OS TEXTOS SAO OS DA CASA, e nao redacao nova
    Medidos nas 65 certidoes de `tbProtesto_Certidao`: 46 negativas, 12 de
    cancelamento e 7 positivas. As frases abaixo sao as que sairam desta
    serventia por anos — a regra do oficial, de 24/08/2026: na duvida, faca
    como o E-Oficio fazia.

    Duas coisas foram escolhidas, e ficam ditas:

    1. "a requerimento VERBAL de parte interessada" e o que as 44 negativas
       dizem, e e o que sai quando ninguem informa o requerente. Informado o
       requerente, sai "a requerimento de FULANO" — dizer "verbal" quando o
       pedido foi escrito e assinado seria certificar o que nao houve.
    2. O fecho do cancelamento existe no acervo em duas formas, singular e
       plural ("no referido livro e folha consta a BAIXA" / "nos referidos
       livros e folhas constam as BAIXAS"). Sai a que couber na quantidade.
       A grafia e a da forma mais nova — "acordo", e nao "acôrdo".

O QUE ENTRA NA BUSCA
    So titulo que CHEGOU A PROTESTO: o que tem ato de PROTESTO lavrado.
    Apontamento nao e protesto — titulo apontado e pago no triduo nunca foi
    protestado, e certidao que o mostrasse seria certidao que mente contra a
    pessoa. Medido no acervo: dos 189 titulos pagos, so 4 tinham chegado a
    protesto.

A CERTIDAO NAO E ATO DE UM TITULO
    Por isso ela nao mora em `pt_atos`, cujo `titulo_id` e NOT NULL: a
    negativa nao tem titulo nenhum. Certidao e ato da SERVENTIA sobre uma
    pessoa. Numeracao por exercicio, teor congelado e hash — a mesma forma do
    recibo do caixa, que ja roda nesta casa.

O TEOR CONGELA NA EMISSAO
    Depois de emitida, a certidao nao se recalcula: o que ela disse e o que
    fica, com o sha256 para provar que a segunda via e a mesma folha. Protesto
    novo lavrado amanha nao muda a certidao de hoje — mudar seria reescrever o
    que a serventia ja afirmou.

FUNDAMENTO
    Lei 9.492/1997, arts. 27 e 31 (certidao), art. 26 (cancelamento).
    Codigo de Normas do Foro Extrajudicial do Maranhao — Prov. TJMA 28/2026.
"""
from __future__ import annotations
from certidao_texto import sem_linha_de_assinatura_a_mao

import hashlib
import json
import sqlite3
from typing import Any

import cancelamento_certidao as CANC
import protesto as PT
from caixa_schema import reais
from pt_schema import normalizar_nome

TIPOS = ("NEGATIVA", "POSITIVA", "CANCELAMENTO")

MODELO_CERTIDAO_NEGATIVA = (
    "CERTIFICO, {pedido}, que revendo nesta Serventia os Livros de Registro "
    "de Protestos de Letras e Outros Títulos, a partir do mês de {desde}, "
    "neles NÃO ENCONTREI protesto contra {identificacao}. Período de Busca: "
    "{periodo_anos} Anos."
)
MODELO_CERTIDAO_POSITIVA = "{cabeca} {corpo}"
MODELO_CERTIDAO_CANCELAMENTO = (
    "{cabeca} {corpo} {fecho} O referido é verdade e aos próprios livros em "
    "meu poder e Cartório reporto e dou fé."
)

# "Período de Busca: 5 Anos" — o que as negativas do acervo dizem, todas.
PERIODO_PADRAO_ANOS = 5

MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro")


class CertidaoError(ValueError):
    """Impedimento de regra, com mensagem pronta para o balcao."""


# --------------------------------------------------------------- utilidades


def _digitos(valor: Any) -> str:
    return "".join(c for c in str(valor or "") if c.isdigit())


def tipo_do_documento(documento: Any) -> str | None:
    """CPF, CNPJ ou None — pelo tamanho, que aqui e definicao e nao chute.

    CPF tem 11 digitos e CNPJ tem 14; nao ha terceiro caso. Medido nos 1.366
    devedores do acervo: 980 com 11 e 386 com 14, nenhum com outro tamanho.
    """
    d = _digitos(documento)
    return "CPF" if len(d) == 11 else "CNPJ" if len(d) == 14 else None


def formatar_documento(documento: Any) -> str:
    """`04785512388` -> `047.855.123-88`. Sem tamanho conhecido, devolve como veio."""
    d = _digitos(documento)
    if len(d) == 11:
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    return str(documento or "").strip()


def _por_extenso_ano(ano: int) -> str:
    """`2020` -> `dois mil e vinte`. So os anos que uma certidao alcanca."""
    unidades = ("", "um", "dois", "três", "quatro", "cinco", "seis", "sete",
                "oito", "nove")
    dez_a_dezenove = ("dez", "onze", "doze", "treze", "catorze", "quinze",
                      "dezesseis", "dezessete", "dezoito", "dezenove")
    dezenas = ("", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta",
               "setenta", "oitenta", "noventa")
    n = int(ano)
    if not 2000 <= n <= 2099:
        return str(n)
    resto = n - 2000
    if resto == 0:
        return "dois mil"
    if resto < 10:
        return f"dois mil e {unidades[resto]}"
    if resto < 20:
        return f"dois mil e {dez_a_dezenove[resto - 10]}"
    d, u = divmod(resto, 10)
    return (f"dois mil e {dezenas[d]}" if not u
            else f"dois mil e {dezenas[d]} e {unidades[u]}")


def data_limite(hoje: str, anos: int = PERIODO_PADRAO_ANOS) -> str:
    """A data a partir da qual se busca. `2026-08-25`, 5 anos -> `2021-08-25`.

    Nao usa `datetime`: a data vem de quem chama, como no resto da casa, e
    subtrair ano de texto ISO e conta de inteiro.
    """
    ano, mes, dia = str(hoje)[:10].split("-")
    return f"{int(ano) - int(anos):04d}-{mes}-{dia}"


# ----------------------------------------------------------------- a busca


def buscar(con: sqlite3.Connection, *, nome: str | None = None,
           documento: str | None = None, desde: str | None = None) -> list[dict]:
    """Os protestos de uma pessoa, no periodo. So LE.

    SO ENTRA TITULO QUE CHEGOU A PROTESTO — o que tem ato de PROTESTO. O
    apontamento nao basta: titulo apontado e pago no triduo nunca foi
    protestado, e certidao que o mostrasse mentiria contra a pessoa.

    O documento casa por DIGITOS, e nao pelo que foi digitado: no acervo ele
    esta sem pontuacao, e quem pede traz o CPF com ponto e traco.
    """
    termo = (nome or "").strip()
    doc = _digitos(documento)
    if not termo and not doc:
        raise CertidaoError(
            "Informe o nome ou o CPF/CNPJ de quem se quer a certidão — sem um "
            "dos dois não há o que buscar.")

    onde, params = [], []
    if doc:
        onde.append("REPLACE(REPLACE(REPLACE(COALESCE(d.documento_numero,''),"
                    "'.',''),'-',''),'/','') = ?")
        params.append(doc)
    if termo:
        # SEM ACENTO E SEM CAIXA, pela coluna `nome_norm`. `UPPER()` do SQLite
        # e ASCII: 'josé' vira 'JOSé', e quem digitasse assim nao achava
        # 'JOSÉ DA SILVA'. Certidao que nao acha por causa de grafia e
        # certidao que mente.
        onde.append("d.nome_norm LIKE ?")
        params.append(f"%{normalizar_nome(termo)}%")
    # NOME **OU** DOCUMENTO, e nao os dois juntos: quem traz o CPF certo e o
    # nome com um acento a menos tem de aparecer assim mesmo. Certidao que nao
    # acha por causa de grafia e certidao que mente.
    filtro = " OR ".join(onde)
    if desde:
        filtro = f"({filtro}) AND a.data_ato >= ?"
        params.append(str(desde)[:10])

    linhas = con.execute(
        f"""SELECT t.id titulo_id, t.numero_titulo, t.especie, t.situacao,
                   t.valor_centavos, t.saldo_centavos, t.data_emissao,
                   t.data_vencimento, t.cedente_nome,
                   d.nome devedor_nome, d.documento_tipo, d.documento_numero,
                   a.id ato_id, a.data_ato, a.folha, a.numero_ordem,
                   a.detalhe_json, a.selo
              FROM pt_atos a
              JOIN pt_titulos t ON t.id = a.titulo_id
              JOIN pt_devedores d ON d.titulo_id = t.id
             WHERE a.tipo = 'PROTESTO' AND ({filtro})
             ORDER BY a.data_ato, t.id""", params).fetchall()

    achados = []
    for r in linhas:
        detalhe = json.loads(r["detalhe_json"] or "{}")
        baixa = con.execute(
            """SELECT data_ato, motivo_cancelamento FROM pt_atos
                WHERE titulo_id=? AND tipo='CANCELAMENTO'
                ORDER BY id DESC LIMIT 1""", (r["titulo_id"],)).fetchone()
        # OS EFEITOS SUSPENSOS POR ORDEM JUDICIAL — e a certidao tem de
        # dizer, porque ela e o papel que faz o banco negar credito.
        #
        # **O PROTESTO NAO SOME DA CERTIDAO**, e isso seria mentir do outro
        # lado: ele existe e esta no livro, e certidao negativa sobre quem tem
        # protesto e o erro que nao se desfaz. O que a ordem faz e parar a
        # PUBLICIDADE dele — e a forma de cumpri-la, recebida depois da
        # lavratura, e a averbacao no proprio registro consignando que os
        # efeitos estao suspensos.
        suspenso = PT.efeito_suspensivo_em_vigor(con, int(r["titulo_id"]))
        achados.append({
            "titulo_id": int(r["titulo_id"]),
            "numero_titulo": r["numero_titulo"],
            "especie": r["especie"],
            "situacao": r["situacao"],
            "devedor": r["devedor_nome"],
            "devedor_documento": formatar_documento(r["documento_numero"]),
            "cedente": r["cedente_nome"],
            "valor": reais(int(r["valor_centavos"] or 0)),
            "saldo": reais(int(r["saldo_centavos"] or 0)),
            "data_emissao": r["data_emissao"],
            "data_vencimento": r["data_vencimento"],
            "data_protesto": r["data_ato"],
            "efeitos_suspensos": bool(suspenso),
            "suspensao_juizo": (suspenso or {}).get("juizo", ""),
            "suspensao_processo": (suspenso or {}).get("processo", ""),
            "suspensao_em": (suspenso or {}).get("data_ato", ""),
            "livro": detalhe.get("livro_do_acervo"),
            "folha": r["folha"],
            "numero_ordem": r["numero_ordem"],
            "selo": r["selo"],
            "cancelado": bool(baixa),
            "data_cancelamento": baixa["data_ato"] if baixa else None,
            "motivo_cancelamento": (baixa["motivo_cancelamento"]
                                    if baixa else None),
        })
    return achados


def tipo_para(achados: list[dict]) -> str:
    """Que certidao cabe no que se achou.

    Nada achado, NEGATIVA. Tudo cancelado, CANCELAMENTO — que e a positiva
    mais o fecho do art. 26. Sobrando protesto em pe, POSITIVA.
    """
    if not achados:
        return "NEGATIVA"
    if all(a["cancelado"] for a in achados):
        return "CANCELAMENTO"
    return "POSITIVA"


# ------------------------------------------------------------------ o teor


def _dia(data: Any) -> str:
    """`2022-02-26` -> `26/02/2022`. E como as 19 certidoes do acervo escrevem.

    Data em ISO na certidao seria data que o cliente le errado — e a certidao
    e papel de balcao, nao tela de sistema.
    """
    s = str(data or "")[:10]
    if len(s) == 10 and s[4] == "-":
        return f"{s[8:10]}/{s[5:7]}/{s[:4]}"
    return s


def _mes_e_ano(data: str) -> str:
    ano, mes = str(data)[:4], int(str(data)[5:7])
    return f"{MESES[mes - 1].capitalize()} de {ano}"


def _linha_do_protesto(a: dict, i: int) -> str:
    """Uma linha por protesto, com o que a casa punha na certidao.

    As colunas sao as de `tbProtesto_Certidao_Itens`, conferidas uma a uma
    contra `tbAvisoProtesto` em 25/08/2026 — os 19 itens do acervo casaram
    todos: livro, folha, numero do titulo, valor, emissao, vencimento e as
    datas do protesto e da baixa.
    """
    onde = []
    if a.get("livro"):
        onde.append(f"Livro {a['livro']}")
    if a.get("folha"):
        onde.append(f"fl. {a['folha']}")
    if a.get("numero_ordem"):
        onde.append(f"n. {a['numero_ordem']}")
    lugar = ", ".join(onde) or "livro e folha não constam do acervo"
    # O CEDENTE SO SAI SE FOR OUTRA PESSOA. Em 28 dos 1.366 titulos o acervo
    # traz o mesmo codigo como cedente e como devedor — o que nao acontece na
    # vida real, e provavelmente e digitacao do comeco do E-Oficio. Certificar
    # que fulano apresentou protesto contra fulano seria pôr no papel um
    # engano que a carga so copiou.
    cedente = (a.get("cedente") or "").strip()
    if cedente and cedente.upper() == (a.get("devedor") or "").strip().upper():
        cedente = ""
    partes = [
        f"{i}) Título n. {a['numero_titulo']}",
        f"espécie {a['especie']}" if a.get("especie") else None,
        f"valor R$ {a['valor']}",
        f"emitido em {_dia(a['data_emissao'])}" if a.get("data_emissao") else None,
        f"vencido em {_dia(a['data_vencimento'])}" if a.get("data_vencimento") else None,
        f"apresentado por {cedente}" if cedente else None,
        f"protestado em {_dia(a['data_protesto'])}",
        lugar,
    ]
    linha = "; ".join(p for p in partes if p)
    if a.get("cancelado"):
        linha += f"; CANCELADO em {_dia(a['data_cancelamento'])}"
        if a.get("motivo_cancelamento"):
            linha += f" ({a['motivo_cancelamento']})"
    return linha + "."


def montar_teor(*, tipo: str, nome: str, documento: str | None,
                achados: list[dict], desde: str, hoje: str,
                periodo_anos: int = PERIODO_PADRAO_ANOS,
                requerente: str | None = None, modelo: str | None = None) -> str:
    """O teor da certidao, nas palavras que esta casa usa.

    Nao grava nada e nao le banco: recebe o que a busca achou e devolve texto.
    """
    if tipo not in TIPOS:
        raise CertidaoError(
            f"Tipo de certidão desconhecido: {tipo!r}. Os que existem são: "
            f"{', '.join(TIPOS)}.")
    quem = (requerente or "").strip()
    # "a requerimento VERBAL de parte interessada" e o que as 44 negativas do
    # acervo dizem. Dizer "verbal" quando o pedido foi escrito e assinado
    # seria certificar o que nao houve — por isso, informado o requerente, ele
    # e quem aparece.
    pedido = (f"a requerimento de {quem}" if quem
              else "a requerimento verbal de parte interessada")
    doc_tipo = tipo_do_documento(documento)
    identificacao = nome.strip()
    if documento:
        identificacao += f" {doc_tipo or 'documento'}: {formatar_documento(documento)}"

    if tipo == "NEGATIVA":
        try:
            return (modelo or MODELO_CERTIDAO_NEGATIVA).format(
                pedido=pedido, desde=_mes_e_ano(desde),
                identificacao=identificacao, periodo_anos=periodo_anos,
                nome=nome.strip())
        except (KeyError, ValueError) as erro:
            raise CertidaoError(f"O modelo da certidão negativa está incompleto: {erro}.") from erro

    if not achados:
        raise CertidaoError(
            f"Não há protesto a certificar: a busca não achou nada, e a "
            f"certidão que cabe é a NEGATIVA, não a {tipo}.")

    inscrito = (f" e inscrito no {doc_tipo or 'documento'}: "
                f"{formatar_documento(documento)}" if documento else "")
    cabeca = (
        f"CERTIFICO {pedido}, que revendo em meu Cartório, os livros de "
        f"Registros de Protestos de Letras e Outros Títulos, a partir do ano "
        f"de {_por_extenso_ano(int(str(desde)[:4]))} até a presente data, "
        f"neles encontrei protesto contra {nome.strip()}{inscrito}.")
    corpo = " ".join(_linha_do_protesto(a, i)
                     for i, a in enumerate(achados, 1))

    if tipo == "POSITIVA":
        try:
            return (modelo or MODELO_CERTIDAO_POSITIVA).format(
                cabeca=cabeca, corpo=corpo, nome=nome.strip(), pedido=pedido)
        except (KeyError, ValueError) as erro:
            raise CertidaoError(f"O modelo da certidão positiva está incompleto: {erro}.") from erro

    # CANCELAMENTO: a positiva mais o fecho do art. 26. O acervo tem as duas
    # formas — singular e plural —, e sai a que couber na quantidade.
    if len(achados) == 1:
        fecho = ("CERTIFICO ainda que no referido livro e folha consta a BAIXA "
                 "e o CANCELAMENTO do mesmo de acordo com o art. 26 da lei "
                 "9492/97.")
    else:
        fecho = ("CERTIFICO ainda que nos referidos livros e folhas constam as "
                 "BAIXAS e o CANCELAMENTOS dos mesmos de acordo com o art. 26 "
                 "da lei 9492/97.")
    try:
        return (modelo or MODELO_CERTIDAO_CANCELAMENTO).format(
            cabeca=cabeca, corpo=corpo, fecho=fecho, nome=nome.strip(),
            pedido=pedido)
    except (KeyError, ValueError) as erro:
        raise CertidaoError(f"O modelo da certidão de cancelamento está incompleto: {erro}.") from erro


def hash_certidao(numero: int, ano: int, nome: str, teor: str,
                  emitida_em: str) -> str:
    """Impressao digital da certidao, para provar que a segunda via e a mesma."""
    bruto = f"{numero}|{ano}|{nome}|{emitida_em}|{teor}"
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- emitir


def proximo_numero(con: sqlite3.Connection, ano: int) -> int:
    """O proximo numero do exercicio. So LE — nao consome nada.

    GET nao abre transacao de escrita: a tela de conferencia chama isto, e
    contador consumido num GET fica preso no `busy_timeout` enquanto outro
    balcao lavra.
    """
    linha = con.execute(
        "SELECT MAX(numero) n FROM pt_certidoes WHERE ano=?",
        (int(ano),)).fetchone()
    return int(linha["n"] if linha and linha["n"] else 0) + 1


def emitir(con: sqlite3.Connection, *, nome: str, documento: str | None,
           achados: list[dict], hoje: str, agora: str, tipo: str | None = None,
           periodo_anos: int = PERIODO_PADRAO_ANOS, desde: str | None = None,
           requerente: str | None = None, finalidade: str | None = None,
           usuario: str | None = None) -> dict:
    """Emite a certidao, com numero do exercicio, teor congelado e hash. ESCREVE.

    O TIPO SAI DO QUE SE ACHOU, e nao de quem pede: `tipo_para(achados)`.
    Deixar escolher deixaria sair negativa sobre quem tem protesto — que e a
    certidao que faz o banco emprestar para quem nao devia.

    Passar `tipo` serve para o caso em que o oficial quer a POSITIVA de quem
    tem tudo cancelado; pedir tipo que o achado nao comporta e recusado.
    """
    if not (nome or "").strip():
        raise CertidaoError("A certidão precisa do nome de quem ela é.")
    cabivel = tipo_para(achados)
    escolhido = (tipo or cabivel).strip().upper()
    if escolhido not in TIPOS:
        raise CertidaoError(
            f"Tipo de certidão desconhecido: {escolhido!r}. Os que existem "
            f"são: {', '.join(TIPOS)}.")
    if escolhido == "NEGATIVA" and achados:
        raise CertidaoError(
            f"Não se emite certidão negativa: a busca achou "
            f"{len(achados)} protesto(s) contra {nome.strip()}. Negativa "
            f"sobre quem tem protesto é o que faz o banco emprestar para quem "
            f"não devia.")
    if escolhido != "NEGATIVA" and not achados:
        raise CertidaoError(
            "A busca não achou protesto nenhum — a certidão que cabe é a "
            "NEGATIVA.")

    limite = desde or data_limite(hoje, periodo_anos)
    try:
        import modelos_da_casa as MODELOS
        chave = {"NEGATIVA": "PT_CERTIDAO_NEGATIVA",
                 "POSITIVA": "PT_CERTIDAO_POSITIVA",
                 "CANCELAMENTO": "PT_CERTIDAO_CANCELAMENTO"}[escolhido]
        modelo = MODELOS.corpo_de(con, chave)
    except Exception:
        modelo = None
    teor = montar_teor(tipo=escolhido, nome=nome, documento=documento,
                       achados=achados, desde=limite, hoje=hoje,
                       periodo_anos=periodo_anos, requerente=requerente,
                       modelo=modelo)
    ano = int(str(hoje)[:4])
    numero = proximo_numero(con, ano)
    # A LINHA DA ASSINATURA A MAO SAI ANTES DO HASH, E NAO ANTES DO
    # INSERT. Esta chamada estava DENTRO do texto do SQL — colada entre
    # as aspas e o `INSERT INTO`, de modo que o banco recusava com
    # «near "teor": syntax error» e a certidao NAO SAIA. Posta so antes
    # do `con.execute`, o teor gravado deixaria de ser o teor que o
    # `hash_certidao` carimbou, e a conferencia de «este e o teor que
    # saiu?» passaria a falhar em toda certidao nova.
    teor = sem_linha_de_assinatura_a_mao(teor)
    impressao = hash_certidao(numero, ano, nome.strip(), teor, agora)
    try:
        cur = con.execute(
            """INSERT INTO pt_certidoes(numero, ano, tipo, nome, documento,
                   documento_tipo, requerente, finalidade, periodo_anos, desde,
                   achados, achados_json, teor, hash_certidao, emitida_em,
                   emitida_por)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (numero, ano, escolhido, nome.strip(), _digitos(documento) or None,
             tipo_do_documento(documento), (requerente or "").strip() or None,
             (finalidade or "").strip() or None, int(periodo_anos), limite,
             len(achados), json.dumps(achados, ensure_ascii=False), teor,
             impressao, agora, usuario))
    except sqlite3.IntegrityError as erro:
        raise CertidaoError(
            f"A certidão n. {numero}/{ano} já existe. Nada foi emitido — "
            f"tente de novo. ({erro})") from erro
    return {"certidao_id": int(cur.lastrowid), "numero": numero, "ano": ano,
            "tipo": escolhido, "teor": teor, "hash": impressao,
            "achados": len(achados), "desde": limite}


# --------------------------------------------------------------- consultas


def certidao(con: sqlite3.Connection, certidao_id: int) -> sqlite3.Row | None:
    """A certidao, como foi emitida. So LE."""
    return con.execute("SELECT * FROM pt_certidoes WHERE id=?",
                       (int(certidao_id),)).fetchone()


def listar(con: sqlite3.Connection, *, termo: str = "",
           limite: int = 100) -> list[sqlite3.Row]:
    """As certidoes emitidas, da mais nova para a mais velha. So LE."""
    t = (termo or "").strip()
    if not t:
        return list(con.execute(
            "SELECT * FROM pt_certidoes ORDER BY ano DESC, numero DESC LIMIT ?",
            (int(limite),)))
    return list(con.execute(
        """SELECT * FROM pt_certidoes
            WHERE UPPER(nome) LIKE UPPER(?) OR documento LIKE ?
                  OR CAST(numero AS TEXT) = ?
            ORDER BY ano DESC, numero DESC LIMIT ?""",
        (f"%{t}%", f"%{_digitos(t) or t}%", t, int(limite))))


def cancelar(con: sqlite3.Connection, certidao_id: int, *, motivo: str,
             agora: str, usuario: str | None = None,
             selo_cancelado_tjma: Any = False) -> dict:
    """Cancela a certidao emitida. ESCREVE. O teor fica — o que saiu, saiu.

    Certidao errada nao se apaga: apaga-la deixaria a via que o cliente levou
    sem par no banco, e e justamente essa via que alguem vai conferir.
    """
    linha = certidao(con, certidao_id)
    if not linha:
        raise CertidaoError("Certidão não encontrada.")
    if int(linha["cancelada"] or 0):
        raise CertidaoError(
            f"A certidão n. {linha['numero']}/{linha['ano']} já está cancelada "
            f"desde {linha['cancelada_em']}.")
    razao = (motivo or "").strip()
    if len(razao) < 10:
        raise CertidaoError(
            "Escreva por que a certidão está sendo cancelada, com pelo menos "
            "dez letras — é o que fica no lugar dela.")
    if not CANC.declaracao_confirmada(selo_cancelado_tjma):
        raise CertidaoError(CANC.MENSAGEM_DECLARACAO_OBRIGATORIA)
    con.execute(
        """UPDATE pt_certidoes SET cancelada=1, motivo_cancelamento=?,
                                   cancelada_em=?, cancelada_por=?,
                                   declaracao_selo_tjma_em=?,
                                   declaracao_selo_tjma_por=?
            WHERE id=?""", (razao, agora, usuario, agora, usuario,
                              int(certidao_id)))
    return CANC.concluir(
        con, tabela="pt_certidoes", ato_id=int(certidao_id), motivo=razao,
        agora=agora, usuario=usuario)
