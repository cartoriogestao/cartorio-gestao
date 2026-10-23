"""CERTIDAO DE INTEIRO TEOR COM O ATO EM DOBRO — HOTFIX SANDBOX-2026-10-19-02.

    Certidao 70/2026, matricula 9.001 (19/10/2026, pedido do balcao): saiu com DOIS
    R-01 — o da transcricao da ficha (teor da matricula, substituido em
    06/10/2026 pela transcricao da digitalizacao) e, depois do teor, o R-01
    do E-Oficio (`ri_atos` 3060), com as letras diferentes.

    `atos_fora_do_teor` so reconhecia o ato escrito com o TEXTO INTEIRO igual.
    A transcricao quebra pagina no meio do ato, escreve o rotulo com o CNM e
    leva a linha de assinatura — e o ato saia de novo. Medido na producao:
    1.078 atos em 391 matriculas.

NA BRANCH DO POSTGRESQL (LX23a)
    Os testes sao os do servidor, com duas trocas que so mudam o BANCO, e nao
    o que se prova: a linha com nome vem da ponte (`banco_pg.Linha`, que faz
    o papel da linha do SQLite) e o piso le uma ficha gravada no PostgreSQL de
    teste (`conexao_de_teste`), porque o modulo ja e nativo e nao roda num
    banco em memoria.

OS DADOS DO ATO SAO FICTICIOS (LH02, 21/10/2026)
    A primeira versao trouxe do servidor os nomes das partes, do imovel, da
    substituta e da atendente, o selo, a cidade, o CNS e a matricula reais. O
    servidor os mascarou na exportacao de 21/10; aqui viraram exemplo, de
    forma coerente (matricula 9.001 com o CNS 000000 dentro do CNM), e o que
    se prova nao muda.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

import ri_numeros_do_teor as NUMT  # noqa: E402
from banco_de_teste import conexao_de_teste  # noqa: E402
from banco_pg import Linha  # noqa: E402
from bd_nativo import banco  # noqa: E402

MAT = {"numero": "9001", "cnm": "000000.2.0009001-76"}

CORPO = ("Pela Escritura Publica de compra e venda lavrada no dia 16 de Julho de "
         "2020, no Livro 028 NOTAS, Folhas 19/021, a ASSOCIACAO DOS PEQUENOS "
         "PRODUTORES RURAIS DA LOCALIDADE EXEMPLO, neste ato representada por "
         "seus Dirigentes, VENDEU o imovel desta matricula, pelo preco de vinte "
         "mil reais, a FULANO DE EXEMPLO e BELTRANA DE EXEMPLO, "
         "lavradores, residentes na Chacara Exemplo, zona rural de Montes "
         "Altos/MA. Comprovante de recolhimento do ITBI de 03/07/2020. O "
         "referido e verdade e dou fe. A Tabelia Substituta Fulana de Exemplo.")
METADE = len(CORPO) // 2

# O teor da ficha: a TRANSCRICAO, com o rotulo pelo CNM e quebra de pagina.
TEOR_TRANSCRITO = (
    "<p>MATRICULA 9.001 - IMOVEL: Chacara Exemplo, 22,2933 ha.</p>"
    "<p>R-01/000000.2.0009001-76 (COMPRA E VENDA). Cidade Exemplo - MA, 16 de "
    "Julho de 2020. " + CORPO[:METADE] + "</p>"
    "<p><em>[Ficha - Matricula 9.001 - pagina 3 de 4]</em></p><p>[rubrica]</p>"
    "<p>" + CORPO[METADE:] + "</p>"
    "<p>R.02/000000.2.0009001-76- Data: 11 de novembro de 2025. Registro de "
    "garantia em favor do banco.</p>")

# O ato do E-Oficio: o mesmo R-01, com o rotulo ERRADO (9.002) e sem a quebra.
ATO_EOFICIO = {"id": 3060, "tipo": "R", "numero": 1, "selo_texto": None,
               "teor": ("<p>R-01/9.002 (COMPRA E VENDA). Cidade Exemplo - MA, 16 "
                        "de Julho de 2020. " + CORPO.replace(
                            "Tabelia Substituta",
                            "Tabelia Substituta ________________") + "</p>")}


def test_o_R01_transcrito_nao_sai_duas_vezes_na_certidao():
    """O caso da 9.001: com a matricula, o ato transcrito fica de fora."""
    assert not NUMT.texto_escrito_no_teor(TEOR_TRANSCRITO, ATO_EOFICIO["teor"]), (
        "premissa: as letras NAO batem uma a uma — era por isso que saia em dobro")
    fora = NUMT.atos_fora_do_teor(TEOR_TRANSCRITO, [ATO_EOFICIO], matricula=MAT)
    assert fora == [], "o R-01 ja transcrito no teor saiu de novo depois dele"


def test_sem_a_matricula_a_regra_e_a_de_sempre():
    fora = NUMT.atos_fora_do_teor(TEOR_TRANSCRITO, [ATO_EOFICIO])
    assert len(fora) == 1


def test_o_ato_posterior_que_o_teor_nao_conta_continua_saindo():
    """O R-3 lavrado depois da transcricao nao tem cabeca no teor: sai."""
    novo = {"id": 9, "tipo": "R", "numero": 3, "selo_texto": None,
            "teor": "R-03/9.001 - " + CORPO}
    fora = NUMT.atos_fora_do_teor(TEOR_TRANSCRITO, [novo], matricula=MAT)
    assert fora == [novo]


def test_rotulo_citado_no_meio_da_frase_nao_conta():
    """A licao da matricula 11: o R-1 cita AV-2 no meio do texto."""
    teor = ("<p>IMOVEL: Chacara. Conforme a AV-2/9.001, ja averbada, "
            "o imovel e rural.</p>")
    av2 = {"id": 10, "tipo": "AV", "numero": 2, "selo_texto": None,
           "teor": "AV-2/9.001 - " + CORPO}
    assert NUMT.atos_fora_do_teor(teor, [av2], matricula=MAT) == [av2]


def test_cabeca_igual_e_texto_diferente_continua_saindo():
    """Medido: o ato 2.962 da 3.138 esta gravado como R-1 e o texto e outro.
    Rotulo sozinho nao esconde ato."""
    outro = {"id": 11, "tipo": "R", "numero": 1, "selo_texto": None,
             "teor": ("R-1/9.001 - Pela Cedula de Credito Bancario numero 81, "
                      "com vencimento final previsto para 29 de junho de 2030, "
                      "no valor de cento e cinquenta e nove mil reais, o "
                      "imovel foi dado em hipoteca cedular de primeiro grau.")}
    assert NUMT.atos_fora_do_teor(TEOR_TRANSCRITO, [outro], matricula=MAT) == [outro]


def test_ato_com_selo_nunca_e_escondido_pela_cabeca():
    selado = dict(ATO_EOFICIO, selo_texto="REGAVD0000002TESTE0000000001")
    assert NUMT.atos_fora_do_teor(TEOR_TRANSCRITO, [selado],
                                  matricula=MAT) == [selado]


def test_aceita_a_linha_com_nome_da_ponte():
    """A rota tambem pode entregar a linha que nao e `dict` — a `Linha` da
    ponte, que se comporta como a linha com nome do SQLite do servidor."""
    m = Linha(["numero", "cnm"], ["9001", "000000.2.0009001-76"])
    assert NUMT.atos_fora_do_teor(TEOR_TRANSCRITO, [ATO_EOFICIO], matricula=m) == []


def test_o_rotulo_com_o_CNM_conta_para_o_piso_da_numeracao():
    """Na 9.001 o piso dizia «proximo: 2» com o R.02 escrito na ficha."""
    citados = NUMT.citados_no_teor("9001", TEOR_TRANSCRITO, "000000.2.0009001-76")
    assert [c["rotulo"] for c in citados] == ["R-1", "R-2"]
    assert NUMT.citados_no_teor("9001", TEOR_TRANSCRITO) == []  # sem CNM: como antes
    assert NUMT.citados_no_teor("9002", TEOR_TRANSCRITO, "000000.2.0009002-57") == []


def test_o_piso_le_o_CNM_da_ficha():
    con = conexao_de_teste()
    try:
        bd = banco(con)
        bd.escrever("CREATE TABLE ri_matriculas (id bigint PRIMARY KEY, "
                    "numero text, cnm text, livro text, teor text)")
        bd.escrever("CREATE TABLE ri_atos (id bigint PRIMARY KEY, "
                    "matricula_id bigint, numero bigint)")
        bd.escrever("INSERT INTO ri_matriculas VALUES (1, '9001', %s, '2S', %s)",
                    (MAT["cnm"], TEOR_TRANSCRITO))
        bd.escrever("INSERT INTO ri_atos VALUES (1, 1, 1)")
        piso = NUMT.piso_do_proximo(con, 1)
        assert piso["proximo"] == 3 and piso["divergente"]
        assert NUMT.ja_usado_na_ficha(con, 1, 2)["rotulo"] == "R-2"
    finally:
        con.close()


def test_as_duas_chamadas_do_ri_web_passam_a_matricula():
    codigo = (RAIZ / "ri_web.py").read_text(encoding="utf-8")
    assert codigo.count('NUMT.atos_fora_do_teor(m["teor"], atos, matricula=m)') == 2
    assert 'NUMT.atos_fora_do_teor(m["teor"], atos)' not in codigo
