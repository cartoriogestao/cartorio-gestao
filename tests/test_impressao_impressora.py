"""A IMPRESSORA GRAVADA DENTRO DO MOLDE CUSTAVA 48 SEGUNDOS POR PAPEL.

Relato #41 do oficial, em 02/09/2026: *«página de certidões quando clica em
imprimir pdf fica carregando muito tempo»*.

**Medido contra o molde real da certidão de nascimento:**

    molde como está (com a impressora)   50,6 s
    molde sem PrinterName/PrinterSetup    2,6 s
    o PDF que sai                        132.469 bytes nos DOIS

**Vinte vezes mais rápido, com o papel idêntico.**

O `settings.xml` de um `.odt` guarda a impressora de quem salvou o arquivo.
Ao abrir o documento, o LibreOffice pergunta as capacidades dela; quando ela
não está alcançável, **ele espera o tempo limite**. Por isso a demora era
CONSTANTE — não era trabalho, era espera.

**E ISSO EXPLICA O QUE FICOU ESCRITO COMO INEXPLICADO EM 01/09/2026.** O
`CLAUDE.md` registrava um tempo «errático» — 1 s de manhã, ~51 s à tarde, mais
de 10 minutos num perfil novo — e listava quatro suspeitas testadas e
refutadas. Nenhuma delas era olhar **dentro do arquivo**. A causa estava a um
`unzip` de distância.

**POR QUE ESTES TESTES NÃO CRONOMETRAM NADA:** teste que mede tempo depende da
máquina e do humor da rede, e um dia fica vermelho sem defeito nenhum. O que
eles guardam é **o fato que causa o tempo** — a impressora sair do arquivo
antes de o conversor o ver.
"""
from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import impressao_pdf as PDF

MOLDES = sorted((RAIZ / "modelos").glob("certidao_*_modelo.odt"))


def _odt(settings: str | None, extra: dict[str, bytes] | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("mimetype", "application/vnd.oasis.opendocument.text")
        z.writestr("content.xml", "<office/>")
        if settings is not None:
            z.writestr("settings.xml", settings)
        for nome, dados in (extra or {}).items():
            z.writestr(nome, dados)
    return buf.getvalue()


COM_IMPRESSORA = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<office:document-settings xmlns:office="urn:o" xmlns:config="urn:c">'
    '<config:config-item config:name="PrinterName" config:type="string">'
    'EPSON344007 (L4260 Series)</config:config-item>'
    '<config:config-item config:name="PrinterSetup" config:type="base64Binary">'
    'yAv+/0VQU09OMzQ0MDA3</config:config-item>'
    '<config:config-item config:name="PrinterIndependentLayout" '
    'config:type="string">high-resolution</config:config-item>'
    '</office:document-settings>')


# ------------------------------------------- o que a limpeza faz


def test_a_impressora_sai_do_arquivo():
    limpo = PDF.sem_a_impressora_de_quem_salvou(_odt(COM_IMPRESSORA))
    dentro = zipfile.ZipFile(io.BytesIO(limpo)).read("settings.xml").decode()
    assert "PrinterName" not in dentro
    assert "PrinterSetup" not in dentro
    assert "EPSON344007" not in dentro


def test_o_RESTO_do_settings_fica():
    """**Tira-se a impressora, e não o `settings.xml`.** Ele carrega o resto
    do que o oficial escolheu — e jogá-lo fora mudaria o papel."""
    limpo = PDF.sem_a_impressora_de_quem_salvou(_odt(COM_IMPRESSORA))
    dentro = zipfile.ZipFile(io.BytesIO(limpo)).read("settings.xml").decode()
    assert "PrinterIndependentLayout" in dentro
    assert "high-resolution" in dentro


def test_os_OUTROS_arquivos_do_odt_ficam_byte_a_byte():
    """O `.odt` é um zip com dez peças; a limpeza toca **uma**."""
    original = _odt(COM_IMPRESSORA,
                    {"styles.xml": b"<estilos/>",
                     "Pictures/qr.png": b"\x89PNG\r\n\x1a\n-fingido"})
    limpo = PDF.sem_a_impressora_de_quem_salvou(original)
    a = zipfile.ZipFile(io.BytesIO(original))
    b = zipfile.ZipFile(io.BytesIO(limpo))
    assert a.namelist() == b.namelist()
    for nome in a.namelist():
        if nome == "settings.xml":
            continue
        assert a.read(nome) == b.read(nome), f"«{nome}» mudou, e não devia"


