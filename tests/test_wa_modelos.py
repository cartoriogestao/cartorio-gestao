"""Os modelos da Meta no WhatsApp (27/10/2026) — `wa_modelos`, a tela e o balcão.

O QUE SE PROVA AQUI
    - o pedido tem a forma da Graph (`"type": "template"`, nome, idioma pt_BR,
      um componente `body` com os parâmetros) e as variáveis saem NA ORDEM do
      corpo aprovado;
    - os cinco nomes e a quantidade de variáveis de cada um são os combinados,
      e o nome gravado na configuração ganha do padrão;
    - a conferência recusa ANTES da rede: modelo desconhecido, quantidade
      errada, variável vazia, CPF, CNPJ, valor, pix, e-mail, quebra de linha,
      número que não é número, data que não existe, link sem https;
    - o interruptor nasce DESLIGADO, e desligado nada sai — nem com o token;
    - o telefone vai com o 55 do Brasil (E.164), e o que não é número
      brasileiro com DDD é recusado;
    - a tela de configuração mostra os cinco nomes e o interruptor; só o
      ADMIN grava; nome fora da regra da Meta não grava nada;
    - no balcão, fora da janela de 24 h, «Reabrir com o modelo» manda o
      `cartorio_retomar_atendimento` para o `wa_id` da conversa; desligado, o
      botão não aparece e a rota recusa sem falar com a rede.

NADA AQUI FALA COM A META. `wa_balcao._http_post_json` é trocado por um falso
(ou por um guarda que estoura), e o token mora num `ler_segredo` falso — nada
vai ao cofre de verdade. Equipe fictícia (mario, beatriz). Testes escritos para
a máquina do merge (nada de pytest nesta máquina, por ordem do oficial).
"""
from __future__ import annotations

import itertools
import json
import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import andamento_avisos as AA  # noqa: E402
import andamento_schema as AS  # noqa: E402
import wa_balcao as WA  # noqa: E402
import wa_modelos as WM  # noqa: E402
import wa_schema as SCH  # noqa: E402
from bd_nativo import banco  # noqa: E402

SENHA = "Senha#12345"
TOKEN_WA = "token-wa-de-teste"
PHONE_ID = "123456789"
WA_ID = "5599900000123"


# ------------------------------------------------------------------ os falsos


@pytest.fixture(autouse=True)
def _sem_rede(monkeypatch):
    def proibido(*a, **k):
        raise AssertionError("o teste tentou falar com a Meta de verdade")
    monkeypatch.setattr(WA, "_http_post_json", proibido)


class Graph:
    """O falso da Graph: guarda o pedido e devolve um id único."""

    _ids = itertools.count(1)

    def __init__(self, status=200, corpo=None):
        self.pedidos: list[dict] = []
        self.status = status
        self.corpo = corpo

    def __call__(self, url, payload, headers, timeout=None):
        self.pedidos.append({"url": url, "payload": payload, "headers": headers})
        if self.corpo is not None:
            return self.status, self.corpo
        return self.status, json.dumps({"messages": [{"id": f"wamid.modelo-{next(Graph._ids)}"}]})


def _cfg_falsa(monkeypatch, **valores) -> dict:
    """A configuração inteira num dicionário — para os testes sem banco."""
    cfg = {SCH.CHAVE_MODELOS_APROVADOS: "1", SCH.CHAVE_TOKEN: TOKEN_WA,
           SCH.CHAVE_PHONE: PHONE_ID, SCH.CHAVE_NOME_NO_MODELO: "de Exemplo"}
    cfg.update(valores)
    monkeypatch.setattr(WA, "ler_config", lambda con, chave: cfg.get(chave, ""))
    return cfg


def _token_falso(monkeypatch):
    """O access_token sem passar pelo cofre de verdade."""
    import cofre_cred
    original = cofre_cred.ler_segredo

    def ler(con, nome, chave):
        if chave == SCH.CHAVE_TOKEN:
            return TOKEN_WA
        return original(con, nome, chave)
    monkeypatch.setattr(cofre_cred, "ler_segredo", ler)


def _gravar(db, **valores):
    with db.transaction() as con:
        for chave, valor in valores.items():
            WA.gravar_config(con, chave, valor)


