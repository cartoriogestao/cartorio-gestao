"""A pública forma e a certidão reprográfica — `nt_publica_forma.py` (LG04, item 6).

O QUE ESTES TESTES PROTEGEM

    a numeração         por exercício, sem repetir
    o teor congelado    o que saiu fica, mesmo que o modelo mude amanhã; a
                        transcrição do balcão é texto, e se escapa
    o item da casa      a tabela de 2026 não tem item de pública forma: sem o
                        item configurado nada se emite, e item que a tabela
                        não conhece não se grava
    o selo              sai pelo caminho do contrato; quando não sai, a
                        pública forma fica SUSPENSA, e não emitida sem selo
    a guarda            anônimo vai ao login, papel errado é 403, POST sem
                        CSRF é 400, toda escrita deixa rastro

    e a CERTIDÃO REPROGRÁFICA, que não é ato novo: a autenticação de cópia
    reprográfica (13.18, por página) e a certidão das Notas por folha (13.12.1
    e 13.12.3) já existiam — aqui se prova que emitem, selam e cobram o item
    certo, com os preços da tabela real de 2026.

Dados fictícios. Nenhum teste fala com o selador: o aparelho é trocado por um
falso que grava no razão como o de verdade.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ato_selado as AS
import notas_certidao as NCE
import nt_publica_forma as PF
from bd_nativo import banco
from caixa_schema import centavos, reais
from conftest import cg_login

SENHA = "Senha#12345"
OFICIAL = "MARIO EXEMPLO DOS SANTOS"
REAIS = json.loads((RAIZ / "tests" / "custas_reais.json").read_text("utf-8"))
ITEM_DE_TESTE = "13.18"   # um item que a tabela conhece — a casa escolhe o seu


def _token(html: str) -> str:
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


def _semear_tabela(db, codigos) -> None:
    """A vigência de 2026 e os itens pedidos, tirados da tabela real."""
    with db.transaction() as con:
        bd = banco(con)
        bd.escrever(
            """INSERT INTO cx_vigencias(codigo, descricao, vigente, inicio, fim,
                                        importado_em)
               VALUES (10022, 'Período de 2026', 1, '2026-01-01', '2026-12-31',
                       '2026-08-21') ON CONFLICT DO NOTHING""")
        for e in REAIS["valores_2026"]:
            if e["tj"] not in codigos:
                continue
            bd.escrever(
                """INSERT INTO cx_servicos(codigo, codigo_tj, descricao, ativo)
                   VALUES (%s,%s,%s,1) ON CONFLICT DO NOTHING""",
                (int(e["s"]), e["tj"], e["descricao"]))
            total = sum(int(round(e[k] * 100))
                        for k in ("emol", "ferc", "femp", "fadp", "ferrfis"))
            bd.escrever(
                """INSERT INTO cx_servico_valores(servico, vigencia, emolumentos,
                       ferc, femp, fadep, ferrfis, total)
                   VALUES (%s,10022,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                (int(e["s"]), reais(int(round(e["emol"] * 100))),
                 reais(int(round(e["ferc"] * 100))),
                 reais(int(round(e["femp"] * 100))),
                 reais(int(round(e["fadp"] * 100))),
                 reais(int(round(e["ferrfis"] * 100))), reais(total)))


def _total_da_tabela(codigo_tj: str) -> int:
    e = next(x for x in REAIS["valores_2026"] if x["tj"] == codigo_tj)
    return sum(int(round(e[k] * 100))
               for k in ("emol", "ferc", "femp", "fadp", "ferrfis"))


@pytest.fixture()
def selador_falso(monkeypatch):
    """O aparelho trocado por um que grava no razão e devolve um selo.

    O mesmo SID devolve o mesmo selo, como o de verdade — é o que prova que
    selar de novo não compra outro.
    """
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
        numero = ja["numero"] if ja else f"PUBFOR{len(pedidos):010d}"
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
def casa(cg_casa):
    db = cg_casa["db"]
    db.create_user("oficial", OFICIAL, SENHA, "ADMIN")
    db.create_user("balcao", "BALCAO EXEMPLO", SENHA, "USER")
    db.create_user("auditor", "AUDITOR EXEMPLO", SENHA, "AUDITOR")
    db.set_settings({"selo_tabela_custas_em": "20260101", "ri_cns": "000000"})
    _semear_tabela(db, {"13.18", "13.12.1", "13.12.3"})
    return cg_casa


