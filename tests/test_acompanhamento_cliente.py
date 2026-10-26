"""O código de acompanhamento e o envio ao portal do cliente — 26/10/2026.

    «portal do cliente para acompanhar o pedido e baixar o recibo», com
     «código no recibo» — o oficial.

O que estes testes guardam, e por quê:
  - o CONTRATO do módulo, que o atendente de IA do WhatsApp usa em paralelo;
  - que o código NUNCA fica em claro no banco nem sobe para a VPS;
  - que «não existe» e «código errado» dão a mesma resposta;
  - que o protesto fica fora de tudo;
  - que o retrato não leva dado pessoal;
  - e que o que o servidor manda, a VPS aceita (as duas pontas do hash).
"""
from __future__ import annotations

import importlib.util
import inspect
import io
import json
import re
import sqlite3
import sys
import zipfile
from datetime import date
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import acompanhamento_cliente as ACOMP  # noqa: E402
import portal_cliente as PORTAL  # noqa: E402

SENHA = "Senha#12345"
TOKEN = "t" * 40
URL = "https://portal.exemplo.invalid/portal"
HOJE = date(2026, 10, 26)


def _vps():
    espec = importlib.util.spec_from_file_location(
        "portal_vps", RAIZ / "vps" / "portal" / "portal_vps.py")
    modulo = importlib.util.module_from_spec(espec)
    espec.loader.exec_module(modulo)
    return modulo