def _ligar(db, monkeypatch, **extra):
    _token_falso(monkeypatch)
    valores = {SCH.CHAVE_MODELOS_APROVADOS: "1", SCH.CHAVE_PHONE: PHONE_ID,
               SCH.CHAVE_NOME_NO_MODELO: "de Exemplo"}
    valores.update(extra)
    _gravar(db, **valores)


# ------------------------------------------------------------------ o pedido


def test_o_pedido_do_modelo_tem_a_forma_da_graph_e_as_variaveis_na_ordem(monkeypatch):
    _cfg_falsa(monkeypatch)
    pedido = WM.montar_envio_modelo(None, "5599999990000", WM.PRAZO,
                                    ["de Exemplo", "12345", "05/11/2026"])
    assert pedido["url"] == f"https://graph.facebook.com/{WA.GRAPH_VER}/{PHONE_ID}/messages"
    assert pedido["headers"]["Authorization"] == f"Bearer {TOKEN_WA}"
    assert pedido["payload"] == {
        "messaging_product": "whatsapp",
        "to": "5599999990000",
        "type": "template",
        "template": {
            "name": "cartorio_prenotacao_vencendo",
            "language": {"code": "pt_BR"},
            "components": [{"type": "body", "parameters": [
                {"type": "text", "text": "de Exemplo"},
                {"type": "text", "text": "12345"},
                {"type": "text", "text": "05/11/2026"},
            ]}],
        },
    }
    # A cópia local é o corpo com as variáveis no lugar certo.
    assert pedido["texto"] == ("Cartório de Exemplo: a prenotação nº 12345 vence em "
                               "05/11/2026. Procure o cartório.")


def test_cada_modelo_tem_o_nome_e_as_variaveis_combinados():
    combinados = {
        WM.EXIGENCIA: ("cartorio_exigencia", 2),
        WM.PRONTO: ("cartorio_pronto_retirar", 2),
        WM.PRAZO: ("cartorio_prenotacao_vencendo", 3),
        WM.PESQUISA: ("cartorio_pesquisa_satisfacao", 3),
        WM.RETOMAR: ("cartorio_retomar_atendimento", 1),
    }
    assert set(WM.MODELOS) == set(combinados) == set(WM.ORDEM)
    for qual, (nome, n) in combinados.items():
        spec = WM.MODELOS[qual]
        assert spec["padrao"] == nome
        assert len(spec["variaveis"]) == n
        assert spec["variaveis"][0] == WM.CARTORIO          # o {{1}} é sempre o cartório
        assert spec["corpo"].startswith("Cartório {{1}}:")
        for i in range(1, n + 1):
            assert "{{" + str(i) + "}}" in spec["corpo"]
        assert "{{" + str(n + 1) + "}}" not in spec["corpo"]
        assert spec["chave"] in SCH.CHAVES_CONFIG
    assert SCH.CHAVE_MODELOS_APROVADOS in SCH.CHAVES_CONFIG
    assert SCH.CHAVE_NOME_NO_MODELO in SCH.CHAVES_CONFIG


def test_o_nome_gravado_na_configuracao_ganha_do_padrao(monkeypatch):
    _cfg_falsa(monkeypatch, **{SCH.CHAVE_MODELO_PRONTO: "pronto_v2"})
    pedido = WM.montar_envio_modelo(None, "5599999990000", WM.PRONTO, ["de Exemplo", "1"])
    assert pedido["payload"]["template"]["name"] == "pronto_v2"
    assert WM.nome_do_modelo(None, WM.EXIGENCIA) == "cartorio_exigencia"