@pytest.fixture()
def protocolo_pago(casa):
    """O balcão já recebeu: protocolo pago com o 13.18, atendido pelo oficial.

    Desde o LX16 o selo PAGO só sai com protocolo e pagamento
    (`ato_selado.cobrir_o_selo`). Estes testes falam da pública forma e da
    autenticação, e não do caixa: montam o que o balcão monta, pelo helper
    único `protocolo_de_teste`, em vez de desligar a trava. Que o balcão
    chega lá pelas telas, sem beco sem saída, quem prova é
    `test_o_balcao_abre_o_protocolo_paga_e_a_autenticacao_sela_pelas_telas`.
    """
    from protocolo_de_teste import atender_protocolo_pago
    with casa["db"].transaction() as con:
        return atender_protocolo_pago(con, usuario=OFICIAL,
                                      codigos=(ITEM_DE_TESTE,))


def _logar(casa, quem="oficial"):
    c = casa["app"].test_client()
    cg_login(c, quem, SENHA)
    return c


def _emitir(c, **campos):
    token = _token(c.get("/notas/publica-forma").get_data(as_text=True))
    dados = {"documento_especie": "Certificado de conclusão",
             "documento_expedidor": "ESCOLA DE EXEMPLO",
             "apresentante": "FULANO DE TAL EXEMPLO",
             "apresentante_documento": "000.000.001-91",
             "transcricao": "CERTIFICAMOS QUE FULANO DE TAL EXEMPLO\n"
                            "CONCLUIU O CURSO DE EXEMPLO.",
             "folhas": "1", "csrf_token": token}
    dados.update(campos)
    return c.post("/notas/publica-forma/emitir", data=dados,
                  follow_redirects=True)


def _linhas(db, sql, parametros=None):
    with db.connect() as con:
        return banco(con).ler(sql, parametros)


# --------------------------------------------------------------- o item

def test_sem_item_configurado_a_publica_forma_nao_se_emite(casa, selador_falso):
    """A tabela de 2026 não tem item de pública forma: sem a casa dizer qual
    cobra, não se numera nada e o selador nem é chamado."""
    r = _emitir(_logar(casa))
    assert "falta dizer qual item" in r.get_data(as_text=True)
    assert _linhas(casa["db"], "SELECT id FROM nt_publicas_formas ORDER BY id") == []
    assert selador_falso == []


def test_a_tabela_ativa_de_2026_nao_tem_item_de_publica_forma():
    """É o que justifica o item ser da casa, e não do código.

    «Transcrição» só conta nas Notas (13.x): as duas da tabela — 14.3.1 e
    14.3.2 — são a transcrição de assento do exterior e a da opção de
    nacionalidade, do Registro Civil, e não a pública forma.
    """
    achados = [e for e in REAIS["valores_2026"]
               if re.search(r"p[uú]blica\s+forma", e["descricao"], re.I)
               or (e["tj"].startswith("13.")
                   and re.search(r"transcri", e["descricao"], re.I))]
    assert achados == []


def test_item_que_a_tabela_nao_conhece_nao_se_grava(casa):
    c = _logar(casa)
    token = _token(c.get("/notas/publica-forma/configuracao").get_data(as_text=True))
    r = c.post("/notas/publica-forma/configuracao",
               data={"codigo_tj": "99.99", "csrf_token": token},
               follow_redirects=True)
    assert "não está na tabela" in r.get_data(as_text=True)
    assert casa["db"].get_setting(PF.CHAVE_DO_ITEM, "") == ""


