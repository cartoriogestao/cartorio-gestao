"""O COMPROVANTE VAI AO CONTATO DA DESPESA — relato #152.

Só de despesa paga, só pelo clique, e o arquivo só se alguém escolher: o documento da
despesa pode ser o recibo da folha inteira.
"""
from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import automacao_avisos as AV
import despesas as DP
import despesas_comprovante as DC
import despesas_inter as INTER
import despesas_recorrentes as RC
import wa_balcao as WA

AGORA = datetime(2026, 10, 30, 9, 0, tzinfo=timezone(timedelta(hours=-3)))
E2E = "E00000000202610301200abcdefghijk"


def _nova(db, **contato):
    with db.transaction() as con:
        return DP.cadastrar(
            con, agora=AGORA, por="mario", origem="MANUAL", chave_origem=None,
            beneficiario_nome="BEATRIZ EXEMPLO", beneficiario_documento="00000000191", valor_centavos=193532,
            vencimento="2026-10-30", forma=DP.PIX_CHAVE, codigo="beatriz@example.com",
            descricao="Folha de pagamento, salário líquido", categoria="PESSOAL",
            documento_especie="Recibo de pagamento", **contato)


def _paga(db, **contato):
    i = _nova(db, **contato)
    with db.transaction() as con:
        DP.banco(con).escrever("UPDATE dp_despesas SET situacao = %s, data_pagamento = %s, "
                               "banco_e2e = %s WHERE id = %s", (DP.PAGA, "2026-10-30", E2E, i))
    return i


def _smtp(monkeypatch, db):
    enviados = []
    monkeypatch.setitem(AV.ENVIO, "email", lambda cfg, senha, **kw: enviados.append((cfg, kw)))
    monkeypatch.setattr(AV, "_senha_do_smtp", lambda pasta, cfg: "")
    monkeypatch.setattr(AV, "configuracao_de_email", lambda con: {"host": "smtp.example.com", "destinos": []})
    return enviados


@pytest.mark.parametrize("email, fone, certo", [
    ("Beatriz@Example.com", "", ("beatriz@example.com", "")),
    ("", "(99) 99900-0000", ("", "5599999000000")),
    ("", "", ("", "")),
])
def test_o_contato_se_padroniza(email, fone, certo):
    assert DP.conferir_contato(email, fone) == certo


@pytest.mark.parametrize("email, fone", [("sem-arroba", ""), ("", "123")])
def test_o_contato_torto_e_recusado(email, fone):
    with pytest.raises(DP.DespesaError):
        DP.conferir_contato(email, fone)


def test_a_recorrente_passa_o_contato_a_despesa_do_mes(cg_casa_logada):
    db = cg_casa_logada["db"]
    with db.transaction() as con:
        RC.cadastrar(con, {"descricao": "Folha de pagamento, salário líquido", "categoria": "PESSOAL",
                           "beneficiario_nome": "BEATRIZ EXEMPLO", "beneficiario_documento": "00000000191", "forma": DP.PIX_CHAVE,
                           "chave_pix": "beatriz@example.com", "valor": 193532, "dia_vencimento": 31,
                           "antecedencia_dias": 25, "documento_especie": "Recibo de pagamento",
                           "primeiro_mes": "2026-10", "contato_email": "beatriz@example.com",
                           "contato_whatsapp": "99999000000"}, por="mario", agora=AGORA)
        [i] = RC.gerar(con, hoje=date(2026, 10, 30), agora=AGORA, por="automação")
        d = DP.despesa(con, i)
    assert (d["contato_email"], d["contato_whatsapp"]) == ("beatriz@example.com", "5599999000000")


def test_o_texto_nao_leva_chave_nem_documento():
    assunto, corpo = DC.texto({"beneficiario_nome": "BEATRIZ EXEMPLO", "descricao": "Folha de outubro",
                               "valor": 193532, "data_pagamento": "2026-10-30", "banco_e2e": E2E,
                               "codigo": "beatriz@example.com", "beneficiario_documento": "00000000191"})
    assert "1.935,32" in corpo and "30/10/2026" in corpo and E2E in corpo
    assert "beatriz@example.com" not in corpo and "00000000191" not in corpo


def test_so_a_despesa_paga_tem_comprovante(cg_casa_logada, monkeypatch):
    db = cg_casa_logada["db"]
    enviados = _smtp(monkeypatch, db)
    i = _nova(db, contato_email="beatriz@example.com")
    with pytest.raises(DP.DespesaError, match="depois de a despesa estar paga"):
        DC.enviar_email(db, i, por="mario", agora=AGORA)
    assert enviados == []


