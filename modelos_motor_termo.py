# -*- coding: utf-8 -*-
"""Termos RC_TERMO_* no motor de fidelidade — Etapa 2b (SANDBOX).

ContextoCanônico do TERMO + render de prévia (HTML) e texto para papel.

O QUE CORRIGE (só na prévia/papel — o banco não é tocado; termo congelado
continua congelado, `rc_termo.congelar` segue sendo o único que grava):

  1. **Tags HTML**: `<strong>` e cia. não sobram literais no texto de papel
     (o nome em negrito vira negrito de verdade só no HTML da prévia).
  2. **Gênero**: «sendo filho de» → «sendo filha de» quando a registrada é
     do sexo feminino; «Inscrito no CPF» do registrado idem; qualificação de
     cada pessoa concorda com o sexo dela (brasileiro/brasileira, inscrito/
     inscrita, nascido/nascida, domiciliado/domiciliada…); «o(a) declarante»
     vira «a/o declarante» quando o sexo do declarante é conhecido.
  3. **Fecho**: «Eu, ____________, Oficial» → nome de quem assina, preenchido
     pela regra viva (`rc_termo.quem_assina_da_serventia`) ou pelo escrevente
     informado; o «Oficial» genérico vira a função real quando ela é outra.
  4. **Datas**: forma única e coerente (ver `ESTILO_DATA_TERMO`), sem o
     «setembro (9)» e sem dia/ano pela metade; `TRES` → `TRÊS`.
  5. **Título**: «… Civil de Pessoas Naturais» → «… Civil das Pessoas
     Naturais» no cabeçalho/serventia (não no corpo).

Sem dado de serventia no código: tudo vem do dict `sv` (`serventia.dados`).
"""
from __future__ import annotations

import re
import sqlite3
from typing import Any

from bd_nativo import banco
from modelos_motor_contexto import (
    chave_termo,
    corrigir_pessoas_naturais,
    corrigir_tres,
    por_extenso_acentuado,
)
from modelos_motor_html import escapar, html_para_texto_impressao, parece_html

# --------------------------------------------------------------- datas
#
# ESTILO DA DATA NO TERMO — nomes alinhados com o catálogo da casa
# (`rc_modelos_do_livro.data_do_termo`, decisão do teste cart em 05/10/2026):
#   "extenso"      → «vinte e sete (27) de setembro de dois mil e vinte e seis
#                    (2026)»: dia e ano por extenso COM o algarismo entre
#                    parênteses (art. 795, § 4º, Código de Normas), mês SÓ pelo
#                    nome, sem «(9)». PADRÃO do motor e do catálogo.
#   "so_extenso"   → só por extenso, sem algarismo (forma da certidão,
#                    `rc_certidao.data_por_extenso`).
#   "mes_numerado" → forma antiga com «setembro (9)» — só para reproduzir
#                    termo antigo; não é mais o que o catálogo escreve.
# Aliases aceitos (compatibilidade 2b): "padrao" e "casa" = "extenso".
ESTILO_DATA_TERMO = "extenso"
ESTILOS_DATA = ("extenso", "so_extenso", "mes_numerado")
ALIASES_ESTILO_DATA = {"padrao": "extenso", "casa": "extenso",
                       "padrão": "extenso"}


def estilo_de_data(estilo: Any) -> str:
    """Nome do estilo (aceita aliases); desconhecido → `ESTILO_DATA_TERMO`."""
    e = str(estilo or "").strip().lower()
    e = ALIASES_ESTILO_DATA.get(e, e)
    return e if e in ESTILOS_DATA else ESTILO_DATA_TERMO


MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro")

# UF → nome do Estado (dado público da federação, não da serventia)
UF_ESTADO = {
    "AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas",
    "BA": "Bahia", "CE": "Ceará", "DF": "Distrito Federal",
    "ES": "Espírito Santo", "GO": "Goiás", "MA": "Maranhão",
    "MT": "Mato Grosso", "MS": "Mato Grosso do Sul", "MG": "Minas Gerais",
    "PA": "Pará", "PB": "Paraíba", "PR": "Paraná", "PE": "Pernambuco",
    "PI": "Piauí", "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte",
    "RS": "Rio Grande do Sul", "RO": "Rondônia", "RR": "Roraima",
    "SC": "Santa Catarina", "SP": "São Paulo", "SE": "Sergipe",
    "TO": "Tocantins",
}

_VALOR = {
    "um": 1, "uma": 1, "primeiro": 1, "dois": 2, "duas": 2, "tres": 3,
    "três": 3, "quatro": 4, "cinco": 5, "seis": 6, "sete": 7, "oito": 8,
    "nove": 9, "dez": 10, "onze": 11, "doze": 12, "treze": 13,
    "catorze": 14, "quatorze": 14, "quinze": 15, "dezesseis": 16,
    "dezessete": 17, "dezoito": 18, "dezenove": 19, "vinte": 20,
    "trinta": 30, "quarenta": 40, "cinquenta": 50, "sessenta": 60,
    "setenta": 70, "oitenta": 80, "noventa": 90, "cem": 100, "cento": 100,
    "duzentos": 200, "duzentas": 200, "trezentos": 300, "trezentas": 300,
    "quatrocentos": 400, "quatrocentas": 400, "quinhentos": 500,
    "quinhentas": 500, "seiscentos": 600, "seiscentas": 600,
    "setecentos": 700, "setecentas": 700, "oitocentos": 800,
    "oitocentas": 800, "novecentos": 900, "novecentas": 900,
}
_PALAVRA_NUM = "|".join(sorted(list(_VALOR) + ["mil"], key=len, reverse=True))
_NUM = rf"(?:{_PALAVRA_NUM})(?:\s+(?:e\s+)?(?:{_PALAVRA_NUM}))*"
_MES_RE = "|".join(MESES + ("marco",))
_DATA_RE = re.compile(
    rf"\b(?P<dia>{_NUM})(?:\s*\((?P<dian>\d{{1,2}})\))?\s+de\s+"
    rf"(?P<mes>{_MES_RE})(?:\s*\((?P<mesn>\d{{1,2}})\))?\s+de\s+"
    rf"(?P<ano>{_NUM})(?:\s*\((?P<anon>\d{{4}})\))?(?![\wÀ-ú])",
    re.IGNORECASE,
)


