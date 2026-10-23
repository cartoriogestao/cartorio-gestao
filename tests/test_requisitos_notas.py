"""Os modelos das Notas abarcam o que a LEI e as NORMAS exigem — LT02, 20/10/2026.

    «quero que seja possível do protocolo à certidão. Minha maior preocupação
     é que TODOS os atos precisam ter uma certidão adequada» — e depois:
    «TERMO E CERTIDÃO».                                  — o oficial, 20/10/2026

O QUE ESTE ARQUIVO MEDE
    A MATRIZ mora aqui, em `MATRIZ` (logo abaixo), e `docs/REQUISITOS_LEGAIS.md`
    (seção «Tabelionato de Notas») a descreve: para cada tipo de ato e de
    papel — as 35 minutas de fábrica (`modelos_padrao/notas/minutas/`) e os
    papéis das Notas do catálogo (qualificação, etiqueta do reconhecimento,
    autenticação, cartão de firma, pública forma, termo de comparecimento,
    termo do livro, traslado, certidões) —, cada ELEMENTO OBRIGATÓRIO, o
    artigo que o exige e onde ele aparece.

    Para cada elemento o teste MONTA o papel com um contexto de teste
    COMPLETO, pelo mesmo caminho do balcão, e confere duas coisas:
      - o RÓTULO — a frase que diz o que é o elemento — está no papel montado;
      - o VALOR — o que se preencheu no campo correspondente — também está.
    E, nas minutas, que o MODELO TEM O CAMPO: o valor só chega ao papel se o
    padrão tiver o claro de onde ele sai (`ri_modelos_atos.campos_do_modelo`).

    O termo de uma minuta se monta como `notas_web.notas_ato_preencher` o
    monta: o Jinja com `sv`, `lavrado_nome`, `lavrado_titulo` e as partes
    (`notas_teor.contexto_jinja_partes`), e depois `ri_modelos_atos.preencher`
    com TODOS os campos preenchidos, a primeira opção de cada escolha e TODAS
    as cláusulas «SE» ligadas — assim o elemento que só existe numa cláusula
    também é medido. A certidão de inteiro teor se monta como
    `notas_certidao.emitir` a monta (`montar_teor`, com o termo, o selo do ato e
    as anotações).

O QUE O ARQUIVO NÃO MEDE
    O que não é modelo da casa — a moldura que a rota acrescenta ao papel: o
    cabeçalho da serventia e o carimbo do selo (número, QR, consulta e
    emolumentos) do termo do livro, do traslado e da certidão. Esses saem do
    selo que o aparelho devolve e se conferem no papel de verdade, pelas telas,
    em `tests/test_fluxo_notas.py`. A pública forma é a exceção: a moldura
    dela (lugar e data, quem expede, a marca do selo) é montada por
    `nt_publica_forma.papel_html`, e a matriz a mede (LD07, 21/10/2026).

ELEMENTO QUE O MODELO NÃO TEM é DEFEITO do modelo: o caso fica marcado
`xfail(strict=True)` com o artigo, a asserção inteira. Consertado o modelo, o
teste avisa (XPASS estrito) — e a marca sai junto com o conserto.

Dados fictícios (docs/AGENTES.md): nomes «EXEMPLO», Cidade Exemplo, CNS
000000, CPFs da lista `tests/fixtures/anti_vazamento/documentos_ficticios.txt`.
"""
from __future__ import annotations

import html
import re
import sys
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import modelos_da_casa as MOD                                    # noqa: E402
import notas_certidao as NCE                                     # noqa: E402
import notas_familias as NF                                      # noqa: E402
import notas_livro as NL                                         # noqa: E402
import notas_modelos as NM                                       # noqa: E402
import notas_teor as NT                                          # noqa: E402
import nt_publica_forma as PF                                    # noqa: E402
from ri_modelos_atos import campos_do_modelo, pendencias, preencher  # noqa: E402
from serventia import dados as dados_da_serventia                # noqa: E402

# ================================================================ o contexto

SERVENTIA = dados_da_serventia({
    "unit_name": "TABELIONATO DE NOTAS DE CIDADE EXEMPLO",
    "serventia_titular": "BEATRIZ EXEMPLO DE SOUZA",
    "serventia_titulo": "Tabeliã e Oficiala de Registro",
    "serventia_cnpj": "00.000.001/0000-55",
    "serventia_endereco": "Rua Exemplo, 100, Centro",
    "serventia_cep": "65000-000",
    "serventia_telefone": "(99) 3000-0000",
    "ri_cidade": "Cidade Exemplo",
    "ri_uf": "MA",
    "ri_cns": "000000",
})
LAVRADO_NOME = "PEDRO EXEMPLO DOS SANTOS"
LAVRADO_TITULO = "Escrevente autorizado"

# A identidade e a união estável entram desde o LD07 (CNN art. 111): sem elas a
# qualificação sai com o colchete do que falta, e o termo não estaria completo.
OUTORGANTE = {"nome": "MARIO EXEMPLO DOS SANTOS", "documento": "00000000191",
              "tipo_pessoa": "F", "qualificacao": "OUTORGANTE", "testemunha": 0,
              "nacionalidade": "brasileiro", "estado_civil": "solteiro",
              "profissao": "comerciante", "identidade": "1234567 SSP/MA",
              "uniao_estavel": "NAO",
              "endereco": "Rua Exemplo, 10, Centro, Cidade Exemplo-MA"}
OUTORGADO = {"nome": "JOANA EXEMPLO DA SILVA", "documento": "00000000272",
             "tipo_pessoa": "F", "qualificacao": "OUTORGADO", "testemunha": 0,
             "nacionalidade": "brasileira", "estado_civil": "solteira",
             "profissao": "professora", "identidade": "7654321 SSP/MA",
             "uniao_estavel": "NAO",
             "endereco": "Rua Exemplo, 20, Centro, Cidade Exemplo-MA"}
# A parte casada, para a qualificação inteira: o cônjuge e o regime de bens só
# aparecem em quem é casado (CC art. 215, § 1º, III; CN-MA art. 798, V).
CASADO = dict(OUTORGANTE, estado_civil="casado", conjuge="ANA EXEMPLO DOS SANTOS",
              regime_bens="comunhão parcial")
TESTEMUNHAS = [
    {"nome": "PAULO EXEMPLO TESTEMUNHA", "documento": "00000000353",
     "tipo_pessoa": "F", "qualificacao": "TESTEMUNHA", "testemunha": 1,
     "nacionalidade": "brasileiro", "estado_civil": "casado",
     "profissao": "motorista", "endereco": "Rua Exemplo, 30, Cidade Exemplo-MA"},
    {"nome": "LUCIA EXEMPLO TESTEMUNHA", "documento": "00000001082",
     "tipo_pessoa": "F", "qualificacao": "TESTEMUNHA", "testemunha": 1,
     "nacionalidade": "brasileira", "estado_civil": "casada",
     "profissao": "costureira", "endereco": "Rua Exemplo, 40, Cidade Exemplo-MA"},
]

# O que a minuta recebe do cadastro e do balcão — o «@nome» dos elementos.
CONTEXTO_DA_MINUTA = {
    "outorgante": OUTORGANTE["nome"], "outorgante_cpf": OUTORGANTE["documento"],
    "outorgante_profissao": OUTORGANTE["profissao"],
    "outorgante_endereco": OUTORGANTE["endereco"],
    "outorgado": OUTORGADO["nome"], "outorgado_cpf": OUTORGADO["documento"],
    "testemunha1": TESTEMUNHAS[0]["nome"], "testemunha2": TESTEMUNHAS[1]["nome"],
    "cidade": SERVENTIA["ri_cidade"], "uf": SERVENTIA["ri_uf"],
    "lavrado_nome": LAVRADO_NOME, "lavrado_titulo": LAVRADO_TITULO,
}

# A data e a hora que o balcão escreve no ato (`valores_campos_data_lavratura`,
# a mesma régua que troca a data no dia do selo).
DATA_DO_ATO = NT.valores_campos_data_lavratura(datetime(2026, 10, 20, 10, 30))

SELO_DO_ATO = "AUTENT000000TESTE0000000007"
TEXTO_DO_SELO_DO_ATO = (
    f"Poder Judiciário – TJMA. Selo: {SELO_DO_ATO}, 20/10/2026 10:30:00, "
    "Ato: 13.2, Parte(s): MARIO EXEMPLO DOS SANTOS, Total R$ 167,02 Emol R$ "
    "149,57 FERC R$ 4,49 FADEP R$ 5,98 FEMP R$ 5,98 "
    "Consulte em https://selo.tjma.jus.br")


def _plano(texto) -> str:
    """O texto como se lê no papel: sem marca HTML, sem acento, minúsculo."""
    texto = html.unescape(re.sub(r"<[^>]+>", " ", str(texto or "")))
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return " ".join(texto.lower().split())


# ================================================================== a matriz


@dataclass(frozen=True)
class Elemento:
    """Um elemento que a norma exige no papel.

    `rotulo`: expressão regular, sobre o texto `_plano`, da frase que diz o
    que o elemento é. `valores`: o que tem de aparecer — `@nome` vem do
    contexto do papel; sem `@`, é o começo da chave de um campo da minuta
    (o campo tem de existir no modelo, e o valor preenchido nele tem de
    chegar ao papel). `a|b`: alternativas da mesma escolha (o processo OU a
    escritura) — os campos existem, e um dos valores chega. `defeito`: o
    modelo não tem o elemento (xfail estrito).
    """
    o_que: str
    artigo: str
    rotulo: str | None = None
    valores: tuple = ()
    defeito: str = ""


@dataclass(frozen=True)
class Tipo:
    chave: str          # a minuta (NT-…) ou o papel do catálogo (NOTAS_…)
    nome: str           # como a matriz o chama (e o .md também)
    elementos: tuple
    # A opção de cada escolha, quando não é a primeira: `(chave, pedaço da
    # opção)`. É o caso que tem o elemento — «com bens a partilhar».
    escolhas: tuple = ()


def E(o_que, artigo, rotulo=None, *valores, defeito=""):
    return Elemento(o_que, artigo, rotulo, tuple(valores), defeito)


# ------------------------------------------- o que vale para toda escritura

DATA = E("data do ato, com dia, mês e ano, por extenso e em algarismos",
         "CC art. 215, § 1º, I; CN-MA arts. 795, § 4º, e 798, I",
         r"aos .{1,60} dias do mes de .{1,20} do ano de",
         "dia_por_extenso", "dia_em_algarismos", "mes_por_extenso",
         "ano_por_extenso", "ano_em_algarismos")
HORA = E("hora do ato", "CN-MA art. 847, § 1º, I (ata); CC art. 1.864 (praxe do testamento)",
         r"\bhoras\b", "hora_por_extenso", "hora_em_algarismos")
LOCAL = E("local do ato (cidade e estado)", "CC art. 215, § 1º, I; CN-MA art. 798, I",
          r"nesta cidade de", "@cidade", "@uf")
