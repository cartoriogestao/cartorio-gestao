"""
Testes do AGENTE — o esquema, as ferramentas e o laço.

POR QUE ELES VEM DEPOIS DA TELA, E NAO ANTES
    A tela e o dominio sao duas provas, e as duas sao necessarias. A tela
    (`test_agente_web.py`) prova que o oficial chega nele. Aqui se prova o que
    ele faz quando chega — e o que ele **nao** faz, que neste modulo importa
    mais: um agente com permissao de mexer no sistema precisa de teste que
    mostre o que ele recusa.

O QUE ELES CONFEREM

  O esquema
      - as quatro tabelas nascem, e abrir o banco de novo nao duplica nada;
      - a escrita NASCE DESLIGADA, e o teto digitado e preso no limite duro.

  As ferramentas
      - ferramenta de escrita desligada **nao e oferecida** — nem como opcao
        recusavel;
      - e, se pedida mesmo assim, RECUSA em vez de escrever;
      - **a mascara vale para o que a ferramenta devolve**: um CPF que esteja
        no banco nao sai daqui;
      - o banco so se le: escrita, ponto e virgula, comentario, nome de
        credencial, `ag_config` e `SELECT *` sao recusados;
      - o codigo so se le de dentro da pasta do sistema.

  O laço
      - sem chave e sem pedido **nao abre sessao**: a recusa vem antes, para a
        lista nao encher de sessao que nunca falou — e o pedido COM dado de
        pessoa entra mascarado, porque recusar o que a barreira sabe mascarar
        seria ensinar o oficial a escrever em codigo;
      - a sessao que ficou ABERTA porque o programa parou no meio vira
        INTERROMPIDA na abertura do banco, e e isso que a torna continuavel;
      - o turno com ferramenta executa, grava o pedido, grava o resultado e
        devolve o resultado ao modelo no turno seguinte;
      - o teto de turnos para o laço, DEIXANDO O AVISO na sessao;
      - falha de provedor vira ESTADO, e nao excecao: o que ja foi apurado
        fica gravado;
      - a sessao interrompida no meio (pedido de ferramenta sem resultado)
        retoma — e o pedido orfao recebe a resposta de interrupcao, que e o
        que faz o provedor aceitar a conversa de volta;
      - o gasto SOMA entre as rodadas: a tela nao pode dizer um preco que
        ninguem pagou;

  O desfazer
      - volta o alcance de um modulo, e recusa o que nao sabe voltar.
"""
from __future__ import annotations

import glob
import json
import sqlite3
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.lento  # gate rapido: pytest -m "not lento" — pesado + DROP/memory
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import agente as AGT                            # noqa: E402
import agente_ferramentas as FER                # noqa: E402
import agente_provedores as PROV                # noqa: E402
import agente_schema as AGS                     # noqa: E402
import ajuda_privacidade as PRIV                # noqa: E402
import ajuda_problemas as AP                    # noqa: E402
import modulos_ligados as ML                    # noqa: E402

HORA = "2026-09-14T10:00:00"
HOJE = "2026-09-14"
CPF = "000.000.048-55"


# =================================================================== a casa


@pytest.fixture(scope="module")
def casa(tmp_path_factory):
    """Um app de verdade, com banco de verdade, uma vez só para o arquivo.

    **DE VERDADE, E NAO UM BANCO DE MENTIRA**: as ferramentas leem o esquema
    desta instalação, e um dublê provaria que a ferramenta chama o dublê. O
    que este arquivo tem de mentira é só o provedor — que é a rede.
    """
    from app import create_app
    from database import Database

    dados = tmp_path_factory.mktemp("agente") / "dados"
    dados.mkdir()
    app = create_app({"DATA_DIR": str(dados)})
    banco = Path(glob.glob(f"{dados}/*.sqlite3")[0])
    db = Database(banco)
    db.create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS", "Senha#12345",
                   "ADMIN")
    return {"app": app, "db": db, "banco": banco, "dados": dados}


def _ctx(casa, sessao_id: int = 1) -> FER.Contexto:
    return FER.Contexto(db=casa["db"], raiz=RAIZ,
                        pasta_de_dados=casa["dados"], agora=HORA,
                        usuario="MARIO EXEMPLO DOS SANTOS", sessao_id=sessao_id,
                        versao="3.6.126", app=casa["app"])


def _cris(casa, chave: str, valor) -> None:
    """Grava uma configuração do agente na mão. **ESCREVE.**"""
    with casa["db"].transaction() as con:
        AGS.gravar_config(con, chave, valor)


def _chave(casa, provedor: str = "deepseek",
           valor: str = "sk-teste-do-agente") -> None:
    PROV.gravar_chave(casa["dados"], provedor, valor)


def _con(casa) -> sqlite3.Connection:
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _sessoes(casa) -> int:
    con = _con(casa)
    total = con.execute("SELECT COUNT(*) c FROM ag_sessoes").fetchone()["c"]
    con.close()
    return total


# ------------------------------------------------------- o provedor de mentira


def _fala(texto: str = "O QUE EU VI: nada quebrado.", *, chamadas=None,
          entrada: int = 100, saida: int = 20) -> dict:
    return {"texto": texto, "modelo": "deepseek-chat", "entrada": entrada,
            "saida": saida, "chamadas": chamadas or []}


def _pedido_ferramenta(nome: str, argumentos: dict | None = None,
                       id_: str = "c1") -> dict:
    return {"id": id_, "nome": nome, "argumentos": argumentos or {}}


def _roteiro(*respostas: dict):
    """Um `conversar` de mentira: segue o roteiro e guarda o que recebeu.

    O QUE ELE GUARDA E O QUE IMPORTA: a conversa que o laço mandou em cada
    turno. É por ali que se prova que o resultado da ferramenta VOLTOU para o
    modelo, e que a máscara foi aplicada antes de sair.
    """
    recebido: list[dict] = []
    fila = list(respostas)

    def falso(pasta, *, provedor, sistema, conversa, ferramentas, modelo,
              maximo_de_saida, prazo):
        recebido.append({"sistema": sistema, "conversa": conversa,
                         "ferramentas": ferramentas, "provedor": provedor,
                         "modelo": modelo})
        if not fila:
            raise AssertionError(
                "o laço continuou depois de o roteiro acabar — quem parou "
                "foi o provedor de mentira, e não o agente")
        return fila.pop(0)

    falso.recebido = recebido
    return falso


