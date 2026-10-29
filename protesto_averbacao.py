"""A AVERBAÇÃO DE RETIFICAÇÃO DE ERRO MATERIAL, DE OFÍCIO — Lei 9.492/1997, art. 25.

    «A averbação de retificação de erros materiais pelo serviço poderá ser
     efetuada de ofício ou a requerimento do interessado, sob
     responsabilidade do Tabelião de Protesto de Títulos.»

O CASO QUE A FEZ NASCER (29/10/2026)
    A carga do acervo do E-Ofício gravou o cedente (o credor) errado nos 1.409
    títulos. O cadastro foi corrigido no mesmo dia, com uma linha de auditoria
    `PROTESTO_CORRECAO_CEDENTE_CARGA` por título — mas o termo dos atos já
    lavrados CONGELOU o credor em `pt_atos.teor`. Medido na produção (só
    leitura): 7 protestos com o credor errado no termo, 12 com o termo sem
    credor nenhum, e 2 termos de cancelamento (um de cada). O oficial aprovou a
    averbação de retificação de ofício pelo art. 25.

O QUE SE MEDIU ANTES DE CONSTRUIR — a regra da casa, «na dúvida, imitar o E-Ofício»
    - O E-OFÍCIO NÃO TINHA AVERBAÇÃO DE RETIFICAÇÃO NO PROTESTO. Nenhuma tabela
      nem tipo de ato. O que havia era a rotina 82, «Retifica protesto»: 40
      linhas em `tbAuditor` (2022 a 2026), todas «retificado titulo com
      ocorrência X — Justificativa: erro». Ela desfazia a ocorrência no
      cadastro para o ato ser refeito — sem selo, sem custas e sem uma palavra
      em papel nenhum (0 das 72 certidões do acervo citam retificação).
    - O ITEM 17.3 da tabela («Averbação de documento que determine alteração
      ou cancelamento de protestos») saiu em 77 protocolos, todos de
      CANCELAMENTO, e sempre cobrado. Nunca numa retificação. O aparelho do
      selo não tem caminho de averbação no Protesto: os seis caminhos são
      título, atos em geral, pagamento, baixa/cancelamento, retirada e
      certidão (`ato_selado.CAMINHO_DO_ATO`).
    - NESTA CASA o precedente é outro, e foi aceito: «corrigir protesto é
      averbar ao lado, e não reescrever» (`protesto_termo`); a redação da
      averbação de retificação do Registro Civil (`rc_averbacao_modelos`,
      medida no E-Ofício e nas averbações 361, 431 e 433); e o efeito
      suspensivo, que é averbação de ofício no próprio registro e não sela nem
      cobra (`protesto.lancar_efeito_suspensivo`).

O QUE ELA É
    Um ato `AVERBACAO_RETIFICACAO` em `pt_atos`, ligado ao ato que retifica por
    `detalhe_json.ato_retificado_id`. Leva o teor da averbação (o que constou,
    o que passa a constar e o fundamento — `protesto_termo.
    montar_averbacao_retificacao`, texto do catálogo), quem lavrou
    (`criado_por`) e a afirmação expressa do oficial. Não ocupa lugar em livro:
    é à margem do registro, como o cancelamento.

    **O ATO RETIFICADO NÃO SE TOCA.** O teor dele fica como foi lavrado; é a
    averbação que o corrige. Quem lê o registro lê os dois — a ficha mostra a
    averbação ao lado do termo, o instrumento e a certidão a mencionam.

SELO E CUSTAS: NENHUM, E ISSO É PERGUNTA AO OFICIAL
    Retificação de erro do próprio serviço, de ofício, não se cobra de
    ninguém; e sem precedente de selo (nem item, nem caminho no aparelho) o
    sistema não inventa um. O ato nasce sem selo e sem lançamento no caixa —
    está em `protesto_selo_previo.ATOS_SEM_SELO_PROPRIO`. Se o oficial decidir
    que há selo, ele entra por decisão dele, e não por dedução daqui.

QUEM LAVRA
    Só o ADMIN em pessoa — o art. 25 diz «sob responsabilidade do Tabelião».
    Robô não lavra (a rota recusa, e este módulo recusa de novo). E só com a
    afirmação expressa do contrato comum da casa (caixa «Afirmo» e pelo menos
    30 letras — `protesto_selo_previo.validar_afirmacao`), que a rota grava em
    `audit("AFIRMACAO_EXPRESSA", ...)`.

O CREDOR QUE O REGISTRO DIZ
    O termo do protesto e o do cancelamento escrevem o credor com a peça
    «credor» de `PT_INSTRUMENTO_DESCRICAO` — o livro lavra o PADRÃO, sem o
    ajuste da casa (`protesto_termo.montar`). Por isso este módulo sabe ler
    o credor que ficou no texto, e `divergencia_do_credor` compara com o
    cadastro: é o que a ficha mostra e o que faz o instrumento recusar sair
    contra o registro (`protesto_instrumento.emitir`).
"""
from __future__ import annotations

