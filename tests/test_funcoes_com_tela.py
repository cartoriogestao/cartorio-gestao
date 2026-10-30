"""As funções prontas que ganharam tela — revisão de telas, 30/10/2026.

    «que nao tem funcoes utilizaveis sem tela» — o oficial

O QUE ELES DEFENDEM
    `test_funcao_sem_tela` só pergunta se o NOME tem caminho até uma rota, e nome
    igual conta como um só. Aqui se pergunta o resto: esta rota chama esta função, a
    tela mostra o quadro, a lista vazia diz que está vazia, e ninguém passou a ver o
    que não via.

AS DUAS METADES
    A primeira só lê arquivo e desenha o molde com dado de mentira: roda em qualquer
    máquina, sem banco. A segunda usa `cg_app`, com o sistema de pé, e roda na máquina
    da suíte.

AS DUAS QUE NÃO PRECISARAM DE TELA, E POR QUÊ
    `conferir_remessa`: a tela de conferir a remessa já confere. `blocos_do`: a ficha
    do assento já separa. As duas têm guarda aqui. E `atos_sem_cobranca` foi apagada,
    por decisão do oficial: a conferência de selos × caixa já responde.
"""
from __future__ import annotations

import ast
import re
import sys
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlencode

import pytest
from jinja2 import (ChainableUndefined, ChoiceLoader, DictLoader, Environment,
                    FileSystemLoader)

RAIZ = Path(__file__).resolve().parent.parent
TELAS = RAIZ / "templates"
sys.path.insert(0, str(RAIZ))

import livro_nucleo as LN  # noqa: E402
import onr_indicador_xml as XML  # noqa: E402
import papel_seguranca as PP  # noqa: E402
import protesto as PT  # noqa: E402
import ri_onr as ARQUIVO  # noqa: E402
import ri_onr_central as ONR  # noqa: E402
from bd_nativo import banco  # noqa: E402

AGORA = "2026-10-30T10:00:00"

# (arquivo da rota, rota, função que ela passou a chamar)
LIGACOES = [
    ("gratuidade_comprovante_web.py", "selo_cobertura", "pagamentos_pendentes"),
    ("papel_web.py", "rcpn_papel", "movimentos_da_folha"),
    ("atribuicoes_web.py", "protesto_cenprot", "titulos_sem_chave"),
    ("atribuicoes_web.py", "protesto_retornos", "atos_do_retorno"),
    ("ri_web.py", "ri_onr", "pendentes_onr"),
    ("ri_web.py", "ri_onr", "corpos_para_o_arquivo"),
    ("ri_web.py", "ri_onr", "arquivo_xml"),
    ("nucleo_web.py", "nucleo_livros", "exigencias_da_inspecao"),
]

# As que abrem o banco: têm de ler por `db.connect()`.
LEEM_DO_BANCO = [x for x in LIGACOES
                 if x[2] not in ("arquivo_xml", "exigencias_da_inspecao")]

# (módulo, função): o que a tela chama, e o que estas chamam por dentro.
SO_LEEM = [
    ("ato_selado.py", "pagamentos_pendentes"),
    ("ato_selado.py", "liberados_sem_cobertura"),
    ("ato_selado.py", "cobertura_de_verdade"),
    ("papel_seguranca.py", "movimentos_da_folha"),
    ("papel_seguranca.py", "ler"),
    ("protesto_cenprot.py", "titulos_sem_chave"),
    ("protesto_retorno.py", "atos_do_retorno"),
    ("ri_digitalizacao.py", "pendentes_onr"),
    ("ri_onr_central.py", "corpos_para_o_arquivo"),
    ("ri_onr_central.py", "montar_indicador"),
    ("onr_indicador_xml.py", "arquivo_xml"),
    ("onr_indicador_xml.py", "indicador_em_xml"),
    ("livro_nucleo.py", "exigencias_da_inspecao"),
]

# A rota que só desenha não grava nada, nem de passagem.
SO_DESENHAM = [
    ("gratuidade_comprovante_web.py", "selo_cobertura"),
    ("papel_web.py", "rcpn_papel"),
    ("atribuicoes_web.py", "protesto_retornos"),
    ("nucleo_web.py", "nucleo_livros"),
]

