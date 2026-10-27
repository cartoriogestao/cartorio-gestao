"""A certidão de ônus POSITIVA ou NEGATIVA, e a IA que sugere — 13/10/2026.

    «precisamos ajustar o modelo de certidao de onus para contemplar tanto a
     positiva e a negativa, podemos incluir a api da ia para fazer a sugestao
     de qual certidao se trata para aquela matricula e escolher o teor
     correto» — o oficial

O que se guarda aqui: o título muda com a escolha; a positiva TRANSCREVE o ato;
o trecho que vai ao papel está escrito na ficha; a negativa não passa sobre ônus
lavrado nem contra a IA sem justificativa; e o módulo não emite nada sozinho.
"""
from __future__ import annotations

import ast
import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import banco_pg  # noqa: E402
import ri_onus as ONUS  # noqa: E402
import ri_onus_ia as RONIA  # noqa: E402

SENHA = "Senha#12345"

TEOR_COM_HIPOTECA = (
    "<p>IMÓVEL: Uma gleba de terras denominada «Vargem Limpa», com 48,40,12ha.</p>"
    "<p>R-01/4201 - COMPRA E VENDA. O imóvel foi adquirido livre e desembaraçado de "
    "quaisquer ônus.</p>"
    "<p>R-02/4201 - Registra-se a Cédula Rural Pignoratícia e Hipotecária nº 40/00596-8, "
    "dando em garantia hipotecária de primeiro grau o imóvel objeto desta matrícula em "
    "favor do BANCO EXEMPLO S/A.</p>")
TRECHO_DA_HIPOTECA = (
    "R-02/4201 - Registra-se a Cédula Rural Pignoratícia e Hipotecária nº 40/00596-8, "
    "dando em garantia hipotecária de primeiro grau o imóvel objeto desta matrícula em "
    "favor do BANCO EXEMPLO S/A.")


# ------------------------------------------------------------- o domínio


def _a(tipo, numero, natureza, teor="", cancelado=0, id_=None):
    return {"id": id_ or numero, "tipo": tipo, "numero": numero,
            "natureza_titulo": natureza, "teor": teor, "cancelado": cancelado,
            "rotulo": f"{tipo}-{numero:02d}/4201"}


def _vigentes(*atos):
    return ONUS.onus_vigentes(list(atos), rotulo=lambda a: a["rotulo"])


def test_o_titulo_diz_positiva_ou_negativa_nas_duas_perguntas():
    assert RONIA.titulo("POSITIVA", "NEGATIVA").upper() == (
        "CERTIDÃO POSITIVA DE ÔNUS E NEGATIVA DE REGISTRO DE AÇÕES REAIS E "
        "PESSOAIS REIPERSECUTÓRIAS")
    assert RONIA.titulo("NEGATIVA", "NEGATIVA").upper().startswith(
        "CERTIDÃO NEGATIVA DE ÔNUS E NEGATIVA")
    # o «DE» que sobrava nas certidões de 2024 («CERTIDÃO DE POSITIVA DE ÔNUS»)
    assert "DE POSITIVA" not in RONIA.titulo("POSITIVA", "POSITIVA").upper()


def test_o_tipo_deixou_de_se_chamar_negativa():
    import ri_schema as RS
    assert "negativa" not in RS.TIPOS_CERTIDAO["ONUS"].lower().split("(")[0]


def test_esta_escrito_ignora_espaco_e_caixa_e_nao_aceita_palavra_trocada():
    ficha = RONIA.normalizar(TEOR_COM_HIPOTECA)
    assert RONIA.esta_escrito(TRECHO_DA_HIPOTECA.upper().replace(" ", "  "), ficha)
    assert not RONIA.esta_escrito(TRECHO_DA_HIPOTECA.replace("primeiro", "segundo"), ficha)
    assert not RONIA.esta_escrito("", ficha)


