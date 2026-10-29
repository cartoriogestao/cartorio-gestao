"""A CONFERÊNCIA CENPROT × SISTEMA — o que a Central diz de cada pedido, e o
que esta casa diz do título.

Ordem do oficial em 29/10/2026: *o sistema tem de impedir que a mão de obra
erre; obrigação ligada a conduta; se a escrevente insistir no erro,
afirmação expressa com log.*

**O CASO QUE ORIGINOU ISTO, medido em 29/10/2026** (produção, só leitura):

    - o pedido de protesto 3597193 (título 350574/1, aqui o 9617, origem
      `CENPROT-PEDIDO:3597193`) está PAGO no portal da CENPROT desde
      27/10/2026 07h08, com «Comprovante TED liquidação» — alguém apertou o
      botão «Liquidação» do portal, que gera o boleto do repasse ao
      apresentante;
    - aqui o 9617 não tinha pagamento, repasse nem boleto, e foi PROTESTADO
      em 28/10;
    - o irmão 350574/2 (pedido 3597208, título 1355, pago no balcão em 11/08)
      continua «apontado / em andamento» na Central, sem liquidação;
    - os dois títulos têm o MESMO protocolo, o mesmo valor e o mesmo devedor,
      e o cedente gravado nos dois não bate com o do acervo do E-Ofício.

  O mais provável é a liquidação ter sido feita no pedido errado — e nada,
  nem aqui nem lá, avisou ninguém. O protesto saiu por cima de um «pago».

O QUE ESTE MÓDULO FAZ

    1. CONFERE (`consultar`): para cada título de origem CENPROT acha o número
       do pedido, pergunta à Central e guarda o que ela disse; `quadro` compara
       com a situação do título e diz o caminho de cada correção;
    2. TRAVA O PROTESTO (`trava_do_protesto`): antes de lavrar, a Central é
       consultada; se ela diz pago, liquidado, retirado ou cancelado — ou se
       não deu para conferir —, a escrevente só passa com AFIRMAÇÃO EXPRESSA,
       que fica no ato e na auditoria com o nome dela;
    3. REGISTRA A LIQUIDAÇÃO DO PORTAL (`registrar_liquidacao`), com a
       afirmação de qual título — porque a API não diz nada de liquidação.

O QUE ELE NÃO FAZ: CORRIGIR. Nenhuma função daqui lavra, desfaz, cancela,
paga ou manda coisa à Central (há teste que varre os nomes públicos). Cada
divergência vem com o caminho, e quem anda por ele é gente — é a regra do
CNIB pela quinta vez: avisar e preparar, ficando pendente o okay.

**A REDE NUNCA DENTRO DE `db.transaction()`.** `consultar` e
`trava_do_protesto` recebem `db` (e não `con`) pela mesma razão de
`cenprot_pendencias.baixar`: um `BEGIN IMMEDIATE` segurado por sessenta
segundos de rede põe todo outro balcão no `busy_timeout`. Lê-se numa
transação curta, fala-se com a Central fora, grava-se noutra transação curta.

**O QUE A API DIZ DE LIQUIDAÇÃO: NADA** — medido no `swagger.yaml` 2.1.0 em
29/10/2026. Os 21 caminhos não têm «liquid», «TED», «boleto», «repasse» nem
«comprovante»; o único eco de pagamento é o «Aguardando Pagamento» do status
da RENEGOCIAÇÃO, que é outra coisa. O `GET /pedidos/consulta` devolve do
pedido `ds_status`, `ocorrencia`, `ds_ocorrencia` e `dt_ocorrencia` — é por
eles que se vê «pago», **sem dizer se o pago veio de um D desta casa ou da
Liquidação do portal**. Por isso a liquidação se registra aqui, à mão, com
afirmação; e endpoint que o contrato não tem não se inventa.

**O TEOR DA CENTRAL NÃO SE GUARDA.** A resposta do `/pedidos/consulta` traz o
devedor inteiro (documento, endereço, telefone, e-mail) e o PDF do pedido em
base64; a conferência só precisa do status, do número, do valor e do
cedente. Guarda-se isso; o devedor só se COMPARA (o resultado é 1/0), e não
se escreve em lugar nenhum.
"""
from __future__ import annotations

import json
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Any

import cenprot_api as API
import centrais_cred as CRED
import cn_schema as CN
from bd_nativo import banco


class ConferenciaError(ValueError):
    """Erro de regra, com a frase pronta para o balcão.

    `sem_rede` diz que a recusa veio de não falar com a Central — o lote
    «A protestar» usa isso para não esperar a rede título a título.
    """

    def __init__(self, frase: str, *, regra: str | None = None,
                 sem_rede: bool = False):
        super().__init__(frase)
        self.regra = regra
        self.sem_rede = sem_rede


# ------------------------------------------------------- de onde vem o título

# O MESMO PREFIXO DE `cenprot_pendencias.PREFIXO_DA_ORIGEM_DO_PEDIDO` (há
# teste que exige os dois iguais). Não se importa de lá para este módulo não
# puxar o domínio das pendências inteiro só por uma constante.
PREFIXO_DA_ORIGEM_DO_PEDIDO = "CENPROT-PEDIDO:"

# «TAB» É A GESTÃO DE PEDIDOS DA CENPROT, e não um banco. MEDIDO na produção
# em 29/10/2026: 96 títulos com apresentante TAB — 93 de origem CENPROT (92
# trazidos do E-Ofício com chave `tbAvisoProtesto:*` e o 9617, de
# `CENPROT-PEDIDO:3597193`) e 3 de origem CRA (27/08/2026). Os três critérios
# juntos pegam os 96, e nenhum título de banco.
APRESENTANTE_DOS_PEDIDOS = "TAB"
ORIGEM_CENPROT = "CENPROT"

# ONDE MORA O NÚMERO DO PEDIDO, na ordem em que se procura. MEDIDO em
# 29/10/2026: `cra_identificacao` (o `tbSDT.Campo03` do E-Ofício) tem 15
# dígitos com zeros à esquerda em 95 dos 96 — `000000003597208` é o pedido
# 3597208 —, e o que falta é o 9617, que tem o número na origem.
FONTE_ORIGEM = "origem do título"
FONTE_CRA = "identificação do E-Ofício"
FONTE_PENDENCIA = "pendência da CENPROT amarrada"

# ------------------------------------------------- o que a Central diz

# O ESTADO DO PEDIDO NA CENTRAL, normalizado. A Central não publica a lista
# de `ds_status` (o contrato só dá o exemplo «Apontado / em andamento»), e
# por isso se lê PRIMEIRO o código da ocorrência — que é o da CRA, medido no
# exemplo do contrato: `ocorrencia: Protestado`, `ds_ocorrencia: '2'` — e
# depois as palavras.
EM_ANDAMENTO = "EM_ANDAMENTO"
PROTESTADO = "PROTESTADO"
PAGO = "PAGO"
LIQUIDADO = "LIQUIDADO"
RETIRADO = "RETIRADO"
CANCELADO = "CANCELADO"
SUSTADO = "SUSTADO"
DEVOLVIDO = "DEVOLVIDO"
DESCONHECIDO = "DESCONHECIDO"

NOME_DO_ESTADO: dict[str, str] = {
    EM_ANDAMENTO: "apontado / em andamento",
    PROTESTADO: "protestado",
    PAGO: "pago",
    LIQUIDADO: "liquidado",
    RETIRADO: "retirado",
    CANCELADO: "cancelado",
    SUSTADO: "sustado",
    DEVOLVIDO: "devolvido",
    DESCONHECIDO: "não sei ler",
}

# O CÓDIGO DA OCORRÊNCIA É O DA CRA (`protesto_cra.OCORRENCIAS`): 0 apontamento,
# 1 pago, 2 protestado, 3 retirado, 4 sustado, 5 devolvido, 7 liquidação em
# condicional, A protesto cancelado.
ESTADO_DO_CODIGO: dict[str, str] = {
    "0": EM_ANDAMENTO, "1": PAGO, "2": PROTESTADO, "3": RETIRADO,
    "4": SUSTADO, "5": DEVOLVIDO, "7": LIQUIDADO, "A": CANCELADO,
}

