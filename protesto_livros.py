"""Os livros do Protesto que a inspeção não achou — montados do que foi lavrado.

Código de Normas do TJMA (Prov. 28/2026), lido no texto em 14/10/2026:

  art. 930 — LIVRO DE REGISTRO DE PAGAMENTOS: «todos os pagamentos recebidos
  serão lançados», com as colunas a) número de ordem; b) data do assentamento;
  c) número do protocolo do documento pago; d) natureza do documento; e) valor
  do pagamento; f) valor dos emolumentos; g) nomes do devedor e do favorecido;
  h) ocorrências — e nelas «se o pagamento se dará em espécie ou por cheque,
  com a correspondente identificação». § 2º: pode ser eletrônico, «facultativa
  sua impressão».

  art. 908 — LIVRO DE PROTOCOLO: número de ordem, natureza do documento,
  valor, apresentante, devedor e OCORRÊNCIAS; § 1º: nelas vão o resultado, a
  liquidação, a sustação judicial, a retirada pelo apresentante, o protesto ou
  a devolução por irregularidade; § 5º: averbam-se as datas da intimação, do
  pagamento, da sustação, da devolução ou da lavratura do protesto.

POR QUE ISTO EXISTE. A inspeção de 2021 marcou o Livro de Registro de
Pagamentos como IRREGULAR («inexistente»), e a de 2026 constatou de novo
(tarefas #52 e #54; relato #128). O pagamento era registrado direto no caixa e
nenhum papel o reunia; o Livro de Protocolo não tinha a coluna de ocorrências.

ESTE MÓDULO SÓ LÊ. O livro é a vista do que os atos já gravaram (`pt_atos`,
`pt_titulos`, `pt_devedores`): não há segunda gaveta para divergir da primeira.
O que o ato não guardou aparece como «não consta», e não inventado — os
pagamentos trazidos do E-Ofício não têm emolumentos nem forma de pagamento.
"""
from __future__ import annotations

import json
from typing import Any

import protesto_pecas as PECAS
from bd_nativo import banco
from caixa_schema import reais
from cpf_cnpj import formatar_documento

# O TEXTO DOS DOIS LIVROS SAIU DAQUI NO LF06E (19/10/2026): as formas de
# pagamento por extenso (`FORMAS`), o que se averba para cada ato
# (`OCORRENCIA_DO_ATO`) e as frases das ocorrências moram nas peças
# `PT_LIVRO_PAGAMENTOS` e `PT_LIVRO_PROTOCOLO`, e o nome da espécie em
# `PT_ESPECIES` — o oficial os edita na tela de Modelos. QUAIS formas e QUAIS
# atos entram continua decidido aqui. Os nomes antigos continuam respondendo —
# ver `__getattr__` no fim deste módulo.


def _br(iso: Any) -> str:
    s = str(iso or "")[:10]
    return f"{s[8:10]}/{s[5:7]}/{s[:4]}" if len(s) == 10 and s[4] == "-" else s


def _natureza(especie: Any, especies: dict, sem: str) -> str:
    e = str(especie or "").strip().upper()
    return especies.get(e, e) if e else sem


def _detalhe(texto: Any) -> dict:
    try:
        return json.loads(texto or "{}") or {}
    except (TypeError, ValueError):
        return {}


def _intervalo(de: str | None, ate: str | None) -> tuple[str, str]:
    """O filtro de data inclui o dia inteiro do «até», mesmo com hora gravada."""
    return (str(de or "0000-00-00")[:10], str(ate or "9999-12-31")[:10] + "z")