# OS MESMOS PAPÉIS DE ANTES: quadro novo não abre tela para ninguém.
PAPEIS = [
    ("gratuidade_comprovante_web.py", "selo_cobertura", "login_required"),
    ("papel_web.py", "rcpn_papel", "login_required"),
    ("atribuicoes_web.py", "protesto_cenprot",
     "roles_required('ADMIN', 'MANAGER', 'USER')"),
    ("atribuicoes_web.py", "protesto_retornos", "login_required"),
    ("ri_web.py", "ri_onr", "roles_required('ADMIN', 'MANAGER')"),
    ("nucleo_web.py", "nucleo_livros",
     "roles_required('ADMIN', 'MANAGER', 'USER', 'AUDITOR')"),
]


# ------------------------------------------------------------ leitura do código


@lru_cache(maxsize=None)
def _arvore(arquivo: str) -> ast.Module:
    return ast.parse((RAIZ / arquivo).read_text(encoding="utf-8"))


def _funcao(arquivo: str, nome: str):
    for no in ast.walk(_arvore(arquivo)):
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)) and no.name == nome:
            return no
    raise AssertionError(f"{nome} não existe em {arquivo}")


def _chamadas(no) -> set[str]:
    fora: set[str] = set()
    for x in ast.walk(no):
        if isinstance(x, ast.Call):
            if isinstance(x.func, ast.Attribute):
                fora.add(x.func.attr)
            elif isinstance(x.func, ast.Name):
                fora.add(x.func.id)
    return fora


def _ler_tela(nome: str) -> str:
    return (TELAS / nome).read_text(encoding="utf-8")


@pytest.mark.parametrize("arquivo, rota, funcao", LIGACOES)
def test_a_rota_chama_a_funcao(arquivo, rota, funcao):
    assert funcao in _chamadas(_funcao(arquivo, rota))


@pytest.mark.parametrize("arquivo, rota, funcao", LEEM_DO_BANCO)
def test_a_leitura_nao_abre_transacao_de_escrita(arquivo, rota, funcao):
    achadas = [ast.unparse(no.items[0].context_expr)
               for no in ast.walk(_funcao(arquivo, rota))
               if isinstance(no, ast.With) and funcao in _chamadas(no)]
    assert achadas, f"{rota} chama {funcao} fora de um `with`"
    assert set(achadas) == {"db.connect()"}, achadas


@pytest.mark.parametrize("arquivo, rota", SO_DESENHAM)
def test_a_rota_de_so_desenhar_nao_grava(arquivo, rota):
    assert not _chamadas(_funcao(arquivo, rota)) & {"transaction", "audit", "escrever"}


@pytest.mark.parametrize("arquivo, funcao", SO_LEEM)
def test_o_que_a_tela_chama_so_le(arquivo, funcao):
    no = _funcao(arquivo, funcao)
    assert not _chamadas(no) & {"escrever", "_escrita", "travar", "commit"}
    doc = ast.get_docstring(no, clean=False)
    textos = [x.value for x in ast.walk(no)
              if isinstance(x, ast.Constant) and isinstance(x.value, str)
              and x.value != doc]
    assert not any(re.search(r"\b(INSERT|UPDATE|DELETE)\b", t) for t in textos)


@pytest.mark.parametrize("arquivo, rota, papel", PAPEIS)
def test_os_papeis_da_tela_nao_mudaram(arquivo, rota, papel):
    decoradores = [ast.unparse(d) for d in _funcao(arquivo, rota).decorator_list]
    assert papel in decoradores, decoradores


def test_a_cobranca_e_de_quem_abriu_e_nao_foi_para_a_tela_do_gestor():
    """A tela do gestor só o ADMIN e o gerente abrem, e a cobrança é de quem selou."""
    rota = ast.unparse(_funcao("gratuidade_comprovante_web.py", "selo_cobertura"))
    assert "eu['full_name']" in rota and "eu['username']" in rota
    assert "pagamentos_pendentes" not in _chamadas(
        _funcao("gratuidade_comprovante_web.py", "selo_conferencia"))
    assert "_anchor='a-pagar'" in _ler_tela("_selo_trava_aviso.html")


