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

A GUIA SAI DO PORTAL, E NÃO DE API — MEDIDO EM 29/10/2026
    Pedido do oficial: «emitir automático a guia de repasse do título pago no
    cartório pela CRA e CENPROT». Não há por onde:
      - a API da CENPROT para o cartório (contrato 2.1.0, baixado de novo no
        dia: 21 caminhos) não tem guia, boleto, repasse nem liquidação;
      - a API da Intimação Digital (Resolve 1.11.0) só fala do pagamento do
        DEVEDOR (o relatório de pagamentos e o link de pagamento), e não do
        repasse ao apresentante;
      - o WSDL da CRA-MA (21 operações, o de produção conferido no dia contra
        a cópia guardada) não tem operação de guia nem de repasse;
      - o E-Ofício tinha as rotinas no menu («Gera repasse ao apresentante»,
        «Repasse aos apresentantes») e NUNCA as usou nesta casa:
        `tbAvisoProtesto.dtmRepasse_Data` vazia em 1.414 de 1.414 (os 142
        pagos, todos vindos da Central, inclusive) e a conta de repasse do
        apresentante (`tbCobrador.strFavorecido`) vazia em 106 de 106. Não há
        precedente de canal, de leiaute nem de agrupamento a imitar.
    A CENPROT tem o módulo de liquidação dos títulos pagos NO PORTAL, e é por
    ele que um título da CENPROT desta casa foi liquidado em 27/10/2026. A
    CRA-MA tem o boleto de repasse no portal dela — lido em 29/10/2026, só
    lendo: menu Retorno → «Boletos de repasse», botão «GERAR BOLETO». Ele
    NASCE DO RETORNO com a ocorrência «pago», um por data de retorno e conta,
    e o identificador dele é o NOSSO NÚMERO.

    POR ISSO O QUE ESTE MÓDULO AUTOMATIZA É O QUE É DA CASA:
      - a relação da guia nasce sozinha, no dia do pagamento, pela rotina da
        central de automação (`protesto_repasse_automacao`), UMA POR CENTRAL
        (`gerar_guias_do_dia`): o título da CENPROT e o da CRA se acertam em
        portais diferentes, e uma relação misturada não se emite em nenhum
        dos dois — duas relações se emitem nos dois casos;
      - o pagamento NÃO SAI DA PENDÊNCIA ao entrar na relação: ele continua
        cobrado, com o prazo do art. 19, § 2º e o passo exato do portal
        (`PASSO_NO_PORTAL`), até a guia ser registrada e paga
        (`pendencias_do_repasse`, a lista que a tela e o roteiro leem).
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

