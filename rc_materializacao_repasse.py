"""O VALOR DE TERCEIRO DA MATERIALIZAÇÃO — o dinheiro do outro cartório, até sair da casa.

F010 do agente financeiro (25/11/2026), a solução B do estudo CR004, escolhida
pelo titular no mesmo dia.

O QUE ACONTECE NO BALCÃO
    O cliente pede, pela CRC, a certidão de um registro que mora em outro
    cartório. Esta casa cobra a MATERIALIZAÇÃO (item 14.5.1, no protocolo,
    como qualquer ato) e recebe também o que o cartório de origem cobra pela
    certidão. Essa segunda parte NÃO É DA CASA: ela passa pelo caixa e sai,
    inteira, para o outro cartório (ou para a CRC, que cobra por ele).

POR QUE UMA NATUREZA PRÓPRIA NO CAIXA (`VALOR_DE_TERCEIRO`)
    Lançado como RECEBIMENTO, o valor viraria receita do titular (o
    carnê-leão o estima como renda), base do ISS (se fosse no campo do
    emolumento) e «selos × caixa» com diferença sem explicação. Lançado como
    «outra entrada», ficaria certo nas contas, mas solto: sem o pedido, sem o
    cartório, sem o aviso do que ainda não foi repassado. Aqui o valor entra
    numa natureza que NENHUM leitor conta como receita — e cada leitor diz
    isso com todas as letras e com teste:
      - relatório financeiro (`gestor_financeiro`): bloco próprio, fora da
        receita e fora das «outras entradas»;
      - carnê-leão (`carne_leao`): só conta RECEBIMENTO e a «outra entrada»
        marcada; esta natureza não é nenhuma das duas;
      - NFS-e e ISS (`nfse.base_do_recibo`): fora da base, e a descrição da
        nota diz que o recibo leva valor de terceiro;
      - Livro Diário (`livro_diario`): a receita sai do SELO, e não do caixa;
        e o selo da materialização é o do 14.5.1 (ver `MEDIDO` abaixo);
      - «selos × caixa» do mês (`gestor_conferencia.regra_fechamento_do_mes`):
        fora da conta do caixa, porque nenhum selo o declara.
    O dinheiro continua no caixa (o fechamento o conta, como conta qualquer
    entrada): ele está na gaveta ou na conta, e a gaveta tem de fechar.

O REPASSE, NO MOLDE DO REPASSE AO APRESENTANTE (`protesto_repasse`)
    Um registro por pedido da CRC (`rc_materializacao_repasses`), ligado ao
    protocolo do balcão, ao lançamento do caixa e — quando o selo sair — à
    materialização. As situações:
        RECEBIDO → REPASSADO → CONCILIADO
        RECEBIDO → DEVOLVIDO   (o pedido não deu certo e o dinheiro voltou)
        RECEBIDO → CANCELADO   (o lançamento do caixa foi desfeito)
    A PENDÊNCIA NASCE DO LANÇAMENTO, e não de uma lista à parte: recebido, com
    o lançamento vivo e sem repasse, É a pendência. O lançamento estornado ou
    excluído sai da pendência e aparece em «desfeitos», para alguém encerrar.
    O MESMO PEDIDO NÃO SE RECEBE DUAS VEZES: a regra mora no banco.

    O REPASSE EXIGE COMPROVANTE, e sai por um dos caminhos que já têm
    autorização do titular (`FORMAS_DE_REPASSE`): a despesa do módulo de
    despesas, na categoria `REPASSE_SERVENTIA_CRC` (natureza REPASSE: fora do
    Livro Diário e do SIAFERJ, como o repasse ao apresentante), ou o débito
    nos créditos que a casa tem na CRC. Repasse em espécie, tirado do caixa,
    NÃO existe aqui: é pergunta aberta ao titular (relatório F010).

O QUE ESTE MÓDULO NÃO DECIDE (perguntas do titular, relatório F010)
    Como a CRC cobra a casa, quem paga a taxa da CRC, se o cliente paga antes
    ou quando a certidão chega, o que fazer com o pedido negado (devolver ou
    deixar crédito) e de onde sai o repasse. Onde a resposta muda o sistema, há
    uma chave em `settings` com o padrão mais seguro:
      - `rc_repasse_prazo_dias_uteis` (1): o prazo DA CASA para o aviso —
        não há prazo legal medido; o padrão curto avisa cedo;
      - `rc_repasse_cobra_taxa_crc` (0): a taxa da CRC só entra no valor do
        cliente com a chave ligada — cobrar do cliente o que o titular não
        decidiu cobrar seria inventar regra.

MEDIDO EM 25/11/2026 (produção, só leitura)
    Nenhuma materialização registrada nem selada (0 em `rc_materializacoes`,
    0 selos pelo caminho da materialização). O envelope do selo manda
    `codigoAto: "14.5.1"` e o valor de origem num campo próprio
    (`valorEmolumentosCertidao`), que descreve a certidão de lá. Nos 1.251
    selos do acervo com «Ato: 14.5.1» (2ª via e atos em geral do civil), o
    texto do TJ declara sempre o valor DA TABELA para o 14.5.1 (Total R$ 53,58
    / Emol R$ 47,84 na vigente), e nunca um valor digitado. Que o TJ faça o
    mesmo no caminho da materialização só se prova com o primeiro selo dela.
    ESTE MÓDULO NÃO MEXE NO SELO, nem no FERJ e no FERC.

PostgreSQL nativo, pelo `bd_nativo`. Dinheiro em centavos. Data e hora se
calculam no Python (regra da casa).
"""
from __future__ import annotations

