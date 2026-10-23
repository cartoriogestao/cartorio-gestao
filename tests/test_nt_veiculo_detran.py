"""A comunicação de venda de veículo ao DETRAN — `nt_veiculo_detran.py` (LG04, item 3).

O QUE ESTES TESTES PROTEGEM

    o que o DETRAN recusaria   placa, RENAVAM (dígito verificador), CPF/CNPJ
                               das partes e data — recusados no balcão
    a firma do veículo         a comunicação não se liga a reconhecimento por
                               semelhança (CN-MA art. 865, II)
    desligada por padrão       sem ligar, nada vai ao DETRAN: o protocolo do
                               portal se registra à mão
    o selo antes               sem selo (13.22) não se comunica, à mão nem
                               pela rede
    homologação                ligada, o padrão é homologação, e o caminho
                               inteiro passa pelo transporte FALSO (sem rede)
    o segredo                  a credencial mora fora do banco e nunca aparece
                               em `audit_logs`, na mensagem de erro nem no HTML
    a guarda                   anônimo, papel errado e CSRF

Dados fictícios. Nenhum teste fala com o DETRAN nem com o selador.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import nt_veiculo_detran as V
from bd_nativo import banco
from caixa_schema import reais
from conftest import cg_login

SENHA = "Senha#12345"
SEGREDO = "senha-de-teste-NAO-VAZA-9k2"
REAIS = json.loads((RAIZ / "tests" / "custas_reais.json").read_text("utf-8"))
# CPFs e CNPJ de teste (dígitos válidos, nenhum de pessoa).
CPF_VENDEDOR = "00000000191"
CPF_COMPRADOR = "11144477735"
RENAVAM = "00639884962"


def _token(html: str) -> str:
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


def _semear_13_22(db) -> None:
    e = next(x for x in REAIS["valores_2026"] if x["tj"] == V.ITEM)
    with db.transaction() as con:
        bd = banco(con)
        bd.escrever(
            """INSERT INTO cx_vigencias(codigo, descricao, vigente, inicio, fim,
                                        importado_em)
               VALUES (10022, 'Período de 2026', 1, '2026-01-01', '2026-12-31',
                       '2026-08-21') ON CONFLICT DO NOTHING""")
        bd.escrever("""INSERT INTO cx_servicos(codigo, codigo_tj, descricao, ativo)
                       VALUES (%s,%s,%s,1) ON CONFLICT DO NOTHING""",
                    (int(e["s"]), e["tj"], e["descricao"]))
        total = sum(int(round(e[k] * 100))
                    for k in ("emol", "ferc", "femp", "fadp", "ferrfis"))
        bd.escrever(
            """INSERT INTO cx_servico_valores(servico, vigencia, emolumentos,
                   ferc, femp, fadep, ferrfis, total)
               VALUES (%s,10022,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
            (int(e["s"]), reais(int(round(e["emol"] * 100))),
             reais(int(round(e["ferc"] * 100))), reais(int(round(e["femp"] * 100))),
             reais(int(round(e["fadp"] * 100))),
             reais(int(round(e["ferrfis"] * 100))), reais(total)))


@pytest.fixture()
def selador_falso(monkeypatch):
    import selador
    import selador_cliente as CL
    pedidos = []

    def selar(con, pasta, caminho, dados, *, referencia, atribuicao, agora,
              cns, tentativa=1, usuario=None, prazo=None):
        pedidos.append({"caminho": caminho, "dados": dados,
                        "referencia": str(referencia)})
        bd = banco(con)
        ja = bd.um("SELECT numero FROM sd_selos WHERE referencia = %s "
                   "ORDER BY id LIMIT 1", (str(referencia),))
        numero = ja["numero"] if ja else f"COMVEI{len(pedidos):010d}"
        if not ja:
            bd.escrever(
                """INSERT INTO sd_selos(numero, texto, sid, caminho, atribuicao,
                       referencia, ambiente, obtido_em, obtido_por)
                   VALUES (%s,%s,%s,%s,%s,%s,'HOMOLOGACAO',%s,%s)""",
                (numero, "selo de teste", f"sid:{referencia}", caminho,
                 atribuicao, str(referencia), agora, usuario))
        return [selador.SeloGerado(numero=numero, texto="selo de teste")]

    monkeypatch.setattr(CL, "selar", selar)
    return pedidos


