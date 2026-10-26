"""O leitor de digital da casa ligado à tela — 26/10/2026.

    Decisão do oficial: integrar o leitor HID DigitalPersona (padrão do
    e-Notariado) ao cadastro do cartão de autógrafo.

O QUE ESTES TESTES GUARDAM, SEM APARELHO NENHUM
    O leitor não está nesta máquina, e o teste não precisa dele: o que o SDK
    web do fabricante devolve à tela é uma imagem PNG, e a tela a manda pelo
    formulário marcado `origem=LEITOR`. **Simular o leitor é mandar esse
    formulário** — com o PNG que o SDK mandaria e o identificador do aparelho.

    - a imagem do leitor entra, com a origem e o aparelho gravados;
    - o que chega «do leitor» e não é PNG não veio do leitor, e se recusa;
    - o envio manual continua, marcado ARQUIVO;
    - a rota do SDK só serve os dois arquivos da lista, e nunca vira caminho;
    - a tela diz a finalidade (LGPD art. 11) e diz quando o SDK falta;
    - a auditoria leva o fato e nunca a imagem;
    - o JavaScript não escreve a digital no console nem no navegador.
"""
from __future__ import annotations

import base64
import re
import struct
import sys
import zlib
from io import BytesIO
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import cadastro_biometria as CB                                  # noqa: E402
import leitor_digital as LD                                      # noqa: E402
from bd_nativo import banco                                      # noqa: E402
from notas_partes import criar_cartao                            # noqa: E402

AGORA = "2026-10-26T10:00:00"
APARELHO = "{0A1B2C3D-0000-4000-8000-ABCDEF012345}"


def _png(marca: bytes) -> bytes:
    """PNG 1×1 com um texto único — o que o SDK entregaria, em miniatura."""
    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"tEXt", b"marca\x00" + marca)
            + chunk(b"IDAT", zlib.compress(b"\x00\x80"))
            + chunk(b"IEND", b""))


PNG_DO_LEITOR = _png(b"LEITOR-SIMULADO-DIGITAL")
JPEG = b"\xff\xd8\xff\xfe\x00\x06TESTE\xff\xd9"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _texto(r) -> str:
    return " ".join(r.get_data(as_text=True).split())


@pytest.fixture()
def casa(cg_casa_logada, tmp_path):
    db = cg_casa_logada["db"]
    with db.transaction() as con:
        cid = criar_cartao(con, {"nome": "BEATRIZ EXEMPLO",
                                 "documento": "00000001082"}, agora=AGORA)
    # A pasta do SDK vai para um lugar do teste, pela configuração — o app é
    # compartilhado entre testes, e a pasta de dados dele não se suja.
    sdk = tmp_path / "sdk_fabricante"
    db.set_settings({LD.CHAVE_DA_PASTA: str(sdk)})
    return {**cg_casa_logada, "cartao": int(cid), "sdk": sdk}


def _mandar(casa, dedo, dados, origem, dispositivo=""):
    """O que `static/leitor_digital.js` faz depois que o SDK devolve a imagem."""
    c = casa["c"]
    tela = c.get(f"/notas/cartoes/{casa['cartao']}").get_data(as_text=True)
    return c.post(
        f"/notas/cartoes/{casa['cartao']}/digital",
        data={"csrf_token": _token(tela), "dedo": str(dedo),
              "origem": origem, "dispositivo": dispositivo,
              "digital": (BytesIO(dados), f"digital_{dedo}.png")},
        content_type="multipart/form-data", follow_redirects=True)


def _linha(casa, dedo):
    with casa["db"].connect() as con:
        imgs = CB.imagens_do_cadastro(con, casa["cartao"])
    return next((dict(i) for i in imgs if i["especie"] == CB.ESPECIE_DIGITAL
                 and int(i["dedo"] or 0) == dedo), None)


# ============================================== o módulo, sem tela


def test_a_pasta_do_sdk_e_a_da_casa_e_a_configuracao_manda(tmp_path):
    assert LD.pasta_do_sdk("", tmp_path) == (
        tmp_path / "terceiros" / "digitalpersona")
    assert LD.pasta_do_sdk(str(tmp_path / "outra"), tmp_path) == (
        tmp_path / "outra")


