"""O extrator de endereço do teor — o que ele lê, e o que ele **recusa** ler.

**ESTES TESTES NÃO TOCAM NO BANCO.** Todo teor de entrada é **texto real de
ficha desta casa**, copiado da produção em 15/09/2026 — os blocos estão
inteiros, e os valores esperados foram medidos, um a um, contra o banco.

Três famílias de defeito moram aqui, e cada uma custou caro uma vez:

1. **a âncora** — o nome do imóvel sai do **bloco do imóvel**, e não do teor
   inteiro. As fichas 971 e 979 provam por quê: no teor inteiro o nome lido é
   «Sitio», que é o **endereço dos proprietários** («residentes e domiciliados
   na fazenda denominada Sitio»); no bloco do imóvel, o nome é «Riacho do
   Meio», que é o **da propriedade**. Medido nas 1.184 fichas que têm bloco e
   nome, em 15/09/2026: **1.144 dão o mesmo nome** pelos dois caminhos e **40
   dão outro** — e é essa diferença que a âncora decide. E o pior dela: na 971
   o nome errado sai com confiança **alta** e arrasta o CPF do proprietário
   para o `de_onde`, enquanto o certo sai com confiança média. Quem olhasse só
   a confiança escolheria a errada.
2. **o tipo do logradouro** — o ONR exige o tipo, e o contrato tem 130; «Av.»
   não é um deles. O extrator canoniza antes de gravar, e o teste exige o par
   inteiro (o nosso texto → o que a régua do **envio** reconhece).
3. **o tipo sozinho** — «Estrada», «Área», «Rua» não são nome de imóvel, e o
   campo volta para a fila de conferência em vez de ir ao índice.
"""
from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import onr_api as API
import onr_endereco_do_teor as E
import ri_onr_central as C

import pytest

# A SERVENTIA DESTES TESTES, num lugar só — desde 09/10/2026 o módulo não traz
#   mais cidade, UF nem CEPs embutidos (sanitização para o código aberto): eles
#   vêm de `settings`. Os valores ainda são os desta casa porque os teores
#   abaixo são trechos reais de fichas; a troca por fictícios é a etapa B3.
SERVENTIA_DE_TESTE = {"ri_cidade": "Cidade Exemplo", "ri_uf": "MA",
                      "serventia_cep": "65.936-000",
                      "onr_ceps_por_cidade": "Ribamar Fiquene=65938000"}


@pytest.fixture(autouse=True)
def _serventia_de_teste(monkeypatch):
    original = E.padrao_da_casa
    monkeypatch.setattr(E, "padrao_da_casa", lambda settings=None: original(
        {**SERVENTIA_DE_TESTE, **(settings or {})}))


# ─────────────────────────────────────────────────────── os blocos reais
#
# **A FICHA 971 É O PAR QUE DECIDE A ÂNCORA**: o bloco do imóvel diz «Riacho do
# Meio», e o teor inteiro traz, mais abaixo, «residentes e domiciliados na
# fazenda denominada Sitio» — o endereço de quem vende. Os dois textos abaixo
# saíram do banco de produção em 15/09/2026.
# O cabeçalho é o de verdade, e não enfeite: `bloco_do_imovel` procura a marca
# «IMÓVEL:-»; sem ela o texto volta **inteiro**, que é justamente o caso que
# este bloco de teste mede. Os `\r\n` são os da ficha.
CABECALHO_971 = (
    " Falta conferir\n\r\n MATRÍCULA: 971\n\r\n LIVRO 2-E FLS. 121\n\r\n"
    " DATADO 23 DE JULHO DE 1984\n\r\n \n\r\n IMÓVEL:- "
)
BLOCO_971 = (
    "- Uma parte do quinhão de terras de lavrar e criar em campo aberto e em "
    "comum com outros condôminos, sito na data ou fazenda “Riacho do Meio” "
    "deste município com área aproximada correspondente a 35,00 há, havida por "
    "herança no inventario dos bens deixado por falecimento de Durcelma "
    "Azevedo de Miranda, cadastrada no INCRA sob código nº110043000950-7. "
)
# O parágrafo da pessoa, que **não** pode virar nome do imóvel — e que, lido no
# teor inteiro, **vence**: «denominada Sitio», com confiança ALTA, e o CPF
# dentro do `de_onde`. É o defeito, medido.
PARAGRAFO_971 = (
    "Proprietário: Marta Pereira de Miranda pelo casamento e seu marido "
    "Bento Esteves da Tavares, brasileiros, casados, lavrador e do lar, "
    "residentes e domiciliados na fazenda denominada Sitio deste município, "
    "portadores do CPF nº055.378.813-68, ele da carteira profissional nº081662 "
    "série 637-MA. Título Aquisitivo: Transcrita no CRI de Imperatriz no Lº "
    "nº 3-D, fls 95, sob nº 4.649, em 12.05.66."
)
TEOR_971 = CABECALHO_971 + BLOCO_971 + PARAGRAFO_971

# A 979 é a irmã da 971 — lavrada no mesmo livro, dois dias depois, com os
# mesmos proprietários. As duas fichas dizem o mesmo, e as duas provam o mesmo.
CABECALHO_979 = (
    " MATRÍCULA: 979\n\r\n LIVRO 2-E FLS. 129\n\r\n DATADO 31 DE JULHO DE 1984"
    "\n\r\n \n\r\n IMÓVEL:- "
)
BLOCO_979 = (
    "- Uma parte do quinhão de terras de lavrar e criar em campo aberto e em "
    "comum com outros condôminos, sita na fazenda “Riacho do Meio” deste "
    "município, com área aproximada de 35,00 hectares cadastrada no INCRA sob "
    "código nº 110043002950-7, havida por herança no inventario dos bens "
    "deixados por falecimento de Durcelia de Azevedo Miranda. "
)
PARAGRAFO_979 = (
    "Proprietários: Marta Pereira de Miranda pelo casamento Odilia Miranda da "
    "Paixão e seu marido Bento Esteves da Tavares, brasileiros, casados, lavrador "
    "e do lar, residentes e domiciliados na fazenda denominada “Sitio” deste "
    "município, portadores do CPF nº000.000.041-89, ele da carteira "
    "Profissional nº 08/662, Série 637-MA"
)
TEOR_979 = CABECALHO_979 + BLOCO_979 + PARAGRAFO_979

