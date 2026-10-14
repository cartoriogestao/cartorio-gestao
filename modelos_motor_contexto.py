# -*- coding: utf-8 -*-
"""ContextoCanônico — única montagem de campos do motor de fidelidade (2a).

Espelha `rc_certidao_quadro` + claros de `rc_certidao_odt.valores` + o que
`montar_teor` escreve, corrigindo divergências documentadas:

  - GÊMEO: caixa SIM/NÃO (`possuigemeos`), não traços de `@nomegemeos`
  - município ≠ endereço (não usar `local_fato_endereco` como município)
  - CPF coerente HTML/quadro
  - claros de óbito que o teor tem e o quadro omite (profissão, cor/raça…)
  - datas por extenso com acento (`três`)

Serventia: só via dict `sv` / `{{serventia.*}}` — nunca CNS/endereço literais
neste módulo.
"""
from __future__ import annotations

import json
import re
from typing import Any

import rc_certidao as RCE
import rc_certidao_quadro as RCQ

# Flag preparada para a prévia RCPN consumir o motor (atribuicoes_web).
# Etapa 2a/2b: NÃO aplicar em atribuicoes_web.py — só documentar.
USAR_MOTOR_NA_PREVIA_RCPN = False

_UNIDADES_ACENTO = {
    "tres": "três",
    "TRES": "TRÊS",
}


def por_extenso_acentuado(n: int, feminino: bool = False) -> str:
    """Como `livro_nucleo.por_extenso`, mas com `três` acentuado."""
    from livro_nucleo import por_extenso
    texto = por_extenso(n, feminino=feminino)
    return corrigir_tres(texto)


def data_por_extenso_acentuada(iso: Any) -> str:
    """`1987-05-03` → `… TRÊS DE …` (maiúsculas, forma das certidões)."""
    texto = str(iso or "").strip()[:10]
    partes = texto.split("-")
    if len(partes) != 3:
        return texto
    try:
        ano, mes, dia = (int(x) for x in partes)
        nome_do_mes = RCE.MESES[mes - 1]
    except (ValueError, IndexError):
        return texto
    diz_o_dia = "primeiro" if dia == 1 else por_extenso_acentuado(dia)
    return f"{diz_o_dia} de {nome_do_mes} de {por_extenso_acentuado(ano)}".upper()


def _dados(assento: dict) -> dict:
    dados = assento.get("dados") if isinstance(assento.get("dados"), dict) else {}
    if dados:
        return dados
    try:
        return json.loads(assento.get("dados_json") or "{}")
    except (TypeError, ValueError):
        return {}


def _parece_endereco(texto: str) -> bool:
    """Rua/av./nº → não é município."""
    t = str(texto or "").strip()
    if not t:
        return False
    if re.search(
        r"(?i)\b(rua|r\.|av\.|avenida|travessa|alameda|rodovia|estrada|"
        r"n[ºo°.]|numero|número|cep|quadra|lote|apto|apartamento)\b",
        t,
    ):
        return True
    # "nome, 123" com dígitos no meio costuma ser logradouro
    if re.search(r",\s*\d", t) and "/" not in t:
        return True
    return False


def _municipio_nascimento(a: dict, dados: dict, sv: dict, local: str) -> tuple[str, str]:
    """Município ≠ endereço: prefere campos de município, nunca a rua."""
    candidatos = [
        dados.get("strMunicipioNascimento"),
        a.get("local_fato_municipio"),
        dados.get("strCidadeNascimento"),
    ]
    mun = ""
    for c in candidatos:
        c = str(c or "").strip()
        if c and not _parece_endereco(c):
            mun = c
            break
    # legado: local_fato_endereco só se parecer município (Cidade/UF)
    if not mun:
        legado = str(a.get("local_fato_endereco") or "").strip()
        if legado and not _parece_endereco(legado):
            mun = legado
    uf = str(
        dados.get("strUFNascimento")
        or a.get("local_fato_uf")
        or (sv or {}).get("ri_uf")
        or ""
    ).strip()
    if mun and "/" in mun:
        mun, uf2 = RCQ._cidade_uf(mun)
        uf = uf or uf2
    # se o local já traz Cidade/UF no fim, não duplicar
    if not mun and local and "/" in local:
        return "", ""
    return mun, uf


