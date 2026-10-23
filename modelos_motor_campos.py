# -*- coding: utf-8 -*-
"""Catálogo de campos e trechos bloqueados (contrato GET do motor).

2c: cada campo traz `codigo` (`{{nome}}`, forma canônica) e `aliases`
(`@nome`, `{nome}`) — as grafias que a ingestão aceita e converte. Para
`tipo=RC_TERMO_*` entram os campos do catálogo do termo
(`rc_modelos_do_livro.campos_do`); para `tipo=RC_MOLDE_*`, os marcadores
`@...` que o molde ODT da espécie usa. Trechos bloqueados por modelo
(nascimento, casamento, óbito, Livro E; moldes e termos), com `literal`
quando o `texto` é o trecho exato que o marcador
`{{#bloqueado id}}…{{/bloqueado}}` envolve.
"""
from __future__ import annotations

from typing import Any


def campos(*, area: str = "", tipo: str = "") -> list[dict[str, Any]]:
    """Lista de claros conhecidos para o editor.

    `nome` no padrão futuro `{{campo}}`; `exemplo` sem dados reais da casa.
    """
    area_n = str(area or "").upper()
    tipo_n = str(tipo or "").upper()
    base_serventia = [
        _c("serventia.nome", "Nome da serventia", "texto", True,
           "{{serventia.nome}}", "serventia"),
        _c("serventia.cns", "CNS", "texto", True, "{{serventia.cns}}", "serventia"),
        _c("serventia.cidade", "Cidade", "texto", True,
           "{{serventia.cidade}}", "serventia"),
        _c("serventia.uf", "UF", "texto", True, "{{serventia.uf}}", "serventia"),
        _c("serventia.endereco", "Endereço", "texto", False,
           "{{serventia.endereco}}", "serventia"),
        _c("serventia.titular", "Oficial / titular", "texto", True,
           "{{serventia.titular}}", "serventia"),
        _c("serventia.titulo", "Cargo do titular", "texto", False,
           "{{serventia.titulo}}", "serventia"),
        _c("serventia.cnpj", "CNPJ", "texto", False,
           "{{serventia.cnpj}}", "serventia"),
    ]
    nasc = [
        _c("nome", "Nome do registrado", "texto", True, "MARIA DE EXEMPLO", "registrado"),
        _c("cpf", "CPF", "cpf", False, "000.000.000-00", "registrado"),
        _c("matricula", "Matrícula", "matricula", True, "0000000155…", "assento"),
        _c("data_fato_extenso", "Data de nascimento (extenso)", "texto", True,
           "três de janeiro de dois mil", "fato"),
        _c("hora", "Hora do nascimento", "texto", False, "10:30 horas", "fato"),
        _c("sexo", "Sexo", "texto", True, "FEMININO", "registrado"),
        _c("local_nascimento", "Local de nascimento", "texto", False,
           "Hospital Municipal", "fato"),
        _c("municipio_nascimento", "Município de nascimento", "texto", True,
           "Cidade Exemplo", "fato"),
        _c("municipio_nascimento_uf", "UF de nascimento", "texto", True, "MA", "fato"),
        _c("possuigemeos", "Gêmeo (SIM/NÃO)", "simnao", True, "NÃO", "registrado"),
        _c("nomegemeos", "Nome do(s) gêmeo(s)", "texto", False, "", "registrado"),
        _c("dnv", "Declaração de nascido vivo", "texto", False, "", "assento"),
        _c("filiacao", "Filiação", "texto", True, "MAE e PAI", "filiacao"),
    ]
    casam = [
        _c("regime", "Regime de bens", "texto", True,
           "Comunhão parcial de bens", "fato"),
        _c("conjuges", "Cônjuges", "lista", True, "", "partes"),
    ]
    obito = [
        _c("nome", "Nome do falecido", "texto", True, "JOÃO DE EXEMPLO", "falecido"),
        _c("cpf", "CPF", "cpf", False, "000.000.000-00", "falecido"),
        _c("causa", "Causa da morte", "texto", True, "", "fato"),
        _c("local_falecimento", "Local do falecimento", "texto", False, "", "fato"),
        _c("municipio_falecimento", "Município do falecimento", "texto", False, "", "fato"),
        _c("conjuge", "Cônjuge", "texto", False, "", "falecido"),
        _c("bens", "Deixou bens", "texto", False, "", "falecido"),
        _c("filhos", "Deixou filhos", "texto", False, "", "falecido"),
        _c("profissao", "Profissão", "texto", False, "", "falecido"),
        _c("cor_raca", "Cor/raça", "texto", False, "", "falecido"),
        _c("domicilio", "Domicílio", "texto", False, "", "falecido"),
        _c("numero_do", "Número da DO", "texto", False, "", "fato"),
        _c("eleitor", "Título de eleitor", "texto", False, "", "falecido"),
        _c("sepultamento", "Local de sepultamento", "texto", False, "", "fato"),
    ]
    termo = [
        _c("escrevente", "Escrevente / quem escreve o termo", "texto", False,
           "", "termo"),
        _c("funcao_do_escrevente", "Função de quem assina", "texto", False,
           "", "termo"),
        _c("teor", "Teor do termo", "texto", True, "", "termo"),
        _c("data_do_ato", "Data do registro (termo)", "texto", True,
           "vinte e sete (27) de setembro de dois mil e vinte e seis (2026)",
           "termo"),
        _c("data_do_fato", "Data do fato (termo)", "texto", True,
           "dez (10) de setembro de dois mil e vinte e seis (2026) - 10/09/2026",
           "termo"),
        _c("estilo_data", "Estilo da data (extenso|so_extenso|mes_numerado)", "texto",
           False, "extenso", "termo"),
        _c("registrado.genero", "Sexo do registrado (F/M) — concordância",
           "texto", False, "F", "termo"),
    ]

    out = list(base_serventia)
    if area_n in ("TERMO", "RC_TERMO", "RCPN_TERMO"):
        tipo_n = tipo_n or "TERMO"
        if "TERMO" not in tipo_n:
            tipo_n = "TERMO_" + tipo_n
    elif area_n and area_n not in ("RCPN", "RC", "TODOS", ""):
        # outras áreas: só serventia na 2a
        return out

    if not tipo_n or "NASC" in tipo_n or "MOLDE_NASC" in tipo_n:
        out += nasc
    if not tipo_n or "CASAM" in tipo_n or "MOLDE_CASAM" in tipo_n:
        out += casam
    if not tipo_n or "OBITO" in tipo_n or "ÓBITO" in tipo_n or "MOLDE_OBITO" in tipo_n:
        out += obito
    if not tipo_n or "TERMO" in tipo_n:
        out += termo

    out += _campos_do_termo(tipo_n) + _campos_do_molde(tipo_n)

    # dedup por nome
    vistos = set()
    unicos = []
    for item in out:
        if item["nome"] in vistos:
            continue
        vistos.add(item["nome"])
        unicos.append(item)
    return unicos


