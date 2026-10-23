"""O MOLDE DA CERTIDÃO DO RCPN — o que o papel promete, o código preenche.

Pedido do oficial em 01/09/2026: *«revise as certidões do rcpn e deixe elas
sem repetições e com layout igual ao do provimento do cnj, inclusive cor de
letra»*.

O QUE ESTES TESTES GUARDAM

  **1. `@` no molde que o código não conhece sai CRU no papel.** É o defeito
  mais caro possível aqui: a certidão é assinada e entregue, e sairia
  literalmente «@genitor1_municipio» impresso. O molde é um `.odt` que o
  oficial edita no LibreOffice — ele vai mexer nele de novo, e este teste é o
  que avisa antes de o papel sair.

  **2. As repetições que ele mandou tirar não voltam.** Eram quatro, todas
  medidas no molde de 01/09:
     - a cidade e a UF duas vezes na linha da comarca, coladas
       («Cidade Exemplo – MA**Cidade Exemplo/MA**»);
     - o nome do oficial grudado no CEP, sendo que ele já assina duas linhas
       acima;
     - os emolumentos numa linha geral **e** dentro de cada selo — com um
       selo só, que é o caso normal, os mesmos números duas vezes;
     - e a pior, que não era repetição mas **descasamento**: `@nomefiliacao1`
       é a MÃE e `@avosfiliacao1` eram os avós PATERNOS. Quem lê pareia linha
       com linha e dá os avós ao genitor errado.

  **3. A cor de letra é a que a certidão real desta casa usa: PRETO.** Medido
  no PDF de uma certidão desta serventia no modelo nacional (CNS 000000,
  12/02/2026): 25 ocorrências de preto puro nos fluxos que desenham texto, e
  nenhum vermelho. O molde pintava os 56 valores de `#c00000`.

  **4. E o estilo não pode voltar a se chamar «TVermelho».** Estilo com esse
  nome pintando preto é carimbo que mente para quem abrir o molde.

  **5. O RODAPÉ VIROU DUAS COLUNAS, IGUAL AO ANEXO IV — 09/09/2026,** a
  pedido do oficial, a partir da imagem real do Provimento CNJ 182/2024
  (`FONTES_EXTERNAS/cnj_provimento_182/provimento_pagina_5.png`). Trocou:
  «COMARCA DE @ri_cidade – @ri_uf» virou só «@ri_cidade – @ri_uf» (o Anexo
  IV não tem «COMARCA DE»); `@linha_assinatura` — que saía em **18pt negrito**,
  do tamanho do título, um defeito seu — virou o «(assinatura)» literal do
  modelo; e `@unit_name`, `@serventia_email`, `@serventia_telefone`,
  `@serventia_cnpj` e `@ri_substituta` saíram do papel, porque o Anexo IV não
  os tem e o oficial mandou tirar o que não consta nele.

  **6. E UM SEGUNDO DEFEITO DE FONTE APARECEU MEDINDO O PRIMEIRO — bem maior
  que o rodapé.** Quase todo valor da certidão (nome, CPF, matrícula, data,
  hora, naturalidade, filiação...) usava `TValor`/`TValorNegrito` **aninhado**
  dentro do estilo do rótulo — `<T5><TValorNegrito>@nomenascido</></>`  — e o
  LibreOffice, ao exportar pra PDF, **derruba o estilo de fora sempre que o
  parágrafo inteiro se resume a esse par aninhado e mais nada**: o valor saía
  em Calibri 11 (o padrão do documento inteiro), sem serifa, do lado de um
  rótulo em Times New Roman. Testado par a par contra a certidão real: um
  parágrafo com mais alguma coisa de texto de verdade (rótulo antes, um
  traço, uma frase) não cai nisso; um parágrafo que é só o par aninhado, cai
  sempre. O conserto **não é reaninhar diferente**: é tirar o aninhamento —
  um span só, com o estilo do rótulo aplicado direto no marcador. Ver
  `test_nenhum_valor_fica_aninhado_dentro_de_tvalor` abaixo.

  **7. E O CORPO NÃO ERA O DO ANEXO IV — 10/09/2026.** O rodapé virou o do
  Anexo em 09/09 e o corpo ficou como estava; medido campo a campo contra a
  página 5 do Provimento, ele diferia em cinco coisas, e **três são de
  fundo**:
     - **«MUNICÍPIO DE REGISTRO E UNIDADE DE FEDERAÇÃO» não existe no Anexo
       IV.** O município do registro é a serventia que assina, e o rodapé já
       a diz inteira — CNS, oficial, cidade, UF, endereço, CEP. Era a
       repetição do rodapé, por dentro do corpo;
     - **a UF não tinha caixa própria** na naturalidade nem no local de
       nascimento: saía «IMPERATRIZ/MA» grudado, e o Anexo dá uma caixa ao
       município e outra, menor, à UF;
     - **o sexo estava na linha errada** — no Anexo ele fecha a linha do
       local de nascimento, e aqui estava ao lado da naturalidade;
     - os genitores iam **os dois na mesma caixa**, com o município grudado
       no nome por um «natural de», e os dois pares de avós noutra caixa; o
       Anexo descreve **um genitor por vez**, com os avós dele logo abaixo;
     - e a caixa «Gêmeo» era duas — uma com SIM/NÃO, que o modelo não tem.

  **E OS RÓTULOS SE POSICIONAM POR PARADA DE TABULAÇÃO, em centímetros.**
  Espaços de Times 8pt bold não dividem 15,191 cm em conta redonda, e foi
  contando espaço que o rótulo do casamento empurrou «ANO» para a segunda
  linha. A parada fica escrita exatamente onde a coluna começa — e a
  primeira versão ainda assim grudou dois rótulos: «MUNICÍPIO DE NASCIMENTO»
  ocupa 4,3 cm e passava da parada do «UF» seguinte, e **parada que o texto
  já passou não anda** (o tabulador vira um espaço). A coluna do município
  do genitor foi a 4,9 cm por causa disso — conferido no PDF, e não na
  leitura.
"""
from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import rc_certidao_odt as ODT

MOLDE = RAIZ / "modelos" / "certidao_nascimento_modelo.odt"
tem_o_molde = pytest.mark.skipif(
    not MOLDE.is_file(), reason="o molde .odt não está nesta instalação")


def conteudo() -> str:
    return zipfile.ZipFile(MOLDE).read("content.xml").decode("utf-8")


def texto_do_molde() -> str:
    """O texto visível, com tabulação e quebra preservadas.

    **TABULAÇÃO SE TRADUZ, e não se apaga** — a primeira versão disto tirava
    as tags sem tratar `<text:tab/>`, e quatro rótulos apareceram colados ou
    sumidos. Eu quase «consertei» um estrago que não existia: era a leitura.
    """
    x = conteudo()
    x = x[x.find("<office:body"):]
    x = re.sub(r"<text:tab/>", " | ", x)
    x = re.sub(r"<text:line-break/>", "\n", x)
    x = re.sub(r"<text:s[^/]*/>", " ", x)
    x = re.sub(r"</text:p>|</table:table-cell>", "\n", x)
    return re.sub(r"<[^>]+>", "", x)


def marcadores_do_molde() -> set[str]:
    return set(re.findall(r"@[A-Za-z_0-9]+", texto_do_molde()))


