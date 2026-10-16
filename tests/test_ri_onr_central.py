"""O indicador real e o edital que sobem A CENTRAL do ONR — dominio e telas.

**NAO CONFUNDIR COM `test_ri_onr.py`**, se ele existir: `ri_onr.py` gera os
ARQUIVOS do ONR (XML e JSON, para envio manual) e `ri_onr_central.py` fala com
a **API**. As duas tem tabelas de tipo de imovel **diferentes**, e ha teste
aqui que guarda a diferenca.

O QUE ESTES TESTES PROTEGEM:

    enviar nao e ser aceito     o ONR processa depois, numa fila propria

    o acervo nao vira atraso    as fichas do E-Oficio ja subiram por outro
                                sistema; manda-las encheria a fila deles

    o que NAO se inventa        o tipo do imovel nao casa por semelhanca, o
                                registro anterior nao se reparte, e o ato cuja
                                natureza nao casa **nao some calado**

    o dono de hoje              `proprietario_ativo`, e nao `proprietario` —
                                mandar as duas publicaria como dono quem vendeu

NENHUM TESTE DAQUI FALA COM O ONR.
"""
from __future__ import annotations

import glob
import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import onr_api as API
import ri_onr as ARQUIVO
import ri_onr_central as ONR
import ri_onr_central_schema as ESQ

SENHA = "Senha#12345"
AGORA = "2026-09-03T10:00:00"
CNS = "000000"


# ------------------------------------------------------- os dois modulos


def test_o_modulo_do_ARQUIVO_e_o_da_API_sao_DOIS(cache=None):
    """**Eu escrevi por cima do primeiro em 03/09/2026**, e o `ImportError` do
    `app` foi quem avisou. Os dois existem, e fazem coisas diferentes."""
    assert hasattr(ARQUIVO, "gerar_indicador_real")   # o arquivo JSON
    assert hasattr(ONR, "enviar_indicador")           # a chamada a API
    assert ARQUIVO.__name__ != ONR.__name__


def test_as_DUAS_tabelas_de_tipo_de_imovel_sao_diferentes():
    """**O achado que a confusao dos nomes revelou.**

    O arquivo usa `TIPO_IMOVEL_ONR`, com os codigos **0 a 9** do
    `tbRI_TipoImovel.onr_id` do E-Oficio; a API usa **64, 65, 15, 71**… Usar
    uma pela outra poria «Loja» onde e «Casa» no indice que o pais consulta.
    """
    do_arquivo = set(ARQUIVO.TIPO_IMOVEL_ONR)
    da_api = set(API.TIPOS_DE_IMOVEL)
    assert do_arquivo == set(range(10))
    assert 64 in da_api and 65 in da_api
    assert not (do_arquivo & da_api), (
        "as duas tabelas passaram a ter codigo em comum — confira antes de usar "
        "uma pela outra")
    # E o mesmo codigo quer dizer coisas diferentes nas duas:
    assert ARQUIVO.TIPO_IMOVEL_ONR[0] == "Casa"
    assert API.TIPOS_DE_IMOVEL[64] == "Casa"


# ----------------------------------------------------------- o endereco


def test_partir_logradouro_acha_o_tipo():
    assert ONR.partir_logradouro("Rua das Flores") == {
        "tipo_codigo": API.CODIGO_DO_LOGRADOURO["rua"],
        "tipo_nome": "Rua", "logradouro": "das Flores"}


def test_partir_logradouro_tenta_da_MAIOR_para_a_MENOR():
    """O catalogo tem nomes de duas palavras. Pegar so a primeira faria «Via
    Expressa Norte» virar tipo «Via» com logradouro «Expressa Norte»."""
    achado = ONR.partir_logradouro("Via Expressa Norte")
    assert achado["tipo_nome"] == "Via Expressa"
    assert achado["logradouro"] == "Norte"


def test_logradouro_sem_tipo_conhecido_NAO_vira_codigo():
    achado = ONR.partir_logradouro("Flores, 100")
    assert achado["tipo_codigo"] is None
    assert achado["logradouro"] == "Flores, 100"


def test_partir_logradouro_ignora_acento_e_caixa():
    assert ONR.partir_logradouro("PRAÇA DA MATRIZ")["tipo_nome"] == "Praça"


# --------------------------------------------------------------- a casa


