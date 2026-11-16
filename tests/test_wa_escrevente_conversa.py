"""O escrevente do WhatsApp que conversa (15/11/2026): `wa_escrevente`.

O modelo lê a conversa em turnos, o estado do atendimento e o que o oficial
aprovou, e usa ferramentas para abrir o pedido e a tarefa, estimar valor e
consultar a norma. Aqui o provedor é um roteiro: cada passo é o texto que ele
escreveria, ou as ferramentas que pediria.

NADA AQUI FALA COM A META NEM COM PROVEDOR DE VERDADE (o guarda de
`test_wa_atendente` vale: ele é importado com os auxiliares).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

import agente_provedores as PROV  # noqa: E402
import wa_atendente as AT  # noqa: E402
import wa_escrevente as WE  # noqa: E402
import wa_ferramentas as FERR  # noqa: E402
import wa_manual as MANUAL  # noqa: E402
import wa_pedido as PEDIDO  # noqa: E402
import wa_schema as SCH  # noqa: E402
import wa_vocabulario as VOCAB  # noqa: E402
from test_wa_atendente import (AGORA, CHEGOU, SENHA, Graph, _cfg, _entrada,  # noqa: E402,F401
                               _entrar, _ler, _rodar, _sem_rede, _tabela_de_teste,
                               _token, _um, casa, portal)

MAIS_TARDE = "2026-10-26T10:05:00"


class Roteiro:
    """O falso do provedor: cada passo é um texto ou uma lista de ferramentas.

    Acabados os passos, repete o último. Guarda o que recebeu em cada ida."""

    def __init__(self, *passos):
        self.passos = list(passos)
        self.idas = []

    def __call__(self, pasta, **k):
        self.idas.append({**k, "conversa": json.loads(json.dumps(k["conversa"]))})
        passo = self.passos[min(len(self.idas), len(self.passos)) - 1]
        if isinstance(passo, Exception):
            raise passo
        base = {"entrada": 300, "saida": 80, "cache_escrita": 0, "cache_lida": 5000,
                "modelo": "claude-sonnet-5", "parou": "end_turn", "conteudo_original": []}
        if isinstance(passo, str):
            return {**base, "texto": passo, "chamadas": []}
        return {**base, "texto": "", "parou": "tool_use", "chamadas": [
            {"id": f"t{len(self.idas)}-{n}", "nome": c["nome"], "argumentos": c["argumentos"]}
            for n, c in enumerate(passo)]}


def _ligar(db, **extra):
    _cfg(db, **{SCH.CHAVE_IA_ESCREVENTE: "1", **extra})


def _textos(graph):
    """O que saiu como mensagem — o aviso de leitura não é texto."""
    return [e["payload"]["text"]["body"] for e in graph.enviados
            if e["payload"].get("type") == "text"]


def _do_cliente(ida):
    """O que o modelo leu como fala do cliente, numa ida."""
    return "\n".join(e["texto"] for e in ida["conversa"] if e["tipo"] == "user")


def _pedir(servico, resumo, **mais):
    return [{"nome": FERR.ABRIR_PEDIDO, "argumentos": {"servico": servico, "resumo": resumo,
                                                      **mais}}]


# ---------------------------------------------------------------- o transporte


def test_o_transporte_marca_o_prefixo_para_cache_e_le_os_tokens_dele():
    pedido = PROV.montar_pedido("claude", sistema="estado de agora", sistema_fixo="instrução",
                                cache_ttl="1h", conversa=[{"tipo": "user", "texto": "oi"}],
                                ferramentas=[])
    sistema = pedido["corpo"]["system"]
    assert sistema[0] == {"type": "text", "text": "instrução",
                          "cache_control": {"type": "ephemeral", "ttl": "1h"}}
    assert sistema[1] == {"type": "text", "text": "estado de agora"}
    # sem prefixo, o corpo é o de sempre: quem não usa cache não muda
    assert PROV.montar_pedido("claude", sistema="s", conversa=[], ferramentas=[]
                              )["corpo"]["system"] == "s"
    outro = PROV.montar_pedido("gpt", sistema="estado", sistema_fixo="instrução",
                               conversa=[], ferramentas=[])
    assert outro["corpo"]["messages"][0]["content"] == "instrução\n\nestado"
    with pytest.raises(PROV.AgenteError):
        PROV.montar_pedido("claude", sistema="s", sistema_fixo="f", cache_ttl="2h",
                           conversa=[], ferramentas=[])
    lida = PROV.ler_resposta("claude", json.dumps({
        "content": [{"type": "text", "text": "ok"}], "model": "m", "stop_reason": "end_turn",
        "usage": {"input_tokens": 40, "output_tokens": 9, "cache_creation_input_tokens": 700,
                  "cache_read_input_tokens": 6000}}).encode())
    assert (lida["entrada"], lida["cache_escrita"], lida["cache_lida"]) == (40, 700, 6000)


def test_o_custo_conta_a_escrita_e_a_leitura_do_cache():
    numeros = {"modelo": "claude-sonnet-5-5", "entrada": 1_000_000, "saida": 1_000_000,
               "cache_escrita": 1_000_000, "cache_lida": 1_000_000}
    cfg = {"preco_entrada": None, "preco_saida": None}
    # 2 de entrada, 10 de saída, 2 × 2 de escrita de uma hora, 2 × 0,05 de leitura
    assert WE.custo(numeros, cfg) == pytest.approx(2 + 10 + 4 + 0.10)
    # o nome mais comprido casa primeiro: o 5.5 não é cobrado como o 5
    assert WE.preco_do_modelo("claude-sonnet-5", cfg)[2] == 0.10
    assert WE.custo({**numeros, "modelo": "modelo-desconhecido"}, cfg) is None
    # o preço gravado na tela manda
    assert WE.custo({"modelo": "x", "entrada": 1_000_000}, {"preco_entrada": 3.0,
                                                            "preco_saida": 9.0}) == 3.0


# ---------------------------------------------------------------- a conferência


def test_a_conferencia_da_resposta():
    fontes = "HORÁRIO: das 8 às 17. ESTIMATIVA: Ato — R$ 12,00, com os fundos. prazo de 15 dias"
    assert WE.conferir("Abrimos às 8 e o prazo é de 15 dias.", fontes) == ""
    assert WE.conferir("Abrimos às 08h.", fontes) == ""            # 08 é 8
    assert "número" in WE.conferir("Fica pronto em 99 dias.", fontes)
    assert WE.conferir("A estimativa é de R$ 12,00.", fontes) == ""
    assert "dinheiro" in WE.conferir("Custa R$ 15,00.", fontes)
    assert "marca" in WE.conferir("Anotei o [CPF_01].", fontes + " 01")
    assert "JSON" in WE.conferir('{"acao": "responder"}', fontes)
    assert "longa" in WE.conferir("a" * (WE.TAMANHO_DA_RESPOSTA + 1), fontes)
    assert WE.conferir("", fontes)


def test_o_nome_so_entra_quando_parece_nome():
    assert WE.nome_de_tratamento("maria aparecida") == "Maria"
    assert WE.nome_de_tratamento("🌸Loja 2000") == ""
    assert WE._com_o_nome("Bom dia, {nome}! Posso ajudar?", "Maria") == "Bom dia, Maria! Posso ajudar?"
    assert WE._com_o_nome("Bom dia, {nome}! Posso ajudar?", "") == "Bom dia! Posso ajudar?"


# ---------------------------------------------------------------- o que sobe


def test_a_palavra_do_balcao_sobe_e_o_nome_de_gente_nao():
    m = VOCAB.mascarar
    assert m("Boa tarde! Gostaria de saber sobre Registro de Imóveis, tenho um Título de "
             "Domínio do INCRA") == ("boa tarde! gostaria de saber sobre registro de imóveis, "
                                     "tenho um título de domínio do incra")
    sobe = m("Bom dia, quero a Certidão de Nascimento da minha filha Maria Clara Souza")
    assert "certidão de nascimento" in sobe and "Maria" not in sobe and "Souza" not in sobe
    # quem escreve tudo em maiúsculas também é entendido
    sobe = m("QUERO SEGUNDA VIA DA CERTIDAO DE CASAMENTO DE MARIA DO NASCIMENTO SILVA")
    assert "segunda via da certidao de casamento" in sobe
    assert "MARIA" not in sobe and "NASCIMENTO" not in sobe          # aqui é sobrenome
    # a cidade da casa não é nome de cliente
    assert "riacho fundo" in m("sou de Riacho Fundo", extras=["Riacho Fundo"])
    assert "Riacho" not in m("sou de Riacho Fundo")


def test_meu_pai_faleceu_sobe_e_o_nome_rotulado_continua_escondido():
    m = VOCAB.mascarar
    sobe = m("meu pai faleceu ontem, como faço o registro de óbito?")
    assert "faleceu ontem" in sobe and "registro de óbito" in sobe
    for frase in ("minha mãe maria aparecida de souza quer a certidão",
                  "meu pai é joão da silva", "meu nome é joão pereira da silva",
                  "Pai: João da Silva"):
        sobe = m(frase).lower()
        assert not any(n in sobe for n in ("maria", "aparecida", "souza", "joão",
                                           "pereira", "silva")), frase
    assert "123.456.789-00" not in m("meu CPF é 123.456.789-00 e quero a certidão")


def test_o_resumo_do_pedido_nao_vira_enigma_e_nao_leva_cpf(casa):
    """Achado do ensaio de 15/11: «o imóvel fica em [PESSOA_01]» era a cidade."""
    resumo = FERR._sem_dado("Quer registrar título do INCRA; imóvel em Riacho Fundo; "
                            "tem a sentença da Justiça Federal. CPF 123.456.789-00")
    assert "Riacho Fundo" in resumo and "Justiça Federal" in resumo
    assert "123.456.789-00" not in resumo


# ---------------------------------------------------------------- a conversa


def test_a_resposta_e_o_texto_do_modelo_e_o_prefixo_e_o_que_o_oficial_aprovou(casa):
    db = casa["db"]
    _ligar(db)
    with db.transaction() as con:
        MANUAL.gravar(con, "FIRMA: documento original com foto.\n[confirmar: pagamento]",
                      por="MARIO EXEMPLO", agora=AGORA)
    cid = _entrada(db, "o que levo pra reconhecer firma?", meta_id="wamid.c1")
    modelo, graph = Roteiro("Leve o documento de identidade original."), Graph()
    _rodar(db, casa["pasta"], conversar=modelo, http_post=graph)
    assert _textos(graph) == ["Leve o documento de identidade original."]
    ida = modelo.idas[0]
    assert "Rua Exemplo, 100" in ida["sistema_fixo"]                # o texto-base
    assert "FIRMA: documento original" in ida["sistema_fixo"]       # o manual aprovado
    assert "[confirmar" not in ida["sistema_fixo"]                  # lembrete não é informação
    assert ida["cache_ttl"] == WE.CACHE_TTL and ida["fontes_normativas"] is False
    assert {f["nome"] for f in ida["ferramentas"]} == set(FERR.EXECUTORES)
    # o que muda a cada mensagem não entra no prefixo guardado
    assert "ESTADO DO ATENDIMENTO" in ida["sistema"] and "26/10/2026" not in ida["sistema_fixo"]
    reg = _um(db, "SELECT caso, enviado, chamadas, tokens_cache_lida, custo_usd, lido "
                  "FROM wa_ia_registro WHERE conversa_id=%s", (cid,))
    assert (reg["caso"], reg["enviado"], reg["chamadas"]) == (AT.CASO_DUVIDA, 1, 1)
    assert reg["tokens_cache_lida"] == 5000 and reg["custo_usd"] is not None
    # o aviso de leitura saiu, com o «digitando»
    assert any(e["payload"].get("status") == "read"
               and e["payload"]["typing_indicator"] == {"type": "text"} for e in graph.enviados)


def test_o_pedido_abre_pela_ferramenta_com_tarefa_e_a_conversa_fica_com_a_ia(casa):
    db = casa["db"]
    _ligar(db)
    cid = _entrada(db, "quero registrar meu título de domínio do incra", meta_id="wamid.c2")
    modelo = Roteiro(_pedir("registro_imovel", "Quer registrar título de domínio do INCRA.",
                            falta="trazer o título original"),
                     "Pode sim. Já deixei encaminhado ao Registro de Imóveis.")
    graph = Graph()
    _rodar(db, casa["pasta"], conversar=modelo, http_post=graph)
    assert _textos(graph) == ["Pode sim. Já deixei encaminhado ao Registro de Imóveis."]
    pedido = _um(db, "SELECT * FROM wa_pedido WHERE conversa_id=%s", (cid,))
    assert (pedido["setor"], pedido["servico"], pedido["situacao"]) == (
        "RI", "registro_imovel", PEDIDO.ABERTO)
    assert "Falta: trazer o título original" in pedido["resumo"]
    tarefa = _um(db, "SELECT title, description, priority FROM tasks WHERE source_ref=%s",
                 (f"wa_pedido:{pedido['id']}",))
    assert "Registro de imóvel" in tarefa["title"] and tarefa["priority"] == "MEDIA"
    assert f"/whatsapp/{cid}" in tarefa["description"]
    # o modelo leu o que a ferramenta devolveu antes de responder
    devolvido = modelo.idas[1]["conversa"][-1]["resultados"][0]["conteudo"]
    assert f"Pedido nº {pedido['id']} aberto para Registro de Imóveis" in devolvido
    assert (_um(db, "SELECT modo FROM wa_conversa WHERE id=%s", (cid,))["modo"]
            or SCH.MODO_IA) == SCH.MODO_IA
    reg = _um(db, "SELECT caso, razao, chamadas FROM wa_ia_registro WHERE conversa_id=%s", (cid,))
    assert (reg["caso"], reg["razao"], reg["chamadas"]) == (AT.CASO_PEDIDO, AT.RAZAO_PEDIDO, 2)


def test_na_mensagem_seguinte_o_modelo_ve_a_conversa_e_o_pedido(casa):
    db = casa["db"]
    _ligar(db)
    cid = _entrada(db, "quero uma certidão de nascimento", meta_id="wamid.c3")
    _rodar(db, casa["pasta"], conversar=Roteiro(
        _pedir("certidao_civil", "Segunda via de certidão de nascimento."),
        "Deixei encaminhado ao Registro Civil."))
    pedido = _um(db, "SELECT id FROM wa_pedido WHERE conversa_id=%s", (cid,))
    _entrada(db, "vc encaminhou? quem ficou responsável?", meta_id="wamid.c3b", quando=AGORA)
    modelo = Roteiro("Encaminhei sim, está com o escrevente do Registro Civil.")
    AT.rodada(db, agora=MAIS_TARDE, pasta_de_dados=casa["pasta"], conversar=modelo,
              http_post=Graph())
    ida = modelo.idas[0]
    # a conversa em turnos: o que ela disse, o que a casa respondeu, a pergunta nova
    assert [e["tipo"] for e in ida["conversa"]] == ["user", "assistant", "user"]
    assert "Deixei encaminhado ao Registro Civil." in ida["conversa"][1]["texto"]
    # e o estado, que é o que responde «quem ficou responsável»
    assert f"nº {pedido['id']}, Certidão do registro civil (Registro Civil)" in ida["sistema"]
    assert "aguardando o escrevente" in ida["sistema"]
    # o segundo pedido do mesmo serviço completaria o primeiro: continua um só
    assert _um(db, "SELECT count(*) AS n FROM wa_pedido WHERE conversa_id=%s", (cid,))["n"] == 1


def test_numero_inventado_volta_uma_vez_ao_modelo_e_sai_a_correcao(casa):
    db = casa["db"]
    _ligar(db)
    _entrada(db, "quanto tempo leva a certidão?", meta_id="wamid.c4")
    modelo = Roteiro("Fica pronta em 99 dias.", "Vou confirmar o prazo com o escrevente.")
    graph = Graph()
    _rodar(db, casa["pasta"], conversar=modelo, http_post=graph)
    assert _textos(graph) == ["Vou confirmar o prazo com o escrevente."]
    assert len(modelo.idas) == 2
    assert "conferência automática" in modelo.idas[1]["conversa"][-1]["texto"]
    assert "99" in modelo.idas[1]["conversa"][-1]["texto"]


def test_numero_inventado_duas_vezes_nao_sai_e_o_recado_vai_ao_escrevente(casa):
    db = casa["db"]
    _ligar(db)
    cid = _entrada(db, "quanto tempo leva a certidão de nascimento?", meta_id="wamid.c5")
    graph = Graph()
    _rodar(db, casa["pasta"], conversar=Roteiro("Em 99 dias.", "Em 98 dias."), http_post=graph)
    assert _textos(graph) == [WE.RESPOSTA_SEM_TEXTO]
    pedido = _um(db, "SELECT resumo, situacao FROM wa_pedido WHERE conversa_id=%s", (cid,))
    assert pedido["situacao"] == PEDIDO.ABERTO and "certidão" in pedido["resumo"]
    assert _um(db, "SELECT count(*) AS n FROM tasks WHERE source_type='WHATSAPP'")["n"] == 1


def test_o_cpf_sobe_mascarado_e_a_conversa_segue(casa):
    db = casa["db"]
    _ligar(db)
    cid = _entrada(db, "meu CPF é 123.456.789-00, quero a segunda via do casamento",
                   meta_id="wamid.c6")
    modelo, graph = Roteiro("Anotei. De que cidade é o registro do casamento?"), Graph()
    _rodar(db, casa["pasta"], conversar=modelo, http_post=graph)
    assert len(modelo.idas) == 1
    subiu = json.dumps(modelo.idas[0], ensure_ascii=False, default=str)
    assert "123.456.789-00" not in subiu and "[CPF_01]" in _do_cliente(modelo.idas[0])
    assert _textos(graph) == ["Anotei. De que cidade é o registro do casamento?"]
    reg = _um(db, "SELECT lido FROM wa_ia_registro WHERE conversa_id=%s", (cid,))
    assert "123.456.789-00" not in reg["lido"]


def test_reclamacao_nao_sobe_e_depois_vira_uma_linha_no_historico(casa):
    db = casa["db"]
    _ligar(db)
    cid = _entrada(db, "quero fazer uma reclamação do atendimento de ontem", meta_id="wamid.c7")
    modelo, graph = Roteiro("não devia ser chamado"), Graph()
    _rodar(db, casa["pasta"], conversar=modelo, http_post=graph)
    assert modelo.idas == [] and _textos(graph) == [AT.RESPOSTA_RECLAMACAO]
    assert _um(db, "SELECT setor FROM wa_pedido WHERE conversa_id=%s", (cid,))["setor"] == "GESTAO"
    _entrada(db, "e qual o horário de vocês?", meta_id="wamid.c7b", quando=AGORA)
    depois = Roteiro("Das 8 às 17 horas.")
    AT.rodada(db, agora=MAIS_TARDE, pasta_de_dados=casa["pasta"], conversar=depois,
              http_post=Graph())
    assert WE.RECLAMACAO in _do_cliente(depois.idas[0])
    assert "atendimento de ontem" not in _do_cliente(depois.idas[0])


def test_quem_pede_o_tabeliao_tem_tarefa_na_gestao_mesmo_se_o_modelo_esquecer(casa):
    db = casa["db"]
    _ligar(db)
    cid = _entrada(db, "quero falar com o tabelião", meta_id="wamid.c8")
    graph = Graph()
    _rodar(db, casa["pasta"], conversar=Roteiro("Vou avisar o tabelião."), http_post=graph)
    assert _textos(graph) == ["Vou avisar o tabelião."]
    pedido = _um(db, "SELECT id, setor, servico, resumo FROM wa_pedido WHERE conversa_id=%s",
                 (cid,))
    assert (pedido["setor"], pedido["servico"]) == ("GESTAO", "tabeliao")
    assert pedido["resumo"].startswith(AT.RESUMO_DO_TABELIAO)
    assert "Falar com o tabelião" in _um(
        db, "SELECT title FROM tasks WHERE source_ref=%s", (f"wa_pedido:{pedido['id']}",))["title"]


def test_o_arquivo_nao_sobe_e_o_modelo_sabe_que_chegou(casa):
    db = casa["db"]
    _ligar(db)
    cid = _entrada(db, "", meta_id="wamid.c9", msg={
        "from": "5599900000001", "id": "wamid.c9", "type": "document",
        "document": {"id": "midia-1", "filename": "MATRICULA DE JOAO.pdf",
                     "mime_type": "application/pdf", "caption": "segue a matrícula"}})
    modelo = Roteiro(_pedir("conferir_arquivo", "Mandou a matrícula para conferir.",
                            protocolo=True),
                     "Recebi. O escrevente vai conferir.")
    graph = Graph()
    _rodar(db, casa["pasta"], conversar=modelo, http_post=graph)
    lido = _do_cliente(modelo.idas[0])
    assert "[enviou documento" in lido and "JOAO" not in lido
    assert "Arquivos que a pessoa mandou nas mensagens de agora: 1." in modelo.idas[0]["sistema"]
    pedido = _um(db, "SELECT id FROM wa_pedido WHERE conversa_id=%s", (cid,))
    devolvido = modelo.idas[1]["conversa"][-1]["resultados"][0]["conteudo"]
    assert f"Protocolo de atendimento: WA-2026-{pedido['id']:05d}" in devolvido
    assert "não o protocolo oficial do título" in devolvido
    assert "Arquivos recebidos na conversa: 1." in _um(
        db, "SELECT description FROM tasks WHERE source_ref=%s",
        (f"wa_pedido:{pedido['id']}",))["description"]
    assert (_um(db, "SELECT modo FROM wa_conversa WHERE id=%s", (cid,))["modo"]
            or SCH.MODO_IA) == SCH.MODO_IA


def test_o_andamento_e_conferido_aqui_e_o_codigo_nao_sobe(casa, portal):
    db = casa["db"]
    _ligar(db)
    cid = _entrada(db, "protocolo 12345 código ABC123, já posso buscar?", meta_id="wamid.c10")
    modelo, graph = Roteiro("Ainda está em análise. A previsão é 30/10/2026."), Graph()
    _rodar(db, casa["pasta"], conversar=modelo, http_post=graph)
    assert portal == [("12345", "ABC123")]
    subiu = json.dumps(modelo.idas[0], ensure_ascii=False, default=str)
    assert "ABC123" not in subiu and "12345" not in subiu
    assert "[código informado]" in _do_cliente(modelo.idas[0])
    assert "já posso buscar?" in _do_cliente(modelo.idas[0])
    assert "Protocolo identificado AGORA" in modelo.idas[0]["sistema"]
    assert "situação «em análise»" in modelo.idas[0]["sistema"]
    assert _textos(graph) == ["Ainda está em análise. A previsão é 30/10/2026."]
    reg = _um(db, "SELECT caso, lido FROM wa_ia_registro WHERE conversa_id=%s", (cid,))
    assert reg["caso"] == AT.CASO_ANDAMENTO
    assert reg["lido"] == "identificação: protocolo 12345 (código omitido)"


def test_a_identificacao_errada_conta_a_tentativa_e_nao_diz_qual_errou(casa, portal):
    db = casa["db"]
    _ligar(db)
    cid = _entrada(db, "protocolo 12345 código ERRADO9", meta_id="wamid.c11")
    modelo = Roteiro("Não consegui achar com esses dados. Confere no recibo e manda de novo?")
    _rodar(db, casa["pasta"], conversar=modelo, http_post=Graph())
    estado = modelo.idas[0]["sistema"]
    assert "não conferiram" in estado and "Não diga qual dos dois" in estado
    assert f"Restam {AT.TENTATIVAS_POR_DIA - 1} tentativa(s)" in estado
    assert _um(db, "SELECT caso FROM wa_ia_registro WHERE conversa_id=%s",
               (cid,))["caso"] == AT.CASO_IDENTIFICACAO_FALHOU
    with db.connect() as con:
        assert AT.tentativas_falhas(con, "5599900000001", agora=MAIS_TARDE) == 1


def test_o_valor_sai_da_ferramenta_e_o_de_faixa_pede_o_valor_do_negocio(casa):
    db = casa["db"]
    _tabela_de_teste(db)
    _ligar(db, **{SCH.CHAVE_VALORES: "99.9.1 | Ato de teste\n13.1 | Escritura"})
    _entrada(db, "quanto custa o ato de teste?", meta_id="wamid.c12")
    modelo = Roteiro([{"nome": FERR.CONSULTAR_VALOR, "argumentos": {"item": 1}},
                      {"nome": FERR.CONSULTAR_VALOR, "argumentos": {"item": 2}},
                      {"nome": FERR.CONSULTAR_VALOR, "argumentos": {"item": 9}}],
                     "A estimativa é de R$ 12,00 por ato, com os fundos.")
    graph = Graph()
    _rodar(db, casa["pasta"], conversar=modelo, http_post=graph)
    fixo, faixa, fora = modelo.idas[1]["conversa"][-1]["resultados"]
    assert "ESTIMATIVA" in fixo["conteudo"] and "R$ 12,00" in fixo["conteudo"]
    assert faixa["erro"] and "valor do negócio" in faixa["conteudo"]
    assert fora["erro"] and "LISTA DE VALORES" in fora["conteudo"]
    assert "2 | Escritura (pelo valor do negócio)" in modelo.idas[0]["sistema_fixo"]
    assert _textos(graph) == ["A estimativa é de R$ 12,00 por ato, com os fundos."]
    assert _um(db, "SELECT caso FROM wa_ia_registro")["caso"] == AT.CASO_VALOR


def test_a_falha_do_provedor_deixa_o_recado_e_nao_repete_a_frase(casa):
    db = casa["db"]
    _ligar(db)
    cid = _entrada(db, "preciso de uma procuração", meta_id="wamid.c13")
    graph = Graph()
    falha = Roteiro(PROV.AgenteError("fora do ar", motivo="sem rede"))
    _rodar(db, casa["pasta"], conversar=falha, http_post=graph)
    assert _textos(graph) == [WE.RESPOSTA_INSTABILIDADE]
    assert _um(db, "SELECT count(*) AS n FROM wa_pedido WHERE conversa_id=%s", (cid,))["n"] == 1
    _entrada(db, "é para vender um terreno", meta_id="wamid.c13b", quando=AGORA)
    AT.rodada(db, agora=MAIS_TARDE, pasta_de_dados=casa["pasta"], conversar=falha,
              http_post=graph)
    assert _textos(graph) == [WE.RESPOSTA_INSTABILIDADE]            # uma vez só
    assert _um(db, "SELECT count(*) AS n FROM wa_pedido WHERE conversa_id=%s", (cid,))["n"] == 1


def test_o_teto_de_respostas_entrega_a_conversa_a_uma_pessoa(casa, monkeypatch):
    db = casa["db"]
    _ligar(db)
    monkeypatch.setattr(WE, "RESPOSTAS_POR_DIA", 1)
    cid = _entrada(db, "qual o horário?", meta_id="wamid.c14")
    _rodar(db, casa["pasta"], conversar=Roteiro("Das 8 às 17 horas."))
    _entrada(db, "e no sábado?", meta_id="wamid.c14b", quando=AGORA)
    modelo = Roteiro("não devia ser chamado")
    AT.rodada(db, agora=MAIS_TARDE, pasta_de_dados=casa["pasta"], conversar=modelo,
              http_post=Graph())
    assert modelo.idas == []
    assert _um(db, "SELECT modo FROM wa_conversa WHERE id=%s", (cid,))["modo"] == SCH.MODO_PESSOA


def test_o_ensaio_nao_grava_nada_e_a_linha_seguinte_lembra_da_anterior(casa):
    db = casa["db"]
    _ligar(db)
    with db.connect() as con:
        cfg = AT.configuracao(con)
    modelo = Roteiro(_pedir("escritura", "Quer escritura de compra e venda."),
                     "Deixei encaminhado ao escrevente de Notas.", "É para o mesmo imóvel?")
    r = AT.ensaiar(db, cfg, "quero fazer uma escritura\ne quanto tempo demora?", agora=AGORA,
                   pasta_de_dados=casa["pasta"], conversar=modelo)
    assert [x["saida"] for x in r["resultados"]] == ["pedir", "responder"]
    assert r["resultados"][0]["setor"] == "NOTAS"
    assert "(ensaio)" in modelo.idas[1]["conversa"][-1]["resultados"][0]["conteudo"]
    assert _um(db, "SELECT count(*) AS n FROM wa_pedido")["n"] == 0
    assert _um(db, "SELECT count(*) AS n FROM tasks WHERE source_type='WHATSAPP'")["n"] == 0
    # a segunda linha leu a primeira e a resposta dela
    assert [e["tipo"] for e in modelo.idas[2]["conversa"]] == ["user", "assistant", "user"]


def test_a_conversa_espera_o_audio_que_ainda_nao_foi_transcrito(casa, monkeypatch):
    db = casa["db"]
    _ligar(db, **{SCH.CHAVE_AUDIO_LIGADO: "1"})
    # a transcrição desta rodada não chegou a este áudio (é uma por rodada, neste servidor)
    monkeypatch.setattr(AT, "transcrever_pendentes", lambda *a, **k: 0)
    cid = _entrada(db, "", meta_id="wamid.c15", quando="2026-10-26T09:58:00", msg={
        "from": "5599900000001", "id": "wamid.c15", "type": "audio",
        "audio": {"id": "midia-audio-1", "mime_type": "audio/ogg"}})
    modelo = Roteiro("Não consegui ouvir o áudio. Pode escrever?")
    _rodar(db, casa["pasta"], conversar=modelo, http_post=Graph())
    assert modelo.idas == []
    assert _um(db, "SELECT ia_situacao FROM wa_mensagem WHERE conversa_id=%s",
               (cid,))["ia_situacao"] is None
    # passados os dez minutos, ela não fica presa: a IA diz que não ouviu
    depois, graph = "2026-10-26T10:15:00", Graph()
    AT.rodada(db, agora=depois, pasta_de_dados=casa["pasta"], conversar=modelo, http_post=graph)
    assert WE.AUDIO_SEM_TEXTO in _do_cliente(modelo.idas[0])
    assert _textos(graph) == ["Não consegui ouvir o áudio. Pode escrever?"]


def test_o_tabeliao_pedido_pelo_escrevente_nao_ganha_segunda_tarefa_na_rotina(casa):
    db = casa["db"]
    _ligar(db)
    _entrada(db, "quero falar com o tabelião", meta_id="wamid.c16", quando=AGORA)
    AT.rodada(db, agora=MAIS_TARDE, pasta_de_dados=casa["pasta"],
              conversar=Roteiro("Vou avisar o tabelião."), http_post=Graph())
    assert _um(db, "SELECT count(*) AS n FROM tasks WHERE source_type='WHATSAPP'")["n"] == 1
    monkeypatch_agora = AT.datetime
    try:
        class Relogio(monkeypatch_agora):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 10, 26, 10, 10, 0)
        AT.datetime = Relogio
        AT.acertar_pedidos_abertos(db)
    finally:
        AT.datetime = monkeypatch_agora
    assert _um(db, "SELECT count(*) AS n FROM wa_pedido")["n"] == 1
    assert _um(db, "SELECT count(*) AS n FROM tasks WHERE source_type='WHATSAPP'")["n"] == 1


# ---------------------------------------------------------------- o manual e a tela


def test_o_manual_so_vale_gravado_e_gravar_pede_a_aprovacao(casa):
    db = casa["db"]
    _ligar(db)
    form = {"ia_ligada": "1", "ia_escrevente": "1", "provedor": "claude",
            "texto_base": "HORÁRIO: das 8 às 17.", "valores": ""}
    with db.transaction() as con:
        # a caixa veio com o texto de fábrica e ninguém marcou «aprovo»: nada muda
        avisos = AT.gravar_configuracao(con, {**form, "manual": MANUAL.PADRAO},
                                        por="MARIO", agora=AGORA)
        assert not MANUAL.config(con)["aprovado"]
        assert any("ainda não foi aprovado" in a for a in avisos)
        assert not any("NÃO foi gravado" in a for a in avisos)
        avisos = AT.gravar_configuracao(con, {**form, "manual": "Texto meu."},
                                        por="MARIO", agora=AGORA)
        assert any("NÃO foi gravado" in a for a in avisos)
        avisos = AT.gravar_configuracao(
            con, {**form, "manual": MANUAL.PADRAO, "manual_aprovo": "1"},
            por="MARIO", agora=AGORA)
        gravado = MANUAL.config(con)
        assert gravado["aprovado"] and gravado["por"] == "MARIO" and gravado["lembretes"]
        assert any("colchetes" in a for a in avisos)
    with db.connect() as con:
        cfg = AT.configuracao(con)
    fixo = WE.instrucao_fixa(cfg, gravado["texto"], "Ofício de Exemplo")
    assert "atendimento do Ofício de Exemplo" in fixo
    assert "REGISTRO DE NASCIMENTO" in fixo and "[confirmar" not in fixo
    # o prefixo é o mesmo texto a cada chamada: é o que o provedor guarda
    assert fixo == WE.instrucao_fixa(cfg, gravado["texto"], "Ofício de Exemplo")


def test_a_lista_sugerida_cabe_no_formato_da_lista_de_valores():
    itens = AT.ler_valores(MANUAL.VALORES_SUGERIDOS)
    assert len(itens) == len(MANUAL.VALORES_SUGERIDOS.strip().splitlines())
    assert {i["codigo_tj"] for i in itens if FERR.tabela_de_faixa(i["codigo_tj"])} == {
        "13.1", "16.3", "17.4"}


def test_a_tela_mostra_o_manual_de_fabrica_ate_ele_ser_aprovado(casa):
    db, app = casa["db"], casa["app"]
    _ligar(db)
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    admin = _entrar(app, "mario")
    html = admin.get("/whatsapp/atendente").get_data(as_text=True)
    assert "Manual do atendimento (aprovado pelo oficial)" in html
    assert "Ainda não aprovado" in html and "SEGUNDA VIA DE CERTIDÃO" in html
    assert "lista sugerida" in html and "13.17.2 | Reconhecimento de firma" in html
