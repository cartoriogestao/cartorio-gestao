"""
Testes do AVISO DE INTIMACAO, da entrega e do edital.

O QUE ELES CONFEREM

    Que O AVISO E O INSTRUMENTO E A INTIMACAO E O ATO, e que os dois so se
    juntam quando o papel chega na mao do devedor. Tentativa que nao achou
    ninguem NAO lavra intimacao — se lavrasse, o titulo ficaria intimado sem
    que ninguem tivesse sido intimado, e o protesto sairia em cima disso.

    Que O ENDERECO CONGELA no aviso. O papel foi para um lugar; cadastro que
    muda amanha nao muda a tentativa de hoje. E o segundo aviso e outra linha,
    com o endereco novo — que e o que os 255 titulos com mais de um aviso do
    acervo mostram.

    Que O EDITAL SO VEM DEPOIS DA TENTATIVA. Ele substitui a intimacao pessoal
    que nao deu certo, e nao a que nem se tentou.

    Que O MOTIVO DA NAO-ENTREGA SAI DO CATALOGO MEDIDO — 13 motivos, com as
    duas marcas do proprio cadastro do E-Oficio.

    E que o TEOR DO EDITAL CONGELA, com hash: edital publicado nao se redige de
    novo, senao ninguem sabe o que foi afixado.
"""
from __future__ import annotations

import sqlite3
import sys
import threading
import time
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402
from prova_de_intimacao import (entregar_com_comprovante,  # noqa: E402
                               garantir_anexos)

import banco_pg
import protesto as PT
import protesto_aviso as AV
from bd_nativo import banco as nativo
from nucleo_schema import init_nucleo_schema
from pt_schema import init_pt_schema

HOJE = "2026-08-25"
AGORA = "2026-08-25T12:30:00"
EXTENSO = "vinte e cinco de agosto de dois mil e vinte e seis"
SV = {"unit_name": "SERVENTIA EXTRAJUDICIAL DO OFÍCIO ÚNICO DE CIDADE EXEMPLO",
      "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
      "serventia_titulo": "Tabelião e Oficial de Registro",
      "ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA"}


@pytest.fixture()
def con():
    c = conexao_de_teste()
    c.row_factory = sqlite3.Row
    init_nucleo_schema(c)
    init_pt_schema(c)
    # o município da serventia fictícia dos testes: UF 21, município 98765
    c.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    c.executemany("INSERT OR REPLACE INTO settings VALUES (?, ?)",
                  [("ibge_uf", "21"), ("ibge_municipio", "98765")])
    # A ENTREGA LEVA O COMPROVANTE NO MESMO ATO (29/10/2026), e ele mora
    # em `attachments` — que o banco do Protesto sozinho não tem.
    garantir_anexos(c)
    yield c
    c.close()


def titulo(con, *, numero="9911/1", apontar=True) -> int:
    dados = {
        "apresentante_codigo": "001", "apresentante_nome": "BANCO DO BRASIL",
        "especie": "DMI", "numero_titulo": numero, "nosso_numero": f"NN{numero}",
        "data_emissao": "2026-01-05", "data_vencimento": "2026-02-05",
        "valor": "1200.00", "saldo": "1310.45",
        "praca_protesto": "CIDADE EXEMPLO",
        "cedente": {"nome": "LOJA CENTRAL LTDA", "documento": "00000017000149"},
        "devedores": [{"nome": "JOSÉ DA SILVA", "CPF": "04785512388",
                       "enderecos": [{"endereco": "RUA GRANDE, 10",
                                      "bairro": "CENTRO", "cep": "65928000",
                                      "cidade": "Cidade Exemplo", "uf": "MA"}]}],
    }
    tid = PT.cadastrar_titulo(con, dados, origem="CRA",
                              origem_chave=f"lote:{numero}", agora=AGORA)
    if apontar:
        PT.lancar_apontamento(con, tid, sv=SV, agora=AGORA,
                              data_extenso=EXTENSO)
    return tid


# --------------------------------------------------------------- o catálogo


def test_o_catalogo_de_motivos_e_o_medido():
    # 13 motivos no cadastro do E-Ofício, 12 ativos e 1 desligado.
    assert len(AV.MOTIVOS_NAO_ENTREGA) == 12
    assert len(AV.TODOS_OS_MOTIVOS) == 13
    assert AV.MOTIVOS_NAO_ENTREGA[11]["motivo"] == "Ausente"
    # As duas marcas do cadastro, que valem regra.
    assert AV.vai_direto_para_edital(1) and AV.vai_direto_para_edital(5)
    assert not AV.vai_direto_para_edital(11)
    assert AV.MOTIVOS_NAO_ENTREGA[11]["contador"]