QUEM_LAVRA = E("quem lavra o ato, com o cargo",
               "CN-MA arts. 798, XIII, e 861, § 10 (identificação de quem pratica)",
               r"perante mim", "@lavrado_nome", "@lavrado_titulo")
IDENTIDADE = E("reconhecimento da identidade de quem comparece",
               "CC art. 215, § 1º, II; CN-MA arts. 791, I, e 798, III",
               r"reconhecid[oa]s? como (o|a|os|as) propri")
QUALIFICACAO = E("nome e qualificação de quem comparece (pelo modelo NOTAS_QUALIFICACAO_PF)",
                 "CC art. 215, § 1º, III; CN-MA art. 798, V; CNN art. 111",
                 r"inscrito\(a\) no cpf", "@outorgante", "@outorgante_cpf",
                 "@outorgante_profissao", "@outorgante_endereco")
OUTORGADO_QUALIFICADO = E("nome e qualificação da outra parte (outorgado)",
                          "CC art. 215, § 1º, III; CN-MA art. 798, V",
                          None, "@outorgado", "@outorgado_cpf")
TESTEMUNHAS_DO_ATO = E("as testemunhas do ato, qualificadas",
                       "CC arts. 1.864, II, e 1.868, I; CN-MA art. 799, VIII",
                       r"testemunha", "@testemunha1", "@testemunha2")
LEITURA = E("declaração de que o ato foi lido",
            "CC art. 215, § 1º, VI; CN-MA arts. 798, XI, e 847, § 1º, IV",
            r"\blid[ao]\b|\bli em voz\b|\bo li\b|leitura")
ENCERRAMENTO = E("encerramento do ato", "CN-MA art. 798, XII", r"encerr")
ASSINATURAS = E("assinatura das partes e de quem lavra",
                "CC art. 215, § 1º, VII; CN-MA arts. 798, XIII, e 847, § 1º, V",
                r"assin")


def _escritura(*proprios, outorgado=True, hora=False, testemunhas=False):
    gerais = [DATA, LOCAL, QUEM_LAVRA, IDENTIDADE, QUALIFICACAO]
    if hora:
        gerais.insert(1, HORA)
    if outorgado:
        gerais.append(OUTORGADO_QUALIFICADO)
    if testemunhas:
        gerais.append(TESTEMUNHAS_DO_ATO)
    return tuple(gerais + list(proprios) + [LEITURA, ENCERRAMENTO, ASSINATURAS])


# ----------------------------------------------- o que vale para imóvel

def MATRICULA(*campos):
    return E("referência à matrícula ou ao registro anterior, com o número e o cartório",
             "Lei 6.015/1973, art. 222", r"matricul", *(campos or ("matricula",
                                                                    "cartorio")))


def DESCRICAO(*campos):
    return E("características, confrontações e localização do imóvel",
             "Lei 6.015/1973, art. 225; CN-MA art. 800, I", r"descrit|descricao",
             *(campos or ("descricao_do_imovel",)))


def INSS(defeito=""):
    return E("certidão do INSS (número, data e local) ou a declaração de que as "
             "partes não estão sujeitas", "CN-MA art. 800, III (Lei 8.212/1991, art. 47)",
             r"8\.212|\binss\b|previdenci", defeito=defeito)


def CADASTRO(*campos, defeito=""):
    return E("número do cadastro fiscal do imóvel (Prefeitura ou INCRA)",
             "CN-MA art. 800, IV", r"inscricao cadastral|cadastro (fiscal|imobiliario)|incra",
             *campos, defeito=defeito)


DOI = E("referência à emissão da DOI", "CN-MA arts. 797 e 800, VII (Lei 10.426/2002, art. 8º)",
        r"\bdoi\b|operacao imobiliaria")

# A certidão do INSS e o cadastro fiscal faltavam em sete escrituras de imóvel
# (doação, hipoteca, alienação fiduciária, confissão e dação, permuta, usufruto
# e a compra e venda rural) — consertado no LD07 (21/10/2026): a escolha do
# INSS (declaração de não sujeição ou a CND com número, data e local) e a do
# cadastro (Prefeitura, INCRA ou o comprovante de que não há lançamento).


def IMPOSTO(rotulo, *campos):
    return E("imposto de transmissão certificado (guia, data e valor quando houver)",
             "CN-MA arts. 791, VIII, e 798, § 3º", rotulo, *campos)


# ------------------------------------------- o que vale para sucessão e família

AUTOR_E_OBITO = E("autor da herança e o registro do óbito (dia, lugar, livro, folha, "
                  "termo e serventia)", "CN-MA art. 812, § 2º (Res. CNJ 35/2007, art. 21)",
                  r"obito", "nome_completo_do_autor_da_heranca", "data_do_obito",
                  "lugar_do_obito", "termo_do_obito", "livro_do_obito",
                  "folhas_do_obito", "serventia_do_registro_do_obito")
ADVOGADO = E("advogado das partes, qualificado e com a inscrição na OAB",
             "CN-MA arts. 808, § 1º, 819 e 822, § 5º", r"advogad|\boab\b",
             "nome_qualificacao_e_inscricao_na_oab")
CASAMENTO = E("o casamento: data, regime de bens e o registro (livro, folha, termo, "
              "serventia)", "CN-MA arts. 812, § 1º, 824, III, e 826, I",
              r"casamento", "data_do_casamento", "regime_de_bens", "termo_do_casamento",
              "livro_do_casamento", "folhas_do_casamento",
              "serventia_do_registro_do_casamento")
PARTILHA_PENSAO_NOME = E("a partilha dos bens comuns, a pensão alimentícia e o nome",
                         "CN-MA art. 822 (CPC art. 733)", r"partilha.*pensao.*nome|nome.*partilha",
                         )
CERTIDOES_FISCAIS = E("as certidões negativas das Fazendas Federal, Estadual e Municipal",
                      "CN-MA arts. 808, § 3º, e 817, parágrafo único",
                      r"fazendas? federal")
CENSEC = E("a certidão da CENSEC (RCTO) sobre a inexistência de testamento",
           "CN-MA arts. 811, XI, e 818, V; CNN art. 441, II", r"censec")


# ------------------------------------------------ o que vale para mandato

def MANDATO_DE_ORIGEM(rotulo, *campos):
    return E("o mandato de origem: serventia, data, livro e folhas",
             "CN-MA arts. 789, § 1º, e 831", rotulo, *campos)


