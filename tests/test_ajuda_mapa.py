"""
Testes do MAPA que a ajuda leva junto de cada pergunta.

POR QUE ELES EXISTEM
    O mapa e o que separa uma resposta sobre "cartorio" em tese de uma resposta
    sobre ESTA casa. E ele tem dois jeitos de dar errado, os dois silenciosos:

      1. ENVELHECER. Uma lista escrita a mao envelhece na tarde em que e
         escrita — o menu deste sistema ja pagou por isso. Aqui seria pior:
         quem le a lista velha nao e um operador que estranha, e uma maquina
         que responde com conviccao. Por isso o mapa se MEDE, e ha teste que
         confere que ele mede mesmo.

      2. LEVAR DADO DE CLIENTE JUNTO. O mapa sai da serventia em toda
         pergunta. Se um dia alguem puser valor onde hoje ha nome de coluna, o
         balcao inteiro comeca a vazar sem ninguem pedir — e a mascara nao
         pega, porque a mascara protege o que o escrevente digita, nao o que o
         sistema junta sozinho.

         Por isso o teste monta um banco com CPF, nome e endereco DENTRO e
         procura os tres no mapa.
"""
from __future__ import annotations

import glob
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ajuda_mapa as MAPA

CPF_DO_CLIENTE = "000.000.048-55"
NOME_DO_CLIENTE = "MARIA DAS DORES SOUSA LIMA"


# UM SISTEMA POR ARQUIVO DE TESTE, e nao um por caso: montar o app inteiro
# custa seis segundos, e nenhum destes casos precisa de um banco virgem —
# medir o mapa nao muda o sistema medido. Com um por caso, este arquivo
# sozinho levava um minuto e meio.
@pytest.fixture(scope="module")
def sistema(tmp_path_factory):
    """Um sistema inteiro montado do zero — app, banco e telas."""
    from app import create_app

    dados = tmp_path_factory.mktemp("dados")
    app = create_app({"DATA_DIR": str(dados)})
    con = sqlite3.connect(glob.glob(f"{dados}/*.sqlite3")[0])
    con.row_factory = sqlite3.Row
    MAPA.esquecer()
    yield {"app": app, "con": con}
    con.close()
    MAPA.esquecer()


# ------------------------------------------------------ o mapa se mede


def test_o_mapa_conhece_as_telas_de_verdade(sistema):
    """Medido de `app.url_map`, e nao de uma lista escrita aqui."""
    mapa = MAPA.medir(sistema["app"], sistema["con"], versao="3.6.15")
    assert mapa["quantas_telas"] > 100
    assert "ri_matriculas" in mapa["telas"]
    assert mapa["telas"]["ri_matriculas"]["endereco"] == "/registro-imoveis"


def test_o_nome_da_tela_vem_do_MENU_e_nao_da_minha_cabeca(sistema):
    """Qualquer outro nome seria um segundo vocabulario para a mesma tela.

    Quem perguntasse «onde fica X» ouviria de volta uma palavra que nao esta
    escrita em lugar nenhum da tela dele.
    """
    mapa = MAPA.medir(sistema["app"], sistema["con"])
    nomes = {m["nome"] for m in mapa["menu"]}
    assert "Tabelionato de Notas → Reconhecer firma" in nomes
    assert "Protesto → Títulos" in nomes


def test_o_nome_leva_o_CAMINHO_DO_MENU_e_nao_so_o_rotulo(sistema):
    """Ha TRES «Certidoes» no menu desde 27/08/2026.

    Uma do Registro de Imoveis, uma do Protesto e uma do Registro Civil. Sem o
    grupo, a ajuda responderia «va em Certidoes» a quem pergunta pela certidao
    de nascimento, e o operador acharia a do Registro de Imoveis.

    Com o grupo, a resposta sai como o caminho que se percorre.
    """
    mapa = MAPA.medir(sistema["app"], sistema["con"])
    por_endereco = {m["endereco"]: m["nome"] for m in mapa["menu"]}
    assert por_endereco["/rcpn/certidoes"] == "Registro Civil das Pessoas Naturais → Certidões"
    assert por_endereco["/protesto/certidoes"] == "Protesto → Certidões"
    assert por_endereco["/registro-imoveis/certidoes"]         == "Registro de Imóveis → Certidões"


