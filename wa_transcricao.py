"""O áudio do cliente no WhatsApp: baixar da Meta e transcrever.

    «TRANSCREVER ÁUDIO do cliente (para a IA e para quem atende)» — decisão do
    oficial, 26/10/2026, um dos quatro casos em que a IA age sozinha.

POR QUE A OPENAI (O PROVEDOR «gpt» DA CASA), E O MODELO `whisper-1`
    Dos quatro provedores que a casa já conhece (`agente_provedores.
    PROVEDORES`), só a OpenAI tem serviço de transcrição de áudio: o Claude, o
    DeepSeek e o Grok recebem texto (e imagem), e não áudio. Usar a OpenAI não
    pede credencial nova nem arquivo novo — a chave é a do provedor «gpt», em
    `agente.cred`, fora do banco, onde as outras já moram — nem dependência
    nova: o pedido é um `multipart/form-data` montado com a biblioteca padrão.

    O modelo padrão é `whisper-1` porque é o que devolve a DURAÇÃO do áudio na
    resposta (`response_format=verbose_json`): o custo por minuto que a decisão
    manda registrar sai do número que o próprio provedor mediu, e não de uma
    estimativa nossa. O modelo e o preço por minuto são configuração da tela
    (`wa_schema.CHAVE_AUDIO_MODELO`, `CHAVE_AUDIO_PRECO_MINUTO`): o preço padrão
    (`PRECO_PADRAO_POR_MINUTO`) é o da tabela pública da OpenAI que eu conhecia
    — A CONFERIR no painel do provedor, e por isso editável.

O QUE SAI DA SERVENTIA, E É DITO NA TELA
    O ÁUDIO INTEIRO vai à OpenAI: áudio não se mascara. A transcrição que volta
    passa pela máscara (`ajuda_privacidade`) antes de ir ao modelo que responde
    o cliente — é o `wa_atendente` quem faz isso. O registro do uso de IA
    (`ia_uso`) marca `mascarado=False` nesta chamada, que é a verdade.

ESTE MÓDULO É TRANSPORTE (`ia_catalogo.TRANSPORTES`)
    `transcrever` grava a linha de `ia_uso` como `agente_provedores.conversar`
    grava a dele: quem chama diz a finalidade e o módulo; o transporte registra,
    e NUNCA o conteúdo. Não recebe `con`, de propósito — fala com a rede, e não
    pode ser chamado de dentro de uma transação sem que se perceba.

O ENDEREÇO VEM DE TABELA, E NUNCA DE FORA
    A OpenAI é `api.openai.com`, escrito aqui. O endereço da mídia vem da Graph
    (é ela que diz onde o arquivo está), e por isso ele é CONFERIDO antes de o
    token da Meta ir junto: só HTTPS, e só nos domínios da própria Meta
    (`DOMINIOS_DA_MIDIA`). Sem isso, uma resposta forjada mandaria o token da
    casa para quem a forjou.
"""
from __future__ import annotations

import http.client
import json
import ssl
import uuid
from typing import Any, Callable
from urllib.parse import urlsplit

import agente_provedores as PROV
import ia_uso as USO

GRAPH_HOST = "graph.facebook.com"
GRAPH_VER = "v21.0"
OPENAI_HOST = "api.openai.com"
OPENAI_CAMINHO = "/v1/audio/transcriptions"
PROVEDOR = "gpt"
MODELO_PADRAO = "whisper-1"
PRECO_PADRAO_POR_MINUTO = 0.006     # US$ — A CONFERIR na tabela da OpenAI
PRAZO = 60
# O WhatsApp aceita áudio de até 16 MB; acima disso é engano, e não cliente.
TETO_DE_BYTES = 16 * 1024 * 1024
DOMINIOS_DA_MIDIA = ("fbsbx.com", "facebook.com", "fbcdn.net", "whatsapp.net")


class TranscricaoErro(ValueError):
    """O áudio não pôde ser baixado ou transcrito. Mensagem pronta para a tela."""


def _https(host: str, metodo: str, caminho: str, *, corpo: bytes | None = None,
           cabecalhos: dict | None = None, prazo: int = PRAZO) -> tuple[int, bytes]:
    """FALA COM A REDE. Isolado para os testes trocarem por um falso."""
    con = http.client.HTTPSConnection(host, 443, timeout=prazo,
                                      context=ssl.create_default_context())
    try:
        con.request(metodo, caminho, body=corpo, headers=cabecalhos or {})
        resp = con.getresponse()
        return int(resp.status), resp.read(TETO_DE_BYTES + 1)
    finally:
        con.close()


def _midia_e_da_meta(url: str) -> tuple[str, str]:
    """(host, caminho) do endereço da mídia, se ele é HTTPS e da Meta."""
    partes = urlsplit(str(url or ""))
    host = (partes.hostname or "").lower()
    if partes.scheme != "https" or not any(
            host == d or host.endswith("." + d) for d in DOMINIOS_DA_MIDIA):
        raise TranscricaoErro(
            "A Graph indicou um endereço de mídia fora da Meta; o áudio não foi "
            "baixado e o token não saiu daqui.")
    caminho = partes.path or "/"
    if partes.query:
        caminho += "?" + partes.query
    return host, caminho


