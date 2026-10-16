"""A consulta à base nacional do CCN, e o que ela traz para o cartão de firma.

    «crie a integracao do ccn para receber e consultar na base nacional.
     tenho uma chave de exportacao do ccn» — o oficial, 15/10/2026

O QUE É, NO VOCABULÁRIO DO CNB
    Mandar daqui para lá é IMPORTAR (`ccn_envio.py`); trazer de lá para cá é
    EXPORTAR. São duas operações, medidas no contrato «CCN 2.99.2 RTM»
    (`FONTES_EXTERNAS/enotariado/ccn_exportacao_2.99.2.json`):

        GET /api/exports/record-sets/{cpf}         quem tem cadastro com o CPF,
                                                    um por cartório
        GET /api/exports/record-sets/{id}/current  a ficha atual daquele cadastro

    As duas pedem o `AppToken` (a «chave de exportação») e um `X-Signature`
    por requisição: a assinatura CAdES de `{"Timestamp":…,"RequestPath":…}`,
    feita pelo A3 do delegatário no serviço local (`a3_servico_local.py`).

QUEM CHAMA O CCN NÃO É ESTE MÓDULO
    A Cloudflare só deixa passar navegador (`O_CCN_E_AS_DUAS_PAREDES.md`). O
    escrevente pede a consulta aqui, recebe um CÓDIGO, e a extensão «CG CCN
    Assistente» faz as chamadas de dentro da aba do portal e devolve a
    resposta pela ponte (só 127.0.0.1, autenticada pelo código) — o mesmo
    caminho do envio do lote.

O QUE ENTRA NO CARTÃO, E O QUE NÃO ENTRA
    A ficha do CCN se MOSTRA inteira. No cartão de firma do mesmo CPF entra só
    o que ele NÃO tem: campo vazio se preenche, campo preenchido não se troca.
    O que a casa conferiu com o documento na mão vale mais que o cadastro de
    outro cartório, e a divergência aparece ao lado, para quem decide.
    Os alertas — pessoa politicamente exposta, investigação por terrorismo,
    cadastro bloqueado no CCN — aparecem na tela e NÃO se gravam sozinhos: são
    decisões do balcão, com motivo.
    E não se abre cartão novo daqui: abrir ficha de firma é ato, com selo.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import sqlite3
from typing import Any

import ccn_envio as CE

SCHEMA = """
CREATE TABLE IF NOT EXISTS nt_ccn_consultas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cpf TEXT NOT NULL,
    ambiente TEXT NOT NULL,                  -- HOMOLOGACAO | PRODUCAO
    situacao TEXT NOT NULL DEFAULT 'PEDIDA', -- PEDIDA | ENCONTRADA | NAO_ENCONTRADA | FALHOU
    pedida_em TEXT NOT NULL,
    pedida_por TEXT,
    respondida_em TEXT,
    achados_json TEXT,                       -- a lista de record-sets/{cpf}
    registros_json TEXT,                     -- as fichas de record-sets/{id}/current
    erro TEXT,
    cartao_id INTEGER REFERENCES nt_cartoes(id),
    aplicada_em TEXT,
    aplicada_por TEXT,
    aplicados_json TEXT                      -- {coluna: valor} que entraram no cartão
);
CREATE INDEX IF NOT EXISTS ix_nt_ccn_consultas_cpf ON nt_ccn_consultas(cpf, pedida_em);
"""

#: Fichas trazidas por consulta — um CPF com cadastro em muitos cartórios não
#: pode virar uma rajada de assinaturas no A3.
MAXIMO_DE_FICHAS = 5


class ConsultaError(CE.CcnError):
    """Erro de regra da consulta ao CCN, com a frase pronta para o balcão."""


def init_schema(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA)


def tem_tabela(con: sqlite3.Connection) -> bool:
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                       "AND name='nt_ccn_consultas'").fetchone() is not None


# ----------------------------------------------------------------- o pedido

def pedir(con: sqlite3.Connection, cpf: Any, ambiente: str, *, usuario: str,
          agora: str) -> int:
    """Abre o pedido de consulta. ESCREVE. Devolve o número do pedido."""
    numero = CE.cpf_valido(cpf)
    if not numero:
        raise ConsultaError("CPF inválido — confira os 11 dígitos")
    if ambiente not in CE.AMBIENTES:
        raise ConsultaError(f"ambiente desconhecido: {ambiente}")
    init_schema(con)
    return con.execute(
        "INSERT INTO nt_ccn_consultas(cpf, ambiente, pedida_em, pedida_por) VALUES (?,?,?,?)",
        (numero, ambiente, agora, usuario)).lastrowid


def codigo_da_consulta(segredo: str, consulta_id: int) -> str:
    """O código que o escrevente cola na extensão. Derivado, e não guardado.

    Começa com «C», e é isso que separa na ponte a consulta do lote de envio
    (cujo código é só número e hífen).
    """
    mac = hmac.new(str(segredo).encode("utf-8"), f"ccn-consulta:{int(consulta_id)}".encode(),
                   hashlib.sha256).hexdigest()
    return f"C{int(consulta_id)}-{mac[:10].upper()}"


def e_codigo_de_consulta(codigo: Any) -> bool:
    return bool(re.fullmatch(r"\s*[Cc]\d+-[0-9A-Fa-f]{10}\s*", str(codigo or "")))


def consulta_pelo_codigo(con: sqlite3.Connection, segredo: str, codigo: str) -> dict:
    """O pedido que aquele código abre — ou recusa. Só LÊ."""
    m = re.fullmatch(r"\s*[Cc](\d+)-([0-9A-Fa-f]{10})\s*", str(codigo or ""))
    if not m or not hmac.compare_digest(codigo_da_consulta(segredo, int(m.group(1))),
                                        f"C{int(m.group(1))}-{m.group(2).upper()}"):
        raise ConsultaError("código da consulta não confere — copie de novo da tela do Cartório Gestão")
    if not tem_tabela(con):
        raise ConsultaError("consulta não encontrada")
    con.row_factory = sqlite3.Row
    r = con.execute("SELECT * FROM nt_ccn_consultas WHERE id=?", (int(m.group(1)),)).fetchone()
    if r is None:
        raise ConsultaError("consulta não encontrada")
    return dict(r)


def para_a_extensao(consulta: dict, codigo: str) -> dict:
    """O que a extensão precisa para fazer as chamadas. Sem dado de pessoa além do CPF."""
    return {"codigo": codigo, "consulta_id": consulta["id"], "cpf": consulta["cpf"],
            "ambiente": consulta["ambiente"], "host": CE.AMBIENTES[consulta["ambiente"]],
            "maximo_de_fichas": MAXIMO_DE_FICHAS}


def registrar_resposta(con: sqlite3.Connection, consulta: dict, dados: dict, agora: str) -> dict:
    """O que a extensão trouxe do CCN. ESCREVE.

    `dados`: `{"achados": [ExportRecordSetModel], "registros":
    [ExportCivilianRecordModel], "erro": "texto"}`. Uma ficha de OUTRO CPF é
    recusada inteira: o código abre a consulta de um CPF, e só dele.
    """
    erro = str(dados.get("erro") or "").strip()[:2000] or None
    achados = dados.get("achados") or []
    registros = dados.get("registros") or []
    if not isinstance(achados, list) or not isinstance(registros, list):
        raise ConsultaError("resposta da extensão fora do formato")
    registros = [r for r in registros if isinstance(r, dict)][:MAXIMO_DE_FICHAS]
    for r in [*achados, *registros]:
        if not isinstance(r, dict):
            raise ConsultaError("resposta da extensão fora do formato")
        outro = CE.cpf_valido(r.get("cpf"))
        if r.get("cpf") and outro != consulta["cpf"]:
            raise ConsultaError("o CCN devolveu ficha de outro CPF — nada foi gravado")
    if erro and not achados:
        situacao = "FALHOU"
    elif achados:
        situacao = "ENCONTRADA"
    else:
        situacao = "NAO_ENCONTRADA"
    con.execute(
        """UPDATE nt_ccn_consultas SET situacao=?, respondida_em=?, achados_json=?,
                  registros_json=?, erro=? WHERE id=?""",
        (situacao, agora, json.dumps(achados, ensure_ascii=False),
         json.dumps(registros, ensure_ascii=False), erro, consulta["id"]))
    return {"situacao": situacao, "achados": len(achados), "fichas": len(registros)}


def consultas(con: sqlite3.Connection, limite: int = 50) -> list[dict]:
    if not tem_tabela(con):
        return []
    con.row_factory = sqlite3.Row
    return [dict(r) for r in con.execute(
        "SELECT * FROM nt_ccn_consultas ORDER BY id DESC LIMIT ?", (int(limite),))]


def carregar(con: sqlite3.Connection, consulta_id: int) -> dict | None:
    if not tem_tabela(con):
        return None
    con.row_factory = sqlite3.Row
    r = con.execute("SELECT * FROM nt_ccn_consultas WHERE id=?", (int(consulta_id),)).fetchone()
    if r is None:
        return None
    c = dict(r)
    c["achados"] = json.loads(c.get("achados_json") or "[]")
    c["registros"] = json.loads(c.get("registros_json") or "[]")
    return c


# ------------------------------------------------- do formato do CCN ao da casa

ESTADO_CIVIL = {
    "Solteiro": "Solteiro(a)", "Casado": "Casado(a)", "Divorciado": "Divorciado(a)",
    "Viuvo": "Viúvo(a)", "UniaoEstavel": "União Estável",
    "SeparadoJudicialmente": "Separado Judicialmente", "Desquitado": "Desquitado(a)",
    "SeparadoExtrajudicialmente": "Separado Extrajudicialmente",
}
REGIME = {
    "RegimeOfPartialCommunityProperty": "comunhão parcial de bens",
    "RegimeOfUniversalCommunityProperty": "comunhão universal de bens",
    "FinalSharingInAcquets": "participação final nos aquestos",
    "SeparationOfProperty": "separação de bens",
    "MandatorySeparation": "separação obrigatória de bens",
}
DOCUMENTO = {"IdCard": "RG", "ProfessionalCard": "carteira profissional", "RNE": "RNE",
             "Passport": "passaporte", "ReservistCard": "certificado de reservista"}
BRASILEIROS = ("Brazilian", "NaturalizedBrazilian", "BrazilianBornAbroad")


def _texto(v: Any) -> str:
    return " ".join(str(v or "").split())


def _data(v: Any) -> str:
    """«1968-05-06T00:00:00» → «1968-05-06» — a forma em que o cartão guarda."""
    m = re.match(r"(\d{4}-\d{2}-\d{2})", str(v or ""))
    return m.group(1) if m else ""


def _digitos(v: Any) -> str:
    return re.sub(r"\D", "", str(v or ""))


def _telefone(v: Any) -> str:
    """Só dígitos, sem o 55 do país — o cartão guarda «99984512929»."""
    d = _digitos(v)
    if len(d) in (12, 13) and d.startswith("55"):
        d = d[2:]
    return d


def _endereco_em_linha(e: Any) -> str:
    if not isinstance(e, dict):
        return ""
    partes = [_texto(e.get("street")), _texto(e.get("number")), _texto(e.get("complement")),
              _texto(e.get("neighbourhood"))]
    cidade = "/".join(x for x in (_texto(e.get("city")), _texto(e.get("state"))) if x)
    return ", ".join(x for x in [*partes, cidade] if x)


def campos_do_cartao(ficha: dict) -> dict[str, str]:
    """A ficha do CCN nas colunas e nos formatos de `nt_cartoes`. Só o que veio."""
    f = ficha or {}
    sexo = {"Female": "F", "Male": "M"}.get(f.get("gender") or "", "")
    saida: dict[str, str] = {
        "nascimento": _data(f.get("dateOfBirth")),
        "sexo": sexo,
        "profissao": _texto(f.get("profession")),
        "estado_civil": ESTADO_CIVIL.get(f.get("civilStatus") or "", ""),
        "conjuge": _texto(f.get("spouseName")).upper(),
        "pai": _texto(f.get("fatherName")).upper(),
        "mae": _texto(f.get("motherName")).upper(),
        "email": _texto(f.get("email")).lower(),
    }
    nac = f.get("nationality") or ""
    if nac in BRASILEIROS and sexo:
        saida["nacionalidade"] = "BRASILEIRA" if sexo == "F" else "BRASILEIRO"
    elif nac == "Foreigner":
        saida["nacionalidade"] = _texto(f.get("nationalityStr") or f.get("nationalityCountryName")).upper()
    cidade, uf = _texto(f.get("birthCity")).upper(), _texto(f.get("birthState"))
    if cidade:
        saida["naturalidade"] = f"{cidade}/{uf}" if uf else cidade
    if (f.get("documentType") or "") == "IdCard":
        saida.update({"rg": _texto(f.get("documentNumber")),
                      "rg_orgao": _texto(f.get("documentIssuer")).upper(),
                      "rg_uf": _texto(f.get("documentIssuerState")),
                      "rg_emissao": _data(f.get("documentIssueDate"))})
    e = f.get("address") if isinstance(f.get("address"), dict) else {}
    saida.update({"endereco": _texto(e.get("street")).upper(),
                  "endereco_numero": _texto(e.get("number")),
                  "endereco_complemento": _texto(e.get("complement")).upper(),
                  "bairro": _texto(e.get("neighbourhood")).upper(),
                  "cidade": _texto(e.get("city")).upper(),
                  "uf": _texto(e.get("state")),
                  "cep": _digitos(e.get("zipCode"))})
    trabalho = _endereco_em_linha(f.get("workAddress"))
    if trabalho:
        saida["endereco_trabalho"] = trabalho.upper()
    fones = [p for p in (f.get("phones") or []) if isinstance(p, dict) and p.get("number")]
    moveis = sorted((p for p in fones if p.get("type") == "Mobile"),
                    key=lambda p: not (p.get("primaryMobilePhone") or p.get("isPrimary")))
    fixos = [p for p in fones if p.get("type") in ("Home", "Work")]
    if moveis:
        saida["celular"] = _telefone(moveis[0]["number"])
    if fixos:
        saida["telefone"] = _telefone(fixos[0]["number"])
    return {k: v for k, v in saida.items() if v}


ROTULOS = {
    "nascimento": "Nascimento", "sexo": "Sexo", "nacionalidade": "Nacionalidade",
    "naturalidade": "Naturalidade", "estado_civil": "Estado civil", "conjuge": "Cônjuge",
    "profissao": "Profissão", "pai": "Pai", "mae": "Mãe", "rg": "RG",
    "rg_orgao": "Órgão do RG", "rg_uf": "UF do RG", "rg_emissao": "Emissão do RG",
    "endereco": "Logradouro", "endereco_numero": "Número",
    "endereco_complemento": "Complemento", "bairro": "Bairro", "cidade": "Cidade",
    "uf": "UF", "cep": "CEP", "telefone": "Telefone", "celular": "Celular",
    "email": "E-mail", "endereco_trabalho": "Endereço de trabalho",
}


def ficha_para_a_tela(ficha: dict) -> dict:
    """A ficha inteira, legível, com os alertas separados. Só LÊ."""
    f = ficha or {}
    notary = f.get("notary") if isinstance(f.get("notary"), dict) else {}
    alertas = []
    if f.get("politicallyExposed"):
        alertas.append("o CCN marca esta pessoa como POLITICAMENTE EXPOSTA")
    if f.get("investigatedOrAccusedOfTerrorism"):
        alertas.append("o CCN marca esta pessoa como INVESTIGADA OU ACUSADA DE TERRORISMO")
    if f.get("blocked"):
        alertas.append("o cadastro está BLOQUEADO no CCN")
    linhas = [(ROTULOS[k], v) for k, v in campos_do_cartao(f).items()]
    if f.get("documentType") and f.get("documentType") != "IdCard":
        linhas.append(("Documento", f"{DOCUMENTO.get(f['documentType'], f['documentType'])} "
                                    f"{_texto(f.get('documentNumber'))}".strip()))
    if f.get("maritalPropertySystem"):
        linhas.append(("Regime de bens", REGIME.get(f["maritalPropertySystem"], f["maritalPropertySystem"])))
    if f.get("spouseCpf"):
        linhas.append(("CPF do cônjuge", _texto(f["spouseCpf"])))
    if f.get("driversLicenseNumber"):
        linhas.append(("CNH", f"{_texto(f.get('driversLicenseNumber'))} — categoria "
                              f"{_texto(f.get('driversLicenseCategory')) or '?'}, validade "
                              f"{_data(f.get('driversLicenseExpirationDate')) or '?'}"))
    if f.get("numberFicha") or f.get("dateFicha"):
        linhas.append(("Ficha no cartório de origem",
                       f"nº {_texto(f.get('numberFicha')) or '?'} de {_data(f.get('dateFicha')) or '?'}"))
    if f.get("observation"):
        linhas.append(("Observação", _texto(f["observation"])))
    arquivos = [f"{a.get('type') or 'Arquivo'}: {a.get('name') or a.get('contentType')}"
                for a in (f.get("files") or []) if isinstance(a, dict)]
    return {
        "nome": _texto(f.get("name")),
        "cartorio": _texto(notary.get("name") or f.get("subscriptionName")),
        "cns": notary.get("cns"),
        "criado_em": _data(f.get("dateCreated")),
        "face_verificada": bool(f.get("faceVerified")),
        "digitais": len([d for d in (f.get("fingerPrints") or []) if isinstance(d, dict)]),
        "arquivos": arquivos,
        "linhas": linhas,
        "alertas": alertas,
    }


# ------------------------------------------------------------- o cartão

def _vazio(v: Any) -> bool:
    return v is None or str(v).strip() == ""


def cartao_do_cpf(con: sqlite3.Connection, cpf: str) -> dict | None:
    con.row_factory = sqlite3.Row
    r = con.execute("SELECT * FROM nt_cartoes WHERE documento=? ORDER BY ativo DESC, id DESC LIMIT 1",
                    (cpf,)).fetchone()
    return dict(r) if r else None


def proposta(con: sqlite3.Connection, consulta: dict, indice: int = 0) -> dict:
    """O que a ficha `indice` acrescentaria ao cartão do CPF. Só LÊ.

    `preencher`: campos vazios no cartão que a ficha tem.
    `diferentes`: campos que os dois têm, com valor diferente — não se trocam.
    """
    fichas = consulta.get("registros") or []
    if not fichas or not (0 <= indice < len(fichas)):
        return {"cartao": None, "preencher": [], "diferentes": [], "motivo": "não há ficha para usar"}
    cartao = cartao_do_cpf(con, consulta["cpf"])
    if cartao is None:
        return {"cartao": None, "preencher": [], "diferentes": [],
                "motivo": "não há cartão de firma com este CPF nesta casa — e abrir cartão é ato, "
                          "com selo, que não se faz daqui"}
    preencher, diferentes = [], []
    for coluna, novo in campos_do_cartao(fichas[indice]).items():
        atual = cartao.get(coluna)
        if _vazio(atual):
            preencher.append({"coluna": coluna, "rotulo": ROTULOS[coluna], "valor": novo})
        elif _texto(atual).upper() != _texto(novo).upper():
            diferentes.append({"coluna": coluna, "rotulo": ROTULOS[coluna],
                               "no_cartao": atual, "no_ccn": novo})
    return {"cartao": cartao, "preencher": preencher, "diferentes": diferentes, "motivo": None}


def aplicar(con: sqlite3.Connection, consulta: dict, *, indice: int, usuario: str,
            agora: str) -> dict:
    """Completa o cartão com o que ele não tem. ESCREVE — só campo vazio.

    A conferência de vazio se faz DE NOVO dentro da transação, na própria
    instrução (`WHERE coluna IS NULL OR coluna=''`): se alguém preencheu o
    campo entre a tela e o clique, o que a pessoa digitou fica.
    """
    p = proposta(con, consulta, indice)
    if p["cartao"] is None:
        raise ConsultaError(p["motivo"] or "não há cartão para completar")
    if not p["preencher"]:
        raise ConsultaError("o cartão já tem tudo o que a ficha do CCN traz — nada a completar")
    cartao_id = p["cartao"]["id"]
    entrou: dict[str, str] = {}
    for item in p["preencher"]:
        col = item["coluna"]
        if col not in ROTULOS:                     # coluna vem de lista fixa, nunca da tela
            continue
        cur = con.execute(f"UPDATE nt_cartoes SET {col}=? WHERE id=? AND ({col} IS NULL OR {col}='')",
                          (item["valor"], cartao_id))
        if cur.rowcount:
            entrou[col] = item["valor"]
    if entrou:
        con.execute("UPDATE nt_cartoes SET atualizado_em=?, atualizado_por=? WHERE id=?",
                    (agora, usuario, cartao_id))
    con.execute("""UPDATE nt_ccn_consultas SET cartao_id=?, aplicada_em=?, aplicada_por=?,
                          aplicados_json=? WHERE id=?""",
                (cartao_id, agora, usuario, json.dumps(entrou, ensure_ascii=False), consulta["id"]))
    return {"cartao_id": cartao_id, "campos": entrou}
