# -*- coding: utf-8 -*-
"""O MONITORAMENTO DO DEVEDOR — os títulos de uma pessoa, juntos, com o que
vence hoje e o que está parado.

O QUE ELE RESPONDE (LG06, 19/10/2026): para um CPF ou CNPJ, quais títulos há
na casa, em que pé está cada um — prazo-limite, intimações, avisos, AR,
boletos, pagamentos — e o que pede atenção agora:

    VENCE_HOJE ........ o prazo-limite é hoje: último dia para pagar (CN-MA
                        art. 925, § 4º — «o dia previsto para a lavratura»);
    PRAZO_VENCIDO ..... passou o prazo-limite e o título continua apontado ou
                        intimado: o protesto é devido, ou falta lançar o que
                        aconteceu (Lei 9.492/1997, art. 12);
    AR_NAO_VOLTOU ..... o AR digital chegou ao prazo-limite sem voltar: a
                        intimação vai por pessoa da casa (CN-MA art. 921, § 2º);
    EDITAL_NECESSARIO . o aviso não foi entregue, a Intimação Digital não serve
                        ou não deu, e o título continua sem intimação (CN-MA
                        art. 922);
    PAGAMENTO_A_CONFERIR o banco pagou o boleto e a baixa não saiu sozinha.

**ELE CONTA E APONTA; NÃO JULGA.** A regra do oficial de 24/08/2026 — «só
registrar, sem contar prazo» nas funções que LAVRAM — continua de pé: nada
aqui lavra, protesta ou publica. É a mesma posição do `gestor_protesto`, e o
prazo é o MESMO número que vai impresso no aviso (`protesto_aviso.
prazo_limite`), para o painel e o papel não discordarem.

**JUNTA-SE POR DOCUMENTO, E SÓ POR ELE.** Dois devedores com o mesmo nome não
são a mesma pessoa — homônimo é a regra, e não a exceção, num cadastro de
protesto. O devedor sem CPF/CNPJ aparece sozinho, com o título dele, e a lista
diz quantos estão assim.

**O CPF NÃO VAI NO ENDEREÇO DA TELA.** A busca é um formulário (POST), e a
ficha se abre pelo número interno do devedor: endereço de página fica no
histórico do navegador e no log do servidor, e CPF é dado pessoal (LGPD). Cada
consulta fica em `audit_logs`.
"""
from __future__ import annotations

import json
from datetime import date
from typing import Any

import protesto as PT
import protesto_ar as AR
import protesto_aviso as AV
import protesto_boleto as BOL
import protesto_integracoes as INTEG
from bd_nativo import banco
from protesto_cenprot import so_digitos
from protesto_certidao import formatar_documento

SITUACOES_EM_ANDAMENTO: tuple[str, ...] = ("RECEBIDO", "APONTADO", "INTIMADO")

# A ORDEM É A DA URGÊNCIA, e é ela que ordena a lista: o que vence hoje vem
# antes do que já venceu, porque hoje ainda dá para fazer alguma coisa.
ALERTAS: dict[str, dict[str, str]] = {
    "VENCE_HOJE": {
        "rotulo": "Vence hoje",
        "frase": "O prazo-limite para pagamento é hoje; amanhã o protesto "
                 "pode ser lavrado.",
        "base": "CN-MA art. 925, § 4º"},
    "AR_NAO_VOLTOU": {
        "rotulo": "AR não voltou",
        "frase": "O AR digital chegou ao prazo-limite sem voltar: a intimação "
                 "vai por pessoa da casa.",
        "base": "CN-MA art. 921, § 2º"},
    "EDITAL_NECESSARIO": {
        "rotulo": "Edital necessário",
        "frase": "O aviso não foi entregue e a Intimação Digital não serve ou "
                 "não deu: o caminho é o edital.",
        "base": "CN-MA art. 922"},
    "PAGAMENTO_A_CONFERIR": {
        "rotulo": "Pagamento a conferir",
        "frase": "O banco pagou o boleto e a baixa não saiu sozinha — veja a "
                 "pendência na tela dos boletos.",
        "base": "CN-MA art. 925"},
    "PRAZO_VENCIDO": {
        "rotulo": "Prazo vencido",
        "frase": "O prazo-limite passou e o título continua sem protesto, "
                 "pagamento nem desistência.",
        "base": "Lei 9.492/1997, art. 12"},
}
ORDEM_DOS_ALERTAS = {codigo: i for i, codigo in enumerate(ALERTAS)}

