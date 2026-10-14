"""As telas do extrator de endereço do ONR — a fila e o botão da ficha.

**O QUE ESTES TESTES GUARDAM, E POR QUE ELES EXISTEM.** O módulo de domínio
(`onr_endereco_do_teor`) tinha 60 testes em 16/09/2026 e as telas tinham
nenhum. O defeito desta casa é sempre o mesmo — peça pronta que ninguém chama —,
e ele **não se pega no domínio**: uma tela que não existe passa em todos os
testes de regra. Aqui se mede o que a tela faz de próprio:

1. **o botão só aparece onde ele pode fazer algo** — com teor e sem endereço;
2. **a leitura leva à conferência**, e não a uma linha nova na fila;
3. **a ficha sem teor é recusada com frase, e volta para onde quem clicou
   estava**;
4. **a proposta decidida não é refeita** — a decisão de quem conferiu vale mais
   que uma segunda leitura, e o `guardar` não a sobrescreve;
5. **a confirmação grava na matrícula**, que é o fim do caminho inteiro.

Os teores de entrada são de ficha desta casa, na forma como a produção os
guarda — com os `\\r\\n` e a marca `IMÓVEL:-`, que é o que `bloco_do_imovel`
procura. Sem a marca o texto volta inteiro, e aí o teste mediria outra coisa.
"""
from __future__ import annotations

import re
import sqlite3

# O teor da ficha urbana de teste: um lote com rua, número, bairro, cidade,
# UF e área. O extrator lê todos, e o que se mede aqui é o CAMINHO da tela —
# a leitura em si tem os testes próprios em `test_onr_endereco_do_teor.py`.
TEOR_URBANO = (
    " MATRÍCULA: 4001\n\r\n LIVRO 2 FLS. 1\n\r\n DATADO 10 DE JANEIRO DE 2026"
    "\n\r\n \n\r\n IMÓVEL:- "
    "- Lote de terreno urbano situado na Rua Dep. La Rocque, nº 123, "
    "bairro Centro, nesta cidade de Cidade Exemplo, Estado do Maranhão, "
    "medindo 10,00 m de frente por 25,00 m de fundo, com área de 250,00 m2, "
    "confrontando à direita com o lote nº 125, à esquerda com o lote nº 121."
    "\n\nProprietário: JOSE DA SILVA, brasileiro, casado, residente e "
    "domiciliado na Av. Venerando F. Borges, nº 45, Centro."
)

# A RUA E O NÚMERO DA PESSOA (Av. Venerando F. Borges, nº 45), no MESMO teor.
# Eles provam a âncora: o endereço que vai à ficha é o do IMÓVEL, e o da
# pessoa não pode vazar — é o defeito das fichas 971 e 979.
RUA_DO_IMOVEL = "Rua Dep. La Rocque"
RUA_DA_PESSOA = "Venerando"


def _con(s):
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    # O CEP DA SERVENTIA VEM DE `settings` desde 09/10/2026 (sanitização: o
    #   mapa de CEPs saiu do código). Sem ele, a proposta não fecha o endereço.
    with con:
        con.execute("INSERT OR REPLACE INTO settings(key, value) "
                    "VALUES ('serventia_cep', '65.936-000')")
    return con


def _ficha(s, numero, *, teor=TEOR_URBANO, logradouro=None, cidade=None) -> int:
    """Uma matrícula como o OCR a deixa: com teor, e sem endereço na coluna."""
    con = _con(s)
    con.execute(
        """INSERT INTO ri_matriculas
           (numero, complemento, livro, livro_norm, tipo_ficha, situacao,
            conferido, origem, criado_em, teor_formato, teor, logradouro,
            cidade)
           VALUES (?,'','2','2','ESTRUTURADA','ATIVA',0,'PDF_OCR',
                   '2026-09-16','texto',?,?,?)""",
        (str(numero), teor, logradouro, cidade))
    mid = con.execute("SELECT MAX(id) i FROM ri_matriculas").fetchone()["i"]
    con.commit()
    con.close()
    return int(mid)


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _ficha_html(s, matricula_id):
    r = s["c"].get(f"/registro-imoveis/{matricula_id}")
    assert r.status_code == 200, r.status_code
    return r.get_data(as_text=True)


def _propostas(s) -> list[dict]:
    con = _con(s)
    linhas = [dict(r) for r in con.execute(
        "SELECT * FROM ri_onr_enderecos ORDER BY id")]
    con.close()
    return linhas


# ───────────────────────────────────────────────── o botão, na ficha do imóvel

def test_o_botao_aparece_na_ficha_que_tem_teor_e_nao_tem_endereco(cg_casa_logada):
    """É o caso das 1.443: o teor está lá, a coluna está vazia."""
    s = cg_casa_logada
    mid = _ficha(s, 4001)
    html = _ficha_html(s, mid)
    assert f"/ri/onr/endereco/da-matricula/{mid}" in html
    assert "o que o teor diz" in html
    # E o botão é formulário com token: nesta casa um GET não escreve, e o
    # `tests/test_csrf_nas_telas.py` varre o sistema inteiro por isto.
    assert _token(html)