from datetime import date
from typing import Any

from bd_nativo import banco
from caixa_schema import centavos, hash_lancamento, reais
from ri_schema import ler_feriados_locais, soma_dias_uteis

TABELA = "rc_materializacao_repasses"
NATUREZA = "VALOR_DE_TERCEIRO"
ORIGEM = "TERCEIRO_MATERIALIZACAO"
CODIGO_DA_MATERIALIZACAO = "14.5.1"
#: A categoria do módulo de despesas por onde o repasse sai da conta.
CATEGORIA_DA_DESPESA = "REPASSE_SERVENTIA_CRC"

RECEBIDO, REPASSADO, CONCILIADO = "RECEBIDO", "REPASSADO", "CONCILIADO"
DEVOLVIDO, CANCELADO = "DEVOLVIDO", "CANCELADO"
SITUACOES = {
    RECEBIDO: "Recebido — falta repassar ao cartório de origem",
    REPASSADO: "Repassado — falta conciliar",
    CONCILIADO: "Repassado e conciliado",
    DEVOLVIDO: "Devolvido ao cliente",
    CANCELADO: "Cancelado — o lançamento do caixa foi desfeito",
}
#: As situações em que o pedido ainda ocupa a vaga (índice único).
VIVAS = (RECEBIDO, REPASSADO, CONCILIADO)

#: Por onde o repasse sai — só caminhos que já passam pela autorização do
#: titular. `despesa` diz se a forma exige a despesa paga do módulo.
FORMAS_DE_REPASSE: dict[str, dict[str, Any]] = {
    "DESPESA": {"rotulo": "pela conta da serventia, numa despesa do módulo de "
                          "despesas (categoria «Repasse a outra serventia — CRC»)",
                "despesa": True},
    "CREDITOS_CRC": {"rotulo": "débito nos créditos que a serventia tem na CRC",
                     "despesa": False},
}
SITUACOES_DA_DESPESA_PAGA = ("PAGA", "CONCILIADA", "PAGA_FORA")

CHAVE_DO_PRAZO = "rc_repasse_prazo_dias_uteis"
PRAZO_PADRAO = 1
CHAVE_DA_TAXA_CRC = "rc_repasse_cobra_taxa_crc"

TRAVA = "rc_materializacao_repasses.pedido"

