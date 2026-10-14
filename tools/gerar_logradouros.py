"""Gera, do contrato do ONR, os vocabularios que `onr_api` transcreve.

São três: os **129 tipos de logradouro**, os **23 tipos de ato** e os **10
tipos de imóvel**. Eles entram no `onr_api.py` **transcritos**, e não lidos em
tempo de execução: o contrato mora em `FONTES_EXTERNAS`, que **não viaja no
`.cgu`**. É a mesma decisão de `atribuicoes.py`, que é «gerado do acervo».

Roda de dentro de `SERVIDOR/INSTALAR_CARTORIO_GESTAO`:

    python tools/gerar_logradouros.py

E é **repetível**: o bloco fica entre marcadores e é trocado inteiro.
"""
import json
import re
from pathlib import Path

ABRE = "# <<< vocabularios do ONR — gerado por tools/gerar_logradouros.py"
FECHA = "# >>> fim dos vocabularios do ONR"

CONTRATO = Path("../../FONTES_EXTERNAS/onr_ri/openapi_limpo.json")
d = json.loads(CONTRATO.read_text(encoding="utf-8"))
S = d["components"]["schemas"]


def pares_de(enum) -> dict[int, str]:
    saida = {}
    for bruto in (enum or []):
        m = re.match(r"\s*(\d+)\s*=\s*(.+?)\s*$", str(bruto))
        if m:
            saida[int(m.group(1))] = m.group(2)
    return saida


ir = S["indicadorRealRequest"]["properties"]
LOGRADOUROS = pares_de(ir["tipoLogradouro"]["enum"])
IMOVEIS = pares_de(ir["tipoImovel"]["enum"])
ATOS = pares_de(S["indicadorRealAtoRequest"]["properties"]["tipo"]["enum"])

assert len(LOGRADOUROS) == 129, len(LOGRADOUROS)
assert len(IMOVEIS) == 10, len(IMOVEIS)
assert len(ATOS) == 23, len(ATOS)


def tabela(pares: dict[int, str]) -> str:
    """**UMA ENTRADA POR LINHA, e não embrulhado por largura.**"""
    return "\n".join(f"    {c}: {n!r}," for c, n in sorted(pares.items()))


