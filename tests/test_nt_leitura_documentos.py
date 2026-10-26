"""A leitura de documentos do balcão das Notas — `nt_leitura_documentos`, a tela,
e o motor comum (`leitura_ia`) que saiu de dentro do Registro Civil.

«autorizo ia sem mascara. trabalharemos com o prazo de retencao de 30 dias da
 api» — o oficial, 26/10/2026.

Nada aqui fala com a rede: a IA é um `conversar` de mentira que responde pelo
molde que recebeu, como nos testes do RCPN. Os dados são FICTÍCIOS (mario,
beatriz, carla; CPFs de teste com dígito válido).
"""
from __future__ import annotations

import json
import re
import sys
from io import BytesIO
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import leitura_ia as LIA                         # noqa: E402
import nt_leitura_documentos as NTL              # noqa: E402
import rc_leitura_documentos as LEIT             # noqa: E402
from bd_nativo import banco                      # noqa: E402

CPF_MARIO = "00000000191"
CPF_BEATRIZ = "00000000272"
CPF_CARLA = "00000000353"
RENAVAM_BOM = "00123456789"       # o dígito fecha
RENAVAM_RUIM = "00123456780"      # o dígito não fecha

RG_MARIO = {"pessoas": [
    {"tipo_documento": "RG", "nome": "MARIO EXEMPLO DOS SANTOS", "numero_documento": "0123456",
     "orgao_emissor": "SSP/MA", "cpf": "000.000.001-91", "data_nascimento": "05/06/1980",
     "naturalidade": "CIDADE EXEMPLO - MA", "filiacao_pai": "JOSE EXEMPLO DOS SANTOS",
     "filiacao_mae": "MARIA EXEMPLA DOS SANTOS (?)", "data_expedicao": "10/01/2015",
     "nacionalidade": "brasileira", "titulo_eleitor": "1234 5678 9012"}]}
CNH_MARIO = {"pessoas": [
    {"tipo_documento": "CNH", "nome": "MARIO EXEMPLO DOS SANTOS", "numero_documento": "0123456",
     "orgao_emissor": "SSP MA", "cpf": CPF_MARIO, "data_nascimento": "05/06/1980",
     "data_expedicao": "02/02/2024", "numero_cnh": "00000000000"}]}
RG_BEATRIZ = {"pessoas": [{"tipo_documento": "RG", "nome": "BEATRIZ TESTE LIMA",
                           "cpf": CPF_BEATRIZ, "data_nascimento": "01/01/1990"}]}

ATPV = {"eletronica": "sim", "numero_atpv": "000000000001", "placa": "abc-1d23",
        "renavam": RENAVAM_BOM, "chassi": "9BWZZZ377VT004251", "marca_modelo": "VW/EXEMPLO",
        "ano_fabricacao": "2018", "ano_modelo": "2019", "cor": "BRANCA",
        "municipio": "CIDADE EXEMPLO", "uf": "ma",
        "vendedor_nome": "MARIO EXEMPLO DOS SANTOS", "vendedor_cpf_cnpj": CPF_MARIO,
        "comprador_nome": "CARLA TESTE SOUSA (?)", "comprador_cpf_cnpj": CPF_CARLA,
        "valor_venda": "R$ 25.000,00", "data_venda": "10/10/2026"}
CRLV = {"placa": "ABC1D23", "renavam": RENAVAM_BOM, "chassi": "9BWZZZ377VT004251",
        "proprietario_nome": "MARIO EXEMPLO DOS SANTOS", "proprietario_cpf_cnpj": CPF_MARIO,
        "municipio": "CIDADE EXEMPLO", "uf": "MA"}


def _doc(tipo, dados, n=1, arquivo="docs.pdf"):
    return {"arquivo": arquivo, "n": n, "attachment_id": None, "tipo": tipo, "dados": dados}


def _textos(junto):
    return " | ".join(a["texto"] for a in junto["conferencia"])


# --------------------------------------------- o motor comum e o Registro Civil

