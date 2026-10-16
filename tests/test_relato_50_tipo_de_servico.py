"""RELATO #50 — o tipo de serviço do depósito prévio.

A frase do oficial, de 11/09/2026, na tela do depósito:

    «NESTE CAMPO DE DEPÓSITO PRÉVIO DEVE CONTER DATA DO DEPÓSITO.
     INFORMAÇÕES DO TIPO DE SERVIÇO»

A data foi a primeira metade (`tests/test_relato_50_data_do_deposito.py`).
Esta é a segunda, e ela nasceu de uma medição, não de uma ideia:

| medido na produção em 17/09/2026 | |
|---|---|
| depósitos | **14** |
| sem vínculo nenhum (nem protocolo, nem prenotação, nem ato) | **8** |
| com vínculo, e neles o tipo é **fato lido** | **6** |
| com o serviço escrito à mão na observação | **10** |

«REGISTRO ESCRITURA DE COMPRA E VENDA LAVRADA NESTA», «AVERBAÇÕES CADASTROS
RURAIS», «GEORREFERENCIAMENTO AGUARDANDO CUMPRIMENTO DE NOTA»: texto livre que
**não se soma, não se filtra e não se confere** — e o pedido dele é justamente
poder achar.

SÃO DOIS CAMPOS PORQUE SÃO DUAS PERGUNTAS. A **atribuição** é «de que cartório é
este dinheiro», o que se soma num relatório; o **serviço** é qual item do
catálogo da casa ele adianta, o que se confere contra o que foi cobrado.

O QUE ESTES TESTES PROVAM, E A ORDEM IMPORTA:

 1. a tela pergunta as duas coisas, e diz que são **opcionais**;
 2. o que for escolhido fica gravado e a lista mostra;
 3. o que não for escolhido **não vira palpite** — o depósito entra sem tipo;
 4. **o vínculo responde sozinho**: as duas telas que criam depósito amarrado
    (o título do RI e o ato das Notas) não precisam perguntar nada;
 5. **o vínculo ganha do serviço**, e a divergência aparece em vez de sumir;
 6. o grupo do catálogo **estreita** o campo, mas não escolhe entre Firmas e
    Notas — quem sabe qual dos dois é quem atende;
 7. o botão dos antigos grava **só** o que o vínculo declara, e é do oficial.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

OPERADOR = "MARIO EXEMPLO DOS SANTOS"
SENHA = "Senha#12345"

# O catálogo de ensaio. Os códigos são altos de propósito: o da casa vai até
# 1.305, e um serviço de mentira com número de gente seria confundido com dado.
#
# Os grupos são os do acervo (`tbGrupoTJ`): **21** é o dos tabelionatos de
# notas — onde o balcão registra tanto firma quanto ato de livro —, **24** é o
# do Registro de Imóveis e **0** é o que não decide nada.
#
# «ZZTIPO» e «ZZUNICO» são palavras que não existem em catálogo nenhum: é o que
# faz a busca achar exatamente os dois serviços que se quer, e não a família
# inteira dos «arquivamento» que a casa tem.
SERVICOS = (
    (990001, "13.17.2", "Reconhecimento de firma por semelhança", 21),
    (990002, "99.91.1", "PROVA ZZTIPO ALFA", 21),
    (990003, "99.91.2", "PROVA ZZTIPO BETA", 21),
    (990004, "16.24.4", "Certidões de inteiro teor, ônus e ações reais", 24),
    (990005, "99.92.1", "PROVA ZZUNICO", 0),
)


# ------------------------------------------------------------- ferramentas

def _token(c, rota: str = "/caixa/depositos") -> str:
    html = c.get(rota).get_data(as_text=True)
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, f"a tela {rota} não trouxe csrf_token"
    return achado.group(1)


def _registrar(c, **campos):
    corpo = {"csrf_token": _token(c), "acao": "novo",
             "depositante": "CONSTRUTORA ALFA LTDA", "valor": "450,00"}
    corpo.update(campos)
    return c.post("/caixa/depositos", data=corpo, follow_redirects=True)


def _entrar(c, usuario: str, senha: str = SENHA):
    """Login por outro usuário, com o token da tela — o mesmo caminho do balcão."""
    html = c.get("/login").get_data(as_text=True)
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela /login não trouxe csrf_token"
    return c.post("/login", data={"username": usuario, "password": senha,
                                  "csrf_token": achado.group(1)},
                  follow_redirects=True)


def _con(banco):
    con = sqlite3.connect(str(banco))
    con.row_factory = sqlite3.Row
    return con


def _semear_catalogo(banco) -> None:
    """Os cinco serviços de ensaio. `INSERT OR REPLACE`: chamar duas vezes não
    estoura — o banco do teste é o mesmo para o arquivo inteiro."""
    con = _con(banco)
    try:
        import emolumentos as EMOL
        # TESTE VELHO, ATUALIZADO EM 14/10/2026: desde a 3.6.198 (24/09/2026)
        # `emolumentos.buscar` — a busca que o depósito reusa de propósito —
        # NÃO LISTA serviço sem preço na vigência vigente (o clique nele dava
        # «Não encontrei esse ato na tabela vigente»). O catálogo de ensaio
        # nascia sem preço, e a busca passou a não achar nenhum dos cinco.
        # O ensaio agora tem o que a casa tem: um preço na vigência vigente.
        vigente = con.execute(
            "SELECT codigo FROM cx_vigencias WHERE vigente=1").fetchone()
        if vigente:
            vigencia = vigente[0]
        else:
            vigencia = 990099
            con.execute("""INSERT OR IGNORE INTO cx_vigencias (codigo, descricao,
                                                             vigente)
                           VALUES (?, 'VIGENCIA DE ENSAIO', 1)""", (vigencia,))
        for codigo, codigo_tj, descricao, grupo in SERVICOS:
            con.execute(
                """INSERT OR REPLACE INTO cx_servicos
                       (codigo, codigo_tj, descricao, descricao_norm, grupo, ativo)
                   VALUES (?,?,?,?,?,1)""",
                (codigo, codigo_tj, descricao, EMOL._norm(descricao), grupo))
            con.execute(
                """INSERT OR REPLACE INTO cx_servico_valores
                       (servico, vigencia, emolumentos, ferc, femp, fadep,
                        ferrfis, total)
                   VALUES (?, ?, '10,00', '0,00', '0,00', '0,00', '0,00',
                           '10,00')""",
                (codigo, vigencia))
        con.commit()
    finally:
        con.close()


def _protocolo(banco, atribuicao: str | None = None, itens: tuple = ()) -> int:
    """Um protocolo do balcão, com ou sem itens. Devolve o id.

    O número sai do maior que já existe: o banco do arquivo é um só, e um
    número fixo estouraria o `UNIQUE(numero)` no segundo teste que o usasse.
    """
    con = _con(banco)
    try:
        proximo = (con.execute("SELECT COUNT(*) FROM cx_protocolos").fetchone()[0]
                   or 0) + 901
        cur = con.execute(
            """INSERT INTO cx_protocolos (numero, data_abertura, atribuicao,
                                          interessado, situacao, criado_em)
               VALUES (?,?,?,?,'ABERTO',?)""",
            # A data é fixa, como o `criado_em` ao lado: o dia em que o ensaio
            # roda não entra no dado de ensaio.
            (f"2026.09.{proximo}", "2026-09-17", atribuicao,
             "CONSTRUTORA ALFA LTDA", "2026-09-17T09:00:00"))
        protocolo_id = int(cur.lastrowid)
        for codigo in itens:
            con.execute(
                """INSERT INTO cx_protocolo_atos (protocolo_id, servico_codigo,
                                                  quantidade)
                   VALUES (?,?,1)""", (protocolo_id, codigo))
        con.commit()
        return protocolo_id
    finally:
        con.close()


def _ultimo_deposito(banco) -> dict:
    con = _con(banco)
    try:
        linha = con.execute(
            "SELECT * FROM cx_depositos ORDER BY id DESC LIMIT 1").fetchone()
        return dict(linha) if linha else {}
    finally:
        con.close()


def _depositos_do_banco(banco) -> list[dict]:
    con = _con(banco)
    try:
        return [dict(r) for r in con.execute("SELECT * FROM cx_depositos")]
    finally:
        con.close()


# ------------------------------------------------------------------ a tela

def test_a_tela_pergunta_a_atribuicao_e_o_servico(cg_casa_logada):
    """Os dois campos, e o que faz o pedido valer: sem eles a observação de
    texto livre continua sendo o único lugar, e texto livre não se soma."""
    html = cg_casa_logada["c"].get("/caixa/depositos").get_data(as_text=True)
    assert 'name="atribuicao"' in html, "a tela não pergunta a atribuição"
    assert 'name="servico_codigo"' in html, "a tela não pergunta o serviço"
    for sigla in ("FIRMAS", "NOTAS", "RCPN", "RI"):
        assert sigla in html, f"a lista não oferece {sigla}, que a casa usa"


def test_os_dois_campos_dizem_que_sao_opcionais(cg_casa_logada):
    """**Opção do oficial, e ela é medida**: 8 dos 14 depósitos não têm
    vínculo. Campo obrigatório aqui recusaria dinheiro que a casa sempre
    recebeu — o depósito deixado «para quando o título chegar»."""
    html = cg_casa_logada["c"].get("/caixa/depositos").get_data(as_text=True)
    assert "— sem tipo —" in html, "a lista não oferece «sem tipo»"
    assert "opcional" in html.lower(), \
        "a tela não diz que o tipo é opcional — quem lê supõe que é obrigatório"


def test_a_lista_tem_a_coluna_do_tipo_e_o_filtro(cg_casa_logada):
    """A segunda metade do pedido dele é **poder achar**: o campo que não tem
    coluna nem filtro é o campo que continua não existindo, só que gravado."""
    html = cg_casa_logada["c"].get("/caixa/depositos").get_data(as_text=True)
    assert "<th>Tipo</th>" in html, "a lista não tem a coluna do tipo"
    assert 'name="atribuicao"' in html, "a lista não filtra por atribuição"
    assert "sem tipo" in html, \
        "a lista não declara quantos depósitos estão sem tipo"


# ---------------------------------------------------------------- domínio

def test_sem_tipo_o_deposito_e_gravado_assim_mesmo(cg_casa_logada):
    """O depósito solto é legítimo. Sem tipo gravado ele entra, e a lista o
    conta em vez de escondê-lo."""
    _registrar(cg_casa_logada["c"])
    d = _ultimo_deposito(cg_casa_logada["banco"])
    assert d, "o depósito solto não foi gravado"
    assert d["atribuicao"] is None and d["servico_codigo"] is None

    html = cg_casa_logada["c"].get("/caixa/depositos").get_data(as_text=True)
    assert "— sem tipo (1)" in html, \
        "a lista não declara o depósito sem tipo"


def test_o_tipo_escolhido_fica_gravado_e_a_lista_mostra(cg_casa_logada):
    """Escolher e não ver o que se escolheu é o mesmo que não ter escolhido."""
    _semear_catalogo(cg_casa_logada["banco"])
    _registrar(cg_casa_logada["c"], atribuicao="NOTAS",
               servico_codigo="13.17.2", depositante="MARIA DA SILVA")
    d = _ultimo_deposito(cg_casa_logada["banco"])
    assert d["atribuicao"] == "NOTAS"
    assert d["servico_codigo"] == 990001, \
        "o código do TJ não virou a chave do catálogo"

    html = cg_casa_logada["c"].get("/caixa/depositos").get_data(as_text=True)
    assert "Notas — atos de livro" in html, "a lista não mostra a atribuição"
    assert "13.17.2" in html, "a lista não mostra o serviço"


def test_atribuicao_fora_do_vocabulario_e_recusada_com_frase(cg_casa_logada):
    """Atribuição que a casa não usa viraria uma linha que nenhum filtro acha —
    e o pedido do relato é justamente poder achar. Erro de regra não é 500."""
    antes = len(_depositos_do_banco(cg_casa_logada["banco"]))
    r = _registrar(cg_casa_logada["c"], atribuicao="XPTO")
    assert len(_depositos_do_banco(cg_casa_logada["banco"])) == antes, \
        "gravou depósito com atribuição que a casa não usa"
    assert "não é uma atribuição desta casa" in r.get_data(as_text=True)


def test_servico_que_nao_existe_no_catalogo_e_recusado(cg_casa_logada):
    _semear_catalogo(cg_casa_logada["banco"])
    antes = len(_depositos_do_banco(cg_casa_logada["banco"]))
    r = _registrar(cg_casa_logada["c"], servico_codigo="ZZNAOEXISTE")
    assert len(_depositos_do_banco(cg_casa_logada["banco"])) == antes
    html = r.get_data(as_text=True)
    assert "Não achei nenhum serviço" in html
    assert "opcional" in html.lower(), \
        "a recusa não lembra que dá para deixar em branco"


def test_servico_ambiguo_recusa_listando_os_codigos(cg_casa_logada):
    """«Não achei» e «achei dois» pedem providências diferentes, e dizer a
    primeira faria a pessoa procurar de novo pelo mesmo termo e receber o
    mesmo silêncio. **A máquina não escolhe em cima de dinheiro.**"""
    _semear_catalogo(cg_casa_logada["banco"])
    antes = len(_depositos_do_banco(cg_casa_logada["banco"]))
    r = _registrar(cg_casa_logada["c"], servico_codigo="ZZTIPO")
    assert len(_depositos_do_banco(cg_casa_logada["banco"])) == antes, \
        "gravou um dos dois candidatos por conta própria"
    html = r.get_data(as_text=True)
    assert "Achei 2 serviços" in html, "a recusa não diz quantos candidatos há"
    assert "99.91.1" in html and "99.91.2" in html, \
        "a recusa não lista os códigos — quem lê não tem como escolher"


# ------------------------------------------------- o vínculo responde

def test_o_vinculo_do_ri_nao_precisa_perguntar(cg_db):
    """A tela do título do Registro de Imóveis não oferece campo nenhum, e não
    precisa: a prenotação é do RI, e isso é fato, não dedução."""
    import caixa_depositos as DEP

    with cg_db.transaction() as con:
        feito = DEP.criar(con, valor_centavos=5000, depositante="BANCO ALFA",
                          agora="2026-09-17T10:00:00", ri_protocolo_id=1)
    assert feito["atribuicao"] == "RI", "o vínculo do RI não declarou a atribuição"


def test_o_ato_de_livro_das_notas_nao_precisa_perguntar(cg_db):
    import caixa_depositos as DEP

    with cg_db.transaction() as con:
        feito = DEP.criar(con, valor_centavos=5000, depositante="BANCO ALFA",
                          agora="2026-09-17T10:00:00", nt_ato_id=1)
    assert feito["atribuicao"] == "NOTAS"


def test_o_protocolo_do_balcao_declara_a_atribuicao(cg_db, cg_casa_logada):
    import caixa_depositos as DEP

    protocolo_id = _protocolo(cg_casa_logada["banco"], atribuicao="FIRMAS")
    with cg_db.transaction() as con:
        feito = DEP.criar(con, valor_centavos=5000, depositante="PEDRO ALVES",
                          agora="2026-09-17T10:00:00",
                          protocolo_id=protocolo_id)
    assert feito["atribuicao"] == "FIRMAS"


def test_o_protocolo_com_um_item_so_declara_o_servico(cg_db, cg_casa_logada):
    """Com um item só, o depósito é daquele serviço — e isso é leitura, não
    escolha."""
    import caixa_depositos as DEP

    _semear_catalogo(cg_casa_logada["banco"])
    protocolo_id = _protocolo(cg_casa_logada["banco"], atribuicao="FIRMAS",
                              itens=(990001,))
    with cg_db.transaction() as con:
        feito = DEP.criar(con, valor_centavos=5000, depositante="PEDRO ALVES",
                          agora="2026-09-17T10:00:00",
                          protocolo_id=protocolo_id)
    assert feito["servico_codigo"] == 990001


def test_o_protocolo_com_varios_itens_nao_escolhe_o_servico(cg_db, cg_casa_logada):
    """Com vários itens o depósito cobre o **conjunto**: escolher um deles
    seria escolher por quem atende. A atribuição continua vindo, porque ela é
    do protocolo inteiro."""
    import caixa_depositos as DEP

    _semear_catalogo(cg_casa_logada["banco"])
    protocolo_id = _protocolo(cg_casa_logada["banco"], atribuicao="FIRMAS",
                              itens=(990002, 990003))
    with cg_db.transaction() as con:
        feito = DEP.criar(con, valor_centavos=5000, depositante="PEDRO ALVES",
                          agora="2026-09-17T10:00:00",
                          protocolo_id=protocolo_id)
    assert feito["atribuicao"] == "FIRMAS"
    assert feito["servico_codigo"] is None, \
        "escolheu um dos dois itens do protocolo por conta própria"


def test_o_vinculo_ganha_do_servico_e_a_divergencia_avisa(cg_db, cg_casa_logada):
    """**O vínculo é fato; o grupo do serviço diz por quais tabelas ele passa.**
    Discordarem não é empate a desempatar por ordem: é uma das duas coisas que
    está errada, e quem sabe qual é quem atende. Sumir com o aviso seria gravar
    dinheiro classificado de um jeito que a tela não mostrou."""
    import caixa_depositos as DEP

    _semear_catalogo(cg_casa_logada["banco"])
    protocolo_id = _protocolo(cg_casa_logada["banco"], atribuicao="RI")
    with cg_db.transaction() as con:
        feito = DEP.criar(con, valor_centavos=5000, depositante="BANCO ALFA",
                          agora="2026-09-17T10:00:00",
                          protocolo_id=protocolo_id, servico_codigo=990001)
    assert feito["atribuicao"] == "RI", "o serviço ganhou do vínculo"
    assert feito["servico_codigo"] == 990001
    assert feito["aviso"], "a divergência passou calada"
    assert "Firmas" in feito["aviso"] and "Registro de Imóveis" in feito["aviso"]


# ------------------------------------------------- o botão dos antigos

def test_o_botao_dos_antigos_preenche_so_o_que_o_vinculo_declara(cg_db,
                                                                cg_casa_logada):
    """**Fato lido, não palpite** (decisão do oficial em 17/09/2026). O que não
    tem vínculo fica sem tipo, e a função conta isso em vez de inventar.

    O DEPÓSITO DE HOJE JÁ NASCE CLASSIFICADO — `criar` pergunta ao vínculo —, e
    por isso o teste apaga a atribuição antes de chamar o botão: é o que a
    produção tem, os **14 depósitos que existiam antes de o campo existir**. Sem
    esse apagamento o botão não teria o que fazer, e o teste provaria o
    contrário do que quer provar.
    """
    import caixa_depositos as DEP

    banco = cg_casa_logada["banco"]
    _semear_catalogo(banco)
    com_vinculo = _protocolo(banco, atribuicao="FIRMAS", itens=(990001,))
    outro_vinculo = _protocolo(banco, atribuicao="RI")

    with cg_db.transaction() as con:
        DEP.criar(con, valor_centavos=1000, depositante="COM VINCULO",
                  agora="2026-09-17T10:00:00", protocolo_id=com_vinculo)
        DEP.criar(con, valor_centavos=1000, depositante="OUTRO VINCULO",
                  agora="2026-09-17T10:00:00", protocolo_id=outro_vinculo)
        DEP.criar(con, valor_centavos=1000, depositante="SOLTO",
                  agora="2026-09-17T10:00:00")
        con.execute("UPDATE cx_depositos SET atribuicao=NULL, servico_codigo=NULL")

    with cg_db.transaction() as con:
        feito = DEP.gravar_tipos_do_vinculo(con)

    assert feito["gravados"] == 2, "não gravou os dois que têm vínculo"
    assert feito["com_servico"] == 1, \
        "não trouxe o serviço do protocolo de item único"
    assert feito["sem_tipo"] == 1, "contou errado os que ficam sem tipo"

    tipos = {d["depositante"]: d["atribuicao"]
             for d in _depositos_do_banco(banco)}
    assert tipos["COM VINCULO"] == "FIRMAS"
    assert tipos["OUTRO VINCULO"] == "RI"
    assert tipos["SOLTO"] is None, "inventou tipo para quem não tem vínculo"


def test_o_botao_dos_antigos_e_do_oficial(cg_casa_logada, cg_db):
    """**Muda a classificação de dinheiro que já entrou.** O menu não oferece o
    que o operador não pode fazer, e a rota recusa de novo."""
    import caixa_depositos as DEP

    banco = cg_casa_logada["banco"]
    protocolo_id = _protocolo(banco, atribuicao="FIRMAS")
    with cg_db.transaction() as con:
        DEP.criar(con, valor_centavos=1000, depositante="COM VINCULO",
                  agora="2026-09-17T10:00:00", protocolo_id=protocolo_id)
        # Apaga a atribuição para o depósito ficar como os antigos da produção.
        con.execute("UPDATE cx_depositos SET atribuicao=NULL, servico_codigo=NULL")

    cg_casa_logada["db"].create_user("escrevente", "LAURA MARIA DA COSTA",
                                     SENHA, "USER")
    c = cg_casa_logada["c"]
    _entrar(c, "escrevente")

    r = c.post("/caixa/depositos",
               data={"csrf_token": _token(c), "acao": "gravar_tipos"},
               follow_redirects=True)
    assert "é do oficial" in r.get_data(as_text=True), \
        "o escrevente não foi recusado"
    gravado = [d for d in _depositos_do_banco(banco)
               if d["depositante"] == "COM VINCULO"]
    assert gravado and gravado[0]["atribuicao"] is None, \
        "o escrevente conseguiu mudar a classificação do dinheiro"

    html = c.get("/caixa/depositos").get_data(as_text=True)
    assert "Preencher o tipo dos" not in html, \
        "o botão aparece para quem a rota recusa"


def test_a_regua_dos_antigos_e_a_mesma_do_cadastro(cg_db, cg_casa_logada):
    """**Três caminhos, uma régua.** O que o botão grava tem de ser o que o
    cadastro gravaria se aquele depósito entrasse hoje — escritos em separado,
    divergiriam no primeiro conserto, e a divergência aqui é dinheiro
    classificado de dois jeitos."""
    import caixa_depositos as DEP

    banco = cg_casa_logada["banco"]
    protocolo_id = _protocolo(banco, atribuicao="RCPN")

    with cg_db.transaction() as con:
        antigo = DEP.criar(con, valor_centavos=1000, depositante="ANTIGO",
                           agora="2026-09-17T10:00:00",
                           protocolo_id=protocolo_id)
        # O depósito novo, criado pelo caminho normal, com o mesmo vínculo.
        novo = DEP.criar(con, valor_centavos=1000, depositante="NOVO",
                         agora="2026-09-17T10:00:00",
                         protocolo_id=protocolo_id)
    with cg_db.transaction() as con:
        con.execute("UPDATE cx_depositos SET atribuicao=NULL WHERE id=?",
                    (antigo["id"],))
    with cg_db.transaction() as con:
        DEP.gravar_tipos_do_vinculo(con)

    con = _con(banco)
    try:
        gravado = con.execute("SELECT atribuicao FROM cx_depositos WHERE id=?",
                              (antigo["id"],)).fetchone()[0]
    finally:
        con.close()
    assert gravado == novo["atribuicao"] == "RCPN"


# ----------------------------------------------------- o grupo do catálogo

def test_o_grupo_do_catalogo_estreita_o_campo():
    """O grupo diz A QUE ATRIBUIÇÃO o item pertence — e estreitar o campo é o
    que poupa quem atende de procurar Protesto num serviço de Notas."""
    import caixa_depositos as DEP

    assert DEP.atribuicoes_do_grupo(24) == ("RI",)
    assert DEP.atribuicoes_do_grupo(22) == ("RCPN",)
    assert DEP.atribuicoes_do_grupo(25) == ("PROTESTO",)
    # Grupo fora da lista **não estreita nada**: oferecer todas é a resposta
    # certa, e esconder as que a casa usa por causa de um 0 seria pior.
    assert DEP.atribuicoes_do_grupo(0) == ()
    assert DEP.atribuicoes_do_grupo(None) == ()
    assert DEP.atribuicoes_do_grupo("texto") == ()


def test_o_grupo_de_notas_e_firmas_nao_escolhe_sozinho(cg_casa_logada):
    """**A medição que decidiu o desenho.** O grupo 21 é onde o balcão registra
    firma (10.310 usos no acervo) e ato de livro (1.576) — dois preços e dois
    caminhos de selo. Se o grupo escolhesse, o sistema diria «Notas» sobre
    dinheiro de firma, e ninguém veria."""
    import caixa_depositos as DEP

    banco = cg_casa_logada["banco"]
    _semear_catalogo(banco)
    con = _con(banco)
    try:
        achados = DEP.buscar_servicos(con, "ZZTIPO")
    finally:
        con.close()
    assert len(achados) == 2, f"a busca achou {len(achados)} em vez de 2"
    for a in achados:
        assert a["atribuicoes"] == ("FIRMAS", "NOTAS")
        assert a["atribuicao"] is None, \
            "o campo foi oferecido já escolhido onde a casa usa os dois"


def test_o_servico_de_um_grupo_so_ja_vem_estreitado(cg_db, cg_casa_logada):
    """Do outro lado: quando o grupo decide, a sugestão vem com procedência —
    sugestão sem procedência é palpite."""
    import caixa_depositos as DEP

    _semear_catalogo(cg_casa_logada["banco"])
    with cg_db.transaction() as con:
        dica = DEP.sugerir_tipo(con, servico_codigo=990004)
    assert dica["atribuicao"] == "RI"
    assert "16.24.4" in dica["de_onde"]
    assert dica["atribuicoes"] == ("RI",)


def test_o_servico_sem_grupo_oferece_as_oito_atribuicoes(cg_db, cg_casa_logada):
    """Instalação sem o grupo semeado continua funcionando — e oferecer as oito
    é melhor do que o campo vazio."""
    import caixa_depositos as DEP

    _semear_catalogo(cg_casa_logada["banco"])
    with cg_db.transaction() as con:
        dica = DEP.sugerir_tipo(con, servico_codigo=990005)
    assert dica["atribuicao"] is None
    assert tuple(dica["atribuicoes"]) == tuple(DEP.ATRIBUICOES)


# ------------------------------------------------- a busca sem JavaScript

def test_a_busca_do_servico_e_do_servidor(cg_casa_logada):
    """A busca da tela do protocolo é instantânea porque o formulário dela não
    recarrega ao digitar. Aqui o formulário **é** o cadastro do depósito, e uma
    busca que sequestrasse o Enter faria o balcão registrar depósito sem
    querer. Então procura-se no servidor, e a lista vem na página."""
    _semear_catalogo(cg_casa_logada["banco"])
    html = cg_casa_logada["c"].get(
        "/caixa/depositos?servico_termo=ZZTIPO").get_data(as_text=True)
    assert "99.91.1" in html and "99.91.2" in html, \
        "a busca não trouxe os dois serviços"
    assert "escolher" in html, "a lista não oferece escolher"


def test_a_busca_que_nao_acha_diz_onde_procurar(cg_casa_logada):
    _semear_catalogo(cg_casa_logada["banco"])
    html = cg_casa_logada["c"].get(
        "/caixa/depositos?servico_termo=ZZNONEC").get_data(as_text=True)
    assert "Nenhum serviço do catálogo" in html
    assert "13.17.2" in html, "a tela não dá um exemplo de código do TJ"


def test_a_busca_do_servico_nao_grava_nada(cg_casa_logada):
    """Conferir e gravar são dois momentos: uma busca que gravasse deixaria
    depósito registrado por quem só estava procurando o código."""
    _semear_catalogo(cg_casa_logada["banco"])
    antes = len(_depositos_do_banco(cg_casa_logada["banco"]))
    cg_casa_logada["c"].get("/caixa/depositos?servico_termo=ZZTIPO")
    assert len(_depositos_do_banco(cg_casa_logada["banco"])) == antes


# --------------------------------------------------- a régua e a afinidade

def test_o_servico_do_catalogo_nao_mexe_no_row_factory_de_quem_chama(cg_db,
                                                                    cg_casa_logada):
    """**A afinidade do SQLite pelo lado da conexão compartilhada.** Estas
    funções rodam DENTRO da transação de quem cria o depósito; trocar o
    `row_factory` da conexão alheia mudaria o que o chamador lê depois — e o
    defeito apareceria longe daqui, num `linha["coluna"]` que virou tupla."""
    import caixa_depositos as DEP

    _semear_catalogo(cg_casa_logada["banco"])
    con = _con(cg_casa_logada["banco"])          # row_factory = sqlite3.Row
    try:
        DEP.servico_do_catalogo(con, 990001)
        DEP.buscar_servicos(con, "ZZTIPO")
        DEP.atribuicao_do_vinculo(con, ri_protocolo_id=1)
        linha = con.execute("SELECT 1 AS x").fetchone()
        assert linha["x"] == 1, \
            "uma destas funções trocou o row_factory de quem a chamou"
    finally:
        con.close()


def test_o_servico_gravado_e_o_mesmo_que_o_protocolo_usa(cg_casa_logada):
    """**A mesma palavra quer dizer a mesma coisa nos dois lugares.** O item do
    catálogo no depósito e o item do catálogo no protocolo são o mesmo campo,
    com o mesmo nome e o mesmo tipo — duas colunas com nomes parecidos e tipos
    diferentes é como as duas divergem."""
    con = _con(cg_casa_logada["banco"])
    try:
        def tipo(tabela: str) -> str:
            for r in con.execute(f"PRAGMA table_info({tabela})"):
                if r[1] == "servico_codigo":
                    return r[2].upper()
            return ""

        assert tipo("cx_depositos") == "INTEGER"
        assert tipo("cx_protocolo_atos") == "INTEGER"
    finally:
        con.close()


def test_as_tres_telas_gravam_pelo_mesmo_modulo_e_o_vinculo_responde():
    """O depósito nasce em três telas — o caixa, o título do RI e o ato das
    Notas —, e **só a do caixa pergunta**: nas outras duas o vínculo já
    responde. Escrever o campo lá seria pedir de novo o que o sistema sabe."""
    caixa = (RAIZ / "caixa_web.py").read_text(encoding="utf-8")
    ri = (RAIZ / "ri_web.py").read_text(encoding="utf-8")
    notas = (RAIZ / "notas_web.py").read_text(encoding="utf-8")
    for nome, codigo in (("caixa_web", caixa), ("ri_web", ri),
                         ("notas_web", notas)):
        assert "INSERT INTO cx_depositos" not in codigo, \
            f"{nome} voltou a criar depósito por fora do módulo"
        assert "DEP.criar(" in codigo, f"{nome} não usa o módulo comum"
    assert "ri_protocolo_id=protocolo_id" in ri
    assert "nt_ato_id=ato_id" in notas
    for nome, codigo in (("ri_web", ri), ("notas_web", notas)):
        assert 'name="atribuicao"' not in codigo.split("DEP.criar(")[0][-3000:], \
            f"{nome} passou a perguntar o que o vínculo já responde"
