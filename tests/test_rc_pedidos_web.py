"""AS TELAS DA CENTRAL DE CERTIDOES — a fila, a ficha e a certidao eletronica.

O QUE ESTES TESTES GUARDAM, e cada um custou uma decisao:

      - **sem token, a tela DIZ onde pegar** e nao oferece botao de subir — e
        diz que o token e o MESMO do e-Proclamas, porque um cadastro serve as
        duas APIs do ON-RCPN;
      - **P13 e EOB nao viram certidao**: a tela avisa que ali se LAVRA, e a
        rota recusa cumpri-los pelo caminho da certidao;
      - **o pedido que nao casou com assento nenhum diz por que**, e oferece
        amarrar a mao — casar por livro/folha abriria a ficha de outra pessoa;
      - **responder nao e do balcao**;
      - as rotas **falam com a Central FORA da transacao**;
      - e **a recusa da Central vira aviso na tela**, e nao HTTP 500.

NENHUM DESTES TESTES FALA COM A CENTRAL. O transporte e trocado por um de
mentira; o que se prova e a TELA — e a tela e o que faltou seis vezes neste
projeto.
"""
from __future__ import annotations

import glob
import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import onrcpn_certidao_api as API
import rc_assento as RC
import rc_pedidos as PED
import rc_pedidos_schema as ESQ

SENHA = "Senha#12345"
AGORA = "2026-09-03T10:00:00"
CNS = "000000"
MATRICULA = "00000001552026100001001000012345"
SV = {"ri_cns": CNS, "ri_cidade": "Cidade Exemplo", "ri_uf": "MA",
      "escrevente": "JEAN", "funcao": "Escrevente"}

PESSOAS = [
    {"papel": "REGISTRADO", "nome": "FULANO DE TAL", "sexo": "M",
     "naturalidade_cidade": "Cidade Exemplo", "naturalidade_uf": "MA"},
    {"papel": "MAE", "nome": "MARIA DE TAL"},
    {"papel": "PAI", "nome": "JOSE DE TAL"},
    {"papel": "DECLARANTE", "nome": "JOSE DE TAL"},
]


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    return achado.group(1) if achado else ""


