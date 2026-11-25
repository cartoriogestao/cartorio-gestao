"""O VALOR DE TERCEIRO DA MATERIALIZAÇÃO e o SALDO DE REPASSE DA CRC.

F010 do agente financeiro (25/11/2026), a solução B do estudo CR004, escolhida
pelo titular no mesmo dia, e refeita no mesmo dia com a explicação dele de como
a CRC cobra.

O QUE ACONTECE NO BALCÃO
    O cliente pede, pela CRC, a certidão de um registro que mora em outro
    cartório. Esta casa cobra a MATERIALIZAÇÃO (item 14.5.1, no protocolo,
    como qualquer ato) e recebe também o que o cartório de origem cobra pela
    certidão. Essa segunda parte entra no caixa SABENDO DE ONDE VEIO: o pedido
    da CRC e o cartório de origem.

COMO A CRC COBRA (o titular, 25/11/2026)
    O outro cartório não recebe de nós: a CRC paga a ele com o SALDO que esta
    casa tem lá. Esse saldo pode se manter sozinho — as certidões que esta casa
    emite para pedidos de outros cartórios entram nele e pagam as que ela pede
    — ou pode precisar de recarga. Por isso o dinheiro do cliente não vai, um
    pedido por vez, ao cartório de origem: ele forma o SALDO DE REPASSE DA CRC,
    que o oficial DESTINA (`DESTINOS`), no valor que quiser, até o saldo:
      - ENVIAR À CRC: completar o saldo de lá. Sai por uma despesa da categoria
        `REPASSE_SERVENTIA_CRC` (natureza REPASSE: fora do Livro Diário e do
        SIAFERJ), paga, e com o comprovante;
      - TRANSFORMAR EM CAIXA: quando o saldo da CRC se paga com as certidões
        emitidas, o dinheiro fica na casa. Ele já está na gaveta ou na conta
        (o fechamento o conta desde a entrada): nada se lança no caixa, só se
        registra que ele deixou de ser saldo de repasse.

POR QUE UMA NATUREZA PRÓPRIA NO CAIXA (`VALOR_DE_TERCEIRO`)
    Lançado como RECEBIMENTO, o valor viraria receita do titular (o
    carnê-leão o estima como renda), base do ISS e «selos × caixa» com
    diferença sem explicação. Aqui ele entra numa natureza que NENHUM leitor
    conta como receita — e cada leitor diz isso com todas as letras e com
    teste: o relatório financeiro (bloco próprio), o carnê-leão, a NFS-e e o
    ISS, o Livro Diário (a receita sai do selo, que é o do 14.5.1) e «selos ×
    caixa» do mês.
    O VALOR QUE VIRA CAIXA TAMBÉM NÃO VIRA RECEITA AQUI. O saldo da CRC que
    pagou o outro cartório veio das certidões que esta casa emitiu, e essas já
    são receita no recebimento delas («PG feito pela CRC»): contar de novo o
    dinheiro do cliente seria contar duas vezes. Se o contador disser outra
    coisa, é pergunta aberta (relatório F010), e não regra inventada aqui.

O PEDIDO (`rc_materializacao_repasses`, um por pedido da CRC)
    Ligado ao protocolo do balcão, ao lançamento do caixa e — quando o selo
    sair — à materialização. As situações:
        RECEBIDO   (está no saldo de repasse da CRC)
        DEVOLVIDO  (o pedido não deu certo e o dinheiro voltou ao cliente)
        CANCELADO  (o lançamento do caixa foi desfeito)
    O MESMO PEDIDO NÃO SE RECEBE DUAS VEZES: a regra mora no banco.

O SALDO (`saldo`)
    Recebido (pedidos RECEBIDO com o lançamento vivo) menos o destinado
    (`rc_crc_saldo_destinacoes`). Não se destina mais do que há, e não se
    devolve nem se estorna o que o saldo já não cobre: o dinheiro já foi para
    a CRC ou para o caixa.

O QUE ESTE MÓDULO NÃO DECIDE (perguntas do titular, relatório F010)
    Quem paga a taxa da CRC: `rc_repasse_cobra_taxa_crc` (0) — a taxa só entra
    no valor do cliente com a chave ligada.

MEDIDO EM 25/11/2026 (produção, só leitura)
    Nenhuma materialização registrada nem selada. O envelope do selo manda
    `codigoAto: "14.5.1"` e o valor de origem num campo próprio
    (`valorEmolumentosCertidao`). Nos 1.251 selos do acervo com «Ato: 14.5.1»
    o texto do TJ declara sempre o valor DA TABELA para o 14.5.1, e nunca um
    valor digitado; no caminho da materialização, só o primeiro selo prova.
    ESTE MÓDULO NÃO MEXE NO SELO, nem no FERJ e no FERC.

PostgreSQL nativo, pelo `bd_nativo`. Dinheiro em centavos. Data e hora se
calculam no Python (regra da casa).
"""
from __future__ import annotations