# O DOCUMENTO SÓ COM DÍGITOS, no SQL: o cadastro da CRA o traz cru, e o do
# balcão pode vir pontuado — juntar pelo texto separaria a mesma pessoa.
_DOC = "regexp_replace(coalesce(d.documento_numero, ''), '[^0-9]', '', 'g')"


def _alerta(codigo: str, detalhe: str = "") -> dict:
    return {"codigo": codigo, **ALERTAS[codigo], "detalhe": detalhe}


def alertas_do_titulo(titulo: dict, *, hoje: str, prazo: str | None,
                      sustado: bool, postagens_sem_retorno: list[dict],
                      avisos_para_edital: list[dict],
                      boletos_a_conferir: list[dict]) -> list[dict]:
    """Os alertas de UM título, já com tudo medido. Só calcula.

    O título sustado não vence: está à disposição do juízo (Lei 9.492/1997,
    art. 17), e «vence hoje» sobre ele mandaria o balcão cobrar quem o juiz
    mandou parar.
    """
    fora: list[dict] = []
    situacao = str(titulo.get("situacao") or "")
    em_prazo = situacao in ("APONTADO", "INTIMADO") and not sustado
    if em_prazo and prazo:
        if prazo == hoje:
            fora.append(_alerta("VENCE_HOJE", f"prazo-limite {_br(prazo)}"))
        elif prazo < hoje:
            fora.append(_alerta("PRAZO_VENCIDO", f"prazo-limite {_br(prazo)}"))
    if em_prazo:
        for p in postagens_sem_retorno:
            fora.append(_alerta(
                "AR_NAO_VOLTOU",
                f"objeto {p.get('codigo_objeto') or '?'}, prazo-limite "
                f"{_br(p.get('prazo_limite'))}"))
    if situacao == "APONTADO" and not sustado:
        for a in avisos_para_edital:
            fora.append(_alerta(
                "EDITAL_NECESSARIO",
                f"aviso {a['numero']}/{a['ano']}: {a.get('frase') or ''}".strip()))
    for b in boletos_a_conferir:
        fora.append(_alerta(
            "PAGAMENTO_A_CONFERIR",
            f"boleto {b.get('nosso_numero') or b.get('identificador')}: "
            f"{b.get('observacao') or ''}".strip()))
    return sorted(fora, key=lambda x: ORDEM_DOS_ALERTAS[x["codigo"]])


def _br(iso: Any) -> str:
    s = str(iso or "")[:10]
    return f"{s[8:10]}/{s[5:7]}/{s[:4]}" if len(s) == 10 and s[4] == "-" else s


def _medir_alertas(bd: Any, titulos: list[dict], *, hoje: str) -> dict[int, list]:
    """Os alertas de vários títulos, com as leituras em lote. SÓ LÊ."""
    ids = sorted({int(t["id"]) for t in titulos})
    if not ids:
        return {}
    sem_retorno: dict[int, list] = {}
    for p in AR.sem_retorno(bd, hoje=hoje, limite=10_000):
        sem_retorno.setdefault(int(p["titulo_id"]), []).append(p)
    para_edital: dict[int, list] = {}
    for a in bd.ler(
            """SELECT a.* FROM pt_avisos a
                WHERE a.situacao = 'NAO_ENTREGUE' AND a.titulo_id = ANY(%s)
                ORDER BY a.titulo_id, a.id""", (ids,)):
        caminho = AV.depois_da_nao_entrega(bd, a)
        if caminho["passo"] == "EDITAL":
            para_edital.setdefault(int(a["titulo_id"]), []).append(
                {**dict(a), "frase": caminho["frase"]})
    a_conferir: dict[int, list] = {}
    for b in bd.ler(
            """SELECT * FROM pt_boletos
                WHERE ambiente = %s AND situacao = 'CONFERIR'
                  AND titulo_id = ANY(%s) ORDER BY titulo_id, id""",
            (INTEG.PRODUCAO, ids)):
        a_conferir.setdefault(int(b["titulo_id"]), []).append(dict(b))
    fora = {}
    for t in titulos:
        tid = int(t["id"])
        fora[tid] = alertas_do_titulo(
            t, hoje=hoje, prazo=t.get("prazo_limite"),
            sustado=bool(t.get("sustado")),
            postagens_sem_retorno=sem_retorno.get(tid, []),
            avisos_para_edital=para_edital.get(tid, []),
            boletos_a_conferir=a_conferir.get(tid, []))
    return fora


