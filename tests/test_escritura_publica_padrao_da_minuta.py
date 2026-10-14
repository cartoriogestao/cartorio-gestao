"""O modelo da escritura pública ajustado ao padrão da minuta — 07/09/2026.

    «criei o submodulo de modelos para poder editar os modelos dos atos no
     sistema mais facilmente. Preciso ajustar o modelo dos atos de escrituras
     publicas para que corresponda ao padrao tecnico e estetico do modelo de
     minuta que baixei mais cedo em downloads» — o oficial.

O QUE O OFICIAL TROUXE, E O QUE SE IMITOU
    `MINUTA_ESCRITURA_MATRICULA para modelo.docx`, uma escritura pública real
    de compra e venda de imóvel rural desta serventia. Ela organiza o corpo em
    TÍTULOS numerados (I a XIII), com seções próprias para o CCIR/CAR, a
    modalidade AD CORPUS, a LGPD e a prevenção à lavagem de dinheiro, e fecha
    com a base legal por extenso. Os dois modelos de compra e venda —
    `NT-ESC-COMPRA-VENDA` (urbano) e `NT-ESC-COMPRA-VENDA-RURAL` — passaram a
    seguir essa mesma forma, com marcador onde o sistema não tem o dado.

    **A NORMA NÃO MUDOU**: art. 795, § 2º, do Código de Normas continua
    exigindo escrituração corrida, sem claros — os títulos são marca dentro
    do MESMO parágrafo, e não linha em branco nem lista. `test_notas_modelos.
    test_nenhum_modelo_tem_quebra_de_linha` já guarda isso.

A LACUNA QUE APARECEU AO CONFERIR SE O MODELO FUNCIONA, E NÃO SÓ SE LÊ BEM
    Os modelos de `notas_modelos.py` usam `{{ sv.ri_cidade }}`,
    `{{ lavrado_nome }}`, `{{ lavrado_titulo }}`, `{{ outorgantes }}` e
    `{{ outorgados }}` — Jinja — desde que foram escritos. **Nada no sistema
    os renderizava**: `/notas/atos/<id>/preencher` só troca `[CAMPO]`,
    `{ESCOLHA}` e `«SE»`, que são os marcadores de `ri_modelos_atos.preencher`.
    Uma escritura montada por aquela tela sairia com as chaves duplas escritas
    por cima do nome das partes — no documento que a serventia assina.

    Corrigido em `notas_teor.partes_por_lado` (monta os dois lados a partir da
    qualificação que o escrevente já digitou) e em `notas_ato_preencher`, que
    agora renderiza o Jinja antes de aplicar os marcadores do escrevente. O
    que não der para classificar sai marcado — não em branco: é a mesma regra
    de `notas_teor._falta()`.
"""
from __future__ import annotations

import glob
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import notas_modelos as NM                                      # noqa: E402
import notas_teor as NT                                         # noqa: E402

SENHA = "Senha#12345"


def limpo(texto: str) -> str:
    return re.sub(r"<[^>]+>", "", texto)


# --------------------------------------------- o padrão da minuta, no corpo

@pytest.mark.parametrize("codigo", ["NT-ESC-COMPRA-VENDA",
                                    "NT-ESC-COMPRA-VENDA-RURAL"])
def test_a_escritura_segue_a_ordem_por_titulos_da_minuta(codigo):
    corpo = limpo(NM.por_codigo(codigo)["corpo"])
    ordem = ["I - DO IMÓVEL", "II - DA MATRÍCULA", "III - DO PREÇO",
             "DA MODALIDADE DA VENDA, AD CORPUS, POSSE E EVICÇÃO",
             "DA BASE LEGAL, DA LEITURA E DO CONSENTIMENTO"]
    posicoes = [corpo.find(t) for t in ordem]
    assert all(p >= 0 for p in posicoes), \
        [t for t, p in zip(ordem, posicoes) if p < 0]
    assert posicoes == sorted(posicoes), "os títulos saíram fora de ordem"


@pytest.mark.parametrize("codigo", ["NT-ESC-COMPRA-VENDA",
                                    "NT-ESC-COMPRA-VENDA-RURAL"])
