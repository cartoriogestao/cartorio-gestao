"""O SELETOR DE API — quem responde, e em que formato se fala com ele.

O QUE ESTE MÓDULO É, E O QUE ELE NÃO É
    Ele é o **transporte** do agente: leva a conversa, traz a resposta, e
    traduz a chamada de ferramentas para o idioma de cada provedor. Ele não
    sabe o que é uma averbação nem o que é a CRA — quem monta o pedido é
    `agente.py`, e quem executa as ferramentas é `agente_ferramentas.py`.

    É a mesma separação de `selador_cliente.py`, e pelo mesmo motivo: quando o
    transporte sabe da regra, a regra passa a existir em dois lugares.

    A AJUDA TINHA UM TRANSPORTE SÓ DELA, e ele foi aposentado em 14/09/2026:
    este módulo faz o que o `claude_cliente.py` fazia, e faz para os dois.

SEM DEPENDÊNCIA NOVA
    `http.client`, `json` e `ssl`, da biblioteca padrão. **Uma dependência a
    mais é um jeito a mais de a instalação falhar num sábado** — é a decisão
    que a Ajuda já tinha tomado com o cliente próprio dela, e ela já se pagou.

AS DUAS FAMÍLIAS, E POR QUE ISSO IMPORTA
    Os provedores falam dois idiomas, e a diferença não é cosmética:

        anthropic · `system` fora das mensagens, resposta em `content[]`,
                    ferramenta em `tool_use`/`tool_result`, uso em
                    `input_tokens`/`output_tokens`
        openai    · `system` como mensagem, resposta em `choices[0].message`,
                    ferramenta em `tool_calls`/`role: tool`, uso em
                    `prompt_tokens`/`completion_tokens`

    **O que muda de um para o outro é o envelope, e não a conversa.** Por isso
    existe UM formato de conversa aqui dentro — documentado abaixo — e dois
    tradutores. Escrever o laço duas vezes daria duas versões divergentes do
    pedaço que decide «o agente já terminou?», que é o defeito que este projeto
    já pagou caro quando a régua é escrita em dois lugares.

A CONVERSA, E POR QUE ELA É UMA LISTA DE EVENTOS
    Um turno de agente não é uma mensagem: é texto, mais pedidos de
    ferramenta, mais resultados de ferramenta. Guardar isso no formato de um
    provedor obrigaria a convertê-lo no outro. Então a conversa é uma lista de
    eventos neutros:

        {"tipo": "user",      "texto": "…"}
        {"tipo": "assistant", "texto": "…", "chamadas": [{
                                  "id": "…", "nome": "…", "argumentos": {…}}]}
        {"tipo": "tool",      "resultados": [{
                                  "id": "…", "nome": "…", "conteudo": "…",
                                  "erro": false}]}

    `montar_pedido` traduz a lista inteira a cada chamada. Traduzir sempre a
    lista toda, em vez de mandar um delta, é o que permite retomar uma sessão
    interrompida sem guardar estado de provedor no banco.

A CHAVE NÃO ENTRA NO BANCO
    Ela mora no arquivo `agente.cred`, em `%PROGRAMDATA%\\CartorioGestao`, ao
    lado de `claude.cred` e de `selador.cred`. O banco viaja — vai no backup, e
    o backup já saiu da serventia. **Chave de API dentro dele é chave
    publicada.**

    E a chave da Anthropic tem DOIS lugares por compatibilidade: se
    `agente.cred` não tiver a dela, vale a `claude.cred` que a Ajuda já usa.
    Quem já configurou a ajuda não digita de novo — e não há duas verdades
    porque a ordem é declarada: o arquivo do agente manda.

O ENDEREÇO VEM DE TABELA, E NUNCA DE FORA
    `host`, `porta` e `caminho` saem do dicionário `PROVEDORES`, e nenhuma
    função aceita endereço por parâmetro. Um endereço que viesse da tela ou do
    modelo transformaria este módulo num cliente que fala com qualquer
    servidor — é o `post_de_teste_liberado` do webhook, na forma de transporte.
"""
from __future__ import annotations

import http.client
import json
import ssl
import time
from pathlib import Path
import re
from typing import Any

import ia_uso as USO

NOME_DO_ARQUIVO = "agente.cred"

# ONDE A AJUDA JÁ GUARDA A CHAVE DA ANTHROPIC. Lido só como compatibilidade, e
# depois do arquivo do agente — a ordem está no cabeçalho.
ARQUIVO_DA_AJUDA = "claude.cred"

PRAZO_PADRAO = 120        # segundos; um turno com ferramentas demora mais
TENTATIVAS = 2            # o laço já repete turnos; repetir aqui multiplicaria
LIMITE_DE_ENVIO = 900_000  # caracteres; acima disso é engano de quem montou

# AS FAMÍLIAS DE FORMATO. Nomear a família, em vez de repetir `if provedor ==`
# em cada canto, é o que faz o quinto provedor entrar sem tocar no laço.
ANTHROPIC, OPENAI = "anthropic", "openai"