def numero_de_extenso(texto: str) -> int | None:
    """«dois mil e vinte e um» → 2021; «vinte e sete» → 27. Só calcula."""
    total = atual = 0
    achou = False
    for palavra in str(texto or "").lower().split():
        if palavra == "e":
            continue
        if palavra == "mil":
            atual = (atual or 1) * 1000
            total += atual
            atual = 0
            achou = True
            continue
        v = _VALOR.get(palavra)
        if v is None:
            return None
        atual += v
        achou = True
    return (total + atual) if achou else None


def _dia_por_extenso(dia: int) -> str:
    return "primeiro" if dia == 1 else por_extenso_acentuado(dia)


def data_termo(iso_ou_partes: Any, *, estilo: str | None = None,
               com_numeros: bool = False) -> str:
    """Data do termo no estilo pedido. `iso` (`2021-09-09`) ou `(a, m, d)`."""
    estilo = estilo_de_data(estilo)
    if isinstance(iso_ou_partes, (tuple, list)):
        ano, mes, dia = (int(x) for x in iso_ou_partes)
    else:
        texto = str(iso_ou_partes or "").strip()[:10]
        partes = texto.split("-")
        if len(partes) != 3 or not all(p.isdigit() for p in partes):
            return texto
        ano, mes, dia = (int(p) for p in partes)
    if not 1 <= mes <= 12 or not 1 <= dia <= 31:
        return f"{ano:04d}-{mes:02d}-{dia:02d}"
    nome_mes = MESES[mes - 1]
    d_ext, a_ext = _dia_por_extenso(dia), por_extenso_acentuado(ano)
    if estilo == "so_extenso":
        fora = f"{d_ext} de {nome_mes} de {a_ext}"
    elif estilo == "mes_numerado":
        fora = (f"{d_ext} ({dia:02d}) de {nome_mes} ({mes}) de "
                f"{a_ext} ({ano})")
    else:
        fora = f"{d_ext} ({dia:02d}) de {nome_mes} de {a_ext} ({ano})"
    if com_numeros:
        fora += f" - {dia:02d}/{mes:02d}/{ano}"
    return fora


def normalizar_datas_no_texto(texto: str, estilo: str | None = None) -> str:
    """Reescreve toda data por extenso do texto numa forma só.

    Acha «nove (9) de setembro (9) de dois mil e vinte e um», «vinte e sete
    (27) de setembro (9) de dois mil e vinte e seis (2026)», «VINTE E TRES DE
    MAIO DE …» etc. e devolve no `estilo`. Se o algarismo e o extenso
    divergirem, vale o algarismo (é o que o escrevente conferiu) — e a data
    não é reescrita se não fechar (dia/mês/ano inválidos).
    """
    def _troca(m: re.Match) -> str:
        bruto = m.group(0)
        try:
            dia = int(m.group("dian")) if m.group("dian") else numero_de_extenso(m.group("dia"))
            ano = int(m.group("anon")) if m.group("anon") else numero_de_extenso(m.group("ano"))
            mes_nome = m.group("mes").lower().replace("marco", "março")
            mes = MESES.index(mes_nome) + 1
        except (TypeError, ValueError):
            return bruto
        if not dia or not ano or not 1 <= dia <= 31 or ano < 1000:
            return bruto
        novo = data_termo((ano, mes, dia), estilo=estilo)
        letras = [c for c in bruto if c.isalpha()]
        if letras and all(c.isupper() for c in letras):
            novo = novo.upper()
        return novo

    return _DATA_RE.sub(_troca, str(texto or ""))


# --------------------------------------------------------------- gênero

_PARES_GENERO = (
    ("brasileiro", "brasileira"), ("estrangeiro", "estrangeira"),
    ("naturalizado", "naturalizada"), ("solteiro", "solteira"),
    ("casado", "casada"), ("divorciado", "divorciada"),
    ("separado", "separada"), ("viúvo", "viúva"), ("viuvo", "viuva"),
    ("nascido", "nascida"), ("inscrito", "inscrita"),
    ("portador", "portadora"), ("domiciliado", "domiciliada"),
    ("lavrador", "lavradora"), ("agricultor", "agricultora"),
    ("aposentado", "aposentada"), ("professor", "professora"),
    ("eleitor", "eleitora"), ("falecido", "falecida"),
    ("sepultado", "sepultada"), ("identificado", "identificada"),
)
_PARA_F = {m: f for m, f in _PARES_GENERO}
_PARA_M = {f: m for m, f in _PARES_GENERO}
_PALAVRA_GENERO = re.compile(
    r"\b(" + "|".join(sorted(list(_PARA_F) + list(_PARA_M), key=len, reverse=True))
    + r")\b(?:\(a\))?", re.IGNORECASE)

_PAPEL_F = {"MAE", "AVO_MATERNA", "AVO_PATERNA", "MAE_NUBENTE1", "MAE_NUBENTE2"}
_PAPEL_M = {"PAI", "AVO_MATERNO", "AVO_PATERNO", "PAI_NUBENTE1", "PAI_NUBENTE2"}


def _caixa_como(modelo: str, palavra: str) -> str:
    if modelo.isupper():
        return palavra.upper()
    if modelo[:1].isupper():
        return palavra[:1].upper() + palavra[1:]
    return palavra


def concordar(palavra: str, feminino: bool) -> str:
    """`brasileiro`+F → `brasileira`; preserva caixa; tira o «(a)»."""
    base = re.sub(r"\(a\)$", "", palavra)
    chave = base.lower()
    alvo = (_PARA_F.get(chave) or chave) if feminino else (_PARA_M.get(chave) or chave)
    return _caixa_como(base, alvo)


def genero_de(pessoa: dict | None, papel: str = "") -> str:
    """'F' | 'M' | '' — sexo informado; senão palavra da nacionalidade/estado
    civil; senão o papel (MÃE/AVÓ → F; PAI/AVÔ → M). Só calcula.

    O sexo informado SEMPRE vence (há casais do mesmo sexo e dado trocado no
    acervo — lição de `rc_modelos_do_livro`); o papel é só a rede final.
    """
    p = pessoa or {}
    s = str(p.get("sexo") or "").strip().upper()[:1]
    if s in ("F", "M"):
        return s
    for campo in ("nacionalidade", "estado_civil"):
        v = str(p.get(campo) or "").strip().lower()
        if v in _PARA_M:
            return "F"
        if v in _PARA_F:
            return "M"
    papel = str(papel or p.get("papel") or "").upper()
    if papel in _PAPEL_F:
        return "F"
    if papel in _PAPEL_M:
        return "M"
    return ""


