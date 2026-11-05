"""RCPN — a PESQUISA AMPLA dos assentos. Só LÊ.

O QUE O BALCÃO PRECISAVA (pedido de 04/11/2026)
    «localizar registros por relação no número do livro, por número de livro e
    folha, pelo nome dos pais, do declarante — ser mais fácil encontrar
    assentos numa busca ampla».

    A lista de `/rcpn` só procurava no NOME DO REGISTRADO e na MATRÍCULA. Quem
    chega com «a certidão do filho da Maria das Graças» ou «o livro A-3, folha
    45» não achava nada, porque a mãe mora em `rc_pessoas` e o livro e a folha
    moram no ato de REGISTRO (ou na matrícula, no acervo).

DUAS PORTAS NA MESMA TELA
    1. **Um campo só, de texto livre** (`q`), que entende o que se digita:
         `maria das gracas`        nome de QUALQUER pessoa do assento
         `A-3/45`  ou  `A-3/45/120` livro / folha / termo
         `livro 3 folha 45`        o mesmo, por extenso (`fl`, `fls`, `nº`...)
         `C-5`                     o livro inteiro — a RELAÇÃO do livro
         `1985`                    termo, folha, livro ou ano
         `000000 01 55 1997 ...`   a matrícula, com ou sem espaços
       E combina: `maria A-3` é «alguém chamado Maria no livro A-3».
    2. **Campos separados**, para quando se sabe o que é cada coisa: nome do
       registrado/partes, filiação (pais), declarante, qualquer pessoa, livro,
       folha, termo, matrícula, espécie, ano e situação.

O LIVRO E A FOLHA SAEM DA REGRA DA CERTIDÃO, E NÃO DE UMA CÓPIA
    `rc_certidao.lugar_das_colunas` é a conta que imprime «Livro A-3, folha
    45» na certidão. A busca a importa: se as duas divergissem, a tela acharia
    um livro e a certidão diria outro.

    O LIVRO SE COMPARA PELA LETRA E PELO NÚMERO, e não pelo texto: o acervo
    escreve `A-24` no nascimento e só `5` no óbito (`ibge_geracao`). Quem
    digita `C5`, `C-05` ou `c 5` quer o mesmo livro; a letra que falta no
    guardado vem da SÉRIE do assento (`RC_C` → C).

O NOME SE COMPARA NA FORMA DA CASA (`normalizar_nome` / `nome_da_casa()`)
    Sem acento e sem caixa — a lição da lista de fraudes, que deixou de achar
    metade das pessoas quando a normalização foi copiada em vez de importada.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from typing import Any

import rc_certidao as CE
from bd_nativo import banco
from pt_schema import normalizar_nome

# ------------------------------------------------------------ os papéis

#: Quem É o assento: o registrado, o falecido, os nubentes, os companheiros.
PAPEIS_TITULARES = ("REGISTRADO", "FALECIDO", "NUBENTE1", "NUBENTE2",
                    "COMPANHEIRO1", "COMPANHEIRO2")
#: A filiação — do registrado, de cada nubente e de cada companheiro.
PAPEIS_DOS_PAIS = ("PAI", "MAE",
                   "PAI_NUBENTE1", "MAE_NUBENTE1",
                   "PAI_NUBENTE2", "MAE_NUBENTE2",
                   "PAI_COMPANHEIRO1", "MAE_COMPANHEIRO1",
                   "PAI_COMPANHEIRO2", "MAE_COMPANHEIRO2")
#: Quem declarou. No Livro E não há declarante: quem promove é o REQUERENTE.
PAPEIS_DO_DECLARANTE = ("DECLARANTE", "REQUERENTE")

ROTULO_CURTO = {
    "REGISTRADO": "Registrado", "FALECIDO": "Falecido",
    "NUBENTE1": "Nubente", "NUBENTE2": "Nubente",
    "COMPANHEIRO1": "Companheiro(a)", "COMPANHEIRO2": "Companheiro(a)",
    "MAE": "Mãe", "PAI": "Pai",
    "MAE_NUBENTE1": "Mãe do nubente", "PAI_NUBENTE1": "Pai do nubente",
    "MAE_NUBENTE2": "Mãe do nubente", "PAI_NUBENTE2": "Pai do nubente",
    "MAE_COMPANHEIRO1": "Mãe do companheiro", "PAI_COMPANHEIRO1": "Pai do companheiro",
    "MAE_COMPANHEIRO2": "Mãe do companheiro", "PAI_COMPANHEIRO2": "Pai do companheiro",
    "AVO_PATERNO": "Avô paterno", "AVO_PATERNA": "Avó paterna",
    "AVO_MATERNO": "Avô materno", "AVO_MATERNA": "Avó materna",
    "DECLARANTE": "Declarante", "REQUERENTE": "Requerente",
    "TESTEMUNHA": "Testemunha", "TESTEMUNHA2": "Testemunha",
    "TUTOR": "Tutor(a)", "CURADOR": "Curador(a)",
}

#: As espécies que o filtro oferece, com o nome que o balcão lê.
ESPECIES = {
    "NASCIMENTO": "Nascimento", "CASAMENTO": "Casamento",
    "CASAMENTO_RELIGIOSO": "Casamento religioso", "OBITO": "Óbito",
    "NATIMORTO": "Natimorto", "PROCLAMAS": "Proclamas",
    "EMANCIPACAO": "Emancipação", "INTERDICAO": "Interdição",
    "AUSENCIA": "Ausência", "TUTELA": "Tutela",
    "UNIAO_ESTAVEL": "União estável",
    "OPCAO_NACIONALIDADE": "Opção de nacionalidade", "OUTRO": "Outro",
}

#: A letra do livro quando o guardado não a tem (o óbito do acervo é só `5`).
LETRA_DA_ESPECIE = {
    "NASCIMENTO": "A", "CASAMENTO": "B", "CASAMENTO_RELIGIOSO": "B",
    "OBITO": "C", "NATIMORTO": "C", "PROCLAMAS": "D",
    "EMANCIPACAO": "E", "INTERDICAO": "E", "AUSENCIA": "E", "TUTELA": "E",
    "UNIAO_ESTAVEL": "E", "OPCAO_NACIONALIDADE": "E",
}

ORDENS = {
    "relevancia": "Mais parecidos primeiro",
    "livro": "Livro, folha e termo",
    "nome": "Nome",
    "data": "Data do registro (mais novos primeiro)",
}

POR_PAGINA = 50

#: Palavras que não ajudam a achar nome: «maria de jesus» e «maria jesus»
#: devem achar a mesma pessoa.
PALAVRAS_VAZIAS = {"de", "da", "do", "das", "dos", "e", "d"}

_KW_LIVRO = {"livro", "liv", "lv", "l", "lo", "lvo"}
_KW_FOLHA = {"folha", "folhas", "fls", "fl", "f", "fol"}
_KW_TERMO = {"termo", "t", "registro", "reg", "n", "no", "numero", "num",
             "nro", "assento", "ordem"}
_KW_MATRICULA = {"matricula", "mat"}

_RE_LIVRO = re.compile(r"^[a-e]-?\d{1,5}$")
_RE_BARRA = re.compile(
    r"^(?P<livro>[a-e]?-?\d{1,5})/(?P<folha>\d{1,4}v?)(?:/(?P<termo>\d{1,7}))?$")
_RE_FOLHA = re.compile(r"^\d{1,4}v?$")
_RE_ANO = re.compile(r"(1[89]\d\d|20\d\d)")


class BuscaError(ValueError):
    """Filtro que não se entende, com a frase pronta para a tela."""


# ------------------------------------------------------- formas comparáveis


def _sem_acento(texto: str) -> str:
    t = unicodedata.normalize("NFD", str(texto or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def _inteiro(valor: Any) -> int | None:
    digitos = "".join(c for c in str(valor if valor is not None else "")
                      if c.isdigit())
    return int(digitos) if digitos else None


def letra_da_serie(serie: Any, especie: Any = None) -> str:
    """`RC_A` -> `A`. Sem série de uma letra, a da espécie. Só calcula."""
    m = re.match(r"^RC_([A-E])$", str(serie or "").strip().upper())
    if m:
        return m.group(1)
    return LETRA_DA_ESPECIE.get(str(especie or "").strip().upper(), "")


def livro_comparavel(texto: Any, letra_padrao: str = "") -> tuple[str, int | None] | None:
    """`A-24`, `a24`, `LIVRO A-024` -> `('A', 24)`; `5` + C -> `('C', 5)`.

    Devolve None quando não há nem letra nem número. Só calcula.
    """
    s = _sem_acento(texto).upper()
    s = re.sub(r"\bLIVRO\b|\bLV\b|\bL\.", " ", s)
    letras = re.findall(r"[A-Z]+", s)
    numeros = re.findall(r"\d+", s)
    letra = letras[0] if letras else ""
    if len(letra) > 1:          # «AUX», «LIVRO» já saiu — fica a primeira
        letra = letra[0]
    numero = int(numeros[0]) if numeros else None
    if not letra and numero is None:
        return None
    return (letra or letra_padrao or "", numero)


def livro_casa(procurado: Any, guardado: Any, letra_padrao: str = "") -> bool:
    """O livro procurado é o guardado? Letra só conta se foi digitada."""
    p = livro_comparavel(procurado)
    g = livro_comparavel(guardado, letra_padrao)
    if not p or not g:
        return False
    letra_p, num_p = p
    letra_g, num_g = g
    if num_p is not None and num_p != num_g:
        return False
    if letra_p and letra_p != letra_g:
        return False
    return num_p is not None or bool(letra_p)


def folha_casa(procurada: Any, guardada: Any) -> bool:
    """`45` acha `45` e `45v`; `45v` acha só o verso."""
    p = _sem_acento(procurada).replace(" ", "")
    g = _sem_acento(guardada).replace(" ", "")
    num_p, num_g = _inteiro(p), _inteiro(g)
    if num_p is None or num_g is None or num_p != num_g:
        return False
    if p.endswith("v"):
        return "v" in g
    return True


def termo_casa(procurado: Any, guardado: Any) -> bool:
    p, g = _inteiro(procurado), _inteiro(guardado)
    return p is not None and p == g


def anos_do_assento(*datas: Any) -> set[int]:
    """Os anos que as datas citam (`1997-03-11`, `11/03/1997`). Só calcula."""
    saida: set[int] = set()
    for d in datas:
        for a in _RE_ANO.findall(str(d or "")):
            saida.add(int(a))
    return saida


def palavras_do_nome(texto: Any) -> list[str]:
    """As palavras de um nome na forma da casa, sem as que não ajudam."""
    n = normalizar_nome(texto) or ""
    return [p for p in n.split() if p and p not in PALAVRAS_VAZIAS and len(p) > 1]


# --------------------------------------------------- o campo de texto livre


def interpretar(q: Any) -> dict:
    """O que o campo único quis dizer. Só calcula.

    Devolve `livro`, `folha`, `termo`, `matricula` (texto ou None), `numeros`
    (números soltos: termo, folha, livro ou ano), `palavras` (de nome) e
    `entendido` — a frase que a tela mostra, para o balcão ver como a busca
    leu o que ele digitou.
    """
    saida: dict[str, Any] = {"livro": None, "folha": None, "termo": None,
                             "matricula": None, "numeros": [], "palavras": [],
                             "entendido": []}
    texto = str(q or "").strip()
    if not texto:
        return saida
    digitos = "".join(c for c in texto if c.isdigit())
    # A MATRÍCULA COM ESPAÇOS (como sai impressa) é um número só.
    if re.fullmatch(r"[\d\s.\-]+", texto) and len(digitos) >= 10:
        saida["matricula"] = digitos
        saida["entendido"].append(f"matrícula {digitos}")
        return saida

    t = _sem_acento(texto).replace("º", "o").replace("°", "o")
    t = re.sub(r"\s*/\s*", "/", t)                 # «A-3 / 45» -> «A-3/45»
    t = re.sub(r"\b([a-e])\s*-\s*(?=\d)", r"\1-", t)   # «A - 3» -> «A-3»
    # «livro A 3» -> «livro A-3» (só depois da palavra «livro»: solto, o «e»
    # de «maria e 45» é conjunção, e não o Livro E).
    t = re.sub(r"\b(livro|liv|lv)\s+([a-e])\s+(?=\d)", r"\1 \2-", t)
    # «fl.45», «fls:45», «nº45», «livroA3» -> palavra-chave e valor separados.
    t = re.sub(r"\b(livro|folhas?|fls?|termo|reg|no)[\.:]*(?=[a-e]?-?\d)",
               r"\1 ", t)
    pedacos = [p.strip(".,;:") for p in t.split()]
    pedacos = [p for p in pedacos if p]

    def guarda(chave: str, valor: str) -> None:
        if saida[chave] is None:
            saida[chave] = valor

    i = 0
    while i < len(pedacos):
        p = pedacos[i]
        prox = pedacos[i + 1] if i + 1 < len(pedacos) else ""
        if p in _KW_LIVRO and prox and (_RE_LIVRO.match(prox) or prox.isdigit()
                                        or re.fullmatch(r"[a-e]", prox)):
            guarda("livro", prox.upper())
            i += 2
            continue
        if p in _KW_FOLHA and _RE_FOLHA.match(prox or ""):
            guarda("folha", prox)
            i += 2
            continue
        if p in _KW_TERMO and (prox or "").isdigit():
            guarda("termo", prox)
            i += 2
            continue
        if p in _KW_MATRICULA and prox:
            junto = "".join(c for c in "".join(pedacos[i + 1:]) if c.isdigit())
            if junto:
                saida["matricula"] = junto
                break
        m = _RE_BARRA.match(p)
        if m:
            guarda("livro", m.group("livro").upper())
            guarda("folha", m.group("folha"))
            if m.group("termo"):
                guarda("termo", m.group("termo"))
            i += 1
            continue
        if _RE_LIVRO.match(p):
            guarda("livro", p.upper())
            i += 1
            continue
        if p.isdigit():
            if len(p) >= 10:
                saida["matricula"] = p
            else:
                saida["numeros"].append(int(p))
            i += 1
            continue
        if p in (_KW_LIVRO | _KW_FOLHA | _KW_TERMO | _KW_MATRICULA):
            i += 1                                   # palavra-chave sem valor
            continue
        saida["palavras"].extend(palavras_do_nome(p))
        i += 1

    e = saida["entendido"]
    if saida["livro"]:
        e.append(f"livro {saida['livro']}")
    if saida["folha"]:
        e.append(f"folha {saida['folha']}")
    if saida["termo"]:
        e.append(f"termo {saida['termo']}")
    if saida["matricula"]:
        e.append(f"matrícula {saida['matricula']}")
    for n in saida["numeros"]:
        e.append(f"o número {n} (termo, folha, livro ou ano)")
    if saida["palavras"]:
        e.append("nome com «" + " ".join(saida["palavras"]) + "» "
                 "(registrado, pais, declarante ou qualquer pessoa do assento)")
    return saida


# ------------------------------------------------------------- a consulta

_NOME_P = "COALESCE(NULLIF(p.nome_norm, ''), nome_da_casa(p.nome))"


def _como(palavra: str) -> str:
    """A palavra dentro do ILIKE, com `%` e `_` desarmados."""
    p = palavra.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{p}%"


def _pessoa_com(papeis: Iterable[str] | None, palavras: list[str]) -> tuple[str, list]:
    """EXISTS de uma pessoa do assento cujo nome tem TODAS as palavras."""
    sql = ["SELECT 1 FROM rc_pessoas p WHERE p.assento_id = s.id"]
    params: list[Any] = []
    papeis = tuple(papeis or ())
    if papeis:
        sql.append("AND p.papel IN (" + ", ".join(["%s"] * len(papeis)) + ")")
        params += list(papeis)
    for w in palavras:
        sql.append(f"AND {_NOME_P} ILIKE %s")
        params.append(_como(w))
    return "EXISTS (" + " ".join(sql) + ")", params


def _titular_com(palavras: list[str]) -> tuple[str, list]:
    """O nome do assento (`rc_assentos.nome`) ou um titular em `rc_pessoas`."""
    partes = " AND ".join(["nome_da_casa(s.nome) ILIKE %s"] * len(palavras))
    params: list[Any] = [_como(w) for w in palavras]
    existe, p2 = _pessoa_com(PAPEIS_TITULARES, palavras)
    return f"(({partes}) OR {existe})", params + p2


def ler_filtros(args: Any) -> dict:
    """Os filtros do formulário, limpos. Só calcula."""
    def campo(nome: str) -> str:
        return str((args.get(nome) if args is not None else "") or "").strip()

    f = {k: campo(k) for k in ("q", "nome", "pais", "declarante", "pessoa",
                               "livro", "folha", "termo", "matricula",
                               "especie", "ano", "situacao", "ordem")}
    if f["especie"] and f["especie"] not in ESPECIES:
        f["especie"] = ""
    if f["situacao"] not in ("", "ATIVO", "CANCELADO"):
        f["situacao"] = ""
    if f["ordem"] not in ORDENS:
        f["ordem"] = ""
    return f


def tem_filtro(f: dict) -> bool:
    return any(f.get(k) for k in ("q", "nome", "pais", "declarante", "pessoa",
                                  "livro", "folha", "termo", "matricula",
                                  "especie", "ano"))


def pesquisar(con: Any, filtros: dict, *, pagina: int = 1,
              por_pagina: int = POR_PAGINA) -> dict:
    """Acha os assentos. SÓ LÊ — GET, sem transação de escrita.

    Duas etapas: o banco filtra o que é de NOME (está indexado e normalizado
    lá), e o livro, a folha, o termo e o ano se conferem aqui, com a conta da
    certidão — o livro do acervo mora em três lugares (ato, volume e
    matrícula), e só `lugar_das_colunas` sabe juntá-los.
    """
    f = dict(filtros or {})
    livre = interpretar(f.get("q"))
    saida: dict[str, Any] = {
        "linhas": [], "total": 0, "pagina": 1, "paginas": 1,
        "entendido": livre["entendido"], "filtros": f,
        "ordem": f.get("ordem") or "", "vazio": not tem_filtro(f),
    }
    if saida["vazio"]:
        return saida

    # O que o campo livre achou soma-se aos campos, sem apagar o que foi
    # digitado neles: o campo separado é mais preciso, e manda.
    livro = f.get("livro") or livre["livro"]
    folha = f.get("folha") or livre["folha"]
    termo = f.get("termo") or livre["termo"]
    matricula = ("".join(c for c in f.get("matricula", "") if c.isdigit())
                 or livre["matricula"])
    ano = _inteiro(f.get("ano"))
    if f.get("ano") and (ano is None or not 1800 <= ano <= 2100):
        raise BuscaError("O ano tem quatro dígitos — por exemplo, 1985.")
    numeros = livre["numeros"]

    onde: list[str] = []
    params: list[Any] = []

    def junta(sql_params: tuple[str, list]) -> None:
        onde.append(sql_params[0])
        params.extend(sql_params[1])

    nome_p = palavras_do_nome(f.get("nome"))
    pais_p = palavras_do_nome(f.get("pais"))
    decl_p = palavras_do_nome(f.get("declarante"))
    pessoa_p = palavras_do_nome(f.get("pessoa"))
    if nome_p:
        junta(_titular_com(nome_p))
    if pais_p:
        junta(_pessoa_com(PAPEIS_DOS_PAIS, pais_p))
    if decl_p:
        junta(_pessoa_com(PAPEIS_DO_DECLARANTE, decl_p))
    if pessoa_p:
        junta(_pessoa_com(None, pessoa_p))
    # O CAMPO LIVRE É AMPLO: cada palavra pode estar em QUALQUER nome do
    # assento — «joao maria» acha o João filho da Maria. Quem quer as
    # palavras numa pessoa só usa os campos separados.
    for w in livre["palavras"]:
        existe, p2 = _pessoa_com(None, [w])
        onde.append(f"(nome_da_casa(s.nome) ILIKE %s OR {existe})")
        params.extend([_como(w), *p2])
    if matricula:
        onde.append("regexp_replace(COALESCE(s.matricula, ''), '[^0-9]', '', 'g')"
                    " LIKE %s")
        params.append(f"%{matricula}%")
    if f.get("especie"):
        onde.append("s.especie = %s")
        params.append(f["especie"])
    if f.get("situacao"):
        onde.append("s.situacao = %s")
        params.append(f["situacao"])

    filtro = (" WHERE " + " AND ".join(onde)) if onde else ""
    candidatos = banco(con).ler(
        f"""SELECT s.id, s.serie, s.especie, s.nome, s.numero, s.matricula,
                   s.livro_volume, s.data_ato, s.data_fato, s.situacao,
                   r.assento_id AS r_assento, r.folha AS r_folha,
                   r.rotulo AS r_rotulo, r.numero_ordem AS r_numero_ordem,
                   r.livro_numero AS r_livro_numero,
                   r.livro_complemento AS r_livro_complemento
              FROM rc_assentos s
              LEFT JOIN LATERAL (
                   SELECT a.assento_id, a.folha, a.rotulo, a.numero_ordem,
                          l.numero AS livro_numero,
                          l.complemento AS livro_complemento
                     FROM rc_atos a
                     LEFT JOIN nu_livros l ON l.id = a.livro_id
                    WHERE a.assento_id = s.id AND a.tipo = 'REGISTRO'
                    ORDER BY a.id LIMIT 1) r ON TRUE
             {filtro}""", params or None)

    linhas: list[dict] = []
    for c in candidatos:
        registro = None
        if c["r_assento"] is not None:
            registro = {"folha": c["r_folha"], "rotulo": c["r_rotulo"],
                        "numero_ordem": c["r_numero_ordem"],
                        "livro_numero": c["r_livro_numero"],
                        "livro_complemento": c["r_livro_complemento"]}
        lugar = CE.lugar_das_colunas(
            {"numero": c["numero"], "livro_volume": c["livro_volume"],
             "matricula": c["matricula"]}, registro)
        letra = letra_da_serie(c["serie"], c["especie"])
        l_livro, l_folha, l_termo = (lugar.get("livro"), lugar.get("folha"),
                                     lugar.get("termo"))
        if livro and not livro_casa(livro, l_livro, letra):
            continue
        if folha and not folha_casa(folha, l_folha):
            continue
        if termo and not termo_casa(termo, l_termo):
            continue
        anos = anos_do_assento(c["data_ato"], c["data_fato"])
        if ano and ano not in anos:
            continue
        pontos = 0
        motivos: list[str] = []
        recusado = False
        for n in numeros:
            achou = []
            if termo_casa(n, l_termo) or termo_casa(n, c["numero"]):
                achou.append(f"termo {n}")
                pontos += 3
            if folha_casa(n, l_folha):
                achou.append(f"folha {n}")
                pontos += 1
            if livro_casa(str(n), l_livro, letra):
                achou.append(f"livro {l_livro}")
                pontos += 1
            if n in anos:
                achou.append(f"ano {n}")
                pontos += 1
            if not achou:
                recusado = True
                break
            motivos += achou
        if recusado:
            continue
        nome_norm = normalizar_nome(c["nome"]) or ""
        palavras_todas = livre["palavras"] + nome_p
        if palavras_todas and all(w in nome_norm for w in palavras_todas):
            pontos += 5           # o próprio registrado vem antes dos pais
        livro_ord = livro_comparavel(l_livro, letra) or ("", None)
        linhas.append({
            "id": c["id"], "especie": c["especie"],
            "especie_diz": ESPECIES.get(c["especie"], c["especie"]),
            "nome": c["nome"], "matricula": c["matricula"],
            "data_ato": c["data_ato"], "data_fato": c["data_fato"],
            "situacao": c["situacao"],
            "livro": l_livro or "", "folha": l_folha or "",
            "termo": l_termo or "",
            "_pontos": pontos, "_motivos": motivos,
            "_ordem_livro": (livro_ord[0] or "", livro_ord[1] or 0,
                             _inteiro(l_folha) or 0, _inteiro(l_termo) or 0),
        })

    ordem = f.get("ordem") or ""
    if not ordem:
        so_livro = (livro or folha) and not (livre["palavras"] or nome_p or pais_p
                                             or decl_p or pessoa_p)
        ordem = "livro" if so_livro else "relevancia"
    saida["ordem"] = ordem
    if ordem == "livro":
        linhas.sort(key=lambda r: (r["_ordem_livro"], r["id"]))
    elif ordem == "nome":
        linhas.sort(key=lambda r: (normalizar_nome(r["nome"]) or "", r["id"]))
    elif ordem == "data":
        linhas.sort(key=lambda r: (str(r["data_ato"] or ""), r["id"]), reverse=True)
    else:
        linhas.sort(key=lambda r: (-r["_pontos"],
                                   normalizar_nome(r["nome"]) or "", r["id"]))

    total = len(linhas)
    paginas = max(1, -(-total // por_pagina))
    pagina = min(max(1, int(pagina or 1)), paginas)
    recorte = linhas[(pagina - 1) * por_pagina: pagina * por_pagina]
    _juntar_pessoas(con, recorte, livre["palavras"], nome_p, pais_p, decl_p,
                    pessoa_p)
    saida.update(linhas=recorte, total=total, pagina=pagina, paginas=paginas)
    return saida


def _juntar_pessoas(con: Any, linhas: list[dict], *listas: list[str]) -> None:
    """Pais, declarante e o «achado em» das linhas da página. Só LÊ.

    Só da página: ler as pessoas de todos os candidatos seria trazer o acervo
    inteiro para mostrar cinquenta.
    """
    if not linhas:
        return
    ids = [int(r["id"]) for r in linhas]
    pessoas = banco(con).ler(
        """SELECT assento_id, papel, nome, nome_norm FROM rc_pessoas
            WHERE assento_id = ANY(%s) ORDER BY assento_id, ordem, id""", (ids,))
    por_assento: dict[int, list[dict]] = {}
    for p in pessoas:
        por_assento.setdefault(int(p["assento_id"]), []).append(p)
    procuradas = {w for lista in listas for w in lista}
    for r in linhas:
        lista = por_assento.get(int(r["id"]), [])
        r["pais"] = [f"{ROTULO_CURTO.get(p['papel'], p['papel'])}: {p['nome']}"
                     for p in lista if p["papel"] in PAPEIS_DOS_PAIS]
        r["declarante"] = ", ".join(p["nome"] for p in lista
                                    if p["papel"] in PAPEIS_DO_DECLARANTE)
        achados = list(r.pop("_motivos", []))
        if procuradas:
            for p in lista:
                n = p["nome_norm"] or normalizar_nome(p["nome"]) or ""
                if any(w in n for w in procuradas):
                    achados.append(
                        f"{ROTULO_CURTO.get(p['papel'], p['papel'].title())}: "
                        f"{p['nome']}")
            n = normalizar_nome(r["nome"]) or ""
            if any(w in n for w in procuradas):
                achados.insert(0, "Nome do assento")
        r["achado_em"] = list(dict.fromkeys(achados))
        r.pop("_pontos", None)
        r.pop("_ordem_livro", None)