@pytest.fixture()
def falso(monkeypatch):
    """O DETRAN de mentira no lugar do de fábrica (que recusa)."""
    t = V.TransporteFalso()
    monkeypatch.setattr(V, "TRANSPORTE", t)
    return t


@pytest.fixture()
def casa(cg_casa, tmp_path, monkeypatch):
    # A credencial vai para a pasta de dados do Windows; no teste, para tmp.
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path / "programdata"))
    db = cg_casa["db"]
    db.create_user("oficial", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    db.create_user("balcao", "BALCAO EXEMPLO", SENHA, "USER")
    db.create_user("gerente", "GERENTE EXEMPLO", SENHA, "MANAGER")
    db.set_settings({"selo_tabela_custas_em": "20260101", "ri_cns": "000000"})
    _semear_13_22(db)
    return cg_casa


@pytest.fixture()
def protocolo_pago(casa):
    """O balcão já recebeu: protocolo pago com o 13.22, atendido pelo oficial.

    Desde o LX16 o selo PAGO só sai com protocolo e pagamento
    (`ato_selado.cobrir_o_selo`). Estes testes falam da comunicação ao
    DETRAN, e não do caixa: montam o que o balcão monta, pelo helper único
    `protocolo_de_teste`, em vez de desligar a trava.
    """
    from protocolo_de_teste import atender_protocolo_pago
    with casa["db"].transaction() as con:
        return atender_protocolo_pago(con, usuario="MARIO EXEMPLO DOS SANTOS",
                                      codigos=(V.ITEM,))


def _logar(casa, quem="oficial"):
    c = casa["app"].test_client()
    cg_login(c, quem, SENHA)
    return c


def _registrar(c, **campos):
    token = _token(c.get("/notas/veiculos").get_data(as_text=True))
    dados = {"documento": "ATPV_E", "placa": "abc-1d23", "renavam": RENAVAM,
             "vendedor_nome": "FULANO DE TAL EXEMPLO",
             "vendedor_documento": CPF_VENDEDOR,
             "comprador_nome": "BELTRANO DE EXEMPLO",
             "comprador_documento": CPF_COMPRADOR,
             "data_venda": "2026-10-10", "valor": "25.000,00",
             "municipio": "Cidade Exemplo", "uf": "ma", "csrf_token": token}
    dados.update(campos)
    return c.post("/notas/veiculos/nova", data=dados, follow_redirects=True)


def _linhas(db, sql, parametros=None):
    with db.connect() as con:
        return banco(con).ler(sql, parametros)


def _ultima(db):
    return _linhas(db, "SELECT * FROM nt_comunicacoes_veiculo "
                       "ORDER BY id DESC LIMIT 1")[0]


def _comunicar(c, cid, **campos):
    token = _token(c.get(f"/notas/veiculos/{cid}").get_data(as_text=True))
    return c.post(f"/notas/veiculos/{cid}/comunicar",
                  data={"csrf_token": token, **campos}, follow_redirects=True)


def _ligar(c, ambiente="HOMOLOGACAO"):
    token = _token(c.get("/notas/veiculos/configuracao").get_data(as_text=True))
    c.post("/notas/veiculos/configuracao",
           data={"acao": "integracao", "ligada": "1", "ambiente": ambiente,
                 "csrf_token": token})


def _credencial(c, ambiente="HOMOLOGACAO"):
    token = _token(c.get("/notas/veiculos/configuracao").get_data(as_text=True))
    return c.post("/notas/veiculos/configuracao",
                  data={"acao": "credencial", "ambiente": ambiente,
                        "usuario": "usuario.teste", "senha": SEGREDO,
                        "csrf_token": token}, follow_redirects=True)


# ----------------------------------------------------------- conferir

def test_o_digito_do_renavam_confere_e_o_trocado_nao():
    assert V.renavam_valido(RENAVAM)
    assert V.renavam_valido("639884962")          # o antigo, de nove
    assert not V.renavam_valido("00639884963")
    assert not V.renavam_valido("11111111111")
    assert not V.renavam_valido("123")


def test_a_placa_antiga_e_a_do_mercosul_valem():
    assert V.PLACA.match(V.placa_normal("abc-1234"))
    assert V.PLACA.match(V.placa_normal("ABC1D23"))
    assert not V.PLACA.match(V.placa_normal("AB12345"))


def test_o_registro_guarda_so_digitos_e_a_placa_normal(casa):
    c = _logar(casa)
    _registrar(c)
    com = _ultima(casa["db"])
    assert com["placa"] == "ABC1D23" and com["renavam"] == RENAVAM
    assert com["vendedor_documento"] == CPF_VENDEDOR
    assert com["valor_centavos"] == 2500000 and com["uf"] == "MA"
    assert com["situacao"] == "REGISTRADA" and com["selo"] is None


@pytest.mark.parametrize("campo,valor,frase", [
    ("renavam", "00639884963", "RENAVAM inválido"),
    ("placa", "XYZ", "Placa inválida"),
    ("comprador_documento", "12345678900", "comprador"),
    ("comprador_documento", CPF_VENDEDOR, "mesmo documento"),
    ("data_venda", "2999-01-01", "futura"),
    ("documento", "DUT", "Escolha o documento"),
])
def test_o_que_o_detran_recusaria_e_recusado_no_balcao(casa, campo, valor, frase):
    html = _registrar(_logar(casa), **{campo: valor}).get_data(as_text=True)
    assert frase in html
    assert _linhas(casa["db"],
                   "SELECT id FROM nt_comunicacoes_veiculo ORDER BY id") == []


def _reconhecimento(db, *, especie, servico=414) -> int:
    with db.transaction() as con:
        bd = banco(con)
        rid = bd.escrever(
            """INSERT INTO nt_reconhecimentos(data, especie, servico_codigo,
                   veiculo_placa, criado_em)
               VALUES (%s,%s,%s,'ABC1D23',%s) RETURNING id""",
            (date.today().isoformat(), especie, servico,
             "2026-10-19T10:00"))[0]["id"]
        bd.escrever(
            """INSERT INTO nt_reconhecimento_partes(reconhecimento_id, nome,
                   documento, criado_em)
               VALUES (%s,'FULANO DE TAL EXEMPLO',%s,'2026-10-19T10:00')""",
            (rid, CPF_VENDEDOR))
    return int(rid)


def test_a_comunicacao_nao_se_liga_a_firma_por_semelhanca(casa):
    rid = _reconhecimento(casa["db"], especie="SEMELHANCA")
    html = _registrar(_logar(casa), reconhecimento_id=str(rid)).get_data(
        as_text=True)
    assert "AUTENTICIDADE" in html
    assert _linhas(casa["db"],
                   "SELECT id FROM nt_comunicacoes_veiculo ORDER BY id") == []


def test_a_firma_por_autenticidade_preenche_e_amarra_a_comunicacao(casa):
    rid = _reconhecimento(casa["db"], especie="AUTENTICIDADE")
    c = _logar(casa)
    html = c.get(f"/notas/veiculos?reconhecimento_id={rid}").get_data(as_text=True)
    assert "ABC1D23" in html and "FULANO DE TAL EXEMPLO" in html
    _registrar(c, reconhecimento_id=str(rid))
    assert _ultima(casa["db"])["reconhecimento_id"] == rid


def test_firma_que_nao_e_de_veiculo_nao_vira_comunicacao(casa):
    rid = _reconhecimento(casa["db"], especie="AUTENTICIDADE", servico=413)
    html = _registrar(_logar(casa), reconhecimento_id=str(rid)).get_data(
        as_text=True)
    assert "13.17.3" in html


# -------------------------------------------- desligada, o padrão

def test_a_integracao_nasce_desligada_e_em_homologacao(casa):
    assert V.ligada(casa["db"].get_setting) is False
    assert V.ambiente(casa["db"].get_setting) == V.HOMOLOGACAO


def test_desligada_o_envio_e_recusado_sem_tocar_no_transporte(casa, falso):
    with pytest.raises(V.DetranError, match="desligada"):
        V.enviar(casa["db"], 1, get_setting=casa["db"].get_setting)
    assert falso.recebidas == []


def test_desligada_sela_e_registra_o_protocolo_do_portal(casa, protocolo_pago,
                                                         selador_falso, falso):
    c = _logar(casa)
    _registrar(c)
    cid = _ultima(casa["db"])["id"]
    html = _comunicar(c, cid, protocolo="PORTAL-2026-0001").get_data(as_text=True)
    assert "protocolo do portal" in html
    com = _ultima(casa["db"])
    assert com["situacao"] == "COMUNICADA_A_MAO"
    assert com["protocolo_detran"] == "PORTAL-2026-0001"
    assert com["selo"] == "COMVEI0000000001"
    assert falso.recebidas == []
    pedido = selador_falso[0]
    assert pedido["caminho"] == V.CAMINHO_DO_SELO
    assert pedido["dados"]["ato"] == {"codigo": "13.22",
                                      "codigoTabelaCusta": "0520260101"}
    assert [p["documento"] for p in pedido["dados"]["partes"]["parteAto"]] == [
        CPF_VENDEDOR, CPF_COMPRADOR]
    acoes = [x["action"] for x in _linhas(
        casa["db"], "SELECT action FROM audit_logs ORDER BY id")]
    assert "NT_COMUNICACAO_VEICULO_SELADA" in acoes
    assert "NT_COMUNICACAO_VEICULO_A_MAO" in acoes


def test_sem_selo_a_venda_nao_se_comunica(casa, protocolo_pago):
    """Sem o falso, o selador do teste não existe: nada se comunica.

    Com o protocolo pago, para a falha ser a do APARELHO — sem ele, quem
    barrava era a trava do selo pago, e o teste passava pelo motivo errado.
    """
    c = _logar(casa)
    _registrar(c)
    cid = _ultima(casa["db"])["id"]
    html = _comunicar(c, cid, protocolo="PORTAL-2026-0001").get_data(as_text=True)
    assert "NÃO foi comunicada" in html
    com = _ultima(casa["db"])
    assert com["situacao"] == "REGISTRADA" and com["protocolo_detran"] is None
    assert com["ultimo_erro"].startswith("selo:")
    assert "aguardando cobertura" not in com["ultimo_erro"]


def test_o_protocolo_a_mao_exige_selo_antes_tambem_no_dominio(casa):
    c = _logar(casa)
    _registrar(c)
    cid = _ultima(casa["db"])["id"]
    with casa["db"].transaction() as con, pytest.raises(V.DetranError,
                                                         match="selo"):
        V.registrar_protocolo_a_mao(con, cid, protocolo="PORTAL-1",
                                    agora="2026-10-19T10:00", usuario="X")


# ------------------------------------------------ ligada, em homologação

def test_ligada_sem_credencial_diz_o_que_falta(casa, protocolo_pago,
                                               selador_falso, falso):
    c = _logar(casa)
    _ligar(c)
    _registrar(c)
    cid = _ultima(casa["db"])["id"]
    html = _comunicar(c, cid).get_data(as_text=True)
    assert "Falta a credencial do DETRAN" in html
    assert falso.recebidas == []


def test_ligada_em_homologacao_o_falso_recebe_e_o_protocolo_se_grava(
        casa, protocolo_pago, selador_falso, falso):
    c = _logar(casa)
    _ligar(c)
    _credencial(c)
    _registrar(c)
    cid = _ultima(casa["db"])["id"]
    html = _comunicar(c, cid).get_data(as_text=True)
    assert "HML-000001" in html
    com = _ultima(casa["db"])
    assert (com["situacao"], com["protocolo_detran"], com["ambiente"]) == (
        "CONFIRMADA", "HML-000001", "HOMOLOGACAO")
    corpo, credencial, ambiente = falso.recebidas[0]
    assert ambiente == "HOMOLOGACAO" and credencial["senha"] == SEGREDO
    assert corpo["renavam"] == RENAVAM and corpo["placa"] == "ABC1D23"


def test_a_recusa_do_detran_conta_a_tentativa_e_permite_reenviar(
        casa, protocolo_pago, selador_falso, monkeypatch):
    t = V.TransporteFalso(recusar=f"usuário inválido ({SEGREDO})")
    monkeypatch.setattr(V, "TRANSPORTE", t)
    c = _logar(casa)
    _ligar(c)
    _credencial(c)
    _registrar(c)
    cid = _ultima(casa["db"])["id"]
    _comunicar(c, cid)
    com = _ultima(casa["db"])
    assert com["situacao"] == "RECUSADA" and com["tentativas"] == 1
    t.recusar = None
    _comunicar(c, cid)
    com = _ultima(casa["db"])
    assert com["situacao"] == "CONFIRMADA" and com["tentativas"] == 2
    # o selo é um só: a segunda ida não comprou outro
    assert len(selador_falso) == 1


def test_a_senha_nao_aparece_no_rastro_no_erro_nem_na_tela(
        casa, protocolo_pago, selador_falso, monkeypatch):
    monkeypatch.setattr(V, "TRANSPORTE", V.TransporteFalso(
        recusar=f"login falhou para a senha {SEGREDO}"))
    c = _logar(casa)
    _ligar(c)
    telas = [_credencial(c).get_data(as_text=True)]
    _registrar(c)
    cid = _ultima(casa["db"])["id"]
    telas.append(_comunicar(c, cid).get_data(as_text=True))
    telas.append(c.get(f"/notas/veiculos/{cid}").get_data(as_text=True))
    telas.append(c.get("/notas/veiculos/configuracao").get_data(as_text=True))
    assert all(SEGREDO not in t for t in telas)
    assert SEGREDO not in (_ultima(casa["db"])["ultimo_erro"] or "")
    rastro = _linhas(casa["db"], "SELECT details FROM audit_logs ORDER BY id")
    assert rastro and all(SEGREDO not in (r["details"] or "") for r in rastro)
    # e ela mora fora do banco, no arquivo da pasta de dados
    arquivo = Path(casa_programdata()) / "CartorioGestao" / V.ARQUIVO_DA_CREDENCIAL
    assert SEGREDO in arquivo.read_text(encoding="utf-8")


def casa_programdata() -> str:
    import os
    return os.environ["PROGRAMDATA"]


def test_o_transporte_de_fabrica_recusa_sem_leiaute(casa, protocolo_pago,
                                                    selador_falso):
    """Sem o falso, ligada e com credencial, a recusa diz que falta o leiaute
    — e não finge que comunicou."""
    c = _logar(casa)
    _ligar(c)
    _credencial(c)
    _registrar(c)
    cid = _ultima(casa["db"])["id"]
    html = _comunicar(c, cid).get_data(as_text=True)
    assert "leiaute do DETRAN não está configurado" in html
    assert _ultima(casa["db"])["situacao"] == "REGISTRADA"


def test_no_sandbox_a_producao_e_recusada(casa, protocolo_pago, selador_falso,
                                          falso, monkeypatch):
    monkeypatch.setenv("CARTORIO_GESTAO_SANDBOX", "1")
    c = _logar(casa)
    _ligar(c, ambiente="PRODUCAO")
    _credencial(c, ambiente="PRODUCAO")
    _registrar(c)
    cid = _ultima(casa["db"])["id"]
    html = _comunicar(c, cid).get_data(as_text=True)
    assert "sandbox" in html
    assert falso.recebidas == []


def test_o_preco_e_o_do_item_13_22_da_tabela_de_2026(casa):
    with casa["db"].connect() as con:
        valor = V.preco(con, data="2026-10-19")
    e = next(x for x in REAIS["valores_2026"] if x["tj"] == "13.22")
    assert valor["total_centavos"] == sum(
        int(round(e[k] * 100)) for k in ("emol", "ferc", "femp", "fadp", "ferrfis"))


# ------------------------------------------------------------- a guarda

def test_anonimo_vai_ao_login(casa):
    c = casa["app"].test_client()
    assert c.get("/notas/veiculos").status_code == 302
    assert c.get("/notas/veiculos/configuracao").status_code == 302


def test_so_o_administrador_configura_a_integracao(casa):
    for quem in ("balcao", "gerente"):
        c = _logar(casa, quem)
        assert c.get("/notas/veiculos/configuracao").status_code == 403, quem
    assert _logar(casa).get("/notas/veiculos/configuracao").status_code == 200


def test_post_sem_csrf_e_recusado(casa):
    c = _logar(casa)
    assert c.post("/notas/veiculos/nova", data={"placa": "ABC1234"}).status_code == 400
    assert c.post("/notas/veiculos/configuracao",
                  data={"acao": "integracao", "ligada": "1",
                        "ambiente": "HOMOLOGACAO"}).status_code == 400
    assert V.ligada(casa["db"].get_setting) is False


def test_ligar_e_desligar_deixa_rastro(casa):
    c = _logar(casa)
    _ligar(c)
    assert V.ligada(casa["db"].get_setting) is True
    rastro = _linhas(casa["db"], "SELECT details FROM audit_logs WHERE action = %s "
                                 "ORDER BY id", ("NT_DETRAN_CONFIGURADO",))
    assert rastro and '"ligada": true' in rastro[-1]["details"]