MATRIZ: tuple[Tipo, ...] = (
    # ================================================================ escrituras
    Tipo("NT-ESC-COMPRA-VENDA", "Escritura de compra e venda de imóvel urbano", _escritura(
        E("natureza do negócio e o objeto", "CN-MA art. 798, VIII", r"vende"),
        DESCRICAO(), MATRICULA("matricula", "cartorio", "natureza_e_numero_do_registro"),
        E("preço e forma de pagamento", "CN-MA art. 798, VIII e IX", r"preco certo e ajustado",
          "preco_por_extenso", "preco_em_algarismos"),
        IMPOSTO(r"itbi", "numero_da_guia_de_itbi", "data_do_itbi", "valor_do_itbi"),
        INSS(), CADASTRO("inscricao_cadastral"),
        E("número predial e rua, se edificado", "CN-MA art. 800, V", r"numero predial",
          "numero_predial", "rua_do_imovel"),
        DOI,
        E("certidão atualizada da matrícula e de ônus reais", "CN-MA art. 791, IV "
          "(Lei 7.433/1985, art. 1º, § 2º — conferir no texto oficial)",
          r"certidao atualizada da matricula", "data_da_certidao_da_matricula"))),
    Tipo("NT-ESC-COMPRA-VENDA-RURAL", "Escritura de compra e venda de imóvel rural", _escritura(
        E("natureza do negócio e o objeto", "CN-MA art. 798, VIII", r"vende"),
        DESCRICAO("denominacao_do_imovel", "localizacao_do_imovel",
                  "descricao_do_imovel_com_confrontacoes"),
        MATRICULA(),
        E("preço e forma de pagamento", "CN-MA art. 798, VIII e IX", r"preco certo e ajustado",
          "preco_por_extenso", "preco_em_algarismos"),
        IMPOSTO(r"itbi", "numero_da_guia_de_itbi", "data_do_itbi"),
        E("CCIR: código do imóvel, nome e nacionalidade do detentor, denominação",
          "CN-MA arts. 801, V, e 802, § 5º", r"ccir", "codigo_do_imovel_no_incra",
          "nome_do_detentor", "nacionalidade_do_detentor", "denominacao_no_ccir"),
        E("módulo e área do imóvel rural", "CN-MA art. 801, V", r"modulo",
          "area_do_ccir", "modulo_fiscal"),
        E("ITR dos cinco últimos exercícios", "CN-MA arts. 791, XI, e 802",
          r"\bitr\b|territorial rural", "exercicios_do_itr"),
        INSS(), CADASTRO(), DOI)),
    Tipo("NT-ESC-DOACAO", "Escritura de doação", _escritura(
        E("natureza do negócio e o objeto", "CN-MA art. 798, VIII", r"\bdoa"),
        E("aceitação do donatário", "CC art. 539 (conferir no texto oficial)", r"aceita"),
        DESCRICAO(), MATRICULA(),
        IMPOSTO(r"itcmd|itcd|imposto", "numero_da_guia_de_itcmd", "data_do_itcmd"),
        DOI, INSS(), CADASTRO("inscricao_cadastral"))),
    Tipo("NT-ESC-HIPOTECA", "Escritura de hipoteca", _escritura(
        E("o valor da dívida, o prazo e os juros", "CC art. 1.424, I a III (conferir no texto oficial)",
          r"juros", "valor_da_divida_por_extenso", "valor_da_divida_em_algarismos",
          "taxa_de_juros", "prazo_da_hipoteca"),
        E("o bem dado em garantia, especificado", "CC art. 1.424, IV; Lei 6.015/1973, art. 225",
          r"hipotec", "descricao_do_imovel"),
        MATRICULA(),
        E("a outorga do cônjuge do devedor", "CC art. 1.647, I (conferir no texto oficial)",
          r"conjuge", "nome_e_qualificacao_do_conjuge"),
        INSS(), CADASTRO("inscricao_cadastral"))),
    Tipo("NT-ESC-ALIENACAO-FIDUCIARIA", "Escritura de alienação fiduciária de imóvel", _escritura(
        E("o principal da dívida, o prazo, os juros e os encargos",
          "Lei 9.514/1997, art. 24, I a III (conferir no texto oficial)", r"juros",
          "valor_do_principal", "numero_de_parcelas", "taxa_de_juros", "encargos_incidentes"),
        E("a propriedade fiduciária, com a descrição do imóvel",
          "Lei 9.514/1997, art. 24, IV (conferir no texto oficial)", r"fiduciari",
          "descricao_do_imovel"),
        E("a livre utilização do imóvel pelo fiduciante",
          "Lei 9.514/1997, art. 24, V (conferir no texto oficial)", r"livre utilizacao"),
        E("o valor do imóvel para leilão e o critério de revisão",
          "Lei 9.514/1997, art. 24, VI (conferir no texto oficial)", r"leilao",
          "valor_do_imovel_para_leilao", "criterio_de_revisao"),
        MATRICULA(), INSS(), CADASTRO("inscricao_cadastral"))),
    Tipo("NT-ESC-CONFISSAO-DACAO", "Escritura de confissão de dívida e dação em pagamento", _escritura(
        E("a dívida confessada", "CC art. 356 (conferir no texto oficial)", r"divida",
          "valor_da_divida", "origem_da_divida"),
        E("o imóvel dado em pagamento e o valor atribuído", "CC art. 357; CN-MA art. 800, I",
          r"dacao|dado em pagamento", "descricao_do_imovel", "valor_atribuido_ao_imovel"),
        MATRICULA(), IMPOSTO(r"itbi", "numero_da_guia_de_itbi", "data_do_itbi"), DOI,
        INSS(), CADASTRO("inscricao_cadastral"))),
    Tipo("NT-ESC-PERMUTA", "Escritura de permuta", _escritura(
        E("os dois imóveis permutados, descritos, e o valor de cada um",
          "CC art. 533; Lei 6.015/1973, art. 225", r"permut",
          "descricao_do_primeiro_imovel", "descricao_do_segundo_imovel",
          "valor_do_primeiro_imovel", "valor_do_segundo_imovel"),
        E("a torna, quando houver", "CC art. 533 (conferir no texto oficial)", r"torna",
          "valor_da_torna"),
        MATRICULA("matricula_do_primeiro_imovel", "matricula_do_segundo_imovel"),
        IMPOSTO(r"itbi", "numeros_das_guias_de_itbi", "datas_do_itbi"), DOI,
        INSS(), CADASTRO("inscricao_cadastral_do_primeiro_imovel",
                         "inscricao_cadastral_do_segundo_imovel"), outorgado=False),
        escolhas=(("op_torna", "valores desiguais"),)),
    Tipo("NT-ESC-USUFRUTO", "Escritura de usufruto", _escritura(
        E("o usufruto, o imóvel e o prazo", "CC arts. 1.390 e 1.410 (conferir no texto oficial)",
          r"usufrut", "descricao_do_imovel", "prazo_do_usufruto"),
        MATRICULA(), IMPOSTO(r"imposto", "numero_da_guia_do_imposto", "data_do_imposto"),
        INSS(), CADASTRO("inscricao_cadastral")),
        escolhas=(("op_duracao", "pelo prazo"),)),
    Tipo("NT-ESC-CESSAO-HEREDITARIA", "Escritura de cessão de direitos hereditários", _escritura(
        E("o autor da herança e o registro do óbito", "CN-MA art. 803 (identificação da herança)",
          r"obito", "nome_do_autor_da_heranca", "data_do_obito", "termo_do_obito",
          "livro_do_obito", "folhas_do_obito", "serventia_do_registro_do_obito"),
        E("a cessão abrange também as dívidas do espólio", "CN-MA art. 803",
          r"dividas do espolio"),
        E("a ciência dos demais coerdeiros", "CN-MA art. 804 (CC art. 1.795)",
          r"coerdeiros", "forma_da_ciencia_aos_coerdeiros"),
        E("o imposto de transmissão", "CN-MA art. 804", r"imposto",
          "numero_da_guia_do_imposto", "data_do_imposto"),
        E("a outorga do cônjuge do cedente, ou o regime que a dispensa",
          "CN-MA art. 804, §§ 4º e 5º", r"outorga", "nome_e_qualificacao_do_conjuge_do_cedente"),
        E("o quinhão em fração, e não em dinheiro", "CN-MA art. 805, parágrafo único",
          r"fracao", "quinhao_ideal"),
        # consertado no LD07 (21/10/2026): a frase do § 8º, logo depois da do art. 803
        E("a ciência de que é negócio de risco: só produz efeito na partilha, se o bem "
          "couber ao cedente", "CN-MA art. 804, § 8º",
          r"negocio de risco|so produzira efeito|caso o bem .{0,80} atribuido"),
        testemunhas=True)),
    Tipo("NT-ESC-INVENTARIO-PARTILHA", "Escritura de inventário e partilha", _escritura(
        AUTOR_E_OBITO,
        E("a qualificação completa do autor da herança e o regime de bens",
          "CN-MA art. 812, § 2º", r"autor da heranca", "qualificacao_completa_do_autor",
          "regime_de_bens_do_autor"),
        E("a data de expedição da certidão de óbito", "CN-MA art. 812, § 2º",
          r"certidao de obito", "data_da_expedicao_da_certidao_de_obito"),
        E("a declaração de que não há testamento nem outros herdeiros",
          "CN-MA arts. 811, X, e 812, § 2º", r"nao deixou testamento"),
        CENSEC,
        E("os herdeiros, com o vínculo de parentesco", "CN-MA art. 812, VI", r"herdeir",
          "nomes_e_qualificacao_dos_herdeiros"),
        E("o inventariante", "CN-MA arts. 811, XV, e 812, VII", r"inventariante",
          "nome_do_inventariante"),
        ADVOGADO,
        E("os bens, com os valores, e a partilha", "CN-MA art. 812, IX, X e XIV", r"partilha",
          "descricao_dos_imoveis", "descricao_dos_bens_moveis", "partilha_com_o_quinhao"),
        E("os impostos pagos, especificados", "CN-MA arts. 808, § 2º, e 812, XVII",
          r"itcd", "numero_da_guia_de_itcd", "data_do_itcd", "valor_do_itcd"),
        CERTIDOES_FISCAIS, outorgado=False)),
    Tipo("NT-ESC-SOBREPARTILHA", "Escritura de sobrepartilha", _escritura(
        AUTOR_E_OBITO,
        E("o inventário anterior (processo ou escritura)", "CN-MA art. 813",
          r"inventario", "numero_do_processo_de_inventario|data_da_escritura_anterior"),
        E("os bens sobrepartilháveis, com valores, e a sobrepartilha", "CN-MA art. 817",
          r"sobrepartilh", "descricao_dos_bens_sobrepartilhaveis",
          "sobrepartilha_com_o_quinhao"),
        E("os herdeiros", "CN-MA art. 812, VI", r"herdeir", "nomes_e_qualificacao_dos_herdeiros"),
        ADVOGADO,
        E("o imposto", "CN-MA art. 817", r"itcd", "numero_da_guia_de_itcd", "data_do_itcd"),
        CERTIDOES_FISCAIS, CENSEC, outorgado=False)),
    Tipo("NT-ESC-PARTILHA-ADJUDICACAO", "Escritura de partilha ou adjudicação", _escritura(
        AUTOR_E_OBITO,
        E("os herdeiros, ou o herdeiro único", "CN-MA art. 814", r"herdeir",
          "nomes_e_qualificacao_dos_herdeiros"),
        ADVOGADO,
        E("os bens com o valor da avaliação, e a partilha", "CN-MA arts. 817 e 819, parágrafo único",
          r"avaliacao", "descricao_dos_bens_com_os_valores", "partilha_com_o_quinhao"),
        E("o imposto", "CN-MA arts. 817 e 819, parágrafo único", r"imposto",
          "numero_da_guia_do_imposto", "data_do_imposto", "valor_do_imposto"),
        CERTIDOES_FISCAIS,
        E("a certidão da CENSEC sobre testamento", "CN-MA art. 818, V", r"censec",
          "numero_da_certidao_da_censec", "data_da_certidao_da_censec"),
        outorgado=False)),
    Tipo("NT-ESC-NOMEACAO-INVENTARIANTE", "Escritura de nomeação de inventariante", _escritura(
        AUTOR_E_OBITO,
        E("o inventariante nomeado", "CN-MA art. 810", r"inventariante",
          "nome_e_qualificacao_do_inventariante"),
        E("os poderes perante bancos e repartições fiscais", "CN-MA art. 810",
          r"banc"),
        ADVOGADO, outorgado=False)),
    Tipo("NT-ESC-DIVORCIO", "Escritura de divórcio consensual", _escritura(
        CASAMENTO,
        E("a descrição e a partilha dos bens comuns", "CN-MA art. 822", r"partilha",
          "descricao_e_partilha_dos_bens_comuns"),
        E("a pensão alimentícia entre os cônjuges", "CN-MA art. 822", r"pensao"),
        E("o nome que o cônjuge passa a usar", "CN-MA art. 822 e § 14", r"\bnome\b"),
        E("os filhos incapazes: compromisso de levar ao Judiciário", "CN-MA art. 822, § 1º",
          r"filhos", "nomes_e_datas_de_nascimento_dos_filhos_incapazes"),
        ADVOGADO,
        E("o processo judicial anterior, se houver", "CN-MA art. 821 (por analogia)",
          r"processo", "numero_do_processo_judicial"), outorgado=False),
        escolhas=(("op_partilha", "partilhados da seguinte forma"),
                  ("op_filhos", "incapazes"))),
    Tipo("NT-ESC-SEPARACAO", "Escritura de separação consensual", _escritura(
        E("a vontade de não manter a sociedade conjugal", "CN-MA art. 823, I",
          r"vontade de separar"),
        CASAMENTO,
        E("a partilha, a pensão e o nome", "CN-MA art. 822", r"partilha"),
        E("a ausência de filhos incapazes, ou o compromisso", "CN-MA arts. 822, § 1º, e 823, II",
          r"filhos"),
        ADVOGADO, outorgado=False)),
    Tipo("NT-ESC-CONVERSAO-DIVORCIO", "Escritura de conversão da separação em divórcio", _escritura(
        E("a separação anterior e a sua averbação", "CN-MA art. 830",
          r"separacao", "numero_do_processo_de_separacao|data_da_escritura_de_separacao",
          "data_da_averbacao_da_separacao"),
        E("o casamento: data, regime e registro", "CN-MA art. 830", r"casamento",
          "data_do_casamento", "regime_de_bens", "termo_do_casamento"),
        E("a partilha, a pensão e o nome", "CN-MA art. 822", r"partilha"),
        ADVOGADO, outorgado=False)),
    Tipo("NT-ESC-RESTABELECIMENTO", "Escritura de restabelecimento da sociedade conjugal", _escritura(
        E("o casamento e a separação que se desfaz", "CN-MA arts. 828 e 829", r"separacao",
          "data_do_casamento", "termo_do_casamento",
          "numero_do_processo_de_separacao|data_da_escritura_de_separacao"),
        E("a orientação de levar o traslado ao registro civil", "CN-MA art. 829, I",
          r"traslado .{0,80}registro civil"),
        E("a anotação à margem da separação, ou a comunicação", "CN-MA art. 829, II e III",
          r"anot|comunic"), outorgado=False)),
    Tipo("NT-ESC-UNIAO-ESTAVEL", "Escritura declaratória de união estável", _escritura(
        E("a data de início da união", "CNN art. 537, § 4º; CC art. 1.723", r"uniao",
          "data_de_inicio_da_uniao"),
        E("o regime de bens", "CC art. 1.725 (conferir no texto oficial)", r"regime",
          "regime_de_bens_estipulado"),
        E("a separação de fato de quem ainda é casado", "CC art. 1.723, § 1º "
          "(conferir no texto oficial)", r"separad[oa] de fato", "nome_de_quem_e_casado",
          "data_da_separacao_de_fato"), outorgado=False),
        escolhas=(("op_regime", "estipulam"),)),
    Tipo("NT-ESC-DISSOLUCAO-UNIAO-ESTAVEL", "Escritura de dissolução de união estável", _escritura(
        E("o início e o fim da união", "CNN art. 537, § 4º; CN-MA art. 822", r"uniao",
          "data_de_inicio_da_uniao", "data_do_fim_da_uniao"),
        E("o regime de bens da união", "CN-MA art. 822", r"regime", "regime_de_bens_da_uniao"),
        E("a partilha, a pensão e o nome", "CN-MA art. 822", r"partilha"),
        ADVOGADO, outorgado=False)),
    Tipo("NT-ESC-EMANCIPACAO", "Escritura de emancipação", _escritura(
        E("a concessão da emancipação pelos pais", "CC art. 5º, parágrafo único, I "
          "(conferir no texto oficial)", r"emancip"),
        E("a data de nascimento e o registro do nascimento do emancipado (data e cartório)",
          "Lei 6.015/1973, art. 90, 2º", r"nascimento", "data_de_nascimento_do_emancipando",
          "termo_do_nascimento", "livro_do_nascimento", "folhas_do_nascimento",
          "serventia_do_registro_de_nascimento"),
        E("a filiação do emancipado", "Lei 6.015/1973, art. 90, 2º",
          r"(os pais|o pai|a mae) do emancipando"),
        # consertado no LD07 (21/10/2026)
        E("a naturalidade do emancipado e dos pais", "Lei 6.015/1973, art. 90, 2º e 3º",
          r"natural de|naturalidade", "naturalidade_do_emancipando",
          "naturalidade_dos_outorgantes"))),
    Tipo("NT-ESC-PACTO-ANTENUPCIAL", "Escritura de pacto antenupcial", _escritura(
        E("o regime de bens escolhido", "CC art. 1.653 (conferir no texto oficial)", r"regime"),
        E("a habilitação para o casamento", "CC art. 1.653", r"habilitac",
          "serventia_da_habilitacao", "numero_da_habilitacao"),
        E("o registro no Registro de Imóveis do domicílio", "CC art. 1.657; Lei 6.015/1973, "
          "art. 244 (conferir no texto oficial)", r"registro de imoveis"),
        outorgado=False)),
    Tipo("NT-ESC-QUITACAO", "Escritura de quitação", _escritura(
        E("o valor e a espécie da dívida quitada", "CC art. 320 (conferir no texto oficial)",
          r"quita", "valor_da_divida", "especie_e_origem_da_divida"),
        E("o nome do devedor", "CC art. 320", r"devedor", "nome_e_qualificacao_do_devedor"),
        E("o tempo e o lugar do pagamento", "CC art. 320", r"pagamento",
          "data_do_pagamento", "lugar_do_pagamento"), outorgado=False)),
    Tipo("NT-ESC-DISTRATO", "Escritura de distrato", _escritura(
        E("o contrato desfeito, identificado (natureza, data, livro, folhas, serventia)",
          "CC art. 472 (conferir no texto oficial)", r"distrat|desfe",
          "natureza_do_contrato_desfeito", "data_do_contrato", "livro_do_contrato",
          "folhas_do_contrato", "serventia_do_contrato"),
        E("o objeto e as restituições", "CC art. 472", r"restitu",
          "objeto_do_contrato_desfeito", "o_que_e_restituido"), outorgado=False),
        escolhas=(("op_restituicoes", "Em razão do distrato"),)),
    Tipo("NT-ESC-DIRETIVAS-VONTADE", "Escritura de diretivas antecipadas de vontade", _escritura(
        E("a capacidade do declarante", "CN-MA art. 876", r"capa[zc]"),
        E("as diretrizes sobre cuidados e tratamentos de saúde", "CN-MA art. 876",
          r"tratamento", "diretrizes_e_vontades_sobre_cuidados"),
        E("o procurador de saúde, quando nomeado", "CN-MA art. 877", r"procurador",
          "nome_e_qualificacao_do_procurador_de_saude"), outorgado=False)),

    # ========================================================= procurações
    Tipo("NT-PROC-PUBLICA", "Procuração pública", _escritura(
        E("os poderes, com a designação e a extensão", "CC art. 654, § 1º "
          "(conferir no texto oficial)", r"poderes", "descricao_dos_poderes"),
        E("os poderes especiais, expressos", "CC art. 661, § 1º (conferir no texto oficial)",
          r"poderes especiais", "poderes_especiais"),
        E("o imóvel e a certidão atualizada do registro de imóveis", "CN-MA art. 833",
          r"certidao atualizada do registro", "matricula", "data_da_certidao_do_registro"),
        E("o prazo do mandato", "CC art. 682, IV (conferir no texto oficial)",
          r"vigorara|validade"))),
    Tipo("NT-PROC-CAUSA-PROPRIA", "Procuração em causa própria", _escritura(
        E("o objeto, com os poderes que exorbitam a administração", "CN-MA art. 835, IV",
          r"causa propria", "objeto_da_procuracao_em_causa_propria"),
        E("o preço pago", "CN-MA art. 835, II", r"preco", "preco_por_extenso",
          "preco_em_algarismos"),
        E("a irrevogabilidade", "CC art. 685 (conferir no texto oficial)", r"irrevogavel"),
        # consertado no LD07 (21/10/2026)
        E("o prévio recolhimento do ITBI", "CN-MA art. 835, III",
          r"itbi|imposto de transmissao", "numero_da_guia_de_itbi", "data_do_itbi"))),
    Tipo("NT-PROC-PREVIDENCIARIA", "Procuração para fins previdenciários", _escritura(
        E("a finalidade junto ao INSS e o benefício", "Lei 8.213/1991, art. 109 "
          "(conferir no texto oficial)", r"\binss\b|previdenci", "numero_do_beneficio"),
        E("a validade não superior a doze meses", "Lei 8.213/1991, art. 109 "
          "(conferir no texto oficial)", r"validade", "data_de_validade"))),
    Tipo("NT-SUBSTABELECIMENTO", "Substabelecimento", _escritura(
        MANDATO_DE_ORIGEM(r"procuracao lavrada", "data_da_procuracao_originaria",
                          "livro_da_procuracao_originaria", "folhas_da_procuracao_originaria",
                          "serventia_da_procuracao_originaria"),
        E("com ou sem reserva de poderes", "CC art. 667 (conferir no texto oficial)",
          r"reserva"),
        E("os poderes substabelecidos", "CN-MA art. 789", r"poderes", "poderes_substabelecidos"))),
    Tipo("NT-REVOGACAO-MANDATO", "Revogação de mandato", _escritura(
        MANDATO_DE_ORIGEM(r"instrumento publico lavrado", "data_da_procuracao_revogada",
                          "livro_da_procuracao_revogada", "folhas_da_procuracao_revogada",
                          "serventia_da_procuracao_revogada"),
        E("a advertência de que é imprescindível notificar o mandatário",
          "CN-MA art. 831, § 2º", r"notificar o mandatario"),
        E("a anotação à margem do ato revogado, ou a comunicação à outra serventia",
          "CN-MA art. 831 e § 1º", r"anotacao|comunicada"))),
    Tipo("NT-RENUNCIA-MANDATO", "Renúncia de mandato", _escritura(
        E("o mandante", "CN-MA art. 831, § 4º", r"procurador de", "nome_do_mandante"),
        MANDATO_DE_ORIGEM(r"instrumento publico lavrado", "data_da_procuracao_renunciada",
                          "livro_da_procuracao_renunciada", "folhas_da_procuracao_renunciada",
                          "serventia_da_procuracao_renunciada"),
        E("a advertência de comunicar a renúncia ao mandante", "CN-MA art. 831, § 4º "
          "(CC art. 688)", r"comunicar a renuncia"),
        E("a anotação à margem, ou a comunicação à outra serventia", "CN-MA art. 831 e § 1º",
          r"anotacao|comunicada"), outorgado=False)),

    # =========================================================== testamentos
    Tipo("NT-TESTAMENTO-PUBLICO", "Testamento público", _escritura(
        E("a capacidade do testador", "CC art. 1.860 (conferir no texto oficial)",
          r"pleno gozo de suas faculdades"),
        E("escrito pelo tabelião, de acordo com as declarações do testador",
          "CC art. 1.864, I (conferir no texto oficial)", r"assim eu escrevi"),
        E("lido em voz alta ao testador e às duas testemunhas, a um só tempo",
          "CC art. 1.864, II", r"voz alta ao testador e as duas testemunhas, a um so tempo"),
        E("assinado pelo testador, pelas testemunhas e pelo tabelião", "CC art. 1.864, III",
          r"assinam o testador, as duas testemunhas"),
        E("as disposições, com cada herdeiro ou legatário", "CC art. 1.857 "
          "(conferir no texto oficial)", r"dispoe", "disposicoes_testamentarias"),
        hora=True, outorgado=False, testemunhas=True)),
    Tipo("NT-TESTAMENTO-CERRADO", "Testamento cerrado — auto de aprovação", _escritura(
        E("a entrega do testamento ao tabelião, na presença de duas testemunhas",
          "CC art. 1.868, I (conferir no texto oficial)", r"me foi entregue"),
        E("a declaração de que é o seu testamento e quer que seja aprovado",
          "CC art. 1.868, II", r"quer que seja aprovado"),
        E("o auto começa logo depois da última palavra do testador", "CC art. 1.869",
          r"ultimas? palavras?|termina com as palavras", "ultimas_palavras_do_testador"),
        E("o auto lido ao testador e às testemunhas, e assinado por todos",
          "CC art. 1.868, III e IV", r"li em voz alta ao testador"),
        E("o testamento cerrado e cosido", "CC art. 1.869", r"cerrei e cosi"),
        E("a nota no livro do lugar, dia, mês e ano da aprovação", "CC art. 1.874",
          r"nota do lugar"),
        E("o número de folhas do testamento", "CC art. 1.868 (praxe)", r"folha",
          "numero_de_folhas_do_testamento"),
        hora=True, outorgado=False, testemunhas=True)),

    # ================================================================ atas
    Tipo("NT-ATA-NOTARIAL", "Ata notarial", _escritura(
        E("o solicitante, nome e qualificação", "CN-MA art. 847, § 1º, II", r"solicitante"),
        E("a narração circunstanciada dos fatos", "CN-MA art. 847, § 1º, III", r"narrar",
          "narracao_circunstanciada"),
        E("o documento transcrito na íntegra, quando houver", "CN-MA art. 847, § 4º",
          r"transcrevo integralmente", "teor_integral_do_documento"),
        E("os anexos numerados e arquivados", "CN-MA art. 847, § 5º", r"anexad",
          "relacao_dos_documentos_anexados"),
        hora=True, outorgado=False, testemunhas=True)),
    Tipo("NT-ATA-USUCAPIAO", "Ata notarial para usucapião extrajudicial", _escritura(
        E("a modalidade de usucapião e a base legal", "CNN art. 401, I, d", r"modalidade"),
        E("a descrição do imóvel e as características", "CNN art. 401, I, a", r"descrito",
          "descricao_do_imovel_conforme_planta"),
        E("a matrícula, ou a informação de que não há", "CNN art. 400, IV", r"matricula",
          "matricula"),
        E("o tempo e as características da posse do requerente e dos antecessores",
          "CNN art. 401, I, b; CN-MA art. 846, V", r"posse", "data_de_inicio_da_posse",
          "nomes_dos_antecessores", "tempo_total_de_posse"),
        E("os documentos da origem, continuidade e tempo da posse", "CNN art. 401, III",
          r"documentos", "relacao_dos_documentos_que_demonstram"),
        E("a ata não declara a propriedade: serve ao pedido no registro de imóveis",
          "CNN art. 402, § 3º", r"nao declara a propriedade"),
        # os seis de baixo, consertados no LD07 (21/10/2026)
        E("o valor do imóvel", "CNN arts. 400, V, e 401, I, f",
          r"valor (do|atribuido ao) imovel", "valor_do_imovel"),
        E("o titular do imóvel na matrícula", "CNN art. 401, I", r"titular",
          "qualificacao_do_titular_do_imovel"),
        E("a forma de aquisição da posse pelo requerente", "CNN art. 401, I, c",
          r"adquiri|aquisicao da posse", "forma_de_aquisicao_da_posse"),
        E("o número de imóveis e as circunscrições em que estão", "CNN art. 401, I, e",
          r"circunscri", "numero_de_imoveis_atingidos"),
        E("o alerta ao requerente e às testemunhas de que declaração falsa é crime",
          "CNN art. 402", r"falsidade|\bcrime\b"),
        E("o endereço eletrônico do requerente", "CNN art. 401, I",
          r"endereco eletronico|e-mail", "endereco_eletronico_do_requerente"),
        hora=True, outorgado=False, testemunhas=True)),
    Tipo("NT-ATA-ADJUDICACAO", "Ata notarial para adjudicação compulsória", _escritura(
        E("o requerente e a sua qualidade (promitente comprador ou cessionário)",
          "CN-MA art. 848, § 1º, I", r"na qualidade de"),
        E("o imóvel conforme a matrícula e o cadastro imobiliário",
          "CN-MA art. 848, § 1º, II; CNN art. 440-G, I", r"matricula",
          "matricula", "inscricao_cadastral", "descricao_do_imovel"),
        E("o contrato e a prova da quitação", "CN-MA art. 848, § 1º, III; CNN art. 440-G, II e III",
          r"quitacao", "data_do_contrato", "nome_do_promitente_vendedor", "prova_da_quitacao"),
        E("a notificação do promitente vendedor e a sua inércia",
          "CN-MA art. 848, § 1º, IV; CNN art. 440-G, IV", r"notificacao",
          "data_da_notificacao", "forma_da_notificacao", "prazo_da_notificacao"),
        E("a certidão de inexistência de litígio", "CN-MA art. 848, § 1º, V",
          r"inexistencia de litigio", "data_da_certidao_de_inexistencia"),
        # os dois de baixo, consertados no LD07 (21/10/2026)
        E("os ônus e gravames do imóvel", "CNN art. 440-G, I", r"onus|gravame",
          "op_onus_e_gravames"),
        E("o valor venal do imóvel", "CNN art. 440-G, V", r"valor venal",
          "valor_venal_do_imovel"),
        # consertado no LH13 (21/10/2026), pela resposta do oficial à pergunta
        # 12 — letra a: o CNN prevalece, e a frase do CN-MA art. 848, § 2º («título
        # hábil para ingresso no Registro de Imóveis») saiu da minuta
        E("a advertência de que a ata não é título de propriedade", "CNN art. 440-G, § 2º "
          "(no lugar do CN-MA art. 848, § 2º, que dizia o contrário)",
          r"nao tem valor de titulo de propriedade; presta-se a instrucao do pedido de "
          r"adjudicacao compulsoria perante o registro de imoveis e podera ser aproveitada "
          r"em processo judicial"),
        hora=True, outorgado=False)),

    # ============================================== papéis do catálogo
    Tipo("NOTAS_QUALIFICACAO_PF", "Qualificação da pessoa física (todo ato de livro)", (
        E("o nome completo", "CC art. 215, § 1º, III; CNN art. 111", None, "@nome"),
        E("a nacionalidade", "CC art. 215, § 1º, III; CNN art. 111", None, "@nacionalidade"),
        E("o estado civil", "CC art. 215, § 1º, III; CNN art. 111", None, "@estado_civil"),
        E("a profissão", "CC art. 215, § 1º, III; CNN art. 111", None, "@profissao"),
        E("o CPF", "CNN art. 111; CN-MA art. 798, V e § 1º", r"\bcpf\b", "@documento"),
        E("o domicílio e a residência", "CC art. 215, § 1º, III; CNN art. 111",
          r"residente e domiciliad", "@endereco"),
        # os três de baixo, consertados no LD07 (21/10/2026): as peças do papel e
        # os campos da parte do ato
        E("o documento de identificação (ou, na falta dele, a filiação)",
          "CNN art. 111; CN-MA art. 798, V", r"\brg\b|identidade|filh[oa] de|filiacao",
          "@identidade"),
        E("a existência de união estável", "CNN art. 111", r"uniao estavel|convivente"),
        E("o nome do cônjuge e o regime de bens, quando casado (ato sobre imóvel)",
          "CC art. 215, § 1º, III; CN-MA art. 798, V", r"conjuge|regime de bens",
          "@conjuge", "@regime_bens"),
    )),
    Tipo("NOTAS_QUALIFICACAO_PJ", "Qualificação da pessoa jurídica", (
        E("o nome empresarial", "CN-MA art. 791, II", None, "@nome"),
        E("o CNPJ", "CN-MA art. 798, § 1º", r"\bcnpj\b", "@documento"),
        E("a sede", "CC art. 215, § 1º, III", r"\bsede\b", "@endereco"),
    )),
    Tipo("NOTAS_RECONHECIMENTO_SEMELHANCA", "Reconhecimento de firma por semelhança", (
        E("a espécie do reconhecimento, expressa", "CN-MA art. 861, §§ 2º e 5º",
          r"por semelhanca"),
        E("o nome de quem teve a firma reconhecida, sem «supra» ou «retro»",
          "CN-MA art. 861, § 5º", None, "@quem"),
    )),
    Tipo("NOTAS_RECONHECIMENTO_AUTENTICIDADE", "Reconhecimento de firma por autenticidade", (
        E("a espécie do reconhecimento, expressa", "CN-MA art. 861, §§ 1º e 5º",
          r"por autenticidade"),
        E("o nome de quem teve a firma reconhecida", "CN-MA art. 861, § 5º", None, "@quem"),
    )),
    Tipo("NOTAS_RECONHECIMENTO_SINAL", "Reconhecimento de sinal público", (
        E("o reconhecimento do sinal público", "CN-MA arts. 870 e 873", r"sinal publico"),
        E("o nome de quem tem o sinal", "CN-MA art. 873", None, "@quem"),
    )),
    Tipo("NOTAS_ETIQUETA_FECHO__local_e_data", "Fecho da etiqueta: local e data", (
        E("o local e a data do ato", "CN-MA art. 861, § 1º (data do reconhecimento)",
          None, "@local", "@dia"),
    )),
    Tipo("ETIQUETA", "Etiqueta do reconhecimento e da autenticação (templates/notas_etiqueta.html)", (
        E("o nome de quem pratica o ato, legível", "CN-MA art. 861, § 10", r"e\.oficial"),
        E("a função de quem pratica", "CN-MA art. 861, § 10", r"e\.funcao"),
        E("o selo no corpo do ato", "CN-MA arts. 130 e 131", r"e\.selo"),
        E("o QR do selo, para a consulta pública", "CN-MA art. 132", r"e\.qr"),
        E("os emolumentos que o selo declara", "CN-MA art. 87, XVI", r"e\.valores"),
    )),
    Tipo("NOTAS_TERMO_COMPARECIMENTO", "Termo de comparecimento (presença) do reconhecimento por autenticidade", (
        E("o nome de quem compareceu", "CN-MA art. 866", r"compareceu", "@nome"),
        E("o documento de identificação", "CN-MA art. 866", r"cpf", "@documento"),
        E("o número do selo do reconhecimento", "CN-MA art. 866", r"\bselo\b", "@selo"),
        E("a data do comparecimento", "CN-MA art. 866", r"aos ", "@data_extenso"),
        E("a assinatura do interessado", "CN-MA art. 866", r"_{8,}"),
        # o claro existe desde o LD02; a matriz passou a montá-lo no LD07
        E("a ordem (o número) do termo", "CN-MA art. 866", r"ordem|termo n", "@ordem"),
    )),
    Tipo("NOTAS_AUTENTICACAO", "Autenticação de cópia", (
        E("a conferência da cópia com o original", "CN-MA art. 836", r"fiel da original"),
        # consertado no LD07 (21/10/2026): a peça da ressalva, e o campo na tela
        E("a ressalva da rasura ou do defeito do original", "CN-MA art. 836",
          r"ressalv|rasura|defeito", "@ressalva"),
    )),
    Tipo("NOTAS_AUTENTICACAO_INTERNET", "Autenticação de documento da internet", (
        E("a conferência com o original", "CN-MA art. 839", r"fiel do original"),
        # a peça da conferência existe desde o LD02; a matriz passou a montá-la no LD07
        E("o endereço eletrônico de acesso", "CN-MA art. 839, § 1º",
          r"https?://|endereco eletronico|\bsitio\b|\bsite\b", "@endereco"),
        E("o horário da conferência", "CN-MA art. 839, § 1º", r"\bhora|horario",
          "@hora", "@data"),
    )),
    Tipo("NOTAS_CARTAO_FICHA", "Cartão de autógrafo (ficha de firma)", (
        E("a numeração crescente da ficha", "CN-MA art. 864, § 1º, I", r"ficha n", "@numero"),
        E("o nome, o endereço, a profissão, o estado civil e o nascimento",
          "CN-MA art. 864, § 1º, III", None, "@nome", "@endereco", "@profissao",
          "@estado_civil", "@nascimento"),
        E("o CPF e o documento de identidade", "CN-MA art. 864, § 1º, IV", r"cpf",
          "@documento", "@identidade"),
        E("o selo de abertura de firma", "CN-MA art. 864, caput", r"@@selo@@"),
        # consertados no LD07 (21/10/2026): «aberta em», a linha do título
        # eleitoral e cada forma de assinar três vezes
        E("a data de abertura", "CN-MA art. 864, § 1º, I", r"abertura|aberto em|aberta em",
          "@data_abertura"),
        E("o título eleitoral, se houver", "CN-MA art. 864, § 1º, III", r"eleitor",
          "@titulo_eleitor"),
        # consertado no LD02 (21/10/2026): a linha «Emissão da identidade»
        E("a data de emissão do documento de identidade", "CN-MA art. 864, § 1º, IV",
          r"emiss|expedi", "@rg_emissao"),
        E("a firma colocada ao menos três vezes", "CN-MA arts. 864, § 1º, V, e 867",
          r"tres vezes|3 vezes"),
        # consertado no LH13 (21/10/2026), pela resposta do oficial à pergunta
        # 9 — letra b: «Preenchimento conferido por: NOME — função», com a
        # linha da assinatura e do carimbo do preposto que abriu o cartão
        E("nome, assinatura e carimbo de quem conferiu o preenchimento", "CN-MA art. 864, § 1º, VI",
          r"conferid[oa] por: .*assinatura e carimbo", "@conferente_nome",
          "@conferente_funcao"),
    )),
    Tipo("NOTAS_PUBLICA_FORMA", "Pública forma", (
        E("o número", "CN-MA art. 130 (controle do ato)", r"publica forma n", "@numero"),
        E("o apresentante", "CN-MA art. 791, I", r"a pedido de", "@apresentante"),
        E("o documento original identificado", "CN-MA art. 836 (por analogia)",
          r"original de", "@documento_descricao", "@documento_expedidor"),
        E("a transcrição na íntegra", "CN-MA arts. 794 e 795", r"na integra", "@transcricao"),
        E("a ressalva, ou a declaração de que o original não tem rasura", "CN-MA art. 836",
          r"ressalva", "@ressalvas"),
        E("a conferência com o original", "CN-MA art. 836", r"conferida com o original"),
        # os três de baixo estão na moldura do papel (LD02), que a matriz passou
        # a montar no LD07 — `nt_publica_forma.papel_html`
        E("o local e a data", "CN-MA art. 798, I (por analogia)",
          r"cidade exemplo|\d{1,2} de [a-z]+ de \d{4}|\d{2}/\d{2}/\d{4}"),
        E("quem a expede, com o nome", "CN-MA art. 861, § 10 (por analogia)",
          r"tabeli|escrevente|oficial", "@emitida_por", "@emitida_por_funcao"),
        E("o selo e os emolumentos no corpo do papel", "CN-MA arts. 87, XVI, 130 e 131",
          r"\bselo\b|@@selo@@"),
    )),
    Tipo("NOTAS_TERMO_LIVRO", "Termo do livro (o ato como vai ao livro)", (
        E("a serventia (nome e CNS)", "CN-MA art. 180 (identificação da serventia)",
          None, "@sv.unit_name", "@sv.ri_cns"),
        E("o livro, a folha e o termo", "CN-MA arts. 792 e 851, § 1º", r"livro .* folha .* termo",
          "@a.livro", "@a.folha", "@a.termo"),
        E("o título do instrumento", "CN-MA art. 798, VIII", None, "@titulo_do_instrumento"),
        E("o teor do ato", "CN-MA art. 798", r"@@teor@@"),
        E("o selo (número, QR e emolumentos) no corpo do ato", "CN-MA arts. 87, XVI, 130 e 131",
          r"@@selo@@"),
        E("as linhas de assinatura das partes e de quem lavra", "CN-MA art. 798, XIII",
          r"@@assinaturas@@"),
    )),
    Tipo("NOTAS_TRASLADO", "Traslado", (
        E("a serventia (nome e CNS)", "CN-MA art. 180", None, "@sv.unit_name", "@sv.ri_cns"),
        E("os números do livro e das folhas", "CN-MA art. 850, § 2º", r"livro .* folha",
          "@a.livro", "@a.folha", "@a.folha_final", "@a.termo"),
        E("o inteiro teor do ato", "CN-MA art. 850 e § 2º", r"@@teor@@"),
        E("a menção «traslado»", "CN-MA art. 850, § 2º", r"\btraslado\b"),
        E("as assinaturas", "CN-MA art. 850, § 2º", r"@@assinaturas@@"),
        E("o selo no corpo do papel", "CN-MA arts. 130 e 131", r"@@selo@@"),
        E("as anotações à margem", "CN-MA art. 831; CC art. 217", r"anotacoes a margem",
          "@anotacoes.0.texto"),
        E("o local e a data", "CN-MA art. 850 (com a mesma data)", None, "@sv.cidade_uf",
          "@data_extenso"),
    )),
    Tipo("NOTAS_CERTIDAO_INTEIRO_TEOR", "Certidão de inteiro teor", (
        E("quem a requer", "CN-MA art. 851, § 3º", r"a pedido de", "@requerente"),
        E("a localização precisa: livro, folha e termo", "CN-MA art. 851, § 1º",
          r"revendo o livro", "@a.livro", "@a.folha", "@a.folha_final", "@a.termo"),
        E("a espécie do ato e a data em que foi lavrado", "CN-MA art. 851, § 1º",
          r"lavrado em", "@rotulo_tipo", "@data_do_ato"),
        E("o teor na íntegra", "CN-MA art. 851; CC art. 217", r"na integra", "@teor"),
        E("o selo do ato, com o que ele declara", "CN-MA arts. 87, XVI, 131 e 851",
          r"selo de fiscalizacao do ato", "@selos_do_ato.0"),
        E("as anotações à margem", "CN-MA arts. 831 e 851; CC art. 217",
          r"anotacoes a margem", "@anotacoes.0.texto"),
        E("a fé de quem certifica", "CN-MA art. 849", r"o referido e verdade e dou fe"),
    )),
    Tipo("NOTAS_CERTIDAO_POSITIVA", "Certidão positiva (por busca)", (
        E("quem a requer", "CN-MA art. 851, § 3º", r"a pedido de", "@requerente"),
        E("quem se buscou e o período", "CN-MA art. 851", r"feitas as buscas", "@nome",
          "@documento", "@periodo"),
        E("cada ato achado: espécie, natureza, livro, folha, data e qualidade",
          "CN-MA art. 851, § 1º", r"consta", "@achados.0.rotulo_tipo",
          "@achados.0.natureza", "@achados.0.livro", "@achados.0.folha",
          "@achados.0.data", "@achados.0.qualificacao"),
        # consertado no LD07 (21/10/2026): o modelo e a busca trazem o termo
        E("o número (termo) de cada ato achado", "CN-MA arts. 792 e 851, § 1º",
          r"termo n", "@achados.0.termo"),
        E("a fé de quem certifica", "CN-MA art. 849", r"o referido e verdade e dou fe"),
    )),
    Tipo("NOTAS_CERTIDAO_NEGATIVA", "Certidão negativa (por busca)", (
        E("quem a requer", "CN-MA art. 851, § 3º", r"a pedido de", "@requerente"),
        E("quem se buscou e o período", "CN-MA art. 851", r"feitas as buscas", "@nome",
          "@documento", "@periodo"),
        E("o resultado: nada consta", "CN-MA art. 851", r"nada consta"),
        E("a fé de quem certifica", "CN-MA art. 849", r"o referido e verdade e dou fe"),
    )),
    # LD02 (21/10/2026): a cópia RESUMIDA do art. 851, que a casa não emitia.
    Tipo("NOTAS_CERTIDAO_BREVE_RELATO", "Certidão em breve relato (do ato identificado)", (
        E("quem a requer", "CN-MA art. 851, § 3º", r"a pedido de", "@requerente"),
        E("a localização precisa: livro, folha e termo", "CN-MA art. 851, § 1º",
          r"revendo o livro", "@a.livro", "@a.folha", "@a.folha_final", "@a.termo"),
        E("a espécie e a natureza do ato, e a data em que foi lavrado",
          "CN-MA art. 851, § 1º", r"lavrado em", "@rotulo_tipo", "@a.natureza",
          "@data_do_ato"),
        E("a forma: breve relato", "CN-MA art. 851 («cópia integral ou resumida»)",
          r"breve relato"),
        E("as partes e a qualidade em que figuram no ato", "CN-MA art. 851, § 1º",
          r"figura como", "@partes.0.nome", "@partes.0.qualificacao", "@partes.1.nome",
          "@partes.1.qualificacao"),
        E("o selo do ato, com o que ele declara", "CN-MA arts. 87, XVI, 131 e 851",
          r"selo de fiscalizacao do ato", "@selos_do_ato.0"),
        E("as anotações à margem", "CN-MA arts. 831 e 851; CC art. 217",
          r"anotacoes a margem", "@anotacoes.0.texto"),
        E("a fé de quem certifica", "CN-MA art. 849", r"o referido e verdade e dou fe"),
    )),
)

