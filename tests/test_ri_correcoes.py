"""
Testes da numeracao por serventia, da renumeracao de matricula e da correcao
de partes.

O CASO REAL QUE ORIGINOU CADA UM
    Em 18/08/2026 o sistema abriu a matricula 4011 no livro "2" quando a
    serventia ja tinha a 4013 no volume "2S", porque contava por volume em vez
    de por serventia. E o R-01 gravou o INCRA como "adquirente" e a adquirente
    sem papel, deixando a matricula SEM TITULAR ATIVO.

    Cada teste abaixo reproduz um desses fatos e exige o comportamento correto.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import ri_correcoes as RC                                   # noqa: E402
from ri_schema import hash_ato, init_ri_schema, verifica_cadeia   # noqa: E402

AGORA = "2026-08-19T09:00:00"


@pytest.fixture()
def con():
    c = conexao_de_teste()
    c.execute("PRAGMA foreign_keys=ON")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    init_ri_schema(c)
    yield c
    c.close()


def matricula(con, numero, livro, origem="MANUAL"):
    cur = con.execute(
        """INSERT INTO ri_matriculas
           (numero, complemento, livro, livro_norm, tipo_ficha, situacao, conferido,
            origem, criado_em, teor_formato)
           VALUES (?,'',?,?,'ESTRUTURADA','ATIVA',1,?,?,'texto')""",
        (str(numero), livro, livro, origem, AGORA))
    return int(cur.lastrowid)


def numeracao(con, livro, proximo, maior):
    con.execute("""INSERT INTO ri_numeracao(livro, proximo_numero, maior_em_uso, fixado_em)
                   VALUES (?,?,?,?)""", (livro, proximo, maior, AGORA))


def ato(con, matricula_id, tipo, numero, matricula_numero, teor):
    anterior = con.execute("""SELECT hash_ato FROM ri_atos WHERE matricula_id=?
                              ORDER BY id DESC LIMIT 1""", (matricula_id,)).fetchone()
    ha = anterior["hash_ato"] if anterior else None
    h = hash_ato(matricula_numero, tipo, numero, "2026-08-18", teor, ha)
    cur = con.execute(
        """INSERT INTO ri_atos
           (matricula_id, tipo, numero, data_ato, teor, teor_formato, cancelado,
            acervo, origem, hash_ato, hash_anterior, lavrado_em)
           VALUES (?,?,?,'2026-08-18',?,'texto',0,0,'MANUAL',?,?,?)""",
        (matricula_id, tipo, numero, teor, h, ha, AGORA))
    return int(cur.lastrowid)


# ------------------------------------------------------------ serie do livro


@pytest.mark.parametrize("livro,serie", [
    ("2", "2"), ("2C", "2"), ("2-C", "2"), ("2S", "2"), ("2 S", "2"),
    ("3", "3"), ("1A", "1"), ("1", "1"),
])
def test_a_letra_e_o_volume_nao_a_serie(livro, serie):
    assert RC.serie_do_livro(livro) == serie


def test_livro_3_nao_se_mistura_com_o_livro_2(con):
    matricula(con, 4013, "2S")
    matricula(con, 1650, "3")
    assert RC.maior_numero_da_serie(con, "2") == 4013
    assert RC.maior_numero_da_serie(con, "3") == 1650, \
        "Registro Auxiliar tem numeracao propria"


# --------------------------------------------- o erro do dia 18, reproduzido


def test_o_proximo_numero_olha_a_serventia_e_nao_o_volume(con):
    """O caso real: livro '2' em 4010, mas a serventia ja usou a 4013 no '2S'."""
    matricula(con, 4010, "2")
    matricula(con, 4012, "2R")
    matricula(con, 4013, "2S")
    numeracao(con, "2", 4011, 4010)
    numeracao(con, "2R", 4013, 4012)
    numeracao(con, "2S", 4014, 4013)

    assert RC.proximo_numero(con, "2") == 4014, \
        "contar por volume daria 4011, que a serventia ja usou"


def test_numero_em_uso_encontra_a_matricula_em_qualquer_volume(con):
    matricula(con, 4013, "2S")
    achada = RC.numero_em_uso(con, "2", 4013)
    assert achada is not None and achada["livro"] == "2S"


def test_numeracao_atrasada_nao_faz_o_numero_andar_para_tras(con):
    numeracao(con, "2", 5000, 4999)
    assert RC.proximo_numero(con, "2") == 5000


# --------------------------------------------------------------- renumeracao


def test_renumerar_4011_para_4014_refaz_a_cadeia(con):
    m = matricula(con, 4011, "2")
    matricula(con, 4013, "2S")
    ato(con, m, "R", 1, "4011", "R-01/4014 TITULO DE DOMINIO")
    ato(con, m, "AV", 2, "4011", "AV-02/4014 CONDICOES RESOLUTIVAS")

    antes = [dict(r) | {"matricula_numero": "4014"} for r in con.execute(
        "SELECT id,tipo,numero,data_ato,teor,hash_ato FROM ri_atos ORDER BY id")]
    assert verifica_cadeia(antes), "com o numero novo, a cadeia antiga NAO confere"

    saida = RC.renumerar_matricula(con, m, 4014, agora=AGORA,
                                   motivo="Número já usado pela serventia no volume 2S")

    assert saida["de"] == "4011" and saida["para"] == "4014"
    assert len(saida["atos"]) == 2
    assert all(a["hash_antigo"] != a["hash_novo"] for a in saida["atos"])

    depois = [dict(r) | {"matricula_numero": "4014"} for r in con.execute(
        "SELECT id,tipo,numero,data_ato,teor,hash_ato FROM ri_atos ORDER BY id")]
    assert verifica_cadeia(depois) == [], "depois de renumerar, a cadeia volta a conferir"
    assert con.execute("SELECT numero FROM ri_matriculas WHERE id=?",
                       (m,)).fetchone()["numero"] == "4014"


def test_renumerar_sincroniza_a_serie_inteira(con):
    m = matricula(con, 4011, "2")
    matricula(con, 4013, "2S")
    numeracao(con, "2", 4012, 4011)
    numeracao(con, "2S", 4014, 4013)
    RC.renumerar_matricula(con, m, 4014, agora=AGORA, motivo="Corrigindo a numeração")
    for livro in ("2", "2S"):
        linha = con.execute("SELECT * FROM ri_numeracao WHERE livro=?", (livro,)).fetchone()
        assert linha["proximo_numero"] == 4015, f"o volume {livro} tem de apontar para 4015"
        assert linha["maior_em_uso"] == 4014


def test_nao_renumera_para_numero_ocupado(con):
    m = matricula(con, 4011, "2")
    matricula(con, 4013, "2S")
    with pytest.raises(RC.CorrecaoError, match="já é da matrícula"):
        RC.renumerar_matricula(con, m, 4013, agora=AGORA, motivo="Tentativa indevida")


def test_nao_renumera_matricula_do_acervo(con):
    m = matricula(con, 582, "2C", origem="EOFICIO")
    with pytest.raises(RC.CorrecaoError, match="acervo"):
        RC.renumerar_matricula(con, m, 9999, agora=AGORA, motivo="Não pode mesmo")


def test_certidao_viva_impede_renumerar(con):
    m = matricula(con, 4011, "2")
    con.execute("""INSERT INTO ri_certidoes
                   (numero, ano, tipo, matricula_id, matricula_numero, data_emissao,
                    corpo, corpo_formato, cancelada, origem, emitida_em)
                   VALUES (7,2026,'INTEIRO_TEOR',?,'4011','2026-08-18','x','html',0,
                           'MANUAL',?)""", (m, AGORA))
    with pytest.raises(RC.CorrecaoError, match="certidão 7/2026"):
        RC.renumerar_matricula(con, m, 4014, agora=AGORA, motivo="Corrigindo a numeração")


def test_motivo_curto_recusado_na_renumeracao(con):
    m = matricula(con, 4011, "2")
    with pytest.raises(RC.CorrecaoError, match="dez letras"):
        RC.renumerar_matricula(con, m, 4014, agora=AGORA, motivo="erro")


def test_renumerar_para_o_mesmo_numero_e_recusado(con):
    m = matricula(con, 4011, "2")
    with pytest.raises(RC.CorrecaoError, match="já é a 4011"):
        RC.renumerar_matricula(con, m, 4011, agora=AGORA, motivo="Nada a fazer aqui")


# -------------------------------------------------------------------- partes


def parte(con, matricula_id, ato_id, nome, papel, doc=None, ativo=0):
    cur = con.execute(
        """INSERT INTO ri_partes
           (matricula_id, ato_id, nome, papel, documento_numero, documento_tipo,
            proprietario, proprietario_ativo, origem)
           VALUES (?,?,?,?,?,?,0,?,'MANUAL')""",
        (matricula_id, ato_id, nome, papel, doc,
         "CPF" if doc and len(doc) == 11 else "CNPJ" if doc else None, ativo))
    return int(cur.lastrowid)


@pytest.mark.parametrize("papel,esperado", [
    ("proprietário", True), ("adquirente", True), ("nu-proprietário", True),
    ("transmitente", False), ("outorgante", False), ("cônjuge", False),
    (None, False), ("", False),
])
def test_quem_o_papel_faz_titular(papel, esperado):
    assert RC.e_titular(papel) is esperado


def test_corrigir_o_papel_do_incra_e_da_adquirente(con):
    """O erro real do R-01: INCRA como adquirente, e a dona sem papel."""
    m = matricula(con, 4011, "2")
    a = ato(con, m, "R", 1, "4011", "R-01/4014")
    incra = parte(con, m, a, "INCRA", "adquirente", "00000013000160")
    maria = parte(con, m, a, "MARIA REGO SILVA PEREIRA", None, "00000002992")

    RC.corrigir_parte(con, incra, papel="transmitente", agora=AGORA,
                      motivo="O INCRA é o outorgante do título de domínio")
    RC.corrigir_parte(con, maria, papel="proprietário", agora=AGORA,
                      motivo="Adquirente do título de domínio; titular atual")

    linhas = {r["nome"]: r for r in con.execute("SELECT * FROM ri_partes")}
    assert linhas["INCRA"]["papel"] == "transmitente"
    assert linhas["INCRA"]["proprietario_ativo"] == 0
    assert linhas["MARIA REGO SILVA PEREIRA"]["papel"] == "proprietário"
    assert linhas["MARIA REGO SILVA PEREIRA"]["proprietario_ativo"] == 1, \
        "sem isto a certidão de propriedade sai vazia"


def test_documento_invalido_e_recusado(con):
    m = matricula(con, 4011, "2")
    p = parte(con, m, None, "ALGUEM", "proprietário")
    with pytest.raises(RC.CorrecaoError, match="dígitos"):
        RC.corrigir_parte(con, p, documento="123", agora=AGORA,
                          motivo="Tentando documento curto")


def test_documento_valido_marca_a_conferencia(con):
    m = matricula(con, 4011, "2")
    p = parte(con, m, None, "ALGUEM", "proprietário")
    RC.corrigir_parte(con, p, documento="000.000.029-92", agora=AGORA,
                      motivo="Documento conferido no título")
    linha = con.execute("SELECT * FROM ri_partes WHERE id=?", (p,)).fetchone()
    assert linha["documento_numero"] == "00000002992"
    assert linha["documento_tipo"] == "CPF"
    assert linha["documento_valido"] == 1


def test_titular_pode_ser_forcado_contra_o_papel(con):
    """Em permuta as duas pontas sao adquirentes, e nem toda vira dona de tudo."""
    m = matricula(con, 4011, "2")
    p = parte(con, m, None, "ALGUEM", "adquirente", ativo=1)
    RC.corrigir_parte(con, p, titular=False, agora=AGORA,
                      motivo="Permuta: adquiriu apenas fração já averbada")
    assert con.execute("SELECT proprietario_ativo FROM ri_partes WHERE id=?",
                       (p,)).fetchone()["proprietario_ativo"] == 0


def test_nada_alterado_e_recusado(con):
    m = matricula(con, 4011, "2")
    p = parte(con, m, None, "ALGUEM", "transmitente")
    with pytest.raises(RC.CorrecaoError, match="Nada foi alterado"):
        RC.corrigir_parte(con, p, papel="transmitente", agora=AGORA,
                          motivo="Não muda nada mesmo")


def test_nome_em_branco_e_recusado(con):
    m = matricula(con, 4011, "2")
    p = parte(con, m, None, "ALGUEM", "transmitente")
    with pytest.raises(RC.CorrecaoError, match="não pode ficar em branco"):
        RC.corrigir_parte(con, p, nome="   ", agora=AGORA, motivo="Nome apagado sem querer")


def test_o_de_para_fica_registrado(con):
    m = matricula(con, 4011, "2")
    p = parte(con, m, None, "INCRA", "adquirente")
    saida = RC.corrigir_parte(con, p, papel="transmitente", agora=AGORA,
                              motivo="O INCRA é quem transmite")
    assert saida["mudancas"]["papel"] == {"de": "adquirente", "para": "transmitente"}


def test_numero_provisorio_nao_entra_na_serie(con):
    """07/10/2026, «opção 2»: as fantasmas 904020–904023 faziam o próximo ser 904024."""
    for n in (4020, 4021):
        matricula(con, n, "2")
    for n in (904020, 904023):
        matricula(con, n, "2")
    numeracao(con, "2", 4022, 4021)
    assert RC.proximo_numero(con, "2") == 4022


# ------------------------------------------------- a trava de quem numera
#
# RESSALVAS DA REVISAO DO L044, consertadas no L044R. Quem numera a matricula
# trava `ri_numeracao.livro` (abertura em `ri_web`, `_sincronizar_numeracao`).
# A renumeracao conferia o numero ocupado ANTES dessa trava, e a carga do
# E-Oficio lia o maior e gravava a numeracao sem ela. Enquanto a ponte existe a
# trava unica do banco serializa tudo; estes testes guardam o dia em que ela sair.


def _assunto_livre(chave: str) -> bool:
    """Outra conexao consegue a trava do assunto agora? Nao espera por ela."""
    import psycopg
    import banco_pg
    with psycopg.connect(banco_pg.dsn(), autocommit=True) as outra:
        return bool(outra.execute(
            "SELECT pg_try_advisory_xact_lock(hashtext(%s))", (chave,)).fetchone()[0])


def test_a_renumeracao_confere_o_numero_livre_dentro_da_trava(con, monkeypatch):
    m = matricula(con, 4011, "2")
    matricula(con, 4013, "2S")
    livre_na_conferencia = []
    original = RC.numero_em_uso

    def espiao(c, livro, numero):
        livre_na_conferencia.append(_assunto_livre("ri_numeracao.livro"))
        return original(c, livro, numero)

    monkeypatch.setattr(RC, "numero_em_uso", espiao)
    RC.renumerar_matricula(con, m, 4014, agora=AGORA, motivo="Corrigindo a numeração")

    assert livre_na_conferencia == [False], (
        "a renumeração conferiu o número ocupado fora da trava de quem abre "
        "matrícula: as duas podiam ficar com o mesmo número")


def test_a_carga_fixa_a_numeracao_dentro_da_trava(con, monkeypatch):
    import ri_import as IMP
    matricula(con, 4013, "2S", origem="EOFICIO")
    imp = IMP.Importador(con)
    livre_na_leitura = []
    original = imp.bd.ler

    def espiao(sql, parametros=None):
        livre_na_leitura.append(_assunto_livre("ri_numeracao.livro"))
        return original(sql, parametros)

    monkeypatch.setattr(imp.bd, "ler", espiao)
    assert imp.fixar_numeracao() == [("2S", 4014)]

    assert livre_na_leitura == [False], (
        "a carga leu o maior número e gravou a numeração fora da trava de "
        "quem abre matrícula")


# ------------------------------------------- quem transmitiu sai do quadro
#
# RESSALVAS DA REVISAO DO LD03, consertadas no LD10 (21/10/2026, «corrija
# tudo»). `titulares_que_transmitiram` casava pelo nome sempre que faltava o
# documento de UM lado, e o homonimo sem CPF saia junto; e lia o quadro e
# gravava sem prender nada. Agora: documento quando os dois lados tem; nome so
# quando nenhum tem e ha um unico candidato; o resto volta em `a_conferir`. E a
# leitura e a escrita ficam sob a trava da ficha e com as linhas presas.
# Os nomes e CPFs sao os ficticios da casa.

import threading                                                 # noqa: E402
import time                                                      # noqa: E402

import banco_pg                                                  # noqa: E402
from bd_nativo import banco                                      # noqa: E402

sem_a_ponte = pytest.mark.skipif(
    not banco_pg.ativo(), reason="a corrida só existe no PostgreSQL")

VENDEDOR, CPF_VENDEDOR = "PEDRO EXEMPLO DOS SANTOS", "00000000191"
COMPRADORA, CPF_COMPRADORA = "BEATRIZ EXEMPLO DE SOUZA", "00000000272"


def _venda(doc_vendedor=CPF_VENDEDOR):
    """As partes que a tela manda na compra e venda."""
    return [{"nome": VENDEDOR, "documento_numero": doc_vendedor or "",
             "papel": "transmitente"},
            {"nome": COMPRADORA, "documento_numero": CPF_COMPRADORA,
             "papel": "adquirente"}]


def _ficha_vendida(con, *donos):
    """A matrícula, os titulares de antes (nome, documento) e o R-1 da venda,
    já com a compradora gravada pela lavratura. Devolve (matrícula, ato, ids)."""
    m = matricula(con, 4100, "2")
    ids = [parte(con, m, None, nome, "proprietário", doc, ativo=1) for nome, doc in donos]
    a = ato(con, m, "R", 1, "4100", "R-01/4100 COMPRA E VENDA")
    parte(con, m, a, COMPRADORA, "adquirente", CPF_COMPRADORA, ativo=1)
    return m, a, ids


def _ativos(con, m) -> list[tuple[int, str]]:
    return [(r["id"], r["nome"]) for r in banco(con).ler(
        "SELECT id, nome FROM ri_partes WHERE matricula_id=%s AND proprietario_ativo=1 "
        "ORDER BY id", (m,))]


def test_quem_transmitiu_sai_pelo_documento_e_o_xara_de_outro_cpf_fica(con):
    m, a, (pedro, xara) = _ficha_vendida(con, (VENDEDOR, CPF_VENDEDOR),
                                         (VENDEDOR, "00000000353"))
    saida = RC.titulares_que_transmitiram(con, m, a, _venda())
    assert saida == {"sairam": [VENDEDOR], "a_conferir": []}
    assert pedro not in [i for i, _ in _ativos(con, m)]
    assert xara in [i for i, _ in _ativos(con, m)], (
        "o xará de outro CPF saiu do quadro: é outra pessoa")


def test_sem_documento_dos_dois_lados_sai_pelo_nome_o_unico_titular(con):
    m, a, (pedro,) = _ficha_vendida(con, (VENDEDOR, None))
    saida = RC.titulares_que_transmitiram(con, m, a, _venda(doc_vendedor=None))
    assert saida == {"sairam": [VENDEDOR], "a_conferir": []}
    assert [n for _, n in _ativos(con, m)] == [COMPRADORA]


def test_o_homonimo_sem_documento_nao_tira_ninguem_do_quadro_e_fica_a_conferir(con):
    """Dois titulares com o nome do vendedor e ninguém com CPF: tirar um seria
    adivinhar — e tirar os dois (o LD03) deixava fora quem não vendeu."""
    m, a, (pedro, xara) = _ficha_vendida(con, (VENDEDOR, None), (VENDEDOR, None))
    saida = RC.titulares_que_transmitiram(con, m, a, _venda(doc_vendedor=None))
    assert saida["sairam"] == []
    assert len(saida["a_conferir"]) == 1, saida
    assert "há 2 titulares atuais com este nome" in saida["a_conferir"][0]
    assert "Partes → Corrigir" in saida["a_conferir"][0]
    assert {pedro, xara} <= {i for i, _ in _ativos(con, m)}


@pytest.mark.parametrize("doc_no_ato,doc_no_quadro", [
    (CPF_VENDEDOR, None),      # a abertura do acervo veio sem CPF
    (None, CPF_VENDEDOR),      # o escrevente não digitou o CPF no ato
])
def test_documento_de_um_lado_so_nao_tira_pelo_nome_e_fica_a_conferir(
        con, doc_no_ato, doc_no_quadro):
    m, a, (pedro,) = _ficha_vendida(con, (VENDEDOR, doc_no_quadro))
    saida = RC.titulares_que_transmitiram(con, m, a, _venda(doc_vendedor=doc_no_ato))
    assert saida["sairam"] == []
    assert len(saida["a_conferir"]) == 1, saida
    assert "só um dos dois tem CPF/CNPJ" in saida["a_conferir"][0]
    assert pedro in [i for i, _ in _ativos(con, m)]


_TRAVA_DESTA_CONEXAO = """
    SELECT count(*) AS n FROM pg_locks
     WHERE locktype = 'advisory' AND pid = pg_backend_pid() AND granted
       AND objsubid = 1
       AND classid::bigint = ((hashtext(%s)::bigint >> 32) & 4294967295)
       AND objid::bigint = (hashtext(%s)::bigint & 4294967295)"""


def _vigiar_o_quadro(monkeypatch, chave: str, modulo=RC) -> list:
    """Antes de cada comando em `ri_partes` que `modulo` manda, anota se ESTA
    conexão já tem a trava `chave`. Olha o `pg_locks` do próprio processo, e
    não pede a trava de fora: a chave é por valor, e outro teste em paralelo,
    noutro schema, pode estar com a da matrícula 1 dele."""
    import bd_nativo
    vistos: list = []

    class Vigiado(bd_nativo.Banco):
        def _rodar(self, sql, parametros=None):
            if "ri_partes" in sql:
                presa = bd_nativo.Banco._rodar(self, _TRAVA_DESTA_CONEXAO, (chave, chave))
                vistos.append((" ".join(sql.split())[:120], bool(presa[0]["n"])))
            return super()._rodar(sql, parametros)

    monkeypatch.setattr(modulo, "banco", Vigiado)
    return vistos


def test_o_quadro_se_le_e_se_grava_dentro_da_trava_da_ficha(con, monkeypatch):
    m, a, _ = _ficha_vendida(con, (VENDEDOR, CPF_VENDEDOR))
    vistos = _vigiar_o_quadro(monkeypatch, RC.chave_dos_titulares(m))
    assert RC.titulares_que_transmitiram(con, m, a, _venda())["sairam"] == [VENDEDOR]
    assert [s.split()[0] for s, _ in vistos] == ["SELECT", "UPDATE"], vistos
    assert all(presa for _, presa in vistos), (
        f"o quadro foi lido ou gravado fora da trava da ficha: {vistos}")


def test_a_correcao_de_parte_le_a_linha_dentro_da_trava_da_ficha(con, monkeypatch):
    m, _, (pedro,) = _ficha_vendida(con, (VENDEDOR, CPF_VENDEDOR))
    vistos = _vigiar_o_quadro(monkeypatch, RC.chave_dos_titulares(m))
    RC.corrigir_parte(con, pedro, qualificacao="brasileiro, solteiro, lavrador",
                      agora=AGORA, motivo="Qualificação conferida no título")
    # o primeiro comando só acha de qual ficha é a parte, para saber a trava
    depois_de_achar = vistos[1:]
    assert depois_de_achar and all(presa for _, presa in depois_de_achar), vistos
    assert any("FOR UPDATE" in s for s, _ in depois_de_achar), (
        f"a correção leu a linha sem prendê-la: {vistos}")


def _psycopg_puro(con, *, autocommit=False):
    """Uma conexão do psycopg no schema do teste, SEM a ponte — como a
    transação vai ficar quando a ponte sair."""
    import psycopg
    esquema = banco(con).valor("SELECT current_schema() AS s")
    pg = psycopg.connect(banco_pg.dsn(), autocommit=autocommit)
    pg.execute(f'SET search_path TO "{esquema}", public')
    if not autocommit:
        pg.commit()
    return pg


def _presa(vigia, parte_id: int) -> bool:
    """A linha da parte está presa por outra transação? Não espera por ela."""
    import psycopg
    try:
        vigia.execute("SELECT id FROM ri_partes WHERE id=%s FOR UPDATE NOWAIT",
                      (int(parte_id),))
    except psycopg.errors.LockNotAvailable:
        return True
    return False


def _ao_mesmo_tempo(con, primeira, segunda):
    """A `primeira` grava e ainda não confirmou; a `segunda` chega no meio,
    por outra conexão. Devolve (o erro da segunda ou None, se ela esperou)."""
    um, dois = _psycopg_puro(con), _psycopg_puro(con)
    vigia = _psycopg_puro(con, autocommit=True)
    pid = banco(dois).valor("SELECT pg_backend_pid() AS pid")
    primeira(um)
    saida: dict = {}

    def no_fio():
        try:
            segunda(dois)
            dois.commit()
        except Exception as erro:  # o teste confere qual
            saida["erro"] = erro
            dois.rollback()

    fio = threading.Thread(target=no_fio)
    fio.start()
    esperou = False
    for _ in range(100):          # a segunda tem de estar ESPERANDO
        if banco(vigia).valor(
                "SELECT count(*) AS n FROM pg_locks WHERE pid=%s AND NOT granted",
                (pid,)):
            esperou = True
            break
        time.sleep(0.05)
    um.commit()
    fio.join(30)
    for c in (um, dois, vigia):
        c.close()
    return saida.get("erro"), esperou


@sem_a_ponte
def test_os_xaras_lidos_ficam_presos_ate_o_fim_da_transacao(con):
    """A decisão «homônimo: ninguém sai» vale enquanto as linhas lidas não
    mudam — e elas não são gravadas. Sem `FOR UPDATE`, nada as segura."""
    m, a, (pedro, xara) = _ficha_vendida(con, (VENDEDOR, None), (VENDEDOR, None))
    con.commit()
    um, vigia = _psycopg_puro(con), _psycopg_puro(con, autocommit=True)
    try:
        saida = RC.titulares_que_transmitiram(um, m, a, _venda(doc_vendedor=None))
        presos = [_presa(vigia, x) for x in (pedro, xara)]
    finally:
        um.rollback()
        um.close()
        vigia.close()
    assert saida["sairam"] == [] and saida["a_conferir"]
    assert presos == [True, True], "os xarás lidos não ficaram presos"


@sem_a_ponte
def test_a_correcao_do_homonimo_no_meio_e_vista_por_quem_tira_o_vendedor(con):
    """A correção «o xará não é titular» está gravando quando a lavratura vai
    tirar o vendedor. Quem tira espera por ela e lê o quadro já corrigido: o
    vendedor é o único com o nome e sai. Sem esperar, leria os dois xarás e
    ninguém sairia — com a correção já confirmada um instante depois."""
    m, a, (pedro, xara) = _ficha_vendida(con, (VENDEDOR, None), (VENDEDOR, None))
    con.commit()
    quadro: dict = {}

    def corrige(c):
        RC.corrigir_parte(c, xara, titular=False, agora=AGORA,
                          motivo="Homônimo do vendedor, não é titular desta ficha")

    def tira(c):
        quadro.update(RC.titulares_que_transmitiram(c, m, a, _venda(doc_vendedor=None)))

    erro, esperou = _ao_mesmo_tempo(con, corrige, tira)
    assert erro is None, erro
    assert esperou, "quem tira o vendedor não esperou a correção que estava no meio"
    assert quadro == {"sairam": [VENDEDOR], "a_conferir": []}, quadro
    assert [n for _, n in _ativos(con, m)] == [COMPRADORA]


@sem_a_ponte
def test_por_de_volta_o_vendedor_no_meio_da_saida_dele_nao_se_perde(con):
    """Venda de parte ideal: o oficial põe o vendedor de volta como titular
    («Corrigir», titular) enquanto a lavratura o tira. Lida solta, a linha
    ainda dizia «titular» — a correção virava «Nada foi alterado» e o vendedor
    ficava fora. Presa, a correção espera, lê a saída e o põe de volta."""
    m, a, (pedro,) = _ficha_vendida(con, (VENDEDOR, CPF_VENDEDOR))
    con.commit()

    def tira(c):
        assert RC.titulares_que_transmitiram(c, m, a, _venda())["sairam"] == [VENDEDOR]

    def devolve(c):
        RC.corrigir_parte(c, pedro, titular=True, agora=AGORA,
                          motivo="Venda de parte ideal: continua condômino")

    erro, esperou = _ao_mesmo_tempo(con, tira, devolve)
    assert erro is None, f"a correção que chegou no meio se perdeu: {erro}"
    assert esperou
    assert pedro in [i for i, _ in _ativos(con, m)]


# ------------------------------------- o chamador em laço: acatar a leitura da IA
#
# RESSALVA DA REVISÃO DO LD10, LD13 (21/10/2026, «nenhuma pendência»).
# `corrigir_parte` lê de qual ficha é a parte antes de pegar a trava, e
# `ri_onus_ia.acatar_proprietarios` a chama em laço, na transação dela. O laço
# só corrige partes da MESMA ficha e não prende linha de outra antes — mas
# decidia quem sai do quadro numa leitura solta. Agora a trava da ficha vem
# antes da lista, e as linhas lidas ficam presas, na ordem do renumerar.

def _leitura_da_ia_pronta(con, m: int, proprietarios: list[dict]) -> None:
    """A leitura da IA terminada sobre a ficha como ela está (o `hash_ficha`
    é o de agora), dizendo quem é o dono de hoje."""
    import json

    import ri_onus_ia as RONIA
    RONIA.init_schema(con)
    banco(con).escrever(
        """INSERT INTO ri_onus_sugestoes
               (matricula_id, hash_ficha, dossie, situacao, pedido_em, resultado_json)
           VALUES (%s, %s, 'dossiê do teste', 'PRONTA', %s, %s)""",
        (m, RONIA.hash_da_ficha(con, m), AGORA,
         json.dumps({"proprietarios": proprietarios, "proprietarios_ato": "R-01",
                     "itens": []})))


def test_acatar_a_leitura_da_ia_decide_quem_sai_dentro_da_trava_da_ficha(con, monkeypatch):
    """A lista de titulares de onde sai quem a IA não leu como dono se lê com
    a trava da ficha já pega e com as linhas presas — a mesma ordem de quem
    tira o transmitente e de quem corrige a parte. Lida solta, uma saída ou
    uma correção no meio mudava o quadro entre a decisão e a gravação."""
    import ri_onus_ia as RONIA
    m = matricula(con, 4100, "2")
    pedro = parte(con, m, None, VENDEDOR, "proprietário", CPF_VENDEDOR, ativo=1)
    a = ato(con, m, "R", 1, "4100",
            f"R-01/4100 COMPRA E VENDA. ADQUIRENTE: {COMPRADORA}, CPF {CPF_COMPRADORA}.")
    beatriz = parte(con, m, a, COMPRADORA, "adquirente", CPF_COMPRADORA, ativo=1)
    _leitura_da_ia_pronta(con, m, [{"nome": COMPRADORA, "documento": CPF_COMPRADORA}])
    vistos = _vigiar_o_quadro(monkeypatch, RC.chave_dos_titulares(m), modulo=RONIA)

    feito = RONIA.acatar_proprietarios(con, m, agora=AGORA, usuario="carla")

    assert [s["parte_id"] for s in feito["desligados"]] == [pedro], feito
    assert [i for i, _ in _ativos(con, m)] == [beatriz]
    leituras = [(s, presa) for s, presa in vistos if s.startswith("SELECT")]
    assert leituras and all(presa for _, presa in leituras), (
        f"o quadro foi lido fora da trava da ficha: {vistos}")
    assert all("FOR UPDATE" in s for s, _ in leituras), (
        f"o quadro foi lido sem prender as linhas: {vistos}")
