"""A costura da remessa do IBGE: de onde vem cada valor.

`ibge_remessa.py` sabe o FORMATO; `ibge_geracao.py` sabe a PROCEDÊNCIA. Estes
testes guardam a segunda, e em especial as três regras que o formato não
expressa e que, erradas, produzem arquivo aceito e mentiroso:

  1. **UF, município e país andam juntos.** Mandar o código de São Luís com a
     UF 98 diria que São Luís fica no estrangeiro.

  2. **O estado civil do casamento não é o do óbito.** No casamento `2` é
     viúvo; no óbito `2` é casado. Usar um pelo outro faria o sistema declarar
     que a viúva era casada — a mesma palavra em dois lugares outra vez.

  3. **O que não se sabe se declara como ignorado**, com noves, e isso é o que
     o próprio IBGE manda (item 14). Não é permissão para mandar tudo em 9: é a
     forma honesta de dizer «não sei», e por isso `conferir` conta quantos
     saíram assim. Remessa cheia de «ignorado» é remessa aceita e inútil.
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

import ibge_geracao as G          # noqa: E402
import ibge_remessa as IBGE       # noqa: E402
import ibge_schema as IB          # noqa: E402

CABECALHO = {"ibge_uf": "21", "ibge_municipio": "98765",
             "ibge_distrito": "05", "ibge_cartorio": "01"}


@pytest.fixture()
def municipios():
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    IB.init_ibge_schema(con)
    for cod, uf_cod, mun, uf, nome in (
            (2198765, 21, "98765", "MA", "Cidade Exemplo"),
            (2111300, 21, "11300", "MA", "São Luís"),
            (3550308, 35, "50308", "SP", "São Paulo"),
            # DOIS «BOM JESUS», que é o caso que a busca sem UF tem de recusar.
            (2101905, 21, "01905", "MA", "Bom Jesus das Selvas"),
            (4302501, 43, "02501", "RS", "Bom Jesus"),
            (2301000, 23, "01000", "CE", "Bom Jesus")):
        con.execute(
            """INSERT INTO ib_municipios(codigo_ibge, codigo_uf, codigo_mun,
                   uf, nome, nome_norm, criado_em)
               VALUES (?,?,?,?,?,?,'2026-08-28')""",
            (cod, uf_cod, mun, uf, nome, IB.normalizar_nome(nome)))
    return con


# ------------------------------------------------ UF, município e país


def test_o_lugar_devolve_os_tres_juntos(municipios):
    r = G.lugar(municipios, "São Luís", "MA")
    assert (r["uf"], r["municipio"], r["pais"]) == ("21", "11300", "076")
    assert r["achou"]


def test_acha_sem_acento_e_sem_caixa(municipios):
    for escrito in ("sao luis", "SAO LUIS", "  São   Luís "):
        assert G.lugar(municipios, escrito, "MA")["municipio"] == "11300"


def test_nome_repetido_sem_uf_nao_se_escolhe(municipios):
    """Há três «Bom Jesus». Escolher o primeiro poria a estatística no estado
    errado, e ninguém notaria nunca."""
    r = G.lugar(municipios, "Bom Jesus", None)
    assert not r["achou"]
    assert (r["uf"], r["municipio"], r["pais"]) == ("99", "99999", "999")
    # com a UF, acha
    assert G.lugar(municipios, "Bom Jesus", "RS")["municipio"] == "02501"


def test_nome_unico_sem_uf_pode_ser_achado(municipios):
    """«Cidade Exemplo» só existe uma vez no Brasil."""
    assert G.lugar(municipios, "Cidade Exemplo", None)["achou"]


def test_nao_achou_nao_inventa(municipios):
    """Escolher o município mais parecido seria assinar por quem lavrou."""
    r = G.lugar(municipios, "CIDADE QUE NÃO EXISTE", "MA")
    assert not r["achou"]
    assert r["uf"] == "99" and r["municipio"] == "99999"


def test_o_estrangeiro_segue_a_regra_1_do_item_15(municipios):
    """UF 98 obriga município 99999 — os três campos andam juntos."""
    r = G.lugar_estrangeiro("076")
    assert (r["uf"], r["municipio"], r["pais"]) == ("98", "99999", "076")
    assert G.lugar_estrangeiro(None)["pais"] == "999"


# ------------------------------------------------------- o cabeçalho


def test_o_cabecalho_sai_com_a_largura_certa():
    c = G.cabecalho(CABECALHO)
    assert c["UF-PESQUISA"] == "21"
    assert c["MUN-PESQUISA"] == "98765"
    assert len(c["DIST-PESQUISA"]) == 2 and len(c["COD_CARTORIO"]) == 2


def test_sem_cabecalho_a_remessa_nao_sai_e_a_frase_diz_onde_responder():
    with pytest.raises(G.IbgeError) as erro:
        G.cabecalho({"ibge_uf": "21"})
    texto = str(erro.value)
    assert "código do município" in texto
    assert "acervo" in texto or "Configurações" in texto


# ---------------------------------------------------------- as datas


def test_a_data_vai_com_o_dia_primeiro():
    """O IBGE quer `ddmmaaaa`; o banco guarda `aaaa-mm-dd`."""
    assert G.data_ddmmaaaa("2026-08-28") == "28082026"


def test_sem_data_saem_oito_noves():
    """É o «sem valor» do item 14, e não uma data inventada."""
    for vazio in (None, "", "hoje", "2026-08"):
        assert G.data_ddmmaaaa(vazio) == "99999999"


# ------------------------------------------------------ sexo e idade


def test_o_sexo_sai_do_que_o_sistema_guarda():
    assert (G.sexo("M"), G.sexo("F"), G.sexo("f")) == ("1", "2", "2")
    assert G.sexo(None) == "9" and G.sexo("") == "9"


def test_a_idade_do_falecido_vem_com_a_unidade_de_tempo():
    """Os dois só fazem sentido juntos: `2` é dois anos ou dois dias conforme
    o campo ao lado."""
    assert G.idade_em_anos("1980-05-10", "2026-06-01") == ("046", "4")
    # ainda não tinha feito aniversário
    assert G.idade_em_anos("1980-05-10", "2026-04-01") == ("045", "4")


def test_sem_data_a_idade_e_ignorada_nas_duas_posicoes():
    assert G.idade_em_anos(None, "2026-06-01") == ("999", "9")
    assert G.idade_em_anos("1980-05-10", None) == ("999", "9")


def test_a_idade_da_genitora_respeita_a_faixa_do_ibge():
    assert G.idade_da_genitora("1990-03-02", "2026-08-20") == "36"
    # fora da faixa declarada (10 a 69) vira 99 — é o que o IBGE manda
    assert G.idade_da_genitora("2018-03-02", "2026-08-20") == "99"
    assert G.idade_da_genitora("1940-03-02", "2026-08-20") == "99"
    assert G.idade_da_genitora(None, "2026-08-20") == "99"


# --------------------------------------- os dois estados civis, que diferem


def test_o_estado_civil_do_casamento_nao_e_o_do_obito():
    """A armadilha mais fácil deste módulo, e ela mente sobre a pessoa.

    No casamento `2` é VIÚVO; no óbito `2` é CASADO. Trocar um pelo outro faz
    o sistema declarar que a viúva era casada.
    """
    assert G.estado_civil_do_nubente("viúva") == "2"
    assert G.estado_civil_do_falecido("viúva") == "3"
    assert G.estado_civil_do_falecido("casado") == "2"
    # e no catálogo do casamento não existe «casado» — quem casa não é casado
    assert 2 in G.ESTADO_CIVIL_DO_NUBENTE
    assert G.ESTADO_CIVIL_DO_NUBENTE[2] == "viúva(o)"
    assert IBGE.ESTADO_CIVIL_DO_FALECIDO[2] == "casado"


def test_o_estado_civil_se_acha_pelo_radical_sem_acento():
    """O sistema guarda texto livre: «Solteiro(a)», «SOLTEIRA», «solteiro»."""
    for escrito in ("Solteiro(a)", "SOLTEIRA", "solteiro", "Solteira"):
        assert G.estado_civil_do_nubente(escrito) == "1"
    for escrito in ("Viúvo", "VIUVA", "viúva(o)"):
        assert G.estado_civil_do_falecido(escrito) == "3"


def test_estado_civil_desconhecido_vira_ignorado():
    assert G.estado_civil_do_nubente("amigado") == "9"
    assert G.estado_civil_do_falecido(None) == "9"


# ------------------------------------- a conferência do que saiu ignorado


def test_a_conferencia_conta_o_que_saiu_como_ignorado():
    """A regra do item 14 permite mandar 9 onde não há valor, e uma remessa
    inteira de noves seria ACEITA pelo IBGE — e inútil. Este número é o que
    separa «cumpri a obrigação» de «mandei papel em branco»."""
    boa = IBGE.montar_linha(IBGE.NASCIMENTO, {
        "UF-PESQUISA": "21", "MUN-PESQUISA": "98765", "DIST-PESQUISA": "05",
        "COD_CARTORIO": "01", "TRIM-PESQUISA": "3", "ANO-PESQUISA": "26",
        "NUM-LIVRO": "A-22", "NUM-REGLIV": "8700", "DATAREGDIA": "28",
        "DATAREGMES": "08", "DATA-NASC": "20082026", "LOCAL-NASC": "1",
        "COD-UF-NASC": "21", "COD-MUNIC-NASC": "98765", "GEMEO": "1",
        "SEXO": "1", "COD-UF-NASC-PAI": "21", "COD-PAIS-NASC-PAI": "076",
        "COD-UF-NASC-MAE": "21", "COD-PAIS-NASC-MAE": "076",
        "COD-UF-RES-MAE": "21", "COD-MUNIC-RES-MAE": "98765",
        "COD-PAIS-RES-MAE": "076", "IDADE-GENI": "28", "DN": "1234567890"})
    r = G.conferir([boa], IBGE.NASCIMENTO)
    assert r["linhas"] == 1
    assert r["ignorados"] == 0

    ruim = IBGE.montar_linha(IBGE.NASCIMENTO, {
        "UF-PESQUISA": "21", "MUN-PESQUISA": "98765", "DIST-PESQUISA": "05",
        "COD_CARTORIO": "01", "TRIM-PESQUISA": "3", "ANO-PESQUISA": "26",
        "NUM-LIVRO": "A-22", "NUM-REGLIV": "8700", "DATAREGDIA": "28",
        "DATAREGMES": "08", "DATA-NASC": "99999999", "LOCAL-NASC": "9",
        "COD-UF-NASC": "99", "COD-MUNIC-NASC": "99999", "GEMEO": "9",
        "SEXO": "9", "COD-UF-NASC-PAI": "99", "COD-PAIS-NASC-PAI": "999",
        "COD-UF-NASC-MAE": "99", "COD-PAIS-NASC-MAE": "999",
        "COD-UF-RES-MAE": "99", "COD-MUNIC-RES-MAE": "99999",
        "COD-PAIS-RES-MAE": "999", "IDADE-GENI": "99", "DN": ""})
    r = G.conferir([ruim], IBGE.NASCIMENTO)
    assert r["ignorados"] >= 13
    assert "SEXO" in r["por_campo"]


# --------------------------------- o que o balcão ainda não tem como coletar


def test_a_lista_do_que_falta_e_por_especie():
    """Documentação não avisa ninguém: esta lista vai para a tela.

    Medido em 28/08/2026: `rc_pessoas` guarda pai, mãe e avós — trazidos pela
    carga —, e não o registrado, os nubentes nem o falecido. O IBGE pede sexo,
    data de nascimento, naturalidade, residência e estado civil dessas pessoas.
    """
    assert "sexo do registrado" in G.o_que_falta(None, "NASCIMENTO")
    assert "estado civil dos cônjuges" in G.o_que_falta(None, "CASAMENTO")
    assert "local do óbito" in G.o_que_falta(None, "OBITO")
    assert G.o_que_falta(None, "PROCLAMAS") == []


def test_a_linha_montada_tem_a_largura_do_layout():
    """A prova mais simples, e a que pega campo fora de lugar: 112, 105, 103."""
    for nome, layout, largura in (("nascimento", IBGE.NASCIMENTO, 112),
                                  ("casamento", IBGE.CASAMENTO, 105),
                                  ("óbito", IBGE.OBITO, 103)):
        linha = IBGE.montar_linha(layout, {})
        assert len(linha) == largura, nome


# ==================================================================
# A TELA — e por que ela vem junto com o domínio, e não depois
#
# `montar()` ficou pronto e testado, e este projeto já tem SEIS casos de função
# de domínio pronta que nenhuma tela chamava: `obter_selo`, a remessa da CRA, o
# apontamento do protesto, as telas do núcleo, o edital, o aviso. Em todos eles
# o buraco só apareceu meses depois, no balcão.
# ==================================================================

import glob        # noqa: E402
import io as _io   # noqa: E402
import re          # noqa: E402
import zipfile     # noqa: E402

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
    db.set_settings({"ibge_uf": "21", "ibge_municipio": "98765",
                     "ibge_distrito": "05", "ibge_cartorio": "01"})
    c = app.test_client()
    c.post("/login",
           data={"username": "mario", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {"app": app, "cliente": c, "banco": banco, "db": db}


def _pedir(casa, **dados):
    html = casa["cliente"].get("/rcpn/ibge").get_data(as_text=True)
    dados.setdefault("csrf_token", _token(html))
    return casa["cliente"].post("/rcpn/ibge", data=dados)


def test_a_tela_abre_e_oferece_o_trimestre_anterior(casa):
    """A remessa se manda depois que o trimestre fecha — oferecer o de hoje
    faria o escrevente mandar um trimestre pela metade."""
    html = casa["cliente"].get("/rcpn/ibge").get_data(as_text=True)
    assert "Remessa do IBGE" in html
    assert 'name="trimestre"' in html


def test_sem_atos_a_tela_diz_onde_procurar(casa):
    """Lista vazia que só mostra nada faz o operador achar que quebrou."""
    html = _pedir(casa, ano=2026, trimestre=1).get_data(as_text=True)
    assert "Nenhum ato registrado" in html
    # O TRECHO É CURTO DE PROPÓSITO: o template quebra a linha no meio da
    # frase, e procurar «carga do acervo» inteiro falharia por causa da
    # quebra — e não por causa da tela.
    assert "acervo já rodou" in html


def test_sem_o_cabecalho_a_remessa_recusa_e_diz_onde_responder(casa):
    """O IBGE não tem como saber de que cartório é a remessa, e recusa tudo."""
    casa["db"].set_settings({"ibge_municipio": ""})
    html = _pedir(casa, ano=2026, trimestre=2).get_data(as_text=True)
    assert "código do município" in html


def test_a_conferencia_vem_antes_do_botao_de_baixar(casa):
    """O IBGE ACEITA uma remessa inteira de noves, e ela não serve para nada.

    Quem manda precisa ver quantas posições saíram como «ignorado» antes de
    mandar — cumprir a obrigação e mandar papel em branco parecem a mesma coisa
    do lado de fora.
    """
    html = (RAIZ / "templates" / "rcpn_ibge.html").read_text(encoding="utf-8")
    assert "ignorado" in html
    assert html.index("ignorado") < html.index("Baixar CARTINF.ZIP")


def test_a_tela_esta_no_menu_do_registro_civil():
    """A remessa é obrigação de quem lavra, e não do administrativo."""
    base = (RAIZ / "templates" / "base.html").read_text(encoding="utf-8")
    assert "rcpn_ibge" in base


def test_o_arquivo_baixa_zipado_e_em_iso_8859_1(casa):
    """Acento em dois bytes empurraria todos os campos da linha para a direita,
    e o arquivo é de largura fixa. É a mesma lição do arquivo da CRA."""
    con = sqlite3.connect(casa["banco"])
    con.execute(
        """INSERT INTO rc_assentos (serie, especie, numero, nome, data_ato,
               data_fato, livro_volume, situacao, origem, criado_em)
           VALUES ('RC_A','NASCIMENTO',900,'FULANO DE TAL','2026-05-10',
                   '2026-05-01','A-24','ATIVO','MANUAL','2026-05-10T09:00')""")
    aid = con.execute("SELECT MAX(id) FROM rc_assentos").fetchone()[0]
    con.execute(
        """INSERT INTO rc_atos (assento_id, tipo, data_ato, criado_em)
           VALUES (?, 'REGISTRO', '2026-05-10', '2026-05-10T09:00')""", (aid,))
    con.commit()

    r = _pedir(casa, ano=2026, trimestre=2, acao="baixar")
    assert r.mimetype == "application/zip"
    # O NOME É `CARTINF.ZIP`, e só ele — 28/10/2026, «diz nome errado».
    assert "CARTINF.ZIP" in r.headers["Content-Disposition"]
    with zipfile.ZipFile(_io.BytesIO(r.get_data())) as z:
        nomes = z.namelist()
        # OS SEIS, como o E-Ofício exportava, mesmo os que não têm linha
        assert nomes == list(G.ARQUIVOS_DO_ZIP)
        assert z.read("CARTINF04.TXT") == b"" and z.read("CONTROLE.SIS") == b""
        resumo = z.read("CARTINF10.TXT").decode("latin-1").splitlines()
        bruto = z.read("CARTINF01.TXT")
    # o RC-10: o livro com o primeiro e o último número, e a linha zerada
    campos = IBGE.ler_linha(IBGE.RC10, resumo[0])
    assert campos["NUM-LIVRO"].strip() == "A24"
    assert campos["PRI-TRIMES"] == "0000900" == campos["ULT-TRIMES"]
    assert campos["TNASCIDOS"] == "00001"
    assert IBGE.ler_linha(IBGE.RC10, resumo[1])["NUM-LIVRO"].strip() == ""
    assert len(resumo) == 2
    # ISO-8859-1 e terminador CRLF, como o layout pede
    # O TERMINADOR É CRLF, e a constante é a do layout: escrever o
    # literal aqui deixaria o teste concordar com um engano meu.
    assert bruto.endswith(IBGE.FIM_DE_LINHA.encode("latin-1"))
    linha = bruto.decode("latin-1").splitlines()[0]
    assert len(linha) == 112
    # e o livro sai na forma do IBGE: `A24`, sem hífen
    de, ate = IBGE.posicoes(IBGE.NASCIMENTO)["NUM-LIVRO"]
    assert linha[de:ate].strip() == "A24"


def test_trimestre_que_nao_existe_e_recusado_com_frase_de_balcao():
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    with pytest.raises(G.IbgeError, match="1, 2, 3 e 4"):
        G.montar(con, ano=2026, trimestre=5, config=CABECALHO)


def test_o_recorte_do_trimestre_esta_certo():
    """Fevereiro de ano bissexto tem 29, e o quarto trimestre acaba em 31/12."""
    assert G._do_trimestre(2026, 1) == ("2026-01-01", "2026-03-31")
    assert G._do_trimestre(2024, 1) == ("2024-01-01", "2024-03-31")
    assert G._do_trimestre(2026, 4) == ("2026-10-01", "2026-12-31")


def test_o_assento_sem_numero_sai_na_mesma_ordem_que_no_sqlite():
    """`ORDER BY a.numero` punha o NULL primeiro no SQLite e põe por último no
    PostgreSQL. A ordem das linhas é a do teor que congela com sha256 na
    entrega; ela não pode mudar só porque o banco mudou."""
    from nucleo_schema import init_nucleo_schema
    from rc_schema import init_rc_schema

    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    for iniciar in (init_nucleo_schema, init_rc_schema, IB.init_ibge_schema):
        iniciar(con)
    # O NUMERADO ENTRA PRIMEIRO, com o id menor: sem o `NULLS FIRST`, o
    # desempate por id não esconderia a troca.
    for numero, nome in ((7, "FULANO DE TAL"), (None, "BELTRANO DE TAL")):
        con.execute(
            """INSERT INTO rc_assentos (serie, especie, numero, nome, data_ato,
                   data_fato, livro_volume, situacao, origem, criado_em)
               VALUES ('RC_A','NASCIMENTO',?,?,'2026-05-10','2026-05-01',
                       'A-24','ATIVO','MANUAL','2026-05-10T09:00')""",
            (numero, nome))
        aid = con.execute("SELECT MAX(id) AS id FROM rc_assentos").fetchone()["id"]
        con.execute(
            """INSERT INTO rc_atos (assento_id, tipo, data_ato, criado_em)
               VALUES (?, 'REGISTRO', '2026-05-10', '2026-05-10T09:00')""",
            (aid,))

    r = G.montar(con, ano=2026, trimestre=2, config=CABECALHO)
    numeros = [IBGE.ler_linha(IBGE.NASCIMENTO, linha)["NUM-REGLIV"].strip().lstrip("0")
               for linha in r["arquivos"]["CARTINF01.TXT"]]
    assert numeros == ["", "7"]


# ------------------------------------------------ a chave é a do IBGE


def test_o_codigo_do_municipio_e_o_do_ibge_e_o_banco_nao_inventa_outro():
    """`ib_municipios.codigo_ibge` é o código de sete dígitos do IBGE, e não um
    número nosso. Com IDENTITY, um INSERT sem o código ganhava 1, 2... por
    conta própria, e a remessa mandaria ao IBGE um município que não existe.
    O certo é recusar, como a carga do acervo recusa a linha sem código."""
    con = conexao_de_teste()
    try:
        IB.init_ibge_schema(con)
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(
                """INSERT INTO ib_municipios(codigo_uf, codigo_mun, uf, nome,
                       nome_norm, criado_em)
                   VALUES (21, '98765', 'MA', 'Cidade Exemplo',
                           'cidade exemplo', '2026-08-28')""")
    finally:
        con.close()


def test_assento_lavrado_aqui_vai_com_o_livro_do_ato():
    """28/10/2026: os assentos que este sistema lavra não têm `livro_volume`
    (que é o volume do livro de papel do acervo), e iam ao IBGE sem livro. O
    livro deles é o do ato, aberto aqui."""
    novo = {"especie": "NASCIMENTO", "livro_volume": None, "ato_livro_id": 2}
    assert G.numero_do_livro(G._com_o_livro_do_ato(novo, {2: 24})) == "A24"
    do_acervo = {"especie": "OBITO", "livro_volume": "5", "ato_livro_id": 9}
    assert G._com_o_livro_do_ato(do_acervo, {9: 7}) is do_acervo

