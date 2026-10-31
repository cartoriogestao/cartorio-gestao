"""Textos da casa para o rascunho do WhatsApp.

Fatia 1: classificador + rascunho por regras. Sem API paga de modelo.
Autoenvio desligado: isto so monta texto para o escrevente conferir.

REVOGADO EM PARTE PELO OFICIAL EM 26/10/2026: a IA passou a poder responder
sozinha em QUATRO casos — andamento do protocolo (depois da identificacao por
numero + codigo de acompanhamento), duvidas gerais pelo texto-base aprovado,
valores pela tabela (sempre ESTIMATIVA) e transcricao do audio. Quem faz isso e
`wa_atendente.py`, com interruptor geral desligado de fabrica e registro de
cada resposta. ESTE modulo continua so montando rascunho: os textos daqui nao
saem sozinhos, e o que ele diz abaixo segue valendo para o rascunho.

NUNCA entra no rascunho: CPF, valor, protesto concreto, certidao, instrumento
ou dado de livro. Assuntos livres no futuro: horario, endereco, lista de
documentos — e mesmo esses, o horario de expediente NAO se inventa.

O TEXTO SAIU DAQUI NO LF06F (19/10/2026)
    Os rascunhos e a assinatura eram f-strings neste modulo. Agora sao o papel
    CAIXA_WHATSAPP do catalogo (`modelos_padrao/caixa/CAIXA_WHATSAPP.txt`), uma
    parte por assunto (===HORARIO===, ===CERTIDAO===...), editavel na tela de
    Modelos. A REGRA que escolhe o assunto continua em
    `wa_balcao.classificar`; a que monta a cidade e o endereco da casa,
    aqui. Sem acento de proposito, como sempre foi.
"""
from __future__ import annotations

import logging
import re
from typing import Any
from unicodedata import normalize

_LOG = logging.getLogger(__name__)

# Telefone e e-mail padrao desta serventia (papel timbrado / serventia.PADRAO).
# Vazias desde 09/10/2026 (sanitização): o valor vem de `settings`.
TELEFONE_PADRAO = ""
EMAIL_PADRAO = ""
CIDADE_PADRAO = ""
NOME_PADRAO = ""

# Sem horario medido no sistema: o texto manda confirmar («confirmar horario
# de balcao», na parte ===HORARIO=== do papel). Nao inventar hora.

ASSUNTO_LIVRE = frozenset({"horario", "endereco", "documentos"})
ASSUNTO_SENSIVEL = frozenset({"certidao", "firma", "protesto"})

MODELO = "CAIXA_WHATSAPP"
PARTES = ("CONTATO", "ENDERECO_DA_CASA", "HORARIO", "ENDERECO", "DOCUMENTOS",
          "CERTIDAO", "FIRMA", "PROTESTO", "OUTROS", "SAUDACAO", "AGRADECIMENTO")
# Os claros de cada parte: a assinatura e o endereço da casa têm os seus; os
# sete rascunhos e as duas frases de cortesia recebem os dois já montados.
CLAROS = {"CONTATO": ("nome", "cidade", "telefone", "email"),
          "ENDERECO_DA_CASA": ("endereco", "cep", "cidade", "uf"),
          **{p: ("contato", "endereco") for p in PARTES[2:]}}


def _s(serventia: Any, chave: str, padrao: str) -> str:
    if not serventia:
        return padrao
    v = serventia.get(chave) if hasattr(serventia, "get") else None
    v = ("" if v is None else str(v)).strip()
    return v or padrao


def _partir(corpo: str) -> dict[str, str]:
    marca = re.compile(r"===(" + "|".join(PARTES) + r")===\s*", re.IGNORECASE)
    pedacos = marca.split(corpo or "")
    return {nome.upper(): re.split(r"\n===", valor, maxsplit=1)[0].strip("\n")
            for nome, valor in zip(pedacos[1::2], pedacos[2::2])}


def _montar(parte: str, claros: dict, con: Any = None) -> str:
    """A parte do papel com os claros. Só lê.

    Com `con`, vale o ajuste da casa, e a parte que ele apagou volta ao padrão.
    **O AJUSTE TORTO NÃO DERRUBA A MENSAGEM QUE CHEGOU**: este texto é montado
    no webhook, ao gravar a mensagem do cliente (`wa_balcao.aplicar_entrada`),
    e um claro que o sistema não preenche faria a mensagem se perder. Aí sai o
    padrão, e o log diz por quê — o rascunho é conferido antes de enviar.
    """
    import modelos_da_casa as CASA
    padrao = _partir(CASA.padrao_de(MODELO))
    texto = padrao.get(parte, "")
    if con is not None:
        try:
            texto = _partir(CASA.texto_do_papel(con, MODELO)).get(parte) or texto
        except Exception as erro:                    # noqa: BLE001 — vai ao log
            _LOG.warning("Rascunho do WhatsApp sem o ajuste da casa: %s", erro)
    try:
        return texto.format(**claros)
    except (KeyError, ValueError, IndexError) as erro:
        _LOG.warning("A parte ===%s=== do %s ajustado usa um claro que não "
                     "existe (%s); saiu o padrão.", parte, MODELO, erro)
        return padrao.get(parte, "").format(**claros)


def bloco_contato(serventia: Any = None, con: Any = None) -> str:
    tel = _s(serventia, "serventia_telefone", TELEFONE_PADRAO)
    email = _s(serventia, "serventia_email", EMAIL_PADRAO)
    nome = _s(serventia, "unit_name", NOME_PADRAO)
    cidade = _s(serventia, "cidade_uf", CIDADE_PADRAO)
    if cidade == CIDADE_PADRAO:
        cid = _s(serventia, "ri_cidade", "")
        uf = _s(serventia, "ri_uf", "MA")
        cidade = f"{cid}/{uf}"
    return _montar("CONTATO", {"nome": nome, "cidade": cidade,
                               "telefone": tel, "email": email}, con)


