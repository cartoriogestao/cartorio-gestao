"""A colheita da digital ganhou tela — relato #39 do oficial.

    «nas aberturas de fichas para reconhecimento de firmas precisamos
     implantar a ferramenta de captura de fotografia pela webcam e coleita de
     digital por aparelho de biometria, e ter ferramenta de exportação de
     todas as fichas para o cadastro de clientes do notariado»
                                                — o oficial, 31/08/2026

SÃO TRÊS PEDIDOS, E ELES ESTAVAM EM TRÊS ESTADOS DIFERENTES
    | | |
    |---|---|
    | **foto pela webcam** | **construída** — rota, tela e o `getUserMedia` |
    | **digital dos dedos** | o domínio existia e **nenhuma tela o chamava** |
    | **exportar para o notariado** | **não dá**, e a razão está medida |

    A do meio é o defeito mais repetido deste projeto, e estava **declarado**:
    `test_funcao_sem_tela.py` listava `colher_digital` como órfã conhecida,
    com a razão escrita. Declarar não é resolver — mas evitou que ela fosse
    apagada por engano, e é por isso que a lista existe.

O QUE ESTA TELA NÃO FAZ, E DIZ QUE NÃO
    **O aparelho não é este sistema.** O leitor de digital entrega uma imagem;
    o que a tela faz é guardá-la no cadastro. Escrever «o sistema lê a
    digital» seria prometer driver que ele não tem — e é a mesma recusa do
    módulo da assinatura A3, que não assina porque não pode.

    **E a exportação para o CCN do e-Notariado continua impossível**, por duas
    paredes medidas em 04/09/2026 e escritas em `O_CCN_E_AS_DUAS_PAREDES.md`:
    a Cloudflare na rota da API, e o `X-Signature` que exige assinatura CAdES
    por requisição — com o A3 que dá segfault no processo do Flask.
"""
from __future__ import annotations

import glob
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import cadastro_biometria as CB                                  # noqa: E402

SENHA = "Senha#12345"