def test_gravar_o_item_deixa_rastro_com_o_antes_e_o_depois(casa):
    c = _logar(casa)
    token = _token(c.get("/notas/publica-forma/configuracao").get_data(as_text=True))
    c.post("/notas/publica-forma/configuracao",
           data={"codigo_tj": ITEM_DE_TESTE, "csrf_token": token})
    assert casa["db"].get_setting(PF.CHAVE_DO_ITEM, "") == ITEM_DE_TESTE
    rastro = _linhas(casa["db"],
                     "SELECT details FROM audit_logs WHERE action = %s "
                     "ORDER BY id", ("NT_PUBLICA_FORMA_ITEM_CONFIGURADO",))
    assert rastro and ITEM_DE_TESTE in rastro[-1]["details"]


def test_o_balcao_nao_escolhe_o_item_da_cobranca(casa):
    c = _logar(casa, "balcao")
    assert c.get("/notas/publica-forma/configuracao").status_code == 403


# ------------------------------------------------------- emitir e selar

def test_a_publica_forma_sai_numerada_selada_e_emitida(casa, protocolo_pago,
                                                       selador_falso):
    casa["db"].set_settings({PF.CHAVE_DO_ITEM: ITEM_DE_TESTE})
    c = _logar(casa)
    html = _emitir(c).get_data(as_text=True)
    assert "emitida" in html
    pf = _linhas(casa["db"], "SELECT * FROM nt_publicas_formas ORDER BY id")[0]
    assert pf["situacao"] == "EMITIDA"
    assert pf["numero"] == 1 and pf["selo"] == "PUBFOR0000000001"
    assert pf["codigo_tj"] == ITEM_DE_TESTE
    assert selador_falso[0]["caminho"] == "/selo/notas/publica-forma"
    corpo = selador_falso[0]["dados"]
    assert corpo["ato"] == {"codigo": ITEM_DE_TESTE,
                            "codigoTabelaCusta": "0520260101"}
    assert corpo["partes"]["parteAto"] == [
        {"documento": "00000000191", "nome": "FULANO DE TAL EXEMPLO"}]
    # o selo amarrado no razão, à pública forma
    selo = _linhas(casa["db"], "SELECT tabela, ato_id FROM sd_selos ORDER BY id")[0]
    assert selo == {"tabela": "nt_publicas_formas", "ato_id": pf["id"]}
    acoes = [x["action"] for x in _linhas(
        casa["db"], "SELECT action FROM audit_logs ORDER BY id")]
    assert "NT_PUBLICA_FORMA_NUMERADA" in acoes
    assert "NT_PUBLICA_FORMA_EMITIDA" in acoes


def test_a_numeracao_e_por_exercicio_e_nao_repete(casa, protocolo_pago,
                                                  selador_falso):
    casa["db"].set_settings({PF.CHAVE_DO_ITEM: ITEM_DE_TESTE})
    c = _logar(casa)
    _emitir(c)
    _emitir(c)
    numeros = [x["numero"] for x in _linhas(
        casa["db"], "SELECT numero FROM nt_publicas_formas ORDER BY id")]
    assert numeros == [1, 2]


def test_sem_o_aparelho_a_publica_forma_fica_suspensa_e_nao_emitida(
        casa, protocolo_pago):
    """Sem o falso, o selador do teste não existe: a falha suspende.

    Com o protocolo pago, para a falha ser a do APARELHO — sem ele, quem
    suspendia era a trava do selo pago, e o teste passava pelo motivo errado.
    """
    casa["db"].set_settings({PF.CHAVE_DO_ITEM: ITEM_DE_TESTE})
    html = _emitir(_logar(casa)).get_data(as_text=True)
    assert "SUSPENSA" in html
    pf = _linhas(casa["db"], "SELECT * FROM nt_publicas_formas ORDER BY id")[0]
    assert pf["situacao"] == "SUSPENSO_SELO"
    assert pf["selo"] is None and pf["motivo_suspensao"]
    assert "aguardando cobertura" not in pf["motivo_suspensao"]
    assert _linhas(casa["db"],
                   "SELECT id FROM audit_logs WHERE action = %s ORDER BY id",
                   ("NT_PUBLICA_FORMA_SUSPENSA_SELO_FALHOU",))


