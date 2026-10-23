"""A IA revisa as transcrições contra a página escaneada — LH11, pedido do
oficial em 21/10/2026.

O que se guarda, com a IA DE MENTIRA (como nos testes da revisão prévia e da
leitura dos anexos): a divergência grave é achada e mostrada no quadro da
certidão; a emissão com grave não resolvida pede justificativa e a grava; a IA
fora do ar não trava a certidão e a tela diz que ela saiu sem revisão; texto e
página iguais não pagam de novo; o lote começa pelo livro mais antigo, respeita
o teto da rodada e retoma de onde parou; e com a imagem desligada a imagem não
sobe.

E as ressalvas da revisão do LH11, fechadas no LH12: a emissão reconfere a
revisão com a linha presa, dentro da transação que numera, e grava a conta lida
ali; o esquema nasce na subida, e não na emissão; a rodada do lote lê o lote
preso e não cobre a pausa pedida no meio; o número de matrícula gigante não
derruba a lista; e o teste fala com o banco pela porta da casa.

E a ressalva da revisão do LH12, fechada no LH15, com a emissão SEM a ponte (a
transação do psycopg, como vai ficar): o erro de banco na reconferência fica no
SAVEPOINT dela e a certidão sai «sem revisão», sem 500; duas emissões ao mesmo
tempo esperam pela trava do número, e não pela linha da revisão; e o lote que
não parou não se diz parado.

OS DADOS SÃO FICTÍCIOS (LGPD): a matrícula 9.001 e as pessoas são de exemplo, e
a página é uma imagem desenhada aqui.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import banco_pg                                                  # noqa: E402
import revisao_previa as RP                                      # noqa: E402
import revisao_transcricao as RT                                 # noqa: E402
import revisao_transcricao_lote as RTL                           # noqa: E402
from bd_nativo import banco                                      # noqa: E402

SENHA = "Senha#12345"
TEOR = ("<p>MATRÍCULA 9.001 - IMÓVEL: Chácara Exemplo, com a área de 12,2933 ha, "
        "confrontando ao norte com terras de Fulano de Exemplo.</p>"
        "<p>R-01/9.001 - Pela escritura de 16 de julho de 1979, BELTRANA DE EXEMPLO, "
        "CPF 000.000.001-91, vendeu o imóvel a CICRANO DE EXEMPLO.</p>")
GRAVE_E_LEVE = json.dumps({
    "divergencias": [
        {"gravidade": "GRAVE", "o_que": "area", "pagina": 1, "trecho": "12,2933 ha",
         "texto_diz": "12,2933 ha", "pagina_diz": "22,2933 ha"},
        {"gravidade": "LEVE", "o_que": "grafia", "pagina": 1, "trecho": "Chácara",
         "texto_diz": "Chácara", "pagina_diz": "Chacara"}],
    "avisos": [{"pagina": 1, "o_que": "o canto de baixo da página está ilegível"}],
    "parecer": "a área diverge"})
SEM_NADA = json.dumps({"divergencias": [], "avisos": [], "parecer": "confere"})


class _IA:
    """A IA de mentira: guarda o que subiu e devolve a resposta combinada."""

    def __init__(self, resposta=SEM_NADA):
        self.resposta, self.pedidos = resposta, []

    def __call__(self, pasta, *, provedor, sistema, conversa, ferramentas, modelo,
                 maximo_de_saida, **registro):
        self.pedidos.append({"sistema": sistema, "texto": conversa[0]["texto"],
                             "imagens": conversa[0].get("imagens") or [],
                             "modelo": modelo, **registro})
        return {"texto": self.resposta, "modelo": modelo, "entrada": 6000, "saida": 800}


def _fora_do_ar(*_a, **_k):
    raise OSError("sem rede")


def _pagina(caminho: Path, texto: str = "pagina de exemplo") -> Path:
    """Uma página escaneada de mentira, SEM EXTENSÃO, como as do E-Ofício."""
    from PIL import Image, ImageDraw
    im = Image.new("L", (800, 1100), 255)
    ImageDraw.Draw(im).text((40, 40), texto, fill=0)
    im.save(caminho, format="PNG")
    return caminho


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _con(casa):
    """A conexão do teste com o banco da casa, pela PORTA DA CASA
    (`Database.connect`, a mesma das rotas) — LH12. O `sqlite3.connect` cru
    só chegava ao PostgreSQL pelo desvio do conftest; sem ele, abria o
    arquivo-marca vazio como SQLite (ver
    `test_o_teste_fala_com_o_postgresql_da_casa_sem_o_desvio_do_conftest`)."""
    return casa["db"].connect()


def _ficha(casa, numero="9001", teor=TEOR, paginas=1, livro="2") -> int:
    con = _con(casa)
    bd = banco(con)
    mid = bd.escrever(
        """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao, tipo_ficha,
                                      teor, origem, criado_em)
           VALUES (%s, %s, %s, 'ATIVA', 'ACERVO', %s, 'EOFICIO', '2026-10-21T10:00:00')
           RETURNING id""", (numero, livro, livro, teor))[0]["id"]
    for n in range(1, paginas + 1):
        arquivo = _pagina(casa["paginas"] / f"{int(numero):08d}.{n:04d}")
        bd.escrever("""INSERT INTO ri_imagens (matricula_id, nome_arquivo, caminho, ordem)
                       VALUES (%s, %s, %s, %s)""", (mid, arquivo.name, str(arquivo), n))
    con.commit()
    con.close()
    return mid


@pytest.fixture()
def casa(cg_casa, monkeypatch, tmp_path):
    import agente_provedores as AP
    monkeypatch.setattr(AP, "tem_chave", lambda pasta, prov=None: True)
    # A LEITURA EM SEGUNDO PLANO NÃO SAI DO TESTE: o botão só a agenda.
    agendadas = []
    monkeypatch.setattr(RT, "ler_em_segundo_plano",
                        lambda banco, pasta, rid, raiz: agendadas.append(rid))
    monkeypatch.setattr(RTL, "rodar_em_segundo_plano",
                        lambda banco, pasta, raiz, lote: agendadas.append(("lote", lote)))
    db = cg_casa["db"]
    db.create_user("balcao", "LAURA EXEMPLO", SENHA, "ADMIN")
    db.set_settings({"ri_cidade": "Cidade Exemplo", "ri_uf": "MA", "ri_cns": "000000"})
    paginas = tmp_path / "eoficio"
    paginas.mkdir()
    c = cg_casa["app"].test_client()
    c.post("/login", data={"username": "balcao", "password": SENHA,
                           "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {**cg_casa, "cliente": c, "paginas": paginas, "agendadas": agendadas,
            "raiz": Path(cg_casa["banco"]).parent / "arquivos"}


def _revisar(casa, mid, ia) -> int:
    con = _con(casa)
    rid, nova = RT.pedir(con, mid, raiz=casa["raiz"], usuario="LAURA EXEMPLO")
    con.commit()
    con.close()
    assert nova
    RT.executar(Path(casa["banco"]), casa["dados"], rid, raiz=casa["raiz"], conversar=ia)
    return rid


def _mostrar(casa, rid) -> dict:
    con = _con(casa)
    try:
        return RT.mostrar(con, rid)
    finally:
        con.close()


def _dados_da_emissao(ficha: str, **campos) -> dict:
    return {"csrf_token": _token(ficha), "tipo": "INTEIRO_TEOR", "fonte_corpo": "TEXTO",
            "requerente": "REQUERENTE DE EXEMPLO",
            "selo_texto": "CERINT000000EXEMPLO000000001", **campos}


def _emitir(casa, mid, **campos):
    ficha = casa["cliente"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    return casa["cliente"].post(f"/registro-imoveis/{mid}/certidao",
                                data=_dados_da_emissao(ficha, **campos),
                                follow_redirects=True)


def _certidoes(casa, mid) -> int:
    con = _con(casa)
    try:
        return banco(con).valor("SELECT count(*) AS n FROM ri_certidoes WHERE matricula_id = %s",
                                (mid,))
    finally:
        con.close()


# ------------------------------------------------------------ a revisão de uma ficha

def test_a_divergencia_grave_e_achada_e_mostrada_no_quadro_da_certidao(casa):
    mid = _ficha(casa)
    ia = _IA(GRAVE_E_LEVE)
    rid = _revisar(casa, mid, ia)
    # o modelo bom (o da revisão prévia), a página como imagem e o texto transcrito
    (pedido,) = ia.pedidos
    assert pedido["modelo"] == RP.MODELO
    assert len(pedido["imagens"]) == 1 and pedido["imagens"][0]["mime"] == "image/jpeg"
    assert "12,2933 ha" in pedido["texto"] and "a 1ª imagem é a página 1 de 1" in pedido["texto"]
    assert (pedido["finalidade"], pedido["modulo"], pedido["mascarado"]) == (
        "revisao_transcricao", "revisao_transcricao", False)
    assert pedido["referencia"] == f"ri_transcricao_revisoes:{rid}"
    r = _mostrar(casa, rid)
    assert (r["situacao"], r["graves"], r["leves"], r["graves_pendentes"]) == ("PRONTA", 1, 1, 1)
    assert r["divergencias"][0]["pagina_diz"] == "22,2933 ha"
    # página ilegível é AVISO, e não divergência
    assert [a["o_que"] for a in r["avisos"]] == ["o canto de baixo da página está ilegível"]
    html = casa["cliente"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    assert 'id="certidao-transcricao"' in html and "22,2933 ha" in html
    assert "1 divergência(s) GRAVE(S)" in html and "transcricao_justificativa" in html
    imagem_id = r["lista_de_paginas"][0]["imagem_id"]
    assert f"/registro-imoveis/imagem/{imagem_id}?p=0" in html, "a página não tem link"


def test_cpf_trocado_e_grave_mesmo_que_a_ia_diga_leve():
    """A gravidade das categorias do pedido é régua do código."""
    r = RT.ler_resposta(json.dumps({"divergencias": [
        {"gravidade": "LEVE", "o_que": "documento", "pagina": 1, "trecho": "CPF",
         "texto_diz": "000.000.001-91", "pagina_diz": "000.000.001-19"},
        {"gravidade": "LEVE", "o_que": "pontuacao", "pagina": 7, "trecho": "1979,",
         "texto_diz": "1979,", "pagina_diz": "1979."}]}), [1, 2])
    assert [d["gravidade"] for d in r["divergencias"]] == ["GRAVE", "LEVE"]
    assert r["divergencias"][1]["pagina"] is None, "página que a IA não viu não vale"


def test_pagina_sem_arquivo_vira_aviso_e_nao_trava_a_leitura(casa):
    mid = _ficha(casa)
    con = _con(casa)
    banco(con).escrever("""INSERT INTO ri_imagens (matricula_id, nome_arquivo, caminho, ordem)
                           VALUES (%s, '00009001.0002', %s, 2)""",
                        (mid, str(casa["paginas"] / "nao_existe")))
    con.commit()
    con.close()
    ia = _IA()
    r = _mostrar(casa, _revisar(casa, mid, ia))
    assert r["situacao"] == "PRONTA" and r["paginas"] == 2 and r["paginas_vistas"] == 1
    assert any("Página 2" in a["o_que"] and "não está na pasta" in a["o_que"]
               for a in r["avisos"])
    assert len(ia.pedidos[0]["imagens"]) == 1


def test_texto_e_pagina_iguais_nao_pagam_de_novo(casa):
    mid = _ficha(casa)
    ia = _IA(GRAVE_E_LEVE)
    rid = _revisar(casa, mid, ia)
    con = _con(casa)
    de_novo, nova = RT.pedir(con, mid, raiz=casa["raiz"])
    con.commit()                     # a trava da procura não espera pela rota
    assert (de_novo, nova) == (rid, False)
    # pelo botão também: a rota não agenda leitura nenhuma
    html = casa["cliente"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    resposta = casa["cliente"].post(f"/registro-imoveis/{mid}/transcricao/revisar",
                                    data={"csrf_token": _token(html)}, follow_redirects=True)
    assert "não se paga de novo" in resposta.get_data(as_text=True)
    assert casa["agendadas"] == [] and len(ia.pedidos) == 1
    # vírgula mudada no teor é outro texto: aí sim, revisão nova
    banco(con).escrever("UPDATE ri_matriculas SET teor = %s WHERE id = %s",
                        (TEOR + "<p>.</p>", mid))
    con.commit()
    outra, nova = RT.pedir(con, mid, raiz=casa["raiz"])
    con.commit()
    con.close()
    assert nova and outra != rid


def test_o_botao_pede_a_revisao_e_a_leitura_vai_para_o_segundo_plano(casa):
    mid = _ficha(casa)
    html = casa["cliente"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    assert "Revisar a transcrição com IA" in html and 'id="form-transcricao-ia"' in html
    resposta = casa["cliente"].post(f"/registro-imoveis/{mid}/transcricao/revisar",
                                    data={"csrf_token": _token(html)}, follow_redirects=True)
    assert "A IA está conferindo a transcrição" in resposta.get_data(as_text=True)
    (rid,) = casa["agendadas"]
    con = _con(casa)
    try:
        detalhes = [json.loads(r["details"]) for r in banco(con).ler(
            """SELECT details FROM audit_logs WHERE action = 'RI_TRANSCRICAO_REVISAO_PEDIDA'
             ORDER BY id""")]
    finally:
        con.close()
    assert detalhes == [{"matricula_id": mid}], "a auditoria leva só ids"
    assert _mostrar(casa, rid)["situacao"] == "PENDENTE"


def test_imagem_desligada_nao_manda_imagem_e_diz_que_nao_viu_a_pagina(casa):
    casa["db"].set_settings({RT.CHAVE_IMAGEM: "0"})
    mid = _ficha(casa)
    ia = _IA()
    r = _mostrar(casa, _revisar(casa, mid, ia))
    (pedido,) = ia.pedidos
    assert pedido["imagens"] == [] and pedido["sistema"] == RT.INSTRUCAO_SEM_IMAGEM
    assert "CADASTRO DA FICHA" in pedido["texto"]
    assert r["com_imagem"] is False and r["paginas_vistas"] == 0
    assert any("NÃO viu a página" in a["o_que"] for a in r["avisos"])
    html = casa["cliente"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    assert "O envio da imagem está desligado" in html


def test_so_o_admin_desliga_a_imagem_e_a_decisao_esta_na_tela(casa):
    html = casa["cliente"].get("/configuracoes").get_data(as_text=True)
    assert 'id="cfg-revisao-transcricao"' in html and "21/10/2026" in html
    casa["cliente"].post("/configuracoes/revisao-transcricao",
                         data={"csrf_token": _token(html), "teto_paginas": "120",
                               "teto_custo": "7,50"}, follow_redirects=True)
    con = _con(casa)
    try:
        assert RT.configuracao(con) == {"manda_imagem": False, "teto_paginas": 120,
                                        "teto_custo": 7.5}
    finally:
        con.close()


# ------------------------------------------------------------ a certidão

def test_a_emissao_com_grave_pede_justificativa_e_a_grava(casa):
    mid = _ficha(casa)
    rid = _revisar(casa, mid, _IA(GRAVE_E_LEVE))
    recusa = _emitir(casa, mid).get_data(as_text=True)
    assert "divergência(s) GRAVE(S)" in recusa and "mínimo de dez" in recusa
    assert _certidoes(casa, mid) == 0, "a recusa veio depois de numerar"
    assert "SEM a revisão" not in recusa
    _emitir(casa, mid, transcricao_justificativa="ok")
    assert _certidoes(casa, mid) == 0, "justificativa curta não basta"
    feita = _emitir(casa, mid, transcricao_justificativa=(
        "conferido no livro físico: a área certa é a do texto")).get_data(as_text=True)
    assert _certidoes(casa, mid) == 1
    assert "a justificativa ficou gravada com a certidão" in feita
    con = _con(casa)
    try:
        bd = banco(con)
        (situacao, graves, justificativa, por, revisao) = bd.um(
            """SELECT situacao, graves_pendentes, justificativa, emitida_por, revisao_id
                 FROM ri_transcricao_emissoes ORDER BY id""").values()
        auditoria = "\n".join(r["details"] for r in bd.ler(
            """SELECT details FROM audit_logs
                WHERE action IN ('RI_CERTIDAO_EMITIDA', 'RI_CERTIDAO_TRANSCRICAO_RECUSADA')
             ORDER BY id"""))
    finally:
        con.close()
    assert (situacao, graves, por, revisao) == ("PRONTA", 1, "LAURA EXEMPLO", rid)
    assert justificativa.startswith("conferido no livro")
    # NA AUDITORIA, SÓ IDS, CONTAGENS E A GRAVIDADE — nem o texto, nem a justificativa
    assert '"transcricao_graves": 1' in auditoria
    assert auditoria.count('"graves": 1') == 2, "as duas recusas ficam na auditoria"
    for palavra in ("12,2933", "22,2933", "conferido no livro", "BELTRANA"):
        assert palavra not in auditoria


def test_divergencia_dada_por_conferida_deixa_de_pedir_justificativa(casa):
    mid = _ficha(casa)
    rid = _revisar(casa, mid, _IA(GRAVE_E_LEVE))
    con = _con(casa)
    with pytest.raises(RT.TranscricaoError, match="gerente ou do administrador"):
        RT.conferir_divergencias(con, rid, [(0, "conferido no livro, folha 3")], papel="USER")
    with pytest.raises(RT.TranscricaoError, match="dez letras"):
        RT.conferir_divergencias(con, rid, [(0, "ok")], papel="MANAGER")
    con.rollback()
    con.close()
    html = casa["cliente"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    casa["cliente"].post(f"/registro-imoveis/transcricao/{rid}/conferir",
                         data={"csrf_token": _token(html), "indice": "0",
                               "obs_0": "a página escaneada está borrada; o livro diz 12"},
                         follow_redirects=True)
    assert _mostrar(casa, rid)["graves_pendentes"] == 0
    _emitir(casa, mid)
    assert _certidoes(casa, mid) == 1


def test_ia_fora_do_ar_nao_trava_e_a_tela_diz_que_saiu_sem_revisao(casa):
    mid = _ficha(casa)
    rid = _revisar(casa, mid, _fora_do_ar)
    assert _mostrar(casa, rid)["situacao"] == "ERRO"
    pagina = _emitir(casa, mid).get_data(as_text=True)
    assert _certidoes(casa, mid) == 1
    assert "saiu SEM a revisão da transcrição" in pagina and "a IA não respondeu" in pagina
    con = _con(casa)
    try:
        assert banco(con).um("SELECT situacao, revisao_id FROM ri_transcricao_emissoes "
                             "ORDER BY id") == {"situacao": "ERRO", "revisao_id": rid}
    finally:
        con.close()


def test_sem_revisao_a_certidao_sai_e_diz_que_saiu_sem_ela(casa):
    mid = _ficha(casa)
    pagina = _emitir(casa, mid).get_data(as_text=True)
    assert _certidoes(casa, mid) == 1
    assert "saiu SEM a revisão da transcrição" in pagina


def test_leitura_em_andamento_pede_para_esperar(casa):
    mid = _ficha(casa)
    con = _con(casa)
    RT.pedir(con, mid, raiz=casa["raiz"])
    con.commit()
    con.close()
    pagina = _emitir(casa, mid).get_data(as_text=True)
    assert "ainda está lendo" in pagina and _certidoes(casa, mid) == 0


def test_sem_chave_da_ia_a_etapa_nao_existe(casa, monkeypatch):
    import agente_provedores as AP
    monkeypatch.setattr(AP, "tem_chave", lambda pasta, prov=None: False)
    mid = _ficha(casa)
    ficha = casa["cliente"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    assert 'id="certidao-transcricao"' not in ficha, "sem IA o quadro não aparece"
    pagina = _emitir(casa, mid).get_data(as_text=True)
    assert _certidoes(casa, mid) == 1 and "SEM a revisão" not in pagina
    con = _con(casa)
    try:
        assert not RT.ligada(con, casa["dados"])
        assert banco_sem_linhas(con, "ri_transcricao_emissoes")
    finally:
        con.close()


def banco_sem_linhas(con, tabela: str) -> bool:
    from bd_nativo import banco
    bd = banco(con)
    return not bd.tem_tabela(tabela) or not bd.valor(f"SELECT count(*) FROM {tabela}")


# ------------------------------------------------------------ o lote

def _lote(casa, **filtro) -> int:
    con = _con(casa)
    lote_id = RTL.criar(con, {"so_sem_revisao": True, **filtro}, usuario="LAURA EXEMPLO")
    RTL.comecar(con, lote_id)
    con.commit()
    con.close()
    return lote_id


def _rodar(casa, lote_id, ia) -> str:
    return RTL.rodar(Path(casa["banco"]), casa["dados"], casa["raiz"], lote_id, conversar=ia)


def _itens(casa, lote_id) -> list[tuple]:
    con = _con(casa)
    try:
        return [(r["numero"], r["situacao"]) for r in banco(con).ler(
            """SELECT m.numero, i.situacao FROM ri_transcricao_lote_itens i
                 JOIN ri_matriculas m ON m.id = i.matricula_id
                WHERE i.lote_id = %s ORDER BY i.ordem, i.id""", (lote_id,))]
    finally:
        con.close()


def test_o_lote_comeca_pelo_mais_antigo_respeita_o_teto_e_retoma(casa):
    for numero in ("300", "4", "57"):
        _ficha(casa, numero=numero)
    casa["db"].set_settings({RT.CHAVE_TETO_PAGINAS: "2"})
    lote_id = _lote(casa)
    assert [n for n, _ in _itens(casa, lote_id)] == ["4", "57", "300"], "o mais antigo primeiro"
    ia = _IA()
    assert _rodar(casa, lote_id, ia) == RTL.PAUSADO
    assert len(ia.pedidos) == 2, "passou do teto de páginas da rodada"
    assert [s for _, s in _itens(casa, lote_id)] == ["FEITO", "FEITO", "A_FAZER"]
    con = _con(casa)
    lote = RTL.ver(con, lote_id)
    assert "teto de páginas" in lote["mensagem"] and lote["paginas_lidas"] == 2
    # continuar abre rodada nova e retoma de onde parou — o que foi lido não se paga
    RTL.comecar(con, lote_id)
    con.commit()
    con.close()
    assert _rodar(casa, lote_id, ia) == RTL.TERMINADO
    assert len(ia.pedidos) == 3
    assert [s for _, s in _itens(casa, lote_id)] == ["FEITO", "FEITO", "FEITO"]


def test_o_lote_para_no_teto_de_custo(casa):
    for numero in ("10", "11", "12"):
        _ficha(casa, numero=numero)
    # a chamada da IA de mentira (6.000 + 800 tokens no Opus) custa US$ 0,04, e a
    # prevista para a seguinte, ~0,038: o teto de 0,05 deixa passar uma só
    casa["db"].set_settings({RT.CHAVE_TETO_CUSTO: "0.05"})
    lote_id = _lote(casa)
    ia = _IA()
    assert _rodar(casa, lote_id, ia) == RTL.PAUSADO
    assert len(ia.pedidos) == 1
    con = _con(casa)
    try:
        assert "teto de custo" in RTL.ver(con, lote_id)["mensagem"]
    finally:
        con.close()


def test_ficha_ja_revisada_entra_no_lote_reaproveitada_e_sem_custo(casa):
    mid = _ficha(casa, numero="5")
    _ficha(casa, numero="6")
    _revisar(casa, mid, _IA(GRAVE_E_LEVE))
    lote_id = _lote(casa, so_sem_revisao=False)
    ia = _IA()
    assert _rodar(casa, lote_id, ia) == RTL.TERMINADO
    assert [s for _, s in _itens(casa, lote_id)] == ["REAPROVEITADO", "FEITO"]
    assert len(ia.pedidos) == 1


def test_a_ia_fora_do_ar_pausa_o_lote_e_a_ficha_volta_para_a_fila(casa):
    for numero in ("20", "21", "22", "23"):
        _ficha(casa, numero=numero)
    lote_id = _lote(casa)
    assert _rodar(casa, lote_id, _fora_do_ar) == RTL.PAUSADO
    assert [s for _, s in _itens(casa, lote_id)] == ["A_FAZER"] * 4
    con = _con(casa)
    lote = RTL.ver(con, lote_id)
    assert "não respondeu em 3 fichas seguidas" in lote["mensagem"]
    RTL.comecar(con, lote_id)
    con.commit()
    con.close()
    assert _rodar(casa, lote_id, _IA()) == RTL.TERMINADO
    assert [s for _, s in _itens(casa, lote_id)] == ["FEITO"] * 4


def test_a_tela_do_lote_conta_estima_e_mostra_o_grave_primeiro(casa):
    _ficha(casa, numero="40")
    _ficha(casa, numero="41", paginas=3)
    html = casa["cliente"].get("/registro-imoveis/transcricoes/lote").get_data(as_text=True)
    assert "Revisar transcrições em lote (IA)" in html
    assert "<strong>2 ficha(s)</strong>" in html and "<strong>4 página(s)</strong>" in html
    assert "3 chamada(s) ao provedor" in html
    respostas = iter([SEM_NADA, GRAVE_E_LEVE, GRAVE_E_LEVE])

    class _IAporFicha(_IA):
        def __call__(self, *a, **k):
            self.resposta = next(respostas)
            return super().__call__(*a, **k)
    resposta = casa["cliente"].post("/registro-imoveis/transcricoes/lote",
                                    data={"csrf_token": _token(html), "so_sem_revisao": "1"})
    lote_id = int(resposta.headers["Location"].rstrip("/").split("/")[-1])
    assert casa["agendadas"] == [("lote", lote_id)]
    assert _rodar(casa, lote_id, _IAporFicha()) == RTL.TERMINADO
    tela = casa["cliente"].get(f"/registro-imoveis/transcricoes/lote/{lote_id}"
                               ).get_data(as_text=True)
    assert tela.index(">41<") < tela.index(">40<"), "a ficha com GRAVE vem primeiro"
    assert "página 1" in tela


def test_a_estimativa_usa_o_uso_medido_quando_ha(casa):
    con = _con(casa)
    try:
        antes = RT.estimativa(con, [2, 3])
        assert antes["chamadas"] == 3 and antes["medido"] == 0
        import ia_uso as USO
        USO.init_ia_schema(con)
        banco(con).escrever("""INSERT INTO ia_uso (quando, modulo, finalidade, tokens_entrada,
                                           tokens_saida, resultado)
                       VALUES ('2026-10-21T10:00:00', 'revisao_transcricao',
                               'revisao_transcricao', 12000, 1800, 'ok')""")
        depois = RT.estimativa(con, [2, 3])
        assert depois["medido"] == 1
        assert depois["custo"] == pytest.approx(3 * RT.custo(RT.MODELO, 12000, 1800))
        assert antes["custo"] == pytest.approx(3 * RT.custo(
            RT.MODELO, RT.TOKENS_DE_ENTRADA_A_PRIORI, RT.TOKENS_DE_SAIDA_A_PRIORI))
    finally:
        con.rollback()
        con.close()


# ------------------------------------------------------------ LH12: as ressalvas do LH11

so_no_postgresql = pytest.mark.skipif(
    not banco_pg.ativo(), reason="a corrida só existe no PostgreSQL")
JUSTIFICATIVA = "conferido no livro físico, folha 3: a área certa é a do texto"


def _psycopg_puro(esquema: str, *, autocommit: bool = False):
    """Uma conexão do psycopg no schema do teste, SEM a ponte — como a
    transação vai ficar quando a ponte sair (com ela, a trava única põe um
    escritor por vez e esconde a falta do `FOR UPDATE`)."""
    import psycopg
    pg = psycopg.connect(banco_pg.dsn(), autocommit=autocommit)
    pg.execute(f'SET search_path TO "{esquema}", public')
    if not autocommit:
        pg.commit()
    return pg


def _esperar_a_espera(vigia, sql: str, parametros) -> bool:
    """Até alguém estar ESPERANDO uma trava (`pg_locks ... NOT granted`)."""
    for _ in range(200):
        if banco(vigia).valor(sql, parametros):
            return True
        time.sleep(0.05)
    return False


def _ao_mesmo_tempo(casa, primeira, segunda):
    """A `primeira` grava e ainda não confirmou; a `segunda` chega no meio,
    por outra conexão. Devolve o erro da segunda (None se ela passou)."""
    con = _con(casa)
    esquema = con.schema
    con.close()
    um, dois = _psycopg_puro(esquema), _psycopg_puro(esquema)
    vigia = _psycopg_puro(esquema, autocommit=True)
    pid = banco(dois).valor("SELECT pg_backend_pid() AS pid")
    saida: dict = {}
    try:
        primeira(um)

        def no_fio():
            try:
                segunda(dois)
                dois.commit()
            except Exception as erro:  # o teste confere qual
                saida["erro"] = erro
                dois.rollback()

        fio = threading.Thread(target=no_fio)
        fio.start()
        saida["esperou"] = _esperar_a_espera(
            vigia, "SELECT count(*) AS n FROM pg_locks WHERE pid = %s AND NOT granted", (pid,))
        um.commit()
        fio.join(30)
    finally:
        for c in (um, dois, vigia):
            c.close()
    assert saida.pop("esperou"), "a segunda não esperou a linha presa pela primeira"
    return saida.get("erro")


def _no_meio_da_emissao(monkeypatch, acao) -> None:
    """Roda `acao` entre a conferência de antes (`conferir_para_emitir`, solta)
    e a transação que numera — o meio em que a certidão saía pela decisão velha.
    Uma vez só: a emissão seguinte do mesmo teste corre sem nada no meio."""
    original = RT.conferir_para_emitir
    feita = []

    def conferir_e_mudar(*a, **k):
        decisao = original(*a, **k)
        if not feita:
            feita.append(1)
            acao()
        return decisao
    monkeypatch.setattr(RT, "conferir_para_emitir", conferir_e_mudar)


def _emissoes(casa) -> list[dict]:
    con = _con(casa)
    try:
        return banco(con).ler("""SELECT situacao, revisao_id, graves_pendentes, justificativa
                                   FROM ri_transcricao_emissoes ORDER BY id""")
    finally:
        con.close()


def _auditoria(casa, acao: str) -> list[dict]:
    con = _con(casa)
    try:
        return [json.loads(r["details"]) for r in banco(con).ler(
            "SELECT details FROM audit_logs WHERE action = %s ORDER BY id", (acao,))]
    finally:
        con.close()


def test_a_conta_gravada_com_a_certidao_e_a_lida_com_a_linha_presa(casa, monkeypatch):
    """A GRAVE é dada por conferida no livro entre a conferência de antes e o
    número. A certidão sai pela régua de dentro da transação, e
    `ri_transcricao_emissoes` grava 0 graves pendentes — e não a conta velha
    da conferência solta (1, com a justificativa de quem já não precisava)."""
    mid = _ficha(casa)
    rid = _revisar(casa, mid, _IA(GRAVE_E_LEVE))

    def dar_por_conferida():
        with casa["db"].transaction() as c:
            RT.conferir_divergencias(c, rid, [(0, "a página está borrada; o livro diz 12")],
                                     usuario="GERENTE EXEMPLO", papel="MANAGER")
    _no_meio_da_emissao(monkeypatch, dar_por_conferida)
    pagina = _emitir(casa, mid, transcricao_justificativa=JUSTIFICATIVA).get_data(as_text=True)
    assert _certidoes(casa, mid) == 1
    assert _emissoes(casa) == [{"situacao": "PRONTA", "revisao_id": rid,
                                "graves_pendentes": 0, "justificativa": None}]
    assert "a justificativa ficou gravada" not in pagina
    (emitida,) = _auditoria(casa, "RI_CERTIDAO_EMITIDA")
    assert emitida["transcricao_graves"] == 0


def test_a_leitura_que_termina_com_grave_no_meio_da_emissao_recusa_a_certidao(casa, monkeypatch):
    """A leitura passou de 15 minutos — a tela e a conferência de antes a dão
    por ERRO, e a certidão sairia «sem revisão» — e termina com GRAVE entre a
    conferência e o número. A régua de dentro da transação a vê: recusa antes
    do número, e a recusa fica na tabela da auditoria (dada fora da transação,
    que segura a trava que a auditoria espera)."""
    mid = _ficha(casa)
    con = _con(casa)
    rid, _ = RT.pedir(con, mid, raiz=casa["raiz"])
    banco(con).escrever("""UPDATE ri_transcricao_revisoes SET situacao = 'LENDO', pedido_em = %s
                            WHERE id = %s""", ("2026-01-01T08:00:00", rid))
    con.commit()
    con.close()
    assert _mostrar(casa, rid)["situacao"] == "ERRO", "a leitura velha já parece perdida"
    _no_meio_da_emissao(monkeypatch, lambda: RT.executar(
        Path(casa["banco"]), casa["dados"], rid, raiz=casa["raiz"], conversar=_IA(GRAVE_E_LEVE)))
    pagina = _emitir(casa, mid).get_data(as_text=True)
    assert _mostrar(casa, rid)["graves_pendentes"] == 1
    assert "divergência(s) GRAVE(S)" in pagina and "SEM a revisão" not in pagina
    assert _certidoes(casa, mid) == 0, "a certidão saiu pela decisão velha (ERRO)"
    assert _emissoes(casa) == []
    assert _auditoria(casa, "RI_CERTIDAO_TRANSCRICAO_RECUSADA") == [
        {"graves": 1, "revisao_id": rid}]
    # com a justificativa, sai — e grava a conta lida dentro da transação
    _emitir(casa, mid, transcricao_justificativa=JUSTIFICATIVA)
    assert _certidoes(casa, mid) == 1
    assert _emissoes(casa) == [{"situacao": "PRONTA", "revisao_id": rid,
                                "graves_pendentes": 1, "justificativa": JUSTIFICATIVA}]


@so_no_postgresql
def test_a_reconferencia_espera_quem_esta_dando_a_divergencia_por_conferida(casa):
    """Sem a ponte: o gerente deu a GRAVE por conferida e ainda não confirmou;
    a reconferência da emissão chega no meio e ESPERA a linha da revisão — e
    lê a conta depois dele (0), e não a de antes (1)."""
    mid = _ficha(casa)
    rid = _revisar(casa, mid, _IA(GRAVE_E_LEVE))
    con = _con(casa)
    try:
        decisao = RT.conferir_para_emitir(con, casa["dados"], casa["raiz"], mid,
                                          justificativa=JUSTIFICATIVA)
    finally:
        con.close()
    assert (decisao["situacao"], decisao["graves_pendentes"]) == ("PRONTA", 1)
    saida: dict = {}
    erro = _ao_mesmo_tempo(
        casa,
        lambda c: RT.conferir_divergencias(c, rid, [(0, "a página está borrada; o livro diz 12")],
                                           usuario="GERENTE EXEMPLO", papel="MANAGER"),
        lambda c: saida.update(r=RT.reconferir_na_emissao(c, decisao, matricula_id=mid,
                                                           justificativa=JUSTIFICATIVA)))
    assert erro is None, erro
    assert (saida["r"]["situacao"], saida["r"]["revisao_id"],
            saida["r"]["graves_pendentes"]) == ("PRONTA", rid, 0)


def test_o_esquema_da_revisao_nasce_na_subida(tmp_path):
    """A subida (`Database.init_schema`) cria as tabelas e os índices da
    revisão e do lote num banco vazio, sem nenhuma revisão ter rodado — a
    emissão não precisa criar nada na transação que numera."""
    import database
    db = database.Database(tmp_path / "cartorio_gestao.sqlite3")
    with db.connect() as con:
        bd = banco(con)
        faltam = [nome for nome in (
            "ri_transcricao_revisoes", "ix_ri_transcricao_revisoes_ficha",
            "ri_transcricao_emissoes", "ix_ri_transcricao_emissoes_certidao",
            "ri_transcricao_lotes", "ri_transcricao_lote_itens",
            "ix_ri_transcricao_lote_itens_lote") if not bd.tem_tabela(nome)]
    assert faltam == [], f"a subida não criou {faltam}"


def test_a_emissao_nao_roda_o_esquema_na_transacao_que_numera(casa, monkeypatch):
    mid = _ficha(casa)
    rid = _revisar(casa, mid, _IA())
    rodou = []
    monkeypatch.setattr(RT, "init_schema", lambda con: rodou.append("revisao"))
    monkeypatch.setattr(RTL, "init_schema", lambda con: rodou.append("lote"))
    _emitir(casa, mid)
    assert _certidoes(casa, mid) == 1
    assert rodou == [], "a emissão rodou o esquema (DDL depois do número)"
    assert _emissoes(casa) == [{"situacao": "PRONTA", "revisao_id": rid,
                                "graves_pendentes": 0, "justificativa": None}]


@so_no_postgresql
def test_a_pausa_pedida_entre_a_leitura_e_o_fim_do_lote_nao_se_perde(casa):
    """A pausa chega quando a rodada já vai gravar TERMINADO (a última ficha
    acabou). Lido solto, o lote saía TERMINADO por cima da pausa; preso, a
    rodada espera a pausa confirmar e fecha o lote PAUSADO, com a frase de
    quem pediu. A pausa vai sem a ponte, como a transação vai ficar sem ela."""
    _ficha(casa, numero="30")
    lote_id = _lote(casa)
    con = _con(casa)
    banco(con).escrever("UPDATE ri_transcricao_lote_itens SET situacao = 'FEITO' "
                        "WHERE lote_id = %s", (lote_id,))
    con.commit()
    esquema = con.schema
    con.close()
    um, vigia = _psycopg_puro(esquema), _psycopg_puro(esquema, autocommit=True)
    saida: dict = {}

    def a_rodada():
        try:
            saida["situacao"] = _rodar(casa, lote_id, _IA())
        except Exception as erro:  # o teste confere
            saida["erro"] = erro
    try:
        assert RTL.pausar(um, lote_id, usuario="LAURA EXEMPLO") == RTL.PAUSANDO
        fio = threading.Thread(target=a_rodada)
        fio.start()
        # a rodada (pela ponte, que dá o nome do schema à conexão) chegou à linha presa
        esperou = _esperar_a_espera(
            vigia, """SELECT count(*) AS n FROM pg_locks l
                        JOIN pg_stat_activity a ON a.pid = l.pid
                       WHERE NOT l.granted AND a.application_name = %s""", (esquema[:60],))
        um.commit()
        fio.join(30)
    finally:
        um.close()
        vigia.close()
    assert esperou, "a rodada não chegou à linha do lote"
    assert "erro" not in saida, saida.get("erro")
    assert saida["situacao"] == RTL.PAUSADO
    con = _con(casa)
    try:
        lote = RTL.ver(con, lote_id)
    finally:
        con.close()
    assert lote["situacao"] == RTL.PAUSADO
    assert "Pausa pedida por LAURA EXEMPLO" in lote["mensagem"]


def test_a_pausa_pedida_durante_a_ficha_nao_e_coberta_pela_pausa_dos_erros(casa):
    """A IA cai três vezes seguidas, e na terceira ficha alguém pede a pausa.
    A pausa dos erros só cobre o lote que ainda roda: o lote fecha PAUSADO
    com a frase de quem pediu, e os erros ficam contados."""
    for numero in ("50", "51", "52"):
        _ficha(casa, numero=numero)
    lote_id = _lote(casa)
    chamadas = []

    def fora_do_ar_e_pausam(*_a, **_k):
        chamadas.append(1)
        if len(chamadas) == RTL.ERROS_SEGUIDOS_PARA_PAUSAR:
            with casa["db"].transaction() as c:
                assert RTL.pausar(c, lote_id, usuario="LAURA EXEMPLO") == RTL.PAUSANDO
        raise OSError("sem rede")
    assert _rodar(casa, lote_id, fora_do_ar_e_pausam) == RTL.PAUSADO
    con = _con(casa)
    try:
        lote = RTL.ver(con, lote_id)
    finally:
        con.close()
    assert lote["situacao"] == RTL.PAUSADO and lote["erros_seguidos"] == 3
    assert "Pausa pedida por LAURA EXEMPLO" in lote["mensagem"]
    assert [s for _, s in _itens(casa, lote_id)] == ["A_FAZER"] * 3


def test_numero_de_matricula_gigante_nao_derruba_a_lista_do_lote(casa):
    """O `bigint` vai até 19 algarismos: o número digitado com 22 estourava a
    ordem da lista, e a tela do lote caía junto."""
    _ficha(casa, numero="7")
    _ficha(casa, numero="1234567890123456789012")
    con = _con(casa)
    try:
        assert [c["numero"] for c in RTL.candidatos(con)] == ["7", "1234567890123456789012"]
    finally:
        con.close()
    tela = casa["cliente"].get("/registro-imoveis/transcricoes/lote")
    assert tela.status_code == 200
    assert "<strong>2 ficha(s)</strong>" in tela.get_data(as_text=True)


def test_o_teste_fala_com_o_postgresql_da_casa_sem_o_desvio_do_conftest(casa, monkeypatch):
    """A porta dos testes deste arquivo é a da casa (`Database.connect`), e não
    o `sqlite3.connect` desviado pelo conftest: sem o desvio, ela continua no
    PostgreSQL, no mesmo banco em que o app grava."""
    monkeypatch.setattr(sqlite3, "connect", banco_pg._CONNECT_ORIGINAL)
    mid = _ficha(casa)
    con = _con(casa)
    try:
        assert isinstance(con, banco_pg.Conexao)
        assert banco(con).valor("SELECT numero FROM ri_matriculas WHERE id = %s",
                                (mid,)) == "9001"
    finally:
        con.close()


# ------------------------------------------------------------ LH15: a ressalva do LH12

def _esquema(casa) -> str:
    con = _con(casa)
    try:
        return con.schema
    finally:
        con.close()


def _emissao_sem_a_ponte(casa, monkeypatch) -> list[int]:
    """Troca a transação da casa (`db.transaction`, a que a rota abre) por uma
    do psycopg puro, SEM a ponte: a emissão roda como vai rodar quando a ponte
    sair — sem o SAVEPOINT por comando e sem a trava única, que escondem o erro
    que condena a transação e a ordem das travas. Devolve os pids das conexões
    abertas, na ordem em que abriram.

    O prazo é longo de propósito: a trava do número é do banco inteiro, e o
    outro processo do xdist (outro schema, o mesmo banco) pode estar com ela."""
    esquema, pids = _esquema(casa), []

    @contextmanager
    def transacao():
        pg = _psycopg_puro(esquema)
        pg.execute("SET lock_timeout = '20s'")
        pg.commit()
        pids.append(pg.info.backend_pid)
        try:
            yield pg
            pg.commit()
        except Exception:
            pg.rollback()
            raise
        finally:
            pg.close()
    monkeypatch.setattr(casa["db"], "transaction", transacao)
    return pids


def _linha_da_revisao(casa, rid) -> dict:
    con = _con(casa)
    try:
        return banco(con).um("SELECT * FROM ri_transcricao_revisoes WHERE id = %s", (rid,))
    finally:
        con.close()


def _logado(casa, usuario: str):
    c = casa["app"].test_client()
    c.post("/login", data={"username": usuario, "password": SENHA,
                           "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return c


@so_no_postgresql
@pytest.mark.parametrize("o_erro", ["a linha da revisão presa além do prazo",
                                    "o SQL que quebra no mostrar"])
def test_o_erro_de_banco_na_reconferencia_sem_a_ponte_nao_derruba_a_certidao(
        casa, monkeypatch, caplog, o_erro):
    """Sem a ponte, o erro de SQL na reconferência (dentro da transação que
    numera) condenava a transação: o número logo abaixo virava 500. No
    SAVEPOINT dela, ele desfaz só a reconferência, e a certidão sai «sem
    revisão», com o aviso — e nada da revisão se grava pela metade: a revisão
    fica como estava, e a certidão leva uma linha só, a do ERRO."""
    mid = _ficha(casa)
    rid = _revisar(casa, mid, _IA())
    revisao_antes = _linha_da_revisao(casa, rid)
    _emissao_sem_a_ponte(casa, monkeypatch)
    outro = None
    if o_erro == "a linha da revisão presa além do prazo":
        # o gerente dando a divergência por conferida, e sem confirmar ainda
        outro = _psycopg_puro(_esquema(casa))
        banco(outro).um("SELECT id FROM ri_transcricao_revisoes WHERE id = %s FOR UPDATE",
                        (rid,))
        original = RT.reconferir_na_emissao

        def reconferir_com_prazo_curto(con, *a, **k):
            # a espera curta só pela linha (o número já está preso): o teste
            # não espera os 20 s
            banco(con).ler("SET LOCAL lock_timeout = '300ms'")
            return original(con, *a, **k)
        monkeypatch.setattr(RT, "reconferir_na_emissao", reconferir_com_prazo_curto)
    else:
        original = RT.mostrar

        def mostrar_que_quebra(con, revisao_id):
            # só na transação da emissão (a sem a ponte): a conferência de
            # antes, que lê pela ponte, passa e deixa a reconferência rodar
            if banco(con)._ponte is None:
                banco(con).valor("SELECT 1 / 0 AS n")
            return original(con, revisao_id)
        monkeypatch.setattr(RT, "mostrar", mostrar_que_quebra)
    try:
        with caplog.at_level(logging.WARNING):
            resposta = _emitir(casa, mid)
    finally:
        if outro is not None:
            outro.rollback()
            outro.close()
    pagina = resposta.get_data(as_text=True)
    assert resposta.status_code == 200
    assert "saiu SEM a revisão da transcrição" in pagina
    assert "a revisão não pôde ser conferida agora" in pagina
    assert any("não pôde ser reconferida" in r.getMessage() for r in caplog.records), (
        "o ERRO não veio da reconferência")
    assert _certidoes(casa, mid) == 1
    assert _emissoes(casa) == [{"situacao": "ERRO", "revisao_id": None,
                                "graves_pendentes": 0, "justificativa": None}]
    assert _linha_da_revisao(casa, rid) == revisao_antes


@so_no_postgresql
def test_duas_emissoes_ao_mesmo_tempo_esperam_pela_trava_do_numero_e_nao_pela_linha(
        casa, monkeypatch):
    """A trava do número vem antes da linha da revisão (LH15, a ordem da
    casa). Sem a ponte, a segunda emissão da mesma ficha chega enquanto a
    primeira, já com o número e a linha presos, ainda não confirmou: a segunda
    espera NA TRAVA DO NÚMERO, sem segurar linha nenhuma — e as duas saem, com
    números seguidos e a revisão gravada em cada uma."""
    mid = _ficha(casa)
    rid = _revisar(casa, mid, _IA())
    casa["db"].create_user("balcao2", "JOANA EXEMPLO", SENHA, "ADMIN")
    clientes = [casa["cliente"], _logado(casa, "balcao2")]
    fichas = [c.get(f"/registro-imoveis/{mid}").get_data(as_text=True) for c in clientes]
    pids = _emissao_sem_a_ponte(casa, monkeypatch)
    dentro, soltar = threading.Event(), threading.Event()
    original = RT.gravar_na_certidao

    def gravar_e_segurar(*a, **k):
        original(*a, **k)
        if not dentro.is_set():           # só a primeira segura, antes de confirmar
            dentro.set()
            soltar.wait(30)
    monkeypatch.setattr(RT, "gravar_na_certidao", gravar_e_segurar)
    respostas: dict = {}

    def emitir(i):
        try:
            respostas[i] = clientes[i].post(f"/registro-imoveis/{mid}/certidao",
                                            data=_dados_da_emissao(fichas[i]))
        except Exception as erro:  # o teste confere
            respostas[i] = erro
    vigia = _psycopg_puro(_esquema(casa), autocommit=True)
    fios = [threading.Thread(target=emitir, args=(i,)) for i in (0, 1)]
    esperou: list = []
    try:
        fios[0].start()
        assert dentro.wait(30), "a primeira emissão não chegou à gravação"
        fios[1].start()
        for _ in range(200):
            if len(pids) > 1:
                esperou = [r["locktype"] for r in banco(vigia).ler(
                    "SELECT locktype FROM pg_locks WHERE pid = %s AND NOT granted "
                    "ORDER BY locktype", (pids[1],))]
                if esperou:
                    break
            time.sleep(0.05)
    finally:
        soltar.set()
        for fio in fios:
            fio.join(60)
        vigia.close()
    assert esperou == ["advisory"], f"a segunda esperou {esperou}, e não a trava do número"
    assert [getattr(respostas[i], "status_code", respostas[i]) for i in (0, 1)] == [302, 302]
    con = _con(casa)
    try:
        numeros = [r["numero"] for r in banco(con).ler(
            "SELECT numero FROM ri_certidoes WHERE matricula_id = %s ORDER BY numero", (mid,))]
    finally:
        con.close()
    assert len(numeros) == 2 and numeros[1] == numeros[0] + 1
    assert _emissoes(casa) == [{"situacao": "PRONTA", "revisao_id": rid,
                                "graves_pendentes": 0, "justificativa": None}] * 2


@so_no_postgresql
@pytest.mark.parametrize("com_a_ponte", [True, False], ids=["com a ponte", "sem a ponte"])
def test_o_savepoint_de_quem_chama_desfaz_so_o_de_dentro_e_a_transacao_segue(
        casa, com_a_ponte):
    """`bd.ponto_de_retorno` (LH15): o erro de SQL dentro do `with` sobe e
    desfaz só o que rodou dentro; a transação segue, e o que vem depois se
    confirma. Com a ponte, mesmo com o SAVEPOINT como primeiro comando da
    transação, a trava única vem antes dele e continua presa depois do
    ROLLBACK TO (a ponte não saberia que a perdeu)."""
    esquema = _esquema(casa)
    con = _con(casa) if com_a_ponte else _psycopg_puro(esquema)
    vigia = _psycopg_puro(esquema, autocommit=True)
    bd = banco(con)

    def emissao(certidao_id):
        bd.escrever("""INSERT INTO ri_transcricao_emissoes (certidao_id, matricula_id,
                           situacao, emitida_em)
                       VALUES (%s, 1, 'ERRO', '2026-10-21T10:00:00')""", (certidao_id,))
    try:
        with pytest.raises(sqlite3.OperationalError):
            with bd.ponto_de_retorno("teste_lh15"):
                emissao(901)
                bd.valor("SELECT 1 / 0 AS n")
        if com_a_ponte:
            assert not banco(vigia).valor("SELECT pg_try_advisory_xact_lock(%s) AS livre",
                                          (con._chave_trava,)), "o ROLLBACK TO soltou a trava"
        emissao(902)
        with bd.ponto_de_retorno("teste_lh15"):
            emissao(903)
        con.commit()
    finally:
        con.close()
        vigia.close()
    con = _con(casa)
    try:
        assert [r["certidao_id"] for r in banco(con).ler(
            "SELECT certidao_id FROM ri_transcricao_emissoes ORDER BY id")] == [902, 903]
    finally:
        con.close()
    pg = _psycopg_puro(esquema)
    try:
        with pytest.raises(ValueError, match="identificador"):
            with banco(pg).ponto_de_retorno("x; DROP TABLE users"):
                pass
    finally:
        pg.close()


def test_o_lote_que_nao_parou_nao_se_diz_parado_e_o_log_conta(casa, monkeypatch, caplog):
    """`_parar` só grava se a situação ainda for a lida. Se a linha mudou — aqui,
    o lote lido SEM a linha presa e a pausa pedida logo depois —, ele não fica
    calado (LH15): o log diz que o lote não terminou, e a rodada relê o lote em
    vez de dizer TERMINADO, e o fecha PAUSADO, com a frase de quem pediu."""
    _ficha(casa, numero="60")
    lote_id = _lote(casa)
    con = _con(casa)
    banco(con).escrever("UPDATE ri_transcricao_lote_itens SET situacao = 'FEITO' "
                        "WHERE lote_id = %s", (lote_id,))
    con.commit()
    con.close()
    original, leituras = RTL._lote_preso, []

    def lido_solto_e_pausado_logo_depois(bd, lote):
        leituras.append(lote)
        if len(leituras) > 1:
            return original(bd, lote)
        c = _con(casa)
        try:
            lido = banco(c).um("SELECT * FROM ri_transcricao_lotes WHERE id = %s", (lote,))
        finally:
            c.close()
        with casa["db"].transaction() as c:
            assert RTL.pausar(c, lote, usuario="LAURA EXEMPLO") == RTL.PAUSANDO
        return lido
    monkeypatch.setattr(RTL, "_lote_preso", lido_solto_e_pausado_logo_depois)
    with caplog.at_level(logging.WARNING, logger="revisao_transcricao_lote"):
        assert _rodar(casa, lote_id, _IA()) == RTL.PAUSADO
    con = _con(casa)
    try:
        lote = RTL.ver(con, lote_id)
    finally:
        con.close()
    assert lote["situacao"] == RTL.PAUSADO
    assert "Pausa pedida por LAURA EXEMPLO" in lote["mensagem"]
    assert [r.getMessage() for r in caplog.records if r.name == "revisao_transcricao_lote"] == [
        f"O lote {lote_id} da revisão das transcrições não ficou TERMINADO: a situação "
        "mudou depois da leitura (lida RODANDO, agora PAUSANDO)."]
