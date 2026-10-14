from __future__ import annotations

import importlib.util
from pathlib import Path


RAIZ = Path(__file__).resolve().parent.parent


def _modulo():
    caminho = RAIZ / "tools" / "conferir_antes_de_atualizar.py"
    spec = importlib.util.spec_from_file_location("conferir_antes_medido", caminho)
    modulo = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(modulo)
    return modulo


def test_a_pre_conferencia_compila_todo_python_que_viaja():
    modulo = _modulo()
    relativos = {
        arquivo.relative_to(RAIZ).as_posix()
        for arquivo in modulo.modulos_do_pacote()
        if arquivo.is_relative_to(RAIZ)
    }
    assert "app.py" in relativos
    assert "tools/criar_atualizacao.py" in relativos
    assert "installer/carimbar_versao.py" in relativos
    assert not any(nome.startswith("tests/") for nome in relativos)


def test_a_pre_conferencia_reprova_qualquer_modulo_invalido(tmp_path):
    modulo = _modulo()
    bom = tmp_path / "bom.py"
    ruim = tmp_path / "ruim.py"
    bom.write_text("valor = 1\n", encoding="utf-8")
    ruim.write_text("def quebrado(:\n", encoding="utf-8")
    falhas = modulo.modulos_que_nao_compilam([bom, ruim])
    assert [nome for nome, _erro in falhas] == ["ruim.py"]


def test_a_impressao_muda_quando_um_arquivo_do_pacote_muda(monkeypatch, tmp_path):
    modulo = _modulo()
    fonte = tmp_path / "parte.py"
    fonte.write_text("valor = 1\n", encoding="utf-8")

    import criar_atualizacao
    monkeypatch.setattr(
        criar_atualizacao, "todos_os_arquivos",
        lambda _raiz: [(fonte, "parte.py")],
    )
    antes = modulo.impressao_do_pacote()
    fonte.write_text("valor = 2\n", encoding="utf-8")
    assert modulo.impressao_do_pacote() != antes


def test_a_pre_conferencia_recusa_versao_que_o_app_nao_responde(
    monkeypatch, tmp_path,
):
    modulo = _modulo()
    (tmp_path / "VERSAO.txt").write_text("3.6.150\n", encoding="utf-8")
    (tmp_path / "app.py").write_text(
        'VERSION = "3.6.149"\n', encoding="utf-8")
    monkeypatch.setattr(modulo, "RAIZ", tmp_path)
    assert "3.6.150" in modulo.inconsistencia_de_versao()
    assert "3.6.149" in modulo.inconsistencia_de_versao()


def test_a_pre_conferencia_aceita_os_dois_carimbos_iguais(
    monkeypatch, tmp_path,
):
    modulo = _modulo()
    (tmp_path / "VERSAO.txt").write_text("3.6.150\n", encoding="utf-8")
    (tmp_path / "app.py").write_text(
        'VERSION = "3.6.150"\n', encoding="utf-8")
    monkeypatch.setattr(modulo, "RAIZ", tmp_path)
    assert modulo.inconsistencia_de_versao() is None
