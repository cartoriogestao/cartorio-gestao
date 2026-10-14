"""
Testes da escrituracao do nucleo — o livro, a folha, a ordem e os termos, para
as seis atribuicoes com um codigo so.

O QUE ELES CONFEREM
    A regra, e nao "a funcao devolveu alguma coisa":

      - a numeracao de ordem e continua por SERIE e por SERVENTIA, e nao
        reinicia quando o livro vira (foi contar por volume que abriu a
        matricula 4011 depois de a 4013 existir, em 18/08/2026);
      - duas faces iguais no mesmo livro nao entram — nem com duas conexoes
        gravando ao mesmo tempo;
      - serie de folha nova nunca divide folha; serie de varios por folha
        enche a face antes de virar;
      - livro cheio encerra com termo e o seguinte abre com termo;
      - quem transborda nao parte o ato entre dois livros;
      - folha escriturada NAO se inutiliza — o ato nela e que se cancela;
      - livro diario encerra todo dia, inclusive dia sem movimento;
      - expurgo solta o lugar mas NAO devolve o numero de ordem.
"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import escrituracao as E                        # noqa: E402
import livro_nucleo as LN                       # noqa: E402
from nucleo_schema import init_nucleo_schema    # noqa: E402

AGORA = "2026-08-21T10:00:00"
EXTENSO = "vinte e um dias do mês de agosto do ano de dois mil e vinte e seis"
SV = {
    "unit_name": "SERVENTIA EXTRAJUDICIAL DO OFÍCIO ÚNICO DE CIDADE EXEMPLO",
    "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
    "serventia_titulo": "Tabelião e Oficial de Registro",
    "ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA",
}


def banco(caminho: str = ":memory:") -> sqlite3.Connection:
    con = sqlite3.connect(caminho)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    init_nucleo_schema(con)
    return con


def reservar(con, serie, referencia, *, paginas=1, dia=None, tabela="atos_de_teste"):
    return E.reservar(con, serie, tabela, referencia, sv=SV, agora=AGORA,
                      data_extenso=EXTENSO, paginas=paginas, dia=dia,
                      usuario="TESTE")


# ------------------------------------------------------- as seis atribuicoes

def test_o_nucleo_atende_as_seis_atribuicoes():
    # Registro de Imoveis nao tem serie de livro aqui: a matricula e ficha, e
    # mora em ri_matriculas. As outras cinco tem.
    atribuicoes = {s.atribuicao for s in LN.SERIES.values()}
    assert atribuicoes == {1, 2, 3, 4, 6}
    assert len(LN.SERIES) == 24


def test_toda_serie_conhecida_abre_livro_e_recebe_ato():
    con = banco()
    for codigo, s in LN.SERIES.items():
        dia = "2026-08-21" if s.diario else None
        lugar = reservar(con, codigo, hash(codigo) % 100000, dia=dia)
        assert lugar["numero_ordem"] == 1, codigo
        assert lugar["folha"] == 1, codigo
        assert lugar["livro_numero"] == "1", codigo


# ------------------------------------------------------------- a numeracao

def test_a_numeracao_e_continua_e_nao_reinicia_no_livro_novo():
    # O defeito de 18/08/2026, virado do avesso: a numeracao segue a SERIE.
    con = banco()
    livro1 = E.abrir_livro(con, "RC_A", sv=SV, agora=AGORA,
                           data_extenso=EXTENSO, folhas=3)
    for i in range(1, 4):
        assert reservar(con, "RC_A", i)["numero_ordem"] == i
    # A quarta reserva nao cabe: encerra o livro 1 e abre o 2.
    quarta = reservar(con, "RC_A", 4)
    assert quarta["livro_id"] != livro1
    assert quarta["livro_numero"] == "2"
    assert quarta["folha"] == 1            # folha reinicia
    assert quarta["numero_ordem"] == 4     # o numero de ordem NAO


def test_a_numeracao_e_por_serie_e_nao_por_atribuicao():
    con = banco()
    assert reservar(con, "RC_A", 1)["numero_ordem"] == 1
    assert reservar(con, "RC_B", 2)["numero_ordem"] == 1
    assert reservar(con, "RC_A", 3)["numero_ordem"] == 2


def test_consultar_o_proximo_numero_nao_escreve_nada():
    # Tela de leitura le. GET que abre transacao de escrita fica preso no
    # busy_timeout enquanto outro balcao lavra, e depois devolve 500.
    con = banco()
    assert E.proximo_numero(con, "RC_A", consumir=False) == 1
    assert E.proximo_numero(con, "RC_A", consumir=False) == 1
    assert con.execute("SELECT COUNT(*) n FROM nu_numeracao").fetchone()["n"] == 0


def test_a_numeracao_e_semeada_do_que_ja_existe():
    con = banco()
    livro = E.abrir_livro(con, "RC_C", sv=SV, agora=AGORA, data_extenso=EXTENSO)
    con.execute(
        """INSERT INTO nu_lugares(livro_id, serie, folha, verso, ordem, rotulo,
               inicio, paginas, numero_ordem, tabela, referencia, ocupado_em)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (livro, "RC_C", 40, 0, 1, "40", 1, 1, 812, "acervo", 9001, AGORA))
    assert reservar(con, "RC_C", 1)["numero_ordem"] == 813


