"""Réguas da web que eram escritas tela a tela — lote LX11, 19/10/2026.

Cada uma fecha um achado que aparecia em várias telas ao mesmo tempo;
escrita uma vez aqui, para a próxima tela não nascer com o furo:

    destino_interno   o «volte para» que vem de fora (M1/B3 do LS01)
    recado_de_erro    a exceção inesperada na tela (B2 do LS01)
    numero_digitado   o número que a tela mandou (LD10 e LD13)
"""
from __future__ import annotations

import logging
from urllib.parse import urlsplit

_LOG = logging.getLogger("cartorio.tela")

# QUEM PRATICA ATO (M2). A regra da casa é que o AUDITOR vê e não grava, e
# 284 rotas a seguiam escrevendo os três papéis à mão; 50 só pediam login, e
# nelas o AUDITOR gravava. Uma tupla só, para os módulos de tela importarem
# — `app` não se importa daqui para baixo.
PRATICA = ("ADMIN", "MANAGER", "USER")

#: Quantos dígitos cabem no número que o banco guarda (`bigint` vai até 19).
DIGITOS_DE_UM_NUMERO = 18

#: A página mais alta que uma lista aceita no endereço (`?pagina=`). Com 50
#: linhas por página são 50 bilhões de linhas; bem antes dos 18 dígitos o
#: OFFSET (`(pagina - 1) * 50`) passa do `bigint`, e o banco recusa a consulta.
PAGINA_MAIS_ALTA = 10 ** 9

#: O maior que cabe numa coluna `integer` (int4) do PostgreSQL. Quantidade
#: que vai gravada numa delas e passa disto derruba o INSERT («integer out of
#: range»), mesmo com menos de 18 dígitos.
MAIOR_INTEGER = 2 ** 31 - 1


def numero_digitado(texto, *, maximo: int | None = None) -> int | None:
    """O número que a tela mandou, ou None se não é um número que o banco
    guarde. Só calcula.

    NASCEU DE UM 500 MEDIDO — LD10, 21/10/2026 (ressalva da revisão do LD03).
    O protocolo digitado no cancelamento e na lavratura passava por
    `isascii() and isdigit()` e ia direto para `int(...)`. Com mais de 4.300
    dígitos o próprio Python recusa a conversão (`ValueError`) e a rota caía
    na tela de erro; entre 19 e 4.300 dígitos o número nem existe numa coluna
    `bigint`. Número assim não é protocolo de ninguém: volta None, que é o
    mesmo «não achei» do texto que não é número. Os zeros da frente não
    contam («0042» é o 42).

    MORA AQUI DESDE O LD13 (21/10/2026, «nenhuma pendência»). A revisão do
    LD10 achou o mesmo `int(...)` cru em outras rotas do RI, e a varredura do
    LD13 nos outros módulos de tela: «abc» virava `ValueError`, o «²» passa
    pelo `isdigit()` e o `int()` o recusa, e o número de 5.000 dígitos passa
    pelos dois guardas. Uma régua só, ao lado das outras da web, para a
    próxima tela não escrever a sua (o `ri_web` a reexporta com o mesmo nome).
    Sinal, ponto e espaço no meio não são número de ninguém aqui: id, página,
    quantidade e ano são todos inteiros a partir de zero.

    `maximo` é o maior que ainda faz sentido no lugar — a página de uma lista
    (`PAGINA_MAIS_ALTA`), que o OFFSET multiplica. Acima dele, None, como o
    que não é número.
    """
    bruto = ("" if texto is None else str(texto)).strip()
    if not (bruto.isascii() and bruto.isdigit()):
        return None
    # Sem os zeros da frente ANTES do `int()`: 5.000 zeros e um 5 também
    # passariam do limite de 4.300 dígitos do Python (achado no LD13).
    algarismos = bruto.lstrip("0") or "0"
    if len(algarismos) > DIGITOS_DE_UM_NUMERO:
        return None
    numero = int(algarismos)
    if maximo is not None and numero > maximo:
        return None
    return numero


def destino_interno(proximo, padrao: str) -> str:
    """Só caminho RELATIVO DESTE sistema; o resto vai para `padrao`.

    O REDIRECIONAMENTO ABERTO (M1). `/login?next=//fora.exemplo` levava quem
    acabou de entrar de verdade para uma página de fora — que imita a tela de
    «senha expirada» e colhe a senha de novo. Vale `/algo`; não vale `//host`
    (o navegador lê como outro site), `/\\host` (idem, no Chrome), esquema
    (`http:`, `javascript:`) nem caractere de controle: o navegador apaga
    TAB e quebra de linha do endereço, e `/<TAB>/fora` vira `//fora`.
    """
    texto = str(proximo or "")
    if (not texto.startswith("/") or texto.startswith("//") or "\\" in texto
            or any(ord(c) < 0x20 or ord(c) == 0x7F for c in texto)):
        return padrao
    partes = urlsplit(texto)
    if partes.scheme or partes.netloc:
        return padrao
    return texto


def volta_do_referer(referer, host: str, padrao: str) -> str:
    """A tela de onde o clique saiu, pelo `Referer` — só se for DESTA casa.

    O Referer é endereço inteiro (`http://servidor:8765/avisos`); vale o
    caminho dele quando o servidor é este, e o resto cai em `padrao`.
    """
    partes = urlsplit(str(referer or ""))
    if partes.scheme not in ("http", "https") or partes.netloc != host:
        return padrao
    caminho = partes.path + (f"?{partes.query}" if partes.query else "")
    return destino_interno(caminho, padrao)


def recado_de_erro(erro: BaseException, onde: str,
                   frase: str = "Não foi possível concluir. O detalhe ficou "
                                "no registro do servidor; se repetir, avise "
                                "o administrador.") -> str:
    """A frase fixa para a tela; o texto da exceção vai para o log (B2).

    `str(erro)` de um `except Exception` mostrava a quem está logado o texto
    do banco, o nome da tabela e o caminho do arquivo no servidor. Quem
    conserta precisa do detalhe; quem está no balcão, não.
    """
    _LOG.error("%s: %s: %s", onde, type(erro).__name__, erro,
               exc_info=(type(erro), erro, erro.__traceback__))
    return frase


def erro_do_modelo(erro: BaseException, onde: str, com_tipo: bool = False) -> str:
    """O erro do MODELO aparece; o resto vira a frase fixa (B2).

    O `except Exception` em volta de `render_modelo` pega duas coisas. O
    erro do Jinja (`{{ x` sem fechar, variável que não existe) é do texto que
    a própria pessoa escreveu na tela de Modelos, e só ela o conserta: esse
    continua na tela, como sempre. Qualquer outro (banco, arquivo) é da casa
    — vai para o log, e a tela diz só que não deu.
    """
    from jinja2 import TemplateError
    if isinstance(erro, TemplateError):
        return f"{type(erro).__name__}: {erro}" if com_tipo else str(erro)
    return recado_de_erro(erro, onde)
