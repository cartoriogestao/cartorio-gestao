"""Quadro da certidão RCPN — Anexos IV, V e VI do Prov. CNJ 182/2024.

O PAPEL DE SEGURANÇA JÁ TRAZ O BRASÃO. Este quadro começa no título
CERTIDÃO DE… e não traz livro/folha/termo: isso já está na matrícula.
"""
from __future__ import annotations

import json
import re
from typing import Any

import rc_certidao as RCE


def so_digitos(valor: Any) -> str:
    return re.sub(r"\D+", "", str(valor or ""))


def formatar_cpf(valor: Any) -> str:
    d = so_digitos(valor)
    if len(d) == 11:
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    return str(valor or "").strip()


def formatar_matricula(valor: Any) -> str:
    d = so_digitos(valor)
    if len(d) == 32:
        return (f"{d[0:6]} {d[6:8]} {d[8:10]} {d[10:14]} {d[14:15]} "
                f"{d[15:20]} {d[20:23]} {d[23:30]} {d[30:32]}")
    return str(valor or "").strip()


def partes_data(iso: Any) -> dict[str, str]:
    s = str(iso or "").strip()
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return {"dia": s[8:10], "mes": s[5:7], "ano": s[0:4]}
    d = so_digitos(s)
    if len(d) == 8:
        return {"dia": d[:2], "mes": d[2:4], "ano": d[4:8]}
    return {"dia": "", "mes": "", "ano": ""}


def _dados(assento: dict) -> dict:
    dados = assento.get("dados") if isinstance(assento.get("dados"), dict) else {}
    if dados:
        return dados
    try:
        return json.loads(assento.get("dados_json") or "{}")
    except (TypeError, ValueError):
        return {}


def _cidade_uf(texto: str) -> tuple[str, str]:
    t = str(texto or "").strip()
    if "/" in t:
        a, b = t.rsplit("/", 1)
        return a.strip(), b.strip()
    return t, ""


def _hora(valor: Any) -> str:
    t = str(valor or "").strip()
    if not t:
        return ""
    if "hora" in t.lower():
        return t
    return f"{t} horas" if t else ""


def _nome_existe(nome: str) -> bool:
    n = str(nome or "").strip()
    if not n:
        return False
    return True