CABECALHO_957 = (
    " conferida\n\r\n MATRÍCULA 957\n\r\n LIVRO 2-E FLS. 105/V°\n\r\n"
    " DATADA DE 18/06/1984\n\r\n \n\r\n IMÓVEL:- "
)
BLOCO_957 = (
    "- Uma parte da metade de uma posse de terras, com área aproximada de "
    "45,00ha (quarenta e cinco hectares), sito na Fazenda “Folha Larga” deste "
    "Município de Cidade Exemplo, próprio para lavoura e criação de gados sem "
    "benfeitorias consideráveis, cadrastada no INCRA sob código nº110 043 000 "
    "26/00. "
)
# Aqui a armadilha é o parágrafo do **proprietário falecido**, que vem colado no
# fim da descrição: «faleceu no lugar Folha Larga deste Município (...) onde
# residia». Mesmo nome, e ainda assim o bloco tem de parar antes dele — a ficha
# 971 mostra o que acontece quando não para.
PARAGRAFO_957 = (
    "PROPRIETARIO:- LUIZ RODRIGUES DE MIRANDA , brasileiro maior, solteiro, "
    "lavrador, filho de Pedro Rodrigues Machado e de Umbelina Pereira Miranda, "
    "faleceu no lugar Folha Larga deste Município de Cidade Exemplo, onde residia, "
    "em 11/06/1955. TÍTULO AQUISITIVO:- Transcrito no Registro de Imóveis de "
    "Imperatriz, o Lº 3-I fls.111 sob nº 9.419, em 18/06/74."
)
TEOR_957 = CABECALHO_957 + BLOCO_957 + PARAGRAFO_957

# A ficha 530: o lugar sai do logradouro e **já está no bairro**.
BLOCO_530 = (
    "- Uma casa e seu respectivo terreno situado no povoado Lageado Novo, deste "
    "Município, medindo de frente 13,40 metros; laterais 50,00 metros fundos "
    "13,40 metros; bem assim os seguintes limites: lateral direita com terreno "
    "ocupado por Carlindo de Tal, lateral esquerda com terreno ocupado pelo seu "
    "Sr. José Ferreira, fundos com terreno da Municipalidade e frente para "
    "“Avenida Principal” do povoado Lageado Novo. Proprietária: Isaias de Sousa "
    "Franco, brasileira, casada, professora, residente e domiciliada em "
    "Lageado Novo deste Município, inscrita no C.P.F. sob nº 000.000.023-05. "
)

# A ficha 589: o nome do imóvel **é** um tipo do catálogo — e continua sendo o
# nome dele.
TEOR_589 = (
    "- Uma gleba de terras com área de 242,43,00ha (duzentos e quarenta e dois "
    "hectares e quarenta e três ares), denominada “Retiro” situada na Data ou "
    "Fazenda Campo Grande deste Município, em conjunto com Denis dos Santos "
    "Mota, com 42,10,00ha."
)

# A ficha 1117: o teor diz URBANO e a coluna diz RURAL. E o teor diz «hectare».
BLOCO_1117 = (
    " MATRÍCULA: 1117 LIVRO 2-F FLS. 110 DATADO 01 DE ABRIL DE 1985 "
    "Um terreno situado na zona urbanizável (suburbana) desta cidade, com área "
    "de 9,92,03 hectares, com as seguintes dimensões e limites: Começa como o "
    "ponto departida do marco zero com 12º30’NE, e 77 metros, marco um com "
    "89º’00’NE e 300 metros. E limita o marco treze com o terreno pertencente ao "
    "patrimônio municipal. Proprietário: JAIRO PEREIRA GOMES, residente e "
    "domiciliado nesta cidade."
)

# Os campos das colunas, como estão na produção — o fixture tem de os trazer,
# senão o teste mede uma ficha que não existe.
COLUNAS_971 = {"id": 4262, "numero": "971", "teor": TEOR_971, "rural_urbano": "R",
               "area_valor": "35", "area_unidade": "m2",
               "bairro": "Zona Rural", "cep": "65936000",
               "tipo_imovel": "Fazenda/Sítio/Chácara"}
COLUNAS_979 = {"id": 4270, "numero": "979", "teor": TEOR_979, "rural_urbano": "R",
               "area_valor": "35", "area_unidade": "ha",
               "bairro": "Zona Rural", "cep": "65936000",
               "tipo_imovel": "Fazenda/Sítio/Chácara"}
COLUNAS_957 = {"id": 4247, "numero": "957", "teor": TEOR_957, "rural_urbano": "R",
               "area_valor": "45", "area_unidade": "ha",
               "bairro": "Zona Rural", "cep": "65936000",
               "tipo_imovel": "Fazenda/Sítio/Chácara"}
COLUNAS_530 = {"id": 3972, "numero": "530", "teor": BLOCO_530, "rural_urbano": "U",
               "area_valor": "13", "area_unidade": "m2",
               "bairro": "LAGEADO NOVO", "cep": "65936000",
               "tipo_imovel": "Terreno/fração"}
COLUNAS_1117 = {"id": 3477, "numero": "1117", "teor": BLOCO_1117,
                "rural_urbano": "R", "area_valor": "9", "area_unidade": "ha",
                "bairro": None, "cep": None,
                "tipo_imovel": "Fazenda/Sítio/Chácara"}
COLUNAS_589 = {"id": 3682, "numero": "589", "teor": TEOR_589,
               "rural_urbano": "R", "area_valor": "242", "area_unidade": "ha",
               "bairro": "Zona Rural", "cep": "65936000",
               "tipo_imovel": "Fazenda/Sítio/Chácara"}
COLUNAS_URBANA = {"id": 1, "numero": "1", "rural_urbano": None,
                  "teor": ("um terreno urbano, situado nesta cidade, na Rua São "
                           "Francisco, nº 10, Quadra 12, Lote 231.")}


# ═══════════════════════════════════════════════════════ 1. a âncora


