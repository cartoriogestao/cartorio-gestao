"""AS TELAS DOS LIVROS OBRIGATÓRIOS (LG08, 19/10/2026).

O QUE SE PROVA AQUI
    - são livros do delegatário: o balcão (USER) não entra; o auditor vê e não
      lança; o gerente lança; GERAR o Diário do mês é só do oficial;
    - POST sem o token de formulário é recusado;
    - o rastro vai para `audit_logs`, sem o texto do termo nem a descrição da
      despesa — esses ficam no próprio livro;
    - toda tela que o catálogo cita existe no app (catálogo que aponta para o
      que não existe é pior do que catálogo nenhum);
    - o Diário gerado abre na versão gravada, e o livro de visitas sai em papel.

Equipe e autoridade fictícias. Nada de dado real de pessoa.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import livros_obrigatorios as LO             # noqa: E402
from bd_nativo import banco                  # noqa: E402

SENHA = "Senha#12345"
TERMO = "Correição ordinária: livros de notas examinados, sem ressalva."


def _entrar(casa, usuario: str, papel: str):
    casa["db"].create_user(usuario, f"OPERADOR {papel} DE TESTE", SENHA, papel)
    c = casa["app"].test_client()
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"',
                      c.get("/login").get_data(as_text=True)).group(1)
    c.post("/login", data={"username": usuario, "password": SENHA, "csrf_token": token},
           follow_redirects=True)
    return c


def _token(c) -> str:
    with c.session_transaction() as s:
        return s["csrf_token"]


def _post(c, url: str, **dados):
    return c.post(url, data={"csrf_token": _token(c), **dados})


def _rastro(casa, acao: str) -> list[dict]:
    with casa["db"].connect() as con:
        return banco(con).ler(
            "SELECT entity_id, details FROM audit_logs WHERE action = %s ORDER BY id", (acao,))


VISITA = {"data": "2026-10-01", "natureza": "CORREICAO_ORDINARIA",
          "autoridade": "Juiz corregedor permanente da comarca", "termo": TERMO}
DESPESA = {"data": "2026-09-10", "descricao": "Energia elétrica da sede, conta de agosto",
           "documento_especie": "Fatura", "documento_numero": "0001", "valor": "45,00"}


def test_o_balcao_nao_entra_nos_livros_do_delegatario(cg_casa):
    c = _entrar(cg_casa, "balcao", "USER")
    for url in ("/livros-obrigatorios", "/livros-obrigatorios/visitas",
                "/livros-obrigatorios/diario", "/livros-obrigatorios/deposito-previo"):
        assert c.get(url).status_code == 403, url
    assert _post(c, "/livros-obrigatorios/visitas", **VISITA).status_code == 403


def test_o_auditor_ve_os_livros_e_nao_lanca(cg_casa):
    c = _entrar(cg_casa, "auditor", "AUDITOR")
    for url in ("/livros-obrigatorios", "/livros-obrigatorios/visitas",
                "/livros-obrigatorios/visitas/imprimir",
                "/livros-obrigatorios/diario?mes=2026-09",
                "/livros-obrigatorios/deposito-previo"):
        assert c.get(url).status_code == 200, url
    assert _post(c, "/livros-obrigatorios/visitas", **VISITA).status_code == 403
    assert _post(c, "/livros-obrigatorios/diario/despesas", **DESPESA).status_code == 403
    assert _post(c, "/livros-obrigatorios/diario/gerar", mes="2026-09").status_code == 403


def test_post_sem_token_de_formulario_e_recusado(cg_casa):
    c = _entrar(cg_casa, "gerente", "MANAGER")
    assert c.post("/livros-obrigatorios/visitas", data=VISITA).status_code == 400
    assert c.post("/livros-obrigatorios/diario/despesas", data=DESPESA).status_code == 400


def test_a_visita_lancada_deixa_rastro_sem_o_texto_do_termo(cg_casa):
    c = _entrar(cg_casa, "gerente", "MANAGER")
    r = _post(c, "/livros-obrigatorios/visitas", **VISITA)
    assert r.status_code == 302
    tela = c.get("/livros-obrigatorios/visitas").get_data(as_text=True)
    assert TERMO in tela and "retificar" in tela
    rastro = _rastro(cg_casa, "LIVRO_VISITAS_LANCADO")
    assert len(rastro) == 1 and json.loads(rastro[0]["details"])["numero"] == 1
    assert "livros de notas" not in rastro[0]["details"]
    papel = c.get("/livros-obrigatorios/visitas/imprimir").get_data(as_text=True)
    assert "Nº 1" in papel and TERMO in papel


def test_a_visita_recusada_volta_com_a_frase_e_nao_grava(cg_casa):
    c = _entrar(cg_casa, "gerente", "MANAGER")
    r = _post(c, "/livros-obrigatorios/visitas", **{**VISITA, "data": "2999-01-01"})
    assert r.status_code == 302
    assert "futuro" in c.get(r.headers["Location"]).get_data(as_text=True)
    assert not _rastro(cg_casa, "LIVRO_VISITAS_LANCADO")


def test_o_gerente_lanca_a_despesa_mas_so_o_oficial_gera_o_diario(cg_casa):
    gerente = _entrar(cg_casa, "gerente", "MANAGER")
    assert _post(gerente, "/livros-obrigatorios/diario/despesas", **DESPESA).status_code == 302
    tela = gerente.get("/livros-obrigatorios/diario?mes=2026-09").get_data(as_text=True)
    assert "Energia elétrica da sede" in tela and "45,00" in tela
    assert _post(gerente, "/livros-obrigatorios/diario/gerar", mes="2026-09").status_code == 403
    rastro = _rastro(cg_casa, "LIVRO_DIARIO_DESPESA_LANCADA")
    assert len(rastro) == 1 and "Energia" not in rastro[0]["details"]

    oficial = _entrar(cg_casa, "oficial", "ADMIN")
    r = _post(oficial, "/livros-obrigatorios/diario/gerar", mes="2026-09")
    assert r.status_code == 302 and "/diario/versao/" in r.headers["Location"]
    papel = oficial.get(r.headers["Location"]).get_data(as_text=True)
    assert "Livro Diário Auxiliar da Receita e da Despesa — 09/2026" in papel
    assert "Energia elétrica da sede" in papel and "assinatura e rubrica" in papel
    assert json.loads(_rastro(cg_casa, "LIVRO_DIARIO_GERADO")[0]["details"])["versao"] == 1
    # A segunda geração sem motivo é recusada, com a frase do art. 206.
    r = _post(oficial, "/livros-obrigatorios/diario/gerar", mes="2026-09")
    assert "art. 206" in oficial.get(r.headers["Location"]).get_data(as_text=True)
    assert len(_rastro(cg_casa, "LIVRO_DIARIO_GERADO")) == 1


def _selo_de_setembro(casa) -> None:
    with casa["db"].transaction() as con:
        banco(con).escrever(
            """INSERT INTO sd_selos (numero, texto, atribuicao, referencia, ambiente,
                   obtido_em, usado_em)
               VALUES (%s, %s, 'NOTAS', 'protocolo 2026.09.1', 'PRODUCAO', %s, %s)""",
            ("TESTEFERJ0001",
             ("Selo: TESTE1323000000000000000000 03/09/2026 10:00:00, "
              "Ato: 13.23, Parte(s): FULANA DE TESTE, Total R$ 140,01 Emol R$ 125,01 "
              "FERC R$ 3,75 FADEP R$ 5,00 FEMP R$ 5,00 FERRFIS R$ 1,25 "
              "Consulte em https://selo.exemplo.invalid"),
             "2026-09-03T10:00:00", "2026-09-03T10:00:00"))


def test_a_tela_e_o_papel_do_diario_tem_o_ferj_e_o_ferc_em_colunas_proprias(cg_casa):
    """O FERJ do art. 190, I, k é 12% do emolumento (15,00 sobre 125,01), e o
    FERC do selo (3,75) sai com o nome dele — não mais «FERJ (FERC no selo)»."""
    _selo_de_setembro(cg_casa)
    oficial = _entrar(cg_casa, "oficial", "ADMIN")
    tela = oficial.get("/livros-obrigatorios/diario?mes=2026-09").get_data(as_text=True)
    assert "FERC no selo" not in tela
    assert "<th>FERJ</th>" in tela and "<th>FERC</th>" in tela
    assert "15,00" in tela and "3,75" in tela and "12,00% de dentro do emolumento" in tela
    r = _post(oficial, "/livros-obrigatorios/diario/gerar", mes="2026-09")
    papel = oficial.get(r.headers["Location"]).get_data(as_text=True)
    assert "FERC no selo" not in papel and "15,00" in papel
    assert "FERJ (art. 190, I, k): 12,00% de dentro do emolumento" in papel


def _ferj_gravado(casa, valor: str) -> None:
    """Grava o percentual do FERJ direto na tabela, «fora da tela» — o caso
    que derrubava a página do livro com HTTP 500 até 27/10/2026."""
    import custas
    casa["db"].set_settings({custas.CHAVE_PERCENTUAL_FERJ: valor})


def test_ferj_ilegivel_gravado_fora_da_tela_nao_derruba_o_diario(cg_casa):
    """Até 27/10/2026 o `CustasError` do percentual ilegível subia sem ser
    apanhado e a tela dava HTTP 500. Agora ela abre, diz o que está errado e
    onde corrigir, e as despesas continuam à mão; gerar também recusa com a
    frase."""
    _selo_de_setembro(cg_casa)
    _ferj_gravado(cg_casa, "doze")
    oficial = _entrar(cg_casa, "oficial", "ADMIN")
    assert _post(oficial, "/livros-obrigatorios/diario/despesas", **DESPESA).status_code == 302
    r = oficial.get("/livros-obrigatorios/diario?mes=2026-09")
    assert r.status_code == 200
    tela = r.get_data(as_text=True)
    assert "O livro do mês não se apura agora" in tela
    assert "Percentual do FERJ ilegível" in tela and "Gestor → NFS-e" in tela
    assert "Energia elétrica da sede" in tela            # as despesas continuam
    assert "Demonstrativo do mês" not in tela             # o livro não se inventa
    r = _post(oficial, "/livros-obrigatorios/diario/gerar", mes="2026-09")
    assert r.status_code == 302
    assert "FERJ" in oficial.get(r.headers["Location"]).get_data(as_text=True)
    assert not _rastro(cg_casa, "LIVRO_DIARIO_GERADO")


def test_ferj_vazio_vale_12_por_cento_no_diario(cg_casa):
    """Decisão do oficial em 27/10/2026: «12% para os dois» — vazio é 12,00
    no Livro Diário e na NFS-e."""
    _selo_de_setembro(cg_casa)
    _ferj_gravado(cg_casa, "")
    oficial = _entrar(cg_casa, "oficial", "ADMIN")
    tela = oficial.get("/livros-obrigatorios/diario?mes=2026-09").get_data(as_text=True)
    assert "12,00% de dentro do emolumento" in tela and "15,00" in tela


def test_a_versao_gerada_antes_do_ferj_abre_e_diz_que_e_de_antes(cg_casa):
    import livro_diario as LD
    _selo_de_setembro(cg_casa)
    oficial = _entrar(cg_casa, "oficial", "ADMIN")
    r = _post(oficial, "/livros-obrigatorios/diario/gerar", mes="2026-09")
    gid = int(r.headers["Location"].rstrip("/").rsplit("/", 1)[1])
    with cg_casa["db"].transaction() as con:
        bd = banco(con)
        velho = LD._sem_ferj(json.loads(bd.valor(
            "SELECT conteudo FROM ld_geracoes WHERE id = %s", (gid,))))
        bd.escrever("UPDATE ld_geracoes SET conteudo = %s, hash = %s WHERE id = %s",
                    (json.dumps(velho, ensure_ascii=False, sort_keys=True),
                     LD._hash(velho), gid))
    papel = oficial.get(r.headers["Location"])
    assert papel.status_code == 200
    texto = papel.get_data(as_text=True)
    assert "Versão gerada antes de 25/10/2026" in texto and "3,75" in texto
    tela = oficial.get("/livros-obrigatorios/diario?mes=2026-09").get_data(as_text=True)
    assert "a versão gerada é de antes da coluna do FERJ" in tela
    assert "o movimento mudou depois da última geração" not in tela


def test_a_despesa_anulada_fica_na_tela_com_o_motivo(cg_casa):
    c = _entrar(cg_casa, "gerente", "MANAGER")
    _post(c, "/livros-obrigatorios/diario/despesas", **DESPESA)
    did = _rastro(cg_casa, "LIVRO_DIARIO_DESPESA_LANCADA")[0]["entity_id"]
    r = _post(c, f"/livros-obrigatorios/diario/despesas/{did}/anular",
              motivo="Lançada em duplicidade.", mes="2026-09")
    assert r.status_code == 302
    tela = c.get("/livros-obrigatorios/diario?mes=2026-09").get_data(as_text=True)
    assert "anulada" in tela and "Lançada em duplicidade." in tela
    assert _rastro(cg_casa, "LIVRO_DIARIO_DESPESA_ANULADA")


def test_toda_tela_que_o_catalogo_cita_existe_no_app(cg_casa):
    rotas = {r for x in LO.LIVROS for r in x["rotas"]}
    assert rotas <= set(cg_casa["app"].view_functions), rotas - set(cg_casa["app"].view_functions)


def test_o_catalogo_abre_e_diz_o_que_falta(cg_casa):
    c = _entrar(cg_casa, "oficial", "ADMIN")
    tela = c.get("/livros-obrigatorios").get_data(as_text=True)
    assert "Livro de Visitas e Correições" in tela and "Livro de Atas Notariais" in tela
    assert "Falta" in tela and "Lei 5.709/1971" in tela
    painel = c.get("/").get_data(as_text=True)
    assert "/livros-obrigatorios" in painel and "/livros-obrigatorios/diario" in painel


def test_o_livro_de_deposito_previo_mostra_as_seis_colunas_do_art_198(cg_casa):
    with cg_casa["db"].transaction() as con:
        banco(con).escrever(
            """INSERT INTO cx_depositos (numero, data, depositante, valor, saldo, criado_em)
               VALUES ('DP2026.09.1', '2026-09-01', 'DEPOSITANTE DE TESTE', '300,00',
                       '300,00', '2026-09-01T09:00:00')""")
    c = _entrar(cg_casa, "oficial", "ADMIN")
    tela = c.get("/livros-obrigatorios/deposito-previo").get_data(as_text=True)
    for coluna in ("I — protocolo", "II — data", "III — valor", "IV — conversão",
                   "V — devolução", "VI — orçamento"):
        assert coluna in tela
    assert "DP2026.09.1" in tela and "não aponta protocolo" in tela


@pytest.mark.parametrize("mes", ["2026-13", "setembro"])
def test_mes_invalido_volta_para_o_mes_anterior_com_a_frase(cg_casa, mes):
    c = _entrar(cg_casa, "oficial", "ADMIN")
    r = c.get(f"/livros-obrigatorios/diario?mes={mes}")
    assert r.status_code == 302
    assert "AAAA-MM" in c.get(r.headers["Location"]).get_data(as_text=True)
