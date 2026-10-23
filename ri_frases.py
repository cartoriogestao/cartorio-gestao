"""As frases dos papéis do Registro de Imóveis — o texto na base, a regra aqui.

    «Não deveríamos ter modelos no código; deveriam estar no banco, para editar
     com mais facilidade.» — o oficial, 19/10/2026.

O QUE O LF06B TIROU DO CÓDIGO
    O LF06A levou para `modelos_padrao/` os treze papéis do RI que já eram
    modelo (ficha, certidão, nota…). Sobravam as FRASES que os módulos do RI
    montavam em f-string — «CERTIFICO ainda que, nesta data, não há título
    prenotado…», o teor do encerramento da matrícula, a ata do expurgo. Cada
    uma virou papel do catálogo (`modelos_papeis/ri.py`), com o texto em
    `modelos_padrao/ri/<CHAVE>.txt`: aparece na tela de Modelos e a casa edita.

A REGRA NÃO SAIU DAQUI
    Quem decide SE a frase entra — há ou não há prenotação, singular ou plural,
    qual dos motivos do encerramento — continua sendo o módulo, em Python. O
    texto de cada frase é que mora na base: escolher a frase é regra jurídica,
    escrever a frase é da casa.

POR QUE JINJA, E NÃO O `str.format`
    É o formato do RI inteiro (`{{ numero }}`), e é o que a tela de Modelos
    confere antes de gravar. Um `{numero}` editado errado no `str.format`
    estouraria com o cliente na frente; no Jinja a tela recusa antes.
    `keep_trailing_newline` porque a frase sai com os MESMOS bytes de antes —
    o teste-ouro do LF06B confere —, e o Jinja comeria a quebra do fim.
"""
from __future__ import annotations

from jinja2.sandbox import SandboxedEnvironment

import modelos_da_casa as MODELOS

# O MESMO AMBIENTE RESTRITO da casa (`modelos_da_casa.conferir`): montar num
# ambiente mais solto aprovaria frase que a conferência da tela recusa.
_AMBIENTE = SandboxedEnvironment(autoescape=False, keep_trailing_newline=True)


def texto(chave: str, con=None) -> str:
    """O texto que vale hoje para a frase. Só lê.

    Com `con`, a busca única (`texto_do_papel`: o ajuste da casa → o padrão da
    base). Sem `con` — montador puro, que não recebe banco —, o padrão da base.
    """
    if con is None:
        return MODELOS.padrao_de(chave)
    return MODELOS.texto_do_papel(con, chave)


def __getattr__(nome: str) -> str:
    """`ri_frases.RI_CHAVE` — o padrão daquela frase, pelo nome da chave.

    É o par `padrao` dos papéis do LF06B no catálogo (`modelos_papeis/ri.py`):
    estas frases não tinham constante antes (eram f-string no meio da regra),
    e o par só serve para o nome responder como os do LF06A respondem
    (`modelos_da_casa.constante_antiga`). Nome que não é papel continua sendo
    `AttributeError`.
    """
    return MODELOS.constante_antiga(__name__, nome)


def frase(chave: str, con=None, **claros) -> str:
    """A frase montada com os claros. Só calcula.

    Os claros chegam PRONTOS do módulo — já escapados para HTML quando a frase
    vai para HTML: a regra de como cada dado se escreve continua lá.
    """
    return montar(texto(chave, con), **claros)


def ler(con, *chaves: str) -> dict[str, str]:
    """Os textos de várias frases, lidos de uma vez. Só lê.

    Para quem monta um papel com a MESMA frase muitas vezes — a ficha da
    matrícula põe um fecho em cada ato: uma leitura por frase, e não uma
    conexão por ato. Quem recebe o texto lido o monta com `montar`.
    """
    return {c: texto(c, con) for c in chaves}


def montar(modelo: str, **claros) -> str:
    """Monta um texto de frase JÁ LIDO (`ler`) com os claros. Só calcula."""
    return _AMBIENTE.from_string(modelo).render(**claros)