# ------------------------------------------------- o guarda principal


@tem_o_molde
def test_todo_marcador_do_molde_o_codigo_sabe_preencher():
    """**O PAPEL NÃO PODE PROMETER O QUE O CÓDIGO NÃO ENTREGA.**

    Marcador que o `valores()` não conhece não é substituído: sai a palavra
    `@alguma_coisa` impressa numa certidão assinada.
    """
    faltando = sorted(marcadores_do_molde() - set(ODT.valores({}, {}, {})))
    assert not faltando, (
        "estes marcadores estão no molde e o código não preenche — sairiam "
        f"escritos no papel: {faltando}")


@tem_o_molde
def test_o_codigo_pode_saber_mais_que_o_molde_usa():
    """A OUTRA DIREÇÃO NÃO É DEFEITO, e por isso não se varre.

    `valores()` é o **vocabulário** que o molde pode usar; o oficial edita o
    `.odt` e pode pôr de volta um campo que hoje não está lá. Exigir que todo
    mapeamento apareça no molde tiraria dele essa liberdade — e o dia em que
    ele repusesse o campo, sairia `@selo1_total` cru.
    """
    sobrando = set(ODT.valores({}, {}, {})) - marcadores_do_molde()
    assert "@selo1_total" in sobrando, (
        "este teste existe para declarar que sobra é normal; se o vocabulário "
        "encolheu até aqui, reveja a decisão em vez de apagar o teste")


# ------------------------------------------------- as repetições


@tem_o_molde
def test_a_cidade_e_a_uf_nao_repetem_coladas():
    """A comarca virou duas colunas em 09/09/2026 (Anexo IV) — cidade e UF
    aparecem uma vez em cada uma, e isso é o modelo, não a repetição que o
    oficial mandou tirar em 01/09. O que continua proibido é a marca
    ANTIGA de repetição: o `@cidade_uf` colado sem espaço nem travessão."""
    t = texto_do_molde()
    assert "@cidade_uf" not in t, (
        "a marca antiga de repetição voltou: "
        "«@ri_cidade – @ri_uf@cidade_uf»")
    assert "COMARCA DE" not in t, (
        "o Anexo IV não tem «COMARCA DE» na frente da cidade — isso é "
        "resíduo do rodapé de uma coluna só, de antes de 09/09/2026")


@tem_o_molde
def test_o_oficial_nao_volta_grudado_no_cep():
    t = texto_do_molde()
    assert "@serventia_cep@escrevente" not in t
    assert "@escrevente" in t, (
        "o molde precisa de @escrevente no rodape (nome de quem assina) "
        "— nao colado no CEP")
    assert "Emitida por" not in t
    assert t.find("@registrador") < t.find("@escrevente"), (
        "no rodapé em duas colunas (09/09/2026), a coluna da esquerda "
        "(@registrador) vem antes da direita (@escrevente) na leitura do "
        "texto — célula por célula")


@tem_o_molde
def test_a_assinatura_gigante_nao_volta_e_o_espaco_fica_vazio():
    """`@linha_assinatura` saía em **18pt negrito** — do tamanho do título da
    certidão —, ao lado de rótulos de 8pt. Defeito seu, achado em 09/09/2026
    ao construir o rodapé em duas colunas.

    **E o «(assinatura)» que entrou no lugar também saiu**, no mesmo dia, por
    decisão do oficial: *«não faz sentido o (assinatura), pedi pra tirar pq é
    o lugar do escrevente assinar»*. No Anexo IV/V a palavra é PLACEHOLDER do
    modelo em branco — diz onde a assinatura vai, como «Nome no momento da
    habilitação» dentro das caixas —, e impressa ela ocupa justamente o
    espaço da caneta.

    **O que fica é a linha vazia**: apagar o parágrafo subiria o nome do
    escrevente e comeria o espaço de assinar, que é o motivo de tirar a
    palavra.
    """
    t = texto_do_molde()
    assert "@linha_assinatura" not in t
    assert "(assinatura)" not in t, (
        "a palavra voltou ao papel — ela é placeholder do modelo em branco, "
        "e impressa ocupa o lugar em que o escrevente assina")
    entre = t[t.find("@dataatual"):t.find("@escrevente")]
    assert entre.count("\n") >= 2, (
        "sumiu o espaço em branco entre a data e o nome de quem assina — "
        "sem ele não há onde assinar de caneta")


@tem_o_molde
def test_o_que_o_anexo_iv_nao_tem_saiu_do_papel():
    """Pedido do oficial em 09/09/2026: «tira o que nao consta no modelo do
    cnj». unit_name, e-mail, telefone, CNPJ e substituta não estão no Anexo
    IV — e o rodapé de uma coluna só já carregava os cinco."""
    t = texto_do_molde()
    for marcador in (
        "@unit_name", "@serventia_email", "@serventia_telefone",
        "@serventia_cnpj", "@ri_substituta",
    ):
        assert marcador not in t, f"{marcador} não está no Anexo IV e devia ter saído"


@tem_o_molde
def test_nenhum_valor_fica_aninhado_dentro_de_tvalor():
    """**O DEFEITO DA FONTE ERRADA, MEDIDO E CONSERTADO EM 09/09/2026.**

    `<span T5><span TValor>@x</span></span>` — T5 (ou T3, T8, T9, T10, T11,
    T13...) por fora, TValor/TValorNegrito por dentro — é o padrão que o
    LibreOffice derruba ao exportar pra PDF sempre que o parágrafo inteiro se
    resume a esse par: o valor sai no Calibri do documento, não no Times do
    rótulo ao lado. O conserto foi tirar o aninhamento; este teste impede
    que ele volte, em qualquer estilo de rótulo.
    """
    c = conteudo()
    aninhados = re.findall(
        r'<text:span text:style-name="T\d+"><text:span '
        r'text:style-name="TValor(?:Negrito)?">',
        c)
    assert not aninhados, (
        "TValor/TValorNegrito aninhado dentro de um estilo de rótulo — isso "
        "é o defeito da fonte errada voltando. Tire o aninhamento: aplique "
        f"o estilo do rótulo direto no marcador. Achados: {aninhados}")