import json
from typing import Any

import afirmacoes_expressas as AFX
from bd_nativo import banco

TIPO = "AVERBACAO_RETIFICACAO"

#: Os atos que têm texto lavrado, e por isso se retificam por averbação — e
#: como a averbação os chama no papel.
ATOS_QUE_SE_RETIFICAM: dict[str, str] = {
    "PROTESTO": "registro do protesto",
    "CANCELAMENTO": "termo do cancelamento",
}

#: Quem lavra — o art. 25 diz «sob responsabilidade do Tabelião».
PAPEL_QUE_LAVRA = "ADMIN"

#: A regra na afirmação expressa (o nome que a tela das afirmações filtra).
REGRA_DA_AFIRMACAO = "AVERBACAO_RETIFICACAO_DE_OFICIO"
#: A linha de auditoria do ato, além da afirmação.
ACAO_DA_AUDITORIA = "PROTESTO_AVERBACAO_RETIFICACAO"

FUNDAMENTO = "Lei 9.492/1997, art. 25 — retificação de erro material, de ofício"

#: O elemento que se retifica quando é o credor: o nome da peça do registro,
#: com o artigo — é como o teor da averbação o escreve.
ELEMENTO_CREDOR = "o credor (sacador/favorecido)"

ERRADO = "ERRADO"
OMITIDO = "OMITIDO"

TETO_DO_ELEMENTO = 80
TETO_DO_VALOR = 400

OBSERVACAO = ("Averbação de retificação de erro material, de ofício "
              "(Lei 9.492/1997, art. 25).")


class AverbacaoError(ValueError):
    """Impedimento de regra, com mensagem pronta para a tela."""


def _corrido(texto: Any) -> str:
    return " ".join(str(texto or "").split())


def _normal(texto: Any) -> str:
    return _corrido(texto).upper()


def _detalhe(texto: Any) -> dict:
    try:
        lido = json.loads(texto or "{}")
    except (TypeError, ValueError):
        return {}
    return lido if isinstance(lido, dict) else {}


def _data_br(iso: Any) -> str:
    s = str(iso or "")[:10]
    if len(s) == 10 and s[4] == "-" and s[7] == "-":
        return f"{s[8:10]}/{s[5:7]}/{s[:4]}"
    return s


# ------------------------------------------------------------- o que já há


def averbacoes_do_titulo(con, titulo_id: int) -> list[dict]:
    """As averbações de retificação VIVAS do título, na ordem em que se
    lavraram. Só LÊ.

    O ato retificado mora no `detalhe_json`, e se lê em Python: operador de
    JSON no SQL seria acoplar a regra ao banco (a régua de
    `afirmacoes_expressas.listar`).
    """
    saida = []
    for linha in banco(con).ler(
            """SELECT id, titulo_id, data_ato, teor, detalhe_json, criado_por,
                      criado_em
                 FROM pt_atos
                WHERE titulo_id = %s AND tipo = %s AND cancelado = 0
                ORDER BY id""", (int(titulo_id), TIPO)):
        d = _detalhe(linha["detalhe_json"])
        saida.append({
            "id": int(linha["id"]), "titulo_id": int(linha["titulo_id"]),
            "data_ato": linha["data_ato"], "data_br": _data_br(linha["data_ato"]),
            "teor": linha["teor"] or "", "criado_por": linha["criado_por"],
            "ato_retificado_id": d.get("ato_retificado_id"),
            "ato_retificado_tipo": d.get("ato_retificado_tipo") or "",
            "elemento": str(d.get("elemento") or ""),
            "constava": str(d.get("constava") or ""),
            "correto": str(d.get("correto") or ""),
            "forma": str(d.get("forma") or ""),
        })
    return saida