from datetime import date
from typing import Any

from bd_nativo import banco
from caixa_schema import centavos, hash_lancamento, reais

TABELA = "rc_materializacao_repasses"
TABELA_DESTINOS = "rc_crc_saldo_destinacoes"
NATUREZA = "VALOR_DE_TERCEIRO"
ORIGEM = "TERCEIRO_MATERIALIZACAO"
CODIGO_DA_MATERIALIZACAO = "14.5.1"
#: A categoria do módulo de despesas por onde o envio à CRC sai da conta.
CATEGORIA_DA_DESPESA = "REPASSE_SERVENTIA_CRC"

RECEBIDO, DEVOLVIDO, CANCELADO = "RECEBIDO", "DEVOLVIDO", "CANCELADO"
SITUACOES = {
    RECEBIDO: "Recebido — no saldo de repasse da CRC",
    DEVOLVIDO: "Devolvido ao cliente",
    CANCELADO: "Cancelado — o lançamento do caixa foi desfeito",
}
#: As situações em que o pedido ainda ocupa a vaga (índice único).
VIVAS = (RECEBIDO,)

ENVIO_CRC, CAIXA = "CRC", "CAIXA"
#: Para onde o saldo de repasse vai. `despesa` diz se exige a despesa paga.
DESTINOS: dict[str, dict[str, Any]] = {
    ENVIO_CRC: {"rotulo": "Enviar à CRC (completar o saldo de lá)",
                "curto": "enviado à CRC", "despesa": True},
    CAIXA: {"rotulo": "Transformar em caixa (o saldo da CRC se paga sozinho)",
            "curto": "transformado em caixa", "despesa": False},
}
SITUACOES_DA_DESPESA_PAGA = ("PAGA", "CONCILIADA", "PAGA_FORA")

CHAVE_DA_TAXA_CRC = "rc_repasse_cobra_taxa_crc"

TRAVA = "rc_materializacao_repasses.saldo"

SCHEMA = (
    ("rc_materializacao_repasses", """
        CREATE TABLE IF NOT EXISTS rc_materializacao_repasses (
            id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            protocolo_id bigint NOT NULL REFERENCES cx_protocolos(id),
            pedido_crc TEXT NOT NULL,              -- o nº do pedido na CRC
            materializacao_id bigint REFERENCES rc_materializacoes(id),
            cartorio_nome TEXT NOT NULL,           -- de onde veio a certidão
            cartorio_cidade TEXT NOT NULL,
            cartorio_uf TEXT NOT NULL,
            emolumentos_origem_centavos bigint NOT NULL DEFAULT 0,
            fundos_origem_centavos bigint NOT NULL DEFAULT 0,
            taxa_crc_centavos bigint NOT NULL DEFAULT 0,
            valor_centavos bigint NOT NULL CHECK (valor_centavos > 0),
            lancamento_id bigint REFERENCES cx_lancamentos(id),
            recebido_em TEXT NOT NULL,
            situacao TEXT NOT NULL DEFAULT 'RECEBIDO',
            devolucao_lancamento_id bigint REFERENCES cx_lancamentos(id),
            motivo_encerramento TEXT,
            encerrado_em TEXT,
            encerrado_por TEXT,
            criado_em TEXT NOT NULL,
            criado_por TEXT
        )"""),
    # O MESMO PEDIDO NÃO SE RECEBE DUAS VEZES — a regra mora no banco. O
    # devolvido e o cancelado soltam a vaga.
    ("ux_rc_mat_repasse_pedido_vivo", """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_rc_mat_repasse_pedido_vivo
            ON rc_materializacao_repasses (pedido_crc)
         WHERE situacao = 'RECEBIDO'"""),
    ("ux_rc_mat_repasse_lancamento", """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_rc_mat_repasse_lancamento
            ON rc_materializacao_repasses (lancamento_id)
         WHERE lancamento_id IS NOT NULL"""),
    ("ix_rc_mat_repasse_protocolo", """
        CREATE INDEX IF NOT EXISTS ix_rc_mat_repasse_protocolo
            ON rc_materializacao_repasses (protocolo_id)"""),
    # Para onde o saldo foi. Uma linha por decisão do oficial, no valor que
    # ele escolheu — não por pedido: a CRC cobra do saldo, e não do pedido.
    ("rc_crc_saldo_destinacoes", """
        CREATE TABLE IF NOT EXISTS rc_crc_saldo_destinacoes (
            id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            destino TEXT NOT NULL CHECK (destino IN ('CRC', 'CAIXA')),
            valor_centavos bigint NOT NULL CHECK (valor_centavos > 0),
            dia TEXT NOT NULL,
            despesa_id bigint,                     -- o envio à CRC
            comprovante TEXT,
            observacao TEXT,
            criado_em TEXT NOT NULL,
            criado_por TEXT
        )"""),
    # O pedido também fica na materialização, para o selo se ligar ao valor
    # recebido. Coluna opcional: a materialização de antes não tem pedido.
    ("rc_materializacoes.pedido_crc", """
        ALTER TABLE rc_materializacoes ADD COLUMN IF NOT EXISTS pedido_crc TEXT"""),
)