def test_a_escritura_traz_lgpd_prevencao_e_a_base_legal(codigo):
    corpo = limpo(NM.por_codigo(codigo)["corpo"])
    assert "13.709/2018" in corpo                       # LGPD
    assert "lavagem de dinheiro" in corpo
    assert "1.245 do Código Civil" in corpo
    assert "Provimento CNJ n. 149/2023" in corpo


def test_a_escritura_rural_traz_o_ccir_o_car_e_o_itr():
    # test_notas_modelos.test_imovel_rural_transcreve_o_ccir_e_o_itr já guarda
    # o essencial (CCIR, 802 § 5º, Territorial Rural). Este acrescenta o CAR
    # e a modalidade, que são o que a minuta trouxe de novo.
    m = NM.por_codigo("NT-ESC-COMPRA-VENDA-RURAL")
    corpo = limpo(m["corpo"])
    assert "Cadastro Ambiental Rural" in corpo
    assert "AD CORPUS" in corpo
    assert any("Cadastro Ambiental Rural" in r for r in m["requisitos"])


def test_a_escritura_urbana_tambem_ganhou_ad_corpus_e_lgpd():
    # A ordem por títulos e as cláusulas de LGPD/prevenção não são exclusivas
    # do rural — o padrão que o oficial pediu é da ESCRITURA, não do imóvel.
    m = NM.por_codigo("NT-ESC-COMPRA-VENDA")
    corpo = limpo(m["corpo"])
    assert "AD CORPUS" in corpo
    assert any("ad corpus ou ad mensuram" in r for r in m["requisitos"])


# ------------------------------------- a lacuna do Jinja, e a correção dela

def test_partes_por_lado_separa_pela_qualificacao_digitada():
    outorgantes, outorgados = NT.partes_por_lado([
        {"nome": "CLAUDIO GOMES BITENCOURT", "qualificacao": "outorgante vendedor",
         "tipo_pessoa": "F", "documento": "00000002216",
         "nacionalidade": "brasileiro", "estado_civil": "casado",
         "profissao": "lavrador", "endereco": "zona rural"},
        {"nome": "CITÂNIO LIMA MIRANDA", "qualificacao": "outorgado comprador",
         "tipo_pessoa": "F", "documento": "00000001678",
         "nacionalidade": "brasileiro", "estado_civil": "casado",
         "profissao": "lavrador", "endereco": "zona rural"},
        {"nome": "FULANA TESTEMUNHA", "qualificacao": "", "testemunha": 1},
    ])
    assert "CLAUDIO GOMES BITENCOURT" in outorgantes
    assert "CITÂNIO LIMA MIRANDA" in outorgados
    assert "ALUIZIO" not in outorgados
    assert "CITÂNIO" not in outorgantes
    assert "TESTEMUNHA" not in outorgantes and "TESTEMUNHA" not in outorgados


def test_partes_por_lado_marca_o_lado_que_nao_achou_ninguem():
    # Lado vazio não pode sair em branco — quem confere o teor precisa ver
    # que falta qualificar alguém, e não uma lacuna muda.
    _, outorgados = NT.partes_por_lado([
        {"nome": "SÓ UMA PARTE", "qualificacao": "outorgante vendedor"},
    ])
    assert "[OUTORGADO" in outorgados


@pytest.fixture()
def casa(cg_casa):
    """App/DB compartilhados do modulo (conftest); setup de dominio por teste."""
    banco = cg_casa["banco"]
    c = cg_casa["c"]
    cg_casa["db"].create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS",
                                SENHA, "ADMIN")
    # `nt_modelos` já entra sozinho na inicialização do banco
    # (`database.Database.init_schema` chama `notas_modelos.instalar`) —
    # não depende mais de a carga do acervo ter rodado. Conferido aqui, e
    # não suposto: se a chamada em `database.py` sumir, este teste cai.
    con = sqlite3.connect(banco)
    assert con.execute(
        "SELECT COUNT(*) FROM nt_modelos WHERE codigo='NT-ESC-COMPRA-VENDA-RURAL'"
    ).fetchone()[0] == 1
    con.close()
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"',
                      c.get("/login").get_data(as_text=True)).group(1)
    c.post("/login", data={"username": "tabeliao", "password": SENHA,
                           "csrf_token": token}, follow_redirects=True)
    return cg_casa