# O PASSO DO PORTAL, POR CENTRAL. É o que a pendência e a tela dizem a quem vai
# emitir a guia. O que não se mediu está em `a_conferir`, e a tela mostra —
# o sistema não entra em portal nenhum, e escrever o menu de memória seria
# mandar o escrevente procurar um botão que talvez se chame de outro jeito.
PASSO_NO_PORTAL: dict[str, dict[str, str]] = {
    "CENPROT": {
        "central": "CENPROT",
        "onde": ("no portal da CENPROT, na área do cartório — a liquidação dos "
                 "títulos pagos"),
        "passo": ("Entre no portal da CENPROT com o acesso do cartório, abra a "
                  "liquidação dos títulos pagos, marque os títulos desta relação "
                  "(pela chave única ou pelo protocolo), emita a guia e pague-a. "
                  "Registre aqui o número da guia (ou a referência da "
                  "liquidação) e, depois de paga, o comprovante."),
        "precedente": ("um título da CENPROT desta casa foi liquidado por esse "
                       "caminho em 27/10/2026, e o portal devolveu o "
                       "«Comprovante TED liquidação»"),
        "a_conferir": ("o nome exato do menu, e se o portal emite boleto ou pede "
                       "TED — o sistema não entra no portal"),
    },
    # O CAMINHO DA CRA FOI LIDO NO PORTAL, só lendo, em 29/10/2026: menu
    # Retorno → «Boletos de repasse». O boleto NASCE DO RETORNO com a
    # ocorrência «pago», um por data de retorno e conta — e sai no portal da
    # CRA, e não na CENPROT.
    "CRA": {
        "central": "CRA",
        "onde": ("no portal da CRA-MA, menu Retorno → «Boletos de repasse»"),
        "passo": ("O boleto nasce do RETORNO com a ocorrência «pago», um por data "
                  "de retorno e conta: mande antes o retorno do pagamento. No "
                  "portal da CRA-MA, menu Retorno → «Boletos de repasse», filtre "
                  "o período e a conta; o movimento aparece em «Boletos "
                  "pendentes de geração» (Conta, Movimento, Repasse, Situação). "
                  "Clique «GERAR BOLETO»: ele passa à lista dos boletos (Conta, "
                  "Geração, Retorno, Nosso número, Repasse, Taxa, Valor, "
                  "Situação). Registre aqui o NOSSO NÚMERO como o número da guia "
                  "(mais de um boleto: separe por vírgula). Pague o boleto e "
                  "registre o pagamento com o comprovante do banco — ou com a "
                  "situação no portal, quando ela deixar de ser «AGUARDANDO "
                  "PAGAMENTO»."),
        "precedente": ("lido no portal em 29/10/2026: um boleto gerado do retorno "
                       "de 26/10/2026, nosso número de 12 dígitos, taxa 0,00 e "
                       "valor igual ao repasse, «AGUARDANDO PAGAMENTO» — pago "
                       "pelo oficial no mesmo dia, sem a situação mudar no "
                       "portal até a leitura"),
        "a_conferir": ("a palavra que substitui «AGUARDANDO PAGAMENTO» depois da "
                       "compensação, e em quanto tempo ela muda"),
    },
}

#: Como o pagamento da guia se prova (`pagar_guia`): o comprovante do banco,
#: ou a situação do boleto no portal da Central, lida por quem registra.
PROVAS_DO_PAGAMENTO: dict[str, str] = {
    "COMPROVANTE": "comprovante do pagamento (autenticação ou transação)",
    "PORTAL": "situação do boleto no portal da Central",
}
#: A situação do portal que NÃO prova pagamento — a do boleto ainda em aberto.
SITUACAO_EM_ABERTO_NO_PORTAL = "AGUARDANDO PAGAMENTO"

#: As etapas da pendência — onde o dinheiro está parado, e o que falta.
SEM_GUIA = "SEM_GUIA"            # da Central, ainda sem relação
DIRETO_A_FAZER = "DIRETO"        # do balcão, sem repasse direto registrado
GUIA_GERADA = "GUIA_GERADA"      # na relação, e a guia não foi emitida/registrada
GUIA_REGISTRADA = "GUIA_REGISTRADA"  # guia registrada, e não paga
ETAPAS = (SEM_GUIA, DIRETO_A_FAZER, GUIA_GERADA, GUIA_REGISTRADA)


def central_do_titulo(origem: Any) -> str | None:
    """CRA ou CENPROT para o título da Central; None para o do balcão."""
    o = str(origem or "").strip().upper()
    return o if o in ORIGENS_PELA_CENTRAL else None


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
                   t.cedente_nome, t.saldo_centavos, t.valor_centavos,
                   t.chave_cenprot,
                   a.retorno_id, a.cra_ja_informado_retorno_id,
                   ret.dia AS retorno_dia,
                   ret.cra_enviado_em AS retorno_enviado_em,
                   ret.cra_recusado_em AS retorno_recusado_em
              FROM pt_atos a
              JOIN pt_titulos t ON t.id = a.titulo_id
              LEFT JOIN pt_retornos ret ON ret.id = a.retorno_id
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
        # O BOLETO DA CRA NASCE DO RETORNO (lido no portal, 29/10/2026): sem o
        # retorno com o «pago» aceito pela CRA não há boleto a gerar. Aceito é
        # o arquivo enviado e não recusado — ou o ato marcado «já informado».
        d["retorno_aceito"] = bool(
            (d.get("retorno_enviado_em") and not d.get("retorno_recusado_em"))
            or d.get("cra_ja_informado_retorno_id"))
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
    # O QUE ESTÁ NA RELAÇÃO E AINDA NÃO SAIU DA CASA (29/10/2026). Entrar na
    # relação não é repassar: a rotina gera a relação sozinha, e o dinheiro só
    # sai quando a guia é emitida no portal e paga.
    em_guia = em_guia_sem_pagamento(bd, hoje=hoje)
    return {"pendentes": lista, "por_canal": por_canal,
            "total_centavos": sum(p["valor_centavos"] for p in lista),
            "vencidos": sum(int(p["vencido"]) for p in lista),
            "em_guia": em_guia,
            "vencidos_em_guia": sum(int(p["vencido"]) for p in em_guia),
            "guias_abertas": abertas,
            "a_conciliar": [g for g in abertas if g["situacao"] == "PAGA"]}


