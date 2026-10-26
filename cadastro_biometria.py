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

QUEM FALA COM OS APARELHOS — corrigido em 26/10/2026
    Este parágrafo dizia que o módulo «não fala com webcam, nem com o leitor
    DigitalPersona». Continua verdade para ESTE ARQUIVO, e tinha deixado de
    ser verdade para o sistema, que é como ele era lido: a foto vem da webcam
    pelo navegador desde 07/09/2026 (`static/cadastro_captura.js`), e a
    digital vem do leitor HID DigitalPersona pelo SDK web do fabricante desde
    26/10/2026 (`static/leitor_digital.js`, `leitor_digital.py`). Os dois
    caminhos terminam aqui, com os bytes da imagem; este módulo só guarda.

    A digital guarda DE ONDE VEIO (`origem`: LEITOR ou ARQUIVO) e, se veio do
    leitor, o identificador do aparelho que o SDK informou (`dispositivo`).
    O que chega marcado como do leitor tem de ser PNG — é o que o SDK entrega.
    A origem é DECLARADA PELO NAVEGADOR, e não provada (ver
    `leitor_digital.ORIGEM_LEITOR`).

    E ANTES DA PRIMEIRA DIGITAL, A CIÊNCIA DO TITULAR (26/10/2026): o cartão
    guarda quando e por quem a finalidade foi lida para a pessoa
    (`registrar_ciencia`); sem essa marca, `colher_digital` recusa.

O QUE ELE NÃO FAZ
    Não fala com o CCN. Não compara digitais (a comparação 1:1 no
    reconhecimento de firma é a próxima etapa, e entra como ALERTA, nunca como
    trava). Não guarda template: o SDK web não entrega o padrão ISO/ANSI, e o
    formato intermediário do fabricante não se colhe (ver `leitor_digital`).
    Não redesenha a ficha. Não impede abrir o cartão nem selar — foto e
    digital ficam para a próxima visita, e `estado().faltando` só avisa.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from bd_nativo import banco
import leitor_digital as LD

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


def _cartao(con: Any, cartao_id: int) -> dict:
    linha = banco(con).um(
        "SELECT id, nome, documento FROM nt_cartoes WHERE id=%s",
        (int(cartao_id),),
    )
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


def _linha_existente(con: Any, cartao_id: int, especie: str,
                     dedo: int | None) -> dict | None:
    if especie == ESPECIE_FOTO:
        linha = banco(con).um(
            """SELECT * FROM nt_cadastro_imagens
                WHERE cartao_id=%s AND especie=%s
                ORDER BY id LIMIT 1""",
            (int(cartao_id), ESPECIE_FOTO),
        )
    else:
        linha = banco(con).um(
            """SELECT * FROM nt_cadastro_imagens
                WHERE cartao_id=%s AND especie=%s AND dedo=%s
                ORDER BY id LIMIT 1""",
            (int(cartao_id), ESPECIE_DIGITAL, int(dedo)),
        )
    return dict(linha) if linha else None


