"""O arquivo XML do CCN (`CcnPessoaFisica`), montado e CONFERIDO contra o XSD v4.

O CONTRATO — 13/10/2026
    `schemas/ccn_v4.xsd` é o anexo «CCN v4.xsd» (7.205 bytes, sha256
    1d63dfca…915f3) do artigo «CCN - Documentação Técnica» do suporte do CNB,
    baixado por ordem do oficial («pode baixar o xsd»). A cópia em
    `FONTES_EXTERNAS/enotariado/` é a prova; a de `schemas/` é a que viaja.

O QUE O XSD DECIDIU, E A DOCUMENTAÇÃO DEIXAVA EM DÚVIDA
    - a raiz é `<pessoas>` com uma `<pessoa>` por cadastro, sem namespace;
    - a ORDEM dos campos é a do `xs:sequence` (e é a de `ORDEM` abaixo);
    - o nome é `dataFicha` e `politicamenteExposta` — a tabela da documentação
      escreve «dataficha» e «politicamenteexposta», e o validador recusaria;
    - `endereco` EXIGE `ibgeCidade`; `documento` EXIGE `docIdentidade`,
      `orgaoEmissor` e `dataEmissao`; `ficha` EXIGE ao menos uma imagem. Bloco
      sem o obrigatório NÃO vai — mandá-lo derrubaria o arquivo inteiro.

O QUE AINDA SE CONFERE NA HOMOLOGAÇÃO
    O estado civil vai pelo CÓDIGO do domínio (1 a 8), porque a tabela da
    documentação chama a coluna de «Código»; o XSD diz só `xs:string`. Se a
    homologação recusar, a troca é numa linha (`CODIGO_DO_ESTADO_CIVIL`).

Todo lote é validado contra o XSD ANTES de ir para o disco: arquivo que não
valida não sai da casa.
"""
from __future__ import annotations

import base64
from pathlib import Path
from xml.sax.saxutils import escape

XSD = Path(__file__).resolve().parent / "schemas" / "ccn_v4.xsd"

CODIGO_DO_ESTADO_CIVIL = {
    "Solteiro": "1", "Casado": "2", "SeparadoJudicialmente": "3", "Divorciado": "4",
    "Viuvo": "5", "UniaoEstavel": "6", "Desquitado": "7", "SeparadoExtrajudicialmente": "8",
}

#: A ordem do `xs:sequence` de `xmlPessoa`, campo a campo.
ORDEM = ("chaveRegistro", "dataRegistro", "estadoCivil", "ibgeCidadeNaturalidade",
         "nacionalidade", "nacionalidadeTipo", "ufNaturalidade", "cidadeNaturalidade",
         "cpf", "nome", "sexo", "mae", "pai", "telefone", "celular", "profissao",
         "dataNascimento", "email", "endereco", "observacao", "documento",
         "carteiraHabilitacao", "biometria", "ficha", "imagemFoto", "cartorio",
         "termoTitularidade", "certidaoCasamento", "anexo", "enderecoTrabalho",
         "politicamenteExposta", "investigadaAcusadaTerrorismo", "conjuge",
         "fichaBloqueada", "fotoVerificada")
ORDEM_ENDERECO = ("ibgeCidade", "cep", "bairro", "cidade", "uf", "complemento",
                  "endereco", "numero")
ORDEM_DOCUMENTO = ("tipo", "docIdentidade", "orgaoEmissor", "ufOrgaoEmissor", "dataEmissao")
#: Nome do domínio (`ccn_envio`) → nome do XSD, onde os dois divergem.
RENOMEIA = {"politicamenteexposta": "politicamenteExposta"}


class FormatoAusente(ValueError):
    """O XSD do CNB não está na casa: o arquivo não se monta por parecença."""


class ArquivoInvalido(ValueError):
    """O arquivo montado não passou no XSD — não sai da casa."""


