"""NENHUM SCRIPT DA CASA TEM TEXTO PARTIDO POR UMA QUEBRA DE LINHA CRUA
(29/10/2026).

O defeito: o `whatsapp_chat.js` do #94 saiu com `"` + quebra de linha
de verdade + `"` onde devia estar `"\\n"` — a contrabarra se perdeu no script
que gravou o arquivo. Em JavaScript isso é erro de sintaxe, e o navegador
recusa O ARQUIVO INTEIRO: a conversa abria no topo em vez da última mensagem,
não se atualizava sozinha e o Ctrl+Enter não enviava. Nenhum teste Python via,
porque nenhum lê o `.js`; quem viu foi o oficial, no balcão.

A régua é estreita de propósito: uma linha que termina abrindo aspas depois de
um `+` e a seguinte que começa fechando-as. Um leitor de JS completo acusaria
as expressões regulares com aspas dentro (`/[&<>"']/`), que são legítimas.
"""
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
TEXTO_PARTIDO = re.compile(r'\+\s*"[ \t]*\r?\n[ \t]*"')


def test_nenhum_js_tem_texto_partido_por_quebra_crua():
    achados = []
    for arquivo in sorted((RAIZ / "static").glob("*.js")):
        conteudo = arquivo.read_text(encoding="utf-8")
        for m in TEXTO_PARTIDO.finditer(conteudo):
            linha = conteudo.count("\n", 0, m.start()) + 1
            achados.append(f"{arquivo.name}:{linha}")
    assert not achados, (
        "texto entre aspas partido por quebra de linha crua (use \\n): "
        + ", ".join(achados))


def test_a_regua_pega_o_defeito_que_a_criou():
    assert TEXTO_PARTIDO.search('a.replace(/x/, "") + "\r\n" + pronto')
    assert not TEXTO_PARTIDO.search('a.replace(/x/, "") + "\\n" + pronto')