def test_a_lista_vem_na_ordem_em_que_a_casa_usou():
    # Motivo de um uso em mil não pode ficar na frente do que responde por 94%.
    lista = AV.motivos_para_escolher()
    assert lista[0]["codigo"] == 11          # Ausente, 1.068 de 1.139
    # 4 e 12 empatam em 4 usos, e o desempate e alfabetico: Falecido, Fechado.
    assert [x["codigo"] for x in lista[:5]] == [11, 2, 3, 4, 12]
    assert 7 not in [x["codigo"] for x in lista]   # o desligado não aparece


def test_motivo_fora_do_catalogo_tem_rotulo_e_nao_estoura():
    assert AV.motivo_rotulo(11) == "Ausente"
    assert AV.motivo_rotulo(99) == "motivo 99"
    assert AV.motivo_rotulo(None) == "motivo None"


# ------------------------------------------------------------ emitir


def test_o_aviso_sai_com_numero_do_exercicio_e_o_endereco_do_dia(con):
    tid = titulo(con)
    r = AV.emitir(con, tid, hoje=HOJE, agora=AGORA, usuario="tabeliao")
    assert r["numero"] == 1 and r["ano"] == 2026

    aviso = AV.ler(con, r["aviso_id"])
    assert aviso["situacao"] == "EMITIDO"
    assert aviso["devedor_nome"] == "JOSÉ DA SILVA"
    assert aviso["endereco"] == "RUA GRANDE, 10"
    assert aviso["cidade"] == "Cidade Exemplo"
    assert aviso["devedor_documento"] == "04785512388"


def test_o_endereco_do_aviso_NAO_muda_quando_o_cadastro_muda(con):
    # O papel foi para um lugar. Cadastro que muda amanhã não muda a tentativa
    # de hoje — e a segunda tentativa é outro aviso, com o endereço novo.
    tid = titulo(con)
    primeiro = AV.emitir(con, tid, hoje=HOJE, agora=AGORA)
    con.execute("UPDATE pt_devedores SET endereco='RUA NOVA, 500' WHERE titulo_id=?",
                (tid,))
    assert AV.ler(con, primeiro["aviso_id"])["endereco"] == "RUA GRANDE, 10"

    segundo = AV.emitir(con, tid, hoje=HOJE, agora=AGORA)
    assert AV.ler(con, segundo["aviso_id"])["endereco"] == "RUA NOVA, 500"


def test_mais_de_um_aviso_no_mesmo_titulo_e_normal(con):
    # 255 dos 1.361 títulos do acervo têm mais de um aviso. Reemitir é rotina.
    tid = titulo(con)
    AV.emitir(con, tid, hoje=HOJE, agora=AGORA)
    AV.emitir(con, tid, hoje=HOJE, agora=AGORA)
    avisos = AV.do_titulo(con, tid)
    assert len(avisos) == 2
    assert [a["numero"] for a in avisos] == [2, 1]      # do mais novo


def test_endereco_informado_no_balcao_sobrepoe_o_cadastro(con):
    tid = titulo(con)
    r = AV.emitir(con, tid, hoje=HOJE, agora=AGORA,
                  endereco={"endereco": "PRAÇA DA MATRIZ, 3",
                            "bairro": "CENTRO"})
    assert AV.ler(con, r["aviso_id"])["endereco"] == "PRAÇA DA MATRIZ, 3"


def test_titulo_nao_apontado_nao_tem_aviso(con):
    # O apontamento é o primeiro ato, e é ele que dá o protocolo que vai no
    # aviso. Avisar antes seria intimar sobre título que não entrou no livro.
    tid = titulo(con, apontar=False)
    with pytest.raises(AV.AvisoError) as erro:
        AV.emitir(con, tid, hoje=HOJE, agora=AGORA)
    assert "RECEBIDO" in str(erro.value)


def test_titulo_sem_devedor_nao_tem_aviso(con):
    tid = titulo(con)
    con.execute("DELETE FROM pt_devedores WHERE titulo_id=?", (tid,))
    with pytest.raises(AV.AvisoError) as erro:
        AV.emitir(con, tid, hoje=HOJE, agora=AGORA)
    assert "sem devedor" in str(erro.value)


def test_o_proximo_numero_nao_consome_nada(con):
    # GET não abre transação de escrita.
    tid = titulo(con)
    assert AV.proximo_numero(con, 2026) == 1
    assert AV.proximo_numero(con, 2026) == 1
    AV.emitir(con, tid, hoje=HOJE, agora=AGORA)
    assert AV.proximo_numero(con, 2026) == 2
    assert AV.proximo_numero(con, 2027) == 1


# ---------------------------------------------------------- a entrega