def averbacoes_do_ato(con, ato_id: int, titulo_id: int) -> list[dict]:
    """As averbações vivas de UM ato lavrado. Só LÊ."""
    return [a for a in averbacoes_do_titulo(con, titulo_id)
            if str(a["ato_retificado_id"]) == str(int(ato_id))]


def atos_que_se_retificam(con, titulo_id: int) -> list[dict]:
    """Os atos vivos do título que têm texto lavrado — os que a averbação
    alcança. Só LÊ."""
    tipos = tuple(ATOS_QUE_SE_RETIFICAM)
    marcas = ", ".join(["%s"] * len(tipos))
    return [dict(a) | {"nome": ATOS_QUE_SE_RETIFICAM[a["tipo"]],
                       "data_br": _data_br(a["data_ato"])}
            for a in banco(con).ler(
                f"""SELECT id, titulo_id, tipo, data_ato, teor
                      FROM pt_atos
                     WHERE titulo_id = %s AND tipo IN ({marcas})
                       AND cancelado = 0
                       AND COALESCE(teor, '') <> ''
                     ORDER BY id""", (int(titulo_id), *tipos))]


def nome_do_ato(ato: dict) -> str:
    """Como a averbação chama o ato que retifica: «registro do protesto», ou
    «termo do cancelamento de 28/10/2026, do registro do protesto»."""
    tipo = str(ato.get("tipo") or "")
    if tipo == "CANCELAMENTO":
        return (f"termo do cancelamento de {_data_br(ato.get('data_ato'))}, "
                f"do registro do protesto")
    return ATOS_QUE_SE_RETIFICAM.get(tipo, "ato")


# ------------------------------------------- o credor que o registro diz


def _rotulos_do_credor() -> dict[str, str]:
    """Os pedaços da peça «credor» do PADRÃO — o que o livro lavra. Só lê."""
    import protesto_pecas as PECAS
    rot = PECAS.vocabulario(None, "PT_INSTRUMENTO_DESCRICAO")
    com_doc = rot["credor_com_documento"]
    sem_doc = rot["credor"]
    return {
        "prefixo": sem_doc.split("{credor}", 1)[0],
        "meio": com_doc.split("{credor}", 1)[1].split("{documento}", 1)[0],
        "registro": rot["registro"].split("{", 1)[0].strip(),
        # a peça que vem DEPOIS do credor, no registro e no termo do
        # cancelamento: a do devedor, que o art. 21, § 4º, não deixa faltar
        "devedor": rot["devedor"].split("{", 1)[0].strip(),
    }


def registro_qualificado(teor: Any) -> bool:
    """O texto traz a qualificação do registro (LD04, 21/10/2026)? Só o termo
    qualificado escreve o credor — o do acervo do E-Ofício não tem texto, e
    o anterior ao LD04 não tinha a qualificação. Só calcula."""
    marca = _rotulos_do_credor()["registro"]
    return bool(marca) and marca in _corrido(teor)