@pytest.mark.parametrize("qual,variaveis,trecho", [
    ("INVENTADO", ["de Exemplo"], "desconhecido"),
    (WM.PRONTO, ["de Exemplo"], "tem 2 variável"),
    (WM.PRONTO, ["de Exemplo", "1", "2"], "tem 2 variável"),
    (WM.PRONTO, ["de Exemplo", ""], "vazia"),
    (WM.PRONTO, ["", "1"], "vazia"),
    (WM.PRONTO, ["de Exemplo", "000.000.001-91"], "CPF"),
    (WM.PRONTO, ["de Exemplo", "12.345.678/0001-00"], "CNPJ"),   # dígito inválido de propósito
    (WM.PRONTO, ["de Exemplo", "R$ 10"], "R$"),
    (WM.PRONTO, ["de Exemplo", "1.234,56"], "valor"),
    (WM.PRONTO, ["de Exemplo", "pix"], "pix"),
    (WM.PRONTO, ["de Exemplo", "BEATRIZ EXEMPLO"], "só o número"),
    (WM.PRONTO, ["de\nExemplo", "1"], "quebra de linha"),
    (WM.PRONTO, ["de     Exemplo", "1"], "quatro"),
    (WM.PRONTO, ["Cartório de Exemplo", "1"], "não repete"),
    (WM.RETOMAR, ["fulano@exemplo.invalid"], "e-mail"),
    (WM.PRAZO, ["de Exemplo", "1", "2026-11-05"], "dd/mm/aaaa"),
    (WM.PRAZO, ["de Exemplo", "1", "31/02/2026"], "não é uma data"),
    (WM.PESQUISA, ["de Exemplo", "1", "http://exemplo.invalid/r/X"], "https://"),
    (WM.PESQUISA, ["de Exemplo", "1", "https://exemplo.invalid/r/X Y"], "https://"),
])
def test_a_conferencia_recusa_antes_da_rede(monkeypatch, qual, variaveis, trecho):
    _cfg_falsa(monkeypatch)
    with pytest.raises(WM.ModeloRecusado) as erro:
        WM.montar_envio_modelo(None, "5599999990000", qual, variaveis)
    assert trecho in str(erro.value)
    # E quem chama do jeito de sempre não chega à rede: o guarda estouraria.
    with pytest.raises(WA.EnvioErro):
        WA.postar_envio(WM.montar_envio_modelo(None, "5599999990000", qual, variaveis))


def test_a_recusa_e_erro_de_envio_e_erro_de_regra():
    erro = WM.ModeloRecusado("x")
    assert isinstance(erro, WA.EnvioErro) and isinstance(erro, ValueError)


def test_nome_de_modelo_fora_da_regra_da_meta_e_recusado(monkeypatch):
    _cfg_falsa(monkeypatch, **{SCH.CHAVE_MODELO_RETOMAR: "Retomar Atendimento"})
    with pytest.raises(WM.ModeloRecusado, match="regra da Meta"):
        WM.montar_envio_modelo(None, WA_ID, WM.RETOMAR, ["de Exemplo"])


def test_destino_que_nao_e_numero_internacional_e_recusado(monkeypatch):
    _cfg_falsa(monkeypatch)
    with pytest.raises(WM.ModeloRecusado, match="internacional"):
        WM.montar_envio_modelo(None, "123", WM.RETOMAR, ["de Exemplo"])


# ------------------------------------------------------------------ o interruptor


def test_desligado_nada_sai_nem_com_o_token(monkeypatch):
    _cfg_falsa(monkeypatch, **{SCH.CHAVE_MODELOS_APROVADOS: ""})
    assert WM.ligado(None) is False
    assert WM.falta_para_enviar(None) == WM.DESLIGADO
    with pytest.raises(WM.ModeloRecusado, match="aprovados"):
        WM.montar_envio_modelo(None, WA_ID, WM.RETOMAR, ["de Exemplo"])


def test_ligado_sem_credencial_diz_o_que_falta(monkeypatch):
    _cfg_falsa(monkeypatch, **{SCH.CHAVE_TOKEN: ""})
    assert WM.falta_para_enviar(None) == WM.SEM_CREDENCIAL
    with pytest.raises(WM.ModeloRecusado, match="access_token"):
        WM.montar_envio_modelo(None, WA_ID, WM.RETOMAR, ["de Exemplo"])


def test_ligado_sem_nome_do_cartorio_diz_o_que_falta(monkeypatch):
    _cfg_falsa(monkeypatch, **{SCH.CHAVE_NOME_NO_MODELO: ""})
    assert WM.falta_para_enviar(None, {"unit_name": "NOME DA SERVENTIA"}) == WM.SEM_NOME
    assert WM.falta_para_enviar(None, {"ri_cidade": "Exemplo"}) == ""


