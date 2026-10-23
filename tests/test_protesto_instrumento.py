"""O INSTRUMENTO DE PROTESTO — o papel do art. 20, e os dez itens do art. 22.

Nasceu da pergunta do oficial em 01/09/2026 — *«onde emitir o instrumento
eletronico do protesto?»* —, cuja resposta era **em lugar nenhum**.

O QUE ESTES TESTES GUARDAM
      - **sem protesto lavrado não há instrumento de protesto**: o papel
        afirma que o ato existe, e vai assinado ao credor;
      - **o § único do art. 22 é uma dispensa CONDICIONAL**, e a condição se
        pergunta ao banco: sem cópia arquivada o papel diz que a dispensa não
        se aplica, em vez de afirmar um arquivo que ninguém conferiu;
      - **o item II fica declarado em falta** quando o apresentante não tem
        endereço — o arquivo da CRA não o traz; desde o LD08 ele vem do
        título (o balcão o pede) ou do cadastro dos apresentantes, pelo
        código, e então vai ao instrumento e o item se satisfaz;
      - **o teor congela**, e aqui por uma razão a mais que no termo: ele vai
        ser assinado, e assinatura é sobre bytes determinados;
      - **emitir põe o papel na fila de assinatura da casa**;
      - **segunda via é outra linha**, e não a primeira reescrita.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import protesto_instrumento as PI
from as_schema import init_as_schema
from nucleo_schema import init_nucleo_schema
from pt_schema import init_pt_schema

AGORA = "2026-09-01T17:00:00"
SERVENTIA = "Ofício Único de Cidade Exemplo/MA"


def banco() -> sqlite3.Connection:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    # `pt_atos.livro_id` aponta para `nu_livros`, e o PostgreSQL nativo
    # cobra a chave estrangeira ja na criacao: o nucleo vem antes.
    init_nucleo_schema(con)
    init_pt_schema(con)
    init_as_schema(con)
    # A `attachments` e da casa inteira; aqui basta a forma que o modulo le.
    con.execute("""CREATE TABLE IF NOT EXISTS attachments (
        id INTEGER PRIMARY KEY AUTOINCREMENT, entity_type TEXT, entity_id INTEGER,
        original_name TEXT, stored_path TEXT, sha256 TEXT, size_bytes INTEGER,
        description TEXT, uploaded_at TEXT)""")
    return con


def titulo(con, **campos) -> int:
    dados = {"especie": "DMI", "numero_titulo": "00123", "nosso_numero": "9620",
             "valor_centavos": 69979, "protocolo": "2606090001",
             "apresentante_codigo": "237", "apresentante_nome": "BANCO X",
             "praca_protesto": "CIDADE EXEMPLO", "motivo_protesto": "1",
             "tipo_protesto": "C", "situacao": "PROTESTADO",
             "origem": "CRA", "criado_em": AGORA}
    dados.update(campos)
    cols = ", ".join(dados)
    cur = con.execute(f"INSERT INTO pt_titulos({cols}) "
                      f"VALUES ({', '.join('?' * len(dados))})",
                      tuple(dados.values()))
    tid = int(cur.lastrowid)
    con.execute("""INSERT INTO pt_devedores(titulo_id, nome, documento_tipo,
                       documento_numero, endereco, cidade, uf, nome_norm)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (tid, "MARIA DA SILVA", "F", "02832147593", "RUA A, 10",
                 "CIDADE EXEMPLO", "MA", "maria da silva"))
    return tid


def ato(con, titulo_id, tipo, *, data="2026-06-13", detalhe="{}", cancelado=0):
    con.execute("""INSERT INTO pt_atos(titulo_id, tipo, data_ato, detalhe_json,
                       cancelado, criado_em)
                   VALUES (?,?,?,?,?,?)""",
                (titulo_id, tipo, data, detalhe, cancelado, AGORA))


