"""O robô do malote (29/10/2026): entra com a senha do cofre, abre os não lidos, baixa e cadastra.

As páginas abaixo imitam o Malote Digital 26.08.0018 como ele foi medido em
29/10/2026 (os nomes dos campos, o botão `:btnPrepararArquivoInterno` e o
cabeçalho `X-Malote-Resultado-Leitura`). Nada aqui fala com a rede: a sessão é
falsa, e o cofre é um dicionário em memória.
"""
from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from requests.cookies import RequestsCookieJar

import automacao_cofre as COFRE
import malote_robo as MR

PAGINA_LOGIN = """<html><body><p>Habilitado duplo fator de acesso (2FA).</p>
<form id="inicial:formLogin" name="inicial:formLogin" method="post" action="/malotedigital/login.jsf;jsessionid=X">
<input type="hidden" name="inicial:formLogin" value="inicial:formLogin">
<input type="hidden" name="csrf" value="abc">
<input type="text" name="Login" id="Login" value="">
<input type="password" name="Senha" id="Senha" value="">
<input type="submit" name="inicial:formLogin:cmdLogin" value="ACESSE »">
<input type="hidden" name="javax.faces.ViewState" value="vs1">
</form></body></html>"""

PAGINA_2FA = """<html><body><p>Informe o código de verificação enviado ao seu e-mail.</p>
<form id="f2fa" method="post" action="/malotedigital/login.jsf">
<input type="text" name="f2fa:codigo" id="f2fa:codigo" value="">
<input type="submit" name="f2fa:confirmar" value="Confirmar">
<input type="hidden" name="javax.faces.ViewState" value="vs2">
</form></body></html>"""

MENU = """<form id="menuLateral:m" method="post" action="/malotedigital/goto.jsf">
<input type="hidden" name="menuLateral:m" value="menuLateral:m">
<a href="#" onclick="if(typeof jsfcljs == 'function'){jsfcljs(document.getElementById('menuLateral:m'),{'menuLateral:m:naoLidos':'menuLateral:m:naoLidos'},'');}return false">» Não Lidos</a>
</form>"""

PAGINA_INICIAL = f"<html><body><a>Fazer Logoff</a>{MENU}</body></html>"


def _lista(ids_e_codigos) -> str:
    linhas = "".join(
        f"<tr><td><span class=\"codigoRastreabilidadeDocumento\">{c}</span></td>"
        f"<td><a href=\"#\" onclick=\"return prepararArquivoInterno(this,'{i}')\">doc {i}.pdf</a></td></tr>"
        for i, c in ids_e_codigos)
    return (f"<html><body><a>Fazer Logoff</a>{MENU}"
            "<form id=\"pesquisaDocumentoNaoLidoBean:pesquisa\" method=\"post\" action=\"/malotedigital/goto.jsf\">"
            "<input type=\"hidden\" name=\"idDocumentoLeitura\" id=\"idDocumentoLeitura\" value=\"\">"
            "<input type=\"submit\" name=\"pesquisaDocumentoNaoLidoBean:pesquisa:btnPrepararArquivoInterno\" "
            "id=\"pesquisaDocumentoNaoLidoBean:pesquisa:btnPrepararArquivoInterno\" value=\"x\" style=\"display:none\">"
            "<input type=\"hidden\" name=\"javax.faces.ViewState\" value=\"vs3\">"
            f"<table>{linhas}</table></form></body></html>")


def _pdf(codigo: str) -> bytes:
    return f"%PDF-1.4 capa {codigo}".encode()


class Resposta:
    def __init__(self, text="", url="", headers=None, content=None):
        self.text, self.url, self.headers = text, url, headers or {}
        self.content = content if content is not None else text.encode()


