"""Coleta de foto e digitais do cadastro — sem aparelho, com JPEG e PNG.

O QUE ESTES TESTES GUARDAM
    Que a imagem mora no DISCO e o banco só tem o caminho: o blob não entra
    no SQLite. Que os quatro dedos da casa (1, 2, 6, 7) entram e o 3 recusa,
    em português, dizendo o que fazer. Que recolher substitui arquivo e linha.
    Que `estado().faltando` lista o que falta, e que foto NÃO é exigida para
    o mínimo do CCN (CPF + nome) — abrir e selar não esperam webcam.
"""
from __future__ import annotations

import hashlib
import sqlite3
import struct
import sys
import zlib
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import cadastro_biometria as CB
from notas_partes import buscar_cartoes, criar_cartao

AGORA = "2026-08-31T19:10:00"
POR = "mario"


def _png(marca: bytes) -> bytes:
    """PNG 1×1 com um texto único, para o teste achar o arquivo e não o blob."""
    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    bruto = zlib.compress(b"\x00\xff\x00\x00")
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"tEXt", b"marca\x00" + marca)
        + chunk(b"IDAT", bruto)
        + chunk(b"IEND", b"")
    )


def _jpeg(marca: bytes) -> bytes:
    """JPEG mínimo com comentário único — o domínio não decodifica, só guarda."""
    return b"\xff\xd8\xff\xfe" + bytes([0, 2 + len(marca)]) + marca + b"\xff\xd9"


JPEG = _jpeg(b"FOTO-CADASTRO-TESTE-39")
JPEG2 = _jpeg(b"FOTO-CADASTRO-RECOLHIDA")
PNG = {d: _png(f"DIGITAL-{d}".encode()) for d in CB.DEDOS_DA_CASA}
PNG3 = _png(b"DIGITAL-3-RECUSADA")


@pytest.fixture()
def casa(tmp_path):
    from database import Database

    banco = tmp_path / "cadastro.sqlite3"
    db = Database(banco)
    pasta = tmp_path / "firmas"
    pasta.mkdir()
    return {"db": db, "banco": banco, "pasta": pasta}


def _abrir(casa):
    return casa["db"].connect()


def _pessoa(con, ciencia=True, **campos) -> int:
    """O cartão, com a ciência do titular já registrada — sem ela nenhuma
    digital se colhe (correção de segurança de 26/10/2026)."""
    dados = {"nome": "MARIA DAS DORES DA SILVA", "documento": "00000001082"}
    dados.update(campos)
    cid = criar_cartao(con, dados, agora=AGORA)
    if ciencia:
        CB.registrar_ciencia(con, cid, AGORA, POR)
    return cid


# ------------------------------------------------------------- a ciência do titular


def test_sem_a_ciencia_registrada_nenhuma_digital_se_colhe(casa):
    """Correção de segurança de 26/10/2026 (revisão do PR #31): a finalidade
    na tela não prova nada; a marca no cartão prova quem informou e quando."""
    with _abrir(casa) as con:
        cid = _pessoa(con, ciencia=False)
        assert CB.ciencia(con, cid) is None
        with pytest.raises(CB.CadastroBioError) as erro:
            CB.colher_digital(con, cid, 1, PNG[1], AGORA, POR, casa["pasta"])
    assert "ciência" in str(erro.value)
    assert not (casa["pasta"] / str(cid)).exists()


def test_a_primeira_ciencia_fica_e_nao_se_regrava(casa):
    with _abrir(casa) as con:
        cid = _pessoa(con, ciencia=False)
        primeira = CB.registrar_ciencia(con, cid, AGORA, POR)
        segunda = CB.registrar_ciencia(con, cid, "2026-10-27T09:00:00", "beatriz")
        assert primeira == segunda == {"em": AGORA, "por": POR}
        with pytest.raises(CB.CadastroBioError):
            outra = _pessoa(con, ciencia=False, nome="BEATRIZ TESTE LIMA",
                            documento="00000000191")
            CB.registrar_ciencia(con, outra, AGORA, "")
        CB.colher_digital(con, cid, 1, PNG[1], AGORA, POR, casa["pasta"])


# ------------------------------------------------------------- foto no disco


def test_a_foto_mora_no_disco_e_o_caminho_no_banco(casa):
    with _abrir(casa) as con:
        cid = _pessoa(con)
        gravada = CB.colher_foto(con, cid, JPEG, AGORA, POR, casa["pasta"])

    arquivo = casa["pasta"] / str(cid) / "foto.jpg"
    assert arquivo.is_file()
    assert arquivo.read_bytes() == JPEG
    assert gravada["caminho"] == str(arquivo)
    assert gravada["nome_arquivo"] == "foto.jpg"
    assert gravada["especie"] == "FOTO"
    assert gravada["dedo"] is None
    assert gravada["sha256"] == hashlib.sha256(JPEG).hexdigest()
    assert gravada["bytes"] == len(JPEG)
    assert gravada["presencial"] == 1
    assert gravada["colhido_por"] == POR

    with _abrir(casa) as con:
        linhas = CB.imagens_do_cadastro(con, cid)
    assert len(linhas) == 1
    assert linhas[0]["caminho"] == str(arquivo)
    assert JPEG not in (linhas[0]["caminho"] or "").encode()

    bruto = casa["banco"].read_bytes()
    assert JPEG not in bruto


