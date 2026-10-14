"""
Desfazer o encerramento de um título, corrigir os dados e lançar depósito prévio.

O QUE ACONTECEU
    O título 11548 foi encerrado por engano. O protocolo do Registro de Imóveis
    só tinha lista: dava para prenotar e dava para encerrar, e mais nada.
    Encerrado por engano, não havia como voltar atrás; digitado errado, não
    havia como corrigir.

POR QUE ABRIR OUTRO NÃO RESOLVE
    O número de ordem do protocolo é o que garante a prioridade do direito
    (Lei 6.015/73, art. 186). Protocolo novo joga o título para o fim da fila —
    e na frente dele pode ter entrado outro título sobre o mesmo imóvel.

O QUE ESTES TESTES PROTEGEM
    Que a reabertura exija motivo e fique registrada; que ela NÃO devolva prazo
    (senão a correção vira uma forma de esticar a prioridade); que a correção de
    dados guarde o que estava escrito antes; e que o depósito prévio fique
    amarrado ao título e entre no caixa do dia.
"""
from __future__ import annotations

import glob
import json
import re
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

AGORA = "2026-08-17 09:00:00"
NUMERO = 11548


@pytest.fixture()
def serventia(cg_casa):
    app = cg_casa['app']
    banco = cg_casa['banco']
    dados = cg_casa['dados']
    d = cg_casa['db']
    d.create_user("registro", "LAURA MARIA DA COSTA", "Senha#12345", "ADMIN")

    prenotado = date.today() - timedelta(days=5)
    limite = date.today() + timedelta(days=10)
    con = sqlite3.connect(banco)
    con.execute("UPDATE users SET funcao='Escrevente Autorizado' WHERE username='registro'")
    con.execute(
        """INSERT INTO ri_protocolos
           (numero, livro, data_prenotacao, apresentante, apresentante_documento,
            natureza_titulo, objeto, matricula_numero, data_limite, situacao,
            origem, criado_em)
           VALUES (?, '1A', ?, 'CONSTRUTORA ALFA LTDA', '12345678000199',
                   'Escritura de compra e venda', 'Aquisição do lote 12',
                   '3527', ?, 'ENCERRADO', 'MANUAL', ?)""",
        (NUMERO, prenotado.isoformat(), limite.isoformat(), AGORA))
    con.commit()
    pid = con.execute("SELECT id FROM ri_protocolos WHERE numero=?", (NUMERO,)).fetchone()[0]
    con.close()

    c = app.test_client()
    pega = lambda h: re.search(r'name="csrf_token"[^>]*value="([^"]+)"', h).group(1)
    c.post("/login", data={"username": "registro", "password": "Senha#12345",
                           "csrf_token": pega(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    token = pega(c.get(f"/registro-imoveis/protocolo/{pid}").get_data(as_text=True))
    return {"app": app, "cliente": c, "banco": banco, "pid": pid, "token": token,
            "prenotado": prenotado.isoformat(), "limite": limite.isoformat()}


def protocolo(s):
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    r = con.execute("SELECT * FROM ri_protocolos WHERE id=?", (s["pid"],)).fetchone()
    con.close()
    return dict(r)


def post(s, **dados):
    dados.setdefault("csrf_token", s["token"])
    return s["cliente"].post(f"/registro-imoveis/protocolo/{s['pid']}",
                             data=dados, follow_redirects=True)


# ============================================================ a tela existe

def test_a_tela_do_titulo_abre(serventia):
    """Antes só havia lista: não havia onde clicar para ver um título."""
    r = serventia["cliente"].get(f"/registro-imoveis/protocolo/{serventia['pid']}")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert str(NUMERO) in html
    assert "CONSTRUTORA ALFA LTDA" in html


def test_a_lista_leva_ao_titulo(serventia):
    html = serventia["cliente"].get("/registro-imoveis/protocolo").get_data(as_text=True)
    assert f"/registro-imoveis/protocolo/{serventia['pid']}" in html


def test_titulo_inexistente_da_404(serventia):
    assert serventia["cliente"].get(
        "/registro-imoveis/protocolo/999999").status_code == 404


# ================================================================= reabrir

def test_reabrir_volta_para_aberto(serventia):
    r = post(serventia, acao="reabrir",
             motivo="encerrado por engano — o título não chegou a ser registrado")
    assert protocolo(serventia)["situacao"] == "ABERTO"
    assert "reaberto" in r.get_data(as_text=True).lower()


def test_reabrir_exige_motivo(serventia):
    """Reabertura de prenotação é correção de ato de livro: o motivo é o que se
    mostra na correição."""
    post(serventia, acao="reabrir", motivo="erro")
    assert protocolo(serventia)["situacao"] == "ENCERRADO", \
        "reabriu sem motivo suficiente"


def test_a_reabertura_guarda_de_onde_veio(serventia):
    """Reabrir não apaga o encerramento: registra que houve um."""
    post(serventia, acao="reabrir",
         motivo="encerrado por engano no lançamento de 17/08")
    p = protocolo(serventia)
    assert p["situacao_anterior"] == "ENCERRADO"
    assert p["reaberto_em"]
    assert p["reaberto_por"] == "LAURA MARIA DA COSTA"
    assert "engano" in p["motivo_reabertura"]


def test_a_reabertura_aparece_na_tela(serventia):
    post(serventia, acao="reabrir", motivo="encerrado por engano, título ativo")
    html = serventia["cliente"].get(
        f"/registro-imoveis/protocolo/{serventia['pid']}").get_data(as_text=True)
    assert "foi reaberto" in html
    assert "encerrado por engano, título ativo" in html


def test_reabrir_NAO_devolve_prazo(serventia):
    """O ponto mais delicado desta tela.

    A prenotação vale 20 dias úteis contados do lançamento no protocolo — não do
    dia em que alguém corrigiu um engano. Reabrir devolvendo prazo novo seria
    usar a correção para esticar a prioridade do título sobre terceiros.
    """
    antes = protocolo(serventia)
    post(serventia, acao="reabrir", motivo="encerrado por engano de digitação")
    depois = protocolo(serventia)
    assert depois["data_prenotacao"] == antes["data_prenotacao"]
    assert depois["data_limite"] == antes["data_limite"]


def test_a_reabertura_fica_na_auditoria(serventia):
    post(serventia, acao="reabrir", motivo="encerrado por engano — conferido hoje")
    con = sqlite3.connect(serventia["banco"])
    linha = con.execute(
        """SELECT details FROM audit_logs WHERE action='RI_PROTOCOLO_REABERTO'
           AND entity_id=?""", (serventia["pid"],)).fetchone()
    con.close()
    assert linha, "a reabertura não foi auditada"
    d = json.loads(linha[0])
    assert d["de"] == "ENCERRADO" and d["para"] == "ABERTO"


def test_reabrir_o_que_ja_esta_aberto_avisa(serventia):
    post(serventia, acao="reabrir", motivo="encerrado por engano, primeira vez")
    r = post(serventia, acao="reabrir", motivo="reabrindo de novo sem precisar")
    assert "já está aberto" in r.get_data(as_text=True)


# ================================================================== editar

def test_corrigir_os_dados_do_titulo(serventia):
    post(serventia, acao="editar", apresentante="CONSTRUTORA ALFA S/A",
         natureza_titulo="Escritura pública de compra e venda",
         objeto="Aquisição do lote 12 da quadra 4", matricula_numero="3527",
         apresentante_documento="12345678000199", telefone="", email="",
         documento_descricao="", anotacao="corrigido em 17/08/2026")
    p = protocolo(serventia)
    assert p["apresentante"] == "CONSTRUTORA ALFA S/A"
    assert p["anotacao"] == "corrigido em 17/08/2026"


def test_a_correcao_guarda_o_que_estava_escrito_antes(serventia):
    """"Protocolo 11548 editado" não responde à pergunta que a correição faz,
    que é o que estava escrito antes."""
    post(serventia, acao="editar", apresentante="CONSTRUTORA ALFA S/A")
    con = sqlite3.connect(serventia["banco"])
    linha = con.execute(
        """SELECT details FROM audit_logs WHERE action='RI_PROTOCOLO_EDITADO'
           AND entity_id=?""", (serventia["pid"],)).fetchone()
    con.close()
    d = json.loads(linha[0])["alteracoes"]["Apresentante"]
    assert d["antes"] == "CONSTRUTORA ALFA LTDA"
    assert d["depois"] == "CONSTRUTORA ALFA S/A"


def test_editar_sem_mudar_nada_avisa(serventia):
    r = post(serventia, acao="editar", apresentante="CONSTRUTORA ALFA LTDA")
    assert "Nada foi alterado" in r.get_data(as_text=True)


def test_o_numero_de_ordem_nao_se_corrige_por_aqui(serventia):
    """Número, livro e data da prenotação são o que dá prioridade ao título."""
    post(serventia, acao="editar", numero="99999", livro="2B",
         data_prenotacao="2020-01-01", apresentante="OUTRO NOME")
    p = protocolo(serventia)
    assert p["numero"] == NUMERO
    assert p["livro"] == "1A"
    assert p["data_prenotacao"] == serventia["prenotado"]


def test_mudar_a_matricula_reamarra_o_vinculo(serventia):
    """Sem isto o protocolo mostraria uma matrícula no texto e continuaria
    ligado a outra por dentro — pior que não estar ligado a nenhuma."""
    con = sqlite3.connect(serventia["banco"])
    con.execute("""INSERT INTO ri_matriculas (numero, livro, situacao, criado_em)
                   VALUES ('4000', '2', 'ATIVA', ?)""", (AGORA,))
    con.commit()
    mid = con.execute("SELECT id FROM ri_matriculas WHERE numero='4000'").fetchone()[0]
    con.close()
    post(serventia, acao="editar", matricula_numero="4000")
    p = protocolo(serventia)
    assert p["matricula_numero"] == "4000"
    assert p["matricula_id"] == mid


# ========================================================= depósito prévio

def depositos(s):
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    r = [dict(x) for x in con.execute(
        "SELECT * FROM cx_depositos WHERE ri_protocolo_id=?", (s["pid"],))]
    con.close()
    return r


def test_lancar_deposito_previo_no_titulo(serventia):
    r = post(serventia, acao="deposito", valor="450,00",
             depositante="CONSTRUTORA ALFA LTDA", forma_pagamento="PIX")
    d = depositos(serventia)
    assert len(d) == 1
    assert d[0]["valor"] == "450,00"
    assert d[0]["saldo"] == "450,00"
    assert d[0]["numero"].startswith("DP")
    assert "450,00" in r.get_data(as_text=True)


def test_o_deposito_fica_amarrado_ao_titulo(serventia):
    """Sem a amarração, a pergunta "quanto já foi pago neste título?" não tem
    resposta — o dinheiro fica no caixa sem dizer a que veio."""
    post(serventia, acao="deposito", valor="200,00")
    assert depositos(serventia)[0]["ri_protocolo_id"] == serventia["pid"]


def test_o_deposito_aparece_na_tela_do_titulo_com_saldo(serventia):
    post(serventia, acao="deposito", valor="300,00")
    post(serventia, acao="deposito", valor="150,50")
    html = serventia["cliente"].get(
        f"/registro-imoveis/protocolo/{serventia['pid']}").get_data(as_text=True)
    assert "450,50" in html, "o saldo somado do título não apareceu"


def test_sem_depositante_usa_o_apresentante(serventia):
    post(serventia, acao="deposito", valor="100,00")
    assert depositos(serventia)[0]["depositante"] == "CONSTRUTORA ALFA LTDA"


def test_valor_zero_e_recusado(serventia):
    r = post(serventia, acao="deposito", valor="0,00")
    assert depositos(serventia) == []
    assert "maior que zero" in r.get_data(as_text=True)


def test_sem_caixa_aberto_o_deposito_e_gravado_e_a_tela_avisa(serventia):
    """O dinheiro entrou. Recusar o registro porque a gaveta está fechada seria
    perder o fato — e é assim que um depósito some."""
    r = post(serventia, acao="deposito", valor="80,00")
    assert len(depositos(serventia)) == 1
    assert "não há caixa aberto" in r.get_data(as_text=True)


def test_com_caixa_aberto_o_deposito_entra_no_movimento(serventia):
    """Depósito que não entra no caixa do dia é a conferência que não fecha no
    fim do expediente, com ninguém lembrando do depósito da manhã."""
    con = sqlite3.connect(serventia["banco"])
    con.execute("""INSERT INTO cx_caixas (data, operador_nome, situacao,
                                          saldo_inicial, aberto_em)
                   VALUES (?, 'LAURA MARIA DA COSTA', 'ABERTO', '0,00', ?)""",
                (date.today().isoformat(), AGORA))
    con.commit()
    con.close()
    post(serventia, acao="deposito", valor="500,00")
    con = sqlite3.connect(serventia["banco"])
    con.row_factory = sqlite3.Row
    lanc = con.execute("""SELECT * FROM cx_lancamentos
                          WHERE natureza='DEPOSITO_PREVIO'""").fetchall()
    con.close()
    assert len(lanc) == 1
    assert lanc[0]["valor"] == "500,00"
    assert lanc[0]["sentido"] == "ENTRADA"


# =============================================== a regra que não se duplicou

def test_o_caixa_e_o_ri_usam_a_MESMA_criacao_de_deposito():
    """A criação do depósito vive em `caixa_depositos.py`, e não copiada nos dois.

    É a armadilha que produziu o defeito da função do usuário: a mesma regra
    escrita em três arquivos, e um deles divergindo em silêncio.
    """
    caixa = (RAIZ / "caixa_web.py").read_text(encoding="utf-8")
    ri = (RAIZ / "ri_web.py").read_text(encoding="utf-8")
    assert "DEP.criar(" in caixa and "DEP.criar(" in ri
    # Nenhum dos dois pode ter voltado a montar o INSERT por conta própria.
    for nome, codigo in (("caixa_web", caixa), ("ri_web", ri)):
        assert "INSERT INTO cx_depositos" not in codigo, \
            f"{nome} voltou a criar depósito por fora do módulo"


# ================================================== o espelho nas três telas
#
# "Espelhar" quer dizer UM depósito visto de vários lugares — não uma cópia em
# cada tela. Duas anotações do mesmo dinheiro divergem no dia em que uma for
# corrigida e a outra não.

def test_o_deposito_do_titulo_aparece_no_caixa_com_link(serventia):
    post(serventia, acao="deposito", valor="700,00")
    html = serventia["cliente"].get("/caixa/depositos").get_data(as_text=True)
    assert f"Título {NUMERO}/1A" in html
    assert f"/registro-imoveis/protocolo/{serventia['pid']}" in html


def test_deposito_sem_vinculo_diz_que_nao_tem(serventia):
    """Dinheiro deixado 'para quando o título chegar' existe, e não é defeito."""
    pagina = serventia["cliente"].get("/caixa/depositos").get_data(as_text=True)
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', pagina).group(1)
    serventia["cliente"].post("/caixa/depositos",
                              data={"csrf_token": token, "acao": "novo",
                                    "valor": "50,00", "depositante": "QUEM PASSOU"},
                              follow_redirects=True)
    html = serventia["cliente"].get("/caixa/depositos").get_data(as_text=True)
    assert "sem vínculo" in html


def test_deposito_no_ato_de_notas_aparece_nas_duas_telas(serventia):
    """O mesmo registro, visto do ato e visto do caixa."""
    con = sqlite3.connect(serventia["banco"])
    con.execute("""INSERT INTO nt_atos (tipo, data, livro, folha, situacao,
                                        origem, criado_em)
                   VALUES ('ESCRITURA', '2026-08-17', '150', '23', 'LAVRADO',
                           'MANUAL', ?)""", (AGORA,))
    con.commit()
    ato = con.execute("SELECT id FROM nt_atos ORDER BY id DESC LIMIT 1").fetchone()[0]
    con.close()

    pagina = serventia["cliente"].get(f"/notas/atos/{ato}").get_data(as_text=True)
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', pagina).group(1)
    serventia["cliente"].post(f"/notas/atos/{ato}",
                              data={"csrf_token": token, "acao": "deposito",
                                    "valor": "1.200,00",
                                    "depositante": "OUTORGANTE FULANO"},
                              follow_redirects=True)

    # visto do ato
    no_ato = serventia["cliente"].get(f"/notas/atos/{ato}").get_data(as_text=True)
    assert "1.200,00" in no_ato
    assert "OUTORGANTE FULANO" in no_ato

    # visto do caixa, com link de volta para o ato
    no_caixa = serventia["cliente"].get("/caixa/depositos").get_data(as_text=True)
    assert f"Ato de livro nº {ato}" in no_caixa
    assert f"/notas/atos/{ato}" in no_caixa

    # e é UM registro só, não dois
    con = sqlite3.connect(serventia["banco"])
    n = con.execute("SELECT COUNT(*) FROM cx_depositos WHERE nt_ato_id=?",
                    (ato,)).fetchone()[0]
    con.close()
    assert n == 1, "o depósito foi gravado em duplicidade"


def test_as_tres_telas_usam_a_mesma_criacao():
    """Caixa, Registro de Imóveis e Notas chamam a MESMA função.

    Três telas criando depósito é exatamente o número de cópias que produziu o
    defeito da função do usuário nesta semana.
    """
    for nome in ("caixa_web.py", "ri_web.py", "notas_web.py"):
        codigo = (RAIZ / nome).read_text(encoding="utf-8")
        assert "DEP.criar(" in codigo, f"{nome} não usa o módulo comum"
        assert "INSERT INTO cx_depositos" not in codigo, \
            f"{nome} voltou a criar depósito por fora do módulo"
