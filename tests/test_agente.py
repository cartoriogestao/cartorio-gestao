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
      - e se le TAMBEM NO POSTGRESQL, onde o texto nao basta: a CTE que apaga
        ou altera, o `SELECT ... INTO` e a consulta sem fim sao barrados pelo
        proprio servidor, a funcao do servidor (`pg_sleep`, `pg_read_file`...)
        e recusada pelo texto, e a conexao sai da consulta como entrou;
      - e o SERVIDOR confere o que a consulta alcanca antes de ela rodar
        (LS03): a linha inteira, a coluna de credencial renomeada no FROM, o
        oraculo no WHERE, a vista e o catalogo do servidor com senha nao levam
        o hash ao provedor — e o `count(*)` e o `information_schema` seguem;
      - e a leitura roda com o PAPEL DO AGENTE (LX10), que nao enxerga a
        coluna de credencial: sem nenhuma conferencia antes, `u.*` e
        `row_to_json(u)` dao «permissao negada»; o nome de funcao dentro de
        literal passa; e a consulta de milhoes de linhas traz so o limite;
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

import contextlib
import dataclasses
import glob
import json
import sqlite3
import sys
import threading
import time
from pathlib import Path

import psycopg
import pytest


pytestmark = pytest.mark.lento  # gate rapido: pytest -m "not lento" — pesado + DROP/memory
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import agente as AGT                            # noqa: E402
import agente_ferramentas as FER                # noqa: E402
import agente_provedores as PROV                # noqa: E402
import agente_schema as AGS                     # noqa: E402
import ajuda_privacidade as PRIV                # noqa: E402
import ajuda_problemas as AP                    # noqa: E402
import banco_pg                                 # noqa: E402
import modulos_ligados as ML                    # noqa: E402
from bd_nativo import banco                     # noqa: E402

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
              maximo_de_saida, prazo, **registro):
        recebido.append({"sistema": sistema, "conversa": conversa,
                         "ferramentas": ferramentas, "provedor": provedor,
                         "modelo": modelo, "registro": registro})
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
    con = conexao_de_teste()
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


# ------------------------------- o banco só se lê, também no PostgreSQL (LX07)
#
# No SQLite, começar com SELECT ou WITH era ser leitura. No PostgreSQL, uma CTE
# com DELETE começa com WITH e apaga, e um SELECT alcança o disco do servidor.
# Cada teste mede o banco DEPOIS da recusa: a frase de recusa sozinha não prova
# que a linha ficou.


def _problema_de_teste(casa, titulo: str) -> int:
    """Uma linha em `aj_problemas` para a consulta tentar mexer. **ESCREVE.**"""
    with casa["db"].transaction() as con:
        return AP.anotar(con, origem="RELATADO", titulo=titulo,
                         detalhe="linha do teste do só-leitura", onde="agente",
                         caminho="/agente", versao="3.6.126", usuario="MARIO",
                         agora=HORA)["id"]


def _titulo_do_problema(casa, problema_id: int):
    with casa["db"].connect() as con:
        return banco(con).valor(
            "SELECT titulo FROM aj_problemas WHERE id = %s", (problema_id,))


class _BancoEmprestado:
    """Um `db` cujo `connect()` entrega SEMPRE a mesma conexão, sem fechá-la:
    é como o teste vê a conexão do jeito que a ferramenta a deixou."""

    def __init__(self, con):
        self.con = con

    @contextlib.contextmanager
    def connect(self):
        yield self.con


def test_a_cte_que_apaga_e_recusada_e_a_linha_continua_la(casa):
    """A conexão da ponte confirma cada comando sozinha: sem a transação
    só-leitura, esta consulta apagava, e o agente diria que só leu."""
    problema = _problema_de_teste(casa, "a cte não apaga")
    antes = _titulo_do_problema(casa, problema)
    r = FER.executar(_ctx(casa), "consultar_banco", {"consulta": (
        f"WITH x AS (DELETE FROM aj_problemas WHERE id = {problema} "
        f"RETURNING id) SELECT id FROM x")})
    assert r["erro"] is True, r["conteudo"]
    assert "só leio" in r["conteudo"]
    assert "Nada mudou" in r["conteudo"]
    assert antes is not None
    assert _titulo_do_problema(casa, problema) == antes


def test_a_cte_que_altera_e_recusada_e_a_linha_nao_muda(casa):
    problema = _problema_de_teste(casa, "a cte não altera")
    antes = _titulo_do_problema(casa, problema)
    r = FER.executar(_ctx(casa), "consultar_banco", {"consulta": (
        f"WITH x AS (UPDATE aj_problemas SET titulo = 'mudou' "
        f"WHERE id = {problema} RETURNING id) SELECT id FROM x")})
    assert r["erro"] is True, r["conteudo"]
    assert "só leio" in r["conteudo"]
    assert _titulo_do_problema(casa, problema) == antes


def test_o_select_que_cria_tabela_e_recusado_e_a_tabela_nao_nasce(casa):
    """`SELECT ... INTO` começa com SELECT e é um CREATE TABLE."""
    r = FER.executar(_ctx(casa), "consultar_banco", {
        "consulta": "SELECT id INTO aj_copia_do_agente FROM aj_problemas"})
    assert r["erro"] is True, r["conteudo"]
    with casa["db"].connect() as con:
        assert banco(con).tem_tabela("aj_copia_do_agente") is False


@pytest.mark.parametrize("consulta", [
    "SELECT pg_sleep(1)",
    "SELECT pg_read_file('postgresql.conf')",
    "SELECT pg_ls_dir('.')",
    "SELECT lo_export(1, '/tmp/agente.txt')",
    "SELECT set_config('statement_timeout', '0', true)",
    "SELECT pg_terminate_backend(1)",
    "SELECT pg_advisory_lock(1)",
    "SELECT current_setting('data_directory')",
    # o nome montado aos pedaços, e o nome escrito em código
    "SELECT query_to_xml('select pg_' || 'sleep(1)', true, false, '')",
    'SELECT U&"pg\\005fsleep"(1)',
])
def test_a_funcao_do_servidor_e_recusada_pelo_texto(casa, consulta):
    """A transação só-leitura não segura nenhuma destas — nenhuma grava em
    tabela —, e o usuário da casa pode ser superusuário no PostgreSQL portátil.
    A recusa tem de ser a do texto, e não um «permissão negada» do servidor."""
    r = FER.executar(_ctx(casa), "consultar_banco", {"consulta": consulta})
    assert r["erro"] is True, r["conteudo"]
    assert "do servidor e não do banco" in r["conteudo"]


def test_a_senha_dos_usuarios_do_postgresql_tambem_e_credencial(casa):
    r = FER.executar(_ctx(casa), "consultar_banco",
                     {"consulta": "SELECT usename, passwd FROM pg_shadow"})
    assert r["erro"] is True
    assert "credencial" in r["conteudo"]


def test_o_select_comum_continua_lendo_e_devolvendo_as_linhas(casa):
    """A coluna repetida volta duas vezes: o resultado é o que a consulta
    trouxe, e não um dicionário que junta as duas numa só."""
    problema = _problema_de_teste(casa, "a consulta comum lê")
    r = FER.executar(_ctx(casa), "consultar_banco", {"consulta": (
        f"SELECT p.id, p.titulo, c.id FROM aj_problemas p "
        f"JOIN aj_problemas c ON c.id = p.id WHERE p.id = {problema}")})
    assert r["erro"] is False, r["conteudo"]
    assert r["conteudo"].splitlines() == [
        "id | titulo | id", f"{problema} | a consulta comum lê | {problema}"]
    # e o WITH que só lê continua sendo leitura
    r = FER.executar(_ctx(casa), "consultar_banco", {"consulta": (
        f"WITH x AS (SELECT id FROM aj_problemas WHERE id = {problema}) "
        f"SELECT id FROM x")})
    assert r["erro"] is False, r["conteudo"]
    assert r["conteudo"].splitlines() == ["id", str(problema)]


def test_a_consulta_que_passa_do_prazo_e_interrompida_pelo_banco(casa,
                                                                  monkeypatch):
    """O prazo é do servidor: sem ele, uma consulta sem fim prende uma conexão
    do banco da serventia enquanto o agente espera."""
    monkeypatch.setattr(FER, "PRAZO_DA_CONSULTA_MS", 50)
    r = FER.executar(_ctx(casa), "consultar_banco", {"consulta": (
        "SELECT count(*) AS n FROM generate_series(1, 20000) AS a, "
        "generate_series(1, 20000) AS b")})
    assert r["erro"] is True, r["conteudo"]
    assert "passou do prazo" in r["conteudo"]


