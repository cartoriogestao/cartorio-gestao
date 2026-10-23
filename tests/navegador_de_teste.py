"""O POST que segue o redirecionamento COMO O NAVEGADOR — lote LX11, 19/10/2026.

POR QUE EXISTE
    Desde o LX11 (M8 do LS01) a etiqueta do RCPJ/RTD é POST com o token: GET
    que grava (a contagem de impressões) não passava pelo CSRF. Quem lavra com
    selo é levado a ela por 307, que manda o navegador REENVIAR o mesmo
    formulário — com o token — para o endereço novo.

    O cliente de teste do Werkzeug segue o 307, mas refaz o POST a partir do
    `environ` da primeira requisição, com o corpo já lido: a etiqueta recebe
    um POST vazio e responde «Token CSRF inválido». É defeito do cliente, e
    não da tela; aqui o teste faz o que o navegador faz.

O ARQUIVO NÃO VAI DE NOVO
    O formulário com anexo já gravou o anexo no primeiro POST, e o cliente
    fecha o arquivo depois de mandá-lo. A etiqueta não lê arquivo nenhum: no
    reenvio vão só os campos de texto.
"""
from __future__ import annotations


def _so_texto(dados: dict) -> dict:
    return {k: v for k, v in dados.items()
            if not isinstance(v, tuple) and not hasattr(v, "read")}


def postar_e_seguir(cliente, url: str, dados: dict, **kw):
    """`cliente.post(..., follow_redirects=True)`, com o 307 reenviando o
    formulário e o 301/302/303 virando GET. Devolve a última resposta."""
    r = cliente.post(url, data=dados, **kw)
    for _ in range(10):
        if r.status_code in (307, 308):
            r = cliente.post(r.headers["Location"], data=_so_texto(dados))
        elif r.status_code in (301, 302, 303):
            r = cliente.get(r.headers["Location"])
        else:
            break
    return r
