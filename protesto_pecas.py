"""As peças dos papéis do Protesto — as frases que a regra escolhe, lidas da base.

    «Não deveríamos ter modelos no código; deveriam estar no banco, para editar
     com mais facilidade.» — o oficial, 19/10/2026 (LF06A).

A REGRA FICA NO MÓDULO, A FRASE VAI PARA A PASTA (LF06E)
    O termo, o instrumento, as certidões, o aviso e o edital do Protesto se
    montam de frases que entram ou não conforme os fatos: intimação por edital
    ou em mãos, um protesto ou vários, cópia do título arquivada ou não. QUEM
    DECIDE qual frase entra continua sendo o módulo do papel — é regra jurídica,
    e mexer nela é mexer no programa. O TEXTO de cada frase saiu das f-strings
    para `modelos_padrao/protesto/`, e é o oficial quem o escreve na tela de
    Modelos (o catálogo em `modelos_papeis/protesto.py`).

UMA BUSCA SÓ, A DE TODOS OS PAPÉIS
    Com a conexão, vale o ajuste da casa e, sem ele, o padrão da base
    (`modelos_da_casa.texto_do_papel`). Sem conexão — o montador chamado solto,
    o teste-ouro — vale o padrão: é o «sem modelo, o padrão» que esses
    montadores sempre tiveram.
"""
from __future__ import annotations

from typing import Any


def texto(con: Any, chave: str) -> str:
    """O texto que vale hoje para aquela peça. Só lê."""
    import modelos_da_casa as MODELOS
    if con is None or not _guarda_ajuste(con):
        return MODELOS.padrao_de(chave)
    return MODELOS.texto_do_papel(con, chave)


def _guarda_ajuste(con: Any) -> bool:
    """Se este banco tem onde a casa guardar ajuste de modelo. Só lê.

    **O PISO NÃO DEPENDE DO ANDAR DE CIMA** — a regra de
    `modelos_da_casa.corpo_de`. Banco só com o esquema do protesto (o teste
    do módulo, a ferramenta avulsa, a instalação a meio de migrar) não tem
    `mo_modelos`, e aí o papel sai com o padrão em vez de estourar na
    consulta do ajuste que não pode existir.
    """
    from bd_nativo import banco
    return banco(con).tem_tabela("mo_modelos")


def montar(con: Any, chave: str, erro: type[Exception], **claros: Any) -> str:
    """A peça com os claros preenchidos. Só calcula.

    **CLARO QUE O SISTEMA NÃO SABE PREENCHER É RECUSA, E NÃO FOLHA TORTA**: o
    ajuste da casa com `{nao_existe}` levanta o erro do módulo do papel
    (`CertidaoError`, `TermoError`...), com o nome da peça e os claros que
    valem — o mesmo recado que o papel inteiro já dava.
    """
    return preencher(texto(con, chave), chave, erro, **claros)


def preencher(modelo: str, chave: str, erro: type[Exception],
              **claros: Any) -> str:
    """Os claros de um texto de peça (ou de um rótulo dela). Só calcula.

    `{data.ano}` e `{data[0]}` também são claro que o sistema não preenche: o
    `str.format` os recusa com `AttributeError` e `TypeError`, e sem apanhá-los
    o ajuste antigo, gravado antes de a tela conferir, dava erro 500 em vez do
    recado com o nome da peça.
    """
    try:
        return modelo.format(**claros)
    except (KeyError, IndexError, ValueError, AttributeError, TypeError) as falha:
        import modelos_da_casa as MODELOS
        nome = MODELOS.POR_CHAVE.get(chave, {}).get("nome", chave)
        validos = ", ".join("{" + c + "}" for c in claros) or "nenhum"
        raise erro(
            f"O modelo «{nome}» ({chave}) tem um claro que o sistema não sabe "
            f"preencher: {falha}. Os que valem nele são: {validos}. Confira "
            "o texto em Administrativo → Modelos.") from falha


# ------------------------------------------------------------ os vocabulários
#
# O RÓTULO QUE VAI AO PAPEL TAMBÉM É TEXTO: «FALTA DE PAGAMENTO» no termo, o
# nome por extenso da espécie no aviso, «pago por cheque» no Livro de
# Pagamentos. Eram dicionários no código; desde o LF06E são peças de uma linha
# por rótulo, «nome = texto». QUAIS nomes existem continua sendo regra (o
# código do motivo na CRA, a forma de pagamento que o sistema aceita); COMO
# cada um se escreve é do oficial.


def vocabulario(con: Any, chave: str) -> dict[str, str]:
    """Os rótulos de uma peça-vocabulário: `{nome: texto}`. Só lê.

    **O NOME É DO SISTEMA, O TEXTO É DO OFICIAL.** Os nomes que valem são os
    do padrão; o ajuste da casa troca o texto deles. Nome que o ajuste
    inventou não entra — quais códigos existem é regra —, e o nome que o ajuste
    apagou, ou deixou sem texto, volta ao padrão: o papel nunca fica sem a
    palavra por causa de uma linha perdida na tela.
    """
    padrao = _rotulos(texto(None, chave))
    if con is None:
        return padrao
    ajuste = _rotulos(texto(con, chave))
    return {nome: ajuste.get(nome) or valor for nome, valor in padrao.items()}


