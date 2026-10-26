"""O painel do gestor no celular — os números, o papel PAINEL e a trava dele.

Pedido de 26/10/2026: «painel do gestor no celular, só com números agregados».
Os testes provam três coisas que não se veem lendo o código:

  * os números são os da régua da casa (selo usado, receita de entrada,
    protocolo atrasado, prenotação vencida e a vencer, fila do dia);
  * NADA que identifica pessoa chega à tela nem ao retrato — o teste semeia
    nome e CPF fictícios e procura os dois;
  * o papel PAINEL só alcança o painel: qualquer outra tela volta para ele, e
    POST nenhum grava.

Dados inventados: mario/beatriz/carla, CPF 000.000.050-70 (fictício declarado
no anti-vazamento).
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import painel_celular_web as PCW              # noqa: E402
import painel_numeros as PN                   # noqa: E402
import painel_retrato as PR                   # noqa: E402
from bd_nativo import banco                   # noqa: E402
from conftest import cg_login                 # noqa: E402

SENHA = "Senha#12345"
NOME_DO_CLIENTE = "BEATRIZ EXEMPLO DA SILVA"
CPF = "000.000.050-70"
HOJE = date.today()


def _semear(db) -> None:
    hoje = HOJE.isoformat()
    ontem_ou_hoje = HOJE.isoformat()
    vencida = (HOJE - timedelta(days=3)).isoformat()
    agora = db.now()
    with db.transaction() as con:
        bd = banco(con)
        # selos: dois usados hoje (RI e Notas), um cancelado hoje, um órfão
        for numero, atr, usado, cancelado in (
                ("SELOTESTE0000000000000000001", "IMOVEL", hoje + "T10:00:00", None),
                ("SELOTESTE0000000000000000002", "NOTAS", hoje + "T11:00:00", None),
                ("SELOTESTE0000000000000000003", "CIVIL", None, hoje + "T12:00:00"),
                ("SELOTESTE0000000000000000004", "PROTESTO", None, None)):
            bd.escrever(
                "INSERT INTO sd_selos(numero, atribuicao, obtido_em, obtido_por, "
                "usado_em, cancelado_em, referencia) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (numero, atr, hoje + "T09:00:00", "beatriz", usado, cancelado,
                 NOME_DO_CLIENTE))
        # caixa: uma entrada de ato, um troco, uma saída, um gratuito
        for natureza, sentido, valor, emol, desc in (
                ("RECEBIMENTO", "ENTRADA", "123,45", "100,00", f"Recebimento de {NOME_DO_CLIENTE}"),
                ("RECEBIMENTO", "ENTRADA", "50,00", "0", "SALDO INICIAL do dia"),
                ("SANGRIA", "SAIDA", "999,00", "0", "retirada"),
                ("RECEBIMENTO", "ENTRADA", "0", "30,00", "gratuito"),
        ):
            bd.escrever(
                "INSERT INTO cx_lancamentos(data, natureza, sentido, valor, "
                "emolumentos, descricao, pagador, pagador_documento, criado_em) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (ontem_ou_hoje, natureza, sentido, valor, emol, desc,
                 NOME_DO_CLIENTE, CPF, agora))
        # protocolos do balcão: um em dia, um atrasado, um encerrado
        for numero, previsao, situacao in (("2026.10.900", None, "ABERTO"),
                                           ("2026.10.901", vencida, "A_PAGAR"),
                                           ("2026.10.902", vencida, "ENTREGUE")):
            bd.escrever(
                "INSERT INTO cx_protocolos(numero, data_abertura, interessado, "
                "interessado_documento, previsao_entrega, situacao, finalizado, criado_em) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (numero, hoje, NOME_DO_CLIENTE, CPF, previsao, situacao,
                 1 if situacao == "ENTREGUE" else 0, agora))
        # prenotação vencida (depois da implantação do gestor)
        bd.escrever(
            "INSERT INTO ri_protocolos(numero, data_prenotacao, data_limite, "
            "situacao, apresentante, criado_em) VALUES (%s,%s,%s,'ABERTO',%s,%s)",
            (99001, "2026-09-20", vencida, NOME_DO_CLIENTE, agora))
        # um achado aberto do gestor, com nome no título (não pode sair)
        bd.escrever(
            "INSERT INTO ge_achados(chave, regra, gravidade, setor, titulo, "
            "primeiro_visto_em, ultimo_visto_em) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            ("TESTE:1", "TESTE", "VENCIDO", "RI_QUALIFICACAO",
             f"Prenotação de {NOME_DO_CLIENTE}", agora, agora))
    db.create_ticket(True, "Certidão")
    db.create_ticket(False, "Firma")


def _todos_os_textos(obj) -> list[str]:
    if isinstance(obj, dict):
        return [t for k, v in obj.items() for t in (k, *_todos_os_textos(v))]
    if isinstance(obj, list):
        return [t for v in obj for t in _todos_os_textos(v)]
    return [obj] if isinstance(obj, str) else []


# ------------------------------------------------------------ os números


def test_os_numeros_seguem_a_regua_da_casa(cg_casa):
    db = cg_casa["db"]
    _semear(db)
    n = PN.montar(db)
    assert n["nao_mediu"] == [], n["nao_mediu"]
    dia = n["periodos"]["dia"]
    # selo usado = ato; o cancelado e o órfão não contam como ato
    assert dia["atos_por_atribuicao"]["RI"] == 1
    assert dia["atos_por_atribuicao"]["Notas"] == 1
    assert dia["selos_usados"] == 2
    assert dia["selos_cancelados"] == 1
    # receita: só a entrada de ato — sem troco, sem saída, sem o gratuito
    assert dia["receita_centavos"] == 12345
    assert dia["lancamentos"] == 1
    assert dia["gratuidades"] == 1
    # o mês e a semana contêm o dia
    for p in ("semana", "mes"):
        assert n["periodos"][p]["receita_centavos"] >= 12345
    ag = n["agora"]
    assert ag["protocolos"]["em_andamento"] == 2      # o ENTREGUE sai
    assert ag["protocolos"]["atrasados"] == 1
    assert ag["prenotacoes"]["vencidas"] == 1
    assert ag["atendimento"]["aguardando"] == 2
    assert dia["senhas"] == 2 and dia["senhas_prioritarias"] == 1
    assert ag["alertas"]["achados_por_gravidade"]["VENCIDO"] == 1


def test_bloco_que_quebra_vira_nao_medido_e_nao_zero(cg_casa, monkeypatch):
    db = cg_casa["db"]

    def quebra(*a, **k):
        raise RuntimeError("tabela que não existe")

    monkeypatch.setattr(PN, "_receita", quebra)
    n = PN.montar(db)
    assert "receita" in n["nao_mediu"]
    assert n["periodos"]["dia"]["receita_centavos"] is None
    # os outros blocos continuam medidos
    assert n["periodos"]["dia"]["selos_usados"] == 0


def test_nenhum_nome_nem_cpf_sai_no_retrato(cg_casa):
    db = cg_casa["db"]
    _semear(db)
    n = PN.montar(db)
    texto = json.dumps(n, ensure_ascii=False)
    assert NOME_DO_CLIENTE not in texto
    assert "BEATRIZ" not in texto.upper()
    assert CPF not in texto and "00000005070" not in texto
    assert "2026.10.90" not in texto           # nem número de protocolo
    # e a guarda do retrato aceita o que o painel monta
    PR.conferir_que_e_so_agregado(n)
    for t in _todos_os_textos(n):
        assert "beatriz" not in t.lower()


def test_a_guarda_recusa_texto_que_nao_e_agregado():
    with pytest.raises(PR.RetratoError):
        PR.conferir_que_e_so_agregado({"agora": {"cliente": NOME_DO_CLIENTE}})
    with pytest.raises(PR.RetratoError):
        PR.conferir_que_e_so_agregado({"lista": [CPF]})
    PR.conferir_que_e_so_agregado({"hoje": "2026-10-26", "n": 3, "x": None,
                                   "rotulo": "Hoje"})


# ------------------------------------------------------------ a tela


def test_o_admin_ve_o_painel_e_ele_nao_mostra_nome(cg_casa_logada):
    _semear(cg_casa_logada["db"])
    c = cg_casa_logada["c"]
    r = c.get("/painel")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "R$ 123,45" in html
    assert NOME_DO_CLIENTE not in html and CPF not in html
    assert r.headers.get("Cache-Control") == "no-store"
    for p in ("semana", "mes"):
        assert c.get(f"/painel?p={p}").status_code == 200


def test_o_balcao_nao_ve_a_receita(cg_casa):
    db = cg_casa["db"]
    db.create_user("carla", "CARLA EXEMPLO LIMA", SENHA, "USER")
    c = cg_casa["c"]
    cg_login(c, "carla", SENHA)
    assert c.get("/painel").status_code == 403


@pytest.fixture
def painel(cg_casa):
    db = cg_casa["db"]
    db.create_user("beatriz", "BEATRIZ EXEMPLO DOS SANTOS", SENHA, "PAINEL")
    c = cg_casa["c"]
    cg_login(c, "beatriz", SENHA)
    return cg_casa


def test_o_papel_painel_existe_nos_tres_lugares():
    import app as APP
    import dois_fatores_web as DFW
    assert "PAINEL" in APP.ROLES and "PAINEL" in DFW.PAPEIS
    assert PCW.PAPEL_SO_AGREGADOS == "PAINEL"


def test_o_papel_painel_entra_e_cai_no_painel(painel):
    c = painel["c"]
    r = c.get("/", follow_redirects=False)
    assert r.status_code == 302 and r.headers["Location"].endswith("/painel")
    assert c.get("/painel").status_code == 200


@pytest.mark.parametrize("endereco", ["/relatorios", "/caixa", "/tarefas",
                                      "/usuarios", "/relatorios/tarefas.csv",
                                      "/selos", "/painel/retrato", "/nao-existe"])
def test_o_papel_painel_nao_alcanca_outra_tela(painel, endereco):
    r = painel["c"].get(endereco, follow_redirects=False)
    assert r.status_code == 302, (endereco, r.status_code)
    assert r.headers["Location"].endswith("/painel")


def test_o_papel_painel_nao_grava_nada(painel):
    c = painel["c"]
    html = c.get("/painel").get_data(as_text=True)
    import re
    token = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
    r = c.post("/atendimento", data={"csrf_token": token, "action": "new"})
    assert r.status_code == 403
    with painel["db"].connect() as con:
        assert banco(con).valor("SELECT COUNT(*) FROM service_tickets") == 0


def test_o_papel_painel_sai_e_troca_a_propria_senha(painel):
    c = painel["c"]
    assert c.get("/conta/senha").status_code == 200
    html = c.get("/painel").get_data(as_text=True)
    assert "Sistema completo" not in html          # não oferece a porta que não abre
    import re
    token = re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)
    r = c.post("/logout", data={"csrf_token": token}, follow_redirects=False)
    assert r.status_code == 302
    assert c.get("/painel", follow_redirects=False).status_code == 302


def test_a_guarda_decide_por_lista_e_fecha_por_padrao():
    assert PCW.destino_do_papel_painel("PAINEL", "painel_celular", "GET") is None
    assert PCW.destino_do_papel_painel("PAINEL", "rota_que_nasceu_amanha", "GET") == "painel"
    assert PCW.destino_do_papel_painel("PAINEL", "rota_que_nasceu_amanha", "POST") == "recusa"
    assert PCW.destino_do_papel_painel("ADMIN", "rota_que_nasceu_amanha", "POST") is None


def test_a_tela_do_retrato_e_do_admin_e_mostra_a_previa_sem_enviar(cg_casa_logada, monkeypatch):
    c = cg_casa_logada["c"]
    chamadas = []
    monkeypatch.setattr(PR, "_http_post", lambda *a, **k: chamadas.append(a) or (204, ""))
    r = c.get("/painel/retrato?ver=previa")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "cg-painel-1" in html
    assert chamadas == []