def test_o_nome_do_imovel_sai_do_bloco_e_nao_do_endereco_de_quem_vende():
    """**É o defeito que a ficha 971 prova, e ele não aparece em tela nenhuma.**

    O teor inteiro traz «residentes e domiciliados na fazenda denominada Sitio»
    — o endereço dos proprietários. O bloco do imóvel traz «sito na data ou
    fazenda “Riacho do Meio”» — o nome da propriedade. Ler o teor inteiro
    publicaria **o endereço de quem vende** como nome do imóvel no índice
    nacional, que é a lista que o país consulta para saber de quem é o imóvel.
    """
    bloco = E.bloco_do_imovel(TEOR_971)
    assert bloco["achou"] is True
    assert "Riacho do Meio" in bloco["texto"]
    assert "Sitio" not in bloco["texto"], (
        "o parágrafo do proprietário não entra no bloco do imóvel")

    certo = E.nome_do_imovel(bloco["texto"])
    assert certo["nome"] == "Riacho do Meio"
    assert certo["de_onde"] == 'fazenda "Riacho do Meio"'

    # o que o teor inteiro diria — e por que ele não é quem decide:
    errado = E.nome_do_imovel(TEOR_971)
    assert errado["nome"] == "Sitio"
    assert errado["confianca"] == "alta"
    assert "CPF" in errado["de_onde"], (
        "a leitura do teor inteiro arrasta o CPF do proprietário para o nome")

    p = E.propor(dict(COLUNAS_971))
    assert p["campos"]["logradouro"] == "Área Riacho do Meio"
    assert p["nome"]["de_onde"] == 'fazenda "Riacho do Meio"'


def test_a_irma_979_le_o_mesmo_imovel_e_comete_o_mesmo_erro():
    """A 979 é a irmã da 971: mesma fazenda, mesmos proprietários, mesma
    armadilha — e o par de fichas mostra que não é caso isolado, é a forma da
    ficha desta casa."""
    assert E.bloco_do_imovel(TEOR_979)["achou"] is True
    assert E.nome_do_imovel(E.bloco_do_imovel(TEOR_979)["texto"])["nome"] == "Riacho do Meio"
    assert E.nome_do_imovel(TEOR_979)["nome"] == "Sitio"
    assert E.propor(dict(COLUNAS_979))["campos"]["logradouro"] == "Área Riacho do Meio"


def test_a_ancora_vale_para_o_proprietario_falecido_da_957():
    """A ficha 957, e a mesma armadilha por outro caminho.

    «PROPRIETARIO:- LUIZ (...) faleceu no lugar Folha Larga deste Município
    (...) onde residia» vem colado no fim da descrição. É a **pessoa**, e o
    bloco do imóvel tem de parar antes dele — o mesmo corte que, na 971,
    separa «Riacho do Meio» de «Sitio».
    """
    bloco = E.bloco_do_imovel(TEOR_957)
    assert bloco["achou"] is True
    assert "Folha Larga" in bloco["texto"]
    assert "onde residia" not in bloco["texto"]
    assert "LUIZ RODRIGUES" not in bloco["texto"]
    assert E.nome_do_imovel(bloco["texto"])["nome"] == "Folha Larga"
    assert E.propor(dict(COLUNAS_957))["campos"]["logradouro"] == "Área Folha Larga"


# ══════════════════════════════════════════════ 2. o tipo do logradouro


def test_o_nome_que_ja_comeca_por_tipo_nao_ganha_outro():
    """«Fazenda São Francisco» já tem o tipo; não se põe «Área» na frente."""
    d = E.logradouro_do_nome("Fazenda São Francisco")
    assert d["acrescentou"] is False
    assert d["texto"] == "Fazenda São Francisco"
    assert d["tipo_codigo"] == 37
    assert d["logradouro"] == "São Francisco"


def test_o_nome_sem_tipo_recebe_area_a_frente():
    """Sem tipo no nome, o mais neutro é «Área» — código 472 do contrato."""
    d = E.logradouro_do_nome("São Francisco")
    assert d["acrescentou"] is True
    assert d["texto"] == "Área São Francisco"
    assert d["tipo_codigo"] == 472
    assert d["logradouro"] == "São Francisco"


def test_o_nome_que_coincide_com_um_tipo_do_catalogo_NAO_se_perde():
    """**A correção óbvia foi medida e recusada — e este teste guarda a recusa.**

    Quando o nome do imóvel é «Retiro», «Sítio», «Chácara» ou «Recanto», ele
    **coincide com um tipo do catálogo**, e a tentação é não pôr o «Área» à
    frente para não escrever «Área Retiro». Medido contra a produção em
    15/09/2026: isso **não ganha nada e perde as sete** — sem o prefixo o texto
    fica só com o tipo, o `so_o_tipo` o recusa, e o nome sai da ficha e volta
    para a fila de conferência.

    As sete são nomes **de propriedade**, confirmados na âncora: «denominada
    “Retiro”» (589), «denominada “Recanto”» (1260), «denominada “Sítio”» (1420),
    «em Data ou Fazenda “Sítio”» (997).

    **E o «Área Área» que motivou a tentativa não existe na produção**: exigiria
    que o nome do imóvel fosse literalmente «Área», e nenhuma das 1.982 fichas
    tem isso.
    """
    for nome in ("Retiro", "Sítio", "Chácara", "Recanto", "Fazenda"):
        d = E.logradouro_do_nome(nome)
        assert d["texto"] == f"Área {nome}", f"{nome} saiu sem o tipo à frente"
        # o que a correção candidata faria, e por que ela é pior:
        assert E.so_o_tipo(nome) is True, (
            "é justamente o prefixo «Área» que salva este nome do descarte")


def test_o_tipo_que_vai_na_proposta_e_reconhecido_pela_regua_do_ENVIO():
    """**A régua tem de ser a mesma que envia — e por isso ela é chamada aqui.**

    `logradouro_do_nome` decide o texto; quem manda o código do tipo ao ONR é
    `ri_onr_central.partir_logradouro`. Se os dois discordarem, a proposta passa
    no extrator e chega ao índice **sem o tipo**, que o contrato exige — foi o
    que aconteceu com «Av.», que não está entre os 130 do catálogo.

    A varredura roda os **130** tipos: nenhum pode ficar sem código.
    """
    problemas = []
    for chave, codigo in sorted(API.CODIGO_DO_LOGRADOURO.items()):
        d = E.logradouro_do_nome(f"{chave.title()} Nome Próprio")
        if d["acrescentou"] or d["tipo_codigo"] != codigo:
            problemas.append((chave, "o extrator não viu o tipo", d["texto"]))
        if C.partir_logradouro(d["texto"])["tipo_codigo"] is None:
            problemas.append((chave, "o envio não achou o tipo", d["texto"]))
    assert not problemas, problemas[:6]