def test_a_tela_com_dois_nomes_no_menu_guarda_os_dois(sistema):
    """O RCPJ e o RTD sao uma tela so em dois lugares do menu.

    Sao duas atribuicoes sobre a mesma tabela — o acervo do E-Oficio ja as
    guardava juntas. Guardar so o primeiro nome faria a ajuda dizer que o RTD
    nao existe.

    Foi assim que este defeito apareceu: o link do menu passou a levar
    argumento (`atribuicao=3`), a expressao que lia o menu exigia o parentese
    logo depois do nome, e os DOIS links sumiam do mapa em silencio.
    """
    mapa = MAPA.medir(sistema["app"], sistema["con"])
    nome = mapa["telas"]["rcpj_rtd_registros"]["nome"]
    assert "RCPJ" in nome
    assert "RTD" in nome


def test_o_dono_da_tela_sai_do_python_e_nao_do_prefixo(sistema):
    """`protesto_*` e `rcpn_*` moram os dois em `atribuicoes_web.py`.

    Supor o arquivo pelo prefixo do nome mandaria quem conserta para um
    arquivo que nao tem a tela dentro.
    """
    mapa = MAPA.medir(sistema["app"], sistema["con"])
    assert mapa["telas"]["protesto_titulos"]["arquivo"] == "atribuicoes_web.py"
    assert mapa["telas"]["rcpn_assentos"]["arquivo"] == "atribuicoes_web.py"
    assert mapa["telas"]["usucapiao_processos"]["arquivo"] == "usucapiao_web.py"


def test_o_mapa_sabe_que_tabelas_cada_arquivo_abre(sistema):
    mapa = MAPA.medir(sistema["app"], sistema["con"])
    assert "pt_titulos" in mapa["arquivos"]["protesto.py"]["tabelas"]
    assert "ri_matriculas" in mapa["arquivos"]["ri_web.py"]["tabelas"]


def test_o_mapa_diz_o_que_cada_arquivo_e(sistema):
    """A primeira linha da docstring — a frase curta, e nao a historia."""
    mapa = MAPA.medir(sistema["app"], sistema["con"])
    assert mapa["arquivos"]["ajuda.py"]["o_que_e"]
    assert "AJUDA DO SISTEMA" in mapa["arquivos"]["ajuda.py"]["o_que_e"]


# --------------------------------------- o mapa nao leva dado de cliente


def test_o_mapa_nao_carrega_dado_de_cliente(sistema):
    """O QUE ESTE TESTE PROTEGE: o mapa sai da casa em TODA pergunta.

    Ele leva nome de tabela e de coluna, e nunca o conteudo delas. Um mapa que
    levasse valores mandaria o balcao inteiro para fora sem ninguem pedir.
    """
    con = sistema["con"]
    con.execute(
        """INSERT INTO nt_cartoes(numero, nome, nome_norm, documento, endereco,
                                  criado_em)
           VALUES ('1', ?, 'maria', ?, 'Rua do Cliente, 100', '2026-08-26')""",
        (NOME_DO_CLIENTE, CPF_DO_CLIENTE))
    con.commit()

    mapa = MAPA.medir(sistema["app"], con)
    inteiro = repr(mapa)
    assert CPF_DO_CLIENTE not in inteiro
    assert NOME_DO_CLIENTE not in inteiro
    assert "Rua do Cliente" not in inteiro

    resumo = MAPA.resumo(mapa, "notas_cartoes")
    assert CPF_DO_CLIENTE not in resumo
    assert NOME_DO_CLIENTE not in resumo
    # E o nome da COLUNA continua indo, que e o que serve a quem responde.
    assert "documento" in resumo


# --------------------------------------------------- a fatia e o resumo


def test_a_fatia_diz_o_arquivo_e_as_telas_irmas(sistema):
    mapa = MAPA.medir(sistema["app"], sistema["con"])
    f = MAPA.fatia(mapa, "ri_matriculas")
    assert f["tela"]["endereco"] == "/registro-imoveis"
    assert f["arquivo"]["arquivo"] == "ri_web.py"
    assert f["irmas"]


def test_tela_que_nao_existe_devolve_fatia_VAZIA_e_nao_inventada(sistema):
    """Vazia e melhor que inventada.

    A ajuda responde sem o contexto da tela em vez de responder com conviccao
    sobre uma tela que nao e aquela.
    """
    mapa = MAPA.medir(sistema["app"], sistema["con"])
    assert MAPA.fatia(mapa, "tela_que_nunca_existiu") == {}
    assert MAPA.arquivo_da_tela(mapa, "tela_que_nunca_existiu") == ""


