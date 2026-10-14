"""
Testes dos PROBLEMAS DO SISTEMA — o que quebrou, e o relatorio do conserto.

NENHUM DELES FALA COM A REDE. O que se prova aqui e a REGRA.

O QUE ELES CONFEREM

      - A MESMA COISA DUAS VEZES E UMA LINHA COM UM CONTADOR. Um defeito que
        acontece quarenta vezes num dia geraria quarenta linhas, e as quarenta
        afogariam os outros tres problemas da lista;
      - NUMERO NAO DISTINGUE DEFEITO: «matricula 1.234 nao existe» e «matricula
        5.678 nao existe» sao o mesmo defeito, e cada cliente que passasse pela
        tela nao pode virar uma linha nova;
      - DISPUTA DE ESCRITA NAO SE ANOTA NO BANCO — gravar no banco que acabou
        de travar e disputar a mesma trava, e o balcao esperaria os dez
        segundos do `busy_timeout` por uma tela que ja deu errado;
      - ANOTAR NUNCA ESTOURA: um anotador que quebra enquanto anota um erro
        transforma um defeito em dois e esconde o primeiro;
      - O QUE VOLTOU DEPOIS DE RELATADO volta para ABERTO e guarda a data em
        que foi mandado — «voltou depois do conserto» e a linha mais importante
        da lista;
      - O RELATORIO SAI MASCARADO, porque nasce para deixar a serventia;
      - E MARCA COMO MANDADO SO O QUE COUBE NELE. Marcar o que ficou de fora
        faria sumir da lista o que ninguem recebeu;
      - A AJUDA AUXILIA, NAO DECIDE — varredura dos nomes publicos, como no
        modulo de fraudes e no da ajuda;
      - A LISTA TEM VISTAS, E ABRE NO QUE AINDA PEDE ALGUMA COISA — relato #82:
        os 62 resolvidos afogavam os 20 abertos numa tabela unica. As vistas
        sao tres, a contagem acompanha o filtro, e o resolvido se ordena pela
        data em que foi resolvido (e nao pela ultima vez que aconteceu);
      - E A PALAVRA QUE O MODULO NAO CONHECE NAO SE DISFARCA DE RESOLVIDO: ela
        aparece como e, ganha numero proprio no quadro e vira achado da
        conferencia — o #77 estava gravado «FECHADO», e a tela o pintava de
        verde;
      - QUEM FECHA DIZ O QUE FEZ. Das 65 linhas resolvidas, 58 nao tinham uma
        linha de explicacao — e escrever a que faltava nao pode regravar quem
        fechou nem quando.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ajuda as AJ                                 # noqa: E402
import ajuda_problemas as AP                       # noqa: E402

AGORA = "2026-08-26T16:00:00"
DEPOIS = "2026-08-26T17:30:00"
# Setembro, para a ordem dos resolvidos: o relato #82 nasceu medindo a lista de
# uma casa que fechou 27 problemas numa tarde, e o que se prova aqui é que o
# mais novo vem primeiro — com dois meses de distancia entre um e outro.
SETEMBRO = "2026-09-17T11:18:00"


def banco() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    AJ.init_ajuda_schema(con)
    AP.init_problemas_schema(con)
    # As duas tabelas que a conferencia da casa le, e que em producao vem de
    # `database.py` e de `nucleo_schema.py`.
    con.executescript(
        """CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
           CREATE TABLE IF NOT EXISTS nu_implantacao(
               chave TEXT PRIMARY KEY, situacao TEXT NOT NULL,
               atribuicao INTEGER);""")
    return con


def test_banco_anterior_recebe_a_prova_da_leitura_de_codigo():
    con = sqlite3.connect(":memory:")
    con.executescript(
        """CREATE TABLE aj_problemas (
               id INTEGER PRIMARY KEY,
               impressao TEXT NOT NULL UNIQUE,
               origem TEXT NOT NULL,
               onde TEXT,
               titulo TEXT NOT NULL,
               situacao TEXT NOT NULL DEFAULT 'ABERTO',
               primeira_em TEXT NOT NULL,
               ultima_em TEXT NOT NULL
           );"""
    )

    AP.init_problemas_schema(con)

    colunas = {r[1] for r in con.execute("PRAGMA table_info(aj_problemas)")}
    assert {coluna for tabela, coluna, _tipo in AP.MIGRACOES
            if tabela == "aj_problemas"} <= colunas
    AP.init_problemas_schema(con)  # abrir novamente não duplica migração


class _DbDeMentira:
    """O minimo que `anotar_falha_de_tela` pede: `transaction()`."""

    def __init__(self, con, quebrado: bool = False):
        self.con = con
        self.quebrado = quebrado

    def transaction(self):
        con, quebrado = self.con, self.quebrado

        class _Ctx:
            def __enter__(self):
                if quebrado:
                    raise sqlite3.OperationalError("disk I/O error")
                return con

            def __exit__(self, *a):
                return False
        return _Ctx()


# ------------------------------------------------ uma linha por especie


def test_a_mesma_coisa_duas_vezes_e_uma_linha_com_contador():
    con = banco()
    um = AP.anotar(con, origem="RELATADO", titulo="o botão não faz nada",
                   onde="caixa", agora=AGORA)
    dois = AP.anotar(con, origem="RELATADO", titulo="o botão não faz nada",
                     onde="caixa", agora=DEPOIS)
    assert um["id"] == dois["id"]
    assert um["nova"] and not dois["nova"]
    assert dois["vezes"] == 2
    assert AP.contagem(con)["total"] == 1


def test_numero_nao_distingue_defeito():
    """Cada cliente que passasse pela tela viraria uma linha nova."""
    con = banco()
    um = AP.anotar(con, origem="ERRO_DE_TELA", onde="ri_matricula",
                   titulo="ValueError — matrícula 1.234 não existe",
                   detalhe="linha 500", agora=AGORA)
    dois = AP.anotar(con, origem="ERRO_DE_TELA", onde="ri_matricula",
                     titulo="ValueError — matrícula 5.678 não existe",
                     detalhe="linha 500", agora=DEPOIS)
    assert um["id"] == dois["id"]


def test_telas_diferentes_sao_problemas_diferentes():
    """A mesma frase em duas telas sao dois defeitos, e se consertam em dois
    lugares."""
    con = banco()
    um = AP.anotar(con, origem="ERRO_DE_TELA", onde="caixa",
                   titulo="KeyError — 'valor'", agora=AGORA)
    dois = AP.anotar(con, origem="ERRO_DE_TELA", onde="notas_atos",
                     titulo="KeyError — 'valor'", agora=AGORA)
    assert um["id"] != dois["id"]


def test_origem_que_nao_existe_e_recusada():
    con = banco()
    with pytest.raises(AP.ProblemaError, match="Origem"):
        AP.anotar(con, origem="SEI_LA", titulo="algo", agora=AGORA)


def test_problema_sem_titulo_e_recusado():
    con = banco()
    with pytest.raises(AP.ProblemaError, match="Escreva"):
        AP.anotar(con, origem="RELATADO", titulo="   ", agora=AGORA)


# --------------------------------------------- a tela que estoura sozinha


def _erro_de_verdade() -> Exception:
    try:
        {}["numero_do_titulo"]
    except KeyError as erro:
        return erro
    raise AssertionError("era para ter estourado")


def test_a_tela_que_estoura_vira_uma_linha_sozinha():
    """Ninguem precisa lembrar de anotar — e em dia de movimento e a lembranca
    que se perde primeiro."""
    con = banco()
    r = AP.anotar_falha_de_tela(_DbDeMentira(con), _erro_de_verdade(),
                                agora=AGORA, onde="caixa", caminho="/caixa",
                                versao="3.6.15", usuario="tabeliao")
    assert r and r["nova"]
    linha = AP.ler(con, r["id"])
    assert linha["origem"] == "ERRO_DE_TELA"
    assert "KeyError" in linha["titulo"]
    # O PONTO DA CASA, e nao a ultima linha do Flask: e ali que se conserta.
    assert "test_ajuda_problemas.py" in linha["titulo"]
    assert "Traceback" in linha["detalhe"]
    assert linha["ultimo_usuario"] == "tabeliao"


def test_disputa_de_escrita_NAO_se_anota_no_banco():
    """Gravar no banco que acabou de travar e disputar a mesma trava.

    E o balcao esperaria mais dez segundos por uma tela que ja deu errado.
    Essa especie ja esta contada em `disputas_de_escrita.log`, que e arquivo.
    """
    con = banco()
    travou = sqlite3.OperationalError("database is locked")
    assert AP.anotar_falha_de_tela(_DbDeMentira(con), travou,
                                   agora=AGORA, onde="caixa") is None
    assert AP.contagem(con)["total"] == 0


def test_anotar_nunca_estoura():
    """Um defeito nao pode virar dois, e o primeiro nao pode se esconder."""
    con = banco()
    assert AP.anotar_falha_de_tela(_DbDeMentira(con, quebrado=True),
                                   _erro_de_verdade(), agora=AGORA,
                                   onde="caixa") is None


# ------------------------------------------- o que volta depois de relatado


def test_o_que_volta_depois_de_relatado_e_a_linha_mais_importante():
    """Ou o conserto nao veio, ou nao era o conserto. As duas merecem ficar
    a vista."""
    con = banco()
    r = AP.anotar(con, origem="RELATADO", titulo="o número sai errado",
                  onde="caixa", agora=AGORA)
    AP.anotar_relatorio(con, arquivo="x.md", ids=[r["id"]], agora=AGORA)
    assert AP.ler(con, r["id"])["situacao"] == "RELATADO"

    AP.anotar(con, origem="RELATADO", titulo="o número sai errado",
              onde="caixa", agora=DEPOIS)
    linha = AP.ler(con, r["id"])
    assert linha["situacao"] == "ABERTO"
    assert linha["relatado_em"] == AGORA        # nao se apaga
    assert AP.contagem(con)["voltaram"] == 1


def test_o_relatorio_marca_so_o_que_coube_nele():
    """A primeira versao marcava TODOS os abertos.

    Um problema que ficasse de fora pelo teto sairia da lista como se tivesse
    sido mandado — e ninguem consertaria o que ninguem recebeu.
    """
    con = banco()
    um = AP.anotar(con, origem="RELATADO", titulo="primeiro", agora=AGORA)
    dois = AP.anotar(con, origem="RELATADO", titulo="segundo", agora=AGORA)
    AP.anotar_relatorio(con, arquivo="x.md", ids=[um["id"]], agora=AGORA)
    assert AP.ler(con, um["id"])["situacao"] == "RELATADO"
    assert AP.ler(con, dois["id"])["situacao"] == "ABERTO"


def test_fechar_e_reabrir():
    con = banco()
    r = AP.anotar(con, origem="RELATADO", titulo="algo", agora=AGORA)
    AP.fechar(con, r["id"], agora=DEPOIS, usuario="JEAN",
              nota="era o cabo da impressora")
    linha = AP.ler(con, r["id"])
    assert linha["situacao"] == "RESOLVIDO"
    assert "cabo" in linha["fechado_nota"]
    AP.reabrir(con, r["id"], agora=DEPOIS, usuario="JEAN")
    assert AP.ler(con, r["id"])["situacao"] == "ABERTO"


def test_fechar_problema_que_nao_existe_e_erro_de_regra():
    con = banco()
    with pytest.raises(AP.ProblemaError, match="não encontrado"):
        AP.fechar(con, 999, agora=AGORA)


def test_a_janela_mostra_o_que_ja_deu_errado_naquela_tela():
    """Quem topa hoje com o defeito que outro topou ontem merece saber que nao
    e ele que esta fazendo errado."""
    con = banco()
    AP.anotar(con, origem="ERRO_DE_TELA", titulo="KeyError", onde="caixa",
              agora=AGORA)
    AP.anotar(con, origem="ERRO_DE_TELA", titulo="KeyError", onde="notas_atos",
              agora=AGORA)
    assert len(AP.da_tela(con, "caixa")) == 1
    assert AP.da_tela(con, "tela_sem_problema") == []
    assert AP.da_tela(con, None) == []


def test_problema_resolvido_some_da_janela():
    """Aviso que fica para sempre e aviso que ninguem le mais."""
    con = banco()
    r = AP.anotar(con, origem="ERRO_DE_TELA", titulo="KeyError", onde="caixa",
                  agora=AGORA)
    AP.fechar(con, r["id"], agora=DEPOIS, usuario="JEAN",
              nota="era o campo que faltava no contexto da tela")
    assert AP.da_tela(con, "caixa") == []


# ------------------------------------------------- a conferencia da casa


def test_a_conferencia_ve_o_gatilho_medido_das_disputas():
    """Cinco em trinta dias e o sinal de conversar sobre trocar de banco."""
    con = banco()
    achados = AP.conferir_a_casa(
        con, agora=AGORA,
        disputas={"total": 9, "recentes": 6, "primeira": "2026-08-01",
                  "ultima": "2026-08-26"})
    graves = [a for a in achados if a["chave"] == "disputas"]
    assert graves and graves[0]["grave"]
    assert "MIGRAR_DE_BANCO" in graves[0]["detalhe"]


def test_uma_disputa_ou_outra_e_normal_e_nao_e_grave():
    con = banco()
    achados = AP.conferir_a_casa(
        con, agora=AGORA,
        disputas={"total": 1, "recentes": 1, "ultima": "2026-08-26"})
    assert not [a for a in achados if a["grave"]]


def test_a_conferencia_ve_o_que_so_o_oficial_pode_informar():
    """Serie sem contador e o primeiro ato novo nascendo com o numero 1 sobre
    acervo que ja passou disso — o defeito de 18/08/2026."""
    con = banco()
    con.execute("""INSERT INTO nu_implantacao(chave, situacao, atribuicao)
                   VALUES ('numeracao:PT_PROTESTO','ABERTA',3)""")
    achados = AP.conferir_a_casa(con, agora=AGORA)
    assert [a for a in achados if a["chave"] == "implantacao"]


def test_a_conferencia_ve_a_manutencao_que_nao_terminou():
    """Ela ja se anotava sozinha em `settings`; o que faltava era alguem
    olhar."""
    con = banco()
    con.execute("""INSERT INTO settings(key, value)
                   VALUES ('manutencao_diaria_erro','2026-08-26 OSError: x')""")
    achados = AP.conferir_a_casa(con, agora=AGORA)
    assert [a for a in achados if a["chave"] == "manutencao"]


def test_a_conferencia_ve_o_banco_com_chave_orfa():
    con = banco()
    achados = AP.conferir_a_casa(
        con, agora=AGORA,
        banco={"integridade": "ok", "orfas": 3, "orfas_detalhe": "pt_atos -> 9"})
    orfas = [a for a in achados if a["chave"] == "orfas"]
    assert orfas and orfas[0]["grave"]


def test_a_casa_em_ordem_nao_inventa_achado():
    """Alarme que soa sempre e alarme que ninguem ouve."""
    con = banco()
    assert AP.conferir_a_casa(con, agora=AGORA, disputas={"total": 0},
                              banco={"integridade": "ok", "orfas": 0}) == []


def test_a_conferencia_ve_a_ajuda_que_nao_respondeu():
    """Um dia em que a internet caiu nao pode parecer um dia normal."""
    con = banco()
    for i in range(3):
        con.execute(
            """INSERT INTO aj_consultas(assunto, pergunta, falha, perguntada_em)
               VALUES ('USO', ?, 'sem internet', ?)""", (f"p{i}", AGORA))
    achados = AP.conferir_a_casa(con, agora=AGORA)
    assert [a for a in achados if a["chave"] == "ajuda_sem_resposta"]


def test_o_que_a_conferencia_achou_entra_na_lista():
    con = banco()
    achados = AP.conferir_a_casa(
        con, agora=AGORA, disputas={"total": 12, "recentes": 7})
    r = AP.anotar_achados(con, achados, agora=AGORA, versao="3.6.15")
    assert r["novos"] == 1
    # De novo no dia seguinte: continua sendo uma linha, com o contador.
    r2 = AP.anotar_achados(con, achados, agora=DEPOIS, versao="3.6.15")
    assert r2["repetidos"] == 1
    assert AP.contagem(con)["total"] == 1


# ---------------------------------------------------------- o relatorio


def test_o_relatorio_sai_sanitizado():
    """Ele NASCE para deixar a serventia: e feito para chegar a outra maquina.

    O que interessa a quem conserta e o ponto do programa, e nunca de quem era
    o CPF que estava sendo gravado quando a tela estourou.
    """
    con = banco()
    AP.anotar(con, origem="ERRO_DE_TELA", titulo="IntegrityError ao gravar",
              detalhe="INSERT ... ('MARIA', '000.000.048-55', '(99) 98472-0370')",
              onde="caixa", agora=AGORA)
    texto = AP.montar_relatorio(problemas=AP.listar(con), agora=AGORA,
                                versao="3.6.15")
    assert "000.000.048-55" not in texto
    assert "[CPF_01]" in texto
    assert "segredos foram substituídos" in texto


def test_o_relatorio_diz_onde_a_tela_MORA():
    """A unica linha do relatorio que existe so para quem programa — e a que
    economiza a meia hora de procurar."""
    con = banco()
    AP.anotar(con, origem="ERRO_DE_TELA", titulo="KeyError", onde="caixa",
              agora=AGORA)
    mapa = {"telas": {"caixa": {"arquivo": "caixa_web.py"}},
            "quantas_telas": 1, "quantas_tabelas": 1, "quantos_arquivos": 1}
    texto = AP.montar_relatorio(problemas=AP.listar(con), agora=AGORA,
                                mapa=mapa, versao="3.6.15")
    assert "caixa_web.py" in texto


def test_o_relatorio_marca_o_que_voltou_depois_do_conserto():
    con = banco()
    r = AP.anotar(con, origem="RELATADO", titulo="o número sai errado",
                  agora=AGORA)
    AP.anotar_relatorio(con, arquivo="x.md", ids=[r["id"]], agora=AGORA)
    AP.anotar(con, origem="RELATADO", titulo="o número sai errado",
              agora=DEPOIS)
    texto = AP.montar_relatorio(problemas=AP.listar(con), agora=DEPOIS)
    assert "voltou a acontecer" in texto


def test_o_relatorio_diz_que_a_leitura_da_ajuda_e_conselho():
    """Mesmo quando lê código, a ajuda não produz laudo nem correção."""
    con = banco()
    AP.anotar(con, origem="RELATADO", titulo="algo", agora=AGORA)
    con.execute("UPDATE aj_problemas SET diagnostico='provavelmente é X'")
    texto = AP.montar_relatorio(problemas=AP.listar(con), agora=AGORA)
    assert "conselho" in texto


def test_o_relatorio_sem_problema_nenhum_diz_isso():
    texto = AP.montar_relatorio(problemas=[], agora=AGORA)
    assert "Nenhum problema aberto" in texto


def test_o_relatorio_diz_quando_cortou():
    """Relatorio que corta em silencio parece cobrir tudo, e nao cobre."""
    con = banco()
    for i in range(AP.LIMITE_DO_RELATORIO + 3):
        AP.anotar(con, origem="RELATADO", titulo=f"defeito número {i} aqui",
                  onde=f"tela_{i}", agora=AGORA)
    texto = AP.montar_relatorio(problemas=AP.listar(con, limite=999),
                                agora=AGORA)
    assert "o resto fica para o próximo" in texto


def test_o_relatorio_fica_em_disco_com_impressao_digital(tmp_path):
    """Ficar em disco e o que salva o dia em que o navegador perde o arquivo."""
    caminho = AP.guardar_relatorio(tmp_path, "# um relatório", agora=AGORA)
    assert caminho.exists()
    assert caminho.parent.name == AP.PASTA_DOS_RELATORIOS
    assert len(AP.digital_do_arquivo(caminho)) == 64
    assert AP.digital_do_arquivo(tmp_path / "nao_existe.md") == ""


# --------------------------------------------- a IA auxilia, nao decide


def test_o_modulo_nao_lavra_nada():
    """Mesmo teste do modulo de fraudes e do da ajuda, e pelo mesmo motivo.

    Ato do delegatario nao se delega a uma ferramenta — e um modulo que fala
    de "problema" e "conserto" e justamente onde alguem se sentiria a vontade
    para acrescentar um "corrigir sozinho".
    """
    proibidas = [n for n in dir(AP) if not n.startswith("_")
                 and any(p in n.lower() for p in
                         ("lavrar", "numerar", "selar", "cobrar", "cancelar",
                          "averbar", "protestar", "decidir", "corrigir",
                          "consertar", "aplicar"))]
    assert proibidas == [], f"os problemas nao consertam nada: {proibidas}"


def test_a_pergunta_do_diagnostico_manda_dizer_quando_nao_da_para_saber():
    """Palpite sobre defeito manda o escrevente mexer onde nao devia."""
    assert "não permite" in AP.PERGUNTA_DO_DIAGNOSTICO
    assert "escrevente faz AGORA" in AP.PERGUNTA_DO_DIAGNOSTICO


def test_diagnostico_le_o_codigo_e_guarda_a_prova(monkeypatch):
    con = banco()
    problema = AP.anotar(
        con, origem="RELATADO", titulo="a Ajuda falhou",
        detalhe="a tela deixou de responder", onde="ajuda_consultar", agora=AGORA,
    )

    class Db:
        def connect(self):
            class Contexto:
                def __enter__(self):
                    return con

                def __exit__(self, *args):
                    return False
            return Contexto()

        transaction = connect

    recebido = {}

    def consultar(*args, **kwargs):
        recebido["contexto"] = kwargs["contexto"]
        recebido["conhecimento"] = kwargs["conhecimento"]
        return {"resposta": "leitura", "consulta_id": 7}

    monkeypatch.setattr(AP.AJ, "consultar", consultar)
    mapa = {"telas": {"ajuda_consultar": {"arquivo": "ajuda_web.py"}}}
    resultado = AP.diagnosticar(
        Db(), problema["id"], pasta_de_dados=".", agora=AGORA,
        papel="ADMIN", mapa=mapa,
    )

    assert "CONFERÊNCIA LOCAL DO CÓDIGO" in recebido["conhecimento"]
    assert "def ajuda_consultar" in recebido["conhecimento"]
    assert "def ajuda_consultar" not in recebido["contexto"]
    assert resultado["codigo"]["arquivo"] == "ajuda_web.py"
    linha = AP.ler(con, problema["id"])
    assert linha["diagnostico_codigo_arquivo"] == "ajuda_web.py"
    assert linha["diagnostico_codigo_linhas"]
    assert len(linha["diagnostico_codigo_sha256"]) == 64


# ------------------------------------------------- as vistas da lista
# RELATO #82, de 17/09/2026 — «organizar problemas concluidos e em aberto.
# Lista apresenta todos problemas já criados e está longa, separar itens
# concluidos dos itens em aberto».
#
# MEDIDO NA PRODUCAO NO DIA: 83 linhas na tabela unica — 65 resolvidas, 17 em
# aberto e 1 com uma palavra que o modulo nao conhece. Quem abria a tela para
# saber o que havia para fazer lia primeiro o que ja estava feito.


def test_o_vocabulario_das_vistas_e_o_que_o_modulo_conhece():
    """Vista que aponta para palavra inexistente filtra por nada — e calada.

    `situacao IN ('RESOLVIDOS')` devolve zero linhas sem erro nenhum, e a tela
    mostraria «nada em aberto» sobre uma casa cheia de problema aberto. E' o
    silencio com cara de medicao, na forma de lista.
    """
    assert set(AP.VISTAS) == {"abertos", "resolvidos", "todos"}
    assert AP.VISTA_PADRAO in AP.VISTAS
    for chave, v in AP.VISTAS.items():
        assert v["rotulo"], f"a vista {chave} sem rotulo nao vira botao"
        for palavra in v["situacoes"]:
            assert palavra in AP.SITUACOES, (
                f"a vista {chave} pede «{palavra}», que o modulo nao conhece")
    assert set(AP.VISTAS[AP.VISTA_EM_ABERTO]["situacoes"]) == {"ABERTO",
                                                              "RELATADO"}


def test_a_vista_escolhida_nao_se_rende_a_palavra_desconhecida():
    """Vista desconhecida nao e erro: um favorito antigo cai na padrao.

    E cai A VISTA — nao a lista. Devolver a tabela inteira para quem pediu uma
    vista que nao existe daria a tela cheia justamente a quem pediu a metade.
    """
    for chave in AP.VISTAS:
        assert AP.vista_escolhida(chave) == chave
    assert AP.vista_escolhida("  RESOLVIDOS ") == "resolvidos"
    assert AP.vista_escolhida("FECHADO") == AP.VISTA_PADRAO
    assert AP.vista_escolhida("") == AP.VISTA_PADRAO
    assert AP.vista_escolhida(None) == AP.VISTA_PADRAO


def test_a_vista_nao_traz_o_que_ela_nao_promete():
    con = banco()
    aberto = AP.anotar(con, origem="RELATADO", titulo="o numero sai errado",
                       onde="caixa", agora=AGORA)
    fechado = AP.anotar(con, origem="RELATADO", titulo="o botao nao faz nada",
                        onde="notas", agora=AGORA)
    AP.fechar(con, fechado["id"], agora=DEPOIS, usuario="JEAN",
              nota="era o cabo da impressora, que foi trocado")

    em_aberto = [p["id"] for p in AP.listar(
        con, situacao=AP.VISTAS["abertos"]["situacoes"])]
    resolvidos = [p["id"] for p in AP.listar(
        con, situacao=AP.VISTAS["resolvidos"]["situacoes"])]
    assert em_aberto == [aberto["id"]]
    assert resolvidos == [fechado["id"]]
    assert len(AP.listar(con)) == 2, "«todos» continua sendo a tabela inteira"


def test_o_resolvido_mais_novo_vem_primeiro():
    """A ordem era `ultima_em` — e num resolvido ela e' a propria abertura.

    Resultado medido antes do relato #82: o que a casa tinha acabado de
    consertar caia no fim da lista, e o que ficou pendurado em agosto aparecia
    no alto. Quem le uma lista de concluidos quer os de agora.
    """
    con = banco()
    velho = AP.anotar(con, origem="RELATADO", titulo="o pendurado em agosto",
                      onde="caixa", agora=AGORA)
    novo = AP.anotar(con, origem="RELATADO", titulo="o consertado agora",
                     onde="notas", agora=AGORA)
    AP.fechar(con, velho["id"], agora=DEPOIS, usuario="JEAN",
              nota="resolvido no fim de agosto, com a nota escrita")
    AP.fechar(con, novo["id"], agora=SETEMBRO, usuario="JEAN",
              nota="resolvido em setembro, com a nota escrita")

    ids = [p["id"] for p in AP.listar(con, situacao="RESOLVIDO")]
    assert ids == [novo["id"], velho["id"]], "o de setembro vem antes do de agosto"


def test_a_linha_com_data_de_fechamento_e_situacao_torta_nao_sobe():
    """A excecao que fez o `CASE WHEN` existir — e' o #77 da producao.

    Numa linha em aberto o `fechado_em` e' NULO, e NULO vai para o fim na ordem
    decrescente — por isso a chave solta parecia certa. A #77 tinha data de
    fechamento SEM estar resolvida, e na vista «Todos» ela subia para o alto do
    grupo do que esta em aberto: na frente do problema que a casa acabou de
    encontrar, e sem nada dizendo por que.

    A chave de um grupo so decide DENTRO dele, e e' isto que se prova: a linha
    torta continua na lista — ela nao se esconde —, mas no lugar dela.
    """
    con = banco()
    torta = AP.anotar(con, origem="RELATADO", titulo="a que veio de fora",
                      onde="antiga", agora=AGORA)
    recem = AP.anotar(con, origem="ERRO_DE_TELA", titulo="KeyError",
                      onde="caixa", agora=SETEMBRO)
    con.execute(
        "UPDATE aj_problemas SET situacao='FECHADO', fechado_em=? WHERE id=?",
        (SETEMBRO, torta["id"]))

    ids = [p["id"] for p in AP.listar(con)]
    assert ids[0] == recem["id"], "a linha torta passou na frente do de agora"
    assert torta["id"] in ids


def test_a_contagem_acompanha_o_filtro():
    """Numero que nao acompanha o proprio filtro e' o carimbo que mente sobre ele.

    Contar a tabela inteira embaixo de um botao que diz «Em aberto» faria quem
    le concluir a coisa errada sobre o proprio filtro — e o numero ao lado do
    botao e' lido como «quantos tem ali dentro».
    """
    con = banco()
    for i in range(3):
        AP.anotar(con, origem="RELATADO", titulo=f"aberto {i}", onde=f"t{i}",
                  agora=AGORA)
    for i in range(2):
        r = AP.anotar(con, origem="RELATADO", titulo=f"fechado {i}",
                      onde=f"f{i}", agora=AGORA)
        AP.fechar(con, r["id"], agora=DEPOIS, usuario="JEAN",
                  nota="consertado, com a explicacao escrita aqui")

    quadro = AP.contagem(con)
    assert quadro["abertos"] == 3
    assert quadro["resolvidos"] == 2
    assert quadro["total"] == 5
    for chave in AP.VISTAS:
        quantos = len(AP.listar(con, situacao=AP.VISTAS[chave]["situacoes"]))
        assert quadro["por_vista"][chave] == quantos, (
            f"o numero do botao «{chave}» nao bate com o que ele mostra")
    assert quadro["por_vista"]["todos"] == quadro["total"]


def test_a_palavra_fora_do_vocabulario_tem_numero_proprio():
    """A linha que nao entra em vista nenhuma precisa de um numero, e nao de sorte.

    Somar as tres palavras conhecidas para dizer «todos» faria a linha torta
    desaparecer justamente da vista que promete nao esconder nada.
    """
    con = banco()
    AP.anotar(con, origem="RELATADO", titulo="aberto de verdade", onde="caixa",
              agora=AGORA)
    torta = AP.anotar(con, origem="RELATADO", titulo="a de fora", onde="antiga",
                      agora=AGORA)
    con.execute("UPDATE aj_problemas SET situacao='FECHADO' WHERE id=?",
                (torta["id"],))

    quadro = AP.contagem(con)
    assert quadro["fora_do_vocabulario"] == 1
    assert quadro["por_vista"]["abertos"] == 1
    assert quadro["por_vista"]["resolvidos"] == 0
    assert quadro["por_vista"]["todos"] == 2
    assert (quadro["por_vista"]["abertos"] + quadro["por_vista"]["resolvidos"]
            < quadro["por_vista"]["todos"]), (
                "se a soma fechasse, a linha de fora estaria numa das duas")


def test_a_janela_da_tela_usa_a_mesma_regua_da_lista():
    """A janela e' do balcao, e nao pode discordar da lista.

    Escrita de dois jeitos — `<> 'RESOLVIDO'` na janela e um grupo na lista —,
    as duas concordavam em quase tudo e discordavam exatamente na palavra fora
    do vocabulario: a janela mostrava como «ainda nao resolvido» o que a lista
    conta como anomalia a arrumar.

    E O QUE A ANOMALIA NAO FAZ E' AFIRMAR: o sistema nao sabe se uma palavra
    desconhecida quer dizer aberto ou fechado, e chutar «aberto» mostraria ao
    balcao um defeito que talvez ja' esteja consertado. Ela espera
    classificacao — com numero proprio, e na vista «Todos».
    """
    con = banco()
    aberto = AP.anotar(con, origem="ERRO_DE_TELA", titulo="KeyError",
                       onde="caixa", agora=AGORA)
    torta = AP.anotar(con, origem="ERRO_DE_TELA", titulo="ValueError",
                      onde="caixa", agora=AGORA)
    con.execute("UPDATE aj_problemas SET situacao='FECHADO' WHERE id=?",
                (torta["id"],))
    assert [p["id"] for p in AP.da_tela(con, "caixa")] == [aberto["id"]]
    assert AP.contagem(con)["fora_do_vocabulario"] == 1, (
        "a palavra torta nao pode sumir: e' o numero dela que manda alguem "
        "classifica-la")

    resolvido = AP.anotar(con, origem="ERRO_DE_TELA", titulo="IndexError",
                          onde="caixa", agora=AGORA)
    AP.fechar(con, resolvido["id"], agora=DEPOIS, usuario="JEAN",
              nota="era o campo que faltava no contexto da tela")
    assert [p["id"] for p in AP.da_tela(con, "caixa")] == [aberto["id"]]


def test_em_aberto_e_a_vista_em_aberto_dizem_o_mesmo():
    """Tres leitores da mesma pergunta: a lista, a janela e o relatorio.

    A do relatorio era um `situacao != 'RESOLVIDO'` escrito na rota, e
    discordava da lista no caso que o relato #82 achou. Relatorio que carrega
    para fora da serventia um problema que a lista ja nao mostra — ou que
    deixa de carregar o que ela mostra — sai assinado errado.
    """
    con = banco()
    a = AP.anotar(con, origem="RELATADO", titulo="aberto", onde="caixa",
                  agora=AGORA)
    torta = AP.anotar(con, origem="RELATADO", titulo="a de fora", onde="antiga",
                      agora=AGORA)
    fechado = AP.anotar(con, origem="RELATADO", titulo="resolvido", onde="notas",
                        agora=AGORA)
    con.execute("UPDATE aj_problemas SET situacao='FECHADO' WHERE id=?",
                (torta["id"],))
    AP.fechar(con, fechado["id"], agora=DEPOIS, usuario="JEAN",
              nota="consertado, com a explicacao escrita aqui")

    da_lista = [p["id"] for p in AP.listar(
        con, situacao=AP.VISTAS[AP.VISTA_EM_ABERTO]["situacoes"])]
    assert [p["id"] for p in AP.em_aberto(con)] == da_lista
    # A TORTA NAO ENTRA EM NENHUM DOS DOIS — e e' assim que eles concordam. O
    # relatorio antigo, com o `!=` escrito na rota, a carregava consigo.
    assert set(da_lista) == {a["id"]}
    assert AP.contagem(con)["fora_do_vocabulario"] == 1


def test_a_conferencia_acusa_a_palavra_fora_do_vocabulario():
    """O #77 nao era so' uma linha estranha: era uma linha que ninguem veria.

    A conferencia mostra, e nao conserta — quem fecha problema e' gente, e a
    linha pode ter sido fechada a mao por um motivo que so' quem a fechou sabe.
    """
    con = banco()
    r = AP.anotar(con, origem="RELATADO", titulo="a de fora", onde="antiga",
                  agora=AGORA)
    con.execute("UPDATE aj_problemas SET situacao='FECHADO' WHERE id=?",
                (r["id"],))

    achados = AP.conferir_a_casa(con, agora=AGORA, disputas={})
    achado = [a for a in achados if a["chave"] == "situacao_fora_do_vocabulario"]
    assert achado, [a["chave"] for a in achados]
    assert "FECHADO" in achado[0]["detalhe"]
    assert "Todos" in achado[0]["detalhe"], (
        "o achado tem de dizer ONDE a linha aparece")
    assert not achado[0]["grave"], (
        "nao e' grave: quem arruma e' gente, na tela, e nao um conserto automatico")


def test_a_conferencia_nao_fala_da_palavra_quando_todas_sao_conhecidas():
    """Achado que sai sempre e' achado que ninguem le."""
    con = banco()
    AP.anotar(con, origem="RELATADO", titulo="aberto", onde="caixa",
              agora=AGORA)
    fechado = AP.anotar(con, origem="RELATADO", titulo="resolvido", onde="notas",
                        agora=AGORA)
    AP.fechar(con, fechado["id"], agora=DEPOIS, usuario="JEAN",
              nota="consertado, com a explicacao escrita aqui")

    achados = AP.conferir_a_casa(con, agora=AGORA, disputas={})
    assert not [a for a in achados
                if a["chave"] == "situacao_fora_do_vocabulario"]