def test_a_busca_da_folha_e_get_e_nao_pede_token():
    tela = _ler_tela("rcpn_papel.html")
    formulario = re.search(r'<form method="get"[^>]*#caminho.*?</form>', tela, re.S)
    assert formulario, "a tela do papel não tem a busca do caminho da folha"
    assert 'name="folha"' in formulario.group(0)
    assert "csrf_token" not in formulario.group(0)


def test_o_botao_do_xml_esta_junto_dos_outros_e_manda_o_token():
    tela = _ler_tela("ri_onr.html")
    painel = re.search(r"Gerar arquivos.*?</section>", tela, re.S).group(0)
    formulario = re.search(r'<form method="post">(?:(?!</form>).)*REAL_XML.*?</form>',
                           painel, re.S)
    assert formulario, "o botão do XML saiu do painel de gerar arquivos"
    assert "csrf_token" in formulario.group(0)


def test_o_arquivo_tem_o_nome_do_que_ele_e():
    from datetime import date
    de, ate = date(2026, 10, 1), date(2026, 10, 30)
    assert ARQUIVO.nome_arquivo("REAL_XML", de, ate) == "IndicadorReal_01102026_30102026.XML"
    assert ARQUIVO.nome_arquivo("REAL", de, ate) == "IndicadorReal_01102026_30102026.json"
    assert ARQUIVO.nome_arquivo("PESSOAL", de, ate) == "IndicadorPessoal_01102026_30102026.XML"


# ------------------------------------------------- as três que não ganharam tela


def test_a_tela_da_remessa_ja_confere_contra_o_contrato_da_cra():
    """`conferir_remessa` não ganhou tela porque o fluxo já faz a mesma conta."""
    assert "conferir_titulo" in _chamadas(_funcao("protesto_remessa.py", "_conferir_lote"))
    assert "conferir" in _chamadas(_funcao("atribuicoes_web.py", "_conferir_a_remessa"))
    tela = _ler_tela("protesto_remessa_conferir.html")
    assert "t.faltas" in tela and "não entra" in tela


def test_a_ficha_do_assento_ja_separa_os_blocos():
    """`blocos_do` não ganhou tela porque a ficha já mostra um quadro por bloco."""
    assert "blocos=blocos" in ast.unparse(_funcao("atribuicoes_web.py", "rcpn_assento"))
    tela = _ler_tela("atrib_rcpn_ficha.html")
    for bloco in ("AVERBACAO", "ANOTACAO", "RETIFICACAO"):
        assert f"('{bloco}'," in tela, bloco


def test_nenhuma_tela_promete_a_lista_de_atos_sem_cobranca():
    """A lista nunca existiu para o Protesto, e a função foi apagada em 30/10/2026."""
    for tela in ("protesto_remessa_conferir.html", "protesto_a_protestar.html"):
        assert "sem cobrança</em>, para" not in _ler_tela(tela)
        assert "Atos sem cobrança" not in _ler_tela(tela)
    assert "«Atos sem" not in (RAIZ / "atribuicoes_web.py").read_text(encoding="utf-8")


# ------------------------------------------------- o XML: o que vai e o que fica


def _montar_de_mentira(con, matricula_id, *, cns):
    if matricula_id == 2:
        return {"corpo": {"numeroRegistro": 2}, "pronto": False,
                "impedem": ["Falta o CEP na ficha da matrícula, e o ONR o exige."]}
    if matricula_id == 3:
        raise ValueError("ficha torta")
    return {"corpo": {"cns": cns, "numeroRegistro": matricula_id, "situacaoConstrucao": 0},
            "pronto": True, "impedem": []}


def test_o_xml_leva_so_a_ficha_completa_e_diz_por_que_a_outra_ficou(monkeypatch):
    monkeypatch.setattr(ONR, "montar_indicador", _montar_de_mentira)
    visto = ONR.corpos_para_o_arquivo(
        None, [{"id": 1, "numero": "101"}, {"id": 2, "numero": "102"},
               {"id": 3, "numero": "103"}], cns="000000")
    assert [c["numeroRegistro"] for c in visto["corpos"]] == [1]
    motivos = {f["numero"]: f["motivos"] for f in visto["de_fora"]}
    assert "Falta o CEP" in motivos["102"][0]
    assert "Não deu para montar" in motivos["103"][0], "a ficha torta derrubou a tela"
    raiz = ET.fromstring(XML.arquivo_xml(visto["corpos"]))
    assert [x.findtext("NumeroRegistro") for x in raiz.findall("IndicadorReal")] == ["1"]
    assert raiz.find("IndicadorReal").findtext("SituacaoConstrucao") == "0"