def test_entrega_com_exito_lavra_a_intimacao_PESSOAL(con):
    tid = titulo(con)
    r = AV.emitir(con, tid, hoje=HOJE, agora=AGORA)
    volta = entregar_com_comprovante(con, r["aviso_id"],
                                 agora=AGORA, recebido_por="MARIA DA SILVA",
                                 usuario="tabeliao")
    assert volta["situacao"] == "ENTREGUE" and volta["ato_id"]

    ato = con.execute("SELECT * FROM pt_atos WHERE id=?",
                      (volta["ato_id"],)).fetchone()
    assert ato["tipo"] == "INTIMACAO"
    assert '"modo": "PESSOAL"' in ato["detalhe_json"]
    assert "MARIA DA SILVA" in ato["detalhe_json"]
    assert con.execute("SELECT situacao FROM pt_titulos WHERE id=?",
                       (tid,)).fetchone()[0] == "INTIMADO"


def test_entrega_SEM_exito_nao_lavra_intimacao_nenhuma(con):
    # É a regra que importa: se a tentativa frustrada lavrasse intimação, o
    # título ficaria intimado sem ninguém ter sido intimado — e o protesto
    # sairia em cima disso.
    tid = titulo(con)
    r = AV.emitir(con, tid, hoje=HOJE, agora=AGORA)
    volta = AV.registrar_entrega(con, r["aviso_id"], entregue=False,
                                 motivo=11, agora=AGORA)
    assert volta["situacao"] == "NAO_ENTREGUE" and volta["ato_id"] is None
    assert volta["vai_para_edital"]
    assert con.execute("SELECT COUNT(*) c FROM pt_atos WHERE tipo='INTIMACAO'"
                       ).fetchone()["c"] == 0
    assert con.execute("SELECT situacao FROM pt_titulos WHERE id=?",
                       (tid,)).fetchone()[0] == "APONTADO"


def test_nao_entrega_exige_motivo_do_catalogo(con):
    tid = titulo(con)
    r = AV.emitir(con, tid, hoje=HOJE, agora=AGORA)
    with pytest.raises(AV.AvisoError) as erro:
        AV.registrar_entrega(con, r["aviso_id"], entregue=False, agora=AGORA)
    assert "Ausente" in str(erro.value)          # a mensagem lista o catálogo

    with pytest.raises(AV.AvisoError):
        AV.registrar_entrega(con, r["aviso_id"], entregue=False, motivo=99,
                             agora=AGORA)


def test_entrega_registrada_duas_vezes_e_recusada(con):
    tid = titulo(con)
    r = AV.emitir(con, tid, hoje=HOJE, agora=AGORA)
    entregar_com_comprovante(con, r["aviso_id"], agora=AGORA)
    with pytest.raises(AV.AvisoError) as erro:
        entregar_com_comprovante(con, r["aviso_id"], agora=AGORA)
    assert "já foi registrada" in str(erro.value)


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


def test_duas_entregas_do_mesmo_aviso_ao_mesmo_tempo_lavram_uma_intimacao(con):
    """Ressalva 4 da revisão do L036: a entrega conferia a situação do aviso
    e gravava por cima sem prender a linha. Com a ponte, a trava única do
    banco põe as duas em fila; sem ela, só o FOR UPDATE segura. A primeira
    entrega grava e ainda não confirmou; a segunda chega no meio — e, sem a
    linha presa, lia EMITIDO e lavrava a segunda intimação."""
    tid = titulo(con)
    r = AV.emitir(con, tid, hoje=HOJE, agora=AGORA)
    erro = _ao_mesmo_tempo(
        con,
        lambda pg: entregar_com_comprovante(pg, r["aviso_id"],
                                        agora=AGORA),
        lambda pg: entregar_com_comprovante(pg, r["aviso_id"],
                                        agora=AGORA))
    assert isinstance(erro, AV.AvisoError), erro
    assert "já foi registrada" in str(erro)
    assert [a["tipo"] for a in PT.atos_do(con, tid)] == ["APONTAMENTO",
                                                         "INTIMACAO"]
    assert len(AV.tentativas(con, r["aviso_id"])) == 1


def test_edital_que_chega_durante_a_entrega_e_recusado(con):
    """Ressalva 4 da revisão do L036, o edital: sem a linha do aviso presa,
    ele lia NAO_ENTREGUE enquanto a segunda tentativa registrava a entrega,
    publicava em cima dela e deixava o aviso EDITAL, com duas intimações."""
    tid = titulo(con)
    r = AV.emitir(con, tid, hoje=HOJE, agora=AGORA)
    AV.registrar_entrega(con, r["aviso_id"], entregue=False, motivo=11,
                         agora=AGORA)
    erro = _ao_mesmo_tempo(
        con,
        lambda pg: entregar_com_comprovante(pg, r["aviso_id"],
                                        agora=AGORA),
        lambda pg: AV.publicar_edital(pg, r["aviso_id"], sv=SV, hoje=HOJE,
                                      agora=AGORA))
    assert isinstance(erro, AV.AvisoError), erro
    assert "está ENTREGUE" in str(erro)
    assert AV.ler(con, r["aviso_id"])["situacao"] == "ENTREGUE"
    assert AV.editais_do_dia(con, HOJE) == []


