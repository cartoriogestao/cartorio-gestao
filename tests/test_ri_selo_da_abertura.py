"""O SELO DA ABERTURA DE MATRÍCULA — 16/09/2026.

    «como emito e coloco o selo de abertura de matricula nessa 4016»
                                                          — o oficial

A RESPOSTA ERA «NÃO HÁ COMO», e o buraco era total. Medido na produção em
16/09/2026: das **1.982 matrículas** desta casa, **zero** têm
`selo_abertura_texto`. A coluna existe desde sempre; a única linha que a
escrevia é o `INSERT` de `ri_nova_matricula`, lendo um campo de formulário que
**nenhuma tela oferecia** — `grep` nos 100 modelos não acha um. Ela era LIDA
para o `.odt` da ficha e nunca escrita por ninguém.

    Não faltava um botão: faltava o caminho inteiro. É «a peça pronta que
    ninguém usa» na forma mais pura — e, ao contrário das outras vezes, aqui
    nem o chamador existia.

O QUE ESTES TESTES GUARDAM, e por quê

  1. **A forma do envelope**, medida nos 41 selos reais que esta casa emitiu
     por `/selo/imovel/lote/subdivisao`. Ela NÃO é a do registro/averbação:
     `naturezaTitulo` **127.0** contra 126.0, sem `registroAverbacao` e sem
     `descricaoNatureza`. Os dois números estão a um dígito de distância e
     **nenhum erro apareceria na tela** — a diferença sairia no relatório do
     Tribunal, meses depois.

  2. **As recusas ANTES da rede.** Sem item de custa e sem partes o selo não
     sai, e a resposta tem de vir com o cliente na frente. Foi exatamente
     isto que derrubou o selo da AV-05 em 15/09: «Os nomes das partes devem
     ser informados» veio do aparelho, depois de o ato já existir.

  3. **Que a rota tem tela.** O defeito que este projeto mais repetiu — sete
     vezes — é a rota que grava sem tela que a chame.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ato_selado as AS


# ----------------------------------------------- o envelope, contra o acervo


def test_a_natureza_da_abertura_nao_e_a_do_ato():
    """127.0 e 126.0 estão a um dígito, e a troca não daria erro nenhum."""
    assert AS.NATUREZA_DO_TITULO_DA_ABERTURA == 127.0
    assert AS.NATUREZA_DO_TITULO_DO_ATO_DO_RI == 126.0
    assert AS.NATUREZA_DO_TITULO_DA_ABERTURA != AS.NATUREZA_DO_TITULO_DO_ATO_DO_RI


def test_o_caminho_da_abertura_e_o_que_a_casa_usou():
    """41 de 45 usos do item 16.2 saíram por ele, e o 16.2 é o único item."""
    assert AS.CAMINHO_DA_ABERTURA == "/selo/imovel/lote/subdivisao"
    assert AS.CAMINHO_DA_ABERTURA in AS.atribuicoes.CAMINHOS_USADOS_POR_ESTA_CASA \
        if hasattr(AS, "atribuicoes") else True


def _envelope(**kw):
    campos = {
        "matricula": "4016",
        "escrevente": "Beatriz Exemplo de Souza",
        "versao_tabela": "0220260101",
        "livro": "2",
        "codigo_tj": "16.2",
        "protocolo": "11559",
        "partes": [{"nome": "GILSON DIAS BARROS DE CASTELO",
                    "documento": "000.000.030-26"}],
    }
    campos.update(kw)
    return AS.envelope_da_abertura_da_matricula(**campos)


def test_o_envelope_tem_a_forma_medida_nos_41():
    """As chaves são exatamente as dos 41 selos reais — nem mais, nem menos."""
    e = _envelope()
    assert set(e) == {"matricula", "protocolo", "dadosSelo"}, sorted(e)
    assert set(e["dadosSelo"]) == {
        "codigoTipoAto", "descontoProvimento279", "escrevente", "isento",
        "livro", "naturezaTitulo", "partes", "percentualDesconto", "reterIss",
        "versaoTabelaDeCustas"}, sorted(e["dadosSelo"])

    # O QUE ELE NAO TEM, e o registro/averbacao tem:
    assert "registroAverbacao" not in e, (
        "a abertura não é ato numerado do livro — um número ali inventaria "
        "um R-1 que não existe")
    assert "descricaoNatureza" not in e["dadosSelo"], (
        "nenhum dos 41 selos reais a leva")
    assert "quantidade" not in e["dadosSelo"]
    assert "baseCalculo" not in e["dadosSelo"]

    assert e["dadosSelo"]["naturezaTitulo"] == 127.0
    assert e["dadosSelo"]["codigoTipoAto"] == "16.2"
    assert e["matricula"] == "4016", "medido: 31 dos 41 levam a matrícula"
    assert e["dadosSelo"]["livro"] == "2", (
        "o livro é o volume da matrícula, e não o 1A do livro de protocolo")


def test_a_folha_e_opcional_e_nao_se_inventa():
    """Ela apareceu em 15 dos 41; nos outros 26 o campo não vai."""
    assert "folha" not in _envelope()["dadosSelo"]
    assert "folha" not in _envelope(folha="")["dadosSelo"]
    assert _envelope(folha="0")["dadosSelo"]["folha"] == "0"


def test_o_documento_da_parte_vai_so_em_digitos():
    e = _envelope()
    assert e["dadosSelo"]["partes"]["parteAto"] == [
        {"nome": "GILSON DIAS BARROS DE CASTELO", "documento": "00000003026"}]


def test_parte_sem_documento_vai_so_com_o_nome():
    """Um `documento: ''` seria campo inventado."""
    e = _envelope(partes=[{"nome": "ASSOCIACAO DOS PEQUENOS PRODUTORES"}])
    assert e["dadosSelo"]["partes"]["parteAto"] == [
        {"nome": "ASSOCIACAO DOS PEQUENOS PRODUTORES"}]


def test_o_envelope_recusa_o_que_o_selo_exige():
    import pytest
    for faltando in ("matricula", "escrevente", "versao_tabela", "codigo_tj"):
        with pytest.raises(AS.AtoError):
            _envelope(**{faltando: ""})


def test_abertura_isenta_sem_motivo_e_recusada():
    import pytest
    with pytest.raises(AS.AtoError):
        _envelope(isento=True, motivo_isencao="")
    e = _envelope(isento=True, motivo_isencao="reurb social")
    assert e["dadosSelo"]["motivoIsentoGratuito"] == "REURB SOCIAL"


# ------------------------------------------- a coluna, e o razão dos selos


def test_o_selo_da_abertura_mora_na_coluna_da_ficha():
    """`ri_matriculas` → `selo_abertura_texto`, e não `selo`.

    É o defeito latente que já custou um HTTP 500 em 15/09: `UPDATE {tabela}
    SET selo=?` com a coluna escrita à mão. `COLUNA_DO_SELO` existe para isso.
    """
    assert AS.COLUNA_DO_SELO["ri_matriculas"] == "selo_abertura_texto"
    assert "ri_matriculas" in AS.TABELAS_DE_ATO, (
        "`selar_o_ato_lavrado` consulta esta lista antes de comprar selo")


def test_a_chave_do_razao_separa_a_abertura_do_ato():
    """`tabela` + `ato_id` — por `ato_id` sozinho vêm selos de outra coisa.

    A matrícula 4.016 tem `id` 5378 e há atos com `id` 5378 noutras tabelas;
    é a mesma razão pela qual os três selos de firma de 2022 não se
    confundiram com os atos 3728-3730 da 3.110.
    """
    assert AS.COLUNA_DO_SELO["ri_matriculas"] != AS.COLUNA_DO_SELO["ri_atos"]


# ------------------------------------------------------- a rota, e a tela


def test_a_rota_de_selar_a_abertura_existe_e_tem_tela(cg_casa):
    """Rota que grava sem tela é o defeito que este projeto mais repetiu."""
    regras = [str(r) for r in cg_casa["app"].url_map.iter_rules()
              if "selar-abertura" in str(r)]
    assert regras, "a rota não foi registrada"

    tela = (RAIZ / "templates" / "ri_ficha.html").read_text(encoding="utf-8")
    assert "ri_selar_abertura" in tela, (
        "a rota grava e nenhuma tela a chama — o defeito que ela nasceu para "
        "fechar era exatamente este")
    assert tela.count("ri_selar_abertura") == 1, (
        "dois formulários para a mesma rota divergem no primeiro conserto")


def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _ficha(con, numero="4016", com_parte=True):
    cur = con.execute(
        """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao,
               tipo_ficha, origem, criado_em, data_abertura)
           VALUES (?, '2', '2', 'ATIVA', 'ESTRUTURADA', 'MANUAL',
                   '2026-09-14T22:43:07', '2026-09-14')""", (numero,))
    mid = int(cur.lastrowid)
    if com_parte:
        con.execute(
            """INSERT INTO ri_partes (matricula_id, ato_id, nome, nome_norm,
                   documento_tipo, documento_numero, documento_valido,
                   papel, proprietario, proprietario_ativo, origem)
               VALUES (?, NULL, 'GILSON DIAS BARROS DE CASTELO',
                       'GILSON DIAS BARROS DE CASTELO', 'CPF', '00000003026', 0,
                       'proprietario', 1, 1, 'MANUAL')""", (mid,))
    return mid


def _token(html: str) -> str:
    import re
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    return achado.group(1) if achado else ""


def test_a_ficha_sem_parte_nao_sela_e_diz_por_que(cg_casa_logada):
    """A recusa é ANTES da rede — foi isto que derrubou a AV-05 em 15/09."""
    casa = cg_casa_logada
    con = _con(casa)
    with con:
        mid = _ficha(con, com_parte=False)
    con.close()

    html = casa["c"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    r = casa["c"].post(f"/registro-imoveis/{mid}/selar-abertura",
                       data={"csrf_token": _token(html), "codigo_tj": "16.2"},
                       follow_redirects=True)
    texto = r.get_data(as_text=True)
    assert "nomes das partes" in texto or "dono do imóvel" in texto, texto[-600:]

    con = _con(casa)
    selo = con.execute("""SELECT selo_abertura_texto FROM ri_matriculas
                            WHERE id=?""", (mid,)).fetchone()[0]
    con.close()
    assert not selo, "nada podia ter sido gravado"


def test_a_ficha_que_ja_tem_selo_e_recusada(cg_casa_logada):
    """Dois selos para a mesma abertura é o dinheiro da casa saindo duas vezes."""
    casa = cg_casa_logada
    con = _con(casa)
    with con:
        mid = _ficha(con)
        con.execute("""UPDATE ri_matriculas SET selo_abertura_texto=?
                        WHERE id=?""", ("SELO-QUE-JA-ESTAVA", mid))
    con.close()

    html = casa["c"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    r = casa["c"].post(f"/registro-imoveis/{mid}/selar-abertura",
                       data={"csrf_token": _token(html), "codigo_tj": "16.2"},
                       follow_redirects=True)
    assert "já tem selo de abertura" in r.get_data(as_text=True)

    con = _con(casa)
    selo = con.execute("""SELECT selo_abertura_texto FROM ri_matriculas
                            WHERE id=?""", (mid,)).fetchone()[0]
    con.close()
    assert selo == "SELO-QUE-JA-ESTAVA", "o selo que estava lá não se perde"


def test_sem_item_de_custa_nao_sela(cg_casa_logada):
    casa = cg_casa_logada
    con = _con(casa)
    with con:
        mid = _ficha(con)
    con.close()
    html = casa["c"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    r = casa["c"].post(f"/registro-imoveis/{mid}/selar-abertura",
                       data={"csrf_token": _token(html)},
                       follow_redirects=True)
    assert "item da tabela de custas" in r.get_data(as_text=True)


def test_o_selo_digitado_a_mao_entra_na_ficha(cg_casa_logada):
    """Quando o aparelho não responde, o balcão não pode parar."""
    casa = cg_casa_logada
    con = _con(casa)
    with con:
        mid = _ficha(con)
    con.close()

    html = casa["c"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    casa["c"].post(f"/registro-imoveis/{mid}/selar-abertura",
                   data={"csrf_token": _token(html),
                         "selo_abertura_texto": "ETIQUETA COLADA A MAO",
                         "emolumentos_abertura": "Ato 16.2 — Total R$ 102,15"},
                   follow_redirects=True)

    con = _con(casa)
    m = con.execute("""SELECT selo_abertura_texto, emolumentos_abertura
                         FROM ri_matriculas WHERE id=?""", (mid,)).fetchone()
    con.close()
    assert m["selo_abertura_texto"] == "ETIQUETA COLADA A MAO"
    assert "102,15" in (m["emolumentos_abertura"] or "")


def test_a_relacao_de_emolumentos_fica_antes_da_rede(cg_casa_logada):
    """Se o aparelho não responder, o que foi digitado não se perde."""
    casa = cg_casa_logada
    con = _con(casa)
    with con:
        mid = _ficha(con)
    con.close()

    html = casa["c"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    # Sem selador configurado nesta instalação de ensaio, o selo não sai — e é
    # justamente o caso que este teste mede.
    casa["c"].post(f"/registro-imoveis/{mid}/selar-abertura",
                   data={"csrf_token": _token(html), "codigo_tj": "16.2",
                         "prenotacao": "11559",
                         "emolumentos_abertura": "Ato 16.2 — Total R$ 102,15"},
                   follow_redirects=True)

    con = _con(casa)
    m = con.execute("""SELECT selo_abertura_texto, emolumentos_abertura
                         FROM ri_matriculas WHERE id=?""", (mid,)).fetchone()
    con.close()
    assert "102,15" in (m["emolumentos_abertura"] or ""), (
        "a relação digitada tinha de ficar na ficha mesmo sem o selo sair")
    assert not m["selo_abertura_texto"], (
        "sem selador não pode haver selo gravado")


def test_a_abertura_nao_lavra_ato_nenhum(cg_casa_logada):
    """Selar a abertura não toma número e não entra na corrente de hash."""
    casa = cg_casa_logada
    con = _con(casa)
    with con:
        mid = _ficha(con)
    con.close()

    html = casa["c"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    casa["c"].post(f"/registro-imoveis/{mid}/selar-abertura",
                   data={"csrf_token": _token(html), "codigo_tj": "16.2",
                         "selo_abertura_texto": "ETIQUETA"},
                   follow_redirects=True)

    con = _con(casa)
    quantos = con.execute("SELECT COUNT(*) FROM ri_atos WHERE matricula_id=?",
                          (mid,)).fetchone()[0]
    con.close()
    assert quantos == 0, "a abertura não é ato do livro de atos"


# ------------------------- o que falta na abertura tem de estar À VISTA


def test_a_ficha_avisa_no_ALTO_o_que_falta_na_abertura(cg_casa_logada):
    """**Ele disse duas vezes que não achava, e as duas coisas existiam.**

        «segue sem o nome e funcao de quem abriu a matricula, segue sem
         possiblidade de selar a abertura da matricula» — 16/09/2026

    MEDIDO ANTES DE MEXER, na ficha real da 4.016: o botão «Selar a abertura
    desta matrícula» estava a **71% da página** (65.263 de 91.510 caracteres),
    dentro de uma **gaveta fechada**, no painel Identificação — que fica no
    fim. E «quem abriu» estava noutra TELA, atrás de «Editar cadastro».

    **Peça que existe e ninguém acha é peça que não existe**, para quem está
    no balcão. E eu ainda o mandei procurar «no painel Identificação»: a
    resposta certa não era explicar melhor, era pôr o aviso onde o olho está.

    Este teste cobra a ORDEM: o aviso vem **antes** do botão na página.
    """
    casa = cg_casa_logada
    con = _con(casa)
    with con:
        mid = _ficha(con)
    con.close()

    html = casa["c"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)

    assert "A abertura desta matrícula ainda não está completa" in html
    assert "Falta o selo da abertura" in html
    assert "Não consta quem abriu a matrícula" in html
    assert (html.index("A abertura desta matrícula")
            < html.index("Selar a abertura desta matrícula")), (
        "o aviso caiu DEPOIS do botão — quem rola a página desiste antes")


def test_a_gaveta_de_selar_vem_ABERTA_enquanto_falta_o_selo(cg_casa_logada):
    """Gaveta guarda o que raramente se usa; isto é o que há para fazer."""
    casa = cg_casa_logada
    con = _con(casa)
    with con:
        mid = _ficha(con)
    con.close()

    html = casa["c"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    assert '<details id="selo-da-abertura" open' in html, (
        "a gaveta voltou a nascer fechada — foi o que escondeu o botão")


def test_ficha_completa_NAO_mostra_o_aviso(cg_casa_logada):
    """Alarme que soa sempre é alarme que ninguém ouve."""
    casa = cg_casa_logada
    con = _con(casa)
    with con:
        mid = _ficha(con)
        con.execute(
            """UPDATE ri_matriculas
                  SET selo_abertura_texto='SELO DE MENTIRA',
                      aberta_nome='Beatriz Exemplo de Souza',
                      aberta_titulo='Tabeliã Registradora Substituta',
                      aberta_tratamento='A'
                WHERE id=?""", (mid,))
    con.close()

    html = casa["c"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    assert "A abertura desta matrícula ainda não está completa" not in html