def test_a_citacao_de_acao_e_separada_do_onus():
    padrao = RONIA.padrao_do_sistema(_vigentes(
        _a("R", 2, "Hipoteca", "R-02/4201 - HIPOTECA."),
        _a("AV", 3, "Citações de Ações Reais ou Pessoais Reipersecutórias",
           "AV-03/4201 - CITAÇÃO da ação real.")))
    assert padrao["resultado_onus"] == "POSITIVA"
    assert padrao["resultado_acoes"] == "POSITIVA"
    assert [i["rotulo"] for i in padrao["itens_onus"]] == ["R-02/4201"]
    assert [i["rotulo"] for i in padrao["itens_acoes"]] == ["AV-03/4201"]


def _decidir(**kw):
    base = dict(texto_da_ficha_=RONIA.normalizar(TEOR_COM_HIPOTECA), onus_vigentes=[],
                sugestao=None, resultado_onus="NEGATIVA", resultado_acoes="NEGATIVA",
                marcados=[], manual_onus="", manual_acao="", justificativa="",
                # sem leitura da IA, quem emite marca que conferiu o dono (15/10)
                proprietario_conferido=True)
    base.update(kw)
    return RONIA.decidir(**base)


def test_sem_escolher_positiva_ou_negativa_nada_sai():
    with pytest.raises(RONIA.OnusError, match="POSITIVA ou NEGATIVA"):
        _decidir(resultado_onus="")


def test_negativa_sobre_onus_lavrado_no_sistema_e_recusada():
    with pytest.raises(RONIA.OnusError, match="não pode ser negativa"):
        _decidir(onus_vigentes=_vigentes(_a("R", 2, "Hipoteca", "R-02/4201 - HIPOTECA.")))


def test_positiva_sem_ato_transcrito_e_recusada():
    with pytest.raises(RONIA.OnusError, match="ao menos um ato transcrito"):
        _decidir(resultado_onus="POSITIVA")


def test_transcricao_que_nao_esta_na_ficha_e_recusada():
    with pytest.raises(RONIA.OnusError, match="não está escrita na ficha"):
        _decidir(resultado_onus="POSITIVA",
                 manual_onus="R-02/4201 - HIPOTECA em favor de quem eu quiser.")


def test_transcricao_que_esta_na_ficha_entra_com_o_rotulo_tirado_do_texto():
    d = _decidir(resultado_onus="POSITIVA", manual_onus=TRECHO_DA_HIPOTECA)
    assert d["resultado_onus"] == "POSITIVA"
    (item,) = d["itens_onus"]
    assert item["rotulo"] == "R-02/4201"
    assert item["texto"].startswith("Registra-se a Cédula Rural")
    assert d["onus_escolhido_por"] == "BALCAO"


def _sugestao(onus="POSITIVA", trecho=TRECHO_DA_HIPOTECA, literal=True, vale=True):
    return {"id": 7, "situacao": "PRONTA", "vale": vale, "onus": onus, "acoes": "NEGATIVA",
            "itens": [{"categoria": "ONUS", "ato": "R-02/4201", "natureza": "Hipoteca",
                       "trecho": trecho, "literal": literal}],
            "cancelados": [], "parecer": "hipoteca de 2014 sem baixa"}


def test_trecho_da_ia_que_nao_esta_escrito_nao_pode_ser_marcado():
    with pytest.raises(RONIA.OnusError, match="não está\\s+escrito na ficha"):
        _decidir(resultado_onus="POSITIVA",
                 sugestao=_sugestao(trecho="R-02/4201 - hipoteca inventada", literal=False),
                 marcados=["IA:1"])


def test_positiva_pela_sugestao_da_ia_transcreve_o_trecho_dela():
    d = _decidir(resultado_onus="POSITIVA", sugestao=_sugestao(), marcados=["IA:1"])
    assert d["itens_onus"][0]["origem"] == "IA"
    assert d["onus_sugestao_id"] == 7


def test_negativa_contra_a_ia_exige_justificativa_e_ela_fica():
    with pytest.raises(RONIA.OnusError, match="escreva por que"):
        _decidir(sugestao=_sugestao())
    d = _decidir(sugestao=_sugestao(),
                 justificativa="hipoteca R-2 quitada e baixada pela AV-5")
    assert d["resultado_onus"] == "NEGATIVA"
    assert "AV-5" in d["onus_justificativa"]