def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def test_PREENCHER_NAO_DEIXA_CHAVE_DUPLA_NO_TEOR(casa):
    """O caminho inteiro: abrir o ato, escolher o modelo, incluir as duas
    partes e preencher — como o escrevente faz de verdade."""
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    codigo_modelo = con.execute(
        "SELECT codigo FROM nt_modelos WHERE codigo='NT-ESC-COMPRA-VENDA-RURAL'"
    ).fetchone()["codigo"]
    con.close()
    assert codigo_modelo == "NT-ESC-COMPRA-VENDA-RURAL"

    html = casa["c"].get("/notas/atos/novo").get_data(as_text=True)
    casa["c"].post("/notas/atos/novo", data={
        "csrf_token": _token(html), "tipo": "ESCRITURA",
        "modelo_codigo": "NT-ESC-COMPRA-VENDA-RURAL",
        "interessado": "CLAUDIO GOMES BITENCOURT"}, follow_redirects=True)
    con = sqlite3.connect(casa["banco"])
    ato_id = int(con.execute("SELECT MAX(id) FROM nt_atos").fetchone()[0])
    con.close()

    def parte(nome, qualificacao):
        html = casa["c"].get(f"/notas/atos/{ato_id}").get_data(as_text=True)
        casa["c"].post(f"/notas/atos/{ato_id}", data={
            "csrf_token": _token(html), "acao": "parte_nova", "nome": nome,
            "qualificacao": qualificacao, "tipo_pessoa": "F",
            "nacionalidade": "brasileiro", "estado_civil": "casado",
            "profissao": "lavrador", "endereco": "zona rural",
            "documento": "00000002216"}, follow_redirects=True)

    parte("CLAUDIO GOMES BITENCOURT", "outorgante vendedor")
    parte("CITÂNIO LIMA MIRANDA", "outorgado comprador")

    html = casa["c"].get(f"/notas/atos/{ato_id}").get_data(as_text=True)
    r = casa["c"].post(f"/notas/atos/{ato_id}/preencher", data={
        "csrf_token": _token(html)}, follow_redirects=True)
    assert r.status_code == 200

    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    teor = con.execute("SELECT teor FROM nt_atos WHERE id=?",
                       (ato_id,)).fetchone()["teor"]
    con.close()

    assert "{{" not in teor and "}}" not in teor, \
        "o Jinja não renderizou — a chave dupla foi escrita no teor"
    assert "Cidade Exemplo" in teor            # sv.ri_cidade, do padrão da casa
    assert "CLAUDIO GOMES BITENCOURT" in teor       # outorgantes
    assert "CITÂNIO LIMA MIRANDA" in teor     # outorgados
    assert "MARIO EXEMPLO DOS SANTOS" in teor  # lavrado_nome, de quem logou


# ------------------- "Montar o teor" e "Preencher a partir do modelo" não
# podem se misturar — achado em 07/09/2026, com o oficial testando o ato 777
# no servidor: os dois escrevem `nt_atos.teor`, e cada um serve uma forma
# diferente de modelo. `notas_teor.montar()` monta comparecimento e
# qualificação por fora, para os 300 modelos importados do E-Ofício (só a
# cláusula de poderes); os modelos do submódulo (`origem='SISTEMA'`) já são o
# instrumento inteiro. Passar um modelo SISTEMA por `montar()` cola o
# instrumento inteiro (cru, sem passar pelo Jinja) depois do comparecimento
# que `montar()` monta por conta própria — o ato sai com o texto dobrado e
# `{{ }}`/`[CAMPO]` intactos, exatamente o que o oficial viu no ato 777.

def test_MONTAR_RECUSA_PARA_MODELO_DE_ORIGEM_SISTEMA(casa):
    html = casa["c"].get("/notas/atos/novo").get_data(as_text=True)
    casa["c"].post("/notas/atos/novo", data={
        "csrf_token": _token(html), "tipo": "ESCRITURA",
        "modelo_codigo": "NT-ESC-COMPRA-VENDA-RURAL",
        "interessado": "FULANO DE TAL"}, follow_redirects=True)
    con = sqlite3.connect(casa["banco"])
    ato_id = int(con.execute("SELECT MAX(id) FROM nt_atos").fetchone()[0])
    con.close()

    html = casa["c"].get(f"/notas/atos/{ato_id}").get_data(as_text=True)
    casa["c"].post(f"/notas/atos/{ato_id}", data={
        "csrf_token": _token(html), "acao": "parte_nova", "nome": "FULANO DE TAL",
        "qualificacao": "outorgante vendedor", "tipo_pessoa": "F",
        "nacionalidade": "brasileiro", "estado_civil": "casado",
        "profissao": "lavrador", "endereco": "zona rural",
        "documento": "00000002216"}, follow_redirects=True)

    html = casa["c"].get(f"/notas/atos/{ato_id}").get_data(as_text=True)
    r = casa["c"].post(f"/notas/atos/{ato_id}/montar", data={
        "csrf_token": _token(html)}, follow_redirects=True)
    assert r.status_code == 200
    pagina = r.get_data(as_text=True)
    assert "Preencher a partir do modelo" in pagina

    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    teor = con.execute("SELECT teor FROM nt_atos WHERE id=?",
                       (ato_id,)).fetchone()["teor"]
    con.close()
    assert not (teor or "").strip(), \
        "a rota recusou, mas gravou teor mesmo assim"