@tem_o_molde
def test_o_cargo_do_delegatario_nao_e_o_de_quem_assina_a_via():
    """**O DEFEITO DE 10/09/2026, MEDIDO NA CERTIDÃO 21 DA PRODUÇÃO.**

        «fomos emitir uma certidao de nascimento e o oficial estava com nome
         de escrevente»                            — o oficial, 10/09/2026

    O rodapé do Anexo IV tem **duas colunas, com um nome e um cargo em cada**:
    à esquerda o delegatário («Nome do Oficial / Oficial de Registro Civil»),
    à direita quem assina aquela via («Nome do Oficial/Escrevente / Cargo»).
    O molde usava **o mesmo marcador nos dois lugares**.

    Medido na certidão 21 (10/09/2026 09:12, emitida pela Elisa), lendo a
    produção em `mode=ro`:

        MARIO EXEMPLO DOS SANTOS       Elisa Exemplo Lima
        Escrevente Autorizado          Escrevente Autorizado

    **E o conserto de 09/09 é que produziu isso.** Naquele dia o oficial
    relatou o contrário — «Tabelião e Oficial de Registro» sob o nome da
    Elisa —, e o marcador único foi apontado para `emitida_funcao`: a
    coluna da direita ficou certa e a da esquerda passou a chamar o
    delegatário de escrevente. **Com um marcador só, consertar um lado
    estraga o outro**; a saída é serem dois.

    Cargo errado debaixo do nome de quem responde pela serventia é afirmação
    falsa em papel assinado — pior que campo vazio, que não afirma nada.
    """
    t = texto_do_molde()
    assert t.count("@funcaoregistrador") == 1, (
        "o cargo do delegatário voltou a ser usado nas duas colunas")
    assert t.count("@funcaoescrevente") == 1, (
        "a coluna de quem assina está sem o cargo dela")
    assert t.find("@registrador") < t.find("@funcaoregistrador")
    assert t.find("@escrevente") < t.find("@funcaoescrevente")
    assert t.find("@funcaoregistrador") < t.find("@escrevente"), (
        "o bloco do delegatário vem antes do de quem assina, como no Anexo IV")

    # e o caso real, com os dados que a produção tinha naquela emissão
    v = ODT.valores(
        {"oficial": "MARIO EXEMPLO DOS SANTOS",
         "cargo": "Escrevente Autorizado"},   # o quadro também os confunde
        {"emitida_por": "Elisa Exemplo Lima",
         "emitida_funcao": "Escrevente Autorizado"},
        {"serventia_titular": "MARIO EXEMPLO DOS SANTOS",
         "serventia_titulo": "Tabelião e Oficial de Registro"})
    assert v["@registrador"] == "MARIO EXEMPLO DOS SANTOS"
    assert v["@funcaoregistrador"] == "Tabelião e Oficial de Registro"
    assert v["@escrevente"] == "Elisa Exemplo Lima"
    assert v["@funcaoescrevente"] == "Escrevente Autorizado"


def test_o_tabeliao_nao_volta_sob_o_nome_de_quem_emitiu():
    """O relato de 09/09/2026 não pode voltar pelo caminho de volta.

    Consertar a coluna da esquerda não pode fazer a da direita voltar a
    chamar a escrevente de tabeliã — e é justamente esse vaivém que um
    marcador só produzia.
    """
    v = ODT.valores(
        {"oficial": "MARIO EXEMPLO DOS SANTOS"},
        {"emitida_por": "Elisa Exemplo Lima",
         "emitida_funcao": "Escrevente Autorizado"},
        {"serventia_titulo": "Tabelião e Oficial de Registro"})
    assert v["@funcaoescrevente"] == "Escrevente Autorizado"
    assert v["@funcaoregistrador"] == "Tabelião e Oficial de Registro"


def test_sem_saber_quem_emitiu_o_cargo_cai_no_da_serventia():
    """Certidão sem emitente registrado (o acervo, por exemplo) assina como a
    serventia — nunca em branco, que numa linha de cargo não afirma nada, e
    nunca com um cargo inventado."""
    v = ODT.valores({}, {}, {"serventia_titular": "MARIO EXEMPLO DOS SANTOS",
                             "serventia_titulo": "Tabelião e Oficial de Registro"})
    assert v["@escrevente"] == "MARIO EXEMPLO DOS SANTOS"
    assert v["@funcaoescrevente"] == "Tabelião e Oficial de Registro"
    assert v["@funcaoregistrador"] == "Tabelião e Oficial de Registro"


def test_escrevente_vem_de_emitida_por():
    """Quem imprime vai em @escrevente; titular fica em @registrador.

    `@linha_assinatura` ficou vazio em 09/09/2026: o rodapé em duas colunas
    (Anexo IV/V) não usa mais essa linha — o «(assinatura)» que a substituiu
    é texto literal do molde, não um marcador. O vocabulário continua
    existindo (sobra não é código morto — outra tela pode repô-lo), só não
    afirma mais «Assinatura: ...»."""
    v = ODT.valores(
        {"oficial": "TITULAR DA CASA", "cargo": "Oficial"},
        {"emitida_por": "MARIO EXEMPLO"},
        {})
    assert v["@escrevente"] == "MARIO EXEMPLO"
    assert v["@registrador"] == "TITULAR DA CASA"
    assert v["@funcaoregistrador"] == "Oficial"
    assert v["@linha_assinatura"] == ""


@tem_o_molde
def test_os_emolumentos_saem_DENTRO_da_caixa_do_selo():
    """**E EU TINHA TIRADO A CÓPIA ERRADA.** A duplicata era real — a linha
    geral e a do selo traziam os mesmos números com um selo só —, e eu apaguei
    a de dentro da caixa, ficando com a de fora.

    O oficial corrigiu em 01/09/2026: *«coloque os emolumentos dentro da caixa
    do selo»*. **É o lugar certo**: o valor é daquele selo, e com dois selos a
    linha de fora seria uma soma que ninguém sabe de onde vem.
    """
    t = texto_do_molde()
    assert "Valor cobrado por esta certidão" not in t, (
        "a linha geral de valores voltou — com um selo ela repete a da caixa")
    for n in ("1", "2"):
        assert f"@selo{n}_valores" in t, (
            f"a caixa do selo {n} está sem a linha de valores")


@tem_o_molde
def test_os_avos_seguem_o_seu_proprio_genitor():
    """**ERA DESCASAMENTO, E NÃO REPETIÇÃO** — e sai mais caro que ela.

    `@nomefiliacao1` é a mãe (o quadro monta mãe, depois pai) e
    `@avosfiliacao1` eram os avós PATERNOS: a primeira linha de cada caixa
    não falava da mesma pessoa.
    """
    t = texto_do_molde()
    for velho in ("@nomefiliacao1", "@nomefiliacao2",
                  "@avosfiliacao1", "@avosfiliacao2"):
        assert velho not in t, f"{velho} voltou ao molde"
    for n in ("1", "2"):
        assert f"@genitor{n}_nome" in t
        assert f"@genitor{n}_avos" in t


@tem_o_molde
def test_o_municipio_de_nascimento_de_cada_genitor_chega_ao_papel():
    """O modelo do CNJ o pede, o quadro já o media, e o molde o perdia."""
    t = texto_do_molde()
    for n in ("1", "2"):
        assert f"@genitor{n}_municipio" in t
        assert f"@genitor{n}_uf" in t


# --------------------------- o CORPO, campo a campo como o Anexo IV


def linhas_do_molde() -> list[str]:
    return [l.strip() for l in texto_do_molde().split("\n") if l.strip()]


ROTULOS_DO_ANEXO_IV = [
    "DATA DE NASCIMENTO | DIA | MÊS | ANO",
    "HORÁRIO DE NASCIMENTO | MUNICÍPIO DA NATURALIDADE | UF",
    "LOCAL DE NASCIMENTO | MUNICÍPIO DE NASCIMENTO | UF | SEXO",
    "NOME DO(A) GENITOR(A) | MUNICÍPIO DE NASCIMENTO | UF",
    "AVÓ(Ó)(S) RESPECTIVO(S)",
    "GENITOR(A) | MUNICÍPIO DE NASCIMENTO | UF",
    "AVÓ(Ó)(S) RESPECTIVO(S)",
    "GÊMEO",
    "DATA DO REGISTRO | DNV",
]