def _sessao(cg_casa, papel: str = "ADMIN"):
    app = cg_casa['app']
    banco = cg_casa['banco']
    dados = cg_casa['dados']
    bd = cg_casa['db']
    bd.create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS", SENHA, papel)
    bd.set_settings({"ri_cns": CNS, "ri_cidade": "Cidade Exemplo", "ri_uf": "MA",
                     "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
                     "serventia_endereco": "Rua da Matriz, 10",
                     "serventia_cep": "65926000"})
    c = app.test_client()
    c.post("/login",
           data={"username": "tabeliao", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {"app": app, "c": c, "banco": banco, "db": bd}


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    return achado.group(1) if achado else ""


@pytest.fixture()
def s(cg_casa):
    return _sessao(cg_casa)


@pytest.fixture()
def com_credencial(monkeypatch):
    monkeypatch.setattr(API, "tem_credencial", lambda *a, **k: True)


@pytest.fixture()
def sem_credencial(monkeypatch):
    """O espelho de `com_credencial`: **sem** credencial, e declarado.

    **A METADE «SEM» NÃO ESTAVA DECLARADA EM NENHUM DOS QUATRO ARQUIVOS** —
    medido em 18/09/2026. Onde havia fixture, ela prendia o lado «com»; o lado
    «sem» perguntava ao disco. Enquanto o credencial daquela Central não
    existia em `%PROGRAMDATA%`, o teste passava; no dia em que o oficial o
    informasse, ficava vermelho **sem uma linha de código mudar**.

    Foi o que aconteceu com o ONRTDPJ em 12/09/2026 (ver
    `test_rg_onrtdpj_web.py::test_sem_token_a_tela_DIZ_onde_pegar`). E é o que
    espera os outros três: `onrcpn.cred`, `resolve.cred` e `onr.cred` são
    justamente as credenciais que `DOCUMENTACAO/PEDIDO_DAS_CREDENCIAIS.md` foi
    pedir.
    """
    monkeypatch.setattr(API, "tem_credencial", lambda *a, **k: False)


def _con(s) -> sqlite3.Connection:
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    return con


def _matricula(s, **campos) -> int:
    base = {"numero": 4014, "livro": "2", "livro_norm": "2",
            "tipo_ficha": "ESTRUTURADA", "tipo_imovel": "Casa",
            "rural_urbano": "Urbano", "logradouro": "Rua das Flores",
            "numero_predial": "100", "bairro": "Centro",
            "cidade": "Cidade Exemplo", "uf": "MA", "cep": "65926-000",
            "area_valor": "360", "criado_em": AGORA}
    base.update(campos)
    con = _con(s)
    colunas = ", ".join(base)
    marcas = ", ".join("?" * len(base))
    cur = con.execute(f"INSERT INTO ri_matriculas({colunas}) VALUES({marcas})",
                      tuple(base.values()))
    ident = int(cur.lastrowid)
    con.commit()
    con.close()
    return ident


def _parte(s, matricula_id, nome, *, ativo=1, documento="22105769039"):
    con = _con(s)
    con.execute(
        "INSERT INTO ri_partes(matricula_id, nome, documento_numero, "
        "proprietario, proprietario_ativo) VALUES(?,?,?,?,?)",
        (matricula_id, nome, documento, 1, ativo))
    con.commit()
    con.close()


def _ato(s, matricula_id, *, numero=1, natureza="Compra e Venda",
         tipo="R", teor="Vendeu."):
    con = _con(s)
    con.execute(
        # `hash_ato` e NOT NULL: e a corrente que prova que nenhum ato foi
        # inventado. O teste a preenche como a lavratura faz.
        "INSERT INTO ri_atos(matricula_id, tipo, numero, natureza_titulo, "
        "data_ato, teor, hash_ato, lavrado_em) VALUES(?,?,?,?,?,?,?,?)",
        (matricula_id, tipo, numero, natureza, "2026-01-15", teor,
         f"hash-{matricula_id}-{numero}", AGORA))
    con.commit()
    con.close()


# ------------------------------------------------------- o indicador real


def test_montar_indicador_traz_a_ficha_inteira(s):
    ident = _matricula(s)
    _parte(s, ident, "FULANO DE TAL")
    _ato(s, ident)
    con = _con(s)
    m = ONR.montar_indicador(con, ident, cns=CNS)
    con.close()
    assert m["pronto"], m["impedem"]
    c = m["corpo"]
    assert c["cns"] == CNS
    assert c["numeroRegistro"] == 4014
    assert c["tipoLogradouro"] == API.CODIGO_DO_LOGRADOURO["rua"]
    assert c["logradouro"] == "das Flores"
    assert c["cep"] == "65926000"
    assert c["tipoImovel"] == API.CODIGO_DO_IMOVEL["casa"]
    assert c["localizacao"] == 1
    assert c["proprietarios"] == [
        {"nome": "FULANO DE TAL", "documento": "22105769039"}]
    # O ato sem a data do título e o valor declarado NÃO VAI — o manual do ONR
    # exige os dois (10/10/2026). Até então este teste afirmava o contrário.
    assert "atos" not in c
    assert any("data do título e o valor declarado" in a and "R-1" in a
               for a in m["avisos"])


def test_o_ato_com_data_do_titulo_e_valor_vai_com_os_dois(s):
    """O manual do ONR ([RFI-01]) exige `dataInstrumento` e `valorDeclarado`."""
    ident = _matricula(s)
    _ato(s, ident)
    con = _con(s)
    con.execute("ALTER TABLE ri_atos ADD COLUMN data_instrumento TEXT")
    con.execute("UPDATE ri_atos SET data_instrumento='2026-01-10', "
                "base_calculo_centavos=15000000 WHERE matricula_id=?", (ident,))
    con.commit()
    m = ONR.montar_indicador(con, ident, cns=CNS)
    con.close()
    ato = m["corpo"]["atos"][0]
    assert ato["tipo"] == API.CODIGO_DO_ATO["compra e venda"]
    assert ato["dataInstrumento"] == "2026-01-10"
    assert ato["valorDeclarado"] == 150000.0
    assert ato["dataRegistro"] == "2026-01-15"


def test_o_zero_da_situacao_de_construcao_NAO_se_perde(s):
    """«Construcao Averbada» e o codigo **0**, e o filtro de vazios o tiraria."""
    ident = _matricula(s)
    con = _con(s)
    m = ONR.montar_indicador(con, ident, cns=CNS, situacao_construcao=0)
    con.close()
    assert m["corpo"]["situacaoConstrucao"] == 0


def test_sem_escolha_a_situacao_vai_como_nao_se_aplica_E_AVISA(s):
    """**Esta casa nao guarda isso em coluna nenhuma**, e o ONR o exige."""
    ident = _matricula(s)
    con = _con(s)
    m = ONR.montar_indicador(con, ident, cns=CNS)
    con.close()
    assert m["corpo"]["situacaoConstrucao"] == 2
    assert any("Não se aplica" in a for a in m["avisos"])


def test_o_tipo_do_imovel_que_nao_casa_IMPEDE(s):
    """Nao se casa por semelhanca: «Barracao» nao vira «Galpao»."""
    ident = _matricula(s, tipo_imovel="Barracão de zinco")
    con = _con(s)
    m = ONR.montar_indicador(con, ident, cns=CNS)
    con.close()
    assert not m["pronto"]
    assert any("dez que o ONR aceita" in i for i in m["impedem"])


def test_o_logradouro_sem_tipo_IMPEDE_e_diz_onde_consertar(s):
    ident = _matricula(s, logradouro="Flores")
    con = _con(s)
    m = ONR.montar_indicador(con, ident, cns=CNS)
    con.close()
    assert any("ficha da matrícula" in i for i in m["impedem"])


def test_sem_urbano_ou_rural_IMPEDE(s):
    ident = _matricula(s, rural_urbano="")
    con = _con(s)
    m = ONR.montar_indicador(con, ident, cns=CNS)
    con.close()
    assert any("urbano ou rural" in i for i in m["impedem"])


def test_so_o_dono_de_HOJE_vai(s):
    """`proprietario_ativo`, e nao `proprietario`: mandar as duas publicaria
    como dono quem vendeu."""
    ident = _matricula(s)
    _parte(s, ident, "QUEM VENDEU", ativo=0)
    _parte(s, ident, "QUEM COMPROU", ativo=1)
    con = _con(s)
    m = ONR.montar_indicador(con, ident, cns=CNS)
    con.close()
    nomes = [p["nome"] for p in m["corpo"]["proprietarios"]]
    assert nomes == ["QUEM COMPROU"]


def test_o_ato_que_nao_casa_NAO_some_calado(s):
    """Sumir com ele faria o indice mostrar uma cadeia com buraco."""
    ident = _matricula(s)
    _ato(s, ident, numero=1, natureza="Compra e Venda")
    _ato(s, ident, numero=2, natureza="Coisa que o ONR nao nomeia")
    con = _con(s)
    m = ONR.montar_indicador(con, ident, cns=CNS)
    con.close()
    assert "atos" not in m["corpo"]
    assert any("não casa com nenhum dos códigos" in a for a in m["avisos"])
    assert any("valor declarado" in a and "R-1" in a for a in m["avisos"])
    assert any("R-2" in a for a in m["avisos"])


def test_o_registro_anterior_NAO_se_reparte(s):
    """O ONR o quer em numero, tipo e CNS; a casa guarda texto. Repartir poria
    o numero de um livro no lugar do outro."""
    ident = _matricula(s, registro_anterior="Transcrição 1.234, Livro 3-B")
    con = _con(s)
    m = ONR.montar_indicador(con, ident, cns=CNS)
    con.close()
    assert "registrosAnteriores" not in m["corpo"]
    assert any("não vai" in a for a in m["avisos"])


def test_sem_cns_IMPEDE(s):
    ident = _matricula(s)
    con = _con(s)
    m = ONR.montar_indicador(con, ident, cns="")
    con.close()
    assert any("CNS" in i for i in m["impedem"])


# ------------------------------------------------------ o acervo e a fila


def test_o_acervo_NAO_entra_na_lista_do_que_falta(s):
    """As fichas do E-Oficio vieram de um sistema que ja respondia ao ONR."""
    _matricula(s, numero=1, tipo_ficha="ACERVO")
    nova = _matricula(s, numero=4015, tipo_ficha="ESTRUTURADA")
    con = _con(s)
    faltam = ONR.a_enviar(con)
    con.close()
    assert [m["id"] for m in faltam] == [nova]


def test_o_que_ja_subiu_sai_da_lista(s):
    ident = _matricula(s)
    con = _con(s)
    con.execute(
        "INSERT INTO ri_onr_envios(especie, ambiente, matricula_id, "
        "identificador, corpo_enviado, corpo_hash, situacao, enviado_em) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (ESQ.INDICADOR, ONR.ambiente(), ident, "abc", "{}", "x" * 64,
         ESQ.ENVIADO, AGORA))
    con.commit()
    faltam = ONR.a_enviar(con)
    con.close()
    assert ident not in [m["id"] for m in faltam]


def test_o_RECUSADO_volta_para_a_lista(s):
    """Recusado e trabalho a refazer, e nao trabalho feito."""
    ident = _matricula(s)
    con = _con(s)
    con.execute(
        "INSERT INTO ri_onr_envios(especie, ambiente, matricula_id, "
        "identificador, corpo_enviado, corpo_hash, situacao, enviado_em) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (ESQ.INDICADOR, ONR.ambiente(), ident, "abc", "{}", "x" * 64,
         ESQ.RECUSADO, AGORA))
    con.commit()
    faltam = ONR.a_enviar(con)
    con.close()
    assert ident in [m["id"] for m in faltam]


