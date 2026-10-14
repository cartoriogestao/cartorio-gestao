"""Corrigir dado do acervo importado — pedido do oficial em 08/09/2026.

    «quero poder editar tambem os dados dos registros e atos em geral»,
    esclarecido a seguir: «corrigir dado do acervo importado (antes deste
    sistema)» — não editar ato que este sistema lavrou.

O QUE ISTO NÃO É
    Não é averbação, não é retificação, não é correção de ato lavrado por
    este sistema. Esses caminhos já existem, cada um com a forma que a norma
    exige (`retificacao_rcpn.py`, `ri_correcoes.py`, `retificacao.py`, e
    outros) — ficam como estão, e continuam sendo o caminho certo para ato
    que este sistema lavrou.

    Isto é só para o erro de TRANSCRIÇÃO que a carga do acervo trouxe do
    E-Ofício — nome errado, endereço errado, RG errado — em dado que já
    estava assim antes deste sistema existir. `origem='EOFICIO'` é a marca
    de proveniência, não de idade: o E-Ofício foi o sistema desta casa até
    agosto de 2026, e um registro de 2026 pode ter essa marca.

A GUARDA DE VERDADE É A LISTA DE CAMPOS, E NÃO A TELA.
    Cada tabela declara os campos que se pode corrigir — nunca número,
    livro, folha, termo, selo, hash, situação, chave estrangeira nem data do
    ato. A lista vive AQUI, e a rota não confia em nome de campo que o
    formulário mandou: ela pergunta a este módulo se aquele campo, NAQUELA
    tabela, está liberado. Rota que confiasse no formulário deixaria
    qualquer coluna vulnerável a quem soubesse o nome dela.

POR QUE `pt_titulos` (PROTESTO) FICA DE FORA
    Medido em 08/09/2026 na produção: as outras cinco tabelas usam
    `origem='EOFICIO'` para marcar o que veio do acervo, sem ambiguidade.
    `pt_titulos` não — os títulos da carga do acervo foram marcados `CRA` ou
    `CENPROT` (o canal por onde chegaram na CASA ANTERIOR), o MESMO valor que
    marca título recebido normalmente pela Central depois que este sistema
    já estava no ar. Não há como distinguir "isto é do acervo" de "isto
    chegou ontem pela CRA" só pelo `origem` nesta tabela — e inventar outro
    critério (por exemplo uma data de corte) seria decidir uma régua que
    ninguém mediu. Fica de fora até isso ser esclarecido.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any


class CorrecaoError(ValueError):
    """Erro de regra, com mensagem pronta para o balcão."""


@dataclass(frozen=True)
class _Tabela:
    nome: str
    rotulo: str
    origem_col: str | None
    valores_acervo: tuple[str, ...]
    campos_seguros: tuple[str, ...]
    campo_busca: str
    colunas_lista: tuple[str, ...]


TABELAS: dict[str, _Tabela] = {
    "ri_matriculas": _Tabela(
        nome="ri_matriculas", rotulo="Registro de Imóveis — matrícula",
        origem_col="origem", valores_acervo=("EOFICIO",),
        campos_seguros=(
            "logradouro", "numero_predial", "complemento_endereco", "bairro",
            "cidade", "uf", "cep", "area_valor", "area_unidade",
            "descricao_perimetro", "confrontacoes", "car", "nirf", "incra",
            "sigef", "ccir", "cmc", "inscricao_municipal", "iptu",
            "registro_anterior", "observacao"),
        campo_busca="numero",
        colunas_lista=("id", "numero", "complemento", "logradouro", "cidade")),
    "rc_assentos": _Tabela(
        nome="rc_assentos", rotulo="Registro Civil — assento",
        origem_col="origem", valores_acervo=("EOFICIO",),
        campos_seguros=(
            "nome", "data_fato", "causa_morte", "local_sepultamento",
            "testamento", "atestante", "atestante_documento", "hora_fato",
            "cor_raca", "regime_bens"),
        campo_busca="nome",
        colunas_lista=("id", "especie", "numero", "nome", "data_ato")),
    "rc_pessoas": _Tabela(
        nome="rc_pessoas", rotulo="Registro Civil — pessoa do assento",
        origem_col="origem", valores_acervo=("EOFICIO",),
        campos_seguros=(
            "nome", "sexo", "documento_tipo", "documento_numero", "profissao",
            "nacionalidade", "naturalidade_cidade", "naturalidade_uf",
            "data_nascimento", "estado_civil", "endereco", "bairro", "cidade",
            "uf", "cep"),
        campo_busca="nome",
        colunas_lista=("id", "papel", "nome", "assento_id")),
    "rg_registros": _Tabela(
        nome="rg_registros", rotulo="RCPJ/RTD — registro",
        origem_col="origem", valores_acervo=("EOFICIO",),
        campos_seguros=("natureza", "requerente_nome", "requerente_documento"),
        campo_busca="requerente_nome",
        colunas_lista=("id", "serie", "numero", "requerente_nome")),
    "nt_atos": _Tabela(
        nome="nt_atos", rotulo="Notas — ato (dado trazido pela carga)",
        origem_col="origem", valores_acervo=("EOFICIO",),
        campos_seguros=("interessado", "natureza", "local_assinatura",
                        "observacao"),
        campo_busca="interessado",
        colunas_lista=("id", "tipo", "livro", "folha", "interessado")),
    "nt_cartoes": _Tabela(
        nome="nt_cartoes", rotulo="Notas — ficha de firma",
        origem_col="origem", valores_acervo=("EOFICIO",),
        campos_seguros=(
            "nome", "documento", "rg", "rg_orgao", "rg_uf", "rg_emissao",
            "nascimento", "sexo", "nacionalidade", "naturalidade",
            "estado_civil", "conjuge", "profissao", "pai", "mae", "endereco",
            "endereco_numero", "endereco_complemento", "bairro", "cidade",
            "uf", "cep", "telefone", "celular", "email", "local_trabalho",
            "endereco_trabalho", "como_assina", "observacao"),
        campo_busca="nome",
        colunas_lista=("id", "numero", "nome", "documento")),
}


def tabelas_disponiveis() -> list[dict]:
    return [{"nome": t.nome, "rotulo": t.rotulo} for t in TABELAS.values()]


def campos_de(tabela: str) -> tuple[str, ...]:
    t = TABELAS.get(tabela)
    if not t:
        raise CorrecaoError("Tabela não reconhecida.")
    return t.campos_seguros


def buscar(con: sqlite3.Connection, tabela: str, termo: str,
          limite: int = 30) -> list[sqlite3.Row]:
    """Só lê. Nunca abre transação de escrita — é tela de busca."""
    t = TABELAS.get(tabela)
    if not t:
        raise CorrecaoError("Tabela não reconhecida.")
    con.row_factory = sqlite3.Row
    colunas = ", ".join(t.colunas_lista)
    termo = (termo or "").strip()
    if t.origem_col:
        marcadores = ",".join("?" for _ in t.valores_acervo)
        sql = (f"SELECT {colunas} FROM {t.nome} "
              f"WHERE {t.origem_col} IN ({marcadores})"
              + (f" AND {t.campo_busca} LIKE ?" if termo else "")
              + " ORDER BY id DESC LIMIT ?")
        params: tuple[Any, ...] = t.valores_acervo
        if termo:
            params += (f"%{termo}%",)
        params += (limite,)
    else:
        sql = (f"SELECT {colunas} FROM {t.nome}"
              + (f" WHERE {t.campo_busca} LIKE ?" if termo else "")
              + " ORDER BY id DESC LIMIT ?")
        params = ((f"%{termo}%",) if termo else ()) + (limite,)
    return list(con.execute(sql, params))


def obter(con: sqlite3.Connection, tabela: str, row_id: int) -> sqlite3.Row:
    """A linha inteira, com a guarda de proveniência já aplicada."""
    t = TABELAS.get(tabela)
    if not t:
        raise CorrecaoError("Tabela não reconhecida.")
    con.row_factory = sqlite3.Row
    row = con.execute(f"SELECT * FROM {t.nome} WHERE id=?", (row_id,)).fetchone()
    if not row:
        raise CorrecaoError("Linha não encontrada.")
    if t.origem_col and row[t.origem_col] not in t.valores_acervo:
        raise CorrecaoError(
            "Esta linha não é do acervo importado — foi lavrada por este "
            "sistema. Correção de ato lavrado segue outro caminho "
            "(averbação/retificação), não esta tela.")
    return row


def corrigir(con: sqlite3.Connection, tabela: str, row_id: int,
            valores: dict[str, str], motivo: str) -> dict:
    """Corrige um ou mais campos de UMA linha do acervo, num motivo só.

    ESCREVE — chame dentro de `db.transaction()`. Devolve o antes/depois de
    cada campo que de fato mudou, para a rota auditar FORA da transação.
    """
    t = TABELAS.get(tabela)
    if not t:
        raise CorrecaoError("Tabela não reconhecida.")
    motivo = (motivo or "").strip()
    if not motivo:
        raise CorrecaoError("Diga o motivo da correção.")
    for campo in valores:
        if campo not in t.campos_seguros:
            raise CorrecaoError(
                f'O campo "{campo}" não pode ser corrigido por aqui — só '
                f"os campos de dado simples estão liberados, nunca "
                f"numeração, livro, folha, selo, situação ou o texto do "
                f"ato.")
    con.row_factory = sqlite3.Row
    row = con.execute(f"SELECT * FROM {t.nome} WHERE id=?", (row_id,)).fetchone()
    if not row:
        raise CorrecaoError("Linha não encontrada.")
    if t.origem_col and row[t.origem_col] not in t.valores_acervo:
        raise CorrecaoError(
            "Esta linha não é do acervo importado — foi lavrada por este "
            "sistema. Correção de ato lavrado segue outro caminho "
            "(averbação/retificação), não esta tela.")
    mudancas: dict[str, dict[str, Any]] = {}
    for campo, valor_novo in valores.items():
        valor_antigo = row[campo]
        valor_novo_norm = (valor_novo or "").strip() or None
        if str(valor_antigo or "") != str(valor_novo_norm or ""):
            mudancas[campo] = {"antes": valor_antigo, "depois": valor_novo_norm}
    if not mudancas:
        raise CorrecaoError("Nenhum campo mudou.")
    for campo, m in mudancas.items():
        con.execute(f"UPDATE {t.nome} SET {campo}=? WHERE id=?",
                   (m["depois"], row_id))
    return {"tabela": tabela, "id": row_id, "mudancas": mudancas,
            "motivo": motivo}