def test_arquivo_sem_settings_volta_INTACTO():
    """Os papéis que a casa monta de HTML não têm `settings.xml` — e para eles
    a limpeza não pode nem reescrever o zip."""
    original = _odt(None)
    assert PDF.sem_a_impressora_de_quem_salvou(original) is original


def test_settings_SEM_impressora_volta_INTACTO():
    original = _odt('<office:document-settings xmlns:office="urn:o"/>')
    assert PDF.sem_a_impressora_de_quem_salvou(original) is original


def test_arquivo_que_nao_e_zip_volta_INTACTO():
    """**Quem decide o que fazer com arquivo torto é quem converte**, e não a
    limpeza: estourar aqui trocaria a frase de balcão por uma tela de erro."""
    torto = b"isto nao e um odt"
    assert PDF.sem_a_impressora_de_quem_salvou(torto) is torto


def test_arquivo_vazio_nao_estoura():
    assert PDF.sem_a_impressora_de_quem_salvou(b"") == b""


# ------------------------------------------- a ligação com a conversão


def test_o_conversor_recebe_o_arquivo_JA_LIMPO(monkeypatch, tmp_path):
    """**É esta a linha que vale 48 segundos.** Sem ela a limpeza existiria e
    ninguém a chamaria — o defeito que mais se repetiu neste projeto."""
    visto = {}

    def espiar(conversor, odt, saida, perfil):
        visto["bytes"] = Path(odt).read_bytes()
        alvo = Path(saida) / (Path(odt).stem + ".pdf")
        alvo.write_bytes(b"%PDF-1.7 fingido")
        return alvo.read_bytes()

    monkeypatch.setattr(PDF, "_tentar", espiar)
    monkeypatch.setattr(PDF, "onde_esta_o_conversor",
                        lambda *a, **k: Path("soffice-fingido"))
    PDF.pdf_de_odt(_odt(COM_IMPRESSORA), nome="ensaio")
    dentro = zipfile.ZipFile(io.BytesIO(visto["bytes"])).read(
        "settings.xml").decode()
    assert "PrinterName" not in dentro, (
        "o conversor recebeu o arquivo COM a impressora — são 48 segundos por "
        "papel, medidos")


# ------------------------------------------- o fato medido, guardado


@pytest.mark.skipif(not MOLDES, reason="os moldes só existem na instalação")
@pytest.mark.parametrize("molde", MOLDES, ids=lambda p: p.name)
def test_o_molde_REAL_carrega_a_impressora_de_quem_o_desenhou(molde):
    """**O fato que causou o relato #41, guardado onde ele se lê.**

    Os moldes do civil são desenhados à mão pelo oficial, no LibreOffice dele
    — e o LibreOffice grava a impressora dele dentro do arquivo. Isso **não é
    defeito do molde**: é o que aquele programa faz ao salvar, e vai voltar
    toda vez que ele ajustar o desenho.

    **É por isso que a limpeza mora na conversão, e não no arquivo.** Se um
    dia este teste ficar vermelho, quer dizer que alguém limpou os moldes em
    disco — o que é inofensivo, mas não substitui a limpeza: o próximo ajuste
    do oficial traz a impressora de volta.
    """
    dados = molde.read_bytes()
    with zipfile.ZipFile(io.BytesIO(dados)) as z:
        if "settings.xml" not in z.namelist():
            pytest.skip(f"{molde.name} não tem settings.xml")
        settings = z.read("settings.xml").decode("utf-8", "replace")
    assert "PrinterName" in settings, (
        f"{molde.name} deixou de carregar impressora. Se foi limpeza em "
        f"disco, tudo bem — mas a limpeza da conversão continua sendo o que "
        f"protege, porque o próximo «salvar» do oficial a traz de volta.")
    assert "PrinterName" not in PDF.sem_a_impressora_de_quem_salvou(
        dados).decode("latin-1", "replace")