def _campos_do_termo(tipo_n: str) -> list[dict[str, Any]]:
    """Campos do catálogo da casa para `RC_TERMO_*` (fonte única)."""
    if not tipo_n.startswith("RC_TERMO_"):
        return []
    try:
        import rc_modelos_do_livro as LIVRO
        base = tipo_n.replace("RC_TERMO_", "")
        return [_c(c["nome"], c.get("rotulo") or c["nome"], "texto",
                   bool(c.get("exigido")), "", "termo")
                for c in LIVRO.campos_do(base)]
    except Exception:  # noqa: BLE001 — sem catálogo, fica a lista fixa
        return []


def _campos_do_molde(tipo_n: str) -> list[dict[str, Any]]:
    """Marcadores `@...` do molde ODT da espécie (só lê o .odt do pacote)."""
    if not tipo_n.startswith("RC_MOLDE_"):
        return []
    try:
        import modelos_moldes as MOLDES
        caminho = MOLDES.caminho_padrao(tipo_n)
        marcadores = sorted(MOLDES.marcadores_de(caminho.read_bytes()))
    except Exception:  # noqa: BLE001 — molde ausente na árvore de teste
        return []
    return [_c(m.lstrip("@"), m, "odt", False, "", "molde") for m in marcadores]


def trechos_bloqueados(*, area: str = "", tipo: str = "") -> list[dict[str, Any]]:
    """Blocos normativos por modelo (contrato GET /modelos/api/trechos-bloqueados).

    Campos: `id`, `texto`, `base_legal` (contrato) + `descricao`, `literal`
    (True quando `texto` é o trecho exato do modelo — o editor compara o
    miolo do marcador com ele), `marcador` e `templates`.
    `tipo` aceita `RC_MOLDE_*`, `RC_TERMO_*` ou a espécie (NASCIMENTO…).
    """
    area_n = str(area or "").upper()
    tipo_n = str(tipo or "").upper()
    if area_n and area_n not in ("RCPN", "RC", "TODOS", "TERMO", "RC_TERMO",
                                 "RCPN_TERMO"):
        return []
    esp = _especie(tipo_n)
    eh_termo = (area_n in ("TERMO", "RC_TERMO", "RCPN_TERMO")
                or tipo_n.startswith("RC_TERMO_") or "TERMO" in tipo_n)
    eh_molde = tipo_n.startswith("RC_MOLDE_") or (esp and not eh_termo)
    if eh_termo:
        return _trechos_termo(esp)
    if eh_molde and esp in _MOLDE_DA_ESPECIE:
        return _trechos_molde(esp)
    # sem tipo: tudo (moldes das três espécies + termos)
    vistos: dict[str, dict] = {}
    for e in ("NASCIMENTO", "CASAMENTO", "OBITO"):
        for t in _trechos_molde(e):
            vistos.setdefault(t["id"], t)
    for t in _trechos_termo(""):
        vistos.setdefault(t["id"], t)
    return list(vistos.values())


