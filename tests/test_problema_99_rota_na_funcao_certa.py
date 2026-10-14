"""
A ROTA TEM DE ESTAR NA FUNÇÃO CERTA — problema #99, 23/09/2026.

O QUE ACONTECEU
    Às 09h08 foi para o servidor um `atribuicoes_web.py` em que a função
    auxiliar nova `_folha_seguranca_do_form` tinha ficado ENTRE os decoradores
    e a função que eles decoravam:

        @app.route("/rcpn/<int:assento_id>/certidao", methods=["POST"])
        @login_required
        @roles_required(...)
        def _folha_seguranca_do_form() -> str:      # <- a auxiliar pegou a rota
            ...
        def rcpn_certidao_emitir(assento_id: int):  # <- e esta ficou sem nenhuma
            ...

    Python não reclama: decorador vale para o `def` que vem logo abaixo, seja
    ele qual for. O sistema subiu, a rota da certidão passou a se chamar
    `_folha_seguranca_do_form`, e o endpoint `rcpn_certidao_emitir` deixou de
    existir. A ficha de TODO assento do Registro Civil pede esse endpoint no
    botão de emitir certidão — e estourou `BuildError` na cara do balcão
    (assento 8308, Elisa, 09h09:02 e 09h09:15). Consertado às 09h14 pela
    mesma passada, trocando a ordem.

AS DUAS RÉGUAS, E POR QUE SÃO DUAS
    1. **Função com rota não tem nome de auxiliar.** Nesta casa o `_` na frente
       quer dizer «ajudante interno, sem tela». Uma função assim decorada com
       `route` é quase sempre o decorador que escorregou para o `def` errado.
       Lê o código com `ast` — sem subir o sistema, em milissegundos.
    2. **Todo `url_for('nome')` escrito num molde aponta para uma rota que
       existe.** Esta é a que pega o caso MESMO QUE a auxiliar não tivesse
       `_` no nome: o que quebrou o balcão foi o molde pedir um endpoint que
       sumiu, e é exatamente isso que ela confere, contra o `url_map` do app
       montado de verdade.

    A primeira diz ONDE está o erro; a segunda garante que ele não chega à
    tela. Nenhuma das duas depende da outra.

O QUE ELAS NÃO PEGAM
    `url_for(variavel)` — endpoint montado em tempo de execução — não se
    confere lendo o molde. A régua conta só o que está escrito entre aspas.
"""
from __future__ import annotations

import ast
import functools
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

# Um literal entre aspas logo depois de `url_for(`. `static` é do Flask.
_URL_FOR = re.compile(r"""url_for\(\s*['"]([A-Za-z_][\w.]*)['"]""")


@functools.lru_cache(maxsize=1)
def _funcoes_com_rota() -> tuple:
    """(arquivo, nome da função, linha) de toda função decorada com `route`.

    `utf-8-sig` porque há módulos desta casa gravados com BOM, e o Python os
    importa normalmente — a régua não pode pular justamente esses.
    """
    achadas = []
    for py in sorted(RAIZ.glob("*.py")):
        arvore = ast.parse(py.read_text(encoding="utf-8-sig"), filename=str(py))
        for no in ast.walk(arvore):
            if not isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in no.decorator_list:
                alvo = dec.func if isinstance(dec, ast.Call) else dec
                if isinstance(alvo, ast.Attribute) and alvo.attr == "route":
                    achadas.append((py.name, no.name, no.lineno))
                    break
    return tuple(achadas)


def test_a_regua_enxerga_as_rotas_da_casa():
    """Varredor que deixa de achar passa calado. Medido em 23/09/2026: 549."""
    assert len(_funcoes_com_rota()) >= 500


def test_funcao_com_rota_nao_tem_nome_de_auxiliar():
    """O #99 exato: `_folha_seguranca_do_form` recebendo a rota da certidão."""
    auxiliares = [f"{arq}:{linha} {nome}"
                  for arq, nome, linha in _funcoes_com_rota()
                  if nome.startswith("_")]
    assert not auxiliares, (
        "estas funções auxiliares receberam uma rota — quase sempre é o "
        "decorador que escorregou para o `def` de cima (problema #99):\n    "
        + "\n    ".join(auxiliares))


def test_a_rota_da_certidao_do_rcpn_e_a_funcao_de_emitir():
    """O caso que quebrou o balcão, dito com o nome dele."""
    donos = [nome for arq, nome, _ in _funcoes_com_rota()
             if arq == "atribuicoes_web.py" and nome == "rcpn_certidao_emitir"]
    assert donos == ["rcpn_certidao_emitir"]


def test_a_rota_da_certidao_do_ri_e_a_funcao_de_emitir():
    """Problema #113 — mesma armadilha do #99, em `ri_web.py` (HOTFIX-2026-09-28-01)."""
    donos = [nome for arq, nome, _ in _funcoes_com_rota()
             if arq == "ri_web.py" and nome == "ri_emitir_certidao"]
    assert donos == ["ri_emitir_certidao"]


def _endpoints_pedidos_pelos_moldes() -> dict[str, list[str]]:
    pedidos: dict[str, list[str]] = {}
    for html in sorted((RAIZ / "templates").rglob("*.html")):
        texto = html.read_text(encoding="utf-8-sig")
        for m in _URL_FOR.finditer(texto):
            linha = texto.count("\n", 0, m.start()) + 1
            pedidos.setdefault(m.group(1), []).append(
                f"{html.relative_to(RAIZ).as_posix()}:{linha}")
    return pedidos


def test_todo_endpoint_escrito_num_molde_existe(cg_app):
    """**A régua que teria impedido o #99 de chegar à tela.**

    O molde da ficha pedia `rcpn_certidao_emitir`, e o app montado não o
    tinha. Aqui o app é montado como o servidor o monta, e cada nome escrito
    entre aspas num `url_for` dos moldes é procurado no `url_map`.
    """
    existentes = {r.endpoint for r in cg_app.url_map.iter_rules()}
    pedidos = _endpoints_pedidos_pelos_moldes()
    assert len(pedidos) >= 300, "a régua deixou de achar os url_for dos moldes"
    faltando = [f"{ep}  ← {', '.join(onde[:3])}"
                for ep, onde in sorted(pedidos.items())
                if ep not in existentes]
    assert not faltando, (
        "estes moldes pedem endpoints que o sistema não tem — a tela estoura "
        "`BuildError` ao abrir (problema #99):\n    " + "\n    ".join(faltando))