def _gemeo_canonic(a: dict, dados: dict) -> dict[str, str]:
    """Caixa GÊMEO = SIM/NÃO; nome separado (nunca traços na caixa SIM/NÃO)."""
    gemeo_n = a.get("ibge_gemeo")
    tem = False
    nome = ""
    if gemeo_n not in (None, "") and str(gemeo_n).strip() != "":
        try:
            tem = int(gemeo_n) > 1
        except (TypeError, ValueError):
            tem = False
    bit = dados.get("bitGemeos")
    if not tem and bit and str(bit) not in ("0", "false", "False", "NÃO", "NAO", ""):
        tem = True
    nome = str(dados.get("strNomeGemeo") or a.get("nome_gemeo") or "").strip()
    # `gemeo` no formato do quadro legado (truthy para ODT.valores):
    # vazio = NÃO; nome ou "SIM" = tem gêmeo. A caixa HTML usa possuigemeos.
    return {
        "possuigemeos": "SIM" if tem else "NÃO",
        "nomegemeos": nome,
        "gemeo_caixa": "SIM" if tem else "NÃO",
        "gemeo": (nome or "SIM") if tem else "",
    }


def _cpf_canonic(a: dict, quem: dict, dados: dict, certidao: dict | None) -> str:
    """Mesma regra do quadro: CPF real preferido a SEM INFORMAÇÃO."""
    certidao = certidao or {}
    reg = quem.get("REGISTRADO") or quem.get("FALECIDO") or {}
    cpf_bruto = (
        a.get("cpf_registrado")
        or (
            reg.get("documento_numero")
            if str(reg.get("documento_tipo") or "").upper() in ("CPF", "")
            else None
        )
        or None
    )
    if not RCQ.so_digitos(cpf_bruto) or len(RCQ.so_digitos(cpf_bruto)) != 11:
        legado = RCE._documento(dados)
        if legado and legado != getattr(RCE, "SEM_INFORMACAO", "SEM INFORMAÇÃO"):
            cpf_bruto = legado
        elif RCQ.so_digitos(certidao.get("cpf")):
            cpf_bruto = certidao.get("cpf")
    return RCQ.formatar_cpf(cpf_bruto) if RCQ.so_digitos(cpf_bruto) else ""


def _obito_extras(a: dict, quem: dict, dados: dict) -> dict[str, str]:
    """Campos que `montar_teor` escreve e o quadro/molde ainda omitem."""
    fal = quem.get("FALECIDO") or {}
    return {
        "profissao": str(
            fal.get("profissao")
            or RCE._de(quem, "FALECIDO", "profissao", dados, "strProfissao")
            or ""
        ).strip(),
        "cor_raca": str(
            a.get("cor_raca") or dados.get("strRacaCor") or fal.get("cor_raca") or ""
        ).strip(),
        "domicilio": str(
            fal.get("endereco")
            or dados.get("strEnderecoFalecido")
            or dados.get("strDomicilio")
            or ""
        ).strip(),
        "numero_do": str(
            a.get("numero_do") or dados.get("strNumeroDO") or dados.get("strDO") or ""
        ).strip(),
        "eleitor": str(
            fal.get("titulo_eleitor")
            or dados.get("strTituloEleitor")
            or dados.get("strEleitor")
            or ""
        ).strip(),
    }


