"""O PLD/COAF — a seleção, a análise, o envio registrado e o sigilo.

Pedido do oficial em 08/10/2026: «precisamos construir o envio automático para o
COAF nos casos que se enquadrar a determinação de comunicação pelo código
nacional de normas». A norma é o CNN (Provimento CNJ 149/2023, redação do
Provimento 161/2024) e o Código do TJMA, art. 476; os trechos de teor abaixo
imitam os que a medição de 08/10/2026 achou na produção.
"""
from __future__ import annotations

import io
import re
import sys
import threading
import time
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

import banco_pg               # noqa: E402
import pld_coaf as P          # noqa: E402
from banco_de_teste import conexao_de_teste  # noqa: E402
from bd_nativo import banco   # noqa: E402

SENHA = "Senha#12345"


# ------------------------------------------------------------- a leitura do teor

def casos(texto, atribuicao="NOTAS", tipo="ESCRITURA"):
    return P.casos_do_texto(atribuicao, "nt_atos", 1, "2026-09-01", texto, tipo=tipo)


def test_especie_de_cem_mil_comunica_sem_analise():
    c = casos("o preço de R$ 150.000,00 (cento e cinquenta mil reais), pago em espécie, "
              "mediante entrega de papel-moeda.")
    assert [x["hipotese"] for x in c] == ["ESPECIE_100MIL"]
    assert c[0]["especie"] == P.AUTOMATICA and c[0]["situacao"] == "A_COMUNICAR"
    assert "art. 171" in c[0]["fundamento"]


def test_moeda_corrente_nao_e_especie():
    # CNN, art. 140, VII; TJMA, art. 476, III.
    assert casos("pago em moeda corrente nacional, R$ 900.000,00, do que dá quitação.") == []


def test_o_valor_que_conta_e_o_pago_em_especie_e_nao_o_total():
    # Medido em 08/10/2026 numa escritura real desta casa.
    texto = ("pagou-lhe torna de R$ 10.000,00 (dez mil reais) em espécie, mediante entrega "
             "de papel-moeda, perfazendo R$ 120.000,00 de quinhão")
    assert casos(texto) == []


def test_especie_negada_nao_seleciona():
    assert casos("declaram que não houve pagamento em espécie; R$ 300.000,00 por PIX.") == []


def test_especie_sem_valor_vai_a_analise():
    c = casos("parte do preço foi paga em espécie, conforme recibo apartado.")
    assert c[0]["hipotese"] == "ESPECIE_SEM_VALOR" and c[0]["situacao"] == "A_ANALISAR"


def test_titulo_ao_portador_conta_como_especie():
    c = casos("pago por título de crédito ao portador no valor de R$ 200.000,00.")
    assert c[0]["hipotese"] == "ESPECIE_100MIL"


def test_numerario_de_estatuto_nao_e_pagamento():
    # Os dois estatutos de associação da produção: regra de tesouraria.
    assert casos("fixar o limite máximo de numerário que poderá ser mantido em caixa",
                 atribuicao="RCPJ", tipo="") == []


def test_doacao_acima_de_cem_mil_pede_analise():
    c = casos("ESCRITURA DE DOAÇÃO de imóvel avaliado em R$ 619.011,30", atribuicao="RI",
              tipo="R")
    assert [x["hipotese"] for x in c] == ["DOACAO_100MIL"]
    assert "art. 162, I" in c[0]["fundamento"]


def test_hipoteca_a_banco_nao_e_entre_particulares():
    assert casos("dá em primeira hipoteca ao BANCO DO BRASIL S/A, cédula de crédito "
                 "bancário", atribuicao="RI", tipo="R") == []


def test_clausula_que_autoriza_hipoteca_nao_e_hipoteca():
    # A matrícula 4017: autorização para hipoteca futura a entidades de crédito.
    assert casos("expressamente autorizada a constituição de hipoteca em garantia de "
                 "financiamentos concedidos por entidades de crédito",
                 atribuicao="RI", tipo="R") == []


def test_hipoteca_entre_particulares_pede_analise():
    c = casos("o devedor dá em hipoteca ao credor JOSÉ DA SILVA, em garantia de mútuo de "
              "R$ 80.000,00", atribuicao="RI", tipo="R")
    assert [x["hipotese"] for x in c] == ["GARANTIA_ENTRE_PARTICULARES"]


def test_procuracao_ampla_irrevogavel_pede_analise():
    c = casos("outorga poderes para a gestão da sociedade e movimentar contas bancárias, "
              "em caráter irrevogável e irretratável", tipo="PROCURACAO")
    assert [x["hipotese"] for x in c] == ["PROCURACAO_AMPLA"]


# ------------------------------------------------------------- a fila

