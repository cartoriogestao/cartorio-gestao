"""Encerrar a prenotação do RI com motivo da lista.

Pedido da Tabeliã e Registradora Substituta (Leidiane): na ficha, o oficial
escolhe o motivo, e a situação sai do motivo. O painel dos pedidos usa o
mesmo caminho. A reabertura continua valendo sobre o que este caminho fechar,
e o rastro (quem, quando, motivo, observação) permanece.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ri_prenotacao_encerrar as ENCERRAR  # noqa: E402
import ri_schema  # noqa: E402

SENHA = "Senha#12345"
NUMERO = 12001


def _csrf(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _entrar(cliente, username: str) -> None:
    pagina = cliente.get("/login").get_data(as_text=True)
    cliente.post("/login", data={"username": username, "password": SENHA,
                                 "csrf_token": _csrf(pagina)},
                 follow_redirects=True)


@pytest.fixture()
def serventia(cg_casa):
    app = cg_casa["app"]
    d = cg_casa["db"]
    d.create_user("registro", "LAURA MARIA DA COSTA", SENHA, "ADMIN")
    d.create_user("gerente", "HELENA GERENTE", SENHA, "MANAGER")
    d.create_user("balcao", "ANA DO BALCAO", SENHA, "USER")

    prenotado = date.today() - timedelta(days=5)
    limite = date.today() + timedelta(days=10)
    con = sqlite3.connect(cg_casa["banco"])
    con.execute(
        """INSERT INTO ri_protocolos
           (numero, livro, data_prenotacao, apresentante, natureza_titulo,
            objeto, data_limite, situacao, origem, criado_em)
           VALUES (?, '1A', ?, 'CONSTRUTORA ALFA LTDA',
                   'Escritura de compra e venda', 'Lote 12', ?, 'ABERTO',
                   'MANUAL', ?)""",
        (NUMERO, prenotado.isoformat(), limite.isoformat(),
         "2026-10-30T09:00:00"))
    con.commit()
    pid = con.execute(
        "SELECT id FROM ri_protocolos WHERE numero=?", (NUMERO,)).fetchone()[0]
    con.close()

    c = app.test_client()
    _entrar(c, "registro")
    return {"app": app, "db": d, "cliente": c, "banco": cg_casa["banco"],
            "pid": pid, "limite": limite.isoformat(),
            "prenotado": prenotado.isoformat()}


def _protocolo(s):
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    linha = con.execute(
        "SELECT * FROM ri_protocolos WHERE id=?", (s["pid"],)).fetchone()
    con.close()
    return dict(linha)


def _post(s, cliente=None, **dados):
    cliente = cliente or s["cliente"]
    html = cliente.get(
        f"/registro-imoveis/protocolo/{s['pid']}").get_data(as_text=True)
    dados.setdefault("csrf_token", _csrf(html))
    dados.setdefault("acao", "encerrar")
    dados.setdefault("confirmar", "1")
    return cliente.post(f"/registro-imoveis/protocolo/{s['pid']}",
                        data=dados, follow_redirects=True)


# ------------------------------------------------------- a lista, sem tela


def test_a_lista_tem_os_sete_motivos_e_a_situacao_de_cada_um():
    assert list(ENCERRAR.MOTIVOS) == [
        "TITULO_REGISTRADO", "DECURSO_PRAZO", "DESISTENCIA", "EXIGENCIA",
        "DEVOLVIDO_NOTA", "RECUSA", "OUTRO",
    ]
    esperado = {
        "TITULO_REGISTRADO": "ENCERRADO",
        "DECURSO_PRAZO": "CANCELADO",
        "DESISTENCIA": "CANCELADO",
        "EXIGENCIA": "CANCELADO",
        "DEVOLVIDO_NOTA": "DEVOLVIDO",
        "RECUSA": "RECUSADO",
        "OUTRO": "CANCELADO",
    }
    for chave, situacao in esperado.items():
        assert ENCERRAR.MOTIVOS[chave]["situacao"] == situacao
    assert ENCERRAR.MOTIVOS["TITULO_REGISTRADO"]["rotulo"] == "Título registrado"
    assert "art. 205" in ENCERRAR.MOTIVOS["DECURSO_PRAZO"]["rotulo"]


def test_outro_sem_observacao_e_recusado():
    with pytest.raises(ENCERRAR.EncerrarError, match="observação"):
        ENCERRAR.resolver("OUTRO", observacao="   ")


def test_outro_aceita_a_situacao_escolhida_e_os_demais_nao():
    outro = ENCERRAR.resolver("OUTRO", observacao="caso fora da lista",
                              situacao_escolhida="recusado")
    assert outro["situacao"] == "RECUSADO"
    assert outro["observacao"] == "caso fora da lista"
    sem_escolha = ENCERRAR.resolver("OUTRO", observacao="sem situação marcada")
    assert sem_escolha["situacao"] == "CANCELADO"
    registrado = ENCERRAR.resolver(
        "TITULO_REGISTRADO", situacao_escolhida="CANCELADO")
    assert registrado["situacao"] == "ENCERRADO"


def test_texto_livre_nao_e_motivo():
    with pytest.raises(ENCERRAR.EncerrarError, match="lista"):
        ENCERRAR.resolver("porque sim, título estranho")


def test_as_colunas_entram_so_por_add_column(serventia):
    """Texto, sem NOT NULL: o ALTER em tabela que já tem linha é o que a
    produção aguenta. Rodar o init de novo é o contrato de idempotência, e
    quem o exerce na suíte inteira é `test_esquemas`."""
    nomes = ("encerrado_em", "encerrado_por", "motivo_encerramento",
             "obs_encerramento")
    for nome in nomes:
        entrada = ("ri_protocolos", nome, "TEXT")
        assert entrada in ri_schema.MIGRACOES
        assert "NOT NULL" not in entrada[2]
    con = sqlite3.connect(serventia["banco"])
    cols = {x[1] for x in con.execute("PRAGMA table_info(ri_protocolos)")}
    con.close()
    for nome in nomes:
        assert nome in cols


# --------------------------------------------------------------- a ficha


@pytest.mark.parametrize("chave,situacao,obs", [
    ("TITULO_REGISTRADO", "ENCERRADO", ""),
    ("DECURSO_PRAZO", "CANCELADO", ""),
    ("DESISTENCIA", "CANCELADO", ""),
    ("EXIGENCIA", "CANCELADO", ""),
    ("DEVOLVIDO_NOTA", "DEVOLVIDO", ""),
    ("RECUSA", "RECUSADO", ""),
    ("OUTRO", "CANCELADO", "caso fora da lista, conferido com a oficial"),
])
def test_cada_motivo_encerra_com_a_situacao_da_lista(serventia, chave, situacao, obs):
    _post(serventia, motivo=chave, observacao=obs)
    p = _protocolo(serventia)
    assert p["situacao"] == situacao
    assert p["motivo_encerramento"] == ENCERRAR.MOTIVOS[chave]["rotulo"]
    assert p["encerrado_por"] == "LAURA MARIA DA COSTA"
    assert p["encerrado_em"]
    if obs:
        assert p["obs_encerramento"] == obs
    else:
        assert not p["obs_encerramento"]
    assert f"[Encerrado] {ENCERRAR.MOTIVOS[chave]['rotulo']}" in (p["anotacao"] or "")


def test_outro_sem_observacao_nao_grava(serventia):
    r = _post(serventia, motivo="OUTRO", observacao="")
    assert _protocolo(serventia)["situacao"] == "ABERTO"
    assert "observação é obrigatória" in r.get_data(as_text=True)


def test_outro_com_situacao_escolhida(serventia):
    _post(serventia, motivo="OUTRO", situacao="RECUSADO",
          observacao="título de outro cartório, recusado na qualificação")
    p = _protocolo(serventia)
    assert p["situacao"] == "RECUSADO"
    assert p["motivo_encerramento"] == "Outro"
    assert "outro cartório" in p["obs_encerramento"]


def test_motivo_da_lista_ignora_situacao_mandada_pela_tela(serventia):
    """A situação do motivo vence o que o formulário mandar — senão a lista
    não decide nada."""
    _post(serventia, motivo="TITULO_REGISTRADO", situacao="CANCELADO")
    assert _protocolo(serventia)["situacao"] == "ENCERRADO"


def test_sem_confirmacao_nao_encerra(serventia):
    r = _post(serventia, motivo="DECURSO_PRAZO", confirmar="0")
    assert _protocolo(serventia)["situacao"] == "ABERTO"
    assert "Confirme o encerramento" in r.get_data(as_text=True)


def test_perfil_comum_nao_encerra_nem_ve_o_quadro(serventia):
    c = serventia["app"].test_client()
    _entrar(c, "balcao")
    html = c.get(f"/registro-imoveis/protocolo/{serventia['pid']}").get_data(
        as_text=True)
    assert "Encerrar esta prenotação" not in html
    r = _post(serventia, cliente=c, motivo="DECURSO_PRAZO")
    assert _protocolo(serventia)["situacao"] == "ABERTO"
    assert "oficial ou do gerente" in r.get_data(as_text=True)


def test_gerente_encerra(serventia):
    c = serventia["app"].test_client()
    _entrar(c, "gerente")
    _post(serventia, cliente=c, motivo="DESISTENCIA")
    p = _protocolo(serventia)
    assert p["situacao"] == "CANCELADO"
    assert p["encerrado_por"] == "HELENA GERENTE"


def test_devolvida_ainda_pode_ser_encerrada(serventia):
    """DEVOLVIDO não é fim: a nota saiu e o prazo continua. Encerrar daí é
    a decisão de não esperar mais."""
    con = sqlite3.connect(serventia["banco"])
    con.execute("UPDATE ri_protocolos SET situacao='DEVOLVIDO' WHERE id=?",
                (serventia["pid"],))
    con.commit()
    con.close()
    html = serventia["cliente"].get(
        f"/registro-imoveis/protocolo/{serventia['pid']}").get_data(as_text=True)
    assert "Encerrar esta prenotação" in html
    assert "está devolvida" in html
    _post(serventia, motivo="EXIGENCIA",
          observacao="o prazo da exigência correu")
    p = _protocolo(serventia)
    assert p["situacao"] == "CANCELADO"
    assert "Exigência não cumprida" in p["motivo_encerramento"]


def test_ja_encerrada_nao_encerra_de_novo(serventia):
    _post(serventia, motivo="RECUSA")
    r = _post(serventia, motivo="DECURSO_PRAZO")
    p = _protocolo(serventia)
    assert p["situacao"] == "RECUSADO"
    assert p["motivo_encerramento"] == "Recusa do título"
    assert "reabra" in r.get_data(as_text=True)
    assert (p["anotacao"] or "").count("[Encerrado]") == 1


def test_a_ficha_aberta_mostra_o_quadro_e_a_encerrada_mostra_o_rastro(serventia):
    html = serventia["cliente"].get(
        f"/registro-imoveis/protocolo/{serventia['pid']}").get_data(as_text=True)
    assert "Encerrar esta prenotação" in html
    assert "Título registrado" in html
    assert 'name="motivo"' in html
    assert 'name="confirmar"' in html
    _post(serventia, motivo="OUTRO", situacao="DEVOLVIDO",
          observacao="devolveu o título em mãos, sem nota formal")
    pagina = serventia["cliente"].get(
        f"/registro-imoveis/protocolo/{serventia['pid']}").get_data(as_text=True)
    assert "Esta prenotação foi encerrada" in pagina
    assert "LAURA MARIA DA COSTA" in pagina
    assert "Motivo: Outro" in pagina
    assert "Observação: devolveu o título em mãos" in pagina
    # DEVOLVIDO continua encerrável; o rastro da vez anterior fica na tela.
    assert "Encerrar esta prenotação" in pagina


def test_reabrir_depois_do_encerramento_novo(serventia):
    antes = _protocolo(serventia)
    _post(serventia, motivo="TITULO_REGISTRADO",
          observacao="lavrado e depois visto que era outro imóvel")
    _post(serventia, acao="reabrir", confirmar="0",
          motivo="encerrado por engano — o título não chegou a ser registrado")
    p = _protocolo(serventia)
    assert p["situacao"] == "ABERTO"
    assert p["situacao_anterior"] == "ENCERRADO"
    assert "engano" in (p["motivo_reabertura"] or "")
    assert p["reaberto_por"] == "LAURA MARIA DA COSTA"
    # Reabrir não apaga o encerramento nem mexe no prazo.
    assert p["motivo_encerramento"] == "Título registrado"
    assert p["encerrado_em"]
    assert "outro imóvel" in (p["obs_encerramento"] or "")
    assert p["data_limite"] == antes["data_limite"]
    assert p["data_prenotacao"] == antes["data_prenotacao"]
    html = serventia["cliente"].get(
        f"/registro-imoveis/protocolo/{serventia['pid']}").get_data(as_text=True)
    assert "foi encerrada" in html
    assert "foi reaberto" in html


def test_o_encerramento_fica_na_auditoria(serventia):
    _post(serventia, motivo="RECUSA", observacao="documento sem firma")
    con = sqlite3.connect(serventia["banco"])
    linha = con.execute(
        """SELECT details FROM audit_logs
            WHERE action='RI_PROTOCOLO_ENCERRADO' AND entity_id=?""",
        (serventia["pid"],)).fetchone()
    con.close()
    assert linha, "o encerramento não foi auditado"
    d = json.loads(linha[0])
    assert d["situacao"] == "RECUSADO"
    assert d["motivo_chave"] == "RECUSA"
    assert d["motivo"] == "Recusa do título"
    assert d["de"] == "ABERTO"
    assert d["observacao"] == "documento sem firma"


def test_a_rota_antiga_usa_a_mesma_validacao(serventia):
    """Quem ainda posta em `/registro-imoveis/protocolo` não fura a lista
    nem a checagem de papel."""
    balcao = serventia["app"].test_client()
    _entrar(balcao, "balcao")
    pagina = balcao.get("/registro-imoveis/protocolo").get_data(as_text=True)
    negado = balcao.post("/registro-imoveis/protocolo", data={
        "acao": "encerrar", "protocolo_id": str(serventia["pid"]),
        "motivo": "RECUSA", "confirmar": "1", "csrf_token": _csrf(pagina)},
        follow_redirects=True)
    assert _protocolo(serventia)["situacao"] == "ABERTO"
    assert "oficial ou do gerente" in negado.get_data(as_text=True)

    c = serventia["cliente"]
    html = c.get("/registro-imoveis/protocolo").get_data(as_text=True)
    token = _csrf(html)
    livre = c.post("/registro-imoveis/protocolo", data={
        "acao": "encerrar", "protocolo_id": str(serventia["pid"]),
        "motivo": "texto livre com mais de cinco letras", "confirmar": "1",
        "csrf_token": token}, follow_redirects=True)
    assert _protocolo(serventia)["situacao"] == "ABERTO"
    assert "lista" in livre.get_data(as_text=True)
    c.post("/registro-imoveis/protocolo", data={
        "acao": "encerrar", "protocolo_id": str(serventia["pid"]),
        "motivo": "DECURSO_PRAZO", "confirmar": "1", "csrf_token": token},
        follow_redirects=True)
    p = _protocolo(serventia)
    assert p["situacao"] == "CANCELADO"
    assert "art. 205" in p["motivo_encerramento"]


def test_a_lista_do_protocolo_filtra_recusado(serventia):
    html = serventia["cliente"].get("/registro-imoveis/protocolo").get_data(
        as_text=True)
    assert "RECUSADO" in html
    assert "título recusado" in html
    _post(serventia, motivo="RECUSA")
    filtrada = serventia["cliente"].get(
        "/registro-imoveis/protocolo?situacao=RECUSADO").get_data(as_text=True)
    assert str(NUMERO) in filtrada
    aberta = serventia["cliente"].get(
        "/registro-imoveis/protocolo?situacao=ABERTO").get_data(as_text=True)
    assert str(NUMERO) not in aberta


def test_o_painel_preseleciona_o_decurso_e_posta_na_ficha(serventia):
    con = sqlite3.connect(serventia["banco"])
    con.execute("UPDATE ri_protocolos SET data_limite='2020-01-06' WHERE id=?",
                (serventia["pid"],))
    con.commit()
    con.close()
    html = serventia["cliente"].get("/registro-imoveis/pedidos").get_data(
        as_text=True)
    assert f'action="/registro-imoveis/protocolo/{serventia["pid"]}"' in html
    assert re.search(r'value="DECURSO_PRAZO"[^>]*selected', html)
    assert 'name="confirmar"' in html
