"""
Testes da numeracao de livro, folha e termo do Tabelionato de Notas.

O QUE ELES CONFEREM
    A regra desta serventia, e nao "a funcao devolveu alguma coisa":

      - cada ato comeca em FOLHA NOVA, e nunca divide folha com outro;
      - conta-se frente e verso, e o ato ocupa folhas inteiras (paginas PARES);
      - o TERMO e continuo por serie e NAO reinicia quando o livro vira;
      - livro cheio encerra sozinho e o seguinte abre sozinho;
      - ato nao se parte entre dois livros;
      - o ACERVO importado nao e renumerado nem estorvado.

COMO RODAM
    Com PRAGMA foreign_keys ligado, como a producao — e com duas conexoes de
    verdade no teste de concorrencia, porque teste de corrida com uma conexao
    so nao testa corrida nenhuma.
"""
from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import notas_livro as NL                       # noqa: E402
from notas_schema import init_notas_schema     # noqa: E402

AGORA = "2026-08-17T10:00:00"
EXTENSO = "dezessete dias do mês de agosto do ano de dois mil e vinte e seis"
SV = {
    "unit_name": "SERVENTIA EXTRAJUDICIAL DE CIDADE EXEMPLO",
    "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
    "serventia_titulo": "Tabelião e Oficial de Registro",
    "ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA",
}


def banco() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    init_notas_schema(con)
    return con


def novo_ato(con, tipo="ESCRITURA", teor="teor", data="2026-08-17") -> int:
    cur = con.execute(
        """INSERT INTO nt_atos(tipo, serie, data, situacao, teor, criado_em)
           VALUES (?,?,?, 'EM_LAVRATURA', ?, ?)""",
        (tipo, NL.LIVRO_DO_ATO.get(tipo), data, teor, AGORA))
    return int(cur.lastrowid)


def lancar(con, ato_id, paginas):
    return NL.lancar_ato(con, ato_id, SV, AGORA, EXTENSO, paginas=paginas,
                         usuario="TESTE")


# ------------------------------------------------------------- aritmetica

def test_a_folha_tem_frente_e_verso():
    assert NL.rotulo_folha(12) == "12"
    assert NL.rotulo_folha(12, verso=True) == "12v"
    assert NL.rotulo_folha(None) == ""


def test_uma_pagina_ainda_ocupa_uma_folha_inteira():
    # O ato comeca em folha nova. Escrevendo so a frente, o verso e dele
    # mesmo — e fica inutilizado, nao vai para o ato seguinte.
    assert NL.folhas_de(1) == 1
    assert NL.paginas_reservadas(NL.folhas_de(1)) == 2


def test_as_paginas_reservadas_sao_sempre_pares():
    for paginas in range(1, 40):
        reservadas = NL.paginas_reservadas(NL.folhas_de(paginas))
        assert reservadas % 2 == 0
        assert reservadas >= paginas


def test_tres_paginas_ocupam_duas_folhas():
    assert NL.folhas_de(3) == 2
    assert NL.folhas_de(4) == 2
    assert NL.folhas_de(5) == 3


def test_inteiro_le_o_numero_de_dentro_do_texto():
    assert NL.inteiro("12v") == 12
    assert NL.inteiro("fl. 139") == 139
    assert NL.inteiro("") is None
    assert NL.inteiro("XII") is None
    assert NL.inteiro(None) is None


def test_por_extenso_no_feminino_para_folhas():
    assert NL.por_extenso(200, feminino=True) == "duzentas"
    assert NL.por_extenso(2, feminino=True) == "duas"
    assert NL.por_extenso(100) == "cem"
    assert NL.por_extenso(1000) == "mil"
    assert NL.com_algarismos(200, feminino=True) == "200 (duzentas)"


def test_a_estimativa_erra_para_mais_e_nunca_para_zero():
    assert NL.estimar_paginas("") == 1
    assert NL.estimar_paginas("<p></p>") == 1
    assert NL.estimar_paginas("x" * (NL.CARACTERES_POR_PAGINA + 1)) == 2


# ------------------------------------------------------------- folha nova

def test_cada_ato_comeca_em_folha_nova():
    con = banco()
    NL.abrir_livro(con, "ESCRITURA", SV, AGORA, EXTENSO, folhas=200)
    a = lancar(con, novo_ato(con), paginas=1)     # ocupa a folha 1 inteira
    b = lancar(con, novo_ato(con), paginas=1)
    assert a["folha"] == "1" and a["folha_final"] == "1"
    # O texto so cobriu a frente. O verso NAO e do ato seguinte: inutiliza-se.
    assert a["inutilizar"] == "1v"
    assert a["paginas_reservadas"] == 2
    assert b["folha"] == "2"


def test_o_ato_de_tres_paginas_ocupa_duas_folhas_e_o_seguinte_comeca_na_terceira():
    con = banco()
    NL.abrir_livro(con, "ESCRITURA", SV, AGORA, EXTENSO, folhas=200)
    a = lancar(con, novo_ato(con), paginas=3)
    b = lancar(con, novo_ato(con), paginas=2)
    assert (a["folha"], a["folha_final"], a["folhas"]) == ("1", "2", 2)
    # Terminou na FRENTE da folha 2: o verso 2v tem de ser inutilizado.
    assert a["inutilizar"] == "2v"
    assert (b["folha"], b["folha_final"]) == ("3", "3v")
    assert b["inutilizar"] is None


