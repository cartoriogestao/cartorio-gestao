"""O registro de cada uso de IA e o catálogo dos sistemas (LF01, 19/10/2026).

O QUE SE PROVA AQUI
    - cada chamada ao transporte grava UMA linha em `ia_uso`, com finalidade,
      provedor, tokens e resultado — e NADA do texto que foi ou voltou;
    - a falha também fica: rede, provedor recusando, falta de chave — com um
      resumo de forma fixa, e não a mensagem do provedor;
    - o registro que não grava NÃO derruba a chamada: vai para o log;
    - o transporte dos robôs registra do mesmo jeito;
    - o catálogo cobre todo chamador dos transportes, e não tem entrada sem
      chamada — o teste varre o código, e não uma lista escrita à mão.

A rede é de mentira (o `http.client` e o `urllib` trocados); o banco é o de
verdade, o da casa do módulo. Nada de dado real de pessoa.
"""
from __future__ import annotations

import ast
import json
import logging
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import agente_provedores as PROV                # noqa: E402
import ia_catalogo as CAT                       # noqa: E402
import ia_uso as USO                            # noqa: E402
import robo_llm as LLM                          # noqa: E402
from bd_nativo import banco                     # noqa: E402

CONTEUDO = "TEXTO-DO-ATO-QUE-NAO-PODE-FICAR CPF 000.000.048-55"
RESPOSTA = "RESPOSTA-DO-PROVEDOR-QUE-NAO-PODE-FICAR"


# ------------------------------------------------------- a rede de mentira


class _Resposta:
    def __init__(self, status: int, corpo: bytes):
        self.status, self._corpo = status, corpo

    def read(self) -> bytes:
        return self._corpo


class _Rede:
    """No lugar do `HTTPSConnection`: responde o roteiro e guarda o que subiu."""

    def __init__(self, *respostas: tuple[int, bytes]):
        self.respostas = list(respostas)
        self.corpos: list[bytes] = []

    def __call__(self, host, porta, timeout=None, context=None):
        rede = self

        class _Conexao:
            def request(self, metodo, caminho, body=None, headers=None):
                rede.corpos.append(body)

            def getresponse(self):
                return _Resposta(*rede.respostas.pop(0))

            def close(self):
                pass

        return _Conexao()


