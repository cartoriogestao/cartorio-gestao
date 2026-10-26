"""A BUSCA EM TEXTO LIVRE NO ACERVO DO RI — o teor de todas as fichas.

O PEDIDO (o oficial, 26/10/2026)
    A caixa da lista de matriculas olha o numero, o CNM, o logradouro e as
    partes cadastradas (`ri_web._condicao_de_busca_da_matricula`), e o
    indicador real olha o `imovel_norm`. **Nenhuma das duas le o teor** — e e
    no teor que mora o acervo: nas fichas do E-Oficio os atos, as partes e os
    documentos estao escritos dentro do texto da matricula, e 71% das partes
    cadastradas nao tem documento (medido em 15/09/2026). Quem procura um CPF
    que so esta escrito no R-3 de uma ficha antiga nao o acha em tela nenhuma.

O QUE SE MEDIU ANTES DE ESCOLHER O INDICE (26/10/2026, producao, so leitura)
    `ri_matriculas.teor`: 4.007 fichas, 29,9 MB, a maior com 231 mil
    caracteres; 3.992 em HTML (o XHTML do TX Text Control: `<p>`, `<em>`,
    `<span>`), 15 em texto, 2 vazias. As entidades do HTML sao so pontuacao
    (`&#x27;`, `&quot;`, `&amp;`) — os acentos estao escritos como letra.
    CPF no teor: 13.704 com mascara (`000.000.000-00`), 2.926 so digitos e 370
    noutras formas (`000.000.000.00`, `000000000-00`).

    E O CUSTO DE NORMALIZAR NO BANCO DECIDIU O DESENHO. Passar o acervo
    inteiro por uma funcao de normalizacao no PostgreSQL custou: a
    `nome_da_casa` da casa, 63 s; `unaccent`, 13,8 s; `unaccent` mais tirar as
    marcas do HTML, 51 s; `to_tsvector('portuguese', unaccent(...))`, 84 s.
    O `ILIKE` sobre o teor cru, 1,7 s. Indice de EXPRESSAO sobre qualquer
    uma delas obrigaria o banco a recalcular a expressao em cada ficha
    candidata (o «recheck»): uma busca por «silva», que esta em 2.111 fichas,
    levaria dezenas de segundos.

A ESCOLHA: TRIGRAMAS SOBRE O TEOR CRU, E O ACENTO NA EXPRESSAO REGULAR
    `ix_ri_mat_teor_trgm` e `gin (teor gin_trgm_ops)` — o mesmo `pg_trgm` do
    `ix_ri_mat_imovel_norm`, sobre a coluna como ela e. Quem cuida do acento,
    da caixa e das marcas do HTML e a EXPRESSAO REGULAR montada aqui: «joao»
    vira `[jJ][oóòôõöOÓÒÔÕÖ][aáàâãäAÁÀÂÃÄ][oóòôõöOÓÒÔÕÖ]`, e o espaco entre
    palavras aceita espaco, quebra e marca de HTML. O `pg_trgm` usa indice
    para expressao regular. Medido num banco de ensaio com 44 MB de texto
    sintetico do mesmo feitio: nome raro, 1 a 3 ms; CPF, 11 ms; palavra que
    esta em quase toda ficha, 0,7 s (o banco le tudo, e e o certo).

    Por que NAO o full-text `portuguese`: ele corta o radical («SOUSA» e
    «SOUSAS» viram o mesmo), joga fora «DE», «DA», «DOS» (que separam
    homonimos em nome de gente), nao acha trecho de palavra, e quebra o CPF
    em pedacos que a tokenizacao decide. Busca de nome e de documento num
    registro publico pede o trecho exato, nao a palavra parecida. E ele
    tambem dependeria do recheck caro na busca de frase.

    O que esta escolha NAO ganha: palavra cortada por marca de HTML no meio
    (`JO<em>ÃO</em>`) nao se acha. E a ficha sem teor — digitalizacao que
    ainda nao foi transcrita — nao se acha por texto nenhum: a tela diz
    quantas sao.

A REGUA DO NUMERO E A DA CASA (relato #55, 15/09/2026)
    «3110» nao acha o CPF de ninguem: numero procurado no texto exige que nao
    haja digito colado antes nem depois. E a pontuacao nao decide nada: o
    CPF digitado com ou sem mascara acha as quatro grafias medidas acima; o
    numero de quatro digitos ou mais acha tambem a grafia com ponto de milhar
    («3110» acha «3.110»).

O QUE ESTE MODULO NAO FAZ
    Nao grava nada, e nao decide quem pode procurar — isso e da rota, que
    restringe pelo papel e registra a busca na auditoria.
"""
from __future__ import annotations

