"""O Livro E pronto para o próximo registro — 13/10/2026.

    «sim. deixe em aberto o proximo registro, mas preparemos o ambiente para
     viabilizar o proximo registro e todos modelos, nos moldes da casa.»
                                                              — o oficial

O QUE ESTES TESTES GUARDAM
    **O número fica em aberto, e não nasce no 1**: com a pendência de
    numeração aberta e sem contador, a lavratura recusa e diz onde informar.
    **Cada espécie tem os papéis que a lei nomeia** (curador, tutor,
    requerente, companheiros e os pais deles), com rótulo, prefixo e ordem.
    **A lavratura recusa o registro sem o título e sem a pessoa que a sentença
    nomeou**, com o artigo da espécie — e o que é condicional não trava.
    **O modelo continua um só** (ordem de 07/09/2026), e a frase de cada
    espécie põe no termo o que o artigo manda.
    **A tela de cada espécie pergunta o que a lavratura cobra**, e nada é
    `required` no navegador.

Nomes fictícios, como em todo teste desta casa.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import rc_assento as RC                                          # noqa: E402
import rc_modelos_do_livro as ML                                 # noqa: E402
import rc_termo as TERMO                                         # noqa: E402
from test_testemunha_fantasma_20261009 import (                  # noqa: E402,F401
    FOLHAS, _como_o_navegador, _con, casa)

LIVRO_E = ("EMANCIPACAO", "INTERDICAO", "AUSENCIA", "TUTELA",
           "UNIAO_ESTAVEL", "OPCAO_NACIONALIDADE")
SV = {"ri_cidade": "Cidade Exemplo", "ri_uf": "MA"}


# ------------------------------------------------------ o número em aberto

def _nucleo_minimo() -> sqlite3.Connection:
    con = conexao_de_teste()
    con.execute("CREATE TABLE nu_numeracao (serie TEXT PRIMARY KEY, proximo INTEGER)")
    con.execute("CREATE TABLE nu_implantacao (chave TEXT, situacao TEXT, titulo TEXT)")
    return con


def test_serie_com_a_pendencia_aberta_e_sem_contador_nao_lavra():
    con = _nucleo_minimo()
    con.execute("INSERT INTO nu_implantacao VALUES ('numeracao:RC_E', 'ABERTA', "
                "'O próximo número do Livro E')")
    with pytest.raises(RC.RcError) as erro:
        RC.numero_sem_dono(con, "RC_E")
    assert "número 1" in str(erro.value)
    assert "O que falta informar" in str(erro.value)


def test_serie_com_contador_lavra_mesmo_com_a_pendencia_aberta():
    """O Livro A lavra todo dia com o contador semeado do acervo."""
    con = _nucleo_minimo()
    con.execute("INSERT INTO nu_implantacao VALUES ('numeracao:RC_A', 'ABERTA', 'x')")
    con.execute("INSERT INTO nu_numeracao VALUES ('RC_A', 19583)")
    RC.numero_sem_dono(con, "RC_A")


def test_informado_o_numero_ou_sem_pendencia_lavra():
    con = _nucleo_minimo()
    con.execute("INSERT INTO nu_implantacao VALUES ('numeracao:RC_E', 'RESOLVIDA', 'x')")
    RC.numero_sem_dono(con, "RC_E")
    RC.numero_sem_dono(conexao_de_teste(), "RC_E")   # sem as tabelas


# ------------------------------------------------------------- os papéis

def test_toda_especie_do_livro_e_tem_papeis_com_rotulo_prefixo_e_ordem():
    for especie in LIVRO_E + ("OUTRO",):
        papeis = RC.PAPEIS_DA_ESPECIE[especie]
        assert papeis
        for p in papeis:
            assert RC.ROTULO_DO_PAPEL.get(p), p
            assert RC.PREFIXO_DO_PAPEL.get(p), p
            assert RC.ORDEM_DO_PAPEL.get(p) is not None, p
    assert "CURADOR" in RC.PAPEIS_DA_ESPECIE["INTERDICAO"]
    assert "TUTOR" in RC.PAPEIS_DA_ESPECIE["TUTELA"]
    assert {"COMPANHEIRO1", "COMPANHEIRO2", "MAE_COMPANHEIRO1",
            "PAI_COMPANHEIRO2"} <= set(RC.PAPEIS_DA_ESPECIE["UNIAO_ESTAVEL"])
    # o registro se faz pelo título, sem declarante nem testemunha (art. 90)
    for especie in LIVRO_E:
        assert "TESTEMUNHA" not in RC.PAPEIS_DA_ESPECIE[especie]


def test_os_prefixos_nao_colidem():
    """Dois papéis com o mesmo prefixo gravariam a mesma gaveta duas vezes."""
    for especie, papeis in RC.PAPEIS_DA_ESPECIE.items():
        prefixos = [RC.PREFIXO_DO_PAPEL[p] for p in papeis]
        assert len(prefixos) == len(set(prefixos)), especie


# --------------------------------------------- o que a lavratura recusa

def _interdicao_completa() -> tuple[dict, list[dict]]:
    a = {"nome": "FULANO EXEMPLO", "livro_e_titulo": "SENTENCA",
         "livro_e_titulo_data": "2026-09-01",
         "livro_e_juizo": "Vara Única da Comarca Exemplo"}
    return a, [{"papel": "REGISTRADO", "nome": "FULANO EXEMPLO"},
               {"papel": "CURADOR", "nome": "BELTRANA EXEMPLO", "sexo": "F"}]


def test_interdicao_sem_curador_nem_sentenca_e_recusada_com_o_artigo():
    with pytest.raises(RC.RcError) as erro:
        RC.conferir_requisitos_legais("INTERDICAO", {"nome": "FULANO"}, [])
    texto = str(erro.value)
    assert "art. 92" in texto
    assert "curador" in texto and "data do título" in texto


def test_interdicao_completa_passa_e_o_condicional_nao_trava():
    a, pessoas = _interdicao_completa()
    RC.conferir_requisitos_legais("INTERDICAO", a, pessoas)   # sem causa,
    # sem limites, sem internação, sem requerente: o termo os omite


def test_sentenca_sem_juizo_e_escritura_sem_tabelionato_sao_recusadas():
    a, pessoas = _interdicao_completa()
    with pytest.raises(RC.RcError, match="juízo"):
        RC.conferir_requisitos_legais("INTERDICAO", {**a, "livro_e_juizo": ""},
                                      pessoas)
    esc = {"nome": "MENOR EXEMPLO", "livro_e_titulo": "ESCRITURA",
           "livro_e_titulo_data": "2026-09-01"}
    with pytest.raises(RC.RcError, match="tabelionato"):
        RC.conferir_requisitos_legais(
            "EMANCIPACAO", esc, [{"papel": "MAE", "nome": "MAE EXEMPLO"}])


def test_titulo_que_a_especie_nao_admite_e_recusado():
    """Interdição não se registra por escritura."""
    a, pessoas = _interdicao_completa()
    with pytest.raises(RC.RcError, match="título que se registra"):
        RC.conferir_requisitos_legais(
            "INTERDICAO", {**a, "livro_e_titulo": "ESCRITURA"}, pessoas)


def test_uniao_estavel_exige_os_dois_companheiros_e_o_regime():
    a = {"nome": "ANA E BRUNO", "livro_e_titulo": "TERMO",
         "livro_e_titulo_data": "2026-09-01"}
    with pytest.raises(RC.RcError) as erro:
        RC.conferir_requisitos_legais("UNIAO_ESTAVEL", a, [
            {"papel": "COMPANHEIRO1", "nome": "ANA EXEMPLO"}])
    assert "segundo(a) companheiro(a)" in str(erro.value)
    assert "regime de bens" in str(erro.value)
    RC.conferir_requisitos_legais(
        "UNIAO_ESTAVEL", {**a, "regime_bens": "COMUNHAO_PARCIAL"},
        [{"papel": "COMPANHEIRO1", "nome": "ANA EXEMPLO"},
         {"papel": "COMPANHEIRO2", "nome": "BRUNO EXEMPLO"}])


def test_o_outro_so_pede_o_nome():
    RC.conferir_requisitos_legais("OUTRO", {"nome": "REGISTRO EXEMPLO"}, [])


# --------------------------------------------------------------- o termo

def test_o_modelo_continua_um_so_e_confere():
    """Ordem de 07/09/2026: «livro e usa o mesmo modelo»."""
    for especie in LIVRO_E + ("OUTRO",):
        assert TERMO.MODELO_DA_ESPECIE[especie] == "RC_TERMO_LIVRO_E"
    assert ML.conferir("LIVRO_E") == []
    assert "Lido e achado conforme" in ML.TERMO_LIVRO_E


def test_o_termo_da_interdicao_diz_o_que_o_art_92_manda():
    a, pessoas = _interdicao_completa()
    a.update(especie="INTERDICAO", data_ato="2026-10-13",
             livro_e_juiz="JUIZ EXEMPLO", livro_e_processo="0000001-00.2026",
             livro_e_causa="causa de exemplo", livro_e_limites="atos patrimoniais",
             livro_e_internacao="Clínica Exemplo")
    pessoas.append({"papel": "REQUERENTE", "nome": "CICRANO EXEMPLO"})
    t = ML.montar_livro_e_do_assento(a, pessoas, sv=SV, escrevente="E",
                                     funcao_do_escrevente="F")
    texto = t["texto"]
    assert t["em_branco"] == []
    for trecho in ("REGISTRO DE INTERDIÇÃO", "Interdição decretada",
                   "pelo Juízo da Vara Única da Comarca Exemplo",
                   "MM. Juiz(a) JUIZ EXEMPLO", "0000001-00.2026",
                   "a requerimento de CICRANO EXEMPLO",
                   "tendo por causa causa de exemplo",
                   "sendo nomeada curadora BELTRANA EXEMPLO",
                   "limites da curatela: atos patrimoniais",
                   "Local de internação: Clínica Exemplo."):
        assert trecho in texto, trecho
    assert ", ," not in texto and " ." not in texto


def test_o_termo_da_uniao_estavel_qualifica_os_dois_e_diz_o_regime():
    a = {"especie": "UNIAO_ESTAVEL", "nome": "ANA EXEMPLO E BRUNO EXEMPLO",
         "data_ato": "2026-10-13", "regime_bens": "COMUNHAO_PARCIAL",
         "livro_e_titulo": "ESCRITURA", "livro_e_titulo_data": "2026-08-10",
         "livro_e_tabelionato": "Tabelionato Exemplo",
         "livro_e_uniao_inicio": "2020-01-15"}
    pessoas = [{"papel": "COMPANHEIRO1", "nome": "ANA EXEMPLO", "sexo": "F",
                "nome_pos": "ANA EXEMPLO SOUSA"},
               {"papel": "COMPANHEIRO2", "nome": "BRUNO EXEMPLO", "sexo": "M"},
               {"papel": "MAE_COMPANHEIRO1", "nome": "MAE DA ANA"}]
    texto = ML.montar_livro_e_do_assento(
        a, pessoas, sv=SV, escrevente="E", funcao_do_escrevente="F")["texto"]
    for trecho in ("entre ANA EXEMPLO, filha de MAE DA ANA, e BRUNO EXEMPLO",
                   "por escritura pública lavrada em",
                   "nas notas de Tabelionato Exemplo",
                   "com início em quinze (15) de janeiro",
                   "sob o regime de comunhão parcial",
                   "ANA EXEMPLO passa a usar o nome ANA EXEMPLO SOUSA."):
        assert trecho in texto, trecho


def test_o_outro_sai_como_era():
    a = {"especie": "OUTRO", "nome": "REGISTRO EXEMPLO", "data_ato": "2026-10-13"}
    texto = ML.montar_livro_e_do_assento(
        a, [], sv=SV, escrevente="E", funcao_do_escrevente="F")["texto"]
    assert '"<strong>REGISTRO EXEMPLO</strong>". Lido e achado conforme.' in texto


# --------------------------------------------------------------- a tela

SLUGS = {"EMANCIPACAO": "emancipacao", "INTERDICAO": "interdicao",
         "AUSENCIA": "ausencia", "TUTELA": "tutela",
         "UNIAO_ESTAVEL": "uniao-estavel",
         "OPCAO_NACIONALIDADE": "opcao-nacionalidade"}


@pytest.mark.parametrize("especie", LIVRO_E)
def test_a_tela_de_cada_especie_pergunta_o_que_a_lavratura_cobra(casa, especie):
    html = casa["c"].get(f"/rcpn/novo/{SLUGS[especie]}").get_data(as_text=True)
    assert 'name="livro_e_titulo"' in html and 'name="livro_e_titulo_data"' in html
    for papel in RC.PAPEIS_DA_ESPECIE[especie]:
        assert f'name="{RC.PREFIXO_DO_PAPEL[papel]}_nome"' in html, papel
    for campo in RC.CAMPOS_DA_LEI_POR_ESPECIE[especie]:
        assert f'name="{campo}"' in html, campo
        assert not re.search(rf'name="{campo}"[^>]*required', html), campo
    if especie == "UNIAO_ESTAVEL":
        assert 'name="regime_bens"' in html


def test_a_tela_do_outro_nao_pergunta_titulo(casa):
    html = casa["c"].get("/rcpn/novo/outro-livro-e").get_data(as_text=True)
    assert 'name="livro_e_titulo"' not in html


def _lavrar_pela_tela(casa, especie: str, **campos):
    """Abre a tela, confere e lavra — clicando como o balcão clica."""
    c, slug = casa["c"], SLUGS.get(especie, "outro-livro-e")
    html = c.get(f"/rcpn/novo/{slug}").get_data(as_text=True)
    envio = _como_o_navegador(html, ("acao", "conferir"), **campos)
    conf = c.post(f"/rcpn/novo/{slug}", data=envio,
                  follow_redirects=True).get_data(as_text=True)
    envio2 = _como_o_navegador(conf, ("acao", "lavrar"),
                               folha_seguranca=FOLHAS[0])
    r = c.post(f"/rcpn/novo/{slug}", data=envio2, follow_redirects=True)
    con = _con(casa)
    a = con.execute("SELECT * FROM rc_assentos WHERE especie=? "
                    "ORDER BY id DESC LIMIT 1", (especie,)).fetchone()
    con.close()
    assert a, "não lavrou: " + re.sub(r"\s+", " ", r.get_data(as_text=True))[:800]
    return a


INTERDICAO = dict(
    nome="FULANO EXEMPLO", livro_e_titulo="SENTENCA",
    livro_e_titulo_data="2026-09-01",
    livro_e_juizo="Vara Única da Comarca Exemplo",
    livro_e_causa="causa de exemplo",
    pessoa_nome="FULANO EXEMPLO", pessoa_sexo="M",
    curador_nome="BELTRANA EXEMPLO", curador_sexo="F",
    requerente_nome="CICRANO EXEMPLO")


def test_interdicao_lavrada_pela_tela_leva_o_que_a_lei_manda(casa):
    a = _lavrar_pela_tela(casa, "INTERDICAO", **INTERDICAO)
    con = _con(casa)
    papeis = {p["papel"]: p["nome"] for p in con.execute(
        "SELECT papel, nome FROM rc_pessoas WHERE assento_id=?", (a["id"],))}
    con.close()
    assert a["serie"] == "RC_E"
    assert a["livro_e_juizo"] == "Vara Única da Comarca Exemplo"
    assert papeis.get("CURADOR") == "BELTRANA EXEMPLO"
    assert papeis.get("REQUERENTE") == "CICRANO EXEMPLO"
    teor = a["teor"] or ""
    assert "Interdição decretada" in teor
    assert "sendo nomeada curadora BELTRANA EXEMPLO" in teor


# ------------------------------------------- a tela de corrigir a ficha
#
# «tela corrigir registro é importante fazer» — o oficial, 13/10/2026.

def _corrigir(casa, aid: int, **trocar):
    c = casa["c"]
    html = c.get(f"/rcpn/{aid}/editar").get_data(as_text=True)
    from test_testemunha_fantasma_20261009 import _Formularios
    p = _Formularios()
    p.feed(html)
    form = next(f for f in p.forms if any(n == "motivo" for n, _ in f["campos"]))
    envio = {}
    for nome, valor in form["campos"]:
        envio.setdefault(nome, valor)
    envio.update(motivo="conferido no mandado original de exemplo", **trocar)
    return html, c.post(f"/rcpn/{aid}/editar", data=envio,
                        follow_redirects=True).get_data(as_text=True)


def test_a_tela_de_corrigir_mostra_o_livro_e_preenchido(casa):
    a = _lavrar_pela_tela(casa, "INTERDICAO", **INTERDICAO)
    html = casa["c"].get(f"/rcpn/{a['id']}/editar").get_data(as_text=True)
    assert 'value="Vara Única da Comarca Exemplo"' in html
    assert 'name="curador_nome"' in html and 'value="BELTRANA EXEMPLO"' in html
    assert 'name="livro_e_limites"' in html
    assert "não tem bloco de" not in html


def test_corrigir_o_livro_e_grava_o_titulo_e_a_pessoa(casa):
    a = _lavrar_pela_tela(casa, "INTERDICAO", **INTERDICAO)
    _, r = _corrigir(casa, a["id"], livro_e_juizo="2ª Vara Exemplo",
                     livro_e_limites="atos patrimoniais",
                     curador_nome="BELTRANA EXEMPLO SOUSA")
    con = _con(casa)
    b = con.execute("SELECT * FROM rc_assentos WHERE id=?", (a["id"],)).fetchone()
    cur = con.execute("SELECT nome FROM rc_pessoas WHERE assento_id=? AND "
                      "papel='CURADOR'", (a["id"],)).fetchone()
    con.close()
    assert b["livro_e_juizo"] == "2ª Vara Exemplo", re.sub(r"\s+", " ", r)[:600]
    assert b["livro_e_limites"] == "atos patrimoniais"
    assert b["livro_e_causa"] == "causa de exemplo"      # o que não mudou fica
    assert cur["nome"] == "BELTRANA EXEMPLO SOUSA"


def test_corrigir_o_regime_da_uniao_estavel(casa):
    a = _lavrar_pela_tela(
        casa, "UNIAO_ESTAVEL", nome="ANA EXEMPLO E BRUNO EXEMPLO",
        livro_e_titulo="TERMO", livro_e_titulo_data="2026-09-01",
        regime_bens="COMUNHAO_PARCIAL",
        companheiro1_nome="ANA EXEMPLO", companheiro2_nome="BRUNO EXEMPLO")
    assert a["regime_bens"] == "COMUNHAO_PARCIAL"
    html, _ = _corrigir(casa, a["id"], regime_bens="SEPARACAO_TOTAL")
    assert 'name="companheiro2_nome"' in html
    con = _con(casa)
    b = con.execute("SELECT regime_bens FROM rc_assentos WHERE id=?",
                    (a["id"],)).fetchone()
    con.close()
    assert b["regime_bens"] == "SEPARACAO_TOTAL"


def test_regime_em_especie_que_nao_tem_e_recusado():
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    con.execute("CREATE TABLE rc_assentos (id INTEGER PRIMARY KEY, especie TEXT, "
                "situacao TEXT, nome TEXT, regime_bens TEXT, dados_json TEXT)")
    con.execute("INSERT INTO rc_assentos VALUES (1,'INTERDICAO','ATIVO','X',NULL,'{}')")
    with pytest.raises(RC.RcError, match="regime"):
        RC.corrigir_informacoes(con, 1, motivo="motivo de exemplo longo",
                                agora="2026-10-13T10:00:00",
                                regime_bens="COMUNHAO_PARCIAL")


def test_a_tela_de_corrigir_o_obito_mostra_o_que_a_lei_pede(casa):
    from test_testemunha_fantasma_20261009 import (_lavrar_do_rascunho,
                                                   _rascunho_obito)
    aid, _ = _lavrar_do_rascunho(
        casa, _rascunho_obito() | {"obito_conjuge_nome": "CONJUGE EXEMPLO"},
        FOLHAS[1])
    html = casa["c"].get(f"/rcpn/{aid}/editar").get_data(as_text=True)
    assert 'value="CONJUGE EXEMPLO"' in html
    for campo in RC.CAMPOS_DA_LEI_POR_ESPECIE["OBITO"]:
        assert f'name="{campo}"' in html, campo
    # salvar outro campo não apaga o que a lavratura gravou
    _corrigir(casa, aid, obito_herdeiros_menores="NAO")
    con = _con(casa)
    b = con.execute("SELECT obito_conjuge_nome, obito_herdeiros_menores FROM "
                    "rc_assentos WHERE id=?", (aid,)).fetchone()
    con.close()
    assert (b[0], b[1]) == ("CONJUGE EXEMPLO", "NAO")