def test_o_que_nao_e_imovel_ativo_nem_chega_a_ser_montado(monkeypatch):
    def nao_devia_montar(*a, **k):
        raise AssertionError("montou ficha que não vai")
    monkeypatch.setattr(ONR, "montar_indicador", nao_devia_montar)
    visto = ONR.corpos_para_o_arquivo(
        None, [{"id": 1, "numero": "101", "encerrada": 1},
               {"id": 2, "numero": "904001"},
               {"id": 3, "numero": "8877"}, {"id": 4, "numero": "8877"}], cns="000000")
    assert visto["corpos"] == []
    assert [f["id"] for f in visto["de_fora"]] == [1, 2, 3, 4]
    assert "repetido" in visto["de_fora"][3]["motivos"][0]


# ----------------------------------------- o molde desenhado, sem sistema de pé


def _url_for(endpoint, **campos):
    ancora = campos.pop("_anchor", None)
    consulta = urlencode({c: v for c, v in campos.items() if v not in (None, "")})
    return (f"/{endpoint}" + (f"?{consulta}" if consulta else "")
            + (f"#{ancora}" if ancora else ""))


_MOLDES = Environment(
    loader=ChoiceLoader([DictLoader({"_serventia.html": ""}),
                         FileSystemLoader(str(TELAS))]),
    undefined=ChainableUndefined, autoescape=True)
_MOLDES.globals.update(url_for=_url_for, fmt_date=lambda v: v or "—", csrf_token="TOKEN",
                       user={"role": "ADMIN"})
_MOLDES.filters["centavos_reais"] = str


def _desenhar(tela: str, **contexto) -> str:
    """Só o miolo da tela: a moldura pede o sistema de pé, e o quadro não mora nela."""
    molde = _MOLDES.get_template(tela)
    return "".join(molde.blocks["content"](molde.new_context(contexto)))


def _sem_recolher_aberto(html: str) -> bool:
    return re.search(r"<details[^>]*\bopen\b", html) is None


SELO = dict(quadro={"titulo": "Para selar este ato falta", "itens": [], "pode_selar": False},
            tabela=None, ato_id=None, atendendo=None, disponiveis=[], aguardando=[],
            pedidos=[], eh_admin=False)
LIBERACAO = {"tabela": "pt_atos", "ato_id": 7, "rotulo": "Protesto",
             "selos": ["SELOEXEMPLO0001"], "liberado_por": "MARIO EXEMPLO",
             "liberado_em": "2026-10-29T09:00:00",
             "justificativa": "O cliente pagou e o caixa estava fora do ar"}


def test_a_cobranca_vem_depois_do_quadro_e_antes_do_resto():
    html = _desenhar("selo_cobertura.html", a_pagar=[LIBERACAO], **SELO)
    assert "SELOEXEMPLO0001" in html and "tabela=pt_atos" in html
    assert "— 1</h2>" in html
    assert (html.index("Para selar este ato falta") < html.index('id="a-pagar"')
            < html.index("Protocolo que estou atendendo"))


def test_sem_cobranca_a_tela_diz_que_nao_ha():
    html = _desenhar("selo_cobertura.html", a_pagar=[], **SELO)
    assert "Nenhum selo liberado seu está sem pagamento." in html


PAPEL = dict(quadro={"em_branco": 5, "usadas": 1, "inutilizadas": 0, "proxima": "8100002"},
             caixas=[], usadas=[], inutilizadas=[],
             pagina_usadas={"total": 0, "busca": "", "paginas": 1, "pagina": 1})
FOLHA_USADA = {"codigo": "8100001", "serie": "HA", "situacao": "USADA",
               "usada_em": "2026-10-29T09:00:00", "usada_por": "BEATRIZ EXEMPLO"}