def _pedir(casa, monkeypatch, *respostas, pedido="confira o selo"):
    _chave(casa)
    falso = _roteiro(*respostas)
    monkeypatch.setattr(PROV, "conversar", falso)
    retrato = AGT.pedir(casa["db"], pedido=pedido,
                        pasta_de_dados=casa["dados"], raiz=RAIZ, agora=HORA,
                        usuario="MARIO EXEMPLO DOS SANTOS", versao="3.6.126",
                        app=casa["app"])
    return retrato, falso


# ================================================================= o esquema


def test_as_quatro_tabelas_nascem_e_abrir_de_novo_nao_duplica():
    """Atualizar o programa não pode exigir recriar nem apagar o histórico."""
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    AGS.init_agente_schema(con)
    tabelas = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"ag_sessoes", "ag_passos", "ag_mudancas", "ag_config"} <= tabelas
    colunas = {r[1] for r in con.execute("PRAGMA table_info(ag_passos)")}
    assert {"chamada_id", "tipo", "ferramenta", "argumentos"} <= colunas
    # Idempotência: abrir o mesmo banco outra vez não estoura nem apaga nada.
    AGS.init_agente_schema(con)
    con.execute("INSERT INTO ag_sessoes(titulo, pedido, provedor, modelo, "
                "estado, criada_em) VALUES ('x', 'y', 'deepseek', 'm', 'ABERTA', ?)",
                (HORA,))
    AGS.init_agente_schema(con)
    assert con.execute("SELECT COUNT(*) c FROM ag_sessoes").fetchone()["c"] == 1
    con.close()


def test_a_escrita_nasce_desligada(casa):
    con = _con(casa)
    assert AGS.escrita_ligada(con) is False
    con.close()


def test_o_teto_digitado_e_preso_no_limite(casa):
    """O número que a tela guarda não pode ser maior que o freio da casa."""
    con = _con(casa)
    AGS.gravar_config(con, AGS.CHAVE_TETO_TURNOS, 900)
    AGS.gravar_config(con, AGS.CHAVE_TETO_SESSOES, 9000)
    assert AGS.teto_de_turnos(con) == AGS.TETO_MAXIMO_DE_TURNOS
    assert AGS.teto_de_sessoes(con) == AGS.TETO_MAXIMO_DE_SESSOES
    # e o que não é número não vira zero calado: cai no padrão da casa
    AGS.gravar_config(con, AGS.CHAVE_TETO_TURNOS, "muitos")
    assert AGS.teto_de_turnos(con) == int(AGS.PADROES[AGS.CHAVE_TETO_TURNOS])
    con.commit()
    con.close()


def test_os_passos_saem_na_ordem_em_que_aconteceram(casa):
    con = _con(casa)
    AGS.init_agente_schema(con)
    sessao = AGS.abrir_sessao(con, titulo="ordem", pedido="ordem",
                              provedor="deepseek", modelo="m", agora=HORA,
                              criada_por="MARIO")
    for ordem, texto in ((2, "segundo"), (1, "primeiro"), (3, "terceiro")):
        AGS.registrar_passo(con, sessao, ordem=ordem, tipo=AGS.TEXTO,
                            conteudo=texto, agora=HORA)
    lidos = [p["conteudo"] for p in AGS.passos_da_sessao(con, sessao)]
    con.commit()
    con.close()
    assert lidos == ["primeiro", "segundo", "terceiro"]


def test_a_contagem_do_dia_conta_pelo_dia_em_que_se_pediu(casa):
    """O freio é sobre quanto se PEDE ao provedor — sessão antiga reaberta não
    é pedido novo, e por isso a conta é por `criada_em`."""
    con = _con(casa)
    AGS.init_agente_schema(con)
    antes = AGS.contagem_do_dia(con, desde=HOJE)
    AGS.abrir_sessao(con, titulo="hoje", pedido="hoje", provedor="deepseek",
                     modelo="m", agora=f"{HOJE}T11:00:00", criada_por="MARIO")
    AGS.abrir_sessao(con, titulo="ontem", pedido="ontem", provedor="deepseek",
                     modelo="m", agora="2026-09-13T11:00:00", criada_por="MARIO")
    agora = AGS.contagem_do_dia(con, desde=HOJE)
    con.commit()
    con.close()
    assert agora["sessoes"] == antes["sessoes"] + 1


# ============================================================= as ferramentas


def test_a_ferramenta_de_escrita_nao_e_oferecida_com_a_escrita_desligada():
    """**Oferecer e recusar depois ensinaria o modelo a pedir o que não pode**,
    e gastaria um turno por tentativa."""
    assert not [f for f in FER.catalogo(escrita=False) if f.e_escrita]
    assert [f for f in FER.catalogo(escrita=True) if f.e_escrita]
    # e as de leitura vão nos dois casos
    so_leitura = {f.nome for f in FER.catalogo(escrita=False)}
    assert "estado_do_sistema" in so_leitura
    assert "definir_alcance_do_modulo" not in so_leitura


def test_a_escrita_desligada_recusa_em_vez_de_escrever(casa):
    """Se o modelo pedir mesmo assim — de memória, ou por um turno antigo —, a
    recusa é dele, e não uma escrita que passou."""
    _cris(casa, AGS.CHAVE_ESCRITA, "")
    chave_do_modulo = sorted(ML.CHAVE_DA_CONFIGURACAO)[0]
    antes = casa["db"].get_setting(ML.CHAVE_DA_CONFIGURACAO[chave_do_modulo], "")
    r = FER.executar(_ctx(casa), "definir_alcance_do_modulo",
                     {"modulo": chave_do_modulo, "alcance": ML.ALCANCES[-1]})
    assert r["erro"] is True
    assert "desligad" in r["conteudo"]
    assert casa["db"].get_setting(
        ML.CHAVE_DA_CONFIGURACAO[chave_do_modulo], "") == antes


def test_a_mascara_vale_para_o_que_a_ferramenta_devolve(casa):
    """**A BARREIRA NÃO É SÓ DA PERGUNTA.** O agente lê o banco; sem esta
    máscara, o conteúdo do balcão sairia numa consulta que ninguém pediu."""
    with casa["db"].transaction() as con:
        problema = AP.anotar(con, origem="RELATADO",
                             titulo="certidão com o CPF errado",
                             detalhe=f"o CPF {CPF} não bate com o cadastro",
                             onde="rcpn_certidoes", caminho="/rcpn",
                             versao="3.6.126", usuario="MARIO", agora=HORA)
    r = FER.executar(_ctx(casa), "ler_problema",
                     {"problema_id": problema["id"]})
    assert r["erro"] is False
    assert CPF not in r["conteudo"], "o CPF saiu inteiro na leitura"
    assert "[CPF_01]" in r["conteudo"]
    # e a mesma coisa pela consulta ao banco
    r = FER.executar(_ctx(casa), "consultar_banco",
                     {"consulta": "SELECT detalhe FROM aj_problemas"})
    assert CPF not in r["conteudo"]