def test_a_conexao_sai_da_consulta_sem_transacao_sem_prazo_e_gravavel(casa):
    """**A CONEXÃO VOLTA AO RESERVATÓRIO** e é a da próxima rota. Se a
    consulta do agente a deixasse com a transação só-leitura aberta, ou com o
    prazo dele, a próxima escrita da casa é que pagaria — dando certo ou não
    a consulta."""
    problema = _problema_de_teste(casa, "depois da consulta")
    con = casa["db"].connect()
    try:
        bd = banco(con)
        prazo_de_antes = bd.valor("SHOW statement_timeout")
        ctx = dataclasses.replace(_ctx(casa), db=_BancoEmprestado(con))
        for consulta in (
                f"SELECT titulo FROM aj_problemas WHERE id = {problema}",
                f"WITH x AS (DELETE FROM aj_problemas WHERE id = {problema} "
                f"RETURNING id) SELECT id FROM x",
                "SELECT coluna_que_nao_existe FROM aj_problemas"):
            FER.executar(ctx, "consultar_banco", {"consulta": consulta})
            assert bd._pg.info.transaction_status.name == "IDLE", consulta
            assert bd.valor("SHOW statement_timeout") == prazo_de_antes
            assert bd.valor("SHOW transaction_read_only") == "off"
        bd.escrever("UPDATE aj_problemas SET titulo = %s WHERE id = %s",
                    ("gravou depois da consulta", problema))
        con.commit()
    finally:
        con.close()
    assert _titulo_do_problema(casa, problema) == "gravou depois da consulta"


def test_a_transacao_que_ja_vem_aberta_nao_se_mistura_com_a_consulta(casa):
    """Dentro da transação de outro, o ROLLBACK do fim desfaria o trabalho
    dele, e o COMMIT confirmaria o que o agente não conhece. A recusa não
    confirma nem desfaz nada."""
    problema = _problema_de_teste(casa, "transação de outro")
    antes = _titulo_do_problema(casa, problema)
    con = casa["db"].connect()
    try:
        bd = banco(con)
        bd.escrever("UPDATE aj_problemas SET titulo = %s WHERE id = %s",
                    ("escrita de outro, ainda aberta", problema))
        ctx = dataclasses.replace(_ctx(casa), db=_BancoEmprestado(con))
        r = FER.executar(ctx, "consultar_banco", {"consulta": (
            f"SELECT titulo FROM aj_problemas WHERE id = {problema}")})
        assert r["erro"] is True, r["conteudo"]
        assert "transação aberta" in r["conteudo"]
        # a escrita de outro continua aberta: ela a vê, e mais ninguém
        assert bd._pg.info.transaction_status.name == "INTRANS"
        assert bd.valor("SELECT titulo FROM aj_problemas WHERE id = %s",
                        (problema,)) == "escrita de outro, ainda aberta"
        assert _titulo_do_problema(casa, problema) == antes
    finally:
        con.rollback()
        con.close()
    assert _titulo_do_problema(casa, problema) == antes


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
    """É este clique que faz a permissão de escrever ser defensável. Aqui com
    a confirmação desligada, que é o caminho em que o agente aplica sozinho;
    o caminho proposto (o padrão desde o LS03, M4) tem os testes dele."""
    _cris(casa, AGS.CHAVE_ESCRITA, "1")
    _cris(casa, AGS.CHAVE_SEM_CONFIRMACAO, "1")
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
    _cris(casa, AGS.CHAVE_SEM_CONFIRMACAO, "")


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


def test_a_ordem_dos_passos_trava_antes_de_ler_o_maior(casa, monkeypatch):
    """A ordem do passo é o MAX + 1 de `proxima_ordem`: ler-o-maior-e-gravar.

    Sem a trava, duas gravações da mesma sessão ao mesmo tempo (a rodada e a
    recuperação das interrompidas, por exemplo) leriam o mesmo MAX e repetiriam
    a ordem (L001R). As quatro gravações travam `ag_passos.ordem` ANTES de ler.
    """
    import bd_nativo
    passos = []
    travar, valor = bd_nativo.Banco.travar, bd_nativo.Banco.valor

    def espia_travar(self, chave):
        if chave.startswith("ag_passos"):
            passos.append(chave)
        return travar(self, chave)

    def espia_valor(self, sql, parametros=None):
        if "MAX(ordem)" in sql and "ag_passos" in sql:
            passos.append("MAX")
        return valor(self, sql, parametros)
    with casa["db"].transaction() as con:
        AGS.init_agente_schema(con)
        sessao = AGS.abrir_sessao(con, titulo="trava", pedido="confira",
                                  provedor="deepseek", modelo="deepseek-chat",
                                  agora=HORA, criada_por="MARIO")
        monkeypatch.setattr(bd_nativo.Banco, "travar", espia_travar)
        monkeypatch.setattr(bd_nativo.Banco, "valor", espia_valor)
        AGT._grava_pedido(con, sessao, pedido="confira o selo", agora=HORA)
        AGT._grava_turno(con, sessao, texto="vou ler",
                         chamadas=[_pedido_ferramenta("ler_banco")], agora=HORA)
        AGT._grava_resultados(con, sessao, agora=HORA, resultados=[
            {"nome": "ler_banco", "id": "c1", "conteudo": "nada", "erro": False}])
        AGT._aviso(con, sessao, "fim", agora=HORA)
        monkeypatch.undo()
        ordens = [p["ordem"] for p in AGS.passos_da_sessao(con, sessao)]
    assert passos == ["ag_passos.ordem", "MAX"] * 4
    assert ordens == [1, 2, 3, 4, 5]


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


def test_duas_aberturas_do_banco_nao_fecham_a_mesma_sessao_duas_vezes(casa):
    """A recuperação lê as sessões ABERTAS e grava nelas (L001R).

    Sem `FOR UPDATE`, a segunda abertura lia a sessão ainda ABERTA enquanto a
    primeira não tinha confirmado, e gravava um segundo aviso. Duas conexões no
    mesmo banco são duas aberturas; a segunda roda numa thread.
    """
    import threading
    con = _con(casa)
    AGS.init_agente_schema(con)
    sessao = AGS.abrir_sessao(con, titulo="duas aberturas", pedido="confira",
                              provedor="deepseek", modelo="deepseek-chat",
                              agora=HORA, criada_por="MARIO")
    con.commit()
    con.close()

    primeira = _con(casa)
    assert AGT.recuperar_sessoes_interrompidas(primeira, agora=HORA) >= 1
    resposta: dict = {}

    def segunda_abertura():
        outra = _con(casa)
        try:
            resposta["r"] = AGT.recuperar_sessoes_interrompidas(outra, agora=HORA)
            outra.commit()
        except Exception as erro:  # noqa: BLE001 — o teste mostra qual foi
            resposta["erro"] = erro
        finally:
            outra.close()

    t = threading.Thread(target=segunda_abertura, daemon=True)
    t.start()
    t.join(1.0)     # a segunda chega enquanto a primeira ainda não confirmou
    primeira.commit()
    primeira.close()
    t.join(15)
    assert not t.is_alive(), "a segunda abertura ficou presa"
    assert "erro" not in resposta, resposta.get("erro")
    con = _con(casa)
    avisos = [p for p in AGS.passos_da_sessao(con, sessao) if p["tipo"] == AGS.AVISO]
    con.close()
    assert len(avisos) == 1, [p["ordem"] for p in avisos]
    assert resposta["r"] == 0


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


# ================================================ o registro do uso de IA (LF01)
#
# O Código de Normas do MA (art. 170, § 4º) pede o relatório anual do uso de
# IA, e o registro é gravado pelo transporte. Os testes inteiros moram em
# `test_ia_uso.py` e `test_relatorio_ia.py`; estes ficam aqui porque o agente
# é o maior usuário do transporte — e porque é este o arquivo que a integração
# do lote LF01 confere.