def test_o_registro_civil_usa_o_motor_comum_com_os_mesmos_nomes():
    """Os nomes antigos continuam lá, e são os MESMOS objetos do motor — é isso
    que deixa os testes do RCPN valendo como prova de que nada mudou."""
    for nome in ("custo", "modelos", "data_iso", "mesmo_nome", "cpf_valido", "cns_valido",
                 "_capitalizar", "_limpo", "_miniatura", "_pedir", "MARCA_DO_SIMULADOR",
                 "MAXIMO_DE_PAGINAS", "PRECO_POR_MILHAO", "ZERO_DATA_RETENTION",
                 "LeituraError"):
        assert getattr(LEIT, nome) is getattr(LIA, nome), nome
    assert LEIT.TIPOS["IDENTIDADE"] is LIA.TIPO_IDENTIDADE is NTL.TIPOS["IDENTIDADE"]
    assert LEIT.TIPOS["OUTRO"] is LIA.TIPO_OUTRO
    # a retenção é a mesma das duas atribuições, e é a de 30 dias
    assert LIA.RETENCAO_DIAS == 30
    assert LEIT.ZERO_DATA_RETENTION["retencao_padrao_dias"] == "30"


def test_a_frase_do_teto_do_rcpn_nao_mudou(monkeypatch, tmp_path):
    """A frase do teto continua a do Registro Civil, com a DNV e a DO."""
    monkeypatch.setenv("CG_TETO_IA_PAGINAS", "1")
    arquivos = [{"caminho": str(_png(tmp_path / f"{i}.png")), "nome": f"{i}.png"}
                for i in range(2)]
    with pytest.raises(LEIT.LeituraError, match="a DNV, a DO, os documentos de identidade"):
        LEIT.paginas_dos_arquivos(arquivos)
    with pytest.raises(LIA.LeituraError, match="o CRV ou o ATPV"):
        NTL.ler(IA([]), tmp_path, EM_USO, arquivos, destino="VEICULO")


# ------------------------------------------------------------ o cartão

def test_o_cartao_sai_do_rg_e_da_cnh_da_mesma_pessoa():
    junto = NTL.juntar_cartao([_doc("IDENTIDADE", CNH_MARIO, 1),
                               _doc("IDENTIDADE", RG_MARIO, 2)])
    c = junto["campos"]
    assert c["nome"] == "MARIO EXEMPLO DOS SANTOS" and c["documento"] == CPF_MARIO
    assert c["rg"] == "0123456" and c["rg_orgao"] == "SSP/MA"     # o do RG, e não o da CNH
    assert c["rg_emissao"] == "2015-01-10"                        # a emissão da CNH não entra
    assert c["nascimento"] == "1980-06-05" and c["nacionalidade"] == "BRASILEIRA"
    assert c["pai"] == "JOSE EXEMPLO DOS SANTOS"
    assert c["mae"] == "MARIA EXEMPLA DOS SANTOS"                 # sem a marca
    assert c["titulo_eleitor"] == "123456789012"
    assert junto["duvidas"] == ["mae"]                             # e a dúvida fica dita
    assert "Mãe: a leitura ficou em dúvida" in _textos(junto)
    assert junto["de_onde"]["rg_emissao"] == "docs.pdf p2"


def test_duas_pessoas_nos_anexos_nao_se_misturam_num_cartao():
    junto = NTL.juntar_cartao([_doc("IDENTIDADE", RG_MARIO), _doc("IDENTIDADE", RG_BEATRIZ, 2)])
    assert junto["campos"]["nome"] == "MARIO EXEMPLO DOS SANTOS"
    assert junto["campos"]["documento"] == CPF_MARIO
    assert "mais de uma pessoa (BEATRIZ TESTE LIMA)" in _textos(junto)


