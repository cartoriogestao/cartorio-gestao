"""O robô do malote (29/10/2026): entra com a senha do cofre, abre os não lidos, baixa e cadastra.

As páginas abaixo imitam o Malote Digital 26.08.0018 como ele foi medido em
29/10/2026 (os nomes dos campos, o botão `:btnPrepararArquivoInterno` e o
cabeçalho `X-Malote-Resultado-Leitura`). Nada aqui fala com a rede: a sessão é
falsa, e o cofre é um dicionário em memória.
"""
from __future__ import annotations

import json
import re
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
<input type="text" name="Login" value="robo">
<input type="password" name="Senha" value="segredo">
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
        if self.cookies.get("aparelho") == "lembrado":
            self.logado = True
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
        if "f2fa:codigo" in pares:
            if pares["f2fa:codigo"] == self.codigo_certo:
                self.logado = True
                self.cookies.set("aparelho", "lembrado", domain="malote.tjma.jus.br", path="/")
                return Resposta(PAGINA_INICIAL, url)
            return Resposta(PAGINA_2FA, url)
        if "Login" in pares:
            if pares.get("Senha") != self.senha_certa:
                return Resposta(PAGINA_LOGIN, url)
            if self.pede_codigo:
                self.cookies.set("JSESSIONID", "sessao-2fa", domain="malote.tjma.jus.br", path="/")
                return Resposta(PAGINA_2FA, url)
            self.logado = True
            return Resposta(PAGINA_INICIAL, url)
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
    monkeypatch.setattr(MA, "usuario_responsavel", lambda con: 1)
    monkeypatch.setattr(MA, "pasta_do_malote", lambda con: None)
    monkeypatch.setattr(MA, "medir", lambda con, dados, pasta: {
        "cadastrados": 0, "erros": [], "grupos": [
            {"nome": p.name, "situacao": "A_CADASTRAR", "nota": ""}
            for p in (tmp_path / "arquivos" / MA.SUBPASTA_ENTRADA).glob("*.pdf")]})
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


def test_mfa_com_login_e_senha_nao_e_recusa_de_senha():
    pagina = PAGINA_2FA.replace("Informe o código de verificação enviado ao seu e-mail.", "Código MFA:")
    assert MR.pagina(pagina) == MR.DOIS_FATORES
    # Um campo desabilitado não é um pedido de código disponível para enviar.
    pagina = pagina.replace('name="f2fa:codigo"', 'disabled name="f2fa:codigo"')
    assert MR.pagina(pagina) == MR.LOGIN


def test_a_lista_traz_id_e_codigo_de_rastreabilidade():
    linhas = MR._nao_lidos_da_pagina(_lista([("101", "81020265990001"), ("102", "81020265990002")]))
    assert [(l["id"], l["codigo"]) for l in linhas] == [("101", "81020265990001"), ("102", "81020265990002")]