# AS PALAVRAS, quando o código não vem. **«Aguardando Pagamento» NÃO é pago**
# — é o status da renegociação na mesma API —, e por isso «pago» se procura
# como palavra inteira, e «aguard» conta como em andamento.
PALAVRAS_DO_ESTADO: tuple[tuple[str, str], ...] = (
    (CANCELADO, r"\bcancelad[oa]s?\b"),
    (LIQUIDADO, r"\bliquidad[oa]s?\b"),
    (PAGO, r"\bpag[oa]s?\b|\bquitad[oa]s?\b"),
    (RETIRADO, r"\bretirad[oa]s?\b|\bdesist"),
    (SUSTADO, r"\bsustad|\bsuspens"),
    (DEVOLVIDO, r"\bdevolvid|\birregular"),
    (PROTESTADO, r"\bprotestad[oa]s?\b"),
    (EM_ANDAMENTO, r"\bapontad|\bandamento\b|\bintimad|\bprotocolad|\baguard"),
)

# QUANDO DUAS LEITURAS BRIGAM, ganha a que tira o título do protesto. É a
# leitura conservadora para a trava: dizer «pode protestar» sobre um «pago»
# é o erro do 350574/1; dizer «confira» sobre um «protestado» custa um clique.
PRIORIDADE_DO_ESTADO: tuple[str, ...] = (
    CANCELADO, LIQUIDADO, PAGO, RETIRADO, SUSTADO, DEVOLVIDO, PROTESTADO,
    EM_ANDAMENTO)

# OS QUE TIRAM O TÍTULO DO PROTESTO, do lado da Central.
ESTADOS_QUE_ENCERRAM: frozenset[str] = frozenset({
    PAGO, LIQUIDADO, RETIRADO, CANCELADO, DEVOLVIDO})

# ------------------------------------------- a situação aqui

ABERTAS = frozenset({"RECEBIDO", "APONTADO", "INTIMADO"})
# O ATO QUE TIROU O TÍTULO DO PROTESTO AQUI, por situação — é ele que o XML D
# leva à Central (`protesto_cenprot_xml.LETRA_DO_ATO`).
ATO_DA_SAIDA: dict[str, str] = {
    "PAGO": "PAGAMENTO", "DESISTIDO": "DESISTENCIA", "RETIRADO": "DESISTENCIA",
    "CANCELADO": "CANCELAMENTO"}
# O QUE CADA SITUAÇÃO DAQUI ESPERA LER NA CENTRAL quando as duas concordam.
ESPERADO_NA_CENTRAL: dict[str, frozenset] = {
    "PAGO": frozenset({PAGO, LIQUIDADO}),
    "DESISTIDO": frozenset({RETIRADO}),
    "RETIRADO": frozenset({RETIRADO}),
    "CANCELADO": frozenset({CANCELADO}),
    "DEVOLVIDO": frozenset({DEVOLVIDO}),
}

# --------------------------------------------------- o que se guarda

# A CONSULTA. `ACHOU` e `NAO_ACHOU` são respostas da Central; `SEM_PEDIDO` é
# a casa não saber o número. «Sem rede» não é resultado: a falha vai em
# `erro`/`tentada_em`, e o que a Central disse da última vez fica de pé.
ACHOU = "ACHOU"
NAO_ACHOU = "NAO_ACHOU"
SEM_PEDIDO = "SEM_PEDIDO"

# O PESO DE CADA ACHADO. `DIVERGE` conta no painel; `CONFERIR` aparece na
# tela e não conta — é o que pode ser só o atraso do arquivo do dia.
DIVERGE = "DIVERGE"
CONFERIR = "CONFERIR"

# ------------------------------------------- a afirmação expressa

# O CONTRATO COMUM DA CASA (29/10/2026 — outros PRs do mesmo dia usam o MESMO):
# caixa `afirmo` + texto `afirmacao` com pelo menos 30 letras, auditoria
# `AFIRMACAO_EXPRESSA` com `regra`, `afirmacao` e `o_que_faltava`, e o texto
# no `detalhe_json` do ato.
ACAO_DA_AUDITORIA = "AFIRMACAO_EXPRESSA"
REGRA_NAO_CONFERIDO = "PROTESTO_CENPROT_NAO_CONFERIDO"
REGRA_DIVERGENTE = "PROTESTO_CENPROT_DIVERGENTE"
REGRA_LIQUIDACAO = "CENPROT_LIQUIDACAO_NO_PORTAL"
MINIMO_DE_LETRAS_DA_AFIRMACAO = 30
MODELO_DA_AFIRMACAO = "Afirmo, sob minha responsabilidade, que…"
# A CHAVE NO `detalhe_json` É UMA LISTA, e não um texto: o mesmo ato pode
# precisar de duas afirmações (a desta trava e a da prova da intimação), e
# uma chave só faria a segunda apagar a primeira.
CHAVE_NO_DETALHE = "afirmacoes_expressas"
MINIMO_DO_MOTIVO = 10


# =================================================================== cálculo


def _txt(v: Any) -> str:
    return str(v if v is not None else "").strip()


def _digitos(v: Any) -> str:
    return "".join(c for c in str(v or "") if c.isdigit())


def _sem_acento(texto: Any) -> str:
    base = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in base if not unicodedata.combining(c))


def _nome_comparavel(texto: Any) -> str:
    """CAIXA, ACENTO E PONTUAÇÃO NÃO SÃO DIVERGÊNCIA. Só calcula."""
    limpo = re.sub(r"[^A-Z0-9]+", " ", _sem_acento(texto).upper())
    return " ".join(limpo.split())


def _numero_comparavel(texto: Any) -> str:
    """`350574/1`, `350574-1` e `0003505741` são o mesmo número. Só calcula."""
    return re.sub(r"[^A-Z0-9]", "", _sem_acento(texto).upper()).lstrip("0")


def _centavos(valor: Any) -> int | None:
    if valor in (None, ""):
        return None
    try:
        return int((Decimal(str(valor).replace(",", ".")) * 100)
                   .to_integral_value())
    except (InvalidOperation, ValueError):
        return None


def _br(iso: Any) -> str:
    s = _txt(iso)[:10]
    return f"{s[8:10]}/{s[5:7]}/{s[:4]}" if len(s) == 10 and s[4] == "-" else s


def e_de_origem_cenprot(titulo: dict) -> bool:
    """O título veio da Gestão de Pedidos da CENPROT? Só calcula."""
    return (_txt(titulo.get("apresentante_codigo")).upper() == APRESENTANTE_DOS_PEDIDOS
            or _txt(titulo.get("origem")).upper() == ORIGEM_CENPROT
            or _txt(titulo.get("origem_chave")).startswith(PREFIXO_DA_ORIGEM_DO_PEDIDO))


def pedidos_do_titulo(titulo: dict, *, da_pendencia: Any = None) -> list[tuple[str, str]]:
    """Os números do pedido que o título traz, com de onde saiu cada um. Só
    calcula.

    Devolve a lista SEM repetição, na ordem de confiança. **Dois números
    diferentes no mesmo título é achado**, e não se escolhe um no escuro: a
    conferência usa o primeiro e mostra o outro.
    """
    achados: list[tuple[str, str]] = []
    origem = _txt(titulo.get("origem_chave"))
    if origem.startswith(PREFIXO_DA_ORIGEM_DO_PEDIDO):
        n = _digitos(origem[len(PREFIXO_DA_ORIGEM_DO_PEDIDO):]).lstrip("0")
        if n:
            achados.append((n, FONTE_ORIGEM))
    cra = _txt(titulo.get("cra_identificacao"))
    # SÓ SE FOR NÚMERO INTEIRO: nos títulos de banco o mesmo campo guarda o
    # «seu número» do apresentante, e ali ele não é pedido nenhum — por isso
    # isto só se lê de título de origem CENPROT.
    if cra.isdigit() and cra.lstrip("0"):
        achados.append((cra.lstrip("0"), FONTE_CRA))
    pend = _digitos(da_pendencia).lstrip("0")
    if pend:
        achados.append((pend, FONTE_PENDENCIA))
    vistos: set[str] = set()
    fora = []
    for numero, fonte in achados:
        if numero not in vistos:
            vistos.add(numero)
            fora.append((numero, fonte))
    return fora