@pytest.fixture()
def con(tmp_path):
    c = conexao_de_teste()
    c.executescript("""
        CREATE TABLE nt_atos (id INTEGER PRIMARY KEY, tipo TEXT, livro TEXT, folha TEXT,
            data TEXT, situacao TEXT, teor TEXT, valor_transacao INTEGER);
        CREATE TABLE nt_ato_partes (id INTEGER PRIMARY KEY, ato_id INTEGER, nome TEXT,
            documento TEXT, qualificacao TEXT, estado_civil TEXT, profissao TEXT,
            endereco TEXT, testemunha INTEGER, ordem INTEGER);
    """)
    c.execute("""INSERT INTO nt_atos VALUES (1,'ESCRITURA','12','40','2026-09-01','LAVRADO',
                 '<p>preço de R$ 150.000,00 pago em espécie</p>', NULL)""")
    c.execute("""INSERT INTO nt_ato_partes VALUES (1,1,'JOSÉ DA SILVA','123.456.789-00',
                 'vendedor','casado','lavrador','Cidade Exemplo',0,1)""")
    c.commit()
    return c


def test_selecionar_e_idempotente(con):
    assert P.selecionar(con, desde="2026-01-01")["novos"] == 1
    assert P.selecionar(con, desde="2026-01-01")["novos"] == 0


def test_comunicacao_traz_motivos_dados_e_fontes(con):
    P.selecionar(con, desde="2026-01-01")
    texto = P.montar_comunicacao(con, 1)
    assert "1. MOTIVOS" in texto and "2. DADOS" in texto and "3. FONTES" in texto
    assert "JOSÉ DA SILVA" in texto and "R$ 150.000,00" in texto


def test_automatica_nao_se_arquiva_sem_comunicar(con):
    P.selecionar(con, desde="2026-01-01")
    with pytest.raises(P.PldError):
        P.concluir_analise(con, 1, comunicar=False, fundamentacao="x" * 40, usuario="a")


def test_analise_exige_fundamentacao(con):
    cid = P.abrir_para_analise(con, referencia="selo ESCPUB0000000000", data_operacao=
                               "2025-03-10", motivo="valor expressivo para o perfil")
    with pytest.raises(P.PldError):
        P.concluir_analise(con, cid, comunicar=False, fundamentacao="curto", usuario="a")
    P.concluir_analise(con, cid, comunicar=False, usuario="a",
                       fundamentacao="Comprador agricultor com renda compatível, "
                                     "pagamento por transferência identificada.")
    assert P.caso(con, cid)["situacao"] == "NAO_COMUNICAR"


def test_envio_so_com_numero_do_coaf(con):
    P.selecionar(con, desde="2026-01-01")
    with pytest.raises(P.PldError):
        P.registrar_envio(con, 1, numero_coaf="", data_envio="2026-09-02", usuario="a")
    P.registrar_envio(con, 1, numero_coaf="123456", data_envio="2026-09-02", usuario="a")
    c = P.caso(con, 1)
    assert c["situacao"] == "COMUNICADA" and c["numero_coaf"] == "123456"


def test_nao_ocorrencia_so_cabe_sem_comunicacao_e_sem_pendencia(con):
    P.selecionar(con, desde="2026-01-01")
    assert P.nao_ocorrencia(con, 2026)["cabe"] is False          # pendente
    assert P.nao_ocorrencia(con, 2025)["cabe"] is True
    assert P.nao_ocorrencia(con, 2025)["prazo"] == "2026-01-31"


def test_prazo_conta_trinta_dias_na_automatica(con):
    P.selecionar(con, desde="2026-01-01")
    assert P.caso(con, 1)["prazo"]["limite"] == "2026-10-01"


def test_caso_sem_data_fica_onde_o_sqlite_o_punha(con):
    """Ressalva da revisão do L035: o SQLite põe o NULL primeiro na ordem
    crescente e por último na decrescente; o PostgreSQL, sem dizer, faz o
    contrário — e o caso sem data mudava de lugar na fila."""
    P.selecionar(con, desde="2026-01-01")             # caso de 2026-09-01
    con.execute("""INSERT INTO pld_casos (atribuicao, tabela, ato_id, hipotese,
                       especie, fundamento, descricao, data_operacao, situacao,
                       selecionado_em)
                   VALUES ('NOTAS', 'manual', 1, 'MANUAL', 'ANALISE', 'CNN',
                           'sem data', NULL, 'A_COMUNICAR', '2026-10-01')""")
    assert [c["data_operacao"] for c in P.casos(con, "A_COMUNICAR")] \
        == [None, "2026-09-01"]
    assert [c["data_operacao"] for c in P.casos(con)] == ["2026-09-01", None]


def _psycopg_puro(con, *, autocommit=False):
    """Uma conexão do psycopg no schema do teste, SEM a ponte — como a
    transação vai ficar quando a ponte sair."""
    import psycopg
    pg = psycopg.connect(banco_pg.dsn(), autocommit=autocommit)
    pg.execute(f'SET search_path TO "{con.schema}", public')
    if not autocommit:
        pg.commit()
    return pg