def _token_da_tela(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa):
    db = cg_casa["db"]
    c = cg_casa["cliente"]
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c.post("/login", data={"username": "mario", "password": SENHA,
                           "csrf_token": _token_da_tela(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    ACOMP._TENTATIVAS.clear()
    return cg_casa


def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


_SEQ = iter(range(500, 10_000))


def _protocolo(con, *, atribuicao="RI", situacao="ABERTO", tipo="SERVICO",
               itens=(), interessado="BEATRIZ EXEMPLO DE SOUZA",
               documento="000.000.001-91") -> tuple[int, str]:
    numero = f"2026.10.{next(_SEQ)}"
    cur = con.execute(
        """INSERT INTO cx_protocolos (numero, data_abertura, atribuicao, interessado,
               interessado_documento, telefone, assunto, situacao, tipo, origem,
               criado_em, previsao_entrega)
           VALUES (?, '2026-10-20', ?, ?, ?, '(11) 98888-7777', 'ESCRITURA DE COMPRA',
                   ?, ?, 'MANUAL', '2026-10-20T09:00', '2026-11-05')""",
        (numero, atribuicao, interessado, documento, situacao, tipo))
    pid = int(cur.lastrowid)
    for quitado, usada in itens:
        con.execute(
            """INSERT INTO cx_protocolo_atos (protocolo_id, codigo_ato, descricao,
                   quantidade, quitado, quantidade_usada, valor_total, origem)
               VALUES (?, '16.1', 'um ato', 1, ?, ?, '57,30', 'MANUAL')""",
            (pid, quitado, usada))
    return pid, numero


# ------------------------------------------------------------ o contrato

def test_o_contrato_do_modulo():
    """O atendente do WhatsApp chama estas quatro — nomes e parâmetros fixos."""
    assert list(inspect.signature(ACOMP.gerar_codigo).parameters) == []
    assert list(inspect.signature(ACOMP.codigo_do_protocolo).parameters) == [
        "con", "protocolo_id"]
    assert list(inspect.signature(ACOMP.consultar).parameters) == [
        "con", "numero", "codigo"]
    assert "con" in inspect.signature(ACOMP.situacao_publica).parameters
    frases = set(ACOMP.SITUACOES_PUBLICAS.values())
    for esperada in ("em atendimento", "aguardando documento/exigência",
                     "pronto para retirar", "entregue", "cancelado"):
        assert esperada in frases


def test_o_codigo_e_aleatorio_e_sem_letra_ambigua():
    vistos = {ACOMP.gerar_codigo() for _ in range(300)}
    assert len(vistos) == 300
    for c in vistos:
        assert len(c) == 8 and not set(c) & set("0O1I")
        assert ACOMP.codigo_valido(c)
    assert ACOMP.formatar_codigo("abcd efgh") == "ABCD-EFGH"


# ------------------------------------------------------------ o código no banco

def test_o_codigo_nasce_uma_vez_e_o_banco_so_guarda_hash_e_cifra(casa):
    con = _con(casa)
    with con:
        pid, _ = _protocolo(con)
        primeiro = ACOMP.codigo_do_protocolo(con, pid)
        segundo = ACOMP.codigo_do_protocolo(con, pid)
    assert primeiro == segundo and ACOMP.codigo_valido(primeiro)
    linha = dict(con.execute("SELECT * FROM cx_protocolos WHERE id=?", (pid,)).fetchone())
    assert linha["acompanhamento_hash"].startswith("pbkdf2_sha256$200000$")
    assert linha["acompanhamento_cifra"].startswith("v1:")
    # EM CLARO, EM COLUNA NENHUMA — nem com hífen.
    texto = json.dumps(linha, default=str)
    assert primeiro not in texto and ACOMP.formatar_codigo(primeiro) not in texto
    assert ACOMP.codigo_ja_gravado(con, pid) == primeiro


def test_trocar_o_codigo_invalida_o_de_antes(casa):
    con = _con(casa)
    with con:
        pid, numero = _protocolo(con)
        antigo = ACOMP.codigo_do_protocolo(con, pid)
        novo = ACOMP.trocar_codigo(con, pid)
    assert novo != antigo
    assert ACOMP.consultar(con, numero, antigo) is None
    assert ACOMP.consultar(con, numero, novo)["numero"] == numero


def test_cofre_sem_a_chave_troca_o_codigo_em_vez_de_travar_o_balcao(casa):
    con = _con(casa)
    with con:
        pid, numero = _protocolo(con)
        antigo = ACOMP.codigo_do_protocolo(con, pid)
    (Path(casa["dados"]) / "portal.cred").unlink()
    with con:
        novo = ACOMP.codigo_do_protocolo(con, pid)
    assert novo != antigo
    assert ACOMP.consultar(con, numero, novo) is not None


# ------------------------------------------------------------ a consulta

def test_consultar_devolve_so_o_retrato_publico(casa):
    con = _con(casa)
    with con:
        pid, numero = _protocolo(con, interessado="CARLA EXEMPLO PEREIRA")
        codigo = ACOMP.codigo_do_protocolo(con, pid)
    r = ACOMP.consultar(con, numero, codigo.lower()[:4] + "-" + codigo[4:].lower())
    assert set(r) == {"numero", "situacao_publica", "previsao", "atualizado_em",
                      "atribuicao"}
    assert r["numero"] == numero and r["previsao"] == "2026-11-05"
    assert r["atribuicao"] == "Registro de Imóveis"
    texto = json.dumps(r, ensure_ascii=False)
    for pessoal in ("CARLA", "000.000.001-91", "98888", "ESCRITURA", "57,30"):
        assert pessoal not in texto


def test_nao_existe_e_codigo_errado_sao_a_mesma_resposta(casa):
    con = _con(casa)
    with con:
        pid, numero = _protocolo(con)
        ACOMP.codigo_do_protocolo(con, pid)
    assert ACOMP.consultar(con, numero, "ZZZZZZZZ") is None
    assert ACOMP.consultar(con, "2099.01.1", "ZZZZZZZZ") is None
    assert ACOMP.consultar(con, numero, "") is None
    assert ACOMP.consultar(con, "", "") is None


def test_quem_erra_demais_o_numero_fica_travado_ate_com_o_codigo_certo(casa):
    con = _con(casa)
    with con:
        pid, numero = _protocolo(con)
        codigo = ACOMP.codigo_do_protocolo(con, pid)
    for _ in range(ACOMP.ERROS_POR_NUMERO):
        assert ACOMP.consultar(con, numero, "ZZZZZZZZ") is None
    assert ACOMP.consultar(con, numero, codigo) is None
    ACOMP._TENTATIVAS.clear()
    assert ACOMP.consultar(con, numero, codigo) is not None


def test_protesto_fica_fora_de_tudo(casa):
    con = _con(casa)
    with con:
        pid, numero = _protocolo(con, atribuicao="PROTESTO")
        with pytest.raises(ACOMP.AcompanhamentoError):
            ACOMP.codigo_do_protocolo(con, pid)
        assert ACOMP.codigo_para_o_papel(con, pid) is None
        # nem um hash posto à mão abre a consulta
        con.execute("UPDATE cx_protocolos SET acompanhamento_hash=? WHERE id=?",
                    (ACOMP.hash_do_codigo("ABCDEFGH"), pid))
    assert ACOMP.consultar(con, numero, "ABCDEFGH") is None


def test_orcamento_nao_tem_codigo(casa):
    con = _con(casa)
    with con:
        pid, _ = _protocolo(con, tipo="ORCAMENTO")
        assert ACOMP.codigo_para_o_papel(con, pid) is None


# ------------------------------------------------------------ a situação

@pytest.mark.parametrize("situacao, itens, esperada", [
    ("ABERTO", (), "em atendimento"),
    ("A_PAGAR", ((0, 0),), "aguardando pagamento"),
    ("PAGO", ((1, 0),), "em atendimento"),
    ("PAGO", ((1, 1),), "pronto para retirar"),
    ("ENTREGUE", ((1, 1),), "entregue"),
    ("CANCELADO", (), "cancelado"),
])
def test_a_situacao_interna_vira_linguagem_simples(casa, situacao, itens, esperada):
    con = _con(casa)
    with con:
        pid, _ = _protocolo(con, situacao=situacao, itens=itens)
    p = dict(con.execute("SELECT * FROM cx_protocolos WHERE id=?", (pid,)).fetchone())
    assert ACOMP.situacao_publica(con, p) == esperada


def test_ri_em_exigencia_diz_ao_cliente_que_falta_documento(casa):
    con = _con(casa)
    with con:
        prenot = int(con.execute(
            """INSERT INTO ri_protocolos (numero, data_prenotacao, situacao,
                   data_limite, criado_em)
               VALUES (?, '2026-10-20', 'DEVOLVIDO', '2026-12-31', '2026-10-20T09:00')""",
            (next(_SEQ),)).lastrowid)
        pid, _ = _protocolo(con, situacao="PAGO", itens=((1, 0),))
        con.execute("UPDATE cx_protocolos SET ri_protocolo_id=? WHERE id=?", (prenot, pid))
    p = dict(con.execute("SELECT * FROM cx_protocolos WHERE id=?", (pid,)).fetchone())
    assert ACOMP.situacao_publica(con, p, hoje="2026-10-26") == \
        "aguardando documento/exigência"


# ------------------------------------------------------------ o envio à VPS

def _configurar(casa, *, ligado=True):
    con = _con(casa)
    with con:
        PORTAL.gravar_configuracao(con, url=URL, ligado=ligado, token=TOKEN)
    return con


def _recibo(con, pid, numero):
    con.execute(
        """INSERT INTO cx_recibos (numero, ano, data_emissao, protocolo_id,
               protocolo_numero, pagador, valor_total, discriminacao, corpo,
               hash_recibo, criado_em)
           VALUES (?, 2026, '2026-10-21', ?, ?, 'BEATRIZ EXEMPLO DE SOUZA', '57,30',
                   '{}', '{}', ?, '2026-10-21T10:00')""",
        (next(_SEQ), pid, numero, "ab" * 32))


def _pdf_falso(con, recibo, settings):
    return b"%PDF-1.4 recibo de teste " + str(recibo["numero"]).encode()


def test_o_token_fica_no_cofre_e_o_endereco_tem_de_ser_https(casa):
    con = _configurar(casa)
    valores = " ".join(str(r[0]) for r in con.execute("SELECT value FROM settings"))
    assert TOKEN not in valores
    assert PORTAL.configuracao(con)["tem_token"]
    with pytest.raises(PORTAL.PortalError):
        PORTAL.endereco_valido("http://portal.exemplo.invalid/portal")
    with pytest.raises(PORTAL.PortalError):
        with con:
            PORTAL.gravar_configuracao(con, url=URL, ligado=True, token="curto")


def test_desligado_nada_sobe(casa):
    _configurar(casa, ligado=False)
    chamadas = []
    resumo = PORTAL.enviar(casa["db"], hoje=HOJE,
                           http_post=lambda *a: chamadas.append(a) or (200, "{}"))
    assert not resumo["ok"] and "desligado" in resumo["motivo"] and not chamadas


def test_o_envio_leva_so_o_retrato_e_nao_repete(casa):
    con = _configurar(casa)
    with con:
        pid, numero = _protocolo(con, interessado="CARLA EXEMPLO PEREIRA")
        codigo = ACOMP.codigo_do_protocolo(con, pid)
        _recibo(con, pid, numero)
        pid_pt, numero_pt = _protocolo(con, atribuicao="PROTESTO")
        pid_rc, numero_rc = _protocolo(con, atribuicao="RCPN")
        ACOMP.codigo_do_protocolo(con, pid_rc)
        _recibo(con, pid_rc, numero_rc)
    corpos = []

    def post(url, token, corpo):
        assert url == URL + "/api/retratos" and token == TOKEN
        corpos.append(json.loads(corpo))
        return 200, '{"ok": true}'

    resumo = PORTAL.enviar(casa["db"], hoje=HOJE, http_post=post, gerar_pdf=_pdf_falso)
    assert resumo["ok"] and resumo["enviados"] >= 2
    retratos = {r["numero"]: r for c in corpos for r in c["retratos"]}
    assert numero in retratos and numero_rc in retratos and numero_pt not in retratos
    texto = json.dumps(corpos, ensure_ascii=False)
    for proibido in (codigo, ACOMP.formatar_codigo(codigo), "CARLA", "000.000.001-91",
                     "98888", "ESCRITURA"):
        assert proibido not in texto
    assert len(retratos[numero]["recibos"]) == 1
    assert retratos[numero_rc]["recibos"] == []       # civil: sem recibo
    # a segunda rodada não manda o que não mudou
    corpos.clear()
    PORTAL.enviar(casa["db"], hoje=HOJE, http_post=post, gerar_pdf=_pdf_falso)
    assert not any(numero in json.dumps(c) for c in corpos)


def test_vps_fora_do_ar_nao_marca_nada(casa):
    con = _configurar(casa)
    with con:
        pid, _ = _protocolo(con)
        ACOMP.codigo_do_protocolo(con, pid)
    resumo = PORTAL.enviar(casa["db"], hoje=HOJE, http_post=lambda *a: (0, "recusado"),
                           gerar_pdf=_pdf_falso)
    assert not resumo["ok"] and "HTTP 0" in resumo["motivo"]
    assert con.execute("SELECT portal_marca FROM cx_protocolos WHERE id=?",
                       (pid,)).fetchone()[0] is None


def test_o_que_o_servidor_manda_a_vps_aceita_e_o_codigo_abre(casa, tmp_path):
    """As duas pontas do hash, de verdade: o pacote vai ao `Portal.receber` da VPS."""
    vps = _vps()
    portal = vps.Portal(str(tmp_path / "portal.sqlite3"), TOKEN, exigir_https=False)
    con = _configurar(casa)
    with con:
        pid, numero = _protocolo(con)
        codigo = ACOMP.codigo_do_protocolo(con, pid)
        _recibo(con, pid, numero)

    def post(url, token, corpo):
        return 200, json.dumps(portal.receber(corpo))

    assert PORTAL.enviar(casa["db"], hoje=HOJE, http_post=post, gerar_pdf=_pdf_falso)["ok"]
    estado, retrato = portal.consultar(numero, ACOMP.formatar_codigo(codigo), "203.0.113.9")
    assert estado == "ok" and retrato["situacao"] == "em atendimento"
    assert len(retrato["recibos"]) == 1
    assert portal.consultar(numero, "ZZZZZZZZ", "203.0.113.9")[0] == "nao_confere"
    # encerrado há mais de 90 dias: a VPS recebe a ordem de apagar
    with con:
        con.execute("""UPDATE cx_protocolos SET situacao='ENTREGUE',
                       data_finalizacao='2026-06-01' WHERE id=?""", (pid,))
    assert PORTAL.enviar(casa["db"], hoje=HOJE, http_post=post,
                         gerar_pdf=_pdf_falso)["removidos"] == 1
    assert portal.consultar(numero, codigo, "203.0.113.10")[0] == "nao_confere"


# ------------------------------------------------------------ as telas

def _odt_texto(resposta) -> str:
    with zipfile.ZipFile(io.BytesIO(resposta.data)) as z:
        return z.read("content.xml").decode("utf-8")


def test_o_protocolo_de_recepcao_sai_com_o_codigo(casa):
    con = _con(casa)
    with con:
        pid, numero = _protocolo(con)
    c = casa["cliente"]
    tela = c.get(f"/caixa/protocolos/{pid}").get_data(as_text=True)
    r = c.post(f"/caixa/protocolos/{pid}/recepcao",
               data={"csrf_token": _token_da_tela(tela)})
    assert r.status_code == 200
    codigo = ACOMP.codigo_ja_gravado(_con(casa), pid)
    assert codigo
    texto = _odt_texto(r)
    assert ACOMP.formatar_codigo(codigo) in texto and "ACOMPANHE O SEU PEDIDO" in texto


def test_o_recibo_do_lancamento_cria_e_imprime_o_codigo(casa):
    con = _con(casa)
    with con:
        pid, numero = _protocolo(con)
        lid = int(con.execute(
            """INSERT INTO cx_lancamentos (protocolo_id, data, natureza, sentido,
                   forma_pagamento, valor, criado_em)
               VALUES (?, '2026-10-21', 'RECEBIMENTO', 'ENTRADA', 'PIX', '57,30',
                       '2026-10-21T10:00')""", (pid,)).lastrowid)
    c = casa["cliente"]
    tela = c.get(f"/caixa/protocolos/{pid}").get_data(as_text=True)
    r = c.post(f"/caixa/recibo/{lid}", data={"csrf_token": _token_da_tela(tela)},
               follow_redirects=True)
    assert r.status_code == 200
    codigo = ACOMP.codigo_ja_gravado(_con(casa), pid)
    assert codigo and ACOMP.formatar_codigo(codigo) in _odt_texto(r)


def test_a_ficha_mostra_gera_e_troca_o_codigo(casa):
    con = _con(casa)
    with con:
        pid, _ = _protocolo(con)
    c = casa["cliente"]
    tela = c.get(f"/caixa/protocolos/{pid}").get_data(as_text=True)
    assert "Gerar o código" in tela
    c.post(f"/caixa/protocolos/{pid}", data={"csrf_token": _token_da_tela(tela),
                                              "acao": "acompanhamento_gerar"})
    codigo = ACOMP.codigo_ja_gravado(_con(casa), pid)
    tela = c.get(f"/caixa/protocolos/{pid}").get_data(as_text=True)
    assert ACOMP.formatar_codigo(codigo) in tela and "Trocar o código" in tela
    c.post(f"/caixa/protocolos/{pid}", data={"csrf_token": _token_da_tela(tela),
                                              "acao": "acompanhamento_trocar"})
    assert ACOMP.codigo_ja_gravado(_con(casa), pid) != codigo
    # o código não vai para a auditoria
    detalhes = " ".join(str(r[0]) for r in _con(casa).execute(
        "SELECT details FROM audit_logs WHERE action LIKE 'PROTOCOLO_ACOMPANHAMENTO%'"))
    assert codigo not in detalhes


def test_a_tela_do_portal_grava_sem_mostrar_o_token(casa):
    c = casa["cliente"]
    tela = c.get("/caixa/portal-do-cliente").get_data(as_text=True)
    assert "Portal do cliente" in tela
    r = c.post("/caixa/portal-do-cliente",
               data={"csrf_token": _token_da_tela(tela), "acao": "gravar",
                     "url": URL, "token": TOKEN, "ligado": "1"},
               follow_redirects=True)
    pagina = r.get_data(as_text=True)
    assert TOKEN not in pagina and "gravado (não aparece)" in pagina
    cfg = PORTAL.configuracao(_con(casa))
    assert cfg["ligado"] and cfg["url"] == URL