def test_nao_ha_verso_a_inutilizar_quando_o_texto_termina_no_verso():
    con = banco()
    NL.abrir_livro(con, "ESCRITURA", SV, AGORA, EXTENSO, folhas=200)
    feito = lancar(con, novo_ato(con), paginas=4)
    assert feito["folha_final"] == "2v"
    assert feito["inutilizar"] is None


def test_duas_escrituras_nao_caem_na_mesma_folha():
    con = banco()
    NL.abrir_livro(con, "ESCRITURA", SV, AGORA, EXTENSO, folhas=200)
    folhas = {lancar(con, novo_ato(con), paginas=2)["folha"] for _ in range(20)}
    assert len(folhas) == 20


def test_o_indice_unico_recusa_folha_repetida_forcada_por_fora():
    # A rede de baixo. Se algum caminho futuro escrever folha sem passar pelo
    # contador, o banco recusa em vez de aceitar duas escrituras na folha 1.
    con = banco()
    lid = NL.abrir_livro(con, "ESCRITURA", SV, AGORA, EXTENSO, folhas=200)
    lancar(con, novo_ato(con), paginas=2)
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            """INSERT INTO nt_atos(tipo, data, livro_id, folha_inicial_num,
                                   situacao, criado_em)
               VALUES ('ESCRITURA','2026-08-17',?,1,'LAVRADO',?)""", (lid, AGORA))


# ------------------------------------------------------------- termo

def test_o_termo_e_continuo_e_nao_reinicia_no_livro_novo():
    con = banco()
    NL.abrir_livro(con, "ESCRITURA", SV, AGORA, EXTENSO, folhas=2)
    a = lancar(con, novo_ato(con), paginas=2)    # folha 1 do livro 1
    b = lancar(con, novo_ato(con), paginas=2)    # folha 2, enche o livro 1
    c = lancar(con, novo_ato(con), paginas=2)    # livro 2, folha 1
    assert (a["termo"], b["termo"], c["termo"]) == (1, 2, 3)
    assert a["livro"] == b["livro"] == "1"
    assert c["livro"] == "2"
    assert c["folha"] == "1"                     # a FOLHA reinicia; o termo nao


def test_o_termo_e_por_serie_e_as_series_nao_se_misturam():
    con = banco()
    NL.abrir_livro(con, "ESCRITURA", SV, AGORA, EXTENSO, folhas=200)
    NL.abrir_livro(con, "PROCURACAO", SV, AGORA, EXTENSO, folhas=200)
    e1 = lancar(con, novo_ato(con, "ESCRITURA"), paginas=2)
    p1 = lancar(con, novo_ato(con, "PROCURACAO"), paginas=2)
    e2 = lancar(con, novo_ato(con, "ESCRITURA"), paginas=2)
    assert (e1["termo"], e2["termo"]) == (1, 2)
    assert p1["termo"] == 1


def test_revogacao_e_renuncia_seguem_o_livro_de_procuracoes():
    con = banco()
    NL.abrir_livro(con, "PROCURACAO", SV, AGORA, EXTENSO, folhas=200)
    p = lancar(con, novo_ato(con, "PROCURACAO"), paginas=2)
    r = lancar(con, novo_ato(con, "REVOGACAO"), paginas=2)
    assert p["livro"] == r["livro"] == "1"
    assert (p["termo"], r["termo"]) == (1, 2)     # sequencia unica da serie


def test_o_contador_do_termo_e_semeado_pelo_acervo():
    # 213 procuracoes e 45 escrituras vieram do E-Oficio com numero de ordem
    # proprio. Comecar do 1 daria termo repetido com ato de 1985.
    con = banco()
    con.execute("""INSERT INTO nt_atos(tipo, data, numero_ordem, situacao, criado_em)
                   VALUES ('ESCRITURA','1998-03-02', 258, 'LAVRADO', ?)""", (AGORA,))
    NL.abrir_livro(con, "ESCRITURA", SV, AGORA, EXTENSO, folhas=200)
    assert lancar(con, novo_ato(con), paginas=2)["termo"] == 259


def test_nao_se_baixa_o_contador_para_dentro_do_que_ja_foi_usado():
    con = banco()
    NL.abrir_livro(con, "ESCRITURA", SV, AGORA, EXTENSO, folhas=200)
    lancar(con, novo_ato(con), paginas=2)
    lancar(con, novo_ato(con), paginas=2)
    with pytest.raises(NL.LivroError):
        NL.fixar_termo(con, "ESCRITURA", 2, "TESTE", "engano", AGORA)
    NL.fixar_termo(con, "ESCRITURA", 500, "TESTE", "salto combinado", AGORA)
    assert lancar(con, novo_ato(con), paginas=2)["termo"] == 500


# ------------------------------------------------------------- virada de livro