def test_o_agente_diz_ao_transporte_a_finalidade_a_sessao_e_quem_pediu(casa, monkeypatch):
    """Sem isto o registro diria que houve uma chamada, mas não de onde."""
    retrato, falso = _pedir(casa, monkeypatch, _fala("O QUE EU VI: nada."))
    (turno,) = falso.recebido
    assert turno["registro"] == {
        "modulo": "agente", "finalidade": "agente",
        "usuario": "MARIO EXEMPLO DOS SANTOS",
        "referencia": f"ag_sessoes:{retrato['sessao']['id']}", "mascarado": True}


def test_o_turno_do_agente_fica_em_ia_uso_sem_a_conversa(casa, monkeypatch):
    """O transporte de verdade, com a rede de mentira: o turno entra no
    registro com tokens e resultado, e o pedido do oficial não entra."""
    from test_ia_uso import _Rede, _ok_openai
    _chave(casa)
    monkeypatch.setattr(PROV.http.client, "HTTPSConnection",
                        _Rede(_ok_openai("O QUE EU VI: nada quebrado.", 321, 12)))
    retrato = AGT.pedir(casa["db"], pedido="confira o selo do ato PEDIDO-SECRETO",
                        pasta_de_dados=casa["dados"], raiz=RAIZ, agora=HORA,
                        usuario="MARIO EXEMPLO DOS SANTOS", versao="3.6.126",
                        app=casa["app"])
    with casa["db"].connect() as con:
        (linha,) = banco(con).ler(
            "SELECT * FROM ia_uso WHERE referencia = %s ORDER BY id",
            (f"ag_sessoes:{retrato['sessao']['id']}",))
    assert (linha["finalidade"], linha["provedor"], linha["tokens_entrada"],
            linha["tokens_saida"], linha["resultado"]) == (
        "agente", "deepseek", 321, 12, "ok")
    assert "PEDIDO-SECRETO" not in json.dumps(linha, default=str)


def test_o_catalogo_de_ia_cobre_todo_chamador_dos_transportes():
    """A prova mora em `test_ia_uso`; roda aqui também pelo motivo de cima."""
    import test_ia_uso
    test_ia_uso.test_a_varredura_pega_quem_chama_o_transporte_sem_finalidade()
    test_ia_uso.test_o_catalogo_cobre_todo_chamador_dos_transportes()
    test_ia_uso.test_toda_entrada_do_catalogo_diz_o_que_a_norma_pede()


# ========================================= o que o LS03 só relatou (LX13)
#
# B2, B7, B8 e M4 da auditoria LS03 (relatorios/LS03.md), que a terceira volta
# deixou «para depois». Cada teste diz o que caía antes do conserto.


def test_o_nome_de_quem_pediu_nao_vai_na_instrucao_ao_provedor(casa, monkeypatch):
    """**B2.** A conversa sobe mascarada, mas a instrução do sistema não passa
    pela barreira, e levava «Quem pediu: MARIO EXEMPLO DOS SANTOS» a cada
    turno. O modelo precisa do papel, e não do nome; o nome continua no
    registro de uso, que fica na casa."""
    _, falso = _pedir(casa, monkeypatch, _fala("O QUE EU VI: nada."))
    (turno,) = falso.recebido
    assert "MARIO" not in turno["sistema"]
    assert "EXEMPLO DOS SANTOS" not in turno["sistema"]
    assert "Quem pediu: um administrador do sistema (papel ADMIN)." in turno["sistema"]
    assert turno["registro"]["usuario"] == "MARIO EXEMPLO DOS SANTOS"


@pytest.mark.parametrize("consulta", [
    "SELECT id INTO aj_copia_b7 FROM aj_problemas",
    "select id\ninto\ttemporary aj_copia_b7 from aj_problemas",
    "WITH x AS (SELECT id FROM aj_problemas) SELECT id INTO aj_copia_b7 FROM x",
])
def test_o_select_into_e_recusado_com_a_frase_de_so_leio(casa, consulta):
    """**B7.** `SELECT … INTO` já era recusado, mas pela vista provisória, que
    não aceita INTO numa subconsulta: o modelo lia «o banco recusou a
    consulta: syntax error», e não o que fazer. Agora a recusa vem do texto,
    antes do servidor, com a frase de sempre — e a tabela continua sem
    nascer."""
    r = FER.executar(_ctx(casa), "consultar_banco", {"consulta": consulta})
    assert r["erro"] is True, r["conteudo"]
    assert "só leio" in r["conteudo"]
    assert "INTO" in r["conteudo"]
    assert "Nada mudou" in r["conteudo"]
    assert "syntax" not in r["conteudo"] and "recusou" not in r["conteudo"]
    with casa["db"].connect() as con:
        assert banco(con).tem_tabela("aj_copia_b7") is False


def test_a_palavra_into_dentro_de_texto_nao_e_select_into(casa):
    """A recusa do B7 é da palavra-comando, e não da palavra: `'into'` num
    literal, ou `"into"` como nome, é texto."""
    r = FER.executar(_ctx(casa), "consultar_banco", {"consulta": (
        "SELECT 'entra into' AS \"into\" FROM aj_problemas "
        "ORDER BY id LIMIT 1")})
    assert r["erro"] is False, r["conteudo"]


@pytest.mark.parametrize("consulta", [
    "SELECT p FROM users u JOIN aj_problemas p ON p.id = u.id",
    "SELECT row_to_json(p) AS r FROM aj_problemas p, users u "
    "WHERE u.username = 'tabeliao' ORDER BY p.id LIMIT 1",
    'SELECT "P" FROM aj_problemas AS "P" CROSS JOIN users ORDER BY "P".id LIMIT 1',
    "SELECT p.id, p FROM ONLY aj_problemas p, users u "
    "WHERE p.titulo ~ 'a.*' ORDER BY p.id LIMIT 1",
])
def test_a_linha_inteira_de_outra_tabela_na_juncao_com_users_passa(casa, consulta):
    """**B8.** Bastava a consulta citar `users` para a linha inteira de
    QUALQUER apelido ser recusada: a de `aj_problemas`, que não tem
    credencial, caía por causa do `u`, que nem era a linha pedida. Agora o
    apelido diz de quem é a linha, e a de `aj_problemas` passa — sem levar
    o hash, que não está nela."""
    o_hash = _hash_do_tabeliao(casa)
    _problema_de_teste(casa, "linha inteira na junção (B8)")
    r = FER.executar(_ctx(casa), "consultar_banco", {"consulta": consulta})
    assert r["erro"] is False, r["conteudo"]
    assert o_hash not in r["conteudo"]


@pytest.mark.parametrize("consulta", [
    # a linha de `users` na mesma junção que passou acima
    "SELECT u FROM users u JOIN aj_problemas p ON p.id = u.id",
    "SELECT p.id FROM aj_problemas p, users u WHERE u::text LIKE '%a%'",
    # o apelido repetido: o `p` de dentro é de `users` (o servidor o chama p_1)
    "SELECT p FROM aj_problemas p WHERE EXISTS "
    "(SELECT 1 FROM users p WHERE p::text LIKE '%a%')",
    # a linha de uma subconsulta ou de uma junção não se sabe o que leva
    "SELECT s FROM (SELECT p.id, u.username FROM aj_problemas p, users u) AS s",
])
def test_a_linha_inteira_que_pode_levar_users_continua_recusada(casa, consulta):
    """**B8, o outro lado.** Liberar a linha de `aj_problemas` não pode
    liberar a de `users` — nem com o apelido repetido, nem com uma CTE que
    se chama como a tabela inocente, nem por dentro de uma subconsulta."""
    o_hash = _hash_do_tabeliao(casa)
    r = FER.executar(_ctx(casa), "consultar_banco", {"consulta": consulta})
    assert o_hash not in r["conteudo"], "o hash vazou na resposta"
    assert r["erro"] is True, r["conteudo"]
    assert "LINHA INTEIRA" in r["conteudo"]


def test_a_cte_com_o_nome_de_uma_tabela_sem_credencial_nao_engana_a_regra(casa):
    """**B8.** A CTE se chama `aj_problemas` e traz linhas de `users`; a
    tabela de verdade também é citada (o servidor a escreve `aj_problemas_1`).
    Pelo nome, a linha inteira da CTE pareceria a da tabela inocente — e é
    por isso que o nome de CTE conta como apelido desconhecido. As colunas da
    CTE são inocentes de propósito: o que se prova é a regra do apelido, e
    não a da coluna (o hash, se viesse, a coluna já recusaria)."""
    with casa["db"].connect() as con:
        esquema = banco(con).valor("SELECT current_schema() AS s")
    r = FER.executar(_ctx(casa), "consultar_banco", {"consulta": (
        "WITH aj_problemas AS (SELECT id, username FROM users) "
        "SELECT aj_problemas FROM aj_problemas WHERE EXISTS "
        f"(SELECT 1 FROM {esquema}.aj_problemas)")})
    assert r["erro"] is True, r["conteudo"]
    assert "LINHA INTEIRA" in r["conteudo"]
    assert "tabeliao" not in r["conteudo"]


