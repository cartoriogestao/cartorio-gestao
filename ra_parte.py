"""AS PARTES DO REGISTRO DO LIVRO 3 — e sem elas o selo não sai.

    «fui tentar selar o ato do 1243 e deu isso: O ato ficou SEM SELO: Os
     nomes das partes devem ser informados. nao tem campo para partes»
                                        — o oficial, 21/09/2026

**E A FRASE É DO APARELHO, e não deste sistema.** É o selador que recusa o
envelope sem `parteAto` — a mesma recusa que derrubou o selo da AV-05 da
matrícula 3.110 em 15/09, no Livro 2. **Eu havia escrito o contrário**, em
comentário, ao construir o selo do Livro 3 em 20/09: «a lista vazia não impede
o selo, e o envelope do Livro 2 já manda `parteAto: []`». Ele manda — e o
aparelho devolve erro. Medição vale mais que dedução, e esta veio do balcão.

**POR QUE NÃO HAVIA CAMPO, medido em 21/09/2026.** A tabela `ra_partes` existe
desde que o Livro 3 nasceu, com nome, documento e papel — e está **vazia nos
14 registros**: nenhuma tela jamais escreveu nela. É o defeito de costume desta
casa pelo avesso — não é função sem tela, é **tabela sem tela**.

**E A CARGA DO ACERVO NÃO RESOLVE O 1.243**, e isso também foi medido: o
`LivroAuxiliar` do E-Ofício tem 14 registros — 1315, 1332, 1409, 1468, 1531,
1549 a 1554, 1560, 1628 e 1636 — e **o 1.243 não está entre eles**. Ele entrou
pela importação dos documentos, em 14/09/2026. Para ele, as partes se digitam:
elas estão escritas no teor e no campo «condições», que a ficha passa a mostrar
ao lado do formulário justamente para não se digitar de cabeça.


OS PAPÉIS SÃO OS DA CASA, e não uma lista inventada

Medidos nas **25 partes** que o E-Ofício guardou no Livro 3
(`LivroAuxiliarPartes` cruzada com `tbQualificacaoPartes`):

| papel | quantas |
|---|---|
| Emitente/Creditado | **14** |
| CREDOR(A) | **9** |
| Proprietário(a) | **2** |

Os outros da lista abaixo **não aparecem nessas 25** e vêm do catálogo do
próprio E-Ofício (`tbQualificacaoPartes`) — avalista, anuente, devedor,
interveniente. Eles entram porque o teor do 1.243 nomeia «AVALISTAS/ANUENTES»
e porque catálogo da casa não é invenção; **os três medidos vêm primeiro**.
"""
from __future__ import annotations

import sqlite3
from typing import Any

# OS TRÊS MEDIDOS, na ordem de uso, e depois o resto do catálogo da casa.
PAPEIS: tuple[tuple[str, str], ...] = (
    ("EMITENTE", "Emitente/Creditado — 14 das 25 partes do acervo"),
    ("CREDOR", "Credor(a) — 9 das 25"),
    ("PROPRIETARIO", "Proprietário(a) — 2 das 25"),
    ("AVALISTA", "Avalista — do catálogo da casa; não aparece nas 25"),
    ("ANUENTE", "Anuente — do catálogo da casa; não aparece nas 25"),
    ("DEVEDOR", "Devedor(a) — do catálogo da casa; não aparece nas 25"),
    ("INTERVENIENTE", "Interveniente — do catálogo da casa; não aparece nas 25"),
)

NOMES_DOS_PAPEIS: dict[str, str] = {c: r.split(" — ")[0] for c, r in PAPEIS}

CPF, CNPJ = "CPF", "CNPJ"


class ParteError(ValueError):
    """Erro de regra, com frase pronta para o balcão — vira `flash(danger)`."""


def _texto(valor: Any) -> str:
    return "" if valor is None else str(valor).strip()


def so_digitos(valor: Any) -> str:
    """O documento sem máscara. **O selo quer só os dígitos.**"""
    return "".join(c for c in _texto(valor) if c.isdigit())


def tipo_do_documento(numero: Any) -> str | None:
    """CPF, CNPJ, ou `None` quando não dá para dizer.

    **Pelo TAMANHO, e não pelo que alguém escolheu numa caixa** — onze dígitos
    é CPF e catorze é CNPJ, e essa é a única leitura que o número sustenta.
    Documento de outro tamanho fica sem tipo, e não vira um palpite.
    """
    d = so_digitos(numero)
    if len(d) == 11:
        return CPF
    if len(d) == 14:
        return CNPJ
    return None


def listar(con: sqlite3.Connection, registro_id: int) -> list[dict]:
    """As partes daquele registro, na ordem em que entraram. Só lê."""
    linhas = con.execute(
        "SELECT * FROM ra_partes WHERE registro_id=? ORDER BY id",
        (int(registro_id),)).fetchall()
    return [dict(x) for x in linhas]


def para_o_selo(con: sqlite3.Connection, registro_id: int) -> list[dict]:
    """As partes na forma que o envelope do selo quer: `{nome, documento}`.

    **Sem documento também vai**, e isso é medido: a casa mandou `{nome}`
    sozinho em 46 dos 236 blocos de parte do Livro 2, e o montador do envelope
    só inclui `documento` quando ele existe. O que o aparelho recusa é a lista
    **vazia**.
    """
    return [{"nome": p["nome"], "documento": p["documento_numero"]}
            for p in listar(con, registro_id) if _texto(p["nome"])]


def acrescentar(con: sqlite3.Connection, *, registro_id: int, nome: str,
                papel: str, documento: Any = None, ato_id=None,
                origem: str = "MANUAL") -> int:
    """Põe uma parte no registro. ESCREVE. Devolve o `id`."""
    nome = _texto(nome)
    if len(nome) < 3:
        raise ParteError(
            "Escreva o nome da parte — é ele que vai dentro do selo, e é por "
            "ele que a pesquisa nacional de bens acha a pessoa.")
    papel = _texto(papel).upper()
    if papel not in NOMES_DOS_PAPEIS:
        raise ParteError(
            f"Papel desconhecido: {papel!r}. Os desta casa estão na caixa — "
            f"emitente, credor, proprietário, avalista, anuente, devedor e "
            f"interveniente.")
    if con.execute("SELECT 1 FROM ra_registros WHERE id=?",
                   (int(registro_id),)).fetchone() is None:
        raise ParteError("Registro do Livro 3 não encontrado.")
    documento = so_digitos(documento)
    cursor = con.execute(
        """INSERT INTO ra_partes(registro_id, ato_id, nome, documento_tipo,
                                 documento_numero, papel, origem)
           VALUES (?,?,?,?,?,?,?)""",
        (int(registro_id), ato_id, nome, tipo_do_documento(documento),
         documento or None, papel, origem))
    return int(cursor.lastrowid)


def remover(con: sqlite3.Connection, parte_id: int) -> int:
    """Tira uma parte do registro. ESCREVE. Devolve o `registro_id`.

    **Parte se tira, e não se corrige por cima**: quem digitou o nome errado
    tira e põe de novo, e assim o que ficou gravado é sempre o que alguém
    escreveu inteiro — e não a metade de duas digitações.
    """
    linha = con.execute("SELECT registro_id FROM ra_partes WHERE id=?",
                        (int(parte_id),)).fetchone()
    if not linha:
        raise ParteError("Parte não encontrada.")
    con.execute("DELETE FROM ra_partes WHERE id=?", (int(parte_id),))
    return int(linha[0])
