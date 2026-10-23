"""O que a LEI e as NORMAS exigem em cada termo e certidão do RCPN — LT01.

O PEDIDO, do oficial em 20/10/2026: os modelos têm de abarcar o que a lei e
as normas exigem. Na ordem de prevalência: Lei 6.015/1973 (LRP), o Código
Nacional de Normas (Prov. CNJ 149/2023, «CNN») e o Código de Normas
Extrajudicial do Maranhão (Prov. COGEX 28/2026, «CN-MA»). A matriz escrita,
com o artigo de cada elemento, está em `docs/REQUISITOS_LEGAIS.md` (seção do
RCPN); esta é a mesma matriz, executável.

CADA LINHA DA MATRIZ VIRA DOIS TESTES:
    1. o MODELO DA CASA (o padrão em `modelos_padrao/rcpn/`) tem o campo
       (`{claro}`) ou a peça (`__peca`) que leva o elemento ao papel;
    2. o DOCUMENTO MONTADO com um contexto de teste COMPLETO traz o elemento —
       o valor, e não só o rótulo.
Elemento que o modelo não tem é DEFEITO do modelo e fica em
`xfail(strict=True)` com o artigo: a asserção é a da lei. Quando o modelo for
consertado, o xfail estoura (XPASS) e sai daqui.

POR QUE SEM BANCO: os montadores do termo (`rc_modelos_do_livro`) e do breve
relato (`rc_certidao.montar_teor`) são puros, e sem ajuste da casa leem o
padrão da base — é o modelo da casa que se mede, e não um ajuste. O caminho
pelas telas, com banco, selo e papel, é o de `tests/test_fluxo_rcpn.py`.

Só fictícios da casa (docs/AGENTES.md).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import NamedTuple

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import rc_certidao as RCE                                        # noqa: E402
import rc_certidao_inteiro_teor as RCIT                          # noqa: E402
import rc_marcas_do_obito as MO                                  # noqa: E402
import rc_modelos_do_livro as ML                                 # noqa: E402

PASTA = RAIZ / "modelos_padrao" / "rcpn"
SV = {"ri_cidade": "Cidade Exemplo", "ri_uf": "MA", "estado": "Maranhão",
      "unit_name": "Ofício Único de Cidade Exemplo/MA", "ri_cns": "000000",
      "cidade_uf": "Cidade Exemplo/MA",
      "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
      "serventia_titulo": "Oficial Registrador",
      "endereco_completo": "Rua da Serventia, 1, Centro, Cidade Exemplo/MA"}
QUEM = {"escrevente": "MARIO EXEMPLO DOS SANTOS",
        "funcao_do_escrevente": "Oficial Registrador"}
LUGAR = {"livro": "1", "folha": "1", "termo": "1"}
MATRICULA = "00000001552026100001001000000171"


def _q(papel: str, nome: str, sexo: str = "F", **kw) -> dict:
    """Uma pessoa com a qualificação inteira."""
    f = sexo == "F"
    d = dict(papel=papel, nome=nome, sexo=sexo,
             nacionalidade="brasileira" if f else "brasileiro",
             profissao="lavradora" if f else "lavrador",
             estado_civil="casada" if f else "casado", documento_tipo="CPF",
             documento_numero="000.000.010-82",
             naturalidade_cidade="Cidade Exemplo", naturalidade_uf="MA",
             data_nascimento="1996-03-10", endereco="Rua Exemplo, 10",
             bairro="Centro", cidade="Cidade Exemplo", uf="MA")
    d.update(kw)
    return d


# ------------------------------------------------------ os contextos completos

NASCIMENTO = {
    "especie": "NASCIMENTO", "nome": "PEDRO EXEMPLO DOS SANTOS",
    "data_ato": "2026-10-20", "data_fato": "2026-10-01", "hora_fato": "08:30",
    "local_fato_nome": "Residência da família",
    "local_fato_endereco": "Rua Exemplo, 10, Centro",
    "naturalidade_declarada": "Cidade Exemplo/MA", "cor_raca": "PARDA",
    "dnv": "12345678901", "ibge_gemeo": 2, "gemeo_ordem": 1,
    "pais_casamento_lugar": "Cidade Exemplo/MA",
    "pais_casamento_cartorio": "Ofício Único de Cidade Exemplo",
    "matricula": MATRICULA}
PESSOAS_DO_NASCIMENTO = [
    _q("REGISTRADO", "PEDRO EXEMPLO DOS SANTOS", "M",
       documento_numero="000.000.014-06", data_nascimento="2026-10-01",
       estado_civil="", profissao=""),
    _q("MAE", "BEATRIZ EXEMPLO DE SOUZA", idade_no_fato="30"),
    _q("PAI", "MARIO EXEMPLO DOS SANTOS", "M",
       documento_numero="000.000.011-63"),
    dict(papel="AVO_MATERNO", nome="JOSE EXEMPLO DE SOUZA"),
    dict(papel="AVO_MATERNA", nome="ANA EXEMPLO DE SOUZA"),
    dict(papel="AVO_PATERNO", nome="JOAO EXEMPLO DOS SANTOS"),
    dict(papel="AVO_PATERNA", nome="MARIA EXEMPLO DOS SANTOS"),
    _q("DECLARANTE", "BEATRIZ EXEMPLO DE SOUZA"),
    # Parto em residência, sem assistência médica: duas testemunhas (art. 54, 9º).
    _q("TESTEMUNHA", "CARLA EXEMPLO", documento_numero="000.000.013-25"),
    _q("TESTEMUNHA", "PEDRO EXEMPLO", "M", documento_numero="000.000.015-97"),
]

# O REGISTRO TARDIO (LH05 — os hotfixes do servidor de 21/10/2026): fora do
# prazo, à vista do requerimento autuado e assinado por duas testemunhas
# (LRP art. 46; CN-MA art. 249, I e II). Adulto e sem DNV: as testemunhas não
# se dispensam. A segunda do nascimento é o papel TESTEMUNHA2.
TARDIO = dict(NASCIMENTO, data_fato="1990-05-03", hora_fato="", dnv="",
              ibge_gemeo=None, gemeo_ordem=None, registro_tardio="1",
              tardio_requerimento="3/2026")
PESSOAS_DO_TARDIO = [
    dict(PESSOAS_DO_NASCIMENTO[0], data_nascimento="1990-05-03"),
    *(p for p in PESSOAS_DO_NASCIMENTO[1:] if p["papel"] != "TESTEMUNHA"),
    _q("TESTEMUNHA", "CARLA EXEMPLO", documento_numero="000.000.013-25"),
    _q("TESTEMUNHA2", "PEDRO EXEMPLO", "M", documento_numero="000.000.015-97"),
]
# Menor de 12 anos com DNV: a dispensa das testemunhas (art. 249, II).
TARDIO_MENOR = dict(NASCIMENTO, data_fato="2020-01-01", dnv="12345678901",
                    registro_tardio="1", tardio_requerimento="4/2026")
PESSOAS_DO_TARDIO_MENOR = [
    dict(PESSOAS_DO_NASCIMENTO[0], data_nascimento="2020-01-01"),
    *(p for p in PESSOAS_DO_NASCIMENTO[1:] if p["papel"] != "TESTEMUNHA")]

NATIMORTO = dict(NASCIMENTO, especie="NATIMORTO",
                 nome="NATIMORTO DE BEATRIZ EXEMPLO DE SOUZA",
                 numero_do="11112222", dnv="", ibge_gemeo=None,
                 gemeo_ordem=None, local_fato_nome="Hospital Municipal de "
                 "Cidade Exemplo", local_fato_endereco="Avenida Exemplo, 100")
PESSOAS_DO_NATIMORTO = [
    dict(papel="REGISTRADO", nome="NATIMORTO DE BEATRIZ EXEMPLO DE SOUZA",
         sexo="M"),
    _q("MAE", "BEATRIZ EXEMPLO DE SOUZA", idade_no_fato="30"),
    _q("PAI", "MARIO EXEMPLO DOS SANTOS", "M"),
    _q("DECLARANTE", "MARIO EXEMPLO DOS SANTOS", "M"),
]

OBITO = {
    "especie": "OBITO", "nome": "CARLA EXEMPLO", "data_ato": "2026-10-20",
    "data_fato": "2026-10-18", "hora_fato": "14:00",
    "local_fato_nome": "Hospital Municipal de Cidade Exemplo",
    "local_fato_endereco": "Avenida Exemplo, 100, Centro",
    "cor_raca": "PARDA", "numero_do": "98765432", "ibge_natureza_obito": 1,
    "causa_morte": "insuficiência cardíaca",
    "atestante": "BEATRIZ EXEMPLO DE SOUZA", "atestante_documento": "CRM-MA 0000",
    "local_sepultamento": "Cemitério Municipal de Cidade Exemplo",
    "testamento": "SIM, lavrado no Tabelionato de Cidade Exemplo",
    "obito_conjuge_nome": "PEDRO EXEMPLO DOS SANTOS",
    "obito_conjuge_situacao": "PRE_MORTO",
    "obito_conjuge_cartorio": "Ofício Único de Cidade Exemplo",
    "obito_filhos": "MARIO EXEMPLO DOS SANTOS, com 50 anos",
    "obito_herdeiros_menores": "NAO", "matricula": MATRICULA}
PESSOAS_DO_OBITO = [
    _q("FALECIDO", "CARLA EXEMPLO", estado_civil="viúva",
       profissao="aposentada", documento_numero="000.000.012-44",
       data_nascimento="1950-01-02", endereco="Rua Exemplo, 20"),
    _q("MAE", "ANA EXEMPLO DE SOUZA", profissao="costureira",
       endereco="Rua Exemplo, 30"),
    _q("PAI", "JOSE EXEMPLO DE SOUZA", "M", profissao="pedreiro",
       endereco="Rua Exemplo, 30"),
    _q("DECLARANTE", "MARIO EXEMPLO DOS SANTOS", "M",
       documento_numero="000.000.011-63"),
]
MARCAS_DO_OBITO = {"obito_eleitor": MO.SIM, "obito_possui_bens": MO.SIM,
                   "obito_possui_filho": MO.SIM, "obito_desconhecido": MO.NAO}

CASAMENTO = {
    "especie": "CASAMENTO", "nome": "MARIO EXEMPLO DOS SANTOS e BEATRIZ "
    "EXEMPLO DE SOUZA", "data_ato": "2026-10-20", "data_fato": "2026-10-20",
    "regime_bens": "SEPARACAO_TOTAL", "pacto_data": "2026-09-10",
    "pacto_serventia": "Tabelionato de Notas de Cidade Exemplo",
    "proclamas_data": "2026-09-01",
    "nubente1_conjuge_anterior": "CARLA EXEMPLO",
    "nubente1_dissolucao_data": "2020-02-03", "matricula": MATRICULA}
PESSOAS_DO_CASAMENTO = [
    _q("NUBENTE1", "MARIO EXEMPLO DOS SANTOS", "M", estado_civil="divorciado",
       nome_pos="MARIO EXEMPLO DOS SANTOS", documento_numero="000.000.011-63"),
    _q("NUBENTE2", "BEATRIZ EXEMPLO DE SOUZA", estado_civil="solteira",
       nome_pos="BEATRIZ EXEMPLO DE SOUZA DOS SANTOS"),
    _q("MAE_NUBENTE1", "ANA EXEMPLO DOS SANTOS", profissao="costureira",
       data_nascimento="1950-04-04", endereco="Rua Exemplo, 40"),
    _q("PAI_NUBENTE1", "JOAO EXEMPLO DOS SANTOS", "M", profissao="pedreiro",
       data_nascimento="1948-05-05", endereco="Rua Exemplo, 40"),
    _q("MAE_NUBENTE2", "MARIA EXEMPLO DE SOUZA", profissao="professora",
       data_nascimento="1960-06-06", endereco="Rua Exemplo, 50"),
    _q("PAI_NUBENTE2", "JOSE EXEMPLO DE SOUZA", "M", profissao="motorista",
       data_nascimento="1958-07-07", endereco="Rua Exemplo, 50"),
    _q("TESTEMUNHA", "CARLA EXEMPLO", profissao="comerciante",
       documento_numero="000.000.013-25"),
    _q("TESTEMUNHA", "PEDRO EXEMPLO", "M", profissao="agricultor",
       documento_numero="000.000.015-97"),
]
DOCUMENTOS = [
    {"descricao": "Certidão de nascimento do segundo nubente", "apresentado": 1},
    {"descricao": "Certidão de casamento com averbação do divórcio do "
                  "primeiro nubente", "apresentado": 1},
]

LIVRO_E = {
    "EMANCIPACAO": (
        {"livro_e_titulo": "ESCRITURA", "livro_e_titulo_data": "2026-10-05",
         "livro_e_escritura_livro": "40", "livro_e_escritura_folha": "12",
         "livro_e_tabelionato": "Tabelionato de Notas de Cidade Exemplo",
         "livro_e_registro_nascimento": "Livro A-1, folha 1, termo 1, deste ofício"},
        [_q("REGISTRADO", "PEDRO EXEMPLO DOS SANTOS", "M", estado_civil="solteiro",
            data_nascimento="2009-05-01", idade_no_fato="17"),
         _q("MAE", "BEATRIZ EXEMPLO DE SOUZA"),
         _q("PAI", "MARIO EXEMPLO DOS SANTOS", "M")]),
    "INTERDICAO": (
        {"livro_e_titulo": "SENTENCA", "livro_e_titulo_data": "2026-09-01",
         "livro_e_juizo": "Vara Única da Comarca de Cidade Exemplo",
         "livro_e_juiz": "CARLA EXEMPLO",
         "livro_e_processo": "0000001-00.2026.8.10.0000",
         "livro_e_transito": "2026-09-20", "livro_e_causa": "causa de exemplo",
         "livro_e_limites": "atos de disposição patrimonial",
         "livro_e_internacao": "Casa de Saúde de Exemplo",
         "livro_e_registro_nascimento": "Livro A-1, folha 1, termo 1",
         "livro_e_registro_casamento": "Livro B-1, folha 2, termo 2",
         "livro_e_conjuge": "BEATRIZ EXEMPLO DE SOUZA"},
        [_q("REGISTRADO", "PEDRO EXEMPLO DOS SANTOS", "M"),
         _q("CURADOR", "BEATRIZ EXEMPLO DE SOUZA"),
         _q("REQUERENTE", "MARIO EXEMPLO DOS SANTOS", "M")]),
    "AUSENCIA": (
        {"livro_e_titulo": "SENTENCA", "livro_e_titulo_data": "2026-09-01",
         "livro_e_juizo": "Vara Única da Comarca de Cidade Exemplo",
         "livro_e_juiz": "CARLA EXEMPLO", "livro_e_ausencia_tempo": "dois anos",
         "livro_e_limites": "administração dos bens",
         "livro_e_registro_nascimento": "Livro A-1, folha 1, termo 1"},
        [_q("REGISTRADO", "PEDRO EXEMPLO DOS SANTOS", "M"),
         _q("CURADOR", "BEATRIZ EXEMPLO DE SOUZA"),
         _q("REQUERENTE", "MARIO EXEMPLO DOS SANTOS", "M")]),
    "UNIAO_ESTAVEL": (
        {"livro_e_titulo": "ESCRITURA", "livro_e_titulo_data": "2026-10-05",
         "livro_e_escritura_livro": "40", "livro_e_escritura_folha": "12",
         "livro_e_tabelionato": "Tabelionato de Notas de Cidade Exemplo",
         "livro_e_uniao_inicio": "2020-01-01", "regime_bens": "COMUNHAO_PARCIAL"},
        [_q("COMPANHEIRO1", "MARIO EXEMPLO DOS SANTOS", "M", estado_civil="solteiro"),
         _q("COMPANHEIRO2", "BEATRIZ EXEMPLO DE SOUZA", estado_civil="solteira",
            documento_numero="000.000.011-63"),
         dict(papel="MAE_COMPANHEIRO1", nome="ANA EXEMPLO DOS SANTOS"),
         dict(papel="MAE_COMPANHEIRO2", nome="MARIA EXEMPLO DE SOUZA")]),
}


# ------------------------------------------------------------- os montadores


def _limpo(texto: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", texto or "")).strip()


def _livro_e(especie: str) -> str:
    assento, pessoas = LIVRO_E[especie]
    a = {"especie": especie, "nome": pessoas[0]["nome"], "data_ato": "2026-10-20",
         "data_fato": assento.get("livro_e_titulo_data"), **assento}
    return _limpo(ML.montar_livro_e_do_assento(a, pessoas, sv=SV, **QUEM)["texto"])


AVERBACAO = {"tipo": "AVERBACAO", "teor": "Averbação de reconhecimento de "
             "filiação, por mandado do juízo da Vara Única de Cidade Exemplo, "
             "processo 0000002-00.2026.8.10.0000, de 01/10/2026.",
             "criado_por": "MARIO EXEMPLO DOS SANTOS",
             "selo": "AVERBA000000TESTE00000000001"}


def _certidao(assento: dict, pessoas: list, atos=()) -> str:
    return RCE.montar_teor(assento=assento, pessoas_do_assento=pessoas,
                           atos=list(atos), sv=SV, hoje="2026-10-20",
                           lugar=LUGAR, data_extenso="20 de outubro de 2026")


def _hab() -> dict:
    return {"certidao_numero": 1, "certidao_ano": 2026, "numero": 7, "ano": 2026,
            "nubente1_nome": "MARIO EXEMPLO DOS SANTOS",
            "nubente1_estado_civil": "DIVORCIADO",
            "nubente2_nome": "BEATRIZ EXEMPLO DE SOUZA",
            "nubente2_estado_civil": "SOLTEIRA", "regime": "COMUNHAO_PARCIAL",
            "edital_em": "2026-09-01", "edital_prazo_ate": "2026-09-06",
            "habilitado_em": "2026-09-08", "habilitacao_vale_ate": "2026-12-07",
            "oposicao_em": None, "habilitado_por": "MARIO EXEMPLO DOS SANTOS"}


def _br(iso) -> str:
    s = str(iso or "")
    return f"{s[8:10]}/{s[5:7]}/{s[:4]}" if len(s) >= 10 else s


def _montar(qual: str) -> str:
    import habilitacao_web as HW
    if qual == "termo_nascimento":
        return _limpo(ML.montar_do_assento(NASCIMENTO, PESSOAS_DO_NASCIMENTO,
                                           sv=SV, **QUEM)["texto"])
    if qual == "termo_nascimento_tardio":
        return _limpo(ML.montar_do_assento(TARDIO, PESSOAS_DO_TARDIO,
                                           sv=SV, **QUEM)["texto"])
    if qual == "termo_nascimento_tardio_menor":
        return _limpo(ML.montar_do_assento(TARDIO_MENOR, PESSOAS_DO_TARDIO_MENOR,
                                           sv=SV, **QUEM)["texto"])
    if qual == "termo_natimorto":
        return _limpo(ML.montar_do_assento(NATIMORTO, PESSOAS_DO_NATIMORTO,
                                           sv=SV, **QUEM)["texto"])
    if qual == "termo_obito":
        return _limpo(ML.montar_obito_do_assento(
            OBITO, PESSOAS_DO_OBITO, marcas=MARCAS_DO_OBITO, sv=SV,
            **QUEM)["texto"])
    if qual == "termo_casamento":
        return _limpo(ML.montar_casamento_do_assento(
            CASAMENTO, PESSOAS_DO_CASAMENTO, documentos=DOCUMENTOS, sv=SV,
            **QUEM)["texto"])
    if qual == "termo_casamento_de_fora":
        return _limpo(ML.montar_casamento_do_assento(
            dict(CASAMENTO, habilitacao_serventia="Ofício de Outra Cidade/MA"),
            PESSOAS_DO_CASAMENTO, documentos=DOCUMENTOS, sv=SV, **QUEM)["texto"])
    if qual.startswith("termo_livro_e_"):
        return _livro_e(qual.removeprefix("termo_livro_e_").upper())
    if qual == "certidao_nascimento":
        return _certidao(NASCIMENTO, PESSOAS_DO_NASCIMENTO)
    if qual == "certidao_nascimento_averbada":
        return _certidao(NASCIMENTO, PESSOAS_DO_NASCIMENTO, [AVERBACAO])
    if qual == "certidao_nascimento_averbacao_sem_texto":
        # A averbação que a certidão NÃO transcreve (sem texto no sistema):
        # é aí que a inscrição do art. 21, parágrafo único, avisa dela.
        return _certidao(NASCIMENTO, PESSOAS_DO_NASCIMENTO,
                         [dict(AVERBACAO, teor="")])
    if qual == "certidao_obito":
        return _certidao(dict(OBITO, obito_eleitor="SIM", obito_possui_bens="SIM",
                              obito_possui_filho="SIM"), PESSOAS_DO_OBITO)
    if qual == "certidao_casamento":
        return _certidao(CASAMENTO, PESSOAS_DO_CASAMENTO)
    if qual == "certidao_natimorto":
        return _certidao(NATIMORTO, PESSOAS_DO_NATIMORTO)
    if qual.startswith("certidao_livro_e_"):
        especie = qual.removeprefix("certidao_livro_e_").upper()
        assento, pessoas = LIVRO_E[especie]
        return _certidao({"especie": especie, "nome": pessoas[0]["nome"],
                          "data_ato": "2026-10-20", **assento}, pessoas)
    if qual == "inteiro_teor":
        return RCIT.introducao(especie="NASCIMENTO",
                               nome="PEDRO EXEMPLO DOS SANTOS",
                               matricula=MATRICULA, livro="1", folha="1",
                               termo="1", cns="000000", cidade="Cidade Exemplo",
                               uf="MA")
    if qual == "certidao_habilitacao":
        return _limpo(HW.html_da_certidao(_hab(), sv=SV, fmt_date=_br))
    if qual == "edital_proclamas":
        return _limpo(HW.teor_sugerido_do_edital(_hab(), sv=SV,
                                                 hoje_iso="2026-09-01",
                                                 fmt_date=_br))
    raise KeyError(qual)


# ----------------------------------------------------------------- a matriz


class Req(NamedTuple):
    montado: str          # o documento (ver `_montar`)
    elemento: str         # o que a lei manda constar
    artigo: str
    modelo: str           # a chave do padrão em modelos_padrao/rcpn
    campos: tuple         # `{claro}` no padrão, ou `__peca` (arquivo próprio)
    esperado: tuple       # o que o documento montado tem de dizer
    defeito: str = ""     # vazio = o modelo cumpre; texto = xfail(strict)


T_NASC, T_OB, T_CAS, T_E = ("RC_TERMO_NASCIMENTO", "RC_TERMO_OBITO",
                            "RC_TERMO_CASAMENTO", "RC_TERMO_LIVRO_E")
C_RES, C_IT, C_HAB = ("RC_CERTIDAO_RESUMO", "RC_CERTIDAO_INTEIRO_TEOR",
                      "RC_CERTIDAO_HABILITACAO")
NA_TABELA = ()   # o breve relato é o leiaute do CNJ, montado em código

MATRIZ: dict[str, Req] = {
    # ------------------------------------------------ termo de nascimento
    "nasc.data_hora_lugar": Req(
        "termo_nascimento", "dia, mês, ano, hora e lugar do nascimento",
        "LRP art. 54, 1º; CN-MA art. 233, I", T_NASC,
        ("{data_do_fato}", "{frase_hora}", "{local_do_fato}"),
        ("um (01) de outubro de dois mil e vinte e seis", "às 08:30",
         "Residência da família, Rua Exemplo, 10, Centro")),
    "nasc.sexo": Req("termo_nascimento", "sexo do registrando",
                     "LRP art. 54, 2º; CN-MA art. 233, II", T_NASC,
                     ("{sexo}",), ("do sexo Masculino",)),
    "nasc.gemeo": Req("termo_nascimento", "o fato de ser gêmeo e a ordem",
                      "LRP art. 54, 3º, e art. 63; CN-MA art. 234", T_NASC,
                      ("{frase_gemeos}",), ("gêmeo",)),
    "nasc.nome": Req("termo_nascimento", "nome e prenome postos à criança",
                     "LRP art. 54, 4º, e art. 55", T_NASC, ("{nome}",),
                     ('"PEDRO EXEMPLO DOS SANTOS"',)),
    "nasc.pais": Req("termo_nascimento",
                     "nomes, naturalidade e profissão dos pais; residência",
                     "LRP art. 54, 7º; CN-MA art. 233, VI e VII", T_NASC,
                     ("{filiacao1_qualificacao}", "{frase_filiacao2}"),
                     ("sendo filho de BEATRIZ EXEMPLO DE SOUZA, brasileira, "
                      "lavradora", "e de MARIO EXEMPLO DOS SANTOS, brasileiro, "
                      "lavrador", "natural de Cidade Exemplo/MA",
                      "residente e domiciliada em Rua Exemplo, 10")),
    "nasc.idade_da_mae": Req("termo_nascimento",
                             "idade da genitora na ocasião do parto",
                             "LRP art. 54, 7º", T_NASC,
                             ("{frase_idade_da_genitora}",),
                             ("30 anos de idade",)),
    "nasc.avos": Req("termo_nascimento", "nomes e prenomes dos avós",
                     "LRP art. 54, 8º; CN-MA art. 233, VIII", T_NASC,
                     ("{frase_avos}",),
                     ("JOSE EXEMPLO DE SOUZA e ANA EXEMPLO DE SOUZA",
                      "JOAO EXEMPLO DOS SANTOS e MARIA EXEMPLO DOS SANTOS")),
    "nasc.testemunhas": Req(
        "termo_nascimento",
        "duas testemunhas, no parto sem assistência médica fora de hospital",
        "LRP art. 54, 9º; CN-MA art. 233, IX", T_NASC, ("{testemunhas}",),
        ("CARLA EXEMPLO", "PEDRO EXEMPLO,")),
    "nasc.dnv": Req("termo_nascimento", "número da DNV", "LRP art. 54, 10; "
                    "CN-MA art. 233, X", T_NASC, ("{frase_dnv}", "__dnv"),
                    ("DNV n.º 12345678901",)),
    "nasc.naturalidade": Req("termo_nascimento", "naturalidade do registrando",
                             "LRP art. 54, 11, e § 4º; CN-MA art. 233, XI",
                             T_NASC, ("{frase_naturalidade}",),
                             ("naturalidade declarada é de Cidade Exemplo/MA",)),
    "nasc.cpf": Req("termo_nascimento", "CPF do registrando",
                    "CN-MA art. 233, XII; CNN art. 477, § 1º", T_NASC,
                    ("{frase_cpf}",), ("000.000.014-06",)),
    "nasc.encerramento": Req(
        "termo_nascimento", "leitura, assinatura do declarante e do oficial",
        "LRP arts. 37 e 38; CN-MA art. 212", T_NASC,
        ("{escrevente}", "{funcao_do_escrevente}"),
        ("Lido e achado conforme, o(a) declarante assina.",
         "Eu, MARIO EXEMPLO DOS SANTOS, Oficial Registrador, dou fé e assino.")),
    "nasc.matricula": Req("termo_nascimento", "matrícula", "CNN art. 473",
                          T_NASC, ("{frase_matricula}",), (MATRICULA,)),
    # --------------------------------- o registro tardio (LH05, 21/10/2026)
    "nasc.tardio": Req(
        "termo_nascimento_tardio",
        "registro fora do prazo, à vista do requerimento autuado e numerado, "
        "assinado por duas testemunhas que atestam a identidade",
        "LRP art. 46; CN-MA art. 249, I e II", T_NASC,
        ("{frase_tardio}", "__tardio_com_requerimento", "__tardio_testemunhas"),
        ("Registro lavrado fora do prazo legal, nos termos do art. 46 da Lei nº "
         "6.015/1973 e do art. 249 do Código de Normas do TJMA",
         "à vista do requerimento nº 3/2026 autuado nesta serventia",
         "assinado pelas testemunhas CARLA EXEMPLO, brasileira",
         "e PEDRO EXEMPLO, brasileiro", "a identidade do(a) registrado(a).")),
    "nasc.tardio_dispensa": Req(
        "termo_nascimento_tardio_menor",
        "a dispensa das testemunhas só com o registrando menor de 12 anos e DNV",
        "CN-MA art. 249, II", T_NASC, ("{frase_tardio}", "__tardio_dispensa"),
        ("dispensada a presença de testemunhas por se tratar de registrando "
         "menor de 12 (doze) anos com DNV apresentada (art. 249, II)",)),
    # ------------------------------------------------- termo de natimorto
    "nati.nasceu_morta": Req(
        "termo_natimorto", "a declaração de que nasceu morta",
        "LRP art. 53, § 1º, e art. 54, 5º; CNN art. 479-A", T_NASC,
        ("{frase_natimorto}",), ("nasceu morta",)),
    # ----------------------------------------------------- termo de óbito
    "ob.data_hora": Req("termo_obito", "hora, dia, mês e ano do falecimento",
                        "LRP art. 80, 1º; CN-MA art. 255, I", T_OB,
                        ("{data_fato_extenso}", "{frase_hora}"),
                        ("dezoito (18) de outubro de dois mil e vinte e seis",
                         "às 14:00")),
    "ob.lugar": Req("termo_obito", "lugar do falecimento, com indicação precisa",
                    "LRP art. 80, 2º; CN-MA art. 255, II", T_OB,
                    ("{local_do_fato}",),
                    ("Hospital Municipal de Cidade Exemplo, Avenida Exemplo, "
                     "100, Centro",)),
    "ob.falecido": Req("termo_obito",
                       "nome, sexo, estado, profissão, naturalidade, domicílio",
                       "LRP art. 80, 3º; CN-MA art. 255, III", T_OB,
                       ("{falecido_qualificacao}",),
                       ("faleceu CARLA EXEMPLO", "aposentada",
                        "natural de Cidade Exemplo/MA",
                        "residente e domiciliada em Rua Exemplo, 20")),
    "ob.idade_e_cor": Req(
        "termo_obito", "idade e cor do morto",
        "LRP art. 80, 3º; CN-MA art. 255, III", T_OB, ("{falecido_qualificacao}",),
        ("76 anos", "parda")),
    "ob.conjuge": Req("termo_obito", "cônjuge sobrevivente ou pré-morto e o "
                      "cartório do casamento", "LRP art. 80, 4º; CN-MA art. 255, IV",
                      T_OB, ("{frase_estado_civil}", "__conjuge_pre_morto"),
                      ("PEDRO EXEMPLO DOS SANTOS", "Ofício Único de Cidade Exemplo")),
    "ob.eleitor": Req("termo_obito", "se era eleitor",
                      "LRP art. 80, 11º; CN-MA art. 255, V", T_OB,
                      ("{frase_eleitor}", "__eleitor_sim", "__eleitor_nao"),
                      ("eleitor",)),
    "ob.pais_nomes": Req("termo_obito", "nomes dos pais",
                         "LRP art. 80, 5º; CN-MA art. 255, VI", T_OB,
                         ("{frase_filiacao}", "__filiacao"),
                         ("ANA EXEMPLO DE SOUZA e JOSE EXEMPLO DE SOUZA",)),
    "ob.pais_qualificacao": Req(
        "termo_obito", "profissão, naturalidade e residência dos pais",
        "LRP art. 80, 5º; CN-MA art. 255, VI", T_OB, ("{frase_filiacao}",),
        ("costureira", "pedreiro", "Rua Exemplo, 30")),
    "ob.testamento": Req("termo_obito", "se faleceu com testamento conhecido",
                         "LRP art. 80, 6º; CN-MA art. 255, VII", T_OB,
                         ("{frase_testamento}", "__testamento"),
                         ("Tabelionato de Cidade Exemplo",)),
    "ob.filhos": Req("termo_obito", "se deixou filhos, nome e idade de cada um",
                     "LRP art. 80, 7º; CN-MA art. 255, VIII", T_OB,
                     ("{frase_filhos}", "__filhos_sim"),
                     ("MARIO EXEMPLO DOS SANTOS, com 50 anos",)),
    "ob.causa": Req("termo_obito", "se a morte foi natural ou violenta, a causa "
                    "e o atestante", "LRP art. 80, 8º; CN-MA art. 255, IX", T_OB,
                    ("{frase_causa}", "__causa", "__atestante"),
                    ("insuficiência cardíaca", "BEATRIZ EXEMPLO DE SOUZA",
                     "CRM-MA 0000")),
    "ob.natural_ou_violenta": Req(
        "termo_obito", "a natureza da morte (natural ou violenta)",
        "LRP art. 80, 8º; CN-MA art. 255, IX", T_OB, ("{frase_causa}",),
        ("morte foi natural",)),
    "ob.sepultamento": Req("termo_obito", "lugar do sepultamento",
                           "LRP art. 80, 9º; CN-MA art. 255, X", T_OB,
                           ("{frase_sepultamento}", "__sepultamento"),
                           ("Cemitério Municipal de Cidade Exemplo",)),
    "ob.bens_herdeiros": Req("termo_obito", "se deixou bens e herdeiros menores",
                             "LRP art. 80, 10º; CN-MA art. 255, XI", T_OB,
                             ("{frase_deixou_bens}", "__bens_sim", "__herdeiros_nao"),
                             ("Deixou bens", "Não deixou herdeiros menores")),
    "ob.documento": Req("termo_obito", "ao menos um documento do falecido (CPF)",
                        "LRP art. 80, 12º; CN-MA art. 255, XII", T_OB,
                        ("{falecido_qualificacao}",), ("000.000.012-44",)),
    "ob.encerramento": Req("termo_obito", "leitura e assinaturas",
                           "LRP arts. 37, 38 e 82", T_OB,
                           ("{escrevente}", "{funcao_do_escrevente}"),
                           ("Lido e achado conforme",
                            "Eu, MARIO EXEMPLO DOS SANTOS, Oficial Registrador, "
                            "escrevi e assino.")),
    # -------------------------------------------------- termo de casamento
    "cas.conjuges": Req("termo_casamento", "nomes, nacionalidade, naturalidade, "
                        "data de nascimento, profissão e residência dos cônjuges",
                        "LRP art. 70, 1º; CN-MA art. 284, I", T_CAS,
                        ("{nubente1_qualificacao}", "{nubente2_qualificacao}"),
                        ("MARIO EXEMPLO DOS SANTOS, brasileiro",
                         "BEATRIZ EXEMPLO DE SOUZA, brasileira",
                         "natural de Cidade Exemplo/MA", "lavrador",
                         "residente e domiciliado em Rua Exemplo, 10")),
    "cas.pais_nomes": Req("termo_casamento", "nomes dos pais",
                          "LRP art. 70, 2º; CN-MA art. 284, II", T_CAS,
                          ("{filiacao1}", "{filiacao2}"),
                          ("ANA EXEMPLO DOS SANTOS e JOAO EXEMPLO DOS SANTOS",
                           "MARIA EXEMPLO DE SOUZA e JOSE EXEMPLO DE SOUZA")),
    "cas.pais_qualificacao": Req(
        "termo_casamento", "nacionalidade, data de nascimento e residência dos "
        "pais", "LRP art. 70, 2º; CN-MA art. 284, II", T_CAS,
        ("{filiacao1}", "{filiacao2}"), ("Rua Exemplo, 40", "Rua Exemplo, 50")),
    "cas.casamento_anterior": Req(
        "termo_casamento", "cônjuge precedente e data da dissolução",
        "LRP art. 70, 3º; CN-MA art. 284, III", T_CAS,
        ("{nubente1_qualificacao}", "__casamento_anterior_dissolvido"),
        ("CARLA EXEMPLO", "03/02/2020")),
    "cas.proclamas_de_fora": Req(
        "termo_casamento_de_fora", "data da publicação dos proclamas "
        "(habilitação de outra serventia)", "LRP art. 70, 4º; CN-MA art. 284, IV",
        T_CAS, ("{frase_habilitacao}", "__habilitacao_de_fora_proclamas"),
        ("Ofício de Outra Cidade/MA", "proclamas publicados em 01/09/2026")),
    "cas.proclamas_desta_casa": Req(
        "termo_casamento", "data da publicação dos proclamas (habilitação desta "
        "serventia)", "LRP art. 70, 4º; CN-MA art. 284, IV", T_CAS,
        ("{frase_habilitacao}",), ("01/09/2026",)),
    "cas.documentos": Req("termo_casamento", "relação dos documentos apresentados",
                          "LRP art. 70, 5º; CN-MA art. 284, V", T_CAS,
                          ("{documentos_apresentados}",),
                          ("Certidão de nascimento do segundo nubente",)),
    "cas.testemunhas_nomes": Req("termo_casamento", "nomes das testemunhas",
                                 "LRP art. 70, 6º; CC art. 1.534", T_CAS,
                                 ("{testemunhas}",),
                                 ("CARLA EXEMPLO", "PEDRO EXEMPLO")),
    "cas.testemunhas_qualificacao": Req(
        "termo_casamento", "nacionalidade, profissão e residência das testemunhas",
        "LRP art. 70, 6º; CN-MA art. 284, VI", T_CAS, ("{testemunhas}",),
        ("comerciante", "agricultor")),
    "cas.regime_e_pacto": Req(
        "termo_casamento", "regime de bens, com a data e o cartório do pacto",
        "LRP art. 70, 7º; CN-MA art. 284, VII", T_CAS,
        ("{regime_bens}", "__pacto_data_serventia"),
        ("separação", "10/09/2026", "Tabelionato de Notas de Cidade Exemplo")),
    "cas.nome_adotado": Req("termo_casamento", "nomes que os cônjuges passam a ter",
                            "LRP art. 70, 8º; CN-MA art. 284, VIII", T_CAS,
                            ("{frase_dos_nomes}",),
                            ("BEATRIZ EXEMPLO DE SOUZA DOS SANTOS",)),
    "cas.encerramento": Req("termo_casamento", "leitura e assinaturas do "
                            "presidente, cônjuges, testemunhas e oficial",
                            "LRP art. 70, caput; CN-MA art. 282", T_CAS,
                            ("{escrevente}",),
                            ("Lido e achado conforme, assinam comigo",
                             "Eu, MARIO EXEMPLO DOS SANTOS, Oficial Registrador")),
    # ------------------------------------------------------------- Livro E
    "e.emancipacao": Req(
        "termo_livro_e_emancipacao", "data e título da emancipação (escritura: "
        "data, livro, folha e ofício), emancipado, pais",
        "LRP art. 90, 1º a 3º; CN-MA art. 329", T_E,
        ("{titulo_do_ato}", "{frase_da_especie}", "__escritura"),
        ("Emancipação", "PEDRO EXEMPLO DOS SANTOS", "40", "12",
         "Tabelionato de Notas de Cidade Exemplo", "BEATRIZ EXEMPLO DE SOUZA",
         "Livro A-1, folha 1, termo 1")),
    "e.interdicao": Req(
        "termo_livro_e_interdicao", "sentença (data, juiz e vara), curador, "
        "requerente, causa, limites, internação, registros anteriores",
        "LRP art. 92, 1º a 7º; CN-MA art. 328", T_E,
        ("{frase_da_especie}", "__sentenca", "__curadora_nomeada",
         "__limites", "__internacao", "__causa"),
        ("Interdição", "Vara Única da Comarca de Cidade Exemplo", "CARLA EXEMPLO",
         "BEATRIZ EXEMPLO DE SOUZA", "MARIO EXEMPLO DOS SANTOS",
         "causa de exemplo", "atos de disposição patrimonial",
         "Casa de Saúde de Exemplo", "Livro B-1, folha 2, termo 2")),
    "e.ausencia": Req(
        "termo_livro_e_ausencia", "sentença, tempo de ausência, curador e "
        "limites da curatela", "LRP art. 94, 1º a 6º; CN-MA art. 328", T_E,
        ("{frase_da_especie}", "__tempo_de_ausencia", "__curadora_nomeada"),
        ("Ausência", "dois anos", "BEATRIZ EXEMPLO DE SOUZA",
         "administração dos bens")),
    "e.uniao_estavel": Req(
        "termo_livro_e_uniao_estavel", "companheiros, escritura (data, livro, "
        "folha, tabelionato), regime de bens, início da união",
        "LRP art. 94-A; CNN arts. 537 a 539", T_E,
        ("{frase_da_especie}", "__uniao_estavel", "__regime", "__inicio"),
        ("MARIO EXEMPLO DOS SANTOS", "BEATRIZ EXEMPLO DE SOUZA",
         "Tabelionato de Notas de Cidade Exemplo", "comunhão parcial",
         "um (01) de janeiro de dois mil e vinte")),
    # ------------------------------------------------------- as certidões
    "cert.nasc": Req(
        "certidao_nascimento", "nome, matrícula, data por extenso, hora, "
        "naturalidade, local, sexo, filiação, avós, gêmeo, DNV, data do "
        "registro, livro/folha/termo", "LRP art. 19, § 4º; CNN arts. 473 a 476",
        C_RES, NA_TABELA,
        ("PEDRO EXEMPLO DOS SANTOS", MATRICULA,
         "PRIMEIRO DE OUTUBRO DE DOIS MIL E VINTE E SEIS", "08:30",
         "NATURALIDADE\nCidade Exemplo/MA", "Residência da família",
         "MASCULINO", "MARIO EXEMPLO DOS SANTOS e BEATRIZ EXEMPLO DE SOUZA",
         "JOSE EXEMPLO DE SOUZA e ANA EXEMPLO DE SOUZA", "GÊMEO\nSIM",
         "12345678901", "VINTE DE OUTUBRO DE DOIS MIL E VINTE E SEIS",
         "LIVRO\n1", "FOLHA\n1", "TERMO\n1")),
    "cert.cpf": Req("certidao_nascimento", "CPF do registrado", "CNN art. 477",
                    C_RES, NA_TABELA, ("CPF\n000.000.014-06",)),
    "cert.fe": Req("certidao_nascimento", "serventia, lugar, data e fé",
                   "LRP art. 19; CN-MA arts. 378 e 381", C_RES,
                   ("{casa}", "{onde}", "{data}"),
                   ("O referido é verdade e dou fé. Ofício Único de Cidade "
                    "Exemplo/MA, Cidade Exemplo/MA, 20 de outubro de 2026.",)),
    "cert.averbacao": Req("certidao_nascimento_averbada",
                          "as averbações, mencionadas obrigatoriamente",
                          "LRP art. 21; CN-MA art. 386", C_RES,
                          ("{averbacoes}",),
                          ("reconhecimento de filiação", AVERBACAO["selo"])),
    # Só quando a averbação NÃO está transcrita na certidão — 22/10/2026, o
    # oficial: «a expressão elementos à margem do termo só aparece quando
    # houver averbação que não aparece na certidão».
    "cert.inscricao_do_art_21": Req(
        "certidao_nascimento_averbacao_sem_texto",
        "a inscrição «a presente certidão envolve elementos de averbação à "
        "margem do termo», quando a averbação não está transcrita",
        "LRP art. 21, parágrafo único; CN-MA art. 386",
        C_RES, ("{averbacoes}",),
        ("a presente certidão envolve elementos de averbação à margem do termo",)),
    "cert.obito": Req(
        "certidao_obito", "nome, CPF, matrícula, data e hora, sexo, idade, "
        "estado civil, cor, naturalidade, domicílio, local, DO, causa e "
        "atestante, sepultamento, filiação", "CNN arts. 472, 473 e 477; LRP art. 80",
        C_RES, NA_TABELA,
        ("CARLA EXEMPLO", "000.000.012-44", MATRICULA,
         "DEZOITO DE OUTUBRO DE DOIS MIL E VINTE E SEIS", "14:00", "FEMININO",
         "76 anos", "viúva", "PARDA", "Cidade Exemplo/MA", "98765432",
         "insuficiência cardíaca", "BEATRIZ EXEMPLO DE SOUZA — CRM-MA 0000",
         "Cemitério Municipal de Cidade Exemplo",
         "JOSE EXEMPLO DE SOUZA e ANA EXEMPLO DE SOUZA")),
    "cert.obito_eleitor_bens_filhos": Req(
        "certidao_obito", "se era eleitor, se deixou bens e filhos (o que o "
        "termo declara)", "LRP art. 21 c/c art. 80, 7º, 10º e 11º; CNN art. 472",
        C_RES, NA_TABELA, ("ELEITOR", "BENS", "MARIO EXEMPLO DOS SANTOS, com 50 anos")),
    "cert.casamento": Req(
        "certidao_casamento", "nomes, CPF, matrícula, data, regime, nomes "
        "adotados, nascimento, naturalidade, estado civil anterior e filiação "
        "de cada cônjuge", "LRP art. 70; CNN arts. 472, 473 e 477", C_RES,
        NA_TABELA,
        ("MARIO EXEMPLO DOS SANTOS e BEATRIZ EXEMPLO DE SOUZA", MATRICULA,
         "VINTE DE OUTUBRO DE DOIS MIL E VINTE E SEIS", "SEPARAÇÃO",
         "BEATRIZ EXEMPLO DE SOUZA DOS SANTOS", "divorciado", "solteira",
         "ANA EXEMPLO DOS SANTOS", "MARIA EXEMPLO DE SOUZA")),
    "cert.natimorto": Req("certidao_natimorto", "o natimorto, a DO, o registro",
                          "LRP art. 53, § 1º; CNN art. 479-A", C_RES, NA_TABELA,
                          ("NATIMORTO DE BEATRIZ EXEMPLO DE SOUZA", "11112222",
                           "LIVRO\n1", "TERMO\n1")),
    "cert.livro_e": Req(
        "certidao_livro_e_interdicao", "a espécie, o título registrado (sentença, "
        "juízo, data), o curador e os limites", "LRP arts. 19, 21 e 92", C_RES,
        NA_TABELA, ("INTERDIÇÃO", "Vara Única da Comarca de Cidade Exemplo",
                    "BEATRIZ EXEMPLO DE SOUZA", "atos de disposição patrimonial")),
    "cert.inteiro_teor": Req(
        "inteiro_teor", "serventia (CNS, município), espécie, nome, matrícula, "
        "livro, folha e termo", "LRP art. 19, § 1º; CNN art. 473; CN-MA art. 378",
        C_IT, ("{lugar}", "{cns}", "{especie}", "{nome}", "{matricula}", "{onde}"),
        ("Cidade Exemplo/MA", "CNS 000000", "nascimento", "PEDRO EXEMPLO DOS SANTOS",
         MATRICULA, "livro 1, folha 1, termo 1")),
    "cert.habilitacao": Req(
        "certidao_habilitacao", "nubentes, regime, edital, validade de 90 dias "
        "e quem assina", "CC arts. 1.531 e 1.532; LRP art. 67, § 1º; CN-MA "
        "art. 272", C_HAB,
        ("{nubente1_nome}", "{nubente2_nome}", "{regime}", "{edital_em}",
         "{vale_ate}", "{assinante}"),
        ("MARIO EXEMPLO DOS SANTOS", "BEATRIZ EXEMPLO DE SOUZA",
         "01/09/2026", "07/12/2026", "artigo 1.532")),
    "edital.proclamas": Req(
        "edital_proclamas", "nome, estado civil, filiação, cidade e "
        "circunscrição do domicílio dos noivos", "CNN art. 122; LRP art. 67, § 1º",
        "RC_EDITAL_PROCLAMAS", ("{nubente1_nome}", "{nubente2_nome}",
                                "{estado_civil}", "{filiacao}", "{domicilio}"),
        ("MARIO EXEMPLO DOS SANTOS", "DIVORCIADO", "SOLTEIRA")),
}


def _casos():
    for nome, r in MATRIZ.items():
        marcas = ([pytest.mark.xfail(strict=True, reason=r.defeito)]
                  if r.defeito else [])
        yield pytest.param(nome, r, id=nome, marks=marcas)


def _padrao(chave: str) -> str:
    return (PASTA / f"{chave}.txt").read_text(encoding="utf-8")


@pytest.mark.parametrize("nome, req", list(_casos()))
def test_o_modelo_da_casa_tem_o_campo_que_a_lei_exige(nome, req):
    """Cada claro `{campo}` está no padrão, e cada peça `__peca` existe."""
    padrao = _padrao(req.modelo)
    faltam = []
    for campo in req.campos:
        if campo.startswith("__"):
            if not (PASTA / f"{req.modelo}{campo}.txt").is_file():
                faltam.append(campo)
        elif campo not in padrao:
            faltam.append(campo)
    assert not faltam, (f"{req.modelo} não tem {faltam} — {req.elemento} "
                        f"({req.artigo})")
    if req.defeito:
        # O claro existe e o elemento ainda não sai: o defeito é do que o
        # montador põe nele, e quem prova é o outro teste desta linha.
        _confere_o_montado(req)


def _confere_o_montado(req: Req) -> None:
    texto = _montar(req.montado)
    assert texto.strip(), f"{req.montado} saiu vazio"
    faltam = [e for e in req.esperado if e not in texto]
    assert not faltam, (f"{req.montado} não traz {faltam} — {req.elemento} "
                        f"({req.artigo}): {texto}")


@pytest.mark.parametrize("nome, req", list(_casos()))
def test_o_documento_montado_traz_o_elemento_que_a_lei_exige(nome, req):
    _confere_o_montado(req)


def test_todo_termo_e_certidao_do_rcpn_esta_na_matriz():
    """Um papel novo de termo ou certidão sem linha na matriz é papel que
    ninguém conferiu contra a lei."""
    papeis = {p.stem for p in PASTA.glob("RC_*.txt") if "__" not in p.stem
              and p.stem.startswith(("RC_TERMO_", "RC_CERTIDAO_",
                                     "RC_EDITAL_PROCLAMAS"))}
    na_matriz = {r.modelo for r in MATRIZ.values()}
    # A folha do edital é a moldura do teor publicado (o teor é o da linha
    # `edital.proclamas`), e não papel com elemento próprio.
    assert papeis - na_matriz <= {"RC_EDITAL_PROCLAMAS_FOLHA"}, papeis - na_matriz


def test_nenhum_documento_montado_sai_com_claro_ou_none():
    """«Sem campo vazio, None nem marcador de modelo sobrando» — em todos os
    documentos que a matriz monta com o contexto completo."""
    for qual in sorted({r.montado for r in MATRIZ.values()}):
        # A LINHA DE ASSINATURA não é claro: é onde quem assina assina, com o
        # nome embaixo (a certidão de habilitação).
        texto = re.sub(r"_{10,}(?=\s*MARIO EXEMPLO DOS SANTOS)", "",
                       _montar(qual))
        assert not re.search(r"\bNone\b|\{\{|\}\}|\{[a-z_]+\}|_{4,}", texto), \
            f"{qual}: {texto}"


# ------------------------------------------ as regras das frases novas (LD01)


def test_no_tardio_a_testemunha_sai_uma_vez_so():
    """O tardio nomeia e qualifica as testemunhas do requerimento (CN-MA art.
    249, II); o claro `{testemunhas}` do LD01 (LRP art. 54, 9º) não as repete
    — e o termo do nascimento dentro do prazo continua com as duas."""
    tardio = _montar("termo_nascimento_tardio")
    assert tardio.count("CARLA EXEMPLO") == 1 and tardio.count("PEDRO EXEMPLO,") == 1
    assert "Testemunhas do assento" not in tardio
    no_prazo = _montar("termo_nascimento")
    assert "Testemunhas do assento" in no_prazo and "fora do prazo" not in no_prazo


def test_a_frase_dos_gemeos_concorda_com_o_sexo_e_sem_a_ordem_diz_so_o_fato():
    """LRP art. 54, 3º («o fato de ser gêmeo») e art. 63 (a ordem, no assento
    de cada um). O código do IBGE diz SE é gêmeo (2, 3); a ordem é outra
    pergunta (`gemeo_ordem`), e sem ela a frase não inventa uma. Parto único
    (1), ignorado (9) ou não informado: nem menção nem espaço (ordem do
    oficial de 30/08/2026)."""
    menina = {"papel": "REGISTRADO", "sexo": "F"}
    menino = {"papel": "REGISTRADO", "sexo": "M"}
    assert ML.frase_dos_gemeos({"ibge_gemeo": 2, "gemeo_ordem": 2}, menina) == (
        ", gêmea, a 2ª na ordem de nascimento")
    assert ML.frase_dos_gemeos({"ibge_gemeo": "3", "gemeo_ordem": 1}, menino) == (
        ", gêmeo, o 1º na ordem de nascimento")
    assert ML.frase_dos_gemeos({"ibge_gemeo": 2}, menina) == ", gêmea"
    for nao in ({"ibge_gemeo": 1, "gemeo_ordem": 1}, {"ibge_gemeo": 9}, {}):
        assert ML.frase_dos_gemeos(nao, menino) == "", nao


def test_o_natimorto_nao_tem_dnv_nem_primeiro_registro_e_o_nascimento_nao_nasce_morto():
    """CNN art. 479-A (sem CPF) e LRP art. 53: o natimorto apresenta a
    Declaração de Óbito, e não a DNV; e «nasceu morta» só sai nele — o termo
    de nascimento continua «nasceu uma criança»."""
    nati = _montar("termo_natimorto")
    assert "Declaração de Óbito n.º 11112222" in nati
    assert "DNV" not in nati and "primeiro registro" not in nati
    nasc = _montar("termo_nascimento")
    assert "nasceu uma criança" in nasc and "morta" not in nasc


def test_o_termo_de_obito_de_um_falecido_continua_no_masculino():
    """A concordância vem do sexo (LD01): o falecido do sexo M continua «Filho
    de», «Sepultado», «Era eleitor»; e a idade abaixo de um ano não vira «0
    anos»."""
    pessoas = [dict(PESSOAS_DO_OBITO[0], sexo="M", nome="PEDRO EXEMPLO"),
               *PESSOAS_DO_OBITO[1:]]
    texto = _limpo(ML.montar_obito_do_assento(
        OBITO, pessoas, marcas=MARCAS_DO_OBITO, sv=SV, **QUEM)["texto"])
    for masculino in ("Filho de", "Sepultado em", "Era eleitor.", "do sexo masculino"):
        assert masculino in texto, masculino
    bebe = [dict(PESSOAS_DO_OBITO[0], data_nascimento="2026-06-01")]
    assert "com menos de um ano de idade" in _limpo(ML.montar_obito_do_assento(
        OBITO, bebe, marcas=MARCAS_DO_OBITO, sv=SV, **QUEM)["texto"])


def test_sem_data_do_fato_o_termo_de_casamento_nao_inventa_a_celebracao():
    """`{frase_da_celebracao}` é opcional: sem a data do fato não há menção, e
    o termo lê-se inteiro sem ela (LRP art. 70, 4º, pede a data — a tela a
    pergunta; o acervo pode não tê-la)."""
    sem_data = {k: v for k, v in CASAMENTO.items() if k != "data_fato"}
    texto = _limpo(ML.montar_casamento_do_assento(
        sem_data, PESSOAS_DO_CASAMENTO, documentos=DOCUMENTOS, sv=SV,
        **QUEM)["texto"])
    assert "foram declarados casados sob o regime" in texto



# ------------------------------------- a inscrição do art. 21 — 22/10/2026
#
# «[a escrevente] emitiu uma certidao agora que diz que existem elementos de
#  averbacao a margem do termo [...] a expressao elementos a margem do termo
#  so aparecem quando houver averbacao que nao aparece na certidao. A
#  averbacao do CPF consta na certidao, por isso nao deve aparecer essa
#  expressao» — o oficial (certidão 159/2026).

INSCRICAO = "a presente certidão envolve elementos de averbação à margem do termo"
AVERBACAO_DO_CPF = {"tipo": "AVERBACAO", "selo": "AVERBA000000TESTE00000000002",
                    "teor": "Averbo neste assento o CPF n. 000.000.014-06.",
                    "fundamento": "art. 347 do Código de Normas do TJMA"}


def test_a_averbacao_transcrita_nao_leva_a_inscricao():
    teor = _certidao(NASCIMENTO, PESSOAS_DO_NASCIMENTO, [AVERBACAO_DO_CPF])
    assert "Averbo neste assento o CPF n. 000.000.014-06." in teor
    assert INSCRICAO not in teor
    assert "Averbação: Averbo" in teor           # o rótulo com acento


def test_a_averbacao_sem_texto_leva_a_inscricao():
    teor = _certidao(NASCIMENTO, PESSOAS_DO_NASCIMENTO,
                     [AVERBACAO_DO_CPF, dict(AVERBACAO, teor="")])
    assert INSCRICAO in teor


def test_a_anotacao_nao_e_alteracao_e_nao_leva_a_inscricao():
    anot = {"tipo": "ANOTACAO", "teor": ""}
    assert not RCE.alteracoes_fora_da_certidao([anot])
    assert RCE.rotulo_do_ato("ANOTACAO") == "Anotação"
    assert RCE.rotulo_do_ato("RETIFICACAO") == "Retificação"