def test_o_interruptor_nasce_desligado(cg_casa):
    with cg_casa["db"].connect() as con:
        assert WM.ligado(con) is False
        assert banco(con).um("SELECT valor FROM wa_config WHERE chave=%s",
                             (SCH.CHAVE_MODELOS_APROVADOS,))["valor"] == ""


# ------------------------------------------------------------------ o nome do cartório


@pytest.mark.parametrize("serventia,esperado", [
    ({"ri_cidade": "Exemplo"}, "de Exemplo"),
    ({"ri_cidade": "Vila Exemplo/MA"}, "de Vila Exemplo"),
    ({"ri_cidade": "Vila Exemplo - MA", "unit_name": "Outro"}, "de Vila Exemplo"),
    ({"unit_name": "Serventia Extrajudicial do Ofício Único de Vila Exemplo/MA"},
     "de Vila Exemplo"),
    ({"unit_name": "NOME DA SERVENTIA"}, ""),
    ({}, ""),
    (None, ""),
])
def test_o_complemento_sai_da_serventia(serventia, esperado):
    assert WM.derivar_nome_no_modelo(serventia) == esperado


def test_a_configuracao_ganha_do_derivado(monkeypatch):
    _cfg_falsa(monkeypatch, **{SCH.CHAVE_NOME_NO_MODELO: "do  Exemplo"})
    assert WM.nome_no_modelo(None, {"ri_cidade": "Outra"}) == "do Exemplo"


# ------------------------------------------------------------------ o telefone


@pytest.mark.parametrize("cadastro,e164", [
    ("(99) 99999-0000", "5599999990000"),
    ("(99) 90000-0000", "5599900000000"),
    ("99 9999-0000", "559999990000"),
    ("+55 (99) 99999-0000", "5599999990000"),
    ("5599999990000", "5599999990000"),
    ("0 99 99999-0000", "5599999990000"),
    ("(55) 99999-0000", "5555999990000"),        # o DDD 55 existe
    ("55 55 99999-0000", "5555999990000"),
])
def test_o_telefone_vai_com_o_55(cadastro, e164):
    assert WM.telefone_e164(cadastro) == e164


@pytest.mark.parametrize("cadastro,trecho", [
    ("", "Sem telefone"),
    ("9999-0000", "DDD"),
    ("+1 650 555 1234", "outro país"),
    ("(09) 99999-0000", "não existe"),
    ("(99) 89999-0000", "começa com 9"),
    ("(99) 0999-0000", "0 ou 1"),
    ("123456789012345", "DDD"),
])
def test_telefone_que_nao_serve_e_recusado(cadastro, trecho):
    with pytest.raises(WM.TelefoneInvalido) as erro:
        WM.telefone_e164(cadastro)
    assert trecho in str(erro.value)


def test_o_aviso_de_andamento_grava_o_telefone_com_o_55():
    reg = {"telefone": "(99) 99999-0000"}
    assert AA.destino_do_canal(reg, AS.WHATSAPP) == "5599999990000"
    with pytest.raises(AA.AndamentoError, match="DDD"):
        AA.destino_do_canal({"telefone": "(09) 99999-0000"}, AS.WHATSAPP)


# ------------------------------------------------------------------ a janela de 24 h


def test_a_janela_conta_da_ultima_mensagem_do_cliente():
    msgs = [{"direcao": WA.DIR_IN, "criado_em": "2026-10-26T09:00:00"},
            {"direcao": WA.DIR_OUT, "criado_em": "2026-10-27T09:30:00"}]
    assert WM.fora_da_janela(msgs, "2026-10-27T08:59:00") is False
    assert WM.fora_da_janela(msgs, "2026-10-27T09:01:00") is True   # a saída não reabre
    assert WM.fora_da_janela([], "2026-10-27T09:01:00") is True      # o cliente nunca escreveu


# ------------------------------------------------------------------ a tela