@tem_o_molde
def test_o_corpo_e_o_do_anexo_iv_na_ordem_do_anexo_iv():
    """**O CORPO, MEDIDO CAMPO A CAMPO — 10/09/2026.**

    O rodapé já era o do Anexo IV desde 09/09; o corpo não. Medido na página
    5 do Provimento CNJ 182/2024, ele pede cada linha nesta ordem, e o molde
    trazia outra coisa em quatro delas.
    """
    linhas = linhas_do_molde()
    onde = []
    for rotulo in ROTULOS_DO_ANEXO_IV:
        assert rotulo in linhas, f"o Anexo IV pede o rótulo «{rotulo}»"
        # o segundo «AVÓ(Ó)(S)» tem de vir depois do primeiro, e por isso a
        # busca começa de onde a anterior parou
        de = (onde[-1] + 1) if onde else 0
        onde.append(linhas.index(rotulo, de))
    assert onde == sorted(onde), (
        f"os rótulos do Anexo IV estão fora de ordem: {onde}")


@tem_o_molde
def test_o_municipio_de_registro_saiu_do_corpo():
    """**ELE NÃO EXISTE NO ANEXO IV, e o rodapé já o diz inteiro.**

    O município do registro é a serventia que assina — e o pé da folha traz
    CNS, oficial, cidade, UF, endereço e CEP. A caixa repetia o que a folha
    já afirma, que é o defeito que o oficial mandou tirar do rodapé em
    01/09/2026, aqui dentro do corpo.
    """
    t = texto_do_molde()
    assert "@municipio_registro_nascimento" not in t
    assert "MUNICIPIO DE REGISTRO" not in t
    assert "MUNICÍPIO DE REGISTRO" not in t


@tem_o_molde
def test_a_uf_tem_caixa_propria_nas_duas_linhas():
    """**«IMPERATRIZ/MA» NUMA CAIXA SÓ É A REPETIÇÃO DO RODAPÉ, POR DENTRO.**

    O Anexo IV dá ao município uma caixa e à UF outra, menor — nas duas
    linhas: a da naturalidade e a do local de nascimento. É o mesmo conserto
    que o casamento recebeu no Anexo V.
    """
    t = texto_do_molde()
    for separado in ("@naturalidade_cidade", "@naturalidade_uf",
                     "@municipio_nascimento", "@uf_nascimento"):
        assert separado in t, f"{separado} não está no molde"
    # os dois marcadores que juntavam cidade e UF saíram do PAPEL — e
    # continuam no vocabulário, porque o oficial edita o molde
    assert "@nomelocalnascimento" not in t
    assert not re.search(r"@naturalidade(?![_A-Za-z0-9])", t), (
        "o marcador que junta cidade e UF voltou ao papel")
    assert "@local_nascimento" in t
    vocabulario = ODT.valores({}, {}, {})
    assert "@nomelocalnascimento" in vocabulario
    assert "@naturalidade" in vocabulario


@tem_o_molde
def test_cada_genitor_tem_o_seu_bloco_com_os_avos_logo_abaixo():
    """**O ANEXO IV DESCREVE UM GENITOR POR VEZ.**

    Nome, município de nascimento, UF — e os avós **daquele** genitor na
    linha seguinte. O molde punha os dois nomes numa caixa e os dois pares de
    avós noutra: quem lê pareia linha com linha, e a primeira linha de uma
    não falava da mesma pessoa que a primeira linha da outra. É o
    descasamento do item 2 desta suíte, pelo outro lado.
    """
    linhas = linhas_do_molde()
    gen1 = linhas.index("NOME DO(A) GENITOR(A) | MUNICÍPIO DE NASCIMENTO | UF")
    avo1 = linhas.index("AVÓ(Ó)(S) RESPECTIVO(S)", gen1)
    gen2 = linhas.index("GENITOR(A) | MUNICÍPIO DE NASCIMENTO | UF", avo1)
    avo2 = linhas.index("AVÓ(Ó)(S) RESPECTIVO(S)", gen2)
    assert gen1 < avo1 < gen2 < avo2
    t = texto_do_molde()
    assert "FILIAÇÃO:" not in t, "o rótulo do bloco único voltou"
    assert "AVÓS:" not in t, "o rótulo do bloco único voltou"
    assert "natural de" not in t, (
        "o município do genitor voltou grudado no nome, com «natural de» no "
        "meio — no Anexo IV ele tem caixa própria")


@tem_o_molde
def test_a_caixa_do_gemeo_e_uma_so():
    """No Anexo IV há **uma** caixa sob «Gêmeo», com o nome e a matrícula. O
    molde tinha duas: uma dizendo SIM/NÃO e outra com os nomes — e o SIM/NÃO
    não está no modelo."""
    t = texto_do_molde()
    assert "@nomegemeos" in t
    assert "@possuigemeos" not in t
    assert "NOME E MATRÍCULA DOS GÊMEOS" not in t


@tem_o_molde
def test_o_rotulo_nao_e_o_placeholder_de_dentro_da_caixa():
    """**TERCEIRA VEZ QUE ESTA LIÇÃO APARECE, e as três foram do oficial.**

    Primeiro o «(assinatura)», depois o «DIA MÊS ANO» do Anexo V — e agora
    «POR EXTENSO»: no modelo em branco, o que está DENTRO da caixa descreve
    a FORMA do dado («Data de nascimento por extenso»), e o rótulo de verdade
    é o que está ACIMA («Data de nascimento»).

    **E «DIA», «MÊS» e «ANO» FICAM AQUI**, ao contrário do casamento: no
    Anexo IV eles estão acima das três caixinhas (dentro está «00», «00»,
    «0000»); no Anexo V estão dentro.
    """
    t = texto_do_molde()
    assert "POR EXTENSO" not in t, (
        "«POR EXTENSO» é o placeholder de dentro da caixa, e não o rótulo")
    assert "DATA DE NASCIMENTO | DIA | MÊS | ANO" in linhas_do_molde()


def test_o_local_de_nascimento_nao_repete_o_municipio():
    """A caixa «Local de nascimento» leva SÓ o local.

    `@nomelocalnascimento` monta «HOSPITAL X, IMPERATRIZ/MA» — era o que a
    caixa única do molde antigo pedia. Com as três caixas do Anexo, ele
    repetiria o município e a UF nas duas seguintes.
    """
    v = ODT.valores(
        {"local_nascimento": "HOSPITAL MUNICIPAL SANTA RITA",
         "municipio_nascimento": "IMPERATRIZ",
         "municipio_nascimento_uf": "MA"},
        {}, {})
    assert v["@local_nascimento"] == "HOSPITAL MUNICIPAL SANTA RITA"
    assert v["@municipio_nascimento"] == "IMPERATRIZ"
    assert v["@uf_nascimento"] == "MA"
    # e o antigo continua sabendo montar a frase inteira
    assert v["@nomelocalnascimento"] == "HOSPITAL MUNICIPAL SANTA RITA, IMPERATRIZ/MA"


def test_sem_local_nem_uf_nada_e_afirmado():
    """Campo vazio não afirma nada — e vai um espaço, nunca um zero ou um
    traço que pareça dado."""
    v = ODT.valores({}, {}, {})
    for marcador in ("@local_nascimento", "@municipio_nascimento",
                     "@uf_nascimento", "@naturalidade_cidade",
                     "@naturalidade_uf"):
        assert v[marcador] == " ", marcador


