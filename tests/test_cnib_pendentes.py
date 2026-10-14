"""A indisponibilidade da CNIB: avisar, preparar a averbação, esperar o okay.

A DECISÃO DO OFICIAL, em 28/08/2026. Perguntei se o sistema devia averbar
sozinho quando encontrasse a pessoa, e ele respondeu com uma terceira coisa,
melhor que as duas que eu tinha oferecido:

    «avisar e preparar a averbação, ficando pendente okay do cartório»

O trabalho fica pronto; a decisão continua sendo de quem assina.

E O QUE SE MEDIU AO CONSTRUIR ISTO
    Entre as 50.054 pessoas das ordens do CNIB e as partes das 1.701
    matrículas desta casa: **zero** batem por CPF, e **seis** por nome — em dez
    matrículas. As ordens vêm do TJSC, do TJPR, do TRF6 e de uma vara do Rio
    Grande do Sul, e os nomes são «Antônio Alves dos Santos», «João Pereira da
    Silva». Homônimo não é a exceção: é a regra.

E DOIS DEFEITOS QUE DESLIGAVAM O AVISO, CALADOS
    A busca por nome de `consultar_cnib` nunca devolveu nada, por duas razões
    independentes — cada uma bastava sozinha. Os testes que as guardam estão no
    fim deste arquivo, e é o que este projeto chama de correção visível.
"""
from __future__ import annotations