def estado_da_central(status: Any, ocorrencia: Any, codigo: Any) -> str:
    """Lê o que a Central disse do pedido. Só calcula.

    O código da ocorrência (o da CRA) e as palavras do status e da ocorrência
    contam juntos; quando brigam, ganha o que tira o título do protesto
    (`PRIORIDADE_DO_ESTADO`). Nada que se reconheça é `DESCONHECIDO` — e
    desconhecido, para a trava, é «não deu para conferir».
    """
    achados: set[str] = set()
    cod = _txt(codigo).upper()
    if cod in ESTADO_DO_CODIGO:
        achados.add(ESTADO_DO_CODIGO[cod])
    texto = _sem_acento(f"{_txt(status)} {_txt(ocorrencia)}").lower()
    for estado, padrao in PALAVRAS_DO_ESTADO:
        if re.search(padrao, texto):
            achados.add(estado)
    for estado in PRIORIDADE_DO_ESTADO:
        if estado in achados:
            return estado
    return DESCONHECIDO


def _blocos(valor: Any) -> list[dict]:
    if isinstance(valor, dict):
        return [valor]
    if isinstance(valor, list):
        return [v for v in valor if isinstance(v, dict)]
    return []


def _lista_da_resposta(resposta: Any) -> list[dict]:
    """A lista de pedidos, venha ela crua ou embrulhada (a mesma API responde
    das duas formas — `cenprot_pendencias._lista_da_resposta`)."""
    if isinstance(resposta, list):
        return [i for i in resposta if isinstance(i, dict)]
    if isinstance(resposta, dict):
        for chave in ("data", "dados", "pedidos", "items", "resultado"):
            if isinstance(resposta.get(chave), list):
                return [i for i in resposta[chave] if isinstance(i, dict)]
        if "dados_pedido" in resposta:
            return [resposta]
    return []


def _o_pedido_na_resposta(resposta: Any, numero: str) -> dict | None:
    """O item daquele pedido. **Um item só e sem número serve; vários sem o
    número pedido, não** — escolher um no escuro seria conferir o título
    contra o pedido de outro."""
    itens = _lista_da_resposta(resposta)
    com_numero = [i for i in itens
                  if _digitos((i.get("dados_pedido") or {}).get(
                      "cd_pedido_protesto")).lstrip("0") == numero]
    if com_numero:
        return com_numero[0]
    sem_numero = [i for i in itens
                  if not _digitos((i.get("dados_pedido") or {}).get(
                      "cd_pedido_protesto"))]
    if len(itens) == 1 and sem_numero:
        return itens[0]
    return None


def o_que_a_central_disse(item: dict, titulo: dict,
                          documentos_dos_devedores: set[str]) -> dict:
    """Os campos da conferência, tirados do pedido da Central. Só calcula.

    **O DEVEDOR SÓ SE COMPARA**: o resultado é 1 (confere), 0 (não confere)
    ou None (não deu para comparar), e o documento dele não sai daqui.
    """
    dp = item.get("dados_pedido") or {}
    tit = dp.get("dados_titulo") or item.get("dados_titulo") or {}
    ced = item.get("dados_cedente") or {}
    docs_da_central = {
        _digitos(d.get("nm_nr_identificacao"))
        for d in (_blocos(item.get("devedor")) + _blocos(item.get("devedores"))
                  + _blocos(item.get("codevedor")) + _blocos(item.get("codevedores")))
    } - {""}
    devedor_confere = None
    if docs_da_central and documentos_dos_devedores:
        devedor_confere = int(bool(docs_da_central & documentos_dos_devedores))
    nome_ced = _txt(ced.get("nm_cedente"))
    doc_ced = _digitos(ced.get("nm_nr_documento"))
    cedente_confere = None
    nosso_doc = _digitos(titulo.get("cedente_documento"))
    nosso_nome = _nome_comparavel(titulo.get("cedente_nome"))
    if doc_ced and nosso_doc:
        cedente_confere = int(doc_ced == nosso_doc)
    elif nome_ced and nosso_nome:
        dela = _nome_comparavel(nome_ced)
        cedente_confere = int(dela == nosso_nome or dela.startswith(nosso_nome)
                              or nosso_nome.startswith(dela))
    status = _txt(dp.get("ds_status"))
    ocorrencia = _txt(dp.get("ocorrencia"))
    codigo = _txt(dp.get("ds_ocorrencia"))
    return {
        "central_estado": estado_da_central(status, ocorrencia, codigo),
        "central_status": status or None,
        "central_ocorrencia": ocorrencia or None,
        "central_codigo": codigo or None,
        "central_data": _txt(dp.get("dt_ocorrencia"))[:10] or None,
        "central_protocolo": _txt(dp.get("nm_nr_protocolo")) or None,
        "central_numero_titulo": _txt(tit.get("nm_nr_titulo")) or None,
        "central_valor_centavos": _centavos(tit.get("vl_titulo")),
        "central_cedente": nome_ced or None,
        "central_cedente_confere": cedente_confere,
        "central_devedor_confere": devedor_confere,
    }


# =================================================================== leitura


def _filtro() -> tuple[str, tuple]:
    return ("(UPPER(TRIM(COALESCE(t.apresentante_codigo, ''))) = %s "
            "OR t.origem = %s OR t.origem_chave LIKE %s)",
            (APRESENTANTE_DOS_PEDIDOS, ORIGEM_CENPROT,
             PREFIXO_DA_ORIGEM_DO_PEDIDO + "%"))


def _titulos(con: Any, titulo_id: int | None = None) -> list[dict]:
    """Os títulos de origem CENPROT (ou um deles). Só LÊ — e sem devedor."""
    onde, valores = _filtro()
    sql = (f"""SELECT t.id, t.numero_titulo, t.protocolo, t.situacao,
                      t.origem, t.origem_chave, t.cra_identificacao,
                      t.apresentante_codigo, t.valor_centavos,
                      t.cedente_nome, t.cedente_documento
                 FROM pt_titulos t WHERE {onde}""")
    params = list(valores)
    if titulo_id is not None:
        sql += " AND t.id = %s"
        params.append(int(titulo_id))
    return [dict(r) for r in banco(con).ler(sql + " ORDER BY t.id", params)]


def _documentos_dos_devedores(con: Any, titulo_id: int | None = None) -> dict[int, set]:
    """Os documentos dos devedores, só para comparar. Só LÊ."""
    onde, valores = _filtro()
    sql = (f"""SELECT d.titulo_id, d.documento_numero FROM pt_devedores d
                 JOIN pt_titulos t ON t.id = d.titulo_id WHERE {onde}""")
    params = list(valores)
    if titulo_id is not None:
        sql += " AND t.id = %s"
        params.append(int(titulo_id))
    fora: dict[int, set] = {}
    for r in banco(con).ler(sql, params):
        doc = _digitos(r["documento_numero"])
        if doc:
            fora.setdefault(int(r["titulo_id"]), set()).add(doc)
    return fora


def _pedidos_das_pendencias(con: Any) -> dict[int, str]:
    linhas = banco(con).ler(
        """SELECT titulo_id, codigo FROM cn_pendencias
            WHERE especie = %s AND ambiente = %s AND titulo_id IS NOT NULL
            ORDER BY id""", (CN.PEDIDO_PROTESTO, CRED.PRODUCAO))
    return {int(r["titulo_id"]): _txt(r["codigo"]) for r in linhas}


def _atos(con: Any) -> dict[int, dict[str, dict]]:
    """O último ato vivo de cada tipo que importa, por título. Só LÊ.

    Junto vem o arquivo XML da CENPROT em que ele subiu, quando subiu — é a
    diferença entre «o D não saiu» e «o D saiu e a Central não o leu».
    """
    onde, valores = _filtro()
    linhas = banco(con).ler(
        f"""SELECT a.id, a.titulo_id, a.tipo, a.data_ato, a.origem,
                   a.cenprot_xml_id, x.nome_arquivo AS xml_nome,
                   x.gerado_em AS xml_gerado_em
              FROM pt_atos a
              JOIN pt_titulos t ON t.id = a.titulo_id
              LEFT JOIN pt_cenprot_xml x ON x.id = a.cenprot_xml_id
             WHERE a.cancelado = 0
               AND a.tipo IN ('PAGAMENTO', 'DESISTENCIA', 'CANCELAMENTO', 'PROTESTO')
               AND {onde}
             ORDER BY a.id""", valores)
    fora: dict[int, dict[str, dict]] = {}
    for r in linhas:
        fora.setdefault(int(r["titulo_id"]), {})[r["tipo"]] = dict(r)
    return fora