_MOLDE_DA_ESPECIE = {
    "NASCIMENTO": ("RC_MOLDE_NASCIMENTO", "quadro_cnj_anexo_iv",
                   "Prov. CNJ 182/2024, Anexo IV; Lei 6.015/1973, art. 54"),
    "CASAMENTO": ("RC_MOLDE_CASAMENTO", "quadro_cnj_anexo_v",
                  "Prov. CNJ 182/2024, Anexo V; Lei 6.015/1973, arts. 70–74"),
    "OBITO": ("RC_MOLDE_OBITO", "quadro_cnj_anexo_vi",
              "Prov. CNJ 182/2024, Anexo VI; Lei 6.015/1973, arts. 80–88"),
}
_NOME_DA_ESPECIE = {"NASCIMENTO": "NASCIMENTO", "CASAMENTO": "CASAMENTO",
                    "OBITO": "ÓBITO"}
# Rótulos do quadro que o molde do pacote traz e que não se editam (a
# conferência `test_trechos_literais_existem_no_molde` garante que cada um
# está no .odt — se o molde mudar, o teste avisa).
_ROTULOS_DO_QUADRO = {
    "NASCIMENTO": (
        ("rotulo_gemeo", "GÊMEO"),
        ("rotulo_dnv", "DNV"),
    ),
    "CASAMENTO": (
        ("rotulo_regime_de_bens", "REGIME DE BENS"),
        ("rotulo_nome_que_passou_a_utilizar", "NOME QUE PASSOU A UTILIZAR"),
        ("rotulo_data_da_celebracao",
         "DATA DA CELEBRAÇÃO DO CASAMENTO OU, SE FOR O CASO DE CONVERSÃO DA "
         "UNIÃO ESTÁVEL, DATA DO REGISTRO"),
    ),
    "OBITO": (
        ("rotulo_causa_da_morte", "CAUSA DA MORTE"),
        ("rotulo_medico_ou_testemunhas", "NOME DO MÉDICO OU DAS TESTEMUNHAS"),
        ("rotulo_sepultamento", "LOCAL DE SEPULTAMENTO / CREMAÇÃO"),
    ),
}


def _especie(tipo_n: str) -> str:
    if "LIVRO_E" in tipo_n:
        return "LIVRO_E"
    if "NASC" in tipo_n:
        return "NASCIMENTO"
    if "CASAM" in tipo_n:
        return "CASAMENTO"
    if "OBITO" in tipo_n or "ÓBITO" in tipo_n:
        return "OBITO"
    return ""


def _t(id_, texto, base_legal, *, descricao="", literal=False, templates=()):
    return {
        "id": id_,
        "texto": texto,
        "base_legal": base_legal,
        "descricao": descricao or texto,
        "literal": bool(literal),
        "marcador": "{{#bloqueado " + id_ + "}}…{{/bloqueado}}",
        "templates": list(templates),
    }


def _trechos_molde(esp: str) -> list[dict[str, Any]]:
    chave, quadro_id, base_quadro = _MOLDE_DA_ESPECIE[esp]
    tpl = (chave,)
    nome = _NOME_DA_ESPECIE[esp]
    out = [
        _t(quadro_id,
           f"Quadro da certidão de {nome.lower()} — campos e rótulos oficiais "
           f"do modelo nacional (não editar a ordem nem os rótulos).",
           base_quadro, templates=tpl),
        _t(f"titulo_certidao_{esp.lower()}", f"CERTIDÃO DE {nome}",
           base_quadro, descricao="Título da certidão no topo do quadro.",
           literal=True, templates=tpl),
        _t("fecho_certidao_rcpn", "O conteúdo da certidão é verdadeiro. Dou fé.",
           "Lei 6.015/1973; Código de Normas da Corregedoria estadual",
           descricao="Fecho da certidão RCPN (dou fé) — fórmula legal; local e "
                     "data vêm de {{serventia.cidade}}/{{serventia.uf}}.",
           literal=True, templates=tpl),
        _t("matricula_cnj",
           "Matrícula de 32 dígitos (CNS + acervo + serviço + ano + tipo "
           "+ termo + DV) — valor do assento, não do modelo.",
           "Prov. CNJ 28/2013 e atualizações; Prov. CNJ 182/2024", templates=tpl),
        _t("rotulo_anotacoes_averbacoes", "ANOTAÇÕES/AVERBAÇÕES", base_quadro,
           descricao="Caixa de anotações/averbações do quadro.",
           literal=True, templates=tpl),
        _t("rotulo_anotacoes_voluntarias", "ANOTAÇÕES VOLUNTÁRIAS DE CADASTRO",
           base_quadro, descricao="Caixa de anotações voluntárias de cadastro.",
           literal=True, templates=tpl),
        _t("selo_fiscalizacao",
           "Área do selo de fiscalização (número, ato, valores e consulta) — "
           "preenchida pelo selo do ato, não pelo modelo.",
           "Norma do selo da Corregedoria estadual", templates=tpl),
    ]
    for id_, rot in _ROTULOS_DO_QUADRO.get(esp, ()):
        out.append(_t(id_, rot, base_quadro, descricao=f"Rótulo «{rot}» do quadro.",
                      literal=True, templates=tpl))
    return out