def test_o_tipo_sozinho_nao_vai_ao_indice():
    """«Estrada» sozinho é linha que não diz nada e ocupa o lugar do nome."""
    for so_tipo in ("Estrada", "Área", "Rua", "Beco", "Avenida"):
        assert E.so_o_tipo(so_tipo) is True, so_tipo
    for tem_nome in ("Estrada de Ferro", "Fazenda São José", "Área Retiro"):
        assert E.so_o_tipo(tem_nome) is False, tem_nome


def test_o_logradouro_que_e_so_tipo_volta_para_a_fila_de_conferencia():
    """E o aviso diz o que fazer, em vez de gravar o vazio calado.

    «Área Retiro» **não** é só tipo, e por isso passa — é o par que separa a
    régua de um `startswith` no tipo.
    """
    campos = {"logradouro": "Estrada"}
    avisos: list[str] = []
    assert E.tira_o_logradouro_que_nao_e_nome(campos, {}, avisos) is True
    assert "logradouro" not in campos
    assert "não diz o nome" in avisos[0]
    assert "índice nacional" in avisos[0]

    fica = {"logradouro": "Área Retiro"}
    assert E.tira_o_logradouro_que_nao_e_nome(fica, {}, []) is False
    assert fica["logradouro"] == "Área Retiro"


# ═══════════════════════════════════════════════════════════ 3. a via


def test_a_via_aceita_a_abreviacao_do_tipo_e_canoniza_antes_de_gravar():
    """**«Av.» não está no catálogo do ONR — «Avenida» está, e é o código 8.**

    Sem a canonização, a via era lida e o código do tipo ia vazio. Medido nas
    1.551 fichas em 15/09/2026: **11 ganham** e nenhuma perde.
    """
    v = E.via_do_texto("situado a Av. Central, no Povoado Lageado II")
    assert v["logradouro"] == "Avenida Central"
    assert v["de_onde"] == "Av. Central"
    assert C.partir_logradouro(v["logradouro"])["tipo_codigo"] == 8

    # a prova de que a canonização é necessária, e não enfeite:
    assert C.partir_logradouro("Av. Central")["tipo_codigo"] is None
    # o token chega da regex **com o ponto** — «Av.», que é como a ficha escreve;
    # «AV» sem o ponto não é capturado por `via_do_texto`, e por isso não é
    # promessa desta função (a lista de apelidos é medida do que a ficha escreve).
    assert E._tipo_da_via("Av.") == "Avenida"


def test_o_ponto_da_abreviacao_no_meio_nao_e_o_fim_do_nome_da_rua():
    """«Rua Dep. La Rocque» — o ponto era da abreviação, e não da rua.

    O corte no ponto devolvia «Rua Dep», que é o nome de **outra rua**, e ia ao
    índice nacional assim.
    """
    v = E.via_do_texto("Rua Dep. La Rocque, nº 100")
    assert v["logradouro"] == "Rua Dep. La Rocque"


def test_a_prosa_com_medida_de_fronteira_nao_e_via():
    """«Estrada com uma linha de 67ºSE e 110 metros» é a divisa, não a rua."""
    assert E.via_do_texto("Estrada com uma linha de 67ºSE e 110 metros") is None
    assert E.via_do_texto("lote 1 da quadra 2") is None


# ═════════════════════════════════════════ 4. quadra, lote e número


def test_quadra_e_lote_vem_antes_da_via_e_o_lote_e_o_numero():
    """O urbano desta casa se identifica por quadra e lote, não por número.

    Medido no fixture: o logradouro é «Quadra 12» e o «Lote 231» vai como número
    predial — que é a leitura da casa para este tipo de ficha.
    """
    assert E.quadra_e_lote(COLUNAS_URBANA["teor"]) == {
        "quadra": "12", "lote": "231",
        "de_onde_quadra": "Quadra 12", "de_onde_lote": "Lote 231"}

    p = E.propor(dict(COLUNAS_URBANA))
    assert p["campos"]["logradouro"] == "Quadra 12"
    assert p["campos"]["numero_predial"] == "231"
    assert p["de_onde"]["numero_predial"] == "Lote 231"


def test_o_numero_da_porta_nao_pega_cpf_nem_data():
    """«nº 054» de CPF e «nº 5 de junho de 2020» não são número de porta.

    O número predial é o campo com que a Receita e o índice localizam o imóvel;
    um CPF ali é o documento de uma pessoa no lugar do endereço.
    """
    assert E.numero_predial_do_texto("Rua X, nº 9, nesta cidade")["numero"] == "9"
    assert E.numero_predial_do_texto(
        "Um Terreno sito a Rua Quintiliano Jose Tavares, n º 64, nesta cidade"
    )["numero"] == "64"
    assert E.numero_predial_do_texto(
        "Fulano, CPF sob nº 054, residente em Imperatriz") is None
    assert E.numero_predial_do_texto("Rua X, nº 5 de junho de 2020") is None


def test_a_ficha_sem_numero_grava_zero_por_convencao_da_casa():
    """`0` é o que esta casa já grava: o campo é `NOT NULL` no ONR, e «0» quer
    dizer «a ficha não tem número» — 1.237 registros da produção o usam assim.
    O `de_onde` diz isso a quem confere."""
    p = E.propor(dict(COLUNAS_957))
    assert p["campos"]["numero_predial"] == "0"
    assert "0" in p["de_onde"]["numero_predial"]


# ══════════════════════════════════ 5. o lugar, o bairro e a área


def test_o_lugar_cortado_do_logradouro_ja_esta_no_bairro():
    """**O corte tira a prosa, e não a informação** — e isso se mediu.

    «“Avenida Principal” do povoado Lageado Novo»: o logradouro é «Avenida
    Principal», e «LAGEADO NOVO» sai do próprio teor como bairro. O nome do
    lugar não some; ele muda de campo.
    """
    p = E.propor(dict(COLUNAS_530))
    assert p["campos"]["logradouro"] == "Avenida Principal"
    assert p["campos"]["bairro"] == "LAGEADO NOVO"
    assert "Lageado Novo" not in p["campos"]["logradouro"]
    assert E.bairro_do_texto(BLOCO_530)["de_onde"] == "teor: «POVOADO Lageado Novo»"