def test_fixar_a_numeracao_recusa_repetir_numero():
    con = banco()
    reservar(con, "RC_A", 1)
    reservar(con, "RC_A", 2)
    with pytest.raises(E.LivroError) as erro:
        E.fixar_numeracao(con, "RC_A", 2, usuario="TESTE",
                          motivo="acerto", agora=AGORA)
    assert "repetiria" in str(erro.value)
    assert E.fixar_numeracao(con, "RC_A", 50, usuario="TESTE",
                             motivo="acerto do livro fisico", agora=AGORA) == 50
    assert reservar(con, "RC_A", 3)["numero_ordem"] == 50


# ---------------------------------------------------------------- a folha

def test_serie_de_folha_nova_nunca_divide_folha():
    con = banco()
    a = reservar(con, "RC_A", 1)
    b = reservar(con, "RC_A", 2)
    assert a["folha"] == 1 and b["folha"] == 2


def test_serie_de_varios_por_face_enche_a_face_antes_de_virar():
    con = banco()
    # Livro de Registro de Pagamentos: 120 por folha, e a origem nao escritura
    # verso — logo a folha tem uma face, e depois dela vem a folha 2.
    s = LN.serie("PT_PAGAMENTO")
    assert s.por_face == 120 and s.usa_verso is False
    for i in range(1, s.por_face + 1):
        lugar = reservar(con, "PT_PAGAMENTO", i)
        assert lugar["folha"] == 1 and lugar["verso"] is False, i
        assert lugar["ordem"] == i
    virou = reservar(con, "PT_PAGAMENTO", s.por_face + 1)
    assert virou["folha"] == 2 and virou["verso"] is False
    assert virou["ordem"] == 1


def test_no_livro_de_protestos_o_verso_recebe_o_protesto_seguinte():
    # Medido no acervo: os livros 7 e 8 fecharam com 207 e 219 registros em
    # 200 folhas. Nao e folha nova — e um por FACE.
    con = banco()
    a = reservar(con, "PT_PROTESTO", 1)
    b = reservar(con, "PT_PROTESTO", 2)
    c = reservar(con, "PT_PROTESTO", 3)
    assert (a["folha"], a["verso"]) == (1, False)
    assert (b["folha"], b["verso"]) == (1, True)
    assert (c["folha"], c["verso"]) == (2, False)


def test_o_ato_de_paginas_pares_ocupa_folhas_inteiras():
    con = banco()
    lugar = reservar(con, "NT_ESCRITURA", 1, paginas=3)
    assert lugar["faces"] == ["1", "1v", "2"]
    assert lugar["sobra"] == ["2v"]
    # O ato seguinte comeca na folha 3, e nao no verso da 2.
    assert reservar(con, "NT_ESCRITURA", 2)["folha"] == 3


