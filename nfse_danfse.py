"""O DANFSe v2.0 — o papel da NFS-e, montado aqui a partir do XML dela.

POR QUE EXISTE (24/10/2026)
    Até aqui o PDF da nota vinha da API do ADN (`GET /danfse/{chave}`). A Nota
    Técnica SE/CGNFS-e nº 008, versão 1.0, de 05/05/2026, suspendeu essa API
    em **1º de julho de 2026** e passou a geração do DANFSe aos sistemas de
    emissão, com um modelo único — o «DANFSe v2.0». Desde então o botão
    «DANFSe (PDF)» da casa pedia um documento que o emissor não entrega mais.

O QUE ESTE MÓDULO FAZ, E O QUE NÃO FAZ
    Lê o XML da NFS-e que a Sefin devolveu (`nfse_notas.xml_nfse`) e monta o
    HTML do DANFSe com a posição, o tamanho e a fonte que a NT 008 dá campo a
    campo (item 2.4.5, em centímetros). O PDF sai do mesmo HTML pelo Chrome
    sem rede (`impressao_pdf.pdf_de_html_chrome`), que é o caminho que a casa
    já usa para imprimir HTML. Não grava nada e não fala com o emissor.

    **SÓ SE IMPRIME O QUE ESTÁ NO XML** (item 2.1: «Não poderão ser impressas
    informações que não constem do arquivo da NFS-e»). Campo sem informação
    sai com um traço (nota 12). As duas exceções são as que a própria NT
    manda: a marca d'água «CANCELADA» (item 2.5.1 — o cancelamento é um
    evento à parte, e o XML da nota não muda) e o nome do município pelo
    código do IBGE (as notas da tabela mandam «utilizar a descrição destes
    códigos»), que vem de `ib_municipios` por quem chama.

    As supressões que a NT permite e a casa usa: o destinatário (quando é o
    próprio tomador, item 2.3.2), o intermediário (não identificado, 2.3.1) e
    o canhoto (bloco opcional, 2.3.3). O espaço que sobra vai para a
    descrição do serviço e as informações complementares, como a NT pede.

O QUE CONFERIR
    O modelo do Anexo I da NT é uma figura; a disposição aqui segue a tabela
    de posições do item 2.4.5. Antes de entregar o primeiro DANFSe a um
    cliente, comparar uma página impressa com a figura da NT.
"""
from __future__ import annotations

import html
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from lxml import etree

NS = "http://www.sped.fazenda.gov.br/nfse"
VERSAO_DO_MODELO = "DANFSe v2.0"
NOTA_TECNICA = "NT SE/CGNFS-e nº 008, v1.0, de 05/05/2026"
URL_CONSULTA = "https://www.nfse.gov.br/ConsultaPublica/?tpc=1&chave="
LOGO = Path(__file__).resolve().parent / "static" / "nfse_logo.png"
TRACO = "-"

# As descrições das opções do leiaute (XSD 1.01, tiposSimples), que a NT
# manda imprimir no lugar do número.
AMBIENTE_GERADOR = {"1": "Prefeitura", "2": "Sistema Nacional da NFS-e"}
TIPO_AMBIENTE = {"1": "Produção", "2": "Homologação"}
EMITENTE = {"1": "Prestador", "2": "Tomador", "3": "Intermediário"}
SITUACAO = {"100": "NFS-e Gerada", "102": "NFS-e de Decisão Judicial",
            "103": "NFS-e Avulsa", "107": "NFS-e MEI"}
FINALIDADE = {"0": "NFS-e regular"}
SIMPLES = {"1": "Não Optante", "2": "Optante - MEI", "3": "Optante - ME/EPP"}
APURACAO_SN = {
    "1": "Regime de apuração dos tributos federais e municipal pelo Simples Nacional",
    "2": "Tributos federais pelo SN e ISSQN por fora do SN",
    "3": "Tributos federais e municipal por fora do SN",
}
TRIBUTACAO_ISSQN = {"1": "Operação Tributável", "2": "Imunidade",
                    "3": "Exportação de Serviço", "4": "Não Incidência"}
REGIME_ESPECIAL = {"0": "Nenhum", "1": "Ato Cooperado", "2": "Estimativa",
                   "3": "Microempresa Municipal", "4": "Notário ou Registrador",
                   "5": "Profissional Autônomo", "6": "Sociedade de Profissionais",
                   "9": "Outros"}
IMUNIDADE = {"0": "Imunidade (tipo não informado)",
             "1": "Patrimônio, renda ou serviços, uns dos outros",
             "2": "Templos de qualquer culto",
             "3": "Partidos, sindicatos, educação e assistência social",
             "4": "Livros, jornais, periódicos e o papel destinado à sua impressão",
             "5": "Fonogramas e videofonogramas musicais"}
SUSPENSAO = {"1": "Exigibilidade Suspensa por Decisão Judicial",
             "2": "Exigibilidade Suspensa por Processo Administrativo"}
BENEFICIO = {"1": "Isenção", "2": "Redução da BC em %", "3": "Redução da BC em R$",
             "4": "Alíquota Diferenciada"}
RETENCAO_ISSQN = {"1": "Não Retido", "2": "Retido pelo Tomador",
                  "3": "Retido pelo Intermediário"}