def test_o_livro_cheio_encerra_e_o_seguinte_abre_sozinho():
    con = banco()
    NL.abrir_livro(con, "ESCRITURA", SV, AGORA, EXTENSO, folhas=2)
    lancar(con, novo_ato(con), paginas=2)
    lancar(con, novo_ato(con), paginas=2)         # enche
    primeiro = con.execute("SELECT * FROM nt_livros WHERE numero='1'").fetchone()
    assert primeiro["encerrado"] == 1
    assert "TERMO DE ENCERRAMENTO" in primeiro["termo_encerramento"]
    segundo = con.execute("SELECT * FROM nt_livros WHERE numero='2'").fetchone()
    assert segundo is not None and segundo["automatico"] == 1
    assert "TERMO DE ABERTURA" in segundo["termo_abertura"]


def test_o_ato_nao_se_parte_entre_dois_livros():
    # Restam 2 folhas e o ato precisa de 3: o livro encerra dizendo que as 2
    # ficaram inutilizadas, e o ato INTEIRO comeca no livro seguinte.
    con = banco()
    NL.abrir_livro(con, "ESCRITURA", SV, AGORA, EXTENSO, folhas=4)
    lancar(con, novo_ato(con), paginas=4)         # folhas 1 e 2
    feito = lancar(con, novo_ato(con), paginas=5)  # precisa de 3
    assert feito["livro"] == "2"
    assert (feito["folha"], feito["folha_final"]) == ("1", "3")
    velho = con.execute("SELECT * FROM nt_livros WHERE numero='1'").fetchone()
    assert velho["encerrado"] == 1
    assert velho["folhas_inutilizadas"] == "3-4"
    assert "INUTILIZADAS" in velho["termo_encerramento"]


def test_o_primeiro_ato_abre_o_livro_quando_nao_ha_nenhum():
    con = banco()
    feito = lancar(con, novo_ato(con), paginas=2)
    assert feito["livro"] == "1" and feito["livro_aberto_automaticamente"]
    livro = con.execute("SELECT * FROM nt_livros").fetchone()
    assert "TERMO DE ABERTURA" in livro["termo_abertura"]
    assert "duzentas" in livro["termo_abertura"]      # 200 folhas por extenso


def test_o_ato_maior_que_o_livro_e_recusado_em_vez_de_partido():
    con = banco()
    NL.abrir_livro(con, "ESCRITURA", SV, AGORA, EXTENSO, folhas=2)
    with pytest.raises(NL.LivroError):
        NL.lancar_ato(con, novo_ato(con), SV, AGORA, EXTENSO, paginas=20,
                      usuario="TESTE", capacidade_novo_livro=2)


def test_o_termo_de_abertura_nao_e_mais_opcional():
    con = banco()
    lid = NL.abrir_livro(con, "ESCRITURA", SV, AGORA, EXTENSO, folhas=200)
    livro = con.execute("SELECT * FROM nt_livros WHERE id=?", (lid,)).fetchone()
    texto = livro["termo_abertura"]
    assert "TERMO DE ABERTURA" in texto
    assert "000000" in texto                       # CNS da serventia
    assert "MARIO EXEMPLO DOS SANTOS" in texto      # quem responde


def test_nao_se_encerra_livro_com_ato_em_lavratura_dentro():
    con = banco()
    lid = NL.abrir_livro(con, "ESCRITURA", SV, AGORA, EXTENSO, folhas=200)
    con.execute("""INSERT INTO nt_atos(tipo, data, livro_id, situacao, criado_em)
                   VALUES ('ESCRITURA','2026-08-17',?, 'EM_LAVRATURA', ?)""",
                (lid, AGORA))
    with pytest.raises(NL.LivroError):
        NL.encerrar_livro(con, lid, SV, AGORA, EXTENSO)


# ------------------------------------------------------------- o ato lancado

def test_o_ato_lancado_nao_se_relanca():
    con = banco()
    NL.abrir_livro(con, "ESCRITURA", SV, AGORA, EXTENSO, folhas=200)
    ato = novo_ato(con)
    lancar(con, ato, paginas=2)
    with pytest.raises(NL.LivroError):
        lancar(con, ato, paginas=2)


def test_ato_cancelado_nao_entra_no_livro():
    con = banco()
    NL.abrir_livro(con, "ESCRITURA", SV, AGORA, EXTENSO, folhas=200)
    ato = novo_ato(con)
    con.execute("UPDATE nt_atos SET situacao='CANCELADO' WHERE id=?", (ato,))
    with pytest.raises(NL.LivroError):
        lancar(con, ato, paginas=2)


def test_a_folha_do_ato_cancelado_depois_nao_volta_para_a_fila():
    con = banco()
    NL.abrir_livro(con, "ESCRITURA", SV, AGORA, EXTENSO, folhas=200)
    ato = novo_ato(con)
    lancar(con, ato, paginas=2)                    # folha 1
    con.execute("UPDATE nt_atos SET situacao='CANCELADO' WHERE id=?", (ato,))
    seguinte = lancar(con, novo_ato(con), paginas=2)
    assert seguinte["folha"] == "2"                # o papel foi gasto