def test_o_banco_so_se_le(casa):
    for consulta in ("DELETE FROM aj_config",
                     "DROP TABLE aj_problemas",
                     "UPDATE aj_sessoes SET estado = 'X'"):
        r = FER.executar(_ctx(casa), "consultar_banco", {"consulta": consulta})
        assert r["erro"] is True, consulta
        assert "SELECT" in r["conteudo"]


def test_a_segunda_instrucao_escondida_e_recusada(casa):
    """O ponto e vírgula e o comentário são por onde passa o que ninguém
    revisou."""
    r = FER.executar(_ctx(casa), "consultar_banco",
                     {"consulta": "SELECT chave FROM aj_config; DROP TABLE x"})
    assert r["erro"] is True
    r = FER.executar(_ctx(casa), "consultar_banco",
                     {"consulta": "SELECT chave FROM aj_config -- e isto"})
    assert r["erro"] is True
    assert "comentário" in r["conteudo"]


def test_a_tabela_de_chaves_do_agente_nao_se_le(casa):
    """`ag_config` guarda chave de API em texto claro, e a barreira de
    privacidade não reconhece chave de API — esta recusa é o que a cobre."""
    r = FER.executar(_ctx(casa), "consultar_banco",
                     {"consulta": "SELECT chave, valor FROM ag_config"})
    assert r["erro"] is True
    assert "chave de API" in r["conteudo"]


def test_o_select_estrela_e_recusado(casa):
    """`SELECT *` traz coluna que ninguém pediu — e é assim que um campo que
    não podia sair sai."""
    r = FER.executar(_ctx(casa), "consultar_banco",
                     {"consulta": "SELECT * FROM users"})
    assert r["erro"] is True
    assert "colunas" in r["conteudo"]


def test_o_nome_de_credencial_e_recusado(casa):
    r = FER.executar(_ctx(casa), "consultar_banco",
                     {"consulta": "SELECT password FROM users"})
    assert r["erro"] is True
    assert "credencial" in r["conteudo"]


def test_o_codigo_so_se_le_de_dentro_da_casa(casa):
    """Sair da pasta do sistema é o caminho por onde o agente leria a máquina
    inteira — e ele não tem a menor necessidade disso."""
    for caminho in ("../../../Windows/win.ini", "C:/Windows/win.ini",
                    "/etc/passwd", "tests/test_agente.py"):
        r = FER.executar(_ctx(casa), "ler_codigo", {"caminho": caminho})
        assert r["erro"] is True, caminho


def test_ler_codigo_devolve_o_trecho_com_a_linha(casa):
    r = FER.executar(_ctx(casa), "ler_codigo",
                     {"caminho": "app.py", "linha": 51})
    assert r["erro"] is False
    assert "VERSION" in r["conteudo"]


def test_a_ferramenta_que_nao_existe_e_recusada_pelo_nome(casa):
    r = FER.executar(_ctx(casa), "apagar_o_sistema", {})
    assert r["erro"] is True
    assert "Não existe ferramenta" in r["conteudo"]


# ================================================================ o desfazer


def test_desfazer_recusa_o_que_nao_sabe_voltar(casa):
    """**Uma volta que não volta é pior que um botão que não existe** — ela dá
    a quem clica a impressão de ter consertado."""
    con = _con(casa)
    AGS.init_agente_schema(con)
    sessao = AGS.abrir_sessao(con, titulo="d", pedido="d", provedor="deepseek",
                              modelo="m", agora=HORA, criada_por="MARIO")
    mudanca = AGS.registrar_mudanca(
        con, sessao, ferramenta="anotar_no_problema", alvo="problema 7",
        antes="sem nota", depois="com nota", agora=HORA, criada_por="MARIO")
    con.commit()
    con.close()
    with pytest.raises(FER.FerramentaError) as recusa:
        AGT.desfazer(casa["db"], mudanca, agora=HORA, usuario="MARIO")
    assert "não sei voltar" in str(recusa.value)


def test_desfazer_volta_o_alcance_de_um_modulo(casa):
    """É este clique que faz a permissão de escrever ser defensável."""
    _cris(casa, AGS.CHAVE_ESCRITA, "1")
    chave = sorted(ML.CHAVE_DA_CONFIGURACAO)[0]
    nome_na_config = ML.CHAVE_DA_CONFIGURACAO[chave]
    de_fabrica = ML.ALCANCE_DE_FABRICA.get(chave, ML.TODOS)
    outro = [a for a in ML.ALCANCES if a != de_fabrica][0]

    con = _con(casa)
    sessao = AGS.abrir_sessao(con, titulo="entende", pedido="e",
                              provedor="deepseek", modelo="m", agora=HORA,
                              criada_por="MARIO")
    con.commit()
    con.close()

    r = FER.executar(_ctx(casa, sessao), "definir_alcance_do_modulo",
                     {"modulo": chave, "alcance": outro})
    assert r["erro"] is False
    assert casa["db"].get_setting(nome_na_config, "") == outro

    con = _con(casa)
    mudanca = con.execute(
        "SELECT id FROM ag_mudancas WHERE sessao_id = ?", (sessao,)).fetchone()
    con.close()
    assert mudanca is not None, "a mudança não foi registrada"

    voltou = AGT.desfazer(casa["db"], mudanca["id"], agora=HORA, usuario="MARIO")
    assert voltou["voltei_para"] == de_fabrica
    assert casa["db"].get_setting(nome_na_config, de_fabrica) == de_fabrica

    # E DESFAZER DUAS VEZES RECUSA: o registro diz que já voltou.
    with pytest.raises(FER.FerramentaError):
        AGT.desfazer(casa["db"], mudanca["id"], agora=HORA, usuario="MARIO")
    _cris(casa, AGS.CHAVE_ESCRITA, "")


# =================================================================== o laço


