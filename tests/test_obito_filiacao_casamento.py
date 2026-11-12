"""Óbito do RCPN — filiação sem nome repetido, cônjuge e revisor.

Os nomes são fictícios. A suíte não pode herdar o schema `producao`
(incidente de 11/11/2026): o conftest já recusa, e este arquivo confere de novo.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import rc_conferencia_dados as CD                          # noqa: E402
import rc_leitura_documentos as LEIT                       # noqa: E402
import rc_modelos_do_livro as ML                           # noqa: E402
import revisao_previa as RV                                # noqa: E402


def test_a_suite_nao_aponta_para_o_schema_producao():
    from tools.trava_producao import exigir_schema_de_teste
    esquema = (os.environ.get("CG_PG_SCHEMA") or "").strip()
    if esquema:
        exigir_schema_de_teste(esquema)
    assert esquema.lower() != "producao"


# -------------------------------------------------- 1. filiação


def test_so_a_mae_qualificada_nao_repete_o_nome_e_diz_o_papel():
    mae = {"nome": "ANA SILVA", "sexo": "F", "profissao": "costureira",
           "naturalidade_cidade": "Cidade Exemplo", "naturalidade_uf": "MA",
           "endereco": "Rua das Flores, 10"}
    pai = {"nome": "JOAO SOUZA", "sexo": "M"}
    texto = ML._filiacao_qualificada(
        mae, pai, ML.CAMPOS_DOS_PAIS_NO_OBITO, repetir_de=True)
    assert texto == (
        "ANA SILVA e de JOAO SOUZA (a mãe, costureira, natural de "
        "Cidade Exemplo/MA, residente e domiciliada em Rua das Flores, 10)")
    assert texto.count("ANA SILVA") == 1


def test_so_o_pai_qualificado_diz_o_pai():
    texto = ML._filiacao_qualificada(
        {"nome": "ANA SILVA", "sexo": "F"},
        {"nome": "JOAO SOUZA", "sexo": "M", "endereco": "Rua B, 2"},
        ML.CAMPOS_DOS_PAIS_NO_OBITO, repetir_de=True)
    assert texto == (
        "ANA SILVA e de JOAO SOUZA (o pai, residente e domiciliado em Rua B, 2)")
    assert texto.count("JOAO SOUZA") == 1


def test_os_dois_qualificados_continuam_respectivamente():
    texto = ML._filiacao_qualificada(
        {"nome": "ANA SILVA", "sexo": "F", "profissao": "costureira",
         "endereco": "Rua das Flores, 10"},
        {"nome": "JOAO SOUZA", "sexo": "M", "profissao": "pedreiro",
         "endereco": "Rua B, 2"},
        ML.CAMPOS_DOS_PAIS_NO_OBITO, repetir_de=True)
    assert texto.startswith("ANA SILVA e JOAO SOUZA (respectivamente:")
    assert " e de " not in texto
    assert "a mãe" not in texto


def test_o_casamento_usa_o_papel_e_nao_troca_a_conjuncao():
    """A mesma função serve o casamento. Um só qualificado não repete o nome;
    a conjunção continua «e», que é o que o termo de casamento já escrevia."""
    texto = ML._filiacao_qualificada(
        {"nome": "ANA SILVA", "sexo": "F", "endereco": "Rua das Flores, 10"},
        {"nome": "JOAO SOUZA", "sexo": "M"},
        ML.CAMPOS_DOS_PAIS_NO_CASAMENTO)
    assert texto == (
        "ANA SILVA e JOAO SOUZA (a mãe, residente e domiciliada em "
        "Rua das Flores, 10)")


def test_o_nascimento_nao_passa_pela_filiacao_entre_parenteses():
    pessoas = [
        {"papel": "REGISTRADO", "nome": "PEDRO EXEMPLO", "sexo": "M"},
        {"papel": "MAE", "nome": "ANA SILVA", "sexo": "F",
         "endereco": "Rua das Flores, 10", "profissao": "costureira"},
        {"papel": "PAI", "nome": "JOAO SOUZA", "sexo": "M"},
    ]
    valores = ML.valores_do_assento(
        {"nome": "PEDRO EXEMPLO", "data_fato": "2026-01-01"}, pessoas)
    assert "ANA SILVA" in valores["filiacao1_qualificacao"]
    assert "(a mãe" not in valores["filiacao1_qualificacao"]
    assert "JOAO SOUZA" in valores["frase_filiacao2"]


def test_o_termo_de_obito_sai_com_a_redacao_do_oficial():
    pessoas = [
        {"papel": "FALECIDO", "nome": "CARLOS EXEMPLO", "sexo": "M"},
        {"papel": "MAE", "nome": "ANA SILVA", "sexo": "F",
         "endereco": "Rua das Flores, 10"},
        {"papel": "PAI", "nome": "JOAO SOUZA", "sexo": "M"},
    ]
    frase = ML.valores_do_obito({}, pessoas)["frase_filiacao"]
    assert frase == (
        "Filho de ANA SILVA e de JOAO SOUZA (a mãe, residente e domiciliada "
        "em Rua das Flores, 10).")


# -------------------------------------------------- 2. conferência


def _obito(**extras):
    dados = {
        "especie": "OBITO",
        "nome": "CARLOS EXEMPLO",
        "pessoas": [
            {"papel": "FALECIDO", "nome": "CARLOS EXEMPLO", "sexo": "M"},
            {"papel": "MAE", "nome": "ANA SILVA", "sexo": "F"},
            {"papel": "PAI", "nome": "JOAO SOUZA", "sexo": "M"},
        ],
        "teor": ("compareceu RITA DECLARANTE e declarou que faleceu CARLOS EXEMPLO. "
                 "Filho de ANA SILVA e de JOAO SOUZA (a mãe, residente e domiciliada "
                 "em Rua das Flores, 10)."),
    }
    dados.update(extras)
    return dados


def test_a_conferencia_avisa_nome_repetido_e_nao_trava():
    ruim = _obito(teor=(
        "faleceu CARLOS EXEMPLO. Filho de ANA SILVA e JOAO SOUZA "
        "(ANA SILVA, residente e domiciliada em Rua das Flores, 10)."))
    achados = CD.conferir(ruim)
    aviso = next(p for p in achados if p["codigo"] == "NOME_REPETIDO")
    assert aviso["gravidade"] == CD.AVISA
    assert "ANA SILVA" in aviso["mensagem"]
    assert aviso["gravidade"] != CD.BLOQUEIA


def test_a_redacao_nova_nao_dispara_o_aviso():
    codigos = {p["codigo"] for p in CD.conferir(_obito())}
    assert "NOME_REPETIDO" not in codigos


def test_a_mae_que_declara_pode_aparecer_duas_vezes():
    teor = ("compareceu ANA SILVA e declarou que faleceu CARLOS EXEMPLO. "
            "Filho de ANA SILVA e de JOAO SOUZA.")
    pessoas = [
        {"papel": "FALECIDO", "nome": "CARLOS EXEMPLO", "sexo": "M"},
        {"papel": "MAE", "nome": "ANA SILVA", "sexo": "F"},
        {"papel": "PAI", "nome": "JOAO SOUZA", "sexo": "M"},
        {"papel": "DECLARANTE", "nome": "ANA SILVA", "sexo": "F"},
    ]
    codigos = {p["codigo"] for p in CD.conferir(
        _obito(teor=teor, pessoas=pessoas))}
    assert "NOME_REPETIDO" not in codigos


def test_conjuge_na_ficha_ou_na_certidao_ausente_do_termo_avisa():
    sem = CD.conferir(_obito(obito_conjuge_nome="MARIA EXEMPLO"))
    aviso = next(p for p in sem if p["codigo"] == "CONJUGE_FORA_DO_TERMO")
    assert aviso["gravidade"] == CD.AVISA
    assert "MARIA EXEMPLO" in aviso["mensagem"]
    citado = _obito(teor=_obito()["teor"] + " Era casado, sendo cônjuge sobrevivente MARIA EXEMPLO.",
                    obito_conjuge_nome="MARIA EXEMPLO")
    assert "CONJUGE_FORA_DO_TERMO" not in {p["codigo"] for p in CD.conferir(citado)}
    cert = CD.conferir(_obito(certidao_casamento={
        "conjuge": "ROSA EXEMPLO", "tipo": "RELIGIOSO", "nomes": ["CARLOS EXEMPLO", "ROSA EXEMPLO"]}))
    assert any(p["codigo"] == "CONJUGE_FORA_DO_TERMO" and "ROSA EXEMPLO" in p["mensagem"]
               for p in cert)


def test_sem_teor_digitado_a_conferencia_olha_a_previa():
    valores = {
        "especie": "OBITO", "pessoa_nome": "CARLOS EXEMPLO", "pessoa_sexo": "M",
        "filiacao1_nome": "ANA SILVA", "filiacao1_sexo": "F",
        "filiacao1_endereco": "Rua das Flores, 10",
        "filiacao2_nome": "JOAO SOUZA", "filiacao2_sexo": "M",
    }
    previo = CD.teor_para_conferir(valores, "")
    assert "a mãe" in previo and previo.count("ANA SILVA") == 1
    assert CD.teor_para_conferir(valores, "teor digitado pela escrevente") == (
        "teor digitado pela escrevente")


# -------------------------------------------------- 3. casamento


def test_a_frase_civil_e_a_religiosa_e_a_antiga_sem_tipo():
    base = {"obito_conjuge_nome": "MARIA EXEMPLO",
            "obito_conjuge_situacao": "SOBREVIVENTE",
            "obito_conjuge_cartorio": "Ofício de Cidade Exemplo"}
    assert ML.frase_do_conjuge_do_falecido(
        {**base, "obito_casamento_tipo": "CIVIL"}, "casado") == (
        "Era casado, sendo cônjuge sobrevivente MARIA EXEMPLO, com casamento "
        "civil registrado em Ofício de Cidade Exemplo.")
    religioso = ML.frase_do_conjuge_do_falecido({
        **base, "obito_casamento_tipo": "RELIGIOSO",
        "obito_casamento_paroquia": "Paróquia São José",
        "obito_casamento_livro": "2", "obito_casamento_folha": "15",
        "obito_casamento_termo": "30"}, "casado")
    assert "casamento religioso celebrado na paróquia São José" in religioso
    assert "livro 2, folha 15, termo 30" in religioso
    assert "registro civil em Ofício de Cidade Exemplo" in religioso
    assert "paróquia Paróquia" not in religioso
    assert ML.frase_do_conjuge_do_falecido(base, "casado") == (
        "Era casado, sendo cônjuge sobrevivente MARIA EXEMPLO, com casamento "
        "registrado em Ofício de Cidade Exemplo.")


def _certidao(dados, arquivo="casamento.pdf"):
    return {"arquivo": arquivo, "n": 2, "attachment_id": None,
            "tipo": "CERTIDAO", "dados": dados}


def test_a_certidao_religiosa_sugere_o_conjuge_e_nao_apaga_o_digitado():
    do = {"numero_do": "12345678-0", "nome_falecido": "Carlos Exemplo",
          "nome_pai": "Joao Souza", "nome_mae": "Ana Silva",
          "data_obito": "10/09/2026", "sexo": "Masculino",
          "estado_civil": "Casado", "causa_a": "Parada cardíaca"}
    cert = {"especie": "casamento religioso",
            "nomes": ["CARLOS EXEMPLO", "MARIA EXEMPLO"],
            "paroquia": "Paróquia São José", "livro": "2", "folha": "15",
            "termo": "30", "cartorio": "Ofício de Cidade Exemplo",
            "tipo_casamento": "religioso"}
    junto = LEIT.juntar_obito([
        {"arquivo": "do.pdf", "n": 1, "attachment_id": None, "tipo": "DO", "dados": do},
        _certidao(cert)])
    v = junto["valores"]
    assert v["obito_conjuge_nome"] == "Maria Exemplo"
    assert v["obito_conjuge_situacao"] == "SOBREVIVENTE"
    assert v["obito_casamento_tipo"] == "RELIGIOSO"
    assert v["obito_casamento_paroquia"] == "Paróquia São José"
    assert v["obito_casamento_livro"] == "2"
    assert v["obito_conjuge_cartorio"] == "Ofício de Cidade Exemplo"
    assert "sugeridos pela certidão" in " ".join(
        a["texto"] for a in junto["conferencia"])

    preservado = {"obito_conjuge_nome": "NOME DIGITADO PELA ESCREVENTE"}
    LEIT.sugerir_conjuge_da_certidao(
        preservado, {"nome": "Carlos Exemplo", "estado_civil": "casado", "sexo": "M"},
        [_certidao(cert)], [])
    assert preservado["obito_conjuge_nome"] == "NOME DIGITADO PELA ESCREVENTE"
    assert preservado["obito_casamento_tipo"] == "RELIGIOSO"


def test_certidao_de_outro_casal_nao_preenche_o_conjuge():
    valores = {}
    avisos = []
    LEIT.sugerir_conjuge_da_certidao(
        valores, {"nome": "Carlos Exemplo", "sexo": "M", "estado_civil": "casado"},
        [_certidao({"especie": "casamento", "nomes": ["PEDRO OUTRO", "RITA OUTRA"],
                    "cartorio": "Ofício de Outra Cidade"})],
        avisos)
    assert "obito_conjuge_nome" not in valores
    assert "não está nela" in avisos[0]["texto"]


def test_a_migracao_do_tipo_de_casamento_e_idempotente():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from banco_de_teste import conexao_de_teste
    from bd_nativo import banco
    from nucleo_schema import init_nucleo_schema
    from rc_schema import init_rc_schema
    con = conexao_de_teste()
    init_nucleo_schema(con)
    init_rc_schema(con)
    init_rc_schema(con)
    bd = banco(con)
    for coluna in ("obito_casamento_tipo", "obito_casamento_paroquia",
                   "obito_casamento_livro", "obito_casamento_folha",
                   "obito_casamento_termo"):
        assert bd.tem_coluna("rc_assentos", coluna), coluna


# -------------------------------------------------- 4. revisor


def test_o_dossie_leva_a_previa_e_a_instrucao_checa_filiacao_e_conjuge():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from banco_de_teste import conexao_de_teste
    con = conexao_de_teste()
    valores = {
        "especie": "OBITO", "pessoa_nome": "CARLOS EXEMPLO", "pessoa_sexo": "M",
        "filiacao1_nome": "ANA SILVA", "filiacao1_sexo": "F",
        "filiacao1_endereco": "Rua das Flores, 10",
        "filiacao2_nome": "JOAO SOUZA", "filiacao2_sexo": "M",
        "obito_conjuge_nome": "MARIA EXEMPLO",
        "obito_casamento_tipo": "RELIGIOSO",
        "obito_casamento_paroquia": "São José",
    }
    dossie = RV.dossie_rcpn(con, 1, "especie=OBITO", valores=valores)
    assert "TEOR QUE SERIA GERADO" in dossie
    assert "a mãe" in dossie
    assert "ANA SILVA e de JOAO SOUZA" in dossie
    assert dossie.count("ANA SILVA") == 1
    _, instrucao = RV.modelo_e_instrucao(con, "RCPN", 1)
    baixa = instrucao.lower()
    assert "teor que seria gerado" in baixa
    assert "religios" in baixa
    assert "cônjuge" in instrucao
    assert "filiação" in instrucao
    assert "Não invente" in instrucao
    fonte = (RAIZ / "revisao_previa.py").read_text(encoding="utf-8")
    assert "'consultivo' (padrão)" in fonte
    assert RV.CHAVE_MODO == "revisao_previa_modo"