def test_o_email_vai_ao_contato_sem_arquivo_e_o_endereco_nao_vai_ao_rastro(cg_casa_logada, monkeypatch):
    db = cg_casa_logada["db"]
    enviados = _smtp(monkeypatch, db)
    i = _paga(db, contato_email="beatriz@example.com")
    with db.transaction() as con:
        DP.guardar_anexo(con, i, nome_arquivo="recibo.pdf", conteudo=b"%PDF", pasta=cg_casa_logada["dados"],
                         usuario_id=None, agora="2026-10-30T09:00:00")
    DC.enviar_email(db, i, por="mario", agora=AGORA)
    [(cfg, kw)] = enviados
    assert cfg["destinos"] == ["beatriz@example.com"]
    assert [a[0] for a in kw["anexos"]] == [f"demonstrativo_de_pagamento_{i}.pdf"], "o recibo não vai sozinho"
    with db.connect() as con:
        rastro = [e for e in DP.eventos(con, i) if e["operacao"] == "COMPROVANTE"]
    assert len(rastro) == 1 and "beatriz@example.com" not in rastro[0]["mensagem"]


def test_o_arquivo_escolhido_vai_e_o_de_outra_despesa_nao(cg_casa_logada, monkeypatch):
    db = cg_casa_logada["db"]
    enviados = _smtp(monkeypatch, db)
    i, outra = _paga(db, contato_email="beatriz@example.com"), _paga(db)
    with db.transaction() as con:
        meu = DP.guardar_anexo(con, i, nome_arquivo="pix.pdf", conteudo=b"%PDF", pasta=cg_casa_logada["dados"],
                               usuario_id=None, agora="2026-10-30T09:00:00")
        alheio = DP.guardar_anexo(con, outra, nome_arquivo="folha.pdf", conteudo=b"%PDF2",
                                  pasta=cg_casa_logada["dados"], usuario_id=None, agora="2026-10-30T09:00:00")
    with pytest.raises(DP.DespesaError, match="não é desta despesa"):
        DC.enviar_email(db, i, por="mario", agora=AGORA, anexo_id=alheio)
    DC.enviar_email(db, i, por="mario", agora=AGORA, anexo_id=meu)
    assert enviados[0][1]["anexos"][1] == ("pix.pdf", b"%PDF", "application/pdf")


def _despesa_paga_para_o_papel():
    return {"id": 7, "situacao": DP.CONCILIADA, "beneficiario_nome": "BEATRIZ EXEMPLO",
            "beneficiario_documento": "00000000191", "descricao": "Folha de pagamento de outubro",
            "valor": 193532, "data_pagamento": "2026-10-30", "banco_e2e": E2E, "codigo": "beatriz@example.com",
            "banco_recebedor_nome": "Beatriz Exemplo", "banco_recebedor_documento": "***.000.001-**"}


def test_o_pdf_diz_o_que_e_e_nao_leva_cpf_inteiro_nem_chave():
    import pymupdf
    pdf = DC.pdf_do_demonstrativo(_despesa_paga_para_o_papel(), {"unit_name": "SERVENTIA EXEMPLO"}, AGORA)
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        lido = " ".join(doc[0].get_text().split())
    assert "DEMONSTRATIVO DE PAGAMENTO" in lido and "1.935,32" in lido and E2E in lido
    assert "Não substitui o comprovante emitido pelo banco" in lido and "SERVENTIA EXEMPLO" in lido
    assert "***.000.001-**" in lido
    assert "00000000191" not in lido and "beatriz@example.com" not in lido


def test_o_travessao_da_descricao_nao_vira_interrogacao():
    assert DC._para_a_fonte("Folha — 10/2026") == "Folha - 10/2026"


@pytest.mark.parametrize("mudanca", [{"banco_e2e": ""}, {"situacao": DP.AUTORIZADA},
                                     {"recebedor_divergente": "O banco informa outro recebedor."}])
def test_sem_e2e_sem_pagamento_ou_em_duvida_nao_ha_demonstrativo(mudanca):
    with pytest.raises(DP.DespesaError, match="demonstrativo sai depois"):
        DC.pdf_do_demonstrativo({**_despesa_paga_para_o_papel(), **mudanca}, {}, AGORA)


def test_o_cpf_inteiro_do_extrato_se_guarda_mascarado(cg_casa_logada):
    db = cg_casa_logada["db"]
    i = _nova(db)
    with db.transaction() as con:
        DP.gravar_dados_do_banco(con, i, e2e=E2E, nome="Beatriz Exemplo", documento="00000000191")
        DP.gravar_dados_do_banco(con, i, nome="", documento="")
        d = DP.despesa(con, i)
    assert (d["banco_e2e"], d["banco_recebedor_nome"], d["banco_recebedor_documento"]) == \
        (E2E, "Beatriz Exemplo", "***.000.001-**")


