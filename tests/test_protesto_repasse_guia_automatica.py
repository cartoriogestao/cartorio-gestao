"""
Testes da relação automática da guia de repasse (29/10/2026).

Pedido do oficial: «emitir automático a guia de repasse do título pago no
cartório pela CRA e CENPROT». Medido antes: nenhuma das duas Centrais tem API
para emitir a guia — ela sai do portal. O que se automatiza é o que é da casa.

O QUE ELES CONFEREM
      - a relação do dia sai UMA POR CENTRAL, só com o que ainda não está em
        guia, e nunca vazia; rodar duas vezes não repete pagamento;
      - entrar na relação NÃO tira o pagamento da pendência: ele segue com o
        prazo e o passo do portal até a guia ser paga
        (`pendencias_do_repasse`, a lista que o roteiro lê);
      - a pendência traz o contrato do roteiro (titulo_id, numero_titulo,
        protocolo, explicacao) e funciona chamada só com `con`;
      - o pagamento desfeito dentro de guia não paga aparece, com o conserto;
      - a rotina da central de automação só gera com «pode agir», avisa
        enquanto a guia espera o portal, vira ERRO com o motivo quando falha,
        e deixa rastro com `agente` — sem dado de pessoa;
      - a rotina nasce no catálogo da automação, e não fala com rede nenhuma;
      - a tela mostra o que falta e onde a guia se emite, e o botão gera as
        relações do dia com rastro.

Nada aqui chama a CRA nem a CENPROT: os dados são sintéticos.
"""
from __future__ import annotations

import json
import re
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import protesto as PT                            # noqa: E402
import protesto_repasse as REP                   # noqa: E402
import protesto_repasse_automacao as RA          # noqa: E402
from bd_nativo import banco as nativo            # noqa: E402
from nucleo_schema import init_nucleo_schema     # noqa: E402
from pt_schema import init_pt_schema             # noqa: E402

PAGO = "2026-10-16T10:00:00"     # uma sexta-feira: o prazo cai na segunda, 19
HOJE = "2026-10-21"
AGORA = HOJE + "T09:00:00"
EXTENSO = "dezesseis dias do mês de outubro do ano de dois mil e vinte e seis"
SV = {"unit_name": "SERVENTIA DE TESTE", "serventia_titular": "TABELIÃO DE TESTE",
      "serventia_titulo": "Tabelião", "ri_cns": "000000",
      "ri_cidade": "Cidade Exemplo", "ri_uf": "MA"}
# Documentos da lista de fictícios (tests/fixtures/anti_vazamento).
CPF = "00000000191"
CNPJ = "00000001000055"


def banco():
    con = conexao_de_teste()
    init_nucleo_schema(con)
    init_pt_schema(con)
    return con


def _dados(numero: str, saldo: str) -> dict:
    return {"especie": "DMI", "numero_titulo": numero,
            "data_emissao": "2026-07-21", "data_vencimento": "2026-09-05",
            "valor": saldo, "saldo": saldo, "praca_protesto": "CIDADE EXEMPLO",
            "tipo_moeda": "1", "tipo_protesto": "C", "motivo_protesto": "1",
            "apresentante_codigo": "999", "apresentante_nome": "BANCO FICTICIO",
            "cedente": {"nome": "CREDOR FICTICIO", "documento": CNPJ,
                        "cidade": "Cidade Exemplo", "uf": "MA"},
            "devedores": [{"nome": "DEVEDOR FICTICIO", "CPF": CPF,
                           "enderecos": [{"endereco": "Rua X", "bairro": "Centro",
                                          "cidade": "Cidade Exemplo",
                                          "uf": "MA"}]}]}