def test_duas_faces_iguais_nao_entram():
    con = banco()
    livro = E.abrir_livro(con, "RC_A", sv=SV, agora=AGORA, data_extenso=EXTENSO)
    reservar(con, "RC_A", 1)
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            """INSERT INTO nu_lugares(livro_id, serie, folha, verso, ordem, rotulo,
                   inicio, paginas, numero_ordem, tabela, referencia, ocupado_em)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (livro, "RC_A", 1, 0, 1, "1", 1, 1, 99, "outra_tabela", 5, AGORA))


def test_um_ato_tem_um_lugar_de_inicio_e_nao_dois():
    con = banco()
    reservar(con, "RC_A", 77)
    with pytest.raises(E.LivroError) as erro:
        reservar(con, "RC_A", 77)
    assert "um lugar e não dois" in str(erro.value)
    # E a trava esta no banco tambem, e nao so no if: indice unico parcial
    # sobre (tabela, referencia) onde inicio=1.
    livro = E.livro_da_vez(con, "RC_A")
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            """INSERT INTO nu_lugares(livro_id, serie, folha, verso, ordem, rotulo,
                   inicio, paginas, numero_ordem, tabela, referencia, ocupado_em)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (int(livro["id"]), "RC_A", 9, 0, 1, "9", 1, 1, 90,
             "atos_de_teste", 77, AGORA))


