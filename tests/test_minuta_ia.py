"""O agente de minutas do RI e das Notas — 23/10/2026.

    «agora vamos criar um agente para preparar as minutas dos atos do RI e do
     Notas (escrituras, procurações e atas notariais), nos moldes que temos no
     RCPN, mas com algumas alterações. O agente usaria a API do claude em opus
     high (...) precisaria ter espaço para instruções iniciais e instruções de
     revisão»

A IA AQUI É DE MENTIRA: ela guarda o que recebeu e devolve a minuta no formato
combinado. É isso que prova o que sobe (os documentos inteiros, a ficha, as
instruções, o Opus no esforço alto) e para onde a minuta volta — sem rede.

O QUE ESTES TESTES PROTEGEM
    1. O transporte manda o PDF como documento, o esforço e o formato, e recusa
       campo que não conhece — e não deixa o esforço sumir noutro provedor.
    2. Só sobem os documentos daquele ato: número de anexo de outro lugar é
       recusado, e sem documento não há pedido.
    3. RI: a minuta pousa em `ri_minutas`, A_REVISAR, com as partes — e nada
       se lavra.
    4. A revisão parte do texto ATUAL — com o que a pessoa corrigiu à mão — e
       pousa na MESMA minuta.
    5. O que mudou enquanto o agente trabalhava não se sobrescreve calado.
    6. Notas: o teor do ato em lavratura recebe a minuta, ESCAPADA.
    7. Recusa do modelo e resposta cortada viram ERRO com a frase.
    8. O quadro aparece nas duas telas, e o arquivo juntado fica onde o ato o
       arquiva.
"""
from __future__ import annotations

import io
import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import agente_provedores as AP   # noqa: E402
import minuta_ia as MI           # noqa: E402

PDF = (b"%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\ntrailer << /Root 1 0 R >>\n"
       b"%%EOF\n")

TEOR_RI = ("R-3/777 - Protocolo nº 11.600, de 20/10/2026. COMPRA E VENDA. Pela "
           "escritura pública lavrada nestas notas, JOSE EXEMPLO vendeu o imóvel "
           "desta matrícula a MARIA EXEMPLO, pelo preço de [COMPLETAR: valor].")


class IA:
    """O provedor de mentira: guarda cada pedido e responde a minuta."""

    def __init__(self, teor=TEOR_RI, parou="end_turn", texto=None):
        self.teor = teor
        self.parou = parou
        self.texto = texto
        self.pedidos: list[dict] = []

    def __call__(self, pasta, *, provedor, sistema, conversa, ferramentas, modelo,
                 maximo_de_saida, **resto):
        self.pedidos.append({"sistema": sistema, "conversa": conversa, "modelo": modelo,
                             **resto})
        texto = self.texto if self.texto is not None else json.dumps({
            "teor": self.teor, "tipo_ato": "R",
            "natureza_titulo": "Escritura pública de compra e venda",
            "partes": [{"nome": "Jose Exemplo", "documento": "000.000.001-91",
                        "papel": "Transmitente", "qualificacao": "brasileiro, casado"},
                       {"nome": "Maria Exemplo", "documento": "",
                        "papel": "adquirente", "qualificacao": "brasileira"}],
            "pendencias": ["o valor da compra não está legível"],
            "fontes": [{"dado": "vendedor", "documento": "escritura.pdf", "pagina": "1"}],
            "observacoes": ""})
        return {"texto": texto, "parou": self.parou, "entrada": 1000, "saida": 200,
                "modelo": modelo}


# ------------------------------------------------------------- a bancada


@pytest.fixture()
def casa(cg_casa_logada):
    return cg_casa_logada