def test_A_TELA_NAO_OFERECE_MONTAR_PARA_MODELO_DE_ORIGEM_SISTEMA(casa):
    html = casa["c"].get("/notas/atos/novo").get_data(as_text=True)
    casa["c"].post("/notas/atos/novo", data={
        "csrf_token": _token(html), "tipo": "ESCRITURA",
        "modelo_codigo": "NT-ESC-COMPRA-VENDA-RURAL",
        "interessado": "FULANO DE TAL"}, follow_redirects=True)
    con = sqlite3.connect(casa["banco"])
    ato_id = int(con.execute("SELECT MAX(id) FROM nt_atos").fetchone()[0])
    con.close()

    pagina = casa["c"].get(f"/notas/atos/{ato_id}").get_data(as_text=True)
    assert 'action="/notas/atos/%d/montar"' % ato_id not in pagina


def test_MONTAR_AINDA_FUNCIONA_PARA_MODELO_DE_ORIGEM_EOFICIO(casa):
    # Os 300 modelos importados do E-Ofício continuam precisando de
    # `notas_teor.montar()` — a cláusula de poderes não é o instrumento
    # inteiro, e por isso a recusa acima não pode alcançá-los.
    con = sqlite3.connect(casa["banco"])
    con.execute(
        """INSERT INTO nt_modelos
           (codigo, tipo, nome, nome_norm, corpo, com_imovel, ativo,
            origem, criado_em)
           VALUES ('PROC-TESTE', 'PROCURACAO', 'Procuração de teste',
                   'PROCURACAO DE TESTE',
                   '<p>a quem confere amplos poderes para vender o imóvel.</p>',
                   0, 1, 'EOFICIO', datetime('now'))""")
    con.commit()
    con.close()

    html = casa["c"].get("/notas/atos/novo").get_data(as_text=True)
    casa["c"].post("/notas/atos/novo", data={
        "csrf_token": _token(html), "tipo": "PROCURACAO",
        "modelo_codigo": "PROC-TESTE",
        "interessado": "FULANO DE TAL"}, follow_redirects=True)
    con = sqlite3.connect(casa["banco"])
    ato_id = int(con.execute("SELECT MAX(id) FROM nt_atos").fetchone()[0])
    con.close()

    html = casa["c"].get(f"/notas/atos/{ato_id}").get_data(as_text=True)
    assert 'action="/notas/atos/%d/montar"' % ato_id in html
    casa["c"].post(f"/notas/atos/{ato_id}", data={
        "csrf_token": _token(html), "acao": "parte_nova", "nome": "FULANO DE TAL",
        "qualificacao": "outorgante", "tipo_pessoa": "F",
        "nacionalidade": "brasileiro", "estado_civil": "casado",
        "profissao": "lavrador", "endereco": "zona rural",
        "documento": "00000002216"}, follow_redirects=True)

    html = casa["c"].get(f"/notas/atos/{ato_id}").get_data(as_text=True)
    r = casa["c"].post(f"/notas/atos/{ato_id}/montar", data={
        "csrf_token": _token(html)}, follow_redirects=True)
    assert r.status_code == 200

    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    teor = con.execute("SELECT teor FROM nt_atos WHERE id=?",
                       (ato_id,)).fetchone()["teor"]
    con.close()
    assert "SAIBAM quantos este público instrumento" in teor
    assert "FULANO DE TAL" in teor
    assert "amplos poderes para vender o imóvel" in teor
