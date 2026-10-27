"""A nota de exigência GERAL do protocolo do balcão — 26/10/2026.

    «precisamos que todas as atribuições tenham nota de exigência»
                                                  — o oficial, 26/10/2026

O RI (nota devolutiva da prenotação) e o RCPJ/RTD (qualificação negativa do
título) já tinham a sua; Notas, Registro Civil e Protesto não tinham nenhuma.
Estes testes guardam:

  · a nota geral nasce no protocolo, numerada por protocolo, e NÃO se apaga —
    sai cumprida (quem e quando) ou cancelada (com motivo);
  · o RI e o RCPJ/RTD continuam com as deles: abrir a geral neles é recusado,
    com a frase de onde fazer;
  · a LEITURA ÚNICA (`exigencias_abertas_do_protocolo`) junta as três, com o
    formato que o portal do cliente e os avisos de andamento vão ler;
  · a regra do balcão: o texto que traz CPF/CNPJ ou nome em maiúsculas é
    AVISADO (não recusado), e a orientação está junto do campo nesta tela e
    na nota devolutiva do RI;
  · o papel sai pelo catálogo da casa (`CAIXA_EXIGENCIA`).

Nomes de teste da casa: mario, beatriz, carla. Nenhum dado real.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import caixa_exigencia as CXEX                      # noqa: E402
from bd_nativo import banco                         # noqa: E402

AGORA = "2026-10-26T10:00:00"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _protocolo(db, *, numero="2026.10.501", atribuicao="NOTAS",
               situacao="ABERTO", ri_protocolo_id=None,
               interessado="BEATRIZ EXEMPLO") -> int:
    with db.transaction() as con:
        return int(banco(con).escrever(
            """INSERT INTO cx_protocolos (numero, data_abertura, atribuicao,
                   interessado, assunto, situacao, origem, criado_em,
                   ri_protocolo_id)
               VALUES (%s, '2026-10-26', %s, %s, 'ESCRITURA', %s, 'MANUAL',
                       %s, %s) RETURNING id""",
            (numero, atribuicao, interessado, situacao, AGORA,
             ri_protocolo_id))[0]["id"])


def _abrir(db, pid, texto="Trazer a certidão de casamento atualizada.", **kw):
    with db.transaction() as con:
        return CXEX.abrir(con, pid, texto=texto, agora=AGORA, quem="MARIO",
                          **kw)


def _linhas(db, pid) -> list[dict]:
    with db.connect() as con:
        return banco(con).ler(
            "SELECT * FROM cx_exigencias WHERE protocolo_id = %s ORDER BY id",
            (pid,))


# ------------------------------------------------------------ o texto


def test_uma_exigencia_por_linha_e_a_numeracao_digitada_sai():
    assert CXEX.itens_do_texto("1. trazer a certidão\n\n2) falta a anuência\n- e o RG") == [
        "trazer a certidão", "falta a anuência", "e o RG"]
    assert CXEX.itens_do_texto("   \n") == []


def test_cpf_e_cnpj_geram_aviso():
    avisos = CXEX.avisos_do_texto("Falta a assinatura do CPF 123.456.789-00 (DV inválido de propósito).")
    assert avisos and "CPF ou CNPJ" in avisos[0]
    assert CXEX.avisos_do_texto("CNPJ 12345678000100 sem certidão")


def test_nome_em_maiusculas_gera_aviso_e_termo_do_balcao_nao():
    assert CXEX.avisos_do_texto("Falta a anuência de CARLA EXEMPLO DOS SANTOS.")
    # Siglas e termos que o balcão escreve todo dia não são nome de gente.
    assert CXEX.avisos_do_texto(
        "Trazer a CERTIDÃO DE CASAMENTO atualizada e a guia do ITBI.") == []
    assert CXEX.avisos_do_texto("Falta a anuência do cônjuge.") == []


# ------------------------------------------------------------ abrir


def test_abrir_numera_por_protocolo_e_guarda_quem(cg_casa_logada):
    db = cg_casa_logada["db"]
    pid = _protocolo(db)
    primeira = _abrir(db, pid, texto="1. Trazer a procuração.\n2. Falta a anuência do cônjuge.")
    segunda = _abrir(db, pid, prazo_ate="2026-11-09")
    assert (primeira["numero"], segunda["numero"]) == (1, 2)
    assert primeira["itens"] == ["Trazer a procuração.", "Falta a anuência do cônjuge."]
    assert primeira["atribuicao"] == "NOTAS"          # sugerida pela do protocolo
    linha = _linhas(db, pid)[0]
    assert linha["situacao"] == "ABERTA"
    assert linha["aberta_por"] == "MARIO" and linha["aberta_em"] == AGORA
    assert _linhas(db, pid)[1]["prazo_ate"] == "2026-11-09"


@pytest.mark.parametrize("atribuicao, trecho", [
    ("RI", "NOTA DEVOLUTIVA"),
    ("RTD", "QUALIFICAÇÃO NEGATIVA"),
    ("RCPJ", "QUALIFICAÇÃO NEGATIVA"),
])
def test_atribuicao_com_nota_propria_e_recusada(cg_casa_logada, atribuicao, trecho):
    db = cg_casa_logada["db"]
    pid = _protocolo(db, atribuicao=atribuicao)
    with pytest.raises(CXEX.ExigenciaError, match=trecho):
        _abrir(db, pid)
    # e escolher a atribuição com nota própria num protocolo de Notas também
    outro = _protocolo(db, numero="2026.10.777")
    with pytest.raises(CXEX.ExigenciaError, match=trecho):
        _abrir(db, outro, atribuicao=atribuicao)
    assert _linhas(db, pid) == [] and _linhas(db, outro) == []


def test_protocolo_de_ri_pode_ter_a_geral_de_outra_atribuicao(cg_casa_logada):
    db = cg_casa_logada["db"]
    pid = _protocolo(db, atribuicao="RI")
    nova = _abrir(db, pid, atribuicao="NOTAS")
    assert nova["atribuicao"] == "NOTAS"


def test_recusas_do_balcao(cg_casa_logada):
    db = cg_casa_logada["db"]
    pid = _protocolo(db)
    with pytest.raises(CXEX.ExigenciaError, match="dez letras"):
        _abrir(db, pid, texto="doc")
    with pytest.raises(CXEX.ExigenciaError, match="já passou"):
        _abrir(db, pid, prazo_ate="2026-10-01")
    with pytest.raises(CXEX.ExigenciaError, match="não é data"):
        _abrir(db, pid, prazo_ate="amanhã")
    with pytest.raises(CXEX.ExigenciaError, match="não é atribuição"):
        _abrir(db, pid, atribuicao="XYZ")
    encerrado = _protocolo(db, numero="2026.10.502", situacao="CANCELADO")
    with pytest.raises(CXEX.ExigenciaError, match="encerrado"):
        _abrir(db, encerrado)
    assert _linhas(db, pid) == []


# ------------------------------------------------------------ cumprir e cancelar


def test_cumprir_e_cancelar_nao_apagam(cg_casa_logada):
    db = cg_casa_logada["db"]
    pid = _protocolo(db)
    a = _abrir(db, pid)
    b = _abrir(db, pid)
    with db.transaction() as con:
        feita = CXEX.dar_por_cumprida(con, pid, a["id"], agora=AGORA,
                                      quem="BEATRIZ", observacao="trouxe a certidão")
    assert feita["situacao"] == "CUMPRIDA" and feita["cumprida_por"] == "BEATRIZ"
    with pytest.raises(CXEX.ExigenciaError, match="dez letras"):
        with db.transaction() as con:
            CXEX.cancelar(con, pid, b["id"], motivo="erro", agora=AGORA)
    with db.transaction() as con:
        cancelada = CXEX.cancelar(con, pid, b["id"], agora=AGORA, quem="CARLA",
                                  motivo="emitida no protocolo errado")
    assert cancelada["situacao"] == "CANCELADA"
    assert cancelada["cancelada_motivo"] == "emitida no protocolo errado"
    # só a aberta se cumpre ou se cancela
    with pytest.raises(CXEX.ExigenciaError, match="só a aberta"):
        with db.transaction() as con:
            CXEX.dar_por_cumprida(con, pid, b["id"], agora=AGORA)
    assert len(_linhas(db, pid)) == 2                  # nada sumiu


def test_nota_de_outro_protocolo_e_recusada(cg_casa_logada):
    db = cg_casa_logada["db"]
    pid = _protocolo(db)
    outro = _protocolo(db, numero="2026.10.503")
    a = _abrir(db, pid)
    with pytest.raises(CXEX.ExigenciaError, match="não é deste protocolo"):
        with db.transaction() as con:
            CXEX.dar_por_cumprida(con, outro, a["id"], agora=AGORA)


# ------------------------------------------------------------ a leitura única

CHAVES_DO_RETORNO = {"origem", "id", "chave", "atribuicao", "numero", "itens",
                     "fundamento", "prazo_ate", "aberta_em", "onde",
                     "prenotacao_id", "titulo_id"}


def _prenotacao_com_nota(db) -> int:
    with db.transaction() as con:
        bd = banco(con)
        ri = int(bd.escrever(
            """INSERT INTO ri_protocolos (numero, livro, data_prenotacao,
                   situacao, origem, criado_em)
               VALUES (90001, '1A', '2026-10-20', 'DEVOLVIDO', 'MANUAL', %s)
               RETURNING id""", (AGORA,))[0]["id"])
        bd.escrever(
            """INSERT INTO ri_notas_devolutivas (protocolo_id, numero, data_nota,
                   exigencias, fundamentacao, prazo_ate, situacao, emitida_em)
               VALUES (%s, 1, '2026-10-21', %s, 'Lei 6.015/1973', '2026-11-19',
                       'ABERTA', %s)""",
            (ri, '["Apresentar a guia do ITBI.", "Falta a anuência do cônjuge."]',
             AGORA))
        bd.escrever(
            """INSERT INTO ri_notas_devolutivas (protocolo_id, numero, data_nota,
                   exigencias, situacao, emitida_em)
               VALUES (%s, 2, '2026-10-22', '["Já cumprida."]', 'CUMPRIDA', %s)""",
            (ri, AGORA))
    return ri


def _titulo_em_exigencia(db, pid: int) -> int:
    import rg_titulo as TIT
    with db.transaction() as con:
        tid = int(banco(con).escrever(
            """INSERT INTO rg_titulos (atribuicao, numero, data_apresentacao,
                   apresentante, natureza, protocolo_geral_id, criado_em)
               VALUES (4, 1275, '2026-10-23', 'CARLA EXEMPLO', 'Contrato', %s, %s)
               RETURNING id""", (pid, AGORA))[0]["id"])
        TIT.qualificar(con, tid, resultado=TIT.NEGATIVA, agora=AGORA,
                       exigencias="Reconhecer a firma do contratante.\nJuntar o contrato social.",
                       prazo_ate="2026-11-23", data_qualificacao="2026-10-24")
    return tid


def test_a_leitura_unica_junta_as_tres_atribuicoes(cg_casa_logada):
    db = cg_casa_logada["db"]
    ri = _prenotacao_com_nota(db)
    pid = _protocolo(db, atribuicao="RI", ri_protocolo_id=ri)
    tid = _titulo_em_exigencia(db, pid)
    geral = _abrir(db, pid, atribuicao="NOTAS",
                   texto="Trazer a procuração com poderes específicos.")
    cancelada = _abrir(db, pid, atribuicao="NOTAS")
    with db.transaction() as con:
        CXEX.cancelar(con, pid, cancelada["id"], agora=AGORA,
                      motivo="emitida no protocolo errado")

    with db.connect() as con:
        abertas = CXEX.exigencias_abertas_do_protocolo(con, pid)

    assert [x["origem"] for x in abertas] == ["RI", "RCPJ_RTD", "GERAL"]  # pela data
    for x in abertas:
        assert set(x) == CHAVES_DO_RETORNO
        assert x["chave"] == f"{x['origem']}:{x['id']}"
    ri_x, rg_x, ge_x = abertas
    assert ri_x["itens"] == ["Apresentar a guia do ITBI.", "Falta a anuência do cônjuge."]
    assert ri_x["prenotacao_id"] == ri and ri_x["numero"] == 1
    assert ri_x["prazo_ate"] == "2026-11-19" and ri_x["fundamento"] == "Lei 6.015/1973"
    assert rg_x["atribuicao"] == "RTD" and rg_x["titulo_id"] == tid
    assert rg_x["itens"] == ["Reconhecer a firma do contratante.", "Juntar o contrato social."]
    assert ge_x["id"] == geral["id"] and ge_x["atribuicao"] == "NOTAS"
    assert ge_x["itens"] == ["Trazer a procuração com poderes específicos."]


def test_protocolo_sem_nada_e_inexistente_devolvem_lista_vazia(cg_casa_logada):
    db = cg_casa_logada["db"]
    pid = _protocolo(db)
    with db.connect() as con:
        assert CXEX.exigencias_abertas_do_protocolo(con, pid) == []
        assert CXEX.exigencias_abertas_do_protocolo(con, 999999) == []


# ------------------------------------------------------------ o papel e o catálogo


def test_o_papel_esta_no_catalogo_e_o_padrao_monta():
    import modelos_da_casa as MODELOS
    assert CXEX.CHAVE_DO_PAPEL in MODELOS.POR_CHAVE
    padrao = MODELOS.padrao_de(CXEX.CHAVE_DO_PAPEL)
    assert CXEX.MODELO_NOTA_DE_EXIGENCIA == padrao     # o nome antigo responde
    assert CXEX.conferir_modelo(padrao) == ""
    assert "inventado" in CXEX.conferir_modelo("{{ inventado.campo }}")


def test_o_papel_escapa_o_texto_do_balcao():
    papel = CXEX.montar_papel(**{**CXEX.CLAROS_DE_EXEMPLO,
                                 "itens": ["Trazer <b>isto</b>."]})
    assert "&lt;b&gt;isto&lt;/b&gt;" in papel
    assert "NOTA DE EXIGÊNCIA" in papel


# ------------------------------------------------------------ as telas


def test_a_ficha_do_protocolo_mostra_as_exigencias(cg_casa_logada):
    db, c = cg_casa_logada["db"], cg_casa_logada["c"]
    pid = _protocolo(db)
    _abrir(db, pid, texto="Trazer a certidão de nascimento atualizada.")
    html = c.get(f"/caixa/protocolos/{pid}").get_data(as_text=True)
    assert 'id="exigencias"' in html
    assert "Trazer a certidão de nascimento atualizada." in html
    assert f"/caixa/protocolos/{pid}/exigencias" in html


def test_a_tela_orienta_e_avisa_sem_gravar(cg_casa_logada):
    db, c = cg_casa_logada["db"], cg_casa_logada["c"]
    pid = _protocolo(db)
    html = c.get(f"/caixa/protocolos/{pid}/exigencias").get_data(as_text=True)
    assert "Não escreva nome de terceiros nem CPF/CNPJ" in html
    tok = _token(html)
    r = c.post(f"/caixa/protocolos/{pid}/exigencias", data={
        "csrf_token": tok, "atribuicao": "NOTAS",
        "texto": "Falta a anuência de CARLA EXEMPLO DOS SANTOS."})
    corpo = r.get_data(as_text=True)
    assert r.status_code == 200 and "nome de pessoa em maiúsculas" in corpo
    assert "revisei_o_texto" in corpo
    assert _linhas(db, pid) == []                      # avisou, não gravou
    # Confirmado pelo balcão, grava.
    r = c.post(f"/caixa/protocolos/{pid}/exigencias", data={
        "csrf_token": tok, "atribuicao": "NOTAS", "revisei_o_texto": "1",
        "texto": "Falta a anuência de CARLA EXEMPLO DOS SANTOS."})
    assert r.status_code == 302
    assert len(_linhas(db, pid)) == 1


def test_abrir_cumprir_e_imprimir_pela_tela(cg_casa_logada):
    db, c = cg_casa_logada["db"], cg_casa_logada["c"]
    pid = _protocolo(db)
    tok = _token(c.get(f"/caixa/protocolos/{pid}/exigencias").get_data(as_text=True))
    r = c.post(f"/caixa/protocolos/{pid}/exigencias", data={
        "csrf_token": tok, "atribuicao": "NOTAS",
        "texto": "Falta a anuência do cônjuge.", "prazo_ate": "2099-12-31"})
    assert r.status_code == 302
    nota = _linhas(db, pid)[0]
    r = c.get(f"/caixa/protocolos/{pid}/exigencias/{nota['id']}/papel?formato=odt")
    assert r.status_code == 200
    assert r.mimetype == "application/vnd.oasis.opendocument.text"
    r = c.post(f"/caixa/protocolos/{pid}/exigencias/{nota['id']}/cumprida",
               data={"csrf_token": tok, "observacao": "trouxe a anuência"})
    assert r.status_code == 302
    assert _linhas(db, pid)[0]["situacao"] == "CUMPRIDA"
    with db.connect() as con:
        acoes = [x["action"] for x in banco(con).ler(
            "SELECT action FROM audit_logs WHERE entity_type = 'PROTOCOLO' "
            "AND entity_id = %s ORDER BY id", (pid,))]
    assert {"PROTOCOLO_EXIGENCIA_ABERTA", "PROTOCOLO_EXIGENCIA_IMPRESSA",
            "PROTOCOLO_EXIGENCIA_CUMPRIDA"} <= set(acoes)


def test_a_tela_recusa_com_a_frase_e_nao_perde_o_texto(cg_casa_logada):
    db, c = cg_casa_logada["db"], cg_casa_logada["c"]
    pid = _protocolo(db)
    tok = _token(c.get(f"/caixa/protocolos/{pid}/exigencias").get_data(as_text=True))
    r = c.post(f"/caixa/protocolos/{pid}/exigencias", data={
        "csrf_token": tok, "atribuicao": "RI",
        "texto": "Trazer a matrícula atualizada do imóvel."})
    corpo = r.get_data(as_text=True)
    assert r.status_code == 200 and "NOTA DEVOLUTIVA" in corpo
    assert "Trazer a matrícula atualizada do imóvel." in corpo
    assert _linhas(db, pid) == []


def test_a_nota_devolutiva_do_ri_traz_a_orientacao(cg_casa_logada):
    db, c = cg_casa_logada["db"], cg_casa_logada["c"]
    ri = _prenotacao_com_nota(db)
    html = c.get(f"/registro-imoveis/protocolo/{ri}/nota").get_data(as_text=True)
    assert "Não escreva nome de terceiros nem CPF/CNPJ" in html