def test_o_sdk_so_esta_instalado_com_os_DOIS_arquivos(tmp_path):
    e = LD.estado_do_sdk(tmp_path)
    assert not e["instalado"] and e["faltando"] == list(LD.ARQUIVOS_DO_SDK)
    (tmp_path / LD.ARQUIVOS_DO_SDK[0]).write_text("//", encoding="utf-8")
    e = LD.estado_do_sdk(tmp_path)
    assert not e["instalado"], "com metade da API a tela falharia no clique"
    (tmp_path / LD.ARQUIVOS_DO_SDK[1]).write_text("//", encoding="utf-8")
    assert LD.estado_do_sdk(tmp_path)["instalado"]


def test_o_nome_da_url_NUNCA_vira_caminho(tmp_path):
    (tmp_path / "segredo.txt").write_text("x", encoding="utf-8")
    for nome in ("segredo.txt", "../segredo.txt", "..\\segredo.txt",
                 "/etc/passwd", ""):
        assert LD.arquivo_do_sdk(tmp_path, nome) is None
    assert LD.arquivo_do_sdk(tmp_path, LD.ARQUIVOS_DO_SDK[0]) is None, (
        "arquivo da lista que não existe também é None")


def test_e_png():
    assert LD.e_png(PNG_DO_LEITOR)
    assert not LD.e_png(JPEG)
    assert not LD.e_png(b"")


# ============================================== o leitor, simulado


def test_A_DIGITAL_DO_LEITOR_entra_com_a_origem_e_o_aparelho(casa):
    r = _mandar(casa, 2, PNG_DO_LEITOR, LD.ORIGEM_LEITOR, APARELHO)
    assert r.status_code == 200
    assert "Digital do indicador direito colhida no leitor" in _texto(r)
    linha = _linha(casa, 2)
    assert linha["origem"] == LD.ORIGEM_LEITOR
    assert linha["dispositivo"] == APARELHO
    assert Path(linha["caminho"]).read_bytes() == PNG_DO_LEITOR
    # e a tela diz de onde veio
    html = _texto(casa["c"].get(f"/notas/cartoes/{casa['cartao']}"))
    assert "do leitor" in html


def test_o_que_chega_DO_LEITOR_e_nao_e_PNG_se_recusa(casa):
    r = _mandar(casa, 1, JPEG, LD.ORIGEM_LEITOR, APARELHO)
    assert r.status_code == 200
    assert "não chegou como imagem do leitor" in _texto(r)
    assert _linha(casa, 1) is None


def test_O_ENVIO_MANUAL_continua_como_reserva_e_fica_marcado(casa):
    r = _mandar(casa, 6, JPEG, LD.ORIGEM_ARQUIVO, APARELHO)
    assert "Digital do polegar esquerdo colhida." in _texto(r)
    linha = _linha(casa, 6)
    assert linha["origem"] == LD.ORIGEM_ARQUIVO
    assert linha["dispositivo"] is None, (
        "o aparelho só se grava quando a imagem veio dele")


def test_origem_desconhecida_e_erro_de_regra_e_nao_500(casa):
    r = _mandar(casa, 7, PNG_DO_LEITOR, "PENDRIVE")
    assert r.status_code == 200
    assert "Origem da digital desconhecida" in _texto(r)
    assert _linha(casa, 7) is None


def test_recolher_no_leitor_SUBSTITUI_a_de_arquivo(casa):
    _mandar(casa, 1, JPEG, LD.ORIGEM_ARQUIVO)
    _mandar(casa, 1, PNG_DO_LEITOR, LD.ORIGEM_LEITOR, APARELHO)
    with casa["db"].connect() as con:
        digitais = [i for i in CB.imagens_do_cadastro(con, casa["cartao"])
                    if i["especie"] == CB.ESPECIE_DIGITAL]
    assert len(digitais) == 1 and digitais[0]["origem"] == LD.ORIGEM_LEITOR


def test_A_AUDITORIA_LEVA_O_FATO_e_nunca_a_imagem(casa):
    _mandar(casa, 2, PNG_DO_LEITOR, LD.ORIGEM_LEITOR, APARELHO)
    with casa["db"].connect() as con:
        linhas = banco(con).ler(
            "SELECT * FROM audit_logs WHERE action=%s",
            ("NT_CADASTRO_DIGITAL",))
    assert linhas, "colher a digital tem de ficar na auditoria"
    tudo = " ".join(str(dict(x)) for x in linhas)
    assert "LEITOR" in tudo
    assert base64.b64encode(PNG_DO_LEITOR).decode()[:20] not in tudo
    assert "LEITOR-SIMULADO-DIGITAL" not in tudo


