"""Fecho da versao final do ato do RI: emolumentos + espaco do selo.

Pedido do oficial (15/09/2026): a versao final a ser lavrada inclui no fim
os emolumentos calculados e espaco para o selo; a tabela de itens acompanha
o protocolo (quando houver); sem protocolo, escolhe-se pelo texto completo
do item; a relacao de emolumentos pode constar no carimbo do selo.

O PADRAO E O DO RCPJ/RTD
    Em atribuicoes_web + _cobrar.html, o protocolo do caixa diz quais
    itens da tabela de emolumentos saem com selo; sem protocolo, a escolha
    e pela descricao completa do item. Em rg_certidao_pdf / rg_teor_rtdpj,
    o papel reserva quadro de emolumentos e faixa do selo; o carimbo imprime
    a linha de valores via selo_no_papel.linha_de_valores.

    Este modulo traz a mesma regra para o RI, sem inventar matricula e sem
    auto-lavrar: so monta o texto do fecho e calcula a conta, para a tela
    de lavrar (humana) incorporar.

UNIFICACAO PRENOTACAO + CAIXA (15/09/2026)
    A prenotacao (ri_protocolos) fixa prioridade; o protocolo de caixa
    (cx_protocolos) carrega os itens a selar. A ponte do esquema e
    cx_protocolos.ri_protocolo_id. Enquanto ela nao estiver preenchida,
    a tela usa o que a casa ja tem: deposito previo em
    cx_depositos.ri_protocolo_id. Nao se inventa join por numero.

NAO FAZ
    Nao grava ato, nao pede selo, nao manda WhatsApp, nao inventa numero de
    protocolo nem de matricula.
"""
from __future__ import annotations

import re
import sqlite3
from typing import Any

import ato_selado as AS
import emolumentos as EMO
import selo_no_papel as SNP


# Marcadores estaveis: a previa e os testes os reconhecem; regravar o teor
# com o mesmo fecho nao duplica (ver sem_fecho_antigo).
MARCA_EMOLUMENTOS = "--- Emolumentos (calculados) ---"
MARCA_SELO = "--- Espaco reservado para o selo digital do TJMA ---"


def sem_fecho_antigo(teor: str | None) -> str:
    """Tira um fecho anterior deste modulo, se houver. So calcula.

    Quem revisa a minuta pode mudar o item da tabela; o fecho antigo nao
    pode ficar colado no teor, senao a ficha levaria dois quadros.
    """
    texto = str(teor or "")
    for marca in (MARCA_EMOLUMENTOS, MARCA_SELO):
        idx = texto.find(marca)
        if idx >= 0:
            texto = texto[:idx].rstrip()
    return texto


def _moeda(v: Any) -> str:
    return SNP.moeda(v)


def linha_da_relacao(item: dict) -> str:
    """Uma linha da relacao: codigo, descricao curta e valores."""
    codigo = str(item.get("codigo_tj") or "").strip() or "—"
    desc = str(item.get("descricao") or "").strip()
    if len(desc) > 70:
        desc = desc[:67] + "..."
    partes = [codigo]
    if desc:
        partes.append(desc)
    valores = []
    if item.get("emolumentos") not in (None, ""):
        valores.append(f"Emol R$ {_moeda(item.get('emolumentos'))}")
    for sigla, chave in (("FERC", "ferc"), ("FADEP", "fadep"),
                         ("FEMP", "femp"), ("FERRFIS", "ferrfis")):
        if item.get(chave) not in (None, "", 0, "0", "0,00"):
            valores.append(f"{sigla} R$ {_moeda(item.get(chave))}")
    if item.get("total") not in (None, ""):
        valores.append(f"Total R$ {_moeda(item.get('total'))}")
    corpo = " — ".join(partes)
    if valores:
        return f"{corpo}: {' '.join(valores)}"
    return corpo


