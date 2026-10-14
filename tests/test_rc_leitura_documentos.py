"""A leitura dos documentos do registro — `rc_leitura_documentos` e a tela.

Nada aqui fala com a rede: a IA é um `conversar` de mentira que responde pelo
molde que recebeu. Os dados são FICTÍCIOS — os documentos reais da casa servem
ao ensaio (`tmp/ensaio_leitura_documentos.py`, que não viaja no pacote), e não a teste versionado.
"""
from __future__ import annotations

import json
import re
import sqlite3

import pytest

import rc_leitura_documentos as LEIT

CPF_MAE = "00000000191"          # CPF de teste com dígito válido
CPF_PAI_ERRADO = "12345678900"   # dígito não fecha

DNV = {
    "numero_dnv": "30-12345678-9", "cartao_sus_rn": None, "nome_rn": "Maria Exemplo da Silva",
    "data_nascimento": "02/03/2026", "hora_nascimento": "10:15", "sexo": "Feminino",
    "raca_cor_rn": "Parda", "peso_gramas": "3100", "tipo_gravidez": "Única",
    "local_ocorrencia": "Hospital", "estabelecimento": "Hospital Municipal Exemplo",
    "endereco_ocorrencia": "Rua das Flores", "numero_ocorrencia": "10",
    "bairro_ocorrencia": "Centro", "municipio_ocorrencia": "IMPERATRIZ", "uf_ocorrencia": "MA",
    "nome_mae": "Ana Exempla da Silva", "cartao_sus_mae": "123456789012345",
    "escolaridade_mae": "Médio", "ocupacao_mae": "Lavradora", "nascimento_mae": "05/06/2000",
    "idade_mae": "24", "naturalidade_mae": "Cidade Exemplo-MA", "situacao_conjugal_mae": "Solteira",
    "raca_cor_mae": "Parda", "logradouro_residencia": "Rua Projetada (?)",
    "numero_residencia": "S/N", "bairro_residencia": "VILA NOVA",
    "municipio_residencia": "CIDADE EXEMPLO", "uf_residencia": "MA",
}
IDENTIDADES = {"pessoas": [
    {"tipo_documento": "RG", "nome": "ANNA EXEMPLA DA SILVA", "numero_documento": "0123",
     "orgao_emissor": "SSP/MA", "cpf": "000.000.001-91", "data_nascimento": "05/06/2000",
     "naturalidade": "CIDADE EXEMPLO - MA", "filiacao_pai": "JOSE EXEMPLO DA SILVA",
     "filiacao_mae": "MARIA EXEMPLA SANTOS"},
    {"tipo_documento": "RG", "nome": "PEDRO TESTE SOUSA", "numero_documento": "0456",
     "orgao_emissor": "SSP/MA", "cpf": CPF_PAI_ERRADO, "data_nascimento": "01/01/1998",
     "naturalidade": "TUCUMA - PA", "filiacao_pai": "JOAO TESTE SOUSA",
     "filiacao_mae": "RITA TESTE LIMA"},
]}
DO = {
    "numero_do": "12345678-0", "nome_falecido": "Jose Exemplo Neto", "nome_pai": "Joao Exemplo",
    "nome_mae": "Rosa Exemplo", "data_obito": "10/09/2026", "hora_obito": "03:20",
    "sexo": "Masculino", "raca_cor": "Branca", "data_nascimento": "01/01/1950", "idade": "76",
    "estado_civil": "Viúvo", "ocupacao": "Aposentado", "naturalidade": "Cidade Exemplo-MA",
    "local_ocorrencia": "Domicílio", "estabelecimento": None,
    "endereco_ocorrencia": "Rua A, 1", "municipio_ocorrencia": "Cidade Exemplo", "uf_ocorrencia": "MA",
    "causa_a": "Insuficiência respiratória", "causa_b": "Pneumonia", "tipo_morte": "Natural",
    "medico_nome": "Dra. Clara Teste", "medico_crm": "CRM-MA 1234",
}


def _doc(tipo, dados, n=1, arquivo="docs.pdf"):
    return {"arquivo": arquivo, "n": n, "attachment_id": None, "tipo": tipo, "dados": dados}


# -------------------------------------------------------------- o que se calcula

