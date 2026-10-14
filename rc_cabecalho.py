"""O cabeçalho da folha do livro — medido no papel que a casa imprime.

DE ONDE SAIU
    Do cabeçalho do **termo de nascimento nº 19.555**, de 19/08/2026, que o
    oficial fotografou em 30/08/2026. É o papel que sai da impressora hoje.

    Sete linhas, e a ordem importa: o brasão, o país, a serventia, o titular
    com a qualidade, o endereço, o contato, e então o **título do ato** com o
    termo, o livro e a folha.

O QUE ELE DENUNCIOU
    Comparando o papel com o que o sistema tem gravado, **quatro campos
    divergiam** — e um deles é o nome do oficial:

        no papel:   MARIO EXEMPLO DOS SANTOS
        no sistema: MARIO EXEMPLO DOS SANTOS      ← falta o «T»

    O nome do delegatário sai em **todo documento que a casa assina**. Um erro
    de uma letra ali não é detalhe de cadastro: é o titular assinando com o
    nome errado.

    Os outros três — telefone, endereço e CEP — estão anotados no roteiro para
    o oficial conferir, porque **dado de identificação da serventia é dele**,
    e não se corrige por dedução de quem lê uma foto.
"""
from __future__ import annotations

from typing import Any

# A ORDEM DAS LINHAS, medida no papel. Cada uma diz de onde sai o texto.
#
#   **NÃO É DECORAÇÃO.** O brasão e o «República Federativa do Brasil» estão lá
#   porque o registro civil é serviço público delegado, e a folha do livro
#   precisa dizer em nome de quem o ato é praticado.
LINHAS: tuple[dict, ...] = (
    {"chave": "brasao", "o_que": "o brasão da República",
     "de_onde": "arquivo da casa", "estilo": "imagem"},
    {"chave": "pais", "o_que": "REPÚBLICA FEDERATIVA DO BRASIL",
     "de_onde": "fixo", "estilo": "normal"},
    {"chave": "unidade", "o_que": "o nome da serventia",
     "de_onde": "`unit_name`", "estilo": "forte"},
    {"chave": "titular", "o_que": "o titular e a qualidade",
     "de_onde": "`serventia_titular` e `serventia_titulo`",
     "estilo": "forte-e-normal"},
    {"chave": "endereco", "o_que": "endereço, cidade/UF e CEP",
     "de_onde": "`serventia_endereco`, `ri_cidade`, `ri_uf`, `serventia_cep`",
     "estilo": "normal"},
    {"chave": "contato", "o_que": "telefone e e-mail",
     "de_onde": "`serventia_telefone` e `serventia_email`",
     "estilo": "normal"},
    {"chave": "titulo", "o_que": "o título do ato — REGISTRO DE NASCIMENTO",
     "de_onde": "a espécie do assento", "estilo": "forte"},
    {"chave": "localizacao", "o_que": "Termo, Livro e Folha",
     "de_onde": "o próprio assento", "estilo": "tres-colunas"},
)

PAIS = "REPÚBLICA FEDERATIVA DO BRASIL"

# O TÍTULO DO ATO, por espécie. É o que está impresso na folha, em caixa alta.
TITULO_DO_ATO: dict[str, str] = {
    "NASCIMENTO": "REGISTRO DE NASCIMENTO",
    "CASAMENTO": "REGISTRO DE CASAMENTO",
    "CASAMENTO_RELIGIOSO": "REGISTRO DE CASAMENTO RELIGIOSO COM EFEITO CIVIL",
    "OBITO": "REGISTRO DE ÓBITO",
    "NATIMORTO": "REGISTRO DE NATIMORTO",
    "PROCLAMAS": "PROCLAMAS",
    # Livro E — mesmo cabeçalho Termo|Livro|Folha; o título muda pela espécie.
    "AUSENCIA": "REGISTRO DE AUSÊNCIA",
    "INTERDICAO": "REGISTRO DE INTERDIÇÃO",
    "TUTELA": "REGISTRO DE TUTELA",
    "EMANCIPACAO": "REGISTRO DE EMANCIPAÇÃO",
    "UNIAO_ESTAVEL": "REGISTRO DE UNIÃO ESTÁVEL",
    "OPCAO_NACIONALIDADE": "REGISTRO DE OPÇÃO DE NACIONALIDADE",
    "OUTRO": "REGISTRO DO LIVRO E",
}


class CabecalhoError(ValueError):
    """Erro de regra, em português de balcão."""


def _texto(v: Any) -> str:
    return "" if v is None else str(v).strip()


def titulo_do_ato(especie: Any) -> str:
    e = _texto(especie).upper()
    if e not in TITULO_DO_ATO:
        raise CabecalhoError(
            f"Não sei que título imprimir para «{especie}». Os que sei: "
            + ", ".join(TITULO_DO_ATO) + ".")
    return TITULO_DO_ATO[e]


def montar(sv: dict, *, especie: Any = None, termo: Any = None,
           livro: Any = None, folha: Any = None) -> dict:
    """As linhas do cabeçalho, prontas para a folha. Só monta.

    **A LOCALIZAÇÃO SAI EM TRÊS COLUNAS** — Termo à esquerda, Livro no meio,
    Folha à direita —, que é como está no papel. Juntá-las numa linha só
    pouparia espaço e tiraria do escrevente a leitura que ele faz de relance,
    sempre no mesmo lugar da folha.
    """
    sv = sv or {}
    cidade = _texto(sv.get("ri_cidade"))
    uf = _texto(sv.get("ri_uf"))
    endereco = ", ".join(x for x in (
        _texto(sv.get("serventia_endereco")),
        f"{cidade}/{uf}" if cidade else "") if x)
    cep = _texto(sv.get("serventia_cep"))
    if cep:
        endereco += f" - CEP: {cep}."
    contato = " - ".join(x for x in (
        f"Telefone: {_texto(sv.get('serventia_telefone'))}"
        if _texto(sv.get("serventia_telefone")) else "",
        f"Email: {_texto(sv.get('serventia_email'))}"
        if _texto(sv.get("serventia_email")) else "") if x)

    titular = _texto(sv.get("serventia_titular"))
    titulo = _texto(sv.get("serventia_titulo"))
    return {
        "pais": PAIS,
        "unidade": _texto(sv.get("unit_name")),
        "titular": titular,
        "titular_qualidade": titulo,
        "endereco": endereco,
        "contato": contato,
        "titulo_do_ato": titulo_do_ato(especie) if especie else "",
        "termo": _texto(termo),
        "livro": _texto(livro),
        "folha": _texto(folha),
    }


def o_que_falta(cabecalho: dict) -> list[str]:
    """O que o cabeçalho não tem. Só lê.

    **CABEÇALHO INCOMPLETO NÃO IMPEDE IMPRIMIR**, e por isso esta função existe
    separada: quem lavra às 17h50 não pode parar porque o telefone da serventia
    não está cadastrado. Mas a folha do livro sai com a identificação da casa
    pela metade, e alguém precisa saber disso antes de encadernar.
    """
    exigidos = {"unidade": "o nome da serventia",
                "titular": "o nome do titular",
                "titular_qualidade": "a qualidade do titular",
                "endereco": "o endereço",
                "titulo_do_ato": "o título do ato"}
    return [texto for chave, texto in exigidos.items()
            if not _texto(cabecalho.get(chave))]
