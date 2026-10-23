"""Auditoria de segurança LS03 — A IA E OS SEGREDOS: o que o LX13 fechou.

A auditoria (`relatorios/LS03.md`) relatou e não consertou; o LX13 (19/10/2026)
aplicou as propostas. Aqui moram as provas dos itens que não têm arquivo de
teste na lista do lote:

    - M5: o teste do robô sobe o pedido MASCARADO, e o registro dos testes
      guarda só a forma mascarada, por trinta dias;
    - M6: a leitura do Registro Civil (DNV e DO inteiras) é de quem lavra, e o
      balcão abre só a que é dele — o número sequencial não basta;
    - M7: a triagem dos anexos da revisão vê as primeiras páginas, e o que ela
      não viu não se descarta pela capa;
    - M12: a leitura do RCPN tem teto de páginas, e acima dele nada sobe;
    - B5: revisão prévia, ônus, RCPN e robôs ganharam teto de uso por dia no
      catálogo, e as telas o conferem antes da rede.

Cada teste falharia no código de antes do LX13. Os dados são inventados: o
CPF 000.000.050-70 é fictício declarado no anti-vazamento, e nenhum nome é de
gente de verdade.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from io import BytesIO
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

import ia_catalogo as CAT                      # noqa: E402
import ia_uso as USO                           # noqa: E402
import rc_leitura_documentos as LEIT           # noqa: E402
import revisao_anexos as RA                    # noqa: E402
import robo_llm as LLM                         # noqa: E402
import robo_schema as SCH                      # noqa: E402
from bd_nativo import banco                    # noqa: E402
# O material dos anexos é o do teste do módulo: o PDF digitalizado, a IA de
# mentira que conta as chamadas e a casa com `attachments`.
from test_revisao_anexos import IA, ORIGEM, anexar, casa, pdf_digitalizado  # noqa: E402,F401

SENHA = "Senha#12345"
CPF = "000.000.050-70"
TELEFONE = "(98) 98877-6655"
#: A marca da máscara, qualquer que seja o tipo que ela escolheu («[CPF_01]»,
#: «[PESSOA_01]» quando o número vem rotulado com quem é).
MARCA = r"\[[A-Z_]+_\d+\]"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _entrar(cg_casa, usuario: str, nome: str, papel: str):
    cg_casa["db"].create_user(usuario, nome, SENHA, papel)
    c = cg_casa["app"].test_client()
    c.post("/login", data={"username": usuario, "password": SENHA,
                           "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return c


def _usos_de_hoje(cg_casa, finalidade: str, quantos: int) -> None:
    """Põe no registro `quantos` chamadas de hoje daquela finalidade."""
    with cg_casa["db"].transaction() as con:
        bd = banco(con)
        USO.init_ia_schema(con)
        for _ in range(quantos):
            bd.escrever(
                """INSERT INTO ia_uso (quando, modulo, finalidade, resultado)
                   VALUES (%s, 'teste', %s, 'ok')""", (USO._agora(), finalidade))


# ------------------------------------------------------- M5: o robô mascarado


def _robo(cg_casa, *, exemplo: str = "") -> int:
    with cg_casa["db"].transaction() as con:
        rid = SCH.criar_robo(con, nome="Firma", ato="firma", provedor="deepseek",
                             prompt="Rascunhe o pedido de firma.", ativo=1,
                             agora="2026-10-19T10:00:00")
        SCH.gravar_config(con, SCH.CHAVE_DEEPSEEK, "sk-robo-de-teste")
        if exemplo:
            SCH.adicionar_exemplo(con, rid, exemplo, "rascunho de exemplo", 1)
    return rid


def test_o_teste_do_robo_sobe_o_pedido_mascarado_e_a_tela_mostra_o_nome_de_volta(
        cg_casa_logada, monkeypatch):
    """Até o LX13 o pedido ia em claro (`mascarado=False`) e ficava em claro
    no `robo_teste_log`, sem expurgo. Agora o CPF e o telefone do pedido e dos
    exemplos não sobem nem ficam no registro; só a tela de quem testou vê o
    rascunho com eles de volta."""
    casa = cg_casa_logada
    rid = _robo(casa, exemplo=f"firma do CPF {CPF}")
    subiu: list[tuple[str, str]] = []

    def pedir(provedor, chave, system, user, *, timeout):
        subiu.append((system, user))
        return {"texto": f"Rascunho para: {user}", "modelo": "deepseek-chat",
                "entrada": 9, "saida": 4}
    monkeypatch.setattr(LLM, "_pedir", pedir)
    c = casa["c"]
    r = c.post(f"/robos/{rid}/testar", data={
        "csrf_token": _token(c.get(f"/robos/{rid}").get_data(as_text=True)),
        "pedido": f"firma do requerente CPF {CPF}, telefone {TELEFONE}"})
    assert r.status_code == 200
    ((system, user),) = subiu
    for dado in (CPF, TELEFONE, "98877"):
        assert dado not in system and dado not in user, dado
    assert re.search(MARCA, user)
    assert CPF in r.get_data(as_text=True)          # a tela devolve o que era dele
    with casa["db"].connect() as con:
        (log,) = banco(con).ler("SELECT pedido, rascunho FROM robo_teste_log "
                                "WHERE robo_id = %s ORDER BY id", (rid,))
        (uso,) = banco(con).ler("SELECT mascarado FROM ia_uso WHERE referencia = %s "
                                "ORDER BY id", (f"robo:{rid}",))
    assert CPF not in log["pedido"] and CPF not in log["rascunho"]
    assert re.search(MARCA, log["pedido"]) and uso["mascarado"] is True


def test_o_registro_dos_testes_do_robo_some_depois_de_trinta_dias(cg_casa):
    """O registro é rastro de teste, e não arquivo do balcão: o de mais de
    `DIAS_DO_REGISTRO_DE_TESTE` dias sai no próximo teste."""
    rid = _robo(cg_casa)
    with cg_casa["db"].transaction() as con:
        for agora in ("2026-08-01 09:00:00", "2026-09-20 09:00:00"):
            SCH.registrar_teste(con, robo_id=rid, usuario="balcao", pedido="p",
                                rascunho="r", modo="local", agora=agora)
        SCH.registrar_teste(con, robo_id=rid, usuario="balcao", pedido="p",
                            rascunho="r", modo="local", agora="2026-10-19 09:00:00")
        datas = [l["criado_em"][:10] for l in banco(con).ler(
            "SELECT criado_em FROM robo_teste_log WHERE robo_id = %s ORDER BY id", (rid,))]
    assert datas == ["2026-09-20", "2026-10-19"]


# ------------------------------------------------ M6: a leitura é de quem lavra


def _leitura(cg_casa, por: str) -> int:
    with cg_casa["db"].transaction() as con:
        return LEIT.abrir(con, especie="OBITO", agora="2026-10-19T10:00:00", por=por)


def test_o_auditor_nao_abre_a_leitura_do_registro_civil(cg_casa):
    """O AUDITOR não lavra assento, e a leitura traz a DO inteira (causa da
    morte, CPF). As rotas exigiam só login."""
    numero = _leitura(cg_casa, "ANA EXEMPLO DO BALCAO")
    c = _entrar(cg_casa, "auditora", "BEATRIZ EXEMPLO AUDITORA", "AUDITOR")
    assert c.get("/rcpn/leitura").status_code == 403
    assert c.get(f"/rcpn/leitura/{numero}").status_code == 403
    r = c.post(f"/rcpn/leitura/{numero}/rascunho",
               data={"csrf_token": _token(c.get("/", follow_redirects=True).get_data(as_text=True))})
    assert r.status_code == 403


def test_o_balcao_nao_abre_pelo_numero_a_leitura_de_outra_pessoa(cg_casa):
    """O número é sequencial: «/rcpn/leitura/1», «/2»… Antes, qualquer login
    via a de qualquer um. O balcão vê a dele; ADMIN e MANAGER, todas."""
    alheia = _leitura(cg_casa, "OUTRA PESSOA DO BALCAO")
    c = _entrar(cg_casa, "balcao", "ANA EXEMPLO DO BALCAO", "USER")
    propria = _leitura(cg_casa, "ANA EXEMPLO DO BALCAO")

    r = c.get(f"/rcpn/leitura/{alheia}")
    assert r.status_code == 302 and "/rcpn/leitura" in r.headers["Location"]
    r = c.post(f"/rcpn/leitura/{alheia}/rascunho",
               data={"csrf_token": _token(c.get("/rcpn/leitura").get_data(as_text=True))})
    assert r.status_code == 302 and "rascunho_id" not in r.headers["Location"]
    lista = c.get("/rcpn/leitura").get_data(as_text=True)
    assert "OUTRA PESSOA DO BALCAO" not in lista and "ANA EXEMPLO DO BALCAO" in lista
    assert c.get(f"/rcpn/leitura/{propria}").status_code == 200

    gerente = _entrar(cg_casa, "gerente", "CARLA EXEMPLO GERENTE", "MANAGER")
    assert gerente.get(f"/rcpn/leitura/{alheia}").status_code == 200
    assert "OUTRA PESSOA DO BALCAO" in gerente.get("/rcpn/leitura").get_data(as_text=True)


# --------------------------------------------- M12: o teto de páginas do RCPN


def _pdf(paginas: int, caminho: Path) -> Path:
    from PIL import Image
    folhas = [Image.new("L", (40, 56), 255) for _ in range(paginas)]
    folhas[0].save(caminho, format="PDF", save_all=True, append_images=folhas[1:])
    return caminho


def test_a_leitura_do_rcpn_acima_do_teto_de_paginas_e_recusada_antes_de_subir(tmp_path):
    """Um PDF de mil folhas eram ~125 triagens e mil leituras pagas. Acima do
    teto a leitura inteira é recusada, e a IA não é chamada nenhuma vez."""
    chamadas = []

    def ia(*a, **k):
        chamadas.append(k)
        raise AssertionError("a IA não devia ser chamada")
    arquivo = _pdf(LEIT.MAXIMO_DE_PAGINAS + 1, tmp_path / "pilha.pdf")
    em_uso = {"triagem": "T", "manuscrito": "F", "impresso": "M"}
    with pytest.raises(LEIT.LeituraError, match=f"{LEIT.MAXIMO_DE_PAGINAS + 1} páginas"):
        LEIT.ler(ia, tmp_path, em_uso, [{"caminho": str(arquivo), "nome": "pilha.pdf"}])
    assert chamadas == []
    assert "páginas por leitura" in json.dumps(CAT.entrada("rc_leitura"), ensure_ascii=False)


# ---------------------------------------------------- B5: o teto de uso do dia


def test_os_sistemas_que_nao_tinham_teto_ganharam_teto_diario_no_catalogo():
    for codigo in ("revisao_previa", "ri_onus_ia", "rc_leitura", "robo_rascunho"):
        teto = CAT.teto_diario(codigo)
        assert isinstance(teto, int) and teto > 0, codigo
        assert CAT.teto_de(CAT.entrada(codigo)) == f"{teto} chamadas ao provedor por dia"
    assert CAT.teto_diario("agente") is None        # o teto dele é por sessão


def test_a_conta_do_dia_ignora_o_recusado_o_outro_dia_e_a_outra_finalidade(cg_casa):
    hoje = USO._agora()[:10]
    with cg_casa["db"].transaction() as con:
        USO.init_ia_schema(con)
        for quando, finalidade, resultado in (
                (f"{hoje}T08:00:00", "rc_leitura", "ok"),
                (f"{hoje}T09:00:00", "rc_leitura", "erro"),
                (f"{hoje}T09:30:00", "rc_leitura", "recusado"),
                ("2026-01-02T09:00:00", "rc_leitura", "ok"),
                (f"{hoje}T10:00:00", "ajuda", "ok")):
            banco(con).escrever(
                "INSERT INTO ia_uso (quando, finalidade, resultado) VALUES (%s, %s, %s)",
                (quando, finalidade, resultado))
    with cg_casa["db"].connect() as con:
        assert USO.usos_do_dia(con, "rc_leitura", hoje) == 2


def test_a_leitura_do_rcpn_passado_o_teto_do_dia_nao_abre_nem_sobe(cg_casa_logada,
                                                                   monkeypatch):
    import agente_provedores as AP
    casa = cg_casa_logada
    monkeypatch.setitem(CAT.CHAMADAS_POR_DIA, "rc_leitura", 2)
    _usos_de_hoje(casa, "rc_leitura", 2)
    monkeypatch.setattr(AP, "tem_chave", lambda *a, **k: True)

    def nao_chama(*a, **k):
        raise AssertionError("passado o teto, a IA não é chamada")
    monkeypatch.setattr(AP, "conversar", nao_chama)
    from PIL import Image
    imagem = BytesIO()
    Image.new("RGB", (60, 80), "white").save(imagem, format="PNG")
    imagem.seek(0)
    c = casa["c"]
    r = c.post("/rcpn/leitura", data={
        "csrf_token": _token(c.get("/rcpn/leitura").get_data(as_text=True)),
        "especie": "NASCIMENTO", "arquivos": [(imagem, "dnv.png")]},
        content_type="multipart/form-data", follow_redirects=True)
    assert "teto de uso de IA de hoje" in r.get_data(as_text=True)
    with casa["db"].connect() as con:
        assert not banco(con).tem_tabela("rc_leituras") or banco(con).valor(
            "SELECT count(*) AS n FROM rc_leituras") == 0


def test_o_teste_do_robo_passado_o_teto_do_dia_nao_chama_o_provedor(cg_casa_logada,
                                                                    monkeypatch):
    casa = cg_casa_logada
    rid = _robo(casa)
    monkeypatch.setitem(CAT.CHAMADAS_POR_DIA, "robo_rascunho", 1)
    _usos_de_hoje(casa, "robo_rascunho", 1)

    def nao_chama(*a, **k):
        raise AssertionError("passado o teto, o provedor não é chamado")
    monkeypatch.setattr(LLM, "_pedir", nao_chama)
    c = casa["c"]
    r = c.post(f"/robos/{rid}/testar", data={
        "csrf_token": _token(c.get(f"/robos/{rid}").get_data(as_text=True)),
        "pedido": "firma simples"})
    assert r.status_code == 200 and "teto de uso de IA de hoje" in r.get_data(as_text=True)


# --------------------------------------- M7: a capa não esconde o documento


def test_a_capa_de_comprovante_nao_tira_o_mandado_do_dossie(casa):
    """A triagem via só a primeira página: um «comprovante» grampeado na frente
    do mandado tirava o mandado inteiro do dossiê do revisor. Agora ela vê as
    primeiras páginas, e o que não viu não descarta."""
    anexar(casa, "comprovante_e_mandado.pdf", pdf_digitalizado(RA.PAGINAS_DA_TRIAGEM + 2))
    ia = IA(importante=False)
    r = RA.ler(casa["con"], casa["pasta"], ORIGEM, conversar=ia)
    assert ia.triagens == 1 and ia.transcricoes >= 1
    assert r["bloco"] != ""
    item = r["resumo"][0]
    assert item["importante"] is True and item["lidas"] == RA.PAGINAS_DA_TRIAGEM + 2
    assert f"viu {RA.PAGINAS_DA_TRIAGEM} de {RA.PAGINAS_DA_TRIAGEM + 2}" in item["motivo"]


def test_o_descarte_de_antes_que_viu_uma_pagina_so_passa_pela_triagem_de_novo(casa):
    """O que a triagem de antes do LX13 descartou foi descartado olhando uma
    página só (`paginas_triadas` NULL). Reaproveitar esse descarte manteria o
    mandado fora do dossiê para sempre."""
    dados = pdf_digitalizado(2)
    anexar(casa, "mandado.pdf", dados)
    RA.init_schema(casa["con"])
    banco(casa["con"]).escrever(
        """INSERT INTO rv_anexos_lidos (sha256, nome, paginas, tipo, importante, motivo,
               situacao, paginas_lidas) VALUES (%s, 'mandado.pdf', 2, 'comprovante', 0,
               'comprovante de pagamento', 'TRIADO', 0)""",
        (hashlib.sha256(dados).hexdigest(),))
    casa["con"].commit()
    ia = IA(importante=True)
    r = RA.ler(casa["con"], casa["pasta"], ORIGEM, conversar=ia)
    assert ia.triagens == 1 and ia.transcricoes == 1
    assert r["resumo"][0]["reaproveitado"] is False and r["bloco"] != ""


# ------------------------- B5: o teto do dia também na revisão prévia e no ônus
# O catálogo passou a anunciar o teto diário dos dois; sem a conferência antes
# da rede, o número estaria só no papel. Passou do teto, a leitura termina em
# ERRO com a frase (o balcão lavra, como em toda falha da IA) e nada sobe.


def _nao_chama(*_a, **_k):
    pytest.fail("passou do teto do dia e ainda chamou o provedor")


def test_a_revisao_previa_passado_o_teto_do_dia_nao_chama_o_provedor(cg_casa):
    import sqlite3

    import revisao_previa as RV
    con = sqlite3.connect(cg_casa["banco"])
    try:
        mid = con.execute("""INSERT INTO ri_matriculas (numero, teor, criado_em)
                             VALUES ('4100', 'Imóvel rural com 10 ha', '2026-10-06')""").lastrowid
        con.commit()
        rid, _ = RV.pedir(con, "RI", mid, RV.hash_do_ato("R", "R-1: venda"),
                          RV.dossie_ri(con, mid, "R", "R-1: venda", "Compra e venda"),
                          usuario="QUEM LAVRA")
        con.commit()
        _usos_de_hoje(cg_casa, "revisao_previa", CAT.CHAMADAS_POR_DIA["revisao_previa"])
        RV.executar(Path(cg_casa["banco"]), cg_casa["dados"], rid, conversar=_nao_chama)
        situacao, erro = con.execute("SELECT situacao, erro FROM rv_revisoes WHERE id = ?",
                                     (rid,)).fetchone()
    finally:
        con.close()
    assert situacao == "ERRO" and "teto de uso de IA de hoje" in erro


def test_o_onus_passado_o_teto_do_dia_nao_chama_o_provedor(cg_casa):
    import sqlite3

    import ri_onus_ia as RONIA
    con = sqlite3.connect(cg_casa["banco"])
    try:
        mid = con.execute("""INSERT INTO ri_matriculas (numero, teor, criado_em)
                             VALUES ('4201', 'Imóvel urbano. R-1: compra e venda.', '2026-10-06')"""
                          ).lastrowid
        con.commit()
        sid, _ = RONIA.pedir(con, mid, usuario="QUEM ATENDE")
        con.commit()
        _usos_de_hoje(cg_casa, "ri_onus_ia", CAT.CHAMADAS_POR_DIA["ri_onus_ia"])
        RONIA.executar(Path(cg_casa["banco"]), cg_casa["dados"], sid, conversar=_nao_chama)
        situacao, erro = con.execute("SELECT situacao, erro FROM ri_onus_sugestoes WHERE id = ?",
                                     (sid,)).fetchone()
    finally:
        con.close()
    assert situacao == "ERRO" and "teto de uso de IA de hoje" in erro