def baixar_audio(token: str, midia_id: str, *,
                 https: Callable | None = None) -> tuple[bytes, str]:
    """(bytes, mime) do áudio. FALA COM A REDE (a Graph, duas vezes)."""
    if not token:
        raise TranscricaoErro("Falta o access_token da Meta na configuração.")
    if not str(midia_id or "").strip():
        raise TranscricaoErro("A mensagem não traz o id do áudio.")
    fn = https or _https
    cab = {"Authorization": f"Bearer {token}"}
    status, bruto = fn(GRAPH_HOST, "GET", f"/{GRAPH_VER}/{midia_id}",
                       cabecalhos=cab)
    if status != 200:
        raise TranscricaoErro(f"A Graph não entregou o endereço do áudio "
                              f"(HTTP {status}).")
    try:
        info = json.loads(bruto.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as erro:
        raise TranscricaoErro("A Graph respondeu num formato que eu não "
                              "entendi.") from erro
    host, caminho = _midia_e_da_meta(info.get("url"))
    status, audio = fn(host, "GET", caminho, cabecalhos=cab)
    if status != 200:
        raise TranscricaoErro(f"A Graph não entregou o áudio (HTTP {status}).")
    if len(audio) > TETO_DE_BYTES:
        raise TranscricaoErro("O áudio passa de 16 MB e não foi transcrito.")
    mime = str(info.get("mime_type") or "audio/ogg").split(";")[0].strip()
    return audio, mime


def _multipart(campos: dict, arquivo: bytes, nome: str, mime: str) -> tuple[bytes, str]:
    fronteira = "cg" + uuid.uuid4().hex
    partes: list[bytes] = []
    for chave, valor in campos.items():
        partes.append(
            f"--{fronteira}\r\nContent-Disposition: form-data; name=\"{chave}\""
            f"\r\n\r\n{valor}\r\n".encode("utf-8"))
    partes.append(
        f"--{fronteira}\r\nContent-Disposition: form-data; name=\"file\"; "
        f"filename=\"{nome}\"\r\nContent-Type: {mime}\r\n\r\n".encode("utf-8"))
    partes.append(arquivo)
    partes.append(f"\r\n--{fronteira}--\r\n".encode("utf-8"))
    return b"".join(partes), f"multipart/form-data; boundary={fronteira}"


_EXTENSAO = {"audio/ogg": "ogg", "audio/mpeg": "mp3", "audio/mp4": "m4a",
             "audio/aac": "aac", "audio/amr": "amr", "audio/wav": "wav",
             "audio/webm": "webm"}


def custo_do_audio(segundos: float, preco_por_minuto: float | None) -> float | None:
    """US$ do áudio pelo preço por minuto. Sem preço, None — e a tela diz que
    não sabe, em vez de um zero que afirmaria «não custou nada»."""
    if preco_por_minuto is None:
        return None
    return round(max(0.0, float(segundos or 0)) / 60.0 * float(preco_por_minuto), 6)


def transcrever(pasta_de_dados: Any, audio: bytes, mime: str, *,
                modelo: str = "", preco_por_minuto: float | None = None,
                modulo: str = "", finalidade: str = "", usuario: str = "",
                referencia: str = "",
                https: Callable | None = None) -> dict:
    """O texto do áudio. **FALA COM A REDE** e registra o uso em `ia_uso`.

    Devolve {"texto", "segundos", "custo_usd", "modelo", "provedor"}."""
    escolhido = str(modelo or "").strip() or MODELO_PADRAO
    registro = {"modulo": modulo, "finalidade": finalidade, "usuario": usuario,
                "referencia": referencia, "mascarado": False,
                "provedor": PROVEDOR, "modelo": escolhido}
    try:
        chave = PROV.credencial(pasta_de_dados, PROVEDOR)
    except PROV.AgenteError as falha:
        USO.registrar(pasta_de_dados, **registro, resultado=USO.RECUSADO,
                      erro="sem chave")
        raise TranscricaoErro(
            "A transcrição usa a chave da OpenAI (provedor «GPT»), e ela ainda "
            "não foi informada em Administrativo → Agente do sistema → "
            "Configuração.") from falha
    mime = (mime or "audio/ogg").split(";")[0].strip()
    corpo, tipo = _multipart({"model": escolhido, "language": "pt",
                              "response_format": "verbose_json"},
                             audio, f"audio.{_EXTENSAO.get(mime, 'ogg')}", mime)
    fn = https or _https
    try:
        status, bruto = fn(OPENAI_HOST, "POST", OPENAI_CAMINHO, corpo=corpo,
                           cabecalhos={"Authorization": f"Bearer {chave}",
                                       "Content-Type": tipo})
    except OSError as falha:
        USO.registrar(pasta_de_dados, **registro, resultado=USO.ERRO,
                      erro="sem rede")
        raise TranscricaoErro("Não consegui falar com a OpenAI para transcrever "
                              "o áudio. Ele fica para quem atende ouvir.") from falha
    if status != 200:
        USO.registrar(pasta_de_dados, **registro,
                      resultado=USO.RECUSADO if 400 <= status < 500 else USO.ERRO,
                      erro=f"HTTP {status}")
        raise TranscricaoErro(f"A OpenAI recusou a transcrição (HTTP {status}).")
    try:
        dados = json.loads(bruto.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as erro:
        USO.registrar(pasta_de_dados, **registro, resultado=USO.ERRO,
                      erro="resposta ilegível")
        raise TranscricaoErro("A transcrição voltou num formato que eu não "
                              "entendi.") from erro
    segundos = float(dados.get("duration") or 0)
    USO.registrar(pasta_de_dados, **registro, resultado=USO.OK)
    return {"texto": str(dados.get("text") or "").strip(), "segundos": segundos,
            "custo_usd": custo_do_audio(segundos, preco_por_minuto),
            "modelo": escolhido, "provedor": PROVEDOR}