import hashlib
import hmac
import html as _html
import re
import unicodedata
from dataclasses import dataclass, field

from bd_nativo import banco

#: Quantas fichas a tela mostra. Acima disto, a tela diz o total e pede um
#: termo mais preciso — 200 fichas com tres trechos cada ja e leitura de uma
#: tarde.
LIMITE_DE_FICHAS = 200

#: Quantos trechos destacados por ficha.
TRECHOS_POR_FICHA = 3

#: Quantos caracteres de cada lado do achado o trecho mostra.
RAIO_DO_TRECHO = 140

#: O minimo de letras ou digitos de cada termo. O indice de trigramas precisa
#: de tres; com menos, o banco leria o acervo inteiro para achar «da».
MINIMO_DO_TERMO = 3


class BuscaError(ValueError):
    """Erro de regra, com mensagem pronta para o balcao."""


# A letra sem acento -> todas as grafias que o acervo usa, nas duas caixas.
# O PostgreSQL desta casa roda com a collation «C», em que `~*` e `ILIKE` so
# sabem a caixa do ASCII: «Ã» e «ã» seriam letras diferentes. Por isso a caixa
# tambem vai na classe, e a comparacao e `~`, sensivel a caixa.
_VARIANTES = {
    "a": "aáàâãäAÁÀÂÃÄ",
    "e": "eéèêëEÉÈÊË",
    "i": "iíìîïIÍÌÎÏ",
    "o": "oóòôõöOÓÒÔÕÖ",
    "u": "uúùûüUÚÙÛÜ",
    "c": "cçCÇ",
    "n": "nñNÑ",
}

# Entre duas palavras o teor pode ter espaco, quebra de linha, `&nbsp;` ou uma
# marca de HTML inteira (`</p><p style=...>`).
_ENTRE_PALAVRAS = r"(\s|<[^>]*>|&nbsp;|&#160;)+"

# A pontuacao que o HTML do acervo escreve como entidade (medido: so estas).
_PONTUACAO_DO_HTML = {
    "'": r"('|&#x27;|&#x0027;|&#39;)",
    '"': r'("|&quot;)',
    "&": r"(&|&amp;)",
}

_SEM_DIGITO_ANTES = r"(^|[^0-9])"
_SEM_DIGITO_DEPOIS = r"([^0-9]|$)"


@dataclass(frozen=True)
class Padrao:
    """Um termo da busca, pronto para o banco e para o destaque.

    `regex` vai ao PostgreSQL (`teor ~ regex`). `regex_python` e a MESMA
    expressao com as tres partes em grupo — o que veio antes, o achado e o
    que veio depois —, para o destaque marcar so o achado (grupo 2). As
    duas falam o mesmo subconjunto de expressao regular: classe, grupo,
    alternativa, `\\s` e `+`.
    """
    termo: str
    tipo: str            # TEXTO, DOCUMENTO ou NUMERO
    regex: str
    regex_python: str


@dataclass
class Resultado:
    termos: list[Padrao] = field(default_factory=list)
    modo: str = "FRASE"
    total: int = 0
    fichas: list[dict] = field(default_factory=list)
    cortado: bool = False
    sem_teor: int = 0


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto)
                   if unicodedata.category(c) != "Mn")


def _letra(ch: str) -> str:
    if ch in _VARIANTES:
        return "[" + _VARIANTES[ch] + "]"
    if "a" <= ch <= "z":
        return "[" + ch + ch.upper() + "]"
    if ch.isdigit():
        return ch
    if ch in _PONTUACAO_DO_HTML:
        return _PONTUACAO_DO_HTML[ch]
    if ch.isascii():
        # Pontuacao ASCII: barra invertida antes, que e literal nos dois
        # motores (no PostgreSQL, `\` antes de nao-alfanumerico e o proprio).
        return "\\" + ch
    # Letra fora do ASCII que nao tem variante («º», «ª»): ela mesma.
    return ch


