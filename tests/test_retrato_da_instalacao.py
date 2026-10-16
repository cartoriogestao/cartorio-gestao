"""O retrato da instalação (14/10/2026): o que mudou por fora aparece, e o pacote
não apaga calado o conserto feito na produção.

Tudo em tmp_path — uma instalação de mentira, uma pasta de atualizações de
mentira. Nada aqui lê nem escreve a produção.
"""
from __future__ import annotations

import hashlib
import json
import sys
import zipfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import retrato_da_instalacao as RET   # noqa: E402
import update_manager as UM           # noqa: E402


def _sha(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _instalacao(tmp_path: Path, versao="3.6.1") -> Path:
    inst = tmp_path / "Program Files" / "CartorioGestao"
    (inst / "templates").mkdir(parents=True)
    (inst / "app.py").write_text(f'VERSION = "{versao}"\n', encoding="utf-8")
    (inst / "VERSAO.txt").write_text(versao, encoding="utf-8")
    (inst / "modulo.py").write_text("X = 1\n", encoding="utf-8")
    (inst / "templates" / "tela.html").write_text("<p>tela</p>", encoding="utf-8")
    return inst


def _aplicado(updates: Path, inst: Path, versao="3.6.1"):
    """Uma preparação APPLIED desta versão, como o aplicador a deixa."""
    pasta = updates / "staged" / versao
    pasta.mkdir(parents=True)
    arquivos = [{"path": p.relative_to(inst).as_posix(),
                 "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                for p in inst.rglob("*") if p.is_file()]
    (pasta / "_update_meta.json").write_text(json.dumps({
        "state": "APPLIED", "manifest": {"version": versao, "source_commit": "abc123"},
        "package_sha256": "f" * 64, "checked_files": arquivos}), encoding="utf-8")


# ---------------------------------------------------------- o retrato

def test_o_retrato_vem_do_pacote_aplicado(tmp_path):
    inst = _instalacao(tmp_path)
    updates = tmp_path / "updates"
    _aplicado(updates, inst)
    r = RET.vigente(updates, inst, "3.6.1")
    assert r["origem"] == "PACOTE" and r["commit"] == "abc123"
    assert "modulo.py" in r["arquivos"]


def test_sem_pacote_que_explique_a_versao_o_retrato_e_medido_e_diz_isso(tmp_path):
    inst = _instalacao(tmp_path)
    r = RET.vigente(tmp_path / "updates", inst, "3.6.1")
    assert r["origem"] == "MEDIDO" and "medido" in r["observacao"]


def test_a_conferencia_acha_o_que_mudou_por_fora(tmp_path):
    inst = _instalacao(tmp_path)
    updates = tmp_path / "updates"
    _aplicado(updates, inst)
    assert RET.conferir(updates, inst, "3.6.1")["limpo"]
    (inst / "modulo.py").write_text("X = 2  # copiado por fora\n", encoding="utf-8")
    (inst / "tmp_rascunho.py").write_text("print(1)\n", encoding="utf-8")
    (inst / "templates" / "tela.html").unlink()
    r = RET.conferir(updates, inst, "3.6.1")
    assert r["alterados"] == ["modulo.py"]
    assert r["novos"] == ["tmp_rascunho.py"]
    assert r["sumidos"] == ["templates/tela.html"]
    assert RET.ultima_conferencia(updates)["alterados"] == ["modulo.py"]


def test_o_cache_nao_le_de_novo_o_que_nao_mudou(tmp_path, monkeypatch):
    """Medido em 14/10/2026: ler a produção inteira levou 280 s."""
    inst = _instalacao(tmp_path)
    updates = tmp_path / "updates"
    RET.medir(inst, updates)
    lidos = []
    original = RET._sha
    monkeypatch.setattr(RET, "_sha", lambda p: lidos.append(p.name) or original(p))
    RET.medir(inst, updates)
    assert lidos == []
    (inst / "modulo.py").write_text("X = 3333\n", encoding="utf-8")
    RET.medir(inst, updates)
    assert lidos == ["modulo.py"]


# ---------------------------------------------------------- o conflito

def test_conflito_e_o_arquivo_mudado_por_fora_que_o_pacote_trocaria(tmp_path):
    inst = _instalacao(tmp_path)
    updates = tmp_path / "updates"
    _aplicado(updates, inst)
    (inst / "modulo.py").write_text("X = 2  # conserto feito na produção\n", encoding="utf-8")
    c = RET.conflitos_do_pacote(updates, inst, "3.6.1",
                                {"modulo.py": _sha("X = 9\n"), "app.py": _sha("outro")})
    assert [x["path"] for x in c] == ["modulo.py"]


def test_sem_conflito_quando_o_pacote_ja_traz_o_conserto(tmp_path):
    inst = _instalacao(tmp_path)
    updates = tmp_path / "updates"
    _aplicado(updates, inst)
    conserto = "X = 2  # conserto feito na produção\n"
    # bytes exatos: no Windows `write_text` poria CRLF, e o SHA-256 seria outro
    (inst / "modulo.py").write_bytes(conserto.encode("utf-8"))
    assert RET.conflitos_do_pacote(updates, inst, "3.6.1",
                                   {"modulo.py": _sha(conserto)}) == []


def _pacote(caminho: Path, versao: str, arquivos: dict[str, str]) -> Path:
    manifesto = {"product": "CartorioGestao", "format": 1, "version": versao,
                 "min_version": "0", "notes": "", "run_pip": False, "delete": [],
                 "files": [{"path": r, "sha256": _sha(t)} for r, t in arquivos.items()]}
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr("update_manifest.json", json.dumps(manifesto))
        for r, t in arquivos.items():
            z.writestr(f"payload/{r}", t)
    return caminho


def test_a_inspecao_bloqueia_o_pacote_que_apagaria_o_conserto(tmp_path, monkeypatch):
    # Pacote montado à mão, sem assinatura: desde 14/10/2026 há chave
    # cadastrada, e aqui se mede a OUTRA trava (o conserto apagado). Modo de
    # transição, como em test_update_network.py.
    import assinatura_da_atualizacao as ASS
    monkeypatch.setattr(ASS, "CHAVES_CONFIAVEIS", {})
    inst = _instalacao(tmp_path)
    updates = tmp_path / "updates"
    _aplicado(updates, inst)
    (inst / "modulo.py").write_text("X = 2  # conserto feito na produção\n", encoding="utf-8")
    pacote = _pacote(tmp_path / "p.cgu", "3.6.2", {
        "app.py": 'VERSION = "3.6.2"\n', "VERSAO.txt": "3.6.2", "modulo.py": "X = 1\n"})
    meta = UM.validate_and_stage(pacote, updates / "staged", "3.6.1")
    insp = UM.inspect_staged(Path(meta["stage_dir"]), inst)
    assert not insp["ok"]
    assert [c["path"] for c in insp["conflitos"]] == ["modulo.py"]
    assert any("sobrescreveria" in p for p in insp["problems"])


def test_aceito_o_estado_instalado_o_pacote_passa(tmp_path):
    inst = _instalacao(tmp_path)
    updates = tmp_path / "updates"
    _aplicado(updates, inst)
    (inst / "modulo.py").write_text("X = 2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="dez letras"):
        RET.aceitar(updates, inst, "3.6.1", por="oficial", motivo="ok")
    RET.aceitar(updates, inst, "3.6.1", por="oficial",
                motivo="o conserto já foi levado ao INSTALAR")
    assert RET.conflitos_do_pacote(updates, inst, "3.6.1", {"modulo.py": _sha("X = 9\n")}) == []


# ---------------------------------------------------------- a emergência

def test_a_emergencia_deixa_pendencia_ate_o_sandbox_ter_o_mesmo(tmp_path):
    inst = _instalacao(tmp_path)
    updates = tmp_path / "updates"
    sandbox = tmp_path / "SANDBOX" / "sistema"
    sandbox.mkdir(parents=True)
    _aplicado(updates, inst)
    RET.vigente(updates, inst, "3.6.1")
    (inst / "modulo.py").write_text("X = 2  # emergência\n", encoding="utf-8")
    r = RET.registrar_emergencia(updates, inst, "3.6.1", "c0ffee", sandbox)
    assert [p["path"] for p in r["pendencias"]] == ["modulo.py"]
    (sandbox / "modulo.py").write_text("X = 2  # emergência\n", encoding="utf-8")
    assert RET.pendencias(updates, sandbox) == []
    assert RET.pendencias(updates) == []   # e a lista gravada já não a traz


def test_a_ferramenta_sai_1_quando_ha_mudanca_por_fora(tmp_path):
    import tools.conferir_instalacao as CI
    inst = _instalacao(tmp_path)
    dados = tmp_path / "dados"
    _aplicado(dados / "updates", inst)
    assert CI.main(["--instalacao", str(inst), "--dados", str(dados)]) == 0
    (inst / "modulo.py").write_text("X = 7\n", encoding="utf-8")
    assert CI.main(["--instalacao", str(inst), "--dados", str(dados)]) == 1