def endereco_da_casa(serventia: Any = None, con: Any = None) -> str:
    end = _s(serventia, "serventia_endereco", "")
    cep = _s(serventia, "serventia_cep", "")
    cid = _s(serventia, "ri_cidade", "")
    uf = _s(serventia, "ri_uf", "MA")
    completo = (serventia or {}).get("endereco_completo") if serventia else None
    if completo and str(completo).strip():
        return str(completo).strip()
    return _montar("ENDERECO_DA_CASA", {"endereco": end, "cep": cep,
                                        "cidade": cid, "uf": uf}, con)


def _rascunho(parte: str, serventia: Any, con: Any) -> str:
    """Um rascunho: a parte do assunto, com a assinatura (`{contato}`) e o
    endereço da casa (`{endereco}`) à disposição de quem ajusta o texto."""
    return _montar(parte, {"contato": bloco_contato(serventia, con),
                           "endereco": endereco_da_casa(serventia, con)}, con)


# A CORTESIA (30/10/2026): mensagem que é SÓ saudação ou agradecimento não precisa de IA
# nem de pessoa. Com qualquer pedido junto («bom dia, quanto custa...»), não é cortesia.
SAUDACAO = "saudacao"
AGRADECIMENTO = "agradecimento"
_SO_SAUDACAO = r"oi+|ola+|opa|bom dia|boa tarde|boa noite|tudo bem|tudo bom|e ai"
_SO_AGRADECIMENTO = (r"(?:muito )?(?:obrigad[oa]s?|brigad[oa]s?)|obg|valeu|agradeco|ok|okay|"
                     r"certo|beleza|blz|ta bom|ta certo")
_CORTESIA = re.compile(rf"(?:(?:{_SO_SAUDACAO}|{_SO_AGRADECIMENTO})\s*)+")
_E_AGRADECIMENTO = re.compile(rf"\b(?:{_SO_AGRADECIMENTO})\b")
_ACENO = ("\U0001F44D", "\U0001F64F")               # o polegar e as mãos juntas
_TETO_DA_CORTESIA = 60


def tipo_de_cortesia(texto: Any) -> str:
    """SAUDACAO, AGRADECIMENTO ou "" (não é só cortesia). Só calcula."""
    bruto = str(texto or "").strip()
    if not bruto or len(bruto) > _TETO_DA_CORTESIA:
        return ""
    sem_acento = "".join(c for c in normalize("NFD", bruto) if not 0x300 <= ord(c) <= 0x36F)
    limpo = " ".join(re.sub(r"[^\w\s]", " ", sem_acento.lower(), flags=re.UNICODE).split())
    if not limpo:
        return AGRADECIMENTO if any(a in bruto for a in _ACENO) else ""
    if not _CORTESIA.fullmatch(limpo):
        return ""
    return AGRADECIMENTO if (_E_AGRADECIMENTO.search(limpo)
                             or any(a in bruto for a in _ACENO)) else SAUDACAO


def frase_de_cortesia(tipo: str, serventia: Any = None, con: Any = None) -> str:
    """A frase pronta da cortesia, ajustável na tela de Modelos. Só lê."""
    return _rascunho("AGRADECIMENTO" if tipo == AGRADECIMENTO else "SAUDACAO", serventia, con)


def rascunho_horario(serventia: Any = None, con: Any = None) -> str:
    return _rascunho("HORARIO", serventia, con)


def rascunho_endereco(serventia: Any = None, con: Any = None) -> str:
    return _rascunho("ENDERECO", serventia, con)


def rascunho_documentos(serventia: Any = None, con: Any = None) -> str:
    return _rascunho("DOCUMENTOS", serventia, con)


def rascunho_certidao(serventia: Any = None, con: Any = None) -> str:
    return _rascunho("CERTIDAO", serventia, con)


def rascunho_firma(serventia: Any = None, con: Any = None) -> str:
    return _rascunho("FIRMA", serventia, con)


def rascunho_protesto(serventia: Any = None, con: Any = None) -> str:
    return _rascunho("PROTESTO", serventia, con)


def rascunho_outros(serventia: Any = None, con: Any = None) -> str:
    return _rascunho("OUTROS", serventia, con)


POR_ETIQUETA = {
    "horario": rascunho_horario,
    "endereco": rascunho_endereco,
    "documentos": rascunho_documentos,
    "certidao": rascunho_certidao,
    "firma": rascunho_firma,
    "protesto": rascunho_protesto,
    "outros": rascunho_outros,
}


def conferir(corpo: str) -> str:
    """O papel que a tela vai gravar monta? Devolve o erro, ou ``""``. Só calcula.

    É a conferência da tela de Modelos: o boneco geral não conhece os claros
    destas partes, e o ajuste torto só apareceria no log do webhook."""
    for parte, texto in _partir(corpo).items():
        try:
            texto.format(**dict.fromkeys(CLAROS[parte], ""))
        except (KeyError, ValueError, IndexError) as erro:
            return (f"A parte ==={parte}=== usa um claro que o rascunho não tem "
                    f"({erro}). Os que ela tem: "
                    + ", ".join("{" + c + "}" for c in CLAROS[parte]) + ".")
    return ""


def __getattr__(nome: str):
    """`MODELO_WHATSAPP`, o nome do papel no catálogo, lido da base. Só lê."""
    if nome.startswith("__"):
        raise AttributeError(nome)
    import modelos_da_casa as _MODELOS
    return _MODELOS.constante_antiga(__name__, nome)