def test_a_segunda_tentativa_do_mesmo_aviso_e_permitida(con):
    # "Ausente" e "Fechado" são motivos que CONTAM tentativa e pedem outra:
    # a pessoa mora ali, só não estava.
    tid = titulo(con)
    r = AV.emitir(con, tid, hoje=HOJE, agora=AGORA)
    AV.registrar_entrega(con, r["aviso_id"], entregue=False, motivo=11,
                         agora=AGORA)
    volta = entregar_com_comprovante(con, r["aviso_id"],
                                 agora=AGORA)
    assert volta["situacao"] == "ENTREGUE"
    assert volta["tentativas"] == 2


def test_a_tentativa_ANTERIOR_nao_se_perde(con):
    """O defeito que a medição achou depois de o módulo estar pronto.

    Guardar só o desfecho no aviso apagava a tentativa anterior — e é o rastro
    dela que JUSTIFICA o edital. Medido em `tbBoletoControleNEntrega`: 1.139
    controles para 1.093 títulos, 39 deles com mais de uma tentativa. São 3,6%
    dos casos, e são justamente os que a inspeção lê com atenção.
    """
    tid = titulo(con)
    r = AV.emitir(con, tid, hoje=HOJE, agora=AGORA)
    AV.registrar_entrega(con, r["aviso_id"], entregue=False, motivo=11,
                         quando="2026-08-20", agora=AGORA,
                         observacao="fui de manhã")
    AV.registrar_entrega(con, r["aviso_id"], entregue=False, motivo=12,
                         quando="2026-08-22", agora=AGORA,
                         observacao="voltei à tarde")

    houve = AV.tentativas(con, r["aviso_id"])
    assert len(houve) == 2
    assert [x["motivo"] for x in houve] == [11, 12]
    assert [x["quando"] for x in houve] == ["2026-08-20", "2026-08-22"]
    assert houve[0]["observacao"] == "fui de manhã"
    # E o aviso guarda o DESFECHO, como `tbBoletoApto` ao lado do controle.
    assert AV.ler(con, r["aviso_id"])["motivo"] == 12


def test_a_entrega_que_deu_certo_tambem_e_uma_tentativa(con):
    tid = titulo(con)
    r = AV.emitir(con, tid, hoje=HOJE, agora=AGORA)
    entregar_com_comprovante(con, r["aviso_id"], agora=AGORA,
                         recebido_por="MARIA")
    houve = AV.tentativas(con, r["aviso_id"])
    assert len(houve) == 1
    assert houve[0]["entregue"] == 1
    assert houve[0]["recebido_por"] == "MARIA"
    assert houve[0]["motivo"] is None


# ------------------------------------------------------------- o edital


def test_o_edital_lavra_a_intimacao_por_EDITAL_com_codigo(con):
    # Antes disto o código do edital era digitado à mão na ficha, e edital que
    # só existe como texto num campo não se confere depois.
    tid = titulo(con)
    r = AV.emitir(con, tid, hoje=HOJE, agora=AGORA)
    AV.registrar_entrega(con, r["aviso_id"], entregue=False, motivo=11,
                         agora=AGORA)
    ed = AV.publicar_edital(con, r["aviso_id"], sv=SV, hoje=HOJE, agora=AGORA,
                            usuario="tabeliao")
    assert ed["numero"] == 1 and ed["codigo"] == "ED-2026-0001"

    ato = con.execute("SELECT * FROM pt_atos WHERE id=?",
                      (ed["ato_id"],)).fetchone()
    assert '"modo": "EDITAL"' in ato["detalhe_json"]
    assert "ED-2026-0001" in ato["detalhe_json"]
    assert "Ausente" in ato["detalhe_json"]     # o motivo vai no comprovante
    assert AV.ler(con, r["aviso_id"])["situacao"] == "EDITAL"
    assert con.execute("SELECT situacao FROM pt_titulos WHERE id=?",
                       (tid,)).fetchone()[0] == "INTIMADO"


def test_edital_sem_tentativa_e_recusado(con):
    # O edital substitui a intimação pessoal que não deu certo, e não a que
    # nem se tentou.
    tid = titulo(con)
    r = AV.emitir(con, tid, hoje=HOJE, agora=AGORA)
    with pytest.raises(AV.AvisoError) as erro:
        AV.publicar_edital(con, r["aviso_id"], sv=SV, hoje=HOJE, agora=AGORA)
    assert "não foi entregue" in str(erro.value)


