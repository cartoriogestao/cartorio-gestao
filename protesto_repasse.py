"""O REPASSE AO APRESENTANTE — o dinheiro do título pago, até chegar a quem o mandou.

Lote LG05 (19/10/2026). Até aqui o sistema registrava o pagamento no Livro de
Pagamentos e parava ali: o valor entrava na conta da serventia e **nenhuma tela
dizia que ele ainda era de outra pessoa**. É o dinheiro que a lei manda pôr à
disposição do apresentante no primeiro dia útil seguinte (Lei 9.492/1997, art.
19, § 2º; CN-MA art. 929), e que o roteiro do oficial já cobrava como passo do
dia: «geração de boleto de repasse dos títulos pagos» (`protesto_roteiro`).

DOIS CAMINHOS, E O QUE DECIDE É POR ONDE O TÍTULO CHEGOU
    IEPTB   título da CRA ou da CENPROT. O valor volta pela Central, numa GUIA
            DE PAGAMENTO AO IEPTB que junta os pagamentos — o «boleto de
            repasse CENPROT» do CN-MA art. 926. A casa gera a relação da guia,
            registra a guia que o Instituto emitiu, registra o pagamento e
            concilia com o que o Instituto confirmou.
    DIRETO  título do balcão (origem MANUAL). O valor vai direto ao
            apresentante, em espécie, cheque ou depósito na conta que ele
            indicou (art. 926) — e acima de R$ 300,00 só por cheque ou depósito
            (art. 926, § 1º). O comprovante é obrigatório.

A PENDÊNCIA NASCE DO LIVRO, E NÃO DE UMA LISTA À PARTE
    Pagamento lançado e sem repasse vivo É a pendência — a consulta parte de
    `pt_atos`, e o ato cancelado (selo que não saiu) sai da lista sozinho. Uma
    fila gravada à parte seria a segunda versão do Livro de Pagamentos, e as
    duas divergiriam no primeiro cancelamento.

O VALOR É O PAGO, OU O DECLARADO
    `valor_pago` do ato, quando o balcão o informou; senão o saldo declarado
    pelo apresentante — que é o valor em que o pagamento se faz (art. 19,
    caput). A linha diz qual dos dois (`valor_de`), e a tela também.

O ACERVO NÃO ENTRA
    Pagamento trazido do E-Ofício (`origem='EOFICIO'`) ou anterior à
    implantação (10/09/2026) já foi repassado fora daqui. Pô-lo na lista faria
    centenas de pendências que ninguém deve.

O QUE NÃO FAZ
    Não fala com o IEPTB nem com banco nenhum: a guia é emitida pelo Instituto
    e paga pela casa, e aqui se REGISTRA cada passo. Não recebe juros (CN-MA
    art. 925, § 9º) nem decide o pagamento parcial — isso é do oficial.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any

from bd_nativo import banco
from caixa_schema import centavos, reais
from gestor_conferencia import IMPLANTACAO
from ri_schema import ler_feriados_locais, soma_dias_uteis

CANAIS = ("IEPTB", "DIRETO")
ORIGENS_PELA_CENTRAL = ("CRA", "CENPROT")

# CN-MA art. 926: espécie, boleto de repasse CENPROT ou depósito em conta
# indicada. O boleto é da Central, e por isso mora na guia; aqui, as formas do
# repasse que a casa faz com a própria mão.
FORMAS_DE_REPASSE_DIRETO: dict[str, str] = {
    "ESPECIE": "em espécie",
    "CHEQUE": "por cheque",
    "DEPOSITO": "por depósito na conta indicada pelo apresentante",
}

# Art. 926, § 1º: acima de R$ 300,00, só por cheque ou depósito bancário.
TETO_EM_ESPECIE_CENTAVOS = 30000
FORMAS_ACIMA_DO_TETO = ("CHEQUE", "DEPOSITO")

SITUACOES_DA_GUIA = ("GERADA", "REGISTRADA", "PAGA", "CONCILIADA", "CANCELADA")

FUNDAMENTO_DO_PRAZO = ("Lei 9.492/1997, art. 19, § 2º; CN-MA art. 929 — o valor "
                       "fica à disposição do apresentante no primeiro dia útil "
                       "seguinte ao recebimento")

# As travas por assunto. A da guia numera; a do repasse impede que a guia e o
# repasse direto peguem o mesmo pagamento ao mesmo tempo.
TRAVA_DA_GUIA = "pt_repasse_guias.numero"
TRAVA_DO_REPASSE = "pt_repasses.ato"


class RepasseError(ValueError):
    """Impedimento de regra, com mensagem pronta para o balcão."""


def canal_da_origem(origem: Any) -> str:
    """IEPTB para o que veio pela Central; DIRETO para o balcão."""
    return ("IEPTB" if str(origem or "").strip().upper() in ORIGENS_PELA_CENTRAL
            else "DIRETO")


def feriados_da_casa(con) -> set[date]:
    """Os feriados locais que o RI e o Gestor já usam — a casa tem uma lista só."""
    bd = banco(con)
    if not bd.tem_tabela("settings"):
        return set()
    linha = bd.um("SELECT value FROM settings WHERE key=%s",
                  ("ri_feriados_locais",))
    return ler_feriados_locais((linha or {}).get("value") or "")


def prazo_do_repasse(recebido_em: Any, feriados: set[date] | None = None) -> str:
    """O primeiro dia útil seguinte ao recebimento, em AAAA-MM-DD."""
    dia = date.fromisoformat(str(recebido_em)[:10])
    return soma_dias_uteis(dia, 1, feriados or set()).isoformat()


def _br(dia: Any) -> str:
    try:
        return date.fromisoformat(str(dia or "")[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return str(dia or "—")


def _valor_do_pagamento(linha: dict) -> tuple[int, str]:
    try:
        detalhe = json.loads(linha.get("detalhe_json") or "{}")
    except (TypeError, ValueError):
        detalhe = {}
    pago = detalhe.get("valor_pago_centavos")
    if pago is not None:
        return int(pago), "PAGO"
    saldo = int(linha.get("saldo_centavos") or 0) or int(linha.get("valor_centavos") or 0)
    return saldo, "SALDO"


def _forma_do_pagamento(linha: dict) -> str:
    try:
        return str(json.loads(linha.get("detalhe_json") or "{}")
                   .get("forma_pagamento") or "")
    except (TypeError, ValueError):
        return ""


# ------------------------------------------------------------ a pendência


def pendentes(con, *, hoje: str, feriados: set[date] | None = None,
              canal: str | None = None, ato_ids: list[int] | None = None
              ) -> list[dict]:
    """Os pagamentos ainda sem repasse, com prazo e atraso. Só LÊ.

    `dias_de_atraso` é contagem, e não juízo — a mesma régua do tríduo: quem
    decide o que fazer com o atraso é quem assina. O pagamento em cheque leva
    a observação de que o prazo corre da compensação (CN-MA art. 927, § ún.).
    """
    bd = banco(con)
    filtro = ""
    parametros: list[Any] = [IMPLANTACAO]
    if ato_ids:
        filtro = " AND a.id = ANY(%s)"
        parametros.append([int(x) for x in ato_ids])
    linhas = bd.ler(
        f"""SELECT a.id AS ato_id, a.data_ato, a.detalhe_json, a.rotulo,
                   a.numero_ordem,
                   t.id AS titulo_id, t.numero_titulo, t.protocolo, t.especie,
                   t.origem, t.apresentante_codigo, t.apresentante_nome,
                   t.cedente_nome, t.saldo_centavos, t.valor_centavos
              FROM pt_atos a
              JOIN pt_titulos t ON t.id = a.titulo_id
             WHERE a.tipo = 'PAGAMENTO' AND a.cancelado = 0
               AND a.origem <> 'EOFICIO' AND a.data_ato >= %s
               AND NOT EXISTS (SELECT 1 FROM pt_repasses r
                                WHERE r.ato_id = a.id
                                  AND r.situacao <> 'CANCELADO'){filtro}
             ORDER BY a.data_ato, a.id""", parametros)
    hoje_d = date.fromisoformat(str(hoje)[:10])
    saida = []
    for linha in linhas:
        d = dict(linha)
        d["canal"] = canal_da_origem(d["origem"])
        if canal and d["canal"] != canal:
            continue
        d["valor_centavos"], d["valor_de"] = _valor_do_pagamento(d)
        d["recebido_em"] = str(d["data_ato"])[:10]
        d["prazo"] = prazo_do_repasse(d["recebido_em"], feriados)
        atraso = (hoje_d - date.fromisoformat(d["prazo"])).days
        d["dias_de_atraso"] = max(0, atraso)
        d["vencido"] = atraso > 0
        d["forma_do_pagamento"] = _forma_do_pagamento(d)
        d["observacao"] = ("pago em cheque: o prazo corre da compensação "
                           "(CN-MA art. 927, parágrafo único)"
                           if d["forma_do_pagamento"] == "CHEQUE" else "")
        d["favorecido"] = d["apresentante_nome"] or d["cedente_nome"] or ""
        saida.append(d)
    return saida


def relatorio(con, *, hoje: str, feriados: set[date] | None = None) -> dict:
    """O relatório de pendências de repasse: o que falta, por canal, e as guias.

    Só LÊ. É a tela inteira numa chamada, para o relatório em CSV e a tela
    dizerem o mesmo.
    """
    lista = pendentes(con, hoje=hoje, feriados=feriados)
    por_canal = {c: {"titulos": 0, "total_centavos": 0, "vencidos": 0}
                 for c in CANAIS}
    for p in lista:
        g = por_canal[p["canal"]]
        g["titulos"] += 1
        g["total_centavos"] += p["valor_centavos"]
        g["vencidos"] += int(p["vencido"])
    bd = banco(con)
    abertas = bd.ler(
        """SELECT * FROM pt_repasse_guias
            WHERE situacao IN ('GERADA','REGISTRADA','PAGA')
            ORDER BY id""")
    return {"pendentes": lista, "por_canal": por_canal,
            "total_centavos": sum(p["valor_centavos"] for p in lista),
            "vencidos": sum(int(p["vencido"]) for p in lista),
            "guias_abertas": abertas,
            "a_conciliar": [g for g in abertas if g["situacao"] == "PAGA"]}


# ---------------------------------------------------------------- a guia


def _relacao_da_guia(numero: int, ano: int, itens: list[dict]) -> str:
    """O teor da relação que a guia paga — uma linha por título, por apresentante."""
    linhas = [f"GUIA DE REPASSE AO IEPTB Nº {numero}/{ano}",
              "PROTOCOLO;TITULO;ESPECIE;APRESENTANTE;PAGO_EM;VALOR"]
    for i in sorted(itens, key=lambda x: (str(x["apresentante_codigo"] or ""),
                                          x["recebido_em"], x["ato_id"])):
        linhas.append(";".join([
            str(i["protocolo"] or ""), str(i["numero_titulo"] or ""),
            str(i["especie"] or ""),
            f"{i['apresentante_codigo'] or ''} {i['apresentante_nome'] or ''}".strip(),
            _br(i["recebido_em"]), reais(i["valor_centavos"])]))
    total = sum(i["valor_centavos"] for i in itens)
    linhas.append(f"TOTAL;{len(itens)} título(s);;;;{reais(total)}")
    return "\n".join(linhas) + "\n"


def gerar_guia(con, *, hoje: str, agora: str, usuario: str | None = None,
               ato_ids: list[int] | None = None,
               feriados: set[date] | None = None) -> dict:
    """Gera a guia de repasse ao IEPTB com os pagamentos da Central. ESCREVE.

    A TRAVA VEM ANTES DA LISTA: ler os pendentes e só depois travar deixaria
    duas guias geradas ao mesmo tempo pegarem o mesmo pagamento. Sem `ato_ids`,
    entram todos os pendentes do canal IEPTB.

    Recusa pagamento de título do balcão (esse se repassa direto) e pagamento
    que já está noutra guia — dizendo qual.
    """
    bd = banco(con)
    bd.travar(TRAVA_DO_REPASSE)
    bd.travar(TRAVA_DA_GUIA)
    lista = pendentes(bd, hoje=hoje, feriados=feriados, ato_ids=ato_ids)
    if ato_ids:
        achados = {p["ato_id"] for p in lista}
        faltam = [int(x) for x in ato_ids if int(x) not in achados]
        if faltam:
            raise RepasseError(
                f"O(s) pagamento(s) {', '.join(map(str, faltam))} não está(ão) "
                f"pendente(s) de repasse — já estão numa guia, já foram "
                f"repassados ou não são pagamento lançado no sistema.")
        diretos = [p for p in lista if p["canal"] != "IEPTB"]
        if diretos:
            raise RepasseError(
                "Título do balcão não vai na guia do IEPTB — o repasse dele é "
                "direto ao apresentante: "
                + ", ".join(str(p["numero_titulo"]) for p in diretos) + ".")
    lista = [p for p in lista if p["canal"] == "IEPTB"]
    if not lista:
        raise RepasseError("Não há pagamento de título da Central esperando repasse.")

    ano = int(str(hoje)[:4])
    numero = int(bd.valor(
        "SELECT coalesce(max(numero), 0) + 1 AS n FROM pt_repasse_guias WHERE ano=%s",
        (ano,)))
    relacao = _relacao_da_guia(numero, ano, lista)
    total = sum(p["valor_centavos"] for p in lista)
    guia_id = int(bd.escrever(
        """INSERT INTO pt_repasse_guias(numero, ano, dia, titulos, total_centavos,
               relacao, hash_relacao, situacao, gerada_em, gerada_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s,'GERADA',%s,%s) RETURNING id""",
        (numero, ano, str(hoje)[:10], len(lista), total, relacao,
         hashlib.sha256(relacao.encode("utf-8")).hexdigest(), agora,
         usuario))[0]["id"])
    for p in lista:
        novo = bd.escrever(
            """INSERT INTO pt_repasses(ato_id, titulo_id, canal, valor_centavos,
                   valor_de, recebido_em, prazo, guia_id, situacao, favorecido,
                   criado_em, criado_por)
               VALUES (%s,%s,'IEPTB',%s,%s,%s,%s,%s,'EM_GUIA',%s,%s,%s)
               ON CONFLICT (ato_id) WHERE situacao <> 'CANCELADO' DO NOTHING
               RETURNING id""",
            (p["ato_id"], p["titulo_id"], p["valor_centavos"], p["valor_de"],
             p["recebido_em"], p["prazo"], guia_id, p["favorecido"], agora,
             usuario))
        if not novo:
            raise RepasseError(
                f"O pagamento do título {p['numero_titulo']} entrou noutro "
                f"repasse enquanto esta guia se montava. Gere de novo.")
    return {"guia_id": guia_id, "numero": numero, "ano": ano,
            "titulos": len(lista), "total_centavos": total}


def guia_para_gravar(con, guia_id: int) -> dict | None:
    """A guia, com a linha presa até o fim da transação (FOR UPDATE)."""
    bd = banco(con)
    bd._escrita()
    return bd.um("SELECT * FROM pt_repasse_guias WHERE id=%s FOR UPDATE",
                 (int(guia_id),))


def _exigir(guia: dict | None, guia_id: int, *situacoes: str) -> dict:
    if not guia:
        raise RepasseError(f"Guia {guia_id} não encontrada.")
    if guia["situacao"] not in situacoes:
        raise RepasseError(
            f"A guia {guia['numero']}/{guia['ano']} está {guia['situacao']} — "
            f"este passo cabe só em guia {' ou '.join(situacoes)}.")
    return guia


def registrar_guia(con, guia_id: int, *, identificador: str,
                   vencimento: str | None, agora: str,
                   usuario: str | None = None) -> dict:
    """Registra a guia que o IEPTB emitiu para esta relação. ESCREVE.

    O identificador (número da guia ou linha digitável) é obrigatório: é por
    ele que o pagamento se confere no extrato, e guia paga sem ele é dinheiro
    que saiu sem endereço.
    """
    bd = banco(con)
    guia = _exigir(guia_para_gravar(bd, guia_id), guia_id, "GERADA")
    ident = " ".join(str(identificador or "").split())
    if len(ident) < 5:
        raise RepasseError(
            "Informe o número da guia (ou a linha digitável) que o IEPTB emitiu.")
    bd.escrever(
        """UPDATE pt_repasse_guias
              SET situacao='REGISTRADA', identificador=%s, vencimento=%s,
                  registrada_em=%s, registrada_por=%s
            WHERE id=%s""",
        (ident, (str(vencimento)[:10] if vencimento else None), agora, usuario,
         int(guia_id)))
    return {"guia_id": int(guia_id), "numero": guia["numero"],
            "identificador": ident}


def pagar_guia(con, guia_id: int, *, paga_em: str, comprovante: str,
               agora: str, usuario: str | None = None) -> dict:
    """Registra o pagamento da guia — e com ele o repasse dos títulos. ESCREVE.

    O REPASSE SE CUMPRE AQUI, e não na conciliação: o dinheiro saiu da casa no
    dia em que a guia foi paga, e é contra esse dia que o prazo do art. 19,
    § 2º se mede. A conciliação é a confirmação do Instituto, e vem depois.
    """
    bd = banco(con)
    guia = _exigir(guia_para_gravar(bd, guia_id), guia_id, "REGISTRADA")
    try:
        dia = date.fromisoformat(str(paga_em or "")[:10]).isoformat()
    except ValueError:
        raise RepasseError("Informe o dia em que a guia foi paga.") from None
    if dia < str(guia["dia"])[:10]:
        raise RepasseError("A guia não pode ter sido paga antes de ser gerada.")
    prova = " ".join(str(comprovante or "").split())
    if len(prova) < 3:
        raise RepasseError(
            "Informe o comprovante do pagamento da guia (autenticação ou "
            "número da transação).")
    bd.escrever(
        """UPDATE pt_repasse_guias
              SET situacao='PAGA', paga_em=%s, comprovante=%s, paga_por=%s
            WHERE id=%s""", (dia, prova, usuario, int(guia_id)))
    bd.escrever(
        """UPDATE pt_repasses
              SET situacao='REPASSADO', repassado_em=%s, forma='GUIA_IEPTB',
                  comprovante=%s
            WHERE guia_id=%s AND situacao='EM_GUIA'""",
        (dia, prova, int(guia_id)))
    return {"guia_id": int(guia_id), "numero": guia["numero"], "paga_em": dia,
            "total_centavos": int(guia["total_centavos"])}


def conciliar_guia(con, guia_id: int, *, valor_confirmado: Any,
                   referencia: str, agora: str,
                   usuario: str | None = None) -> dict:
    """Confere o que o IEPTB confirmou contra o total da guia. ESCREVE.

    VALOR QUE NÃO FECHA NÃO CONCILIA, e a mensagem diz a diferença. Conciliar
    «quase» seria guardar como conferida uma guia em que faltou um título — e
    é exatamente o título que o apresentante vai cobrar.
    """
    bd = banco(con)
    guia = _exigir(guia_para_gravar(bd, guia_id), guia_id, "PAGA")
    valor = centavos(valor_confirmado)
    ref = " ".join(str(referencia or "").split())
    if len(ref) < 3:
        raise RepasseError(
            "Informe a referência da confirmação do IEPTB (o número do aviso, "
            "do extrato ou do e-mail).")
    total = int(guia["total_centavos"])
    if valor != total:
        raise RepasseError(
            f"O IEPTB confirmou R$ {reais(valor)} e a guia "
            f"{guia['numero']}/{guia['ano']} soma R$ {reais(total)} — diferença "
            f"de R$ {reais(valor - total)}. Confira a relação da guia antes de "
            f"conciliar.")
    bd.escrever(
        """UPDATE pt_repasse_guias
              SET situacao='CONCILIADA', valor_confirmado_centavos=%s,
                  referencia_conciliacao=%s, conciliada_em=%s, conciliada_por=%s
            WHERE id=%s""", (valor, ref, agora, usuario, int(guia_id)))
    return {"guia_id": int(guia_id), "numero": guia["numero"],
            "total_centavos": total}


def cancelar_guia(con, guia_id: int, *, motivo: str, agora: str,
                  usuario: str | None = None) -> dict:
    """Cancela a guia ainda não paga; os pagamentos voltam a ser pendência. ESCREVE.

    Guia paga não se cancela aqui: o dinheiro já saiu, e desfazer é estorno
    com o Instituto, que não é ato deste sistema.
    """
    bd = banco(con)
    bd.travar(TRAVA_DO_REPASSE)
    guia = _exigir(guia_para_gravar(bd, guia_id), guia_id, "GERADA", "REGISTRADA")
    razao = " ".join(str(motivo or "").split())
    if len(razao) < 5:
        raise RepasseError("Escreva por que a guia se cancela.")
    bd.escrever(
        """UPDATE pt_repasse_guias
              SET situacao='CANCELADA', motivo_cancelamento=%s, cancelada_em=%s,
                  cancelada_por=%s
            WHERE id=%s""", (razao, agora, usuario, int(guia_id)))
    bd.escrever("UPDATE pt_repasses SET situacao='CANCELADO' WHERE guia_id=%s",
                (int(guia_id),))
    return {"guia_id": int(guia_id), "numero": guia["numero"],
            "titulos": int(guia["titulos"])}


def guias(con, limite: int = 60) -> list[dict]:
    """As guias, da mais nova para a mais velha. Só LÊ."""
    return banco(con).ler(
        "SELECT * FROM pt_repasse_guias ORDER BY ano DESC, numero DESC, id DESC "
        "LIMIT %s", (int(limite),))


def guia(con, guia_id: int) -> dict | None:
    """A guia e os repasses dela. Só LÊ."""
    bd = banco(con)
    g = bd.um("SELECT * FROM pt_repasse_guias WHERE id=%s", (int(guia_id),))
    if not g:
        return None
    g["repasses"] = bd.ler(
        """SELECT r.*, t.numero_titulo, t.protocolo
             FROM pt_repasses r JOIN pt_titulos t ON t.id = r.titulo_id
            WHERE r.guia_id=%s ORDER BY r.id""", (int(guia_id),))
    return g


# ------------------------------------------------------------ o repasse direto


def registrar_direto(con, ato_id: int, *, forma: str, comprovante: str,
                     repassado_em: str, hoje: str, agora: str,
                     favorecido: str | None = None,
                     usuario: str | None = None,
                     feriados: set[date] | None = None) -> dict:
    """Registra o repasse direto ao apresentante do título do balcão. ESCREVE.

    A forma é do art. 926; acima de R$ 300,00 só cheque ou depósito (§ 1º). O
    comprovante é obrigatório — o recibo assinado, o número do cheque, o
    comprovante do depósito: repasse sem prova é repasse que o apresentante
    pode dizer que não recebeu.
    """
    bd = banco(con)
    bd.travar(TRAVA_DO_REPASSE)
    achado = pendentes(bd, hoje=hoje, feriados=feriados, ato_ids=[int(ato_id)])
    if not achado:
        raise RepasseError(
            f"O pagamento {ato_id} não está pendente de repasse — já foi "
            f"repassado, está numa guia, ou não é pagamento lançado no sistema.")
    p = achado[0]
    if p["canal"] != "DIRETO":
        raise RepasseError(
            f"O título {p['numero_titulo']} veio pela {p['origem']}: o repasse "
            f"dele vai pela guia do IEPTB, e não direto.")
    chave = str(forma or "").strip().upper()
    if chave not in FORMAS_DE_REPASSE_DIRETO:
        raise RepasseError(
            f"Forma de repasse desconhecida: {forma!r}. As que existem são: "
            f"{', '.join(FORMAS_DE_REPASSE_DIRETO.values())}.")
    if (p["valor_centavos"] > TETO_EM_ESPECIE_CENTAVOS
            and chave not in FORMAS_ACIMA_DO_TETO):
        raise RepasseError(
            f"O repasse é de R$ {reais(p['valor_centavos'])}: acima de "
            f"R$ 300,00 ele só se faz por cheque ou depósito bancário (CN-MA "
            f"art. 926, § 1º).")
    prova = " ".join(str(comprovante or "").split())
    if len(prova) < 3:
        raise RepasseError(
            "Informe o comprovante do repasse — o recibo assinado, o número do "
            "cheque ou o do depósito.")
    try:
        dia = date.fromisoformat(str(repassado_em or "")[:10]).isoformat()
    except ValueError:
        raise RepasseError("Informe o dia do repasse.") from None
    if dia < p["recebido_em"]:
        raise RepasseError("O repasse não pode ser anterior ao pagamento.")
    quem = " ".join(str(favorecido or "").split()) or p["favorecido"] or None
    repasse_id = int(bd.escrever(
        """INSERT INTO pt_repasses(ato_id, titulo_id, canal, valor_centavos,
               valor_de, recebido_em, prazo, situacao, forma, comprovante,
               favorecido, repassado_em, criado_em, criado_por)
           VALUES (%s,%s,'DIRETO',%s,%s,%s,%s,'REPASSADO',%s,%s,%s,%s,%s,%s)
           RETURNING id""",
        (p["ato_id"], p["titulo_id"], p["valor_centavos"], p["valor_de"],
         p["recebido_em"], p["prazo"], chave, prova, quem, dia, agora,
         usuario))[0]["id"])
    return {"repasse_id": repasse_id, "ato_id": p["ato_id"],
            "titulo_id": p["titulo_id"], "valor_centavos": p["valor_centavos"],
            "forma": chave, "no_prazo": dia <= p["prazo"]}
