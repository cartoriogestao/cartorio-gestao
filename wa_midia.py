"""O arquivo da conversa do WhatsApp: o que o cliente manda, e o que a casa envia.

    «receba arquivos enviados na conversa» — o oficial, 29/10/2026

O DEFEITO QUE ISTO CONSERTA
    Da foto, do PDF e do documento que o cliente mandava, a fila guardava só o
    TIPO e o id da mídia (`wa_balcao.tipo_e_midia`). O balão mostrava «image —»
    e ninguém via o documento: quem atendia pedia de novo, ou abria o celular.
    Só o áudio era baixado, e só para a transcrição — os bytes eram jogados
    fora depois.

O QUE ELE FAZ
    `baixar_pendentes` (o vigia chama a cada volta) pega as mensagens com mídia
    ainda não baixada, pede à Graph o endereço do arquivo, baixa e guarda na
    pasta da casa (`<arquivos>/whatsapp/AAAA-MM/`), com nome, tipo, tamanho e
    sha256 em `wa_mensagem`. O balão passa a mostrar a foto, o PDF, o áudio e o
    vídeo, e a baixar o resto (`wa_web.whatsapp_midia`).

    `subir` e `montar_envio` são a outra direção: quem atende escolhe um
    arquivo, a casa o guarda, sobe à Meta (`/media`) e manda a mensagem com o id
    que a Meta devolveu.

TRÊS TEMPOS, E SÓ O DO MEIO FALA COM A REDE (a regra da casa)
    (1) transação curta que marca a mensagem como «baixando» — a trava contra
    duas voltas baixarem o mesmo arquivo; (2) a Graph, sem transação; (3)
    transação curta que grava onde o arquivo ficou. Falhou, a mensagem fica
    «erro» com o motivo, e não tenta de novo sozinha a cada 20 segundos: o
    balão oferece «tentar de novo».

O TOKEN SÓ VAI À META
    O endereço do arquivo vem da Graph, e é CONFERIDO antes de o token ir junto
    (`wa_transcricao._midia_e_da_meta`, a mesma régua do áudio): só HTTPS, e só
    nos domínios da própria Meta.

O QUE O NAVEGADOR ABRE NA TELA, E O QUE BAIXA
    `MOSTRA_NA_TELA` é lista curta, pela razão de `arquivo_visivel`: arquivo
    servido em linha roda na origem do sistema. Foto (jpeg, png, webp), PDF,
    áudio e vídeo mp4 o navegador desenha ou toca sem executar. O resto — Word,
    planilha, o que o cliente mandar — baixa. O tipo que decide é o que a casa
    deduziu do arquivo guardado, e não o que o cliente declarou.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import logging
import ssl
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from bd_nativo import banco

import storage as ARQ
import wa_schema as WA
import wa_transcricao as TRANSC

LOG = logging.getLogger(__name__)

GRAPH_HOST = TRANSC.GRAPH_HOST
GRAPH_VER = TRANSC.GRAPH_VER
PRAZO = 60
# O WhatsApp aceita documento de até 100 MB; a casa guarda até 25 MB — acima
# disso o balão diz que o arquivo ficou no celular do cliente, em vez de
# encher o disco do servidor com um vídeo.
TETO_DE_BYTES = 25 * 1024 * 1024
PRESO_MINUTOS = 15          # «baixando» mais velho que isso é volta que caiu
POR_VOLTA = 10              # arquivos por volta do vigia
DIAS_DA_META = 30           # a Meta guarda a mídia por 30 dias; depois, não adianta pedir

# O tipo pelo mime que a Meta informa, e a extensão com que a casa guarda.
EXTENSAO_DO_MIME = {
    "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp",
    "application/pdf": "pdf",
    "audio/ogg": "ogg", "audio/mpeg": "mp3", "audio/mp4": "m4a", "audio/aac": "aac",
    "audio/amr": "amr",
    "video/mp4": "mp4", "video/3gpp": "3gp",
    "text/plain": "txt",
    "application/msword": "doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.ms-excel": "xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.oasis.opendocument.text": "odt",
}
# O que o navegador desenha ou toca sem executar (ver o cabeçalho).
MOSTRA_NA_TELA = {
    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp",
    "pdf": "application/pdf",
    "ogg": "audio/ogg", "mp3": "audio/mpeg", "m4a": "audio/mp4", "aac": "audio/aac",
    "mp4": "video/mp4",
}
FOTO = ("jpg", "jpeg", "png", "webp")
AUDIO = ("ogg", "mp3", "m4a", "aac")
VIDEO = ("mp4",)

# O QUE QUEM ATENDE PODE ENVIAR, e como a Meta o chama. Os tetos são os da
# própria Meta (foto 5 MB, áudio e vídeo 16 MB, documento 100 MB — aqui, 25).
ENVIO_POR_EXTENSAO = {
    "jpg": ("image", "image/jpeg", 5), "jpeg": ("image", "image/jpeg", 5),
    "png": ("image", "image/png", 5),
    "pdf": ("document", "application/pdf", 25),
    "doc": ("document", "application/msword", 25),
    "docx": ("document",
             "application/vnd.openxmlformats-officedocument.wordprocessingml.document", 25),
    "xls": ("document", "application/vnd.ms-excel", 25),
    "xlsx": ("document",
             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 25),
    "txt": ("document", "text/plain", 25),
    "mp3": ("audio", "audio/mpeg", 16), "ogg": ("audio", "audio/ogg", 16),
    "mp4": ("video", "video/mp4", 16),
}


class MidiaErro(ValueError):
    """O arquivo não pôde ser baixado, guardado ou enviado. Mensagem pronta."""


class MidiaPassageira(MidiaErro):
    """A Graph respondeu 5xx ou 429: passa, e vale tentar de novo depois."""


# O ERRO PASSAGEIRO NÃO VIRA DEFINITIVO (29/10/2026): rede caída, tempo
# esgotado e a Graph com 5xx ou 429 devolvem a mensagem à fila, e só a terceira
# vez grava o erro. A espera entre as tentativas existe porque o vigia roda a
# cada poucos segundos: sem ela, as três se gastariam em menos de um minuto.
TENTATIVAS_DA_MIDIA = 3
ESPERA_ENTRE_TENTATIVAS_MIN = 2
PASSAGEIROS = (MidiaPassageira, OSError, http.client.HTTPException)


def _http(status: int, texto: str) -> MidiaErro:
    """O erro de HTTP da Graph: 5xx e 429 passam; o resto é definitivo."""
    passa = status == 429 or 500 <= status <= 599
    return (MidiaPassageira if passa else MidiaErro)(texto)


# ------------------------------------------------------------- a rede


def _https(host: str, metodo: str, caminho: str, *, corpo: bytes | None = None,
           cabecalhos: dict | None = None, prazo: int = PRAZO) -> tuple[int, bytes]:
    """FALA COM A REDE. Isolado para os testes trocarem por um falso. Lê no
    máximo um byte além do teto: o arquivo maior é recusado sem ir inteiro à
    memória."""
    con = http.client.HTTPSConnection(host, 443, timeout=prazo,
                                      context=ssl.create_default_context())
    try:
        con.request(metodo, caminho, body=corpo, headers=cabecalhos or {})
        resp = con.getresponse()
        return int(resp.status), resp.read(TETO_DE_BYTES + 1)
    finally:
        con.close()


def baixar(token: str, midia_id: str, *, https: Callable | None = None) -> tuple[bytes, str]:
    """(bytes, mime) da mídia. FALA COM A REDE (a Graph, duas vezes)."""
    if not token:
        raise MidiaErro("Falta o access_token da Meta na configuração.")
    if not str(midia_id or "").strip():
        raise MidiaErro("A mensagem não traz o id do arquivo.")
    fn = https or _https
    cab = {"Authorization": f"Bearer {token}"}
    status, bruto = fn(GRAPH_HOST, "GET", f"/{GRAPH_VER}/{midia_id}", cabecalhos=cab)
    if status != 200:
        raise _http(status, f"A Meta não entregou o endereço do arquivo (HTTP {status}). "
                            "Depois de 30 dias ela apaga a mídia.")
    try:
        info = json.loads(bruto.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as erro:
        raise MidiaErro("A Meta respondeu num formato que eu não entendi.") from erro
    try:
        host, caminho = TRANSC._midia_e_da_meta(info.get("url"))
    except TRANSC.TranscricaoErro as erro:
        raise MidiaErro("A Meta indicou um endereço fora dela; o arquivo não foi "
                        "baixado e o token não saiu daqui.") from erro
    declarado = int(info.get("file_size") or 0)
    if declarado > TETO_DE_BYTES:
        raise MidiaErro(f"O arquivo tem {declarado // (1024 * 1024)} MB; a casa guarda "
                        f"até {TETO_DE_BYTES // (1024 * 1024)} MB. Peça ao cliente por "
                        "outro meio, ou abra pelo celular.")
    status, dados = fn(host, "GET", caminho, cabecalhos=cab)
    if status != 200:
        raise _http(status, f"A Meta não entregou o arquivo (HTTP {status}).")
    if len(dados) > TETO_DE_BYTES:
        raise MidiaErro(f"O arquivo passa de {TETO_DE_BYTES // (1024 * 1024)} MB e não "
                        "foi guardado.")
    mime = str(info.get("mime_type") or "").split(";")[0].strip().lower()
    return dados, mime or "application/octet-stream"


def _multipart(campos: dict, arquivo: bytes, nome: str, mime: str) -> tuple[bytes, str]:
    fronteira = "cg" + uuid.uuid4().hex
    partes: list[bytes] = []
    for chave, valor in campos.items():
        partes.append(f"--{fronteira}\r\nContent-Disposition: form-data; name=\"{chave}\""
                      f"\r\n\r\n{valor}\r\n".encode("utf-8"))
    nome_seguro = nome.replace('"', "").replace("\r", "").replace("\n", "")
    partes.append(f"--{fronteira}\r\nContent-Disposition: form-data; name=\"file\"; "
                  f"filename=\"{nome_seguro}\"\r\nContent-Type: {mime}\r\n\r\n"
                  .encode("utf-8"))
    partes.append(arquivo)
    partes.append(f"\r\n--{fronteira}--\r\n".encode("utf-8"))
    return b"".join(partes), f"multipart/form-data; boundary={fronteira}"


def subir(token: str, phone: str, dados: bytes, mime: str, nome: str, *,
          https: Callable | None = None) -> str:
    """Sobe o arquivo à Meta e devolve o id da mídia. FALA COM A REDE."""
    if not token or not phone:
        raise MidiaErro("Falta access_token ou phone_number_id na configuração.")
    corpo, tipo = _multipart({"messaging_product": "whatsapp", "type": mime},
                             dados, nome, mime)
    fn = https or _https
    try:
        status, bruto = fn(GRAPH_HOST, "POST", f"/{GRAPH_VER}/{phone}/media", corpo=corpo,
                           cabecalhos={"Authorization": f"Bearer {token}",
                                       "Content-Type": tipo})
    except OSError as falha:
        raise MidiaErro(f"Não consegui falar com a Meta: {falha}. Nada foi enviado.") from falha
    try:
        resposta = json.loads(bruto.decode("utf-8") or "{}")
    except (UnicodeDecodeError, ValueError):
        resposta = {}
    if status < 200 or status >= 300 or not resposta.get("id"):
        erro = (resposta.get("error") or {}).get("message") or f"HTTP {status}"
        raise MidiaErro(f"A Meta recusou o arquivo: {erro}. Nada foi enviado.")
    return str(resposta["id"])


# ------------------------------------------------------------- o que se guarda


def extensao(nome: str) -> str:
    return Path(str(nome or "")).suffix.lstrip(".").lower()


def nome_do_arquivo(mensagem: dict, mime: str) -> str:
    """O nome com que a casa guarda: o que o cliente deu ao documento (limpo),
    ou «whatsapp_<id>.<ext>». A extensão SAI DO TIPO quando o nome não tem uma
    que a casa conheça — o tipo é o que a Meta mediu, e não o que o cliente
    escreveu."""
    try:
        bruto = json.loads(mensagem.get("bruto_json") or "{}")
    except ValueError:
        bruto = {}
    dado = ""
    for chave in ("document", "image", "video", "audio", "sticker"):
        bloco = bruto.get(chave)
        if isinstance(bloco, dict) and bloco.get("filename"):
            dado = str(bloco["filename"])
            break
    ext = EXTENSAO_DO_MIME.get(mime, "")
    nome = ARQ.safe_component(Path(dado).name, "") if dado else ""
    if nome and extensao(nome) in set(EXTENSAO_DO_MIME.values()):
        return nome[:120]
    base = Path(nome).stem[:80] if nome else f"whatsapp_{mensagem.get('id')}"
    return f"{base}.{ext}" if ext else f"{base}.bin"


def pasta_do_mes(pasta_arquivos: Path, agora: str) -> Path:
    return Path(pasta_arquivos) / "whatsapp" / str(agora)[:7]


# AS EXTENSÕES COM QUE A CASA GRAVA. O nome do arquivo em disco NÃO vem de
# fora (revisão do CodeQL no #94, 29/10/2026): é o sha256 do conteúdo mais uma
# extensão desta lista. O nome que o cliente ou o atendente deu fica só em
# `arquivo_nome`, para a tela — com ele no caminho, um «..\..\x» escreveria
# fora da pasta da casa.
EXTENSOES_GUARDADAS = tuple(sorted(set(EXTENSAO_DO_MIME.values())
                                   | set(ENVIO_POR_EXTENSAO) | {"bin", "jpeg"}))


def _extensao_da_casa(nome: str) -> str:
    """A extensão de `nome`, mas como a string DA LISTA (e não a que veio de
    fora); o que não está na lista vira «bin»."""
    pedida = extensao(nome)
    return next((e for e in EXTENSOES_GUARDADAS if e == pedida), "bin")


def guardar(pasta: Path, nome: str, dados: bytes) -> dict:
    """Grava os bytes na pasta da casa. Devolve caminho, nome (o de exibição),
    sha e tamanho. O arquivo em disco se chama `<sha256>.<extensão da lista>`:
    o mesmo conteúdo guardado duas vezes ocupa um arquivo só."""
    sha = hashlib.sha256(dados).hexdigest()
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"{sha}.{_extensao_da_casa(nome)}"
    novo = not destino.exists()
    if novo:
        destino.write_bytes(dados)
    exibido = ARQ.safe_component(Path(str(nome or "")).name, "arquivo")[:120]
    # `novo`: o arquivo nasceu agora. Só o que nasceu agora se apaga quando o
    # envio falha — o mesmo conteúdo pode ser o de outra mensagem.
    return {"caminho": str(destino.resolve()), "nome": exibido, "sha256": sha,
            "bytes": len(dados), "novo": novo}


def como_mostrar(mensagem: dict) -> str:
    """«foto», «audio», «video», «pdf», «baixar» ou "" (sem arquivo). Só calcula,
    a partir do nome GUARDADO — é o que a rota usa para servir."""
    if not mensagem.get("arquivo_caminho"):
        return ""
    ext = extensao(mensagem.get("arquivo_nome") or mensagem.get("arquivo_caminho"))
    if ext in FOTO:
        return "foto"
    if ext in AUDIO:
        return "audio"
    if ext in VIDEO:
        return "video"
    if ext == "pdf":
        return "pdf"
    return "baixar"


def tipo_para_servir(mensagem: dict) -> tuple[str, bool]:
    """(mime, em_linha). Só o que está em `MOSTRA_NA_TELA` abre na tela."""
    ext = extensao(mensagem.get("arquivo_nome") or mensagem.get("arquivo_caminho"))
    if ext in MOSTRA_NA_TELA:
        return MOSTRA_NA_TELA[ext], True
    return "application/octet-stream", False


# ------------------------------------------------------------- o que entra


def _soltar_presas(db: Any, *, agora: str) -> None:
    limite = (datetime.fromisoformat(str(agora)[:19]) - timedelta(minutes=PRESO_MINUTOS)
              ).strftime("%Y-%m-%dT%H:%M:%S")
    with db.transaction() as con:
        banco(con).escrever(
            "UPDATE wa_mensagem SET midia_situacao=NULL WHERE midia_situacao=%s "
            "AND (midia_desde IS NULL OR midia_desde < %s)", (WA.MIDIA_BAIXANDO, limite))


def baixar_pendentes(db: Any, *, pasta_arquivos: Path, agora: str,
                     limite: int = POR_VOLTA, https: Callable | None = None) -> dict:
    """Baixa e guarda os arquivos que os clientes mandaram. **FALA COM A REDE**,
    e nunca de dentro de uma transação. Devolve {"baixados", "erros",
    "adiados"} — adiado é o erro passageiro que volta à fila."""
    import wa_balcao as BALCAO
    _soltar_presas(db, agora=agora)
    inicio = (datetime.fromisoformat(str(agora)[:19]) - timedelta(days=DIAS_DA_META)
              ).strftime("%Y-%m-%dT%H:%M:%S")
    espera = (datetime.fromisoformat(str(agora)[:19])
              - timedelta(minutes=ESPERA_ENTRE_TENTATIVAS_MIN)).strftime("%Y-%m-%dT%H:%M:%S")
    with db.connect() as con:
        token = BALCAO.ler_config(con, WA.CHAVE_TOKEN)
        if not token:
            return {"baixados": 0, "erros": 0, "sem_token": True}
        candidatos = banco(con).ler(
            """SELECT id FROM wa_mensagem
                WHERE direcao='in' AND midia_id IS NOT NULL AND midia_id <> ''
                  AND midia_situacao IS NULL AND criado_em >= %s
                  AND (COALESCE(midia_tentativas, 0) = 0
                       OR midia_desde IS NULL OR midia_desde < %s)
                ORDER BY id LIMIT %s""", (inicio, espera, int(limite)))
    baixados = erros = adiados = 0
    for c in candidatos:
        with db.transaction() as con:
            pega = banco(con).escrever(
                """UPDATE wa_mensagem SET midia_situacao=%s, midia_desde=%s
                    WHERE id=%s AND midia_situacao IS NULL
                RETURNING id, midia_id, bruto_json, tipo, midia_tentativas""",
                (WA.MIDIA_BAIXANDO, agora, int(c["id"])))
        if not pega:
            continue                         # outra volta pegou primeiro
        m = dict(pega[0])
        try:
            dados, mime = baixar(token, m["midia_id"], https=https)
            salvo = guardar(pasta_do_mes(pasta_arquivos, agora), nome_do_arquivo(m, mime),
                            dados)
        except PASSAGEIROS as falha:
            tentativas = int(m.get("midia_tentativas") or 0) + 1
            if tentativas < TENTATIVAS_DA_MIDIA:
                with db.transaction() as con:
                    banco(con).escrever(
                        """UPDATE wa_mensagem SET midia_situacao=NULL, midia_desde=%s,
                                  midia_tentativas=%s WHERE id=%s""",
                        (agora, tentativas, int(m["id"])))
                LOG.info("o arquivo da mensagem %s volta à fila (tentativa %s): %s",
                         m["id"], tentativas, falha)
                adiados += 1
                continue
            with db.transaction() as con:
                banco(con).escrever(
                    """UPDATE wa_mensagem SET midia_situacao=%s, arquivo_erro=%s,
                              midia_tentativas=%s WHERE id=%s""",
                    (WA.MIDIA_ERRO, f"{str(falha)[:260]} ({tentativas} tentativas)",
                     tentativas, int(m["id"])))
            LOG.warning("o arquivo da mensagem %s não foi baixado: %s", m["id"], falha)
            erros += 1
            continue
        except MidiaErro as falha:
            with db.transaction() as con:
                banco(con).escrever(
                    "UPDATE wa_mensagem SET midia_situacao=%s, arquivo_erro=%s WHERE id=%s",
                    (WA.MIDIA_ERRO, str(falha)[:300], int(m["id"])))
            LOG.warning("o arquivo da mensagem %s não foi baixado: %s", m["id"], falha)
            erros += 1
            continue
        with db.transaction() as con:
            banco(con).escrever(
                """UPDATE wa_mensagem
                      SET midia_situacao=%s, arquivo_nome=%s, arquivo_caminho=%s,
                          arquivo_mime=%s, arquivo_bytes=%s, arquivo_sha256=%s,
                          arquivo_erro=NULL
                    WHERE id=%s""",
                (WA.MIDIA_OK, salvo["nome"], salvo["caminho"], mime, salvo["bytes"],
                 salvo["sha256"], int(m["id"])))
        baixados += 1
    return {"baixados": baixados, "erros": erros, "adiados": adiados}


def tentar_de_novo(con: Any, mensagem_id: int) -> bool:
    """Devolve a mensagem com erro à fila de baixar. ESCREVE."""
    linha = banco(con).escrever(
        """UPDATE wa_mensagem SET midia_situacao=NULL, arquivo_erro=NULL,
                  midia_tentativas=0
            WHERE id=%s AND midia_situacao=%s RETURNING id""",
        (int(mensagem_id), WA.MIDIA_ERRO))
    return bool(linha)


def bytes_guardados(mensagem: dict) -> tuple[bytes, str] | None:
    """(bytes, mime) do arquivo já guardado, se ele está lá e confere com o
    sha256. É o que poupa a transcrição de baixar o áudio uma segunda vez."""
    caminho = mensagem.get("arquivo_caminho")
    if not caminho:
        return None
    try:
        dados = Path(caminho).read_bytes()
    except OSError:
        return None
    if mensagem.get("arquivo_sha256") and \
            hashlib.sha256(dados).hexdigest() != mensagem["arquivo_sha256"]:
        return None
    return dados, str(mensagem.get("arquivo_mime") or "")


# ------------------------------------------------------------- o que sai


def conferir_envio(nome: str, tamanho: int) -> tuple[str, str]:
    """(tipo da Meta, mime) do arquivo que quem atende quer mandar, ou
    `MidiaErro` com o porquê. O tipo sai da EXTENSÃO, e não do que o navegador
    declarou."""
    ext = extensao(nome)
    if ext not in ENVIO_POR_EXTENSAO:
        aceitos = ", ".join(sorted(ENVIO_POR_EXTENSAO))
        raise MidiaErro(f"O WhatsApp não aceita «.{ext or '?'}» por aqui. Aceitos: {aceitos}.")
    tipo, mime, teto_mb = ENVIO_POR_EXTENSAO[ext]
    if tamanho <= 0:
        raise MidiaErro("O arquivo veio vazio.")
    if tamanho > teto_mb * 1024 * 1024:
        raise MidiaErro(f"Para «.{ext}» o WhatsApp aceita até {teto_mb} MB.")
    return tipo, mime


def montar_envio(con: Any, wa_id: str, tipo: str, midia_id: str, *, legenda: str = "",
                 nome: str = "") -> dict:
    """O pedido da mensagem com o arquivo já subido. SÓ LÊ. A legenda vai na
    foto, no vídeo e no documento; o áudio não aceita legenda."""
    import wa_balcao as BALCAO
    token = BALCAO.ler_config(con, WA.CHAVE_TOKEN)
    phone = BALCAO.ler_config(con, WA.CHAVE_PHONE)
    if not token or not phone:
        raise MidiaErro("Falta access_token ou phone_number_id na configuração.")
    bloco: dict = {"id": midia_id}
    legenda = (legenda or "").strip()
    if legenda and tipo in ("image", "video", "document"):
        bloco["caption"] = legenda[:1024]
    if tipo == "document" and nome:
        bloco["filename"] = Path(nome).name[:120]
    return {
        "url": f"https://graph.facebook.com/{GRAPH_VER}/{phone}/messages",
        "payload": {"messaging_product": "whatsapp", "to": str(wa_id), "type": tipo,
                    tipo: bloco},
        "headers": {"Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"},
    }
