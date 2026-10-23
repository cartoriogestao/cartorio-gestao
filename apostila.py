"""A APOSTILA DE HAIA — pedido, documento, emissão, selo, cobrança e controle.

POR QUE EXISTE (LG03, 19/10/2026)
    A serventia não apostila hoje. O módulo nasce pronto para o dia em que for
    habilitada, e por isso nasce **desligado**: o alcance de fábrica é
    `NINGUEM` (`modulos_ligados`), e quem o liga é o oficial, no Gestor.

O QUE ESTE MÓDULO É, E O QUE NÃO É
    **A emissão em si é no sistema do CNJ.** Aqui é o que a serventia precisa
    guardar em volta dela: quem pediu, que documento foi apostilado (tipo,
    signatário, cargo, autoridade), o número/código que o sistema do CNJ deu à
    apostila, o selo, o valor pela tabela do MA e o protocolo geral em que ela
    foi cobrada — e o **controle numerado**, de onde sai a certidão e o
    relatório. Não há integração com o sistema do CNJ: não há o que ligar nem
    credencial a guardar.

A BASE NORMATIVA
    - Código de Normas do MA (Prov. COGEX 28/2026), art. 875: o apostilamento
      «observará rigorosamente» a Resolução CNJ nº 228/2016 e os arts. 195 a
      216 do Código Nacional de Normas (Prov. CNJ 149/2023). Conferido no
      texto do Código do MA em `referencia/`.
    - Convenção da Apostila (Decreto nº 8.660/2016), art. 7º: a autoridade
      que apostila mantém um REGISTRO das apostilas, com o número e a data de
      cada uma, e o nome de quem assinou o documento e a qualidade em que
      agiu — ou, no documento sem assinatura, a autoridade que apôs o selo ou
      carimbo. É por isso que `signatario_nome` OU `autoridade` é obrigatório,
      e é esse registro que `controle` devolve.
    - Resolução CNJ 228/2016 e arts. 195 a 216 do CNN: os detalhes (livro,
      prazo de guarda, recusa, cobrança) — **conferir no texto oficial**; o
      texto não está em `referencia/`, e nada aqui foi tirado de resumo.

A COBRANÇA MORA NO CAIXA, E NÃO AQUI
    Decisão do oficial em 27/08/2026: «no caixa/protocolo geral colocamos os
    serviços prestados». A apostila **consome** uma unidade do item de
    protocolo que a cobrou (`caixa_protocolo.consumir_item`), como os outros
    atos da casa; um segundo trilho de dinheiro seria o defeito que o caixa já
    pagou (32.416 itens que nunca viraram lançamento). O que se guarda aqui é
    o valor da tabela NO DIA do registro — o que o balcão disse ao cliente.

O NÚMERO DE ORDEM SÓ NASCE NA EMISSÃO
    O controle é das apostilas EMITIDAS. Documento recusado ou ainda na fila
    não ocupa número: buraco na numeração é o que a correição pergunta.
    Cancelar depois de emitida NÃO devolve o número — a linha fica no controle,
    marcada, com o motivo.

PostgreSQL nativo, pelo `bd_nativo` (MANUAL_DA_CONVERSAO). Data e hora se
calculam no Python (regra da casa).
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

import atribuicoes as ATR
import caixa_protocolo as CXP
import cpf_cnpj
import custas
from bd_nativo import banco
from caixa_schema import centavos, reais

# A CHAVE DO MÓDULO EM `modulos_ligados` — quem decide o alcance é aquele
# módulo, e não uma segunda régua aqui.
MODULO = "APOSTILA"

# A CONFIGURAÇÃO PRÓPRIA. Só o serviço da tabela: o alcance é do
# `modulos_ligados`.
CHAVE_DO_SERVICO = "apostila_servico"

# ---------------------------------------------------------- vocabulário

# AS ATRIBUIÇÕES QUE APOSTILAM, tiradas do vocabulário do E-Ofício
# (`atribuicoes.ATOS`), e não digitadas de novo. O Protesto tem o ato, mas o
# acervo o marca como NÃO liberado — e ato não liberado não se pratica.
ATOS_DE_APOSTILA: dict[str, dict] = {
    ATR.ATRIBUICOES[a["atribuicao"]]["sigla"]: {"ato": codigo, **a}
    for codigo, a in sorted(ATR.ATOS.items())
    if a["nome"] == "Apostila de Haia"
}
ATRIBUICOES_LIBERADAS: tuple[str, ...] = tuple(
    sigla for sigla, a in ATOS_DE_APOSTILA.items() if a["liberado"])

PENDENTE, EMITIDA, RECUSADA, CANCELADA = "PENDENTE", "EMITIDA", "RECUSADA", "CANCELADA"
SITUACOES: dict[str, str] = {
    PENDENTE: "Aguardando a emissão no sistema do CNJ",
    EMITIDA: "Emitida",
    RECUSADA: "Recusada (não emitida)",
    CANCELADA: "Cancelada depois de emitida",
}

# OS TIPOS DE DOCUMENTO. Lista curta e uma porta («Outro», com descrição):
# a correição lê o tipo, e uma lista de cinquenta seria escolhida ao acaso.
TIPOS_DE_DOCUMENTO: dict[str, str] = {
    "REGISTRO_CIVIL": "Certidão de registro civil",
    "NOTARIAL": "Ato notarial (escritura, procuração, ata)",
    "REGISTRAL": "Certidão de registro de imóveis, títulos ou pessoa jurídica",
    "JUDICIAL": "Documento judicial",
    "ESCOLAR": "Documento escolar ou acadêmico",
    "ADMINISTRATIVO": "Documento da administração pública",
    "FIRMA_RECONHECIDA": "Documento particular com firma reconhecida",
    "TRADUCAO": "Tradução juramentada",
    "OUTRO": "Outro (descrever)",
}

# Dez caracteres, a régua do protocolo geral (`caixa_protocolo`): «erro» não
# explica nada a quem ler daqui a dois anos.
MINIMO_DO_MOTIVO = CXP.MINIMO_DO_MOTIVO

# O CÓDIGO DA APOSTILA é o que o sistema do CNJ imprimiu nela. O formato não
# está em texto que eu tenha conferido, e por isso a régua é larga — letras,
# dígitos e separadores —, só para barrar o que claramente não é código.
_CODIGO = re.compile(r"[A-Z0-9][A-Z0-9./ -]{3,59}")

LIMITE = 200


class ApostilaError(ValueError):
    """Impedimento de regra, com a frase pronta para o balcão."""


# ---------------------------------------------------------------- esquema
#
# TABELA NOVA, UM COMANDO POR LINHA, E CADA UM SÓ SE O OBJETO FALTA — o
# `to_regclass` acha tabela e índice (o padrão de `ia_uso`). Sem FK para
# `cx_protocolos`: o caixa nasce depois desta tabela na subida, e o vínculo é
# pelo item consumido, que já guarda `usado_por_tabela`/`usado_por_ato_id`.
# Dinheiro em CENTAVOS, `bigint` (o `INTEGER` do esquema é int4).
SCHEMA: tuple[tuple[str, str], ...] = (
    ("ap_pedidos", """
        CREATE TABLE IF NOT EXISTS ap_pedidos (
            id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            recebido_em TEXT NOT NULL,
            atribuicao TEXT NOT NULL,
            requerente_nome TEXT NOT NULL,
            requerente_documento TEXT NOT NULL DEFAULT '',
            requerente_contato TEXT NOT NULL DEFAULT '',
            pais_destino TEXT NOT NULL DEFAULT '',
            protocolo_id bigint,
            protocolo_numero TEXT NOT NULL DEFAULT '',
            observacao TEXT NOT NULL DEFAULT '',
            criado_em TEXT NOT NULL,
            criado_por TEXT NOT NULL DEFAULT ''
        )"""),
    ("ix_ap_pedidos_recebido",
     "CREATE INDEX IF NOT EXISTS ix_ap_pedidos_recebido ON ap_pedidos (recebido_em, id)"),
    ("ap_apostilas", """
        CREATE TABLE IF NOT EXISTS ap_apostilas (
            id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            pedido_id bigint NOT NULL REFERENCES ap_pedidos (id),
            documento_tipo TEXT NOT NULL,
            documento_descricao TEXT NOT NULL DEFAULT '',
            documento_data TEXT NOT NULL DEFAULT '',
            signatario_nome TEXT NOT NULL DEFAULT '',
            signatario_cargo TEXT NOT NULL DEFAULT '',
            autoridade TEXT NOT NULL DEFAULT '',
            situacao TEXT NOT NULL DEFAULT 'PENDENTE'
                CHECK (situacao IN ('PENDENTE', 'EMITIDA', 'RECUSADA', 'CANCELADA')),
            servico bigint,
            codigo_tj TEXT NOT NULL DEFAULT '',
            vigencia bigint,
            emolumentos bigint NOT NULL DEFAULT 0,
            ferc bigint NOT NULL DEFAULT 0,
            femp bigint NOT NULL DEFAULT 0,
            fadep bigint NOT NULL DEFAULT 0,
            ferrfis bigint NOT NULL DEFAULT 0,
            total bigint NOT NULL DEFAULT 0,
            ordem bigint UNIQUE,
            codigo_cnj TEXT,
            emitida_em TEXT,
            emitida_por TEXT NOT NULL DEFAULT '',
            selo TEXT,
            selo_em TEXT,
            selo_por TEXT NOT NULL DEFAULT '',
            protocolo_item_id bigint,
            motivo TEXT NOT NULL DEFAULT '',
            encerrada_em TEXT,
            encerrada_por TEXT NOT NULL DEFAULT '',
            criado_em TEXT NOT NULL,
            criado_por TEXT NOT NULL DEFAULT ''
        )"""),
    ("ix_ap_apostilas_pedido",
     "CREATE INDEX IF NOT EXISTS ix_ap_apostilas_pedido ON ap_apostilas (pedido_id, id)"),
    ("ix_ap_apostilas_emitida",
     "CREATE INDEX IF NOT EXISTS ix_ap_apostilas_emitida ON ap_apostilas (emitida_em, ordem)"),
    # O MESMO CÓDIGO DO CNJ E O MESMO SELO NÃO ENTRAM DUAS VEZES. A conferência
    # da rota dá a frase; o índice é a trava que vale quando duas passam juntas.
    ("ux_ap_apostilas_codigo",
     "CREATE UNIQUE INDEX IF NOT EXISTS ux_ap_apostilas_codigo "
     "ON ap_apostilas (codigo_cnj) WHERE codigo_cnj IS NOT NULL"),
    ("ux_ap_apostilas_selo",
     "CREATE UNIQUE INDEX IF NOT EXISTS ux_ap_apostilas_selo "
     "ON ap_apostilas (selo) WHERE selo IS NOT NULL"),
)


def init_apostila_schema(con) -> None:
    """Cria as duas tabelas e os índices que faltarem. Idempotente."""
    bd = banco(con)
    for nome, comando in SCHEMA:
        if not bd.tem_tabela(nome):
            bd.escrever(comando)


# ------------------------------------------------------------- auxiliares


def _texto(valor: Any, limite: int = LIMITE) -> str:
    return " ".join(str(valor or "").split())[:limite]


def _dia(valor: Any, *, campo: str, obrigatorio: bool = True,
         ate: str | None = None) -> str:
    """Data AAAA-MM-DD do formulário. Data no futuro não é de ato praticado."""
    texto = str(valor or "").strip()[:10]
    if not texto:
        if obrigatorio:
            raise ApostilaError(f"Informe {campo}.")
        return ""
    try:
        dia = date.fromisoformat(texto)
    except ValueError as erro:
        raise ApostilaError(f"{campo.capitalize()} não é uma data válida.") from erro
    if ate and dia.isoformat() > ate:
        raise ApostilaError(f"{campo.capitalize()} está no futuro.")
    return dia.isoformat()


def _motivo(valor: Any) -> str:
    texto = _texto(valor, 1000)
    if len(texto) < MINIMO_DO_MOTIVO:
        raise ApostilaError(
            f"Escreva o motivo em uma frase (pelo menos {MINIMO_DO_MOTIVO} "
            f"letras): quem ler o controle daqui a dois anos precisa entender.")
    return texto


def valores_em_reais(linha: dict) -> dict:
    """Os centavos da linha, na forma da tela. Só calcula."""
    return {c: reais(int(linha.get(c) or 0))
            for c in ("emolumentos", "ferc", "femp", "fadep", "ferrfis", "total")}


# ----------------------------------------------------------- o serviço


def servicos_da_tabela(con) -> list[dict]:
    """Os serviços da tabela carregada cujo nome é o da apostila. Só LÊ."""
    bd = banco(con)
    if not bd.tem_tabela("cx_servicos"):
        return []
    return bd.ler(
        """SELECT codigo, codigo_tj, descricao FROM cx_servicos
            WHERE descricao ILIKE %s
            ORDER BY codigo_tj, codigo""", ("apostila de haia%",))


def servico_configurado(con, get_setting=None) -> int | None:
    """O serviço da tabela que cobra a apostila. Só LÊ.

    O que o oficial escolheu no Gestor manda; sem escolha, o primeiro da
    tabela com o nome da apostila. A tabela do MA tem mais de um (13.23 nas
    Notas, 15.16 no RTD, ambos com o mesmo valor em 2026) — e quem decide
    qual a casa usa é ele, não a ordem do código.
    """
    escolhido = str((get_setting(CHAVE_DO_SERVICO, "") if get_setting else "") or "").strip()
    if escolhido.isdigit():
        return int(escolhido)
    achados = servicos_da_tabela(con)
    return int(achados[0]["codigo"]) if achados else None


def calcular_valor(con, *, servico: int | None, dia: str) -> dict:
    """O valor da apostila pela tabela do dia. Só LÊ (pelo `custas`)."""
    if servico is None:
        raise ApostilaError(
            "A tabela de emolumentos carregada não tem o serviço da Apostila de "
            "Haia. Importe a tabela ou escolha o serviço no Gestor → Apostila "
            "de Haia.")
    try:
        conta = custas.calcular(con, servico=int(servico), data=dia)
    except custas.CustasError as erro:
        raise ApostilaError(str(erro)) from erro
    return {
        "servico": int(servico),
        "codigo_tj": str(conta.get("codigo_tj") or ""),
        "vigencia": int(conta["vigencia"]),
        "emolumentos": int(conta["emolumento_centavos"]),
        "ferc": centavos(conta.get("ferc")),
        "femp": centavos(conta.get("femp")),
        "fadep": centavos(conta.get("fadep")),
        "ferrfis": centavos(conta.get("ferrfis")),
        "total": int(conta["total_centavos"]),
        "avisos": list(conta.get("avisos") or []),
    }


# ------------------------------------------------------------- o pedido


def abrir_pedido(con, *, agora: str, por: str, recebido_em: Any,
                 atribuicao: Any, requerente_nome: Any,
                 requerente_documento: Any = "", requerente_contato: Any = "",
                 pais_destino: Any = "", protocolo: Any = "",
                 observacao: Any = "") -> int:
    """Registra o pedido de apostilamento. **ESCREVE** na transação de quem chama.

    O PROTOCOLO GERAL é opcional aqui (o cliente pode pedir antes de pagar),
    mas, se vier, tem de existir: número digitado errado seria a cobrança
    apontando para o atendimento de outra pessoa.
    """
    hoje = str(agora)[:10]
    sigla = str(atribuicao or "").strip().upper()
    if sigla not in ATRIBUICOES_LIBERADAS:
        raise ApostilaError(
            "Escolha a atribuição em que a apostila é praticada: "
            + ", ".join(ATR.ATRIBUICOES[ATOS_DE_APOSTILA[s]["atribuicao"]]["nome"]
                        for s in ATRIBUICOES_LIBERADAS) + ".")
    nome = _texto(requerente_nome)
    if not nome:
        raise ApostilaError("Informe quem pede a apostila.")
    documento = cpf_cnpj.so_digitos(requerente_documento)
    if cpf_cnpj.documento_valido(documento) is False:
        raise ApostilaError(cpf_cnpj.mensagem_documento_invalido(documento))
    bd = banco(con)
    protocolo_id, protocolo_numero = None, _texto(protocolo, 30)
    if protocolo_numero:
        achado = bd.um("SELECT id, numero FROM cx_protocolos WHERE numero = %s",
                       (protocolo_numero,)) if bd.tem_tabela("cx_protocolos") else None
        if not achado:
            raise ApostilaError(
                f"O protocolo geral {protocolo_numero} não existe. Confira o "
                f"número no Caixa (AAAA.MM.N).")
        protocolo_id = int(achado["id"])
    return int(bd.escrever(
        """INSERT INTO ap_pedidos (recebido_em, atribuicao, requerente_nome,
               requerente_documento, requerente_contato, pais_destino,
               protocolo_id, protocolo_numero, observacao, criado_em, criado_por)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           RETURNING id""",
        (_dia(recebido_em, campo="a data do pedido", ate=hoje), sigla, nome,
         documento, _texto(requerente_contato, 120), _texto(pais_destino, 80),
         protocolo_id, protocolo_numero, _texto(observacao, 1000), agora,
         _texto(por, 120)))[0]["id"])


def pedido(con, pedido_id: int) -> dict | None:
    """O pedido, com as apostilas dele em ordem de entrada. Só LÊ."""
    bd = banco(con)
    linha = bd.um("SELECT * FROM ap_pedidos WHERE id = %s", (int(pedido_id),))
    if not linha:
        return None
    linha["apostilas"] = [
        a | {"valores": valores_em_reais(a)}
        for a in bd.ler("SELECT * FROM ap_apostilas WHERE pedido_id = %s ORDER BY id",
                        (int(pedido_id),))]
    linha["ato"] = ATOS_DE_APOSTILA.get(linha["atribuicao"], {}).get("ato")
    return linha


def pedidos(con, *, limite: int = 200) -> list[dict]:
    """Os pedidos mais recentes, com a contagem por situação. Só LÊ."""
    return banco(con).ler(
        """SELECT p.id, p.recebido_em, p.atribuicao, p.requerente_nome,
                  p.protocolo_numero,
                  count(a.id) AS documentos,
                  count(a.id) FILTER (WHERE a.situacao = 'PENDENTE') AS pendentes,
                  count(a.id) FILTER (WHERE a.situacao = 'EMITIDA') AS emitidas
             FROM ap_pedidos p
             LEFT JOIN ap_apostilas a ON a.pedido_id = p.id
            GROUP BY p.id
            ORDER BY p.recebido_em DESC, p.id DESC
            LIMIT %s""", (int(limite),))


# ----------------------------------------------------------- o documento


def incluir_documento(con, pedido_id: int, *, agora: str, por: str,
                      documento_tipo: Any, documento_descricao: Any = "",
                      documento_data: Any = "", signatario_nome: Any = "",
                      signatario_cargo: Any = "", autoridade: Any = "",
                      get_setting=None) -> int:
    """Um documento a apostilar, com o valor da tabela do dia. **ESCREVE.**

    UMA APOSTILA POR DOCUMENTO — é o que a Convenção certifica: a assinatura,
    a qualidade de quem assinou e o selo de UM documento público.
    """
    bd = banco(con)
    if not bd.um("SELECT id FROM ap_pedidos WHERE id = %s", (int(pedido_id),)):
        raise ApostilaError("Pedido não encontrado.")
    tipo = str(documento_tipo or "").strip().upper()
    if tipo not in TIPOS_DE_DOCUMENTO:
        raise ApostilaError("Escolha o tipo do documento.")
    descricao = _texto(documento_descricao, 300)
    if tipo == "OUTRO" and not descricao:
        raise ApostilaError("No tipo «Outro», descreva o documento.")
    nome, cargo = _texto(signatario_nome), _texto(signatario_cargo)
    quem_carimba = _texto(autoridade)
    # O REGISTRO DA CONVENÇÃO (art. 7º) pede quem assinou e em que qualidade,
    # OU, no documento sem assinatura, quem apôs o selo ou carimbo.
    if not nome and not quem_carimba:
        raise ApostilaError(
            "Informe quem assinou o documento — ou, se ele não tem assinatura, "
            "a autoridade que pôs o selo ou carimbo. É o que o controle de "
            "apostilas registra.")
    if nome and not cargo:
        raise ApostilaError(
            "Informe o cargo ou a função de quem assinou: a apostila certifica "
            "a qualidade em que ele agiu.")
    hoje = str(agora)[:10]
    valor = calcular_valor(con, servico=servico_configurado(con, get_setting),
                           dia=hoje)
    return int(bd.escrever(
        """INSERT INTO ap_apostilas (pedido_id, documento_tipo,
               documento_descricao, documento_data, signatario_nome,
               signatario_cargo, autoridade, servico, codigo_tj, vigencia,
               emolumentos, ferc, femp, fadep, ferrfis, total, criado_em,
               criado_por)
           VALUES (%(pedido_id)s, %(tipo)s, %(descricao)s, %(data)s, %(nome)s,
               %(cargo)s, %(autoridade)s, %(servico)s, %(codigo_tj)s,
               %(vigencia)s, %(emolumentos)s, %(ferc)s, %(femp)s, %(fadep)s,
               %(ferrfis)s, %(total)s, %(agora)s, %(por)s)
           RETURNING id""",
        {"pedido_id": int(pedido_id), "tipo": tipo, "descricao": descricao,
         "data": _dia(documento_data, campo="a data do documento",
                      obrigatorio=False, ate=hoje),
         "nome": nome, "cargo": cargo, "autoridade": quem_carimba,
         "agora": agora, "por": _texto(por, 120),
         **{k: valor[k] for k in ("servico", "codigo_tj", "vigencia", "emolumentos",
                                  "ferc", "femp", "fadep", "ferrfis", "total")}})[0]["id"])


def _presa(bd, apostila_id: int) -> dict:
    """A apostila com a linha presa, DEPOIS da trava do assunto.

    A ordem é a do `renumerar` da casa: trava de assunto, depois a linha. Ao
    contrário, duas emissões podiam se prender uma na outra.
    """
    bd.travar("ap_apostilas")
    linha = bd.um("SELECT * FROM ap_apostilas WHERE id = %s FOR UPDATE",
                  (int(apostila_id),))
    if not linha:
        raise ApostilaError("Apostila não encontrada.")
    return linha


def _codigo(valor: Any) -> str:
    codigo = " ".join(str(valor or "").upper().split())
    if not _CODIGO.fullmatch(codigo):
        raise ApostilaError(
            "Informe o número/código da apostila exatamente como o sistema do "
            "CNJ o imprimiu (letras, números e separadores).")
    return codigo


def _selo(valor: Any) -> str:
    return " ".join(str(valor or "").upper().split())[:60]


def itens_para_cobrar(con, pedido_id: int, get_setting=None) -> list[dict]:
    """Os itens do protocolo geral do pedido que podem pagar uma apostila. Só LÊ.

    Só o item do MESMO serviço (ou do mesmo código da tabela): gastar a
    unidade de uma certidão para fechar uma apostila deixaria a certidão sem
    pagamento e a conferência de fundos sem fechar.
    """
    bd = banco(con)
    p = bd.um("SELECT protocolo_id FROM ap_pedidos WHERE id = %s", (int(pedido_id),))
    if not p or p["protocolo_id"] is None:
        return []
    servico = servico_configurado(con, get_setting)
    tj = {str(s["codigo_tj"] or "") for s in servicos_da_tabela(con)}
    return [i for i in CXP.itens_disponiveis(con, p["protocolo_id"])
            if (servico is not None and i.get("servico_codigo") == servico)
            or str(i.get("codigo_ato") or "").strip() in tj]


def emitir(con, apostila_id: int, *, agora: str, por: str, codigo_cnj: Any,
           emitida_em: Any, selo: Any = "", protocolo_item_id: Any = None,
           get_setting=None) -> dict:
    """Registra a apostila que o sistema do CNJ emitiu. **ESCREVE.**

    É aqui que nasce o número de ordem do controle — com a trava do assunto,
    para duas emissões não lerem o mesmo maior. O item do protocolo geral,
    se vier, é consumido na mesma transação: ou as duas coisas ficam, ou
    nenhuma.
    """
    hoje = str(agora)[:10]
    codigo = _codigo(codigo_cnj)
    dia = _dia(emitida_em, campo="a data da emissão", ate=hoje)
    numero_do_selo = _selo(selo)
    bd = banco(con)
    linha = _presa(bd, apostila_id)
    if linha["situacao"] != PENDENTE:
        raise ApostilaError(
            f"Esta apostila está «{SITUACOES[linha['situacao']]}» e não pode ser "
            f"emitida de novo.")
    if bd.um("SELECT id FROM ap_apostilas WHERE codigo_cnj = %s AND id <> %s",
             (codigo, int(apostila_id))):
        raise ApostilaError(f"O código {codigo} já está no controle, em outra apostila.")
    if numero_do_selo and bd.um(
            "SELECT id FROM ap_apostilas WHERE selo = %s AND id <> %s",
            (numero_do_selo, int(apostila_id))):
        raise ApostilaError(f"O selo {numero_do_selo} já está em outra apostila.")
    item_id = None
    if str(protocolo_item_id or "").strip():
        item_id = int(str(protocolo_item_id).strip())
        validos = {int(i["id"]) for i in itens_para_cobrar(con, linha["pedido_id"],
                                                         get_setting)}
        if item_id not in validos:
            raise ApostilaError(
                "Esse item do protocolo geral não é da apostila ou já foi "
                "todo usado. Escolha um item da Apostila de Haia com saldo.")
    ordem = int(bd.valor("SELECT coalesce(max(ordem), 0) + 1 AS n FROM ap_apostilas"))
    bd.escrever(
        """UPDATE ap_apostilas
              SET situacao = 'EMITIDA', ordem = %s, codigo_cnj = %s,
                  emitida_em = %s, emitida_por = %s,
                  selo = %s, selo_em = %s, selo_por = %s,
                  protocolo_item_id = %s
            WHERE id = %s""",
        (ordem, codigo, dia, _texto(por, 120),
         numero_do_selo or None, agora if numero_do_selo else None,
         _texto(por, 120) if numero_do_selo else "", item_id, int(apostila_id)))
    if item_id is not None:
        if not CXP.consumir_item(con, item_id, ato_id=int(apostila_id),
                                 tabela="ap_apostilas", agora=agora):
            raise ApostilaError("O item do protocolo geral ficou sem saldo. Tente de novo.")
    return {"ordem": ordem, "codigo_cnj": codigo, "protocolo_item_id": item_id}


def registrar_selo(con, apostila_id: int, *, agora: str, por: str, selo: Any) -> str:
    """O selo que chegou depois da emissão. **ESCREVE.** Não troca selo gravado."""
    numero = _selo(selo)
    if not numero:
        raise ApostilaError("Informe o número do selo.")
    bd = banco(con)
    linha = _presa(bd, apostila_id)
    if linha["situacao"] != EMITIDA:
        raise ApostilaError("Só a apostila emitida recebe selo.")
    if linha["selo"]:
        raise ApostilaError(
            f"Esta apostila já tem o selo {linha['selo']}. Selo gravado não se "
            f"troca por aqui: o erro de selo se resolve com o Tribunal.")
    if bd.um("SELECT id FROM ap_apostilas WHERE selo = %s AND id <> %s",
             (numero, int(apostila_id))):
        raise ApostilaError(f"O selo {numero} já está em outra apostila.")
    bd.escrever("UPDATE ap_apostilas SET selo = %s, selo_em = %s, selo_por = %s WHERE id = %s",
                (numero, agora, _texto(por, 120), int(apostila_id)))
    return numero


def recusar(con, apostila_id: int, *, agora: str, por: str, motivo: Any) -> None:
    """O documento que não se apostila (assinatura que não se confere, documento
    que não é público). **ESCREVE.** Não ocupa número de ordem."""
    texto = _motivo(motivo)
    bd = banco(con)
    linha = _presa(bd, apostila_id)
    if linha["situacao"] != PENDENTE:
        raise ApostilaError("Só o documento que ainda não foi emitido pode ser recusado.")
    bd.escrever(
        """UPDATE ap_apostilas SET situacao = 'RECUSADA', motivo = %s,
                  encerrada_em = %s, encerrada_por = %s WHERE id = %s""",
        (texto, agora, _texto(por, 120), int(apostila_id)))


def cancelar(con, apostila_id: int, *, agora: str, por: str, motivo: Any) -> dict:
    """A apostila emitida que foi cancelada no sistema do CNJ. **ESCREVE.**

    O NÚMERO DE ORDEM FICA: a linha continua no controle, marcada, com o
    motivo. E a unidade do protocolo geral VOLTA (`devolver_item`) — o cliente
    pagou uma apostila, e a que vier no lugar desta usa o mesmo pagamento.
    """
    texto = _motivo(motivo)
    bd = banco(con)
    linha = _presa(bd, apostila_id)
    if linha["situacao"] != EMITIDA:
        raise ApostilaError("Só a apostila emitida pode ser cancelada.")
    bd.escrever(
        """UPDATE ap_apostilas SET situacao = 'CANCELADA', motivo = %s,
                  encerrada_em = %s, encerrada_por = %s WHERE id = %s""",
        (texto, agora, _texto(por, 120), int(apostila_id)))
    voltou = 0
    if linha["protocolo_item_id"] is not None:
        voltou = CXP.devolver_item(con, int(linha["protocolo_item_id"]), quantas=1)
    return {"ordem": linha["ordem"], "unidade_devolvida": bool(voltou)}


def apostila(con, apostila_id: int) -> dict | None:
    """Uma apostila, com o pedido (para a certidão). Só LÊ."""
    linha = banco(con).um(
        """SELECT a.*, p.recebido_em, p.atribuicao, p.requerente_nome,
                  p.pais_destino, p.protocolo_numero
             FROM ap_apostilas a JOIN ap_pedidos p ON p.id = a.pedido_id
            WHERE a.id = %s""", (int(apostila_id),))
    if linha:
        linha["valores"] = valores_em_reais(linha)
        linha["tipo_nome"] = TIPOS_DE_DOCUMENTO.get(linha["documento_tipo"], "")
    return linha


# ---------------------------------------------------- controle e rastro


def controle(con, *, de: Any = "", ate: Any = "") -> dict:
    """O controle das apostilas emitidas no período, na ordem do número. Só LÊ.

    Entram as EMITIDAS e as CANCELADAS depois de emitidas — as duas ocupam
    número, e o controle sem a cancelada teria um buraco sem explicação. A
    soma do valor é só das que ficaram emitidas.
    """
    inicio = _dia(de, campo="o início do período", obrigatorio=False) or "0001-01-01"
    fim = _dia(ate, campo="o fim do período", obrigatorio=False) or "9999-12-31"
    linhas = banco(con).ler(
        """SELECT a.*, p.requerente_nome, p.atribuicao, p.protocolo_numero
             FROM ap_apostilas a JOIN ap_pedidos p ON p.id = a.pedido_id
            WHERE a.ordem IS NOT NULL
              AND a.emitida_em >= %s AND a.emitida_em <= %s
            ORDER BY a.ordem""", (inicio, fim))
    for linha in linhas:
        linha["valores"] = valores_em_reais(linha)
        linha["tipo_nome"] = TIPOS_DE_DOCUMENTO.get(linha["documento_tipo"], "")
    emitidas = [x for x in linhas if x["situacao"] == EMITIDA]
    return {
        "de": "" if inicio == "0001-01-01" else inicio,
        "ate": "" if fim == "9999-12-31" else fim,
        "linhas": linhas,
        "emitidas": len(emitidas),
        "canceladas": len(linhas) - len(emitidas),
        "total": reais(sum(int(x["total"] or 0) for x in emitidas)),
        "emolumentos": reais(sum(int(x["emolumentos"] or 0) for x in emitidas)),
    }


def pendencias(con) -> list[dict]:
    """O que a apostila ainda deve: emissão, selo e cobrança. Só LÊ.

    É a lista que impede a apostila emitida de ficar sem selo, ou sem o
    pagamento apontado, sem que ninguém perceba.
    """
    bd = banco(con)
    saida = []
    for linha in bd.ler(
            """SELECT a.id, a.pedido_id, a.situacao, a.ordem, a.codigo_cnj,
                      a.selo, a.protocolo_item_id, a.criado_em
                 FROM ap_apostilas a
                WHERE a.situacao = 'PENDENTE'
                   OR (a.situacao = 'EMITIDA'
                       AND (a.selo IS NULL OR a.protocolo_item_id IS NULL))
                ORDER BY a.criado_em, a.id"""):
        if linha["situacao"] == PENDENTE:
            saida.append(linha | {"falta": "emissão no sistema do CNJ"})
            continue
        if not linha["selo"]:
            saida.append(linha | {"falta": "selo"})
        if linha["protocolo_item_id"] is None:
            saida.append(linha | {"falta": "cobrança no protocolo geral"})
    return saida