@pytest.mark.parametrize("palavra,esperado", [
    ("Concluído", ESQ.ACEITO),
    ("processado com sucesso", ESQ.ACEITO),
    ("ERRO na validação", ESQ.RECUSADO),
    ("Recusado", ESQ.RECUSADO),
    ("aguardando", ESQ.ENVIADO),
    ("", ESQ.ENVIADO),
    ("palavra que ninguém conhece", ESQ.ENVIADO),
])
def test_a_fila_so_muda_a_situacao_com_palavra_conhecida(palavra, esperado):
    """**Chutar «aceito» sobre uma palavra desconhecida** faria a casa dar por
    publicado o que o ONR recusou."""
    assert ONR._situacao_da_fila(palavra) == esperado


# --------------------------------------------------------------- as telas


def test_sem_credencial_a_tela_diz_que_e_um_PAR(s, sem_credencial):
    html = s["c"].get("/ri/onr").get_data(as_text=True)
    assert "credencial do ONR ainda não foi informada" in html
    assert "client_id" in html
    assert "client secret" in html


def test_a_tela_fala_so_da_producao(s):
    # 15/10/2026: a nota dos dois ambientes saiu da tela (ordem do oficial);
    # o endereço de testes continua em onr_api, pedido pelo nome.
    html = s["c"].get("/ri/onr").get_data(as_text=True)
    assert "testes-api" not in html
    assert "ambiente <strong>producao</strong>" in html