def test_pedido_vazio_e_recusado_sem_abrir_sessao(casa):
    antes = _sessoes(casa)
    with pytest.raises(AGT.AgenteRecusado) as recusa:
        AGT.pedir(casa["db"], pedido="   ", pasta_de_dados=casa["dados"],
                  raiz=RAIZ, agora=HORA, usuario="MARIO")
    assert "pedido vazio" in str(recusa.value)
    assert _sessoes(casa) == antes


def test_sem_chave_o_agente_recusa_antes_de_abrir_sessao(casa, monkeypatch):
    """Sessão que já nasce recusada é linha na lista que nunca falou com
    ninguém — e o oficial acharia que pediu algo."""
    antes = _sessoes(casa)
    PROV.gravar_chave(casa["dados"], "deepseek", "")
    with pytest.raises(AGT.AgenteRecusado) as recusa:
        AGT.pedir(casa["db"], pedido="confira o selo",
                  pasta_de_dados=casa["dados"], raiz=RAIZ, agora=HORA,
                  usuario="MARIO")
    assert "Não há chave do DeepSeek" in str(recusa.value)
    assert _sessoes(casa) == antes


def test_o_pedido_com_dado_de_pessoa_vira_mascara_antes_de_sair(casa,
                                                                monkeypatch):
    """**A BARREIRA VALE NA PORTA DE ENTRADA.** O pedido do oficial é mascarado
    antes de virar sessão: o CPF que ele colou não é gravado nem sai daqui.

    Aqui o certo é MASCARAR, e não recusar — recusar é o que a barreira faz
    quando sobra resíduo que ela não sabe tirar. Recusar o que ela sabe mascarar
    ensinaria o oficial a escrever em código, e o número voltaria por outro
    caminho."""
    retrato, falso = _pedir(
        casa, monkeypatch,
        _fala("O QUE EU VI: o cadastro está com o número trocado."),
        pedido=f"confira o CPF {CPF} no cadastro")
    gravado = [p for p in retrato["passos"] if p["tipo"] == AGS.PEDIDO][0]
    assert CPF not in gravado["conteudo"], "o CPF ficou gravado na sessão"
    assert "[CPF_01]" in gravado["conteudo"]
    # e o que saiu para o provedor é o texto mascarado, e não o original
    perguntas = [e["texto"] for e in falso.recebido[0]["conversa"]
                 if e["tipo"] == "user"]
    assert perguntas, "o pedido não chegou ao provedor"
    assert all(CPF not in t for t in perguntas)


def test_a_barreira_de_privacidade_confere_sozinha(casa):
    """A máscara é a de sempre — e o teste é da barreira, não minha."""
    seguro = PRIV.sanitizar_para_modelo(f"o CPF {CPF} não passa na conferência")
    assert CPF not in seguro
    assert "[CPF_01]" in seguro


def test_o_laco_executa_a_ferramenta_e_devolve_o_resultado_ao_modelo(casa,
                                                                    monkeypatch):
    retrato, falso = _pedir(
        casa, monkeypatch,
        _fala(chamadas=[_pedido_ferramenta("estado_do_sistema", id_="c1")]),
        _fala("O QUE EU VI: nada anotado.\nO QUE FALTA: nada."))

    sessao = retrato["sessao"]
    assert sessao["estado"] == AGS.CONCLUIDA
    assert sessao["turnos"] == 2
    assert sessao["tokens_de_entrada"] == 200
    assert sessao["tokens_de_saida"] == 40

    tipos = [p["tipo"] for p in retrato["passos"]]
    assert tipos[0] == AGS.PEDIDO
    assert AGS.FERRAMENTA in tipos and AGS.RESULTADO in tipos
    assert tipos[-1] == AGS.TEXTO

    # 1) A FERRAMENTA FOI OFERECIDA, e sem as de escrita
    assert "estado_do_sistema" in {f["nome"] for f in falso.recebido[0]["ferramentas"]}
    assert "definir_alcance_do_modulo" not in {
        f["nome"] for f in falso.recebido[0]["ferramentas"]}

    # 2) O RESULTADO VOLTOU PARA O MODELO no turno seguinte — é isto que faz o
    #    agente saber o que leu em vez de adivinhar
    segunda = falso.recebido[1]["conversa"]
    blocos = [e for e in segunda if e["tipo"] == "tool"]
    assert blocos, "o resultado da ferramenta não voltou ao provedor"
    assert blocos[0]["resultados"][0]["id"] == "c1"
    assert blocos[0]["resultados"][0]["nome"] == "estado_do_sistema"
    assert blocos[0]["resultados"][0]["conteudo"].strip(), "resultado vazio"

    # 3) E O QUE O MODELO RECEBEU É O QUE A TELA MOSTRA: o conteúdo do passo
    #    gravado é o mesmo que foi ao provedor
    gravado = [p for p in retrato["passos"] if p["tipo"] == AGS.RESULTADO][0]
    assert gravado["conteudo"] == blocos[0]["resultados"][0]["conteudo"]


def test_o_laco_para_no_teto_de_turnos_e_deixa_o_aviso(casa, monkeypatch):
    """Teto não é erro: é parada com o trabalho feito. O aviso é o que faz
    quem olha a tela saber que pode continuar escrevendo.

    **E O FECHO CUSTA UM TURNO A MAIS, que é o preço de ter a resposta.** Desde
    18/09/2026 (problema #68), ao bater o teto a rodada pede o resumo do que já
    apurou antes de parar: é uma chamada ao modelo a mais, real e paga. O que não
    pode acontecer — e é o que as quatro linhas de baixo guardam — é a rodada
    seguir TRABALHANDO: o fecho vai sem catálogo, e a ferramenta que ele pedir
    nele não roda.
    """
    _cris(casa, AGS.CHAVE_TETO_TURNOS, 2)
    retrato, falso = _pedir(
        casa, monkeypatch,
        *[_fala(chamadas=[_pedido_ferramenta("estado_do_sistema",
                                             id_=f"c{i}")]) for i in range(1, 4)])
    sessao = retrato["sessao"]
    assert sessao["estado"] == AGS.LIMITE
    assert sessao["turnos"] == 3, "o fecho não foi pedido"
    assert len(falso.recebido) == 3
    assert falso.recebido[0]["ferramentas"] and falso.recebido[1]["ferramentas"]
    assert falso.recebido[2]["ferramentas"] == [], \
        "o turno de fecho levou o catálogo, e o modelo leria mais uma vez"
    assert "Nenhuma ferramenta está disponível" in falso.recebido[2]["sistema"]
    resultados = [p for p in retrato["passos"] if p["tipo"] == AGS.RESULTADO]
    assert len(resultados) == 2, "a rodada trabalhou depois do teto"
    avisos = [p["conteudo"] for p in retrato["passos"] if p["tipo"] == AGS.AVISO]
    assert any("teto de 2 turnos" in a for a in avisos), avisos
    # e o conselho do que fazer está no aviso: continue a conversa
    assert any("escreva de novo" in a for a in avisos)
    _cris(casa, AGS.CHAVE_TETO_TURNOS,
          AGS.PADROES[AGS.CHAVE_TETO_TURNOS])