class RepasseTerceiroError(ValueError):
    """Impedimento de regra, com a frase pronta para o balcão."""


def init_rc_materializacao_repasse_schema(con) -> None:
    """Cria as tabelas. Idempotente. Vem depois do caixa (chaves estrangeiras)."""
    bd = banco(con)
    for _nome, sql in SCHEMA:
        bd.escrever(sql)


# ------------------------------------------------------------ a configuração


def _setting(bd, chave: str) -> str:
    if not bd.tem_tabela("settings"):
        return ""
    linha = bd.um("SELECT value FROM settings WHERE key=%s", (chave,))
    return str((linha or {}).get("value") or "").strip()


def cobra_taxa_da_crc(con) -> bool:
    """A taxa da CRC entra no valor que o cliente paga? Só LÊ. Padrão: não."""
    return _setting(banco(con), CHAVE_DA_TAXA_CRC) == "1"


def _limpo(valor: Any) -> str:
    return " ".join(str(valor or "").split())


def _dia(valor: Any, rotulo: str) -> str:
    try:
        return date.fromisoformat(str(valor or "")[:10]).isoformat()
    except ValueError:
        raise RepasseTerceiroError(f"Informe {rotulo}.") from None


# ---------------------------------------------------------- o recebimento


def conferir(dados: dict, *, taxa_permitida: bool = False) -> dict:
    """Confere o que o balcão digitou e devolve limpo, em centavos. Só calcula."""
    limpo = {k: _limpo(dados.get(k)) for k in (
        "pedido_crc", "cartorio_nome", "cartorio_cidade", "cartorio_uf",
        "forma_pagamento", "pagador", "pagador_documento")}
    limpo["pedido_crc"] = limpo["pedido_crc"].upper()
    limpo["cartorio_uf"] = limpo["cartorio_uf"].upper()
    faltando = [rotulo for chave, rotulo in (
        ("pedido_crc", "o número do pedido na CRC"),
        ("cartorio_nome", "o nome do cartório de origem"),
        ("cartorio_cidade", "a cidade do cartório de origem"),
        ("cartorio_uf", "a UF do cartório de origem"),
        ("forma_pagamento", "a forma de pagamento"))
        if not limpo[chave]]
    valores = {}
    for campo, rotulo, obrigatorio in (
            ("emolumentos_origem", "os emolumentos cobrados lá", True),
            ("fundos_origem", "os fundos cobrados lá", False),
            ("taxa_crc", "a taxa da CRC", False)):
        bruto = str(dados.get(campo) or "").strip()
        if not bruto:
            if obrigatorio:
                faltando.append(rotulo)
            valores[campo] = 0
            continue
        try:
            v = centavos(bruto)
        except (TypeError, ValueError):
            v = -1
        if v < 0:
            raise RepasseTerceiroError(f"Não entendi o valor de {rotulo}: «{bruto}».")
        valores[campo] = v
    if faltando:
        raise RepasseTerceiroError(
            "Para receber o valor do outro cartório falta " + ", ".join(faltando) + ".")
    if len(limpo["cartorio_uf"]) != 2 or not limpo["cartorio_uf"].isalpha():
        raise RepasseTerceiroError("A UF do cartório de origem tem duas letras (ex.: PI).")
    if valores["taxa_crc"] and not taxa_permitida:
        raise RepasseTerceiroError(
            "A taxa da CRC não entra no valor do cliente: quem paga essa taxa "
            "ainda não foi decidido pelo titular (chave "
            f"«{CHAVE_DA_TAXA_CRC}»). Receba só os emolumentos e os fundos de lá.")
    total = sum(valores.values())
    if total <= 0:
        raise RepasseTerceiroError("O valor do outro cartório tem de ser maior que zero.")
    if limpo["forma_pagamento"] in ("GRATUITO", "DEPOSITO_PREVIO", "PG_CRC", "PG_ONR"):
        raise RepasseTerceiroError(
            "Esta forma não serve para valor de terceiro: ele é dinheiro que o "
            "cliente entrega agora. O depósito prévio vira receita no uso, e «PG "
            "feito pela CRC» é receita que a Central paga a esta casa.")
    limpo.update({f"{k}_centavos": v for k, v in valores.items()})
    limpo["valor_centavos"] = total
    return limpo


