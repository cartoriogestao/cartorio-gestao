"""
Testes do Protesto — o cadastro do titulo e o apontamento, ligados ao nucleo.

O QUE ELES CONFEREM
    A regra, e nao "a funcao devolveu alguma coisa":

      - titulo que o contrato da CRA recusa nao entra no banco;
      - titulo de CRA/CENPROT sem chave de origem nao entra — sem ela a
        carga nao e repetivel;
      - reapresentar a mesma (origem, origem_chave) devolve o id que ja
        existe, em vez de duplicar o titulo;
      - o apontamento ocupa lugar no Livro de Apontamento (52 por face, sem
        verso) e muda a situacao do titulo para APONTADO;
      - um titulo nao se aponta duas vezes;
      - a intimacao registra o modo e NAO calcula prazo nenhum — o acervo
        nao tem essa data, e a regra de contagem e do oficial;
      - titulo nao apontado nao se intima; edital sem codigo e recusado;
        intimacao pessoal sem exito seguida de edital sao duas linhas;
      - o protesto ocupa lugar no Livro de Registro de Protestos (1 por
        face, com verso) e exige titulo ja intimado;
      - a desistencia so cabe ANTES do protesto lavrado, e nao ocupa livro;
      - o pagamento cabe ANTES do protesto (apontado ou intimado), ocupa o
        Livro de Registro de Pagamentos (120 por folha, sem verso) e recusa
        titulo em situacao final; o PROTESTADO tambem se recusa desde
        21/10/2026 (LH13: «protesto nao pode ser pago na serventia depois de
        lavrar», o oficial);
      - o cancelamento so cabe titulo PROTESTADO — e o PAGO com protesto em
        pe, legado da regra de 24/08/2026, pela anuencia ou ordem judicial —,
        exige hipotese do catalogo (nao "Erro Material" generico) e
        fundamento proprio do caso, com pelo menos dez letras.
"""
from __future__ import annotations

import json
import sqlite3
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import banco_pg                                  # noqa: E402
import protesto as PT                            # noqa: E402
from bd_nativo import banco as nativo            # noqa: E402
from nucleo_schema import init_nucleo_schema     # noqa: E402
from pt_schema import init_pt_schema             # noqa: E402

AGORA = "2026-08-24T09:00:00"
EXTENSO = "vinte e quatro dias do mês de agosto do ano de dois mil e vinte e seis"
SV = {
    "unit_name": "SERVENTIA EXTRAJUDICIAL DO OFÍCIO ÚNICO DE CIDADE EXEMPLO",
    "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
    "serventia_titulo": "Tabelião e Oficial de Registro",
    "ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA",
}


def banco() -> sqlite3.Connection:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    init_nucleo_schema(con)
    init_pt_schema(con)
    return con


def titulo_bom() -> dict:
    """O mesmo titulo de `test_protesto_cra.titulo_bom()` — real, mascarado."""
    return {
        "especie": "DMI",
        "numero_titulo": "84713/1",
        "data_emissao": "2022-07-21",
        "data_vencimento": "2022-09-05",
        "valor": "1482.78",
        "saldo": "1482.78",
        "praca_protesto": "CIDADE EXEMPLO",
        "tipo_moeda": "1",
        "tipo_protesto": "C",
        "motivo_protesto": "1",
        "cedente": {"nome": "«mascarado»", "documento": "00000000000000",
                   "cidade": "Cidade Exemplo", "uf": "MA"},
        "devedores": [{"nome": "«mascarado»", "CNPJ": "00000000000000",
                      "enderecos": [{"endereco": "Rua X", "bairro": "Centro",
                                    "cidade": "Cidade Exemplo", "uf": "MA"}]}],
    }


# --------------------------------------------------------------- o cadastro


def test_cadastra_titulo_em_ordem():
    con = banco()
    titulo_id = PT.cadastrar_titulo(con, titulo_bom(), origem="MANUAL", agora=AGORA)
    tit = PT.titulo(con, titulo_id)
    assert tit["especie"] == "DMI"
    assert tit["numero_titulo"] == "84713/1"
    assert tit["valor_centavos"] == 148278
    assert tit["saldo_centavos"] == 148278
    assert tit["situacao"] == "RECEBIDO"
    devedores = PT.devedores_do(con, titulo_id)
    assert len(devedores) == 1
    assert devedores[0]["documento_tipo"] == "CNPJ"
    assert devedores[0]["cidade"] == "Cidade Exemplo"


