"""As tabelas da automação — a central única das rotinas da casa.

    «um despachante que rode tudo, um lugar só para ver se rodou» — a decisão do
    oficial que fez este módulo (24/10/2026)

POR QUE TABELAS PRÓPRIAS
    Cada robô da casa nasceu com o seu jeito de dizer que rodou: o gestor em
    `ge_execucoes`, o compliance em `cp_execucoes`, os outros batendo ponto em
    `of_batidas`, e o backup e as minutas do CNIB num arquivo fora do banco.
    Ninguém via tudo num lugar só. Aqui cada rotina é uma linha de
    `au_processos`, e cada vez que ela roda é uma linha de `au_execucoes` — com
    o que achou, o que fez e, quando quebra, o rastro técnico.

AS CINCO TABELAS
    `au_processos`  o cadastro: o que roda, quando, com que prazo, quem
                    responde e por onde se avisa. **Nasce desligado.**
    `au_execucoes`  cada rodada: o relato para gente, os achados, as ações,
                    o erro e o detalhe técnico (cortado).
    `au_avisos`     cada aviso que saiu (ou não pôde sair) por um canal.
    `au_trava`      a trava global do despachante, com a batida do coração —
                    é ela que a tela lê para dizer «último tique às HH:MM».
    `au_config`     o que se configura na tela (SMTP, destinos, lembrete). A
                    SENHA DO SMTP NÃO MORA AQUI: vai para o cofre, fora do banco.

TABELA NOVA VAI NO `SCHEMA`, E NÃO EM `MIGRACOES`
    Regra da casa. Estas nascem inteiras, e as duas listas de migração ficam
    vazias até a primeira coluna chegar depois.
"""
from __future__ import annotations

import re
from typing import Any

from bd_nativo import banco

# ---------------------------------------------------------------- os tipos

FUNCAO, SCRIPT, AGENTE_IA = "FUNCAO", "SCRIPT", "AGENTE_IA"
TIPOS = (FUNCAO, SCRIPT, AGENTE_IA)
NOME_DO_TIPO = {
    FUNCAO: "verificação do sistema",
    SCRIPT: "script da instalação",
    AGENTE_IA: "agente de IA",
}

# ---------------------------------------------------------------- o disparo

AGENDA, MANUAL, RECUPERACAO = "AGENDA", "MANUAL", "RECUPERACAO"
DISPAROS = (AGENDA, MANUAL, RECUPERACAO)

# ---------------------------------------------------------------- a situação

RODANDO = "RODANDO"
OK = "OK"
AVISO = "AVISO"
ERRO = "ERRO"
TEMPO_ESGOTADO = "TEMPO_ESGOTADO"
INTERROMPIDA = "INTERROMPIDA"
PULADA = "PULADA"
SITUACOES = (RODANDO, OK, AVISO, ERRO, TEMPO_ESGOTADO, INTERROMPIDA, PULADA)

#: As que pedem gente. `PULADA` não é problema: é a rodada que não começou
#: porque a anterior ainda estava de pé, e quem decide é a anterior.
PROBLEMAS = (AVISO, ERRO, TEMPO_ESGOTADO, INTERROMPIDA)

#: O rótulo e a cor de cada situação — escritos UMA vez, e não no modelo.
ROTULO_DA_SITUACAO = {
    RODANDO: ("rodando", ""),
    OK: ("ok", "ok"),
    AVISO: ("pede atenção", "media"),
    ERRO: ("erro", "critica"),
    TEMPO_ESGOTADO: ("passou do prazo", "critica"),
    INTERROMPIDA: ("parou no meio", "alta"),
    PULADA: ("pulada (a anterior ainda rodava)", ""),
}

#: A gravidade, para saber se um problema PIOROU (e avisar de novo).
PESO = {OK: 0, PULADA: 0, RODANDO: 0, AVISO: 1, INTERROMPIDA: 2,
        TEMPO_ESGOTADO: 2, ERRO: 3}


def selo(situacao: Any) -> dict[str, str]:
    """O texto e a classe do selo. Situação desconhecida não estoura a tela."""
    texto, classe = ROTULO_DA_SITUACAO.get(str(situacao or ""), (str(situacao or "—"), ""))
    return {"situacao": str(situacao or ""), "texto": texto, "classe": classe}


# ---------------------------------------------------------------- os avisos

PAINEL, TAREFA, EMAIL, WHATSAPP = "PAINEL", "TAREFA", "EMAIL", "WHATSAPP"
CANAIS = (PAINEL, TAREFA, EMAIL, WHATSAPP)
NOME_DO_CANAL = {PAINEL: "painel e sino", TAREFA: "tarefa do responsável",
                 EMAIL: "e-mail", WHATSAPP: "WhatsApp"}