SCHEMA = (
    ("rc_materializacao_repasses", """
        CREATE TABLE IF NOT EXISTS rc_materializacao_repasses (
            id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            protocolo_id bigint NOT NULL REFERENCES cx_protocolos(id),
            pedido_crc TEXT NOT NULL,              -- o nº do pedido na CRC
            materializacao_id bigint REFERENCES rc_materializacoes(id),
            cartorio_nome TEXT NOT NULL,           -- quem recebe o repasse
            cartorio_cidade TEXT NOT NULL,
            cartorio_uf TEXT NOT NULL,
            emolumentos_origem_centavos bigint NOT NULL DEFAULT 0,
            fundos_origem_centavos bigint NOT NULL DEFAULT 0,
            taxa_crc_centavos bigint NOT NULL DEFAULT 0,
            valor_centavos bigint NOT NULL CHECK (valor_centavos > 0),
            lancamento_id bigint REFERENCES cx_lancamentos(id),
            recebido_em TEXT NOT NULL,
            prazo TEXT NOT NULL,
            situacao TEXT NOT NULL DEFAULT 'RECEBIDO',
            forma TEXT,
            comprovante TEXT,
            favorecido TEXT,
            despesa_id bigint,
            repassado_em TEXT,
            repassado_por TEXT,
            valor_confirmado_centavos bigint,
            referencia_conciliacao TEXT,
            conciliado_em TEXT,
            conciliado_por TEXT,
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
         WHERE situacao IN ('RECEBIDO', 'REPASSADO', 'CONCILIADO')"""),
    ("ux_rc_mat_repasse_lancamento", """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_rc_mat_repasse_lancamento
            ON rc_materializacao_repasses (lancamento_id)
         WHERE lancamento_id IS NOT NULL"""),
    ("ix_rc_mat_repasse_protocolo", """
        CREATE INDEX IF NOT EXISTS ix_rc_mat_repasse_protocolo
            ON rc_materializacao_repasses (protocolo_id)"""),
    # O pedido também fica na materialização, para o selo se ligar ao valor
    # recebido. Coluna opcional: a materialização de antes não tem pedido.
    ("rc_materializacoes.pedido_crc", """
        ALTER TABLE rc_materializacoes ADD COLUMN IF NOT EXISTS pedido_crc TEXT"""),
)


class RepasseTerceiroError(ValueError):
    """Impedimento de regra, com a frase pronta para o balcão."""


def init_rc_materializacao_repasse_schema(con) -> None:
    """Cria a tabela. Idempotente. Vem depois do caixa (chaves estrangeiras)."""
    bd = banco(con)
    for _nome, sql in SCHEMA:
        bd.escrever(sql)


# ------------------------------------------------------------ a configuração


def _setting(bd, chave: str) -> str:
    if not bd.tem_tabela("settings"):
        return ""
    linha = bd.um("SELECT value FROM settings WHERE key=%s", (chave,))
    return str((linha or {}).get("value") or "").strip()


def prazo_em_dias_uteis(con) -> int:
    """O prazo da casa para repassar, em dias úteis. Só LÊ.

    Não é prazo legal (nenhum foi medido para esta situação): é a régua do
    aviso. Vazio ou ilegível vale o padrão, que é curto — avisar cedo é o lado
    seguro de uma régua que ninguém decidiu."""
    bruto = _setting(banco(con), CHAVE_DO_PRAZO)
    try:
        dias = int(bruto)
    except ValueError:
        return PRAZO_PADRAO
    return dias if 0 <= dias <= 60 else PRAZO_PADRAO


def cobra_taxa_da_crc(con) -> bool:
    """A taxa da CRC entra no valor que o cliente paga? Só LÊ. Padrão: não."""
    return _setting(banco(con), CHAVE_DA_TAXA_CRC) == "1"


def feriados_da_casa(con) -> set[date]:
    """Os feriados locais da casa — a mesma lista do RI e do Protesto."""
    return ler_feriados_locais(_setting(banco(con), "ri_feriados_locais"))


def prazo_do_repasse(recebido_em: Any, dias: int,
                     feriados: set[date] | None = None) -> str:
    dia = date.fromisoformat(str(recebido_em)[:10])
    return soma_dias_uteis(dia, int(dias), feriados or set()).isoformat()