@pytest.fixture()
def suspensa(casa, protocolo_pago):
    casa["db"].set_settings({PF.CHAVE_DO_ITEM: ITEM_DE_TESTE})
    c = _logar(casa)
    _emitir(c)
    pf = _linhas(casa["db"], "SELECT * FROM nt_publicas_formas ORDER BY id")[0]
    return c, pf


def test_a_suspensa_selada_de_novo_vira_emitida(casa, suspensa, selador_falso):
    c, pf = suspensa
    token = _token(c.get(f"/notas/publica-forma/{pf['id']}").get_data(as_text=True))
    c.post(f"/notas/publica-forma/{pf['id']}/selar",
           data={"csrf_token": token})
    c.post(f"/notas/publica-forma/{pf['id']}/selar",
           data={"csrf_token": token})
    depois = _linhas(casa["db"], "SELECT * FROM nt_publicas_formas WHERE id = %s",
                     (pf["id"],))[0]
    assert depois["situacao"] == "EMITIDA" and depois["selo"]
    # o segundo clique não pede outro selo: a ficha já tem o dela
    assert len(selador_falso) == 1


# -------------------------------------------------------------- o teor

def test_o_teor_fica_congelado_mesmo_que_o_modelo_mude(casa, protocolo_pago,
                                                       selador_falso):
    casa["db"].set_settings({PF.CHAVE_DO_ITEM: ITEM_DE_TESTE})
    c = _logar(casa)
    _emitir(c)
    antes = _linhas(casa["db"], "SELECT teor, hash_teor FROM nt_publicas_formas "
                                "ORDER BY id")[0]
    assert "CONCLUIU O CURSO DE EXEMPLO" in antes["teor"]
    assert "PÚBLICA FORMA" in antes["teor"]
    assert len(antes["hash_teor"]) == 64
    import modelos_da_casa as MODELOS
    with casa["db"].transaction() as con:
        MODELOS.salvar(con, PF.CHAVE_DO_PAPEL,
                       corpo="<p>OUTRO TEXTO {{ numero }}</p>",
                       quem="MARIO EXEMPLO DOS SANTOS", agora="2026-10-19T10:00")
    depois = _linhas(casa["db"], "SELECT teor, hash_teor FROM nt_publicas_formas "
                                 "ORDER BY id")[0]
    assert depois == antes
    _emitir(c)
    nova = _linhas(casa["db"], "SELECT teor FROM nt_publicas_formas "
                               "ORDER BY id DESC LIMIT 1")[0]
    assert "OUTRO TEXTO 2" in nova["teor"] and "PÚBLICA FORMA" not in nova["teor"]


def test_a_transcricao_do_balcao_se_escapa_e_guarda_as_linhas():
    teor = PF.montar_teor(modelo=None, **dict(
        PF.CLAROS_DE_EXEMPLO, transcricao="LINHA UM\n<script>x</script>"))
    assert "<script>" not in teor
    assert "LINHA UM<br>&lt;script&gt;" in teor


def test_a_ressalva_da_rasura_vai_no_papel():
    teor = PF.montar_teor(modelo=None, **dict(
        PF.CLAROS_DE_EXEMPLO, ressalvas="Rasura na data de emissão."))
    assert "RESSALVA:" in teor and "Rasura na data de emissão." in teor
    sem = PF.montar_teor(modelo=None, **PF.CLAROS_DE_EXEMPLO)
    assert "não apresenta rasura" in sem


def test_transcricao_curta_demais_e_recusada(casa, selador_falso):
    casa["db"].set_settings({PF.CHAVE_DO_ITEM: ITEM_DE_TESTE})
    html = _emitir(_logar(casa), transcricao="RESUMO").get_data(as_text=True)
    assert "por inteiro" in html
    assert _linhas(casa["db"], "SELECT id FROM nt_publicas_formas ORDER BY id") == []


