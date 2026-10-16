"""
Anotacao a margem: revogacao, renuncia e substabelecimento.

O QUE ESTES TESTES PROTEGEM
    Que a revogacao lavrada num livro apareca na margem da procuracao que ela
    revoga, no outro. E, principalmente, que ela apareca NO TRASLADO — que e
    onde o defeito doia: certidao de procuracao revogada saindo limpa.

    A tabela `nt_ato_anotacoes` existia desde o inicio e nenhuma linha do
    sistema a usava. Estes sao os primeiros testes que ela tem.
"""
from __future__ import annotations

import glob
import re
import sqlite3
import sys
import zipfile
from io import BytesIO
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import notas_anotacoes as NA                   # noqa: E402
import notas_livro as NL                       # noqa: E402
from notas_schema import init_notas_schema     # noqa: E402

AGORA = "2026-08-17T10:00:00"
EXTENSO = "dezessete de agosto de dois mil e vinte e seis"
SV = {
    "unit_name": "SERVENTIA EXTRAJUDICIAL DE CIDADE EXEMPLO",
    "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
    "serventia_titulo": "Tabelião e Oficial de Registro",
    "ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA",
}
SENHA = "Senha#12345"


def banco() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    init_notas_schema(con)
    return con


def procuracao_do_acervo(con, livro="27", folha="139", situacao="LAVRADO") -> int:
    cur = con.execute(
        """INSERT INTO nt_atos(tipo, data, livro, folha, numero_ordem, situacao,
                               interessado, teor, criado_em)
           VALUES ('PROCURACAO','2024-03-11',?,?,100,?, 'MARIA DAS DORES',
                   '<p>poderes amplos</p>', ?)""",
        (livro, folha, situacao, AGORA))
    return int(cur.lastrowid)


def rascunho(con, tipo="REVOGACAO", **kw) -> int:
    cols = {"tipo": tipo, "serie": NL.LIVRO_DO_ATO.get(tipo), "data": "2026-08-17",
            "situacao": "EM_LAVRATURA", "teor": "<p>revogo</p>", "criado_em": AGORA}
    cols.update(kw)
    campos = ",".join(cols)
    marcas = ",".join("?" * len(cols))
    return int(con.execute(f"INSERT INTO nt_atos({campos}) VALUES ({marcas})",
                           tuple(cols.values())).lastrowid)


def lancar(con, ato_id, paginas=2):
    return NL.lancar_ato(con, ato_id, SV, AGORA, EXTENSO, paginas=paginas,
                         usuario="MARIO EXEMPLO DOS SANTOS")


# ------------------------------------------------------------- o texto

def test_o_texto_padrao_diz_o_que_quem_le_a_margem_precisa():
    con = banco()
    NL.abrir_livro(con, "PROCURACAO", SV, AGORA, EXTENSO, folhas=200)
    novo = rascunho(con)
    lancar(con, novo)
    ato = con.execute("SELECT * FROM nt_atos WHERE id=?", (novo,)).fetchone()
    texto = NA.texto_padrao("REVOGACAO", ato, SV)
    assert texto.startswith("REVOGADA")
    assert "CIDADE EXEMPLO" in texto.upper()
    assert "Livro 1" in texto and "folha 1" in texto
    assert "termo nº 1" in texto
    assert texto.endswith(".")


def test_o_texto_da_anotacao_externa_nomeia_a_serventia():
    texto = NA.texto_padrao("REVOGACAO", None, SV, data="2026-05-02",
                            externa=True, serventia_externa="2º Ofício de Imperatriz",
                            cns_externa="012345")
    assert "2º Ofício de Imperatriz" in texto
    assert "012345" in texto
    assert "CIDADE EXEMPLO" not in texto.upper()


def test_a_renuncia_nao_se_escreve_como_revogacao():
    # Revogação é do outorgante; renúncia é do mandatário (CC, art. 682).
    # A situação é a mesma; o texto da margem não pode ser.
    assert "RENÚNCIA DO MANDATÁRIO" in NA.texto_padrao("RENUNCIA", None, SV)
    assert "REVOGADA" not in NA.texto_padrao("RENUNCIA", None, SV)