def _protocolos_repetidos(con: Any) -> dict[int, list[dict]]:
    """Os outros títulos (de qualquer origem) com o mesmo protocolo. Só LÊ.

    MEDIDO em 29/10/2026: entre os 96 de origem CENPROT, um par só — 1355 e
    9617 —, e é o par do 350574. O protocolo é AAMMDD + sequencial do dia;
    dois títulos com o mesmo número é defeito de dado, e é o tipo de defeito
    que faz o pagamento de um ir parar no outro.
    """
    onde, valores = _filtro()
    linhas = banco(con).ler(
        f"""SELECT t.id, o.id AS outro, o.numero_titulo AS outro_numero
              FROM pt_titulos t
              JOIN pt_titulos o ON o.protocolo = t.protocolo AND o.id <> t.id
             WHERE {onde} AND TRIM(COALESCE(t.protocolo, '')) <> ''
             ORDER BY t.id, o.id""", valores)
    fora: dict[int, list[dict]] = {}
    for r in linhas:
        fora.setdefault(int(r["id"]), []).append(
            {"id": int(r["outro"]), "numero_titulo": r["outro_numero"]})
    return fora


def _conferencias(con: Any) -> dict[int, dict]:
    linhas = banco(con).ler(
        "SELECT * FROM cn_conferencias WHERE ambiente = %s", (CRED.PRODUCAO,))
    return {int(r["titulo_id"]): dict(r) for r in linhas}


def liquidacoes(con: Any) -> list[dict]:
    """As liquidações do portal registradas aqui, vivas e anuladas. Só LÊ."""
    return [dict(r) for r in banco(con).ler(
        """SELECT l.*, t.numero_titulo, t.situacao AS titulo_situacao
             FROM cn_liquidacoes_portal l
             LEFT JOIN pt_titulos t ON t.id = l.titulo_id
            ORDER BY l.id DESC""")]


# ================================================================= avaliação


def _rotulo(t: dict) -> str:
    numero = _txt(t.get("numero_titulo"))
    return f"{numero} (título {t['id']})" if numero else f"título {t['id']}"


def _achado(regra: str, nivel: str, frase: str, caminho: str, *,
            trava: bool = False) -> dict:
    return {"regra": regra, "nivel": nivel, "frase": frase,
            "caminho": caminho, "trava": trava}


def _o_que_a_central_disse_em_frase(c: dict) -> str:
    partes = [f"«{c[k]}»" for k in ("central_status", "central_ocorrencia")
              if c.get(k)]
    texto = " / ".join(partes) or "sem status"
    if c.get("central_codigo"):
        texto += f" (ocorrência {c['central_codigo']})"
    if c.get("central_data"):
        texto += f" em {_br(c['central_data'])}"
    return texto


def _caminho_do_d(ato: dict | None, pedido: str) -> str:
    """O que fazer quando a Central não sabe que o título saiu daqui."""
    if not ato:
        return ("Não há ato vivo que explique a situação deste título — abra a "
                "ficha e confira a vida dele antes de qualquer outra coisa.")
    quando = _br(ato.get("data_ato"))
    if _txt(ato.get("origem")).upper() == "EOFICIO":
        return (f"O ato ({ato['tipo'].lower()} de {quando}) veio do E-Ofício, "
                f"que mandava o D por conta própria — e a Central não o tem. O "
                f"XML desta casa não reenvia ato do E-Ofício: confira no portal "
                f"da CENPROT (Gestão de Pedidos → pedido {pedido}) e informe "
                f"por lá.")
    if ato.get("cenprot_xml_id"):
        return (f"O D saiu no arquivo {ato.get('xml_nome') or ato['cenprot_xml_id']}"
                f" ({_br(ato.get('xml_gerado_em'))}) e a Central ainda não o "
                f"leu: confira no portal da CENPROT se o arquivo foi subido e "
                f"aceito.")
    return (f"O D deste {ato['tipo'].lower()} ({quando}) ainda não saiu: gere-o "
            f"em Protesto → XML da CENPROT (letra D) e suba-o pelo portal.")


