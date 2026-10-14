"""Preenche as colunas `_norm` que a BUSCA consulta e que ficaram vazias.

O QUE ACONTECEU. A coluna de sufixo `_norm` é derivada: ninguém a digita, e o
arquivo de importação não a traz (o sufixo está em `importar_padrao.
SUFIXOS_DA_MAQUINA` por isso mesmo). Só que quem grava a linha tem de
**lembrar** de derivá-la — e não lembrou:

    · `ri_matriculas.livro_norm` — **1 de 1.982** vazia, e é a ficha 3.110, que
      o importador padrão gravou em 14/09/2026. O defeito é dele, e foi
      consertado no mesmo dia (`importar_padrao.DERIVACOES`). Relato **#55** do
      balcão: a ficha existe, abre pelo número, e **nenhum filtro de livro a
      acha** — procurar «3110» com o filtro do livro 2-Q devolve lista vazia.

    · `ri_matriculas.imovel_norm` — **6 de 1.982** com endereço ou descrição
      preenchidos e a coluna vazia, de cinco origens diferentes (a 3.110 e as
      fichas 4.010, 4.011, 4.016, 4.017 e 4.018). O preenchimento de
      `ri_schema` roda **uma vez só**, quando a coluna nasce; quem a criou
      depois entra sem ela.

    · `ri_partes.nome_norm` — **6 de 3.992** partes com nome e coluna vazia.

POR QUE ESTE ARQUIVO EXISTE, E NÃO UM CLIQUE NA TELA
    É conserto de DADO, e a regra que o produz já foi corrigida no código. Sem
    esta passada, as fichas que já estão gravadas continuariam invisíveis para
    sempre — e é o balcão que paga, procurando uma ficha que o sistema jura que
    não existe.

A RÉGUA É UMA SÓ, E ELA NÃO ESTÁ AQUI
    Este script **não sabe** derivar coluna nenhuma: ele lê `importar_padrao.
    DERIVACOES` — de que campos cada coluna se compõe e com que função da casa
    — e chama a mesma `_derivar` que o importador usa. Duas réguas divergiriam
    no primeiro conserto, e a segunda passaria a gravar diferente da primeira
    sem que ninguém visse; é a lição da `normalizar_nome`, pela enésima vez.

    As duas normalizações de nome desta casa convivem de propósito
    (`pt_schema.normalizar_nome` devolve minúsculas, `ri_schema.
    normalizar_busca` maiúsculas, cada uma com a sua busca) — e é a entrada da
    tabela, e não este script, que decide qual vale em cada coluna.

QUEM MANDA RODAR, E O QUE ELE FAZ
    Só MEDE por padrão: imprime quantas linhas cada coluna ganharia, de que
    origem, e com que valor. Nada é gravado sem `--confirmar` — e com ele tudo
    é impresso antes, mais uma CÓPIA do banco (`VACUUM INTO`), que é o desfazer
    deste passo.

O QUE ELE NÃO FAZ
    · **Não sobrescreve coluna que já tem valor.** Se o que está lá divergir do
      que a função devolve, isso é assunto do oficial — e aparece no relatório
      como divergência, não como conserto.
    · **Não inventa valor onde não há fonte.** Linha sem nenhum dos campos de
      origem fica como está: coluna derivada de nada seria um vazio disfarçado
      de cálculo.
    · Não mexe em data, número, situação nem em nenhuma outra coluna.

COMO USAR
    python tools/preencher_colunas_norm.py "C:\\ProgramData\\CartorioGestao\\cartorio_gestao.sqlite3"
    python tools/preencher_colunas_norm.py "C:\\...\\cartorio_gestao.sqlite3" --confirmar
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import importar_padrao as IMP                                          # noqa: E402


def _colunas_de(con: sqlite3.Connection, tabela: str) -> list[tuple]:
    """As mesmas colunas que o importador lê — nome, obrigatório, padrão, pk.

    **A régua é `importar_padrao._colunas`, e não uma `PRAGMA` escrita aqui.**
    O que `_derivar` espera é a lista com o NOME na posição zero; uma `PRAGMA`
    crua devolve o `cid` ali, e o efeito seria o pior possível: nenhuma coluna
    «encontrada», zero linhas a preencher, e o relatório dizendo que está tudo
    certo. Aconteceu na primeira versão deste arquivo, e quem apanhou foi a
    contagem — que dizia 6 e o script dizia 0.
    """
    return IMP._colunas(con, tabela)


def _casos(con: sqlite3.Connection) -> list[dict]:
    """O que está vazio, o que a régua da casa escreveria, e o que diverge.

    Ela é o corpo do script: as três coisas saem juntas porque a pergunta do
    oficial é uma só — «o que esta coluna deixou de achar, e o que está certo?»
    """
    achados: list[dict] = []
    for (tabela, coluna), (fontes, _funcao) in IMP.DERIVACOES.items():
        colunas = _colunas_de(con, tabela)
        existentes = {c[0] if isinstance(c, (tuple, list)) else c
                      for c in colunas}
        if coluna not in existentes:
            continue
        select = ", ".join(["id", *fontes])
        for linha in con.execute(f'SELECT {select} FROM "{tabela}"'):
            valores = dict(zip(fontes, list(linha)[1:]))
            if not any(IMP._texto(v) for v in valores.values()):
                continue            # sem fonte não há o que derivar
            novinha: dict = dict(valores)
            IMP._derivar(tabela, colunas, novinha)
            certo = novinha.get(coluna, "")
            atual = con.execute(
                f'SELECT "{coluna}" FROM "{tabela}" WHERE id=?',
                (linha["id"],)).fetchone()[0]
            if IMP._texto(atual) == certo or not certo:
                continue
            achados.append({"tabela": tabela, "coluna": coluna,
                            "id": int(linha["id"]), "atual": atual or "",
                            "certo": certo,
                            "era_vazio": not IMP._texto(atual)})
    return achados


def _descricao(con: sqlite3.Connection, achado: dict) -> str:
    """O rótulo humano da linha — o número da ficha, o nome da parte."""
    if achado["tabela"] == "ri_matriculas":
        r = con.execute("SELECT numero, livro, origem FROM ri_matriculas "
                        "WHERE id=?", (achado["id"],)).fetchone()
        return (f"ficha {r['numero']} (Livro {r['livro'] or '—'}, "
                f"origem {r['origem'] or '—'})")
    if achado["tabela"] == "ri_partes":
        r = con.execute("SELECT nome, matricula_id FROM ri_partes "
                        "WHERE id=?", (achado["id"],)).fetchone()
        return f"parte «{r['nome']}» da matrícula id={r['matricula_id']}"
    return f"id={achado['id']}"


def main() -> int:
    # O CONSOLE DO WINDOWS É cp1252, E ESTE SCRIPT ESCREVE PORTUGUÊS. Sem esta
    # linha o `print` estoura com `UnicodeEncodeError` — e o do RI estourou
    # DEPOIS de o banco já estar certo, que é a pior ordem possível: quem lê
    # conclui que nada foi feito.
    for saida in (sys.stdout, sys.stderr):
        try:
            saida.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("banco", help="caminho do arquivo .sqlite3 do sistema")
    ap.add_argument("--confirmar", action="store_true",
                    help="grava de verdade — sem isto, só mostra")
    args = ap.parse_args()

    caminho = Path(args.banco)
    if not caminho.is_file():
        print(f"Não achei o banco em: {caminho}", file=sys.stderr)
        return 1

    con = sqlite3.connect(caminho)
    con.row_factory = sqlite3.Row

    print("=== As colunas que a busca consulta, e o que ficou vazio ===")
    for (tabela, coluna), (fontes, _f) in IMP.DERIVACOES.items():
        vazias = con.execute(
            f'SELECT COUNT(*) FROM "{tabela}" WHERE COALESCE("{coluna}",\'\')=\'\''
        ).fetchone()[0]
        total = con.execute(f'SELECT COUNT(*) FROM "{tabela}"').fetchone()[0]
        print(f"  {tabela}.{coluna:<14} vazias: {vazias:>5} de {total:>6}"
              f"   (de {' + '.join(fontes)})")

    achados = _casos(con)
    vazios = [a for a in achados if a["era_vazio"]]
    divergentes = [a for a in achados if not a["era_vazio"]]

    por_coluna: dict[tuple[str, str], list[dict]] = {}
    for a in vazios:
        por_coluna.setdefault((a["tabela"], a["coluna"]), []).append(a)

    print("\n=== O que a régua da casa escreveria ===")
    if not vazios:
        print("  Nada a preencher: nenhuma coluna derivada está vazia com "
              "fonte preenchida.")
    for (tabela, coluna), lista in sorted(por_coluna.items()):
        print(f"\n  {tabela}.{coluna} — {len(lista)} linha(s):")
        for a in lista[:12]:
            print(f"    · {_descricao(con, a):<48} → {a['certo']!r}")
        if len(lista) > 12:
            print(f"    · … e mais {len(lista) - 12}")

    if divergentes:
        # DIVERGÊNCIA NÃO É CONSERTO, É ASSUNTO DO OFICIAL. A coluna tem valor,
        # e ele não é o que a função da casa devolve: pode ser ajuste a mão,
        # pode ser a função que mudou. Sobrescrever calado apagaria o ajuste.
        print(f"\n=== Divergem, e NÃO serão tocadas ({len(divergentes)}) ===")
        for a in divergentes[:12]:
            print(f"    · {_descricao(con, a):<48} tem {a['atual']!r}, "
                  f"a função diria {a['certo']!r}")
        if len(divergentes) > 12:
            print(f"    · … e mais {len(divergentes) - 12}")
        print("  Isto é assunto do oficial: a coluna tem valor, e ele não é o "
              "que a função da casa devolve.")

    if not vazios:
        con.close()
        return 0

    if not args.confirmar:
        print("\nNada foi gravado — rode de novo com --confirmar.")
        print(f"Com --confirmar, {len(vazios)} coluna(s) de {len(vazios)} "
              f"linha(s) são preenchidas com a função da casa, e uma cópia "
              f"deste banco é guardada antes.")
        con.close()
        return 0

    # A CÓPIA VEM ANTES DE TUDO. É o desfazer deste passo, e o projeto não tem
    # git.
    selo_da_hora = datetime.now().strftime("%Y%m%d-%H%M%S")  # noqa: DTZ005
    copia = caminho.with_suffix(f".antes-das-colunas-norm-{selo_da_hora}.sqlite3")
    # FORA DA PASTA DO BANCO — ordem do oficial em 11/10/2026.
    import pasta_das_copias as _PC
    copia = _PC.destino_da_copia(copia, Path(caminho))
    try:
        con.execute("VACUUM INTO ?", (str(copia),))
    except sqlite3.OperationalError:
        # `VACUUM INTO` é do SQLite 3.27+. Onde não houver, copia o arquivo —
        # e aí o banco precisa estar quieto, o que é o caso de um script que o
        # oficial roda fora do expediente.
        shutil.copy2(caminho, copia)
    print(f"\nCópia do banco guardada em:\n  {copia}")

    # REABRE DEPOIS DO VACUUM INTO — a sequência que, na 1.197, deixou o SQLite
    # com estado residual de «readonly database» no INSERT seguinte.
    con.close()
    con = sqlite3.connect(caminho)
    con.row_factory = sqlite3.Row

    # **A GRAVAÇÃO É A MESMA DO SISTEMA, E NÃO UMA SEGUNDA VERSÃO DELA.** Desde
    # 15/09/2026 a abertura do banco também preenche estas colunas
    # (`importar_padrao.preencher_colunas_derivadas`, chamada em `database.py`),
    # e este script passou a chamar **aquela** função — a que grava e a que
    # mede saem da mesma `_derivar`, e duas cópias divergiriam no primeiro
    # conserto. O que é só deste script continua sendo o que a do sistema não
    # faz: **medir antes**, mostrar o que divergiria, e guardar a cópia.
    with con:
        gravadas = IMP.preencher_colunas_derivadas(con)

    total = sum(gravadas.values())
    print(f"\n{total} coluna(s) preenchida(s):")
    for (tabela, coluna), lista in sorted(por_coluna.items()):
        print(f"  {tabela}.{coluna}: {len(lista)}")

    print("\n=== Como conferir que pegou ===")
    for (tabela, coluna), _l in sorted(por_coluna.items()):
        vazias = con.execute(
            f'SELECT COUNT(*) FROM "{tabela}" WHERE COALESCE("{coluna}",\'\')=\'\''
        ).fetchone()[0]
        print(f"  {tabela}.{coluna}: vazias agora = {vazias}")
    print("\nAbra a ficha 3.110 no sistema e use o filtro de livro: ela passa a "
          "aparecer, que é o relato #55.")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