def test_cartao_sus_e_datas():
    assert LEIT.cns_valido("700123456789010")
    assert LEIT.cns_valido("500987654321019")       # o cartão novo começa por 5
    assert not LEIT.cns_valido("123456789012345")
    assert LEIT.data_iso("02/03/2026") == "2026-03-02"
    assert LEIT.data_iso("10102003") == "2003-10-10"
    assert LEIT.data_iso("31/02/2026") == ""
    assert LEIT.data_iso("05/06/2000 (?)") == "2000-06-05"


def test_nome_proprio_deixa_as_particulas_em_minuscula():
    assert LEIT._capitalizar("ANA DE SOUSA DOS SANTOS") == "Ana de Sousa dos Santos"
    assert LEIT._capitalizar("Ana de Sousa") == "Ana de Sousa"
    assert LEIT._capitalizar("D'AVILA SANTOS") == "D'Avila Santos"


def test_o_municipio_ganha_o_nome_oficial():
    import sqlite3 as sq
    con = sq.connect(":memory:")
    con.execute("CREATE TABLE ib_municipios (uf TEXT, nome TEXT)")
    con.execute("INSERT INTO ib_municipios VALUES ('PA', 'Tucumã')")
    junto = {"pessoas": [{"nome": "X", "naturalidade_cidade": "Tucuma", "naturalidade_uf": "PA",
                          "cidade": "Lugar Nenhum", "uf": "PA"}]}
    LEIT.corrigir_municipios(junto, LEIT.municipios_oficiais(con))
    assert junto["pessoas"][0]["naturalidade_cidade"] == "Tucumã"
    assert junto["pessoas"][0]["cidade"] == "Lugar Nenhum"      # não achou: fica


def test_nascimento_junta_a_dnv_e_os_documentos():
    junto = LEIT.juntar_nascimento([_doc("DNV", DNV), _doc("IDENTIDADE", IDENTIDADES, 2)])
    v = junto["valores"]
    assert v["especie"] == "NASCIMENTO" and v["nome"] == "Maria Exemplo da Silva"
    assert v["data_fato"] == "2026-03-02" and v["hora_fato"] == "10:15"
    assert v["cor_raca"] == "PARDA" and v["ibge_local_nascimento"] == "1" and v["ibge_gemeo"] == "1"
    assert v["local_fato_endereco"] == "Rua das Flores, 10, Centro, Imperatriz/MA"
    por_papel = {p["papel"]: p for p in junto["pessoas"]}
    assert por_papel["REGISTRADO"]["sexo"] == "F"
    mae = por_papel["MAE"]
    # vale a grafia do documento de identidade, e o CPF dele
    assert mae["nome"] == "Anna Exempla da Silva"
    assert (mae["documento_tipo"], mae["documento_numero"]) == ("CPF", CPF_MAE)
    assert mae["cidade"] == "Cidade Exemplo" and mae["bairro"] == "Vila Nova"
    assert por_papel["AVO_MATERNO"]["nome"] == "Jose Exemplo da Silva"
    assert por_papel["AVO_MATERNA"]["nome"] == "Maria Exempla Santos"
    assert por_papel["PAI"]["nome"] == "Pedro Teste Sousa"
    assert por_papel["AVO_PATERNO"]["nome"] == "Joao Teste Sousa"
    textos = " | ".join(a["texto"] for a in junto["conferencia"])
    assert "não são iguais letra a letra" in textos           # Ana × Anna
    assert "A idade da mãe no parto não fecha" in textos       # 24 × 25
    assert "Cartão SUS da mãe" in textos                       # dígito
    assert "O CPF de PEDRO TESTE SOUSA" in textos              # dígito
    assert "entrou como PAI" in textos                         # dedução avisada
    assert "naturalidade é escolha do declarante" in textos    # art. 54, § 4º
    assert "Residência da mãe: a leitura ficou em dúvida" in textos


def test_nascimento_sem_dnv_recusa():
    with pytest.raises(LEIT.LeituraError, match="não há uma DNV"):
        LEIT.juntar_nascimento([_doc("IDENTIDADE", IDENTIDADES)])


