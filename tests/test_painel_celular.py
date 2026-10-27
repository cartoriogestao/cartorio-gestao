"""O painel do gestor no celular — os números, o titular e a trava dele.

Pedido de 26/10/2026: «painel do gestor no celular, só com números agregados»;
respostas do oficial no mesmo dia: «apenas eu» e «apenas emolumentos abatidos
do FERJ». Os testes provam o que não se vê lendo o código:

  * os números são os da régua da casa (selo usado, protocolo atrasado,
    prenotação vencida e a vencer, fila do dia) — e a RECEITA é o emolumento
    dos selos pagos menos o FERJ, sem fundos, sem ISS, sem o caixa;
  * NADA que identifica pessoa chega à tela nem ao retrato — o teste semeia
    nome e CPF fictícios e procura os dois;
  * só o oficial TITULAR (um único ADMIN, guardado em configuração) abre o
    painel e mexe no retrato: outro ADMIN, o gerente, o auditor e o balcão
    recebem 403; e o papel PAINEL da primeira versão deixou de existir.

Dados inventados: mario/beatriz/carla, CPF 000.000.050-70 (fictício declarado
no anti-vazamento).

Testes escritos e NÃO executados na máquina de desenvolvimento (sobrecarga),
por ordem do oficial em 26/10/2026; a suíte completa roda na máquina do merge.
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
        # selos: RI e Notas pagos hoje, um RI isento hoje, um de homologação
        # hoje (não é receita), um cancelado hoje e um órfão. O texto é o que
        # o aparelho escreve; o nome da parte está nele e não pode sair.
        def texto(n, emol, marca=""):
            return (f"Poder Judiciário – TJMA. Selo: {n}, 26/10/2026 10:00:00, "
                    f"Ato: 16.24.1,{marca} Total R$ 999,99 Emol R$ {emol} FERC R$ 3,00 "
                    "FADEP R$ 4,00 FEMP R$ 2,00 FERRFIS R$ 1,00 "
                    f"PARTE(S): {NOME_DO_CLIENTE}, Consulte em https://selo.tjma.jus.br")
        for numero, atr, usado, cancelado, emol, marca, ambiente in (
                ("SELOTESTE0000000000000000001", "IMOVEL", hoje + "T10:00:00", None,
                 "100,00", "", "PRODUCAO"),
                ("SELOTESTE0000000000000000002", "NOTAS", hoje + "T11:00:00", None,
                 "50,00", "", "PRODUCAO"),
                ("SELOTESTE0000000000000000005", "IMOVEL", hoje + "T11:30:00", None,
                 "70,00", " Selo Isento", "PRODUCAO"),
                ("SELOTESTE0000000000000000006", "CIVIL", hoje + "T11:40:00", None,
                 "1.000,00", "", "HOMOLOGACAO"),
                ("SELOTESTE0000000000000000003", "CIVIL", None, hoje + "T12:00:00",
                 "500,00", "", "PRODUCAO"),
                ("SELOTESTE0000000000000000004", "PROTESTO", None, None,
                 "500,00", "", "PRODUCAO")):
            bd.escrever(
                "INSERT INTO sd_selos(numero, atribuicao, obtido_em, obtido_por, "
                "usado_em, cancelado_em, referencia, texto, ambiente) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (numero, atr, hoje + "T09:00:00", "beatriz", usado, cancelado,
                 NOME_DO_CLIENTE, texto(numero, emol, marca), ambiente))
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
        # duas senhas do balcão, direto na tabela: o painel de senhas (PR #32)
        # tira `Database.create_ticket` e passa a emitir por `senhas.emitir`;
        # a tabela e estas colunas são as mesmas nos dois.
        for numero, preferencial, tipo in ((1, 1, "Certidão"), (2, 0, "Firma")):
            bd.escrever(
                "INSERT INTO service_tickets(ticket_no, ticket_date, priority, "
                "service_type, status, created_at) VALUES (%s,%s,%s,%s,'AGUARDANDO',%s)",
                (numero, hoje, preferencial, tipo, agora))


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
    # selo usado = ato (o painel conta o razão inteiro, como /selos); o
    # cancelado e o órfão não contam como ato
    assert dia["atos_por_atribuicao"]["RI"] == 2
    assert dia["atos_por_atribuicao"]["Notas"] == 1
    assert dia["atos_por_atribuicao"]["RCPN"] == 1
    assert dia["selos_usados"] == 4
    assert dia["selos_cancelados"] == 1
    ag = n["agora"]
    assert ag["protocolos"]["em_andamento"] == 2      # o ENTREGUE sai
    assert ag["protocolos"]["atrasados"] == 1
    assert ag["prenotacoes"]["vencidas"] == 1
    assert ag["atendimento"]["aguardando"] == 2
    assert dia["senhas"] == 2 and dia["senhas_prioritarias"] == 1
    assert ag["alertas"]["achados_por_gravidade"]["VENCIDO"] == 1


# ------------------------------------------------- a receita: emolumento − FERJ


def test_a_receita_e_o_emolumento_menos_o_ferj_sem_fundos_nem_caixa(cg_casa):
    """«apenas emolumentos abatidos do FERJ» — 26/10/2026.

    RI: emolumento R$ 100,00, FERJ 12% = R$ 12,00 → R$ 88,00.
    Notas: emolumento R$ 50,00, FERJ = R$ 6,00 → R$ 44,00. Total R$ 132,00.
    Fora: o isento (não se cobrou), o de homologação (não é ato praticado), o
    cancelado, o órfão, os quatro fundos do selo, o «Total» do selo e TODO o
    caixa — inclusive a sangria de R$ 999,00 e a entrada de R$ 123,45.
    """
    db = cg_casa["db"]
    _semear(db)
    n = PN.montar(db)
    dia = n["periodos"]["dia"]
    assert n["ferj_percentual_centesimos"] == 1200
    assert dia["receita_centavos"] == 13200
    assert dia["atos_cobrados"] == 2
    assert dia["isentos"] == 1
    assert dia["diferidos"] == 0 and dia["sem_valor"] == 0
    for p in ("semana", "mes"):
        assert n["periodos"][p]["receita_centavos"] >= 13200
    assert "lancamentos" not in dia and "gratuidades" not in dia


def test_o_ferj_e_a_regua_de_custas_e_nao_doze_por_cento_solto(cg_casa):
    import custas
    db = cg_casa["db"]
    _semear(db)
    db.set_settings({custas.CHAVE_PERCENTUAL_FERJ: "10,00"})
    dia = PN.montar(db)["periodos"]["dia"]
    # 100 − 10 + 50 − 5 = 135
    assert dia["receita_centavos"] == 13500
    assert custas.ferj_do_emolumento(10000, custas.percentual_ferj({})) == 1200


def test_percentual_do_ferj_ilegivel_nao_vira_zero(cg_casa):
    import custas
    db = cg_casa["db"]
    _semear(db)
    db.set_settings({custas.CHAVE_PERCENTUAL_FERJ: "doze"})
    n = PN.montar(db)
    assert "ferj" in n["nao_mediu"]
    assert n["periodos"]["dia"]["receita_centavos"] is None
    assert n["periodos"]["dia"]["selos_usados"] == 4


def test_selo_diferido_e_selo_sem_emolumento_nao_somam_mas_se_contam(cg_casa):
    db = cg_casa["db"]
    hoje = HOJE.isoformat()
    with db.transaction() as con:
        bd = banco(con)
        for numero, texto in (
                ("SELOTESTE0000000000000000007",
                 "Selo: SELOTESTE0000000000000000007, Total R$ 80,00 Emol R$ 80,00 Diferido"),
                ("SELOTESTE0000000000000000008",
                 "Selo: SELOTESTE0000000000000000008, sem valores")):
            bd.escrever(
                "INSERT INTO sd_selos(numero, atribuicao, obtido_em, usado_em, texto) "
                "VALUES (%s,'IMOVEL',%s,%s,%s)",
                (numero, hoje + "T09:00:00", hoje + "T10:00:00", texto))
    dia = PN.montar(db)["periodos"]["dia"]
    assert dia["receita_centavos"] == 0
    assert dia["diferidos"] == 1 and dia["sem_valor"] == 1


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


# ------------------------------------------------------------ o titular


def _admin(db, nome="mario"):
    return next(u for u in db.list_users() if u["username"] == nome)


def _titular(db, nome="mario"):
    u = _admin(db, nome)
    PR.definir_titular(db, novo_id=u["id"], quem=u)
    return u


def _token(c, endereco):
    import re
    html = c.get(endereco).get_data(as_text=True)
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


def test_o_papel_painel_deixou_de_existir():
    import app as APP
    import dois_fatores_web as DFW
    assert "PAINEL" not in APP.ROLES and "PAINEL" not in DFW.PAPEIS
    assert not hasattr(PCW, "ROTAS_DO_PAINEL")


def test_o_papel_painel_e_recusado_no_cadastro(cg_casa):
    with pytest.raises(ValueError):
        cg_casa["db"].create_user("carla", "CARLA EXEMPLO LIMA", SENHA, "PAINEL")


def test_sem_titular_o_admin_e_levado_a_escolher(cg_casa_logada):
    c = cg_casa_logada["c"]
    r = c.get("/painel", follow_redirects=False)
    assert r.status_code == 302 and r.headers["Location"].endswith("/painel/retrato")
    html = c.get("/painel/retrato").get_data(as_text=True)
    assert 'value="titular"' in html
    assert "Gerar a chave" not in html        # sem titular, nada de retrato


def test_o_admin_escolhe_o_titular_pela_tela_e_fica_na_auditoria(cg_casa_logada):
    db, c = cg_casa_logada["db"], cg_casa_logada["c"]
    mario = _admin(db)
    r = c.post("/painel/retrato", data={
        "csrf_token": _token(c, "/painel/retrato"), "acao": "titular",
        "usuario_id": str(mario["id"])})
    assert r.status_code == 302
    assert db.get_setting(PR.CHAVE_TITULAR) == str(mario["id"])
    with db.connect() as con:
        linha = banco(con).um(
            "SELECT details FROM audit_logs WHERE action = 'PAINEL_TITULAR_ESCOLHIDO' "
            "ORDER BY id DESC LIMIT 1")
    detalhes = json.loads(linha["details"])
    assert detalhes["titular"] == "mario"
    assert detalhes["agente"] and detalhes["a_mando_de"] == "mario"


def test_o_titular_ve_o_painel_e_ele_nao_mostra_nome(cg_casa_logada):
    db, c = cg_casa_logada["db"], cg_casa_logada["c"]
    _semear(db)
    _titular(db)
    r = c.get("/painel")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Emolumentos líquidos do FERJ" in html
    assert "R$ 132,00" in html
    assert "12,00%" in html
    assert NOME_DO_CLIENTE not in html and CPF not in html
    assert r.headers.get("Cache-Control") == "no-store"
    for p in ("semana", "mes"):
        assert c.get(f"/painel?p={p}").status_code == 200


@pytest.fixture
def outro_admin(cg_casa):
    """mario é o titular; carla é OUTRO ADMIN, logada."""
    db = cg_casa["db"]
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    db.create_user("carla", "CARLA EXEMPLO LIMA", SENHA, "ADMIN")
    _titular(db, "mario")
    cg_login(cg_casa["c"], "carla", SENHA)
    return cg_casa


def test_outro_admin_nao_ve_o_painel(outro_admin):
    assert outro_admin["c"].get("/painel").status_code == 403


def test_outro_admin_ve_quem_e_o_titular_e_nada_mais(outro_admin):
    html = outro_admin["c"].get("/painel/retrato?ver=previa").get_data(as_text=True)
    assert "MARIO EXEMPLO DOS SANTOS" in html
    assert "cg-painel-1" not in html            # sem prévia
    assert 'value="titular"' not in html        # sem o formulário de escolha
    assert "Gerar a chave" not in html


@pytest.mark.parametrize("acao", ["salvar", "gerar_chave", "enviar"])
def test_outro_admin_nao_mexe_no_retrato(outro_admin, acao, monkeypatch):
    chamadas = []
    monkeypatch.setattr(PR, "_http_post", lambda *a, **k: chamadas.append(a) or (204, ""))
    c = outro_admin["c"]
    r = c.post("/painel/retrato", data={
        "csrf_token": _token(c, "/painel/retrato"), "acao": acao,
        "url": "https://vps.exemplo.invalid/painel/retrato", "ligado": "1"})
    assert r.status_code == 403
    assert chamadas == []
    assert outro_admin["db"].get_setting(PR.CHAVE_URL, "") == ""


def test_outro_admin_nao_toma_o_painel_para_si(outro_admin):
    db, c = outro_admin["db"], outro_admin["c"]
    carla = _admin(db, "carla")
    c.post("/painel/retrato", data={
        "csrf_token": _token(c, "/painel/retrato"), "acao": "titular",
        "usuario_id": str(carla["id"])})
    assert db.get_setting(PR.CHAVE_TITULAR) == str(_admin(db, "mario")["id"])
    with pytest.raises(PR.RetratoError):
        PR.definir_titular(db, novo_id=carla["id"], quem=carla)


def test_o_titular_passa_o_painel_a_outro_admin(outro_admin):
    db = outro_admin["db"]
    mario, carla = _admin(db, "mario"), _admin(db, "carla")
    PR.definir_titular(db, novo_id=carla["id"], quem=mario)
    assert PR.e_o_titular(db, carla) and not PR.e_o_titular(db, mario)
    assert outro_admin["c"].get("/painel").status_code == 200


def test_titular_desativado_libera_a_escolha(outro_admin):
    db = outro_admin["db"]
    mario, carla = _admin(db, "mario"), _admin(db, "carla")
    db.set_user_active(mario["id"], False)
    assert PR.titular(db) is None
    PR.definir_titular(db, novo_id=carla["id"], quem=carla)
    assert PR.e_o_titular(db, carla)


@pytest.mark.parametrize("papel", ["MANAGER", "AUDITOR", "USER"])
def test_ninguem_alem_do_admin_titular_entra(cg_casa, papel):
    db = cg_casa["db"]
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    _titular(db)
    db.create_user("carla", "CARLA EXEMPLO LIMA", SENHA, papel)
    c = cg_casa["c"]
    cg_login(c, "carla", SENHA)
    assert c.get("/painel").status_code == 403
    assert c.get("/painel/retrato").status_code == 403


def test_titular_tem_de_ser_admin_ativo_e_pessoa(cg_casa):
    db = cg_casa["db"]
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    db.create_user("carla", "CARLA EXEMPLO LIMA", SENHA, "MANAGER")
    mario, carla = _admin(db, "mario"), _admin(db, "carla")
    with pytest.raises(PR.RetratoError):
        PR.definir_titular(db, novo_id=carla["id"], quem=mario)
    with pytest.raises(PR.RetratoError):
        PR.definir_titular(db, novo_id=mario["id"], quem=carla)
    robo = dict(mario, eh_robo=1)
    assert not PR._usuario_valido_para_titular(robo)
    assert PR.titular(db) is None


def test_a_tela_do_retrato_do_titular_mostra_a_previa_sem_enviar(cg_casa_logada, monkeypatch):
    db, c = cg_casa_logada["db"], cg_casa_logada["c"]
    _titular(db)
    chamadas = []
    monkeypatch.setattr(PR, "_http_post", lambda *a, **k: chamadas.append(a) or (204, ""))
    r = c.get("/painel/retrato?ver=previa")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "cg-painel-1" in html
    assert "ferj_percentual_centesimos" in html
    assert chamadas == []


def test_sem_titular_o_retrato_nao_sai(cg_casa):
    db = cg_casa["db"]
    PR.salvar_configuracao(db, url="https://vps.exemplo.invalid/painel/retrato", ligado=True)
    feito = PR.empurrar(db, cg_casa["app"].config["DATA_DIR"], forcar=True,
                        http_post=lambda u, c: (204, ""))
    assert feito["ok"] is False and "titular" in feito["motivo"]