# ============================================== a tela


def test_A_TELA_DIZ_A_FINALIDADE_LGPD(casa):
    html = _texto(casa["c"].get(f"/notas/cartoes/{casa['cartao']}"))
    assert " ".join(LD.FINALIDADE.split()) in html
    assert "LGPD, art. 11" in html


def test_sem_o_SDK_a_tela_diz_o_que_falta_e_o_manual_continua(casa):
    html = _texto(casa["c"].get(f"/notas/cartoes/{casa['cartao']}"))
    assert "SDK web do fabricante não está instalado" in html
    for nome in LD.ARQUIVOS_DO_SDK:
        assert nome in html
    assert "/notas/leitor-digital/sdk/" not in html, (
        "sem os arquivos, a tela não carrega script que dá 404")
    assert 'data-leitor-colher' in html and "disabled" in html
    assert 'name="digital"' in html, "o envio manual é a reserva"


def test_com_o_SDK_a_tela_carrega_os_dois_e_a_rota_os_serve(casa):
    casa["sdk"].mkdir()
    for nome in LD.ARQUIVOS_DO_SDK:
        (casa["sdk"] / nome).write_text(f"/* {nome} */", encoding="utf-8")
    html = casa["c"].get(f"/notas/cartoes/{casa['cartao']}").get_data(
        as_text=True)
    posicoes = [html.index(f"/notas/leitor-digital/sdk/{n}")
                for n in LD.ARQUIVOS_DO_SDK]
    assert posicoes == sorted(posicoes), "o canal carrega antes da API"
    assert html.index("leitor_digital.js") > posicoes[-1]
    r = casa["c"].get(f"/notas/leitor-digital/sdk/{LD.ARQUIVOS_DO_SDK[1]}")
    assert r.status_code == 200
    assert r.mimetype == "application/javascript"
    assert LD.ARQUIVOS_DO_SDK[1] in r.get_data(as_text=True)


def test_a_rota_do_SDK_nao_serve_outro_arquivo(casa):
    casa["sdk"].mkdir()
    (casa["sdk"] / "outro.js").write_text("//", encoding="utf-8")
    assert casa["c"].get(
        "/notas/leitor-digital/sdk/outro.js").status_code == 404
    assert casa["c"].get(
        f"/notas/leitor-digital/sdk/{LD.ARQUIVOS_DO_SDK[0]}").status_code == 404


def test_o_formulario_do_leitor_vai_para_a_MESMA_rota_do_manual(casa):
    """Uma porta só para gravar: duas divergiriam no primeiro conserto."""
    html = casa["c"].get(f"/notas/cartoes/{casa['cartao']}").get_data(
        as_text=True)
    form = re.search(r"<form[^>]*data-leitor-form[^>]*>", html).group(0)
    assert f'action="/notas/cartoes/{casa["cartao"]}/digital"' in form
    assert f'value="{LD.ORIGEM_LEITOR}"' in html


# ============================================== o JavaScript


def test_o_JS_usa_a_API_do_SDK_e_pede_PNG():
    js = (RAIZ / "static" / "leitor_digital.js").read_text(encoding="utf-8")
    for peca in ("Fingerprint", "WebApi", "enumerateDevices",
                 "startAcquisition", "stopAcquisition", "onSamplesAcquired",
                 "onDeviceDisconnected", "onCommunicationFailed",
                 "PngImage", "data-leitor-form"):
        assert peca in js, peca


def test_o_JS_nao_escreve_a_digital_no_console_nem_no_navegador():
    """Dado sensível não vai para log — nem o do navegador."""
    js = (RAIZ / "static" / "leitor_digital.js").read_text(encoding="utf-8")
    codigo = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    codigo = re.sub(r"//[^\n]*", "", codigo)
    for proibido in ("console.", "localStorage", "sessionStorage",
                     "indexedDB"):
        assert proibido not in codigo, proibido


# ============================================== a documentação


def test_a_documentacao_registra_a_finalidade_e_a_proxima_etapa():
    doc = (RAIZ / "docs" / "tecnico" / "PROJETO_39_CADASTRO_CCN.md").read_text(
        encoding="utf-8")
    assert "LGPD" in doc and "art. 11" in doc
    assert "1:1" in doc and "ALERTA" in doc
    assert "leitor_digital.py" in doc
