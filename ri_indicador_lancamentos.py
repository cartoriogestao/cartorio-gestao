"""Lançamentos próprios dos Indicadores (Livros 4 e 5) — cancelamento.

Pedido do oficial em 18/09/2026: além da averbação no Livro 2 ou 3, o
cancelamento gera lançamento/histórico próprio no Indicador Real (Livro 4)
e no Indicador Pessoal (Livro 5).

Os Indicadores continuam sendo índices de busca sobre matrículas/partes;
esta tabela é o livro de anotações formais de cancelamento neles.
"""
from __future__ import annotations

import sqlite3
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS ri_indicador_lancamentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    livro INTEGER NOT NULL,                 -- 4 = Real, 5 = Pessoal
    especie TEXT NOT NULL DEFAULT 'CANCELAMENTO',
    data_lancamento TEXT NOT NULL,
    teor TEXT NOT NULL,
    motivo TEXT,

    origem_livro INTEGER NOT NULL,          -- 2 = matrícula, 3 = auxiliar
    matricula_id INTEGER,
    matricula_numero TEXT,
    ra_registro_id INTEGER,
    ra_registro_numero INTEGER,

    ato_cancelado_id INTEGER,
    ato_cancelado_tipo TEXT,
    ato_cancelado_numero INTEGER,
    ato_cancelado_rotulo TEXT,
    averbacao_id INTEGER,
    averbacao_rotulo TEXT,

    imovel_resumo TEXT,                     -- Livro 4
    pessoa_nome TEXT,                       -- Livro 5
    pessoa_documento_tipo TEXT,
    pessoa_documento_numero TEXT,
    pessoa_papel TEXT,
    parte_id INTEGER,

    criado_em TEXT NOT NULL,
    criado_por TEXT,
    origem TEXT NOT NULL DEFAULT 'CANCELAMENTO'
);

CREATE INDEX IF NOT EXISTS ix_ri_ind_lanc_livro
    ON ri_indicador_lancamentos(livro, data_lancamento DESC, id DESC);
CREATE INDEX IF NOT EXISTS ix_ri_ind_lanc_mat
    ON ri_indicador_lancamentos(matricula_id);
CREATE INDEX IF NOT EXISTS ix_ri_ind_lanc_ra
    ON ri_indicador_lancamentos(ra_registro_id);
CREATE INDEX IF NOT EXISTS ix_ri_ind_lanc_pessoa
    ON ri_indicador_lancamentos(pessoa_documento_numero, pessoa_nome);
