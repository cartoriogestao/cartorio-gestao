"""
Testes da CERTIDAO DO REGISTRO CIVIL, no modelo nacional do CNJ.

O QUE ELES CONFEREM
    A regra, e nao "a funcao devolveu alguma coisa":

      - SEM FILIACAO NAO HA CERTIDAO DE NASCIMENTO, e a recusa diz o que
        fazer. A filiacao e o corpo da certidao — papel sem ela sai
        incompleto, e incompleto e o que o cliente so descobre no INSS;
      - a FILIACAO e a AVOENGA saem no teor, nos blocos do modelo do CNJ e
        com "e" ligando o casal, que e como as 145 certidoes reais escrevem;
      - a MATRICULA SAI COMO ESTA e nao se gera: o verificador dos 32 digitos
        nao se explica, e numero chutado no documento mais definitivo da casa
        e pior que campo vazio;
      - o TEOR CONGELA: averbacao lancada depois nao muda a certidao de
        ontem, e a de hoje ja sai com ela;
      - AVERBACAO ENTRA NO TEOR. Certidao que esconde averbacao e certidao
        que engana — e e o bloco que a inspecao confere;
      - numeracao por exercicio, com UNIQUE guardando; `proximo_numero` SO LE
        (GET nao abre transacao de escrita);
      - a BUSCA acha por nome SEM ACENTO. `UPPER()` do SQLite e ASCII, e no
        Registro Civil quase todo nome tem acento — e este foi o defeito que
        a lista de fraudes teve duas vezes;
      - CANCELAR EXIGE MOTIVO e o teor FICA: a certidao esta na mao de
        alguem, e nao se apaga o que saiu da casa.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import rc_assento as RC                           # noqa: E402
import rc_certidao as CE                          # noqa: E402
from nucleo_schema import init_nucleo_schema      # noqa: E402
from rc_schema import init_rc_schema              # noqa: E402

AGORA = "2026-08-26T09:00:00"
HOJE = "2026-08-26"
EXTENSO = "vinte e seis dias do mês de agosto do ano de dois mil e vinte e seis"
SV = {
    "unit_name": "SERVENTIA EXTRAJUDICIAL DO OFÍCIO ÚNICO DE CIDADE EXEMPLO",
    "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
    "ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA",
}
MATRICULA = "000000015519971000111270010385 01"


def banco() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    init_nucleo_schema(con)
    init_rc_schema(con)
    CE.init_rc_certidao_schema(con)
    return con


def pessoa(con, assento_id, papel, nome, ordem=1):
    con.execute(
        """INSERT INTO rc_pessoas(assento_id, papel, nome, ordem, criado_em)
           VALUES (?,?,?,?,?)""", (assento_id, papel, nome, ordem, AGORA))


def assento_completo(con, nome="JOÃO DA SILVA", especie="NASCIMENTO",
                     com_filiacao=True, com_avos=True, **kw):
    kw.setdefault("origem", "SISTEMA")
    r = RC.lavrar_assento(con, especie=especie, nome=nome, sv=SV, agora=AGORA,
                          data_extenso=EXTENSO, matricula=MATRICULA,
                          data_fato="1997-03-11", **kw)
    aid = r["assento_id"]
    if com_filiacao:
        pessoa(con, aid, "PAI", "JOSÉ DA SILVA", 1)
        pessoa(con, aid, "MAE", "MARIA DAS GRAÇAS SILVA", 2)
    if com_avos:
        pessoa(con, aid, "AVO_PATERNO", "ANTÔNIO DA SILVA", 3)
        pessoa(con, aid, "AVO_PATERNA", "ANA DA SILVA", 4)
        pessoa(con, aid, "AVO_MATERNO", "PEDRO GOMES", 5)
        pessoa(con, aid, "AVO_MATERNA", "RITA GOMES", 6)
    return aid


# ------------------------------------------- sem filiacao nao ha certidao


def test_nascimento_sem_filiacao_e_recusado():
    """A filiacao e o CORPO da certidao de nascimento, nao um campo a mais."""
    con = banco()
    aid = assento_completo(con, com_filiacao=False, com_avos=False)
    with pytest.raises(CE.CertidaoRCPNError):
        CE.emitir(con, aid, sv=SV, hoje=HOJE, agora=AGORA)


def test_a_recusa_diz_que_o_assento_existe_e_o_que_fazer():
    """Recusa que so diz «nao da» manda o escrevente adivinhar."""
    con = banco()
    aid = assento_completo(con, com_filiacao=False, com_avos=False)
    with pytest.raises(CE.CertidaoRCPNError) as erro:
        CE.emitir(con, aid, sv=SV, hoje=HOJE, agora=AGORA)
    texto = str(erro.value)
    assert "existe no livro" in texto
    assert "carga do acervo" in texto


def test_so_a_mae_ja_basta():
    """Registro so com a mae e comum, e a certidao dele sai."""
    con = banco()
    aid = assento_completo(con, com_filiacao=False, com_avos=False)
    pessoa(con, aid, "MAE", "MARIA DAS GRAÇAS SILVA", 2)
    saida = CE.emitir(con, aid, sv=SV, hoje=HOJE, agora=AGORA)
    assert "MARIA DAS GRAÇAS SILVA" in saida["teor"]


def test_obito_sem_filiacao_sai_assim_mesmo():
    """No obito a filiacao ajuda; no nascimento ela E a certidao."""
    con = banco()
    aid = assento_completo(con, nome="JOSÉ ANTIGO", especie="OBITO",
                           com_filiacao=False, com_avos=False)
    saida = CE.emitir(con, aid, sv=SV, hoje=HOJE, agora=AGORA)
    assert "CERTIDÃO DE ÓBITO" in saida["teor"]


# --------------------------------------------- a filiacao e a avoenga


def test_a_filiacao_sai_no_teor():
    con = banco()
    aid = assento_completo(con)
    saida = CE.emitir(con, aid, sv=SV, hoje=HOJE, agora=AGORA)
    assert "FILIAÇÃO:" in saida["teor"]
    assert "JOSÉ DA SILVA e MARIA DAS GRAÇAS SILVA" in saida["teor"]


def test_os_avos_saem_separados_por_lado():
    """PATERNOS e MATERNOS em linhas proprias — o desenho do CNJ."""
    con = banco()
    aid = assento_completo(con)
    teor = CE.emitir(con, aid, sv=SV, hoje=HOJE, agora=AGORA)["teor"]
    assert "PATERNOS:" in teor
    assert "ANTÔNIO DA SILVA e ANA DA SILVA" in teor
    assert "MATERNOS:" in teor
    assert "PEDRO GOMES e RITA GOMES" in teor


def test_um_avo_so_nao_leva_o_e():
    """«FULANO e» seria erro de portugues no papel que a casa assina."""
    con = banco()
    aid = assento_completo(con, com_avos=False)
    pessoa(con, aid, "AVO_PATERNO", "ANTÔNIO DA SILVA", 3)
    teor = CE.emitir(con, aid, sv=SV, hoje=HOJE, agora=AGORA)["teor"]
    assert "ANTÔNIO DA SILVA" in teor
    assert "ANTÔNIO DA SILVA e" not in teor


def test_avo_que_falta_sai_como_nd():
    """O acervo escreve `ND`; a certidao escreve o mesmo."""
    con = banco()
    aid = assento_completo(con, com_avos=False)
    teor = CE.emitir(con, aid, sv=SV, hoje=HOJE, agora=AGORA)["teor"]
    assert CE.SEM_DADO in teor


# ----------------------------------------------------- a matricula


def test_a_matricula_sai_como_esta():
    con = banco()
    aid = assento_completo(con)
    teor = CE.emitir(con, aid, sv=SV, hoje=HOJE, agora=AGORA)["teor"]
    assert "MATRÍCULA Nº" in teor
    assert MATRICULA in teor


def test_o_modulo_nao_gera_matricula():
    """O verificador dos 32 digitos NAO SE EXPLICA — 243 amostras.

    Se alguem acrescentar uma funcao que a gere, este teste fica vermelho: a
    certidao e o documento mais definitivo desta casa, e digito chutado nela
    volta como erro em cartorio de outro estado, anos depois.
    """
    proibidas = [n for n in dir(CE) if not n.startswith("_")
                 and any(p in n.lower() for p in
                         ("gerar_matricula", "montar_matricula",
                          "calcular_matricula", "dv_matricula"))]
    assert proibidas == []


def test_assento_sem_matricula_nao_derruba_a_certidao():
    """Assento antigo do livro de papel nao tem os 32 digitos."""
    con = banco()
    r = RC.lavrar_assento(con, especie="NASCIMENTO", nome="MARIA ANTIGA",
                          sv=SV, agora=AGORA, data_extenso=EXTENSO,
                          origem="SISTEMA")
    pessoa(con, r["assento_id"], "MAE", "JOANA ANTIGA", 2)
    saida = CE.emitir(con, r["assento_id"], sv=SV, hoje=HOJE, agora=AGORA)
    assert saida["numero"] == 1


# ------------------------------------------------ o teor e as averbacoes


def test_averbacao_entra_no_teor():
    """Certidao que esconde averbacao e certidao que engana."""
    con = banco()
    aid = assento_completo(con)
    RC.averbar(con, aid, teor="Retificado o nome do pai por sentença.",
               agora=AGORA)
    teor = CE.emitir(con, aid, sv=SV, hoje=HOJE, agora=AGORA)["teor"]
    assert "Retificado o nome do pai por sentença." in teor


def test_sem_averbacao_o_teor_diz_nada_consta():
    """Bloco vazio faz o leitor achar que faltou imprimir."""
    con = banco()
    aid = assento_completo(con)
    teor = CE.emitir(con, aid, sv=SV, hoje=HOJE, agora=AGORA)["teor"]
    assert "NADA CONSTA." in teor


def test_o_teor_congela():
    """Averbacao de amanha nao muda a certidao de hoje."""
    con = banco()
    aid = assento_completo(con)
    antes = CE.emitir(con, aid, sv=SV, hoje=HOJE, agora=AGORA)
    RC.averbar(con, aid, teor="Averbado o casamento.", agora=AGORA)
    guardada = CE.ler(con, antes["certidao_id"])
    assert "Averbado o casamento." not in guardada["teor"]
    depois = CE.emitir(con, aid, sv=SV, hoje=HOJE, agora=AGORA)
    assert "Averbado o casamento." in depois["teor"]


def test_guarda_quantos_atos_o_assento_tinha():
    """Quem conferir depois sabe se o assento andou."""
    con = banco()
    aid = assento_completo(con)
    primeira = CE.emitir(con, aid, sv=SV, hoje=HOJE, agora=AGORA)
    RC.averbar(con, aid, teor="Averbado o casamento.", agora=AGORA)
    segunda = CE.emitir(con, aid, sv=SV, hoje=HOJE, agora=AGORA)
    assert segunda["atos_no_assento"] == primeira["atos_no_assento"] + 1


def test_o_hash_muda_com_o_teor():
    con = banco()
    aid = assento_completo(con)
    a = CE.emitir(con, aid, sv=SV, hoje=HOJE, agora=AGORA)
    RC.averbar(con, aid, teor="Averbado o casamento.", agora=AGORA)
    b = CE.emitir(con, aid, sv=SV, hoje=HOJE, agora=AGORA)
    assert a["hash"] != b["hash"]
    assert len(a["hash"]) == 64


def test_o_fecho_traz_a_serventia():
    con = banco()
    aid = assento_completo(con)
    teor = CE.emitir(con, aid, sv=SV, hoje=HOJE, agora=AGORA)["teor"]
    assert "O referido é verdade e dou fé." in teor
    assert "CIDADE EXEMPLO" in teor


def test_o_livro_e_a_folha_saem_PREENCHIDOS():
    """O LUGAR MORA NO ATO, e nao no assento — e errar isso e CALADO.

    Eu havia buscado `livro` e `folha` em `rc_assentos`, onde elas nao
    existem. `dict.get` de coluna que nao ha devolve None, e o teor saia com
    `ND` no lugar do livro: certidao que nao diz de onde foi tirada, sem uma
    linha de erro em lugar nenhum. So estourou na busca, por acaso.

    Por isso este teste confere o VALOR, e nao a presenca do rotulo.
    """
    con = banco()
    aid = assento_completo(con)
    teor = CE.emitir(con, aid, sv=SV, hoje=HOJE, agora=AGORA)["teor"]
    linhas = teor.splitlines()
    lugar = CE.lugar_do_assento(con, aid)
    assert lugar["livro"] and lugar["folha"] and lugar["termo"]
    assert linhas[linhas.index("LIVRO") + 1] == str(lugar["livro"])
    assert linhas[linhas.index("FOLHA") + 1] == str(lugar["folha"])
    assert linhas[linhas.index("TERMO") + 1] == str(lugar["termo"])



def test_acervo_sem_registro_preenche_livro_folha_termo():
    """Assento ARQUIVO sem ato REGISTRO ainda tem livro/folha/termo.

    Confirmado no vivo (Eldo id 1222): origem=ARQUIVO, sem rc_atos REGISTRO,
    livro_volume e matrícula preenchidos. Sem o recurso, lugar_do_assento
    devolvia {} → teor com ND e envelope_do_civil recusava a folha (selo=NULL).
    """
    con = banco()
    aid = assento_completo(con, nome="GUSTAVO OLIVEIRA INACIO")
    # Simula acervo/ARQUIVO: apaga o REGISTRO e grava volume + matrícula.
    con.execute("DELETE FROM rc_atos WHERE assento_id=? AND tipo='REGISTRO'",
                (aid,))
    mat = "00000001551994100009141000884223"
    con.execute(
        """UPDATE rc_assentos
              SET origem='ARQUIVO', livro_volume='A-9', matricula=?, numero=8842
            WHERE id=?""", (mat, aid))
    lugar = CE.lugar_do_assento(con, aid)
    assert lugar.get("livro") == "A-9"
    assert str(lugar.get("folha")) == "141"
    assert str(lugar.get("termo")) == "8842"
    teor = CE.emitir(con, aid, sv=SV, hoje=HOJE, agora=AGORA)["teor"]
    linhas = teor.splitlines()
    assert linhas[linhas.index("LIVRO") + 1] == "A-9"
    assert linhas[linhas.index("FOLHA") + 1] == "141"
    assert linhas[linhas.index("TERMO") + 1] == "8842"
    assert "ND" not in (
        linhas[linhas.index("LIVRO") + 1],
        linhas[linhas.index("FOLHA") + 1],
        linhas[linhas.index("TERMO") + 1],
    )



def test_assento_cancelado_se_certifica_E_A_CERTIDAO_DIZ():
    """Recusar seria esconder o que existe; CALAR SERIA MENTIR.

    Certidao de assento cancelado que sai igual a de um assento vivo e o
    documento com que alguem prova o que nao vale mais.

    O ensaio contra o acervo real nao podia achar isto: os 244 assentos de la
    estao todos ATIVOS. Achou-se conferindo o modulo contra `atrib_certidao`,
    que ja tratava o caso no RCPJ/RTD.
    """
    con = banco()
    aid = assento_completo(con)
    con.execute("UPDATE rc_assentos SET situacao='CANCELADO' WHERE id=?", (aid,))
    teor = CE.emitir(con, aid, sv=SV, hoje=HOJE, agora=AGORA)["teor"]
    assert "CANCELADO nesta Serventia" in teor


def test_assento_ativo_nao_diz_que_esta_cancelado():
    """O par do teste de cima: a frase so aparece quando e verdade."""
    con = banco()
    aid = assento_completo(con)
    teor = CE.emitir(con, aid, sv=SV, hoje=HOJE, agora=AGORA)["teor"]
    assert "CANCELADO" not in teor


# ------------------------------------------------------ o casamento


def test_o_casamento_traz_os_dois_conjuges_e_o_regime():
    con = banco()
    r = RC.lavrar_assento(
        con, especie="CASAMENTO", nome="JOÃO DA SILVA", sv=SV, agora=AGORA,
        data_extenso=EXTENSO, origem="SISTEMA",
        dados={"strNomeConjuge1": "JOÃO DA SILVA",
               "strNomeConjuge2": "MARIA DE SOUZA",
               "strRegimeCasamento": "COMUNHÃO PARCIAL DE BENS"})
    teor = CE.emitir(con, r["assento_id"], sv=SV, hoje=HOJE,
                     agora=AGORA)["teor"]
    assert "CERTIDÃO DE CASAMENTO DE:" in teor
    assert "JOÃO DA SILVA e MARIA DE SOUZA" in teor
    assert "COMUNHÃO PARCIAL DE BENS" in teor


def test_casamento_sem_filiacao_sai():
    """No casamento os conjuges estao qualificados nas colunas proprias."""
    con = banco()
    r = RC.lavrar_assento(con, especie="CASAMENTO", nome="JOÃO DA SILVA",
                          sv=SV, agora=AGORA, data_extenso=EXTENSO,
                          origem="SISTEMA")
    assert CE.emitir(con, r["assento_id"], sv=SV, hoje=HOJE,
                     agora=AGORA)["numero"] == 1


# ------------------------------------------------------ a numeracao


def test_numera_por_exercicio():
    con = banco()
    aid = assento_completo(con)
    assert CE.emitir(con, aid, sv=SV, hoje=HOJE, agora=AGORA)["numero"] == 1
    assert CE.emitir(con, aid, sv=SV, hoje=HOJE, agora=AGORA)["numero"] == 2
    assert CE.emitir(con, aid, sv=SV, hoje="2027-01-02",
                     agora=AGORA)["numero"] == 1


def test_o_banco_guarda_o_numero_do_exercicio():
    """Onde a regra pode morar no banco, ela mora no banco."""
    con = banco()
    aid = assento_completo(con)
    CE.emitir(con, aid, sv=SV, hoje=HOJE, agora=AGORA)
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            """INSERT INTO rc_certidoes(numero, ano, assento_id, especie,
                   nome, teor, emitida_em) VALUES (1,2026,?,'NASCIMENTO',
                   'X','x',?)""", (aid, AGORA))


def test_proximo_numero_so_le():
    """GET nao abre transacao de escrita: perguntar nao consome contador."""
    con = banco()
    aid = assento_completo(con)
    assert CE.proximo_numero(con, 2026) == 1
    assert CE.proximo_numero(con, 2026) == 1
    assert CE.emitir(con, aid, sv=SV, hoje=HOJE, agora=AGORA)["numero"] == 1


def test_assento_que_nao_existe_e_erro_de_regra():
    """Erro de regra nao e HTTP 500."""
    con = banco()
    with pytest.raises(CE.CertidaoRCPNError):
        CE.emitir(con, 999, sv=SV, hoje=HOJE, agora=AGORA)


# --------------------------------------------------------- a busca


def test_a_busca_acha_sem_acento():
    """`UPPER()` do SQLite e ASCII — foi o defeito da lista de fraudes."""
    con = banco()
    assento_completo(con, nome="JOÃO ANTÔNIO DA CONCEIÇÃO")
    achados = CE.buscar(con, "joao antonio da conceicao")
    assert len(achados) == 1


def test_a_busca_acha_por_pedaco_do_nome():
    con = banco()
    assento_completo(con, nome="MARIA DAS GRAÇAS SILVA")
    assert len(CE.buscar(con, "gracas")) == 1


def test_a_busca_acha_pela_matricula():
    con = banco()
    assento_completo(con)
    assert len(CE.buscar(con, "000000015519971000111270010385")) == 1


def test_busca_vazia_nao_devolve_a_casa_inteira():
    """Campo em branco que lista tudo e o balcao rolando 244 assentos."""
    con = banco()
    assento_completo(con)
    assert CE.buscar(con, "   ") == []


# ------------------------------------------------------- o cancelamento


def test_cancelar_exige_motivo_escrito():
    con = banco()
    aid = assento_completo(con)
    saida = CE.emitir(con, aid, sv=SV, hoje=HOJE, agora=AGORA)
    with pytest.raises(CE.CertidaoRCPNError):
        CE.cancelar(con, saida["certidao_id"], motivo="erro", agora=AGORA)


def test_cancelar_nao_apaga_o_teor():
    """Ela esta na mao de alguem: o que se registra e o cancelamento."""
    con = banco()
    aid = assento_completo(con)
    saida = CE.emitir(con, aid, sv=SV, hoje=HOJE, agora=AGORA)
    CE.cancelar(con, saida["certidao_id"], agora=AGORA,
                motivo="Erro no nome da mãe, conferido no livro.",
                selo_cancelado_tjma=True, usuario="TABELIÃO")
    linha = CE.ler(con, saida["certidao_id"])
    assert linha["cancelada_em"] == AGORA
    assert linha["teor"] == saida["teor"]
    assert linha["declaracao_selo_tjma_em"] == AGORA
    assert linha["declaracao_selo_tjma_por"] == "TABELIÃO"


def test_cancelar_exige_declaracao_do_selo_no_tjma():
    con = banco()
    aid = assento_completo(con)
    saida = CE.emitir(con, aid, sv=SV, hoje=HOJE, agora=AGORA)
    with pytest.raises(CE.CertidaoRCPNError, match="Portal do Selo do TJMA"):
        CE.cancelar(con, saida["certidao_id"], agora=AGORA,
                    motivo="Erro no nome da mãe, conferido no livro.")
    assert CE.ler(con, saida["certidao_id"])["cancelada_em"] is None


def test_as_certidoes_do_assento_saem_da_mais_nova():
    con = banco()
    aid = assento_completo(con)
    CE.emitir(con, aid, sv=SV, hoje=HOJE, agora=AGORA)
    CE.emitir(con, aid, sv=SV, hoje=HOJE, agora=AGORA)
    lista = CE.do_assento(con, aid)
    assert [x["numero"] for x in lista] == [2, 1]


def test_do_assento_traz_o_selo():
    con = banco()
    aid = assento_completo(con)
    saida = CE.emitir(con, aid, sv=SV, hoje=HOJE, agora=AGORA)
    con.execute("UPDATE rc_certidoes SET selo=? WHERE id=?",
                ("AVESVD000000NARRKWVNJCRSVO21", saida["certidao_id"]))
    lista = CE.do_assento(con, aid)
    assert lista[0]["selo"] == "AVESVD000000NARRKWVNJCRSVO21"


def test_teor_sem_titulo_tira_so_a_primeira_linha():
    titulo = CE.titulo_do_modelo("NASCIMENTO")
    assert titulo.startswith("CERTID")
    corpo = CE.teor_sem_titulo(titulo + "\n\nNOME:\nJOAO", titulo)
    assert not corpo.startswith(titulo)
    assert "NOME:" in corpo
    assert CE.teor_sem_titulo("OUTRA COISA\nNOME:", titulo).startswith("OUTRA")


def test_importado_sem_selo_registro_presume_segunda_via():
    """EOFICIO/ARQUIVO/IMPORTACAO sem REGISTRO selado: certidao e 2a via."""
    con = banco()
    aid = assento_completo(con, nome="TESTE IMPORTADO")
    con.execute("UPDATE rc_assentos SET origem='EOFICIO' WHERE id=?", (aid,))
    con.execute(
        "DELETE FROM rc_atos WHERE assento_id=? AND tipo='REGISTRO'",
        (aid,),
    )
    assert CE.selo_do_registro(con, aid) == ""
    assert CE.eh_primeira_certidao_do_registro(con, aid) is False

    con.execute(
        """INSERT INTO rc_atos (assento_id, tipo, data_ato, selo, criado_em)
           VALUES (?, 'REGISTRO', '2020-01-02', 'REGNAS000000TESTEIMPORT1', ?)""",
        (aid, AGORA),
    )
    assert CE.eh_primeira_certidao_do_registro(con, aid) is True

    aid2 = assento_completo(con, nome="TESTE ARQUIVO")
    con.execute("UPDATE rc_assentos SET origem='ARQUIVO' WHERE id=?", (aid2,))
    con.execute(
        "DELETE FROM rc_atos WHERE assento_id=? AND tipo='REGISTRO'",
        (aid2,),
    )
    assert CE.eh_primeira_certidao_do_registro(con, aid2) is False

    aid3 = assento_completo(con, nome="TESTE IMPORTACAO")
    con.execute(
        "UPDATE rc_assentos SET origem='IMPORTACAO' WHERE id=?", (aid3,))
    con.execute(
        "DELETE FROM rc_atos WHERE assento_id=? AND tipo='REGISTRO'",
        (aid3,),
    )
    assert CE.eh_primeira_certidao_do_registro(con, aid3) is False

