"""O acervo não vira atraso — e este varredor pega a classe inteira.

O DEFEITO, ACHADO NO ENSAIO CONTRA A PRODUÇÃO EM 30/08/2026
    `sirc_remessa.pendentes_de_remessa` devolvia **243 registros, o mais antigo
    de 12/10/1955**, numa tela que diz «o prazo é de 1 dia útil». Aquele
    nascimento apareceria com vinte e cinco mil dias de atraso, numa lista que o
    balcão não teria como zerar.

    **E não era um módulo: eram três.** As comunicações mensais listariam oito
    meses «em atraso», o mais antigo de março de 2009. Os termos a escrever
    mostravam 244, e nenhum deles é trabalho.

POR QUE UM VARREDOR, E NÃO TRÊS CONSERTOS
    Porque o quarto módulo vai nascer amanhã. **O que se repete não se conserta:
    guarda-se.** Este teste semeia um banco com **um assento do acervo e mais
    nada** e pergunta a cada lista de pendência quantas ela vê. Quem contar o
    assento do acervo como trabalho fica vermelho aqui.

E HÁ DUAS LISTAS QUE O CONTAM DE PROPÓSITO
    A **carga da CRC** existe justamente para subir o acervo histórico à Central
    (`ACAO_CARGA = "CARGA"`) — ali 243 é o número certo. E os **termos** listam
    os do acervo porque a tela explica que eles ficam sem termo de propósito.

    **Elas são declaradas aqui, com o motivo.** Exceção sem motivo escrito é
    exceção que alguém copia para o módulo seguinte sem saber por quê.
"""
from __future__ import annotations

import glob
import importlib
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

AGORA = "2026-08-20T09:00"

