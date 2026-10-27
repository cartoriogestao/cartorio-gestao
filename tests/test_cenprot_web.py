"""Testes das TELAS da CENPROT — a fila do que ela manda.

POR QUE ELES EXISTEM SEPARADOS DOS DE DOMÍNIO
    «Função de domínio pronta que nenhuma tela chama» é o defeito que mais se
    repetiu neste projeto — **seis vezes** —, e esta integração nasceu com
    dezesseis funções de transporte e nenhuma tela. Três delas ficaram órfãs
    na primeira passada, e é isto que as segura.

O QUE ESTES TESTES GUARDAM, E QUE O DE DOMÍNIO NÃO ALCANÇA
      - as telas EXISTEM e estão NO MENU;
      - **toda função pública de `cenprot_api` tem chamador** — o varredor das
        seis vezes, aplicado a este módulo;
      - elas mandam o `csrf_token` — dez formulários da casa não mandavam, e o
        balcão levou «bad request error» em 27/08/2026;
      - **o ambiente de homologação GRITA na tela**: pendência de teste com
        cara de real faz alguém ir ao balcão dizer que existe;
      - a recusa do domínio chega como frase em português, e não como HTTP 500;
      - **a rota de enviar não é do balcão** — quem manda muda coisa na
        Central;
      - e a decisão judicial **não oferece botão de responder**, porque o
        sistema não julga ordem de juiz.
"""
from __future__ import annotations

import ast
import glob
import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import cn_schema as CN
import centrais_cred as CRED
import cenprot_pendencias as PEND