# ------------------------------------------- o que falta para o repasse sair


def _atraso(prazo: str, hoje_d: date) -> int:
    return (hoje_d - date.fromisoformat(str(prazo)[:10])).days


def em_guia_sem_pagamento(con, *, hoje: str) -> list[dict]:
    """Os pagamentos que estão numa guia ainda não paga. Só LÊ.

    Uma linha por pagamento, com a guia, a etapa (`GUIA_GERADA` — falta emitir
    no portal e registrar; `GUIA_REGISTRADA` — falta pagar), a Central, o
    prazo que o repasse já guarda e o atraso contado. `desfeito` marca o
    pagamento cancelado depois de entrar na relação: a guia dele não pode ser
    emitida como está.
    """
    bd = banco(con)
    hoje_d = date.fromisoformat(str(hoje)[:10])
    saida = []
    for linha in bd.ler(
            """SELECT r.id AS repasse_id, r.ato_id, r.titulo_id, r.valor_centavos,
                      r.recebido_em, r.prazo, r.guia_id,
                      g.numero AS guia_numero, g.ano AS guia_ano,
                      g.situacao AS situacao_da_guia, g.identificador,
                      g.vencimento,
                      t.numero_titulo, t.protocolo, t.origem, t.chave_cenprot,
                      a.cancelado
                 FROM pt_repasses r
                 JOIN pt_repasse_guias g ON g.id = r.guia_id
                 JOIN pt_titulos t ON t.id = r.titulo_id
                 JOIN pt_atos a ON a.id = r.ato_id
                WHERE r.situacao = 'EM_GUIA'
                  AND g.situacao IN ('GERADA','REGISTRADA')
                ORDER BY r.prazo, r.id"""):
        d = dict(linha)
        atraso = _atraso(d["prazo"], hoje_d)
        d["etapa"] = (GUIA_GERADA if d["situacao_da_guia"] == "GERADA"
                      else GUIA_REGISTRADA)
        d["canal"] = "IEPTB"
        d["central"] = central_do_titulo(d["origem"])
        d["guia"] = f"{d['guia_numero']}/{d['guia_ano']}"
        d["dias_de_atraso"] = max(0, atraso)
        d["vencido"] = atraso > 0
        d["desfeito"] = bool(int(d.get("cancelado") or 0))
        saida.append(d)
    return saida


def _frase_do_prazo(p: dict) -> str:
    frase = (f"pago em {_br(p['recebido_em'])}; repasse até "
             f"{_br(p['prazo'])}")
    if p["vencido"]:
        frase += f" — {p['dias_de_atraso']} dia(s) de atraso"
    return frase


