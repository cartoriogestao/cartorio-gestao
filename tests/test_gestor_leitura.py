"""Camada 4: o texto do ato contra o cadastro (por regra) e a leitura pela IA.

O QUE ESTES TESTES GUARDAM
    **Que nome se confere aqui, e não na IA**: «JOSÉ» e «JOSE» são o mesmo nome
    para a regra, e a máscara os trocaria por marcas diferentes.

    **Que nada sai sem a máscara**: o CPF do cadastro não chega ao provedor.

    **Que resposta que não é JSON vira erro, e não «nada achado»** — zero por
    engano é a mesma tela que zero medido, e são coisas diferentes.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import gestor_conferencia as GC                                  # noqa: E402
import gestor_leitura as GL                                      # noqa: E402

AGORA = "2026-09-20T10:00:00"
HOJE = date(2026, 10, 6)
TEOR = ("<p>R-1/9001 - COMPRA E VENDA. Transmitente: JOSÉ DA SILVA, CPF 000.000.044-21. "
        "Adquirente: MARIA SOUZA LIMA. Valor: R$ 120.000,00 (cento e vinte mil reais). "
        "Matrícula 9001.</p>")


@pytest.fixture()
def con(cg_casa):
    c = sqlite3.connect(cg_casa["banco"])
    c.row_factory = sqlite3.Row
    yield c
    c.close()


# 06/10/2026: o ato vai SELADO porque, por ordem do oficial, ato já lavrado só
# gera apontamento de texto se estiver selado (gestor_conferencia.so_o_essencial).
def _r(con, teor=TEOR, partes=(("JOSE DA SILVA", "000.000.044-21"), ("MARIA SOUZA LIMA", ""))):
    mid = con.execute("INSERT INTO ri_matriculas (numero, criado_em) VALUES ('9001', ?)",
                      (AGORA,)).lastrowid
    aid = con.execute(
        """INSERT INTO ri_atos (matricula_id, tipo, numero, hash_ato, lavrado_em, teor,
               natureza_titulo, data_ato, selo_texto)
           VALUES (?, 'R', 1, 'h', ?, ?, 'COMPRA E VENDA', '2026-09-20', 'MATRIC000000AAAAAAAAAAAAAAAA')""",
        (mid, AGORA, teor)).lastrowid
    for nome, doc in partes:
        con.execute("""INSERT INTO ri_partes (matricula_id, ato_id, nome, documento_numero)
                       VALUES (?, ?, ?, ?)""", (mid, aid, nome, doc))
    return aid


def _regras(achados, regra):
    return [a for a in achados if a["regra"] == regra]


# ------------------------------------------------------------ 4a, por regra


def test_acento_nao_e_divergencia_e_o_texto_bate(con):
    _r(con)
    assert _regras(GC.conferir(con, HOJE), "TEXTO_CONTRA_CADASTRO") == []


def test_nome_do_cadastro_que_nao_esta_no_texto(con):
    _r(con, partes=(("JOSE DA SILVA", ""), ("MARIA SOUSA LIMA", "")))
    t = _regras(GC.conferir(con, HOJE), "TEXTO_CONTRA_CADASTRO")
    assert len(t) == 1 and "MARIA SOUSA LIMA" in t[0]["detalhe"]


def test_documento_zerado_nao_se_cobra_e_o_errado_se_cobra(con):
    _r(con, partes=(("JOSE DA SILVA", "000.000.000-00"),))
    assert _regras(GC.conferir(con, HOJE), "TEXTO_CONTRA_CADASTRO") == []


def test_averbacao_fica_de_fora(con):
    aid = _r(con, partes=(("FULANO QUE NAO ESTA", ""),))
    con.execute("UPDATE ri_atos SET tipo='AV' WHERE id=?", (aid,))
    assert _regras(GC.conferir(con, HOJE), "TEXTO_CONTRA_CADASTRO") == []


def test_marcador_de_modelo_no_texto_e_critico_e_email_nao_conta(con):
    aid = _r(con, teor=TEOR + " Contato: cidadeexemplo@cartorio.ch")
    assert _regras(GC.conferir(con, HOJE), "MODELO_NAO_PREENCHIDO") == []
    con.execute("UPDATE ri_atos SET teor = ? WHERE id = ?",
                (TEOR + " {{ rotulo }} — {{ protocolo_frase }} e @nomefiliacao1", aid))
    m = _regras(GC.conferir(con, HOJE), "MODELO_NAO_PREENCHIDO")
    assert len(m) == 1 and m[0]["gravidade"] == "CRITICO"
    assert "{{ rotulo }}" in m[0]["detalhe"] and "@nomefiliacao1" in m[0]["detalhe"]


# ------------------------------------------------------------ 4b, a IA


class _Provedor:
    def __init__(self, resposta):
        self.resposta, self.enviados = resposta, []

    def __call__(self, pasta, *, provedor, sistema, conversa, ferramentas, modelo, maximo_de_saida, **_registro):
        self.enviados.append(conversa[0]["texto"])
        return {"texto": self.resposta, "entrada": 100, "saida": 20, "modelo": "x"}


@pytest.fixture()
def com_chave(monkeypatch):
    import agente_provedores as AP
    monkeypatch.setattr(AP, "tem_chave", lambda pasta, prov=None: True)


def test_le_uma_vez_por_versao_e_vai_sem_mascara(con, com_chave, tmp_path):
    """SEM MÁSCARA desde 06/10/2026, por decisão do oficial («liberar revisão sem
    máscara»): a máscara cegava a revisão para número de matrícula e município."""
    _r(con)
    # GRAVE desde 06/10/2026: em ato já lavrado, o apontamento leve da IA não chega
    # mais à conferência (ordem do oficial — só o fundamental).
    ia = _Provedor('{"achados": [{"gravidade": "GRAVE", "o_que": "valor por extenso diverge", "trecho": "cento"}]}')
    assert GL.ler_pendentes(con, tmp_path, conversar=ia)["lidos"] == 1
    assert "000.000.044-21" in ia.enviados[0]
    assert GL.ler_pendentes(con, tmp_path, conversar=ia)["lidos"] == 0     # mesma versão
    leitura = _regras(GC.conferir(con, HOJE), "LEITURA_DO_TEXTO")
    assert len(leitura) == 1 and leitura[0]["setor"] == "RI_QUALIFICACAO"


def test_texto_que_mudou_nao_herda_o_apontamento(con, com_chave, tmp_path):
    aid = _r(con)
    GL.ler_pendentes(con, tmp_path, conversar=_Provedor(
        '{"achados": [{"gravidade": "GRAVE", "o_que": "data impossível"}]}'))
    assert _regras(GC.conferir(con, HOJE), "LEITURA_DO_TEXTO")[0]["gravidade"] == "CRITICO"
    con.execute("UPDATE ri_atos SET teor = ? WHERE id = ?", (TEOR + " Retificado.", aid))
    assert _regras(GC.conferir(con, HOJE), "LEITURA_DO_TEXTO") == []


def test_resposta_que_nao_e_json_vira_erro_e_nao_nada_achado(con, com_chave, tmp_path):
    _r(con)
    r = GL.ler_pendentes(con, tmp_path, conversar=_Provedor("Não encontrei problemas."))
    assert r["erros"] == 1 and r["lidos"] == 0
    erro = con.execute("SELECT erro FROM ge_leituras").fetchone()[0]
    assert "sem JSON" in erro


def test_sem_chave_nao_le_e_diz_por_que(con, monkeypatch, tmp_path):
    import agente_provedores as AP
    monkeypatch.setattr(AP, "tem_chave", lambda pasta, prov=None: False)
    _r(con)
    assert "sem_chave" in GL.ler_pendentes(con, tmp_path, conversar=_Provedor("{}"))


def test_teto_do_dia(con, com_chave, tmp_path):
    for _ in range(3):
        _r(con)
    r = GL.ler_pendentes(con, tmp_path, teto=2, conversar=_Provedor('{"achados": []}'))
    assert r["lidos"] == 2


def test_revisado_sai_da_lista(con, com_chave, tmp_path):
    _r(con)
    GL.ler_pendentes(con, tmp_path, conversar=_Provedor(
        '{"achados": [{"gravidade": "ATENCAO", "o_que": "x"}]}'))
    lid = con.execute("SELECT id FROM ge_leituras").fetchone()[0]
    GL.marcar_revisado(con, lid, "beatriz")
    assert _regras(GC.conferir(con, HOJE), "LEITURA_DO_TEXTO") == []
    assert json.loads(con.execute("SELECT achados_json FROM ge_leituras").fetchone()[0])


def test_com_a_configuracao_de_mascara_o_cpf_nao_sai(con, com_chave, tmp_path):
    con.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('revisao_mascara', '1')")
    _r(con)
    ia = _Provedor('{"achados": []}')
    GL.ler_pendentes(con, tmp_path, conversar=ia)
    assert "000.000.044-21" not in ia.enviados[0] and "00000004421" not in ia.enviados[0]


def test_a_averbacao_entra_com_a_ficha_e_o_ato_ja_revisado_nao_se_rele(con):
    import revisao_previa as RV
    mid = con.execute("""INSERT INTO ri_matriculas (numero, teor, criado_em)
                         VALUES ('4200', 'FICHA: imóvel de 10 ha', ?)""", (AGORA,)).lastrowid
    for n, tipo, teor in ((1, "R", "R-1: venda"), (2, "AV", "AV-2: cancela a hipoteca do R-1")):
        con.execute("""INSERT INTO ri_atos (matricula_id, tipo, numero, teor, lavrado_em, hash_ato)
                       VALUES (?, ?, ?, ?, '2026-09-20T10:00:00', ?)""", (mid, tipo, n, teor, f"h{n}"))
    cands = {c["rotulo"]: c for c in GL.candidatos(con) if c["tabela"] == "ri_atos"}
    assert "AV-2" in cands and "FICHA: imóvel de 10 ha" in GL.dossie(cands["AV-2"])
    assert "R-1: venda" in GL.dossie(cands["AV-2"])          # o ato anterior vai junto
    RV.init_schema(con)
    con.execute("""INSERT INTO rv_revisoes (atribuicao, alvo_id, hash_texto, dossie, situacao,
                       pedido_em) VALUES ('RI', ?, ?, 'x', 'PRONTA', ?)""",
                (mid, RV.hash_do_ato("AV", "AV-2: cancela a hipoteca do R-1"), AGORA))
    assert "AV-2" not in {c["rotulo"] for c in GL.candidatos(con) if c["tabela"] == "ri_atos"}


def test_a_procuracao_se_le_como_no_botao(con, com_chave, tmp_path):
    """13/10/2026, ordem do oficial («atualiza o gestor»): a procuração vai ao
    mesmo Sonnet, com a mesma instrução e o cadastro inteiro das partes; a
    escritura continua na régua geral."""
    import revisao_previa as RV
    proc = con.execute("""INSERT INTO nt_atos (tipo, data, situacao, teor, criado_em)
                          VALUES ('PROCURACAO', '2026-10-13', 'EM_LAVRATURA',
                                  '<p>HUGO nomeia procurador JOSE</p>', ?)""", (AGORA,)).lastrowid
    con.execute("""INSERT INTO nt_ato_partes (ato_id, nome, nome_norm, qualificacao, profissao,
                       ordem, criado_em) VALUES (?, 'HUGO', 'hugo', 'OUTORGANTE', 'lavrador', 1, ?)""",
                (proc, AGORA))
    escr = con.execute("""INSERT INTO nt_atos (tipo, data, situacao, teor, criado_em)
                          VALUES ('ESCRITURA', '2026-10-13', 'EM_LAVRATURA',
                                  '<p>compra e venda</p>', ?)""", (AGORA,)).lastrowid
    con.commit()
    vistos = {}

    def ia(pasta, *, provedor, sistema, conversa, ferramentas, modelo, maximo_de_saida, **_registro):
        texto = conversa[0]["texto"]
        alvo = "proc" if "HUGO" in texto else "escr"
        vistos[alvo] = (modelo, sistema, texto)
        return {"texto": '{"achados": []}', "entrada": 10, "saida": 5, "modelo": None}

    GL.ler_pendentes(con, tmp_path, conversar=ia)
    modelo, sistema, texto = vistos["proc"]
    assert modelo == RV.MODELO_DA_PROCURACAO and sistema == RV.INSTRUCAO_DA_PROCURACAO
    assert "lavrador" in texto and "PARTES CADASTRADAS" in texto
    assert vistos["escr"][1] == GL.INSTRUCAO
    linha = con.execute("SELECT modelo FROM ge_leituras WHERE tabela='nt_atos' AND ato_id=?",
                        (proc,)).fetchone()
    assert linha[0] == RV.MODELO_DA_PROCURACAO
    # mesma versão não se relê — o hash leva a instrução da procuração
    assert GL.ler_pendentes(con, tmp_path, conversar=ia)["lidos"] == 0
    assert escr


# ================================================== CONSERTO DO L031R (18/10/2026)
# A TELA DAS LEITURAS SÓ LÊ. O `executescript` do esquema confirmava o que
# estava aberto e não deixava transação; o `bd.escrever` que o trocou abre a
# transação com a trava única da ponte e não a confirmava. A rota GET
# (`/administrativo/gestor/leituras`) chama `achados_vigentes`, que roda o
# esquema e depois monta TODOS os candidatos (com o dossiê de cada R e AV):
# durante a página inteira, quem gravasse no balcão esperava a trava e levava
# «database is locked».

import banco_pg                                                   # noqa: E402

so_no_postgres = pytest.mark.skipif(
    not banco_pg.ativo(), reason="mede a trava única da ponte (CG_PG_DSN)")


@so_no_postgres
def test_a_tela_das_leituras_nao_prende_o_balcao(con, cg_casa):
    GL.init_leitura_schema(con)                  # a leitura já rodou um dia
    _r(con)
    con.commit()
    tela = sqlite3.connect(cg_casa["banco"])     # a conexão da rota GET
    balcao = sqlite3.connect(cg_casa["banco"])
    try:
        assert GL.achados_vigentes(tela) == []
        balcao.execute("PRAGMA busy_timeout = 500")
        try:
            balcao.execute("INSERT INTO settings(key, value) VALUES ('balcao_gravou', '1') "
                           "ON CONFLICT(key) DO UPDATE SET value = excluded.value")
            balcao.commit()
        except sqlite3.OperationalError as erro:
            pytest.fail("a tela das leituras deixou a transação aberta e a trava da "
                        f"ponte presa: o balcão não gravou ({erro})")
    finally:
        balcao.close()
        tela.close()


# ================================================== LX13 (A6 da auditoria LS03)
# O «sem máscara» de 06/10/2026 foi decidido com o Claude como provedor. Sem a
# chave dele, a leitura cai no provedor da tela do agente (DeepSeek de
# fábrica) — e lá ia SEM máscara, contra o que a docstring dizia. Agora vai
# mascarada, salvo a liberação expressa no Gestor → IA (padrão desligado).


@pytest.fixture()
def so_o_reserva(monkeypatch):
    """Sem a chave do Claude; o provedor da tela do agente tem a dele."""
    import agente_provedores as AP
    monkeypatch.setattr(AP, "tem_chave", lambda pasta, prov=None: prov != "claude")


def test_no_provedor_reserva_a_leitura_vai_mascarada(con, so_o_reserva, tmp_path):
    _r(con)
    ia = _Provedor('{"achados": []}')
    r = GL.ler_pendentes(con, tmp_path, conversar=ia)
    assert r["lidos"] == 1 and r["provedor"] != "claude"
    assert "000.000.044-21" not in ia.enviados[0] and "00000004421" not in ia.enviados[0]


def test_o_oficial_pode_liberar_o_reserva_sem_mascara(con, so_o_reserva, tmp_path):
    con.execute("INSERT INTO settings (key, value) VALUES (?, '1') ON CONFLICT (key) "
                "DO UPDATE SET value = excluded.value", (GL.CHAVE_RESERVA_SEM_MASCARA,))
    _r(con)
    ia = _Provedor('{"achados": []}')
    GL.ler_pendentes(con, tmp_path, conversar=ia)
    assert "000.000.044-21" in ia.enviados[0]


def test_a_regra_da_mascara_por_provedor(con):
    assert GL.vai_mascarado(con, "claude") is False          # decisão de 06/10/2026
    assert GL.vai_mascarado(con, "deepseek") is True         # padrão: desligado
    con.execute("INSERT INTO settings (key, value) VALUES (?, 'sim') ON CONFLICT (key) "
                "DO UPDATE SET value = excluded.value", (GL.CHAVE_RESERVA_SEM_MASCARA,))
    assert GL.vai_mascarado(con, "deepseek") is True         # só '1' libera
    con.execute("UPDATE settings SET value = '1' WHERE key = ?", (GL.CHAVE_RESERVA_SEM_MASCARA,))
    assert GL.vai_mascarado(con, "deepseek") is False
    con.execute("INSERT INTO settings (key, value) VALUES ('revisao_mascara', '1') "
                "ON CONFLICT (key) DO UPDATE SET value = excluded.value")
    assert GL.vai_mascarado(con, "claude") is True and GL.vai_mascarado(con, "deepseek") is True


def test_a_docstring_nao_diz_mais_que_tudo_sai_mascarado():
    assert "CPF e nome saem como marcas" not in GL.__doc__
    assert "provedor reserva" in GL.__doc__


def _token_da_tela(c) -> str:
    import re
    html = c.get("/administrativo/gestor/ia").get_data(as_text=True)
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


def test_a_cautela_do_reserva_se_muda_no_gestor_e_so_pelo_admin(cg_casa_logada):
    casa = cg_casa_logada
    c, db = casa["c"], casa["db"]
    tela = c.get("/administrativo/gestor/ia").get_data(as_text=True)
    assert "Permitir sem máscara no provedor reserva" in tela
    assert 'name="reserva_sem_mascara" value="1" checked' not in tela     # nasce desligada
    r = c.post("/administrativo/gestor/ia/cautelas",
               data={"csrf_token": _token_da_tela(c), "reserva_sem_mascara": "1"})
    assert r.status_code == 302 and db.get_setting(GL.CHAVE_RESERVA_SEM_MASCARA) == "1"
    c.post("/administrativo/gestor/ia/cautelas", data={"csrf_token": _token_da_tela(c)})
    assert db.get_setting(GL.CHAVE_RESERVA_SEM_MASCARA) == "0"
    from bd_nativo import banco
    with db.connect() as cx:
        assert banco(cx).valor("SELECT count(*) FROM audit_logs WHERE action = 'GESTOR_IA_CAUTELA'") == 2
    # o balcão não muda a cautela
    from conftest import cg_login
    db.create_user("balcao", "Balcao Exemplo", "Senha#12345", "USER")
    outro = casa["app"].test_client()
    cg_login(outro, "balcao", "Senha#12345")
    outro.post("/administrativo/gestor/ia/cautelas", data={"reserva_sem_mascara": "1"})
    assert db.get_setting(GL.CHAVE_RESERVA_SEM_MASCARA) == "0"