def _entrar(cliente, login, nome, papel, db):
    db.create_user(login, nome, SENHA, papel)
    html = cliente.get("/login").get_data(as_text=True)
    csrf = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)
    cliente.post("/login", data={"username": login, "password": SENHA, "csrf_token": csrf},
                 follow_redirects=True)


def _csrf(cliente, caminho):
    html = cliente.get(caminho).get_data(as_text=True)
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1), html


def _form(csrf, **extra):
    dados = {"csrf_token": csrf, "phone_number_id": PHONE_ID}
    dados.update(extra)
    return dados


def test_a_tela_mostra_os_cinco_nomes_e_o_interruptor_desligado(cg_casa_logada):
    _, html = _csrf(cg_casa_logada["c"], "/whatsapp/config")
    assert "Modelos aprovados pela Meta" in html
    for spec in WM.MODELOS.values():
        assert spec["padrao"] in html
    caixa = re.search(r'<input[^>]*name="%s"[^>]*>' % SCH.CHAVE_MODELOS_APROVADOS, html)
    assert caixa and "checked" not in caixa.group(0)


def test_o_admin_liga_e_troca_um_nome(cg_casa_logada):
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    csrf, _ = _csrf(c, "/whatsapp/config")
    r = c.post("/whatsapp/config", data=_form(csrf, **{
        SCH.CHAVE_MODELOS_APROVADOS: "1", SCH.CHAVE_NOME_NO_MODELO: "de Exemplo",
        SCH.CHAVE_MODELO_PRONTO: "cartorio_pronto_v2",
        SCH.CHAVE_MODELO_EXIGENCIA: "cartorio_exigencia"}))
    assert r.status_code in (302, 303)
    with db.connect() as con:
        assert WM.ligado(con) is True
        assert WM.nome_no_modelo(con) == "de Exemplo"
        assert WM.nome_do_modelo(con, WM.PRONTO) == "cartorio_pronto_v2"
        # Gravar o próprio padrão é o mesmo que deixar vazio.
        assert WA.ler_config(con, SCH.CHAVE_MODELO_EXIGENCIA) == ""
        assert WM.nome_do_modelo(con, WM.EXIGENCIA) == "cartorio_exigencia"
    _, html = _csrf(c, "/whatsapp/config")
    caixa = re.search(r'<input[^>]*name="%s"[^>]*>' % SCH.CHAVE_MODELOS_APROVADOS, html)
    assert "checked" in caixa.group(0)


def test_nome_fora_da_regra_nao_grava_nada(cg_casa_logada):
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    csrf, _ = _csrf(c, "/whatsapp/config")
    c.post("/whatsapp/config", data=_form(csrf, **{
        SCH.CHAVE_MODELOS_APROVADOS: "1", SCH.CHAVE_MODELO_PRONTO: "Pronto Para Retirar"}))
    with db.connect() as con:
        assert WM.ligado(con) is False
        assert WA.ler_config(con, SCH.CHAVE_MODELO_PRONTO) == ""


def test_complemento_que_repete_cartorio_nao_grava(cg_casa_logada):
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    csrf, _ = _csrf(c, "/whatsapp/config")
    c.post("/whatsapp/config", data=_form(csrf, **{
        SCH.CHAVE_MODELOS_APROVADOS: "1", SCH.CHAVE_NOME_NO_MODELO: "Cartório de Exemplo"}))
    with db.connect() as con:
        assert WM.ligado(con) is False
        assert WA.ler_config(con, SCH.CHAVE_NOME_NO_MODELO) == ""


def test_so_o_admin_grava_os_modelos(cg_casa):
    c, db = cg_casa["c"], cg_casa["db"]
    _entrar(c, "beatriz", "BEATRIZ EXEMPLO", "USER", db)
    csrf, html = _csrf(c, "/whatsapp/config")
    assert "Modelos aprovados pela Meta" in html          # ver é de todos
    r = c.post("/whatsapp/config", data=_form(csrf, **{SCH.CHAVE_MODELOS_APROVADOS: "1"}))
    assert r.status_code == 403
    with db.connect() as con:
        assert WM.ligado(con) is False