def _numero_com_milhar(digitos: str) -> str:
    """«3110» -> «3.110»; «12345» -> «12.345». Sem zero a esquerda inventado."""
    grupos = []
    resto = digitos
    while len(resto) > 3:
        grupos.insert(0, resto[-3:])
        resto = resto[:-3]
    grupos.insert(0, resto)
    return ".".join(grupos)


def _formas_do_numero(digitos: str) -> list[str]:
    """As grafias de um numero que o teor usa, como expressao regular."""
    d = digitos
    if len(d) == 11:       # CPF: as quatro grafias medidas no acervo
        return [d,
                rf"{d[:3]}\.{d[3:6]}\.{d[6:9]}-{d[9:]}",
                rf"{d[:3]}\.{d[3:6]}\.{d[6:9]}[ .]{d[9:]}",
                rf"{d[:9]}-{d[9:]}"]
    if len(d) == 14:       # CNPJ
        return [d, rf"{d[:2]}\.{d[2:5]}\.{d[5:8]}/{d[8:12]}-{d[12:]}"]
    if len(d) == 16:       # CNM, como a casa o grava
        return [d, rf"{d[:6]}\.{d[6]}\.{d[7:14]}-{d[14:]}"]
    formas = [d]
    if len(d) >= 4 and not d.startswith("0"):
        formas.append(_numero_com_milhar(d).replace(".", r"\."))
    return formas


def padrao_do_termo(termo: str) -> Padrao:
    """O termo digitado, como expressao regular sem acento, caixa nem mascara.

    Recusa (`BuscaError`) o termo curto demais para o indice.
    """
    bruto = " ".join(str(termo or "").split())
    if not bruto:
        raise BuscaError("Digite o que procurar.")
    so_numero = re.sub(r"[.\-/\s]", "", bruto)
    if so_numero.isdigit() and so_numero.isascii():
        if len(so_numero) < MINIMO_DO_TERMO:
            raise BuscaError(
                f"«{bruto}» é curto demais para procurar no texto das fichas. "
                "Para achar a matrícula pelo número, use a lista de matrículas.")
        tipo = "DOCUMENTO" if len(so_numero) in (11, 14) else "NUMERO"
        miolo = "(" + "|".join(_formas_do_numero(so_numero)) + ")"
        return Padrao(termo=bruto, tipo=tipo,
                      regex=_SEM_DIGITO_ANTES + miolo + _SEM_DIGITO_DEPOIS,
                      regex_python=(_SEM_DIGITO_ANTES + "(" + miolo + ")"
                                    + _SEM_DIGITO_DEPOIS))

    limpo = _sem_acento(bruto).lower()
    if sum(1 for c in limpo if c.isalnum()) < MINIMO_DO_TERMO:
        raise BuscaError(
            f"«{bruto}» é curto demais: escreva ao menos {MINIMO_DO_TERMO} "
            "letras ou números.")
    pedacos = [("".join(_letra(c) for c in palavra))
               for palavra in limpo.split(" ")]
    miolo = _ENTRE_PALAVRAS.join(pedacos)
    return Padrao(termo=bruto, tipo="TEXTO", regex=miolo,
                  regex_python="()(" + miolo + ")()")


def termos_da_busca(texto: str, modo: str = "FRASE") -> list[Padrao]:
    """FRASE: o que se digitou e um trecho so, nesta ordem (como a lista de
    matriculas procura o nome). TODAS: cada palavra e um termo, e a ficha tem
    de ter todas, em qualquer ordem e em qualquer ponto do texto. As aspas,
    no modo TODAS, juntam palavras num termo so («"joao da silva" lote»)."""
    texto = str(texto or "").strip()
    if modo != "TODAS":
        return [padrao_do_termo(texto.replace('"', " "))]
    pedacos = [a or b for a, b in re.findall(r'"([^"]+)"|(\S+)', texto)]
    pedacos = [p for p in pedacos if p.strip()]
    if not pedacos:
        raise BuscaError("Digite o que procurar.")
    if len(pedacos) > 6:
        raise BuscaError("No máximo seis termos de uma vez.")
    return [padrao_do_termo(p) for p in pedacos]