def _explicacao(p: dict) -> str:
    """A frase pronta da pendência: onde o dinheiro está e o passo que falta."""
    prazo = _frase_do_prazo(p)
    portal = PASSO_NO_PORTAL.get(p.get("central") or "")
    onde = portal["onde"] if portal else "no portal da Central"
    if p["etapa"] == DIRETO_A_FAZER:
        return (f"{prazo}. Título do balcão: repasse direto ao apresentante "
                f"(espécie até R$ 300,00, cheque ou depósito) e registre o "
                f"comprovante em Repasses ao apresentante.")
    da_cra = p.get("central") == "CRA"
    if p["etapa"] == SEM_GUIA and da_cra and not p.get("retorno_aceito"):
        return (f"{prazo}. O boleto de repasse da CRA nasce do RETORNO com a "
                f"ocorrência «pago», e o retorno deste pagamento ainda não foi "
                f"aceito pela CRA: mande o retorno (até as 11:30) — só depois o "
                f"boleto aparece {onde}.")
    if p["etapa"] == SEM_GUIA and da_cra:
        aceito = (f" (retorno de {_br(p['retorno_dia'])})"
                  if p.get("retorno_dia") else "")
        return (f"{prazo}. O retorno com o «pago» foi aceito pela CRA{aceito}: "
                f"{onde}, o movimento aparece em «Boletos pendentes de "
                f"geração» — clique «GERAR BOLETO», registre aqui o nosso "
                f"número (a rotina gera a relação quando ligada; senão, gere-a "
                f"em Repasses ao apresentante) e pague o boleto.")
    if p["etapa"] == SEM_GUIA:
        return (f"{prazo}. Ainda sem relação de guia: gere-a em Repasses ao "
                f"apresentante (a rotina automática a gera quando ligada), "
                f"emita a guia {onde} e registre-a aqui.")
    if p.get("desfeito"):
        return (f"{prazo}. O pagamento foi desfeito depois de entrar na guia "
                f"{p['guia']}: cancele essa guia (só o administrador) antes de "
                f"emiti-la ou pagá-la, e gere outra.")
    if p["etapa"] == GUIA_GERADA and da_cra:
        return (f"{prazo}. Está na relação da guia {p['guia']}, ainda NÃO "
                f"registrada: {onde}, gere o boleto («GERAR BOLETO», em "
                f"«Boletos pendentes de geração») e registre aqui o nosso "
                f"número dele.")
    if p["etapa"] == GUIA_GERADA:
        return (f"{prazo}. Está na relação da guia {p['guia']}, que ainda NÃO "
                f"foi emitida: emita-a {onde} e registre aqui o número da guia "
                f"(ou a referência da liquidação).")
    vence = f", que vence em {_br(p['vencimento'])}" if p.get("vencimento") else ""
    numero = "nosso número" if da_cra else "guia"
    portal = (" — ou com a situação do boleto no portal, quando ela deixar de "
              "ser «AGUARDANDO PAGAMENTO»") if da_cra else ""
    return (f"{prazo}. A guia {p['guia']} está registrada ({numero} "
            f"{p.get('identificador') or '—'}){vence}, e ainda NÃO foi paga: "
            f"pague-a e registre o pagamento com o comprovante{portal}.")