MOVIMENTOS = [
    {"situacao_anterior": "EM BRANCO", "situacao_nova": "USADA", "tabela": "rc_atos",
     "ato_id": 428, "selo": "SELOEXEMPLO0001", "motivo": None,
     "ocorrido_em": "2026-10-29T09:00:00", "ocorrido_por": "BEATRIZ EXEMPLO"},
    {"situacao_anterior": "USADA", "situacao_nova": "EM BRANCO", "tabela": "rc_certidoes",
     "ato_id": 57, "selo": None, "motivo": "certidão emitida com erro",
     "ocorrido_em": "2026-10-29T10:00:00", "ocorrido_por": "MARIO EXEMPLO"},
]


def _caminho(html: str) -> str:
    return html[html.index('id="caminho"'):html.index('id="usadas"')]


def test_sem_procurar_a_tela_do_papel_so_oferece_o_campo():
    html = _caminho(_desenhar("rcpn_papel.html", procurada="", folha=None, caminho=[], **PAPEL))
    assert 'name="folha"' in html and "<table" not in html and "Limpar" not in html


def test_o_caminho_da_folha_fala_a_lingua_do_balcao():
    html = _caminho(_desenhar("rcpn_papel.html", procurada="HA 8100001", folha=FOLHA_USADA,
                              caminho=MOVIMENTOS, **PAPEL))
    assert "HA 8100001" in html and "voltou ao estoque" in html
    assert "registro nº 428" in html and "certidão nº 57" in html
    assert "certidão emitida com erro" in html
    assert "rc_atos" not in html and "rc_certidoes" not in html, "nome de tabela na tela"


def test_a_folha_que_nao_esta_no_estoque_diz_isso():
    html = _caminho(_desenhar("rcpn_papel.html", procurada="999", folha=None, caminho=[], **PAPEL))
    assert "não está no estoque" in html


@pytest.mark.parametrize("folha, frase", [
    ({"codigo": "1", "situacao": "EM BRANCO"}, "em branco, no estoque"),
    ({"codigo": "1", "situacao": "EM BRANCO"}, "não passou por nenhum ato"),
    ({"codigo": "1", "situacao": "INUTILIZADA", "inutilizada_motivo": "saiu borrada"},
     "saiu borrada"),
    ({"codigo": "1", "situacao": "USADA"}, "anterior a este registro"),
])
def test_a_folha_sem_movimento_nao_fica_calada(folha, frase):
    html = _caminho(_desenhar("rcpn_papel.html", procurada="1", folha=folha, caminho=[], **PAPEL))
    assert frase in html


CENPROT = dict(resultado=None, do_arquivo=0, editais_hoje=0, hoje="2026-10-30",
               versao_medida="1.0")
SEM_CHAVE = {"id": 41, "protocolo": "2610300001", "numero_titulo": "1234/1",
             "nosso_numero": None, "situacao": "PROTESTADO"}


def test_a_lista_dos_sem_chave_vem_recolhida_e_diz_quando_corta():
    html = _desenhar("protesto_cenprot.html", sem_chave=[SEM_CHAVE], quadro={
        "total": 300, "com_chave": 0, "sem_protocolo": 0, "a_preencher": 300}, **CENPROT)
    assert "esperando a chave — 300" in html and "titulo_id=41" in html
    assert "mostra os 1 mais novos" in html
    assert _sem_recolher_aberto(html)


def test_sem_titulo_esperando_a_tela_diz_que_nao_ha():
    html = _desenhar("protesto_cenprot.html", sem_chave=[], quadro={
        "total": 3, "com_chave": 3, "sem_protocolo": 0, "a_preencher": 0}, **CENPROT)
    assert "Nenhum título esperando a chave." in html and "<details" not in html


def _arquivo_gerado(**campos):
    return {"id": 9, "tipo": "SDTBFORTP", "apresentante_codigo": "001", "dia": "2026-10-30",
            "titulos": 1, "soma_centavos": 100, "nome_arquivo": "R0013010.261",
            "gerado_em": AGORA, "atos_presos": 1, "atos_desfeitos": 0,
            "atos_do_arquivo": [], **campos}


RETORNOS = dict(grupos=[], atos=[], desfeitos=[], ja_aceitas=[], hoje="2026-10-30")


