"""
Testes do retorno a CRA — e do andamento, que sai junto com ele.

O QUE ELES CONFEREM
    Que NADA SAI DUAS VEZES: ato informado ganha `retorno_id` e some da lista
    de pendentes. Mandar o mesmo protesto duas vezes faz a Central registrar
    dois, e desfazer isso e trabalho de carta.

    Que a OCORRENCIA sai do ato, e que ela e a MEDIDA — `C` para o protesto,
    que e o que esta casa mandou 287 vezes em 383 e a Central aceitou.

    Que o RETORNO e o ANDAMENTO saem em PAR. E regra da casa, do roteiro do
    protesto que o oficial trouxe: "SEMPRE QUE GERAR RETORNO (FINAL), GERAR
    ANDAMENTO".

    E que os dois arquivos tem 600 posicoes e passam pela LEITURA de volta —
    o ida e volta que ja pegou quatro defeitos neste modulo.
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
from prova_de_intimacao import juntar_prova  # noqa: E402

import banco_pg
import protesto as PT
import protesto_arquivo as PA
import protesto_retorno as PR
from caixa_schema import init_caixa_schema
from nucleo_schema import init_nucleo_schema
from pt_schema import init_pt_schema

AGORA = "2026-08-25T10:00:00"
HOJE = "2026-08-25"
SV = {"unit_name": "SERVENTIA EXTRAJUDICIAL DE CIDADE EXEMPLO",
      "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
      "serventia_titulo": "Tabelião e Oficial de Registro",
      "ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA"}


def banco() -> sqlite3.Connection:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    init_nucleo_schema(con)
    init_pt_schema(con)
    return con


def titulo(con, *, numero="9911/1", apresentante="001",
           nome_apresentante="BANCO DO BRASIL", origem="CRA",
           valor="1.200,00") -> int:
    dados = {
        "apresentante_codigo": apresentante,
        "apresentante_nome": nome_apresentante,
        "especie": "DMI", "numero_titulo": numero,
        "nosso_numero": f"NN{numero}",
        "data_emissao": "2026-01-05", "data_vencimento": "2026-02-05",
        "valor": valor, "saldo": "1.310,45",
        "praca_protesto": "CIDADE EXEMPLO", "motivo_protesto": "1",
        "cedente": {"nome": "LOJA CENTRAL LTDA",
                    "documento": "00000017000149"},
        "devedores": [{"nome": "JOSÉ DA SILVA", "CPF": "04785512388",
                       "enderecos": [{"endereco": "RUA GRANDE, 10",
                                      "bairro": "CENTRO",
                                      "cidade": "Cidade Exemplo", "uf": "MA"}]}],
    }
    return PT.cadastrar_titulo(con, dados, origem=origem,
                               origem_chave=f"lote:{numero}", agora=AGORA)


def ate_o_protesto(con, titulo_id: int) -> None:
    PT.lancar_apontamento(con, titulo_id, sv=SV, agora=AGORA, data_extenso="x")
    PT.lancar_intimacao(con, titulo_id, modo="PESSOAL", agora=AGORA)
    juntar_prova(con, titulo_id)   # a prova da intimação (29/10/2026)
    PT.lancar_protesto(con, titulo_id, sv=SV, agora=AGORA, data_extenso="x")


# Os itens fixos da retirada na vigência 10022, de `tests/custas_reais.json`
# (a soma com 5 folhas é a constante medida, R$ 82,64), e a faixa 17.4 que
# fecha o caso medido: R$ 418,17 dá R$ 118,49. O teto da faixa é do ensaio.
ITENS_10022 = {"17.7": "11,96", "17.2": "10,68", "17.10.1": "26,25", "17.9": "6,75"}
FAIXA_10022 = ("0,00", "10.000,00", "35,85")
CODIGO_DO_ITEM = {"17.7": 67, "17.2": 25, "17.10.1": 645, "17.9": 331}


def tabela_de_custas(con, *, vigencia=10022, inicio="2026-01-01",
                     fim="2026-12-31", itens=None, faixa=FAIXA_10022) -> None:
    # `init_caixa_schema` pede estas três; o banco da casa as cria antes.
    con.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY)")
    con.execute("CREATE TABLE IF NOT EXISTS ri_protocolos (id INTEGER PRIMARY KEY)")
    con.execute("CREATE TABLE IF NOT EXISTS ri_matriculas (id INTEGER PRIMARY KEY)")
    init_caixa_schema(con)
    con.execute(
        """INSERT INTO cx_vigencias(codigo, descricao, vigente, inicio, fim)
           VALUES (?,?,?,?,?)""",
        (vigencia, f"TABELA {vigencia}", 1 if vigencia == 10022 else 0, inicio, fim))
    for tj, total in (ITENS_10022 if itens is None else itens).items():
        con.execute(
            "INSERT OR IGNORE INTO cx_servicos(codigo, codigo_tj, descricao) "
            "VALUES (?,?,?)", (CODIGO_DO_ITEM[tj], tj, f"item {tj}"))
        con.execute(
            "INSERT INTO cx_servico_valores(servico, vigencia, total) VALUES (?,?,?)",
            (CODIGO_DO_ITEM[tj], vigencia, total))
    de, ate, total = faixa
    con.execute(
        """INSERT INTO cx_faixas(tabela, vigencia, de, ate, codigo_tj, total)
           VALUES (17, ?, ?, ?, '17.4.1', ?)""", (vigencia, de, ate, total))
    con.commit()


def desistido(con, *, numero="9911/1", valor="418,17", agora=AGORA) -> int:
    tid = titulo(con, numero=numero, valor=valor)
    PT.lancar_apontamento(con, tid, sv=SV, agora=agora, data_extenso="x")
    PT.lancar_desistencia(con, tid, motivo="Credor desistiu.", agora=agora)
    return tid


# ------------------------------------------------------------- o protocolo


def test_o_protocolo_nasce_com_o_apontamento_na_forma_medida():
    # AAMMDD + o sequencial do dia. Medido em 928 dos 931 titulos que
    # entraram de 2024 em diante.
    con = banco()
    a = titulo(con, numero="1/1")
    b = titulo(con, numero="2/1")
    PT.lancar_apontamento(con, a, sv=SV, agora=AGORA, data_extenso="x")
    PT.lancar_apontamento(con, b, sv=SV, agora=AGORA, data_extenso="x")
    protocolos = [r[0] for r in con.execute(
        "SELECT protocolo FROM pt_titulos ORDER BY id")]
    assert protocolos == ["2608250001", "2608250002"]


def test_o_protocolo_de_quem_ja_tem_nao_se_renumera():
    # Titulo vindo do acervo traz o protocolo que a Central ja conhece.
    con = banco()
    tid = titulo(con)
    con.execute("UPDATE pt_titulos SET protocolo='7797140001' WHERE id=?", (tid,))
    PT.lancar_apontamento(con, tid, sv=SV, agora=AGORA, data_extenso="x")
    assert con.execute("SELECT protocolo FROM pt_titulos").fetchone()[0] \
        == "7797140001"


# -------------------------------------------------------------- pendentes


def test_so_entra_ato_que_a_central_espera():
    # Apontamento nao volta no retorno: a Central ja sabe que o titulo chegou,
    # foi ela que o mandou.
    con = banco()
    tid = titulo(con)
    ate_o_protesto(con, tid)
    tipos = sorted(a["tipo"] for a in PR.pendentes(con))
    assert tipos == ["PROTESTO"]


def test_titulo_digitado_no_balcao_nao_tem_para_onde_voltar():
    con = banco()
    tid = titulo(con, origem="MANUAL")
    ate_o_protesto(con, tid)
    assert PR.pendentes(con) == []


def test_os_pendentes_se_agrupam_por_apresentante():
    con = banco()
    ate_o_protesto(con, titulo(con, numero="1/1", apresentante="001"))
    ate_o_protesto(con, titulo(con, numero="2/1", apresentante="001"))
    ate_o_protesto(con, titulo(con, numero="3/1", apresentante="002",
                               nome_apresentante="BRADESCO"))
    grupos = {g["apresentante_codigo"]: g["atos"]
              for g in PR.apresentantes_pendentes(con)}
    assert grupos == {"001": 2, "002": 1}


# ---------------------------------------------------------------- montar


def test_a_ocorrencia_sai_do_ato_e_e_a_medida():
    con = banco()
    tabela_de_custas(con)       # a retirada leva a custa do cartório
    ate_o_protesto(con, titulo(con, numero="1/1"))
    pago = titulo(con, numero="2/1")
    PT.lancar_apontamento(con, pago, sv=SV, agora=AGORA, data_extenso="x")
    PT.lancar_pagamento(con, pago, sv=SV, agora=AGORA, data_extenso="x")
    desistido = titulo(con, numero="3/1")
    PT.lancar_apontamento(con, desistido, sv=SV, agora=AGORA, data_extenso="x")
    PT.lancar_desistencia(con, desistido, motivo="Credor desistiu.",
                          agora=AGORA)
    r = PR.montar(con, apresentante_codigo="001", dia=HOJE, marca="A")
    saiu = {t["ocorrencia"] for t in r["arquivo"].titulos}
    assert saiu == {"C", "1", "3"}          # protesto, pago, retirado


def test_a_retirada_leva_a_custa_do_cartorio_na_posicao_467():
    """A CRA recusou o zero com 2239 (30/10/2026). O caso medido: R$ 418,17 dá
    R$ 118,49 na vigência 10022."""
    con = banco()
    tabela_de_custas(con)
    desistido(con)
    r = PR.montar(con, apresentante_codigo="001", dia=HOJE, marca="A")
    linha = r["conteudo"].splitlines()[1]
    assert len(linha) == 600
    assert linha[457] == "3"
    assert linha[466:476] == "0000011849"
    assert PA.ler(r["conteudo"]).titulos[0]["reservado_467"] == "0000011849"


def test_a_custa_da_retirada_e_a_da_tabela_do_dia_do_ato():
    con = banco()
    tabela_de_custas(con)
    tabela_de_custas(con, vigencia=10021, inicio="2025-01-01", fim="2025-12-31",
                     itens={"17.7": "10,00", "17.2": "10,00", "17.10.1": "20,00",
                            "17.9": "5,00"},
                     faixa=("0,00", "10.000,00", "30,00"))
    desistido(con, agora="2025-12-20T10:00:00")
    # O arquivo sai em 2026 e o ato é de 2025: 40,00 + 5 x 5,00 + 30,00.
    r = PR.montar(con, apresentante_codigo="001", dia=HOJE, marca="A")
    assert r["conteudo"].splitlines()[1][466:476] == "0000009500"


def test_as_outras_ocorrencias_seguem_em_zero_e_nao_pedem_tabela():
    # Sem tabela nenhuma neste banco: nem o pagamento nem o protesto a leem.
    con = banco()
    pago = titulo(con, numero="1/1")
    PT.lancar_apontamento(con, pago, sv=SV, agora=AGORA, data_extenso="x")
    PT.lancar_pagamento(con, pago, sv=SV, agora=AGORA, data_extenso="x")
    ate_o_protesto(con, titulo(con, numero="2/1"))
    r = PR.montar(con, apresentante_codigo="001", dia=HOJE, marca="A")
    linhas = r["conteudo"].splitlines()[1:3]
    assert {x[457] for x in linhas} == {"1", "C"}
    assert [x[466:476] for x in linhas] == ["0000000000"] * 2


def test_retirada_sem_faixa_recusa_com_a_frase_do_balcao_e_nunca_zero():
    con = banco()
    tabela_de_custas(con, faixa=("10.000,01", "20.000,00", "35,85"))
    desistido(con)
    with pytest.raises(PR.RetornoError) as erro:
        PR.montar(con, apresentante_codigo="001", dia=HOJE, marca="A")
    frase = str(erro.value)
    assert "R$ 418,17" in frase and "17.4" in frase and "10022" in frase
    assert "2608250001" in frase, "o balcão precisa saber qual título"


def test_retirada_com_a_tabela_incompleta_recusa():
    con = banco()
    tabela_de_custas(con, itens={"17.7": "11,96", "17.2": "10,68",
                                 "17.10.1": "26,25"})     # falta o 17.9
    desistido(con)
    with pytest.raises(PR.RetornoError, match="incompleta"):
        PR.montar(con, apresentante_codigo="001", dia=HOJE, marca="A")


def test_retirada_sem_tabela_na_instalacao_recusa_e_nao_estoura():
    con = banco()
    desistido(con)
    with pytest.raises(PR.RetornoError, match="tabela de emolumentos"):
        PR.montar(con, apresentante_codigo="001", dia=HOJE, marca="A")


def test_o_gerar_nao_engole_a_recusa_da_custa_nem_grava_metade():
    """`gerar` trata «sem conteúdo» como dia vazio, e o andamento deste título
    está pendente: engolida, a tela diria «gerados» sem o retorno ter saído."""
    con = banco()
    desistido(con)
    with pytest.raises(PR.RetornoError, match="tabela de emolumentos"):
        PR.gerar(con, apresentante_codigo="001", dia=HOJE, agora=AGORA, marca="A")
    assert con.execute("SELECT COUNT(*) FROM pt_retornos").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM pt_atos WHERE retorno_id IS NOT NULL"
                       ).fetchone()[0] == 0


def test_o_andamento_nao_pede_a_tabela_e_nao_trava_a_remessa():
    con = banco()
    desistido(con)
    r = PR.gerar_andamento(con, apresentante_codigo="001", dia=HOJE, agora=AGORA,
                           marca="A")
    assert r["andamento_id"] and r["retorno_id"] is None


def test_o_retorno_leva_so_a_chave_e_o_resultado():
    # Medido nos 383 reais: especie, cedente e devedor sempre em branco.
    con = banco()
    ate_o_protesto(con, titulo(con))
    r = PR.montar(con, apresentante_codigo="001", dia=HOJE, marca="A")
    linha = r["conteudo"].splitlines()[1]
    assert len(linha) == 600
    assert not linha[19:198].strip()        # cedente e devedor em branco
    assert linha[198:213].strip() == "NN9911/1"
    assert linha[447:457] == "2608250001"   # protocolo
    assert linha[457] == "C"                # ocorrência


def test_o_andamento_leva_o_titulo_inteiro():
    # Ele nao tem layout proprio: e o da remessa mais o bloco do retorno.
    con = banco()
    ate_o_protesto(con, titulo(con))
    r = PR.montar(con, apresentante_codigo="001", dia=HOJE, marca="A",
                  tipo="SDTBFOAND")
    linha = r["conteudo"].splitlines()[1]
    assert len(linha) == 600
    assert "LOJA CENTRAL LTDA" in linha[19:64]      # cedente preenchido
    assert "JOSÉ DA SILVA" in linha[297:342]        # devedor preenchido
    assert linha[213:216] == "DMI"                  # espécie
    assert linha[457] == "0"                        # e o bloco do retorno


def test_o_andamento_leva_APONTAMENTO_e_nao_o_ato_final():
    """MEDIDO nos 25 andamentos que esta casa mandou em 2026: **`0` em 103 de
    103 registros**, sem uma excecao. `0` e «Apontamento» no contrato.

    ESTE TESTE AFIRMAVA `C` ATE 31/08/2026, porque o sistema copiava a
    ocorrencia do retorno para o andamento — e o comentario do codigo dizia que
    era «o que se quer». Metade daquilo estava certa: os dois arquivos levam
    quase os mesmos titulos (42 dos 47 aparecem nos dois). A outra metade nao.

    O ESTRAGO QUE ISSO EVITA: um andamento dizendo `C` afirma um PROTESTO que o
    retorno do mesmo dia ja afirmou — a Central registraria o mesmo protesto
    duas vezes, por dois arquivos.
    """
    con = banco()
    ate_o_protesto(con, titulo(con))
    andamento = PR.montar(con, apresentante_codigo="001", dia=HOJE, marca="A",
                          tipo="SDTBFOAND")
    retorno = PR.montar(con, apresentante_codigo="001", dia=HOJE, marca="A",
                        tipo="SDTBFORTP")
    assert andamento["conteudo"].splitlines()[1][457] == "0"
    # E o retorno continua dizendo o que aconteceu.
    assert retorno["conteudo"].splitlines()[1][457] == "C"


def test_sem_apresentante_o_retorno_e_recusado():
    con = banco()
    with pytest.raises(PR.RetornoError) as erro:
        PR.montar(con, apresentante_codigo="", dia=HOJE)
    assert "volta para quem mandou" in str(erro.value)


def test_sem_ato_novo_o_retorno_e_recusado():
    con = banco()
    with pytest.raises(PR.RetornoError) as erro:
        PR.montar(con, apresentante_codigo="001", dia=HOJE, marca="A")
    assert "Não há ato novo" in str(erro.value)


def test_titulo_sem_protocolo_e_recusado_dizendo_o_que_fazer():
    con = banco()
    tid = titulo(con)
    ate_o_protesto(con, tid)
    con.execute("UPDATE pt_titulos SET protocolo=NULL WHERE id=?", (tid,))
    with pytest.raises(PR.RetornoError) as erro:
        PR.montar(con, apresentante_codigo="001", dia=HOJE, marca="A")
    assert "posição 448" in str(erro.value)
    assert "confira o protocolo no livro" in str(erro.value)


def test_apresentante_sem_historico_e_recusado_e_pergunta():
    # A letra da posicao 566 nao se chuta: nos arquivos medidos o empate e
    # exato, 74 «A» contra 74 «P».
    con = banco()
    ate_o_protesto(con, titulo(con, apresentante="ZZZ"))
    with pytest.raises(PA.ArquivoError) as erro:
        PR.montar(con, apresentante_codigo="ZZZ", dia=HOJE)
    assert "posição 566" in str(erro.value)


def test_tipo_de_arquivo_desconhecido_e_recusado():
    con = banco()
    ate_o_protesto(con, titulo(con))
    with pytest.raises(PR.RetornoError) as erro:
        PR.montar(con, apresentante_codigo="001", dia=HOJE, marca="A",
                  tipo="XPTO")
    assert "Tipo de arquivo desconhecido" in str(erro.value)


# ------------------------------------------------------------------ gerar


def test_gerar_produz_o_par_retorno_e_andamento():
    # "SEMPRE QUE GERAR RETORNO (FINAL), GERAR ANDAMENTO" — o roteiro do
    # protesto que o oficial trouxe da serventia em que trabalhou.
    con = banco()
    ate_o_protesto(con, titulo(con))
    r = PR.gerar(con, apresentante_codigo="001", dia=HOJE, agora=AGORA,
                 marca="A", usuario="TABELIÃO")
    gerados = {x["tipo"]: dict(x) for x in PR.listar(con)}
    assert set(gerados) == {"SDTBFORTP", "SDTBFOAND"}
    # Nome FEBRABAN desde 13/10/2026 (era «SDTBFORTP-001-20260825-001.txt»):
    # medido nos 125 arquivos de 2026 da pasta da CRA e exigido por ela.
    assert gerados["SDTBFORTP"]["nome_arquivo"] == "R0012508.261"
    assert gerados["SDTBFOAND"]["nome_arquivo"] == "M0012508.261"
    # Os dois se apontam.
    assert gerados["SDTBFORTP"]["par_id"] == r["andamento_id"]
    assert gerados["SDTBFOAND"]["par_id"] == r["retorno_id"]
    # E CADA UM LEVA OS SEUS ATOS — correção de 31/08/2026.
    #
    # Este comentário dizia «os dois levam os MESMOS títulos», e era o defeito
    # descrito como se fosse a regra: o andamento saía com os atos finais do
    # retorno, dizendo «Apontamento» sobre um título que acabara de ser
    # protestado.
    #
    # O número continua 1 nos dois, e agora por outro motivo: **é o mesmo
    # título em dois atos diferentes** — apontado (vai no andamento) e
    # protestado (vai no retorno).
    assert gerados["SDTBFORTP"]["titulos"] == gerados["SDTBFOAND"]["titulos"] == 1
    atos_ret = {a["tipo"] for a in PR.atos_do_retorno(con, r["retorno_id"])}
    atos_and = {a["tipo"] for a in PR.atos_do_retorno(con, r["andamento_id"])}
    assert atos_ret == {"PROTESTO"}
    assert atos_and == {"APONTAMENTO"}


def test_nada_sai_duas_vezes():
    con = banco()
    ate_o_protesto(con, titulo(con))
    PR.gerar(con, apresentante_codigo="001", dia=HOJE, agora=AGORA, marca="A")
    assert PR.pendentes(con) == []
    with pytest.raises(PR.RetornoError) as erro:
        PR.gerar(con, apresentante_codigo="001", dia=HOJE, agora=AGORA,
                 marca="A")
    # A palavra mudou de «retorno» para «arquivo» em 31/08/2026, porque agora
    # são dois — o retorno e o andamento —, e a recusa vale para os dois.
    assert "já entrou num arquivo anterior" in str(erro.value)


def test_o_arquivo_inteiro_fica_gravado_com_o_hash():
    con = banco()
    ate_o_protesto(con, titulo(con))
    r = PR.gerar(con, apresentante_codigo="001", dia=HOJE, agora=AGORA,
                 marca="A", usuario="TABELIÃO")
    linha = PR.retorno(con, r["retorno_id"])
    assert linha["conteudo"] == r["conteudo"]
    assert linha["hash_arquivo"] == PR.hash_retorno(r["conteudo"])
    assert linha["gerado_por"] == "TABELIÃO"
    assert linha["soma_centavos"] == 131045          # o saldo, não o valor
    atos = PR.atos_do_retorno(con, r["retorno_id"])
    assert [a["tipo"] for a in atos] == ["PROTESTO"]


def test_ato_novo_depois_do_retorno_entra_no_proximo():
    con = banco()
    ate_o_protesto(con, titulo(con, numero="1/1"))
    PR.gerar(con, apresentante_codigo="001", dia=HOJE, agora=AGORA, marca="A")
    ate_o_protesto(con, titulo(con, numero="2/1"))
    assert len(PR.pendentes(con)) == 1
    r = PR.gerar(con, apresentante_codigo="001", dia="2026-08-26",
                 agora=AGORA, marca="A", numero_da_remessa=2)
    assert len(r["atos"]) == 1


def test_titulo_com_dois_devedores_volta_numa_linha_so():
    # Dois devedores = duas linhas da remessa = dois títulos com o MESMO
    # protocolo. Duas linhas no retorno a CRA recusa com 9999 «MESMO
    # PROTOCOLO» (23/10/2026). Vai uma; os dois atos ficam informados.
    con = banco()
    a = titulo(con, numero="7/1")
    b = titulo(con, numero="7/1-B")
    for tid in (a, b):
        con.execute("UPDATE pt_titulos SET protocolo='2608250009' WHERE id=?",
                    (tid,))
        ate_o_protesto(con, tid)
    montado = PR.montar(con, apresentante_codigo="001", dia=HOJE, marca="A")
    lido = PA.ler(montado["conteudo"])
    assert [str(t["protocolo"]) for t in lido.titulos] == ["2608250009"]
    assert lido.rodape["quantidade_de_titulos"] == 1
    assert montado["soma_centavos"] == 131045
    assert len(montado["atos"]) == 2
    PR.gerar(con, apresentante_codigo="001", dia=HOJE, agora=AGORA, marca="A")
    assert PR.pendentes(con) == []


def test_ato_do_mesmo_protocolo_com_outra_ocorrencia_fica_para_o_proximo():
    # 27/10/2026: o corte «uma linha por protocolo» marcava como informado
    # QUALQUER segundo ato do protocolo — um pago e um protestado no mesmo
    # protocolo saíam só com um, e o outro ficava marcado sem ter ido à CRA.
    # O irmão com outra ocorrência não entra no arquivo e continua pendente.
    con = banco()
    a = titulo(con, numero="8/1")
    b = titulo(con, numero="8/1-B")
    for tid in (a, b):
        con.execute("UPDATE pt_titulos SET protocolo='2608250010' WHERE id=?",
                    (tid,))
    ate_o_protesto(con, a)
    PT.lancar_apontamento(con, b, sv=SV, agora=AGORA, data_extenso="x")
    PT.lancar_pagamento(con, b, sv=SV, agora=AGORA, data_extenso="x")
    montado = PR.montar(con, apresentante_codigo="001", dia=HOJE, marca="A")
    assert len(montado["arquivo"].titulos) == 1
    assert len(montado["atos"]) == 1
    assert len(montado["adiados"]) == 1
    primeira = montado["arquivo"].titulos[0]["ocorrencia"]
    PR.gerar(con, apresentante_codigo="001", dia=HOJE, agora=AGORA, marca="A")
    # o outro continua esperando, e sai no arquivo seguinte com a SUA ocorrência
    resto = PR.pendentes(con)
    assert len(resto) == 1
    r = PR.montar(con, apresentante_codigo="001", dia="2026-08-26", marca="A",
                  numero_da_remessa=2)
    segunda = r["arquivo"].titulos[0]["ocorrencia"]
    assert {primeira, segunda} == {"C", "1"}


def test_o_titulo_da_cenprot_e_contado_a_parte_e_nao_vai_a_cra():
    # `pendentes_da_cenprot` tinha uma segunda definição, no estilo do SQLite,
    # que sobrescrevia a desta casa; a conta tem de rodar no banco de hoje.
    con = banco()
    ate_o_protesto(con, titulo(con, numero="5/1", origem="CENPROT"))
    assert PR.pendentes(con) == []
    assert PR.pendentes_da_cenprot(con) == 1
    assert PR.pendentes_da_cenprot(con, apresentante_codigo="001") == 1
    assert PR.pendentes_da_cenprot(con, apresentante_codigo="002") == 0
    with pytest.raises(PR.RetornoError) as erro:
        PR.montar(con, apresentante_codigo="001", dia=HOJE, marca="A")
    assert "XML do CENPROT" in str(erro.value)


# ------------------------------------------------- o ida e volta, de novo


@pytest.mark.parametrize("tipo", ["SDTBFORTP", "SDTBFOAND"])
def test_o_que_a_casa_escreve_a_casa_le_de_volta(tipo):
    # E o teste que ja pegou quatro defeitos neste modulo: o bairro do devedor
    # duas posicoes fora, o rodape contando registros em vez de titulos, a
    # marca `99999999` de sem-vencimento e o campo reservado lido como texto.
    con = banco()
    ate_o_protesto(con, titulo(con, numero="1/1"))
    ate_o_protesto(con, titulo(con, numero="2/1"))
    montado = PR.montar(con, apresentante_codigo="001", dia=HOJE, marca="A",
                        tipo=tipo)
    lido = PA.ler(montado["conteudo"])
    assert lido.tipo == tipo
    assert len(lido.titulos) == 2
    assert lido.rodape["quantidade_de_titulos"] == 2
    assert lido.rodape["soma_dos_valores"] == 131045 * 2
    assert PA.escrever(lido) == montado["conteudo"]


# ------------------- o andamento é o aviso do APONTAMENTO, e sai na remessa


def test_o_andamento_leva_o_APONTAMENTO_e_nao_o_ato_final():
    """Correção do oficial em 31/08/2026: *«sempre que recebe remessa, precisa
    gerar o andamento para atualizar a CRA sobre o andamento»*.

    Medido nos 125 arquivos de 2026: a ocorrência do andamento é `0` em 103 de
    103 linhas, e `0` no contrato da CRA é **«Apontamento»**. Até esta data o
    andamento saía com os atos finais do retorno — dizendo «apontado» sobre um
    título que acabara de ser protestado.
    """
    con = banco()
    ate_o_protesto(con, titulo(con))
    do_retorno = PR.pendentes(con, tipo="SDTBFORTP")
    do_andamento = PR.pendentes(con, tipo="SDTBFOAND")
    assert {a["tipo"] for a in do_retorno} == {"PROTESTO"}
    assert {a["tipo"] for a in do_andamento} == {"APONTAMENTO"}


def test_o_andamento_sai_SOZINHO_ao_receber_a_remessa():
    """O momento em que ele existe para ser mandado é logo depois do
    apontamento — e até 31/08/2026 não havia por onde.

    Medido: **38 dos 39** títulos recebidos por remessa aparecem num
    andamento, e ele vem na data da remessa ou depois em **38 de 38**.
    """
    con = banco()
    tid = titulo(con)
    PT.lancar_apontamento(con, tid, sv=SV, agora=AGORA, data_extenso="x")
    r = PR.gerar_andamento(con, apresentante_codigo="001", dia=HOJE,
                           agora=AGORA, marca="A")
    assert r["andamento_id"]
    assert r["retorno_id"] is None
    gerados = {x["tipo"] for x in PR.listar(con)}
    assert gerados == {"SDTBFOAND"}


def test_o_apontamento_informado_nao_sai_de_novo():
    """A marcação é de CADA arquivo, e agora são atos diferentes: o
    APONTAMENTO é marcado pelo andamento, o PROTESTO pelo retorno. Um não
    marca o outro, e nenhum sai duas vezes."""
    con = banco()
    tid = titulo(con)
    PT.lancar_apontamento(con, tid, sv=SV, agora=AGORA, data_extenso="x")
    PR.gerar_andamento(con, apresentante_codigo="001", dia=HOJE, agora=AGORA,
                       marca="A")
    assert PR.pendentes(con, tipo="SDTBFOAND") == []
    with pytest.raises(PR.RetornoError):
        PR.gerar_andamento(con, apresentante_codigo="001", dia=HOJE,
                           agora=AGORA, marca="A")


def test_um_arquivo_vazio_nao_derruba_o_outro():
    """Há dia em que chega remessa e não se lavra ato final nenhum, e há dia
    em que é o contrário. Recusar os dois porque um está vazio faria o balcão
    deixar de mandar o que tem."""
    con = banco()
    tid = titulo(con)
    PT.lancar_apontamento(con, tid, sv=SV, agora=AGORA, data_extenso="x")
    # Só há apontamento: o retorno não tem o que levar, e o andamento tem.
    r = PR.gerar(con, apresentante_codigo="001", dia=HOJE, agora=AGORA,
                 marca="A")
    assert r["andamento_id"]
    assert r["retorno_id"] is None
    assert "SDTBFORTP" in r["recusas"]


def test_o_andamento_declara_a_ocorrencia_do_contrato():
    """`0` não é número escolhido: é o que o contrato da CRA chama de
    «Apontamento», e o que esta casa mandou em 103 de 103 linhas."""
    import protesto_cra as CRA
    assert PR.OCORRENCIA_DO_ANDAMENTO == "0"
    assert CRA.OCORRENCIAS["0"]["rotulo"] == "Apontamento"


# --------------------------------------- dois balcões gerando ao mesmo tempo
#
# Ressalva da revisão do L038. `montar` lê os pendentes e `nome_do_arquivo`
# conta em `pt_retornos` a sequência do nome — e nada travava. No SQLite a
# escrita era uma por vez; no PostgreSQL, sem a ponte, só espera quem trava com
# a MESMA chave, e o segundo `gerar` lia os mesmos atos e o mesmo `…1`.

CHAVE_DO_NOME = "pt_retornos.nome_arquivo"


def _sem_a_ponte(con, *, autocommit=False):
    """Uma conexão do psycopg no schema do teste, SEM a ponte — como a
    transação vai ficar quando a ponte sair."""
    import psycopg
    pg = psycopg.connect(banco_pg.dsn(), autocommit=autocommit)
    pg.execute(f'SET search_path TO "{con.schema}", public')
    if not autocommit:
        pg.commit()
    return pg


def _assunto_livre(chave: str) -> bool:
    """Outra conexão consegue a trava do assunto agora? Não espera por ela."""
    import psycopg
    with psycopg.connect(banco_pg.dsn(), autocommit=True) as outra:
        return bool(outra.execute(
            "SELECT pg_try_advisory_xact_lock(hashtext(%s))",
            (chave,)).fetchone()[0])


def test_dois_balcoes_gerando_ao_mesmo_tempo_nao_mandam_o_protesto_duas_vezes():
    """O primeiro gerou e ainda não confirmou; o segundo chega no meio. Sem a
    trava, ele saía com o MESMO protesto e o MESMO nome (`R0012508.261`), e a
    Central registraria dois protestos."""
    con = banco()
    # A casa tem `settings` (database.py); sem a ponte não há SAVEPOINT, e a
    # leitura do IBGE numa tabela que falta derrubaria a transação inteira.
    con.execute("CREATE TABLE IF NOT EXISTS settings "
                "(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    ate_o_protesto(con, titulo(con))
    con.commit()
    um, dois = _sem_a_ponte(con), _sem_a_ponte(con)
    vigia = _sem_a_ponte(con, autocommit=True)
    pid = dois.execute("SELECT pg_backend_pid()").fetchone()[0]
    dois.rollback()
    PR.gerar(um, apresentante_codigo="001", dia=HOJE, agora=AGORA, marca="A")
    saida: dict = {}

    def segundo():
        try:
            saida["r"] = PR.gerar(dois, apresentante_codigo="001", dia=HOJE,
                                  agora=AGORA, marca="A")
            dois.commit()
        except Exception as erro:  # o teste confere qual
            saida["erro"] = erro
            dois.rollback()

    fio = threading.Thread(target=segundo)
    fio.start()
    for _ in range(200):       # o segundo tem de estar ESPERANDO (ou já ter ido)
        if not fio.is_alive() or vigia.execute(
                "SELECT count(*) FROM pg_locks WHERE pid=%s AND NOT granted",
                (pid,)).fetchone()[0]:
            break
        time.sleep(0.05)
    um.commit()
    fio.join(30)
    for c in (um, dois, vigia):
        c.close()
    assert not fio.is_alive(), "o segundo balcão ficou preso"
    assert isinstance(saida.get("erro"), PR.RetornoError), saida
    assert "já entrou num arquivo anterior" in str(saida["erro"])
    assert sorted(x["nome_arquivo"] for x in PR.listar(con)) \
        == ["M0012508.261", "R0012508.261"]


def test_gerar_e_a_virada_leem_ja_com_a_trava_do_nome(monkeypatch):
    """A trava tem de estar pega ANTES de ler: quem trava depois de ler a
    lista já leu o que o outro balcão está gravando. E a virada
    (`marcar_o_que_o_eoficio_ja_informou`) marca os mesmos atos que `gerar` e
    confere a linha dela antes de inserir — a chave é a mesma."""
    import bd_nativo
    from datetime import date
    livres: list[bool] = []

    class Espiao(bd_nativo.Banco):
        def _rodar(self, sql, parametros=None):
            if "FROM pt_atos" in sql or "FROM pt_retornos" in sql:
                livres.append(_assunto_livre(CHAVE_DO_NOME))
            return super()._rodar(sql, parametros)

    monkeypatch.setattr(PR, "banco", Espiao)
    con = banco()
    ate_o_protesto(con, titulo(con, numero="1/1"))
    PR.gerar(con, apresentante_codigo="001", dia=HOJE, agora=AGORA, marca="A")
    assert livres and not any(livres), f"gerar leu sem a trava: {livres}"
    con.commit()

    livres.clear()
    ate_o_protesto(con, titulo(con, numero="2/1"))
    con.execute("UPDATE pt_atos SET origem='EOFICIO' WHERE retorno_id IS NULL")
    prot = con.execute("SELECT protocolo FROM pt_titulos "
                       "WHERE numero_titulo='2/1'").fetchone()[0]
    fluxo = {"retorno": {prot: [{"ocorrencia": "C",
                                 "enviado": date(2026, 8, 1)}]},
             "respondido": set()}
    contagem = PR.marcar_o_que_o_eoficio_ja_informou(con, fluxo, agora=AGORA)
    assert contagem["retorno"] == 1
    assert livres and not any(livres), f"a virada leu sem a trava: {livres}"
