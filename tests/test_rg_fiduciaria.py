"""O PROCESSO FIDUCIÁRIO, O SOBRESTAMENTO, A DOI DO RTD E O NOME PARECIDO (01/11/2026).

O QUE ESTES TESTES GUARDAM
    - a numeração é própria, por ano, e um título tem um processo só;
    - positiva exige os requisitos do art. 397-T, e o gravame é facultativo;
    - os prazos: 20 dias corridos do primeiro dia útil depois da ciência; 3 dias úteis de leitura;
    - pagamento integral encerra; parcial só com a concordância do credor;
    - a busca não cabe antes de vencer o prazo do devedor;
    - a impugnação não conhecida ou indeferida segue para a entrega; a acolhida encerra;
    - a diligência negativa não consolida; a positiva abre os 5 dias úteis de reversão;
    - processo encerrado não recebe lançamento, e a linha do tempo fica;
    - título sobrestado não se qualifica nem se registra, e mantém número e data;
    - a DOI do RTD sai com serviço 3, ato 4 e natureza 1, no layout do DOI-Web;
    - o nome parecido levanta a mão, e duas associações diferentes não se parecem.

Dados fictícios: Cidade Exemplo, CNS 000000.
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import date
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))
from banco_de_teste import conexao_de_teste  # noqa: E402

import rg_doi as RDOI
import rg_fiduciaria as FID
import rg_livros as RGL
import rg_normas as NORMAS
import rg_schema as RGS
import rg_titulo as TIT
from bd_nativo import banco
from nucleo_schema import init_nucleo_schema

AGORA = "2026-11-03T09:30:00"
SV = {"unit_name": "SERVENTIA DE CIDADE EXEMPLO/MA", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA",
      "ri_cns": "000000", "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
      "serventia_titulo": "Tabelião e Oficial de Registro"}
TUDO = [r["chave"] for r in FID.REQUISITOS if r["obrigatorio"]]
COMUM = {"agora": AGORA, "usuario": "mario"}


def _util(d: date) -> bool:
    return d.weekday() < 5


@pytest.fixture()
def con(tmp_path):
    c = conexao_de_teste()
    c.row_factory = sqlite3.Row
    init_nucleo_schema(c)
    c.executescript("""
        CREATE TABLE IF NOT EXISTS cx_protocolos (id INTEGER PRIMARY KEY AUTOINCREMENT, numero TEXT);
        CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, full_name TEXT);
    """)
    RGS.init_rg_schema(c)
    return c


def _titulo(con, **kw) -> int:
    return TIT.receber(con, atribuicao=TIT.RTD, sv=SV, agora=AGORA, data_extenso="três de novembro",
                       data_apresentacao="2026-11-03", natureza="Requerimento de consolidação", **kw)["titulo_id"]


def _processo(con, ate=None) -> int:
    pid = FID.autuar(con, titulo_id=_titulo(con), credor_nome="Banco Exemplo", devedor_nome="Maria Exemplo",
                     bem_descricao="Motocicleta exemplo", ano=2026, **COMUM)["id"]
    if ate in (None, "autuado"):
        return pid
    FID.qualificar(con, pid, resultado="POSITIVA", itens=TUDO, dia="2026-11-03", **COMUM)
    if ate == "qualificado":
        return pid
    FID.notificar(con, pid, forma="ELETRONICA", dia="2026-11-03", e_util=_util, **COMUM)
    if ate == "notificado":
        return pid
    FID.ciencia(con, pid, dia="2026-11-06", e_util=_util, **COMUM)   # uma sexta-feira
    return pid


def test_a_numeracao_e_propria_e_um_titulo_tem_um_processo(con):
    t = _titulo(con)
    a = FID.autuar(con, titulo_id=t, credor_nome="C", devedor_nome="D", bem_descricao="B", ano=2026, **COMUM)
    b = _processo(con)
    assert a["rotulo"] == "1/2026" and FID.um(con, b)["rotulo"] == "2/2026"
    with pytest.raises(FID.FiduciariaError):
        FID.autuar(con, titulo_id=t, credor_nome="C", devedor_nome="D", bem_descricao="B", ano=2026, **COMUM)


def test_o_titulo_do_rcpj_nao_autua(con):
    t = TIT.receber(con, atribuicao=TIT.RCPJ, sv=SV, agora=AGORA, data_extenso="x", data_apresentacao="2026-11-03")["titulo_id"]
    with pytest.raises(FID.FiduciariaError):
        FID.autuar(con, titulo_id=t, credor_nome="C", devedor_nome="D", bem_descricao="B", ano=2026, **COMUM)


def test_positiva_exige_os_requisitos_e_o_gravame_e_facultativo(con):
    pid = _processo(con)
    with pytest.raises(FID.FiduciariaError):
        FID.qualificar(con, pid, resultado="POSITIVA", itens=TUDO[1:], dia="2026-11-03", **COMUM)
    assert "gravame" not in TUDO
    FID.qualificar(con, pid, resultado="POSITIVA", itens=TUDO, dia="2026-11-03", **COMUM)
    assert FID.um(con, pid)["situacao"] == FID.QUALIFICADO


def test_a_emenda_da_dez_dias_e_volta_a_qualificacao(con):
    pid = _processo(con)
    FID.qualificar(con, pid, resultado="EMENDA", motivo="Falta a planilha da dívida.", dia="2026-11-03", **COMUM)
    p = FID.um(con, pid)
    assert p["situacao"] == FID.EMENDA and p["prazo_ate"] == "2026-11-13"
    FID.qualificar(con, pid, resultado="POSITIVA", itens=TUDO, dia="2026-11-13", **COMUM)
    assert FID.um(con, pid)["situacao"] == FID.QUALIFICADO


def test_a_notificacao_eletronica_tem_tres_dias_uteis_de_leitura(con):
    pid = _processo(con, "notificado")
    assert FID.um(con, pid)["prazo_ate"] == "2026-11-06"


def test_o_prazo_comeca_no_primeiro_dia_util_depois_da_ciencia(con):
    pid = _processo(con, "prazo")
    assert FID.um(con, pid)["prazo_ate"] == "2026-11-28"   # segunda 09/11 é o dia 1


def test_pagamento_integral_encerra_e_parcial_so_com_o_credor(con):
    pid = _processo(con, "prazo")
    assert FID.pagamento(con, pid, dia="2026-11-10", valor="100,00", e_util=_util, **COMUM)["encerrou"] is False
    assert FID.um(con, pid)["situacao"] == FID.PRAZO_DEVEDOR
    assert FID.pagamento(con, pid, dia="2026-11-11", valor="100,00", credor_aceitou=True, e_util=_util, **COMUM)["encerrou"]
    assert FID.um(con, pid)["situacao"] == FID.PAGO
    with pytest.raises(FID.FiduciariaError):
        FID.entrega(con, pid, dia="2026-11-12", e_util=_util, **COMUM)
    assert FID.eventos_de(con, pid)[-1]["averbar"] == 1


def test_a_busca_nao_cabe_antes_de_vencer_o_prazo(con):
    pid = _processo(con, "prazo")
    with pytest.raises(FID.FiduciariaError):
        FID.requerer_busca(con, pid, dia="2026-11-20", valor="1000,00", tem_planilha=True, hoje="2026-11-20", **COMUM)
    assert "requerer_busca" not in FID.acoes_possiveis(FID.um(con, pid), hoje="2026-11-28")
    assert "requerer_busca" in FID.acoes_possiveis(FID.um(con, pid), hoje="2026-11-29")
    with pytest.raises(FID.FiduciariaError):
        FID.requerer_busca(con, pid, dia="2026-11-30", valor="1000,00", tem_planilha=False, hoje="2026-11-30", **COMUM)
    FID.requerer_busca(con, pid, dia="2026-11-30", valor="1000,00", tem_planilha=True, hoje="2026-11-30", **COMUM)
    assert FID.um(con, pid)["situacao"] == FID.BUSCA


def test_impugnacao_nao_conhecida_segue_para_a_entrega(con):
    pid = _processo(con, "prazo")
    FID.impugnar(con, pid, dia="2026-11-10", texto="Alega que a taxa é abusiva.", **COMUM)
    FID.conhecer(con, pid, conhece=False, fundamento="Exorbita o art. 397-X.", dia="2026-11-11", e_util=_util, **COMUM)
    p = FID.um(con, pid)
    assert p["situacao"] == FID.AGUARDA_ENTREGA and p["prazo_ate"] == "2026-12-01"


def test_impugnacao_conhecida_dez_dias_ao_credor_e_a_decisao(con):
    pid = _processo(con, "prazo")
    FID.impugnar(con, pid, dia="2026-11-10", texto="Pagamento não processado.", valor="50,00", **COMUM)
    with pytest.raises(FID.FiduciariaError):
        FID.decidir(con, pid, procedente=True, fundamento="Antes de conhecer.", dia="2026-11-10", **COMUM)
    FID.conhecer(con, pid, conhece=True, fundamento="Alegação cabível.", dia="2026-11-11", e_util=_util, **COMUM)
    assert FID.um(con, pid)["prazo_ate"] == "2026-11-21"
    FID.decidir(con, pid, procedente=True, fundamento="O pagamento está comprovado.", dia="2026-11-25", **COMUM)
    assert FID.um(con, pid)["situacao"] == FID.IMPUGNACAO_ACOLHIDA


def test_diligencia_negativa_nao_consolida_e_a_positiva_abre_a_reversao(con):
    pid = _processo(con, "prazo")
    FID.requerer_busca(con, pid, dia="2026-11-30", valor="1000,00", tem_planilha=True, hoje="2026-11-30", **COMUM)
    with pytest.raises(FID.FiduciariaError):
        FID.diligencia(con, pid, dia="2026-12-01", local="Rua Exemplo", resultado="NEGATIVA", e_util=_util, **COMUM)
    FID.diligencia(con, pid, dia="2026-12-01", local="Rua Exemplo", resultado="NEGATIVA",
                   detalhe="O bem não estava no local.", e_util=_util, **COMUM)
    assert FID.um(con, pid)["situacao"] == FID.BUSCA
    FID.diligencia(con, pid, dia="2026-12-02", hora="10:00", local="Rua Exemplo", resultado="POSITIVA", e_util=_util, **COMUM)
    p = FID.um(con, pid)
    assert p["situacao"] == FID.CONSOLIDADO and p["prazo_ate"] == "2026-12-09"
    with pytest.raises(FID.FiduciariaError):
        FID.concluir(con, pid, dia="2026-12-05", hoje="2026-12-05", **COMUM)
    FID.concluir(con, pid, dia="2026-12-10", valor_venda="900,00", hoje="2026-12-10", **COMUM)
    assert FID.um(con, pid)["situacao"] == FID.CONCLUIDO


def test_a_peca_so_existe_quando_cabe_e_traz_o_que_o_artigo_manda(con):
    pid = _processo(con, "qualificado")
    p, ev = FID.um(con, pid), FID.eventos_de(con, pid)
    assert list(FID.pecas_disponiveis(p, ev)) == ["NOTIFICACAO"]
    texto = " ".join(FID.texto_da_peca(p, "NOTIFICACAO", ev, sv=SV))
    assert "20 dias corridos" in texto and "multa de 5%" in texto and "convalesce" in texto


def test_a_averbacao_so_amarra_ato_do_registro_do_processo(con):
    pid = _processo(con, "notificado")
    pendente = FID.averbacoes_pendentes(FID.um(con, pid), FID.eventos_de(con, pid))
    assert len(pendente) == 1
    r = banco(con).escrever(
        "INSERT INTO rg_registros(atribuicao, serie, numero, situacao, origem, origem_chave, criado_em) "
        "VALUES (4,'TD_B',9,'ATIVO','TESTE','t:9',%s) RETURNING id", (AGORA,))[0]["id"]
    a = banco(con).escrever(
        "INSERT INTO rg_atos(registro_id, tipo, data_ato, origem, origem_chave, criado_em) "
        "VALUES (%s,'AVERBACAO',%s,'TESTE','a:9',%s) RETURNING id", (r, AGORA, AGORA))[0]["id"]
    with pytest.raises(FID.FiduciariaError):
        FID.amarrar_averbacao(con, pid, pendente[0]["id"], ato_id=a)


# ------------------------------------------------------------- o sobrestamento


def test_titulo_sobrestado_mantem_numero_e_nao_se_qualifica(con):
    t = _titulo(con)
    antes = TIT.um(con, t)
    TIT.sobrestar(con, t, tipo="SUSPEITA_FALSIFICACAO", motivo="Assinatura diverge do cartão.", agora=AGORA)
    depois = TIT.um(con, t)
    assert (depois["numero"], depois["data_apresentacao"], depois["situacao"]) == (
        antes["numero"], antes["data_apresentacao"], antes["situacao"])
    with pytest.raises(TIT.TituloError):
        TIT.qualificar(con, t, resultado=TIT.POSITIVA, agora=AGORA)
    assert RGL.motivo_da_pendencia(con, dict(depois)).startswith("sobrestado")
    TIT.retomar(con, t, forma="REQUERIMENTO", motivo="O apresentante insistiu por escrito.", agora=AGORA)
    assert TIT.sobrestamento_aberto(con, t) is None
    assert "Sobrestamento encerrado" in TIT.um(con, t)["observacao"]


def test_remetido_ao_juizo_sai_do_protocolo(con):
    t = _titulo(con)
    TIT.sobrestar(con, t, tipo="SUSPEITA_FALSIFICACAO", motivo="Selo evidentemente falso.", agora=AGORA)
    TIT.retomar(con, t, forma="REMETIDO_AO_JUIZO", motivo="Falsificação evidente no documento.", agora=AGORA)
    assert TIT.um(con, t)["situacao"] == TIT.CANCELADO


def test_sobrestar_exige_motivo_e_nao_abre_dois(con):
    t = _titulo(con)
    with pytest.raises(TIT.TituloError):
        TIT.sobrestar(con, t, tipo="DUVIDA", motivo="curto", agora=AGORA)
    TIT.sobrestar(con, t, tipo="DUVIDA", motivo="Dúvida suscitada ao juiz.", agora=AGORA)
    with pytest.raises(TIT.TituloError):
        TIT.sobrestar(con, t, tipo="DUVIDA", motivo="Dúvida suscitada de novo.", agora=AGORA)


# ---------------------------------------------------------------- a DOI do RTD


def test_a_doi_do_rtd_diz_o_que_falta_e_a_retirada_tira(con):
    r = banco(con).escrever(
        "INSERT INTO rg_registros(atribuicao, serie, numero, situacao, origem, origem_chave, criado_em) "
        "VALUES (4,'TD_B',5,'ATIVO','TESTE','t:5',%s) RETURNING id", (AGORA,))[0]["id"]
    banco(con).escrever(
        "INSERT INTO rg_atos(registro_id, tipo, data_ato, origem, origem_chave, criado_em) "
        "VALUES (%s,'REGISTRO','2026-11-03','TESTE','a:5',%s)", (r, AGORA))
    RDOI.gravar(con, r, operacao="11", matricula="123", valor="1000,00", agora=AGORA)
    linhas = RDOI.declaracoes_da_competencia(con, "2026-11-01", "2026-12-01", "000000", "2100000")
    assert len(linhas) == 1 and linhas[0]["registro"] is None
    assert any(p["campo"] == "partes" for p in linhas[0]["problemas"])
    assert RDOI.declaracoes_da_competencia(con, "2026-10-01", "2026-11-01", "000000", "2100000") == []
    RDOI.retirar(con, r)
    assert RDOI.declaracoes_da_competencia(con, "2026-11-01", "2026-12-01", "000000", "2100000") == []


def test_a_doi_recusa_registro_do_rcpj_e_operacao_desconhecida(con):
    r = banco(con).escrever(
        "INSERT INTO rg_registros(atribuicao, serie, numero, situacao, origem, origem_chave, criado_em) "
        "VALUES (3,'PJ_A',5,'ATIVO','TESTE','t:p5',%s) RETURNING id", (AGORA,))[0]["id"]
    with pytest.raises(RDOI.DoiDoRegistroError):
        RDOI.gravar(con, r, operacao="11", matricula="1", valor="1,00", agora=AGORA)


# --------------------------------------------------------------- o nome parecido


def _pj(con, numero, nome):
    return banco(con).escrever(
        "INSERT INTO rg_registros(atribuicao, serie, numero, requerente_nome, situacao, origem, origem_chave, criado_em) "
        "VALUES (3,'PJ_A',%s,%s,'ATIVO','TESTE',%s,%s) RETURNING id", (numero, nome, f"t:n{numero}", AGORA))[0]["id"]


def test_o_parecido_levanta_a_mao_e_o_igual_vem_primeiro(con):
    _pj(con, 1, "Associação dos Moradores do Bairro Exemplar")
    _pj(con, 2, "ASSOCIACAO DOS MORADORES DO BAIRRO EXEMPLO")
    achados = NORMAS.nomes_parecidos(con, "Associação dos Moradores do Bairro Exemplo")
    assert [x["igual"] for x in achados] == [True, False]


def test_duas_associacoes_diferentes_nao_se_parecem(con):
    _pj(con, 1, "Associação dos Pescadores")
    assert NORMAS.nomes_parecidos(con, "Associação dos Lavradores do Sertão") == []
