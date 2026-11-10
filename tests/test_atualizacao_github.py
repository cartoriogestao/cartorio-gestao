"""A versão nova no GitHub, o botão com a senha do oficial e o pacote parcial (02/11/2026).

Sem rede: o GitHub é um falso que responde como a API. A assinatura fica no modo de transição
(`CHAVES_CONFIAVEIS` vazio), como em `test_update_approval`; ela tem os testes dela.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import pytest

import atualizacao_github as AG

RAIZ = Path(__file__).resolve().parents[1]
SENHA = "SenhaForte123!"
VERSAO_ALVO = "999.999.999"


def pacote() -> tuple[bytes, str]:
    payload = {"VERSAO.txt": VERSAO_ALVO.encode("ascii"),
               "app.py": f'VERSION = "{VERSAO_ALVO}"\n'.encode("ascii")}
    manifesto = {"product": "CartorioGestao", "format": 1, "version": VERSAO_ALVO, "min_version": "0",
                 "files": [{"path": n, "sha256": hashlib.sha256(c).hexdigest()} for n, c in payload.items()],
                 "delete": []}
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as zf:
        zf.writestr("update_manifest.json", json.dumps(manifesto))
        for n, c in payload.items():
            zf.writestr(f"payload/{n}", c)
    dados = saida.getvalue()
    return dados, hashlib.sha256(dados).hexdigest()


RELEASE = {
    "tag_name": f"v{VERSAO_ALVO}", "name": "Cartório Gestão", "published_at": "2026-11-03T10:00:00Z",
    "html_url": "https://github.com/cartoriogestao/cartorio-gestao/releases/tag/v999.999.999",
    "body": "## 999.999.999 — a versão de ensaio",
    "assets": [
        {"name": "CartorioGestao-999.999.999.cgu", "size": 10,
         "browser_download_url": "https://github.com/cartoriogestao/cartorio-gestao/releases/download/v999.999.999/x.cgu"},
        {"name": "CartorioGestao-999.999.999.cgu.sha256", "size": 80,
         "browser_download_url": "https://github.com/cartoriogestao/cartorio-gestao/releases/download/v999.999.999/x.cgu.sha256"},
    ],
}


class _Resposta(io.BytesIO):
    def __init__(self, dados: bytes, url: str = ""):
        super().__init__(dados)
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def _github(dados_do_pacote: bytes, sha: str, *, release=RELEASE):
    def abrir(pedido, timeout=None):
        url = pedido.full_url
        if url.startswith("https://api.github.com/"):
            return _Resposta(json.dumps(release).encode())
        if url.endswith(".sha256"):
            return _Resposta(f"{sha}  x.cgu\n".encode())
        if url.endswith(".cgu"):
            return _Resposta(dados_do_pacote, url="https://objects.githubusercontent.com/x")
        raise AssertionError(url)
    return abrir


# ------------------------------------------------------------------ o módulo

def test_a_release_traz_versao_pacote_e_sha():
    r = AG.ler_release(RELEASE)
    assert r["versao"] == VERSAO_ALVO and r["pacote_url"].endswith(".cgu") and r["sha_url"].endswith(".sha256")


def test_etiqueta_fora_do_formato_e_recusada():
    with pytest.raises(AG.GitHubIndisponivel):
        AG.ler_release({**RELEASE, "tag_name": "ultima"})


def test_versao_mais_nova_compara_numero_e_nao_texto():
    assert AG.e_mais_nova("3.7.10", "3.7.9") and not AG.e_mais_nova("3.7.9", "3.7.10")
    assert not AG.e_mais_nova("3.7.9", "3.7.9") and not AG.e_mais_nova("lixo", "3.7.9")


@pytest.mark.parametrize("url", ["http://github.com/x.cgu", "https://exemplo.invalid/x.cgu",
                                 "file:///etc/passwd"])
def test_nada_fora_do_github_se_abre(url):
    with pytest.raises(AG.GitHubIndisponivel):
        AG._conferir_endereco(url)


def test_baixar_confere_o_sha_e_apaga_o_que_nao_confere(tmp_path):
    dados, sha = pacote()
    release = AG.ler_release(RELEASE)
    arquivo, esperado = AG.baixar(release, tmp_path, limite_bytes=10_000_000, abrir=_github(dados, sha))
    assert esperado == sha and arquivo.read_bytes() == dados
    with pytest.raises(AG.GitHubIndisponivel, match="não confere"):
        AG.baixar(release, tmp_path / "b", limite_bytes=10_000_000, abrir=_github(dados, "0" * 64))
    assert not list((tmp_path / "b").glob("*.cgu"))


def test_baixar_respeita_o_limite(tmp_path):
    dados, sha = pacote()
    with pytest.raises(AG.GitHubIndisponivel, match="limite"):
        AG.baixar(AG.ler_release(RELEASE), tmp_path, limite_bytes=10, abrir=_github(dados, sha))


def test_o_guardado_mantem_a_ultima_resposta_boa_quando_a_rede_falha(tmp_path):
    dados, sha = pacote()
    AG.atualizar_guardado(tmp_path, abrir=_github(dados, sha))
    assert AG.versao_nova(tmp_path, "3.7.9")["versao"] == VERSAO_ALVO

    def sem_rede(pedido, timeout=None):
        raise OSError("sem rede")
    depois = AG.atualizar_guardado(tmp_path, abrir=sem_rede)
    assert "sem rede" in depois["erro"] and depois["release"]["versao"] == VERSAO_ALVO
    assert AG.versao_nova(tmp_path, VERSAO_ALVO) is None


# ------------------------------------------------------------------ a tela

def _csrf(html):
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


@pytest.fixture
def tela():
    import assinatura_da_atualizacao as ASS
    from app import create_app
    with mock.patch.object(ASS, "CHAVES_CONFIAVEIS", {}), TemporaryDirectory() as td:
        app = create_app({"TESTING": True, "DATA_DIR": td})
        app.extensions["backup_checked"] = True
        app.extensions["db"].create_user("oficial", "Oficial Exemplo", SENHA, "ADMIN")
        c = app.test_client()
        c.post("/login", data={"username": "oficial", "password": SENHA,
                               "csrf_token": _csrf(c.get("/login").get_data(as_text=True))})
        yield app, c, Path(td)


def _guardar(pasta: Path, release=RELEASE):
    (pasta / "updates").mkdir(parents=True, exist_ok=True)
    (pasta / "updates" / AG.NOME_DO_GUARDADO).write_text(
        json.dumps({"release": AG.ler_release(release), "consultado_em": "2026-11-03T10:00:00"}),
        encoding="utf-8")


def test_a_tela_avisa_a_versao_nova_e_oferece_o_botao(tela):
    app, c, pasta = tela
    _guardar(pasta)
    html = c.get("/atualizacoes").get_data(as_text=True)
    assert f"Saiu a versão {VERSAO_ALVO}" in html
    assert 'name="action" value="github_atualizar"' in html and 'name="senha_do_oficial"' in html


def test_sem_versao_nova_a_tela_diz_que_esta_em_dia(tela):
    app, c, pasta = tela
    _guardar(pasta, {**RELEASE, "tag_name": "v0.0.1"})
    html = c.get("/atualizacoes").get_data(as_text=True)
    assert "versão mais nova publicada" in html and "github_atualizar" not in html


def test_o_sino_do_layout_novo_avisa(tela):
    app, c, pasta = tela
    _guardar(pasta)
    html = c.get("/").get_data(as_text=True)
    if 'data-layout="novo"' in html:
        assert f"Versão {VERSAO_ALVO} disponível" in html


def test_senha_errada_nao_baixa_nada(tela):
    app, c, pasta = tela
    _guardar(pasta)
    with mock.patch.object(AG, "baixar") as baixar:
        r = c.post("/atualizacoes", data={"csrf_token": _csrf(c.get("/atualizacoes").get_data(as_text=True)),
                                          "action": "github_atualizar", "senha_do_oficial": "errada"},
                   follow_redirects=True)
    assert "Senha incorreta" in r.get_data(as_text=True)
    baixar.assert_not_called()


def test_a_atualizacao_grava_so_o_banco_e_deixa_as_digitalizacoes(tela):
    """A troca do programa não reempacota o acervo: isso enche o disco e a atualização nem começa."""
    import backup as BKP
    app, c, pasta = tela
    _guardar(pasta)
    dados, sha = pacote()
    folha = pasta / "arquivos" / "livro" / "folha.pdf"
    folha.parent.mkdir(parents=True)
    folha.write_bytes(b"%PDF-1.4 folha de teste")

    def baixar(release, destino, *, limite_bytes, abrir=None):
        Path(destino).mkdir(parents=True, exist_ok=True)
        arq = Path(destino) / "baixado.cgu"
        arq.write_bytes(dados)
        return arq, sha

    def timer_imediato(intervalo, func):
        class _T:
            def start(self):
                func()
        return _T()

    with mock.patch.object(AG, "baixar", side_effect=baixar), \
         mock.patch("app.pode_aplicar_sozinho", return_value=(True, "")), \
         mock.patch("app.launch_windows_updater") as subir, \
         mock.patch("app.threading.Timer", side_effect=timer_imediato):
        r = c.post("/atualizacoes", data={"csrf_token": _csrf(c.get("/atualizacoes").get_data(as_text=True)),
                                          "action": "github_atualizar", "senha_do_oficial": SENHA},
                   follow_redirects=True)
    assert r.status_code == 200
    assert f"Atualizacao {VERSAO_ALVO} aprovada" in r.get_data(as_text=True)
    zips = list(pasta.rglob("backup_pre_atualizacao_*.zip"))
    assert len(zips) == 1
    with zipfile.ZipFile(zips[0]) as zf:
        nomes = zf.namelist()
    assert BKP.resumo(zips[0])["tipo"] == "banco"
    assert not any(n.startswith("arquivos/") for n in nomes)
    assert not any(n.endswith("folha.pdf") for n in nomes)
    subir.assert_called_once()


def test_com_a_senha_baixa_prepara_e_chega_a_aplicacao(tela):
    """Até onde o teste vai: a aplicação de verdade é a do Windows, e aqui ela diz por que não aplica."""
    app, c, pasta = tela
    _guardar(pasta)
    dados, sha = pacote()

    def baixar(release, destino, *, limite_bytes, abrir=None):
        Path(destino).mkdir(parents=True, exist_ok=True)
        arq = Path(destino) / "baixado.cgu"
        arq.write_bytes(dados)
        return arq, sha
    with mock.patch.object(AG, "baixar", side_effect=baixar):
        r = c.post("/atualizacoes", data={"csrf_token": _csrf(c.get("/atualizacoes").get_data(as_text=True)),
                                          "action": "github_atualizar", "senha_do_oficial": SENHA},
                   follow_redirects=True)
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "nao foi aprovada" in html, html[:2000]
    meta = json.loads((pasta / "updates" / "staged" / VERSAO_ALVO / "_update_meta.json").read_text("utf-8"))
    assert meta["state"] == "READY_FOR_APPROVAL"


def test_pg_dump_ausente_na_aprovacao_volta_com_aviso(tela):
    """of-0156: sem pg_dump a atualização avisa e não cai em HTTP 500."""
    import banco_pg
    app, c, pasta = tela
    _guardar(pasta)
    dados, sha = pacote()

    def baixar(release, destino, *, limite_bytes, abrir=None):
        Path(destino).mkdir(parents=True, exist_ok=True)
        arq = Path(destino) / "baixado.cgu"
        arq.write_bytes(dados)
        return arq, sha

    with mock.patch.object(AG, "baixar", side_effect=baixar), \
         mock.patch("app.pode_aplicar_sozinho", return_value=(True, "")), \
         mock.patch("banco_pg.binario_do_postgres",
                    side_effect=banco_pg.OperationalError(
                        "pg_dump não encontrado: defina CG_PG_BIN com a pasta bin do PostgreSQL.")):
        r = c.post("/atualizacoes", data={
            "csrf_token": _csrf(c.get("/atualizacoes").get_data(as_text=True)),
            "action": "github_atualizar", "senha_do_oficial": SENHA},
            follow_redirects=True)
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "pg_dump não encontrado" in html
    assert "aprovada" not in html
    meta = json.loads((pasta / "updates" / "staged" / VERSAO_ALVO / "_update_meta.json").read_text("utf-8"))
    assert meta["state"] == "READY_FOR_APPROVAL"


def test_erro_inesperado_ao_preparar_vira_aviso_e_nao_500(tela):
    app, c, pasta = tela
    dados, sha = pacote()
    with mock.patch("app.validate_and_stage", side_effect=KeyError("campo_que_faltou")):
        r = c.post("/atualizacoes", data={
            "csrf_token": _csrf(c.get("/atualizacoes").get_data(as_text=True)), "action": "prepare",
            "expected_sha256": sha, "update_file": (io.BytesIO(dados), "x.cgu")},
            content_type="multipart/form-data", follow_redirects=True)
    assert r.status_code == 200
    assert "erro inesperado (KeyError" in r.get_data(as_text=True)


# ------------------------------------------------------------------ o pacote parcial

def test_o_pacote_parcial_leva_so_o_que_mudou_e_o_que_sumiu(tmp_path):
    raiz = tmp_path / "projeto"
    (raiz / "tools").mkdir(parents=True)
    for nome in ("criar_atualizacao.py",):
        (raiz / "tools" / nome).write_bytes((RAIZ / "tools" / nome).read_bytes())
    (raiz / "update_manager.py").write_bytes((RAIZ / "update_manager.py").read_bytes())
    (raiz / "igual.py").write_text("x = 1\n", encoding="utf-8")
    (raiz / "muda.py").write_text("y = 1\n", encoding="utf-8")
    (raiz / "some.py").write_text("z = 1\n", encoding="utf-8")
    (raiz / "VERSAO.txt").write_text("1.0.0\n", encoding="utf-8")
    (raiz / "app.py").write_text('VERSION = "1.0.0"\n', encoding="utf-8")
    git = ["git", "-C", str(raiz), "-c", "user.name=t", "-c", "user.email=t@t.invalid"]
    subprocess.run(git[:3] + ["init", "-q"], check=True)
    subprocess.run(git + ["add", "-A"], check=True)
    subprocess.run(git + ["commit", "-qm", "1"], check=True)
    subprocess.run(git + ["tag", "v1.0.0"], check=True)
    (raiz / "muda.py").write_text("y = 2\n", encoding="utf-8")
    (raiz / "some.py").unlink()
    (raiz / "novo.py").write_text("w = 1\n", encoding="utf-8")
    (raiz / "VERSAO.txt").write_text("1.0.1\n", encoding="utf-8")
    (raiz / "app.py").write_text('VERSION = "1.0.1"\n', encoding="utf-8")
    saida = tmp_path / "p.cgu"
    subprocess.run([sys.executable, str(raiz / "tools" / "criar_atualizacao.py"), str(raiz),
                    "--version", "1.0.1", "--min-version", "1.0.0", "--desde", "v1.0.0",
                    "--output", str(saida), "--sem-versionar"], check=True, capture_output=True)
    manifesto = json.loads(zipfile.ZipFile(saida).read("update_manifest.json"))
    caminhos = {f["path"] for f in manifesto["files"]}
    assert {"muda.py", "novo.py", "VERSAO.txt", "app.py"} <= caminhos
    assert "igual.py" not in caminhos
    assert manifesto["delete"] == ["some.py"]


def test_as_novidades_da_versao_saem_do_trecho_dela():
    import importlib.util
    spec = importlib.util.spec_from_file_location("publicar_versao", RAIZ / "tools" / "publicar_versao.py")
    pub = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pub)
    texto = "# Novidades\n\n## 3.7.10 — nova\n\n- a\n\n## 3.7.9 — velha\n\n- b\n"
    trecho = pub.novidades_da_versao(texto, "3.7.10")
    assert trecho.startswith("## 3.7.10") and "- a" in trecho and "3.7.9" not in trecho