def pago(con, *, origem="CENPROT", chave="GR:1", numero="GR/1",
         saldo="1482.78", quando=PAGO) -> dict:
    tid = PT.cadastrar_titulo(con, _dados(numero, saldo), origem=origem,
                              origem_chave=None if origem == "MANUAL" else chave,
                              agora=quando)
    PT.lancar_apontamento(con, tid, sv=SV, agora=quando, data_extenso=EXTENSO)
    # A FORMA É INCIDENTAL AQUI, e não pode ser PIX: desde o PR #119 o PIX só
    # é pagamento com o crédito conferido (`pix_id`), e `lancar_pagamento`
    # recusa sem ele. Os dois PRs nasceram em paralelo — trocado na
    # integração de 29/10/2026, como o #119 fez nos testes que já existiam.
    r = PT.lancar_pagamento(con, tid, sv=SV, agora=quando, data_extenso=EXTENSO,
                            forma_pagamento="TRANSFERENCIA")
    return {"titulo_id": tid, "ato_id": r["ato_id"]}


def _as_tres(con) -> dict:
    return {"cenprot": pago(con, origem="CENPROT", chave="GR:1", numero="GR/1"),
            "cra": pago(con, origem="CRA", chave="GR:2", numero="GR/2",
                        saldo="200.00"),
            "balcao": pago(con, origem="MANUAL", numero="GR/3", saldo="100.00")}


def _linha(lista, ato_id) -> dict:
    [linha] = [p for p in lista if p["ato_id"] == ato_id]
    return linha


# ----------------------------------------------- a relação do dia, por Central


def test_a_relacao_do_dia_sai_uma_por_central_e_deixa_o_balcao():
    con = banco()
    t = _as_tres(con)
    geradas = REP.gerar_guias_do_dia(con, hoje=HOJE, agora=AGORA, usuario="mario")
    assert [(g["central"], g["titulos"]) for g in geradas] == [("CRA", 1),
                                                               ("CENPROT", 1)]
    assert [g["numero"] for g in geradas] == [1, 2]
    cra = REP.guia(con, geradas[0]["guia_id"])
    assert "GR/2" in cra["relacao"] and "GR/1" not in cra["relacao"]
    assert [p["ato_id"] for p in REP.pendentes(con, hoje=HOJE)] == [
        t["balcao"]["ato_id"]]


def test_sem_pagamento_esperando_nao_gera_guia_vazia():
    con = banco()
    pago(con, origem="MANUAL", numero="GR/3")
    assert REP.gerar_guias_do_dia(con, hoje=HOJE, agora=AGORA) == []
    assert nativo(con).ler("SELECT id FROM pt_repasse_guias") == []


def test_rodar_duas_vezes_no_mesmo_dia_nao_repete_pagamento():
    con = banco()
    pago(con)
    assert len(REP.gerar_guias_do_dia(con, hoje=HOJE, agora=AGORA)) == 1
    assert REP.gerar_guias_do_dia(con, hoje=HOJE, agora=AGORA) == []
    assert len(nativo(con).ler("SELECT id FROM pt_repasse_guias")) == 1


def test_a_guia_de_uma_central_recusa_titulo_de_outra():
    con = banco()
    t = _as_tres(con)
    with pytest.raises(REP.RepasseError, match="outra Central"):
        REP.gerar_guia(con, hoje=HOJE, agora=AGORA, origem="CRA",
                       ato_ids=[t["cenprot"]["ato_id"]])
    with pytest.raises(REP.RepasseError, match="Central desconhecida"):
        REP.gerar_guia(con, hoje=HOJE, agora=AGORA, origem="BANCO")


def test_a_relacao_leva_prazo_central_e_chave_para_o_portal():
    con = banco()
    p = pago(con)
    nativo(con).escrever("UPDATE pt_titulos SET chave_cenprot=%s WHERE id=%s",
                         ("CHAVE-DE-TESTE-0001", p["titulo_id"]))
    [g] = REP.gerar_guias_do_dia(con, hoje=HOJE, agora=AGORA)
    relacao = REP.guia(con, g["guia_id"])["relacao"]
    cabecalho, linha = relacao.splitlines()[1:3]
    assert cabecalho.endswith(";PRAZO;CENTRAL;CHAVE_CENPROT")
    assert linha.endswith(";19/10/2026;CENPROT;CHAVE-DE-TESTE-0001")