def livro_de_pagamentos(con, *, de: str | None = None,
                        ate: str | None = None) -> list[dict]:
    """As linhas do Livro de Registro de Pagamentos, na ordem do livro. Só LÊ."""
    import protesto as PT
    inicio, fim = _intervalo(de, ate)
    rotulo = PECAS.vocabulario(con, "PT_LIVRO_PAGAMENTOS")
    especies = PECAS.vocabulario(con, "PT_ESPECIES")

    def _p(nome: str, **claros: Any) -> str:
        return PECAS.preencher(rotulo[nome], "PT_LIVRO_PAGAMENTOS", ValueError,
                               **claros)

    linhas = []
    for r in banco(con).ler(
            """SELECT a.id, a.data_ato, a.numero_ordem, a.folha, a.rotulo,
                      a.detalhe_json, a.origem,
                      (SELECT v.numero FROM nu_livros v WHERE v.id = a.livro_id) AS livro,
                      t.protocolo, t.especie, t.numero_titulo, t.saldo_centavos,
                      t.cedente_nome,
                      (SELECT d.nome FROM pt_devedores d WHERE d.titulo_id = t.id
                        ORDER BY d.id LIMIT 1) AS devedor
                 FROM pt_atos a JOIN pt_titulos t ON t.id = a.titulo_id
                WHERE a.tipo = 'PAGAMENTO' AND a.cancelado = 0
                  AND a.data_ato >= %s AND a.data_ato <= %s
                ORDER BY a.data_ato, a.id""", (inicio, fim)):
        d = _detalhe(r["detalhe_json"])
        valor = d.get("valor_pago_centavos")
        codigo = str(d.get("forma_pagamento") or "").upper()
        forma = rotulo[codigo] if codigo in PT.FORMAS_DE_PAGAMENTO else None
        ocorr = []
        if forma:
            ocorr.append(_p("pago_com_identificacao", forma=forma,
                            identificacao=d["forma_identificacao"])
                         if d.get("forma_identificacao") else _p("pago", forma=forma))
        if r["origem"] == "EOFICIO":
            ocorr.append(_p("eoficio"))
        linhas.append({
            "ato_id": int(r["id"]),
            "ordem": r["numero_ordem"],
            "livro": r["livro"], "folha": r["rotulo"] or r["folha"],
            "data": _br(r["data_ato"]),
            "protocolo": r["protocolo"] or "",
            "natureza": _natureza(r["especie"], especies, _p("sem_natureza")),
            "titulo": r["numero_titulo"] or "",
            "valor": reais(int(valor)) if valor is not None else
                     _p("saldo", valor=reais(int(r["saldo_centavos"] or 0))),
            "emolumentos": (reais(int(d["emolumentos_centavos"]))
                            if d.get("emolumentos_centavos") is not None
                            else _p("sem_emolumentos")),
            "devedor": r["devedor"] or "",
            "favorecido": r["cedente_nome"] or "",
            "ocorrencias": "; ".join(ocorr) or _p("sem_forma"),
        })
    return linhas


# Os atos que se averbam no Livro de Protocolo (art. 908, §§ 1º e 5º). O que
# se escreve para cada um é a peça `PT_LIVRO_PROTOCOLO`.
ATOS_NO_PROTOCOLO = ("INTIMACAO", "PAGAMENTO", "DESISTENCIA", "PROTESTO",
                     "CANCELAMENTO", "SUSTACAO", "REVOGACAO_SUSTACAO",
                     "EFEITO_SUSPENSIVO")


def livro_de_protocolo(con, *, de: str | None = None,
                       ate: str | None = None) -> list[dict]:
    """As linhas do Livro de Protocolo, com a coluna de OCORRÊNCIAS. Só LÊ.

    A data que filtra é a do APONTAMENTO (a protocolização); as ocorrências
    trazem a data de cada ato posterior, como o § 5º manda averbar.
    """
    inicio, fim = _intervalo(de, ate)
    return _linhas_do_protocolo(con, "", (inicio, fim))