def avaliar(t: dict, conf: dict | None, *, pedidos: list[tuple[str, str]],
            atos: dict[str, dict], liquidacoes_vivas: list[dict],
            dono_do_pedido: dict[str, list[int]],
            repetidos: list[dict], titulos_por_id: dict[int, dict]) -> list[dict]:
    """Os achados de UM título. Só calcula — quem lê o banco é `quadro`.

    `trava` marca o que impede o protesto sem afirmação expressa.
    """
    achados: list[dict] = []
    rot = _rotulo(t)
    situacao = _txt(t.get("situacao")).upper()
    pedido = pedidos[0][0] if pedidos else ""

    # --- o número do pedido
    if not pedidos:
        achados.append(_achado(
            "SEM_PEDIDO", CONFERIR,
            f"Não se acha o número do pedido da CENPROT de {rot}: nem na origem "
            f"do título, nem na identificação do E-Ofício, nem numa pendência.",
            "Procure o pedido no portal da CENPROT (Gestão de Pedidos), pelo "
            "protocolo ou pelo devedor; sem o número a Central não se consulta."))
    elif len(pedidos) > 1:
        lista = "; ".join(f"{n} ({fonte})" for n, fonte in pedidos)
        achados.append(_achado(
            "PEDIDO_EM_DOIS_LUGARES", CONFERIR,
            f"{rot} traz mais de um número de pedido: {lista}. A conferência "
            f"usa o primeiro.",
            "Confira no portal qual é o pedido deste título; o outro número é "
            "defeito de dado a corrigir na ficha."))
    if pedido and len(dono_do_pedido.get(pedido, [])) > 1:
        outros = [i for i in dono_do_pedido[pedido] if i != t["id"]]
        achados.append(_achado(
            "PEDIDO_EM_DOIS_TITULOS", DIVERGE,
            f"O pedido {pedido} está em mais de um título desta casa: "
            f"{', '.join(_rotulo(titulos_por_id[i]) for i in outros)} e {rot}.",
            "Um pedido da CENPROT é um título. Confira no portal de qual deles é "
            "este pedido antes de lavrar ou pagar qualquer um dos dois.",
            trava=True))
    if repetidos:
        outros = ", ".join(
            f"{_txt(o.get('numero_titulo'))} (título {o['id']})" for o in repetidos)
        achados.append(_achado(
            "PROTOCOLO_EM_DOIS_TITULOS", DIVERGE,
            f"{rot} tem o mesmo protocolo ({_txt(t.get('protocolo'))}) que "
            f"{outros}. Protocolo é um por título.",
            "Pode ser o mesmo título entrado duas vezes. Compare as duas fichas "
            "com o pedido no portal e leve ao oficial antes de lavrar, pagar ou "
            "liquidar qualquer um dos dois.", trava=True))

    # --- o que a Central disse
    if conf and conf.get("resultado") == NAO_ACHOU:
        achados.append(_achado(
            "CENTRAL_NAO_ACHOU", CONFERIR,
            f"A CENPROT não devolveu o pedido {conf.get('pedido') or pedido} de "
            f"{rot} (consulta de {_br(conf.get('consultada_em'))}).",
            "Confira no portal se o número do pedido está certo; pedido que a "
            "Central não conhece não é deste título."))
    if conf and conf.get("resultado") == ACHOU:
        estado = _txt(conf.get("central_estado")) or DESCONHECIDO
        disse = _o_que_a_central_disse_em_frase(conf)
        quando = _br(conf.get("consultada_em"))
        nunca_pagou_aqui = "PAGAMENTO" not in atos
        if estado == DESCONHECIDO:
            achados.append(_achado(
                "CENTRAL_ILEGIVEL", CONFERIR,
                f"A CENPROT respondeu {disse} sobre o pedido {pedido}, e este "
                f"sistema não sabe ler isso (consulta de {quando}).",
                "Confira no portal o status do pedido; se for um status novo da "
                "Central, ele precisa entrar na leitura deste módulo."))
        elif estado in ESTADOS_QUE_ENCERRAM and (situacao in ABERTAS
                                                 or situacao == "PROTESTADO"):
            frase = (f"A CENPROT dá o pedido {pedido} por "
                     f"{NOME_DO_ESTADO[estado]} — {disse} — e aqui {rot} está "
                     f"{situacao}.")
            if estado in (PAGO, LIQUIDADO) and nunca_pagou_aqui:
                frase += (" Este sistema nunca lavrou pagamento deste título: o "
                          "«pago» da Central não veio de um D desta casa — o "
                          "mais provável é a Liquidação feita no portal neste "
                          "pedido.")
            if situacao == "PROTESTADO" and estado in (PAGO, LIQUIDADO):
                caminho = (
                    f"Confira no portal (Gestão de Pedidos → pedido {pedido}) o "
                    f"comprovante e de qual título é a liquidação. Se foi feita "
                    f"no pedido errado, peça à CENPROT a correção e registre "
                    f"abaixo a liquidação certa. Se o devedor pagou mesmo este "
                    f"título, leve ao oficial: o protesto lavrado só se desfaz "
                    f"por cancelamento, na ficha, com hipótese e fundamento — "
                    f"a decisão é dele.")
            elif situacao == "PROTESTADO" and estado == CANCELADO:
                caminho = (
                    "Veja se há pedido de cancelamento em Pendências da CENPROT; "
                    "o cancelamento se lavra na ficha do título, com a hipótese "
                    "do catálogo, e só depois se informa a Central.")
            elif situacao == "PROTESTADO":
                caminho = ("Leve ao oficial com o portal aberto no pedido: a "
                           "Central e o livro desta casa dizem coisas que não "
                           "cabem juntas.")
            elif estado in (PAGO, LIQUIDADO):
                caminho = (
                    f"NÃO PROTESTE. Confira o comprovante no portal (pedido "
                    f"{pedido}). Se o devedor pagou, lance o pagamento na "
                    f"ficha (o D sai no XML da CENPROT); se a liquidação foi "
                    f"no pedido errado, peça a correção à CENPROT.")
            elif estado == RETIRADO:
                caminho = ("NÃO PROTESTE. O apresentante retirou o pedido na "
                           "Central: lance a desistência na ficha do título (o "
                           "D sai no XML da CENPROT).")
            else:
                caminho = ("NÃO PROTESTE. Confira no portal o que aconteceu com "
                           "o pedido e leve ao oficial antes de lavrar.")
            achados.append(_achado(
                "CENTRAL_ENCERROU_" + estado, DIVERGE, frase, caminho,
                trava=True))
        elif estado == SUSTADO and situacao in ABERTAS:
            achados.append(_achado(
                "CENTRAL_SUSTADO", DIVERGE,
                f"A CENPROT dá o pedido {pedido} por sustado — {disse} — e "
                f"aqui {rot} está {situacao}.",
                "NÃO PROTESTE. Procure a ordem judicial (Pendências da CENPROT "
                "→ Decisão judicial) e registre a sustação na ficha do título.",
                trava=True))
        elif estado == SUSTADO and situacao == "PROTESTADO":
            achados.append(_achado(
                "CENTRAL_SUSTADO", CONFERIR,
                f"A CENPROT dá o pedido {pedido} por sustado — {disse} — e "
                f"aqui {rot} está PROTESTADO.",
                "Procure a ordem judicial (Pendências da CENPROT → Decisão "
                "judicial); depois do protesto, a ordem se registra na ficha "
                "como efeito suspensivo."))
        elif estado == PROTESTADO and situacao in ABERTAS:
            achados.append(_achado(
                "CENTRAL_JA_PROTESTADO", DIVERGE,
                f"A CENPROT já dá o pedido {pedido} por protestado — {disse} — "
                f"e aqui {rot} está {situacao}.",
                "NÃO PROTESTE de novo sem conferir: pode ser outro título desta "
                "casa com o mesmo pedido, e o protesto sairia em dobro.",
                trava=True))
        elif situacao in ESPERADO_NA_CENTRAL and estado in (EM_ANDAMENTO,
                                                            PROTESTADO):
            ato = atos.get(ATO_DA_SAIDA.get(situacao, ""))
            achados.append(_achado(
                "SAIU_AQUI_E_A_CENTRAL_NAO_SABE", DIVERGE,
                f"Aqui {rot} está {situacao}, e a CENPROT ainda dá o pedido "
                f"{pedido} por {NOME_DO_ESTADO[estado]} — {disse}.",
                _caminho_do_d(ato, pedido)
                + (f" Se o repasse ao apresentante ainda não saiu, ele sai pela "
                   f"Liquidação no portal, no pedido {pedido} — e, feita, "
                   f"registre-a abaixo." if situacao == "PAGO" else "")))
        elif (situacao in ESPERADO_NA_CENTRAL
              and estado in ESTADOS_QUE_ENCERRAM
              and estado not in ESPERADO_NA_CENTRAL[situacao]):
            achados.append(_achado(
                "SAIDAS_DIFERENTES", CONFERIR,
                f"Aqui {rot} está {situacao}, e a CENPROT dá o pedido {pedido} "
                f"por {NOME_DO_ESTADO[estado]} — {disse}.",
                "As duas dizem que o título saiu do protesto, por caminhos "
                "diferentes. Confira no portal qual é o certo."))
        elif situacao == "PROTESTADO" and estado == EM_ANDAMENTO:
            ato = atos.get("PROTESTO") or {}
            if ato and _txt(ato.get("origem")).upper() != "EOFICIO" \
                    and not ato.get("cenprot_xml_id"):
                caminho = ("O P deste protesto ainda não saiu: gere-o em "
                           "Protesto → XML da CENPROT (letra P) e suba-o pelo "
                           "portal.")
            else:
                caminho = ("Confira no portal se o P deste protesto chegou à "
                           "Central.")
            achados.append(_achado(
                "PROTESTO_QUE_A_CENTRAL_NAO_VIU", CONFERIR,
                f"Aqui {rot} está PROTESTADO, e a CENPROT ainda dá o pedido "
                f"{pedido} por apontado — {disse}.", caminho))

        # --- o pedido é deste título?
        nosso = _numero_comparavel(t.get("numero_titulo"))
        dela = _numero_comparavel(conf.get("central_numero_titulo"))
        if nosso and dela and nosso != dela:
            achados.append(_achado(
                "PEDIDO_DE_OUTRO_TITULO", DIVERGE,
                f"O pedido {pedido} da CENPROT é do título "
                f"{conf.get('central_numero_titulo')}, e aqui ele está amarrado "
                f"a {rot}.",
                "Confira no portal: o pedido pode estar amarrado ao título "
                "errado nesta casa. Nada se lavra, paga ou liquida neste título "
                "até isso se resolver.", trava=True))
        valor_dela = conf.get("central_valor_centavos")
        valor_nosso = t.get("valor_centavos")
        if valor_dela not in (None, "") and valor_nosso not in (None, "", 0) \
                and int(valor_dela) != int(valor_nosso):
            achados.append(_achado(
                "VALOR_DIFERENTE", DIVERGE,
                f"O pedido {pedido} vale R$ {int(valor_dela) / 100:.2f} na "
                f"CENPROT, e {rot} vale R$ {int(valor_nosso) / 100:.2f} aqui.",
                "Confira no portal e na imagem do título qual é o valor certo; "
                "valor diferente pode ser pedido de outro título.", trava=True))
        if conf.get("central_devedor_confere") == 0:
            achados.append(_achado(
                "DEVEDOR_DIFERENTE", DIVERGE,
                f"O devedor do pedido {pedido} na CENPROT não é nenhum dos "
                f"devedores de {rot} aqui (o documento não bate).",
                "Confira no portal: pedido de outro devedor é pedido de outro "
                "título.", trava=True))
        if conf.get("central_cedente_confere") == 0:
            achados.append(_achado(
                "CEDENTE_DIFERENTE", CONFERIR,
                f"O cedente do pedido {pedido} na CENPROT é "
                f"«{conf.get('central_cedente') or '—'}», e o de {rot} aqui é "
                f"«{_txt(t.get('cedente_nome')) or '—'}».",
                "Confira no pedido e na imagem do título qual é o cedente certo "
                "e corrija a ficha; o cedente vai no instrumento e no XML."))
        prot_dela = _txt(conf.get("central_protocolo"))
        prot_nosso = _txt(t.get("protocolo"))
        if prot_dela and prot_nosso and prot_dela != prot_nosso:
            achados.append(_achado(
                "PROTOCOLO_DIFERENTE", CONFERIR,
                f"A CENPROT tem o pedido {pedido} com o protocolo {prot_dela}, e "
                f"{rot} tem o protocolo {prot_nosso} aqui.",
                "Confira qual é o certo; o protocolo da Central é o que a casa "
                "devolveu pela pendência do pedido."))

    # --- a liquidação feita no portal
    for liq in liquidacoes_vivas:
        dono = int(liq["titulo_id"])
        numero = _txt(liq["pedido"])
        quando = _br(liq.get("liquidada_em") or liq.get("registrada_em"))
        if dono == t["id"] and pedido and numero != pedido:
            donos = [i for i in dono_do_pedido.get(numero, []) if i != t["id"]]
            de_quem = (f"; e o pedido {numero} é de "
                       + ", ".join(_rotulo(titulos_por_id[i]) for i in donos)
                       if donos else "")
            achados.append(_achado(
                "LIQUIDACAO_EM_PEDIDO_DE_OUTRO_TITULO", DIVERGE,
                f"Registrou-se a liquidação no portal do pedido {numero} "
                f"({quando}) afirmando ser de {rot} — mas o pedido de {rot} é "
                f"{pedido}{de_quem}.",
                f"Confira no portal qual pedido foi liquidado. Se foi o errado, "
                f"peça à CENPROT a correção da liquidação do pedido {numero} e "
                f"liquide o pedido {pedido}; depois anule este registro e "
                f"registre o certo.", trava=True))
        if dono != t["id"] and pedido and numero == pedido:
            achados.append(_achado(
                "LIQUIDACAO_DESTE_PEDIDO_POR_OUTRO_TITULO", DIVERGE,
                f"O pedido {pedido}, que é de {rot}, foi liquidado no portal "
                f"({quando}) em nome de "
                f"{_rotulo(titulos_por_id.get(dono) or {'id': dono})}.",
                f"Para a Central, {rot} está pago. Confira de qual título era o "
                f"dinheiro e, se a liquidação foi no pedido errado, peça a "
                f"correção à CENPROT antes de qualquer outro ato.", trava=True))
        if dono == t["id"] and situacao != "PAGO":
            achados.append(_achado(
                "LIQUIDACAO_SEM_PAGAMENTO_AQUI", DIVERGE,
                f"Registrou-se a liquidação no portal do pedido {numero} "
                f"({quando}) para {rot}, e aqui ele está {situacao} — não há "
                f"pagamento lavrado.",
                "A Liquidação do portal repassa ao apresentante o que o devedor "
                "pagou. Se ele não pagou, a liquidação foi no pedido errado: "
                "peça a correção à CENPROT. Se pagou, lance o pagamento na "
                "ficha.", trava=situacao in ABERTAS))
    pagamento = atos.get("PAGAMENTO")
    liquidados = {_txt(x["pedido"]) for x in liquidacoes_vivas}
    if (situacao == "PAGO" and pagamento
            and _txt(pagamento.get("origem")).upper() != "EOFICIO"
            and pedido and pedido not in liquidados):
        achados.append(_achado(
            "PAGO_SEM_LIQUIDACAO_REGISTRADA", CONFERIR,
            f"{rot} foi pago aqui em {_br(pagamento.get('data_ato'))}, e não há "
            f"registro de liquidação no portal do pedido {pedido}.",
            f"O repasse ao apresentante sai pela Liquidação no portal da "
            f"CENPROT, no pedido {pedido}. Feita, registre-a abaixo — com o "
            f"número do pedido conferido na tela do portal."))
    return achados