def contexto_de_assento(
    con,
    *,
    assento_id: int | None = None,
    certidao: dict | None = None,
    assento: dict | None = None,
    sv: dict | None = None,
) -> dict[str, Any]:
    """Monta o ContextoCanônico a partir do banco (ou dicts já carregados).

    Quando há `con` + `assento_id`/`certidao`, reusa `quadro_da_certidao` e
    corrige os campos divergentes em cima.
    """
    sv = dict(sv or {})
    certidao = dict(certidao or {})
    if assento is None and con is not None and (assento_id or certidao.get("assento_id")):
        aid = int(assento_id or certidao["assento_id"])
        row = con.execute("SELECT * FROM rc_assentos WHERE id=?", (aid,)).fetchone()
        assento = dict(row) if row else {}
        if not certidao.get("assento_id"):
            certidao["assento_id"] = aid
            certidao.setdefault("especie", assento.get("especie"))
            certidao.setdefault("matricula", assento.get("matricula"))
            certidao.setdefault("cpf", assento.get("cpf_registrado"))
    assento = dict(assento or {})
    aid = int(assento.get("id") or certidao.get("assento_id") or assento_id or 0)

    # base = quadro oficial (quando há conexão)
    if con is not None and aid and certidao.get("assento_id"):
        quadro = RCQ.quadro_da_certidao(con, certidao, sv)
    else:
        quadro = _quadro_de_dicts(assento, certidao, sv)

    especie = str(quadro.get("especie") or assento.get("especie") or "").upper()
    dados = _dados(assento)
    quem = RCE._por_papel(RCE.pessoas(con, aid)) if (con is not None and aid) else {}

    # --- correções canônicas ---
    cpf = _cpf_canonic(assento, quem, dados, certidao)
    quadro["cpf"] = cpf

    if especie == "NASCIMENTO":
        local = str(
            quadro.get("local_nascimento")
            or RCE._local_do_nascimento(dados)
            or assento.get("local_fato_nome")
            or ""
        ).strip()
        mun, mun_uf = _municipio_nascimento(assento, dados, sv, local)
        quadro["local_nascimento"] = local
        quadro["municipio_nascimento"] = mun
        quadro["municipio_nascimento_uf"] = mun_uf
        g = _gemeo_canonic(assento, dados)
        quadro.update(g)

    if especie == "OBITO":
        quadro.update(_obito_extras(assento, quem, dados))

    # datas com acento
    if assento.get("data_fato"):
        quadro["data_fato_extenso"] = data_por_extenso_acentuada(assento.get("data_fato"))
        quadro["dma_fato"] = RCQ.partes_data(assento.get("data_fato"))
    if assento.get("data_ato"):
        quadro["data_registro_extenso"] = data_por_extenso_acentuada(
            assento.get("data_ato")
        )
        quadro["dma_registro"] = RCQ.partes_data(assento.get("data_ato"))
    if certidao.get("emitida_em"):
        quadro["data_comercial"] = data_por_extenso_acentuada(
            str(certidao.get("emitida_em") or "")[:10]
        )

    # bloco serventia só por referência (sem literais)
    quadro["serventia"] = {
        "nome": sv.get("unit_name") or "",
        "cns": sv.get("ri_cns") or "",
        "cidade": sv.get("ri_cidade") or "",
        "uf": sv.get("ri_uf") or "",
        "endereco": sv.get("serventia_endereco") or "",
        "cep": sv.get("serventia_cep") or "",
        "telefone": sv.get("serventia_telefone") or "",
        "email": sv.get("serventia_email") or "",
        "titular": sv.get("serventia_titular") or "",
        "titulo": sv.get("serventia_titulo") or "",
        "cnpj": sv.get("serventia_cnpj") or "",
    }

    quadro["_meta"] = {
        "fonte": "ContextoCanônico",
        "especie": especie,
        "assento_id": aid or None,
        "template_sugerido": _chave_molde(especie),
        "usar_motor_na_previa_rcpn": USAR_MOTOR_NA_PREVIA_RCPN,
    }
    return quadro