# AS LISTAS DE PENDENCIA DO RCPN que leem `rc_assentos`. Cada uma diz se o
# assento do acervo entra — e por que.
LISTAS: tuple[dict, ...] = (
    {"modulo": "sirc_remessa", "funcao": "pendentes_de_remessa",
     "conta_o_acervo": False,
     "porque": "a remessa é do que se REGISTROU, e o registro deles é de "
               "décadas atrás — o prazo de um dia útil não alcança digitação"},
    {"modulo": "rc_comunicacoes", "funcao": "meses_sem_comunicacao",
     "conta_o_acervo": False,
     "porque": "a comunicação de um óbito de 2009 era devida em 2009, pelo "
               "E-Ofício — e não em 2026, porque alguém o digitou"},
    {"modulo": "ibge_geracao", "funcao": "a_prestar",
     "conta_o_acervo": False,
     "porque": "o E-Ofício já entregou aqueles trimestres, e dizer o contrário "
               "seria acusar setenta anos de livro"},
    {"modulo": "rc_dados_cadastrais", "funcao": "quantas_pendentes",
     "conta_o_acervo": True,
     "porque": "**é o oposto**: o art. 347 alcança justamente os assentos "
               "anteriores a 14/11/2017, que são os do acervo. Uma lista que os "
               "excluísse ficaria sempre vazia"},
    # **A FILA DA CERTIDÃO ELETRÔNICA NASCEU EM 03/09/2026 E NÃO SE DECLAROU**,
    # e foi este varredor que cobrou — que é o que ele existe para fazer.
    {"modulo": "rc_pedidos", "funcao": "pendentes",
     "conta_o_acervo": False,
     "porque": "**o acervo não entra nela por construção, e não por filtro**: "
               "`rc_pedidos` só recebe o que a Central manda AGORA, pela API "
               "da Certidão Eletrônica. Não há um único pedido de 1955 ali "
               "para excluir — a tabela nasceu depois da carga e nunca a viu"},
    {"modulo": "crc_carga", "funcao": "pendentes_de_carga",
     "conta_o_acervo": True,
     "porque": "a carga é *justamente* a subida do acervo histórico à Central "
               "(`ACAO_CARGA = \"CARGA\"`) — excluí-lo apagaria a razão de ela "
               "existir"},
    # **MUDOU DE LADO EM 30/08/2026, POR ORDEM DO OFICIAL** — e foi este
    # varredor que cobrou a mudança, que é o que ele existe para fazer.
    #
    # Antes os do acervo apareciam com uma legenda explicando que ficavam sem
    # termo de propósito. O oficial: «aparentemente vc esta gerando uma
    # expectativa de termo, que nao corresponde à realidade».
    #
    # **LISTA É PROMESSA**: o que está numa lista de trabalho é trabalho que
    # alguém vai fazer, por mais que a legenda diga o contrário.
    {"modulo": "rc_termo", "funcao": "assentos_sem_termo",
     "conta_o_acervo": False,
     "porque": "o termo deles existe **em papel, assinado**, e o sistema guarda "
               "as informações — que servem à certidão. Eles têm lista própria, "
               "`informacoes_importadas`, que não é lista de trabalho"},

    # ---------------------------------------------------------------------
    # AS CINCO QUE O PROPRIO VARREDOR ACHOU, na primeira vez que rodou. Era
    # exatamente para isso que ele existe — e ele achou mais do que eu tinha
    # visto olhando modulo a modulo.
    {"modulo": "rc_anotacao", "funcao": "pendentes",
     "conta_o_acervo": False,
     "porque": "as anotações são **declaradas** ao lavrar o ato, por "
               "`rc_anotacao.declarar` — e a carga não lavra ato: ela traz o "
               "que já foi lavrado. Aqui o acervo fica de fora por construção, "
               "e não por filtro"},
    {"modulo": "rc_comunicacoes", "funcao": "pendentes",
     "conta_o_acervo": False,
     "porque": "esta lista mostra as comunicações **já declaradas** que ainda "
               "não saíram, e a carga não declara nenhuma — quem declara é o "
               "oficial, mês a mês"},
    {"modulo": "rc_dados_cadastrais", "funcao": "pendentes",
     "conta_o_acervo": True,
     "porque": "**é o oposto**, como `quantas_pendentes`: o art. 347 alcança "
               "justamente os assentos anteriores a 14/11/2017"},
    {"modulo": "rc_funai", "funcao": "pendentes",
     "conta_o_acervo": True,
     "porque": "o RANI é **o documento da pessoa**, e não uma remessa "
               "estatística: se ele não foi feito, a criança segue sem ele — e "
               "o tempo não apaga isso. O prazo já correu; o que importa é "
               "fazer, e a tela diz as duas coisas"},
    {"modulo": "rc_gemeos", "funcao": "pendentes",
     "conta_o_acervo": True,
     "porque": "a ordem de nascimento é **requisito do assento** (art. 233, "
               "III), e a falta é real mesmo num assento de 1990 — mas ali o "
               "caminho é a **retificação** (art. 352, I), e não editar o "
               "campo: a tela diz isso"},
    # A DIGITALIZAÇÃO DO TERMO NASCEU EM 08/10/2026 (problema #121, pacote
    # 3.6.288) E NÃO SE DECLAROU — declarada em 14/10/2026, cobrada por este
    # varredor. O módulo já excluía o acervo; faltava dizer aqui.
    {"modulo": "rc_digitalizacao", "funcao": "pendentes",
     "conta_o_acervo": False,
     "porque": "a obrigação de digitalizar o termo assinado vale só para o que "
               "ESTE sistema lavra (`origem='MANUAL'`) depois do corte "
               "`rc_digitalizacao_obrigatoria_desde`; o acervo (EOFICIO, "
               "IMPORTACAO, ARQUIVO) fica de fora por construção"},
)


@pytest.fixture()
def casa(cg_casa):
    """App/DB compartilhados do modulo (conftest); setup de dominio por teste."""
    db = cg_casa["db"]
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", "Senha#12345", "ADMIN")
    return cg_casa

def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _um_assento_do_acervo(con):
    """O acervo em miniatura — e ele cobre os cinco casos.

    **UM SEED QUE NÃO ALCANÇA A LISTA NÃO PROVA NADA SOBRE ELA.** Sem o
    nascimento indígena, `rc_funai` devolveria zero por não ter o que ver, e o
    teste passaria dizendo o contrário do que quer dizer. Sem o gêmeo, o mesmo
    em `rc_gemeos`.
    """
    cur = con.execute(
        """INSERT INTO rc_assentos (serie, especie, numero, nome, data_ato,
               data_fato, situacao, origem, criado_em)
           VALUES ('RC_A','NASCIMENTO',283,'HEITOR DIAS CAMARGO','1955-10-12',
                   '1955-10-01','ATIVO','EOFICIO',?)""", (AGORA,))
    aid = int(cur.lastrowid)
    # O OBITO DE 2009 — o que fazia as comunicacoes mensais listarem oito meses.
    con.execute(
        """INSERT INTO rc_assentos (serie, especie, numero, nome, data_ato,
               data_fato, situacao, origem, criado_em)
           VALUES ('RC_C','OBITO',12,'ANTONIO DIAS','2009-03-14','2009-03-13',
                   'ATIVO','EOFICIO',?)""", (AGORA,))
    # O NASCIMENTO INDIGENA — quatro deles vieram na carga, todos Krikati.
    con.execute(
        """INSERT INTO rc_assentos (serie, especie, numero, nome, data_ato,
               data_fato, situacao, origem, criado_em, cor_raca)
           VALUES ('RC_A','NASCIMENTO',19132,'CAMILO KRIKATI','2022-12-12',
                   '2022-10-15','ATIVO','EOFICIO',?,'Indigena')""", (AGORA,))
    # E UM PARTO MULTIPLO, sem a ordem de nascimento.
    con.execute(
        """INSERT INTO rc_assentos (serie, especie, numero, nome, data_ato,
               data_fato, situacao, origem, criado_em, ibge_gemeo)
           VALUES ('RC_A','NASCIMENTO',9001,'MARIA GEMEA','1990-04-02',
                   '1990-04-01','ATIVO','EOFICIO',?,2)""", (AGORA,))
    return aid