def _guardar(con: Any, *, cartao_id: int, especie: str,
             dedo: int | None, dados: bytes, agora: str, por: str | None,
             destino: Path, presencial: int, origem: str | None = None,
             dispositivo: str | None = None) -> dict:
    digest = _sha256(dados)
    tamanho = len(dados)
    nome = destino.name
    caminho = str(destino)
    quem = (por or "").strip() or None
    anterior = _linha_existente(con, cartao_id, especie, dedo)
    _gravar_arquivo(destino, dados, anterior["caminho"] if anterior else None)

    if anterior:
        banco(con).escrever(
            """UPDATE nt_cadastro_imagens
                  SET caminho=%s, nome_arquivo=%s, sha256=%s, bytes=%s,
                      presencial=%s, colhido_em=%s, colhido_por=%s,
                      origem=%s, dispositivo=%s
                WHERE id=%s""",
            (caminho, nome, digest, tamanho, int(presencial), agora, quem,
             origem, dispositivo, anterior["id"]),
        )
        row_id = int(anterior["id"])
    else:
        row_id = int(banco(con).escrever(
            """INSERT INTO nt_cadastro_imagens
               (cartao_id, especie, dedo, caminho, nome_arquivo, sha256, bytes,
                presencial, colhido_em, colhido_por, origem, dispositivo)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (int(cartao_id), especie, dedo, caminho, nome, digest, tamanho,
             int(presencial), agora, quem, origem, dispositivo),
        )[0]["id"])

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
        "origem": origem,
        "dispositivo": dispositivo,
    }


def colher_foto(con: Any, cartao_id: int, jpeg_bytes: bytes,
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


def ciencia(con: Any, cartao_id: int) -> dict | None:
    """A ciência do titular registrada no cartão, ou `None`. Só LÊ.

    Correção de segurança de 26/10/2026 (revisão do PR #31): ver
    `leitor_digital.BASE_LEGAL`.
    """
    _cartao(con, cartao_id)
    linha = banco(con).um(
        """SELECT biometria_ciencia_em, biometria_ciencia_por
             FROM nt_cartoes WHERE id=%s""", (int(cartao_id),))
    if not linha or not linha["biometria_ciencia_em"]:
        return None
    return {"em": linha["biometria_ciencia_em"],
            "por": linha["biometria_ciencia_por"]}


def registrar_ciencia(con: Any, cartao_id: int, agora: str,
                      por: str | None) -> dict:
    """Registra que a finalidade foi lida para a pessoa — ciência como
    TRANSPARÊNCIA (LGPD art. 9º), e não consentimento: a hipótese é o art. 11,
    II, «g» (decisão do oficial em 26/10/2026). ESCREVE só a marca do cartão.

    A primeira marca FICA: registrar de novo não regrava quem informou nem
    quando — o fato é o do dia em que aconteceu.
    """
    ja = ciencia(con, cartao_id)
    if ja:
        return ja
    quem = (por or "").strip()
    if not quem:
        raise CadastroBioError(
            "Não sei quem está registrando a ciência. Entre de novo no sistema "
            "e registre outra vez.")
    banco(con).escrever(
        """UPDATE nt_cartoes SET biometria_ciencia_em=%s, biometria_ciencia_por=%s
            WHERE id=%s AND biometria_ciencia_em IS NULL""",
        (agora, quem, int(cartao_id)))
    return ciencia(con, cartao_id) or {"em": agora, "por": quem}


def colher_digital(con: Any, cartao_id: int, dedo: int,
                   png_bytes: bytes, agora: str, por: str | None,
                   pasta_base: Any, origem: str = LD.ORIGEM_ARQUIVO,
                   dispositivo: str | None = None) -> dict:
    """Grava a digital de um dos quatro dedos da casa. ESCREVE arquivo e linha.

    Recolher o mesmo dedo substitui o arquivo e a linha. Dedo fora de
    `{1, 2, 6, 7}` recusa, dizendo o que usar.

    `origem` diz de onde veio a imagem: `LEITOR` (o SDK do fabricante, na
    tela) ou `ARQUIVO` (o envio manual, que continua como reserva). A do
    leitor tem de ser PNG — é o que o SDK entrega quando se pede imagem; o que
    chega marcado como do leitor e não é PNG não veio dele, e se recusa.
    `dispositivo` é o identificador do aparelho que o SDK informou; só se
    guarda quando a origem é o leitor.

    E SEM A CIÊNCIA DO TITULAR REGISTRADA NO CARTÃO NÃO SE COLHE (correção de
    segurança de 26/10/2026): ver `ciencia` e `leitor_digital.BASE_LEGAL`.
    """
    _cartao(con, cartao_id)
    if not ciencia(con, cartao_id):
        raise CadastroBioError(
            "Antes de colher a digital, leia para a pessoa a finalidade da "
            "coleta e registre a ciência dela no quadro «Digitais» do cartão. "
            "Nada foi gravado.")
    origem = str(origem or LD.ORIGEM_ARQUIVO).strip().upper()
    if origem not in LD.ORIGENS:
        raise CadastroBioError(
            f"Origem da digital desconhecida: «{origem}». A digital vem do "
            "leitor ou de um arquivo enviado; colha de novo pela tela.")
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
    if origem == LD.ORIGEM_LEITOR and not LD.e_png(png_bytes):
        raise CadastroBioError(
            f"A digital do {nome_do_dedo(codigo)} não chegou como imagem do "
            "leitor (o leitor entrega PNG). Colha de novo no leitor, ou envie "
            "o arquivo pelo campo de envio manual.")
    aparelho = None
    if origem == LD.ORIGEM_LEITOR:
        aparelho = (str(dispositivo or "").strip()[:120]) or None
    destino = (
        _pasta_do_cartao(pasta_base, cartao_id)
        / _ARQUIVO_DIGITAL.format(dedo=codigo)
    )
    return _guardar(
        con, cartao_id=cartao_id, especie=ESPECIE_DIGITAL, dedo=codigo,
        dados=bytes(png_bytes), agora=agora, por=por, destino=destino,
        presencial=1, origem=origem, dispositivo=aparelho,
    )


def imagens_do_cadastro(con: Any, cartao_id: int) -> list[dict]:
    """As imagens do cadastro, foto primeiro. Só LÊ. Sem o blob."""
    _cartao(con, cartao_id)
    return banco(con).ler(
        """SELECT id, cartao_id, especie, dedo, caminho, nome_arquivo,
                  sha256, bytes, presencial, colhido_em, colhido_por,
                  origem, dispositivo
             FROM nt_cadastro_imagens
            WHERE cartao_id=%s
            ORDER BY CASE especie WHEN 'FOTO' THEN 0 ELSE 1 END, dedo, id""",
        (int(cartao_id),),
    )


def estado(con: Any, cartao_id: int) -> dict:
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