def test_a_tela_separa_enviado_de_aceito(s):
    ident = _matricula(s)
    con = _con(s)
    con.execute(
        "INSERT INTO ri_onr_envios(especie, ambiente, matricula_id, "
        "identificador, corpo_enviado, corpo_hash, situacao, enviado_em) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (ESQ.INDICADOR, ONR.ambiente(), ident, "abc", "{}", "x" * 64,
         ESQ.ENVIADO, AGORA))
    con.commit()
    con.close()
    html = s["c"].get("/ri/onr").get_data(as_text=True)
    assert "não é" in html and "aceito" in html


def test_sem_credencial_a_ficha_nao_oferece_enviar(s, sem_credencial):
    ident = _matricula(s)
    _parte(s, ident, "FULANO")
    html = s["c"].get(f"/ri/onr/indicador/{ident}").get_data(as_text=True)
    assert f"/ri/onr/indicador/{ident}/enviar" not in html


def test_com_credencial_a_ficha_oferece_enviar(s, com_credencial):
    ident = _matricula(s)
    _parte(s, ident, "FULANO")
    html = s["c"].get(f"/ri/onr/indicador/{ident}").get_data(as_text=True)
    assert f"/ri/onr/indicador/{ident}/enviar" in html


def test_enviar_grava_o_corpo_congelado_com_hash(s, monkeypatch,
                                                 com_credencial):
    ident = _matricula(s)
    _parte(s, ident, "FULANO DE TAL")
    monkeypatch.setattr(API, "enviar_indicador", lambda c, **k: {
        "hash": "abc-123", "corpo": c, "bruto": {"data": {"hash": "abc-123"}}})
    html = s["c"].get("/ri/onr").get_data(as_text=True)
    s["c"].post(f"/ri/onr/indicador/{ident}/enviar",
                data={"csrf_token": _token(html)}, follow_redirects=True)
    con = _con(s)
    linha = con.execute("SELECT * FROM ri_onr_envios").fetchone()
    con.close()
    assert linha["identificador"] == "abc-123"
    assert linha["situacao"] == ESQ.ENVIADO
    assert len(linha["corpo_hash"]) == 64
    assert json.loads(linha["corpo_enviado"])["numeroRegistro"] == 4014