def test_a_linha_de_valores_so_escreve_o_que_o_selo_declara():
    """**RÓTULO SEM VALOR É RUÍDO NUM PAPEL ASSINADO.**

    A primeira versão escrevia os seis rótulos no molde, e o ensaio com um
    selo real do acervo saiu com «FADEP R$» e nada depois — aquele selo não
    declara FADEP. Medido: dos 39 textos de selo da casa, o FERC aparece em
    39, o FADEP em 38, o FEMP em 38 e o **FERRFIS em 4**; com rótulo fixo, a
    certidão traria um campo vazio em nove de cada dez.

    Zero também não serviria: `selo.ler_texto` devolve `None` para o que não
    achou, de propósito — afirmar zero de emolumento sobre ato oneroso é pior
    que não dizer.
    """
    # O CODIGO DO SELO TEM DE TER A FORMA REAL — `selo.ler_texto` exige de 20
    # a 40 caracteres, e com um `X` ele nao le nada. Boneco que nao passa pelo
    # leitor testa o teste, e nao o modulo.
    codigo = "BRCXXX00000037Z7UYDS1EOW8G07"
    # A FORMA E A DO SELO REAL DESTA CASA, medida no acervo: «Total R$ ...
    # Emol R$ ... FERC R$ ...». O boneco que eu escrevi antes usava
    # «Emolumentos: 40,69 FERC: 1,22», que o leitor nao entende — e um boneco
    # que nao passa pelo leitor testa o teste, e nao o modulo.
    completo = (f"Poder Judiciario - TJMA. Selo: {codigo}, "
                "30/07/2026 10:31:00, Ato: 14.6.6, Parte(s): FULANA DE TAL, "
                "Total R$ 44,76 Emol R$ 40,69 FERC R$ 1,22 FADEP R$ 0,81 "
                "FEMP R$ 1,63 FERRFIS R$ 0,41")
    v = ODT.valores({}, {"selos": [{"numero": codigo, "texto": completo}]}, {})
    linha = v["@selo1_valores"]
    for rotulo in ("Total R$", "Emol R$", "FERC R$", "FADEP R$", "FEMP R$",
                   "FERRFIS R$"):
        assert rotulo in linha, f"{rotulo} sumiu de um selo que o declara"

    sem_fadep = completo.replace("FADEP R$ 0,81 ", "")
    v2 = ODT.valores({}, {"selos": [{"numero": codigo, "texto": sem_fadep}]}, {})
    assert "FADEP" not in v2["@selo1_valores"], (
        "o rótulo do FADEP saiu num selo que não o declara")
    assert "FERC R$" in v2["@selo1_valores"], "os outros continuam saindo"


def test_sem_selo_a_linha_de_valores_nao_afirma_nada():
    v = ODT.valores({}, {}, {})
    assert v["@selo1_valores"].strip() == ""
    assert v["@selo2_valores"].strip() == ""


# ------------------------------------------------- a cor de letra


@tem_o_molde
def test_o_texto_do_molde_e_preto_como_o_da_certidao_real():
    x = conteudo()
    assert "#c00000" not in x, (
        "o vermelho voltou ao molde; a certidão real desta casa, no modelo "
        "nacional, é preta")
    assert 'fo:color="#000000"' in x


@tem_o_molde
def test_nenhum_estilo_se_chama_vermelho_pintando_preto():
    """Nome de estilo que mente é pior que estilo sem nome."""
    x = conteudo()
    assert "Vermelho" not in x, (
        "há estilo chamado «Vermelho» no molde — se ele pinta preto, o nome "
        "engana quem abrir o arquivo no LibreOffice")


# ------------------------------------------------- e o preenchimento roda


def test_valores_monta_os_genitores_sem_estourar_com_quadro_vazio():
    """O `get` com padrão não salva de `None`, e o molde é preenchido com o
    que vier do assento — que às vezes não tem genitor nenhum."""
    v = ODT.valores({}, {}, {})
    for n in ("1", "2"):
        for campo in ("nome", "municipio", "uf", "avos"):
            assert v[f"@genitor{n}_{campo}"] == " "


def test_valores_leva_cada_genitor_com_o_seu_municipio_e_os_seus_avos():
    quadro = {"genitores": [
        {"nome": "ELISA DE SOUSA MIRANDA", "municipio": "CIDADE EXEMPLO",
         "uf": "MA", "avos": "CLEMENTINO PEREIRA MARINHO; ISABEL DE SOUSA"},
        {"nome": "BERNARDINO MIRANDA RODRIGUES", "municipio": "GRAJAÚ",
         "uf": "MA", "avos": "PEDRO JOSÉ MIRANDA; MARIA RODRIGUES"}]}
    v = ODT.valores(quadro, {}, {})
    assert v["@genitor1_nome"] == "ELISA DE SOUSA MIRANDA"
    assert v["@genitor1_municipio"] == "CIDADE EXEMPLO"
    assert v["@genitor1_avos"].startswith("CLEMENTINO")
    assert v["@genitor2_nome"] == "BERNARDINO MIRANDA RODRIGUES"
    assert v["@genitor2_municipio"] == "GRAJAÚ"
    assert v["@genitor2_avos"].startswith("PEDRO")


def test_um_genitor_so_nao_inventa_o_segundo():
    """Assento com um genitor só é caso real, e o campo vazio não afirma
    nada — nome inventado no lugar afirmaria."""
    v = ODT.valores({"genitores": [{"nome": "MARIA", "municipio": "X",
                                    "uf": "MA", "avos": "A; B"}]}, {}, {})
    assert v["@genitor1_nome"] == "MARIA"
    assert v["@genitor2_nome"] == " "
    assert v["@genitor2_avos"] == " "


# ------------------------------------------------- um molde, uma espécie


@tem_o_molde
def test_o_molde_recusa_a_especie_que_ele_nao_serve():
    """**HÁ UM MOLDE SÓ, E AS TRÊS ESPÉCIES IMPRIMIAM NELE.**

    Achado em 01/09/2026 ao revisar as certidões: o título do molde é texto
    fixo — «CERTIDÃO DE NASCIMENTO» —, e não um marcador. Uma certidão de
    óbito saía com o cabeçalho de nascimento, com caixa de DNV e de gêmeos.
    O quadro monta os dados das três espécies certos; era o PAPEL que era de
    uma.

    **Papel que afirma a espécie errada é pior que papel nenhum** — campo
    vazio não afirma nada, cabeçalho errado afirma. É a regra do selo («não
    se sela por caminho que a casa nunca usou») aplicada ao papel.
    """
    # **AS ESPÉCIES RECUSADAS MUDARAM EM 01/09/2026**: casamento e óbito
    # ganharam molde próprio quando o oficial mandou aplicar as correções «nas
    # outras certidões de registro civil também». Ficam de fora o NATIMORTO —
    # cuja certidão não afirma nascimento com vida — e o Livro E, que registra
    # seis coisas diferentes entre si. Papel derivado no chute para elas é
    # exatamente o que esta guarda existe para impedir.
    #
    # **E MUDARAM DE NOVO NO LD01 (21/10/2026)**: o natimorto e o Livro E
    # ganharam molde PRÓPRIO — com as caixas do que o assento deles tem, e não
    # o de nascimento —, porque a 1ª certidão do natimorto é gratuita (LRP art.
    # 30) e não tinha o que imprimir (`test_fluxo_rcpn`). O que continua sem
    # papel é o que não tem certidão de breve relato própria: o proclama e o
    # «outro», que não se sabe o que registra.
    for especie in ("PROCLAMAS", "OUTRO"):
        with pytest.raises(ODT.MoldeError) as e:
            ODT.arquivo_da_certidao({"especie": especie}, {}, {})
        assert especie in str(e.value)
        assert "cabeçalho errado" in str(e.value)