POR_CHAVE = {t.chave: t for t in MATRIZ}
MINUTAS = tuple(m["codigo"] for m in NM.MINUTAS)


# =============================================================== a montagem


@dataclass
class Montado:
    texto: str              # o papel montado (HTML)
    contexto: dict          # o que se pôs nele
    campos: dict | None = None   # minuta: chave do campo → valor preenchido


def _valor_de_exemplo(campo: dict) -> str:
    if campo["chave"] in DATA_DO_ATO:
        return DATA_DO_ATO[campo["chave"]]
    return f"{campo['chave'].upper().replace('_', ' ').strip()} DE EXEMPLO"


def _partes_da_minuta(corpo: str) -> list[dict]:
    partes = [dict(OUTORGANTE, ordem=1)]
    if "outorgados" in corpo:
        partes.append(dict(OUTORGADO, ordem=2))
    if "testemunhas" in corpo:
        partes += [dict(t, ordem=3 + i) for i, t in enumerate(TESTEMUNHAS)]
    return partes


_MONTADAS: dict[str, Montado] = {}


def termo_da_minuta(codigo: str) -> Montado:
    """O teor da minuta, montado como `notas_ato_preencher` o monta.

    Todos os campos preenchidos, a 1ª opção de cada escolha e TODAS as
    cláusulas «SE» ligadas: elemento que só existe numa cláusula também se
    mede, e nada fica por preencher.
    """
    if codigo in _MONTADAS:
        return _MONTADAS[codigo]
    from jinja2.sandbox import SandboxedEnvironment
    corpo = NM.por_codigo(codigo)["corpo"]
    partes = _partes_da_minuta(corpo)
    preferidas = dict(POR_CHAVE[codigo].escolhas) if codigo in POR_CHAVE else {}
    corpo_jinja = SandboxedEnvironment(autoescape=False).from_string(corpo).render(
        sv=SERVENTIA, lavrado_nome=LAVRADO_NOME, lavrado_titulo=LAVRADO_TITULO,
        **NT.contexto_jinja_partes(partes))
    valores: dict[str, str] = {}
    for campo in campos_do_modelo({"corpo": corpo}):
        if campo["tipo"] == "condicao":
            valores[campo["chave"]] = "1"
        elif campo["tipo"] == "escolha":
            pedaco = preferidas.get(campo["chave"])
            valores[campo["chave"]] = next(
                (o for o in campo["opcoes"] if pedaco and pedaco in o),
                campo["opcoes"][0])
        else:
            valores[campo["chave"]] = _valor_de_exemplo(campo)
    # o campo do fecho, como a tela o completa (`notas_ato_preencher`)
    valores[NT.CHAVE_ASSINANTES] = NT.texto_dos_assinantes(partes)
    texto = preencher({"corpo": corpo_jinja}, valores)
    _MONTADAS[codigo] = Montado(texto, dict(CONTEXTO_DA_MINUTA), valores)
    return _MONTADAS[codigo]