def _protocolo_da_materializacao(bd, protocolo_id: int) -> dict:
    p = bd.um("SELECT * FROM cx_protocolos WHERE id=%s", (int(protocolo_id),))
    if not p:
        raise RepasseTerceiroError("Protocolo não encontrado.")
    if str(p.get("situacao") or "").upper() in ("CANCELADO", "ENTREGUE"):
        raise RepasseTerceiroError(
            f"O protocolo {p['numero']} está {str(p['situacao']).lower()}: abra "
            f"(ou reabra) o atendimento antes de receber.")
    if str(p.get("atribuicao") or "").upper() != "RCPN":
        raise RepasseTerceiroError(
            f"O protocolo {p['numero']} não é do Registro Civil: a materialização "
            f"é ato do RCPN, e o valor do outro cartório vai no protocolo dela.")
    if str(p.get("tipo") or "SERVICO").upper() == "ORCAMENTO":
        raise RepasseTerceiroError(
            f"O protocolo {p['numero']} é só orçamento: não recebe dinheiro.")
    tem_item = bd.valor(
        """SELECT count(*) AS n FROM cx_protocolo_atos
            WHERE protocolo_id=%s AND trim(coalesce(codigo_ato, '')) = %s""",
        (int(protocolo_id), CODIGO_DA_MATERIALIZACAO))
    if not tem_item:
        raise RepasseTerceiroError(
            f"O protocolo {p['numero']} não tem o item {CODIGO_DA_MATERIALIZACAO} "
            f"(materialização). O valor do outro cartório anda junto com ela: "
            f"acrescente o item antes.")
    return p


def descricao_do_lancamento(d: dict) -> str:
    return (f"Valor de terceiro — certidão do {d['cartorio_nome']} "
            f"({d['cartorio_cidade']}/{d['cartorio_uf']}), pedido CRC nº "
            f"{d['pedido_crc']}. Saldo de repasse da CRC; não é emolumento desta "
            f"serventia.")


def receber(con, protocolo_id: int, dados: dict, *, caixa_id: int, hoje: str,
            hora: str, agora: str, usuario: Any = None, usuario_id: Any = None) -> dict:
    """Recebe o valor do outro cartório: o registro e o lançamento. ESCREVE.

    O lançamento é `VALOR_DE_TERCEIRO`, de ENTRADA, com as colunas do
    emolumento e dos fundos VAZIAS (não são desta casa) e
    `receita_do_titular = 0`. A chave de origem aponta para o registro."""
    bd = banco(con)
    d = conferir(dados, taxa_permitida=cobra_taxa_da_crc(bd))
    if not caixa_id:
        raise RepasseTerceiroError(
            "Você não tem caixa aberto, e sem caixa o dinheiro não aparece na "
            "conferência do dia. Abra o caixa em Administrativo → Caixa.")
    p = _protocolo_da_materializacao(bd, protocolo_id)
    bd.travar(TRAVA)
    ja = bd.um(
        f"""SELECT id, protocolo_id FROM {TABELA}
             WHERE pedido_crc=%s AND situacao = ANY(%s) ORDER BY id LIMIT 1""",
        (d["pedido_crc"], list(VIVAS)))
    if ja:
        raise RepasseTerceiroError(
            f"O pedido CRC nº {d['pedido_crc']} já foi recebido (registro "
            f"{ja['id']}). Receber de novo cobraria o cliente duas vezes.")
    repasse_id = int(bd.escrever(
        f"""INSERT INTO {TABELA}(protocolo_id, pedido_crc, cartorio_nome,
               cartorio_cidade, cartorio_uf, emolumentos_origem_centavos,
               fundos_origem_centavos, taxa_crc_centavos, valor_centavos,
               recebido_em, situacao, criado_em, criado_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'RECEBIDO',%s,%s)
           RETURNING id""",
        (int(protocolo_id), d["pedido_crc"], d["cartorio_nome"],
         d["cartorio_cidade"], d["cartorio_uf"], d["emolumentos_origem_centavos"],
         d["fundos_origem_centavos"], d["taxa_crc_centavos"], d["valor_centavos"],
         str(hoje)[:10], agora, str(usuario or "") or None))[0]["id"])
    # O LANÇAMENTO, no mesmo jeito do lançamento do balcão (`caixa_web`):
    # número de ordem do ano e hash encadeado no último DO MESMO CAIXA — uma
    # das duas grafias que a conferência da cadeia aceita (`compliance`).
    descricao = descricao_do_lancamento(d)
    ano = int(str(hoje)[:4])
    bd.travar("cx_lancamentos.numero")
    anterior = bd.valor(
        """SELECT hash_lancamento FROM cx_lancamentos
            WHERE caixa_id=%s ORDER BY id DESC LIMIT 1""", (int(caixa_id),))
    numero = int(bd.valor("SELECT MAX(numero) AS n FROM cx_lancamentos WHERE ano=%s",
                          (ano,)) or 0) + 1
    valor = reais(d["valor_centavos"])
    h = hash_lancamento(int(caixa_id), str(hoje)[:10], NATUREZA, valor, descricao,
                        anterior)
    lancamento_id = int(bd.escrever(
        """INSERT INTO cx_lancamentos(numero, ano, caixa_id, protocolo_id, data,
               hora, natureza, sentido, forma_pagamento, descricao, pagador,
               pagador_documento, valor, hash_lancamento, origem, origem_chave,
               criado_em, criado_por, receita_do_titular)
           VALUES (%s,%s,%s,%s,%s,%s,%s,'ENTRADA',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,0)
           RETURNING id""",
        (numero, ano, int(caixa_id), int(protocolo_id), str(hoje)[:10], hora,
         NATUREZA, d["forma_pagamento"], descricao,
         d["pagador"] or p.get("interessado"),
         d["pagador_documento"] or p.get("interessado_documento"),
         valor, h, ORIGEM, f"{TABELA}:{repasse_id}", agora,
         int(usuario_id) if str(usuario_id or "").isdigit() else None))[0]["id"])
    bd.escrever(f"UPDATE {TABELA} SET lancamento_id=%s WHERE id=%s",
                (lancamento_id, repasse_id))
    return {"repasse_id": repasse_id, "lancamento_id": lancamento_id,
            "lancamento": f"{numero}/{ano}", "valor_centavos": d["valor_centavos"],
            "protocolo": p["numero"], "pedido_crc": d["pedido_crc"]}