@tem_o_molde
def test_o_nascimento_continua_saindo():
    """A recusa não pode fechar a porta que funciona."""
    b = ODT.arquivo_da_certidao({"especie": "NASCIMENTO", "nome": "MARIA"},
                                {}, {})
    assert b[:2] == b"PK" and len(b) > 10000


@tem_o_molde
def test_sem_especie_declarada_ele_nao_recusa():
    """Quadro sem espécie é o boneco de ensaio e o caso antigo; recusar aí
    faria a guarda alcançar quem ela não quer alcançar."""
    assert ODT.arquivo_da_certidao({}, {}, {})[:2] == b"PK"


@tem_o_molde
def test_a_recusa_diz_onde_o_teor_pode_ser_conferido():
    """Recusa sem saída manda o escrevente embora sem nada."""
    with pytest.raises(ODT.MoldeError) as e:
        ODT.arquivo_da_certidao({"especie": "OUTRO"}, {}, {})
    assert "ficha da certidão" in str(e.value)


# ------------------------------------------- tantas caixas quantos selos


SELO_REAL = ("Poder Judiciário - TJMA. Selo: BRCXXX00000037Z7UYDS1EOW8G07, "
             "30/07/2026 10:31:00, Ato: 14.6.6, Parte(s): FULANA DE TAL, "
             "Emolumentos: 40,69 FERC: 1,22 FEMP: 1,63 FERRFIS: 0,41 "
             "Total: 45,58")


def com_selos(quantos: int) -> dict:
    return {"selos": [{"numero": f"SELO{i}", "texto": SELO_REAL}
                      for i in range(1, quantos + 1)]}


def caixas_no_papel(quantos: int) -> int:
    """Quantas caixas de selo o papel traz, gerado de verdade."""
    from io import BytesIO
    bruto = ODT.arquivo_da_certidao({"especie": "NASCIMENTO"},
                                    com_selos(quantos), {})
    xml = zipfile.ZipFile(BytesIO(bruto)).read("content.xml").decode("utf-8")
    return xml[xml.find("<office:body"):].count("Poder Judici")


@tem_o_molde
def test_saem_tantas_caixas_quantos_selos():
    """**AS DUAS ESTAVAM DESENHADAS NO MOLDE, E SAÍAM SEMPRE** — o oficial em
    01/09/2026: *«controle para sair quantas caixas quanto os selos
    utilizados, ali tem duas sempre, permanentes»*.

    Com um selo, que é o caso normal desta casa (medido: a única certidão da
    produção tem um), o papel mostrava uma caixa preenchida e outra vazia, com
    «Selo:» e nada depois. Caixa vazia num papel assinado parece campo que
    ninguém preencheu.
    """
    assert caixas_no_papel(1) == 1
    assert caixas_no_papel(2) == 2


@tem_o_molde
def test_sem_selo_nenhum_nao_sai_caixa():
    """Ato sem selo existe nesta casa — aparece em `atos_sem_selo`. O papel
    simplesmente não traz o quadro: caixa vazia afirmaria menos que o
    silêncio."""
    assert caixas_no_papel(0) == 0


@tem_o_molde
def test_mais_selos_que_caixas_nao_estoura():
    """O molde tem duas vagas. Um terceiro selo não quebra o papel — e o
    módulo já só leva dois (`_selos_da_certidao`), de propósito: inventar uma
    caixa que não foi desenhada sairia torto na folha de segurança."""
    assert caixas_no_papel(3) == 2


@tem_o_molde
def test_podar_a_caixa_fecha_a_borda_da_direita():
    """As bordas pontilhadas estão repartidas entre as células: a primeira tem
    a da esquerda e a última a da direita. Cortando as de trás sem mais nada,
    **a caixa ficaria aberta do lado direito** — a última que sobra herda o
    estilo da última original."""
    xml = conteudo()
    ini = xml.find('<table:table table:name="Tabela11"')
    fim = xml.find("</table:table>", ini)
    estilos = re.findall(r'<table:table-cell table:style-name="([^"]+)"',
                         xml[ini:fim])
    assert len(estilos) == 4, "o molde deixou de ter duas células por selo"
    podado = ODT.caixas_do_selo(xml, 1)
    ini2 = podado.find('<table:table table:name="Tabela11"')
    fim2 = podado.find("</table:table>", ini2)
    ficaram = re.findall(r'<table:table-cell table:style-name="([^"]+)"',
                         podado[ini2:fim2])
    assert len(ficaram) == 2, "sobrou célula da caixa que saiu"
    assert ficaram[-1] == estilos[-1], (
        "a última célula não herdou o estilo que fecha a borda da direita")


@tem_o_molde
def test_podar_tira_a_coluna_junto_com_a_celula():
    """A tabela declara uma coluna por célula; sobrando declaração, o
    LibreOffice desenha coluna vazia depois do que ficou."""
    podado = ODT.caixas_do_selo(conteudo(), 1)
    ini = podado.find('<table:table table:name="Tabela11"')
    fim = podado.find("</table:table>", ini)
    bloco = podado[ini:fim]
    assert len(re.findall(r"<table:table-column[ >]", bloco)) == 2


# ------------------------------------------- a sigla canônica do fundo


def test_o_fundo_se_pede_pela_SIGLA_e_nao_pelo_sinonimo():
    """**O FADEP NUNCA CHEGOU A UMA CERTIDÃO DESTA CASA** — achado em
    01/09/2026, e é anterior a esta passada.

    `rc_certidao_odt` pedia `fundos.get("FADEP")`, e `FADEP` é **sinônimo**: a
    sigla da casa é `FADP` (Fundo de Aparelhamento da Defensoria Pública), e
    `selo.ler_texto` devolve sempre a canônica. Medido em **4.000 textos de
    selo do acervo**: o leitor produz `FADP` em 3.998 e `FADEP` em **zero**.

    O campo saía em branco em vez de estourar, e por isso ninguém viu. É a
    «mesma palavra em dois lugares» outra vez — agora entre sigla e sinônimo.
    """
    import atribuicoes as ATR
    for sigla in ODT._FUNDOS_DO_PAPEL:
        assert any(f["sigla"] == sigla for f in ATR.FUNDOS), (
            f"«{sigla}» não é sigla de fundo da casa — se for sinônimo, o "
            f"`selo.ler_texto` nunca vai devolvê-la")


def test_o_iss_nao_entra_no_papel():
    """O cadastro tem cinco fundos e só quatro são cobrados — conferido em 39
    selos reais, na tabela de preços e em 400 valores de 2026."""
    assert "ISS" not in ODT._FUNDOS_DO_PAPEL


