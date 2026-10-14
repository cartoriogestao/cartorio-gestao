"""
Conferencia das matriculas digitadas em Word contra o acervo do sistema.

DE ONDE VEM O ARQUIVO
    De `ri_doc_extrair.py`, que le a pasta das matriculas digitadas e produz
    `matriculas_doc.jsonl`. Enquanto os arquivos estavam no Proton Drive em
    modo "sob demanda", so a maquina da serventia conseguia abri-los; depois
    que a pasta baixou por inteiro, a leitura passou a funcionar de qualquer
    lugar que enxergue o caminho.

O QUE ESTE MODULO FAZ
    Compara, matricula a matricula, o texto digitado em Word com o teor que
    esta no sistema, e classifica cada caso:

      NOVA        numero que nao existe no sistema — candidata a inclusao
      SO_NO_DOC   o sistema tem a matricula, mas sem teor nenhum
      AMBIGUA     o numero aparece em mais de um livro do acervo
      AMPLIADA    o Word contem tudo o que o sistema tem, e continua
      IGUAL       os dois textos dizem a mesma coisa
      DIVERGENTE  os dois tem texto e eles se contradizem
      VAZIA       o arquivo em Word nao tem texto util

    AMPLIADA existe porque foi o caso mais comum do acervo: a carga do
    E-Oficio trouxe a abertura da matricula e parou ali, enquanto o arquivo
    digitado tem tambem o titulo aquisitivo, o valor, o fecho e as averbacoes.
    Nesses, carregar o Word acrescenta e nao apaga — o que ja estava continua
    inteiro dentro do texto novo. E diferente de DIVERGENTE, onde os dois
    afirmam coisas incompativeis e alguem tem de ir ao livro.

O QUE ELE NAO FAZ
    Nao decide qual versao vale. Matricula e ato registral: quem confere e o
    registrador, contra o livro. O sistema separa, mede e mostra lado a lado.
"""
from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Iterator

# Abaixo disto, os textos sao considerados diferentes o bastante para conferir
# a olho. Acima, tratamos como o mesmo texto com variacao de digitacao.
LIMIAR_IGUAL = 0.92
TEXTO_MINIMO = 40

# Quanto do teor do sistema precisa reaparecer no arquivo em Word para que
# substituir seja acrescentar. Nao e 1,00 porque a carga do E-Oficio traz
# residuo de marcacao e quebra de palavra que a digitacao nao repete.
LIMIAR_CONTIDO = 0.97

# Teor de matricula com quarenta anos de averbacao chega a 280 mil letras, e o
# alinhamento do difflib e quadratico: um unico par desse tamanho leva minutos.
# Por isso a comparacao tem dois estagios — primeiro o peso das palavras, que e
# linear e ja separa o que e outro texto; depois, so no que sobrou, o
# alinhamento caractere a caractere numa janela do inicio, que e onde estao a
# descricao do imovel e o registro de origem.
JANELA_ALINHAMENTO = 6_000