# ------------------------------------------- quem fecha diz o que fez


def test_fechar_sem_a_linha_de_explicacao_e_recusado():
    """MEDIDO EM 17/09/2026, quando a exigencia nasceu: das 65 linhas
    resolvidas, 58 nao tinham uma linha de explicacao — e 27 delas foram
    fechadas numa tarde so'. A lista dizia «resolvido» e nao dizia o que.

    A RECUSA DERRUBA O FECHAMENTO INTEIRO. Gravar «RESOLVIDO» e reclamar
    depois deixaria a linha fechada sem explicacao — que e' exatamente o
    estado que a exigencia existe para nao produzir de novo.
    """
    con = banco()
    r = AP.anotar(con, origem="RELATADO", titulo="algo", onde="caixa",
                  agora=AGORA)
    for nota in (None, "", "   ", "ok", "feito"):
        with pytest.raises(AP.ProblemaError, match=f"#{r['id']}"):
            AP.fechar(con, r["id"], agora=DEPOIS, usuario="JEAN", nota=nota)
        assert AP.ler(con, r["id"])["situacao"] == "ABERTO", (
            "a recusa nao pode fechar o que ela recusou")

    with pytest.raises(AP.ProblemaError) as recusa:
        AP.fechar(con, r["id"], agora=DEPOIS)
    assert "dez letras" in str(recusa.value), (
        "a mensagem tem de dizer o tamanho que falta")