def test_o_lancamento_marca_o_ato_como_lavrado():
    con = banco()
    NL.abrir_livro(con, "ESCRITURA", SV, AGORA, EXTENSO, folhas=200)
    ato = novo_ato(con)
    lancar(con, ato, paginas=2)
    linha = con.execute("SELECT * FROM nt_atos WHERE id=?", (ato,)).fetchone()
    assert linha["situacao"] == "LAVRADO"
    assert linha["lancado_por"] == "TESTE"
    # `numero_ordem` NAO e reaproveitado como termo. Ele era sequencia unica
    # do tabelionato inteiro; o termo e por serie. Escrever o termo ali daria
    # escritura nº 1 e procuracao nº 1 no mesmo campo, e colisao com o acervo.
    assert linha["numero_ordem"] is None
    assert linha["termo"] == 1


def test_o_termo_nao_colide_com_o_numero_de_ordem_do_acervo():
    con = banco()
    con.execute("""INSERT INTO nt_atos(tipo, data, numero_ordem, situacao, criado_em)
                   VALUES ('ESCRITURA','1998-03-02', 45, 'LAVRADO', ?)""", (AGORA,))
    NL.abrir_livro(con, "ESCRITURA", SV, AGORA, EXTENSO, folhas=200)
    NL.abrir_livro(con, "PROCURACAO", SV, AGORA, EXTENSO, folhas=200)
    e = lancar(con, novo_ato(con, "ESCRITURA"), paginas=2)
    p = lancar(con, novo_ato(con, "PROCURACAO"), paginas=2)
    assert e["termo"] == 46 and p["termo"] == 1
    repetidos = con.execute(
        """SELECT numero_ordem, COUNT(*) n FROM nt_atos
           WHERE numero_ordem IS NOT NULL GROUP BY numero_ordem HAVING n > 1""").fetchall()
    assert repetidos == []


# ------------------------------------------------------------- acervo

def test_o_acervo_nao_e_renumerado():
    con = banco()
    lid = NL.abrir_livro(con, "ESCRITURA", SV, AGORA, EXTENSO, numero="27",
                         folhas=200)
    con.execute("""INSERT INTO nt_atos(tipo, data, livro_id, livro, folha,
                                       numero_ordem, situacao, criado_em)
                   VALUES ('ESCRITURA','2011-05-04',?, '27','139', 100,
                           'LAVRADO', ?)""", (lid, AGORA))
    novo = lancar(con, novo_ato(con), paginas=2)
    antigo = con.execute("SELECT * FROM nt_atos WHERE folha='139'").fetchone()
    assert antigo["folha"] == "139" and antigo["numero_ordem"] == 100
    assert antigo["termo"] is None                 # o acervo nao ganha termo
    # E o ato novo entra DEPOIS da folha 139, nao por cima dela.
    assert novo["folha"] == "140"


def test_o_livro_velho_que_nascera_em_folha_1_e_reconciliado():
    # Os livros abertos antes desta versao ficaram com folha_atual = 1 para
    # sempre. Ligar a numeracao sem reconciliar mandaria o proximo ato para a
    # folha 1 de um livro que ja vai na 139.
    con = banco()
    con.execute("""INSERT INTO nt_livros(tipo, numero, complemento, folhas,
                                         folha_atual, ativo, encerrado, criado_em)
                   VALUES ('ESCRITURA','27','',200,1,1,0,?)""", (AGORA,))
    lid = con.execute("SELECT id FROM nt_livros").fetchone()["id"]
    con.execute("""INSERT INTO nt_atos(tipo, data, livro_id, livro, folha,
                                       situacao, criado_em)
                   VALUES ('ESCRITURA','2011-05-04',?, '27','139','LAVRADO',?)""",
                (lid, AGORA))
    assert NL.sincronizar_folha_atual(con, lid) == 140
    assert lancar(con, novo_ato(con), paginas=2)["folha"] == "140"


def test_o_complemento_desempata_o_acervo_que_divide_folha():
    # Quatro pares de atos na mesma folha do livro 27 vieram do E-Oficio. Sem
    # complemento a CENSEC recusa os dois por duplicidade.
    con = banco()
    for i in (1, 2, 3):
        con.execute("""INSERT INTO nt_atos(id, tipo, data, livro, folha,
                                           numero_ordem, situacao, criado_em)
                       VALUES (?, 'PROCURACAO','2011-05-04','27','139',?,
                               'LAVRADO', ?)""", (i, i, AGORA))
    assert NL.desambiguar_folhas_do_acervo(con) == 2
    complementos = [r["folha_complemento"] for r in con.execute(
        "SELECT folha_complemento FROM nt_atos ORDER BY id")]
    assert complementos == [None, "A", "B"]
    # Idempotente: rodar de novo nao muda nada.
    assert NL.desambiguar_folhas_do_acervo(con) == 0


def test_o_complemento_nao_toca_em_folha_unica():
    con = banco()
    con.execute("""INSERT INTO nt_atos(tipo, data, livro, folha, situacao, criado_em)
                   VALUES ('PROCURACAO','2011-05-04','27','139','LAVRADO',?)""",
                (AGORA,))
    assert NL.desambiguar_folhas_do_acervo(con) == 0