def _sessao_de_teste(casa, titulo: str = "m4") -> int:
    with casa["db"].transaction() as con:
        return AGS.abrir_sessao(con, titulo=titulo, pedido=titulo,
                                provedor="deepseek", modelo="m", agora=HORA,
                                criada_por="MARIO")


def _modulo_e_outro_alcance(casa) -> tuple[str, str, str, str]:
    """O módulo da prova, o nome dele em `settings`, o alcance de agora e um
    alcance diferente."""
    chave = sorted(ML.CHAVE_DA_CONFIGURACAO)[0]
    nome_na_config = ML.CHAVE_DA_CONFIGURACAO[chave]
    agora = casa["db"].get_setting(
        nome_na_config, ML.ALCANCE_DE_FABRICA.get(chave, ML.TODOS))
    outro = [a for a in ML.ALCANCES if a != agora][0]
    return chave, nome_na_config, agora, outro


def test_a_confirmacao_da_escrita_nasce_ligada(casa):
    """**M4.** O lado seguro é o padrão: sem ninguém mexer, o agente só
    propõe."""
    con = conexao_de_teste()
    AGS.init_agente_schema(con)
    assert AGS.escrita_sem_confirmacao(con) is False
    assert AGS.config_para_tela(con)["escrita_sem_confirmacao"] is False
    con.close()


def test_com_a_escrita_ligada_o_alcance_fica_proposto_e_nada_muda_ate_o_clique(casa):
    """**M4.** Com a escrita ligada, o modelo abria e fechava módulo sozinho,
    e o oficial só via depois. Agora a ferramenta grava a PROPOSTA, diz ao
    modelo que nada mudou, e o alcance só muda no clique do oficial — que
    fica registrado com quem e quando."""
    _cris(casa, AGS.CHAVE_ESCRITA, "1")
    try:
        chave, nome_na_config, antes, outro = _modulo_e_outro_alcance(casa)
        sessao = _sessao_de_teste(casa)
        r = FER.executar(_ctx(casa, sessao), "definir_alcance_do_modulo",
                         {"modulo": chave, "alcance": outro})
        assert r["erro"] is False, r["conteudo"]
        assert "PROPOSTO" in r["conteudo"] and "NADA MUDOU" in r["conteudo"]
        assert casa["db"].get_setting(nome_na_config, antes) == antes
        with casa["db"].connect() as con:
            (mudanca,) = AGS.mudancas_da_sessao(con, sessao)
        assert (mudanca["situacao"], mudanca["antes"], mudanca["depois"],
                mudanca["aplicada_em"]) == (AGS.PROPOSTA, antes, outro, None)

        feito = AGT.aplicar(casa["db"], mudanca["id"], agora=HORA,
                            usuario="O OFICIAL")
        assert (feito["antes"], feito["apliquei"]) == (antes, outro)
        assert casa["db"].get_setting(nome_na_config, antes) == outro
        with casa["db"].connect() as con:
            linha = AGS.ler_mudanca(con, mudanca["id"])
        assert (linha["situacao"], linha["aplicada_em"], linha["aplicada_por"]) == (
            AGS.APLICADA, HORA, "O OFICIAL")

        # aplicar duas vezes recusa; e o desfazer de sempre volta
        with pytest.raises(FER.FerramentaError) as recusa:
            AGT.aplicar(casa["db"], mudanca["id"], agora=HORA, usuario="O OFICIAL")
        assert "já está aplicada" in str(recusa.value)
        voltou = AGT.desfazer(casa["db"], mudanca["id"], agora=HORA, usuario="O OFICIAL")
        assert voltou["voltei_para"] == antes
        assert casa["db"].get_setting(nome_na_config, antes) == antes
    finally:
        _cris(casa, AGS.CHAVE_ESCRITA, "")


def test_a_proposta_aplica_e_desfaz_pelo_alcance_que_estava_no_clique(casa):
    """**M4.** Entre a proposta e o clique alguém pode mudar o alcance na tela
    de configuração. O desfazer volta ao que havia NO CLIQUE — senão ele
    desfaria também a mudança de quem não era o agente."""
    _cris(casa, AGS.CHAVE_ESCRITA, "1")
    chave, nome_na_config, antes, _ = _modulo_e_outro_alcance(casa)
    meio, alvo = [a for a in ML.ALCANCES if a != antes][:2]
    try:
        sessao = _sessao_de_teste(casa, "m4 no meio")
        FER.executar(_ctx(casa, sessao), "definir_alcance_do_modulo",
                     {"modulo": chave, "alcance": alvo})
        with casa["db"].connect() as con:
            (mudanca,) = AGS.mudancas_da_sessao(con, sessao)
        casa["db"].set_settings({nome_na_config: meio})      # a tela, no meio
        feito = AGT.aplicar(casa["db"], mudanca["id"], agora=HORA, usuario="O OFICIAL")
        assert (feito["antes"], casa["db"].get_setting(nome_na_config, "")) == (meio, alvo)
        AGT.desfazer(casa["db"], mudanca["id"], agora=HORA, usuario="O OFICIAL")
        assert casa["db"].get_setting(nome_na_config, "") == meio
    finally:
        casa["db"].set_settings({nome_na_config: antes})
        _cris(casa, AGS.CHAVE_ESCRITA, "")


def test_a_proposta_descartada_nao_muda_nada_e_nao_se_aplica_depois(casa):
    """**M4.** Recusar a proposta é o «desfazer» dela: nada volta no sistema,
    porque nada mudou, e a linha fica dizendo quem a descartou. Aplicar
    depois de descartada recusa."""
    _cris(casa, AGS.CHAVE_ESCRITA, "1")
    try:
        chave, nome_na_config, antes, outro = _modulo_e_outro_alcance(casa)
        sessao = _sessao_de_teste(casa, "m4 descartada")
        FER.executar(_ctx(casa, sessao), "definir_alcance_do_modulo",
                     {"modulo": chave, "alcance": outro})
        with casa["db"].connect() as con:
            (mudanca,) = AGS.mudancas_da_sessao(con, sessao)
        r = AGT.desfazer(casa["db"], mudanca["id"], agora=HORA, usuario="O OFICIAL")
        assert r["descartada"] is True
        assert casa["db"].get_setting(nome_na_config, antes) == antes
        with pytest.raises(FER.FerramentaError) as recusa:
            AGT.aplicar(casa["db"], mudanca["id"], agora=HORA, usuario="O OFICIAL")
        assert "descartada" in str(recusa.value)
        assert casa["db"].get_setting(nome_na_config, antes) == antes
    finally:
        _cris(casa, AGS.CHAVE_ESCRITA, "")


def test_a_instrucao_diz_ao_modelo_que_a_mudanca_fica_proposta(casa, monkeypatch):
    """**M4.** O modelo precisa saber que «definir» é propor, senão ele conta
    ao oficial que o módulo já mudou."""
    _cris(casa, AGS.CHAVE_ESCRITA, "1")
    try:
        _, falso = _pedir(casa, monkeypatch, _fala("O QUE EU VI: nada."))
        (turno,) = falso.recebido
        assert "fica PROPOSTA" in turno["sistema"]
    finally:
        _cris(casa, AGS.CHAVE_ESCRITA, "")


# ------------- o que o texto da consulta não mostra, o servidor mostra (LS03)
#
# O guarda de texto recusa o NOME da coluna de credencial e o `SELECT *`. Três
# jeitos de ler `password_salt` e `password_hash` sem escrever nome nenhum
# passavam por ele e levavam o hash ao provedor: a LINHA INTEIRA (`SELECT u
# FROM users u`, `row_to_json(u)`, `"U".*`), a COLUNA RENOMEADA no FROM
# (`FROM users AS x(a, b, c, d, e)`) e o ORÁCULO no WHERE (`u::text LIKE`).
# Agora quem responde é o servidor, antes de a consulta rodar: o plano e as
# colunas que a consulta referencia. (Era o item em aberto da revisão do LX07;
# a primeira volta do LS03 fechou a linha inteira na saída, e estes testes
# medem também o que ela deixava passar.)