def protocolo_do_devedor(con, *, nome: str | None = None,
                         documento: str | None = None,
                         desde: str | None = None) -> list[dict]:
    """As linhas do Livro de Protocolo em que a pessoa figura como devedor. Só LÊ.

    É O QUE A CERTIDÃO A PEDIDO ESCRITO CERTIFICA (LD04, 21/10/2026): CN-MA
    art. 906, § 2º — «Informações e certidões extraídas do Livro de Protocolo
    somente serão fornecidas mediante requerimento escrito do próprio devedor
    ou por determinação judicial» —, e art. 905, parágrafo único. Até aqui a
    única certidão era a de protesto lavrado, e o título só apontado saía
    NEGATIVA mesmo a pedido do devedor. Quem decide se a autorização existe é
    `protesto_certidao.emitir`; aqui só se lê.

    Casa como a busca da certidão, pela MESMA regra
    (`protesto_certidao.onde_casa_o_devedor`, LD11 e LD12): com o CPF/CNPJ,
    pelo documento — o protocolo do homônimo de outro CPF não vai ao papel do
    devedor —, e o devedor gravado sem documento pelo nome inteiro; sem
    documento no pedido, pelo nome. O nome é texto e não curinga: «%» não
    traz o livro inteiro.

    A LINHA EM QUE SÓ O NOME LIGA A PESSOA vem com `so_pelo_nome` (LD12): o
    título em que nenhum devedor achado tem CPF/CNPJ. É para o escrevente
    conferir a identidade; o teor não a lê.
    """
    import protesto_certidao as PCE
    onde, params = PCE.onde_casa_o_devedor(nome, documento)
    if not onde:
        return []
    inicio, fim = _intervalo(desde, None)
    filtro = (" AND EXISTS (SELECT 1 FROM pt_devedores d WHERE d.titulo_id = t.id"
              f" AND {onde})")
    linhas = _linhas_do_protocolo(con, filtro, (inicio, fim, *params))
    if linhas:
        com_documento = {int(r["titulo_id"]) for r in banco(con).ler(
            f"""SELECT DISTINCT d.titulo_id FROM pt_devedores d
                 WHERE d.titulo_id = ANY(%s) AND {onde}
                   AND NOT ({PCE.DEVEDOR_SEM_DOCUMENTO})
                 ORDER BY d.titulo_id""",
            ([l["titulo_id"] for l in linhas], *params))}
        for linha in linhas:
            linha["so_pelo_nome"] = linha["titulo_id"] not in com_documento
    return linhas


def _linhas_do_protocolo(con, filtro: str, params: tuple) -> list[dict]:
    """A linha do Livro de Protocolo, uma por apontamento. Só LÊ.

    `filtro` é SQL fixo (deste módulo, ou o de `onde_casa_o_devedor`; nunca
    texto de quem pede) e `params` começa pelo intervalo do apontamento.
    """
    bd = banco(con)
    rotulo = PECAS.vocabulario(con, "PT_LIVRO_PROTOCOLO")
    especies = PECAS.vocabulario(con, "PT_ESPECIES")

    def _p(nome: str, **claros: Any) -> str:
        return PECAS.preencher(rotulo[nome], "PT_LIVRO_PROTOCOLO", ValueError,
                               **claros)

    linhas = []
    # O CPF/CNPJ DO DEVEDOR É DO MESMO DEVEDOR DA COLUNA DO NOME (LD04) — CN-MA
    # art. 906: o número identificador consta «no Livro de Protocolo e em
    # todos os registros e certidões». A coluna «Devedor» era só o nome.
    for r in bd.ler(
            f"""SELECT t.id, t.protocolo, t.especie, t.numero_titulo,
                      t.valor_centavos, t.apresentante_nome, t.apresentante_codigo,
                      t.situacao, a.data_ato, a.numero_ordem,
                      (SELECT d.nome FROM pt_devedores d WHERE d.titulo_id = t.id
                        ORDER BY d.id LIMIT 1) AS devedor,
                      (SELECT d.documento_numero FROM pt_devedores d
                        WHERE d.titulo_id = t.id ORDER BY d.id LIMIT 1)
                          AS devedor_documento
                 FROM pt_atos a JOIN pt_titulos t ON t.id = a.titulo_id
                WHERE a.tipo = 'APONTAMENTO' AND a.cancelado = 0
                  AND a.data_ato >= %s AND a.data_ato <= %s{filtro}
                ORDER BY a.data_ato, a.numero_ordem, a.id""", params):
        ocorr = []
        for o in bd.ler(
                """SELECT tipo, data_ato, detalhe_json FROM pt_atos
                    WHERE titulo_id = %s AND cancelado = 0 AND tipo <> 'APONTAMENTO'
                    ORDER BY data_ato, id""", (int(r["id"]),)):
            if o["tipo"] not in ATOS_NO_PROTOCOLO:
                continue
            ocorrencia = rotulo[o["tipo"]]
            if o["tipo"] == "INTIMACAO":
                modo = str(_detalhe(o["detalhe_json"]).get("modo") or "").upper()
                if modo == "EDITAL":
                    ocorrencia = _p("por_edital", ocorrencia=ocorrencia)
                elif modo == "PESSOAL":
                    ocorrencia = _p("pessoalmente", ocorrencia=ocorrencia)
            ocorr.append(_p("com_data", ocorrencia=ocorrencia,
                            data=_br(o["data_ato"])))
        linhas.append({
            "titulo_id": int(r["id"]),
            "ordem": r["numero_ordem"],
            "protocolo": r["protocolo"] or "",
            "data": _br(r["data_ato"]),
            "natureza": _natureza(r["especie"], especies, _p("sem_natureza")),
            "titulo": r["numero_titulo"] or "",
            "valor": reais(int(r["valor_centavos"] or 0)),
            "apresentante": r["apresentante_nome"] or r["apresentante_codigo"] or "",
            "devedor": r["devedor"] or "",
            "documento": formatar_documento(r["devedor_documento"]),
            "ocorrencias": "; ".join(ocorr) or _p("sem_ocorrencia"),
        })
    return linhas