# ------------------------------------------------------------- conferencia

def test_a_conferencia_acha_folha_pulada_e_termo_faltando():
    con = banco()
    lid = NL.abrir_livro(con, "ESCRITURA", SV, AGORA, EXTENSO, folhas=200)
    lancar(con, novo_ato(con), paginas=2)          # folha 1, termo 1
    con.execute("""INSERT INTO nt_atos(tipo, serie, data, livro_id, folha,
                                       folha_inicial_num, folha_final_num, termo,
                                       situacao, criado_em)
                   VALUES ('ESCRITURA','ESCRITURA','2026-08-17',?, '5',5,5,7,
                           'LAVRADO', ?)""", (lid, AGORA))
    laudo = NL.conferir_livro(con, lid)
    assert laudo["folhas_puladas"] == ["2-4"]
    assert laudo["termos_faltando"] == ["2-6"]
    assert laudo["folhas_repetidas"] == []


def test_a_conferencia_de_livro_certo_nao_reclama():
    con = banco()
    lid = NL.abrir_livro(con, "ESCRITURA", SV, AGORA, EXTENSO, folhas=200)
    for _ in range(5):
        lancar(con, novo_ato(con), paginas=3)
    laudo = NL.conferir_livro(con, lid)
    assert laudo["folhas_puladas"] == []
    assert laudo["folhas_repetidas"] == []
    assert laudo["termos_faltando"] == []
    assert laudo["atos"] == 5


# ------------------------------------------------------------- previsao

def test_a_previsao_nao_gasta_numero():
    con = banco()
    NL.abrir_livro(con, "ESCRITURA", SV, AGORA, EXTENSO, folhas=200)
    for _ in range(3):
        assert NL.previsao(con, "ESCRITURA", 2)["termo"] == 1
    assert lancar(con, novo_ato(con), paginas=2)["termo"] == 1


def test_a_previsao_avisa_que_o_livro_vai_virar():
    con = banco()
    NL.abrir_livro(con, "ESCRITURA", SV, AGORA, EXTENSO, folhas=2)
    lancar(con, novo_ato(con), paginas=2)
    p = NL.previsao(con, "ESCRITURA", 4)           # 2 folhas, so resta 1
    assert p["abrira_livro"] is True
    assert p["proximo_livro"] == "2"


# ------------------------------------------------------------- concorrencia

def test_dois_balcoes_lancando_ao_mesmo_tempo_nao_pegam_a_mesma_folha():
    """Duas conexoes de verdade, com BEGIN IMMEDIATE, como a producao.

    `database.transaction()` abre BEGIN IMMEDIATE: o segundo escritor espera o
    primeiro comitar e so entao le o `folha_atual` — ja incrementado.
    """
    with tempfile.TemporaryDirectory() as pasta:
        caminho = str(Path(pasta) / "cartorio.db")
        base = sqlite3.connect(caminho)
        base.row_factory = sqlite3.Row
        init_notas_schema(base)
        NL.abrir_livro(base, "ESCRITURA", SV, AGORA, EXTENSO, folhas=200)
        a1, a2 = novo_ato(base), novo_ato(base)
        base.commit()
        base.close()

        def conexao():
            c = sqlite3.connect(caminho, timeout=10)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA foreign_keys = ON")
            return c

        um, dois = conexao(), conexao()
        um.execute("BEGIN IMMEDIATE")
        primeiro = lancar(um, a1, 2)
        um.commit()

        dois.execute("BEGIN IMMEDIATE")
        segundo = lancar(dois, a2, 2)
        dois.commit()

        assert primeiro["folha"] != segundo["folha"]
        assert primeiro["termo"] != segundo["termo"]
        assert {primeiro["folha"], segundo["folha"]} == {"1", "2"}
        um.close()
        dois.close()


# ------------------------------------------------------------- o acervo é intocável
#
# Tudo abaixo nasceu de uma revisão adversarial em 17/08/2026: a primeira
# versão da guarda perguntava "já tem termo ou folha numérica?", e os 258 atos
# do acervo não têm nem uma coisa nem outra — as colunas são novas. Passavam
# direto, e o lançamento reescrevia a folha de uma escritura de 2011.

def _ato_do_acervo(con, tipo="ESCRITURA", situacao="LAVRADO", livro="27",
                   folha="139", numero_ordem=100) -> int:
    cur = con.execute(
        """INSERT INTO nt_atos(tipo, data, livro, folha, folha_final,
                               numero_ordem, situacao, teor, criado_em)
           VALUES (?,?,?,?,?,?,?, '<p>teor antigo</p>', ?)""",
        (tipo, "2011-05-04", livro, folha, folha, numero_ordem, situacao, AGORA))
    return int(cur.lastrowid)


def test_ato_do_acervo_nao_se_lanca():
    con = banco()
    NL.abrir_livro(con, "ESCRITURA", SV, AGORA, EXTENSO, folhas=200)
    antigo = _ato_do_acervo(con)
    with pytest.raises(NL.LivroError, match="já está lançado"):
        lancar(con, antigo, paginas=4)
    linha = con.execute("SELECT * FROM nt_atos WHERE id=?", (antigo,)).fetchone()
    assert (linha["livro"], linha["folha"], linha["numero_ordem"]) == ("27", "139", 100)