ENVIADO, FALHOU, PENDENTE_CONFIG = "ENVIADO", "FALHOU", "PENDENTE_CONFIG"
#: Por que o aviso saiu: o problema começou, o lembrete do problema que segue,
#: o problema que piorou, a volta ao normal, o e-mail de teste da tela, ou o
#: resumo do dia (o e-mail único com tudo o que segue com problema).
ALERTA, LEMBRETE, PIOROU, NORMALIZOU, TESTE, RESUMO = (
    "ALERTA", "LEMBRETE", "PIOROU", "NORMALIZOU", "TESTE", "RESUMO")

# ---------------------------------------------------------------- a config

CHAVE_SMTP_HOST = "smtp_host"
CHAVE_SMTP_PORTA = "smtp_porta"
CHAVE_SMTP_USUARIO = "smtp_usuario"
CHAVE_SMTP_REMETENTE = "smtp_remetente"
CHAVE_SMTP_SEGURANCA = "smtp_seguranca"
CHAVE_EMAIL_DESTINO = "email_destino"
CHAVE_WHATSAPP_DESTINO = "whatsapp_destino"
CHAVE_LEMBRAR = "lembrar_a_cada_h"
CHAVE_BACKUP_ESTADO = "backup_estado_caminho"
CHAVE_CNIB_LOG = "cnib_minutas_log_caminho"
CHAVE_TESTE_EMAIL = "email_teste_pedido_em"
CHAVE_TESTE_EMAIL_POR = "email_teste_pedido_por"
CHAVE_RESUMO_HORA = "email_resumo_hora"
CHAVE_RESUMO_ENVIADO = "email_resumo_enviado_em"

#: A palavra que desliga o resumo do dia. Campo vazio volta ao padrão (como
#: toda a config), e por isso desligar precisa de uma palavra própria.
RESUMO_DESLIGADO = "desligado"

SEGURANCAS_SMTP = ("STARTTLS", "SSL", "NENHUMA")

PADROES: dict[str, str] = {
    CHAVE_SMTP_HOST: "",
    CHAVE_SMTP_PORTA: "587",
    CHAVE_SMTP_USUARIO: "",
    CHAVE_SMTP_REMETENTE: "",
    CHAVE_SMTP_SEGURANCA: "STARTTLS",
    CHAVE_EMAIL_DESTINO: "",
    CHAVE_WHATSAPP_DESTINO: "",
    CHAVE_LEMBRAR: "4",
    CHAVE_BACKUP_ESTADO: "",
    CHAVE_CNIB_LOG: "",
    CHAVE_TESTE_EMAIL: "",
    CHAVE_TESTE_EMAIL_POR: "",
    CHAVE_RESUMO_HORA: "8",
    CHAVE_RESUMO_ENVIADO: "",
}
CHAVES_CONFIG = tuple(PADROES)

#: Onde mora a senha do SMTP: `avisos.cred`, cifrado na pasta de dados
#: (`cofre_cred`), e não em `au_config` — o banco vai no backup, e o backup sai
#: da serventia. E também NÃO no cofre da senha-mestra (`automacao_cofre`):
#: trancado depois de religar a máquina, ele calaria o e-mail que avisa
#: justamente que está trancado. Um lugar só: nada de «tenta o cofre, senão o
#: arquivo».
ARQUIVO_SMTP = "avisos.cred"
CHAVE_SENHA_SMTP = "smtp_senha"

SCHEMA = """
CREATE TABLE IF NOT EXISTS au_processos (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    codigo TEXT NOT NULL UNIQUE,
    nome TEXT NOT NULL,
    descricao TEXT NOT NULL DEFAULT '',
    setor TEXT NOT NULL DEFAULT 'GESTAO',
    tipo TEXT NOT NULL DEFAULT 'FUNCAO',
    alvo TEXT NOT NULL DEFAULT '',
    parametros TEXT NOT NULL DEFAULT '{}',
    agenda TEXT NOT NULL DEFAULT '{}',
    ativo INTEGER NOT NULL DEFAULT 0,
    pode_agir INTEGER NOT NULL DEFAULT 0,
    usa_credencial TEXT,
    timeout_s INTEGER NOT NULL DEFAULT 300,
    max_tentativas INTEGER NOT NULL DEFAULT 1,
    responsavel_user_id bigint,
    canais TEXT NOT NULL DEFAULT '{}',
    lembrar_a_cada_h INTEGER,
    robo_oficial TEXT,
    estado TEXT NOT NULL DEFAULT '{}',
    ativado_em TEXT,
    pedido_manual_em TEXT,
    pedido_manual_por TEXT,
    alerta_desde TEXT,
    alerta_situacao TEXT,
    alertado_em TEXT,
    aviso_id bigint,
    tarefa_id bigint,
    criado_por TEXT,
    criado_em TEXT NOT NULL,
    alterado_por TEXT,
    alterado_em TEXT
);

CREATE TABLE IF NOT EXISTS au_execucoes (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    processo_id bigint NOT NULL REFERENCES au_processos(id),
    disparo TEXT NOT NULL DEFAULT 'AGENDA',
    agendada_para TEXT,
    iniciada_em TEXT NOT NULL,
    terminada_em TEXT,
    situacao TEXT NOT NULL DEFAULT 'RODANDO',
    relato TEXT NOT NULL DEFAULT '',
    achados TEXT NOT NULL DEFAULT '[]',
    acoes TEXT NOT NULL DEFAULT '[]',
    erro TEXT,
    detalhe_tecnico TEXT,
    quem TEXT,
    pid INTEGER,
    tentativas INTEGER NOT NULL DEFAULT 0,
    duracao_s INTEGER
);
CREATE INDEX IF NOT EXISTS idx_au_execucoes_processo ON au_execucoes(processo_id, id);
CREATE INDEX IF NOT EXISTS idx_au_execucoes_situacao ON au_execucoes(situacao);
CREATE UNIQUE INDEX IF NOT EXISTS uq_au_execucoes_uma_rodando
    ON au_execucoes(processo_id) WHERE situacao = 'RODANDO';

CREATE TABLE IF NOT EXISTS au_avisos (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    execucao_id bigint,
    processo_id bigint,
    canal TEXT NOT NULL,
    motivo TEXT NOT NULL DEFAULT 'ALERTA',
    destino TEXT,
    situacao TEXT NOT NULL,
    criado_em TEXT NOT NULL,
    enviado_em TEXT,
    erro TEXT
);
CREATE INDEX IF NOT EXISTS idx_au_avisos_processo ON au_avisos(processo_id, id);

CREATE TABLE IF NOT EXISTS au_trava (
    id INTEGER PRIMARY KEY,
    dono TEXT,
    adquirida_em TEXT,
    batida_em TEXT,
    ultimo_tique_em TEXT,
    ultimo_resumo TEXT
);

CREATE TABLE IF NOT EXISTS au_config (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL DEFAULT ''
);
"""

