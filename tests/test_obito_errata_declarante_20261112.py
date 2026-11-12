"""Óbito: a errata da DO, a página «dados do declarante» e o falecido achado
fora da DO — 12/11/2026 (hotfix de produção; Robô Óbito RCPN ignorou 11 folhas
da leitura: errata e declaração viravam OUTRO, eram lidas, pagas e descartadas).

Só calcula, sem rede. Dados FICTÍCIOS.
"""
from __future__ import annotations

import rc_leitura_documentos as LEIT

CPF_FALECIDO = "00000000191"
CPF_DECLARANTE = "12345678909"


def _doc(tipo, dados, n=1, arquivo="docs.pdf"):
    return {"arquivo": arquivo, "n": n, "attachment_id": None, "tipo": tipo, "dados": dados}


DO = {
    "numero_do": "12345678-0", "nome_falecido": "Alberto Quase Illegivel",
    "nome_pai": "Pai Lido Torto", "nome_mae": "Mae Lida Torta",
    "data_obito": "10/09/2026", "hora_obito": "03:20", "sexo": "Masculino",
    "data_nascimento": "01/01/1950", "idade": "76", "estado_civil": "Viúvo",
    "causa_a": "Insuficiência respiratória", "tipo_morte": "Natural",
}
RG = {"pessoas": [
    {"tipo_documento": "RG", "nome": "ULISSES EXEMPLO DA SILVA", "cpf": CPF_FALECIDO,
     "data_nascimento": "01/01/1950", "filiacao_pai": "JOAO EXEMPLO DA SILVA",
     "filiacao_mae": "MARIA EXEMPLA DA SILVA"},
]}
CERT_NASC = {"especie": "Nascimento", "nomes": ["ULISSES EXEMPLO DA SILVA"],
             "pai": "JOAO EXEMPLO DA SILVA", "mae": "MARIA EXEMPLA DA SILVA",
             "data_nascimento": "01/01/1950"}
ERRATA = {"numero_do": "12345678-0", "nome_falecido": "Ulisses Exemplo da Silva",
          "secao": "Data", "item": "Data do óbito",
          "onde_le_se": "10/09/2026", "leia_se": "11/09/2026",
          "responsavel": "Fulana Teste", "cargo": "Diretora", "data_da_errata": "12/09/2026"}
DECLARANTE = {"nome": "Beltrana Declarante de Teste", "cpf": CPF_DECLARANTE,
              "rg": "999", "telefone": "99 99999-9999"}


def test_tipos_novos_existem_com_moldes_de_campos_fixos():
    assert {"ERRATA", "DECLARANTE"} <= set(LEIT.TIPOS)
    assert "onde_le_se" in LEIT.TIPOS["ERRATA"]["campos"]
    assert "ERRATA" in LEIT.INSTRUCAO_TRIAGEM and "DECLARANTE" in LEIT.INSTRUCAO_TRIAGEM


def test_a_errata_corrige_a_data_do_obito_e_diz_o_que_fez():
    junto = LEIT.juntar_obito([_doc("DO", DO), _doc("ERRATA", ERRATA, 2)])
    assert junto["valores"]["data_fato"] == "2026-09-11"
    textos = " | ".join(a["texto"] for a in junto["conferencia"])
    assert "A errata da DO corrige a data" in textos


def test_a_errata_lida_como_outro_tambem_vale_pela_propria_transcricao():
    """Leituras gravadas antes dos moldes novos: a triagem chamou de OUTRO."""
    velha = {"tipo_do_documento": "Errata da Declaração de Óbito",
             "onde lê-se": "10/09/2026", "leia-se": "11/09/2026",
             "numero da declaração de óbito": "12345678-0"}
    junto = LEIT.juntar_obito([_doc("DO", DO), _doc("OUTRO", velha, 2)])
    assert junto["valores"]["data_fato"] == "2026-09-11"


def test_errata_de_outra_do_nao_corrige_esta():
    outra = dict(ERRATA, numero_do="99999999-9")
    junto = LEIT.juntar_obito([_doc("DO", DO), _doc("ERRATA", outra, 2)])
    assert junto["valores"]["data_fato"] == "2026-09-10"


def test_do_manuscrita_que_nao_confere_acha_o_falecido_pela_certidao_e_pela_errata():
    """A DO foi lida com nome que não se parece com o de nenhum documento: o RG
    não pode ser ignorado, e a filiação vem da certidão, não da DO torta."""
    junto = LEIT.juntar_obito([
        _doc("DO", DO), _doc("IDENTIDADE", RG, 2),
        _doc("CERTIDAO", CERT_NASC, 3), _doc("ERRATA", ERRATA, 4)])
    por_papel = {p["papel"]: p for p in junto["pessoas"]}
    assert por_papel["FALECIDO"]["nome"].upper() == "ULISSES EXEMPLO DA SILVA"
    assert por_papel["PAI"]["nome"].upper() == "JOAO EXEMPLO DA SILVA"
    assert por_papel["MAE"]["nome"].upper() == "MARIA EXEMPLA DA SILVA"
    textos = " | ".join(a["texto"] for a in junto["conferencia"])
    assert "não se parece com o de nenhum documento" in textos
    assert "e não da DO" in textos


def test_a_pagina_do_declarante_diz_quem_declarou():
    rg_decl = {"pessoas": RG["pessoas"] + [
        {"tipo_documento": "RG", "nome": "BELTRANA DECLARANTE DE TESTE",
         "cpf": CPF_DECLARANTE, "data_nascimento": "02/02/1980"}]}
    do = dict(DO, nome_falecido="Ulisses Exemplo da Silva")
    junto = LEIT.juntar_obito([
        _doc("DO", do), _doc("IDENTIDADE", rg_decl, 2),
        _doc("DECLARANTE", DECLARANTE, 3)])
    decl = [p for p in junto["pessoas"] if p["papel"] == "DECLARANTE"]
    assert len(decl) == 1 and decl[0]["nome"].upper() == "BELTRANA DECLARANTE DE TESTE"
    assert "é o declarante, pelo formulário" in " | ".join(
        a["texto"] for a in junto["conferencia"])


def test_declarante_sem_documento_entra_pelo_cpf_da_pagina():
    do = dict(DO, nome_falecido="Ulisses Exemplo da Silva")
    junto = LEIT.juntar_obito([_doc("DO", do), _doc("IDENTIDADE", RG, 2),
                               _doc("DECLARANTE", DECLARANTE, 3)])
    decl = [p for p in junto["pessoas"] if p["papel"] == "DECLARANTE"][0]
    assert decl["nome"] == "Beltrana Declarante de Teste"
    assert decl["documento_tipo"] == "CPF" and decl["documento_numero"] == CPF_DECLARANTE


def test_sem_errata_nem_declarante_o_obito_junta_como_antes():
    do = dict(DO, nome_falecido="Ulisses Exemplo da Silva")
    junto = LEIT.juntar_obito([_doc("DO", do), _doc("IDENTIDADE", RG, 2)])
    assert junto["valores"]["data_fato"] == "2026-09-10"
    assert junto["valores"]["especie"] == "OBITO"
