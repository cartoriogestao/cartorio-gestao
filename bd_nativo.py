"""Acesso NATIVO ao PostgreSQL — o caminho dos módulos já convertidos.

PILOTO DA MIGRAÇÃO (16/10/2026). O resto do sistema ainda fala «sqlite3» e
passa pela ponte (`banco_pg`). Um módulo convertido escreve SQL do PostgreSQL
direto — `%s`, `RETURNING`, `ILIKE`, `information_schema`, tipos de verdade — e
fala com o banco por aqui.

COMO CONVIVE COM A PONTE: as funções do domínio continuam recebendo o `con`
que a rota já abriu. Se ele é uma conexão da ponte, este módulo usa a MESMA
conexão do PostgreSQL que está dentro dela, na MESMA transação: o que a parte
nativa grava, o `commit()` da rota confirma junto com o resto. Se é uma
conexão do psycopg, usa-a como está. Se é um `sqlite3` de verdade, recusa:
módulo nativo não roda no SQLite, e fingir que roda seria o carimbo que mente.

O QUE SAI QUANDO A PONTE FOR EMBORA: o `SAVEPOINT` por comando e a trava única
por banco existem só porque o código antigo, que ainda divide a transação com
este, conta com eles. Sem a ponte, a transação é a do psycopg e cada módulo
trava só o que precisa (`travar`).
"""
from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterator, Mapping, Sequence

import banco_pg

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover
    psycopg = None
    dict_row = None


class BancoNaoEPostgres(RuntimeError):
    """O módulo é nativo e o banco aberto não é o PostgreSQL."""


#: O que o banco levanta, para quem apanha SÓ erro de banco e deixa o resto
#: subir (LD13). O que passa por aqui e pela ponte chega traduzido para o
#: `sqlite3` — a trava que não veio no prazo (`lock_timeout`, deadlock,
#: comando cancelado) é `sqlite3.OperationalError("database is locked")`. O
#: COMMIT da ponte não se traduz: o que só aparece nele (a chave estrangeira
#: adiada, a conexão que caiu) sobe como `psycopg.Error` cru.
ERROS_DO_BANCO: tuple[type[BaseException], ...] = (
    (sqlite3.Error,) + ((psycopg.Error,) if psycopg is not None else ()))


Parametros = Sequence[Any] | Mapping[str, Any] | None

#: O nome do SAVEPOINT vai dentro do SQL (não há parâmetro para ele): só
#: identificador simples, escrito no código.
_NOME_DE_PONTO = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