PROVEDORES: dict[str, dict[str, Any]] = {
    "deepseek": {
        "nome": "DeepSeek",
        "familia": OPENAI,
        "host": "api.deepseek.com",
        "porta": 443,
        "caminho": "/chat/completions",
        "modelos": {"PADRAO": "deepseek-chat", "FORTE": "deepseek-reasoner"},
        # A FORMA DA CHAVE, POR PROVEDOR. Não é enfeite: quem cola o campo
        # errado — o nome do projeto, o e-mail da conta, meia chave — descobre
        # no primeiro pedido, com o balcão esperando, em vez de aqui.
        "prefixo": "sk-",
        "vitrine": "https://api.deepseek.com",
    },
    "claude": {
        "nome": "Claude (Anthropic)",
        "familia": ANTHROPIC,
        "host": "api.anthropic.com",
        "porta": 443,
        "caminho": "/v1/messages",
        "modelos": {"PADRAO": "claude-sonnet-5", "FORTE": "claude-opus-5"},
        "prefixo": "sk-",
        "vitrine": "https://api.anthropic.com",
        # A VERSÃO DA API DA ANTHROPIC vai em cabeçalho próprio. Não é
        # opcional: sem ela o serviço recusa.
        "cabecalho_de_versao": ("anthropic-version", "2023-06-01"),
    },
    "gpt": {
        "nome": "GPT (OpenAI)",
        "familia": OPENAI,
        "host": "api.openai.com",
        "porta": 443,
        "caminho": "/v1/chat/completions",
        "modelos": {"PADRAO": "gpt-4o-mini", "FORTE": "gpt-4o"},
        "prefixo": "sk-",
        "vitrine": "https://api.openai.com",
    },
    "grok": {
        "nome": "Grok (xAI)",
        "familia": OPENAI,
        "host": "api.x.ai",
        "porta": 443,
        "caminho": "/v1/chat/completions",
        "modelos": {"PADRAO": "grok-2-latest", "FORTE": "grok-2-latest"},
        "prefixo": "xai-",
        "vitrine": "https://api.x.ai",
    },
}

PADRAO = "deepseek"

# OS NOMES DOS MODELOS SÃO PADRÃO EDITÁVEL, E NÃO LEI.
#
# A tela mostra e deixa trocar. O nome de um modelo muda de trimestre — e um
# nome vencido dentro do código pararia o agente sem que ninguém tivesse feito
# nada de errado. A tabela acima é o ponto de partida; quem instala confere no
# painel do provedor e ajusta na tela.



def _sem_segredo(texto: str) -> str:
    """Tira chave/token do texto antes de mostrar ao balcao."""
    t = str(texto or "")
    t = re.sub(r"sk-[A-Za-z0-9_\-]{8,}", "[chave omitida]", t)
    t = re.sub(r"(?i)(api[_-]?key|authorization|bearer)\s*[:=]\s*\S+",
               r"\1=[omitido]", t)
    return t


class AgenteError(ValueError):
    """Falha de transporte, com a mensagem pronta para quem opera.

    `motivo` é o resumo de forma fixa que vai para o registro do uso de IA
    (`ia_uso`, LF01) — e só ele vai: a mensagem pode trazer de volta um pedaço
    do que o provedor recebeu. `recusado` separa o pedido que não chegou a sair
    (ou que o provedor recusou) da falha de rede ou de serviço.

    `enviado` diz se o pedido CHEGOU A SAIR (26/10/2026, para a cota do dia):
    False = falhou antes do envio (chave, tamanho, conexão recusada) e a vaga
    volta; True = saiu (o provedor respondeu, ou o prazo esgotou depois); None
    = não se sabe, e conta como saiu.
    """

    def __init__(self, mensagem: object = "", *, motivo: str = "",
                 recusado: bool = False, enviado: bool | None = None) -> None:
        super().__init__(_sem_segredo(str(mensagem or "")))
        self.motivo = motivo
        self.recusado = recusado
        self.enviado = enviado


# ----------------------------------------------------------- as credenciais


def _mesclar(destino: dict[str, str], origem: Any) -> None:
    """Copia para `destino` os pares com valor de verdade. Chave vazia não entra."""
    if isinstance(origem, dict):
        for chave, valor in origem.items():
            texto = str(valor or "").strip()
            if texto:
                destino[str(chave).strip().lower()] = texto