A_DO_LIVRO = {"id": 1, "livro": "7", "folha": "12", "folha_final": "12v",
              "termo": 345, "selo": SELO_DO_ATO, "tipo": "ESCRITURA"}
ANOTACAO = {"tipo": "REVOGAÇÃO", "data": "21/10/2026",
            "texto": "Revogada por instrumento lavrado no Livro 8, folha 3, termo 12."}


def _papel(chave: str) -> Montado:
    """Cada papel do catálogo, montado pelo montador da casa, com tudo preenchido."""
    from jinja2.sandbox import SandboxedEnvironment
    textos = MOD.textos()
    if chave == "NOTAS_QUALIFICACAO_PF":
        # PELO MONTADOR, `notas_teor.qualificar` (LD07, 21/10/2026): os claros
        # novos do papel (identidade, união estável, cônjuge) são frases que o
        # montador escolhe pela parte, e só ele as põe. Uma parte casada e
        # completa, para cada elemento ter o que medir.
        return Montado(NT.qualificar(CASADO), dict(CASADO))
    if chave == "NOTAS_QUALIFICACAO_PJ":
        ctx = {"nome": "EMPRESA EXEMPLO LTDA", "documento": "00000010000127",
               "endereco": "Rua Exemplo, 500, Cidade Exemplo-MA"}
        return Montado(textos.preencher(chave, **ctx), ctx)
    if chave.startswith("NOTAS_RECONHECIMENTO_"):
        ctx = {"quem": OUTORGANTE["nome"]}
        return Montado(textos.preencher(chave, **ctx), ctx)
    if chave == "NOTAS_ETIQUETA_FECHO__local_e_data":
        ctx = {"local": "CIDADE EXEMPLO-MA", "dia": "20/10/2026"}
        return Montado(textos.preencher(chave, **ctx), ctx)
    if chave == "ETIQUETA":
        return Montado((RAIZ / "templates" / "notas_etiqueta.html").read_text(
            encoding="utf-8"), {})
    if chave == "NOTAS_TERMO_COMPARECIMENTO":
        # A ORDEM VAI COMO A ROTA A PASSA (LD07, 21/10/2026): o balcão numera
        # o termo por `NL.ordem_da_presenca` desde o LD02, e a matriz montava
        # o termo sem ela — media o montador avulso, e não o papel.
        ctx = {"nome": OUTORGANTE["nome"], "documento": "000.000.001-91",
               "selo": "RECFIR000000TESTE000000001", "data_extenso":
               "vinte dias do mês de outubro do ano de dois mil e vinte e seis",
               "ordem": 4321}
        texto = NL.texto_termo_comparecimento(
            sv=SERVENTIA, data_extenso=ctx["data_extenso"],
            reconhecimento={"selo": ctx["selo"], "oficial": LAVRADO_NOME,
                            "oficial_funcao": LAVRADO_TITULO,
                            "documento_descricao": "contrato de exemplo"},
            parte={"nome": ctx["nome"], "documento": ctx["documento"]},
            ordem=ctx["ordem"])
        return Montado(texto, ctx)
    if chave in ("NOTAS_AUTENTICACAO", "NOTAS_AUTENTICACAO_INTERNET"):
        # PELO MONTADOR DO BALCÃO, `notas_schema.texto_autenticacao` (LD07): é
        # ele que acrescenta à fórmula a conferência da internet (endereço,
        # data e hora, LD02) e a ressalva do original (LD07). A matriz lia só a
        # fórmula do catálogo, sem o que a rota grava junto.
        import notas_schema as NS
        tipo = "INTERNET" if chave.endswith("INTERNET") else "PADRAO"
        ctx = {"endereco": "https://servicos.exemplo.gov.br/certidao/000000",
               "data": "20/10/2026", "hora": "10:30",
               "ressalva": "a folha 2 do original tem rasura na data, que se ressalva"}
        return Montado(NS.texto_autenticacao(tipo, **ctx), ctx)
    if chave == "NOTAS_CARTAO_FICHA":
        ctx = {"numero": 4321, "nome": OUTORGANTE["nome"], "documento": "000.000.001-91",
               "identidade": "1234567 SSP MA", "rg_emissao": "03/02/2001",
               "nascimento": "04/03/1980", "data_abertura": "15/09/2026",
               "titulo_eleitor": "0000 0000 0000", "espaco_curto": "<p></p>",
               "nacionalidade": "brasileira", "naturalidade": "Cidade Exemplo-MA",
               "estado_civil": "solteiro", "profissao": "comerciante",
               "filiacao": "PAI EXEMPLO e MAE EXEMPLO", "endereco": "Rua Exemplo, 10",
               "bairro_cidade": "Centro / Cidade Exemplo — MA", "cep": "65000-000",
               "telefone": "(99) 90000-0000", "conjuge": "", "como_assina": "",
               "conferente_nome": "CARLA EXEMPLO", "conferente_funcao": "Escrevente Autorizada",
               "somente_autenticidade": False, "bloqueado": False,
               "motivo_bloqueio": "", "espaco": "<p></p>", "linha": "<p>____</p>",
               "cidade_uf": "Cidade Exemplo/MA",
               "data_extenso": "20 de outubro de 2026",
               "caixa_foto_digital_celulas": "<tr><td></td><td></td></tr>"}
        texto = SandboxedEnvironment(autoescape=False).from_string(
            MOD.padrao_de(chave)).render(**ctx)
        return Montado(texto, ctx)
    if chave == "NOTAS_PUBLICA_FORMA":
        ctx = {"numero": 17, "ano": 2026, "apresentante": OUTORGADO["nome"],
               "apresentante_documento": "000.000.002-72",
               "documento_especie": "Contrato particular",
               "documento_descricao": "contrato de locação de exemplo",
               "documento_expedidor": "EMPRESA EXEMPLO LTDA", "folhas": 2,
               "transcricao": "TEXTO TRANSCRITO DE EXEMPLO DO DOCUMENTO ORIGINAL.",
               "ressalvas": "a folha 2 tem rasura na data, que se ressalva"}
        # O PAPEL, E NÃO SÓ O TEOR (LD07, 21/10/2026): a pública forma sai em
        # `/notas/publica-forma/<id>/odt` com a moldura do LD02 — lugar e data,
        # quem expede e o carimbo do selo — em volta do teor congelado. A
        # matriz montava só o teor e acusava a falta do que estava no papel.
        pf = dict(ctx, teor=PF.montar_teor(**ctx), situacao="EMITIDA",
                  emitida_em="2026-10-20T10:30:00", emitida_por=LAVRADO_NOME,
                  emitida_por_funcao=LAVRADO_TITULO, hash_teor="0" * 64)
        return Montado(PF.papel_html(pf, sv=SERVENTIA), pf)
    if chave in ("NOTAS_TERMO_LIVRO", "NOTAS_TRASLADO"):
        ctx = {"a": dict(A_DO_LIVRO), "sv": SERVENTIA, "anotacoes": [ANOTACAO],
               "rotulo_tipo": "Escritura pública",
               "titulo_do_instrumento": "Escritura pública de compra e venda de exemplo",
               "data_extenso": "20 de outubro de 2026",
               "lavrado_nome": LAVRADO_NOME, "lavrado_titulo": LAVRADO_TITULO}
        texto = SandboxedEnvironment(autoescape=False).from_string(
            MOD.padrao_de(chave)).render(**ctx)
        return Montado(texto, ctx)
    if chave == "NOTAS_CERTIDAO_INTEIRO_TEOR":
        from markupsafe import Markup
        teor = termo_da_minuta("NT-ESC-COMPRA-VENDA").texto
        ctx = {"a": dict(A_DO_LIVRO), "teor": Markup(teor),
               "rotulo_tipo": "Escritura pública", "data_do_ato": "20/10/2026",
               "anotacoes": [ANOTACAO], "selos_do_ato": [TEXTO_DO_SELO_DO_ATO],
               "requerente": OUTORGADO["nome"], "requerente_documento": "000.000.002-72",
               "finalidade": "instruir pedido de exemplo"}
        return Montado(NCE.montar_teor(tipo="INTEIRO_TEOR", **ctx), ctx)
    if chave in ("NOTAS_CERTIDAO_POSITIVA", "NOTAS_CERTIDAO_NEGATIVA"):
        achados = ([{"rotulo_tipo": "Escritura pública", "natureza": "COMPRA E VENDA",
                     "livro": "7", "folha": "12", "termo": 345, "data": "2026-10-20",
                     "qualificacao": "OUTORGANTE"}]
                   if chave.endswith("POSITIVA") else [])
        ctx = {"requerente": OUTORGADO["nome"], "requerente_documento": "000.000.002-72",
               "nome": OUTORGANTE["nome"], "documento": "000.000.001-91",
               "periodo": NCE.frase_do_periodo("2016-01-01", "2026-10-20"),
               "achados": achados, "finalidade": None}
        tipo = "POSITIVA" if chave.endswith("POSITIVA") else "NEGATIVA"
        return Montado(NCE.montar_teor(tipo=tipo, **ctx), ctx)
    if chave == "NOTAS_CERTIDAO_BREVE_RELATO":
        ctx = {"a": dict(A_DO_LIVRO, natureza="COMPRA E VENDA"),
               "rotulo_tipo": "Escritura pública", "data_do_ato": "20/10/2026",
               "partes": [OUTORGANTE, OUTORGADO], "anotacoes": [ANOTACAO],
               "selos_do_ato": [TEXTO_DO_SELO_DO_ATO],
               "requerente": OUTORGADO["nome"], "requerente_documento": "000.000.002-72",
               "finalidade": "instruir pedido de exemplo"}
        return Montado(NCE.montar_teor(tipo="BREVE_RELATO", **ctx), ctx)
    raise KeyError(chave)