def test_a_ficha_da_guia_diz_onde_emitir_e_o_prazo_vencido():
    con = banco()
    pago(con)
    [g] = REP.gerar_guias_do_dia(con, hoje=HOJE, agora=AGORA)
    ficha = REP.guia(con, g["guia_id"], hoje=HOJE)
    assert ficha["centrais"] == ["CENPROT"]
    assert ficha["passos"][0]["onde"].startswith("no portal da CENPROT")
    assert (ficha["prazo"], ficha["vencida"]) == ("2026-10-19", True)
    assert REP.guia(con, g["guia_id"], hoje="2026-10-19")["vencida"] is False


# ------------------------------------- a pendência só acaba com a guia paga


def test_o_pagamento_nao_sai_da_pendencia_ao_entrar_na_relacao():
    con = banco()
    p = pago(con)
    antes = _linha(REP.pendencias_do_repasse(con, hoje=HOJE), p["ato_id"])
    assert antes["etapa"] == REP.SEM_GUIA

    [g] = REP.gerar_guias_do_dia(con, hoje=HOJE, agora=AGORA)
    gerada = _linha(REP.pendencias_do_repasse(con, hoje=HOJE), p["ato_id"])
    assert (gerada["etapa"], gerada["guia"]) == (REP.GUIA_GERADA, f"1/{g['ano']}")
    assert "portal da CENPROT" in gerada["explicacao"]
    assert "ainda NÃO foi emitida" in gerada["explicacao"]

    REP.registrar_guia(con, g["guia_id"], identificador="LIQ-TESTE-123",
                       vencimento="2026-10-23", agora=AGORA, usuario="beatriz")
    registrada = _linha(REP.pendencias_do_repasse(con, hoje=HOJE), p["ato_id"])
    assert registrada["etapa"] == REP.GUIA_REGISTRADA
    assert "LIQ-TESTE-123" in registrada["explicacao"]
    assert "NÃO foi paga" in registrada["explicacao"]

    REP.pagar_guia(con, g["guia_id"], paga_em=HOJE, comprovante="AUT 4455",
                   agora=AGORA, usuario="carla")
    assert REP.pendencias_do_repasse(con, hoje=HOJE) == []


def test_o_prazo_e_o_atraso_seguem_na_guia_nao_paga():
    con = banco()
    p = pago(con)
    REP.gerar_guias_do_dia(con, hoje=HOJE, agora=AGORA)
    linha = _linha(REP.pendencias_do_repasse(con, hoje=HOJE), p["ato_id"])
    assert (linha["prazo"], linha["vencido"], linha["dias_de_atraso"]) == (
        "2026-10-19", True, 2)
    assert "repasse até 19/10/2026 — 2 dia(s) de atraso" in linha["explicacao"]
    rel = REP.relatorio(con, hoje=HOJE)
    assert (len(rel["em_guia"]), rel["vencidos_em_guia"]) == (1, 1)


def test_a_pendencia_traz_o_contrato_do_roteiro_e_aceita_so_con():
    con = banco()
    t = _as_tres(con)
    REP.gerar_guias_do_dia(con, hoje=HOJE, agora=AGORA)
    lista = REP.pendencias_do_repasse(con)          # como o roteiro chama
    assert len(lista) == 3
    for linha in lista:
        assert {"titulo_id", "numero_titulo", "protocolo",
                "explicacao"} <= set(linha)
        assert linha["explicacao"]
        assert str(linha.get("origem") or "").upper() != "ACERVO"
    balcao = _linha(lista, t["balcao"]["ato_id"])
    assert (balcao["etapa"], balcao["central"]) == (REP.DIRETO_A_FAZER, None)
    assert "repasse direto" in balcao["explicacao"]