def test_cada_arquivo_abre_os_atos_que_levou_e_marca_o_desfeito():
    atos = [{"ato_id": 5, "titulo_id": 41, "tipo": "PROTESTO", "data_ato": "2026-10-30",
             "cancelado": 1, "numero_titulo": "1234/1", "protocolo": "2610300001"}]
    html = _desenhar("protesto_retornos.html",
                     gerados=[_arquivo_gerado(atos_do_arquivo=atos)], **RETORNOS)
    assert "1 ato(s)</small></summary>" in html
    assert "titulo_id=41" in html and "desfeito depois" in html
    assert _sem_recolher_aberto(html)


@pytest.mark.parametrize("tipo, frase", [("SDTBFOCRT", "a confirmação não leva ato"),
                                         ("SDTBFORTP", "nenhum ato ligado a este arquivo")])
def test_o_arquivo_sem_ato_diz_que_esta_sem(tipo, frase):
    html = _desenhar("protesto_retornos.html",
                     gerados=[_arquivo_gerado(tipo=tipo, atos_presos=0)], **RETORNOS)
    assert frase in html


ONR_TELA = dict(inicio="2026-10-01", fim="2026-10-30", cns="000000", vinculos=[], sem_doc=0)
PENDENTE = {"id": 5, "numero": "8021", "digi_nome": "ficha-8021.pdf", "digi_sha256": "ABCDEF",
            "digi_em": "2026-10-29T09:00:00", "digi_por": "BEATRIZ EXEMPLO",
            "digi_path": "ARQUIVO-DE-TESTE.pdf"}


def test_a_exportacao_mostra_o_que_fica_de_fora_e_o_pendente_recolhidos():
    html = _desenhar(
        "ri_onr.html", matriculas=[{"id": 1}, {"id": 2}],
        real_xml={"corpos": [{"numeroRegistro": 1}],
                  "de_fora": [{"id": 2, "numero": "8020", "motivos": ["Falta o CEP."]}]},
        pendentes_onr=[PENDENTE], pendentes_cortadas=True, **ONR_TELA)
    assert "1 de 2 matrícula(s)" in html
    assert "Fora do Indicador Real (.XML) — 1" in html and "Falta o CEP." in html
    assert "matricula_id=2" in html
    assert "1 ou mais matrícula(s)" in html and "só as 1 mais recentes" in html
    assert "ficha-8021.pdf" in html and "matricula_id=5" in html
    assert "ARQUIVO-DE-TESTE" not in html and "ABCDEF" not in html, "caminho ou sha na tela"
    assert _sem_recolher_aberto(html)


def test_sem_nada_a_exportacao_desliga_o_botao_e_diz_que_nao_ha_pendente():
    html = _desenhar("ri_onr.html", matriculas=[], real_xml={"corpos": [], "de_fora": []},
                     pendentes_onr=[], pendentes_cortadas=False, **ONR_TELA)
    assert re.search(r"<button class=\"primary\" disabled>\s*Indicador Real \(\.XML\)", html)
    assert "Nenhuma matrícula com digitalização nova esperando o ONR." in html
    assert "Fora do Indicador Real" not in html


LIVROS = dict(linhas=[], atribuicoes={}, atrasados={}, fechados=[], series=LN.SERIES)


def test_o_que_a_inspecao_cobra_vem_recolhido_e_com_o_nome_do_livro():
    exigencias = LN.exigencias_da_inspecao()
    html = _desenhar("nucleo_livros.html", exigencias=exigencias, **LIVROS)
    assert f"{len(exigencias)} série(s)" in html
    assert LN.SERIES["RC_A"].nome in html and "assinaturas do assento" in html
    assert "RC_A" not in html, "código da série na tela, em vez do nome"
    assert _sem_recolher_aberto(html)


def test_sem_exigencia_a_tela_diz_que_nao_ha():
    html = _desenhar("nucleo_livros.html", exigencias={}, **LIVROS)
    assert "Nenhuma exigência registrada." in html


# ------------------------------------------------- com o sistema de pé (outra máquina)


@pytest.fixture(scope="module")
def app(cg_app):
    return cg_app


def _token(html: str) -> str:
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