def _pessoa_concordada(p: dict, papel: str) -> dict:
    """Cópia da pessoa com sexo (rede) e nacionalidade/estado civil concordados."""
    q = dict(p)
    g = genero_de(q, papel)
    if g and not str(q.get("sexo") or "").strip():
        q["sexo"] = g
    if g:
        for campo in ("nacionalidade", "estado_civil", "profissao"):
            v = str(q.get(campo) or "").strip()
            if v and " " not in v:
                q[campo] = concordar(v, g == "F")
    return q


_FIM_QUALIFICACAO = re.compile(
    r",\s*e\s+de\b|;\s|\.\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ])|\bsendo\s+filh|,\s*apresentou\b|"
    r",\s*e\s+declarou\b|\bdeclarou\b|\bnasceu\b|\bfaleceu\b|\bque\s+recebeu\b|"
    r",\s*tendo\b|\be\s+(?:a|o)\s+contraente\b|\bcompareceu\b",
    re.IGNORECASE)


def concordar_qualificacoes(texto: str, pessoas: dict[str, dict]) -> tuple[str, int]:
    """Ajusta o gênero das palavras da qualificação logo após cada nome.

    O trecho vai do fim do nome até a próxima fronteira (`, e de`, `sendo
    filho`, `declarou`, outro nome…), no máximo 350 caracteres — nunca o
    texto inteiro. Devolve (texto, quantas trocas).
    """
    trocas = 0
    nomes = []
    for papel, p in (pessoas or {}).items():
        nome = str((p or {}).get("nome") or "").strip()
        g = genero_de(p, papel)
        if len(nome) >= 5 and g:
            nomes.append((nome, g))
    if not nomes:
        return texto, 0
    todos = [n for n, _ in nomes]
    for nome, g in sorted(nomes, key=lambda x: len(x[0]), reverse=True):
        pos = 0
        while True:
            i = texto.find(nome, pos)
            if i < 0:
                break
            ini = i + len(nome)
            # nome inteiro (não pedaço de outro nome mais longo)
            antes = texto[i - 1:i]
            depois = texto[ini:ini + 2]
            if antes.isalpha() or depois[:1].isalpha() or (
                    depois[:1] == " " and depois[1:2].isupper()):
                pos = ini
                continue
            fim = min(len(texto), ini + 350)
            trecho = texto[ini:fim]
            corte = len(trecho)
            m = _FIM_QUALIFICACAO.search(trecho)
            if m:
                corte = m.start()
            for outro in todos:
                if outro == nome:
                    continue
                j = trecho.find(outro)
                if 0 <= j < corte:
                    corte = j
            pedaco = trecho[:corte]
            novo = _PALAVRA_GENERO.sub(
                lambda mm: concordar(mm.group(0), g == "F"), pedaco)
            if novo != pedaco:
                trocas += sum(1 for a, b in zip(
                    _PALAVRA_GENERO.findall(pedaco),
                    _PALAVRA_GENERO.findall(novo)) if a.lower() != b.lower())
                texto = texto[:ini] + novo + texto[ini + len(pedaco):]
            pos = ini + len(novo)
    return texto, trocas


def corrigir_genero_do_principal(texto: str, especie: str, genero: str) -> tuple[str, list[str]]:
    """Filiação / frases do registrado ou falecido, pelo sexo dele."""
    if genero not in ("F", "M"):
        return texto, []
    fem = genero == "F"
    feitas: list[str] = []
    e = str(especie or "").upper()

    def _sub(padrao, troca, rotulo, flags=0):
        nonlocal texto
        novo = re.sub(padrao, troca, texto, flags=flags)
        if novo != texto:
            feitas.append(rotulo)
            texto = novo

    if e in ("NASCIMENTO", "NATIMORTO"):
        _sub(r"\b(sendo\s+)(filh)(?:o|a)(?:\(a\))?(\s+de)\b",
             lambda m: m.group(1) + ("filha" if fem else "filho") + m.group(3),
             "filiação (filho/filha)", re.IGNORECASE)
        # « Inscrito no CPF n.º …» do registrado (frase_cpf, início de frase)
        _sub(r"((?:^|[.!?]\s+))(Inscrit)(?:o|a)(?:\(a\))?(\s+no\s+CPF)",
             lambda m: m.group(1) + ("Inscrita" if fem else "Inscrito") + m.group(3),
             "CPF do registrado (inscrito/inscrita)")
    elif e == "OBITO":
        _sub(r"((?:^|[.!?]\s+))(Filh)(?:o|a)(?:\(a\))?(\s+de)\b",
             lambda m: m.group(1) + ("Filha" if fem else "Filho") + m.group(3),
             "filiação do falecido")
        _sub(r"\bfilho\(a\)(\s+de)\b",
             lambda m: ("filha" if fem else "filho") + m.group(1),
             "filiação do falecido")
        for m_, f_ in (("Sepultado", "Sepultada"), ("Era eleitor", "Era eleitora"),
                       ("era eleitor", "era eleitora")):
            alvo, troca = (m_, f_) if fem else (f_, m_)
            _sub(rf"\b{alvo}\b", troca, "frases do falecido")
        _sub(r"\b(Era\s+)(\w+)(\.)",
             lambda m: m.group(1) + concordar(m.group(2), fem) + m.group(3),
             "estado civil do falecido")
    return texto, feitas


def corrigir_declarante(texto: str, genero: str) -> str:
    if genero == "F":
        texto = re.sub(r"\bo\(a\)\s+declarante\b", "a declarante", texto)
        texto = re.sub(r"\bo\(a\)\s+Sr\.\(a\)", "a Sra.", texto)
    elif genero == "M":
        texto = re.sub(r"\bo\(a\)\s+declarante\b", "o declarante", texto)
        texto = re.sub(r"\bo\(a\)\s+Sr\.\(a\)", "o Sr.", texto)
    return texto


# --------------------------------------------------------------- fecho

_FECHO = re.compile(
    r"(Eu,\s*)(_{3,})(\s*,\s*)?(_{3,}|Oficial(?=\s*[,.]))?")