def _hash_do_tabeliao(casa) -> str:
    with casa["db"].connect() as con:
        return banco(con).valor(
            "SELECT password_hash FROM users WHERE username = %s", ("tabeliao",))


def _colunas_de_users(casa) -> list[str]:
    """As colunas de `users`, na ordem do banco — é a ordem que o apelido de
    coluna do FROM segue."""
    with casa["db"].connect() as con:
        return [r["column_name"] for r in banco(con).ler(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = 'users' "
            "ORDER BY ordinal_position")]


def _apelidos_ate_o_hash(casa, *, no_lugar_do_hash: str = "") -> tuple[str, str]:
    """`(c1, c2, …, cN)` até a coluna do hash, e o apelido que ela recebeu."""
    colunas = _colunas_de_users(casa)
    posicao = colunas.index("password_hash") + 1
    apelidos = [f"c{i}" for i in range(1, posicao + 1)]
    if no_lugar_do_hash:
        apelidos[-1] = no_lugar_do_hash
    return ", ".join(apelidos), apelidos[-1]


@pytest.mark.parametrize("consulta", [
    "SELECT u FROM users u",
    "SELECT users FROM users",
    "SELECT row_to_json(u) FROM users u",
    "SELECT to_jsonb(u) FROM users u",
    "SELECT u.* FROM users u",
    # o apelido entre aspas, e o que o plano escreve entre aspas: `"U".*`
    'SELECT "U" FROM users AS "U"',
    "SELECT ç FROM users AS ç",
])
def test_a_linha_inteira_de_users_nao_leva_sal_nem_hash_ao_provedor(casa, consulta):
    """O sal e o hash não têm forma de CPF nem de e-mail: se a linha inteira
    passasse, a barreira de privacidade não a seguraria. A recusa é pelo plano,
    e o que o modelo recebe é a recusa — nunca o hash."""
    o_hash = _hash_do_tabeliao(casa)
    assert o_hash, "o teste precisa de um usuário com hash gravado"
    r = FER.executar(_ctx(casa), "consultar_banco", {"consulta": consulta})
    assert r["erro"] is True, r["conteudo"]
    assert o_hash not in r["conteudo"], "o hash vazou na resposta"


@pytest.mark.parametrize("forma", ["apelido", "nome_de_outra", "cte"])
def test_a_coluna_do_hash_renomeada_no_from_nao_sai(casa, forma):
    """`FROM users AS x(c1, …, c5)` lê a quinta coluna com o nome `c5`: o texto
    não diz `password_hash`, e o plano também não — ele escreve o apelido. Com
    a ordem trocada, o hash sai até com o nome de outra coluna (`username`).
    Quem diz a coluna de verdade é o `pg_depend` da vista provisória."""
    o_hash = _hash_do_tabeliao(casa)
    if forma == "apelido":
        lista, coluna = _apelidos_ate_o_hash(casa)
        consulta = f"SELECT x.{coluna} FROM users AS x({lista})"
    elif forma == "nome_de_outra":
        lista, coluna = _apelidos_ate_o_hash(casa, no_lugar_do_hash="username")
        consulta = f"SELECT x.{coluna} FROM users AS x({lista})"
    else:
        lista, coluna = _apelidos_ate_o_hash(casa)
        consulta = (f"WITH t({lista}) AS MATERIALIZED (TABLE users) "
                    f"SELECT t.{coluna} FROM t")
    r = FER.executar(_ctx(casa), "consultar_banco", {"consulta": consulta})
    assert o_hash not in r["conteudo"], "o hash vazou na resposta"
    assert r["erro"] is True, r["conteudo"]
    assert "coluna de credencial" in r["conteudo"]
    assert "users.password_hash" in r["conteudo"]


@pytest.mark.parametrize("forma", ["linha_inteira", "apelido"])
def test_o_where_nao_vira_oraculo_do_hash(casa, forma):
    """A consulta que só devolve `username` mas filtra pelo hash responde «sim»
    ou «não» sobre ele — e cem perguntas soletram o hash. A recusa olha o
    filtro, e não só o que a consulta devolve."""
    prefixo = _hash_do_tabeliao(casa)[:6]
    if forma == "linha_inteira":
        consulta = (f"SELECT username FROM users u "
                    f"WHERE u::text LIKE '%{prefixo}%'")
    else:
        lista, coluna = _apelidos_ate_o_hash(casa)
        consulta = (f"SELECT x.c2 FROM users AS x({lista}) "
                    f"WHERE x.{coluna} LIKE '{prefixo}%'")
    r = FER.executar(_ctx(casa), "consultar_banco", {"consulta": consulta})
    assert r["erro"] is True, r["conteudo"]
    assert "tabeliao" not in r["conteudo"]


def test_a_linha_inteira_ensina_a_nomear_as_colunas(casa):
    """A recusa da linha inteira mostra o caminho: escrever as colunas."""
    r = FER.executar(_ctx(casa), "consultar_banco",
                     {"consulta": "SELECT u FROM users u"})
    assert r["erro"] is True
    assert "LINHA INTEIRA" in r["conteudo"]


def test_a_tabela_do_whatsapp_nao_se_le(casa):
    """`wa_config` guarda o token e o segredo do WhatsApp no VALOR da linha, sob
    a coluna `valor` — um nome que `NOMES_PROIBIDOS` não alcança. A recusa é
    pela tabela, como a de `robo_config` e `ag_config`."""
    r = FER.executar(_ctx(casa), "consultar_banco",
                     {"consulta": "SELECT chave, valor FROM wa_config"})
    assert r["erro"] is True, r["conteudo"]
    assert "não é lida pelo agente" in r["conteudo"]


def test_a_tabela_proibida_por_tras_de_uma_vista_nao_se_le(casa):
    """O texto da consulta diz o nome da vista, e não o da tabela que ela lê;
    o plano diz a tabela. **ESCREVE** uma vista no esquema do arquivo, e a
    tira no fim."""
    with casa["db"].transaction() as con:
        banco(con).escrever(
            "CREATE VIEW vista_neutra_ls03 AS SELECT chave, valor FROM wa_config")
    try:
        r = FER.executar(_ctx(casa), "consultar_banco", {
            "consulta": "SELECT chave, valor FROM vista_neutra_ls03"})
        assert r["erro"] is True, r["conteudo"]
        assert "wa_config" in r["conteudo"]
        assert "não é lida pelo agente" in r["conteudo"]
    finally:
        with casa["db"].transaction() as con:
            banco(con).escrever("DROP VIEW IF EXISTS vista_neutra_ls03")


def test_o_count_e_a_coluna_escrita_continuam_valendo_em_users(casa):
    """A recusa é da coluna de credencial e da LINHA INTEIRA, e não da tabela:
    contar e ler uma coluna escrita à mão continua valendo. O `count(*)` não
    referencia coluna nenhuma; e o `.*` de uma expressão regular, dentro de um
    literal, não é linha inteira."""
    r = FER.executar(_ctx(casa), "consultar_banco",
                     {"consulta": "SELECT count(*) AS n FROM users"})
    assert r["erro"] is False, r["conteudo"]
    assert r["conteudo"].splitlines()[0] == "n"
    r = FER.executar(_ctx(casa), "consultar_banco", {"consulta": (
        "SELECT username FROM users WHERE username = 'tabeliao'")})
    assert r["erro"] is False, r["conteudo"]
    assert "tabeliao" in r["conteudo"]
    r = FER.executar(_ctx(casa), "consultar_banco", {"consulta": (
        "SELECT username, 'tab.*' AS padrao FROM users "
        "WHERE (username COLLATE \"C\") ~ '^tab.*o$'")})
    assert r["erro"] is False, r["conteudo"]
    assert "tabeliao" in r["conteudo"]


