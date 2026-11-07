"""O cálculo que vira serviço: o mesmo número, os mesmos itens, o mesmo dinheiro.

Pedido do oficial, 01/11/2026. Medido na produção: 56 protocolos abertos como «só cálculo» foram quitados,
com 109 itens no caixa, porque as duas opções pareciam a mesma. Ele explicou a causa e respondeu que sim ao
botão, que também serve para corrigir esses.

O QUE ELES DEFENDEM
    O dinheiro e o número não mudam. Nada sai para o cliente. O rastro diz quem, quando e por quê. E o papel de
    recepção afirma o dia em que o serviço entrou, e não o dia em que o cálculo foi aberto.
"""
from __future__ import annotations

import io
import itertools
import re
import zipfile

import pytest

import acompanhamento_cliente as ACOMP
import caixa_protocolo as CXP
import navegacao as NAV
from bd_nativo import banco

SENHA = "Senha#12345"
HOJE = "2026-11-01"
AGORA = f"{HOJE}T10:00:00"
_NUMEROS = itertools.count(10000)


def _token(html: str) -> str:
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


@pytest.fixture()
def casa(cg_casa):
    db = cg_casa["db"]
    c = cg_casa["cliente"]
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c.post("/login", data={"username": "mario", "password": SENHA,
                           "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return cg_casa


def _calculo(casa, *, abertura="2026-10-20", quitado=False, situacao="ABERTO", tipo="ORCAMENTO") -> int:
    with casa["db"].transaction() as con:
        bd = banco(con)
        pid = int(bd.escrever(
            """INSERT INTO cx_protocolos (numero, data_abertura, hora, atribuicao, interessado, assunto, tipo, situacao,
                   origem, criado_em)
               VALUES (%s, %s, '09:15', 'NOTAS', 'Ana Exemplo', 'Procuração', %s, %s, 'MANUAL', %s) RETURNING id""",
            (f"2026.10.{next(_NUMEROS)}", abertura, tipo, situacao, f"{abertura}T09:15:00"))[0]["id"])
        bd.escrever(
            """INSERT INTO cx_protocolo_atos (protocolo_id, codigo_ato, descricao, quantidade, quitado, origem)
               VALUES (%s, '13.1', 'um ato', 1, %s, 'MANUAL')""", (pid, 1 if quitado else 0))
    return pid


def _protocolo(casa, pid: int) -> dict:
    with casa["db"].connect() as con:
        return dict(banco(con).um("SELECT * FROM cx_protocolos WHERE id=%s", (pid,)))


def _virar(casa, pid: int, **campos) -> dict:
    with casa["db"].transaction() as con:
        return CXP.virar_servico(con, pid, quem="Mario Exemplo", agora=AGORA, **campos)


def _postar(casa, endereco: str, **campos):
    c = casa["cliente"]
    pagina = c.get("/caixa/protocolos").get_data(as_text=True)
    return c.post(endereco, data={"csrf_token": _token(pagina), **campos})


# ------------------------------------------------------------------- a regra

def test_o_cliente_que_volta_entra_hoje_e_o_rastro_fica(casa):
    pid = _calculo(casa)
    feito = _virar(casa, pid)
    p = _protocolo(casa, pid)
    assert p["tipo"] == "SERVICO" and feito["servico_desde"] == HOJE == p["servico_desde"]
    assert p["virou_servico_em"] == AGORA and p["virou_servico_por"] == "Mario Exemplo"
    # O que aconteceu antes não se regrava: o cálculo foi aberto naquele dia.
    assert p["data_abertura"] == "2026-10-20" and p["hora"] == "09:15"


def test_com_dinheiro_no_caixa_a_data_e_a_da_abertura_e_o_motivo_e_obrigatorio(casa):
    pid = _calculo(casa, quitado=True)
    with pytest.raises(CXP.ProtocoloError, match="dinheiro no caixa"):
        _virar(casa, pid, motivo="curto")
    assert _protocolo(casa, pid)["tipo"] == "ORCAMENTO", "a recusa não pode deixar o protocolo pela metade"
    feito = _virar(casa, pid, motivo="Aberto como cálculo por engano.")
    p = _protocolo(casa, pid)
    assert feito["itens_quitados"] == 1 and p["servico_desde"] == "2026-10-20"
    assert p["virou_servico_motivo"] == "Aberto como cálculo por engano."


def test_o_dinheiro_e_os_itens_nao_mudam(casa):
    pid = _calculo(casa, quitado=True)
    with casa["db"].connect() as con:
        antes = [dict(x) for x in banco(con).ler("SELECT * FROM cx_protocolo_atos WHERE protocolo_id=%s", (pid,))]
    situacao = _protocolo(casa, pid)["situacao"]
    numero = _protocolo(casa, pid)["numero"]
    _virar(casa, pid, motivo="Aberto como cálculo por engano.")
    with casa["db"].connect() as con:
        depois = [dict(x) for x in banco(con).ler("SELECT * FROM cx_protocolo_atos WHERE protocolo_id=%s", (pid,))]
    assert depois == antes
    assert _protocolo(casa, pid)["situacao"] == situacao and _protocolo(casa, pid)["numero"] == numero


def test_servico_nao_vira_de_novo(casa):
    pid = _calculo(casa)
    _virar(casa, pid, motivo="O cliente voltou.")
    primeiro = _protocolo(casa, pid)
    with pytest.raises(CXP.ProtocoloError, match="já é de serviço"):
        _virar(casa, pid, motivo="Segundo clique.")
    depois = _protocolo(casa, pid)
    assert depois["virou_servico_motivo"] == primeiro["virou_servico_motivo"], "o segundo clique reescreveu o rastro"


@pytest.mark.parametrize("situacao", ["ENTREGUE", "CANCELADO"])
def test_encerrado_se_reabre_antes(casa, situacao):
    pid = _calculo(casa, situacao=situacao)
    with pytest.raises(CXP.ProtocoloError, match="Reabra"):
        _virar(casa, pid)
    assert _protocolo(casa, pid)["tipo"] == "ORCAMENTO"


@pytest.mark.parametrize("dia", ["2026-10-19", "2026-11-02", "ontem"])
def test_o_servico_entra_entre_a_abertura_e_hoje(casa, dia):
    pid = _calculo(casa)
    with pytest.raises(CXP.ProtocoloError):
        _virar(casa, pid, servico_desde=dia)
    assert _protocolo(casa, pid)["tipo"] == "ORCAMENTO"


def test_a_lista_so_traz_calculo_quitado_e_vivo(casa):
    alvo = _calculo(casa, quitado=True)
    sem_dinheiro = _calculo(casa, abertura="2026-10-21")
    servico = _calculo(casa, abertura="2026-10-22", quitado=True, tipo="SERVICO")
    with casa["db"].connect() as con:
        ids = {x["id"] for x in CXP.calculos_quitados(con)}
    assert alvo in ids and sem_dinheiro not in ids and servico not in ids


def test_virar_nao_manda_nada_ao_cliente(casa):
    """O portal só publica quem tem código, e o código nasce na recepção: transformar 56 de uma vez não avisa ninguém."""
    pid = _calculo(casa, quitado=True)
    assert ACOMP.elegivel(_protocolo(casa, pid)) is False
    _virar(casa, pid, motivo="Aberto como cálculo por engano.")
    p = _protocolo(casa, pid)
    assert ACOMP.elegivel(p) is True
    assert p["acompanhamento_hash"] is None and p["portal_marca"] is None


# ------------------------------------------------------------------- as telas

def test_o_botao_leva_ao_servico_e_a_ficha_conta_o_que_houve(casa):
    pid = _calculo(casa)
    html = casa["cliente"].get(f"/caixa/protocolos/{pid}").get_data(as_text=True)
    assert "Transformar em serviço" in html and f'value="{casa["db"].now()[:10]}"' in html
    assert "Protocolo de recepção" not in html
    r = _postar(casa, f"/caixa/protocolos/{pid}/virar-servico", servico_desde=casa["db"].now()[:10], motivo="")
    assert r.status_code == 302
    html = casa["cliente"].get(f"/caixa/protocolos/{pid}").get_data(as_text=True)
    assert "Transformar em serviço" not in html and "só cálculo</span>" not in html
    assert "Protocolo de recepção" in html and "Aberto como só cálculo, e transformado em" in html
    # Quem lê o rastro é uma pessoa: o nome, e não o login.
    assert _protocolo(casa, pid)["virou_servico_por"] == "MARIO EXEMPLO DOS SANTOS"


def test_a_recusa_nao_vira_erro_de_tela(casa):
    pid = _calculo(casa, quitado=True)
    r = _postar(casa, f"/caixa/protocolos/{pid}/virar-servico", motivo="")
    assert r.status_code == 302
    assert _protocolo(casa, pid)["tipo"] == "ORCAMENTO"
    assert "dinheiro no caixa" in casa["cliente"].get(r.headers["Location"]).get_data(as_text=True)


def test_com_dinheiro_a_ficha_ja_sugere_a_data_da_abertura_e_pede_o_motivo(casa):
    pid = _calculo(casa, quitado=True)
    html = casa["cliente"].get(f"/caixa/protocolos/{pid}").get_data(as_text=True)
    assert 'name="servico_desde" value="2026-10-20"' in html
    assert re.search(r'name="motivo" required minlength="10"', html)


def test_encerrado_nao_oferece_o_botao(casa):
    pid = _calculo(casa, situacao="CANCELADO")
    html = casa["cliente"].get(f"/caixa/protocolos/{pid}").get_data(as_text=True)
    assert "reabra-o primeiro" in html and 'id="virar-servico"' not in html


def test_a_tela_de_corrigir_transforma_os_marcados_e_deixa_os_outros(casa):
    marcado, desmarcado = _calculo(casa, quitado=True), _calculo(casa, abertura="2026-10-23", quitado=True)
    aviso = casa["cliente"].get("/caixa/protocolos").get_data(as_text=True)
    assert "Ver e corrigir" in aviso and "item quitado" in aviso
    html = casa["cliente"].get("/caixa/protocolos/calculos-quitados").get_data(as_text=True)
    assert f'value="{marcado}" checked' in html and f'value="{desmarcado}" checked' in html
    r = _postar(casa, "/caixa/protocolos/calculos-quitados", protocolo_id=[marcado],
                motivo="Aberto como só cálculo por engano.")
    assert r.status_code == 302
    assert _protocolo(casa, marcado)["tipo"] == "SERVICO"
    assert _protocolo(casa, marcado)["servico_desde"] == "2026-10-20", "o serviço entrou quando o protocolo abriu"
    assert _protocolo(casa, desmarcado)["tipo"] == "ORCAMENTO"
    with casa["db"].connect() as con:
        linha = banco(con).um("SELECT count(*) AS n FROM audit_logs WHERE action=%s AND entity_id=%s",
                              ("PROTOCOLO_VIROU_SERVICO", str(marcado)))
    assert linha["n"] == 1, "cada protocolo fica com a própria linha na auditoria"


def test_a_tela_de_corrigir_e_do_oficial_e_do_gerente(casa):
    db = casa["db"]
    db.create_user("beatriz", "BEATRIZ EXEMPLO", SENHA, "USER")
    c = casa["app"].test_client() if "app" in casa else None
    if c is None:
        pytest.skip("o conftest não expõe o app")
    c.post("/login", data={"username": "beatriz", "password": SENHA,
                           "csrf_token": _token(c.get("/login").get_data(as_text=True))})
    r = c.get("/caixa/protocolos/calculos-quitados")
    assert r.status_code in (302, 403)
    assert "Ver e corrigir" not in c.get("/caixa/protocolos").get_data(as_text=True)


def test_a_tela_de_corrigir_tem_lugar_na_barra():
    # 07/11/2026 (#368): a seção «Protocolo geral» do Caixa passou a se chamar «Atendimentos».
    assert NAV.PAI["caixa_calculos_quitados"] == ("CAIXA", "Atendimentos")


# ------------------------------------------------------------------- o papel

def _recepcao(casa, pid: int) -> str:
    r = _postar(casa, f"/caixa/protocolos/{pid}/recepcao")
    assert r.status_code == 200, r.status_code
    with zipfile.ZipFile(io.BytesIO(r.get_data())) as odt:
        return re.sub(r"<[^>]+>", " ", odt.read("content.xml").decode("utf-8"))


def test_a_recepcao_afirma_o_dia_em_que_o_servico_entrou(casa):
    pid = _calculo(casa)
    _virar(casa, pid)
    texto = _recepcao(casa, pid)
    assert "01/11/2026" in texto
    assert "20/10/2026" not in texto and "09:15" not in texto, "a hora é a do cálculo: em outro dia, ela é invenção"


def test_a_recepcao_da_correcao_afirma_o_dia_da_abertura(casa):
    pid = _calculo(casa, quitado=True)
    _virar(casa, pid, motivo="Aberto como cálculo por engano.")
    texto = _recepcao(casa, pid)
    assert "20/10/2026" in texto and "09:15" in texto