def pendencias_do_repasse(con, *, hoje: Any = None,
                          feriados: set[date] | None = None) -> list[dict]:
    """TODO pagamento cujo repasse ainda não saiu da casa. Só LÊ.

    É a lista que o roteiro do dia lê (`protesto_roteiro.GANCHOS`, que chama
    `funcao(con)`) e a que a tela de repasses mostra no alto — uma régua só
    para «o que falta repassar».

    ENTRAR NA RELAÇÃO NÃO TIRA DA LISTA. Aqui estão as quatro etapas: o
    pagamento da Central ainda sem relação (`SEM_GUIA`), o do balcão sem
    repasse direto (`DIRETO`), o que está numa guia que ninguém emitiu ou
    registrou (`GUIA_GERADA`) e o que está numa guia registrada e não paga
    (`GUIA_REGISTRADA`). O pagamento só sai quando a guia é paga — é nesse dia
    que o dinheiro sai da casa e que o art. 19, § 2º se cumpre.

    O CONTRATO DO ROTEIRO: cada linha traz `titulo_id`, `numero_titulo`,
    `protocolo` e `explicacao` — a frase pronta, com o prazo e o passo do
    portal. E mais `etapa`, `central`, `guia`, `prazo`, `vencido`,
    `dias_de_atraso`, `valor_centavos` e `data_ato` — as chaves que a cobrança
    da conduta 10 do roteiro já lê. Nenhuma linha é do acervo: o
    pagamento trazido do E-Ofício já foi repassado fora daqui (`pendentes`).

    `hoje` é `AAAA-MM-DD`; sem ele, o dia do relógio da máquina — o roteiro
    chama só com `con`. `feriados`, sem eles, os da casa.
    """
    dia = str(hoje or date.today().isoformat())[:10]
    if feriados is None:
        feriados = feriados_da_casa(con)
    saida = []
    for p in pendentes(con, hoje=dia, feriados=feriados):
        linha = {k: p.get(k) for k in (
            "ato_id", "titulo_id", "numero_titulo", "protocolo", "canal",
            "data_ato", "recebido_em", "prazo", "vencido", "dias_de_atraso",
            "valor_centavos", "chave_cenprot", "retorno_aceito", "retorno_dia")}
        linha.update(etapa=(SEM_GUIA if p["canal"] == "IEPTB" else DIRETO_A_FAZER),
                     central=central_do_titulo(p["origem"]), guia=None,
                     guia_id=None, desfeito=False)
        saida.append(linha)
    for p in em_guia_sem_pagamento(con, hoje=dia):
        linha = {k: p.get(k) for k in (
            "ato_id", "titulo_id", "numero_titulo", "protocolo", "canal",
            "recebido_em", "prazo", "vencido", "dias_de_atraso",
            "valor_centavos", "chave_cenprot", "etapa", "central", "guia",
            "guia_id", "desfeito", "identificador", "vencimento")}
        linha["data_ato"] = p.get("recebido_em")
        linha["retorno_aceito"], linha["retorno_dia"] = None, None
        saida.append(linha)
    for linha in saida:
        linha["explicacao"] = _explicacao(linha)
        portal = PASSO_NO_PORTAL.get(linha.get("central") or "")
        linha["onde"] = portal["onde"] if portal else ""
    saida.sort(key=lambda x: (str(x["prazo"]), int(x["ato_id"])))
    return saida


# ---------------------------------------------------------------- a guia


def _relacao_da_guia(numero: int, ano: int, itens: list[dict]) -> str:
    """O teor da relação que a guia paga — uma linha por título, por apresentante.

    AS TRÊS COLUNAS DO FIM (29/10/2026) são para quem vai ao portal: o PRAZO do
    art. 19, § 2º, a CENTRAL por onde o título veio (é ela que diz em que
    portal a guia se emite) e a CHAVE única da CENPROT, que é como o portal
    acha o título. Não há leiaute de guia a imitar — o E-Ofício nunca a
    gerou nesta casa —; a relação é a lista de conferência de quem a emite.
    """
    linhas = [f"GUIA DE REPASSE AO IEPTB Nº {numero}/{ano}",
              ("PROTOCOLO;TITULO;ESPECIE;APRESENTANTE;PAGO_EM;VALOR;PRAZO;"
               "CENTRAL;CHAVE_CENPROT")]
    for i in sorted(itens, key=lambda x: (str(x["apresentante_codigo"] or ""),
                                          x["recebido_em"], x["ato_id"])):
        linhas.append(";".join([
            str(i["protocolo"] or ""), str(i["numero_titulo"] or ""),
            str(i["especie"] or ""),
            f"{i['apresentante_codigo'] or ''} {i['apresentante_nome'] or ''}".strip(),
            _br(i["recebido_em"]), reais(i["valor_centavos"]),
            _br(i.get("prazo")), str(central_do_titulo(i.get("origem")) or ""),
            str(i.get("chave_cenprot") or "")]))
    total = sum(i["valor_centavos"] for i in itens)
    linhas.append(f"TOTAL;{len(itens)} título(s);;;;{reais(total)}")
    return "\n".join(linhas) + "\n"