def contexto_de_exemplo(dados: dict, *, area: str = "RCPN",
                        template_id: str = "", sv: dict | None = None) -> dict:
    """Contexto a partir de JSON de ensaio (API previa sem assento real)."""
    dados = dict(dados or {})
    sv = dict(sv or dados.get("serventia") or dados.get("sv") or {})
    # aceita forma aninhada {assento, pessoas, certidao} ou plana
    assento = dict(dados.get("assento") or {})
    certidao = dict(dados.get("certidao") or {})
    if not assento and dados.get("especie"):
        assento = {k: v for k, v in dados.items()
                   if k not in ("serventia", "sv", "pessoas", "certidao")}
    if dados.get("dados_json") and "dados_json" not in assento:
        assento["dados_json"] = dados["dados_json"]
    if dados.get("dados") and "dados" not in assento:
        assento["dados"] = dados["dados"]
    especie = str(
        assento.get("especie")
        or certidao.get("especie")
        or _especie_do_template(template_id)
        or ""
    ).upper()
    assento.setdefault("especie", especie)
    certidao.setdefault("especie", especie)
    certidao.setdefault("assento_id", assento.get("id") or 0)

    # pessoas opcionais no exemplo
    pessoas = dados.get("pessoas") or []
    quem = {}
    if isinstance(pessoas, list):
        for p in pessoas:
            if isinstance(p, dict) and p.get("papel"):
                quem[str(p["papel"]).upper()] = p
    elif isinstance(pessoas, dict):
        quem = {str(k).upper(): v for k, v in pessoas.items()}

    # monta quadro mínimo sem banco
    q = _quadro_de_dicts(assento, certidao, sv, quem=quem)
    q["cpf"] = _cpf_canonic(assento, quem, _dados(assento), certidao)
    if especie == "NASCIMENTO":
        local = str(q.get("local_nascimento") or assento.get("local_fato_nome") or "").strip()
        mun, mun_uf = _municipio_nascimento(assento, _dados(assento), sv, local)
        q["local_nascimento"] = local
        q["municipio_nascimento"] = mun
        q["municipio_nascimento_uf"] = mun_uf
        q.update(_gemeo_canonic(assento, _dados(assento)))
    if especie == "OBITO":
        q.update(_obito_extras(assento, quem, _dados(assento)))
    if assento.get("data_fato"):
        q["data_fato_extenso"] = data_por_extenso_acentuada(assento.get("data_fato"))
        q["dma_fato"] = RCQ.partes_data(assento.get("data_fato"))
    if assento.get("data_ato"):
        q["data_registro_extenso"] = data_por_extenso_acentuada(assento.get("data_ato"))
        q["dma_registro"] = RCQ.partes_data(assento.get("data_ato"))
    q["serventia"] = {
        "nome": sv.get("unit_name") or sv.get("nome") or "",
        "cns": sv.get("ri_cns") or sv.get("cns") or "",
        "cidade": sv.get("ri_cidade") or sv.get("cidade") or "",
        "uf": sv.get("ri_uf") or sv.get("uf") or "",
        "endereco": sv.get("serventia_endereco") or sv.get("endereco") or "",
        "cep": sv.get("serventia_cep") or sv.get("cep") or "",
        "telefone": sv.get("serventia_telefone") or sv.get("telefone") or "",
        "email": sv.get("serventia_email") or sv.get("email") or "",
        "titular": sv.get("serventia_titular") or sv.get("titular") or "",
        "titulo": sv.get("serventia_titulo") or sv.get("titulo") or "",
        "cnpj": sv.get("serventia_cnpj") or sv.get("cnpj") or "",
    }
    q["_meta"] = {
        "fonte": "ContextoCanônico/exemplo",
        "especie": especie,
        "area": area,
        "template_id": template_id or _chave_molde(especie),
        "usar_motor_na_previa_rcpn": USAR_MOTOR_NA_PREVIA_RCPN,
    }
    return q


def _especie_do_template(template_id: str) -> str:
    t = str(template_id or "").upper()
    if "LIVRO_E" in t:
        return "LIVRO_E"
    if "NASC" in t:
        return "NASCIMENTO"
    if "CASAM" in t:
        return "CASAMENTO"
    if "OBITO" in t or "ÓBITO" in t:
        return "OBITO"
    return ""