def relacao_de_emolumentos(itens: list[dict] | None) -> str:
    """O bloco de texto da relacao, pronto para ir no fim do teor."""
    lista = [i for i in (itens or []) if i]
    if not lista:
        return ""
    linhas = [MARCA_EMOLUMENTOS]
    for i in lista:
        linhas.append(linha_da_relacao(i))
    # Totais somados, no mesmo jeito da linha do carimbo (selo_no_papel).
    try:
        soma = EMO.somar_itens(lista)
    except Exception:  # noqa: BLE001 — falta de campo nao pode derrubar lavrar
        soma = {}
    if soma:
        partes = []
        if soma.get("total") not in (None, ""):
            partes.append(f"Total R$ {_moeda(soma.get('total'))}")
        if soma.get("emolumentos") not in (None, ""):
            partes.append(f"Emol R$ {_moeda(soma.get('emolumentos'))}")
        for sigla, chave in (("FERC", "ferc"), ("FADEP", "fadep"),
                             ("FEMP", "femp"), ("FERRFIS", "ferrfis")):
            if soma.get(chave) not in (None, "", 0, "0", "0,00"):
                partes.append(f"{sigla} R$ {_moeda(soma.get(chave))}")
        if partes:
            linhas.append("Soma: " + " ".join(partes))
    return "\n".join(linhas)


def espaco_do_selo() -> str:
    """Reserva tipografica para o carimbo — espelha a faixa do RCPJ.

    O carimbo de verdade (numero, QR e relacao de emolumentos via
    selo_no_papel.linha_de_valores) entra depois, quando o aparelho
    responde; aqui so se reserva o lugar, sem inventar numero.
    """
    return (
        f"{MARCA_SELO}\n"
        "[ selo / verificacao ]                    [ QR / autenticacao ]\n"
        "(a relacao de emolumentos pode constar no carimbo do selo)"
    )


def versao_final_para_lavrar(
    teor: str | None,
    itens: list[dict] | None = None,
    *,
    com_emolumentos: bool = True,
    com_espaco_selo: bool = True,
) -> str:
    """Teor + fecho de emolumentos + espaco do selo. So calcula.

    E a versao final que o oficial pediu para lavrar: o texto do ato, e no
    fim a conta e o lugar do carimbo. Nao grava nada.
    """
    base = sem_fecho_antigo(teor).rstrip()
    pedacos = [base] if base else []
    if com_emolumentos:
        rel = relacao_de_emolumentos(itens)
        if rel:
            pedacos.append(rel)
    if com_espaco_selo:
        pedacos.append(espaco_do_selo())
    return "\n\n".join(pedacos).strip() + ("\n" if pedacos else "")


def valores_para_o_carimbo(selo_texto: str | None) -> str:
    """A relacao que o carimbo imprime — mesma regua do RCPJ. So calcula.

    Devolve vazio quando o selo nada declara (selo a mao incompleto, previa
    sem selo). Quem desenha o carimbo decide se esconde a linha.
    """
    return SNP.linha_de_valores(selo_texto)


def servico_do_codigo_tj(con: sqlite3.Connection, codigo_tj: str) -> dict | None:
    """O servico da tabela vigente com aquele codigo TJ. So le."""
    codigo = str(codigo_tj or "").strip()
    if not codigo:
        return None
    r = con.execute(
        """SELECT s.codigo, s.codigo_tj, s.descricao, v.emolumentos, v.ferc,
                  v.femp, v.fadep, v.ferrfis, v.total
             FROM cx_servicos s
             LEFT JOIN cx_servico_valores v
                    ON v.servico = s.codigo
                   AND v.vigencia = (SELECT codigo FROM cx_vigencias
                                      WHERE vigente=1 LIMIT 1)
            WHERE s.codigo_tj=? AND COALESCE(s.ativo,1)=1
            ORDER BY s.codigo LIMIT 1""",
        (codigo,),
    ).fetchone()
    if not r:
        return None
    return dict(zip(
        ("servico", "codigo_tj", "descricao", "emolumentos", "ferc",
         "femp", "fadep", "ferrfis", "total"), r))