# trecho bloqueado do termo: (id, regex no corpo padrão do catálogo, base legal)
_TRECHOS_TERMO = (
    ("fecho_termo_rcpn",
     r"(?:Nada mais(?: declarou)?\.\s*)?Lido e achado conforme.*?"
     r"(?:dou fé e assino|escrevi e assino)\.",
     "Lei 6.015/1973, arts. 37 e 39; relatos #63/#65",
     "Fecho do termo («Lido e achado conforme… Eu, {{escrevente}}, "
     "{{funcao_do_escrevente}}, … assino.») — quem assina vem da regra viva "
     "da serventia, não se digita."),
    # A data da celebração entrou na declaração no LD01 (21/10/2026, LRP art.
    # 70, 4º): o claro é opcional no trecho, para o ajuste de antes da casa
    # continuar sendo reconhecido.
    ("declaracao_casados_regime",
     r"E, não havendo impedimento, foram declarados casados"
     r"(?:\{frase_da_celebracao\})? sob o regime de \{regime_bens\}\.",
     "Código Civil, art. 1.535; Lei 6.015/1973, art. 70",
     "Declaração de casamento, a data da celebração e o regime de bens."),
    ("naturalidade_art54",
     r"\{frase_naturalidade\}",
     "Lei 6.015/1973, art. 54, § 4º",
     "Naturalidade declarada (frase montada pelo sistema)."),
)


def _trechos_termo(esp: str) -> list[dict[str, Any]]:
    tpl = (f"RC_TERMO_{esp}",) if esp else (
        "RC_TERMO_NASCIMENTO", "RC_TERMO_CASAMENTO", "RC_TERMO_OBITO",
        "RC_TERMO_LIVRO_E")
    corpo = ""
    if esp:
        try:
            import rc_modelos_do_livro as LIVRO
            corpo = LIVRO.modelo(esp)["texto"]
        except Exception:  # noqa: BLE001 — sem catálogo: só descrição
            corpo = ""
    out = []
    for id_, rx, base, desc in _TRECHOS_TERMO:
        literal = ""
        if corpo:
            import re
            m = re.search(rx, corpo, re.DOTALL)
            literal = m.group(0) if m else ""
            if id_ == "naturalidade_art54":
                literal = ""  # claro de frase: descrito, não marcado
            if not m and id_ != "fecho_termo_rcpn":
                continue  # o trecho não existe neste termo
        elif id_ != "fecho_termo_rcpn":
            continue
        out.append(_t(id_, literal or desc, base, descricao=desc,
                      literal=bool(literal), templates=tpl))
    out.append(_t(
        "data_termo_extenso_algarismo",
        "Datas do termo por extenso com repetição em algarismos (dia e ano); "
        "mês por extenso.",
        "Código de Normas CGJ/TJMA, art. 795, § 4º", templates=tpl))
    out.append(_t(
        "matricula_cnj",
        "Matrícula de 32 dígitos (CNS + acervo + serviço + ano + tipo + termo "
        "+ DV) — valor do assento, não do modelo.",
        "Prov. CNJ 28/2013 e atualizações; Prov. CNJ 182/2024", templates=tpl))
    return out


def _c(nome, rotulo, tipo, obrigatorio, exemplo, grupo):
    return {
        "nome": nome,
        "rotulo": rotulo,
        "tipo": tipo,
        "obrigatorio": bool(obrigatorio),
        "exemplo": exemplo,
        "grupo": grupo,
        # 2c: forma canônica + grafias aceitas na ingestão
        "codigo": "{{" + nome + "}}",
        "aliases": ["@" + nome, "{" + nome + "}"],
    }