def _com_prazo(bd: Any, titulo: dict) -> dict:
    t = dict(titulo)
    t["prazo_limite"] = AV.prazo_limite(bd, t)
    t["sustado"] = bool(PT.sustacao_em_vigor(bd, int(t["id"])))
    return t


# ----------------------------------------------------------- a lista


def devedores_em_andamento(con: Any, *, hoje: str, limite: int = 300) -> dict:
    """Os devedores com título em andamento, por CPF/CNPJ, os com alerta
    primeiro. SÓ LÊ.

    Um título com dois devedores (solidários) aparece nos dois: a intimação
    de qualquer um autoriza o protesto (CN-MA art. 919, § 5º), e cada um deve
    ver o título no seu painel.
    """
    bd = banco(con)
    linhas = bd.ler(
        f"""SELECT t.*, d.id AS devedor_id, d.nome AS devedor_nome,
                   {_DOC} AS documento
              FROM pt_titulos t JOIN pt_devedores d ON d.titulo_id = t.id
             WHERE t.situacao IN ('RECEBIDO', 'APONTADO', 'INTIMADO')
             ORDER BY documento, t.id, d.id""")
    sem_documento = sorted({int(x["id"]) for x in linhas if not x["documento"]})
    com_doc = [x for x in linhas if x["documento"]]
    titulos = {int(x["id"]): _com_prazo(bd, x) for x in com_doc}
    alertas = _medir_alertas(bd, list(titulos.values()), hoje=hoje)
    grupos: dict[str, dict] = {}
    for x in com_doc:
        doc = x["documento"]
        g = grupos.setdefault(doc, {
            "devedor_id": int(x["devedor_id"]), "documento": doc,
            "documento_formatado": formatar_documento(doc),
            "nome": x["devedor_nome"], "titulos": set(), "valor_centavos": 0,
            "alertas": []})
        tid = int(x["id"])
        if tid in g["titulos"]:
            continue
        g["titulos"].add(tid)
        g["devedor_id"] = min(g["devedor_id"], int(x["devedor_id"]))
        g["valor_centavos"] += int(x["saldo_centavos"] or x["valor_centavos"] or 0)
        g["alertas"].extend(alertas.get(tid, []))
    fora = []
    for g in grupos.values():
        g["n_titulos"] = len(g.pop("titulos"))
        contagem: dict[str, int] = {}
        for a in g["alertas"]:
            contagem[a["codigo"]] = contagem.get(a["codigo"], 0) + 1
        g["contagem"] = [{"codigo": c, "rotulo": ALERTAS[c]["rotulo"], "n": n}
                         for c, n in sorted(contagem.items(),
                                            key=lambda kv: ORDEM_DOS_ALERTAS[kv[0]])]
        g["urgencia"] = min((ORDEM_DOS_ALERTAS[a["codigo"]] for a in g["alertas"]),
                            default=len(ALERTAS))
        del g["alertas"]
        fora.append(g)
    fora.sort(key=lambda g: (g["urgencia"], str(g["nome"] or ""), g["documento"]))
    return {"devedores": fora[:int(limite)], "total": len(fora),
            "titulos_sem_documento": len(sem_documento),
            "titulos_sem_documento_ids": sem_documento[:50]}


def achar(con: Any, documento: Any) -> int | None:
    """O devedor daquele CPF/CNPJ (o número interno mais antigo), ou None. SÓ LÊ."""
    doc = so_digitos(documento)
    if len(doc) not in (11, 14):
        return None
    return banco(con).valor(
        f"SELECT min(d.id) AS id FROM pt_devedores d WHERE {_DOC} = %s", (doc,))


