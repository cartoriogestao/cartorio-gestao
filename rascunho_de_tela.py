"""Salvar o preenchimento de um formulário e continuar depois.

    «em todos os atos do cartório, durante o preenchimento, é preciso ter um
     campo para salvar o progresso e continuar depois»
        — o oficial, relato #36, 30/08/2026

POR QUE UM MECANISMO SÓ, E NÃO UM RASCUNHO POR TELA
    O pedido é «em todos os atos», e os atos desta casa são muitos: assento,
    escritura, protocolo, prenotação, habilitação, usucapião. Um rascunho
    escrito dentro de cada formulário daria seis implementações que divergem
    no primeiro conserto — e é o defeito que este projeto persegue.

    Aqui há **um** mecanismo: ele guarda o que foi digitado numa tela,
    identificado por qual tela é, e devolve isso quando ela reabrir. Não sabe
    nada sobre assento, escritura ou protocolo — e é justamente por não saber
    que serve aos seis.

POR QUE NÃO É `ri_rascunhos`, QUE JÁ EXISTE
    Aquele resolve outro problema, e resolve bem: ele guarda **um ato do RI**
    antes de virar ato, para se ver como a matrícula vai ler com ele dentro.
    Tem regra própria — o ato do RI toma número e entra na corrente de hash no
    instante em que nasce.

    Este aqui é mais humilde: guarda **o que foi digitado**, sem entender o que
    significa. Um serve ao Registro de Imóveis; o outro, ao balcão inteiro.

O QUE ELE NÃO FAZ, E POR QUÊ
    **Não lavra, não numera, não reserva nada.** Rascunho que consome número é
    ato disfarçado — e ato disfarçado aparece na correição como buraco na
    sequência. Aqui o número só nasce quando o ato nasce.

    **Não é fila de trabalho.** Quem lista o que ficou pela metade e cobra é
    `inacabados`, que mede atos que já existem. Rascunho é papel de anotação:
    pode ser abandonado sem que nada fique devendo.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any

SCHEMA = """
-- O QUE FOI DIGITADO NUMA TELA, antes de virar ato.
--
-- `tela` e o endpoint (`rcpn_assento_novo`, `notas_ato_novo`...), e e por ele
-- que a tela reencontra o proprio rascunho. `chave` distingue rascunhos da
-- mesma tela — o numero do protocolo, o id da matricula —, e fica vazia
-- quando a tela e unica.
CREATE TABLE IF NOT EXISTS rascunhos_de_tela (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tela TEXT NOT NULL,
    chave TEXT NOT NULL DEFAULT '',

    -- O ROTULO QUE O ESCREVENTE VE. Sem ele a lista seria de endpoints, e
    -- ninguem reconhece o proprio trabalho por `rcpn_assento_novo`.
    titulo TEXT NOT NULL,

    -- O QUE FOI DIGITADO. JSON porque cada tela tem os seus campos, e uma
    -- coluna por campo daria uma tabela que muda a cada formulario novo.
    dados_json TEXT NOT NULL DEFAULT '{}',

    criado_em TEXT NOT NULL,
    criado_por TEXT,
    atualizado_em TEXT,
    atualizado_por TEXT
);

CREATE INDEX IF NOT EXISTS ix_rascunhos_tela
    ON rascunhos_de_tela(tela, chave);
CREATE INDEX IF NOT EXISTS ix_rascunhos_quando
    ON rascunhos_de_tela(atualizado_em DESC);
