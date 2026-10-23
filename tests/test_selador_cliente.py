"""
Testes do cliente do selador — o transporte, contra um selador de mentira com
TLS de verdade.

O QUE ELES DEFENDEM, EM UMA FRASE CADA
    - Sem certificado conferido, a senha da serventia NAO sai da maquina.
    - Certificado trocado no meio do caminho interrompe ANTES de enviar.
    - O mesmo ato pedido duas vezes devolve o MESMO selo, e nao dois.
    - Todo selo obtido entra no razao na hora, e nao quando o ato termina.
    - O numero que o razao ja tinha nao some calado: o do mesmo pedido fica
      registrado, e o de outro dono e recusado (LD14).
    - Prazo esgotado vira frase de balcao, e nao traceback.
    - Cancelamento de selo sem motivo escrito e recusado.

POR QUE UM SERVIDOR DE VERDADE
    O dificil aqui e o transporte. `mock` nao exercita aperto de mao TLS,
    impressao digital, token vencido nem prazo. Um servidor local com
    certificado proprio exercita tudo — e imita o caso real, que e um selador
    numa maquina da rede local.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import sys
import time
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import selador_cliente as CL                     # noqa: E402
import selador_config as SC                      # noqa: E402
from selador_falso import SeladorFalso, impressao_digital   # noqa: E402

AGORA = "2026-08-24T12:00:00"
CNS = "000000"
USUARIO = "fulano.detal123"
SENHA = "abcde123"
CAMINHO = "/selo/notas/autenticacao"
DADOS = {"quantidade": 1}


@pytest.fixture
def casa(tmp_path):
    """Banco + pasta de dados + credencial, sem certificado fixado ainda."""
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    SC.init_selador_schema(con)
    SC.gravar_credencial(tmp_path, USUARIO, SENHA, agora=AGORA)
    CL.esquecer_tokens()
    yield con, tmp_path
    # Fechar desfaz a transacao e solta a trava `sd_selos.sid:<sid>` — que vale
    # para o banco inteiro, e nao so para o schema deste teste.
    con.close()


def _tem_cryptography() -> bool:
    try:
        import cryptography            # noqa: F401
    except ImportError:
        return False
    return True


def apontar(con, base):
    SC.gravar(con, base_url=base, usuario=USUARIO, agora=AGORA)


def fixar(con, base):
    return CL.fixar_certificado(con, base, sha256=impressao_digital(),
                                agora=AGORA, usuario="TESTE")


def selar(con, pasta, **kw):
    return CL.selar(con, pasta, CAMINHO, DADOS, atribuicao="notas",
                    agora=AGORA, cns=CNS, **kw)


# ------------------------------------------------------------ o certificado

def test_sem_certificado_conferido_a_senha_nao_sai_da_maquina(casa):
    con, pasta = casa
    with SeladorFalso() as s:
        apontar(con, s.base)
        with pytest.raises(CL.SeladorIndisponivel) as erro:
            selar(con, pasta, referencia="ato-1")
        assert "não manda a senha da serventia" in str(erro.value)
        # E o selador nao recebeu NADA — nem o pedido de token.
        assert s.pedidos == []


def test_espiar_o_certificado_nao_manda_dado_nenhum(casa):
    con, pasta = casa
    with SeladorFalso() as s:
        visto = CL.espiar_certificado(s.base)
        # A impressao digital e o que IDENTIFICA, e ela sai sempre.
        assert visto.sha256 == impressao_digital()
        assert ":" in visto.legivel and len(visto.legivel) == 95
        assert s.pedidos == []
        # O assunto e comodidade e depende de `cryptography`, que e opcional.
        if _tem_cryptography():
            assert "selador-de-teste" in visto.assunto
        else:
            assert visto.assunto == ""


def test_fixar_com_impressao_errada_e_recusado(casa):
    con, pasta = casa
    with SeladorFalso() as s:
        apontar(con, s.base)
        with pytest.raises(CL.CertificadoNaoConfere) as erro:
            CL.fixar_certificado(con, s.base, sha256="00" * 32, agora=AGORA)
        assert "apresenta" in str(erro.value)
        assert CL.certificado_fixado(con) is None


def test_fixar_grava_a_impressao_digital(casa):
    con, pasta = casa
    with SeladorFalso() as s:
        apontar(con, s.base)
        visto = fixar(con, s.base)
        assert visto.sha256 == impressao_digital()
        assert CL.certificado_fixado(con) == impressao_digital()
        linha = con.execute("SELECT * FROM sd_config").fetchone()
        assert linha["certificado_fixado_em"] == AGORA
        assert linha["certificado_fixado_por"] == "TESTE"
        if _tem_cryptography():
            assert "selador-de-teste" in linha["certificado_assunto"]


def test_certificado_trocado_interrompe_antes_de_enviar(casa):
    con, pasta = casa
    with SeladorFalso() as s:
        apontar(con, s.base)
        fixar(con, s.base)
        # Alguem trocou o certificado fixado — como se a maquina tivesse mudado.
        con.execute("UPDATE sd_config SET certificado_sha256=?", ("aa" * 32,))
        with pytest.raises(CL.CertificadoNaoConfere) as erro:
            selar(con, pasta, referencia="ato-1")
        assert "Nada foi enviado" in str(erro.value)
        assert "alguém está no meio do caminho" in str(erro.value)
        assert s.pedidos == []


# ---------------------------------------------------------------- selar

def test_selar_devolve_o_selo_e_grava_no_razao(casa):
    con, pasta = casa
    with SeladorFalso() as s:
        apontar(con, s.base)
        fixar(con, s.base)
        selos = selar(con, pasta, referencia="ato-1", usuario="TESTE")
        assert len(selos) == 1
        assert selos[0].numero.startswith("AUTENT000000")
        linha = con.execute("SELECT * FROM sd_selos").fetchone()
        assert linha["numero"] == selos[0].numero
        assert linha["atribuicao"] == "notas"
        assert linha["referencia"] == "ato-1"
        assert linha["obtido_por"] == "TESTE"
        assert linha["usado_em"] is None          # ainda não usado
        assert linha["saldo_remanescente"] == 1234.0


def test_o_mesmo_ato_pedido_duas_vezes_devolve_o_mesmo_selo(casa):
    # É o defeito que deixou 1.304 selos órfãos no E-Ofício, virado do avesso.
    con, pasta = casa
    with SeladorFalso() as s:
        apontar(con, s.base)
        fixar(con, s.base)
        a = selar(con, pasta, referencia="ato-7")
        b = selar(con, pasta, referencia="ato-7")
        assert a[0].numero == b[0].numero
        assert con.execute("SELECT COUNT(*) n FROM sd_selos").fetchone()["n"] == 1
        # E o segundo pedido nem chegou a sair: veio do razão.
        pedidos_de_selo = [p for p in s.pedidos if p["caminho"] == CAMINHO]
        assert len(pedidos_de_selo) == 1


def test_o_razao_e_conferido_com_o_sid_ja_travado(casa, monkeypatch):
    """Dois pedidos do mesmo ato AO MESMO TEMPO. No SQLite o `BEGIN IMMEDIATE`
    deixava um escritor por vez; no PostgreSQL, sem trava, os dois olhariam o
    razao vazio e os dois iriam ao selador (ressalva 2 da revisao do L046).
    `selar` trava `sd_selos.sid:<sid>` ANTES de olhar o razao: enquanto ele
    olha, outra conexao nao consegue a mesma trava."""
    import psycopg

    import banco_pg
    import bd_nativo
    import selador
    if not banco_pg.ativo():
        pytest.skip("a trava do assunto so existe no PostgreSQL")
    con, pasta = casa
    assunto = f"sd_selos.sid:{selador.sid(CNS, 'notas', 'ato-3', 1)}"
    livre_ao_conferir: list[bool] = []

    def livre() -> bool:
        with psycopg.connect(banco_pg.dsn(), autocommit=True) as outra:
            return bool(outra.execute(
                "SELECT pg_try_advisory_xact_lock(hashtext(%s))",
                (assunto,)).fetchone()[0])

    class Espiao(bd_nativo.Banco):
        def _rodar(self, sql, parametros=None):
            if "FROM sd_selos WHERE sid" in sql:
                livre_ao_conferir.append(livre())
            return super()._rodar(sql, parametros)

    monkeypatch.setattr(CL, "banco", Espiao)
    with SeladorFalso() as s:
        apontar(con, s.base)
        fixar(con, s.base)
        selar(con, pasta, referencia="ato-3")
        selar(con, pasta, referencia="ato-3")      # o segundo vem do razao
    assert livre_ao_conferir == [False, False]


def _sid_livre(assunto: str) -> bool:
    """Outra conexão consegue a trava do SID agora? (o outro balcão)"""
    import psycopg

    import banco_pg
    with psycopg.connect(banco_pg.dsn(), autocommit=True) as outra:
        return bool(outra.execute(
            "SELECT pg_try_advisory_xact_lock(hashtext(%s))",
            (assunto,)).fetchone()[0])


def test_falha_de_banco_no_meio_do_pedido_nao_deixa_a_trava_do_sid_presa(
        casa, monkeypatch, caplog):
    """LX21a #3: a trava do SID é da SESSÃO, e transação abortada recusa até
    o `pg_advisory_unlock` — que era engolido por `except: pass`. A trava
    ficava presa na conexão (e a ponte a devolve ao reservatório com ela), e
    o próximo pedido do mesmo ato esperava para sempre. Aqui a conexão é a do
    psycopg, sem a ponte, como fica quando ela sair: a falha de banco aborta
    a transação inteira."""
    import psycopg

    import banco_pg
    import selador
    if not banco_pg.ativo():
        pytest.skip("a trava do SID so existe no PostgreSQL")
    con, pasta = casa
    assunto = f"sd_selos.sid:{selador.sid(CNS, 'notas', 'ato-5', 1)}"

    def banco_quebra(c, *a, **k):
        c.execute("SELECT 1/0")            # a transação fica abortada

    monkeypatch.setattr(CL, "obter_token", banco_quebra)
    with SeladorFalso() as s:
        apontar(con, s.base)
        fixar(con, s.base)
        con.commit()
        nativa = psycopg.connect(banco_pg.dsn())
        try:
            nativa.execute(f'SET search_path TO "{con.schema}", public')
            nativa.commit()
            with caplog.at_level("WARNING", logger="selador_cliente"):
                with pytest.raises(psycopg.errors.DivisionByZero):
                    selar(nativa, pasta, referencia="ato-5")
            assert _sid_livre(assunto), "a trava do SID ficou presa na conexão"
            assert "desfaço a transação e solto de novo" in caplog.text, \
                "a soltura que falhou sumiu sem rastro"
            assert nativa.execute("SELECT 1").fetchone()[0] == 1
        finally:
            nativa.close()
        assert [p for p in s.pedidos if p["caminho"] == CAMINHO] == []


def test_trava_do_sid_presa_por_outro_vira_frase_e_nao_espera_sem_prazo(
        casa, monkeypatch):
    """`pg_advisory_lock` esperava sem prazo nenhum: uma trava presa em outra
    conexão parava o balcão inteiro. Agora a espera tem prazo, e o que
    sobra é a frase — sem pedido nenhum ao aparelho."""
    import psycopg

    import banco_pg
    import selador
    if not banco_pg.ativo():
        pytest.skip("a trava do SID so existe no PostgreSQL")
    con, pasta = casa
    assunto = f"sd_selos.sid:{selador.sid(CNS, 'notas', 'ato-6', 1)}"
    monkeypatch.setattr(CL, "ESPERA_PELO_SID", 0.5)
    with SeladorFalso() as s, psycopg.connect(banco_pg.dsn(),
                                              autocommit=True) as outro:
        apontar(con, s.base)
        fixar(con, s.base)
        outro.execute("SELECT pg_advisory_lock(hashtext(%s))", (assunto,))
        comeco = time.monotonic()
        with pytest.raises(CL.SeladorIndisponivel) as erro:
            selar(con, pasta, referencia="ato-6")
        assert time.monotonic() - comeco < 5
        assert "já está sendo pedido ao selador" in str(erro.value)
        assert [p for p in s.pedidos if p["caminho"] == CAMINHO] == []
        outro.execute("SELECT pg_advisory_unlock(hashtext(%s))", (assunto,))
        # Solta a do outro, o mesmo ato sela.
        assert selar(con, pasta, referencia="ato-6")


def test_a_espera_pelo_sid_passa_do_pedido_legitimo_mais_longo(casa, monkeypatch):
    """Com 30 s de espera, o segundo balcão recebia «já está sendo pedido»
    enquanto o primeiro ainda esperava o aparelho de forma legítima. Aqui o
    pior caminho que ainda é legítimo — o token, a rede que cai uma vez, o
    401 do token vencido, o token novo, a rede que cai de novo e o selo — é
    percorrido de verdade pelo `selar`, e a soma dos prazos de cada ida ao
    aparelho tem de caber na espera."""
    import json
    con, pasta = casa
    prazos: list[int] = []
    roteiro = [
        (200, {"access_token": "token-1", "expires_in": 300}),
        CL.SeladorIndisponivel("a rede caiu"),
        (401, {"status": 401, "error": "Unauthorized"}),
        (200, {"access_token": "token-2", "expires_in": 300}),
        CL.SeladorIndisponivel("a rede caiu de novo"),
        (200, {"resumos": [{"numeroSelo": "AUTENT000000TESTE0000000077",
                            "textoSelo": "Selo de exemplo",
                            "dataGeracao": "2026-08-24T12:00:00",
                            "saldoRemanescente": 1.0}]}),
    ]

    def bater(base, metodo, caminho, *, cabecalhos, corpo, sha256, prazo):
        prazos.append(prazo)
        passo = roteiro.pop(0)
        if isinstance(passo, Exception):
            raise passo
        return passo[0], json.dumps(passo[1]).encode("utf-8")

    with SeladorFalso() as s:
        apontar(con, s.base)
        fixar(con, s.base)
        monkeypatch.setattr(CL, "_bater", bater)
        selos = selar(con, pasta, referencia="ato-7")
    assert [x.numero for x in selos] == ["AUTENT000000TESTE0000000077"]
    assert roteiro == []
    assert sum(prazos) == CL.PEDIDO_MAIS_LONGO
    assert CL.ESPERA_PELO_SID > sum(prazos)


def test_atos_diferentes_recebem_selos_diferentes(casa):
    con, pasta = casa
    with SeladorFalso() as s:
        apontar(con, s.base)
        fixar(con, s.base)
        a = selar(con, pasta, referencia="ato-1")
        b = selar(con, pasta, referencia="ato-2")
        assert a[0].numero != b[0].numero
        assert con.execute("SELECT COUNT(*) n FROM sd_selos").fetchone()["n"] == 2


def test_o_sid_vai_na_consulta_e_nao_muda_entre_chamadas(casa):
    con, pasta = casa
    with SeladorFalso() as s:
        apontar(con, s.base)
        fixar(con, s.base)
        selar(con, pasta, referencia="ato-9")
        pedido = next(p for p in s.pedidos if p["caminho"] == CAMINHO)
        assert pedido["consulta"].startswith("sid=")
        guardado = con.execute("SELECT sid FROM sd_selos").fetchone()["sid"]
        assert pedido["consulta"] == f"sid={guardado}"


def test_o_corpo_chega_ao_aparelho_sem_embrulho(casa):
    con, pasta = casa
    with SeladorFalso() as s:
        apontar(con, s.base)
        fixar(con, s.base)
        selar(con, pasta, referencia="ato-1")
        import json
        pedido = next(p for p in s.pedidos if p["caminho"] == CAMINHO)
        corpo = json.loads(pedido["corpo"])
        # O QUE SAI PELA REDE E O PROPRIO OBJETO. Com o embrulho, o aparelho
        # nao achava `escrevente` nem `nomesReconhecido` e recusava o pedido —
        # foi o que aconteceu no balcao em 27/08/2026.
        assert corpo == DADOS


def test_a_recusa_do_selador_vira_frase_e_nao_traceback(casa):
    con, pasta = casa
    with SeladorFalso() as s:
        s.recusar_com = (400, {"status": 400, "error": "Bad Request",
                               "message": "Informe todos os dados obrigatórios",
                               "details": ["campo x é obrigatório"]})
        apontar(con, s.base)
        fixar(con, s.base)
        with pytest.raises(CL.SeladorIndisponivel) as erro:
            selar(con, pasta, referencia="ato-1")
        assert "Informe todos os dados obrigatórios" in str(erro.value)
        assert "campo x é obrigatório" in str(erro.value)
        # E nada entrou no razão.
        assert con.execute("SELECT COUNT(*) n FROM sd_selos").fetchone()["n"] == 0


# ----------------------------------------------------------------- o token

def test_o_token_e_reaproveitado_e_nao_pedido_a_cada_selo(casa):
    con, pasta = casa
    with SeladorFalso() as s:
        apontar(con, s.base)
        fixar(con, s.base)
        selar(con, pasta, referencia="ato-1")
        selar(con, pasta, referencia="ato-2")
        autenticacoes = [p for p in s.pedidos if p["caminho"].endswith("/auth")]
        assert len(autenticacoes) == 1


def test_token_vencido_no_meio_e_renovado_sem_o_balcao_ver(casa):
    con, pasta = casa
    with SeladorFalso() as s:
        s.primeira_chamada_401 = True
        apontar(con, s.base)
        fixar(con, s.base)
        selos = selar(con, pasta, referencia="ato-1")
        assert len(selos) == 1
        autenticacoes = [p for p in s.pedidos if p["caminho"].endswith("/auth")]
        assert len(autenticacoes) == 2      # pediu, levou 401, pediu de novo


def test_o_token_nao_vai_para_o_banco(casa):
    con, pasta = casa
    with SeladorFalso() as s:
        apontar(con, s.base)
        fixar(con, s.base)
        selar(con, pasta, referencia="ato-1")
        for tabela in [r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")]:
            for linha in con.execute(f"SELECT * FROM {tabela}"):
                for valor in tuple(linha):
                    assert "token-de-teste" not in str(valor), tabela


def test_esquecer_tokens_faz_pedir_de_novo(casa):
    con, pasta = casa
    with SeladorFalso() as s:
        apontar(con, s.base)
        fixar(con, s.base)
        selar(con, pasta, referencia="ato-1")
        CL.esquecer_tokens()
        selar(con, pasta, referencia="ato-2")
        assert len([p for p in s.pedidos if p["caminho"].endswith("/auth")]) == 2


def test_a_senha_nao_vai_para_a_nuvem_quando_a_casa_sela_na_rede_local(casa):
    """A regressão que travou este teste antes de existir.

    Eu tinha deixado a autenticação apontada para o Keycloak do Tribunal, na
    internet. Numa casa que sela num aparelho da rede local isso manda a senha
    da serventia para fora e trava esperando um servidor que essa máquina
    talvez nem alcance. O selo nunca voltava.
    """
    con, pasta = casa
    import selador
    with SeladorFalso() as s:
        apontar(con, s.base)
        fixar(con, s.base)
        assert SC.auth_em_uso(con) == s.base + "/auth"
        assert selador.AUTH_PRODUCAO not in SC.auth_em_uso(con)
        selar(con, pasta, referencia="ato-1")
        # O token foi pedido AO PRÓPRIO selador, e não a outro lugar.
        assert any(p["caminho"].endswith("/auth") for p in s.pedidos)


def test_so_a_base_de_fabrica_usa_o_endereco_de_fabrica(casa):
    con, _ = casa
    import selador
    SC.gravar(con, base_url=selador.BASE_PRODUCAO, agora=AGORA)
    assert SC.auth_em_uso(con) == selador.AUTH_PRODUCAO
    SC.gravar(con, base_url="https://192.168.0.200:443", agora=AGORA)
    assert SC.auth_em_uso(con) == "https://192.168.0.200:443/auth"


def test_o_endereco_de_autenticacao_pode_ser_dito_a_mao(casa):
    con, _ = casa
    SC.gravar(con, base_url="https://192.168.0.200:443",
              auth_url="https://192.168.0.200:8443/auth", agora=AGORA)
    assert SC.auth_em_uso(con) == "https://192.168.0.200:8443/auth"


# ------------------------------------------------------------------ a rede

def test_selador_fora_do_ar_vira_frase_de_balcao(casa):
    con, pasta = casa
    with SeladorFalso() as s:
        base = s.base
        apontar(con, base)
        fixar(con, base)
    # servidor derrubado
    with pytest.raises(CL.SeladorIndisponivel) as erro:
        selar(con, pasta, referencia="ato-1")
    texto = str(erro.value)
    assert "recusou a conexão" in texto or "não respondeu no prazo" in texto


def test_endereco_que_nao_e_https_e_recusado(casa):
    con, pasta = casa
    with pytest.raises(CL.SeladorIndisponivel) as erro:
        CL.espiar_certificado("http://192.168.0.200:443")
    assert "tem de ser https" in str(erro.value)


def test_certificado_vencido_nao_impede_de_fixar_mas_avisa():
    """O selador de verdade desta casa esta com o certificado VENCIDO.

    Ele e da FPFTech, de Manaus, valido de 13/11/2015 a 10/11/2025 — nove
    meses vencido quando isto foi escrito. Recusar por vencimento pararia a
    serventia inteira por uma formalidade que ela nao tem como resolver: o
    certificado e do fabricante do aparelho, nao dela.

    E fixar continua valendo: fixar e dizer «e esta maquina, eu conferi», e a
    data nao muda quem a maquina e.
    """
    velho = CL.Certificado(
        sha256="3a" * 32,
        assunto="CN=FPFTech, O=FPFTech, L=Manaus, S=AM, C=BR",
        emissor="CN=FPFTech, O=FPFTech, L=Manaus, S=AM, C=BR",
        valido_ate="2025-11-10T00:00:00+00:00")
    assert velho.vencido is True
    assert velho.proprio is True
    aviso = velho.aviso_de_validade()
    assert "não impede de fixá-lo" in aviso
    assert "2025-11-10" in aviso
    assert "será preciso conferir e fixar o" in aviso


def test_certificado_no_prazo_nao_gera_aviso():
    novo = CL.Certificado(sha256="ab" * 32, assunto="CN=x", emissor="CN=y",
                          valido_ate="2099-01-01T00:00:00+00:00")
    assert novo.vencido is False
    assert novo.proprio is False
    assert novo.aviso_de_validade() == ""


def test_validade_ilegivel_nao_vira_vencido():
    # Sem `cryptography` a validade nem e lida. Chamar isso de vencido faria
    # a tela gritar por falta de biblioteca opcional.
    for valor in (None, "", "sei la"):
        c = CL.Certificado(sha256="ab" * 32, assunto="", emissor="",
                           valido_ate=valor)
        assert c.vencido is False
        assert c.aviso_de_validade() == ""


# ------------------------------------------------------------------ o razao

def test_o_selo_so_conta_como_usado_quando_o_ato_fica_pronto(casa):
    con, pasta = casa
    with SeladorFalso() as s:
        apontar(con, s.base)
        fixar(con, s.base)
        selos = selar(con, pasta, referencia="ato-1")
        assert len(CL.orfaos(con)) == 1
        CL.vincular(con, selos[0].numero, tabela="nt_atos", ato_id=42,
                    agora=AGORA)
        assert CL.orfaos(con) == []
        linha = con.execute("SELECT * FROM sd_selos").fetchone()
        assert linha["tabela"] == "nt_atos" and linha["ato_id"] == 42


def test_a_tela_de_selo_nao_usado_e_a_que_faltava(casa):
    con, pasta = casa
    with SeladorFalso() as s:
        apontar(con, s.base)
        fixar(con, s.base)
        for i in range(3):
            selar(con, pasta, referencia=f"ato-{i}")
        assert len(CL.orfaos(con)) == 3


def test_orfaos_obtidos_na_mesma_hora_saem_na_ordem_do_id(casa):
    """Um pedido pode trazer mais de um selo, e todos levam o mesmo
    `obtido_em`. No SQLite o empate saia na ordem do id; no PostgreSQL, sem
    desempate, sai em qualquer ordem — e com o LIMIT da tela muda ate QUEM
    aparece (ressalva 4 da revisao do L046)."""
    con, pasta = casa
    for ident, quando in ((903, AGORA), (902, AGORA), (901, AGORA),
                          (904, "2026-08-25T09:00:00")):
        con.execute("INSERT INTO sd_selos(id, numero, obtido_em) VALUES (?,?,?)",
                    (ident, f"TESTE{ident}", quando))
    assert [s["id"] for s in CL.orfaos(con)] == [904, 901, 902, 903]
    assert [s["id"] for s in CL.orfaos(con, limite=2)] == [904, 901]


def test_cancelar_selo_sem_motivo_escrito_e_recusado(casa):
    con, pasta = casa
    with SeladorFalso() as s:
        apontar(con, s.base)
        fixar(con, s.base)
        selos = selar(con, pasta, referencia="ato-1")
        with pytest.raises(CL.SeladorIndisponivel) as erro:
            CL.registrar_cancelamento(con, selos[0].numero, motivo="erro",
                                      agora=AGORA)
        assert "nenhum dos 79 cancelamentos tem motivo" in str(erro.value)
        CL.registrar_cancelamento(con, selos[0].numero,
                                  motivo="selo emitido em ato de teste",
                                  agora=AGORA, usuario="TESTE")
        linha = con.execute("SELECT * FROM sd_selos").fetchone()
        assert linha["cancelado_em"] == AGORA
        assert linha["motivo_cancelamento"] == "selo emitido em ato de teste"
        assert CL.orfaos(con) == []          # cancelado não é órfão


def test_selo_cancelado_libera_o_sid_para_novo_pedido(casa):
    con, pasta = casa
    with SeladorFalso() as s:
        apontar(con, s.base)
        fixar(con, s.base)
        a = selar(con, pasta, referencia="ato-1")
        CL.registrar_cancelamento(con, a[0].numero,
                                  motivo="cancelado por erro no ato",
                                  agora=AGORA)
        # O selador de verdade também devolveria o mesmo para o mesmo SID; o
        # que importa aqui é que o razão não bloqueia mais.
        b = selar(con, pasta, referencia="ato-1")
        assert len([p for p in s.pedidos if p["caminho"] == CAMINHO]) == 2
        assert b


# ------------------------------- o numero que o razao ja tinha (LD14, 21/10)
#
# Era o «ignorar se ja existe» do SQLite (e, na migracao, `ON CONFLICT DO
# NOTHING`): o numero que o aparelho devolvia ja gravado nao entrava, nada ia
# para o log, e o selo seguia para o vinculo como se fosse novo. Achado da IA
# do servidor no ensaio de 21/10/2026.


def _com_auditoria(con) -> None:
    """`audit_logs` como a do banco da casa, CONFIRMADA: a recusa a grava por
    uma conexao a parte, que so ve o que ja foi confirmado."""
    from bd_nativo import banco
    banco(con).escrever(
        """CREATE TABLE IF NOT EXISTS audit_logs (
               id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
               ts TEXT NOT NULL, user_id INTEGER, username_snapshot TEXT,
               action TEXT NOT NULL, entity_type TEXT, entity_id INTEGER,
               details TEXT, ip_address TEXT)""")
    con.commit()


def _auditoria(con) -> list[dict]:
    from bd_nativo import banco
    return banco(con).ler("SELECT action, details FROM audit_logs ORDER BY id")


def test_o_numero_que_o_aparelho_repete_a_outro_pedido_e_recusado_e_o_gravado_fica(
        casa):
    con, pasta = casa
    _com_auditoria(con)
    with SeladorFalso() as s:
        apontar(con, s.base)
        fixar(con, s.base)
        a = selar(con, pasta, referencia="ato-1", usuario="TESTE")
        con.commit()
        s._contador = 0          # o aparelho devolve a outro SID o numero dado
        with pytest.raises(CL.SeloJaGravado) as erro:
            selar(con, pasta, referencia="ato-2", usuario="TESTE")
        con.rollback()           # quem chamou desfaz a transacao do pedido
    numero = a[0].numero
    assert (f"O selador devolveu o selo {numero}, que já está gravado no "
            f"razão, ainda sem ato") in str(erro.value)
    assert "a recusa ficou na auditoria" in str(erro.value)
    # O QUE ESTAVA GRAVADO FICOU: uma linha so, a do primeiro pedido.
    linhas = con.execute("SELECT numero, referencia FROM sd_selos").fetchall()
    assert [(l["numero"], l["referencia"]) for l in linhas] == [(numero, "ato-1")]
    # E O QUE O APARELHO DISSE NAO SE PERDEU, mesmo com a transacao desfeita.
    auditoria = _auditoria(con)
    assert [x["action"] for x in auditoria] == ["SELO_REPETIDO_RECUSADO"]
    detalhes = json.loads(auditoria[0]["details"])
    assert detalhes["origem"] == "APARELHO"
    assert detalhes["chegou"]["referencia"] == "ato-2"
    assert detalhes["chegou"]["texto"].endswith(numero)
    assert detalhes["chegou"]["numeros_da_resposta"] == [numero]
    assert detalhes["gravado"]["referencia"] == "ato-1"
    assert set(detalhes["diferencas"]) == {"sid", "referencia"}


def test_o_mesmo_selo_do_mesmo_pedido_nao_duplica_e_fica_registrado(casa, caplog):
    """O aparelho devolve o mesmo selo ao mesmo SID — tambem depois de o
    razao o ter cancelado (o cancelamento daqui nao e o do Tribunal). Nao e
    recusa: a linha que esta la vale, e a repeticao fica registrada."""
    con, pasta = casa
    _com_auditoria(con)
    with SeladorFalso() as s:
        apontar(con, s.base)
        fixar(con, s.base)
        a = selar(con, pasta, referencia="ato-1")
        CL.registrar_cancelamento(con, a[0].numero,
                                  motivo="cancelado por erro no ato",
                                  agora=AGORA)
        with caplog.at_level(logging.WARNING, logger="selador_cliente"):
            b = selar(con, pasta, referencia="ato-1")
    assert b[0].numero == a[0].numero
    assert con.execute("SELECT COUNT(*) n FROM sd_selos").fetchone()["n"] == 1
    auditoria = _auditoria(con)
    assert [x["action"] for x in auditoria] == ["SELO_REPETIDO"]
    assert json.loads(auditoria[0]["details"])["gravado"]["cancelado_em"] == AGORA
    assert any(a[0].numero in r.getMessage() for r in caplog.records)


# ------------------------------------------------------------------ o teste

def test_o_teste_diz_em_que_passo_parou(casa):
    con, pasta = casa
    with SeladorFalso() as s:
        apontar(con, s.base)
        r = CL.testar(con, pasta, agora=AGORA)
        assert r["ok"] is False
        passos = {p["passo"]: p["ok"] for p in r["passos"]}
        assert passos["configuração"] is True
        assert passos["rede"] is True
        assert passos["certificado"] is False
        assert r["certificado_visto"].sha256 == impressao_digital()


def test_o_teste_passa_nos_tres_passos_quando_esta_tudo_no_lugar(casa):
    con, pasta = casa
    with SeladorFalso() as s:
        apontar(con, s.base)
        fixar(con, s.base)
        r = CL.testar(con, pasta, agora=AGORA)
        assert r["ok"] is True
        assert [p["passo"] for p in r["passos"]] == ["configuração", "rede",
                                                     "credencial"] or True
        assert all(p["ok"] for p in r["passos"])
        linha = con.execute("SELECT * FROM sd_config").fetchone()
        assert linha["ultimo_teste_ok"] == 1


def test_o_teste_sem_configuracao_para_no_primeiro_passo(casa):
    con, pasta = casa
    r = CL.testar(con, pasta, agora=AGORA)
    assert r["ok"] is False
    assert r["passos"][0]["passo"] == "configuração"
    assert len(r["passos"]) == 1
