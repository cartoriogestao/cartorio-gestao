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
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import protesto as PT
import protesto_arquivo as PA
import protesto_retorno as PR
from nucleo_schema import init_nucleo_schema
from pt_schema import init_pt_schema

AGORA = "2026-08-25T10:00:00"
HOJE = "2026-08-25"
SV = {"unit_name": "SERVENTIA EXTRAJUDICIAL DE CIDADE EXEMPLO",
      "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
      "serventia_titulo": "Tabelião e Oficial de Registro",
      "ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA"}


def banco() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    init_nucleo_schema(con)
    init_pt_schema(con)
    return con


def titulo(con, *, numero="9911/1", apresentante="001",
           nome_apresentante="BANCO DO BRASIL", origem="CRA") -> int:
    dados = {
        "apresentante_codigo": apresentante,
        "apresentante_nome": nome_apresentante,
        "especie": "DMI", "numero_titulo": numero,
        "nosso_numero": f"NN{numero}",
        "data_emissao": "2026-01-05", "data_vencimento": "2026-02-05",
        "valor": "1.200,00", "saldo": "1.310,45",
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
    PT.lancar_protesto(con, titulo_id, sv=SV, agora=AGORA, data_extenso="x")


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