# ────────────────────────────────── o que a ficha velha escreve do bairro
#
# **AS TRÊS FORMAS SÃO REAIS, tiradas do acervo em 16/09/2026**, e cada uma
# derrubava a régua de um jeito diferente. Foram medidas sobre as 1.443 antes de
# entrar: **+8 e −1**, e o que se perde é um falso positivo.

def test_o_nome_do_lugar_entre_aspas_nao_derruba_a_regua():
    """`no povoado “Sumaúma”` — a aspa antes do nome.

    A régua exige a letra maiúscula logo depois da palavra do lugar, e a aspa
    não é letra: **mat 1615 e 1617** ficavam sem bairro por causa de dois
    caracteres. O que sai é o nome, sem a aspa de fecho.
    """
    assert E.bairro_do_texto("situado no povoado “Sumaúma”, deste Município")["bairro"] \
        == "SUMAÚMA"
    assert E.bairro_do_texto("no povoado 'Pombal', zona rural")["bairro"] == "POMBAL"


def test_o_loteamento_nomeia_lugar_nesta_casa():
    """**A régua dizia que «LOTEAMENTO» não existia no acervo, e existia.**

    Ele dera zero leituras nas 943 fichas da conferência — e aparece duas vezes
    nas 1.443 que o índice vai receber (mat 1779 e 1791). O zero era medido e a
    conclusão era falsa: **ausência na amostra não prova ausência no acervo**.
    """
    b = E.bairro_do_texto('na Quadra F da Rua 02, no loteamento "Eunice Coelho"')
    assert b["bairro"] == "EUNICE COELHO"
    assert b["de_onde"] == "teor: «LOTEAMENTO Eunice Coelho»"


def test_o_centro_do_endereco_e_bairro():
    """`, Centro` — o acervo escreve assim, e a régua só via `no Centro`.

    «Rua do Campo nº198, Centro» é endereço de terreno em Ribamar Fiquene, e a
    preposição simplesmente não está lá. **Três fichas** saíram por isso (mat
    2626, 2627 e 2754).
    """
    assert E.bairro_do_texto("Rua do Campo nº198, Centro, na área urbana")["bairro"] \
        == "CENTRO"
    assert E.bairro_do_texto(
        "Travessa Central, s/nº, Centro; adquirido por compra")["bairro"] == "CENTRO"


def test_o_centro_de_uma_medida_de_distancia_nao_e_bairro():
    """**O falso positivo que a medição achou, e o mais perigoso dos três.**

    A mat 1931 diz «500 metros aproximadamente **do centro da cidade**» — e a
    régua lia `CENTRO`, porque a preposição estava lá e o que vinha depois não
    estava sendo olhado. **Bairro errado no índice não se desconfia**, porque
    `CENTRO` é bairro de verdade em muita cidade. A guarda é a palavra seguinte.
    """
    assert E.bairro_do_texto(
        "situado ao norte nesta cidade, com 500 metros aproximadamente "
        "do centro da cidade") is None
    assert E.bairro_do_texto("com frente para a rua, no centro do terreno") is None
    assert E.bairro_do_texto("distante 2 km do centro da sede") is None


def test_a_procedencia_do_centro_e_o_que_a_ficha_escreveu():
    """**O `de_onde` citava «no Centro» mesmo quando o texto dizia `, Centro`.**

    Quem confere a proposta procura o trecho citado na ficha — e ele tem de
    estar lá. Procedência que não se acha no teor é carimbo que mente.
    """
    b = E.bairro_do_texto("Travessa Central, s/nº, Centro, nesta cidade")
    assert b["de_onde"] == "teor: «, Centro»"
    assert E.bairro_do_texto("no Centro")["de_onde"] == "teor: «no Centro»"


def test_a_area_em_hectares_vai_em_metros_quadrados_ao_indice():
    """**O defeito de 10.000× — e o valor vem do que a ficha escreve.**

    45 ha = 450.000 m²; 242,43,00 ha = 2.424.300 m². O campo do ONR é em m², e
    mandar o número da coluna mandaria «45» — quarenta e cinco metros quadrados.
    """
    assert E.propor(dict(COLUNAS_957))["campos"]["area_valor"] == "450000"
    p = E.propor(dict(COLUNAS_589))
    assert p["campos"]["area_valor"] == "2424300"
    assert p["campos"]["area_unidade"] == "m2"


def test_a_unidade_da_coluna_mente_e_o_teor_e_quem_manda():
    """**A ficha 971: a coluna diz «35 m2» para 35,00 hectares.**

    Trinta e cinco metros quadrados é um banheiro; o teor diz «35,00 há». Vai o
    teor — 350.000 m² —, e o aviso mostra os dois números, para quem confere
    saber de onde saiu o que foi.
    """
    p = E.propor(dict(COLUNAS_971))
    assert p["campos"]["area_valor"] == "350000"
    assert "teor" in p["de_onde"]["area_valor"]
    aviso = [a for a in p["avisos"] if "não bate" in a][0]
    assert "35 m2 = 35 m²" in aviso
    assert "350000 m²" in aviso
    assert "A da ficha é a que vai" in aviso


def test_a_area_que_discorda_avisa_e_a_da_ficha_vai():
    """A coluna diz 9 ha e a ficha diz 9,92,03 ha: vai a da ficha."""
    p = E.propor(dict(COLUNAS_1117))
    assert p["campos"]["area_valor"] == "99203"
    aviso = [a for a in p["avisos"] if "não bate" in a][0]
    assert "90000" in aviso and "99203" in aviso


# ══════════════════════════════════ 6. o teor que discorda da coluna


def test_o_teor_que_discorda_da_coluna_nao_sai_pronto():
    """Sai para a fila da conferência, com as duas versões à vista.

    A ficha está marcada como **rural** e o teor diz «zona urbanizável
    (suburbana) desta cidade». Quem decide é o oficial; a máquina não escolhe.
    """
    p = E.propor(dict(COLUNAS_1117))
    assert p["divergente"] is True
    assert p["pode_enviar"] is False
    assert p["confianca"] == "baixa"
    assert any("marcada como RURAL" in a for a in p["avisos"])
    # e a coluna do rural/urbano **não** vai preenchida com o palpite:
    assert p["campos"]["rural_urbano"] == "U"