def _contexto(con: Any) -> dict:
    """Tudo o que a avaliação precisa, em sete consultas. Só LÊ."""
    titulos = _titulos(con)
    pendencias = _pedidos_das_pendencias(con)
    pedidos = {t["id"]: pedidos_do_titulo(t, da_pendencia=pendencias.get(t["id"]))
               for t in titulos}
    dono: dict[str, list[int]] = {}
    for tid, lista in pedidos.items():
        if lista:
            dono.setdefault(lista[0][0], []).append(tid)
    vivas = [x for x in liquidacoes(con) if not x.get("anulada_em")]
    return {"titulos": titulos, "pedidos": pedidos, "dono": dono,
            "atos": _atos(con), "conferencias": _conferencias(con),
            "repetidos": _protocolos_repetidos(con), "liquidacoes": vivas,
            "por_id": {t["id"]: t for t in titulos}}


def _linha(t: dict, ctx: dict) -> dict:
    tid = t["id"]
    pedidos = ctx["pedidos"].get(tid) or []
    pedido = pedidos[0][0] if pedidos else ""
    da_conta = [x for x in ctx["liquidacoes"]
                if int(x["titulo_id"]) == tid or (pedido and _txt(x["pedido"]) == pedido)]
    achados = avaliar(
        t, ctx["conferencias"].get(tid), pedidos=pedidos,
        atos=ctx["atos"].get(tid, {}), liquidacoes_vivas=da_conta,
        dono_do_pedido=ctx["dono"], repetidos=ctx["repetidos"].get(tid, []),
        titulos_por_id=ctx["por_id"])
    nivel = (DIVERGE if any(a["nivel"] == DIVERGE for a in achados)
             else CONFERIR if achados else "")
    return {**t, "pedido": pedido, "pedidos": pedidos,
            "conferencia": ctx["conferencias"].get(tid),
            "achados": achados, "nivel": nivel,
            "trava": [a for a in achados if a["trava"]]}


def quadro(con: Any) -> dict:
    """A tela da conferência, sem rede: o que a Central disse da última vez,
    comparado com o que o título é AGORA. Só LÊ.

    **A COMPARAÇÃO É DE AGORA, E A RESPOSTA DA CENTRAL É DA ÚLTIMA CONSULTA** —
    o pagamento lavrado depois da consulta já aparece; o que a Central mudou
    depois dela, não. Por isso cada linha diz quando foi consultada.
    """
    ctx = _contexto(con)
    linhas = [_linha(t, ctx) for t in ctx["titulos"]]
    ordem = {DIVERGE: 0, CONFERIR: 1, "": 2}
    linhas.sort(key=lambda r: (ordem[r["nivel"]], r["id"]))
    consultadas = [r["conferencia"]["consultada_em"] for r in linhas
                   if r["conferencia"] and r["conferencia"].get("consultada_em")]
    return {
        "linhas": linhas,
        "liquidacoes": liquidacoes(con),
        "contagem": {
            "titulos": len(linhas),
            "divergem": sum(1 for r in linhas if r["nivel"] == DIVERGE),
            "conferir": sum(1 for r in linhas if r["nivel"] == CONFERIR),
            "nunca_consultados": sum(
                1 for r in linhas
                if not (r["conferencia"] or {}).get("consultada_em")),
            "com_erro": sum(1 for r in linhas
                            if (r["conferencia"] or {}).get("erro")),
        },
        "ultima_consulta": max(consultadas) if consultadas else None,
    }


def quantos_divergem(con: Any) -> int:
    """Para a linha do painel do Protesto. Só LÊ."""
    return quadro(con)["contagem"]["divergem"]


def da_ficha(con: Any, titulo_id: int) -> dict | None:
    """O que a ficha do título mostra junto do botão de protestar. Só LÊ.

    `None` quando o título não veio da CENPROT — a ficha não mostra nada.
    """
    ctx = _contexto(con)
    t = ctx["por_id"].get(int(titulo_id))
    if t is None:
        return None
    return _linha(t, ctx)


# ===================================================================== rede


def _perguntar(numero: str, titulo: dict, documentos: set[str], *,
               ambiente: str, pasta=None) -> dict:
    """Pergunta à Central por UM pedido. FALA COM A REDE — nunca dentro de
    transação. Estoura `API.CenprotError` / `CRED.CredencialError` quando não
    deu para falar."""
    resposta = API.pedidos_de_protesto(ambiente, numero=numero, pasta=pasta)
    item = _o_pedido_na_resposta(resposta, numero)
    if item is None:
        return {"resultado": NAO_ACHOU}
    return {"resultado": ACHOU, **o_que_a_central_disse(item, titulo, documentos)}


_CAMPOS_DA_CENTRAL = (
    "central_estado", "central_status", "central_ocorrencia", "central_codigo",
    "central_data", "central_protocolo", "central_numero_titulo",
    "central_valor_centavos", "central_cedente", "central_cedente_confere",
    "central_devedor_confere")