def test_a_mesma_pessoa_em_varios_documentos_e_uma_so():
    rg = {"pessoas": [{"nome": "JOSE EXEMPLO NETO", "cpf": CPF_MAE, "data_nascimento": "01/01/1950"},
                      {"nome": "Rita Declarante", "cpf": None}]}
    cartao_cpf = {"pessoas": [{"nome": "JOSÉ EXEMPLO NETO", "cpf": "000.000.001-91"}]}
    do = dict(DO, nome_falecido="Jose Exenplo Neto")      # a DO manuscrita, lida torta
    junto = LEIT.juntar_obito([_doc("DO", do), _doc("IDENTIDADE", rg, 2),
                               _doc("IDENTIDADE", cartao_cpf, 3)])
    por_papel = {p["papel"]: p for p in junto["pessoas"]}
    assert por_papel["FALECIDO"]["nome"] == "Jose Exemplo Neto"      # vale o documento
    assert por_papel["DECLARANTE"]["nome"] == "Rita Declarante"      # e não «mais de uma»
    textos = " | ".join(a["texto"] for a in junto["conferencia"])
    assert "O nome do falecido na DO" in textos


def test_obito_junta_a_do():
    junto = LEIT.juntar_obito([_doc("DO", DO)])
    v = junto["valores"]
    assert v["especie"] == "OBITO" and v["data_fato"] == "2026-09-10"
    assert v["causa_morte"] == "Insuficiência respiratória; Pneumonia"
    assert v["ibge_local_obito"] == "3" and v["ibge_natureza_obito"] == "1"
    assert v["atestante"] == "Dra. Clara Teste"
    fal = junto["pessoas"][0]
    assert fal["papel"] == "FALECIDO" and fal["estado_civil"] == "viúvo"
    assert {p["papel"] for p in junto["pessoas"]} >= {"FALECIDO", "PAI", "MAE"}


# ------------------------------------------------- a rede, de mentira

def _png(caminho):
    from PIL import Image
    Image.new("RGB", (60, 80), "white").save(caminho)
    return caminho


class IA:
    """Responde pela instrução que recebe, e anota quem pediu o quê."""

    def __init__(self, tipos):
        self.tipos = tipos
        self.pedidos = []

    def __call__(self, pasta, *, provedor, sistema, conversa, ferramentas, modelo,
                 maximo_de_saida):
        self.pedidos.append({"modelo": modelo, "sistema": sistema,
                             "imagens": len(conversa[0]["imagens"])})
        if sistema == LEIT.INSTRUCAO_TRIAGEM:
            corpo = {"paginas": [{"n": i, "tipo": t} for i, t in enumerate(self.tipos, 1)]}
        elif "Nascido Vivo" in sistema:
            corpo = DNV
        else:
            corpo = IDENTIDADES
        return {"texto": json.dumps(corpo), "entrada": 1000, "saida": 200, "modelo": modelo}


def test_ler_tria_e_manda_cada_pagina_ao_modelo_certo(tmp_path):
    arquivos = [{"caminho": str(_png(tmp_path / f"{i}.png")), "nome": f"{i}.png"}
                for i in range(3)]
    ia = IA(["DNV", "IDENTIDADE", "OUTRO"])
    em_uso = {"triagem": "T", "manuscrito": "FORTE", "impresso": "MEDIO"}
    lido = LEIT.ler(ia, tmp_path, em_uso, arquivos)
    assert [p["tipo"] for p in lido["paginas"]] == ["DNV", "IDENTIDADE", "OUTRO"]
    # a triagem vê as três de uma vez; TODA página é lida («tudo que é
    # preenchido precisa ser lido», 12/10/2026), e a identidade vai ao forte
    assert ia.pedidos[0]["modelo"] == "T" and ia.pedidos[0]["imagens"] == 3
    por_tipo = {p["tipo"]: p["modelo"] for p in lido["envios"][1:]}
    assert por_tipo == {"DNV": "FORTE", "IDENTIDADE": "FORTE", "OUTRO": "MEDIO"}
    assert [d["tipo"] for d in lido["documentos"]] == ["DNV", "IDENTIDADE", "OUTRO"]
    assert len(lido["envios"]) == 4


