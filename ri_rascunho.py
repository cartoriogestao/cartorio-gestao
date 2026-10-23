"""O ato do RI antes de ser ato: rascunho, e a matricula como ela vai ficar.

OS DOIS DEBITOS DO `CLAUDE.md`, QUE SAO UM SO
    «pre-visualizar matricula com o ato novo» e «rascunho de ato sem consumir
    numero». Sao a mesma necessidade por dois lados: escrever a averbacao,
    **ver como a matricula vai ler com ela dentro**, e so entao lavrar.

POR QUE O RASCUNHO NAO MORA EM `ri_atos` — e a medicao decide
    Medido em 28/08/2026: **`ri_atos` nao tem coluna de situacao**. Nao ha
    `EM_LAVRATURA` como nas Notas (que tem, e usa: 259 lavrados e 1 em
    lavratura). No Registro de Imoveis todo ato e definitivo no instante em que
    entra, e entra ja fazendo duas coisas irreversiveis:

      1. **toma o numero** — `MAX(numero) + 1` daquela matricula;
      2. **entra na corrente de hash** — cada ato guarda o `hash_anterior`, e a
         corrente e o que prova que nenhum ato foi mexido depois.

    Um rascunho dentro de `ri_atos` seria um ato que existe e nao devia: ou
    ocupa numero que nao e dele, ou entra na corrente e a quebra quando for
    apagado. **A corrente so pode conter ato de verdade** — por isso a tabela e
    outra, e `ri_atos` fica exatamente como estava.

E A PRE-VISUALIZACAO NAO GRAVA NADA
    Ela monta em memoria: os atos que existem, mais o rascunho no fim, com o
    numero que ELE TERIA. `numero_que_teria` **calcula e nao consome** — a
    mesma regra do resto da casa, onde toda funcao de contador tem
    `consumir=False`.

    Se dois escreventes rascunharem na mesma matricula, os dois veem o mesmo
    numero previsto, e quem lavrar primeiro fica com ele. Isso e verdade e nao
    defeito: o numero e de quem lavra, e a tela diz isso com todas as letras.

O RISCO DESTA TELA, E O QUE SE FAZ CONTRA ELE
    Pre-visualizacao de matricula **parece certidao**. Alguem pode imprimir e
    entregar, e ai a casa teria posto no mundo um papel afirmando um ato que
    nao existe. Por isso o rascunho sai marcado em toda parte — no titulo, ao
    lado do numero, e no proprio corpo do ato — e ha teste que confere a marca.
"""
from __future__ import annotations

import sqlite3

from bd_nativo import banco

TIPOS = ("R", "AV")


class RascunhoError(ValueError):
    """Erro de regra, com mensagem pronta para o balcao."""


# A marca que separa o rascunho do ato. Ela e literal e feia de proposito:
# quem imprimir esta tela tem de ver na folha que aquilo nao e ato.
MARCA = "RASCUNHO — ATO NÃO LAVRADO"


def numero_que_teria(con: sqlite3.Connection, matricula_id: int) -> int:
    """O numero que o proximo ato desta matricula receberia. So CALCULA.

    E a mesma conta de `ri_web.ri_lavrar_ato` — `MAX(numero) + 1` —, e ela nao
    grava nada: chamar esta funcao nao tira o numero de ninguem. A tela avisa
    que o numero e de quem lavrar primeiro.
    """
    ultimo = banco(con).um(
        "SELECT MAX(numero) AS n FROM ri_atos WHERE matricula_id = %s",
        (int(matricula_id),))
    return int(ultimo["n"] or 0) + 1


def salvar(con: sqlite3.Connection, matricula_id: int, *, tipo: str,
           teor: str, modelo_codigo: str | None, natureza_titulo: str | None,
           protocolo: str | None, prenotacao: str | None,
           data_ato: str | None, quem: str | None, agora: str) -> int:
    """Guarda (ou atualiza) o rascunho daquela matricula. Devolve o id.

    UM RASCUNHO POR MATRICULA, e isso e `UNIQUE(matricula_id)` no banco. Dois
    rascunhos abertos na mesma ficha fariam o escrevente lavrar o errado — e no
    Registro de Imoveis lavrar o errado nao se desfaz: o ato entra na corrente.

    O TEOR VAZIO E RECUSADO. Rascunho sem texto e uma linha na lista que nao
    diz nada, e que so serve para alguem clicar em «lavrar» num ato em branco.
    """
    if str(tipo or "").upper() not in TIPOS:
        raise RascunhoError(
            f"«{tipo}» não é tipo de ato do Registro de Imóveis. "
            f"São dois: R (registro) e AV (averbação).")
    limpo = (teor or "").strip()
    if not limpo:
        raise RascunhoError(
            "Escreva o texto do ato antes de guardar o rascunho — rascunho em "
            "branco só serve para alguém lavrar um ato vazio depois.")

    bd = banco(con)
    linha = bd.escrever(
        """INSERT INTO ri_rascunhos
              (matricula_id, tipo, teor, modelo_codigo, natureza_titulo,
               protocolo, prenotacao, data_ato, criado_por, criado_em,
               atualizado_em)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT(matricula_id) DO UPDATE SET
              tipo = excluded.tipo, teor = excluded.teor,
              modelo_codigo = excluded.modelo_codigo,
              natureza_titulo = excluded.natureza_titulo,
              protocolo = excluded.protocolo,
              prenotacao = excluded.prenotacao,
              data_ato = excluded.data_ato,
              atualizado_em = excluded.atualizado_em
           RETURNING id""",
        (int(matricula_id), str(tipo).upper(), limpo, modelo_codigo,
         natureza_titulo, protocolo, prenotacao, data_ato, quem, agora,
         agora))[0]
    return int(linha["id"])