def test_guia_cancelada_devolve_a_etapa_sem_guia():
    con = banco()
    p = pago(con)
    [g] = REP.gerar_guias_do_dia(con, hoje=HOJE, agora=AGORA)
    REP.cancelar_guia(con, g["guia_id"], motivo="Relação gerada para conferir",
                      agora=AGORA, usuario="mario")
    assert _linha(REP.pendencias_do_repasse(con, hoje=HOJE),
                  p["ato_id"])["etapa"] == REP.SEM_GUIA


def test_pagamento_desfeito_dentro_de_guia_nao_paga_aparece_com_o_conserto():
    con = banco()
    p = pago(con)
    REP.gerar_guias_do_dia(con, hoje=HOJE, agora=AGORA)
    nativo(con).escrever("UPDATE pt_atos SET cancelado=1 WHERE id=%s",
                         (p["ato_id"],))
    linha = _linha(REP.pendencias_do_repasse(con, hoje=HOJE), p["ato_id"])
    assert linha["desfeito"] is True
    assert "cancele essa guia" in linha["explicacao"]


# ------------------------------------------------ a rotina da automação


class _Db:
    """O `db` que a rotina recebe, sobre a conexão de teste. Grava o rastro."""

    def __init__(self, con):
        self.con, self.rastro = con, []

    @contextmanager
    def transaction(self):
        yield self.con

    @contextmanager
    def connect(self):
        yield self.con

    def log(self, *args, **kwargs):
        self.rastro.append((args, kwargs))


def _contexto(con, *, pode_agir: bool):
    return SimpleNamespace(db=_Db(con), agora=datetime(2026, 10, 16, 17, 0),
                           processo={"codigo": RA.CODIGO, "pode_agir": pode_agir})


def test_a_rotina_sem_pode_agir_so_conta():
    con = banco()
    pago(con)
    r = RA.gerar_a_relacao_do_dia(_contexto(con, pode_agir=False))
    assert r["situacao"] == "AVISO"
    assert "pode agir" in r["relato"] and r["acoes"] == []
    assert nativo(con).ler("SELECT id FROM pt_repasse_guias") == []


def test_a_rotina_com_pode_agir_gera_no_dia_e_avisa_que_falta_o_portal():
    con = banco()
    _as_tres(con)
    ctx = _contexto(con, pode_agir=True)
    r = RA.gerar_a_relacao_do_dia(ctx)
    assert r["situacao"] == "AVISO"
    assert [a["central"] for a in r["acoes"]] == ["CRA", "CENPROT"]
    assert "Relação gerada agora" in r["relato"]
    assert "não foi emitida no portal" in r["relato"]
    guias = nativo(con).ler("SELECT dia, gerada_por FROM pt_repasse_guias")
    assert {(str(g["dia"])[:10], g["gerada_por"]) for g in guias} == {
        ("2026-10-16", RA.QUEM_GERA)}
    # O RASTRO: uma linha por guia, com o robô identificado — e sem pessoa.
    assert len(ctx.db.rastro) == 2
    for args, kwargs in ctx.db.rastro:
        assert args[2] == "PROTESTO_REPASSE_GUIA_GERADA"
        assert kwargs["agente"] == RA.AGENTE and kwargs["a_mando_de"] is not None
    tudo = json.dumps([r, [a for a, _ in ctx.db.rastro]], ensure_ascii=False,
                      default=str)
    assert "DEVEDOR" not in tudo and "CREDOR" not in tudo and CPF not in tudo


def test_a_rotina_sem_nada_esperando_fica_ok():
    con = banco()
    r = RA.gerar_a_relacao_do_dia(_contexto(con, pode_agir=True))
    assert r["situacao"] == "OK" and r["acoes"] == []