def test_o_resumo_manda_nao_inventar_nome_de_tela(sistema):
    """Nome de tela chutado manda o escrevente procurar o que nao existe."""
    resumo = MAPA.resumo(MAPA.medir(sistema["app"], sistema["con"]), "caixa")
    assert "Não invente" in resumo
    assert "não existem neste sistema" in resumo


def test_a_instrucao_sobrevive_ao_mapa_gigante(sistema):
    """**O QUE ENCOLHE E A LISTA, NUNCA A INSTRUCAO.**

    Este teste existe porque o de cima ficou vermelho em 30/08/2026 sem que
    ninguem tivesse mexido na ajuda: entraram as telas dos modelos, do
    checklist e da folha do livro, o mapa passou dos 9.000 caracteres pela
    primeira vez, e o corte — que caia no fim — decepou a instrucao no meio da
    palavra («...nao existe neste sistema. Nao inve»).

    O de cima so pegou o defeito porque o sistema cresceu ate quebrar. Este
    pega ANTES: aperta o teto ate um valor absurdo e cobra que a instrucao
    continue inteira. **Esperar o sistema crescer para descobrir o limite e
    descobrir tarde**, e aqui o sintoma nao seria erro na tela — seria a ajuda
    voltando a inventar nome de tela, calada.
    """
    mapa = MAPA.medir(sistema["app"], sistema["con"])
    antigo = MAPA.LIMITE_DO_RESUMO
    try:
        for teto in (9_000, 2_000, 500, 50):
            MAPA.LIMITE_DO_RESUMO = teto
            resumo = MAPA.resumo(mapa, "caixa")
            assert "Não invente: diga que não achou." in resumo, (
                f"com teto {teto} a instrucao foi cortada — e ela e a unica "
                f"parte do resumo que muda o comportamento de quem le")
            assert "O MAPA DESTA INSTALAÇÃO" in resumo, (
                f"com teto {teto} sumiu ate o cabecalho")
    finally:
        MAPA.LIMITE_DO_RESUMO = antigo


def test_o_corte_nunca_parte_uma_linha_do_menu(sistema):
    """Meia linha de menu e um caminho de menu pela metade — que e exatamente
    o que a instrucao manda nao inventar. Cortar em linha inteira custa alguns
    caracteres e evita que o modelo leia «Registro Civil > Modelos dos te»."""
    mapa = MAPA.medir(sistema["app"], sistema["con"])
    antigo = MAPA.LIMITE_DO_RESUMO
    try:
        MAPA.LIMITE_DO_RESUMO = 1_500
        resumo = MAPA.resumo(mapa, "caixa")
        # A fatia da tela atual entra no miolo junto da lista geral — desde
        # 08/09/2026 ela vem PRIMEIRO, exatamente para sobreviver a um teto
        # apertado —, e as linhas dela também são "inteiras", não sobra de
        # corte.
        inteiras = (set(MAPA._linhas_do_menu(mapa))
                    | set(MAPA._linhas_da_fatia(MAPA.fatia(mapa, "caixa")))
                    | set(MAPA._linhas_das_tabelas_da_fatia(
                        MAPA.fatia(mapa, "caixa"))))
        cortadas = [x for x in resumo.splitlines()
                    if x.startswith("  ") and x not in inteiras
                    and x != MAPA.AVISO_DO_CORTE]
        assert not cortadas, f"linhas partidas no meio: {cortadas[:3]}"
        assert MAPA.AVISO_DO_CORTE in resumo, (
            "cortou e nao disse — mapa que some em silencio faz o modelo "
            "responder como se a parte cortada nao existisse")
    finally:
        MAPA.LIMITE_DO_RESUMO = antigo


def test_A_TELA_ATUAL_SOBREVIVE_QUANDO_A_LISTA_GERAL_NAO_CABE(sistema):
    """O defeito de verdade, achado em 08/09/2026 medindo a produção: o mapa
    já tem 451 telas, e a lista geral sozinha passou a estourar o teto de
    9.000 caracteres — o corte, que sempre poupou cabeça e rodapé, comia a
    fatia da tela atual porque ela vinha DEPOIS da lista inteira no miolo.
    Quem perguntou "onde lanço um depósito prévio?" a partir do Caixa nunca
    soube que a resposta vinha de `caixa_web.py`, porque essa linha nunca
    chegava a sair do corte.

    Este teste aperta o teto ao ponto em que a lista geral NÃO cabe mais, e
    cobra que a fatia da tela sobreviva mesmo assim — o oposto do teste
    anterior, que cobra que a lista sobreviva quando cabe."""
    mapa = MAPA.medir(sistema["app"], sistema["con"])
    antigo = MAPA.LIMITE_DO_RESUMO
    try:
        lista_geral = len("\n".join(MAPA._linhas_do_menu(mapa)))
        MAPA.LIMITE_DO_RESUMO = min(lista_geral, MAPA.LIMITE_DO_RESUMO) // 2
        resumo = MAPA.resumo(mapa, "caixa")
        assert "Mora em caixa_web.py" in resumo, (
            "a lista geral de telas apagou a informação da tela atual — "
            "exatamente o defeito que o oficial pediu para corrigir")
        assert MAPA.AVISO_DO_CORTE in resumo
    finally:
        MAPA.LIMITE_DO_RESUMO = antigo


