"""
O ATO DE ORIGEM na lista de atenção para fraudes — 24/11/2026.

O CASO
    Uma circular de outro estado suspendeu procurações identificadas SÓ por
    serventia, livro, folha e ordem, sem o nome das partes. A lista só sabia
    procurar pessoa: nada entrou, o expediente foi arquivado como ciência, e o
    traslado podia aparecer no balcão sem aviso nenhum.

O QUE ESTES TESTES CONFEREM
    - que o ato entra com a MESMA régua de procedência da pessoa, e sai da
      lista do mesmo jeito (inativar com motivo);
    - que bate pelo LIVRO e pela FOLHA (ou ordem), e que a força do achado diz
      se a serventia bateu junto — livro 10, folha 20 existe em todo cartório;
    - que serventia diferente (CNS, cidade ou UF) NÃO bate;
    - que o alerta aparece onde a procuração de terceiro é informada: na ficha
      do ato das Notas e na prenotação do RI;
    - que o malote leva o aviso SEM pessoa e COM ato à lista, e o aviso sem
      pessoa e sem ato continua expediente («só ciência»).

Todos os dados são fictícios.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import fraude as FR  # noqa: E402
import malote_fraudes as MF  # noqa: E402
from fr_schema import init_fr_schema  # noqa: E402
from nucleo_schema import init_nucleo_schema  # noqa: E402
from pt_schema import init_pt_schema  # noqa: E402

AGORA = "2026-11-24T10:00:00"
SERVENTIA = "1º Tabelionato de Notas de Cidade Exemplo"


@pytest.fixture()
def con():
    c = conexao_de_teste()
    c.row_factory = sqlite3.Row
    init_nucleo_schema(c)
    init_pt_schema(c)
    init_fr_schema(c)
    yield c
    c.close()


def incluir_ato(con, **kw):
    kw.setdefault("origem", "Circular 99/2026, recebida pelo malote")
    kw.setdefault("agora", AGORA)
    kw.setdefault("natureza", "Procuração")
    kw.setdefault("serventia", SERVENTIA)
    kw.setdefault("cidade", "Cidade Exemplo")
    kw.setdefault("uf", "XX")
    kw.setdefault("cns", "99.999-9")
    kw.setdefault("livro", "0120")
    kw.setdefault("folha", "45/46")
    kw.setdefault("ordem", "3")
    return FR.incluir_ato(con, **kw)


# ------------------------------------------------------------------ incluir


def test_o_ato_entra_com_procedencia_e_formas_normalizadas(con):
    r = incluir_ato(con, origem_orgao="Corregedoria Exemplo", origem_data="2026-11-20",
                    observacao="procurações suspensas por indício de falsidade")
    a = FR.ler(con, r["alerta_id"])
    assert a["papel"] == "ATO" and a["situacao"] == "ATIVO"
    # nome e documento ficam vazios: não há pessoa para procurar
    assert a["nome"] is None and a["documento"] is None
    assert a["ato_livro"] == "0120" and a["ato_livro_norm"] == "120"
    assert a["ato_folhas_norm"] == "|45|46|"
    assert a["ato_cns"] == "999999" and a["ato_ordem_norm"] == "3"
    assert a["ato_cidade_norm"] == "cidade exemplo"
    assert a["origem_orgao"] == "Corregedoria Exemplo"
    assert "livro 0120" in r["descricao"] and "Cidade Exemplo" in r["descricao"]


@pytest.mark.parametrize("falta, frase", [
    ({"origem": "  "}, "de onde veio a comunicação"),
    ({"livro": ""}, "Informe o livro"),
    ({"folha": None, "ordem": None}, "a folha ou o número de ordem"),
    ({"serventia": None, "cidade": None, "cns": None}, "de que serventia"),
])
def test_ato_que_nao_identifica_ou_sem_procedencia_nao_entra(con, falta, frase):
    with pytest.raises(FR.FraudeError) as erro:
        incluir_ato(con, **falta)
    assert frase in str(erro.value)


def test_o_papel_de_ato_nao_entra_pela_porta_da_pessoa(con):
    # `incluir` é da pessoa: o papel de ato não está nos papéis dela
    assert "ATO" not in FR.PAPEIS
    with pytest.raises(FR.FraudeError):
        FR.incluir(con, papel="ATO", origem="Circular", agora=AGORA, nome="X Y")


# ------------------------------------------------------- conferir em campos


def test_cns_livro_e_folha_batem_com_certeza(con):
    incluir_ato(con)
    achados = FR.conferir_ato(con, cns="999999", livro="120", folha="46")
    assert len(achados) == 1
    assert achados[0]["forca"] == "SERVENTIA" and "CNS" in achados[0]["por_que"]
    assert achados[0]["papel_rotulo"] == "Ato suspenso ou fraudado"


def test_a_cidade_bate_mas_avisa_que_pode_ser_outra_serventia(con):
    incluir_ato(con)
    achados = FR.conferir_ato(con, cidade="CIDADE EXEMPLO", livro="Livro 120", folha="45v")
    assert [a["forca"] for a in achados] == ["CIDADE"]


def test_sem_nada_da_serventia_bate_fraco(con):
    incluir_ato(con)
    achados = FR.conferir_ato(con, livro="120", folha="45")
    assert [a["forca"] for a in achados] == ["LIVRO_FOLHA"]


def test_a_ordem_bate_sem_a_folha(con):
    incluir_ato(con)
    assert FR.conferir_ato(con, livro="120", ordem="003", cns="999999")


@pytest.mark.parametrize("outro", [
    {"cns": "999998"}, {"cidade": "Outra Cidade"}, {"uf": "YY"},
])
def test_serventia_diferente_nao_bate(con, outro):
    incluir_ato(con)
    assert FR.conferir_ato(con, livro="120", folha="45", **outro) == []


def test_outra_folha_ou_outro_livro_nao_batem(con):
    incluir_ato(con)
    assert FR.conferir_ato(con, cns="999999", livro="120", folha="47") == []
    assert FR.conferir_ato(con, cns="999999", livro="121", folha="45") == []
    # só o livro não basta: acenderia o alerta para o livro inteiro
    assert FR.conferir_ato(con, cns="999999", livro="120") == []


def test_inativado_com_motivo_deixa_de_bater_e_reativado_volta(con):
    r = incluir_ato(con)
    with pytest.raises(FR.FraudeError):
        FR.inativar(con, r["alerta_id"], motivo="curto", agora=AGORA)
    FR.inativar(con, r["alerta_id"], motivo="a suspensão foi revogada pela circular 100/2026",
                agora=AGORA, usuario="tabeliao")
    assert FR.conferir_ato(con, cns="999999", livro="120", folha="45") == []
    FR.reativar(con, r["alerta_id"], agora=AGORA)
    assert FR.conferir_ato(con, cns="999999", livro="120", folha="45")


def test_o_alerta_de_ato_nao_aparece_na_conferencia_de_pessoa(con):
    incluir_ato(con)
    FR.incluir(con, papel="VITIMA", origem="Ofício 1/2026", agora=AGORA, nome="Maria Exemplo")
    assert [a["papel"] for a in FR.conferir(con, nome="maria exemplo")] == ["VITIMA"]
    assert [a["papel"] for a in FR.conferir_ato(con, livro="120", folha="45")] == ["ATO"]


# -------------------------------------------------------- conferir no texto


def test_o_texto_do_instrumento_com_a_serventia_bate_forte(con):
    incluir_ato(con)
    texto = (f"procuração lavrada no {SERVENTIA}/XX, Livro nº 120, fls. 45/46, "
             "em 10/03/2026")
    achados = FR.conferir_ato_no_texto(con, texto)
    assert [a["forca"] for a in achados] == ["SERVENTIA"]
    assert achados[0]["conferido_nome"].startswith("procuração lavrada")


def test_o_texto_so_com_a_cidade_bate_pela_cidade(con):
    incluir_ato(con)
    achados = FR.conferir_ato_no_texto(
        con, "procuração do Cartório do 2º Ofício de Cidade Exemplo, livro 120 a fls. 45")
    assert [a["forca"] for a in achados] == ["CIDADE"]


def test_o_texto_sem_a_serventia_bate_fraco_e_o_cns_com_ponto_conta(con):
    incluir_ato(con)
    assert [a["forca"] for a in FR.conferir_ato_no_texto(con, "livro 120, folha 45")] == ["LIVRO_FOLHA"]
    assert [a["forca"] for a in FR.conferir_ato_no_texto(
        con, "CNS 99.999-9, livro 120, folha 46")] == ["SERVENTIA"]


def test_texto_sem_livro_ou_sem_folha_nao_bate(con):
    incluir_ato(con)
    assert FR.conferir_ato_no_texto(con, "procuração de Cidade Exemplo, folha 45") == []
    assert FR.conferir_ato_no_texto(con, "procuração de Cidade Exemplo, livro 120") == []
    assert FR.conferir_ato_no_texto(con, "", None) == []


def test_as_notas_conferem_o_instrumento_e_o_ato_anterior(con):
    incluir_ato(con)
    partes = [
        {"id": 1, "nome": "OUTORGANTE EXEMPLO", "representacoes": []},
        {"id": 2, "nome": "PROCURADOR EXEMPLO", "representacoes": [
            {"representado_parte_id": 1,
             "instrumento": "procuração do 1º Tabelionato de Notas de Cidade Exemplo, "
                            "livro 120, fls. 45"}]},
    ]
    achados = FR.atos_citados_no_ato_de_notas(con, {}, partes)
    assert len(achados) == 1
    assert achados[0]["papel_no_ato"] == "instrumento de PROCURADOR EXEMPLO"
    # o ato anterior em campos (substabelecimento, revogação) — e um alerta só uma vez
    anterior = {"anterior_livro": "120", "anterior_folha": "45", "anterior_cns": "999999"}
    achados = FR.atos_citados_no_ato_de_notas(con, anterior, partes)
    assert len(achados) == 1 and achados[0]["papel_no_ato"] == "ato anterior citado"


def test_a_prenotacao_confere_a_procuracao_citada_e_os_textos(con):
    incluir_ato(con)
    assert FR.atos_citados_na_prenotacao(con, {
        "procuracao_citada": "Cidade Exemplo/XX, livro 120, folha 45"})
    assert FR.atos_citados_na_prenotacao(con, {
        "documento_descricao": "escritura com procuração do livro 120, fls. 46, CNS 999999"})
    assert FR.atos_citados_na_prenotacao(con, {"objeto": "compra e venda"}) == []


# ------------------------------------------------------------- a lista


def test_a_lista_procura_o_ato_pela_cidade_e_descreve(con):
    incluir_ato(con)
    linhas = FR.listar(con, busca="cidade exemplo")
    assert len(linhas) == 1 and linhas[0]["papel_rotulo"] == "Ato suspenso ou fraudado"
    assert "livro 0120" in linhas[0]["ato_descricao"]
    assert FR.contagem(con)["por_papel"] == {"ATO": 1}


def test_a_conferencia_do_ato_deixa_o_rastro(con):
    r = incluir_ato(con)
    FR.registrar_conferencia(con, r["alerta_id"], decisao="RECUSOU", agora=AGORA,
                             onde="Notas — ficha do ato", nome="livro 120, fls. 45")
    rastro = FR.conferencias(con, alerta_id=r["alerta_id"])
    assert rastro[0]["decisao"] == "RECUSOU" and rastro[0]["nome_conferido"] == "livro 120, fls. 45"


# ================================================================= as telas

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def s(cg_casa):
    cg_casa["db"].create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c = cg_casa["app"].test_client()
    c.post("/login", data={"username": "tabeliao", "password": SENHA,
                           "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {"c": c, "banco": cg_casa["banco"], "db": cg_casa["db"]}


def incluir_ato_pela_tela(s, **extra):
    tela = s["c"].get("/fraudes").get_data(as_text=True)
    dados = {"csrf_token": _token(tela), "origem": "Circular 99/2026, recebida pelo malote",
             "origem_orgao": "Corregedoria Exemplo", "ato_natureza": "Procuração",
             "ato_serventia": SERVENTIA, "ato_cidade": "Cidade Exemplo", "ato_uf": "XX",
             "ato_cns": "999999", "ato_livro": "120", "ato_folha": "45", "ato_ordem": "3"}
    dados.update(extra)
    return s["c"].post("/fraudes/incluir-ato", data=dados, follow_redirects=True)


def test_a_tela_inclui_o_ato_e_o_mostra_na_lista(s):
    html = incluir_ato_pela_tela(s).get_data(as_text=True)
    assert "entrou na lista de atenção" in html
    assert "Incluir um ato suspenso ou fraudado" in html
    assert "Procuração — 1º Tabelionato de Notas de Cidade Exemplo" in html
    assert "Ato suspenso ou fraudado" in html


def test_a_tela_sem_procedencia_avisa_e_nao_grava(s):
    html = incluir_ato_pela_tela(s, origem="").get_data(as_text=True)
    assert "de onde veio a comunicação" in html
    with sqlite3.connect(s["banco"]) as con:
        assert con.execute("SELECT count(*) FROM fr_alertas").fetchone()[0] == 0


def test_a_consulta_do_balcao_acha_o_ato(s):
    incluir_ato_pela_tela(s)
    html = s["c"].get("/fraudes/consultar?ato_cns=999999&ato_livro=120&ato_folha=45"
                      ).get_data(as_text=True)
    assert "Atenção para fraudes — Ato suspenso ou fraudado" in html
    assert "Registrar a conferência" in html
    nada = s["c"].get("/fraudes/consultar?ato_livro=7&ato_folha=1").get_data(as_text=True)
    assert "Nada na lista de atenção" in nada


def test_a_escritura_com_procuracao_de_outra_serventia_mostra_o_alerta(s):
    from database import Database
    from pt_schema import normalizar_nome
    incluir_ato_pela_tela(s)
    db = Database(s["banco"])
    agora = db.now()
    with db.transaction() as con:
        aid = int(con.execute(
            """INSERT INTO nt_atos(tipo, data, situacao, criado_em)
               VALUES ('ESCRITURA', ?, 'EM_LAVRATURA', ?)""", (agora[:10], agora)).lastrowid)
        outorgante = int(con.execute(
            """INSERT INTO nt_ato_partes(ato_id, nome, nome_norm, qualificacao, criado_em)
               VALUES (?,?,?,?,?)""",
            (aid, "OUTORGANTE EXEMPLO", normalizar_nome("OUTORGANTE EXEMPLO"), "outorgante",
             agora)).lastrowid)
        con.execute(
            """INSERT INTO nt_ato_partes(ato_id, nome, nome_norm, qualificacao, criado_em,
                   representa_parte_id, representa_instrumento)
               VALUES (?,?,?,?,?,?,?)""",
            (aid, "PROCURADOR EXEMPLO", normalizar_nome("PROCURADOR EXEMPLO"), "procurador",
             agora, outorgante,
             "procuração lavrada no 1º Tabelionato de Notas de Cidade Exemplo, livro 120, fls. 45"))
    html = s["c"].get(f"/notas/atos/{aid}").get_data(as_text=True)
    assert "Atenção para fraudes — Ato suspenso ou fraudado" in html
    assert "instrumento de PROCURADOR EXEMPLO" in html
    assert "o nome da serventia, o livro e a folha" in html


def test_a_prenotacao_que_cita_a_procuracao_mostra_o_alerta(s):
    from database import Database
    incluir_ato_pela_tela(s)
    # o campo novo está no formulário da prenotação
    assert 'name="procuracao_citada"' in s["c"].get("/registro-imoveis/protocolo").get_data(as_text=True)
    db = Database(s["banco"])
    agora = db.now()
    with db.transaction() as con:
        pid = int(con.execute(
            """INSERT INTO ri_protocolos(numero, livro, data_prenotacao, situacao, origem,
                   criado_em, natureza_titulo, procuracao_citada)
               VALUES (9001, '1A', ?, 'ABERTO', 'MANUAL', ?, 'Compra e venda', ?)""",
            (agora[:10], agora, "CNS 999999, livro 120, folha 45")).lastrowid)
    html = s["c"].get(f"/registro-imoveis/protocolo/{pid}").get_data(as_text=True)
    assert "Atenção para fraudes — Ato suspenso ou fraudado" in html
    assert "ato citado no título" in html
    # e o campo se corrige na ficha, como os outros
    assert "Procuração citada (de outra serventia)" in html


# ================================================================= o malote

TEXTO_DA_CIRCULAR = (
    "CIRCULAR Nº 99/2026 — Corregedoria Exemplo. Comunica às serventias a SUSPENSÃO dos "
    "efeitos das procurações públicas lavradas no 1º Tabelionato de Notas de Cidade Exemplo/XX, "
    "CNS 99.999-9: livro 120, folhas 45/46, ordem 3, e livro 121, folha 10, ordem 7, por "
    "indício de falsidade das assinaturas. As serventias devem abster-se de praticar atos com "
    "base nesses instrumentos e comunicar qualquer apresentação a esta Corregedoria. ")

ATO_1 = {"natureza": "Procuração", "serventia": SERVENTIA, "cns": "99.999-9",
         "cidade": "Cidade Exemplo", "uf": "XX", "livro": "120", "folha": "45/46", "ordem": "3",
         "trecho": "livro 120, folhas 45/46, ordem 3"}
ATO_2 = dict(ATO_1, livro="121", folha="10", ordem="7", trecho="livro 121, folha 10, ordem 7")


def _ia(atos, pessoas=(), aviso=True):
    def conversar(pasta, *, provedor, sistema, conversa, ferramentas, modelo, maximo_de_saida,
                  **_registro):
        assert '"atos"' in sistema, "a instrução não pede os atos"
        return {"texto": json.dumps({"aviso_de_fraude": aviso, "resumo": "Procurações suspensas.",
                                     "processos": ["0099/2026"], "pessoas": list(pessoas),
                                     "atos": list(atos)}),
                "modelo": "claude-sonnet-5", "entrada": 100, "saida": 50, "provedor": "claude"}
    return conversar


def test_a_porta_da_ia_abre_para_a_suspensao_de_procuracao_e_nao_para_a_de_prazo():
    assert MF.parece_fraude("Ficam suspensas as procurações lavradas no livro 120")
    assert MF.parece_fraude("", "Suspensão dos efeitos de procuração pública")
    assert not MF.parece_fraude("Suspensão do expediente forense no dia 20")
    assert not MF.parece_fraude("Suspensão dos prazos processuais")


def test_o_ato_que_nao_esta_no_texto_do_pdf_nao_entra(tmp_path):
    inventado = dict(ATO_1, livro="555")
    sem_serventia = dict(ATO_1, serventia="Outro Cartório Qualquer", cidade="Outra Cidade", cns="")
    r = MF.ler_aviso(tmp_path, TEXTO_DA_CIRCULAR,
                     conversar=_ia([ATO_1, inventado, sem_serventia, dict(ATO_1, folha="", ordem="")]),
                     provedor="claude")
    assert [a["ato_livro"] for a in r["atos"]] == ["120"]
    assert any("o livro não está no texto" in f for f in r["fora"])
    assert any("a serventia e a cidade não estão no texto" in f for f in r["fora"])
    assert any("sem a folha nem o número de ordem" in f for f in r["fora"])


def _grupo(tmp_path, nome="Circular suspensao de procuracoes.pdf"):
    import malote_agente as MA
    entrada = tmp_path / "entrada"
    entrada.mkdir(exist_ok=True)
    (entrada / nome).write_bytes(b"%PDF-1.4\n% x\n%%EOF\n")
    return MA.varrer([entrada])[0]


@pytest.fixture()
def con_casa(cg_casa):
    c = sqlite3.connect(cg_casa["banco"])
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def test_aviso_sem_pessoa_com_ato_vira_alerta_de_ato_e_nao_expediente(con_casa, cg_casa, tmp_path,
                                                                    monkeypatch):
    import agente_provedores as AP
    import malote_agente as MA
    monkeypatch.setattr(AP, "tem_chave", lambda pasta, provedor=None: True)
    MA.init_schema(con_casa)
    r = MF.tratar_grupo(con_casa, _grupo(tmp_path), cg_casa["dados"], tmp_path / "arquivos", "mario",
                        conversar=_ia([ATO_1, ATO_2]), agora=AGORA,
                        ler_texto=lambda arquivos: TEXTO_DA_CIRCULAR)
    assert r["caminho"] == "FRAUDE" and len(r["incluidos"]) == 2
    assert "0 pessoa(s) e 2 ato(s) de outra serventia" in r["nota"]
    alertas = con_casa.execute("SELECT * FROM fr_alertas ORDER BY id").fetchall()
    assert [a["papel"] for a in alertas] == ["ATO", "ATO"]
    assert [a["ato_livro_norm"] for a in alertas] == ["120", "121"]
    # a referência inteira do aviso vai junto, e a marca de que a IA pôs
    assert alertas[0]["origem"].startswith("Malote Digital")
    assert alertas[0]["observacao"].startswith(MF.MARCA_DA_IA)
    # o traslado que aparecer no balcão acende o alerta
    assert FR.conferir_ato(con_casa, cns="999999", livro="121", folha="10")
    # a lista diária do oficial mostra o ato pela descrição, e não como «?»
    entradas = MF.entradas_pela_ia(con_casa, "2026-11-24")
    assert len(entradas) == 2 and entradas[0]["nome"].startswith("Procuração — ")
    # o mesmo aviso lido de novo não dobra o alerta
    r2 = MF.tratar_grupo(con_casa, _grupo(tmp_path), cg_casa["dados"], tmp_path / "arquivos", "mario",
                         conversar=_ia([ATO_1]), agora="2026-11-24T11:00:00",
                         ler_texto=lambda arquivos: TEXTO_DA_CIRCULAR)
    assert r2["caminho"] == "FRAUDE" and len(r2["ja_havia"]) == 1 and not r2["incluidos"]
    assert con_casa.execute("SELECT count(*) FROM fr_alertas").fetchone()[0] == 2


def test_aviso_sem_pessoa_e_sem_ato_continua_expediente(con_casa, cg_casa, tmp_path, monkeypatch):
    import agente_provedores as AP
    import malote_agente as MA
    monkeypatch.setattr(AP, "tem_chave", lambda pasta, provedor=None: True)
    MA.init_schema(con_casa)
    r = MF.tratar_grupo(con_casa, _grupo(tmp_path), cg_casa["dados"], tmp_path / "arquivos", "mario",
                        conversar=_ia([]), agora=AGORA,
                        ler_texto=lambda arquivos: TEXTO_DA_CIRCULAR)
    assert r["caminho"] == "EXPEDIENTE" and "nem ato identificado" in r["motivo"]
    assert con_casa.execute("SELECT count(*) FROM fr_alertas").fetchone()[0] == 0


def test_a_proposta_de_ato_pela_revisao_do_oficial(con_casa):
    base = {"codigo_malote": "00000000000099", "documento_malote": "CIRCULAR-99.pdf",
            "assunto": "Suspensão de procurações", "remetente": "Corregedoria Exemplo",
            "enviado_em": "2026-11-24 09:00:00", "papel": "ATO"}
    ato = {f"ato_{k}": v for k, v in ATO_1.items() if k != "trecho"}
    with pytest.raises(MF.PropostaError, match="não identifica"):
        MF.carregar(con_casa, [dict(base, ato_livro="120")])
    assert MF.carregar(con_casa, [dict(base, **ato), dict(base, **ato)]) == {"novas": 1, "repetidas": 1}
    linha = con_casa.execute("SELECT * FROM mt_alertas_propostos").fetchone()
    assert linha["nome"].startswith("Procuração — ") and linha["ato_livro"] == "120"
    assert "ato de outra serventia" in MF.pagina_de_revisao([dict(linha)])
    MF.revisar(con_casa, [linha["id"]], aprovar=True, revisor="mario")
    assert MF.aplicar(con_casa, usuario="mario") == {"incluidos": 1, "ja_havia": 0}
    a = con_casa.execute("SELECT * FROM fr_alertas").fetchone()
    assert a["papel"] == "ATO" and a["origem"].startswith("Malote Digital nº 00000000000099")
    assert not (a["observacao"] or "").startswith(MF.MARCA_DA_IA)
