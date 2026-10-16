"""OS ELEMENTOS DOS MODELOS — herança por atribuição, com troca por ato.

O QUE ESTES TESTES GUARDAM, e cada um custou uma decisão:

      - **os 15 papéis saem byte a byte como saíam na véspera**, e este é o
        teste que importa: foi a promessa feita ao oficial ao tirar o
        cabeçalho do desenho — «manter a forma e diminuir o risco de ir
        errado». A primeira versão da junção a quebrou **por um caractere**,
        em nove dos catorze (à época);
      - **o degrau do ato ganha do da atribuição**, que ganha do padrão;
      - **uma atribuição não herda da outra** — o encerramento do Registro de
        Imóveis não aparece no termo do Registro Civil;
      - **o formato do claro é medido, e não suposto**: um elemento
        compartilhado só existe porque os papéis da atribuição leem o mesmo
        marcador;
      - **o corpo vazio apaga a linha** e volta ao herdado, em vez de gravar
        vazio e mandar imprimir folha em branco;
      - e **o catálogo inteiro tem atribuição conhecida** — papel fora do
        de-para ficaria sem submódulo, sem erro em lugar nenhum.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import modelos_da_casa as CASA
import modelos_elementos as ELEM
import modelos_previa as PREVIA
import modelos_elementos_schema as ESQ
import ri_schema

AGORA = "2026-09-07T16:00:00"


@pytest.fixture()
def con(tmp_path):
    c = sqlite3.connect(tmp_path / "t.sqlite3")
    c.row_factory = sqlite3.Row
    # `ri_schema` traz `mo_modelos`, que é o legado que a resolução consulta.
    ri_schema.init_ri_schema(c)
    ESQ.init_modelos_elementos_schema(c)
    yield c
    c.close()


def _salvar(con, **campos):
    ELEM.salvar(con, quem="MARIO", agora=AGORA, **campos)


# ================================================ a promessa: nada mudou de forma

def test_os_papeis_saem_como_saiam_na_vespera(con):
    """**É a promessa feita ao oficial, e ela se mede — não se afirma.**

    A primeira versão de `montar_documento` juntava as partes com `strip()` em
    cada uma, e nove dos catorze (à época) perderam a quebra de linha do fim: 743
    caracteres viraram 742. Um deles é o molde da ficha da matrícula, que é
    XML de ODT. «Um caractere a menos» não se vê lendo.
    """
    for c in CASA.CATALOGO:
        assert CASA.corpo_de(con, c["chave"]) == CASA.padrao_de(c["chave"]), \
            c["chave"]


def test_sem_ajuste_nenhum_o_documento_e_so_o_corpo(con):
    for c in CASA.CATALOGO:
        assert (ELEM.montar_documento(con, c["chave"])
                == ELEM.corpo_do_ato(con, c["chave"]))


# ==================================================== os três degraus da herança

def test_o_padrao_do_codigo_e_o_piso(con):
    e = ELEM.elemento(con, atribuicao=ESQ.RI, ato="RI_CERTIDAO",
                      parte=ESQ.CORPO)
    assert e["de_onde"] == ELEM.DO_PADRAO
    assert e["texto"] == CASA.padrao_de("RI_CERTIDAO")


def test_o_elemento_da_atribuicao_vale_para_os_papeis_dela(con):
    _salvar(con, atribuicao=ESQ.RI, ato="", parte=ESQ.ENCERRAMENTO,
            corpo="Dou fé.")
    for chave in ("RI_CERTIDAO", "RI_NOTA", "RI_FICHA"):
        e = ELEM.elemento(con, atribuicao=ESQ.RI, ato=chave,
                          parte=ESQ.ENCERRAMENTO)
        assert e["de_onde"] == ELEM.DA_ATRIBUICAO
        assert e["texto"] == "Dou fé."
        assert CASA.corpo_de(con, chave).endswith("Dou fé.")


def test_o_elemento_do_ato_sobrepoe_o_da_atribuicao(con):
    """É o exemplo do oficial: a certidão com fecho diferente do resto."""
    _salvar(con, atribuicao=ESQ.RI, ato="", parte=ESQ.ENCERRAMENTO,
            corpo="Dou fé.")
    _salvar(con, atribuicao=ESQ.RI, ato="RI_CERTIDAO",
            parte=ESQ.ENCERRAMENTO, corpo="O referido é verdade.")
    proprio = ELEM.elemento(con, atribuicao=ESQ.RI, ato="RI_CERTIDAO",
                            parte=ESQ.ENCERRAMENTO)
    herdado = ELEM.elemento(con, atribuicao=ESQ.RI, ato="RI_NOTA",
                            parte=ESQ.ENCERRAMENTO)
    assert proprio["de_onde"] == ELEM.DO_ATO and proprio["proprio"]
    assert herdado["de_onde"] == ELEM.DA_ATRIBUICAO
    assert CASA.corpo_de(con, "RI_CERTIDAO").endswith("O referido é verdade.")
    assert CASA.corpo_de(con, "RI_NOTA").endswith("Dou fé.")


def test_uma_atribuicao_nao_herda_da_outra(con):
    """O fecho do Registro de Imóveis não pode aparecer no termo do civil."""
    _salvar(con, atribuicao=ESQ.RI, ato="", parte=ESQ.ENCERRAMENTO,
            corpo="Dou fé.")
    assert (CASA.corpo_de(con, "RC_TERMO_OBITO")
            == CASA.padrao_de("RC_TERMO_OBITO"))


def test_voltar_ao_herdado_apaga_so_o_proprio(con):
    _salvar(con, atribuicao=ESQ.RI, ato="", parte=ESQ.ENCERRAMENTO,
            corpo="Dou fé.")
    _salvar(con, atribuicao=ESQ.RI, ato="RI_CERTIDAO",
            parte=ESQ.ENCERRAMENTO, corpo="Outro fecho.")
    assert ELEM.restaurar(con, atribuicao=ESQ.RI, ato="RI_CERTIDAO",
                          parte=ESQ.ENCERRAMENTO)
    e = ELEM.elemento(con, atribuicao=ESQ.RI, ato="RI_CERTIDAO",
                      parte=ESQ.ENCERRAMENTO)
    assert e["texto"] == "Dou fé." and e["de_onde"] == ELEM.DA_ATRIBUICAO


def test_restaurar_o_que_nao_havia_devolve_falso(con):
    assert not ELEM.restaurar(con, atribuicao=ESQ.RI, ato="RI_NOTA",
                              parte=ESQ.RODAPE)


# ================================================= o corpo, e o que ele apaga

def test_corpo_vazio_apaga_a_linha_e_volta_ao_padrao(con):
    _salvar(con, atribuicao=ESQ.RI, ato="RI_NOTA", parte=ESQ.CORPO,
            corpo="Um corpo novo.")
    assert CASA.corpo_de(con, "RI_NOTA") == "Um corpo novo."
    _salvar(con, atribuicao=ESQ.RI, ato="RI_NOTA", parte=ESQ.CORPO, corpo="   ")
    assert CASA.corpo_de(con, "RI_NOTA") == CASA.padrao_de("RI_NOTA")


def test_nao_ha_corpo_compartilhado_pela_atribuicao(con):
    """O corpo de uma certidão não é o corpo de uma nota devolutiva.

    Oferecê-lo daria um campo que, preenchido, apagaria o texto de todos os
    papéis da atribuição de uma vez.
    """
    q = ELEM.quadro(con, ESQ.RI)
    assert [e["parte"] for e in q["comuns"]] == [ESQ.ENCERRAMENTO, ESQ.RODAPE]


# ========================================================== o de-para e o formato

def test_todo_papel_do_catalogo_tem_atribuicao_conhecida():
    """Papel fora do de-para ficaria sem submódulo, sem erro em lugar nenhum."""
    for c in CASA.CATALOGO:
        assert ELEM.atribuicao_do_ato(c["chave"]) in ESQ.ATRIBUICOES, c["chave"]


def test_a_soma_dos_submodulos_e_o_catalogo_inteiro():
    total = sum(len(ELEM.atos_da_atribuicao(a)) for a in ESQ.ATRIBUICOES)
    assert total == len(CASA.CATALOGO)


def test_o_formato_e_uniforme_dentro_de_cada_atribuicao():
    """**É isto que permite um elemento compartilhado.**

    Um encerramento em Jinja herdado por um termo do Registro Civil — que é
    `str.format` — seria texto aprovado numa conferência e recusado pela
    outra, e o escrevente descobriria com o cliente na frente.
    """
    for a in ESQ.ATRIBUICOES:
        assert ELEM.formato_da_atribuicao(a) in (CASA.JINJA, CASA.CHAVES), a


def test_as_certidoes_de_rcpj_e_rtd_estao_no_catalogo():
    """As certidões antes presas em atrib_certidao agora são editáveis.

    E ESTA LISTA ESTAVA VERMELHA DESDE ANTES DE 15/09/2026, pelo mesmo defeito
    que o `CLAUDE.md` já registra para a CONTAGEM do catálogo: alguém
    acrescentou as **quatro peças da certidão em PDF** — a capa e a faixa de
    cada — e atualizou o teste pela metade.

    APURADO NO `.cgu`, que é a régua desta casa para «esta falha é minha?»: as
    quatro chaves já estão no `modelos_da_casa.py` do pacote **3.6.131**
    (15/09), empacotado antes desta passada. Logo não são de hoje.

    **O NÚMERO FOI CORRIGIDO; O POR QUÊ DAQUELAS QUATRO É DE QUEM AS PÔS.**
    Teste vermelho que afirma o errado é pior que teste nenhum — mas inventar
    aqui a razão de outra passada seria o carimbo que mente. Elas entram na
    lista porque **estão no catálogo, medido**, e nada mais se afirma sobre
    elas. `modelos_da_casa.py` não foi tocado.
    """
    chaves = {a["chave"] for a in ELEM.atos_da_atribuicao(ESQ.RCPJ_RTD)}
    assert chaves == {"RCPJ_CERTIDAO", "RTD_CERTIDAO",
                     "RCPJ_TEOR_AVERBACAO", "RCPJ_TEOR_REGISTRO",
                     "RTD_TEOR_AVERBACAO", "RTD_TEOR_REGISTRO",
                     "RCPJ_CERTIDAO_CAPA", "RCPJ_CERTIDAO_FAIXA",
                     "RTD_CERTIDAO_CAPA", "RTD_CERTIDAO_FAIXA"}
    assert ELEM.formato_da_atribuicao(ESQ.RCPJ_RTD) == CASA.CHAVES


def test_todo_modelo_do_catalogo_tem_previa_hipotetica():
    for modelo in CASA.CATALOGO:
        documento, erro = PREVIA.renderizar(
            modelo["chave"], [CASA.padrao_de(modelo["chave"]), "", ""])
        assert not erro, (modelo["chave"], erro)
        assert documento.strip(), modelo["chave"]


def test_legenda_mostra_arroba_mas_insere_a_sintaxe_real():
    chaves = ELEM.legenda_do_ato(
        "RC_TERMO_OBITO", "Falecido {nome}, termo {numero}.")
    assert {x["rotulo"] for x in chaves} == {"@nome", "@numero"}
    assert {x["codigo"] for x in chaves} == {"{nome}", "{numero}"}
    jinja = ELEM.legenda_do_ato("CAIXA_RECIBO", "{{ sv.unit_name }}")
    assert jinja == [{"rotulo": "@sv_unit_name", "codigo": "{{ sv.unit_name }}",
                      "nome": "sv › unit name"}]


def test_atribuicao_inventada_recusa():
    with pytest.raises(ELEM.ElementoError):
        ELEM.atos_da_atribuicao("MALOTE")


def test_parte_inventada_recusa(con):
    with pytest.raises(ELEM.ElementoError):
        ELEM.elemento(con, atribuicao=ESQ.RI, ato="", parte="CABECALHO")


def test_o_cabecalho_nao_e_uma_parte_deste_modulo():
    """Decisão do oficial em 07/09/2026, e a ausência está declarada."""
    assert "CABECALHO" not in ESQ.PARTES
    assert ESQ.CABECALHO_FICOU_DE_FORA.strip()


# ============================================================ a conferência

def test_jinja_num_elemento_de_chaves_recusa(con):
    with pytest.raises(ELEM.ElementoError):
        _salvar(con, atribuicao=ESQ.RCPN, ato="RC_TERMO_OBITO",
                parte=ESQ.ENCERRAMENTO, corpo="{{ sv.registrador }}")


def test_chave_sem_fechar_num_elemento_de_chaves_recusa(con):
    with pytest.raises(ELEM.ElementoError):
        _salvar(con, atribuicao=ESQ.RCPN, ato="RC_TERMO_OBITO",
                parte=ESQ.ENCERRAMENTO, corpo="Dou fé, {escrevente.")


def test_jinja_quebrado_num_elemento_de_jinja_recusa(con):
    with pytest.raises(ELEM.ElementoError):
        _salvar(con, atribuicao=ESQ.RI, ato="RI_NOTA",
                parte=ESQ.ENCERRAMENTO, corpo="{% for x in %}")


def test_elemento_bom_grava(con):
    _salvar(con, atribuicao=ESQ.RCPN, ato="RC_TERMO_OBITO",
            parte=ESQ.RODAPE, corpo="Selo {selo}.")
    assert CASA.corpo_de(con, "RC_TERMO_OBITO").endswith("Selo {selo}.")


def test_gravar_ato_de_outra_atribuicao_recusa(con):
    """Poria o texto onde ninguém o procura, e a herança nunca o alcançaria."""
    with pytest.raises(ELEM.ElementoError):
        _salvar(con, atribuicao=ESQ.RI, ato="RC_TERMO_OBITO",
                parte=ESQ.ENCERRAMENTO, corpo="Dou fé.")


# ================================================================== o quadro

def test_o_quadro_traz_os_papeis_e_as_partes(con):
    q = ELEM.quadro(con, ESQ.RI)
    assert q["nome"] == "Registro de Imóveis"
    # **ONZE PAPÉIS DO RI** — catálogo `modelos_papeis` (3.6.221+): miolos de
    # certidão, negativa de imóvel, prenotação e Livro 3, além de cabeçalho,
    # ficha, molde e nota. O número vem do catálogo; se alguém acrescentar ou
    # retirar um papel editável, este assert avisa. 14/10/2026: 11 → 13, com
    # os miolos da certidão dominial e da vintenária reconstituídos.
    assert len(q["atos"]) == 13
    for a in q["atos"]:
        assert [p["parte"] for p in a["partes"]] == list(ESQ.PARTES)


def test_o_quadro_conta_os_ajustes(con):
    assert ELEM.quadro(con, ESQ.RI)["quantos_ajustes"] == 0
    _salvar(con, atribuicao=ESQ.RI, ato="", parte=ESQ.RODAPE, corpo="x")
    assert ELEM.quadro(con, ESQ.RI)["quantos_ajustes"] == 1


def test_esta_ajustado_ve_qualquer_parte(con):
    assert not ELEM.esta_ajustado(con, "RI_NOTA")
    _salvar(con, atribuicao=ESQ.RI, ato="RI_NOTA", parte=ESQ.RODAPE,
            corpo="Uma nota.")
    assert ELEM.esta_ajustado(con, "RI_NOTA")
    # E a tela do submodulo diz QUAL parte foi ajustada, parte por parte —
    # `quadro` ja traz o `de_onde` de cada uma. Houve aqui uma
    # `partes_ajustadas` que ninguem chamava: o varredor a apanhou, e ela foi
    # apagada em vez de ganhar uma tela para se justificar.
    partes = {e["parte"]: e["de_onde"]
              for a in ELEM.quadro(con, ESQ.RI)["atos"]
              if a["chave"] == "RI_NOTA" for e in a["partes"]}
    assert partes[ESQ.RODAPE] == ELEM.DO_ATO
    assert partes[ESQ.ENCERRAMENTO] == ELEM.DO_PADRAO


# =============================================== o legado das tabelas antigas

def test_o_ajuste_antigo_do_papel_ganha_do_da_atribuicao(con):
    """Quem ajustou o PAPEL ajustou o mais específico.

    Perder esse ajuste ao subir de versão seria apagar trabalho de alguém sem
    avisar. Medido: `mo_modelos` tem zero linhas nesta casa, mas uma
    instalação que já tivesse ajustado não pode perder o ajuste.
    """
    CASA.salvar(con, "RI_NOTA", corpo="A nota antiga.", quem="MARIO",
                agora=AGORA)
    e = ELEM.elemento(con, atribuicao=ESQ.RI, ato="RI_NOTA", parte=ESQ.CORPO)
    assert e["de_onde"] == ELEM.DO_LEGADO
    assert e["texto"] == "A nota antiga."


def test_o_elemento_novo_ganha_do_legado(con):
    CASA.salvar(con, "RI_NOTA", corpo="A nota antiga.", quem="MARIO",
                agora=AGORA)
    _salvar(con, atribuicao=ESQ.RI, ato="RI_NOTA", parte=ESQ.CORPO,
            corpo="A nota nova.")
    assert CASA.corpo_de(con, "RI_NOTA") == "A nota nova."
