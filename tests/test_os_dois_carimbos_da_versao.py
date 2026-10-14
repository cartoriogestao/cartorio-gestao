"""OS DOIS CARIMBOS DA VERSÃO TÊM DE DIZER A MESMA COISA.

    «Ao subir versão: `VERSION` em `app.py` **e** `VERSAO.txt`, os dois.»
      — a regra escrita deste projeto, em `CLAUDE.md`

POR QUE ISTO NASCEU — 16/09/2026, e custou uma atualização com cara de
quebrada. O oficial aplicou a **3.6.138** e o reinício do servidor avisou:

    ATENCAO: quem respondeu esta na versao 3.6.137, e a instalada e 3.6.138.

A atualização tinha funcionado: medido arquivo por arquivo, **504 de 505
batiam byte a byte** com a árvore. O que não batia eram os dois carimbos entre
si — `VERSAO.txt` e `install.json` diziam 3.6.138, e `app.py` continuava em
`VERSION = "3.6.137"`. Quem empacotou subiu um e esqueceu o outro.

E O AVISO ESTAVA CERTO, e é isso que faz este teste valer. O guarda do
reinício nasceu na 3.6.136 para pegar «o disco tem a versão nova e quem
responde é o processo velho» — um defeito que já aconteceu aqui e que é
**invisível de qualquer outra forma**. Ele não tem como distinguir *processo
velho* de *carimbo esquecido*: os dois se parecem exatamente assim de fora.

**O CUSTO DE UM ALARME QUE SOA SEM DEFEITO É ELE DEIXAR DE SER OUVIDO** — e
este alarme guarda a hipótese mais cara da casa, a de o balcão estar rodando
código que ninguém acha que está lá. Por isso a conferência é aqui, antes de o
pacote sair, e não lá, depois de ele ser aplicado.

**A COMPARAÇÃO É ENTRE OS DOIS ARQUIVOS DA ÁRVORE**, e não contra um número
escrito neste teste: número escrito num teste envelhece na tarde em que se
escreve, e este projeto já pagou por isso — a primeira linha do `CLAUDE.md`
envelheceu **cinco vezes**.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))


def _versao_do_app() -> str:
    """Lê o literal, sem importar o `app` — importar sobe o sistema inteiro."""
    achado = re.search(r'^VERSION\s*=\s*"([^"]+)"',
                       (RAIZ / "app.py").read_text(encoding="utf-8"),
                       re.MULTILINE)
    assert achado, "app.py não tem mais uma linha `VERSION = \"...\"`"
    return achado.group(1)


def _versao_do_txt() -> str:
    return (RAIZ / "VERSAO.txt").read_text(encoding="utf-8").strip()


def test_o_app_e_o_txt_dizem_a_mesma_versao():
    """É o `app.py` que responde no `/saude`; é o `.txt` que o instalador lê."""
    do_app, do_txt = _versao_do_app(), _versao_do_txt()
    assert do_app == do_txt, (
        f"`app.py` diz {do_app} e `VERSAO.txt` diz {do_txt}. Quem sobe versão "
        f"sobe os dois — senão o servidor responde um número, a instalação "
        f"carimba outro, e o reinício avisa «quem respondeu está na versão "
        f"velha» sobre um processo que está novo")


def test_a_versao_tem_a_forma_de_versao():
    """Carimbo torto é carimbo que ninguém compara."""
    for nome, valor in (("app.py", _versao_do_app()),
                        ("VERSAO.txt", _versao_do_txt())):
        assert re.fullmatch(r"\d+\.\d+\.\d+", valor), (
            f"{nome} carimbou {valor!r}, que não tem a forma `3.6.138`")
