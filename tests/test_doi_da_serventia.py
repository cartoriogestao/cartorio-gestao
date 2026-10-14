"""A DOI da serventia — as escrituras entram no mesmo arquivo dos registros.

O RELATO DO OFICIAL, em 27/08/2026:

    «Consta apenas DOI e CTP no registro de imóveis, deveríamos ter para as
     escrituras também, com intercomunicabilidade para que o arquivo da DOI
     seja possível gerar único, com tudo da serventia.»

E a decisão dele em 28/08: **um arquivo só, das duas atribuições.** É o que a
Receita espera — uma declaração por serventia por mês —, e esta casa tem um CNS
só, de ofício único.

O QUE SE MEDIU ANTES DE CONSTRUIR
    As colunas `com_imovel`, `doi_transacao`, `doi_tipo_imovel`, `doi_matricula`,
    `doi_endereco` e `doi_area` **já existiam** em `nt_atos` desde a importação
    do E-Ofício — e **nenhuma tela as preenchia**: zero em 260 escrituras.

    E `notas_doi.py` — que tem o módulo inteiro, com prazo, conferência,
    montagem e geração do arquivo — era chamado **só pelo Registro de Imóveis**,
    apesar do nome.

    Não faltava o módulo nem o lugar de guardar. Faltava a tela, e faltava
    juntar as duas pontas.

POR QUE UM ARQUIVO E NÃO DOIS
    Duas telas gerariam dois arquivos, e alguém mandaria um só. O prazo é do
    mês, e quem controla o prazo tem de ver o mês inteiro num lugar.
"""
from __future__ import annotations