def test_um_numero_de_ordem_aparece_uma_vez_por_livro():
    con = banco()
    livro = E.abrir_livro(con, "RC_A", sv=SV, agora=AGORA, data_extenso=EXTENSO)
    reservar(con, "RC_A", 1)
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            """INSERT INTO nu_lugares(livro_id, serie, folha, verso, ordem, rotulo,
                   inicio, paginas, numero_ordem, tabela, referencia, ocupado_em)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (livro, "RC_A", 8, 0, 1, "8", 1, 1, 1, "outra", 9, AGORA))


def test_duas_conexoes_nao_pegam_a_mesma_folha():
    # Corrida de verdade: dois processos, dois arquivos de conexao, o banco
    # como arbitro. Teste de corrida com uma conexao so nao testa corrida.
    with tempfile.TemporaryDirectory() as pasta:
        caminho = str(Path(pasta) / "b.sqlite3")
        a, b = banco(caminho), banco(caminho)
        try:
            for con in (a, b):
                con.execute("PRAGMA busy_timeout = 3000")
            E.abrir_livro(a, "RC_A", sv=SV, agora=AGORA, data_extenso=EXTENSO)
            a.commit()
            a.execute("BEGIN IMMEDIATE")
            reservar(a, "RC_A", 1)
            with pytest.raises(sqlite3.OperationalError):
                b.execute("BEGIN IMMEDIATE")
                reservar(b, "RC_A", 2)
            a.commit()
            b.rollback()
            assert reservar(b, "RC_A", 2)["folha"] == 2
        finally:
            # AS DUAS CONEXOES FICAVAM ABERTAS ATE O FIM DO TESTE, e no
            # Windows arquivo aberto nao se apaga: a limpeza da pasta
            # temporaria estourava (NotADirectoryError) DEPOIS de todas as
            # verificacoes terem passado. O suite ficava vermelho por causa
            # da faxina, e nao da regra que o teste confere.
            a.close()
            b.close()


# ---------------------------------------------------------------- o livro

def test_o_livro_nasce_com_termo_de_abertura():
    con = banco()
    livro_id = E.abrir_livro(con, "RC_A", sv=SV, agora=AGORA,
                             data_extenso=EXTENSO)
    termo = con.execute("SELECT termo_abertura FROM nu_livros WHERE id=?",
                        (livro_id,)).fetchone()["termo_abertura"]
    assert "TERMO DE ABERTURA" in termo
    assert "Livro A — Registro de Nascimento" in termo
    assert "300 (trezentas) folhas" in termo
    assert "CNS 000000" in termo


def test_nao_se_abre_um_segundo_livro_aberto_na_mesma_serie():
    con = banco()
    E.abrir_livro(con, "RC_A", sv=SV, agora=AGORA, data_extenso=EXTENSO)
    with pytest.raises(E.LivroError) as erro:
        E.abrir_livro(con, "RC_A", sv=SV, agora=AGORA, data_extenso=EXTENSO)
    assert "Encerre-o antes" in str(erro.value)


def test_o_termo_de_encerramento_diz_o_que_ficou_em_branco():
    con = banco()
    livro = E.abrir_livro(con, "RC_A", sv=SV, agora=AGORA,
                          data_extenso=EXTENSO, folhas=10)
    reservar(con, "RC_A", 1)
    teor = E.encerrar_livro(con, livro, sv=SV, agora=AGORA,
                            data_extenso=EXTENSO, motivo="mudança de série")
    assert "TERMO DE ENCERRAMENTO" in teor
    assert "folhas de 2 (duas) a 10 (dez) ficam INUTILIZADAS" in teor
    assert "mudança de série" in teor


def test_livro_encerrado_nao_encerra_de_novo():
    con = banco()
    livro = E.abrir_livro(con, "RC_A", sv=SV, agora=AGORA, data_extenso=EXTENSO)
    E.encerrar_livro(con, livro, sv=SV, agora=AGORA, data_extenso=EXTENSO)
    with pytest.raises(E.LivroError):
        E.encerrar_livro(con, livro, sv=SV, agora=AGORA, data_extenso=EXTENSO)


def test_quem_transborda_nao_parte_o_ato_entre_dois_livros():
    # Livro A do RCPJ: o ultimo registro passa do fim do livro em vez de ser
    # cortado no meio.
    con = banco()
    livro = E.abrir_livro(con, "PJ_A", sv=SV, agora=AGORA,
                          data_extenso=EXTENSO, folhas=2)
    reservar(con, "PJ_A", 1)
    reservar(con, "PJ_A", 2)
    terceiro = reservar(con, "PJ_A", 3)
    assert terceiro["livro_id"] == livro      # nao abriu livro novo
    assert terceiro["folha"] == 3             # transbordou


# ---------------------------------------------------------- a inutilizacao

def test_folha_escriturada_nao_se_inutiliza():
    con = banco()
    lugar = reservar(con, "RC_A", 1)
    with pytest.raises(E.LivroError) as erro:
        E.inutilizar(con, lugar["livro_id"], "1",
                     motivo="quero apagar este ato",
                     sv=SV, agora=AGORA, data_extenso=EXTENSO)
    assert "não se inutiliza" in str(erro.value)


def test_a_inutilizacao_exige_motivo_escrito():
    con = banco()
    livro = E.abrir_livro(con, "RC_A", sv=SV, agora=AGORA, data_extenso=EXTENSO)
    with pytest.raises(E.LivroError) as erro:
        E.inutilizar(con, livro, "5", motivo="erro", sv=SV, agora=AGORA,
                     data_extenso=EXTENSO)
    assert "dez letras" in str(erro.value)


def test_a_face_inutilizada_nao_recebe_ato_depois():
    con = banco()
    s = LN.serie("PT_PROTOCOLO")
    livro = E.abrir_livro(con, "PT_PROTOCOLO", sv=SV, agora=AGORA,
                          data_extenso=EXTENSO, dia="2026-08-21")
    E.inutilizar(con, livro, "1", motivo="folha rasgada na impressão",
                 sv=SV, agora=AGORA, data_extenso=EXTENSO)
    lugar = reservar(con, "PT_PROTOCOLO", 1, dia="2026-08-21")
    assert lugar["rotulo"] == "1v"
    assert s.por_face > 1 and s.usa_verso is True


def test_no_apontamento_sem_verso_a_folha_inutilizada_pula_para_a_seguinte():
    con = banco()
    livro = E.abrir_livro(con, "PT_APONTAMENTO", sv=SV, agora=AGORA,
                          data_extenso=EXTENSO)
    E.inutilizar(con, livro, "1", motivo="folha rasgada na impressão",
                 sv=SV, agora=AGORA, data_extenso=EXTENSO)
    assert reservar(con, "PT_APONTAMENTO", 1)["rotulo"] == "2"
    # E inutilizar verso de livro que nao tem verso e recusado.
    with pytest.raises(E.LivroError) as erro:
        E.inutilizar(con, livro, "3v", motivo="verso que nao existe aqui",
                     sv=SV, agora=AGORA, data_extenso=EXTENSO)
    assert "não escritura o verso" in str(erro.value)


def test_a_sobra_do_ato_se_inutiliza_com_termo_proprio():
    con = banco()
    lugar = reservar(con, "NT_ESCRITURA", 1, paginas=3)
    assert lugar["sobra"] == ["2v"]
    # A reserva NAO inutiliza por conta propria: inutilizar e ato do oficial.
    assert con.execute("SELECT COUNT(*) n FROM nu_inutilizacoes").fetchone()["n"] == 0
    feitas = E.inutilizar_sobra(con, "atos_de_teste", 1, sv=SV, agora=AGORA,
                                data_extenso=EXTENSO)
    assert feitas == ["2v"]
    linha = con.execute("SELECT * FROM nu_inutilizacoes").fetchone()
    assert linha["origem"] == "SOBRA"
    assert "FOLHA INUTILIZADA" in linha["teor"]
    assert "n. 1" in linha["motivo"]
    # Chamar duas vezes nao duplica.
    assert E.inutilizar_sobra(con, "atos_de_teste", 1, sv=SV, agora=AGORA,
                              data_extenso=EXTENSO) == []


def test_a_inutilizacao_recusa_folha_fora_do_livro():
    con = banco()
    livro = E.abrir_livro(con, "RC_A", sv=SV, agora=AGORA,
                          data_extenso=EXTENSO, folhas=10)
    with pytest.raises(E.LivroError) as erro:
        E.inutilizar(con, livro, "11", motivo="folha que nao existe aqui",
                     sv=SV, agora=AGORA, data_extenso=EXTENSO)
    assert "fora do Livro" in str(erro.value)


# --------------------------------------------------------- o livro diario

def test_a_serie_diaria_exige_o_dia():
    con = banco()
    with pytest.raises(E.LivroError) as erro:
        E.abrir_livro(con, "PT_PROTOCOLO", sv=SV, agora=AGORA,
                      data_extenso=EXTENSO)
    assert "livro diário" in str(erro.value)


def test_cada_dia_tem_o_seu_livro_de_protocolo():
    con = banco()
    a = reservar(con, "PT_PROTOCOLO", 1, dia="2026-08-20")
    b = reservar(con, "PT_PROTOCOLO", 2, dia="2026-08-21")
    assert a["livro_id"] != b["livro_id"]


def test_o_protocolo_do_protesto_reinicia_a_numeracao_todo_dia():
    # `tbProtocoloProtesto` guarda um intProtocolo_Ultimo POR DATA, de 1 a 6.
    # Numeracao continua faria o protocolo do dia sair como 2.157 em vez de 3.
    con = banco()
    assert reservar(con, "PT_PROTOCOLO", 1, dia="2026-08-20")["numero_ordem"] == 1
    assert reservar(con, "PT_PROTOCOLO", 2, dia="2026-08-20")["numero_ordem"] == 2
    assert reservar(con, "PT_PROTOCOLO", 3, dia="2026-08-21")["numero_ordem"] == 1
    assert reservar(con, "PT_PROTOCOLO", 4, dia="2026-08-21")["numero_ordem"] == 2
    # E nao existe contador para corrigir a mao numa série assim.
    with pytest.raises(E.LivroError) as erro:
        E.fixar_numeracao(con, "PT_PROTOCOLO", 90, usuario="TESTE",
                          motivo="acerto", agora=AGORA)
    assert "reinicia sozinha" in str(erro.value)
    # O apontamento, ao lado, continua contínuo.
    assert reservar(con, "PT_APONTAMENTO", 5)["numero_ordem"] == 1
    assert reservar(con, "PT_APONTAMENTO", 6)["numero_ordem"] == 2


def test_o_dia_sem_movimento_tambem_se_encerra():
    con = banco()
    fecho = E.encerrar_o_dia(con, "PJ_PROTOCOLO", "2026-08-21", sv=SV,
                             agora=AGORA, dia_extenso=EXTENSO)
    assert fecho["quantidade"] == 0
    assert "Não houve movimento neste dia" in fecho["teor"]


def test_o_dia_encerrado_nao_se_encerra_de_novo():
    con = banco()
    reservar(con, "TD_PROTOCOLO", 1, dia="2026-08-21")
    fecho = E.encerrar_o_dia(con, "TD_PROTOCOLO", "2026-08-21", sv=SV,
                             agora=AGORA, dia_extenso=EXTENSO)
    assert fecho["quantidade"] == 1
    assert "1 (um) títulos ou documentos" in fecho["teor"]
    with pytest.raises(E.LivroError):
        E.encerrar_o_dia(con, "TD_PROTOCOLO", "2026-08-21", sv=SV,
                         agora=AGORA, dia_extenso=EXTENSO)


def test_a_tela_mostra_os_dias_que_ficaram_abertos_atras():
    con = banco()
    reservar(con, "PT_PROTOCOLO", 1, dia="2026-08-19")
    reservar(con, "PT_PROTOCOLO", 2, dia="2026-08-20")
    E.encerrar_o_dia(con, "PT_PROTOCOLO", "2026-08-20", sv=SV, agora=AGORA,
                     dia_extenso=EXTENSO)
    assert E.dias_sem_encerrar(con, "PT_PROTOCOLO") == ["2026-08-19"]
    assert E.dias_sem_encerrar(con, "RC_A") == []


def test_serie_que_nao_e_diaria_nao_tem_encerramento_diario():
    con = banco()
    with pytest.raises(E.LivroError) as erro:
        E.encerrar_o_dia(con, "RC_A", "2026-08-21", sv=SV, agora=AGORA,
                         dia_extenso=EXTENSO)
    assert "não é livro diário" in str(erro.value)


# ------------------------------------------------------------- o expurgo

def test_expurgo_solta_o_lugar_mas_nao_devolve_o_numero():
    con = banco()
    reservar(con, "RC_A", 1)
    reservar(con, "RC_A", 2)
    assert E.liberar(con, "atos_de_teste", 2) == 1
    assert E.lugar_de(con, "atos_de_teste", 2) is None
    # O numero 2 NAO volta: ele ja apareceu em ata de ocorrencia.
    assert reservar(con, "RC_A", 3)["numero_ordem"] == 3


def test_a_folha_liberada_volta_a_ser_usada():
    con = banco()
    reservar(con, "RC_A", 1)
    reservar(con, "RC_A", 2)
    E.liberar(con, "atos_de_teste", 2)
    assert reservar(con, "RC_A", 3)["folha"] == 2


# ---------------------------------------------------------- a conferencia

def test_a_conferencia_acha_folha_em_branco_no_meio_do_livro():
    con = banco()
    livro = E.abrir_livro(con, "RC_A", sv=SV, agora=AGORA,
                          data_extenso=EXTENSO, folhas=10)
    reservar(con, "RC_A", 1)
    reservar(con, "RC_A", 2)
    E.liberar(con, "atos_de_teste", 1)      # deixa a folha 1 vazia
    achados = E.conferir_livro(con, livro)["achados"]
    assert any("em branco no meio do livro" in a for a in achados)


def test_a_conferencia_de_livro_em_ordem_nao_acha_nada():
    con = banco()
    livro = E.abrir_livro(con, "RC_A", sv=SV, agora=AGORA,
                          data_extenso=EXTENSO, folhas=10)
    for i in (1, 2):
        reservar(con, "RC_A", i)
        # O Livro A comeca cada registro em folha nova; o verso que sobra tem
        # de ser inutilizado, e e isto que a inspecao de 12/08 cobrou.
        assert E.inutilizar_sobra(con, "atos_de_teste", i, sv=SV, agora=AGORA,
                                  data_extenso=EXTENSO) == [f"{i}v"]
    conf = E.conferir_livro(con, livro)
    assert conf["achados"] == []
    assert conf["atos"] == 2
    assert conf["serie_nome"] == "Livro A — Registro de Nascimento"


def test_a_conferencia_cobra_o_encerramento_do_dia():
    con = banco()
    lugar = reservar(con, "PT_PROTOCOLO", 1, dia="2026-08-21")
    achados = E.conferir_livro(con, lugar["livro_id"])["achados"]
    assert any("encerramento diário" in a for a in achados)


def test_o_panorama_mostra_as_series_da_atribuicao():
    con = banco()
    reservar(con, "RC_A", 1)
    linhas = E.panorama(con, 6)
    assert len(linhas) == 7
    a = next(x for x in linhas if x["serie"] == "RC_A")
    assert a["atos"] == 1 and a["livro_numero"] == "1" and a["folha_livre"] == 2
    b = next(x for x in linhas if x["serie"] == "RC_B")
    assert b["livro_id"] is None and b["proximo_numero"] == 1


def test_o_panorama_nao_consome_numeracao():
    con = banco()
    E.panorama(con)
    E.panorama(con)
    assert con.execute("SELECT COUNT(*) n FROM nu_numeracao").fetchone()["n"] == 0


# ------------------------------------------------------------- as mensagens

def test_a_serie_desconhecida_da_mensagem_de_balcao_e_nao_KeyError():
    con = banco()
    with pytest.raises(E.LivroError) as erro:
        E.abrir_livro(con, "LIVRO_QUE_NAO_EXISTE", sv=SV, agora=AGORA,
                      data_extenso=EXTENSO)
    assert "não existe no núcleo" in str(erro.value)