def test_edital_de_aviso_entregue_e_recusado(con):
    tid = titulo(con)
    r = AV.emitir(con, tid, hoje=HOJE, agora=AGORA)
    entregar_com_comprovante(con, r["aviso_id"], agora=AGORA)
    with pytest.raises(AV.AvisoError):
        AV.publicar_edital(con, r["aviso_id"], sv=SV, hoje=HOJE, agora=AGORA)


def test_o_teor_do_edital_traz_o_que_a_lei_manda_e_congela(con):
    tid = titulo(con)
    r = AV.emitir(con, tid, hoje=HOJE, agora=AGORA)
    AV.registrar_entrega(con, r["aviso_id"], entregue=False, motivo=11,
                         agora=AGORA)
    ed = AV.publicar_edital(con, r["aviso_id"], sv=SV, hoje=HOJE, agora=AGORA)

    teor = ed["teor"]
    assert "EDITAL DE INTIMAÇÃO" in teor
    assert "JOSÉ DA SILVA" in teor
    # O DOCUMENTO SAI PONTUADO: o edital vai na parede para a pessoa se
    # reconhecer nele, e `04785512388` não se lê.
    assert "047.855.123-88" in teor
    assert "04785512388" not in teor
    assert "9911/1" in teor
    assert "1.310,45" in teor
    assert "9.492" in teor
    assert "Cidade Exemplo/MA" in teor

    # Congelado com hash: o que foi afixado não se redige de novo.
    guardado = AV.edital(con, ed["edital_id"])
    assert guardado["teor"] == teor
    assert guardado["hash_teor"] == AV.hash_edital(1, 2026, teor, AGORA)
    assert guardado["cidade_ibge"] == AV.cidade_ibge(con) == "2198765"


def test_o_teor_diz_A_CONFERIR_quando_nao_ha_protocolo(con):
    # Não se inventa número: título sem protocolo sai dizendo isso.
    tid = titulo(con)
    con.execute("UPDATE pt_titulos SET protocolo=NULL WHERE id=?", (tid,))
    r = AV.emitir(con, tid, hoje=HOJE, agora=AGORA)
    AV.registrar_entrega(con, r["aviso_id"], entregue=False, motivo=11,
                         agora=AGORA)
    ed = AV.publicar_edital(con, r["aviso_id"], sv=SV, hoje=HOJE, agora=AGORA)
    assert "Protocolo: A CONFERIR" in ed["teor"]


# ------------------------------------------------------------ as listas


def test_as_listas_mostram_o_que_esta_esperando(con):
    a = titulo(con, numero="1/1")
    b = titulo(con, numero="2/1")
    c = titulo(con, numero="3/1")
    ra = AV.emitir(con, a, hoje=HOJE, agora=AGORA)
    rb = AV.emitir(con, b, hoje=HOJE, agora=AGORA)
    rc = AV.emitir(con, c, hoje=HOJE, agora=AGORA)
    AV.registrar_entrega(con, rb["aviso_id"], entregue=False, motivo=11,
                         agora=AGORA)
    entregar_com_comprovante(con, rc["aviso_id"], agora=AGORA)

    esperando = AV.esperando_entrega(con)
    assert [x["id"] for x in esperando] == [ra["aviso_id"]]
    assert esperando[0]["numero_titulo"] == "1/1"

    para_edital = AV.esperando_edital(con)
    assert [x["id"] for x in para_edital] == [rb["aviso_id"]]

    assert AV.contagens(con) == {"EMITIDO": 1, "ENTREGUE": 1,
                                 "NAO_ENTREGUE": 1, "EDITAL": 0,
                                 "CANCELADO": 0}


def test_a_folha_do_dia_junta_os_editais_publicados(con):
    # A folha que se prega na parede junta vários; o registro é um por aviso.
    for n in ("1/1", "2/1"):
        tid = titulo(con, numero=n)
        r = AV.emitir(con, tid, hoje=HOJE, agora=AGORA)
        AV.registrar_entrega(con, r["aviso_id"], entregue=False, motivo=11,
                             agora=AGORA)
        AV.publicar_edital(con, r["aviso_id"], sv=SV, hoje=HOJE, agora=AGORA)

    do_dia = AV.editais_do_dia(con, HOJE)
    assert len(do_dia) == 2
    assert [x["numero"] for x in do_dia] == [1, 2]
    assert AV.editais_do_dia(con, "2026-08-24") == []