def credor_no_registro(teor: Any) -> str | None:
    """O credor que o texto lavrado escreveu, ou None se ele não escreveu
    credor nenhum. Só calcula.

    A PEÇA VAI do fim do rótulo («Credor (sacador/favorecido): ») até a peça
    seguinte, a do devedor («Devedor: ») — e não até o primeiro ponto: «S. A.»
    tem ponto no meio do nome. Dentro dela, o nome vai até o documento
    («, CPF/CNPJ »), ou até o ponto que fecha a peça. É leitura do texto que o
    próprio sistema escreveu com a peça do padrão — e mesmo assim serve só de
    SUGESTÃO: quem lavra confere, e `lavrar` exige que o que se diz errado
    esteja escrito no texto.
    """
    r = _rotulos_do_credor()
    texto = _corrido(teor)
    i = texto.find(r["prefixo"])
    if i < 0:
        return None
    resto = texto[i + len(r["prefixo"]):]
    fim = resto.find(" " + r["devedor"]) if r["devedor"] else -1
    if fim >= 0:
        pedaco = resto[:fim]
    else:                       # texto fora do padrão: até o primeiro ponto
        k = resto.find(". ")
        pedaco = resto[:k + 1] if k >= 0 else resto
    pedaco = pedaco.strip()
    j = pedaco.find(r["meio"])
    if j >= 0:
        nome = pedaco[:j]
    else:
        nome = pedaco[:-1] if pedaco.endswith(".") else pedaco
    return nome.strip() or None


def credor_do_cadastro(titulo: dict) -> str:
    """O credor como o registro o escreve — nome e, havendo, o documento com o
    mesmo separador da peça. Vazio sem credor no cadastro. Só calcula."""
    nome = _corrido((titulo or {}).get("cedente_nome"))
    if not nome:
        return ""
    doc = _corrido((titulo or {}).get("cedente_documento"))
    return f"{nome}{_rotulos_do_credor()['meio']}{doc}" if doc else nome


def divergencia_do_credor(con, ato: dict) -> dict | None:
    """O registro (ou o termo do cancelamento) diz um credor diferente do
    cadastro — ou nenhum — e ainda não há averbação que o corrija? Só LÊ.

    Devolve a sugestão da averbação (`forma`, `constava`, `correto`,
    `elemento`) ou None. Só olha o texto QUALIFICADO (o que escreve credor), e
    só quando o cadastro tem credor: sem ele não há o que fazer constar.

    A última averbação do credor vale como o texto de hoje: o que ela fez
    constar é o que «consta», e é contra isso que o cadastro se compara.
    """
    if not ato or str(ato.get("tipo") or "") not in ATOS_QUE_SE_RETIFICAM:
        return None
    if int(ato.get("cancelado") or 0) or not registro_qualificado(ato.get("teor")):
        return None
    titulo = banco(con).um("SELECT * FROM pt_titulos WHERE id = %s",
                           (int(ato["titulo_id"]),))
    nome = _corrido((titulo or {}).get("cedente_nome"))
    if not nome:
        return None
    correto = credor_do_cadastro(titulo)
    anteriores = [a for a in averbacoes_do_ato(con, int(ato["id"]),
                                                int(ato["titulo_id"]))
                  if _normal(a["elemento"]) == _normal(ELEMENTO_CREDOR)]
    if anteriores:
        consta = anteriores[-1]["correto"]
        forma = ERRADO
    else:
        consta = credor_no_registro(ato.get("teor"))
        forma = OMITIDO if consta is None else ERRADO
    if consta is not None and _normal(consta) in (_normal(nome), _normal(correto)):
        return None
    return {"ato_id": int(ato["id"]), "titulo_id": int(ato["titulo_id"]),
            "tipo": ato.get("tipo"), "nome_do_ato": nome_do_ato(ato),
            "forma": forma, "elemento": ELEMENTO_CREDOR,
            "constava": consta or "", "correto": correto}


def divergencias_do_titulo(con, titulo_id: int) -> list[dict]:
    """As divergências do credor em todos os atos lavrados do título. Só LÊ."""
    saida = []
    for ato in atos_que_se_retificam(con, titulo_id):
        achado = divergencia_do_credor(con, {**ato, "cancelado": 0})
        if achado:
            saida.append(achado)
    return saida


# --------------------------------------------------------------- lavrar