def preencher_fecho(texto: str, escrevente: str, funcao: str) -> tuple[str, bool]:
    """«Eu, ____________, Oficial» → «Eu, NOME, Função». Só calcula.

    Só mexe no traço que vem DEPOIS de «Eu,» (moldura de quem assina) — a
    linha de assinatura do acervo («Em testemunho da verdade. ______») fica,
    como em `rc_termo._o_traco_ficou`. Sem nome de quem assina, nada muda.
    """
    escrevente = str(escrevente or "").strip()
    funcao = str(funcao or "").strip()
    if not escrevente:
        return texto, False

    def _troca(m: re.Match) -> str:
        sep = m.group(3) or ", "
        depois = m.group(4)
        if depois is None:
            return f"{m.group(1)}{escrevente}{m.group(3) or ''}"
        if depois.startswith("_") or (
                funcao and depois == "Oficial" and funcao.lower() != "oficial"):
            return f"{m.group(1)}{escrevente}{sep}{funcao or depois}"
        return f"{m.group(1)}{escrevente}{sep}{depois}"

    novo = _FECHO.sub(_troca, texto)
    return novo, novo != texto


# --------------------------------------------------------------- serventia

def serventia_do_termo(sv: dict | None, *, escrevente: str = "",
                       funcao: str = "") -> dict:
    """A serventia como o termo lê (mesmo desenho de `atribuicoes_web._servent`).

    Aceita `serventia.dados()` (unit_name, serventia_titular, ri_cidade…) ou o
    formato curto (nome, cidade, uf). Nada fixo: o Estado sai da UF.
    """
    s = dict(sv or {})
    titular = str(s.get("serventia_titular") or s.get("titular") or "").strip()
    substituta = str(s.get("ri_substituta") or s.get("substituta") or "").strip()
    titulo = str(s.get("serventia_titulo") or s.get("titulo") or "").strip()
    cidade = str(s.get("ri_cidade") or s.get("cidade") or "").strip()
    uf = str(s.get("ri_uf") or s.get("uf") or "").strip().upper()
    estado = str(s.get("ri_estado") or s.get("estado") or UF_ESTADO.get(uf, "")).strip()
    titulo_sub = str(s.get("ri_substituta_titulo") or "").strip()
    out = {
        "nome": titular,
        "cidade": cidade, "uf": uf, "estado": estado,
        "ri_cidade": cidade, "ri_uf": uf,
        "registrador": substituta or titular,
        "titulo": (titulo_sub or "Tabeliã Registradora Substituta")
        if substituta else titulo,
        "unit_name": corrigir_pessoas_naturais(
            s.get("unit_name") or s.get("nome_serventia") or ""),
        "serventia_titulo": corrigir_pessoas_naturais(titulo),
    }
    if escrevente:
        out["escrevente"] = str(escrevente).strip()
    if funcao:
        out["funcao"] = str(funcao).strip()
    return out


def quem_assina(sv_termo: dict) -> dict:
    """`{escrevente, funcao_do_escrevente}` pela regra viva da casa."""
    try:
        import rc_termo as RCT
        return RCT.quem_assina_da_serventia(sv_termo)
    except Exception:  # noqa: BLE001 — mesma regra, local
        quem = next((str(sv_termo.get(k) or "").strip() for k in
                     ("escrevente", "registrador", "nome")
                     if str(sv_termo.get(k) or "").strip()), "")
        func = next((str(sv_termo.get(k) or "").strip() for k in
                     ("funcao", "titulo")
                     if str(sv_termo.get(k) or "").strip()), "Oficial")
        return {"escrevente": quem, "funcao_do_escrevente": func}


def _cabecalho(sv: dict, especie: str, assento: dict) -> dict:
    s = dict(sv or {})
    for k in ("unit_name", "serventia_titulo"):
        if s.get(k):
            s[k] = corrigir_pessoas_naturais(s[k])
    try:
        import rc_cabecalho as CAB
        try:
            cab = CAB.montar(s, especie=especie or None,
                             termo=assento.get("numero"),
                             livro=assento.get("livro_volume") or assento.get("livro"),
                             folha=assento.get("folha"))
        except CAB.CabecalhoError:
            cab = CAB.montar(s, termo=assento.get("numero"),
                             livro=assento.get("livro_volume"),
                             folha=assento.get("folha"))
    except ImportError:
        cab = {"unidade": s.get("unit_name") or "",
               "titular": s.get("serventia_titular") or "",
               "titular_qualidade": s.get("serventia_titulo") or "",
               "endereco": "", "contato": "", "titulo_do_ato": "",
               "termo": "", "livro": "", "folha": ""}
    for k in ("unidade", "titular_qualidade", "titulo_do_ato"):
        cab[k] = corrigir_pessoas_naturais(cab.get(k) or "")
    return cab


# --------------------------------------------------------------- contexto

def _por_papel(pessoas: Any) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if isinstance(pessoas, dict):
        for k, v in pessoas.items():
            if isinstance(v, dict):
                out.setdefault(str(k).upper(), dict(v, papel=str(k).upper()))
        return out
    for p in pessoas or []:
        if isinstance(p, dict) and p.get("papel"):
            out.setdefault(str(p["papel"]).upper(), dict(p))
    return out


def _lista_pessoas(pessoas: Any) -> list[dict]:
    if isinstance(pessoas, dict):
        return [dict(v, papel=str(k).upper()) for k, v in pessoas.items()
                if isinstance(v, dict)]
    return [dict(p) for p in (pessoas or []) if isinstance(p, dict)]


def _montar_texto(assento: dict, pessoas: list[dict], chave: str,
                  sv_termo: dict, assina: dict, corpo: str | None,
                  documentos: list | None = None) -> str:
    """Monta pelo catálogo da casa (`rc_modelos_do_livro`) — sem gravar."""
    import rc_modelos_do_livro as LIVRO
    import rc_termo as RCT
    base = chave.replace("RC_TERMO_", "")
    if corpo is None:
        corpo = LIVRO.modelo(base)["texto"]
    ruim = LIVRO.conferir_corpo(base, corpo)
    if ruim:
        raise ValueError(ruim)
    comum = {"sv": RCT._como_as_pontes_leem(sv_termo), **assina}
    if chave == "RC_TERMO_CASAMENTO":
        r = LIVRO.montar_casamento_do_assento(
            assento, pessoas, corpo, documentos=documentos or [], **comum)
    elif chave == "RC_TERMO_LIVRO_E":
        r = LIVRO.montar_livro_e_do_assento(assento, pessoas, corpo, **comum)
    elif chave == "RC_TERMO_OBITO":
        import rc_marcas_do_obito as MARCAS
        r = LIVRO.montar_obito_do_assento(
            assento, pessoas, corpo,
            marcas={m["chave"]: m["estado"] for m in MARCAS.do_assento(assento)},
            **comum)
    else:
        r = LIVRO.montar_do_assento(assento, pessoas, corpo, **comum)
    return r["texto"]


