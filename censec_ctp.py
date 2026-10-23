"""
A CTP DAS ESCRITURAS PELA API DA CENSEC — 22/10/2026.

SÃO DUAS CTPs, E ESTA É A DO TABELIONATO
    Palavra do oficial em 22/10/2026: «existem duas CTPs. Da ONR e da
    CENSEC». O contrato confirma: na CENSEC, `Doi.CtpData.tipoAto` só admite
    `Desconhecido | Escritura | Procuracao`. A CTP do Registro de Imóveis vai
    pela ONR (Ofício Eletrônico, «o mesmo arquivo JSON válido, utilizado no
    site da Receita Federal» — MANUAL-CTP da ONR), e é do Agente RI.

DE ONDE VEM CADA COISA
    O registro é o da DOI da escritura, `notas_doi.declaracao_da_escritura`: a
    CTP e a DOI declaram o MESMO negócio, e dois montadores divergiriam. O que
    muda é a LÍNGUA: o DOI-Web fala por códigos (`"11"`, `"3"`), e a API da
    CENSEC fala pelo NOME do enum (`CompraEVenda`, `Rural`) e quer as datas em
    date-time. A tradução mora aqui, e o contrato vai junto
    (`censec_ctp_esquema.json`, os `Doi.*` do Swagger 2.71.2 RTM, baixado em
    22/10/2026) para conferir antes da rede.

QUANDO VAI — A CONFERIR COM A CENSEC
    O portal mostra a CTP por MÊS («Setembro de 2026») e a carga da API exige
    uma QUINZENA. O sistema manda a CTP na carga da 2ª quinzena — a que fecha
    o mês —, com as escrituras do mês inteiro. Escritura já aceita numa
    remessa de CTP não vai de novo: a CEP pode ser reenviada à vontade, mas
    a CTP repetida seria a mesma transação declarada duas vezes à prefeitura.

A API NÃO FECHA O MÊS. O fechamento (com ou sem atos) é no portal, ou pelo
    «Fechamento automático» que o oficial liga lá.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from bd_nativo import banco
import notas_doi as NDOI

ESQUEMA = json.loads(Path(__file__).with_name("censec_ctp_esquema.json")
                     .read_text(encoding="utf-8"))["schemas"]

CENTRAL = "CTP"

# ------------------------------------------------- código do DOI-Web -> enum da CENSEC
# Os dois lados medidos: o código é o do layout do DOI-Web (`ri_doi_layout.json`
# e `ri_ctp`), o nome é o enum de `Doi.CtpData` no Swagger da CENSEC. Onde o
# nome não bate um a um, fica o que o rótulo da tabela da Receita diz.
TIPO_SERVICO = {"1": "Notarial", "2": "RegistroImoveis", "3": "RegistroTitulosDocumentos"}
TIPO_ATO = {"1": "Escritura", "2": "Procuracao"}
# O layout do DOI-Web só publica o código "0" (Original); os de Retificadora e
# Canceladora não estão medidos, e por isso não se traduzem.
TIPO_DECLARACAO = {"0": "Original"}
TIPO_OPERACAO = {
    "11": "CompraEVenda", "13": "Permuta", "15": "Adjudicacao",
    "19": "DacaoEmPagamento", "21": "DistratoDeNegocio",
    "31": "ProcuracaoEmCausaPropria", "33": "PromessaDeCompraEVenda",
    "35": "PromessaDeCessaoDeDireitos", "37": "CessaoDeDireitos", "39": "Outros",
    "41": "AlienacaoPorIniciativaParticularOuLeilaoJudicial",
    "45": "IncorporacaoELoteamento", "47": "IntegralizacaoSubscricaoDeCapital",
    "55": "DoacaoEmAdiantamentoDaLegitima", "56": "Aforamento",
    "57": "CasamentoEmComunhaoUniversalDeBens", "58": "CisaoTotalOuParcial",
    "59": "CompraEVendaDeImovelGravadoPorEnfiteuse",
    "60": "ConcessaoDeDireitoRealDeUsoCDRU",
    "61": "ConcessaoDeUsoEspecialParaFinsDeMoradiaCUEM",
    "62": "ConsolidacaoDaPropriedadeEmNomeDoFiduciario",
    "63": "DesapropriacaoParaFinsDeReformaAgraria",
    "64": "DesapropriacaoExcetoParaReformaAgraria", "65": "DireitoDeLaje",
    "66": "DireitoDeSuperficie", "67": "DoacaoExcetoEmAdiantamentoDeLegitima",
    "68": "Incorporacao", "69": "Inventario",
    "70": "PartSeparacaoDivorcioUniaoEstavel",
    "71": "RetornoDeCapitalProprioNaExtincaoDePessoaJuridica",
    "72": "RetornoDeCapitalProprioExcetoNaExtincaoDePessoaJuridica",
    "73": "TituloDeDominioTD", "74": "Usucapiao",
}
FORMA_PAGAMENTO = {"5": "QuitadoAVista", "7": "APrazo", "9": "NaoSeAplica",
                   "10": "QuitadoAPrazo", "11": "QuitadoSemInformacaoDaFormaDePagamento"}
DESTINACAO = {"1": "Urbano", "3": "Rural"}
TIPO_PARTE = {"1": "Percentual", "2": "HaM2"}
TIPO_IMOVEL = {"15": "Loja", "31": "Galpao", "65": "Apartamento", "67": "Casa",
               "69": "FazendaSitioChacara", "71": "TerrenoFracao", "73": "SalaLoja",
               "89": "Outros", "90": "Sala", "91": "ConjuntoDeSalas", "92": "Sobreloja",
               "93": "VagaDeGaragem", "94": "Laje", "95": "Estacionamento",
               "96": "Barraco"}
REGIME_BENS = {"1": "SeparacaoDeBens", "2": "ComunhaoParcialDeBens",
               "3": "ComunhaoUniversalDeBens", "4": "ParticipacaoFinalNosAquestos",
               "5": "SeparacaoObrigatoria"}
MOTIVO_SEM_NI = {"1": "SemCPFCNPJDecisaoJudicial", "2": "NaoConstaNoDocumento"}

_CAMPOS_ENUM = {"tipoServico": TIPO_SERVICO, "tipoAto": TIPO_ATO,
                "tipoDeclaracao": TIPO_DECLARACAO,
                "tipoOperacaoImobiliaria": TIPO_OPERACAO,
                "formaPagamento": FORMA_PAGAMENTO, "destinacao": DESTINACAO,
                "tipoParteTransacionada": TIPO_PARTE, "tipoImovel": TIPO_IMOVEL}
_CAMPOS_DATA = ("dataLavraturaRegistroAverbacao", "dataNegocioJuridico",
                "mesAnoUltimaParcela")


def _data_hora(valor: Any) -> Any:
    s = str(valor or "").strip()
    return f"{s[:10]}T00:00:00" if re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", s) else valor


def _parte(p: dict) -> dict:
    p = dict(p)
    if p.get("regimeBens") is not None:
        p["regimeBens"] = REGIME_BENS.get(str(p["regimeBens"]), p["regimeBens"])
    if p.get("motivoNaoIdentificacaoNi") is not None:
        p["motivoNaoIdentificacaoNi"] = MOTIVO_SEM_NI.get(
            str(p["motivoNaoIdentificacaoNi"]), p["motivoNaoIdentificacaoNi"])
    return p


def item_da_declaracao(reg: dict) -> dict:
    """A declaração do DOI-Web (códigos) na língua da API da CENSEC (enums)."""
    # Campo opcional em branco NÃO vai: a CENSEC aceita a ausência, e recusa o
    # texto vazio onde o contrato pede tamanho mínimo (o `cep` tem 8). Medido no
    # teste da escritura urbana sem CEP, que o DOI-Web aceita com "".
    obrig = set(ESQUEMA["Doi.CtpData"].get("required", []))
    item = {k: v for k, v in reg.items() if k in ESQUEMA["Doi.CtpData"]["properties"]
            and not (v == "" and k not in obrig)}
    for campo, tabela in _CAMPOS_ENUM.items():
        if item.get(campo) is not None:
            item[campo] = tabela.get(str(item[campo]), item[campo])
    for campo in _CAMPOS_DATA:
        if item.get(campo):
            item[campo] = _data_hora(item[campo])
    for lado in ("alienantes", "adquirentes"):
        item[lado] = [_parte(p) for p in item.get(lado) or []]
    return item


# ------------------------------------------------- conferência contra o contrato

def _conferir(obj: dict, nome: str, onde: str, erros: list[str]) -> None:
    schema = ESQUEMA[nome]
    props = schema.get("properties", {})
    for k in schema.get("required", []):
        if obj.get(k) is None:
            erros.append(f"{onde}: falta {k}")
    for k, v in obj.items():
        if k not in props:
            erros.append(f"{onde}: {k} não existe no contrato da CENSEC")
            continue
        if v is None:
            continue
        regra = props[k]
        if "enum" in regra and v not in regra["enum"]:
            erros.append(f"{onde}: {k} = {v!r} fora do vocabulário da CENSEC")
        if isinstance(v, str):
            if regra.get("maxLength") and len(v) > regra["maxLength"]:
                erros.append(f"{onde}: {k} passa de {regra['maxLength']} caracteres")
            if regra.get("minLength") and len(v) < regra["minLength"]:
                erros.append(f"{onde}: {k} tem menos de {regra['minLength']} caracteres")
            if regra.get("pattern") and not re.search(regra["pattern"], v):
                erros.append(f"{onde}: {k} fora do formato da CENSEC")
        if regra.get("type") == "array":
            ref = (regra.get("items") or {}).get("$ref", "").split("/")[-1]
            for i, el in enumerate(v):
                if ref in ESQUEMA:
                    _conferir(el, ref, f"{onde}.{k}[{i + 1}]", erros)


def conferir(item: dict, onde: str = "CTP") -> list[str]:
    """O item contra `Doi.CtpData`. Lista vazia: a CENSEC aceitaria a forma."""
    erros: list[str] = []
    _conferir(item, "Doi.CtpData", onde, erros)
    return erros


# ------------------------------------------------- as escrituras do mês

def _ibge(bd) -> str:
    def cfg(chave):
        return str(bd.valor("SELECT value FROM settings WHERE key = %s", (chave,)) or "").strip()
    explicito = cfg("ri_codigo_ibge")
    if explicito:
        return explicito
    uf, mun = cfg("ibge_uf"), cfg("ibge_municipio")
    return uf.zfill(2) + mun.zfill(5) if uf and mun else ""


def declaracoes_do_mes(con: Any, ano: int, mes: int, cns: str) -> dict:
    """As escrituras com imóvel lavradas no mês, separadas em aptas e impedidas.

    Não grava nada. Fica de fora a escritura que já entrou numa remessa de
    CTP aceita (ENVIADA ou CONFIRMADA); a rejeitada volta, para reenviar.
    """
    bd = banco(con)
    primeiro = f"{ano:04d}-{mes:02d}-01"
    seguinte = f"{ano + 1:04d}-01-01" if mes == 12 else f"{ano:04d}-{mes + 1:02d}-01"
    ibge = _ibge(bd)
    aptos, impedidos = [], []
    for linha in bd.ler(
            """SELECT a.* FROM nt_atos a
                WHERE a.tipo = 'ESCRITURA' AND a.com_imovel = 1
                  AND a.situacao = 'LAVRADO'
                  AND a.data >= %s AND a.data < %s
                  AND NOT EXISTS (
                      SELECT 1 FROM nt_remessa_itens i
                        JOIN nt_remessas r ON r.id = i.remessa_id
                       WHERE i.ato_id = a.id AND r.central = %s
                         AND i.situacao IN ('ENVIADA', 'CONFIRMADA'))
                ORDER BY a.data, a.id""", (primeiro, seguinte, CENTRAL)):
        ato = dict(linha)
        partes = bd.ler("SELECT * FROM nt_ato_partes WHERE ato_id = %s ORDER BY id",
                        (ato["id"],))
        reg, problemas = NDOI.declaracao_da_escritura(ato, partes, cns, ibge)
        item = None
        if not problemas:
            item = item_da_declaracao(reg)
            problemas = [{"campo": "censec", "motivo": e} for e in conferir(
                item, f"livro {ato.get('livro')}, fl. {ato.get('folha')}")]
        if problemas:
            impedidos.append({"ato": ato, "problemas": problemas})
        else:
            aptos.append({"ato": ato, "linha": item})
    return {"aptos": aptos, "impedidos": impedidos}