def test_o_simulador_do_sandbox_e_dito_e_nao_culpa_o_documento(tmp_path):
    # O simulado de IA não lê; sem a recusa a tela dizia «não há uma DNV».
    def simulador(pasta, **_):
        return {"texto": LEIT.MARCA_DO_SIMULADOR + " Não há resposta de IA aqui.",
                "entrada": 0, "saida": 0, "modelo": "simulador-do-sandbox"}
    arquivos = [{"caminho": str(_png(tmp_path / "1.png")), "nome": "1.png"}]
    em_uso = {"triagem": "T", "manuscrito": "FORTE", "impresso": "MEDIO"}
    with pytest.raises(LEIT.LeituraError, match="sistema de teste"):
        LEIT.ler(simulador, tmp_path, em_uso, arquivos)


def test_o_pedido_de_zero_data_retention_esta_registrado():
    assert LEIT.ZERO_DATA_RETENTION["situacao"] in ("A PEDIR", "PEDIDO", "ACORDADO", "NEGADO")
    assert "outros_campos" in LEIT.INSTRUCAO_LEITURA


def test_o_modulo_nao_lavra_nao_sela_nao_cobra():
    proibidos = ("lavrar", "selar", "cobrar", "numerar")
    publicos = [n for n in dir(LEIT) if not n.startswith("_")]
    assert not [n for n in publicos if any(p in n.lower() for p in proibidos)]


# ------------------------------------------------------------- a tela

def _token(html):
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


def test_da_tela_ao_rascunho(cg_casa_logada, monkeypatch, tmp_path):
    import agente_provedores as AP
    casa = cg_casa_logada
    c = casa["c"]
    r = c.get("/rcpn/leitura")
    assert r.status_code == 200 and "Ler documentos do registro" in r.get_data(as_text=True)
    ia = IA(["DNV", "IDENTIDADE"])
    monkeypatch.setattr(AP, "conversar", ia)
    monkeypatch.setattr(AP, "tem_chave", lambda *a, **k: True)
    from io import BytesIO
    from PIL import Image
    arquivos = []
    for i in range(2):
        b = BytesIO()
        Image.new("RGB", (60, 80), "white").save(b, format="PNG")
        b.seek(0)
        arquivos.append((b, f"doc{i}.png"))
    r = c.post("/rcpn/leitura", data={"csrf_token": _token(r.get_data(as_text=True)),
                                      "especie": "NASCIMENTO", "arquivos": arquivos},
               content_type="multipart/form-data")
    assert r.status_code == 302 and "/rcpn/leitura/" in r.headers["Location"]
    ficha = c.get(r.headers["Location"])
    html = ficha.get_data(as_text=True)
    assert ficha.status_code == 200 and "Maria Exemplo da Silva" in html
    assert "não são iguais letra a letra" in html
    with sqlite3.connect(casa["banco"]) as con:
        leitura_id, situacao, anexos = con.execute(
            "SELECT id, situacao, (SELECT count(*) FROM attachments WHERE "
            "entity_type='RC_LEITURA' AND entity_id=rc_leituras.id) FROM rc_leituras").fetchone()
    assert situacao == "LIDA" and anexos == 2
    r = c.post(f"/rcpn/leitura/{leitura_id}/rascunho", data={"csrf_token": _token(html)})
    assert r.status_code == 302 and "rascunho_id=" in r.headers["Location"]
    tela = c.get(r.headers["Location"]).get_data(as_text=True)
    assert "Maria Exemplo da Silva" in tela and CPF_MAE in tela
    with sqlite3.connect(casa["banco"]) as con:
        assert con.execute("SELECT situacao FROM rc_leituras").fetchone()[0] == "NO_RASCUNHO"
        assert con.execute("SELECT count(*) FROM rc_assentos WHERE nome = ?",
                           ("Maria Exemplo da Silva",)).fetchone()[0] == 0   # não lavrou