def _texto_vigente(con, ato: dict) -> str:
    """O texto lavrado mais o das averbações que já o corrigiram — o que se
    lê hoje naquele registro. Só LÊ."""
    partes = [ato.get("teor") or ""]
    partes += [a["teor"] for a in averbacoes_do_ato(con, int(ato["id"]),
                                                     int(ato["titulo_id"]))]
    return _normal(" ".join(partes))


def _validar_afirmacao(afirmo: Any, afirmacao: Any) -> str:
    """O contrato comum da afirmação expressa — a mesma régua da correção de
    ofício da situação. Obrigatória aqui. Só calcula."""
    import protesto_selo_previo as PSELO
    try:
        texto = PSELO.validar_afirmacao(afirmo, afirmacao)
    except PSELO.SituacaoError as erro:
        raise AverbacaoError(str(erro)) from erro
    if texto is None:
        raise AverbacaoError(
            "A averbação de retificação de ofício exige a afirmação expressa "
            "do oficial: marque «Afirmo» e escreva por quê, com pelo menos "
            f"{PSELO.MINIMO_DE_LETRAS_DA_AFIRMACAO} letras, começando por "
            f"«{PSELO.MODELO_DA_AFIRMACAO}». Ela fica gravada no ato e na "
            "auditoria, com o seu nome.")
    return texto