def test_cpf_que_nao_fecha_e_apontado_e_nao_apagado():
    rg = {"pessoas": [dict(RG_MARIO["pessoas"][0], cpf="000.000.001-90")]}
    junto = NTL.juntar_cartao([_doc("IDENTIDADE", rg)])
    assert junto["campos"]["documento"] == "00000000190"
    assert "não fecha o dígito" in _textos(junto)


def test_sem_documento_de_identidade_a_leitura_recusa():
    with pytest.raises(LIA.LeituraError, match="não achou documento de identidade"):
        NTL.juntar_cartao([_doc("CRLV", CRLV)])


# ------------------------------------------------------------ o veículo

def test_o_veiculo_sai_do_atpv_e_o_crlv_confere():
    junto = NTL.juntar_veiculo([_doc("CRLV", CRLV, 1), _doc("ATPV", ATPV, 2)])
    v = junto["valores"]
    assert junto["transferencia"] == "ATPV_E"
    assert v["placa"] == "ABC1D23" and v["renavam"] == RENAVAM_BOM
    assert v["chassi"] == "9BWZZZ377VT004251"
    assert v["vendedor_documento"] == CPF_MARIO and v["comprador_nome"] == "CARLA TESTE SOUSA"
    assert v["valor"] == "25.000,00" and v["data_venda"] == "2026-10-10" and v["uf"] == "MA"
    assert v["proprietario_nome"] == "MARIO EXEMPLO DOS SANTOS"
    assert "comprador_nome" in junto["duvidas"]
    textos = _textos(junto)
    assert "RENAVAM" not in textos and "proprietário" not in textos


def test_o_renavam_sem_digito_e_o_vendedor_que_nao_e_dono_sao_apontados():
    atpv = dict(ATPV, renavam=RENAVAM_RUIM, vendedor_nome="BEATRIZ TESTE LIMA",
                vendedor_cpf_cnpj=CPF_BEATRIZ)
    junto = NTL.juntar_veiculo([_doc("ATPV", atpv), _doc("CRLV", CRLV, 2)])
    textos = _textos(junto)
    assert junto["valores"]["renavam"] == RENAVAM_RUIM            # entra, com o aviso
    assert "não fecha o dígito verificador" in textos
    assert "RENAVAM difere entre os documentos" in textos
    assert "não é o proprietário" in textos


def test_no_crv_quem_vende_e_o_proprietario_e_o_crlv_sozinho_nao_transfere():
    crv = dict(CRLV, comprador_nome="CARLA TESTE SOUSA", comprador_cpf_cnpj=CPF_CARLA,
               data_venda="10/10/2026")
    junto = NTL.juntar_veiculo([_doc("CRV", crv)])
    assert junto["transferencia"] == "CRV"
    assert junto["valores"]["vendedor_nome"] == "MARIO EXEMPLO DOS SANTOS"
    so_crlv = NTL.juntar_veiculo([_doc("CRLV", CRLV)])
    assert so_crlv["transferencia"] == "" and "não transfere" in _textos(so_crlv)


def test_os_campos_de_cada_tela_do_veiculo():
    junto = NTL.juntar_veiculo([_doc("ATPV", ATPV)])
    rec = NTL.campos_do_reconhecimento(junto)["campos"]
    assert rec["especie"] == "AUTENTICIDADE" and rec["veiculo"] == "1"
    assert rec["veiculo_documento"] == "ATPV" and rec["veiculo_placa"] == "ABC1D23"
    assert rec["busca"] == "MARIO EXEMPLO DOS SANTOS"
    assert f"RENAVAM {RENAVAM_BOM}" in rec["documento_descricao"]
    com = NTL.campos_da_comunicacao(junto)
    assert com["campos"]["documento"] == "ATPV_E" and com["campos"]["renavam"] == RENAVAM_BOM
    assert com["duvidas"] == ["comprador_nome"]


# ------------------------------------------------- a rede, de mentira

