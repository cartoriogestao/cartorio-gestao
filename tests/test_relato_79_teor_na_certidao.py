"""O TEOR DA MATRÍCULA NA CERTIDÃO DE INTEIRO TEOR — relato #79, 17/09/2026.

    «NÃO ESTÁ GERANDO O TEOR DA MATRICULA NA CERTIDÃO APENAS OS CABEÇARIO»

O QUE ESTAVA ACONTECENDO, E A GUARDA QUE O FAZIA
    `MODELO_CERTIDAO_PADRAO` imprimia o teor assim:

        {% if m.tipo_ficha == "ACERVO" %}{{ teor_odf }}{% endif %}

    Medido na produção em 17/09/2026: das **1.985** matrículas, **1.979 são
    ACERVO** e **6 são ESTRUTURADA** — e as seis perdiam o teor. A certidão
    **10/2026**, da matrícula **4.016**, saiu com **674 caracteres**: a
    introdução, o «cujo inteiro teor segue:», e «Era o que nela continha.»
    sem nada entre os dois. O papel afirmava «inteiro teor» e não reproduzia
    teor nenhum — «carimbo que mente» na sua forma mais cara, porque quem
    pede inteiro teor leva o papel para o banco, para o comprador e para o
    juiz.

E AS SEIS SÃO AS FICHAS NOVAS
    A 4.016 tem **5.294 caracteres** de teor, com a descrição perimétrica
    inteira da Fazenda Boa Lembrança; a 4.018 tem **11.500**. As ESTRUTURADAS
    são as fichas que a casa abriu, e são elas que a certidão deixava em
    branco.

POR QUE A GUARDA EXISTIA, E POR QUE ELA NÃO SERVE PARA A CERTIDÃO
    Ela nasceu para a **ficha de papel** — `MODELO_FICHA_PADRAO`, 16/09/2026,
    quando o oficial mandou que a abertura de acervo saísse exatamente como
    veio da importação, sem o sistema acrescentar assinatura. Ali o teor só
    sai quando a ficha é ACERVO, e a guarda tem teste próprio em
    `test_ri_assinatura_da_abertura.py`.

    **São dois papéis, e eles não imprimem a mesma coisa.** A pergunta da
    certidão não é de que tipo a ficha é: é se ela TEM teor.

O ATO QUE O TEOR JÁ CONTA NÃO SE REPETE NO PAPEL
    Quem decide isso é `contexto_ficha`, com `atos_fora_do_teor` — e a conta
    é uma só. Ela passa a valer para a certidão (que agora imprime o teor das
    ESTRUTURADAS) e continua valendo só para o acervo na ficha de papel (que
    só imprime o teor do acervo). Repeti-la nos dois lugares divergiria no
    primeiro conserto, e o lado que ficasse para trás apagaria um ato da
    leitura — o defeito que o relato #67 existiu para impedir.
"""
from __future__ import annotations

import io
import re
import sqlite3
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import modelos_da_casa
import ri_odt

# O teor de uma ficha estruturada desta casa, na forma que ela guarda: HTML,
# com a descrição do imóvel e o fecho da abertura dentro.
DENOMINACAO = "FAZENDA BOA LEMBRANÇA"
FRASE_DO_ATO = "PROTOCOLO Nº 11.559, DE 14 DE SETEMBRO DE 2026."
TEOR_DA_FICHA = (
    "<p>FICHA DE ABERTURA - IMÓVEL RURAL. DENOMINAÇÃO: " + DENOMINACAO
    + ".</p><p>" + FRASE_DO_ATO
    + " O referido é verdade e dou fé.</p>")


