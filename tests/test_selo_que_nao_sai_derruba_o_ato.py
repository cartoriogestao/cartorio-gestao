"""SELO QUE NÃO SAI NÃO DEIXA ATO DE PÉ — nas seis atribuições.

    «se falhar o selo, sempre suspender o ato para corrigir o problema (...)
     nao precisa manter essa caixa de selecao em nenhum servico ou modulo»
      — o oficial, relato #77, 16/09/2026

    «a regra do item 1 deve servir para todas atribuicoes» — ele, no mesmo dia

POR QUE ISTO É UM VARREDOR, E NÃO UM TESTE DE TELA. A regra vale em **quinze
lugares** — Protesto, RCPN (assento, ato, averbação de CPF, certidão),
RCPJ/RTD (registro, ato, certidão), Notas (cartão, reconhecimento,
autenticação, sinal), habilitação de casamento e a certidão do RI —, e um
teste de tela por lugar não impede o décimo sexto de nascer com um desvio. O
que impede é **medir a família inteira**, com piso: varredor que deixa de
achar passa calado, e no dia do defeito de verdade ele não diz nada.

O QUE ELE PROVA, EM TRÊS PEDAÇOS:

  1. **Toda falha de selo desfaz o ato e volta** — o bloco que grava
     `..._SELO_FALHOU` termina em `return`, e não tem `else`. Sem o `return`,
     o programa seguiria adiante e o ato ficaria de pé depois de a tela dizer
     que não ficou: o pior dos dois mundos, porque o escrevente vai embora
     achando que não lavrou.
  2. **Não há desvio** — nenhuma daquelas decisões pergunta a ninguém se pode
     seguir assim mesmo. A caixa «lavrar mesmo se o selo falhar» saiu das
     telas e dos motores em 16/09; este teste é o que impede a volta dela pela
     porta de trás, que é um `and not alguma_coisa()` acrescentado sem querer.
  3. **Nenhuma marca de auditoria diz «por decisão»** — ninguém decide mais
     nada, e rastro que nomeia uma decisão inexistente é o carimbo que mente
     no único lugar desta casa que não se reescreve. Medido na produção em
     16/09: há **uma** linha `RI_ATO_LAVRADO_SEM_SELO_POR_DECISAO`, de 15/09
     às 22h23, e o motivo dela é «Os nomes das partes devem ser informados» —
     recusa do envelope, e não decisão de ninguém. Ela fica onde está; o que
     não pode é nascer outra.

**A LEITURA É PELA ÁRVORE (`ast`), E NÃO PELO TEXTO.** Um varredor que
procurasse as palavras bateria nos comentários que explicam por que elas não
existem mais — é o que já aconteceu **catorze vezes** neste projeto, e a
décima primeira foi exatamente com um número citado em comentário.

O QUE ESTE ARQUIVO **NÃO** COBRE, e está dito de propósito: o **ato do RI**,
que não grava `..._SELO_FALHOU` — ele *suspende*, devolvendo o trabalho à
minuta, e tem arquivo próprio em `test_ri_selo_que_nao_sai_suspende_o_ato.py`.
E a **única exceção da casa**, decidida por ele no mesmo dia: o ato de ACERVO
sem item de custa, onde quem atende não tem como corrigir.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

# OS MÓDULOS QUE LAVRAM E SELAM. O ato do RI não está aqui — ver o cabeçalho.
MODULOS = ("atribuicoes_web.py", "habilitacao_web.py", "notas_web.py",
           "ri_web.py")

# O PISO É MEDIDO, e não estimado — contado na árvore em 16/09/2026.
#
#   Ele existe porque varredor que deixa de achar passa calado: sem piso, um
#   `endswith` trocado por engano varreria zero lugares e diria «tudo certo».
QUANTOS_LUGARES = {"atribuicoes_web.py": 9, "habilitacao_web.py": 1,
                   "notas_web.py": 4, "ri_web.py": 1}

# Os nomes que o desvio teve enquanto existiu. Estão aqui para ninguém os
# reintroduzir sem o teste perceber.
NOMES_DO_DESVIO = ("manter_sem_selo", "_lavrar_sem_selo_confirmado")


def _arvore(modulo: str) -> ast.Module:
    return ast.parse((RAIZ / modulo).read_text(encoding="utf-8"))


def _marcas_de(no: ast.AST) -> list[str]:
    """As marcas de auditoria gravadas dentro deste nó. Lê a ÁRVORE."""
    return [c.args[0].value for c in ast.walk(no)
            if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
            and c.func.id == "audit" and c.args
            and isinstance(c.args[0], ast.Constant)
            and isinstance(c.args[0].value, str)]


def _blocos_da_falha(modulo: str) -> list[ast.If]:
    """Os `if` que gravam «o selo não saiu», sem repetir os aninhados."""
    achados = [no for no in ast.walk(_arvore(modulo))
               if isinstance(no, ast.If)
               and any(m.endswith("_SELO_FALHOU") for m in _marcas_de(no))]
    # UM `if` DENTRO DE OUTRO CONTA UMA VEZ: o de fora enxerga a marca do de
    # dentro, e contar os dois inventaria lugares que não existem.
    de_dentro = {id(x) for fora in achados
                 for x in ast.walk(fora) if isinstance(x, ast.If) and x is not fora}
    return [no for no in achados if id(no) not in de_dentro]


@pytest.mark.parametrize("modulo", MODULOS)
def test_a_falha_do_selo_desfaz_o_ato_e_volta(modulo):
    """Sem o `return`, o ato ficaria de pé depois de a tela dizer que não."""
    blocos = _blocos_da_falha(modulo)
    for no in blocos:
        marca = next(m for m in _marcas_de(no) if m.endswith("_SELO_FALHOU"))
        assert any(isinstance(x, ast.Return) for x in ast.walk(no)), (
            f"{modulo}, linha {no.lineno} ({marca}): o bloco da falha do selo "
            f"não volta — o ato seguiria de pé com a tela dizendo que não")
        assert not no.orelse, (
            f"{modulo}, linha {no.lineno} ({marca}): apareceu um `else` no "
            f"caminho da falha do selo, que é por onde um desvio volta")


@pytest.mark.parametrize("modulo", MODULOS)
def test_o_numero_de_lugares_nao_encolheu(modulo):
    """Varredor que deixa de achar passa calado — por isso há piso."""
    quantos = len(_blocos_da_falha(modulo))
    assert quantos >= QUANTOS_LUGARES[modulo], (
        f"{modulo}: o varredor achou {quantos} lugares e havia "
        f"{QUANTOS_LUGARES[modulo]} em 16/09/2026. Ou um caminho de selo "
        f"deixou de desfazer o ato, ou a régua parou de enxergá-lo")


def _literais_de_codigo(arvore: ast.Module) -> set[str]:
    """Os textos que são CÓDIGO — sem docstring, e sem comentário.

    **O COMENTÁRIO NEM CHEGA AQUI**, porque não vira nó da árvore; e a
    docstring se exclui **pelo NÓ**, e não comparando textos: `ast.
    get_docstring` limpa a indentação, e o texto limpo nunca bate com o
    literal cru — comparar textos deixaria toda docstring passar como se
    fosse código. Foi assim que o varredor do `onr_carga` foi consertado.
    """
    docs = set()
    for no in ast.walk(arvore):
        if isinstance(no, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                           ast.ClassDef)):
            corpo = getattr(no, "body", None)
            if (corpo and isinstance(corpo[0], ast.Expr)
                    and isinstance(corpo[0].value, ast.Constant)
                    and isinstance(corpo[0].value.value, str)):
                docs.add(id(corpo[0].value))
    return {n.value for n in ast.walk(arvore)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and id(n) not in docs}


@pytest.mark.parametrize("modulo", MODULOS)
def test_nao_ha_desvio_para_seguir_sem_selo(modulo):
    """A caixa «lavrar mesmo se o selo falhar» saiu — e não volta por trás.

    **A LEITURA É PELA ÁRVORE, e isto custou uma vermelha para ser aprendido
    outra vez.** A primeira versão procurava a palavra no texto do arquivo e
    bateu num comentário de `atribuicoes_web` que dizia «selo falha salvo
    lavrar_sem_selo» — prosa velha, que o mesmo conserto corrigiu. **Décima
    quinta vez** que um varredor desta casa acha a palavra fora do código que
    ele quer medir, e a primeira em que eu a cometi no próprio guarda.
    """
    arvore = _arvore(modulo)
    nomes = {n.id for n in ast.walk(arvore) if isinstance(n, ast.Name)}
    nomes |= {f.name for f in ast.walk(arvore)
              if isinstance(f, ast.FunctionDef)}
    for palavra in NOMES_DO_DESVIO:
        assert palavra not in nomes, (
            f"{modulo}: `{palavra}` voltou. O relato #77 tirou o desvio de "
            f"todo módulo em 16/09/2026")
    assert "lavrar_sem_selo" not in _literais_de_codigo(arvore), (
        f"{modulo}: o campo do formulário `lavrar_sem_selo` voltou a ser lido")


@pytest.mark.parametrize("modulo", MODULOS)
def test_nenhuma_marca_de_auditoria_diz_por_decisao(modulo):
    """Ninguém decide mais nada — e o rastro não pode dizer que sim."""
    ruins = [m for m in _marcas_de(_arvore(modulo)) if m.endswith("_POR_DECISAO")]
    assert not ruins, (
        f"{modulo}: {', '.join(ruins)} — a marca nomeia uma decisão que não "
        f"existe desde o relato #77, e o rastro é o que a correição lê")