def test_aviso_que_nao_existe_nao_estoura(con):
    assert AV.ler(con, 9999) is None
    with pytest.raises(AV.AvisoError):
        entregar_com_comprovante(con, 9999, agora=AGORA)
    with pytest.raises(AV.AvisoError):
        AV.publicar_edital(con, 9999, sv=SV, hoje=HOJE, agora=AGORA)


def test_o_edital_data_por_extenso_como_todo_papel_da_casa(con):
    """`2026-08-25` é formato de banco de dados, e não de edital afixado.

    Foi lendo o edital pronto — e não o código — que os dois defeitos
    apareceram: a data crua e o CPF sem pontuação. A função da data é a mesma
    que o resto da casa usa; duas formas de datar seriam uma a mais.
    """
    tid = titulo(con)
    r = AV.emitir(con, tid, hoje=HOJE, agora=AGORA)
    AV.registrar_entrega(con, r["aviso_id"], entregue=False, motivo=11,
                         agora=AGORA)
    ed = AV.publicar_edital(con, r["aviso_id"], sv=SV, hoje=HOJE, agora=AGORA,
                            data_extenso="vinte e cinco de agosto de 2026")
    assert "Cidade Exemplo/MA, vinte e cinco de agosto de 2026." in ed["teor"]
    assert HOJE not in ed["teor"]


def test_sem_data_por_extenso_o_edital_sai_com_a_data_crua_e_nao_quebra(con):
    # Quem chama esquecer o parâmetro não pode derrubar a publicação: sai a
    # data como veio, que é feio mas é verdadeiro.
    tid = titulo(con)
    r = AV.emitir(con, tid, hoje=HOJE, agora=AGORA)
    AV.registrar_entrega(con, r["aviso_id"], entregue=False, motivo=11,
                         agora=AGORA)
    ed = AV.publicar_edital(con, r["aviso_id"], sv=SV, hoje=HOJE, agora=AGORA)
    assert f"Cidade Exemplo/MA, {HOJE}." in ed["teor"]


# ------------------------- apontados sem aviso e apontados antigos (LH06)
#
# 21/10/2026: os títulos apontados que vieram do E-Ofício sem aviso não
# apareciam em lista nenhuma de intimação, e os apontados de 2020-2022 se
# misturavam aos avisos da rua. O «hoje» chega do Python, como em toda a casa.

HOJE_LH06 = "2026-10-21"


def _apontado_em(con, numero: str, quando: str) -> int:
    tid = titulo(con, numero=numero, apontar=False)
    PT.lancar_apontamento(con, tid, sv=SV, agora=f"{quando}T09:00:00",
                          data_extenso=EXTENSO)
    return tid


def test_o_apontado_sem_aviso_vai_para_intimar_e_o_antigo_para_decidir(con):
    novo = titulo(con, numero="10/1")                      # 25/08/2026
    velho = _apontado_em(con, "11/1", "2022-03-01")
    com_aviso = titulo(con, numero="12/1")
    AV.emitir(con, com_aviso, hoje=HOJE, agora=AGORA)

    assert [t["titulo_id"] for t in AV.apontados_sem_aviso(con, HOJE_LH06)] == [novo]
    antigos = AV.apontados_antigos(con, HOJE_LH06)
    assert [t["titulo_id"] for t in antigos] == [velho]
    assert antigos[0]["apontado_em"] == "2022-03-01"
    assert antigos[0]["devedor_nome"] == "JOSÉ DA SILVA"
    assert antigos[0]["avisos"] == 0


def test_o_corte_dos_antigos_e_de_180_dias_contados_do_hoje_do_python(con):
    assert AV.ANTIGO_DIAS == 180
    no_limite = _apontado_em(con, "20/1", "2026-04-24")   # 180 dias antes
    passou = _apontado_em(con, "21/1", "2026-04-23")      # 181 dias antes
    assert [t["titulo_id"] for t in AV.apontados_sem_aviso(con, HOJE_LH06)] == [
        no_limite]
    assert [t["titulo_id"] for t in AV.apontados_antigos(con, HOJE_LH06)] == [passou]
    # O mesmo banco, outro «hoje»: quem decide é a data que a tela passa.
    assert AV.apontados_antigos(con, "2026-10-20") == []


def test_o_aviso_do_apontado_antigo_sai_da_lista_dos_que_esperam_entrega(con):
    recente = titulo(con, numero="30/1")
    velho = _apontado_em(con, "31/1", "2021-06-10")
    ra = AV.emitir(con, recente, hoje=HOJE, agora=AGORA)
    rv = AV.emitir(con, velho, hoje=HOJE, agora=AGORA)
    assert [a["id"] for a in AV.esperando_entrega(con, hoje=HOJE_LH06)] == [
        ra["aviso_id"]]
    # Sem `hoje`, como era: quem não passa a data recebe a lista inteira.
    assert [a["id"] for a in AV.esperando_entrega(con)] == [
        ra["aviso_id"], rv["aviso_id"]]
    # E o aviso do antigo continua à vista, na lista dos antigos.
    assert [t["avisos"] for t in AV.apontados_antigos(con, HOJE_LH06)] == [1]