MIGRACOES: tuple[tuple[str, str, str], ...] = ()
INDICES_DEPOIS_DA_MIGRACAO: tuple[str, ...] = ()


def init_automacao_schema(con) -> None:
    """Cria as tabelas, a linha da trava e a config. Idempotente.

    **NÃO SEMEIA OS PROCESSOS.** Quem semeia é `automacao.semear`, chamada pela
    tela e pelo despachante: o esquema não depende do catálogo das
    verificações, e o catálogo importa meio sistema.
    """
    bd = banco(con)
    for comando in re.split(r";[ \t]*\n", SCHEMA):
        if re.sub(r"--[^\n]*", "", comando).strip():
            bd.escrever(comando)
    for tabela, coluna, tipo in MIGRACOES:
        if not bd.tem_coluna(tabela, coluna):
            bd.escrever(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")
    for comando in INDICES_DEPOIS_DA_MIGRACAO:
        bd.escrever(comando)
    bd.escrever("INSERT INTO au_trava (id) VALUES (1) ON CONFLICT DO NOTHING")
    for chave, valor in PADROES.items():
        bd.escrever("INSERT INTO au_config(chave, valor) VALUES (%s, %s) "
                    "ON CONFLICT DO NOTHING", (chave, valor))


def ler_config(con, chave: str) -> str:
    """O valor gravado, ou o padrão. Chave desconhecida devolve vazio."""
    linha = banco(con).um("SELECT valor FROM au_config WHERE chave = %s", (chave,))
    if not linha or linha["valor"] in (None, ""):
        return PADROES.get(chave, "")
    return str(linha["valor"])


def gravar_config(con, chave: str, valor: Any) -> None:
    """Grava um valor. Chave fora de `CHAVES_CONFIG` é recusada, não ignorada."""
    if chave not in CHAVES_CONFIG:
        raise ValueError(f"Configuração desconhecida da automação: {chave!r}.")
    banco(con).escrever(
        "INSERT INTO au_config(chave, valor) VALUES (%s, %s) "
        "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
        (chave, str(valor if valor is not None else "")))


def lembrar_a_cada_h(con) -> int:
    """De quantas em quantas horas o problema que segue é lembrado (1 a 72)."""
    try:
        n = int(str(ler_config(con, CHAVE_LEMBRAR)).strip())
    except (TypeError, ValueError):
        n = int(PADROES[CHAVE_LEMBRAR])
    return max(1, min(72, n))


def hora_valida_do_resumo(texto: Any) -> int | None:
    """A hora (0 a 23) do resumo do dia, ou None se o texto não é uma. Só lê."""
    t = str(texto or "").strip()
    if t.isdigit() and 0 <= int(t) <= 23:
        return int(t)
    return None


def hora_do_resumo(con) -> int | None:
    """A partir de que hora sai o resumo do dia; None = desligado.

    Valor que não é hora nem «desligado» volta ao padrão: um erro de digitação
    não pode calar o único e-mail que sobrou.
    """
    valor = str(ler_config(con, CHAVE_RESUMO_HORA)).strip().lower()
    if valor == RESUMO_DESLIGADO:
        return None
    hora = hora_valida_do_resumo(valor)
    return hora if hora is not None else int(PADROES[CHAVE_RESUMO_HORA])