def normalizar(texto: str | None) -> str:
    """Tira marcacao, acento, caixa e espaco repetido.

    A comparacao tem de sobreviver a diferenca de digitacao, nao a diferenca
    de conteudo: 'JOSE' e 'José' sao a mesma pessoa; 147 ha e 174 ha nao.
    """
    if not texto:
        return ""
    t = re.sub(r"<[^>]+>", " ", texto)
    t = unicodedata.normalize("NFD", t)
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = t.lower()
    t = re.sub(r"[^\w\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def semelhanca(a: str, b: str) -> float:
    """Quanto os dois textos se parecem, de 0 a 1. Pelo peso das palavras.

    Linear no tamanho do texto, e por isso e esta que roda no lote inteiro.
    Dois teores da mesma matricula usam as mesmas palavras nas mesmas
    quantidades, ainda que a digitacao mude a pontuacao ou a ordem de uma
    frase; teores de matriculas diferentes, nao.

    Mede-se pelo indice de Sorensen-Dice sobre o multiconjunto de palavras:
    duas vezes o que ha em comum, dividido pelo tamanho somado dos dois. Uma
    palavra que aparece tres vezes num texto e uma no outro conta uma vez.
    """
    if not a or not b:
        return 0.0
    ca, cb = Counter(a.split()), Counter(b.split())
    if not ca or not cb:
        return 0.0
    comum = sum((ca & cb).values())
    return round(2 * comum / (sum(ca.values()) + sum(cb.values())), 3)


def contido(dentro: str, fora: str) -> float:
    """Quanto de `dentro` reaparece em `fora`, de 0 a 1.

    Serve para reconhecer o caso do acervo: o teor do sistema termina onde a
    carga do E-Oficio parou, e o arquivo digitado segue adiante com o titulo
    aquisitivo, o fecho e as averbacoes. Se quase toda palavra do sistema
    reaparece no Word, nada se perde ao substituir.

    Conta repeticao: se o sistema diz 'Miranda' tres vezes e o Word so uma,
    duas ficaram de fora e o indice cai.
    """
    if not dentro:
        return 0.0
    cd, cf = Counter(dentro.split()), Counter(fora.split())
    return round(sum((cd & cf).values()) / sum(cd.values()), 3)


def semelhanca_fina(a: str, b: str) -> float:
    """Alinhamento caractere a caractere, para UM par, na tela.

    O difflib e quadratico: nos 1.477 pares do acervo levaria horas, e por
    isso nao entra no lote. Aqui serve para a confrontacao lado a lado de uma
    matricula so, onde o custo e de um par e a precisao ajuda a decidir.
    """
    if not a or not b:
        return 0.0
    s = SequenceMatcher(None, a[:JANELA_ALINHAMENTO], b[:JANELA_ALINHAMENTO],
                        autojunk=False)
    if s.real_quick_ratio() < LIMIAR_IGUAL - 0.15:
        return round(s.real_quick_ratio(), 3)
    return round(s.ratio(), 3)


def ler_jsonl(caminho: str | Path) -> Iterator[dict]:
    with open(caminho, encoding="utf-8", errors="replace") as fh:
        for linha in fh:
            linha = linha.strip()
            if linha:
                yield json.loads(linha)


def conferir(caminho: str | Path, matriculas_sistema: dict[str, dict],
             ambiguos: set[str] | None = None) -> list[dict]:
    """Compara o arquivo com o acervo.

    `matriculas_sistema` e {numero: {"id":..., "teor":..., "tipo_ficha":...}}.

    `ambiguos` sao os numeros que aparecem MAIS DE UMA VEZ no acervo. O acervo
    tem a matricula 8 duas vezes, uma no Livro 2-A e outra no Livro 2S — cada
    livro reinicia a numeracao, e o numero sozinho deixa de identificar. Nesses
    casos nao ha contra o que comparar sem escolher um livro, e escolher livro
    e ato do registrador: a linha sai como AMBIGUA e nao entra na carga.
    """
    ambiguos = ambiguos or set()
    saida: list[dict] = []
    for reg in ler_jsonl(caminho):
        numero = str(reg.get("numero") or "").strip()
        texto = reg.get("texto") or ""
        n_doc = normalizar(texto)
        m = matriculas_sistema.get(numero)

        # Normaliza o teor do sistema UMA vez: em 2.768 comparacoes, fazer
        # duas vezes o mesmo trabalho custa o dobro do tempo por nada.
        n_sis = normalizar(m.get("teor")) if m else ""

        if len(n_doc) < TEXTO_MINIMO:
            situacao, sem = "VAZIA", 0.0
        elif numero in ambiguos:
            situacao, sem = "AMBIGUA", 0.0
        elif not m:
            situacao, sem = "NOVA", 0.0
        elif len(n_sis) < TEXTO_MINIMO:
            situacao, sem = "SO_NO_DOC", 0.0
        else:
            sem = semelhanca(n_doc, n_sis)
            if sem >= LIMIAR_IGUAL:
                situacao = "IGUAL"
            elif (contido(n_sis, n_doc) >= LIMIAR_CONTIDO
                  and len(n_doc) > len(n_sis)):
                situacao = "AMPLIADA"
            else:
                situacao = "DIVERGENTE"

        saida.append({
            "numero": numero,
            "arquivo": reg.get("arquivo"),
            "versoes": reg.get("versoes"),
            "bytes": reg.get("bytes"),
            "alterado": reg.get("alterado"),
            "letras_doc": len(n_doc),
            "letras_sistema": len(n_sis),
            "matricula_id": m.get("id") if m else None,
            "semelhanca": sem,
            "contido": contido(n_sis, n_doc) if n_sis else 0.0,
            "situacao": situacao,
            "texto": texto,
        })
    saida.sort(key=lambda r: (r["situacao"], int(r["numero"]) if r["numero"].isdigit() else 0))
    return saida


def resumo(linhas: list[dict]) -> dict[str, int]:
    r: dict[str, int] = {}
    for l in linhas:
        r[l["situacao"]] = r.get(l["situacao"], 0) + 1
    return r


def teor_html(texto: str) -> str:
    """Vira paragrafos simples, preservando as quebras do documento.

    Sem tentar adivinhar estrutura: o que veio digitado em Word entra como
    esta, e a conferencia contra o livro decide o resto.
    """
    linhas = [l.strip() for l in (texto or "").split("\n")]
    return "\n".join(f"<p>{_escapa(l)}</p>" for l in linhas if l)


def _escapa(t: str) -> str:
    return (t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