def _chave_molde(especie: str) -> str:
    e = str(especie or "").upper()
    return {
        "NASCIMENTO": "RC_MOLDE_NASCIMENTO",
        "CASAMENTO": "RC_MOLDE_CASAMENTO",
        "CASAMENTO_RELIGIOSO": "RC_MOLDE_CASAMENTO",
        "OBITO": "RC_MOLDE_OBITO",
    }.get(e, "")


def chave_termo(especie: str) -> str:
    """Espécie → chave RC_TERMO_* (mesma tabela de `rc_termo.MODELO_DA_ESPECIE`).

    2b: delega a `rc_termo` quando importável (fonte única); a tabela local
    fica como rede para testes sem o módulo.
    """
    e = str(especie or "").upper()
    try:
        import rc_termo as RCT
        chave = RCT.MODELO_DA_ESPECIE.get(e, "")
        if chave:
            return chave
    except Exception:  # noqa: BLE001 — rede local abaixo
        pass
    return {
        "NASCIMENTO": "RC_TERMO_NASCIMENTO",
        "NATIMORTO": "RC_TERMO_NASCIMENTO",
        "CASAMENTO": "RC_TERMO_CASAMENTO",
        "CASAMENTO_RELIGIOSO": "RC_TERMO_CASAMENTO",
        "OBITO": "RC_TERMO_OBITO",
        "LIVRO_E": "RC_TERMO_LIVRO_E",
    }.get(e, "")


def eh_template_termo(template_id: str = "", area: str = "") -> bool:
    """`RC_TERMO_*` ou `area` termo → caminho do termo (2b)."""
    t = str(template_id or "").upper()
    a = str(area or "").upper()
    return t.startswith("RC_TERMO_") or a in ("TERMO", "RC_TERMO", "RCPN_TERMO")


# ------------------------------------------------------------- textos (2b)

# Só as grafias de TÍTULO («Pessoas Naturais» / «PESSOAS NATURAIS»); a
# minúscula fica intacta porque é a forma da Lei 6.015/1973, art. 1º, § 1º, I.
_PESSOAS_NATURAIS = re.compile(
    r"\b(de|De|DE)(\s+)(Pessoas\s+Naturais|PESSOAS\s+NATURAIS)\b")


def corrigir_pessoas_naturais(texto: Any) -> str:
    """Título/rodapé: «… Civil de Pessoas Naturais» → «… Civil das Pessoas Naturais».

    Só para TÍTULOS, cabeçalhos e rodapés (nome/título da serventia, molde
    ODT). A grafia minúscula («registro civil de pessoas naturais», Lei
    6.015/1973, art. 1º, § 1º, I) não é tocada — citação de lei fica literal.
    """
    s = str(texto or "")
    if not s:
        return ""
    return _PESSOAS_NATURAIS.sub(
        lambda m: {"de": "das", "De": "Das", "DE": "DAS"}[m.group(1)]
        + m.group(2) + m.group(3), s)


_TRES = re.compile(r"\b(TRES|Tres|tres)\b")


def corrigir_tres(texto: Any) -> str:
    """`VINTE E TRES` → `VINTE E TRÊS` (e minúsculas/Título)."""
    s = str(texto or "")
    return _TRES.sub(
        lambda m: {"TRES": "TRÊS", "Tres": "Três", "tres": "três"}[m.group(1)], s)