def corrigir_texto_termo(texto: str, *, especie: str, pessoas: dict[str, dict],
                         genero_principal: str, assina: dict,
                         estilo_data: str | None = None) -> tuple[str, list[str]]:
    """Pipeline de correção do texto do termo para PAPEL. Só calcula."""
    correcoes: list[str] = []
    bruto = str(texto or "")
    t = html_para_texto_impressao(bruto)
    if parece_html(bruto) or "&lt;" in bruto:
        correcoes.append("tags HTML removidas")
    # texto corrido (art. 795, § 2º): quebras viram espaço
    # O `(?<!\s)` só deixa a busca começar no INÍCIO de um trecho de brancos
    # (CodeQL py/polynomial-redos, 28/10/2026). Sem ele, um trecho longo de
    # espaços sem quebra era varrido de novo a partir de cada espaço — tempo
    # quadrático. O que casa é o mesmo: a primeira tentativa de um trecho já
    # começava no início dele e o tomava inteiro.
    t = re.sub(r"(?<!\s)\s*\n\s*", " ", t).strip()
    novo = normalizar_datas_no_texto(t, estilo_data)
    if novo != t:
        correcoes.append(f"datas no estilo «{estilo_de_data(estilo_data)}»")
        t = novo
    novo = corrigir_tres(t)
    if novo != t:
        correcoes.append("TRES → TRÊS")
        t = novo
    t, feitas = corrigir_genero_do_principal(t, especie, genero_principal)
    correcoes += feitas
    t, n = concordar_qualificacoes(t, pessoas)
    if n:
        correcoes.append(f"gênero na qualificação ({n})")
    dec = pessoas.get("DECLARANTE") or {}
    novo = corrigir_declarante(t, genero_de(dec, "DECLARANTE"))
    if novo != t:
        correcoes.append("o(a) declarante → gênero do declarante")
        t = novo
    t, mudou = preencher_fecho(t, assina.get("escrevente", ""),
                               assina.get("funcao_do_escrevente", ""))
    if mudou:
        correcoes.append("fecho «Eu, ____» preenchido")
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r"(?<!\s)\s+([,.;:])", r"\1", t)  # `(?<!\s)`: ver a quebra acima
    return t.strip(), correcoes


ESPECIE_DO_TERMO = {
    "RC_TERMO_NASCIMENTO": "NASCIMENTO",
    "RC_TERMO_CASAMENTO": "CASAMENTO",
    "RC_TERMO_OBITO": "OBITO",
    "RC_TERMO_LIVRO_E": "LIVRO_E",
}


def _tem_dados_de_ato(assento: dict) -> bool:
    return any(str(assento.get(k) or "").strip() for k in
               ("nome", "data_ato", "data_fato", "numero", "matricula"))


def corpo_de_exemplo(corpo: str | None, chave: str, sv_termo: dict,
                     assina: dict) -> str:
    """Corpo do termo com os claros visíveis (`[campo]`). Só calcula.

    Serventia e quem assina entram (vêm do cadastro); o resto fica entre
    colchetes — nada inventado.
    """
    texto = corpo
    if not texto:
        try:
            import rc_modelos_do_livro as LIVRO
            texto = LIVRO.modelo(chave.replace("RC_TERMO_", ""))["texto"]
        except Exception:  # noqa: BLE001
            return ""
    conhecidos = {
        "cidade_do_ato": sv_termo.get("cidade") or "",
        "estado_do_ato": sv_termo.get("estado") or "",
        "uf_do_ato": sv_termo.get("uf") or "",
        "escrevente": assina.get("escrevente") or "",
        "funcao_do_escrevente": assina.get("funcao_do_escrevente") or "",
    }

    def _claro(m: re.Match) -> str:
        nome = m.group(1)
        return str(conhecidos.get(nome) or f"[{nome}]")
    return re.sub(r"\{(\w+)\}", _claro, str(texto))