import glob
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ri_cnib as CNIB
from ri_schema import consultar_cnib, normalizar_busca

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa):
    """App/DB compartilhados do modulo (conftest); setup de dominio por teste."""
    db = cg_casa["db"]
    c = cg_casa["cliente"]
    db.create_user("jean", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c.post("/login",
           data={"username": "jean", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return cg_casa

def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _ordem(con, *, nome, documento, protocolo="202302.2121.02568410-IA-021",
           ativa=1, instituicao="STJ", vara="TJSC — 1a Vara de Joinville",
           processo="0800123-45.2023.8.24.0038", data="2023-02-21"):
    cur = con.execute(
        """INSERT INTO ri_cnib_ordens (protocolo_cnib, data_pedido, processo,
               instituicao, forum_vara, ativa)
           VALUES (?,?,?,?,?,?)""",
        (protocolo, data, processo, instituicao, vara, ativa))
    con.execute(
        """INSERT INTO ri_cnib_pessoas (ordem_id, nome, nome_norm, documento)
           VALUES (?,?,?,?)""",
        (cur.lastrowid, nome, normalizar_busca(nome), documento))
    return int(cur.lastrowid)


def _matricula(con, *, numero="4010", partes=()):
    cur = con.execute(
        """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao,
               criado_em)
           VALUES (?, '2', '2', 'ATIVA', '2026-08-28T09:00')""", (numero,))
    mid = int(cur.lastrowid)
    for nome, documento in partes:
        con.execute(
            """INSERT INTO ri_partes (matricula_id, nome, nome_norm,
                   documento_numero, papel)
               VALUES (?,?,?,?, 'proprietario')""",
            (mid, nome, normalizar_busca(nome), documento))
    return mid


# ------------------------------------------------- o texto vem pronto


def test_a_averbacao_vem_com_os_dados_da_ordem_no_lugar():
    teor = CNIB.teor_preparado({
        "protocolo_cnib": "202302.2121.02568410-IA-021",
        "data_pedido": "2023-02-21", "instituicao": "STJ",
        "forum_vara": "TJSC — 1a Vara", "processo": "0800123-45.2023.8.24.0038",
        "nome": "ANTONIO ALVES DOS SANTOS", "documento": "00012345678"})
    assert "202302.2121.02568410-IA-021" in teor
    assert "ANTONIO ALVES DOS SANTOS" in teor
    assert "0800123-45.2023.8.24.0038" in teor


def test_a_data_sai_em_portugues_e_nao_em_forma_de_banco():
    """O banco guarda em ISO porque assim ela ordena; o livro lê em português."""
    teor = CNIB.teor_preparado({"data_pedido": "2023-02-21"})
    assert "21/02/2023" in teor
    assert "2023-02-21" not in teor


def test_o_documento_sai_pontuado_e_o_que_nao_se_reconhece_sai_como_esta():
    assert CNIB._documento("00012345678") == "000.123.456-78"
    assert CNIB._documento("00000012000116") == "00.000.012/0001-16"
    # pontuar o que não se reconhece daria a um número errado a aparência de CPF
    assert CNIB._documento("123") == "123"


def test_o_que_a_ordem_nao_trouxe_continua_visivel_no_texto():
    """Uma averbação que diz «nos autos n. » sem número é pior que uma que diz
    «nos autos n. [PROCESSO]», porque a primeira parece pronta."""
    teor = CNIB.teor_preparado({"protocolo_cnib": "X1", "nome": "FULANO"})
    assert "[PROCESSO]" in teor


# ------------------------------------------------- a lista, e o que sai dela


def test_a_ordem_que_atinge_parte_da_matricula_aparece(casa):
    con = _con(casa)
    with con:
        _ordem(con, nome="ANTONIO ALVES DOS SANTOS", documento="00012345678")
        _matricula(con, partes=(("ANTONIO ALVES DOS SANTOS", "00012345678"),))
    achados = CNIB.pendentes(_con(casa))
    assert len(achados) == 1
    assert achados[0]["criterio"] == "documento"
    assert "202302" in achados[0]["teor"]


def test_a_ordem_cancelada_nao_aparece(casa):
    """`ativa = 0` é ordem já cancelada pela mesma via. Averbar em cima dela
    poria restrição em imóvel que a justiça já liberou."""
    con = _con(casa)
    with con:
        _ordem(con, nome="FULANO DE TAL", documento="00012345678", ativa=0)
        _matricula(con, partes=(("FULANO DE TAL", "00012345678"),))
    assert CNIB.pendentes(_con(casa)) == []


def test_o_achado_por_documento_vem_antes_do_achado_por_nome(casa):
    """Documento não tem homônimo, nome tem. Sem essa ordem os homônimos afogam
    o achado que importa — a mesma regra da lista de fraudes."""
    con = _con(casa)
    with con:
        _ordem(con, nome="JOAO PEREIRA DA SILVA", documento="00099999999",
               protocolo="POR-NOME")
        _matricula(con, numero="1", partes=(("JOAO PEREIRA DA SILVA", None),))
        _ordem(con, nome="OUTRO NOME QUALQUER", documento="00012345678",
               protocolo="POR-DOC")
        _matricula(con, numero="2", partes=(("QUEM QUER QUE SEJA", "00012345678"),))
    achados = CNIB.pendentes(_con(casa))
    assert [x["criterio"] for x in achados] == ["documento", "nome"]


def test_decidir_que_nao_e_a_pessoa_tira_da_lista(casa):
    """«Aviso sem saída é aviso que fica para sempre»: na terceira vez que a
    mesma linha aparece, ninguém lê mais."""
    con = _con(casa)
    with con:
        _ordem(con, nome="ANTONIO ALVES DOS SANTOS", documento="00012345678")
        mid = _matricula(con, partes=(("ANTONIO ALVES DOS SANTOS", "00012345678"),))
    pendente = CNIB.pendentes(_con(casa))[0]
    con = _con(casa)
    with con:
        CNIB.decidir(con, matricula_id=mid, ordem=pendente["ordem"],
                     decisao=CNIB.NAO_E_A_PESSOA,
                     motivo="conferi o CPF na certidão: o desta matrícula é "
                            "outro, nascido em 1961 em Cidade Exemplo",
                     ato_id=None, quem="jean", agora="2026-08-28T10:00")
    assert CNIB.pendentes(_con(casa)) == []


def test_dizer_que_nao_e_a_pessoa_exige_motivo_escrito(casa):
    """Dispensar é decisão de quem assina; ignorar não é. Daqui a dois anos,
    numa correição, a pergunta vai ser exatamente por quê."""
    con = _con(casa)
    with con:
        _ordem(con, nome="FULANO", documento="00012345678")
        mid = _matricula(con, partes=(("FULANO", "00012345678"),))
    with pytest.raises(CNIB.CnibError) as e:
        with _con(casa) as c:
            CNIB.decidir(c, matricula_id=mid,
                         ordem={"protocolo_cnib": "X", "nome": "FULANO",
                                "documento": "00012345678", "criterio": "documento"},
                         decisao=CNIB.NAO_E_A_PESSOA, motivo="  ",
                         ato_id=None, quem="jean", agora="2026-08-28T10:00")
    assert "por que" in str(e.value).lower()


def test_o_modulo_nao_averba_sozinho():
    """«Ficando pendente okay do cartório». Este teste fica vermelho se alguém
    escrever aqui a função que lavra o ato — que é como um atalho de um clique
    nasce, meses depois, sem ninguém lembrar por que ele não existia."""
    publicos = [n for n in dir(CNIB) if not n.startswith("_")]
    for proibido in ("averbar", "lavrar", "registrar", "aplicar"):
        assert not [n for n in publicos if proibido in n.lower()], proibido


# ------------------------------------------------- a tela


def test_a_tela_lista_e_deixa_dizer_que_nao_e_a_pessoa(casa):
    con = _con(casa)
    with con:
        _ordem(con, nome="ANTONIO ALVES DOS SANTOS", documento="00012345678")
        _matricula(con, partes=(("ANTONIO ALVES DOS SANTOS", "00012345678"),))
    html = casa["cliente"].get(
        "/registro-imoveis/cnib/pendentes").get_data(as_text=True)
    assert "ANTONIO ALVES DOS SANTOS" in html
    assert "A averbação preparada" in html
    assert 'name="motivo"' in html


def test_a_tela_recusa_sem_motivo_e_diz_o_que_escrever(casa):
    con = _con(casa)
    with con:
        _ordem(con, nome="FULANO DE TAL", documento="00012345678")
        mid = _matricula(con, partes=(("FULANO DE TAL", "00012345678"),))
    html = casa["cliente"].get(
        "/registro-imoveis/cnib/pendentes").get_data(as_text=True)
    r = casa["cliente"].post("/registro-imoveis/cnib/pendentes", data={
        "csrf_token": _token(html), "matricula_id": mid,
        "protocolo_cnib": "202302.2121.02568410-IA-021",
        "pessoa_nome": "FULANO DE TAL", "pessoa_documento": "00012345678",
        "criterio": "documento", "motivo": ""}, follow_redirects=True)
    assert "Escreva por que" in r.get_data(as_text=True)
    assert _con(casa).execute(
        "SELECT COUNT(*) c FROM ri_cnib_decisoes").fetchone()["c"] == 0


def test_a_tela_diz_quando_a_copia_do_cnib_esta_velha(casa):
    con = _con(casa)
    with con:
        _ordem(con, nome="FULANO", documento="00012345678", data="2023-03-19")
        _matricula(con, partes=(("FULANO", "00012345678"),))
    # O HTML quebra linha onde quiser; a frase e que tem de estar la. Procurar
    # o texto cru faria o teste falhar por causa de uma quebra de linha da
    # tela — e um teste que quebra por indentacao nao esta provando nada.
    html = " ".join(casa["cliente"].get(
        "/registro-imoveis/cnib/pendentes").get_data(as_text=True).split())
    assert "Esta cópia da CNIB tem" in html
    assert "confirme na central antes de registrar" in html


# ============ OS DOIS DEFEITOS QUE DESLIGAVAM O AVISO, EM SILÊNCIO ============


def test_a_busca_por_nome_nao_exclui_quem_tem_documento(casa):
    """PRIMEIRO DEFEITO. A exclusão estava escrita como

        p.documento NOT IN (SELECT documento FROM ri_cnib_pessoas ...)

    — o conjunto de TODOS os documentos do CNIB. Logo ela só deixava passar
    quem não tem documento nenhum, e **das 50.054 pessoas do CNIB, zero estão
    sem documento**: a busca por nome devolvia lista vazia sempre.

    O que ela queria dizer era «não repita quem eu já achei pelo documento» —
    e isso é a lista que se PROCUROU, não a tabela inteira.
    """
    con = _con(casa)
    with con:
        _ordem(con, nome="JOAO PEREIRA DA SILVA", documento="00011122233")
    achados = consultar_cnib(_con(casa), [], ["JOAO PEREIRA DA SILVA"])
    assert len(achados) == 1, (
        "a pessoa do CNIB tem documento, e por isso sumiu da busca por nome")
    assert achados[0]["criterio"] == "nome"


def test_quem_ja_apareceu_pelo_documento_nao_aparece_duas_vezes(casa):
    """E a exclusão continua fazendo o que devia: não repetir o mesmo achado."""
    con = _con(casa)
    with con:
        _ordem(con, nome="JOAO PEREIRA DA SILVA", documento="00011122233")
    achados = consultar_cnib(_con(casa), ["00011122233"],
                             ["JOAO PEREIRA DA SILVA"])
    assert len(achados) == 1
    assert achados[0]["criterio"] == "documento"


def test_o_acento_nao_esconde_a_ordem(casa):
    """SEGUNDO DEFEITO. `UPPER` no SQLite é ASCII: `UPPER('josé')` devolve
    `JOSé`, enquanto o `.upper()` do Python devolve `JOSÉ`. Os dois lados da
    comparação nunca se encontravam em nome com acento — e `ri_partes` tem
    **1.257** nomes acentuados.

    É a mesma pedra em que a lista de atenção para fraudes já tropeçou.
    """
    con = _con(casa)
    with con:
        _ordem(con, nome="JOSE ANTONIO DA SILVA", documento="00011122233")
    achados = consultar_cnib(_con(casa), [], ["José Antônio da Silva"])
    assert len(achados) == 1, (
        "o nome com acento não achou a ordem escrita sem acento")


def test_a_coluna_normalizada_e_a_mesma_dos_dois_lados():
    """`ri_partes.nome_norm` e `ri_cnib_pessoas.nome_norm` têm de sair da MESMA
    função — senão a comparação falha calada, que é como este defeito nasceu.
    """
    from ri_schema import MIGRACOES
    assert ("ri_cnib_pessoas", "nome_norm", "TEXT") in MIGRACOES
    esquema = (RAIZ / "ri_schema.py").read_text(encoding="utf-8")
    assert "UPDATE ri_cnib_pessoas SET nome_norm" in esquema, (
        "a coluna foi criada e não foi preenchida no acervo que já existe")
    assert "normalizar_nome" not in esquema, (
        "entrou um segundo normalizador neste módulo — ele já tem o seu")


def test_a_importacao_grava_a_forma_normalizada():
    """Sem isso a importação de amanhã entraria muda: achada por documento e
    invisível por nome."""
    importador = (RAIZ / "ri_import.py").read_text(encoding="utf-8")
    assert "normalizar_busca(p.get(\"NOME\"))" in importador