# ------------------------------------------------------------ a quitação

# A QUITAÇÃO DO TÍTULO (LD04, 21/10/2026) — Lei 9.492/1997, art. 19, § 2º: «No
# ato do pagamento, o Tabelionato de Protesto dará a respectiva quitação»; CN-MA
# art. 927: «Recebido o pagamento no tabelionato, o oficial emitirá
# imediatamente a quitação e entregará o título ao devedor». O recibo do caixa
# é o dos EMOLUMENTOS; a quitação é do VALOR DO TÍTULO, e não havia papel dela.
# O texto mora em `modelos_padrao/protesto/PT_QUITACAO.txt` e é do oficial; o
# nome `QUITACAO_DO_TITULO` responde pelo `__getattr__` do fim deste módulo.
CHAVE_DA_QUITACAO = "PT_QUITACAO"


class QuitacaoError(ValueError):
    """Impedimento de regra, com mensagem pronta para o balcão."""


def quitacao(con, ato_id: int) -> dict:
    """O teor da quitação de um pagamento JÁ LANÇADO. Só LÊ.

    **A QUITAÇÃO SAI DO LANÇAMENTO, E NÃO DO CAIXA**: o CN-MA art. 930, § 1º,
    manda escriturar o Livro de Pagamentos «no exato momento do recebimento do
    pagamento e antes da emissão do respectivo recibo». Por isso este papel só
    existe para o ato PAGAMENTO que está no livro (não anulado): sem ele não
    há o que quitar, e a recusa diz isso. O valor é o pago que o ato guardou;
    sem ele, o saldo do título — que é o que o aviso cobrou (art. 19, caput).

    No CHEQUE a quitação fica condicionada à liquidação (art. 19, § 3º; CN-MA
    art. 927, parágrafo único), e o papel o diz. Devolve as linhas do teor.
    """
    import protesto as PT
    import protesto_termo as TERMO
    bd = banco(con)
    livro_sql = ("(SELECT v.numero FROM nu_livros v WHERE v.id = a.livro_id)"
                 if bd.tem_tabela("nu_livros") else "NULL")
    ato = bd.um(
        f"""SELECT a.*, {livro_sql} AS livro_numero
              FROM pt_atos a WHERE a.id = %s""", (int(ato_id),))
    if not ato or ato["tipo"] != "PAGAMENTO" or int(ato["cancelado"] or 0):
        raise QuitacaoError(
            "Não há pagamento lançado no Livro de Registro de Pagamentos com "
            "este número — a quitação só sai do pagamento lançado (CN-MA art. "
            "930, § 1º).")
    t = bd.um("SELECT * FROM pt_titulos WHERE id = %s", (int(ato["titulo_id"]),))
    # O TÍTULO QUE NÃO ESTÁ NO BANCO RECUSA COM RECADO (LD11, revisão do
    # LD04). A chave estrangeira de `pt_atos.titulo_id` não deixa isso
    # acontecer hoje; mas o `None` caía em `TypeError` no primeiro campo lido,
    # e a rota, que só apanha `QuitacaoError`, mostrava a página de erro.
    if not t:
        raise QuitacaoError(
            "O título deste pagamento não está no banco — sem ele não há o que "
            "quitar, e a quitação não sai (Lei 9.492/1997, art. 19, § 2º).")
    devedores = bd.ler(
        """SELECT nome, documento_tipo, documento_numero FROM pt_devedores
            WHERE titulo_id = %s ORDER BY id""", (int(ato["titulo_id"]),))
    d = _detalhe(ato["detalhe_json"])
    rotulo = PECAS.vocabulario(con, "PT_LIVRO_PAGAMENTOS")
    descricao = PECAS.vocabulario(con, "PT_INSTRUMENTO_DESCRICAO")
    especies = PECAS.vocabulario(con, "PT_ESPECIES")

    def _p(peca: dict, chave: str, nome: str, **claros: Any) -> str:
        return PECAS.preencher(peca[nome], chave, QuitacaoError, **claros)

    valor = d.get("valor_pago_centavos")
    if valor is None:
        valor = t["saldo_centavos"] or t["valor_centavos"] or 0
    codigo = str(d.get("forma_pagamento") or "").upper()
    lugar = []
    if ato["livro_numero"]:
        lugar.append(_p(descricao, "PT_INSTRUMENTO_DESCRICAO", "livro",
                        livro=ato["livro_numero"]))
    if ato["rotulo"] or ato["folha"]:
        lugar.append(_p(descricao, "PT_INSTRUMENTO_DESCRICAO", "folha",
                        folha=ato["rotulo"] or ato["folha"]))
    if ato["numero_ordem"]:
        lugar.append(_p(descricao, "PT_INSTRUMENTO_DESCRICAO", "numero_de_ordem",
                        numero_ordem=ato["numero_ordem"]))
    # O TÍTULO E O DEVEDOR SE ESCREVEM COMO NO INSTRUMENTO — as frases de
    # `PT_INSTRUMENTO_DESCRICAO` —, e o documento vai formatado, como na
    # certidão: é papel que o devedor leva para casa.
    sem = _p(descricao, "PT_INSTRUMENTO_DESCRICAO", "sem_especie")
    titulo = _p(descricao, "PT_INSTRUMENTO_DESCRICAO", "titulo",
                especie=_natureza(t["especie"], especies, sem),
                numero_titulo=(t["numero_titulo"] or "").strip()
                or _p(descricao, "PT_INSTRUMENTO_DESCRICAO", "sem_numero"))
    pagadores = []
    for dev in devedores:
        documento = (_p(descricao, "PT_INSTRUMENTO_DESCRICAO", "devedor_documento",
                        tipo_documento=dev["documento_tipo"] or _p(
                            descricao, "PT_INSTRUMENTO_DESCRICAO",
                            "sem_tipo_de_documento"),
                        documento=formatar_documento(dev["documento_numero"]))
                     if dev["documento_numero"] else "")
        pagadores.append(", ".join(x for x in ((dev["nome"] or "").strip(),
                                               documento) if x))
    partes = {
        "data": _br(ato["data_ato"]),
        "valor": reais(int(valor)),
        "devedor": "; ".join(x for x in pagadores if x),
        "titulo": titulo,
        "protocolo": t["protocolo"] or "",
        "credor": t["cedente_nome"] or "",
        "forma": rotulo[codigo] if codigo in PT.FORMAS_DE_PAGAMENTO else "",
        "identificacao": (d.get("forma_identificacao") or ""
                          if codigo != "CHEQUE" else ""),
        "cheque": (d.get("forma_identificacao") or "") if codigo == "CHEQUE" else "",
        "emolumentos": (reais(int(d["emolumentos_centavos"]))
                        if d.get("emolumentos_centavos") is not None else ""),
        "lancamento": ", ".join(lugar),
    }
    # O CLARO QUE NÃO EXISTE RECUSA com o nome do papel e os claros que valem
    # (`protesto_pecas.preencher`) — o ajuste antigo gravado por fora da tela.
    modelo = PECAS.texto(con, CHAVE_DA_QUITACAO)
    PECAS.preencher(modelo, CHAVE_DA_QUITACAO, QuitacaoError, **partes)
    return {"ato_id": int(ato["id"]), "titulo_id": int(ato["titulo_id"]),
            "data_ato": ato["data_ato"], "selo": ato["selo"],
            "linhas": TERMO.linhas_com_fatos(modelo, partes)}


def __getattr__(nome: str):
    """Os nomes antigos do texto dos livros, lidos da base dos padrões.

    O TEXTO SAIU DESTE MÓDULO NO LF06E (19/10/2026) e mora em
    `modelos_padrao/protesto/`. Quem ainda pede `FORMAS` ou `OCORRENCIA_DO_ATO`
    recebe o padrão da base — o MESMO que o livro imprime. Nome que não é de
    papel continua sendo `AttributeError`.
    """
    if nome.startswith("__"):
        raise AttributeError(nome)
    import modelos_da_casa as _MODELOS
    return _MODELOS.constante_antiga(__name__, nome)