import glob
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import notas_doi as NDOI
import ri_ctp as CTP

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa):
    """App/DB compartilhados do modulo (conftest); setup de dominio por teste."""
    db = cg_casa["db"]
    c = cg_casa["cliente"]
    db.create_user("jean", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    db.set_settings({"ri_cns": "000000", "ri_codigo_ibge": "2198765"})
    c.post("/login",
           data={"username": "jean", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return cg_casa

def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _escritura(casa, data="2026-07-15", partes=None) -> int:
    con = _con(casa)
    with con:
        cur = con.execute(
            """INSERT INTO nt_atos (tipo, data, natureza, livro, folha,
                   situacao, origem, criado_em, valor_transacao)
               VALUES ('ESCRITURA', ?, 'COMPRA E VENDA', '1', '10',
                       'LAVRADO', 'MANUAL', '2026-07-15T09:00', 12000000)""", (data,))
        aid = int(cur.lastrowid)
        _partes(con, aid, partes or (("VENDEDOR(A)", "FULANO DE TAL"),
                                     ("COMPRADOR(A)", "BELTRANA DE TAL")))
    return aid


def _partes(con, ato_id, quais):
    """A qualificacao e CAMPO LIVRE — e por isso os testes usam o que o balcao
    escreveu de verdade, e nao um vocabulario arrumado que so existe aqui."""
    for qualificacao, nome in quais:
        con.execute(
            """INSERT INTO nt_ato_partes (ato_id, qualificacao, nome,
                   documento, criado_em)
               VALUES (?,?,?, '00000000191', '2026-07-15T09:00')""",
            (ato_id, qualificacao, nome))


def _anotar_imovel(casa, ato_id, **campos):
    """Manda de volta o que a TELA veio preenchida, como o navegador faria.

    Os percentuais de participação vêm sugeridos no campo, e um teste que os
    inventasse por conta própria provaria a regra e não a tela — que é o
    engano que este projeto já cometeu: teste que aplica a suposição aos dois
    lados não testa a suposição. Aqui a sugestão que a tela mostrou é a que
    volta, e por isso o teste também prova que ela é aceitável.
    """
    html = casa["cliente"].get(
        f"/notas/atos/{ato_id}").get_data(as_text=True)
    dados = {"csrf_token": _token(html), "acao": "imovel"}
    for parte_id, valor in re.findall(
            r'name="participacao_(\d+)"[^>]*value="([^"]*)"', html):
        dados[f"participacao_{parte_id}"] = valor
    dados.update(campos)
    return casa["cliente"].post(f"/notas/atos/{ato_id}", data=dados,
                                follow_redirects=True)


# ------------------------------------------- o painel na ficha da escritura


def test_a_escritura_tem_painel_da_doi(casa):
    aid = _escritura(casa)
    html = casa["cliente"].get(f"/notas/atos/{aid}").get_data(as_text=True)
    assert "para a DOI" in html
    assert 'name="com_imovel"' in html
    assert 'name="doi_matricula"' in html
    # e a operação é ESCOLHIDA, não digitada
    assert "Compra e venda" in html


def test_os_dados_do_imovel_ficam_gravados(casa):
    aid = _escritura(casa)
    _anotar_imovel(casa, aid, com_imovel="1", doi_transacao="11",
                   doi_tipo_imovel="67", doi_matricula="4010",
                   doi_endereco="RUA DAS FLORES, 10", doi_area="360")
    r = _con(casa).execute("SELECT * FROM nt_atos WHERE id=?", (aid,)).fetchone()
    assert r["com_imovel"] == 1
    # 11 e nao "11": `doi_transacao` e coluna INTEGER, e a afinidade do SQLite
    # converte na entrada. Quem ler esperando texto compara com o que nao esta la.
    assert r["doi_transacao"] == 11
    assert r["doi_matricula"] == "4010"


def test_permuta_com_torna_e_papeis_ficam_no_vinculo_do_ato(casa, monkeypatch):
    aid = _escritura(casa, partes=(("", "JERLAN"), ("", "LEIDE"),
                                    ("", "TRANSMITENTE")))
    con = _con(casa)
    partes = con.execute("SELECT id, nome FROM nt_ato_partes WHERE ato_id=? ORDER BY id",
                         (aid,)).fetchall()
    for p, lado in zip(partes, ("ADQUIRENTE", "ADQUIRENTE", "ALIENANTE")):
        html = casa["cliente"].get(f"/notas/atos/{aid}").get_data(as_text=True)
        casa["cliente"].post(f"/notas/atos/{aid}",
                             data={"csrf_token": _token(html), "acao": "papel_doi",
                                   "parte_id": p["id"], "doi_lado": lado})
    _anotar_imovel(casa, aid, com_imovel="1", doi_transacao="13",
                   doi_tipo_imovel="67", doi_matricula="4010",
                   doi_torna_dinheiro="10000,00")
    ato = con.execute("SELECT doi_transacao, doi_torna_dinheiro FROM nt_atos WHERE id=?",
                      (aid,)).fetchone()
    assert tuple(ato) == (13, 1000000)
    assert [r[0] for r in con.execute(
        "SELECT doi_lado FROM nt_ato_partes WHERE ato_id=? ORDER BY id", (aid,))] == [
            "ADQUIRENTE", "ADQUIRENTE", "ALIENANTE"]
    assert con.execute("SELECT COUNT(*) FROM nt_cartoes").fetchone()[0] == 0
    capturados = []
    declarar = NDOI.declarar
    def guardar(dec, *args, **kwargs):
        capturados.append(dec)
        return declarar(dec, *args, **kwargs)
    monkeypatch.setattr(NDOI, "declarar", guardar)
    resposta = casa["cliente"].get("/registro-imoveis/doi?competencia=2026-07")
    assert resposta.status_code == 200
    dec = next(d for d in capturados if d.get("ato_id") == aid)
    assert dec["operacao"] == 13
    assert dec["valor_operacao"] == 12000000
    assert dec["houve_permuta"] is True
    assert dec["houve_pagamento_dinheiro"] is True
    assert dec["valor_especie"] == 1000000
    assert [p["nome"] for p in dec["adquirentes"]] == ["JERLAN", "LEIDE"]


def test_operacao_fora_da_tabela_da_receita_e_recusada(casa):
    """Código de operação digitado à mão é o que a Receita recusa sem dizer
    qual linha — e a multa é da serventia."""
    aid = _escritura(casa)
    html = _anotar_imovel(casa, aid, com_imovel="1",
                          doi_transacao="99").get_data(as_text=True)
    assert "não é uma operação imobiliária" in html
    assert _con(casa).execute(
        "SELECT doi_transacao FROM nt_atos WHERE id=?",
        (aid,)).fetchone()["doi_transacao"] is None


def test_marcar_sem_imovel_tira_da_lista(casa):
    """Procuração, ata e declaração não transmitem imóvel. Sem essa marca elas
    ficariam cobrando para sempre — e lista que nunca diminui ninguém olha."""
    aid = _escritura(casa)
    html = _anotar_imovel(casa, aid).get_data(as_text=True)
    assert "não entra na DOI" in html
    assert _con(casa).execute(
        "SELECT com_imovel FROM nt_atos WHERE id=?",
        (aid,)).fetchone()["com_imovel"] == 0


# --------------------------------------------- e o arquivo é um só


def test_a_escritura_aparece_na_doi_da_competencia(casa):
    aid = _escritura(casa, "2026-07-15")
    _anotar_imovel(casa, aid, com_imovel="1", doi_transacao="11",
                   doi_tipo_imovel="67", doi_matricula="4010",
                   doi_endereco="RUA DAS FLORES, 10", doi_area="360")
    html = casa["cliente"].get(
        "/registro-imoveis/doi?competencia=2026-07").get_data(as_text=True)
    # a marca da linha, e não a palavra solta: «Tabelionato» também está no
    # menu lateral de toda tela, e a busca por ela passaria sempre
    assert '<span class="badge">Tabelionato</span>' in html, (
        "a escritura não apareceu na DOI — o arquivo continuou só do RI")
    # e a operação sai por extenso, e não como o código 11
    assert "Compra e venda" in html


def test_a_tela_diz_de_onde_cada_ato_veio(casa):
    """As duas atribuições saem no mesmo arquivo, e quem confere precisa saber
    qual linha é de qual — senão a conferência vira procurar em duas telas."""
    aid = _escritura(casa)
    _anotar_imovel(casa, aid, com_imovel="1", doi_transacao="11",
                   doi_matricula="4010")
    html = casa["cliente"].get(
        "/registro-imoveis/doi?competencia=2026-07").get_data(as_text=True)
    assert '<span class="badge">Tabelionato</span>' in html


def test_escritura_incompleta_nao_entra_e_diz_o_que_falta(casa):
    """Declaração incompleta é recusada pela Receita sem dizer qual linha."""
    aid = _escritura(casa)
    _anotar_imovel(casa, aid, com_imovel="1")     # sem operação nem matrícula
    html = casa["cliente"].get(
        "/registro-imoveis/doi?competencia=2026-07").get_data(as_text=True)
    assert "falta" in html
    assert "a operação" in html or "a matrícula do imóvel" in html


def test_escritura_sem_imovel_nao_entra_na_lista(casa):
    aid = _escritura(casa)
    _anotar_imovel(casa, aid)      # marcada como sem imóvel
    html = casa["cliente"].get(
        "/registro-imoveis/doi?competencia=2026-07").get_data(as_text=True)
    assert '<span class="badge">Tabelionato</span>' not in html


def test_a_tela_se_chama_da_serventia_e_nao_do_ri():
    """Duas telas gerariam dois arquivos, e alguém mandaria um só."""
    html = (RAIZ / "templates" / "ri_doi.html").read_text(encoding="utf-8")
    assert "DOI da serventia" in html
    assert "Registro de Imóveis e" in html and "Tabelionato" in html


# ------------------------------------------- as tabelas moram num lugar só


def test_as_tabelas_da_receita_nao_estao_duplicadas():
    """A DOI e a CTP usam as mesmas, e duplicá-las as faria divergir no
    primeiro código que a Receita mudasse."""
    notas = (RAIZ / "notas_web.py").read_text(encoding="utf-8")
    assert "import ri_ctp as CTP" in notas
    assert "TIPO_OPERACAO = {" not in notas, (
        "as tabelas da Receita foram copiadas para dentro do módulo de notas")
    assert "11" in CTP.TIPO_OPERACAO and "67" in CTP.TIPO_IMOVEL


# ------------------------------------------- de que lado cada parte está


def test_o_procurador_do_vendedor_nao_e_o_vendedor():
    """A armadilha: «PROCURADOR DO VENDEDOR» contém «VENDEDOR».

    Quem procurasse o vendedor primeiro mandaria à Receita o CPF de quem só
    assinou por outro, como se ele tivesse vendido o imóvel — cruzado com a
    declaração de imposto de renda dele. Por isso o descarte vem ANTES.
    """
    assert NDOI.lado_da_parte("PROCURADOR DO VENDEDOR") == "FORA"
    assert NDOI.lado_da_parte("PROCURADORA DA VENDEDORA") == "FORA"
    assert NDOI.lado_da_parte("Procurador do vendedor") == "FORA"
    assert NDOI.lado_da_parte("PROCURADOR DO PROPRIETÁRIO") == "FORA"
    assert NDOI.lado_da_parte("VENDEDOR(A)") == "ALIENANTE"


def test_o_herdeiro_que_cede_esta_do_lado_de_quem_cede():
    """A mesma armadilha do outro lado: `HERDEIRO(A) CEDENTE` bateria nas duas
    listas se `HERDEIRO` estivesse na de quem adquire, e a ordem das regras
    decidiria — dando uma resposta com cara de certa."""
    assert NDOI.lado_da_parte("HERDEIRO(A) CEDENTE") == "ALIENANTE"


def test_o_que_nao_se_reconhece_vira_duvida_e_nao_some():
    """Mandar só quem se reconheceu deixaria a declaração BEM FORMADA e sem
    quem alienou — e a Receita aceitaria. Declaração aceita sem o alienante é
    pior que declaração recusada: a recusada volta."""
    partes = [{"nome": "AGNI", "qualificacao": "DECLARANTE"},
              {"nome": "ZEZE", "qualificacao": "PERMUTANTE"},
              {"nome": "SEM", "qualificacao": ""}]
    alienantes, adquirentes, duvidas = NDOI.lados_das_partes(partes)
    assert not alienantes and not adquirentes
    assert [d["nome"] for d in duvidas] == ["AGNI", "ZEZE", "SEM"]


def test_a_testemunha_nunca_entra_na_declaracao():
    assert NDOI.lado_da_parte("TESTEMUNHA") == "FORA"
    assert NDOI.lado_da_parte("REPRESENTANTE") == "FORA"


def test_o_acento_e_a_caixa_nao_mudam_o_lado():
    """O balcão escreve como fala: `VENDEDOR(A)`, `Vendedor(a)` e `VENDEDORA`
    são a mesma coisa, e as três aparecem no acervo. O acento também não pode
    separar — `DONATÁRIO(A)` está escrito com ele."""
    for escrito in ("VENDEDOR(A)", "Vendedor(a)", "VENDEDORA", "vendedor"):
        assert NDOI.lado_da_parte(escrito) == "ALIENANTE", escrito
    for escrito in ("COMPRADOR(A)", "Comprador(a)", "COMPRADORA"):
        assert NDOI.lado_da_parte(escrito) == "ADQUIRENTE", escrito
    for escrito in ("DONATÁRIO(A)", "DONATARIO(A)", "Donatário(a)"):
        assert NDOI.lado_da_parte(escrito) == "ADQUIRENTE", escrito


def test_a_escritura_so_com_vendedoras_para_e_diz_por_que(casa):
    """Medido: 20 das 37 escrituras do acervo têm um lado só — o escrevente
    lançou as vendedoras e mais ninguém. Elas não podem virar declaração."""
    aid = _escritura(casa, partes=(("VENDEDORA", "MARIA UM"),
                                   ("VENDEDORA", "MARIA DOIS")))
    _anotar_imovel(casa, aid, com_imovel="1", doi_transacao="11",
                   doi_tipo_imovel="67", doi_matricula="4010")
    html = casa["cliente"].get(
        "/registro-imoveis/doi?competencia=2026-07").get_data(as_text=True)
    assert "quem adquiriu" in html


def test_a_duvida_diz_o_nome_e_a_qualificacao(casa):
    """Quem for consertar precisa saber QUEM e o que está escrito — senão a
    conferência vira abrir as escrituras uma a uma."""
    aid = _escritura(casa, partes=(("VENDEDOR(A)", "FULANO DE TAL"),
                                   ("COMPRADOR(A)", "BELTRANA DE TAL"),
                                   ("DECLARANTE", "AGNI DE TAL")))
    _anotar_imovel(casa, aid, com_imovel="1", doi_transacao="11",
                   doi_tipo_imovel="67", doi_matricula="4010")
    html = casa["cliente"].get(
        "/registro-imoveis/doi?competencia=2026-07").get_data(as_text=True)
    assert "AGNI DE TAL" in html and "DECLARANTE" in html


def test_a_conferencia_conta_as_escrituras_paradas_antes_de_gerar(casa):
    """A metade que o oficial pediu: «a tela mensal mostra o que ficou faltando
    antes de gerar o arquivo». O resumo já existia e contava só os atos do RI,
    porque eu havia escrito a chave `texto` onde ele lê `motivo`."""
    aid = _escritura(casa)
    _anotar_imovel(casa, aid, com_imovel="1")      # sem operação nem matrícula
    html = casa["cliente"].get(
        "/registro-imoveis/doi?competencia=2026-07").get_data(as_text=True)
    # a conta no alto, ANTES das ações — a ordem da tela do IBGE
    assert "O que falta" in html
    assert "1 parada" in html
    assert (html.index("falta a operação imobiliária")
            < html.index('name="acao"'))


def test_o_resumo_nao_estoura_com_escritura_parada(casa):
    """`resumo_impedimentos` lê `problema["motivo"]`: com a chave errada a tela
    inteira dava erro 500 em vez de mostrar a conferência."""
    aid = _escritura(casa)
    _anotar_imovel(casa, aid, com_imovel="1")
    assert casa["cliente"].get(
        "/registro-imoveis/doi?competencia=2026-07").status_code == 200


def test_o_proprietario_nao_diz_o_lado():
    """A escritura 222 do acervo desmente a regra que eu tinha escrito:
    `Proprietário(a)` aparece AO LADO de um `Vendedor(a)` e de dois
    compradores. Se o proprietário fosse o vendedor, o vendedor não estaria
    ali. Nos outros três atos em que aparece não há contraparte nenhuma."""
    assert NDOI.lado_da_parte("PROPRIETÁRIO(A)") == "DUVIDA"
    assert NDOI.lado_da_parte("Proprietário(a)") == "DUVIDA"
    # mas o procurador DELE continua fora, e não em dúvida
    assert NDOI.lado_da_parte("PROCURADOR DO PROPRIETÁRIO") == "FORA"


def test_as_duas_reguas_de_papel_ficam_separadas():
    """`ri_ctp._papel` responde a mesma pergunta para o Registro de Imóveis, e
    as duas NÃO se juntam: lá `papel` é vocabulário controlado e
    `proprietario` quer dizer «dono de registro» — 3.894 das 3.992 linhas.
    Juntá-las faria todos eles virarem alienantes de uma hora para outra.

    Este teste fica vermelho se alguém unificar sem tratar isso."""
    import ri_ctp
    assert ri_ctp._papel({"papel": "proprietario"}) == "", (
        "o dono de registro do RI passou a contar como parte do negócio")
    assert NDOI.lado_da_parte("proprietario") == "DUVIDA"
    # e os avisos que explicam a separação continuam nos dois arquivos
    for arquivo in ("ri_ctp.py", "notas_doi.py"):
        texto = (RAIZ / arquivo).read_text(encoding="utf-8")
        assert "separadas de proposito" in texto.lower(), arquivo


# ------------------------------------------- a participação de cada parte


def test_a_sugestao_divide_em_partes_iguais_e_fecha_em_cem():
    """O resto da divisão vai no primeiro, e não se espalha: sete pessoas dão
    14,28 sete vezes, que soma 99,96 — e a faixa da Receita não perdoaria um
    número de partes maior."""
    assert NDOI.participacoes_sugeridas(1) == ["100,00"]
    assert NDOI.participacoes_sugeridas(2) == ["50,00", "50,00"]
    assert NDOI.participacoes_sugeridas(3) == ["33,34", "33,33", "33,33"]
    for quantos in range(1, 30):
        soma = sum(float(x.replace(",", "."))
                   for x in NDOI.participacoes_sugeridas(quantos))
        assert abs(soma - 100.0) < 0.005, quantos


def test_a_ficha_doi_avisa_quando_nao_ha_partes(casa):
    """Sem partes, o painel da DOI não pode sumir em silêncio — quem lavra
    precisa saber que falta cadastrar no bloco de cima."""
    aid = _escritura(casa)
    con = _con(casa)
    with con:
        con.execute("DELETE FROM nt_ato_partes WHERE ato_id=?", (aid,))
    assert con.execute(
        "SELECT COUNT(*) n FROM nt_ato_partes WHERE ato_id=?",
        (aid,)).fetchone()["n"] == 0
    html = casa["cliente"].get(f"/notas/atos/{aid}").get_data(as_text=True)
    assert "Nenhuma parte nesta" in html and "escritura" in html
    assert "painel" in html.lower() and "Partes" in html


def test_a_sugestao_aparece_na_ficha_preenchida(casa):
    """«A sugestão fica visível — ninguém manda um número sem ver qual é»."""
    aid = _escritura(casa)
    html = casa["cliente"].get(f"/notas/atos/{aid}").get_data(as_text=True)
    assert "Participação" in html
    achados = re.findall(r'name="participacao_\d+"[^>]*value="([^"]*)"', html)
    assert achados == ["100,00", "100,00"], achados   # um de cada lado


def test_a_ficha_mostra_de_que_lado_cada_parte_esta(casa):
    """É aqui que quem lavra descobre que escreveu «Declarante» onde precisava
    de «Vendedor» — e não no fim do mês, na tela da DOI."""
    aid = _escritura(casa, partes=(("VENDEDOR(A)", "FULANO DE TAL"),
                                   ("COMPRADOR(A)", "BELTRANA DE TAL"),
                                   ("TESTEMUNHA", "ZEZE DE TAL"),
                                   ("DECLARANTE", "AGNI DE TAL")))
    html = casa["cliente"].get(f"/notas/atos/{aid}").get_data(as_text=True)
    assert "alienou" in html and "adquiriu" in html
    assert "não é parte do negócio" in html          # a testemunha
    assert "não dá para saber o lado" in html        # o declarante


def test_a_participacao_fora_da_faixa_e_recusada_no_balcao(casa):
    """A Receita recusa o ARQUIVO INTEIRO fora de 99% a 100%, e não a linha.
    Descobrir isso no fim do mês custa o prazo da serventia."""
    aid = _escritura(casa)
    html = _anotar_imovel(casa, aid, com_imovel="1", doi_transacao="11",
                          doi_matricula="4010",
                          **{f"participacao_{i}": "30,00"
                             for i in _ids_das_partes(casa, aid)}
                          ).get_data(as_text=True)
    assert "99,00% e 100,00%" in html
    # e nada foi gravado: recusa não grava metade
    assert _con(casa).execute(
        "SELECT com_imovel FROM nt_atos WHERE id=?",
        (aid,)).fetchone()["com_imovel"] == 0


def test_a_participacao_gravada_vale_mais_que_a_sugestao(casa):
    """Dois vendedores podem não ser meeiros."""
    aid = _escritura(casa, partes=(("VENDEDOR(A)", "UM DE TAL"),
                                   ("VENDEDOR(A)", "DOIS DE TAL"),
                                   ("COMPRADOR(A)", "TRES DE TAL")))
    ids = _ids_das_partes(casa, aid)
    _anotar_imovel(casa, aid, com_imovel="1", doi_transacao="11",
                   doi_matricula="4010",
                   **{f"participacao_{ids[0]}": "70,00",
                      f"participacao_{ids[1]}": "30,00",
                      f"participacao_{ids[2]}": "100,00"})
    guardado = [r["participacao"] for r in _con(casa).execute(
        "SELECT participacao FROM nt_ato_partes WHERE ato_id=? ORDER BY id",
        (aid,))]
    assert guardado == ["70,00", "30,00", "100,00"]
    # e a ficha devolve o gravado, não a sugestão de 50/50
    html = casa["cliente"].get(f"/notas/atos/{aid}").get_data(as_text=True)
    assert "70,00" in html and "50,00" not in html


def test_o_select_devolve_a_operacao_que_foi_gravada(casa):
    """`doi_transacao` é coluna INTEGER: o «11» gravado como texto volta como o
    número 11, e `11 == "11"` é falso. O escrevente escolhia «Compra e venda»,
    gravava, reabria a ficha e via «— não informada —»: pareceria que a tela
    não gravou nada."""
    aid = _escritura(casa)
    _anotar_imovel(casa, aid, com_imovel="1", doi_transacao="11",
                   doi_tipo_imovel="67", doi_matricula="4010")
    html = casa["cliente"].get(f"/notas/atos/{aid}").get_data(as_text=True)
    assert re.search(r'<option value="11"\s+selected>', html), (
        "a operação gravada não voltou marcada na caixa de seleção")
    assert re.search(r'<option value="67"\s+selected>', html)


def _ids_das_partes(casa, ato_id):
    return [r["id"] for r in _con(casa).execute(
        "SELECT id FROM nt_ato_partes WHERE ato_id=? ORDER BY id", (ato_id,))]
