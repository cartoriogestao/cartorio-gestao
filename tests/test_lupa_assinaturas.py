"""
A lupa das assinaturas — o que ela precisa entregar para servir no balcão.

O QUE ACONTECIA
    A assinatura do cartão de autógrafo aparecia numa miniatura de 200 pixels,
    parada, sem clique. Reconhecimento por semelhança é o tabelião confrontando
    o traço com o cartão: a inclinação, o ponto onde a caneta levanta, o laço do
    sobrenome. Nada disso cabe em 200 pixels.

    E havia o defeito calado por baixo: a rota rotulava `.jpg` como
    `image/jpeg` e TODO O RESTO como `image/png`. Das 3.637 assinaturas do
    acervo, 3.635 são JPG — as outras duas são uma GIF e um PDF, e as duas
    saíam mentindo o tipo. Dois arquivos em três mil e seiscentos não parece
    muito até ser o cartão da pessoa que está no balcão.

O QUE ESTES TESTES PROTEGEM
    Que a imagem chegue à tela no formato que o navegador desenha, que dê para
    pedir uma versão menor sem trazer a original inteira, que o original
    continue disponível para baixar, e que UMA assinatura ruim não derrube a
    tela das outras vinte.
"""
from __future__ import annotations

import glob
import io
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

AGORA = "2026-08-17 09:00:00"


def assinatura(caminho: Path, texto: str, formato: str, tam=(900, 320)) -> None:
    """Uma assinatura digitalizada de mentira, mas do tamanho das de verdade."""
    from PIL import Image, ImageDraw
    im = Image.new("RGB", tam, "white")
    d = ImageDraw.Draw(im)
    d.text((40, 130), texto, fill="black")
    d.line([(40, 200), (300, 150), (520, 230), (820, 160)], fill="black", width=4)
    im.save(caminho, format=formato)


@pytest.fixture()
def serventia(tmp_path):
    """Sistema de pé, com um cartão de três vias: duas JPG e uma TIFF.

    A TIFF está aqui de propósito. Não aparece nas firmas do E-Ofício hoje, mas
    é o que sai de digitalizador de balcão quando ninguém troca a configuração —
    e é exatamente o formato que navegador nenhum exibe.
    """
    pytest.importorskip("PIL", reason="a conversão de formato depende do Pillow")
    from app import create_app
    from database import Database

    dados = tmp_path / "dados"
    dados.mkdir()
    firmas = dados / "arquivos" / "eoficio" / "Firmas"
    firmas.mkdir(parents=True)
    assinatura(firmas / "RF210703-1.JPG", "Maria da Silva - via 1", "JPEG")
    assinatura(firmas / "RF210703-2.JPG", "Maria da Silva - via 2", "JPEG")
    assinatura(firmas / "RF210703-3.TIF", "Maria da Silva - via 3", "TIFF")

    app = create_app({"DATA_DIR": str(dados)})
    banco = Path(glob.glob(f"{dados}/*.sqlite3")[0])
    d = Database(banco)
    d.create_user("prova", "Operador de Prova", "Senha#12345", "ADMIN")
    d.set_settings({"archive_root": str(dados / "arquivos")})

    con = sqlite3.connect(banco)
    con.execute(
        """INSERT INTO nt_cartoes (nome, nome_norm, documento, origem, ativo,
                                   abertura, criado_em)
           VALUES ('MARIA DA SILVA','MARIA DA SILVA','52998224725','EOFICIO',1,
                   '2019-04-02',?)""", (AGORA,))
    cartao = con.execute(
        "SELECT id FROM nt_cartoes WHERE nome='MARIA DA SILVA'").fetchone()[0]
    for ordem, nome in enumerate(
            ["RF210703-1.JPG", "RF210703-2.JPG", "RF210703-3.TIF"], 1):
        con.execute(
            """INSERT INTO nt_cartao_imagens (cartao_id, ordem, nome_arquivo,
                                              caminho, favorita, criado_em)
               VALUES (?,?,?,?,?,?)""",
            (cartao, ordem, nome, str(firmas), 1 if ordem == 1 else 0, AGORA))
    con.commit()
    imagens = [r[0] for r in con.execute(
        "SELECT id FROM nt_cartao_imagens ORDER BY ordem")]
    con.close()

    c = app.test_client()
    pagina = c.get("/login").get_data(as_text=True)
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', pagina).group(1)
    c.post("/login", data={"username": "prova", "password": "Senha#12345",
                           "csrf_token": token}, follow_redirects=True)
    return {"cliente": c, "cartao": cartao, "imagens": imagens, "firmas": firmas}


# ------------------------------------------------------------------ formatos

def test_jpg_sai_como_jpeg_e_intacto(serventia):
    """Sem `w`, o arquivo vai como está: não há por que reprocessá-lo."""
    r = serventia["cliente"].get(f"/notas/cartoes/imagem/{serventia['imagens'][0]}")
    assert r.status_code == 200
    assert r.mimetype == "image/jpeg"


def test_tiff_chega_na_tela_convertido(serventia):
    """O formato que o navegador não desenha é o que mais precisa de conversão.

    Antes ele saía rotulado `image/png` sendo TIFF — o rótulo mentia e a tela
    mostrava o quadrado quebrado.
    """
    r = serventia["cliente"].get(f"/notas/cartoes/imagem/{serventia['imagens'][2]}")
    assert r.status_code == 200
    assert r.mimetype == "image/png"
    from PIL import Image
    assert Image.open(io.BytesIO(r.data)).width == 900          # abre de verdade


