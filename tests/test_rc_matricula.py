"""A matricula de 32 digitos.

O QUE ESTES TESTES GUARDAM
    **O caso do Anexo IV, com o resultado que a NORMA publica.** Se alguem
    mexer no calculo, e este caso continuar verde, mexeu certo. Nao e um caso
    inventado por mim: e o exemplo trabalhado do manual da CRC.

    **Os assentos REAIS desta casa.** A formula foi conferida contra 255 casos
    e acertou 255 — inclusive um em que o acervo estava errado e ela estava
    certa. O teste guarda uma amostra medida, com o DV que o servico oficial da
    ARPEN confirmou.

    **Que o varredor nao conserta nada.** A matricula ja pode ter saido em
    certidao e ido para a CRC e o SIRC; trocar o numero no banco calaria o
    problema sem resolver nenhuma dessas pontas.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import rc_matricula as M                                       # noqa: E402


# O EXEMPLO DO ANEXO IV DO MANUAL DA CRC, com a conta que ele publica:
#   somatoria fase 1 = 15010 -> /11 -> resto 6 -> D1 = 6
#   somatoria fase 2 = 16010 -> /11 -> resto 5 -> D2 = 5
DO_ANEXO_IV = "001883" "01" "55" "1987" "1" "00018" "050" "0000566"
DV_DO_ANEXO_IV = "65"

# Casos REAIS desta serventia, com o CNS trocado pelo fictício 000000 e o
# dígito refeito pela conta (sanitização B3, 10/10/2026). Os originais — que
# o serviço da ARPEN-SP confirmou — ficam no acervo da casa, e não no repositório.
REAIS = [
    ("000000" "01" "55" "2026" "4" "00005" "277" "0001978", "51"),
    ("000000" "01" "55" "2022" "1" "00022" "291" "0019068", "08"),
    ("000000" "01" "55" "1988" "1" "00006" "191" "0006846", "36"),
    ("000000" "01" "55" "2022" "1" "00023" "057" "0019132", "22"),
]


def test_o_exemplo_da_norma():
    """Se este cair, o calculo deixou de ser o da norma — e nao adianta
    discutir com o resto da suite antes de consertar este."""
    assert M.digito_verificador(DO_ANEXO_IV) == DV_DO_ANEXO_IV


def test_os_casos_reais_desta_casa():
    for base, dv in REAIS:
        assert M.digito_verificador(base) == dv, f"base {base}"


def test_a_soma_e_multiplicada_por_dez():
    """O «vezes 10» do Anexo IV nao e enfeite: sem ele o numero e outro.

    Este teste existe porque o passo e estranho o suficiente para alguem
    «limpar» no futuro achando que sobra.
    """
    digitos = DO_ANEXO_IV
    sem_o_dez = sum(int(d) * p for d, p in zip(digitos, range(31, 1, -1))) % 11
    com_o_dez = M._fase(digitos, 31)
    assert com_o_dez == 6
    assert sem_o_dez != com_o_dez, (
        "se tirar o «vezes 10» der o mesmo, este caso nao prova nada — "
        "troque por outro que prove")


def test_a_segunda_fase_usa_o_primeiro_digito():
    """Calcular as duas fases sobre a mesma base daria outro numero, calado."""
    d1 = M._fase(DO_ANEXO_IV, 31)
    certo = M._fase(DO_ANEXO_IV + str(d1), 32)
    errado = M._fase(DO_ANEXO_IV, 32)
    assert certo == 5
    assert certo != errado


def test_resto_dez_vira_um():
    """A letra do Anexo IV: «Se o resto for 10, entao o digito sera 1»."""
    achou = False
    for termo in range(1, 400):
        base = "000000" "01" "55" "2026" "4" "00005" "277" f"{termo:07d}"
        soma = sum(int(d) * p for d, p in zip(base, range(31, 1, -1)))
        if (soma * 10) % 11 == 10:
            achou = True
            assert M.digito_verificador(base)[0] == "1"
    assert achou, "nenhum caso deu resto 10 — o teste nao provou nada"


# ------------------------------------------------------------- compor


def test_compor_preenche_com_zeros_a_esquerda():
    """Folha 57 e `057`. Encaixar a direita daria outro numero com 32 digitos
    — e numero errado do tamanho certo passa em conferencia de formato."""
    m = M.compor(cns="0", ano=2022, livro_tipo="1", livro=23, folha=57,
                 termo=19132)
    assert m == "000000" "01" "55" "2022" "1" "00023" "057" "0019132" "22"


def test_compor_do_assento():
    a = {"especie": "NASCIMENTO", "data_ato": "2022-12-12", "livro": "23",
         "folha": "57", "numero": 19132}
    assert M.compor_do_assento(a, cns="000000").endswith("22")


def test_compor_recusa_campo_que_nao_cabe():
    with pytest.raises(M.MatriculaError) as e:
        M.compor(cns="000000", ano=2026, livro_tipo="1", livro=23,
                 folha=1234, termo=1)
    assert "folha" in str(e.value).lower()


def test_compor_recusa_tipo_de_livro_que_nao_existe():
    with pytest.raises(M.MatriculaError) as e:
        M.compor(cns="000000", ano=2026, livro_tipo="9", livro=1, folha=1,
                 termo=1)
    assert "Livro A" in str(e.value), "a recusa tem de dizer quais existem"


def test_a_especie_sem_livro_recusa_dizendo_as_que_sabe():
    with pytest.raises(M.MatriculaError) as e:
        M.compor_do_assento({"especie": "INVENTADA", "data_ato": "2026-01-01"},
                            cns="000000")
    assert "NASCIMENTO" in str(e.value)


# ------------------------------------------------------------- conferir


def test_confere_aceita_a_certa_e_recusa_a_errada():
    certa = DO_ANEXO_IV + DV_DO_ANEXO_IV
    assert M.confere(certa)["ok"] is True
    errada = DO_ANEXO_IV + "00"
    r = M.confere(errada)
    assert r["ok"] is False
    assert r["esperado"] == "65" and r["achado"] == "00"
    assert "65" in r["motivo"]


def test_confere_nao_levanta_erro_com_matricula_errada():
    """Matricula errada e fato do acervo, nao excecao de programa: quebrar a
    tela esconderia justamente o que o escrevente precisa ver."""
    for ruim in ("", "123", None, "x" * 32, DO_ANEXO_IV + "99"):
        r = M.confere(ruim)
        assert r["ok"] is False
        assert r["motivo"], f"recusou «{ruim}» sem dizer por que"


def test_partes_abre_a_matricula_e_nomeia_o_livro():
    p = M.partes(DO_ANEXO_IV + DV_DO_ANEXO_IV)
    assert p["cns"] == "001883"
    assert p["ano"] == "1987"
    assert p["livro"] == "00018"
    assert p["folha"] == "050"
    assert p["termo"] == "0000566"
    assert p["dv"] == "65"
    assert p["livro_nome"] == "A" and "nascimento" in p["livro_e"]


def test_a_tabela_de_livros_tem_os_sete():
    """Eram seis ate 03/09/2026; o Livro D entrou com o e-Proclamas.

    O teste dizia «os seis da norma» e o conjunto nao tinha o `6` — o buraco
    entre o 5 (C-Auxiliar) e o 7 (E). Ele nao era esquecimento: o guia do SIRC,
    que deu a tabela, **nao trata de proclamas**.
    """
    assert set(M.TIPOS_DE_LIVRO) == {"1", "2", "3", "4", "5", "6", "7"}
    assert M.TIPOS_DE_LIVRO["4"]["livro"] == "C"
    assert M.TIPOS_DE_LIVRO["5"]["e"] == "natimorto"
    assert M.TIPOS_DE_LIVRO["6"]["livro"] == "D"
    assert M.TIPOS_DE_LIVRO["6"]["e"] == "proclamas"


def test_todo_tipo_de_livro_declara_de_onde_veio():
    """Procedencia nao e enfeite: ela diz o que se pode afirmar.

    E a regra do envelope do selo do civil (`MEDIDO` / `TABELA`) aplicada
    aqui. Tipo de livro que entrasse sem fonte seria numero sem procedencia
    dentro da identidade nacional da certidao.
    """
    for chave, livro in M.TIPOS_DE_LIVRO.items():
        assert livro.get("fonte"), f"o tipo {chave} nao diz de onde veio"
        assert M.procedencia_do_livro(chave) == livro["fonte"]


def test_o_livro_D_declara_que_a_fonte_dele_e_mais_fraca():
    """O `6` veio de um EXEMPLO de contrato, e nao do guia do SIRC.

    Se um dia alguem medir o digito do Livro D numa fonte melhor — a norma, ou
    uma matricula real de proclama desta casa —, este teste fica vermelho e
    obriga a trocar a procedencia junto. **Fonte que melhora sem alguem
    reparar e procedencia que envelhece.**
    """
    assert M.TIPOS_DE_LIVRO["6"]["fonte"] == M.EXEMPLO_DO_EPROCLAMAS
    assert "e-Proclamas" in M.EXEMPLO_DO_EPROCLAMAS
    # E as outras seis NAO saem daquele exemplo.
    outras = [k for k in M.TIPOS_DE_LIVRO if k != "6"]
    assert all(M.TIPOS_DE_LIVRO[k]["fonte"] != M.EXEMPLO_DO_EPROCLAMAS
               for k in outras)


def test_o_exemplo_do_contrato_e_fabricado_e_isso_fica_dito():
    """O exemplo NAO prova a conta — so a posicao. Medido.

    O CNS dele e `111111`, que nao existe, e o digito nao confere com o Anexo
    IV. Quem o tomasse por matricula real concluiria que a regra do digito
    esta errada.
    """
    exemplo = "11111101552025600001102000001541"
    assert M.partes(exemplo)["livro_tipo"] == "6"
    assert M.confere(exemplo)["ok"] is False


def test_a_especie_proclamas_compoe_matricula():
    """Sem isto o envio ao e-Proclamas nao teria como se identificar."""
    assert M.LIVRO_DA_ESPECIE["PROCLAMAS"] == "6"
    m = M.compor(cns="000000", ano="2026", livro_tipo="6", livro="1",
                 folha="7", termo="1")
    assert len(m) == M.TAMANHO
    assert M.confere(m)["ok"] is True
    assert M.partes(m)["livro_nome"] == "D"


def test_explicar_diz_campo_a_campo():
    """32 digitos seguidos nao se conferem a olho."""
    linhas = M.explicar(DO_ANEXO_IV + DV_DO_ANEXO_IV)
    junto = "\n".join(linhas)
    assert "Livro A" in junto and "confere" in junto
    assert len(linhas) == len(M.CAMPOS) + 1


# ------------------------------------------------------------- o varredor


def _banco() -> sqlite3.Connection:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    con.execute("CREATE TABLE rc_assentos (id INTEGER PRIMARY KEY, "
                "especie TEXT, numero INTEGER, nome TEXT, data_ato TEXT, "
                "matricula TEXT, origem TEXT)")
    con.execute("INSERT INTO rc_assentos VALUES (1,'NASCIMENTO',566,'FULANO',"
                "'1987-01-01',?,'EOFICIO')", (DO_ANEXO_IV + DV_DO_ANEXO_IV,))
    con.execute("INSERT INTO rc_assentos VALUES (2,'NASCIMENTO',19132,'BELTRANO',"
                "'2022-12-12',?,'EOFICIO')",
                ("000000" "01" "55" "2022" "1" "00023" "057" "0019132" "55",))
    con.execute("INSERT INTO rc_assentos VALUES (3,'OBITO',1,'SICRANO',"
                "'2026-01-01','','MANUAL')")
    con.commit()
    return con


def test_o_varredor_acha_so_a_errada():
    con = _banco()
    achados = M.matriculas_com_digito_errado(con)
    assert [a["id"] for a in achados] == [2]
    assert achados[0]["esperado"] == "22" and achados[0]["achado"] == "55"
    con.close()


def test_o_varredor_nao_conserta_nada():
    """A matricula ja pode ter ido para a CRC e o SIRC com o numero errado.
    Trocar no banco calaria o problema sem resolver nenhuma dessas pontas."""
    con = _banco()
    antes = con.execute("SELECT matricula FROM rc_assentos "
                        "WHERE id=2").fetchone()[0]
    M.matriculas_com_digito_errado(con)
    depois = con.execute("SELECT matricula FROM rc_assentos "
                         "WHERE id=2").fetchone()[0]
    assert antes == depois
    con.close()

    codigo = (RAIZ / "rc_matricula.py").read_text(encoding="utf-8")
    for proibido in ("UPDATE ", "INSERT INTO", "DELETE FROM"):
        assert proibido not in codigo, f"o modulo escreve com «{proibido}»"


def test_quantas_sem_matricula():
    con = _banco()
    assert M.quantas_sem_matricula(con) == 1
    con.close()


def test_a_fonte_da_regra_esta_dita_no_modulo():
    """Regra sem endereco vira lenda: daqui a um ano ninguem sabe de onde saiu
    o «vezes 10», e o primeiro que achar estranho vai tirar."""
    assert "Anexo IV" in M.FONTE and "CRC" in M.FONTE


def test_a_ficha_do_assento_nao_diz_que_o_sistema_nao_gera_a_matricula():
    """Ela se compõe ao lavrar desde 03/09/2026, e a tela continuou dizendo o contrário."""
    ficha = (RAIZ / "templates" / "atrib_rcpn_ficha.html").read_text(
        encoding="utf-8-sig")
    corrido = " ".join(ficha.split())
    assert "não gera nem valida" not in corrido
    assert "não foi decifrado" not in corrido
    assert "o sistema a compõe" in corrido
