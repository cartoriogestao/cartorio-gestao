"""
Testes do que SO O OFICIAL PODE INFORMAR.

O QUE ELES CONFEREM

    Que PENDENCIA E DECLARADA, e nao adivinhada. Um sistema NOVO, sem carga
    nenhuma, nao tem pendencia alguma — e comecar do numero 1 nele esta certo.
    Se este modulo listasse "toda serie sem contador", gritaria quinze avisos
    numa instalacao limpa, e alarme que soa sempre e alarme que ninguem ouve.

    Que a carga do acervo DECLARA o que nao soube semear, com o motivo medido —
    inclusive as TRES SERIES DO RCPN que ficavam caladas ate 26/08/2026.

    Que declarar e REPETIVEL: rodar a carga duas vezes nao reabre o que o
    oficial ja resolveu nem apaga o que ele escreveu.

    Que quem recusa BAIXAR o contador continua sendo `escrituracao`, e nao
    este modulo — a regra mora num lugar so.

    E que DISPENSAR EXIGE MOTIVO ESCRITO. Dispensar e decisao do oficial;
    ignorar nao e.
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

import acervo_carga as AC
import implantacao as IMP
import livro_nucleo as LN
from nucleo_schema import init_nucleo_schema
from pt_schema import init_pt_schema
from rc_schema import init_rc_schema
from rg_schema import init_rg_schema

AGORA = "2026-08-26T10:00:00"


@pytest.fixture()
def con():
    c = conexao_de_teste()
    c.row_factory = sqlite3.Row
    init_nucleo_schema(c)
    init_pt_schema(c)
    init_rc_schema(c)
    # `rg_titulos` aponta para `cx_protocolos` (FK): o PostgreSQL cobra a FK
    # na criacao, e o banco da casa cria o caixa antes. Aqui basta o esqueleto.
    c.execute("CREATE TABLE IF NOT EXISTS cx_protocolos (id INTEGER PRIMARY KEY)")
    init_rg_schema(c)
    yield c
    c.close()


def semear(con):
    """Roda o que a carga roda no fim — é quem declara as pendências."""
    return AC.semear_numeracao(con, agora=AGORA, usuario="tabeliao")


# ------------------------------------------------- o alarme que não mente


def test_sistema_novo_nao_tem_pendencia_nenhuma(con):
    # Num banco sem carga, começar do número 1 está CERTO. Aviso que soa em
    # sistema vazio é aviso que ninguém ouve.
    assert IMP.abertas(con) == []
    assert IMP.contagem(con)["abertas"] == 0


def test_a_carga_DECLARA_o_que_nao_soube_semear(con):
    semear(con)
    abertas = IMP.abertas(con)
    chaves = {x["chave"] for x in abertas}
    assert f"{IMP.PREFIXO_NUMERACAO}:PT_PROTESTO" in chaves
    assert f"{IMP.PREFIXO_NUMERACAO}:PT_PAGAMENTO" in chaves
    # As três do RCPN ficavam CALADAS até 26/08/2026 — e caladas é pior que
    # pendentes: `rc_assento.SERIE_DA_ESPECIE` manda casamento religioso,
    # natimorto e proclamas para elas.
    assert f"{IMP.PREFIXO_NUMERACAO}:RC_B_AUXILIAR" in chaves
    assert f"{IMP.PREFIXO_NUMERACAO}:RC_C_AUXILIAR" in chaves
    assert f"{IMP.PREFIXO_NUMERACAO}:RC_D" in chaves


def test_toda_serie_que_o_nucleo_SERVE_esta_coberta(con):
    """A pergunta que achou as três caladas, virada em teste.

    Uma série que algum módulo lavra pelo núcleo e que a carga não semeia
    **tem de estar declarada**. Sem isto, acrescentar uma espécie nova ao RCPN
    amanhã traria de volta o mesmo silêncio.
    """
    import protesto as PT
    import rc_assento as RC
    import rg_registro as RG

    servidas = (set(RG.SERIES_CONHECIDAS)
                | set(RC.SERIE_DA_ESPECIE.values())
                | {PT.SERIE_APONTAMENTO, PT.SERIE_PROTESTO,
                   PT.SERIE_PAGAMENTO})
    com_fonte = {s for s, _ in AC.FONTES_DO_CONTADOR}
    caladas = servidas - com_fonte - set(AC.SEM_CONTADOR_NO_ACERVO)
    assert not caladas, (
        f"séries que o núcleo serve, sem fonte na carga e sem motivo "
        f"declarado: {sorted(caladas)} — cada uma nasceria com o número 1 e "
        f"ninguém seria avisado")


def test_a_pendencia_diz_por_que_e_o_que_acontece(con):
    semear(con)
    p = IMP.ler(con, f"{IMP.PREFIXO_NUMERACAO}:RC_D")
    assert "proclamas" in p["motivo"]
    assert "livro físico" in p["motivo"]
    assert "número 1" in p["consequencia"]
    assert p["atribuicao"] == LN.serie("RC_D").atribuicao
    assert p["serie"] == "RC_D"


def test_declarar_e_repetivel_e_nao_reabre_o_resolvido(con):
    # A carga pode rodar duas vezes, e a segunda não pode desfazer o que o
    # oficial respondeu na primeira.
    semear(con)
    chave = f"{IMP.PREFIXO_NUMERACAO}:PT_PROTESTO"
    IMP.resolver_numero(con, chave, 2157, agora=AGORA, usuario="tabeliao",
                        observacao="conferido no Livro 9, folha 200")
    semear(con)
    p = IMP.ler(con, chave)
    assert p["situacao"] == "RESOLVIDA"
    assert p["valor"] == "2157"
    assert "Livro 9" in p["observacao"]


# ----------------------------------------------------------- resolver


def test_informar_o_numero_fixa_o_contador(con):
    semear(con)
    chave = f"{IMP.PREFIXO_NUMERACAO}:PT_PROTESTO"
    r = IMP.resolver_numero(con, chave, 2157, agora=AGORA, usuario="tabeliao")
    assert r["proximo"] == 2157

    linha = con.execute("SELECT * FROM nu_numeracao WHERE serie='PT_PROTESTO'"
                        ).fetchone()
    assert linha["proximo"] == 2157
    assert IMP.contagem(con)["abertas"] == len(IMP.abertas(con))
    assert chave not in {x["chave"] for x in IMP.abertas(con)}


def test_quem_recusa_baixar_o_contador_e_a_ESCRITURACAO(con):
    """A regra mora num lugar só. Repeti-la aqui daria duas versões dela.

    E a regra é sobre o MAIOR JÁ USADO, não sobre o contador atual: enquanto
    ninguém lavrou nada, baixar o contador é seguro e está certo. O que não se
    pode é pôr o próximo número abaixo de um número que já saiu num ato — isso
    repetiria número de ordem, que é o defeito de 18/08/2026.
    """
    import escrituracao as ESC
    semear(con)
    chave = f"{IMP.PREFIXO_NUMERACAO}:PT_PROTESTO"
    ESC.fixar_numeracao(con, "PT_PROTESTO", 2157, agora=AGORA,
                        usuario="tabeliao", motivo="conferido no livro")
    # Como se atos tivessem sido lavrados até o 2156.
    con.execute("UPDATE nu_numeracao SET maior_em_uso=2156 "
                "WHERE serie='PT_PROTESTO'")

    with pytest.raises(LN.LivroError) as erro:
        IMP.resolver_numero(con, chave, 10, agora=AGORA)
    assert "repetiria número de ordem" in str(erro.value)
    # E a pendência continua aberta, porque nada foi informado.
    assert IMP.ler(con, chave)["situacao"] == "ABERTA"


def test_decisao_se_resolve_escrevendo_o_que_foi_decidido(con):
    semear(con)
    chave = IMP.CATALOGO_DE_DECISOES[0]["chave"]
    assert IMP.ler(con, chave)["tipo"] == "DECISAO"
    with pytest.raises(IMP.ImplantacaoError) as erro:
        IMP.resolver_decisao(con, chave, observacao="ok", agora=AGORA)
    assert "não responde a pergunta" in str(erro.value)

    IMP.resolver_decisao(
        con, chave, agora=AGORA, usuario="tabeliao",
        observacao="encerrei o Livro 6 com termo de que nada foi lançado")
    assert IMP.ler(con, chave)["situacao"] == "RESOLVIDA"


def test_decisao_nao_se_resolve_com_numero(con):
    semear(con)
    chave = IMP.CATALOGO_DE_DECISOES[0]["chave"]
    with pytest.raises(IMP.ImplantacaoError) as erro:
        IMP.resolver_numero(con, chave, 10, agora=AGORA)
    assert "não é de número" in str(erro.value)


def test_dispensar_exige_motivo_escrito(con):
    # Dispensar é decisão do oficial; ignorar não é. Mesma regra do usucapião.
    semear(con)
    chave = f"{IMP.PREFIXO_NUMERACAO}:RC_D"
    with pytest.raises(IMP.ImplantacaoError) as erro:
        IMP.dispensar(con, chave, motivo="não", agora=AGORA)
    assert "motivo escrito" in str(erro.value)

    IMP.dispensar(con, chave, agora=AGORA, usuario="tabeliao",
                  motivo="esta serventia nunca abriu Livro D de proclamas")
    p = IMP.ler(con, chave)
    assert p["situacao"] == "DISPENSADA"
    assert "proclamas" in p["observacao"]
    assert chave not in {x["chave"] for x in IMP.abertas(con)}


def test_reabrir_nao_apaga_o_que_foi_escrito(con):
    # Engano se conserta à vista, e não apagando o que se disse antes.
    semear(con)
    chave = f"{IMP.PREFIXO_NUMERACAO}:RC_D"
    IMP.dispensar(con, chave, agora=AGORA, motivo="achei que não se usava")
    IMP.reabrir(con, chave, agora=AGORA, usuario="tabeliao")
    p = IMP.ler(con, chave)
    assert p["situacao"] == "ABERTA"
    assert "achei que não se usava" in p["observacao"]


def test_pendencia_que_nao_existe_nao_estoura(con):
    with pytest.raises(IMP.ImplantacaoError):
        IMP.resolver_numero(con, "numeracao:NAO_EXISTE", 10, agora=AGORA)
    with pytest.raises(IMP.ImplantacaoError):
        IMP.dispensar(con, "x:y", motivo="dez caracteres", agora=AGORA)


# ------------------------------------------------------------ consultas


def test_a_contagem_serve_o_aviso_de_qualquer_tela(con):
    semear(con)
    c = IMP.contagem(con)
    assert c["abertas"] == len(IMP.abertas(con))
    # Agrupada por atribuição, para o aviso poder dizer de quais são.
    assert 2 in c["por_atribuicao"]           # Protesto
    assert 6 in c["por_atribuicao"]           # Registro Civil
    assert "Protesto" in c["atribuicoes"]


def test_a_lista_vem_por_atribuicao(con):
    semear(con)
    abertas = IMP.abertas(con)
    atribuicoes = [x["atribuicao"] for x in abertas]
    assert atribuicoes == sorted(atribuicoes)
    assert all(x["atribuicao_nome"] for x in abertas)
    assert all(x["serie_nome"] for x in abertas if x["serie"])


def test_as_fechadas_ficam_guardadas(con):
    semear(con)
    IMP.resolver_numero(con, f"{IMP.PREFIXO_NUMERACAO}:PT_PROTESTO", 2157,
                        agora=AGORA, usuario="tabeliao", observacao="Livro 9")
    fechadas = IMP.fechadas(con)
    assert len(fechadas) == 1
    assert fechadas[0]["valor"] == "2157"
    assert fechadas[0]["resolvida_por"] == "tabeliao"


def test_tipo_desconhecido_e_recusado(con):
    with pytest.raises(IMP.ImplantacaoError):
        IMP.declarar(con, "x", tipo="INVENTADO", titulo="t", motivo="m",
                     agora=AGORA)


def test_a_letra_da_566_entrou_como_DECISAO(con):
    """A pendência que o segundo acervo tornou decidível.

    Ela estava numa lista dentro da documentação desde 24/08/2026. Em
    26/08 o acervo da serventia de Sergipe mostrou uma terceira opção que
    ninguém tinha: **branco** — 2.087 retornos de lá vêm com a posição 566
    vazia, e a Central aceita.

    Documentação não avisa ninguém; a aba avisa.
    """
    semear(con)
    chaves = {x["chave"] for x in IMP.abertas(con)}
    chave = f"{IMP.PREFIXO_DECISAO}:PT_RETORNO:letra-566"
    assert chave in chaves
    p = IMP.ler(con, chave)
    assert p["tipo"] == "DECISAO"
    assert p["atribuicao"] == 2
    # As três opções medidas ficam à vista de quem decide.
    assert "branco" in p["motivo"] and "2.087" in p["motivo"]
    assert "RECUSADO" in p["consequencia"]