def _br(dia: Any) -> str:
    try:
        return date.fromisoformat(str(dia or "")[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return str(dia or "—")


def _limpo(valor: Any) -> str:
    return " ".join(str(valor or "").split())


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
            "cliente entrega agora, e sai inteiro para o outro cartório. O "
            "depósito prévio vira receita no uso, e «PG feito pela CRC» é "
            "receita que a Central paga a esta casa.")
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
    return (f"Valor de terceiro — repasse ao {d['cartorio_nome']} "
            f"({d['cartorio_cidade']}/{d['cartorio_uf']}), pedido CRC nº "
            f"{d['pedido_crc']}. Não é emolumento desta serventia.")


def receber(con, protocolo_id: int, dados: dict, *, caixa_id: int, hoje: str,
            hora: str, agora: str, usuario: Any = None, usuario_id: Any = None,
            feriados: set[date] | None = None) -> dict:
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
    dias = prazo_em_dias_uteis(bd)
    prazo = prazo_do_repasse(hoje, dias, feriados if feriados is not None
                             else feriados_da_casa(bd))
    repasse_id = int(bd.escrever(
        f"""INSERT INTO {TABELA}(protocolo_id, pedido_crc, cartorio_nome,
               cartorio_cidade, cartorio_uf, emolumentos_origem_centavos,
               fundos_origem_centavos, taxa_crc_centavos, valor_centavos,
               recebido_em, prazo, situacao, favorecido, criado_em, criado_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'RECEBIDO',%s,%s,%s)
           RETURNING id""",
        (int(protocolo_id), d["pedido_crc"], d["cartorio_nome"],
         d["cartorio_cidade"], d["cartorio_uf"], d["emolumentos_origem_centavos"],
         d["fundos_origem_centavos"], d["taxa_crc_centavos"], d["valor_centavos"],
         str(hoje)[:10], prazo, d["cartorio_nome"], agora,
         str(usuario or "") or None))[0]["id"])
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
            "prazo": prazo, "protocolo": p["numero"], "pedido_crc": d["pedido_crc"]}


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


def _enfeitar(linha: dict, hoje_d: date | None = None) -> dict:
    d = dict(linha)
    d["lancamento_vivo"] = bool(d.get("lancamento_id")) and not (
        int(d.get("lancamento_estornado") or 0) or int(d.get("lancamento_excluido") or 0))
    d["situacao_rotulo"] = SITUACOES.get(d["situacao"], d["situacao"])
    d["valor"] = reais(int(d["valor_centavos"]))
    if hoje_d is not None:
        atraso = (hoje_d - date.fromisoformat(str(d["prazo"])[:10])).days
        d["dias_de_atraso"] = max(0, atraso)
        d["vencido"] = atraso > 0
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


def pendentes(con, *, hoje: str) -> dict:
    """O que foi recebido e ainda não saiu, e o que precisa de alguém. Só LÊ.

    `a_repassar`: recebido, com o lançamento vivo e sem repasse — com prazo e
    atraso contados (contagem, e não juízo). `a_conciliar`: repassado e ainda
    não conferido com o que o outro lado confirmou. `desfeitos`: o lançamento
    do caixa foi estornado ou excluído, e o registro continua aberto — alguém
    tem de encerrá-lo (ou conferir, se o dinheiro já tinha saído)."""
    hoje_d = date.fromisoformat(str(hoje)[:10])
    linhas = [_enfeitar(x, hoje_d) for x in banco(con).ler(
        _SELECT + " WHERE r.situacao = ANY(%s) ORDER BY r.prazo, r.id",
        ([RECEBIDO, REPASSADO, CONCILIADO],))]
    a_repassar = [x for x in linhas if x["situacao"] == RECEBIDO and x["lancamento_vivo"]]
    a_conciliar = [x for x in linhas if x["situacao"] == REPASSADO and x["lancamento_vivo"]]
    desfeitos = [x for x in linhas if not x["lancamento_vivo"]]
    for x in a_repassar:
        x["explicacao"] = (
            f"Recebido em {_br(x['recebido_em'])}; repasse até {_br(x['prazo'])}"
            + (f" — {x['dias_de_atraso']} dia(s) de atraso" if x["vencido"] else "")
            + f". R$ {x['valor']} do {x['cartorio_nome']} ({x['cartorio_cidade']}/"
              f"{x['cartorio_uf']}), pedido CRC nº {x['pedido_crc']}, protocolo "
              f"{x['protocolo_numero']}.")
    return {"a_repassar": a_repassar, "a_conciliar": a_conciliar,
            "desfeitos": desfeitos,
            "total_a_repassar_centavos": sum(int(x["valor_centavos"]) for x in a_repassar),
            "total_a_repassar": reais(sum(int(x["valor_centavos"]) for x in a_repassar)),
            "vencidos": sum(int(x["vencido"]) for x in a_repassar)}


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