class MaloteFalso:
    """O malote do lado de lá: guarda quem entrou, o que foi lido e o que foi pedido."""

    def __init__(self, nao_lidos, *, pede_codigo=False, codigo_certo="123456", senha_certa="segredo"):
        self.nao_lidos = dict(nao_lidos)          # id -> codigo
        self.codigos = dict(nao_lidos)
        self.pede_codigo, self.codigo_certo, self.senha_certa = pede_codigo, codigo_certo, senha_certa
        self.logado = False
        self.lidos: list[str] = []
        self.atual: str | None = None
        self.posts: list[dict] = []
        self.cookies = RequestsCookieJar()

    def get(self, url, timeout=None):
        if url.endswith("login.jsf"):
            return Resposta(PAGINA_INICIAL if self.logado else PAGINA_LOGIN, url)
        if url.endswith("inicial.jsf"):
            return Resposta(PAGINA_INICIAL if self.logado else PAGINA_LOGIN, url)
        if url.endswith("documentoLeitorPDF.jsf"):
            return Resposta(url=url, content=_pdf(self.codigos.get(self.atual) or str(self.atual)))
        return Resposta("<html></html>", url)

    def post(self, url, data=None, timeout=None, headers=None):
        from urllib.parse import parse_qsl
        pares = dict(parse_qsl(data.decode()))
        self.posts.append(pares)
        if "Login" in pares:
            if pares.get("Senha") != self.senha_certa:
                return Resposta(PAGINA_LOGIN, url)
            if self.pede_codigo:
                self.cookies.set("JSESSIONID", "sessao-2fa", domain="malote.tjma.jus.br", path="/")
                return Resposta(PAGINA_2FA, url)
            self.logado = True
            return Resposta(PAGINA_INICIAL, url)
        if "f2fa:codigo" in pares:
            if pares["f2fa:codigo"] == self.codigo_certo:
                self.logado = True
                self.cookies.set("aparelho", "lembrado", domain="malote.tjma.jus.br", path="/")
                return Resposta(PAGINA_INICIAL, url)
            return Resposta(PAGINA_2FA, url)
        if "menuLateral:m:naoLidos" in pares:
            return Resposta(_lista(sorted(self.nao_lidos.items())), url)
        if pares.get("idDocumentoLeitura"):
            ident = pares["idDocumentoLeitura"]
            assert any(k.endswith(":btnPrepararArquivoInterno") for k in pares), "o botão tem de ir junto"
            self.atual = ident
            self.lidos.append(ident)
            self.nao_lidos.pop(ident, None)          # lido sai da lista de não lidos
            return Resposta("", url, headers={MR.CABECALHO_DA_LEITURA: "sucesso"})
        return Resposta("<html></html>", url)


class CofreNaMemoria:
    def __init__(self, itens=None):
        self.itens = {k: {"campos": v, "alterado_em": datetime.now().isoformat(timespec="seconds")}
                      for k, v in (itens or {}).items()}

    def instalar(self, monkeypatch):
        monkeypatch.setattr(COFRE, "caminho_do_cofre", lambda pasta=None: Path("cofre.json"))
        monkeypatch.setattr(COFRE, "ler", self.ler)
        monkeypatch.setattr(COFRE, "gravar", self.gravar)
        monkeypatch.setattr(COFRE, "remover", self.remover)
        monkeypatch.setattr(COFRE, "metadados", self.metadados)

    def ler(self, nome, **_):
        if nome not in self.itens:
            raise COFRE.ItemInexistente(nome)
        return dict(self.itens[nome]["campos"])

    def gravar(self, nome, campos, **_):
        self.itens[nome] = {"campos": dict(campos), "alterado_em": datetime.now().isoformat(timespec="seconds")}
        return {"nome": nome}

    def remover(self, nome, **_):
        return self.itens.pop(nome, None) is not None

    def metadados(self, nome, **_):
        if nome not in self.itens:
            raise COFRE.ItemInexistente(nome)
        return {"nome": nome, "alterado_em": self.itens[nome]["alterado_em"]}


class _Db:
    db_path = "banco.sqlite3"

    @contextmanager
    def connect(self):
        yield object()


def _ctx(tmp_path, pode_agir=True):
    return SimpleNamespace(pasta_dados=tmp_path, db=_Db(),
                           processo={"codigo": "MALOTE_CIENCIA_DIARIA", "pode_agir": pode_agir})


@pytest.fixture()
def arquivos(tmp_path, monkeypatch):
    import malote_agente as MA
    monkeypatch.setattr(MA, "archive_root_de", lambda pasta, con=None: tmp_path / "arquivos")
    monkeypatch.setattr(MA, "capa_do_pdf", lambda caminho: {
        "codigo": caminho.read_bytes().decode().split()[-1], "nome_original": "oficio.pdf"})
    return tmp_path / "arquivos"


def _rodar(ctx, malote, cadastrados=None):
    chamadas = []

    def cadastrar(con):
        chamadas.append(con)
        return {"cadastrados": cadastrados if cadastrados is not None else len(malote.lidos),
                "fraudes": [], "erros": []}
    r = MR.ciencia_diaria(ctx, cliente=MR.ClienteMalote(malote), cadastrar=cadastrar,
                          copiar=lambda con, banco: "copia.sqlite3")
    return r, chamadas


# ------------------------------------------------------------------ a leitura das páginas