def test_a_nota_escrita_depois_nao_regrava_quem_fechou_nem_quando():
    """As 58 linhas sem explicacao so' ganham a delas passando por aqui de novo.

    Sem o cuidado com quem ja' tem data, esse ato — o de ESCREVER o que
    faltava — carimbava data e nome novos sobre um fechamento de agosto, e a
    lista dos resolvidos, que desde o relato #82 se ordena por essa data,
    subiria para o alto as linhas mais antigas como se tivessem acabado de ser
    resolvidas. A nota e' o que se escreve agora; a data e o nome sao fato do
    passado, e fato do passado nao se regrava.
    """
    con = banco()
    r = AP.anotar(con, origem="RELATADO", titulo="algo", onde="caixa",
                  agora=AGORA)
    AP.fechar(con, r["id"], agora=AGORA, usuario="QUEM FECHOU NA PRENSA",
              nota="fechado na correria, sem explicar nada de util")
    AP.fechar(con, r["id"], agora=SETEMBRO, usuario="OUTRO",
              nota="explicacao escrita meses depois, ao revisar a lista")

    linha = AP.ler(con, r["id"])
    assert linha["fechado_em"] == AGORA
    assert linha["fechado_por"] == "QUEM FECHOU NA PRENSA"
    assert "explicacao escrita meses depois" in linha["fechado_nota"]


def test_rotulo_curto_dev_cabe_numa_linha_na_lista():
    """O substatus na coluna Situação usa rótulo curto e layout em pilha."""
    for chave, rotulo in AP.ROTULO_CURTO_DEV.items():
        assert chave in AP.ESTADOS_DO_DEV
        assert "\n" not in rotulo
        assert len(rotulo) <= 22, f"{chave!r} longo demais para a coluna: {rotulo!r}"
    fonte = (RAIZ / "templates" / "ajuda_problemas.html").read_text(encoding="utf-8")
    assert "problema-situacao-badges" in fonte
    assert 'class="badge dev-sub dev-' in fonte
    assert "<br><span class=\"badge dev-" not in fonte