def test_aviso_cancelado_nao_conta_como_aviso_vivo(con):
    tid = titulo(con, numero="40/1")
    r = AV.emitir(con, tid, hoje=HOJE, agora=AGORA)
    assert AV.apontados_sem_aviso(con, HOJE_LH06) == []
    nativo(con).escrever("UPDATE pt_avisos SET situacao='CANCELADO' WHERE id=%s",
                         (r["aviso_id"],))
    [linha] = AV.apontados_sem_aviso(con, HOJE_LH06)
    assert (linha["titulo_id"], linha["avisos_vivos"], linha["avisos"]) == (tid, 0, 1)


def test_o_titulo_apontado_sem_apontamento_valido_vem_primeiro_entre_os_antigos(con):
    """O estado do 900001/1: APONTADO com o único apontamento cancelado. Sem
    data, ele é «antigo a decidir» — e vem PRIMEIRO, como vinha no SQLite (o
    NULL do PostgreSQL iria para o fim sem o NULLS FIRST)."""
    velho = _apontado_em(con, "50/1", "2020-01-15")
    sem_data = titulo(con, numero="51/1")
    nativo(con).escrever(
        "UPDATE pt_atos SET cancelado=1 WHERE titulo_id=%s AND tipo='APONTAMENTO'",
        (sem_data,))
    antigos = AV.apontados_antigos(con, HOJE_LH06)
    assert [t["titulo_id"] for t in antigos] == [sem_data, velho]
    assert antigos[0]["apontado_em"] is None


def test_o_titulo_que_nao_esta_apontado_nao_entra_em_nenhuma_das_duas(con):
    tid = _apontado_em(con, "60/1", "2022-02-02")
    nativo(con).escrever("UPDATE pt_titulos SET situacao='PAGO' WHERE id=%s", (tid,))
    titulo(con, numero="61/1", apontar=False)              # RECEBIDO
    assert AV.apontados_sem_aviso(con, HOJE_LH06) == []
    assert AV.apontados_antigos(con, HOJE_LH06) == []


# ----------------------- o tipo de `data_ato` no PostgreSQL (revisão do LH06)
#
# Conferido no LH08: `pt_atos.data_ato` é `text` no esquema da branch
# (`pt_schema.py`) e no da produção (`respostas_pg/schema.sql`). O corte dos
# antigos compara TEXTO, e isso só é cronológico porque as duas formas que o
# sistema grava começam pela data ISO.


def _ids(linhas) -> list[int]:
    return [int(t["titulo_id"]) for t in linhas]


def _data_do_apontamento(con, titulo_id: int, data_ato: str) -> None:
    nativo(con).escrever(
        "UPDATE pt_atos SET data_ato=%s WHERE titulo_id=%s AND tipo='APONTAMENTO'",
        (data_ato, titulo_id))


def test_o_corte_vale_nas_duas_formas_de_data_que_o_sistema_grava(con):
    """A carga do E-Ofício grava `AAAA-MM-DD` (`acervo_carga._data`); o balcão
    grava `AAAA-MM-DDTHH:MM:SS` (`lancar_apontamento`, com o `agora`). O
    corte de 21/10/2026 é 24/04/2026, e as duas formas caem do lado certo
    dele — inclusive a do balcão no último segundo do dia anterior."""
    no_corte_da_carga = _apontado_em(con, "90/1", "2026-04-24")
    _data_do_apontamento(con, no_corte_da_carga, "2026-04-24")
    no_corte_do_balcao = _apontado_em(con, "91/1", "2026-04-24")
    _data_do_apontamento(con, no_corte_do_balcao, "2026-04-24T00:00:00")
    vespera_do_balcao = _apontado_em(con, "92/1", "2026-04-23")
    _data_do_apontamento(con, vespera_do_balcao, "2026-04-23T23:59:59")
    vespera_da_carga = _apontado_em(con, "93/1", "2026-04-23")
    _data_do_apontamento(con, vespera_da_carga, "2026-04-23")

    assert nativo(con).valor(
        "SELECT pg_typeof(data_ato)::text AS tipo FROM pt_atos "
        "ORDER BY id LIMIT 1") == "text"
    assert _ids(AV.apontados_sem_aviso(con, HOJE_LH06)) == [
        no_corte_da_carga, no_corte_do_balcao]
    antigos = AV.apontados_antigos(con, HOJE_LH06)
    assert sorted(_ids(antigos)) == sorted([vespera_do_balcao, vespera_da_carga])
    assert {t["apontado_em"] for t in antigos} == {"2026-04-23"}
    # O «hoje» da rota é texto; como `date` ou com hora, o corte é o mesmo.
    from datetime import date
    for hoje in (date(2026, 10, 21), "2026-10-21T17:30:00"):
        assert _ids(AV.apontados_sem_aviso(con, hoje)) == [
            no_corte_da_carga, no_corte_do_balcao], hoje
        assert sorted(_ids(AV.apontados_antigos(con, hoje))) == sorted(
            [vespera_do_balcao, vespera_da_carga]), hoje