def quadro_da_certidao(con, certidao: dict, sv: dict) -> dict:
    """Monta as células da impressão. SÓ CALCULA."""
    aid = int(certidao["assento_id"])
    row = con.execute("SELECT * FROM rc_assentos WHERE id=?", (aid,)).fetchone()
    a = dict(row) if row else {}
    especie = str(a.get("especie") or certidao.get("especie") or "").upper()
    titulo = RCE.titulo_do_modelo(especie)
    if titulo.endswith(" DE:"):
        titulo = titulo[:-4]
    dados = _dados(a)
    quem = RCE._por_papel(RCE.pessoas(con, aid))
    atos = [dict(x) for x in con.execute(
        """SELECT tipo, teor FROM rc_atos WHERE assento_id=?
           AND tipo IN ('AVERBACAO','ANOTACAO','RETIFICACAO')
           ORDER BY id""", (aid,)).fetchall()]
    acrescer = []
    for x in atos:
        rotulo = str(x.get("tipo") or "").capitalize()
        acrescer.append(f"{rotulo}: {str(x.get('teor') or '').strip()}".strip())
    if str(a.get("situacao") or "").upper() == "CANCELADO":
        acrescer.append(
            "CERTIFICO ainda que o referido assento encontra-se "
            "CANCELADO nesta Serventia.")
    anota = "\n".join(acrescer)

    # CPF do registrado: assento.cpf_registrado / pessoa REGISTRADO, depois
    # legado do dados_json (E-Oficio). `_documento` devolve "SEM INFORMACAO"
    # quando vazio - isso e truthy e engolia o CPF ja gravado no assento.
    reg = quem.get("REGISTRADO") or {}
    cpf_bruto = (
        a.get("cpf_registrado")
        or (
            reg.get("documento_numero")
            if str(reg.get("documento_tipo") or "").upper() in ("CPF", "")
            else None
        )
        or None
    )
    if not so_digitos(cpf_bruto) or len(so_digitos(cpf_bruto)) != 11:
        legado = RCE._documento(dados)
        if legado and legado != getattr(RCE, "SEM_INFORMACAO", "SEM INFORMACAO"):
            cpf_bruto = legado
        elif so_digitos(certidao.get("cpf")):
            cpf_bruto = certidao.get("cpf")
    cpf = formatar_cpf(cpf_bruto) if so_digitos(cpf_bruto) else ""
    matricula = formatar_matricula(a.get("matricula") or certidao.get("matricula"))
    do_fato = RCE.data_por_extenso(a.get("data_fato"))
    do_registro = RCE.data_por_extenso(a.get("data_ato"))
    dma_fato = partes_data(a.get("data_fato"))
    dma_reg = partes_data(a.get("data_ato"))

    q: dict[str, Any] = {
        "especie": especie,
        "titulo": titulo,
        "cpf": cpf,
        "matricula": matricula,
        "anotacoes": anota,
        "data_fato_extenso": do_fato,
        "data_registro_extenso": do_registro,
        "dma_fato": dma_fato,
        "dma_registro": dma_reg,
        "cns": str(sv.get("ri_cns") or "").strip(),
        "casa": str(sv.get("unit_name") or "").strip(),
        "cidade": str(sv.get("ri_cidade") or "").strip(),
        "uf": str(sv.get("ri_uf") or "").strip(),
        "oficial": str(sv.get("serventia_titular") or "").strip(),
        "cargo": (str(certidao.get("emitida_funcao") or "").strip()
                  or str(sv.get("serventia_titulo") or "").strip()),
        "rua": str(sv.get("serventia_endereco") or "").strip(),
        "cep": str(sv.get("serventia_cep") or "").strip(),
        "data_comercial": RCE.data_por_extenso(
            (certidao.get("emitida_em") or "")[:10]),
        "email": str(sv.get("serventia_email") or "").strip(),
        "telefone": str(sv.get("serventia_telefone") or "").strip(),
        "municipio_registro": RCE._lugar(sv.get("ri_cidade"), sv.get("ri_uf")),
        "anotacoes_cadastro": "",
        "filiacao": "",
        "avos_maternos": "",
        "avos_paternos": "",
        "qualificacao_conjuges": "",
        "endereco": ", ".join(
            x for x in (
                str(sv.get("endereco_completo") or sv.get("serventia_endereco") or "").strip(),
            ) if x),
    }
    # endereço desta casa vive em várias chaves; o ODT já imprimia um composto.
    if not q["endereco"]:
        q["endereco"] = ""

    if especie == "NASCIMENTO":
        nat, nat_uf = _cidade_uf(RCE._lugar_da_pessoa(
            quem, "REGISTRADO", "naturalidade_cidade", "naturalidade_uf",
            dados, "strCidade", "strUF"))
        local = RCE._local_do_nascimento(dados) or str(
            a.get("local_fato_nome") or "").strip()
        mun_nasc, mun_uf = _cidade_uf(RCE._lugar(
            a.get("local_fato_endereco") or dados.get("strMunicipioNascimento"),
            dados.get("strUFNascimento") or sv.get("ri_uf")))
        if not mun_nasc and local and "/" in local:
            # se o local já traz cidade/UF no fim, não duplicar no município
            mun_nasc, mun_uf = "", ""
        mae = quem.get("MAE") or {}
        pai = quem.get("PAI") or {}
        gemeo_n = a.get("ibge_gemeo")
        gemeo = ""
        if gemeo_n not in (None, "") and int(gemeo_n) > 1:
            gemeo = str(dados.get("strNomeGemeo") or "SIM")
        elif dados.get("bitGemeos") and str(dados.get("bitGemeos")) not in (
                "0", "false", "False", "NÃO", "NAO"):
            gemeo = str(dados.get("strNomeGemeo") or "").strip()
        q.update({
            "nome": str(a.get("nome") or "").strip().upper(),
            "hora": _hora(a.get("hora_fato") or dados.get("strHoraNascimento")),
            "naturalidade": nat,
            "naturalidade_uf": nat_uf,
            "local_nascimento": local,
            "municipio_nascimento": mun_nasc,
            "municipio_nascimento_uf": mun_uf,
            "sexo": RCE._sexo_por_extenso(
                RCE._de(quem, "REGISTRADO", "sexo", dados, "strSexo")),
            "genitores": _genitores_nascimento(quem, dados),
            "gemeo": gemeo,
            "dnv": str(a.get("dnv") or dados.get("strDeclaracaoNascidoVivo")
                       or "").strip(),
            "mae": mae, "pai": pai,
            "filiacao": RCE._e_junta([RCE._nome(mae), RCE._nome(pai)]),
            "avos_maternos": RCE._e_junta([
                RCE._nome(quem.get("AVO_MATERNO")),
                RCE._nome(quem.get("AVO_MATERNA"))]),
            "avos_paternos": RCE._e_junta([
                RCE._nome(quem.get("AVO_PATERNO")),
                RCE._nome(quem.get("AVO_PATERNA"))]),
        })
    elif especie in ("CASAMENTO", "CASAMENTO_RELIGIOSO"):
        q.update(_quadro_casamento(a, quem, dados, do_fato, dma_fato))
    else:
        q.update(_quadro_obito(a, quem, dados, do_fato, dma_fato))
    return q


