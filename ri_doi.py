"""
A DECLARAÇÃO DO REGISTRO DE IMÓVEIS NO FORMATO DO DOI-WEB.

POR QUE ESTE MÓDULO EXISTE — a DOI de 09/2026, entregue em 22/10/2026
    A tela da DOI montava a declaração do RI com `ri_ctp.montar_registro`, o
    montador da CTP da CENSEC, e a CTP só conhece o serviço Notarial. O arquivo
    de setembro saiu com cinco defeitos em cada declaração, e o DOI-Web recusou
    ou deixou passar errado:

      tipoServico "1" (Notarial) e tipoAto "1" (Escritura) num registro de RI;
      sem tipoLivro, naturezaTitulo e numeroRegistroAverbacao;
      a folha era a da MATRÍCULA («FICHA», «fichas», vazia), e não a do ato;
      a localização era a descrição perimétrica cortada em 200 caracteres;
      a chave `IndicadorNaoConsta…` com «I» maiúsculo, que o layout não tem;
      `indicadorConjuge` em parte que é CNPJ (o INCRA) — o DOI-Web recusa;
      `mesAnoUltimaParcela` «08/2036», e o layout exige data AAAA-MM-DD;
      título a prazo sem `valorPagoAteDataAto`, que o DOI-Web cobra.

    O arquivo corrigido à mão foi aceito com zero pendência. Este módulo faz o
    mesmo pelo sistema, e confere contra o LAYOUT OFICIAL antes de gerar.

O LAYOUT É O DA RECEITA, E MORA AO LADO: `ri_doi_layout.json` é o
    `/api/layout-doiweb.json` do DOI-Web (JSON Schema 2020-12), baixado em
    22/10/2026, sha256 f244cfbc…17666. Quando a Receita mudar o layout, troca-se
    o arquivo — a conferência acompanha sem mexer no código.

O PRECEDENTE DO TÍTULO DE DOMÍNIO A PRAZO é a DOI da matrícula 4014 (controle
    3226, entregue em agosto/2026): última parcela «2036-08-01» e valor pago =
    parcelas vencidas até a data do ato (6 × 425,52 = 2.553,12). O que o título
    não diz — se a parcela vencida foi paga — a casa já declarou assim, e é
    assim que o sistema sugere. Quem confere pode corrigir na tela da CTP.
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

import ri_cnm
from ri_ctp import _bool, _decimal, montar_registro, so_digitos

LAYOUT = json.loads((Path(__file__).with_name("ri_doi_layout.json"))
                    .read_text(encoding="utf-8"))
DEFS = LAYOUT["$defs"]

TIPO_SERVICO_RI = "2"
TIPO_ATO_REGISTRO = "4"
TIPO_ATO_AVERBACAO = "3"
TIPO_LIVRO_REGISTRO_GERAL = "1"

NATUREZA_TITULO = {
    "1": "Instrumento particular com força de escritura pública",
    "2": "Escritura pública",
    "3": "Título judicial",
    "4": "Contratos ou termos administrativos",
    "5": "Atos autênticos de países estrangeiros",
}

# Pistas no teor do ato -> natureza do título. A ORDEM IMPORTA, e «INCRA» não
# é pista: a escritura de imóvel rural cita o INCRA (o CCIR, o SIGEF) e não
# deixa de ser escritura — a R-1/4004 e a R-2/4020 citam. Sugestão, e a tela
# diz que é.
_PISTAS_NATUREZA = (
    ("3", ("carta de sentenca", "formal de partilha", "mandado judicial",
           "carta de adjudicacao", "carta de arrematacao")),
    ("2", ("escritura publica", "escritura de compra", "escritura de doacao")),
    ("4", ("titulo de dominio", "termo administrativo",
           "contrato administrativo", "concessao de uso")),
    ("1", ("instrumento particular", "cedula de credito", "contrato particular")),
)

_MESES = {"janeiro": 1, "fevereiro": 2, "marco": 3, "março": 3, "abril": 4,
          "maio": 5, "junho": 6, "julho": 7, "agosto": 8, "setembro": 9,
          "outubro": 10, "novembro": 11, "dezembro": 12}


def _sem_acento(texto: Any) -> str:
    import unicodedata
    s = unicodedata.normalize("NFD", "" if texto is None else str(texto))
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


def _texto_do_teor(teor: Any) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", str(teor or "")))


def natureza_sugerida(ato: dict, operacao: str = "") -> str:
    """A natureza do título lida do teor. Vazio quando não há pista."""
    if str(operacao) == "73":          # título de domínio — sempre termo administrativo
        return "4"
    texto = _sem_acento(_texto_do_teor(ato.get("teor")) + " " +
                        (ato.get("natureza_titulo") or ""))
    for codigo, pistas in _PISTAS_NATUREZA:
        if any(p in texto for p in pistas):
            return codigo
    return ""


# ------------------------------------------------- denominação do imóvel

# A coluna `logradouro` da ficha rural guarda, às vezes, a FRASE da ficha e não
# o nome do imóvel — medido na DOI de 09/2026: «Município de <a cidade>,
# Estado do Maranhão.» (4018) e «situada na zona rural do Município…» (4020,
# 4021). Isso não é denominação, e o DOI-Web aceita sem reclamar.
_FRASE_NAO_E_NOME = ("situad", "municipio", "zona rural", "localizad", "estado do")


def _parece_frase(texto: Any) -> bool:
    return _sem_acento(texto).strip().startswith(_FRASE_NAO_E_NOME)


def denominacao_sugerida(ato: dict, m: dict) -> str:
    """O nome do imóvel: da ficha quando ela traz um nome, senão do teor do ato."""
    ficha = str(m.get("logradouro") or "").strip()
    if ficha and not _parece_frase(ficha):
        return ficha[:200]
    t = _texto_do_teor(ato.get("teor"))
    for padrao in (
            r"IM[ÓO]VEL OBJETO DESTA MATR[ÍI]CULA:\s*(.{3,120}?),\s*com",
            r"denominad[oa]\s+(?:de\s+)?[\"“«]?(.{3,120}?)[\"”»]?\s*,\s*"
            r"(?:situad|localizad|com\s+[áa]rea|no\s+munic|neste\s+munic)"):
        achado = re.search(padrao, t, re.I)
        if achado and not _parece_frase(achado.group(1)):
            return achado.group(1).strip(" \"“”«»")[:200]
    return ""


# ------------------------------------------------- pagamento a prazo

def parcelas_do_teor(teor: Any) -> dict | None:
    """Quantidade, valor e 1º vencimento das prestações, lidos do teor.

    As duas redações medidas nos títulos do INCRA desta casa:
      «em 17 (dezessete) prestações anuais de R$ 453,34 (...), vencendo-se a
       primeira em 22 de agosto de 2020» (R-1/4019)
      «em 17 (dezessete) prestações anuais, sendo a primeira no valor de
       R$ 425,52 (...), com vencimento indicado no título em 22 de agosto de
       2020» (R-1/4014)
    Devolve None quando não acha as três coisas: meia leitura não sugere nada.
    """
    t = _texto_do_teor(teor)
    m = re.search(r"(\d+)\s*\([^)]*\)\s*presta[çc][õo]es\s+anuais", t, re.I)
    if not m:
        return None
    trecho = t[m.start(): m.start() + 600]
    valor = re.search(r"R\$\s*([\d.]+,\d{2})", trecho)
    data = re.search(r"(\d{1,2})\s+de\s+([a-zçã]+)\s+de\s+(\d{4})", trecho, re.I)
    if not (valor and data and _sem_acento(data.group(2)) in
            {_sem_acento(k) for k in _MESES}):
        return None
    mes = next(v for k, v in _MESES.items() if _sem_acento(k) == _sem_acento(data.group(2)))
    return {"quantidade": int(m.group(1)), "valor": _decimal(valor.group(1)),
            "primeira": date(int(data.group(3)), mes, int(data.group(1)))}


def pagamento_a_prazo(parcelas: dict, data_ato: str) -> dict:
    """Última parcela e valor das vencidas até a data do ato (o precedente)."""
    primeira = parcelas["primeira"]
    ato = date.fromisoformat(str(data_ato)[:10])
    vencidas = sum(1 for i in range(parcelas["quantidade"])
                   if date(primeira.year + i, primeira.month, primeira.day) <= ato)
    ultima = primeira.year + parcelas["quantidade"] - 1
    return {"ultima_parcela": f"{ultima:04d}-{primeira.month:02d}-01",
            "valor_pago_ate_ato": round(vencidas * parcelas["valor"], 2),
            "vencidas": vencidas}


def _data_da_ultima_parcela(valor: Any) -> str:
    """«08/2036», «2036-08» ou «2036-08-22» -> «2036-08-01» (o precedente)."""
    s = str(valor or "").strip()
    m = re.fullmatch(r"(\d{1,2})/(\d{4})", s)
    if m:
        return f"{m.group(2)}-{int(m.group(1)):02d}-01"
    m = re.fullmatch(r"(\d{4})-(\d{2})(?:-\d{2})?", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-01"
    return s


# ------------------------------------------------- sugestões para a tela

def sugestoes(ato: dict, m: dict, dados: dict) -> dict:
    """O que a tela da CTP pode pré-preencher para a DOI, sem gravar nada."""
    s: dict[str, Any] = {}
    nat = natureza_sugerida(ato, dados.get("operacao") or "")
    if nat:
        s["natureza_titulo"] = nat
    rural = (m.get("rural_urbano") or "").upper().startswith("R")
    if rural:
        s["localizacao"] = "zona rural"
        nome = denominacao_sugerida(ato, m)
        if nome:
            s["denominacao"] = nome
    par =parcelas_do_teor(ato.get("teor"))
    if par and ato.get("data_ato"):
        s.update({k: v for k, v in pagamento_a_prazo(par, ato["data_ato"]).items()
                  if k != "vencidas"})
        s["forma_pagamento"] = "7"
    return s


def com_sugestoes(ato: dict, m: dict, dados: dict) -> dict:
    """`dados` com as lacunas preenchidas pelas sugestões. O digitado ganha."""
    out = dict(sugestoes(ato, m, dados))
    out.update({k: v for k, v in dados.items() if str(v or "").strip()})
    return out


# ------------------------------------------------- a declaração

def _parte_doi(p: dict) -> dict:
    """A parte no vocabulário do DOI-Web (o da CTP difere em três nomes)."""
    p = dict(p)
    if "niConjuge" in p:
        p["cpfConjuge"] = p.pop("niConjuge")
        p["indicadorCpfConjugeIdentificado"] = True
    if "indicadorConjugeParticipante" in p:
        p["indicadorConjugeParticipa"] = p.pop("indicadorConjugeParticipante")
    # Pessoa jurídica não tem cônjuge: o DOI-Web RECUSA o campo quando o ni
    # tem 14 dígitos (medido na validação de 22/10/2026, matrícula 4018).
    if len(p.get("ni") or "") == 14:
        for k in ("indicadorConjuge", "cpfConjuge", "indicadorConjugeParticipa",
                  "indicadorCpfConjugeIdentificado", "regimeBens"):
            p.pop(k, None)
    return p


def montar(ato: dict, m: dict, partes: list[dict], dados: dict,
           cns: str, codigo_ibge: str) -> dict:
    """A declaração do ato do RI, pronta para o DOI-Web."""
    dados = com_sugestoes(ato, m, dados)
    reg = montar_registro(ato, m, partes, dados, cns, codigo_ibge,
                          tipo_servico=TIPO_SERVICO_RI,
                          tipo_ato=(TIPO_ATO_REGISTRO if (ato.get("tipo") or "R") == "R"
                                    else TIPO_ATO_AVERBACAO))
    reg["tipoLivro"] = TIPO_LIVRO_REGISTRO_GERAL
    reg["numeroLivro"] = "2"
    reg["numeroRegistroAverbacao"] = str(int(ato.get("numero") or 0)).zfill(7)
    reg["folha"] = str(dados.get("folha_ato") or "").strip()
    if dados.get("natureza_titulo"):
        reg["naturezaTitulo"] = str(dados["natureza_titulo"])
    reg["existeDoiAnterior"] = _bool(dados.get("doi_anterior"))

    if not reg.get("codigoNacionalMatricula"):
        try:
            reg["codigoNacionalMatricula"] = so_digitos(
                ri_cnm.montar(cns, "2", so_digitos(m.get("numero"))))
        except ri_cnm.CnmError:
            pass

    # A localização NUNCA é a descrição perimétrica: cortada em 200 caracteres
    # ela não localiza nada (era o que saía na 4018, 4020 e 4021).
    rural = reg.get("destinacao") == "3"
    if rural:
        loc = (dados.get("localizacao") or m.get("bairro") or "zona rural")
        reg["localizacao"] = str(loc)[:200]
        reg["denominacao"] = str(dados.get("denominacao") or "")[:200]

    return no_layout_do_doiweb(reg)


def no_layout_do_doiweb(reg: dict) -> dict:
    """O registro montado por `ri_ctp` com os nomes e formatos do DOI-Web.

    Vale para o RI e para a escritura, que vão no MESMO arquivo: o montador da
    CTP fala a língua da CENSEC, e o DOI-Web difere em quatro pontos medidos
    em 22/10/2026 — a caixa de `indicadorNaoConsta…`, os nomes do cônjuge, o
    cônjuge de pessoa jurídica e a data da última parcela.
    """
    reg = dict(reg)
    if "IndicadorNaoConstaValorBaseCalculoItbiItcmd" in reg:
        reg["indicadorNaoConstaValorBaseCalculoItbiItcmd"] = reg.pop(
            "IndicadorNaoConstaValorBaseCalculoItbiItcmd")
    if reg.get("mesAnoUltimaParcela"):
        reg["mesAnoUltimaParcela"] = _data_da_ultima_parcela(reg["mesAnoUltimaParcela"])
    for lado in ("alienantes", "adquirentes"):
        reg[lado] = [_parte_doi(p) for p in reg.get(lado) or []]
    return reg


# ------------------------------------------------- conferências

def pendencias(ato: dict, m: dict, dados: dict) -> list[str]:
    """O que é da DOI do RI e a conferência da CTP não cobra."""
    d = com_sugestoes(ato, m, dados)
    p = []
    if not str(d.get("folha_ato") or "").strip():
        p.append("falta a folha (ficha) do ato — onde ele começa e termina, ex.: 2-2v")
    elif len(str(d["folha_ato"]).strip()) > 7:
        p.append("a folha do ato passa de 7 caracteres, que é o limite do DOI-Web")
    if str(d.get("natureza_titulo") or "") not in NATUREZA_TITULO:
        p.append("falta a natureza do título (escritura, título judicial, "
                 "termo administrativo…)")
    if str(d.get("forma_pagamento") or "") == "7":
        if _decimal(d.get("valor_pago_ate_ato")) is None:
            p.append("pagamento a prazo sem o valor pago até a data do ato")
        if not str(d.get("ultima_parcela") or "").strip():
            p.append("pagamento a prazo sem o mês e o ano da última parcela")
    rural = (m.get("rural_urbano") or "").upper().startswith("R")
    if rural:
        nome = str(d.get("denominacao") or "").strip()
        if not nome:
            p.append("imóvel rural sem a denominação (o nome da fazenda, sítio ou lote)")
        elif _parece_frase(nome):
            p.append(f"a denominação «{nome[:40]}…» é frase da ficha, e não o nome "
                     f"do imóvel — escreva o nome (ex.: Chácara Arco-Íris)")
    return p


def _dominio(ref: str) -> set[str]:
    alvo = DEFS[ref.split("/")[-1]]
    return {o["const"] for o in alvo.get("oneOf", [])} | set(alvo.get("enum", []))


def _conferir(obj: dict, schema: dict, onde: str, erros: list[str]) -> None:
    props = schema.get("properties", {})
    for k in schema.get("required", []):
        if k not in obj:
            erros.append(f"{onde}: falta o campo {k}")
    for k, v in obj.items():
        if k not in props:
            erros.append(f"{onde}: campo {k} não existe no layout do DOI-Web")
            continue
        regra = props[k]
        if "$ref" in regra:
            if str(v) not in _dominio(regra["$ref"]):
                erros.append(f"{onde}: {k} = {v!r} fora da tabela do DOI-Web")
            continue
        tipo = regra.get("type")
        if tipo == "string":
            if not isinstance(v, str):
                erros.append(f"{onde}: {k} tem de ser texto")
            elif "maxLength" in regra and len(v) > regra["maxLength"]:
                erros.append(f"{onde}: {k} passa de {regra['maxLength']} caracteres")
            elif regra.get("format") == "date" and v and \
                    not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
                erros.append(f"{onde}: {k} tem de ser data AAAA-MM-DD, veio {v!r}")
        elif tipo == "boolean" and not isinstance(v, bool):
            erros.append(f"{onde}: {k} tem de ser verdadeiro/falso")
        elif tipo == "number" and (isinstance(v, bool) or not isinstance(v, (int, float))):
            erros.append(f"{onde}: {k} tem de ser número")
        elif tipo == "array":
            if regra.get("minItems") and len(v) < regra["minItems"]:
                erros.append(f"{onde}: {k} vazio")
            item = (regra.get("items") or {}).get("$ref")
            for i, el in enumerate(v):
                if item:
                    _conferir(el, DEFS[item.split("/")[-1]], f"{onde}.{k}[{i + 1}]", erros)


def conferir_layout(reg: dict) -> list[str]:
    """A declaração contra o layout oficial do DOI-Web. Lista vazia = passa."""
    erros: list[str] = []
    _conferir(reg, DEFS["DeclaracaoDadosBasicosDTO"], "declaração", erros)
    for p in reg.get("alienantes", []) + reg.get("adquirentes", []):
        if len(p.get("ni") or "") == 14 and "indicadorConjuge" in p:
            erros.append("pessoa jurídica com indicadorConjuge — o DOI-Web recusa")
    return erros