def impressao_da_busca(texto: str, chave: bytes | str | None = None) -> str:
    """O que vai para a auditoria NO LUGAR do termo — ver a rota.

    Mesma busca, mesma impressao: quem audita confere se alguem procurou um
    CPF calculando a impressao dele, sem que o CPF fique escrito no rastro.

    COM CHAVE, E NAO SHA-256 PURO (conferencia de 26/10/2026, PR #30): o CPF
    tem onze digitos, e o sha256 sem chave de um CPF se desfaz percorrendo os
    CPFs possiveis numa tarde de computador comum — na pratica, o CPF estaria
    no rastro. A rota passa a chave secreta do servidor (a mesma que nao sai
    da pasta de dados); quem audita confere a impressao NO SERVIDOR, com esta
    funcao. Sem chave (teste de dominio) continua o sha256 de antes.
    """
    norma = " ".join(_sem_acento(str(texto or "")).upper().split())
    if chave:
        k = chave.encode("utf-8") if isinstance(chave, str) else bytes(chave)
        return hmac.new(k, b"ri-busca-no-acervo:" + norma.encode("utf-8"),
                        hashlib.sha256).hexdigest()[:16]
    return hashlib.sha256(norma.encode("utf-8")).hexdigest()[:16]


def documento_mascarado(termo: str) -> str:
    """CPF/CNPJ procurado, como a auditoria da casa o guarda: so os dois
    ultimos digitos (`centrais_log.mascarar_texto`, revisao M9 de 22/10).
    Diz a quem audita que se procurou UM DOCUMENTO, sem dizer qual."""
    d = re.sub(r"\D", "", str(termo or ""))
    return "*" * max(len(d) - 2, 0) + d[-2:]


# ------------------------------------------------------------------ o trecho

_TAG = re.compile(r"<[^>]*>")
_TAG_CORTADA_NO_INICIO = re.compile(r"^[^<]*>")
_TAG_CORTADA_NO_FIM = re.compile(r"<[^>]*$")


def _texto_visivel(pedaco: str) -> str:
    """O HTML do teor como se le na tela: sem marca, sem entidade, uma linha.

    NAO APARA AS PONTAS: o trecho se monta de tres pedacos (antes, achado,
    depois), e o espaco que havia entre eles no texto tem de continuar la —
    aparar colaria «CPF» no numero, ou poria espaco antes da virgula.
    """
    sem = _TAG.sub(" ", pedaco)
    return re.sub(r"\s+", " ", _html.unescape(sem))


def trechos_destacados(teor: str, padroes: list[Padrao], *,
                       maximo: int = TRECHOS_POR_FICHA,
                       raio: int = RAIO_DO_TRECHO) -> tuple[list[str], int]:
    """Os trechos do teor em volta de cada achado, com o achado em <mark>.

    Devolve `(trechos_em_html_seguro, quantos_achados)`. O texto do acervo
    e ESCAPADO aqui — nada do teor chega a tela como HTML.
    """
    teor = str(teor or "")
    achados: list[tuple[int, int]] = []
    for p in padroes:
        for m in re.finditer(p.regex_python, teor):
            if m.end(2) > m.start(2):
                achados.append((m.start(2), m.end(2)))
    achados.sort()
    total = len(achados)
    trechos: list[str] = []
    ultimo_fim = -1
    for ini, fim in achados:
        if len(trechos) >= maximo:
            break
        if ini < ultimo_fim:      # ja coberto pelo trecho anterior
            continue
        a, b = max(0, ini - raio), min(len(teor), fim + raio)
        antes = _TAG_CORTADA_NO_INICIO.sub("", teor[a:ini]) if a else teor[a:ini]
        depois = _TAG_CORTADA_NO_FIM.sub("", teor[fim:b])
        trecho = ("…" if a else "") + _html.escape(_texto_visivel(antes).lstrip())
        trecho += "<mark>" + _html.escape(_texto_visivel(teor[ini:fim]).strip()) + "</mark>"
        trecho += _html.escape(_texto_visivel(depois).rstrip()) + ("…" if b < len(teor) else "")
        trechos.append(trecho)
        ultimo_fim = b
    return trechos, total