EM_USO = {"triagem": "T", "manuscrito": "FORTE", "impresso": "MEDIO"}


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
                 maximo_de_saida, **registro):
        self.pedidos.append({"modelo": modelo, "sistema": sistema, "registro": registro,
                             "imagens": len(conversa[0]["imagens"])})
        if sistema == NTL.INSTRUCAO_TRIAGEM:
            corpo = {"paginas": [{"n": i, "tipo": t} for i, t in enumerate(self.tipos, 1)]}
        elif "Autorização para Transferência" in sistema:
            corpo = ATPV
        elif "Licenciamento" in sistema:
            corpo = CRLV
        else:
            corpo = RG_MARIO
        return {"texto": json.dumps(corpo), "entrada": 1000, "saida": 200, "modelo": modelo}


def test_ler_usa_os_moldes_das_notas_e_o_modelo_certo(tmp_path):
    arquivos = [{"caminho": str(_png(tmp_path / f"{i}.png")), "nome": f"{i}.png"}
                for i in range(2)]
    ia = IA(["ATPV", "CRLV"])
    lido = NTL.ler(ia, tmp_path, EM_USO, arquivos, destino="VEICULO")
    assert [p["tipo"] for p in lido["paginas"]] == ["ATPV", "CRLV"]
    assert "tabelionato de notas" in ia.pedidos[0]["sistema"]
    por_tipo = {e["tipo"]: e["modelo"] for e in lido["envios"][1:]}
    assert por_tipo == {"ATPV": "FORTE", "CRLV": "MEDIO"}       # o manuscrito vai ao forte
    assert len(lido["envios"]) == 3
    assert NTL.sugestao("VEICULO", lido["documentos"])["campos"]["placa"] == "ABC1D23"


def test_o_simulador_do_sandbox_e_dito_tambem_nas_notas(tmp_path):
    def simulador(pasta, **_):
        return {"texto": LIA.MARCA_DO_SIMULADOR, "entrada": 0, "saida": 0, "modelo": "s"}
    arquivos = [{"caminho": str(_png(tmp_path / "1.png")), "nome": "1.png"}]
    with pytest.raises(LIA.LeituraError, match="sistema de teste"):
        NTL.ler(simulador, tmp_path, EM_USO, arquivos, destino="CARTAO")


def test_a_conferencia_humana_e_cobrada():
    assert NTL.recusa_sem_conferencia("", None) is None            # sem leitura, a tela de sempre
    assert NTL.recusa_sem_conferencia("7", "1") is None
    assert "ainda não foram conferidos" in NTL.recusa_sem_conferencia("7", None)


def test_o_modulo_nao_lavra_nao_sela_nao_cobra():
    proibidos = ("lavrar", "selar", "cobrar", "numerar", "reconhecer", "comunicar")
    for modulo in (NTL, LIA):
        publicos = [n for n in dir(modulo) if not n.startswith("_")]
        assert not [n for n in publicos if any(p in n.lower() for p in proibidos)], modulo


def test_a_decisao_do_oficial_esta_escrita_com_a_data():
    assert NTL.DECISAO_DO_OFICIAL["data"] == "26/10/2026"
    assert "sem mascara" in NTL.DECISAO_DO_OFICIAL["texto"]
    assert "30 dias" in NTL.AVISO_DA_RETENCAO and "SEM MÁSCARA" in NTL.AVISO_DA_RETENCAO
    assert "26/10/2026" in NTL.BASE_LEGAL


# ------------------------------------------------------------- a tela

def _token(html):
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


def _arquivo():
    from PIL import Image
    b = BytesIO()
    Image.new("RGB", (60, 80), "white").save(b, format="PNG")
    b.seek(0)
    return (b, "documento.png")


def _ler(c, destino, ia, monkeypatch):
    import agente_provedores as AP
    monkeypatch.setattr(AP, "conversar", ia)
    monkeypatch.setattr(AP, "tem_chave", lambda *a, **k: True)
    token = _token(c.get("/notas/cartoes").get_data(as_text=True))
    return c.post("/notas/leitura/ler", data={"csrf_token": token, "destino": destino,
                                              "arquivos": [_arquivo()]},
                  content_type="multipart/form-data")