def recusa_ao_desfazer(con, lancamento_id: int) -> str | None:
    """Pode estornar ou excluir este lançamento? A frase da recusa, ou None.

    O valor que já saiu da casa (repassado ou conciliado) não se desfaz pelo
    caixa: o dinheiro do cliente já está no outro cartório, e estornar a
    entrada faria o caixa dizer que ele nunca entrou."""
    if not banco(con).tem_tabela(TABELA):
        return None
    r = do_lancamento(con, lancamento_id)
    if r and r["situacao"] in (REPASSADO, CONCILIADO):
        return (f"Este lançamento é o valor de terceiro do pedido CRC nº "
                f"{r['pedido_crc']}, e ele já foi repassado ao {r['cartorio_nome']}. "
                f"O dinheiro já saiu da casa: estornar a entrada desfaria a prova "
                f"de que ele entrou. Fale com o oficial.")
    return None


# ------------------------------------------------------------- o repasse


def _prender(bd, repasse_id: int) -> dict:
    bd.travar(TRAVA)
    linha = bd.um(_SELECT + " WHERE r.id=%s", (int(repasse_id),))
    if not linha:
        raise RepasseTerceiroError(f"Registro {repasse_id} não encontrado.")
    return _enfeitar(linha)


def registrar_repasse(con, repasse_id: int, *, forma: str, comprovante: str,
                      repassado_em: str, hoje: str, agora: str,
                      despesa_id: Any = None, favorecido: Any = None,
                      usuario: Any = None) -> dict:
    """Registra que o valor saiu para o outro cartório. ESCREVE.

    O comprovante é obrigatório: repasse sem prova é repasse que o outro lado
    pode dizer que não recebeu. Pela despesa, ela tem de ser da categoria
    própria e estar paga — e a soma do que se liga a ela não passa do valor
    dela (uma despesa pode pagar vários pedidos, se a CRC cobrar em lote)."""
    bd = banco(con)
    r = _prender(bd, repasse_id)
    if r["situacao"] != RECEBIDO:
        raise RepasseTerceiroError(
            f"O pedido CRC nº {r['pedido_crc']} não está esperando repasse "
            f"({r['situacao_rotulo'].lower()}).")
    if not r["lancamento_vivo"]:
        raise RepasseTerceiroError(
            "O lançamento deste valor foi estornado ou excluído no caixa: não há "
            "o que repassar. Encerre o registro.")
    chave = str(forma or "").strip().upper()
    if chave not in FORMAS_DE_REPASSE:
        raise RepasseTerceiroError(
            "Escolha por onde o repasse saiu: "
            + "; ".join(f["rotulo"] for f in FORMAS_DE_REPASSE.values()) + ".")
    prova = _limpo(comprovante)
    if len(prova) < 3:
        raise RepasseTerceiroError(
            "Informe o comprovante do repasse (autenticação do pagamento, número "
            "da transação ou do débito na CRC).")
    try:
        dia = date.fromisoformat(str(repassado_em or "")[:10]).isoformat()
    except ValueError:
        raise RepasseTerceiroError("Informe o dia do repasse.") from None
    if dia < str(r["recebido_em"])[:10]:
        raise RepasseTerceiroError("O repasse não pode ser anterior ao recebimento.")
    if dia > str(hoje)[:10]:
        raise RepasseTerceiroError("O dia do repasse está no futuro: registre quando ele sair.")
    despesa = None
    if FORMAS_DE_REPASSE[chave]["despesa"]:
        numero = str(despesa_id or "").strip()
        if not numero.isdigit():
            raise RepasseTerceiroError(
                "Informe o número da despesa (módulo de despesas) que pagou o repasse.")
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
                f"A despesa {numero} ainda não foi paga: o repasse só se registra "
                f"quando o dinheiro sai.")
        ja_ligado = int(bd.valor(
            f"""SELECT coalesce(sum(valor_centavos), 0) AS n FROM {TABELA}
                 WHERE despesa_id=%s AND situacao IN ('REPASSADO', 'CONCILIADO')""",
            (int(numero),)) or 0)
        if ja_ligado + int(r["valor_centavos"]) > int(despesa["valor"]):
            raise RepasseTerceiroError(
                f"A despesa {numero} é de R$ {reais(int(despesa['valor']))} e já paga "
                f"R$ {reais(ja_ligado)} de outros pedidos: este (R$ {r['valor']}) "
                f"não cabe nela.")
    quem = _limpo(favorecido) or r["cartorio_nome"]
    bd.escrever(
        f"""UPDATE {TABELA} SET situacao='REPASSADO', forma=%s, comprovante=%s,
               favorecido=%s, despesa_id=%s, repassado_em=%s, repassado_por=%s
             WHERE id=%s""",
        (chave, prova, quem, int(despesa["id"]) if despesa else None, dia,
         str(usuario or "") or None, int(repasse_id)))
    return {"repasse_id": int(repasse_id), "pedido_crc": r["pedido_crc"],
            "valor_centavos": int(r["valor_centavos"]), "forma": chave,
            "no_prazo": dia <= str(r["prazo"])[:10],
            "despesa_id": int(despesa["id"]) if despesa else None}


