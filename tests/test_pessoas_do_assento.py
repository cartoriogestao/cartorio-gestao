"""A pessoa de quem o assento é — o registrado, os nubentes, o falecido.

O BURACO QUE ISTO FECHA
    Até 28/08/2026 `rc_pessoas` guardava **pai, mãe e avós** — que a carga
    trouxe porque a certidão de nascimento os cobrou — e não guardava a pessoa
    principal. O assento tinha o **nome** dela e mais nada.

    Duas coisas paravam nisso ao mesmo tempo, e por isso é uma passada só:

      - a **remessa do IBGE**, que pede sexo, data de nascimento, naturalidade,
        residência e estado civil dessas pessoas;
      - a **certidão de casamento e a de óbito**, que descrevem essas mesmas
        pessoas e saíam incompletas.

O QUE O ENSAIO CONTRA O ACERVO REAL ACHOU, E OS TESTES DE REGRA NÃO ACHARIAM
    **1. A chave era do assento, e não da pessoa.** `rc_pessoas` tem
    `UNIQUE(origem, origem_chave)`, e os dois nubentes moram na MESMA linha do
    acervo. Com a chave do assento, o NUBENTE1 entrava e o NUBENTE2 era
    ignorado em silêncio pelo `OR IGNORE` — a carga dizia «entraram 20» e a
    tabela tinha **zero**.

    **2. O contador contava tentativa, e não entrada.** Foi ele que deixou o
    defeito acima visível em vez de calado: se contasse certo, teria dito zero
    e eu teria procurado; dizendo 20, ele confirmava o engano.

    **3. Vinte e uma pessoas «nascem» depois do próprio ato.** Medido: 7 dos 20
    casamentos em cada cônjuge, 6 dos 193 nascimentos e 1 dos 31 óbitos. O
    valor guardado não é a data de nascimento — é o dia em que alguém digitou o
    registro antigo, com o campo em branco pegando a data de hoje.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.lento  # gate rapido: pytest -m "not lento" — acervo/prod references
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import acervo_carga as AC                        # noqa: E402
from nucleo_schema import init_nucleo_schema     # noqa: E402
from rc_schema import init_rc_schema             # noqa: E402

AGORA = "2026-08-28T12:00:00"
ACERVO_REAL = Path(r"C:\ProgramData\CartorioGestao\acervo_eoficio.sqlite3")
PAPEIS = ("REGISTRADO", "NUBENTE1", "NUBENTE2", "FALECIDO")


@pytest.fixture()
def banco():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    init_nucleo_schema(con)
    init_rc_schema(con)
    return con


# ------------------------------------------------------ a regra, só


def test_ninguem_nasce_depois_do_ato_que_o_registra():
    """A conferência que recusa as 21 datas sujas do acervo."""
    assert AC._nascimento_possivel("1980-05-10", "2026-04-01")
    assert AC._nascimento_possivel("2026-04-01", "2026-04-01")   # no mesmo dia
    assert not AC._nascimento_possivel("2026-04-02", "2026-04-01")


def test_sem_uma_das_duas_datas_nao_ha_o_que_comparar():
    """Recusar por falta de comparação seria jogar fora dado bom."""
    assert AC._nascimento_possivel(None, "2026-04-01")
    assert AC._nascimento_possivel("1980-05-10", None)
    assert AC._nascimento_possivel("", "")


def test_o_papel_entra_na_chave_de_origem():
    """Os dois nubentes moram na mesma linha do acervo, e `rc_pessoas` tem
    `UNIQUE(origem, origem_chave)`. Sem o papel na chave, o segundo é ignorado
    em silêncio — a carga diz que entrou e a tabela fica vazia."""
    codigo = (RAIZ / "acervo_carga.py").read_text(encoding="utf-8")
    i = codigo.find("def _o_proprio_assento_que_falta")
    trecho = codigo[i:i + 6000]
    assert "origem_chave\"]}:{papel}" in trecho or "origem_chave']}:{papel}" in trecho


def test_os_quatro_papeis_estao_declarados():
    """Espécie sem papel declarado é assento que entra sem a pessoa principal,
    e o defeito só aparece na certidão, meses depois."""
    achados = {papel for papeis in AC.O_PROPRIO_ASSENTO.values()
               for papel, _, _ in papeis}
    assert achados == set(PAPEIS)
    # e cada espécie sabe de onde puxar
    assert set(AC.O_PROPRIO_ASSENTO) == {"NASCIMENTO", "CASAMENTO", "OBITO"}


def test_o_lugar_do_nascimento_vem_da_coluna_que_esta_cheia():
    """`strUF`/`strCidade` estão em 193 de 193; `strUFNascido`/`strCidadeNascido`
    em 22. Escolher pelo nome mais parecido teria perdido 171 assentos, calado."""
    _, _, de_para = AC.O_PROPRIO_ASSENTO["NASCIMENTO"][0]
    assert de_para["naturalidade_uf"] == "strUF"
    assert de_para["naturalidade_cidade"] == "strCidade"


# ---------------------------------------------- contra o acervo real
#
# TESTE DE REGRA PROVA A REGRA; ENSAIO CONTRA O ACERVO PROVA O DADO. Os três
# defeitos do cabeçalho deste arquivo passaram pelos testes de regra e só
# apareceram aqui.


@pytest.mark.skipif(not ACERVO_REAL.exists(),
                    reason="o acervo do E-Ofício não está nesta máquina")
def test_contra_o_acervo_real(banco):
    acervo = sqlite3.connect(f"file:{ACERVO_REAL}?mode=ro", uri=True)
    acervo.row_factory = sqlite3.Row
    r = AC.carregar_rcpn(banco, acervo, agora=AGORA).como_dict()

    assert r["inseridos"] == 244
    # As pessoas do próprio assento: 193 registrados, 20+20 nubentes, 31
    # falecidos. Se algum dia isso mudar, é aqui que se vê.
    assert r["contagens"]["pessoas_registrado"] == 193
    assert r["contagens"]["pessoas_nubente1"] == 20
    assert r["contagens"]["pessoas_nubente2"] == 20
    assert r["contagens"]["pessoas_falecido"] == 31


@pytest.mark.skipif(not ACERVO_REAL.exists(),
                    reason="o acervo do E-Ofício não está nesta máquina")
def test_o_contador_bate_com_a_tabela(banco):
    """A prova do defeito nº 2: contar tentativa em vez de entrada faz o
    número da tela concordar com o engano em vez de denunciá-lo."""
    acervo = sqlite3.connect(f"file:{ACERVO_REAL}?mode=ro", uri=True)
    acervo.row_factory = sqlite3.Row
    r = AC.carregar_rcpn(banco, acervo, agora=AGORA).como_dict()
    for papel in PAPEIS:
        na_tabela = banco.execute(
            "SELECT COUNT(*) n FROM rc_pessoas WHERE papel=?",
            (papel,)).fetchone()["n"]
        assert r["contagens"][f"pessoas_{papel.lower()}"] == na_tabela, papel


@pytest.mark.skipif(not ACERVO_REAL.exists(),
                    reason="o acervo do E-Ofício não está nesta máquina")
def test_as_vinte_e_uma_datas_impossiveis_ficam_de_fora_e_avisadas(banco):
    """Elas não entram, e a rejeição fica escrita com o número do assento —
    para quem for à estante saber a quais ir.

    Certidão com data de nascimento falsa e IBGE com idade absurda são os dois
    piores que o campo vazio: campo vazio não afirma nada.
    """
    acervo = sqlite3.connect(f"file:{ACERVO_REAL}?mode=ro", uri=True)
    acervo.row_factory = sqlite3.Row
    r = AC.carregar_rcpn(banco, acervo, agora=AGORA).como_dict()

    sem_data = banco.execute(
        "SELECT COUNT(*) n FROM rc_pessoas "
        " WHERE papel IN ('REGISTRADO','NUBENTE1','NUBENTE2','FALECIDO')"
        "   AND data_nascimento IS NULL").fetchone()["n"]
    assert sem_data == 21
    assert AC.NASCE_DEPOIS_DO_ATO in r["motivos_do_aviso"]

    # e nenhuma das que entraram é impossível
    ruins = banco.execute(
        "SELECT COUNT(*) n FROM rc_pessoas p JOIN rc_assentos a"
        "    ON a.id = p.assento_id"
        " WHERE p.papel IN ('REGISTRADO','NUBENTE1','NUBENTE2','FALECIDO')"
        "   AND p.data_nascimento IS NOT NULL"
        "   AND p.data_nascimento > COALESCE(a.data_fato, a.data_ato)"
    ).fetchone()["n"]
    assert ruins == 0


@pytest.mark.skipif(not ACERVO_REAL.exists(),
                    reason="o acervo do E-Ofício não está nesta máquina")
def test_o_nome_de_casada_entra_e_e_diferente_do_de_solteira(banco):
    """Medido: o segundo cônjuge muda de nome em 17 dos 20 casamentos, e o
    primeiro em 2. É o nome que a certidão de casamento tem de mostrar."""
    acervo = sqlite3.connect(f"file:{ACERVO_REAL}?mode=ro", uri=True)
    acervo.row_factory = sqlite3.Row
    AC.carregar_rcpn(banco, acervo, agora=AGORA)
    mudou = banco.execute(
        "SELECT COUNT(*) n FROM rc_pessoas"
        " WHERE papel='NUBENTE2' AND COALESCE(nome_pos,'') <> ''"
        "   AND TRIM(nome_pos) <> TRIM(nome)").fetchone()["n"]
    assert mudou == 17


@pytest.mark.skipif(not ACERVO_REAL.exists(),
                    reason="o acervo do E-Ofício não está nesta máquina")
def test_a_carga_e_repetivel(banco):
    """Rodar de novo não duplica ninguém — e a segunda rodada acha zero, porque
    a passada procura assento sem pessoa **daquele papel**."""
    acervo = sqlite3.connect(f"file:{ACERVO_REAL}?mode=ro", uri=True)
    acervo.row_factory = sqlite3.Row
    AC.carregar_rcpn(banco, acervo, agora=AGORA)
    antes = banco.execute("SELECT COUNT(*) n FROM rc_pessoas").fetchone()["n"]
    segunda = AC.carregar_rcpn(banco, acervo, agora=AGORA).como_dict()
    depois = banco.execute("SELECT COUNT(*) n FROM rc_pessoas").fetchone()["n"]
    assert depois == antes
    for papel in PAPEIS:
        assert f"pessoas_{papel.lower()}" not in segunda["contagens"], papel


# ==================================================================
# PELA TELA — o balcão coletando as pessoas ao lavrar
#
# O PAPEL SAI DA ESPÉCIE, E NÃO DO FORMULÁRIO. É a mesma regra da série:
# deixar o balcão escolher o papel seria deixar gravar um nubente num assento
# de óbito, e o defeito só apareceria na certidão, meses depois.
# ==================================================================

import glob      # noqa: E402
import re        # noqa: E402

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(tmp_path):
    from app import create_app
    from database import Database

    dados = tmp_path / "dados"
    dados.mkdir()
    app = create_app({"DATA_DIR": str(dados)})
    banco = Path(glob.glob(f"{dados}/*.sqlite3")[0])
    db = Database(banco)
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c = app.test_client()
    c.post("/login",
           data={"username": "mario", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    bancada = {"app": app, "cliente": c, "banco": banco,
               "dados": dados, "db": db}
    # Estes ensaios medem espécie, pessoas e validações do assento. Desde que
    # falha de selo passou a suspender a lavratura, a bancada precisa do mesmo
    # selador TLS usado pelos testes próprios do selo; sem ele, todos mediriam
    # apenas a guarda global e nunca chegariam ao assunto do arquivo.
    from selador_de_bancada import ligar_o_selador
    with ligar_o_selador(bancada):
        yield bancada


def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _semear_folha(casa) -> str:
    """Uma folha em branco: registro novo só é lavrado depois da conferência."""
    codigo = "9999999"
    con = _con(casa)
    with con:
        con.execute(
            """INSERT INTO pp_remessas(fornecedor, codigo_de, codigo_ate,
                   quantas, recebida_em)
               VALUES ('TESTE', ?, ?, 1, '2026-08-28T00:00:00')""",
            (codigo, codigo))
        rid = con.execute(
            "SELECT id FROM pp_remessas ORDER BY id DESC LIMIT 1").fetchone()[0]
        con.execute(
            """INSERT INTO pp_folhas(codigo, remessa_id, situacao, criada_em)
               VALUES (?,?,'EM BRANCO','2026-08-28T00:00:00')""",
            (codigo, rid))
    con.close()
    return codigo


def _minimo_legal(especie="NASCIMENTO"):
    if especie in ("NASCIMENTO", "NATIMORTO"):
        d = {"pessoa_nome": "FULANO DE TAL", "pessoa_sexo": "M",
             "data_fato": "2026-08-20",
             "local_fato_nome": "Hospital Municipal",
             "filiacao1_nome": "MARIA DA SILVA",
             "filiacao2_nome": "IGNORADO",
             "declarante_nome": "MARIA DA SILVA"}
        if especie == "NATIMORTO":
            d["numero_do"] = "12345"
        else:
            d["ibge_local"] = "1"     # relato #130: o SIRC exige «onde nasceu»
        return d
    if especie in ("CASAMENTO", "CASAMENTO_RELIGIOSO"):
        return {"data_fato": "2026-08-20",
                "regime_bens": "COMUNHAO_PARCIAL",
                "nubente1_nome": "FULANO DE TAL",
                "nubente2_nome": "BELTRANA DE TAL",
                "filiacao1n1_nome": "ANA", "filiacao2n1_nome": "IGNORADO",
                "filiacao1n2_nome": "RITA", "filiacao2n2_nome": "IGNORADO",
                "testemunha_nome": "CICLANO"}
    if especie == "OBITO":
        return {"pessoa_nome": "FULANO DE TAL", "data_fato": "2026-08-01",
                "local_fato_nome": "Hospital Municipal",
                "numero_do": "98765",
                "filiacao1_nome": "IGNORADO", "filiacao2_nome": "IGNORADO",
                "declarante_nome": "FULANO",
                # relato #130: a CRC exige «deixou bens»
                "obito_possui_bens": "NAO"}
    return {}


def _lavrar(casa, **extra):
    html = casa["cliente"].get("/rcpn/novo").get_data(as_text=True)
    especie = extra.get("especie", "NASCIMENTO")
    dados = {"csrf_token": _token(html), "especie": especie,
             "acao": "lavrar", "folha_seguranca": _semear_folha(casa),
             "nome": "FULANO DE TAL", "data_fato": "2026-08-20"}
    dados.update(_minimo_legal(especie))
    dados.update(extra)
    r = casa["cliente"].post("/rcpn/novo", data=dados, follow_redirects=True)
    fila = _con(casa).execute("SELECT MAX(id) FROM rc_assentos").fetchone()[0]
    return int(fila or 0), r.get_data(as_text=True)


def test_a_tela_pede_a_pessoa_do_registro(casa):
    nascimento = casa["cliente"].get(
        "/rcpn/novo/nascimento").get_data(as_text=True)
    for campo in ("pessoa_sexo", "pessoa_data_nascimento",
                  "pessoa_naturalidade_cidade", "pessoa_naturalidade_uf"):
        assert f'name="{campo}"' in nascimento, campo
    assert 'name="nubente1_nome"' not in nascimento

    casamento = casa["cliente"].get(
        "/rcpn/novo/casamento").get_data(as_text=True)
    for campo in ("nubente1_nome", "nubente2_nome_pos"):
        assert f'name="{campo}"' in casamento, campo
    assert 'name="pessoa_sexo"' not in casamento


def test_a_tela_explica_por_que_a_uf_vai_separada(casa):
    """Há três «Bom Jesus» no Brasil, e sem a UF o sistema não escolhe nenhum."""
    html = casa["cliente"].get(
        "/rcpn/novo/nascimento").get_data(as_text=True)
    assert "Bom Jesus" in html


@pytest.mark.parametrize("rota,presentes,ausentes", [
    ("/rcpn/novo/nascimento",
     ("pessoa_nome", "dnv", "ibge_local", "prog1f1_nome"),
     ("nubente1_nome", "numero_do", "regime_bens")),
    ("/rcpn/novo/casamento",
     ("nubente1_nome", "nubente2_nome", "regime_bens", "filiacao1n1_nome"),
     ("pessoa_nome", "dnv", "numero_do", "cor_raca")),
    ("/rcpn/novo/obito",
     ("pessoa_nome", "numero_do", "natureza_obito", "declarante_nome"),
     ("nubente1_nome", "dnv", "regime_bens", "prog1f1_nome")),
])
def test_cada_registro_mostra_so_os_campos_que_lhe_cabem(
        casa, rota, presentes, ausentes):
    html = casa["cliente"].get(rota).get_data(as_text=True)
    for campo in presentes:
        assert f'name="{campo}"' in html, f"{campo} faltou em {rota}"
    for campo in ausentes:
        assert f'name="{campo}"' not in html, f"{campo} vazou para {rota}"


def test_a_porta_de_escolha_nao_repete_o_formulario_misturado(casa):
    html = casa["cliente"].get("/rcpn/novo").get_data(as_text=True)
    assert "/rcpn/novo/nascimento" in html
    assert "/rcpn/novo/casamento" in html
    assert "/rcpn/novo/obito" in html
    assert 'id="form-do-ato"' not in html


def test_a_url_fixa_a_especie_mesmo_se_o_post_for_adulterado(casa):
    c = casa["cliente"]
    html = c.get("/rcpn/novo/nascimento").get_data(as_text=True)
    r = c.post("/rcpn/novo/nascimento", data={
        "csrf_token": _token(html), "especie": "OBITO",
        "acao": "lavrar", "folha_seguranca": _semear_folha(casa),
        "pessoa_nome": "CRIANÇA DA SILVA", "pessoa_sexo": "F",
        "data_fato": "2026-08-31",
        "local_fato_nome": "Hospital Municipal",
        "ibge_local": "1",            # relato #130: o SIRC exige
        "filiacao1_nome": "MARIA DA SILVA",
        "filiacao2_nome": "IGNORADO",
        "declarante_nome": "MARIA DA SILVA",
    }, follow_redirects=True)
    assert "Assento lavrado" in r.get_data(as_text=True)
    a = _con(casa).execute("SELECT especie, serie FROM rc_assentos").fetchone()
    assert dict(a) == {"especie": "NASCIMENTO", "serie": "RC_A"}


def test_o_nascimento_grava_o_registrado(casa):
    aid, _ = _lavrar(casa, pessoa_sexo="M",
                     pessoa_data_nascimento="2026-08-20",
                     pessoa_naturalidade_cidade="Cidade Exemplo",
                     pessoa_naturalidade_uf="MA")
    p = _con(casa).execute(
        "SELECT * FROM rc_pessoas WHERE assento_id=? AND papel='REGISTRADO'",
        (aid,)).fetchall()
    assert len(p) == 1
    assert p[0]["sexo"] == "M"
    assert p[0]["naturalidade_cidade"] == "Cidade Exemplo"


def test_o_casamento_grava_os_dois_nubentes(casa):
    aid, _ = _lavrar(
        casa, especie="CASAMENTO", nome="FULANO E BELTRANA",
        nubente1_nome="FULANO DE TAL", nubente1_sexo="M",
        nubente1_data_nascimento="1990-03-02",
        nubente2_nome="BELTRANA DE TAL", nubente2_sexo="F",
        nubente2_nome_pos="BELTRANA DE TAL SILVA",
        nubente2_data_nascimento="1992-07-11")
    p = _con(casa).execute(
        "SELECT * FROM rc_pessoas WHERE assento_id=? AND papel LIKE 'NUBENTE%' "
        "ORDER BY ordem",
        (aid,)).fetchall()
    assert [x["papel"] for x in p] == ["NUBENTE1", "NUBENTE2"]
    assert p[1]["nome_pos"] == "BELTRANA DE TAL SILVA"


def test_o_obito_grava_o_falecido_pelo_mesmo_bloco(casa):
    """Um bloco só serve o registrado e o falecido — os campos são os mesmos,
    e duas cópias divergiriam no primeiro conserto."""
    aid, _ = _lavrar(casa, especie="OBITO", nome="FULANO DE TAL",
                     pessoa_sexo="M", pessoa_estado_civil="Viúvo",
                     pessoa_data_nascimento="1940-01-01")
    p = _con(casa).execute(
        "SELECT * FROM rc_pessoas WHERE assento_id=? AND papel='FALECIDO'",
        (aid,)).fetchall()
    assert len(p) == 1
    assert p[0]["estado_civil"] == "Viúvo"


def test_preencher_o_bloco_errado_nao_grava_papel_errado(casa):
    """O papel sai da ESPÉCIE. Quem digitar nos nubentes num nascimento não
    grava nubente nenhum — e não recebe erro por isso: o campo simplesmente
    não é daquela espécie."""
    aid, _ = _lavrar(casa, especie="NASCIMENTO", nubente1_nome="NINGUÉM",
                     nubente2_nome="NINGUÉM TAMBÉM")
    papeis = [x["papel"] for x in _con(casa).execute(
        "SELECT papel FROM rc_pessoas WHERE assento_id=?", (aid,))]
    assert "NUBENTE1" not in papeis and "NUBENTE2" not in papeis


def test_nada_digitado_nao_grava_linha_de_pessoa(casa):
    """Quem não perguntar avós e testemunha não inventa essas linhas.
    Filiação e declarante a lei exige — ou o nome, ou ignorado."""
    aid, _ = _lavrar(casa)
    papeis = {x["papel"] for x in _con(casa).execute(
        "SELECT papel FROM rc_pessoas WHERE assento_id=?", (aid,))}
    assert "AVO_MATERNO" not in papeis
    assert "TESTEMUNHA" not in papeis


def test_data_de_nascimento_impossivel_derruba_o_lancamento(casa):
    """Ninguém nasce depois do próprio ato. A recusa é no balcão, onde ainda
    dá para perguntar — e não meses depois, numa certidão já assinada."""
    antes = _con(casa).execute(
        "SELECT COUNT(*) n FROM rc_assentos").fetchone()["n"]
    _, html = _lavrar(casa, data_fato="2026-08-20",
                      pessoa_data_nascimento="2026-09-01")
    assert "posterior ao próprio ato" in html
    assert _con(casa).execute(
        "SELECT COUNT(*) n FROM rc_assentos").fetchone()["n"] == antes


# ---------------------------------- acervo de outra safra não derruba a carga
#
# O E-OFÍCIO MUDOU DE VERSÃO AO LONGO DOS ANOS, e nem todo acervo tem as mesmas
# colunas. Pedir uma coluna que não existe **não devolve vazio: estoura** — e
# derruba a carga inteira, que é o defeito que a carga do Livro 3 já cometeu.
#
# Quem achou isto foi a suíte completa: 29 testes caíram de uma vez porque o
# acervo de teste não tinha `intCodigoLocalNascimento`. Num acervo real de outra
# serventia daria no mesmo.


def _acervo_magro():
    """Um acervo com o mínimo: nome, número, livro — e nada do IBGE."""
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript("""
        CREATE TABLE tbRegistroNascimento (
            intChave REAL, strNomeNascido TEXT, dtmDataNascimento TEXT,
            dtmDataAssento TEXT, strNumeroMatricula TEXT,
            intNumeroRegistro REAL, strLivro TEXT, strTipoLivro TEXT,
            intFolha REAL, strSexo TEXT, memTexto TEXT);
        INSERT INTO tbRegistroNascimento VALUES
            (1.0,'FULANO DE TAL','2026-08-20','2026-08-21','',900,'24','A',
             10,'Masculino','');
        CREATE TABLE tbPropriedadeRCPN (strPropriedade TEXT, strValor TEXT);
    """)
    return con


def test_acervo_sem_as_colunas_do_ibge_nao_derruba_a_carga(banco):
    """A carga entrega o que dá, e o que falta fica vazio — não estoura."""
    r = AC.carregar_rcpn(banco, _acervo_magro(), agora=AGORA).como_dict()
    assert "erro" not in r
    assert r["inseridos"] == 1
    linha = banco.execute("SELECT * FROM rc_assentos").fetchone()
    assert linha["ibge_local_nascimento"] is None
    assert linha["dnv"] is None


def test_o_registrado_entra_mesmo_no_acervo_magro(banco):
    """Ele não depende de coluna nenhuma do IBGE: o nome vem do assento."""
    AC.carregar_rcpn(banco, _acervo_magro(), agora=AGORA)
    p = banco.execute(
        "SELECT * FROM rc_pessoas WHERE papel='REGISTRADO'").fetchall()
    assert len(p) == 1
    assert p[0]["nome"] == "FULANO DE TAL"


def test_o_de_para_do_local_do_nascimento_sai_do_acervo(banco):
    """O E-Ofício numera de 1 a 5 e o IBGE **não tem 4**: ele pula do 3 para o 5.

    A tradução estava no próprio acervo, numa coluna chamada `intCodigoIBGE` —
    e mandar o código de lá direto faria o IBGE recusar o trimestre inteiro,
    meses depois, sem dizer qual linha.
    """
    from tests.test_acervo_carga import acervo_falso   # noqa: E402
    acervo = acervo_falso()
    de_para = {int(r["id"]): int(r["intCodigoIBGE"]) for r in acervo.execute(
        "SELECT id, intCodigoIBGE FROM tbRCPN_LocalNascimento")}
    assert de_para[4] == 5, "«Outros» do E-Ofício é o 5 do IBGE, e não o 4"
    assert de_para[5] == 9
    assert 4 not in de_para.values()


# ==================================================================
# QUEM É PAI E QUEM É MÃE — o sexo decide, e o código do acervo não é confiável
#
# O QUE ESTAVA ESCRITO ERA `{1: "PAI", 2: "MAE"}`, com um comentário dizendo que
# era medido. O que se mediu foram os PARES por registro (2 em 196 de 196), e
# não QUEM é quem dentro do par. Medido agora, no acervo inteiro:
#
#     NASCIMENTO  código 1 -> 162 masculinos e **30 femininos**
#     ÓBITO       código 1 ->  19 masculinos e **12 femininos**
#
# E há o caso que decide: `(1, Feminino, BIANCA PEREIRA GOMES)` com
# `(2, Masculino, BENTO GOMES DE SAMPAIO)` — os dois com nome, e trocados.
#
# O ESTRAGO, se o código mandasse: 30 certidões de nascimento e 12 de óbito com
# a MÃE no lugar do PAI, e a remessa do IBGE usando a pessoa errada para a
# residência e para a idade da genitora.
# ==================================================================


def _linhas(*trios):
    """(código, sexo, nome) -> as linhas como `tbFiliacao` as devolve."""
    return [{"intCodigoFiliacao": c, "strSexo": s, "strNome": n}
            for c, s, n in trios]


def test_o_sexo_decide_quando_os_dois_discordam():
    """O caso comum, e o que conserta os 42 registros trocados."""
    papeis, duvida = AC.papeis_da_filiacao(
        1, _linhas((1, "Feminino", "JOSEFA"), (2, "Masculino", "MANOEL")))
    assert papeis == {1: "MAE", 2: "PAI"}
    assert not duvida


def test_o_codigo_desempata_quando_o_sexo_falta():
    """Quatro linhas de nascimento e três de óbito não têm sexo nenhum."""
    papeis, duvida = AC.papeis_da_filiacao(
        1, _linhas((1, "", "FULANO"), (2, "", "BELTRANA")))
    assert papeis == {1: "PAI", 2: "MAE"}
    assert not duvida


def test_um_sexo_so_decide_os_dois():
    """Se um diz «Feminino», o outro é o pai — a invariante é mais forte que
    o silêncio do acervo."""
    papeis, _ = AC.papeis_da_filiacao(
        1, _linhas((1, "Feminino", "JOSEFA"), (2, "", "MANOEL")))
    assert papeis == {1: "MAE", 2: "PAI"}


def test_dois_do_mesmo_sexo_nao_viram_dois_pais(banco):
    """A correção de uma regra minha que estava certa em 42 casos e errada em 1
    — e o errado era pior que o problema original.

    No registro 19532 o acervo marca **as duas pessoas como «Masculino»** —
    WANDERSON e VALQUIANE, e «Valquiane» é nome feminino: o sexo é que está
    errado ali. Com a regra linha a linha saíam dois pais e nenhuma mãe, e a
    mãe sumia da certidão e da remessa do IBGE.

    A invariante é mais forte que os dois sinais: **um assento tem um pai e uma
    mãe.**
    """
    papeis, duvida = AC.papeis_da_filiacao(
        1, _linhas((1, "Masculino", "WANDERSON"),
                   (2, "Masculino", "VALQUIANE")))
    assert papeis == {1: "PAI", 2: "MAE"}
    assert duvida, "o par contraditório tem de virar aviso, e não silêncio"


def test_o_casamento_tem_quatro_filiacoes_e_nao_duas():
    """Os códigos 1 e 2 são os pais do PRIMEIRO cônjuge, e 3 e 4 os do SEGUNDO.

    Conferido pelos sobrenomes, que casam um a um: BARROS/BANDEIRA para NELSON
    FALCAO BARROS, e CIRQUEIRA PIMENTEL/PINHEIRO MILHOMEM para EDNA
    SERRA MONTEIRO.

    Lendo só 1 e 2, os pais do segundo cônjuge **nunca entravam**, e a certidão
    de casamento mostrava uma filiação só, como se fosse «a» filiação — quem
    lesse concluiria que aqueles eram os pais dos dois.
    """
    papeis, _ = AC.papeis_da_filiacao(2, _linhas(
        (1, "Masculino", "BOAVENTURA"), (2, "Feminino", "ADELAIDE"),
        (3, "Masculino", "DIONÍSIO"), (4, "Feminino", "AURORA")))
    assert papeis == {1: "PAI_NUBENTE1", 2: "MAE_NUBENTE1",
                      3: "PAI_NUBENTE2", 4: "MAE_NUBENTE2"}


@pytest.mark.skipif(not ACERVO_REAL.exists(),
                    reason="o acervo do E-Ofício não está nesta máquina")
def test_contra_o_acervo_nenhum_assento_tem_dois_pais(banco):
    """A invariante, provada sobre os 244 assentos reais."""
    acervo = sqlite3.connect(f"file:{ACERVO_REAL}?mode=ro", uri=True)
    acervo.row_factory = sqlite3.Row
    AC.carregar_rcpn(banco, acervo, agora=AGORA)
    repetidos = banco.execute(
        "SELECT assento_id, papel, COUNT(*) n FROM rc_pessoas"
        " WHERE papel IN ('PAI','MAE') GROUP BY 1,2 HAVING n > 1").fetchall()
    assert not repetidos, [dict(r) for r in repetidos]


@pytest.mark.skipif(not ACERVO_REAL.exists(),
                    reason="o acervo do E-Ofício não está nesta máquina")
def test_contra_o_acervo_os_pais_dos_dois_conjuges_entram(banco):
    """Vinte e três pessoas que se perdiam — os pais do segundo cônjuge."""
    acervo = sqlite3.connect(f"file:{ACERVO_REAL}?mode=ro", uri=True)
    acervo.row_factory = sqlite3.Row
    AC.carregar_rcpn(banco, acervo, agora=AGORA)
    conta = dict(banco.execute(
        "SELECT papel, COUNT(*) FROM rc_pessoas"
        " WHERE papel LIKE '%NUBENTE%' AND papel <> 'NUBENTE1'"
        "   AND papel <> 'NUBENTE2' GROUP BY papel").fetchall())
    assert conta == {"PAI_NUBENTE1": 12, "MAE_NUBENTE1": 12,
                     "PAI_NUBENTE2": 12, "MAE_NUBENTE2": 12}


@pytest.mark.skipif(not ACERVO_REAL.exists(),
                    reason="o acervo do E-Ofício não está nesta máquina")
def test_o_par_contraditorio_vira_aviso(banco):
    """Se os dois se dizem do mesmo sexo, um deles está errado no acervo — e a
    certidão pode sair com o pai no lugar da mãe. Quem for à estante precisa
    saber quais conferir."""
    acervo = sqlite3.connect(f"file:{ACERVO_REAL}?mode=ro", uri=True)
    acervo.row_factory = sqlite3.Row
    r = AC.carregar_rcpn(banco, acervo, agora=AGORA).como_dict()
    assert AC.FILIACAO_COM_SEXO_REPETIDO in r["motivos_do_aviso"]


def test_get_do_formulario_nao_lavra(casa):
    """GET não escreve. A conferência legal é da lavratura, e lavratura é POST."""
    antes = _con(casa).execute("SELECT COUNT(*) n FROM rc_assentos").fetchone()["n"]
    casa["cliente"].get("/rcpn/novo/nascimento")
    casa["cliente"].get("/rcpn/novo/casamento")
    casa["cliente"].get("/rcpn/novo/obito")
    depois = _con(casa).execute("SELECT COUNT(*) n FROM rc_assentos").fetchone()["n"]
    assert antes == depois