def gerar_guia(con, *, hoje: str, agora: str, usuario: str | None = None,
               ato_ids: list[int] | None = None,
               feriados: set[date] | None = None,
               origem: str | None = None) -> dict:
    """Gera a guia de repasse ao IEPTB com os pagamentos da Central. ESCREVE.

    A TRAVA VEM ANTES DA LISTA: ler os pendentes e só depois travar deixaria
    duas guias geradas ao mesmo tempo pegarem o mesmo pagamento. Sem `ato_ids`,
    entram todos os pendentes do canal IEPTB — e, com `origem` (CRA ou
    CENPROT), só os da Central dita (`gerar_guias_do_dia`).

    Recusa pagamento de título do balcão (esse se repassa direto) e pagamento
    que já está noutra guia — dizendo qual.
    """
    central = None
    if origem is not None:
        central = central_do_titulo(origem)
        if not central:
            raise RepasseError(
                f"Central desconhecida: {origem!r}. A guia é da CRA ou da "
                f"CENPROT.")
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
        outra = [p for p in lista if central
                 and central_do_titulo(p["origem"]) != central]
        if outra:
            raise RepasseError(
                f"Esta guia é da {central}, e estes títulos vieram por outra "
                f"Central: " + ", ".join(str(p["numero_titulo"]) for p in outra)
                + ".")
    lista = [p for p in lista if p["canal"] == "IEPTB"
             and (central is None or central_do_titulo(p["origem"]) == central)]
    if not lista:
        raise RepasseError("Não há pagamento de título da Central esperando repasse"
                           + (f" (da {central})." if central else "."))

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
            "titulos": len(lista), "total_centavos": total,
            "central": central,
            "prazo": min(str(p["prazo"]) for p in lista)}