def test_foto_vazia_recusa_em_portugues(casa):
    with _abrir(casa) as con:
        cid = _pessoa(con)
        with pytest.raises(CB.CadastroBioError) as erro:
            CB.colher_foto(con, cid, b"", AGORA, POR, casa["pasta"])
    assert "vazia" in str(erro.value).lower()
    assert "webcam" in str(erro.value).lower()
    assert not (casa["pasta"] / str(cid) / "foto.jpg").exists()


# ------------------------------------------------------------- os quatro dedos


def test_os_quatro_dedos_da_casa_entram_e_o_3_recusa(casa):
    with _abrir(casa) as con:
        cid = _pessoa(con)
        for dedo in CB.DEDOS_DA_CASA:
            CB.colher_digital(con, cid, dedo, PNG[dedo], AGORA, POR, casa["pasta"])
        with pytest.raises(CB.CadastroBioError) as erro:
            CB.colher_digital(con, cid, 3, PNG3, AGORA, POR, casa["pasta"])

    texto = str(erro.value)
    assert "3" in texto
    assert "quatro" in texto
    for nome in CB.NOMES_DOS_DEDOS.values():
        assert nome in texto

    for dedo in CB.DEDOS_DA_CASA:
        arquivo = casa["pasta"] / str(cid) / f"digital_{dedo}.png"
        assert arquivo.is_file()
        assert arquivo.read_bytes() == PNG[dedo]
    assert not (casa["pasta"] / str(cid) / "digital_3.png").exists()

    bruto = casa["banco"].read_bytes()
    for dedo in CB.DEDOS_DA_CASA:
        assert PNG[dedo] not in bruto


def test_digital_vazia_recusa_dizendo_o_dedo(casa):
    with _abrir(casa) as con:
        cid = _pessoa(con)
        with pytest.raises(CB.CadastroBioError) as erro:
            CB.colher_digital(con, cid, 1, b"", AGORA, POR, casa["pasta"])
    assert "polegar direito" in str(erro.value)
    assert "DigitalPersona" in str(erro.value)


# ------------------------------------------------------------- recolher


def test_recolher_a_foto_substitui_arquivo_e_linha(casa):
    with _abrir(casa) as con:
        cid = _pessoa(con)
        primeira = CB.colher_foto(con, cid, JPEG, AGORA, POR, casa["pasta"])
        segunda = CB.colher_foto(
            con, cid, JPEG2, "2026-08-31T19:40:00", "ana", casa["pasta"])
        fotos = [i for i in CB.imagens_do_cadastro(con, cid)
                 if i["especie"] == "FOTO"]

    arquivo = casa["pasta"] / str(cid) / "foto.jpg"
    assert arquivo.read_bytes() == JPEG2
    assert len(fotos) == 1
    assert fotos[0]["id"] == primeira["id"] == segunda["id"]
    assert fotos[0]["sha256"] == hashlib.sha256(JPEG2).hexdigest()
    assert fotos[0]["colhido_por"] == "ana"
    assert JPEG not in casa["banco"].read_bytes()
    assert JPEG2 not in casa["banco"].read_bytes()


def test_recolher_o_mesmo_dedo_substitui(casa):
    outra = _png(b"DIGITAL-1-NOVA")
    with _abrir(casa) as con:
        cid = _pessoa(con)
        CB.colher_digital(con, cid, 1, PNG[1], AGORA, POR, casa["pasta"])
        CB.colher_digital(con, cid, 1, outra, AGORA, POR, casa["pasta"])
        digitais = [i for i in CB.imagens_do_cadastro(con, cid)
                    if i["especie"] == "DIGITAL"]

    assert len(digitais) == 1
    assert digitais[0]["dedo"] == 1
    assert (casa["pasta"] / str(cid) / "digital_1.png").read_bytes() == outra


# ------------------------------------------------------------- estado


def test_estado_lista_o_que_falta_em_portugues_e_nao_exige_foto(casa):
    """Abrir e selar não esperam webcam: o mínimo do CCN é CPF + nome."""
    with _abrir(casa) as con:
        cid = _pessoa(con)
        e = CB.estado(con, cid)

    assert e["tem_foto"] is False
    assert e["dedos"] == []
    assert e["faltando"] == [
        "fotografia",
        "polegar direito",
        "indicador direito",
        "polegar esquerdo",
        "indicador esquerdo",
    ]
    assert e["pronto_para_ccn_minimo"] is True

    with _abrir(casa) as con:
        CB.colher_digital(con, cid, 1, PNG[1], AGORA, POR, casa["pasta"])
        CB.colher_digital(con, cid, 2, PNG[2], AGORA, POR, casa["pasta"])
        e = CB.estado(con, cid)

    assert e["tem_foto"] is False
    assert e["dedos"] == [1, 2]
    assert "fotografia" in e["faltando"]
    assert "polegar esquerdo" in e["faltando"]
    assert "indicador esquerdo" in e["faltando"]
    assert "polegar direito" not in e["faltando"]
    assert e["pronto_para_ccn_minimo"] is True


