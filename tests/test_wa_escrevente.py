"""O atendimento do escrevente no WhatsApp (10/11/2026).

A IA responde com o ofício, a base da casa e a norma, e quando a pessoa quer
o serviço feito abre um pedido para o escrevente. A conversa não passa para
pessoa. Sem a chave `ia_escrevente`, o comportamento de antes continua — isso
está em `test_wa_atendente` e `test_wa_triagem`.

DESDE 15/11/2026 A CONVERSA É DE `wa_escrevente` (o modelo com ferramentas, e
não mais a ficha JSON): o fluxo inteiro está em `test_wa_escrevente_conversa`.
Aqui ficam as regras que continuam em `wa_atendente` e servem aos dois.

Nada aqui fala com provedor nem com a Meta. O conhecimento injetado nos casos
de decisão é fixo, para o número permitido ser o do teste; um caso lê a base
de verdade.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

import wa_atendente as AT  # noqa: E402
import wa_conhecimento as CONHEC  # noqa: E402
import wa_pedido as PEDIDO  # noqa: E402
import wa_schema as SCH  # noqa: E402
from test_wa_atendente import (AGORA, CHEGOU, SENHA, TEXTO_BASE, Graph, Modelo,  # noqa: E402
                               _cfg, _entrada, _entrar, _rodar, _token, _um, casa)

CONHECIMENTO = ("A apresentação do título não se recusa por falta de informação, "
                "art. 12 da lei de registros.")


def _ligar(db, **extra):
    _cfg(db, **{SCH.CHAVE_IA_ESCREVENTE: "1", **extra})


def _fixar_conhecimento(monkeypatch, texto=CONHECIMENTO):
    monkeypatch.setattr(AT.CONHEC, "para_o_atendimento", lambda *a, **k: texto)


def test_o_conhecimento_de_verdade_traz_o_oficio_e_a_norma():
    texto = CONHEC.para_o_atendimento("certidão de nascimento", setor="RCPN")
    assert "escrevente" in texto.lower()
    assert "Registro Civil" in texto
    assert "não decide o ato" in texto
    # A base normativa entra com a citação. Sem ela, a IA não tem lei para citar.
    assert "=== A NORMA PERTINENTE" in texto
    assert "art." in texto.lower()










def test_a_chave_vazia_liga_o_escrevente_e_o_zero_fica_desligado(casa):
    db = casa["db"]
    _cfg(db)
    with db.connect() as con:
        assert AT.configuracao(con)["escrevente"] is False
    with db.transaction() as con:
        assert AT.adotar_escrevente_se_vazio(con) is True
    with db.connect() as con:
        assert AT.configuracao(con)["escrevente"] is True
    with db.transaction() as con:
        assert AT.adotar_escrevente_se_vazio(con) is False
        AT.gravar_configuracao(
            con, {"ia_ligada": "1", "provedor": "claude"},
            por="MARIO EXEMPLO", agora=AGORA)
    assert _um(db, "SELECT valor FROM wa_config WHERE chave=%s",
               (SCH.CHAVE_IA_ESCREVENTE,))["valor"] == "0"
    with db.connect() as con:
        assert AT.configuracao(con)["escrevente"] is False
    with db.transaction() as con:
        assert AT.adotar_escrevente_se_vazio(con) is False


def test_titulo_de_dominio_e_do_registro_de_imoveis():
    import wa_fila as FILA
    setores = [s for s, _m, _p in FILA.setores_pelo_texto(
        "quero registrar um título de domínio do INCRA")]
    assert "RI" in setores


def test_o_encaminhamento_leva_o_fato_e_nao_repete_o_cardapio():
    decisao = {
        "caso": AT.CASO_PEDIDO, "razao": AT.RAZAO_INSISTENCIA,
        "motivo": "o cliente seguiu escrevendo depois de 10 respostas automáticas",
        "resposta": AT.TEXTO_PEDIDO,
        "pedido": {"setor": "RI", "servico": "registro_imovel",
                   "resumo": "o cliente seguiu escrevendo depois de 10 respostas automáticas"},
    }
    assunto = "quero registrar um título de domínio do INCRA no imóvel"
    ido = AT.completar_encaminhamento(decisao, assunto=assunto, ultimo="")
    assert ido["pedido"]["resumo"].startswith("quero registrar")
    assert "Me diga o serviço" not in ido["resposta"]
    assert ido["resposta"] == "Vou passar ao escrevente de Registro de Imóveis."
    de_novo = AT.completar_encaminhamento(
        {"caso": AT.CASO_PEDIDO, "razao": AT.RAZAO_INSISTENCIA,
         "resposta": AT.TEXTO_PEDIDO,
         "pedido": {"setor": "RI", "servico": "registro_imovel",
                    "resumo": "o cliente seguiu escrevendo depois de 10 respostas automáticas"}},
        assunto=assunto, ultimo=ido["resposta"])
    assert de_novo["resposta"] == "" and de_novo["ja_avisado"] is True


def test_a_resposta_do_modelo_fica_e_o_audio_sem_texto_pede_para_escrever():
    boa = {
        "caso": AT.CASO_PEDIDO, "razao": AT.RAZAO_PEDIDO,
        "resposta": "O escrevente vê o título e te diz o caminho.",
        "pedido": {"setor": "RI", "servico": "registro_imovel",
                   "resumo": "Quer registrar título de domínio."},
    }
    ficou = AT.completar_encaminhamento(boa, assunto="outra coisa qualquer aqui", ultimo="")
    assert ficou["resposta"].startswith("O escrevente vê")
    assert ficou["pedido"]["resumo"].startswith("Quer registrar")
    audio = {
        "caso": AT.CASO_PEDIDO, "razao": AT.RAZAO_FALHA,
        "motivo": "mensagem sem texto (anexo, ou áudio sem transcrição)",
        "resposta": AT.TEXTO_PEDIDO,
        "pedido": {"setor": "ATENDIMENTO", "servico": "orientacao",
                   "resumo": "mensagem sem texto"},
    }
    pedido = AT.completar_encaminhamento(audio, assunto="", ultimo="")
    assert "ouvir" in pedido["resposta"].lower()
    assert "Me diga o serviço" not in pedido["resposta"]


def test_o_relato_do_escrevente_nao_leva_o_cpf():
    limpo = AT._sem_dado_pessoal("meu CPF é 123.456.789-00, quero uma certidão")
    assert "123.456.789-00" not in limpo
    assert "certidão" in limpo
    assert AT._sem_dado_pessoal("quero registrar o imóvel") == "quero registrar o imóvel"


def test_falar_com_o_tabeliao_abre_pedido_da_gestao():
    assert AT.pede_o_tabeliao("quero falar com o tabelião")
    assert AT.pede_o_tabeliao("me passa para o oficial")
    assert not AT.pede_o_tabeliao("quero falar com o escrevente")
    assert not AT.pede_o_tabeliao("o tabelião assinou a escritura")
    assert not AT.pede_o_tabeliao("quero uma certidão do oficial de registro")
    d = AT._virar_pedido({
        "passar": "GESTAO", "razao": AT.RAZAO_PEDIU_PESSOA,
        "resumo": AT.RESUMO_DO_TABELIAO, "caso": "duvida", "resposta": "",
    })
    assert d["caso"] == AT.CASO_PEDIDO
    assert d["pedido"]["setor"] == "GESTAO"
    assert d["pedido"]["servico"] == "orientacao"
    assert d["resposta"] == "Vou avisar o tabelião."
    assert "Gestão" not in d["resposta"]
    repetido = AT.completar_encaminhamento(
        d, assunto="quero falar com o tabelião e registrar o imóvel",
        ultimo="Vou avisar o tabelião.")
    assert repetido["resposta"] == "" and repetido["ja_avisado"] is True
    assert repetido["pedido"]["setor"] == "GESTAO"
    texto = AT._relato_da_tarefa(AT.RESUMO_DO_TABELIAO, "quero registrar o imóvel " * 20)
    assert texto.startswith("Pediu para falar com o tabelião.")
    assert "registrar o imóvel" in texto
    assert "Vou avisar o tabelião." in AT.instrucao_do_escrevente(
        {"texto_base": "", "valores": []}, "")


def test_falar_com_o_escrevente_abre_o_pedido_do_setor():
    assert AT.pede_pessoa("quero falar com o escrevente")
    assert not AT.pede_o_tabeliao("quero falar com o escrevente")
    d = AT._virar_pedido({
        "passar": "RI", "razao": AT.RAZAO_PEDIU_PESSOA,
        "resumo": "Pediu para falar com o escrevente.",
    })
    assert d["pedido"]["setor"] == "RI"
    assert d["resposta"] == "Vou passar ao escrevente de Registro de Imóveis."
    assert "Pode falar comigo" not in d["resposta"]