def preparar(con, ato_id: Any, *, elemento: Any, constava: Any, correto: Any,
             afirmo: Any, afirmacao: Any, agora: str, usuario: str | None,
             papel: Any, eh_robo: Any, titulo_id: int | None = None,
             modelo: str | None = None, travar: bool = True) -> dict:
    """Confere tudo o que a averbação exige e monta o teor dela. NÃO GRAVA.

    É a metade de `lavrar` que decide — e por isso o script que mede antes de
    gravar a usa com `travar=False`, numa transação só-leitura: o que ele
    mostra é o que `lavrar` gravaria, pela mesma régua, e não uma cópia
    parecida. Com `travar=True` (o padrão, o de `lavrar`) o título e o ato
    ficam presos até o fim da transação, na ordem da casa.

    `constava` vazio é a OMISSÃO (o texto não escreveu o elemento); com
    texto, é o ERRO, e o que se diz errado tem de estar escrito no registro
    (ou na última averbação dele): averbação retifica o que está lá, e não o
    que alguém acha que estava. `correto` é o que passa a constar.
    """
    import protesto as PT
    import protesto_termo as TERMO

    if bool(eh_robo) or str(papel or "").strip().upper() != PAPEL_QUE_LAVRA:
        raise AverbacaoError(
            "A averbação de retificação de ofício é ato do Tabelião (Lei "
            "9.492/1997, art. 25: «sob responsabilidade do Tabelião»): só o "
            "oficial, em pessoa, a lavra. Conta de robô não lavra.")
    texto_da_afirmacao = _validar_afirmacao(afirmo, afirmacao)

    bd = banco(con)
    try:
        ato_id = int(ato_id)
    except (TypeError, ValueError):
        raise AverbacaoError("Escolha o ato lavrado que se retifica.") from None
    ato = bd.um("SELECT id, titulo_id FROM pt_atos WHERE id = %s", (ato_id,))
    if not ato:
        raise AverbacaoError(f"Não há ato {ato_id} neste sistema.")
    if titulo_id is not None and int(ato["titulo_id"]) != int(titulo_id):
        raise AverbacaoError(f"O ato {ato_id} é de outro título.")
    if travar:
        # AS TRAVAS NA ORDEM DA CASA: o título primeiro, o ato depois.
        tit = PT.titulo_para_gravar(con, int(ato["titulo_id"]))
        bd._escrita()
        ato = dict(bd.um("SELECT * FROM pt_atos WHERE id = %s FOR UPDATE",
                         (ato_id,)))
    else:
        tit = PT.titulo(con, int(ato["titulo_id"]))
        ato = dict(bd.um("SELECT * FROM pt_atos WHERE id = %s", (ato_id,)))
    if ato["tipo"] not in ATOS_QUE_SE_RETIFICAM:
        raise AverbacaoError(
            f"O ato {ato_id} é {ato['tipo']}, e a averbação de retificação "
            f"alcança o texto lavrado do protesto ou do cancelamento.")
    if int(ato["cancelado"] or 0):
        raise AverbacaoError(
            f"O ato {ato_id} foi anulado — não existe registro a retificar.")
    if not str(ato.get("teor") or "").strip():
        raise AverbacaoError(
            f"O ato {ato_id} não tem texto lavrado neste sistema (o do acervo "
            f"do E-Ofício está no livro de papel): não há o que averbar aqui.")

    el = _corrido(elemento)
    antes = _corrido(constava)
    certo = _corrido(correto)
    if not 3 <= len(el) <= TETO_DO_ELEMENTO:
        raise AverbacaoError(
            "Diga o que se retifica (o elemento, com o artigo — por exemplo "
            f"«{ELEMENTO_CREDOR}»), em até {TETO_DO_ELEMENTO} letras.")
    if not certo:
        raise AverbacaoError("Escreva o que passa a constar.")
    if len(certo) > TETO_DO_VALOR or len(antes) > TETO_DO_VALOR:
        raise AverbacaoError(
            f"O que constou e o que passa a constar cabem em {TETO_DO_VALOR} "
            f"letras cada.")
    if antes and _normal(antes) == _normal(certo):
        raise AverbacaoError(
            "O que constou e o que passa a constar são o mesmo — não há erro "
            "a retificar.")
    vigente = _texto_vigente(con, ato)
    if antes and _normal(antes) not in vigente:
        raise AverbacaoError(
            f"«{antes}» não está escrito no {nome_do_ato(ato)} nem nas "
            f"averbações dele. A averbação retifica o que está lavrado: copie "
            f"o que o texto diz, ou deixe em branco se ele omitiu o elemento.")
    anteriores = averbacoes_do_ato(con, ato_id, int(ato["titulo_id"]))
    if not antes and _normal(el) == _normal(ELEMENTO_CREDOR):
        # A OMISSÃO DO CREDOR SE CONFERE PELA PEÇA, e não pelo nome solto: o
        # nome do credor pode estar no texto como APRESENTANTE — medido em
        # 29/10/2026, três títulos em que o credor é o próprio apresentante, e
        # o termo sem a peça «Credor». Texto com a peça (ou averbação anterior
        # do credor) é erro a retificar, e não omissão a suprir.
        ja = ([a["correto"] for a in anteriores
               if _normal(a["elemento"]) == _normal(ELEMENTO_CREDOR)]
              or [credor_no_registro(ato.get("teor"))])[-1]
        if ja:
            raise AverbacaoError(
                f"O {nome_do_ato(ato)} já indica um credor («{ja}»): isso é "
                f"erro a retificar, e não omissão — escreva em «o que constou» "
                f"o que o texto diz.")
    for a in anteriores:
        if (_normal(a["elemento"]) == _normal(el)
                and _normal(a["correto"]) == _normal(certo)):
            raise AverbacaoError(
                f"Esta retificação já foi averbada em {a['data_br']} (ato "
                f"{a['id']}).")

    forma = ERRADO if antes else OMITIDO
    teor = TERMO.montar_averbacao_retificacao(
        modelo=modelo, data=agora, ato=nome_do_ato(ato), elemento=el,
        constava=antes, correto=certo,
        qualificacao_do_registro=TERMO.fatos_da_qualificacao(
            bd, int(ato["titulo_id"])))
    import protesto_selo_previo as PSELO
    registro = {"regra": REGRA_DA_AFIRMACAO, "afirmacao": texto_da_afirmacao,
                "o_que_faltava": (
                    "o requerimento do interessado — esta averbação é de "
                    "ofício, sob responsabilidade do Tabelião (Lei 9.492/1997, "
                    "art. 25)")}
    detalhe = {"ato_retificado_id": ato_id,
               "ato_retificado_tipo": ato["tipo"],
               "elemento": el, "constava": antes, "correto": certo,
               "forma": forma, "fundamento": FUNDAMENTO, "de_oficio": True,
               "lavrada_por": usuario or "",
               PSELO.CHAVE_NO_DETALHE: [registro]}
    return {"titulo_id": int(ato["titulo_id"]),
            "numero_titulo": (tit or {}).get("numero_titulo"),
            "ato_retificado_id": ato_id, "ato_retificado_tipo": ato["tipo"],
            "elemento": el, "constava": antes, "correto": certo,
            "forma": forma, "teor": teor, "afirmacao": registro,
            "detalhe": detalhe}