def _quadro_de_dicts(assento: dict, certidao: dict, sv: dict,
                     quem: dict | None = None) -> dict:
    """Quadro mínimo sem conexão — para fixtures e API com dados de ensaio."""
    quem = quem or {}
    especie = str(assento.get("especie") or certidao.get("especie") or "").upper()
    titulo = RCE.titulo_do_modelo(especie) if especie else "CERTIDÃO"
    if titulo.endswith(" DE:"):
        titulo = titulo[:-4]
    dados = _dados(assento)
    q: dict[str, Any] = {
        "especie": especie,
        "titulo": titulo,
        "cpf": "",
        "matricula": RCQ.formatar_matricula(
            assento.get("matricula") or certidao.get("matricula")),
        "anotacoes": "",
        "data_fato_extenso": data_por_extenso_acentuada(assento.get("data_fato"))
        if assento.get("data_fato") else "",
        "data_registro_extenso": data_por_extenso_acentuada(assento.get("data_ato"))
        if assento.get("data_ato") else "",
        "dma_fato": RCQ.partes_data(assento.get("data_fato")),
        "dma_registro": RCQ.partes_data(assento.get("data_ato")),
        "cns": str(sv.get("ri_cns") or "").strip(),
        "casa": str(sv.get("unit_name") or "").strip(),
        "cidade": str(sv.get("ri_cidade") or "").strip(),
        "uf": str(sv.get("ri_uf") or "").strip(),
        "oficial": str(sv.get("serventia_titular") or "").strip(),
        "cargo": str(sv.get("serventia_titulo") or "").strip(),
        "rua": str(sv.get("serventia_endereco") or "").strip(),
        "cep": str(sv.get("serventia_cep") or "").strip(),
        "email": str(sv.get("serventia_email") or "").strip(),
        "telefone": str(sv.get("serventia_telefone") or "").strip(),
        "municipio_registro": RCE._lugar(sv.get("ri_cidade"), sv.get("ri_uf")),
        "nome": str(assento.get("nome") or "").strip().upper(),
        "hora": RCQ._hora(assento.get("hora_fato") or dados.get("strHoraNascimento")
                          or dados.get("strHoraObito")),
        "sexo": RCE._sexo_por_extenso(
            (quem.get("REGISTRADO") or quem.get("FALECIDO") or {}).get("sexo")
            or dados.get("strSexo")
        ),
    }
    if especie == "NASCIMENTO":
        mae = quem.get("MAE") or {}
        pai = quem.get("PAI") or {}
        q.update({
            "local_nascimento": str(
                assento.get("local_fato_nome") or dados.get("strNomeLocalNascimento")
                or ""
            ).strip(),
            "naturalidade": str(
                (quem.get("REGISTRADO") or {}).get("naturalidade_cidade")
                or dados.get("strCidade") or ""
            ).strip(),
            "naturalidade_uf": str(
                (quem.get("REGISTRADO") or {}).get("naturalidade_uf")
                or dados.get("strUF") or ""
            ).strip(),
            "mae": mae, "pai": pai,
            "filiacao": RCE._e_junta([
                str(mae.get("nome") or ""), str(pai.get("nome") or "")]),
            "avos_maternos": "",
            "avos_paternos": "",
            "genitores": [
                {"nome": str(mae.get("nome") or ""), "municipio": "", "uf": "", "avos": ""},
                {"nome": str(pai.get("nome") or ""), "municipio": "", "uf": "", "avos": ""},
            ] if (mae or pai) else [],
            "dnv": str(assento.get("dnv") or dados.get("strDeclaracaoNascidoVivo") or ""),
        })
        q.update(_gemeo_canonic(assento, dados))
    elif especie in ("CASAMENTO", "CASAMENTO_RELIGIOSO"):
        conj = []
        for i, papel in enumerate(("NUBENTE1", "NUBENTE2"), start=1):
            p = quem.get(papel) or {}
            nome = str(p.get("nome") or dados.get(f"strNomeConjuge{i}") or "")
            if i == 1:
                nome = nome or str(assento.get("nome") or "")
            if not nome:
                continue
            conj.append({
                "nome_habilitacao": nome,
                "cpf": RCQ.formatar_cpf(p.get("documento_numero")),
                "nome_atual": str(p.get("nome_pos") or nome),
                "dma": RCQ.partes_data(p.get("data_nascimento")),
                "nacionalidade": str(p.get("nacionalidade") or "Brasileira"),
                "estado_civil": str(p.get("estado_civil") or ""),
                "naturalidade": str(p.get("naturalidade_cidade") or ""),
                "naturalidade_uf": str(p.get("naturalidade_uf") or ""),
                "genitores": "",
                "nome_pos": str(p.get("nome_pos") or nome),
            })
        q["conjuges"] = conj
        q["regime"] = str(
            assento.get("regime_bens") or dados.get("strRegimeCasamento") or "")
    elif especie == "OBITO":
        fal = quem.get("FALECIDO") or {}
        q.update({
            "local_falecimento": str(
                assento.get("local_fato_nome") or dados.get("strNomeLocalObito") or ""),
            "municipio_falecimento": str(
                dados.get("strMunicipioObito") or dados.get("strMunicipioFalecido") or ""),
            "municipio_falecimento_uf": str(
                dados.get("strUFObito") or dados.get("strUFFalecido") or ""),
            "estado_civil": str(fal.get("estado_civil") or dados.get("strEstadoCivil") or ""),
            "conjuge": str(dados.get("strNomeConjuge") or ""),
            "idade": str(dados.get("intIdade") or ""),
            "dma_nascimento": RCQ.partes_data(fal.get("data_nascimento")),
            "naturalidade": str(fal.get("naturalidade_cidade") or ""),
            "naturalidade_uf": str(fal.get("naturalidade_uf") or ""),
            "genitores": RCE._e_junta([
                str((quem.get("MAE") or {}).get("nome") or ""),
                str((quem.get("PAI") or {}).get("nome") or ""),
            ]),
            "causa": str(assento.get("causa_morte") or dados.get("strCausaMorte") or ""),
            "medico": str(assento.get("atestante") or dados.get("strNomeMedico") or ""),
            "crm": str(assento.get("atestante_documento") or dados.get("strCRM") or ""),
            "sepultamento": str(
                assento.get("local_sepultamento") or dados.get("strLocalSepultamento") or ""),
            "sepultamento_mun": str(dados.get("strMunicipioSepultamento") or ""),
            "sepultamento_uf": str(dados.get("strUFSepultamento") or ""),
            "declarante": str((quem.get("DECLARANTE") or {}).get("nome") or ""),
            "bens": str(dados.get("strBens") or ""),
            "filhos": str(dados.get("strFilhos") or ""),
        })
        q.update(_obito_extras(assento, quem, dados))
    return q