def test_o_conferidor_recusa_claro_inventado_e_aceita_o_padrao():
    import modelos_da_casa as MODELOS
    assert PF.conferir_modelo(MODELOS.padrao_de(PF.CHAVE_DO_PAPEL)) == ""
    assert "não monta" in PF.conferir_modelo("<p>{{ claro_inventado.x }}</p>")


def test_o_preco_sai_da_tabela_do_dia_pelo_item_da_casa(casa):
    with casa["db"].connect() as con:
        valor = PF.preco(con, ITEM_DE_TESTE, data="2026-10-19")
    assert valor["total_centavos"] == _total_da_tabela(ITEM_DE_TESTE)


# ------------------------------------------------------------- cancelar

def test_cancelar_guarda_o_teor_e_exige_motivo(casa, protocolo_pago,
                                               selador_falso):
    casa["db"].set_settings({PF.CHAVE_DO_ITEM: ITEM_DE_TESTE})
    c = _logar(casa)
    _emitir(c)
    pf = _linhas(casa["db"], "SELECT * FROM nt_publicas_formas ORDER BY id")[0]
    token = _token(c.get(f"/notas/publica-forma/{pf['id']}").get_data(as_text=True))
    c.post(f"/notas/publica-forma/{pf['id']}/cancelar",
           data={"motivo": "curto", "csrf_token": token})
    assert _linhas(casa["db"], "SELECT situacao FROM nt_publicas_formas")[0][
        "situacao"] == "EMITIDA"
    c.post(f"/notas/publica-forma/{pf['id']}/cancelar",
           data={"motivo": "Emitida em nome trocado.", "csrf_token": token})
    depois = _linhas(casa["db"], "SELECT * FROM nt_publicas_formas")[0]
    assert depois["situacao"] == "CANCELADA" and depois["teor"] == pf["teor"]


# ------------------------------------------------------------- a guarda

def test_anonimo_vai_ao_login(casa):
    c = casa["app"].test_client()
    assert c.get("/notas/publica-forma").status_code == 302
    assert c.post("/notas/publica-forma/emitir").status_code in (302, 400)


def test_auditor_le_e_nao_emite(casa):
    c = _logar(casa, "auditor")
    assert c.get("/notas/publica-forma").status_code == 200
    token = _token(c.get("/notas/publica-forma").get_data(as_text=True))
    r = c.post("/notas/publica-forma/emitir", data={"csrf_token": token})
    assert r.status_code == 403


def test_post_sem_csrf_e_recusado(casa):
    c = _logar(casa)
    r = c.post("/notas/publica-forma/emitir",
               data={"documento_especie": "x", "apresentante": "y"})
    assert r.status_code == 400


# ------------------------------------------- a certidão reprográfica

def test_a_autenticacao_de_copia_reprografica_sela_uma_vez_por_pagina(
        casa, protocolo_pago, selador_falso):
    """13.18 é «autenticação de cópias extraídas por meio reprográfico, por
    página»: três folhas, três selos, todos pelo caminho da autenticação."""
    c = _logar(casa)
    token = _token(c.get("/notas/autenticacao").get_data(as_text=True))
    r = c.post("/notas/autenticacao",
               data={"acao": "autenticar", "folhas": "3", "tipo": "PADRAO",
                     "apresentante": "FULANO DE TAL EXEMPLO",
                     "csrf_token": token}, follow_redirects=True)
    assert r.status_code == 200
    a = _linhas(casa["db"], "SELECT * FROM nt_autenticacoes ORDER BY id")[0]
    assert a["servico_codigo"] == 415 and a["folhas"] == 3 and a["selo"]
    assert [p["caminho"] for p in selador_falso] == ["/selo/notas/autenticacao"] * 3
    assert {p["dados"]["ato"]["codigo"] for p in selador_falso} == {"13.18"}
    with casa["db"].connect() as con:
        conta = AS.calcular_custas(con, servico=415, quantidade=3,
                                   data="2026-10-19")
    assert conta["total_centavos"] == 3 * _total_da_tabela("13.18")