# ------------------------------------------------------------- anotar

def test_anotar_muda_a_situacao_do_ato_anotado():
    con = banco()
    velha = procuracao_do_acervo(con)
    feito = NA.anotar(con, velha, "REVOGACAO", AGORA, criado_por="T", sv=SV)
    assert feito["situacao_nova"] == "REVOGADO"
    linha = con.execute("SELECT * FROM nt_atos WHERE id=?", (velha,)).fetchone()
    assert linha["situacao"] == "REVOGADO"
    assert linha["revogado_por"] == "T"


def test_o_substabelecimento_anota_e_NAO_extingue():
    # Substabelecer não extingue a procuração: com reserva, o outorgado
    # continua com os poderes; sem reserva, ela segue sendo o título de onde
    # eles vieram.
    con = banco()
    velha = procuracao_do_acervo(con)
    feito = NA.anotar(con, velha, "SUBSTABELECIMENTO", AGORA, sv=SV)
    assert feito["situacao_nova"] is None
    assert con.execute("SELECT situacao FROM nt_atos WHERE id=?",
                       (velha,)).fetchone()["situacao"] == "LAVRADO"
    assert len(NA.do_ato(con, velha)) == 1


def test_ato_em_lavratura_nao_tem_margem():
    con = banco()
    with pytest.raises(NA.AnotacaoError, match="margem"):
        NA.anotar(con, rascunho(con, "PROCURACAO"), "REVOGACAO", AGORA, sv=SV)


def test_um_ato_nao_se_anota_a_si_mesmo():
    con = banco()
    velha = procuracao_do_acervo(con)
    with pytest.raises(NA.AnotacaoError):
        NA.anotar(con, velha, "REVOGACAO", AGORA, ato_relacionado_id=velha, sv=SV)


def test_a_mesma_anotacao_nao_entra_duas_vezes():
    con = banco()
    velha = procuracao_do_acervo(con)
    NL.abrir_livro(con, "PROCURACAO", SV, AGORA, EXTENSO, folhas=200)
    novo = rascunho(con)
    lancar(con, novo)
    NA.anotar(con, velha, "REVOGACAO", AGORA, ato_relacionado_id=novo, sv=SV)
    with pytest.raises(NA.AnotacaoError, match="já está na margem"):
        NA.anotar(con, velha, "REVOGACAO", AGORA, ato_relacionado_id=novo, sv=SV)
    assert len(NA.do_ato(con, velha)) == 1


def test_tipo_desconhecido_e_recusado():
    con = banco()
    with pytest.raises(NA.AnotacaoError):
        NA.anotar(con, procuracao_do_acervo(con), "INVENTADO", AGORA, sv=SV)


# ------------------------------------------------------------- o automático

def test_a_revogacao_lancada_anota_sozinha_a_procuracao_do_acervo():
    con = banco()
    velha = procuracao_do_acervo(con, livro="27", folha="139")
    NL.abrir_livro(con, "PROCURACAO", SV, AGORA, EXTENSO, folhas=200)
    novo = rascunho(con, anterior_livro="27", anterior_folha="139")
    lancar(con, novo)
    feito = NA.anotar_ato_anterior(con, novo, SV, AGORA, "T")

    assert feito is not None and feito["ato_id"] == velha
    assert feito["situacao_nova"] == "REVOGADO"
    margem = NA.do_ato(con, velha)
    assert len(margem) == 1 and margem[0]["ato_relacionado_id"] == novo
    # E o vínculo interno fica gravado nos dois sentidos.
    assert con.execute("SELECT anterior_ato_id FROM nt_atos WHERE id=?",
                       (novo,)).fetchone()["anterior_ato_id"] == velha


def test_nao_anota_ato_de_outra_serventia():
    con = banco()
    procuracao_do_acervo(con, livro="27", folha="139")
    NL.abrir_livro(con, "PROCURACAO", SV, AGORA, EXTENSO, folhas=200)
    novo = rascunho(con, anterior_livro="27", anterior_folha="139",
                    anterior_cns="012345")
    lancar(con, novo)
    assert NA.anotar_ato_anterior(con, novo, SV, AGORA, "T") is None