def _ok_openai(texto: str = RESPOSTA, entrada: int = 120, saida: int = 30) -> tuple[int, bytes]:
    return 200, json.dumps({
        "model": "deepseek-chat",
        "choices": [{"message": {"content": texto}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": entrada, "completion_tokens": saida}}).encode()


def _conversar(casa, referencia: str, **mais):
    registro = {"modulo": "agente", "finalidade": "agente", "usuario": "tabeliao",
                "referencia": referencia, "mascarado": True}
    registro.update(mais)
    return PROV.conversar(casa["dados"], provedor="deepseek", sistema="instrução",
                          conversa=[{"tipo": "user", "texto": CONTEUDO}],
                          ferramentas=[], **registro)


def _linhas(casa, referencia: str) -> list[dict]:
    with casa["db"].connect() as con:
        return banco(con).ler("SELECT * FROM ia_uso WHERE referencia = %s ORDER BY id",
                              (referencia,))


@pytest.fixture
def casa(cg_casa, monkeypatch):
    PROV.gravar_chave(cg_casa["dados"], "deepseek", "sk-teste-do-registro")
    monkeypatch.setattr(PROV.time, "sleep", lambda *_: None)
    return cg_casa


# ---------------------------------------------------------------- o registro


def test_cada_chamada_grava_uma_linha_com_finalidade_e_tokens_e_sem_o_conteudo(casa, monkeypatch):
    rede = _Rede(_ok_openai())
    monkeypatch.setattr(PROV.http.client, "HTTPSConnection", rede)

    resposta = _conversar(casa, "ag_sessoes:901")

    assert resposta["texto"] == RESPOSTA and CONTEUDO in rede.corpos[0].decode()
    (linha,) = _linhas(casa, "ag_sessoes:901")
    assert {k: linha[k] for k in ("modulo", "finalidade", "provedor", "modelo", "usuario",
                                  "mascarado", "tokens_entrada", "tokens_saida",
                                  "resultado", "erro")} == {
        "modulo": "agente", "finalidade": "agente", "provedor": "deepseek",
        "modelo": "deepseek-chat", "usuario": "tabeliao", "mascarado": True,
        "tokens_entrada": 120, "tokens_saida": 30, "resultado": "ok", "erro": ""}
    gravado = json.dumps(linha, default=str)
    assert "TEXTO-DO-ATO" not in gravado and RESPOSTA not in gravado
    assert "000.000.048-55" not in gravado


def test_a_falha_fica_registrada_com_resumo_fixo_e_sem_a_mensagem_do_provedor(casa, monkeypatch):
    """O 400 traz de volta, na mensagem, um pedaço do que subiu — e é por isso
    que o registro guarda `HTTP 400`, e não a mensagem."""
    eco = json.dumps({"error": {"message": f"campo inválido: {CONTEUDO}"}}).encode()
    monkeypatch.setattr(PROV.http.client, "HTTPSConnection",
                        _Rede((429, b"{}"), (429, b"{}"), (400, eco)))

    with pytest.raises(PROV.AgenteError):
        _conversar(casa, "ag_sessoes:902")
    with pytest.raises(PROV.AgenteError):
        _conversar(casa, "ag_sessoes:903")

    (cheia,) = _linhas(casa, "ag_sessoes:902")
    (recusa,) = _linhas(casa, "ag_sessoes:903")
    assert (cheia["resultado"], cheia["erro"]) == ("erro", "HTTP 429")
    assert (recusa["resultado"], recusa["erro"]) == ("recusado", "HTTP 400")
    assert "TEXTO-DO-ATO" not in json.dumps(recusa, default=str)


def test_sem_chave_o_pedido_fica_registrado_como_recusado(casa):
    PROV.gravar_chave(casa["dados"], "deepseek", "")
    with pytest.raises(PROV.AgenteError):
        _conversar(casa, "ag_sessoes:904")
    (linha,) = _linhas(casa, "ag_sessoes:904")
    assert (linha["resultado"], linha["erro"], linha["tokens_entrada"]) == (
        "recusado", "sem chave", 0)


def test_falha_ao_gravar_o_registro_nao_derruba_a_chamada(casa, monkeypatch, caplog):
    def banco_fora(*_a, **_k):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(PROV.http.client, "HTTPSConnection", _Rede(_ok_openai()))
    monkeypatch.setattr(USO.banco_pg, "conectar", banco_fora)
    with caplog.at_level(logging.ERROR, logger="cartorio.ia"):
        resposta = _conversar(casa, "ag_sessoes:905")
    assert resposta["texto"] == RESPOSTA
    assert "USO DE IA NAO REGISTRADO" in caplog.text and "finalidade=agente" in caplog.text
    assert "TEXTO-DO-ATO" not in caplog.text and RESPOSTA not in caplog.text
    monkeypatch.undo()
    assert _linhas(casa, "ag_sessoes:905") == []


def test_o_transporte_dos_robos_registra_do_mesmo_jeito(casa, monkeypatch):
    class _Url:
        def __init__(self, corpo):
            self.corpo = corpo

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return self.corpo

    def urlopen(pedido, timeout=None):
        assert CONTEUDO in pedido.data.decode()
        return _Url(_ok_openai(entrada=50, saida=7)[1])

    monkeypatch.setattr(LLM.urllib.request, "urlopen", urlopen)
    r = LLM.rascunhar({"prompt": "Rascunhe.", "provedor": "deepseek"}, CONTEUDO,
                      api_key="sk-robo", pasta_de_dados=casa["dados"], modulo="robo_web",
                      finalidade="robo_rascunho", usuario="tabeliao",
                      referencia="robo:906", mascarado=False)
    assert r["modo"] == "api" and r["texto"] == RESPOSTA
    (linha,) = _linhas(casa, "robo:906")
    assert (linha["finalidade"], linha["provedor"], linha["tokens_entrada"],
            linha["tokens_saida"], linha["resultado"], linha["mascarado"]) == (
        "robo_rascunho", "deepseek", 50, 7, "ok", False)


def test_o_teste_do_robo_chama_o_provedor_fora_da_transacao_e_registra(cg_casa_logada,
                                                                       monkeypatch):
    """A tela pedia o rascunho DENTRO do `db.transaction()`, com a trava única
    presa durante a rede. O registro (conexão própria, espera de 800 ms) não
    entraria nunca — e o balcão esperava o provedor para gravar."""
    import re

    import robo_schema as RS
    casa = cg_casa_logada
    with casa["db"].transaction() as con:
        rid = RS.criar_robo(con, nome="Firma", ato="firma", provedor="deepseek",
                            prompt="Rascunhe.", ativo=1, agora="2026-10-19T10:00:00")
        RS.gravar_config(con, RS.CHAVE_DEEPSEEK, "sk-robo-de-teste")
    monkeypatch.setattr(LLM, "_pedir", lambda *a, **k: {
        "texto": "rascunho de teste", "modelo": "deepseek-chat", "entrada": 9, "saida": 4})
    c = casa["c"]
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"',
                      c.get(f"/robos/{rid}").get_data(as_text=True)).group(1)
    r = c.post(f"/robos/{rid}/testar", data={"csrf_token": token, "pedido": CONTEUDO})
    assert r.status_code == 200 and "rascunho de teste" in r.get_data(as_text=True)
    (linha,) = _linhas(casa, f"robo:{rid}")
    assert (linha["modulo"], linha["finalidade"], linha["resultado"],
            linha["tokens_entrada"]) == ("robo_web", "robo_rascunho", "ok", 9)
    assert linha["usuario"] and "TEXTO-DO-ATO" not in json.dumps(linha, default=str)


def test_o_robo_sem_pasta_de_dados_segue_e_o_registro_vai_para_o_log(monkeypatch, caplog):
    monkeypatch.setattr(LLM, "_pedir", lambda *a, **k: {"texto": "ok", "modelo": "m",
                                                        "entrada": 1, "saida": 1})
    with caplog.at_level(logging.ERROR, logger="cartorio.ia"):
        assert LLM.chamar_provedor("grok", "xai-k", "s", "u", finalidade="robo_rascunho") == "ok"
    assert "USO DE IA NAO REGISTRADO" in caplog.text


# ---------------------------------------------------- o que o fornecedor diz


def test_a_pendencia_aponta_o_que_contraria_o_requisito_sem_decidir():
    assert USO.pendencias(None) == [
        "Dados do fornecedor não preenchidos — sem eles não há como conferir o "
        "requisito do MA."]
    conforme = {"empresa": "Empresa Exemplo", "pais_processa": "Brasil",
                "pais_armazena": "brasil", "retencao": USO.NAO_GUARDA,
                "iso27001": USO.SIM, "treinamento": USO.NAO}
    assert USO.pendencias(conforme) == []
    fora = dict(conforme, pais_armazena="Estados Unidos", retencao=USO.GUARDA,
                retencao_prazo="30 dias", iso27001=USO.NAO_SEI)
    texto = " ".join(USO.pendencias(fora))
    assert "fora do Brasil (Estados Unidos)" in texto
    assert "guarda o que recebe (30 dias)" in texto and "ISO 27001: não sei" in texto


# ---------------------------------------------------------- o catálogo


def _apelidos(arvore: ast.AST) -> tuple[dict[str, str], set[str]]:
    """Os nomes locais dos módulos de transporte, e das funções importadas."""
    modulos: dict[str, str] = {}
    funcoes: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            for a in no.names:
                if a.name in CAT.TRANSPORTES:
                    modulos[a.asname or a.name] = a.name
        elif isinstance(no, ast.ImportFrom) and no.module in CAT.TRANSPORTES:
            for a in no.names:
                if a.name in CAT.TRANSPORTES[no.module]:
                    funcoes.add(a.asname or a.name)
    return modulos, funcoes


def _quem_pega_o_transporte(fonte: str) -> list[dict]:
    """Cada função que pega um transporte, com a finalidade e o módulo que diz.

    «Pegar» é citar `apelido.conversar` (ou `chamar_provedor`/`rascunhar`):
    chamar direto, pôr como padrão do `conversar=` injetado ou prender num
    `functools.partial`. É essa função que tem de dizer a finalidade — o
    transporte injetado mais para dentro herda o que ela disse.
    """
    arvore = ast.parse(fonte)
    modulos, funcoes = _apelidos(arvore)
    achadas = []
    for f in ast.walk(arvore):
        if not isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        pega = any(
            (isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
             and n.value.id in modulos and n.attr in CAT.TRANSPORTES[modulos[n.value.id]])
            or (isinstance(n, ast.Name) and n.id in funcoes)
            for n in ast.walk(f))
        if not pega:
            continue
        diz = {"finalidade": set(), "modulo": set()}
        for n in ast.walk(f):
            if isinstance(n, ast.Call):
                for k in n.keywords:
                    if k.arg in diz and isinstance(k.value, ast.Constant):
                        diz[k.arg].add(k.value.value)
        achadas.append({"funcao": f.name, "linha": f.lineno, **diz})
    return achadas


def _fontes_do_sistema() -> list[Path]:
    """O código que roda: a raiz e `tools/`. Os transportes e os testes, não."""
    return [p for p in sorted([*RAIZ.glob("*.py"), *RAIZ.glob("tools/*.py")])
            if p.stem not in CAT.TRANSPORTES]


def test_a_varredura_pega_quem_chama_o_transporte_sem_finalidade():
    """O teste do teste: um chamador novo, sem finalidade, é achado."""
    fonte = ("import agente_provedores as X\n"
             "def novo(p):\n    return X.conversar(p, provedor='claude')\n"
             "def injetado(p, conversar=None):\n"
             "    conversar = conversar or X.conversar\n"
             "    return conversar(p, finalidade='agente', modulo='agente')\n"
             "def so_chave(p):\n    return X.tem_chave(p)\n")
    achadas = {a["funcao"]: a for a in _quem_pega_o_transporte(fonte)}
    assert set(achadas) == {"novo", "injetado"}
    assert achadas["novo"]["finalidade"] == set()
    assert achadas["injetado"]["finalidade"] == {"agente"}


def test_o_catalogo_cobre_todo_chamador_dos_transportes():
    """Chamada a um transporte de IA sem entrada no catálogo faz este teste falhar.

    E o contrário também: entrada no catálogo sem chamada no código é catálogo
    que mente, e o relatório à COGEX listaria um sistema que não existe.
    """
    problemas, vistas = [], set()
    for caminho in _fontes_do_sistema():
        for a in _quem_pega_o_transporte(caminho.read_text(encoding="utf-8")):
            onde = f"{caminho.name}:{a['linha']} ({a['funcao']})"
            if not a["finalidade"]:
                problemas.append(f"{onde}: pega o transporte e não diz a finalidade")
            for codigo in a["finalidade"]:
                item = CAT.entrada(codigo)
                if item is None:
                    problemas.append(f"{onde}: finalidade «{codigo}» fora do catálogo")
                elif item["modulo"] != caminho.stem:
                    problemas.append(f"{onde}: «{codigo}» é do módulo {item['modulo']} "
                                     f"no catálogo")
                else:
                    vistas.add(codigo)
            if a["modulo"] != {caminho.stem}:
                problemas.append(f"{onde}: modulo={sorted(a['modulo'])}, e o arquivo é "
                                 f"{caminho.stem}")
    for item in CAT.CATALOGO:
        if item["codigo"] not in vistas:
            problemas.append(f"catálogo: «{item['codigo']}» sem chamada em {item['modulo']}.py")
    assert not problemas, "\n".join(problemas)


def test_toda_entrada_do_catalogo_diz_o_que_a_norma_pede():
    """Finalidade, inciso, dado, máscara, revisão humana e o que a IA não faz."""
    codigos = [e["codigo"] for e in CAT.CATALOGO]
    assert len(codigos) == len(set(codigos))
    for e in CAT.CATALOGO:
        for campo in ("nome", "onde", "finalidade", "dado", "mascara",
                      "revisao_humana", "nao_faz", "chave", "enquadramento"):
            assert str(e.get(campo) or "").strip(), (e["codigo"], campo)
        assert all(parte in CAT.INCISOS_DO_ART_171
                   for parte in e["inciso"].replace(" e ", " ").split()), e["codigo"]
        assert "não encontrado" not in CAT.teto_de(e), e["codigo"]
    assert "conferir o texto oficial do Código de Normas" in CAT.AVISO_DO_TEXTO_OFICIAL