def lavrar(con, ato_id: Any, *, elemento: Any, constava: Any, correto: Any,
           afirmo: Any, afirmacao: Any, agora: str, usuario: str | None,
           papel: Any, eh_robo: Any, titulo_id: int | None = None,
           modelo: str | None = None) -> dict:
    """Lavra a averbação de retificação de erro material, de ofício. ESCREVE
    — chame dentro de `db.transaction()`.

    A conferência e o teor são os de `preparar`; aqui só se grava o ato
    novo, sem selo, sem lançamento no caixa e sem lugar em livro. Devolve o
    que a rota grava na auditoria (`para_a_auditoria`), FORA da transação,
    como manda a casa. O ato retificado não se toca.
    """
    feito = preparar(con, ato_id, elemento=elemento, constava=constava,
                     correto=correto, afirmo=afirmo, afirmacao=afirmacao,
                     agora=agora, usuario=usuario, papel=papel, eh_robo=eh_robo,
                     titulo_id=titulo_id, modelo=modelo, travar=True)
    detalhe = feito.pop("detalhe")
    novo = int(banco(con).escrever(
        """INSERT INTO pt_atos(titulo_id, tipo, data_ato, observacao,
               detalhe_json, teor, origem, criado_em, criado_por)
           VALUES (%s,%s,%s,%s,%s,%s,'MANUAL',%s,%s) RETURNING id""",
        (feito["titulo_id"], TIPO, agora, OBSERVACAO,
         json.dumps(detalhe, ensure_ascii=False), feito["teor"], agora,
         usuario))[0]["id"])
    return {"ato_id": novo, **feito}


def para_a_auditoria(feito: dict) -> list[tuple[str, str, int, dict]]:
    """As linhas de auditoria da averbação lavrada: a afirmação expressa (o
    contrato comum) e o ato. SEM NOME DE CREDOR: o que constou e o que passa a
    constar estão no próprio ato; a auditoria aponta para ele. Só calcula."""
    return [
        (AFX.ACAO, "pt_atos", int(feito["ato_id"]),
         dict(feito["afirmacao"])),
        (ACAO_DA_AUDITORIA, "pt_atos", int(feito["ato_id"]),
         {"titulo_id": feito["titulo_id"],
          "ato_retificado_id": feito["ato_retificado_id"],
          "ato_retificado_tipo": feito["ato_retificado_tipo"],
          "elemento": feito["elemento"], "forma": feito["forma"],
          "fundamento": FUNDAMENTO}),
    ]


# ----------------------------------------------- o que os papéis mencionam


def mencoes(con, titulo_id: int, *, ato_id: int | None = None) -> list[dict]:
    """O que o instrumento e a certidão dizem de cada averbação viva: a data,
    o elemento e o ato retificado. Só LÊ.

    Sem o que constou: o instrumento vai ao apresentante e a certidão a
    terceiros, e o «antes» desta casa foi, em geral, o nome de OUTRA pessoa —
    o devedor de outro título. Os dados certos já estão no papel, que os lê do
    cadastro; a menção diz que o registro foi retificado, e quando.
    """
    saida = []
    for a in averbacoes_do_titulo(con, titulo_id):
        if ato_id is not None and str(a["ato_retificado_id"]) != str(int(ato_id)):
            continue
        tipo = a["ato_retificado_tipo"]
        nome = ATOS_QUE_SE_RETIFICAM.get(tipo, "registro do protesto")
        saida.append({"id": a["id"], "data": a["data_ato"],
                      "elemento": a["elemento"], "ato": nome})
    return saida