def _guardar(con: Any, titulo_id: int, pedido: str, r: dict, *, ambiente: str,
             agora: str, quem: str) -> None:
    """Grava a última consulta do título. ESCREVE.

    A FALHA DE REDE NÃO APAGA O QUE A CENTRAL DISSE ANTES: grava só a
    tentativa e o erro. O «pago» de ontem continua valendo como o último
    fato conhecido até a Central dizer outra coisa.
    """
    bd = banco(con)
    if r.get("erro") is not None and "resultado" not in r:
        bd.escrever(
            """INSERT INTO cn_conferencias (titulo_id, ambiente, pedido,
                   tentada_em, erro)
               VALUES (%s,%s,%s,%s,%s)
               ON CONFLICT (ambiente, titulo_id) DO UPDATE SET
                   tentada_em = excluded.tentada_em, erro = excluded.erro""",
            (int(titulo_id), ambiente, pedido or None, agora,
             _txt(r["erro"])[:500]))
        return
    valores = [r.get(c) for c in _CAMPOS_DA_CENTRAL]
    colunas = ", ".join(_CAMPOS_DA_CENTRAL)
    marcas = ", ".join(["%s"] * len(_CAMPOS_DA_CENTRAL))
    atualiza = ", ".join(f"{c} = excluded.{c}" for c in _CAMPOS_DA_CENTRAL)
    bd.escrever(
        f"""INSERT INTO cn_conferencias (titulo_id, ambiente, pedido, resultado,
               consultada_em, consultada_por, tentada_em, erro, {colunas})
            VALUES (%s,%s,%s,%s,%s,%s,%s,NULL, {marcas})
            ON CONFLICT (ambiente, titulo_id) DO UPDATE SET
               pedido = excluded.pedido, resultado = excluded.resultado,
               consultada_em = excluded.consultada_em,
               consultada_por = excluded.consultada_por,
               tentada_em = excluded.tentada_em, erro = NULL, {atualiza}""",
        (int(titulo_id), ambiente, pedido or None, r["resultado"], agora,
         quem or None, agora, *valores))


def consultar(db, *, titulo_id: int | None = None, quem: str = "",
              ambiente: Any = CRED.PRODUCAO, pasta=None) -> dict:
    """Pergunta à Central por cada título de origem CENPROT (ou por um) e
    guarda o que ela disse. RECEBE `db`: a rede fica FORA da transação.

    **NÃO CORRIGE NADA.** Grava só `cn_conferencias`; quem compara é `quadro`.

    **PARA NA PRIMEIRA FALHA DE REDE.** São quase cem pedidos, um por
    chamada; com a Central fora do ar, insistir faria o balcão esperar um
    minuto por título. O que ficou sem perguntar continua com a resposta de
    antes, e o contador diz quantos foram.
    """
    onde = CRED.ambiente_de_uso(CRED.CENPROT, ambiente)
    with db.transaction() as con:
        titulos = _titulos(con, titulo_id)
        documentos = _documentos_dos_devedores(con, titulo_id)
        pendencias = _pedidos_das_pendencias(con)
    if titulo_id is not None and not titulos:
        raise ConferenciaError(
            f"O título {titulo_id} não veio da CENPROT (Gestão de Pedidos) — "
            f"não há pedido na Central para conferir.")
    respostas: list[tuple[int, str, dict]] = []
    parou = ""
    nao_perguntados = 0
    for t in titulos:
        lista = pedidos_do_titulo(t, da_pendencia=pendencias.get(t["id"]))
        if not lista:
            respostas.append((t["id"], "", {"resultado": SEM_PEDIDO}))
            continue
        numero = lista[0][0]
        if parou:
            nao_perguntados += 1
            continue
        try:
            r = _perguntar(numero, t, documentos.get(t["id"], set()),
                           ambiente=onde, pasta=pasta)
        except API.CenprotRecusou as erro:
            # A CENTRAL RESPONDEU, E RESPONDEU NÃO a este pedido: os outros
            # podem responder. Não para.
            r = {"erro": str(erro)}
        except (API.CenprotError, CRED.CredencialError) as erro:
            parou = str(erro)
            r = {"erro": parou}
        respostas.append((t["id"], numero, r))
    agora = db.now()
    with db.transaction() as con:
        for tid, numero, r in respostas:
            _guardar(con, tid, numero, r, ambiente=onde, agora=agora, quem=quem)
    return {
        "titulos": len(titulos),
        "achados": sum(1 for _, _, r in respostas if r.get("resultado") == ACHOU),
        "nao_achados": sum(1 for _, _, r in respostas
                           if r.get("resultado") == NAO_ACHOU),
        "sem_pedido": sum(1 for _, _, r in respostas
                          if r.get("resultado") == SEM_PEDIDO),
        "com_erro": sum(1 for _, _, r in respostas if "erro" in r),
        "nao_perguntados": nao_perguntados,
        "parou": parou,
    }


# ===================================================== a trava do protesto


def validar_afirmacao(afirmo: Any, afirmacao: Any, *, por_que: str = "") -> str:
    """A afirmação expressa do contrato comum da casa. Só calcula.

    Devolve o texto limpo, ou recusa com a frase: a caixa «Afirmo» marcada E
    pelo menos 30 LETRAS (espaço e pontuação não contam — «.......» não é
    afirmação de ninguém).
    """
    texto = " ".join(str(afirmacao or "").split())
    letras = sum(1 for c in texto if c.isalpha())
    if afirmo and letras >= MINIMO_DE_LETRAS_DA_AFIRMACAO:
        return texto
    falta = []
    if not afirmo:
        falta.append("marque a caixa «Afirmo»")
    if letras < MINIMO_DE_LETRAS_DA_AFIRMACAO:
        falta.append(f"escreva a afirmação com pelo menos "
                     f"{MINIMO_DE_LETRAS_DA_AFIRMACAO} letras (vieram {letras})")
    raise ConferenciaError(
        (por_que + " " if por_que else "")
        + "Para seguir assim mesmo, " + " e ".join(falta)
        + f", começando por «{MODELO_DA_AFIRMACAO}». Ela fica gravada no ato e "
          f"na auditoria, com o seu nome.")


def trava_do_protesto(db, titulo_id: int, *, afirmo: Any = False,
                      afirmacao: Any = "", quem: str = "", robo: bool = False,
                      em_lote: bool = False, perguntar: bool = True,
                      ambiente: Any = CRED.PRODUCAO, pasta=None) -> dict | None:
    """Confere o pedido na CENPROT ANTES de lavrar o protesto. RECEBE `db`:
    a rede fica fora da transação.

    Devolve:
      - `None` — pode protestar sem afirmação: o título não veio da CENPROT,
        não está intimado (o domínio recusa por conta própria), ou a Central
        confere;
      - a afirmação aceita — `{regra, afirmacao, o_que_faltava, pedido}` —,
        que a rota grava no ato (`anotar_afirmacao_no_ato`) e na auditoria.

    Recusa (`ConferenciaError`) quando a Central diz que o título saiu, quando
    não deu para conferir, ou quando o próprio título está em conflito (o
    protocolo de outro, o pedido de outro, a liquidação de outro) — e a
    afirmação expressa não veio. **No lote não se afirma**: a afirmação é
    título a título, na ficha, depois de olhar.
    """
    with db.transaction() as con:
        linhas = _titulos(con, titulo_id)
        if not linhas or _txt(linhas[0].get("situacao")).upper() != "INTIMADO":
            return None
        t = linhas[0]
        documentos = _documentos_dos_devedores(con, titulo_id).get(t["id"], set())
        pendencia = _pedidos_das_pendencias(con).get(t["id"])
    onde = CRED.ambiente_de_uso(CRED.CENPROT, ambiente)
    lista = pedidos_do_titulo(t, da_pendencia=pendencia)
    pedido = lista[0][0] if lista else ""
    faltou: list[str] = []
    sem_rede = False
    r: dict | None = None
    if not pedido:
        faltou.append("o número do pedido da CENPROT não está no título, e "
                      "sem ele a Central não se consulta")
    elif not perguntar:
        sem_rede = True
        faltou.append("a CENPROT não respondeu no começo deste lote, e os "
                      "títulos seguintes não foram perguntados")
    else:
        try:
            r = _perguntar(pedido, t, documentos, ambiente=onde, pasta=pasta)
        except API.CenprotRecusou as erro:
            r = {"erro": str(erro)}
            faltou.append(f"a CENPROT recusou a consulta do pedido {pedido}: "
                          f"{erro}")
        except (API.CenprotError, CRED.CredencialError) as erro:
            r = {"erro": str(erro)}
            sem_rede = True
            faltou.append(f"não deu para falar com a CENPROT: {erro}")
    with db.transaction() as con:
        if r is not None:
            _guardar(con, t["id"], pedido, r, ambiente=onde, agora=db.now(),
                     quem=quem)
        linha = da_ficha(con, t["id"]) or {"achados": [], "trava": []}
    conf = linha.get("conferencia") or {}
    if r is not None and r.get("resultado") == NAO_ACHOU:
        faltou.append(f"a CENPROT não devolveu o pedido {pedido}")
    if (r is not None and r.get("resultado") == ACHOU
            and conf.get("central_estado") == DESCONHECIDO):
        faltou.append(f"a CENPROT respondeu "
                      f"{_o_que_a_central_disse_em_frase(conf)}, e este "
                      f"sistema não sabe ler isso")
    travas = linha.get("trava") or []
    if travas:
        regra = REGRA_DIVERGENTE
        o_que = " ".join(a["frase"] for a in travas)
        if faltou:
            o_que += " Além disso, " + "; ".join(faltou) + "."
        frase = (f"Protesto NÃO lavrado: {o_que} Caminho: "
                 f"{travas[0]['caminho']}")
    elif faltou:
        regra = REGRA_NAO_CONFERIDO
        o_que = "; ".join(faltou) + "."
        frase = (f"Protesto NÃO lavrado: {_rotulo(t)} veio da CENPROT "
                 f"(pedido {pedido or 'desconhecido'}) e não deu para conferir "
                 f"na Central antes de protestar — {o_que} Confira o pedido "
                 f"no portal da CENPROT antes de lavrar.")
    else:
        return None
    if em_lote:
        raise ConferenciaError(
            frase + " A afirmação expressa é título a título: abra a ficha "
                    "do título, confira e, se for o caso, afirme por lá.",
            regra=regra, sem_rede=sem_rede)
    if robo:
        raise ConferenciaError(
            frase + " Afirmação expressa é de pessoa — conta de robô não "
                    "afirma.", regra=regra, sem_rede=sem_rede)
    try:
        texto = validar_afirmacao(afirmo, afirmacao, por_que=frase)
    except ConferenciaError as erro:
        raise ConferenciaError(str(erro), regra=regra,
                               sem_rede=sem_rede) from None
    return {"regra": regra, "afirmacao": texto, "o_que_faltava": o_que,
            "pedido": pedido or None, "titulo_id": int(t["id"])}