def montado(chave: str) -> Montado:
    return termo_da_minuta(chave) if chave.startswith("NT-") else _papel(chave)


def _do_contexto(ctx: dict, caminho: str):
    alvo = ctx
    for pedaco in caminho.split("."):
        alvo = alvo[int(pedaco)] if isinstance(alvo, (list, tuple)) else alvo[pedaco]
    return alvo


def faltas(chave: str, elemento: Elemento) -> list[str]:
    """O que falta do elemento no papel montado — vazio, o papel o tem."""
    m = montado(chave)
    plano = _plano(m.texto)
    achado = []
    if elemento.rotulo and not re.search(elemento.rotulo, plano):
        achado.append(f"o rótulo /{elemento.rotulo}/ não está no papel")
    for v in elemento.valores:
        if v.startswith("@"):
            valor = _do_contexto(m.contexto, v[1:])
        else:
            candidatos = []
            for alternativa in v.split("|"):
                chaves = [k for k in (m.campos or {}) if k.startswith(alternativa)]
                if not chaves:
                    achado.append(f"o modelo não tem o campo «{alternativa}…»")
                candidatos += [m.campos[k] for k in chaves[:1]]
            if candidatos and not any(_plano(x) in plano for x in candidatos):
                achado.append(f"o valor de «{v}» ({str(candidatos[0])[:40]!r}) não "
                              "chegou ao papel")
            continue
        if _plano(valor) not in plano:
            achado.append(f"o valor de «{v}» ({str(valor)[:40]!r}) não chegou ao papel")
    return achado


