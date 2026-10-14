"""
Foto e digitais do cadastro — o cartão de autógrafo, não a ficha de papel.

O PROBLEMA QUE ISTO RESOLVE
    Na abertura da ficha o oficial colhe fotografia e digitais para o Cadastro
    de Clientes do Notariado (CCN). A ficha impressa NÃO muda: decisão de
    31/08/2026. Foto e digital moram no CADASTRO, e o cadastro em Notas é o
    cartão (`nt_cartoes`). Não há tabela `pessoas` nem `clientes`.

    Os 462 moldes em `nt_cartoes.biometria` são texto do leitor antigo do
    E-Ofício, sem o dedo marcado, e não são imagem. Não se reaproveitam. A
    coluna fica como legado; a coleta nova grava arquivo em disco.

ONDE MORA O ARQUIVO
    Em disco, como as assinaturas (`nt_cartao_imagens`): pasta
    `{pasta_base}/{cartao_id}/foto.jpg` e `digital_{dedo}.png`. O banco guarda
    caminho, espécie, dedo, sha256, tamanho, quando e quem colheu. Nunca o
    blob. Recolher substitui o arquivo e a linha daquela espécie+dedo.

O QUE ELE NÃO FAZ
    Não fala com webcam, nem com o leitor DigitalPersona, nem com o CCN.
    Não redesenha a ficha. Não impede abrir o cartão nem selar — foto e
    digital ficam para a próxima visita, e `estado().faltando` só avisa.
"""
from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Any

# Códigos do CCN (1–10). Esta casa colhe os quatro de identificação:
# polegar e indicador de cada mão. Decisão do oficial em 31/08/2026.
DEDOS_DA_CASA = (1, 2, 6, 7)

NOMES_DOS_DEDOS = {
    1: "polegar direito",
    2: "indicador direito",
    6: "polegar esquerdo",
    7: "indicador esquerdo",
}

ESPECIE_FOTO = "FOTO"
ESPECIE_DIGITAL = "DIGITAL"

_ARQUIVO_FOTO = "foto.jpg"
_ARQUIVO_DIGITAL = "digital_{dedo}.png"


class CadastroBioError(ValueError):
    """Erro de regra da coleta, com a mensagem pronta para o balcão."""


def nome_do_dedo(dedo: int) -> str:
    return NOMES_DOS_DEDOS.get(int(dedo), f"dedo {dedo}")