# ------------------------------------------------------------- as leituras


_SELECT = f"""
    SELECT r.*, p.numero AS protocolo_numero, p.interessado,
           l.numero AS lancamento_numero, l.ano AS lancamento_ano,
           l.forma_pagamento, l.recibo_id,
           coalesce(l.estornado, 0) AS lancamento_estornado,
           coalesce(l.excluido, 0) AS lancamento_excluido,
           m.selo AS materializacao_selo
      FROM {TABELA} r
      JOIN cx_protocolos p ON p.id = r.protocolo_id
      LEFT JOIN cx_lancamentos l ON l.id = r.lancamento_id
      LEFT JOIN rc_materializacoes m ON m.id = r.materializacao_id
"""


def _enfeitar(linha: dict) -> dict:
    d = dict(linha)
    d["lancamento_vivo"] = bool(d.get("lancamento_id")) and not (
        int(d.get("lancamento_estornado") or 0) or int(d.get("lancamento_excluido") or 0))
    d["situacao_rotulo"] = SITUACOES.get(d["situacao"], d["situacao"])
    d["valor"] = reais(int(d["valor_centavos"]))
    return d


def registro(con, repasse_id: int) -> dict | None:
    linha = banco(con).um(_SELECT + " WHERE r.id=%s", (int(repasse_id),))
    return _enfeitar(linha) if linha else None


def do_protocolo(con, protocolo_id: int) -> list[dict]:
    """Os valores de terceiro de um protocolo, do mais velho ao mais novo. Só LÊ."""
    return [_enfeitar(x) for x in banco(con).ler(
        _SELECT + " WHERE r.protocolo_id=%s ORDER BY r.id", (int(protocolo_id),))]


def listar(con, *, limite: int = 100) -> list[dict]:
    return [_enfeitar(x) for x in banco(con).ler(
        _SELECT + " ORDER BY r.id DESC LIMIT %s", (int(limite),))]


def destinacoes(con, *, limite: int = 100) -> list[dict]:
    """Para onde o saldo foi, da mais nova à mais velha. Só LÊ."""
    bd = banco(con)
    if not bd.tem_tabela(TABELA_DESTINOS):
        return []
    saida = []
    for x in bd.ler(f"SELECT * FROM {TABELA_DESTINOS} ORDER BY id DESC LIMIT %s",
                    (int(limite),)):
        d = dict(x)
        d["valor"] = reais(int(d["valor_centavos"]))
        d["destino_rotulo"] = DESTINOS.get(d["destino"], {}).get("curto", d["destino"])
        saida.append(d)
    return saida


def saldo(con) -> dict:
    """O saldo de repasse da CRC: o recebido menos o destinado. Só LÊ.

    Recebido é o pedido RECEBIDO com o lançamento vivo — o estornado ou
    excluído no caixa sai sozinho, porque o dinheiro não ficou."""
    bd = banco(con)
    recebido = int(bd.valor(
        f"""SELECT coalesce(sum(r.valor_centavos), 0) AS n FROM {TABELA} r
              JOIN cx_lancamentos l ON l.id = r.lancamento_id
             WHERE r.situacao = 'RECEBIDO'
               AND coalesce(l.estornado, 0) = 0 AND coalesce(l.excluido, 0) = 0""") or 0)
    por_destino = {k: 0 for k in DESTINOS}
    if bd.tem_tabela(TABELA_DESTINOS):
        for x in bd.ler(f"""SELECT destino, coalesce(sum(valor_centavos), 0) AS n
                              FROM {TABELA_DESTINOS} GROUP BY destino ORDER BY destino"""):
            por_destino[x["destino"]] = int(x["n"] or 0)
    livre = recebido - sum(por_destino.values())
    return {"recebido_centavos": recebido,
            "enviado_crc_centavos": por_destino[ENVIO_CRC],
            "em_caixa_centavos": por_destino[CAIXA],
            "saldo_centavos": livre,
            "recebido": reais(recebido), "enviado_crc": reais(por_destino[ENVIO_CRC]),
            "em_caixa": reais(por_destino[CAIXA]), "saldo": reais(max(livre, 0))}