def _casos():
    for tipo in MATRIZ:
        for i, elemento in enumerate(tipo.elementos, start=1):
            marcas = ([pytest.mark.xfail(strict=True, raises=AssertionError,
                                         reason=elemento.defeito)]
                      if elemento.defeito else [])
            yield pytest.param(tipo.chave, i - 1, marks=marcas,
                               id=f"{tipo.chave}-{i:02d}")


# ================================================================== os testes


@pytest.mark.parametrize("chave,indice", list(_casos()))
def test_cada_elemento_que_a_norma_exige_esta_no_papel_com_rotulo_e_valor(chave, indice):
    """O elemento obrigatório aparece no papel montado: a frase que o nomeia e
    o valor que se preencheu — e, na minuta, o campo de onde o valor sai.

    O `id` é «chave-ordem»; o elemento, o artigo e o que faltou vão na
    mensagem, que é o que a casa lê para consertar o modelo.
    """
    elemento = POR_CHAVE[chave].elementos[indice]
    achado = faltas(chave, elemento)
    assert not achado, (f"{POR_CHAVE[chave].nome}: {elemento.o_que} "
                        f"({elemento.artigo}) — " + "; ".join(achado))


def test_a_ata_de_adjudicacao_nao_se_diz_mais_titulo_habil_para_o_registro():
    """O CNN art. 440-G, § 2º, e o CN-MA art. 848, § 2º, dizem o contrário um
    do outro: o nacional, que a ata «não tem valor de título de propriedade»;
    o estadual, que ela «servirá como título hábil para ingresso no Registro
    de Imóveis, independentemente de homologação judicial». O oficial
    respondeu «12 a» em 21/10/2026 (LH13): segue o CNN, que prevalece, e a
    frase do CN-MA SAI — as duas juntas eram a letra c, que ele não quis. A
    matriz de cima mede que a advertência entrou; este, que a outra saiu."""
    texto = _plano(termo_da_minuta("NT-ATA-ADJUDICACAO").texto)
    assert "nao tem valor de titulo de propriedade" in texto
    for saiu in ("titulo habil", "independentemente de homologacao judicial",
                 "848, § 2"):
        assert saiu not in texto, saiu