def test_a_ficha_que_ja_tem_endereco_nao_oferece_o_botao(cg_casa_logada):
    """**O botão que não pode fazer nada não se oferece.**

    Quem clicasse e recebesse uma recusa aprenderia a não clicar — e a coluna
    preenchida é o caso em que a leitura não tem o que acrescentar.
    """
    s = cg_casa_logada
    mid = _ficha(s, 4002, logradouro="Rua Dep. La Rocque")
    html = _ficha_html(s, mid)
    assert f"/ri/onr/endereco/da-matricula/{mid}" not in html


def test_a_ficha_sem_teor_nao_oferece_o_botao(cg_casa_logada):
    """Sem texto não há o que ler — a ficha do acervo sem teor é o caso."""
    s = cg_casa_logada
    mid = _ficha(s, 4003, teor="")
    html = _ficha_html(s, mid)
    assert f"/ri/onr/endereco/da-matricula/{mid}" not in html


# ─────────────────────────────────────────────── ler o teor e ir à conferência

def test_o_botao_le_o_teor_e_leva_direto_a_conferencia_da_proposta(
        cg_casa_logada):
    """Um clique, uma proposta, e a tela que mostra as duas versões."""
    s = cg_casa_logada
    mid = _ficha(s, 4001)
    r = s["c"].post(f"/ri/onr/endereco/da-matricula/{mid}",
                    data={"csrf_token": _token(_ficha_html(s, mid))},
                    follow_redirects=True)
    assert r.status_code == 200, r.status_code
    html = r.get_data(as_text=True)

    proposta = _propostas(s)
    assert len(proposta) == 1, "devia nascer exatamente uma proposta"
    p = proposta[0]
    assert p["matricula_id"] == mid
    assert p["situacao"] == "A_CONFERIR"
    assert p["pode_enviar"] == 1

    # A tela da conferência mostra a rua lida, e é ela que leva à decisão.
    assert RUA_DO_IMOVEL in html
    # **E A RUA DA PESSOA NÃO ESTÁ NA PROPOSTA** — a âncora medida no domínio
    # vale no caminho de tela também: quem abre a ficha do imóvel não pode ler
    # o endereço de quem vende como se fosse o do imóvel.
    assert "numero_predial" in html
    assert RUA_DA_PESSOA not in p["proposta"], p["proposta"]


def test_a_ficha_sem_teor_e_recusada_com_frase_e_volta_para_a_ficha(
        cg_casa_logada):
    """A rota sem passar pelo botão: o domínio recusa, e a frase volta.

    **A recusa volta para a FICHA**, e não para a fila: quem clicou estava lá,
    e mandá-lo a outra tela depois de uma recusa é tirar-lhe o lugar onde ele
    estava. E **nada é gravado** — a recusa não deixa linha na fila.
    """
    s = cg_casa_logada
    mid = _ficha(s, 4004, teor="")
    r = s["c"].post(f"/ri/onr/endereco/da-matricula/{mid}",
                    data={"csrf_token": _token(_ficha_html(s, mid))},
                    follow_redirects=True)
    assert r.status_code == 200, r.status_code
    html = r.get_data(as_text=True)
    assert "não tem teor" in html.lower() or "sem teor" in html.lower()
    assert _propostas(s) == []


def test_a_proposta_decidida_nao_e_refeita_e_a_tela_diz_por_que(cg_casa_logada):
    """**A decisão de quem conferiu vale mais que uma segunda leitura.**

    Sem esta guarda, a rota leria o teor, o `guardar` devolveria o `id` da
    proposta antiga e a tela mostraria a proposta VELHA como se fosse a leitura
    que o operador acabou de pedir — o carimbo que mente na sua forma mais
    direta.
    """
    s = cg_casa_logada
    mid = _ficha(s, 4005)
    con = _con(s)
    con.execute(
        """INSERT INTO ri_onr_enderecos
           (matricula_id, situacao, proposta, de_onde, faltam, avisos, bloco,
            antes, confianca, pode_enviar, calculado_em, decidido_em,
            decidido_por, motivo)
           VALUES (?,'CONFIRMADA','{"logradouro": "Rua Antiga"}','{}','[]','[]',
                   '','{}','alta',1,'2026-09-16 08:00','2026-09-16 09:00',
                   'JEAN','')""", (mid,))
    antiga = con.execute("SELECT MAX(id) i FROM ri_onr_enderecos").fetchone()["i"]
    con.commit()
    con.close()

    r = s["c"].post(f"/ri/onr/endereco/da-matricula/{mid}",
                    data={"csrf_token": _token(_ficha_html(s, mid))},
                    follow_redirects=True)
    assert r.status_code == 200, r.status_code
    html = r.get_data(as_text=True)
    assert "vale mais" in html
    # **A LEITURA ANTIGA FICOU DE PÉ** — nem outra linha, nem sobrescrita.
    guardadas = _propostas(s)
    assert len(guardadas) == 1
    assert guardadas[0]["id"] == antiga
    assert "Rua Antiga" in guardadas[0]["proposta"]
    assert RUA_DO_IMOVEL not in guardadas[0]["proposta"]