def test_sem_csrf_a_tela_nao_grava(cg_casa_logada):
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    r = c.post("/whatsapp/config", data={SCH.CHAVE_MODELOS_APROVADOS: "1",
                                         "phone_number_id": PHONE_ID})
    assert r.status_code == 400
    with db.connect() as con:
        assert WM.ligado(con) is False


# ------------------------------------------------------------------ o balcão: reabrir


def _conversa(db, quando):
    with db.transaction() as con:
        r = WA.aplicar_entrada(con, {"messages": [{
            "from": WA_ID, "id": f"wamid.in-{quando}", "type": "text",
            "text": {"body": "bom dia, e a minha certidão?"}}]}, agora=quando)
    return r["conversa_ids"][0]


def _saidas(db, cid):
    with db.connect() as con:
        return banco(con).ler("SELECT * FROM wa_mensagem WHERE conversa_id=%s AND direcao=%s",
                              (cid, WA.DIR_OUT))


def test_fora_da_janela_o_balcao_reabre_com_o_modelo(cg_casa_logada, monkeypatch):
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    _ligar(db, monkeypatch)
    graph = Graph()
    monkeypatch.setattr(WA, "_http_post_json", graph)
    cid = _conversa(db, "2026-10-01T09:00:00")
    csrf, html = _csrf(c, f"/whatsapp/{cid}")
    assert "fora da janela de 24 h" in html and "Reabrir com o modelo" in html
    r = c.post(f"/whatsapp/{cid}/reabrir", data={"csrf_token": csrf})
    assert r.status_code in (302, 303)
    (pedido,) = graph.pedidos
    assert pedido["payload"]["to"] == WA_ID
    assert pedido["payload"]["type"] == "template"
    assert pedido["payload"]["template"]["name"] == "cartorio_retomar_atendimento"
    assert pedido["payload"]["template"]["language"] == {"code": "pt_BR"}
    assert pedido["payload"]["template"]["components"] == [
        {"type": "body", "parameters": [{"type": "text", "text": "de Exemplo"}]}]
    (saida,) = _saidas(db, cid)
    assert saida["tipo"] == "modelo" and saida["meta_id"].startswith("wamid.modelo-")
    assert saida["texto"].startswith("Cartório de Exemplo: temos uma resposta")


def test_dentro_da_janela_o_botao_nao_aparece(cg_casa_logada, monkeypatch):
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    _ligar(db, monkeypatch)
    cid = _conversa(db, db.now())
    _, html = _csrf(c, f"/whatsapp/{cid}")
    assert "Reabrir com o modelo" not in html


def test_desligado_o_balcao_continua_como_antes(cg_casa_logada, monkeypatch):
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    _token_falso(monkeypatch)
    _gravar(db, **{SCH.CHAVE_PHONE: PHONE_ID, SCH.CHAVE_NOME_NO_MODELO: "de Exemplo"})
    cid = _conversa(db, "2026-10-01T09:00:00")
    csrf, html = _csrf(c, f"/whatsapp/{cid}")
    assert "Reabrir com o modelo</button>" not in html
    # A rota recusa sem falar com a rede (o guarda estouraria).
    r = c.post(f"/whatsapp/{cid}/reabrir", data={"csrf_token": csrf})
    assert r.status_code == 400
    assert _saidas(db, cid) == []


def test_a_recusa_da_meta_por_janela_aponta_o_modelo(cg_casa_logada, monkeypatch):
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    _ligar(db, monkeypatch)
    erro = json.dumps({"error": {"message": "Re-engagement message", "code": 131047}})
    monkeypatch.setattr(WA, "_http_post_json", Graph(status=400, corpo=erro))
    cid = _conversa(db, "2026-10-01T09:00:00")
    with db.transaction() as con:
        WA.salvar_rascunho(con, cid, "Sua certidão está pronta.")
    csrf, _ = _csrf(c, f"/whatsapp/{cid}")
    r = c.post(f"/whatsapp/{cid}/enviar", data={"csrf_token": csrf})
    assert r.status_code == 400
    html = c.get(f"/whatsapp/{cid}").get_data(as_text=True)     # os avisos da tela
    assert "131047" in html and "Use «Reabrir com o modelo»" in html
    assert _saidas(db, cid) == []