def test_sugestao_de_antes_de_a_ficha_mudar_nao_conta():
    # vale=False: ato lavrado ou cancelado depois da leitura
    d = _decidir(sugestao=_sugestao(vale=False))
    assert d["resultado_onus"] == "NEGATIVA" and d["onus_justificativa"] == ""
    assert d["onus_sugestao_id"] is None


def test_ler_resposta_confere_cada_trecho_contra_a_ficha():
    resposta = json.dumps({
        "onus": "POSITIVA", "acoes": "NEGATIVA",
        "itens": [{"categoria": "ONUS", "ato": "R-02/4201", "natureza": "Hipoteca",
                   "trecho": TRECHO_DA_HIPOTECA},
                  {"categoria": "ONUS", "ato": "R-09/4201", "natureza": "Penhora",
                   "trecho": "R-09/4201 - PENHORA que não existe"}],
        "cancelados": [], "parecer": "ok"})
    r = RONIA.ler_resposta("```json\n" + resposta + "\n```",
                           RONIA.normalizar(TEOR_COM_HIPOTECA))
    assert [i["literal"] for i in r["itens"]] == [True, False]


def test_o_modulo_nao_emite_nao_sela_nao_numera_e_nao_cobra():
    arvore = ast.parse((RAIZ / "ri_onus_ia.py").read_text(encoding="utf-8"))
    nomes = {n.name for n in arvore.body if isinstance(n, ast.FunctionDef)}
    proibidas = ("emitir", "selar", "numerar", "cobrar", "lavrar", "gravar_certidao")
    assert not [n for n in nomes if any(p in n for p in proibidas)], nomes


# ------------------------------------------------------- a leitura da IA


def _banco_com_ficha(tmp_path):
    banco = tmp_path / "b.sqlite3"
    # módulo nativo não roda no SQLite solto: o arquivo é registrado como «banco da casa»
    banco_pg.registrar_banco(banco)
    con = sqlite3.connect(banco)
    con.executescript("""
        CREATE TABLE ri_matriculas (id INTEGER PRIMARY KEY, numero TEXT, livro TEXT, teor TEXT);
        CREATE TABLE ri_atos (id INTEGER PRIMARY KEY, matricula_id INTEGER, tipo TEXT,
            numero INTEGER, data_ato TEXT, natureza_titulo TEXT, cancelado INTEGER, teor TEXT);
        CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT);""")
    con.execute("INSERT INTO ri_matriculas VALUES (1, '4201', '2', ?)", (TEOR_COM_HIPOTECA,))
    con.commit()
    return banco, con


def test_a_leitura_grava_a_sugestao_e_ela_perde_valor_quando_a_ficha_muda(tmp_path):
    banco, con = _banco_com_ficha(tmp_path)
    sid, nova = RONIA.pedir(con, 1, usuario="QUEM ATENDE")
    con.commit()
    assert nova and RONIA.pedir(con, 1)[1] is False

    def conversar(pasta, **kw):
        assert "R-02/4201" in kw["conversa"][0]["texto"]
        return {"texto": json.dumps({
            "onus": "POSITIVA", "acoes": "NEGATIVA",
            "itens": [{"categoria": "ONUS", "ato": "R-02/4201", "natureza": "Hipoteca",
                       "trecho": TRECHO_DA_HIPOTECA}],
            "cancelados": [], "parecer": "hipoteca sem baixa"}),
            "modelo": "teste", "entrada": 10, "saida": 5}

    RONIA.executar(banco, tmp_path, sid, conversar=conversar)
    s = RONIA.ultima(con, 1)
    assert s["situacao"] == "PRONTA" and s["vale"] and s["onus"] == "POSITIVA"
    assert s["itens"][0]["literal"] is True

    con.execute("""INSERT INTO ri_atos (matricula_id, tipo, numero, cancelado, teor)
                   VALUES (1, 'AV', 3, 0, 'AV-03/4201 - CANCELAMENTO da hipoteca R-02.')""")
    con.commit()
    assert RONIA.ultima(con, 1)["vale"] is False
    assert RONIA.itens_da_sugestao(RONIA.ultima(con, 1)) == []