def test_reconhece_as_tres_paginas():
    assert MR.pagina(PAGINA_LOGIN) == MR.LOGIN
    assert MR.pagina(PAGINA_INICIAL) == MR.LOGADO
    assert MR.pagina(PAGINA_2FA) == MR.DOIS_FATORES
    assert MR.pagina("<html><body>outra coisa</body></html>") == MR.DESCONHECIDA


def test_a_lista_traz_id_e_codigo_de_rastreabilidade():
    linhas = MR.nao_lidos_da_pagina(_lista([("101", "81020265990001"), ("102", "81020265990002")]))
    assert [(l["id"], l["codigo"]) for l in linhas] == [("101", "81020265990001"), ("102", "81020265990002")]


def test_o_jsfcljs_vira_formulario_e_parametros():
    form, params = MR.parametros_do_jsfcljs(
        "jsfcljs(document.getElementById('menuLateral:m'),{'a:b':'a:b','c':'1'},'')")
    assert form == "menuLateral:m" and params == {"a:b": "a:b", "c": "1"}


def test_a_serializacao_e_a_do_navegador():
    leitor = MR.ler_pagina(PAGINA_LOGIN)
    pares = dict(MR.serializar(leitor.formularios[0], trocar={"Login": "u", "Senha": "s"}))
    assert pares["Login"] == "u" and pares["Senha"] == "s" and pares["csrf"] == "abc"
    assert "inicial:formLogin:cmdLogin" not in pares          # botão só vai quando é ele o clicado


# ------------------------------------------------------------------ a rodada


def test_entra_com_o_cofre_abre_baixa_e_cadastra(tmp_path, monkeypatch, arquivos):
    CofreNaMemoria({MR.CREDENCIAL: {"usuario": "robo", "senha": "segredo"}}).instalar(monkeypatch)
    malote = MaloteFalso({"101": "81020265990001", "102": "81020265990002"})
    r, chamadas = _rodar(_ctx(tmp_path), malote)
    assert r["situacao"] == "OK", r
    assert sorted(malote.lidos) == ["101", "102"]
    entrada = sorted(p.name for p in (arquivos / "malote" / "entrada").iterdir())
    assert entrada == ["MALOTE_81020265990001_oficio.pdf", "MALOTE_81020265990002_oficio.pdf"]
    assert len(chamadas) == 1
    assert "2 documento(s) aberto(s)" in r["relato"]


def test_sem_pode_agir_conta_e_nao_abre(tmp_path, monkeypatch, arquivos):
    CofreNaMemoria({MR.CREDENCIAL: {"usuario": "robo", "senha": "segredo"}}).instalar(monkeypatch)
    malote = MaloteFalso({"101": "81020265990001"})
    r, chamadas = _rodar(_ctx(tmp_path, pode_agir=False), malote)
    assert r["situacao"] == "AVISO" and malote.lidos == [] and chamadas == []
    assert "nenhum aberto" in r["relato"]


def test_nada_nao_lido_nao_copia_nem_cadastra(tmp_path, monkeypatch, arquivos):
    CofreNaMemoria({MR.CREDENCIAL: {"usuario": "robo", "senha": "segredo"}}).instalar(monkeypatch)
    r, chamadas = _rodar(_ctx(tmp_path), MaloteFalso({}))
    assert r["situacao"] == "OK" and chamadas == [] and r["relato"] == "Nenhum documento não lido no malote."


def test_sem_credencial_e_erro_com_o_caminho(tmp_path, monkeypatch, arquivos):
    CofreNaMemoria().instalar(monkeypatch)
    r, _ = _rodar(_ctx(tmp_path), MaloteFalso({"101": "1"}))
    assert r["situacao"] == "ERRO" and MR.CREDENCIAL in r["relato"]


def test_senha_errada_nao_insiste(tmp_path, monkeypatch, arquivos):
    CofreNaMemoria({MR.CREDENCIAL: {"usuario": "robo", "senha": "errada"}}).instalar(monkeypatch)
    malote = MaloteFalso({"101": "1"})
    r, _ = _rodar(_ctx(tmp_path), malote)
    assert r["situacao"] == "ERRO" and "recusou a entrada" in r["relato"]
    assert sum(1 for p in malote.posts if "Login" in p) == 1