def test_o_resumo_obedecido_ainda_fecha_no_limite(casa, monkeypatch):
    """O caso BOM do fecho: o modelo obedece, não pede ferramenta e escreve o
    resumo — e mesmo assim a sessão PAROU NO TETO, e não terminou.

    **É A ORDEM DAS PARADAS DO LAÇO, E ELA NÃO É DETALHE.** Sem o `forcado`
    conferido ANTES do «acabou», este mesmo turno fecharia a sessão como
    CONCLUIDA: o recado da tela diria «terminou» sobre um trabalho interrompido,
    e quem lê pararia de continuar. **Carimbo que mente é pior que carimbo
    nenhum**, e este mentiria sobre o motivo de a rodada ter acabado.
    """
    _cris(casa, AGS.CHAVE_TETO_TURNOS, 1)
    retrato, _ = _pedir(
        casa, monkeypatch,
        _fala(chamadas=[_pedido_ferramenta("estado_do_sistema", id_="c1")]),
        _fala("O QUE EU VI: nada quebrado.\nO QUE FALTA: o resto do laudo."))
    sessao = retrato["sessao"]
    assert sessao["estado"] == AGS.LIMITE
    # E O «POR QUE PAROU» DIZ QUAL DOS DOIS TETOS — é a pergunta do #68.
    assert "teto de turnos" in sessao["erro"], sessao["erro"]
    assert "O agente parou no teto" in retrato["recado"]["texto"]
    assert "teto de turnos" in retrato["recado"]["texto"]
    assert retrato["recado"]["tom"] == "warning"
    textos = [p["conteudo"] for p in retrato["passos"] if p["tipo"] == AGS.TEXTO]
    assert any("O QUE FALTA: o resto do laudo" in t for t in textos), textos
    _cris(casa, AGS.CHAVE_TETO_TURNOS,
          AGS.PADROES[AGS.CHAVE_TETO_TURNOS])


def test_o_teto_de_tokens_e_da_sessao_e_nao_da_rodada(casa, monkeypatch):
    """O #68, com o teto baixado para caber num teste.

    A sessão 1 desta instalação gastou **1.395.475 tokens de entrada + 24.946 de
    saída = 1.420.421** — 3,55 vezes o teto — porque a conferência era contra o
    contador DESTA RODADA, que nasce em zero a cada fala nova do oficial. Aqui o
    teto são 300 tokens: a primeira rodada gasta 540 e termina; a segunda não
    pode mais trabalhar, e para pedindo o resumo.

    **O TETO NÃO É FATURA, É PONTO DE PARADA:** uma rodada pode ultrapassá-lo
    (foi o que a primeira fez), e o que ele garante é que a SEGUINTE não comece a
    trabalhar — nem que seja recomeçando a contagem.
    """
    monkeypatch.setattr(AGT, "TETO_DE_TOKENS", 300)
    retrato, _ = _pedir(
        casa, monkeypatch,
        _fala(chamadas=[_pedido_ferramenta("estado_do_sistema", id_="c1")],
              entrada=250, saida=20),
        _fala("O QUE EU VI: nada.", entrada=250, saida=20))
    assert retrato["sessao"]["estado"] == AGS.CONCLUIDA
    assert retrato["sessao"]["tokens_de_entrada"] == 500

    falso = _roteiro(_fala("O QUE EU VI: o que deu para ver até aqui."))
    monkeypatch.setattr(PROV, "conversar", falso)
    retrato = AGT.responder(casa["db"], retrato["sessao"]["id"],
                            pedido="e agora?", pasta_de_dados=casa["dados"],
                            raiz=RAIZ, agora=HORA, usuario="MARIO",
                            app=casa["app"])
    sessao = retrato["sessao"]
    assert sessao["estado"] == AGS.LIMITE
    # UMA chamada só, e ela é o fecho: a rodada nova não voltou a trabalhar
    assert len(falso.recebido) == 1, "a rodada nova recomeçou a contagem"
    assert falso.recebido[0]["ferramentas"] == []
    avisos = [p["conteudo"] for p in retrato["passos"] if p["tipo"] == AGS.AVISO]
    assert any("540 até aqui" in a for a in avisos), avisos
    # e o gasto continua sendo o DA SESSÃO, somadas as duas rodadas
    assert sessao["tokens_de_entrada"] == 600
    assert sessao["tokens_de_saida"] == 60