def test_a_conferencia_nao_deixa_vista_nem_transacao_na_conexao(casa):
    """A vista provisória nasce numa transação que é desfeita: a conexão volta
    ao reservatório sem ela, sem transação e sem o prazo — tanto da consulta
    que passa quanto da que é recusada."""
    con = casa["db"].connect()
    try:
        bd = banco(con)
        prazo_de_antes = bd.valor("SHOW statement_timeout")
        ctx = dataclasses.replace(_ctx(casa), db=_BancoEmprestado(con))
        for consulta in ("SELECT username FROM users",
                         "SELECT u FROM users u",
                         "SELECT x.c1 FROM users AS x(c1)"):
            FER.executar(ctx, "consultar_banco", {"consulta": consulta})
            assert bd._pg.info.transaction_status.name == "IDLE", consulta
            assert bd.valor("SHOW statement_timeout") == prazo_de_antes
            assert bd.valor(
                "SELECT to_regclass('pg_temp.cg_agente_consulta') IS NULL "
                "AS sumiu") is True, consulta
    finally:
        con.close()


@pytest.mark.parametrize("consulta", [
    # a amostra que o ANALYZE guarda: `histogram_bounds` traz o hash de todos
    "SELECT attname, histogram_bounds FROM pg_stats WHERE tablename = 'users'",
    "SELECT attname, most_common_vals FROM pg_stats WHERE tablename = 'users'",
    # a senha dos usuários do PostgreSQL, renomeada e pela linha inteira
    "SELECT x.c11 FROM pg_authid AS x(c1, c2, c3, c4, c5, c6, c7, c8, c9, c10, c11)",
    "SELECT s FROM pg_shadow s",
])
def test_o_catalogo_do_servidor_com_senha_ou_amostra_nao_se_le(casa, consulta):
    """O `pg_stats` guarda amostras dos valores de cada coluna, e a de `users`
    traz o hash da senha sem que a consulta o nomeie; o `pg_authid` e o
    `pg_shadow`, a senha dos usuários do PostgreSQL. São tabelas do sistema,
    cuja dependência o servidor não grava — a recusa é pelo nome delas.
    **ESCREVE** a estatística de `users` (ANALYZE), que é o que o servidor
    faz sozinho com o tempo."""
    o_hash = _hash_do_tabeliao(casa)
    with casa["db"].transaction() as con:
        banco(con).escrever("ANALYZE users")
    r = FER.executar(_ctx(casa), "consultar_banco", {"consulta": consulta})
    assert o_hash not in r["conteudo"], "o hash vazou na resposta"
    assert "SCRAM-SHA-256$" not in r["conteudo"], "a senha do PostgreSQL vazou"
    assert r["erro"] is True, r["conteudo"]
    assert "catálogo do servidor" in r["conteudo"]


@pytest.mark.parametrize("consulta", [
    "SELECT v FROM vista_de_usuarios_ls03 v",
    "SELECT row_to_json(v) FROM vista_de_usuarios_ls03 v",
    "SELECT v.username FROM vista_de_usuarios_ls03 v WHERE v::text LIKE '%a%'",
])
def test_a_linha_inteira_de_uma_vista_com_credencial_nao_sai(casa, consulta):
    """A linha inteira de uma VISTA não aparece como `v.*` no plano — ele a
    abre nas colunas da tabela — nem deixa coluna no `pg_depend`. Quem a
    mostra é o SQL que o servidor entendeu. **ESCREVE** uma vista no esquema
    do arquivo, e a tira no fim."""
    o_hash = _hash_do_tabeliao(casa)
    with casa["db"].transaction() as con:
        banco(con).escrever(
            "CREATE VIEW vista_de_usuarios_ls03 AS "
            "SELECT id, username, password_hash FROM users")
    try:
        r = FER.executar(_ctx(casa), "consultar_banco", {"consulta": consulta})
        assert o_hash not in r["conteudo"], "o hash vazou na resposta"
        assert r["erro"] is True, r["conteudo"]
        assert "LINHA INTEIRA" in r["conteudo"]
        assert "vista_de_usuarios_ls03" in r["conteudo"]
    finally:
        with casa["db"].transaction() as con:
            banco(con).escrever("DROP VIEW IF EXISTS vista_de_usuarios_ls03")


@pytest.mark.parametrize("consulta", [
    # o guarda de texto libera o `SELECT *` do information_schema, e as
    # funções dela recebem linhas inteiras de `pg_attribute` por dentro
    "SELECT * FROM information_schema.columns WHERE table_name = 'tasks'",
    # linha inteira de tabela sem credencial é o mesmo que escrever as colunas
    "SELECT p FROM aj_problemas p ORDER BY p.id LIMIT 1",
    "SELECT rolname FROM pg_roles ORDER BY rolname",
    "SELECT pid, state FROM pg_stat_activity ORDER BY pid",
])
def test_o_catalogo_e_a_linha_sem_credencial_continuam_valendo(casa, consulta):
    """O freio é da credencial, e não do catálogo nem da linha inteira: o
    diagnóstico continua lendo o esquema, as conexões e os papéis."""
    r = FER.executar(_ctx(casa), "consultar_banco", {"consulta": consulta})
    assert r["erro"] is False, r["conteudo"]


@pytest.mark.parametrize("consulta", [
    # a linha inteira de uma JUNÇÃO leva a de `users` dentro dela
    "SELECT j FROM (users u CROSS JOIN (SELECT 1 AS um) AS k) AS j",
    "SELECT j FROM (users NATURAL JOIN (SELECT 1 AS um) AS k) AS j",
    # `TABLE users` numa subconsulta é o `SELECT *` sem a palavra
    "SELECT s FROM (TABLE users) AS s",
    "SELECT x FROM users AS u, LATERAL row_to_json(u) AS x",
    "SELECT ARRAY(SELECT users FROM users) AS a",
    "SELECT k.v FROM users AS u, json_each_text(row_to_json(u)) AS k(c, v)",
    # não devolvem o hash, mas a ordem e o agrupamento pela linha inteira
    # respondem perguntas sobre ele: são o oráculo do WHERE com outro nome
    "SELECT username FROM users AS u ORDER BY u",
    "SELECT count(*) AS n FROM users AS u GROUP BY u",
])
def test_a_linha_inteira_por_juncao_subconsulta_ou_ordem_tambem_nao_sai(
        casa, consulta):
    """Medidos na terceira volta do LS03 (19/10/2026), contra o freio da
    segunda: cada forma chega à linha inteira de `users` por um caminho que o
    texto não mostra — o apelido de uma junção, `TABLE`, `LATERAL`, um ARRAY
    de linhas, a ordem. No HEAD de antes do LS03 todas passavam: as seis
    primeiras levavam o hash ao provedor, e as duas últimas respondiam. O
    freio do servidor pega todas, e este teste segura que continue pegando."""
    o_hash = _hash_do_tabeliao(casa)
    r = FER.executar(_ctx(casa), "consultar_banco", {"consulta": consulta})
    assert o_hash not in r["conteudo"], "o hash vazou na resposta"
    assert r["erro"] is True, r["conteudo"]


@pytest.mark.parametrize("escrita", ["DELETE", "UPDATE", "INSERT"])
def test_a_cte_que_escreve_e_recusada_pelo_plano_com_a_frase_de_sempre(
        casa, escrita):
    """**A ESCRITA SAI NO PLANO, ANTES DA VISTA PROVISÓRIA** (pedido da
    revisão da segunda volta do LS03: prova direta deste ramo).

    A vista provisória não aceita CTE que escreve. Sem a recusa pelo nó
    `ModifyTable` do plano, a CTE chegaria lá, e o modelo receberia «o banco
    recusou a consulta» com um erro do PostgreSQL, no lugar do «só leio, nada
    mudou», que diz o que fazer. Os testes do LX07 já caem sem este ramo, mas
    só para DELETE e UPDATE; este cobre também o INSERT, prende a frase do
    plano, e mede no banco que a linha ficou e que nenhuma nasceu."""
    problema = _problema_de_teste(casa, f"a cte de {escrita} não escreve")
    antes = _titulo_do_problema(casa, problema)
    with casa["db"].connect() as con:
        quantas_antes = banco(con).valor("SELECT count(*) AS n FROM aj_problemas")
    dentro = {
        "DELETE": f"DELETE FROM aj_problemas WHERE id = {problema} RETURNING id",
        "UPDATE": (f"UPDATE aj_problemas SET titulo = 'mudou' "
                   f"WHERE id = {problema} RETURNING id"),
        "INSERT": ("INSERT INTO aj_problemas (impressao, origem, titulo, "
                   "primeira_em, ultima_em) VALUES ('ls03-plano', 'RELATADO', "
                   "'nasceu pela cte', '2026-09-14', '2026-09-14') RETURNING id"),
    }[escrita]
    r = FER.executar(_ctx(casa), "consultar_banco", {
        "consulta": f"WITH x AS ({dentro}) SELECT id FROM x"})
    assert r["erro"] is True, r["conteudo"]
    assert "o plano dela tem um INSERT, UPDATE ou DELETE" in r["conteudo"]
    assert "Nada mudou" in r["conteudo"]
    assert _titulo_do_problema(casa, problema) == antes
    with casa["db"].connect() as con:
        assert banco(con).valor(
            "SELECT count(*) AS n FROM aj_problemas") == quantas_antes


