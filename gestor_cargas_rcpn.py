"""O agente de cargas do RCPN — SIRC, CRC, FUNAI, óbitos do mês e IBGE.

    «agente de cargas rcpn: esse agente sera responsavel por fiscalizar e
     manter em dia as cargas do rcpn do cartorio» — o oficial, 09/10/2026

SÃO CINCO CARGAS, E NENHUMA SOBE SOZINHA DAQUI
    | carga             | prazo                         | onde sobe                         |
    |-------------------|-------------------------------|-----------------------------------|
    | SIRC (INSS)       | 1 dia útil (art. 225)         | SIRC-Web, o `.mrc` do lote        |
    | CRC Nacional      | 5 dias (arts. 243 e 367)      | portal da CRC, o XML da carga     |
    | FUNAI             | imediatamente (art. 253, § 2º)| ofício, depois de completar etnia |
    | óbitos do mês     | 5º dia útil (art. 226; Lei 4.375/1964) | os cinco destinos        |
    | IBGE              | dia 8 do mês seguinte ao trimestre (art. 224) | o `CARTINF.zip`   |

    **O agente PREPARA e FISCALIZA; quem sobe é a pessoa.** Medido em
    06/10/2026: a casa manda o SIRC pelo SIRC-Web, à mão, e a credencial da API
    do SIRC nunca funcionou para envio; a CRC sobe pelo portal (quatro lotes
    MANUAL em `rc_crc_lotes`); e a FUNAI, o IBGE e os óbitos não têm envio por
    programa nenhum. Mandar sozinho ao SIRC é decisão que o oficial ainda não
    tomou («enviar só com o "sim" do oficial por lote», 02/10/2026) — e o § 4º
    do art. 225 pune informação inexata com ação regressiva do INSS.

O QUE ELE FAZ TODO DIA (`rodada`, chamada pela rodada das 07:30 do gestor)
    1. **Separa o que não pode ir.** Assento duplicado e assento ativo sem
       número ficam FORA de todo arquivo. A régua é a do agente do RCPN
       (`gestor_rcpn.duplicidades` e `gestor_rcpn.inacabados`, divisão de
       terreno combinada em 09/10/2026): o achado é dele; a retenção, daqui.
       Medido nesse dia: o óbito de MOACIR SILVA PEREIRA lavrado duas vezes
       (1983 e 1984, dois minutos de diferença) e o assento 8362, sem número,
       duplicata do nascimento 19578 — o 8362 estava na fila do SIRC como
       «nº None».
    2. **Monta o arquivo de cada carga** com o montador que a tela já usa
       (`sirc_remessa.montar`, `crc_carga.montar`, `rc_funai.montar`,
       `rc_comunicacoes.montar`, `ibge_geracao.montar`) — um formato só na casa —
       e o deixa na pasta da carga, com um LEIA-ME do que subir hoje.
    3. **Abre as comunicações do mês fechado** (`rc_comunicacoes.declarar_mes`,
       o mesmo botão «abrir» da tela): sem a linha PENDENTE, a tela das
       comunicações não mostra o mês, e não há onde registrar o envio.
    4. **Confere a CRC contra o XSD**, e não só com o parser: «bem formado» não é
       «válido» (13/09/2026, a causa da morte de 375 caracteres).

O QUE ELE CONFERE (`conferir`, uma regra do gestor)
    Uma tarefa por dia para o RCPN — «Cargas do RCPN: o que subir hoje» —, com
    um achado por carga pronta, o prazo mais apertado dela e o caminho do
    arquivo; o que o montador recusou por falta de dado, assento a assento; a
    CRC que não passa no XSD; e o próprio agente parado. A tarefa fecha sozinha
    quando o envio é registrado na tela de cada carga, porque o item sai da fila
    do módulo e o arquivo de amanhã já não o traz.

O QUE ELE NÃO FAZ
    Não lavra, não sela, não cobra, não corrige assento e **não manda nada a
    Central nenhuma**. Não registra envio: «enviado» se registra com o protocolo
    que a Central devolveu, e quem o vê é quem subiu. E não sobe o acervo: o
    corte do oficial (10/09/2026) vale aqui como no gestor — o que se lavrou
    antes dele não entra nos arquivos.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sqlite3
import sys
import traceback
import unicodedata
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from gestor_schema import init_gestor_schema

QUEM = "gestor"

#: A pasta é da casa (09/10/2026), ao lado das do E-Ofício. **Não é a
#: `IBGE_EXP` dele**: lá estão os CARTINF que o E-Ofício gerou em 23/07/2026,
#: que são a prova do 2º trimestre, e o agente não escreve por cima de prova.
PASTA_PADRAO = r"C:\ARPNET\C11\CARGAS_RCPN"
CHAVE_PASTA = "rcpn_cargas_pasta"

CANAIS = ("SIRC", "CRC", "FUNAI", "OBITOS", "IBGE")

#: Os prefixos dos arquivos que o agente escreve. É por eles — e só por eles —
#: que ele limpa a pasta da carga: o que outra pessoa pôs ali não se apaga.
PREFIXO_DO_ARQUIVO = {"SIRC": "SIRC_", "CRC": "CRC_", "FUNAI": "FUNAI_",
                      "OBITOS": "OBITOS_", "IBGE": "CARTINF_"}

#: O destino da comunicação de óbito (`rc_comunicacoes`) e a Central em que o
#: gestor registra o mesmo envio (`ge_envios`). São dois vocabulários para a
#: mesma coisa, e até 09/10/2026 a regra do gestor só olhava o segundo: o que a
#: tela das comunicações registrava continuava sendo cobrado.
CENTRAL_DO_DESTINO = {"ELEITORAL": "OBITO_TRE", "ECONOMIA": "OBITO_ME",
                      "RECEITA": "OBITO_RFB", "IDENTIFICACAO": "OBITO_IIMA",
                      "JUNTA_MILITAR": "JUNTA_MILITAR"}

#: O agente rodou ontem ou hoje? Mais que isso, ninguém está cuidando.
AGENTE_DIAS_TOLERADOS = 1

ONDE_SOBE = {
    "SIRC": "SIRC-Web (Transmissão de Arquivo → Enviar Arquivo de Movimento), o "
            "arquivo .mrc. Depois, registre o envio em «Envios às Centrais» com o "
            "número que o SIRC mostrar.",
    "CRC": "portal da CRC Nacional, o XML. Depois, na tela da CRC do sistema, "
           "registre o lote como enviado.",
    "FUNAI": "por ofício — complete a etnia e a aldeia na tela «FUNAI» do sistema "
             "(o arquivo daqui sai com o lugar marcado), mande, e registre lá.",
    "OBITOS": "cada destino pelo seu meio (o eleitoral pelo INFODIP). Depois, "
              "registre cada um na tela «Comunicações de óbito» com o protocolo.",
    "IBGE": "pelo meio que o IBGE indicar, o CARTINF.zip. Depois, registre a "
            "entrega na tela do IBGE do sistema.",
}

FUNDAMENTO = {
    "SIRC": "art. 225 do Código de Normas do TJMA; art. 68 da Lei 8.212/1991",
    "CRC": "arts. 243 e 367 do Código de Normas do TJMA",
    "FUNAI": "art. 253, § 2º, do Código de Normas do TJMA",
    "OBITOS": "art. 226 do Código de Normas do TJMA; Lei 4.375/1964",
    "IBGE": "art. 224 do Código de Normas; art. 49 da Lei 6.015/1973",
}

#: Regras que são decisão do oficial: medidas e relatadas, sem tarefa.
REGRAS_DE_DECISAO = frozenset({"CARGAS_RCPN_DECISAO"})

ROTULOS = {
    "CARGAS_RCPN_PRONTA": "Cargas do RCPN — arquivo pronto para subir",
    "CARGAS_RCPN_FALTA": "Cargas do RCPN — registro que não monta por falta de dado",
    "CARGAS_RCPN_INVALIDA": "Cargas do RCPN — arquivo que não passa no esquema",
    "CARGAS_RCPN_AGENTE_PARADO": "Cargas do RCPN — o agente de cargas não rodou",
    "CARGAS_RCPN_DECISAO": "Cargas do RCPN — decisão do oficial",
}


# ---------------------------------------------------------------- miúdos

def _agora() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _tem_tabela(con, nome: str) -> bool:
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                       (nome,)).fetchone() is not None


def _settings(con) -> dict[str, str]:
    if not _tem_tabela(con, "settings"):
        return {}
    return {r[0]: (r[1] or "") for r in con.execute("SELECT key, value FROM settings")}


def pasta(con) -> Path:
    return Path((_settings(con).get(CHAVE_PASTA) or "").strip() or PASTA_PADRAO)


def _cns(s: dict) -> str:
    """O mesmo de `atribuicoes_web._cns_rcpn`: `serventia_cns`, senão `ri_cns`."""
    return (s.get("serventia_cns") or "").strip() or (s.get("ri_cns") or "").strip()


def _dia(texto) -> date | None:
    bruto = str(texto or "")[:10]
    try:
        return date.fromisoformat(bruto)
    except ValueError:
        return None


def _implantacao() -> str:
    import gestor_conferencia as GC
    return GC.IMPLANTACAO


def _depois_do_corte(texto) -> bool:
    d = _dia(texto)
    return d is not None and d.isoformat() >= _implantacao()


def _sha(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def _sem_acento(texto: str) -> str:
    t = unicodedata.normalize("NFD", str(texto or "").upper())
    return " ".join("".join(c for c in t if not unicodedata.combining(c)).split())


def _registrar(con, canal: str, *, situacao: str, detalhe: Any) -> int:
    return int(con.execute(
        """INSERT INTO ge_rcpn_cargas (canal, tipo, situacao, gerado_em, detalhe)
           VALUES (?, 'RODADA', ?, ?, ?)""",
        (canal, situacao, _agora(), json.dumps(detalhe, ensure_ascii=False, default=str))
    ).lastrowid)


# ======================================================= 1. O QUE NÃO PODE IR

def retidos(con) -> dict[int, str]:
    """Os assentos que não entram em arquivo de carga nenhum, com o motivo.

    A RÉGUA É A DO AGENTE DO RCPN, e não uma segunda: duas réguas para «este
    assento é duplicado» divergiriam no primeiro conserto, e a carga mandaria o
    que o balcão já sabe que está errado. Enquanto o módulo dele não estiver na
    árvore, vale a régua provisória daqui, declarada como tal.
    """
    try:
        import gestor_rcpn
        duplicidades, inacabados = gestor_rcpn.duplicidades, gestor_rcpn.inacabados
    except (ImportError, AttributeError):
        return _retidos_provisorio(con)
    saida: dict[int, str] = {}
    for g in duplicidades(con):
        numeros = ", ".join(str(n) for n in (g.get("numeros") or []) if n is not None)
        for aid in g.get("ids") or []:
            saida[int(aid)] = (f"{str(g.get('especie') or '').lower()} lançado mais de uma "
                               f"vez (termos {numeros or 'sem número'}) — o oficial decide "
                               "qual vale; até lá nenhum vai à Central")
    for a in inacabados(con):
        saida.setdefault(int(a["id"]), "assento ativo sem número de termo")
    return saida


def _retidos_provisorio(con) -> dict[int, str]:
    """Régua provisória: sem número, e a mesma pessoa duas vezes desde o corte.

    «A mesma pessoa» é a mesma espécie, o mesmo nome (sem acento e sem caixa) e a
    mesma data do fato. Gêmeos não caem aqui: o art. 234 manda nomes distintos.
    """
    saida: dict[int, str] = {}
    grupos: dict[tuple, list] = {}
    for r in con.execute(
            """SELECT id, especie, numero, nome, data_fato FROM rc_assentos
                WHERE COALESCE(situacao,'ATIVO') = 'ATIVO'
                  AND COALESCE(origem,'') NOT IN ('EOFICIO','ARQUIVO','IMPORTACAO')
                  AND especie IN ('NASCIMENTO','NATIMORTO','CASAMENTO',
                                  'CASAMENTO_RELIGIOSO','OBITO')
                  AND data_ato >= ?""", (_implantacao(),)):
        if r["numero"] is None:
            saida[int(r["id"])] = "assento ativo sem número de termo"
        chave = (r["especie"], _sem_acento(r["nome"]), str(r["data_fato"] or "")[:10])
        grupos.setdefault(chave, []).append(r)
    for (especie, _n, _d), linhas in grupos.items():
        if len(linhas) < 2:
            continue
        numeros = ", ".join(str(x["numero"]) for x in linhas if x["numero"] is not None)
        for x in linhas:
            saida.setdefault(int(x["id"]), (
                f"{str(especie).lower()} lançado mais de uma vez (termos "
                f"{numeros or 'sem número'}) — o oficial decide qual vale"))
    return saida


# ======================================================= 2. OS CINCO ARQUIVOS
#
# Cada `preparar_*` SÓ LÊ (fora `declarar_mes`, quando `gravar`) e devolve:
#   arquivos   [{nome, dados (bytes), quantos, referencias?}]
#   prazo      o prazo mais apertado do que está nos arquivos (date ou None)
#   faltas     [{assento_id, nome, faltas}] — o que o montador recusou
#   fora       [{assento_id, nome, motivo}] — o que ficou retido aqui
#   problemas  [texto] — o que impede ou ressalva a carga

def _vazio() -> dict:
    return {"arquivos": [], "prazo": None, "faltas": [], "fora": [], "problemas": [],
            "quantos": 0}


def preparar_sirc(con, hoje: date, *, s: dict, ret: dict[int, str]) -> dict:
    import sirc_remessa as SIRC
    from ri_schema import soma_dias_uteis
    r = _vazio()
    devendo, prazos = [], []
    for p in SIRC.sem_os_ja_enviados(con, SIRC.pendentes_de_remessa(con)):
        ref = SIRC.referencia_do_envio(p)
        ultima = ref.rsplit(":", 1)[-1] if ref.count(":") >= 2 else str(p.get("data_ato") or "")
        if not _depois_do_corte(ultima):
            continue
        aid = int(p.get("assento_id") or 0)
        if aid in ret:
            r["fora"].append({"assento_id": aid, "nome": p.get("nome"),
                              "numero": p.get("numero"), "motivo": ret[aid]})
            continue
        devendo.append(p)
        d = _dia(ultima)
        if d:
            prazos.append(soma_dias_uteis(d, 1))
    if not devendo:
        return r
    cns = _cns(s)
    montado = SIRC.montar(con, devendo, cns=cns)
    r["faltas"] = [{"assento_id": x.get("assento_id"), "nome": x.get("nome"),
                    "faltas": x.get("faltas")} for x in montado["retidos"]]
    for lote in montado["lotes"]:
        base = f"SIRC_{lote['especie']}_{lote['numero']:02d}"
        r["arquivos"].append({"nome": base + ".xml", "dados": lote["xml"].encode("utf-8"),
                              "quantos": lote["quantos"], "referencias": lote["referencias"]})
        try:
            mrc = SIRC.arquivo_mrc(lote["xml"], cns=cns)
            r["arquivos"].append({"nome": base + ".mrc", "dados": mrc,
                                  "quantos": lote["quantos"],
                                  "referencias": lote["referencias"]})
        except Exception as erro:                       # noqa: BLE001
            r["problemas"].append(f"o .mrc do lote {lote['numero']} não saiu "
                                  f"({type(erro).__name__}: {erro}); o .xml está na pasta")
        if not lote.get("cabe", True):
            r["problemas"].append(f"o lote {lote['numero']} passa do tamanho que o SIRC aceita")
        r["problemas"] += [f"lote {lote['numero']}: {a}" for a in lote.get("avisos") or []]
    r["quantos"] = montado["quantos"]
    retidos_ids = {x.get("assento_id") for x in montado["retidos"]}
    prazos_dos_que_vao = [pz for p, pz in zip(devendo, prazos)
                          if p.get("assento_id") not in retidos_ids]
    r["prazo"] = min(prazos_dos_que_vao or prazos or [None], key=lambda x: x or date.max)
    return r


def _xsd_da_crc():
    import crc_carga
    return Path(crc_carga.__file__).resolve().parent / "schemas" / "cargaRegistrosCompleto.xsd"


def validar_crc(xml: str) -> list[str] | None:
    """Os erros do XML da CRC contra o XSD. `None` quando não deu para validar
    (sem lxml ou sem o esquema) — que não é o mesmo que «sem erro»."""
    try:
        from lxml import etree
    except ImportError:
        return None
    caminho = _xsd_da_crc()
    if not caminho.exists():
        return None
    esquema = etree.XMLSchema(etree.parse(str(caminho)))
    doc = etree.fromstring(xml.encode("utf-8"))
    if esquema.validate(doc):
        return []
    return [f"linha {e.line}: {e.message}" for e in esquema.error_log][:20]


def preparar_crc(con, hoje: date, *, s: dict, ret: dict[int, str]) -> dict:
    import crc_carga
    r = _vazio()
    ids, prazos, antes = [], [], 0
    for p in crc_carga.pendentes_de_carga(con):
        if not _depois_do_corte(p.get("data_ato")):
            antes += 1
            continue
        if int(p["id"]) in ret:
            r["fora"].append({"assento_id": p["id"], "nome": p.get("nome"),
                              "numero": p.get("numero"), "motivo": ret[int(p["id"])]})
            continue
        ids.append(int(p["id"]))
        prazos.append(_dia(p["data_ato"]) + timedelta(days=5))
    r["fora_pelo_corte"] = antes
    if not ids:
        return r
    montado = crc_carga.montar(con, ids, cns=_cns(s))
    r["faltas"] = [{"assento_id": x.get("assento_id"), "nome": x.get("nome"),
                    "faltas": x.get("faltas")} for x in montado["retidos"]]
    r["quantos"] = montado["quantos"]
    if montado["quantos"]:
        erros = validar_crc(montado["xml"])
        r["xsd"] = "NAO_MEDIU" if erros is None else ("OK" if not erros else "ERRO")
        if erros:
            r["problemas"] += erros
            r["erros_xsd"] = erros
        else:
            r["arquivos"].append({"nome": f"CRC_carga_{hoje.isoformat()}.xml",
                                  "dados": montado["xml"].encode("utf-8"),
                                  "quantos": montado["quantos"],
                                  "assentos": [i for i in ids if i not in
                                               {x.get("assento_id") for x in montado["retidos"]}]})
    r["prazo"] = min(prazos)
    return r


def preparar_funai(con, hoje: date, *, s: dict, ret: dict[int, str]) -> dict:
    import rc_funai
    r = _vazio()
    for p in rc_funai.pendentes(con, hoje=hoje.isoformat()):
        if not _depois_do_corte(p.get("data_ato")):
            continue
        if int(p["id"]) in ret:
            r["fora"].append({"assento_id": p["id"], "nome": p.get("nome"),
                              "numero": p.get("numero"), "motivo": ret[int(p["id"])]})
            continue
        oficio = rc_funai.montar(con, int(p["id"]),
                                 serventia={"nome": s.get("serventia_nome", ""),
                                            "cns": _cns(s)})
        r["arquivos"].append({"nome": f"FUNAI_{p.get('numero')}_{p['id']}.txt",
                              "dados": oficio["teor"].encode("utf-8"), "quantos": 1,
                              "assentos": [int(p["id"])]})
        if oficio.get("faltando"):
            r["problemas"].append(f"nº {p.get('numero')} ({p.get('nome')}): falta "
                                  + ", ".join(oficio["faltando"]).lower())
        d = _dia(p.get("data_ato"))
        r["prazo"] = min([x for x in (r["prazo"], d) if x], default=None)
    r["quantos"] = len(r["arquivos"])
    return r


def _feitas(con, comp: str) -> set[str]:
    """Os destinos da competência que já não devem nada — pela tela
    (`rc_comunicacoes` ENVIADA ou DISPENSADA) ou pelo gestor (`ge_envios`)."""
    feitos = set()
    if _tem_tabela(con, "rc_comunicacoes"):
        feitos |= {r[0] for r in con.execute(
            "SELECT destino FROM rc_comunicacoes WHERE competencia = ? "
            "AND situacao IN ('ENVIADA','DISPENSADA')", (comp,))}
    if _tem_tabela(con, "ge_envios"):
        centrais = {r[0] for r in con.execute(
            "SELECT central FROM ge_envios WHERE competencia = ? "
            "AND situacao <> 'REJEITADO'", (comp,))}
        feitos |= {d for d, c in CENTRAL_DO_DESTINO.items() if c in centrais}
    return feitos


def competencias_comunicadas(con, central: str) -> set[str]:
    """As competências em que o destino `central` (vocabulário do gestor) já foi
    cumprido pela tela das comunicações. É o que `regra_obitos_do_mes` soma ao
    que `ge_envios` diz."""
    destino = {c: d for d, c in CENTRAL_DO_DESTINO.items()}.get(central)
    if not destino or not _tem_tabela(con, "rc_comunicacoes"):
        return set()
    return {r[0] for r in con.execute(
        "SELECT competencia FROM rc_comunicacoes WHERE destino = ? "
        "AND situacao IN ('ENVIADA','DISPENSADA')", (destino,))}


def _serventia_da_comunicacao(s: dict) -> dict:
    """A serventia como `atribuicoes_web._servent` a monta para a comunicação."""
    import serventia
    d = serventia.dados(s)
    substituta = (s.get("ri_substituta") or "").strip()
    return {"nome": d["serventia_titular"], "cidade": d["ri_cidade"], "uf": d["ri_uf"],
            "registrador": substituta or d["serventia_titular"],
            "titulo": ("Tabeliã Registradora Substituta" if substituta
                       else d["serventia_titulo"])}


def preparar_obitos(con, hoje: date, *, s: dict, ret: dict[int, str],
                    gravar: bool = True) -> dict:
    import gestor_conferencia as GC
    import rc_comunicacoes as COM
    r = _vazio()
    serv = _serventia_da_comunicacao(s)
    for ano, mes in GC._meses(_implantacao()[:7], hoje):
        if (ano, mes) >= (hoje.year, hoje.month):
            continue
        comp = f"{ano:04d}-{mes:02d}"
        faltam = [d["chave"] for d in COM.DESTINOS if d["chave"] not in _feitas(con, comp)]
        if not faltam:
            continue
        prazo = GC._quinto_dia_util(*GC._mes_seguinte(ano, mes))
        presos = [row for row in con.execute(
            "SELECT id, numero, nome FROM rc_assentos WHERE especie='OBITO' "
            "AND data_ato LIKE ?", (comp + "%",)) if int(row["id"]) in ret]
        if presos:
            r["problemas"].append(
                f"{comp}: não preparado — " + "; ".join(
                    f"óbito nº {x['numero']} ({x['nome']}): {ret[int(x['id'])]}" for x in presos))
            r["fora"] += [{"assento_id": x["id"], "nome": x["nome"], "numero": x["numero"],
                           "motivo": ret[int(x["id"])]} for x in presos]
            continue
        if gravar:
            COM.declarar_mes(con, comp, agora=_agora(), prazo_ate=prazo.isoformat(),
                             usuario=QUEM)
        linhas = {row["destino"]: row["id"] for row in con.execute(
            "SELECT id, destino FROM rc_comunicacoes WHERE competencia = ? "
            "AND situacao = 'PENDENTE'", (comp,))} if _tem_tabela(con, "rc_comunicacoes") else {}
        for destino in faltam:
            cid = linhas.get(destino)
            if cid is None:
                r["problemas"].append(f"{comp} — {destino}: a comunicação ainda não "
                                      "foi aberta (o agente abre na rodada)")
                continue
            m = COM.montar(con, cid, serventia=serv)
            r["arquivos"].append({"nome": f"OBITOS_{comp}_{destino}.txt",
                                  "dados": m["texto"].encode("utf-8"),
                                  "quantos": m["quantos"], "comunicacao_id": cid})
        r["prazo"] = min([x for x in (r["prazo"], prazo) if x], default=None)
    r["quantos"] = len(r["arquivos"])
    return r


def _trimestres(hoje: date) -> list[tuple[int, int]]:
    """Os trimestres fechados desde o do corte, inclusive."""
    ini = _dia(_implantacao())
    ano, tri = ini.year, (ini.month + 2) // 3
    saida = []
    while True:
        fim_mes = tri * 3
        prox = date(ano + 1, 1, 1) if fim_mes == 12 else date(ano, fim_mes + 1, 1)
        if prox > hoje:
            return saida
        saida.append((ano, tri))
        ano, tri = (ano + 1, 1) if tri == 4 else (ano, tri + 1)


def zip_do_ibge(montado: dict) -> bytes:
    """O `CARTINF.zip` como `atribuicoes_web._zip_do_ibge` o monta: ISO-8859-1 e
    CRLF — o arquivo é de largura fixa, e acento em dois bytes empurraria a linha."""
    import ibge_remessa as IBGE
    memoria = io.BytesIO()
    with zipfile.ZipFile(memoria, "w", zipfile.ZIP_DEFLATED) as z:
        for nome, linhas in sorted(montado["arquivos"].items()):
            corpo = IBGE.FIM_DE_LINHA.join(linhas) + IBGE.FIM_DE_LINHA
            z.writestr(nome, corpo.encode(IBGE.CODIFICACAO, "replace"))
    return memoria.getvalue()


def preparar_ibge(con, hoje: date, *, s: dict, ret: dict[int, str]) -> dict:
    import ibge_geracao as IBGEG
    r = _vazio()
    entregues = set()
    if _tem_tabela(con, "ib_entregas"):
        entregues |= {(x[0], x[1]) for x in con.execute(
            "SELECT ano, trimestre FROM ib_entregas WHERE enviada_em IS NOT NULL")}
    if _tem_tabela(con, "ge_envios"):
        entregues |= {(int(c[:4]), int(c[-1])) for (c,) in con.execute(
            "SELECT competencia FROM ge_envios WHERE central='IBGE' "
            "AND situacao <> 'REJEITADO' AND competencia LIKE '____-T_'")}
    r["transicao"] = []
    for ano, tri in _trimestres(hoje):
        if (ano, tri) in entregues:
            continue
        montado = IBGEG.montar(con, ano=ano, trimestre=tri, config=s)
        de, ate = montado["de"], montado["ate"]
        presos = [row for row in con.execute(
            "SELECT id, numero, nome, especie FROM rc_assentos WHERE data_ato >= ? "
            "AND data_ato <= ?", (de, ate + "z")) if int(row["id"]) in ret]
        if presos:
            r["problemas"].append(f"{ano}-T{tri}: não preparado — " + "; ".join(
                f"{x['especie'].lower()} nº {x['numero']}: {ret[int(x['id'])]}" for x in presos))
            continue
        # O TRIMESTRE QUE ATRAVESSA A TROCA DE SISTEMA: o E-Ofício lavrou até
        # 14/08/2026 e este sistema desde 09/09. O mapa é do trimestre inteiro;
        # se o E-Ofício já mandou a parte dele, mandar de novo é duplicar.
        acervo = con.execute(
            "SELECT COUNT(*) FROM rc_assentos WHERE data_ato >= ? AND data_ato <= ? "
            "AND COALESCE(situacao,'ATIVO') <> 'CANCELADO' "
            "AND COALESCE(origem,'') IN ('EOFICIO','ARQUIVO','IMPORTACAO')",
            (de, ate + "z")).fetchone()[0]
        if acervo:
            r["transicao"].append({"competencia": f"{ano}-T{tri}", "do_acervo": acervo,
                                   "linhas": montado["linhas"]})
        if montado["linhas"]:
            r["arquivos"].append({"nome": f"CARTINF_{ano}_T{tri}.zip",
                                  "dados": zip_do_ibge(montado),
                                  "quantos": montado["linhas"],
                                  "competencia": f"{ano}-T{tri}"})
        mes = tri * 3 + 1
        prazo = date(ano + 1, 1, 8) if mes > 12 else date(ano, mes, 8)
        r["prazo"] = min([x for x in (r["prazo"], prazo) if x], default=None)
        r["quantos"] += montado["linhas"]
    return r


PREPARA: dict[str, Callable] = {"SIRC": preparar_sirc, "CRC": preparar_crc,
                                "FUNAI": preparar_funai, "OBITOS": preparar_obitos,
                                "IBGE": preparar_ibge}


# ================================================================ a pasta

def escrever_na_pasta(raiz: Path, canal: str, arquivos: list[dict]) -> list[dict]:
    """Deixa na pasta da carga exatamente os arquivos de hoje.

    O que o agente escreveu ontem e hoje não vale mais (o item foi registrado,
    ou mudou) sai — mas só o que tem o prefixo dele: arquivo posto à mão fica.
    """
    destino = raiz / canal
    destino.mkdir(parents=True, exist_ok=True)
    novos = {a["nome"] for a in arquivos}
    for velho in destino.glob(PREFIXO_DO_ARQUIVO[canal] + "*"):
        if velho.is_file() and velho.name not in novos:
            velho.unlink()
    saida = []
    for a in arquivos:
        caminho = destino / a["nome"]
        if not caminho.exists() or caminho.read_bytes() != a["dados"]:
            caminho.write_bytes(a["dados"])
        saida.append({k: v for k, v in a.items() if k != "dados"}
                     | {"caminho": str(caminho), "sha256": _sha(a["dados"])})
    return saida


def _sem_bytes(r: dict) -> dict:
    return {**r, "arquivos": [{k: v for k, v in a.items() if k != "dados"}
                              | {"sha256": _sha(a["dados"])} for a in r["arquivos"]]}


def pauta(resumo: dict, hoje: date) -> str:
    """O LEIA-ME da pasta: o que subir hoje, carga por carga."""
    linhas = [f"CARGAS DO RCPN — {hoje:%d/%m/%Y}", "",
              "Arquivos preparados pelo agente de cargas. Quem sobe é a pessoa; o agente",
              "não manda nada a Central nenhuma.", ""]
    for canal in CANAIS:
        r = resumo.get(canal) or {}
        if "erro" in r:
            linhas += [f"{canal}: o agente NÃO conseguiu preparar — {r['erro']}", ""]
            continue
        if not r.get("arquivos"):
            linhas += [f"{canal}: nada a subir.", ""]
            continue
        prazo = r.get("prazo")
        linhas.append(f"{canal}: {len(r['arquivos'])} arquivo(s), {r.get('quantos', 0)} "
                      f"item(ns)" + (f", prazo {_dia(prazo):%d/%m/%Y}" if _dia(prazo) else ""))
        linhas += [f"   {a['nome']}" for a in r["arquivos"]]
        linhas.append(f"   Onde: {ONDE_SOBE[canal]}")
        for f in r.get("fora") or []:
            linhas.append(f"   FICOU FORA: {f.get('nome')} — {f.get('motivo')}")
        linhas.append("")
    return "\r\n".join(linhas) + "\r\n"


# ================================================================ A RODADA

def rodada(con: sqlite3.Connection, banco: Path | None = None, hoje: date | None = None,
           *, escrever=print) -> dict:
    """A rodada do agente: separa o que não pode ir, monta e deixa na pasta.

    Cada carga tem o seu `try`: uma que quebra não segura as outras, e a quebra
    fica gravada no livro de cargas — é ela que a conferência lê depois.
    """
    hoje = hoje or date.today()
    con.row_factory = sqlite3.Row
    init_gestor_schema(con)
    con.commit()
    s = _settings(con)
    raiz = pasta(con)
    try:
        ret = retidos(con)
    except Exception as erro:                           # noqa: BLE001
        # SEM A RÉGUA NÃO SE MONTA NADA: arquivo montado sem saber o que é
        # duplicado poderia levar o duplicado.
        ret = None
        falha = f"{type(erro).__name__}: {erro}"
    resumo: dict[str, Any] = {}
    for canal in CANAIS:
        try:
            if ret is None:
                raise RuntimeError(f"não deu para medir os assentos retidos ({falha})")
            r = PREPARA[canal](con, hoje, s=s, ret=ret)
            r["arquivos"] = escrever_na_pasta(raiz, canal, r["arquivos"])
            r["retidos_medidos_por"] = ("gestor_rcpn" if _tem_modulo("gestor_rcpn")
                                        else "régua provisória deste agente")
            resumo[canal] = r
            _registrar(con, canal, situacao="OK", detalhe=r)
        except Exception as erro:                       # noqa: BLE001
            con.rollback()
            resumo[canal] = {"erro": f"{type(erro).__name__}: {erro}"}
            _registrar(con, canal, situacao="ERRO",
                       detalhe={"erro": resumo[canal]["erro"],
                                "rastro": traceback.format_exc()[-2000:]})
        con.commit()
        r = resumo[canal]
        escrever(f"  cargas RCPN — {canal}: " + (r["erro"] if "erro" in r else
                 f"{len(r['arquivos'])} arquivo(s), {r.get('quantos', 0)} item(ns), "
                 f"{len(r.get('fora') or [])} retido(s), {len(r.get('faltas') or [])} sem dado"))
    try:
        raiz.mkdir(parents=True, exist_ok=True)
        (raiz / "LEIA-ME - O QUE SUBIR HOJE.txt").write_bytes(
            pauta(resumo, hoje).encode("utf-8-sig"))
    except OSError as erro:
        escrever(f"  cargas RCPN — o LEIA-ME não foi escrito: {erro}")
    # O ROBÔ OFICIAL ACOMPANHA OS AGENTES (09/10/2026): a batida diz que esta
    # passada aconteceu e como terminou. Sem o módulo dele, segue sem bater.
    try:
        import oficial_robos
        quebrou = [c for c in CANAIS if "erro" in resumo[c]]
        oficial_robos.bater(
            con, "CARGAS_RCPN",
            situacao="ERRO" if quebrou else ("AVISO" if any(
                resumo[c].get("arquivos") for c in CANAIS) else "OK"),
            resumo={c: (resumo[c]["erro"] if c in quebrou else
                        f"{len(resumo[c].get('arquivos') or [])} arquivo(s)") for c in CANAIS})
        con.commit()
    except ImportError:
        pass
    except Exception as erro:                           # noqa: BLE001
        escrever(f"  cargas RCPN — a batida no robô oficial falhou: {erro}")
    return resumo


def _tem_modulo(nome: str) -> bool:
    import importlib.util
    return importlib.util.find_spec(nome) is not None


# ============================================================ A CONFERÊNCIA

def _achado(chave, regra, gravidade, setor, titulo, detalhe="", prazo=None,
            fundamento="") -> dict:
    return {"chave": chave, "regra": regra, "gravidade": gravidade, "setor": setor,
            "titulo": titulo, "detalhe": detalhe,
            "prazo": prazo.isoformat() if isinstance(prazo, date) else prazo,
            "fundamento": fundamento}


def _ultima_rodada(con, canal: str):
    return con.execute(
        "SELECT * FROM ge_rcpn_cargas WHERE canal=? AND tipo='RODADA' "
        "ORDER BY id DESC LIMIT 1", (canal,)).fetchone()


def conferir(con: sqlite3.Connection, hoje: date) -> list[dict]:
    """O que está pronto e não subiu, o que não monta, e o agente parado.
    SÓ LÊ — o que mede é o livro de cargas que a rodada deixou."""
    import gestor_conferencia as GC
    con.row_factory = sqlite3.Row
    if not _tem_tabela(con, "ge_rcpn_cargas"):
        return [_achado("CARGAS_RCPN_AGENTE:TODAS", "CARGAS_RCPN_AGENTE_PARADO", "CRITICO",
                        "TI", "O agente de cargas do RCPN nunca rodou nesta base",
                        "A rodada das 07:30 chama gestor_cargas_rcpn.rodada.")]
    achados: list[dict] = []
    limite = (hoje - timedelta(days=AGENTE_DIAS_TOLERADOS)).isoformat()
    for canal in CANAIS:
        linha = _ultima_rodada(con, canal)
        if linha is None or (linha["gerado_em"] or "")[:10] < limite:
            achados.append(_achado(
                f"CARGAS_RCPN_AGENTE:{canal}", "CARGAS_RCPN_AGENTE_PARADO", "CRITICO", "TI",
                f"O agente de cargas do RCPN não preparou {canal} desde "
                f"{(linha['gerado_em'] or '')[:10] if linha else 'nunca'}",
                "A rodada das 07:30 chama gestor_cargas_rcpn.rodada; veja o "
                "CONFERENCIA_DIARIA.log."))
            continue
        r = json.loads(linha["detalhe"] or "{}") or {}
        if linha["situacao"] == "ERRO":
            achados.append(_achado(
                f"CARGAS_RCPN_AGENTE:{canal}", "CARGAS_RCPN_AGENTE_PARADO", "CRITICO", "TI",
                f"O agente de cargas do RCPN quebrou ao preparar {canal}", r.get("erro", "")))
            continue
        prazo = _dia(r.get("prazo"))
        if r.get("arquivos"):
            gravidade = (GC._situacao_do_prazo(prazo, hoje) if prazo else None) or "PRAZO"
            nomes = "\n".join(f"• {a['caminho']}" for a in r["arquivos"])
            fora = "".join(f"\nFicou fora: {f.get('nome')} — {f.get('motivo')}."
                           for f in r.get("fora") or [])
            ressalvas = "".join(f"\nAtenção: {p}" for p in r.get("problemas") or [])
            achados.append(_achado(
                f"CARGAS_RCPN_PRONTA:{canal}", "CARGAS_RCPN_PRONTA", gravidade, "RCPN",
                f"{canal}: {len(r['arquivos'])} arquivo(s) pronto(s) para subir "
                f"({r.get('quantos', 0)} item(ns))",
                f"{nomes}\nOnde: {ONDE_SOBE[canal]}{fora}{ressalvas}", prazo,
                FUNDAMENTO[canal]))
        for f in r.get("faltas") or []:
            faltas = f.get("faltas") or []
            achados.append(_achado(
                f"CARGAS_RCPN_FALTA:{canal}:rc_assentos:{f.get('assento_id')}",
                "CARGAS_RCPN_FALTA", "ATENCAO", "RCPN",
                f"{canal}: {f.get('nome') or 'assento ' + str(f.get('assento_id'))} não "
                "monta — falta dado no assento",
                "; ".join(str(x) for x in faltas) if isinstance(faltas, list) else str(faltas),
                prazo, FUNDAMENTO[canal]))
        if r.get("erros_xsd"):
            achados.append(_achado(
                f"CARGAS_RCPN_INVALIDA:{canal}", "CARGAS_RCPN_INVALIDA", "CRITICO", "TI",
                f"{canal}: o arquivo montado não passa no esquema oficial — não foi para a pasta",
                "\n".join(r["erros_xsd"][:10])))
        elif r.get("xsd") == "NAO_MEDIU":
            achados.append(_achado(
                f"CARGAS_RCPN_INVALIDA:{canal}", "CARGAS_RCPN_INVALIDA", "NAO_MEDIU", "TI",
                f"{canal}: o arquivo não pôde ser conferido contra o esquema",
                "Falta o lxml ou o arquivo schemas/cargaRegistrosCompleto.xsd na "
                "instalação. O arquivo foi para a pasta sem a conferência."))
        for t in r.get("transicao") or []:
            achados.append(_achado(
                f"CARGAS_RCPN_DECISAO:IBGE:{t['competencia']}", "CARGAS_RCPN_DECISAO",
                "ATENCAO", "GESTAO",
                f"IBGE {t['competencia']}: o trimestre atravessa a troca do E-Ofício",
                f"O mapa preparado tem {t['linhas']} linha(s), e {t['do_acervo']} registro(s) "
                "do trimestre vieram do E-Ofício (lavrados até 14/08/2026). Se o E-Ofício "
                "já mandou a parte dele, subir este arquivo a manda de novo; se não "
                "mandou, ela tem de ir. Decisão do oficial antes de subir.",
                prazo, FUNDAMENTO["IBGE"]))
    return achados


# ================================================================ o painel

def painel(con: sqlite3.Connection) -> dict:
    """O que a última rodada deixou, carga por carga. SÓ LÊ."""
    saida = {}
    for canal in CANAIS:
        linha = _ultima_rodada(con, canal) if _tem_tabela(con, "ge_rcpn_cargas") else None
        if linha is None:
            saida[canal] = None
            continue
        r = json.loads(linha["detalhe"] or "{}") or {}
        saida[canal] = {"em": linha["gerado_em"], "situacao": linha["situacao"],
                        "arquivos": len(r.get("arquivos") or []),
                        "quantos": r.get("quantos"), "prazo": r.get("prazo")}
    return saida


def medir(con: sqlite3.Connection, hoje: date) -> dict:
    """Tudo o que a rodada prepararia, SEM gravar nada e sem escrever na pasta —
    para conferir contra a produção aberta só para leitura."""
    con.row_factory = sqlite3.Row
    s = _settings(con)
    ret = retidos(con)
    saida: dict[str, Any] = {"retidos": ret}
    for canal in CANAIS:
        try:
            kw = {"gravar": False} if canal == "OBITOS" else {}
            saida[canal] = _sem_bytes(PREPARA[canal](con, hoje, s=s, ret=ret, **kw))
        except Exception as erro:                       # noqa: BLE001
            saida[canal] = {"erro": f"{type(erro).__name__}: {erro}",
                            "rastro": traceback.format_exc()[-1500:]}
    return saida


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="O agente de cargas do RCPN.")
    ap.add_argument("--banco", required=True)
    ap.add_argument("--hoje", default=date.today().isoformat())
    ap.add_argument("--so-medir", action="store_true",
                    help="não grava nem escreve na pasta: só mostra o que prepararia")
    a = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:                                   # noqa: BLE001
        pass
    hoje = date.fromisoformat(a.hoje)
    if a.so_medir:
        con = sqlite3.connect(f"file:{a.banco}?mode=ro", uri=True, timeout=60)
        try:
            print(json.dumps(medir(con, hoje), ensure_ascii=False, indent=1, default=str))
        finally:
            con.close()
        return 0
    con = sqlite3.connect(a.banco, timeout=60)
    try:
        rodada(con, Path(a.banco), hoje)
        for x in conferir(con, hoje):
            print(f"  [{x['gravidade']}] {x['titulo']}")
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