def _quantas(nome_modulo, nome_funcao, con):
    modulo = importlib.import_module(nome_modulo)
    funcao = getattr(modulo, nome_funcao)
    import inspect
    parametros = inspect.signature(funcao).parameters
    r = (funcao(con, hoje="2026-08-30") if "hoje" in parametros
         else funcao(con))
    return r if isinstance(r, int) else len(r)


@pytest.mark.parametrize("lista", [x for x in LISTAS if not x["conta_o_acervo"]],
                         ids=lambda x: x["modulo"])
def test_o_acervo_nao_conta_como_atraso(casa, lista):
    """**O QUE VEIO DO ACERVO NÃO É TRABALHO DE HOJE.**

    Semeia um assento de 1955 e um óbito de 2009 — e mais nada — e exige que a
    lista veja **zero**. Quem contá-los põe setenta anos de livro numa fila com
    prazo, e o balcão não tem como zerá-la.
    """
    con = _con(casa)
    with con:
        _um_assento_do_acervo(con)
    quantas = _quantas(lista["modulo"], lista["funcao"], con)
    assert quantas == 0, (
        f"`{lista['modulo']}.{lista['funcao']}` contou {quantas} — mas "
        f"{lista['porque']}.")


@pytest.mark.parametrize("lista", [x for x in LISTAS if x["conta_o_acervo"]],
                         ids=lambda x: x["modulo"])
def test_as_listas_que_contam_o_acervo_de_proposito(casa, lista):
    """As três exceções, e cada uma com o motivo escrito.

    **EXCEÇÃO SEM MOTIVO É EXCEÇÃO QUE ALGUÉM COPIA** para o módulo seguinte sem
    saber por quê — e aí o defeito volta pela porta que a exceção abriu.
    """
    con = _con(casa)
    with con:
        _um_assento_do_acervo(con)
    quantas = _quantas(lista["modulo"], lista["funcao"], con)
    assert quantas > 0, (
        f"`{lista['modulo']}.{lista['funcao']}` deveria contar o assento do "
        f"acervo, porque {lista['porque']} — e contou {quantas}.")


def test_toda_excecao_diz_por_que():
    """Sem isto a lista de exceções vira uma lista de nomes, que é como a
    `MODULOS_COM_SECAO` envelheceu."""
    for x in LISTAS:
        assert len(x["porque"]) > 40, f"{x['modulo']} sem motivo escrito"


def test_a_lista_cobre_o_que_existe():
    """**VARREDOR QUE DEIXA DE ACHAR PASSA CALADO.** Se um módulo do RCPN ganhar
    uma lista de pendência e ninguém a declarar aqui, este teste avisa.

    A varredura procura a FORMA — uma função pública cujo nome começa por
    `pendentes`, `a_prestar` ou `meses_sem` —, e não uma palavra solta.
    """
    import re
    esperados = set()
    for arquivo in RAIZ.glob("rc_*.py"):
        codigo = arquivo.read_text(encoding="utf-8")
        for nome in re.findall(
                r"^def (pendentes\w*|a_prestar|meses_sem_\w+)\(", codigo,
                re.M):
            esperados.add((arquivo.stem, nome))
    declarados = {(x["modulo"], x["funcao"]) for x in LISTAS}
    faltando = esperados - declarados
    assert not faltando, (
        "Estas listas de pendência do RCPN não dizem se contam o acervo: "
        + ", ".join(f"{m}.{f}" for m, f in sorted(faltando))
        + ". Declare em LISTAS, com o motivo — foi assim que o SIRC listou "
          "243 registros de 1955 numa tela de um dia útil.")


