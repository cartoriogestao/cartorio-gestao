"""A assinatura e os hashes são reconferidos contra o `.cgu` ao inspecionar e
ao aprovar — revisão de segurança da 3.7.0, 22/10/2026, achado C1.

O QUE A REVISÃO MEDIU: a assinatura Ed25519 do manifesto era conferida UMA
vez, no upload (`validate_and_stage`), e o resultado ia para o
`_update_meta.json` da preparação. Dali em diante a tela lia «ASSINADO» do
meta, a aprovação conferia os hashes do payload contra o meta, e o
`aplicar_atualizacao.ps1` copiava a pasta preparada inteira (`robocopy /E`).
Numa pasta em que se pode escrever — e `updates/staged` era gravável por
Usuários até o endurecimento do mesmo dia —, trocar um `.py` e reescrever o
hash no meta bastava.

O CONSERTO (`update_manager.reconferir_contra_o_pacote`): a inspeção e a
aprovação reabrem o pacote original, conferem a assinatura contra as chaves
DE HOJE e comparam cada arquivo preparado ao hash do MANIFESTO ASSINADO —
inclusive recusando arquivo a mais no payload. Estes testes forjam cada um
dos ataques e exigem a recusa; e provam que o pacote honesto continua
passando.
"""
from __future__ import annotations

import base64
import hashlib
import json
import sys
import zipfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

ed25519 = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.ed25519")

import assinatura_da_atualizacao as ASS   # noqa: E402
import update_manager as UM               # noqa: E402

VERSAO = "3.6.2"


def _par():
    privada = ed25519.Ed25519PrivateKey.generate()
    crua = ASS.publica_crua(privada)
    return privada, {ASS.id_da_chave(crua): base64.b64encode(crua).decode()}


def _pacote(caminho: Path, *, privada=None) -> Path:
    arquivos = {
        "app.py": f'VERSION = "{VERSAO}"\n'.encode(),
        "VERSAO.txt": VERSAO.encode(),
    }
    manifesto = {"product": "CartorioGestao", "format": 1, "version": VERSAO,
                 "min_version": "0", "notes": "", "run_pip": False,
                 "files": [{"path": nome,
                            "sha256": hashlib.sha256(dados).hexdigest()}
                           for nome, dados in arquivos.items()],
                 "delete": []}
    m = json.dumps(manifesto, indent=2).encode()
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr("update_manifest.json", m)
        if privada is not None:
            z.writestr(ASS.NOME_NO_PACOTE, json.dumps(ASS.assinar(m, privada)))
        for nome, dados in arquivos.items():
            z.writestr(f"payload/{nome}", dados)
    return caminho


def _instalacao(tmp_path: Path) -> Path:
    pasta = tmp_path / "instalada"
    pasta.mkdir()
    (pasta / "app.py").write_text('VERSION = "3.6.1"\n', encoding="utf-8")
    (pasta / "VERSAO.txt").write_text("3.6.1", encoding="utf-8")
    return pasta


def _preparar(tmp_path: Path, monkeypatch, *, assinado=True):
    privada, chaves = _par()
    monkeypatch.setattr(ASS, "CHAVES_CONFIAVEIS", chaves if assinado else {})
    pacote = _pacote(tmp_path / "p.cgu", privada=privada if assinado else None)
    UM.validate_and_stage(pacote, tmp_path / "stage", "3.6.1")
    stage = tmp_path / "stage" / VERSAO
    return stage, chaves


def _meta(stage: Path) -> dict:
    return json.loads((stage / "_update_meta.json").read_text(encoding="utf-8"))