def test_procuracao_revogada_do_acervo_nao_ressuscita():
    # A pior das consequências: `lancar_ato` fazia situacao='LAVRADO' sem
    # perguntar. Uma procuração revogada voltava a valer — e voltava a ser
    # elegível para a remessa à CENSEC, que filtra por LAVRADO.
    con = banco()
    NL.abrir_livro(con, "PROCURACAO", SV, AGORA, EXTENSO, folhas=200)
    revogada = _ato_do_acervo(con, "PROCURACAO", "REVOGADO", "27", "88", 77)
    with pytest.raises(NL.LivroError):
        lancar(con, revogada, paginas=2)
    assert con.execute("SELECT situacao FROM nt_atos WHERE id=?",
                       (revogada,)).fetchone()["situacao"] == "REVOGADO"


def test_so_o_ato_em_lavratura_se_lanca():
    con = banco()
    NL.abrir_livro(con, "ESCRITURA", SV, AGORA, EXTENSO, folhas=200)
    ato = novo_ato(con)
    con.execute("UPDATE nt_atos SET situacao='LAVRADO' WHERE id=?", (ato,))
    with pytest.raises(NL.LivroError, match="em lavratura"):
        lancar(con, ato, paginas=2)


# ------------------------------------------------------------- livro sem capacidade

def test_livro_sem_folhas_declaradas_nao_e_encerrado_sozinho():
    # `nt_livros.folhas` é NULLABLE e a importação copia o `intNFL` do
    # E-Ofício sem conferir. Com NULO, a conta da última folha dava ZERO, o
    # ato "não cabia", e o sistema encerrava um livro em uso com um termo
    # dizendo que ele tinha "0 (zero) folhas".
    for valor in (None, 0):
        con = banco()
        con.execute("""INSERT INTO nt_livros(tipo, numero, complemento, folhas,
                                             folha_atual, ativo, encerrado, criado_em)
                       VALUES ('ESCRITURA','27','',?,1,1,0,?)""", (valor, AGORA))
        lid = con.execute("SELECT id FROM nt_livros").fetchone()["id"]
        feito = lancar(con, novo_ato(con), paginas=2)
        livro = con.execute("SELECT * FROM nt_livros WHERE id=?", (lid,)).fetchone()
        assert livro["encerrado"] == 0, f"folhas={valor} encerrou o livro"
        assert feito["livro"] == "27"
        assert NL.capacidade(livro) == NL.CAPACIDADE_PADRAO


def test_capacidade_de_livro_normal_e_a_declarada():
    con = banco()
    NL.abrir_livro(con, "ESCRITURA", SV, AGORA, EXTENSO, folhas=150)
    livro = con.execute("SELECT * FROM nt_livros").fetchone()
    assert NL.capacidade(livro) == 150
    assert NL.ultima_folha(livro) == 150


def test_livro_que_comeca_em_folha_diferente_de_1():
    con = banco()
    NL.abrir_livro(con, "ESCRITURA", SV, AGORA, EXTENSO, folhas=100,
                   folha_inicial=51)
    livro = con.execute("SELECT * FROM nt_livros").fetchone()
    assert livro["folha_inicial"] == 51 and livro["folha_atual"] == 51
    assert NL.ultima_folha(livro) == 150
    assert lancar(con, novo_ato(con), paginas=2)["folha"] == "51"


# ------------------------------------------------------------- páginas do formulário

def test_paginas_zero_negativa_ou_lixo_e_recusada_em_vez_de_adivinhada():
    con = banco()
    NL.abrir_livro(con, "ESCRITURA", SV, AGORA, EXTENSO, folhas=200)
    for ruim in ("0", "-4", "abc", "2,5"):
        with pytest.raises(NL.LivroError):
            lancar(con, novo_ato(con), paginas=ruim)


def test_paginas_em_branco_cai_na_estimativa():
    con = banco()
    NL.abrir_livro(con, "ESCRITURA", SV, AGORA, EXTENSO, folhas=200)
    ato = novo_ato(con, teor="x" * (NL.CARACTERES_POR_PAGINA + 10))
    assert lancar(con, ato, paginas="")["paginas_texto"] == 2


def test_numero_absurdo_nao_derruba_o_atendimento():
    assert NL.por_extenso(1_000_000) == "1000000"     # devolve, nao estoura
    assert NL.com_algarismos(999_999).startswith("999999 (novecentos")
    con = banco()
    with pytest.raises(NL.LivroError):
        NL.abrir_livro(con, "ESCRITURA", SV, AGORA, EXTENSO, folhas=10_000_000)
    NL.abrir_livro(con, "ESCRITURA", SV, AGORA, EXTENSO, folhas=200)
    with pytest.raises(NL.LivroError):
        lancar(con, novo_ato(con), paginas=9_999_999)


# ------------------------------------------------------------- livros duplicados

