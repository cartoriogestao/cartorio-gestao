"""O arquivo inteiro do Indicador Real, por botão, em qualquer serventia.

O QUE ELES DEFENDEM
    Pedido do oficial, 30/10/2026. O risco é decisão de uma serventia ficar no código e ir para as
    outras, a regra gravar um logradouro que o ONR recusa em todas as fichas, ou o cálculo mudar a
    ficha de verdade. A parte de baixo usa o sistema de pé, e roda na outra máquina.
"""
from __future__ import annotations

import ast
import io
import re
import sys
import zipfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import onr_indicador_xml as XML  # noqa: E402
import onr_ir_inteiro as IR  # noqa: E402

TELAS = RAIZ / "templates"


def _ficha_em_branco():
    return {"numero": "10", "teor": "", "cidade": "", "uf": ""}


# ------------------------------------------------------------ a regra vira dado


def test_sem_nada_escrito_valem_os_padroes_de_antes():
    padrao = IR.padrao_do_arquivo({"ri_cidade": "Cidade Exemplo", "ri_uf": "ma"})
    novo, origem = XML.completar_ficha(_ficha_em_branco(), None, padrao)
    assert novo["rural_urbano"] == "Rural" and origem["rural_urbano"] == "regra"
    assert novo["logradouro"] == XML.LOGRADOURO_RURAL_SEM_NOME
    assert novo["bairro"] == "Zona Rural" and novo["numero_predial"] == "0"
    assert novo["tipo_imovel"] == XML.TIPO_RURAL
    assert (novo["cidade"], novo["uf"]) == ("Cidade Exemplo", "MA")


def test_a_serventia_urbana_escreve_a_dela():
    padrao = IR.padrao_do_arquivo({"onr_ir_rural_padrao": "U", "onr_ir_bairro_urbano": "Bairro Exemplo",
                                   "onr_ir_logradouro_urbano": "Avenida Sem Nome", "onr_ir_tipo_urbano": "Casa",
                                   "onr_ir_numero": "S/N"})
    novo, _origem = XML.completar_ficha(_ficha_em_branco(), None, padrao)
    assert novo["rural_urbano"] == "Urbano"
    assert novo["logradouro"] == "Avenida Sem Nome"
    assert novo["bairro"] == "Bairro Exemplo"
    assert novo["tipo_imovel"] == "Casa"
    assert novo["numero_predial"] == "S/N"


def test_a_ficha_continua_ganhando_da_regra():
    padrao = IR.padrao_do_arquivo({"onr_ir_rural_padrao": "U", "onr_ir_bairro_rural": "Outro"})
    ficha = {**_ficha_em_branco(), "rural_urbano": "Rural", "logradouro": "Rua das Flores", "bairro": "Centro",
             "tipo_imovel": "Casa"}
    novo, origem = XML.completar_ficha(ficha, None, padrao)
    assert novo["rural_urbano"] == "Rural" and "rural_urbano" not in origem
    assert novo["logradouro"] == "Rua das Flores" and novo["bairro"] == "Centro"


def test_a_lista_da_tela_diz_o_valor_e_o_padrao():
    linhas = {x["chave"]: x for x in IR.regras_na_tela({"onr_ir_bairro_rural": "Interior"})}
    assert linhas["onr_ir_bairro_rural"]["valor"] == "Interior"
    assert linhas["onr_ir_bairro_rural"]["padrao"] == "Zona Rural"
    assert linhas["onr_ir_numero"]["valor"] == "0"


@pytest.mark.parametrize("campo,valor,trecho", [
    ("onr_ir_rural_padrao", "X", "rural ou urbano"),
    ("onr_ir_logradouro_rural", "Sem Nome Nenhum", "tipo que ele conheça"),
    ("onr_ir_logradouro_urbano", "Lugar Qualquer", "tipo que ele conheça"),
    ("onr_ir_tipo_rural", "Mansão", "dez que o ONR aceita"),
    ("onr_ir_bairro_rural", "x" * 101, "100 letras"),
])
def test_regra_que_o_onr_recusaria_nao_se_grava(campo, valor, trecho):
    with pytest.raises(IR.RegraError) as erro:
        IR.conferir_regras({campo: valor})
    assert trecho in str(erro.value)


def test_campo_vazio_volta_ao_padrao():
    novas = IR.conferir_regras({"onr_ir_bairro_rural": "  "})
    assert novas["onr_ir_bairro_rural"] == "Zona Rural"
    assert set(novas) == {r[0] for r in IR.REGRAS}


# ------------------------------------------------------------ nenhuma decisão de uma serventia no código