def test_o_que_ja_foi_lido_nao_volta_inteiro_a_cada_turno(casa, monkeypatch):
    """A segunda metade do #68: a conversa INTEIRA vai ao provedor a cada turno,
    e nada a podava.

    Medido na sessão 1 desta instalação, com
    `tools/medir_o_peso_da_conversa.py`: 107 passos, **240.095 caracteres** entre
    o que ela leu e o que escreveu, reenviados nos **32 pontos de chamada** — os
    mesmos caracteres comprados **dezoito vezes**, **4.420.607** no total. Foi
    assim que 240 mil caracteres de conversa viraram 1.395.475 tokens de entrada,
    e a poda derruba essa soma a 1.669.358 (62,2 % menos).

    **A PODA NÃO APAGA O QUE ELE LEU.** O que sai é o que VOLTA ao modelo:
    `ag_passos` e a tela continuam com o texto inteiro. Os últimos resultados vão
    inteiros, porque é neles que ele está trabalhando; os antigos e grandes viram
    uma linha com o nome da ferramenta e o tamanho — e ele pode chamá-la de novo.
    """
    grande = "R" * (AGT.PISO_DE_RESULTADO_INTEIRO + 500)
    passos: list[dict] = [{"tipo": AGS.PEDIDO, "conteudo": "leia tudo",
                           "ferramenta": None, "chamada_id": None,
                           "argumentos": None, "erro": None}]
    for i in range(1, 9):
        passos.append({"tipo": AGS.FERRAMENTA, "conteudo": "", "erro": None,
                       "ferramenta": "ler_documentacao", "chamada_id": f"c{i}",
                       "argumentos": "{}"})
        passos.append({"tipo": AGS.RESULTADO, "conteudo": f"{grande}{i}",
                       "ferramenta": "ler_documentacao", "chamada_id": f"c{i}",
                       "argumentos": None, "erro": 0})

    conversa = AGT._conversa([], passos)
    # A TRADUÇÃO É FIEL — e a tela desenha esta: nenhum resultado vem resumido
    # daqui. Podar dentro do `_conversa` mostraria ao oficial um resumo onde o
    # texto inteiro está guardado, e a tela passaria a mentir sobre o que o
    # agente leu.
    assert all(len(e["resultados"][0]["conteudo"]) > AGT.PISO_DE_RESULTADO_INTEIRO
               for e in conversa if e["tipo"] == "tool")

    blocos = [e for e in AGT._poupar(conversa) if e["tipo"] == "tool"]
    assert len(blocos) == 8
    resumidos = [b for b in blocos
                 if "resumido para o orçamento" in b["resultados"][0]["conteudo"]]
    inteiros = [b for b in blocos
                if len(b["resultados"][0]["conteudo"]) > AGT.PISO_DE_RESULTADO_INTEIRO]
    assert len(inteiros) == AGT.RESULTADOS_INTEIROS, \
        "a poda cortou o resultado em que ele está trabalhando"
    assert len(resumidos) == 8 - AGT.RESULTADOS_INTEIROS
    # o resumo diz QUAL ferramenta devolveu e QUANTO ela devolveu
    assert "ler_documentacao" in resumidos[0]["resultados"][0]["conteudo"]
    assert str(len(grande) + 1) in resumidos[0]["resultados"][0]["conteudo"]
    # E O QUE ESTÁ GRAVADO CONTINUA INTEIRO: a poda é do reenvio, não do registro
    assert len(passos[2]["conteudo"]) == len(grande) + 1


def test_a_poda_derruba_o_maior_envio_e_nao_so_a_soma():
    """A conta do #74 NÃO é a soma: é UMA requisição que não coube no prazo.

    Medido na sessão 1 desta instalação, com
    `tools/medir_o_peso_da_conversa.py` — que reconstrói a conversa com o
    `_conversa` de verdade em cada um dos 32 pontos de chamada dela: o MAIOR
    envio subia com **256.965 caracteres**, e com a poda vai a **88.622** —
    65,5 % menor. É a diferença entre uma conversa que o provedor começa a
    responder em segundos e uma que estoura o prazo.

    **SOMA E MAIOR ENVIO SÃO DUAS PERGUNTAS**, e a poda responde as duas: a soma
    é o gasto (#68) e o maior envio é o tempo (#74). Este teste guarda a
    segunda, e por um motivo: uma poda «pela metade» — que só cortasse o
    resultado antigo mais curto, ou que ficasse com muitos resultados inteiros —
    continuaria derrubando a soma e deixaria o maior envio onde estava, que é
    exatamente o que faz o turno estourar o prazo.
    """
    # Doze leituras grandes, que é a forma que a sessão real teve: muitas
    # ferramentas, e cada uma devolvendo bem mais que o piso.
    grande = "R" * 20_000
    passos: list[dict] = [{"tipo": AGS.PEDIDO, "conteudo": "leia tudo",
                           "ferramenta": None, "chamada_id": None,
                           "argumentos": None, "erro": None}]
    for i in range(1, 13):
        passos.append({"tipo": AGS.FERRAMENTA, "conteudo": "", "erro": None,
                       "ferramenta": "ler_codigo", "chamada_id": f"c{i}",
                       "argumentos": "{}"})
        passos.append({"tipo": AGS.RESULTADO, "conteudo": f"{grande}{i}",
                       "ferramenta": "ler_codigo", "chamada_id": f"c{i}",
                       "argumentos": None, "erro": 0})

    def envio(podar: bool) -> int:
        """O tamanho do que sobe no ÚLTIMO ponto de chamada — o maior deles.

        É aqui que a conversa está do tamanho máximo: tudo o que ele leu já
        entrou nela. É esta requisição — e não a média — que o provedor tem de
        responder dentro do prazo.
        """
        conversa = AGT._conversa([], passos)
        if podar:
            conversa = AGT._poupar(conversa)
        return len(json.dumps(conversa, ensure_ascii=False))

    sem, com = envio(podar=False), envio(podar=True)
    assert com < sem, (
        f"a poda não derrubou o maior envio ({sem} → {com} caracteres): "
        f"é ele que estoura o prazo, e não a soma")
    # Com 12 leituras e 6 delas inteiras, o maior envio tem de cair quase pela
    # metade. O piso é folgado de propósito: o que ele pega é a poda que voltar
    # a deixar tudo inteiro, que é o defeito de novo — e não um detalhe de
    # formatação do JSON.
    assert com <= sem * 0.6, f"a poda quase não mexeu: {sem} → {com} caracteres"


def test_o_modelo_que_responde_vazio_vira_erro_e_nao_silencio(casa, monkeypatch):
    """O #74 do lado do provedor.

    `_grava_turno` não escreve nada quando não há texto nem ferramenta, e a
    rodada seguia para o «acabou» e fechava como CONCLUIDA: quem perguntou
    ficava **sem resposta, sem erro e sem aviso**, com o console parecendo
    travado — a conversa com os passos de antes e nada depois.

    **E O PROVEDOR JÁ DIZIA POR QUÊ.** `parou` vem do `finish_reason` da
    resposta, era devolvido por `conversar` e ninguém o lia: quando ele diz
    `length`, o modelo gastou o teto de SAÍDA (`maximo_de_saida`) pensando e
    devolveu o conteúdo vazio — o caso clássico dos modelos de raciocínio.
    """
    retrato, _ = _pedir(casa, monkeypatch, _fala(""))
    assert retrato["sessao"]["estado"] == AGS.ERRO
    assert "sem texto nenhum" in retrato["sessao"]["erro"]
    assert retrato["recado"]["tom"] == "danger"
    # e o que ele já tinha lido não se perde: a conversa continua na tela
    assert retrato["conversa"][0]["tipo"] == "user"

    # com o motivo declarado pelo provedor, o erro DIZ qual é
    retrato, _ = _pedir(casa, monkeypatch,
                        {"texto": "", "modelo": "deepseek-reasoner",
                         "entrada": 900, "saida": 8000, "chamadas": [],
                         "parou": "length"})
    assert retrato["sessao"]["estado"] == AGS.ERRO
    assert "limite de tamanho da resposta" in retrato["sessao"]["erro"]