def _gravar_meta(stage: Path, meta: dict) -> None:
    (stage / "_update_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def _pronta_para_aprovacao(stage: Path) -> dict:
    """O meta como fica depois da inspeção — sem rodar a inspeção, de
    propósito: é o estado que um atacante escreveria à mão."""
    meta = _meta(stage)
    meta["state"] = "READY_FOR_APPROVAL"
    meta["inspection"] = {"ok": True, "executed_code": False}
    _gravar_meta(stage, meta)
    return meta


# ------------------------------------------------- o honesto continua passando

def test_o_pacote_honesto_inspeciona_e_aprova_com_a_assinatura_conferida_agora(
        tmp_path, monkeypatch):
    stage, _ = _preparar(tmp_path, monkeypatch)
    inspecao = UM.inspect_staged(stage, _instalacao(tmp_path))
    assert inspecao["ok"], inspecao["problems"]
    assert inspecao["assinatura"]["situacao"] == "ASSINADO"
    meta = UM.revalidate_staged(stage)
    assert meta["assinatura"]["situacao"] == "ASSINADO"


# ------------------------------------------------------------ os quatro ataques

def test_arquivo_trocado_no_payload_com_o_hash_reescrito_no_meta_e_recusado(
        tmp_path, monkeypatch):
    """O ataque que o meta sozinho não pegava: o payload E o meta mudam
    juntos. O hash que vale é o do manifesto assinado dentro do pacote."""
    stage, _ = _preparar(tmp_path, monkeypatch)
    meta = _pronta_para_aprovacao(stage)
    plantado = b'VERSION = "3.6.2"\nimport os; os.system("x")\n'
    (stage / "payload" / "app.py").write_bytes(plantado)
    for item in meta["checked_files"]:
        if item["path"] == "app.py":
            item["sha256"] = hashlib.sha256(plantado).hexdigest()
    _gravar_meta(stage, meta)
    with pytest.raises(UM.UpdateError, match="alterada depois da conferencia"):
        UM.revalidate_staged(stage)


def test_arquivo_a_mais_no_payload_e_recusado_mesmo_sem_tocar_no_meta(
        tmp_path, monkeypatch):
    """`robocopy /E` copiaria o que estivesse na pasta; um `.pth` plantado
    rodaria como SYSTEM na subida seguinte."""
    stage, _ = _preparar(tmp_path, monkeypatch)
    _pronta_para_aprovacao(stage)
    (stage / "payload" / "sitecustomize.pth").write_text(
        "import os\n", encoding="utf-8")
    with pytest.raises(UM.UpdateError, match="nao declara"):
        UM.revalidate_staged(stage)


def test_a_assinatura_e_conferida_de_novo_contra_as_chaves_de_hoje(
        tmp_path, monkeypatch):
    """O meta diz «ASSINADO»; a chave que assinou deixou de ser confiável. A
    aprovação tem de perguntar ao pacote, e não ao meta."""
    stage, _ = _preparar(tmp_path, monkeypatch)
    _pronta_para_aprovacao(stage)
    outra, chaves_de_outro = _par()
    monkeypatch.setattr(ASS, "CHAVES_CONFIAVEIS", chaves_de_outro)
    with pytest.raises(UM.UpdateError, match="não reconhece"):
        UM.revalidate_staged(stage)


def test_a_palavra_assinado_escrita_no_meta_nao_engana_a_tela(
        tmp_path, monkeypatch):
    """Pacote da transição (sem chave, sem assinatura) com o meta forjado
    dizendo ASSINADO: a inspeção mostra o que conferiu agora."""
    stage, _ = _preparar(tmp_path, monkeypatch, assinado=False)
    meta = _meta(stage)
    meta["assinatura"] = {"situacao": "ASSINADO", "chave": "forjada"}
    _gravar_meta(stage, meta)
    inspecao = UM.inspect_staged(stage, _instalacao(tmp_path))
    assert inspecao["assinatura"]["situacao"] == "NAO_ASSINADO"
    assert _meta(stage)["assinatura"]["situacao"] == "NAO_ASSINADO"


def test_a_inspecao_recusa_quando_o_pacote_nao_confere(tmp_path, monkeypatch):
    stage, _ = _preparar(tmp_path, monkeypatch)
    (stage / "payload" / "extra.py").write_text("", encoding="utf-8")
    inspecao = UM.inspect_staged(stage, _instalacao(tmp_path))
    assert not inspecao["ok"]
    assert any("nao declara" in p for p in inspecao["problems"])
    assert inspecao["assinatura"]["situacao"] == "NAO_CONFERIDA"
    assert _meta(stage)["state"] == "REJECTED"


# ------------------------------------------------------------------- o ps1

def test_o_ps1_recusa_arquivo_que_o_manifesto_nao_declara():
    """A última porta: o `ps1` roda depois da aprovação e copiava a pasta
    inteira. Ele passa a varrer o payload e recusar o que não está em
    `checked_files` — antes de parar o serviço."""
    texto = (RAIZ / "installer" / "aplicar_atualizacao.ps1").read_text(
        encoding="utf-8")
    varredura = texto.find("Get-ChildItem -LiteralPath $payload -File -Recurse")
    parar = texto.find("ReiniciarServico 'Parar'")
    assert varredura > -1, "o ps1 nao varre o payload"
    assert "arquivo que o manifesto nao declara" in texto
    assert varredura < parar, "a varredura tem de vir antes de parar o servico"