def _nasc_pessoa(quem, papel, dados) -> tuple[str, str]:
    return _cidade_uf(RCE._lugar_da_pessoa(
        quem, papel, "naturalidade_cidade", "naturalidade_uf", dados))


def _genitores_nascimento(quem, dados) -> list[dict]:
    blocos = []
    for papel, avos in (
            ("MAE", ("AVO_MATERNO", "AVO_MATERNA")),
            ("PAI", ("AVO_PATERNO", "AVO_PATERNA"))):
        nome = RCE._nome(quem.get(papel))
        if not _nome_existe(nome):
            continue
        cid, uf = _nasc_pessoa(quem, papel, dados)
        avo_txt = "; ".join(
            n for n in (RCE._nome(quem.get(a)) for a in avos) if n)
        blocos.append({
            "nome": nome, "municipio": cid, "uf": uf, "avos": avo_txt,
        })
    return blocos


def _quadro_casamento(a, quem, dados, do_fato, dma_fato) -> dict:
    conj = []
    for i, papel in enumerate(("NUBENTE1", "NUBENTE2"), start=1):
        nome = RCE._de(quem, papel, "nome", dados, f"strNomeConjuge{i}")
        if i == 1:
            nome = nome or str(a.get("nome") or "").strip()
        if not nome:
            continue
        dma = partes_data(RCE._de(quem, papel, "data_nascimento", dados))
        cid, uf = _nasc_pessoa(quem, papel, dados)
        pais = "; ".join(n for n in (
            RCE._nome(quem.get(f"MAE_NUBENTE{i}")),
            RCE._nome(quem.get(f"PAI_NUBENTE{i}")),
        ) if n)
        # **O RECURSO AOS PAIS GENÉRICOS VALE SÓ PARA O PRIMEIRO CÔNJUGE**, e
        # isso foi medido — achado em 01/09/2026 no ensaio contra a produção,
        # ao gerar a primeira certidão de casamento no molde novo.
        #
        # A produção **não tem uma única** pessoa com papel `PAI_NUBENTE1` ou
        # `MAE_NUBENTE2`: só `PAI` e `MAE` genéricos, 12 de cada em 20
        # casamentos. Com o recurso valendo para os dois, a certidão saía com
        # **a mesma filiação nos dois cônjuges** — um papel assinado dizendo
        # que o casal é irmão.
        #
        # De quem são os genéricos, decidido pelos sobrenomes nos 20
        # casamentos da casa: **batem com o NUBENTE 1 em 10, e com o NUBENTE 2
        # em ZERO** (8 não têm pais no banco e não decidem). É a mesma régua
        # que separou as quatro filiações do casamento na carga.
        #
        # Para o segundo, campo em branco: **campo vazio não afirma nada, e a
        # filiação errada afirma.**
        if not pais and i == 1:
            pais = "; ".join(n for n in (
                RCE._nome(quem.get("MAE")), RCE._nome(quem.get("PAI"))) if n)
        conj.append({
            "nome_habilitacao": nome,
            "cpf": formatar_cpf(
                (quem.get(papel) or {}).get("documento_numero")
                if str((quem.get(papel) or {}).get("documento_tipo") or "").upper()
                in ("CPF", "") else ""),
            "nome_atual": RCE._de(quem, papel, "nome_pos", dados,
                                  f"strNomePosCasamentoConjuge{i}") or nome,
            "dma": dma,
            "nacionalidade": RCE._de(quem, papel, "nacionalidade", dados) or "Brasileira",
            "estado_civil": RCE._de(quem, papel, "estado_civil", dados),
            "naturalidade": cid,
            "naturalidade_uf": uf,
            "genitores": pais,
            "nome_pos": RCE._de(quem, papel, "nome_pos", dados,
                                f"strNomePosCasamentoConjuge{i}") or nome,
        })
    return {
        "conjuges": conj,
        "regime": RCE.regime_da_certidao(
            a.get("regime_bens") or dados.get("strRegimeCasamento")),
        "hora": "",
    }