def test_o_jsfcljs_vira_formulario_e_parametros():
    form, params = MR._parametros_do_jsfcljs(
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


@pytest.mark.parametrize("inexistente", [False, True])
def test_sem_responsavel_nao_da_ciencia(tmp_path, monkeypatch, arquivos, inexistente):
    import malote_agente as MA
    CofreNaMemoria({MR.CREDENCIAL: {"usuario": "robo", "senha": "segredo"}}).instalar(monkeypatch)

    def responsavel(con):
        if inexistente:
            raise MA.MaloteError("O usuário configurado não existe. Confira em Configurações.")
        return None
    monkeypatch.setattr(MA, "usuario_responsavel", responsavel)
    malote = MaloteFalso({"101": "81020265990001"})
    r, chamadas = _rodar(_ctx(tmp_path), malote)
    assert r["situacao"] == "AVISO" and malote.lidos == [] and chamadas == []
    assert "Nenhum documento aberto" in r["relato"]


@pytest.mark.parametrize("situacao", ["FRAUDE_PENDENTE", "SEM_RESPONSAVEL", "PARCIAL"])
def test_pendencia_de_inclusao_nao_vira_sucesso(tmp_path, monkeypatch, arquivos, situacao):
    import malote_agente as MA
    CofreNaMemoria({MR.CREDENCIAL: {"usuario": "robo", "senha": "segredo"}}).instalar(monkeypatch)
    monkeypatch.setattr(MA, "medir", lambda *a: {"grupos": [
        {"nome": "oficio.pdf", "situacao": "A_CADASTRAR", "nota": ""}]})
    r = MR.ciencia_diaria(_ctx(tmp_path), cliente=MR.ClienteMalote(MaloteFalso({})),
        copiar=lambda *a: "copia.sqlite3", cadastrar=lambda con: {
            "grupos": [{"nome": "oficio.pdf", "situacao": situacao, "nota": "Confira a pendência."}]})
    assert r["situacao"] == "AVISO"
    assert "1 grupo(s) pendente(s)" in r["relato"]
    assert r["achados"][-1]["situacao"] == situacao


def test_retorna_ao_pdf_baixado_apos_falha_sem_novo_nao_lido(cg_casa, tmp_path, monkeypatch):
    """Portal falso, cofre em memória e PostgreSQL isolado: ciência uma vez,
    backup falha; próxima rodada inclui o PDF e a terceira não o duplica."""
    import malote_agente as MA
    db = cg_casa["db"]
    db.create_user("beatriz", "Beatriz Exemplo de Souza", "Senha#12345", "ADMIN")
    raiz = tmp_path / "acervo_configurado"
    db.set_settings({"archive_root": str(raiz), "malote_cadastra_em_nome_de": "beatriz"})
    CofreNaMemoria({MR.CREDENCIAL: {"usuario": "robo", "senha": "segredo"}}).instalar(monkeypatch)
    monkeypatch.setattr(MA, "capa_do_pdf", lambda p: {
        "codigo": "81020265990001", "nome_original": "oficio.pdf", "assunto": "Ofício de exemplo"})
    ctx = SimpleNamespace(db=db, pasta_dados=cg_casa["dados"], processo={"pode_agir": True})
    malote = MaloteFalso({"101": "81020265990001"})
    copias = []

    def copiar(con, banco):
        copias.append(banco)
        if len(copias) == 1:
            raise OSError("destino da cópia indisponível")
        return "copia.sqlite3"

    r = MR.ciencia_diaria(ctx, cliente=MR.ClienteMalote(malote), copiar=copiar)
    assert r["situacao"] == "ERRO" and malote.lidos == ["101"] and not malote.nao_lidos
    assert list((raiz / MA.SUBPASTA_ENTRADA).glob("*.pdf"))
    assert not (cg_casa["dados"] / "arquivos" / MA.SUBPASTA_ENTRADA).exists()
    with db.connect() as con:
        assert con.execute("SELECT count(*) FROM expedientes").fetchone()[0] == 0
        medicao = MA.medir(con, cg_casa["dados"], None)
        assert medicao["grupos"][0]["situacao"] == "A_CADASTRAR"

    for esperado in (1, 0):
        r = MR.ciencia_diaria(ctx, cliente=MR.ClienteMalote(malote), copiar=copiar)
        assert r["situacao"] == "OK", r
        if esperado:
            assert "1 expediente(s)" in r["relato"]
        else:
            assert r["relato"] == "Nenhum documento não lido no malote."
        with db.connect() as con:
            assert con.execute("SELECT count(*) FROM expedientes").fetchone()[0] == 1
            a = con.execute("SELECT stored_path FROM attachments WHERE entity_type='EXPEDIENTE'").fetchone()
            assert Path(a[0]).is_relative_to(raiz) and Path(a[0]).is_file()
    assert len(copias) == 2 and malote.lidos == ["101"]


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
    # Outro cliente, na próxima rodada, usa o pote do cofre sem novo login/2FA.
    malote3 = MaloteFalso({}, pede_codigo=True)
    r, _ = _rodar(_ctx(tmp_path), malote3)
    assert r["situacao"] == "OK"
    assert not any("Login" in p or "f2fa:codigo" in p for p in malote3.posts)


def test_diagnostico_do_mfa_so_guarda_estrutura(tmp_path, arquivos):
    pagina = PAGINA_2FA.replace('value="vs2"', "value='estado-secreto'") + (
        "<script>token='token-secreto'</script><p>contato-privado@example.test</p>")
    alvo = MR._guardar_pagina_para_conferir(_ctx(tmp_path), pagina, "pedido_do_codigo")
    salvo = Path(alvo).read_text(encoding="utf-8")
    assert "f2fa:codigo" in salvo and "javax.faces.ViewState" in salvo
    assert all(segredo not in salvo for segredo in (
        "segredo", "estado-secreto", "token-secreto", "contato-privado@example.test"))


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


def test_login_so_de_numeros_na_caixa_do_nome_diz_onde_vai_cada_um():
    """29/10/2026: o CPF digitado na caixa do NOME do campo era recusado com
    «nome inválido», sem dizer que ele vai do lado do valor."""
    with pytest.raises(COFRE.CofreError) as erro:
        COFRE._campos_limpos({"00011122233": "segredo"})
    assert "BAIXO" in str(erro.value) and "00011122233" not in str(erro.value)
    assert COFRE._campos_limpos({"usuario": "00011122233", "senha": "x"}) == {
        "usuario": "00011122233", "senha": "x"}


def test_o_cpf_com_mascara_vira_so_numeros_e_outro_login_fica():
    import malote_robo_web as W
    assert W.login_limpo(" 000.111.222-33 ") == "00011122233"
    assert W.login_limpo("00011122233") == "00011122233"
    assert W.login_limpo("Fulano.1") == "Fulano.1"
    assert W.login_limpo("") == ""


def test_o_formulario_do_malote_guarda_o_cpf_como_usuario(monkeypatch):
    """30/10/2026: «sistema nao aceita meu cpf como login do cadastro do malote»."""
    from flask import Flask

    import malote_robo_web as W
    app = Flask(__name__)
    app.secret_key = "teste"
    app.extensions["usuario_nome"] = lambda: "mario"
    auditoria = []
    cofre = CofreNaMemoria()
    cofre.instalar(monkeypatch)
    monkeypatch.setattr("centrais_cred.pasta_de_dados", lambda: Path("."))

    def so_passa(*_):
        return lambda f: f
    W.registrar_rotas(app, None, None, so_passa, lambda *a: auditoria.append(a))
    with app.test_client() as c:
        r = c.post("/automacao/malote/credencial",
                   data={"login_malote": "000.111.222-33", "senha_malote": "segredo"})
    assert r.status_code == 302
    assert cofre.itens[MR.CREDENCIAL]["campos"] == {"usuario": "00011122233", "senha": "segredo"}
    assert "segredo" not in repr(auditoria) and "00011122233" not in repr(auditoria)


def test_tela_escolhe_responsavel_ativo_e_audita(cg_casa_logada):
    casa = cg_casa_logada
    db, c = casa["db"], casa["c"]
    db.create_user("beatriz", "Beatriz Exemplo de Souza", "Senha#12345", "USER")
    tela = c.get("/automacao/malote/codigo").get_data(as_text=True)
    csrf = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', tela).group(1)
    r = c.post("/automacao/malote/responsavel", data={"responsavel_malote": "beatriz", "csrf_token": csrf})
    assert r.status_code == 302
    assert db.get_setting("malote_cadastra_em_nome_de") == "beatriz"
    with db.connect() as con:
        log = con.execute("SELECT details FROM audit_logs WHERE action='MALOTE_ROBO_RESPONSAVEL'").fetchone()
        assert json.loads(log[0])["em_nome_de"] == "beatriz"
    r = c.get("/automacao/malote/codigo")
    assert r.status_code == 200
    assert b'name="responsavel_malote"' in r.data
    assert b'value="beatriz" selected' in r.data
    with db.connect() as con:
        ident = con.execute("SELECT id FROM users WHERE username='beatriz'").fetchone()[0]
    db.set_user_active(ident, False)
    # Inativo, inexistente ou vazio: a configuração anterior não é sobrescrita.
    for login in ("beatriz", "ninguem", ""):
        r = c.post("/automacao/malote/responsavel", data={"responsavel_malote": login, "csrf_token": csrf})
        assert r.status_code == 302 and db.get_setting("malote_cadastra_em_nome_de") == "beatriz"


def test_escolher_responsavel_exige_admin(cg_casa):
    from conftest import cg_login
    db, c = cg_casa["db"], cg_casa["c"]
    r = c.post("/automacao/malote/responsavel", data={"responsavel_malote": "beatriz"})
    assert r.status_code in (302, 403)
    db.create_user("beatriz", "Beatriz Exemplo de Souza", "Senha#12345", "USER")
    cg_login(c, "beatriz", "Senha#12345")
    with c.session_transaction() as sessao:
        csrf = sessao["csrf_token"]
    r = c.post("/automacao/malote/responsavel", data={"responsavel_malote": "beatriz", "csrf_token": csrf})
    assert r.status_code == 403
    assert db.get_setting("malote_cadastra_em_nome_de") == ""


def test_fluxo_com_triagem_retorna_pendencia_e_retoma_sem_novo_documento(tmp_path, monkeypatch, arquivos):
    import malote_fluxo as FL
    import malote_agente as MA
    cofre = CofreNaMemoria({MR.CREDENCIAL: {'usuario': '00011122233', 'senha': 'segredo'}})
    cofre.instalar(monkeypatch)
    monkeypatch.setattr(FL, 'conferir_distribuicao', lambda con: {})
    monkeypatch.setattr(MA, 'medir', lambda *a: {'cadastrados': 0, 'grupos': [], 'erros': []})
    ctx = _ctx(tmp_path)
    ctx.processo['parametros'] = {'triar_recebidos': True}
    chamadas = []
    def triagem(*a, **kw):
        chamadas.append(kw)
        return {'triados': 0, 'tarefas': 0, 'pendentes': 1}
    r = MR.ciencia_diaria(ctx, cliente=MR.ClienteMalote(MaloteFalso({})), triar=triagem)
    assert r['situacao'] == 'ERRO' and 'triagem pendente' in r['relato']
    assert chamadas == [{'somente_malote': True}]


def test_distribuicao_incompleta_para_antes_da_ciencia(tmp_path, monkeypatch, arquivos):
    import malote_fluxo as FL
    cofre = CofreNaMemoria({MR.CREDENCIAL: {'usuario': '00011122233', 'senha': 'segredo'}})
    cofre.instalar(monkeypatch)
    def recusa(*a):raise FL.FluxoMaloteError('falta responsável')
    monkeypatch.setattr(FL, 'conferir_distribuicao', recusa)
    ctx = _ctx(tmp_path); ctx.processo['parametros'] = {'triar_recebidos': True}
    portal = MaloteFalso({'1': '81000000000001'})
    r = MR.ciencia_diaria(ctx, cliente=MR.ClienteMalote(portal))
    assert r['situacao'] == 'AVISO' and not portal.lidos