# Um PNG mínimo de verdade — 1×1, cinza. O domínio confere que é imagem.
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000100ffff03000006000557bfabd400"
    "00000049454e44ae426082")


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa):
    """App/DB compartilhados do modulo (conftest); setup de dominio por teste."""
    banco = cg_casa["banco"]
    c = cg_casa["c"]
    cg_casa["db"].create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS",
                                SENHA, "ADMIN")
    c.post("/login",
           data={"username": "tabeliao", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    con = sqlite3.connect(banco)
    con.execute("INSERT INTO nt_cartoes (numero, nome, criado_em) "
                "VALUES ('1','FULANO DE TAL','2026-09-07')")
    con.commit()
    cid = int(con.execute("SELECT id FROM nt_cartoes").fetchone()[0])
    con.close()
    return {**cg_casa, "cartao": cid}

def _colher(casa, dedo: int, dados: bytes = PNG):
    from io import BytesIO
    tela = casa["c"].get(f"/notas/cartoes/{casa['cartao']}").get_data(
        as_text=True)
    return casa["c"].post(
        f"/notas/cartoes/{casa['cartao']}/digital",
        data={"csrf_token": _token(tela), "dedo": str(dedo),
              "digital": (BytesIO(dados), "digital.png")},
        content_type="multipart/form-data", follow_redirects=True)


# ============================================ a peça que faltava


def test_A_ROTA_EXISTE_E_A_TELA_A_CHAMA(casa):
    """**O defeito mais repetido deste projeto**, e este estava declarado como
    órfão conhecido em `test_funcao_sem_tela.py`."""
    regras = {r.rule for r in casa["app"].url_map.iter_rules()}
    assert "/notas/cartoes/<int:cartao_id>/digital" in regras
    assert "/notas/cartoes/<int:cartao_id>/digital/<int:dedo>" in regras

    html = casa["c"].get(f"/notas/cartoes/{casa['cartao']}").get_data(
        as_text=True)
    assert f"/notas/cartoes/{casa['cartao']}/digital" in html
    assert 'name="dedo"' in html


def test_colher_grava_e_a_tela_mostra(casa):
    r = _colher(casa, 1)
    assert r.status_code == 200
    assert "Digital do polegar direito colhida" in " ".join(
        r.get_data(as_text=True).split())
    assert casa["c"].get(
        f"/notas/cartoes/{casa['cartao']}/digital/1").status_code == 200


def test_OS_QUATRO_DEDOS_DA_CASA_e_nao_dez(casa):
    """**Quem escolheu foi o domínio**, e a tela não inventa um quinto —
    `DEDOS_DA_CASA` é polegar e indicador de cada mão."""
    html = casa["c"].get(f"/notas/cartoes/{casa['cartao']}").get_data(
        as_text=True)
    for dedo in CB.DEDOS_DA_CASA:
        assert CB.nome_do_dedo(dedo) in html
    assert len(CB.DEDOS_DA_CASA) == 4
    # e um dedo de fora é recusado, com a frase que diz o que usar
    r = _colher(casa, 3)
    assert "Digital do" not in " ".join(r.get_data(as_text=True).split())


def test_A_LISTA_DOS_DEDOS_VEM_DO_DOMINIO_e_nao_da_tela(casa):
    """Uma lista escrita no template divergiria de `DEDOS_DA_CASA` no primeiro
    conserto, e a tela ofereceria um dedo que o domínio recusa."""
    fonte = (RAIZ / "templates" / "notas_cartao.html").read_text(
        encoding="utf-8")
    for nome in CB.NOMES_DOS_DEDOS.values():
        assert nome not in fonte, (
            f"«{nome}» está escrito no template — os nomes têm de vir de "
            f"`CB.nome_do_dedo`")


def test_recolher_o_MESMO_DEDO_substitui(casa):
    """Quem colhe de novo é porque a primeira saiu ruim. Guardar as duas faria
    a conferência ter de escolher entre elas."""
    _colher(casa, 1)
    outra = PNG[:-1] + bytes([PNG[-1] ^ 0xFF])
    _colher(casa, 1, outra)
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    quantas = CB.imagens_do_cadastro(con, casa["cartao"])
    con.close()
    digitais = [i for i in quantas if i["especie"] == CB.ESPECIE_DIGITAL
                and int(i["dedo"] or 0) == 1]
    assert len(digitais) == 1, "recolher tem de substituir, e não acumular"


def test_arquivo_vazio_e_erro_de_REGRA_e_nao_500(casa):
    r = _colher(casa, 1, b"")
    assert r.status_code == 200
    assert "Digital do" not in " ".join(r.get_data(as_text=True).split())


def test_digital_que_nao_existe_da_404_e_NAO_CRIA_NADA(casa):
    assert casa["c"].get(
        f"/notas/cartoes/{casa['cartao']}/digital/2").status_code == 404
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    assert not CB.imagens_do_cadastro(con, casa["cartao"])
    con.close()


# ============================================ o que NÃO se promete


def test_A_TELA_DIZ_QUE_O_APARELHO_NAO_E_ESTE_SISTEMA(casa):
    """**Prometer driver que não se tem é pior que não ter a tela.** O leitor
    entrega uma imagem; o que a tela faz é guardá-la — a mesma recusa do
    módulo da assinatura A3, que não assina porque não pode."""
    html = " ".join(casa["c"].get(f"/notas/cartoes/{casa['cartao']}")
                    .get_data(as_text=True).split())
    assert "O aparelho não é este sistema" in html
    assert "guardá-la no cadastro" in html


def test_a_exportacao_para_o_NOTARIADO_continua_declarada_impossivel():
    """A terceira metade do relato. **Não construir é a resposta certa**, e a
    razão está medida: a Cloudflare na rota da API e o `X-Signature` que exige
    CAdES por requisição, com o A3 que dá segfault no processo."""
    doc = (RAIZ / "DOCUMENTACAO" / "O_CCN_E_AS_DUAS_PAREDES.md").read_text(
        encoding="utf-8")
    assert "Cloudflare" in doc and "X-Signature" in doc
