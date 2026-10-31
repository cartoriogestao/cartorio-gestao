"""O atendimento eletrônico do ONR, as cobranças e a consulta da CNIB por documento.

O QUE ELES DEFENDEM
    Pedido do oficial, 30/10/2026. Duas telas escrevem lá fora, em nome da serventia, e uma mexe com o
    dinheiro do cliente. Os riscos: valor errado no boleto, dois cliques virando duas cobranças,
    resposta que a tela não entendeu virando «não há nada», e o CPF de alguém no endereço da página.
    Nenhum teste fala com o ONR nem com a CNIB. A parte de baixo usa o sistema de pé, e roda na outra
    máquina.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import onr_saec as SAEC  # noqa: E402

TELAS = RAIZ / "templates"
CPF_FICTICIO = "00000000191"  # da lista de fictícios do portão anti-vazamento


def _campos(**trocas):
    campos = {
        "tipo_cobranca": "PIX", "vencimento": "2026-11-30", "pagador_nome": "Ana Exemplo",
        "pagador_documento": CPF_FICTICIO, "pagador_email": "ana@exemplo.invalid",
        "cep": "00000-000", "tipo_logradouro": "Rua", "logradouro": "das Flores", "bairro": "Centro",
        "cidade": "Cidade Exemplo", "estado": "ma", "servico_codigo_1": "12345", "servico_valor_1": "100,00",
    }
    campos.update(trocas)
    return campos


# ------------------------------------------------------------ o que o ONR responde


def test_a_lista_na_forma_do_contrato():
    r = SAEC.atendimentos_da_resposta({
        "totalRegistros": 3, "totalPaginas": 2, "paginaAtual": 1,
        "dados": [
            {"id": 1, "status": 1, "statusDescricao": "Em aberto", "tipoAtendimento": 90,
             "tipoAtendimentoDescricao": "Resposta de exigência", "dataAtualizacao": "2026-10-30 09:15:00"},
            {"id": 2, "status": 4, "tipoAtendimento": 6},
            {"id": 3, "status": 11, "tipoAtendimento": 1},
        ]})
    assert [x["id"] for x in r["esperam"]] == [1, 3]
    assert [x["id"] for x in r["outros"]] == [2]
    assert r["esperam"][0]["atualizado"] == "30/10/2026 09:15"
    assert r["outros"][0]["situacao"] == "Finalizado"
    assert r["outros"][0]["tipo"] == "WhatsApp"
    assert (r["total"], r["paginas"], r["pagina"], r["estranha"]) == (3, 2, 1, False)


@pytest.mark.parametrize("resposta", [{"data": []}, []])
def test_a_lista_vazia_nao_e_estranha(resposta):
    r = SAEC.atendimentos_da_resposta(resposta)
    assert r["estranha"] is False and r["esperam"] == [] and r["outros"] == []


@pytest.mark.parametrize("resposta", [None, "fora do ar", {"outra": 1}])
def test_resposta_que_nao_se_entende_nao_vira_lista_vazia(resposta):
    """A tela não pode dizer «nenhum» de uma resposta que ela não entendeu."""
    assert SAEC.atendimentos_da_resposta(resposta)["estranha"] is True
    assert SAEC.cobrancas_da_resposta(resposta)["estranha"] is True


def test_situacao_que_a_casa_nao_conhece_sai_como_veio():
    r = SAEC.atendimentos_da_resposta({"dados": [{"id": 9, "status": 77}]})
    assert r["outros"][0]["situacao"] == "código 77"
    assert r["esperam"] == []


def test_a_conversa_vem_da_mais_nova_e_link_perigoso_nao_passa():
    a = SAEC.atendimento_da_resposta({
        "id": 5, "status": 1, "usuarioCelular": "(99) 98888-7777",
        "interacoes": [
            {"data": "2026-10-01 08:00:00", "origemDescricao": "0 = Parte", "mensagem": "primeira"},
            {"data": "2026-10-02 08:00:00", "origemDescricao": "1 = Cartório", "mensagem": "segunda",
             "arquivos": [{"nome": "bom.pdf", "url": "https://exemplo.invalid/a.pdf"},
                          {"nome": "ruim", "url": "javascript:alert(1)"}]},
        ]})
    assert [m["mensagem"] for m in a["interacoes"]] == ["segunda", "primeira"]
    assert a["interacoes"][0]["origem"] == "Cartório"
    assert [x["nome"] for x in a["interacoes"][0]["arquivos"]] == ["bom.pdf"]


def test_so_passa_link_http_base64_e_hash():
    assert SAEC.url_segura("javascript:alert(1)") == ""
    assert SAEC.url_segura("https://exemplo.invalid/x") == "https://exemplo.invalid/x"
    assert SAEC.qrcode_seguro('x" onerror="alert(1)') == ""
    assert SAEC.qrcode_seguro("QUJD\nREVG==") == "QUJDREVG=="
    assert SAEC.hash_valido("123e4567-e89b-12d3-a456-426614174000")
    assert not SAEC.hash_valido("../../v1/auth")


def test_dois_campos_do_atendimento_abrem_a_cobranca_sem_endereco():
    campos = SAEC.campos_do_atendimento({
        "nome": "Ana Exemplo", "documento": "000.000.001-91", "email": "ana@exemplo.invalid",
        "celular": "(99) 98888-7777", "cidade": "Cidade Exemplo", "estado": "MA", "protocolo": "4321"})
    assert campos["pagador_documento"] == CPF_FICTICIO
    assert (campos["ddd"], campos["telefone"]) == ("99", "988887777")
    assert campos["servico_codigo_1"] == "4321"
    assert "cep" not in campos
    assert SAEC.campos_do_atendimento({"protocolo": "S-12"})["servico_codigo_1"] == ""


# ------------------------------------------------------------ a resposta


def test_a_acao_vai_como_numero_e_a_forma_e_opcional():
    assert SAEC.corpo_da_resposta("3", "Atendimento concluído aqui.") == {
        "acao": 3, "mensagem": "Atendimento concluído aqui."}
    assert SAEC.corpo_da_resposta("0", "Atendimento concluído aqui.", "2")["formaAtendimento"] == 2


@pytest.mark.parametrize("acao,mensagem,forma", [
    ("9", "Mensagem bem escrita.", ""), ("", "Mensagem bem escrita.", ""),
    ("0", "ok", ""), ("0", "Mensagem bem escrita.", "7"),
])
def test_resposta_ruim_recusa_antes_da_rede(acao, mensagem, forma):
    with pytest.raises(SAEC.SaecError):
        SAEC.corpo_da_resposta(acao, mensagem, forma)


# ------------------------------------------------------------ a cobrança


def test_o_corpo_segue_o_contrato():
    corpo = SAEC.corpo_da_cobranca(_campos(numero="10", ddd="99", telefone="988887777",
                                           observacao="Certidão"), hoje="2026-10-30")
    assert corpo["tipoCobranca"] == "PIX"
    assert corpo["dataVencimento"] == "2026-11-30"
    assert corpo["observacao"] == "Certidão"
    pagador = corpo["dadosPagador"]
    assert pagador["documento"] == CPF_FICTICIO
    assert pagador["telefone"] == {"ddd": 99, "numero": 988887777}
    assert pagador["endereco"]["cep"] == "00000000"
    assert pagador["endereco"]["estado"] == "MA"
    assert corpo["servicos"] == [{"codigo": 12345, "valor": 10000}]
    assert SAEC.total_em_centavos(corpo) == 10000


def test_campo_opcional_vazio_nao_vai():
    corpo = SAEC.corpo_da_cobranca(_campos(), hoje="2026-10-30")
    assert "observacao" not in corpo and "tipoPagamento" not in corpo
    assert "telefone" not in corpo["dadosPagador"]
    assert "numero" not in corpo["dadosPagador"]["endereco"]


@pytest.mark.parametrize("digitado,centavos", [
    ("100", 10000), ("100,00", 10000), ("1.000", 100000), ("1.234,56", 123456), ("0,5", 50),
    ("12.345.678,90", 1234567890),
])
def test_o_valor_digitado(digitado, centavos):
    assert SAEC.centavos_digitados(digitado) == centavos


@pytest.mark.parametrize("digitado", ["", "abc", "1,234.56", "10,123", "1.00", "-5"])
def test_o_que_nao_e_valor_recusa(digitado):
    """«1.00» recusa de propósito: nesta casa o ponto é milhar, e o erro seria de cem vezes."""
    with pytest.raises(SAEC.SaecError):
        SAEC.centavos_digitados(digitado)


@pytest.mark.parametrize("trocas,trecho", [
    ({"tipo_cobranca": "CHEQUE"}, "PIX ou boleto"),
    ({"vencimento": "2026-10-29"}, "já passou"),
    ({"vencimento": ""}, "vencimento"),
    ({"pagador_documento": "11111111111"}, "não fecha"),
    ({"pagador_email": "sem-arroba"}, "@"),
    ({"cep": "123"}, "CEP"),
    ({"estado": "Maranhão"}, "sigla"),
    ({"observacao": "x" * 31}, "observação"),
    ({"ddd": "99"}, "telefone"),
    ({"servico_codigo_1": "S-12"}, "número do protocolo"),
    ({"servico_valor_1": "0,00"}, "sem valor"),
    ({"servico_codigo_1": "", "servico_valor_1": ""}, "pelo menos um serviço"),
    ({"tipo_logradouro": ""}, "tipo do logradouro"),
])
def test_cobranca_ruim_recusa_antes_da_rede(trocas, trecho):
    with pytest.raises(SAEC.SaecError) as erro:
        SAEC.corpo_da_cobranca(_campos(**trocas), hoje="2026-10-30")
    assert trecho in str(erro.value)


def test_a_recusa_diz_todos_os_problemas_de_uma_vez():
    with pytest.raises(SAEC.SaecError) as erro:
        SAEC.corpo_da_cobranca({"tipo_cobranca": "PIX"}, hoje="2026-10-30")
    assert all(p in str(erro.value) for p in ("vencimento", "nome do pagador", "CEP", "serviço"))


def test_o_valor_devolvido_se_le_na_mesma_conta():
    assert SAEC.reais_do_onr(10000) == "100,00"
    assert SAEC.reais_do_onr(None) == ""
    c = SAEC.cobranca_da_resposta({"hash": "h1", "valorTotal": 10000, "url": "javascript:x",
                                   "servicos": [{"codigo": 7, "valor": 2500}]})
    assert (c["valor"], c["valor_bruto"], c["url"]) == ("100,00", "10000", "")
    assert c["servicos"] == [{"codigo": "7", "valor": "25,00"}]


def test_so_os_tipos_de_pagamento_ativos():
    assert SAEC.tipos_de_pagamento_da_resposta({"dados": [
        {"id": 1, "descricao": "Certidão", "status": 1}, {"id": 2, "descricao": "Velho", "status": 0},
    ]}) == [{"id": 1, "descricao": "Certidão"}]


# ------------------------------------------------------------ as regras, lidas do código


def _rotas(arquivo: str) -> dict:
    """Os decoradores de cada rota de um módulo, como texto."""
    arvore = ast.parse((RAIZ / arquivo).read_text(encoding="utf-8"))
    saida = {}
    for no in ast.walk(arvore):
        if isinstance(no, ast.FunctionDef) and any("route" in ast.unparse(d) for d in no.decorator_list):
            saida[no.name] = (" ".join(ast.unparse(d) for d in no.decorator_list), ast.unparse(no))
    return saida


def test_o_que_escreve_la_fora_e_so_do_admin():
    rotas = _rotas("onr_saec_web.py")
    assert set(n for n, (d, _) in rotas.items() if "POST" in d) == {"onr_saec_responder", "onr_cobranca_gerar"}
    for nome in ("onr_saec_responder", "onr_cobranca_gerar", "onr_cobranca_nova"):
        assert "roles_required(*QUEM_ESCREVE)" in rotas[nome][0], nome
    import onr_saec_web as WEB
    assert WEB.QUEM_ESCREVE == ("ADMIN",)


def test_nenhuma_chamada_a_rede_dentro_de_transacao():
    """A rede dentro de `db.transaction()` trava o balcão inteiro enquanto o ONR não responde."""
    arvore = ast.parse((RAIZ / "onr_saec_web.py").read_text(encoding="utf-8"))
    for no in ast.walk(arvore):
        if isinstance(no, ast.With) and "transaction" in ast.unparse(no.items[0]):
            assert "API." not in "".join(ast.unparse(x) for x in no.body)


def test_a_chave_entra_antes_da_rede():
    for nome, chamada in (("onr_saec_responder", "API.interagir_no_atendimento"),
                          ("onr_cobranca_gerar", "API.gerar_cobranca")):
        corpo = _rotas("onr_saec_web.py")[nome][1]
        assert corpo.index("SAEC.reservar") < corpo.index(chamada), nome


def test_a_chave_e_unica_no_banco():
    assert re.search(r"chave TEXT NOT NULL UNIQUE", SAEC.SCHEMA)


def test_as_duas_telas_que_escrevem_mandam_token_e_chave():
    for tela in ("onr_saec_ficha.html", "onr_cobranca_nova.html"):
        texto = (TELAS / tela).read_text(encoding="utf-8")
        assert 'name="csrf_token"' in texto and 'name="chave"' in texto, tela
        assert "confirm(" in texto, tela


def test_a_lista_diz_onde_esta_o_pedido_de_certidao():
    texto = (TELAS / "onr_saec.html").read_text(encoding="utf-8")
    assert "Pedido de certidão não chega por aqui" in texto
    assert "url_for('onr_certidoes')" in texto


def test_o_documento_da_consulta_nao_vai_no_endereco():
    texto = (TELAS / "cnib_consulta.html").read_text(encoding="utf-8")
    assert '<form method="post"' in texto
    assert "request.args" not in _rotas("cnib_web.py")["cnib_consulta"][1]


def test_a_consulta_so_diz_que_nao_ha_quando_a_central_disse():
    texto = (TELAS / "cnib_consulta.html").read_text(encoding="utf-8")
    assert texto.index("not r.respondeu") < texto.index("A Central não aponta indisponibilidade")
    assert "Isso não quer dizer que não há ordem" in texto


# ------------------------------------------------------------- com o sistema de pé


def _token(html: str) -> str:
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


def _entrar(app, usuario: str, papel: str):
    d = app.extensions["db"]
    try:
        d.create_user(usuario, "Operador Exemplo", "Senha#12345", papel)
    except Exception:                                              # noqa: BLE001
        pass
    c = app.test_client()
    c.post("/login", data={"username": usuario, "password": "Senha#12345",
                           "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return c


@pytest.fixture
def onr(monkeypatch):
    """O ONR de mentira. `chamadas` guarda o que foi mandado."""
    import onr_api as API
    chamadas = []

    def falso(qual, **kw):
        chamadas.append((qual, kw))
        if qual == "atendimentos":
            return {"status": 200, "texto": "", "json": {"totalRegistros": 1, "totalPaginas": 1, "paginaAtual": 1, "dados": [
                {"id": 77, "status": 1, "tipoAtendimento": 90, "usuarioNome": "Ana Exemplo"}]}}
        if qual == "atendimento":
            return {"status": 200, "texto": "", "json": {
                "id": 77, "status": 1, "tipoAtendimento": 90, "usuarioNome": "Ana Exemplo",
                "usuarioCpf": CPF_FICTICIO, "usuarioEmail": "ana@exemplo.invalid", "interacoes": []}}
        if qual == "atendimento_interagir":
            return {"status": 201, "texto": "", "json": {}}
        if qual == "cobranca_gerar":
            return {"status": 201, "texto": "", "json": {
                "hash": "123e4567-e89b-12d3-a456-426614174000", "status": 1, "valorTotal": 10000,
                "url": "https://exemplo.invalid/c", "qrcode": "QUJD"}}
        if qual == "cobranca":
            return {"status": 200, "texto": "", "json": {"hash": kw.get("hash"), "status": 1, "valorTotal": 10000,
                                                          "url": "https://exemplo.invalid/c"}}
        if qual == "cobrancas":
            return {"status": 200, "texto": "", "json": {"cobrancas": []}}
        if qual == "cobranca_tipos_de_pagamento":
            return {"status": 200, "texto": "", "json": {"dados": []}}
        raise AssertionError(qual)

    monkeypatch.setattr(API, "_bater", falso)
    monkeypatch.setattr(API, "tem_credencial", lambda *a, **k: True)
    return chamadas


def test_o_balcao_le_e_nao_escreve(cg_app, onr):
    c = _entrar(cg_app, "saec_balcao", "USER")
    pagina = c.get("/ri/onr/atendimentos").get_data(as_text=True)
    assert "Esperando a serventia" in pagina and "Ana Exemplo" in pagina
    ficha = c.get("/ri/onr/atendimentos/77").get_data(as_text=True)
    assert "Ana Exemplo" in ficha and "Enviar ao ONR" not in ficha
    assert c.post("/ri/onr/atendimentos/77/responder", data={
        "acao": "0", "mensagem": "Mensagem bem escrita.", "chave": "k1",
        "csrf_token": _token(pagina)}).status_code == 403
    assert not [q for q, _ in onr if q == "atendimento_interagir"]
    assert c.get("/ri/onr/cobrancas").status_code == 403


def test_dois_cliques_na_resposta_valem_um_envio(cg_app, onr):
    c = _entrar(cg_app, "saec_admin1", "ADMIN")
    ficha = c.get("/ri/onr/atendimentos/77").get_data(as_text=True)
    dados = {"acao": "3", "mensagem": "Resolvido por aqui, obrigado.", "csrf_token": _token(ficha),
             "chave": re.search(r'name="chave" value="([^"]+)"', ficha).group(1)}
    assert c.post("/ri/onr/atendimentos/77/responder", data=dados).status_code == 302
    assert c.post("/ri/onr/atendimentos/77/responder", data=dados).status_code == 302
    enviados = [k for q, k in onr if q == "atendimento_interagir"]
    assert len(enviados) == 1 and enviados[0]["corpo"]["acao"] == 3


def test_dois_cliques_na_cobranca_valem_uma_cobranca(cg_app, onr):
    c = _entrar(cg_app, "saec_admin2", "ADMIN")
    tela = c.get("/ri/onr/cobrancas/nova?atendimento=77").get_data(as_text=True)
    assert 'value="Ana Exemplo"' in tela
    dados = {**_campos(vencimento="2099-12-31"), "atendimento_id": "77", "csrf_token": _token(tela),
             "chave": re.search(r'name="chave" value="([^"]+)"', tela).group(1)}
    primeira = c.post("/ri/onr/cobrancas/gerar", data=dados)
    assert primeira.status_code == 302 and "/ri/onr/cobrancas/123e4567" in primeira.headers["Location"]
    assert c.post("/ri/onr/cobrancas/gerar", data=dados).status_code == 302
    enviadas = [k for q, k in onr if q == "cobranca_gerar"]
    assert len(enviadas) == 1 and enviadas[0]["corpo"]["servicos"][0]["valor"] == 10000
    ficha = c.get(primeira.headers["Location"]).get_data(as_text=True)
    assert "confira o valor" in ficha and "data:image/png;base64,QUJD" in ficha


def test_recusa_do_onr_mantem_o_que_foi_digitado(cg_app, onr, monkeypatch):
    import onr_api as API

    def recusa(*a, **k):
        raise API.OnrRecusou("O ONR recusou os dados: exemplo.")

    monkeypatch.setattr(API, "interagir_no_atendimento", recusa)
    c = _entrar(cg_app, "saec_admin3", "ADMIN")
    ficha = c.get("/ri/onr/atendimentos/77").get_data(as_text=True)
    volta = c.post("/ri/onr/atendimentos/77/responder", data={
        "acao": "0", "mensagem": "Texto que não pode sumir.", "csrf_token": _token(ficha),
        "chave": re.search(r'name="chave" value="([^"]+)"', ficha).group(1)}).get_data(as_text=True)
    assert "O ONR recusou os dados" in volta and "Texto que não pode sumir." in volta


def test_rede_que_cai_na_cobranca_pede_para_conferir(cg_app, onr, monkeypatch):
    import onr_api as API

    def cai(*a, **k):
        raise API.OnrError("Não consegui falar com o ONR.")

    monkeypatch.setattr(API, "gerar_cobranca", cai)
    c = _entrar(cg_app, "saec_admin4", "ADMIN")
    tela = c.get("/ri/onr/cobrancas/nova").get_data(as_text=True)
    volta = c.post("/ri/onr/cobrancas/gerar", data={
        **_campos(vencimento="2099-12-31"), "csrf_token": _token(tela),
        "chave": re.search(r'name="chave" value="([^"]+)"', tela).group(1)}, follow_redirects=True).get_data(as_text=True)
    assert "confira antes de repetir" in volta and "sem resposta" in volta


def test_consulta_da_cnib_diz_cada_resposta(cg_app, monkeypatch):
    import cnib_api as API
    import cnib_atualizador as ATZ
    monkeypatch.setattr(ATZ, "esta_pronto", lambda con: {"pronto": True, "falta": []})
    monkeypatch.setattr(ATZ, "cpf_de_quem_consulta", lambda con: CPF_FICTICIO)
    c = _entrar(cg_app, "cnib_balcao", "USER")
    tela = c.get("/registro-imoveis/cnib/consulta").get_data(as_text=True)
    token = _token(tela)

    def pede(resposta):
        monkeypatch.setattr(API, "consultar_por_documento", lambda *a, **k: resposta)
        return c.post("/registro-imoveis/cnib/consulta", data={
            "documento": CPF_FICTICIO, "csrf_token": token}).get_data(as_text=True)

    base = {"documento": "000.000.001-91", "nome": "ANA EXEMPLO", "quantas": 0, "protocolos": [], "forma": "documento"}
    assert "A Central não aponta indisponibilidade" in pede({**base, "respondeu": True, "indisponivel": False})
    tem = pede({**base, "respondeu": True, "indisponivel": True, "quantas": 2, "protocolos": ["P-1", "P-2"]})
    assert "Há ordem de indisponibilidade" in tem and "P-2" in tem
    assert "forma que este sistema não conhece" in pede({**base, "respondeu": False, "indisponivel": False})