def test_a_certidao_das_notas_por_folha_cobra_a_primeira_e_as_acrescidas(casa):
    """Certidão por meio reprográfico (CN-MA art. 851, § 1º) de três folhas:
    13.12.1 uma vez e 13.12.3 duas — os itens e os preços da tabela de 2026."""
    itens = NCE.itens_do_selo(3)
    assert itens == [("13.12.1", 1), ("13.12.3", 2)]
    total = 0
    with casa["db"].connect() as con:
        for codigo, quantas in itens:
            servico = AS.servico_do_codigo_tj(con, codigo)
            total += AS.calcular_custas(con, servico=servico["codigo"],
                                        quantidade=quantas,
                                        data="2026-10-19")["total_centavos"]
    assert total == (_total_da_tabela("13.12.1")
                     + 2 * _total_da_tabela("13.12.3"))


def test_a_certidao_das_notas_emite_o_teor_do_livro_e_o_envelope_do_selo(casa):
    with casa["db"].transaction() as con:
        aid = banco(con).escrever(
            """INSERT INTO nt_atos(tipo, data, situacao, livro, folha, teor,
                                   criado_em)
               VALUES ('ESCRITURA', '2026-10-01', 'LAVRADO', '12', '34',
                       '<p>TEOR DE EXEMPLO DO LIVRO</p>', '2026-10-01T10:00')
               RETURNING id""")[0]["id"]
        r = NCE.emitir(con, hoje="2026-10-19", agora="2026-10-19T10:00:00",
                       ato_id=aid, requerente="FULANO DE TAL EXEMPLO",
                       requerente_documento="000.000.001-91",
                       usuario="MARIO EXEMPLO DOS SANTOS")
    assert r["tipo"] == "INTEIRO_TEOR" and "TEOR DE EXEMPLO DO LIVRO" in r["teor"]
    corpo = NCE.envelope(codigo="13.12.1", quantidade=1,
                         escrevente="MARIO EXEMPLO DOS SANTOS",
                         versao_tabela="0520260101", parte=r["parte"])
    assert corpo["ato"]["codigo"] == "13.12.1"
    assert corpo["partes"]["parteAto"][0]["documento"] == "00000000191"


# ------------------------------ o balcão com a trava do selo pago (LX16)

def _clicar(c, tela, alvo, **campos) -> str:
    """O botão da tela: POST com o token dela, seguindo para onde ele leva."""
    token = _token(c.get(tela).get_data(as_text=True))
    return c.post(alvo, data={"csrf_token": token, **campos},
                  follow_redirects=True).get_data(as_text=True)