def _entrar(app, usuario: str, papel: str, nome: str = "Operador Exemplo"):
    d = app.extensions["db"]
    try:
        d.create_user(usuario, nome, "Senha#12345", papel)
    except Exception:                                              # noqa: BLE001
        pass
    c = app.test_client()
    c.post("/login", data={"username": usuario, "password": "Senha#12345",
                           "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return c


def _titulo(con, numero: str) -> int:
    return PT.cadastrar_titulo(con, {
        "apresentante_codigo": "001", "apresentante_nome": "BANCO EXEMPLO",
        "especie": "DMI", "numero_titulo": numero, "nosso_numero": f"NN{numero}",
        "data_emissao": "2026-01-05", "data_vencimento": "2026-02-05",
        "valor": "1.200,00", "saldo": "1.310,45",
        "praca_protesto": "CIDADE EXEMPLO", "motivo_protesto": "1",
        "cedente": {"nome": "LOJA EXEMPLO LTDA", "documento": "00000001000055"},
        "devedores": [{"nome": "ANA EXEMPLO", "CPF": "00000000191",
                       "enderecos": [{"endereco": "RUA EXEMPLO, 10", "bairro": "CENTRO",
                                      "cidade": "Cidade Exemplo", "uf": "MA"}]}],
    }, origem="CRA", origem_chave=f"telas:{numero}", agora=AGORA)


def _ficha(con, numero: str, **campos) -> int:
    base = {"numero": numero, "livro": "2", "livro_norm": "2",
            "tipo_ficha": "ESTRUTURADA", "tipo_imovel": "Casa", "rural_urbano": "Urbano",
            "logradouro": "Rua das Flores", "numero_predial": "100", "bairro": "Centro",
            "cidade": "Cidade Exemplo", "uf": "MA", "cep": "99999-000",
            "data_abertura": "2026-01-15", "criado_em": AGORA, **campos}
    colunas, marcas = ", ".join(base), ", ".join(["%s"] * len(base))
    return int(banco(con).escrever(
        f"INSERT INTO ri_matriculas({colunas}) VALUES({marcas}) RETURNING id",
        tuple(base.values()))[0]["id"])


def test_selo_e_caixa_lista_so_a_cobranca_de_quem_abriu(app):
    c = _entrar(app, "telas_beatriz", "USER", nome="BEATRIZ EXEMPLO")
    with app.extensions["db"].transaction() as con:
        bd = banco(con)
        for ato_id, quem, numero in ((9001, "BEATRIZ EXEMPLO", "SELOEXEMPLO0001"),
                                     (9002, "CARLA EXEMPLO", "SELOEXEMPLO0002")):
            bd.escrever(
                """INSERT INTO cx_selo_liberacoes (tabela, ato_id, justificativa,
                       liberado_por, liberado_em)
                   VALUES ('pt_atos', %s, 'O cliente pagou e o caixa estava fora do ar',
                           'MARIO EXEMPLO', %s)""", (ato_id, AGORA))
            bd.escrever(
                """INSERT INTO sd_selos (numero, texto, tabela, ato_id, obtido_em, obtido_por)
                   VALUES (%s, 'Selo pago', 'pt_atos', %s, %s, %s)""",
                (numero, ato_id, AGORA, quem))
    html = c.get("/selo/cobertura").get_data(as_text=True)
    assert "SELOEXEMPLO0001" in html and "SELOEXEMPLO0002" not in html
    assert "Você tem 1 selo(s) liberado(s)" in html, "a barra e a lista não batem"


def test_o_caminho_da_folha_acha_com_a_serie_e_sem_ela(app):
    c = _entrar(app, "telas_papel", "USER")
    with app.extensions["db"].transaction() as con:
        PP.receber_remessa(con, fornecedor="ARPENBRASIL", serie="HA", codigo_de="8100001",
                           codigo_ate="8100002", agora=AGORA, usuario="MARIO EXEMPLO")
        PP.usar(con, "8100001", tabela="rc_atos", ato_id=9001, agora=AGORA,
                usuario="MARIO EXEMPLO")
    for digitado in ("HA 8100001", "8100001"):
        html = c.get("/rcpn/papel", query_string={"folha": digitado}).get_data(as_text=True)
        assert "registro nº 9001" in _caminho(html), digitado
    em_branco = c.get("/rcpn/papel", query_string={"folha": "8100002"}).get_data(as_text=True)
    assert "em branco, no estoque" in _caminho(em_branco)
    fora = c.get("/rcpn/papel", query_string={"folha": "7"}).get_data(as_text=True)
    assert "não está no estoque" in _caminho(fora)


def test_a_chave_do_cenprot_lista_os_titulos_esperando(app):
    c = _entrar(app, "telas_cenprot", "ADMIN")
    with app.extensions["db"].transaction() as con:
        tid = _titulo(con, "9901/1")
        banco(con).escrever("UPDATE pt_titulos SET protocolo=%s WHERE id=%s",
                            ("2610309901", tid))
    html = c.get("/protesto/cenprot").get_data(as_text=True)
    quadro = html[html.index("Como está a casa hoje"):html.index("Trazer o arquivo do CENPROT")]
    assert "esperando a chave —" in quadro and f"/protesto/{tid}" in quadro
    assert _sem_recolher_aberto(quadro)


def test_a_lista_de_retornos_abre_os_atos_do_arquivo(app):
    c = _entrar(app, "telas_retorno", "ADMIN")
    with app.extensions["db"].transaction() as con:
        bd = banco(con)
        tid = _titulo(con, "9902/1")
        rid = bd.escrever(
            """INSERT INTO pt_retornos (tipo, apresentante_codigo, dia, nome_arquivo,
                   conteudo, gerado_em)
               VALUES ('SDTBFORTP', '001', '2026-10-30', 'R0013010.261', 'x', %s)
               RETURNING id""", (AGORA,))[0]["id"]
        bd.escrever(
            """INSERT INTO pt_atos (titulo_id, tipo, data_ato, retorno_id, criado_em)
               VALUES (%s, 'PROTESTO', '2026-10-30', %s, %s)""", (tid, rid, AGORA))
    html = c.get("/protesto/retornos").get_data(as_text=True)
    assert "1 ato(s)</small></summary>" in html and f"/protesto/{tid}" in html


def test_a_exportacao_do_onr_baixa_o_xml_so_com_a_ficha_completa(app):
    c = _entrar(app, "telas_onr", "MANAGER")
    d = app.extensions["db"]
    d.set_settings({"ri_cns": "000000"})
    with d.transaction() as con:
        boa = _ficha(con, "8001")
        _ficha(con, "8002", cep="")
        banco(con).escrever(
            """UPDATE ri_matriculas SET digi_path=%s, digi_nome=%s, digi_em=%s, digi_por=%s,
                      digi_onr_pendente=1 WHERE id=%s""",
            ("ARQUIVO-DE-TESTE.pdf", "ficha-8001.pdf", AGORA, "BEATRIZ EXEMPLO", boa))
    periodo = {"inicio": "2026-01-01", "fim": "2026-01-31"}
    html = c.get("/registro-imoveis/onr", query_string=periodo).get_data(as_text=True)
    assert "1 de 2 matrícula(s)" in html and "Falta o CEP" in html
    assert "ficha-8001.pdf" in html and "ARQUIVO-DE-TESTE" not in html
    r = c.post("/registro-imoveis/onr",
               data={**periodo, "tipo": "REAL_XML", "csrf_token": _token(html)})
    assert r.status_code == 200 and r.mimetype == "application/xml"
    assert "IndicadorReal_01012026_31012026.XML" in r.headers["Content-Disposition"]
    raiz = ET.fromstring(r.get_data())
    assert [x.findtext("NumeroRegistro") for x in raiz.findall("IndicadorReal")] == ["8001"]


def test_o_escrevente_continua_sem_abrir_a_exportacao(app):
    c = _entrar(app, "telas_carla", "USER")
    assert c.get("/registro-imoveis/onr").status_code == 403


def test_a_tela_dos_livros_mostra_o_que_a_inspecao_cobra_ao_auditor(app):
    c = _entrar(app, "telas_auditor", "AUDITOR")
    html = c.get("/nucleo/livros").get_data(as_text=True)
    assert "O que a inspeção cobra de cada livro" in html
    assert LN.SERIES["RC_A"].nome in html