def test_o_aviso_mostra_os_sinais_de_QUEM_VENCEU():
    """**O defeito consertado em 15/09/2026, e ele estava no aviso que existe
    para a pessoa conferir.**

    A primeira versão escrevia os sinais dos dois lados na mesma frase, e nas
    duas fichas em que o teor é urbano **e** fala «hectare» (1117 e 1125) ela
    dizia «O teor diz URBANO — apoia-se em: hectare»: a razão apresentada
    contradizia a conclusão. Os sinais de quem perdeu entram depois de «Do outro
    lado aparecem», e não como apoio.
    """
    p = E.propor(dict(COLUNAS_1117))
    aviso = [a for a in p["avisos"] if "O teor diz" in a][0]
    apoia, _, outro = aviso.partition("Do outro lado aparecem")
    assert "hectare" not in apoia, apoia
    assert "suburbana" in apoia
    assert "hectare" in outro


# ════════════════════════════════════════ 7. o que o contrato exige


def test_o_que_o_contrato_exige_e_o_teor_nao_deu_volta_em_faltam():
    """`faltam` é a fila do que a pessoa completa na mão — e não um erro.

    Sem bairro no teor, ele aparece; e o `pode_enviar` fica `False` porque o
    contrato o exige, não porque o extrator falhou.
    """
    p = E.propor(dict(COLUNAS_URBANA))
    assert p["faltam"] == ["Bairro"]
    assert p["pode_enviar"] is False
    assert p["campos"]["logradouro"] == "Quadra 12"


def test_o_campo_que_falta_nao_impede_o_resto_de_sair():
    """O que falta não apaga o que foi lido: o `propor` devolve os dois, e quem
    confere decide se completa ou descarta."""
    p = E.propor(dict(COLUNAS_1117))
    assert p["faltam"] and p["campos"], "o que falta não pode esvaziar os campos"
    assert p["campos"]["cidade"] == "Cidade Exemplo"
    assert p["campos"]["uf"] == "MA"
    assert p["campos"]["cep"] == "65936000"


# ═══════════════════════ 8. o guarda do próprio módulo


def test_o_propor_nao_toca_no_banco():
    """**Ler o teor e propor não grava nada** — quem grava é quem confirma.

    O guarda lê o código da função, e não a intenção dela: sem isso, uma linha
    de `con.execute` acrescentada «para adiantar» passaria calada, e o extrator —
    que é leitura pura — passaria a escrever na fila por conta própria.
    """
    fonte = inspect.getsource(E.propor)
    arvore = ast.parse(fonte)
    proibidas = {"execute", "executemany", "executescript", "commit", "rollback"}
    achadas = [
        no.attr for no in ast.walk(arvore)
        if isinstance(no, ast.Attribute) and no.attr in proibidas
    ]
    assert not achadas, f"`propor` não pode chamar {achadas}"
    for verbo in ("INSERT", "UPDATE", "DELETE"):
        assert f'"{verbo} ' not in fonte and f"'{verbo} " not in fonte


def test_o_extrator_nao_tem_a_palavra_sigilo_nem_escrita():
    """O módulo lê teor e propõe endereço: **não sela, não cobra, não lava ato**.

    É o varredor dos nomes públicos na forma curta — a mesma régua das fraudes,
    do CNIB, do usucapião e da minuta do RI.
    """
    proibidos = ("selar", "cobrar", "lavrar", "averb", "cancelar", "registrar_ato")
    nomes = [n for n in dir(E) if not n.startswith("__")]
    achados = [n for n in nomes if any(p in n.lower() for p in proibidos)]
    assert not achados, achados


# ══════════════ 9. a unidade escrita em palavra, em rótulo e em alqueire
#
# **AS TRÊS FORMAS EXISTEM NA CASA, E A COLUNA DISCORDA DAS TRÊS.** Medido em
# 16/09/2026, depois de o conserto das tags inline (`<span>`) revelar a família
# das 24 fichas do loteamento Veronília. O texto abaixo é o **trecho real** de
# cada ficha, com a marca «IMÓVEL:-» do cabeçalho para o bloco ser o do imóvel.
#
# A régua antiga só olhava a sigla colada no número, e por isso tratava estas
# como «sem unidade»: caía na coluna, e a coluna erra nas três — 89 e 28 `m2`
# para glebas de 89 e 50 hectares, e nada para uma fazenda de 84 ha.

CABECALHO_DO_BLOCO = " MATRÍCULA: {n}\n\r\n IMÓVEL:- "


def _ficha(numero: str, area_valor, area_unidade: str, texto: str) -> dict:
    return {"id": abs(hash(numero)) % 9999, "numero": numero, "teor": texto,
            "rural_urbano": "R", "area_valor": area_valor,
            "area_unidade": area_unidade, "bairro": None, "cep": None,
            "tipo_imovel": "Fazenda/Sítio/Chácara"}


# 381 — «(oitenta e nove hectares, quarenta e três ares e cinco centiares)»,
# e a coluna diz `89 m2`.
TEOR_381 = CABECALHO_DO_BLOCO.format(n="381") + (
    "Uma gleba de terras denominada São Francisco com a área de 89,43,75 "
    "(oitenta e nove hectares, quarenta e três ares e cinco centiares) sita na "
    "fazenda Fortaleza deste município.")

# 3326 — «(cinquenta hectares trinta e dois ares e cinquenta e nove centiares)»,
# e a coluna diz `28 m2`.
TEOR_3326 = CABECALHO_DO_BLOCO.format(n="3326") + (
    "Rural denominado FAZENDA LEÃO FILHO, situado em CIDADE EXEMPLO - MA, com a "
    "área de 50,3259 (cinquenta hectares trinta e dois ares e cinquenta e nove "
    "centiares) e 2.836,20m, identificado pelas coordenadas geográficas.")

# 4010 — o rótulo vem ANTES: «área total (ha) do imóvel rural: 84,7438».
TEOR_4010 = CABECALHO_DO_BLOCO.format(n="4010") + (
    "Fazenda Nova Jerusalém: Município: Cidade Exemplo/MA; área total (ha) do "
    "imóvel rural: 84,7438; área liquida do imóvel: 84,7438; área de servidão "
    "administrativa: 0,0000; número do CCIR: 71179906258.")

