"""Projetos de desenvolvimento — andamento técnico de integrações (ADMIN e MANAGER).

FASES, COMPROVANTES E LINHA DO TEMPO (26/11/2026, S006)
    «Projetos que não estão com resultado pleno funcional devem ser cadastrados
    em Projetos com possibilidade de ver o acompanhamento e cadastramento sobre
    todas as fases, comprovantes de cada etapa e linha do tempo com o que falta
    para o resultado pleno» — o titular.

    O projeto diz o RESULTADO PLENO (o que precisa ser verdade para estar
    pronto) e anda em FASES, cada uma com o critério de pronta, a situação, o
    responsável e o prazo. A fase só se conclui com prova: um comprovante dela
    (arquivo, link, PR, relatório, tarefa ou texto) ou a observação que explica
    como se sabe que ficou pronta. Aguardar pede o quê; dispensar pede o porquê.
    `o_que_falta` mede o progresso e as fases abertas (atrasadas em destaque);
    `linha_do_tempo` junta, em ordem de data, o cadastro, os andamentos, cada
    mudança de fase, os comprovantes e a retirada/devolução (T019).

    `importar` é a porta da carga em lote (o agente 11): idempotente, acha o
    projeto pelo código ou pelo título exato (e preenche o código que faltava),
    e devolve o que criou e o que mudou para quem chama auditar.

    Banco, só acréscimo: colunas novas em `dev_projetos` e três tabelas —
    `dev_projetos_fases`, `dev_projetos_fases_historico` (cada mudança de
    situação, com quem e quando: é dela que a linha do tempo lê) e
    `dev_projetos_comprovantes`. O arquivo do comprovante mora em
    `attachments`, com o tipo `DEV_PROJETO_COMPROVANTE` e o `entity_id` do
    projeto; abre para quem abre a ficha (`TELA_DO_ANEXO`, app.py).
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any

import gestao_retirados as GR
from bd_nativo import banco

STATUS_EM_ANDAMENTO = "EM_ANDAMENTO"
STATUS_PAUSADO = "PAUSADO"
STATUS_CONCLUIDO = "CONCLUIDO"

STATUS_ROTULO = {
    STATUS_EM_ANDAMENTO: "Em andamento",
    STATUS_PAUSADO: "Pausado",
    STATUS_CONCLUIDO: "Concluído",
}

STATUS_VALIDOS = frozenset(STATUS_ROTULO)

# ------------------------------------------------------------- as fases (S006)

FASE_A_FAZER = "A_FAZER"
FASE_EM_ANDAMENTO = "EM_ANDAMENTO"
FASE_AGUARDANDO = "AGUARDANDO"
FASE_CONCLUIDA = "CONCLUIDA"
FASE_DISPENSADA = "DISPENSADA"

#: Na ordem em que a tela as oferece.
SITUACAO_DA_FASE_ROTULO = {
    FASE_A_FAZER: "A fazer",
    FASE_EM_ANDAMENTO: "Em andamento",
    FASE_AGUARDANDO: "Aguardando",
    FASE_CONCLUIDA: "Concluída",
    FASE_DISPENSADA: "Dispensada",
}
SITUACOES_DA_FASE = tuple(SITUACAO_DA_FASE_ROTULO)
#: O que conta como feito no progresso.
FASE_FEITA = frozenset({FASE_CONCLUIDA, FASE_DISPENSADA})

#: Os tipos de comprovante. O código é o que se grava: não muda.
TIPOS_DE_COMPROVANTE = {
    "ARQUIVO": "Arquivo",
    "LINK": "Link",
    "PR": "PR",
    "RELATORIO": "Relatório",
    "TAREFA": "Tarefa",
    "TEXTO": "Texto",
}

#: O tipo do anexo em `attachments` (o `entity_id` é o projeto).
ENTIDADE_DO_ANEXO = "DEV_PROJETO_COMPROVANTE"
EXTENSOES_DO_ARQUIVO = (".pdf", ".png", ".jpg", ".jpeg", ".txt", ".md", ".csv", ".json",
                        ".log", ".odt", ".ods", ".docx", ".xlsx", ".zip")
TAMANHO_MAXIMO_DO_ARQUIVO = 20 * 1024 * 1024
#: O PR citado só pelo número aponta para o repositório público do sistema.
REPOSITORIO_PR = "https://github.com/cartoriogestao/cartorio-gestao/pull/"

#: O que a linha do tempo junta.
EVENTO_ROTULO = {
    "PROJETO_CRIADO": "Cadastro",
    "ANDAMENTO": "Andamento",
    "FASE_INICIADA": "Fase iniciada",
    "FASE_CONCLUIDA": "Fase concluída",
    "FASE_SITUACAO": "Fase",
    "COMPROVANTE": "Comprovante",
    "COMPROVANTES": "Comprovantes",
    "RETIRADO": "Retirado",
    "DEVOLVIDO": "Devolvido",
}

#: Os filtros da lista, além da área.
FILTROS_DE_SITUACAO = (
    (STATUS_EM_ANDAMENTO, "Em andamento"),
    (STATUS_PAUSADO, "Pausado"),
    (STATUS_CONCLUIDO, "Concluído"),
    ("ATRASADO", "Com fase ou prazo atrasado"),
    ("SEM_FASES", "Sem fases cadastradas"),
)

#: Os campos que a tela e a carga gravam no projeto.
CAMPOS_DO_PROJETO = ("titulo", "codigo", "area", "responsavel", "resultado_pleno", "prazo",
                     "origem", "status_geral", "proximo_passo")
#: Os campos da fase que se editam (a situação tem regra própria).
CAMPOS_DA_FASE = ("titulo", "criterio", "ordem", "responsavel", "prazo", "observacao",
                  "aguardando_o_que")

#: A carga em lote: até quantos projetos de uma vez, e o que cabe em cada um.
#: Folgados para a carga real (o maior projeto dela: 8 fases, 12 comprovantes
#: numa fase, uns 40 andamentos); existem para a carga errada não entupir a ficha.
CARGA_MAXIMA_DE_PROJETOS = 200
CARGA_MAXIMA_DE_FASES = 60
CARGA_MAXIMA_DE_COMPROVANTES = 40          # por fase, e os do projeto sem fase
CARGA_MAXIMA_DE_ANDAMENTOS = 300
LIMITE_DO_ANDAMENTO = 4000                 # letras, como os outros blocos de texto
#: Comprovantes registrados juntos (mesmo minuto, mesma pessoa) a partir de
#: quantos viram um evento só na linha do tempo.
COMPROVANTES_JUNTOS = 3


class ProjetoError(ValueError):
    """O que não se grava no projeto, com a frase pronta para a tela."""


_COLUNAS_NOVAS_DO_PROJETO = (
    ("codigo", "TEXT"),
    ("area", "TEXT NOT NULL DEFAULT ''"),
    ("responsavel", "TEXT NOT NULL DEFAULT ''"),
    ("resultado_pleno", "TEXT NOT NULL DEFAULT ''"),
    ("prazo", "TEXT"),
    ("origem", "TEXT NOT NULL DEFAULT ''"),
    ("criado_por", "TEXT NOT NULL DEFAULT ''"),
)


def init_dev_projetos_schema(con: sqlite3.Connection) -> None:
    bd = banco(con)
    bd.escrever(
        """
        CREATE TABLE IF NOT EXISTS dev_projetos (
            id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            titulo TEXT NOT NULL UNIQUE,
            status_geral TEXT NOT NULL DEFAULT 'EM_ANDAMENTO',
            criado_em TEXT NOT NULL,
            atualizado_em TEXT NOT NULL
        )
        """
    )
    bd.escrever(
        """
        CREATE TABLE IF NOT EXISTS dev_projetos_andamento (
            id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            projeto_id bigint NOT NULL,
            texto TEXT NOT NULL,
            criado_em TEXT NOT NULL,
            autor TEXT,
            FOREIGN KEY(projeto_id) REFERENCES dev_projetos(id) ON DELETE CASCADE
        )
        """
    )
    bd.escrever(
        """
        CREATE INDEX IF NOT EXISTS idx_dev_projetos_andamento_projeto
            ON dev_projetos_andamento(projeto_id, criado_em DESC)
        """
    )
    bd.escrever("ALTER TABLE dev_projetos ADD COLUMN IF NOT EXISTS proximo_passo TEXT")
    # S006 (26/11/2026): só acréscimo. O índice do código vem DEPOIS da coluna,
    # porque no banco que já existia ela só nasce aqui (`tests/test_esquemas.py`).
    for coluna, tipo in _COLUNAS_NOVAS_DO_PROJETO:
        bd.escrever(f"ALTER TABLE dev_projetos ADD COLUMN IF NOT EXISTS {coluna} {tipo}")
    bd.escrever(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_dev_projetos_codigo "
        "ON dev_projetos(codigo) WHERE codigo IS NOT NULL"
    )
    bd.escrever(
        """
        CREATE TABLE IF NOT EXISTS dev_projetos_fases (
            id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            projeto_id bigint NOT NULL REFERENCES dev_projetos(id) ON DELETE CASCADE,
            ordem INTEGER NOT NULL,
            titulo TEXT NOT NULL,
            criterio TEXT NOT NULL DEFAULT '',
            situacao TEXT NOT NULL DEFAULT 'A_FAZER'
                CHECK (situacao IN ('A_FAZER','EM_ANDAMENTO','AGUARDANDO','CONCLUIDA','DISPENSADA')),
            aguardando_o_que TEXT NOT NULL DEFAULT '',
            responsavel TEXT NOT NULL DEFAULT '',
            prazo TEXT,
            iniciada_em TEXT,
            concluida_em TEXT,
            concluida_por TEXT,
            observacao TEXT NOT NULL DEFAULT '',
            criado_em TEXT NOT NULL,
            atualizado_em TEXT NOT NULL,
            UNIQUE (projeto_id, titulo)
        )
        """
    )
    bd.escrever(
        "CREATE INDEX IF NOT EXISTS idx_dev_projetos_fases_projeto "
        "ON dev_projetos_fases(projeto_id, ordem)"
    )
    # Cada mudança de situação de uma fase, com quem e quando: a linha do tempo lê daqui.
    bd.escrever(
        """
        CREATE TABLE IF NOT EXISTS dev_projetos_fases_historico (
            id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            projeto_id bigint NOT NULL REFERENCES dev_projetos(id) ON DELETE CASCADE,
            fase_id bigint NOT NULL REFERENCES dev_projetos_fases(id) ON DELETE CASCADE,
            evento TEXT NOT NULL CHECK (evento IN ('INICIADA','CONCLUIDA','SITUACAO')),
            situacao_antes TEXT,
            situacao_depois TEXT NOT NULL,
            nota TEXT NOT NULL DEFAULT '',
            em TEXT NOT NULL,
            por TEXT NOT NULL DEFAULT ''
        )
        """
    )
    bd.escrever(
        "CREATE INDEX IF NOT EXISTS idx_dev_projetos_fases_historico_projeto "
        "ON dev_projetos_fases_historico(projeto_id, em)"
    )
    bd.escrever(
        """
        CREATE TABLE IF NOT EXISTS dev_projetos_comprovantes (
            id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            projeto_id bigint NOT NULL REFERENCES dev_projetos(id) ON DELETE CASCADE,
            fase_id bigint REFERENCES dev_projetos_fases(id),
            tipo TEXT NOT NULL
                CHECK (tipo IN ('ARQUIVO','LINK','PR','RELATORIO','TAREFA','TEXTO')),
            descricao TEXT NOT NULL,
            referencia TEXT NOT NULL DEFAULT '',
            attachment_id bigint,
            registrado_em TEXT NOT NULL,
            registrado_por TEXT NOT NULL
        )
        """
    )
    # A chave da carga idempotente: o mesmo link, PR ou relatório não entra duas
    # vezes na mesma fase. O comprovante do projeto (sem fase) conta como fase 0.
    bd.escrever(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_dev_projetos_comprovantes_referencia "
        "ON dev_projetos_comprovantes(projeto_id, COALESCE(fase_id, 0), tipo, referencia) "
        "WHERE referencia <> ''"
    )
    bd.escrever(
        "CREATE INDEX IF NOT EXISTS idx_dev_projetos_comprovantes_projeto "
        "ON dev_projetos_comprovantes(projeto_id, fase_id)"
    )


def _agora_iso(agora: datetime | str | None) -> str:
    if agora is None:
        return datetime.now().isoformat(timespec="seconds")
    if isinstance(agora, datetime):
        return agora.isoformat(timespec="seconds")
    return str(agora).strip()



def formatar_atualizado_em_local(valor: str | None) -> str:
    """Exibe timestamp ISO do banco como DD/MM/AA - HH:MM (fuso local do PC)."""
    if valor is None:
        return "—"
    bruto = str(valor).strip()
    if not bruto:
        return "—"
    try:
        normalizado = bruto
        if " " in normalizado and "T" not in normalizado:
            normalizado = normalizado.replace(" ", "T", 1)
        dt = datetime.fromisoformat(normalizado)
        if dt.tzinfo is not None:
            dt = dt.astimezone()
        return dt.strftime("%d/%m/%y - %H:%M")
    except ValueError:
        legivel = bruto.replace("T", " ")
        return legivel[:16] if legivel else "—"


_COLUNAS_DO_PROJETO = (
    "id, codigo, titulo, area, responsavel, resultado_pleno, prazo, origem, status_geral, "
    "proximo_passo, criado_em, criado_por, atualizado_em"
)


def listar_projetos(con: sqlite3.Connection, *, hoje: date | None = None) -> list[dict[str, Any]]:
    """Os projetos, com o progresso das fases de cada um (`progresso`)."""
    bd = banco(con)
    rows = bd.ler(
        f"SELECT {_COLUNAS_DO_PROJETO} "
        "FROM dev_projetos ORDER BY titulo COLLATE public.cg_nocase, id"
    )
    progresso = resumo_das_fases(bd, hoje=hoje)
    out: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["atualizado_em_exibicao"] = formatar_atualizado_em_local(
            item.get("atualizado_em")
        )
        item["prazo_exibicao"] = formatar_dia(item.get("prazo"))
        medida = progresso.get(int(item["id"])) or _medir([], hoje=hoje)
        item["progresso"] = medida
        item["prazo_atrasado"] = _projeto_atrasado(item, medida, hoje)
        out.append(item)
    return out


def obter_projeto(con: sqlite3.Connection, projeto_id: int) -> dict | None:
    return banco(con).um(
        f"SELECT {_COLUNAS_DO_PROJETO} FROM dev_projetos WHERE id=%s",
        (int(projeto_id),),
    )


def listar_andamento(con: sqlite3.Connection, projeto_id: int) -> list[dict]:
    return banco(con).ler(
        "SELECT id, projeto_id, texto, criado_em, autor "
        "FROM dev_projetos_andamento WHERE projeto_id=%s "
        "ORDER BY criado_em DESC, id DESC",
        (int(projeto_id),),
    )


def alterar_status(
    con: sqlite3.Connection,
    projeto_id: int,
    status_geral: str,
    agora: datetime | str | None = None,
) -> None:
    status = (status_geral or "").strip().upper()
    if status not in STATUS_VALIDOS:
        raise ValueError(f"status invalido: {status_geral}")
    ts = _agora_iso(agora)
    alterados = banco(con).escrever(
        "UPDATE dev_projetos SET status_geral=%s, atualizado_em=%s WHERE id=%s "
        "RETURNING id",
        (status, ts, int(projeto_id)),
    )
    if not alterados:
        raise LookupError("projeto nao encontrado")

def alterar_proximo_passo(
    con: sqlite3.Connection,
    projeto_id: int,
    proximo_passo: str | None,
    agora: datetime | str | None = None,
) -> None:
    texto = (proximo_passo or "").strip() or None
    ts = _agora_iso(agora)
    alterados = banco(con).escrever(
        "UPDATE dev_projetos SET proximo_passo=%s, atualizado_em=%s WHERE id=%s "
        "RETURNING id",
        (texto, ts, int(projeto_id)),
    )
    if not alterados:
        raise LookupError("projeto nao encontrado")


def registrar_andamento(
    con: sqlite3.Connection,
    projeto_id: int,
    texto: str,
    autor: str | None = None,
    agora: datetime | str | None = None,
) -> int:
    corpo = (texto or "").strip()
    if not corpo:
        raise ValueError("texto vazio")
    ts = _agora_iso(agora)
    bd = banco(con)
    novo = bd.escrever(
        "INSERT INTO dev_projetos_andamento (projeto_id, texto, criado_em, autor) "
        "VALUES (%s, %s, %s, %s) RETURNING id",
        (int(projeto_id), corpo, ts, (autor or "").strip() or None),
    )[0]["id"]
    bd.escrever(
        "UPDATE dev_projetos SET atualizado_em=%s WHERE id=%s",
        (ts, int(projeto_id)),
    )
    return int(novo)


def _ensure_projeto_seed(
    con: sqlite3.Connection,
    spec: dict[str, Any],
    agora: datetime | str | None = None,
) -> int:
    titulo = (spec.get("titulo") or "").strip()
    if not titulo:
        raise ValueError("titulo vazio")
    status = (spec.get("status_geral") or STATUS_EM_ANDAMENTO).strip().upper()
    if status not in STATUS_VALIDOS:
        status = STATUS_EM_ANDAMENTO
    ts = _agora_iso(agora)
    bd = banco(con)
    row = bd.um(
        "SELECT id FROM dev_projetos WHERE titulo=%s", (titulo,)
    )
    if row:
        pid = int(row["id"])
    else:
        pid = int(bd.escrever(
            "INSERT INTO dev_projetos (titulo, status_geral, criado_em, atualizado_em) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (titulo, status, ts, ts),
        )[0]["id"])
    for item in spec.get("andamento") or []:
        texto = (item.get("texto") or "").strip()
        if not texto:
            continue
        criado = (item.get("criado_em") or ts).strip()
        dup = bd.um(
            "SELECT 1 AS um FROM dev_projetos_andamento WHERE projeto_id=%s AND texto=%s",
            (pid, texto),
        )
        if dup:
            continue
        bd.escrever(
            "INSERT INTO dev_projetos_andamento (projeto_id, texto, criado_em, autor) "
            "VALUES (%s, %s, %s, %s)",
            (pid, texto, criado, item.get("autor")),
        )
    proximo = spec.get("proximo_passo")
    if proximo is not None:
        bd.escrever(
            "UPDATE dev_projetos SET proximo_passo=%s, atualizado_em=%s WHERE id=%s",
            ((proximo or "").strip() or None, ts, pid),
        )
    return pid


def _specs_sandbox() -> list[dict[str, Any]]:
    return [
        {
            "titulo": "Homologação CRA21 (API)",
            "status_geral": STATUS_EM_ANDAMENTO,
            "proximo_passo": (
                "Homolog H4 pausado: nome do arquivo de remessa válido — já solicitado aos responsáveis (IEPTB); "
                "aguardando retorno. Depois: trazer remessa + confirmar/retorno."
            ),
            "andamento": [
                {
                    "criado_em": "2026-10-01T17:00:00",
                    "autor": "atualizacao-20261001",
                    "texto": (
                        "Versão 3.6.283: módulo Projetos com pendência explícita; CRA API/simulador no sandbox; "
                        "homolog slices 1–4 e ligação ~17k chars OK."
                    ),
                },
                {
                    "criado_em": "2026-09-20 10:00:00",
                    "texto": "Slices 1–4 da homolog CRA21; teste de ligação homolog com resposta ~17k caracteres.",
                },
                {
                    "criado_em": "2026-09-25 14:00:00",
                    "texto": "Slice H4 (remessa XML) pausado aguardando IEPTB; epic Ajuda #118 mantido em paralelo.",
                },
                {
                    "criado_em": "2026-10-01 12:00:00",
                    "texto": "Sandbox 3.6.281: telas CRA API + simulador; credencial de ensaio no sandbox (não produção).",
                },
            ],
        },
        {
            "titulo": "Integração CENPROT",
            "status_geral": STATUS_EM_ANDAMENTO,
            "proximo_passo": (
                "Credencial homolog IEPTB real + roteiro homolog (tipo CRA); "
                "conferir cancelamento nr_pedido e protocolar/custas."
            ),
            "andamento": [
                {
                    "criado_em": "2026-10-01T17:00:00",
                    "autor": "atualizacao-20261001",
                    "texto": (
                        "Sandbox 3.6.283: 129 pytest CENPROT OK; telas pendências/web e simulador :8911 ativos."
                    ),
                },
                {
                    "criado_em": "2026-09-02 10:00:00",
                    "texto": "Ordem do oficial (02/09): integrar API Resolve CENPROT (OpenAPI 2.1.0). Início: cenprot_api + cenprot_pendencias + fila cn_pendencias (6 espécies).",
                },
                {
                    "criado_em": "2026-09-03 18:00:00",
                    "texto": "Telas cenprot_web (/protesto/cenprot/pendencias), renegociações, emolumentos via API; roteiro Centrais 11/16 passos; suíte pytest CENPROT em expansão.",
                },
                {
                    "criado_em": "2026-10-01 15:30:00",
                    "texto": "Auditoria concluída: sandbox 3.6.281, 129 pytest CENPROT OK, simulador :8911 + sandbox_liga; cred cenprot.cred de ensaio no sandbox (não IEPTB).",
                },
                {
                    "criado_em": "2026-10-01 15:45:00",
                    "texto": "Parado antes da homolog real: credencial IEPTB homolog, slice documentado (paridade CRA #118), conferir nr_pedido cancelamento e protocolar/custas ponta a ponta.",
                },
                {
                    "criado_em": "2026-10-01 15:45:00",
                    "texto": "Doc Context: cenprot-integracao-status-20261001.md. Produção :8765 ainda sem pacote alinhado. Resolve (intimação) = projeto separado.",
                },
            ],
        },
        {
            "titulo": "Resolve (Protesto)",
            "status_geral": STATUS_EM_ANDAMENTO,
            "proximo_passo": (
                "Credencial/homolog Resolve (PAR IEPTB); E2E intimação digital ponta a ponta."
            ),
            "andamento": [
                {
                    "criado_em": "2026-10-01T17:00:00",
                    "autor": "atualizacao-20261001",
                    "texto": (
                        "Rotas Resolve e fila de intimação digital no sandbox; pytest web cobre telas principais."
                    ),
                },
                {
                    "criado_em": "2026-09-10 11:00:00",
                    "texto": "PT-13: rotas /protesto/resolve e credencial centrais_cred; fila de intimação digital ligada ao protesto.",
                },
                {
                    "criado_em": "2026-09-28 16:00:00",
                    "texto": "Saída de protesto parcial documentada; pytest de web cobre telas principais.",
                },
            ],
        },
        {
            "titulo": "ONR — envio de matrículas",
            "status_geral": STATUS_EM_ANDAMENTO,
            "proximo_passo": (
                "Credencial ONR + simulador 8914 ativo; fila ~1443 fichas sem endereço conferido."
            ),
            "andamento": [
                {
                    "criado_em": "2026-10-01T17:00:00",
                    "autor": "atualizacao-20261001",
                    "texto": (
                        "Export Next Cloud + simulador :8914; ~130 pytest ONR validados no sandbox."
                    ),
                },
                {
                    "criado_em": "2026-08-15 09:00:00",
                    "texto": "ri_onr_* + onr_api + export Next Cloud; simulador ONR na porta 8914.",
                },
                {
                    "criado_em": "2026-09-30 10:00:00",
                    "texto": "Suíte pytest ONR ~130 casos; pacotes JSON de exemplo validados no sandbox.",
                },
            ],
        },
        {
            "titulo": "ONR — indicador pessoal",
            "status_geral": STATUS_PAUSADO,
            "proximo_passo": (
                "Pausado: corrigir pytest web pós-export; auditar API antes de homolog."
            ),
            "andamento": [
                {
                    "criado_em": "2026-10-01T17:00:00",
                    "autor": "atualizacao-20261001",
                    "texto": (
                        "UI ri_indicador_pessoal entregue; status pausado registrado no módulo Projetos."
                    ),
                },
                {
                    "criado_em": "2026-09-05 14:00:00",
                    "texto": "UI ri_indicador_pessoal entregue; export pós-ajuste falhou em pytest web — auditar API antes de retomar.",
                },
            ],
        },
        {
            "titulo": "ONR — indicador real",
            "status_geral": STATUS_EM_ANDAMENTO,
            "proximo_passo": (
                "Endereços conferidos na fila; cred + E2E painel→central."
            ),
            "andamento": [
                {
                    "criado_em": "2026-10-01T17:00:00",
                    "autor": "atualizacao-20261001",
                    "texto": (
                        "Painel /ri/indicador-real e pacotes JSON no sandbox; exige endereço conferido."
                    ),
                },
                {
                    "criado_em": "2026-09-12 11:30:00",
                    "texto": "/ri/indicador-real + painel central ONR; pacote 52 JSON; exige endereço conferido (onr_endereco).",
                },
            ],
        },
        {
            "titulo": "ONRTDPJ",
            "status_geral": STATUS_EM_ANDAMENTO,
            "proximo_passo": (
                "Credencial PAR; homolog certidão inteiro teor adiada."
            ),
            "andamento": [
                {
                    "criado_em": "2026-10-01T17:00:00",
                    "autor": "atualizacao-20261001",
                    "texto": "Central ONRTDPJ e fila de certidões no sandbox; E2E local OK.",
                },
                {
                    "criado_em": "2026-09-18 09:00:00",
                    "texto": "Central /rcpj-rtd/onrtdpj revisada na 3.6.208; fila de certidões eletrônicas.",
                },
                {
                    "criado_em": "2026-09-25 17:00:00",
                    "texto": "Certidão inteiro teor adiada para slice posterior; E2E local OK no sandbox.",
                },
            ],
        },
        {
            "titulo": "ONRCPN (CRC)",
            "status_geral": STATUS_PAUSADO,
            "proximo_passo": (
                "Pausado: credencial CRC + lote batch; fluxos locais OK."
            ),
            "andamento": [
                {
                    "criado_em": "2026-10-01T17:00:00",
                    "autor": "atualizacao-20261001",
                    "texto": "onrcpn_api + pedidos web; fluxos locais E2E OK no sandbox.",
                },
                {
                    "criado_em": "2026-09-08 10:00:00",
                    "texto": "onrcpn_api + pedidos web; fluxos locais E2E OK.",
                },
                {
                    "criado_em": "2026-09-22 15:00:00",
                    "texto": "Carga batch CRC adiada; aguarda credencial e roteiro de homologação.",
                },
            ],
        },
    ]



ATUALIZACAO_20261001_AUTOR = "atualizacao-20261001"
ATUALIZACAO_20261001_TS = "2026-10-01T17:00:00"

PENDENCIAS_20261001: dict[str, dict[str, str]] = {
    "Homologação CRA21 (API)": {
        "andamento": (
            "Versão 3.6.283: módulo Projetos com pendência explícita; CRA API/simulador no sandbox; "
            "homolog slices 1–4 e ligação ~17k chars OK."
        ),
        "proximo_passo": (
            "Homolog H4 pausado: nome do arquivo de remessa válido — já solicitado aos responsáveis (IEPTB); "
            "aguardando retorno. Depois: trazer remessa + confirmar/retorno."
        ),
    },
    "Integração CENPROT": {
        "andamento": (
            "Sandbox 3.6.283: 129 pytest CENPROT OK; telas pendências/web e simulador :8911 ativos."
        ),
        "proximo_passo": (
            "Credencial homolog IEPTB real + roteiro homolog (tipo CRA); "
            "conferir cancelamento nr_pedido e protocolar/custas."
        ),
    },
    "Resolve (Protesto)": {
        "andamento": (
            "Rotas Resolve e fila de intimação digital no sandbox; pytest web cobre telas principais."
        ),
        "proximo_passo": (
            "Credencial/homolog Resolve (PAR IEPTB); E2E intimação digital ponta a ponta."
        ),
    },
    "ONR — envio de matrículas": {
        "andamento": (
            "Export Next Cloud + simulador :8914; ~130 pytest ONR validados no sandbox."
        ),
        "proximo_passo": (
            "Credencial ONR + simulador 8914 ativo; fila ~1443 fichas sem endereço conferido."
        ),
    },
    "ONR — indicador pessoal": {
        "andamento": (
            "UI ri_indicador_pessoal entregue; status pausado registrado no módulo Projetos."
        ),
        "proximo_passo": (
            "Pausado: corrigir pytest web pós-export; auditar API antes de homolog."
        ),
    },
    "ONR — indicador real": {
        "andamento": (
            "Painel /ri/indicador-real e pacotes JSON no sandbox; exige endereço conferido."
        ),
        "proximo_passo": (
            "Endereços conferidos na fila; cred + E2E painel→central."
        ),
    },
    "ONRTDPJ": {
        "andamento": (
            "Central ONRTDPJ e fila de certidões no sandbox; E2E local OK."
        ),
        "proximo_passo": (
            "Credencial PAR; homolog certidão inteiro teor adiada."
        ),
    },
    "ONRCPN (CRC)": {
        "andamento": (
            "onrcpn_api + pedidos web; fluxos locais E2E OK no sandbox."
        ),
        "proximo_passo": (
            "Pausado: credencial CRC + lote batch; fluxos locais OK."
        ),
    },
}


def aplicar_atualizacao_pendencias_20261001(
    con: sqlite3.Connection,
    agora: datetime | str | None = None,
) -> int:
    """Idempotente: proximo_passo + andamento (autor atualizacao-20261001) por título."""
    ts = _agora_iso(agora or ATUALIZACAO_20261001_TS)
    aplicados = 0
    bd = banco(con)
    for titulo, payload in PENDENCIAS_20261001.items():
        row = bd.um(
            "SELECT id FROM dev_projetos WHERE titulo=%s", (titulo,)
        )
        if not row:
            continue
        pid = int(row["id"])
        pp = (payload.get("proximo_passo") or "").strip()
        if pp:
            bd.escrever(
                "UPDATE dev_projetos SET proximo_passo=%s, atualizado_em=%s WHERE id=%s",
                (pp, ts, pid),
            )
        texto = (payload.get("andamento") or "").strip()
        if texto:
            dup = bd.um(
                "SELECT 1 AS um FROM dev_projetos_andamento "
                "WHERE projeto_id=%s AND autor=%s AND texto=%s",
                (pid, ATUALIZACAO_20261001_AUTOR, texto),
            )
            if not dup:
                registrar_andamento(
                    bd,
                    pid,
                    texto,
                    autor=ATUALIZACAO_20261001_AUTOR,
                    agora=ts,
                )
        aplicados += 1
    return aplicados


def seed_sandbox_exemplo(
    con: sqlite3.Connection,
    agora: datetime | str | None = None,
) -> None:
    bd = banco(con)
    for spec in _specs_sandbox():
        _ensure_projeto_seed(bd, spec, agora=agora)


def atualizar_andamento_cenprot(con: sqlite3.Connection) -> int | None:
    """Substitui stub antigo do projeto CENPROT pelo seed auditado."""
    specs = [s for s in _specs_sandbox() if s["titulo"] == "Integração CENPROT"]
    if not specs:
        return None
    bd = banco(con)
    row = bd.um(
        "SELECT id FROM dev_projetos WHERE titulo=%s", ("Integração CENPROT",)
    )
    if row:
        pid = int(row["id"])
        bd.escrever("DELETE FROM dev_projetos_andamento WHERE projeto_id=%s", (pid,))
    else:
        pid = None
    pid = _ensure_projeto_seed(bd, specs[0])
    return pid


# =====================================================================
# S006 (26/11/2026) — cadastro, fases, comprovantes, linha do tempo,
# o que falta e a carga em lote. Ver o topo do módulo.
# =====================================================================

# ------------------------------------------------------------------ miúdos

def _linha(valor, nome: str, *, limite: int, obrigatorio: bool = False) -> str:
    """Texto de uma linha: os espaços repetidos viram um."""
    texto = " ".join(str(valor if valor is not None else "").split())
    if obrigatorio and not texto:
        raise ProjetoError(f"{nome}: preencha.")
    if len(texto) > limite:
        raise ProjetoError(f"{nome}: no máximo {limite} caracteres.")
    return texto


def _bloco(valor, nome: str, *, limite: int, obrigatorio: bool = False) -> str:
    """Texto de várias linhas: guarda as quebras, tira só as pontas."""
    texto = str(valor if valor is not None else "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if obrigatorio and not texto:
        raise ProjetoError(f"{nome}: preencha.")
    if len(texto) > limite:
        raise ProjetoError(f"{nome}: no máximo {limite} caracteres.")
    return texto


def _codigo(valor) -> str | None:
    texto = _linha(valor, "Código", limite=40).upper()
    if not texto:
        return None
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9._/-]*", texto):
        raise ProjetoError("Código: use letras, números, ponto, hífen ou barra, sem espaço "
                           "(ex.: RI013, PRJ-01).")
    return texto


def _dia(valor, nome: str) -> str | None:
    """A data (só o dia) em ISO. Aceita AAAA-MM-DD e DD/MM/AAAA; vazio é nada."""
    texto = str(valor if valor is not None else "").strip()
    if not texto:
        return None
    d = None
    try:
        m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", texto)
        if m:
            d = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        elif re.fullmatch(r"\d{4}-\d{2}-\d{2}([T ].*)?", texto):
            d = date.fromisoformat(texto[:10])
    except ValueError:
        d = None
    if d is None:
        raise ProjetoError(f"{nome}: informe a data como dia/mês/ano.")
    return d.isoformat()


def _momento(valor, nome: str) -> str | None:
    """Data, ou data e hora, em ISO. Só o dia fica só o dia."""
    texto = str(valor if valor is not None else "").strip()
    if not texto:
        return None
    if re.fullmatch(r"\d{2}/\d{2}/\d{4}", texto) or len(texto) == 10:
        return _dia(texto, nome)
    try:
        dt = datetime.fromisoformat(texto.replace(" ", "T", 1))
    except ValueError:
        raise ProjetoError(f"{nome}: informe a data (AAAA-MM-DD) ou a data e a hora "
                           "(AAAA-MM-DDTHH:MM).") from None
    if dt.tzinfo is not None:
        # Com fuso, vira a hora local sem fuso: é como o resto do banco grava, e
        # só assim a ordem da linha do tempo e o que a tela mostra batem.
        dt = dt.astimezone().replace(tzinfo=None)
    return dt.isoformat(timespec="seconds")


def _ordem(valor) -> int:
    try:
        n = int(str(valor).strip())
    except (TypeError, ValueError):
        raise ProjetoError("Ordem da fase: um número inteiro, de 1 em diante.") from None
    if not 1 <= n <= 999:
        raise ProjetoError("Ordem da fase: um número inteiro, de 1 em diante.")
    return n


def _status(valor) -> str:
    status = str(valor or "").strip().upper()
    if status not in STATUS_VALIDOS:
        raise ProjetoError("Situação do projeto: em andamento, pausado ou concluído.")
    return status


def _situacao_da_fase(valor) -> str:
    situacao = str(valor or "").strip().upper()
    if situacao not in SITUACAO_DA_FASE_ROTULO:
        raise ProjetoError("Situação da fase: a fazer, em andamento, aguardando, concluída "
                           "ou dispensada.")
    return situacao


def _id_ou_nada(valor) -> int | None:
    if valor is None or str(valor).strip() == "":
        return None
    try:
        return int(str(valor).strip())
    except ValueError:
        raise ProjetoError("Fase desconhecida.") from None


def _e_url(texto: str) -> bool:
    return bool(re.fullmatch(r"https?://\S+", texto or "", flags=re.I))


def _chave_do_momento(texto) -> str:
    """Para ordenar datas gravadas com espaço ou com «T»: a mesma régua."""
    t = str(texto or "")
    if len(t) > 10 and t[10] == " ":
        t = t[:10] + "T" + t[11:]
    return t


def _antes(a, b) -> bool:
    """`a` é anterior a `b`? Só o dia contra dia e hora compara pelo dia."""
    x, y = _chave_do_momento(a), _chave_do_momento(b)
    n = min(len(x), len(y))
    return x[:n] < y[:n]


def _lista(valor, nome: str, *, limite: int) -> list:
    """O que a carga manda em lista: vazio é lista vazia; outro tipo é recusa."""
    if valor is None:
        return []
    if not isinstance(valor, list):
        raise ProjetoError(f"{nome} vêm numa lista.")
    if len(valor) > limite:
        raise ProjetoError(f"{nome}: {len(valor)} na carga, e o máximo é {limite}.")
    return valor


def formatar_dia(valor) -> str:
    """AAAA-MM-DD → DD/MM/AAAA; vazio → «»."""
    t = str(valor or "")
    if len(t) >= 10 and re.fullmatch(r"\d{4}-\d{2}-\d{2}", t[:10]):
        return f"{t[8:10]}/{t[5:7]}/{t[:4]}"
    return t


def formatar_momento(valor) -> str:
    """O momento para a tela: DD/MM/AAAA, e «às HH:MM» quando tem hora."""
    t = _chave_do_momento(valor)
    dia = formatar_dia(t)
    if len(t) >= 16 and t[10] == "T":
        return f"{dia} às {t[11:16]}"
    return dia


def _hoje(hoje: date | None) -> date:
    return hoje or date.today()


def _data_de(texto) -> date | None:
    try:
        return date.fromisoformat(str(texto or "")[:10])
    except ValueError:
        return None


def _existe_projeto(bd, projeto_id: int) -> bool:
    return bool(bd.um("SELECT 1 AS um FROM dev_projetos WHERE id=%s", (int(projeto_id),)))


def _tocar(bd, projeto_id: int, ts: str) -> None:
    bd.escrever("UPDATE dev_projetos SET atualizado_em=%s WHERE id=%s", (ts, int(projeto_id)))


# ------------------------------------------------------------------ o projeto

_PROJETO_TEXTOS = {
    # campo: (rótulo, limite, várias linhas?)
    "area": ("Área", 80, False),
    "responsavel": ("Responsável", 120, False),
    "origem": ("Origem", 120, False),
    "resultado_pleno": ("Resultado pleno", 4000, True),
}


def _campos_do_projeto(dados: dict) -> dict:
    """Só os campos que vieram, já conferidos e no formato do banco."""
    saida: dict[str, Any] = {}
    for campo in CAMPOS_DO_PROJETO:
        if campo not in dados:
            continue
        valor = dados[campo]
        if campo == "titulo":
            saida[campo] = _linha(valor, "Título", limite=200, obrigatorio=True)
        elif campo == "codigo":
            saida[campo] = _codigo(valor)
        elif campo == "prazo":
            saida[campo] = _dia(valor, "Prazo")
        elif campo == "status_geral":
            saida[campo] = _status(valor)
        elif campo == "proximo_passo":
            saida[campo] = _bloco(valor, "Próximo passo", limite=4000) or None
        else:
            rotulo, limite, varias = _PROJETO_TEXTOS[campo]
            saida[campo] = (_bloco if varias else _linha)(valor, rotulo, limite=limite)
    return saida


def _conferir_unicos(bd, campos: dict, projeto_id: int | None) -> None:
    outro_id = int(projeto_id or 0)
    titulo = campos.get("titulo")
    if titulo and bd.um("SELECT id FROM dev_projetos WHERE titulo=%s AND id<>%s",
                        (titulo, outro_id)):
        raise ProjetoError(f"Já existe um projeto chamado «{titulo}». Abra-o na lista em vez "
                           "de cadastrar outro.")
    codigo = campos.get("codigo")
    if codigo:
        outro = bd.um("SELECT titulo FROM dev_projetos WHERE codigo=%s AND id<>%s",
                      (codigo, outro_id))
        if outro:
            raise ProjetoError(f"O código {codigo} já é do projeto «{outro['titulo']}».")


def criar_projeto(con, dados: dict, *, por: str, agora: datetime | str | None = None) -> int:
    """Cadastra o projeto. Título obrigatório e único; código único quando vem."""
    campos = _campos_do_projeto(dados or {})
    if not campos.get("titulo"):
        raise ProjetoError("Dê um título ao projeto.")
    campos.setdefault("status_geral", STATUS_EM_ANDAMENTO)
    bd = banco(con)
    _conferir_unicos(bd, campos, None)
    ts = _agora_iso(agora)
    colunas = list(campos) + ["criado_em", "atualizado_em", "criado_por"]
    valores = [campos[c] for c in campos] + [ts, ts, str(por or "").strip()]
    novo = bd.escrever(
        f"INSERT INTO dev_projetos ({', '.join(colunas)}) "
        f"VALUES ({', '.join(['%s'] * len(colunas))}) RETURNING id",
        valores,
    )
    return int(novo[0]["id"])


def atualizar_projeto(con, projeto_id: int, dados: dict, *, por: str,
                      agora: datetime | str | None = None) -> dict[str, list]:
    """Grava os campos que vieram e mudaram. Devolve {campo: [antes, depois]}.

    `por` é quem altera: a rota o leva à auditoria com o que mudou.
    """
    bd = banco(con)
    atual = obter_projeto(bd, projeto_id)
    if not atual:
        raise LookupError("Projeto não encontrado.")
    campos = _campos_do_projeto(dados or {})
    mudou = {c: [atual.get(c), v] for c, v in campos.items() if atual.get(c) != v}
    if not mudou:
        return {}
    _conferir_unicos(bd, {c: campos[c] for c in mudou}, int(projeto_id))
    ts = _agora_iso(agora)
    sets = ", ".join(f"{c}=%s" for c in mudou)
    bd.escrever(
        f"UPDATE dev_projetos SET {sets}, atualizado_em=%s WHERE id=%s",
        [par[1] for par in mudou.values()] + [ts, int(projeto_id)],
    )
    return mudou


def areas_em_uso(projetos: list[dict]) -> list[str]:
    return sorted({p.get("area") or "" for p in projetos} - {""}, key=str.casefold)


def filtrar_projetos(projetos: list[dict], *, area: str = "", situacao: str = "") -> list[dict]:
    """O filtro da lista: a área exata e a situação (ou «atrasado», «sem fases»)."""
    area = (area or "").strip()
    situacao = (situacao or "").strip().upper()
    saida = []
    for p in projetos:
        if area and (p.get("area") or "") != area:
            continue
        medida = p.get("progresso") or {}
        if situacao == "ATRASADO":
            if not (medida.get("atrasadas") or p.get("prazo_atrasado")):
                continue
        elif situacao == "SEM_FASES":
            if medida.get("total"):
                continue
        elif situacao and p.get("status_geral") != situacao:
            continue
        saida.append(p)
    return saida


# ------------------------------------------------------------------ as fases

_COLUNAS_DA_FASE = (
    "id, projeto_id, ordem, titulo, criterio, situacao, aguardando_o_que, responsavel, prazo, "
    "iniciada_em, concluida_em, concluida_por, observacao, criado_em, atualizado_em"
)


def obter_fase(con, fase_id: int) -> dict | None:
    return banco(con).um(f"SELECT {_COLUNAS_DA_FASE} FROM dev_projetos_fases WHERE id=%s",
                         (int(fase_id),))


def listar_fases(con, projeto_id: int) -> list[dict]:
    return banco(con).ler(
        f"SELECT {_COLUNAS_DA_FASE} FROM dev_projetos_fases WHERE projeto_id=%s "
        "ORDER BY ordem, id",
        (int(projeto_id),),
    )


def _campos_da_fase(dados: dict) -> dict:
    saida: dict[str, Any] = {}
    for campo in CAMPOS_DA_FASE:
        if campo not in dados:
            continue
        valor = dados[campo]
        if campo == "titulo":
            saida[campo] = _linha(valor, "Título da fase", limite=200, obrigatorio=True)
        elif campo == "criterio":
            saida[campo] = _bloco(valor, "Critério de pronta", limite=2000)
        elif campo == "ordem":
            saida[campo] = _ordem(valor)
        elif campo == "responsavel":
            saida[campo] = _linha(valor, "Responsável da fase", limite=120)
        elif campo == "prazo":
            saida[campo] = _dia(valor, "Prazo da fase")
        elif campo == "observacao":
            saida[campo] = _bloco(valor, "Observação", limite=4000)
        elif campo == "aguardando_o_que":
            saida[campo] = _linha(valor, "Aguardando o quê", limite=500)
    return saida


def _tem_comprovante(bd, fase_id: int) -> bool:
    return bool(bd.um("SELECT 1 AS um FROM dev_projetos_comprovantes WHERE fase_id=%s LIMIT 1",
                      (int(fase_id),)))


def _conferir_situacao(nova: str, *, titulo: str, aguardando: str, observacao_nova: str,
                       tem_comprovante: bool) -> None:
    """As regras da situação. A fase só se conclui com prova (S006).

    `observacao_nova` é a observação dada NESTA mudança: a que já estava
    gravada (a da conclusão de antes, o motivo de uma dispensa) não vale.
    """
    if nova == FASE_AGUARDANDO and not (aguardando or "").strip():
        raise ProjetoError(f"A fase «{titulo}» fica aguardando o quê? Diga em «Aguardando o quê».")
    if nova == FASE_CONCLUIDA and not (tem_comprovante or (observacao_nova or "").strip()):
        raise ProjetoError(f"Para concluir a fase «{titulo}», anexe um comprovante dela ou "
                           "escreva, nesta mudança, como se sabe que ficou pronta (a observação "
                           "já gravada não vale).")
    if nova == FASE_DISPENSADA and not (observacao_nova or "").strip():
        raise ProjetoError(f"Para dispensar a fase «{titulo}», diga, nesta mudança, por que ela "
                           "não é mais necessária.")


def _transitar(bd, fase: dict, nova: str, *, por: str, ts: str, quando: str | None = None,
               limpar_aguardando: bool = True, nota: str | None = None) -> str | None:
    """Muda a situação (já conferida), grava as datas e anota no histórico.

    Devolve o evento anotado (INICIADA, CONCLUIDA ou SITUACAO), ou None se
    nada mudou. `fase` sai atualizada. `nota` é o que o histórico guarda;
    sem ela, o «aguardando» ou a observação da fase.
    """
    antes = fase["situacao"]
    if nova == antes:
        return None
    quando = quando or ts
    sets: dict[str, Any] = {"situacao": nova}
    if nova == FASE_EM_ANDAMENTO and not fase.get("iniciada_em"):
        sets["iniciada_em"] = quando
    if nova == FASE_CONCLUIDA:
        sets["concluida_em"] = quando
        sets["concluida_por"] = str(por or "").strip()
    elif fase.get("concluida_em"):
        # reaberta: a conclusão de antes fica no histórico, e não na fase
        sets["concluida_em"] = None
        sets["concluida_por"] = None
    if limpar_aguardando and nova != FASE_AGUARDANDO and fase.get("aguardando_o_que"):
        sets["aguardando_o_que"] = ""
    if nova == FASE_EM_ANDAMENTO and antes == FASE_A_FAZER:
        evento = "INICIADA"
    elif nova == FASE_CONCLUIDA:
        evento = "CONCLUIDA"
    else:
        evento = "SITUACAO"
    if nova == FASE_AGUARDANDO:
        nota = fase.get("aguardando_o_que") or ""
    elif nota is None:
        nota = (fase.get("observacao") or "") if nova in FASE_FEITA else ""
    colunas = ", ".join(f"{c}=%s" for c in sets)
    bd.escrever(
        f"UPDATE dev_projetos_fases SET {colunas}, atualizado_em=%s WHERE id=%s",
        list(sets.values()) + [ts, int(fase["id"])],
    )
    if nova in FASE_FEITA:
        # QUEM CUIDAVA DA FASE termina com ela (`quem_resolve`): a marca fecha
        # como CONCLUIU, e quem chama a leva à auditoria.
        import quem_resolve as QR
        fechado = QR.encerrar(bd, QR.FASE, str(int(fase["id"])), por=por, agora=ts)
        if fechado:
            fase["_quem_resolvia"] = fechado
    bd.escrever(
        "INSERT INTO dev_projetos_fases_historico (projeto_id, fase_id, evento, situacao_antes, "
        "situacao_depois, nota, em, por) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (int(fase["projeto_id"]), int(fase["id"]), evento, antes, nova, nota, quando,
         str(por or "").strip()),
    )
    fase.update(sets)
    return evento


def _anotar_inicio(bd, fase: dict, quando: str, *, por: str, ts: str) -> None:
    """O início informado depois (a carga), sem mudar a situação."""
    bd.escrever("UPDATE dev_projetos_fases SET iniciada_em=%s, atualizado_em=%s WHERE id=%s",
                (quando, ts, int(fase["id"])))
    bd.escrever(
        "INSERT INTO dev_projetos_fases_historico (projeto_id, fase_id, evento, situacao_antes, "
        "situacao_depois, nota, em, por) VALUES (%s, %s, 'INICIADA', %s, %s, '', %s, %s)",
        (int(fase["projeto_id"]), int(fase["id"]), fase["situacao"], fase["situacao"], quando,
         str(por or "").strip()),
    )
    fase["iniciada_em"] = quando


def adicionar_fase(con, projeto_id: int, dados: dict, *, por: str,
                   agora: datetime | str | None = None) -> int:
    """Cadastra a fase no fim da lista (ou na `ordem` dada). Nasce «a fazer», salvo
    `situacao` nos dados, que passa pelas mesmas regras de `alterar_fase`."""
    bd = banco(con)
    if not _existe_projeto(bd, projeto_id):
        raise LookupError("Projeto não encontrado.")
    dados = dados or {}
    campos = _campos_da_fase(dados)
    if not campos.get("titulo"):
        raise ProjetoError("Dê um título à fase.")
    if bd.um("SELECT 1 AS um FROM dev_projetos_fases WHERE projeto_id=%s AND titulo=%s",
             (int(projeto_id), campos["titulo"])):
        raise ProjetoError(f"Este projeto já tem a fase «{campos['titulo']}».")
    nova = _situacao_da_fase(dados["situacao"]) if dados.get("situacao") else FASE_A_FAZER
    _conferir_situacao(nova, titulo=campos["titulo"], aguardando=campos.get("aguardando_o_que", ""),
                       observacao_nova=campos.get("observacao", ""), tem_comprovante=False)
    if "ordem" not in campos:
        campos["ordem"] = int(bd.valor(
            "SELECT COALESCE(MAX(ordem), 0) + 1 FROM dev_projetos_fases WHERE projeto_id=%s",
            (int(projeto_id),)) or 1)
    ts = _agora_iso(agora)
    colunas = ["projeto_id"] + list(campos) + ["situacao", "criado_em", "atualizado_em"]
    valores = [int(projeto_id)] + [campos[c] for c in campos] + [FASE_A_FAZER, ts, ts]
    fid = int(bd.escrever(
        f"INSERT INTO dev_projetos_fases ({', '.join(colunas)}) "
        f"VALUES ({', '.join(['%s'] * len(colunas))}) RETURNING id",
        valores,
    )[0]["id"])
    if nova != FASE_A_FAZER:
        _transitar(bd, obter_fase(bd, fid), nova, por=por, ts=ts)
    _tocar(bd, projeto_id, ts)
    return fid


def _ultimo_evento(bd, fase_id: int) -> str | None:
    datas = [r["em"] for r in bd.ler(
        "SELECT em FROM dev_projetos_fases_historico WHERE fase_id=%s", (int(fase_id),))]
    return max(datas, key=_chave_do_momento) if datas else None


def _alterar_fase(bd, fase_id: int, dados: dict, *, por: str, ts: str,
                  iniciada_em: str | None = None, concluida_em: str | None = None,
                  observacao_da_carga: bool = False) -> dict:
    """`iniciada_em` e `concluida_em` são as datas da carga. Valem só onde dizem a
    verdade: o início, quando a fase sai de «a fazer» pela primeira vez; a
    conclusão, se não for anterior ao último evento da fase. No resto, `ts`."""
    fase = obter_fase(bd, fase_id)
    if not fase:
        raise LookupError("Fase não encontrada.")
    nova = _situacao_da_fase(dados["situacao"]) if dados.get("situacao") else None
    campos = _campos_da_fase(dados)
    if nova and nova != FASE_AGUARDANDO:
        campos.pop("aguardando_o_que", None)  # a mudança o limpa
    efetivo = {**fase, **campos}
    # a observação dada NESTA mudança; na carga, a do arquivo conta como dada
    observacao_nova = ""
    if campos.get("observacao") and (observacao_da_carga or campos["observacao"] != fase["observacao"]):
        observacao_nova = campos["observacao"]
    transita = bool(nova) and nova != fase["situacao"]
    if transita:
        _conferir_situacao(
            nova, titulo=efetivo["titulo"], aguardando=efetivo["aguardando_o_que"],
            observacao_nova=observacao_nova,
            tem_comprovante=_tem_comprovante(bd, fase_id) if nova == FASE_CONCLUIDA else False)
    elif fase["situacao"] == FASE_AGUARDANDO and "aguardando_o_que" in campos:
        _conferir_situacao(FASE_AGUARDANDO, titulo=efetivo["titulo"],
                           aguardando=campos["aguardando_o_que"], observacao_nova="",
                           tem_comprovante=False)
    mudou = {c: [fase.get(c), v] for c, v in campos.items() if fase.get(c) != v}
    if "titulo" in mudou and bd.um(
            "SELECT 1 AS um FROM dev_projetos_fases WHERE projeto_id=%s AND titulo=%s AND id<>%s",
            (int(fase["projeto_id"]), campos["titulo"], int(fase_id))):
        raise ProjetoError(f"Este projeto já tem a fase «{campos['titulo']}».")
    if mudou:
        sets = ", ".join(f"{c}=%s" for c in mudou)
        bd.escrever(f"UPDATE dev_projetos_fases SET {sets}, atualizado_em=%s WHERE id=%s",
                    [par[1] for par in mudou.values()] + [ts, int(fase_id)])
        fase.update({c: par[1] for c, par in mudou.items()})
    eventos: list[str] = []
    if transita:
        antes = fase["situacao"]
        primeiro_inicio = antes == FASE_A_FAZER and not fase.get("iniciada_em")
        if iniciada_em and primeiro_inicio and nova != FASE_EM_ANDAMENTO:
            # o início informado vem antes, e não limpa o «aguardando» que vem depois
            eventos.append(_transitar(bd, fase, FASE_EM_ANDAMENTO, por=por, ts=ts, quando=iniciada_em,
                                      limpar_aguardando=False))
        quando = None
        if nova == FASE_EM_ANDAMENTO and iniciada_em and primeiro_inicio:
            quando = iniciada_em
        elif nova == FASE_CONCLUIDA and concluida_em:
            ultimo = _ultimo_evento(bd, fase_id)
            if ultimo is None or not _antes(concluida_em, ultimo):
                quando = concluida_em
        evento = _transitar(bd, fase, nova, por=por, ts=ts, quando=quando,
                            nota=observacao_nova if nova in FASE_FEITA else None)
        if evento:
            eventos.append(evento)
        mudou["situacao"] = [antes, nova]
    elif iniciada_em and not fase.get("iniciada_em") and fase["situacao"] != FASE_A_FAZER:
        _anotar_inicio(bd, fase, iniciada_em, por=por, ts=ts)
        mudou["iniciada_em"] = [None, iniciada_em]
    if mudou:
        _tocar(bd, fase["projeto_id"], ts)
    return {"mudou": mudou, "eventos": [e for e in eventos if e],
            "concluida": "CONCLUIDA" in eventos,
            "quem_resolvia": fase.get("_quem_resolvia")}


def alterar_fase(con, fase_id: int, dados: dict, *, por: str,
                 agora: datetime | str | None = None) -> dict:
    """Muda os campos e/ou a situação da fase.

    Regras: AGUARDANDO exige «aguardando o quê»; CONCLUIDA exige ao menos um
    comprovante da fase OU a observação dada nesta mudança (a já gravada não
    vale); DISPENSADA exige o porquê, dado nesta mudança. EM_ANDAMENTO grava o
    início (o primeiro fica);
    CONCLUIDA grava quando e por quem; reabrir limpa a conclusão da fase (o
    histórico a guarda). Devolve {mudou: {campo: [antes, depois]}, eventos,
    concluida}.
    """
    return _alterar_fase(banco(con), fase_id, dados or {}, por=por, ts=_agora_iso(agora))


def reordenar_fases(con, projeto_id: int, ids_em_ordem: list[int], *, por: str,
                    agora: datetime | str | None = None) -> list[int]:
    """Põe as fases na ordem dada (1, 2, 3…). A lista traz todas, uma vez cada."""
    bd = banco(con)
    atuais = [int(r["id"]) for r in bd.ler(
        "SELECT id FROM dev_projetos_fases WHERE projeto_id=%s ORDER BY ordem, id",
        (int(projeto_id),))]
    try:
        novos = [int(i) for i in ids_em_ordem]
    except (TypeError, ValueError):
        raise ProjetoError("A nova ordem traz uma fase desconhecida.") from None
    if sorted(novos) != sorted(atuais) or len(set(novos)) != len(novos):
        raise ProjetoError("A nova ordem precisa trazer todas as fases do projeto, uma vez cada.")
    ts = _agora_iso(agora)
    for n, fid in enumerate(novos, 1):
        bd.escrever("UPDATE dev_projetos_fases SET ordem=%s, atualizado_em=%s "
                    "WHERE id=%s AND ordem<>%s", (n, ts, fid, n))
    _tocar(bd, projeto_id, ts)
    return novos


def mover_fase(con, projeto_id: int, fase_id: int, direcao: str, *, por: str,
               agora: datetime | str | None = None) -> list[int] | None:
    """Sobe ou desce a fase uma posição. None quando já está na ponta."""
    bd = banco(con)
    ids = [int(r["id"]) for r in bd.ler(
        "SELECT id FROM dev_projetos_fases WHERE projeto_id=%s ORDER BY ordem, id",
        (int(projeto_id),))]
    if int(fase_id) not in ids:
        raise ProjetoError("Essa fase não é deste projeto.")
    i = ids.index(int(fase_id))
    j = i - 1 if (direcao or "").strip().lower() == "subir" else i + 1
    if j < 0 or j >= len(ids):
        return None
    ids[i], ids[j] = ids[j], ids[i]
    return reordenar_fases(bd, projeto_id, ids, por=por, agora=agora)


# ------------------------------------------------------------- os comprovantes

#: O endereço de um PR do próprio repositório: vira o número, para não duplicar.
_PR_DO_REPOSITORIO = re.compile(
    r"https?://(?:www\.)?" + re.escape(REPOSITORIO_PR.split("://", 1)[1]) + r"(\d{1,6})(?:[/?#]\S*)?",
    flags=re.I)


def _referencia(tipo: str, valor, *, tem_anexo: bool) -> str:
    """A referência de cada tipo, conferida e no formato da chave única."""
    ref = _linha(valor, "Referência", limite=500)
    if tipo == "LINK":
        if not _e_url(ref):
            raise ProjetoError("Link: cole o endereço completo, começando por https://.")
    elif tipo == "PR":
        m = re.fullmatch(r"#?\s*(\d{1,6})", ref) or _PR_DO_REPOSITORIO.fullmatch(ref)
        if m:
            ref = m.group(1)
        elif not _e_url(ref):
            raise ProjetoError("PR: informe o número (ex.: 528) ou o endereço do PR.")
    elif tipo == "TAREFA":
        m = re.fullmatch(r"#?\s*(\d{1,9})", ref)
        if m:
            ref = m.group(1)
        if not ref:
            raise ProjetoError("Tarefa: informe o número ou o código da tarefa.")
    elif tipo == "RELATORIO":
        if not ref and not tem_anexo:
            raise ProjetoError("Relatório: informe onde ele está (caminho ou endereço) ou anexe "
                               "o arquivo.")
    return ref


def _comprovante_igual(bd, projeto_id: int, fase_id: int | None, tipo: str, referencia: str,
                       descricao: str = "") -> dict | None:
    """O comprovante que já existe com a mesma chave (a da carga idempotente)."""
    if referencia:
        return bd.um(
            "SELECT id FROM dev_projetos_comprovantes WHERE projeto_id=%s "
            "AND COALESCE(fase_id, 0)=%s AND tipo=%s AND referencia=%s",
            (int(projeto_id), int(fase_id or 0), tipo, referencia))
    return bd.um(
        "SELECT id FROM dev_projetos_comprovantes WHERE projeto_id=%s "
        "AND COALESCE(fase_id, 0)=%s AND tipo=%s AND referencia='' AND descricao=%s",
        (int(projeto_id), int(fase_id or 0), tipo, descricao))


def _conferir_comprovante(bd, pid: int, *, fase_id, tipo, descricao, referencia,
                          sha_do_anexo: str | None) -> dict:
    """Tudo o que se confere antes de gravar o comprovante. Só lê.

    `sha_do_anexo` é o do arquivo que vai junto (None: sem arquivo). Devolve
    os campos prontos: fase_id, tipo, descricao, referencia.
    """
    if not _existe_projeto(bd, pid):
        raise LookupError("Projeto não encontrado.")
    tipo_n = str(tipo or "").strip().upper()
    if tipo_n not in TIPOS_DE_COMPROVANTE:
        raise ProjetoError("Escolha o tipo do comprovante: arquivo, link, PR, relatório, tarefa "
                           "ou texto.")
    fid = _id_ou_nada(fase_id)
    if fid is not None:
        fase = bd.um("SELECT projeto_id FROM dev_projetos_fases WHERE id=%s", (fid,))
        if not fase or int(fase["projeto_id"]) != pid:
            raise ProjetoError("Essa fase não é deste projeto.")
    desc = _bloco(descricao, "Descrição", limite=1000)
    if not desc:
        raise ProjetoError("Descreva o comprovante: o que ele prova.")
    if tipo_n == "ARQUIVO" and sha_do_anexo is None:
        raise ProjetoError("Escolha o arquivo do comprovante.")
    ref = _referencia(tipo_n, referencia, tem_anexo=sha_do_anexo is not None)
    if tipo_n == "ARQUIVO" and not ref:
        ref = "sha256:" + str(sha_do_anexo)
    if ref and _comprovante_igual(bd, pid, fid, tipo_n, ref):
        raise ProjetoError("Este comprovante já está registrado " +
                           ("nesta fase." if fid else "no projeto."))
    return {"fase_id": fid, "tipo": tipo_n, "descricao": desc, "referencia": ref}


def _gravar_comprovante(bd, pid: int, campos: dict, *, attachment_id: int | None, por: str,
                        ts: str) -> int:
    novo = bd.escrever(
        "INSERT INTO dev_projetos_comprovantes (projeto_id, fase_id, tipo, descricao, referencia, "
        "attachment_id, registrado_em, registrado_por) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
        "RETURNING id",
        (pid, campos["fase_id"], campos["tipo"], campos["descricao"], campos["referencia"],
         attachment_id, ts, str(por or "").strip()),
    )
    _tocar(bd, pid, ts)
    return int(novo[0]["id"])


def registrar_comprovante(con, projeto_id: int, *, fase_id, tipo: str, descricao: str,
                          referencia: str, attachment_id: int | None = None, por: str,
                          agora: datetime | str | None = None) -> int:
    """Registra a prova de uma fase (ou do projeto, sem fase). Devolve o id.

    ARQUIVO exige o anexo (`guardar_arquivo`) e, sem referência, usa o
    sha-256 dele; LINK exige o endereço http(s); PR, o número ou o endereço
    (o do próprio repositório vira o número); TAREFA, o número ou o código;
    RELATORIO, o caminho, o endereço ou o anexo; TEXTO, só a descrição. A
    mesma referência não entra duas vezes na mesma fase. `agora` é quando foi
    registrado. Com o arquivo na mão, use `registrar_comprovante_com_arquivo`:
    ele confere antes de gravar o arquivo.
    """
    bd = banco(con)
    pid = int(projeto_id)
    anexo = None
    if attachment_id is not None:
        anexo = bd.um("SELECT id, sha256, entity_type, entity_id FROM attachments WHERE id=%s",
                      (int(attachment_id),)) if bd.tem_tabela("attachments") else None
        if (not anexo or anexo["entity_type"] != ENTIDADE_DO_ANEXO
                or int(anexo["entity_id"]) != pid):
            raise ProjetoError("O arquivo anexado não é deste projeto.")
    campos = _conferir_comprovante(bd, pid, fase_id=fase_id, tipo=tipo, descricao=descricao,
                                   referencia=referencia,
                                   sha_do_anexo=str(anexo["sha256"]) if anexo else None)
    return _gravar_comprovante(bd, pid, campos, attachment_id=int(anexo["id"]) if anexo else None,
                               por=por, ts=_agora_iso(agora))


def _conferir_arquivo(nome_arquivo, conteudo: bytes) -> tuple[str, str, str]:
    """O nome (sem pasta), a extensão e o sha-256 do arquivo, ou a recusa. Só calcula."""
    nome = re.split(r"[\\/]", str(nome_arquivo or ""))[-1].strip()
    extensao = Path(nome).suffix.lower()
    if extensao not in EXTENSOES_DO_ARQUIVO:
        raise ProjetoError("Arquivo do comprovante: PDF, imagem (JPG, PNG), texto (TXT, MD, CSV, "
                           "JSON, LOG), documento ou planilha (ODT, ODS, DOCX, XLSX) ou ZIP.")
    if not conteudo:
        raise ProjetoError("O arquivo veio vazio.")
    if len(conteudo) > TAMANHO_MAXIMO_DO_ARQUIVO:
        raise ProjetoError("O arquivo passa de 20 MB.")
    return nome, extensao, hashlib.sha256(conteudo).hexdigest()


def _guardar(bd, pid: int, nome: str, extensao: str, sha: str, conteudo: bytes, pasta,
             usuario_id: int | None, ts: str) -> tuple[int, Path | None]:
    """Grava o arquivo e a linha em `attachments`. Devolve (id, o arquivo SE foi
    escrito agora): quem chama apaga só o que esta chamada escreveu."""
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"{pid}_{sha[:16]}{extensao}"
    escrito = None
    if not destino.exists():
        destino.write_bytes(conteudo)
        escrito = destino
    try:
        novo = bd.escrever(
            "INSERT INTO attachments(entity_type, entity_id, original_name, stored_name, stored_path, "
            "sha256, size_bytes, description, uploaded_by, uploaded_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (ENTIDADE_DO_ANEXO, pid, nome, destino.name, str(destino), sha, len(conteudo),
             "Comprovante do projeto de desenvolvimento", usuario_id, ts))
    except BaseException:
        if escrito is not None:
            escrito.unlink(missing_ok=True)
        raise
    return int(novo[0]["id"]), escrito


def guardar_arquivo(con, projeto_id: int, *, nome_arquivo: str, conteudo: bytes, pasta,
                    usuario_id: int | None, agora: datetime | str | None = None) -> int:
    """Guarda o arquivo do comprovante em `attachments`. Devolve o id do anexo.

    O nome em disco sai do número do projeto e do sha-256: nada do que a
    pessoa digitou vira caminho (só a extensão, de uma lista curta). O nome
    original fica só para mostrar e para o download.
    """
    bd = banco(con)
    pid = int(projeto_id)
    if not _existe_projeto(bd, pid):
        raise LookupError("Projeto não encontrado.")
    nome, extensao, sha = _conferir_arquivo(nome_arquivo, conteudo)
    return _guardar(bd, pid, nome, extensao, sha, conteudo, pasta, usuario_id, _agora_iso(agora))[0]


def registrar_comprovante_com_arquivo(con, projeto_id: int, *, fase_id, tipo: str, descricao: str,
                                      referencia: str, nome_arquivo: str, conteudo: bytes, pasta,
                                      usuario_id: int | None, por: str,
                                      agora: datetime | str | None = None) -> tuple[int, int]:
    """O comprovante com o arquivo junto. Devolve (comprovante_id, attachment_id).

    CONFERE TUDO ANTES DE ESCREVER O ARQUIVO: o comprovante recusado não deixa
    arquivo no disco nem linha em `attachments`. Se algo falha depois de
    escrito, o arquivo que esta chamada escreveu é apagado.
    """
    bd = banco(con)
    pid = int(projeto_id)
    nome, extensao, sha = _conferir_arquivo(nome_arquivo, conteudo)
    campos = _conferir_comprovante(bd, pid, fase_id=fase_id, tipo=tipo, descricao=descricao,
                                   referencia=referencia, sha_do_anexo=sha)
    ts = _agora_iso(agora)
    anexo_id, escrito = _guardar(bd, pid, nome, extensao, sha, conteudo, pasta, usuario_id, ts)
    try:
        comprovante_id = _gravar_comprovante(bd, pid, campos, attachment_id=anexo_id, por=por, ts=ts)
    except BaseException:
        if escrito is not None:
            escrito.unlink(missing_ok=True)
        raise
    return comprovante_id, anexo_id


def _destino_do_comprovante(c: dict) -> dict:
    """Para onde o comprovante leva: o endereço de fora, o anexo ou a tarefa."""
    tipo, ref = c.get("tipo"), str(c.get("referencia") or "")
    url = None
    tarefa_id = None
    if tipo == "PR" and ref.isdigit():
        url = REPOSITORIO_PR + ref
    elif tipo in ("LINK", "PR", "RELATORIO") and _e_url(ref):
        url = ref
    elif tipo == "TAREFA" and ref.isdigit():
        tarefa_id = int(ref)
    return {"url": url, "tarefa_id": tarefa_id}


def listar_comprovantes(con, projeto_id: int) -> list[dict]:
    bd = banco(con)
    if bd.tem_tabela("attachments"):
        rows = bd.ler(
            "SELECT c.id, c.projeto_id, c.fase_id, c.tipo, c.descricao, c.referencia, "
            "c.attachment_id, c.registrado_em, c.registrado_por, a.original_name AS anexo_nome, "
            "a.sha256 AS anexo_sha256 FROM dev_projetos_comprovantes c "
            "LEFT JOIN attachments a ON a.id = c.attachment_id "
            "WHERE c.projeto_id=%s ORDER BY c.registrado_em, c.id",
            (int(projeto_id),))
    else:
        rows = bd.ler(
            "SELECT id, projeto_id, fase_id, tipo, descricao, referencia, attachment_id, "
            "registrado_em, registrado_por, NULL AS anexo_nome, NULL AS anexo_sha256 "
            "FROM dev_projetos_comprovantes WHERE projeto_id=%s ORDER BY registrado_em, id",
            (int(projeto_id),))
    saida = []
    for r in rows:
        item = dict(r)
        item["tipo_rotulo"] = TIPOS_DE_COMPROVANTE.get(item["tipo"], item["tipo"])
        item["registrado_em_exibicao"] = formatar_momento(item["registrado_em"])
        item.update(_destino_do_comprovante(item))
        saida.append(item)
    return saida


# ------------------------------------------------------------- o que falta

def _medir(fases: list[dict], *, hoje: date | None = None) -> dict:
    """O progresso e as fases abertas, na ordem. Só calcula."""
    dia = _hoje(hoje)
    total = len(fases)
    concluidas = sum(1 for f in fases if f["situacao"] == FASE_CONCLUIDA)
    dispensadas = sum(1 for f in fases if f["situacao"] == FASE_DISPENSADA)
    feitas = concluidas + dispensadas
    abertas = []
    for f in fases:
        if f["situacao"] in FASE_FEITA:
            continue
        prazo = _data_de(f.get("prazo"))
        atrasada = bool(prazo and prazo < dia)
        abertas.append({
            "id": f["id"], "ordem": f["ordem"], "titulo": f["titulo"],
            "criterio": f.get("criterio") or "", "situacao": f["situacao"],
            "situacao_rotulo": SITUACAO_DA_FASE_ROTULO.get(f["situacao"], f["situacao"]),
            "aguardando_o_que": f.get("aguardando_o_que") or "",
            "responsavel": f.get("responsavel") or "", "prazo": f.get("prazo"),
            "prazo_exibicao": formatar_dia(f.get("prazo")),
            "atrasada": atrasada, "dias_de_atraso": (dia - prazo).days if atrasada else 0,
        })
    return {
        "total": total, "concluidas": concluidas, "dispensadas": dispensadas, "feitas": feitas,
        "percentual": round(100 * feitas / total) if total else 0,
        "abertas": abertas, "proxima": abertas[0] if abertas else None,
        "atrasadas": sum(1 for f in abertas if f["atrasada"]),
        "pleno": bool(total) and not abertas, "sem_fases": total == 0,
    }


def _projeto_atrasado(projeto: dict, medida: dict, hoje: date | None) -> bool:
    prazo = _data_de(projeto.get("prazo"))
    return bool(prazo and prazo < _hoje(hoje) and not medida.get("pleno")
                and projeto.get("status_geral") != STATUS_CONCLUIDO)


def resumo_das_fases(con, *, hoje: date | None = None) -> dict[int, dict]:
    """O progresso de todos os projetos de uma vez (a lista). Só lê."""
    por_projeto: dict[int, list[dict]] = {}
    for f in banco(con).ler(f"SELECT {_COLUNAS_DA_FASE} FROM dev_projetos_fases "
                            "ORDER BY projeto_id, ordem, id"):
        por_projeto.setdefault(int(f["projeto_id"]), []).append(f)
    return {pid: _medir(fases, hoje=hoje) for pid, fases in por_projeto.items()}


def o_que_falta(con, projeto_id: int, *, hoje: date | None = None) -> dict:
    """O que falta para o resultado pleno: o progresso (concluídas e dispensadas
    sobre o total), a próxima fase e as abertas com critério, prazo,
    responsável e se está atrasada. Só lê."""
    bd = banco(con)
    projeto = obter_projeto(bd, projeto_id)
    if not projeto:
        raise LookupError("Projeto não encontrado.")
    medida = _medir(listar_fases(bd, projeto_id), hoje=hoje)
    medida["resultado_pleno"] = projeto.get("resultado_pleno") or ""
    medida["prazo_do_projeto"] = projeto.get("prazo")
    medida["projeto_atrasado"] = _projeto_atrasado(projeto, medida, hoje)
    return medida


# ------------------------------------------------------------- a linha do tempo

def linha_do_tempo(con, projeto_id: int) -> list[dict]:
    """Tudo o que aconteceu no projeto, do mais antigo ao mais novo. Só lê.

    Junta o cadastro, os andamentos, o início, a conclusão e cada mudança de
    fase (`dev_projetos_fases_historico`), os comprovantes e a retirada e a
    devolução (T019). Cada evento: data, tipo, rótulo, texto e quem.
    """
    bd = banco(con)
    pid = int(projeto_id)
    projeto = obter_projeto(bd, pid)
    if not projeto:
        raise LookupError("Projeto não encontrado.")
    eventos: list[dict] = []

    def junta(data, tipo: str, texto: str, quem, **extra) -> None:
        eventos.append({"data": str(data or ""), "tipo": tipo, "rotulo": EVENTO_ROTULO[tipo],
                        "texto": texto, "quem": str(quem or ""), **extra})

    origem = projeto.get("origem") or ""
    junta(projeto["criado_em"], "PROJETO_CRIADO",
          "Projeto cadastrado" + (f" (origem: {origem})" if origem else "") + ".",
          projeto.get("criado_por"))
    for a in reversed(listar_andamento(bd, pid)):      # do mais antigo ao mais novo
        junta(a["criado_em"], "ANDAMENTO", a["texto"], a["autor"])
    titulos = {int(f["id"]): f["titulo"] for f in listar_fases(bd, pid)}
    for h in bd.ler("SELECT fase_id, evento, situacao_antes, situacao_depois, nota, em, por "
                    "FROM dev_projetos_fases_historico WHERE projeto_id=%s ORDER BY em, id",
                    (pid,)):
        nome = titulos.get(int(h["fase_id"]), "?")
        nota = (h["nota"] or "").strip()
        if h["evento"] == "INICIADA":
            junta(h["em"], "FASE_INICIADA", f"Fase «{nome}» iniciada.", h["por"],
                  fase_id=h["fase_id"])
        elif h["evento"] == "CONCLUIDA":
            junta(h["em"], "FASE_CONCLUIDA",
                  f"Fase «{nome}» concluída." + (f" {nota}" if nota else ""), h["por"],
                  fase_id=h["fase_id"])
        else:
            antes = SITUACAO_DA_FASE_ROTULO.get(h["situacao_antes"] or "", h["situacao_antes"] or "")
            depois = SITUACAO_DA_FASE_ROTULO.get(h["situacao_depois"], h["situacao_depois"])
            extra = ""
            if nota:
                extra = (f" Aguardando: {nota}" if h["situacao_depois"] == FASE_AGUARDANDO
                         else f" {nota}")
            junta(h["em"], "FASE_SITUACAO", f"Fase «{nome}»: {antes} → {depois}.{extra}",
                  h["por"], fase_id=h["fase_id"])
    for c in listar_comprovantes(bd, pid):
        onde = f" da fase «{titulos.get(int(c['fase_id']), '?')}»" if c["fase_id"] else " do projeto"
        junta(c["registrado_em"], "COMPROVANTE",
              f"Comprovante ({c['tipo_rotulo'] if c['tipo'] == 'PR' else c['tipo_rotulo'].lower()})"
              f"{onde}: {c['descricao']}",
              c["registrado_por"], comprovante=c)
    for r in GR.historico(bd, GR.PROJETOS, str(pid)):
        motivo = (f"{r['motivo_pronto']} — " if r["motivo_pronto"] else "") + (r["motivo"] or "")
        junta(r["retirado_em"], "RETIRADO", f"Retirado dos projetos da gestão: {motivo}.",
              r["retirado_por"])
        if r["devolvido_em"]:
            junta(r["devolvido_em"], "DEVOLVIDO", "Devolvido à lista dos projetos da gestão.",
                  r["devolvido_por"])
    ordem = [e for _, e in sorted(enumerate(eventos),
                                  key=lambda par: (_chave_do_momento(par[1]["data"]), par[0]))]
    saida = _juntar_comprovantes(ordem, titulos)
    for e in saida:
        e["data_exibicao"] = formatar_momento(e["data"])
    return saida


def _juntar_comprovantes(eventos: list[dict], titulos: dict[int, str]) -> list[dict]:
    """Os comprovantes registrados de uma vez viram um evento só.

    A carga registra dezenas de comprovantes no mesmo minuto, e eles tomavam o
    alto da linha do tempo, escondendo a história real (o ensaio com os 41
    projetos, 26/11/2026). Três ou mais COMPROVANTE seguidos, do mesmo minuto
    e da mesma pessoa, viram «N comprovantes registrados de uma vez», com as
    fases a que pertencem. Cada um continua na sua fase, na ficha.
    """
    def chave(e: dict):
        return (_chave_do_momento(e["data"])[:16], e["quem"])

    saida: list[dict] = []
    i = 0
    while i < len(eventos):
        e = eventos[i]
        j = i + 1
        if e["tipo"] == "COMPROVANTE":
            while (j < len(eventos) and eventos[j]["tipo"] == "COMPROVANTE"
                   and chave(eventos[j]) == chave(e)):
                j += 1
        grupo = eventos[i:j]
        if len(grupo) < COMPROVANTES_JUNTOS:
            saida.extend(grupo)
        else:
            contagem: dict[str, int] = {}
            for g in grupo:
                fase_id = g["comprovante"]["fase_id"]
                nome = f"«{titulos.get(int(fase_id), '?')}»" if fase_id else "do projeto, sem fase"
                contagem[nome] = contagem.get(nome, 0) + 1
            onde = "; ".join(f"{nome} ({n})" for nome, n in contagem.items())
            saida.append({
                "data": e["data"], "tipo": "COMPROVANTES", "rotulo": EVENTO_ROTULO["COMPROVANTES"],
                "texto": f"{len(grupo)} comprovantes registrados de uma vez — {onde}.",
                "quem": e["quem"], "quantidade": len(grupo),
                "comprovantes": [g["comprovante"] for g in grupo]})
        i = j
    return saida


def ficha(con, projeto_id: int, *, hoje: date | None = None) -> dict | None:
    """Tudo o que a ficha mostra, numa chamada. None se o projeto não existe. Só lê."""
    bd = banco(con)
    projeto = obter_projeto(bd, projeto_id)
    if not projeto:
        return None
    projeto = dict(projeto)
    projeto["prazo_exibicao"] = formatar_dia(projeto.get("prazo"))
    falta = o_que_falta(bd, projeto_id, hoje=hoje)
    abertas = {f["id"]: f for f in falta["abertas"]}
    comprovantes = listar_comprovantes(bd, projeto_id)
    fases = []
    for f in listar_fases(bd, projeto_id):
        item = dict(f)
        item["situacao_rotulo"] = SITUACAO_DA_FASE_ROTULO.get(f["situacao"], f["situacao"])
        item["prazo_exibicao"] = formatar_dia(f.get("prazo"))
        item["iniciada_em_exibicao"] = formatar_momento(f.get("iniciada_em"))
        item["concluida_em_exibicao"] = formatar_momento(f.get("concluida_em"))
        item["atrasada"] = bool(abertas.get(f["id"], {}).get("atrasada"))
        item["comprovantes"] = [c for c in comprovantes if c["fase_id"] == f["id"]]
        fases.append(item)
    return {
        "projeto": projeto, "fases": fases, "falta": falta,
        "comprovantes_do_projeto": [c for c in comprovantes if not c["fase_id"]],
        "linha_do_tempo": linha_do_tempo(bd, projeto_id),
    }


# ------------------------------------------------------------- a carga em lote

def ler_carga(texto: str) -> list[dict]:
    """O JSON da carga: um projeto, uma lista deles ou {"projetos": [...]}. Só lê.

    Recusa a carga que repete o código ou o título de um projeto: os dois
    acertariam o mesmo projeto, e o segundo desfaria o primeiro.
    """
    bruto = str(texto or "").strip()
    if not bruto:
        raise ProjetoError("Cole a carga (JSON) ou escolha o arquivo .json.")
    try:
        dado = json.loads(bruto)
    except RecursionError:
        raise ProjetoError("A carga não é um JSON que se leia: aninhada demais.") from None
    except ValueError as erro:
        raise ProjetoError(f"A carga não é um JSON válido (linha {getattr(erro, 'lineno', '?')}).") from None
    if isinstance(dado, dict) and isinstance(dado.get("projetos"), list):
        dado = dado["projetos"]
    specs = dado if isinstance(dado, list) else [dado]
    if not specs or not all(isinstance(s, dict) for s in specs):
        raise ProjetoError("A carga é um objeto por projeto (ou uma lista deles).")
    if len(specs) > CARGA_MAXIMA_DE_PROJETOS:
        raise ProjetoError(f"A carga traz {len(specs)} projetos: no máximo "
                           f"{CARGA_MAXIMA_DE_PROJETOS} por vez.")
    codigos: set[str] = set()
    titulos: set[str] = set()
    for s in specs:
        codigo = _codigo(s.get("codigo"))
        titulo = _linha(s.get("titulo"), "Título", limite=200)
        if codigo and codigo in codigos:
            raise ProjetoError(f"A carga traz duas vezes o projeto {codigo}: junte-os num só.")
        if titulo and titulo in titulos:
            raise ProjetoError(f"A carga traz duas vezes o projeto «{titulo}»: junte-os num só.")
        codigos.add(codigo or "")
        titulos.add(titulo or "")
    return specs


def _importar_comprovante(bd, pid: int, fid: int | None, spec: dict, *, por: str, ts: str,
                          r: dict, autoria: bool) -> None:
    if not isinstance(spec, dict):
        raise ProjetoError("Cada comprovante da carga é um objeto {tipo, descricao, referencia}.")
    tipo = str(spec.get("tipo") or "").strip().upper()
    if tipo == "ARQUIVO":
        raise ProjetoError("Na carga, o arquivo entra como RELATORIO (o caminho) ou LINK; o "
                           "ARQUIVO se anexa pela ficha do projeto.")
    if tipo not in TIPOS_DE_COMPROVANTE:
        raise ProjetoError(f"Comprovante de tipo desconhecido: {tipo or '(vazio)'}.")
    referencia = _referencia(tipo, spec.get("referencia"), tem_anexo=False)
    descricao = _bloco(spec.get("descricao"), "Descrição", limite=1000)
    if _comprovante_igual(bd, pid, fid, tipo, referencia, descricao):
        return
    quem = str(spec.get("registrado_por") or "").strip() if autoria else ""
    r["comprovantes_criados"].append(registrar_comprovante(
        bd, pid, fase_id=fid, tipo=tipo, descricao=descricao, referencia=referencia,
        por=quem or por,
        agora=_momento(spec.get("registrado_em"), "Data do comprovante") or ts))


def _importar_fase(bd, pid: int, spec: dict, *, por: str, ts: str, r: dict, autoria: bool) -> int:
    """Uma fase da carga. Devolve o id. A ordem não se grava aqui: `importar`
    renumera todas no fim, na ordem do arquivo."""
    titulo = _linha(spec.get("titulo"), "Título da fase", limite=200, obrigatorio=True)
    simples = {k: spec[k] for k in CAMPOS_DA_FASE if k in spec and k not in ("titulo", "ordem")}
    alvo = _situacao_da_fase(spec["situacao"]) if spec.get("situacao") else None
    iniciada = _momento(spec.get("iniciada_em"), f"Início da fase «{titulo}»")
    concluida = _momento(spec.get("concluida_em"), f"Conclusão da fase «{titulo}»")
    if iniciada and concluida and _antes(concluida, iniciada):
        raise ProjetoError(f"A fase «{titulo}» vem concluída em {formatar_momento(concluida)}, "
                           f"antes de iniciada em {formatar_momento(iniciada)}.")
    comprovantes = _lista(spec.get("comprovantes"), f"Os comprovantes da fase «{titulo}»",
                          limite=CARGA_MAXIMA_DE_COMPROVANTES)
    fase = bd.um("SELECT id FROM dev_projetos_fases WHERE projeto_id=%s AND titulo=%s",
                 (pid, titulo))
    criada = fase is None
    if criada:
        fid = adicionar_fase(bd, pid, {"titulo": titulo, **simples}, por=por, agora=ts)
        r["fases_criadas"].append(fid)
    else:
        fid = int(fase["id"])
    # os comprovantes antes da situação: a conclusão os conta
    for c in comprovantes:
        _importar_comprovante(bd, pid, fid, c, por=por, ts=ts, r=r, autoria=autoria)
    if alvo:
        simples["situacao"] = alvo
    # a fase recém-criada já tem os campos: passá-los de novo só faz a
    # observação do arquivo contar como dada nesta mudança
    feito = _alterar_fase(bd, fid, simples, por=por, ts=ts, iniciada_em=iniciada,
                          concluida_em=concluida, observacao_da_carga=True)
    if feito["mudou"] and not criada:
        r["fases_alteradas"].setdefault(fid, {}).update(feito["mudou"])
    if feito["concluida"]:
        r["fases_concluidas"].append(fid)
    if feito.get("quem_resolvia"):
        r["quem_resolve_encerrados"].append({"id": int(feito["quem_resolvia"]["id"]),
                                             "fase_id": fid, "titulo": titulo,
                                             "por": feito["quem_resolvia"]["por"]})
    return fid


def _renumerar_pela_carga(bd, pid: int, specs_e_ids: list[tuple[int, dict, int]], *, por: str,
                          ts: str, r: dict) -> list[dict]:
    """Põe as fases na ordem do arquivo (o `ordem` dele, senão a posição na lista);
    as que existem e não vieram na carga vão para o fim, como estavam. Devolve
    essas que ficaram de fora (id e título): não se apagam nem mudam."""
    def chave(item):
        posicao, spec, _ = item
        return (_ordem(spec["ordem"]) if spec.get("ordem") not in (None, "") else posicao, posicao)

    da_carga = [fid for _, _, fid in sorted(specs_e_ids, key=chave)]
    atuais = listar_fases(bd, pid)
    fora = [f for f in atuais if int(f["id"]) not in set(da_carga)]
    nova_ordem = da_carga + [int(f["id"]) for f in fora]
    ordem_antes = {int(f["id"]): int(f["ordem"]) for f in atuais}
    if any(ordem_antes[fid] != n for n, fid in enumerate(nova_ordem, 1)):
        reordenar_fases(bd, pid, nova_ordem, por=por, agora=ts)
        criadas = set(r["fases_criadas"])
        for n, fid in enumerate(nova_ordem, 1):
            if fid not in criadas and ordem_antes[fid] != n:
                r["fases_alteradas"].setdefault(fid, {})["ordem"] = [ordem_antes[fid], n]
    return [{"id": int(f["id"]), "titulo": f["titulo"]} for f in fora]


def importar(con, spec: dict, *, por: str, agora: datetime | str | None = None,
             autoria_da_carga: bool = False) -> dict:
    """A carga de UM projeto, idempotente — a porta da carga em lote (o agente 11).

    Acha o projeto pelo `codigo`; senão pelo `titulo` exato (e então preenche
    o código que faltava; `"codigo": ""` não apaga o código de ninguém); senão
    cadastra. As fases se acham pelo (projeto, título) e são renumeradas na
    ordem do arquivo; as que existem e não vêm na carga ficam como estão, no
    fim, e voltam em `fases_fora_da_carga`. Os comprovantes se acham pela
    chave única (projeto, fase, tipo, referência) — o TEXTO sem referência,
    pela descrição; os andamentos pelo (projeto, texto). Só grava o que
    mudou: rodar duas vezes não duplica nada.

    As datas da carga valem onde dizem a verdade: `iniciada_em` no primeiro
    início da fase, `concluida_em` se não for anterior ao último evento dela;
    no resto vale `agora`. A observação da fase no arquivo conta como dada
    para concluir ou dispensar. Quem registrou o comprovante e quem escreveu o
    andamento é `por`; os nomes do arquivo (`registrado_por`, `autor`) só
    valem com `autoria_da_carga=True` (o script do agente 11; a tela, nunca).

    É tudo ou nada: a recusa de uma fase desfaz o que a carga deste projeto
    já tinha gravado (SAVEPOINT), e a transação de quem chama continua.

    Devolve, para quem chama auditar: projeto_id, codigo, titulo, projeto
    (CRIADO | ALTERADO | SEM_MUDANCA), achado_por (CODIGO | TITULO | None),
    campos_alterados {campo: [antes, depois]}, fases_criadas [ids],
    fases_alteradas {fase_id: {campo: [antes, depois]}}, fases_concluidas
    [ids], comprovantes_criados [ids], andamentos_criados [ids],
    fases_fora_da_carga [{id, titulo}] e mudou (bool).
    """
    if not isinstance(spec, dict):
        raise ProjetoError("A carga é um objeto por projeto.")
    bd = banco(con)
    ts = _agora_iso(agora)
    r: dict[str, Any] = {
        "projeto_id": None, "codigo": None, "titulo": None, "projeto": "SEM_MUDANCA",
        "achado_por": None, "campos_alterados": {}, "fases_criadas": [], "fases_alteradas": {},
        "fases_concluidas": [], "comprovantes_criados": [], "andamentos_criados": [],
        "fases_fora_da_carga": [], "quem_resolve_encerrados": [], "mudou": False,
    }
    with bd.ponto_de_retorno("dev_projetos_importar"):
        codigo = _codigo(spec.get("codigo"))
        titulo = _linha(spec.get("titulo"), "Título", limite=200)
        if not codigo and not titulo:
            raise ProjetoError("A carga precisa do código ou do título do projeto.")
        # o que vem em lista se confere antes de gravar qualquer coisa
        tem_fases = "fases" in spec
        fases = _lista(spec.get("fases"), "As fases da carga", limite=CARGA_MAXIMA_DE_FASES)
        if not all(isinstance(f, dict) for f in fases):
            raise ProjetoError("Cada fase da carga é um objeto {titulo, criterio, situacao, …}.")
        vistos: set[str] = set()
        for f in fases:
            nome = _linha(f.get("titulo"), "Título da fase", limite=200, obrigatorio=True)
            if nome in vistos:
                raise ProjetoError(f"A carga traz duas vezes a fase «{nome}»: junte-as numa só.")
            vistos.add(nome)
        comprovantes = _lista(spec.get("comprovantes"), "Os comprovantes do projeto",
                              limite=CARGA_MAXIMA_DE_COMPROVANTES)
        andamentos = _lista(spec.get("andamento"), "Os andamentos da carga",
                            limite=CARGA_MAXIMA_DE_ANDAMENTOS)
        if not all(isinstance(a, dict) for a in andamentos):
            raise ProjetoError("Cada andamento da carga é um objeto {texto, criado_em, autor}.")

        atual = None
        if codigo:
            atual = bd.um("SELECT id, codigo, titulo FROM dev_projetos WHERE codigo=%s", (codigo,))
            if atual:
                r["achado_por"] = "CODIGO"
        if atual is None and titulo:
            atual = bd.um("SELECT id, codigo, titulo FROM dev_projetos WHERE titulo=%s", (titulo,))
            if atual:
                r["achado_por"] = "TITULO"
                if codigo and atual["codigo"] and atual["codigo"] != codigo:
                    raise ProjetoError(f"O projeto «{titulo}» já tem o código {atual['codigo']}, "
                                       f"e a carga traz {codigo}.")
        dados = {k: spec[k] for k in CAMPOS_DO_PROJETO if k in spec}
        if codigo:
            dados["codigo"] = codigo
        else:
            dados.pop("codigo", None)       # a carga não apaga o código de ninguém
        if not titulo:
            dados.pop("titulo", None)       # sem título, a carga não renomeia
        if atual is None:
            if not titulo:
                raise ProjetoError(f"O projeto {codigo} ainda não existe: a carga precisa do "
                                   "título para cadastrá-lo.")
            pid = criar_projeto(bd, dados, por=por,
                                agora=_momento(spec.get("criado_em"), "Data do cadastro") or ts)
            r["projeto"] = "CRIADO"
            r["campos_alterados"] = {c: [None, v] for c, v in _campos_do_projeto(dados).items()}
        else:
            pid = int(atual["id"])
            mudou = atualizar_projeto(bd, pid, dados, por=por, agora=ts)
            if mudou:
                r["projeto"] = "ALTERADO"
                r["campos_alterados"] = mudou
        r["projeto_id"] = pid
        feitas = [(posicao, f, _importar_fase(bd, pid, f, por=por, ts=ts, r=r,
                                              autoria=autoria_da_carga))
                  for posicao, f in enumerate(fases, 1)]
        if tem_fases:
            r["fases_fora_da_carga"] = _renumerar_pela_carga(bd, pid, feitas, por=por, ts=ts, r=r)
        for c in comprovantes:
            _importar_comprovante(bd, pid, None, c, por=por, ts=ts, r=r, autoria=autoria_da_carga)
        for item in andamentos:
            texto = _bloco(item.get("texto"), "Texto do andamento", limite=LIMITE_DO_ANDAMENTO)
            if not texto or bd.um("SELECT 1 AS um FROM dev_projetos_andamento "
                                  "WHERE projeto_id=%s AND texto=%s", (pid, texto)):
                continue
            criado = _momento(item.get("criado_em"), "Data do andamento") or ts
            autor = str(item.get("autor") or "").strip() if autoria_da_carga else ""
            r["andamentos_criados"].append(int(bd.escrever(
                "INSERT INTO dev_projetos_andamento (projeto_id, texto, criado_em, autor) "
                "VALUES (%s, %s, %s, %s) RETURNING id",
                (pid, texto, criado, autor or str(por or "").strip() or None),
            )[0]["id"]))
        r["mudou"] = r["projeto"] != "SEM_MUDANCA" or any(
            r[k] for k in ("fases_criadas", "fases_alteradas", "fases_concluidas",
                           "comprovantes_criados", "andamentos_criados"))
        if r["mudou"]:
            _tocar(bd, pid, ts)
        final = obter_projeto(bd, pid)
        r["codigo"], r["titulo"] = final["codigo"], final["titulo"]
    return r