# ------------------------------------------------- a habilitação de casamento
# 12/10/2026: «falta casamento». O casamento desta casa começa pela habilitação.
CPF_NOIVA = "00000000272"        # dígito válido
REQUERIMENTO = {
    "nubentes": [
        {"nome": "CARLOS TESTE RIBEIRO", "nome_apos_casamento": None, "cpf": None,
         "estado_civil": "Divorciado", "profissao": "Lavrador",
         "endereco": "Rua B, 20, Centro, Cidade Exemplo/MA"},
        {"nome": "Bruna Exemplo Costa", "nome_apos_casamento": "Bruna Exemplo Costa Ribeiro",
         "estado_civil": "Solteira", "profissao": "Professora"},
    ],
    "regime_bens": "Comunhão parcial de bens", "tipo_casamento": "Civil",
    "testemunhas": [{"nome": "Lucas Testemunha Um", "cpf": "000.000.001-91"},
                    {"nome": "Rita Testemunha Dois", "cpf": None}],
}
CERT_NOIVA = {"especie": "Nascimento", "nomes": ["BRUNA EXEMPLO COSTA"],
              "data_nascimento": "10/02/1999", "naturalidade": "CIDADE EXEMPLO - MA",
              "pai": "JOAO EXEMPLO COSTA", "mae": "MARIA EXEMPLO COSTA", "sexo": "Feminino"}
CERT_CASAMENTO_DIVORCIADO = {"especie": "Casamento",
                             "nomes": ["CARLOS TESTE RIBEIRO", "ANA ANTIGA SILVA"],
                             "averbacoes": "Averbação de DIVÓRCIO consensual, 2019."}
IDS_HAB = {"pessoas": [
    {"tipo_documento": "CIN", "nome": "BRUNA EXEMPLO COSTA", "cpf": "000.000.002-72",
     "data_nascimento": "10/02/1999", "naturalidade": "CIDADE EXEMPLO - MA",
     "filiacao_pai": "JOAO EXEMPLO COSTA", "filiacao_mae": "MARIA EXEMPLO COSTA",
     "sexo": "F"},
    {"tipo_documento": "RG", "nome": "CARLOS TESTE RIBEIRO", "cpf": "000.000.001-91",
     "data_nascimento": "01/05/1990", "naturalidade": "TUCUMA - PA",
     "filiacao_pai": "PEDRO RIBEIRO", "filiacao_mae": "LUZIA RIBEIRO", "sexo": "M"},
]}


def test_habilitacao_junta_requerimento_certidoes_e_documentos():
    junto = LEIT.juntar_habilitacao([
        _doc("HABILITACAO", REQUERIMENTO, 1), _doc("CERTIDAO", CERT_NOIVA, 2),
        _doc("CERTIDAO", CERT_CASAMENTO_DIVORCIADO, 3), _doc("IDENTIDADE", IDS_HAB, 4)])
    v = junto["valores"]
    assert v["tipo"] == "CIVIL" and v["regime"] == "COMUNHAO_PARCIAL"
    assert v["nubente1_nome"] == "Carlos Teste Ribeiro"
    assert v["nubente1_estado_civil"] == "DIVORCIADO"
    assert v["nubente1_profissao"] == "lavrador"
    assert v["nubente1_documento"] == "00000000191" and v["nubente1_sexo"] == "M"
    assert v["nubente1_naturalidade"] == "Tucuma/PA" and v["nubente1_pai"] == "Pedro Ribeiro"
    assert v["nubente2_nome"] == "Bruna Exemplo Costa"
    assert v["nubente2_nome_pos"] == "Bruna Exemplo Costa Ribeiro"
    assert v["nubente2_documento"] == CPF_NOIVA and v["nubente2_nascimento"] == "1999-02-10"
    assert v["nubente2_mae"] == "Maria Exemplo Costa"
    assert "Lucas Testemunha Um" in v["observacao"]
    papeis = [p["papel"] for p in junto["pessoas"]]
    assert papeis == ["NUBENTE1", "NUBENTE2", "TESTEMUNHA", "TESTEMUNHA"]
    textos = " ".join(a["texto"] for a in junto["conferencia"])
    # o divorciado tem a prova da dissolução; nada aqui é impedimento
    assert "prova da dissolução" not in textos
    assert not any(a["gravidade"] == "IMPEDIMENTO" for a in junto["conferencia"])


def test_casamento_anterior_sem_divorcio_e_impedimento():
    sem_divorcio = dict(CERT_CASAMENTO_DIVORCIADO, averbacoes=None)
    junto = LEIT.juntar_habilitacao([
        _doc("HABILITACAO", REQUERIMENTO, 1), _doc("CERTIDAO", sem_divorcio, 2)])
    impedimentos = [a for a in junto["conferencia"] if a["gravidade"] == "IMPEDIMENTO"]
    assert impedimentos and "1.521, VI" in impedimentos[0]["texto"]


