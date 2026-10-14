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

    def __call__(self, pasta, *, provedor, sistema, conversa, ferramentas, modelo, maximo_de_saida):
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

    def ia(pasta, *, provedor, sistema, conversa, ferramentas, modelo, maximo_de_saida):
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