RETENCAO_PIS = {"0": "PIS/COFINS/CSLL Não Retidos", "1": "PIS/COFINS Retidos",
                "2": "PIS/COFINS Não Retidos", "3": "PIS/COFINS/CSLL Retidos",
                "4": "PIS/COFINS Retidos, CSLL Não Retido",
                "5": "PIS Retido, COFINS/CSLL Não Retido",
                "6": "COFINS Retido, PIS/CSLL Não Retido",
                "7": "PIS Não Retido, COFINS/CSLL Retidos",
                "8": "PIS/COFINS Não Retidos, CSLL Retido",
                "9": "COFINS Não Retido, PIS/CSLL Retidos"}

NomeDoMunicipio = Callable[[str], tuple[str, str]]


class DanfseError(ValueError):
    """O XML não serve para montar o DANFSe, com a frase para a tela."""


# ------------------------------------------------------------ a leitura do XML

def _no(raiz, caminho: str):
    el = raiz
    for parte in caminho.split("/"):
        if el is None:
            return None
        el = el.find(f"{{{NS}}}{parte}")
    return el


def _txt(raiz, caminho: str) -> str:
    el = _no(raiz, caminho)
    return (el.text or "").strip() if el is not None and el.text else ""


def _primeiro(raiz, *caminhos: str) -> str:
    for c in caminhos:
        v = _txt(raiz, c)
        if v:
            return v
    return ""


def ler_nfse(xml: bytes | str) -> etree._Element:
    """O `infNFSe` do XML da nota. Recusa o que não é NFS-e."""
    if not xml:
        raise DanfseError("Esta nota não tem o XML da NFS-e gravado; consulte-a no "
                          "emissor antes de imprimir.")
    try:
        raiz = etree.fromstring(xml.encode("utf-8") if isinstance(xml, str) else xml)
    except etree.XMLSyntaxError as erro:
        raise DanfseError("O XML da NFS-e gravado está ilegível.") from erro
    inf = raiz if raiz.tag == f"{{{NS}}}infNFSe" else raiz.find(f".//{{{NS}}}infNFSe")
    if inf is None:
        raise DanfseError("O XML gravado não é de uma NFS-e (falta o infNFSe).")
    return inf


# ------------------------------------------------------------- as formatações

def _digitos(v: Any) -> str:
    return re.sub(r"\D", "", str(v or ""))


def documento(cnpj: str = "", cpf: str = "", nif: str = "") -> str:
    d = _digitos(cnpj)
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    d = _digitos(cpf)
    if len(d) == 11:
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    return nif.strip() or TRACO


def cep(v: str) -> str:
    d = _digitos(v)
    return f"{d[:2]}.{d[2:5]}-{d[5:]}" if len(d) == 8 else (v or "")


def dinheiro(v: str) -> str:
    if not str(v or "").strip():
        return TRACO
    try:
        n = float(v)
    except ValueError:
        return str(v)
    texto = f"{abs(n):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{'-' if n < 0 else ''}R$ {texto}"


def percentual(v: str) -> str:
    if not str(v or "").strip():
        return TRACO
    try:
        return f"{float(v):.2f}".replace(".", ",") + "%"
    except ValueError:
        return str(v)


def data_hora(v: str) -> str:
    """«2026-10-24T10:00:00-03:00» → «24/10/2026 10:00:00», no fuso do XML."""
    if not v:
        return TRACO
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00")).strftime("%d/%m/%Y %H:%M:%S")
    except ValueError:
        return v