def claros_do_contexto(contexto: dict, certidao: dict | None = None,
                       sv: dict | None = None) -> dict[str, str]:
    """Mesmos `@claros` do ODT — fonte única para HTML de prévia e papel."""
    import rc_certidao_odt as ODT
    certidao = certidao or {}
    sv = sv or {}
    # se serventia veio no contexto e sv está vazio, espelha
    if not sv and isinstance(contexto.get("serventia"), dict):
        s = contexto["serventia"]
        sv = {
            "unit_name": s.get("nome"),
            "ri_cns": s.get("cns"),
            "ri_cidade": s.get("cidade"),
            "ri_uf": s.get("uf"),
            "serventia_endereco": s.get("endereco"),
            "serventia_cep": s.get("cep"),
            "serventia_telefone": s.get("telefone"),
            "serventia_email": s.get("email"),
            "serventia_titular": s.get("titular"),
            "serventia_titulo": s.get("titulo"),
            "serventia_cnpj": s.get("cnpj"),
        }
    vals = ODT.valores(contexto, certidao, sv)
    # correção GÊMEO: a caixa usa SIM/NÃO do canônico, não o nome/traços
    if "possuigemeos" in contexto or "gemeo_caixa" in contexto:
        vals["@possuigemeos"] = str(
            contexto.get("possuigemeos")
            or contexto.get("gemeo_caixa")
            or vals.get("@possuigemeos")
            or "NÃO"
        )
        nome = str(contexto.get("nomegemeos") or "").strip()
        if nome:
            vals["@nomegemeos"] = nome
        elif vals.get("@possuigemeos") == "NÃO":
            # nome vazio quando não há gêmeo — traços só se o molde pedir nome
            vals["@nomegemeos"] = ""
    # claros extras de óbito (preparação; molde pode ainda não usá-los)
    for chave in ("profissao", "cor_raca", "domicilio", "numero_do", "eleitor"):
        if contexto.get(chave) is not None:
            vals[f"@{chave}"] = str(contexto.get(chave) or "") or " "
    return vals