def conciliar(con, repasse_id: int, *, valor_confirmado: Any, referencia: str,
              agora: str, usuario: Any = None) -> dict:
    """Confere o repasse com o que o outro lado confirmou. ESCREVE.

    Valor que não fecha não concilia — a mesma regra da guia do protesto."""
    bd = banco(con)
    r = _prender(bd, repasse_id)
    if r["situacao"] != REPASSADO:
        raise RepasseTerceiroError(
            f"Só se concilia o que já foi repassado ({r['situacao_rotulo'].lower()}).")
    try:
        confirmado = centavos(valor_confirmado)
    except (TypeError, ValueError):
        confirmado = -1
    if confirmado < 0 or not str(valor_confirmado or "").strip():
        raise RepasseTerceiroError("Informe o valor que o outro lado confirmou.")
    if confirmado != int(r["valor_centavos"]):
        diferenca = confirmado - int(r["valor_centavos"])
        raise RepasseTerceiroError(
            f"O valor confirmado (R$ {reais(confirmado)}) não fecha com o repassado "
            f"(R$ {r['valor']}): diferença de R$ {reais(abs(diferenca))} "
            f"{'a mais' if diferenca > 0 else 'a menos'}. Valor que não fecha não "
            f"concilia — confira antes.")
    ref = _limpo(referencia)
    if len(ref) < 3:
        raise RepasseTerceiroError(
            "Informe onde a confirmação está (o pedido na CRC, o recibo do outro "
            "cartório, o extrato).")
    bd.escrever(
        f"""UPDATE {TABELA} SET situacao='CONCILIADO', valor_confirmado_centavos=%s,
               referencia_conciliacao=%s, conciliado_em=%s, conciliado_por=%s
             WHERE id=%s""",
        (confirmado, ref, agora, str(usuario or "") or None, int(repasse_id)))
    return {"repasse_id": int(repasse_id), "pedido_crc": r["pedido_crc"]}