def test_titulo_que_o_contrato_da_cra_recusa_nao_entra():
    con = banco()
    ruim = titulo_bom()
    ruim["devedores"] = []
    with pytest.raises(PT.ProtestoError) as erro:
        PT.cadastrar_titulo(con, ruim, origem="MANUAL", agora=AGORA)
    assert "ao menos um devedor" in str(erro.value)
    assert con.execute("SELECT COUNT(*) n FROM pt_titulos").fetchone()["n"] == 0


def test_titulo_de_cra_sem_chave_de_origem_e_recusado():
    con = banco()
    with pytest.raises(PT.ProtestoError) as erro:
        PT.cadastrar_titulo(con, titulo_bom(), origem="CRA", agora=AGORA)
    assert "chave de origem" in str(erro.value)


def test_origem_desconhecida_e_recusada():
    con = banco()
    with pytest.raises(PT.ProtestoError):
        PT.cadastrar_titulo(con, titulo_bom(), origem="SERASA", agora=AGORA)


def test_carga_e_repetivel_por_construcao():
    # A mesma chave de origem duas vezes devolve o MESMO id, nao duplica.
    con = banco()
    id1 = PT.cadastrar_titulo(con, titulo_bom(), origem="CRA",
                              origem_chave="REMESSA-1:84713/1", agora=AGORA)
    id2 = PT.cadastrar_titulo(con, titulo_bom(), origem="CRA",
                              origem_chave="REMESSA-1:84713/1", agora=AGORA)
    assert id1 == id2
    assert con.execute("SELECT COUNT(*) n FROM pt_titulos").fetchone()["n"] == 1


# ----------------------------------------------------------- o apontamento


def test_lanca_apontamento_e_ocupa_o_livro():
    con = banco()
    titulo_id = PT.cadastrar_titulo(con, titulo_bom(), origem="MANUAL", agora=AGORA)
    lugar = PT.lancar_apontamento(con, titulo_id, sv=SV, agora=AGORA,
                                  data_extenso=EXTENSO, usuario="TESTE")
    assert lugar["numero_ordem"] == 1
    assert lugar["folha"] == 1
    assert lugar["verso"] is False

    ato = PT.atos_do(con, titulo_id)[0]
    assert ato["tipo"] == "APONTAMENTO"
    assert ato["folha"] == 1
    assert ato["numero_ordem"] == 1

    tit = PT.titulo(con, titulo_id)
    assert tit["situacao"] == "APONTADO"


def test_cinquenta_e_dois_apontamentos_cabem_numa_face_so():
    # PT_APONTAMENTO: 52 por face, sem verso — medido no acervo em 21/08/2026.
    con = banco()
    for i in range(52):
        titulo_id = PT.cadastrar_titulo(
            con, titulo_bom(), origem="CRA", origem_chave=f"LOTE:{i}", agora=AGORA)
        lugar = PT.lancar_apontamento(con, titulo_id, sv=SV, agora=AGORA,
                                      data_extenso=EXTENSO)
        assert lugar["folha"] == 1
    # O quinquagesimo terceiro vai para a folha seguinte.
    titulo_id = PT.cadastrar_titulo(
        con, titulo_bom(), origem="CRA", origem_chave="LOTE:52", agora=AGORA)
    lugar = PT.lancar_apontamento(con, titulo_id, sv=SV, agora=AGORA,
                                  data_extenso=EXTENSO)
    assert lugar["folha"] == 2
    assert lugar["numero_ordem"] == 53


def test_nao_aponta_titulo_inexistente():
    con = banco()
    with pytest.raises(PT.ProtestoError, match="não encontrado"):
        PT.lancar_apontamento(con, 999, sv=SV, agora=AGORA, data_extenso=EXTENSO)


def test_nao_aponta_duas_vezes():
    con = banco()
    titulo_id = PT.cadastrar_titulo(con, titulo_bom(), origem="MANUAL", agora=AGORA)
    PT.lancar_apontamento(con, titulo_id, sv=SV, agora=AGORA, data_extenso=EXTENSO)
    with pytest.raises(PT.ProtestoError, match="não se aponta de novo"):
        PT.lancar_apontamento(con, titulo_id, sv=SV, agora=AGORA, data_extenso=EXTENSO)


# ------------------------------------------------------------ a intimacao