def test_a_recusa_do_onr_vira_aviso_e_nao_500(s, monkeypatch, com_credencial):
    ident = _matricula(s)
    _parte(s, ident, "FULANO")

    def recusa(*a, **k):
        raise API.OnrRecusou("O ONR recusou os dados: cep: obrigatorio")
    monkeypatch.setattr(API, "enviar_indicador", recusa)
    html = s["c"].get("/ri/onr").get_data(as_text=True)
    r = s["c"].post(f"/ri/onr/indicador/{ident}/enviar",
                    data={"csrf_token": _token(html)}, follow_redirects=True)
    assert r.status_code == 200
    assert "cep" in r.get_data(as_text=True)


def test_conferir_a_fila_muda_a_situacao(s, monkeypatch, com_credencial):
    ident = _matricula(s)
    con = _con(s)
    con.execute(
        "INSERT INTO ri_onr_envios(especie, ambiente, matricula_id, "
        "identificador, corpo_enviado, corpo_hash, situacao, enviado_em) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (ESQ.INDICADOR, ONR.ambiente(), ident, "abc", "{}", "x" * 64,
         ESQ.ENVIADO, AGORA))
    con.commit()
    con.close()
    monkeypatch.setattr(API, "fila", lambda **k: [
        {"hash": "fila-1", "identificador": "abc", "situacao": "Concluído"}])
    html = s["c"].get("/ri/onr").get_data(as_text=True)
    s["c"].post("/ri/onr/fila", data={"csrf_token": _token(html)},
                follow_redirects=True)
    con = _con(s)
    linha = con.execute("SELECT * FROM ri_onr_envios").fetchone()
    con.close()
    assert linha["situacao"] == ESQ.ACEITO
    assert linha["fila_situacao"] == "Concluído"


def test_enviar_NAO_e_do_balcao(cg_casa, monkeypatch):
    monkeypatch.setattr(API, "tem_credencial", lambda *a, **k: True)
    s = _sessao(cg_casa, papel="USER")
    ident = _matricula(s)
    assert s["c"].get("/ri/onr").status_code == 200
    assert s["c"].get(f"/ri/onr/indicador/{ident}").status_code == 200
    html = s["c"].get("/ri/onr").get_data(as_text=True)
    r = s["c"].post(f"/ri/onr/indicador/{ident}/enviar",
                    data={"csrf_token": _token(html)})
    assert r.status_code == 403


