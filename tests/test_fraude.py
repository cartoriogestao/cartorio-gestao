"""
Testes da LISTA DE ATENCAO PARA FRAUDES.

O QUE ELES CONFEREM

    Que ALERTA NAO E TRAVA. Nao ha funcao que recuse ato nenhum neste modulo —
    ele mostra, e quem decide e o oficial. Travar pararia o balcao para gente
    inocente, porque homonimo e a regra e nao a excecao.

    Que A VITIMA E QUEM SE PROTEGE, e nao quem se barra: o texto do alerta dela
    diz o CONTRARIO do texto do envolvido. Barrar a vitima seria fazer com o
    inocente o que o fraudador fez.

    Que ALERTA SEM PROCEDENCIA NAO ENTRA. "Fulano esta na lista" nao ajuda
    ninguem a decidir; a comunicacao, o orgao e a data ajudam.

    Que O DOCUMENTO VEM ANTES DO NOME nos achados — documento nao tem homonimo
    e nome tem, e sem essa ordem o alerta por homonimo afoga o que importa.

    Que a busca acha SEM ACENTO E SEM CAIXA, com a mesma funcao que o resto da
    casa usa.

    E que o RASTRO da conferencia fica: se um ato fraudado passar apesar do
    aviso, a pergunta e "o sistema avisou?", e a resposta tem de estar escrita.
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

import fraude as FR
from fr_schema import init_fr_schema
from nucleo_schema import init_nucleo_schema
from pt_schema import init_pt_schema

AGORA = "2026-08-26T11:00:00"


@pytest.fixture()
def con():
    c = conexao_de_teste()
    c.row_factory = sqlite3.Row
    init_nucleo_schema(c)
    init_pt_schema(c)
    init_fr_schema(c)
    yield c
    c.close()


def incluir(con, **kw):
    kw.setdefault("papel", "ENVOLVIDO")
    kw.setdefault("origem", "Ofício 123/2026, recebido pelo malote")
    kw.setdefault("agora", AGORA)
    return FR.incluir(con, **kw)


# ------------------------------------------------------------- incluir


def test_o_alerta_entra_com_nome_documento_e_procedencia(con):
    r = incluir(con, nome="José da Silva", documento="047.855.123-88",
                origem_orgao="Corregedoria-Geral", origem_data="2026-08-20",
                observacao="uso de CPF de terceiro em escritura",
                usuario="tabeliao")
    a = FR.ler(con, r["alerta_id"])
    assert a["nome"] == "José da Silva"
    # O DOCUMENTO SE GUARDA SEM PONTUACAO: buscar com ponto e traco acharia so
    # quem digitou igual, e cada balcao digita de um jeito.
    assert a["documento"] == "04785512388"
    assert a["documento_tipo"] == "CPF"
    # A FORMA NORMALIZADA E A DA CASA — minuscula, a mesma de
    # `pt_devedores.nome_norm`. Eu tinha escrito uma copia que
    # devolvia MAIUSCULAS, e a busca por nome nao achava nada.
    assert a["nome_norm"] == "jose da silva"
    assert a["situacao"] == "ATIVO"


def test_sem_nome_e_sem_documento_nao_entra(con):
    with pytest.raises(FR.FraudeError) as erro:
        incluir(con)
    assert "Informe o nome, o documento" in str(erro.value)


def test_sem_PROCEDENCIA_nao_entra(con):
    # Alerta que nao se avalia vira alerta que se ignora.
    with pytest.raises(FR.FraudeError) as erro:
        incluir(con, nome="Maria", origem="   ")
    assert "de onde veio a comunicação" in str(erro.value)


def test_papel_desconhecido_e_recusado_e_a_mensagem_lista_os_tres(con):
    with pytest.raises(FR.FraudeError) as erro:
        incluir(con, nome="Maria", papel="SUSPEITO")
    texto = str(erro.value)
    assert "VITIMA" in texto and "ENVOLVIDO" in texto and "DOCUMENTO" in texto


def test_os_tres_papeis_sao_os_do_oficial():
    # "seja vítima ou fraudador ou nome que conste em documento fraudado"
    assert set(FR.PAPEIS) == {"VITIMA", "ENVOLVIDO", "DOCUMENTO"}


def test_documento_de_tamanho_estranho_fica_SEM_TIPO(con):
    # Nao se inventa: documento de 9 digitos nao vira CPF com zeros a esquerda.
    r = incluir(con, documento="123456789")
    a = FR.ler(con, r["alerta_id"])
    assert a["documento"] == "123456789"
    assert a["documento_tipo"] is None


# ------------------------------------------------------------ conferir


def test_acha_pelo_nome_SEM_ACENTO_E_SEM_CAIXA(con):
    incluir(con, nome="JOSÉ DA SILVA")
    for escrito in ("josé da silva", "JOSE DA SILVA", "  José  da  Silva  "):
        achados = FR.conferir(con, nome=escrito)
        assert len(achados) == 1, escrito
        assert achados[0]["por_nome"] and not achados[0]["por_documento"]


def test_acha_pelo_documento_com_ou_sem_pontuacao(con):
    incluir(con, documento="04785512388")
    for escrito in ("04785512388", "047.855.123-88", "047855123-88"):
        achados = FR.conferir(con, documento=escrito)
        assert len(achados) == 1, escrito
        assert achados[0]["por_documento"]


def test_O_DOCUMENTO_VEM_ANTES_DO_NOME(con):
    """Sem esta ordem, o alerta por homônimo afoga o que importa.

    Documento não tem homônimo; nome tem. Quem está no balcão lê o primeiro.
    """
    incluir(con, nome="JOSÉ DA SILVA", papel="DOCUMENTO")      # homônimo
    incluir(con, documento="04785512388", papel="ENVOLVIDO")   # o que importa
    achados = FR.conferir(con, nome="jose da silva",
                          documento="047.855.123-88")
    assert len(achados) == 2
    assert achados[0]["forca"] == "DOCUMENTO"
    assert achados[1]["forca"] == "NOME"


def test_O_AVISO_DA_VITIMA_DIZ_O_CONTRARIO_DO_ENVOLVIDO(con):
    """A regra que mais importa deste módulo.

    A vítima está na lista porque o nome dela foi usado por outro. Barrá-la
    seria fazer com o inocente exatamente o que o fraudador fez.
    """
    incluir(con, nome="Maria Vítima", papel="VITIMA")
    incluir(con, nome="João Envolvido", papel="ENVOLVIDO")

    vitima = FR.conferir(con, nome="maria vitima")[0]
    envolvido = FR.conferir(con, nome="joao envolvido")[0]

    assert "quem se protege" in vitima["aviso"]
    assert "segue normalmente" in vitima["aviso"]
    assert "antes de lavrar" in envolvido["aviso"]
    assert vitima["aviso"] != envolvido["aviso"]
    assert vitima["papel_rotulo"] == "Vítima de fraude"


def test_ALERTA_NAO_TRAVA_e_o_modulo_nao_tem_como_travar():
    # Não existe função que recuse ato neste módulo, e é de propósito: recusar
    # um ato é decisão do oficial, e não de uma lista.
    publicas = {n for n in dir(FR) if not n.startswith("_")}
    assert not {n for n in publicas
                if any(k in n.lower() for k in ("bloquear", "impedir",
                                                "travar", "recusar"))}


def test_alerta_INATIVO_nao_alerta(con):
    r = incluir(con, nome="José da Silva")
    assert FR.conferir(con, nome="jose da silva")
    FR.inativar(con, r["alerta_id"], agora=AGORA,
                motivo="comunicação cancelada pelo órgão de origem")
    assert FR.conferir(con, nome="jose da silva") == []


def test_conferir_sem_nome_e_sem_documento_devolve_vazio(con):
    incluir(con, nome="José")
    assert FR.conferir(con) == []
    assert FR.conferir(con, nome="  ", documento="") == []


def test_conferir_confere_TODAS_as_partes_do_ato(con):
    """O ato tem partes, e não uma pessoa.

    Um título tem devedor e cedente; um assento tem os pais. Conferir uma só
    deixaria o resto passar.
    """
    incluir(con, nome="José da Silva", papel="ENVOLVIDO")
    achados = FR.conferir_pessoas(con, [
        {"nome": "Maria Souza", "papel_no_ato": "credor"},
        {"nome": "josé da silva", "papel_no_ato": "devedor"},
    ])
    assert len(achados) == 1
    # E o achado diz QUEM bateu, senão a tela não sabe o que apontar.
    assert achados[0]["papel_no_ato"] == "devedor"
    assert achados[0]["conferido_nome"] == "josé da silva"


# ---------------------------------------------------------- inativar


def test_inativar_exige_motivo_e_NAO_APAGA(con):
    r = incluir(con, nome="José da Silva")
    with pytest.raises(FR.FraudeError) as erro:
        FR.inativar(con, r["alerta_id"], motivo="não", agora=AGORA)
    assert "não se apaga sem explicação" in str(erro.value)

    FR.inativar(con, r["alerta_id"], agora=AGORA, usuario="tabeliao",
                motivo="a comunicação foi cancelada pelo órgão de origem")
    a = FR.ler(con, r["alerta_id"])
    assert a["situacao"] == "INATIVO"
    assert a is not None                    # a linha continua lá
    assert "cancelada" in a["inativado_motivo"]


def test_reativar_mantem_o_motivo_da_saida(con):
    r = incluir(con, nome="José da Silva")
    FR.inativar(con, r["alerta_id"], agora=AGORA, motivo="achei que era outro")
    FR.reativar(con, r["alerta_id"], agora=AGORA, usuario="tabeliao")
    a = FR.ler(con, r["alerta_id"])
    assert a["situacao"] == "ATIVO"
    assert "achei que era outro" in a["inativado_motivo"]
    assert FR.conferir(con, nome="jose da silva")


# ------------------------------------------------------------- o rastro


def test_o_rastro_da_conferencia_fica_escrito(con):
    """O que protege a casa não é o alerta: é o rastro de que ele foi visto."""
    r = incluir(con, nome="José da Silva")
    FR.registrar_conferencia(
        con, r["alerta_id"], decisao="PROSSEGUIU", agora=AGORA,
        onde="protesto/titulo", referencia="84713/1",
        nome="José da Silva", documento="047.855.123-88",
        observacao="conferi o RG; é outra pessoa, mesma homonímia",
        usuario="tabeliao")
    linhas = FR.conferencias(con)
    assert len(linhas) == 1
    assert linhas[0]["decisao"] == "PROSSEGUIU"
    assert linhas[0]["onde"] == "protesto/titulo"
    assert linhas[0]["documento_conferido"] == "04785512388"
    assert linhas[0]["conferido_por"] == "tabeliao"
    assert "homonímia" in linhas[0]["observacao"]


def test_decisao_fora_do_catalogo_e_recusada(con):
    r = incluir(con, nome="José")
    with pytest.raises(FR.FraudeError):
        FR.registrar_conferencia(con, r["alerta_id"], decisao="TALVEZ",
                                 agora=AGORA)


def test_conferencia_de_alerta_que_nao_existe_e_recusada(con):
    with pytest.raises(FR.FraudeError):
        FR.registrar_conferencia(con, 9999, decisao="ANOTOU", agora=AGORA)


# ------------------------------------------------------------ consultas


def test_a_lista_procura_nome_E_documento_com_o_mesmo_texto(con):
    # Quem está no balcão tem uma coisa só na mão, e não sabe se é nome ou
    # documento até digitar.
    incluir(con, nome="José da Silva", documento="04785512388")
    incluir(con, nome="Maria Souza")
    assert len(FR.listar(con, busca="silva")) == 1
    assert len(FR.listar(con, busca="0478551")) == 1
    assert len(FR.listar(con)) == 2


def test_a_contagem_serve_o_painel(con):
    incluir(con, nome="a", papel="VITIMA")
    incluir(con, nome="b", papel="ENVOLVIDO")
    incluir(con, nome="c", papel="ENVOLVIDO")
    c = FR.contagem(con)
    assert c["ativos"] == 3
    assert c["por_papel"]["ENVOLVIDO"] == 2
    assert c["conferencias"] == 0


def test_o_que_a_casa_JA_TEM_daquela_pessoa(con):
    """A comunicação chega DEPOIS do fato.

    Saber que a pessoa já tem atos aqui é o que transforma um aviso numa
    diligência.
    """
    con.execute(
        """INSERT INTO pt_titulos(especie, numero_titulo, situacao, origem,
               criado_em, cedente_nome, cedente_documento)
           VALUES ('DMI','1/1','RECEBIDO','MANUAL',?,'JOSE DA SILVA',
                   '047.855.123-88')""", (AGORA,))
    achados = FR.atos_da_pessoa(con, nome="josé da silva")
    assert len(achados) == 1
    assert achados[0]["o_que_e"] == "credor de protesto"

    # E acha pelo documento, mesmo o banco guardando com pontuação.
    assert FR.atos_da_pessoa(con, documento="04785512388")


def test_atos_da_pessoa_nao_estoura_em_banco_sem_as_tabelas():
    # Nem toda instalação tem as seis atribuições criadas, e uma consulta a
    # tabela que não existe derrubaria a tela inteira.
    c = conexao_de_teste()
    c.row_factory = sqlite3.Row
    init_fr_schema(c)
    assert FR.atos_da_pessoa(c, nome="qualquer") == []
    c.close()