def situacao_do_formato() -> dict:
    """Para a tela: dá para gerar lote? Só LÊ."""
    if not XSD.is_file():
        return {"pronto": False,
                "motivo": "o XSD v4 do CNB (schemas/ccn_v4.xsd) não está nesta instalação"}
    try:
        import lxml.etree  # noqa: F401
    except ImportError:
        return {"pronto": False, "motivo": "falta a biblioteca lxml para conferir o arquivo"}
    return {"pronto": True, "motivo": None}


def _t(nome: str, valor) -> str:
    return f"<{nome}>{escape(str(valor))}</{nome}>"


def _b64(caminho) -> str:
    return base64.b64encode(Path(caminho).read_bytes()).decode("ascii")


def _bool(v) -> str:
    return "true" if v else "false"


def pessoa_xml(p: dict) -> str:
    """Uma `<pessoa>`, na ordem do XSD, só com os blocos completos."""
    c = {RENOMEIA.get(k, k): v for k, v in p["campos"].items()}
    img = p.get("imagens") or {}
    partes: list[str] = []
    for nome in ORDEM:
        if nome == "estadoCivil" and c.get(nome):
            partes.append(_t(nome, CODIGO_DO_ESTADO_CIVIL[c[nome]]))
        elif nome == "endereco":
            e = c.get("endereco") or {}
            if e.get("ibgeCidade"):                       # obrigatório no XSD
                partes.append("<endereco>" + "".join(_t(k, e[k]) for k in ORDEM_ENDERECO
                                                     if e.get(k)) + "</endereco>")
        elif nome == "documento":
            d = c.get("documento") or {}
            if all(d.get(k) for k in ("docIdentidade", "orgaoEmissor", "dataEmissao")):
                partes.append("<documento>" + "".join(_t(k, d[k]) for k in ORDEM_DOCUMENTO
                                                      if d.get(k)) + "</documento>")
        elif nome == "biometria":
            for dg in img.get("digitais") or []:
                partes.append("<biometria>" + _t("dedo", dg["dedo"])
                              + f"<imagemBiometria>{_b64(dg['caminho'])}</imagemBiometria></biometria>")
        elif nome == "ficha":
            f = c.get("ficha") or {}
            fichas = img.get("ficha") or []
            if fichas and f.get("dataficha") and f.get("numeroFicha"):
                partes.append("<ficha>" + _t("dataFicha", f["dataficha"])
                              + _t("numeroFicha", f["numeroFicha"])
                              + "".join(f"<imagensFicha>{_b64(x)}</imagensFicha>" for x in fichas)
                              + "</ficha>")
        elif nome == "imagemFoto":
            if img.get("foto"):
                partes.append(f"<imagemFoto>{_b64(img['foto']['caminho'])}</imagemFoto>")
        elif nome == "fotoVerificada":
            if img.get("foto"):
                partes.append(_t(nome, _bool(img["foto"].get("verificada"))))
        elif nome in ("politicamenteExposta", "investigadaAcusadaTerrorismo", "fichaBloqueada"):
            if nome in c:
                partes.append(_t(nome, _bool(c[nome])))
        elif isinstance(c.get(nome), (str, int)) and str(c.get(nome)).strip():
            partes.append(_t(nome, c[nome]))
    return "<pessoa>" + "".join(partes) + "</pessoa>"


def validar(conteudo: bytes) -> None:
    """Confere contra o XSD v4. Arquivo que não valida não sai da casa."""
    from lxml import etree
    esquema = etree.XMLSchema(etree.parse(str(XSD)))
    doc = etree.fromstring(conteudo, etree.XMLParser(huge_tree=True))
    if not esquema.validate(doc):
        erro = esquema.error_log.last_error
        raise ArquivoInvalido(f"o arquivo não passou no XSD do CCN: linha {erro.line}: {erro.message}")


def montar(pessoas: list[dict]) -> bytes:
    situacao = situacao_do_formato()
    if not situacao["pronto"]:
        raise FormatoAusente(situacao["motivo"])
    if not pessoas:
        raise ArquivoInvalido("lote sem pessoa nenhuma")
    conteudo = ("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<pessoas>"
                + "".join(pessoa_xml(p) for p in pessoas) + "</pessoas>").encode("utf-8")
    validar(conteudo)
    return conteudo