def test_ia_que_nao_responde_vira_erro_e_nao_trava(tmp_path):
    banco, con = _banco_com_ficha(tmp_path)
    sid, _ = RONIA.pedir(con, 1)
    con.commit()

    def conversar(pasta, **kw):
        raise RuntimeError("sem rede")

    RONIA.executar(banco, tmp_path, sid, conversar=conversar)
    assert RONIA.ultima(con, 1)["situacao"] == "ERRO"


def test_desligada_por_configuracao(tmp_path):
    _banco, con = _banco_com_ficha(tmp_path)
    con.execute("INSERT INTO settings VALUES ('onus_ia', '0')")
    assert RONIA.ligada(con, tmp_path) is False


def test_tabela_que_ja_existe_sem_o_indice_ganha_o_indice(tmp_path):
    """O `executescript` do SQLite rodava o `CREATE INDEX IF NOT EXISTS` toda vez.
    No nativo o `init_schema` só escreve o que falta — e confere o índice à
    parte, senão a tabela que já existe nunca mais o ganha (revisão do L052)."""
    from bd_nativo import Banco
    _banco, con = _banco_com_ficha(tmp_path)
    RONIA.init_schema(con)
    con.commit()
    con.execute("DROP INDEX ix_ri_onus_sugestoes_matricula")
    con.commit()

    RONIA.init_schema(con)
    con.commit()
    assert Banco(con).valor(
        """SELECT count(*) AS n FROM pg_indexes
            WHERE schemaname = current_schema() AND tablename = 'ri_onus_sugestoes'
              AND indexname = 'ix_ri_onus_sugestoes_matricula'""") == 1


# ------------------------------------------------------------- a tela


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado
    return achado.group(1)