def pendentes(con, *, hoje: str | None = None) -> dict:
    """O saldo e o que precisa de alguém. Só LÊ.

    `no_saldo`: os pedidos recebidos com o lançamento vivo, de onde o saldo
    veio. `desfeitos`: o lançamento do caixa foi estornado ou excluído e o
    registro continua RECEBIDO — alguém tem de encerrá-lo. Não há prazo: a CRC
    cobra do saldo dela, e quando recarregar é decisão do oficial."""
    linhas = [_enfeitar(x) for x in banco(con).ler(
        _SELECT + " WHERE r.situacao = 'RECEBIDO' ORDER BY r.id")]
    s = saldo(con)
    return {"no_saldo": [x for x in linhas if x["lancamento_vivo"]],
            "desfeitos": [x for x in linhas if not x["lancamento_vivo"]],
            "saldo": s}


def terceiros_para_o_recibo(con, protocolo_id: int) -> list[dict]:
    """Os valores de terceiro do protocolo que entram no recibo. Só LÊ.

    Os vivos e ainda sem recibo — a mesma regra do recibo do item: um real
    não sai em dois papéis. Cada um com a discriminação de lá."""
    saida = []
    for x in do_protocolo(con, protocolo_id):
        if not x["lancamento_vivo"] or x.get("recibo_id"):
            continue
        if x["situacao"] not in VIVAS:
            continue
        saida.append(bloco_do_recibo(x))
    return saida


def bloco_do_recibo(x: dict) -> dict:
    """A linha do valor de terceiro como ela fica congelada no recibo."""
    return {"lancamento_id": int(x["lancamento_id"]),
            "repasse_id": int(x["id"]),
            "pedido_crc": x["pedido_crc"],
            "cartorio": f"{x['cartorio_nome']} ({x['cartorio_cidade']}/{x['cartorio_uf']})",
            "emolumentos_origem": reais(int(x["emolumentos_origem_centavos"])),
            "fundos_origem": reais(int(x["fundos_origem_centavos"])),
            "taxa_crc": reais(int(x["taxa_crc_centavos"])),
            "valor": reais(int(x["valor_centavos"])),
            "forma_pagamento": x.get("forma_pagamento")}


def do_lancamento(con, lancamento_id: int) -> dict | None:
    """O registro do valor de terceiro ligado a um lançamento. Só LÊ."""
    linha = banco(con).um(_SELECT + " WHERE r.lancamento_id=%s", (int(lancamento_id),))
    return _enfeitar(linha) if linha else None


def _frase_do_saldo_curto(r: dict, livre: int, acao: str) -> str:
    return (f"O valor de terceiro do pedido CRC nº {r['pedido_crc']} (R$ {r['valor']}) "
            f"já não está no saldo de repasse da CRC, que tem R$ {reais(max(livre, 0))}: "
            f"o dinheiro já foi enviado à CRC ou transformado em caixa. {acao} "
            f"desfaria a prova de que ele entrou. Fale com o oficial.")


def recusa_ao_desfazer(con, lancamento_id: int) -> str | None:
    """Pode estornar ou excluir este lançamento? A frase da recusa, ou None.

    Só enquanto o saldo de repasse cobre o valor: se o saldo já foi destinado,
    o dinheiro do cliente já foi para a CRC ou para o caixa, e estornar a
    entrada deixaria o saldo negativo."""
    if not banco(con).tem_tabela(TABELA):
        return None
    r = do_lancamento(con, lancamento_id)
    if not r or r["situacao"] != RECEBIDO or not r["lancamento_vivo"]:
        return None
    livre = saldo(con)["saldo_centavos"]
    if livre < int(r["valor_centavos"]):
        return _frase_do_saldo_curto(r, livre, "Estornar a entrada")
    return None


# ------------------------------------------------- a destinação do saldo