def protestado(con, **campos) -> int:
    tid = titulo(con, **campos)
    ato(con, tid, "APONTAMENTO", data="2026-06-09")
    ato(con, tid, "INTIMACAO", data="2026-06-10",
        detalhe='{"modo": "EDITAL", "motivo_nao_entrega": "Ausente"}')
    ato(con, tid, "PROTESTO", data="2026-06-13")
    return tid


# ------------------------------------------------- a recusa que protege


def test_sem_protesto_lavrado_nao_ha_instrumento():
    """O papel afirma que o ato existe, e vai assinado ao credor."""
    con = banco()
    tid = titulo(con)
    ato(con, tid, "APONTAMENTO")
    with pytest.raises(PI.InstrumentoError) as e:
        PI.emitir(con, tid, serventia=SERVENTIA, agora=AGORA)
    assert "não tem protesto lavrado" in str(e.value)


def test_protesto_cancelado_nao_serve_de_base():
    con = banco()
    tid = titulo(con)
    ato(con, tid, "PROTESTO", cancelado=1)
    with pytest.raises(PI.InstrumentoError):
        PI.emitir(con, tid, serventia=SERVENTIA, agora=AGORA)


def test_titulo_que_nao_existe_recusa_dizendo_qual():
    con = banco()
    with pytest.raises(PI.InstrumentoError) as e:
        PI.dados(con, 9999)
    assert "9999" in str(e.value)


# ------------------------------------------------- os dez itens