def test_o_resumo_cabe_no_teto(sistema):
    """Cada pergunta paga o tamanho do que vai junto — e sao 120 por dia."""
    mapa = MAPA.medir(sistema["app"], sistema["con"])
    for onde in ("ri_matriculas", "notas_atos", "caixa", "protesto_titulos"):
        assert len(MAPA.resumo(mapa, onde)) <= MAPA.LIMITE_DO_RESUMO + 60


def test_o_corte_do_resumo_fica_DITO(sistema):
    """Mapa que some em silencio faz o modelo responder como se nao existisse.

    E ele responde com conviccao — que e o que torna o silencio caro aqui.
    """
    mapa = MAPA.medir(sistema["app"], sistema["con"])
    antigo = MAPA.LIMITE_DO_RESUMO
    try:
        MAPA.LIMITE_DO_RESUMO = 500
        resumo = MAPA.resumo(mapa, "caixa")
    finally:
        MAPA.LIMITE_DO_RESUMO = antigo
    assert "cortado aqui pelo tamanho" in resumo


def test_o_mapa_se_mede_uma_vez_por_processo(sistema):
    """Ler noventa arquivos a cada pergunta seria pagar disco por nada.

    O codigo nao muda debaixo do servidor em execucao: atualizar reinicia o
    servico.
    """
    um = MAPA.do_processo(sistema["app"], sistema["con"], versao="3.6.15")
    outro = MAPA.do_processo(sistema["app"], sistema["con"], versao="3.6.15")
    assert um is outro


def test_versao_nova_mede_de_novo(sistema):
    """Versao nova e codigo novo — e mapa velho mandaria a tela que saiu."""
    um = MAPA.do_processo(sistema["app"], sistema["con"], versao="3.6.15")
    outro = MAPA.do_processo(sistema["app"], sistema["con"], versao="3.6.16")
    assert um is not outro


def test_banco_que_nao_responde_nao_derruba_o_mapa(sistema):
    """Mapa que falta e resposta mais pobre; mapa que estoura e tela quebrada."""
    con = sqlite3.connect(":memory:")
    con.close()                        # fechado de proposito
    mapa = MAPA.medir(sistema["app"], con)
    assert mapa["quantas_tabelas"] == 0
    assert mapa["quantas_telas"] > 100     # o resto continua medido


def test_o_mapa_nao_le_os_testes_nem_as_ferramentas():
    """Teste e sobre o sistema, e ferramenta e de quem empacota.

    Nenhum dos dois responde duvida de balcao, e os dois pagariam espaco na
    pergunta.
    """
    assert "tests" in MAPA.PASTAS_QUE_NAO_SAO_O_SISTEMA
    with tempfile.TemporaryDirectory() as pasta:
        assert MAPA._arquivos_do_sistema(Path(pasta)) == {}


# --------------------------------------------- o que mudou entre versoes
#
# ESTE MECANISMO NAO TINHA TESTE NENHUM, e e ele que responde ao oficial «o que
# mudou nesta instalacao» — a metade de «atualizar sozinha» do lembrete dele.
# Medido na producao em 15/09/2026, a resposta era:
#
#     1 tela(s) nova(s): ri_minuta_guardar
#
# O mapa JA SABIA o nome da tela (sai do menu, em `_nomes_do_menu`) e a
# fotografia o jogava fora: quem lê `ri_minuta_guardar` nao tem como saber o
# que isso e. Os testes abaixo guardam as duas metades — o nome quando existe,
# e a verdade quando nao existe.


def _foto(versao, *, telas, nomes=None, menu=None, arquivos=(), tabelas=()):
    """Uma fotografia como `impressao` a grava. So para o teste comparar."""
    if nomes is None:
        nomes = {t: "" for t in telas}
    if menu is None:
        menu = [t for t, rotulo in nomes.items() if rotulo]
    return {"versao": versao, "telas": sorted(telas), "nomes": dict(nomes),
            "menu": sorted(menu), "arquivos": sorted(arquivos),
            "tabelas": sorted(tabelas)}