def test_da_leitura_ao_cartao_preenchido_e_a_conferencia_cobrada(cg_casa_logada, monkeypatch):
    casa = cg_casa_logada
    c = casa["c"]
    ia = IA(["IDENTIDADE"])
    r = _ler(c, "CARTAO", ia, monkeypatch)
    assert r.status_code == 302 and "leitura_id=" in r.headers["Location"]
    # o registro de uso diz a finalidade, e que subiu sem máscara
    assert ia.pedidos[0]["registro"]["finalidade"] == "nt_leitura"
    assert ia.pedidos[0]["registro"]["mascarado"] is False
    tela = c.get(r.headers["Location"]).get_data(as_text=True)
    assert "RASCUNHO preenchido pela leitura" in tela
    assert 'value="MARIO EXEMPLO DOS SANTOS"' in tela and f'value="{CPF_MARIO}"' in tela
    assert 'name="conferi_leitura"' in tela and "30 dias" in tela
    with casa["db"].connect() as con:
        linha = banco(con).um("SELECT * FROM nt_leituras ORDER BY id DESC LIMIT 1")
        anexos = banco(con).valor(
            "SELECT count(*) FROM attachments WHERE entity_type = 'NT_LEITURA' "
            "AND entity_id = %s", (linha["id"],))
    assert linha["situacao"] == "LIDA" and anexos == 1
    assert linha["retencao_dias"] == 30 and linha["sem_mascara"] == 1
    assert linha["criada_por_id"] and float(linha["custo_estimado"]) > 0
    # sem a caixa da conferência, o cartão não abre
    r = c.post("/notas/cartoes", data={"csrf_token": _token(tela), "acao": "novo",
                                       "nome": "MARIO EXEMPLO DOS SANTOS",
                                       "leitura_id": str(linha["id"])},
               follow_redirects=True)
    assert "ainda não foram conferidos" in r.get_data(as_text=True)
    with casa["db"].connect() as con:
        assert banco(con).valor("SELECT count(*) FROM nt_cartoes WHERE nome = %s",
                                ("MARIO EXEMPLO DOS SANTOS",)) == 0
    ficha = c.get(f"/notas/leitura/{linha['id']}").get_data(as_text=True)
    assert "até 30 dias" in ficha and "26/10/2026" in ficha
    assert "Leituras de documentos" in c.get("/notas/leituras").get_data(as_text=True)


def test_da_leitura_a_comunicacao_de_venda_preenchida(cg_casa_logada, monkeypatch):
    c = cg_casa_logada["c"]
    r = _ler(c, "VEICULO", IA(["ATPV"]), monkeypatch)
    assert r.status_code == 302 and "/notas/veiculos" in r.headers["Location"]
    tela = c.get(r.headers["Location"]).get_data(as_text=True)
    assert f'value="{RENAVAM_BOM}"' in tela and 'value="ABC1D23"' in tela
    assert 'value="ATPV_E" selected' in tela and 'name="conferi_leitura"' in tela


def test_a_leitura_de_outra_pessoa_nao_preenche_a_tela(cg_casa_logada, monkeypatch):
    casa = cg_casa_logada
    with casa["db"].transaction() as con:
        lid = NTL.abrir(con, destino="CARTAO", agora="2026-10-26T10:00:00",
                        por="CARLA TESTE", por_id=999999)
        NTL.concluir(con, lid, arquivos=[], lido={
            "documentos": [_doc("IDENTIDADE", RG_BEATRIZ)], "envios": []})
    casa["db"].create_user("beatriz", "BEATRIZ TESTE LIMA", "Senha#12345", "USER")
    from conftest import cg_login
    c = casa["app"].test_client()
    cg_login(c, "beatriz", "Senha#12345")
    tela = c.get(f"/notas/cartoes?leitura_id={lid}").get_data(as_text=True)
    assert "RASCUNHO preenchido" not in tela and CPF_BEATRIZ not in tela