def test_o_balcao_abre_o_protocolo_paga_e_a_autenticacao_sela_pelas_telas(
        casa, selador_falso):
    """A trava do selo pago (LX16) não deixa o balcão num beco sem saída.

    O escrevente autentica sem protocolo: a autenticação NÃO se lavra, o
    aparelho nem é chamado, e o recado diz o que falta e onde se resolve.
    Daí em diante, só pelos links e botões que as telas mostram — «Selo e
    caixa» no menu, «Abrir protocolo», o item achado na tabela, «Atender este
    protocolo», «Registrar pagamento», o caixa do dia —, a mesma autenticação
    sai com um selo por folha, e cada selo gasta uma unidade do item pago.

    DOIS ACHADOS DESTE LOTE (LX22A3), que o teste prende:
      - o menu escondia «Selo e caixa» do escrevente: o link estava no bloco
        do ADMIN/MANAGER/AUDITOR, e o recado mandava o USER resolver numa
        tela que o menu dele não tinha;
      - a segunda folha saía sem gastar a segunda unidade: o consumo do
        primeiro selo deixava o item «ligado ao ato» pelo rastro antigo
        (`usado_por_*`), e `caixa_protocolo.itens_do_ato` o devolvia.
    """
    import caixa_protocolo as CXP
    c = _logar(casa, "balcao")
    pedido = {"acao": "autenticar", "folhas": "2", "tipo": "PADRAO",
              "apresentante": "FULANO DE TAL EXEMPLO"}

    # 1. sem protocolo: não lavra, não chama o aparelho e diz o que falta
    html = _clicar(c, "/notas/autenticacao", "/notas/autenticacao", **pedido)
    assert "NÃO lavrada" in html and AS.TITULO_DO_QUADRO in html
    assert "protocolo do balcão" in html and "Selo e caixa" in html
    assert _linhas(casa["db"], "SELECT id FROM nt_autenticacoes ORDER BY id") == []
    assert selador_falso == []
    assert 'href="/selo/cobertura"' in html, "o menu do USER não leva ao quadro"

    # 2. «Selo e caixa» → «Abrir protocolo» → o formulário do protocolo geral
    quadro = c.get("/selo/cobertura").get_data(as_text=True)
    assert "Abrir protocolo" in quadro
    assert 'href="/caixa/protocolos/novo"' in quadro
    ida = c.get("/caixa/protocolos/novo")
    assert ida.status_code == 302 and "/caixa/protocolos" in ida.headers["Location"]
    _clicar(c, "/caixa/protocolos", "/caixa/protocolos", acao="novo",
            interessado="FULANO DE TAL EXEMPLO", telefone="(99) 90000-0000",
            atribuicao="NOTAS")
    p = _linhas(casa["db"], "SELECT id, numero FROM cx_protocolos "
                            "WHERE interessado = %s ORDER BY id",
                ("FULANO DE TAL EXEMPLO",))[0]
    ficha = f"/caixa/protocolos/{p['id']}"

    # 3. o item 13.18 achado pela busca da ficha, uma unidade por folha
    achados = c.get(f"{ficha}?busca_ato=13.18").get_data(as_text=True)
    assert 'name="servico" value="415"' in achados
    _clicar(c, ficha, f"{ficha}/itens", acao="acrescentar", servico="415",
            quantidade="2")
    itens = _linhas(casa["db"], "SELECT * FROM cx_protocolo_atos "
                                "WHERE protocolo_id = %s ORDER BY id", (p["id"],))
    assert [(i["codigo_ato"], int(i["quantidade"]), int(i["quitado"] or 0))
            for i in itens] == [("13.18", 2, 0)]
    item_id = itens[0]["id"]

    # 4. «Atender este protocolo»: o quadro acha o item e pede o pagamento
    html = _clicar(c, "/selo/cobertura", "/selo/cobertura/atender",
                   protocolo=p["numero"])
    assert f"atendendo o protocolo {p['numero']}" in html
    assert "Registrar pagamento" in html and f'href="{ficha}"' in html

    # 5. sem caixa aberto, «quitar» diz onde se abre; aberto, quita
    html = _clicar(c, ficha, f"{ficha}/itens", acao="quitar", item_id=str(item_id))
    assert "Abra o caixa" in html
    _clicar(c, "/caixa", "/caixa", acao="abrir", saldo_inicial="0,00")
    html = _clicar(c, ficha, f"{ficha}/itens", acao="quitar", item_id=str(item_id))
    assert "Item quitado e lançado no caixa" in html
    assert "Tudo certo" in c.get("/selo/cobertura").get_data(as_text=True)

    # 6. a mesma autenticação de novo: lavra, um selo por folha, item gasto
    html = _clicar(c, "/notas/autenticacao", "/notas/autenticacao", **pedido)
    assert "NÃO lavrada" not in html
    a = _linhas(casa["db"], "SELECT * FROM nt_autenticacoes ORDER BY id")
    assert len(a) == 1 and a[0]["folhas"] == 2 and a[0]["selo"]
    assert [x["caminho"] for x in selador_falso] == ["/selo/notas/autenticacao"] * 2
    assert _linhas(casa["db"], "SELECT forma, item_id FROM cx_selo_coberturas "
                               "WHERE tabela = 'nt_autenticacoes' ORDER BY id") == [
        {"forma": AS.FORMA_ITEM_PAGO, "item_id": item_id}] * 2
    # duas folhas, duas unidades: com uma só, a segunda saía de graça
    gasto = _linhas(casa["db"], "SELECT * FROM cx_protocolo_atos WHERE id = %s",
                    (item_id,))[0]
    assert CXP.saldo_do_item(gasto) == 0