def anotar_afirmacao_no_ato(con: Any, ato_id: int, afirmacao: dict, *,
                            quem: str = "", agora: str = "") -> None:
    """Acrescenta a afirmação expressa ao `detalhe_json` do ato. ESCREVE.

    Chamada DENTRO da transação que lavrou o ato: ato sem a afirmação que o
    permitiu é ato que ninguém explica depois.
    """
    bd = banco(con)
    linha = bd.um("SELECT detalhe_json FROM pt_atos WHERE id = %s", (int(ato_id),))
    if linha is None:
        raise ConferenciaError(f"Ato {ato_id} não encontrado.")
    try:
        detalhe = json.loads(linha["detalhe_json"] or "{}")
    except ValueError:
        detalhe = {}
    if not isinstance(detalhe, dict):
        detalhe = {}
    lista = detalhe.get(CHAVE_NO_DETALHE)
    if not isinstance(lista, list):
        lista = []
    lista.append({"regra": afirmacao.get("regra"),
                  "afirmacao": afirmacao.get("afirmacao"),
                  "o_que_faltava": afirmacao.get("o_que_faltava"),
                  "pedido": afirmacao.get("pedido"),
                  "por": quem or None, "em": agora or None})
    detalhe[CHAVE_NO_DETALHE] = lista
    bd.escrever("UPDATE pt_atos SET detalhe_json = %s WHERE id = %s",
                (json.dumps(detalhe, ensure_ascii=False), int(ato_id)))


def detalhe_da_auditoria(afirmacao: dict) -> dict:
    """O `details` do `audit("AFIRMACAO_EXPRESSA", ...)` — o contrato comum.
    Só calcula."""
    return {"regra": afirmacao.get("regra"),
            "afirmacao": afirmacao.get("afirmacao"),
            "o_que_faltava": afirmacao.get("o_que_faltava"),
            "pedido": afirmacao.get("pedido")}


# ========================================= a liquidação feita no portal


_DATA = re.compile(r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$")


def registrar_liquidacao(con: Any, *, pedido: Any, titulo_id: int,
                         liquidada_em: Any = None, afirmo: Any = False,
                         afirmacao: Any = "", quem: str = "",
                         agora: str = "") -> dict:
    """«Liquidei no portal o pedido N, e ele é do título T.» ESCREVE.

    A casa precisa saber que liquidou, e de qual título — a API não conta
    (ver o cabeçalho). **A AFIRMAÇÃO É DE QUAL TÍTULO**, e é ela que deixa a
    conferência mostrar o erro do 350574: o pedido liquidado não ser o do
    título pago aqui.

    Devolve `{id, pedido, titulo_id, achados}` — os achados do título depois
    do registro, para a tela dizer na hora se o pedido não é dele.
    """
    numero = _digitos(pedido).lstrip("0")
    if not numero:
        raise ConferenciaError(
            "Informe o número do pedido que se liquidou no portal (Gestão de "
            "Pedidos da CENPROT), como aparece na tela do portal.")
    bd = banco(con)
    t = bd.um("""SELECT id, numero_titulo, situacao, origem, origem_chave,
                        apresentante_codigo FROM pt_titulos WHERE id = %s""",
              (int(titulo_id),))
    if t is None:
        raise ConferenciaError(f"Título {titulo_id} não encontrado.")
    if not e_de_origem_cenprot(dict(t)):
        raise ConferenciaError(
            f"O título {titulo_id} não veio da CENPROT (Gestão de Pedidos) — a "
            f"Liquidação do portal é de pedido da CENPROT.")
    data = _txt(liquidada_em)
    if data and not _DATA.match(data):
        raise ConferenciaError("A data da liquidação não se lê — use o "
                               "calendário da tela.")
    texto = validar_afirmacao(
        afirmo, afirmacao,
        por_que="O registro da liquidação é uma afirmação de qual título ela é.")
    if bd.um("""SELECT id FROM cn_liquidacoes_portal
                 WHERE pedido = %s AND titulo_id = %s AND anulada_em IS NULL""",
             (numero, int(titulo_id))):
        raise ConferenciaError(
            f"A liquidação do pedido {numero} para o título {titulo_id} já está "
            f"registrada.")
    novo = int(bd.escrever(
        """INSERT INTO cn_liquidacoes_portal (pedido, titulo_id, liquidada_em,
               afirmacao, registrada_em, registrada_por)
           VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
        (numero, int(titulo_id), data or None, texto, agora, quem or None))[0]["id"])
    linha = da_ficha(con, int(titulo_id)) or {"achados": []}
    return {"id": novo, "pedido": numero, "titulo_id": int(titulo_id),
            "afirmacao": texto, "achados": linha["achados"]}


def anular_liquidacao(con: Any, liquidacao_id: int, *, motivo: Any,
                      quem: str = "", agora: str = "") -> dict:
    """Tira do quadro um registro de liquidação feito por engano. ESCREVE.

    **NÃO APAGA**: a linha fica, com quem anulou, quando e por quê — o
    registro errado também é história do título. E não mexe em nada na
    Central: estornar uma liquidação é com a CENPROT.
    """
    texto = " ".join(str(motivo or "").split())
    if len(texto) < MINIMO_DO_MOTIVO:
        raise ConferenciaError(
            "Escreva por que este registro está errado (pelo menos "
            f"{MINIMO_DO_MOTIVO} caracteres) — a linha fica, anulada, com o "
            "motivo.")
    bd = banco(con)
    linha = bd.um("SELECT * FROM cn_liquidacoes_portal WHERE id = %s",
                  (int(liquidacao_id),))
    if linha is None:
        raise ConferenciaError(f"Registro de liquidação {liquidacao_id} não "
                               f"encontrado.")
    if linha["anulada_em"]:
        raise ConferenciaError("Este registro já está anulado.")
    bd.escrever("""UPDATE cn_liquidacoes_portal
                      SET anulada_em = %s, anulada_por = %s, anulada_motivo = %s
                    WHERE id = %s""",
                (agora, quem or None, texto, int(liquidacao_id)))
    return {"id": int(liquidacao_id), "pedido": linha["pedido"],
            "titulo_id": int(linha["titulo_id"]), "motivo": texto}