SENHA = "Senha#12345"
AGORA = "2026-09-02T10:00:00"
CHAVE = "21987650141243301260417"
PROTOCOLO = "2604170001"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _sessao(cg_casa, papel: str = "ADMIN"):
    app = cg_casa['app']
    banco = cg_casa['banco']
    dados = cg_casa['dados']
    bd = cg_casa['db']
    bd.create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS", SENHA, papel)
    bd.set_settings({"ibge_uf": "21", "ibge_municipio": "98765",
                     "ibge_cartorio": "01", "ibge_distrito": "05"})
    # O PROTESTO É DO OFICIAL desde 01/09/2026, e o alcance de fábrica é
    # ADMIN. Estes testes exercitam as telas dele e por isso o abrem **a
    # vista**, para que o de papel USER prove a guarda de verdade.
    bd.set_settings({"modulo_protesto_alcance": "TODOS"})
    c = app.test_client()
    c.post("/login",
           data={"username": "tabeliao", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {"app": app, "c": c, "banco": banco}


@pytest.fixture()
def s(cg_casa):
    return _sessao(cg_casa)


@pytest.fixture()
def sem_credencial(monkeypatch, tmp_path):
    """A pasta das credenciais das Centrais apontada para uma pasta VAZIA.

    **O TESTE NÃO PODE DEPENDER DO DISCO DE QUEM O RODA.** Ele diz «sem
    credencial a tela avisa, e a recusa é no balcão» — e isso só é verdade
    onde não há credencial gravada. Nesta máquina a CENPROT **tem**
    `cenprot.cred` desde que o oficial a cadastrou (medido: 68 bytes em
    18/09/2026), e ali os dois testes ficavam vermelhos **sem defeito
    nenhum**: com a credencial no lugar o aviso some, que é o comportamento
    certo — só não era o caminho que o teste queria percorrer.

    Apontar `pasta_de_dados` para uma pasta vazia é mais fiel que forçar
    `tem()` a devolver falso: **toda** leitura de credencial daquela rodada
    passa a ver ausência, e o teste exercita a mesma coisa que a instalação
    limpa exercita. É a forma do `sem_chave` de `test_resolve_intimacao.py`
    e do `sem_credencial` de `test_cra21_web.py`.
    """
    monkeypatch.setattr(CRED, "pasta_de_dados", lambda: tmp_path)


def _con(s) -> sqlite3.Connection:
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    return con


# O AMBIENTE PADRÃO DA PENDÊNCIA DE MESA É PRODUÇÃO desde 14/10/2026 («agora
# é tudo produção»): a tela só lista e só decide as de produção. Até 13/10 o
# padrão daqui era «HOMOLOGACAO».
def pendencia(s, *, especie=CN.ANUENCIA, codigo="1",
              ambiente="PRODUCAO", titulo_id=None, teor=None,
              situacao=CN.PENDENTE) -> int:
    corpo = teor or {"cd_anuencia": 1, "nm_chave": CHAVE,
                     "nm_nr_protocolo": PROTOCOLO,
                     "nm_devedor": "FULANO DA SILVA",
                     "nm_nr_titulo": "00123", "dt_protocolo": "2026-04-17",
                     "dt_emissao": "2026-03-01", "vl_protesto": 200.95,
                     "nm_nr_documento_devedor": "00000000000",
                     "nm_nr_documento_credor": "00000010000127",
                     "dt_solicitacao_anuencia": "2026-04-20"}
    con = _con(s)
    with con:
        cur = con.execute(
            """INSERT INTO cn_pendencias
                   (especie, ambiente, codigo, chave, titulo_id, teor,
                    resumo, baixada_em, baixada_por, situacao)
               VALUES (?,?,?,?,?,?,?,?,'teste',?)""",
            (especie, ambiente, codigo, CHAVE, titulo_id,
             json.dumps(corpo, ensure_ascii=False),
             "FULANO DA SILVA · 00123", AGORA, situacao))
        pid = int(cur.lastrowid)
    con.close()
    return pid


# ------------------------------------------- as telas existem, e no menu


def test_a_tela_da_fila_abre(s):
    r = s["c"].get("/protesto/cenprot/pendencias")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    for nome in CN.NOME_DA_ESPECIE.values():
        assert nome in html, f"«{nome}» não aparece no quadro"


def test_a_fila_esta_no_menu(s):
    """**O defeito das seis vezes.** Sem link no menu, a tela existe e ninguém
    a acha — e o buraco só aparece meses depois no balcão."""
    html = s["c"].get("/protesto/cenprot/pendencias").get_data(as_text=True)
    assert "/protesto/cenprot/pendencias" in html
    painel = s["c"].get("/protesto").get_data(as_text=True)
    assert "Pendências da CENPROT" in painel, (
        "o menu do Protesto não oferece a tela nova")


def test_toda_funcao_de_transporte_tem_chamador():
    """**O varredor das seis vezes, aplicado a este módulo.**

    Ele me pegou com três: `renegociacoes` (apagada, porque o roteiro não a
    pede), `arquivos_da_anuencia` e `enviar_custas` — as duas ganharam botão.
    Sem este teste elas ficariam prontas e testadas, esperando alguém religá-las
    sem saber por que existiam.
    """
    fonte = (RAIZ / "cenprot_api.py").read_text(encoding="utf-8")
    arvore = ast.parse(fonte)
    publicas = {n.name for n in arvore.body
                if isinstance(n, ast.FunctionDef)
                and not n.name.startswith("_")}

    # **O MEU PRIMEIRO VARREDOR CONTAVA SO CHAMADOR DE FORA**, e acusou tres
    # que o proprio modulo usa — `token`, `base_do_ambiente` e
    # `esquecer_token`. **Varredor que acusa o certo e varredor que ninguem le
    # na terceira vez.** O que se procura e «funcao que NINGUEM chama», e o
    # «ninguem» inclui o modulo dela.
    usadas = {no.func.id if isinstance(no.func, ast.Name) else no.func.attr
              for no in ast.walk(arvore)
              if isinstance(no, ast.Call)
              and isinstance(no.func, (ast.Name, ast.Attribute))}
    for arq in RAIZ.glob("*.py"):
        if arq.name == "cenprot_api.py":
            continue
        texto = arq.read_text(encoding="utf-8", errors="replace")
        # chamada OU referencia: `API.anuencias(` e `API.anuencias,` valem
        usadas |= {n for n in publicas if ("API." + n) in texto}
    assert publicas - usadas == set(), (
        f"funcoes de transporte sem chamador: {sorted(publicas - usadas)}")


# ------------------------------------------- o que a tela diz


def test_a_tela_so_tem_producao(s):
    """**CONTRATO MUDADO EM 14/10/2026** — ordem do oficial: «tire a opção de
    funcionar na homologação, agora é tudo produção». Este teste se chamava
    `test_a_homologacao_grita_na_tela` e cobrava o aviso de homologação
    quando a tela era aberta nela. Agora a tela não tem seletor, um endereço
    antigo com `?ambiente=HOMOLOGACAO` abre a produção, e a pendência de
    homologação que ficou no banco não aparece na lista nem se decide."""
    pendencia(s, codigo="7", ambiente="HOMOLOGACAO")
    for endereco in ("/protesto/cenprot/pendencias",
                     "/protesto/cenprot/pendencias?ambiente=HOMOLOGACAO"):
        html = s["c"].get(endereco).get_data(as_text=True)
        assert "PRODUÇÃO" in html
        assert "não se desfaz" in html
        assert 'name="ambiente"' not in html.split("Trazer da Central")[1] \
            .split("</form>")[0], "o seletor de ambiente voltou"
        assert 'value="HOMOLOGACAO"' not in html
        assert "FULANO DA SILVA · 00123" not in html, (
            "a pendência de homologação apareceu na lista de produção")


def test_a_pendencia_de_homologacao_nao_se_decide(s):
    """Ela fica no banco como histórico; decidi-la deixaria uma resposta
    esperando um envio que não existe mais."""
    pid = pendencia(s, codigo="8", ambiente="HOMOLOGACAO")
    ficha = " ".join(s["c"].get(f"/protesto/cenprot/pendencias/{pid}")
                     .get_data(as_text=True).split())
    assert "guardado só como histórico" in ficha
    con = _con(s)
    with pytest.raises(CRED.CredencialError) as e:
        with con:
            PEND.decidir(con, pid, decisao={"cd_anuencia": 8,
                                            "ic_aprovado": True},
                         quem="t", agora=AGORA)
    assert "só em produção" in str(e.value)


def test_a_tela_avisa_quando_falta_a_credencial(s, sem_credencial):
    """Sem isto, a primeira notícia seria uma lista vazia — que o escrevente
    leria como «a Central está em dia»."""
    html = s["c"].get("/protesto/cenprot/pendencias").get_data(as_text=True)
    assert "ainda não foi\n  informada" in html or "ainda não foi" in html
    assert "fora do banco" in html


def test_zero_nao_quer_dizer_em_dia(s):
    """Um zero pode ser «nada chegou» ou «ainda não baixei», e a tela diz
    isso — em vez de deixar quem lê tirar a conclusão errada sozinho."""
    html = s["c"].get("/protesto/cenprot/pendencias").get_data(as_text=True)
    assert "nunca se baixou" in html
    assert "não quer dizer" in html


def test_todo_formulario_manda_o_csrf(s):
    """Dez formulários da casa não mandavam, e o balcão levou «bad request
    error». Os testes de rota montam o POST com o token na mão — este olha o
    HTML."""
    for endereco in ("/protesto/cenprot/pendencias",):
        html = s["c"].get(endereco).get_data(as_text=True)
        formularios = re.findall(r"<form[^>]*method=[\"']post[\"'].*?</form>",
                                 html, re.DOTALL | re.IGNORECASE)
        assert formularios, f"{endereco} não tem formulário de POST"
        for f in formularios:
            assert "csrf_token" in f, f"formulário sem token em {endereco}"
    pid = pendencia(s)
    html = s["c"].get(f"/protesto/cenprot/pendencias/{pid}").get_data(
        as_text=True)
    formularios = re.findall(r"<form[^>]*method=[\"']post[\"'].*?</form>",
                             html, re.DOTALL | re.IGNORECASE)
    assert len(formularios) >= 2, "a ficha tem de ter decidir e dispensar"
    for f in formularios:
        assert "csrf_token" in f


def test_a_lista_vazia_diz_o_que_fazer(s):
    """**Lista vazia que só mostra nada faz o operador achar que quebrou** — e
    aqui é pior: ele acharia que a Central está vazia."""
    html = s["c"].get("/protesto/cenprot/pendencias").get_data(as_text=True)
    assert "lista vazia não quer dizer" in html


# ------------------------------------------- a ficha


def test_a_ficha_mostra_o_teor_congelado(s):
    pid = pendencia(s)
    html = s["c"].get(f"/protesto/cenprot/pendencias/{pid}").get_data(
        as_text=True)
    assert "FULANO DA SILVA" in html
    assert CHAVE in html
    assert "congelado" in html


def test_a_pendencia_que_nao_casou_avisa_na_ficha(s):
    """**Responder sem título é responder sobre o que a casa não tem.**"""
    pid = pendencia(s, titulo_id=None)
    html = s["c"].get(f"/protesto/cenprot/pendencias/{pid}").get_data(
        as_text=True)
    assert "não casou com título nenhum" in html


def test_a_decisao_judicial_nao_oferece_botao_de_responder(s):
    """O sistema não julga ordem de juiz — e a tela não pode sugerir que julga."""
    pid = pendencia(s, especie=CN.DECISAO_JUDICIAL, codigo=CHAVE)
    html = s["c"].get(f"/protesto/cenprot/pendencias/{pid}").get_data(
        as_text=True)
    assert "não se responde por esta tela" in html
    assert "Gravar a decisão" not in html
    assert "art. 17" in html


def test_o_cancelamento_diz_que_NAO_cancela_o_protesto_aqui(s):
    """O ato se lavra na ficha do título, com hipótese e fundamento — e a tela
    que informa a Central não pode parecer a que cancela."""
    pid = pendencia(s, especie=CN.CANCELAMENTO, codigo="1000001",
                    teor={"nr_pedido": 1000001, "nm_chave": CHAVE})
    html = s["c"].get(f"/protesto/cenprot/pendencias/{pid}").get_data(
        as_text=True)
    assert "não cancela o protesto aqui" in html
    assert "ficha do título" in html
    assert "nr_pedido" in html, "a coisa a conferir tem de estar à vista"


def test_a_pendencia_que_nao_existe_nao_da_500(s):
    r = s["c"].get("/protesto/cenprot/pendencias/9999",
                   follow_redirects=True)
    assert r.status_code == 200
    assert "não existe" in r.get_data(as_text=True)


# ------------------------------------------- decidir e dispensar pela tela


def test_decidir_grava_e_diz_que_nao_subiu(s):
    """**Decidir e enviar são dois botões**, e a tela tem de dizer isso — senão
    o escrevente vai embora achando que a Central já sabe."""
    pid = pendencia(s)
    html = s["c"].get(f"/protesto/cenprot/pendencias/{pid}").get_data(
        as_text=True)
    r = s["c"].post(f"/protesto/cenprot/pendencias/{pid}/decidir",
                    data={"csrf_token": _token(html), "decisao": "aprovar",
                          "vl_custas": "82,64"},
                    follow_redirects=True)
    assert r.status_code == 200
    assert "ainda não subiu" in r.get_data(as_text=True)
    con = _con(s)
    linha = con.execute(
        "SELECT situacao, decisao, enviada_em FROM cn_pendencias").fetchone()
    con.close()
    assert linha["situacao"] == CN.DECIDIDA
    assert linha["enviada_em"] is None
    decisao = json.loads(linha["decisao"])
    assert decisao["ic_aprovado"] is True
    assert decisao["vl_custas"] == 82.64
    # **OS DOZE CAMPOS SAEM DO TEOR CONGELADO**, e não de um formulário que
    # alguém redigitaria — redigitar é como o dado da casa passa a discordar
    # do da Central.
    assert decisao["nm_chave"] == CHAVE
    assert decisao["nm_devedor"] == "FULANO DA SILVA"


def test_recusar_sem_motivo_volta_com_a_frase_e_nao_com_500(s):
    """Erro de regra é `ValueError` com mensagem de balcão, e a rota o trata
    com `flash(..., 'danger')` — não é HTTP 500."""
    pid = pendencia(s)
    html = s["c"].get(f"/protesto/cenprot/pendencias/{pid}").get_data(
        as_text=True)
    r = s["c"].post(f"/protesto/cenprot/pendencias/{pid}/decidir",
                    data={"csrf_token": _token(html), "decisao": "recusar",
                          "motivo_recusa": ""},
                    follow_redirects=True)
    assert r.status_code == 200
    assert "motivo" in r.get_data(as_text=True)


def test_dispensar_sem_motivo_volta_com_a_frase(s):
    pid = pendencia(s)
    html = s["c"].get(f"/protesto/cenprot/pendencias/{pid}").get_data(
        as_text=True)
    r = s["c"].post(f"/protesto/cenprot/pendencias/{pid}/dispensar",
                    data={"csrf_token": _token(html), "motivo": "  "},
                    follow_redirects=True)
    assert r.status_code == 200
    assert "por que" in r.get_data(as_text=True)


def test_enviar_sem_nada_decidido_volta_com_a_frase(s):
    html = s["c"].get("/protesto/cenprot/pendencias").get_data(as_text=True)
    r = s["c"].post("/protesto/cenprot/pendencias/enviar",
                    data={"csrf_token": _token(html), "especie": CN.ANUENCIA},
                    follow_redirects=True)
    assert r.status_code == 200
    assert "Decida na lista" in r.get_data(as_text=True)


def test_baixar_sem_credencial_volta_com_a_frase_e_nao_com_500(s,
                                                                sem_credencial):
    """**A recusa é no balcão, e não na rede.** Sem credencial a chamada nem
    sai — e a frase diz onde informá-la."""
    html = s["c"].get("/protesto/cenprot/pendencias").get_data(as_text=True)
    r = s["c"].post("/protesto/cenprot/pendencias/baixar",
                    data={"csrf_token": _token(html), "especie": CN.ANUENCIA,
                          "ambiente": "HOMOLOGACAO"},
                    follow_redirects=True)
    assert r.status_code == 200
    texto = r.get_data(as_text=True)
    assert "não foi" in texto and "informada" in texto


def test_a_baixa_do_cancelamento_exige_o_periodo(s):
    """O contrato marca as duas datas como obrigatórias, e a recusa é aqui —
    antes de gastar uma viagem até a Central."""
    html = s["c"].get("/protesto/cenprot/pendencias").get_data(as_text=True)
    r = s["c"].post("/protesto/cenprot/pendencias/baixar",
                    data={"csrf_token": _token(html),
                          "especie": CN.CANCELAMENTO, "inicio": "", "fim": ""},
                    follow_redirects=True)
    assert r.status_code == 200
    texto = r.get_data(as_text=True)
    assert "período" in texto or "informada" in texto


# ------------------------------------------- quem pode o quê


def test_enviar_tambem_e_do_balcao(cg_casa):
    """21/10/2026 — CONTRATO MUDADO POR ORDEM DO OFICIAL: «dar acesso às
    escreventes operarem todo o protesto, em especial operar as API, CRA etc.».
    Até aqui este teste se chamava `test_enviar_NAO_e_do_balcao` e cobrava
    que o escrevente NÃO enviasse à CENPROT; agora cobra que envia — a rota
    chega ao domínio (que recusa o lote vazio com a frase dele) em vez de 403.
    A auxiliar, que tem o mesmo papel, fica de fora pela FUNÇÃO
    (`test_modulo_alcance`)."""
    s = _sessao(cg_casa, papel="USER")
    html = s["c"].get("/protesto/cenprot/pendencias").get_data(as_text=True)
    assert "Baixar da CENPROT" in html, "o balcão pode BAIXAR"
    for endereco in ("/protesto/cenprot/pendencias/enviar",
                     "/protesto/cenprot/emolumentos/enviar"):
        r = s["c"].post(endereco, data={"csrf_token": _token(html)})
        assert r.status_code != 403, f"{endereco}: o balcão continua barrado"


def test_a_guarda_do_alcance_alcanca_as_telas_novas(cg_casa):
    """**A guarda é no servidor, e não no menu.** A régua de «qual módulo é
    esta tela» é a de `modulos.py`, e ela decide pelo prefixo do endpoint —
    rota que fugisse do prefixo ficaria aberta no dia em que o oficial
    fechasse o Protesto."""
    import modulos as MOD
    for endpoint in ("protesto_pendencias", "protesto_pendencia",
                     "protesto_pendencias_baixar",
                     "protesto_pendencias_enviar",
                     "protesto_pendencia_decidir",
                     "protesto_pendencia_dispensar",
                     "protesto_pendencia_arquivos",
                     "protesto_cenprot_testar",
                     "protesto_cenprot_emolumentos_enviar"):
        assert MOD.modulo_da_tela(endpoint) == "PROTESTO", (
            f"«{endpoint}» ficou fora do alcance do Protesto")

    bd = cg_casa['db']
    bd.create_user("escrevente", "ESCREVENTE", SENHA, "USER")
    bd.set_settings({"modulo_protesto_alcance": "ADMIN"})
    c = cg_casa['app'].test_client()
    c.post("/login",
           data={"username": "escrevente", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    r = c.get("/protesto/cenprot/pendencias", follow_redirects=True)
    assert "CENPROT — o que chegou" not in r.get_data(as_text=True), (
        "o escrevente entrou numa tela do Protesto fechado para ele")


# ------------------------------------------- o roteiro não mente


def test_o_roteiro_declara_as_telas_que_passaram_a_existir():
    """**Buraco fechado que continua declarado é o carimbo que mente.** Estes
    passos diziam «no site da CENPROT» com `tela: None`, e três deles não
    tinham tela nenhuma. Agora têm."""
    import protesto_roteiro as R
    por_tela = {p["passo"]: p.get("tela") for p in R.ROTEIRO_DA_CENPROT}
    assert por_tela["Recebimento dos pedidos de anuencia"] == (
        "protesto_pendencias")
    assert por_tela["Recebimento de pedido de cancelamento"] == (
        "protesto_pendencias")
    assert por_tela["Recebimento de remessa (menu Gestao de Pedidos)"] == (
        "protesto_pendencias")
    c = R.quantos_o_sistema_faz()
    assert c["cenprot_com_tela"] >= 6, (
        "a cobertura da CENPROT caiu — se uma tela saiu, o roteiro tem de "
        "voltar a declarar o buraco")


def test_toda_tela_que_o_roteiro_cita_existe(cg_app):
    """Roteiro que aponta para tela inexistente é a promessa com cara de
    prova — o defeito do `ri_nota`, que só aparecia no caminho de falha."""
    import protesto_roteiro as R
    app = cg_app
    existentes = {r.endpoint for r in app.url_map.iter_rules()}
    for passo in list(R.ROTEIRO_DA_CRA) + list(R.ROTEIRO_DA_CENPROT):
        tela = passo.get("tela")
        if tela:
            assert tela in existentes, (
                f"o roteiro aponta para «{tela}», que não é rota nenhuma")


# ------------------------------------------- a régua do domínio


def test_a_tela_nao_repete_a_regra_do_dominio():
    """A ficha só **oferece** o que cabe; quem **recusa** é o domínio. Repetir
    a regra nos dois lugares é como eles divergem."""
    fonte = (RAIZ / "cenprot_web.py").read_text(encoding="utf-8")
    for proibido in ("CAMPOS_OBRIGATORIOS", "raise API.CenprotError"):
        if proibido == "CAMPOS_OBRIGATORIOS":
            # A tela PODE ler a lista para saber quais campos copiar do teor;
            # o que ela não pode é CONFERIR — a conferência é do transporte.
            continue
        assert proibido not in fonte
    assert "def _decisao_do_formulario" in fonte
    assert "A CONFERÊNCIA DE VERDADE É NO DOMÍNIO E NO TRANSPORTE" in fonte


def test_os_papeis_estao_declarados_e_nao_espalhados():
    """Duas listas de papéis divergem no primeiro conserto."""
    import cenprot_web as W
    assert W.QUEM_OPERA == ("ADMIN", "MANAGER", "USER")
    # 21/10/2026: era ("ADMIN", "MANAGER") e `<` (envio mais fechado que a
    # consulta); por ordem do oficial o balcão também envia.
    assert W.QUEM_ENVIA == ("ADMIN", "MANAGER", "USER")
    assert set(W.QUEM_ENVIA) <= set(W.QUEM_OPERA)


# ------------------------------------------- a anuência na forma da produção

#: A forma em que a produção devolveu as 3 anuências pendentes em 13/10/2026
#: (`GET /v2/anuencias`) — os campos são os reais, os VALORES são fictícios.
ANUENCIA_COMO_A_PRODUCAO_MANDA = {"dados_anuencia": {
    "cd_anuencia": "99000001", "cd_status": "8", "nm_chave": "2" * 23,
    "ic_aprovado": True, "nm_nr_protocolo": "2501070004",
    "dt_protocolo": "2025-01-07", "nm_nr_documento_devedor": "00000000000",
    "nm_devedor": "DEVEDOR FICTICIO", "vl_protesto": "100.00",
    "dt_solicitacao_anuencia": "2026-10-08 21:02:17.000",
    "nm_nr_titulo": "123/1", "nm_nr_documento_credor": "00000042000122",
    "dt_emissao": "2024-12-01", "nm_assinatura": "x",
    "nm_assinatura_validade": "x",
    "dados_cartorio": {"cd_cartorio": "1", "nm_nome": "CARTORIO"},
    "dados_solicitante": {"nm_nome": "SOLICITANTE", "nr_telefone": None},
}}


def test_a_resposta_da_anuencia_le_o_teor_aninhado(monkeypatch):
    """Lendo só o primeiro nível, o corpo saía sem os onze campos que a
    CENPROT exige de volta, e nenhuma anuência se respondia pela tela."""
    from flask import Flask

    import cenprot_api as API
    import cenprot_web as WEB

    p = {"especie": CN.ANUENCIA, "codigo": "99000001",
         "teor_aberto": ANUENCIA_COMO_A_PRODUCAO_MANDA}
    with Flask(__name__).test_request_context(
            method="POST", data={"decisao": "aprovar", "vl_custas": "123,45"}):
        corpo = WEB._decisao_do_formulario(p)
    for campo, _ in API.CAMPOS_OBRIGATORIOS_DA_ANUENCIA:
        assert campo in corpo, campo
    assert corpo["nm_chave"] == "2" * 23 and corpo["ic_aprovado"] is True
    assert corpo["vl_custas"] is not None

    enviados = []
    monkeypatch.setattr(API, "_escrever",
                        lambda amb, chave, c, o_que, **k: enviados.append(c) or {})
    API.processar_anuencia([corpo], CRED.HOMOLOGACAO)   # a conferência passa
    assert enviados and enviados[0][0]["cd_anuencia"] == "99000001"


def test_a_anuencia_vem_cotada_pela_custa_de_cancelamento(s, monkeypatch):
    """Ordem do oficial em 13/10/2026: as anuências «são respondidas conforme
    tabela de emolumentos, cota cada uma». O valor vem da CUSTA DE
    CANCELAMENTO da casa (e não da retirada), como sugestão que se confere."""
    import cenprot_pendencias as PEND

    chamadas = []

    def cotacao(con, p, *, hoje):
        chamadas.append(p["especie"])
        return {"centavos": 40767, "reais": "407.67",
                "motivo": "somado da tabela desta casa"}

    monkeypatch.setattr(PEND, "custa_de_cancelamento_sugerida", cotacao)
    monkeypatch.setattr(PEND, "retirada_sugerida",
                        lambda *a, **k: pytest.fail("anuência não é retirada"))
    pid = pendencia(s)
    html = s["c"].get(f"/protesto/cenprot/pendencias/{pid}").get_data(
        as_text=True)
    assert chamadas == [CN.ANUENCIA]
    assert re.search(r'name="vl_custas"\s+value="407\.67"', html)
    assert "a custa de cancelamento" in html


def test_a_anuencia_sem_titulo_nao_inventa_cotacao(s):
    pid = pendencia(s, titulo_id=None)
    html = " ".join(s["c"].get(f"/protesto/cenprot/pendencias/{pid}")
                    .get_data(as_text=True).split())
    assert 'name="vl_custas" value=""' in html
    assert "O sistema não sugeriu valor" in html


# ------------------------------- o caminho do contrato (13/10/2026)

def _titulo_protestado(s, situacao="PROTESTADO") -> int:
    con = _con(s)
    with con:
        cur = con.execute(
            """INSERT INTO pt_titulos
                   (especie, numero_titulo, chave_cenprot, protocolo, situacao,
                    valor_centavos, origem, origem_chave, criado_em)
               VALUES ('DMI', '00123', ?, ?, ?, 94973, 'CRA', 'cam-1', ?)""",
            (CHAVE, PROTOCOLO, situacao, AGORA))
        tid = int(cur.lastrowid)
    con.close()
    return tid


PEDIDO_DE_CANCELAMENTO = {
    "dados_pedido": {"nr_pedido": 1000001, "nm_chave": CHAVE},
    "anuencia": {"nr_anuencia": 28655422, "status": "Aprovado",
                 "vl_emolumentos_cancelamento": 319.54},
}


def test_nao_se_informa_cancelamento_antes_de_lavrar(s):
    """Ordem do oficial: «vamos seguir o caminho do contrato». Informar a
    Central antes de lavrar faria ela dar por cancelado o que o livro desta
    casa ainda tem de pé."""
    tid = _titulo_protestado(s)
    pid = pendencia(s, especie=CN.CANCELAMENTO, codigo="1000001",
                    titulo_id=tid, teor=PEDIDO_DE_CANCELAMENTO)
    html = s["c"].post(f"/protesto/cenprot/pendencias/{pid}/decidir",
                       data={"csrf_token": _token(s["c"].get(
                           f"/protesto/cenprot/pendencias/{pid}").get_data(
                               as_text=True))},
                       follow_redirects=True).get_data(as_text=True)
    assert "ainda está PROTESTADO" in html
    assert _con(s).execute("SELECT situacao FROM cn_pendencias WHERE id=?",
                           (pid,)).fetchone()[0] == CN.PENDENTE

    con = _con(s)
    with con:
        con.execute("UPDATE pt_titulos SET situacao='CANCELADO' WHERE id=?", (tid,))
    con.close()
    s["c"].post(f"/protesto/cenprot/pendencias/{pid}/decidir",
                data={"csrf_token": _token(s["c"].get(
                    f"/protesto/cenprot/pendencias/{pid}").get_data(as_text=True))})
    assert _con(s).execute("SELECT situacao FROM cn_pendencias WHERE id=?",
                           (pid,)).fetchone()[0] == CN.DECIDIDA


def test_o_pedido_mostra_a_anuencia_os_emolumentos_e_leva_a_ficha(s):
    tid = _titulo_protestado(s)
    pid = pendencia(s, especie=CN.CANCELAMENTO, codigo="1000001",
                    titulo_id=tid, teor=PEDIDO_DE_CANCELAMENTO)
    html = s["c"].get(f"/protesto/cenprot/pendencias/{pid}").get_data(as_text=True)
    assert "28655422" in html and "R$ 319.54" in html
    assert "quem pede é quem paga" in html
    link = re.search(r'href="(/protesto/%d\?[^"]+)"' % tid, html)
    assert link and "hipotese=ANUENCIA_CREDOR" in link.group(1)

    ficha = s["c"].get(link.group(1).replace("&amp;", "&")).get_data(as_text=True)
    assert re.search(r'value="ANUENCIA_CREDOR"\s+selected', ficha)
    assert "anuência nº 28655422 do credor" in ficha


# ------------------- o pedido de protesto vira título (27/10/2026)
#
# Pedido do oficial: «chegou um título pela CENPROT. nossa integração funciona
# para receber direto pelo sistema?». O teor tem a forma do contrato
# (`/pedidos/consulta`, swagger 2.1.0), com dados fictícios.

PDF_DO_PEDIDO = b"%PDF-1.4\n% pedido de teste\n%%EOF\n"


def teor_do_pedido(numero=3600001) -> dict:
    import base64
    return {
        "dados_pedido": {
            "cd_pedido_protesto": numero, "nr_cartorio": "01",
            "dt_pedido": "2026-10-27", "ds_status": "Aguardando protocolo",
            "tipo_protesto": "Comum", "aceite": "Não",
            "fins_falimentares": "Não", "tipo_endosso": "Sem Endosso",
            "dados_titulo": {"nm_nr_titulo": "000777/1",
                             "nm_nosso_numero": "000777/1",
                             "vl_titulo": 1234.5, "vl_saldo": 1234.5,
                             "dt_vencimento": "2026-09-30",
                             "dt_emissao": "2026-08-30",
                             "ds_especie": "Duplicata Mercantil por Indicação",
                             "sg_especie": "DMI"}},
        "devedor": {"nm_devedor": "FULANO DE TAL",
                    "nm_nr_identificacao": "000.000.001-91",
                    "nm_endereco": "Rua Exemplo, 100", "nm_nr_cep": "65000-000",
                    "nm_bairro": "Centro", "nm_cidade": "Cidade Exemplo",
                    "sg_uf": "MA"},
        "dados_cedente": {"nm_cedente": "EMPRESA CEDENTE LTDA",
                          "nm_nr_documento": "00.000.010/0001-27",
                          "nm_endereco": "Av. Exemplo, 1000",
                          "nm_nr_cep": "65000-001", "nm_bairro": "Centro",
                          "nm_cidade": "Cidade Vizinha", "sg_uf": "MA"},
        "dados_sacador": {"nm_sacador": "SACADOR EXEMPLO LTDA",
                          "nm_nr_documento": "00.000.011/0001-71",
                          "nm_endereco": "Rua Sacador, 50",
                          "nm_cidade": "Cidade Vizinha", "sg_uf": "MA"},
        "dados_solicitante": {"nm_nome": "EMPRESA CEDENTE LTDA",
                              "nm_nr_documento": "00.000.010/0001-27",
                              "ds_endereco_solicitante": "Av. Exemplo, 1000"},
        "arquivos": {"pedido_pdf_b64": base64.b64encode(PDF_DO_PEDIDO).decode(),
                     "anexo_b64": None},
    }


def _pedido(s, cg_casa, numero=3600001) -> int:
    cg_casa["db"].set_settings({"ri_cidade": "Cidade Exemplo"})
    return pendencia(s, especie=CN.PEDIDO_PROTESTO, codigo=str(numero),
                     teor=teor_do_pedido(numero))


def _dar_entrada(s, pid) -> str:
    ficha = s["c"].get(f"/protesto/cenprot/pendencias/{pid}").get_data(
        as_text=True)
    return s["c"].post(f"/protesto/cenprot/pendencias/{pid}/titulo",
                       data={"csrf_token": _token(ficha)},
                       follow_redirects=True).get_data(as_text=True)


def test_o_pedido_sem_titulo_oferece_dar_entrada(s, cg_casa):
    pid = _pedido(s, cg_casa)
    html = s["c"].get(f"/protesto/cenprot/pendencias/{pid}").get_data(
        as_text=True)
    assert "Dar entrada no título" in html
    assert "não casou com título nenhum" not in html


def test_o_pedido_de_protesto_vira_titulo_recebido(s, cg_casa):
    pid = _pedido(s, cg_casa)
    html = _dar_entrada(s, pid)
    assert "O título entrou (RECEBIDO)" in html
    con = _con(s)
    t = con.execute("SELECT * FROM pt_titulos WHERE origem_chave=?",
                    ("CENPROT-PEDIDO:3600001",)).fetchone()
    assert t is not None
    assert t["origem"] == "CENPROT" and t["situacao"] == "RECEBIDO"
    assert t["apresentante_codigo"] == "TAB" and t["motivo_protesto"] == "1"
    assert t["praca_protesto"] == "CIDADE EXEMPLO"
    assert t["especie"] == "DMI" and t["numero_titulo"] == "000777/1"
    assert t["valor_centavos"] == 123450 and t["tipo_endosso"] == "S"
    assert t["aceite"] == "N" and t["tipo_protesto"] == "C"
    assert t["cedente_nome"] == "EMPRESA CEDENTE LTDA"
    d = con.execute("SELECT * FROM pt_devedores WHERE titulo_id=?",
                    (t["id"],)).fetchall()
    assert len(d) == 1 and d[0]["documento_numero"] == "00000000191"
    assert con.execute("SELECT titulo_id FROM cn_pendencias WHERE id=?",
                       (pid,)).fetchone()[0] == t["id"]
    anexos = con.execute("SELECT original_name FROM attachments WHERE "
                         "entity_type='PT_TITULO' AND entity_id=?",
                         (t["id"],)).fetchall()
    assert [a[0] for a in anexos] == ["cenprot-pedido-3600001-pedido.pdf"]


def test_o_pedido_nao_vira_dois_titulos(s, cg_casa):
    pid = _pedido(s, cg_casa)
    _dar_entrada(s, pid)
    html = s["c"].post(f"/protesto/cenprot/pendencias/{pid}/titulo",
                       data={"csrf_token": _token(s["c"].get(
                           f"/protesto/cenprot/pendencias/{pid}").get_data(
                               as_text=True))},
                       follow_redirects=True).get_data(as_text=True)
    assert "já está amarrado ao título" in html
    assert _con(s).execute(
        "SELECT COUNT(*) FROM pt_titulos WHERE origem_chave=?",
        ("CENPROT-PEDIDO:3600001",)).fetchone()[0] == 1


def test_titulo_parecido_ja_na_casa_pede_conferencia(s, cg_casa):
    # 27/10/2026: o título que entrou pelo E-Ofício tem outra chave de origem,
    # e o botão criava um segundo título para a mesma dívida. Outro pedido com
    # o mesmo número e o mesmo devedor é recusado até alguém confirmar.
    _dar_entrada(s, _pedido(s, cg_casa))
    outro = _pedido(s, cg_casa, numero=3600002)
    html = _dar_entrada(s, outro)
    assert "mesmo número e o mesmo devedor" in html
    assert _con(s).execute("SELECT COUNT(*) FROM pt_titulos WHERE numero_titulo=?",
                           ("000777/1",)).fetchone()[0] == 1
    ficha = s["c"].get(f"/protesto/cenprot/pendencias/{outro}").get_data(as_text=True)
    html = s["c"].post(f"/protesto/cenprot/pendencias/{outro}/titulo",
                       data={"csrf_token": _token(ficha), "mesmo_assim": "1"},
                       follow_redirects=True).get_data(as_text=True)
    assert "O título entrou (RECEBIDO)" in html


def test_protocolo_fora_da_forma_da_casa_nao_entra(s, cg_casa):
    # O exemplo do contrato traz «0000000001»: fora de AAMMDD+sequencial o aviso
    # de intimação recusaria sair. O protocolo nasce no apontamento.
    cg_casa["db"].set_settings({"ri_cidade": "Cidade Exemplo"})
    teor = teor_do_pedido(3600003)
    teor["dados_pedido"]["nm_nr_protocolo"] = "0000000001"
    pid = pendencia(s, especie=CN.PEDIDO_PROTESTO, codigo="3600003", teor=teor)
    _dar_entrada(s, pid)
    t = _con(s).execute("SELECT protocolo FROM pt_titulos WHERE origem_chave=?",
                        ("CENPROT-PEDIDO:3600003",)).fetchone()
    assert t is not None and not t["protocolo"]


def test_so_o_pedido_de_protesto_vira_titulo(s, cg_casa):
    pid = pendencia(s)                       # uma anuência
    html = s["c"].get(f"/protesto/cenprot/pendencias/{pid}").get_data(
        as_text=True)
    assert "Dar entrada no título" not in html
    html = s["c"].post(f"/protesto/cenprot/pendencias/{pid}/titulo",
                       data={"csrf_token": _token(html)},
                       follow_redirects=True).get_data(as_text=True)
    assert "Só o pedido de protesto vira título" in html


def test_o_xml_da_cenprot_le_cedente_e_sacador_do_pedido(s, cg_casa):
    """Sem remessa e sem E-Ofício, o XML recusava: «sem ele não se sabe quem
    é o cedente e quem é o sacador». Agora eles vêm do pedido congelado."""
    import protesto_cenprot_xml as X
    pid = _pedido(s, cg_casa)
    _dar_entrada(s, pid)
    con = _con(s)
    t = dict(con.execute("SELECT * FROM pt_titulos WHERE origem_chave=?",
                         ("CENPROT-PEDIDO:3600001",)).fetchone())
    reg = X.registro_da_cra(con, t)
    assert reg["cedente_nome"] == "EMPRESA CEDENTE LTDA"
    assert reg["cedente_nome_2"] == "SACADOR EXEMPLO LTDA"
    assert reg["cedente_documento"] == "00000011000171"
    cedente, sacador, endosso = X._cedente_e_sacador(reg)
    assert endosso == "H" and sacador["nome"] == "SACADOR EXEMPLO LTDA"