# --------------------------------------------------------------------------
# E O VARREDOR NAO ALCANCAVA `inacabados`, PORQUE SO OLHAVA `rc_assentos`.
#
#   **Medido na producao em 30/08/2026**: a fonte do protocolo do balcao
#   contava **21.348 atendimentos em aberto, 21.342 deles do E-Oficio**. O
#   painel anunciaria vinte e um mil pendencias.
#
#   O varredor de cima semeia um assento do acervo e pergunta as listas do
#   RCPN. `inacabados` le NOVE tabelas, e nenhuma delas e `rc_assentos` — ele
#   passou ao lado. **Varredor tem escopo, e o escopo e a parte que envelhece.**


def _colunas(con, tabela: str) -> set[str]:
    return {r[1] for r in con.execute(f"PRAGMA table_info({tabela})")}


def test_toda_fonte_que_le_tabela_com_acervo_se_declara(casa):
    """A tabela guarda coluna `origem`? Entao a fonte diz o que faz com ela.

    **DIZER NAO E FILTRAR, e e de proposito.** Tres das quatro nao filtram, e
    estao certas — uma pela situacao, uma porque o acervo nao tem a tabela, e
    a **prenotacao por acidente**: as 784 do acervo so nao aparecem porque
    ganharam `ato_id` em 28/08/2026. O que este teste exige e que a razao esteja
    **escrita**, para a proxima fonte nao herdar a coincidencia sem saber.
    """
    import inacabados as IN

    con = _con(casa)
    sem_declarar = []
    for f in IN.FONTES:
        if "origem" in _colunas(con, f["tabela"]) and not f.get("o_acervo"):
            sem_declarar.append(f"{f['chave']} ({f['tabela']})")
    con.close()
    assert not sem_declarar, (
        "estas fontes leem tabela que guarda acervo e nao dizem o que fazem "
        "com ele: " + ", ".join(sem_declarar)
        + ". Escreva `o_acervo` na fonte — filtrando, ou dizendo por que nao "
          "precisa. Foi assim que o protocolo do balcao mostrou 21.342 "
          "atendimentos do E-Ofício como trabalho de hoje.")


def test_o_protocolo_do_balcao_nao_conta_o_eoficio(casa):
    """O caso que aconteceu, com as duas linhas lado a lado.

    Um protocolo do E-Ofício e um da casa, **os dois na mesma situacao**. Se a
    fonte contasse os dois, a lista do balcao nasceria com vinte e um mil itens
    que ninguem tem como zerar — e lista que nao se zera e lista que ninguem
    abre duas vezes.
    """
    import inacabados as IN

    con = _con(casa)
    con.execute(
        "INSERT INTO cx_protocolos (numero, interessado, data_abertura, "
        "situacao, origem, criado_em) VALUES (?,?,?,?,?,?)",
        ("2019.01.001", "GENTE DE OUTRO TEMPO", "2019-03-04", "PAGO",
         "EOFICIO", AGORA))
    con.execute(
        "INSERT INTO cx_protocolos (numero, interessado, data_abertura, "
        "situacao, origem, criado_em) VALUES (?,?,?,?,?,?)",
        ("2026.08.900", "QUEM ESTA NO BALCAO HOJE", "2026-08-28", "PAGO",
         "MANUAL", AGORA))
    con.commit()

    achados = IN.lista(con, hoje="2026-08-30", chave="BALCAO_PROTOCOLO")
    con.close()

    rotulos = [x["rotulo"] for x in achados]
    assert rotulos == ["QUEM ESTA NO BALCAO HOJE"], (
        "a fonte do protocolo trouxe o acervo junto: " + str(rotulos))


def test_pago_nao_e_situacao_terminal(casa):
    """**Pago nao e entregue**, e confundi-los faria sumir da lista o servico
    que o cliente pagou e ainda nao recebeu — que e justamente o que o balcao
    precisa lembrar de entregar."""
    import inacabados as IN

    con = _con(casa)
    con.execute(
        "INSERT INTO cx_protocolos (numero, interessado, data_abertura, "
        "situacao, origem, criado_em) VALUES (?,?,?,?,?,?)",
        ("2026.08.901", "PAGOU E NAO LEVOU", "2026-08-29", "PAGO", "MANUAL", AGORA))
    con.commit()
    achados = IN.lista(con, hoje="2026-08-30", chave="BALCAO_PROTOCOLO")
    con.close()
    assert [x["rotulo"] for x in achados] == ["PAGOU E NAO LEVOU"]