def test_dois_livros_abertos_na_serie_nao_viram_tres():
    con = banco()
    NL.abrir_livro(con, "ESCRITURA", SV, AGORA, EXTENSO, numero="1", folhas=2)
    NL.abrir_livro(con, "ESCRITURA", SV, AGORA, EXTENSO, numero="2", folhas=200)
    lancar(con, novo_ato(con), paginas=2)          # folha 1 do livro 1
    lancar(con, novo_ato(con), paginas=2)          # folha 2, enche o livro 1
    seguinte = lancar(con, novo_ato(con), paginas=2)
    numeros = [r["numero"] for r in con.execute(
        "SELECT numero FROM nt_livros ORDER BY CAST(numero AS INTEGER)")]
    assert numeros == ["1", "2"]                   # nenhum livro 3 fantasma
    assert seguinte["livro"] == "2"


# ------------------------------------------------------------- desempate por série

def test_o_desempate_nao_confunde_livro_27_de_series_diferentes():
    # Livro 27 de escrituras e livro 27 de procurações são dois livros de
    # papel distintos. Agrupar só por (número, folha) dava complemento a uma
    # procuração que não tinha duplicidade nenhuma.
    con = banco()
    con.execute("""INSERT INTO nt_atos(tipo, data, livro, folha, situacao, criado_em)
                   VALUES ('ESCRITURA','2011-05-04','27','139','LAVRADO',?)""", (AGORA,))
    con.execute("""INSERT INTO nt_atos(tipo, data, livro, folha, situacao, criado_em)
                   VALUES ('PROCURACAO','2011-05-04','27','139','LAVRADO',?)""", (AGORA,))
    assert NL.desambiguar_folhas_do_acervo(con) == 0
    assert [r["folha_complemento"] for r in con.execute(
        "SELECT folha_complemento FROM nt_atos ORDER BY id")] == [None, None]


# ------------------------------------------------------------- leitura é leitura

def test_a_previsao_nao_escreve_no_banco():
    """Tela de conferência roda em GET. GET que escreve trava o balcão.

    `db.transaction()` é BEGIN IMMEDIATE: um GET que abre transação de
    escrita fica dez segundos no busy_timeout com outro balcão lavrando, e
    depois devolve 500.
    """
    con = banco()
    NL.abrir_livro(con, "ESCRITURA", SV, AGORA, EXTENSO, folhas=200)
    con.execute("""INSERT INTO nt_atos(tipo, data, livro_id, livro, folha,
                                       situacao, criado_em)
                   VALUES ('ESCRITURA','2011-05-04',1,'1','40','LAVRADO',?)""",
                (AGORA,))
    con.commit()
    antes = con.total_changes
    p = NL.previsao(con, "ESCRITURA", 2)
    assert con.total_changes == antes, "previsao gravou no banco"
    assert p["folha_inicial"] == 41           # e mesmo assim acertou a folha
    assert p["termo"] == 1
    assert con.execute("SELECT COUNT(*) n FROM nt_termos").fetchone()["n"] == 0


def test_folha_livre_le_e_sincronizar_grava():
    con = banco()
    lid = NL.abrir_livro(con, "ESCRITURA", SV, AGORA, EXTENSO, folhas=200)
    con.execute("""INSERT INTO nt_atos(tipo, data, livro_id, livro, folha,
                                       situacao, criado_em)
                   VALUES ('ESCRITURA','2011-05-04',?,'1','139','LAVRADO',?)""",
                (lid, AGORA))
    con.commit()
    antes = con.total_changes
    livro = con.execute("SELECT * FROM nt_livros WHERE id=?", (lid,)).fetchone()
    assert NL.folha_livre(con, livro) == 140
    assert con.total_changes == antes
    assert NL.sincronizar_folha_atual(con, lid) == 140
    assert con.total_changes > antes


# ------------------------------------------------------------- migração real