# ----------------------------------------------------------------- a busca

def _condicao(coluna: str, padroes: list[Padrao]) -> tuple[str, list[str]]:
    return (" AND ".join(f"{coluna} ~ %s" for _ in padroes),
            [p.regex for p in padroes])


def _numero_para_ordenar(numero) -> tuple[int, str]:
    digitos = re.match(r"\d+", str(numero or ""))
    return (int(digitos.group()) if digitos else 0, str(numero or ""))


def buscar(con, texto: str, *, modo: str = "FRASE",
           limite: int = LIMITE_DE_FICHAS) -> Resultado:
    """Procura no teor das fichas E no teor dos atos lavrados no sistema.

    O ato lavrado aqui mora em `ri_atos.teor`, e nas fichas estruturadas ele
    nao esta no texto da matricula: procurar so na ficha deixaria de fora o
    registro de ontem. `ri_atos` e pequena (1.248 linhas em 18/09/2026) e
    dispensa indice proprio. SO LE.
    """
    modo = "TODAS" if modo == "TODAS" else "FRASE"
    padroes = termos_da_busca(texto, modo)
    bd = banco(con)

    onde_m, par_m = _condicao("teor", padroes)
    pela_ficha = {int(r["id"]) for r in bd.ler(
        f"SELECT id FROM ri_matriculas WHERE {onde_m}", par_m)}
    onde_a, par_a = _condicao("teor", padroes)
    pelo_ato: dict[int, list[dict]] = {}
    for r in bd.ler(
            f"""SELECT id, matricula_id, tipo, numero, cancelado
                  FROM ri_atos WHERE {onde_a}
                 ORDER BY matricula_id, numero, id""", par_a):
        pelo_ato.setdefault(int(r["matricula_id"]), []).append(r)

    ids = pela_ficha | set(pelo_ato)
    res = Resultado(termos=padroes, modo=modo, total=len(ids))
    res.sem_teor = int(bd.valor(
        "SELECT COUNT(*) AS n FROM ri_matriculas WHERE COALESCE(teor, '') = ''") or 0)
    if not ids:
        return res

    curtas = bd.ler(
        f"""SELECT id, numero, complemento, livro_norm, tipo_ficha, encerrada,
                   conferido, logradouro, bairro
              FROM ri_matriculas WHERE id IN ({",".join(["%s"] * len(ids))})""",
        sorted(ids))
    curtas.sort(key=lambda r: (_numero_para_ordenar(r["numero"]), r["id"]))
    res.cortado = len(curtas) > limite
    escolhidas = curtas[:limite]

    teores = {int(r["id"]): r["teor"] for r in bd.ler(
        f"""SELECT id, teor FROM ri_matriculas
             WHERE id IN ({",".join(["%s"] * len(escolhidas))})""",
        [r["id"] for r in escolhidas])}
    ids_dos_atos = [a["id"] for r in escolhidas for a in pelo_ato.get(int(r["id"]), [])]
    teor_do_ato = {}
    if ids_dos_atos:
        teor_do_ato = {int(r["id"]): r["teor"] for r in bd.ler(
            f"""SELECT id, teor FROM ri_atos
                 WHERE id IN ({",".join(["%s"] * len(ids_dos_atos))})""",
            ids_dos_atos)}

    for r in escolhidas:
        mid = int(r["id"])
        linha = dict(r)
        trechos, n = ([], 0)
        if mid in pela_ficha:
            trechos, n = trechos_destacados(teores.get(mid), padroes)
        linha["no_teor"] = mid in pela_ficha
        linha["trechos"] = trechos
        linha["achados"] = n
        linha["atos"] = []
        for a in pelo_ato.get(mid, []):
            t_ato, n_ato = trechos_destacados(teor_do_ato.get(int(a["id"])), padroes,
                                              maximo=1)
            linha["atos"].append({"id": a["id"], "tipo": a["tipo"],
                                  "numero": a["numero"],
                                  "cancelado": bool(a["cancelado"]),
                                  "trechos": t_ato, "achados": n_ato})
        res.fichas.append(linha)
    return res