# ─────────────────────────────────────────────────────── a confirmação grava

def test_a_confirmacao_grava_o_endereco_na_matricula(cg_casa_logada):
    """O fim do caminho: a proposta vira endereço na ficha, e a matrícula sai
    da fila do ONR."""
    s = cg_casa_logada
    mid = _ficha(s, 4006)
    s["c"].post(f"/ri/onr/endereco/da-matricula/{mid}",
                data={"csrf_token": _token(_ficha_html(s, mid))})
    pid = _propostas(s)[0]["id"]
    html = s["c"].get(f"/ri/onr/endereco/{pid}").get_data(as_text=True)
    r = s["c"].post(f"/ri/onr/endereco/{pid}/confirmar",
                    data={"csrf_token": _token(html)},
                    follow_redirects=True)
    assert r.status_code == 200, r.status_code

    con = _con(s)
    m = con.execute("SELECT logradouro, numero_predial, bairro, cidade, uf, "
                    "area_valor, area_unidade FROM ri_matriculas WHERE id=?",
                    (mid,)).fetchone()
    p = con.execute("SELECT situacao FROM ri_onr_enderecos WHERE id=?",
                    (pid,)).fetchone()
    con.close()
    assert m["logradouro"] == RUA_DO_IMOVEL
    assert m["numero_predial"] == "123"
    assert m["bairro"] == "CENTRO"
    assert m["cidade"] == "Cidade Exemplo"
    assert m["uf"] == "MA"
    assert p["situacao"] == "CONFIRMADA"


def test_a_confirmacao_nao_sobrescreve_o_que_a_ficha_ja_tinha(cg_casa_logada):
    """O que uma pessoa digitou vale mais que o que a máquina leu.

    É a regra do CNM, e aqui ela protege um caso real: o bairro corrigido à mão
    na ficha entre a proposta e a confirmação.
    """
    s = cg_casa_logada
    mid = _ficha(s, 4007)
    s["c"].post(f"/ri/onr/endereco/da-matricula/{mid}",
                data={"csrf_token": _token(_ficha_html(s, mid))})
    pid = _propostas(s)[0]["id"]
    # Alguém corrigiu o bairro na ficha, direto no banco, como a tela do RI faz.
    con = _con(s)
    con.execute("UPDATE ri_matriculas SET bairro='VILA NOVA' WHERE id=?", (mid,))
    con.commit()
    con.close()

    html = s["c"].get(f"/ri/onr/endereco/{pid}").get_data(as_text=True)
    r = s["c"].post(f"/ri/onr/endereco/{pid}/confirmar",
                    data={"csrf_token": _token(html)},
                    follow_redirects=True)
    assert r.status_code == 200, r.status_code
    # «Não foram tocados» — a frase que diz QUAL campo ficou de fora, e por quê.
    assert "foram tocados" in r.get_data(as_text=True)
    con = _con(s)
    m = con.execute("SELECT logradouro, bairro FROM ri_matriculas WHERE id=?",
                    (mid,)).fetchone()
    con.close()
    assert m["bairro"] == "VILA NOVA", "o que a pessoa escreveu foi sobrescrito"
    assert m["logradouro"] == RUA_DO_IMOVEL, "o que estava vazio devia entrar"


# ─────────────────────────────────────────────────────────────────── a fila

def test_a_fila_abre_e_conta_o_que_tem(cg_casa_logada):
    """A porta de quem vai despachar 1.443 fichas."""
    s = cg_casa_logada
    _ficha(s, 4008)
    _ficha(s, 4009)
    s["c"].post(f"/ri/onr/enderecos/gerar", data={"csrf_token": _token(
        s["c"].get("/ri/onr/enderecos").get_data(as_text=True))},
        follow_redirects=True)
    r = s["c"].get("/ri/onr/enderecos")
    assert r.status_code == 200, r.status_code
    html = r.get_data(as_text=True)
    assert "4008" in html and "4009" in html


def test_o_botao_da_ficha_e_um_formulario_e_nao_um_link(cg_casa_logada):
    """**A prova de que ele não escreve por GET**, que é a regra da casa.

    O botão de gravar o CNM, ali ao lado na mesma ficha, tem a mesma forma — e
    a razão é a mesma: `GET` não abre transação de escrita.
    """
    s = cg_casa_logada
    mid = _ficha(s, 4010)
    html = _ficha_html(s, mid)
    trecho = html[html.index(f"/ri/onr/endereco/da-matricula/{mid}") - 400:]
    assert 'method="post"' in trecho
    # E um GET na rota não cria proposta nenhuma: 405, e a tabela continua vazia.
    assert s["c"].get(f"/ri/onr/endereco/da-matricula/{mid}").status_code == 405
    assert _propostas(s) == []
