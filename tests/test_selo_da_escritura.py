"""O selo automático da escritura, e a anotação antes da lavratura.

    «acrescenta o campo de anotacoes antes da lavratura tambem para as
     escrituras e atas notariais. (...) e constroi o modulo de selo
     automatizado na escritura (se ja nao houver), ali consta pra inserir o
     selo manualmente» — o oficial, 17/09/2026

**O CAMINHO E O ENVELOPE SÃO MEDIDOS**, nos 283 selos de ato de livro que esta
casa comprou — e o que amarra cada caminho ao seu ato é o `selo{livro, folha}`
de dentro do envelope, que casa com o livro e a folha do ato:

| caminho | envelopes | casou com |
|---|---|---|
| `procuracao/poderes-especificos` | 217 | 204 PROCURACAO |
| `procuracao/simples` | 22 | 22 PROCURACAO |
| `procuracao/venda` | 1 | 1 PROCURACAO |
| `ato-declarado/com-valor` | 28 | 17 ESCRITURA |
| `ato-declarado/sem-valor` | 15 | 14 ESCRITURA |

Zero cruzamento entre as duas famílias. A **ata notarial** usa o contrato de
ato declarado sem valor, mas com seu item próprio 13.14.1; o caminho define a
forma do envelope e o item identifica a espécie do ato.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ato_selado as AS  # noqa: E402

SENHA = "Senha#12345"


# ------------------------------------------------- o caminho e o envelope


def test_a_escritura_escolhe_pelo_valor_declarado():
    """A mesma regra do ato do RI, e aqui ela está no nome dos caminhos."""
    assert AS.caminho_do_ato_de_livro_das_notas("ESCRITURA") == (
        "/selo/notas/ato-declarado/sem-valor")
    assert AS.caminho_do_ato_de_livro_das_notas(
        "ESCRITURA", com_valor=True) == "/selo/notas/ato-declarado/com-valor"


def test_a_procuracao_pergunta_porque_a_natureza_nao_separa():
    """`OUTRA`, `DETRAN` e `BANCO DO NORDESTE` aparecem nos três caminhos."""
    with pytest.raises(AS.AtoError) as erro:
        AS.caminho_do_ato_de_livro_das_notas("PROCURACAO")
    assert "três caminhos" in str(erro.value)
    for chave, caminho in AS.CAMINHO_DA_PROCURACAO.items():
        assert AS.caminho_do_ato_de_livro_das_notas(
            "PROCURACAO", especie_procuracao=chave) == caminho


def test_a_ata_comum_usa_o_contrato_sem_valor_e_o_item_proprio():
    assert AS.caminho_do_ato_de_livro_das_notas("ATA") == (
        "/selo/notas/ato-declarado/sem-valor")
    assert AS.ITENS_DA_ATA["ATA"] == (("13.14.1", 0),)


def test_a_ata_de_usucapiao_exige_o_valor_do_imovel():
    with pytest.raises(AS.AtoError, match="valor do imóvel"):
        AS.caminho_do_ato_de_livro_das_notas("ATA_USUCAPIAO")
    assert AS.caminho_do_ato_de_livro_das_notas(
        "ATA_USUCAPIAO", com_valor=True) == (
            "/selo/notas/ato-declarado/com-valor")


def test_o_envelope_sem_valor_tem_a_forma_medida():
    """15 de 15: `natureza{Outros, 41}` e `quantidade: 1`, sem valor."""
    env, cam = AS.envelope_do_ato_de_livro_das_notas(
        tipo="ESCRITURA", codigo_tj="13.2", escrevente="CARLA",
        versao_tabela="0520260101", livro="30", folha="12", termo="1234",
        partes=[{"nome": "SÔNIA"}])
    assert cam == "/selo/notas/ato-declarado/sem-valor"
    assert env["natureza"] == {"descricao": "Outros", "tipo": 41}
    assert env["quantidade"] == 1
    assert "valorDeclarado" not in env
    assert env["selo"] == {"escrevente": "CARLA", "livro": "30",
                           "folha": "12", "termo": "1234"}
    assert env["partes"]["nomePartes"] == []


def test_o_envelope_com_valor_nao_manda_quantidade():
    """28 de 28 mandam `valorDeclarado` e NENHUM manda `quantidade`."""
    env, cam = AS.envelope_do_ato_de_livro_das_notas(
        tipo="ESCRITURA", codigo_tj="13.1", escrevente="G",
        versao_tabela="0520260101", livro="30", folha="12",
        valor_declarado=25000.0, partes=[{"nome": "A"}])
    assert cam == "/selo/notas/ato-declarado/com-valor"
    assert env["valorDeclarado"] == {"valorDeclarado": 25000.0,
                                     "valorAvaliado": 25000.0}
    assert "quantidade" not in env
    assert "natureza" not in env


def test_a_parte_sem_documento_sai_so_com_o_nome():
    """`{nome}` em 429 e `{nome, documento}` em 185 — as duas formas reais.

    Mandar `documento: ""` onde a casa mandava só o nome seria inventar um
    campo vazio que ela nunca mandou.
    """
    env, _ = AS.envelope_do_ato_de_livro_das_notas(
        tipo="ESCRITURA", codigo_tj="13.2", escrevente="G",
        versao_tabela="0520260101", livro="1", folha="1",
        partes=[{"nome": "SEM DOC"}, {"nome": "COM DOC",
                                      "documento": "000.000.048-55"}])
    assert env["partes"]["parteAto"] == [
        {"nome": "SEM DOC"},
        {"nome": "COM DOC", "documento": "00000004855"}]


def test_sem_livro_e_folha_o_selo_nao_sai():
    """O pedido leva livro e folha — por isso o selo vem DEPOIS do livro."""
    with pytest.raises(AS.AtoError) as erro:
        AS.envelope_do_ato_de_livro_das_notas(
            tipo="ESCRITURA", codigo_tj="13.2", escrevente="G",
            versao_tabela="0520260101", livro="", folha="")
    assert "o livro" in str(erro.value) and "a folha" in str(erro.value)


def test_isento_sem_motivo_e_recusado():
    """Os 8 casos reais são a procuração do INSS, e todos trazem o motivo."""
    with pytest.raises(AS.AtoError):
        AS.envelope_do_ato_de_livro_das_notas(
            tipo="ESCRITURA", codigo_tj="13.2", escrevente="G",
            versao_tabela="0520260101", livro="1", folha="1", isento=True)
    env, _ = AS.envelope_do_ato_de_livro_das_notas(
        tipo="ESCRITURA", codigo_tj="13.2", escrevente="G",
        versao_tabela="0520260101", livro="1", folha="1", isento=True,
        motivo_isencao="art. 68-A da Lei 8.212/1991")
    assert env["isento"]["value"] is True


# ------------------------------------------------- a tela


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _ato(casa, tipo="ESCRITURA", **campos) -> int:
    con = sqlite3.connect(casa["banco"])
    with con:
        cur = con.execute(
            """INSERT INTO nt_atos (tipo, serie, data, hora, situacao,
                   natureza, interessado, teor, teor_formato, lavrado_nome,
                   origem, criado_em)
               VALUES (?, 'LIVRO', '2026-09-17', '10:22', 'EM_LAVRATURA',
                       'Compra e venda', 'MARIA DA SILVA',
                       '<p>Teor da escritura.</p>', 'html',
                       'CARLA EXEMPLO LIMA', 'MANUAL',
                       '2026-09-17T10:22:35')""", (tipo,))
        aid = int(cur.lastrowid)
        con.execute(
            """INSERT INTO nt_ato_partes (ato_id, nome, nome_norm, documento,
                                          ordem, testemunha, criado_em)
               VALUES (?,'MARIA DA SILVA','MARIA DA SILVA','00000004855',1,0,
                       '2026-09-17T10:22:35')""", (aid,))
        if campos:
            sets = ", ".join(f"{k}=?" for k in campos)
            con.execute(f"UPDATE nt_atos SET {sets} WHERE id=?",
                        (*campos.values(), aid))
    con.close()
    return aid


@pytest.fixture()
def casa(cg_casa):
    db = cg_casa["db"]
    db.create_user("carla", "CARLA EXEMPLO LIMA", SENHA, "USER")
    db.set_settings({"ri_cidade": "Cidade Exemplo", "ri_uf": "MA"})
    c = cg_casa["app"].test_client()
    c.post("/login", data={"username": "carla", "password": SENHA,
                           "csrf_token": _token(
                               c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {**cg_casa, "cliente": c}


def _postar(casa, ato_id, **dados) -> str:
    if dados.get("acao") == "lancar":
        # A trava da CENSEC (09/10/2026) — ver `notas_pronto_para_a_censec`.
        from notas_pronto_para_a_censec import preparar
        preparar(casa["banco"], ato_id)
    html = casa["cliente"].get(f"/notas/atos/{ato_id}").get_data(as_text=True)
    return casa["cliente"].post(
        f"/notas/atos/{ato_id}",
        data={"csrf_token": _token(html), **dados},
        follow_redirects=True).get_data(as_text=True)


def _linha(casa, ato_id):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    r = con.execute("SELECT * FROM nt_atos WHERE id=?", (ato_id,)).fetchone()
    con.close()
    return r


# ------------------------------------------------- a anotação


def test_a_escritura_em_lavratura_tem_o_campo_de_anotacoes(casa):
    """«acrescenta o campo de anotações antes da lavratura» — 17/09/2026."""
    aid = _ato(casa)
    html = casa["cliente"].get(f"/notas/atos/{aid}").get_data(as_text=True)
    assert "Anotações antes da lavratura" in html
    assert 'name="observacao"' in html
    assert 'value="anotacao_de_lavratura"' in html


def test_a_ata_notarial_tambem_tem_o_campo(casa):
    """Ele pediu as duas — escrituras **e** atas notariais."""
    aid = _ato(casa, tipo="ATA")
    html = casa["cliente"].get(f"/notas/atos/{aid}").get_data(as_text=True)
    assert "Anotações antes da lavratura" in html


def test_a_anotacao_guarda_quem_escreveu_e_quando(casa):
    """Nota sem dono é nota que ninguém sabe se ainda vale."""
    aid = _ato(casa)
    _postar(casa, aid, acao="anotacao_de_lavratura",
            observacao="Conferir livro, termo e folha antes de lavrar.")
    r = _linha(casa, aid)
    assert r["observacao"] == "Conferir livro, termo e folha antes de lavrar."
    assert r["observacao_por"] == "CARLA EXEMPLO LIMA"
    assert (r["observacao_em"] or "").startswith("20")


def test_a_anotacao_nao_e_a_anotacao_a_margem(casa):
    """Aquela é ATO — entra no livro, tem selo e não se apaga."""
    aid = _ato(casa)
    _postar(casa, aid, acao="anotacao_de_lavratura", observacao="nota")
    con = sqlite3.connect(casa["banco"])
    n = con.execute("SELECT COUNT(*) FROM nt_ato_anotacoes").fetchone()[0]
    con.close()
    assert n == 0, "a nota de trabalho não pode virar anotação à margem"


def test_a_anotacao_fica_visivel_depois_de_lavrado(casa):
    """Ela é o registro do que foi conferido antes de escrever no livro."""
    aid = _ato(casa)
    _postar(casa, aid, acao="anotacao_de_lavratura", observacao="conferido")
    con = sqlite3.connect(casa["banco"])
    with con:
        con.execute("UPDATE nt_atos SET situacao='LAVRADO', livro='30', "
                    "folha='12', termo='1234' WHERE id=?", (aid,))
    con.close()
    html = casa["cliente"].get(f"/notas/atos/{aid}").get_data(as_text=True)
    assert "conferido" in html and "Anotações antes da lavratura" in html


# ------------------------------------------------- o selo


def test_a_tela_oferece_o_item_medido_e_nao_um_campo_livre(casa):
    """Item digitado à mão é o erro que só aparece no selo recusado."""
    aid = _ato(casa)
    html = casa["cliente"].get(f"/notas/atos/{aid}").get_data(as_text=True)
    assert 'name="codigo_tj"' in html
    assert "13.2" in html, "o item que a casa usou 13 vezes tem de estar lá"


def test_escritura_de_120_mil_mostra_faixa_13_1_13_e_recusa_item_incorreto(casa):
    aid = _ato(casa, valor_transacao=12000000)
    con = sqlite3.connect(casa["banco"])
    with con:
        con.execute("UPDATE cx_vigencias SET vigente=0")
        con.execute("INSERT INTO cx_vigencias (codigo, descricao, vigente) "
                    "VALUES (10022, '2026', 1)")
        con.execute("INSERT INTO cx_faixas "
                    "(tabela, vigencia, de, ate, codigo_tj) "
                    "VALUES (3, 10022, '107463,98', '134329,95', '13.1.13')")
    con.close()
    html = casa["cliente"].get(f"/notas/atos/{aid}").get_data(as_text=True)
    assert '<option value="13.1.13"' in html
    assert '<option value="13.2"' not in html
    resposta = _postar(casa, aid, acao="lancar", paginas="2", codigo_tj="13.2")
    assert "exige o item 13.1.13" in resposta
    assert not (_linha(casa, aid)["livro"] or "").strip()


def test_a_tela_da_procuracao_pergunta_qual_das_tres(casa):
    aid = _ato(casa, tipo="PROCURACAO")
    html = casa["cliente"].get(f"/notas/atos/{aid}").get_data(as_text=True)
    assert 'name="especie_procuracao"' in html
    assert "PODERES_ESPECIFICOS" in html and "SIMPLES" in html


def test_a_tela_da_ata_oferece_o_item_proprio_e_o_selo_automatico(casa):
    aid = _ato(casa, tipo="ATA")
    html = casa["cliente"].get(f"/notas/atos/{aid}").get_data(as_text=True)
    assert 'name="codigo_tj"' in html
    assert "13.14.1" in html and "item próprio desta espécie" in html
    assert "não sela sozinha" not in html


def test_a_ata_de_usucapiao_sem_valor_explica_o_bloqueio(casa):
    aid = _ato(casa, tipo="ATA_USUCAPIAO")
    html = casa["cliente"].get(f"/notas/atos/{aid}").get_data(as_text=True)
    assert "valor do imóvel" in html
    assert "13.14.3" in html and "13.1" in html


def test_o_selo_sai_sozinho_no_ato_ja_lancado(casa):
    """O pedido leva livro e folha: o selo vem depois do lançamento."""
    from selador_de_bancada import ligar_o_selador
    aid = _ato(casa, situacao="LAVRADO", livro="30", folha="12", termo="1234")
    with ligar_o_selador(casa):
        _postar(casa, aid, acao="selar", codigo_tj="13.2")
    r = _linha(casa, aid)
    assert (r["selo"] or "").strip(), "o ato ficou sem selo"
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    selo = con.execute(
        "SELECT * FROM sd_selos WHERE tabela='nt_atos' AND ato_id=?",
        (aid,)).fetchone()
    con.close()
    assert selo is not None, "o selo tem de entrar no razão, amarrado ao ato"
    assert selo["caminho"] == "/selo/notas/ato-declarado/sem-valor"


def test_o_selo_da_ata_sai_pelo_sistema(casa):
    """Regressão do caso real: a trava antiga nem chamava o selador."""
    from selador_de_bancada import ligar_o_selador
    aid = _ato(casa, tipo="ATA", situacao="LAVRADO", livro="1", folha="1",
               termo="1")
    with ligar_o_selador(casa) as aparelho:
        html = _postar(casa, aid, acao="selar", codigo_tj="13.14.1")
    r = _linha(casa, aid)
    assert (r["selo"] or "").strip(), html
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    selo = con.execute(
        "SELECT * FROM sd_selos WHERE tabela='nt_atos' AND ato_id=?",
        (aid,)).fetchone()
    con.close()
    assert selo is not None
    assert selo["caminho"] == "/selo/notas/ato-declarado/sem-valor"
    enviado = next(p for p in aparelho.pedidos
                   if p["caminho"] == selo["caminho"])
    pedido = json.loads(enviado["corpo"])
    assert pedido["ato"]["codigo"] == "13.14.1"
    assert pedido["selo"]["livro"] == "1"


def test_ato_que_ja_tem_selo_nao_compra_outro(casa):
    """Dois selos para o mesmo ato é o dinheiro da serventia saindo duas vezes."""
    aid = _ato(casa, situacao="LAVRADO", livro="30", folha="12",
               selo="ESCRIT000000AAAAAAAAAAAAAAAA")
    html = casa["cliente"].get(f"/notas/atos/{aid}").get_data(as_text=True)
    assert "já está selado" in html
    assert 'value="selar"' not in html


def test_sem_item_marcado_o_ato_fica_sem_selo_e_a_tela_diz(casa):
    """O item é escolha de quem atende — a média da casa não serve ao caso."""
    aid = _ato(casa, situacao="LAVRADO", livro="30", folha="12")
    html = _postar(casa, aid, acao="selar", codigo_tj="")
    assert "Marque o item" in html
    assert not (_linha(casa, aid)["selo"] or "").strip()


def test_o_selo_a_mao_entra_no_razao(casa):
    """O buraco declarado em 01/09: a tela gravava a coluna e o razão ficava vazio."""
    aid = _ato(casa, situacao="LAVRADO", livro="30", folha="12")
    casa["db"].set_settings({"ri_cns": "000000"})
    _postar(casa, aid, acao="selo", selo="ESCRIT000000ZZZZZZZZZZZZZZ12")
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    selo = con.execute(
        "SELECT * FROM sd_selos WHERE tabela='nt_atos' AND ato_id=?",
        (aid,)).fetchone()
    con.close()
    assert selo is not None, "o selo digitado à mão não entrou no razão"
    assert (_linha(casa, aid)["selo"] or "") == "ESCRIT000000ZZZZZZZZZZZZZZ12"


def test_o_selo_de_outra_serventia_e_recusado(casa):
    """O CNS é conferido: selo de outro cartório digitado por engano não entra."""
    aid = _ato(casa, situacao="LAVRADO", livro="30", folha="12")
    casa["db"].set_settings({"ri_cns": "000000"})
    html = _postar(casa, aid, acao="selo",
                   selo="ESCRIT999999ZZZZZZZZZZZZZZ12")
    assert "não é desta serventia" in html
    assert not (_linha(casa, aid)["selo"] or "").strip()


# ------------------------------------------------- lançar e selar no mesmo clique


def _abrir_pela_tela(casa, tipo="ESCRITURA") -> int:
    html = casa["cliente"].get("/notas/atos/novo").get_data(as_text=True)
    casa["cliente"].post("/notas/atos/novo",
                         data={"csrf_token": _token(html), "tipo": tipo,
                               "interessado": "MARIA DAS DORES"},
                         follow_redirects=True)
    con = sqlite3.connect(casa["banco"])
    aid = int(con.execute("SELECT MAX(id) FROM nt_atos").fetchone()[0])
    con.close()
    return aid


def test_lancar_no_livro_ja_pede_o_selo(casa):
    """«O selo é emitido quando praticado o ato» — 27/08/2026.

    O pedido leva livro e folha, e por isso ele acontece logo depois do
    lançamento, no mesmo clique.
    """
    from selador_de_bancada import ligar_o_selador
    aid = _abrir_pela_tela(casa)
    _postar(casa, aid, acao="teor", teor="<p>Teor da escritura.</p>")
    with ligar_o_selador(casa):
        html = _postar(casa, aid, acao="lancar", paginas="2",
                       codigo_tj="13.2")
    r = _linha(casa, aid)
    assert (r["livro"] or "").strip(), "o ato tinha de estar no livro"
    assert (r["selo"] or "").strip(), f"o ato saiu do livro sem selo: {html[:0]}"
    con = sqlite3.connect(casa["banco"])
    n = con.execute("SELECT COUNT(*) FROM sd_selos WHERE tabela='nt_atos' "
                    "AND ato_id=?", (aid,)).fetchone()[0]
    con.close()
    assert n == 1, "o selo tem de entrar no razão, amarrado ao ato"


def test_lancar_sem_item_recusa_antes_de_ocupar_o_livro(casa):
    """Sem o item não há pedido de selo, portanto o lançamento não começa."""
    aid = _abrir_pela_tela(casa)
    _postar(casa, aid, acao="teor", teor="<p>Teor da escritura.</p>")
    html = _postar(casa, aid, acao="lancar", paginas="2", codigo_tj="")
    r = _linha(casa, aid)
    assert not (r["livro"] or "").strip()
    assert not (r["selo"] or "").strip()
    assert "NÃO lançado" in html and "item da tabela" in html


def test_recusa_do_selador_suspende_e_o_mesmo_ato_pode_ser_selado(casa):
    """Falha de rede não deixa LAVRADO; a correção reaproveita o mesmo ato."""
    from selador_de_bancada import ligar_o_selador

    aid = _abrir_pela_tela(casa)
    _postar(casa, aid, acao="teor", teor="<p>Teor da escritura.</p>")
    with ligar_o_selador(casa) as aparelho:
        aparelho.recusar_com = (400, {"message": "item recusado pelo TJMA"})
        html = _postar(casa, aid, acao="lancar", paginas="2",
                       codigo_tj="13.2")
    r = _linha(casa, aid)
    assert r["situacao"] == "SUSPENSO_SELO"
    assert not (r["selo"] or "").strip()
    assert "NÃO concluído" in html and "item recusado" in html

    with ligar_o_selador(casa):
        _postar(casa, aid, acao="selar", codigo_tj="13.2")
    r = _linha(casa, aid)
    assert r["situacao"] == "LAVRADO"
    assert (r["selo"] or "").strip()