def da_matricula(con: sqlite3.Connection, matricula_id: int) -> dict | None:
    """O rascunho daquela matricula, se houver. So LE."""
    return banco(con).um("SELECT * FROM ri_rascunhos WHERE matricula_id = %s",
                         (int(matricula_id),))


def apagar(con: sqlite3.Connection, matricula_id: int) -> bool:
    """Joga fora o rascunho. Devolve se havia algum.

    APAGAR RASCUNHO NAO DEIXA RASTRO, e e a unica coisa neste sistema de que
    isso vale: rascunho **nao e ato**. Guardar o texto que alguem desistiu de
    escrever seria guardar o que a casa decidiu nao dizer.
    """
    bd = banco(con)
    bd.escrever("DELETE FROM ri_rascunhos WHERE matricula_id = %s",
                (int(matricula_id),))
    return bd.linhas_afetadas > 0


def como_ficara(con: sqlite3.Connection, matricula_id: int) -> dict:
    """A matricula com o rascunho no fim — montada em MEMORIA, sem gravar nada.

    Devolve `{matricula, atos, rascunho, numero_previsto}`, com o rascunho ja
    trazendo o `rotulo` que ele TERIA (`AV-12`) e a marca de que nao e ato.

    OS ATOS VEM NA ORDEM DA MATRICULA, e o rascunho no fim, porque e ali que
    ele entraria. Mostra-lo no meio faria a tela responder a pergunta errada:
    a pergunta e «como esta ficha vai ler depois deste ato», e nao «onde este
    texto caberia».
    """
    bd = banco(con)
    m = bd.um("SELECT * FROM ri_matriculas WHERE id = %s",
              (int(matricula_id),))
    if not m:
        raise RascunhoError(f"Não achei a matrícula {matricula_id}.")
    atos = bd.ler(
        """SELECT * FROM ri_atos WHERE matricula_id = %s
            ORDER BY numero, id""", (int(matricula_id),))
    rascunho = da_matricula(bd, matricula_id)
    numero = numero_que_teria(bd, matricula_id)
    if rascunho:
        rascunho = dict(rascunho)
        rascunho["numero_previsto"] = numero
        rascunho["rotulo"] = f"{rascunho['tipo']}-{numero:02d}"
        rascunho["marca"] = MARCA
    return {"matricula": dict(m), "atos": atos, "rascunho": rascunho,
            "numero_previsto": numero}


def campos_do_ato(rascunho: dict) -> dict:
    """O rascunho traduzido para os campos que a tela do ato espera.

    O NOME NAO TEM «LAVRAR» DENTRO, e isso nao e capricho: ha varredura que
    recusa nome publico com `lavrar`, `registrar`, `averbar` ou `numerar` neste
    modulo, e ela existe para impedir que alguem escreva aqui, um dia, a funcao
    que lavra de verdade. Eu chamei esta de `campos_para_lavrar` e a varredura
    me pegou — que e exatamente o trabalho dela.

    ELE NAO LAVRA. Quem lavra e `ri_lavrar_ato`, que ja tem a corrente de hash,
    o selo, os emolumentos, o delegatario e a amarracao com a prenotacao — e um
    segundo caminho para dentro de `ri_atos` seria a segunda versao do codigo
    mais delicado do modulo. Esta funcao so entrega o conteudo preenchido.
    """
    return {
        "tipo": rascunho.get("tipo"),
        "teor": rascunho.get("teor"),
        "modelo_codigo": rascunho.get("modelo_codigo"),
        "natureza_titulo": rascunho.get("natureza_titulo"),
        "protocolo": rascunho.get("protocolo"),
        "prenotacao": rascunho.get("prenotacao"),
        "data_ato": rascunho.get("data_ato"),
    }


def abertos(con: sqlite3.Connection, limite: int = 100) -> list[dict]:
    """Os rascunhos que existem, do mais antigo ao mais novo.

    Rascunho esquecido e trabalho que ninguem terminou — e sem esta lista ele
    so apareceria a quem abrisse aquela matricula por acaso.
    """
    return banco(con).ler(
        """SELECT r.*, m.numero AS matricula_numero, m.livro AS matricula_livro
             FROM ri_rascunhos r JOIN ri_matriculas m ON m.id = r.matricula_id
            ORDER BY r.atualizado_em, r.id LIMIT %s""", (int(limite),))
