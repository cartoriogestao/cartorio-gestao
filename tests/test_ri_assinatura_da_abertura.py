"""QUEM ABRIU A MATRÍCULA ASSINA O PAPEL — 16/09/2026.

    «precisa ter espaco pra quem abriu a matricula assinar» — o oficial

O QUE ESTAVA ACONTECENDO, E ERA PIOR QUE FALTAR ESPAÇO. O molde da ficha tem
`{% if abertura_fecho %}` desde sempre, e o contexto o montava assim:

    "abertura_fecho": fecho_do_ato(cidade, uf, m["data_abertura"], m["teor"])

— **quatro argumentos, sem o `nome`**. E `fecho_do_ato` devolve `""` quando não
sabe quem praticou (regra certa para ato: «melhor faltar o nome do que atribuir
o ato a quem não o praticou»). Resultado medido: **o fecho da abertura saía
vazio em todas as 1.982 fichas da casa.** A linha existia no molde e nunca
imprimiu nada.

E NÃO HAVIA DE ONDE TIRAR O NOME. `ri_matriculas.criado_por` estava **NULL em
1.982 de 1.982** — a rota que abre matrícula gravava `NULL` escrito na consulta.
Nenhuma ficha desta casa jamais soube quem a abriu.

O QUE ESTES TESTES GUARDAM

  1. **O espaço aparece mesmo sem o nome.** É a diferença entre esta função e
     `fecho_do_ato`, e é o pedido literal: é na linha que a pessoa assina e
     escreve quem é.
  2. **O nome não se inventa.** Quem abriu a 4.016 foi o script de importação;
     pôr ali quem está logado hoje seria atribuir o ato a quem não o praticou.
  3. **O tratamento vem do cadastro**, e não da última letra da função —
     `ri_delegatarios.tratamento` guarda «A»/«O», e deduzir acertaria
     «Substituta» e erraria «Auxiliar».
  4. **Tudo corre na mesma linha** — ordem dele no mesmo dia, horas depois:
     «o cidade exemplo na ficha deve começar logo depois da parte do registro
     anterior, sem espaços desnecessários». A linha em branco que havia aqui
     veio do relato #27, que era sobre a ficha do CARTÃO DE AUTÓGRAFO, e
     nesta não servia a ninguém.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ri_odt


# ------------------------------------------------- o molde imprime o espaço


def test_o_fecho_CORRE_na_mesma_linha_do_registro_anterior():
    """**O contrato mudou em 16/09/2026, e este teste cobrava o anterior.**

        «o cidade exemplo na ficha deve começar logo depois da parte do
         registro anterior, sem espaços desnecessários, e precisa constar o
         usuário que está abrindo a matrícula logo depois, sem pular linha.
         e espaço pra ele assinar na sequência da linha»

    Ele exigia `<p></p>` — a linha em branco — antes da assinatura, que veio
    do relato #27 de 31/08 sobre **outro papel**: a ficha do cartão de
    autógrafo, em que a firma se desenvolve num campo próprio. Aqui a
    assinatura vai sobre os 32 sublinhados, e o vão acima abria quatro linhas
    de nada entre «REGISTRO ANTERIOR» e quem assina.

    **O que este teste cobra agora é que os três corram juntos**: descrição
    do imóvel, fecho e assinatura no MESMO parágrafo.
    """
    molde = ri_odt.MODELO_FICHA_PADRAO
    assert "abertura_assinatura" in molde, (
        "o molde não imprime a assinatura da abertura")
    depois = molde[molde.index("REGISTRO ANTERIOR"):]
    ate_fechar = depois[:depois.index("</p>")]
    assert "abertura_fecho" in ate_fechar, (
        "o fecho saiu do parágrafo do registro anterior — ele volta a pular "
        "linha no papel")
    assert "abertura_assinatura" in ate_fechar, (
        "a assinatura saiu do parágrafo — ela tem de vir na sequência")
    assert "<p>" not in ate_fechar, (
        f"há parágrafo novo entre o registro anterior e a assinatura: "
        f"{ate_fechar[-200:]!r}")


def test_a_linha_em_branco_sobrevive_a_conversao_para_odt():
    """Ela era descartada até 31/08/2026 — e sem ela não há espaço nenhum."""
    odf = ri_odt.html_para_odf("<p>antes</p><p></p><p>depois</p>")
    assert odf.count("<text:p") >= 3, (
        f"o parágrafo vazio sumiu na conversão: {odf!r}")


# --------------------------------------------- o fecho, com e sem o nome


def test_o_espaco_sai_no_papel_mesmo_sem_o_nome(cg_casa_logada):
    """O pedido é o ESPAÇO, e ele não pode depender de saber quem foi.

    **E ELE SE MEDE DENTRO DO `.odt`, E NÃO NOS BYTES DA RESPOSTA.** A primeira
    versão deste teste procurou os sublinhados em `response.data` — e desde
    01/09/2026 a rota entrega **PDF**, cujo fluxo vem comprimido com
    FlateDecode: os sublinhados estão lá e não aparecem. O teste acusava o
    produto por um defeito dele mesmo, que é a lição do «teste que mede
    espaço não pode colapsar espaço» noutra forma.
    """
    import io
    import zipfile

    casa = cg_casa_logada
    con = sqlite3.connect(casa["banco"])
    with con:
        cur = con.execute(
            """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao,
                   tipo_ficha, origem, criado_em, data_abertura, cidade, uf)
               VALUES ('4016','2','2','ATIVA','ESTRUTURADA','MANUAL',
                       '2026-09-14T22:43:07','2026-09-14','Cidade Exemplo','MA')""")
        mid = int(cur.lastrowid)
    con.close()

    r = casa["c"].get(f"/registro-imoveis/{mid}/ficha.odt?formato=odt")
    assert r.status_code == 200, r.status_code
    with zipfile.ZipFile(io.BytesIO(r.data)) as z:
        conteudo = z.read("content.xml").decode("utf-8")

    assert "_" * 32 in conteudo, (
        "a linha de assinatura não chegou ao papel — e é ela o espaço que "
        "ele pediu")
    assert "O referido é verdade e dou fé" in conteudo, (
        "o fecho da abertura continua saindo vazio: era isto que acontecia "
        "em todas as 1.982 fichas")
    # E O NOME NAO SE INVENTA: esta ficha nao sabe quem a abriu.
    assert "MARIO EXEMPLO" not in conteudo.upper(), (
        "o papel pôs quem está logado como quem abriu a matrícula")


def test_o_nome_de_quem_abriu_nao_se_inventa():
    """A rota que abre matrícula grava os três; as 1.982 antigas não os têm.

    **Pôr quem está logado hoje seria atribuir a abertura a quem não a
    praticou** — quem abriu a 4.016 foi o script de importação. A regra já
    estava escrita em `fecho_do_ato` e vale igual aqui.
    """
    codigo = (RAIZ / "ri_web.py").read_text(encoding="utf-8")
    assert "aberta_nome" in codigo and "aberta_titulo" in codigo, (
        "a rota que abre matrícula deixou de registrar quem abriu")
    # E o `criado_por` continua NULL de propósito: ele é um `id`, e papel não
    # imprime `id`.
    assert "quem_pratica_o_ato()" in codigo


def test_o_tratamento_vem_do_cadastro_e_nao_da_ultima_letra():
    """«Substituta» acertaria; «Auxiliar» erraria, sem avisar qual foi qual."""
    codigo = (RAIZ / "ri_web.py").read_text(encoding="utf-8")
    i = codigo.index("def fecho_da_abertura")
    corpo = codigo[i:i + 4000]
    assert "tratamento" in corpo
    # A régua é o valor cadastrado, e não o fim da palavra da função.
    assert "endswith" not in corpo, (
        "o tratamento passou a ser deduzido da última letra — "
        "`ri_delegatarios.tratamento` guarda 'A'/'O' justamente para isso")


def test_o_fecho_nao_sai_duas_vezes_quando_o_teor_ja_o_tem():
    """Medido em 28/08: 1.450 das 1.507 fichas herdadas já o trazem dentro."""
    codigo = (RAIZ / "ri_web.py").read_text(encoding="utf-8")
    i = codigo.index("def fecho_da_abertura")
    corpo = codigo[i:i + 4000]
    assert re.search(r"dou\\\\s\+f", corpo) or "dou" in corpo, (
        "a guarda contra o fecho em dobro saiu")


def test_as_tres_colunas_entraram_por_migracao():
    """`MIGRACOES` é só `ALTER TABLE ADD COLUMN` — regra da casa."""
    import ri_schema
    novas = [m for m in ri_schema.MIGRACOES
             if m[0] == "ri_matriculas" and m[1].startswith("aberta_")]
    assert len(novas) == 3, novas
    assert all(m[2] == "TEXT" for m in novas)


def test_a_coluna_existe_no_banco_depois_de_migrar(cg_casa):
    con = sqlite3.connect(cg_casa["banco"])
    cols = {x[1] for x in con.execute("PRAGMA table_info(ri_matriculas)")}
    con.close()
    for c in ("aberta_nome", "aberta_titulo", "aberta_tratamento"):
        assert c in cols, f"{c} não chegou ao banco"


def test_acervo_sem_linha_nao_ganha_fecho_nem_assinatura(cg_casa_logada):
    """Abaixo de 4.015 o papel segue o conteúdo importado, sem recomposição.

    A linha de assinatura que antes era acrescentada atribuía uma abertura
    histórica a quem trabalha hoje. A regra da serventia em 17/09/2026 é que
    o sistema não completa abertura de acervo: imprime exatamente o teor que
    veio da importação.
    """
    import io
    import zipfile

    casa = cg_casa_logada
    con = sqlite3.connect(casa["banco"])
    with con:
        cur = con.execute(
            """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao,
                   tipo_ficha, origem, criado_em, data_abertura, cidade, uf,
                   teor)
               VALUES ('3110','2-Q','2-Q','ATIVO','ACERVO','EOFICIO',
                       '2026-09-14T10:27','2009-08-13','Cidade Exemplo','MA',
                       'Emolumentos R$17,30. Dou fé. Ana Grácia - Oficiala.')""")
        mid = int(cur.lastrowid)
    con.close()

    r = casa["c"].get(f"/registro-imoveis/{mid}/ficha.odt?formato=odt")
    assert r.status_code == 200, r.status_code
    with zipfile.ZipFile(io.BytesIO(r.data)) as z:
        conteudo = z.read("content.xml").decode("utf-8")

    assert "_" * 32 not in conteudo, (
        "o sistema acrescentou assinatura que não existe na importação")
    # A frase que veio do acervo continua uma vez, sem outra gerada hoje.
    assert conteudo.count("dou fé") + conteudo.count("Dou fé") == 1, (
        "o «dou fé» saiu repetido")


def test_teor_que_JA_TEM_linha_nao_ganha_outra(cg_casa_logada):
    """Duas linhas no mesmo papel e ninguém sabe em qual assinar.

    **E O CASO E DE FICHA DE ACERVO, E NAO DA 4.016 — eu errei isto na
    primeira versao.** O molde imprime o teor só quando `tipo_ficha` é
    `ACERVO`; a 4.016 é `ESTRUTURADA` (são 434 assim), e o teor dela **não vai
    ao papel**. A linha que o documento dela trazia nunca chegava à
    impressão — eu li a coluna e supus que ela imprimia.

    Quem me corrigiu foi este teste, que acusou **zero** linhas onde eu
    esperava duas.
    """
    import io
    import zipfile

    casa = cg_casa_logada
    con = sqlite3.connect(casa["banco"])
    with con:
        cur = con.execute(
            """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao,
                   tipo_ficha, origem, criado_em, data_abertura, cidade, uf,
                   teor)
               VALUES ('582','2-C','2-C','ATIVO','ACERVO','EOFICIO',
                       '2026-09-14T22:43','2026-09-14','Cidade Exemplo','MA',
                       'O referido é verdade e dou fé. A Substituta, '
                       || '________________________________ BEATRIZ.')""")
        mid = int(cur.lastrowid)
    con.close()

    r = casa["c"].get(f"/registro-imoveis/{mid}/ficha.odt?formato=odt")
    assert r.status_code == 200
    with zipfile.ZipFile(io.BytesIO(r.data)) as z:
        conteudo = z.read("content.xml").decode("utf-8")
    import re as _re
    assert len(_re.findall(r"_{8,}", conteudo)) == 1, (
        "saíram duas linhas de assinatura no mesmo papel")


def test_a_ficha_ESTRUTURADA_ganha_a_linha_mesmo_com_o_teor_cheio(cg_casa_logada):
    """A 4.016 é este caso, e eu o tinha dado por resolvido sem medir.

    O teor dela — vindo do documento de abertura — traz «dou fé» E a linha.
    Mas ela é `ESTRUTURADA`, e o molde só imprime o teor de ficha `ACERVO`:
    nada daquilo chega ao papel. **A guarda não pode olhar o que não sai.**
    """
    import io
    import zipfile

    casa = cg_casa_logada
    con = sqlite3.connect(casa["banco"])
    with con:
        cur = con.execute(
            """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao,
                   tipo_ficha, origem, criado_em, data_abertura, cidade, uf,
                   teor)
               VALUES ('4016','2','2','ATIVA','ESTRUTURADA','MANUAL',
                       '2026-09-14T22:43','2026-09-14','Cidade Exemplo','MA',
                       'O referido é verdade e dou fé. A Substituta, '
                       || '________________________________ BEATRIZ.')""")
        mid = int(cur.lastrowid)
    con.close()

    r = casa["c"].get(f"/registro-imoveis/{mid}/ficha.odt?formato=odt")
    assert r.status_code == 200
    with zipfile.ZipFile(io.BytesIO(r.data)) as z:
        conteudo = z.read("content.xml").decode("utf-8")
    assert "_" * 32 in conteudo, (
        "a ficha ESTRUTURADA saiu sem espaço para assinar — o teor dela não "
        "vai ao papel, e a guarda estava olhando para ele")


def test_no_papel_o_fecho_sai_no_MESMO_paragrafo(cg_casa_logada):
    """A prova é o `.odt` gerado, e não o molde: é ele que vai à impressora.

    Medir no molde prova que o texto está escrito junto; medir no `content.xml`
    prova que o CONVERSOR não separou de novo — e `html_para_odf` abre
    parágrafo por conta própria em mais de um lugar.
    """
    import io
    import zipfile

    casa = cg_casa_logada
    con = sqlite3.connect(casa["banco"])
    with con:
        cur = con.execute(
            """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao,
                   tipo_ficha, origem, criado_em, data_abertura, cidade, uf,
                   registro_anterior)
               VALUES ('4016','2','2','ATIVA','ESTRUTURADA','MANUAL',
                       '2026-09-14T22:43:07','2026-09-14','Cidade Exemplo','MA',
                       'Matrícula nº 3.110, Livro nº 2-Q, fl. 168.')""")
        mid = int(cur.lastrowid)
    con.close()

    r = casa["c"].get(f"/registro-imoveis/{mid}/ficha.odt?formato=odt")
    with zipfile.ZipFile(io.BytesIO(r.data)) as z:
        conteudo = z.read("content.xml").decode("utf-8")

    # Um paragrafo por vez: o que tem o registro anterior tem de ter tudo.
    paragrafos = conteudo.split("<text:p")
    dele = [x for x in paragrafos if "REGISTRO ANTERIOR" in x]
    assert dele, "a ficha saiu sem o registro anterior"
    assert "dou f" in dele[0], (
        "o «Cidade Exemplo…» caiu noutro parágrafo — volta a pular linha")
    assert "_" * 32 in dele[0], (
        "a linha de assinatura caiu noutro parágrafo, e não na sequência")


def test_o_papel_nao_leva_paragrafo_vazio_depois_do_registro_anterior(
        cg_casa_logada):
    """«Sem espaços desnecessários» se mede contando os vãos."""
    import io
    import zipfile

    casa = cg_casa_logada
    con = sqlite3.connect(casa["banco"])
    with con:
        cur = con.execute(
            """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao,
                   tipo_ficha, origem, criado_em, data_abertura, cidade, uf,
                   registro_anterior)
               VALUES ('4017','2','2','ATIVA','ESTRUTURADA','MANUAL',
                       '2026-09-14T22:43:07','2026-09-14','Cidade Exemplo','MA',
                       'Matrícula nº 3.201, Livro nº 2-R, fl. 10.')""")
        mid = int(cur.lastrowid)
    con.close()

    r = casa["c"].get(f"/registro-imoveis/{mid}/ficha.odt?formato=odt")
    with zipfile.ZipFile(io.BytesIO(r.data)) as z:
        conteudo = z.read("content.xml").decode("utf-8")

    corte = conteudo.index("REGISTRO ANTERIOR")
    fim = conteudo.index("_" * 32)
    assert fim > corte
    meio = conteudo[corte:fim]
    assert "<text:p/>" not in meio and "<text:p></text:p>" not in meio, (
        "sobrou parágrafo vazio entre o registro anterior e a assinatura")


# ------------------------------------------- quem abriu, e de onde ele sai


def _matricula_e_delegatario(casa, numero="4018"):
    con = sqlite3.connect(casa["banco"])
    with con:
        cur = con.execute(
            """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao,
                   tipo_ficha, origem, criado_em, data_abertura, cidade, uf,
                   registro_anterior)
               VALUES (?,'2','2','ATIVA','ESTRUTURADA','MANUAL',
                       '2026-09-14T22:43:07','2026-09-14','Cidade Exemplo','MA',
                       'Matrícula nº 1.197, Livro nº 2-F, fl. 1.')""",
            (numero,))
        mid = int(cur.lastrowid)
        con.execute(
            """INSERT INTO ri_delegatarios (nome, cargo, titulo, tratamento)
               VALUES ('BEATRIZ EXEMPLO DE SOUZA','SUBSTITUTO',
                       'Tabeliã Registradora Substituta','A')""")
    con.close()
    return mid


def _editar(casa, mid, **campos):
    """Manda o formulário INTEIRO, como a tela manda.

    A rota lê cada campo cadastral do POST e grava `None` no que não veio —
    é assim que ela apaga o que o operador esvaziou na tela. Um teste que
    mandasse só dois campos zeraria o resto do cadastro e mediria o próprio
    atalho: foi o que aconteceu na primeira versão deste ajudante, que apagou
    o registro anterior e depois acusou a ficha de ter saído sem ele.
    """
    tela = casa["c"].get(f"/registro-imoveis/{mid}/editar").get_data(
        as_text=True)
    ficha = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', tela)
    assert ficha, "a tela de editar nao trouxe csrf_token"
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    m = con.execute("SELECT * FROM ri_matriculas WHERE id=?",
                    (mid,)).fetchone()
    con.close()
    dados = {c: (m[c] or "") for c in m.keys()
             if f'name="{c}"' in tela and c != "aberta_nome"}
    dados["csrf_token"] = ficha.group(1)
    dados["motivo"] = "informando quem abriu a ficha"
    dados.update(campos)
    return casa["c"].post(f"/registro-imoveis/{mid}/editar", data=dados,
                          follow_redirects=True)


def test_a_tela_oferece_quem_abriu_a_matricula(cg_casa_logada):
    """Sem o campo não há como informar: a coluna existe e nada a preenchia.

    Medido na produção em 16/09/2026: `aberta_nome` vazio em **1.982 de
    1.982** fichas — inclusive a 4.016. Ela só se preenche em
    `ri_nova_matricula`, que nasceu ontem; o acervo e as importações, que são
    tudo o que há hoje, não a têm.
    """
    casa = cg_casa_logada
    mid = _matricula_e_delegatario(casa)
    tela = casa["c"].get(f"/registro-imoveis/{mid}/editar").get_data(
        as_text=True)
    assert 'name="aberta_nome"' in tela, (
        "não há onde informar quem abriu a matrícula")
    assert "BEATRIZ EXEMPLO DE SOUZA" in tela, (
        "a lista não veio do cadastro de delegatários")


def test_os_tres_campos_viajam_juntos(cg_casa_logada):
    """O título e o tratamento saem do cadastro, e não do formulário.

    Deduzir o artigo da última letra da função acertaria «Substituta» e
    erraria «Auxiliar», sem avisar qual foi qual — por isso a pessoa se
    escolhe e os três campos são gravados de uma vez.
    """
    casa = cg_casa_logada
    mid = _matricula_e_delegatario(casa)
    _editar(casa, mid, aberta_nome="BEATRIZ EXEMPLO DE SOUZA")

    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    m = con.execute("SELECT * FROM ri_matriculas WHERE id=?",
                    (mid,)).fetchone()
    con.close()
    assert m["aberta_nome"] == "BEATRIZ EXEMPLO DE SOUZA"
    assert m["aberta_titulo"] == "Tabeliã Registradora Substituta"
    assert m["aberta_tratamento"] == "A"


def test_nome_fora_do_cadastro_e_recusado(cg_casa_logada):
    """Digitado à mão, o papel sairia «O Tabeliã» — ou sem título nenhum."""
    casa = cg_casa_logada
    mid = _matricula_e_delegatario(casa)
    html = _editar(casa, mid, aberta_nome="FULANO DE TAL").get_data(
        as_text=True)

    assert "não está no cadastro desta serventia" in html
    con = sqlite3.connect(casa["banco"])
    guardado = con.execute(
        "SELECT aberta_nome FROM ri_matriculas WHERE id=?",
        (mid,)).fetchone()[0]
    con.close()
    assert guardado is None, "gravou um nome que a serventia não conhece"


def test_quem_abriu_sai_no_papel_na_sequencia_da_linha(cg_casa_logada):
    """É o pedido inteiro num teste: nome logo depois, e linha na sequência."""
    import io
    import zipfile

    casa = cg_casa_logada
    mid = _matricula_e_delegatario(casa)
    _editar(casa, mid, aberta_nome="BEATRIZ EXEMPLO DE SOUZA")

    r = casa["c"].get(f"/registro-imoveis/{mid}/ficha.odt?formato=odt")
    with zipfile.ZipFile(io.BytesIO(r.data)) as z:
        conteudo = z.read("content.xml").decode("utf-8")

    dele = [x for x in conteudo.split("<text:p")
            if "REGISTRO ANTERIOR" in x]
    assert dele, "a ficha saiu sem o registro anterior"
    bloco = dele[0]
    assert "dou f" in bloco
    assert "Tabeliã Registradora Substituta" in bloco, (
        "a função de quem abriu não chegou ao papel")
    assert "_" * 32 in bloco, "a linha de assinatura não veio na sequência"
    assert "BEATRIZ EXEMPLO DE SOUZA" in bloco, (
        "quem abriu a matrícula não saiu impresso")
    # A ORDEM É A QUE ELE PEDIU EM 16/09: fecho, ESPAÇO PARA ASSINAR, e só
    # então o nome e a função — «logo depois do espaco pra assinar».
    assert (bloco.index("dou f") < bloco.index("_" * 32)
            < bloco.index("BEATRIZ")
            < bloco.index("Tabeliã Registradora Substituta"))


def test_o_registro_anterior_nao_ganha_dois_pontos(cg_casa_logada):
    """«Sem espaços desnecessários» — e o ponto dobrado é um deles.

    **ACHADO NO ENSAIO CONTRA A PRODUÇÃO**, e não em teste de mesa: a 4.016
    guarda `registro_anterior` já terminado em ponto — «… aberta em
    13/08/2009.» —, e o molde acrescentava o seu. Enquanto o fecho ficava
    noutro parágrafo ninguém via; correndo na mesma linha, o papel passou a
    dizer «…13/08/2009.. Cidade Exemplo/MA…».

    **O teste de mesa não pegaria**: ali o registro anterior entra do jeito
    certo, sem ponto, porque foi o teste que o escreveu. É a lição do ensaio
    contra o acervo mais uma vez.
    """
    import io
    import zipfile

    casa = cg_casa_logada
    con = sqlite3.connect(casa["banco"])
    with con:
        cur = con.execute(
            """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao,
                   tipo_ficha, origem, criado_em, data_abertura, cidade, uf,
                   registro_anterior)
               VALUES ('4019','2','2','ATIVA','ESTRUTURADA','MANUAL',
                       '2026-09-14T22:43:07','2026-09-14','Cidade Exemplo','MA',
                       'Matrícula nº 3.110, Livro nº 2-Q, fl. 168, aberta em 13/08/2009.')""")
        mid = int(cur.lastrowid)
    con.close()

    r = casa["c"].get(f"/registro-imoveis/{mid}/ficha.odt?formato=odt")
    with zipfile.ZipFile(io.BytesIO(r.data)) as z:
        conteudo = z.read("content.xml").decode("utf-8")

    assert "13/08/2009.." not in conteudo, (
        "o ponto do registro anterior saiu dobrado no papel")
    assert "13/08/2009. Cidade Exemplo" in conteudo, (
        "o fecho não veio colado no registro anterior")


# ------------------------------- o escrevente também pode constar (16/09/2026)


def test_a_lista_oferece_os_escreventes_e_nao_so_os_delegatarios(cg_casa_logada):
    """«é preciso que seja possível escolher um escrevente para constar como
    responsável por abrir a matrícula» — o oficial.

    QUEM ABRE FICHA NO BALCÃO NÃO É O DELEGATÁRIO. A lista tinha três pessoas
    (medido na produção: `ri_delegatarios` tem 3 linhas) e a casa tem sete
    usuários ativos, cinco deles escreventes e auxiliares.
    """
    casa = cg_casa_logada
    mid = _matricula_e_delegatario(casa, "4019")
    con = sqlite3.connect(casa["banco"])
    with con:
        con.execute(
            """INSERT INTO users (username, full_name, password_salt,
                                  password_hash, role, active, funcao, created_at)
               VALUES ('carla','Carla Exemplo Lima','x','y','USER',1,
                       'Escrevente Autorizada','2026-09-16T10:00:00')""")
    con.close()

    tela = casa["c"].get(f"/registro-imoveis/{mid}/editar").get_data(as_text=True)
    assert "Carla Exemplo Lima" in tela, (
        "o escrevente não aparece na lista de quem abriu a matrícula")
    assert "Escrevente Autorizada" in tela, "a função dele não veio junto"
    assert "BEATRIZ EXEMPLO DE SOUZA" in tela, (
        "os delegatários saíram da lista — eles continuam sendo a primeira "
        "fonte, porque é deles que vem o título registral")


def test_o_escrevente_escolhido_sai_no_papel_com_a_funcao(cg_casa_logada):
    """O título vem do cadastro dele: `users.funcao`, e não inventado."""
    import io
    import zipfile

    casa = cg_casa_logada
    mid = _matricula_e_delegatario(casa, "4020")
    con = sqlite3.connect(casa["banco"])
    with con:
        con.execute(
            """INSERT INTO users (username, full_name, password_salt,
                                  password_hash, role, active, funcao, created_at)
               VALUES ('elisa','Elisa Exemplo Lima','x','y','USER',1,
                       'Escrevente Autorizada','2026-09-16T10:00:00')""")
    con.close()

    _editar(casa, mid, aberta_nome="Elisa Exemplo Lima")

    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    m = con.execute("SELECT * FROM ri_matriculas WHERE id=?", (mid,)).fetchone()
    con.close()
    assert m["aberta_nome"] == "Elisa Exemplo Lima"
    assert m["aberta_titulo"] == "Escrevente Autorizada"
    # ELE NÃO TEM TRATAMENTO, e nenhum é deduzido: desde 16/09 a assinatura é
    # «linha NOME, função.», e o artigo não entra mais no papel.
    assert m["aberta_tratamento"] is None

    r = casa["c"].get(f"/registro-imoveis/{mid}/ficha.odt?formato=odt")
    with zipfile.ZipFile(io.BytesIO(r.data)) as z:
        conteudo = z.read("content.xml").decode("utf-8")
    bloco = [x for x in conteudo.split("<text:p") if "REGISTRO ANTERIOR" in x][0]
    assert "Elisa Exemplo Lima, Escrevente Autorizada." in re.sub(
        r"<[^>]+>", "", bloco)


def test_usuario_inativo_nao_entra_na_lista(cg_casa_logada):
    """Quem saiu da casa não abre ficha hoje — e a lista é de hoje."""
    casa = cg_casa_logada
    mid = _matricula_e_delegatario(casa, "4021")
    con = sqlite3.connect(casa["banco"])
    with con:
        con.execute(
            """INSERT INTO users (username, full_name, password_salt,
                                  password_hash, role, active, funcao, created_at)
               VALUES ('saiu','Fulano Que Saiu Da Casa','x','y','USER',0,
                       'Escrevente Autorizado','2026-09-16T10:00:00')""")
    con.close()
    tela = casa["c"].get(f"/registro-imoveis/{mid}/editar").get_data(as_text=True)
    assert "Fulano Que Saiu Da Casa" not in tela