def test_a_miniatura_pedida_e_a_miniatura_entregue(serventia):
    """`?w=` existe para a lista do balcão não baixar trinta imagens inteiras
    para desenhar cada uma em 44 pixels de altura."""
    r = serventia["cliente"].get(
        f"/notas/cartoes/imagem/{serventia['imagens'][0]}?w=280")
    from PIL import Image
    assert Image.open(io.BytesIO(r.data)).width == 280


def test_pedir_maior_que_o_original_nao_inventa_pixel(serventia):
    """Ampliar no servidor não acrescenta traço nenhum. Quem amplia é a lupa."""
    r = serventia["cliente"].get(
        f"/notas/cartoes/imagem/{serventia['imagens'][0]}?w=4000")
    from PIL import Image
    assert Image.open(io.BytesIO(r.data)).width == 900


# ------------------------------------------------------------------- original

def test_baixar_original_vem_como_anexo_e_com_o_nome_certo(serventia):
    r = serventia["cliente"].get(
        f"/notas/cartoes/imagem/{serventia['imagens'][0]}/original")
    assert r.status_code == 200
    assert 'attachment; filename="RF210703-1.JPG"' in r.headers["Content-Disposition"]


def test_arquivo_sem_extensao_ganha_tif_ao_baixar(serventia, tmp_path):
    """A lição das fichas do RI, repetida aqui antes de custar de novo.

    Arquivo entregue sem extensão o Windows não associa a visualizador nenhum,
    e o operador vê "baixou um arquivo que não abre".
    """
    from PIL import Image
    caminho = serventia["firmas"] / "00002576.0001"
    Image.new("RGB", (100, 40), "white").save(caminho, format="TIFF")
    c = serventia["cliente"]
    con = sqlite3.connect(glob.glob(str(caminho.parents[2].parent / "*.sqlite3"))[0])
    con.execute("""INSERT INTO nt_cartao_imagens (cartao_id, ordem, nome_arquivo,
                                                  caminho, favorita, criado_em)
                   VALUES (?,?,?,?,0,?)""",
                (serventia["cartao"], 9, "00002576.0001",
                 str(serventia["firmas"]), AGORA))
    con.commit()
    novo = con.execute("SELECT id FROM nt_cartao_imagens WHERE ordem=9").fetchone()[0]
    con.close()
    r = c.get(f"/notas/cartoes/imagem/{novo}/original")
    assert '00002576.0001.tif' in r.headers["Content-Disposition"]


# ------------------------------------------------------------- não derrubar

def test_imagem_que_nao_existe_da_404_e_nao_500(serventia):
    """Uma assinatura ruim não pode levar junto as outras vinte da mesma tela."""
    assert serventia["cliente"].get("/notas/cartoes/imagem/99999").status_code == 404


def test_arquivo_corrompido_vira_download_em_vez_de_erro(serventia, tmp_path):
    quebrado = serventia["firmas"] / "RF999999-1.TIF"
    quebrado.write_bytes(b"isto nao e um TIFF")
    banco = glob.glob(str(serventia["firmas"].parents[2] / "*.sqlite3"))[0]
    con = sqlite3.connect(banco)
    con.execute("""INSERT INTO nt_cartao_imagens (cartao_id, ordem, nome_arquivo,
                                                  caminho, favorita, criado_em)
                   VALUES (?,?,?,?,0,?)""",
                (serventia["cartao"], 8, "RF999999-1.TIF",
                 str(serventia["firmas"]), AGORA))
    con.commit()
    ruim = con.execute("SELECT id FROM nt_cartao_imagens WHERE ordem=8").fetchone()[0]
    con.close()
    r = serventia["cliente"].get(f"/notas/cartoes/imagem/{ruim}")
    assert r.status_code == 200                       # e não 500
    assert r.headers.get("X-Assinatura-Motivo") == "conversao-falhou"


# ------------------------------------------------------------------- na tela

def test_a_tela_do_cartao_marca_as_assinaturas_como_ampliaveis(serventia):
    r = serventia["cliente"].get(f"/notas/cartoes/{serventia['cartao']}")
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert html.count('class="ampliavel"') == 3
    # O grupo é o que liga as vias da mesma pessoa: dele saem as setas e o
    # botão de comparar duas lado a lado.
    assert f'data-lupa-grupo="cartao-{serventia["cartao"]}"' in html
    assert "/original" in html


def test_o_balcao_do_reconhecimento_tambem_amplia(serventia):
    """É a tela onde a conferência de fato acontece, com a pessoa na frente."""
    html = serventia["cliente"].get(
        "/notas/reconhecimento?busca=MARIA").get_data(as_text=True)
    assert 'class="ampliavel"' in html


def test_a_lupa_e_servida_em_toda_tela(serventia):
    c = serventia["cliente"]
    assert "lupa.js" in c.get(f"/notas/cartoes/{serventia['cartao']}").get_data(as_text=True)
    assert c.get("/static/lupa.js").status_code == 200
    assert b".lupa-palco" in c.get("/static/app.css").data
