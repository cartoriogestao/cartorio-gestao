"""A ABERTURA DE MATRÍCULA COM VÁRIOS PROPRIETÁRIOS — T022, 26/11/2026.

O PEDIDO, do balcão do Registro de Imóveis: incluir mais proprietários na
abertura. Na «Nova matrícula» o passo «Proprietário» cabia um dono só, e a
ficha só deixava cadastrar o dono da abertura quando não havia nenhum: não
existia caminho para o segundo.

O QUE ESTES TESTES GUARDAM
  1. Um dono só continua exatamente como era: as mesmas colunas e a mesma
     `origem_chave`. É o caso de quase toda abertura.
  2. Vários donos entram de uma vez, na mesma transação da matrícula, cada um
     com a sua fração conferida por `fracao_escrita`.
  3. O que se recusa, recusa ANTES de gravar e devolve a tela preenchida:
     fração que não se lê, bloco sem nome, documento repetido.
  4. A soma das frações não impede a abertura: avisa, como a ficha.
  5. A ficha acrescenta dono até o selo da abertura, e não depois.
  6. O selo da abertura leva todos os donos ao aparelho.

DADOS: só os fictícios da casa (`fixtures/anti_vazamento/documentos_ficticios.txt`).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from bd_nativo import banco  # noqa: E402

CPF_1, CPF_2, CPF_3 = "000.000.001-91", "000.000.002-72", "000.000.003-53"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _ler(db, sql: str, params=()) -> list[dict]:
    with db.connect() as con:
        return [dict(r) for r in banco(con).ler(sql, params)]


def _numeracao(db, proximo: int | None = None) -> None:
    from ri_schema import PRIMEIRA_MATRICULA_DO_SISTEMA as PRIMEIRA
    proximo = proximo or PRIMEIRA
    with db.transaction() as con:
        bd = banco(con)
        if not bd.um("SELECT 1 AS um FROM ri_numeracao WHERE livro=%s", ("2",)):
            bd.escrever("""INSERT INTO ri_numeracao(livro, proximo_numero, maior_em_uso, fixado_em)
                           VALUES (%s,%s,%s,'2026-11-26')""", ("2", proximo, proximo - 1))


def _matriculas(db) -> int:
    return int(_ler(db, "SELECT COUNT(*) AS n FROM ri_matriculas")[0]["n"])


def _abrir(s, **donos):
    """«Nova matrícula» pela tela. Os campos do proprietário podem vir em lista."""
    _numeracao(s["db"])
    html = s["c"].get("/registro-imoveis/nova").get_data(as_text=True)
    r = s["c"].post("/registro-imoveis/nova", data={
        "csrf_token": _token(html), "rural_urbano": "U", "logradouro": "Rua Exemplo",
        "cidade": "Cidade Exemplo", "uf": "MA", "area_unidade": "m2", **donos},
        follow_redirects=True)
    return r.get_data(as_text=True)


def _ultima(db) -> dict:
    return _ler(db, "SELECT * FROM ri_matriculas ORDER BY id DESC LIMIT 1")[0]


def _donos(db, mid: int) -> list[dict]:
    return _ler(db, "SELECT * FROM ri_partes WHERE matricula_id=%s ORDER BY id", (mid,))


def _auditoria(db, acao: str, mid: int) -> list[dict]:
    linhas = _ler(db, "SELECT details FROM audit_logs WHERE action=%s AND entity_id=%s ORDER BY id",
                  (acao, mid))
    return [json.loads(x["details"]) if isinstance(x["details"], str) else x["details"] for x in linhas]


def _texto(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


# ------------------------------------------------------- a «Nova matrícula»


def test_um_dono_so_grava_como_sempre(cg_casa_logada):
    s = cg_casa_logada
    pagina = _abrir(s, proprietario_nome="Pedro Exemplo dos Santos",
                    proprietario_documento=CPF_1,
                    proprietario_qualificacao="brasileiro, solteiro, comerciante")
    m = _ultima(s["db"])
    assert "aberta no livro" in pagina
    (p,) = _donos(s["db"], m["id"])
    assert p["ato_id"] is None and p["origem_chave"] == "abertura_nova_matricula"
    assert (p["nome"], p["documento_tipo"], p["documento_numero"], p["documento_valido"]) == (
        "Pedro Exemplo dos Santos", "CPF", "00000000191", 1)
    assert (p["papel"], p["proprietario"], p["proprietario_ativo"], p["origem"]) == (
        "proprietario", 1, 1, "MANUAL")
    assert p["qualificacao"] == "brasileiro, solteiro, comerciante"
    assert p["fracao"] is None
    assert "somam" not in pagina and "têm a fração informada" not in pagina
    (aberta,) = _auditoria(s["db"], "RI_MATRICULA_ABERTA", m["id"])
    assert aberta["proprietarios"] == 1
    assert len(_auditoria(s["db"], "RI_PARTE_ABERTURA_INCLUIDA", m["id"])) == 1


def test_tres_donos_com_as_fracoes_escritas(cg_casa_logada):
    s = cg_casa_logada
    pagina = _abrir(s, proprietario_nome=["Pedro Exemplo", "Beatriz Exemplo", "Carla Exemplo"],
                    proprietario_documento=[CPF_1, CPF_2, CPF_3],
                    proprietario_qualificacao=["", "casada", ""],
                    proprietario_fracao=["50", "25 %", "1 / 4"])
    m = _ultima(s["db"])
    donos = _donos(s["db"], m["id"])
    assert [d["nome"] for d in donos] == ["Pedro Exemplo", "Beatriz Exemplo", "Carla Exemplo"]
    assert [d["fracao"] for d in donos] == ["50%", "25%", "1/4"]
    assert all(d["ato_id"] is None and d["origem_chave"] == "abertura_nova_matricula" for d in donos)
    assert [d["qualificacao"] for d in donos] == [None, "casada", None]
    assert "somam" not in pagina and "têm a fração informada" not in pagina
    (aberta,) = _auditoria(s["db"], "RI_MATRICULA_ABERTA", m["id"])
    assert aberta["proprietarios"] == 3
    incluidos = _auditoria(s["db"], "RI_PARTE_ABERTURA_INCLUIDA", m["id"])
    assert [x["nome"] for x in incluidos] == ["Pedro Exemplo", "Beatriz Exemplo", "Carla Exemplo"]


def test_bloco_em_branco_e_ignorado(cg_casa_logada):
    s = cg_casa_logada
    _abrir(s, proprietario_nome=["Pedro Exemplo", "", " "],
           proprietario_documento=[CPF_1, "", ""], proprietario_fracao=["", "", ""])
    assert [d["nome"] for d in _donos(s["db"], _ultima(s["db"])["id"])] == ["Pedro Exemplo"]


def test_fracoes_que_somam_90_abrem_com_o_aviso(cg_casa_logada):
    s = cg_casa_logada
    pagina = _abrir(s, proprietario_nome=["Pedro Exemplo", "Beatriz Exemplo"],
                    proprietario_documento=[CPF_1, CPF_2], proprietario_fracao=["40%", "50%"])
    assert "aberta no livro" in pagina
    assert "As frações dos titulares somam 90,00%, e não 100%" in pagina
    assert len(_donos(s["db"], _ultima(s["db"])["id"])) == 2


def test_fracao_ilegivel_nao_grava_nada_e_a_tela_volta_preenchida(cg_casa_logada):
    s = cg_casa_logada
    _numeracao(s["db"])
    antes = _matriculas(s["db"])
    pagina = _abrir(s, proprietario_nome=["Pedro Exemplo", "Beatriz Exemplo"],
                    proprietario_documento=[CPF_1, CPF_2], proprietario_fracao=["50%", "metade"])
    assert _matriculas(s["db"]) == antes
    assert _ler(s["db"], "SELECT COUNT(*) AS n FROM ri_partes")[0]["n"] == 0
    assert "2º proprietário (Beatriz Exemplo)" in pagina and "não é fração do imóvel" in pagina
    for valor in ("Pedro Exemplo", "Beatriz Exemplo", CPF_2, "metade", "Rua Exemplo"):
        assert f'value="{valor}"' in pagina, valor
    # o segundo bloco volta como bloco, com o «Remover», e o primeiro não
    assert pagina.count("data-parte data-dono-primeiro>") == 1
    assert pagina.count("data-remover-parte hidden") == 2, "o do bloco que voltou e o do molde"


def test_bloco_com_cpf_e_sem_nome_e_recusado_dizendo_qual(cg_casa_logada):
    s = cg_casa_logada
    _numeracao(s["db"])
    antes = _matriculas(s["db"])
    pagina = _abrir(s, proprietario_nome=["Pedro Exemplo", ""],
                    proprietario_documento=[CPF_1, CPF_2])
    assert _matriculas(s["db"]) == antes
    assert "O 2º proprietário está sem nome, mas tem CPF ou CNPJ" in pagina


def test_o_mesmo_cpf_em_dois_blocos_e_recusado(cg_casa_logada):
    s = cg_casa_logada
    _numeracao(s["db"])
    antes = _matriculas(s["db"])
    pagina = _abrir(s, proprietario_nome=["Pedro Exemplo", "Beatriz Exemplo"],
                    proprietario_documento=[CPF_1, "00000000191"])
    assert _matriculas(s["db"]) == antes
    assert f"O documento {CPF_1} está no 1º e no 2º proprietário" in pagina


def test_a_tela_traz_o_molde_e_o_botao_de_acrescentar(cg_casa_logada):
    s = cg_casa_logada
    _numeracao(s["db"])
    html = s["c"].get("/registro-imoveis/nova").get_data(as_text=True)
    assert "+ Acrescentar proprietário</button>" in html
    assert "<template data-modelo-parte>" in html
    assert 'name="proprietario_fracao"' in html
    assert html.count("data-parte data-dono-primeiro>") == 1


def test_o_acervo_continua_sem_o_proprietario(cg_casa_logada):
    s = cg_casa_logada
    _numeracao(s["db"], proximo=4010)
    html = s["c"].get("/registro-imoveis/nova").get_data(as_text=True)
    assert "automaticamente como" in html and 'name="proprietario_nome"' not in html
    s["c"].post("/registro-imoveis/nova", data={
        "csrf_token": _token(html), "teor": "TEOR IMPORTADO", "cidade": "Cidade Exemplo", "uf": "MA",
        "proprietario_nome": ["Pedro Exemplo", ""], "proprietario_documento": ["", CPF_1]})
    m = _ultima(s["db"])
    assert m["numero"] == "4010" and m["tipo_ficha"] == "ACERVO"
    assert _donos(s["db"], m["id"]) == []


# ------------------------------------------------------- a ficha, até o selo


def _ficha(s, mid: int) -> str:
    return s["c"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)


def _incluir(s, mid: int, **campos) -> str:
    return s["c"].post(f"/registro-imoveis/{mid}/parte-abertura",
                       data={"csrf_token": _token(_ficha(s, mid)), **campos},
                       follow_redirects=True).get_data(as_text=True)


def test_ficha_com_um_dono_acrescenta_o_segundo_e_recusa_o_repetido(cg_casa_logada):
    s = cg_casa_logada
    _abrir(s, proprietario_nome="Pedro Exemplo", proprietario_documento=CPF_1,
           proprietario_fracao="50%")
    mid = _ultima(s["db"])["id"]
    ficha = _texto(_ficha(s, mid))
    assert "Acrescentar outro proprietário da abertura" in ficha
    assert "Cadastrar o proprietário da abertura" not in ficha
    assert "Pedro Exemplo — CPF 00000000191 — fração 50%" in ficha

    pagina = _incluir(s, mid, nome="Beatriz Exemplo", documento=CPF_2, fracao="50%")
    assert "Proprietário da abertura cadastrado: Beatriz Exemplo" in pagina
    assert "somam" not in pagina
    assert [d["nome"] for d in _donos(s["db"], mid)] == ["Pedro Exemplo", "Beatriz Exemplo"]
    incluidos = _auditoria(s["db"], "RI_PARTE_ABERTURA_INCLUIDA", mid)
    assert [x["nome"] for x in incluidos] == ["Pedro Exemplo", "Beatriz Exemplo"]

    pagina = _incluir(s, mid, nome="Outro Nome", documento="00000000272")
    assert f"O documento {CPF_2} já está na abertura, com Beatriz Exemplo" in pagina
    assert len(_donos(s["db"], mid)) == 2


def test_ficha_avisa_a_soma_depois_de_acrescentar(cg_casa_logada):
    s = cg_casa_logada
    _abrir(s, proprietario_nome="Pedro Exemplo", proprietario_documento=CPF_1,
           proprietario_fracao="50%")
    mid = _ultima(s["db"])["id"]
    pagina = _incluir(s, mid, nome="Beatriz Exemplo", documento=CPF_2, fracao="1/4")
    assert "As frações dos titulares somam 75,00%, e não 100%" in pagina


def test_ficha_sem_dono_continua_com_o_quadro_de_cadastrar(cg_casa_logada):
    s = cg_casa_logada
    _abrir(s)
    mid = _ultima(s["db"])["id"]
    ficha = _texto(_ficha(s, mid))
    assert "Cadastrar o proprietário da abertura" in ficha
    assert "Acrescentar outro proprietário" not in ficha


def test_ficha_selada_nao_mostra_o_quadro_e_a_rota_recusa(cg_casa_logada):
    s = cg_casa_logada
    _abrir(s, proprietario_nome="Pedro Exemplo", proprietario_documento=CPF_1)
    mid = _ultima(s["db"])["id"]
    with s["db"].transaction() as con:
        banco(con).escrever("UPDATE ri_matriculas SET selo_abertura_texto=%s WHERE id=%s",
                            ("Selo: MATRIC000000TESTE00000000001", mid))
    ficha = _ficha(s, mid)
    assert f"/registro-imoveis/{mid}/parte-abertura" not in ficha
    assert "Acrescentar outro proprietário" not in ficha
    pagina = _incluir(s, mid, nome="Beatriz Exemplo", documento=CPF_2)
    assert "já tem selo de abertura" in pagina
    assert len(_donos(s["db"], mid)) == 1


# ------------------------------------------------------- o selo da abertura


def test_o_selo_da_abertura_leva_os_tres_donos(cg_casa_logada):
    import ato_selado as AS
    from selador_de_bancada import ligar_o_selador

    s = cg_casa_logada
    nomes = ["Pedro Exemplo", "Beatriz Exemplo", "Carla Exemplo"]
    _abrir(s, proprietario_nome=nomes, proprietario_documento=[CPF_1, CPF_2, CPF_3],
           proprietario_fracao=["50%", "25%", "1/4"])
    mid = _ultima(s["db"])["id"]
    with ligar_o_selador(s) as aparelho:
        pagina = s["c"].post(f"/registro-imoveis/{mid}/selar-abertura",
                             data={"csrf_token": _token(_ficha(s, mid)), "codigo_tj": "16.2"},
                             follow_redirects=True).get_data(as_text=True)
        envelopes = [json.loads(p["corpo"]) for p in aparelho.pedidos
                     if p["caminho"].endswith(AS.CAMINHO_DA_ABERTURA)]
    assert envelopes, f"o selo da abertura não chegou ao aparelho: {_texto(pagina)[:600]}"
    partes = envelopes[-1]["dadosSelo"]["partes"]["parteAto"]
    assert [p["nome"] for p in partes] == nomes
    assert [p.get("documento") for p in partes] == ["00000000191", "00000000272", "00000000353"]
    assert "selada" in pagina
