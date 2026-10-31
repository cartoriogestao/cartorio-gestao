"""
Testes da amarracao do ato — custas calculadas e selo conferido.

O QUE ELES CONFEREM
    A regra, e nao "a funcao devolveu alguma coisa":

      - ato NAO LIBERADO nao se sela. O acervo tem dois assim, e selo de ato
        que o Tribunal nao reconhece nao sai;
      - selo de OUTRA serventia e recusado — CNS conferido contra o da casa;
      - selo REPETIDO e recusado, e a mensagem diz em que ato ele ja esta. Um
        selo serve a um ato so, e usar duas vezes e o que a inspecao aponta;
        a recusa fica na auditoria, e o mesmo selo no MESMO ato nao e recusa
        — e o formulario enviado duas vezes (LD14);
      - codigo torto e recusado na digitacao, e nao na inspecao;
      - so tabela de ATO recebe selo — escrever em tabela qualquer seria
        gravar em qualquer lugar;
      - `atos_sem_selo` acha o ato que ficou sem selo, que e o defeito dos
        cinco atos de 18/08/2026.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.lento  # gate rapido: pytest -m "not lento" — suite larga de dominio
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402
from protocolo_de_teste import cobrir_o_ato  # noqa: E402

import ato_selado as AS                            # noqa: E402
from nucleo_schema import init_nucleo_schema       # noqa: E402
from pt_schema import init_pt_schema               # noqa: E402
from selador_config import init_selador_schema     # noqa: E402

AGORA = "2026-08-24T09:00:00"
CNS = "000000"
# Selos reais desta serventia, dos atos de 18/08/2026.
SELO_BOM = "AVESVD000000NARRKWVNJCRSVO21"
SELO_OUTRO = "REGAVD000000OD1Q8BV5TOOZE492"
# Mesmo formato, CNS de outra casa.
SELO_DE_FORA = "AVESVD999999NARRKWVNJCRSVO21"


def banco() -> sqlite3.Connection:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    init_nucleo_schema(con)
    init_pt_schema(con)
    init_selador_schema(con)
    con.execute(
        """INSERT INTO pt_titulos(especie, numero_titulo, situacao, origem,
               criado_em)
           VALUES ('DMI','84713/1','APONTADO','MANUAL',?)""", (AGORA,))
    con.execute(
        """INSERT INTO pt_atos(titulo_id, tipo, data_ato, origem, criado_em)
           VALUES (1,'APONTAMENTO',?, 'MANUAL',?)""", (AGORA, AGORA))
    return con


def _registrar(con, numero=SELO_BOM, ato_id=1):
    return AS.registrar_selo_obtido_a_mao(
        con, numero, tabela="pt_atos", ato_id=ato_id, atribuicao="PROTESTO",
        agora=AGORA, cns=CNS, usuario="TESTE")


# ------------------------------------------------------------- o catalogo


def test_o_ato_do_catalogo_e_devolvido_com_o_nome():
    ato = AS.conferir_ato(110)          # Registro de Protesto de Título
    assert ato["atribuicao"] == 2
    assert "Protesto" in ato["nome"]


def test_ato_fora_do_catalogo_e_recusado():
    with pytest.raises(AS.AtoError, match="não está no catálogo"):
        AS.conferir_ato(99999)


def test_ato_nao_liberado_nao_se_sela():
    # 101 = Apostila de Haia no Protesto, marcada como não liberada no acervo.
    with pytest.raises(AS.AtoError, match="não está liberado"):
        AS.conferir_ato(101)


def test_codigo_de_ato_invalido_da_frase_de_balcao():
    with pytest.raises(AS.AtoError, match="inválido"):
        AS.conferir_ato("abacaxi")


# ---------------------------------------------------- o selo obtido a mao


def test_o_selo_tirado_no_portal_entra_amarrado_ao_ato():
    # E o caminho normal do Protesto e do RCPN nesta casa: os caminhos de selo
    # automatico observados no acervo sao TODOS de RTD/RCPJ.
    con = banco()
    r = _registrar(con)
    assert r["numero"] == SELO_BOM
    assert r["prefixo"] == "AVESVD"

    linha = con.execute("SELECT * FROM sd_selos WHERE numero=?",
                        (SELO_BOM,)).fetchone()
    assert linha["tabela"] == "pt_atos"
    assert linha["ato_id"] == 1
    assert linha["usado_em"] == AGORA           # ja nasce usado: o ato existe
    # e o ato aponta de volta para o selo
    assert con.execute("SELECT selo FROM pt_atos WHERE id=1").fetchone()[0] == SELO_BOM


def test_selo_de_outra_serventia_e_recusado():
    con = banco()
    with pytest.raises(AS.AtoError, match="não é desta serventia"):
        _registrar(con, SELO_DE_FORA)
    assert con.execute("SELECT COUNT(*) FROM sd_selos").fetchone()[0] == 0


def test_selo_repetido_e_recusado_e_diz_onde_ja_esta():
    # Um selo serve a um ato só. Usar duas vezes é o que a inspeção aponta.
    con = banco()
    _registrar(con)
    con.execute(
        """INSERT INTO pt_atos(titulo_id, tipo, data_ato, origem, criado_em)
           VALUES (1,'PROTESTO',?, 'MANUAL',?)""", (AGORA, AGORA))
    with pytest.raises(AS.AtoError, match="já está gravado"):
        _registrar(con, SELO_BOM, ato_id=2)


def test_codigo_torto_e_recusado_na_digitacao():
    con = banco()
    with pytest.raises(AS.AtoError, match="não tem forma de selo"):
        _registrar(con, "ISTO NAO E SELO")


def test_selo_em_branco_e_recusado():
    con = banco()
    with pytest.raises(AS.AtoError, match="Informe o número do selo"):
        _registrar(con, "   ")


def test_so_tabela_de_ato_recebe_selo():
    # Escrever selo em tabela que nao e de ato seria gravar em qualquer lugar.
    con = banco()
    with pytest.raises(AS.AtoError, match="não é tabela de ato"):
        AS.registrar_selo_obtido_a_mao(
            con, SELO_BOM, tabela="pt_titulos", ato_id=1,
            atribuicao="PROTESTO", agora=AGORA, cns=CNS)


def test_dois_selos_diferentes_no_mesmo_ato_convivem():
    # No protesto ha um selo POR ETAPA — o acervo tem coluna de selo para
    # apontamento, intimacao, protesto, certidao. Dois selos no mesmo ato nao
    # sao erro.
    con = banco()
    _registrar(con, SELO_BOM)
    _registrar(con, SELO_OUTRO)
    assert len(AS.selos_do_ato(con, "pt_atos", 1)) == 2


# ------------------------------- o numero que o razao ja tinha (LD14, 21/10)
#
# A IA do servidor achou, no ensaio de 21/10/2026, o razao descartando em
# silencio o selo de numero ja gravado. O digitado a mao recusava, mas sem
# rastro, recusava ate o mesmo selo no mesmo ato (o formulario enviado duas
# vezes), e dois balcoes com o mesmo selo davam HTTP 500 no segundo.


def _com_auditoria(con) -> None:
    """`audit_logs` como a do banco da casa, CONFIRMADA: a recusa a grava por
    uma conexao a parte, que so ve o que ja foi confirmado."""
    import bd_nativo
    bd_nativo.banco(con).escrever(
        """CREATE TABLE IF NOT EXISTS audit_logs (
               id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
               ts TEXT NOT NULL, user_id INTEGER, username_snapshot TEXT,
               action TEXT NOT NULL, entity_type TEXT, entity_id INTEGER,
               details TEXT, ip_address TEXT)""")
    con.commit()


def _auditoria(con) -> list[dict]:
    import bd_nativo
    return bd_nativo.banco(con).ler(
        "SELECT action, entity_type, details FROM audit_logs ORDER BY id")


def _segundo_ato(con) -> None:
    con.execute(
        """INSERT INTO pt_atos(titulo_id, tipo, data_ato, origem, criado_em)
           VALUES (1,'PROTESTO',?, 'MANUAL',?)""", (AGORA, AGORA))


def test_o_mesmo_selo_digitado_de_novo_no_mesmo_ato_nao_duplica_e_fica_registrado(
        caplog):
    con = banco()
    _com_auditoria(con)
    _registrar(con)
    with caplog.at_level(logging.WARNING, logger="selador_cliente"):
        r = _registrar(con)                 # o formulario enviado duas vezes
    assert r["numero"] == SELO_BOM
    assert con.execute("SELECT COUNT(*) FROM sd_selos").fetchone()[0] == 1
    auditoria = _auditoria(con)
    assert [(a["action"], a["entity_type"]) for a in auditoria] == [
        ("SELO_REPETIDO", "SD_SELO")]
    detalhes = json.loads(auditoria[0]["details"])
    assert detalhes["origem"] == "A_MAO"
    assert detalhes["gravado"]["tabela"] == "pt_atos"
    assert detalhes["gravado"]["ato_id"] == 1
    assert any(SELO_BOM in registro.getMessage() for registro in caplog.records)


def test_o_selo_de_outro_ato_e_recusado_com_auditoria_e_o_gravado_fica():
    con = banco()
    _com_auditoria(con)
    _segundo_ato(con)
    _registrar(con)                                         # ato 1
    con.commit()
    with pytest.raises(AS.AtoError) as erro:
        _registrar(con, SELO_BOM, ato_id=2)
    con.rollback()           # a tela desfaz a transacao do ato que nao selou
    assert "já está gravado no ato 1 de pt_atos" in str(erro.value)
    assert "a recusa ficou na auditoria" in str(erro.value)
    # O QUE ESTAVA GRAVADO FICOU COMO ESTAVA, e o ato 2 continua sem selo.
    linhas = con.execute("SELECT tabela, ato_id FROM sd_selos").fetchall()
    assert [(l["tabela"], l["ato_id"]) for l in linhas] == [("pt_atos", 1)]
    assert con.execute("SELECT selo FROM pt_atos WHERE id=2").fetchone()[0] is None
    # E A RECUSA FICOU, mesmo com a transacao desfeita: foi gravada por fora.
    auditoria = _auditoria(con)
    assert [a["action"] for a in auditoria] == ["SELO_REPETIDO_RECUSADO"]
    detalhes = json.loads(auditoria[0]["details"])
    assert detalhes["gravado"]["ato_id"] == 1
    assert detalhes["chegou"]["ato_id"] == 2
    assert detalhes["diferencas"] == {"ato_id": {"gravado": 1, "chegou": 2}}


def test_o_selo_cancelado_nao_volta_a_valer_digitado_de_novo_no_mesmo_ato():
    import selador_cliente as CL
    con = banco()
    _registrar(con)
    CL.registrar_cancelamento(con, SELO_BOM, motivo="selo colado no papel errado",
                              agora=AGORA)
    with pytest.raises(AS.AtoError, match=f"cancelado em {AGORA}"):
        _registrar(con)


def test_dois_balcoes_com_o_mesmo_selo_o_segundo_ouve_onde_ele_esta():
    """O `SELECT` antes e o `INSERT` depois deixavam os dois balcoes passarem
    pelo «ainda nao existe»: o segundo estourava o UNIQUE (IntegrityError,
    HTTP 500) em vez de ouvir em que ato o selo ja estava."""
    import threading
    con = banco()
    _com_auditoria(con)
    _segundo_ato(con)
    con.commit()
    outro = sqlite3.connect(str(con.db_path))
    _registrar(con)              # o primeiro balcao gravou e nao confirmou
    resultado: dict = {}

    def segundo_balcao():
        try:
            _registrar(outro, SELO_BOM, ato_id=2)
        except Exception as erro:                              # noqa: BLE001
            resultado["erro"] = erro
        finally:
            outro.rollback()

    fio = threading.Thread(target=segundo_balcao)
    fio.start()
    fio.join(0.5)                # o segundo esbarra no primeiro e espera
    con.commit()
    fio.join(20)
    outro.close()
    assert isinstance(resultado.get("erro"), AS.AtoError), resultado
    assert "já está gravado no ato 1 de pt_atos" in str(resultado["erro"])


# ------------------------------- o ambiente do selo digitado (LD14, 21/10)


def _selador_em(con, ambiente: str) -> None:
    import selador_config as SC
    SC.gravar(con, base_url="https://selador.exemplo.invalid",
              base_homologacao="https://homologacao.exemplo.invalid",
              ambiente=ambiente, agora=AGORA)


def _ambiente_gravado(con) -> str:
    return con.execute("SELECT ambiente FROM sd_selos WHERE numero=?",
                       (SELO_BOM,)).fetchone()[0]


def test_o_selo_a_mao_com_o_selador_em_homologacao_sai_HOMOLOGACAO():
    """`_ambiente_do_selo` chamava `SC.estado`, que nao existe: o `except`
    engolia e o selo a mao saia PRODUCAO sempre — tambem em homologacao."""
    con = banco()
    _selador_em(con, "HOMOLOGACAO")
    _registrar(con)
    assert _ambiente_gravado(con) == "HOMOLOGACAO"


def test_o_selo_a_mao_com_o_selador_em_producao_sai_PRODUCAO():
    con = banco()
    _selador_em(con, "PRODUCAO")
    _registrar(con)
    assert _ambiente_gravado(con) == "PRODUCAO"


def test_sem_configuracao_do_selador_o_selo_a_mao_sai_PRODUCAO_e_o_log_diz(caplog):
    con = banco()
    with caplog.at_level(logging.WARNING, logger="ato_selado"):
        _registrar(con)
    assert _ambiente_gravado(con) == "PRODUCAO"
    assert any("sem configuracao" in r.getMessage() for r in caplog.records)


def test_o_ambiente_do_selo_nao_engole_a_funcao_que_nao_existe(monkeypatch):
    """Erro de programacao sobe: so a falta de configuracao cai no padrao."""
    import selador_config as SC
    con = banco()
    _selador_em(con, "HOMOLOGACAO")
    monkeypatch.delattr(SC, "_linha")
    with pytest.raises(AttributeError):
        _registrar(con)


def test_todo_nome_que_o_selo_pede_a_outro_modulo_existe_nele():
    """`SC.estado` nao existia e ninguem viu: a chamada morava dentro de um
    `except Exception`. Aqui cada `APELIDO.nome` e cada `from x import y` de
    `ato_selado` e `selador_cliente` e conferido contra o modulo de verdade —
    inclusive os importados dentro de funcao, que so estouram na hora do uso."""
    import ast
    import importlib
    import importlib.util

    def existe(modulo: str, nome: str) -> bool:
        if hasattr(importlib.import_module(modulo), nome):
            return True
        try:                     # `from pacote import submodulo`
            return importlib.util.find_spec(f"{modulo}.{nome}") is not None
        except ModuleNotFoundError:
            return False

    raiz = Path(__file__).resolve().parent.parent
    faltam, conferidos = [], 0
    for arquivo in ("ato_selado.py", "selador_cliente.py"):
        arvore = ast.parse((raiz / arquivo).read_text(encoding="utf-8"))
        apelidos: dict[str, str] = {}
        pedidos: set[tuple[str, str]] = set()
        for no in ast.walk(arvore):
            if isinstance(no, ast.Import):
                for a in no.names:
                    apelidos[a.asname or a.name] = a.name
            elif (isinstance(no, ast.ImportFrom) and no.level == 0
                  and no.module and no.module != "__future__"):
                pedidos |= {(no.module, a.name) for a in no.names}
        pedidos |= {(apelidos[no.value.id], no.attr) for no in ast.walk(arvore)
                    if isinstance(no, ast.Attribute)
                    and isinstance(no.value, ast.Name)
                    and no.value.id in apelidos
                    and not isinstance(no.ctx, ast.Store)}
        for modulo, nome in sorted(pedidos):
            conferidos += 1
            if not existe(modulo, nome):
                faltam.append(f"{arquivo}: {modulo}.{nome}")
    assert conferidos > 50, f"o varredor conferiu so {conferidos} nomes"
    assert faltam == [], f"chamados e inexistentes: {faltam}"


# ------------------------------------------------------------ conferencia


def test_atos_sem_selo_acha_o_que_ficou_para_tras():
    # E o defeito dos cinco atos de 18/08/2026: o selo foi colado como imagem
    # e nunca entrou no banco.
    con = banco()
    assert len(AS.atos_sem_selo(con, "pt_atos")) == 1
    _registrar(con)
    assert AS.atos_sem_selo(con, "pt_atos") == []


def test_atos_sem_selo_recusa_tabela_que_nao_e_de_ato():
    con = banco()
    with pytest.raises(AS.AtoError, match="não é tabela de ato"):
        AS.atos_sem_selo(con, "sqlite_master")


# ---------------------------------------------------------------- custas


def test_custas_de_servico_que_nao_esta_na_tabela_da_frase_de_balcao():
    # A tabela de emolumentos nao foi importada neste banco de teste: o erro
    # tem de dizer o que fazer, e nao o nome da funcao que falhou.
    con = banco()
    from caixa_schema import init_caixa_schema
    # `caixa_schema` referencia `users`; no banco de verdade ela vem antes.
    con.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY)")
    # `cx_protocolos` aponta para a prenotacao e a matricula do RI: o
    # PostgreSQL cobra a FK, e o banco da casa cria as duas antes.
    con.execute("CREATE TABLE IF NOT EXISTS ri_protocolos (id INTEGER PRIMARY KEY)")
    con.execute("CREATE TABLE IF NOT EXISTS ri_matriculas (id INTEGER PRIMARY KEY)")
    init_caixa_schema(con)
    with pytest.raises(AS.AtoError) as erro:
        AS.calcular_custas(con, servico=999999, data="2026-08-24")
    assert "tabela" in str(erro.value).lower()


# --------------------------------------------- o selo pedido ao aparelho
#
# Contra o selador de mentira com TLS de verdade, o mesmo de
# `test_selador_cliente.py`. O que se prova aqui nao e o transporte — aquele
# ja tem 27 testes — e sim a ORDEM: o pedido acontece FORA da transacao do
# ato, e o vinculo acontece dentro dela, depois de o ato existir.


def _tem_cryptography() -> bool:
    try:
        import cryptography              # noqa: F401
    except ImportError:
        return False
    return True


class _DbDeMentira:
    """O minimo que `obter_selo` usa de `db`: uma transacao propria e uma
    conexao sem transacao — a do pedido ao aparelho (LX21a), que nao conta
    como transacao: e justamente a que nao pode segurar trava nenhuma."""

    def __init__(self, con):
        self.con = con
        self.transacoes = 0

    def transaction(self):
        from contextlib import contextmanager

        @contextmanager
        def _abrir():
            self.transacoes += 1
            yield self.con

        return _abrir()

    def connect(self):
        return self.con


@pytest.mark.skipif(not _tem_cryptography(),
                    reason="o selador de mentira precisa de `cryptography`")
def test_o_selo_e_pedido_fora_da_transacao_do_ato_e_vinculado_dentro(tmp_path):
    import selador_cliente as CL
    import selador_config as SC
    from selador_falso import SeladorFalso, impressao_digital

    con = banco()
    # LX16: selo pago só sai com protocolo pago — o teste monta o do balcão.
    cobrir_o_ato(con, tabela="rg_atos", ato_id=1)
    SC.gravar_credencial(tmp_path, "fulano.detal123", "abcde123", agora=AGORA)
    CL.esquecer_tokens()

    with SeladorFalso() as s:
        SC.gravar(con, base_url=s.base, usuario="fulano.detal123", agora=AGORA)
        CL.fixar_certificado(con, s.base, sha256=impressao_digital(),
                             agora=AGORA, usuario="TESTE")
        db = _DbDeMentira(con)
        selos = AS.obter_selo(db, tmp_path, caminho="/selo/rtdpj/atos-em-geral",
                              dados={"quantidade": 1}, referencia="rg_atos:1",
                              atribuicao="rtd", agora=AGORA, cns=CNS,
                              usuario="TESTE")

    assert selos, "o selador de mentira não devolveu selo"
    # A transacao foi ABERTA POR `obter_selo`, e nao pela do ato: e o que
    # impede a chamada de rede de segurar a trava de escrita da casa.
    assert db.transacoes == 1

    # O selo ja esta no razao, e ainda SEM ato — e assim que ele apareceria na
    # tela de "selo obtido e nao usado" se o ato falhasse agora.
    numero = selos[0].numero
    linha = con.execute("SELECT * FROM sd_selos WHERE numero=?",
                        (numero,)).fetchone()
    assert linha["tabela"] is None and linha["ato_id"] is None

    # Agora o ato existe, e o vinculo entra na transacao dele.
    AS.vincular_ao_ato(con, numero, tabela="pt_atos", ato_id=1,
                       agora="2026-08-27T10:00:00")
    linha = con.execute("SELECT * FROM sd_selos WHERE numero=?",
                        (numero,)).fetchone()
    assert linha["tabela"] == "pt_atos" and linha["ato_id"] == 1
    assert con.execute("SELECT selo FROM pt_atos WHERE id=1").fetchone()[0] == numero


def test_vincular_recusa_tabela_que_nao_e_de_ato():
    con = banco()
    with pytest.raises(AS.AtoError, match="não é tabela de ato"):
        AS.vincular_ao_ato(con, SELO_BOM, tabela="pt_titulos", ato_id=1,
                           agora="2026-08-27T10:00:00")


# ------------------------------------------ a receita de custas do ato


def _com_tabela(con):
    """Acrescenta a tabela de emolumentos, com dois serviços de mentira."""
    from caixa_schema import init_caixa_schema
    con.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY)")
    # `cx_protocolos` aponta para a prenotacao e a matricula do RI: o
    # PostgreSQL cobra a FK, e o banco da casa cria as duas antes.
    con.execute("CREATE TABLE IF NOT EXISTS ri_protocolos (id INTEGER PRIMARY KEY)")
    con.execute("CREATE TABLE IF NOT EXISTS ri_matriculas (id INTEGER PRIMARY KEY)")
    init_caixa_schema(con)
    con.execute("""INSERT INTO cx_vigencias(codigo, descricao, vigente)
                   VALUES (1, '2026', 1)""")
    # 17.2 tem preço; 17.4 é linha de cabeçalho, com subitem por faixa.
    for cod, tj, desc in ((1, "17.2", "Intimação por título"),
                          (2, "17.4", "Quando ocorrer a liquidação:"),
                          (3, "17.4.3", "de R$ 1 a R$ 100"),
                          (4, "17.10.1", "Diligência"),
                          (5, "17.5.1", "Certidão de uma folha")):
        con.execute("""INSERT INTO cx_servicos(codigo, codigo_tj, descricao)
                       VALUES (?,?,?)""", (cod, tj, desc))
    for cod, total in ((1, "10,68"), (2, "0,00"), (3, "25,00"),
                       (4, "26,25"), (5, "53,58")):
        con.execute("""INSERT INTO cx_servico_valores(servico, vigencia,
                           emolumentos, ferc, femp, fadep, ferrfis, total)
                       VALUES (?,1,?, '0,00','0,00','0,00','0,00', ?)""",
                    (cod, total, total))
    return con


def test_o_caminho_do_ato_sai_do_nome_do_endpoint():
    # Não é adivinhação: o endpoint que a casa usou diz o ato.
    assert AS.caminho_do_ato("pt_atos", "PAGAMENTO") == "/selo/protesto/pagamento"
    assert AS.caminho_do_ato("pt_atos", "CANCELAMENTO") == \
        "/selo/protesto/baixa-cancelamento"
    assert AS.caminho_do_ato("pt_atos", "pagamento") == "/selo/protesto/pagamento"
    assert AS.caminho_do_ato("pt_atos", "INVENTADO") is None


def test_a_receita_traz_os_itens_que_a_casa_cobrou_com_preco():
    con = _com_tabela(banco())
    r = AS.receita_de_custas(con, "/selo/protesto/pagamento")
    codigos = [i["codigo_tj"] for i in r["itens"]]
    # Medidos: 17.2, 17.4, 17.10.1 e 17.5.1 — em ordem de frequência.
    assert codigos == ["17.2", "17.4", "17.10.1", "17.5.1"]
    assert r["itens"][0]["preco"] == 1068
    assert r["itens"][0]["vezes"] == 163


def test_item_de_cabecalho_nao_e_item_de_graca():
    # 17.4 vale 0,00 na tabela porque o preço está nos subitens, por faixa de
    # valor do título. Mostrar "R$ 0,00" faria o balcão cobrar zero por ato
    # que custa — são 151 dos 1.317 serviços com total zerado.
    con = _com_tabela(banco())
    r = AS.receita_de_custas(con, "/selo/protesto/pagamento")
    dezessete_quatro = next(i for i in r["itens"] if i["codigo_tj"] == "17.4")
    assert dezessete_quatro["preco"] is None
    assert dezessete_quatro["por_faixa"] is True
    assert "depende do valor" in dezessete_quatro["motivo"]
    assert r["por_faixa"] == ["17.4"]
    # e ele NÃO entra no total, que soma só o que tem preço
    assert r["total_centavos"] == 1068 + 2625 + 5358


def test_item_que_nao_esta_na_tabela_entra_com_o_motivo_e_nao_some():
    # Sumir seria cobrar a menos sem ninguém ver.
    con = banco()
    from caixa_schema import init_caixa_schema
    con.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY)")
    # `cx_protocolos` aponta para a prenotacao e a matricula do RI: o
    # PostgreSQL cobra a FK, e o banco da casa cria as duas antes.
    con.execute("CREATE TABLE IF NOT EXISTS ri_protocolos (id INTEGER PRIMARY KEY)")
    con.execute("CREATE TABLE IF NOT EXISTS ri_matriculas (id INTEGER PRIMARY KEY)")
    init_caixa_schema(con)
    r = AS.receita_de_custas(con, "/selo/protesto/pagamento")
    assert len(r["itens"]) == 4
    assert all(i["preco"] is None for i in r["itens"])
    assert set(r["sem_preco"]) == {"17.2", "17.4", "17.10.1", "17.5.1"}


def test_o_rcpn_nao_tem_receita_medida_e_isso_e_o_fato():
    # A casa selou 1.238 atos por `/selo/civil/atos-em-geral` e mandou o
    # `codigoAto` VAZIO em todos. Não há o que medir — e devolver vazio é
    # dizer a verdade, não falhar.
    con = _com_tabela(banco())
    r = AS.receita_de_custas(con, AS.caminho_do_ato("rc_atos", "AVERBACAO"))
    assert r["itens"] == []
    assert r["total_centavos"] == 0


def test_servico_do_codigo_tj_acha_e_nao_inventa():
    con = _com_tabela(banco())
    assert AS.servico_do_codigo_tj(con, "17.2")["codigo"] == 1
    assert AS.servico_do_codigo_tj(con, "99.9") is None


# -------------------------------------------- a cobrança no caixa


def test_cobrar_lanca_no_caixa_e_amarra_ao_ato():
    # Fecha o ciclo do dinheiro: até aqui o ato lavrava e o preço aparecia,
    # mas nada era cobrado — e cartório que lavra sem lançar não fecha o caixa.
    con = _com_tabela(banco())
    r = AS.cobrar(con, tabela="pt_atos", ato_id=1, servico=1, agora=AGORA,
                  hoje="2026-08-24", hora="09:00", pagador="MARIA")
    assert r["total_centavos"] == 1068
    linha = con.execute("SELECT * FROM cx_lancamentos WHERE id=?",
                        (r["lancamento_id"],)).fetchone()
    assert linha["natureza"] == "RECEBIMENTO"
    assert linha["sentido"] == "ENTRADA"
    assert linha["valor"] == "10,68"
    assert linha["origem"] == "ATO"
    assert linha["origem_chave"] == "pt_atos:1:1"
    # e o ato aponta de volta para o lançamento
    assert con.execute("SELECT lancamento_id FROM pt_atos WHERE id=1"
                       ).fetchone()[0] == r["lancamento_id"]


def test_os_fundos_vao_separados_para_a_linha_do_caixa():
    # É o que faz o relatório da COGEX fechar sem ninguém recompor à mão.
    con = _com_tabela(banco())
    r = AS.cobrar(con, tabela="pt_atos", ato_id=1, servico=1, agora=AGORA,
                  hoje="2026-08-24", hora="09:00")
    linha = con.execute("SELECT * FROM cx_lancamentos WHERE id=?",
                        (r["lancamento_id"],)).fetchone()
    assert linha["emolumentos"] == "10,68"     # o serviço de teste é só emolumento
    for fundo in ("ferc", "fadep", "femp", "ferrfis"):
        assert linha[fundo] is not None


def test_nao_se_cobra_duas_vezes_o_mesmo_item_do_mesmo_ato():
    # É o erro que o cliente descobre no extrato.
    con = _com_tabela(banco())
    AS.cobrar(con, tabela="pt_atos", ato_id=1, servico=1, agora=AGORA,
              hoje="2026-08-24", hora="09:00")
    with pytest.raises(AS.AtoError, match="já foi lançado no caixa"):
        AS.cobrar(con, tabela="pt_atos", ato_id=1, servico=1, agora=AGORA,
                  hoje="2026-08-24", hora="09:00")


def test_o_mesmo_ato_cobra_varios_itens():
    # No protesto há um selo e uma custa POR ETAPA: 17.2, 17.10.1 e 17.5.1
    # saem juntos no mesmo ato.
    con = _com_tabela(banco())
    for servico in (1, 4, 5):
        AS.cobrar(con, tabela="pt_atos", ato_id=1, servico=servico,
                  agora=AGORA, hoje="2026-08-24", hora="09:00")
    lancados = AS.lancamentos_do_ato(con, "pt_atos", 1)
    assert len(lancados) == 3
    assert sum(int(x["valor"].replace(",", "")) for x in lancados) > 0


def test_cobrar_recusa_tabela_que_nao_e_de_ato():
    con = _com_tabela(banco())
    with pytest.raises(AS.AtoError, match="não é tabela de ato"):
        AS.cobrar(con, tabela="cx_lancamentos", ato_id=1, servico=1,
                  agora=AGORA, hoje="2026-08-24", hora="09:00")


def test_servico_que_nao_esta_na_tabela_nao_lanca_nada():
    # Se a conta não fecha, não entra linha no caixa — meia cobrança é pior
    # que nenhuma.
    con = _com_tabela(banco())
    with pytest.raises(AS.AtoError):
        AS.cobrar(con, tabela="pt_atos", ato_id=1, servico=999999,
                  agora=AGORA, hoje="2026-08-24", hora="09:00")
    assert con.execute("SELECT COUNT(*) FROM cx_lancamentos").fetchone()[0] == 0


def test_obter_selo_abre_transacao_propria_e_nao_usa_a_do_ato(monkeypatch):
    # ESTA e a decisao que o modulo existe para guardar, e ela roda em
    # qualquer maquina — sem TLS, sem `cryptography`.
    #
    # `db.transaction()` e BEGIN IMMEDIATE: um escritor por vez. A chamada ao
    # selador tem prazo de 20 segundos. Se o pedido acontecesse dentro da
    # transacao do ato, todo outro balcao ficaria no `busy_timeout` — o mesmo
    # defeito que a tela de leitura que consumia contador ja causou aqui.
    import selador_cliente as CL

    con = banco()
    db = _DbDeMentira(con)
    vistos = {}

    def falso_selar(recebido, *a, **kw):
        vistos["con"] = recebido
        vistos["transacoes_ate_aqui"] = db.transacoes
        return []

    monkeypatch.setattr(CL, "selar", falso_selar)
    # LX16: selo pago só sai com protocolo pago — o teste monta o do balcão.
    cobrir_o_ato(con, tabela="rg_atos", ato_id=1)
    # O escrevente é humano e vem informado: desde 21/09/2026 (REGNAS...KM25)
    # `obter_selo` recusa selar sem gente, e este banco de mentira não tem
    # cadastro de onde tirar um nome.
    AS.obter_selo(db, "/tmp", caminho="/selo/rtdpj/atos-em-geral", dados={},
                  referencia="rg_atos:1", atribuicao="rtd", agora=AGORA,
                  cns=CNS, usuario="ESCREVENTE DE TESTE")

    # Abriu UMA transacao, e foi a dela — a conexao que chegou em `selar` e a
    # que `obter_selo` pediu, e nao uma que o chamador ja tivesse aberto.
    assert db.transacoes == 1
    assert vistos["transacoes_ate_aqui"] == 1
    assert vistos["con"] is con


# ------------------------------------- toda tela que sela, sela numa tabela


def _argumentos_da_chamada(texto: str, comeco: int) -> str:
    r"""O que esta DENTRO dos parenteses da chamada, inteiro.

    **PARENTESES SE CONTAM, NAO SE CASAM.** A primeira versao deste guarda
    usava `selar_o_ato_lavrado\((.*?)\)` e parava no primeiro `)` — que e
    o de `Path(app.config["DATA_DIR"])`, o segundo argumento. Ele lia a
    chamada pela metade e acusava **as seis** telas de nao passar envelope,
    estando as seis certas.

    E a mesma familia do varredor que bateu no `DO UPDATE SET` e na prosa
    dos comentarios: **regex que nao entende a estrutura acusa o inocente.**

    Virou funcao de modulo em 15/09/2026 porque o varredor de
    `_tabelas_que_as_telas_selam` passou a precisar da mesma leitura — e duas
    reguas para a mesma pergunta divergem no primeiro conserto.
    """
    i = texto.index("(", comeco)
    nivel, fim = 0, i
    for fim in range(i, len(texto)):
        if texto[fim] == "(":
            nivel += 1
        elif texto[fim] == ")":
            nivel -= 1
            if nivel == 0:
                break
    return texto[i:fim + 1]


def _tabelas_que_as_telas_selam() -> dict[str, list[str]]:
    """Le o CODIGO das telas e diz em que tabela cada uma manda selar.

    Ler o codigo em vez de exercitar cada rota e o mesmo caminho de
    `tests/test_portabilidade.py`, e pelo mesmo motivo: a pergunta e sobre
    TODAS as chamadas, inclusive as que nenhum teste de tela cobre hoje.

    O QUE ELE NAO COBRE, dito na cara: as chamadas de `ri_web.py` e
    `notas_web.py` tem outra forma e nao caem nesta expressao. As duas
    atribuicoes antigas selam por caminho proprio, anterior a `ato_selado`.
    O varredor cobre as quatro atribuicoes NOVAS, que sao as que usam este
    modulo — e e ali que uma tela nova vai nascer.
    """
    import re

    # **A EXPRESSAO PEGA O ARGUMENTO DA TABELA, E NAO QUALQUER ASPAS DEPOIS DA
    # CHAMADA** — corrigido em 14/09/2026.
    #
    #   A anterior era `[^)]*?["\'](...)["\']`, que varria ate achar a primeira
    #   palavra_com_underline entre aspas em qualquer lugar da chamada. Ela
    #   acusou DUAS tabelas que nao existem:
    #
    #     cobrar(con, tabela=tabela, ato_id=ato_id, servico=int(linha["servico_codigo"]))
    #     _selar_se_pedido(con, feito["ato_id"], ...)
    #
    #   `servico_codigo` e `ato_id` sao CHAVES DE DICIONARIO, e o teste as
    #   cobrava como se fossem tabela de ato. **Regua que erra acusa quem esta
    #   certo** — e este projeto ja aprendeu isso onze vezes, sempre pelo mesmo
    #   caminho: o varredor conta a palavra em vez de ler a chamada.
    #
    #   Agora so conta o que de fato nomeia a tabela: o literal na PRIMEIRA
    #   posicao depois de `db`/`con`, ou o `tabela="..."` nomeado. Tabela
    #   passada em VARIAVEL (`tabela=tabela`) nao e capturada — e nao pode ser:
    #   dali o teste nao tem como saber qual e.
    raiz = Path(__file__).resolve().parent.parent
    achados: dict[str, list[str]] = {}
    for arquivo in sorted(raiz.glob("*_web.py")):
        texto = arquivo.read_text(encoding="utf-8")
        for funcao in ("_selar_se_pedido", "registrar_selo_obtido_a_mao",
                       "cobrar"):
            for posicional, nomeada in re.findall(
                    rf'{funcao}\(\s*(?:db|con)\s*,\s*(?:["\']([a-z]+_[a-z_]+)["\']'
                    rf'|tabela\s*=\s*["\']([a-z]+_[a-z_]+)["\'])',
                    texto):
                tabela = posicional or nomeada
                achados.setdefault(tabela, []).append(arquivo.name)

        # **E A QUARTA FUNCAO — ACRESCENTADA EM 15/09/2026, E ELA FALTAVA.**
        #
        #   `selar_o_ato_lavrado` e a porta por onde selam as telas do RI, das
        #   Notas e do civil, e ela nao estava em nenhuma das tres expressoes
        #   acima. O buraco era conhecido e estava declarado no docstring
        #   («as chamadas de `ri_web.py` e `notas_web.py` tem outra forma»).
        #
        #   `nt_sinais_reconhecimentos` caiu exatamente nele: reconhecimento
        #   autonomo de sinal publico, selado pelo item 413, e **fora de
        #   `TABELAS_DE_ATO`** — de modo que o selo saia, fosse pago, e o
        #   `vincular_ao_ato` o recusasse depois. Achado pelo SANDBOX, no
        #   primeiro caso de uso que exercitou o ato inteiro.
        #
        #   Aqui a leitura e por PARENTESES CONTADOS — a mesma funcao que o
        #   guarda do envelope usa —, e nao por regex ate o primeiro `)`:
        #   estas chamadas levam `Path(app.config["DATA_DIR"])` no meio.
        procura = 0
        while True:
            onde = texto.find("selar_o_ato_lavrado(", procura)
            if onde < 0:
                break
            procura = onde + 1
            for tabela in re.findall(
                    r'tabela\s*=\s*["\']([a-z]+_[a-z_]+)["\']',
                    _argumentos_da_chamada(texto, onde)):
                achados.setdefault(tabela, []).append(arquivo.name)
    return achados


def test_toda_tabela_que_as_telas_selam_esta_registrada():
    """UMA TABELA NAO REGISTRADA NAO DA ERRO DE PROGRAMACAO: DA ATO PERDIDO.

    Foi o que aconteceu com `rc_certidoes` em 26/08/2026. Sem ela em
    `TABELAS_DE_ATO`, `registrar_selo_obtido_a_mao` recusava com "nao e tabela
    de ato" — e a rota, fazendo o que a casa manda (selo recusado derruba o
    lancamento inteiro), desfazia a transacao.

    O escrevente que digitasse o selo emitia a certidao, via um aviso vermelho
    e A CERTIDAO SUMIA. Quem nao digitasse selo nunca veria nada — e por isso
    os dezoito primeiros testes de tela da certidao passavam: todos emitiam
    sem selo.

    Este teste pergunta pelo conjunto inteiro, e nao por uma tela de cada vez.
    """
    achados = _tabelas_que_as_telas_selam()
    # O PISO. Varredor que deixa de achar passa calado, e teste que nao olha
    # nada e pior que teste nenhum: ele da a impressao de que alguem conferiu.
    # Sao sete hoje, e o numero so pode subir.
    assert len(achados) >= 7, (
        f"o varredor achou so {len(achados)} tabela(s): {sorted(achados)}. "
        f"Ou uma tela sumiu, ou a forma de chamar mudou e a expressao "
        f"precisa acompanhar.")
    assert "rc_certidoes" in achados, (
        "a certidao do RCPN sumiu do varredor — foi ela que motivou o teste")
    # **A SEGUNDA QUE MOTIVOU UMA CORRECAO, e ela entrou por outro caminho.**
    # `nt_sinais_reconhecimentos` sela por `selar_o_ato_lavrado`, e nao pelas
    # tres funcoes que o varredor procurava: quando ele passou a ler as quatro,
    # achou esta tabela fora de `TABELAS_DE_ATO` — o que custava o SELO PAGO e
    # o ato sem selo. Achado pelo sandbox em 15/09/2026.
    assert "nt_sinais_reconhecimentos" in achados, (
        "o reconhecimento de sinal publico sumiu do varredor — foi ele que "
        "achou o buraco do `selar_o_ato_lavrado`")
    faltando = {tabela: telas for tabela, telas in achados.items()
                if tabela not in AS.TABELAS_DE_ATO}
    assert not faltando, (
        f"estas telas selam ou cobram numa tabela que nao esta em "
        f"TABELAS_DE_ATO, e o ato sera desfeito quando alguem digitar o "
        f"selo: {faltando}")


def _banco_inteiro() -> sqlite3.Connection:
    """O banco inteiro, e nao o minimo deste modulo.

    A pergunta e sobre as tabelas das SEIS atribuicoes, e `banco()` so monta o
    Protesto — quem responde sobre todas e o esquema de verdade, criado pelo
    `create_app` numa pasta temporaria.
    """
    import glob
    import tempfile

    from database import Database

    pasta = tempfile.mkdtemp()
    from app import create_app
    create_app({"DATA_DIR": pasta})
    caminho = glob.glob(f"{pasta}/*.sqlite3")[0]
    return Database(Path(caminho)).connect()


def test_toda_tabela_registrada_existe_no_banco():
    """Registrar tabela que nao existe faria o selo bater na chave estrangeira.

    E o mesmo defeito que o usucapiao teve: `registrar_reconhecimento` batia
    na FK e virava HTTP 500 no fim de um processo de meses.
    """
    con = _banco_inteiro()
    existem = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    con.close()
    assert set(AS.TABELAS_DE_ATO) <= existem, (
        f"registradas e inexistentes: "
        f"{sorted(set(AS.TABELAS_DE_ATO) - existem)}")


def test_toda_tabela_COM_FORMA_DE_ATO_esta_registrada():
    """**A PERGUNTA PELO LADO DO BANCO — 15/09/2026.**

    Os dois varredores acima leem o CODIGO das telas: eles acham a tabela que
    uma tela sela hoje. Este pergunta pelo ESQUEMA, e acha a que ninguem
    lembrou de registrar — que e o estado de `nt_sinais_reconhecimentos` ate
    hoje.

    **A FORMA DO ATO SAO DUAS COLUNAS**: `selo` (o numero do selo, em qualquer
    dos quatro nomes que o banco usa) e `lancamento_id` (o dinheiro, que vem do
    mesmo `cobrar()`). Tabela que tem as duas E ato, ainda que nenhuma tela a
    sele hoje — e no dia em que selar, o `vincular_ao_ato` a recusaria DEPOIS
    de o selo ter sido pago.

    Medido no esquema inteiro, em 15/09/2026 — e nas DUAS bases, a que o
    `create_app` cria e a da producao, para o piso nao valer so numa: **13
    tabelas** tem a forma; **12 sao atos** e a decima terceira esta declarada
    abaixo. A lista nao envelhece sozinha porque ela e lida do banco, e nao
    escrita aqui.

    **E A PRIMEIRA VERSAO DESTE TESTE ACUSOU A TABELA ERRADA — ele nasceu
    vermelho, e o vermelho estava certo.** A regua dizia «tem selo e
    `lancamento_id`, logo e ato», e `cx_protocolo_atos` tem as duas: e o
    **ITEM do protocolo**, que CARREGA o selo para o ato que ainda vai ser
    lavrado (`usado_por_ato_id` diz qual o consumiu) e o `lancamento_id` que a
    quitacao lanca no caixa. Registra-lo em `TABELAS_DE_ATO` faria
    `atos_sem_selo` acusar os **32.416 itens do acervo** para sempre — o alarme
    que soa sempre, que e como um alarme deixa de ser ouvido.

    A excecao **se declara**, na forma de `FORA_DA_VARREDURA` e de
    `DONOS_DO_PRAGMA`; e ela nao pode virar desculpa: o proprio teste cobra que
    a tabela declarada **tenha a marca de item que outro consome**. Sem essa
    conferencia, um nome na lista seria uma tabela de ato escondida da conta.
    """
    con = _banco_inteiro()
    nomes = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    colunas: dict[str, set[str]] = {
        nome: {r[1] for r in con.execute(f'PRAGMA table_info("{nome}")')}
        for nome in nomes}
    con.close()

    colunas_da_familia = {"selo", "selo_texto", "selo_abertura",
                          "selo_prenotacao"}
    com_forma = [nome for nome, cols in colunas.items()
                 if (cols & colunas_da_familia) and "lancamento_id" in cols]
    origem = [nome for nome in com_forma if nome not in AS.TABELAS_DE_ATO]

    # O PISO, na forma dos outros varredores deste arquivo: varredura que
    # deixou de achar passa calado, e um `PRAGMA` que parasse de responder
    # devolveria lista vazia — que e o mesmo que "tudo certo".
    assert len(com_forma) >= 13, (
        f"o varredor achou so {len(com_forma)} tabela(s) com forma de ato — "
        f"eram 13 em 15/09/2026, e o `PRAGMA` provavelmente parou de responder: "
        f"{com_forma}")

    # **A EXCECAO, DECLARADA COM A RAZAO AO LADO.** Ela nao e' uma lista de
    # nomes: e' nome -> motivo, e o motivo e' medido logo abaixo.
    nao_e_ato = {
        "cx_protocolo_atos": (
            "e' o ITEM do protocolo, e nao o ato: ele CARREGA o selo que o ato "
            "vai consumir (`usado_por_ato_id` / `usado_por_tabela`) e o "
            "`lancamento_id` que a quitacao lanca no caixa — quem sela de "
            "verdade e o ato que o consome"),
    }
    for nome, motivo in nao_e_ato.items():
        assert nome in colunas, (
            f"a excecao declarada `{nome}` nao existe mais no banco — lista que "
            f"envelhece esconde a proxima, e a razao dela era: {motivo}")
        assert {"usado_por_ato_id", "usado_por_tabela"} <= colunas[nome], (
            f"`{nome}` esta declarada fora da forma de ato e NAO tem a marca de "
            f"item que outro consome: o que sobra dela e' {sorted(colunas[nome])}"
            f" — sem a marca, ela e' uma tabela de ato escondida da conta, e a "
            f"razao declarada ({motivo}) deixou de valer")

    faltando = [nome for nome in origem if nome not in nao_e_ato]
    assert faltando == [], (
        f"estas tabelas tem selo e lancamento e NAO estao em TABELAS_DE_ATO — "
        f"no dia em que uma tela as selar, o selo sera pago e o ato ficara sem "
        f"ele: {faltando}")


# ================ O SELO SAI QUANDO O ATO E PRATICADO (27/08/2026)
#
# «O selo deve ser emitido quando praticado o ato. Igual o E-Oficio.» — a
# decisao do oficial. E o que o E-Oficio fazia: 26.123 selos em 34 caminhos,
# sem perguntar a ninguem.
#
# Ate aqui, `obter_selo` estava pronto e testado e NENHUMA TELA O CHAMAVA: a
# unica forma de selar era o escrevente digitar o numero a mao. E a quinta vez
# neste projeto que a mesma pergunta acha o mesmo defeito.


@pytest.mark.skipif(not _tem_cryptography(),
                    reason="o selador de mentira precisa de `cryptography`")
def test_o_ato_praticado_sai_selado_sem_ninguem_pedir(tmp_path):
    """O caminho inteiro: pede ao aparelho, grava no razao e amarra ao ato.

    **ESTE TESTE ESTAVA VERMELHO, E O DEFEITO ERA DELE.** Achado em 30/08/2026,
    ao rodar a suite inteira antes de empacotar a 3.6.47.

    Ele chamava `selar_o_ato_lavrado` **sem `dados`** e esperava selo. Sem
    envelope o contrato recusa antes de despachar — «o pedido veio sem dados» —,
    e recusar ali esta **certo**: pedido de selo sem corpo e o pedido que o
    aparelho responderia com qualquer coisa.

    **E o sistema nao estava quebrado**: as **seis** telas que selam montam o
    envelope e o passam (`dados=envelope`) — foi conferido uma a uma. Quem
    estava fora do caminho real era este teste, que por isso nao provava o que o
    nome dele promete.

    > **Teste que chama diferente da tela nao prova a tela.** E a licao dos 37
    > testes que remontavam pedidos do acervo e conferiam contra a minha propria
    > ideia do pedido: passavam todos, com o defeito de pe. Aqui foi ao
    > contrario — ele reprovava o codigo certo —, mas a causa e a mesma: o teste
    > exercitava um caminho que ninguem percorre.

    Agora ele monta o envelope **como `atribuicoes_web` monta**, e volta a
    provar o caminho inteiro.
    """
    import selador_cliente as CL
    import selador_config as SC
    from selador_falso import SeladorFalso, impressao_digital

    con = banco()
    # LX16: selo pago só sai com protocolo pago — o teste monta o do balcão.
    cobrir_o_ato(con, tabela="pt_atos", ato_id=1)
    SC.gravar_credencial(tmp_path, "fulano.detal123", "abcde123", agora=AGORA)
    CL.esquecer_tokens()

    # O ENVELOPE, do mesmo jeito que a tela do Protesto o monta.
    envelope = AS.envelope_do_protesto(
        tipo="APONTAMENTO", tabela="pt_atos", codigo_tj="16.1",
        escrevente="TESTE", protocolo="2608260001",
        versao_tabela="0320260101", livro="1A", folha="12")

    with SeladorFalso() as s:
        SC.gravar(con, base_url=s.base, usuario="fulano.detal123", agora=AGORA)
        CL.fixar_certificado(con, s.base, sha256=impressao_digital(),
                             agora=AGORA, usuario="TESTE")
        r = AS.selar_o_ato_lavrado(
            _DbDeMentira(con), tmp_path, tabela="pt_atos", ato_id=1,
            tipo="APONTAMENTO", atribuicao="protesto", agora=AGORA, cns=CNS,
            usuario="TESTE", dados=envelope)

    assert r["selado"] is True
    assert r["caminho"] == "/selo/protesto/titulo"
    # O SELO ESTA AMARRADO AO ATO — nao basta existir no razao.
    linha = con.execute("SELECT * FROM sd_selos WHERE numero=?",
                        (r["numero"],)).fetchone()
    assert linha["tabela"] == "pt_atos" and linha["ato_id"] == 1
    assert con.execute(
        "SELECT selo FROM pt_atos WHERE id=1").fetchone()[0] == r["numero"]


class _DbQueConfirma(_DbDeMentira):
    """Como o `Database`: a transacao propria confirma ao sair — a reserva da
    cobertura fica valendo antes do aparelho, como no balcao."""

    def transaction(self):
        from contextlib import contextmanager

        @contextmanager
        def _abrir():
            self.transacoes += 1
            try:
                yield self.con
            except BaseException:
                self.con.rollback()
                raise
            self.con.commit()

        return _abrir()


@pytest.mark.skipif(not _tem_cryptography(),
                    reason="o selador de mentira precisa de `cryptography`")
def test_o_aparelho_que_repete_o_selo_de_outro_ato_nao_sela_este_e_nada_some(
        tmp_path):
    """O defeito que a IA do servidor achou em 21/10/2026 (LD14), no caminho
    inteiro. O `ON CONFLICT DO NOTHING` do razao engolia o numero repetido e o
    selo seguia para o vinculo: o ato 2 ficava com o selo do ato 1, e do que
    o aparelho respondeu nao sobrava rastro. Agora o ato 2 fica sem selo,
    dizendo por que, e a recusa fica na auditoria."""
    import selador_cliente as CL
    import selador_config as SC
    from selador_falso import SeladorFalso, impressao_digital

    con = banco()
    _com_auditoria(con)
    _segundo_ato(con)
    cobrir_o_ato(con, tabela="pt_atos", ato_id=1)
    cobrir_o_ato(con, tabela="pt_atos", ato_id=2)
    SC.gravar_credencial(tmp_path, "fulano.detal123", "abcde123", agora=AGORA)
    CL.esquecer_tokens()
    envelope = AS.envelope_do_protesto(
        tipo="APONTAMENTO", tabela="pt_atos", codigo_tj="16.1",
        escrevente="TESTE", protocolo="2608260001",
        versao_tabela="0320260101", livro="1A", folha="12")

    def selar(ato_id):
        return AS.selar_o_ato_lavrado(
            _DbQueConfirma(con), tmp_path, tabela="pt_atos", ato_id=ato_id,
            tipo="APONTAMENTO", atribuicao="protesto", agora=AGORA, cns=CNS,
            usuario="TESTE", dados=envelope)

    with SeladorFalso() as s:
        SC.gravar(con, base_url=s.base, usuario="fulano.detal123", agora=AGORA)
        CL.fixar_certificado(con, s.base, sha256=impressao_digital(),
                             agora=AGORA, usuario="TESTE")
        con.commit()
        primeiro = selar(1)
        s._contador = 0          # o aparelho repete, a outro SID, o numero dado
        segundo = selar(2)

    assert primeiro["selado"] is True
    assert segundo["selado"] is False
    assert (f"O selador devolveu o selo {primeiro['numero']}, que já está "
            f"gravado no ato 1 de pt_atos") in segundo["motivo"]
    linhas = con.execute("SELECT numero, tabela, ato_id FROM sd_selos").fetchall()
    assert [(l["numero"], l["tabela"], l["ato_id"]) for l in linhas] == [
        (primeiro["numero"], "pt_atos", 1)]
    assert con.execute("SELECT selo FROM pt_atos WHERE id=2").fetchone()[0] is None
    # A recusa, e depois o estorno da reserva que o pedido do ato 2 fez.
    assert [a["action"] for a in _auditoria(con)] == [
        "SELO_REPETIDO_RECUSADO", "SELO_RESERVA_ESTORNADA"]
    # A COBERTURA DO ATO 2 NAO SE CONFIRMOU: selo que nao saiu nao se paga.
    assert con.execute(
        """SELECT COUNT(*) FROM cx_selo_coberturas WHERE tabela='pt_atos'
            AND ato_id=2 AND situacao='CONFIRMADA'""").fetchone()[0] == 0


def test_toda_tela_que_sela_passa_o_envelope():
    """**O guarda que faltava**, e que teria achado o defeito acima na hora.

    `selar_o_ato_lavrado` aceita `dados=None` na assinatura e **falha sempre**
    nesse caso: o contrato recusa pedido sem corpo. Uma tela que chamasse sem o
    envelope selaria zero atos — e o escrevente veria «o ato foi lavrado SEM
    SELO» sem entender por que.

    Medido em 30/08/2026: **seis** chamadas em cinco modulos de tela, e as seis
    passam `dados=`.
    """
    from pathlib import Path as _Path

    raiz = _Path(__file__).resolve().parent.parent
    achadas, sem_envelope = 0, []
    for arquivo in sorted(raiz.glob("*_web.py")):
        texto = arquivo.read_text(encoding="utf-8")
        procura = 0
        while True:
            onde = texto.find("selar_o_ato_lavrado(", procura)
            if onde < 0:
                break
            procura = onde + 1
            achadas += 1
            if "dados=" not in _argumentos_da_chamada(texto, onde):
                linha = texto[:onde].count("\n") + 1
                sem_envelope.append(f"{arquivo.name}:{linha}")
    assert achadas >= 6, (
        f"o varredor achou {achadas} chamadas e eram 6 em 30/08/2026 — "
        f"varredor que deixa de achar passa calado")
    assert not sem_envelope, (
        "estas telas chamam `selar_o_ato_lavrado` sem envelope, e selariam "
        "zero atos: " + ", ".join(sem_envelope))


def test_o_aparelho_fora_do_ar_NAO_derruba_o_ato(tmp_path):
    """O ato ja esta lavrado quando o selo e pedido.

    O aparelho e maquina de rede local e cai; a energia do escritorio cai. Nada
    disso pode derrubar um ato que ja existe — e por isso esta funcao NAO
    ESTOURA: devolve o motivo, e a tela conta ao escrevente.

    E a mesma escolha que a casa ja fazia quando o balcao pesava mais: ato sem
    selo entra e aparece em `atos_sem_selo`, que e melhor que balcao parado e
    melhor que ato com selo inventado.
    """
    con = banco()          # sem configuracao nenhuma do selador
    r = AS.selar_o_ato_lavrado(
        _DbDeMentira(con), tmp_path, tabela="pt_atos", ato_id=1,
        tipo="APONTAMENTO", atribuicao="protesto", agora=AGORA, cns=CNS)
    assert r["selado"] is False
    assert r["motivo"]                       # diz o que faltou
    # O ATO CONTINUA LA, e sem selo.
    assert con.execute("SELECT selo FROM pt_atos WHERE id=1").fetchone()[0] is None


def test_ato_sem_caminho_medido_nao_inventa_por_onde_selar(tmp_path):
    """Selar por um caminho que a casa nunca usou e assinar por quem selou.

    No civil, o caminho vem da ESPECIE: sem ela nao ha caminho, e devolver
    None e o certo — selar registro de obito pelo caminho do nascimento seria
    pior que nao selar.
    """
    con = banco()
    r = AS.selar_o_ato_lavrado(
        _DbDeMentira(con), tmp_path, tabela="rc_certidoes", ato_id=1,
        tipo="CERTIDAO", atribuicao="RCPN", agora=AGORA, cns=CNS)
    assert r["selado"] is False
    assert r["caminho"] is None
    assert "caminho de selo medido" in r["motivo"]


# ---------------- o caminho do civil, medido em 27/08/2026
#
# Ver DOCUMENTACAO/SELO_DO_CIVIL_MEDIDO.md. O contrato tem uma FAMILIA de
# caminhos por especie, e as tres do meio sao a divisao tripartite que
# `rc_assento` ja modela.


def test_o_caminho_do_civil_se_compoe_da_especie_e_do_ato():
    assert AS.caminho_do_civil("NASCIMENTO", "REGISTRO") == "/selo/civil/nascimento"
    assert AS.caminho_do_civil("OBITO", "REGISTRO") == "/selo/civil/obito"
    assert AS.caminho_do_civil("NASCIMENTO", "AVERBACAO")         == "/selo/civil/nascimento/averbacao"
    assert AS.caminho_do_civil("NASCIMENTO", "ANOTACAO")         == "/selo/civil/nascimento/anotacao"
    assert AS.caminho_do_civil("OBITO", "RETIFICACAO")         == "/selo/civil/obito/retificacao"
    # A certidao depois da primeira: o nome «segunda via» e do selador.
    assert AS.caminho_do_civil("CASAMENTO", "CERTIDAO")         == "/selo/civil/casamento/segunda-via"


def test_o_caminho_composto_e_CONFERIDO_contra_o_contrato():
    """Compor sozinho produziria caminho que nao existe.

    E o contrato e quem responde que nao existe — nao eu, e nao uma lista que
    envelhece. O caso vivo e PROCLAMAS: `/selo/civil/casamento/habilitacao`
    existe, e `.../habilitacao/averbacao` nao. A composicao devolve None ali, e
    nao um caminho parecido.
    """
    import selador
    for especie, tipo in (("NASCIMENTO", "REGISTRO"), ("OBITO", "AVERBACAO"),
                          ("NATIMORTO", "CERTIDAO"), ("TUTELA", "ANOTACAO")):
        assert AS.caminho_do_civil(especie, tipo) in selador.ENDPOINTS
    # O contrato nao tem averbacao de habilitacao, e por isso ela nao sai.
    assert AS.caminho_do_civil("PROCLAMAS", "AVERBACAO") is None
    # E o que nao existe no sistema tambem nao inventa caminho.
    for especie in ("OUTRO", "SEI_LA"):
        assert AS.caminho_do_civil(especie, "REGISTRO") is None
    assert AS.caminho_do_civil("NASCIMENTO", "TIPO_QUE_NAO_EXISTE") is None


def test_o_civil_saiu_da_tabela_de_pares():
    """A correcao de 27/08/2026, e ela e visivel.

    Estava escrito que os tres atos do civil selavam por `atos-em-geral` e que
    o `codigoAto` fora mandado vazio nos 1.238 — a medicao desmentiu as duas
    coisas. `atos-em-geral` foi o caminho ANTIGO (2020 a set/2024), e 98% do
    que saiu por ele foram certidoes.
    """
    do_civil = [k for k in AS.CAMINHO_DO_ATO
                if k[0] in ("rc_atos", "rc_certidoes")]
    assert do_civil == [], f"o civil nao mora mais na tabela de pares: {do_civil}"


def test_a_referencia_do_selo_e_o_ATO_e_nao_a_hora():
    """E dela que sai o SID, e e o SID que impede o aparelho de vender dois
    selos para o mesmo ato.

    Foi a falta disso que deixou 1.304 selos orfaos no E-Oficio — 5% de tudo o
    que a casa selou em seis anos.
    """
    import inspect
    fonte = inspect.getsource(AS.selar_o_ato_lavrado)
    assert 'f"{tabela}:{int(ato_id)}"' in fonte


def test_as_especies_que_o_oficial_decidiu_em_27_08():
    """As tres que a medicao nao fechava, e ele decidiu.

    CASAMENTO RELIGIOSO sela pelo caminho do casamento: o contrato nao tem
    `casamento-religioso`, e o religioso com efeito civil E registro de
    casamento — o que muda e o livro (B-Auxiliar), nao o ato.

    PROCLAMAS e a habilitacao, e o contrato tem o caminho dela.

    O LIVRO E se partiu em seis, cada uma com a sua familia inteira.
    """
    assert AS.caminho_do_civil("CASAMENTO_RELIGIOSO", "REGISTRO") \
        == "/selo/civil/casamento"
    assert AS.caminho_do_civil("PROCLAMAS", "REGISTRO") \
        == "/selo/civil/casamento/habilitacao"
    for especie, segmento in (("AUSENCIA", "ausencia"),
                              ("INTERDICAO", "interdicao"),
                              ("TUTELA", "tutela"),
                              ("EMANCIPACAO", "emancipacao"),
                              ("UNIAO_ESTAVEL", "uniao-estavel"),
                              ("OPCAO_NACIONALIDADE", "opcao-nacionalidade")):
        assert AS.caminho_do_civil(especie, "REGISTRO") \
            == f"/selo/civil/{segmento}"
        assert AS.caminho_do_civil(especie, "AVERBACAO") \
            == f"/selo/civil/{segmento}/averbacao"


def test_TODA_especie_do_sistema_tem_caminho_menos_OUTRO():
    """A varredura que impede a especie nova de nascer sem selo.

    Se alguem acrescentar uma especie amanha e esquecer o segmento, este teste
    fica vermelho — em vez de o ato sair sem selo no balcao, meses depois.

    `OUTRO` e a excecao declarada: ele existe para o que nao tem nome, e para o
    que nao tem nome nao ha caminho.
    """
    import rc_assento as RC
    sem_caminho = [e for e in RC.ESPECIES
                   if AS.caminho_do_civil(e, "REGISTRO") is None]
    assert sem_caminho == ["OUTRO"], (
        f"estas especies nascem sem selo: {sem_caminho}")


# ================ O ENVELOPE DO SELO DO CIVIL (27/08/2026)
#
# Medido nos 175 selos das especies do civil, que carregam a MESMA estrutura
# sem excecao. Ver DOCUMENTACAO/SELO_DO_CIVIL_MEDIDO.md.


def _envelope(**muda):
    campos = dict(especie="NASCIMENTO", tipo="REGISTRO",
                  escrevente="ELISA EXEMPLO LIMA", livro="24", folha="166",
                  termo="19552", nome_parte="ZELIA HOLANDA XAVIER SALES",
                  versao_tabela="0120260101", papel="7225319")
    campos.update(muda)
    return AS.envelope_do_civil(**campos)


def test_o_envelope_do_registro_e_o_que_a_casa_mandou():
    """Conferido contra um selo real de 13/08/2026."""
    e = _envelope()
    assert e["codigoTipoAtoRegistro"] == "14.a"
    d = e["dadosSelo"]
    assert d["escrevente"] == "ELISA EXEMPLO LIMA"
    assert (d["livro"], d["folha"], d["termo"]) == ("24", "166", "19552")
    assert d["versaoTabelaDeCustas"] == "0120260101"
    # O NOME VAI EM DOIS LUGARES, e vai nos 175 medidos.
    assert e["nomeParte"] == e["parte"]["nome"]
    assert e["papelMoeda"] == {"codigo": "7225319",
                               "fornecedor": "ARPENBRASIL",
                               "utilizado": False}


def test_a_isencao_da_lei_vai_junto_e_com_o_motivo():
    """A tabela de precos diz «Registro de nascimento, bem como pela primeira
    certidao respectiva. Isento» — e o selo leva isso escrito."""
    d = _envelope()["dadosSelo"]
    assert d["isentoGratuito"] == "ISENTO"
    assert d["motivoIsentoGratuito"] == "REGISTRO DE NASCIMENTO"
    assert _envelope(especie="OBITO")["dadosSelo"]["motivoIsentoGratuito"] \
        == "REGISTRO DE ÓBITO"
    # E a certidao NAO e isenta: quem paga, paga.
    assert "isentoGratuito" not in _envelope(tipo="CERTIDAO")["dadosSelo"]


def test_o_campo_do_codigo_muda_de_nome_com_o_ato():
    """Medido: o registro manda `codigoTipoAtoRegistro` e a certidao manda
    `codigoTipoAtoCertidao`. Mandar o nome errado e o aparelho recusar."""
    assert "codigoTipoAtoRegistro" in _envelope(tipo="REGISTRO")
    certidao = _envelope(tipo="CERTIDAO")
    assert certidao["codigoTipoAtoCertidao"] == "14.5.1"
    assert "codigoTipoAtoRegistro" not in certidao


def test_a_certidao_de_inteiro_teor_tem_item_proprio():
    """109 selos com `14.5.1` e 237 com `14.5.6` — as duas formas medidas."""
    assert _envelope(tipo="CERTIDAO",
                     inteiro_teor=True)["codigoTipoAtoCertidao"] == "14.5.6"


def test_o_envelope_recusa_e_DIZ_o_que_falta():
    """Um envelope incompleto que saisse pela rede voltaria como HTTP 400 com o
    texto do fornecedor, que ninguem no balcao entende."""
    with pytest.raises(AS.AtoError) as erro:
        _envelope(livro="", termo=None)
    assert "o livro" in str(erro.value) and "o termo" in str(erro.value)


def test_ato_sem_item_de_custas_conhecido_nao_inventa_um():
    """`OUTRO` nao tem item — e a regra da casa e nao inventar codigo."""
    with pytest.raises(AS.AtoError, match="tabela de custas"):
        _envelope(especie="OUTRO")


def test_o_papel_e_opcional_no_envelope_e_isso_e_deliberado():
    """A folha e do RCPN. Deixar o envelope exigi-la impediria de reaproveitar
    esta funcao no dia em que outra atribuicao selar sem papel."""
    assert "papelMoeda" not in _envelope(papel=None)


def test_a_procedencia_de_cada_codigo_fica_marcada():
    """`MEDIDO` e o que a casa mandou de verdade; `TABELA` e o que saiu da
    tabela de precos do TJMA, lida pela descricao do item. Nenhum e chute — e
    saber qual e qual e o que permite conferir depois."""
    assert AS.codigo_do_ato_do_civil("NASCIMENTO", "REGISTRO") \
        == ("14.a", AS.MEDIDO)
    assert AS.codigo_do_ato_do_civil("NATIMORTO", "REGISTRO") \
        == ("14.d", AS.TABELA)
    assert AS.codigo_do_ato_do_civil(None, "AVERBACAO") == ("14.4.1", AS.TABELA)
    assert AS.codigo_do_ato_do_civil("OUTRO", "REGISTRO") is None


def test_toda_especie_COM_CAMINHO_tem_item_de_custas():
    """As duas coisas andam juntas: caminho sem item nao monta envelope, e
    item sem caminho nao tem para onde ir. Especie nova que nasca com um so
    fica vermelha aqui."""
    import rc_assento as RC
    faltando = [e for e in RC.ESPECIES
                if AS.caminho_do_civil(e, "REGISTRO")
                and not AS.codigo_do_ato_do_civil(e, "REGISTRO")]
    assert faltando == [], f"tem caminho e nao tem item de custas: {faltando}"


def test_a_versao_da_tabela_de_custas_muda_com_a_ATRIBUICAO():
    """CORRECAO DE 27/08/2026, no mesmo dia em que o defeito entrou.

    Eu havia posto `0120260101` — o valor do civil — numa configuracao unica,
    como se ele valesse para a casa inteira. Os selos de 2026 desmentiram:

        civil 01 · imovel 02 · protesto 03 · rtdpj 04 · notas 05

    Os dois primeiros algarismos nao variam com o ano: variam com a SECAO da
    atribuicao na tabela do TJMA. Mandar `01` num selo de protesto seria dizer
    ao aparelho que o ato foi cobrado por outra tabela.
    """
    assert AS.versao_da_tabela_de_custas("/selo/civil/nascimento",
                                         "20260101") == "0120260101"
    assert AS.versao_da_tabela_de_custas("/selo/protesto/titulo",
                                         "20260101") == "0320260101"
    assert AS.versao_da_tabela_de_custas("/selo/imovel/certidao",
                                         "20260101") == "0220260101"
    assert AS.versao_da_tabela_de_custas("/selo/notas/autenticacao",
                                         "20260101") == "0520260101"


def test_a_data_da_tabela_aceita_o_que_o_oficial_digitar():
    """Ele vai digitar `2027-01-01` tanto quanto `20270101`."""
    assert AS.versao_da_tabela_de_custas("/selo/civil/obito",
                                         "2027-01-01") == "0120270101"


def test_sem_prefixo_medido_a_versao_e_None_e_o_selo_nao_sai():
    """Melhor nao sair do que sair com a tabela de outra atribuicao."""
    assert AS.versao_da_tabela_de_custas("/selo/desconhecido/x",
                                         "20260101") is None
    assert AS.versao_da_tabela_de_custas("/selo/civil/obito", "") is None
    assert AS.versao_da_tabela_de_custas("", "20260101") is None


# ================ O ENVELOPE DO SELO DO PROTESTO (27/08/2026)
#
# UM SELO POR ITEM COBRADO — decisao do oficial, e e o que o E-Oficio fazia:
# na retirada, `17.10.1`, `17.4` e `17.2` saem SEMPRE JUNTOS, 49 vezes cada.


def test_a_natureza_do_protesto_vem_do_contrato_e_nao_de_palpite():
    """O enum estava no `selador-doc` o tempo todo.

    Medindo, `natureza.tipo` variava dentro do mesmo caminho e eu escrevi que
    «sai de outra coisa, que nao medi». Saia do contrato — e a medicao encaixa
    inteira: pagamento 8 (431 selos), retirada 9 (147), certidao 0 (57 de 57).
    """
    assert AS.natureza_do_protesto("PAGAMENTO") == 8
    assert AS.natureza_do_protesto("RETIRADA") == 9
    assert AS.natureza_do_protesto("PROTESTO") == 7
    # A CERTIDAO TEM O SEU PROPRIO ENUM: 0 e «por nome», que e como esta casa
    # busca. No enum do TITULO o 0 e outra coisa — «Intimacao por Carta
    # Protocolada» —, e foi por confundir os dois que este numero saiu errado
    # da primeira vez.
    assert AS.natureza_do_protesto("CERTIDAO") == 0


def test_a_intimacao_e_a_unica_que_depende_de_COMO_aconteceu():
    """E o sistema ja sabe: `protesto_aviso` grava PESSOAL ou EDITAL.

    PESSOAL e «Carta Protocolada», e nao «Registrada»: quem entrega nesta casa
    e a propria casa, e as 1.618 entregas sairam com taxa de AR zero.
    """
    assert AS.natureza_do_protesto("INTIMACAO", "PESSOAL") == 0
    assert AS.natureza_do_protesto("INTIMACAO", "EDITAL") == 2
    assert AS.natureza_do_protesto("SEI_LA") is None


def test_o_envelope_do_protesto_e_o_que_a_casa_mandou():
    """Conferido contra um selo real de pagamento, de 06/08/2026."""
    e = AS.envelope_do_protesto(
        tipo="PAGAMENTO", codigo_tj="17.10.1", escrevente="ELISA EXEMPLO LIMA",
        protocolo="2608060001", versao_tabela="0320260101", livro="1",
        folha="34", valor_centavos=23000,
        partes=[{"nome": "MARCOS MAURO", "documento": "000.000.031-07"}])
    assert e["natureza"] == {"tipo": 8}
    assert e["ato"] == {"codigo": "17.10.1", "codigoTabelaCusta": "0320260101"}
    assert e["selo"]["protocolo"] == "2608060001"
    # O VALOR VAI EM REAIS, e o caixa desta casa conta em centavos.
    assert e["selo"]["valorTitulo"] == 230.0
    # O DOCUMENTO VAI SO COM ALGARISMOS, como nos 1.308 medidos.
    assert e["partes"]["parteAto"][0]["documento"] == "00000003107"
    # `nomePartes` VAZIO: o contrato diz que ele existe «apenas para
    # compatibilidade com versoes anteriores».
    assert e["partes"]["nomePartes"] == []


def test_o_convenio_NAO_vai_no_envelope():
    """Medido: ausente em 440 dos 465 selos de pagamento. Mandar campo que a
    casa nao mandava e inventar."""
    e = AS.envelope_do_protesto(
        tipo="PAGAMENTO", codigo_tj="17.2", escrevente="X", protocolo="1",
        versao_tabela="0320260101")
    assert "convenio" not in e


def test_o_envelope_do_protesto_recusa_e_diz_o_que_falta():
    with pytest.raises(AS.AtoError, match="o protocolo"):
        AS.envelope_do_protesto(tipo="PAGAMENTO", codigo_tj="17.2",
                                escrevente="X", protocolo="",
                                versao_tabela="0320260101")


def test_CANCELAMENTO_quer_dizer_DUAS_COISAS_e_a_tabela_desempata():
    """DEFEITO MEU DE UM MINUTO, e a segunda vez na mesma tarde.

    A palavra vale para duas coisas nesta casa: a BAIXA do protesto
    (`pt_atos`), que e natureza 9, e a CERTIDAO de cancelamento
    (`pt_certidoes`), que e certidao como as outras e sai por busca de nome.

    E a mesma armadilha do enum da certidao, meia hora antes: **a mesma
    palavra em dois lugares nao quer dizer a mesma coisa.**
    """
    assert AS.natureza_do_protesto("CANCELAMENTO", tabela="pt_atos") == 9
    assert AS.natureza_do_protesto("CANCELAMENTO", tabela="pt_certidoes") == 0


def test_toda_certidao_do_protesto_sela_pelo_enum_DA_CERTIDAO():
    """Negativa, positiva e de cancelamento: o que muda entre elas e o TEOR do
    papel, e nao a forma da busca — e o enum pergunta pela busca."""
    for tipo in ("NEGATIVA", "POSITIVA", "CANCELAMENTO"):
        assert AS.natureza_do_protesto(tipo, tabela="pt_certidoes") == 0
        assert AS.caminho_do_ato("pt_certidoes", tipo) \
            == "/selo/protesto/certidao"


def test_todo_ato_do_protesto_COM_CAMINHO_tem_natureza():
    """A varredura que impede um ato de nascer com caminho e sem natureza — e
    de sair sem selo meses depois, no balcao."""
    sem = [(tabela, tipo) for (tabela, tipo) in AS.CAMINHO_DO_ATO
           if tabela.startswith("pt_")
           and AS.natureza_do_protesto(tipo, tabela=tabela) is None]
    assert sem == [], f"tem caminho e nao tem natureza: {sem}"


# ================ O ENVELOPE DO SELO DAS NOTAS (27/08/2026)
#
# METADE DO MOVIMENTO DESTA CASA: 13.776 selos de reconhecimento de firma,
# 3.664 de autenticacao e 2.667 de cartao — 96% dos selos de notas do acervo.


def test_o_reconhecimento_de_firma_e_o_que_a_casa_mandou():
    """Conferido contra um selo real."""
    e = AS.envelope_das_notas(
        tabela="nt_reconhecimentos", codigo_tj="13.17.4",
        escrevente="ELISA EXEMPLO LIMA", versao_tabela="0520260101",
        especie="SEMELHANCA",
        partes=[{"nome": "ZENO DO NASCIMENTO COSTA",
                 "documento": "000.000.011-63"}])
    assert e["natureza"] == {"tipo": 1}
    assert e["ato"] == {"codigo": "13.17.4", "codigoTabelaCusta": "0520260101"}
    # O NOME DO CAMPO E `nomesReconhecido` aqui — e `partes` no cartao. E o
    # mesmo conteudo com dois nomes, e mandar o errado e o aparelho recusar.
    assert "nomesReconhecido" in e and "partes" not in e
    assert e["nomesReconhecido"]["parteAto"][0]["documento"] == "00000001163"


def test_a_natureza_da_firma_ja_estava_no_contrato_e_no_sistema():
    """`selador.NATUREZA_FIRMA` diz 0 autenticidade, 1 semelhanca; e
    `nt_reconhecimentos.especie` ja guarda qual e.

    Medido, os dois lados batem: SEMELHANCA sao 11.410 atos no sistema para
    11.919 selos com `tipo: 1`.
    """
    import selador
    assert AS.NATUREZA_DA_FIRMA["AUTENTICIDADE"] == 0
    assert AS.NATUREZA_DA_FIRMA["SEMELHANCA"] == 1
    assert selador.NATUREZA_FIRMA[0].lower().endswith("autenticidade")


def test_reconhecimento_sem_especie_e_recusado():
    """O selo pede um dos dois, e nao ha padrao a supor."""
    with pytest.raises(AS.AtoError, match="semelhança ou por autenticidade"):
        AS.envelope_das_notas(tabela="nt_reconhecimentos", codigo_tj="13.17.2",
                              escrevente="X", versao_tabela="0520260101")


def test_a_autenticacao_manda_QUANTIDADE_e_nao_parte():
    """O que se autentica e copia, e o que se cobra e por copia. Medido: 1 em
    3.664 de 3.664."""
    e = AS.envelope_das_notas(tabela="nt_autenticacoes", codigo_tj="13.18",
                              escrevente="X", versao_tabela="0520260101",
                              quantidade=3)
    assert e["quantidade"] == 3
    assert "partes" not in e and "natureza" not in e


def test_o_cartao_manda_PARTES():
    e = AS.envelope_das_notas(tabela="nt_cartoes", codigo_tj="13.17.1",
                              escrevente="X", versao_tabela="0520260101",
                              partes=[{"nome": "ALBERTO RESENDE DOS SANTOS"}])
    assert e["partes"]["parteAto"][0]["nome"] == "ALBERTO RESENDE DOS SANTOS"
    assert "nomesReconhecido" not in e


def test_o_caminho_das_notas_e_da_TABELA_e_nao_do_tipo():
    """Cada tela das Notas sela uma coisa so — firma, copia, cartao."""
    assert AS.caminho_do_ato("nt_reconhecimentos", "SEMELHANCA") \
        == "/selo/notas/reconhecimento-firma"
    assert AS.caminho_do_ato("nt_autenticacoes", "QUALQUER") \
        == "/selo/notas/autenticacao"
    assert AS.caminho_do_ato("nt_cartoes", "") == "/selo/notas/cartao-assinatura"


def test_tabela_das_notas_sem_caminho_medido_e_recusada():
    with pytest.raises(AS.AtoError, match="caminho de selo medido"):
        AS.envelope_das_notas(tabela="nt_atos", codigo_tj="13.30",
                              escrevente="X", versao_tabela="0520260101")


def test_a_certidao_de_mais_de_uma_folha_sao_dois_itens():
    """**MEDIDO EM 21/09/2026 nos 667 envelopes de `/selo/imovel/certidao`**,
    agrupados pelo protocolo geral:

    | o que saiu no protocolo | protocolos |
    |---|---|
    | `16.24.4` + `16.24.4.1` (inteiro teor + folha acrescida) | **99** |
    | `16.24.1` + `16.24.2` (certidão comum + folha acrescida) | **94** |
    | o item base sozinho | **88**, com quantidade 1 em todos |

    A casa não mandou «inteiro teor, quantidade 5»: mandou «inteiro teor, 1»
    **e** «folha acrescida, 4».
    """
    import ato_selado as AS
    assert AS.itens_da_certidao_do_ri("INTEIRO_TEOR", 1) == [("16.24.4", 1)]
    assert AS.itens_da_certidao_do_ri("INTEIRO_TEOR", 5) == [
        ("16.24.4", 1), ("16.24.4.1", 4)]
    assert AS.itens_da_certidao_do_ri("ONUS", 2) == [
        ("16.24.4", 1), ("16.24.4.1", 1)]
    # A CERTIDAO COMUM TEM O SEU PROPRIO PAR — e ele NAO e o `16.24.1.1`, que
    # aparece uma vez em 667, num protocolo com todos os itens juntos. Um caso
    # nao e regra.
    assert AS.itens_da_certidao_do_ri("PROPRIEDADE", 3) == [
        ("16.24.1", 1), ("16.24.2", 2)]
    for folhas in range(1, 13):
        itens = AS.itens_da_certidao_do_ri("INTEIRO_TEOR", folhas)
        assert itens[0][1] == 1, "o item base vai sempre com uma folha"
        assert sum(q for _, q in itens) == folhas


def test_a_certidao_digital_de_inteiro_teor_nao_cobra_folha_excedente():
    """DECISÃO-COGEx 2035/2026, item «b»: a certidão digital de inteiro teor de
    matrícula se cobra pelo 16.24.4, «vedada a cobrança adicional por folhas
    excedentes». A do balcão continua com a folha acrescida, e a comum digital
    (16.24.1) não é alcançada pela decisão."""
    import ato_selado as AS
    assert AS.itens_da_certidao_do_ri("INTEIRO_TEOR", 7, digital=True) == [("16.24.4", 1)]
    assert AS.itens_da_certidao_do_ri("ONUS", 3, digital=True) == [("16.24.4", 1)]
    assert AS.itens_da_certidao_do_ri("INTEIRO_TEOR", 7) == [("16.24.4", 1), ("16.24.4.1", 6)]
    assert AS.itens_da_certidao_do_ri("PROPRIEDADE", 3, digital=True) == [
        ("16.24.1", 1), ("16.24.2", 2)]
    assert AS.e_certidao_digital_do_ri(f"{AS.PREFIXO_DA_FINALIDADE_ONR}IS0001234")
    assert not AS.e_certidao_digital_do_ri("Para fins de financiamento")
    assert not AS.e_certidao_digital_do_ri(None)


def test_a_emissao_do_ri_e_o_orcamento_do_onr_usam_a_regra_digital():
    """Os dois lugares que contam itens de certidão de matrícula passam a marca
    digital: o laço dos selos do RI (pela finalidade gravada) e o orçamento do ONR."""
    raiz = Path(__file__).resolve().parent.parent
    ri = (raiz / "ri_web.py").read_text(encoding="utf-8")
    assert "digital=AS.e_certidao_digital_do_ri(" in ri
    onr = (raiz / "onr_certidoes_auto.py").read_text(encoding="utf-8")
    assert "digital=True" in onr


def test_o_tipo_que_a_casa_nunca_selou_nao_vira_item():
    """Não se sela por caminho — nem por item — que a casa nunca usou."""
    import pytest as _pytest

    import ato_selado as AS
    with _pytest.raises(AS.AtoError):
        AS.itens_da_certidao_do_ri("NEGATIVA", 1)


def test_o_envelope_aceita_o_codigo_do_item_de_folha():
    """O item da folha acrescida não é um TIPO de certidão: é o segundo item
    do mesmo pedido, com o mesmo corpo e outra linha da tabela."""
    import ato_selado as AS
    envelope = AS.envelope_da_certidao_do_ri(
        tipo="INTEIRO_TEOR", escrevente="MARIO", versao_tabela="0520260101",
        quantidade=4, codigo_do_item="16.24.4.1", matricula="1116")
    assert envelope["codigoTipoAto"] == "16.24.4.1"
    assert envelope["quantidade"] == 4
    assert envelope["partes"]["parteAto"][0]["nome"] == "MATRICULA 1116"


def test_selos_do_ato_e_uma_funcao_so():
    """ELA ESTAVA DEFINIDA DUAS VEZES, e a segunda era a que valia — apagada
    em 21/09/2026. As duas liam o mesmo; o que mudava era a ordem, e
    `obtido_em` tem dois formatos nesta casa."""
    from pathlib import Path as _P
    fonte = _P(__file__).resolve().parents[1] / "ato_selado.py"
    texto = fonte.read_text(encoding="utf-8")
    assert texto.count("def selos_do_ato(") == 1