def calcular_itens(
    con: sqlite3.Connection,
    codigos_tj: list[str] | None = None,
    *,
    base_calculo: Any = None,
    quantidade: int = 1,
) -> list[dict]:
    """Calcula cada item escolhido, pela tabela vigente. So le/calcula.

    Item que a tabela nao tem volta so com codigo e descricao (se houver),
    sem inventar valor — melhor faltar a conta do que afirmar zero sobre
    ato oneroso.
    """
    saida: list[dict] = []
    for codigo in codigos_tj or []:
        codigo = str(codigo or "").strip()
        if not codigo:
            continue
        serv = servico_do_codigo_tj(con, codigo)
        if not serv or serv.get("servico") is None:
            saida.append({
                "codigo_tj": codigo,
                "descricao": (serv or {}).get("descricao") or "",
                "emolumentos": None, "ferc": None, "femp": None,
                "fadep": None, "ferrfis": None, "total": None,
                "motivo": "nao esta na tabela de emolumentos importada",
            })
            continue
        try:
            item = EMO.calcular_item(
                con, servico=int(serv["servico"]),
                quantidade=max(1, int(quantidade or 1)))
        except Exception:  # noqa: BLE001
            item = None
        if not item:
            saida.append({
                "codigo_tj": codigo,
                "descricao": serv.get("descricao") or "",
                "emolumentos": serv.get("emolumentos"),
                "ferc": serv.get("ferc"), "femp": serv.get("femp"),
                "fadep": serv.get("fadep"), "ferrfis": serv.get("ferrfis"),
                "total": serv.get("total"),
            })
            continue
        saida.append(item)
    return saida


def itens_com_texto_completo(
    con: sqlite3.Connection | None = None,
) -> list[dict]:
    """Os itens medidos do RI, com descricao completa da tabela. So le.

    Sem protocolo, o balcao escolhe por este catalogo — pedido do oficial:
    «quando nao houver protocolo, permitir escolher com texto completo».
    A ordem continua sendo a de uso nesta casa (itens_medidos_do_ato_do_ri).
    """
    medidos = AS.itens_medidos_do_ato_do_ri()
    if con is None:
        return [{"codigo_tj": c, "usos": u, "descricao": ""} for c, u in medidos]
    saida = []
    for codigo, usos in medidos:
        serv = servico_do_codigo_tj(con, codigo)
        saida.append({
            "codigo_tj": codigo,
            "usos": usos,
            "descricao": (serv or {}).get("descricao") or "",
            "emolumentos": (serv or {}).get("emolumentos"),
            "total": (serv or {}).get("total"),
            "servico": (serv or {}).get("servico"),
        })
    return saida