def _sessao(cg_casa, papel: str = "ADMIN"):
    app = cg_casa['app']
    banco = cg_casa['banco']
    dados = cg_casa['dados']
    bd = cg_casa['db']
    bd.create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS", SENHA, papel)
    bd.set_settings({"serventia_cns": CNS, "ri_uf": "MA"})
    c = app.test_client()
    c.post("/login",
           data={"username": "tabeliao", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {"app": app, "c": c, "banco": banco, "db": bd}


@pytest.fixture()
def s(cg_casa):
    return _sessao(cg_casa)


@pytest.fixture()
def com_token(monkeypatch):
    """O sistema acha que o token existe, sem gravar segredo nenhum."""
    monkeypatch.setattr(API, "tem_credencial", lambda **k: True)


@pytest.fixture()
def sem_token(monkeypatch):
    """O espelho de `com_token`: **sem** token, e declarado.

    **O LADO «SEM» NÃO ESTAVA DECLARADO, E ELE HERDAVA DO DISCO** — medido em
    18/09/2026. Verde enquanto `onrcpn.cred` não existia; vermelho no dia em
    que o oficial informasse o token do IdRC, sem uma linha de código mudar.
    """
    monkeypatch.setattr(API, "tem_credencial", lambda **k: False)


def _con(s) -> sqlite3.Connection:
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    return con


def _assento(s) -> int:
    con = _con(s)
    feito = RC.lavrar_assento(
        con, especie="NASCIMENTO", nome="FULANO DE TAL", sv=SV, agora=AGORA,
        data_extenso="tres de setembro de dois mil e vinte e seis",
        data_fato="2020-01-15", usuario="JEAN", pessoas=PESSOAS,
        termo_dados={"local_fato_nome": "Hospital Municipal"})
    con.execute("UPDATE rc_assentos SET matricula=? WHERE id=?",
                (MATRICULA, feito["assento_id"]))
    con.commit()
    con.close()
    return feito["assento_id"]


def _pedido(s, *, modulo="CRC", assento_id=None, matricula=MATRICULA,
            situacao=ESQ.PENDENTE) -> int:
    linha = {"pedido_certidao_id": 11111111, "numero_cnj_solicitante": "000000",
             "numero_cnj_recebedor": CNS, "nome_requerente": "ENZO FERREIRA",
             "documento_requerente": "33521478", "data_pedido": "30/12/2024",
             "tipo_registro": "N", "nome_registrado": "FULANO DE TAL",
             "data_ato_fato": "15/01/2020", "data_registro": "16/01/2020",
             "num_livro": "00061", "num_folha": "051",
             "num_registro": "0001111", "matricula": matricula,
             "obs_pedido": "", "deposito_previo": "43,76"}
    con = _con(s)
    cur = con.execute(
        """INSERT INTO rc_pedidos(modulo, ambiente, numero_pedido,
               letra_registro, especie, assento_id, casamento_motivo, teor,
               resumo, deposito_previo, deposito_previo_valor, baixado_em,
               situacao)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (modulo, PED.ambiente(), "11111111", "N", "nascimento", assento_id,
         "Achado pela matricula." if assento_id else
         "O pedido nao trouxe matricula.",
         json.dumps(linha), "FULANO DE TAL · nascimento", "43,76", 43.76,
         AGORA, situacao))
    con.commit()
    ident = int(cur.lastrowid)
    con.close()
    return ident


def _eletronica(s, pedido_id, assento_id, *, certidao_id="abc-123",
                situacao=ESQ.CRIADA) -> int:
    con = _con(s)
    cur = con.execute(
        """INSERT INTO rc_certidoes_eletronicas(assento_id, pedido_id,
               ambiente, tipo_registro, modalidade, certidao_id,
               corpo_enviado, corpo_hash, situacao, criada_em)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (assento_id, pedido_id, PED.ambiente(), "nascimento", "eletronica",
         certidao_id, "{}", "x" * 64, situacao, AGORA))
    con.commit()
    ident = int(cur.lastrowid)
    con.close()
    return ident


def _post(s, caminho, dados, *, de=None):
    html = s["c"].get(de or "/rcpn/pedidos").get_data(as_text=True)
    dados = dict(dados)
    dados["csrf_token"] = _token(html)
    return s["c"].post(caminho, data=dados, follow_redirects=True)


# ------------------------------------------------------- sem credencial


def test_sem_token_a_tela_diz_onde_pegar_e_que_ele_serve_as_duas(s, sem_token):
    """Quem nao souber que o token e o mesmo pede duas credenciais."""
    html = s["c"].get("/rcpn/pedidos").get_data(as_text=True)
    assert "token do IdRC ainda não foi informado" in html
    assert "Configurações" in html
    assert "e-Proclamas" in html


def test_a_tela_diz_que_o_ambiente_e_o_de_homologacao_e_por_que(s):
    """O contrato **nao declara `servers`** — o endereco sai da pagina de
    documentacao, e ela tem o «h».

    **E a razao mudou em 18/09/2026**: o endereco de producao foi medido, existe
    e responde, com o mesmo contrato. O que segura a casa em homologacao e a
    ordem do cadastro — e a tela passou a dizer isso em vez de dizer que o outro
    nao existe."""
    html = s["c"].get("/rcpn/pedidos").get_data(as_text=True)
    assert "certidaoh" in html
    assert "homologa" in html.lower()
    assert "existe e responde" in html
    assert "Só há ambiente de homologação publicado" not in html


def test_a_fila_vazia_nao_finge_que_nao_ha_trabalho(s):
    html = s["c"].get("/rcpn/pedidos").get_data(as_text=True)
    assert "Baixar" in html
    assert "A Central" in html


# ------------------------------------------------------------- a fila


def test_os_sete_modulos_aparecem_com_o_que_cada_um_e(s):
    html = s["c"].get("/rcpn/pedidos").get_data(as_text=True)
    for modulo in API.MODULOS:
        assert modulo in html
    assert "Unidades Interligadas" in html
    assert "e-Óbito" in html or "e-&#211;bito" in html


def test_a_tela_avisa_que_P13_e_EOB_pedem_REGISTRO(s):
    """A diferenca que muda o ato: um se emite, o outro se LAVRA."""
    html = s["c"].get("/rcpn/pedidos").get_data(as_text=True)
    assert "pede registro" in html
    assert "corrente de hash" in html


def test_o_pedido_sem_assento_diz_que_nao_casou(s):
    _pedido(s)
    html = s["c"].get("/rcpn/pedidos").get_data(as_text=True)
    assert "não casou" in html


def test_baixar_com_a_central_fora_do_ar_vira_aviso_e_nao_500(s, monkeypatch,
                                                              com_token):
    def cai(*a, **k):
        raise API.CertidaoError("Nao consegui falar com a Central.")
    monkeypatch.setattr(API, "obter_pedidos", cai)
    r = _post(s, "/rcpn/pedidos/baixar", {"modulo": "CRC"})
    assert r.status_code == 200
    assert "Nao consegui falar com a Central." in r.get_data(as_text=True)


def test_baixar_um_modulo_que_nao_existe_vira_aviso(s):
    r = _post(s, "/rcpn/pedidos/baixar", {"modulo": "XPTO"})
    assert r.status_code == 200
    assert "não é um dos módulos" in r.get_data(as_text=True)


def test_baixar_grava_o_que_a_central_mandou_e_conta(s, monkeypatch, com_token):
    """**A rede acontece FORA da transacao** — o dominio recebe `db`."""
    linha = {"pedido_certidao_id": 999, "tipo_registro": "N",
             "nome_registrado": "FULANO DE TAL", "matricula": MATRICULA,
             "deposito_previo": "43,76", "nome_requerente": "ENZO"}
    monkeypatch.setattr(API, "obter_pedidos", lambda m, c, **k: {
        "modulo": m, "quantos": 1, "quantos_a_central_disse": 1,
        "contagem_bate": True, "pedidos": [API._pedido(linha)]})
    _assento(s)
    r = _post(s, "/rcpn/pedidos/baixar", {"modulo": "CRC"})
    html = r.get_data(as_text=True)
    assert "entraram 1" in html
    con = _con(s)
    guardado = con.execute("SELECT * FROM rc_pedidos").fetchone()
    con.close()
    assert guardado["numero_pedido"] == "999"
    # **CASOU PELA MATRICULA**, e o motivo fica escrito para o balcao ler.
    assert guardado["assento_id"] is not None
    assert MATRICULA in guardado["casamento_motivo"]


def test_a_divergencia_de_contagem_NAO_passa_calada(s, monkeypatch, com_token):
    monkeypatch.setattr(API, "obter_pedidos", lambda m, c, **k: {
        "modulo": m, "quantos": 0, "quantos_a_central_disse": 5,
        "contagem_bate": False, "pedidos": []})
    r = _post(s, "/rcpn/pedidos/baixar", {"modulo": "CRC"})
    assert "disse que havia" in r.get_data(as_text=True)


# ------------------------------------------------------------ a ficha


def test_a_ficha_mostra_o_que_a_central_mandou(s):
    ident = _assento(s)
    p = _pedido(s, assento_id=ident)
    html = s["c"].get(f"/rcpn/pedidos/{p}").get_data(as_text=True)
    assert "ENZO FERREIRA" in html
    assert "43,76" in html
    assert "congelado" in html


def test_a_ficha_do_pedido_sem_assento_oferece_amarrar_a_mao(s):
    p = _pedido(s)
    html = s["c"].get(f"/rcpn/pedidos/{p}").get_data(as_text=True)
    assert f"/rcpn/pedidos/{p}/amarrar" in html
    assert "abriria a ficha de outra pessoa" in html


def test_amarrar_o_assento_a_mao_grava_e_diz_como_se_achou(s):
    ident = _assento(s)
    p = _pedido(s)
    _post(s, f"/rcpn/pedidos/{p}/amarrar",
          {"assento_id": ident, "motivo": "conferido no livro A-12"},
          de=f"/rcpn/pedidos/{p}")
    con = _con(s)
    linha = con.execute("SELECT * FROM rc_pedidos WHERE id=?", (p,)).fetchone()
    con.close()
    assert linha["assento_id"] == ident
    assert "livro A-12" in linha["casamento_motivo"]


def test_a_ficha_do_P13_avisa_que_ali_se_LAVRA(s):
    p = _pedido(s, modulo="P13")
    html = s["c"].get(f"/rcpn/pedidos/{p}").get_data(as_text=True)
    assert "não pede certidão" in html
    assert f"/rcpn/pedidos/{p}/registrado" in html


def test_a_letra_desconhecida_aparece_crua_e_diz_que_so_o_N_esta_medido(s):
    p = _pedido(s)
    con = _con(s)
    con.execute("UPDATE rc_pedidos SET especie=NULL, letra_registro='Z' "
                "WHERE id=?", (p,))
    con.commit()
    con.close()
    html = s["c"].get(f"/rcpn/pedidos/{p}").get_data(as_text=True)
    assert "só o «N» está medido" in html


# ------------------------------------------------- registro nao e certidao


def test_atender_um_P13_e_recusado_com_a_frase_certa(s, monkeypatch, com_token):
    ident = _assento(s)
    p = _pedido(s, modulo="P13", assento_id=ident)
    e = _eletronica(s, p, ident)
    r = _post(s, f"/rcpn/pedidos/{p}/atender",
              {"eletronica_id": e, "valor_emolumentos": "43,76"},
              de=f"/rcpn/pedidos/{p}")
    html = r.get_data(as_text=True)
    assert "pede **registro**" in html or "pede" in html
    assert "Lavre o assento" in html


def test_marcar_registrado_num_modulo_de_certidao_e_recusado(s):
    ident = _assento(s)
    p = _pedido(s, modulo="CRC", assento_id=ident)
    r = _post(s, f"/rcpn/pedidos/{p}/registrado", {"assento_id": ident},
              de=f"/rcpn/pedidos/{p}")
    assert "pede certidão" in r.get_data(as_text=True)


def test_marcar_registrado_num_P13_fecha_o_pedido_sem_lavrar(s):
    ident = _assento(s)
    p = _pedido(s, modulo="P13")
    con = _con(s)
    antes = con.execute("SELECT COUNT(*) FROM rc_assentos").fetchone()[0]
    con.close()
    _post(s, f"/rcpn/pedidos/{p}/registrado", {"assento_id": ident},
          de=f"/rcpn/pedidos/{p}")
    con = _con(s)
    depois = con.execute("SELECT COUNT(*) FROM rc_assentos").fetchone()[0]
    linha = con.execute("SELECT * FROM rc_pedidos WHERE id=?", (p,)).fetchone()
    con.close()
    assert antes == depois, "a tela LAVROU um assento"
    assert linha["situacao"] == ESQ.REGISTRADO


# ----------------------------------------------------- a certidao eletronica


def test_sem_token_a_ficha_nao_oferece_criar(s, sem_token):
    ident = _assento(s)
    p = _pedido(s, assento_id=ident)
    html = s["c"].get(f"/rcpn/pedidos/{p}").get_data(as_text=True)
    # **O ENDERECO DO BOTAO, E NAO A PALAVRA** — «criar» solto bateria no texto.
    assert f"/rcpn/pedidos/{p}/emitir" not in html
    assert "token do IdRC" in html


def test_com_token_a_ficha_oferece_criar_e_avisa_que_201_nao_basta(s, com_token):
    ident = _assento(s)
    p = _pedido(s, assento_id=ident)
    html = s["c"].get(f"/rcpn/pedidos/{p}").get_data(as_text=True)
    assert f"/rcpn/pedidos/{p}/emitir" in html
    assert "success" in html


def test_criar_com_recusa_da_central_vira_aviso_e_nao_500(s, monkeypatch,
                                                          com_token):
    ident = _assento(s)
    p = _pedido(s, assento_id=ident)

    def recusa(*a, **k):
        raise API.CertidaoRecusou(
            "A Central recusou os dados: registro.matricula: obrigatorio")
    monkeypatch.setattr(API, "criar", recusa)
    r = _post(s, f"/rcpn/pedidos/{p}/emitir", {}, de=f"/rcpn/pedidos/{p}")
    assert r.status_code == 200
    assert "registro.matricula" in r.get_data(as_text=True)


def test_criar_grava_o_corpo_congelado_com_hash(s, monkeypatch, com_token):
    ident = _assento(s)
    p = _pedido(s, assento_id=ident)
    monkeypatch.setattr(API, "criar", lambda c, r, **k: {
        "id": "abc-123", "arquivo": None, "mensagem": "ok",
        "corpo": {"certidao": c, "registro": r}, "bruto": {"success": True}})
    _post(s, f"/rcpn/pedidos/{p}/emitir", {"cota_emolumentos": "43,76"},
          de=f"/rcpn/pedidos/{p}")
    con = _con(s)
    linha = con.execute(
        "SELECT * FROM rc_certidoes_eletronicas").fetchone()
    con.close()
    assert linha["certidao_id"] == "abc-123"
    assert len(linha["corpo_hash"]) == 64
    corpo = json.loads(linha["corpo_enviado"])
    assert corpo["registro"]["matricula"] == MATRICULA
    assert corpo["certidao"]["cota_emolumentos"] == "R$ 43,76"


def test_assinar_guarda_o_link_que_a_central_devolveu(s, monkeypatch, com_token):
    ident = _assento(s)
    p = _pedido(s, assento_id=ident)
    e = _eletronica(s, p, ident)
    monkeypatch.setattr(API, "assinar", lambda i, **k: {
        "id": i, "link": "https://exemplo/assina/1", "id_assinatura": "as-1",
        "arquivo": None, "pdf": b"", "bruto": {"success": True}})
    _post(s, f"/rcpn/certidao-eletronica/{e}/assinar", {"volta_para": p},
          de=f"/rcpn/pedidos/{p}")
    con = _con(s)
    linha = con.execute(
        "SELECT * FROM rc_certidoes_eletronicas WHERE id=?", (e,)).fetchone()
    con.close()
    assert linha["situacao"] == ESQ.ASSINADA
    assert linha["assinatura_link"] == "https://exemplo/assina/1"


def test_assinar_certidao_cancelada_vira_aviso(s, com_token):
    ident = _assento(s)
    p = _pedido(s, assento_id=ident)
    e = _eletronica(s, p, ident, situacao=ESQ.CANCELADA)
    r = _post(s, f"/rcpn/certidao-eletronica/{e}/assinar", {"volta_para": p},
              de=f"/rcpn/pedidos/{p}")
    assert "cancelada" in r.get_data(as_text=True)


def test_a_ficha_diz_que_a_assinatura_acontece_na_central(s, com_token):
    """O A3 nao pode ser carregado dentro do servidor — esta medido."""
    ident = _assento(s)
    p = _pedido(s, assento_id=ident)
    _eletronica(s, p, ident)
    html = s["c"].get(f"/rcpn/pedidos/{p}").get_data(as_text=True)
    assert "na Central" in html
    assert "assinatura_digital" in html


def test_o_pdf_vem_da_central_e_nao_do_banco(s, monkeypatch, com_token):
    ident = _assento(s)
    p = _pedido(s, assento_id=ident)
    e = _eletronica(s, p, ident)
    monkeypatch.setattr(API, "buscar", lambda i, **k: {
        "id": i, "situacao": "assinada",
        "arquivo": {"type": "Buffer", "data": [37, 80, 68, 70]},
        "pdf": b"%PDF", "bruto": {"success": True}})
    r = s["c"].get(f"/rcpn/certidao-eletronica/{e}/pdf")
    assert r.status_code == 200
    assert r.mimetype == "application/pdf"
    assert r.get_data() == b"%PDF"
    # **OS CABECALHOS DE SEGURANCA DA CASA VAO JUNTO.**
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    # E nada do arquivo ficou no banco:
    con = _con(s)
    colunas = {linha[1] for linha in con.execute(
        "PRAGMA table_info(rc_certidoes_eletronicas)")}
    con.close()
    assert "arquivo" not in colunas and "pdf" not in colunas


# ------------------------------------------------------------ responder


def test_rejeitar_sem_motivo_e_recusado(s, com_token):
    ident = _assento(s)
    p = _pedido(s, assento_id=ident)
    r = _post(s, f"/rcpn/pedidos/{p}/rejeitar", {"motivo": ""},
              de=f"/rcpn/pedidos/{p}")
    assert "motivo" in r.get_data(as_text=True).lower()


def test_rejeitar_sobe_o_motivo_e_fecha_o_pedido(s, monkeypatch, com_token):
    ident = _assento(s)
    p = _pedido(s, assento_id=ident)
    mandado = {}

    def rejeita(**k):
        mandado.update(k)
        return {"corpo": {"numero_pedido": 11111111, "modulo": "CRC",
                          "descricao_motivo": k["motivo"]},
                "resposta": "ok"}
    monkeypatch.setattr(API, "rejeitar_pedido", rejeita)
    _post(s, f"/rcpn/pedidos/{p}/rejeitar",
          {"motivo": "o registro nao e desta serventia"},
          de=f"/rcpn/pedidos/{p}")
    con = _con(s)
    linha = con.execute("SELECT * FROM rc_pedidos WHERE id=?", (p,)).fetchone()
    con.close()
    assert linha["situacao"] == ESQ.REJEITADO
    assert linha["rejeicao_motivo"] == "o registro nao e desta serventia"
    assert mandado["motivo"] == "o registro nao e desta serventia"


def test_dispensar_avisa_que_a_central_continua_com_o_pedido(s):
    ident = _assento(s)
    p = _pedido(s, assento_id=ident)
    r = _post(s, f"/rcpn/pedidos/{p}/dispensar",
              {"motivo": "pedido duplicado, ja atendido em papel"},
              de=f"/rcpn/pedidos/{p}")
    html = r.get_data(as_text=True)
    assert "continua com ele em aberto" in html


def test_atender_manda_o_id_verificador_e_a_averbacao_NULA_fora_de_SP(
        s, monkeypatch, com_token):
    """**Fora de Sao Paulo a quantidade de averbacoes vai NULA** — esta na
    descricao do proprio caminho, e a serventia e do Maranhao."""
    ident = _assento(s)
    p = _pedido(s, assento_id=ident)
    e = _eletronica(s, p, ident)
    mandado = {}

    def envia(**k):
        mandado.update(k)
        return {"numero_pedido": k["numero_pedido"], "modulo": k["modulo"],
                "corpo": {"numero_pedido": k["numero_pedido"]},
                "resposta": 1, "bruto": {"success": True}}
    monkeypatch.setattr(API, "enviar_pedido", envia)
    _post(s, f"/rcpn/pedidos/{p}/atender",
          {"eletronica_id": e, "valor_emolumentos": "43,76",
           "quantidade_averbacao": "3"},
          de=f"/rcpn/pedidos/{p}")
    assert mandado["id_verificador"] == "abc-123"
    assert mandado["uf_da_serventia"] == "MA"
    con = _con(s)
    linha = con.execute("SELECT * FROM rc_pedidos WHERE id=?", (p,)).fetchone()
    con.close()
    assert linha["situacao"] == ESQ.ATENDIDO


def test_a_ficha_diz_que_a_averbacao_nao_vai_fora_de_SP(s, com_token):
    ident = _assento(s)
    p = _pedido(s, assento_id=ident)
    _eletronica(s, p, ident)
    html = s["c"].get(f"/rcpn/pedidos/{p}").get_data(as_text=True)
    assert "não vai" in html
    assert "SP" in html


def test_a_sugestao_do_valor_adicional_diz_de_onde_veio(s, com_token):
    ident = _assento(s)
    p = _pedido(s, assento_id=ident)
    _eletronica(s, p, ident)
    html = s["c"].get(
        f"/rcpn/pedidos/{p}?valor_emolumentos=50,00").get_data(as_text=True)
    assert "depósito prévio" in html
    assert "43.76" in html or "43,76" in html


# --------------------------------------------------------- quem pode o quê


def test_responder_NAO_e_do_balcao(cg_casa, monkeypatch):
    """Conferir e baixar sao de quem atende; responder e do oficial."""
    monkeypatch.setattr(API, "tem_credencial", lambda **k: True)
    s = _sessao(cg_casa, papel="USER")
    ident = _assento(s)
    p = _pedido(s, assento_id=ident)
    # Ver, pode:
    assert s["c"].get("/rcpn/pedidos").status_code == 200
    assert s["c"].get(f"/rcpn/pedidos/{p}").status_code == 200
    # Responder, nao:
    for caminho in (f"/rcpn/pedidos/{p}/rejeitar",
                    f"/rcpn/pedidos/{p}/dispensar",
                    f"/rcpn/pedidos/{p}/emitir",
                    f"/rcpn/pedidos/{p}/atender"):
        r = s["c"].post(caminho, data={"csrf_token": _token(
            s["c"].get(f"/rcpn/pedidos/{p}").get_data(as_text=True))})
        assert r.status_code == 403, caminho


def test_baixar_a_fila_e_do_balcao(cg_casa, monkeypatch):
    monkeypatch.setattr(API, "tem_credencial", lambda **k: True)
    monkeypatch.setattr(API, "obter_pedidos", lambda m, c, **k: {
        "modulo": m, "quantos": 0, "quantos_a_central_disse": 0,
        "contagem_bate": True, "pedidos": []})
    s = _sessao(cg_casa, papel="USER")
    r = _post(s, "/rcpn/pedidos/baixar", {"modulo": "CRC"})
    assert r.status_code == 200
    assert "entraram 0" in r.get_data(as_text=True)
