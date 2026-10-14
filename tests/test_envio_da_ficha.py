"""
Enviar a ficha de firma digitalizada — o cartão novo precisa nascer com autógrafo.

O QUE FALTAVA
    As 3.637 assinaturas do acervo vieram do E-Ofício. Para as firmas NOVAS não
    havia botão nenhum: a ficha era assinada no balcão, digitalizada, e não
    tinha por onde entrar no sistema. Cartão de autógrafo sem autógrafo não
    reconhece nada por semelhança, que é o motivo de o cartão existir.

O QUE ESTES TESTES PROTEGEM
    Que o arquivo entre e fique guardado DENTRO DO ACERVO — a pasta que o
    backup já varre. Digitalização que não entra no backup é digitalização que
    se perde na primeira troca de disco.

    Que a mesma ficha enviada duas vezes não vire duas linhas, e que a
    conferência seja pelo CONTEÚDO: `digitalizar001.jpg` é o nome que todo
    scanner dá.

    Que um arquivo ruim no meio de três não derrube os outros dois.

    E que a imagem enviada apareça como disponível na tela — este era o erro
    mais fácil de cometer, porque a tela procurava só nas pastas do E-Ofício.
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


def imagem(largura=900, altura=320, formato="JPEG", cor="white") -> bytes:
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (largura, altura), cor)
    d = ImageDraw.Draw(im)
    d.line([(40, 200), (300, 150), (520, 230), (820, 160)], fill="black", width=4)
    buf = io.BytesIO()
    im.save(buf, format=formato)
    return buf.getvalue()


@pytest.fixture()
def serventia(cg_casa):
    pytest.importorskip("PIL")
    app = cg_casa['app']
    banco = cg_casa['banco']
    dados = cg_casa['dados']
    d = cg_casa['db']
    d.create_user("balcao", "LAURA MARIA DA COSTA", "Senha#12345", "ADMIN")
    d.set_settings({"archive_root": str(dados / "arquivos")})

    con = sqlite3.connect(banco)
    con.execute(
        """INSERT INTO nt_cartoes (nome, nome_norm, documento, origem, ativo,
                                   abertura, criado_em)
           VALUES ('MARIA DA SILVA','MARIA DA SILVA','52998224725','MANUAL',1,
                   '2026-08-17',?)""", (AGORA,))
    con.commit()
    cartao = con.execute("SELECT id FROM nt_cartoes").fetchone()[0]
    con.execute(
        """INSERT OR REPLACE INTO cx_servicos (codigo, codigo_tj, descricao)
           VALUES (412, '13.17.1', 'Abertura de cartão de autógrafo')""")
    con.commit()
    con.close()

    c = app.test_client()
    pega = lambda html: re.search(r'name="csrf_token"[^>]*value="([^"]+)"',
                                  html).group(1)
    c.post("/login", data={"username": "balcao", "password": "Senha#12345",
                           "csrf_token": pega(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    # O token é rotacionado no login. Pegar o de antes dava 400 em tudo — e é
    # exatamente o que aconteceria no navegador de quem deixa a aba aberta.
    token = pega(c.get(f"/notas/cartoes/{cartao}").get_data(as_text=True))
    bancada = {"app": app, "cliente": c, "cartao": cartao, "banco": banco,
               "acervo": dados / "arquivos", "token": token,
               "db": d, "dados": dados}
    from selador_de_bancada import ligar_o_selador
    with ligar_o_selador(bancada):
        yield bancada


def enviar(s, arquivos, **campos):
    """`arquivos` é lista de (nome, bytes)."""
    dados = {"csrf_token": s["token"]}
    dados.update(campos)
    dados["ficha"] = [(io.BytesIO(b), n) for n, b in arquivos]
    return s["cliente"].post(f"/notas/cartoes/{s['cartao']}/fichas",
                             data=dados, content_type="multipart/form-data",
                             follow_redirects=True)


def linhas(s):
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    r = list(con.execute("SELECT * FROM nt_cartao_imagens WHERE cartao_id=? "
                         "ORDER BY ordem", (s["cartao"],)))
    con.close()
    return r


# --------------------------------------------------------------- o caminho

def test_a_ficha_entra_e_fica_dentro_do_acervo(serventia):
    enviar(serventia, [("ficha.jpg", imagem())])
    r = linhas(serventia)
    assert len(r) == 1
    # DENTRO DO ACERVO: é a pasta que o backup varre.
    guardado = serventia["acervo"] / r[0]["caminho_interno"]
    assert guardado.is_file()
    assert "notas" in r[0]["caminho_interno"] and "firmas" in r[0]["caminho_interno"]
    assert r[0]["sha256"] and r[0]["bytes"] > 0


def test_a_primeira_ficha_vira_a_favorita_sozinha(serventia):
    """É a que aparece nas listas e no balcão. Ninguém deveria escolher o óbvio."""
    enviar(serventia, [("ficha.jpg", imagem())])
    assert linhas(serventia)[0]["favorita"] == 1


def test_a_data_da_coleta_e_gravada(serventia):
    """Quando a via foi assinada — que é outra coisa que quando foi digitalizada."""
    enviar(serventia, [("ficha.jpg", imagem())], data_coleta="2026-08-14")
    assert linhas(serventia)[0]["data"] == "2026-08-14"


def test_tres_vias_entram_com_ordem_propria(serventia):
    enviar(serventia, [("a.jpg", imagem(cor="white")),
                       ("b.jpg", imagem(cor="#fefefe")),
                       ("c.png", imagem(cor="#fdfdfd", formato="PNG"))])
    r = linhas(serventia)
    assert len(r) == 3
    assert [x["ordem"] for x in r] == [1, 2, 3]
    assert sum(x["favorita"] for x in r) == 1        # uma só


# ------------------------------------------------------------- o que recusa

def test_a_mesma_ficha_duas_vezes_nao_duplica(serventia):
    """Pelo CONTEÚDO, e não pelo nome: `digitalizar001.jpg` é o nome que todo
    scanner dá. Conferir pelo nome deixaria passar a mesma ficha duas vezes e
    recusaria duas fichas diferentes — errado dos dois lados."""
    mesma = imagem()
    enviar(serventia, [("digitalizar001.jpg", mesma)])
    r = enviar(serventia, [("outro-nome-totalmente-diferente.jpg", mesma)])
    assert len(linhas(serventia)) == 1
    assert "já está neste cartão" in r.get_data(as_text=True)


def test_tipo_nao_aceito_e_recusado_com_recado_util(serventia):
    r = enviar(serventia, [("contrato.docx", b"PK\x03\x04qualquercoisa")])
    assert len(linhas(serventia)) == 0
    assert "JPG, PNG ou PDF" in r.get_data(as_text=True)


def test_arquivo_grande_demais_e_recusado(serventia):
    r = enviar(serventia, [("enorme.jpg", b"\xff\xd8" + b"x" * (26 * 1024 * 1024))])
    assert len(linhas(serventia)) == 0
    assert "grande demais" in r.get_data(as_text=True)


def test_um_arquivo_ruim_nao_derruba_os_bons(serventia):
    """Quem envia as três vias de uma vez e erra numa precisa que as duas boas
    entrem, e que a recusa diga qual foi."""
    r = enviar(serventia, [("boa1.jpg", imagem(cor="white")),
                           ("ruim.docx", b"PK\x03\x04"),
                           ("boa2.jpg", imagem(cor="#fefefe"))])
    assert len(linhas(serventia)) == 2
    texto = r.get_data(as_text=True)
    assert "ruim.docx" in texto


def test_sem_arquivo_nenhum_avisa_em_vez_de_quebrar(serventia):
    r = serventia["cliente"].post(
        f"/notas/cartoes/{serventia['cartao']}/fichas",
        data={"csrf_token": serventia["token"]},
        content_type="multipart/form-data", follow_redirects=True)
    assert r.status_code == 200
    assert "Nenhum arquivo" in r.get_data(as_text=True)


# ------------------------------------------------------------------- na tela

def test_a_ficha_enviada_aparece_como_disponivel(serventia):
    """O erro mais fácil de cometer aqui.

    A tela conferia a existência varrendo só as pastas do E-Ofício. A ficha
    enviada mora em `notas\\firmas\\<cartão>`, que não está nessa lista: seria
    gravada, apareceria no banco, a rota da imagem a serviria sem problema — e
    a tela diria "não foi encontrada nesta máquina".
    """
    enviar(serventia, [("ficha.jpg", imagem())])
    html = serventia["cliente"].get(
        f"/notas/cartoes/{serventia['cartao']}").get_data(as_text=True)
    assert "não foi encontrada nesta máquina" not in html
    assert 'class="ampliavel"' in html                 # e abre na lupa


def test_a_imagem_enviada_e_servida_de_verdade(serventia):
    enviar(serventia, [("ficha.jpg", imagem())])
    ident = linhas(serventia)[0]["id"]
    r = serventia["cliente"].get(f"/notas/cartoes/imagem/{ident}")
    assert r.status_code == 200
    assert r.mimetype == "image/jpeg"


# ------------------------------------------------------------------ gerir

def test_trocar_a_favorita(serventia):
    enviar(serventia, [("a.jpg", imagem(cor="white")),
                       ("b.jpg", imagem(cor="#fefefe"))])
    segunda = linhas(serventia)[1]["id"]
    serventia["cliente"].post(f"/notas/cartoes/imagem/{segunda}/gerir",
                              data={"csrf_token": serventia["token"],
                                    "acao": "favorita"}, follow_redirects=True)
    r = {x["id"]: x["favorita"] for x in linhas(serventia)}
    assert r[segunda] == 1 and sum(r.values()) == 1


def test_remover_tira_da_tela_mas_guarda_o_arquivo(serventia):
    """Ficha de firma é peça de conferência de ato notarial. Errar o cartão ao
    enviar tem de ter conserto; apagar do disco a digitalização de uma
    assinatura não tem conserto nenhum."""
    enviar(serventia, [("ficha.jpg", imagem())])
    linha = linhas(serventia)[0]
    guardado = serventia["acervo"] / linha["caminho_interno"]
    serventia["cliente"].post(f"/notas/cartoes/imagem/{linha['id']}/gerir",
                              data={"csrf_token": serventia["token"],
                                    "acao": "remover"}, follow_redirects=True)
    assert len(linhas(serventia)) == 0
    assert guardado.is_file(), "o arquivo não podia ter sido apagado do acervo"


def test_removida_a_favorita_a_proxima_assume(serventia):
    """Senão o cartão fica com imagens e nenhuma aparecendo no balcão."""
    enviar(serventia, [("a.jpg", imagem(cor="white")),
                       ("b.jpg", imagem(cor="#fefefe"))])
    primeira = linhas(serventia)[0]
    serventia["cliente"].post(f"/notas/cartoes/imagem/{primeira['id']}/gerir",
                              data={"csrf_token": serventia["token"],
                                    "acao": "remover"}, follow_redirects=True)
    resto = linhas(serventia)
    assert len(resto) == 1 and resto[0]["favorita"] == 1


def test_anotar_a_data_depois(serventia):
    enviar(serventia, [("ficha.jpg", imagem())])
    ident = linhas(serventia)[0]["id"]
    serventia["cliente"].post(f"/notas/cartoes/imagem/{ident}/gerir",
                              data={"csrf_token": serventia["token"], "acao": "data",
                                    "data_coleta": "2026-07-02"},
                              follow_redirects=True)
    assert linhas(serventia)[0]["data"] == "2026-07-02"


# --------------------------------------------------------------- cartão novo

def test_abrir_cartao_ja_com_a_ficha_e_um_gesto_so(serventia):
    """No balcão a pessoa está ali, a ficha acabou de ser assinada. Separar em
    duas telas é o tipo de passo que se esquece."""
    r = serventia["cliente"].post(
        "/notas/cartoes",
        data={"csrf_token": serventia["token"], "acao": "novo",
              "nome": "PEDRO ALVES DE SOUZA", "documento": "11144477735",
              "ficha": (io.BytesIO(imagem(cor="#fcfcfc")), "ficha-pedro.jpg")},
        content_type="multipart/form-data", follow_redirects=True)
    texto = r.get_data(as_text=True)
    assert "aberto para PEDRO ALVES DE SOUZA" in texto

    con = sqlite3.connect(serventia["banco"])
    con.row_factory = sqlite3.Row
    novo = con.execute("SELECT id FROM nt_cartoes WHERE nome='PEDRO ALVES DE SOUZA'"
                       ).fetchone()["id"]
    imgs = list(con.execute("SELECT * FROM nt_cartao_imagens WHERE cartao_id=?",
                            (novo,)))
    con.close()
    assert len(imgs) == 1 and imgs[0]["favorita"] == 1


# ------------------------------------------------------------------- o PDF

def test_pdf_e_aceito_e_vira_imagem_quando_da(serventia):
    """Convertido, comporta-se como as outras e a lupa funciona igual. Sem o
    pypdfium2 instalado, é guardado como veio e a tela diz o que instalar — o
    envio não pode parar por causa de uma biblioteca."""
    pypdfium2 = pytest.importorskip("pypdfium2", reason="conversão de PDF é opcional")
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (900, 320), "white").save(buf, format="PDF")
    r = enviar(serventia, [("ficha.pdf", buf.getvalue())])
    assert r.status_code == 200
    guardadas = linhas(serventia)
    assert len(guardadas) == 1
    assert guardadas[0]["nome_arquivo"].endswith(".png")     # virou imagem


def test_frente_e_verso_no_mesmo_envio(serventia):
    """O caso que motivou a fila: as duas faces do cartão de uma vez.

    A primeira versão da tela aceitava vários arquivos mas só sabia trabalhar
    com um: editar qualquer um fazia os outros sumirem no envio, sem erro e sem
    aviso. Do lado do servidor a regra sempre foi a mesma — todos os `ficha`
    entram — e este teste é o que garante que ela continua valendo.
    """
    r = enviar(serventia, [("frente.jpg", imagem(cor="white")),
                           ("verso.jpg", imagem(cor="#fdfdfd"))])
    guardadas = linhas(serventia)
    assert len(guardadas) == 2, "o segundo arquivo se perdeu"
    assert [x["ordem"] for x in guardadas] == [1, 2]
    assert sum(x["favorita"] for x in guardadas) == 1
    assert "2 ficha" in r.get_data(as_text=True)


def test_a_tela_do_cartao_traz_a_fila(serventia):
    html = serventia["cliente"].get(
        f"/notas/cartoes/{serventia['cartao']}").get_data(as_text=True)
    assert "data-fila" in html
    assert "multiple" in html