# A MARCAÇÃO QUE O PREENCHIMENTO NÃO RESOLVE — achada ao montar a matriz.
# `ri_modelos_atos.preencher` passa UMA vez pelas cláusulas e UMA pelas
# escolhas, e a expressão de cada uma não aceita outra dentro: a de fora fica
# crua no teor. E duas escolhas de mesmo rótulo respondem pelo mesmo campo.
#
# AS TRÊS QUE HAVIA FORAM CONSERTADAS NO LD02 (21/10/2026): o usufruto (a
# {DURAÇÃO} dentro da {ATO}, e uma segunda {ATO}), a partilha (duas {ATO}) e as
# diretivas (a «SE HOUVER SUBSTITUTO» dentro da «SE NOMEAR PROCURADOR DE
# SAÚDE»). Minuta nova com o mesmo defeito entra aqui, com o motivo.
MARCACAO_QUE_NAO_SE_RESOLVE: dict[str, str] = {}


@pytest.mark.parametrize("codigo", [
    pytest.param(c, marks=[pytest.mark.xfail(strict=True, raises=AssertionError,
                                             reason=MARCACAO_QUE_NAO_SE_RESOLVE[c])]
                 if c in MARCACAO_QUE_NAO_SE_RESOLVE else [])
    for c in MINUTAS])
def test_a_minuta_preenchida_por_inteiro_nao_deixa_claro_nem_marcador(codigo):
    """Com todos os campos preenchidos e as cláusulas ligadas, o termo sai sem
    `[CAMPO]`, `{ESCOLHA: …}`, `«SE …»`, `{{ }}`, «None» nem fileira de X: o
    claro que sobra é o espaço em branco que o art. 795, § 2º, do CN-MA
    proíbe."""
    texto = termo_da_minuta(codigo).texto
    assert pendencias(texto) == [], pendencias(texto)
    assert NT.claros_de_x(texto) == []
    sobra = re.search(r"\{[A-ZÀ-Ü][A-ZÀ-Ü ]+:|«SE ", texto)
    assert not sobra, (codigo, texto[sobra.start():sobra.start() + 80])
    for marca in ("{{", "}}", "{%", "None", "@@"):
        assert marca not in texto, (codigo, marca)


def test_as_ultimas_palavras_do_testador_ficam_no_auto_mesmo_sem_marcar_clausula():
    """O auto de aprovação começa «imediatamente depois da última palavra do
    testador» (CC art. 1.869): as palavras são o elemento, e não uma cláusula
    que o escrevente escolhe pôr.

    Até o LD02 (21/10/2026) a minuta as punha entre «», que a marcação lê como
    cláusula opcional; agora vão entre aspas curvas (“ ”), que ela não lê."""
    corpo = NM.por_codigo("NT-TESTAMENTO-CERRADO")["corpo"]
    valores = {c["chave"]: _valor_de_exemplo(c)
               for c in campos_do_modelo({"corpo": corpo})
               if c["tipo"] not in ("condicao", "escolha")}
    texto = preencher({"corpo": corpo}, valores)
    assert _plano(valores["ultimas_palavras_do_testador"]) in _plano(texto)


@pytest.mark.parametrize("codigo", MINUTAS)
def test_a_certidao_de_inteiro_teor_reproduz_o_termo_de_cada_tipo(codigo):
    """A certidão de inteiro teor de cada tipo de ato traz o termo inteiro, a
    localização (livro, folha, termo), a espécie, a data e o selo do ato —
    «TERMO E CERTIDÃO» batendo (CN-MA arts. 849 a 851; CC art. 217)."""
    from markupsafe import Markup
    m = NM.por_codigo(codigo)
    tipo = NF.tipo_ato_do_modelo(m["tipo"])
    termo = termo_da_minuta(codigo).texto
    certidao = NCE.montar_teor(
        tipo="INTEIRO_TEOR", a=dict(A_DO_LIVRO, tipo=tipo),
        teor=Markup(NCE._sem_marcas(termo)), rotulo_tipo=NCE._rotulo_tipo(tipo),
        data_do_ato="20/10/2026", anotacoes=[], selos_do_ato=[TEXTO_DO_SELO_DO_ATO],
        requerente=OUTORGADO["nome"], requerente_documento="000.000.002-72")
    plano = _plano(certidao)
    assert _plano(termo) in plano, "a certidão não reproduz o termo na íntegra"
    for pedaco in ("livro 7", "folha 12 a 12v", "termo n. 345", "lavrado em 20/10/2026",
                   _plano(NCE._rotulo_tipo(tipo)), _plano(TEXTO_DO_SELO_DO_ATO),
                   "nada mais consta a margem", "o referido e verdade e dou fe"):
        assert pedaco in plano, (codigo, pedaco)


def test_ha_certidao_em_breve_relato_do_ato_das_notas():
    """O breve relato traz os elementos do termo, resumidos e iguais aos dele.
    Sem modelo e sem tipo, a casa não o emite — e até o LD02 (21/10/2026) não
    emitia: o CN-MA art. 851 define certidão como cópia integral OU RESUMIDA."""
    assert "BREVE_RELATO" in NCE.TIPOS
    assert any(c["chave"].startswith("NOTAS_CERTIDAO_BREVE") for c in MOD.CATALOGO)


def test_a_matriz_cobre_toda_minuta_e_todo_papel_das_notas_que_vai_ao_cliente():
    """Minuta nova ou papel novo sem linha na matriz passaria sem conferência
    de requisito nenhum — este teste avisa no mesmo dia."""
    assert set(MINUTAS) <= set(POR_CHAVE), set(MINUTAS) - set(POR_CHAVE)
    papeis = {"NOTAS_QUALIFICACAO_PF", "NOTAS_QUALIFICACAO_PJ",
              "NOTAS_RECONHECIMENTO_SEMELHANCA", "NOTAS_RECONHECIMENTO_AUTENTICIDADE",
              "NOTAS_RECONHECIMENTO_SINAL", "NOTAS_TERMO_COMPARECIMENTO",
              "NOTAS_AUTENTICACAO", "NOTAS_AUTENTICACAO_INTERNET", "NOTAS_CARTAO_FICHA",
              "NOTAS_PUBLICA_FORMA", "NOTAS_TERMO_LIVRO", "NOTAS_TRASLADO",
              "NOTAS_CERTIDAO_INTEIRO_TEOR", "NOTAS_CERTIDAO_POSITIVA",
              "NOTAS_CERTIDAO_NEGATIVA", "NOTAS_CERTIDAO_BREVE_RELATO"}
    assert papeis <= set(MOD.POR_CHAVE), papeis - set(MOD.POR_CHAVE)
    assert papeis <= set(POR_CHAVE), papeis - set(POR_CHAVE)
    for tipo in MATRIZ:
        assert tipo.elementos, tipo.chave
        for e in tipo.elementos:
            assert e.rotulo or e.valores, (tipo.chave, e.o_que)
            assert e.artigo, (tipo.chave, e.o_que)


def test_o_documento_da_matriz_descreve_cada_tipo_desta_matriz():
    """`docs/REQUISITOS_LEGAIS.md` e esta matriz dizem a mesma coisa: cada
    tipo daqui tem a sua linha lá, pelo mesmo nome."""
    doc = (RAIZ / "docs" / "REQUISITOS_LEGAIS.md").read_text(encoding="utf-8")
    secao = doc.split("## Tabelionato de Notas (LT02)", 1)
    assert len(secao) == 2, "falta a seção das Notas em docs/REQUISITOS_LEGAIS.md"
    for tipo in MATRIZ:
        assert tipo.nome in secao[1], tipo.nome