def _titulo_apontado(con) -> int:
    titulo_id = PT.cadastrar_titulo(con, titulo_bom(), origem="MANUAL", agora=AGORA)
    PT.lancar_apontamento(con, titulo_id, sv=SV, agora=AGORA, data_extenso=EXTENSO)
    return titulo_id


def test_intimacao_pessoal_registra_e_nao_calcula_prazo():
    con = banco()
    titulo_id = _titulo_apontado(con)
    resultado = PT.lancar_intimacao(con, titulo_id, modo="PESSOAL", agora=AGORA,
                                    comprovante="AR 123, assinado por João")
    assert resultado["modo"] == "PESSOAL"

    ato = PT.atos_do(con, titulo_id)[-1]
    assert ato["tipo"] == "INTIMACAO"
    # A igualdade exata prova que nenhum campo de prazo ou vencimento entrou.
    detalhe = json.loads(ato["detalhe_json"])
    assert detalhe == {"modo": "PESSOAL", "digital": False,
                       "comprovante": "AR 123, assinado por João"}

    tit = PT.titulo(con, titulo_id)
    assert tit["situacao"] == "INTIMADO"


def test_intimacao_por_edital_exige_codigo():
    con = banco()
    titulo_id = _titulo_apontado(con)
    with pytest.raises(PT.ProtestoError, match="código do edital"):
        PT.lancar_intimacao(con, titulo_id, modo="EDITAL", agora=AGORA)


def test_intimacao_por_edital_com_codigo():
    con = banco()
    titulo_id = _titulo_apontado(con)
    resultado = PT.lancar_intimacao(con, titulo_id, modo="EDITAL", agora=AGORA,
                                    codigo_edital="ED-2026-014")
    assert resultado["codigo_edital"] == "ED-2026-014"


def test_modo_de_intimacao_desconhecido_e_recusado():
    con = banco()
    titulo_id = _titulo_apontado(con)
    with pytest.raises(PT.ProtestoError, match="Modo de intimação desconhecido"):
        PT.lancar_intimacao(con, titulo_id, modo="TELEFONE", agora=AGORA)


def test_nao_intima_titulo_que_ainda_nao_foi_apontado():
    con = banco()
    titulo_id = PT.cadastrar_titulo(con, titulo_bom(), origem="MANUAL", agora=AGORA)
    with pytest.raises(PT.ProtestoError, match="só se intima título já apontado"):
        PT.lancar_intimacao(con, titulo_id, modo="PESSOAL", agora=AGORA)


def test_intimacao_pessoal_sem_exito_seguida_de_edital_sao_duas_linhas():
    con = banco()
    titulo_id = _titulo_apontado(con)
    PT.lancar_intimacao(con, titulo_id, modo="PESSOAL", agora=AGORA,
                        comprovante="não encontrado no endereço")
    PT.lancar_intimacao(con, titulo_id, modo="EDITAL", agora=AGORA,
                        codigo_edital="ED-2026-014")
    intimacoes = [a for a in PT.atos_do(con, titulo_id) if a["tipo"] == "INTIMACAO"]
    assert len(intimacoes) == 2
    assert PT.titulo(con, titulo_id)["situacao"] == "INTIMADO"


# --------------------------------------------------- o protesto e a desistencia


def _titulo_intimado(con) -> int:
    titulo_id = _titulo_apontado(con)
    PT.lancar_intimacao(con, titulo_id, modo="PESSOAL", agora=AGORA,
                        comprovante="AR 123")
    return titulo_id


def test_lanca_protesto_e_ocupa_o_livro_de_registro_de_protestos():
    con = banco()
    titulo_id = _titulo_intimado(con)
    lugar = PT.lancar_protesto(con, titulo_id, sv=SV, agora=AGORA,
                              data_extenso=EXTENSO, usuario="TESTE")
    assert lugar["numero_ordem"] == 1
    assert lugar["folha"] == 1
    assert lugar["verso"] is False

    ato = next(a for a in PT.atos_do(con, titulo_id) if a["tipo"] == "PROTESTO")
    assert ato["folha"] == 1
    assert ato["verso"] == 0

    assert PT.titulo(con, titulo_id)["situacao"] == "PROTESTADO"