def destinar(con, *, destino: str, valor: Any, dia: Any, hoje: str, agora: str,
             despesa_id: Any = None, comprovante: Any = None, observacao: Any = None,
             usuario: Any = None) -> dict:
    """Destina parte do saldo de repasse da CRC. ESCREVE.

    ENVIO À CRC: pela despesa paga da categoria própria, com o comprovante; a
    soma do que se liga a uma despesa não passa do valor dela. CAIXA: só o
    registro — o dinheiro já está na casa desde a entrada. Nos dois, não se
    destina mais do que o saldo."""
    bd = banco(con)
    chave = str(destino or "").strip().upper()
    if chave not in DESTINOS:
        raise RepasseTerceiroError(
            "Escolha o destino do saldo: "
            + "; ".join(f["rotulo"] for f in DESTINOS.values()) + ".")
    try:
        quanto = centavos(valor) if str(valor or "").strip() else 0
    except (TypeError, ValueError):
        quanto = 0
    if quanto <= 0:
        raise RepasseTerceiroError("Informe o valor a destinar, maior que zero.")
    quando = _dia(dia, "o dia")
    if quando > str(hoje)[:10]:
        raise RepasseTerceiroError("O dia está no futuro: registre quando acontecer.")
    bd.travar(TRAVA)
    livre = saldo(con)["saldo_centavos"]
    if quanto > livre:
        raise RepasseTerceiroError(
            f"O saldo de repasse da CRC é de R$ {reais(max(livre, 0))}: não se destina "
            f"R$ {reais(quanto)}.")
    prova = _limpo(comprovante)
    despesa = None
    if DESTINOS[chave]["despesa"]:
        numero = str(despesa_id or "").strip()
        if not numero.isdigit():
            raise RepasseTerceiroError(
                "Informe o número da despesa (módulo de despesas) que pagou o envio à CRC.")
        if not bd.tem_tabela("dp_despesas"):
            raise RepasseTerceiroError("O módulo de despesas não está instalado.")
        despesa = bd.um("SELECT * FROM dp_despesas WHERE id=%s FOR UPDATE", (int(numero),))
        if not despesa:
            raise RepasseTerceiroError(f"A despesa {numero} não existe.")
        if despesa["categoria"] != CATEGORIA_DA_DESPESA:
            raise RepasseTerceiroError(
                f"A despesa {numero} não é da categoria «Repasse a outra serventia — "
                f"CRC». Em outra categoria ela iria ao Livro Diário e ao SIAFERJ "
                f"como despesa da serventia, e não é.")
        if despesa["situacao"] not in SITUACOES_DA_DESPESA_PAGA:
            raise RepasseTerceiroError(
                f"A despesa {numero} ainda não foi paga: o envio à CRC só se registra "
                f"quando o dinheiro sai.")
        ja_ligado = int(bd.valor(
            f"""SELECT coalesce(sum(valor_centavos), 0) AS n FROM {TABELA_DESTINOS}
                 WHERE despesa_id=%s""", (int(numero),)) or 0)
        if ja_ligado + quanto > int(despesa["valor"]):
            raise RepasseTerceiroError(
                f"A despesa {numero} é de R$ {reais(int(despesa['valor']))} e já leva "
                f"R$ {reais(ja_ligado)} do saldo: R$ {reais(quanto)} não cabem nela.")
        if len(prova) < 3:
            raise RepasseTerceiroError(
                "Informe o comprovante do envio à CRC (autenticação do pagamento ou "
                "número da transação).")
    nova = int(bd.escrever(
        f"""INSERT INTO {TABELA_DESTINOS}(destino, valor_centavos, dia, despesa_id,
               comprovante, observacao, criado_em, criado_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (chave, quanto, quando, int(despesa["id"]) if despesa else None,
         prova or None, _limpo(observacao) or None, agora,
         str(usuario or "") or None))[0]["id"])
    return {"destinacao_id": nova, "destino": chave, "valor_centavos": quanto,
            "despesa_id": int(despesa["id"]) if despesa else None,
            "saldo_centavos": livre - quanto}


# ---------------------------------------------------- o pedido que não vale


def encerrar_sem_repasse(con, repasse_id: int, *, motivo: str, agora: str,
                         devolucao: Any = None, usuario: Any = None) -> dict:
    """Tira do saldo o pedido que não vale. ESCREVE.

    Dois casos, e o sistema não escolhe entre eles — o caixa já disse:
      - o lançamento foi estornado ou excluído: CANCELADO (o dinheiro não
        ficou na casa);
      - o lançamento está vivo: só com a DEVOLUÇÃO ao cliente lançada no caixa
        (natureza «Devolução ao cliente», no mesmo protocolo e do mesmo
        valor), e enquanto o saldo cobre o valor: DEVOLVIDO."""
    bd = banco(con)
    bd.travar(TRAVA)
    linha = bd.um(_SELECT + " WHERE r.id=%s", (int(repasse_id),))
    if not linha:
        raise RepasseTerceiroError(f"Registro {repasse_id} não encontrado.")
    r = _enfeitar(linha)
    if r["situacao"] != RECEBIDO:
        raise RepasseTerceiroError(
            f"O pedido CRC nº {r['pedido_crc']} já está encerrado "
            f"({r['situacao_rotulo'].lower()}).")
    razao = _limpo(motivo)
    if len(razao) < 10:
        raise RepasseTerceiroError(
            "Escreva por que este valor sai do saldo (o pedido foi negado, "
            "cancelado, o lançamento estava errado…).")
    if not r["lancamento_vivo"]:
        bd.escrever(
            f"""UPDATE {TABELA} SET situacao='CANCELADO', motivo_encerramento=%s,
                   encerrado_em=%s, encerrado_por=%s WHERE id=%s""",
            (razao, agora, str(usuario or "") or None, int(repasse_id)))
        return {"repasse_id": int(repasse_id), "situacao": CANCELADO}
    livre = saldo(con)["saldo_centavos"]
    if livre < int(r["valor_centavos"]):
        raise RepasseTerceiroError(_frase_do_saldo_curto(r, livre, "Devolver por aqui"))
    numero = str(devolucao or "").strip()
    if not numero:
        raise RepasseTerceiroError(
            "O dinheiro deste valor continua no caixa. Lance antes a devolução ao "
            "cliente no caixa (natureza «Devolução ao cliente», neste protocolo) e "
            "informe aqui o número do lançamento (nº/ano).")
    dev = None
    if "/" in numero:
        n, _, a = numero.partition("/")
        if n.strip().isdigit() and a.strip().isdigit():
            dev = bd.um("SELECT * FROM cx_lancamentos WHERE numero=%s AND ano=%s",
                        (int(n), int(a)))
    if not dev:
        raise RepasseTerceiroError(f"O lançamento {numero} não existe (use nº/ano).")
    if (dev["natureza"] != "DEVOLUCAO" or dev["sentido"] != "SAIDA"
            or int(dev.get("estornado") or 0) or int(dev.get("excluido") or 0)):
        raise RepasseTerceiroError(
            f"O lançamento {numero} não é uma devolução ao cliente viva.")
    if int(dev.get("protocolo_id") or 0) != int(r["protocolo_id"]):
        raise RepasseTerceiroError(
            f"A devolução {numero} não é do protocolo {r['protocolo_numero']}.")
    if centavos(dev["valor"]) != int(r["valor_centavos"]):
        raise RepasseTerceiroError(
            f"A devolução {numero} é de R$ {dev['valor']}, e o valor de terceiro é "
            f"de R$ {r['valor']}: devolução parcial não encerra o registro.")
    usada = bd.valor(
        f"SELECT count(*) AS n FROM {TABELA} WHERE devolucao_lancamento_id=%s",
        (int(dev["id"]),))
    if usada:
        raise RepasseTerceiroError(f"A devolução {numero} já encerra outro registro.")
    bd.escrever(
        f"""UPDATE {TABELA} SET situacao='DEVOLVIDO', devolucao_lancamento_id=%s,
               motivo_encerramento=%s, encerrado_em=%s, encerrado_por=%s
             WHERE id=%s""",
        (int(dev["id"]), razao, agora, str(usuario or "") or None, int(repasse_id)))
    return {"repasse_id": int(repasse_id), "situacao": DEVOLVIDO}


def vincular_materializacao(con, materializacao_id: int, pedido_crc: Any) -> int:
    """Liga o valor recebido à materialização selada, pelo pedido. ESCREVE.

    Devolve quantos registros ficaram ligados (0 ou 1). Não mexe no selo."""
    pedido = _limpo(pedido_crc).upper()
    bd = banco(con)
    if not pedido or not bd.tem_tabela(TABELA):
        return 0
    feitos = bd.escrever(
        f"""UPDATE {TABELA} SET materializacao_id=%s
             WHERE pedido_crc=%s AND materializacao_id IS NULL
               AND situacao = ANY(%s) RETURNING id""",
        (int(materializacao_id), pedido, list(VIVAS)))
    return len(feitos or [])


# --------------------------------------------------------------- o aviso


def achados(con, *, hoje: str | None = None) -> list[dict]:
    """Os avisos para o oficial: o que ficou torto. Só LÊ.

    Não há aviso de prazo — a CRC cobra do saldo dela, e quando recarregar é
    decisão do oficial. Fica o lançamento desfeito com o registro aberto.
    Cada um com `chave`, `gravidade`, `titulo` e `detalhe` — a forma das regras
    da conferência do gestor (`gestor_conferencia`), que os mostra no painel."""
    bd = banco(con)
    if not bd.tem_tabela(TABELA):
        return []
    return [{
        "chave": f"REPASSE_TERCEIRO_DESFEITO:{x['id']}", "gravidade": "ATENCAO",
        "titulo": (f"Valor de terceiro com o lançamento desfeito — pedido CRC nº "
                   f"{x['pedido_crc']}, R$ {x['valor']}"),
        "detalhe": ("O lançamento do caixa foi estornado ou excluído e o pedido "
                    "continua aberto. Encerre-o em Registro Civil → Materializar "
                    "certidão → Saldo de repasse da CRC."),
        "prazo": None} for x in pendentes(con)["desfeitos"]]


# --------------------------------------------------- o que os leitores usam


def ids_de_devolucao(con) -> set[int]:
    """Os lançamentos de devolução que encerram valor de terceiro. Só LÊ.

    A conferência «selos × caixa» os tira da conta junto com a entrada: os dois
    são dinheiro de terceiro que nenhum selo declara."""
    bd = banco(con)
    if not bd.tem_tabela(TABELA):
        return set()
    return {int(x["devolucao_lancamento_id"]) for x in bd.ler(
        f"""SELECT devolucao_lancamento_id FROM {TABELA}
             WHERE devolucao_lancamento_id IS NOT NULL ORDER BY id""")}
