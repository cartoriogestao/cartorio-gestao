"""«NÃO CONSTA» na certidão de nascimento — decisão do oficial, 17/11/2026.

O livro de papel antigo não diz hora, DNV, CPF nem, às vezes, os avós. A
certidão física diz que não consta, em vez de «ND» ou da caixa em branco.
"""
import rc_certidao as RCE
import rc_certidao_quadro as Q


def test_a_constante_e_nao_consta():
    assert RCE.SEM_DADO == "NÃO CONSTA"
    assert RCE._linha("HORA", "") == ["HORA", "NÃO CONSTA"]
    assert RCE._linha("HORA", "08:15") == ["HORA", "08:15"]


def test_as_celulas_vazias_dizem_nao_consta():
    q = {"hora": "", "naturalidade": "Cidade Exemplo", "local_nascimento": "",
         "municipio_nascimento": "", "sexo": "MASCULINO", "dnv": "", "cpf": "",
         "avos_maternos": "", "avos_paternos": "JOSÉ e MARIA", "gemeo": "",
         "genitores": [{"nome": "ANA", "municipio": "", "uf": "", "avos": ""}]}
    Q._nao_consta_no_nascimento(q)
    for celula in ("hora", "local_nascimento", "municipio_nascimento", "dnv",
                   "cpf", "avos_maternos"):
        assert q[celula] == "NÃO CONSTA", celula
    assert q["naturalidade"] == "Cidade Exemplo"
    assert q["avos_paternos"] == "JOSÉ e MARIA"
    assert q["gemeo"] == ""  # vazio é «não é gêmeo»
    assert q["genitores"][0]["avos"] == "NÃO CONSTA"
    assert q["genitores"][0]["municipio"] == "NÃO CONSTA"


def test_o_municipio_fica_em_branco_quando_o_local_ja_traz_a_cidade():
    q = {"local_nascimento": "Hospital X, Cidade Exemplo/MA",
         "municipio_nascimento": ""}
    Q._nao_consta_no_nascimento(q)
    assert q["municipio_nascimento"] == ""