def rotulos(con: Any, chave: str, erro: type[Exception] = ValueError):
    """O vocabulário pronto para preencher: `r("nome", claro=valor)`. Só lê."""
    lidos = vocabulario(con, chave)

    def r(nome: str, **claros: Any) -> str:
        return preencher(lidos[nome], chave, erro, **claros)
    return r


def _rotulos(corpo: str) -> dict[str, str]:
    """`«nome = texto»` por linha. Linha sem `=` não é rótulo, e se ignora."""
    lidos: dict[str, str] = {}
    for linha in str(corpo or "").split("\n"):
        nome, sep, valor = linha.partition("=")
        if sep and nome.strip():
            lidos.setdefault(nome.strip(), valor.strip())
    return lidos


# ------------------------------------------------------------ a tela confere
#
# A PEÇA QUEBRADA SE RECUSA AO GRAVAR, E NÃO NA HORA DO ATO — a regra de
# `modelos_da_casa.conferir`. Sem conferidor próprio, a tela conferia estas
# frases como Jinja, e `{claro_inventado}` passava: estourava depois, no termo
# que se lavra ou na certidão com o cliente na frente. A régua é a de quem
# preenche (`modelos_da_casa.conferir_claros`, a mesma do LF06G), com os claros
# que o PADRÃO usa — ele é o texto que o montador escrevia, e o montador
# preenche os claros dele (o teste mede, chamada por chamada).
#
# Os cinco papéis do LF06A (o termo, o instrumento e as três certidões) ficam
# fora: eles aceitam claros de ajustes antigos que o padrão não usa
# (`{fecho}`, `{nome}` na certidão positiva), e continuam no conferidor geral.

# As peças lidas por `vocabulario`: cada linha é um rótulo, com claros próprios.
VOCABULARIOS: tuple[str, ...] = (
    "PT_TERMO_MOTIVOS", "PT_TERMO_TIPOS", "PT_ESPECIES", "PT_CERTIDAO_LINHA",
    "PT_INSTRUMENTO_DESCRICAO", "PT_AVISO_ROTULOS", "PT_EDITAL_ROTULOS",
    "PT_LIVRO_PAGAMENTOS", "PT_LIVRO_PROTOCOLO", "PT_MOLDURAS")


# OS PAPÉIS INTEIROS QUE ESTA RÉGUA CONFERE: os dois do LF06E e os dois do LD04
# (21/10/2026) — o termo do cancelamento e a quitação, que nasceram sem ajuste
# antigo nenhum a aceitar, e por isso não ficam no conferidor geral.
PAPEIS_CONFERIDOS = ("PT_AVISO_INTIMACAO", "PT_EDITAL_INTIMACAO",
                     "PT_TERMO_CANCELAMENTO", "PT_QUITACAO")


def chaves_conferidas() -> tuple[str, ...]:
    """As peças e os papéis inteiros de `PAPEIS_CONFERIDOS` — os que esta régua conhece."""
    from modelos_papeis import protesto as CATALOGO
    return tuple(c["chave"] for c in CATALOGO.PAPEIS
                 if c.get("peca") or c["chave"] in PAPEIS_CONFERIDOS)


def conferir(chave: str, corpo: str) -> str:
    """O ajuste da casa serve para aquela peça? Devolve o erro, ou ``""``. Só calcula.

    No vocabulário a conferência é por linha: o rótulo só pede os claros que
    o mesmo rótulo pede no padrão. Nome que o padrão não tem não se confere —
    a leitura o ignora (`vocabulario`), e o papel não o vê.
    """
    import modelos_da_casa as MODELOS
    padrao = MODELOS.padrao_de(chave)
    if chave not in VOCABULARIOS:
        return MODELOS.conferir_claros(corpo, claros_do_texto(padrao))
    do_padrao = _rotulos(padrao)
    for nome, valor in _rotulos(corpo).items():
        if nome in do_padrao:
            erro = MODELOS.conferir_claros(valor,
                                           claros_do_texto(do_padrao[nome]))
            if erro:
                return f"Na linha «{nome}»: {erro}"
    return ""


def claros_do_texto(modelo: str) -> set[str]:
    """Os nomes `{nome}` que um texto do padrão pede. Só calcula."""
    import string
    return {n for _, n, _, _ in string.Formatter().parse(modelo) if n}


def __getattr__(nome: str):
    """O nome da moldura dos papéis (`MOLDURA_DOS_PAPEIS`), lido da base.

    Mesma regra dos módulos do protesto: o nome do texto de fábrica devolve o
    padrão da base — o MESMO que o papel imprime. Nome que não é de papel
    continua sendo `AttributeError`.
    """
    if nome.startswith("__"):
        raise AttributeError(nome)
    import modelos_da_casa as _MODELOS
    return _MODELOS.constante_antiga(__name__, nome)