def test_o_segundo_protesto_vai_para_o_verso_da_mesma_folha():
    # PT_PROTESTO: 1 por FACE, com verso, sem folha nova — medido no acervo:
    # os livros 7 e 8 fecharam com mais registros que folhas.
    con = banco()
    t1 = _titulo_intimado(con)
    PT.lancar_protesto(con, t1, sv=SV, agora=AGORA, data_extenso=EXTENSO)
    t2 = _titulo_intimado(con)
    lugar2 = PT.lancar_protesto(con, t2, sv=SV, agora=AGORA, data_extenso=EXTENSO)
    assert lugar2["folha"] == 1
    assert lugar2["verso"] is True


def test_nao_protesta_titulo_que_nao_foi_intimado():
    con = banco()
    titulo_id = _titulo_apontado(con)
    with pytest.raises(PT.ProtestoError, match="só se protesta título já intimado"):
        PT.lancar_protesto(con, titulo_id, sv=SV, agora=AGORA, data_extenso=EXTENSO)


def test_nao_protesta_duas_vezes():
    con = banco()
    titulo_id = _titulo_intimado(con)
    PT.lancar_protesto(con, titulo_id, sv=SV, agora=AGORA, data_extenso=EXTENSO)
    with pytest.raises(PT.ProtestoError, match="só se protesta título já intimado"):
        PT.lancar_protesto(con, titulo_id, sv=SV, agora=AGORA, data_extenso=EXTENSO)


def test_lanca_desistencia_antes_do_protesto():
    con = banco()
    titulo_id = _titulo_intimado(con)
    resultado = PT.lancar_desistencia(con, titulo_id, motivo="Credor pagou por fora",
                                      agora=AGORA)
    assert resultado["motivo"] == "Credor pagou por fora"
    assert PT.titulo(con, titulo_id)["situacao"] == "DESISTIDO"
    ato = next(a for a in PT.atos_do(con, titulo_id) if a["tipo"] == "DESISTENCIA")
    assert ato["livro_id"] is None


def test_desistencia_exige_motivo():
    con = banco()
    titulo_id = _titulo_apontado(con)
    with pytest.raises(PT.ProtestoError, match="motivo da desistência"):
        PT.lancar_desistencia(con, titulo_id, motivo="  ", agora=AGORA)


def test_nao_desiste_de_protesto_ja_lavrado():
    con = banco()
    titulo_id = _titulo_intimado(con)
    PT.lancar_protesto(con, titulo_id, sv=SV, agora=AGORA, data_extenso=EXTENSO)
    with pytest.raises(PT.ProtestoError, match="antes do protesto lavrado"):
        PT.lancar_desistencia(con, titulo_id, motivo="Credor pagou por fora", agora=AGORA)


def _psycopg_puro(con, *, autocommit=False):
    """Uma conexão do psycopg no schema do teste, SEM a ponte — como a
    transação vai ficar quando a ponte sair."""
    import psycopg
    pg = psycopg.connect(banco_pg.dsn(), autocommit=autocommit)
    pg.execute(f'SET search_path TO "{con.schema}", public')
    if not autocommit:
        pg.commit()
    return pg


def _ao_mesmo_tempo(con, primeiro, segundo):
    """`primeiro` grava e ainda não confirmou; `segundo` chega no meio, por
    outra conexão. Devolve o erro do segundo, ou None se ele passou."""
    if not banco_pg.ativo():
        pytest.skip("a corrida é do PostgreSQL sem a ponte")
    con.commit()
    um, dois = _psycopg_puro(con), _psycopg_puro(con)
    vigia = _psycopg_puro(con, autocommit=True)
    pid = nativo(dois).valor("SELECT pg_backend_pid() AS pid")
    primeiro(um)
    saida: dict = {}

    def corre():
        try:
            segundo(dois)
            dois.commit()
        except Exception as erro:  # o teste confere qual
            saida["erro"] = erro
            dois.rollback()

    fio = threading.Thread(target=corre)
    fio.start()
    for _ in range(200):          # o segundo tem de estar ESPERANDO a linha
        if nativo(vigia).valor(
                "SELECT count(*) AS n FROM pg_locks WHERE pid=%s AND NOT granted",
                (pid,)):
            break
        time.sleep(0.05)
    um.commit()
    fio.join(30)
    for c in (um, dois, vigia):
        c.close()
    return saida.get("erro")