def test_o_valor_do_fadep_chega_ao_papel():
    """O ensaio que prova o conserto: o selo declara, e a linha imprime."""
    codigo = "BRCXXX00000037Z7UYDS1EOW8G07"
    texto = (f"Poder Judiciario - TJMA. Selo: {codigo}, 30/07/2026 10:31:00, "
             "Ato: 14.6.6, Parte(s): FULANA, Total R$ 45,58 Emol R$ 40,69 "
             "FERC R$ 1,22 FADEP R$ 1,63 FEMP R$ 1,63 FERRFIS R$ 0,41")
    v = ODT.valores({}, {"selos": [{"numero": codigo, "texto": texto}]}, {})
    assert "FADEP R$ 1,63" in v["@selo1_valores"]
    assert v["@selo1_fadep"] == "1,63"
    assert v["@fadep"] == "1,63", "a soma geral também lia o sinônimo"


# ------------------------------------------- as três espécies, cada uma no seu


@tem_o_molde
def test_cada_especie_sai_no_molde_dela():
    """**ATÉ 01/09/2026 HAVIA UM MOLDE SÓ, e as outras duas não imprimiam
    nada.** O oficial mandou aplicar as correções «nas outras certidões de
    registro civil também»; `tools/moldes_do_civil.py` as derivou do de
    nascimento — mesma geometria, mesmas cores, mesmas caixas de selo.

    **O título é texto fixo no molde**, e era ele que fazia uma certidão de
    óbito sair com o cabeçalho de nascimento. Este teste confere o título de
    cada papel gerado, e não a lista de espécies servidas: lista se escreve,
    papel se abre.
    """
    import re
    import zipfile
    from io import BytesIO
    esperado = {"NASCIMENTO": "CERTIDÃO DE NASCIMENTO",
                "CASAMENTO": "CERTIDÃO DE CASAMENTO",
                "OBITO": "CERTIDÃO DE ÓBITO"}
    for especie, titulo in esperado.items():
        molde = ODT.molde_da_especie(especie)
        if not molde.exists():
            pytest.skip(f"molde de {especie} ainda não gerado")
        bruto = ODT.arquivo_da_certidao({"especie": especie}, {}, {})
        xml = zipfile.ZipFile(BytesIO(bruto)).read("content.xml").decode("utf-8")
        texto = re.sub(r"<[^>]+>", "", xml)
        assert titulo in texto, f"o papel de {especie} não diz «{titulo}»"
        for outro in esperado.values():
            if outro != titulo:
                assert outro not in texto, (
                    f"o papel de {especie} também diz «{outro}» — cabeçalho "
                    f"que afirma a espécie errada é pior que papel nenhum")


@tem_o_molde
def test_nenhum_molde_deixa_marcador_cru_no_papel():
    """**`@` NO MOLDE QUE O CÓDIGO NÃO PREENCHE SAI IMPRESSO** numa certidão
    assinada. O guarda já existia para o de nascimento; ao nascerem mais dois
    moldes ele passa a valer para os três — senão o defeito só apareceria no
    papel novo, que é justamente o menos conferido."""
    import re
    import zipfile
    from io import BytesIO
    # Os cinco moldes desde o LD01 (natimorto e Livro E), pela lista das
    # espécies — molde novo entra na varredura sozinho.
    for especie in sorted(ODT.MOLDE_DA_ESPECIE):
        if not ODT.molde_da_especie(especie).exists():
            continue
        bruto = ODT.arquivo_da_certidao({"especie": especie}, {}, {})
        xml = zipfile.ZipFile(BytesIO(bruto)).read("content.xml").decode("utf-8")
        crus = sorted(set(re.findall(r"@[a-z0-9_]+", re.sub(r"<[^>]+>", "", xml))))
        assert not crus, f"{especie}: marcadores sem valor no papel: {crus}"


@tem_o_molde
def test_nenhum_dos_TRES_moldes_tem_valor_aninhado():
    """**O VARREDOR DA FONTE OLHAVA DOIS MOLDES, E ERAM TRÊS — 10/09/2026.**

    O defeito da fonte (item 6, acima) foi medido e consertado em 09/09 no
    molde de nascimento, e o de casamento ganhou o guarda dele no arquivo
    vizinho. **O de óbito não tinha guarda nenhum** — e por isso os **20 pares
    aninhados** dele sobreviveram: conferido no PDF, o nome da serventia, a
    data e o nome de quem assina saíam em Calibri ao lado dos rótulos em
    Times.

    Achado ao CONFERIR o trabalho do dia, e não ao construí-lo: renderizei o
    molde de óbito só para ver se eu não o tinha quebrado. **Varredor que
    olha uma parte do problema deixa a outra crescer calada** — é a lição da
    lista escrita à mão, pela enésima vez, agora dentro do teste.

    E ele varre pela ESPÉCIE, e não por uma lista de arquivos: molde novo
    entra na varredura sozinho.
    """
    for especie in ODT.MOLDE_DA_ESPECIE:
        molde = ODT.molde_da_especie(especie)
        if not molde.exists():
            continue
        xml = zipfile.ZipFile(molde).read("content.xml").decode("utf-8")
        aninhados = re.findall(
            r'<text:span text:style-name="T\d+"><text:span '
            r'text:style-name="TValor(?:Negrito)?">', xml)
        assert not aninhados, (
            f"{especie} ({molde.name}): {len(aninhados)} valor(es) aninhados "
            "dentro do estilo do rótulo — o defeito da fonte errada. Tire o "
            "aninhamento: o estilo do rótulo vai direto no marcador.")


@tem_o_molde
def test_o_rodape_do_anexo_esta_nos_TRES_moldes():
    """**O RODAPÉ APROVADO VALE PARA AS TRÊS ESPÉCIES** — o Anexo IV, o V e o
    VI têm o mesmo pé de folha.

    O de óbito ficou com o rodapé antigo até 10/09/2026: trazia os seis campos
    que o oficial mandou tirar em 09/09 («tira o que nao consta no modelo do
    cnj») e o `@linha_assinatura`. Ele não apareceu no relato porque **a casa
    nunca emitiu certidão de óbito** — 18 de nascimento e 4 de casamento, e
    zero de óbito, com 31 assentos de óbito no sistema esperando a primeira.
    """
    for especie in ODT.MOLDE_DA_ESPECIE:
        molde = ODT.molde_da_especie(especie)
        if not molde.exists():
            continue
        xml = zipfile.ZipFile(molde).read("content.xml").decode("utf-8")
        texto = re.sub(r"<[^>]+>", " ", xml[xml.find("<office:body"):])
        quem = f"{especie} ({molde.name})"
        assert "TabelaRodape" in xml, f"{quem}: sem o rodapé de duas colunas"
        for saiu in ("COMARCA DE", "@unit_name", "@serventia_email",
                     "@serventia_telefone", "@serventia_cnpj",
                     "@ri_substituta", "@linha_assinatura", "(assinatura)"):
            assert saiu not in texto, f"{quem}: «{saiu}» não está no Anexo"
        # **OS DOIS CARGOS, um por coluna** — ver
        # `test_o_cargo_do_delegatario_nao_e_o_de_quem_assina_a_via`.
        assert texto.count("@funcaoregistrador") == 1, quem
        assert texto.count("@funcaoescrevente") == 1, quem