def protocolos_do_caixa_abertos(
    con: sqlite3.Connection, atribuicao: str | None = None,
) -> list[dict]:
    """Protocolos de caixa em andamento (ABERTO e A_PAGAR). So le.

    A_PAGAR tambem: custas lancadas ainda nao pagas. Filtrar so
    ABERTO escondia a OP na lavratura (ex.: 2026.09.23 na 3110).

    `atribuicao` recorta a lista quando a tela e de uma atribuicao so —
    relato #76, 17/09/2026: a certidao do RI nao tem o que fazer com um
    protocolo de firma. **Medido na producao em 17/09/2026**: dos **4.628**
    protocolos de caixa em andamento, **925 sao do RI** e **2.785 sao de
    firma**, mais 734 do RCPN, 98 das notas, 70 do protesto, 12 do RTD, 3 de
    outros e 1 do RCPJ — sem o recorte, a janela da tela seria mais da metade
    de reconhecimento de firma. Com ele, os 80 mais recentes do RI cobrem
    **01/07/2025 a 17/09/2026** (64 `A_PAGAR` e 16 `ABERTO`), e os 80 tem
    `interessado` preenchido — a lista sempre diz de quem e o pedido.

    **A JANELA E PARCIAL, E ISSO E DELIBERADO**: ela leva 80 dos **925** do RI
    em andamento, e a cauda (de 16/06/2025 para tras) fica de fora. O que a
    tela resolve e o pedido do dia; protocolo antigo se digita, e o campo
    continua livre por isso. Aumentar o limite nao apaga a pendencia da cauda
    — so empurra a fronteira.

    O recorte e parametro, e nao uma segunda funcao: duas consultas
    parecidas divergiriam no primeiro conserto, e a lista de uma delas
    vira dinheiro e a da outra, documento assinado.

    Inclui `ri_protocolo_id` e o numero da prenotacao ligada, quando a
    coluna e a tabela `ri_protocolos` existirem. Nao inventa ligacao.
    """
    cols = {r[1] for r in con.execute("PRAGMA table_info(cx_protocolos)")}
    tem_fk = "ri_protocolo_id" in cols
    tem_ri = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ri_protocolos'"
    ).fetchone()
    # `? IS NULL OR` mantem o recorte opcional sem montar o WHERE em pedacos
    # — `atribuicao` e coluna so de `cx_protocolos` (medido: `ri_protocolos`
    # nao tem uma), e por isso o `c.` basta nas tres consultas.
    filtro = " AND (? IS NULL OR c.atribuicao = ?)"
    recorte = (atribuicao, atribuicao)
    if tem_fk and tem_ri:
        return [dict(x) for x in con.execute(
            f"""SELECT c.id, c.numero, c.interessado, c.ri_protocolo_id,
                       r.numero AS prenotacao_numero
                  FROM cx_protocolos c
                  LEFT JOIN ri_protocolos r ON r.id = c.ri_protocolo_id
                 WHERE c.situacao IN ('ABERTO', 'A_PAGAR'){filtro}
                 ORDER BY c.id DESC LIMIT 80""", recorte)]
    if tem_fk:
        return [dict(x) for x in con.execute(
            f"""SELECT c.id, c.numero, c.interessado, c.ri_protocolo_id,
                       NULL AS prenotacao_numero
                  FROM cx_protocolos c
                 WHERE c.situacao IN ('ABERTO', 'A_PAGAR'){filtro}
                 ORDER BY c.id DESC LIMIT 80""", recorte)]
    return [dict(x) for x in con.execute(
        f"""SELECT c.id, c.numero, c.interessado,
                   NULL AS ri_protocolo_id, NULL AS prenotacao_numero
              FROM cx_protocolos c
             WHERE c.situacao IN ('ABERTO', 'A_PAGAR'){filtro}
             ORDER BY c.id DESC LIMIT 80""", recorte)]


def caixa_ligado_a_prenotacao(
    con: sqlite3.Connection, ri_protocolo_id: int | str | None,
) -> dict | None:
    """O protocolo de caixa aberto com 
i_protocolo_id = prenotacao. So le.

    A coluna existe no esquema (caixa_schema); em producao pode estar
    vazia — neste caso devolve None. Nao adivinha por numero nem por
    interessado.
    """
    if ri_protocolo_id is None or not str(ri_protocolo_id).strip().isdigit():
        return None
    r = con.execute(
        """SELECT c.id, c.numero, c.interessado, c.ri_protocolo_id,
                  r.numero AS prenotacao_numero
             FROM cx_protocolos c
             LEFT JOIN ri_protocolos r ON r.id = c.ri_protocolo_id
            WHERE c.ri_protocolo_id=? AND c.situacao IN ('ABERTO', 'A_PAGAR')
            ORDER BY c.id DESC LIMIT 1""",
        (int(ri_protocolo_id),),
    ).fetchone()
    return dict(r) if r else None