def test_a_migracao_sobrevive_a_um_banco_de_producao():
    """Esquema ANTES das colunas novas, populado, e o `init_notas_schema` por cima.

    O banco de verdade tem folhas repetidas no livro 27, `numero_ordem`
    duplicado e livros com `folha_atual = 1`. Um indice UNIQUE sem a condicao
    `IS NOT NULL` recusaria criar-se, e a atualizacao morreria na largada.

    O "esquema antigo" aqui e o SCHEMA sem as MIGRACOES — que e exatamente o
    que havia no banco antes desta versao, porque as MIGRACOES sao os ALTER
    TABLE que faltavam aplicar.
    """
    from notas_schema import INDICES_IMPORTACAO, SCHEMA

    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(SCHEMA)
    con.executescript(INDICES_IMPORTACAO)

    con.execute("""INSERT INTO nt_livros(tipo, numero, folhas, folha_atual, criado_em)
                   VALUES ('ESCRITURA','27',200,1,?)""", (AGORA,))
    for i in range(1, 60):
        con.execute("""INSERT INTO nt_atos(tipo, numero_ordem, livro_id, livro,
                                           folha, data, criado_em)
                       VALUES ('ESCRITURA', ?, 1, '27', ?, '2011-05-04', ?)""",
                    (i // 2, str(100 + i // 2), AGORA))   # ordem E folha repetidas
    con.commit()

    init_notas_schema(con)                       # nao pode levantar

    colunas = {r["name"] for r in con.execute("PRAGMA table_info(nt_atos)")}
    assert {"termo", "serie", "folha_inicial_num", "verso_final"} <= colunas
    indices = {r["name"] for r in con.execute("PRAGMA index_list(nt_atos)")}
    assert {"ux_nt_atos_folha", "ux_nt_atos_termo"} <= indices
    assert con.execute("SELECT COUNT(*) n FROM nt_atos WHERE verso_final IS NULL"
                       ).fetchone()["n"] == 0
    # E o acervo continua onde estava, com as folhas repetidas e tudo — que e
    # justamente o que um indice unico sem condicao teria recusado.
    assert con.execute("SELECT COUNT(*) n FROM nt_atos").fetchone()["n"] == 59
    repetidas = con.execute(
        """SELECT COUNT(*) n FROM (SELECT folha FROM nt_atos
                                   GROUP BY folha HAVING COUNT(*) > 1)""").fetchone()
    assert repetidas["n"] > 0
    # Rodar de novo tambem nao levanta: o start do sistema chama isto sempre.
    init_notas_schema(con)


def test_o_livro_do_acervo_recebe_o_ato_novo_depois_da_ultima_folha_usada():
    from notas_schema import SCHEMA

    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    con.execute("""INSERT INTO nt_livros(tipo, numero, folhas, folha_atual, criado_em)
                   VALUES ('ESCRITURA','27',200,1,?)""", (AGORA,))
    con.execute("""INSERT INTO nt_atos(tipo, numero_ordem, livro_id, livro, folha,
                                       data, situacao, criado_em)
                   VALUES ('ESCRITURA', 45, 1, '27', '139','2011-05-04',
                           'LAVRADO', ?)""", (AGORA,))
    init_notas_schema(con)
    feito = lancar(con, novo_ato(con), paginas=2)
    assert (feito["livro"], feito["folha"]) == ("27", "140")
    assert feito["termo"] == 46


# ------------------------------------------------------------- corrida de verdade

def test_quatro_balcoes_lavrando_ao_mesmo_tempo():
    """Threads, conexões separadas, WAL. O outro teste serializa; este não.

    Cada thread abre a sua conexão, faz BEGIN IMMEDIATE e lança. O SQLite
    serializa os escritores; o que este teste prova é que a serialização
    produz folhas e termos sem repetição, e sem furo.
    """
    import threading

    with tempfile.TemporaryDirectory() as pasta:
        caminho = str(Path(pasta) / "cartorio.db")
        base = sqlite3.connect(caminho)
        base.row_factory = sqlite3.Row
        base.execute("PRAGMA journal_mode=WAL")
        init_notas_schema(base)
        NL.abrir_livro(base, "ESCRITURA", SV, AGORA, EXTENSO, folhas=200)
        atos = [novo_ato(base) for _ in range(16)]
        base.commit()
        base.close()

        feitos, erros = [], []
        travas = threading.Lock()
        largada = threading.Barrier(4)

        def balcao(meus):
            con = sqlite3.connect(caminho, timeout=20)
            con.row_factory = sqlite3.Row
            con.execute("PRAGMA busy_timeout=20000")
            largada.wait()
            for ato in meus:
                try:
                    con.execute("BEGIN IMMEDIATE")
                    resultado = lancar(con, ato, 2)
                    con.commit()
                    with travas:
                        feitos.append(resultado)
                except Exception as erro:               # noqa: BLE001
                    con.rollback()
                    with travas:
                        erros.append(f"{type(erro).__name__}: {erro}")
            con.close()

        fios = [threading.Thread(target=balcao, args=(atos[i::4],)) for i in range(4)]
        for f in fios:
            f.start()
        for f in fios:
            f.join()

        assert erros == []
        assert len({f["folha"] for f in feitos}) == 16
        assert len({f["termo"] for f in feitos}) == 16
        assert sorted(int(f["folha"]) for f in feitos) == list(range(1, 17))
        assert sorted(f["termo"] for f in feitos) == list(range(1, 17))


def test_parse_livro_folha_busca_ajuda_95():
    assert NL.parse_livro_folha_busca("3/45") == ("3", "45")
    assert NL.parse_livro_folha_busca("x") == (None, None)


def test_termo_comparecimento_ajuda_91():
    html = NL.texto_termo_comparecimento(
        sv={"unit_name": "X", "serventia_titulo": "T", "serventia_titular": "F",
            "ri_cns": "1", "endereco_completo": "R"},
        reconhecimento={"documento_descricao": "doc", "selo": "", "oficial": "O",
                        "oficial_funcao": ""},
        parte={"nome": "Maria", "documento": "1"},
        data_extenso="hoje",
    )
    assert "TERMO DE COMPARECIMENTO" in html


def test_notas_atos_livro_id_vazio(cg_casa_logada):
    html = cg_casa_logada["c"].get("/notas/atos?livro_id=999999").get_data(as_text=True)
    assert "Nada encontrado" in html or "0 ato" in html