def test_a_rodada_que_nao_escreveu_nada_deixa_a_linha_que_faltava(casa,
                                                                 monkeypatch):
    """O #74 do lado da casa.

    Uma rodada pode terminar sem gravar um passo — o processo morre, uma exceção
    sobe antes do primeiro `_aviso`. Até 18/09/2026 isso deixava o console
    exatamente como estava, com a sessão ABERTA recusando a fala seguinte, e
    nenhuma pista do que houve: **a tela não tinha como dizer o que o banco não
    guardou**.

    A guarda é chamada direto porque é isso que ela é: o conserto do fim de
    qualquer rodada, e não um caminho do laço.
    """
    con = _con(casa)
    AGS.init_agente_schema(con)
    sessao = AGS.abrir_sessao(con, titulo="muda", pedido="confira",
                              provedor="deepseek", modelo="deepseek-chat",
                              agora=HORA, criada_por="MARIO")
    AGS.registrar_passo(con, sessao, ordem=1, tipo=AGS.PEDIDO,
                        conteudo="confira o selo", agora=HORA)
    desde = AGS.proxima_ordem(con, sessao)
    con.commit()
    con.close()

    AGT._a_rodada_nao_escreveu_nada(casa["db"], sessao, desde=desde,
                                    hora=lambda: HORA)

    con = _con(casa)
    passos = AGS.passos_da_sessao(con, sessao)
    assert passos[-1]["tipo"] == AGS.AVISO
    assert AGT.AVISO_DE_RODADA_MUDA in passos[-1]["conteudo"]
    assert AGS.ler_sessao(con, sessao)["estado"] == AGS.INTERROMPIDA
    con.close()

    # E QUEM JÁ ESCREVEU NÃO RECEBE AVISO NENHUM: a guarda pergunta à gravação
    # (`proxima_ordem`, o mesmo número que `registrar_passo` usa), e não a um
    # contador paralelo que divergiria do de lá no primeiro conserto.
    AGT._a_rodada_nao_escreveu_nada(casa["db"], sessao, desde=desde,
                                    hora=lambda: HORA)
    con = _con(casa)
    assert len(AGS.passos_da_sessao(con, sessao)) == len(passos)
    con.close()


def test_a_falha_do_provedor_vira_estado_e_nao_perde_o_trabalho(casa,
                                                                monkeypatch):
    """Um `raise` aqui perderia o diagnóstico inteiro por causa da última
    chamada — e é justamente ele que custou dinheiro."""
    _chave(casa)
    recebido = []
    respostas = [_fala(chamadas=[_pedido_ferramenta("estado_do_sistema")])]

    def cai(pasta, **k):
        recebido.append(k)
        if respostas:
            return respostas.pop(0)
        raise PROV.AgenteError("sem crédito nesta conta")

    monkeypatch.setattr(PROV, "conversar", cai)
    retrato = AGT.pedir(casa["db"], pedido="confira o selo",
                        pasta_de_dados=casa["dados"], raiz=RAIZ, agora=HORA,
                        usuario="MARIO", app=casa["app"])
    sessao = retrato["sessao"]
    assert sessao["estado"] == AGS.ERRO
    assert "sem crédito" in sessao["erro"]
    # o que já tinha sido lido continua gravado, e o aviso diz o que houve
    assert [p for p in retrato["passos"] if p["tipo"] == AGS.RESULTADO]
    assert any("sem crédito" in p["conteudo"] for p in retrato["passos"]
               if p["tipo"] == AGS.AVISO)


def test_a_sessao_interrompida_retoma_com_o_resultado_que_faltou(casa,
                                                                 monkeypatch):
    """**FALTA LUZ, ALGUÉM FECHA O CONSOLE, O PROCESSO CAI** entre a gravação
    do pedido e a do resultado. O provedor recusa a conversa quando falta um
    resultado — e a sessão ficaria irrecuperável, com o trabalho perdido."""
    con = _con(casa)
    AGS.init_agente_schema(con)
    sessao = AGS.abrir_sessao(con, titulo="interrompida", pedido="confira",
                              provedor="deepseek", modelo="deepseek-chat",
                              agora=HORA, criada_por="MARIO")
    AGS.registrar_passo(con, sessao, ordem=1, tipo=AGS.PEDIDO,
                        conteudo="confira o selo", agora=HORA)
    AGS.registrar_passo(con, sessao, ordem=2, tipo=AGS.FERRAMENTA,
                        ferramenta="estado_do_sistema", chamada_id="c9",
                        argumentos="{}", agora=HORA)
    con.commit()
    con.close()

    # O PROGRAMA ABRIU DE NOVO — e é aqui que esta sessão volta a ter conserto:
    # `responder` recusa sessão aberta, e sem esta passada ela ficaria presa com
    # o trabalho (já pago) dentro. É a mesma reconciliação da abertura do banco.
    con = _con(casa)
    assert AGT.recuperar_sessoes_interrompidas(con, agora=HORA) >= 1
    assert AGS.ler_sessao(con, sessao)["estado"] == AGS.INTERROMPIDA
    avisos = [p["conteudo"] for p in AGS.passos_da_sessao(con, sessao)
              if p["tipo"] == AGS.AVISO]
    assert any("interrompida" in a for a in avisos), avisos
    # e rodar de novo não move o que já está fechado
    assert AGT.recuperar_sessoes_interrompidas(con, agora=HORA) == 0
    con.commit()
    con.close()

    _chave(casa)
    falso = _roteiro(_fala("O QUE EU VI: retomei."))
    monkeypatch.setattr(PROV, "conversar", falso)

    retrato = AGT.responder(casa["db"], sessao, pedido="continue",
                            pasta_de_dados=casa["dados"], raiz=RAIZ,
                            agora=HORA, usuario="MARIO", app=casa["app"])
    conversa = falso.recebido[0]["conversa"]
    blocos = [e for e in conversa if e["tipo"] == "tool"]
    assert blocos, "o pedido de ferramenta ficou sem resposta — o provedor "
    assert blocos[0]["resultados"][0]["id"] == "c9"
    assert blocos[0]["resultados"][0]["erro"] is True
    assert "interromp" in blocos[0]["resultados"][0]["conteudo"].lower()
    # e o pedido novo do oficial entrou na conversa
    assert any(e["tipo"] == "user" and e["texto"] == "continue"
               for e in conversa)
    assert retrato["sessao"]["estado"] == AGS.CONCLUIDA


