"""Os MODELOS da Meta no WhatsApp — o único jeito de a casa INICIAR conversa.

O QUE FALTAVA (revisão de 27/10/2026)
    Nenhum código mandava `"type": "template"`: `wa_balcao.montar_envio` só
    sabe texto livre, e a Meta só aceita texto livre DENTRO da janela de 24 h
    aberta pela última mensagem do cliente. Por isso três coisas ficavam
    paradas: os avisos de andamento por WhatsApp («não configurado»), o convite
    da pesquisa por WhatsApp (na fila para sempre) e, no balcão, a resposta que
    sai depois das 24 h (a Meta recusa).

OS CINCO MODELOS (categoria Utilidade, idioma pt_BR)
    Foram criados na conta WhatsApp da serventia e esperam a aprovação da Meta.
    Os nomes e as variáveis são EXATAMENTE estes, e a ordem das variáveis é a
    do corpo aprovado ({{1}}, {{2}}, {{3}}):

        cartorio_exigencia            {{1}} cartório · {{2}} protocolo
        cartorio_pronto_retirar       {{1}} cartório · {{2}} protocolo
        cartorio_prenotacao_vencendo  {{1}} cartório · {{2}} prenotação · {{3}} data
        cartorio_pesquisa_satisfacao  {{1}} cartório · {{2}} protocolo · {{3}} link
        cartorio_retomar_atendimento  {{1}} cartório

    O {{1}} é o COMPLEMENTO que vem depois da palavra «Cartório» no corpo
    («Cartório {{1}}: …») — por exemplo «de Exemplo». Ele mora na configuração
    `nome_no_modelo` (`wa_config`); vazia, sai da cidade da serventia
    («de <cidade>»), e, sem cidade, do nome da serventia (o que vem depois do
    último « de »). Sem nenhum dos dois, o envio é RECUSADO antes da rede: um
    modelo que dissesse «Cartório NOME DA SERVENTIA» é pior que nenhum.

    Os NOMES ficam na configuração (`modelo_*`, em `wa_config`), com o padrão
    acima: se a Meta pedir outro nome na aprovação, o ADMIN troca na tela, sem
    versão nova. Nome vazio = o padrão.

O INTERRUPTOR NASCE DESLIGADO
    `modelos_aprovados` em `wa_config`. Enquanto ele estiver desligado, NADA
    muda: o aviso de andamento continua «não configurado» com a mesma frase, o
    convite por WhatsApp continua na fila, e o balcão não mostra o botão de
    reabrir. Quem liga é o ADMIN, na tela de configuração do WhatsApp, quando a
    Meta aprovar os cinco.

A CONFERÊNCIA VEM ANTES DA REDE
    `montar_envio_modelo` recusa, sem falar com a Meta: modelo desconhecido,
    nome fora da regra da Meta, quantidade errada de variáveis, variável vazia,
    variável com quebra de linha, tabulação ou mais de quatro espaços seguidos
    (a Meta recusa), e — a regra da casa para o que sai sozinho — variável com
    CPF, CNPJ, valor em dinheiro, «R$», «pix» ou e-mail. Cada variável tem
    ainda a régua do que ela é: o número só tem dígitos, ponto, barra e hífen
    (não cabe nome de pessoa nem teor), a data é dd/mm/aaaa, o link é https://.

    A recusa é `ModeloRecusado`, que é `wa_balcao.EnvioErro` (a rota que já
    apanha o erro de envio apanha este) e é `ValueError` (erro de regra, com a
    frase pronta para o balcão).

O TELEFONE VAI COM O 55
    `telefone_e164` normaliza o telefone do cadastro para o formato
    internacional brasileiro (55 + DDD + número, 12 ou 13 dígitos). O cadastro
    guarda «(99) 99999-0000»; a Meta quer «5599999990000». Número de fora do
    Brasil é recusado: o aviso automático é para o cliente desta casa, e um
    número que não se confere não recebe mensagem com o nome dela.

ESTE MÓDULO NÃO FALA COM A REDE
    Ele MONTA o pedido (url, corpo e cabeçalhos), como `wa_balcao.montar_envio`;
    quem posta é `wa_balcao.postar_envio`, fora de toda transação.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Iterable, Mapping, Sequence

import wa_balcao as WA
import wa_schema as SCH

IDIOMA = "pt_BR"

# Os cinco modelos, pela chave interna.
EXIGENCIA = "EXIGENCIA"
PRONTO = "PRONTO"
PRAZO = "PRAZO"
PESQUISA = "PESQUISA"
RETOMAR = "RETOMAR"
ORDEM = (EXIGENCIA, PRONTO, PRAZO, PESQUISA, RETOMAR)

# O que cada variável é — e é isso que decide a régua dela.
CARTORIO = "cartorio"
NUMERO = "numero"
DATA = "data"
LINK = "link"
NOME_DA_VARIAVEL = {
    CARTORIO: "complemento do nome do cartório",
    NUMERO: "número",
    DATA: "data (dd/mm/aaaa)",
    LINK: "link da pesquisa",
}

#: Os cinco modelos. `corpo` é a CÓPIA LOCAL do texto cadastrado na Meta —
#: serve para a tela mostrar o que sai e para a conversa guardar o que foi
#: mandado. O texto que vale é o aprovado lá; se a Meta o mudar na aprovação,
#: esta cópia se corrige aqui, e o envio não muda (o corpo não vai no pedido).
MODELOS: dict[str, dict[str, Any]] = {
    EXIGENCIA: {
        "chave": SCH.CHAVE_MODELO_EXIGENCIA, "padrao": "cartorio_exigencia",
        "rotulo": "Exigência (nota devolutiva na prenotação)",
        "variaveis": (CARTORIO, NUMERO),
        "corpo": ("Cartório {{1}}: o protocolo nº {{2}} recebeu nota de exigência. "
                  "Procure o cartório ou consulte o portal com o seu código de "
                  "acompanhamento."),
    },
    PRONTO: {
        "chave": SCH.CHAVE_MODELO_PRONTO, "padrao": "cartorio_pronto_retirar",
        "rotulo": "Pronto para retirar",
        "variaveis": (CARTORIO, NUMERO),
        "corpo": "Cartório {{1}}: o protocolo nº {{2}} está pronto para retirar.",
    },
    PRAZO: {
        "chave": SCH.CHAVE_MODELO_PRAZO, "padrao": "cartorio_prenotacao_vencendo",
        "rotulo": "Prenotação perto de vencer",
        "variaveis": (CARTORIO, NUMERO, DATA),
        "corpo": "Cartório {{1}}: a prenotação nº {{2}} vence em {{3}}. Procure o cartório.",
    },
    PESQUISA: {
        "chave": SCH.CHAVE_MODELO_PESQUISA, "padrao": "cartorio_pesquisa_satisfacao",
        "rotulo": "Convite da pesquisa de satisfação",
        "variaveis": (CARTORIO, NUMERO, LINK),
        "corpo": ("Cartório {{1}}: conte como foi o seu atendimento no protocolo nº {{2}}. "
                  "Responda aqui: {{3}} Obrigado!"),
    },
    RETOMAR: {
        "chave": SCH.CHAVE_MODELO_RETOMAR, "padrao": "cartorio_retomar_atendimento",
        "rotulo": "Retomar o atendimento (depois das 24 h)",
        "variaveis": (CARTORIO,),
        "corpo": ("Cartório {{1}}: temos uma resposta para a sua mensagem. Responda esta "
                  "mensagem para continuar o atendimento."),
    },
}

#: A janela da Meta para texto livre: 24 h desde a última mensagem do cliente.
JANELA_HORAS = 24

#: As frases que a fila e a tela mostram quando o envio por modelo não pode sair.
DESLIGADO = ("os modelos da Meta ainda não foram marcados como aprovados "
             "(WhatsApp → configuração)")
SEM_CREDENCIAL = ("falta access_token ou phone_number_id na configuração do WhatsApp "
                  "(WhatsApp → configuração)")
SEM_NOME = ("falta o nome do cartório no modelo: preencha «nome no modelo» em "
            "WhatsApp → configuração (ex.: «de Exemplo»), ou a cidade da serventia")


class ModeloRecusado(WA.EnvioErro, ValueError):
    """O pedido de modelo não passou na conferência. Nada foi à Meta."""


class TelefoneInvalido(ValueError):
    """O telefone do cadastro não serve para o WhatsApp. Frase pronta."""


# ------------------------------------------------------------------ a configuração


def ligado(con: Any) -> bool:
    """O interruptor «modelos aprovados pela Meta». Nasce desligado. Só lê."""
    return WA.ler_config(con, SCH.CHAVE_MODELOS_APROVADOS) == "1"


def _spec(qual: str) -> dict[str, Any]:
    spec = MODELOS.get(str(qual or "").strip().upper())
    if spec is None:
        raise ModeloRecusado(f"Modelo desconhecido: «{qual}». Os conhecidos são "
                             + ", ".join(ORDEM) + ".")
    return spec


_RE_NOME_DO_MODELO = re.compile(r"^[a-z0-9_]{1,512}$")


def nome_do_modelo(con: Any, qual: str) -> str:
    """O nome cadastrado na Meta para aquele modelo: o da configuração ou o
    padrão. Só lê."""
    spec = _spec(qual)
    gravado = WA.ler_config(con, spec["chave"]) if con is not None else ""
    return gravado or spec["padrao"]


def _cidade_sem_uf(cidade: str) -> str:
    return re.split(r"\s*[/-]\s*[A-Za-z]{2}\s*$", cidade.strip())[0].strip()


def derivar_nome_no_modelo(serventia: Mapping[str, Any] | None) -> str:
    """O complemento que vai depois de «Cartório», tirado da serventia. Só calcula.

    1. a cidade (`ri_cidade`): «de <cidade>», sem a UF;
    2. sem cidade, o nome (`unit_name`): o que vem depois do último « de »;
    3. sem nenhum dos dois, vazio — e o envio é recusado (`SEM_NOME`).
    A preposição pode não ser «de» («do», «da»): por isso a configuração
    `nome_no_modelo` existe e ganha deste cálculo."""
    s = serventia or {}
    cidade = _cidade_sem_uf(str(s.get("ri_cidade") or ""))
    if cidade:
        return f"de {cidade}"
    nome = str(s.get("unit_name") or "").strip()
    pedacos = re.split(r"\s+de\s+", nome)
    if len(pedacos) > 1 and pedacos[-1].strip():
        return "de " + _cidade_sem_uf(pedacos[-1])
    return ""


def nome_no_modelo(con: Any, serventia: Mapping[str, Any] | None = None) -> str:
    """O {{1}} dos cinco modelos: a configuração, ou o derivado da serventia. Só lê."""
    gravado = WA.ler_config(con, SCH.CHAVE_NOME_NO_MODELO) if con is not None else ""
    return " ".join(gravado.split()) or derivar_nome_no_modelo(serventia)


def falta_para_enviar(con: Any, serventia: Mapping[str, Any] | None = None) -> str:
    """O que impede o envio por modelo, ou ``""``. Só lê.

    Desligado vem primeiro: com o interruptor desligado, quem chama mantém o
    comportamento de antes (a frase dele)."""
    if not ligado(con):
        return DESLIGADO
    if not WA.pode_enviar_meta(con):
        return SEM_CREDENCIAL
    nome = nome_no_modelo(con, serventia)
    if not nome:
        return SEM_NOME
    try:
        _conferir_variavel(CARTORIO, nome, 1)
    except ModeloRecusado as erro:
        return f"o nome do cartório no modelo não serve: {erro}"
    return ""


# ------------------------------------------------------------------ o telefone


def telefone_e164(texto: Any) -> str:
    """O telefone do cadastro no formato da Meta: 55 + DDD + número. Só calcula.

    Aceita «(99) 99999-0000», «99 9999-0000», «+55 99 99999-0000»,
    «0 99 99999-0000». Recusa, com a frase pronta, o que não é número
    brasileiro com DDD."""
    d = "".join(c for c in str(texto or "") if c.isdigit())
    if not d:
        raise TelefoneInvalido("Sem telefone no cadastro. Corrija o contato antes de mandar "
                               "pelo WhatsApp.")
    if str(texto).strip().startswith("+") and not d.startswith("55"):
        raise TelefoneInvalido("O telefone tem código de outro país. Número de fora do Brasil "
                               "não recebe o aviso automático.")
    if d.startswith("55") and len(d) in (12, 13):
        nacional = d[2:]
    elif len(d) in (10, 11):
        nacional = d
    elif d.startswith("0") and len(d.lstrip("0")) in (10, 11):
        nacional = d.lstrip("0")          # o zero de discagem de longa distância
    else:
        raise TelefoneInvalido(
            "O telefone precisa do DDD e do número (ex.: (99) 99999-0000), ou do 55 do "
            "Brasil na frente (12 ou 13 dígitos). Número de fora do Brasil não recebe o "
            "aviso automático.")
    ddd, numero = nacional[:2], nacional[2:]
    if "0" in ddd:
        raise TelefoneInvalido(f"O DDD «{ddd}» não existe (DDD não tem zero). Corrija o "
                               "telefone.")
    if len(numero) == 9 and numero[0] != "9":
        raise TelefoneInvalido("Celular de 9 dígitos começa com 9. Corrija o telefone.")
    if len(numero) == 8 and numero[0] in "01":
        raise TelefoneInvalido("O número depois do DDD não pode começar com 0 ou 1. Corrija "
                               "o telefone.")
    return "55" + nacional


# ------------------------------------------------------------------ a conferência


# A regra da casa para o que sai sozinho: nenhuma variável leva CPF, CNPJ,
# valor, pix nem e-mail. A comparação é sem caixa.
_PROIBIDO = (
    (re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"), "número com cara de CPF"),
    (re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b"), "número com cara de CNPJ"),
    (re.compile(r"r\$", re.IGNORECASE), "valor em reais («R$»)"),
    (re.compile(r"\b\d{1,3}(?:\.\d{3})*,\d{2}\b"), "valor em dinheiro"),
    (re.compile(r"\bpix\b", re.IGNORECASE), "a palavra «pix»"),
    (re.compile(r"[^\s@/]+@[^\s@/]+\.[^\s@/]+"), "endereço de e-mail"),
)
_RE_NUMERO = re.compile(r"^\d[\d./-]{0,29}$")
_RE_DATA = re.compile(r"^\d{2}/\d{2}/\d{4}$")
_RE_LINK = re.compile(r"^https://[^\s<>\"']{4,300}$")
_RE_CARTORIO = re.compile(r"^[^\d@{}<>|\\]{2,80}$")


def _conferir_variavel(tipo: str, valor: Any, posicao: int) -> str:
    texto = "" if valor is None else str(valor)
    rotulo = f"A variável {{{{{posicao}}}}} ({NOME_DA_VARIAVEL.get(tipo, tipo)})"
    if not texto.strip():
        raise ModeloRecusado(f"{rotulo} está vazia.")
    if any(c in texto for c in "\n\r\t") or "    " in texto:
        raise ModeloRecusado(f"{rotulo} tem quebra de linha, tabulação ou mais de quatro "
                             "espaços seguidos — a Meta recusa.")
    texto = texto.strip()
    if "{{" in texto or "}}" in texto:
        raise ModeloRecusado(f"{rotulo} traz «{{{{»: variável dentro de variável não sai.")
    for padrao, o_que in _PROIBIDO:
        if padrao.search(texto):
            raise ModeloRecusado(f"{rotulo} traz {o_que}. Mensagem automática não leva "
                                 "CPF, valor, nome de pessoa nem o teor do ato.")
    if tipo == NUMERO and not _RE_NUMERO.match(texto):
        raise ModeloRecusado(f"{rotulo} tem de ser só o número (dígitos, ponto, barra e "
                             f"hífen), e veio «{texto[:40]}».")
    if tipo == DATA:
        if not _RE_DATA.match(texto):
            raise ModeloRecusado(f"{rotulo} tem de ser dd/mm/aaaa, e veio «{texto[:20]}».")
        try:
            datetime.strptime(texto, "%d/%m/%Y")
        except ValueError:
            raise ModeloRecusado(f"{rotulo} não é uma data que existe: «{texto}».") from None
    if tipo == LINK and not _RE_LINK.match(texto):
        raise ModeloRecusado(f"{rotulo} tem de ser um endereço https:// sem espaço.")
    if tipo == CARTORIO:
        if not _RE_CARTORIO.match(texto):
            raise ModeloRecusado(f"{rotulo} tem de ser texto curto, sem número (ex.: «de "
                                 "Exemplo»).")
        if re.match(r"(?i)cart[oó]rio\b", texto):
            raise ModeloRecusado(f"{rotulo} não repete «Cartório»: o modelo já começa com a "
                                 "palavra. Escreva só o complemento, ex.: «de Exemplo».")
    return texto


def conferir(qual: str, variaveis: Sequence[Any], nome: str | None = None) -> list[str]:
    """As variáveis conferidas, na ordem do corpo. Recusa com `ModeloRecusado`. Só calcula."""
    spec = _spec(qual)
    nome = spec["padrao"] if nome is None else str(nome)
    if not _RE_NOME_DO_MODELO.match(nome):
        raise ModeloRecusado(f"O nome do modelo «{nome}» não segue a regra da Meta (só letras "
                             "minúsculas, números e sublinhado).")
    if isinstance(variaveis, (str, bytes)) or variaveis is None:
        raise ModeloRecusado("As variáveis do modelo vão numa lista, na ordem do corpo.")
    variaveis = list(variaveis)
    esperadas = spec["variaveis"]
    if len(variaveis) != len(esperadas):
        raise ModeloRecusado(
            f"O modelo {nome} tem {len(esperadas)} variável(is) "
            f"({', '.join(NOME_DA_VARIAVEL[t] for t in esperadas)}), e vieram "
            f"{len(variaveis)}.")
    return [_conferir_variavel(t, v, i) for i, (t, v) in enumerate(zip(esperadas, variaveis),
                                                                   start=1)]


_RE_PARA = re.compile(r"^\d{8,15}$")


def montar_envio_modelo(con: Any, para: str, qual: str, variaveis: Sequence[Any]) -> dict:
    """O pedido de MODELO pronto para a Graph: url, corpo e cabeçalhos. Só lê.

    `para` já vai no formato internacional (só dígitos): o telefone do cadastro
    passa antes por `telefone_e164`; o `wa_id` da conversa já vem assim da Meta.
    Recusa (`ModeloRecusado`) com o interruptor desligado, sem credencial, ou
    quando a conferência não passa — e em nenhum desses casos fala com a rede."""
    if not ligado(con):
        raise ModeloRecusado("Os modelos da Meta ainda não foram marcados como aprovados "
                             "(WhatsApp → configuração). Nada foi enviado.")
    nome = nome_do_modelo(con, qual)
    conferidas = conferir(qual, variaveis, nome)
    destino = "".join(c for c in str(para or "") if c.isdigit())
    if not _RE_PARA.match(destino):
        raise ModeloRecusado("O número de destino não está no formato internacional "
                             "(só dígitos, com o código do país).")
    token = WA.ler_config(con, SCH.CHAVE_TOKEN)
    phone = WA.ler_config(con, SCH.CHAVE_PHONE)
    if not token or not phone:
        raise ModeloRecusado("Falta access_token ou phone_number_id na configuração.")
    return {
        "url": f"https://graph.facebook.com/{WA.GRAPH_VER}/{phone}/messages",
        "payload": {
            "messaging_product": "whatsapp",
            "to": destino,
            "type": "template",
            "template": {
                "name": nome,
                "language": {"code": IDIOMA},
                "components": [{
                    "type": "body",
                    "parameters": [{"type": "text", "text": v} for v in conferidas],
                }],
            },
        },
        "headers": {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        "modelo": nome,
        "texto": texto_local(qual, conferidas),
    }


def texto_local(qual: str, variaveis: Sequence[Any]) -> str:
    """O corpo do modelo com as variáveis — a cópia local do que a Meta mostra
    ao cliente. Serve à tela e ao registro da conversa. Só calcula."""
    corpo = _spec(qual)["corpo"]
    for i, v in enumerate(variaveis, start=1):
        corpo = corpo.replace("{{" + str(i) + "}}", str(v))
    return corpo


# ------------------------------------------------------------------ a janela de 24 h


def _quando(texto: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(texto or "").strip()[:19])
    except ValueError:
        return None


def fora_da_janela(mensagens: Iterable[Mapping[str, Any]], agora: Any) -> bool:
    """Passou a janela de 24 h desde a última mensagem DO CLIENTE? Só calcula.

    Conversa sem mensagem do cliente também está fora: a Meta só abre a janela
    quando o cliente escreve."""
    agora_dt = agora if isinstance(agora, datetime) else _quando(agora)
    if agora_dt is None:
        agora_dt = datetime.now()
    ultima = None
    for m in mensagens or ():
        if m.get("direcao") != WA.DIR_IN:
            continue
        q = _quando(m.get("criado_em"))
        if q and (ultima is None or q > ultima):
            ultima = q
    return ultima is None or agora_dt - ultima > timedelta(hours=JANELA_HORAS)


# ------------------------------------------------------------------ a tela


def config_para_tela(con: Any, serventia: Mapping[str, Any] | None = None) -> dict:
    """O que a tela de configuração mostra dos modelos. Só lê."""
    gravado_nome = WA.ler_config(con, SCH.CHAVE_NOME_NO_MODELO)
    derivado = derivar_nome_no_modelo(serventia)
    efetivo = nome_no_modelo(con, serventia)
    linhas = []
    for qual in ORDEM:
        spec = MODELOS[qual]
        gravado = WA.ler_config(con, spec["chave"])
        exemplo = [efetivo or "de Exemplo"] + [
            {NUMERO: "2026.10.123", DATA: "05/11/2026",
             LINK: "https://exemplo.invalid/r/CODIGO"}[t] for t in spec["variaveis"][1:]]
        linhas.append({"qual": qual, "campo": spec["chave"], "rotulo": spec["rotulo"],
                       "gravado": gravado, "padrao": spec["padrao"],
                       "nome": gravado or spec["padrao"],
                       "variaveis": [NOME_DA_VARIAVEL[t] for t in spec["variaveis"]],
                       "exemplo": texto_local(qual, exemplo)})
    return {"ligado": ligado(con), "nome_no_modelo": gravado_nome,
            "nome_derivado": derivado, "nome_efetivo": efetivo, "modelos": linhas,
            "falta": falta_para_enviar(con, serventia), "idioma": IDIOMA}


def gravar_tela(con: Any, form: Mapping[str, Any]) -> None:
    """Grava os nomes, o complemento e o interruptor. ESCREVE.

    Confere tudo ANTES de gravar qualquer coisa: um nome torto não deixa os
    outros pela metade. Nome vazio = o padrão."""
    nomes: dict[str, str] = {}
    for qual in ORDEM:
        spec = MODELOS[qual]
        valor = str(form.get(spec["chave"]) or "").strip()
        if valor and not _RE_NOME_DO_MODELO.match(valor):
            raise ModeloRecusado(f"O nome «{valor}» ({spec['rotulo']}) não segue a regra da "
                                 "Meta: só letras minúsculas, números e sublinhado.")
        nomes[spec["chave"]] = "" if valor == spec["padrao"] else valor
    complemento = " ".join(str(form.get(SCH.CHAVE_NOME_NO_MODELO) or "").split())
    if complemento:
        _conferir_variavel(CARTORIO, complemento, 1)
    for chave, valor in nomes.items():
        WA.gravar_config(con, chave, valor)
    WA.gravar_config(con, SCH.CHAVE_NOME_NO_MODELO, complemento)
    WA.gravar_config(con, SCH.CHAVE_MODELOS_APROVADOS,
                     "1" if str(form.get(SCH.CHAVE_MODELOS_APROVADOS) or "") == "1" else "")