# 534 — «165,96,87,5 = 34,291 alqueires goiano», e a coluna diz `600 m2`.
TEOR_534 = CABECALHO_DO_BLOCO.format(n="534") + (
    "Uma gleba de terras denominada Campo Verde, com área de "
    "165,96,87,5= 34,291 alqueires goiano, desmembrada da gleba maior com o "
    "mesmo nome Campo Verde sita na fazenda Fortaleza deste Município.")

# 971 — o caso já provado: a sigla `há` colada, contra a coluna que diz `35 m2`.
COLUNAS_381 = _ficha("381", "89", "m2", TEOR_381)
COLUNAS_3326 = _ficha("3326", "28", "m2", TEOR_3326)
COLUNAS_4010 = _ficha("4010", None, "m2", TEOR_4010)
COLUNAS_534 = _ficha("534", "600", "m2", TEOR_534)


def test_a_unidade_escrita_em_palavra_vence_a_coluna():
    """**A ficha 381: a coluna diz `89 m2` para uma gleba de 89 hectares.**

    Oitenta e nove metros quadrados é um cômodo. O teor diz «oitenta e nove
    hectares, quarenta e três ares e cinco centiares» — a grafia do hectare, a
    mesma que os parênteses escrevem —, e a leitura tem de ir por ele: são
    **894.375 m²**. Seguir a coluna mandaria 89 m² ao índice nacional.
    """
    p = E.propor(dict(COLUNAS_381))
    assert p["campos"]["area_valor"] == "894375"
    assert p["campos"]["area_unidade"] == "m2"
    assert p["de_onde"]["area_valor"].startswith("teor: «89,43,75 ha»")
    # e a divergência com a coluna aparece, para quem confere:
    assert any("não bate" in a for a in p["avisos"])


def test_a_palavra_no_parantese_vale_para_a_mesma_grafia_sem_virgula():
    """**A ficha 3326: «50,3259 (cinquenta hectares trinta e dois ares…)».**

    É o mesmo hectare escrito sem as vírgulas de separação — e a coluna diz
    `28 m2`. A conversão é 50 ha + 32 ares + 59 centiares = **503.259 m²**.
    """
    p = E.propor(dict(COLUNAS_3326))
    assert p["campos"]["area_valor"] == "503259"
    assert any("não bate" in a for a in p["avisos"])


def test_o_rotulo_antes_do_numero_tambem_e_unidade_escrita():
    """**A ficha 4010: «área total (ha) do imóvel rural: 84,7438».**

    Aqui o número não tem sigla colada nem palavra depois — a unidade está
    **antes**, no rótulo. Sem lê-la, a coluna (`m2`, sem valor) daria uma
    fazenda de 84 m²; com ela, **847.438 m²**.
    """
    p = E.propor(dict(COLUNAS_4010))
    assert p["campos"]["area_valor"] == "847438"

    diretamente = E.area_do_texto(
        "com a área total (ha) do imóvel rural: 84,7438", unidade_da_coluna="m2")
    assert diretamente["unidade"] == "ha" and diretamente["metros"] == 847438
    assert E.area_do_texto("área (m²) do terreno: 1.759,25")["unidade"] == "m2"


def test_o_alqueire_nao_se_converte_e_diz_por_que():
    """**A ficha 534: «165,96,87,5 = 34,291 alqueires goiano».**

    O alqueire não tem uma medida só — o goiano, o paulista e o do Norte
    diferem. O sistema **não faz essa conta**: devolve `metros=None`, a área cai
    na coluna da casa e a proposta ganha o aviso. A leitura antiga, pela régua
    do hectare, dava **1,65 trilhão de m²** para esta ficha.
    """
    a = E.area_do_texto(
        E.bloco_do_imovel(E.texto_do_teor(TEOR_534))["texto"], unidade_da_coluna="m2")
    assert a["palavra"] == "alqueire" and a["metros"] is None

    p = E.propor(dict(COLUNAS_534))
    assert p["campos"]["area_valor"] == "600"          # a coluna, não o palpite
    assert any("alqueire" in aviso for aviso in p["avisos"])
    assert any("não faz essa conta" in aviso for aviso in p["avisos"])


def test_a_unidade_do_teor_que_vem_em_par_nao_engana():
    """**A primeira unidade escrita é a da área; a segunda é equivalência.**

    «quinhentos metros quadrados, o que equivale a 0,05 hectares» fala de metro
    quadrado — procurar hectares primeiro leria a equivalência como se fosse a
    unidade. E é a ordem das palavras no texto, não a preferência de quem lê.

    **São duas coisas: o CAMPO é canônico e a CITAÇÃO é fiel.** O campo diz
    `m2`/`ha`, que é o que o contrato conhece; a citação guarda a forma do
    livro («metros quadrados»), porque quem confere vai procurar isso na ficha.

    > **E ESTE TESTE NÃO RODAVA** — ele estava **indentado dentro** do teste do
    > alqueire, e pytest não recolhe função aninhada. Achado em 16/09/2026
    > conferindo a coleta com `--collect-only`, na mesma passada em que a regra
    > que ele guarda foi estendida ao ponto de milhar: **teste que não roda é
    > pior que teste nenhum**, porque a lista de testes diz que ele existe.
    """
    a = E.area_do_texto("com a área de 500 metros quadrados, o que equivale "
                        "a 0,05 hectares, nesta cidade")
    assert a["metros"] == 500 and a["unidade"] == "m2"
    assert a["unidade_como_escrita"] == "metros quadrados"

    b = E.area_do_texto("com a área de 5,0000 hectares, o que equivale a "
                        "50.000,00 metros quadrados")
    assert b["unidade"] == "ha" and b["metros"] == 50000
    assert b["unidade_como_escrita"] == "hectares"


TEOR_2902 = ("um terreno com 300 (trezentos) metros de frente e 49,00 (quarenta "
             "e nove) metros de fundo, frente para a Vila Vaquejada. O terreno "
             "tem uma área de 13.200 metros quadrados, com cerca de arame lizo.")
COLUNAS_2902 = _ficha("2902", "39", "m2", TEOR_2902)