def test_desistencia_e_intimacao_ao_mesmo_tempo_nao_ressuscitam_o_titulo():
    """Ressalva 4 da revisão do L036, o mesmo padrão no título: os `lancar_*`
    conferiam a situação e gravavam por cima sem prender a linha. Com a
    ponte, a trava única do banco põe tudo em fila; sem ela, só o FOR UPDATE
    segura. A desistência grava e ainda não confirmou; a intimação chega no
    meio — e, sem a linha presa, lia APONTADO e deixava o título desistido
    como INTIMADO."""
    con = banco()
    titulo_id = _titulo_apontado(con)
    erro = _ao_mesmo_tempo(
        con,
        lambda pg: PT.lancar_desistencia(pg, titulo_id, motivo="Credor pagou por fora",
                                         agora=AGORA),
        lambda pg: PT.lancar_intimacao(pg, titulo_id, modo="PESSOAL", agora=AGORA,
                                       comprovante="AR 123"))
    assert isinstance(erro, PT.ProtestoError), erro
    assert "só se intima título já apontado" in str(erro)
    assert PT.titulo(con, titulo_id)["situacao"] == "DESISTIDO"
    assert [a["tipo"] for a in PT.atos_do(con, titulo_id)] == ["APONTAMENTO",
                                                               "DESISTENCIA"]


def test_sustacao_que_chega_durante_o_protesto_o_impede():
    """Lei 9.492/1997, art. 17, § 1º, com as duas ao mesmo tempo: a sustação
    não mexe na situação do título, e sem a linha presa o protesto conferia
    «sem ordem em vigor» antes de ela confirmar — e lavrava o título sustado."""
    con = banco()
    titulo_id = _titulo_intimado(con)
    erro = _ao_mesmo_tempo(
        con,
        lambda pg: PT.lancar_sustacao(pg, titulo_id, juizo="Vara Única da Comarca",
                                      processo="0000000-00.2026.8.10.0000",
                                      agora=AGORA),
        lambda pg: PT.lancar_protesto(pg, titulo_id, sv=SV, agora=AGORA,
                                      data_extenso=EXTENSO))
    assert isinstance(erro, PT.ProtestoError), erro
    assert "SUSTADO" in str(erro)
    assert PT.titulo(con, titulo_id)["situacao"] == "INTIMADO"
    assert "PROTESTO" not in [a["tipo"] for a in PT.atos_do(con, titulo_id)]


def test_a_mesma_chave_cadastrada_ao_mesmo_tempo_devolve_o_mesmo_id():
    """Ressalva 3 da revisão do L036: o cadastro conferia a chave de origem e
    fazia o INSERT puro. Sem a ponte, o segundo cadastro não vê o primeiro
    (ainda não confirmado), o INSERT espera o UNIQUE(origem, origem_chave) e
    estoura — e a carga, que é «repetível por construção», cai em erro em vez
    de devolver o id que já existe."""
    con = banco()
    ids: list[int] = []
    cadastra = (lambda pg: ids.append(PT.cadastrar_titulo(
        pg, titulo_bom(), origem="CRA", origem_chave="CRA:9:1", agora=AGORA)))
    erro = _ao_mesmo_tempo(con, cadastra, cadastra)
    assert erro is None, erro
    assert len(ids) == 2 and ids[0] == ids[1]
    assert nativo(con).valor("SELECT count(*) AS n FROM pt_titulos") == 1
    assert len(PT.devedores_do(con, ids[0])) == 1


# ------------------------------------------------------------- o pagamento


@pytest.mark.parametrize("preparar", ["apontado", "intimado"])
def test_lanca_pagamento_em_qualquer_ponto_antes_do_protesto(preparar):
    """Apontado ou intimado, o título se paga. O «protestado» saiu desta lista
    em 21/10/2026 (LH13): ver o teste logo abaixo."""
    con = banco()
    if preparar == "apontado":
        titulo_id = _titulo_apontado(con)
    else:
        titulo_id = _titulo_intimado(con)

    lugar = PT.lancar_pagamento(con, titulo_id, sv=SV, agora=AGORA,
                               data_extenso=EXTENSO, valor_pago="1482.78")
    assert lugar["folha"] == 1
    assert lugar["verso"] is False

    ato = next(a for a in PT.atos_do(con, titulo_id) if a["tipo"] == "PAGAMENTO")
    detalhe = json.loads(ato["detalhe_json"])
    assert detalhe == {"valor_pago_centavos": 148278}

    assert PT.titulo(con, titulo_id)["situacao"] == "PAGO"


