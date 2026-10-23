"""As quatro marcas do assento de obito.

O QUE ESTES TESTES GUARDAM
    **QUE «NAO PERGUNTEI» NAO VIRA «NAO».** E a razao de o campo ser TEXT com
    tres estados em vez de um booleano. Um assento em que ninguem perguntou
    nada nao pode parecer um assento em que tudo foi respondido com «nao» —
    a obrigacao sumiria calada, que e o unico jeito de ela sumir.

    **QUE CADA MARCA DIZ O QUE OBRIGA.** Caixa sem consequencia escrita e
    caixa que alguem marca no automatico. O valor nao esta na marca: esta na
    comunicacao que ela faz existir.

    **QUE O ACERVO NAO ENTRA.** Ninguem vai telefonar para a familia de um
    obito de 2009 para perguntar se o falecido era eleitor. A pergunta e do
    balcao, com o declarante na frente; depois dele nao se responde mais.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import rc_marcas_do_obito as M                                 # noqa: E402


# ------------------------------------------------ os tres estados


def test_sao_tres_estados_e_nao_dois():
    """Se um dia virarem dois, «nao perguntei» passa a mentir «nao»."""
    assert set(M.ESTADOS) == {M.SIM, M.NAO, M.NAO_PERGUNTADO}
    assert M.NAO_PERGUNTADO == ""
    assert M.ESTADOS[M.NAO_PERGUNTADO] == "Não perguntado"


def test_normalizar_reconhece_o_que_vem_de_formulario():
    for v in ("SIM", "sim", "S", "1", "true"):
        assert M.normalizar(v) == M.SIM
    for v in ("NAO", "não", "N", "0", "false"):
        assert M.normalizar(v) == M.NAO


def test_valor_estranho_cai_em_nao_perguntado_e_nao_em_nao():
    """**Cair no «nao» seria inventar uma resposta que ninguem deu.** Valor que
    o sistema nao entende tem de voltar a pedir a pergunta."""
    for v in (None, "", "  ", "talvez", "X", 7, "SIM SENHOR"):
        assert M.normalizar(v) == M.NAO_PERGUNTADO, v


# ------------------------------------------------ o que cada uma obriga


def test_sao_as_quatro_do_e_oficio():
    assert len(M.MARCAS) == 4
    assert set(M.CHAVES) == {"obito_eleitor", "obito_possui_bens",
                             "obito_possui_filho", "obito_desconhecido"}


def test_toda_marca_diz_o_que_obriga_e_por_que_importa():
    """Caixa sem consequencia escrita e caixa que se marca no automatico."""
    for m in M.MARCAS:
        assert m["rotulo"] and m["pergunta"]
        assert m["obriga"], f"{m['chave']} nao diz o que obriga"
        assert m["artigo"], f"{m['chave']} nao diz o artigo"
        assert m["porque_importa"], f"{m['chave']} nao diz por que importa"


def test_o_eleitor_aponta_a_pendencia_da_casa():
    """O INFODIP nao esta cadastrado, e a tela tem de dizer isso — senao o
    balcao marca a caixa achando que a comunicacao vai sair."""
    e = M.marca("obito_eleitor")
    assert "INFODIP" in e["pendencia_da_casa"]
    assert "Eleitoral" in e["obriga"]


def test_marca_que_nao_existe_recusa_dizendo_as_que_existem():
    with pytest.raises(M.MarcaError) as erro:
        M.marca("obito_inventada")
    assert "obito_eleitor" in str(erro.value)


# ------------------------------------------------ a leitura do assento


def test_assento_vazio_tem_as_quatro_por_perguntar():
    faltam = M.o_que_falta_perguntar({})
    assert len(faltam) == 4


def test_responder_nao_tira_da_lista_de_por_perguntar():
    """**E O TESTE QUE SEPARA OS DOIS SILENCIOS.** Responder «nao» e uma
    resposta; nao responder nao e."""
    a = {"obito_eleitor": "NAO"}
    faltam = [m["chave"] for m in M.o_que_falta_perguntar(a)]
    assert "obito_eleitor" not in faltam
    assert len(faltam) == 3


def test_obrigacoes_abertas_so_conta_as_que_obrigam_de_verdade():
    """«Deixou filhos» interessa a sucessao mas nao obriga a serventia a nada;
    listar as quatro faria a tela cobrar trabalho que nao existe."""
    a = {c: "SIM" for c in M.CHAVES}
    abertas = [m["chave"] for m in M.obrigacoes_abertas(a)]
    assert "obito_eleitor" in abertas
    assert "obito_desconhecido" in abertas
    assert "obito_possui_filho" not in abertas


def test_marca_com_nao_nao_abre_obrigacao():
    a = {"obito_eleitor": "NAO"}
    assert M.obrigacoes_abertas(a) == []


# ------------------------------------------------ as listas


def _banco() -> sqlite3.Connection:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    cols = ", ".join(f"{c} TEXT" for c in M.CHAVES)
    con.execute(f"CREATE TABLE rc_assentos (id INTEGER PRIMARY KEY, "
                f"especie TEXT, numero INTEGER, nome TEXT, data_ato TEXT, "
                f"data_fato TEXT, situacao TEXT, origem TEXT, {cols})")
    def por(id_, nome, origem="MANUAL", **kw):
        campos = {c: kw.get(c, "") for c in M.CHAVES}
        con.execute(
            f"INSERT INTO rc_assentos (id, especie, numero, nome, data_ato, "
            f"situacao, origem, {', '.join(M.CHAVES)}) "
            f"VALUES (?,?,?,?,?,?,?,{','.join('?' * len(M.CHAVES))})",
            (id_, "OBITO", id_, nome, "2026-08-30", "ATIVO", origem,
             *[campos[c] for c in M.CHAVES]))
    por(1, "SEM NADA PERGUNTADO")
    por(2, "ELEITOR", obito_eleitor="SIM", obito_possui_bens="NAO",
        obito_possui_filho="NAO", obito_desconhecido="NAO")
    por(3, "DO ACERVO", origem="EOFICIO")
    con.execute("INSERT INTO rc_assentos (id, especie, numero, nome, "
                "data_ato, situacao, origem) VALUES "
                "(4,'NASCIMENTO',4,'CRIANCA','2026-08-30','ATIVO','MANUAL')")
    con.commit()
    return con


def test_a_lista_de_por_perguntar_pega_so_o_obito_novo():
    con = _banco()
    achados = [a["id"] for a in M.assentos_com_marca_por_perguntar(con)]
    assert achados == [1], "entrou acervo, nascimento, ou o ja respondido"
    assert M.quantas_pendentes(con) == 1
    con.close()


def test_o_acervo_nao_entra():
    """A pergunta e do balcao, com o declarante na frente. Um obito de 2009
    numa lista de pendencias e trabalho que nao se pode fazer."""
    con = _banco()
    ids = [a["id"] for a in M.assentos_com_marca_por_perguntar(con)]
    assert 3 not in ids
    con.close()


def test_a_lista_de_eleitores_so_tem_quem_foi_marcado():
    """**Ela so existe porque alguem marcou a caixa** — nao ha como deduzir de
    um assento que o falecido votava."""
    con = _banco()
    ids = [a["id"] for a in M.eleitores_a_comunicar(con)]
    assert ids == [2]
    con.close()


def test_o_modulo_so_mexe_nas_quatro_colunas():
    """Ele ESCREVE — as respostas do balcao tem de ir para algum lugar —, mas
    nao cria nem apaga assento, e nao toca em coluna que nao seja dele."""
    codigo = (RAIZ / "rc_marcas_do_obito.py").read_text(encoding="utf-8")
    for proibido in ("INSERT INTO", "DELETE FROM", "DROP "):
        assert proibido not in codigo, f"o modulo usa «{proibido}»"
    import re
    for alvo in re.findall(r"UPDATE\s+(\w+)\s+SET", codigo):
        assert alvo == "rc_assentos", f"escreve em «{alvo}»"


def test_responder_grava_e_diz_o_que_mudou():
    con = _banco()
    r = M.responder(con, 1, {"obito_eleitor": "SIM", "obito_possui_bens": "NAO"})
    assert r["quantas"] == 2
    assert r["mudou"]["obito_eleitor"] == M.SIM
    lido = dict(con.execute("SELECT * FROM rc_assentos WHERE id=1").fetchone())
    assert M.normalizar(lido["obito_eleitor"]) == M.SIM
    assert M.normalizar(lido["obito_possui_bens"]) == M.NAO
    con.close()


def test_responder_nao_apaga_resposta_com_campo_que_nao_veio():
    """**UM POST QUE PERDE CAMPO NAO PODE DESFAZER UMA RESPOSTA.** O navegador
    que nao enviou, o escrevente que voltou a pagina — nada disso pode
    transformar «ele respondeu que nao» de volta em «ninguem perguntou»."""
    con = _banco()
    M.responder(con, 1, {"obito_eleitor": "SIM"})
    M.responder(con, 1, {"obito_eleitor": "", "obito_possui_bens": "SIM"})
    lido = dict(con.execute("SELECT * FROM rc_assentos WHERE id=1").fetchone())
    assert M.normalizar(lido["obito_eleitor"]) == M.SIM, "apagou a resposta"
    assert M.normalizar(lido["obito_possui_bens"]) == M.SIM
    con.close()


def test_ha_caminho_para_desfazer_de_proposito():
    """Quem marcou por engano precisa de saida — mas dizendo que quer desfazer,
    e nao pelo silencio de um campo que nao veio."""
    con = _banco()
    M.responder(con, 1, {"obito_eleitor": "SIM"})
    M.apagar_resposta(con, 1, "obito_eleitor")
    lido = dict(con.execute("SELECT * FROM rc_assentos WHERE id=1").fetchone())
    assert M.normalizar(lido["obito_eleitor"]) == M.NAO_PERGUNTADO
    con.close()


def test_apagar_recusa_chave_inventada():
    con = _banco()
    with pytest.raises(M.MarcaError):
        M.apagar_resposta(con, 1, "obito_qualquer_coisa")
    con.close()


def test_responder_assento_que_nao_existe_recusa_em_portugues():
    con = _banco()
    with pytest.raises(M.MarcaError) as e:
        M.responder(con, 999, {"obito_eleitor": "SIM"})
    assert "999" in str(e.value)
    con.close()


def test_as_colunas_estao_declaradas_na_migracao():
    """Modulo que le coluna que o esquema nao cria quebra na primeira subida —
    e quebra em producao, nao aqui."""
    import rc_schema
    declaradas = {c for t, c, _ in rc_schema.MIGRACOES if t == "rc_assentos"}
    for chave in M.CHAVES:
        assert chave in declaradas, f"falta migracao para {chave}"
    assert "titulo_eleitor" in declaradas
