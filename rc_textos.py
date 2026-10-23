"""Os textos do Registro Civil que saíram do código — a leitura e a conferência.

    «Não deveríamos ter modelos no código; deveriam estar no banco, para editar
     com mais facilidade.» — o oficial, 19/10/2026 (LF06A; o civil é o LF06C).

O TEXTO MORA EM `modelos_padrao/rcpn/`, E A REGRA FICA NO MÓDULO
    Cada papel do civil que era montado no código tem o texto de fábrica na
    pasta dos padrões: o papel inteiro (`RC_EDITAL_PROCLAMAS.txt`) ou, quando
    uma REGRA decide se a frase entra — gênero, plural, edital ou pessoal —, a
    frase como PEÇA do papel (`RC_TERMO_OBITO__sepultamento.txt`). Quem decide
    se a frase entra continua sendo o módulo; aqui só se lê o texto dela.

DE ONDE O TEXTO SAI — UMA REGRA SÓ, A DO `docs/MODELOS_PADRAO.md`
    · com a conexão à mão, a BUSCA ÚNICA (`modelos_da_casa.texto_do_papel`):
      o ajuste da casa, e na falta dele o padrão da base;
    · sem conexão (o montador puro, a prévia, a ferramenta avulsa), o padrão
      da base (`padrao_de`).

    O termo do civil é montado por funções puras, dez chamadas abaixo de quem
    tem a conexão (`rc_termo.montar_para_conferir`). Em vez de pendurar a
    conexão na assinatura de uma dúzia de funções que os testes e o motor de
    prévia também chamam, quem lavra abre `lendo_da_casa(con)` em volta da
    montagem, e `texto()` lê pela busca única enquanto ele estiver aberto. A
    emissão da certidão (`rc_certidao.emitir`), a tela da averbação de
    retificação e a prévia do inteiro teor fazem o mesmo, pelo mesmo motivo.

POR QUE HÁ UM CONFERIDOR PRÓPRIO
    Os papéis do civil escrevem os claros com uma chave só (`{nome}`, o
    `str.format`), e a conferência geral da tela só pega a FORMA (chave sem
    fechar, `{{` do Jinja). Um claro inventado num ajuste — `{nome_do_pai}`
    onde o papel só sabe `{pai}` — passaria na tela e estouraria `KeyError`
    na hora de emitir, com o cliente no balcão. `conferir_claros` recusa na
    tela, que é onde há tempo de consertar: o ajuste só pode usar os claros
    que o padrão daquele papel usa. A régua é a de `modelos_da_casa`; daqui
    sai só a lista dos claros de cada papel.
"""
from __future__ import annotations

import string
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Callable, Iterator

# Os papéis do civil que nasceram no catálogo no LF06C e escrevem os claros
# com chave simples. Os quatro termos têm conferidor próprio, mais rico
# (`rc_modelos_do_livro.conferir_corpo`), registrado em `atribuicoes_web`.
# As PEÇAS não estão aqui porque a tela de Modelos ainda não as lista; quando
# listar, `conferir_claros` já serve a elas (o padrão de uma peça se lê igual).
CLAROS_FECHADOS: tuple[str, ...] = (
    "RC_QUALIFICACAO",
    "RC_CERTIDAO_RESUMO",
    "RC_CERTIDAO_INTEIRO_TEOR",
    "RC_ANOTACAO_CRC_COMPACTA",
    "RC_ANOTACAO_CRC_COMPLETA",
    "RC_ANOTACAO_CRC_FE_PUBLICA",
    "RC_AVERBACAO_RETIFICACAO",
    "RC_COMUNICACAO_OBITOS",
    "RC_OFICIO_FUNAI",
    "RC_EDITAL_PROCLAMAS",
    "RC_EDITAL_PROCLAMAS_FOLHA",
    "RC_CERTIDAO_HABILITACAO",
)

_LEITOR: ContextVar[Callable[[str], str] | None] = ContextVar(
    "rc_textos_leitor", default=None)


def texto(chave: str, con: Any = None) -> str:
    """O texto que vale para aquele papel ou peça. Só lê.

    Com `con` — ou dentro de `lendo_da_casa` —, a busca única; sem, o padrão
    da base. Papel ou peça que não está na pasta é `ModeloError` com o nome do
    arquivo que falta, e nunca folha em branco.
    """
    import modelos_da_casa as CASA
    if con is not None:
        return CASA.texto_do_papel(con, chave)
    leitor = _LEITOR.get()
    if leitor is not None:
        return leitor(chave)
    return CASA.padrao_de(chave)


def peca(chave: str, con: Any = None, **claros: Any) -> str:
    """O texto da peça com os claros preenchidos (`str.format`)."""
    return texto(chave, con).format(**claros)


@contextmanager
def lendo_da_casa(con: Any) -> Iterator[None]:
    """Enquanto aberto, `texto()` lê pela busca única com esta conexão.

    Cada texto é lido UMA vez por abertura: o termo de nascimento pede a mesma
    peça da qualificação para a mãe, o pai e o declarante, e não há por que ir
    ao banco três vezes atrás do mesmo texto no meio de uma lavratura.
    """
    import modelos_da_casa as CASA
    lidos: dict[str, str] = {}

    def ler(chave: str) -> str:
        if chave not in lidos:
            lidos[chave] = CASA.texto_do_papel(con, chave)
        return lidos[chave]

    marca = _LEITOR.set(ler)
    try:
        yield
    finally:
        _LEITOR.reset(marca)


def claros_de(corpo: str) -> list[str]:
    """Os claros que um texto usa, na ordem em que aparecem. Só calcula."""
    vistos: list[str] = []
    for _, campo, _, _ in string.Formatter().parse(corpo or ""):
        if campo is not None and campo not in vistos:
            vistos.append(campo)
    return vistos


def conferir_claros(chave: str, corpo: str) -> str:
    """O ajuste serve àquele papel? Devolve o erro, ou ``""``. Só calcula.

    Os claros conhecidos são os do PADRÃO do papel: são os que o módulo
    preenche, e o ajuste pode usar menos, nunca outro.

    **A RÉGUA É A DO `modelos_da_casa.conferir_claros`** (LF06G) — a mesma da
    retificação e da usucapião. O LF06C nasceu em paralelo com uma cópia dela,
    com as mesmas recusas (`{{`/`{%` do Jinja, chave sem fechar, claro sem nome,
    claro que o papel não tem) e outras palavras; duas réguas para a mesma
    coisa acabariam discordando, e a tela diria uma coisa num papel e outra
    no vizinho.
    """
    import modelos_da_casa as CASA
    return CASA.conferir_claros(corpo, claros_de(CASA.padrao_de(chave)))
