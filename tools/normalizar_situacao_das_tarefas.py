"""A PALAVRA FORA DO VOCABULÁRIO NA LISTA DE TAREFAS — só mede, por padrão.

A SEGUNDA VEZ EM DOIS DIAS, e por isso o script é geral e não um conserto de
uma linha só. Em 17/09/2026 de manhã foi a lista de **problemas** (o `#77`,
gravado `FECHADO` por fora do sistema); à noite, a das **tarefas** — e aqui a
palavra foi escrita pelo próprio sistema.

A tarefa **#85** está `PENDENTE`. Essa palavra não pertence ao vocabulário da
casa (`tarefa_processo.SITUACOES`, que é o que `app.TASK_STATUSES` apelida):
quem a escreveu foi o botão «Reabrir tarefa», que até 17/09/2026 mandava
`PENDENTE` no lugar de `ABERTA` — está no `app.py` do pacote **3.6.141**, linha
**922**: `novo = "CONCLUIDA" if action == "concluir" else "PENDENTE"`. A notícia
da tela era «Tarefa reaberta como pendente.». O estrago é duplo, e os dois ficam
à vista:

  * a situação não existe em `<select>` nenhum da tela, de modo que a linha não
    se alcança por filtro — só pela vista «Em aberto» ou por «Todas»;
  * o **carimbo de conclusão continua dentro dela** (`completed_at` de
    08/09/2026 11:40:53), e o serviço voltou a andar em 14/09. **Carimbo que
    fica depois de a tarefa voltar a andar mente sobre o dia em que o serviço
    terminou** — é a mesma régua do `update_task`, que apaga o carimbo de toda
    situação que não conclui.

O QUE ESTE SCRIPT CONSERTA, E O QUE ELE RECUSA CONSERTAR:

  * só a PALAVRA muda, e só quando ela está no mapa de sinônimos declarados
    abaixo. As notas, a evidência e o resto do histórico ficam: são fato do
    passado, e fato do passado não se regrava.
  * o carimbo de conclusão sai **pela régua do módulo**
    (`tarefa_processo.carimba_o_status`), e não por uma regra escrita aqui:
    situação que não conclui não tem carimbo, e se o destino fosse uma delas o
    script pararia de apagá-lo no dia em que a régua mudasse.
  * palavra que o mapa não conhece **não é adivinhada**. Converter uma delas em
    `ABERTA` mostraria ao balcão um serviço em andamento que talvez esteja
    concluído; convertê-la em `CONCLUIDA` o esconderia. Quem sabe é quem
    escreveu, e o caminho é a tela — a lista mostra a palavra como ela é.
  * o `WHERE` leva o valor antigo junto: este script não toca em linha que já
    esteja certa, mesmo que o banco mude entre a medição e a escrita.
  * a mudança vai para a **linha do tempo da tarefa** e para a **auditoria**.
    A rota faz as duas; quem escreve por fora dela precisa fazer à mão, senão o
    rastro fica com um buraco exatamente onde alguém mexeu na mão.

E A ROTA NÃO SERVE PARA ISTO, o que é bom saber antes de tentar: `reabrir()`
exige que a tarefa **esteja concluída**, e ela não está — está fora do
vocabulário. É por estar fora dele que a rota a recusa, e é este script que a
traz de volta.

Sem `--confirmar` ele não escreve nada: mede, mostra o antes e o depois que
teria, e para. Com `--confirmar` tira uma cópia do banco (`VACUUM INTO`) antes
de escrever.

E a escrita se prova **contra uma cópia**, com `--banco`: o caminho do banco
medido sai impresso no alto, e quando ele não é o da produção o script diz isso
na mesma linha — quem lê «1 tarefa mudou» precisa saber onde. A cópia de
segurança vai para o lado do banco que se escreve, e não para a pasta de backups
da serventia: ensaio não deixa lixo de 163 MB onde o backup da casa mora.

E FICAM DUAS COISAS DECLARADAS, para quem mexer nisto depois:

  * **a palavra `PENDENTE` existe em outras tabelas, e não é esta.** Expediente,
    retificação, usucapião, anotação, LGPD e pedido da Central têm vocabulários
    próprios, e ali `PENDENTE` é palavra de casa. Este script olha só `tasks`.
  * **a porta não está no esquema, e eu quase escrevi que estava.** Procurando a
    palavra no código, a linha **507** de `database.py` apareceu como
    `status TEXT NOT NULL DEFAULT 'PENDENTE'` — e eu ia trocá-la para `ABERTA`,
    declarando que o banco da produção ficaria com a palavra velha. **Ela é de
    `lgpd_items`, e não de `tasks`**: o `DEFAULT` da tarefa sempre foi
    `'ABERTA'` (linha **358**), e `create_task` passa
    `data.get("status") or "ABERTA"` por cima. Nada a corrigir, e o engano fica
    escrito porque **a mesma palavra em tabelas diferentes não é o mesmo
    vocabulário** — foi o que quase me fez «consertar» o que não estava torto.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

# A RÉGUA É A DO MÓDULO, e não uma lista escrita aqui: duas listas de situações
# divergiriam no dia em que a sexta nascesse, e a que ficasse velha seria esta.
import banco_pg
import tarefa_processo as TP
from bd_nativo import banco as abrir_banco

for saida in (sys.stdout, sys.stderr):
    try:
        saida.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

BANCO = Path(r"C:\ProgramData\CartorioGestao\cartorio_gestao.sqlite3")
PASTA_DAS_COPIAS = Path(r"C:\ProgramData\CartorioGestao\backups")

# PALAVRA ESCRITA -> PALAVRA DO VOCABULÁRIO. Só entra aqui o que foi medido, e
# `PENDENTE` foi: quem a escreveu foi o botão «Reabrir tarefa» da própria casa,
# e a intenção dele está no nome do ato — a tarefa volta a ser trabalhada.
SINONIMOS: dict[str, str] = {"PENDENTE": TP.STATUS_DE_REABERTURA}

# A NOTA DA LINHA DO TEMPO. Ela é o que responde, meses depois, por que a
# palavra mudou sem ninguém ter mexido na tela.
NOTA_DA_LINHA = (
    "Situação corrigida de «{de}» para «{para}» por "
    "tools/normalizar_situacao_das_tarefas.py: a palavra não pertence ao "
    "vocabulário do sistema, e a tarefa ficava fora dos filtros por ela."
    "{carimbo}"
)


def _fora_do_vocabulario(bd) -> list[dict]:
    marcadores = ",".join(["%s"] * len(TP.SITUACOES))
    return bd.ler(
        f"""SELECT t.id, t.title, t.status, t.sector, t.assigned_user_id,
                   t.completed_at, t.completed_by, t.updated_at,
                   COALESCE(u.full_name,'') AS quem
              FROM tasks t
              LEFT JOIN users u ON u.id=t.assigned_user_id
             WHERE COALESCE(t.status,'') NOT IN ({marcadores})
             ORDER BY t.id""", tuple(TP.SITUACOES))


def _o_que_a_linha_tem(bd, task_id: int) -> list[dict]:
    """O histórico inteiro dela — é dele que sai por que a palavra está assim."""
    return bd.ler(
        """SELECT h.ts, h.action, h.old_value, h.new_value, h.note
             FROM task_history h WHERE h.task_id=%s ORDER BY h.id""", (task_id,))


def _depois(bd, task_id: int) -> dict | None:
    return bd.um(
        """SELECT id, status, completed_at, completed_by, updated_at
             FROM tasks WHERE id=%s""", (task_id,))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--confirmar", action="store_true",
                    help="escreve no banco (sem isto, só mede)")
    # O `--banco` existe para o ENSAIO: a escrita se prova contra uma cópia
    # (`VACUUM INTO`) antes de valer na produção — é o que `atos_para_minutas_do_ri`
    # já faz. O caminho medido sai impresso no alto, sempre: quem roda contra uma
    # cópia e lê «1 tarefa mudou» precisa ver **onde** isso aconteceu, senão
    # conclui que a produção foi consertada.
    ap.add_argument("--banco", default=str(BANCO), help=f"o banco a medir (padrão: {BANCO})")
    args = ap.parse_args()
    banco = Path(args.banco)

    if not banco.exists():
        print(f"o banco não está em {banco}", file=sys.stderr)
        return 1

    con = banco_pg.conectar(str(banco))
    bd = abrir_banco(con)
    print(f"medido em {datetime.now():%d/%m/%Y às %H:%M:%S}")  # noqa: DTZ005
    print(f"banco: {banco}" + ("" if banco == BANCO else "   (NÃO é o da produção)"))
    print(f"o vocabulário que a tela conhece: {', '.join(TP.SITUACOES)}")

    linhas = _fora_do_vocabulario(bd)
    if not linhas:
        print("\nNenhuma tarefa fora do vocabulário — nada a fazer.")
        con.close()
        return 0

    elegiveis, desconhecidas = [], []
    for linha in linhas:
        (elegiveis if linha["status"] in SINONIMOS else desconhecidas).append(linha)

    print(f"\n=== as tarefas com palavra que a tela não oferece: {len(linhas)} ===")
    for linha in linhas:
        destino = SINONIMOS.get(linha["status"])
        print(f"\n   #{linha['id']}  status={linha['status']!r}"
              + (f"  ->  {destino!r}" if destino else "  ->  ? (sem sinônimo)"))
        print(f"      {str(linha['title'] or '')[:78]}")
        print(f"      setor {linha['sector'] or '—'}"
              f"   responsável {linha['quem'] or '—'}")
        print(f"      carimbo de conclusão {linha['completed_at'] or '—'}"
              f"   por {linha['completed_by'] or '—'}")
        for h in _o_que_a_linha_tem(bd, int(linha["id"])):
            # O que pôs a palavra foi um `ALTEROU_STATUS` cujo `new_value` é
            # ela mesma — foi assim na #85: `CONCLUIDA → PENDENTE`, três
            # segundos depois de a tarefa ser concluída (o botão «Reabrir
            # tarefa», que mandava `PENDENTE` no lugar de `ABERTA`).
            marca = ("  <-- quem pôs a palavra"
                     if (h["new_value"] or "") == linha["status"] and
                     h["action"] in ("ALTEROU_STATUS", "REABERTA", "PASSAGEM")
                     else "")
            print(f"        {h['ts']}  {h['action']}{marca}")
            if h["old_value"] or h["new_value"]:
                print(f"            {h['old_value'] or '—'} → {h['new_value'] or '—'}")
            if h["note"]:
                print(f"            nota: {str(h['note'])[:100]}")

    if desconhecidas:
        print("\nRECUSA: estas palavras eu não conheço, e adivinhar esconderia "
              "serviço —", file=sys.stderr)
        print("  " + ", ".join(f"#{l['id']} {l['status']!r}"
                               for l in desconhecidas), file=sys.stderr)
        print("abra cada tarefa na tela e escolha a situação no formulário;",
              file=sys.stderr)
        print("rode este script de novo — ele não toca nelas.", file=sys.stderr)
        if not elegiveis:
            con.close()
            return 1

    if not args.confirmar:
        print(f"\nSÓ MEDI — {len(elegiveis)} tarefa(s) mudariam de palavra, e o "
              "carimbo de conclusão sairia delas.")
        print("para escrever, rode de novo com --confirmar.")
        con.close()
        return 0

    # A CÓPIA DE SEGURANÇA FICA AO LADO DO BANCO QUE SE ESCREVE. No caminho de
    # ensaio (`--banco` apontando para uma cópia), deixá-la na pasta de backups da
    # produção encheria a pasta da serventia com cópias de cópias — medido: 163 MB
    # por ensaio, e num arquivo que ninguém sabe de onde veio.
    pasta_das_copias = PASTA_DAS_COPIAS if banco == BANCO else banco.parent
    pasta_das_copias.mkdir(parents=True, exist_ok=True)
    copia = pasta_das_copias / (
        f"cartorio_gestao_antes_da_situacao_da_tarefa_"
        f"{datetime.now():%Y%m%d_%H%M%S}.sqlite3")  # noqa: DTZ005
    # FORA DA PASTA DO BANCO — ordem do oficial em 11/10/2026.
    import pasta_das_copias as _PC
    copia = _PC.destino_da_copia(copia, Path(banco))
    banco_pg.copiar_para_arquivo(banco, copia)
    print(f"\ncópia do banco: {copia}")

    agora = datetime.now().isoformat(timespec="seconds")  # noqa: DTZ005
    mudadas: list[tuple[dict, str, bool]] = []
    with con:
        for linha in elegiveis:
            destino = SINONIMOS[linha["status"]]
            # A RÉGUA DO CARIMBO É A DO MÓDULO. Se o destino carimbasse, o
            # carimbo ficaria onde está; como não carimba, ele sai.
            guarda_carimbo = TP.carimba_o_status(destino)
            if guarda_carimbo:
                bd.escrever(
                    "UPDATE tasks SET status=%s, updated_at=%s WHERE id=%s AND status=%s",
                    (destino, agora, int(linha["id"]), linha["status"]),
                )
            else:
                bd.escrever(
                    "UPDATE tasks SET status=%s, completed_at=NULL, "
                    "completed_by=NULL, updated_at=%s WHERE id=%s AND status=%s",
                    (destino, agora, int(linha["id"]), linha["status"]),
                )
            apagou = bool(linha["completed_at"]) and not guarda_carimbo
            nota = NOTA_DA_LINHA.format(
                de=linha["status"], para=destino,
                carimbo=(" O carimbo de conclusão de "
                         f"{linha['completed_at']} saiu: o serviço voltou a andar, "
                         "e carimbo que fica mente sobre o dia em que terminou."
                         if apagou else ""),
            )
            # `user_id` NULL: quem fez isto não foi gente no sistema, e a tela
            # mostra «sistema» — que é a verdade. O nome do script vai na nota e
            # na auditoria, onde se procura por ele.
            bd.escrever(
                "INSERT INTO task_history(task_id,ts,user_id,action,old_value,"
                "new_value,note) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (int(linha["id"]), agora, None, "NORMALIZADA",
                 linha["status"], destino, nota),
            )
            # A MESMA SERIALIZAÇÃO DE `db.log` (`json.dumps`, `ensure_ascii=False`).
            bd.escrever(
                """INSERT INTO audit_logs (ts, user_id, username_snapshot, action,
                       entity_type, entity_id, details)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                (agora, None, "tools/normalizar_situacao_das_tarefas.py",
                 "TAREFA_SITUACAO", "tasks", int(linha["id"]),
                 json.dumps({"acao": "normalizar", "de": linha["status"],
                             "para": destino,
                             "carimbo_apagado": apagou,
                             "nota": "palavra fora do vocabulário da lista, "
                                     "escrita pela própria rota de reabrir "
                                     "antes de 17/09/2026"},
                            ensure_ascii=False)))
            mudadas.append((linha, destino, apagou))

    print("\n=== como ficaram ===")
    for linha, destino, apagou in mudadas:
        d = _depois(bd, int(linha["id"]))
        print(f"   #{d['id']}  {linha['status']!r} -> {d['status']!r}"
              f"   carimbo {d['completed_at'] or '—'}"
              + ("  (apagado)" if apagou else ""))
    print("\nA linha do tempo e a auditoria de cada uma ganharam a linha desta "
          "mudança.")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