def test_a_fotografia_leva_o_nome_do_menu_de_cada_tela(sistema):
    """O nome da tela sai do menu, e vai junto do identificador.

    E toda tela tem entrada em `nomes`, mesmo as que nao estao no menu — e o
    que deixa a diferenca perguntar «esta tem nome?» sem consultar o menu, que
    e o que a fotografia antiga nao tem como responder.
    """
    foto = MAPA.impressao(MAPA.medir(sistema["app"], sistema["con"],
                                     versao="3.6.131"))
    assert foto["nomes"]["protesto_titulos"] == "Protesto → Títulos"
    assert set(foto["nomes"]) == set(foto["telas"])
    assert foto["nomes"]["ri_selar_ato"] == "", (
        "as telas de botao (sem item de menu) respondem vazio, e nao somem")


def test_o_que_mudou_chama_a_tela_pelo_NOME_do_menu():
    """«1 tela nova» sem dizer QUAL nao serve a quem le."""
    antes = _foto("3.6.128", telas=["caixa"],
                  nomes={"caixa": "Caixa e protocolo"})
    agora = _foto("3.6.129", telas=["caixa", "ri_selar_ato"],
                  nomes={"caixa": "Caixa e protocolo",
                         "ri_selar_ato": "Registro de Imóveis → Selos"})
    texto = "\n".join(MAPA.resumo_da_diferenca(MAPA.diferenca(antes, agora)))
    assert "«Registro de Imóveis → Selos» (ri_selar_ato)" in texto, texto


def test_a_tela_nova_SEM_item_de_menu_diz_isso_e_de_qual_modulo():
    """Medido em 15/09/2026: as QUATRO telas nascidas depois da 3.6.128
    (`ri_selar_ato`, `ri_descartar_minuta`, `ri_reabrir_matricula`,
    `ri_minuta_guardar`) sao botoes dentro de telas que ja existem, e nao tem
    nome humano nenhum. A pergunta que sobra — «entao onde isso aparece?» —
    tem resposta, e ela vai no texto."""
    antes = _foto("3.6.129", telas=["caixa"],
                  nomes={"caixa": "Caixa e protocolo"})
    agora = _foto("3.6.130", telas=["caixa", "ri_minuta_guardar"],
                  nomes={"caixa": "Caixa e protocolo", "ri_minuta_guardar": ""})
    texto = "\n".join(MAPA.resumo_da_diferenca(MAPA.diferenca(antes, agora)))
    assert ("ri_minuta_guardar (sem item no menu — do Registro de Imóveis)"
            in texto), texto


def test_fotografia_gravada_antes_dos_nomes_nao_vira_mentira():
    """As fotografias ate a 3.6.130 trazem so `menu`: sabem QUEM esta no menu,
    e nao COMO se chama. Dizer «sem item de menu» sobre uma delas seria
    afirmar sobre o menu uma coisa que aquela fotografia nao mediu — e o
    carimbo que mente e pior que carimbo nenhum."""
    velha = {"versao": "3.6.130", "telas": ["caixa", "rcpn_assentos"],
             "menu": ["caixa", "rcpn_assentos"], "arquivos": [], "tabelas": []}
    nova = _foto("3.6.131", telas=["caixa"],
                 nomes={"caixa": "Caixa e protocolo"})
    texto = "\n".join(MAPA.resumo_da_diferenca(MAPA.diferenca(velha, nova)))
    assert "rcpn_assentos (no menu)" in texto, texto
    assert "sem item no menu" not in texto, (
        "a fotografia antiga nao mediu isso, e o texto nao pode afirmar")


def test_a_mesma_fotografia_duas_vezes_nao_inventa_mudanca():
    """«Nada mudou» e uma resposta, e nao a falta de resposta."""
    foto = _foto("3.6.131", telas=["caixa"], nomes={"caixa": "Caixa"})
    iguais = MAPA.resumo_da_diferenca(MAPA.diferenca(foto, dict(foto)))
    assert len(iguais) == 1 and "nada mudou" in iguais[0], iguais

    # E SEM ANTERIOR NAO SE DIZ NADA — lista vazia se lê como «nada mudou», e
    # na primeira versao de uma instalacao nao ha o que comparar.
    assert MAPA.diferenca(None, foto) == {}
    assert MAPA.resumo_da_diferenca({}) == []
    assert MAPA.resumo_da_diferenca(None) == []