def gerar_guias_do_dia(con, *, hoje: str, agora: str,
                       usuario: str | None = None,
                       feriados: set[date] | None = None) -> list[dict]:
    """As relações do dia: uma por Central, com os pagamentos dela ainda sem
    guia. ESCREVE. É o que a rotina automática faz.

    UMA POR CENTRAL, e não uma para todas: o título da CENPROT se liquida no
    portal da CENPROT e o da CRA no boleto de repasse da CRA-MA, e uma
    relação misturada não se emite em nenhum dos dois. Duas relações se
    emitem nos dois casos — inclusive se um dia os dois portais forem o mesmo.

    O DA CRA SÓ ENTRA COM O RETORNO ACEITO (lido no portal, 29/10/2026): o
    boleto de repasse da CRA nasce do retorno com a ocorrência «pago». Antes
    dele não há boleto a gerar, e o pagamento fica na pendência dizendo que
    falta o retorno — a relação dele sai na rodada seguinte ao envio.

    Sem pagamento esperando, não gera nada e devolve lista vazia: guia vazia
    seria número consumido sem dinheiro nenhum. Rodar duas vezes no mesmo dia
    não repete pagamento — o que já está numa relação não está mais em
    `pendentes`.
    """
    bd = banco(con)
    bd.travar(TRAVA_DO_REPASSE)
    bd.travar(TRAVA_DA_GUIA)
    prontos: dict[str, list[int]] = {c: [] for c in ORIGENS_PELA_CENTRAL}
    for p in pendentes(bd, hoje=hoje, feriados=feriados, canal="IEPTB"):
        central = central_do_titulo(p["origem"])
        if central == "CRA" and not p["retorno_aceito"]:
            continue
        prontos[central].append(int(p["ato_id"]))
    return [gerar_guia(bd, hoje=hoje, agora=agora, usuario=usuario,
                       feriados=feriados, origem=central, ato_ids=atos)
            for central, atos in prontos.items() if atos]


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
    que saiu sem endereço. No boleto de repasse da CRA ele é o NOSSO NÚMERO
    que o portal mostra na lista dos boletos (12 dígitos no lido em
    29/10/2026), com os zeros da frente — guardado como texto, sem conta.
    Mais de um boleto para a mesma relação: os nossos números separados por
    vírgula.
    """
    bd = banco(con)
    guia = _exigir(guia_para_gravar(bd, guia_id), guia_id, "GERADA")
    ident = " ".join(str(identificador or "").split())
    if len(ident) < 5:
        raise RepasseError(
            "Informe o número da guia que o portal emitiu — no boleto de "
            "repasse da CRA, o nosso número; na CENPROT, o número da guia ou a "
            "referência da liquidação.")
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
               agora: str, usuario: str | None = None,
               prova: str = "COMPROVANTE") -> dict:
    """Registra o pagamento da guia — e com ele o repasse dos títulos. ESCREVE.

    O REPASSE SE CUMPRE AQUI, e não na conciliação: o dinheiro saiu da casa no
    dia em que a guia foi paga, e é contra esse dia que o prazo do art. 19,
    § 2º se mede. A conciliação é a confirmação do Instituto, e vem depois.

    A PROVA É O COMPROVANTE DO BANCO OU A SITUAÇÃO NO PORTAL (`prova`,
    29/10/2026): é só com uma das duas que o título sai da pendência. A
    situação «AGUARDANDO PAGAMENTO» é a do boleto em aberto e NÃO prova nada
    — lido no portal da CRA: o boleto pago no dia continuava nela.
    """
    bd = banco(con)
    guia = _exigir(guia_para_gravar(bd, guia_id), guia_id, "REGISTRADA")
    try:
        dia = date.fromisoformat(str(paga_em or "")[:10]).isoformat()
    except ValueError:
        raise RepasseError("Informe o dia em que a guia foi paga.") from None
    if dia < str(guia["dia"])[:10]:
        raise RepasseError("A guia não pode ter sido paga antes de ser gerada.")
    forma_da_prova = str(prova or "COMPROVANTE").strip().upper()
    if forma_da_prova not in PROVAS_DO_PAGAMENTO:
        raise RepasseError(
            f"Prova do pagamento desconhecida: {prova!r}. As que valem são: "
            f"{'; '.join(PROVAS_DO_PAGAMENTO.values())}.")
    prova = " ".join(str(comprovante or "").split())
    if len(prova) < 3:
        raise RepasseError(
            "Informe o comprovante do pagamento da guia (autenticação ou "
            "número da transação) — ou a situação do boleto no portal.")
    if "AGUARDANDO" in prova.upper():
        raise RepasseError(
            f"«{SITUACAO_EM_ABERTO_NO_PORTAL}» é a situação do boleto em aberto, "
            f"e não prova o pagamento: registre com o comprovante do banco, ou "
            f"espere a situação mudar no portal.")
    if forma_da_prova == "PORTAL":
        prova = f"situação no portal: {prova}"
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
            "total_centavos": int(guia["total_centavos"]),
            "prova": forma_da_prova}


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


def guia(con, guia_id: int, *, hoje: str | None = None) -> dict | None:
    """A guia e os repasses dela, com o passo do portal e o prazo. Só LÊ.

    `centrais` são as Centrais dos títulos da relação, e `passos` o que se faz
    no portal de cada uma (`PASSO_NO_PORTAL`). `prazo` é o mais curto dos
    repasses dela — é contra ele que a guia não paga atrasa. Com `hoje`,
    `vencida` diz se ele já passou com a guia ainda não paga.
    """
    bd = banco(con)
    g = bd.um("SELECT * FROM pt_repasse_guias WHERE id=%s", (int(guia_id),))
    if not g:
        return None
    g["repasses"] = bd.ler(
        """SELECT r.*, t.numero_titulo, t.protocolo, t.origem
             FROM pt_repasses r JOIN pt_titulos t ON t.id = r.titulo_id
            WHERE r.guia_id=%s ORDER BY r.id""", (int(guia_id),))
    g["centrais"] = sorted({c for c in (central_do_titulo(r["origem"])
                                         for r in g["repasses"]) if c})
    g["passos"] = [PASSO_NO_PORTAL[c] for c in g["centrais"]]
    prazos = [str(r["prazo"])[:10] for r in g["repasses"] if r.get("prazo")]
    g["prazo"] = min(prazos) if prazos else None
    g["vencida"] = bool(
        hoje and g["prazo"] and g["situacao"] in ("GERADA", "REGISTRADA")
        and str(hoje)[:10] > g["prazo"])
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