def _quadro_obito(a, quem, dados, do_fato, dma_fato) -> dict:
    nasc = RCE._de(quem, "FALECIDO", "data_nascimento", dados)
    nat, nat_uf = _cidade_uf(RCE._lugar_da_pessoa(
        quem, "FALECIDO", "naturalidade_cidade", "naturalidade_uf", dados,
        "strMunicipioNaturalidade", "strUFNaturalidade"))
    local = str(a.get("local_fato_nome") or dados.get("strNomeLocalObito")
                or "").strip()
    mun, mun_uf = _cidade_uf(RCE._lugar(
        dados.get("strMunicipioObito") or dados.get("strMunicipioFalecido"),
        dados.get("strUFObito") or dados.get("strUFFalecido")))
    gen = "; ".join(n for n in (
        RCE._nome(quem.get("MAE")), RCE._nome(quem.get("PAI"))) if n)
    return {
        "nome": str(a.get("nome") or "").strip().upper(),
        "hora": _hora(a.get("hora_fato") or dados.get("strHoraObito")),
        "local_falecimento": local,
        "municipio_falecimento": mun,
        "municipio_falecimento_uf": mun_uf,
        "sexo": RCE._sexo_por_extenso(
            RCE._de(quem, "FALECIDO", "sexo", dados, "strSexo")),
        "estado_civil": RCE._de(quem, "FALECIDO", "estado_civil", dados,
                                "strEstadoCivil"),
        "conjuge": RCE._de(quem, "FALECIDO", "nome_pos", dados,
                           "strNomeConjuge") or dados.get("strNomeConjuge") or "",
        "idade": RCE._idade_no_obito(nasc, a.get("data_fato"))
                 or str(dados.get("intIdade") or ""),
        "dma_nascimento": partes_data(nasc),
        "naturalidade": nat,
        "naturalidade_uf": nat_uf,
        "genitores": gen,
        "causa": str(a.get("causa_morte") or dados.get("strCausaMorte")
                     or "").strip(),
        "medico": str(a.get("atestante") or dados.get("strNomeMedico")
                      or "").strip(),
        "crm": str(a.get("atestante_documento") or dados.get("strCRM")
                   or dados.get("strDocumentoMedico") or "").strip(),
        "sepultamento": str(a.get("local_sepultamento")
                            or dados.get("strLocalSepultamento") or "").strip(),
        "sepultamento_mun": str(dados.get("strMunicipioSepultamento") or "").strip(),
        "sepultamento_uf": str(dados.get("strUFSepultamento") or "").strip(),
        "declarante": RCE._nome(quem.get("DECLARANTE")),
        "bens": str(dados.get("strBens") or "").strip(),
        "filhos": str(dados.get("strFilhos") or "").strip(),
    }
