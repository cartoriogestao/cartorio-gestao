"""
O ROTEIRO DAS CENTRAIS — o que a escrevente faz, e a cobranca de cada conduta.

Dois papeis, de 01/09/2026: o **Roteiro das Centrais de Protesto** do TJMA e o
**Oficio Circular IEPTB-MA/CRA-MA n. 015/2025**. E a ordem do oficial de
29/10/2026: *«ter apenas itens necessarios [...] e vincular a operacao»*, *«vincular
cada obrigacao a uma conduta»*.

O QUE ESTES TESTES GUARDAM
      - os QUATRO HORARIOS da CRA, com a hora exata do papel;
      - **todo passo do papel vai para uma conduta ou sai com a prova** — passo
        sem destino seria passo esquecido; e so saiu o que o sistema faz
        sozinho (a imagem, a confirmacao, o andamento do apontamento);
      - cada conduta tem o botao que leva a tela que FAZ, e cada uma e cobrada;
      - **ATRASADO SO SAI COM PRAZO PROVADO**: a hora do papel (11:30, 14:10)
        ou o prazo da norma. Sem prazo, pendente; sem tabela, sem medida — e
        nunca zero;
      - as obrigacoes dos erros de outubro (edital sem comprovante, entrega sem
        comprovante, protesto sem instrumento, XML que nao saiu) sao cobradas;
      - a tela e de LEITURA e esta aberta ao balcao.

O QUE MUDOU EM 29/10/2026, E POR QUE
    Ate aqui havia `test_o_zero_e_zero_e_nao_um_julgamento`, que varria os nomes
    publicos procurando «atrasado» e «pendente» para garantir que o modulo «nao
    julgava». A ordem do oficial e o contrario — a obrigacao e cobrada —, e o
    teste saiu. O que ele protegia continua guardado de outro jeito:
    `test_sem_prazo_nao_ha_atraso` e `test_remessa_sem_expediente_nunca_atrasa`.
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

import protesto_roteiro as PR  # noqa: E402

SENHA = "Senha#12345"
# DIAS DEPOIS DA VIRADA (14/10/2026): 28 e 29/10/2026 sao quarta e quinta, sem
# feriado nacional; 31/10/2026 e sabado.
ONTEM = "2026-10-28"
HOJE = "2026-10-29"
SABADO = "2026-10-31"


def _obrigacao(roteiro_ou_condutas, chave: str) -> dict:
    condutas = (roteiro_ou_condutas["condutas"]
                if isinstance(roteiro_ou_condutas, dict)
                else roteiro_ou_condutas)
    for c in condutas:
        for o in c["obrigacoes"]:
            if o["chave"] == chave:
                return o
    raise AssertionError(f"obrigacao {chave} nao existe")


def _conduta(condutas, chave: str) -> dict:
    return next(c for c in condutas if c["chave"] == chave)


# ------------------------------------------------------------- os horarios


def test_os_quatro_horarios_sao_os_do_papel():
    horas = {h["o_que"]: h["hora"] for h in PR.HORARIOS_DA_CRA}
    assert horas == {"Envio de remessa": "12:30",
                     "Envio de confirmacao": "14:10",
                     "Envio de retorno": "11:30",
                     "Andamento": "11:30"}
    assert (PR.HORA_DO_RETORNO, PR.HORA_DA_CONFIRMACAO, PR.HORA_DA_REMESSA) == (
        "11:30", "14:10", "12:30")


def test_tres_dos_quatro_horarios_sao_de_arquivo_que_SAI_daqui():
    nossos = [h["o_que"] for h in PR.HORARIOS_DA_CRA if h["nosso"]]
    assert nossos == ["Envio de confirmacao", "Envio de retorno", "Andamento"]


# ------------------------------------------------------------- o papel


def test_os_dois_papeis_continuam_com_os_dezesseis_passos():
    """O papel e a FONTE: nada dele se apaga — cada passo diz para onde foi."""
    assert len(PR.ROTEIRO_DA_CRA) == 8
    assert len(PR.ROTEIRO_DA_CENPROT) == 8


def test_todo_passo_do_papel_vai_para_uma_conduta_ou_sai_com_prova():
    """Passo sem destino seria passo esquecido; passo com dois, ambiguo."""
    condutas = {c["chave"] for c in PR.CONDUTAS_DO_DIA}
    fora = {f["chave"] for f in PR.FORA_DO_ROTEIRO}
    for p in PR.ROTEIRO_DA_CRA + PR.ROTEIRO_DA_CENPROT:
        destinos = [k for k in ("conduta", "fora") if p.get(k)]
        assert len(destinos) == 1, p["passo"]
        if p.get("conduta"):
            assert p["conduta"] in condutas, p["passo"]
        else:
            assert p["fora"] in fora, p["passo"]
    for c in PR.CONDUTAS_DO_DIA:
        assert any(p.get("conduta") == c["chave"]
                   for p in PR.ROTEIRO_DA_CRA + PR.ROTEIRO_DA_CENPROT
                   ) or c["chave"] in ("entregas", "protestos", "encerrar"), \
            c["chave"]


def test_so_saiu_o_que_o_sistema_faz_sozinho_e_cada_um_com_a_prova():
    """«tirar a parte de baixar imagem, que ja vem com a remessa ou a
    confirmacao que ja vai automatica» — e NADA alem do que tem prova."""
    assert {f["chave"] for f in PR.FORA_DO_ROTEIRO} == {
        "imagens", "confirmacao", "andamento_da_remessa"}
    for f in PR.FORA_DO_ROTEIRO:
        for campo in ("o_que", "por_que", "codigo", "medido"):
            assert str(f.get(campo) or "").strip(), (f["chave"], campo)
        assert "29/10/2026" in f["medido"]
    titulos = " | ".join(c["titulo"] for c in PR.CONDUTAS_DO_DIA).lower()
    assert "imagem" not in titulos and "imagens" not in titulos
    confirmacao = next(p for p in PR.ROTEIRO_DA_CRA
                       if p["passo"] == "Confirmacao de remessa")
    assert confirmacao.get("fora") == "confirmacao"


def test_a_confirmacao_saiu_do_roteiro_mas_continua_cobrada_quando_falha():
    """A excecao do automatico nao some: ela mora na conduta da remessa."""
    con = _casa_minima()
    condutas = PR.cobrar_o_dia(con, agora=HOJE + "T10:00:00")
    remessa = _conduta(condutas, "remessa")
    assert "confirmacoes_nao_aceitas" in {o["chave"] for o in remessa["obrigacoes"]}


def test_todo_passo_sem_tela_DIZ_onde_se_faz():
    for p in PR.ROTEIRO_DA_CRA + PR.ROTEIRO_DA_CENPROT:
        if not p.get("tela"):
            assert p.get("onde"), f"«{p['passo']}» nao diz onde se faz"


def test_nenhum_passo_aponta_para_tela_que_nao_existe():
    """A PROMESSA COM CARA DE PROVA. Procura em todo modulo que pendura rota."""
    telas = {p["tela"] for p in PR.ROTEIRO_DA_CRA + PR.ROTEIRO_DA_CENPROT
             if p.get("tela")}
    telas |= {b["tela"] for c in PR.CONDUTAS_DO_DIA for b in c["botoes"]}
    fontes = "".join(
        arq.read_text(encoding="utf-8", errors="replace")
        for arq in RAIZ.glob("*.py")
        if "registrar_rotas" in arq.read_text(encoding="utf-8",
                                              errors="replace"))
    for tela in sorted(telas):
        assert f"def {tela}(" in fontes, f"a rota «{tela}» nao existe"


def test_o_oficio_da_a_norma_de_quatro_passos_da_cenprot():
    com_norma = [p["passo"] for p in PR.ROTEIRO_DA_CENPROT if p.get("norma")]
    assert len(com_norma) == 4
    juntas = " ".join(p.get("norma", "") for p in PR.ROTEIRO_DA_CENPROT)
    assert "Resolucao n. 1 do IEPTB-BR" in juntas
    assert "Lei 9.492/1997" in juntas
    assert "Resolucao n. 8" in juntas and "Resolucao n. 9" in juntas


def test_o_cadastro_de_usuario_e_do_tabeliao():
    assert any("Tabeliao ou Substituto" in x for x in PR.SO_O_TABELIAO)


# ------------------------------------------------------------- as condutas


def test_as_obrigacoes_dos_erros_de_outubro_tem_conduta():
    chaves = [c["chave"] for c in PR.CONDUTAS_DO_DIA]
    for k in ("retorno", "remessa", "pedidos_cra", "entregas", "editais",
              "protestos", "instrumentos", "xml", "cenprot", "repasse",
              "encerrar"):
        assert k in chaves, k
    # ENCERRAR O DIA E A ULTIMA — ela confere todas as outras.
    assert chaves[-1] == "encerrar"
    assert [c["n"] for c in PR.CONDUTAS_DO_DIA] == list(
        range(1, len(PR.CONDUTAS_DO_DIA) + 1))
    n = {c["chave"]: c["n"] for c in PR.CONDUTAS_DO_DIA}
    # A ORDEM DO DIA: desistencia antes do protesto, e o protesto antes do
    # instrumento, que vai dentro do XML P.
    assert n["pedidos_cra"] < n["protestos"] < n["instrumentos"] < n["xml"]
    assert n["entregas"] < n["editais"] < n["protestos"]


def test_toda_conduta_tem_botao_e_e_cobrada():
    assert set(PR._COBRANCA_DA_CONDUTA) == {c["chave"]
                                            for c in PR.CONDUTAS_DO_DIA}
    for c in PR.CONDUTAS_DO_DIA:
        assert c["botoes"] and c["conduta"].strip(), c["chave"]
        for b in c["botoes"]:
            assert b["rotulo"].strip() and b["tela"].strip()


def test_os_links_das_centrais_pedem_producao():
    import centrais_cred as CRED
    assert PR.AMBIENTE_DE_PRODUCAO == CRED.PRODUCAO
    for c in PR.CONDUTAS_DO_DIA:
        for b in c["botoes"]:
            if b["tela"] == "protesto_pendencias":
                assert b["args"].get("ambiente") == CRED.PRODUCAO
    assert "HOMOLOG" not in json.dumps(PR.CONDUTAS_DO_DIA,
                                       ensure_ascii=False).upper()


def test_toda_tela_das_condutas_existe_e_aceita_os_argumentos(cg_casa):
    """Mais forte que procurar `def nome(`: monta o endereco de verdade."""
    from flask import url_for
    app = cg_casa["app"]
    with app.test_request_context():
        for c in PR.CONDUTAS_DO_DIA:
            for b in c["botoes"]:
                assert b["tela"] in app.view_functions, b["tela"]
                url_for(b["tela"], **b["args"])
        for tela, args in (("protesto_titulo", {"titulo_id": 1}),
                           ("protesto_desistencia", {"desistencia_id": 1}),
                           ("protesto_pendencia", {"pendencia_id": 1}),
                           ("protesto_retornos", {}),
                           ("protesto_instrumentos", {}),
                           ("protesto_repasses", {}),
                           ("protesto_avisos", {}),
                           ("protesto_remessas", {}),
                           ("protesto_cra_api", {}),
                           ("protesto_afirmacoes", {}), ("settings", {}),
                           ("protesto_encerrar_o_dia", {}),
                           ("nucleo_encerramento_diario", {})):
            url_for(tela, **args)


# ------------------------------------------------------------- a regua


def test_sem_prazo_nao_ha_atraso():
    """O VERMELHO E RESERVADO AO QUE O BANCO PROVA QUE PASSOU DA HORA."""
    from datetime import datetime
    ctx = {"agora": datetime(2026, 10, 29, 18, 0)}
    vencido = PR._item("x", prazo=datetime(2026, 10, 1, 9, 0), ctx=ctx)
    assert vencido["atrasado"]
    o = PR._obrigacao("k", "r", [vencido], regra="sem hora", tem_prazo=False)
    assert o["situacao"] == PR.PENDENTE and o["atrasados"] == 0
    o = PR._obrigacao("k", "r", [PR._item("x", prazo=datetime(2026, 10, 1),
                                          ctx=ctx)],
                      regra="com hora", tem_prazo=True)
    assert o["situacao"] == PR.ATRASADO and o["atrasados"] == 1
    assert PR._obrigacao("k", "r", [], regra="", tem_prazo=True)[
        "situacao"] == PR.FEITO
    nada = PR._obrigacao("k", "r", None, regra="", tem_prazo=True)
    assert nada["situacao"] == PR.SEM_MEDIDA and nada["faltam"] is None


def test_a_conduta_fica_com_a_pior_obrigacao():
    def o(s):
        return {"situacao": s}
    assert PR._situacao_da_conduta([o(PR.FEITO), o(PR.ATRASADO),
                                    o(PR.PENDENTE)]) == PR.ATRASADO
    assert PR._situacao_da_conduta([o(PR.FEITO), o(PR.PENDENTE)]) == PR.PENDENTE
    assert PR._situacao_da_conduta([o(PR.FEITO), o(PR.SEM_MEDIDA)]) == PR.FEITO
    assert PR._situacao_da_conduta([o(PR.SEM_MEDIDA)]) == PR.SEM_MEDIDA


def test_coluna_errada_ESTOURA_em_vez_de_virar_zero():
    con = _casa_minima()
    with pytest.raises(sqlite3.Error):
        PR._um(con, "pt_remessas",
               "SELECT COUNT(*) FROM pt_remessas WHERE nao_existe = %s", "x")


def test_tabela_que_nao_existe_devolve_NONE_e_nao_zero():
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    assert PR._um(con, "pt_remessas", "SELECT COUNT(*) FROM pt_remessas") is None


def test_instalacao_sem_protesto_fica_sem_medida_e_nunca_atrasada():
    """«Nao ha o que contar» nao e «contei zero», e muito menos «atrasado»."""
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    condutas = PR.cobrar_o_dia(con, agora=HOJE + "T16:00:00")
    for c in condutas:
        assert c["situacao"] != PR.ATRASADO, c["chave"]
    assert _conduta(condutas, "instrumentos")["situacao"] == PR.SEM_MEDIDA
    assert PR.estado_do_envio(con)["cra_envio_automatico_producao"] is None


# ------------------------------------------------------------- o que se cobra
#
# O banco da casa inteira (todas as tabelas), com o seed restaurado a cada
# teste. A ligacao e a da ponte de teste: `?` como marcador.


@pytest.fixture()
def casa(cg_casa):
    con = sqlite3.connect(cg_casa["banco"])
    con.row_factory = sqlite3.Row
    yield con
    con.close()


def _casa_minima() -> sqlite3.Connection:
    from nucleo_schema import init_nucleo_schema
    from pt_schema import init_pt_schema
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    init_nucleo_schema(con)
    init_pt_schema(con)
    return con


def _titulo(con, *, origem="CRA", situacao="APONTADO", numero="T1",
            protocolo="2610280001", criado_em=ONTEM + "T09:00:00") -> int:
    cur = con.execute(
        """INSERT INTO pt_titulos(especie, numero_titulo, situacao, origem,
               origem_chave, protocolo, apresentante_codigo, criado_em)
           VALUES ('DMI', ?, ?, ?, ?, ?, '033', ?)""",
        (numero, situacao, origem, f"{origem}:{numero}", protocolo, criado_em))
    con.commit()
    return cur.lastrowid


def _ato(con, titulo_id, tipo, data_ato, *, origem="MANUAL") -> int:
    cur = con.execute(
        """INSERT INTO pt_atos(titulo_id, tipo, data_ato, origem, criado_em)
           VALUES (?, ?, ?, ?, ?)""",
        (titulo_id, tipo, data_ato, origem, data_ato))
    con.commit()
    return cur.lastrowid


def _retorno(con, *, tipo, gerado_em, ambiente=None, enviado=None,
             erro=None) -> int:
    cur = con.execute(
        """INSERT INTO pt_retornos(tipo, apresentante_codigo, dia, nome_arquivo,
               conteudo, titulos, gerado_em, cra_enviado_em,
               cra_enviado_ambiente, cra_envio_erro)
           VALUES (?, '033', ?, 'x.txt', 'x', 1, ?, ?, ?, ?)""",
        (tipo, gerado_em[:10], gerado_em, enviado, ambiente, erro))
    con.commit()
    return cur.lastrowid


def _auditoria(con, acao, ts, detalhe) -> None:
    con.execute(
        """INSERT INTO audit_logs(ts, username_snapshot, action, details)
           VALUES (?, 'MARIA', ?, ?)""", (ts, acao, json.dumps(detalhe)))
    con.commit()


def _anexo(con, entidade, entidade_id) -> None:
    con.execute(
        """INSERT INTO attachments(entity_type, entity_id, original_name,
               stored_name, stored_path, sha256, size_bytes, uploaded_at)
           VALUES (?, ?, 'c.pdf', 'c.pdf', 'c.pdf', ?, 4, ?)""",
        (entidade, entidade_id, f"{entidade}{entidade_id}", HOJE))
    con.commit()


def test_a_remessa_so_atrasa_quando_ninguem_foi_buscar_depois_das_14h10(casa):
    antes = _obrigacao(PR.cobrar_o_dia(casa, agora=HOJE + "T13:00:00"),
                       "remessa_do_dia")
    assert antes["situacao"] == PR.PENDENTE
    depois = _obrigacao(PR.cobrar_o_dia(casa, agora=HOJE + "T14:11:00"),
                        "remessa_do_dia")
    assert depois["situacao"] == PR.ATRASADO
    # A CONSULTA PROVA A CONDUTA MESMO QUANDO A CRA NAO MANDA NADA: o zero
    # deixa de ser «nada chegou ou ninguem olhou».
    _auditoria(casa, "cra_baixar_e_conferir", HOJE + "T12:40:00",
               {"o_que": "pendentes", "tamanho": 241})
    feito = _obrigacao(PR.cobrar_o_dia(casa, agora=HOJE + "T15:00:00"),
                       "remessa_do_dia")
    assert feito["situacao"] == PR.FEITO and "12:40" in feito["feito"]


def test_remessa_sem_expediente_nunca_atrasa(casa):
    o = _obrigacao(PR.cobrar_o_dia(casa, agora=SABADO + "T16:00:00"),
                   "remessa_do_dia")
    assert o["situacao"] == PR.PENDENTE


def test_o_retorno_vence_as_11h30_do_dia_util_seguinte(casa):
    tid = _titulo(casa)
    _ato(casa, tid, "PAGAMENTO", ONTEM + "T10:00:00")
    no_prazo = _obrigacao(PR.cobrar_o_dia(casa, agora=HOJE + "T11:00:00"),
                          "atos_sem_retorno")
    assert no_prazo["situacao"] == PR.PENDENTE and no_prazo["faltam"] == 1
    vencido = _obrigacao(PR.cobrar_o_dia(casa, agora=HOJE + "T11:31:00"),
                         "atos_sem_retorno")
    assert vencido["situacao"] == PR.ATRASADO and vencido["atrasados"] == 1
    linha = vencido["lista"][0]
    assert linha["tela"] == "protesto_titulo"
    assert linha["args"] == {"titulo_id": tid} and linha["atrasado"]
    assert linha["prazo"] == "29/10 11:30"


def test_o_arquivo_gerado_e_nao_aceito_e_cobrado_e_a_virada_nao(casa):
    _retorno(casa, tipo="SDTBFORTP", gerado_em=HOJE + "T08:13:17",
             ambiente="EOFICIO", enviado=HOJE + "T08:13:17")
    _retorno(casa, tipo="SDTBFORTP", gerado_em="2026-09-01T10:00:00")
    o = _obrigacao(PR.cobrar_o_dia(casa, agora=HOJE + "T10:00:00"),
                   "retornos_nao_aceitos")
    assert o["situacao"] == PR.FEITO, (
        "a marca da virada e o ensaio de setembro nao sao obrigacao de hoje")
    _retorno(casa, tipo="SDTBFORTP", gerado_em=HOJE + "T09:00:00",
             ambiente="PRODUCAO", erro="a CRA nao respondeu")
    assert _obrigacao(PR.cobrar_o_dia(casa, agora=HOJE + "T11:00:00"),
                      "retornos_nao_aceitos")["situacao"] == PR.PENDENTE
    assert _obrigacao(PR.cobrar_o_dia(casa, agora=HOJE + "T11:31:00"),
                      "retornos_nao_aceitos")["situacao"] == PR.ATRASADO


def test_a_confirmacao_que_nao_subiu_vence_as_14h10(casa):
    _retorno(casa, tipo="SDTBFOCRT", gerado_em=HOJE + "T12:40:00",
             ambiente="PRODUCAO", enviado=HOJE + "T12:41:00")
    assert _obrigacao(PR.cobrar_o_dia(casa, agora=HOJE + "T15:00:00"),
                      "confirmacoes_nao_aceitas")["situacao"] == PR.FEITO
    _retorno(casa, tipo="SDTBFOCRT", gerado_em=HOJE + "T12:42:00",
             ambiente="PRODUCAO", erro="A CRA recusou")
    assert _obrigacao(PR.cobrar_o_dia(casa, agora=HOJE + "T14:00:00"),
                      "confirmacoes_nao_aceitas")["situacao"] == PR.PENDENTE
    assert _obrigacao(PR.cobrar_o_dia(casa, agora=HOJE + "T14:11:00"),
                      "confirmacoes_nao_aceitas")["situacao"] == PR.ATRASADO


def _consulta_a_cra(con, quando, operacao, *, nivel="INFO") -> None:
    con.execute(
        """INSERT INTO centrais_log(quando, central, operacao, ambiente, nivel,
               evento) VALUES (?, 'CRA', ?, 'PRODUCAO', ?, 'RESPOSTA')""",
        (quando, operacao, nivel))
    con.commit()


def test_protesto_lavrado_antes_de_consultar_a_cra_e_atraso(casa):
    """O erro que o papel manda evitar conferindo tres vezes por dia. DP, CP
    e AC sao UMA conduta desde 29/10/2026 (decisao do oficial), provada em
    `centrais_log`."""
    tid = _titulo(casa, origem="MANUAL", situacao="PROTESTADO")
    _ato(casa, tid, "PROTESTO", HOJE + "T14:31:00")
    o = _obrigacao(PR.cobrar_o_dia(casa, agora=HOJE + "T15:00:00"),
                   "consulta_da_cra")
    assert o["situacao"] == PR.ATRASADO and "14:31" in o["lista"][0]["texto"]
    # Consultada DEPOIS do protesto: continua atrasado — o protesto ja saiu.
    _consulta_a_cra(casa, HOJE + "T14:40:00", "Desistencia")
    # A chamada que deu ERRO nao e consulta.
    _consulta_a_cra(casa, HOJE + "T09:00:00", "Cancelamento", nivel="ERRO")
    assert _obrigacao(PR.cobrar_o_dia(casa, agora=HOJE + "T15:00:00"),
                      "consulta_da_cra")["situacao"] == PR.ATRASADO
    _consulta_a_cra(casa, HOJE + "T10:00:00", "Autorizacao")
    assert _obrigacao(PR.cobrar_o_dia(casa, agora=HOJE + "T15:00:00"),
                      "consulta_da_cra")["situacao"] == PR.FEITO


def test_sem_protesto_a_cra_nao_consultada_e_so_pendente(casa):
    o = _obrigacao(PR.cobrar_o_dia(casa, agora=HOJE + "T17:00:00"),
                   "consulta_da_cra")
    assert o["situacao"] == PR.PENDENTE
    # Fora do expediente nao se cobra.
    assert _obrigacao(PR.cobrar_o_dia(casa, agora=SABADO + "T17:00:00"),
                      "consulta_da_cra")["situacao"] == PR.FEITO


def test_a_consulta_de_cancelamento_e_AC_deixou_de_ser_passo_separado():
    con = _casa_minima()
    pedidos = next(c for c in PR.cobrar_o_dia(con, agora=HOJE + "T10:00:00")
                   if c["chave"] == "pedidos_cra")
    chaves = {o["chave"] for o in pedidos["obrigacoes"]}
    assert "consulta_de_cancelamento" not in chaves
    assert "pendencias_da_cra" in chaves, "o gancho da peça que traz DP, CP e AC"
    assert PR.OPERACOES_DOS_PEDIDOS_DA_CRA == (
        "Desistencia", "Cancelamento", "Autorizacao")


def test_entrega_sem_comprovante_atrasa_no_dia_seguinte(casa):
    tid = _titulo(casa)
    cur = casa.execute(
        """INSERT INTO pt_avisos(titulo_id, numero, ano, situacao, emitido_em,
               entrega_em, entregue, criado_em)
           VALUES (?, 1, 2026, 'ENTREGUE', ?, ?, 1, ?)""",
        (tid, ONTEM, ONTEM + "T09:00:00", ONTEM))
    casa.commit()
    o = _obrigacao(PR.cobrar_o_dia(casa, agora=HOJE + "T09:00:00"),
                   "entregas_sem_comprovante")
    assert o["situacao"] == PR.ATRASADO and o["faltam"] == 1
    _anexo(casa, "PT_AVISO", cur.lastrowid)
    assert _obrigacao(PR.cobrar_o_dia(casa, agora=HOJE + "T09:00:00"),
                      "entregas_sem_comprovante")["situacao"] == PR.FEITO


def test_edital_sem_comprovante_do_envio_a_cenprot_e_cobrado(casa):
    """O ERRO DE OUTUBRO: edital publicado e nenhum comprovante do envio."""
    tid = _titulo(casa)
    aviso = casa.execute(
        """INSERT INTO pt_avisos(titulo_id, numero, ano, situacao, emitido_em,
               criado_em) VALUES (?, 1, 2026, 'EDITAL', ?, ?)""",
        (tid, ONTEM, ONTEM)).lastrowid
    edital = casa.execute(
        """INSERT INTO pt_editais(numero, ano, aviso_id, titulo_id,
               publicado_em, teor, criado_em)
           VALUES (1, 2026, ?, ?, ?, 'teor', ?)""",
        (aviso, tid, ONTEM, ONTEM)).lastrowid
    casa.commit()
    o = _obrigacao(PR.cobrar_o_dia(casa, agora=HOJE + "T09:00:00"),
                   "editais_sem_comprovante")
    assert o["situacao"] == PR.ATRASADO
    assert "NÃO gerado" in o["lista"][0]["texto"]
    _anexo(casa, "PT_EDITAL_CENPROT", edital)
    assert _obrigacao(PR.cobrar_o_dia(casa, agora=HOJE + "T09:00:00"),
                      "editais_sem_comprovante")["situacao"] == PR.FEITO


def test_protesto_sem_instrumento_trava_o_xml_e_os_dois_sao_cobrados(casa):
    tid = _titulo(casa, origem="MANUAL", situacao="PROTESTADO")
    _ato(casa, tid, "PROTESTO", ONTEM + "T14:31:00")
    acervo = _titulo(casa, origem="CRA", situacao="PROTESTADO", numero="T2",
                     protocolo="2610280002")
    _ato(casa, acervo, "PROTESTO", ONTEM + "T14:31:00", origem="EOFICIO")
    condutas = PR.cobrar_o_dia(casa, agora=HOJE + "T09:00:00")
    sem_instr = _obrigacao(condutas, "protestos_sem_instrumento")
    assert sem_instr["situacao"] == PR.ATRASADO and sem_instr["faltam"] == 1, (
        "o protesto do E-Oficio nao e trabalho deste sistema")
    xml = _obrigacao(condutas, "atos_sem_xml")
    assert xml["situacao"] == PR.ATRASADO and xml["faltam"] == 1
    # A subida no portal da CENPROT tem obrigação própria desde o #114
    # (`xml_sem_comprovante`); a nota do XML diz quantos se geraram hoje.
    assert "arquivo(s) gerado(s) hoje" in xml["nota"]


def test_pendencia_da_cenprot_nunca_fica_vermelha(casa):
    """O papel lista os pedidos sem hora: pendente, e nao atrasado."""
    casa.execute(
        """INSERT INTO cn_pendencias(especie, ambiente, codigo, teor,
               baixada_em, situacao)
           VALUES ('ANUENCIA', 'PRODUCAO', '1', '{}', '2026-09-01T10:00:00',
                   'PENDENTE')""")
    casa.commit()
    o = _obrigacao(PR.cobrar_o_dia(casa, agora=HOJE + "T18:00:00"),
                   "cenprot_esperando")
    assert o["situacao"] == PR.PENDENTE and o["faltam"] == 1


def test_o_roteiro_junta_tudo_para_a_tela(casa):
    r = PR.roteiro(casa, agora=HOJE + "T10:00:00")
    assert r["hoje"] == HOJE
    assert [c["chave"] for c in r["condutas"]] == [
        c["chave"] for c in PR.CONDUTAS_DO_DIA]
    assert sum(r["total"].values()) == len(PR.CONDUTAS_DO_DIA)
    assert [x["hora"] for x in r["relogio"]] == ["11:30", "12:30", "14:10"]
    assert r["relogio"][0]["ancora"] == "conduta-retorno"
    assert "Andamento" in r["relogio"][0]["o_que"]
    assert len(r["papel"]) == 16
    assert all(p["conduta_n"] or p["fora_o_que"] for p in r["papel"])


# ------------------------------------------------------------- a tela


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado
    return achado.group(1)


@pytest.fixture()
def s(cg_casa):
    app = cg_casa['app']
    # USER, e nao ADMIN: o pedido foi «amplo acesso dos escreventes».
    cg_casa['db'].create_user("escrevente", "MARIA", SENHA, "USER")
    cg_casa['db'].set_settings({"modulo_protesto_ligado": "1"})
    c = app.test_client()
    c.post("/login", data={"username": "escrevente", "password": SENHA,
                           "csrf_token": _token(
                               c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return c


def test_o_escrevente_abre_a_tela(s):
    r = s.get("/protesto/roteiro")
    assert r.status_code == 200
    assert "o roteiro do dia" in r.get_data(as_text=True)


def test_a_tela_esta_no_menu(s):
    html = s.get("/protesto").get_data(as_text=True)
    assert 'href="/protesto/roteiro"' in html


def test_os_horarios_aparecem_na_TELA_ONDE_O_BALCAO_CHEGA(s):
    html = s.get("/protesto").get_data(as_text=True)
    assert "Horários da CRA" in html
    assert "11:30" in html and "14:10" in html and "12:30" in html


def test_a_faixa_dos_horarios_e_SO_do_protesto(s):
    for outra in ("/rcpn", "/rcpj-rtd", "/livro3"):
        assert "Horários da CRA" not in s.get(outra).get_data(as_text=True)


def test_a_tela_mostra_as_condutas_com_botao_e_situacao(s):
    html = s.get("/protesto/roteiro").get_data(as_text=True)
    for c in PR.CONDUTAS_DO_DIA:
        assert c["titulo"] in html
        assert f'id="{c["ancora"]}"' in html
    assert 'href="/protesto/remessas"' in html
    assert 'href="/protesto/a-protestar"' in html
    assert "ambiente=PRODUCAO" in html and "ambiente=HOMOLOG" not in html
    assert "A conduta:" in html
    assert re.search(r'class="rt-sit s-(FEITO|PENDENTE|ATRASADO)"', html)
    for hora in ("12:30", "14:10", "11:30"):
        assert hora in html


def test_a_tela_diz_o_que_saiu_do_roteiro_e_a_prova(s):
    html = s.get("/protesto/roteiro").get_data(as_text=True)
    assert "O que saiu do roteiro, e a prova" in html
    assert "Baixar e guardar as imagens dos títulos" in html
    assert "Enviar a confirmação da remessa" in html


def test_a_tela_traz_a_norma_e_de_onde_saiu(s):
    html = s.get("/protesto/roteiro").get_data(as_text=True)
    assert "Lei 9.492/1997" in html and "Resolucao n. 9 de 2024" in html
    assert "IEPTB-MA/CRA-MA" in html and "não está no acervo" in html


def test_a_tela_conta_as_afirmacoes_e_o_link_e_so_do_oficial(s):
    html = s.get("/protesto/roteiro").get_data(as_text=True)
    assert "afirmações nos últimos 7 dias" in html
    assert 'href="/protesto/afirmacoes"' not in html


def test_o_unico_formulario_do_painel_e_o_encerramento(s):
    """Os botoes LEVAM a tela que faz — nenhum faz por aqui. A excecao e o
    encerramento do dia (29/10/2026), e ele manda o csrf_token."""
    html = s.get("/protesto/roteiro").get_data(as_text=True)
    painel = html.split('id="relogio"', 1)[1].split(
        'id="roteiro-das-centrais"', 1)[0]
    formularios = re.findall(r"<form\b[^>]*>", painel)
    assert len(formularios) == 1
    assert 'action="/protesto/roteiro/encerrar"' in formularios[0]
    corpo = painel.split(formularios[0], 1)[1].split("</form>", 1)[0]
    assert 'name="csrf_token"' in corpo


# ================================================== o encerramento do dia
#
# Acrescimo do oficial em 29/10/2026: «garantir que todos processos sejam
# concluidos todos os dias; nao deixar margem para a escrevente esquecer ou
# fazer errado». O dia so se encerra com tudo feito; o que ficar exige a
# afirmacao de CADA item, e o dia seguinte abre mostrando isso.

AFIRMACAO = ("Afirmo, sob minha responsabilidade, que a CRA ficou fora do ar "
             "a tarde inteira")


def _todas(pendencias: list[dict], texto: str = AFIRMACAO) -> dict:
    return {p["chave"]: (True, texto) for p in pendencias}


def test_o_dia_com_pendencia_nao_se_encerra_sem_afirmacao(casa):
    agora = HOJE + "T18:00:00"
    with pytest.raises(PR.EncerramentoError) as recusa:
        PR.conferir_o_encerramento(casa, agora=agora, afirmacoes={})
    assert "não se encerra" in str(recusa.value)
    assert "Trazer e receber a remessa da CRA" in str(recusa.value), (
        "a recusa diz O QUE falta, item por item")
    pend = PR.pendencias_para_encerrar(PR.cobrar_o_dia(casa, agora=agora))
    assert pend and all(p["situacao"] in (PR.PENDENTE, PR.ATRASADO)
                        for p in pend)
    assert PR.OBRIGACAO_DO_PROPRIO_ENCERRAMENTO not in {p["chave"]
                                                        for p in pend}


def test_a_afirmacao_e_por_item_com_caixa_e_trinta_letras(casa):
    agora = HOJE + "T18:00:00"
    pend = PR.pendencias_para_encerrar(PR.cobrar_o_dia(casa, agora=agora))
    primeiro, *resto = pend
    afirm = _todas(resto)
    for ruim in ((False, AFIRMACAO),                  # sem a caixa
                 (True, "Afirmo que sim."),           # poucas letras
                 (True, "." * 80 + " 1234567890")):   # pontuacao nao conta
        afirm[primeiro["chave"]] = ruim
        with pytest.raises(PR.EncerramentoError) as recusa:
            PR.conferir_o_encerramento(casa, agora=agora, afirmacoes=afirm)
        assert primeiro["rotulo"] in str(recusa.value)
    afirm[primeiro["chave"]] = (True, AFIRMACAO)
    conferido = PR.conferir_o_encerramento(casa, agora=agora, afirmacoes=afirm)
    assert len(conferido["afirmacoes"]) == len(pend)
    assert all(a["afirmacao"] == AFIRMACAO and a["o_que_faltava"]
               for a in conferido["afirmacoes"])


def test_o_encerramento_grava_uma_vez_e_o_dia_seguinte_abre_com_ele(casa):
    agora = ONTEM + "T18:00:00"
    pend = PR.pendencias_para_encerrar(PR.cobrar_o_dia(casa, agora=agora))
    conferido = PR.conferir_o_encerramento(casa, agora=agora,
                                           afirmacoes=_todas(pend))
    r = PR.gravar_o_encerramento(casa, conferido, agora=agora, usuario="MARIA")
    casa.commit()
    assert r["situacao"] == "COM_PENDENCIA" and r["id"]
    with pytest.raises(PR.EncerramentoError):
        PR.conferir_o_encerramento(casa, agora=ONTEM + "T19:00:00",
                                   afirmacoes={})
    with pytest.raises(PR.EncerramentoError):
        PR.gravar_o_encerramento(casa, conferido, agora=agora, usuario="MARIA")
    # O DIA SEGUINTE ABRE MOSTRANDO O QUE FICOU, sem depender de memoria.
    r = PR.roteiro(casa, agora=HOJE + "T08:00:00")
    ontem = r["de_ontem"]
    assert ontem["dia_util_anterior"] == ONTEM
    assert ontem["anterior_encerrado"] is True
    assert ontem["ultimo"]["dia"] == ONTEM
    assert [a["afirmacao"] for a in ontem["ultimo"]["afirmacoes"]] == [
        AFIRMACAO] * len(pend)
    assert _obrigacao(r, "dias_sem_encerramento")["situacao"] == PR.FEITO
    assert _obrigacao(r, "dia_encerrado")["situacao"] == PR.PENDENTE


def test_o_dia_que_ficou_sem_encerrar_e_cobrado_ate_o_proximo(casa):
    casa.execute(
        """INSERT INTO pt_encerramentos_do_dia(dia, situacao, encerrado_em,
               encerrado_por) VALUES ('2026-10-27', 'COMPLETO',
               '2026-10-27T18:00:00', 'MARIA')""")
    casa.commit()
    r = PR.roteiro(casa, agora=HOJE + "T08:00:00")
    o = _obrigacao(r, "dias_sem_encerramento")
    assert o["situacao"] == PR.ATRASADO and o["faltam"] == 1
    assert "28/10" in o["lista"][0]["texto"]
    assert r["de_ontem"]["anterior_encerrado"] is False
    # Encerrar hoje exige afirmar tambem o dia que ficou — e, encerrado, ele
    # deixa de ser cobrado.
    pend = PR.pendencias_para_encerrar(r["condutas"])
    assert "dias_sem_encerramento" in {p["chave"] for p in pend}
    conferido = PR.conferir_o_encerramento(casa, agora=HOJE + "T18:00:00",
                                           afirmacoes=_todas(pend))
    PR.gravar_o_encerramento(casa, conferido, agora=HOJE + "T18:00:00",
                             usuario="MARIA")
    casa.commit()
    depois = PR.roteiro(casa, agora=HOJE + "T18:05:00")
    assert _obrigacao(depois, "dias_sem_encerramento")["situacao"] == PR.FEITO
    assert _obrigacao(depois, "dia_encerrado")["situacao"] == PR.FEITO
    # E O QUADRO DO ALTO DIZ O MESMO: não há como encerrar um dia passado.
    assert depois["de_ontem"]["anterior_encerrado"] is True


def test_sem_encerramento_nenhum_nao_ha_dia_atrasado(casa):
    """A obrigacao nasce com o primeiro encerramento — sem alarme no primeiro
    dia da instalacao, sobre um dever que ainda nao existia."""
    o = _obrigacao(PR.cobrar_o_dia(casa, agora=HOJE + "T09:00:00"),
                   "dias_sem_encerramento")
    assert o["situacao"] == PR.FEITO


def test_sem_medida_nao_prende_o_dia():
    condutas = [{"n": 1, "titulo": "X", "obrigacoes": [
        {"chave": "a", "rotulo": "a", "situacao": PR.SEM_MEDIDA, "faltam": None,
         "atrasados": 0},
        {"chave": "b", "rotulo": "b", "situacao": PR.FEITO, "faltam": 0,
         "atrasados": 0},
        {"chave": PR.OBRIGACAO_DO_PROPRIO_ENCERRAMENTO, "rotulo": "c",
         "situacao": PR.PENDENTE, "faltam": 1, "atrasados": 0}]}]
    assert PR.pendencias_para_encerrar(condutas) == []


def test_o_livro_de_protocolo_que_nao_esta_aberto_nao_e_cobrado(casa):
    """Medido em 29/10/2026: o Livro de Protocolo do Protesto nunca foi aberto
    no nucleo. Cobrar termo de livro que a casa nao usa seria o alarme que
    soa sempre; com o livro aberto, o dia com movimento sem termo e cobrado."""
    tem = casa.execute("SELECT 1 FROM nu_livros WHERE serie = ?",
                       (PR.SERIE_DO_PROTOCOLO,)).fetchone()
    o = _obrigacao(PR.cobrar_o_dia(casa, agora=HOJE + "T09:00:00"),
                   "termo_do_protocolo")
    if not tem:
        assert o["situacao"] == PR.SEM_MEDIDA and "não se aplica" in o["motivo"]


# ------------------------------------------------- os ganchos das outras pecas


def _gancho(monkeypatch, funcao, **extra):
    import types
    modulo = types.ModuleType("peca_de_teste_do_roteiro")
    if funcao is not None:
        modulo.pendencias = funcao
    monkeypatch.setitem(sys.modules, "peca_de_teste_do_roteiro", modulo)
    g = {"chave": "peca_de_teste", "conduta": "protestos",
         "rotulo": "a peça de teste", "modulo": "peca_de_teste_do_roteiro",
         "funcao": "pendencias", "de_onde": "o teste", **extra}
    monkeypatch.setattr(PR, "GANCHOS", (g,))


def test_gancho_ausente_e_ainda_nao_instalado_e_nao_prende_o_dia(
        casa, monkeypatch):
    _gancho(monkeypatch, None)
    o = _obrigacao(PR.cobrar_o_dia(casa, agora=HOJE + "T09:00:00"),
                   "peca_de_teste")
    assert o["situacao"] == PR.SEM_MEDIDA
    assert "ainda não instalada" in o["motivo"]


def test_gancho_que_conta_e_que_lista_vira_pendencia(casa, monkeypatch):
    _gancho(monkeypatch, lambda con: 3, tela="protesto_titulos")
    o = _obrigacao(PR.cobrar_o_dia(casa, agora=HOJE + "T09:00:00"),
                   "peca_de_teste")
    assert o["situacao"] == PR.PENDENTE and o["faltam"] == 3
    _gancho(monkeypatch, lambda con: [
        {"titulo_id": 7, "protocolo": "2610290001", "explicacao": "sem ato"},
        {"titulo_id": 8, "origem": "ACERVO", "explicacao": "do acervo"}])
    o = _obrigacao(PR.cobrar_o_dia(casa, agora=HOJE + "T09:00:00"),
                   "peca_de_teste")
    assert o["faltam"] == 1, "o acervo nao vira trabalho de hoje"
    assert o["lista"][0]["args"] == {"titulo_id": 7}
    assert o["situacao"] == PR.PENDENTE, "gancho nao tem prazo aqui"


def test_gancho_que_estoura_nao_derruba_o_roteiro(casa, monkeypatch):
    def quebra(con):
        con.execute("SELECT * FROM tabela_que_nao_existe_no_roteiro")
    _gancho(monkeypatch, quebra)
    r = PR.roteiro(casa, agora=HOJE + "T09:00:00")
    o = _obrigacao(r, "peca_de_teste")
    assert o["situacao"] == PR.SEM_MEDIDA and "não respondeu" in o["motivo"]
    assert r["de_ontem"]["dia_util_anterior"] == ONTEM, (
        "a leitura desfeita nao leva junto o resto do roteiro")


def test_os_ganchos_declarados_apontam_para_condutas_que_existem():
    chaves = {c["chave"] for c in PR.CONDUTAS_DO_DIA}
    for g in PR.GANCHOS:
        assert g["conduta"] in chaves and g["conduta"] != "encerrar", g
        for campo in ("chave", "rotulo", "modulo", "funcao", "de_onde"):
            assert g[campo], (g, campo)
    assert {(g["modulo"], g["funcao"]) for g in PR.GANCHOS} >= {
        ("protesto_selo_previo", "pendencias_do_selo"),
        ("protesto_selo_previo", "titulos_sem_ato_que_sustente"),
        ("cenprot_conferencia", "quantos_divergem"),
        ("protesto_prova", "intimacoes_sem_prova"),
        ("protesto_titulos_irmaos", "pendencias_dos_irmaos"),
        ("protesto_retorno", "protocolos_repetidos_na_fila"),
        ("protesto_desistencia", "pendencias_da_cra")}


def test_gancho_com_nome_certo_acha_a_funcao_na_arvore():
    """«nome_a_confirmar» sai quando a peca entra no main com aquele nome; o
    gancho sem a marca, cujo modulo existe, TEM de achar a funcao — senao a
    linha diria «ainda nao instalada» sobre peca instalada com outro nome."""
    import importlib
    for g in PR.GANCHOS:
        if g.get("nome_a_confirmar") or not (RAIZ / f"{g['modulo']}.py").exists():
            continue
        modulo = importlib.import_module(g["modulo"])
        assert callable(getattr(modulo, g["funcao"], None)), g


# ------------------------------------------------- o encerramento pela tela


def test_a_tela_encerra_com_afirmacao_e_grava_a_auditoria(s, cg_casa):
    html = s.get("/protesto/roteiro").get_data(as_text=True)
    assert 'id="o-que-ficou"' in html and "Primeiro: o que ficou de antes" in html
    itens = re.findall(r'name="item" value="([^"]+)"', html)
    token = _token(html)
    sem = s.post("/protesto/roteiro/encerrar",
                 data={"csrf_token": token, "item": itens},
                 follow_redirects=True).get_data(as_text=True)
    if itens:
        assert "não se encerra" in sem
    dados = {"csrf_token": token, "item": itens}
    for chave in itens:
        dados[f"afirmo_{chave}"] = "1"
        dados[f"afirmacao_{chave}"] = AFIRMACAO
    fim = s.post("/protesto/roteiro/encerrar", data=dados,
                 follow_redirects=True).get_data(as_text=True)
    assert "O dia de hoje está encerrado" in fim
    con = sqlite3.connect(cg_casa["banco"])
    con.row_factory = sqlite3.Row
    assert con.execute(
        "SELECT COUNT(*) FROM pt_encerramentos_do_dia").fetchone()[0] == 1
    regras = [json.loads(x["details"])["regra"] for x in con.execute(
        "SELECT details FROM audit_logs WHERE action = 'AFIRMACAO_EXPRESSA'")]
    assert regras == [PR.REGRA_DO_ENCERRAMENTO] * len(itens)
    con.close()


# ======================================== decisoes do oficial de 29/10/2026
#
# A escrevente encerra; SO O OFICIAL (ADMIN humano) reabre, com o motivo por
# afirmacao expressa, e a reabertura fica na propria linha. Robo nao encerra
# nem reabre. E a subida do XML P/D so fica feita com o comprovante.


def test_so_o_oficial_reabre_e_a_reabertura_fica_na_linha(casa):
    with pytest.raises(PR.EncerramentoError):
        PR.reabrir_o_dia(casa, agora=HOJE + "T18:00:00", afirmacao=AFIRMACAO,
                         usuario="OFICIAL")
    agora = HOJE + "T18:00:00"
    pend = PR.pendencias_para_encerrar(PR.cobrar_o_dia(casa, agora=agora))
    primeiro = PR.gravar_o_encerramento(
        casa, PR.conferir_o_encerramento(casa, agora=agora,
                                         afirmacoes=_todas(pend)),
        agora=agora, usuario="MARIA")
    casa.commit()
    PR.reabrir_o_dia(casa, agora=HOJE + "T18:30:00", afirmacao=AFIRMACAO,
                     usuario="OFICIAL")
    casa.commit()
    e = PR.encerramento_do_dia(casa, HOJE)
    assert e["reaberto_por"] == "OFICIAL" and e["reabertura_afirmacao"]
    assert e["reaberturas"][0]["encerramento"]["encerrado_por"] == "MARIA"
    with pytest.raises(PR.EncerramentoError):
        PR.reabrir_o_dia(casa, agora=HOJE + "T18:31:00", afirmacao=AFIRMACAO,
                         usuario="OFICIAL")
    o = _obrigacao(PR.cobrar_o_dia(casa, agora=HOJE + "T18:40:00"),
                   "dia_encerrado")
    assert o["situacao"] == PR.PENDENTE and "reaberto por OFICIAL" in o["nota"]
    # REENCERRADO NA MESMA LINHA, e o encerramento de antes nao se perde.
    agora = HOJE + "T19:00:00"
    pend = PR.pendencias_para_encerrar(PR.cobrar_o_dia(casa, agora=agora))
    segundo = PR.gravar_o_encerramento(
        casa, PR.conferir_o_encerramento(casa, agora=agora,
                                         afirmacoes=_todas(pend)),
        agora=agora, usuario="MARIA")
    casa.commit()
    assert segundo["id"] == primeiro["id"]
    e = PR.encerramento_do_dia(casa, HOJE)
    assert not e["reaberto_em"] and len(e["reaberturas"]) == 1
    assert casa.execute("SELECT COUNT(*) FROM pt_encerramentos_do_dia "
                        "WHERE dia = ?", (HOJE,)).fetchone()[0] == 1


def test_a_afirmacao_do_contrato_e_uma_regua_so():
    import afirmacoes_expressas as AFX
    assert PR.MINIMO_DE_LETRAS_DA_AFIRMACAO == AFX.MINIMO_DE_LETRAS == 30
    assert AFX.validar(True, AFIRMACAO) == AFIRMACAO
    for afirmo, texto in ((False, AFIRMACAO), (True, "curto demais"),
                          (True, "!" * 60)):
        with pytest.raises(AFX.AfirmacaoError):
            AFX.validar(afirmo, texto)


def _entrar(cg_casa, usuario: str, papel: str):
    cg_casa["db"].create_user(usuario, usuario.upper(), SENHA, papel)
    cg_casa["db"].set_settings({"modulo_protesto_ligado": "1"})
    c = cg_casa["app"].test_client()
    c.post("/login", data={"username": usuario, "password": SENHA,
                           "csrf_token": _token(
                               c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return c


def _encerrar_pela_tela(c) -> str:
    html = c.get("/protesto/roteiro").get_data(as_text=True)
    itens = re.findall(r'name="item" value="([^"]+)"', html)
    dados = {"csrf_token": _token(html), "item": itens}
    for chave in itens:
        dados[f"afirmo_{chave}"] = "1"
        dados[f"afirmacao_{chave}"] = AFIRMACAO
    return c.post("/protesto/roteiro/encerrar", data=dados,
                  follow_redirects=True).get_data(as_text=True)


def test_a_escrevente_encerra_e_nao_reabre(cg_casa):
    c = _entrar(cg_casa, "escrevente", "USER")
    assert "O dia de hoje está encerrado" in _encerrar_pela_tela(c)
    html = c.get("/protesto/roteiro").get_data(as_text=True)
    assert "Reabrir o dia" not in html
    r = c.post("/protesto/roteiro/reabrir",
               data={"csrf_token": _token(html), "afirmo": "1",
                     "afirmacao": AFIRMACAO})
    assert r.status_code == 403


def test_o_oficial_reabre_com_afirmacao_e_fica_na_auditoria(cg_casa):
    c = _entrar(cg_casa, "oficial", "ADMIN")
    _encerrar_pela_tela(c)
    html = c.get("/protesto/roteiro").get_data(as_text=True)
    assert "Reabrir o dia" in html
    sem = c.post("/protesto/roteiro/reabrir",
                 data={"csrf_token": _token(html), "afirmacao": AFIRMACAO},
                 follow_redirects=True).get_data(as_text=True)
    assert "Afirmo" in sem and "Dia reaberto" not in sem
    com = c.post("/protesto/roteiro/reabrir",
                 data={"csrf_token": _token(html), "afirmo": "1",
                       "afirmacao": AFIRMACAO},
                 follow_redirects=True).get_data(as_text=True)
    assert "Dia reaberto" in com and "Reaberto" in com
    con = sqlite3.connect(cg_casa["banco"])
    con.row_factory = sqlite3.Row
    assert con.execute("SELECT COUNT(*) FROM audit_logs WHERE action = ?",
                       (PR.REGRA_DA_REABERTURA,)).fetchone()[0] == 1
    regras = [json.loads(x["details"])["regra"] for x in con.execute(
        "SELECT details FROM audit_logs WHERE action = 'AFIRMACAO_EXPRESSA'")]
    assert PR.REGRA_DA_REABERTURA in regras
    con.close()


def _xml(con, *, nome: str, gerado_em: str) -> int:
    cur = con.execute(
        """INSERT INTO pt_cenprot_xml(letra, dia, sequencial, nome_arquivo,
               conteudo, sha256, titulos, gerado_em)
           VALUES ('D', ?, 1, ?, ?, 'x', 1, ?)""",
        (gerado_em[:10], nome, b"<xml/>", gerado_em))
    con.commit()
    return cur.lastrowid


def test_o_xml_sem_comprovante_atrasa_no_dia_util_seguinte(casa, tmp_path):
    import protesto_cenprot_xml as PCXML
    um = _xml(casa, nome="D2107001281026.xml", gerado_em=ONTEM + "T16:00:00")
    no_dia = _obrigacao(PR.cobrar_o_dia(casa, agora=ONTEM + "T17:00:00"),
                        "xml_sem_comprovante")
    assert no_dia["situacao"] == PR.PENDENTE
    seguinte = _obrigacao(PR.cobrar_o_dia(casa, agora=HOJE + "T08:00:00"),
                          "xml_sem_comprovante")
    assert seguinte["situacao"] == PR.ATRASADO
    with pytest.raises(PCXML.CenprotXmlError):
        PCXML.guardar_comprovante_do_envio(
            casa, um, nome="c.pdf", conteudo=b"nao sou pdf",
            pasta_de_arquivos=tmp_path, agora=HOJE + "T09:00:00")
    PCXML.guardar_comprovante_do_envio(
        casa, um, nome="c.pdf", conteudo=b"%PDF-1.4 portal",
        pasta_de_arquivos=tmp_path, agora=HOJE + "T09:00:00")
    casa.commit()
    assert _obrigacao(PR.cobrar_o_dia(casa, agora=HOJE + "T09:30:00"),
                      "xml_sem_comprovante")["situacao"] == PR.FEITO
    # SEM COMPROVANTE, SO POR AFIRMACAO — gravada na linha do arquivo.
    dois = _xml(casa, nome="P2107001281026.xml", gerado_em=ONTEM + "T16:05:00")
    PCXML.afirmar_envio_sem_comprovante(casa, dois, afirmacao=AFIRMACAO,
                                        agora=HOJE + "T10:00:00",
                                        usuario="MARIA")
    casa.commit()
    assert _obrigacao(PR.cobrar_o_dia(casa, agora=HOJE + "T10:30:00"),
                      "xml_sem_comprovante")["situacao"] == PR.FEITO
    with pytest.raises(PCXML.CenprotXmlError):
        PCXML.afirmar_envio_sem_comprovante(casa, dois, afirmacao=AFIRMACAO,
                                            agora=HOJE + "T10:40:00",
                                            usuario="MARIA")