def _ler_json(caminho: Path) -> dict:
    """O JSON do arquivo, ou vazio. Arquivo ausente ou quebrado não estoura."""
    if not caminho.is_file():
        return {}
    try:
        achado = json.loads(caminho.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        return {}
    return achado if isinstance(achado, dict) else {}


def caminho_da_credencial(pasta_de_dados: Any) -> Path:
    """Onde as chaves do agente moram. Só calcula caminho."""
    return Path(pasta_de_dados) / NOME_DO_ARQUIVO


def chaves(pasta_de_dados: Any) -> dict[str, str]:
    """Todas as chaves gravadas, por provedor. **Só LÊ.**

    O arquivo do agente manda; o da Ajuda entra depois, e só para a Anthropic.
    """
    achadas: dict[str, str] = {}
    _mesclar(achadas, _ler_json(caminho_da_credencial(pasta_de_dados)))
    if "claude" not in achadas:
        da_ajuda = _ler_json(Path(pasta_de_dados) / ARQUIVO_DA_AJUDA)
        api_key = str(da_ajuda.get("api_key") or "").strip()
        if api_key:
            achadas["claude"] = api_key
    return achadas


def tem_chave(pasta_de_dados: Any, provedor: Any = None) -> bool:
    """**Só LÊ.** Com provedor, responde só por ele; sem, se há alguma."""
    gravadas = chaves(pasta_de_dados)
    if provedor:
        return bool(gravadas.get(str(provedor).strip().lower()))
    return any(gravadas.get(nome) for nome in PROVEDORES)


def credencial(pasta_de_dados: Any, provedor: Any) -> str:
    """A chave em claro. É o único lugar do sistema que a devolve.

    Quem chama isto está prestes a autenticar; qualquer outro uso é vazamento.
    """
    prov = normalizar_provedor(provedor)
    achada = chaves(pasta_de_dados).get(prov, "")
    if not achada:
        raise AgenteError(
            f"A chave do {PROVEDORES[prov]['nome']} ainda não foi informada. "
            f"Ela é gravada em {caminho_da_credencial(pasta_de_dados)}, fora do "
            f"banco — o banco vai no backup, e o backup sai da serventia. "
            f"Informe em Administrativo → Agente do sistema → "
            f"Configuração.", motivo="sem chave", recusado=True)
    return achada


def gravar_chave(pasta_de_dados: Any, provedor: Any, chave: Any) -> Path:
    """Grava ou apaga a chave de um provedor. **ESCREVE EM DISCO.**

    Chave vazia **apaga** a daquele provedor: é o único jeito de desligar um
    provedor sem deixar a credencial dele viva no disco.

    A gravação é atômica do ponto de vista de quem lê — escreve num arquivo ao
    lado e troca. Não há `with_suffix` aqui de propósito: `agente.cred` tem
    sufixo `.cred`, e `with_suffix(".cred.tmp")` levantaria `ValueError`.
    """
    prov = normalizar_provedor(provedor)
    texto = str(chave or "").strip()
    caminho = caminho_da_credencial(pasta_de_dados)

    # **A FORMA DA CHAVE É CONFERIDA AQUI, E ISTO VEIO DA AJUDA.** O cliente
    # que ela tinha recusava o que não começasse com «sk-», e a aposentadoria
    # dele ia deixar passar qualquer coisa — inclusive o e-mail da conta, que é
    # o engano mais comum de quem copia do painel errado. A conferência voltou
    # para o lugar onde os dois passam, e virou POR PROVEDOR: a chave do Grok
    # não começa com «sk-», e uma régua só estragaria a dele.
    #
    # **E É SÓ A FORMA.** A chave de verdade quem diz se vale é o provedor, no
    # primeiro turno — e é por isso que a mensagem manda conferir no painel, em
    # vez de afirmar que a chave está errada.
    if texto:
        prefixo = str(PROVEDORES[prov].get("prefixo") or "")
        if prefixo and not texto.startswith(prefixo):
            raise AgenteError(
                f"Isto não tem forma de chave do {PROVEDORES[prov]['nome']} — a "
                f"de lá começa com «{prefixo}». Confira se você copiou a chave "
                f"inteira do painel do provedor, e não o nome da conta nem o "
                f"nome do projeto. Campo vazio não passa por aqui: apagar é o "
                f"botão que diz que apaga.")

    # **O ARQUIVO É REESCRITO SÓ COM O QUE É DELE.** Se a chave da Anthropic
    # veio emprestada do `claude.cred`, a herança não se materializa aqui:
    # copiá-la criaria uma segunda verdade, e no dia em que alguém trocasse a
    # chave em Administrativo → Ajuda o agente continuaria autenticando
    # com a velha sem nada na tela dizendo isso.
    so_o_do_agente: dict[str, str] = {}
    _mesclar(so_o_do_agente, _ler_json(caminho))
    if prov == "claude" and not so_o_do_agente.get("claude"):
        so_o_do_agente.pop("claude", None)
    if texto:
        so_o_do_agente[prov] = texto
    else:
        so_o_do_agente.pop(prov, None)

    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.parent / (caminho.name + ".tmp")
    temporario.write_text(json.dumps(so_o_do_agente, ensure_ascii=False,
                                     indent=2), encoding="utf-8")
    temporario.replace(caminho)
    # O `.tmp` novo herda a ACE de Usuários da pasta; a chave do provedor
    # ficava legível até o próximo reinício (22/10/2026, M6).
    import centrais_cred as _CRED
    _CRED._so_do_servico(caminho)
    return caminho


def mascarar(valor: Any) -> str:
    """Mostra só os últimos 4. Nunca a chave inteira."""
    texto = str(valor or "").strip()
    if not texto:
        return ""
    if len(texto) <= 4:
        return "****"
    return "\u2022\u2022\u2022\u2022" + texto[-4:]


# ---------------------------------------------------------------- os nomes


def normalizar_provedor(provedor: Any) -> str:
    """O provedor, em minúsculas e existente. Recusa com a lista na mão."""
    nome = str(provedor or "").strip().lower() or PADRAO
    if nome not in PROVEDORES:
        raise AgenteError(
            f"Provedor desconhecido: {provedor!r}. Os que existem são "
            f"{', '.join(PROVEDORES)}.", motivo="provedor desconhecido",
            recusado=True)
    return nome


def modelo_de(provedor: Any, modelo: Any = None) -> str:
    """O nome do modelo pedido, ou o padrão do provedor. Só calcula."""
    prov = normalizar_provedor(provedor)
    escolhido = str(modelo or "").strip()
    return escolhido or PROVEDORES[prov]["modelos"]["PADRAO"]


def catalogo_para_tela(pasta_de_dados: Any) -> list[dict]:
    """O que a tela mostra: provedor, nome, modelo e se há chave. **Só LÊ.**"""
    gravadas = chaves(pasta_de_dados)
    do_agente = _ler_json(caminho_da_credencial(pasta_de_dados))
    saida = []
    for prov, dados in PROVEDORES.items():
        chave = gravadas.get(prov, "")
        saida.append({
            "id": prov,
            "nome": dados["nome"],
            "familia": dados["familia"],
            "endereco": dados["vitrine"],
            "modelos": dict(dados["modelos"]),
            "tem_chave": bool(chave),
            "mascarada": mascarar(chave),
            # A CHAVE EMPRESTADA É DITA EM VOZ ALTA. Sem isto, a tela diria que
            # o agente tem chave própria da Anthropic quando ele está usando a
            # da Ajuda — e a pessoa editaria o lugar errado.
            "vem_da_ajuda": bool(chave) and prov == "claude"
            and not do_agente.get("claude"),
        })
    return saida


# ------------------------------------------------ o envelope de cada família


def _ferramentas_anthropic(ferramentas: list[dict]) -> list[dict]:
    return [{"name": f["nome"], "description": f["descricao"],
             "input_schema": f["schema"]} for f in ferramentas]


def _ferramentas_openai(ferramentas: list[dict]) -> list[dict]:
    return [{"type": "function",
             "function": {"name": f["nome"], "description": f["descricao"],
                          "parameters": f["schema"]}} for f in ferramentas]


def _mensagens_anthropic(conversa: list[dict]) -> list[dict]:
    saida: list[dict] = []
    for evento in conversa:
        tipo = evento.get("tipo")
        if tipo == "user":
            # A PÁGINA DIGITALIZADA VAI COMO IMAGEM (07/10/2026, a leitura dos
            # anexos na revisão): `imagens` é uma lista de {"mime", "base64"},
            # e elas vão ANTES do texto, que é a pergunta sobre elas.
            # O DOCUMENTO INTEIRO VAI COMO DOCUMENTO (23/10/2026, o agente de
            # minutas): `documentos` é uma lista de {"mime", "base64", "titulo"}
            # — o PDF sobe como está, e o provedor lê o texto e a imagem de cada
            # página. Vão antes das imagens soltas e do texto, que é o pedido.
            conteudo: list[dict] = [
                {"type": "document",
                 "source": {"type": "base64", "media_type": doc["mime"],
                            "data": doc["base64"]},
                 **({"title": str(doc["titulo"])[:200]} if doc.get("titulo") else {})}
                for doc in evento.get("documentos") or []]
            conteudo += [
                {"type": "image",
                 "source": {"type": "base64", "media_type": img["mime"],
                            "data": img["base64"]}}
                for img in evento.get("imagens") or []]
            conteudo.append({"type": "text", "text": str(evento.get("texto") or "")})
            saida.append({"role": "user", "content": conteudo})
        elif tipo == "assistant":
            blocos: list[dict] = []
            if evento.get("texto"):
                blocos.append({"type": "text", "text": str(evento["texto"])})
            for chamada in evento.get("chamadas") or []:
                blocos.append({"type": "tool_use", "id": chamada["id"],
                               "name": chamada["nome"],
                               "input": chamada.get("argumentos") or {}})
            # A API recusa turno do assistente sem conteúdo. Acontece quando o
            # provedor devolve só ferramenta e nada de texto.
            if not blocos:
                blocos = [{"type": "text", "text": "(sem texto)"}]
            saida.append({"role": "assistant", "content": blocos})
        elif tipo == "tool":
            # **OS RESULTADOS VÃO NUM TURNO SÓ**, e não um por ferramenta: a
            # Anthropic exige que todo `tool_use` do turno anterior tenha o
            # `tool_result` dele no MESMO turno seguinte.
            blocos = []
            for resultado in evento.get("resultados") or []:
                bloco = {"type": "tool_result", "tool_use_id": resultado["id"],
                         "content": str(resultado.get("conteudo") or "")}
                if resultado.get("erro"):
                    bloco["is_error"] = True
                blocos.append(bloco)
            if blocos:
                saida.append({"role": "user", "content": blocos})
    return saida


def _mensagens_openai(conversa: list[dict], sistema: str) -> list[dict]:
    saida: list[dict] = []
    if sistema.strip():
        saida.append({"role": "system", "content": sistema})
    for evento in conversa:
        tipo = evento.get("tipo")
        if tipo == "user":
            if evento.get("imagens") or evento.get("documentos"):
                # Imagem só se manda pela família da Anthropic; aqui ela sumiria
                # calada, e a «transcrição» viria de uma página que não subiu.
                raise AgenteError("Este provedor não recebe imagem pelo sistema; "
                                  "a leitura de documento digitalizado usa o Claude.",
                                  motivo="imagem neste provedor", recusado=True)
            saida.append({"role": "user",
                          "content": str(evento.get("texto") or "")})
        elif tipo == "assistant":
            mensagem: dict[str, Any] = {
                "role": "assistant", "content": str(evento.get("texto") or "")}
            chamadas = evento.get("chamadas") or []
            if chamadas:
                mensagem["tool_calls"] = [
                    {"id": c["id"], "type": "function",
                     "function": {"name": c["nome"],
                                  "arguments": json.dumps(
                                      c.get("argumentos") or {},
                                      ensure_ascii=False)}}
                    for c in chamadas]
            saida.append(mensagem)
        elif tipo == "tool":
            for resultado in evento.get("resultados") or []:
                saida.append({"role": "tool", "tool_call_id": resultado["id"],
                              "content": str(resultado.get("conteudo") or "")})
    return saida


#: O QUE QUEM CHAMA PODE ACRESCENTAR AO CORPO, NA FAMÍLIA DA ANTHROPIC — e só
#: isto (23/10/2026, o agente de minutas). `output_config` leva o esforço e o
#: formato da resposta; `fallbacks` é o desvio do próprio provedor quando o
#: modelo recusa. Lista fechada de propósito: chave livre no corpo seria um
#: jeito de mudar o pedido por fora do que este módulo conhece.
EXTRAS_ACEITOS = ("output_config", "fallbacks")


def montar_pedido(provedor: Any, *, sistema: str, conversa: list[dict],
                  ferramentas: list[dict], modelo: Any = None,
                  maximo_de_saida: int = 2000, extras: dict | None = None,
                  betas: list[str] | None = None) -> dict:
    """O pedido inteiro, pronto para ir: endereço, corpo e cabeçalhos.

    Devolve o que já está pronto em vez de mandar direto: assim o teste confere
    o que sairia **sem abrir a rede** — a mesma ideia do envelope do selo.

    `extras` e `betas` só valem na família da Anthropic: noutro provedor eles
    são recusados, e não esquecidos — o esforço pedido que some calado faria a
    minuta sair de um modelo que pensou menos do que se disse.
    """
    prov = normalizar_provedor(provedor)
    dados = PROVEDORES[prov]
    escolhido = modelo_de(prov, modelo)
    extras = dict(extras or {})
    fora = sorted(set(extras) - set(EXTRAS_ACEITOS))
    if fora:
        raise AgenteError(f"Campo do pedido que este transporte não conhece: "
                          f"{', '.join(fora)}.", motivo="extra desconhecido",
                          recusado=True)
    if (extras or betas) and dados["familia"] != ANTHROPIC:
        raise AgenteError("Esforço, formato e desvio do pedido só existem no "
                          "Claude.", motivo="extra noutro provedor", recusado=True)

    if dados["familia"] == ANTHROPIC:
        corpo: dict[str, Any] = {
            "model": escolhido,
            "max_tokens": int(maximo_de_saida),
            "system": sistema,
            "messages": _mensagens_anthropic(conversa),
        }
        if ferramentas:
            corpo["tools"] = _ferramentas_anthropic(ferramentas)
        corpo.update(extras)
    else:
        corpo = {
            "model": escolhido,
            "max_tokens": int(maximo_de_saida),
            "messages": _mensagens_openai(conversa, sistema),
        }
        if ferramentas:
            corpo["tools"] = _ferramentas_openai(ferramentas)
            corpo["tool_choice"] = "auto"

    return {"provedor": prov, "modelo": escolhido, "familia": dados["familia"],
            "host": dados["host"], "porta": int(dados["porta"]),
            "caminho": dados["caminho"],
            "cabecalho_de_versao": dados.get("cabecalho_de_versao"),
            "betas": [str(b) for b in (betas or [])],
            "corpo": corpo}


def _cabecalhos(pedido: dict, chave: str) -> dict[str, str]:
    """Os cabeçalhos de autenticação da família. A chave não é logada aqui."""
    cabecalhos = {"content-type": "application/json",
                  "accept": "application/json"}
    if pedido["familia"] == ANTHROPIC:
        cabecalhos["x-api-key"] = chave
    else:
        cabecalhos["authorization"] = f"Bearer {chave}"
    versao = pedido.get("cabecalho_de_versao")
    if versao:
        cabecalhos[versao[0]] = versao[1]
    if pedido.get("betas"):
        cabecalhos["anthropic-beta"] = ",".join(pedido["betas"])
    return cabecalhos


# ------------------------------------------------ a leitura, por família


def _sem_argumentos(bruto: Any) -> dict:
    """Os argumentos vêm em JSON-escapado. JSON quebrado não derruba o turno.

    Devolver vazio em vez de estourar é o que transforma «o modelo escreveu um
    JSON inválido» numa mensagem de falta de argumento — que o modelo lê e
    corrige —, e não num turno perdido.
    """
    if isinstance(bruto, dict):
        return bruto
    texto = str(bruto or "").strip()
    if not texto:
        return {}
    try:
        achado = json.loads(texto)
    except ValueError:
        return {}
    return achado if isinstance(achado, dict) else {}


def ler_resposta(provedor: Any, bruto: bytes) -> dict:
    """A resposta em forma neutra: texto, chamadas, uso e motivo de parada.

    **NÃO INTERPRETA CONTEÚDO.** Argumento fora do esquema não é recusado aqui:
    quem recusa é `agente_ferramentas`, que é quem conhece o esquema — duas
    recusas seriam a segunda régua divergindo da primeira.
    """
    prov = normalizar_provedor(provedor)
    try:
        dados = json.loads(bruto.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as erro:
        raise AgenteError(
            "A resposta veio num formato que eu não entendi. Tente de novo.",
            motivo="resposta ilegível") from erro
    if not isinstance(dados, dict):
        raise AgenteError("A resposta veio vazia. Tente de novo.",
                          motivo="resposta vazia")

    if PROVEDORES[prov]["familia"] == ANTHROPIC:
        blocos = dados.get("content") or []
        texto = "\n".join(
            str(b.get("text") or "") for b in blocos
            if isinstance(b, dict) and b.get("type") == "text").strip()
        chamadas = [{"id": str(b.get("id") or ""), "nome": str(b.get("name") or ""),
                     "argumentos": _sem_argumentos(b.get("input"))}
                    for b in blocos
                    if isinstance(b, dict) and b.get("type") == "tool_use"]
        uso = dados.get("usage") or {}
        entrada = int(uso.get("input_tokens") or 0)
        saida = int(uso.get("output_tokens") or 0)
        parou = str(dados.get("stop_reason") or "")
    else:
        escolhas = dados.get("choices") or []
        if not escolhas:
            raise AgenteError(
                "A resposta do provedor veio sem escolha nenhuma. Tente de novo.",
                motivo="resposta vazia")
        escolha = escolhas[0] or {}
        mensagem = escolha.get("message") or {}
        texto = str(mensagem.get("content") or "").strip()
        chamadas = [{"id": str(tc.get("id") or ""),
                     "nome": str((tc.get("function") or {}).get("name") or ""),
                     "argumentos": _sem_argumentos(
                         (tc.get("function") or {}).get("arguments"))}
                    for tc in (mensagem.get("tool_calls") or [])
                    if isinstance(tc, dict)]
        uso = dados.get("usage") or {}
        entrada = int(uso.get("prompt_tokens") or 0)
        saida = int(uso.get("completion_tokens") or 0)
        parou = str(escolha.get("finish_reason") or "")

    return {"texto": texto, "chamadas": chamadas, "parou": parou,
            "entrada": entrada, "saida": saida,
            "modelo": str(dados.get("model") or "")}


def _explicar(provedor: str, situacao: int, bruto: bytes) -> str:
    """A falha em português, dizendo o que fazer — e não o código cru."""
    nome = PROVEDORES[provedor]["nome"]
    detalhe = ""
    try:
        erro = json.loads(bruto.decode("utf-8"))
        if isinstance(erro, dict):
            detalhe = str((erro.get("error") or {}).get("message")
                          or erro.get("message") or "")
    except (UnicodeDecodeError, ValueError):
        detalhe = ""
    if situacao == 401:
        return (f"A chave do {nome} não foi aceita. Confira em Administrativo "
                f"→ Agente do sistema → Configuração se ela foi "
                f"copiada inteira e se ainda está ativa no painel do provedor.")
    if situacao == 402:
        return (f"O {nome} recusou por falta de crédito na conta. O agente não "
                f"gasta mais nada até a conta ser reforçada.")
    if situacao == 403:
        return f"A chave do {nome} não tem permissão para esta chamada."
    if situacao == 404:
        return (f"O {nome} não conhece o modelo pedido. Confira o nome do "
                f"modelo na tela de configuração do agente.")
    if situacao == 429:
        return (f"O {nome} recebeu pedidos demais e pediu para esperar. Tente "
                f"de novo daqui a pouco.")
    if situacao == 400:
        return f"O {nome} recusou o pedido. {detalhe}".strip()
    if situacao and situacao >= 500:
        return (f"O {nome} está fora do ar no momento. Isso não impede nenhum "
                f"ato: siga o atendimento e tente de novo depois.")
    if situacao == 0:
        return ("Não consegui alcançar a internet a partir desta máquina. "
                "Confira a conexão — o resto do sistema não depende dela.")
    return f"O {nome} respondeu HTTP {situacao}. {detalhe}".strip()


def _nao_consegui(prov: str, ultimo: str, *, corpo: bytes, prazo: int,
                  segundos: float) -> str:
    """A frase de quando a conversa não chegou a acontecer — e ela MEDE.

        **O PROBLEMA #74 É ESTA FRASE, E O QUE FALTAVA NELA.** O relato foi «a
        conversa demorou e deu timeout», e a mensagem de então dizia só que não
        conseguiu falar com o provedor **depois de 2 tentativas** — sem o tempo,
        sem o tamanho do que subiu e sem separar uma causa da outra. Quem fosse
        procurar teria de medir tudo de novo, e a resposta mais provável ficava
        escondida: o MAIOR ponto de chamada daquela sessão era o do passo 106, e
        subia com **256.965 caracteres** (medido nos 32 pontos de chamada dela por
        `tools/medir_o_peso_da_conversa.py`, que só lê). **O mesmo ponto**, com a
        poda, cai a **88.622** — **65,5 % menor**. E a comparação é no mesmo ponto
        de propósito: depois da poda o maior envio passa a ser outro, de 89.077, e
        cruzar 256.965 com 89.077 daria 65,3 % — porcentagem entre dois pontos
        diferentes, que não descreve nem um nem outro.

    Então a frase passou a levar: quantos KB subiram, qual era o prazo, quantos
    segundos se esperou no total, e qual dos dois casos é — **prazo estourado**
    ou **a máquina não alcançou a rede**. As providências são diferentes, e
    quem lê a tela decide sem abrir um terminal.

    **E ELA NÃO INVENTA CAUSA QUANDO O ERRO NÃO É DE TEMPO.** Se o que voltou
    foi «Name or service not known», dizer «estourou o prazo» seria carimbo que
    mente; a frase mostra o erro do sistema e diz o que ele é.
    """
    nome = PROVEDORES[prov]["nome"]
    kb = max(1, len(corpo) // 1024)
    estourou = "timed out" in ultimo.lower() or "timeout" in ultimo.lower()
    if estourou:
        porque = (f"O prazo de cada tentativa é de {prazo} s, e a conversa que "
                  f"subiu tem {kb} KB — quando ela é grande, o provedor demora "
                  f"mais do que isso para começar a responder. Tente de novo: "
                  f"a próxima tentativa pode passar. Se repetir sempre, comece "
                  f"uma sessão nova — ela leva só o que interessa, porque a "
                  f"poda não reenvia o que já foi lido por inteiro.")
    else:
        porque = (f"O erro da máquina foi «{ultimo}». Conversa de {kb} KB, "
                  f"prazo de {prazo} s por tentativa.")
    return (f"Não consegui falar com o {nome} depois de {TENTATIVAS} tentativas "
            f"({segundos:.0f} s no total). {porque} Isso não impede nenhum ato: "
            f"siga o atendimento, e tente de novo daqui a pouco.")


def _turno(pasta_de_dados: Any, *, provedor: Any, sistema: str,
           conversa: list[dict], ferramentas: list[dict],
           modelo: Any = None, maximo_de_saida: int = 2000,
           prazo: int = PRAZO_PADRAO, extras: dict | None = None,
           betas: list[str] | None = None,
           limite_de_envio: int | None = None) -> dict:
    """O turno em si, sem o registro — quem chama é `conversar`.

    `limite_de_envio` existe para quem manda DOCUMENTO: um PDF digitalizado em
    base64 passa fácil dos 900 mil caracteres que bastam a uma conversa, e o
    teto do provedor é de 32 MB por pedido. Quem o aumenta declara por quê.
    """
    try:
        prov = normalizar_provedor(provedor)
        pedido = montar_pedido(prov, sistema=sistema, conversa=conversa,
                               ferramentas=ferramentas, modelo=modelo,
                               maximo_de_saida=maximo_de_saida, extras=extras,
                               betas=betas)
        corpo = json.dumps(pedido["corpo"], ensure_ascii=False).encode("utf-8")
        if len(corpo) > (limite_de_envio or LIMITE_DE_ENVIO):
            raise AgenteError(
                f"A conversa ficou grande demais ({len(corpo) // 1024} KB). Isso "
                f"quase sempre é engano de quem a montou — reduza o que vai junto "
                f"e comece uma sessão nova.", motivo="conversa grande demais",
                recusado=True)
        # A CREDENCIAL É PEDIDA AQUI, e não antes: assim uma sessão que só lê o
        # histórico não precisa de chave nenhuma para existir.
        cabecalhos = _cabecalhos(pedido, credencial(pasta_de_dados, prov))
    except AgenteError as falha:
        # NADA SAIU AINDA: a recusa aqui é antes de qualquer conexão.
        falha.enviado = False
        raise

    # O RELÓGIO COMEÇA AQUI, E ELE EXISTE PARA A MENSAGEM DO FIM — problema #74.
    # «Não consegui falar com o provedor» não dizia se o problema foi a rede ou o
    # TAMANHO do que subiu, e as duas coisas pedem providências diferentes. Com o
    # tempo decorrido e os KB enviados na frase, a próxima pessoa responde a
    # pergunta olhando a tela, em vez de ir medir de novo.
    inicio = time.time()
    ultimo = ""
    # O PEDIDO SAIU? `request` só volta depois de mandar o corpo inteiro; se
    # qualquer tentativa chegou até ali, o provedor pode ter processado.
    saiu = False
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            conexao = http.client.HTTPSConnection(
                pedido["host"], pedido["porta"], timeout=prazo,
                context=ssl.create_default_context())
            try:
                conexao.request("POST", pedido["caminho"], body=corpo,
                                headers=cabecalhos)
                saiu = True
                resposta = conexao.getresponse()
                bruto = resposta.read()
                situacao = int(resposta.status)
            finally:
                conexao.close()
        except OSError as erro:
            ultimo = f"{type(erro).__name__}: {erro}"
            situacao, bruto = 0, b""

        if situacao == 200:
            lida = ler_resposta(prov, bruto)
            lida["provedor"] = prov
            return lida

        # 429 e 5xx melhoram repetindo; o resto não.
        if situacao and situacao not in (429, 500, 502, 503, 504):
            raise AgenteError(_explicar(prov, situacao, bruto),
                              motivo=f"HTTP {situacao}",
                              recusado=400 <= situacao < 500, enviado=True)
        ultimo = ultimo or _explicar(prov, situacao, bruto)
        if tentativa < TENTATIVAS:
            time.sleep(2 * tentativa)

    if situacao:
        motivo = f"HTTP {situacao}"
    elif "timed out" in ultimo.lower() or "timeout" in ultimo.lower():
        motivo = "sem resposta no prazo"
    else:
        motivo = "sem rede"
    # PRAZO ESGOTADO CONTA COMO ENVIADO, mesmo na conexão: não se sabe se o
    # provedor recebeu, e a vaga fica gasta (reconferência de 26/10/2026).
    raise AgenteError(_nao_consegui(prov, ultimo, corpo=corpo, prazo=prazo,
                                    segundos=time.time() - inicio),
                      motivo=motivo,
                      enviado=saiu or motivo == "sem resposta no prazo")


def conversar(pasta_de_dados: Any, *, provedor: Any, sistema: str,
              conversa: list[dict], ferramentas: list[dict],
              modelo: Any = None, maximo_de_saida: int = 2000,
              prazo: int = PRAZO_PADRAO, modulo: str = "",
              finalidade: str = "", usuario: str = "", atribuicao: str = "",
              referencia: str = "", mascarado: bool | None = None,
              extras: dict | None = None, betas: list[str] | None = None,
              limite_de_envio: int | None = None) -> dict:
    """Um turno. **FALA COM A REDE** e devolve a resposta em forma neutra.

    **NÃO RECEBE `con`, E ISSO É DE PROPÓSITO** — a mesma assinatura de
    `ato_selado.obter_selo` e do antigo `claude_cliente.perguntar`, pelo mesmo
    motivo:
    assim não há como chamá-la de dentro de uma transação sem reparar no que
    está fazendo. Um turno leva dezenas de segundos, e dentro do
    `BEGIN IMMEDIATE` poria a casa inteira no `busy_timeout`.

    **E CADA TURNO FICA REGISTRADO** (LF01 — Código de Normas do MA, arts.
    170, § 4º, e 176): quando, de onde (`modulo`), para quê (`finalidade`, o
    código de `ia_catalogo`), quem, em que atribuição, sobre qual registro
    (`referencia`, «tabela:id»), se o que subiu ia mascarado, quantos tokens e
    como terminou. Quem chama diz esses dados; o transporte grava, depois da
    resposta, numa conexão própria — e **nada do texto que foi ou voltou**.
    Registro que não grava vai para o log e não derruba o turno
    (`ia_uso.registrar`).
    """
    registro = {"modulo": modulo, "finalidade": finalidade, "usuario": usuario,
                "atribuicao": atribuicao, "referencia": referencia,
                "mascarado": mascarado,
                "provedor": str(provedor or "").strip().lower() or PADRAO,
                "modelo": str(modelo or "").strip()}
    try:
        registro["modelo"] = modelo_de(provedor, modelo)
    except AgenteError:
        pass
    # A COTA DO DIA SE RESERVA AQUI, ANTES DA REDE (26/10/2026, achado
    # transversal 3 da revisão de segurança): o chamador que esqueceu de
    # conferir o teto também para, e duas chamadas ao mesmo tempo não passam
    # pela última vaga. Reserva que não pôde ser conferida também para (falha
    # fechada). A vaga só volta se o pedido NÃO SAIU (`AgenteError.enviado`).
    try:
        reserva = USO.reservar(pasta_de_dados, finalidade)
    except USO.TetoAtingido as teto:
        motivo = ("cota indisponível" if isinstance(teto, USO.ReservaIndisponivel)
                  else "teto do dia")
        USO.registrar(pasta_de_dados, **registro, resultado=USO.RECUSADO,
                      erro=motivo)
        raise AgenteError(str(teto), motivo=motivo, recusado=True,
                          enviado=False) from teto
    try:
        lida = _turno(pasta_de_dados, provedor=provedor, sistema=sistema,
                      conversa=conversa, ferramentas=ferramentas,
                      modelo=modelo, maximo_de_saida=maximo_de_saida,
                      prazo=prazo, extras=extras, betas=betas,
                      limite_de_envio=limite_de_envio)
    except AgenteError as falha:
        if falha.enviado is False:
            USO.devolver(pasta_de_dados, reserva)
        else:
            USO.consumida_sem_resposta(reserva, falha.motivo or "falha do transporte")
        USO.registrar(pasta_de_dados, **registro,
                      resultado=USO.RECUSADO if falha.recusado else USO.ERRO,
                      erro=falha.motivo or "falha do transporte")
        raise
    except Exception as falha:
        # Falha que não se sabe onde aconteceu conta como enviada.
        USO.consumida_sem_resposta(reserva, type(falha).__name__)
        USO.registrar(pasta_de_dados, **registro, resultado=USO.ERRO,
                      erro=type(falha).__name__)
        raise
    registro["modelo"] = lida.get("modelo") or registro["modelo"]
    USO.registrar(pasta_de_dados, **registro, resultado=USO.OK,
                  tokens_entrada=lida.get("entrada") or 0,
                  tokens_saida=lida.get("saida") or 0)
    return lida
