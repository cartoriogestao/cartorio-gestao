"""
Testes da certidão diária em forma de relação (LG05) — CN-MA art. 949.

O QUE ELES CONFEREM
      - a relação traz os protestos lavrados e os cancelamentos do dia, uma
        linha por devedor, com o aviso de informação reservada;
      - o dia sem nada gera certidão NEGATIVA (§ 5º);
      - só recebe entidade habilitada, e não de dia anterior à habilitação
        (§ 1º); a suspensa não recebe (§ 3º);
      - a relação é do dia que já fechou, e a segunda pedida devolve a
        primeira, com o mesmo teor;
      - o protesto com os efeitos suspensos por ordem judicial não entra;
      - a entrega exige comprovante e não se repete;
      - o envio pela CENPROT nasce DESLIGADO; em homologação o serviço FALSO
        recebe e não conta como entrega; em produção registra a entrega; o
        transporte de verdade recusa sem rede.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import protesto as PT                            # noqa: E402
import protesto_relacao as REL                   # noqa: E402
from bd_nativo import banco as nativo            # noqa: E402
from nucleo_schema import init_nucleo_schema     # noqa: E402
from pt_schema import init_pt_schema             # noqa: E402

DIA = "2026-10-15"
LAVRADO = DIA + "T15:00:00"
HOJE = "2026-10-16"
AGORA = HOJE + "T09:00:00"
EXTENSO = "quinze dias do mês de outubro do ano de dois mil e vinte e seis"
SV = {"unit_name": "SERVENTIA DE TESTE", "serventia_titular": "TABELIÃO DE TESTE",
      "serventia_titulo": "Tabelião", "ri_cns": "000000",
      "ri_cidade": "Cidade Exemplo", "ri_uf": "MA"}
# CNPJ fictício que confere pelo dígito — não é de ninguém de verdade.
CNPJ = "00000043000177"


def banco():
    con = conexao_de_teste()
    init_nucleo_schema(con)
    init_pt_schema(con)
    nativo(con).escrever(
        "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    return con


def protestado(con, *, chave="REL:1", devedores=1) -> int:
    d = {"especie": "DMI", "numero_titulo": chave.replace(":", "/"),
         "data_emissao": "2026-07-21", "data_vencimento": "2026-09-05",
         "valor": "500.00", "saldo": "500.00", "praca_protesto": "CIDADE EXEMPLO",
         "tipo_moeda": "1", "tipo_protesto": "C", "motivo_protesto": "1",
         "cedente": {"nome": "CREDOR FICTICIO", "documento": "00000000000000",
                     "cidade": "Cidade Exemplo", "uf": "MA"},
         "devedores": [{"nome": f"DEVEDOR FICTICIO {i}", "CPF": f"0000000000{i}",
                        "enderecos": [{"endereco": "Rua X", "bairro": "Centro",
                                       "cidade": "Cidade Exemplo", "uf": "MA"}]}
                       for i in range(1, devedores + 1)]}
    tid = PT.cadastrar_titulo(con, d, origem="CRA", origem_chave=chave,
                              agora="2026-10-10T09:00:00")
    PT.lancar_apontamento(con, tid, sv=SV, agora="2026-10-10T09:00:00",
                          data_extenso=EXTENSO)
    PT.lancar_intimacao(con, tid, modo="PESSOAL", agora="2026-10-11T09:00:00")
    PT.lancar_protesto(con, tid, sv=SV, agora=LAVRADO, data_extenso=EXTENSO)
    return tid


def entidade(con, *, canal="DIRETO", desde="2026-10-01") -> int:
    return REL.habilitar_entidade(
        con, nome="ENTIDADE DE CRÉDITO FICTÍCIA", documento=CNPJ, canal=canal,
        habilitacao="Requerimento 12/2026, deferido", habilitada_em=desde,
        agora=AGORA)


def ligar(con, modo: str) -> None:
    nativo(con).escrever(
        """INSERT INTO settings(key, value) VALUES (%s,%s)
           ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value""",
        (REL.CHAVE_DO_ENVIO, modo))


# -------------------------------------------------------------- a relação


def test_a_relacao_traz_o_protesto_do_dia_uma_linha_por_devedor():
    con = banco()
    protestado(con, devedores=2)
    ent = entidade(con)
    r = REL.gerar_relacao(con, dia=DIA, entidade_id=ent, hoje=HOJE, agora=AGORA,
                          sv=SV)
    rel = REL.relacao(con, r["relacao_id"])
    assert (rel["protestos"], rel["cancelamentos"], rel["registros"]) == (1, 0, 1)
    assert "DEVEDOR FICTICIO 1" in rel["teor"] and "DEVEDOR FICTICIO 2" in rel["teor"]
    assert REL.AVISO_DE_RESERVA in rel["teor"]
    assert rel["negativa"] == 0


def test_o_cancelamento_do_dia_entra_com_a_letra_c():
    con = banco()
    tid = protestado(con)
    PT.lancar_cancelamento(con, tid, hipotese="PAGAMENTO",
                           fundamento="Quitado, com o título original.",
                           agora="2026-10-14T10:00:00")
    ent = entidade(con)
    r = REL.gerar_relacao(con, dia="2026-10-14", entidade_id=ent, hoje=HOJE,
                          agora=AGORA, sv=SV)
    rel = REL.relacao(con, r["relacao_id"])
    assert rel["cancelamentos"] == 1
    assert "\nC;14/10/2026;" in rel["teor"]


def test_o_vencimento_vai_na_ultima_coluna_e_as_de_antes_nao_mudam_de_lugar():
    """CNN art. 130 pede a data do vencimento, e o LD04 a pôs no MEIO da
    relação: a entidade que a lê por posição passava a ler a data no lugar do
    valor. Desde o LD11 as oito colunas de antes ficam onde estavam, e o
    vencimento vai no fim."""
    con = banco()
    protestado(con)
    ent = entidade(con)
    r = REL.gerar_relacao(con, dia=DIA, entidade_id=ent, hoje=HOJE, agora=AGORA,
                          sv=SV)
    linhas = REL.relacao(con, r["relacao_id"])["teor"].splitlines()
    cabeca = linhas.index("TIPO;DIA;PROTOCOLO;ESPECIE;TITULO;VALOR;DEVEDOR;"
                          "DOCUMENTO;VENCIMENTO")
    campos = linhas[cabeca + 1].split(";")
    assert campos[:2] == ["P", "15/10/2026"]
    assert campos[3:] == ["DMI", "REL/1", "500,00", "DEVEDOR FICTICIO 1",
                          "00000000001", "05/09/2026"]


def test_dia_sem_protesto_nem_cancelamento_gera_certidao_negativa():
    con = banco()
    ent = entidade(con)
    r = REL.gerar_relacao(con, dia=DIA, entidade_id=ent, hoje=HOJE, agora=AGORA,
                          sv=SV)
    assert r["negativa"] is True
    assert "CERTIDÃO NEGATIVA" in REL.relacao(con, r["relacao_id"])["teor"]


def test_a_relacao_de_hoje_nao_se_gera():
    con = banco()
    ent = entidade(con)
    with pytest.raises(REL.RelacaoError, match="já fechou"):
        REL.gerar_relacao(con, dia=HOJE, entidade_id=ent, hoje=HOJE,
                          agora=AGORA, sv=SV)


def test_a_segunda_pedida_devolve_a_primeira_com_o_mesmo_teor():
    con = banco()
    protestado(con)
    ent = entidade(con)
    a = REL.gerar_relacao(con, dia=DIA, entidade_id=ent, hoje=HOJE, agora=AGORA,
                          sv=SV)
    protestado(con, chave="REL:2")           # lavrado depois, no mesmo dia
    b = REL.gerar_relacao(con, dia=DIA, entidade_id=ent, hoje=HOJE, agora=AGORA,
                          sv=SV)
    assert b["ja_existia"] is True and b["relacao_id"] == a["relacao_id"]
    assert b["registros"] == 1


def test_dia_anterior_a_habilitacao_nao_e_da_entidade():
    con = banco()
    ent = entidade(con, desde="2026-10-16")
    with pytest.raises(REL.RelacaoError, match="§ 1º"):
        REL.gerar_relacao(con, dia=DIA, entidade_id="%d" % ent, hoje="2026-10-17",
                          agora=AGORA, sv=SV)


def test_entidade_suspensa_nao_recebe():
    con = banco()
    ent = entidade(con)
    REL.suspender_entidade(con, ent, motivo="Divulgou protesto cancelado",
                           agora=AGORA)
    with pytest.raises(REL.RelacaoError, match="§ 3º"):
        REL.gerar_relacao(con, dia=DIA, entidade_id=ent, hoje=HOJE, agora=AGORA,
                          sv=SV)


def test_protesto_com_efeitos_suspensos_nao_entra_na_relacao():
    """A relação diária (Lei 9.492, art. 29) continua sem o suspenso, MESMO
    por decisão provisória: o CNN art. 263-K, que o oficial passou a seguir em
    21/10/2026 (LH13), é regra da CERTIDÃO a terceiro — a «sustação judicial
    precária» sai nela, e não na relação às entidades de proteção ao crédito."""
    con = banco()
    tid = protestado(con)
    PT.lancar_efeito_suspensivo(con, tid, juizo="Vara de teste",
                                processo="0000000-00.2026.8.10.0000",
                                carater="PROVISORIA", agora=LAVRADO)
    ent = entidade(con)
    r = REL.gerar_relacao(con, dia=DIA, entidade_id=ent, hoje=HOJE, agora=AGORA,
                          sv=SV)
    assert r["suspensos"] == 1 and r["registros"] == 0
    assert "efeitos suspensos" in REL.relacao(con, r["relacao_id"])["teor"]


def test_cnpj_que_nao_confere_nao_se_habilita():
    con = banco()
    with pytest.raises(REL.RelacaoError, match="dígito"):
        REL.habilitar_entidade(con, nome="ENTIDADE", documento="11222333000100",
                               canal="DIRETO", habilitacao="Requerimento 1",
                               habilitada_em="2026-10-01", agora=AGORA)


def test_habilitar_sem_dizer_a_habilitacao_e_recusado():
    con = banco()
    with pytest.raises(REL.RelacaoError, match="§ 1º"):
        REL.habilitar_entidade(con, nome="ENTIDADE", documento=CNPJ,
                               canal="DIRETO", habilitacao="",
                               habilitada_em="2026-10-01", agora=AGORA)


def test_os_dias_uteis_sem_relacao_aparecem_no_controle():
    con = banco()
    ent = entidade(con, desde="2026-10-13")
    REL.gerar_relacao(con, dia="2026-10-13", entidade_id=ent, hoje=HOJE,
                      agora=AGORA, sv=SV)
    [falta] = REL.dias_sem_relacao(con, hoje=HOJE)
    assert falta["dias"] == ["2026-10-14", "2026-10-15"]


# --------------------------------------------------------------- a entrega


def test_a_entrega_exige_comprovante_e_nao_se_repete():
    con = banco()
    ent = entidade(con)
    r = REL.gerar_relacao(con, dia=DIA, entidade_id=ent, hoje=HOJE, agora=AGORA,
                          sv=SV)
    with pytest.raises(REL.RelacaoError, match="comprovante"):
        REL.registrar_entrega(con, r["relacao_id"], forma="EMAIL",
                              comprovante="", entregue_em=HOJE, agora=AGORA)
    REL.registrar_entrega(con, r["relacao_id"], forma="EMAIL",
                          comprovante="E-mail de 16/10, 9h12", entregue_em=HOJE,
                          agora=AGORA)
    assert REL.a_entregar(con) == []
    with pytest.raises(REL.RelacaoError, match="já foi entregue"):
        REL.registrar_entrega(con, r["relacao_id"], forma="EMAIL",
                              comprovante="outra", entregue_em=HOJE, agora=AGORA)


# ----------------------------------------------------------------- o envio


def _relacao_cenprot(con) -> int:
    ent = entidade(con, canal="CENPROT")
    return REL.gerar_relacao(con, dia=DIA, entidade_id=ent, hoje=HOJE,
                             agora=AGORA, sv=SV)["relacao_id"]


def test_o_envio_nasce_desligado_e_nao_toca_no_transporte():
    con = banco()
    rid = _relacao_cenprot(con)
    falso = REL.TransporteFalso()
    assert REL.modo_de_envio(con) == "DESLIGADO"
    with pytest.raises(REL.RelacaoError, match="desligado"):
        REL.enviar(con, rid, transporte=falso, agora=AGORA)
    assert falso.enviados == []


def test_configuracao_estragada_nao_liga_o_envio():
    con = banco()
    ligar(con, "SIM")
    assert REL.modo_de_envio(con) == "DESLIGADO"


def test_em_homologacao_o_servico_falso_recebe_e_nao_conta_como_entrega():
    con = banco()
    rid = _relacao_cenprot(con)
    ligar(con, "HOMOLOGACAO")
    falso = REL.TransporteFalso()
    r = REL.enviar(con, rid, transporte=falso, agora=AGORA)
    assert r["entregue"] is False and r["protocolo"] == "FALSO-1"
    assert falso.enviados[0]["ambiente"] == "HOMOLOGACAO"
    assert REL.relacao(con, rid)["entregue_em"] is None


def test_em_producao_o_envio_registra_a_entrega_com_o_protocolo():
    con = banco()
    rid = _relacao_cenprot(con)
    ligar(con, "PRODUCAO")
    REL.enviar(con, rid, transporte=REL.TransporteFalso(), agora=AGORA)
    rel = REL.relacao(con, rid)
    assert (rel["forma_entrega"], rel["comprovante_entrega"]) == ("CENPROT", "FALSO-1")


def test_entidade_de_entrega_direta_nao_vai_pela_cenprot():
    con = banco()
    ent = entidade(con)
    rid = REL.gerar_relacao(con, dia=DIA, entidade_id=ent, hoje=HOJE,
                            agora=AGORA, sv=SV)["relacao_id"]
    ligar(con, "PRODUCAO")
    with pytest.raises(REL.RelacaoError, match="recebe direto"):
        REL.enviar(con, rid, transporte=REL.TransporteFalso(), agora=AGORA)


def test_o_transporte_de_verdade_recusa_sem_credencial_e_sem_rede(tmp_path,
                                                                  monkeypatch):
    import centrais_cred as CENTCRED
    monkeypatch.setattr(CENTCRED, "pasta_de_dados", lambda: tmp_path)
    con = banco()
    rid = _relacao_cenprot(con)
    ligar(con, "PRODUCAO")
    with pytest.raises(REL.RelacaoError, match="Sem credencial"):
        REL.enviar(con, rid, transporte=REL.TransporteCenprot(), agora=AGORA)


def test_a_homologacao_da_cenprot_de_verdade_segue_a_ordem_de_so_producao():
    con = banco()
    rid = _relacao_cenprot(con)
    ligar(con, "HOMOLOGACAO")
    with pytest.raises(REL.RelacaoError, match="só em produção"):
        REL.enviar(con, rid, transporte=REL.TransporteCenprot(), agora=AGORA)
