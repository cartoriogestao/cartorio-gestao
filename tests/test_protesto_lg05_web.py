"""
Testes das telas do LG05 — repasse, certidão em relação e o a posteriori na rota.

O QUE ELES CONFEREM
      - as duas telas abrem em instalação nova, e o relatório sai em CSV;
      - cada passo grava rastro em `audit_logs`, sem dado de pessoa;
      - quem não responde pelo caixa não mexe no dinheiro (403), e sem CSRF
        nada se grava;
      - na rota de lançar, o ato do título diferido sela e NÃO entra no caixa;
        o pagamento cobra o devido e o item marcado pela tabela da
        protocolização — com duas tabelas de preços diferentes no banco;
      - o envio da relação nasce desligado e, ligado em produção com o serviço
        falso, registra a entrega.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import protesto as PT                            # noqa: E402
import protesto_relacao as REL                   # noqa: E402
from bd_nativo import banco as nativo            # noqa: E402

SENHA = "Senha#12345"
SV = {"unit_name": "SERVENTIA DE TESTE", "serventia_titular": "TABELIÃO DE TESTE",
      "serventia_titulo": "Tabelião", "ri_cns": "000000",
      "ri_cidade": "Cidade Exemplo", "ri_uf": "MA"}
EXTENSO = "um dia do mês de janeiro do ano de dois mil e vinte e seis"
CNPJ = "00000043000177"          # fictício, confere pelo dígito


@pytest.fixture()
def s(cg_casa_logada):
    cg_casa_logada["db"].set_settings({"modulo_protesto_ligado": "1"})
    return cg_casa_logada


def _token(s) -> str:
    html = s["c"].get("/protesto/repasses").get_data(as_text=True)
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _post(s, rota, **campos):
    return s["c"].post(rota, data={"csrf_token": _token(s), **campos},
                       follow_redirects=True)


def _titulo(s, *, origem="CRA", chave="WEB:1", pagar=True, quando=None) -> dict:
    quando = quando or s["db"].now()
    d = {"especie": "DMI", "numero_titulo": chave.replace(":", "/"),
         "data_emissao": "2025-12-01", "data_vencimento": "2025-12-20",
         "valor": "1482.78", "saldo": "1482.78", "praca_protesto": "CIDADE EXEMPLO",
         "tipo_moeda": "1", "tipo_protesto": "C", "motivo_protesto": "1",
         "cedente": {"nome": "CREDOR FICTICIO", "documento": "00000000000000",
                     "cidade": "Cidade Exemplo", "uf": "MA"},
         "devedores": [{"nome": "DEVEDOR FICTICIO", "CPF": "00000000000",
                        "enderecos": [{"endereco": "Rua X", "bairro": "Centro",
                                       "cidade": "Cidade Exemplo", "uf": "MA"}]}]}
    with s["db"].transaction() as con:
        tid = PT.cadastrar_titulo(con, d, origem=origem,
                                  origem_chave=None if origem == "MANUAL" else chave,
                                  agora=quando)
        PT.lancar_apontamento(con, tid, sv=SV, agora=quando, data_extenso=EXTENSO)
        ato = None
        if pagar:
            ato = PT.lancar_pagamento(con, tid, sv=SV, agora=quando,
                                      data_extenso=EXTENSO,
                                      forma_pagamento="PIX")["ato_id"]
    return {"titulo_id": tid, "ato_id": ato}


def _rastro(s, acao) -> list[dict]:
    with s["db"].connect() as con:
        return nativo(con).ler(
            "SELECT * FROM audit_logs WHERE action=%s ORDER BY id", (acao,))


def _ler(s, sql, parametros=None):
    with s["db"].connect() as con:
        return nativo(con).ler(sql, parametros)


# --------------------------------------------------------------- as telas


@pytest.mark.parametrize("rota", ["/protesto/repasses", "/protesto/relacao-diaria"])
def test_as_telas_do_lg05_abrem_em_instalacao_nova(s, rota):
    r = s["c"].get(rota)
    assert r.status_code == 200


def test_o_relatorio_de_pendencias_sai_em_csv_com_o_pagamento(s):
    _titulo(s)
    r = s["c"].get("/protesto/repasses/pendencias.csv")
    assert r.status_code == 200
    texto = r.get_data().decode("utf-8-sig")
    # Desde 26/10/2026 todo campo vai entre aspas (`csv_seguro`, achado
    # transversal 2 da revisão de segurança).
    assert texto.splitlines()[0].startswith('"CANAL";"PROTOCOLO";"TITULO"')
    assert '"IEPTB";' in texto and "1.482,78" in texto


def test_gerar_a_guia_pela_tela_deixa_rastro_sem_dado_de_pessoa(s):
    _titulo(s)
    html = _post(s, "/protesto/repasses/guias").get_data(as_text=True)
    assert "Guia 1/" in html
    [linha] = _rastro(s, "PROTESTO_REPASSE_GUIA_GERADA")
    assert "DEVEDOR" not in (linha["details"] or "")
    assert json.loads(linha["details"])["titulos"] == 1


def test_o_balcao_ve_mas_nao_mexe_no_dinheiro(s):
    _titulo(s)
    s["db"].create_user("balcao", "ESCREVENTE DE TESTE", SENHA, "USER")
    from conftest import cg_login
    c = s["app"].test_client()
    cg_login(c, "balcao", SENHA)
    assert c.get("/protesto/repasses").status_code == 200
    html = c.get("/protesto/repasses").get_data(as_text=True)
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)
    assert c.post("/protesto/repasses/guias",
                  data={"csrf_token": token}).status_code == 403
    assert _ler(s, "SELECT id FROM pt_repasse_guias ORDER BY id") == []


def test_sem_csrf_a_guia_nao_se_gera(s):
    _titulo(s)
    r = s["c"].post("/protesto/repasses/guias", data={})
    assert r.status_code in (400, 403)
    assert _ler(s, "SELECT id FROM pt_repasse_guias ORDER BY id") == []


def test_o_repasse_direto_pela_tela_exige_o_comprovante(s):
    p = _titulo(s, origem="MANUAL")
    html = _post(s, "/protesto/repasses/direto", ato_id=str(p["ato_id"]),
                 forma="DEPOSITO", comprovante="").get_data(as_text=True)
    assert "comprovante" in html
    _post(s, "/protesto/repasses/direto", ato_id=str(p["ato_id"]),
          forma="DEPOSITO", comprovante="Depósito 556677")
    assert len(_rastro(s, "PROTESTO_REPASSE_DIRETO")) == 1


def test_a_guia_anda_pela_tela_ate_conciliada(s):
    _titulo(s)
    _post(s, "/protesto/repasses/guias")
    [g] = _ler(s, "SELECT id FROM pt_repasse_guias ORDER BY id")
    base = f"/protesto/repasses/guias/{g['id']}"
    _post(s, base + "/registrar", identificador="IEPTB-2026-000777")
    _post(s, base + "/pagar", paga_em=s["db"].now()[:10], comprovante="AUT 1")
    html = _post(s, base + "/conciliar", valor_confirmado="1.000,00",
                 referencia="Aviso 1").get_data(as_text=True)
    assert "diferença" in html
    _post(s, base + "/conciliar", valor_confirmado="1.482,78",
          referencia="Aviso 1")
    [g] = _ler(s, "SELECT situacao FROM pt_repasse_guias ORDER BY id")
    assert g["situacao"] == "CONCILIADA"
    assert s["c"].get(base + "/relacao.txt").status_code == 200


# --------------------------------------------- o a posteriori na rota de lançar


def _tabelas_e_caixa(s) -> int:
    """Duas tabelas com preços diferentes e o caixa do operador aberto."""
    with s["db"].transaction() as con:
        bd = nativo(con)
        bd.escrever("""INSERT INTO cx_vigencias(codigo, descricao, vigente, inicio, fim)
                       VALUES (801, 'velha', 0, '2020-01-01', '2026-06-30'),
                              (802, 'nova', 0, '2026-07-01', NULL)""")
        bd.escrever("""INSERT INTO cx_servicos(codigo, codigo_tj, descricao)
                       VALUES (9901, '17.5.1', 'Item de teste')""")
        for vig, preco in ((801, "10,00"), (802, "12,00")):
            bd.escrever(
                """INSERT INTO cx_servico_valores(servico, vigencia, emolumentos,
                       ferc, femp, fadep, ferrfis, total)
                   VALUES (9901,%s,%s,'0,00','0,00','0,00','0,00',%s)""",
                (vig, preco, preco))
        bd.escrever(
            """INSERT INTO cx_caixas(data, operador_nome, aberto_em, situacao)
               VALUES (%s,'MARIO EXEMPLO DOS SANTOS',%s,'ABERTO')""",
            (s["db"].now()[:10], s["db"].now()))
    return 9901


def _lancar(s, titulo_id, **campos):
    html = s["c"].get(f"/protesto/{titulo_id}").get_data(as_text=True)
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)
    return s["c"].post(f"/protesto/{titulo_id}/lancar",
                       data={"csrf_token": token, **campos},
                       follow_redirects=True).get_data(as_text=True)


def test_a_ficha_do_titulo_da_central_mostra_que_e_a_posteriori(s):
    p = _titulo(s, pagar=False)
    texto = " ".join(s["c"].get(f"/protesto/{p['titulo_id']}")
                     .get_data(as_text=True).split())
    assert "a posteriori (diferido)" in texto
    assert "§ 11" in texto


def test_o_pagamento_diferido_cobra_pela_tabela_da_protocolizacao(s):
    from selador_de_bancada import ligar_o_selador
    servico = _tabelas_e_caixa(s)
    p = _titulo(s, pagar=False, quando="2026-01-15T09:00:00")
    # O que a protocolização deixou devido, como a rota deixaria.
    with s["db"].transaction() as con:
        import protesto_posteriori as POST
        [ap] = nativo(con).ler(
            "SELECT id FROM pt_atos WHERE titulo_id=%s AND tipo='APONTAMENTO'",
            (p["titulo_id"],))
        POST.diferir(con, titulo_id=p["titulo_id"], ato_id=ap["id"],
                     tipo_ato="APONTAMENTO", itens=[{"servico": servico}],
                     data_do_ato="2026-01-15", agora="2026-01-15T09:00:00")
    with ligar_o_selador(s):
        html = _lancar(s, p["titulo_id"], ato="PAGAMENTO",
                       forma_pagamento="PIX", cobrar=str(servico),
                       cobrar_diferidos="1")
    assert "A posteriori: R$ 10,00" in html
    valores = [r["valor"] for r in _ler(
        s, "SELECT valor FROM cx_lancamentos WHERE origem='ATO' ORDER BY id")]
    # Os dois pela tabela VELHA (a da protocolização), e não pela de hoje.
    assert valores == ["10,00", "10,00"]


def test_a_protocolizacao_diferida_pela_rota_nao_entra_no_caixa(s):
    from selador_de_bancada import ligar_o_selador
    servico = _tabelas_e_caixa(s)
    with s["db"].transaction() as con:
        d = {"especie": "DMI", "numero_titulo": "WEB/AP",
             "data_emissao": "2025-12-01", "data_vencimento": "2025-12-20",
             "valor": "100.00", "saldo": "100.00",
             "praca_protesto": "CIDADE EXEMPLO", "tipo_moeda": "1",
             "tipo_protesto": "C", "motivo_protesto": "1",
             "cedente": {"nome": "CREDOR FICTICIO", "documento": "00000000000000",
                         "cidade": "Cidade Exemplo", "uf": "MA"},
             "devedores": [{"nome": "DEVEDOR FICTICIO", "CPF": "00000000000",
                            "enderecos": [{"endereco": "Rua X", "bairro": "C",
                                           "cidade": "Cidade Exemplo",
                                           "uf": "MA"}]}]}
        tid = PT.cadastrar_titulo(con, d, origem="CRA", origem_chave="WEB:AP",
                                  agora=s["db"].now())
    with ligar_o_selador(s):
        html = _lancar(s, tid, ato="APONTAMENTO", cobrar=str(servico))
    assert "fica devido e NÃO entrou no caixa" in html
    assert _ler(s, "SELECT id FROM cx_lancamentos WHERE origem='ATO' ORDER BY id") == []
    assert len(_ler(s, "SELECT id FROM pt_emolumentos_diferidos ORDER BY id")) == 1


def test_o_regime_muda_pela_ficha_antes_do_primeiro_ato_e_fica_no_rastro(s):
    with s["db"].transaction() as con:
        d = {"especie": "DMI", "numero_titulo": "WEB/REG",
             "data_emissao": "2025-12-01", "data_vencimento": "2025-12-20",
             "valor": "100.00", "saldo": "100.00",
             "praca_protesto": "CIDADE EXEMPLO", "tipo_moeda": "1",
             "tipo_protesto": "C", "motivo_protesto": "1",
             "cedente": {"nome": "CREDOR FICTICIO", "documento": "00000000000000",
                         "cidade": "Cidade Exemplo", "uf": "MA"},
             "devedores": [{"nome": "DEVEDOR FICTICIO", "CPF": "00000000000",
                            "enderecos": [{"endereco": "Rua X", "bairro": "C",
                                           "cidade": "Cidade Exemplo",
                                           "uf": "MA"}]}]}
        tid = PT.cadastrar_titulo(con, d, origem="CRA", origem_chave="WEB:REG",
                                  agora=s["db"].now())
    _post(s, f"/protesto/{tid}/regime-emolumentos", regime="ANTECIPADO",
          motivo="Apresentante sem convênio com a Central")
    [linha] = _rastro(s, "PROTESTO_REGIME_EMOLUMENTOS")
    assert json.loads(linha["details"])["regime"] == "ANTECIPADO"


# ------------------------------------------------- a certidão em relação


def test_a_relacao_pela_tela_habilita_gera_baixa_e_entrega(s):
    ontem = (date.fromisoformat(s["db"].now()[:10]) - timedelta(days=1)).isoformat()
    _post(s, "/protesto/relacao-diaria/entidades", nome="ENTIDADE FICTÍCIA",
          documento=CNPJ, canal="DIRETO", habilitacao="Requerimento 1/2026",
          habilitada_em="2026-01-01")
    [ent] = _ler(s, "SELECT id FROM pt_relacao_entidades ORDER BY id")
    html = _post(s, "/protesto/relacao-diaria/gerar", dia=ontem,
                 entidade_id=str(ent["id"])).get_data(as_text=True)
    assert "gerada" in html
    [rel] = _ler(s, "SELECT id FROM pt_relacoes_diarias ORDER BY id")
    arquivo = s["c"].get(f"/protesto/relacao-diaria/{rel['id']}/arquivo")
    assert REL.AVISO_DE_RESERVA in arquivo.get_data().decode("utf-8-sig")
    _post(s, f"/protesto/relacao-diaria/{rel['id']}/entregar", forma="EMAIL",
          comprovante="E-mail enviado às 9h")
    assert len(_rastro(s, "PROTESTO_RELACAO_ENTREGUE")) == 1


def test_o_envio_pela_tela_nasce_desligado_e_ligado_registra_a_entrega(s):
    ontem = (date.fromisoformat(s["db"].now()[:10]) - timedelta(days=1)).isoformat()
    _post(s, "/protesto/relacao-diaria/entidades", nome="ENTIDADE FICTÍCIA",
          documento=CNPJ, canal="CENPROT", habilitacao="Requerimento 2/2026",
          habilitada_em="2026-01-01")
    [ent] = _ler(s, "SELECT id FROM pt_relacao_entidades ORDER BY id")
    _post(s, "/protesto/relacao-diaria/gerar", dia=ontem,
          entidade_id=str(ent["id"]))
    [rel] = _ler(s, "SELECT id FROM pt_relacoes_diarias ORDER BY id")
    falso = REL.TransporteFalso()
    s["app"].config["PROTESTO_RELACAO_TRANSPORTE"] = falso
    try:
        html = _post(s, f"/protesto/relacao-diaria/{rel['id']}/enviar"
                     ).get_data(as_text=True)
        assert "desligado" in html and falso.enviados == []
        _post(s, "/protesto/relacao-diaria/configuracao", modo="PRODUCAO")
        _post(s, f"/protesto/relacao-diaria/{rel['id']}/enviar")
    finally:
        s["app"].config.pop("PROTESTO_RELACAO_TRANSPORTE", None)
    assert len(falso.enviados) == 1
    [r] = _ler(s, "SELECT forma_entrega, comprovante_entrega FROM "
                  "pt_relacoes_diarias ORDER BY id")
    assert (r["forma_entrega"], r["comprovante_entrega"]) == ("CENPROT", "FALSO-1")