def test_o_2fa_espera_o_codigo_e_retoma_a_mesma_sessao(tmp_path, monkeypatch, arquivos):
    cofre = CofreNaMemoria({MR.CREDENCIAL: {"usuario": "robo", "senha": "segredo"}})
    cofre.instalar(monkeypatch)
    malote = MaloteFalso({"101": "81020265990001"}, pede_codigo=True)
    r, _ = _rodar(_ctx(tmp_path), malote)
    assert r["situacao"] == "AVISO" and "código de dois fatores" in r["relato"]
    guardado = cofre.itens[MR.SESSAO]["campos"]
    assert json.loads(guardado["formulario_2fa"])["campo"] == "f2fa:codigo"
    assert any(c["name"] == "JSESSIONID" for c in json.loads(guardado["cookies"]))
    assert list((arquivos / "malote" / "robo").glob("*pedido_do_codigo.html"))   # guardada para conferir
    assert malote.lidos == []

    cofre.gravar(MR.CODIGO, {"codigo": "123456"})                  # o oficial digita na tela
    malote2 = MaloteFalso({"101": "81020265990001"}, pede_codigo=True)
    r, _ = _rodar(_ctx(tmp_path), malote2)
    assert r["situacao"] == "OK", r
    assert malote2.lidos == ["101"]
    assert MR.CODIGO not in cofre.itens                             # usado, apagado
    assert any(c["name"] == "aparelho" for c in json.loads(cofre.itens[MR.SESSAO]["campos"]["cookies"]))
    assert "formulario_2fa" not in cofre.itens[MR.SESSAO]["campos"]


def test_codigo_velho_nao_e_usado(tmp_path, monkeypatch, arquivos):
    cofre = CofreNaMemoria({MR.CREDENCIAL: {"usuario": "robo", "senha": "segredo"},
                            MR.SESSAO: {"cookies": "[]", "formulario_2fa": json.dumps(
                                {"formulario": MR.ler_pagina(PAGINA_2FA).formularios[0],
                                 "campo": "f2fa:codigo", "url": MR.URL_LOGIN})},
                            MR.CODIGO: {"codigo": "123456"}})
    cofre.itens[MR.CODIGO]["alterado_em"] = (datetime.now() - timedelta(minutes=40)).isoformat(timespec="seconds")
    cofre.instalar(monkeypatch)
    malote = MaloteFalso({"101": "1"}, pede_codigo=True)
    r, _ = _rodar(_ctx(tmp_path), malote)
    assert r["situacao"] == "AVISO"
    assert not any("f2fa:codigo" in p for p in malote.posts)
    assert MR.CODIGO not in cofre.itens


def test_cofre_trancado_e_aviso(tmp_path, monkeypatch, arquivos):
    def trancado(*a, **k):
        raise COFRE.CofreTrancado("trancado")
    CofreNaMemoria().instalar(monkeypatch)
    monkeypatch.setattr(COFRE, "ler", trancado)
    r, _ = _rodar(_ctx(tmp_path), MaloteFalso({"101": "1"}))
    assert r["situacao"] == "AVISO" and "trancado" in r["relato"]


def test_capa_que_nao_bate_nao_entra_na_entrada(tmp_path, monkeypatch, arquivos):
    import malote_agente as MA
    CofreNaMemoria({MR.CREDENCIAL: {"usuario": "robo", "senha": "segredo"}}).instalar(monkeypatch)
    monkeypatch.setattr(MA, "capa_do_pdf", lambda caminho: {"codigo": "99999999999999", "nome_original": "x.pdf"})
    r, chamadas = _rodar(_ctx(tmp_path), MaloteFalso({"101": "81020265990001"}))
    assert r["situacao"] == "ERRO" and chamadas == []
    assert not list((arquivos / "malote" / "entrada").glob("*.pdf"))
    assert list((arquivos / "malote" / "robo").glob("CONFERIR_101.pdf"))


def test_o_segredo_nao_vai_ao_relato(tmp_path, monkeypatch, arquivos):
    CofreNaMemoria({MR.CREDENCIAL: {"usuario": "robo", "senha": "segredo"}}).instalar(monkeypatch)
    r, _ = _rodar(_ctx(tmp_path), MaloteFalso({"101": "81020265990001"}))
    assert "segredo" not in json.dumps(r, ensure_ascii=False)


# ------------------------------------------------------------------ o lugar no hub


def test_o_processo_entra_no_catalogo_desligado_e_as_8h():
    import automacao_processos as PROC
    semente = next(s for s in PROC.todas_as_sementes() if s["codigo"] == "MALOTE_CIENCIA_DIARIA")
    assert semente["alvo"] == "malote_robo:ciencia_diaria"
    assert semente["agenda"]["horarios"] == ["08:00"]


def test_a_tela_do_codigo_nao_le_o_cofre():
    texto = Path(__file__).resolve().parent.parent.joinpath("malote_robo_web.py").read_text(encoding="utf-8")
    assert "COFRE.ler(" not in texto and ".ler(" not in texto.replace("COFRE.gravar(", "")