"""

# OS CAMPOS QUE NUNCA ENTRAM NO RASCUNHO.
#
#   `csrf_token` e de uso unico: guardado, volta invalido e o formulario
#   recusa — o escrevente veria o proprio rascunho ser rejeitado sem entender.
#   `senha` e `password` nao se guardam em lugar nenhum, e muito menos num
#   papel de anotacao que fica no banco ate alguem apagar.
NAO_SE_GUARDA = ("csrf_token", "senha", "password", "pin", "certificado")

# QUANTOS DIAS UM RASCUNHO FICA ANTES DE VIRAR ENTULHO.
#
#   **Rascunho tem dado de cliente dentro** — nome, filiacao, endereco. Ele
#   existe para o escrevente voltar hoje ou amanha, e nao para virar um
#   arquivo paralelo de dados pessoais que ninguem sabe que tem. O prazo e
#   generoso e o descarte e explicito: `expirados()` mostra, e alguem apaga.
DIAS_ATE_ENVELHECER = 30


class RascunhoError(ValueError):
    """Erro de regra, em português de balcão."""


def init_rascunho_schema(con: sqlite3.Connection) -> None:
    """Cria a tabela. Idempotente."""
    con.executescript(SCHEMA)


def _texto(v: Any) -> str:
    return "" if v is None else str(v).strip()


def limpar_campos(dados: dict) -> dict:
    """Tira o que não se guarda. Só calcula.

    **NÃO É ZELO GENÉRICO**: o `csrf_token` guardado volta inválido e faz o
    formulário recusar o próprio rascunho, e o escrevente não teria como
    entender por quê.
    """
    fora = {}
    for chave, valor in (dados or {}).items():
        nome = str(chave).lower()
        if any(proibido in nome for proibido in NAO_SE_GUARDA):
            continue
        fora[str(chave)] = valor
    return fora


def salvar(con: sqlite3.Connection, *, tela: str, dados: dict, titulo: str,
           agora: str, chave: str = "", por: str = "",
           rascunho_id: int | None = None) -> dict:
    """Guarda o que foi digitado. ESCREVE.

    **NÃO EXIGE QUE O FORMULÁRIO ESTEJA VÁLIDO**, e essa é a razão de existir:
    o escrevente salva no meio, com metade dos campos e a outra metade errada,
    porque o cliente foi buscar um documento. Cobrar validade aqui seria
    exigir que ele terminasse para poder parar.

    Só recusa duas coisas: tela sem nome e rascunho vazio — este porque um
    registro sem nada dentro só serviria para confundir a lista.
    """
    tela = _texto(tela)
    if not tela:
        raise RascunhoError("O rascunho precisa saber de que tela ele é.")
    limpos = limpar_campos(dados)
    if not any(_texto(v) for v in limpos.values()):
        raise RascunhoError(
            "Não havia nada preenchido para guardar. Escreva alguma coisa "
            "antes de salvar o rascunho.")
    titulo = _texto(titulo) or tela
    corpo = json.dumps(limpos, ensure_ascii=False)
    # O RASCUNHO DO ASSENTO DO RCPN VOLTA COM A CONFERÊNCIA (11/10/2026). Não
    # recusa — rascunho é para guardar pela metade —, mas quem o monta (o
    # balcão, ou o robô que lê as digitalizações) fica sabendo na hora o que
    # a lavratura vai recusar, e não no balcão com o declarante na frente.
    conferencia: list[dict] = []
    if tela.startswith("rcpn_assento"):
        try:
            import rc_conferencia_dados as CONF
            conferencia = CONF.conferir(CONF.dados_do_formulario(
                limpos, data_ato=agora, assina_depois=True))
        except Exception:                               # noqa: BLE001
            conferencia = []

    if rascunho_id:
        existe = con.execute("SELECT id FROM rascunhos_de_tela WHERE id=?",
                             (int(rascunho_id),)).fetchone()
        if not existe:
            raise RascunhoError(f"Não achei o rascunho #{rascunho_id}.")
        con.execute(
            """UPDATE rascunhos_de_tela SET dados_json=?, titulo=?,
                   atualizado_em=?, atualizado_por=? WHERE id=?""",
            (corpo, titulo, agora, por, int(rascunho_id)))
        return {"id": int(rascunho_id), "novo": False, "conferencia": conferencia}

    cur = con.execute(
        """INSERT INTO rascunhos_de_tela
               (tela, chave, titulo, dados_json, criado_em, criado_por,
                atualizado_em, atualizado_por)
           VALUES (?,?,?,?,?,?,?,?)""",
        (tela, _texto(chave), titulo, corpo, agora, por, agora, por))
    return {"id": int(cur.lastrowid), "novo": True, "conferencia": conferencia}


def ler(con: sqlite3.Connection, rascunho_id: int) -> dict:
    """O rascunho e o que ele guarda. Só lê."""
    con.row_factory = sqlite3.Row
    linha = con.execute("SELECT * FROM rascunhos_de_tela WHERE id=?",
                        (int(rascunho_id),)).fetchone()
    if not linha:
        raise RascunhoError(f"Não achei o rascunho #{rascunho_id}.")
    d = dict(linha)
    try:
        d["dados"] = json.loads(d.get("dados_json") or "{}")
    except (ValueError, TypeError):
        # DADO ILEGIVEL NAO DERRUBA A TELA. O rascunho abre vazio, e a tela
        # diz que ele nao pode ser lido — melhor que um erro de sistema em
        # cima de um papel de anotacao.
        d["dados"] = {}
        d["ilegivel"] = True
    return d


def listar(con: sqlite3.Connection, *, tela: str = "",
           limite: int = 200) -> list[dict]:
    """Os rascunhos guardados, do mais recente. Só lê."""
    con.row_factory = sqlite3.Row
    onde, params = ["1=1"], []
    if _texto(tela):
        onde.append("tela = ?")
        params.append(_texto(tela))
    return [dict(r) for r in con.execute(
        f"""SELECT id, tela, chave, titulo, criado_em, criado_por,
                   atualizado_em, atualizado_por
              FROM rascunhos_de_tela WHERE {' AND '.join(onde)}
          ORDER BY COALESCE(atualizado_em, criado_em) DESC LIMIT ?""",
        (*params, int(limite)))]


def quantos(con: sqlite3.Connection, *, tela: str = "") -> int:
    return len(listar(con, tela=tela, limite=100000))


def apagar(con: sqlite3.Connection, rascunho_id: int) -> None:
    """Joga o rascunho fora. ESCREVE.

    **APAGAR RASCUNHO NÃO PEDE MOTIVO**, ao contrário de cancelar ato: ele
    nunca foi ato, não tomou número e não está em corrente nenhuma. Exigir
    justificativa para jogar fora um papel de anotação faria o escrevente
    deixar tudo acumulado.
    """
    con.execute("DELETE FROM rascunhos_de_tela WHERE id=?",
                (int(rascunho_id),))


def expirados(con: sqlite3.Connection, hoje: str,
              dias: int = DIAS_ATE_ENVELHECER) -> list[dict]:
    """Os rascunhos velhos demais. Só lê — **não apaga sozinho**.

    Apagar sozinho seria o sistema jogando fora trabalho de alguém sem
    avisar. A lista mostra; quem apaga é quem olha.
    """
    from datetime import date, timedelta

    def _dia(v: Any):
        try:
            return date.fromisoformat(_texto(v)[:10])
        except ValueError:
            return None

    limite = _dia(hoje)
    if not limite:
        raise RascunhoError("Preciso da data de hoje em aaaa-mm-dd.")
    corte = limite - timedelta(days=int(dias))
    fora = []
    for r in listar(con, limite=100000):
        quando = _dia(r.get("atualizado_em") or r.get("criado_em"))
        if quando and quando < corte:
            r["dias_parado"] = (limite - quando).days
            fora.append(r)
    return fora