def test_o_codigo_nao_traz_ficha_nem_dono_de_serventia_nenhuma():
    """O script antigo trazia números de matrícula e donos escritos à mão."""
    arvore = ast.parse((RAIZ / "onr_ir_inteiro.py").read_text(encoding="utf-8"))
    nomes = {alvo.id for no in ast.walk(arvore) if isinstance(no, ast.Assign)
             for alvo in no.targets if isinstance(alvo, ast.Name)}
    assert not nomes & {"DONOS_INFORMADOS", "FORA_DO_INDICADOR"}
    # O padrão de cada regra é genérico: não há CNS, cidade nem nome de pessoa.
    assert IR.REGRAS and all(not re.search(r"\d{4}", r[3]) for r in IR.REGRAS)


def test_a_instalacao_nova_nasce_sem_decisao():
    assert "INSERT" not in IR.SCHEMA.upper()


# ------------------------------------------------------------ o pacote


def _resultado(corpos):
    return {"corpos": corpos, "fora": [{"id": 1, "numero": "7", "motivo": "falta o CEP"}],
            "donos": [{"numero": "8", "nome": "Ana Exemplo", "de_onde": "teor"}], "sem_dono": ["9"],
            "repetidas": [{"numero": "3", "id_fora": 4, "id_que_vai": 5}],
            "preenchido": [{"numero": "8", "campo": "cep", "de_onde": "regra", "valor": "00000000"}], "arquivadas": 0}


def test_o_pacote_traz_o_xml_e_os_relatorios():
    conteudo, nomes = IR.pacote(_resultado([{"cns": "000000", "numeroRegistro": 8}]), data="2026-10-30")
    with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
        dentro = set(z.namelist())
        assert nomes == ["IndicadorReal_COMPLETO_2026-10-30.XML"]
        assert dentro == {"IndicadorReal_COMPLETO_2026-10-30" + s for s in (
            ".XML", "_fora.csv", "_donos.csv", "_sem_dono.csv", "_repetidas.csv", "_preenchido.csv")}
        xml = z.read(nomes[0]).decode("utf-8")
        assert "<NumeroRegistro>8</NumeroRegistro>" in xml
        fora = z.read("IndicadorReal_COMPLETO_2026-10-30_fora.csv").decode("utf-8-sig")
        assert "falta o CEP" in fora and '"matricula";"motivo"' in fora


def test_o_relatorio_nao_deixa_formula_passar():
    """O nome do dono é digitado na tela, e o relatório vai abrir numa planilha."""
    r = {**_resultado([{"cns": "000000", "numeroRegistro": 8}]),
         "donos": [{"numero": "8", "nome": '=HIPERLINK("http://exemplo.invalid")', "de_onde": "-informado"}]}
    conteudo, _ = IR.pacote(r, data="2026-10-30")
    with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
        donos = z.read("IndicadorReal_COMPLETO_2026-10-30_donos.csv").decode("utf-8-sig")
    assert "'=HIPERLINK" in donos and "'-informado" in donos


def test_passando_do_limite_do_onr_o_xml_se_divide(monkeypatch):
    monkeypatch.setattr(XML, "LIMITE_POR_ARQUIVO", 2)
    corpos = [{"numeroRegistro": i} for i in range(5)]
    conteudo, nomes = IR.pacote(_resultado(corpos), data="2026-10-30")
    assert nomes == [f"IndicadorReal_COMPLETO_2026-10-30_{i}.XML" for i in (1, 2, 3)]
    with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
        assert z.read(nomes[2]).decode("utf-8").count("<IndicadorReal>") == 1


# ------------------------------------------------------------ as regras, lidas do código


def _rotas() -> dict:
    arvore = ast.parse((RAIZ / "onr_ir_inteiro_web.py").read_text(encoding="utf-8"))
    return {no.name: " ".join(ast.unparse(d) for d in no.decorator_list) for no in ast.walk(arvore)
            if isinstance(no, ast.FunctionDef) and any("route" in ast.unparse(d) for d in no.decorator_list)}


def test_decidir_e_so_do_admin_e_exportar_e_de_quem_ja_exporta():
    rotas = _rotas()
    for nome in ("onr_ir_regras", "onr_ir_fora", "onr_ir_fora_voltar", "onr_ir_dono", "onr_ir_dono_tirar"):
        assert "QUEM_DECIDE" in rotas[nome], nome
    for nome in ("onr_ir", "onr_ir_conferir", "onr_ir_baixar"):
        assert "QUEM_EXPORTA" in rotas[nome], nome
    import onr_ir_inteiro_web as WEB
    assert WEB.QUEM_DECIDE == ("ADMIN",) and WEB.QUEM_EXPORTA == ("ADMIN", "MANAGER")