def test_o_protesto_lavrado_nao_se_paga_mais_na_serventia():
    """O oficial, 21/10/2026 (LH13, pergunta 17, letra c): «protesto nao pode
    ser pago na serventia depois de lavrar». Até então o pagamento cabia
    também no PROTESTADO (decisão de 24/08/2026), e o título ficava PAGO com o
    protesto em pé para sempre. A recusa diz o caminho: o credor, a carta de
    anuência e o cancelamento (Lei 9.492/1997, art. 26, § 1º; CN-MA art. 942,
    § 2º) — e não lança nada nem ocupa o Livro de Pagamentos."""
    con = banco()
    titulo_id = _titulo_protestado(con)
    with pytest.raises(PT.ProtestoError, match="não se paga mais") as erro:
        PT.lancar_pagamento(con, titulo_id, sv=SV, agora=AGORA,
                            data_extenso=EXTENSO, valor_pago="1482.78",
                            forma_pagamento="PIX")
    assert "carta de anuência" in str(erro.value)
    assert "art. 26, § 1º" in str(erro.value)
    assert PT.titulo(con, titulo_id)["situacao"] == "PROTESTADO"
    assert not [a for a in PT.atos_do(con, titulo_id) if a["tipo"] == "PAGAMENTO"]
    assert "PROTESTADO" in PT.SITUACOES_SEM_PAGAMENTO


def test_cento_e_vinte_pagamentos_cabem_numa_folha_so():
    # PT_PAGAMENTO: 120 por folha, sem verso — medido no acervo (Livro 1,
    # ordens 826 a 2145 em 11 folhas, exatamente 120 por folha).
    con = banco()
    for i in range(120):
        titulo_id = PT.cadastrar_titulo(
            con, titulo_bom(), origem="CRA", origem_chave=f"PAG:{i}", agora=AGORA)
        lugar = PT.lancar_pagamento(con, titulo_id, sv=SV, agora=AGORA,
                                    data_extenso=EXTENSO)
        assert lugar["folha"] == 1
    titulo_id = PT.cadastrar_titulo(
        con, titulo_bom(), origem="CRA", origem_chave="PAG:120", agora=AGORA)
    lugar = PT.lancar_pagamento(con, titulo_id, sv=SV, agora=AGORA,
                               data_extenso=EXTENSO)
    assert lugar["folha"] == 2
    assert lugar["numero_ordem"] == 121


@pytest.mark.parametrize("situacao_final", ["PAGO", "DESISTIDO"])
def test_nao_paga_titulo_em_situacao_final(situacao_final):
    con = banco()
    titulo_id = _titulo_apontado(con)
    if situacao_final == "PAGO":
        PT.lancar_pagamento(con, titulo_id, sv=SV, agora=AGORA, data_extenso=EXTENSO)
    else:
        PT.lancar_desistencia(con, titulo_id, motivo="erro na apresentação",
                              agora=AGORA)
    with pytest.raises(PT.ProtestoError, match="não há como registrar pagamento"):
        PT.lancar_pagamento(con, titulo_id, sv=SV, agora=AGORA, data_extenso=EXTENSO)


def test_pagamento_sem_valor_informado_grava_detalhe_vazio():
    con = banco()
    titulo_id = _titulo_apontado(con)
    PT.lancar_pagamento(con, titulo_id, sv=SV, agora=AGORA, data_extenso=EXTENSO)
    ato = next(a for a in PT.atos_do(con, titulo_id) if a["tipo"] == "PAGAMENTO")
    assert json.loads(ato["detalhe_json"]) == {}


def test_a_quitacao_do_pagamento_sem_titulo_recusa_com_recado():
    """O CAMINHO DE ERRO QUE A REVISÃO DO LD04 ACHOU (LD11): o pagamento cujo
    título não está no banco caía em `TypeError` dentro da quitação, e a rota
    — que só apanha `QuitacaoError` — mostrava a página de erro em vez do
    recado. O banco de hoje tem a chave estrangeira; para chegar ao caso, ela
    sai do schema próprio deste teste, e o ato passa a apontar para um título
    que não existe."""
    import protesto_livros as PLIV
    con = banco()
    titulo_id = _titulo_apontado(con)
    PT.lancar_pagamento(con, titulo_id, sv=SV, agora=AGORA, data_extenso=EXTENSO,
                        valor_pago="1482.78")
    ato = next(a for a in PT.atos_do(con, titulo_id) if a["tipo"] == "PAGAMENTO")
    bd = nativo(con)
    for fk in bd.ler("""SELECT conname FROM pg_constraint
                         WHERE conrelid = 'pt_atos'::regclass AND contype = 'f'
                           AND confrelid = 'pt_titulos'::regclass
                         ORDER BY conname"""):
        bd.escrever(f'ALTER TABLE pt_atos DROP CONSTRAINT "{fk["conname"]}"')
    bd.escrever("UPDATE pt_atos SET titulo_id = %s WHERE id = %s",
                (titulo_id + 1000, ato["id"]))
    with pytest.raises(PLIV.QuitacaoError, match="não está no banco"):
        PLIV.quitacao(con, ato["id"])