def contexto_termo(
    dados: dict | None = None,
    *,
    assento: dict | None = None,
    pessoas: Any = None,
    sv: dict | None = None,
    template_id: str = "",
    escrevente: str = "",
    funcao: str = "",
    estilo_data: str | None = None,
    remontar: bool = False,
    corpo: str | None = None,
    documentos: list | None = None,
) -> dict[str, Any]:
    """ContextoCanônico do TERMO (sem banco).

    `dados` pode ser o JSON de ensaio (forma plana do fixture ou
    `{assento, pessoas}`). Teor existente (`teor`, `teor_html_cru`) é
    CORRIGIDO para papel; sem teor (ou `remontar=True`) monta pelo catálogo.
    """
    dados = dict(dados or {})
    sv = dict(sv or dados.get("serventia") or dados.get("sv") or {})
    assento = dict(assento or dados.get("assento") or {})
    if not assento:
        assento = {k: v for k, v in dados.items()
                   if k not in ("serventia", "sv", "pessoas", "certidao",
                                "escrevente", "funcao", "estilo_data")}
    if pessoas is None:
        pessoas = dados.get("pessoas") or []
    escrevente = escrevente or str(dados.get("escrevente") or "")
    funcao = funcao or str(dados.get("funcao") or dados.get("funcao_do_escrevente") or "")
    estilo_data = estilo_de_data(estilo_data or dados.get("estilo_data"))

    avisos: list[str] = []
    especie = str(assento.get("especie") or "").upper()
    if not especie:
        especie = ESPECIE_DO_TERMO.get(str(template_id or "").upper(), "")
    chave_esp = chave_termo(especie)
    chave_pedida = str(template_id or "").upper()
    if chave_pedida.startswith("RC_TERMO_") and chave_esp and chave_pedida != chave_esp:
        avisos.append(
            f"template {chave_pedida} não serve a espécie {especie}: a espécie "
            f"manda no modelo — usando {chave_esp}.")
    chave = chave_esp or (chave_pedida if chave_pedida.startswith("RC_TERMO_") else "")

    lista = _lista_pessoas(pessoas)
    principal_papel = "FALECIDO" if especie == "OBITO" else "REGISTRADO"
    dados_a = assento.get("dados") if isinstance(assento.get("dados"), dict) else {}
    principal_bruto = next((p for p in lista if str(p.get("papel") or "").upper()
                            == principal_papel), None)
    sexo_p = str((principal_bruto or {}).get("sexo") or assento.get("sexo")
                 or dados_a.get("strSexo") or "").strip()
    genero = (genero_de({"sexo": sexo_p}) if sexo_p
              else genero_de(principal_bruto or {}, principal_papel))
    if genero and principal_bruto is not None and not principal_bruto.get("sexo"):
        principal_bruto["sexo"] = genero
    por_papel = {papel: _pessoa_concordada(p, papel)
                 for papel, p in _por_papel(lista).items()}

    sv_termo = serventia_do_termo(sv, escrevente=escrevente, funcao=funcao)
    assina = quem_assina(sv_termo)
    if not assina.get("escrevente"):
        avisos.append("não sei quem assina — informe o escrevente ou o titular "
                      "da serventia; o fecho «Eu, ____» ficaria em branco.")

    teor = str(assento.get("teor") or assento.get("teor_html_cru") or "").strip()
    fonte = "congelado" if (teor and not remontar) else "montado"
    erro = ""
    if fonte == "congelado":
        bruto = teor
    else:
        try:
            lista_conc = [_pessoa_concordada(p, str(p.get("papel") or "").upper())
                          for p in lista]
            bruto = _montar_texto(assento, lista_conc, chave, sv_termo, assina,
                                  corpo, documentos) if chave else ""
        except Exception as exc:  # noqa: BLE001 — erro vai no contrato
            bruto, erro = "", str(exc)
        # 2c: sem assento (prévia do editor só com o corpo) o catálogo não
        # monta — mostra o corpo com os claros entre colchetes, sem inventar
        # dado. Com assento real o erro continua indo no contrato.
        if erro and chave and not assento.get("id") and not _tem_dados_de_ato(assento):
            bruto = corpo_de_exemplo(corpo, chave, sv_termo, assina)
            if bruto:
                avisos.append("sem assento: o corpo saiu com os claros entre "
                              "colchetes ([campo]) — informe assento_id para "
                              "ver com os dados do ato.")
                fonte, erro = "exemplo", ""
    texto, correcoes = corrigir_texto_termo(
        bruto, especie=especie, pessoas=por_papel, genero_principal=genero,
        assina=assina, estilo_data=estilo_data)
    if fonte == "congelado" and correcoes:
        avisos.append("termo congelado: correções aplicadas só na prévia/papel; "
                      "o texto gravado no assento não muda (averbe ao lado para "
                      "corrigir o livro).")
    if "____" in texto:
        avisos.append("ainda há traço «____» no texto — confira o claro.")

    cab = _cabecalho(sv, especie, assento)
    serventia = {
        "nome": corrigir_pessoas_naturais(sv.get("unit_name") or sv.get("nome") or ""),
        "cns": sv.get("ri_cns") or sv.get("cns") or "",
        "cidade": sv_termo["cidade"], "uf": sv_termo["uf"],
        "estado": sv_termo["estado"],
        "endereco": sv.get("serventia_endereco") or sv.get("endereco") or "",
        "titular": sv_termo["nome"],
        "titulo": corrigir_pessoas_naturais(sv_termo.get("serventia_titulo") or ""),
    }
    return {
        "especie": especie,
        "template_id": chave,
        "titulo": cab.get("titulo_do_ato") or "",
        "cabecalho": cab,
        "serventia": serventia,
        "registrado": {"nome": str(assento.get("nome")
                               or (principal_bruto or {}).get("nome") or ""),
                       "genero": genero},
        "pessoas": por_papel,
        "quem_assina": assina,
        "data_do_ato": data_termo(assento.get("data_ato"), estilo=estilo_data)
        if assento.get("data_ato") else "",
        "data_do_fato": data_termo(assento.get("data_fato"), estilo=estilo_data,
                                   com_numeros=True) if assento.get("data_fato") else "",
        "estilo_data": estilo_data,
        "fonte_texto": fonte,
        "texto_bruto": bruto,
        "texto": texto,
        "correcoes": correcoes,
        "avisos": avisos,
        "erro": erro,
        "_meta": {"fonte": "ContextoCanônico/termo", "especie": especie,
                  "assento_id": assento.get("id"), "template_id": chave},
    }


def contexto_termo_de_assento(con: sqlite3.Connection, assento_id: int, *,
                              sv: dict | None = None, escrevente: str = "",
                              funcao: str = "", estilo_data: str | None = None,
                              remontar: bool = False,
                              corpo: str | None = None) -> dict[str, Any]:
    """ContextoCanônico do termo lido do banco. SÓ LÊ (SELECT).

    2c: `corpo` (rascunho NÃO salvo, formato do catálogo `{campo}`) substitui
    o corpo persistido e força `remontar`. Sem ele, o corpo vem de
    `modelos_motor_versao.corpo_do_termo` — publicada do Editor se a flag
    `USAR_CONTEUDO_PUBLICADO_EDITOR` e a chave da área estiverem ligadas;
    senão `modelos_da_casa.corpo_de` (caminho atual).
    """
    bd = banco(con)
    a = bd.um("SELECT * FROM rc_assentos WHERE id = %s", (int(assento_id),))
    if not a:
        raise LookupError(f"Não achei o assento nº {assento_id}.")
    assento = dict(a)
    pessoas = bd.ler(
        "SELECT * FROM rc_pessoas WHERE assento_id = %s ORDER BY ordem, id",
        (int(assento_id),))
    chave = chave_termo(assento.get("especie"))
    documentos = None
    origem_corpo = "rascunho"
    if corpo is not None:
        remontar = True
    else:
        import modelos_motor_versao as VERSAO
        corpo, origem_corpo = VERSAO.corpo_do_termo(con, chave)
    if chave == "RC_TERMO_CASAMENTO":
        try:
            import rc_termo as RCT
            documentos = RCT._documentos_da_habilitacao(con, int(assento_id))
        except Exception:  # noqa: BLE001
            documentos = []
    ctx = contexto_termo(
        assento=assento, pessoas=pessoas, sv=sv, escrevente=escrevente,
        funcao=funcao, estilo_data=estilo_data, remontar=remontar,
        corpo=corpo, documentos=documentos)
    ctx["origem_corpo"] = origem_corpo
    return ctx


# --------------------------------------------------------------- render