@tem_o_molde
def test_a_matricula_esta_nos_tres_moldes():
    """**ELA QUASE SE PERDEU NOS DOIS NOVOS.** No molde de nascimento o bloco
    da matrícula vem depois do CPF, e o corte que gerou os outros dois a levou
    junto na primeira tentativa. A matrícula de 32 dígitos é a identidade
    nacional da certidão — sem ela o papel não serve, e a falta só apareceria
    quando alguém fosse conferir o registro noutra serventia."""
    import re
    import zipfile
    # Os cinco moldes desde o LD01 (natimorto e Livro E), pela lista das
    # espécies — molde novo entra na varredura sozinho.
    for especie in sorted(ODT.MOLDE_DA_ESPECIE):
        molde = ODT.molde_da_especie(especie)
        if not molde.exists():
            continue
        xml = zipfile.ZipFile(molde).read("content.xml").decode("utf-8")
        texto = re.sub(r"<[^>]+>", "", xml)
        assert "MATRÍCULA" in texto, f"{especie}: o molde não tem a matrícula"


# ------------------------------------------- a filiação do casamento


def test_a_filiacao_generica_nao_alcanca_o_segundo_conjuge():
    """**A CERTIDÃO SAÍA DIZENDO QUE O CASAL É IRMÃO** — achado em 01/09/2026
    no ensaio contra a produção, ao gerar a primeira certidão de casamento no
    molde novo.

    A produção não tem **uma única** pessoa com papel `PAI_NUBENTE1` ou
    `MAE_NUBENTE2`: só `PAI` e `MAE` genéricos, 12 de cada em 20 casamentos. O
    quadro recorria a eles para os DOIS cônjuges, e o papel saía com a mesma
    filiação nas duas colunas.

    De quem são os genéricos, decidido pelos sobrenomes nos 20 casamentos da
    casa: **NUBENTE 1 em 10, NUBENTE 2 em ZERO**.

    Para o segundo, campo em branco: **campo vazio não afirma nada, e a
    filiação errada afirma** — a mesma regra que decidiu o cabeçalho da
    espécie e a linha de valores do selo.
    """
    import rc_certidao_quadro as RCQ
    quem = {
        "NUBENTE1": {"nome": "NELSON FALCAO BARROS"},
        "NUBENTE2": {"nome": "EDNA SERRA MONTEIRO"},
        "PAI": {"nome": "JULIA RODRIGUES BARROS"},
        "MAE": {"nome": "RUBENS FALCAO DE TORRES"},
    }
    q = RCQ._quadro_casamento({}, quem, {}, "", {})
    conj = q["conjuges"]
    assert len(conj) == 2
    assert "JULIA RODRIGUES" in conj[0]["genitores"], (
        "o primeiro cônjuge fica com os pais genéricos — é dele que eles são")
    assert conj[1]["genitores"] == "", (
        "o segundo cônjuge NÃO herda os pais do primeiro: sairia uma certidão "
        "afirmando que o casal é irmão")


def test_a_filiacao_propria_de_cada_conjuge_manda(): 
    """Quando o assento tem os pais de cada um, é isso que sai — o recurso aos
    genéricos é só a falta."""
    import rc_certidao_quadro as RCQ
    quem = {
        "NUBENTE1": {"nome": "A"}, "NUBENTE2": {"nome": "B"},
        "PAI_NUBENTE1": {"nome": "PAI DE A"}, "MAE_NUBENTE1": {"nome": "MÃE DE A"},
        "PAI_NUBENTE2": {"nome": "PAI DE B"}, "MAE_NUBENTE2": {"nome": "MÃE DE B"},
        "PAI": {"nome": "NÃO USAR"}, "MAE": {"nome": "NÃO USAR"},
    }
    conj = RCQ._quadro_casamento({}, quem, {}, "", {})["conjuges"]
    assert "PAI DE A" in conj[0]["genitores"] and "NÃO USAR" not in conj[0]["genitores"]
    assert "PAI DE B" in conj[1]["genitores"] and "NÃO USAR" not in conj[1]["genitores"]


@tem_o_molde
def test_o_natimorto_e_o_livro_e_saem_no_papel_deles_com_o_titulo_da_especie():
    """LD01 (21/10/2026): o natimorto e as seis espécies do Livro E não tinham
    papel. O do natimorto diz «CERTIDÃO DE NATIMORTO» e não afirma nascimento;
    o do Livro E é um para as seis, e o título é o da espécie, vindo do quadro
    (`rc_certidao.titulo_do_modelo`) — um papel de interdição que dissesse
    «CERTIDÃO» e mais nada é o defeito que o lote consertou."""
    import re
    import zipfile
    from io import BytesIO

    def texto(quadro):
        bruto = ODT.arquivo_da_certidao(quadro, {}, {})
        xml = zipfile.ZipFile(BytesIO(bruto)).read("content.xml").decode("utf-8")
        return re.sub(r"<[^>]+>", " ", xml)

    nati = texto({"especie": "NATIMORTO", "nome": "NATIMORTO DE EXEMPLO",
                  "numero_do": "11112222"})
    assert "CERTIDÃO DE NATIMORTO" in nati and "11112222" in nati
    assert "CERTIDÃO DE NASCIMENTO" not in nati
    assert "NASCIDO VIVO" not in nati
    inter = texto({"especie": "INTERDICAO", "nome": "PEDRO EXEMPLO",
                   "titulo_livro_e": "CERTIDÃO DE INTERDIÇÃO",
                   "livro_e_especie": "Interdição",
                   "livro_e_titulo": "Sentença proferida em exemplo",
                   "livro_e_indicacoes": "CURADOR(A): BEATRIZ EXEMPLO"})
    for esperado in ("CERTIDÃO DE INTERDIÇÃO", "Interdição",
                     "Sentença proferida em exemplo",
                     "CURADOR(A): BEATRIZ EXEMPLO"):
        assert esperado in inter, esperado
    assert "CERTIDÃO DE NASCIMENTO" not in inter


def test_a_lista_de_especies_servidas_e_a_dos_moldes_concordam():
    """**DUAS LISTAS QUE PRECISAM CONCORDAR SÃO O DEFEITO CLÁSSICO DESTA
    CASA.** `ESPECIES_QUE_O_MOLDE_SERVE` diz o que passa pela guarda;
    `MOLDE_DA_ESPECIE` diz em que arquivo cada uma imprime. Divergindo, a
    guarda deixaria passar uma espécie que cairia no molde de nascimento — e
    sairia um papel com o cabeçalho errado, que é exatamente o que ela existe
    para impedir.

    É a lição da lista das cargas (`TITULO_DA_CARGA`) e a do menu: lista
    escrita à mão noutro lugar envelhece na tarde em que se escreve.
    """
    servidas = set(ODT.ESPECIES_QUE_O_MOLDE_SERVE)
    com_molde = set(ODT.MOLDE_DA_ESPECIE)
    assert servidas == com_molde, (
        f"servidas mas sem molde: {sorted(servidas - com_molde)}; "
        f"com molde mas recusadas: {sorted(com_molde - servidas)}")
    for especie in servidas:
        assert ODT.molde_da_especie(especie).exists(), (
            f"{especie} passa pela guarda e o arquivo do molde não existe — "
            f"o balcão levaria um erro no lugar do papel")