def depositos_da_prenotacao(
    con: sqlite3.Connection, ri_protocolo_id: int | str | None,
) -> list[dict]:
    """Depositos previos ligados ao titulo (ponte da casa). So le.

    E a ponte que esta casa ja usa quando o apresentante deixa
    adiantamento na tela da prenotacao (cx_depositos.ri_protocolo_id).
    Nao cria protocolo de caixa; so informa o balcao.
    """
    if ri_protocolo_id is None or not str(ri_protocolo_id).strip().isdigit():
        return []
    return [dict(x) for x in con.execute(
        """SELECT id, numero, data, depositante, valor, saldo, protocolo_id,
                  encerrado, observacao
             FROM cx_depositos
            WHERE ri_protocolo_id=?
            ORDER BY data, id""",
        (int(ri_protocolo_id),))]


def resolver_protocolo_caixa(
    con: sqlite3.Connection,
    *,
    protocolo_caixa_id: int | str | None = None,
    ri_protocolo_id: int | str | None = None,
) -> dict:
    """Une prenotacao e caixa sem inventar join.

    Ordem:
      1. protocolo de caixa escolhido a mao (override do balcao);
      2. protocolo de caixa com 
i_protocolo_id = prenotacao (FK);
      3. nenhum — itens pelo catalogo de texto completo.

    Sempre devolve tambem os depositos do titulo, que sao a ponte
    operacional desta casa enquanto a FK do caixa nao for preenchida.
    """
    depositos = depositos_da_prenotacao(con, ri_protocolo_id)
    escolhido = None
    if protocolo_caixa_id is not None and str(protocolo_caixa_id).strip().isdigit():
        r = con.execute(
            """SELECT c.id, c.numero, c.interessado, c.ri_protocolo_id,
                      r.numero AS prenotacao_numero
                 FROM cx_protocolos c
                 LEFT JOIN ri_protocolos r ON r.id = c.ri_protocolo_id
                WHERE c.id=?""",
            (int(protocolo_caixa_id),),
        ).fetchone()
        if r:
            escolhido = dict(r)
            return {
                "protocolo_caixa_id": escolhido["id"],
                "origem": "escolhido",
                "caixa": escolhido,
                "depositos": depositos,
            }
    ligado = caixa_ligado_a_prenotacao(con, ri_protocolo_id)
    if ligado:
        return {
            "protocolo_caixa_id": ligado["id"],
            "origem": "ligado",
            "caixa": ligado,
            "depositos": depositos,
        }
    return {
        "protocolo_caixa_id": None,
        "origem": "nenhum",
        "caixa": None,
        "depositos": depositos,
    }


def itens_do_protocolo_disponiveis(
    con: sqlite3.Connection, protocolo_id: int | str | None,
) -> list[dict]:
    """Itens ainda nao usados do protocolo de caixa. So le.

    Espelha atribuicoes_web (RCPJ): um protocolo serve varios atos; o que
    nao for marcado fica para o proximo.
    """
    # O ITEM TEM QUANTIDADE, E ELA SE GASTA POR UNIDADE — relato do oficial em
    # 15/09/2026: um item «De ato sem valor declarado × 5» sumia da tela depois
    # da PRIMEIRA averbacao, porque a condicao era `usado_em IS NULL`.
    #
    #   A regra mora em `caixa_protocolo.itens_disponiveis`, que serve o RI e o
    #   RCPJ/RTD: duas copias divergiriam no primeiro conserto.
    import caixa_protocolo as CXPROT
    return CXPROT.itens_disponiveis(con, protocolo_id)


def frase_emolumentos_curta(itens: list[dict] | None) -> str | None:
    """Uma linha para gravar em 
i_atos.emolumentos (campo curto)."""
    lista = [i for i in (itens or []) if i and i.get("total") not in (None, "")]
    if not lista:
        return None
    try:
        soma = EMO.somar_itens(lista)
    except Exception:  # noqa: BLE001
        return None
    if not soma or soma.get("total") in (None, ""):
        return None
    partes = [f"Total R$ {_moeda(soma.get('total'))}"]
    if soma.get("emolumentos") not in (None, ""):
        partes.append(f"Emol R$ {_moeda(soma.get('emolumentos'))}")
    return " ".join(partes)
