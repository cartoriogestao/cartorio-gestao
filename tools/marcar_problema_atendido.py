"""ANOTA O REALIZADO E FECHA UM PROBLEMA — só mede, por padrão.

Nasceu de uma ORDEM, e não de um defeito: em 18/09/2026 o oficial mandou anotar
o que foi feito no #71 e marcá-lo como atendido. Fechar problema é ato dele, e o
caminho normal disso é a TELA — este script existe porque o pedido veio pelo
lado do desenvolvimento, que não tem a sessão de quem fecha. E **quem escreve
por fora da rota precisa gravar a auditoria à mão**, senão o rastro fica com um
buraco exatamente onde alguém mexeu na mão. É a mesma razão de
`tools/normalizar_situacao_dos_problemas.py`.

O QUE ELE FAZ, e são as duas metades de «anote o realizado e marque como
atendido»:

  1. **põe as notas do desenvolvimento** que a árvore tem e este banco ainda não.
     Elas viajam dentro do `.cgu` e sobem sozinhas na próxima atualização;
     aplicá-las aqui é o mesmo que a subida faria, **com a mesma função**
     (`notas_do_desenvolvimento.aplicar`) — e por isso ela não sobrescreve o que
     uma pessoa escreveu nem fecha problema nenhum. Montar aqui uma versão
     «parecida» faria a lista mostrar uma coisa e a subida gravar outra.
  2. **fecha o problema** com a nota curta, que é a que aparece na lista.

O QUE ELE NÃO FAZ: **não escreve a nota do desenvolvimento à mão** — ela sai da
árvore, que é onde ela mora e de onde ela viaja —, não reabre nada, e não
regrava o carimbo de fechamento de quem já fechou: a data e o nome só entram se
estiverem vazios (`COALESCE` do `fechar`), porque fato do passado não se
regrava.

A AUDITORIA É ASSINADA PELO NOME DA FERRAMENTA, e não pelo nome de quem pediu.
O campo `fechado_por` recebe o nome que o `--por` informar — é a mão a quem o
fechamento se credita —, mas a linha de auditoria diz quem de fato rodou isto.
Assinar com o login de uma pessoa que não clicou em nada seria o carimbo que
mente, e num rastro de auditoria é o pior lugar para ele.

Sem `--confirmar` ele não escreve nada: mede, mostra o antes e o que teria, e
para. Com `--confirmar` tira uma cópia do banco (`VACUUM INTO`) antes de
escrever, e **confere o resultado numa conexão nova** — a leitura na mesma
conexão mostra o que ainda não foi gravado (medido em 17/09/2026, no script do
#82: sem commit, a linha parecia posta e nunca chegava ao banco).
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import ajuda_problemas as AP  # noqa: E402
import notas_do_desenvolvimento as ND  # noqa: E402

for saida in (sys.stdout, sys.stderr):
    try:
        saida.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

BANCO = Path(r"C:\ProgramData\CartorioGestao\cartorio_gestao.sqlite3")
PASTA_DAS_COPIAS = Path(r"C:\ProgramData\CartorioGestao\backups")

ASSINATURA = "tools/marcar_problema_atendido.py"


def _ler(con: sqlite3.Connection, problema_id: int) -> sqlite3.Row | None:
    con.row_factory = sqlite3.Row
    return con.execute(
        """SELECT id, impressao, situacao, titulo, versao, onde,
                  COALESCE(fechado_em,'') fechado_em,
                  COALESCE(fechado_por,'') fechado_por,
                  COALESCE(fechado_nota,'') fechado_nota,
                  COALESCE(nota_dev,'') nota_dev,
                  COALESCE(nota_dev_por,'') nota_dev_por,
                  COALESCE(nota_dev_estado,'') nota_dev_estado,
                  COALESCE(nota_dev_prova,'') nota_dev_prova
             FROM aj_problemas WHERE id = ?""", (int(problema_id),)).fetchone()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--id", type=int, required=True,
                    help="o número do problema (o `#` que aparece na lista)")
    ap.add_argument("--por", required=True,
                    help="a quem o fechamento se credita (vai no `fechado_por`; "
                         "o nome não é adivinhado por ninguém aqui)")
    ap.add_argument("--nota", required=True,
                    help="a nota curta do fechamento, com pelo menos dez letras "
                         "— é ela que aparece na lista dos resolvidos")
    ap.add_argument("--confirmar", action="store_true",
                    help="escreve no banco (sem isto, só mede)")
    args = ap.parse_args()

    if not BANCO.exists():
        print(f"o banco não está em {BANCO}", file=sys.stderr)
        return 1

    con = sqlite3.connect(str(BANCO))
    con.row_factory = sqlite3.Row
    agora = datetime.now().isoformat(timespec="seconds")  # noqa: DTZ005
    print(f"medido em {agora[:16].replace('T', ' às ')}")
    print(f"banco: {BANCO}")

    linha = _ler(con, args.id)
    if linha is None:
        print(f"\nRECUSA: não existe problema #{args.id} neste banco.",
              file=sys.stderr)
        con.close()
        return 1

    print(f"\n=== o problema #{linha['id']} ===")
    print(f"   situacao   {linha['situacao']!r}"
          + ("   (já está resolvido)" if linha["situacao"] == "RESOLVIDO" else ""))
    print(f"   relato     {linha['titulo']}")
    print(f"   onde       {linha['onde']}   versao {linha['versao']}")
    if linha["fechado_em"] or linha["fechado_por"]:
        print(f"   fechado    {linha['fechado_em'] or '—'}"
              f"  por {linha['fechado_por'] or '—'}"
              f"   nota {linha['fechado_nota']!r}")

    # ---- a metade de cima: o realizado, que vem da árvore
    nota = ND.POR_IMPRESSAO.get(linha["impressao"])
    print(f"\n=== a nota do desenvolvimento deste problema ({ND.MARCA}) ===")
    if nota is None:
        print("   NÃO HÁ nota na árvore para este problema — o realizado não está")
        print("   escrito em lugar nenhum, e quem lê a lista depois vai perguntar")
        print("   o que foi feito. Escreva-a em `notas_do_desenvolvimento.py`.")
    else:
        ja = linha["nota_dev"].strip()
        dono = linha["nota_dev_por"]
        if ja and dono != ND.MARCA:
            situacao_da_nota = f"RESPEITADA — escrita por {dono!r}, não se toca"
        elif ja.strip() == nota["nota"].strip():
            situacao_da_nota = "já está no banco, igual"
        else:
            situacao_da_nota = "A POSTAR agora"
        print(f"   estado     {nota['estado']}   ({situacao_da_nota})")
        print(f"   tamanho    {len(nota['nota'])} caracteres"
              + (f"  (no banco: {len(ja)})" if ja else "  (no banco: nada)"))
        print(f"   prova      {nota['prova']}")

    # ---- a metade de baixo: o fechamento
    texto = str(args.nota).strip()
    print("\n=== o que seria gravado no fechamento ===")
    print(f"   situacao   -> 'RESOLVIDO'")
    print(f"   fechado_por-> {args.por!r}"
          + ("   (já preenchido: não se regrava)"
             if linha["fechado_por"] else ""))
    print(f"   fechado_nota -> {texto!r}  ({len(texto)} caracteres)")
    if len(texto) < 10:
        print("\nRECUSA: a nota do fechamento precisa de pelo menos dez letras — "
              "«ok» não explica nada a quem abrir a lista depois.", file=sys.stderr)
        con.close()
        return 1

    if not args.confirmar:
        print("\nSÓ MEDI — nada foi escrito.")
        print("para escrever, rode de novo com --confirmar.")
        con.close()
        return 0

    PASTA_DAS_COPIAS.mkdir(parents=True, exist_ok=True)
    copia = PASTA_DAS_COPIAS / (
        f"cartorio_gestao_antes_do_fechamento_do_{int(args.id)}_"
        f"{datetime.now():%Y%m%d_%H%M%S}.sqlite3")  # noqa: DTZ005
    # FORA DA PASTA DO BANCO — ordem do oficial em 11/10/2026.
    import pasta_das_copias as _PC
    copia = _PC.destino_da_copia(copia, Path(BANCO))
    try:
        con.execute("VACUUM INTO ?", (str(copia),))
    except sqlite3.Error as erro:  # pragma: no cover - caminho de recusa
        print(f"\nNADA FOI ALTERADO: a cópia do banco falhou ({erro})",
              file=sys.stderr)
        con.close()
        return 1
    print(f"\ncópia do banco: {copia}")

    # AS DUAS ESCRITAS NUMA TRANSAÇÃO SÓ: ou o realizado e o fechamento entram
    # juntos, ou não entra nenhum dos dois — meia ordem cumprida é pior que
    # nenhuma, porque a lista mostraria o problema fechado sem dizer o que foi
    # feito.
    with con:
        postas = ND.aplicar(con, agora=agora)
        AP.fechar(con, int(args.id), agora=agora, usuario=args.por, nota=texto)
        con.execute(
            """INSERT INTO audit_logs (ts, user_id, username_snapshot, action,
                   entity_type, entity_id, details)
               VALUES (?,?,?,?,?,?,?)""",
            (agora, None, ASSINATURA, "AJUDA_PROBLEMA_SITUACAO", "aj_problemas",
             int(args.id),
             json.dumps({"acao": "fechar", "nota": texto, "por": args.por,
                         "notas_do_desenvolvimento": {
                             "postas": postas.get("postas"),
                             "mantidas": postas.get("mantidas"),
                             "respeitadas": postas.get("respeitadas"),
                             "sem_problema": postas.get("sem_problema")}},
                        ensure_ascii=False)))

    print("\n=== o que a passada das notas fez ===")
    for chave in ("postas", "mantidas", "respeitadas", "sem_problema"):
        print(f"   {chave:14} {postas.get(chave)}")
    for recusada in postas.get("recusadas", []):
        print(f"   RECUSADA      {recusada}")
    tocados = [r["id"] for r in con.execute(
        "SELECT id FROM aj_problemas WHERE nota_dev_em = ? ORDER BY id", (agora,))]
    print(f"   notas postas agora nos problemas: {tocados or '(nenhuma)'}")
    con.close()

    # A CONFERÊNCIA É NUMA CONEXÃO NOVA. A leitura na mesma conexão mostra o que
    # ainda não foi gravado quando falta o commit — o carimbo que mente dentro
    # da própria ferramenta de medição.
    conf = sqlite3.connect(f"file:{BANCO}?mode=ro", uri=True)
    conf.row_factory = sqlite3.Row
    depois = _ler(conf, args.id)
    auditoria = conf.execute(
        "SELECT ts, username_snapshot, details FROM audit_logs "
        "WHERE action='AJUDA_PROBLEMA_SITUACAO' AND entity_id=? "
        "ORDER BY id DESC LIMIT 1", (int(args.id),)).fetchone()
    conf.close()

    print(f"\n=== como ficou, lido do banco ===")
    print(f"   situacao        {depois['situacao']!r}")
    print(f"   fechado_em      {depois['fechado_em'] or '—'}")
    print(f"   fechado_por     {depois['fechado_por'] or '—'}")
    print(f"   fechado_nota    {depois['fechado_nota']!r}")
    print(f"   nota_dev        {len(depois['nota_dev'])} caracteres"
          f"   estado {depois['nota_dev_estado'] or '—'}"
          f"   por {depois['nota_dev_por'] or '—'}")
    print(f"   auditoria       {auditoria['ts']} por {auditoria['username_snapshot']}")
    if depois["situacao"] != "RESOLVIDO" or not depois["fechado_nota"].strip():
        print("\nO BANCO NÃO MOSTRA O QUE EU ACABEI DE ESCREVER — não confie nesta "
              "rodada.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