def texto_do_termo(ctx: dict, *, com_cabecalho: bool = True) -> str:
    """Texto plano para papel/PDF (nenhuma tag sobra)."""
    linhas: list[str] = []
    if com_cabecalho:
        cab = ctx.get("cabecalho") or {}
        for k in ("unidade", "titular", "titular_qualidade", "endereco", "contato"):
            v = str(cab.get(k) or "").strip()
            if v:
                linhas.append(v)
        if cab.get("titulo_do_ato"):
            linhas.append("")
            linhas.append(cab["titulo_do_ato"])
        loc = "   ".join(f"{r}: {cab.get(k)}" for r, k in (
            ("Termo", "termo"), ("Livro", "livro"), ("Folha", "folha"))
            if str(cab.get(k) or "").strip())
        if loc:
            linhas.append(loc)
        linhas.append("")
    linhas.append(str(ctx.get("texto") or ""))
    return "\n".join(linhas).strip()


def _negrito_do_nome(texto_esc: str, nome: str) -> str:
    nome = str(nome or "").strip()
    if not nome:
        return texto_esc
    alvo = escapar(nome)
    return texto_esc.replace(alvo, f"<strong>{alvo}</strong>", 1)


def html_do_termo(ctx: dict, *, papel: str = "A4") -> str:
    """HTML da prévia do termo (sem selo, sem numeração, sem gravação).

    O corpo é ESCAPADO a partir do texto plano: tag que veio no teor nunca
    aparece literal; o nome do registrado vai em negrito real.
    """
    cab = ctx.get("cabecalho") or {}
    titulo = str(cab.get("titulo_do_ato") or ctx.get("titulo") or "TERMO").upper()
    corpo = _negrito_do_nome(escapar(ctx.get("texto") or ""),
                             (ctx.get("registrado") or {}).get("nome"))
    topo = []
    for k, cls in (("unidade", "unidade"), ("titular", "titular"),
                   ("titular_qualidade", "qualidade"), ("endereco", "endereco"),
                   ("contato", "contato")):
        v = str(cab.get(k) or "").strip()
        if v:
            topo.append(f"<div class={cls}>{escapar(v)}</div>")
    loc = "".join(
        f"<span><b>{r}:</b> {escapar(cab.get(k))}</span>"
        for r, k in (("Termo", "termo"), ("Livro", "livro"), ("Folha", "folha"))
        if str(cab.get(k) or "").strip())
    avisos = "".join(f"<li>{escapar(a)}</li>" for a in ctx.get("avisos") or [])
    css = """
    body{font-family:"Times New Roman",Times,serif;font-size:12pt;background:#fff;
         color:#000;margin:1.5cm;}
    .cab{text-align:center;margin-bottom:.6cm;line-height:1.3}
    .unidade{font-weight:bold;font-size:13pt}.titular{font-weight:bold}
    .endereco,.contato{font-size:10pt}
    h1{font-size:13pt;text-align:center;margin:.4cm 0 .2cm}
    .loc{display:flex;justify-content:space-between;font-size:10pt;margin-bottom:.5cm}
    p.termo{text-align:justify;line-height:1.5}
    .aviso{font-size:8pt;color:#555;margin-bottom:.6cm}
    """
    return (
        "<!doctype html><html lang=pt-BR><head><meta charset=utf-8>"
        f"<title>{escapar(titulo)}</title><style>{css}</style></head><body>"
        f"<div class=aviso>Prévia do termo pelo motor de fidelidade — sem selo, "
        f"sem numeração, sem gravação. Papel: {escapar(papel)}."
        f"{'<ul>' + avisos + '</ul>' if avisos else ''}</div>"
        f"<div class=cab>{''.join(topo)}</div>"
        f"<h1>{escapar(titulo)}</h1>"
        f"<div class=loc>{loc}</div>"
        f"<p class=termo>{corpo}</p>"
        "</body></html>"
    )


def _corpo_odf_html(ctx: dict) -> str:
    cab = ctx.get("cabecalho") or {}
    partes = []
    for k in ("unidade", "titular", "titular_qualidade", "endereco", "contato"):
        v = str(cab.get(k) or "").strip()
        if v:
            partes.append(f'<p align="center">{escapar(v)}</p>')
    if cab.get("titulo_do_ato"):
        partes.append(f'<p align="center"><b>{escapar(cab["titulo_do_ato"])}</b></p>')
    partes.append('<p align="justify">' + _negrito_do_nome(
        escapar(ctx.get("texto") or ""),
        (ctx.get("registrado") or {}).get("nome")) + "</p>")
    return "".join(partes)


def odt_do_termo(ctx: dict) -> bytes:
    """ODT do termo (mesmo `ri_odt.gerar_odt` da rota `termo.odt`), com
    autoria neutra no meta."""
    from ri_odt import gerar_odt, html_para_odf
    from modelos_motor_adapters import autor_neutro, limpar_autoria_odt
    cab = ctx.get("cabecalho") or {}
    # mesmo pipeline e mesmo título da rota de emissão `rcpn_termo_odt`
    titulo = (f"Termo {cab['termo']}" if str(cab.get("termo") or "").strip()
              else str(cab.get("titulo_do_ato") or "Termo"))
    odt = gerar_odt(html_para_odf(_corpo_odf_html(ctx)), titulo=titulo)
    return limpar_autoria_odt(odt, autor_neutro(ctx))


def campos_usados(ctx: dict) -> list[str]:
    usados = []
    if ctx.get("texto"):
        usados.append("teor")
    for k in ("data_do_ato", "data_do_fato"):
        if ctx.get(k):
            usados.append(k)
    qa = ctx.get("quem_assina") or {}
    for k in ("escrevente", "funcao_do_escrevente"):
        if qa.get(k):
            usados.append(k)
    for k, v in (ctx.get("serventia") or {}).items():
        if v:
            usados.append(f"serventia.{k}")
    return sorted(usados)