def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _abrir(casa, *, numero, teor="", atos=(), tipo_ficha=None) -> int:
    """Abre a ficha e, se pedido, os atos — devolve o id da matrícula."""
    from ri_schema import hash_ato

    if tipo_ficha is None:
        tipo_ficha = "ACERVO" if int(numero) < 4015 else "ESTRUTURADA"
    con = _con(casa)
    with con:
        cur = con.execute(
            """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao,
                   tipo_ficha, origem, criado_em, data_abertura, cidade, uf,
                   teor, teor_formato)
               VALUES (?, '2', '2', 'ATIVA', ?, 'MANUAL',
                       '2026-09-17T09:00', '2026-09-14', 'Cidade Exemplo', 'MA',
                       ?, 'html')""", (numero, tipo_ficha, teor or None))
        mid = int(cur.lastrowid)
        for i, texto in enumerate(atos, start=1):
            data = "2026-09-14"
            h = hash_ato(numero, "R", i, data, texto, None)
            con.execute(
                """INSERT INTO ri_atos (matricula_id, tipo, numero, data_ato,
                       teor, teor_formato, cancelado, acervo, origem, hash_ato,
                       hash_anterior, lavrado_em)
                   VALUES (?, 'R', ?, ?, ?, 'html', 0, 0, 'MANUAL', ?, NULL,
                           '2026-09-14T09:00')""", (mid, i, data, texto, h))
    con.close()
    return mid


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _emitir(casa, mid) -> dict:
    """Emite a certidão pela tela e lê o corpo CONGELADO em `ri_certidoes`.

    É o corpo gravado, e não o que a tela mostra: é ele o papel que sai.
    """
    tela = casa["c"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    casa["c"].post(f"/registro-imoveis/{mid}/certidao", data={
        "csrf_token": _token(tela), "tipo": "INTEIRO_TEOR",
        "fonte_corpo": "TEXTO", "requerente": "FULANO DE TAL"},
        follow_redirects=True)
    con = _con(casa)
    linha = con.execute(
        "SELECT * FROM ri_certidoes ORDER BY id DESC LIMIT 1").fetchone()
    con.close()
    assert linha, "a certidão não foi emitida"
    return dict(linha)


def _ficha_odt(casa, mid) -> str:
    """O `content.xml` da ficha em papel — o outro papel deste mesmo contexto."""
    r = casa["c"].get(f"/registro-imoveis/{mid}/ficha.odt?formato=odt")
    assert r.status_code == 200, r.status_code
    with zipfile.ZipFile(io.BytesIO(r.data)) as z:
        return z.read("content.xml").decode("utf-8")


# ------------------------------------------ o teor sai na certidão, em toda ficha


def test_a_certidao_da_ficha_ESTRUTURADA_imprime_o_teor(cg_casa_logada):
    """É o relato #79, e a 4.016 é este caso: 5.294 caracteres de teor, e o
    papel saiu com 674 — a introdução e o fecho, sem teor nenhum."""
    casa = cg_casa_logada
    mid = _abrir(casa, numero="4016", teor=TEOR_DA_FICHA)
    certidao = _emitir(casa, mid)

    assert DENOMINACAO in certidao["corpo"], (
        "o teor da ficha ESTRUTURADA não chegou à certidão — é o relato #79")
    assert len(certidao["corpo"]) > len(TEOR_DA_FICHA), (
        f"o corpo saiu com {len(certidao['corpo'])} caracteres: é a "
        f"introdução e o fecho, sem o teor")


def test_o_teor_sai_ENTRE_a_introducao_e_o_fecho(cg_casa_logada):
    """«cujo inteiro teor segue:» … teor … «Era o que nela continha.»

    A ordem não é estética: o fecho da certidão fecha o que a introdução
    abriu, e teor depois dele sairia fora do documento.
    """
    casa = cg_casa_logada
    mid = _abrir(casa, numero="4016", teor=TEOR_DA_FICHA)
    corpo = _emitir(casa, mid)["corpo"]

    i_segue = corpo.find("inteiro teor segue")
    i_teor = corpo.find(DENOMINACAO)
    i_era = corpo.find("Era o que nela continha")
    assert -1 < i_segue < i_teor < i_era, (
        f"a ordem saiu errada: segue={i_segue} teor={i_teor} era={i_era}")


def test_a_ficha_de_ACERVO_continua_imprimindo_o_teor(cg_casa_logada):
    """A regressão que o conserto podia causar: 1.979 fichas são de acervo, e
    é delas que saem as certidões desta casa desde sempre."""
    casa = cg_casa_logada
    mid = _abrir(casa, numero="3110", teor=TEOR_DA_FICHA)
    certidao = _emitir(casa, mid)
    assert DENOMINACAO in certidao["corpo"]


def test_ficha_sem_teor_nao_imprime_teor_nenhum(cg_casa_logada):
    """`teor_odf` vazio não pode virar a palavra «None» no papel.

    A guarda nova é `{% if teor_odf %}` — e ela existe para isto: a ficha que
    não tem teor sai com os atos, e não com um buraco escrito.
    """
    casa = cg_casa_logada
    mid = _abrir(casa, numero="4017",
                 atos=("REGISTRO DO TÍTULO, protocolo 11.560.",))
    corpo = _emitir(casa, mid)["corpo"]
    assert "None" not in corpo
    assert "REGISTRO DO TÍTULO" in corpo, "o ato saiu do papel"


# ------------------------- o ato que o teor já conta não se repete no papel


def test_o_ato_que_o_teor_ja_conta_nao_sai_duas_vezes(cg_casa_logada):
    """A conta é do `atos_fora_do_teor`, e ela passou a valer para a certidão
    no mesmo conserto — porque agora a certidão imprime o teor das seis.

    Repetir o ato faria o papel dizer duas vezes a mesma coisa, uma dentro do
    teor e outra fora — e o teor é o que a ficha de papel já dizia.
    """
    casa = cg_casa_logada
    ato = FRASE_DO_ATO + " O referido é verdade e dou fé."
    mid = _abrir(casa, numero="4018", teor=TEOR_DA_FICHA, atos=(ato,))
    corpo = _emitir(casa, mid)["corpo"]

    # As duas metades na mesma asserção, de propósito: só «uma vez» não
    # distingue o certo das duas formas de errar — o papel que não imprime o
    # teor (relato #79) e o que o imprime e repete o ato logo abaixo.
    assert DENOMINACAO in corpo, (
        "o teor não chegou ao papel — é o relato #79")
    assert corpo.count("PROTOCOLO Nº 11.559") == 1, (
        "o ato que o teor já conta saiu outra vez, fora dele")


def test_o_ato_que_o_teor_NAO_conta_continua_saindo(cg_casa_logada):
    """O outro lado da mesma conta: o ato posterior, que o teor não conta,
    tem de estar no papel — senão o conserto esconderia ato."""
    casa = cg_casa_logada
    ato = "AVERBAÇÃO DE PENHORA, protocolo 11.600, do processo 0001234."
    mid = _abrir(casa, numero="4019", teor=TEOR_DA_FICHA, atos=(ato,))
    corpo = _emitir(casa, mid)["corpo"]
    assert "AVERBAÇÃO DE PENHORA" in corpo


# ------------------------------------- os dois papéis, e a regra de cada um


def test_a_ficha_de_papel_continua_com_a_regra_dela(cg_casa_logada):
    """A ficha ESTRUTURADA não ganha o teor: continua decisão de 16/09/2026.

    **Os dois papéis não mudaram de regra juntos, e não podiam.** A ficha de
    papel só imprime o teor do acervo; a certidão imprime o teor que existe.
    Este teste guarda a metade que NÃO se mexeu — quem ler o conserto do #79
    e "uniformizar" as duas apaga o comportamento que o oficial pediu.
    """
    # A REGRA DA FICHA SE AFINOU EM 23/09/2026 (3.6.185): a ESTRUTURADA SEM
    # `descricao_perimetro` passou a imprimir o teor como miolo — sem ele a
    # ficha sairia sem nada sobre o imóvel (`usa_teor_como_miolo` em
    # `MODELO_FICHA_PADRAO`). A metade que este teste guarda continua: a
    # ESTRUTURADA que TEM a descrição do imóvel não imprime o teor.
    casa = cg_casa_logada
    mid = _abrir(casa, numero="4020", teor=TEOR_DA_FICHA)
    con = _con(casa)
    with con:
        con.execute("UPDATE ri_matriculas SET descricao_perimetro=? WHERE id=?",
                    ("Um imóvel rural com 38,55,55 ha.", mid))
    con.close()
    conteudo = _ficha_odt(casa, mid)
    assert DENOMINACAO not in conteudo, (
        "a ficha de papel de uma ESTRUTURADA passou a imprimir o teor — a "
        "decisão de 16/09/2026 sobre a abertura do acervo era a outra")


def test_o_ato_nao_some_da_ficha_de_papel_quando_o_teor_o_conta(cg_casa_logada):
    """É o motivo do `or not para_odt` na guarda do contexto.

    Na ficha ESTRUTURADA o teor NÃO vai ao papel — então o ato que ele conta
    é a única forma de aquilo aparecer impresso. Tirá-lo da lista, ali,
    apagaria do papel um ato que existe.
    """
    casa = cg_casa_logada
    ato = FRASE_DO_ATO + " O referido é verdade e dou fé."
    mid = _abrir(casa, numero="4021", teor=TEOR_DA_FICHA, atos=(ato,))
    conteudo = _ficha_odt(casa, mid)
    assert "PROTOCOLO Nº 11.559" in conteudo, (
        "o ato sumiu da ficha de papel: o teor não é impresso nela, e sem o "
        "ato a ficha sai sem registro nenhum")


# ------------------------------------------------ o molde, e a guarda antiga


def test_o_molde_da_certidao_nao_pergunta_mais_o_tipo_da_ficha():
    """A guarda era `{% if m.tipo_ficha == "ACERVO" %}{{ teor_odf }}{% endif %}`.

    Fica vermelho se alguém a reintroduzir — e a certidão da ficha nova volta
    a sair só com cabeçalho e assinatura.

    **E O TEOR PASSOU A MORAR NO MIOLO** — problema #75, 18/09/2026: o molde
    ficou com o que toda certidão tem e o texto de cada tipo virou papel
    próprio no catálogo. A guarda que este teste protege é a mesma, e mudou de
    endereço junto com o teor: quem a procura tem de procurar onde ela está.
    """
    # O miolo se lê COMO A EMISSÃO O LÊ — pelo catálogo, que é quem diz onde o
    # texto do papel mora. Buscar `getattr(ri_odt, <chave>)` seria procurar pelo
    # nome errado: a chave do catálogo é `RI_CERTIDAO_INTEIRO_TEOR` e a
    # constante é `MIOLO_CERTIDAO_INTEIRO_TEOR`, e as duas se chamarem parecido
    # não as torna a mesma — é a lição do `normalizar_nome` pela enésima vez.
    chave_do_miolo = ri_odt.MIOLO_DA_CERTIDAO["INTEIRO_TEOR"]
    assert chave_do_miolo == "RI_CERTIDAO_INTEIRO_TEOR"
    texto = modelos_da_casa.padrao_de(chave_do_miolo)
    assert "{% if teor_odf %}{{ teor_odf }}{% endif %}" in texto, (
        "a certidão deixou de imprimir o teor que a ficha tem")
    assert '{% if m.tipo_ficha == "ACERVO" %}{{ teor_odf }}' not in texto, (
        "a guarda pelo tipo da ficha voltou para a certidão — é o relato #79")
    # **E O MOLDE CARREGA A EMENDA POR ONDE ELE ENTRA.** Sem o marcador, o
    # teor não chega ao papel nem que o miolo esteja perfeito — é a segunda
    # metade da mesma propriedade, e ela se perde sozinha.
    assert ri_odt.MARCADOR_DO_MIOLO in ri_odt.MODELO_CERTIDAO_PADRAO


def test_a_ficha_de_papel_mantem_a_guarda_do_acervo_no_molde():
    """A outra metade, no molde: `ACERVO and teor_odf`, com o teste do
    `test_ri_assinatura_da_abertura.py` ao lado."""
    molde = ri_odt.MODELO_FICHA_PADRAO
    # Desde 23/09/2026 (3.6.185) a guarda tem a segunda metade: a ESTRUTURADA
    # sem descrição do imóvel também leva o teor (ver o teste acima).
    assert ('{% set usa_teor_como_miolo = (m.tipo_ficha == "ACERVO" or '
            '(m.tipo_ficha == "ESTRUTURADA" and not m.descricao_perimetro)) '
            'and teor_odf %}') in molde


def test_o_teor_que_ja_tem_a_assinatura_nao_ganha_outra_na_certidao(
        cg_casa_logada):
    """A certidão imprime o teor COMO ELE É, e não acrescenta o fecho da
    abertura por baixo.

    **ESTA PROPRIEDADE EU MEDI DEPOIS DE SUPOR O CONTRÁRIO — 17/09/2026.** Ao
    corrigir o #79 eu escrevi, na nota de `fecho_da_abertura`, que a certidão
    sairia com a assinatura em dobro, porque o teor das 6 ESTRUTURADAS desta
    casa (4.016 a 4.021) traz «dou fé» e uma linha de assinar dentro dele. Fui
    ler `MODELO_CERTIDAO_PADRAO` e **ele não chama nem `abertura_fecho` nem
    `abertura_assinatura`**: fecha com «Era o que nela continha.», com o «Dou
    fe.» da validade e com o bloco de quem assina a certidão. O risco era de
    um papel que não existe — e o defeito seria inventado por quem o
    introduzisse, não encontrado.

    Por isso o teste fica: ele é o que avisa no dia em que alguém puser a
    linha da abertura no molde da certidão. Aí, sim, o papel sairia com duas
    linhas de assinar, e quem assina não saberia em qual.
    """
    casa = cg_casa_logada
    teor = ("<p>FICHA DE ABERTURA - IMÓVEL RURAL. DENOMINAÇÃO: " + DENOMINACAO
            + ".</p><p>O referido é verdade e dou fé. A Substituta, "
            + "_" * 32 + " BEATRIZ EXEMPLO DE SOUZA.</p>")
    mid = _abrir(casa, numero="4016", teor=teor)
    corpo = _emitir(casa, mid)["corpo"]

    assert DENOMINACAO in corpo, "o teor não chegou ao papel — é o relato #79"
    assert corpo.count("dou fé") == 1, (
        f"o «dou fé» saiu {corpo.count('dou fé')} vezes: uma é a do teor, e a "
        f"outra só pode ter vindo de um fecho da abertura posto no molde da "
        f"certidão")
    # DESDE 22/09/2026 (3.6.185) A CERTIDÃO TIRA A LINHA DE ASSINAR DA FICHA:
    # o corpo passa por `certidao_texto.sem_linha_de_assinatura_a_mao`, que
    # apaga os traços e mantém o nome de quem lavrou («sem espaço de
    # assinatura da FICHA no papel da certidão»). Logo a linha que veio no
    # teor também sai — e a régua deste teste, «nunca DUAS», vira «nenhuma».
    assert len(re.findall(r"_{8,}", corpo)) == 0, (
        "sobrou linha de assinatura no papel da certidão — a da ficha (dentro "
        "do teor) ou outra acrescentada por baixo")
    assert "BEATRIZ EXEMPLO DE SOUZA" in corpo, (
        "tirar os traços não pode levar junto o nome de quem lavrou")


def test_a_conta_dos_atos_e_uma_so_e_mora_no_contexto():
    """O `atos_fora_do_teor` é chamado UMA vez, com a decisão escrita.

    Escrever a conta de novo no outro papel — ou repeti-la para cada tipo de
    documento — faria as duas divergirem no primeiro conserto. E é ela que
    decide se um ato APARECE.
    """
    codigo = (RAIZ / "ri_web.py").read_text(encoding="utf-8")
    i = codigo.index("def contexto_ficha")
    # A função inteira: da linha dela até a rota seguinte. Uma janela de N
    # caracteres mediria menos que a função no dia em que ela crescer — e
    # mediria o vazio dizendo «está certo».
    corpo = codigo[i:codigo.index("\n    @app.route(", i)]
    assert corpo.count("NUMT.atos_fora_do_teor(") == 1, (
        "a conta dos atos fora do teor passou a ser feita duas vezes")
    assert "teor_vai_ao_papel" in corpo, (
        "a decisão de filtrar saiu do contexto — quem chama passa a decidir "
        "por conta própria, e é assim que as duas versões divergem")