# ---------------------------------------------------------- o cancelamento


def _titulo_protestado(con) -> int:
    titulo_id = _titulo_intimado(con)
    PT.lancar_protesto(con, titulo_id, sv=SV, agora=AGORA, data_extenso=EXTENSO)
    return titulo_id


@pytest.mark.parametrize("hipotese", list(PT.CATALOGO_CANCELAMENTO))
def test_cancela_com_cada_hipotese_do_catalogo(hipotese):
    con = banco()
    titulo_id = _titulo_protestado(con)
    resultado = PT.lancar_cancelamento(
        con, titulo_id, hipotese=hipotese,
        fundamento="Conferido o título apresentado pela parte interessada.",
        agora=AGORA)
    assert resultado["hipotese"] == hipotese
    assert resultado["fundamento_legal"] == PT.CATALOGO_CANCELAMENTO[hipotese]["fundamento_legal"]
    assert PT.titulo(con, titulo_id)["situacao"] == "CANCELADO"


def test_o_cancelamento_lavra_o_termo_com_o_registro_que_cancela():
    """Lei 9.492/1997, art. 26, § 6º: no registro eletrônico, «o termo do
    cancelamento será lançado em documento apartado». Até o LD04 o ato
    gravava a hipótese e o fundamento, e `pt_atos.teor` ficava vazio."""
    con = banco()
    titulo_id = _titulo_protestado(con)
    PT.lancar_cancelamento(con, titulo_id, hipotese="PAGAMENTO",
                           fundamento="Título apresentado com a prova da quitação",
                           agora=AGORA)
    protesto = next(a for a in PT.atos_do(con, titulo_id) if a["tipo"] == "PROTESTO")
    baixa = next(a for a in PT.atos_do(con, titulo_id) if a["tipo"] == "CANCELAMENTO")
    titulo = PT.titulo(con, titulo_id)
    for esperado in ("CANCELAMENTO DO REGISTRO DE PROTESTO.",
                     f"sob o n.º {protesto['numero_ordem']}",
                     f"Protocolo n.º {titulo['protocolo']}",
                     "Hipótese do cancelamento: Pagamento do título.",
                     "Fundamento do caso: Título apresentado com a prova da quitação."):
        assert esperado in baixa["teor"], (esperado, baixa["teor"])
    assert "{" not in baixa["teor"] and "None" not in baixa["teor"]


def test_termo_do_cancelamento_com_claro_inventado_recusa_sem_cancelar_nada():
    """O CAMINHO DE ERRO: o modelo da casa gravado por fora da tela com um
    claro que não existe recusa ANTES de gravar o ato — o título continua
    PROTESTADO, e não há baixa sem termo (nem selo pedido para ela)."""
    import protesto_termo as TERMO
    con = banco()
    titulo_id = _titulo_protestado(con)
    with pytest.raises(TERMO.TermoError, match="PT_TERMO_CANCELAMENTO"):
        PT.lancar_cancelamento(con, titulo_id, hipotese="PAGAMENTO",
                               fundamento="Título apresentado com a prova da quitação.",
                               agora=AGORA, modelo_do_termo="Cancelado em {quando}.")
    assert PT.titulo(con, titulo_id)["situacao"] == "PROTESTADO"
    assert not [a for a in PT.atos_do(con, titulo_id) if a["tipo"] == "CANCELAMENTO"]


def test_hipotese_fora_do_catalogo_e_recusada():
    con = banco()
    titulo_id = _titulo_protestado(con)
    with pytest.raises(PT.ProtestoError, match="Hipótese de cancelamento desconhecida"):
        PT.lancar_cancelamento(con, titulo_id, hipotese="ERRO_MATERIAL",
                               fundamento="Título já pago antes do protesto.",
                               agora=AGORA)