def _sha256(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()


def _cartao(con: sqlite3.Connection, cartao_id: int) -> dict:
    linha = con.execute(
        "SELECT id, nome, documento FROM nt_cartoes WHERE id=?",
        (int(cartao_id),),
    ).fetchone()
    if not linha:
        raise CadastroBioError(
            "Não há cartão com esse número. Abra o cadastro da pessoa em "
            "Cartões de autógrafo e tente de novo."
        )
    return dict(linha)


def _pasta_do_cartao(pasta_base: Any, cartao_id: int) -> Path:
    return Path(pasta_base) / str(int(cartao_id))


def _gravar_arquivo(destino: Path, dados: bytes, anterior: str | None) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(dados)
    if not anterior:
        return
    antigo = Path(anterior)
    try:
        if antigo.resolve() != destino.resolve() and antigo.is_file():
            antigo.unlink()
    except OSError:
        pass


def _linha_existente(con: sqlite3.Connection, cartao_id: int, especie: str,
                     dedo: int | None) -> dict | None:
    if especie == ESPECIE_FOTO:
        linha = con.execute(
            """SELECT * FROM nt_cadastro_imagens
                WHERE cartao_id=? AND especie=?""",
            (int(cartao_id), ESPECIE_FOTO),
        ).fetchone()
    else:
        linha = con.execute(
            """SELECT * FROM nt_cadastro_imagens
                WHERE cartao_id=? AND especie=? AND dedo=?""",
            (int(cartao_id), ESPECIE_DIGITAL, int(dedo)),
        ).fetchone()
    return dict(linha) if linha else None


def _guardar(con: sqlite3.Connection, *, cartao_id: int, especie: str,
             dedo: int | None, dados: bytes, agora: str, por: str | None,
             destino: Path, presencial: int) -> dict:
    digest = _sha256(dados)
    tamanho = len(dados)
    nome = destino.name
    caminho = str(destino)
    quem = (por or "").strip() or None
    anterior = _linha_existente(con, cartao_id, especie, dedo)
    _gravar_arquivo(destino, dados, anterior["caminho"] if anterior else None)

    if anterior:
        con.execute(
            """UPDATE nt_cadastro_imagens
                  SET caminho=?, nome_arquivo=?, sha256=?, bytes=?,
                      presencial=?, colhido_em=?, colhido_por=?
                WHERE id=?""",
            (caminho, nome, digest, tamanho, int(presencial), agora, quem,
             anterior["id"]),
        )
        row_id = int(anterior["id"])
    else:
        cur = con.execute(
            """INSERT INTO nt_cadastro_imagens
               (cartao_id, especie, dedo, caminho, nome_arquivo, sha256, bytes,
                presencial, colhido_em, colhido_por)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (int(cartao_id), especie, dedo, caminho, nome, digest, tamanho,
             int(presencial), agora, quem),
        )
        row_id = int(cur.lastrowid)

    return {
        "id": row_id,
        "cartao_id": int(cartao_id),
        "especie": especie,
        "dedo": dedo,
        "caminho": caminho,
        "nome_arquivo": nome,
        "sha256": digest,
        "bytes": tamanho,
        "presencial": int(presencial),
        "colhido_em": agora,
        "colhido_por": quem,
    }


def colher_foto(con: sqlite3.Connection, cartao_id: int, jpeg_bytes: bytes,
                agora: str, por: str | None, pasta_base: Any) -> dict:
    """Grava a fotografia do cadastro. ESCREVE arquivo e linha.

    `presencial=1`: foto colhida no balcão, que o CCN recebe como
    `fotoVerificada=true`. Recolher substitui a anterior.
    """
    _cartao(con, cartao_id)
    if not jpeg_bytes:
        raise CadastroBioError(
            "A fotografia veio vazia. Colha de novo pela webcam e confirme "
            "que a imagem apareceu na tela antes de gravar."
        )
    destino = _pasta_do_cartao(pasta_base, cartao_id) / _ARQUIVO_FOTO
    return _guardar(
        con, cartao_id=cartao_id, especie=ESPECIE_FOTO, dedo=None,
        dados=bytes(jpeg_bytes), agora=agora, por=por, destino=destino,
        presencial=1,
    )


def colher_digital(con: sqlite3.Connection, cartao_id: int, dedo: int,
                   png_bytes: bytes, agora: str, por: str | None,
                   pasta_base: Any) -> dict:
    """Grava a digital de um dos quatro dedos da casa. ESCREVE arquivo e linha.

    Recolher o mesmo dedo substitui o arquivo e a linha. Dedo fora de
    `{1, 2, 6, 7}` recusa, dizendo o que usar.
    """
    _cartao(con, cartao_id)
    try:
        codigo = int(dedo)
    except (TypeError, ValueError):
        codigo = -1
    if codigo not in DEDOS_DA_CASA:
        nomes = ", ".join(
            f"{NOMES_DOS_DEDOS[d]} ({d})" for d in DEDOS_DA_CASA
        )
        raise CadastroBioError(
            f"O dedo {dedo} não é um dos quatro que esta casa colhe "
            f"({nomes}). Escolha um desses quatro e colha de novo."
        )
    if not png_bytes:
        raise CadastroBioError(
            f"A digital do {nome_do_dedo(codigo)} veio vazia. Colha de novo "
            "no leitor DigitalPersona e tente outra vez."
        )
    destino = (
        _pasta_do_cartao(pasta_base, cartao_id)
        / _ARQUIVO_DIGITAL.format(dedo=codigo)
    )
    return _guardar(
        con, cartao_id=cartao_id, especie=ESPECIE_DIGITAL, dedo=codigo,
        dados=bytes(png_bytes), agora=agora, por=por, destino=destino,
        presencial=1,
    )


def imagens_do_cadastro(con: sqlite3.Connection, cartao_id: int) -> list[dict]:
    """As imagens do cadastro, foto primeiro. Só LÊ. Sem o blob."""
    _cartao(con, cartao_id)
    return [dict(r) for r in con.execute(
        """SELECT id, cartao_id, especie, dedo, caminho, nome_arquivo,
                  sha256, bytes, presencial, colhido_em, colhido_por
             FROM nt_cadastro_imagens
            WHERE cartao_id=?
            ORDER BY CASE especie WHEN 'FOTO' THEN 0 ELSE 1 END, dedo, id""",
        (int(cartao_id),),
    )]


def estado(con: sqlite3.Connection, cartao_id: int) -> dict:
    """O que o cadastro já tem, e o que falta, em português. Só LÊ.

    `pronto_para_ccn_minimo` é CPF + nome — o mínimo que o CCN aceita.
    Foto e digitais NÃO entram nesse mínimo: abrir e selar não esperam.
    """
    cartao = _cartao(con, cartao_id)
    imgs = imagens_do_cadastro(con, cartao_id)
    tem_foto = any(i["especie"] == ESPECIE_FOTO for i in imgs)
    presentes = {
        int(i["dedo"]) for i in imgs
        if i["especie"] == ESPECIE_DIGITAL and i["dedo"] is not None
    }
    faltando: list[str] = []
    if not tem_foto:
        faltando.append("fotografia")
    for codigo in DEDOS_DA_CASA:
        if codigo not in presentes:
            faltando.append(NOMES_DOS_DEDOS[codigo])
    nome = (cartao.get("nome") or "").strip()
    cpf = "".join(c for c in str(cartao.get("documento") or "") if c.isdigit())
    return {
        "cartao_id": int(cartao_id),
        "tem_foto": tem_foto,
        "dedos": sorted(presentes),
        "faltando": faltando,
        "pronto_para_ccn_minimo": bool(nome) and len(cpf) == 11,
    }