def test_a_conferencia_percorre_os_dez_itens_do_art_22():
    con = banco()
    tid = protestado(con)
    c = PI.conferir(con, tid)
    assert len(c["itens"]) == 10
    assert [i["inciso"] for i in c["itens"]] == [
        "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]
    assert c["pode_emitir"] is True


def test_o_item_II_fica_em_falta_com_o_motivo_e_onde_cadastrar():
    """SEM ENDEREÇO DO APRESENTANTE, O ITEM II FALTA, e o motivo diz onde se
    conserta. Medido em 01/09/2026: o cabeçalho da remessa da CRA traz código
    (3) e nome (40) e nenhuma posição de endereço. Desde o LD08 o endereço tem
    fonte — o título ou o cadastro dos apresentantes —, e o motivo deixou de
    ser «não está em fonte nenhuma»: o título 237 deste teste não está no
    cadastro. Calar seria assinar papel omitindo item da lei."""
    con = banco()
    tid = protestado(con)
    c = PI.conferir(con, tid)
    item = next(i for i in c["itens"] if i["inciso"] == "II")
    assert item["tem"] is False
    assert item["falta"] == "endereço do apresentante"
    assert "cadastro dos apresentantes" in item["porque"]
    assert "art. 22, II" in PI.por_que_nao_esta_completo(c)
    teor = PI.emitir(con, tid, serventia=SERVENTIA, agora=AGORA)["teor"]
    assert "Apresentante: BANCO X." in teor and "endereço Rua" not in teor


def test_com_o_endereco_no_cadastro_o_item_II_se_satisfaz_e_vai_ao_papel():
    """Lei 9.492/1997, art. 22, II; CN-MA art. 914, III (LD08). O banco que
    manda pela CRA é um só para muitos títulos: o endereço dele se cadastra uma
    vez, pelo código, e chega ao instrumento — e ao corpo que se assina."""
    import protesto_cenprot_xml as X
    con = banco()
    tid = protestado(con)
    X.gravar_apresentante(con, codigo="237", nome="BANCO X DO CADASTRO",
                          documento="00000010000127", tipo_apresentante="0",
                          endereco="Avenida Exemplo, 500, Cidade Exemplo/MA",
                          agora=AGORA)
    c = PI.conferir(con, tid)
    item = next(i for i in c["itens"] if i["inciso"] == "II")
    assert item["tem"] is True
    assert not any(i["inciso"] == "II" for i in c["faltando"])
    emitido = PI.emitir(con, tid, serventia=SERVENTIA, agora=AGORA)
    # o NOME é o do título (o que a CRA mandou); o endereço, o do cadastro
    assert ("Apresentante: BANCO X, endereço Avenida Exemplo, 500, Cidade "
            "Exemplo/MA.") in emitido["teor"]
    corpo = PI.instrumento(con, emitido["id"])["corpo"]
    assert corpo["apresentante"]["endereco"] == "Avenida Exemplo, 500, Cidade Exemplo/MA"


def test_o_titulo_do_balcao_traz_o_proprio_endereco_do_apresentante():
    """O título do balcão não tem código da CRA: o endereço é o que quem o
    apresentou informou (CN-MA art. 884, I), gravado no título."""
    con = banco()
    tid = protestado(con, apresentante_codigo=None, origem="MANUAL",
                     apresentante_nome="CARLA EXEMPLO",
                     apresentante_endereco="Rua das Flores, 10, Cidade Exemplo/MA")
    assert next(i for i in PI.conferir(con, tid)["itens"]
                if i["inciso"] == "II")["tem"] is True
    teor = PI.emitir(con, tid, serventia=SERVENTIA, agora=AGORA)["teor"]
    assert ("Apresentante: CARLA EXEMPLO, endereço Rua das Flores, 10, Cidade "
            "Exemplo/MA.") in teor


def test_os_itens_V_e_VI_dizem_que_so_cabem_na_letra_de_cambio():
    """Item declarado como «não se aplica» é diferente de item esquecido."""
    con = banco()
    tid = protestado(con)
    c = PI.conferir(con, tid)
    for inciso in ("V", "VI"):
        item = next(i for i in c["itens"] if i["inciso"] == inciso)
        assert item["tem"] is None
        assert "letra de câmbio" in item["nota"]


def test_sem_imagem_o_item_III_aparece_em_falta():
    con = banco()
    tid = protestado(con)
    c = PI.conferir(con, tid)
    assert c["copias_arquivadas"] == 0
    assert any(i["inciso"] == "III" for i in c["faltando"])


def test_com_imagem_arquivada_o_item_III_se_satisfaz():
    con = banco()
    tid = protestado(con)
    con.execute("""INSERT INTO attachments(entity_type, entity_id, original_name)
                   VALUES ('pt_titulos', ?, 'titulo.pdf')""", (tid,))
    c = PI.conferir(con, tid)
    assert c["copias_arquivadas"] == 1
    assert not any(i["inciso"] == "III" for i in c["faltando"])


# ------------------------------------------------- o § único


def test_com_copia_arquivada_o_teor_escreve_a_mencao_do_paragrafo_unico():
    """São DUAS obrigações, e não uma: conservar a cópia, e dizer que conserva."""
    teor = PI.montar_teor(serventia=SERVENTIA, praca="CIDADE EXEMPLO",
                          motivo="FALTA DE PAGAMENTO", copia_arquivada=True,
                          intimacao=None)
    assert "parágrafo único do art. 22" in teor
    assert "por conservar esta serventia" in teor


def test_sem_copia_o_teor_diz_que_a_dispensa_NAO_se_aplica():
    """Escrever a menção sem ter a cópia é o «carimbo que mente» num papel que
    vai ao credor."""
    teor = PI.montar_teor(serventia=SERVENTIA, praca="CIDADE EXEMPLO",
                          motivo="FALTA DE PAGAMENTO", copia_arquivada=False,
                          intimacao=None)
    assert "não se aplica a dispensa" in teor
    assert "por conservar esta serventia" not in teor


# ------------------------------------------------- texto corrido, sem claros
#
# «o corpo de todos os atos do cartorio eh texto corrido, sem espacos» — o
# oficial, 07/09/2026. Até essa data `INSTRUMENTO_DE_PROTESTO` juntava as
# três partes com `"\n\n"` — linha em branco de propósito —, e isso ia
# inteiro para o papel que o tabelião assina e entrega ao apresentante. É o
# mesmo `claro` que o art. 795, § 2º do Código de Normas proíbe.

def test_o_instrumento_nao_tem_quebra_de_linha():
    for intimacao in (None, {"modo": "EDITAL", "data": "2026-08-20"},
                      {"modo": "PESSOAL", "data": "2026-08-20"}):
        teor = PI.montar_teor(serventia=SERVENTIA, praca="CIDADE EXEMPLO",
                              motivo="FALTA DE PAGAMENTO",
                              copia_arquivada=True, intimacao=intimacao)
        assert "\n" not in teor, intimacao


def test_o_instrumento_nao_tem_espaco_duplo_nem_antes_de_pontuacao():
    teor = PI.montar_teor(serventia=SERVENTIA, praca="CIDADE EXEMPLO",
                          motivo="FALTA DE PAGAMENTO", copia_arquivada=False,
                          intimacao={"modo": "EDITAL", "data": "2026-08-20",
                                     "motivo_nao_entrega": "Ausente"})
    assert "  " not in teor
    assert not re.search(r"\s[,.;:]", teor)


def test_a_copia_arquivada_nao_tem_padrao():
    """Padrão `True` faria o papel afirmar um arquivo que ninguém conferiu."""
    with pytest.raises(TypeError):
        PI.montar_teor(serventia=SERVENTIA, praca="X", motivo="Y",
                       intimacao=None)


# ------------------------------------------------- a certidão do inciso IV


def test_a_certidao_da_intimacao_diz_o_meio_edital():
    teor = PI.montar_teor(serventia=SERVENTIA, praca="X", motivo="Y",
                          copia_arquivada=False,
                          intimacao={"data": "2026-06-10", "modo": "EDITAL",
                                     "motivo_nao_entrega": "Ausente"})
    assert "por EDITAL, publicado em 10/06/2026" in teor
    assert "pelo motivo Ausente." in teor


def test_a_certidao_da_intimacao_em_maos_nao_afirma_edital():
    """Escrever «por edital» numa intimação em mãos afirmaria uma publicação
    que não houve — a mesma regra do termo do livro."""
    teor = PI.montar_teor(serventia=SERVENTIA, praca="X", motivo="Y",
                          copia_arquivada=False,
                          intimacao={"data": "2026-06-10", "modo": "PESSOAL"})
    assert "EDITAL" not in teor
    assert "entregue no endereço do devedor em 10/06/2026" in teor


def test_sem_intimacao_o_teor_diz_que_nao_ha_ato():
    teor = PI.montar_teor(serventia=SERVENTIA, praca="X", motivo="Y",
                          copia_arquivada=False, intimacao=None)
    assert "não consta ato de intimação" in teor


def test_modelo_com_campo_desconhecido_recusa_na_hora():
    with pytest.raises(PI.InstrumentoError) as e:
        PI.montar_teor(modelo="{serventia} e {inventado}", serventia=SERVENTIA,
                       praca="X", motivo="Y", copia_arquivada=False,
                       intimacao=None)
    assert "Modelos da casa" in str(e.value)


# ------------------------------------------------- emitir


def test_emitir_congela_o_teor_e_numera_por_exercicio():
    con = banco()
    tid = protestado(con)
    r = PI.emitir(con, tid, serventia=SERVENTIA, agora=AGORA)
    assert r["numero"] == 1 and r["ano"] == 2026
    assert r["data_do_protesto"] == "2026-06-13"
    assert r["data_por_extenso"] == "13 de junho de 2026"
    assert len(r["hash_instrumento"]) == 64
    guardado = PI.instrumento(con, r["id"])
    assert guardado["teor"] == r["teor"]
    assert guardado["corpo"]["valor"] == "699,79"
    assert guardado["corpo"]["devedores"][0]["nome"] == "MARIA DA SILVA"


def test_emitir_poe_o_papel_na_fila_de_assinatura_da_casa():
    """A fila é uma só, e o instrumento é mais um papel nela."""
    con = banco()
    tid = protestado(con)
    r = PI.emitir(con, tid, serventia=SERVENTIA, agora=AGORA)
    linha = con.execute(
        "SELECT * FROM as_documentos WHERE entidade='pt_instrumentos'").fetchone()
    assert linha is not None
    assert linha["entidade_id"] == r["id"]
    assert linha["sha256_documento"] == r["hash_instrumento"]
    assert linha["assinado_em"] is None
    assert "Instrumento de protesto n.º 1/2026" == linha["titulo"]


def test_segunda_via_e_outra_linha_e_nao_a_primeira_reescrita():
    """Reaproveitar faria a segunda via sobrescrever o teor que a primeira
    levou assinado — e a firma da primeira passaria a não conferir."""
    con = banco()
    tid = protestado(con)
    a = PI.emitir(con, tid, serventia=SERVENTIA, agora=AGORA)
    b = PI.emitir(con, tid, serventia=SERVENTIA, agora=AGORA)
    assert b["numero"] == a["numero"] + 1
    assert len(PI.do_titulo(con, tid)) == 2
    assert con.execute("SELECT COUNT(*) c FROM as_documentos").fetchone()["c"] == 2


def test_o_motivo_sai_do_catalogo_da_CRA_e_nao_do_codigo_cru():
    con = banco()
    tid = protestado(con)
    r = PI.emitir(con, tid, serventia=SERVENTIA, agora=AGORA)
    assert "FALTA DE PAGAMENTO" in r["teor"]
    assert "por motivo de 1" not in r["teor"]


def test_ato_sem_data_recusa_em_vez_de_inventar_ano():
    """A DATA NULA O BANCO JA IMPEDE — `pt_atos.data_ato` e NOT NULL, e este
    teste tentou inseri-la antes de descobrir isso. **Onde a regra pode morar
    no banco, ela mora no banco.**

    O que sobra alcancavel e a data VAZIA, que passa pelo NOT NULL e nao diz
    ano nenhum: dela sairia um instrumento numerado no exercicio 0. Os dois
    lados ficam guardados aqui — a trava do esquema e a do modulo."""
    con = banco()
    tid = titulo(con)
    with pytest.raises(sqlite3.IntegrityError):
        ato(con, tid, "PROTESTO", data=None)

    outro = titulo(con, numero_titulo="00999", protocolo="2606090009")
    ato(con, outro, "PROTESTO", data="")
    with pytest.raises(PI.InstrumentoError) as e:
        PI.emitir(con, outro, serventia=SERVENTIA, agora="")
    assert "sem data" in str(e.value)


# ------------------------------------------------- as listas


def test_a_lista_do_que_falta_entregar_conta_e_nao_julga():
    """A mesma regra do roteiro das Centrais: quem diz se o prazo do art. 20
    correu é quem tem o calendário do balcão, e não uma lista."""
    con = banco()
    a = protestado(con)
    protestado(con, numero_titulo="00124", protocolo="2606090002")
    assert len(PI.a_entregar(con)) == 2
    PI.emitir(con, a, serventia=SERVENTIA, agora=AGORA)
    restam = PI.a_entregar(con)
    assert len(restam) == 1
    assert restam[0]["titulo_id"] != a
    publicos = [n for n in dir(PI) if not n.startswith("_")]
    for palavra in ("atrasado", "vencido", "alerta"):
        assert not any(palavra in n.lower() for n in publicos)


def test_as_contagens_separam_o_que_tem_do_que_falta():
    con = banco()
    a = protestado(con)
    protestado(con, numero_titulo="00124", protocolo="2606090002")
    PI.emitir(con, a, serventia=SERVENTIA, agora=AGORA)
    assert PI.contagens(con) == {"protestos": 2, "com_instrumento": 1,
                                 "sem_instrumento": 1}