def test_o_gasto_soma_entre_as_rodadas_da_mesma_sessao(casa, monkeypatch):
    """Gravar só a última rodada faria a tela dizer um preço que ninguém
    pagou — e o teto de gasto olharia para o número errado."""
    retrato, _ = _pedir(casa, monkeypatch, _fala(entrada=1000, saida=200))
    primeiro = retrato["sessao"]["tokens_de_entrada"]

    falso = _roteiro(_fala(entrada=500, saida=100))
    monkeypatch.setattr(PROV, "conversar", falso)
    retrato = AGT.responder(casa["db"], retrato["sessao"]["id"],
                            pedido="e mais isto", pasta_de_dados=casa["dados"],
                            raiz=RAIZ, agora=HORA, usuario="MARIO",
                            app=casa["app"])
    assert retrato["sessao"]["tokens_de_entrada"] == primeiro + 500
    assert retrato["sessao"]["tokens_de_saida"] == 200 + 100


def test_o_teto_de_sessoes_do_dia_recusa_a_seguinte(casa, monkeypatch):
    """O freio de gasto que a casa controla — e ele não muda o que já foi
    feito hoje."""
    con = _con(casa)
    hoje = AGS.contagem_do_dia(con, desde=HOJE)["sessoes"]
    con.close()
    _cris(casa, AGS.CHAVE_TETO_SESSOES, max(hoje, 1))
    _chave(casa)
    with pytest.raises(AGT.AgenteRecusado) as recusa:
        AGT.pedir(casa["db"], pedido="mais uma",
                  pasta_de_dados=casa["dados"], raiz=RAIZ, agora=HORA,
                  usuario="MARIO")
    assert "teto do dia" in str(recusa.value)
    _cris(casa, AGS.CHAVE_TETO_SESSOES,
          AGS.PADROES[AGS.CHAVE_TETO_SESSOES])


def test_o_retrato_traz_a_conversa_e_os_dados_da_tela(casa, monkeypatch):
    """A tela não remonta nada: ela desenha o que o domínio devolve."""
    retrato, _ = _pedir(casa, monkeypatch, _fala("O QUE EU VI: nada."))
    # O CONJUNTO É EXATO, E ISSO É DE PROPÓSITO: `retrato` é o que a tela da
    # sessão desenha, e uma chave a mais aqui é ou campo que ninguém usa, ou
    # campo que a tela passou a precisar e alguém esqueceu de desenhar. As
    # cinco que entraram com a conversa ao vivo (15/09/2026) têm cada uma o seu
    # porquê, e nenhuma é enfeite:
    #   `rodando`          — sem ele a página não sabe se deve continuar
    #                        perguntando, e a conversa congela sem avisar;
    #   `proximo`          — o cursor dos passos; sem ele a tela releria a
    #   `mudanca_proxima`    conversa inteira a cada segundo para descobrir que
    #                        nada mudou, e o resultado de uma ferramenta pode ter
    #                        dezenas de linhas;
    #   `selo`             — o texto e a cor do estado, escritos UMA vez em
    #                        `agente_schema.selo_do_estado`; o JavaScript os
    #                        troca sem traduzir, e a tradução escrita à mão
    #                        diria «em curso» onde o servidor diz «parou no teto»;
    #   `recado`           — a frase do fim, a mesma do console e da gaveta.
    assert set(retrato) == {"sessao", "passos", "mudancas", "conversa",
                            "rodando", "selo", "recado",
                            "proximo", "mudanca_proxima"}
    assert retrato["conversa"][0]["tipo"] == "user"
    assert retrato["conversa"][-1]["tipo"] == "assistant"
    assert "O QUE EU VI" in retrato["conversa"][-1]["texto"]
    # E ELES RESPONDEM, NÃO SÓ EXISTEM. A sessão terminou neste pedido, e é
    # isso que os cinco dizem: não está rodando, tem recado de fim, o selo é o
    # do estado, e os cursores apontam para o último passo (não para zero, que
    # faria a tela redesenhar o que já está nela).
    assert retrato["rodando"] is False
    assert retrato["recado"]["tom"] == "success"
    assert retrato["selo"]["texto"] == "terminou"
    assert retrato["proximo"] == retrato["passos"][-1]["ordem"] > 0
    assert retrato["mudanca_proxima"] == 0


# ============================================ a frase do fim, quando não houve
# Problema #74: o relato foi «a conversa demorou e deu timeout», e a mensagem
# de então só dizia «não consegui falar com o provedor». As duas causas — prazo
# estourado e máquina sem rede — pedem providências diferentes, e a frase não
# as separava. Estes dois testes guardam a separação.


def test_o_timeout_diz_o_tamanho_do_que_subiu_e_o_prazo():
    """A frase que responde «foi a rede ou foi o tamanho?» sem ir medir de novo.

    O que a medição da sessão 1 achou está no `_poupar` (item 2): a conversa
    subia com **256.965 caracteres**, e requisição grande é o que faz o
    provedor demorar mais que o prazo. Sem esses dois números na mensagem, o
    próximo a ver o erro refaz a investigação inteira.
    """
    frase = PROV._nao_consegui(
        "deepseek", "TimeoutError: The read operation timed out",
        corpo=b"x" * 263_000, prazo=120, segundos=241.7)
    assert "256 KB" in frase          # o tamanho do que subiu, em KB
    assert "120 s" in frase           # o prazo de cada tentativa
    assert "242 s no total" in frase  # quanto se esperou de verdade
    assert "DeepSeek" in frase
    # E DIZ O QUE FAZER — a saída é a poda: sessão nova reenvia menos.
    assert "sessão nova" in frase


def test_o_erro_que_nao_e_de_tempo_nao_e_chamado_de_timeout():
    """Dizer «estourou o prazo» sobre «Name or service not known» seria o
    carimbo que mente — a causa é outra, e a providência também."""
    frase = PROV._nao_consegui(
        "deepseek", "[Errno -2] Name or service not known",
        corpo=b"x" * 263_000, prazo=120, segundos=3.2)
    assert "Name or service not known" in frase
    assert "prazo de 120 s por tentativa" in frase
    assert "quando ela é grande" not in frase
    assert "sessão nova" not in frase
