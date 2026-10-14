"""Os modelos do livro — um por ato, e o formulário que sai deles.

O QUE ESTES TESTES GUARDAM
    **Que os campos do formulário saem do PRÓPRIO modelo.** Duas listas — uma na
    tela e outra no texto — divergem no primeiro conserto, e a tela passaria a
    perguntar uma coisa e o texto a esperar outra. É a lição da
    `normalizar_nome`, aplicada ao formulário.

    **Que cada modelo diz se é medido ou montado.** O de nascimento é o texto do
    termo nº 8.369 desta casa; os outros dois são montados dos requisitos, e
    dizem isso. Apresentar como precedente o que não é precedente seria a
    «etiqueta que afirma medição sem ter medido».

    **Que claro em branco não some: fica marcado.** Substituí-lo por vazio faria
    a frase perder o sentido sem dizer por quê.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import rc_folha as F                                             # noqa: E402
import rc_modelos_do_livro as M                                  # noqa: E402


# ------------------------------------------------ a folha


def test_a_folha_e_retrato():
    """215 × 279 mm — carta em pé. O #38 mandou paisagem e a impressão
    saiu errada; o oficial, 01/09/2026, mandou retrato. Não é A4 deitado."""
    assert F.ORIENTACAO == "retrato"
    assert F.LARGURA_MM < F.ALTURA_MM
    assert F.LARGURA_MM == pytest.approx(215.0)
    assert F.ALTURA_MM == pytest.approx(279.0)


def test_sao_tres_colunas_e_elas_fecham():
    """Largura que não fecha é coluna que invade a outra — no papel, o texto do
    termo entrando na margem das averbações."""
    assert len(F.COLUNAS) == 3
    assert F.somam_um()
    assert F.CHAVES == ("NUMERO", "TERMO", "NOTAS")


def test_cada_coluna_diz_o_que_leva_e_por_que():
    for c in F.COLUNAS:
        assert c["o_que_leva"], f"{c['chave']} não diz o que leva"
        assert c["por_que"], f"{c['chave']} não diz por quê"


def test_a_terceira_coluna_e_a_divisao_tripartite():
    """Ela está desenhada no papel desde sempre — e é o que a inspeção cobra.

    **E ESTE TESTE FIXAVA UMA PALAVRA, e por isso ficou vermelho com o papel
    certo.** Ele exigia «tripartite» dentro do `por_que`, e o oficial mandou
    apertar a primeira coluna em 01/09/2026; ao refazer as três, o `por_que`
    passou a explicar a decisão do desenho — «é o campo próprio da margem —
    um só, não três caixas» — e a palavra saiu.

    **As duas coisas são verdade ao mesmo tempo, e não se contradizem**: os
    ATOS continuam três (averbação, anotação e retificação, que `rc_assento`
    modela e a inspeção cobra), e o LUGAR deles na folha é uma margem só. É a
    lição do regex do menu outra vez: teste que fixa a palavra exata reprova
    mudança legítima. O que ele guarda agora é a divisão pelo **título da
    coluna**, que é onde ela aparece para quem lê o livro.
    """
    notas = F.coluna("NOTAS")
    assert notas["titulo"] == "Notas, Averbações e Retificações"
    for parte in ("Averbações", "Retificações"):
        assert parte in notas["titulo"]
    # E o `por_que` continua tendo de dizer alguma coisa — o teste de cima
    # (`cada_coluna_diz_o_que_leva_e_por_que`) é quem guarda isso.
    assert notas["por_que"].strip()


# ------------------------------------------------ a exigência tem endereço


def test_a_exigencia_e_da_inspecao_e_nao_da_lei_generica():
    """Eu tinha escrito que a citação ficava A CONFERIR, e o oficial apontou o
    lugar: o relatório da COGEX. **Não achar a regra onde procurei não prova que
    ela não existe — prova que procurei no lugar errado.**"""
    assert "Inspeção" in F.EXIGENCIA["fonte"]
    assert "12/08/2026" in F.EXIGENCIA["fonte"]
    assert F.EXIGENCIA["prazo_dias"] == 30


def test_sao_quatro_livros_cobrados_e_nao_um():
    """Quem consertasse só o A-24 deixaria três exigências abertas."""
    livros = [x["livro"] for x in F.LIVROS_COBRADOS]
    assert livros == ["A-24", "B-04", "C-05", "D-03"]


def test_o_verso_tambem_leva_a_coluna_de_notas():
    """Está na letra da exigência do A-24 e do B-04: «inclusive no verso das
    folhas». Folha cujo verso não tem a margem é folha em que a averbação não
    cabe — e a averbação vem depois."""
    assert F.A_COLUNA_DE_NOTAS_VAI_NOS_DOIS_LADOS
    assert "verso" in F.EXIGENCIA["texto"]
    assert any(x["no_verso"] for x in F.LIVROS_COBRADOS)


def test_a_face_impar_e_frente_e_a_par_e_verso():
    """Inverter faria o termo sair no lado errado do papel — e quem imprime
    frente e verso não descobre o engano até a folha estar no livro."""
    assert F.face_da(1) == "FRENTE"
    assert F.face_da(2) == "VERSO"
    assert F.face_da(3) == "FRENTE"
    assert F.folha_da(1) == 1
    assert F.folha_da(2) == 1
    assert F.folha_da(3) == 2


def test_face_zero_recusa():
    for ruim in (0, -1, None, "abc"):
        with pytest.raises(F.FolhaError):
            F.face_da(ruim)


# ------------------------------------------------ os modelos


def test_ha_um_modelo_por_ato():
    """**A LISTA CRESCEU, E ESTE TESTE FICOU COBRANDO A DE TRÊS.**

    Até 07/09/2026 eram três modelos — nascimento, casamento e óbito —, e o
    oficial mandou que o **Livro E inteiro usasse um modelo só** («livro e usa
    o mesmo modelo»). O `CHAVES` passou a ter quatro, e a expectativa escrita
    aqui à mão continuou com três: **teste que afirma o contrato antigo é pior
    que teste nenhum**, porque quem o lê conclui que o sistema regrediu.

    O que ele guarda, e que continua valendo: **um modelo por ato, e cada um
    com texto, campos, livro e artigo** — modelo sem livro é termo sem lugar no
    papel.
    """
    assert M.CHAVES == ("NASCIMENTO", "CASAMENTO", "OBITO", "LIVRO_E")
    for c in M.CHAVES:
        m = M.modelo(c)
        assert m["texto"] and m["campos"] and m["livro"] and m["artigo"]


def test_todo_modelo_diz_de_que_norma_saiu():
    """**MUDOU EM 30/08/2026, POR ORDEM DO OFICIAL:**

        «vamos construir os nossos com os requisitos legais e regulamentares,
         nao utilizaremos os modelos ruins do e-oficio, nem em papel»

    Ate esse dia eu tratava «montado dos requisitos» como defeito a confessar —
    a tela dizia que o casamento e o obito «nao sao precedente desta casa»,
    como quem pede desculpa. **Montar dos requisitos passou a ser o
    objetivo**, e o que cada modelo tem de dizer e de QUE NORMA saiu.

    **E O LIVRO E DIZ OUTRA COISA, PORQUE A ORIGEM DELE É OUTRA.** O texto dele
    não saiu de requisitos: saiu de uma **ordem do oficial** («livro e usa o
    mesmo modelo», 07/09/2026). Inventar uma citação de incisos para ele seria
    a etiqueta que afirma medição sem ter medido — o que a regra pede é que o
    modelo **declare de onde veio**, e é isso que este teste cobra.
    """
    for c in M.CHAVES:
        m = M.modelo(c)
        assert m["artigo"], f"{c} nao diz o artigo"
        de_onde = m["fonte"]
        assert ("requisitos" in de_onde or "incisos" in de_onde
                or "ordem do oficial" in de_onde), (
            f"{c} nao diz de onde o texto saiu: {de_onde}")


def test_o_papel_serve_de_conferencia_e_nao_de_fonte():
    """O termo nº 8.369 continua util — foi nele que se mediu a ordem dos
    gemeos e a idade da genitora —, mas **nao manda no texto**."""
    assert M.modelo("NASCIMENTO")["conferido_no_papel"] is True
    assert "8.369" in M.modelo("NASCIMENTO")["fonte"]
    assert "conferência" in M.modelo("NASCIMENTO")["fonte"]
    for c in ("CASAMENTO", "OBITO"):
        assert M.modelo(c)["conferido_no_papel"] is False


def test_o_obito_cobre_os_doze_incisos_do_art_255():
    """Cada inciso do art. 255 tem de ter onde entrar no termo. Faltar um
    significa lavrar assento sem elemento que a norma lista."""
    artigos = " ".join(c.get("artigo", "") for c in M.campos_do("OBITO"))
    for inciso in ("I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX",
                   "X", "XI", "XII"):
        assert f"255, {inciso}" in artigos, f"falta o inciso {inciso}"


def test_o_obito_declara_o_que_o_declarante_ignorava():
    """**E a parte mais interessante do art. 255.** O § 1º manda o oficial
    «declarar, no corpo do registro, que fez a pergunta e que o declarante
    ignorava» os dados que faltam — o contrario de deixar campo em branco.

    E a base normativa da diferenca entre «nao» e «nao perguntei» que
    `rc_marcas_do_obito` guarda: ela nao foi escolha de desenho.
    """
    campos = {c["nome"]: c for c in M.campos_do("OBITO")}
    assert "frase_ignorados" in campos
    assert "§ 1" in campos["frase_ignorados"]["artigo"]
    assert "ignorava" in campos["frase_ignorados"]["ajuda"]


def test_a_DO_exigida_sempre_esta_marcada_como_regra_da_casa():
    """O art. 254 admitiria duas pessoas qualificadas onde nao houvesse
    medico. Esta casa exige a DO sempre — e isso e escolha, nao lei."""
    campos = {c["nome"]: c for c in M.campos_do("OBITO")}
    d = campos["frase_declaracao_de_obito"]
    assert "esta casa" in d["ajuda"]
    assert "254" in d["ajuda"]


def test_o_texto_do_nascimento_traz_as_frases_do_livro():
    """Duas delas confirmam o que se construiu em 29 e 30/08: a ordem dos gêmeos
    e a idade da genitora no parto."""
    campos = {c["nome"] for c in M.campos_do("NASCIMENTO")}
    assert "frase_gemeos" in campos
    assert "frase_idade_da_genitora" in campos


def test_a_idade_da_genitora_nao_se_calcula():
    """Calcular onde a data de nascimento da mãe falta daria idade errada num
    papel assinado."""
    c = [x for x in M.campos_do("NASCIMENTO")
         if x["nome"] == "frase_idade_da_genitora"][0]
    assert "não calculado" in c["de_onde"]


def test_o_casamento_diz_o_que_aconteceu_com_os_nomes():
    """**É o motivo pelo qual a certidão de casamento existe** — e o segundo
    cônjuge muda de nome em 17 dos 20 casamentos desta casa.

    Ate 30/08/2026 o campo se chamava `nome_apos_casamento` e a frase do termo
    afirmava sempre «Passou o conjuge X a assinar-se Y» — com ninguem mudando,
    ela saia com o claro no meio de uma afirmacao. O oficial pediu: «se ninguem
    mudou o nome, fala que ambos mantem os mesmos nomes».

    **O silencio nao e opcao**, e por isso o campo e exigido: nao dizer nada
    sobre o nome e pior que dizer que ele nao mudou.
    """
    campos = {c["nome"]: c for c in M.campos_do("CASAMENTO")}
    assert "frase_dos_nomes" in campos
    assert campos["frase_dos_nomes"]["exigido"], (
        "a frase dos nomes tem de ser exigida — o silencio nao e opcao")
    assert "regime_bens" in campos


def test_o_casamento_relaciona_os_documentos_apresentados():
    """Pedido do oficial: «apresentar relacao dos documentos apresentados».

    O termo dizia «apresentando os documentos exigidos em lei», generico —
    **quem confere um casamento anos depois precisa saber QUAIS**.
    """
    campos = {c["nome"]: c for c in M.campos_do("CASAMENTO")}
    assert "documentos_apresentados" in campos
    assert campos["documentos_apresentados"]["exigido"]
    assert "os documentos exigidos em lei" not in M.TERMO_CASAMENTO, (
        "o termo voltou a dizer «os documentos exigidos em lei» em vez de "
        "relaciona-los")


def test_o_casamento_tem_as_duas_filiacoes():
    """São quatro pessoas, e o sistema já leu duas por engano uma vez."""
    campos = {c["nome"] for c in M.campos_do("CASAMENTO")}
    assert {"filiacao1", "filiacao2"} <= campos


def test_modelo_que_nao_existe_recusa():
    with pytest.raises(M.ModeloError):
        M.modelo("INVENTADO")


# ------------------------------------------------ o guarda das duas listas


def test_os_claros_e_os_campos_batem_em_todos():
    """**É O GUARDA QUE IMPEDE AS DUAS LISTAS DE DIVERGIREM.** Claro no texto sem
    campo sai como chave literal no papel assinado; campo sem claro é pergunta
    que não vai a lugar nenhum. Os dois enganam quem preenche."""
    for c in M.CHAVES:
        assert M.conferir(c) == [], f"{c}: {M.conferir(c)}"


def test_todo_campo_tem_rotulo():
    for c in M.CHAVES:
        for campo in M.campos_do(c):
            assert campo["rotulo"], f"{c}.{campo['nome']} sem rótulo"


def test_os_claros_saem_na_ordem_do_texto():
    claros = M.claros_do_texto("Em {a}, com {b} e de novo {a}.")
    assert claros == ("a", "b")


# ------------------------------------------------ montar do formulário


def test_montar_com_tudo_preenchido():
    valores = {c["nome"]: f"«{c['nome']}»" for c in M.campos_do("OBITO")}
    r = M.montar_do_formulario("OBITO", valores)
    assert r["completo"]
    assert r["em_branco"] == []
    assert "{" not in r["texto"]


def test_claro_em_branco_fica_marcado_e_nao_some():
    """Substituí-lo por vazio faria a frase perder o sentido sem dizer por quê.
    Ele vira o traço que o livro de papel tem, e a tela lista quais são.

    **E A CONTA MUDOU EM 31/08/2026, com o defeito que ela escondia.** Antes,
    `em_branco` juntava os campos **exigidos** vazios com as frases
    **ocasionais** que simplesmente não se aplicam — e como metade do óbito é
    frase ocasional, um óbito comum saía marcado INCOMPLETO com dez linhas de
    aviso. Alarme que soa sempre é alarme que ninguém ouve.

    O traço já distinguia os dois casos; a conta é que não distinguia.
    """
    r = M.montar_do_formulario("NASCIMENTO", {"nome": "MARIA"})
    assert "____________" in r["texto"]
    assert not r["completo"]
    exigidos = [c for c in M.campos_do("NASCIMENTO") if c.get("exigido")]
    # menos um: o `nome`, que foi preenchido
    assert len(r["em_branco"]) == len(exigidos) - 1
    # e as frases ocasionais estao na OUTRA lista, e nao sumiram
    ocasionais = [c for c in M.campos_do("NASCIMENTO") if not c.get("exigido")]
    assert len(r["nao_e_o_caso"]) == len(ocasionais)


def test_o_que_foi_preenchido_aparece():
    r = M.montar_do_formulario("NASCIMENTO", {"nome": "MARIA ÍSIS"})
    assert "MARIA ÍSIS" in r["texto"]


# ------------------------------------------------- texto corrido, sem claros
#
# «o corpo de todos os atos do cartorio eh texto corrido, sem espacos» — o
# oficial, 07/09/2026. `TERMO_NASCIMENTO` já não tinha quebra de linha real
# (todo `\n` do código-fonte tem `\` de continuação); `TERMO_CASAMENTO` e
# `TERMO_OBITO` tinham — seis e sete pontos, por faltar esse `\` —, e o texto
# ia com a quebra real para `rc_assentos.teor`, o próprio Livro do Registro
# Civil. `limpar()` agora colapsa toda quebra, e não só a linha em branco.

def test_nenhum_modelo_cru_tem_quebra_de_linha():
    for c in M.CHAVES:
        assert "\n" not in M.modelo(c)["texto"], c


def test_o_texto_montado_nao_tem_quebra_de_linha_nem_espaco_duplo():
    import re
    for c in M.CHAVES:
        valores = {campo["nome"]: f"valor de {campo['nome']}"
                  for campo in M.campos_do(c)}
        r = M.montar_do_formulario(c, valores)
        assert "\n" not in r["texto"], c
        assert "  " not in r["texto"], c
        assert not re.search(r"\s[,.;:]", r["texto"]), c


def test_montar_nao_grava_nada():
    """Quem congela o termo é `rc_termo.congelar`, e ele o faz uma vez só."""
    codigo = (RAIZ / "rc_modelos_do_livro.py").read_text(encoding="utf-8")
    for proibido in ("INSERT INTO", "UPDATE ", "DELETE FROM", "sqlite3"):
        assert proibido not in codigo, f"o módulo escreve com «{proibido}»"


def test_o_cabecalho_do_eoficio_nao_vazou():
    """Dois dos treze modelos trazem a oficial ANTERIOR — o «carimbo que mente»."""
    codigo = (RAIZ / "rc_modelos_do_livro.py").read_text(encoding="utf-8")
    for vazado in ("ANA CRISTINA", "MURAI", "98472-0370"):
        assert vazado not in codigo


# ------------------------------------------------ os tipos de teor
#
# APRENDIDO NOS PRINTS DO E-OFICIO EM 30/08/2026: a aba «Teor» da tela de
# lavratura nao e um texto, e um combo «Tipo de Teor» mais um botao. Um ato tem
# VARIOS teores, e nao um — que era como eu tinha escrito no dia anterior.


def test_um_ato_tem_varios_teores():
    """O nascimento tem quatro, e nao um. Escrever «um modelo por ato» era o
    erro de premissa que os prints corrigiram."""
    nasc = M.tipos_do_ato("NASCIMENTO")
    assert len(nasc) >= 4
    assert {t["tipo"] for t in nasc} >= {"COMUM", "TARDIO", "GEMEOS"}


def test_a_lista_traz_o_que_falta_e_nao_so_o_que_ha():
    """**Uma lista so com os prontos faria a tela dizer que o nascimento tem um
    teor, quando ele tem quatro e nos temos um.** Quem abre precisa saber o
    tamanho do que falta."""
    nasc = M.tipos_do_ato("NASCIMENTO")
    prontos = [t for t in nasc if M.tem_texto(t)]
    faltando = [t for t in nasc if not M.tem_texto(t)]
    assert len(prontos) == 1, "so o teor comum foi medido ate agora"
    assert faltando, "a lista tem de mostrar os que faltam"


def test_todo_teor_que_falta_diz_por_que_falta():
    """Buraco sem motivo escrito vira buraco esquecido — e, pior, alguem
    inventa o texto para tapa-lo."""
    for t in M.TIPOS_DE_TEOR:
        if not M.tem_texto(t):
            assert t.get("porque_falta"), f"{t['nome']} nao diz por que falta"


def test_todo_teor_diz_quando_se_usa():
    for t in M.TIPOS_DE_TEOR:
        assert t.get("quando"), f"{t['nome']} nao diz quando se usa"


def test_o_teor_pronto_aponta_para_um_modelo_que_existe():
    """Chave preenchida que nao acha modelo seria a tela oferecendo montar um
    texto que nao ha."""
    for t in M.TIPOS_DE_TEOR:
        if M.tem_texto(t):
            assert M.modelo(t["chave"])["texto"]


def test_a_conta_dos_teores_nunca_e_escrita_a_mao():
    """O numero sai da soma. Escrito a mao, ele mente no dia em que a tabela
    crescer — foi o defeito do menu e o do carimbo da versao.

    **E A CONTA PEGOU UM BURACO DE VERDADE, EM 15/09/2026.** Ela exige que todo
    modelo do catálogo tenha o seu teor na lista — e o `LIVRO_E`, que entrou em
    07/09/2026, **nao estava em `TIPOS_DE_TEOR`**: a tela contava 3 prontos
    onde havia 4, e o termo do Livro E nao aparecia em lista nenhuma. Nao era o
    numero que estava errado: era a lista.
    """
    c = M.quantos_teores_faltam()
    assert c["total"] == len(M.TIPOS_DE_TEOR)
    assert c["prontos"] + c["faltam"] == c["total"]
    assert c["prontos"] == len(M.CHAVES)


def test_o_natimorto_e_ato_proprio_e_nao_especie_de_nascimento():
    """Livro C-Auxiliar, tipo 5 na matricula. Enfia-lo no nascimento faria o
    numero nacional do assento sair errado."""
    assert "NATIMORTO" in M.ESPECIES
    nat = M.tipos_do_ato("NATIMORTO")
    assert "C-Auxiliar" in nat[0]["porque_falta"]


def test_ato_que_nao_existe_recusa_dizendo_os_que_existem():
    with pytest.raises(M.ModeloError) as e:
        M.tipos_do_ato("INVENTADO")
    assert "NASCIMENTO" in str(e.value)


# ------------------------------------------ o termo montado DO ASSENTO
#
# ATE 30/08/2026 O MODELO SO SE PREENCHIA A MAO. O escrevente lavrava o assento
# com filiacao, avos, declarante e hora — e depois **redigitava tudo** na tela
# de teores para ver o termo. **Dado digitado duas vezes diverge na segunda.**


ASSENTO = {"nome": "PAULO HENRIQUE BARROS ALMEIDA", "hora_fato": "18:04",
           "local_fato_nome": "MATERNIDADE DE ALTO RISCO",
           "data_ato": "2026-08-19", "data_fato": "2026-08-08",
           "cor_raca": "PARDA", "dnv": "30942697008"}
PESSOAS = [
    {"papel": "REGISTRADO", "nome": "PAULO HENRIQUE", "sexo": "M"},
    {"papel": "PAI", "nome": "BALTAZAR SOARES DA SILVA"},
    {"papel": "MAE", "nome": "ADA BARROS ALMEIDA", "idade_no_fato": "29"},
    {"papel": "AVO_PATERNO", "nome": "JOSE SOARES"},
    {"papel": "AVO_MATERNA", "nome": "MARIA AMARAL BARROS DA SILVA"},
    {"papel": "DECLARANTE", "nome": "JOAO BATISTA ALMEIDA SILVA",
     "profissao": "lavrador", "cidade": "Cidade Exemplo", "uf": "MA"},
]


def _sem_negrito(texto: str) -> str:
    """O termo como ele se lê, sem as marcas de negrito do papel."""
    return texto.replace("<strong>", "").replace("</strong>", "")


def test_o_termo_se_monta_do_assento():
    r = M.montar_do_assento(ASSENTO, PESSOAS,
                            sv={"ri_cidade": "Cidade Exemplo", "ri_uf": "MA"})
    t = r["texto"]
    # A FORMA E A DO TERMO REAL nº 19.555, de 19/08/2026 — o precedente vivo.
    assert "JOAO BATISTA ALMEIDA SILVA, lavrador" in t
    assert "ADA BARROS ALMEIDA" in t and "BALTAZAR SOARES DA SILVA" in t
    assert "avós (da filiação 1)" in t, "a forma que o oficial aprovou"
    assert "18:04" in t
    assert "MATERNIDADE DE ALTO RISCO" in t
    assert "sexo Masculino" in t
    # **O NOME DO REGISTRADO VAI ENTRE ASPAS E EM NEGRITO** — o negrito é
    #   pedido do oficial em 07/09/2026 (`nome_em_negrito`), e a folha o
    #   renderiza com `|safe`. Este teste cobrava só as aspas, sobre o texto
    #   cru: entre a aspa e o nome agora há a marca, e **o que ele mede é a
    #   frase como ela se lê no papel** — por isso compara sem a marca, e
    #   confere a marca à parte.
    assert 'nome de: "PAULO HENRIQUE BARROS ALMEIDA"' in _sem_negrito(t), (
        "o nome vai entre aspas")
    assert "<strong>PAULO HENRIQUE BARROS ALMEIDA</strong>" in t, (
        "o nome do registrado sai em negrito — ordem do oficial, 07/09/2026")
    assert "dezenove (19)" in t or "de dois mil e vinte e seis (2026)" in t, (
        "a data vai por extenso com o algarismo — art. 795, § 4º")


def test_a_idade_da_genitora_sai_do_que_o_declarante_informou():
    """«A genitora na ocasiao do parto contava 29 anos de idade» — a frase esta
    no termo nº 8.369 desta casa. E **nao se calcula**: onde a data de
    nascimento da mae falta, o calculo erraria num papel assinado."""
    r = M.montar_do_assento(ASSENTO, PESSOAS)
    assert "na ocasião do parto, 29 anos de idade" in r["texto"]

    sem_idade = [p for p in PESSOAS if p["papel"] != "MAE"]
    sem_idade.append({"papel": "MAE", "nome": "VALDENISA"})
    r2 = M.montar_do_assento(ASSENTO, sem_idade)
    assert "contava" not in r2["texto"], (
        "sem a idade informada, a frase inteira tem de sumir — nao virar traco")


def test_campo_opcional_vazio_some_e_nao_vira_traco():
    """**MEDIDO NUM ASSENTO REAL EM 30/08/2026**: o `frase_gemeos` de quem nao
    e gemeo virava traco colado ao nome — «PAULO HENRIQUE ALMEIDA____________».

    Traco onde nao ha claro e pior que claro em branco: no livro ele parece
    erro de impressao, e o escrevente vai preencher alguma coisa ali.
    """
    r = M.montar_do_assento(ASSENTO, PESSOAS)
    t = r["texto"]
    assert "____________" not in t.split("sendo filho")[0].split("nome de:")[1], (
        "o gemeo de quem nao e gemeo deixou traco ao lado do nome")
    # **«NAO CONTERA QUALQUER MENCAO OU ESPACO»** — ordem do oficial.
    assert "gêmeo" not in t.lower()
    assert "  " not in t, "a frase ausente deixou espaco duplo"
    assert '", sendo filho de' in t


def test_o_campo_exigido_vazio_continua_virando_traco():
    """O que e obrigatorio e falta tem de aparecer — o teto do teste acima."""
    r = M.montar_do_assento({"nome": "FULANO"}, [])
    assert "____________" in r["texto"]
    assert not r["completo"]


def test_o_ocasional_some_do_texto_e_continua_listado():
    """**Quem monta o termo precisa saber que nao perguntou os gemeos** — e
    essa intencao continua atendida, noutra lista.

    Ate 31/08/2026 o campo ocasional caia em `em_branco`, junto do que falta de
    verdade, e por isso marcava o termo como incompleto. Agora ele esta em
    `nao_e_o_caso`: **continua a vista**, e para de contar como falta.

    A diferenca importa porque sao duas perguntas distintas — «o que impede de
    lavrar?» e «o que este ato nao tem?» —, e a resposta da primeira e a que o
    escrevente precisa ler antes de assinar.
    """
    r = M.montar_do_assento(ASSENTO, PESSOAS)
    assert any("meos" in x for x in r["nao_e_o_caso"]), \
        "os gêmeos sumiram das duas listas — o operador deixa de saber"
    assert not any("meos" in x for x in r["em_branco"]), \
        "não ser gêmeo não é uma falta"


def test_pessoa_sem_qualificacao_nao_sai_com_virgula_solta():
    """«Fulano, , residente em » e pior que «Fulano»: parece erro de impressao
    num livro que nao aceita rasura."""
    r = M.montar_do_assento(
        ASSENTO, [{"papel": "DECLARANTE", "nome": "MARIA"}])
    t = r["texto"]
    assert "MARIA" in t
    assert ", ," not in t and ",," not in t, "deixou virgula solta"
    assert "portador" not in t, "inventou documento que nao ha"
    assert "e de." not in t, (
        "sem a filiacao 2, sobrou «e de.» — conjuncao sem sujeito")


def test_so_um_avo_nao_sai_com_e_sem_sujeito():
    """Escrever « e BELTRANA» quando o primeiro falta deixaria no livro uma
    conjuncao sem sujeito."""
    r = M.montar_do_assento(
        ASSENTO, [{"papel": "AVO_MATERNA", "nome": "MARIA ERNITA"}])
    assert " e MARIA ERNITA" not in r["texto"]
    assert "MARIA ERNITA" in r["texto"]


def test_montar_do_assento_nao_grava_nada():
    codigo = (RAIZ / "rc_modelos_do_livro.py").read_text(encoding="utf-8")
    for proibido in ("INSERT INTO", "UPDATE ", "DELETE FROM", "sqlite3"):
        assert proibido not in codigo