def test_nao_anota_quando_ha_dois_candidatos_na_mesma_folha():
    # O acervo tem pares de atos na mesma folha do livro 27. Anotar a margem
    # do ato errado é pior do que não anotar.
    con = banco()
    procuracao_do_acervo(con, livro="27", folha="139")
    procuracao_do_acervo(con, livro="27", folha="139")
    NL.abrir_livro(con, "PROCURACAO", SV, AGORA, EXTENSO, folhas=200)
    novo = rascunho(con, anterior_livro="27", anterior_folha="139")
    lancar(con, novo)
    assert NA.anotar_ato_anterior(con, novo, SV, AGORA, "T") is None


def test_escritura_nao_pede_anotacao():
    con = banco()
    NL.abrir_livro(con, "ESCRITURA", SV, AGORA, EXTENSO, folhas=200)
    novo = rascunho(con, "ESCRITURA")
    lancar(con, novo)
    assert NA.anotar_ato_anterior(con, novo, SV, AGORA, "T") is None


def test_o_vinculo_manual_copia_os_dados_da_censec():
    con = banco()
    velha = procuracao_do_acervo(con, livro="27", folha="139")
    NL.abrir_livro(con, "PROCURACAO", SV, AGORA, EXTENSO, folhas=200)
    novo = rascunho(con)
    NA.vincular_anterior(con, novo, velha, SV)
    a = con.execute("SELECT * FROM nt_atos WHERE id=?", (novo,)).fetchone()
    assert a["anterior_ato_id"] == velha
    assert (a["anterior_livro"], a["anterior_folha"]) == ("27", "139")
    assert a["anterior_cns"] == "000000"
    assert a["anterior_data"] == "2024-03-11"


# ------------------------------------------------------------- pendentes

def test_a_lista_de_pendentes_diz_o_motivo():
    con = banco()
    NL.abrir_livro(con, "PROCURACAO", SV, AGORA, EXTENSO, folhas=200)
    sem_anterior = rascunho(con)
    de_fora = rascunho(con, anterior_livro="9", anterior_folha="3",
                       anterior_cns="012345")
    nao_achado = rascunho(con, anterior_livro="99", anterior_folha="1")
    for ato in (sem_anterior, de_fora, nao_achado):
        lancar(con, ato)
    motivos = {p["id"]: p["motivo"] for p in NA.pendentes(con)}
    assert "não foi informado" in motivos[sem_anterior]
    assert "outra serventia" in motivos[de_fora]
    assert "não foi localizado" in motivos[nao_achado]


def test_o_ato_anotado_sai_da_lista_de_pendentes():
    con = banco()
    procuracao_do_acervo(con, livro="27", folha="139")
    NL.abrir_livro(con, "PROCURACAO", SV, AGORA, EXTENSO, folhas=200)
    novo = rascunho(con, anterior_livro="27", anterior_folha="139")
    lancar(con, novo)
    assert len(NA.pendentes(con)) == 1
    NA.anotar_ato_anterior(con, novo, SV, AGORA, "T")
    assert NA.pendentes(con) == []


def test_a_busca_acha_o_ato_anterior_pelo_nome_da_parte():
    con = banco()
    velha = procuracao_do_acervo(con)
    con.execute("""INSERT INTO nt_ato_partes(ato_id, nome, nome_norm, ordem, criado_em)
                   VALUES (?, 'JOSE ALVES DE SOUZA','jose alves de souza',1,?)""",
                (velha, AGORA))
    assert [c["id"] for c in NA.candidatos(con, "alves")] == [velha]
    assert [c["id"] for c in NA.candidatos(con, "MARIA DAS")] == [velha]
    assert NA.candidatos(con, "x") == []       # busca curta não varre o acervo


# ------------------------------------------------------------- pelas telas