def _entrar(app, usuario):
    c = app.test_client()
    c.post("/login", data={"username": usuario, "password": SENHA,
                           "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return c


@pytest.fixture()
def casa(cg_casa):
    cg_casa["db"].create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    return {**cg_casa, "oficial": _entrar(cg_casa["app"], "mario")}


def _ficha_acervo(casa, numero="4201"):
    con = sqlite3.connect(casa["banco"])
    cur = con.execute(
        """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao, tipo_ficha,
               origem, criado_em, data_abertura, cidade, uf, teor)
           VALUES (?, '2', '2', 'ATIVA', 'ACERVO', 'MANUAL', '2026-10-13T08:00',
                   '2010-01-01', 'Cidade Exemplo', 'MA', ?)""", (numero, TEOR_COM_HIPOTECA))
    con.commit()
    mid = int(cur.lastrowid)
    con.close()
    return mid


def _emitir(casa, mid, **campos):
    c = casa["oficial"]
    tela = c.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    dados = {"csrf_token": _token(tela), "tipo": "ONUS", "fonte_corpo": "TEXTO",
             "requerente": "FULANO DE TAL", "selo_texto": "SELO-DE-TESTE-0001",
             "onus_formulario": "1", "proprietario_conferido": "1"}
    dados.update(campos)
    c.post(f"/registro-imoveis/{mid}/certidao", data=dados)
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    linha = con.execute("SELECT * FROM ri_certidoes WHERE matricula_id=? ORDER BY id DESC",
                        (mid,)).fetchone()
    con.close()
    return dict(linha) if linha else None


def test_a_ficha_mostra_o_quadro_da_certidao_de_onus(casa):
    mid = _ficha_acervo(casa)
    html = casa["oficial"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    assert 'id="certidao-onus"' in html
    assert 'name="resultado_onus"' in html and 'name="onus_transcricao"' in html
    # numa ficha de acervo sem ato lavrado ninguém sabe a resposta: nada vem marcado
    assert not re.search(r'name="resultado_onus" value="\w+"\s+checked', html)


def test_sem_escolher_a_certidao_nao_sai(casa):
    mid = _ficha_acervo(casa)
    assert _emitir(casa, mid) is None


def test_positiva_com_a_transcricao_do_teor(casa):
    mid = _ficha_acervo(casa)
    c = _emitir(casa, mid, resultado_onus="POSITIVA", resultado_acoes="NEGATIVA",
                onus_transcricao=TRECHO_DA_HIPOTECA)
    assert c, "a certidão positiva não foi emitida"
    texto = RONIA.normalizar(c["corpo"])
    assert "CERTIDÃO POSITIVA DE ÔNUS E NEGATIVA DE REGISTRO" in texto
    assert "HÁ ÔNUS REAIS" in texto and "garantia hipotecária de primeiro grau" in texto
    assert "NADA CONSTA de ônus" not in texto
    assert c["resultado_onus"] == "POSITIVA" and c["onus_escolhido_por"] == "BALCAO"


def test_negativa_escolhida_sai_livre_e_desembaracada(casa):
    mid = _ficha_acervo(casa, "4202")
    c = _emitir(casa, mid, resultado_onus="NEGATIVA", resultado_acoes="NEGATIVA")
    texto = RONIA.normalizar(c["corpo"])
    assert "CERTIDÃO NEGATIVA DE ÔNUS E NEGATIVA DE REGISTRO" in texto
    assert "LIVRE E DESEMBARAÇADO" in texto and "NÃO CONSTA registro de citação" in texto
    assert c["resultado_onus"] == "NEGATIVA"


def test_sugerir_sem_chave_da_ia_avisa_e_nao_pede_nada(casa):
    mid = _ficha_acervo(casa)
    c = casa["oficial"]
    tela = c.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    r = c.post(f"/registro-imoveis/{mid}/onus/sugerir",
               data={"csrf_token": _token(tela)}, follow_redirects=True)
    assert "não está ligada" in r.get_data(as_text=True)
    con = sqlite3.connect(casa["banco"])
    tem = con.execute("SELECT name FROM sqlite_master WHERE name='ri_onus_sugestoes'").fetchone()
    assert not tem or con.execute("SELECT COUNT(*) FROM ri_onus_sugestoes").fetchone()[0] == 0
    con.close()


# ------------------------------------------- as duas ordens de 13/10/2026


def test_no_sandbox_a_ia_nao_existe(tmp_path, monkeypatch):
    """«nao quero ia na sandbox» — o oficial. Nem com chave, nem com a
    configuração ligada: a escolha ali é sempre manual."""
    _banco, con = _banco_com_ficha(tmp_path)
    monkeypatch.setenv("CARTORIO_GESTAO_SANDBOX", "1")
    assert RONIA.no_sandbox(con) is True
    assert RONIA.ligada(con, tmp_path) is False


def test_a_noticia_de_penhor_entra_na_certidao_de_onus():
    """«entra o penhor na certidao de onus» — o oficial, depois do ensaio da
    2914, em que a IA marcou as AV-05/06 (penhor rural do gado, no Livro 3)
    só «por cautela». É o que a casa já fazia: a positiva da 3376 (2024)
    transcreve a AV-02 de penhor pecuário."""
    assert "NOTÍCIA DE PENHOR" in RONIA.INSTRUCAO
    assert "TAMBÉM É ÔNUS" in RONIA.INSTRUCAO
    achado = ONUS.classificar({"tipo": "AV", "natureza_titulo": None, "cancelado": 0,
                               "teor": "AV-05/2914 - noticia de penhor rural cedular."})
    assert achado is not None


# ------------------------------- a IA confere o proprietário (15/10/2026)
#
# «a IA confere o proprietario» — o oficial, depois de a certidão de ônus
# 64/2026 (matrícula 3371) sair com o dono da matrícula-mãe: o cadastro vinha
# errado da importação, e o papel imprime o cadastro.

CADASTRO_ERRADO = [{"nome": "TOMAS EXEMPLO BARROS", "documento_numero": "00000000191"}]
CADASTRO_CERTO = [{"nome": "Magno Exemplo Pereira", "documento_numero": "00000000272"},
                  {"nome": "MARIANA EXEMPLO DOS SANTOS", "documento_numero": ""}]


def _leitura(*donos, situacao="PRONTA", vale=True):
    return {"id": 9, "situacao": situacao, "vale": vale, "onus": "NEGATIVA",
            "acoes": "NEGATIVA", "itens": [], "cancelados": [], "parecer": "",
            "proprietarios": list(donos), "proprietarios_ato": "R-01/4201",
            "proprietarios_trecho": "vende a MAGNO e MARIANA", "proprietarios_literal": True}


DONOS_LIDOS = ({"nome": "MAGNO EXEMPLO PEREIRA", "documento": ""},
               {"nome": "Mariana Exemplo dos Santos", "documento": ""})


def test_o_proprietario_confere_sem_acento_caixa_ou_de_da_dos():
    c = RONIA.conferir_proprietarios(CADASTRO_CERTO, _leitura(*DONOS_LIDOS))
    assert c["situacao"] == RONIA.CONFERE


def test_o_documento_decide_quando_os_dois_lados_tem():
    lido = {"nome": "MAGNO E PEREIRA", "documento": "00000000272"}
    c = RONIA.conferir_proprietarios(CADASTRO_CERTO[:1], _leitura(lido))
    assert c["situacao"] == RONIA.CONFERE


def test_o_caso_da_3371_diverge_e_diz_quem_falta_e_quem_sobra():
    c = RONIA.conferir_proprietarios(CADASTRO_ERRADO, _leitura(*DONOS_LIDOS))
    assert c["situacao"] == RONIA.DIVERGE
    assert [p["nome"] for p in c["sobram"]] == ["TOMAS EXEMPLO BARROS"]
    assert len(c["faltam"]) == 2


def test_divergencia_sem_justificativa_nao_emite():
    with pytest.raises(RONIA.OnusError, match="não confere com o teor"):
        _decidir(proprietarios_cadastro=CADASTRO_ERRADO, sugestao=_leitura(*DONOS_LIDOS),
                 ia_ligada=True)


def test_divergencia_com_justificativa_emite_e_grava_o_porque():
    d = _decidir(proprietarios_cadastro=CADASTRO_ERRADO, sugestao=_leitura(*DONOS_LIDOS),
                 ia_ligada=True, justificativa_proprietario="a IA leu o vendedor do R-1")
    assert d["onus_proprietario_conferencia"] == RONIA.DIVERGE
    assert "vendedor" in d["onus_proprietario_justificativa"]


def test_leitura_que_confere_dispensa_a_caixa():
    d = _decidir(proprietarios_cadastro=CADASTRO_CERTO, sugestao=_leitura(*DONOS_LIDOS),
                 ia_ligada=True, proprietario_conferido=False)
    assert d["onus_proprietario_conferencia"] == RONIA.CONFERE


def test_ia_ainda_lendo_espera():
    with pytest.raises(RONIA.OnusError, match="ainda está lendo"):
        _decidir(proprietarios_cadastro=CADASTRO_CERTO, ia_ligada=True,
                 sugestao=_leitura(situacao="LENDO"))


def test_sem_leitura_quem_emite_marca_que_conferiu():
    with pytest.raises(RONIA.OnusError, match="Conferi o proprietário no teor"):
        _decidir(proprietarios_cadastro=CADASTRO_CERTO, proprietario_conferido=False)
    d = _decidir(proprietarios_cadastro=CADASTRO_CERTO, proprietario_conferido=True)
    assert d["onus_proprietario_conferencia"] == "CONFERIDO_NO_BALCAO"


def test_leitura_velha_nao_confere_nada():
    with pytest.raises(RONIA.OnusError, match="Conferi o proprietário"):
        _decidir(proprietarios_cadastro=CADASTRO_CERTO, proprietario_conferido=False,
                 ia_ligada=True, sugestao=_leitura(*DONOS_LIDOS, vale=False))


def test_a_ia_devolve_os_donos_e_o_trecho_conferido():
    resposta = json.dumps({"onus": "NEGATIVA", "acoes": "NEGATIVA", "itens": [],
                           "proprietarios": [{"nome": "BANCO EXEMPLO S/A", "documento": "x"}],
                           "proprietarios_ato": "R-02/4201",
                           "proprietarios_trecho": "em favor do BANCO EXEMPLO S/A."})
    r = RONIA.ler_resposta(resposta, RONIA.normalizar(TEOR_COM_HIPOTECA))
    assert r["proprietarios"] == [{"nome": "BANCO EXEMPLO S/A", "documento": ""}]
    assert r["proprietarios_literal"] is True
    assert "PROPRIETÁRIOS DE HOJE" in RONIA.INSTRUCAO


def test_sem_conferir_o_proprietario_a_certidao_nao_sai(casa):
    mid = _ficha_acervo(casa, "4203")
    assert _emitir(casa, mid, resultado_onus="NEGATIVA", resultado_acoes="NEGATIVA",
                   proprietario_conferido="") is None


def test_a_certidao_grava_como_o_proprietario_foi_conferido(casa):
    mid = _ficha_acervo(casa, "4204")
    c = _emitir(casa, mid, resultado_onus="NEGATIVA", resultado_acoes="NEGATIVA")
    assert c["onus_proprietario_conferencia"] == "CONFERIDO_NO_BALCAO"


def test_a_tela_mostra_o_passo_do_proprietario(casa):
    mid = _ficha_acervo(casa, "4205")
    html = casa["oficial"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    assert "2. Proprietário que a certidão vai imprimir" in html
    assert 'name="proprietario_conferido"' in html  # sem IA nos testes: a caixa aparece
    assert 'data-url-andamento=' in html


# --------------------- acatar a leitura corrige o cadastro (15/10/2026)
#
# «sendo acatada a sugestao, sistema tbm retifique no cadastro da matricula
#  para constar o proprietario atual correto» — o oficial.

TEOR_DA_VENDA = (
    "<p>IMÓVEL: Uma gleba de terras com 10ha, destacada da matrícula 4300.</p>"
    "<p>R-01/4206 - COMPRA E VENDA. ASSOCIAÇÃO EXEMPLO vende o imóvel a MAGNO EXEMPLO "
    "PEREIRA, CPF nº 000.000.001-91, e MARIANA EXEMPLO DOS SANTOS.</p>")


def _ficha_com_dono_errado(casa, numero="4206"):
    con = sqlite3.connect(casa["banco"])
    cur = con.execute(
        """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao, tipo_ficha,
               origem, criado_em, data_abertura, cidade, uf, teor)
           VALUES (?, '2', '2', 'ATIVA', 'ACERVO', 'MANUAL', '2026-10-15T08:00',
                   '2010-01-01', 'Cidade Exemplo', 'MA', ?)""", (numero, TEOR_DA_VENDA))
    mid = int(cur.lastrowid)
    con.execute("""INSERT INTO ri_partes (matricula_id, nome, nome_norm, papel, proprietario,
                       proprietario_ativo, origem) VALUES (?, 'MANOEL EXEMPLO BARROS',
                       'manoel exemplo barros', 'proprietario', 1, 1, 'EOFICIO')""", (mid,))
    con.commit()
    con.close()
    return mid


def _leitura_gravada(casa, mid, donos):
    con = sqlite3.connect(casa["banco"])
    RONIA.init_schema(con)
    r = {"onus": "NEGATIVA", "acoes": "NEGATIVA", "itens": [], "cancelados": [],
         "proprietarios": donos, "proprietarios_ato": "R-01/4206",
         "proprietarios_trecho": "vende o imóvel a MAGNO", "proprietarios_literal": True,
         "parecer": ""}
    con.execute("""INSERT INTO ri_onus_sugestoes (matricula_id, hash_ficha, dossie, situacao,
                       pedido_em, resultado_json) VALUES (?,?,?, 'PRONTA', ?, ?)""",
                (mid, RONIA.hash_da_ficha(con, mid), "x", "2026-10-15T08:00:00",
                 json.dumps(r, ensure_ascii=False)))
    con.commit()
    con.close()


def _acatar(casa, mid):
    c = casa["oficial"]
    tela = c.get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    return c.post(f"/registro-imoveis/{mid}/onus/acatar-proprietario",
                  data={"csrf_token": _token(tela)}, follow_redirects=True)


def _titulares(casa, mid):
    con = sqlite3.connect(casa["banco"])
    linhas = con.execute("""SELECT nome, documento_numero, proprietario_ativo, origem_chave
                              FROM ri_partes WHERE matricula_id=? ORDER BY id""",
                         (mid,)).fetchall()
    con.close()
    return linhas


def test_acatar_corrige_o_cadastro_e_guarda_o_historico(casa):
    mid = _ficha_com_dono_errado(casa)
    _leitura_gravada(casa, mid, [{"nome": "MAGNO EXEMPLO PEREIRA", "documento": "00000000191"},
                                 {"nome": "MARIANA EXEMPLO DOS SANTOS", "documento": ""}])
    tela = casa["oficial"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    assert "Acatar a leitura e corrigir o cadastro" in tela
    r = _acatar(casa, mid)
    assert "Cadastro da matrícula corrigido" in r.get_data(as_text=True)
    linhas = {n: (doc, ativo, chave) for n, doc, ativo, chave in _titulares(casa, mid)}
    assert linhas["MANOEL EXEMPLO BARROS"][1] == 0          # fica, como histórico
    assert linhas["MAGNO EXEMPLO PEREIRA"][:2] == ("00000000191", 1)
    assert linhas["MARIANA EXEMPLO DOS SANTOS"][:2] == (None, 1)
    assert linhas["MAGNO EXEMPLO PEREIRA"][2].startswith("ia_onus_acatada:")
    depois = casa["oficial"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    assert "Confere" in depois
    con = sqlite3.connect(casa["banco"])
    n = con.execute("""SELECT COUNT(*) FROM audit_logs WHERE action IN
                       ('RI_PARTE_CORRIGIDA','RI_PARTE_INCLUIDA')
                       AND details LIKE '%leitura da IA acatada%'""").fetchone()[0]
    con.close()
    assert n == 3


def test_acatar_recusa_nome_que_nao_esta_na_ficha(casa):
    mid = _ficha_com_dono_errado(casa, "4207")
    _leitura_gravada(casa, mid, [{"nome": "FULANO INVENTADO", "documento": ""}])
    r = _acatar(casa, mid)
    assert "não está escrito" in r.get_data(as_text=True)
    assert [a for _n, _d, a, _c in _titulares(casa, mid)] == [1]   # nada mudou


def test_acatar_nao_poe_cpf_que_a_ficha_nao_escreve(casa):
    mid = _ficha_com_dono_errado(casa, "4208")
    _leitura_gravada(casa, mid, [{"nome": "MARIANA EXEMPLO DOS SANTOS",
                                  "documento": "00000000272"}])
    _acatar(casa, mid)
    linhas = {n: doc for n, doc, _a, _c in _titulares(casa, mid)}
    assert linhas["MARIANA EXEMPLO DOS SANTOS"] is None


def test_leitura_sem_dono_volta_para_a_caixa_e_nao_acusa_o_cadastro():
    """Leitura antiga, ou que não achou o dono: sem o lado da IA não há o que
    comparar — a conferência volta para quem emite, e não diz «não confere»."""
    r = RONIA.conferir_proprietarios(
        [{"nome": "MARIO DA SILVA", "documento_numero": ""}],
        {"situacao": "PRONTA", "vale": True, "proprietarios": []})
    assert r["situacao"] == RONIA.SEM_LEITURA
    assert r["ia_sem_dono"] is True


def test_a_ia_so_le_quando_alguem_clica():
    """«a IA so vai ler se clicar no botao na emissao de certidao de onus. para
    cada matricula» — o oficial, 15/10/2026. A tela não pede leitura sozinha."""
    # O quadro da decisão mora em `_onus_decisao.html` desde 26/10/2026 (a ficha
    # e o pedido do ONR no automático o incluem): a tela é a ficha com ele.
    modelos = Path(__file__).resolve().parent.parent / "templates"
    tela = (modelos / "ri_ficha.html").read_text(encoding="utf-8")
    assert "{% include '_onus_decisao.html' %}" in tela
    tela += (modelos / "_onus_decisao.html").read_text(encoding="utf-8")
    assert "Pedir a leitura à IA" in tela
    assert "pela_tela" not in tela and "lerSozinha" not in tela and "ler_sozinha" not in tela
    fonte = (Path(__file__).resolve().parent.parent / "ri_onus_ia.py").read_text(encoding="utf-8")
    assert "ler_sozinha" not in fonte