def test_sem_requerimento_os_nubentes_vem_das_certidoes_e_a_testemunha_nao_entra():
    cert_noivo = {"especie": "Nascimento", "nomes": ["CARLOS TESTE RIBEIRO"],
                  "data_nascimento": "01/05/1990"}
    testemunha = {"pessoas": [{"nome": "LUCAS TESTEMUNHA UM", "cpf": None}]}
    junto = LEIT.juntar_habilitacao([
        _doc("CERTIDAO", CERT_NOIVA, 1), _doc("CERTIDAO", cert_noivo, 2),
        _doc("IDENTIDADE", IDS_HAB, 3), _doc("IDENTIDADE", testemunha, 4)])
    v = junto["valores"]
    assert {v["nubente1_nome"], v["nubente2_nome"]} == {"Bruna Exemplo Costa",
                                                       "Carlos Teste Ribeiro"}
    assert [p["nome"] for p in junto["pessoas"] if p["papel"] == "TESTEMUNHA"] == \
        ["Lucas Testemunha Um"]


def test_habilitacao_sem_nubente_recusa():
    with pytest.raises(LEIT.LeituraError, match="nubentes"):
        LEIT.juntar_habilitacao([_doc("RESIDENCIA", {"logradouro": "Rua X"})])


class IAPorMolde:
    """Responde pelo molde que a instrução pede — a triagem diz os tipos."""

    def __init__(self, tipos, por_molde):
        self.tipos, self.por_molde = tipos, por_molde

    def __call__(self, pasta, *, provedor, sistema, conversa, ferramentas, modelo,
                 maximo_de_saida):
        if sistema == LEIT.INSTRUCAO_TRIAGEM:
            corpo = {"paginas": [{"n": i, "tipo": t} for i, t in enumerate(self.tipos, 1)]}
        else:
            corpo = next(v for chave, v in self.por_molde.items() if chave in sistema)
        return {"texto": json.dumps(corpo), "entrada": 900, "saida": 150, "modelo": modelo}


def test_da_tela_a_habilitacao_preenchida(cg_casa_logada, monkeypatch):
    import agente_provedores as AP
    casa = cg_casa_logada
    c = casa["c"]
    r = c.get("/rcpn/leitura")
    assert "Casamento (habilitação)" in r.get_data(as_text=True)
    ia = IAPorMolde(["HABILITACAO", "CERTIDAO", "IDENTIDADE"], {
        "habilitação de casamento": REQUERIMENTO,
        "Certidão de registro civil": CERT_NOIVA,
        "Documento de identidade": IDS_HAB})
    monkeypatch.setattr(AP, "conversar", ia)
    monkeypatch.setattr(AP, "tem_chave", lambda *a, **k: True)
    from io import BytesIO
    from PIL import Image
    arquivos = []
    for i in range(3):
        b = BytesIO()
        Image.new("RGB", (60, 80), "white").save(b, format="PNG")
        b.seek(0)
        arquivos.append((b, f"hab{i}.png"))
    r = c.post("/rcpn/leitura", data={"csrf_token": _token(r.get_data(as_text=True)),
                                      "especie": "HABILITACAO", "arquivos": arquivos},
               content_type="multipart/form-data")
    ficha = c.get(r.headers["Location"])
    html = ficha.get_data(as_text=True)
    assert ficha.status_code == 200 and "Casamento (habilitação)" in html
    with sqlite3.connect(casa["banco"]) as con:
        leitura_id, situacao = con.execute(
            "SELECT id, situacao FROM rc_leituras ORDER BY id DESC").fetchone()
    assert situacao == "LIDA"
    r = c.post(f"/rcpn/leitura/{leitura_id}/rascunho", data={"csrf_token": _token(html)})
    assert r.status_code == 302
    assert "/rcpn/habilitacoes/nova?rascunho_id=" in r.headers["Location"]
    tela = c.get(r.headers["Location"]).get_data(as_text=True)
    assert 'value="Bruna Exemplo Costa"' in tela and CPF_NOIVA in tela
    assert 'value="COMUNHAO_PARCIAL" selected' in tela
    assert 'value="DIVORCIADO" selected' in tela
    with sqlite3.connect(casa["banco"]) as con:
        assert con.execute("SELECT count(*) FROM hc_habilitacoes").fetchone()[0] == 0
