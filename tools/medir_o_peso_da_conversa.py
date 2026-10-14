"""Quanto pesa a conversa de uma sessão do agente, turno a turno. **SÓ LÊ.**

POR QUE ISTO EXISTE, E ELE NASCEU DOS PROBLEMAS #68 E #74.

A conversa INTEIRA vai ao provedor a CADA turno — é assim que um modelo de
linguagem conversa. Então o gasto de uma sessão não é o tamanho do que ela leu:
é a SOMA do tamanho da conversa em cada ponto em que o modelo foi chamado. Duas
coisas quebraram por causa disso, e as duas foram relatadas pelo oficial:

  #68 — a sessão 1 do console gastou 1.395.475 tokens de entrada e parou no
        teto sem ter concluído nada. Os 240.095 caracteres que ela leu foram
        reenviados 28 vezes e somaram 4.420.607.
  #74 — a maior requisição daquela sessão subiu com 256.965 caracteres, e
        requisição grande é o que faz o provedor demorar mais que o prazo: o
        turno estourou o timeout duas vezes seguidas, 242 s no total.

O QUE O PROGRAMA FAZ: reconstrói a conversa com o `agente._conversa` — a função
de verdade do módulo, e não uma cópia — em cada ponto de chamada, e mede as duas
versões: a que subia antes (sem poda) e a que sobe agora (`agente._poupar`).

O QUE ELE IMPRIME, E O QUE CADA NÚMERO RESPONDE:

  * a SOMA reenviada nos dois mundos — é a conta do #68, e a economia da poda;
  * o MAIOR ponto de chamada nos dois mundos — **é a conta do #74**, porque o
    que estoura o prazo não é a soma, é o maior envio;
  * o câmbio de caracteres por token desta instalação, tirado do
    `tokens_de_entrada` que ela declarou ter pagado.

USO:

    python tools/medir_o_peso_da_conversa.py            # a sessão mais pesada
    python tools/medir_o_peso_da_conversa.py 1          # a sessão 1

NÃO ESCREVE NADA: abre o banco em modo somente leitura e não toca em arquivo.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import agente  # precisa da raiz no caminho

BANCO_PADRAO = r"C:\ProgramData\CartorioGestao\cartorio_gestao.sqlite3"


def _pontos_de_chamada(passos: list[dict]) -> list[int]:
    """Em que passo do histórico a conversa é enviada ao provedor.

    São dois momentos, e são os dois que a conversa tem: logo depois de um
    pedido do oficial, e logo depois do fim de um grupo de resultados — que é
    quando o turno anterior acabou. Contar por `tipo` e não por número de linha
    é o que faz isto valer para qualquer sessão.
    """
    pontos: set[int] = set()
    total = len(passos)
    for i, passo in enumerate(passos):
        if passo["tipo"] == "PEDIDO":
            pontos.add(i + 1)
        elif passo["tipo"] == "RESULTADO":
            seguinte = i
            while seguinte < total and passos[seguinte]["tipo"] == "RESULTADO":
                seguinte += 1
            pontos.add(seguinte)
    return sorted(pontos)


def medir(passos: list[dict], podar: bool) -> list[int]:
    """O tamanho da conversa em cada ponto de chamada, com ou sem a poda.

    **A PODA É APLICADA AQUI, E NÃO DENTRO DO `_conversa`** — e é isto que faz a
    medição ser fiel ao que o sistema faz hoje: o módulo poda no ponto em que
    fala com o provedor (`_rodar`), e não na tradução, porque a tradução também
    monta a conversa que o console DESENHA. Podar lá dentro faria a tela mostrar
    um resumo onde o resultado inteiro está guardado.
    """

    def tamanho(k: int) -> int:
        conversa = agente._conversa([], passos[:k])
        if podar:
            conversa = agente._poupar(conversa)
        return len(json.dumps(conversa, ensure_ascii=False))

    return [tamanho(k) for k in _pontos_de_chamada(passos)]


def _milhar(n: float) -> str:
    return f"{int(n):,}".replace(",", ".")


def main(argv: list[str]) -> int:
    con = sqlite3.connect(f"file:{BANCO_PADRAO}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row

    if len(argv) > 1:
        sessao_id = int(argv[1])
    else:
        linha = con.execute(
            "SELECT id FROM ag_sessoes "
            "ORDER BY (tokens_de_entrada + tokens_de_saida) DESC LIMIT 1").fetchone()
        if linha is None:
            print("Não há sessão nenhuma gravada neste banco.")
            return 0
        sessao_id = int(linha["id"])

    sessao = con.execute("SELECT * FROM ag_sessoes WHERE id = ?",
                         (sessao_id,)).fetchone()
    if sessao is None:
        print(f"Não existe sessão {sessao_id} neste banco.")
        return 1
    passos = [dict(p) for p in con.execute(
        "SELECT * FROM ag_passos WHERE sessao_id = ? ORDER BY ordem", (sessao_id,))]

    print(f"=== a sessão {sessao_id}, como ela está gravada ===")
    print("estado={} turnos={} entrada={} saida={}".format(
        sessao["estado"], sessao["turnos"], sessao["tokens_de_entrada"],
        sessao["tokens_de_saida"]))
    lidos = sum(len(str(p.get("conteudo") or "")) + len(str(p.get("argumentos") or ""))
                for p in passos)
    print(f"passos={len(passos)} caracteres_gravados={_milhar(lidos)}")

    pontos = _pontos_de_chamada(passos)
    if not pontos:
        print("\nEsta sessão não tem um ponto de chamada — não há o que medir.")
        return 0
    sem = medir(passos, podar=False)
    com = medir(passos, podar=True)

    print()
    print("=== a conta do #68: o que se reenvia, somado ===")
    print(f"chamadas ao provedor: {len(pontos)}")
    print(f"SOMA reenviada, sem poda: {_milhar(sum(sem)):>12} caracteres")
    print(f"SOMA reenviada, com poda: {_milhar(sum(com)):>12} caracteres")
    print(f"economia: {100 * (1 - sum(com) / max(sum(sem), 1)):.1f}%")
    if lidos:
        # **O NÚMERO QUE SE LÊ EM VOZ ALTA.** «A soma é N vezes o que a sessão
        # leu» é o que explica o gasto a quem não é da área; sem ele, 4.420.607
        # caracteres não dizem nada a ninguém.
        print(f"a soma é {sum(sem) / lidos:.1f} vezes o que a sessão leu "
              f"(com poda: {sum(com) / lidos:.1f} vezes)")

    print()
    print("=== a conta do #74: o MAIOR envio, que é o que estoura o prazo ===")
    # **A COMPARAÇÃO É NO MESMO PONTO DE CHAMADA.** Comparar `max(sem)` com
    # `max(com)` misturaria dois pontos diferentes e daria uma porcentagem que
    # não descreve nem um nem outro — é o carimbo que mente na forma de conta.
    # O maior envio de antes é o passo que estourava o prazo; o que interessa é
    # quanto ELE encolheu.
    i = max(range(len(sem)), key=lambda k: sem[k])
    print(f"maior ponto: o passo {pontos[i]}, sem poda: {_milhar(sem[i]):>12} caracteres")
    print(f"o MESMO ponto, com poda:                     "
          f"{_milhar(com[i]):>12} caracteres")
    print(f"o maior envio encolheu: {100 * (1 - com[i] / max(sem[i], 1)):.1f}%")
    if max(com) > com[i]:
        print(f"   e o maior ponto DEPOIS da poda é outro — o passo "
              f"{pontos[com.index(max(com))]}, com {_milhar(max(com))}")

    declarado = int(sessao["tokens_de_entrada"] or 0)
    if declarado and sum(sem):
        print()
        print("=== o câmbio desta instalação ===")
        print(f"tokens_de_entrada declarados: {_milhar(declarado):>12}")
        print(f"caracteres por token: {sum(sem) / declarado:.2f}")

    print()
    print("=== os dez maiores pontos de chamada ===")
    for k, n in sorted(zip(pontos, sem), key=lambda par: -par[1])[:10]:
        print(f"   até o passo {k:>3}: {_milhar(n):>10} caracteres  "
              f"(com poda: {_milhar(com[pontos.index(k)]):>8})")

    podada = agente._poupar(agente._conversa([], passos))
    texto = sum(len(e.get("texto") or "") for e in podada
                if e["tipo"] in ("user", "assistant"))
    restos = sum(len(str(r.get("conteudo") or "")) for e in podada
                 if e["tipo"] == "tool" for r in (e.get("resultados") or []))
    print()
    print("=== do que sobra na conversa podada do fim ===")
    print(f"   o que o oficial e o modelo escreveram: {_milhar(texto):>10}")
    print(f"   resultados de ferramenta inteiros    : {_milhar(restos):>10}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