def test_o_extrato_completa_o_e2e_da_despesa_ja_conciliada(cg_casa_logada):
    db = cg_casa_logada["db"]
    i = _nova(db)
    with db.transaction() as con:
        DP.banco(con).escrever("UPDATE dp_despesas SET situacao = %s, extrato_id = %s WHERE id = %s",
                               (DP.CONCILIADA, "77", i))
    transacoes = [{"idTransacao": "77", "detalhes": {"endToEndId": E2E, "nomeRecebedor": "Beatriz Exemplo",
                                                     "cpfCnpjRecebedor": "00000000191"}}]
    INTER._completar_as_conciliadas(db, transacoes, por="automação", quando=AGORA)
    with db.connect() as con:
        d = DP.despesa(con, i)
    assert d["banco_e2e"] == E2E and d["banco_recebedor_documento"] == "***.000.001-**"
    assert d["recebedor_divergente"] == "" and DC.pode_gerar(d)


def test_a_ja_conciliada_de_outro_recebedor_fica_em_duvida_e_sem_demonstrativo(cg_casa_logada):
    db = cg_casa_logada["db"]
    i = _nova(db)
    with db.transaction() as con:
        DP.banco(con).escrever("UPDATE dp_despesas SET situacao = %s, extrato_id = %s WHERE id = %s",
                               (DP.CONCILIADA, "78", i))
    transacoes = [{"idTransacao": "78", "detalhes": {"endToEndId": E2E, "nomeRecebedor": "CARLA EXEMPLO",
                                                     "cpfCnpjRecebedor": "00000000272"}}]
    INTER._completar_as_conciliadas(db, transacoes, por="automação", quando=AGORA)
    with db.connect() as con:
        d = DP.despesa(con, i)
        assert [x["id"] for x in DP.recebedor_em_duvida(con)] == [i]
    assert "CARLA EXEMPLO" in d["recebedor_divergente"] and not DC.pode_gerar(d)
    assert d["situacao"] == DP.CONCILIADA, "a linha do livro não muda sozinha"


def test_o_whatsapp_na_janela_manda_o_pdf(cg_casa_logada, monkeypatch, tmp_path):
    import wa_midia as MIDIA
    db = cg_casa_logada["db"]
    i = _paga(db, contato_whatsapp="5599999000000")
    with db.transaction() as con:
        conversa = DP.banco(con).escrever(
            "INSERT INTO wa_conversa (wa_id) VALUES (%s) RETURNING id", ("5599999000000",))[0]["id"]
    monkeypatch.setattr(WA, "ultima_do_cliente", lambda con, c: [
        {"direcao": WA.DIR_IN, "criado_em": "2026-10-30T08:00:00"}])
    monkeypatch.setattr(WA, "ler_config", lambda con, chave: "x")
    subidos = []
    monkeypatch.setattr(MIDIA, "subir", lambda token, phone, dados, mime, nome: subidos.append((dados[:4], mime)) or "m1")
    pedidos = []
    monkeypatch.setattr(WA, "postar_envio", lambda pedido: pedidos.append(pedido) or "meta1")
    DC.enviar_whatsapp(db, i, por="mario", agora=AGORA, agora_texto="2026-10-30T09:00:00", pasta_arquivos=tmp_path)
    assert subidos == [(b"%PDF", "application/pdf")]
    assert pedidos[0]["payload"]["type"] == "document"
    with db.connect() as con:
        assert [e for e in DP.eventos(con, i) if e["operacao"] == "COMPROVANTE"]
        assert conversa


def test_fora_da_janela_nao_vai_a_meta_e_a_ficha_oferece_o_link(cg_casa_logada, monkeypatch):
    db = cg_casa_logada["db"]
    monkeypatch.setattr(WA, "postar_envio", lambda pedido: pytest.fail("não devia ir à Meta"))
    i = _paga(db, contato_whatsapp="5599999000000")
    with pytest.raises(DP.DespesaError, match="24 horas"):
        DC.enviar_whatsapp(db, i, por="mario", agora=AGORA, agora_texto="2026-10-30T09:00:00",
                           pasta_arquivos=None)
    with db.connect() as con:
        na_ficha = DC.whatsapp_na_ficha(con, DP.despesa(con, i), "2026-10-30T09:00:00")
    assert na_ficha["janela_aberta"] is False
    assert na_ficha["link"].startswith("https://wa.me/5599999000000?text=")


def test_a_ficha_mostra_o_contato_e_so_paga_mostra_o_envio(cg_casa_logada):
    db, c = cg_casa_logada["db"], cg_casa_logada["c"]
    espera, paga = _nova(db), _paga(db, contato_email="beatriz@example.com")
    assert "Baixar o demonstrativo" not in c.get(f"/administrativo/despesas/{espera}").get_data(as_text=True)
    html = c.get(f"/administrativo/despesas/{paga}").get_data(as_text=True)
    assert "Baixar o demonstrativo" in html and "beatriz@example.com" in html