# ----------------------------------------------------------- a ficha


def _detalhe(ato: dict) -> dict:
    try:
        return json.loads(ato.get("detalhe_json") or "{}")
    except (TypeError, ValueError):
        return {}


def painel(con: Any, devedor_id: int, *, hoje: str) -> dict | None:
    """Tudo de um devedor: os títulos, os prazos, as intimações, os pagamentos
    e os alertas. SÓ LÊ. None quando o devedor não existe."""
    bd = banco(con)
    d0 = bd.um(f"""SELECT d.*, {_DOC} AS documento FROM pt_devedores d
                   WHERE d.id = %s""", (int(devedor_id),))
    if not d0:
        return None
    doc = d0["documento"]
    if doc:
        devs = bd.ler(f"""SELECT d.id, d.titulo_id, d.nome FROM pt_devedores d
                          WHERE {_DOC} = %s ORDER BY d.titulo_id, d.id""", (doc,))
    else:
        devs = [d0]
    ids = sorted({int(x["titulo_id"]) for x in devs})
    nomes = sorted({str(x["nome"] or "").strip() for x in devs} - {""})
    titulos = [_com_prazo(bd, t) for t in bd.ler(
        "SELECT * FROM pt_titulos WHERE id = ANY(%s) ORDER BY id", (ids,))]
    alertas = _medir_alertas(bd, titulos, hoje=hoje)

    for t in titulos:
        tid = int(t["id"])
        atos = PT.atos_do(bd, tid)
        t["intimacoes"] = [
            {"data": a["data_ato"], "modo": _detalhe(a).get("modo") or "",
             "digital": bool(_detalhe(a).get("digital")),
             "comprovante": _detalhe(a).get("comprovante") or ""}
            for a in atos if a["tipo"] == "INTIMACAO" and not a["cancelado"]]
        t["pagamentos"] = [
            {"data": a["data_ato"], "forma": PT.FORMAS_DE_PAGAMENTO.get(
                _detalhe(a).get("forma_pagamento") or "", ""),
             "identificacao": _detalhe(a).get("forma_identificacao") or "",
             "valor_centavos": _detalhe(a).get("valor_pago_centavos"),
             "rotulo": a["rotulo"]}
            for a in atos if a["tipo"] == "PAGAMENTO" and not a["cancelado"]]
        t["protesto"] = next((a for a in atos if a["tipo"] == "PROTESTO"
                              and not a["cancelado"]), None)
        t["avisos"] = AV.do_titulo(bd, tid)
        t["postagens"] = AR.do_titulo(bd, tid)
        t["boletos"] = BOL.boletos_do_titulo(bd, tid)
        t["alertas"] = alertas.get(tid, [])
        t["em_andamento"] = t["situacao"] in SITUACOES_EM_ANDAMENTO
        t["dias_para_o_prazo"] = (
            (date.fromisoformat(t["prazo_limite"]) - date.fromisoformat(hoje)).days
            if t["prazo_limite"] and t["em_andamento"] else None)

    titulos.sort(key=lambda t: (not t["em_andamento"],
                                str(t["prazo_limite"] or "9999") if t["em_andamento"]
                                else "", -int(t["id"])))
    andamento = [t for t in titulos if t["em_andamento"]]
    return {
        "devedor_id": int(devedor_id),
        "documento": doc,
        "documento_formatado": formatar_documento(doc) if doc else "",
        "documento_tipo": d0.get("documento_tipo") or (
            "CPF" if len(doc) == 11 else "CNPJ" if len(doc) == 14 else ""),
        "nomes": nomes or [str(d0.get("nome") or "")],
        "sem_documento": not doc,
        "titulos": titulos,
        "resumo": {
            "titulos": len(titulos),
            "em_andamento": len(andamento),
            "valor_em_aberto_centavos": sum(
                int(t["saldo_centavos"] or t["valor_centavos"] or 0)
                for t in andamento),
            "alertas": sum(len(t["alertas"]) for t in titulos),
            "protestados": sum(1 for t in titulos if t["situacao"] == "PROTESTADO"),
        },
    }