def test_se_a_data_do_ato_virar_date_as_listas_nao_mudam(con):
    """Com a coluna `date`, o psycopg devolve `datetime.date`, e o `[:10]`
    da lista estourava (`'datetime.date' object is not subscriptable`). A
    mesma bancada, antes e depois de trocar o tipo, dá as mesmas listas."""
    recente = titulo(con, numero="94/1")                  # 25/08/2026
    velho = _apontado_em(con, "95/1", "2022-03-01")
    com_aviso = _apontado_em(con, "96/1", "2021-06-10")
    AV.emitir(con, com_aviso, hoje=HOJE, agora=AGORA)

    def listas():
        return (_ids(AV.apontados_sem_aviso(con, HOJE_LH06)),
                [(t["titulo_id"], t["apontado_em"])
                 for t in AV.apontados_antigos(con, HOJE_LH06)],
                [a["titulo_id"] for a in AV.esperando_entrega(con, hoje=HOJE_LH06)])

    como_texto = listas()
    assert como_texto == ([recente],
                          [(com_aviso, "2021-06-10"), (velho, "2022-03-01")],
                          [])
    bd = nativo(con)
    bd.escrever("ALTER TABLE pt_atos ALTER COLUMN data_ato TYPE date "
                "USING left(data_ato, 10)::date")
    assert bd.valor("SELECT pg_typeof(data_ato)::text AS tipo FROM pt_atos "
                    "ORDER BY id LIMIT 1") == "date"
    assert listas() == como_texto


def _com_anexos(con):
    """A tabela dos anexos, que a lista do upload consulta: o banco deste
    arquivo só tem o núcleo e o Protesto."""
    bd = nativo(con)
    bd.escrever("""CREATE TABLE IF NOT EXISTS attachments (
        id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
        entity_type text, entity_id bigint, original_name text,
        size_bytes bigint, uploaded_at text)""")
    return bd


def test_o_aviso_entregue_do_eoficio_nao_e_trabalho_de_upload(con):
    """Os 68 entregues em mãos do E-Ofício viriam ao alto como «falta o
    comprovante»: o papel deles é do arquivo do E-Ofício. A coluna `origem`
    chega ao esquema com a carga (LH07) — aqui ela é posta no banco do teste."""
    bd = _com_anexos(con)
    bd.escrever("ALTER TABLE pt_avisos ADD COLUMN IF NOT EXISTS origem TEXT")
    daqui = AV.emitir(con, titulo(con, numero="70/1"), hoje=HOJE, agora=AGORA)
    de_la = AV.emitir(con, titulo(con, numero="71/1"), hoje=HOJE, agora=AGORA)
    sem_origem = AV.emitir(con, titulo(con, numero="72/1"), hoje=HOJE, agora=AGORA)
    for r in (daqui, de_la, sem_origem):
        entregar_com_comprovante(con, r["aviso_id"], agora=AGORA)
    bd.escrever("UPDATE pt_avisos SET origem='SISTEMA' WHERE id=%s",
                (daqui["aviso_id"],))
    bd.escrever("UPDATE pt_avisos SET origem='EOFICIO' WHERE id=%s",
                (de_la["aviso_id"],))
    ids = {a["id"] for a in AV.entregues(con)}
    assert ids == {daqui["aviso_id"], sem_origem["aviso_id"]}


def test_sem_a_coluna_origem_a_lista_do_upload_e_a_de_sempre(con):
    """O esquema sem `pt_avisos.origem` (antes da carga do LH07) não pode
    derrubar a tela: a consulta só filtra a origem quando a coluna existe."""
    bd = _com_anexos(con)
    bd.escrever("ALTER TABLE pt_avisos DROP COLUMN IF EXISTS origem")
    r = AV.emitir(con, titulo(con, numero="80/1"), hoje=HOJE, agora=AGORA)
    entregar_com_comprovante(con, r["aviso_id"], agora=AGORA)
    assert [a["id"] for a in AV.entregues(con)] == [r["aviso_id"]]