def data(v: str) -> str:
    if not v:
        return TRACO
    try:
        return datetime.strptime(v[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return v


def reticencias(v: str, limite: int) -> str:
    """O corte da NT: passou do limite, corta e põe «...»."""
    v = " ".join(str(v or "").split())
    return v if len(v) <= limite else v[:limite].rstrip() + "..."


def _ou_traco(v: str) -> str:
    return v if str(v or "").strip() else TRACO


def _descricao(tabela: Mapping[str, str], codigo: str, limite: int = 37) -> str:
    if not codigo:
        return TRACO
    return reticencias(tabela.get(codigo, codigo), limite)


def codigo_tributacao(nac: str, mun: str) -> str:
    d = _digitos(nac)
    texto = f"{d[:2]}.{d[2:4]}.{d[4:]}" if len(d) == 6 else (nac or TRACO)
    return f"{texto} / {mun}" if mun else texto


def nbs(v: str) -> str:
    d = _digitos(v)
    return f"{d[0]}.{d[1:5]}.{d[5:7]}.{d[7:]}" if len(d) == 9 else _ou_traco(v)


# --------------------------------------------------------------- os blocos

def _nome_mun(nome_do_municipio: NomeDoMunicipio | None, codigo: str) -> str:
    if not codigo:
        return TRACO
    if nome_do_municipio is None:
        return codigo
    nome, uf = nome_do_municipio(codigo)
    return f"{nome} / {uf}" if nome else codigo


def _pessoa(inf, base: str, nome_do_municipio, *, emit=None) -> dict[str, str] | None:
    """Os campos de um bloco de pessoa (prestador, tomador...), ou None."""
    p = _no(inf, base)
    if p is None:
        return None
    end = "end"
    cmun = _txt(p, f"{end}/endNac/cMun")
    cep_ = _txt(p, f"{end}/endNac/CEP")
    ext = _no(p, f"{end}/endExt")
    if ext is not None:
        municipio = _ou_traco(_txt(ext, "xCidade"))
        ibge_cep = _ou_traco(_txt(ext, "cEndPost"))
    else:
        municipio = _nome_mun(nome_do_municipio, cmun)
        ibge_cep = f"{cmun} / {cep(cep_)}" if cmun else TRACO
    endereco = ", ".join(x for x in (_txt(p, f"{end}/xLgr"), _txt(p, f"{end}/nro"),
                                     _txt(p, f"{end}/xCpl"), _txt(p, f"{end}/xBairro")) if x)
    campos = {
        "doc": documento(_txt(p, "CNPJ"), _txt(p, "CPF"), _txt(p, "NIF")),
        "im": _ou_traco(_txt(p, "IM")),
        "fone": _ou_traco(_txt(p, "fone")),
        "nome": reticencias(_txt(p, "xNome"), 77) or TRACO,
        "municipio": reticencias(municipio, 37),
        "ibge_cep": ibge_cep,
        "endereco": reticencias(endereco, 77) or TRACO,
        "email": _ou_traco(_txt(p, "email")),
    }
    # O prestador da DPS desta casa não repete nome e endereço (o leiaute os
    # deixa opcionais); quando o emitente É o prestador, o mesmo dado está em
    # `emit`, do mesmo XML — e a NT manda não deixar em branco o que a nota diz.
    if emit is not None:
        if campos["nome"] == TRACO:
            campos["nome"] = reticencias(_txt(emit, "xNome"), 77) or TRACO
        if campos["im"] == TRACO:
            campos["im"] = _ou_traco(_txt(emit, "IM"))
        if campos["fone"] == TRACO:
            campos["fone"] = _ou_traco(_txt(emit, "fone"))
        if campos["email"] == TRACO:
            campos["email"] = _ou_traco(_txt(emit, "email"))
        if campos["endereco"] == TRACO and _no(emit, "enderNac") is not None:
            e = _no(emit, "enderNac")
            campos["endereco"] = reticencias(", ".join(x for x in (
                _txt(e, "xLgr"), _txt(e, "nro"), _txt(e, "xCpl"), _txt(e, "xBairro")) if x),
                77) or TRACO
            cm = _txt(e, "cMun")
            uf = _txt(e, "UF")
            nome = _nome_mun(nome_do_municipio, cm)
            campos["municipio"] = reticencias(nome if " / " in nome else f"{nome} / {uf}", 37)
            campos["ibge_cep"] = f"{cm} / {cep(_txt(e, 'CEP'))}" if cm else TRACO
    return campos


def dados(xml: bytes | str, *, nome_do_municipio: NomeDoMunicipio | None = None) -> dict:
    """Tudo o que o DANFSe imprime, já formatado. Só LÊ o XML."""
    inf = ler_nfse(xml)
    dps = "DPS/infDPS"
    emit = _no(inf, "emit")
    tp_emit = _txt(inf, f"{dps}/tpEmit")
    ibs = _no(inf, "IBSCBS")
    rtc_dps = _no(inf, f"{dps}/IBSCBS")
    uf_emit = _txt(inf, "emit/enderNac/UF")
    chave = _digitos(inf.get("Id") or "")
    trib_nac = _txt(inf, f"{dps}/serv/cServ/cTribNac")
    tot = _no(inf, f"{dps}/valores/trib/totTrib")
    totais = TRACO
    if tot is not None and _no(tot, "vTotTrib") is not None:
        v = _no(tot, "vTotTrib")
        totais = (f"Federais: {dinheiro(_txt(v, 'vTotTribFed'))} ; Estaduais: "
                  f"{dinheiro(_txt(v, 'vTotTribEst'))} ; Municipais: {dinheiro(_txt(v, 'vTotTribMun'))}")
    elif tot is not None and _no(tot, "pTotTrib") is not None:
        p = _no(tot, "pTotTrib")
        totais = (f"Federais: {percentual(_txt(p, 'pTotTribFed'))} ; Estaduais: "
                  f"{percentual(_txt(p, 'pTotTribEst'))} ; Municipais: {percentual(_txt(p, 'pTotTribMun'))}")
    else:
        totais = f"Federais: {TRACO} ; Estaduais: {TRACO} ; Municipais: {TRACO}"
    complementares = [
        ("Inf. Cont.:", _txt(inf, f"{dps}/serv/infoCompl/xInfComp")),
        ("NFS-e Subst.:", _txt(inf, f"{dps}/subst/chSubstda")),
        ("Doc. Ref.:", _txt(inf, f"{dps}/serv/infoCompl/docRef")),
        ("Cod. Obra:", _txt(inf, f"{dps}/serv/obra/cObra")),
        ("Insc. Imob.:", _primeiro(inf, f"{dps}/serv/obra/inscImobFisc",
                                   f"{dps}/IBSCBS/imovel/inscImobFisc")),
        ("Cod. Evt.:", _txt(inf, f"{dps}/serv/atvEvento/idAtvEvt")),
        ("Doc. Tec.:", _txt(inf, f"{dps}/serv/infoCompl/idDocTec")),
        ("Núm. Ped.:", _txt(inf, f"{dps}/serv/infoCompl/xPed")),
        ("Item Ped.:", "; ".join(
            (e.text or "").strip() for e in inf.iterfind(
                f"{{{NS}}}DPS/{{{NS}}}infDPS/{{{NS}}}serv/{{{NS}}}infoCompl/"
                f"{{{NS}}}gItemPed/{{{NS}}}xItemPed") if e.text)),
        ("Inf. A. T. Mun.:", _txt(inf, "xOutInf")),
    ]
    info = " | ".join(f"{r} {v}" for r, v in complementares if v)
    exclusoes = 0.0
    for caminho in (f"{dps}/valores/vDescCondIncond/vDescIncond",
                    "IBSCBS/valores/vCalcReeRepRes", "valores/vISSQN",
                    f"{dps}/valores/trib/tribFed/piscofins/vPis",
                    f"{dps}/valores/trib/tribFed/piscofins/vCofins"):
        try:
            exclusoes += float(_txt(inf, caminho) or 0)
        except ValueError:
            pass
    vibs = _txt(inf, "IBSCBS/totCIBS/gIBS/vIBSTot")
    vcbs = _txt(inf, "IBSCBS/totCIBS/gCBS/vCBS")
    total_ibscbs = TRACO
    if vibs or vcbs:
        total_ibscbs = dinheiro(str(float(vibs or 0) + float(vcbs or 0)))
    loc_inc = TRACO
    if ibs is not None:
        nome = _nome_mun(nome_do_municipio, _txt(ibs, "cLocalidadeIncid"))
        if " / " not in nome:
            nome = _txt(ibs, "xLocalidadeIncid") or nome
        loc_inc = " / ".join(x for x in (_txt(rtc_dps, "cIndOp") if rtc_dps is not None else "",
                                         _txt(ibs, "cLocalidadeIncid"), nome) if x)
    elif rtc_dps is not None:
        loc_inc = _txt(rtc_dps, "cIndOp") or TRACO
    red = [percentual(_txt(inf, f"IBSCBS/valores/{g}")) for g in
           ("uf/pRedAliqUF", "mun/pRedAliqMun", "fed/pRedAliqCBS")]
    pais_prest = _txt(inf, f"{dps}/serv/locPrest/cPaisPrestacao") or "BR"
    pais_inc = _txt(inf, f"{dps}/valores/trib/tribMun/cPaisResult") or "BR"
    nome_emit_mun = _txt(inf, "xLocEmi")
    return {
        "ambiente": _txt(inf, f"{dps}/tpAmb"),
        "cabecalho": {
            # Nota da NT: não exibir o município quando o item do código de
            # tributação nacional for 99.
            "municipio": ("" if trib_nac.startswith("99")
                          else f"Município: {nome_emit_mun} / {uf_emit}".strip(" /")),
            "ambiente_gerador": _descricao(AMBIENTE_GERADOR, _txt(inf, "ambGer"), 60),
            "tipo_ambiente": _descricao(TIPO_AMBIENTE, _txt(inf, f"{dps}/tpAmb"), 60),
        },
        "chave": chave or TRACO,
        "url_consulta": URL_CONSULTA + chave,
        "nota": {
            "numero": _ou_traco(_txt(inf, "nNFSe")),
            "competencia": data(_txt(inf, f"{dps}/dCompet")),
            "emissao": data_hora(_txt(inf, "dhProc")),
            "dps_numero": _ou_traco(_txt(inf, f"{dps}/nDPS")),
            "dps_serie": _ou_traco(_txt(inf, f"{dps}/serie")),
            "dps_emissao": data_hora(_txt(inf, f"{dps}/dhEmi")),
            "emitente": _descricao(EMITENTE, tp_emit),
            "situacao": _descricao(SITUACAO, _txt(inf, "cStat")),
            "finalidade": _descricao(FINALIDADE, _txt(inf, f"{dps}/IBSCBS/finNFSe")),
        },
        "prestador": _pessoa(inf, f"{dps}/prest", nome_do_municipio,
                             emit=emit if tp_emit in ("", "1") else None),
        "simples": _descricao(SIMPLES, _txt(inf, f"{dps}/prest/regTrib/opSimpNac")),
        "apuracao_sn": _descricao(APURACAO_SN, _txt(inf, f"{dps}/prest/regTrib/regApTribSN"), 77),
        "tomador": _pessoa(inf, f"{dps}/toma", nome_do_municipio),
        "destinatario_proprio": (rtc_dps is not None
                                 and _txt(rtc_dps, "indDest") == "0"),
        "servico": {
            "codigo": codigo_tributacao(trib_nac, _txt(inf, f"{dps}/serv/cServ/cTribMun")),
            "nbs": nbs(_txt(inf, f"{dps}/serv/cServ/cNBS")),
            "local": reticencias(f"{_txt(inf, 'xLocPrestacao')} / {pais_prest}"
                                 if _txt(inf, "xLocPrestacao") else TRACO, 42),
            "descricao_codigo": reticencias(_primeiro(inf, "xTribMun", "xTribNac"), 167),
            "descricao": reticencias(_txt(inf, f"{dps}/serv/cServ/xDescServ"), 1297) or TRACO,
        },
        "issqn": {
            "tipo": _descricao(TRIBUTACAO_ISSQN, _txt(inf, f"{dps}/valores/trib/tribMun/tribISSQN")),
            "incidencia": reticencias(f"{_txt(inf, 'xLocIncid')} / {pais_inc}"
                                      if _txt(inf, "xLocIncid") else TRACO, 42),
            "regime": _descricao(REGIME_ESPECIAL, _txt(inf, f"{dps}/prest/regTrib/regEspTrib"), 27),
            "imunidade": _descricao(IMUNIDADE, _txt(inf, f"{dps}/valores/trib/tribMun/tpImunidade")),
            "suspensao": _descricao(SUSPENSAO, _txt(inf, f"{dps}/valores/trib/tribMun/exigSusp/tpSusp")),
            "processo": _ou_traco(_txt(inf, f"{dps}/valores/trib/tribMun/exigSusp/nProcesso")),
            "beneficio": _descricao(BENEFICIO, _txt(inf, "valores/tpBM")),
            "calculo_bm": dinheiro(_primeiro(inf, "valores/vCalcBM",
                                             f"{dps}/valores/trib/tribMun/BM/vRedBCBM")),
            "deducoes": dinheiro(_primeiro(inf, f"{dps}/valores/vDedRed/vDR", "valores/vCalcDR")),
            "desconto": dinheiro(_txt(inf, f"{dps}/valores/vDescCondIncond/vDescIncond")),
            "bc": dinheiro(_txt(inf, "valores/vBC")),
            "aliquota": percentual(_txt(inf, "valores/pAliqAplic")),
            "retencao": _descricao(RETENCAO_ISSQN, _txt(inf, f"{dps}/valores/trib/tribMun/tpRetISSQN")),
            "apurado": dinheiro(_txt(inf, "valores/vISSQN")),
        },
        "federal": {
            "irrf": dinheiro(_txt(inf, f"{dps}/valores/trib/tribFed/vRetIRRF")),
            "cp": dinheiro(_txt(inf, f"{dps}/valores/trib/tribFed/vRetCP")),
            "csll": dinheiro(_txt(inf, f"{dps}/valores/trib/tribFed/vRetCSLL")),
            "pis": dinheiro(_txt(inf, f"{dps}/valores/trib/tribFed/piscofins/vPis")),
            "cofins": dinheiro(_txt(inf, f"{dps}/valores/trib/tribFed/piscofins/vCofins")),
            "descricao": _descricao(RETENCAO_PIS, _txt(
                inf, f"{dps}/valores/trib/tribFed/piscofins/tpRetPisCofins"), 35),
            # Nota 6 da NT: a linha de PIS/COFINS só vai nas notas com
            # competência até o fim de 2026.
            "linha_pis": _txt(inf, f"{dps}/dCompet")[:4] <= "2026",
        },
        "ibscbs": {
            "cst": (" / ".join(x for x in (
                _txt(inf, f"{dps}/IBSCBS/valores/trib/gIBSCBS/CST"),
                _txt(inf, f"{dps}/IBSCBS/valores/trib/gIBSCBS/cClassTrib")) if x) or TRACO),
            "operacao": reticencias(loc_inc, 56),
            "exclusoes": dinheiro(f"{exclusoes:.2f}") if ibs is not None else TRACO,
            "bc": dinheiro(_txt(inf, "IBSCBS/valores/vBC")),
            "reducoes": " / ".join(red) if any(r != TRACO for r in red) else TRACO,
            "aliquotas_ibs": (" / ".join((percentual(_txt(inf, "IBSCBS/valores/uf/pIBSUF")),
                                          percentual(_txt(inf, "IBSCBS/valores/mun/pIBSMun"))))
                              if ibs is not None else TRACO),
            "efetiva_mun": percentual(_txt(inf, "IBSCBS/valores/mun/pAliqEfetMun")),
            "valor_mun": dinheiro(_txt(inf, "IBSCBS/totCIBS/gIBS/gIBSMunTot/vIBSMun")),
            "efetiva_uf": percentual(_txt(inf, "IBSCBS/valores/uf/pAliqEfetUF")),
            "valor_uf": dinheiro(_txt(inf, "IBSCBS/totCIBS/gIBS/gIBSUFTot/vIBSUF")),
            "total_ibs": dinheiro(vibs),
            "aliquota_cbs": percentual(_txt(inf, "IBSCBS/valores/fed/pCBS")),
            "efetiva_cbs": percentual(_txt(inf, "IBSCBS/valores/fed/pAliqEfetCBS")),
            "valor_cbs": dinheiro(vcbs),
        },
        "total": {
            "servico": dinheiro(_txt(inf, f"{dps}/valores/vServPrest/vServ")),
            "desconto_incond": dinheiro(_txt(inf, f"{dps}/valores/vDescCondIncond/vDescIncond")),
            "desconto_cond": dinheiro(_txt(inf, f"{dps}/valores/vDescCondIncond/vDescCond")),
            "retencoes": dinheiro(_txt(inf, "valores/vTotalRet")),
            "liquido": dinheiro(_txt(inf, "valores/vLiq")),
            "ibscbs": total_ibscbs,
            "liquido_ibscbs": dinheiro(_txt(inf, "IBSCBS/totCIBS/vTotNF")),
        },
        "informacoes": reticencias(info, 1997),
        "totais_aproximados": ("Totais Aproximados dos Tributos cfe. Lei nº 12.741/2012: "
                               + totais),
    }


# ---------------------------------------------------------------- o desenho

_CSS = """
@page { size: A4 portrait; margin: 0; }
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; background: #fff; }
body { width: 21cm; height: 29.7cm; position: relative; color: #000;
  font-family: "Microsoft Sans Serif", Arial, sans-serif; font-size: 7pt; }
.folha { position: absolute; left: .30cm; top: .30cm; width: 20.40cm; height: 29.10cm;
  border: 1pt solid #000; display: flex; flex-direction: column; overflow: hidden; }
.cab { height: 1.16cm; display: flex; background: #f2f2f2; border-bottom: .5pt solid #000; }
.cab .logo { width: 5.11cm; display: flex; align-items: center; padding-left: .19cm; }
.cab .logo img { width: 4.00cm; height: .85cm; object-fit: contain; }
.cab .titulo { width: 10.19cm; text-align: center; font-family: Arial, sans-serif;
  font-weight: bold; font-size: 9pt; display: flex; flex-direction: column;
  justify-content: center; line-height: 1.15; }
.cab .titulo .sem { color: #ff0000; }
.cab .mun { width: 5.10cm; padding: .08cm .1cm; line-height: 1.2; }
.cab .mun .m { font-size: 8pt; }
.cab .mun .a { font-size: 6pt; }
.ident { height: 2.86cm; position: relative; border-bottom: .5pt solid #000; }
.ident .grade { position: absolute; left: 0; top: 0; width: 15.30cm; }
.ident .qr { position: absolute; left: 17.18cm; top: .19cm; width: 1.52cm; height: 1.52cm; }
.ident .qrtexto { position: absolute; left: 15.50cm; top: 1.88cm; width: 4.72cm;
  font-size: 6pt; text-align: center; line-height: 1.15; }
.linha { display: flex; border-bottom: .5pt solid #000; min-height: .63cm; }
.ident .linha:last-child { border-bottom: 0; }
.c { width: 5.10cm; padding: .03cm .08cm; border-right: .5pt solid #000; overflow: hidden; }
.c:last-child { border-right: 0; }
.c2 { width: 10.20cm; } .c3 { width: 15.30cm; } .c4 { width: 20.40cm; }
.r { display: block; font-family: Arial, sans-serif; font-weight: bold; font-size: 6pt; }
.ident .r { font-size: 7pt; text-transform: uppercase; }
.v { display: block; font-size: 7pt; line-height: 1.15; word-wrap: break-word; }
.chave .v { font-size: 9pt; letter-spacing: .02cm; }
.bloco { background: #f2f2f2; font-family: Arial, sans-serif; font-weight: bold;
  font-size: 7pt; text-transform: uppercase; display: flex; align-items: center; }
.sombra { background: #f2f2f2; }
.aviso { min-height: .32cm; font-family: Arial, sans-serif; font-weight: bold; font-size: 7pt;
  text-transform: uppercase; padding: .05cm .08cm; border-bottom: .5pt solid #000;
  background: #f2f2f2; }
.desc { flex: 1 1 auto; border-bottom: .5pt solid #000; padding: .03cm .08cm; min-height: .63cm; }
.desc .v { white-space: pre-wrap; }
.info { flex: 1 1 auto; padding: .03cm .08cm; display: flex; flex-direction: column;
  justify-content: space-between; min-height: .78cm; }
.titulo-info { min-height: .39cm; }
.marca { position: absolute; left: 0; top: 0; width: 21cm; height: 29.7cm; display: flex;
  align-items: center; justify-content: center; pointer-events: none; z-index: 9; }
.marca span { transform: rotate(-45deg); font-family: Arial, sans-serif; font-size: 90pt;
  color: #a6a6a6; opacity: .55; }
@media screen { body { margin: 1cm auto; box-shadow: 0 0 .3cm #999; } }
"""


def _e(v: Any) -> str:
    return html.escape(str(v if v not in (None, "") else TRACO))


def _celula(rotulo: str, valor: str, larg: int = 1, *, classe: str = "") -> str:
    larg_cls = {1: "", 2: " c2", 3: " c3", 4: " c4"}[larg]
    return (f'<div class="c{larg_cls}{" " + classe if classe else ""}">'
            f'<span class="r">{_e(rotulo)}</span><span class="v">{_e(valor)}</span></div>')


def _titulo(nome: str) -> str:
    return f'<div class="c bloco">{_e(nome)}</div>'


def _linha(*celulas: str) -> str:
    return f'<div class="linha">{"".join(celulas)}</div>'


def _vazia() -> str:
    return '<div class="c"></div>'


def _bloco_pessoa(titulo: str, p: Mapping[str, str] | None, *, com_im: bool = True,
                  extra: list[str] | None = None, nao_identificado: str = "") -> str:
    if p is None:
        return f'<div class="aviso">{_e(nao_identificado)}</div>'
    partes = [_linha(_titulo(titulo), _celula("CNPJ / CPF / NIF", p["doc"]),
                     _celula("Indicador Municipal (Inscrição)", p["im"]) if com_im else _vazia(),
                     _celula("Telefone", p["fone"])),
              _linha(_celula("Nome / Nome Empresarial", p["nome"], 2),
                     _celula("Município / Sigla UF", p["municipio"]),
                     _celula("Código IBGE / CEP", p["ibge_cep"])),
              _linha(_celula("Endereço", p["endereco"], 2), _celula("E-mail", p["email"], 2))]
    return "".join(partes + (extra or []))


def montar_html(d: Mapping[str, Any], *, cancelada: bool = False,
                logo_data_uri: str = "") -> str:
    """O HTML do DANFSe, numa página A4. Só calcula."""
    import segno
    qr = segno.make(d["url_consulta"], error="m").svg_data_uri(border=0, dark="#000")
    n, cab = d["nota"], d["cabecalho"]
    sem_validade = (d["ambiente"] == "2")
    logo = (f'<img src="{logo_data_uri}" alt="NFS-e">' if logo_data_uri
            else '<b style="font-family:Arial;font-size:14pt">NFS-e</b>')
    partes = [
        "<!doctype html><html lang=\"pt-BR\"><head><meta charset=\"utf-8\">",
        f"<title>DANFSe {_e(n['numero'])}</title><style>{_CSS}</style></head><body>",
        '<div class="folha">',
        '<div class="cab">',
        f'<div class="logo">{logo}</div>',
        f'<div class="titulo"><div>{VERSAO_DO_MODELO}</div><div>Documento Auxiliar da NFS-e</div>'
        + ('<div class="sem">NFS-e SEM VALIDADE JURÍDICA</div>' if sem_validade else "")
        + "</div>",
        '<div class="mun">'
        + (f'<div class="m">{_e(cab["municipio"])}</div>' if cab["municipio"] else "")
        + f'<div class="a">{_e(cab["ambiente_gerador"])}</div>'
        f'<div class="a">{_e(cab["tipo_ambiente"])}</div></div>',
        "</div>",
        '<div class="ident"><div class="grade">',
        _linha(f'<div class="c c3 chave"><span class="r">Chave de Acesso da NFS-e</span>'
               f'<span class="v">{_e(d["chave"])}</span></div>'),
        _linha(_celula("Número da NFS-e", n["numero"]),
               _celula("Competência da NFS-e", n["competencia"]),
               _celula("Data e Hora da Emissão da NFS-e", n["emissao"])),
        _linha(_celula("Número da DPS", n["dps_numero"]),
               _celula("Série da DPS", n["dps_serie"]),
               _celula("Data e Hora da Emissão da DPS", n["dps_emissao"])),
        _linha(_celula("Emitente da NFS-e", n["emitente"], classe="sombra"),
               _celula("Situação da NFS-e", n["situacao"]),
               _celula("Finalidade", n["finalidade"])),
        "</div>",
        f'<img class="qr" src="{qr}" alt="QR Code da consulta pública">',
        '<div class="qrtexto">A autenticidade desta NFS-e pode ser verificada pela '
        "leitura deste código QR ou pela consulta da chave de acesso no portal "
        "nacional da NFS-e</div>",
        "</div>",
        _bloco_pessoa("Prestador / Fornecedor", d["prestador"], extra=[_linha(
            _celula("Simples Nacional na Data de Competência", d["simples"]), _vazia(),
            _celula("Regime de Apuração Tributária pelo SN", d["apuracao_sn"], 2))]),
        _bloco_pessoa("Tomador / Adquirente", d["tomador"],
                      nao_identificado="TOMADOR/ADQUIRENTE DA OPERAÇÃO NÃO IDENTIFICADO NA NFS-e"),
        ('<div class="aviso">O DESTINATÁRIO É O PRÓPRIO TOMADOR/ADQUIRENTE DA OPERAÇÃO</div>'
         if d["destinatario_proprio"] else
         '<div class="aviso">DESTINATÁRIO DA OPERAÇÃO NÃO IDENTIFICADO NA NFS-e</div>'),
        '<div class="aviso">INTERMEDIÁRIO DA OPERAÇÃO NÃO IDENTIFICADO NA NFS-e</div>',
    ]
    s, i, f, r, t = d["servico"], d["issqn"], d["federal"], d["ibscbs"], d["total"]
    partes += [
        _linha(_titulo("Serviço Prestado"),
               _celula("Código de Tributação Nacional / Municipal", s["codigo"]),
               _celula("Código da NBS", s["nbs"]),
               _celula("Local da Prestação / Sigla UF / País", s["local"])),
        f'<div class="linha" style="min-height:.38cm"><div class="c c4">'
        f'<span class="v">{_e(s["descricao_codigo"])}</span></div></div>',
        f'<div class="desc"><span class="r">Descrição do Serviço</span>'
        f'<span class="v">{_e(s["descricao"])}</span></div>',
        _linha(_titulo("Tributação Municipal (ISSQN)"),
               _celula("Tipo de Tributação do ISSQN", i["tipo"]),
               _celula("Município / Sigla UF / País da Incidência do ISSQN", i["incidencia"], 2)),
    ]
    # Nota 5: as duas linhas opcionais saem só quando têm algum dado.
    linha_reg = (i["regime"], i["imunidade"], i["suspensao"], i["processo"])
    if any(v != TRACO for v in linha_reg):
        partes.append(_linha(_celula("Regime Especial de Tributação do ISSQN", i["regime"]),
                             _celula("Tipo de Imunidade do ISSQN", i["imunidade"]),
                             _celula("Suspensão da Exigibilidade do ISSQN", i["suspensao"]),
                             _celula("Número Processo Suspensão", i["processo"])))
    linha_bm = (i["beneficio"], i["calculo_bm"], i["deducoes"], i["desconto"])
    if any(v != TRACO for v in linha_bm):
        partes.append(_linha(_celula("Benefício Municipal", i["beneficio"]),
                             _celula("Cálculo do BM", i["calculo_bm"]),
                             _celula("Total Deduções/Reduções", i["deducoes"]),
                             _celula("Desconto Incondicionado", i["desconto"])))
    partes += [
        _linha(_celula("BC ISSQN", i["bc"]), _celula("Alíquota Aplicada", i["aliquota"]),
               _celula("Retenção do ISSQN", i["retencao"]),
               _celula("ISSQN Apurado", i["apurado"])),
        _linha(_titulo("Tributação Federal (Exceto CBS)"), _celula("IRRF", f["irrf"]),
               _celula("Contribuição Previdenciária - Retida", f["cp"]),
               _celula("Contribuições Sociais - Retidas", f["csll"])),
    ]
    if f["linha_pis"]:
        partes.append(_linha(_celula("PIS - Débito Apuração Própria", f["pis"]),
                             _celula("COFINS - Débito Apuração Própria", f["cofins"]),
                             _celula("Descrição Contrib. Sociais - Retidas", f["descricao"], 2)))
    partes += [
        _linha(_titulo("Tributação IBS / CBS"), _celula("CST / cClassTrib", r["cst"]),
               _celula("Indicador de Operação / Código IBGE Incidência / "
                       "Município Incidência / Sigla UF", r["operacao"], 2)),
        _linha(_celula("Exclusões e Reduções da Base de Cálculo", r["exclusoes"]),
               _celula("Base de Cálculo Após Exclusões e Reduções", r["bc"]),
               _celula("Red. Alíquota IBS / Red. Alíquota CBS", r["reducoes"]),
               _celula("Alíquota - IBS UF / IBS Mun", r["aliquotas_ibs"])),
        _linha(_celula("Alíq. Efetiva Municipal - IBS", r["efetiva_mun"]),
               _celula("Valor Apurado Municipal - IBS", r["valor_mun"]),
               _celula("Alíq. Efetiva Estadual - IBS", r["efetiva_uf"]),
               _celula("Valor Apurado Estadual - IBS", r["valor_uf"])),
        _linha(_celula("Valor Total Apurado - IBS", r["total_ibs"]),
               _celula("Alíquota - CBS", r["aliquota_cbs"]),
               _celula("Alíquota Efetiva - CBS", r["efetiva_cbs"]),
               _celula("Valor Total Apurado - CBS", r["valor_cbs"])),
        _linha(_titulo("Valor Total da NFS-e"),
               _celula("Valor da Operação / Serviço", t["servico"]),
               _celula("Desconto Incondicionado", t["desconto_incond"]),
               _celula("Desconto Condicionado", t["desconto_cond"])),
        _linha(_celula("Total das Retenções (ISSQN / Federais)", t["retencoes"]),
               _celula("Valor Líquido da NFS-e", t["liquido"]),
               _celula("Total do IBS/CBS", t["ibscbs"]),
               _celula("Valor Líquido da NFS-e + IBS/CBS", t["liquido_ibscbs"],
                       classe="sombra")),
        '<div class="linha titulo-info"><div class="c c4 bloco">Informações Complementares'
        "</div></div>",
        f'<div class="info"><span class="v">{_e(d["informacoes"]) if d["informacoes"] else ""}'
        f'</span><span class="v">{_e(d["totais_aproximados"])}</span></div>',
        "</div>",
    ]
    if cancelada:
        partes.append('<div class="marca"><span>CANCELADA</span></div>')
    partes.append("</body></html>")
    return "".join(partes)


def logo_data_uri() -> str:
    """O logotipo oficial da NFS-e (gov.br/nfse → logos da NFS-e), embutido."""
    import base64
    try:
        return "data:image/png;base64," + base64.b64encode(LOGO.read_bytes()).decode("ascii")
    except OSError:
        return ""


def html_da_nota(xml: bytes | str, *, cancelada: bool = False,
                 nome_do_municipio: NomeDoMunicipio | None = None) -> str:
    return montar_html(dados(xml, nome_do_municipio=nome_do_municipio),
                       cancelada=cancelada, logo_data_uri=logo_data_uri())


def pdf_da_nota(xml: bytes | str, *, cancelada: bool = False,
                nome_do_municipio: NomeDoMunicipio | None = None,
                nome: str = "danfse", get_setting=None) -> bytes:
    """O PDF do DANFSe, pelo Chrome sem rede. Erro vira `DanfseError`."""
    import impressao_pdf
    pagina = html_da_nota(xml, cancelada=cancelada, nome_do_municipio=nome_do_municipio)
    try:
        return impressao_pdf.pdf_de_html_chrome(pagina, nome=nome, get_setting=get_setting)
    except impressao_pdf.PdfError as erro:
        raise DanfseError(str(erro)) from erro