def test_a_falha_da_rotina_vira_erro_com_o_motivo(monkeypatch):
    con = banco()
    pago(con)

    def quebra(*_a, **_k):
        raise RuntimeError("banco indisponível no teste")

    monkeypatch.setattr(REP, "gerar_guias_do_dia", quebra)
    r = RA.gerar_a_relacao_do_dia(_contexto(con, pode_agir=True))
    assert r["situacao"] == "ERRO"
    assert "NÃO foi gerada" in r["relato"]
    assert "banco indisponível no teste" in r["erro"]


def test_a_rotina_esta_no_catalogo_da_automacao():
    import automacao as AU
    import automacao_processos as PROC
    assert "protesto_repasse_automacao" in PROC.MODULOS_COM_PROCESSOS
    [semente] = [s for s in PROC.sementes_de_outros_modulos()
                 if s["codigo"] == RA.CODIGO]
    assert semente["alvo"] == "protesto_repasse_automacao:gerar_a_relacao_do_dia"
    assert semente["alvo"] in AU.funcoes_permitidas()
    assert semente["agenda"]["horarios"] == ["08:00", "17:00"]


def test_a_rotina_nao_fala_com_rede_nem_com_central():
    fonte = (RAIZ / "protesto_repasse_automacao.py").read_text(encoding="utf-8")
    proibidos = r"^\s*(?:import|from)\s+(requests|urllib|http|socket|cenprot_api|" \
                r"cra21_api|resolve_api|centrais_cred|automacao_cofre)\b"
    assert not re.search(proibidos, fonte, re.MULTILINE)


# ------------------------------------------------------------- a tela


@pytest.fixture()
def s(cg_casa_logada):
    cg_casa_logada["db"].set_settings({"modulo_protesto_ligado": "1"})
    return cg_casa_logada


def _pago_na_tela(s, *, origem="CENPROT", chave="GRW:1") -> dict:
    with s["db"].transaction() as con:
        return pago(con, origem=origem, chave=chave,
                    numero=chave.replace(":", "/"))


def _token(s) -> str:
    html = s["c"].get("/protesto/repasses").get_data(as_text=True)
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


def test_a_tela_mostra_o_que_falta_e_onde_a_guia_se_emite(s):
    _pago_na_tela(s)
    html = s["c"].get("/protesto/repasses").get_data(as_text=True)
    assert "O que falta para o repasse sair" in html
    assert "Onde a guia se emite" in html
    assert "no portal da CENPROT" in html
    assert "Rotina automática da relação" in html


def test_o_botao_gera_as_relacoes_do_dia_e_o_titulo_continua_pendente(s):
    _pago_na_tela(s)
    _pago_na_tela(s, origem="CRA", chave="GRW:2")
    r = s["c"].post("/protesto/repasses/guias/do-dia",
                    data={"csrf_token": _token(s)}, follow_redirects=True)
    html = r.get_data(as_text=True)
    assert "Relação gerada" in html
    assert "falta emitir e registrar" in html
    with s["db"].connect() as con:
        rastro = nativo(con).ler(
            "SELECT details FROM audit_logs WHERE action=%s ORDER BY id",
            ("PROTESTO_REPASSE_GUIA_GERADA",))
    assert sorted(json.loads(x["details"])["central"] for x in rastro) == [
        "CENPROT", "CRA"]
    assert all("DEVEDOR" not in (x["details"] or "") for x in rastro)


def test_o_csv_leva_a_etapa_e_a_guia_nao_paga(s):
    _pago_na_tela(s)
    s["c"].post("/protesto/repasses/guias/do-dia",
                data={"csrf_token": _token(s)})
    texto = s["c"].get("/protesto/repasses/pendencias.csv").get_data().decode(
        "utf-8-sig")
    assert texto.splitlines()[0].endswith('"ETAPA"')
    assert '"GUIA_GERADA"' in texto


def test_sem_csrf_o_botao_nao_gera(s):
    _pago_na_tela(s)
    r = s["c"].post("/protesto/repasses/guias/do-dia", data={})
    assert r.status_code in (400, 403)
    with s["db"].connect() as con:
        assert nativo(con).ler("SELECT id FROM pt_repasse_guias") == []