# ------------------------------ o papel do agente e o resto da revisão (LX10)
#
# As ressalvas da revisão do LX07. A credencial agora é recusada pela ORIGEM:
# a leitura roda com um papel do PostgreSQL que não enxerga as colunas dela.
# Os testes do papel desligam as conferências de antes (`_conferir_antes_de_ler`)
# para provar que é o servidor, e não mais uma lista, quem segura o hash.


def _sem_conferencia(monkeypatch) -> None:
    monkeypatch.setattr(FER, "_conferir_antes_de_ler", lambda pg, sql: None)


@pytest.mark.parametrize("conferencia", ["com_as_conferencias", "so_o_papel"])
@pytest.mark.parametrize("consulta", [
    "SELECT u.* FROM users u",
    "SELECT users.* FROM users",
    "SELECT u FROM users u",
    "SELECT row_to_json(u) AS j FROM users u",
    "SELECT to_jsonb(u) AS j FROM users u",
    "SELECT (u).* FROM users u",
])
def test_a_linha_inteira_de_users_nao_sai_nem_sem_as_conferencias(
        casa, monkeypatch, consulta, conferencia):
    """Item 11 da revisão do LX07: `u.*`, `u`, `row_to_json(u)` e `to_jsonb`
    driblavam a recusa pelo nome da coluna. Sem nenhuma conferência antes, o
    papel do agente ainda não tem SELECT no sal nem no hash, e o servidor
    recusa a linha inteira com «permissão negada»."""
    o_hash = _hash_do_tabeliao(casa)
    if conferencia == "so_o_papel":
        _sem_conferencia(monkeypatch)
    r = FER.executar(_ctx(casa), "consultar_banco", {"consulta": consulta})
    assert o_hash not in r["conteudo"], "o hash vazou na resposta"
    assert r["erro"] is True, r["conteudo"]
    if conferencia == "so_o_papel":
        assert "não me deixa ler" in r["conteudo"]


def test_o_papel_do_agente_le_tudo_menos_a_credencial(casa):
    """O papel é o que a leitura usa, e ele não entra, não é superusuário e não
    vê a coluna de credencial nem a tabela de chave. A coluna comum de `users`
    ele vê, e a tabela sem credencial ele vê inteira."""
    r = FER.executar(_ctx(casa), "consultar_banco", {
        "consulta": "SELECT current_user AS quem, session_user AS sessao"})
    assert r["erro"] is False, r["conteudo"]
    quem, sessao = r["conteudo"].splitlines()[1].split(" | ")
    assert quem == FER.PAPEL_DO_AGENTE
    assert sessao != FER.PAPEL_DO_AGENTE
    with casa["db"].connect() as con:
        bd = banco(con)
        papel = bd.um(
            "SELECT rolsuper, rolcanlogin, rolinherit FROM pg_roles "
            "WHERE rolname = %s", (FER.PAPEL_DO_AGENTE,))
        assert papel == {"rolsuper": False, "rolcanlogin": False,
                         "rolinherit": False}

        def ve(tabela, coluna=None):
            if coluna is None:
                return bd.valor("SELECT has_table_privilege(%s, %s, 'SELECT') "
                                "AS ve", (FER.PAPEL_DO_AGENTE, tabela))
            return bd.valor("SELECT has_column_privilege(%s, %s, %s, 'SELECT') "
                            "AS ve", (FER.PAPEL_DO_AGENTE, tabela, coluna))

        assert ve("users", "password_hash") is False
        assert ve("users", "password_salt") is False
        assert ve("users", "username") is True
        assert ve("users") is False         # só coluna a coluna
        assert ve("aj_problemas") is True
        for tabela in FER.TABELAS_PROIBIDAS:
            if bd.tem_tabela(tabela):
                assert ve(tabela) is False, tabela


def test_a_tabela_que_nasce_depois_entra_no_papel_sem_a_credencial(casa):
    """O papel é acertado na consulta: a tabela que nasce numa atualização do
    sistema é lida na primeira consulta depois dela, e a coluna de credencial
    dela fica de fora. **ESCREVE** uma tabela no esquema do arquivo, e a tira
    no fim."""
    with casa["db"].transaction() as con:
        banco(con).escrever(
            "CREATE TABLE lx10_tabela_nova (id bigint, nome text, "
            "api_token text)")
        banco(con).escrever(
            "INSERT INTO lx10_tabela_nova VALUES (1, 'linha nova', 'tk-teste')")
    try:
        r = FER.executar(_ctx(casa), "consultar_banco", {
            "consulta": "SELECT id FROM lx10_tabela_nova ORDER BY id"})
        assert r["erro"] is False, r["conteudo"]
        assert r["conteudo"].splitlines() == ["id", "1"]
        with casa["db"].connect() as con:
            assert banco(con).valor(
                "SELECT has_column_privilege(%s, 'lx10_tabela_nova', "
                "'api_token', 'SELECT') AS ve", (FER.PAPEL_DO_AGENTE,)) is False
    finally:
        with casa["db"].transaction() as con:
            banco(con).escrever("DROP TABLE IF EXISTS lx10_tabela_nova")


def test_a_visao_materializada_com_o_hash_renomeado_nao_se_le_pelo_papel(
        casa, monkeypatch):
    """A visão materializada guarda o que a consulta de quem a criou leu, com o
    apelido como nome de coluna: `password_hash AS outra` não casa com
    `NOMES_PROIBIDOS`, e o GRANT de tabela inteira entregaria o hash ao papel
    (anotação da revisão da 2ª volta do LX10). Sem as conferências de antes,
    para provar que é o papel quem segura. **ESCREVE** uma visão materializada
    no esquema do arquivo, e a tira no fim."""
    o_hash = _hash_do_tabeliao(casa)
    with casa["db"].transaction() as con:
        banco(con).escrever(
            "CREATE MATERIALIZED VIEW lx10_materializada AS "
            "SELECT id, password_hash AS outra FROM users")
    try:
        _sem_conferencia(monkeypatch)
        r = FER.executar(_ctx(casa), "consultar_banco", {
            "consulta": "SELECT outra FROM lx10_materializada ORDER BY id"})
        assert o_hash not in r["conteudo"], "o hash vazou na resposta"
        assert r["erro"] is True, r["conteudo"]
        assert "não me deixa ler" in r["conteudo"]
        with casa["db"].connect() as con:
            assert banco(con).valor(
                "SELECT has_table_privilege(%s, 'lx10_materializada', "
                "'SELECT') AS ve", (FER.PAPEL_DO_AGENTE,)) is False
    finally:
        with casa["db"].transaction() as con:
            banco(con).escrever(
                "DROP MATERIALIZED VIEW IF EXISTS lx10_materializada")


def test_a_conexao_volta_com_o_usuario_de_antes(casa):
    """O `SET LOCAL ROLE` morre com o ROLLBACK: a próxima rota não pode
    herdar o papel do agente, que não grava nada."""
    con = casa["db"].connect()
    try:
        bd = banco(con)
        antes = bd.valor("SELECT current_user AS quem")
        ctx = dataclasses.replace(_ctx(casa), db=_BancoEmprestado(con))
        for consulta in ("SELECT username FROM users",
                         "SELECT u FROM users u",
                         "SELECT coluna_que_nao_existe FROM users"):
            FER.executar(ctx, "consultar_banco", {"consulta": consulta})
            assert bd.valor("SELECT current_user AS quem") == antes, consulta
            assert bd._pg.info.transaction_status.name == "IDLE", consulta
    finally:
        con.close()


class _CursorQueCai:
    """Um cursor cuja conexão cai: o ROLLBACK também falha."""

    def __init__(self):
        self.comandos: list[str] = []

    def execute(self, comando, *_):
        self.comandos.append(comando)
        if comando == "ROLLBACK":
            raise psycopg.OperationalError("the connection is closed")