def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela nao trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def serventia(cg_casa):
    app = cg_casa['app']
    caminho = cg_casa['banco']
    dados = cg_casa['dados']
    cg_casa['db'].create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c = app.test_client()
    c.post("/login",
           data={"username": "tabeliao", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    bancada = {"app": app, "cliente": c, "banco": caminho,
               "db": cg_casa["db"], "dados": dados}
    from selador_de_bancada import ligar_o_selador
    with ligar_o_selador(bancada):
        yield bancada


def sql(s, comando, args=()):
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    cur = con.execute(comando, args)
    linhas = [dict(r) for r in cur.fetchall()]
    con.commit()
    ultimo = cur.lastrowid
    con.close()
    return linhas, ultimo


def acao(s, ato_id, **dados):
    html = s["cliente"].get(f"/notas/atos/{ato_id}").get_data(as_text=True)
    dados.setdefault("csrf_token", _token(html))
    if dados.get("acao") == "lancar":
        dados.setdefault("codigo_tj", "13.9.3")
        # A trava da CENSEC (09/10/2026) — ver `notas_pronto_para_a_censec`.
        from notas_pronto_para_a_censec import preparar
        preparar(s["banco"], ato_id)
        # O ARQUIVAMENTO 13.30 É OBRIGATÓRIO na revogação, no substabelecimento
        # e na renúncia desde 15/10/2026 (pedido do oficial): sem o documento
        # anexado e as folhas confirmadas o lançamento é recusado — ver
        # test_arquivamento_obrigatorio_procuracao.py.
        import io
        s["cliente"].post(
            f"/notas/atos/{ato_id}/anexos",
            data={"csrf_token": dados["csrf_token"],
                  "descricao": "Documento arquivado",
                  "arquivo": (io.BytesIO(b"\xff\xd8\xff\xe0 imagem"), "doc.jpg")},
            content_type="multipart/form-data", follow_redirects=True)
        s["cliente"].post(f"/notas/atos/{ato_id}",
                          data={"csrf_token": dados["csrf_token"],
                                "acao": "confirmar_arquivamento",
                                "folhas_arquivamento": "1"},
                          follow_redirects=True)
    return s["cliente"].post(f"/notas/atos/{ato_id}", data=dados,
                             follow_redirects=True)


def test_a_revogacao_lancada_pela_tela_anota_a_procuracao(serventia):
    _, velha = sql(serventia, """INSERT INTO nt_atos(tipo, data, livro, folha,
                                     numero_ordem, situacao, interessado, criado_em)
                                 VALUES ('PROCURACAO','2024-03-11','27','139',100,
                                         'LAVRADO','MARIA DAS DORES','2026-08-17T09:00:00')""")
    html = serventia["cliente"].get("/notas/atos/novo").get_data(as_text=True)
    serventia["cliente"].post("/notas/atos/novo",
                              data={"csrf_token": _token(html), "tipo": "REVOGACAO"},
                              follow_redirects=True)
    (novo,), _ = sql(serventia, "SELECT MAX(id) id FROM nt_atos")
    novo = novo["id"]
    acao(serventia, novo, acao="vincular_anterior", anterior_id=velha)
    acao(serventia, novo, acao="teor", teor="<p>revogo a procuração</p>")
    resposta = acao(serventia, novo, acao="lancar", paginas=2)
    corpo = resposta.get_data(as_text=True)
    assert "Anotado à margem do ato anterior" in corpo
    assert "revogado" in corpo.lower()

    (marcada,), _ = sql(serventia, "SELECT * FROM nt_atos WHERE id=?", (velha,))
    assert marcada["situacao"] == "REVOGADO"
    (nota,), _ = sql(serventia, "SELECT * FROM nt_ato_anotacoes WHERE ato_id=?", (velha,))
    assert nota["tipo"] == "REVOGACAO" and nota["ato_relacionado_id"] == novo

    # A tela da procuração revogada avisa, em vermelho, no topo.
    tela = serventia["cliente"].get(f"/notas/atos/{velha}").get_data(as_text=True)
    assert "ESTE ATO TEM ANOTAÇÃO À MARGEM" in tela
    assert "REVOGADA" in tela


def test_o_traslado_da_procuracao_revogada_transcreve_a_margem(serventia):
    """O ponto inteiro da mudança.

    Lei 8.935/1994, art. 6º, II: expedir cópias FIDEDIGNAS. Traslado de
    procuração revogada que não diz que foi revogada não é cópia fiel do livro.
    """
    _, velha = sql(serventia, """INSERT INTO nt_atos(tipo, data, livro, folha,
                                     numero_ordem, situacao, teor, criado_em)
                                 VALUES ('PROCURACAO','2024-03-11','27','139',100,
                                         'LAVRADO','<p>poderes amplos</p>',
                                         '2026-08-17T09:00:00')""")
    antes = serventia["cliente"].get(f"/notas/atos/{velha}/traslado")
    assert antes.status_code == 200
    texto_antes = zipfile.ZipFile(BytesIO(antes.data)).read("content.xml").decode()
    assert "ANOTAÇÕES À MARGEM" not in texto_antes

    acao(serventia, velha, acao="anotar", tipo="REVOGACAO", externa="1",
         serventia_externa="2º Ofício de Imperatriz", cns_externa="012345",
         data="2026-05-02")

    depois = serventia["cliente"].get(f"/notas/atos/{velha}/traslado")
    texto = zipfile.ZipFile(BytesIO(depois.data)).read("content.xml").decode()
    assert "ANOTAÇÕES À MARGEM" in texto
    assert "REVOGADA" in texto
    assert "Imperatriz" in texto
    assert "anotações constantes da margem" in texto


def test_a_tela_de_pendentes_lista_e_esvazia(serventia):
    html = serventia["cliente"].get("/notas/atos/novo").get_data(as_text=True)
    serventia["cliente"].post("/notas/atos/novo",
                              data={"csrf_token": _token(html), "tipo": "REVOGACAO"},
                              follow_redirects=True)
    (novo,), _ = sql(serventia, "SELECT MAX(id) id FROM nt_atos")
    novo = novo["id"]
    acao(serventia, novo, acao="teor", teor="<p>x</p>")
    acao(serventia, novo, acao="lancar", paginas=2)

    lista = serventia["cliente"].get("/notas/anotacoes/pendentes").get_data(as_text=True)
    assert "1 ato(s) sem a anotação" in lista
    assert "não foi informado" in lista
    painel = serventia["cliente"].get("/notas").get_data(as_text=True)
    assert "sem anotação à margem" in painel

    acao(serventia, novo, acao="anotar", tipo="OUTRA",
         texto="Anotação de teste na margem deste próprio ato")
    # A pendência é do ato que GEROU a anotação; anotar a si não resolve.
    lista = serventia["cliente"].get("/notas/anotacoes/pendentes").get_data(as_text=True)
    assert "1 ato(s) sem a anotação" in lista


def test_anotacao_nao_tem_botao_de_apagar(serventia):
    _, velha = sql(serventia, """INSERT INTO nt_atos(tipo, data, livro, folha,
                                     situacao, criado_em)
                                 VALUES ('PROCURACAO','2024-03-11','27','139',
                                         'LAVRADO','2026-08-17T09:00:00')""")
    acao(serventia, velha, acao="anotar", tipo="RETIFICACAO", texto="teste")
    html = serventia["cliente"].get(f"/notas/atos/{velha}").get_data(as_text=True)
    assert 'value="remover_anotacao"' not in html
    assert "Anotação não se apaga" in html


# =====================================================================
# Regressao da revisao adversarial de 17/08/2026.
#
# A primeira versao de `localizar_ato_anterior` casava so por (livro, folha).
# O livro 27 existe em toda serie, e o importador do E-Oficio joga o numero do
# livro de escrituras e o de procuracoes na MESMA coluna. "Unico candidato"
# queria dizer "o unico ato do acervo inteiro que por acaso esta naquele
# numero de livro e naquela folha".
# =====================================================================

def test_a_revogacao_NAO_alcanca_escritura_do_livro_de_mesmo_numero():
    """O achado crítico: uma escritura de R$150.000 foi marcada REVOGADA."""
    con = banco()
    escritura = con.execute(
        """INSERT INTO nt_atos(tipo, serie, data, livro, folha, situacao,
                               interessado, criado_em)
           VALUES ('ESCRITURA','ESCRITURA','2019-04-02','27','139','LAVRADO',
                   'COMPRA E VENDA', ?)""", (AGORA,)).lastrowid
    NL.abrir_livro(con, "PROCURACAO", SV, AGORA, EXTENSO, folhas=200)
    novo = rascunho(con, anterior_livro="27", anterior_folha="139")
    lancar(con, novo)

    assert NA.anotar_ato_anterior(con, novo, SV, AGORA, "T") is None
    linha = con.execute("SELECT * FROM nt_atos WHERE id=?", (escritura,)).fetchone()
    assert linha["situacao"] == "LAVRADO"
    assert NA.do_ato(con, escritura) == []
    # E o ato fica na lista de pendentes, para alguém resolver a mão.
    assert [p["id"] for p in NA.pendentes(con)] == [novo]


def test_a_revogacao_nao_alcanca_testamento_nem_ata():
    con = banco()
    for tipo in ("TESTAMENTO", "ATA", "ESCRITURA"):
        con.execute(
            """INSERT INTO nt_atos(tipo, data, livro, folha, situacao, criado_em)
               VALUES (?, '2019-04-02','9','5','LAVRADO', ?)""", (tipo, AGORA))
    NL.abrir_livro(con, "PROCURACAO", SV, AGORA, EXTENSO, folhas=200)
    novo = rascunho(con, anterior_livro="9", anterior_folha="5")
    lancar(con, novo)
    assert NA.anotar_ato_anterior(con, novo, SV, AGORA, "T") is None


def test_a_serie_do_livro_desempata_quando_o_tipo_nao_basta():
    """Duas procurações no livro 27 de séries diferentes de livro."""
    con = banco()
    l_proc = NL.abrir_livro(con, "PROCURACAO", SV, AGORA, EXTENSO, numero="27",
                            folhas=200)
    l_sub = NL.abrir_livro(con, "SUBSTABELECIMENTO", SV, AGORA, EXTENSO,
                           numero="27", folhas=200)
    alvo = con.execute(
        """INSERT INTO nt_atos(tipo, data, livro, livro_id, folha, situacao, criado_em)
           VALUES ('PROCURACAO','2019-04-02','27',?,'50','LAVRADO',?)""",
        (l_proc, AGORA)).lastrowid
    con.execute(
        """INSERT INTO nt_atos(tipo, data, livro, livro_id, folha, situacao, criado_em)
           VALUES ('SUBSTABELECIMENTO','2019-04-02','27',?,'50','LAVRADO',?)""",
        (l_sub, AGORA))
    novo = rascunho(con, "SUBSTABELECIMENTO", anterior_livro="27",
                    anterior_folha="50")
    lancar(con, novo)
    feito = NA.anotar_ato_anterior(con, novo, SV, AGORA, "T")
    # Substabelecimento só alcança procuração, e do livro de procurações.
    assert feito is not None and feito["ato_id"] == alvo


def test_o_nome_da_serventia_vem_das_configuracoes_e_nao_de_uma_constante():
    """Renomear a serventia na tela não pode desligar o reconhecimento."""
    con = banco()
    outro_nome = dict(SV, unit_name="Serventia Extrajudicial")
    procuracao_do_acervo(con, livro="27", folha="139")
    NL.abrir_livro(con, "PROCURACAO", SV, AGORA, EXTENSO, folhas=200)
    novo = rascunho(con, anterior_livro="27", anterior_folha="139",
                    anterior_cartorio="Serventia Extrajudicial")
    lancar(con, novo)
    assert NA.anotar_ato_anterior(con, novo, outro_nome, AGORA, "T") is not None


def test_cartorio_de_fora_pelo_nome_continua_barrado():
    con = banco()
    procuracao_do_acervo(con, livro="27", folha="139")
    NL.abrir_livro(con, "PROCURACAO", SV, AGORA, EXTENSO, folhas=200)
    novo = rascunho(con, anterior_livro="27", anterior_folha="139",
                    anterior_cartorio="2º Ofício de Imperatriz")
    lancar(con, novo)
    assert NA.anotar_ato_anterior(con, novo, SV, AGORA, "T") is None


def test_sem_saber_o_proprio_cns_nao_se_adivinha():
    con = banco()
    procuracao_do_acervo(con, livro="27", folha="139")
    NL.abrir_livro(con, "PROCURACAO", SV, AGORA, EXTENSO, folhas=200)
    novo = rascunho(con, anterior_livro="27", anterior_folha="139",
                    anterior_cns="777777")
    lancar(con, novo)
    sem_cns = dict(SV, ri_cns="")
    assert NA.anotar_ato_anterior(con, novo, sem_cns, AGORA, "T") is None


def test_revincular_depois_de_anotado_e_recusado():
    """Clicar na linha errada e depois na certa deixava DUAS revogadas."""
    con = banco()
    errada = procuracao_do_acervo(con, livro="3", folha="10")
    certa = procuracao_do_acervo(con, livro="3", folha="20")
    NL.abrir_livro(con, "PROCURACAO", SV, AGORA, EXTENSO, folhas=200)
    novo = rascunho(con)
    lancar(con, novo)

    NA.vincular_anterior(con, novo, errada, SV)
    NA.anotar_ato_anterior(con, novo, SV, AGORA, "T")
    assert con.execute("SELECT situacao FROM nt_atos WHERE id=?",
                       (errada,)).fetchone()["situacao"] == "REVOGADO"

    with pytest.raises(NA.AnotacaoError, match="não se apaga"):
        NA.vincular_anterior(con, novo, certa, SV)
    assert con.execute("SELECT situacao FROM nt_atos WHERE id=?",
                       (certa,)).fetchone()["situacao"] == "LAVRADO"
    assert con.execute("SELECT anterior_ato_id FROM nt_atos WHERE id=?",
                       (novo,)).fetchone()["anterior_ato_id"] == errada


def test_revincular_ao_MESMO_ato_continua_permitido():
    con = banco()
    velha = procuracao_do_acervo(con, livro="3", folha="10")
    NL.abrir_livro(con, "PROCURACAO", SV, AGORA, EXTENSO, folhas=200)
    novo = rascunho(con)
    lancar(con, novo)
    NA.vincular_anterior(con, novo, velha, SV)
    NA.anotar_ato_anterior(con, novo, SV, AGORA, "T")
    NA.vincular_anterior(con, novo, velha, SV)      # não levanta
    assert len(NA.do_ato(con, velha)) == 1


def test_a_mesma_anotacao_manual_nao_entra_tres_vezes():
    con = banco()
    velha = procuracao_do_acervo(con)
    NA.anotar(con, velha, "RETIFICACAO", AGORA, texto="corrige o nome", sv=SV)
    for _ in range(2):
        with pytest.raises(NA.AnotacaoError, match="já está na margem"):
            NA.anotar(con, velha, "RETIFICACAO", AGORA, texto="corrige o nome",
                      sv=SV)
    assert len(NA.do_ato(con, velha)) == 1


def test_anotar_ato_ja_fora_de_vigor_nao_troca_a_situacao_em_silencio():
    con = banco()
    velha = procuracao_do_acervo(con, situacao="SEM_EFEITO")
    feito = NA.anotar(con, velha, "REVOGACAO", AGORA, sv=SV)
    assert feito["situacao_nova"] is None
    assert feito["aviso"] and "sem efeito" in feito["aviso"]
    assert con.execute("SELECT situacao FROM nt_atos WHERE id=?",
                       (velha,)).fetchone()["situacao"] == "SEM_EFEITO"
    assert len(NA.do_ato(con, velha)) == 1     # mas a margem registra


def test_o_motivo_na_tela_e_o_da_revogacao_e_nao_um_texto_velho():
    con = banco()
    velha = procuracao_do_acervo(con)
    con.execute("UPDATE nt_atos SET sem_efeito_motivo=? WHERE id=?",
                ("AVERBADO POR ORDEM JUDICIAL 0800123-45", velha))
    NA.anotar(con, velha, "REVOGACAO", AGORA, sv=SV)
    linha = con.execute("SELECT * FROM nt_atos WHERE id=?", (velha,)).fetchone()
    assert linha["situacao"] == "REVOGADO"
    assert "REVOGADA" in linha["sem_efeito_motivo"]
    assert "0800123-45" not in linha["sem_efeito_motivo"]