"""


def init_indicador_lancamentos(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA)


def _imovel_resumo(m: Any) -> str:
    partes = []
    logradouro = (m["logradouro"] if m["logradouro"] is not None else "") or ""
    logradouro = logradouro.strip()
    if logradouro:
        partes.append(logradouro)
    bairro = (m["bairro"] if m["bairro"] is not None else "") or ""
    bairro = bairro.strip()
    if bairro:
        partes.append(bairro)
    peri = (m["descricao_perimetro"] if "descricao_perimetro" in m.keys()
            and m["descricao_perimetro"] else "") or ""
    peri = peri.strip()
    if peri and not logradouro:
        partes.append(peri[:120])
    if not partes:
        return f"matrícula {m['numero']}"
    return " — ".join(partes)[:200]


def _partes_para_livro5_matricula(con: sqlite3.Connection, matricula_id: int
                                 ) -> list[sqlite3.Row]:
    """Quem entra no Indicador Pessoal no cancelamento do Livro 2.

    Preferência: proprietários atuais (`proprietario_ativo=1`). Se a ficha
    não tiver nenhum marcado, entram todas as partes cadastradas — sem isso
    o Livro 5 ficaria sem lançamento e o cancelamento sumiria do índice
    pessoal.
    """
    ativos = con.execute(
        """SELECT * FROM ri_partes
           WHERE matricula_id=? AND proprietario_ativo=1
           ORDER BY id""",
        (matricula_id,)).fetchall()
    if ativos:
        return list(ativos)
    return list(con.execute(
        "SELECT * FROM ri_partes WHERE matricula_id=? ORDER BY id",
        (matricula_id,)).fetchall())


def _inserir(con: sqlite3.Connection, **campos) -> int:
    cols = ", ".join(campos.keys())
    ph = ", ".join("?" for _ in campos)
    cur = con.execute(
        f"INSERT INTO ri_indicador_lancamentos ({cols}) VALUES ({ph})",
        tuple(campos.values()))
    return int(cur.lastrowid)


def registrar_cancelamento_livro2(
        con: sqlite3.Connection, *,
        matricula: Any,
        ato_alvo: Any,
        averbacao_id: int,
        averbacao_numero: int,
        motivo: str,
        usuario: str | None,
        agora: str,
        data_lancamento: str | None = None) -> dict:
    """Grava lançamentos 4 e 5 após cancelar ato da matrícula. ESCREVE."""
    data = (data_lancamento or agora)[:10]
    rotulo = (f"{ato_alvo['tipo']}-{int(ato_alvo['numero']):02d}"
              f"/{matricula['numero']}")
    av_rotulo = f"AV-{int(averbacao_numero):02d}"
    imovel = _imovel_resumo(matricula)
    teor4 = (f"CANCELAMENTO no Indicador Real. Fica anotado o cancelamento "
             f"do ato {rotulo} da matrícula {matricula['numero']}, lavrado "
             f"pela averbação {av_rotulo}. Imóvel: {imovel}. "
             f"FUNDAMENTO: {motivo}")
    id4 = _inserir(
        con,
        livro=4, especie="CANCELAMENTO", data_lancamento=data, teor=teor4,
        motivo=motivo, origem_livro=2,
        matricula_id=int(matricula["id"]),
        matricula_numero=str(matricula["numero"]),
        ato_cancelado_id=int(ato_alvo["id"]),
        ato_cancelado_tipo=ato_alvo["tipo"],
        ato_cancelado_numero=int(ato_alvo["numero"]),
        ato_cancelado_rotulo=rotulo,
        averbacao_id=int(averbacao_id),
        averbacao_rotulo=av_rotulo,
        imovel_resumo=imovel,
        criado_em=agora, criado_por=usuario, origem="CANCELAMENTO",
    )

    ids5: list[int] = []
    partes = _partes_para_livro5_matricula(con, int(matricula["id"]))
    if not partes:
        teor5 = (f"CANCELAMENTO no Indicador Pessoal. Ato {rotulo} da "
                 f"matrícula {matricula['numero']} cancelado pela {av_rotulo}. "
                 f"Sem partes nominadas na ficha. FUNDAMENTO: {motivo}")
        ids5.append(_inserir(
            con,
            livro=5, especie="CANCELAMENTO", data_lancamento=data, teor=teor5,
            motivo=motivo, origem_livro=2,
            matricula_id=int(matricula["id"]),
            matricula_numero=str(matricula["numero"]),
            ato_cancelado_id=int(ato_alvo["id"]),
            ato_cancelado_tipo=ato_alvo["tipo"],
            ato_cancelado_numero=int(ato_alvo["numero"]),
            ato_cancelado_rotulo=rotulo,
            averbacao_id=int(averbacao_id),
            averbacao_rotulo=av_rotulo,
            imovel_resumo=imovel,
            pessoa_nome=None,
            criado_em=agora, criado_por=usuario, origem="CANCELAMENTO",
        ))
    else:
        for p in partes:
            nome = p["nome"]
            teor5 = (f"CANCELAMENTO no Indicador Pessoal. Em relação a "
                     f"{nome}, fica anotado o cancelamento do ato {rotulo} "
                     f"da matrícula {matricula['numero']}, pela {av_rotulo}. "
                     f"FUNDAMENTO: {motivo}")
            ids5.append(_inserir(
                con,
                livro=5, especie="CANCELAMENTO", data_lancamento=data,
                teor=teor5, motivo=motivo, origem_livro=2,
                matricula_id=int(matricula["id"]),
                matricula_numero=str(matricula["numero"]),
                ato_cancelado_id=int(ato_alvo["id"]),
                ato_cancelado_tipo=ato_alvo["tipo"],
                ato_cancelado_numero=int(ato_alvo["numero"]),
                ato_cancelado_rotulo=rotulo,
                averbacao_id=int(averbacao_id),
                averbacao_rotulo=av_rotulo,
                imovel_resumo=imovel,
                pessoa_nome=nome,
                pessoa_documento_tipo=p["documento_tipo"],
                pessoa_documento_numero=p["documento_numero"],
                pessoa_papel=p["papel"],
                parte_id=int(p["id"]),
                criado_em=agora, criado_por=usuario, origem="CANCELAMENTO",
            ))
    return {"livro4_id": id4, "livro5_ids": ids5,
            "n_pessoas": len(partes)}


def registrar_cancelamento_livro3(
        con: sqlite3.Connection, *,
        registro: Any,
        averbacao_id: int,
        averbacao_numero: int,
        motivo: str,
        usuario: str | None,
        agora: str,
        data_lancamento: str | None = None) -> dict:
    """Grava lançamentos 4 e 5 após cancelar registro do Livro 3. ESCREVE."""
    data = (data_lancamento or agora)[:10]
    n = int(registro["numero"])
    av_rotulo = f"AV-{int(averbacao_numero):02d}"
    natureza = (registro["natureza"] or "").strip() or "Registro Auxiliar"
    titulo = (registro["titulo_tipo"] or "").strip()
    titulo_n = (registro["titulo_numero"] or "").strip()
    resumo = natureza
    if titulo:
        resumo = f"{natureza} — {titulo}"
    if titulo_n:
        resumo = f"{resumo} ({titulo_n})"
    resumo = resumo[:200]

    teor4 = (f"CANCELAMENTO no Indicador Real. Fica anotado o cancelamento "
             f"do registro {n} do Livro 3 ({resumo}), lavrado pela "
             f"averbação {av_rotulo}. FUNDAMENTO: {motivo}")
    id4 = _inserir(
        con,
        livro=4, especie="CANCELAMENTO", data_lancamento=data, teor=teor4,
        motivo=motivo, origem_livro=3,
        ra_registro_id=int(registro["id"]),
        ra_registro_numero=n,
        ato_cancelado_id=None,
        ato_cancelado_tipo="R",
        ato_cancelado_numero=None,
        ato_cancelado_rotulo=f"R-{n}/Livro3",
        averbacao_id=int(averbacao_id),
        averbacao_rotulo=av_rotulo,
        imovel_resumo=resumo,
        criado_em=agora, criado_por=usuario, origem="CANCELAMENTO",
    )

    partes = list(con.execute(
        "SELECT * FROM ra_partes WHERE registro_id=? ORDER BY id",
        (int(registro["id"]),)).fetchall())
    ids5: list[int] = []
    if not partes:
        teor5 = (f"CANCELAMENTO no Indicador Pessoal. Registro {n} do "
                 f"Livro 3 cancelado pela {av_rotulo}. Sem partes "
                 f"nominadas. FUNDAMENTO: {motivo}")
        ids5.append(_inserir(
            con,
            livro=5, especie="CANCELAMENTO", data_lancamento=data, teor=teor5,
            motivo=motivo, origem_livro=3,
            ra_registro_id=int(registro["id"]),
            ra_registro_numero=n,
            ato_cancelado_rotulo=f"R-{n}/Livro3",
            averbacao_id=int(averbacao_id),
            averbacao_rotulo=av_rotulo,
            imovel_resumo=resumo,
            criado_em=agora, criado_por=usuario, origem="CANCELAMENTO",
        ))
    else:
        for p in partes:
            nome = p["nome"]
            teor5 = (f"CANCELAMENTO no Indicador Pessoal. Em relação a "
                     f"{nome}, fica anotado o cancelamento do registro {n} "
                     f"do Livro 3, pela {av_rotulo}. FUNDAMENTO: {motivo}")
            ids5.append(_inserir(
                con,
                livro=5, especie="CANCELAMENTO", data_lancamento=data,
                teor=teor5, motivo=motivo, origem_livro=3,
                ra_registro_id=int(registro["id"]),
                ra_registro_numero=n,
                ato_cancelado_rotulo=f"R-{n}/Livro3",
                averbacao_id=int(averbacao_id),
                averbacao_rotulo=av_rotulo,
                imovel_resumo=resumo,
                pessoa_nome=nome,
                pessoa_documento_tipo=p["documento_tipo"],
                pessoa_documento_numero=p["documento_numero"],
                pessoa_papel=p["papel"],
                parte_id=int(p["id"]),
                criado_em=agora, criado_por=usuario, origem="CANCELAMENTO",
            ))
    return {"livro4_id": id4, "livro5_ids": ids5, "n_pessoas": len(partes)}


def listar(con: sqlite3.Connection, livro: int, *,
           busca: str = "", limite: int = 50) -> list[sqlite3.Row]:
    """Lista lançamentos de um Indicador (4 ou 5). SÓ LÊ."""
    onde = ["livro=?"]
    params: list[Any] = [int(livro)]
    b = (busca or "").strip()
    if b:
        like = f"%{b}%"
        onde.append(
            "(matricula_numero LIKE ? OR imovel_resumo LIKE ? OR "
            "pessoa_nome LIKE ? OR pessoa_documento_numero LIKE ? OR "
            "ato_cancelado_rotulo LIKE ? OR teor LIKE ? OR "
            "CAST(ra_registro_numero AS TEXT) LIKE ?)")
        params.extend([like] * 7)
    sql = (f"""SELECT * FROM ri_indicador_lancamentos
               WHERE {' AND '.join(onde)}
               ORDER BY data_lancamento DESC, id DESC
               LIMIT ?""")
    params.append(int(limite))
    return list(con.execute(sql, params).fetchall())