bloco = f'''{ABRE}
#
# **UMA ENTRADA POR LINHA, e nao embrulhado.** A primeira versao deste gerador
# usou `textwrap.wrap` e **partiu nomes no meio** — «Praça de\\nEsportes» —,
# produzindo um arquivo que nem compilava. Quem pegou foi o `ruff`, com vinte e
# cinco erros de sintaxe; a licao e que texto que contem espaco nao se quebra
# por largura.
#
# Eles entram aqui em vez de serem lidos em tempo de execucao porque o contrato
# mora em `FONTES_EXTERNAS`, que **nao viaja no `.cgu`**. Ha teste que compara
# os tres com o contrato.


def sem_acento(texto: Any) -> str:
    """Sem acento e sem caixa. **O que a casa guarda chega escrito de todo
    jeito**, e o de-para casa pelo NOME."""
    cru = "" if texto is None else str(texto)
    return "".join(
        c for c in unicodedata.normalize("NFD", cru)
        if unicodedata.category(c) != "Mn").casefold()


# **OS TIPOS DE LOGRADOURO SERVEM AOS DOIS LADOS DO MESMO CONTRATO**, que e a
# razao de a tabela existir: no `indicadorRealRequest` o `tipoLogradouro` e um
# **integer** (o codigo), e no `editalRequest` e um **string max=16** (o nome).
# Mesmo nome de campo, dois tipos, no mesmo documento.
TIPOS_DE_LOGRADOURO: dict[int, str] = {{
{tabela(LOGRADOUROS)}
}}

# **UM NOME APARECE DUAS VEZES NO CATALOGO DELES**: «Alameda» e 4 e 645.
# Medido, e nao suposto. Para o caminho contrario — do nome para o codigo — o
# sistema fica com o **menor**, que e o da sequencia; a duplicata fica
# declarada para quem for conferir nao achar que a leitura se perdeu.
NOMES_REPETIDOS_NO_CATALOGO: dict[str, tuple[int, ...]] = {{
    "Alameda": (4, 645),
}}

# **O CONTRATO DELES ESCREVE «Ýrea» ONDE QUER DIZER «Área»**, e o glifo
# U+00DD (Ý) **nao existe em portugues** — o que faz dele, sozinho, prova de
# corrupcao. Medido em 15/09/2026: dos 129 nomes, **exatamente dois** o
# carregam, o 472 («Ýrea») e o 654 («Ýrea Especial»), e sao a MESMA palavra.
# A prosa do proprio contrato fecha a leitura: o campo `area` esta descrito
# como «Ýrea em metros quadrados do imovel rural…», onde `Ýrea` so pode ser
# «Area».
#
# **A TABELA ACIMA FICA COMO O CONTRATO A ESCREVEU**, e nao se emenda: o nome
# e o que o EDITAL manda (ali `tipoLogradouro` e `string max=16`), e inventar
# o que o outro lado escreveu seria pior que transcrever o defeito dele. Ha
# teste que compara os 129 com o contrato, e ele nao sabe deste mapa.
#
# O que entra aqui e so o caminho do NOME PARA O CODIGO — que e o que o
# indicador real usa: ele manda `472`, um integer, onde o glifo nem aparece.
# Sem isto a casa escrevia «Area», `sem_acento` levava o catalogo a `yrea`, e
# os dois nunca se encontravam: **o 472 existia e a regua nao o alcancava** —
# e o `tipoLogradouro` e OBRIGATORIO no indicador real, de modo que o ato
# inteiro era recusado por um caractere.
APELIDOS_DO_LOGRADOURO: dict[str, int] = {{
    "area": 472,
    "area especial": 654,
}}

TIPOS_DE_IMOVEL: dict[int, str] = {{
{tabela(IMOVEIS)}
}}

TIPOS_DE_ATO: dict[int, str] = {{
{tabela(ATOS)}
}}


def _de_para(pares: dict[int, str]) -> dict[str, int]:
    """Do nome escrito para o codigo. **Menor codigo ganha** — ver acima."""
    saida: dict[str, int] = {{}}
    for codigo, nome in sorted(pares.items()):
        saida.setdefault(sem_acento(nome), codigo)
    return saida


CODIGO_DO_LOGRADOURO: dict[str, int] = _de_para(TIPOS_DE_LOGRADOURO)
# **Os apelidos entram DEPOIS do de-para, e nao dentro dele**: o `setdefault`
# do menor codigo so age em nome que ainda nao esta la, e o nome corrompido já
# está — `yrea`. Somar isto ao `_de_para` faria o apelido nao entrar, calado.
CODIGO_DO_LOGRADOURO.update(APELIDOS_DO_LOGRADOURO)
CODIGO_DO_IMOVEL: dict[str, int] = _de_para(TIPOS_DE_IMOVEL)
CODIGO_DO_ATO: dict[str, int] = _de_para(TIPOS_DE_ATO)
{FECHA}
'''

alvo = Path("onr_api.py")
t = alvo.read_text(encoding="utf-8")

antigo = "# <<< tipos de logradouro — gerado por tools/gerar_logradouros.py"
antigo_fecha = "# >>> fim dos tipos de logradouro"
if antigo in t and antigo_fecha in t:
    t = (t[:t.index(antigo)]
         + t[t.index(antigo_fecha) + len(antigo_fecha) + 1:])

if ABRE in t and FECHA in t:
    t = (t[:t.index(ABRE)] + bloco
         + t[t.index(FECHA) + len(FECHA) + 1:])
else:
    marca = "\ndef _texto(v: Any) -> str:"
    assert marca in t, "nao achei onde inserir"
    t = t.replace(marca, "\n" + bloco + marca, 1)

if "import unicodedata" not in t:
    t = t.replace("import ssl\nimport time",
                  "import ssl\nimport time\nimport unicodedata", 1)

alvo.write_text(t, encoding="utf-8")
print(f"gerados: {len(LOGRADOUROS)} logradouros, {len(IMOVEIS)} imoveis, "
      f"{len(ATOS)} atos")