def test_sem_cpf_nao_esta_pronto_para_o_ccn(casa):
    with _abrir(casa) as con:
        cid = _pessoa(con, documento="")
        e = CB.estado(con, cid)
    assert e["pronto_para_ccn_minimo"] is False
    assert "fotografia" in e["faltando"]


def test_com_foto_e_quatro_dedos_nao_falta_nada(casa):
    with _abrir(casa) as con:
        cid = _pessoa(con)
        CB.colher_foto(con, cid, JPEG, AGORA, POR, casa["pasta"])
        for dedo in CB.DEDOS_DA_CASA:
            CB.colher_digital(con, cid, dedo, PNG[dedo], AGORA, POR, casa["pasta"])
        e = CB.estado(con, cid)
    assert e["tem_foto"] is True
    assert e["dedos"] == [1, 2, 6, 7]
    assert e["faltando"] == []
    assert e["pronto_para_ccn_minimo"] is True


# ------------------------------------------------------------- cartão ausente


def test_cartao_que_nao_existe_recusa(casa):
    with _abrir(casa) as con:
        with pytest.raises(CB.CadastroBioError) as erro:
            CB.colher_foto(con, 99999, JPEG, AGORA, POR, casa["pasta"])
    assert "não há cartão" in str(erro.value).lower()
    assert "tente de novo" in str(erro.value).lower()
    assert not (casa["pasta"] / "99999" / "foto.jpg").exists()

    with _abrir(casa) as con:
        with pytest.raises(CB.CadastroBioError):
            CB.estado(con, 99999)
        with pytest.raises(CB.CadastroBioError):
            CB.imagens_do_cadastro(con, 99999)


def test_a_tabela_nova_existe_e_o_legado_biometria_fica(casa):
    """Não se reusa `nt_cartoes.biometria`. Coleta nova é outra tabela."""
    con = sqlite3.connect(casa["banco"])
    tabelas = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    colunas_cartao = {r[1] for r in con.execute("PRAGMA table_info(nt_cartoes)")}
    colunas_img = {r[1] for r in con.execute(
        "PRAGMA table_info(nt_cadastro_imagens)")}
    con.close()
    assert "nt_cadastro_imagens" in tabelas
    assert "biometria" in colunas_cartao
    assert "biometria_dedo" in colunas_cartao
    for campo in ("cartao_id", "especie", "dedo", "caminho", "sha256",
                  "bytes", "nome_arquivo", "presencial", "colhido_em",
                  "colhido_por"):
        assert campo in colunas_img
    assert "conteudo" not in colunas_img
    assert "blob" not in colunas_img


# ------------------------------------------------------------- busca no cartão


def test_homonimos_na_busca_vem_na_ordem_em_que_os_cartoes_foram_abertos(casa):
    """No empate do nome, o cartão mais antigo vem antes, como no SQLite.

    No PostgreSQL, a linha editada muda de lugar na tabela. Sem o desempate
    por `id`, editar o cartão mais antigo trocava a ordem dos homônimos na
    busca e, com o LIMIT, trocava também qual deles aparecia na tela."""
    with _abrir(casa) as con:
        antigo = _pessoa(con, nome="PESSOA FICTICIA HOMONIMA", documento="")
        novo = _pessoa(con, nome="PESSOA FICTICIA HOMONIMA", documento="")
        con.execute("UPDATE nt_cartoes SET observacao=? WHERE id=?",
                    ("cadastro conferido", antigo))
    with _abrir(casa) as con:
        assert [c["id"] for c in buscar_cartoes(con, "pessoa ficticia")] == [antigo, novo]
        assert [c["id"] for c in buscar_cartoes(con, "pessoa ficticia", limite=1)] == [antigo]


def test_a_firma_do_cartao_no_empate_de_ordem_e_a_mais_antiga(casa):
    """Duas imagens com a mesma `ordem` (o padrão é 1): vale a de `id` menor.

    É a imagem que a busca mostra no cartão. Sem o desempate, no PostgreSQL
    ela dependia de onde a linha estava gravada: a firma que entrou como 2ª e
    depois foi posta como 1ª passava a perder para a outra."""
    with _abrir(casa) as con:
        cid = _pessoa(con, nome="PESSOA FICTICIA COM DUAS FIRMAS", documento="")
        imagens = [con.execute(
            """INSERT INTO nt_cartao_imagens (cartao_id, ordem, nome_arquivo, criado_em)
               VALUES (?, ?, ?, ?)""", (cid, ordem, nome, AGORA)).lastrowid
            for ordem, nome in ((2, "firma-1.jpg"), (1, "firma-2.jpg"))]
        con.execute("UPDATE nt_cartao_imagens SET ordem=1 WHERE id=?", (imagens[0],))
    with _abrir(casa) as con:
        (achado,) = buscar_cartoes(con, "pessoa ficticia com duas")
    assert achado["imagens"] == 2
    assert achado["imagem_id"] == imagens[0]