# ------------------------------- as portas do extrator de endereço (16/09/2026)
#
# **O QUE SE MEDE AQUI, E POR QUE NÃO É EM `test_onr_endereco_telas.py`.** As
# telas do extrator têm os testes deles lá — a fila, a conferência, o botão da
# ficha do imóvel. O que se mede aqui é outra coisa: as duas remissões que
# nasceram nas telas **deste** módulo, e que um dia alguém reescreve sem saber
# por que estavam ali. É a lição do relato #28 outra vez — tela que perde uma
# frase perde a informação junto, e a rota continua entregando o que ninguém lê.
#
# **E POR QUE ELAS NÃO TRAZEM NÚMERO.** O painel diz *onde* se resolve o
# endereço; o número da fila (**1.443**) é da outra tela, onde ele é o número
# daquela fila. Trazer 1.443 para o lado de **434** — que é o que esta lista
# conta — faria quem lê concluir que esta lista é aquela, e as duas não são: a
# fila do endereço soma o acervo, que esta lista deixa de fora de propósito.

TEOR_COM_IMOVEL = (
    " MATRÍCULA: 4014\n\r\n LIVRO 2 FLS. 10\n\r\n DATADO 10 DE JANEIRO DE 2026"
    "\n\r\n \n\r\n IMÓVEL:- "
    "- Lote de terreno urbano situado na Rua Dep. La Rocque, nº 123, "
    "bairro Centro, nesta cidade de Cidade Exemplo, Estado do Maranhão."
)


def test_o_painel_do_ONR_manda_conferir_os_enderecos(s):
    """**A PORTA FICA ONDE O PROBLEMA APARECE.**

    Quem abre esta lista procurando o que falta para publicar descobre, na
    linha da matrícula, que o que falta é o endereço — e a pergunta seguinte
    («de onde eu tiro isso?») precisa ter resposta na mesma tela. A remissão ao
    menu existia desde a manhã; o painel é que é a tela onde o problema é lido.
    """
    html = s["c"].get("/ri/onr").get_data(as_text=True)
    i = html.index("Muita matrícula desta lista não sobe por falta de endereço")
    # **O MESMO PARÁGRAFO, e não «em algum lugar da página»**: solto na página,
    # o endereço continuaria ali e a frase poderia sair — o teste passaria
    # guardando metade da coisa. É a lição do comentário de CSS que viajou para
    # o navegador, aplicada à leitura: olha-se o trecho, e não o arquivo.
    assert "/ri/onr/enderecos" in html[i:i + 900].split("</p>")[0]


def test_a_ficha_do_indicador_leva_ao_extrator_quando_falta_o_endereco(s):
    """A segunda porta: o botão onde o impedimento é lido.

    A ficha do indicador já dizia que o logradouro impede a publicação. O que
    faltava era o caminho — e o endereço está escrito dentro do teor, que é o
    texto que a digitalização trouxe.
    """
    ident = _matricula(s, logradouro=None, teor=TEOR_COM_IMOVEL)
    html = s["c"].get(f"/ri/onr/indicador/{ident}").get_data(as_text=True)
    assert f"/ri/onr/endereco/da-matricula/{ident}" in html
    assert "o que o teor diz" in html
    # **É POST, E NÃO UM LINK** — a rota cria proposta, e nesta casa um GET não
    # abre transação de escrita. O formulário é lido de perto, e não só a
    # palavra «post» na página: a tela tem outros formulários adiante.
    trecho = html[max(0, html.index(
        f"/ri/onr/endereco/da-matricula/{ident}") - 400):]
    assert 'method="post"' in trecho.split("</form>")[0]


def test_a_ficha_do_indicador_nao_oferece_o_botao_onde_ele_nao_faz_nada(s):
    """**Botão que não pode fazer nada não se oferece.**

    Sem teor não há o que ler; com o logradouro preenchido a proposta não tem o
    que acrescentar (o `gerar` não propõe sobre endereço já digitado, e é a
    mesma régua). Quem clicasse e recebesse recusa aprenderia a não clicar.
    """
    com_endereco = _matricula(s, teor=TEOR_COM_IMOVEL)      # a base já tem rua
    sem_teor = _matricula(s, logradouro=None, teor=None)
    for ident in (com_endereco, sem_teor):
        html = s["c"].get(f"/ri/onr/indicador/{ident}").get_data(as_text=True)
        assert f"/ri/onr/endereco/da-matricula/{ident}" not in html
