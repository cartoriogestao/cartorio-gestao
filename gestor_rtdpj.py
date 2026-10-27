"""O AGENTE DO RTD/PJ — fiscaliza o Registro de Títulos e Documentos e o Registro
Civil das Pessoas Jurídicas, e conserta o que é mecânico.

    «Agente RTDPJ: fiscaliza e resolver problemas do RTDPJ» — o oficial, 09/10/2026

O QUE A CONFERÊNCIA ACHOU, NA PRODUÇÃO, NO DIA EM QUE O AGENTE NASCEU
    Medido em 09/10/2026 (só leitura) — 73 registros, 75 atos, 1 título:

    1. **O título n. 1 do RCPJ ficou «Qualificado» para sempre.** Era uma ata e
       um estatuto para AVERBAR no registro n. 148 (Caixa Escolar Uex Santa
       Isabel); as averbações 378 e 379 foram lavradas e seladas em 11/09 pela
       ficha do registro, gastando os itens do protocolo dele — e não havia
       caminho que fechasse o título: `registrar` abre registro novo, e
       `encerrar` só diz «devolvido» ou «cancelado». A saída nasceu no mesmo dia
       (`rg_titulo.concluir_pelo_ato`).
    2. **A etiqueta da averbação 378 saiu seis vezes com o selo da PRENOTAÇÃO**
       (15.1, R$ 42,60) no lugar do da averbação (15.9.1): a coluna `selo`
       guardava o primeiro que saiu. A régua nasceu no mesmo dia
       (`rg_registro.papel_dos_selos`).
    3. O protocolo geral 2026.09.17 desse título está **A_PAGAR**: R$ 1.034,98
       em itens, cinco selos e uma certidão consumidos, nenhum lançamento.
    4. O Livro de Protocolo do RCPJ está **sem o termo de encerramento do dia
       11/09/2026**.
    5. O registro n. 1256 do Livro B do RTD está **duas vezes** na base — o
       E-Ofício gravou a mesma linha duas vezes (folha «79» e «079»), e a carga
       trouxe as duas.

AS REGRAS SÃO CÓDIGO, como as de `gestor_conferencia`: quem decide se o achado
existe é a consulta. E **o agente não lavra, não sela, não numera e não
cobra** — o que ele conserta sozinho são duas anotações mecânicas, cada uma com
a ponte gravada que a prova e uma linha na auditoria com o antes e o depois:

    - concluir o título qualificado cujo ato já foi lavrado com os itens do
      protocolo dele, quando todos esses atos são do mesmo registro;
    - pôr na coluna `selo` do ato o selo do próprio ato, e não o da prenotação.

**Nenhum prazo foi inventado.** O título parado aparece com os dias contados e a
data de onde se conta; prazo só se afirma quando quem qualificou o escreveu.

ONDE MORA
    Ligado à conferência por `gestor_conferencia.regra_rtdpj` e à rotina por
    `gestor_rotina` (rótulos, regras sem tarefa e a correção antes da
    conferência) — o mesmo feitio de `gestor_cargas_ri`.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Callable

from bd_nativo import banco
import identidade_do_robo as IDR

QUEM = "gestor"

#: A data a partir da qual a casa lavra no sistema — a mesma régua de
#: `gestor_conferencia.IMPLANTACAO`, repetida aqui de propósito para este
#: módulo não depender de importar aquele (é ele que importa este).
IMPLANTACAO = "2026-09-10"

SETOR_OPERACIONAL = "RCPJ_RTD"
SETOR_QUALIFICACAO = "RCPJ_RTD_QUALIFICACAO"
SETOR_GESTAO = "GESTAO"

TITULO_ATENDIDO = "RTDPJ_TITULO_ATENDIDO"
TITULO_PARADO = "RTDPJ_TITULO_PARADO"
SELO_DA_ETIQUETA = "RTDPJ_SELO_DA_ETIQUETA"
CERTIDAO_SEM_SELO = "RTDPJ_CERTIDAO_SEM_SELO"
CENTRAL_PENDENTE = "RTDPJ_CENTRAL_PENDENTE"
CENTRAL_NAO_LIDA = "RTDPJ_CENTRAL_NAO_LIDA"
ENCERRAMENTO_DIARIO = "RTDPJ_ENCERRAMENTO_DIARIO"
LIVRO = "RTDPJ_LIVRO"
SEM_PAGAMENTO = "RTDPJ_SEM_PAGAMENTO"
REGISTRO_REPETIDO = "RTDPJ_REGISTRO_REPETIDO"
CORRIGIDO = "RTDPJ_CORRIGIDO"

ROTULOS = {
    TITULO_ATENDIDO: "RTD/PJ — títulos já atendidos e não concluídos",
    TITULO_PARADO: "RTD/PJ — títulos parados no protocolo",
    SELO_DA_ETIQUETA: "RTD/PJ — atos com o selo da prenotação no lugar do selo do ato",
    CERTIDAO_SEM_SELO: "RTD/PJ — certidões emitidas sem selo",
    CENTRAL_PENDENTE: "RTD/PJ — pedidos esperando na Central ONRTDPJ",
    CENTRAL_NAO_LIDA: "RTD/PJ — Central ONRTDPJ não respondeu",
    ENCERRAMENTO_DIARIO: "RTD/PJ — Livro de Protocolo sem encerramento do dia",
    LIVRO: "RTD/PJ — conferência dos livros",
    SEM_PAGAMENTO: "RTD/PJ — protocolos com selo gasto e sem pagamento",
    REGISTRO_REPETIDO: "RTD/PJ — número de registro repetido na base",
    CORRIGIDO: "RTD/PJ — o que o agente corrigiu sozinho (para revisar)",
}

#: O critério do oficial (06/10/2026): só vira tarefa o que pode gerar
#: responsabilidade civil. Livro sem termo do dia e conferência do livro são
#: da inspeção (sanção administrativa); dinheiro sem lançamento é da casa; o
#: número repetido do acervo e a Central fora do ar são decisão e aviso; o que o
#: agente corrigiu é para o oficial revisar. Todos continuam no relatório.
REGRAS_SEM_TAREFA = frozenset({
    CENTRAL_NAO_LIDA, ENCERRAMENTO_DIARIO, LIVRO, SEM_PAGAMENTO,
    REGISTRO_REPETIDO, CORRIGIDO,
})

FUNDAMENTO = "Lei 6.015/1973, arts. 114 a 148; Lei 8.935/1994, art. 30"

#: «Onde abrir» de cada regra — (caminho no menu, endereço).
TELA = {
    TITULO_ATENDIDO: ("RTD/PJ → Títulos", "/rcpj-rtd/titulos"),
    TITULO_PARADO: ("RTD/PJ → Títulos", "/rcpj-rtd/titulos"),
    CENTRAL_PENDENTE: ("RTD/PJ → Central ONRTDPJ", "/rcpj-rtd/onrtdpj"),
    ENCERRAMENTO_DIARIO: ("Livros e acervo → Encerramento diário",
                          "/nucleo/encerramento-diario"),
}

#: O texto didático das tarefas — regra → (por que existe, [passos]).
GUIA: dict[str, tuple[str, list[str]]] = {
    TITULO_ATENDIDO: (
        "O título foi qualificado e o ato que o atende já está no livro — uma "
        "averbação ou um cancelamento lavrado na ficha de um registro que já "
        "existia —, mas o título continua «Qualificado», como se esperasse "
        "registro.",
        ["Abra a ficha do título (o endereço está em cada item).",
         "Em «Já foi averbado? Concluir pelo ato lavrado», escolha o ato e "
         "confirme. Nada é lavrado nem cobrado ali.",
         "Se a sua versão do sistema ainda não tem esse quadro, o agente "
         "conclui sozinho na conferência seguinte quando o ato gastou o "
         "protocolo do título — e avisa no relatório."]),
    TITULO_PARADO: (
        "Título protocolado em dia anterior que ainda não teve decisão: sem "
        "qualificação, qualificado e não registrado, ou com a exigência cujo "
        "prazo (o que quem qualificou escreveu) já passou. O protocolo do "
        "RTD/PJ garante a prioridade do título — título esquecido é "
        "prioridade perdida para quem apresentou.",
        ["Abra a ficha do título.",
         "Qualifique, registre, ou encerre (devolvido ou cancelado) com o "
         "motivo escrito.",
         "Se a exigência venceu e o apresentante não voltou, encerre como "
         "devolvido."]),
    SELO_DA_ETIQUETA: (
        "A coluna do selo do ato guarda o selo da PRENOTAÇÃO (item 15.1), e "
        "não o do próprio ato. É esse número que sai na etiqueta colada no "
        "título e no carimbo — quem conferir lê uma prenotação.",
        ["O agente corrige a coluna sozinho na conferência seguinte e registra "
         "o antes e o depois.",
         "Se a etiqueta já foi colada no título, imprima a etiqueta de novo "
         "pela ficha do registro e substitua a antiga."]),
    CERTIDAO_SEM_SELO: (
        "Certidão do RTD/PJ emitida e não cancelada sem selo de fiscalização. "
        "Papel sem selo que saiu da casa não vale como certidão.",
        ["Abra a ficha do registro e confira a certidão.",
         "Se ela não foi entregue, cancele-a com o motivo; se foi, emita a "
         "segunda via com selo e recolha a primeira."]),
    CENTRAL_PENDENTE: (
        "A Central ONRTDPJ tem pedido esperando esta serventia. É por ali que "
        "chegam o título eletrônico e a notificação; pedido parado na Central "
        "é serviço de alguém parado.",
        ["Abra RTD/PJ → Central ONRTDPJ.",
         "Traga o pedido para o protocolo (botão da própria fila) e siga como "
         "título."]),
}

CODIGO_TJ_PRENOTACAO = "15.1"
CODIGO_TJ_ARQUIVAMENTO = "15.22"
_ATO_NO_TEXTO = re.compile(r"Ato:\s*([0-9][0-9.]*[0-9])")


def registrar_na_didatica() -> None:
    """Põe o texto didático e as telas do RTD/PJ em `gestor_didatica` — a
    mesma forma de `agente_notas.registrar_na_didatica`."""
    try:
        import gestor_didatica as D
    except ImportError:
        return
    for k, v in GUIA.items():
        D.GUIA.setdefault(k, v)
    for k, v in TELA.items():
        D.TELA.setdefault(k, v)


# ------------------------------------------------------------------ apoio

def _achado(chave, regra, gravidade, setor, titulo, detalhe="", prazo=None) -> dict:
    """O mesmo formato de `gestor_conferencia._achado`."""
    return {"chave": chave, "regra": regra, "gravidade": gravidade,
            "setor": setor, "titulo": titulo, "detalhe": detalhe,
            "prazo": prazo.isoformat() if isinstance(prazo, date) else prazo,
            "fundamento": FUNDAMENTO}


def _tem_tabela(con, nome: str) -> bool:
    return banco(con).tem_tabela(nome)


def _tem_colunas(con, tabela: str, *colunas: str) -> bool:
    bd = banco(con)
    return all(bd.tem_coluna(tabela, c) for c in colunas)


def _dia(texto) -> date | None:
    bruto = str(texto or "")[:10]
    try:
        return date(int(bruto[:4]), int(bruto[5:7]), int(bruto[8:10]))
    except (ValueError, IndexError):
        return None


def _br(d) -> str:
    x = d if isinstance(d, date) else _dia(d)
    return x.strftime("%d/%m/%Y") if x else str(d or "")


def _centavos(valor) -> int:
    """'1.034,98' → 103498. O dinheiro do protocolo é texto nesta casa."""
    t = str(valor or "").strip().replace("R$", "").replace(" ", "")
    if not t:
        return 0
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return round(float(t) * 100)
    except ValueError:
        return 0


def _brl(centavos: int) -> str:
    inteiro, resto = divmod(int(centavos), 100)
    return f"{inteiro:,}".replace(",", ".") + f",{resto:02d}"


def codigo_do_selo(referencia, texto) -> str:
    """O item da tabela do selo: pela referência (`rg_atos:79:15.1:1`), que é
    a que este sistema grava, e pelo texto do selo («Ato: 15.1,»)."""
    partes = str(referencia or "").split(":")
    if len(partes) >= 3 and partes[2].strip():
        return partes[2].strip()
    m = _ATO_NO_TEXTO.search(str(texto or ""))
    return m.group(1) if m else ""


# --------------------------------------------------------------- as regras

def atendidos(con) -> list[dict]:
    """Os títulos QUALIFICADOS cujo ato já foi lavrado com os itens do protocolo
    deles — averbação ou cancelamento, que é o que não abre registro. Só LÊ."""
    if not (_tem_tabela(con, "rg_titulos")
            and _tem_colunas(con, "cx_protocolo_atos", "usado_por_tabela",
                             "usado_por_ato_id")):
        return []
    saida: dict[int, dict] = {}
    for r in banco(con).ler(
            """SELECT t.id titulo_id, t.numero, t.atribuicao, t.apresentante,
                      t.data_apresentacao, a.id ato_id, a.tipo, a.numero_ordem,
                      a.data_ato, a.registro_id, g.numero registro_numero,
                      g.serie
                 FROM rg_titulos t
                 JOIN cx_protocolo_atos i ON i.protocolo_id = t.protocolo_geral_id
                 JOIN rg_atos a ON a.id = i.usado_por_ato_id
                 JOIN rg_registros g ON g.id = a.registro_id
                WHERE t.situacao = 'QUALIFICADO'
                  AND i.usado_por_tabela = 'rg_atos'
                  AND a.tipo IN ('AVERBACAO','CANCELAMENTO')
                  AND g.atribuicao = t.atribuicao
                ORDER BY t.id, a.id"""):
        t = saida.setdefault(int(r["titulo_id"]), {
            "titulo_id": int(r["titulo_id"]), "numero": r["numero"],
            "atribuicao": r["atribuicao"], "apresentante": r["apresentante"],
            "atos": []})
        if all(int(a["ato_id"]) != int(r["ato_id"]) for a in t["atos"]):
            t["atos"].append(dict(r))
    return list(saida.values())


def regra_titulo_atendido(con, hoje: date) -> list[dict]:
    saida = []
    for t in atendidos(con):
        atos = ", ".join(
            f"{'AV' if a['tipo'] == 'AVERBACAO' else 'CANC'} n. "
            f"{a['numero_ordem'] or '?'} do registro n. {a['registro_numero']}"
            f" ({_br(a['data_ato'])})" for a in t["atos"])
        saida.append(_achado(
            f"RTDPJ_ATENDIDO:{t['titulo_id']}", TITULO_ATENDIDO, "ATENCAO",
            SETOR_QUALIFICACAO,
            f"Título n. {t['numero']} ({t['apresentante'] or 'sem apresentante'}) "
            f"já atendido e ainda «Qualificado»",
            f"Atendido por {atos}. Abra: /rcpj-rtd/titulo/{t['titulo_id']}"))
    return saida


def regra_titulo_parado(con, hoje: date) -> list[dict]:
    if not _tem_tabela(con, "rg_titulos"):
        return []
    ja_atendidos = {t["titulo_id"] for t in atendidos(con)}
    saida = []
    for t in banco(con).ler(
            """SELECT t.*, (SELECT MAX(q.data_qualificacao) FROM rg_qualificacoes q
                             WHERE q.titulo_id = t.id) AS qualificado_em,
                      (SELECT q.prazo_ate FROM rg_qualificacoes q
                        WHERE q.titulo_id = t.id ORDER BY q.ordem DESC LIMIT 1)
                        AS prazo_da_exigencia
                 FROM rg_titulos t
                WHERE t.situacao IN ('APRESENTADO','QUALIFICADO','EXIGENCIA')
                  AND t.data_apresentacao >= %s
                ORDER BY t.id""", (IMPLANTACAO,)):
        if int(t["id"]) in ja_atendidos:
            continue                    # é a regra de cima, com saída própria
        quem = t["apresentante"] or "sem apresentante"
        abrir = f"Abra: /rcpj-rtd/titulo/{t['id']}"
        if t["situacao"] == "EXIGENCIA":
            prazo = _dia(t["prazo_da_exigencia"] or t["prazo_ate"])
            if prazo is None or prazo >= hoje:
                continue
            saida.append(_achado(
                f"RTDPJ_PARADO:{t['id']}", TITULO_PARADO, "VENCIDO",
                SETOR_QUALIFICACAO,
                f"Título n. {t['numero']} ({quem}): a exigência venceu em "
                f"{_br(prazo)}",
                f"O prazo é o que quem qualificou escreveu. Devolver ou "
                f"requalificar. {abrir}", prazo))
            continue
        desde = _dia(t["qualificado_em"] if t["situacao"] == "QUALIFICADO"
                     else t["data_apresentacao"])
        if desde is None or desde >= hoje:
            continue                    # o título de hoje ainda está no dia dele
        dias = (hoje - desde).days
        o_que = ("qualificado e sem registro" if t["situacao"] == "QUALIFICADO"
                 else "sem qualificação")
        saida.append(_achado(
            f"RTDPJ_PARADO:{t['id']}", TITULO_PARADO, "ATENCAO",
            SETOR_QUALIFICACAO,
            f"Título n. {t['numero']} ({quem}) {o_que} há {dias} dia(s)",
            f"Desde {_br(desde)}. Não é prazo da lei — é o tempo contado, para "
            f"quem decide saber. {abrir}"))
    return saida


def selos_do_ato(con, ato_id: int) -> list[tuple[str, str]]:
    """`(codigo_tj, numero)` dos selos não cancelados de um ato do RTD/PJ, na
    ordem em que entraram. A chave é `tabela` + `ato_id`. Só LÊ."""
    if not _tem_tabela(con, "sd_selos"):
        return []
    return [(codigo_do_selo(r["referencia"], r["texto"]), r["numero"])
            for r in banco(con).ler(
                """SELECT numero, referencia, texto FROM sd_selos
                    WHERE tabela = 'rg_atos' AND ato_id = %s
                      AND cancelado_em IS NULL ORDER BY id""", (int(ato_id),))]


def principal_dos_selos(saidos: list[tuple[str, str]]) -> str | None:
    """O selo do próprio ato — a régua de `rg_registro.papel_dos_selos`. Usa a
    da casa quando ela existe; a cópia abaixo vale só para a versão instalada
    que ainda não a tem (o gestor da produção importa os módulos de lá)."""
    try:
        import rg_registro
        return rg_registro.papel_dos_selos(saidos)[0]
    except (ImportError, AttributeError):
        principal = prenotacao = None
        for codigo, numero in saidos:
            if codigo == CODIGO_TJ_ARQUIVAMENTO:
                continue
            if codigo == CODIGO_TJ_PRENOTACAO:
                prenotacao = prenotacao or numero
            else:
                principal = principal or numero
        return principal or prenotacao


def selos_trocados(con) -> list[dict]:
    """Atos cuja coluna `selo` não é o selo do próprio ato. Só LÊ."""
    if not _tem_tabela(con, "sd_selos"):
        return []
    saida = []
    for a in banco(con).ler(
            """SELECT a.id, a.tipo, a.selo, a.numero_ordem, a.registro_id,
                      COALESCE(a.etiqueta_impressoes, 0) impressoes,
                      g.numero registro_numero, g.serie
                 FROM rg_atos a JOIN rg_registros g ON g.id = a.registro_id
                WHERE COALESCE(a.selo, '') <> ''
                  AND EXISTS (SELECT 1 FROM sd_selos s WHERE s.tabela = 'rg_atos'
                                 AND s.ato_id = a.id)
                ORDER BY a.id"""):
        selos = selos_do_ato(con, int(a["id"]))
        certo = principal_dos_selos(selos)
        if certo and certo != a["selo"]:
            codigo_atual = next((c for c, n in selos if n == a["selo"]), "")
            saida.append(dict(a, certo=certo, codigo_atual=codigo_atual))
    return saida


def regra_selo_da_etiqueta(con, hoje: date) -> list[dict]:
    saida = []
    for a in selos_trocados(con):
        saida.append(_achado(
            f"RTDPJ_SELO:{a['id']}", SELO_DA_ETIQUETA, "ATENCAO",
            SETOR_QUALIFICACAO,
            f"{'AV' if a['tipo'] == 'AVERBACAO' else a['tipo'].title()} n. "
            f"{a['numero_ordem'] or '?'} do registro n. {a['registro_numero']} "
            f"({a['serie']}): a coluna do selo tem {a['selo']}"
            + (f" (item {a['codigo_atual']})" if a["codigo_atual"] else ""),
            f"O selo do ato é {a['certo']}. A etiqueta foi impressa "
            f"{a['impressoes']} vez(es) com o número errado. Abra: "
            f"/rcpj-rtd/{a['registro_id']}"))
    return saida


def regra_certidao_sem_selo(con, hoje: date) -> list[dict]:
    if not _tem_tabela(con, "at_certidoes"):
        return []
    saida = []
    for c in banco(con).ler(
            """SELECT id, numero, ano, registro_id, registro_numero, emitida_em
                 FROM at_certidoes
                WHERE atribuicao = 'RCPJ_RTD' AND COALESCE(selo, '') = ''
                  AND COALESCE(cancelada, 0) = 0 AND emitida_em >= %s
                ORDER BY id""",
            (IMPLANTACAO,)):
        saida.append(_achado(
            f"RTDPJ_CERTIDAO:{c['id']}", CERTIDAO_SEM_SELO, "CRITICO",
            SETOR_QUALIFICACAO,
            f"Certidão {c['numero']}/{c['ano']} do registro n. "
            f"{c['registro_numero']} emitida sem selo",
            f"Emitida em {_br(c['emitida_em'])}. Abra: "
            f"/rcpj-rtd/{c['registro_id']}"))
    return saida


def _pendentes_da_central() -> list[dict] | None:
    """A fila da Central, ou `None` quando não há credencial. FALA COM A REDE
    (só GET — a mesma chamada da tela «Central ONRTDPJ»)."""
    import onrtdpj_api as ONR
    if not ONR.tem_credencial():
        return None
    return ONR.pendentes()


def regra_central(con, hoje: date, central: Callable | None = None) -> list[dict]:
    """O que a Central ONRTDPJ tem esperando a casa.

    **A FALHA NÃO VIRA ZERO.** Central fora do ar aparece como «não respondeu»,
    e não como fila vazia — lista vazia diria que não há pedido, e isso seria
    afirmar o que não se perguntou.
    """
    buscar = central or _pendentes_da_central
    try:
        fila = buscar()
    except Exception as erro:                       # noqa: BLE001 — vira achado
        return [_achado(
            f"RTDPJ_CENTRAL_NAO_LIDA:{hoje.isoformat()}", CENTRAL_NAO_LIDA,
            "ATENCAO", SETOR_OPERACIONAL,
            "Não deu para perguntar à Central ONRTDPJ o que está pendente",
            f"{type(erro).__name__}: {erro}. Isto NÃO quer dizer que não há "
            f"pedido — confira a fila pela tela.")]
    if not fila:
        return []
    saida = []
    for p in fila:
        protocolo = str(p.get("Protocolo") or p.get("protocolo") or "?")
        servico = p.get("Servico") or {}
        cliente = p.get("Cliente") or {}
        nome_servico = (servico.get("Nome") if isinstance(servico, dict) else servico) or ""
        nome_cliente = (cliente.get("Nome") if isinstance(cliente, dict) else cliente) or ""
        saida.append(_achado(
            f"RTDPJ_CENTRAL:{protocolo}", CENTRAL_PENDENTE, "ATENCAO",
            SETOR_OPERACIONAL,
            f"Pedido {protocolo} esperando na Central ONRTDPJ"
            + (f" — {nome_servico}" if nome_servico else ""),
            (f"Cliente: {nome_cliente}. " if nome_cliente else "")
            + "Abra: /rcpj-rtd/onrtdpj"))
    return saida


def regra_encerramento_diario(con, hoje: date) -> list[dict]:
    import escrituracao as ESC
    saida = []
    for serie, nome in (("PJ_PROTOCOLO", "Livro de Protocolo do RCPJ"),
                        ("TD_PROTOCOLO", "Livro de Protocolo do RTD")):
        for dia in ESC.dias_sem_encerrar(con, serie):
            d = _dia(dia)
            if d is None or d >= hoje:
                continue                # o dia de hoje ainda pode ser encerrado
            saida.append(_achado(
                f"RTDPJ_ENCERRAMENTO:{serie}:{dia}", ENCERRAMENTO_DIARIO,
                "ATENCAO", SETOR_OPERACIONAL,
                f"{nome}: o dia {_br(d)} não tem termo de encerramento",
                "Dia sem movimento também se encerra. Abra: Livros e acervo → "
                "Encerramento diário"))
    return saida


def regra_livro(con, hoje: date) -> list[dict]:
    """O que a conferência do próprio livro (`escrituracao.conferir_livro`)
    acha nos livros abertos do RCPJ e do RTD — menos o termo do dia, que é a
    regra de cima."""
    import escrituracao as ESC
    saida = []
    for lv in banco(con).ler(
            """SELECT id, serie, numero FROM nu_livros
                WHERE (serie ILIKE 'PJ%' OR serie ILIKE 'TD%')
                  AND COALESCE(encerrado, 0) = 0 ORDER BY id"""):
        r = ESC.conferir_livro(con, int(lv["id"]))
        for n, frase in enumerate(r.get("achados") or []):
            if "encerramento diário" in frase:
                continue
            saida.append(_achado(
                f"RTDPJ_LIVRO:{lv['id']}:{n}", LIVRO, "ATENCAO",
                SETOR_OPERACIONAL,
                f"{r.get('serie_nome') or lv['serie']} n. {lv['numero']}: {frase}",
                f"Abra: /nucleo/livros/{lv['id']}"))
    return saida


def regra_sem_pagamento(con, hoje: date) -> list[dict]:
    """Protocolo do RCPJ/RTD com item já gasto por ato e nada quitado. É
    achado da Gestão, e não acusação: a casa também cobra por lançamento à
    mão, e o pagamento pode ter entrado por outro caminho — conferir."""
    if not (_tem_tabela(con, "cx_protocolos")
            and _tem_colunas(con, "cx_protocolo_atos", "usado_por_tabela",
                             "quitado", "lancamento_id")):
        return []
    saida = []
    bd = banco(con)
    for p in bd.ler(
            """SELECT id, numero, interessado, data_abertura, situacao,
                      valor_total
                 FROM cx_protocolos
                WHERE atribuicao IN ('RCPJ','RTD','RTDPJ')
                  AND data_abertura >= %s
                  AND situacao NOT IN ('PAGO','CANCELADO')
                ORDER BY id""", (IMPLANTACAO,)):
        usados = bd.ler(
            """SELECT valor_total, quitado, lancamento_id FROM cx_protocolo_atos
                WHERE protocolo_id = %s AND usado_por_tabela IS NOT NULL
                ORDER BY id""",
            (int(p["id"]),))
        devidos = [u for u in usados
                   if not int(u["quitado"] or 0) and u["lancamento_id"] is None]
        if not devidos:
            continue
        valor = sum(_centavos(u["valor_total"]) for u in devidos)
        saida.append(_achado(
            f"RTDPJ_PAGAMENTO:{p['id']}", SEM_PAGAMENTO, "ATENCAO", SETOR_GESTAO,
            f"Protocolo {p['numero']} ({p['interessado'] or '—'}): "
            f"R$ {_brl(valor)} em itens já gastos por ato, sem pagamento",
            f"{len(devidos)} item(ns) usado(s) e não quitado(s); situação "
            f"{p['situacao']}. Pode ter sido cobrado por lançamento à mão — "
            f"conferir no caixa."))
    return saida


def regra_registro_repetido(con, hoje: date) -> list[dict]:
    saida = []
    for r in banco(con).ler(
            """SELECT serie, numero, COUNT(*) n, MIN(id) primeiro, MAX(id) ultimo
                 FROM rg_registros WHERE numero IS NOT NULL
                GROUP BY serie, numero HAVING COUNT(*) > 1
                ORDER BY serie, numero"""):
        saida.append(_achado(
            f"RTDPJ_REPETIDO:{r['serie']}:{r['numero']}", REGISTRO_REPETIDO,
            "ATENCAO", SETOR_QUALIFICACAO,
            f"O registro n. {r['numero']} ({r['serie']}) está {r['n']} vezes na base",
            f"Fichas /rcpj-rtd/{r['primeiro']} e "
            f"/rcpj-rtd/{r['ultimo']}. Veio assim do acervo do "
            f"sistema antigo; qual fica é decisão do oficial, à vista do livro."))
    return saida


def regra_corrigido(con, hoje: date) -> list[dict]:
    """O que o agente corrigiu sozinho nos últimos sete dias — para o oficial
    revisar (a ordem de 06/10/2026: «eu fiscalizo e reviso depois»)."""
    if not _tem_tabela(con, "audit_logs"):
        return []
    desde = date.fromordinal(hoje.toordinal() - 7).isoformat()
    saida = []
    for r in banco(con).ler(
            """SELECT id, ts, action, details FROM audit_logs
                WHERE action ILIKE 'GESTOR_RTDPJ_%%' AND ts >= %s ORDER BY id""",
            (desde,)):
        try:
            d = json.loads(r["details"] or "{}")
        except ValueError:
            d = {}
        saida.append(_achado(
            f"RTDPJ_CORRIGIDO:{r['id']}", CORRIGIDO, "ATENCAO", SETOR_GESTAO,
            d.get("resumo") or r["action"],
            f"Em {_br(r['ts'])}. Antes: {d.get('antes')}. Depois: "
            f"{d.get('depois')}."))
    return saida


#: A ordem é a de aperto, como em `gestor_conferencia.REGRAS`.
REGRAS: tuple[tuple[str, Callable], ...] = (
    (CERTIDAO_SEM_SELO, regra_certidao_sem_selo),
    (TITULO_ATENDIDO, regra_titulo_atendido),
    (TITULO_PARADO, regra_titulo_parado),
    (SELO_DA_ETIQUETA, regra_selo_da_etiqueta),
    (CENTRAL_PENDENTE, regra_central),
    (ENCERRAMENTO_DIARIO, regra_encerramento_diario),
    (LIVRO, regra_livro),
    (SEM_PAGAMENTO, regra_sem_pagamento),
    (REGISTRO_REPETIDO, regra_registro_repetido),
    (CORRIGIDO, regra_corrigido),
)


def conferir(con, hoje: date, *,
             central: Callable | None = None) -> list[dict]:
    """Roda as regras do RTD/PJ. Só lê (e a Central, por GET).

    Regra que quebra vira `NAO_MEDIU` com o erro à vista — nunca lista vazia.
    `central` existe para o teste não falar com a rede.
    """
    if not _tem_tabela(con, "rg_registros"):
        return []
    achados: list[dict] = []
    for nome, regra in REGRAS:
        try:
            if regra is regra_central:
                achados.extend(regra(con, hoje, central))
            else:
                achados.extend(regra(con, hoje))
        except Exception as erro:                   # noqa: BLE001 — vai à fila
            achados.append(_achado(
                f"NAO_MEDIU:{nome}", nome, "NAO_MEDIU", "TI",
                f"A conferência «{nome}» não conseguiu medir",
                f"{type(erro).__name__}: {erro}"))
    return achados


# ------------------------------------------------- o que o agente conserta

def _auditar(con, acao: str, entidade: str, entidade_id, resumo: str,
             antes, depois, agora: str) -> None:
    # O agente diz quem é e a mando de quem age (ordem do oficial, 26/10/2026).
    IDR.registrar(con, ts=agora, user_id=None, username=QUEM, action=acao,
                  entity_type=entidade, entity_id=entidade_id,
                  details=json.dumps({"resumo": resumo, "antes": antes, "depois": depois},
                                     ensure_ascii=False, default=str),
                  agente="agente do RTD/PJ (gestor)", a_mando_de=IDR.PELO_RESPONSAVEL)


def corrigir(con, hoje: date | None = None, *,
             agora: str | None = None, escrever: Callable = print) -> dict:
    """As duas correções mecânicas. ESCREVE — na transação de quem chama.

    1. **O título atendido se conclui** quando todos os atos que gastaram o
       protocolo dele são do mesmo registro, e só pela função da casa
       (`rg_titulo.concluir_pelo_ato`), que confere tudo de novo. Na versão
       instalada que ainda não a tem, o título fica e a regra o mostra.
    2. **A coluna do selo recebe o selo do próprio ato**, pela régua da casa
       (`rg_registro.papel_dos_selos`); só muda quando o certo é outro selo
       do MESMO ato no razão.

    Cada mudança deixa uma linha na auditoria com o antes e o depois, e a
    regra `RTDPJ_CORRIGIDO` a põe no relatório para o oficial revisar.
    """
    agora = agora or datetime.now().isoformat(timespec="seconds")
    feito = {"titulos": 0, "selos": 0, "pulados": []}
    if not _tem_tabela(con, "rg_registros"):
        return feito

    try:
        import rg_titulo as TIT
        concluir = getattr(TIT, "concluir_pelo_ato", None)
    except ImportError:
        concluir = None
    for t in atendidos(con):
        registros = {int(a["registro_id"]) for a in t["atos"]}
        if concluir is None or len(registros) != 1:
            feito["pulados"].append(
                f"título {t['titulo_id']}: "
                + ("a versão instalada não tem a saída" if concluir is None
                   else "atos em registros diferentes — decide quem qualifica"))
            continue
        antes = banco(con).um(
            "SELECT situacao, registro_id, observacao FROM rg_titulos WHERE id=%s",
            (t["titulo_id"],))
        r = concluir(con, t["titulo_id"], ato_id=int(t["atos"][0]["ato_id"]),
                     agora=agora, usuario="o agente do RTD/PJ")
        _auditar(con, "GESTOR_RTDPJ_TITULO_CONCLUIDO", "rg_titulos",
                 t["titulo_id"],
                 f"Título n. {t['numero']} concluído pelo ato já lavrado",
                 dict(antes), {"situacao": "REGISTRADO",
                               "registro_id": r["registro_id"],
                               "nota": r["nota"]}, agora)
        feito["titulos"] += 1
        escrever(f"  RTD/PJ: título n. {t['numero']} concluído — {r['nota']}")

    for a in selos_trocados(con):
        banco(con).escrever("UPDATE rg_atos SET selo=%s WHERE id=%s",
                            (a["certo"], a["id"]))
        _auditar(con, "GESTOR_RTDPJ_SELO_PRINCIPAL", "rg_atos", a["id"],
                 f"{'AV' if a['tipo'] == 'AVERBACAO' else a['tipo'].title()} n. "
                 f"{a['numero_ordem'] or '?'} do registro n. "
                 f"{a['registro_numero']}: selo do ato no lugar do da prenotação",
                 {"selo": a["selo"], "item": a["codigo_atual"]},
                 {"selo": a["certo"]}, agora)
        feito["selos"] += 1
        escrever(f"  RTD/PJ: ato {a['id']}: selo {a['selo']} → {a['certo']}")
    return feito