def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _anexar(casa, entidade: str, entidade_id: int, nome="escritura.pdf",
            dados=PDF) -> int:
    caminho = casa["dados"] / f"{entidade}-{entidade_id}-{nome}"
    caminho.write_bytes(dados)
    con = _con(casa)
    with con:
        cur = con.execute(
            """INSERT INTO attachments (entity_type, entity_id, original_name, stored_name,
                   stored_path, sha256, size_bytes, uploaded_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (entidade, entidade_id, nome, caminho.name, str(caminho),
             f"sha-{entidade}-{entidade_id}-{nome}", len(dados), "2026-10-23T10:00"))
        aid = int(cur.lastrowid)
    con.close()
    return aid


def _matricula_com_prenotacao(casa) -> tuple[int, int]:
    con = _con(casa)
    with con:
        mid = int(con.execute(
            """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao, tipo_ficha,
                   teor, criado_em)
               VALUES ('777', '2', '2', 'ATIVO', 'ESTRUTURADA',
                       'IMÓVEL: lote 12 da quadra 3, Cidade Exemplo', '2026-10-01T10:00')"""
        ).lastrowid)
        pid = int(con.execute(
            """INSERT INTO ri_protocolos (numero, livro, data_prenotacao, natureza_titulo,
                   matricula_id, situacao, criado_em)
               VALUES (11600, '1A', '2026-10-20', 'Escritura de compra e venda', ?,
                       'ABERTO', '2026-10-20T09:00')""", (mid,)).lastrowid)
    con.close()
    return mid, pid


def _ato_das_notas(casa, tipo="PROCURACAO", situacao="EM_LAVRATURA") -> int:
    con = _con(casa)
    with con:
        aid = int(con.execute(
            """INSERT INTO nt_atos (tipo, data, situacao, natureza, teor_formato, origem,
                   criado_em)
               VALUES (?, '2026-10-23', ?, 'procuração ad negotia', 'html', 'MANUAL',
                       '2026-10-23T09:00')""", (tipo, situacao)).lastrowid)
    con.close()
    return aid


def _pedir_e_executar(casa, atribuicao, alvo_id, anexos, ia, **kw) -> int:
    con = _con(casa)
    with con:
        pid = MI.pedir(con, atribuicao, alvo_id, anexos_ids=anexos, usuario="MARIO", **kw)
    con.close()
    MI.executar(casa["banco"], casa["dados"], pid, conversar=ia)
    return pid


def _pedido(casa, pid) -> dict:
    con = _con(casa)
    p = MI.mostrar(con, pid)
    con.close()
    return p


# ------------------------------------------------------------- o transporte


def test_o_pdf_sobe_como_documento_antes_do_texto():
    pedido = AP.montar_pedido("claude", sistema="s", conversa=[
        {"tipo": "user", "texto": "leia",
         "documentos": [{"mime": "application/pdf", "base64": "QUJD", "titulo": "a.pdf"}],
         "imagens": [{"mime": "image/jpeg", "base64": "QUJD"}]}],
        ferramentas=[], modelo=MI.MODELO,
        extras={"output_config": {"effort": "high"}, "fallbacks": "default"},
        betas=[MI.BETA_DO_DESVIO])
    conteudo = pedido["corpo"]["messages"][0]["content"]
    assert [b["type"] for b in conteudo] == ["document", "image", "text"]
    assert conteudo[0]["title"] == "a.pdf"
    assert pedido["corpo"]["output_config"] == {"effort": "high"}
    assert pedido["corpo"]["fallbacks"] == "default"
    assert AP._cabecalhos(pedido, "sk-x")["anthropic-beta"] == MI.BETA_DO_DESVIO


def test_campo_desconhecido_e_esforco_noutro_provedor_sao_recusados():
    with pytest.raises(AP.AgenteError):
        AP.montar_pedido("claude", sistema="s", conversa=[], ferramentas=[],
                         extras={"temperature": 0})
    with pytest.raises(AP.AgenteError):
        AP.montar_pedido("gpt", sistema="s", conversa=[], ferramentas=[],
                         extras={"output_config": {"effort": "high"}})


def test_sem_extras_o_pedido_de_sempre_nao_muda():
    pedido = AP.montar_pedido("claude", sistema="s", conversa=[
        {"tipo": "user", "texto": "oi"}], ferramentas=[])
    assert "output_config" not in pedido["corpo"] and "fallbacks" not in pedido["corpo"]
    assert "anthropic-beta" not in AP._cabecalhos(pedido, "sk-x")


# ------------------------------------------------------------- o RI


def test_ri_a_minuta_pousa_na_fila_com_as_partes_e_nada_se_lavra(casa):
    mid, prenot = _matricula_com_prenotacao(casa)
    anexo = _anexar(casa, "RI_PROTOCOLO", prenot)
    ia = IA()
    pid = _pedir_e_executar(casa, MI.RI, mid, [anexo], ia, tipo_ato="R",
                            instrucao="compra e venda da totalidade")
    p = _pedido(casa, pid)
    assert p["situacao"] == MI.PRONTA, p.get("erro")
    assert p["aplicado_em"] and p["minuta_id"]

    enviado = ia.pedidos[0]
    assert enviado["modelo"] == "claude-opus-5-5"
    assert enviado["extras"]["output_config"]["effort"] == "high"
    assert enviado["extras"]["output_config"]["format"]["type"] == "json_schema"
    turno = enviado["conversa"][0]
    assert turno["documentos"][0]["mime"] == "application/pdf"
    assert "MATRÍCULA nº 777" in turno["texto"]
    assert "lote 12 da quadra 3" in turno["texto"]
    assert "compra e venda da totalidade" in turno["texto"]
    assert "REGISTRO DE IMÓVEIS" in enviado["sistema"]

    con = _con(casa)
    mi = con.execute("SELECT * FROM ri_minutas WHERE id = ?", (p["minuta_id"],)).fetchone()
    partes = con.execute("SELECT * FROM ri_minuta_partes WHERE minuta_id = ? ORDER BY ordem",
                         (p["minuta_id"],)).fetchall()
    atos = con.execute("SELECT COUNT(*) FROM ri_atos WHERE matricula_id = ?",
                       (mid,)).fetchone()[0]
    con.close()
    assert mi["situacao"] == "A_REVISAR" and mi["origem"] == MI.ORIGEM_DA_MINUTA
    assert mi["teor"] == TEOR_RI and mi["prenotacao"] == "11600"
    assert [x["nome"] for x in partes] == ["JOSE EXEMPLO", "MARIA EXEMPLO"]
    assert partes[0]["documento_tipo"] == "CPF" and partes[0]["papel"] == "transmitente"
    assert atos == 0


def test_so_sobem_os_documentos_daquele_ato(casa):
    mid, prenot = _matricula_com_prenotacao(casa)
    _anexar(casa, "RI_PROTOCOLO", prenot)
    de_outro = _anexar(casa, "EXPEDIENTE", 99, nome="oficio.pdf")
    con = _con(casa)
    with pytest.raises(MI.MinutaIAError, match="não é deste ato"):
        MI.pedir(con, MI.RI, mid, anexos_ids=[de_outro], tipo_ato="R")
    with pytest.raises(MI.MinutaIAError, match="ao menos um documento"):
        MI.pedir(con, MI.RI, mid, anexos_ids=[], tipo_ato="R")
    con.close()


def test_a_revisao_parte_do_texto_corrigido_a_mao_e_pousa_na_mesma_minuta(casa):
    import ri_minuta as RIMIN
    mid, prenot = _matricula_com_prenotacao(casa)
    anexo = _anexar(casa, "RI_PROTOCOLO", prenot)
    primeiro = _pedir_e_executar(casa, MI.RI, mid, [anexo], IA(), tipo_ato="R")
    minuta_id = _pedido(casa, primeiro)["minuta_id"]

    corrigido = TEOR_RI.replace("[COMPLETAR: valor]", "R$ 50.000,00 (CORRIGIDO À MÃO)")
    con = _con(casa)
    with con:
        RIMIN.atualizar(con, minuta_id, teor=corrigido, agora="2026-10-23T11:00")
    con.close()

    ia = IA(teor=corrigido + " Cláusula de usufruto retirada.")
    con = _con(casa)
    with con:
        pid = MI.pedir(con, MI.RI, mid, anexos_ids=None, anterior_id=primeiro,
                       revisao="retire a cláusula de usufruto", usuario="MARIO")
    con.close()
    MI.executar(casa["banco"], casa["dados"], pid, conversar=ia)

    texto = ia.pedidos[0]["conversa"][0]["texto"]
    assert "CORRIGIDO À MÃO" in texto
    assert "retire a cláusula de usufruto" in texto
    p = _pedido(casa, pid)
    assert p["versao"] == 2 and p["minuta_id"] == minuta_id and p["aplicado_em"]
    con = _con(casa)
    teor = con.execute("SELECT teor FROM ri_minutas WHERE id = ?", (minuta_id,)).fetchone()[0]
    quantas = con.execute("SELECT COUNT(*) FROM ri_minutas WHERE matricula_id = ?",
                          (mid,)).fetchone()[0]
    con.close()
    assert "usufruto retirada" in teor and quantas == 1


def test_o_que_mudou_enquanto_o_agente_trabalhava_nao_se_sobrescreve(casa):
    import ri_minuta as RIMIN
    mid, prenot = _matricula_com_prenotacao(casa)
    anexo = _anexar(casa, "RI_PROTOCOLO", prenot)
    primeiro = _pedir_e_executar(casa, MI.RI, mid, [anexo], IA(), tipo_ato="R")
    minuta_id = _pedido(casa, primeiro)["minuta_id"]

    con = _con(casa)
    with con:
        pid = MI.pedir(con, MI.RI, mid, anexos_ids=None, anterior_id=primeiro,
                       revisao="ajuste a qualificação", usuario="MARIO")
        # alguém corrige a minuta à mão ENQUANTO o agente trabalha
        RIMIN.atualizar(con, minuta_id, teor=TEOR_RI + " (mexida no meio)",
                        agora="2026-10-23T11:00")
    con.close()
    MI.executar(casa["banco"], casa["dados"], pid,
                conversar=IA(teor=TEOR_RI + " versão do agente"))
    p = _pedido(casa, pid)
    assert p["situacao"] == MI.PRONTA and not p["aplicado_em"]
    assert "mudou enquanto o agente trabalhava" in p["nao_aplicado_motivo"]

    # a pessoa decide trocar, pela tela
    html = casa["c"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)
    casa["c"].post(f"/agente-minutas/pedido/{pid}/usar", data={"csrf_token": token})
    con = _con(casa)
    teor = con.execute("SELECT teor FROM ri_minutas WHERE id = ?", (minuta_id,)).fetchone()[0]
    con.close()
    assert teor.endswith("versão do agente")


# ------------------------------------------------------------- as Notas


def test_notas_o_teor_do_ato_recebe_a_minuta_escapada(casa):
    aid = _ato_das_notas(casa)
    anexo = _anexar(casa, "NT_ATO", aid, nome="rg.pdf")
    ia = IA(teor="PROCURAÇÃO bastante que faz <script>alert(1)</script> MARIA.\n\n"
                 "Outorgado: JOSE.")
    pid = _pedir_e_executar(casa, MI.NOTAS, aid, [anexo], ia)
    p = _pedido(casa, pid)
    assert p["situacao"] == MI.PRONTA and p["aplicado_em"], p.get("erro")
    assert "TABELIONATO DE NOTAS" in ia.pedidos[0]["sistema"]
    con = _con(casa)
    teor = con.execute("SELECT teor FROM nt_atos WHERE id = ?", (aid,)).fetchone()[0]
    con.close()
    assert "<script>" not in teor and "&lt;script&gt;" in teor
    assert teor.count("<p>") == 2


def test_notas_ato_ja_lancado_ou_de_outra_especie_nao_recebe_minuta(casa):
    lavrado = _ato_das_notas(casa, situacao="LAVRADO")
    testamento = _ato_das_notas(casa, tipo="TESTAMENTO")
    con = _con(casa)
    with pytest.raises(MI.MinutaIAError, match="lançado no livro"):
        MI.alvo(con, MI.NOTAS, lavrado)
    with pytest.raises(MI.MinutaIAError, match="outra espécie"):
        MI.alvo(con, MI.NOTAS, testamento)
    con.close()


# ------------------------------------------------------------- as falhas


@pytest.mark.parametrize("parou,frase", [("refusal", "recusou"),
                                         ("max_tokens", "veio cortada")])
def test_recusa_e_resposta_cortada_viram_erro_com_a_frase(casa, parou, frase):
    aid = _ato_das_notas(casa)
    anexo = _anexar(casa, "NT_ATO", aid, nome="rg.pdf")
    pid = _pedir_e_executar(casa, MI.NOTAS, aid, [anexo], IA(parou=parou))
    p = _pedido(casa, pid)
    assert p["situacao"] == MI.ERRO and frase in p["erro"]
    con = _con(casa)
    teor = con.execute("SELECT teor FROM nt_atos WHERE id = ?", (aid,)).fetchone()[0]
    con.close()
    assert not teor


def test_dois_pedidos_ao_mesmo_tempo_no_mesmo_ato_sao_recusados(casa):
    aid = _ato_das_notas(casa)
    anexo = _anexar(casa, "NT_ATO", aid, nome="rg.pdf")
    con = _con(casa)
    with con:
        MI.pedir(con, MI.NOTAS, aid, anexos_ids=[anexo])
    with pytest.raises(MI.MinutaIAError, match="ainda está preparando"):
        MI.pedir(con, MI.NOTAS, aid, anexos_ids=[anexo])
    con.close()


# ------------------------------------------------------------- a tela


def test_o_quadro_aparece_na_ficha_e_no_ato(casa, monkeypatch):
    # sem a chave do Claude o quadro aparece, mas o formulário (com a lista dos
    # documentos) não — por isso a chave de mentira aqui
    monkeypatch.setattr(AP, "tem_chave", lambda *a, **k: True)
    mid, prenot = _matricula_com_prenotacao(casa)
    _anexar(casa, "RI_PROTOCOLO", prenot)
    aid = _ato_das_notas(casa)
    ficha = casa["c"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    ato = casa["c"].get(f"/notas/atos/{aid}").get_data(as_text=True)
    assert 'id="agente-minutas"' in ficha and "escritura.pdf" in ficha
    assert 'id="agente-minutas"' in ato
    # É O PRIMEIRO QUADRO DAS DUAS TELAS — ordem do oficial em 23/10/2026
    assert ficha.index('id="agente-minutas"') < ficha.index('id="minutas-para-lavrar"')
    assert ficha.index('<section class="panel"') == ficha.index('<section class="panel" id="agente-minutas"')
    assert ato.index('id="agente-minutas"') < ato.index('id="documentos-qualificacao"')
    assert ato.index('<section class="panel"') == ato.index('<section class="panel" id="agente-minutas"')


def test_o_arquivo_juntado_fica_na_prenotacao_e_o_pedido_entra(casa, monkeypatch):
    monkeypatch.setattr(AP, "tem_chave", lambda *a, **k: True)
    comecados = []
    monkeypatch.setattr(MI, "preparar_em_segundo_plano",
                        lambda banco, pasta, pid: comecados.append(pid))
    mid, prenot = _matricula_com_prenotacao(casa)
    html = casa["c"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)
    r = casa["c"].post(f"/agente-minutas/RI/{mid}/pedir", data={
        "csrf_token": token, "tipo_ato": "R", "prenotacao_destino": str(prenot),
        "instrucao": "registro da compra e venda",
        "arquivos": (io.BytesIO(PDF), "titulo.pdf")}, content_type="multipart/form-data")
    assert r.status_code == 302
    con = _con(casa)
    anexo = con.execute("""SELECT * FROM attachments WHERE entity_type = 'RI_PROTOCOLO'
                             AND entity_id = ?""", (prenot,)).fetchone()
    pedido = con.execute("SELECT * FROM mi_pedidos WHERE alvo_id = ?", (mid,)).fetchone()
    con.close()
    assert anexo["original_name"] == "titulo.pdf"
    assert pedido and comecados == [pedido["id"]]
    assert json.loads(pedido["documentos_json"])[0]["anexo_id"] == anexo["id"]


def test_o_agente_nao_lavra_nao_sela_nao_numera_nao_cobra():
    publicos = [n for n in dir(MI) if not n.startswith("_") and callable(getattr(MI, n))]
    proibidas = ("lavrar", "selar", "numerar", "cobrar", "lancar")
    assert not [n for n in publicos if any(p in n.lower() for p in proibidas)]