def test_o_rollback_que_falha_nao_troca_o_erro_da_consulta():
    """Item 5 da revisão do LX07: o ROLLBACK do `finally` levantava o erro dele
    no lugar do da consulta. Com erro subindo, ele cede; sem erro, ele sobe,
    porque a conexão não volta ao reservatório num estado que ninguém sabe."""
    cursor = _CursorQueCai()
    with pytest.raises(psycopg.errors.QueryCanceled, match="erro da consulta"):
        with FER._desfeita(cursor, "BEGIN READ ONLY"):
            raise psycopg.errors.QueryCanceled("o erro da consulta")
    assert cursor.comandos == ["BEGIN READ ONLY", "ROLLBACK"]
    cursor = _CursorQueCai()
    with pytest.raises(psycopg.OperationalError, match="closed"):
        with FER._desfeita(cursor, "BEGIN READ ONLY"):
            pass


def test_a_conexao_que_cai_no_meio_da_consulta_diz_por_que_caiu(casa):
    """A mesma coisa no banco de verdade: a conexão do agente é derrubada no
    meio da leitura (`pg_terminate_backend`, por outra conexão). O modelo tem
    de ler que o servidor encerrou a conexão, e não «a conexão está fechada»,
    que é o erro do ROLLBACK depois dela."""
    con = casa["db"].connect()
    pid = banco(con).valor("SELECT pg_backend_pid() AS pid")
    ctx = dataclasses.replace(_ctx(casa), db=_BancoEmprestado(con))

    def derrubar():
        with casa["db"].connect() as outra:
            bd = banco(outra)
            for _ in range(400):
                if bd.valor("SELECT count(*) AS n FROM pg_stat_activity "
                            "WHERE pid = %s AND state = 'active' "
                            "AND query LIKE %s", (pid, "FETCH%")):
                    bd.valor("SELECT pg_terminate_backend(%s) AS ok", (pid,))
                    return
                time.sleep(0.05)

    quem_derruba = threading.Thread(target=derrubar)
    quem_derruba.start()
    try:
        r = FER.executar(ctx, "consultar_banco", {"consulta": (
            "SELECT count(*) AS n FROM generate_series(1, 20000) AS a, "
            "generate_series(1, 20000) AS b")})
    finally:
        quem_derruba.join()
        with contextlib.suppress(Exception):
            con.close()
    assert r["erro"] is True, r["conteudo"]
    assert "is closed" not in r["conteudo"], r["conteudo"]
    assert ("administrator" in r["conteudo"]
            or "administrador" in r["conteudo"]), r["conteudo"]


@pytest.mark.parametrize("consulta", [
    "SELECT titulo FROM aj_problemas WHERE titulo LIKE '%copy %'",
    "SELECT titulo FROM aj_problemas WHERE titulo ILIKE '%notify%'",
    "SELECT x.lo_x, x.pg_sleeper FROM (SELECT 1 AS lo_x, 2 AS pg_sleeper) AS x",
    "SELECT 'pg_sleep(1)' AS texto",
    "SELECT $$pg_read_file('postgresql.conf')$$ AS texto",
    "SELECT E'o \\'pg_terminate_backend(1)\\' é texto' AS texto",
])
def test_o_nome_de_funcao_dentro_de_literal_ou_de_coluna_nao_e_recusado(
        casa, consulta):
    """Item 8 da revisão do LX07: o filtro casava no texto inteiro e por
    prefixo, e recusava `LIKE '%copy %'` e a coluna `lo_x`. Conta agora a
    CHAMADA, fora do literal."""
    r = FER.executar(_ctx(casa), "consultar_banco", {"consulta": consulta})
    assert r["erro"] is False, r["conteudo"]


@pytest.mark.parametrize("consulta, nome", [
    # a chamada continua sendo chamada com espaço, schema ou aspas
    ("SELECT pg_catalog.pg_sleep (1)", "pg_sleep"),
    ('SELECT "pg_sleep"(1)', "pg_sleep"),
    ("SELECT lo_export(1, '/tmp/agente.txt')", "lo_export"),
    # e o literal que esconderia a chamada, se a fronteira dele saísse errada
    ("SELECT E'\\'' AS a, pg_advisory_lock(1)", "pg_advisory_lock"),
    ("SELECT 'a''b' AS a, pg_advisory_lock(1)", "pg_advisory_lock"),
    ("SELECT $x$ ' $x$ AS a, pg_advisory_lock(1)", "pg_advisory_lock"),
])
def test_a_chamada_ao_servidor_fora_do_literal_continua_recusada(
        casa, consulta, nome):
    """A recusa diz o nome que a consulta escreveu (`lo_export`), e não o
    começo da lista (`lo_`), que não dizia nada ao modelo."""
    r = FER.executar(_ctx(casa), "consultar_banco", {"consulta": consulta})
    assert r["erro"] is True, r["conteudo"]
    assert "do servidor e não do banco" in r["conteudo"]
    assert f"usa {nome}" in r["conteudo"]


@pytest.mark.parametrize("consulta", [
    "SELECT pg_notify('canal_do_agente', 'oi')",
    "SELECT pg_stat_reset()",
    "SELECT pg_stat_reset_shared('bgwriter')",
    "SELECT pg_rotate_logfile()",
    "SELECT pg_log_backend_memory_contexts(pg_backend_pid())",
    "SELECT pg_export_snapshot()",
    "SELECT 1 AS um FROM (NOTIFY canal_do_agente) AS x",
    "SELECT 1 AS um FROM (LISTEN canal_do_agente) AS x",
])
def test_a_funcao_com_efeito_fora_do_banco_e_recusada_pelo_texto(casa, consulta):
    """Item 9 da revisão do LX07: o aviso a quem escuta, a estatística do
    servidor, o log e a fotografia da transação não são ler o banco."""
    r = FER.executar(_ctx(casa), "consultar_banco", {"consulta": consulta})
    assert r["erro"] is True, r["conteudo"]
    assert "do servidor e não do banco" in r["conteudo"]


def test_o_aviso_que_passasse_pelo_texto_morre_no_rollback(casa, monkeypatch):
    """O NOTIFY só sai no COMMIT, e a leitura do agente termina sempre em
    ROLLBACK: mesmo sem a recusa pelo texto, quem escuta não recebe nada."""
    escuta = psycopg.connect(banco_pg.dsn(), autocommit=True)
    try:
        escuta.execute("LISTEN canal_do_agente_lx10")
        monkeypatch.setattr(FER, "_do_servidor", lambda baixo: [])
        r = FER.executar(_ctx(casa), "consultar_banco", {
            "consulta": "SELECT pg_notify('canal_do_agente_lx10', 'oi') AS n"})
        assert r["erro"] is False, r["conteudo"]
        assert list(escuta.notifies(timeout=0.5)) == []
    finally:
        escuta.close()


def test_a_consulta_de_milhoes_de_linhas_traz_so_o_limite(casa, monkeypatch):
    """Item 10 da revisão do LX07: o cursor comum trazia o resultado inteiro
    antes de a tela cortar. Este produto cartesiano tem 10¹⁰ linhas; com o
    cursor do servidor, as primeiras chegam muito antes do prazo, e a que
    sobra diz que há mais."""
    monkeypatch.setattr(FER, "PRAZO_DA_CONSULTA_MS", 3000)
    r = FER.executar(_ctx(casa), "consultar_banco", {"consulta": (
        "SELECT a.n AS a, b.n AS b FROM generate_series(1, 100000) AS a(n), "
        "generate_series(1, 100000) AS b(n)"), "limite": 3})
    assert r["erro"] is False, r["conteudo"]
    linhas = r["conteudo"].splitlines()
    assert linhas[0] == "a | b"
    assert len(linhas) == 5, linhas
    assert linhas[-1] == "(parei em 3 linhas; há mais)"


def test_a_consulta_que_cabe_no_limite_nao_diz_que_ha_mais(casa):
    """Com exatamente `limite` linhas, não há mais: a linha que sobra é a que
    diz, e antes a tela dizia «há mais» só por ter chegado ao limite."""
    r = FER.executar(_ctx(casa), "consultar_banco", {"consulta": (
        "SELECT g.n AS n FROM generate_series(1, 3) AS g(n) ORDER BY g.n"),
        "limite": 3})
    assert r["erro"] is False, r["conteudo"]
    assert r["conteudo"].splitlines() == ["n", "1", "2", "3"]
