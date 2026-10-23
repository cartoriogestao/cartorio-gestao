"""O RASTRO DO ENVIO À CRC — relato do oficial em 11/09/2026: "os assentos
não ficaram lá nas cargas [e] já foram enviados", sem opção de dizer isso ao
sistema.

O QUE ESTES TESTES GUARDAM
    - `pendentes_de_carga` some, por padrão, quem já tem lote registrado, e
      `incluir_ja_enviados=True` traz de volta;
    - `registrar_envio` grava o lote e os assentos dele, e recusa lote
      vazio;
    - `historico_de_envios` e `assentos_do_lote` respondem "o que foi
      enviado, quando, e o que a Central disse";
    - a rota `/rcpn/crc/enviar` só marca como enviados os assentos que
      **entraram de verdade** no XML — nunca os retidos;
    - a rota `/rcpn/crc/marcar-enviado` é o "Confirmei no livro de papel"
      do modelo por upload.
"""
from __future__ import annotations

import glob
import re
import sqlite3
import sys
from pathlib import Path

import pytest
from werkzeug.datastructures import MultiDict

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import crc_carga as CRC                                          # noqa: E402
import crc_envios as CRCENVIOS                                   # noqa: E402

SENHA = "Senha#12345"
AGORA = "2026-09-11T09:00"
M32 = "00000001552026100002269100086802"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa):
    """App/DB compartilhados do modulo (conftest); setup de dominio por teste."""
    db = cg_casa["db"]
    c = cg_casa["cliente"]
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    db.set_settings({"serventia_cns": "000000"})
    c.post("/login",
           data={"username": "mario", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return cg_casa

def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _liso(t: str) -> str:
    return " ".join((t or "").split())


def _assento(con, nome="MARIA ÍSIS", *, numero=1, matricula=M32):
    with con:
        cur = con.execute(
            """INSERT INTO rc_assentos (serie, especie, numero, nome, data_ato,
                   data_fato, situacao, origem, criado_em, matricula)
               VALUES ('RC_A','NASCIMENTO',?,?,?,?,'ATIVO','SISTEMA',?,?)""",
            (numero, nome, "2026-08-20", "2026-08-18", AGORA, matricula))
        aid = int(cur.lastrowid)
        con.execute(
            """INSERT INTO rc_pessoas (assento_id, papel, nome, nome_norm,
                   sexo, criado_em) VALUES (?,?,?,?,?,?)""",
            (aid, "REGISTRADO", nome, nome.lower(), "F", AGORA))
    return aid


def _token_html(casa):
    return casa["cliente"].get("/rcpn/crc").get_data(as_text=True)


def _campos(html, ids, **extra):
    campos = MultiDict([("csrf_token", _token(html))])
    for k, v in extra.items():
        campos.add(k, v)
    for i in ids:
        campos.add("assento", str(i))
    return campos


# ------------------------------------------------ o módulo


def test_pendentes_some_quem_ja_tem_lote(casa):
    con = _con(casa)
    aid = _assento(con)
    assert CRC.pendentes_de_carga(con) == [
        dict(r) for r in con.execute(
            "SELECT id, especie, numero, nome, data_ato, matricula "
            "FROM rc_assentos WHERE id=?", (aid,))]

    CRCENVIOS.registrar_envio(con, [aid], agora=AGORA, por="mario",
                              canal="MANUAL")
    con.commit()

    assert CRC.pendentes_de_carga(con) == []
    trazido = CRC.pendentes_de_carga(con, incluir_ja_enviados=True)
    assert len(trazido) == 1 and trazido[0]["id"] == aid


def test_registrar_envio_recusa_lote_vazio(casa):
    con = _con(casa)
    with pytest.raises(CRC.CrcError, match="Nenhum assento"):
        CRCENVIOS.registrar_envio(con, [], agora=AGORA, por="mario",
                                  canal="MANUAL")


def test_historico_e_assentos_do_lote(casa):
    con = _con(casa)
    a1 = _assento(con, "MARIA ÍSIS", numero=1)
    a2 = _assento(con, "JOÃO PEDRO", numero=2)
    lote_id = CRCENVIOS.registrar_envio(
        con, [a1, a2], agora=AGORA, por="mario", canal="WEBSERVICE",
        ambiente="HOMOLOGACAO", resposta="<return>OK</return>")
    con.commit()

    lotes = CRCENVIOS.historico_de_envios(con)
    assert len(lotes) == 1
    assert lotes[0]["id"] == lote_id
    assert lotes[0]["canal"] == "WEBSERVICE"
    assert lotes[0]["quantos"] == 2
    assert lotes[0]["resposta"] == "<return>OK</return>"

    assentos = CRCENVIOS.assentos_do_lote(con, lote_id)
    nomes = {a["nome"] for a in assentos}
    assert nomes == {"MARIA ÍSIS", "JOÃO PEDRO"}


def test_assento_sem_data_do_ato_vem_primeiro_como_no_sqlite(casa):
    """No SQLite o NULL vinha primeiro no `ORDER BY data_ato`; no PostgreSQL
    vai por último, e com o `LIMIT` o assento sem data sairia da lista da
    carga. `NULLS FIRST` guarda a ordem de antes (revisão do L004)."""
    con = _con(casa)
    com_data = _assento(con, "MARIA ÍSIS", numero=1)
    sem_data = _assento(con, "JOÃO PEDRO", numero=2)
    with con:
        con.execute("UPDATE rc_assentos SET data_ato = NULL WHERE id = ?",
                    (sem_data,))
    assert [a["id"] for a in CRC.pendentes_de_carga(con)] == [sem_data, com_data]
    assert [a["id"] for a in CRC.pendentes_de_carga(con, limite=1)] == [sem_data]

    lote_id = CRCENVIOS.registrar_envio(con, [com_data, sem_data], agora=AGORA,
                                        por="mario", canal="MANUAL")
    con.commit()
    assert [a["id"] for a in CRCENVIOS.assentos_do_lote(con, lote_id)] == [
        sem_data, com_data]
    assert [a["id"] for a in CRC.pendentes_de_carga(
        con, incluir_ja_enviados=True)] == [sem_data, com_data]


def test_a_carga_nao_ganhou_a_escrita_que_o_varredor_proibe():
    """`crc_carga.py` continua só medindo e avisando — quem escreve o lote
    é `crc_envios.py`, e não ele."""
    fonte = (RAIZ / "crc_carga.py").read_text(encoding="utf-8")
    corpo = "\n".join(
        linha for linha in fonte.splitlines()
        if not linha.lstrip().startswith("#"))
    for proibido in ("UPDATE ", "INSERT ", "DELETE "):
        assert proibido not in corpo.upper()


# ------------------------------------------------ a tela: marcar como enviado


def test_marcar_como_enviado_tira_da_lista(casa):
    con = _con(casa)
    aid = _assento(con)
    html = _token_html(casa)
    r = casa["cliente"].post(
        "/rcpn/crc/marcar-enviado",
        data=_campos(html, [aid], nota="site da CRC, hoje de manhã"),
        follow_redirects=True)
    assert r.status_code == 200
    assert "marcado(s) como já enviados" in _liso(r.get_data(as_text=True))

    con2 = _con(casa)
    assert CRC.pendentes_de_carga(con2) == []
    lotes = CRCENVIOS.historico_de_envios(con2)
    assert len(lotes) == 1
    assert lotes[0]["canal"] == "MANUAL"
    assert lotes[0]["nota"] == "site da CRC, hoje de manhã"


def test_marcar_como_enviado_sem_escolher_nada_avisa(casa):
    html = _token_html(casa)
    r = casa["cliente"].post(
        "/rcpn/crc/marcar-enviado", data={"csrf_token": _token(html)},
        follow_redirects=True)
    assert "Escolha ao menos um assento" in _liso(r.get_data(as_text=True))


def test_o_botao_de_marcar_ja_aparece_na_lista_sem_montar_nada(casa):
    """**O oficial não achou o botão na 3.6.88** — ele só existia depois de
    clicar em "Montar o arquivo", igual ao de "Baixar o XML". Quem já subiu
    o arquivo numa ocasião anterior não tem por que montar de novo só para
    confirmar o envio. O botão agora está na própria lista de assentos, com
    `formaction` apontando para a rota de marcar — mesmas caixinhas, sem
    passar por "Montar o arquivo"."""
    con = _con(casa)
    _assento(con)
    html = _abrir_lista(casa)
    assert "Já enviei estes, no site da CRC" in html
    assert 'formaction="/rcpn/crc/marcar-enviado"' in html


def _abrir_lista(casa):
    return _liso(casa["cliente"].get("/rcpn/crc").get_data(as_text=True))


def test_a_lista_avisa_quantos_ja_foram_enviados(casa):
    con = _con(casa)
    aid = _assento(con)
    CRCENVIOS.registrar_envio(con, [aid], agora=AGORA, por="mario",
                              canal="MANUAL")
    con.commit()

    html = _liso(casa["cliente"].get("/rcpn/crc").get_data(as_text=True))
    assert "1" in html and "já enviado" in html
    assert "ver os já enviados" in html


def test_ver_enviados_traz_de_volta(casa):
    con = _con(casa)
    aid = _assento(con)
    CRCENVIOS.registrar_envio(con, [aid], agora=AGORA, por="mario",
                              canal="MANUAL")
    con.commit()

    escondido = casa["cliente"].get("/rcpn/crc").get_data(as_text=True)
    assert "MARIA ÍSIS" not in escondido

    trazido = casa["cliente"].get(
        "/rcpn/crc?ver_enviados=1").get_data(as_text=True)
    assert "MARIA ÍSIS" in trazido


# ------------------------------------------------ o histórico


def test_a_tela_de_historico_mostra_o_lote(casa):
    con = _con(casa)
    aid = _assento(con)
    CRCENVIOS.registrar_envio(
        con, [aid], agora=AGORA, por="mario", canal="WEBSERVICE",
        ambiente="HOMOLOGACAO", resposta="<return>OK-999</return>")
    con.commit()

    html = _liso(casa["cliente"].get(
        "/rcpn/crc/historico").get_data(as_text=True))
    assert "WEBSERVICE" in html
    assert "MARIA ÍSIS" in html
    assert "OK-999" in html


def test_a_tela_de_historico_sem_lote_nenhum(casa):
    html = _liso(casa["cliente"].get(
        "/rcpn/crc/historico").get_data(as_text=True))
    assert "Nenhum envio registrado" in html


# ------------------------------------------------ o envio pelo web service


def test_enviar_so_marca_como_enviado_quem_entrou_de_verdade(casa, monkeypatch):
    """O retido não subiu — marcá-lo como enviado esconderia da lista um
    assento que a Central nunca recebeu."""
    import atribuicoes_web

    con = _con(casa)
    bom = _assento(con, "MARIA ÍSIS", numero=1)
    ruim = _assento(con, "SEM MATRÍCULA", numero=2, matricula=None)

    def _driver_ok(nome):
        return "C:/fake.dll"
    monkeypatch.setattr(atribuicoes_web.CRCA3, "driver_disponivel", _driver_ok)

    def _enviar_carga(con, assentos, *, cns, driver, pin, ambiente):
        return {"enviado": 1,
                "retidos": [{"assento_id": ruim, "nome": "SEM MATRÍCULA",
                             "faltas": ["sem matrícula"]}],
                "a_arrumar": [], "resposta": "<return>OK-1</return>"}
    monkeypatch.setattr(atribuicoes_web.CRCSOAP, "enviar_carga", _enviar_carga)

    html = _token_html(casa)
    # O DRIVER É UM DOS DA LISTA DA TELA (LS02, 19/10/2026): a rota passou a
    # recusar o que não está em `DRIVERS_CONHECIDOS` — o nome vira
    # `WinDLL(driver)` no assinador, como SYSTEM. Este teste mede quem sai da
    # pendência, e não o driver; o `fake.dll` era só enchimento.
    r = casa["cliente"].post(
        "/rcpn/crc/enviar",
        data=_campos(html, [bom, ruim],
                     driver=atribuicoes_web.CRCA3.DRIVERS_CONHECIDOS[0],
                     pin="000000",
                    ambiente="HOMOLOGACAO"),
        follow_redirects=True)
    assert r.status_code == 200

    con2 = _con(casa)
    pendentes = {a["id"] for a in CRC.pendentes_de_carga(con2)}
    assert bom not in pendentes, "o que entrou no XML tem de sair da pendência"
    assert ruim in pendentes, "o retido não entrou, e continua pendente"

    lotes = CRCENVIOS.historico_de_envios(con2)
    assert len(lotes) == 1
    assert lotes[0]["canal"] == "WEBSERVICE"
    assentos_do_lote = {a["id"] for a in CRCENVIOS.assentos_do_lote(con2, lotes[0]["id"])}
    assert assentos_do_lote == {bom}