def rascunho_do_termo(conteudo: Any, *, area: str = "RCPN",
                      template_id: str = "") -> dict[str, Any]:
    """Ingestão do `conteudo` NÃO SALVO de um termo. Só calcula.

    Aceita `{{campo}}`, `{campo}` e `@campo` (convertidos para `{{campo}}`
    na validação), marcadores `{{#bloqueado id}}…{{/bloqueado}}` (conferidos
    e tirados antes de montar) e HTML do editor (vira texto). Devolve o
    corpo no formato do catálogo (`{campo}`) + a análise para a resposta.
    """
    from modelos_motor_placeholders import (
        analisar_placeholders, conferir_bloqueados, conteudo_de_partes,
        marcar_bloqueados, para_formato_do_catalogo, remover_marcadores_bloqueados)
    bruto = conteudo_de_partes(conteudo, parte="CORPO")
    if isinstance(bruto, (bytes, bytearray)):
        bruto = bytes(bruto).decode("utf-8", errors="replace")
    bruto = str(bruto or "")
    erros, avisos, ids = conferir_bloqueados(area, template_id, bruto)
    sem_marcas = remover_marcadores_bloqueados(bruto)
    if parece_html(sem_marcas) or "&lt;" in sem_marcas:
        sem_marcas = html_para_texto_impressao(sem_marcas)
        avisos.append("conteudo em HTML: virou texto antes de montar o termo.")
    analise = analisar_placeholders(sem_marcas, area=area, template_id=template_id)
    for d in analise["placeholders_desconhecidos"]:
        erros.append({"linha": 0, "coluna": 0, "codigo": "PLACEHOLDER_DESCONHECIDO",
                      "msg": f"Claro desconhecido neste termo: {{{{{d}}}}}"})
    return {
        "corpo": para_formato_do_catalogo(analise["texto_canonico"]),
        "conteudo_marcado": marcar_bloqueados(area, template_id, bruto),
        "erros": erros,
        "avisos": avisos,
        "bloqueados_presentes": ids,
        **analise,
    }


def resposta_previa_termo(
    *,
    area: str = "TERMO",
    template_id: str = "",
    dados: dict | None = None,
    contexto: dict | None = None,
    sv: dict | None = None,
    papel: str = "A4",
    formato: str = "html",
    conteudo: Any = None,
    corpo: str | None = None,
) -> dict[str, Any]:
    """Contrato POST /modelos/api/previa para `RC_TERMO_*` / area termo.

    2c: pdf|odt saem pelo pipeline de EMISSÃO do termo (`ri_odt.gerar_odt`
    + `html_para_odf`, como `rcpn_termo_odt`; PDF pelo `impressao_pdf`) —
    nunca pelo molde de certidão. `conteudo` não salvo substitui o corpo
    persistido (remonta pelo catálogo, sem gravar). Arquivo em
    `arquivo_base64` (alias `pdf_base64`) com `mime` correto.
    """
    from modelos_motor_adapters import MIME_ODT, MIME_PDF, _pacote, pdf_de_odt_bytes
    import base64

    papel_n = "seguranca" if str(papel or "").strip().lower() in (
        "seguranca", "segurança", "folha_seguranca") else "A4"
    formato_n = str(formato or "html").strip().lower()
    if formato_n not in ("html", "pdf", "odt"):
        return _pacote(erros=[{"linha": 0, "coluna": 0, "codigo": "FORMATO_INVALIDO",
                               "msg": f"formato deve ser html|pdf|odt, veio {formato!r}"}])
    tpl = str(template_id or "").upper()
    if not tpl.startswith("RC_TERMO_") and contexto:
        tpl = str(contexto.get("template_id") or "")
    rasc = None
    extras: dict[str, Any] = {}
    if conteudo:
        rasc = rascunho_do_termo(conteudo, area=area, template_id=tpl)
        corpo = rasc["corpo"]
        extras = {"conversoes": rasc["conversoes"],
                  "conteudo_marcado": rasc["conteudo_marcado"],
                  "bloqueados_presentes": rasc["bloqueados_presentes"],
                  "fonte_conteudo": "rascunho"}
    ctx = contexto or contexto_termo(dados or {}, sv=sv, template_id=template_id,
                                     corpo=corpo, remontar=corpo is not None)
    avisos = list(ctx.get("avisos") or [])
    erros: list[dict] = []
    if rasc is not None:
        avisos.insert(0, "conteudo não salvo: prévia do rascunho (nada foi "
                         "gravado; o modelo vigente continua valendo).")
        avisos += rasc["avisos"]
        erros += rasc["erros"]
    if ctx.get("erro"):
        erros.append({"linha": 0, "coluna": 0, "codigo": "TERMO_NAO_MONTOU",
                      "msg": ctx["erro"]})
    if rasc is not None:
        usados = rasc["placeholders_usados"]
        desconhecidos = rasc["placeholders_desconhecidos"]
    else:
        usados = campos_usados(ctx)
        desconhecidos = sorted(set(re.findall(r"\{\{?(\w+)\}?\}", ctx.get("texto") or "")))
    base = dict(avisos=avisos, erros=erros, placeholders_usados=usados,
                placeholders_desconhecidos=desconhecidos,
                texto=texto_do_termo(ctx), template_id=ctx.get("template_id"),
                correcoes=list(ctx.get("correcoes") or []),
                fonte_texto=ctx.get("fonte_texto"), **extras)
    html = html_do_termo(ctx, papel=papel_n)
    if formato_n == "html":
        return _pacote(html=html, paginas=1, **base)
    if not str(ctx.get("texto") or "").strip():
        base["erros"] = erros + [{"linha": 0, "coluna": 0, "codigo": "TERMO_VAZIO",
                                  "msg": "o termo saiu vazio — nada a imprimir."}]
        return _pacote(html=html, paginas=1, **base)
    try:
        odt = odt_do_termo(ctx)
    except Exception as exc:  # noqa: BLE001
        base["erros"] = erros + [{"linha": 0, "coluna": 0, "codigo": "ODT_FALHOU",
                                  "msg": str(exc)}]
        base["avisos"] = avisos + ["ODT indisponível; devolvendo HTML de prévia."]
        return _pacote(html=html, paginas=1, **base)
    if formato_n == "odt":
        base["avisos"] = avisos + ["formato=odt: bytes em arquivo_base64 "
                                   "(alias pdf_base64)."]
        return _pacote(arquivo_base64=base64.b64encode(odt).decode("ascii"),
                       paginas=1, mime=MIME_ODT, **base)
    try:
        pdf = pdf_de_odt_bytes(odt, nome="previa_termo")
        return _pacote(arquivo_base64=base64.b64encode(pdf).decode("ascii"),
                       paginas=1, mime=MIME_PDF, **base)
    except Exception as exc:  # noqa: BLE001
        base["erros"] = erros + [{"linha": 0, "coluna": 0, "codigo": "PDF_FALHOU",
                                  "msg": str(exc)}]
        base["avisos"] = avisos + ["PDF falhou; devolvendo ODT em arquivo_base64."]
        return _pacote(arquivo_base64=base64.b64encode(odt).decode("ascii"),
                       paginas=1, mime=MIME_ODT, **base)