def encerrar_sem_repasse(con, repasse_id: int, *, motivo: str, agora: str,
                         devolucao: Any = None, usuario: Any = None) -> dict:
    """Encerra o valor que não vai ser repassado. ESCREVE.

    Dois casos, e o sistema não escolhe entre eles — o caixa já disse:
      - o lançamento foi estornado ou excluído: CANCELADO (o dinheiro não
        ficou na casa);
      - o lançamento está vivo: só com a DEVOLUÇÃO ao cliente lançada no caixa
        (natureza «Devolução ao cliente», no mesmo protocolo e do mesmo
        valor): DEVOLVIDO. Deixar como crédito do cliente é pergunta aberta
        ao titular, e não existe aqui."""
    bd = banco(con)
    r = _prender(bd, repasse_id)
    if r["situacao"] != RECEBIDO:
        raise RepasseTerceiroError(
            f"Só se encerra o que ainda não foi repassado ({r['situacao_rotulo'].lower()}).")
    razao = _limpo(motivo)
    if len(razao) < 10:
        raise RepasseTerceiroError(
            "Escreva por que este valor não vai ser repassado (o pedido foi negado, "
            "cancelado, o lançamento estava errado…).")
    if not r["lancamento_vivo"]:
        bd.escrever(
            f"""UPDATE {TABELA} SET situacao='CANCELADO', motivo_encerramento=%s,
                   encerrado_em=%s, encerrado_por=%s WHERE id=%s""",
            (razao, agora, str(usuario or "") or None, int(repasse_id)))
        return {"repasse_id": int(repasse_id), "situacao": CANCELADO}
    numero = str(devolucao or "").strip()
    if not numero:
        raise RepasseTerceiroError(
            "O dinheiro deste valor continua no caixa. Lance antes a devolução ao "
            "cliente no caixa (natureza «Devolução ao cliente», neste protocolo) e "
            "informe aqui o número do lançamento (nº/ano).")
    if "/" in numero:
        n, _, a = numero.partition("/")
        dev = (bd.um("SELECT * FROM cx_lancamentos WHERE numero=%s AND ano=%s",
                     (int(n), int(a))) if n.strip().isdigit() and a.strip().isdigit()
               else None)
    else:
        dev = None
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


def achados(con, *, hoje: str) -> list[dict]:
    """Os avisos para o oficial: o que passou do prazo e o que ficou torto. Só LÊ.

    Cada um com `chave`, `gravidade`, `titulo` e `detalhe` — a forma das regras
    da conferência do gestor (`gestor_conferencia`), que os mostra no painel."""
    bd = banco(con)
    if not bd.tem_tabela(TABELA):
        return []
    p = pendentes(con, hoje=hoje)
    saida = []
    for x in p["a_repassar"]:
        if not x["vencido"]:
            continue
        saida.append({
            "chave": f"REPASSE_TERCEIRO:{x['id']}", "gravidade": "ATENCAO",
            "titulo": (f"Valor do {x['cartorio_nome']} ({x['cartorio_uf']}) recebido e não "
                       f"repassado — pedido CRC nº {x['pedido_crc']}, R$ {x['valor']}"),
            "detalhe": x["explicacao"] + (
                " Registre o repasse em Registro Civil → Materializar certidão → "
                "Repasses aos cartórios de origem, com o comprovante."),
            "prazo": x["prazo"]})
    for x in p["desfeitos"]:
        saida.append({
            "chave": f"REPASSE_TERCEIRO_DESFEITO:{x['id']}", "gravidade": "ATENCAO",
            "titulo": (f"Valor de terceiro com o lançamento desfeito — pedido CRC nº "
                       f"{x['pedido_crc']}, R$ {x['valor']}"),
            "detalhe": (f"O lançamento do caixa foi estornado ou excluído e o registro está "
                        f"«{x['situacao_rotulo'].lower()}». "
                        + ("Encerre-o na tela dos repasses." if x["situacao"] == RECEBIDO
                           else "O dinheiro já tinha saído: confira com o oficial.")),
            "prazo": None})
    return saida


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