def test_envio_e_descarte_ao_mesmo_tempo_nao_descomunicam_o_caso(con):
    """Ressalva da revisão do L035, o mesmo padrão do papel: a decisão
    conferia a situação e gravava por cima sem prender a linha. Com a ponte,
    `init_schema` já grava antes e pega a trava única do banco; sem ela, só o
    FOR UPDATE segura. O envio grava e ainda não confirmou; o descarte chega
    no meio."""
    P.selecionar(con, desde="2026-01-01")
    con.commit()
    um, dois = _psycopg_puro(con), _psycopg_puro(con)
    vigia = _psycopg_puro(con, autocommit=True)
    pid = banco(dois).valor("SELECT pg_backend_pid() AS pid")
    P.registrar_envio(um, 1, numero_coaf="123456", data_envio="2026-09-02", usuario="a")
    saida: dict = {}

    def descarte():
        try:
            P.descartar(dois, 1, motivo="o valor achado não era o pago em espécie, "
                                        "era o total do quinhão", usuario="b")
            dois.commit()
        except Exception as erro:  # o teste confere qual
            saida["erro"] = erro
            dois.rollback()

    fio = threading.Thread(target=descarte)
    fio.start()
    for _ in range(200):          # o descarte tem de estar ESPERANDO a linha
        if banco(vigia).valor(
                "SELECT count(*) AS n FROM pg_locks WHERE pid=%s AND NOT granted",
                (pid,)):
            break
        time.sleep(0.05)
    um.commit()
    fio.join(30)
    for c in (um, dois, vigia):
        c.close()
    assert isinstance(saida.get("erro"), P.PldError), saida
    assert P.caso(con, 1)["situacao"] == "COMUNICADA"


# ------------------------------------------------------------- as telas e o sigilo

def _token(html: str) -> str:
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


@pytest.fixture()
def casa(cg_casa):
    app = cg_casa["app"]
    cg_casa["db"].create_user("oficial", "OFICIAL", SENHA, "ADMIN")
    cg_casa["db"].create_user("balcao", "ESCREVENTE", SENHA, "USER")

    def entrar(login):
        c = app.test_client()
        c.post("/login", data={"username": login, "password": SENHA,
                               "csrf_token": _token(c.get("/login").get_data(as_text=True))},
               follow_redirects=True)
        return c
    return {"admin": entrar("oficial"), "balcao": entrar("balcao"), "cg": cg_casa}


def test_o_painel_abre_para_o_admin(casa):
    r = casa["admin"].get("/administrativo/pld")
    assert r.status_code == 200 and "sigiloso" in r.get_data(as_text=True)


def test_o_balcao_nao_ve_o_painel_nem_o_menu(casa):
    r = casa["balcao"].get("/administrativo/pld")
    assert r.status_code in (302, 403, 404)
    assert "PLD / COAF" not in casa["balcao"].get("/").get_data(as_text=True)


def test_caso_aberto_a_mao_e_envio_registrado_pela_tela(casa):
    c = casa["admin"]
    html = c.get("/administrativo/pld").get_data(as_text=True)
    r = c.post("/administrativo/pld/abrir", data={
        "csrf_token": _token(html), "referencia": "selo ESCPUB000000JO1ZKDDPL2TXK845",
        "data": "2025-01-10", "atribuicao": "NOTAS", "valor": "250.000,00",
        "motivo": "reanálise pedida pela inspeção 0000524"}, follow_redirects=True)
    pagina = r.get_data(as_text=True)
    assert "ESCPUB000000JO1ZKDDPL2TXK845" in pagina
    caso_id = int(re.search(r"caso (\d+)", pagina).group(1))
    c.post(f"/administrativo/pld/caso/{caso_id}/analise", data={
        "csrf_token": _token(pagina), "conclusao": "COMUNICAR",
        "fundamentacao": "Valor incompatível com a renda declarada do comprador, "
                         "pagamento sem origem identificada."}, follow_redirects=True)
    pagina = c.get(f"/administrativo/pld/caso/{caso_id}").get_data(as_text=True)
    c.post(f"/administrativo/pld/caso/{caso_id}/enviado", data={
        "csrf_token": _token(pagina), "numero_coaf": "987654", "data_envio": "2026-10-08",
        "recibo": (io.BytesIO(b"%PDF-1.4 recibo"), "recibo.pdf")},
        content_type="multipart/form-data", follow_redirects=True)
    pagina = c.get(f"/administrativo/pld/caso/{caso_id}").get_data(as_text=True)
    assert "987654" in pagina and "recibo.pdf" in pagina
    # O recibo é sigiloso: o balcão não o baixa nem pelo número do anexo.
    anexo = int(re.search(r"/arquivo/(\d+)", pagina).group(1))
    assert casa["balcao"].get(f"/arquivo/{anexo}").status_code == 404
    assert casa["balcao"].get(f"/arquivo/{anexo}/ver").status_code == 404
    assert c.get(f"/arquivo/{anexo}").status_code == 200