def test_cancelamento_exige_fundamento_proprio():
    con = banco()
    titulo_id = _titulo_protestado(con)
    with pytest.raises(PT.ProtestoError, match="fundamento do cancelamento"):
        PT.lancar_cancelamento(con, titulo_id, hipotese="PAGAMENTO",
                               fundamento="ok", agora=AGORA)


def test_nao_cancela_titulo_que_nao_foi_protestado():
    con = banco()
    titulo_id = _titulo_intimado(con)
    with pytest.raises(PT.ProtestoError, match="só se cancela protesto já lavrado"):
        PT.lancar_cancelamento(con, titulo_id, hipotese="PAGAMENTO",
                               fundamento="Título pago antes do protesto.",
                               agora=AGORA)


def _pago_depois_de_protestado(con) -> int:
    """O LEGADO DA REGRA DE 24/08/2026, montado como ele está no banco: o
    protesto lavrado e, depois, o pagamento lançado na serventia, com o
    título PAGO. Desde 21/10/2026 (LH13) o domínio não deixa mais chegar a
    isso, e por isso o pagamento entra aqui direto na tabela."""
    titulo_id = _titulo_protestado(con)
    nativo(con).escrever(
        """INSERT INTO pt_atos(titulo_id, tipo, data_ato, detalhe_json, origem,
               criado_em) VALUES (%s, 'PAGAMENTO', %s, '{}', 'MANUAL', %s)""",
        (titulo_id, AGORA, AGORA))
    nativo(con).escrever("UPDATE pt_titulos SET situacao = 'PAGO' WHERE id = %s",
                         (titulo_id,))
    return titulo_id


@pytest.mark.parametrize("hipotese", PT.HIPOTESES_DO_PAGO_DEPOIS_DO_PROTESTO)
def test_o_pago_depois_do_protesto_pela_regra_antiga_se_cancela(hipotese):
    """Sem isto o título pago aqui depois de protestado, entre 24/08 e
    21/10/2026, ficava para sempre na certidão positiva: o cancelamento só
    aceitava PROTESTADO. Pela decisão de 21/10 (LH13) ele se cancela pela
    anuência do credor — e pela ordem judicial, que vale sempre."""
    con = banco()
    titulo_id = _pago_depois_de_protestado(con)
    assert PT.protesto_em_pe(con, titulo_id)
    assert set(PT.hipoteses_que_cabem(con, PT.titulo(con, titulo_id))) == set(
        PT.HIPOTESES_DO_PAGO_DEPOIS_DO_PROTESTO)
    PT.lancar_cancelamento(con, titulo_id, hipotese=hipotese,
                           fundamento="Carta de anuência do credor, com firma.",
                           agora=AGORA)
    assert PT.titulo(con, titulo_id)["situacao"] == "CANCELADO"
    assert not PT.protesto_em_pe(con, titulo_id)


def test_o_pago_depois_do_protesto_nao_se_cancela_pelo_pagamento_lancado_aqui():
    """Usar o pagamento do Livro de Pagamentos como prova da quitação era a
    letra (a) da pergunta 17, que o oficial não escolheu: depois do protesto,
    a anuência. A recusa diz isso, e o título continua PAGO."""
    con = banco()
    titulo_id = _pago_depois_de_protestado(con)
    with pytest.raises(PT.ProtestoError, match="carta de anuência"):
        PT.lancar_cancelamento(con, titulo_id, hipotese="PAGAMENTO",
                               fundamento="Pago nesta serventia, com recibo.",
                               agora=AGORA)
    assert PT.titulo(con, titulo_id)["situacao"] == "PAGO"


def test_o_pago_sem_protesto_continua_sem_cancelamento():
    """O pago ANTES do protesto nunca teve protesto: não há o que cancelar, e
    a exceção do legado não o alcança."""
    con = banco()
    titulo_id = _titulo_intimado(con)
    PT.lancar_pagamento(con, titulo_id, sv=SV, agora=AGORA, data_extenso=EXTENSO)
    assert PT.hipoteses_que_cabem(con, PT.titulo(con, titulo_id)) == {}
    with pytest.raises(PT.ProtestoError, match="só se cancela protesto já lavrado"):
        PT.lancar_cancelamento(con, titulo_id, hipotese="ANUENCIA_CREDOR",
                               fundamento="Carta de anuência do credor, com firma.",
                               agora=AGORA)