class Banco:
    """A conexão nativa, emprestada da rota. Não abre nem fecha nada."""

    def __init__(self, con: Any):
        if isinstance(con, Banco):
            self._pg, self._ponte = con._pg, con._ponte
            return
        if isinstance(con, banco_pg.Conexao):
            self._pg, self._ponte = con._pg, con
            return
        if psycopg is not None and isinstance(con, psycopg.Connection):
            self._pg, self._ponte = con, None
            return
        if isinstance(con, sqlite3.Connection):
            raise BancoNaoEPostgres(
                "Este módulo já é PostgreSQL nativo e a instalação ainda está no "
                "SQLite. Ligue o PostgreSQL (CG_PG_DSN) antes de usá-lo.")
        raise TypeError(f"conexão que não sei usar: {type(con).__name__}")

    # -- transação
    def _escrita(self) -> None:
        """Toda escrita roda em transação. Com a ponte, entra na dela."""
        if self._ponte is not None:
            self._ponte._comecar(True)

    def travar(self, chave: str) -> None:
        """Trava da transação, por assunto (`'cx_protocolos.numero'`).

        Enquanto a ponte existir, a escrita já pega a trava única do banco, e
        esta é redundante; ela fica escrita para o dia em que a ponte sair.
        """
        self._escrita()
        self._rodar("SELECT pg_advisory_xact_lock(hashtext(%s))", (chave,))

    @contextmanager
    def ponto_de_retorno(self, nome: str) -> Iterator["Banco"]:
        """SAVEPOINT de quem chama (LH15): o erro dentro do `with` desfaz só o
        que rodou dentro e sobe igual — e a transação de fora continua viva.

        SEM A PONTE, O ERRO DE SQL CONDENA A TRANSAÇÃO INTEIRA: depois dele o
        PostgreSQL recusa todo comando até o ROLLBACK. Hoje quem apanha o erro
        de banco e segue na mesma transação conta com o SAVEPOINT por comando
        de `_rodar`, que só existe com a ponte; com este, conta sem ela.

        O SAVEPOINT VAI CRU, fora do `cg_nativo` de `_rodar`: o RELEASE daquele
        leva junto todo savepoint aberto depois dele (ver
        `banco_pg.Conexao._ponto_de_retorno`, LX01).

        A ESCRITA ABRE ANTES DO SAVEPOINT. A trava de transação pega DEPOIS
        dele o PostgreSQL solta no ROLLBACK TO: com a ponte, a trava única vem
        antes e fica. Pela mesma razão, o que se trava DENTRO (`travar`, `FOR
        UPDATE`) se solta no erro — a trava que tem de durar a transação
        inteira se pega antes do `with`."""
        if not _NOME_DE_PONTO.match(nome):
            raise ValueError(f"nome de SAVEPOINT que não é identificador: {nome!r}")
        self._escrita()
        self._cru(f"SAVEPOINT {nome}")
        try:
            yield self
        except BaseException:
            self._cru(f"ROLLBACK TO SAVEPOINT {nome}")
            self._cru(f"RELEASE SAVEPOINT {nome}")
            raise
        self._cru(f"RELEASE SAVEPOINT {nome}")

    # -- execução
    def _cru(self, sql: str) -> None:
        """Comando de transação direto no psycopg, sem o SAVEPOINT de `_rodar`."""
        if self._pg is None:
            raise sqlite3.ProgrammingError("Cannot operate on a closed database.")
        try:
            with self._pg.cursor() as c:
                c.execute(sql)
        except psycopg.Error as erro:
            raise banco_pg._traduzir_erro(erro) from erro

    def _rodar(self, sql: str, parametros: Parametros = None) -> list[dict]:
        if self._pg is None:      # a ponte foi fechada: o sqlite3 também recusa
            raise sqlite3.ProgrammingError("Cannot operate on a closed database.")
        protege = self._ponte is not None and self._ponte._em_transacao
        try:
            with self._pg.cursor(row_factory=dict_row) as c:
                if protege:
                    c.execute("SAVEPOINT cg_nativo")
                try:
                    c.execute(sql, parametros)
                except psycopg.Error:
                    if protege:
                        c.execute("ROLLBACK TO SAVEPOINT cg_nativo")
                        c.execute("RELEASE SAVEPOINT cg_nativo")
                    raise
                linhas = c.fetchall() if c.description else []
                # banco novo sendo GRAVADO (ver banco_pg.criar_por_reproducao):
                # o que o nativo executa entra na gravação, senão a reprodução sai sem.
                if self._ponte is not None:
                    self._ponte._anotar(c, sql, parametros)
                self.linhas_afetadas = c.rowcount
                if protege:
                    c.execute("RELEASE SAVEPOINT cg_nativo")
                return linhas
        except psycopg.Error as erro:
            # O código antigo apanha as exceções do sqlite3; a ponte as traduz.
            raise banco_pg._traduzir_erro(erro) from erro

    def ler(self, sql: str, parametros: Parametros = None) -> list[dict]:
        return self._rodar(sql, parametros)

    def um(self, sql: str, parametros: Parametros = None) -> dict | None:
        linhas = self._rodar(sql, parametros)
        return linhas[0] if linhas else None

    def valor(self, sql: str, parametros: Parametros = None) -> Any:
        linha = self.um(sql, parametros)
        return next(iter(linha.values())) if linha else None

    def escrever(self, sql: str, parametros: Parametros = None) -> list[dict]:
        """INSERT/UPDATE/DELETE. Com `RETURNING`, devolve as linhas."""
        self._escrita()
        return self._rodar(sql, parametros)

    # -- o esquema
    def tem_tabela(self, nome: str) -> bool:
        return bool(self.valor("SELECT to_regclass(%s) IS NOT NULL", (nome,)))

    def tem_coluna(self, tabela: str, coluna: str) -> bool:
        return bool(self.valor(
            """SELECT 1 FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = %s AND column_name = %s""",
            (tabela, coluna)))


def banco(con: Any) -> Banco:
    return Banco(con)