def test_o_calculo_nao_escreve():
    """Nenhuma ficha muda: o `calcular` não tem INSERT, UPDATE nem DELETE."""
    arvore = ast.parse((RAIZ / "onr_ir_inteiro.py").read_text(encoding="utf-8"))
    corpo = next(ast.unparse(no) for no in ast.walk(arvore)
                 if isinstance(no, ast.FunctionDef) and no.name == "calcular")
    assert not re.search(r"\b(INSERT|UPDATE|DELETE)\b", corpo)
    assert ".escrever(" not in corpo


def test_os_formularios_mandam_o_token():
    texto = (TELAS / "onr_ir_inteiro.html").read_text(encoding="utf-8")
    assert texto.count('method="post"') == texto.count('name="csrf_token"') == 7


def test_a_exportacao_aponta_para_o_arquivo_inteiro():
    assert "url_for('onr_ir')" in (TELAS / "ri_onr.html").read_text(encoding="utf-8-sig")


# ------------------------------------------------------------- com o sistema de pé


def _token(html: str) -> str:
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


def _entrar(app, usuario: str, papel: str):
    d = app.extensions["db"]
    try:
        d.create_user(usuario, "Operador Exemplo", "Senha#12345", papel)
    except Exception:                                              # noqa: BLE001
        pass
    c = app.test_client()
    c.post("/login", data={"username": usuario, "password": "Senha#12345",
                           "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return c


def _ficha(app, numero: str, **campos):
    from bd_nativo import banco
    d = app.extensions["db"]
    with d.transaction() as con:
        linha = banco(con).um(
            "INSERT INTO ri_matriculas (numero, livro, livro_norm, origem) VALUES (%s, '2', '2', 'MANUAL') RETURNING id",
            (numero,))
        for coluna, valor in campos.items():
            banco(con).escrever(f"UPDATE ri_matriculas SET {coluna} = %s WHERE id = %s", (valor, linha["id"]))
    return linha["id"]


def test_o_arquivo_completa_sem_mudar_a_ficha(cg_app):
    d = cg_app.extensions["db"]
    d.set_settings({"ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA", "ri_cep": "00000000"})
    mid = _ficha(cg_app, "70001")
    c = _entrar(cg_app, "ir_admin", "ADMIN")
    pagina = c.get("/registro-imoveis/onr/indicador-inteiro").get_data(as_text=True)
    assert "A regra desta serventia" in pagina
    r = c.post("/registro-imoveis/onr/indicador-inteiro/baixar", data={"csrf_token": _token(pagina)})
    assert r.status_code == 200 and r.mimetype == "application/zip"
    with zipfile.ZipFile(io.BytesIO(r.data)) as z:
        xml = z.read(next(n for n in z.namelist() if n.endswith(".XML"))).decode("utf-8")
    assert "<NumeroRegistro>70001</NumeroRegistro>" in xml
    from bd_nativo import banco
    with d.connect() as con:
        ficha = banco(con).um("SELECT logradouro, bairro FROM ri_matriculas WHERE id = %s", (mid,))
    assert not ficha["logradouro"] and not ficha["bairro"]


def test_ficha_fora_e_dono_informado_valem_no_arquivo(cg_app):
    d = cg_app.extensions["db"]
    d.set_settings({"ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA", "ri_cep": "00000000"})
    _ficha(cg_app, "70002")
    _ficha(cg_app, "70003")
    c = _entrar(cg_app, "ir_admin2", "ADMIN")
    token = _token(c.get("/registro-imoveis/onr/indicador-inteiro").get_data(as_text=True))
    base = "/registro-imoveis/onr/indicador-inteiro"
    c.post(f"{base}/fora", data={"numero": "70002", "motivo": "Ficha sem efeito no ensaio.", "csrf_token": token})
    c.post(f"{base}/dono", data={"numero": "70003", "nome": "Ana Exemplo", "de_onde": "Informado no ensaio.", "csrf_token": token})
    conferido = c.post(f"{base}/conferir", data={"csrf_token": token}).get_data(as_text=True)
    assert "Ficha sem efeito no ensaio." in conferido
    r = c.post(f"{base}/baixar", data={"csrf_token": token})
    with zipfile.ZipFile(io.BytesIO(r.data)) as z:
        xml = z.read(next(n for n in z.namelist() if n.endswith(".XML"))).decode("utf-8")
    assert "<NumeroRegistro>70002</NumeroRegistro>" not in xml
    assert "Ana Exemplo" in xml


def test_quem_nao_e_admin_nao_decide(cg_app):
    c = _entrar(cg_app, "ir_gerente", "MANAGER")
    pagina = c.get("/registro-imoveis/onr/indicador-inteiro").get_data(as_text=True)
    assert "Gravar a regra" not in pagina
    assert c.post("/registro-imoveis/onr/indicador-inteiro/regras", data={"csrf_token": _token(pagina)}).status_code == 403
    balcao = _entrar(cg_app, "ir_balcao", "USER")
    assert balcao.get("/registro-imoveis/onr/indicador-inteiro").status_code == 403