def test_o_ponto_de_milhar_do_teor_nao_vira_mil_vezes_menos():
    """**A ficha 2902: «uma área de 13.200 metros quadrados».**

    Treze metros quadrados é um banheiro; a mesma ficha descreve o terreno com
    **300 metros de frente e 49 de fundo**, e o milhar inteiro são **13.200 m²**.
    O ponto com três dígitos depois dele é o separador de milhar da casa, e não
    o decimal — e era por isso que `13.200` saía como `13` no campo que diz de
    quem é o imóvel e de que tamanho ele é.

    **A medição das 11 linhas da COLUNA continua valendo**, e é o que a guarda
    preserva: ali o ponto tem um ou dois dígitos depois (`9.7`, `31.47`) e é
    decimal. Quem escreve o milhar inteiro é o **teor**, e nenhuma das duas
    medições responde pela outra.
    """
    assert API.area_em_metros("13.200", "m2") == 13200
    assert API.area_em_metros("9.7", "m2") == 10        # a coluna, decimal
    assert API.area_em_metros("31.47", "m2") == 31
    assert API.area_em_metros("1.118,91", "m2") == 1118  # a vírgula manda

    p = E.propor(dict(COLUNAS_2902))
    assert p["campos"]["area_valor"] == "13200"
    assert p["campos"]["area_unidade"] == "m2"
    assert "13.200" in p["de_onde"]["area_valor"]


def test_o_numero_sem_unidade_no_teor_nao_vira_area():
    """**O lote não é área.** «LOTE 231» tem quatro dígitos e nenhuma unidade no
    teor; a régua é a unidade **escrita na ficha**, e não a que veio da coluna —
    contar a da coluna aqui fazia a matrícula 513 ler «100» como 100 hectares.
    """
    assert E.area_do_texto("terreno urbano, LOTE 231, quadra 12",
                           unidade_da_coluna="m2") is None


# ═══════════════════════════════════════════════════════════════════════
# A CITAÇÃO DA PROVENIÊNCIA — o que cada campo diz de onde veio
# ═══════════════════════════════════════════════════════════════════════
#
# A tela da conferência tem uma coluna, «de onde saiu», e é ela que separa
# conferir a leitura de confiar na máquina. Medido nas 1.442 propostas da cópia
# da produção, 16/09/2026: **todo campo preenchido tem citação** — os campos sem
# citação são exatamente os que ficaram em `faltam` (logradouro 26, bairro 93,
# número 13, urbano/rural 2, área 7, tipo 1.403). Os testes daqui guardam três
# coisas que a medição daquele dia achou faltando: a UF e a unidade da área
# saíam com a célula **em branco**, e a cidade e o urbano/rural diziam de onde
# vieram **sem mostrar o que o livro escreve**.

TEOR_DA_CITACAO = CABECALHO_DO_BLOCO.format(n="1616") + (
    "Uma gleba de terras denominada Fazenda Boa Esperança, situada na zona rural "
    "deste município de Cidade Exemplo-MA, com a área de 45,0000 ha.")
COLUNAS_DA_CITACAO = _ficha("1616", None, "ha", TEOR_DA_CITACAO)


def test_a_cidade_cita_a_frase_do_livro_e_nao_so_o_nome_limpo():
    """**«teor: Cidade Exemplo» dizia de onde veio sem mostrar o que o livro
    escreve** — e quem confere vai procurar na ficha a frase, não o nome já
    limpo. Medido: 680 citações deste campo saíam assim."""
    p = E.propor(dict(COLUNAS_DA_CITACAO))
    assert p["de_onde"]["cidade"] == "teor: «município de Cidade Exemplo»"


def test_o_urbano_ou_rural_cita_as_palavras_do_livro_entre_aspas():
    """**As palavras soltas se liam como rótulo do sistema.** «teor: gleba de
    terras, fazenda, hectare» não dizia que aquilo está escrito na ficha —
    1.427 citações deste campo saíam assim. Entre «» elas são o que são."""
    p = E.propor(dict(COLUNAS_DA_CITACAO))
    d = p["de_onde"]["rural_urbano"]
    assert d.startswith("teor: «") and d.count("«") >= 2
    assert '"' not in d      # a marca é «», e aspas retas são do texto de fora


def test_a_uf_diz_de_onde_veio_mesmo_quando_e_padrao_da_casa():
    """**A célula da UF saía em branco nas 1.442.** A origem é certa e simples
    — o padrão da casa, porque o teor quase nunca escreve a sigla —, e o
    silêncio a fazia parecer desconhecida."""
    p = E.propor(dict(COLUNAS_DA_CITACAO))
    assert p["campos"]["uf"] == "MA"
    assert p["de_onde"]["uf"] == (
        "padrão da serventia (MA) — o teor não escreve a UF")

    com_uf = dict(COLUNAS_DA_CITACAO)
    com_uf["uf"] = "ma"
    assert E.propor(com_uf)["de_onde"]["uf"] == "já estava na ficha"


def test_a_unidade_da_area_diz_de_onde_veio_e_para_onde_vai():
    """A unidade da área também saía em branco: o campo vai como `m2` porque é
    o que o ONR espera, e a citação diz **de onde** veio a unidade e **que
    houve conversão** — sem isso, quem confere lê `m2` e não sabe se a ficha
    estava em metros ou se alguém converteu."""
    p = E.propor(dict(COLUNAS_DA_CITACAO))
    assert p["campos"]["area_unidade"] == "m2"
    d = p["de_onde"]["area_unidade"]
    assert "«ha»" in d and "convertida para m²" in d

    da_coluna = _ficha("992", "63", "ha", TEOR_DA_CITACAO.replace("45,0000 ha", ""))
    d2 = E.propor(dict(da_coluna))["de_onde"]["area_unidade"]
    assert "coluna" in d2 and "convertida para m²" in d2


def test_todo_campo_preenchido_diz_de_onde_veio():
    """**A invariante que a medição confirmou nas 1.442**: campo preenchido tem
    citação; campo sem citação é campo que ficou em `faltam`.

    É ela que impede o defeito de voltar em campo novo — um décimo primeiro
    campo que a tela mostre sem a coluna preenchida aparece aqui.
    """
    for colunas in (COLUNAS_DA_CITACAO, COLUNAS_381, COLUNAS_2902,
                    COLUNAS_4010, COLUNAS_3326, COLUNAS_1117):
        p = E.propor(dict(colunas))
        for campo, valor in p["campos"].items():
            if E._vazio(valor):
                continue
            assert not E._vazio(p["de_onde"].get(campo)), (
                f"o campo «{campo}» foi preenchido com «{valor}» e não diz de "
                f"onde veio — matrícula {colunas.get('numero')}")