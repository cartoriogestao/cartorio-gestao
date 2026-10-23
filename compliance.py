"""O agente de compliance — fiscaliza os outros agentes e o que a casa pratica e informa.

    «esse agente fiscalizará o trabalho de todos os outros agentes e a regularidade
     dos atos e informações prestadas pelo cartório» — o oficial, 09/10/2026

QUEM FISCALIZA O FISCAL
    A casa tem hoje agentes que trabalham sozinhos: o gestor (conferência das
    07:30, 14:00 e 14:30), a leitura do texto pela IA, a triagem do malote, as
    minutas do CNIB, o agente do sistema e, a partir de 09/10/2026, os agentes de
    carga do RCPN e do RI. Cada um mede o balcão. **Ninguém media cada um deles.**

    Medido no dia em que este módulo nasceu, e é por isso que ele existe:

    - a leitura do texto pela IA rodou **três dias sem ler um ato só** — 0 lidos,
      os erros subindo a cada rodada, e o log terminando em «código de saída 0».
      A causa é uma linha de configuração: `ag_config.modelo_padrao` guardava
      «Opus 5.5», o nome de vitrine, e a API respondia «não conheço esse modelo»;
    - essa linha mudou **sem nenhum registro em `audit_logs`**;
    - a tarefa do backup do gestor **fechou e reabriu** — fechamento que não se
      sustentou, o caso já conhecido da conferência rodada sem `pasta_dados`.

    Nenhum dos três aparece em tela nenhuma. Rotina que falha calada é pior que
    rotina que não existe: a que não existe ninguém acha que está protegendo.

INDEPENDENTE, DE PROPÓSITO
    Este módulo **não importa** `gestor_conferencia`, `gestor_rotina` nem os
    agentes que fiscaliza. Ele lê as tabelas que eles escrevem e mede de novo,
    pelo próprio caminho. Fiscal que usa a régua do fiscalizado confirma o
    defeito dele. Quando as duas medições divergem, o achado é sobre o gestor —
    é a «dupla medição» de `ATOS`.

NÃO CONSERTA
    Escreve só as próprias tabelas (`cp_*`), o relatório do dia e, quando há
    ponto crítico, UMA tarefa ao oficial. Consertar é de quem responde pelo
    que está errado; o fiscal que conserta apaga a prova do que fiscalizou.

REGRA QUE QUEBRA VIRA `NAO_MEDIU`, NUNCA ZERO
    A mesma régua do gestor, e pela mesma razão: zero com cara de medição é o
    carimbo que mente. E o que este módulo **ainda não mede** está declarado em
    `NAO_MEDE`, no relatório — fiscal que não diz onde não olhou deixa supor que
    olhou em tudo.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import sqlite3
import subprocess
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable

from bd_nativo import banco

QUEM = "compliance"
SOURCE_TYPE = "COMPLIANCE"

#: O CORTE É O DO OFICIAL, 06/10/2026 («não crie tarefas para atos praticados
#: antes de 10 de setembro»). Copiado do gestor, e não importado — a
#: independência é o ponto —, e `tests/test_compliance.py` exige os dois iguais.
CORTE = "2026-09-10"

GRAVIDADES = ("CRITICO", "NAO_MEDIU", "ATENCAO")
#: As origens de linha que são acervo trazido, e não ato desta casa (as mesmas do gestor).
ORIGENS_DO_ACERVO = ("EOFICIO", "ARQUIVO", "IMPORTACAO")
AREAS = {
    "AGENTES": "Fiscalização dos agentes",
    "INFORMACOES": "Informações prestadas às Centrais e órgãos",
    "ATOS": "Regularidade dos atos — segunda medição",
}

#: Rotina diária que não roda há mais que isto parou.
HORAS_SEM_RODAR = 26
#: Rotina (não servidor) «rodando» há mais que isto está travada.
MINUTOS_RODANDO = 90
#: Janela em que a IA tem de ter lido alguma coisa, se tentou.
HORAS_DA_IA = 48

#: Códigos do Agendador que não são erro: 0 terminou bem; 0x41301 está
#: rodando; 0x41303 ainda não rodou; 0x41306 alguém parou à mão.
RESULTADOS_BONS = {0, 0x41301, 0x41303, 0x41306}

#: O que este módulo AINDA NÃO MEDE. Vai no relatório, sempre.
NAO_MEDE = (
    "Se o que foi enviado às Centrais é o que está no livro, campo a campo — o "
    "compliance confere a prova e a quantidade do envio, não o conteúdo dele.",
    "Se a CRC recebeu as averbações lavradas depois da carga do assento.",
    "O que se declarou ao Justiça Aberta (CNJ) — não há registro dele no sistema.",
    "Os repasses ao FERJ e aos fundos — o sistema guarda o que se cobrou, e não o "
    "que se repassou.",
    "A tarefa do servidor de produção no Agendador (`CartorioGestaoServidor`): a "
    "conta que roda o compliance não tem permissão de lê-la; o que se mede é a "
    "resposta do servidor em /saude.",
)


# ------------------------------------------------------------------ o contexto

@dataclass
class Contexto:
    con: sqlite3.Connection
    agora: datetime
    pasta_dados: Path | None = None
    #: pares (cópia em produção, origem) cujos .py têm de bater
    copias: list[tuple[Path, Path]] = field(default_factory=list)
    #: as rotinas do Agendador; None = ler do Windows
    agendador: list[dict] | None = None
    #: a resposta do /saude; None = perguntar ao servidor
    saude: Callable[[], dict] | None = None
    versao_instalada: str | None = None
    #: False no ensaio contra o banco de produção aberto só para leitura: as
    #: regras que fotografam não fotografam.
    gravar: bool = True
    #: a pasta «6. MALOTE DIGITAL» do Proton; None = a de sempre, e só quando
    #: há `pasta_dados` (a rodada de produção) — o teste não lê o disco real.
    pasta_malote: Path | None = None

    @property
    def hoje(self) -> date:
        return self.agora.date()


def _achado(chave: str, area: str, regra: str, gravidade: str, titulo: str,
            detalhe: str = "", evidencia: str = "", fundamento: str = "",
            o_que_fazer: str = "") -> dict:
    return {"chave": chave, "area": area, "regra": regra, "gravidade": gravidade,
            "titulo": titulo, "detalhe": detalhe, "evidencia": evidencia,
            "fundamento": fundamento, "o_que_fazer": o_que_fazer}


def _dt(valor) -> datetime | None:
    """Data e hora do banco: aceita «2026-10-09T14:00:03», com espaço no lugar
    do T, e a data sozinha. O que não se lê volta None — nunca uma data inventada."""
    if not valor:
        return None
    texto = str(valor).strip().replace(" ", "T")[:19]
    try:
        return datetime.fromisoformat(texto)
    except ValueError:
        try:
            return datetime.fromisoformat(texto[:10])
        except ValueError:
            return None


def _tem_tabela(con, nome: str) -> bool:
    return banco(con).tem_tabela(nome)


def _colunas(con, tabela: str) -> set[str]:
    """As colunas pelo `information_schema`: módulo novo entra com zero (`test_portabilidade`)."""
    return {r["column_name"] for r in banco(con).ler(
        """SELECT column_name FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = %s""", (tabela,))}


def _linhas(con, sql: str, args=None) -> list[dict]:
    return banco(con).ler(sql, args)


# =================================================================== AGENTES

_PS_AGENDADOR = r"""
$saida = @(Get-ScheduledTask | Where-Object { $_.TaskName -like 'CartorioGestao*' } | ForEach-Object {
  $i = $_ | Get-ScheduledTaskInfo
  $a = @($_.Actions)[0]
  [pscustomobject]@{
    nome = $_.TaskName
    estado = [string]$_.State
    ultima = $(if ($i.LastRunTime -and $i.LastRunTime.Year -gt 2000) { $i.LastRunTime.ToString('s') } else { $null })
    resultado = [int64]$i.LastTaskResult
    proxima = $(if ($i.NextRunTime) { $i.NextRunTime.ToString('s') } else { $null })
    diario = (@($_.Triggers | Where-Object { $_.CimClass.CimClassName -eq 'MSFT_TaskDailyTrigger' }).Count -gt 0)
    executa = $a.Execute
    argumentos = $a.Arguments
  }
})
ConvertTo-Json -InputObject $saida -Depth 3
"""


def ler_agendador() -> list[dict]:
    """As rotinas `CartorioGestao*` do Agendador do Windows. Estoura se não der
    para ler — e quem chama transforma isso em NAO_MEDIU."""
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                        _PS_AGENDADOR], capture_output=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace")[:300])
    texto = r.stdout.decode("utf-8", "replace").strip() or "[]"
    dados = json.loads(texto)
    return dados if isinstance(dados, list) else [dados]


def _caminho_da_rotina(t: dict) -> Path | None:
    """O .cmd que a rotina chama — no `Execute` ou dentro dos argumentos."""
    for texto in (t.get("executa") or "", t.get("argumentos") or ""):
        m = re.search(r'"?([A-Za-z]:\\[^"]+?\.cmd)"?', texto, re.I)
        if m:
            return Path(m.group(1))
    return None


# ============================================================= O CAIXA
#: Quantos dias de lançamentos a cadeia confere a cada rodada.
DIAS_DA_CADEIA_DO_CAIXA = 60
#: A corrente da auditoria se confere nos últimos N dias — mais a semente,
#: que é a última linha encadeada antes da janela.
DIAS_DA_CADEIA_DA_AUDITORIA = 30


def _valores_de_origem(linha: dict) -> tuple[str, str, str]:
    """valor, natureza e descrição COMO ESTAVAM quando o hash foi feito.

    O lançamento editado guarda o que havia antes em `historico`
    (`caixa_web`, ação «editar»), e o hash foi feito sobre isso — editar não
    recalcula a cadeia, de propósito: é o histórico que a sustenta.
    """
    valor, natureza, descricao = (str(linha.get("valor") or ""),
                                  str(linha.get("natureza") or ""),
                                  str(linha.get("descricao") or ""))
    try:
        historico = json.loads(linha.get("historico") or "[]")
    except (TypeError, ValueError):
        historico = []
    if historico and isinstance(historico[0], dict):
        antes = historico[0].get("antes") or {}
        valor = str(antes.get("valor", valor) or "")
        natureza = str(antes.get("natureza", natureza) or "")
        descricao = str(antes.get("descricao", descricao) or "")
    return valor, natureza, descricao


def divergencias_da_cadeia_do_caixa(linhas: list[dict], *,
                                    desde: str = "") -> list[dict]:
    """Os lançamentos cujo hash não fecha com o anterior. Só calcula.

    HÁ DUAS GRAFIAS DO «ANTERIOR» NA CASA, e as duas valem: `caixa_web` encadeia
    com o último lançamento DO MESMO CAIXA; `caixa_schema.cobrar_item_do_
    protocolo` encadeia com o último hash DO MESMO ANO. Um hash que feche por
    qualquer das duas está íntegro. `linhas` vem em ordem de `id`, com TODOS
    os lançamentos que têm hash — o anterior pode estar antes de `desde`.
    """
    import caixa_schema as CXS
    ultimo_do_caixa: dict[Any, str] = {}
    ultimo_do_ano: dict[Any, str] = {}
    fora = []
    for linha in linhas:
        h = str(linha.get("hash_lancamento") or "")
        if not h:
            continue
        caixa, ano = linha.get("caixa_id"), linha.get("ano")
        if str(linha.get("data") or "") >= desde:
            valor, natureza, descricao = _valores_de_origem(linha)
            candidatos = set()
            for anterior in (ultimo_do_caixa.get(caixa), ultimo_do_ano.get(ano)):
                for v in {valor, str(linha.get("valor") or "")}:
                    candidatos.add(CXS.hash_lancamento(caixa, str(linha.get("data") or ""),
                                                       natureza, v, descricao, anterior))
            if h not in candidatos:
                fora.append({"id": linha.get("id"), "caixa_id": caixa,
                             "data": linha.get("data"), "numero": linha.get("numero"),
                             "ano": ano})
        ultimo_do_caixa[caixa] = h
        ultimo_do_ano[ano] = h
    return fora


def regra_cadeia_do_caixa(ctx: Contexto) -> list[dict]:
    """A corrente de hash do caixa confere? (revisão de segurança de
    22/10/2026, M2). Até aqui ninguém a recalculava — a cadeia existia e não
    protegia nada. Lançamento cujo hash não fecha é ATENÇÃO para o oficial,
    com o número dele: ou foi mexido por fora, ou editado sem histórico."""
    if not _tem_tabela(ctx.con, "cx_lancamentos"):
        return []
    desde = (ctx.agora - timedelta(days=DIAS_DA_CADEIA_DO_CAIXA)).date().isoformat()
    linhas = _linhas(ctx.con, """SELECT id, caixa_id, ano, numero, data, natureza, valor,
                                        descricao, historico, hash_lancamento
                                   FROM cx_lancamentos
                                  WHERE hash_lancamento IS NOT NULL
                                  ORDER BY id""")
    fora = divergencias_da_cadeia_do_caixa(linhas, desde=desde)
    if not fora:
        return []
    exemplos = ", ".join(f"#{f['numero']}/{f['ano']} (id {f['id']})" if f.get("numero")
                         else f"id {f['id']}" for f in fora[:8])
    return [_achado("CAIXA:cadeia", "CAIXA", "CAIXA_CADEIA", "CRITICO",
                    f"{len(fora)} lançamento(s) do caixa com o hash que não fecha",
                    f"Nos últimos {DIAS_DA_CADEIA_DO_CAIXA} dias: {exemplos}"
                    + ("…" if len(fora) > 8 else ""),
                    evidencia="cx_lancamentos.hash_lancamento recalculado "
                              "(duas grafias do anterior aceitas)",
                    o_que_fazer="Abrir o lançamento e o histórico dele; o que foi "
                                "mexido por fora do sistema não tem histórico.")]


def regra_cadeia_da_auditoria(ctx: Contexto) -> list[dict]:
    """A corrente de hash de `audit_logs` fecha? (revisão de segurança de
    22/10/2026). Linha apagada, editada ou inserida sem o gatilho é CRÍTICO:
    a auditoria é o que responde «quem fez» numa correição, e uma auditoria
    que se edita sem rastro não responde nada. Só lê; só calcula."""
    import auditoria_cadeia as AC
    con = ctx.con
    if not _tem_tabela(con, "audit_logs") or not banco(con).tem_coluna("audit_logs", "hash_linha"):
        return []
    desde = (ctx.agora - timedelta(days=DIAS_DA_CADEIA_DA_AUDITORIA)).isoformat(timespec="seconds")
    semente = banco(con).valor(
        """SELECT hash_linha FROM audit_logs
            WHERE ts < %s AND hash_linha IS NOT NULL ORDER BY id DESC LIMIT 1""", (desde,))
    linhas = _linhas(con, """SELECT id, ts, user_id, username_snapshot, action, entity_type,
                                    entity_id, details, ip_address, hash_anterior, hash_linha
                               FROM audit_logs WHERE ts >= %s ORDER BY id""", (desde,))
    fora = AC.divergencias(linhas, semente)
    if not fora:
        return []
    exemplos = "; ".join(f"id {f['id']} ({str(f['ts'])[:16]}, {f['action']}): {f['motivo']}"
                         for f in fora[:6])
    return [_achado("AUDITORIA:cadeia", "AUDITORIA", "AUDITORIA_CADEIA", "CRITICO",
                    f"{len(fora)} linha(s) da auditoria fora da corrente de hash",
                    f"Nos últimos {DIAS_DA_CADEIA_DA_AUDITORIA} dias: {exemplos}"
                    + ("…" if len(fora) > 6 else ""),
                    evidencia="audit_logs.hash_linha recalculado contra hash_anterior "
                              "(auditoria_cadeia.divergencias)",
                    o_que_fazer="Comparar com a cópia de segurança do dia anterior: a "
                                "auditoria não se edita, e o que falta ou mudou nela foi "
                                "feito por fora do sistema.")]


def regra_agendador(ctx: Contexto) -> list[dict]:
    rotinas = ctx.agendador if ctx.agendador is not None else ler_agendador()
    achados = []
    if not rotinas:
        return [_achado("AGENDADOR:nenhuma", "AGENTES", "AGENDADOR", "NAO_MEDIU",
                        "Nenhuma rotina CartorioGestao* encontrada no Agendador",
                        "O gestor roda pelo Agendador; lista vazia é falta de acesso "
                        "ou rotina apagada.")]
    for t in rotinas:
        nome = t.get("nome") or "?"
        servidor = not t.get("proxima")      # sem próxima execução: é serviço
        estado = (t.get("estado") or "").lower()
        resultado = t.get("resultado")
        ultima = _dt(t.get("ultima"))
        if estado == "disabled":
            achados.append(_achado(
                f"AGENDADOR:{nome}:desligada", "AGENTES", "AGENDADOR", "CRITICO",
                f"Rotina «{nome}» desligada no Agendador",
                "Rotina desligada não roda e não avisa.",
                o_que_fazer="Religar no Agendador de Tarefas, ou apagar se foi aposentada."))
            continue
        if resultado is not None and int(resultado) not in RESULTADOS_BONS:
            achados.append(_achado(
                f"AGENDADOR:{nome}:resultado", "AGENTES", "AGENDADOR", "CRITICO",
                f"A última execução de «{nome}» terminou com erro",
                f"Código {resultado} (0x{int(resultado) & 0xFFFFFFFF:X}) em "
                f"{ultima:%d/%m/%Y %H:%M}" if ultima else f"Código {resultado}",
                evidencia="Get-ScheduledTaskInfo.LastTaskResult",
                o_que_fazer="Abrir o log da rotina e ver onde parou."))
        if servidor:
            continue
        if estado == "running" and ultima and ctx.agora - ultima > timedelta(minutes=MINUTOS_RODANDO):
            minutos = int((ctx.agora - ultima).total_seconds() // 60)
            achados.append(_achado(
                f"AGENDADOR:{nome}:travada", "AGENTES", "AGENDADOR", "ATENCAO",
                f"«{nome}» está rodando há {minutos} minutos",
                "A rodada normal leva segundos; a que não termina segura a próxima.",
                o_que_fazer="Conferir no Gerenciador de Tarefas e encerrar se travou."))
        if t.get("diario") and (ultima is None or ctx.agora - ultima > timedelta(hours=HORAS_SEM_RODAR)):
            quando = f"desde {ultima:%d/%m/%Y %H:%M}" if ultima else "nunca rodou"
            achados.append(_achado(
                f"AGENDADOR:{nome}:parada", "AGENTES", "AGENDADOR", "CRITICO",
                f"Rotina diária «{nome}» não roda há mais de {HORAS_SEM_RODAR} h",
                f"Última execução: {quando}.",
                o_que_fazer="Conferir se o computador ficou desligado na hora marcada "
                            "e rodar à mão."))
    return achados


_SEPARADOR = re.compile(r"^\s*={10,}\s*$", re.M)
_SAIDA = re.compile(r"digo de sa\S*da:\s*(-?\d+)", re.I)


def ultimo_bloco_do_log(texto: str) -> str:
    """O que a última rodada escreveu: o trecho depois do último separador
    que tem conteúdo. O `.cmd` escreve o separador ANTES da rodada."""
    partes = [p for p in _SEPARADOR.split(texto) if p.strip()]
    return partes[-1] if partes else ""


def regra_log_das_rotinas(ctx: Contexto) -> list[dict]:
    """O log que fica ao lado do .cmd de cada rotina: o código de saída e os
    avisos da ÚLTIMA rodada. «Código de saída 0» com AVISO dentro é a falha
    calada — o caso da leitura da IA."""
    rotinas = ctx.agendador if ctx.agendador is not None else ler_agendador()
    achados = []
    for t in rotinas:
        cmd = _caminho_da_rotina(t)
        if cmd is None:
            continue
        log = cmd.with_suffix(".log")
        if not log.exists():
            continue
        texto = log.read_bytes().decode("utf-8", "replace")
        bloco = ultimo_bloco_do_log(texto)
        nome = t.get("nome") or cmd.stem
        m = _SAIDA.search(bloco)
        rodando = (t.get("estado") or "").lower() == "running"
        # Só cobra a linha do código de saída de quem costuma escrevê-la: a
        # rotina das minutas do CNIB não a escreve nunca (medido em 09/10/2026).
        escreve_saida = _SAIDA.search(texto) is not None
        if m and int(m.group(1)) != 0:
            achados.append(_achado(
                f"LOG:{nome}:saida", "AGENTES", "LOG_DA_ROTINA", "CRITICO",
                f"A última rodada de «{nome}» saiu com código {m.group(1)}",
                bloco.strip()[-600:], evidencia=str(log)))
        elif not m and escreve_saida and not rodando:
            achados.append(_achado(
                f"LOG:{nome}:incompleto", "AGENTES", "LOG_DA_ROTINA", "ATENCAO",
                f"O último registro de «{nome}» não diz como terminou",
                "Sem a linha do código de saída: a rodada foi interrompida no meio.",
                evidencia=str(log)))
        if re.search(r"^\s*(ERRO|Traceback)", bloco, re.M):
            achados.append(_achado(
                f"LOG:{nome}:erro", "AGENTES", "LOG_DA_ROTINA", "CRITICO",
                f"A última rodada de «{nome}» registrou erro",
                _trecho(bloco, r"^\s*(ERRO|Traceback)"), evidencia=str(log)))
        elif re.search(r"^\s*AVISO", bloco, re.M):
            achados.append(_achado(
                f"LOG:{nome}:aviso", "AGENTES", "LOG_DA_ROTINA", "ATENCAO",
                f"A última rodada de «{nome}» terminou com aviso",
                _trecho(bloco, r"^\s*AVISO"), evidencia=str(log)))
    return achados


def _trecho(texto: str, padrao: str, tamanho: int = 500) -> str:
    m = re.search(padrao, texto, re.M)
    return texto[m.start():m.start() + tamanho].strip() if m else texto[-tamanho:].strip()


def regra_execucoes_do_gestor(ctx: Contexto) -> list[dict]:
    con = ctx.con
    if not _tem_tabela(con, "ge_execucoes"):
        return []
    achados = []
    ultima = banco(con).valor("SELECT max(iniciada_em) AS ultima FROM ge_execucoes")
    quando = _dt(ultima)
    if quando is None or ctx.agora - quando > timedelta(hours=HORAS_SEM_RODAR):
        achados.append(_achado(
            "GESTOR:parado", "AGENTES", "GESTOR_EXECUCAO", "CRITICO",
            "O gestor não conferiu a casa nas últimas 26 horas",
            f"Última rodada registrada: {quando:%d/%m/%Y %H:%M}." if quando else
            "Nenhuma rodada registrada em ge_execucoes.",
            evidencia="ge_execucoes.iniciada_em"))
    limite = (ctx.agora - timedelta(days=7)).isoformat(timespec="seconds")
    for e in _linhas(con, """SELECT id, iniciada_em, terminada_em, erro FROM ge_execucoes
                              WHERE iniciada_em >= %s ORDER BY id""", (limite,)):
        if e["erro"]:
            achados.append(_achado(
                f"GESTOR:erro:{e['id']}", "AGENTES", "GESTOR_EXECUCAO", "CRITICO",
                f"A rodada do gestor de {_dt(e['iniciada_em']):%d/%m %H:%M} quebrou",
                e["erro"][:400], evidencia=f"ge_execucoes.id={e['id']}"))
        elif not e["terminada_em"] and ctx.agora - (_dt(e["iniciada_em"]) or ctx.agora) > timedelta(hours=1):
            achados.append(_achado(
                f"GESTOR:sem_fim:{e['id']}", "AGENTES", "GESTOR_EXECUCAO", "CRITICO",
                f"A rodada do gestor de {_dt(e['iniciada_em']):%d/%m %H:%M} não terminou",
                "Sem terminada_em nem erro: o processo morreu no meio.",
                evidencia=f"ge_execucoes.id={e['id']}"))
    return achados


#: Onde cada agente de IA grava o que tentou. (tabela, coluna da hora, como se
#: sabe que falhou, nome para o relatório)
FONTES_DE_IA = (
    ("ge_leituras", "lido_em", "erro", "A leitura do texto dos atos pela IA (gestor)"),
    ("ge_triagens", "lido_em", "erro", "A triagem do malote pela IA (gestor)"),
    ("rv_revisoes", "pedido_em", "erro", "A revisão antes da lavratura (Opus)"),
    ("aj_consultas", "perguntada_em", "falha", "A ajuda do sistema"),
)


def regra_ia_sem_resultado(ctx: Contexto) -> list[dict]:
    con = ctx.con
    desde = (ctx.agora - timedelta(hours=HORAS_DA_IA)).isoformat(timespec="seconds")
    achados = []
    for tabela, quando, falha, nome in FONTES_DE_IA:
        if not _tem_tabela(con, tabela) or not {quando, falha} <= _colunas(con, tabela):
            continue
        linhas = _linhas(con, f"SELECT {falha} AS falha FROM {tabela} WHERE {quando} >= %s "
                              "ORDER BY id", (desde,))
        erros = [str(r["falha"]) for r in linhas if r["falha"] not in (None, "", 0)]
        certos = len(linhas) - len(erros)
        if not erros:
            continue
        mais = Counter(e[:160] for e in erros).most_common(1)[0][0]
        if certos == 0:
            achados.append(_achado(
                f"IA:{tabela}:parou", "AGENTES", "IA_SEM_RESULTADO", "CRITICO",
                f"{nome} não produziu nada em {HORAS_DA_IA} h — {len(erros)} tentativa(s), "
                "todas com erro",
                f"Erro mais comum: {mais}",
                evidencia=f"{tabela}.{falha} desde {desde}",
                o_que_fazer="O erro diz a causa. Se for «não conhece o modelo», o nome "
                            "gravado na configuração do agente não é o identificador da API."))
        elif len(erros) > certos:
            achados.append(_achado(
                f"IA:{tabela}:falha", "AGENTES", "IA_SEM_RESULTADO", "ATENCAO",
                f"{nome}: {len(erros)} erro(s) contra {certos} resultado(s) em {HORAS_DA_IA} h",
                f"Erro mais comum: {mais}", evidencia=f"{tabela}.{falha}"))
    return achados


#: O identificador de modelo que as APIs aceitam: minúsculas, dígitos, ponto,
#: hífen. «Opus 5.5» (com espaço e maiúscula) é o nome de vitrine, e a API recusa.
_ID_DE_MODELO = re.compile(r"^[a-z0-9][a-z0-9.\-_:/]*$")


def regra_config_do_modelo(ctx: Contexto) -> list[dict]:
    con = ctx.con
    achados = []
    lugares = []
    if _tem_tabela(con, "ag_config"):
        r = banco(con).um("SELECT valor FROM ag_config WHERE chave='modelo_padrao'")
        if r:
            lugares.append(("ag_config.modelo_padrao", "o agente do sistema, a leitura do "
                            "texto e a revisão", r["valor"]))
    if _tem_tabela(con, "aj_config") and "modelo" in _colunas(con, "aj_config"):
        for r in _linhas(con, "SELECT modelo FROM aj_config ORDER BY id"):
            lugares.append(("aj_config.modelo", "a ajuda do sistema", r["modelo"]))
    for onde, quem, valor in lugares:
        if valor and not _ID_DE_MODELO.match(str(valor).strip()):
            achados.append(_achado(
                f"CONFIG_MODELO:{onde}", "AGENTES", "CONFIG_DO_MODELO", "CRITICO",
                f"O modelo de IA gravado em {onde} não é um identificador válido",
                f"Gravado: «{valor}». É o nome de vitrine, com espaço ou maiúscula; a API "
                f"só aceita o identificador (ex.: «claude-opus-5-5»). Atinge {quem}.",
                evidencia=onde,
                o_que_fazer="Trocar pelo identificador na tela de configuração do agente "
                            "(Administrativo → Agente) — ou deixar vazio para o padrão."))
    return achados


#: O que se fotografa a cada rodada para saber o que mudou e quem registrou.
#: Valor de chave com cara de segredo vai só como hash: a fotografia mora no
#: banco, e o banco viaja no backup.
_SEGREDO = re.compile(r"senha|token|secret|chave_api|api_key|password|cred", re.I)


def _fotos(con) -> dict[str, str]:
    foto: dict[str, str] = {}
    if _tem_tabela(con, "ag_config"):
        for r in _linhas(con, "SELECT chave, valor FROM ag_config ORDER BY chave"):
            foto[f"ag_config.{r['chave']}"] = str(r["valor"])
    if _tem_tabela(con, "aj_config"):
        cols = _colunas(con, "aj_config") - {"alterada_em", "escolha_em"}
        for r in _linhas(con, "SELECT * FROM aj_config ORDER BY id"):
            for k in sorted(cols):
                foto[f"aj_config.{r.get('id', 1)}.{k}"] = str(r.get(k))
    if _tem_tabela(con, "settings"):
        for r in _linhas(con, "SELECT key, value FROM settings ORDER BY key"):
            k, v = r["key"], str(r["value"])
            if _SEGREDO.search(str(k)):
                v = "sha256:" + hashlib.sha256(v.encode()).hexdigest()[:16]
            foto[f"settings.{k}"] = v[:300]
    if _tem_tabela(con, "ge_responsaveis"):
        for r in _linhas(con, "SELECT setor, user_id, substituto_id, rodizio FROM ge_responsaveis "
                              "ORDER BY setor"):
            foto[f"ge_responsaveis.{r['setor']}"] = (
                f"titular={r['user_id']} substituto={r['substituto_id']} rodizio={r['rodizio']}")
    if _tem_tabela(con, "users"):
        for r in _linhas(con, "SELECT username, role, active FROM users ORDER BY id"):
            foto[f"users.{r['username']}"] = f"perfil={r['role']} ativo={r['active']}"
    return foto


def regra_config_sem_rastro(ctx: Contexto) -> list[dict]:
    """Compara a fotografia de agora com a da rodada anterior. O que mudou e
    não deixou NENHUMA linha de auditoria no intervalo foi mudado por fora."""
    con = ctx.con
    if not ctx.gravar or not _tem_tabela(con, "cp_fotografias"):
        return []
    agora = ctx.agora.isoformat(timespec="seconds")
    bd = banco(con)
    anterior = {r["chave"]: (r["valor"], r["tirada_em"]) for r in _linhas(
        con, "SELECT chave, valor, tirada_em FROM cp_fotografias ORDER BY chave")}
    atual = _fotos(con)
    if anterior:
        desde = min(t for _, t in anterior.values())
        trilha = bd.valor(
            "SELECT count(*) AS n FROM audit_logs WHERE ts >= %s AND (action ILIKE '%%CONFIG%%' "
            "OR action ILIKE '%%SETTING%%' OR action ILIKE '%%AJUSTE%%' OR action ILIKE 'AG\\_%%' "
            "ESCAPE '\\' OR action ILIKE '%%RESPONSAV%%' OR action ILIKE '%%USUARIO%%' "
            "OR action ILIKE '%%USER%%')", (desde,)) if _tem_tabela(con, "audit_logs") else 0
        for chave in sorted(set(anterior) | set(atual)):
            antes = anterior.get(chave, (None, None))[0]
            depois = atual.get(chave)
            if antes == depois:
                continue
            bd.escrever(
                """INSERT INTO cp_mudancas (chave, antes, depois, vista_em, com_rastro)
                   VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                (chave, antes, depois, agora, 1 if trilha else 0))
    bd.escrever("DELETE FROM cp_fotografias")
    for k, v in atual.items():
        bd.escrever("INSERT INTO cp_fotografias (chave, valor, tirada_em) VALUES (%s,%s,%s)",
                    (k, v, agora))
    sete = (ctx.agora - timedelta(days=7)).isoformat(timespec="seconds")
    achados = []
    for m in _linhas(con, """SELECT id, chave, antes, depois, vista_em FROM cp_mudancas
                              WHERE com_rastro = 0 AND vista_em >= %s ORDER BY id""", (sete,)):
        achados.append(_achado(
            f"CONFIG_SEM_RASTRO:{m['id']}", "AGENTES", "CONFIG_SEM_RASTRO", "ATENCAO",
            f"A configuração «{m['chave']}» mudou sem registro na auditoria",
            f"De «{m['antes']}» para «{m['depois']}» — percebido em "
            f"{_dt(m['vista_em']):%d/%m/%Y %H:%M}.",
            evidencia="cp_fotografias × audit_logs",
            o_que_fazer="Confirmar se a mudança foi sua; se não foi, desfazer."))
    return achados


def regra_fechou_sem_medir(ctx: Contexto) -> list[dict]:
    """Achado do gestor marcado resolvido no MESMO instante em que a regra dele
    não conseguiu medir: não foi resolvido, foi esquecido."""
    con = ctx.con
    if not _tem_tabela(con, "ge_achados"):
        return []
    falhas = {(r["chave"][len("NAO_MEDIU:"):], r["ultimo_visto_em"]) for r in _linhas(
        con, "SELECT chave, ultimo_visto_em FROM ge_achados WHERE chave ILIKE 'NAO_MEDIU:%' "
             "ORDER BY id")}
    if not falhas:
        return []
    achados = []
    for a in _linhas(con, """SELECT id, chave, regra, titulo, resolvido_em FROM ge_achados
                              WHERE resolvido_em IS NOT NULL AND chave NOT ILIKE 'NAO_MEDIU:%'
                              ORDER BY id"""):
        if (a["regra"], a["resolvido_em"]) in falhas:
            achados.append(_achado(
                f"FECHOU_SEM_MEDIR:{a['id']}", "AGENTES", "FECHOU_SEM_MEDIR", "CRITICO",
                f"O gestor deu por resolvido «{a['titulo']}» na rodada em que não conseguiu medir",
                f"Regra {a['regra']}, {_dt(a['resolvido_em']):%d/%m/%Y %H:%M}.",
                evidencia=f"ge_achados.id={a['id']}"))
    return achados


def regra_fechou_e_reabriu(ctx: Contexto) -> list[dict]:
    """Tarefa do gestor que ele fechou («não há mais pendência») e reabriu depois."""
    con = ctx.con
    if not _tem_tabela(con, "tasks"):
        return []
    desde = (ctx.agora - timedelta(days=14)).isoformat(timespec="seconds")
    achados = []
    for t in _linhas(con, """SELECT id, source_ref, title FROM tasks WHERE source_type='GESTOR'
                              ORDER BY id"""):
        historico = _linhas(con, """SELECT ts, action, note FROM task_history WHERE task_id=%s
                                     ORDER BY id""", (t["id"],))
        fechou = [h for h in historico if (h["note"] or "").startswith("Fechada pela conferência")]
        reabriu = [h for h in historico if h["action"] == "REABERTA" and (h["ts"] or "") >= desde
                   and any(f["ts"] <= h["ts"] for f in fechou)]
        if reabriu:
            achados.append(_achado(
                f"FECHOU_E_REABRIU:{t['id']}", "AGENTES", "FECHOU_E_REABRIU", "ATENCAO",
                f"A tarefa #{t['id']} fechou sozinha e voltou: o fechamento não se sustentou",
                f"{t['title']} — fechada {len(fechou)} vez(es), reaberta {len(reabriu)} "
                "nos últimos 14 dias. Ou a regra deixou de medir por um dia, ou o "
                "problema voltou.",
                evidencia=f"task_history da tarefa {t['id']} ({t['source_ref']})"))
    return achados


def _hash_do_arquivo(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def regra_copia_divergente(ctx: Contexto) -> list[dict]:
    """A produção roda a cópia em FERRAMENTAS; o desenvolvimento mexe no
    SANDBOX. Cópia diferente da origem é produção rodando outra versão."""
    achados = []
    for producao, origem in ctx.copias:
        if not producao.is_dir() or not origem.is_dir():
            continue
        diferentes = []
        for p in sorted(producao.glob("*.py")):
            o = origem / p.name
            if o.exists() and _hash_do_arquivo(p) != _hash_do_arquivo(o):
                mo, mp = (datetime.fromtimestamp(x.stat().st_mtime) for x in (o, p))
                diferentes.append(f"{p.name} (origem {mo:%d/%m %H:%M}, produção {mp:%d/%m %H:%M})")
        if diferentes:
            achados.append(_achado(
                f"COPIA:{producao.name}", "AGENTES", "COPIA_DIVERGENTE", "ATENCAO",
                f"A cópia em produção de {producao.name} difere da origem em "
                f"{len(diferentes)} arquivo(s)",
                "; ".join(diferentes[:12]),
                evidencia=f"sha256 {producao} × {origem}",
                o_que_fazer="Recopiar da origem para a pasta de produção, ou registrar "
                            "por que a produção está diferente."))
    return achados


def regra_agente_mexeu(ctx: Contexto) -> list[dict]:
    """O que o agente do sistema mudou sozinho e ninguém reverteu nem olhou."""
    con = ctx.con
    if not _tem_tabela(con, "ag_mudancas"):
        return []
    desde = (ctx.agora - timedelta(days=7)).isoformat(timespec="seconds")
    linhas = _linhas(con, """SELECT id, ferramenta, alvo, criada_em FROM ag_mudancas
                              WHERE revertida_em IS NULL AND criada_em >= %s
                              ORDER BY id""", (desde,))
    if not linhas:
        return []
    return [_achado(
        "AGENTE_MEXEU:semana", "AGENTES", "AGENTE_MEXEU", "ATENCAO",
        f"O agente do sistema fez {len(linhas)} mudança(s) nos últimos 7 dias",
        "; ".join(f"{m['ferramenta']} em {m['alvo']}" for m in linhas[:10]),
        evidencia="ag_mudancas", o_que_fazer="Conferir na tela do agente; cada uma volta com um clique.")]


_PRAZO_NO_TEXTO = re.compile(
    r"\bprazo\b|\bintim|\bdetermin|\bsob pena\b|\bdias? (?:úteis|uteis|corridos)\b", re.I)


def regra_triagem_duvidosa(ctx: Contexto) -> list[dict]:
    """O malote que a IA mandou «para ciência» e que fala em prazo ou
    determinação. Ciência é o único destino que não vira tarefa — e por isso o
    único em que o erro da IA some sem deixar rastro."""
    con = ctx.con
    if not _tem_tabela(con, "ge_triagens"):
        return []
    desde = (ctx.agora - timedelta(days=30)).isoformat(timespec="seconds")
    achados = []
    for t in _linhas(con, """SELECT id, expediente_id, resultado_json FROM ge_triagens
                              WHERE erro IS NULL AND tarefa_id IS NULL AND lido_em >= %s
                              ORDER BY id""",
                     (desde,)):
        try:
            r = json.loads(t["resultado_json"] or "{}")
        except ValueError:
            continue
        if (r.get("tipo") or "").upper() != "CIENCIA":
            continue
        texto = " ".join(str(r.get(k) or "") for k in ("resumo", "o_que_fazer"))
        if r.get("prazo_dias") or r.get("data_limite") or _PRAZO_NO_TEXTO.search(texto):
            limite = _dt(r.get("data_limite"))
            prazo = (f" A própria IA anotou prazo de {r.get('prazo_dias') or '?'} dia(s)"
                     f"{f', até {limite:%d/%m/%Y}' if limite else ''}, e não abriu tarefa."
                     if r.get("prazo_dias") or limite else "")
            achados.append(_achado(
                f"TRIAGEM:{t['expediente_id']}", "AGENTES", "TRIAGEM_DUVIDOSA",
                "CRITICO" if limite and limite.date() <= ctx.hoje + timedelta(days=2) else "ATENCAO",
                f"Expediente {t['expediente_id']}: a IA mandou para ciência, e ele fala "
                "em prazo ou determinação",
                (r.get("resumo") or "")[:300] + prazo,
                evidencia=f"ge_triagens.id={t['id']}",
                o_que_fazer="Ler o expediente: se pede providência, abrir a tarefa à mão."))
    return achados


def regra_servidor(ctx: Contexto) -> list[dict]:
    """O servidor responde, e responde com a versão que está instalada. Em
    15/09/2026 o disco tinha a versão nova e quem respondia era o processo velho."""
    try:
        saude = ctx.saude() if ctx.saude else _perguntar_saude()
    except Exception as erro:                            # noqa: BLE001
        return [_achado("SERVIDOR:fora", "AGENTES", "SERVIDOR", "CRITICO",
                        "O servidor de produção não respondeu em /saude",
                        f"{type(erro).__name__}: {erro}",
                        o_que_fazer="Conferir se o sistema está no ar no balcão.")]
    achados = []
    if not saude.get("ok"):
        achados.append(_achado("SERVIDOR:nao_ok", "AGENTES", "SERVIDOR", "CRITICO",
                               "O servidor respondeu, mas diz que não está bem",
                               json.dumps(saude, ensure_ascii=False)[:300]))
    instalada = ctx.versao_instalada
    if instalada and saude.get("version") and saude["version"] != instalada:
        achados.append(_achado(
            "SERVIDOR:versao", "AGENTES", "SERVIDOR", "CRITICO",
            "O servidor responde com uma versão diferente da instalada",
            f"Responde {saude['version']}; instalada {instalada}. O disco tem uma versão "
            "e quem atende o balcão é outra.",
            o_que_fazer="Reiniciar o servidor pelo caminho de atualização."))
    return achados


#: O banco que roda e o acervo morto não são cópia.
BANCOS_VIVOS = {"cartorio_gestao.sqlite3", "acervo_eoficio.sqlite3", "cartorio.sqlite3"}
#: «antes-minutas-cnib-20261009-074502»: o que a cópia antecede e o DIA, que
#: vem no nome — a data do arquivo em disco muda quando alguém copia a pasta.
_SLUG_DA_COPIA = re.compile(r"antes[-_](.+?)[-_](\d{8})[-_]\d{6}", re.I)


def regra_copias_do_banco(ctx: Contexto) -> list[dict]:
    """As cópias inteiras do banco que os scripts e os agentes deixam na pasta
    de dados antes de mexer nele («cartorio_gestao.antes-…sqlite3»).

    MEDIDO EM 09/10/2026: 107 cópias, 48,6 GB — 41 delas e 32,8 GB só na última
    semana — com 8,5 GB livres no disco do servidor. O banco tem 1 GB; cada
    cópia nova também. Disco cheio para o SQLite no meio de uma gravação, e
    para o backup da noite. Uma das que se repetem é a da rotina diária das
    minutas do CNIB, que copia o banco inteiro mesmo quando não gera minuta."""
    if ctx.pasta_dados is None or not Path(ctx.pasta_dados).is_dir():
        return []
    import shutil
    pasta = Path(ctx.pasta_dados)
    copias = [p for p in pasta.glob("*.sqlite3") if p.name not in BANCOS_VIVOS]
    if not copias:
        return []
    total = sum(p.stat().st_size for p in copias)
    semana = ctx.agora - timedelta(days=7)
    recentes = [p for p in copias if datetime.fromtimestamp(p.stat().st_mtime) > semana]
    do_recente = sum(p.stat().st_size for p in recentes)
    livre = shutil.disk_usage(pasta).free
    vivo = pasta / "cartorio_gestao.sqlite3"
    tamanho_vivo = vivo.stat().st_size if vivo.exists() else 0
    # quem faz cópia todo dia: o mesmo nome em três dias diferentes
    dias: dict[str, set] = {}
    for p in copias:
        m = _SLUG_DA_COPIA.search(p.name)
        if m:
            slug = re.sub(r"\d+", "#", m.group(1))
            dias.setdefault(slug, set()).add(m.group(2))
    repetidas = sorted((s for s, d in dias.items() if len(d) >= 3), key=lambda s: -len(dias[s]))
    gb = 1024 ** 3

    def _gb(n: int) -> str:
        return f"{n / gb:.1f}".replace(".", ",") + " GB"
    critico = livre < 3 * max(tamanho_vivo, gb) or do_recente > 10 * gb
    detalhe = (f"{len(copias)} cópia(s), {_gb(total)} no total; {len(recentes)} nos "
               f"últimos 7 dias ({_gb(do_recente)}). Livre no disco: {_gb(livre)}; o "
               f"banco tem {_gb(tamanho_vivo)}.")
    if repetidas:
        detalhe += " Fazem cópia em vários dias: " + "; ".join(
            f"«antes-{s}» ({len(dias[s])} dias)" for s in repetidas[:6]) + "."
    return [_achado(
        "COPIAS_DO_BANCO", "AGENTES", "COPIAS_DO_BANCO", "CRITICO" if critico else "ATENCAO",
        "Cópias inteiras do banco acumuladas na pasta de dados",
        detalhe, evidencia=str(pasta),
        o_que_fazer="Decidir quais guardar e levar as antigas para um disco externo; e "
                    "trocar, nas rotinas diárias, a cópia inteira por cópia só quando "
                    "vão de fato gravar algo.")]


PORTA_DA_PRODUCAO = 8765


def _perguntar_saude() -> dict:
    with urllib.request.urlopen(f"http://127.0.0.1:{PORTA_DA_PRODUCAO}/saude", timeout=8) as r:
        return json.loads(r.read().decode("utf-8"))


# =============================================================== INFORMAÇÕES

def regra_envio_sem_prova(ctx: Contexto) -> list[dict]:
    """O que a casa diz que mandou tem de ter com que provar. «Enviado» sem
    protocolo é afirmação; comprovante apontado e que não existe é pior."""
    con = ctx.con
    achados = []
    if _tem_tabela(con, "ge_envios"):
        sem_recibo: dict[str, list] = {}
        for e in _linhas(con, "SELECT * FROM ge_envios ORDER BY id"):
            prot = (e.get("protocolo") or "").strip()
            if e["situacao"] == "ENVIADO" and not prot:
                achados.append(_achado(
                    f"ENVIO:ge:{e['id']}:protocolo", "INFORMACOES", "ENVIO_SEM_PROVA", "CRITICO",
                    f"Envio ao {e['central']} registrado sem protocolo",
                    f"{e['referencia'] or e['competencia'] or ''} — registrado por "
                    f"{e['registrado_por']} em {e['registrado_em']}",
                    evidencia=f"ge_envios.id={e['id']}"))
            recibo = e.get("recibo_caminho")
            if recibo and not Path(recibo).exists():
                achados.append(_achado(
                    f"ENVIO:ge:{e['id']}:recibo", "INFORMACOES", "ENVIO_SEM_PROVA", "CRITICO",
                    f"O comprovante do envio ao {e['central']} não está onde o registro diz",
                    str(recibo), evidencia=f"ge_envios.id={e['id']}"))
            if e["situacao"] == "ENVIADO" and not recibo:
                sem_recibo.setdefault(e["central"], []).append(e)
            if e["situacao"] == "DISPENSADO" and len((e.get("mensagem") or "").strip()) < 20:
                achados.append(_achado(
                    f"ENVIO:ge:{e['id']}:dispensa", "INFORMACOES", "ENVIO_SEM_PROVA", "ATENCAO",
                    f"Dispensa de envio ao {e['central']} sem motivo escrito",
                    e["referencia"] or "", evidencia=f"ge_envios.id={e['id']}"))
        for central, envios in sem_recibo.items():
            por_agente = sum(1 for e in envios if (e.get("origem") or "") == "AGENTE")
            achados.append(_achado(
                f"ENVIO:ge:{central}:sem_recibo", "INFORMACOES", "ENVIO_SEM_PROVA", "ATENCAO",
                f"{len(envios)} envio(s) ao {central} sem comprovante arquivado",
                f"Têm protocolo, e o comprovante não foi guardado no sistema"
                f"{f' ({por_agente} registrados por agente)' if por_agente else ''}. Numa "
                "correição, a prova fica só no portal da Central.",
                evidencia="ge_envios.recibo_caminho vazio",
                o_que_fazer="Baixar o comprovante no portal e anexar ao registro."))
    if _tem_tabela(con, "rc_crc_lotes"):
        cols = _colunas(con, "rc_crc_lotes")
        sem = _linhas(con, f"""SELECT id, quantos, enviado_em FROM rc_crc_lotes
                               WHERE COALESCE(resposta,'') = ''
                               {"AND COALESCE(canal,'') = 'MANUAL'" if 'canal' in cols else ''}
                               ORDER BY id""")
        if sem:
            achados.append(_achado(
                "ENVIO:crc:sem_resposta", "INFORMACOES", "ENVIO_SEM_PROVA", "ATENCAO",
                f"{len(sem)} lote(s) da CRC registrados como enviados sem a resposta da Central",
                "; ".join(f"lote {x['id']} ({x['quantos']} assentos, {str(x['enviado_em'])[:10]})"
                          for x in sem),
                evidencia="rc_crc_lotes.resposta vazia",
                o_que_fazer="Guardar o retorno da CRC (o relatório de carga) em cada lote."))
    for tabela, quando, prova, nome in (
            ("ib_entregas", "enviada_em", "protocolo", "IBGE"),
            ("ri_doi_remessas", "entregue_em", "recibo", "DOI"),
            ("nt_remessas", "enviada_em", "protocolo_central", "remessa de Notas")):
        if not _tem_tabela(con, tabela) or not {quando, prova} <= _colunas(con, tabela):
            continue
        for x in _linhas(con, f"""SELECT id FROM {tabela}
                                  WHERE {quando} IS NOT NULL AND COALESCE({prova},'') = ''
                                  ORDER BY id"""):
            achados.append(_achado(
                f"ENVIO:{tabela}:{x['id']}", "INFORMACOES", "ENVIO_SEM_PROVA", "CRITICO",
                f"Entrega de {nome} registrada sem {prova}",
                evidencia=f"{tabela}.id={x['id']}"))
    if _tem_tabela(con, "ri_onr_envios"):
        tres = (ctx.agora - timedelta(days=3)).isoformat(timespec="seconds")
        pend = _linhas(con, """SELECT id, especie, enviado_em FROM ri_onr_envios
                               WHERE situacao = 'ENVIADO' AND fila_situacao IS NULL
                                 AND enviado_em < %s
                               ORDER BY id""", (tres,))
        if pend:
            achados.append(_achado(
                "ENVIO:onr:sem_fila", "INFORMACOES", "ENVIO_SEM_PROVA", "ATENCAO",
                f"{len(pend)} envio(s) ao ONR sem confirmação da fila há mais de 3 dias",
                "Enviar não é ser aceito: o ONR processa depois.",
                evidencia="ri_onr_envios.fila_situacao vazia"))
    return achados


def regra_quantos_nao_fecha(ctx: Contexto) -> list[dict]:
    """O número que o envio declara é o número de itens que o sistema amarrou a ele."""
    con = ctx.con
    achados = []
    if _tem_tabela(con, "ge_envios"):
        grupos: dict[tuple, list] = {}
        for e in _linhas(con, """SELECT id, central, protocolo, quantos FROM ge_envios
                                  WHERE situacao='ENVIADO' AND COALESCE(protocolo,'') <> ''
                                  ORDER BY id"""):
            grupos.setdefault((e["central"], e["protocolo"]), []).append(e)
        for (central, prot), envios in grupos.items():
            declarados = {e["quantos"] for e in envios if e["quantos"] is not None}
            if len(declarados) > 1 or (declarados and max(declarados) != len(envios)):
                achados.append(_achado(
                    f"QUANTOS:ge:{central}:{prot}", "INFORMACOES", "QUANTOS_NAO_FECHA", "ATENCAO",
                    f"O envio ao {central} «{prot}» declara {sorted(declarados)} item(ns) e "
                    f"o sistema amarra {len(envios)}",
                    evidencia="ge_envios agrupado por protocolo"))
    if _tem_tabela(con, "rc_crc_lotes") and _tem_tabela(con, "rc_crc_lote_assentos"):
        for l in _linhas(con, """SELECT l.id, l.quantos,
                                       (SELECT count(*) FROM rc_crc_lote_assentos x
                                         WHERE x.lote_id = l.id) AS itens
                                  FROM rc_crc_lotes l ORDER BY l.id"""):
            if l["quantos"] is not None and l["quantos"] != l["itens"]:
                achados.append(_achado(
                    f"QUANTOS:crc:{l['id']}", "INFORMACOES", "QUANTOS_NAO_FECHA", "ATENCAO",
                    f"O lote {l['id']} da CRC declara {l['quantos']} assentos e amarra {l['itens']}",
                    evidencia="rc_crc_lotes × rc_crc_lote_assentos"))
    return achados


def _dia_util():
    """O calendário da casa (feriados de `ri_schema`); sem ele, segunda a sexta,
    e o achado diz que a conta foi sem feriados."""
    try:
        from ri_schema import eh_dia_util
        return eh_dia_util, True
    except Exception:                                    # noqa: BLE001
        return (lambda d: d.weekday() < 5), False


def dias_uteis_entre(inicio: date, fim: date, eh_util) -> int:
    """Dias úteis depois de `inicio`, até `fim` inclusive."""
    n, d = 0, inicio
    while d < fim:
        d += timedelta(days=1)
        if eh_util(d):
            n += 1
    return n


#: O prazo de cada Central em dias úteis contados do ato, quando a norma o dá
#: por ato. SIRC: art. 225 do Código de Normas — um dia útil.
PRAZO_EM_DIAS_UTEIS = {"SIRC": 1}


def regra_envio_fora_do_prazo(ctx: Contexto) -> list[dict]:
    """O envio registrado depois do prazo. A tarefa do gestor some quando o
    envio é registrado — e com ela a memória de que ele saiu atrasado. Numa
    correição a pergunta é exatamente essa."""
    con = ctx.con
    if not _tem_tabela(con, "ge_envios"):
        return []
    eh_util, com_feriados = _dia_util()
    atrasos: dict[str, list[str]] = {}
    for e in _linhas(con, "SELECT central, referencia, enviado_em FROM ge_envios "
                          "WHERE situacao='ENVIADO' ORDER BY id"):
        prazo = PRAZO_EM_DIAS_UTEIS.get(e["central"])
        partes = (e["referencia"] or "").split(":")
        if prazo is None or len(partes) < 3:
            continue
        ato, envio = _dt(partes[2]), _dt(e["enviado_em"])
        if not ato or not envio or partes[2] < CORTE:
            continue
        dias = dias_uteis_entre(ato.date(), envio.date(), eh_util)
        if dias > prazo:
            atrasos.setdefault(e["central"], []).append(
                f"{partes[0]}:{partes[1]} (ato {ato:%d/%m}, enviado {envio:%d/%m}: {dias} dias úteis)")
    return [_achado(
        f"PRAZO:{central}", "INFORMACOES", "ENVIO_FORA_DO_PRAZO", "ATENCAO",
        f"{len(lista)} envio(s) ao {central} feitos depois do prazo de "
        f"{PRAZO_EM_DIAS_UTEIS[central]} dia(s) útil(eis)",
        "; ".join(lista[:15]) + ("" if com_feriados else " — contado sem feriados"),
        evidencia="ge_envios.referencia (data do ato) × enviado_em",
        fundamento="Código de Normas TJMA, art. 225 (SIRC)",
        o_que_fazer="Já foi enviado; fica para o registro de correição e para "
                    "ajustar a rotina de quem envia.")
        for central, lista in atrasos.items()]


# ====================================================================== ATOS

def _abertos_do_gestor(con, regra: str) -> int:
    if not _tem_tabela(con, "ge_achados"):
        return 0
    return int(banco(con).valor(
        "SELECT count(*) AS n FROM ge_achados WHERE regra=%s AND resolvido_em IS NULL",
        (regra,)))


def _dupla(con, regra_do_gestor: str, achados_meus: list[dict], o_que: str) -> list[dict]:
    """A dupla medição: o que eu acho e o gestor não acha é achado sobre o
    gestor; o que ele acha e eu não confirmo vai como atenção."""
    dele = _abertos_do_gestor(con, regra_do_gestor)
    if achados_meus and dele == 0:
        for a in achados_meus:
            a["gravidade"] = "CRITICO"
            a["detalhe"] += f" — e o gestor NÃO acusa ({regra_do_gestor} sem achado aberto)."
        return achados_meus
    if achados_meus:
        return []          # os dois veem: a tarefa é do gestor, e já existe
    if dele:
        return [_achado(f"DUPLA:{regra_do_gestor}", "ATOS", "DUPLA_MEDICAO", "ATENCAO",
                        f"O gestor acusa {dele} achado(s) de {o_que} e a segunda medição não "
                        "confirma",
                        "Pode ser achado falso do gestor, ou um caso que esta medição não alcança.",
                        evidencia=f"ge_achados regra {regra_do_gestor}")]
    return []


def regra_numeracao(ctx: Contexto) -> list[dict]:
    con = ctx.con
    meus = []
    if _tem_tabela(con, "ri_atos"):
        for d in _linhas(con, """SELECT matricula_id, numero, count(*) AS n, max(lavrado_em) AS ult
                                   FROM ri_atos WHERE COALESCE(cancelado,0) = 0
                                  GROUP BY matricula_id, numero HAVING count(*) > 1
                                  ORDER BY matricula_id, numero"""):
            if (d["ult"] or "") >= CORTE:
                mat = banco(con).um("SELECT numero FROM ri_matriculas WHERE id=%s",
                                    (d["matricula_id"],))
                meus.append(_achado(
                    f"NUMERO:ri:{d['matricula_id']}:{d['numero']}", "ATOS", "NUMERO_REPETIDO",
                    "ATENCAO", f"Matrícula {mat['numero'] if mat else d['matricula_id']}: o ato nº "
                    f"{d['numero']} aparece {d['n']} vezes",
                    "Dois atos vivos com o mesmo número na mesma ficha",
                    evidencia="ri_atos agrupado por matrícula e número"))
    if _tem_tabela(con, "rc_assentos"):
        for d in _linhas(con, """SELECT serie, numero, count(*) AS n, max(data_ato) AS ult
                                   FROM rc_assentos
                                  WHERE COALESCE(situacao,'') NOT IN ('CANCELADO','CANCELADA')
                                    AND numero IS NOT NULL
                                  GROUP BY serie, numero HAVING count(*) > 1
                                  ORDER BY serie, numero"""):
            if (d["ult"] or "") >= CORTE:
                meus.append(_achado(
                    f"NUMERO:rc:{d['serie']}:{d['numero']}", "ATOS", "NUMERO_REPETIDO", "ATENCAO",
                    f"Registro Civil, série {d['serie']}: o termo {d['numero']} aparece "
                    f"{d['n']} vezes", "Dois assentos vivos com o mesmo número na mesma série",
                    evidencia="rc_assentos agrupado por série e número"))
    return _dupla(con, "NUMERACAO", meus, "numeração")


def regra_corrente_ri(ctx: Contexto) -> list[dict]:
    """Cada ato do RI aponta o hash do anterior DA MESMA MATRÍCULA (medido em
    09/10/2026: 839 de 839). Confere só o encadeamento — não recalcula o hash,
    e por isso não depende da função da casa que o calcula."""
    con = ctx.con
    if not _tem_tabela(con, "ri_atos"):
        return []
    anterior: dict[int, dict] = {}
    meus = []
    for a in _linhas(con, """SELECT id, matricula_id, numero, hash_ato, hash_anterior, lavrado_em
                               FROM ri_atos ORDER BY id"""):
        prev = anterior.get(a["matricula_id"])
        if prev and (a["lavrado_em"] or "") >= CORTE and prev.get("hash_ato") \
                and a["hash_anterior"] != prev["hash_ato"]:
            meus.append(_achado(
                f"CORRENTE:{a['id']}", "ATOS", "CORRENTE_RI", "ATENCAO",
                f"O ato {a['id']} (nº {a['numero']}) não aponta o hash do ato anterior da ficha",
                f"Anterior: ato {prev['id']}. Ato lavrado em {str(a['lavrado_em'])[:10]}.",
                evidencia="ri_atos.hash_anterior × hash_ato do anterior na matrícula"))
        anterior[a["matricula_id"]] = a
    return _dupla(con, "CORRENTE_RI", meus, "corrente de hash")


#: Onde cada tabela de ato escreve o selo. No razão (`sd_selos`) o número é
#: UNIQUE e o banco já impede o selo repetido; no ATO a coluna é texto livre —
#: o selo digitado à mão, a etiqueta colada —, e ali nada impede.
COLUNAS_DE_SELO = (
    ("ri_atos", "selo_texto"), ("rc_atos", "selo"), ("nt_atos", "selo"),
    ("rg_atos", "selo"), ("pt_atos", "selo"), ("ra_atos", "selo"),
    ("nt_reconhecimentos", "selo"), ("nt_autenticacoes", "selo"),
)
_CODIGO_DE_SELO = re.compile(r"\b[A-Z]{6}\d{6}[A-Z0-9]{16}\b")


def regra_selo_em_dois_atos(ctx: Contexto) -> list[dict]:
    """O mesmo selo em dois atos é a fraude que o selo existe para impedir —
    e o erro de digitação que faz parecer fraude. Dois casos, os dois dentro
    da MESMA tabela (o selo espelhado da habilitação no assento, ou do registro
    na 1ª certidão, cruza tabelas de propósito):

    - o código escrito em duas linhas da tabela;
    - o código escrito num ato e que o razão diz ser de OUTRO ato da tabela.

    A chave do ato é tabela + id: o id sozinho repete entre atribuições."""
    con = ctx.con
    razao: dict[str, tuple] = {}
    if _tem_tabela(con, "sd_selos"):
        for s in _linhas(con, "SELECT numero, tabela, ato_id FROM sd_selos WHERE ato_id IS NOT NULL "
                              "ORDER BY id"):
            razao[s["numero"]] = (s["tabela"], s["ato_id"])
    achados = []
    for tabela, coluna in COLUNAS_DE_SELO:
        if not _tem_tabela(con, tabela) or coluna not in _colunas(con, tabela):
            continue
        cols = _colunas(con, tabela)
        vivo = "AND COALESCE(cancelado,0)=0" if "cancelado" in cols else ""
        # O ACERVO DO E-OFÍCIO FICA DE FORA, como no gestor: medido em 09/10/2026,
        # quatro pares de títulos do protesto de 2025 trazem o mesmo selo da
        # carga — é o que o E-Ofício gravou, e não ato desta casa.
        data = next((c for c in ("lavrado_em", "data_ato", "criado_em") if c in cols), None)
        origem = "origem" if "origem" in cols else "NULL"
        acervo = "acervo" if "acervo" in cols else "0"
        donos: dict[str, set] = {}
        recentes: set = set()
        for a in _linhas(con, f"""SELECT id, {coluna} AS selo, {data or 'NULL'} AS quando,
                                         {origem} AS origem, {acervo} AS acervo FROM {tabela}
                                   WHERE COALESCE({coluna},'') <> '' {vivo}
                                   ORDER BY id"""):
            do_acervo = (a["origem"] in ORIGENS_DO_ACERVO or a["acervo"] == 1)
            for codigo in set(_CODIGO_DE_SELO.findall(str(a["selo"]).upper())):
                donos.setdefault(codigo, set()).add(a["id"])
                if not do_acervo and str(a["quando"] or "") >= CORTE:
                    recentes.add(codigo)
        for codigo, ids in donos.items():
            if codigo not in recentes:
                continue
            if len(ids) > 1:
                achados.append(_achado(
                    f"SELO_DOIS:{tabela}:{codigo}", "ATOS", "SELO_EM_DOIS_ATOS", "CRITICO",
                    f"O selo {codigo} está escrito em {len(ids)} atos de {tabela}",
                    "Atos " + ", ".join(str(i) for i in sorted(ids)),
                    evidencia=f"{tabela}.{coluna}"))
                continue
            dono = razao.get(codigo)
            (ato_id,) = ids
            if dono and dono[0] == tabela and dono[1] != ato_id:
                achados.append(_achado(
                    f"SELO_OUTRO:{tabela}:{codigo}", "ATOS", "SELO_EM_DOIS_ATOS", "CRITICO",
                    f"O selo {codigo} está escrito no ato {ato_id} de {tabela}, e o razão "
                    f"diz que ele é do ato {dono[1]}",
                    evidencia=f"{tabela}.{coluna} × sd_selos"))
    return achados


# ================================================================== a rodada

# =================================================================== O MALOTE
#
# Ordem do oficial em 11/10/2026, repassada pela sessão 12: «vamos integrar o
# verificador interno para revisar e cobrir falhas» do agente do malote
# (`malote_agente.py`, agente 13). Estas regras MEDEM DE NOVO, sem importar o
# agente — a mesma independência com que o compliance fiscaliza o gestor. O que
# elas cobrem é o que o agente pode deixar cair: o arquivo baixado que ninguém
# cadastrou, o expediente que a triagem não leu, e o anexo que não está onde o
# expediente diz (ou não é o mesmo arquivo).

#: O NOME da pasta do malote no Proton; o caminho até ela é desta casa e não se
#: escreve no código (relato #111): `settings.malote_pasta_proton`, ou achada.
NOME_DA_PASTA_DO_MALOTE = "6. MALOTE DIGITAL"
#: Papel que a casa produziu e guarda junto do expediente cumprido (etiqueta de
#: selo com o CNS da casa, certidão emitida) — não é recebido. Copiado do
#: agente, e não importado; o CNS vem de `settings`.
_CERTIDAO_DA_CASA = re.compile(r"^certid[aã]o-(rcpn|ri|rcpj|rtd|protesto)-\d+-\d{4}", re.I)


def _setting(con, chave: str) -> str:
    if not _tem_tabela(con, "settings"):
        return ""
    r = banco(con).um("SELECT value FROM settings WHERE key=%s", (chave,))
    return str((r["value"] if r else "") or "").strip()


def _pasta_do_malote_no_proton(con) -> Path | None:
    configurada = _setting(con, "malote_pasta_proton")
    if configurada:
        return Path(configurada)
    proton = Path.home() / "Proton Drive"
    if not proton.is_dir():
        return None
    achadas = sorted(proton.glob(f"*/Shared with me/*/{NOME_DA_PASTA_DO_MALOTE}")) \
        or sorted(proton.glob(f"*/{NOME_DA_PASTA_DO_MALOTE}"))
    return achadas[0] if achadas else None


def _e_papel_da_casa(nome: str, cns: str) -> bool:
    if _CERTIDAO_DA_CASA.search(nome):
        return True
    return bool(cns) and re.search(rf"\b[A-Z]{{6}}{re.escape(cns)}[A-Z0-9]{{10,16}}\b", nome) is not None
_ARQUIVOS_DE_SISTEMA = {".ds_store", "desktop.ini", "thumbs.db"}


def _pastas_de_entrada_do_malote(ctx: Contexto) -> list[Path]:
    pastas = []
    if ctx.pasta_dados:
        pastas.append(Path(ctx.pasta_dados) / "arquivos" / "malote" / "entrada")
    proton = ctx.pasta_malote if ctx.pasta_malote is not None else (
        _pasta_do_malote_no_proton(ctx.con) if ctx.pasta_dados else None)
    if proton is not None:
        pastas.append(Path(proton) / "PARA CADASTRAR")
    return [p for p in pastas if p.is_dir()]


def regra_malote_parado(ctx: Contexto) -> list[dict]:
    """Arquivo baixado do malote que não virou anexo de expediente depois de um
    dia útil. Medido em 11/10/2026: dois PDFs em «PARA CADASTRAR» desde 23/09 —
    um deles um divórcio para averbar no nascimento — sem expediente e sem
    tarefa. A chave é o sha256: o nome do arquivo pode mudar, o conteúdo não."""
    pastas = _pastas_de_entrada_do_malote(ctx)
    if not pastas:
        return []
    con = ctx.con
    no_sistema = set()
    if _tem_tabela(con, "attachments"):
        no_sistema = {r["sha256"] for r in _linhas(
            con, "SELECT sha256 FROM attachments WHERE entity_type='EXPEDIENTE'")}
    # O AVISO DE FRAUDE NÃO VIRA EXPEDIENTE (ordem do oficial de 13/10/2026):
    # lido pela IA e levado à lista de fraudes, ele está resolvido — e a prova é
    # a linha FRAUDE do agente do malote, pelo mesmo sha256.
    if _tem_tabela(con, "mt_arquivos"):
        no_sistema |= {r["sha256"] for r in _linhas(
            con, "SELECT sha256 FROM mt_arquivos WHERE situacao='FRAUDE'")}
    eh_util, com_feriados = _dia_util()
    corte = date.fromisoformat(CORTE)
    cns = "".join(ch for ch in (_setting(con, "serventia_cns") or _setting(con, "ri_cns")) if ch.isdigit())
    achados = []
    for pasta in pastas:
        for p in sorted(pasta.rglob("*")):
            if not p.is_file() or p.name.lower() in _ARQUIVOS_DE_SISTEMA or p.name.startswith("~$"):
                continue
            if _e_papel_da_casa(p.name, cns):
                continue
            chegou = date.fromtimestamp(p.stat().st_mtime)
            if chegou < corte:
                continue
            dias = dias_uteis_entre(chegou, ctx.hoje, eh_util)
            if dias < 1:
                continue
            sha = _hash_do_arquivo(p)
            if sha in no_sistema:
                continue
            achados.append(_achado(
                f"MALOTE_PARADO:{sha[:16]}", "AGENTES", "MALOTE_PARADO",
                "CRITICO" if dias >= 3 else "ATENCAO",
                f"Malote baixado e não cadastrado há {dias} dia(s) útil(eis): {p.name}",
                f"Na pasta «{p.parent}», desde {chegou:%d/%m/%Y}. Nenhum expediente tem "
                "este arquivo como anexo (conferido pelo sha256)."
                + ("" if com_feriados else " Conta feita sem o calendário de feriados."),
                evidencia=str(p),
                o_que_fazer="Rodar o agente do malote (MALOTE_CADASTRAR_AGORA) ou cadastrar o "
                            "expediente à mão; abrir o prazo pelo documento. Se for aviso de fraude "
                            "que a IA interna não conseguiu ler, ele fica aqui de propósito: rodar "
                            "de novo, ou incluir as pessoas à mão na tela de fraudes."))
    return achados


def regra_malote_sem_triagem(ctx: Contexto) -> list[dict]:
    """Expediente do malote, ainda RECEBIDO e sem tarefa, que a triagem não leu
    depois de um dia útil. A triagem roda às 07:30; o expediente que ela pula
    fica sem setor, sem prazo e sem dono — e nada mais o cobra."""
    con = ctx.con
    if not (_tem_tabela(con, "expedientes") and _tem_tabela(con, "tasks")):
        return []
    triados = set()
    erro_da_ia = ""
    if _tem_tabela(con, "ge_triagens"):
        triados = {r["expediente_id"] for r in _linhas(
            con, "SELECT DISTINCT expediente_id FROM ge_triagens WHERE erro IS NULL")}
        ultimo = _linhas(con, """SELECT erro, lido_em FROM ge_triagens WHERE erro IS NOT NULL
                                  ORDER BY id DESC LIMIT 1""")
        if ultimo:
            erro_da_ia = (f" Último erro da triagem ({ultimo[0]['lido_em']}): "
                          f"{(ultimo[0]['erro'] or '')[:200]}")
    eh_util, _ = _dia_util()
    achados = []
    for e in _linhas(con, """SELECT e.id, e.internal_protocol, e.subject, e.created_at
                               FROM expedientes e
                              WHERE e.source = 'Malote Digital' AND e.stage = 'RECEBIDO'
                                AND e.created_at >= %s
                                AND NOT EXISTS (SELECT 1 FROM tasks t
                                                 WHERE t.linked_expediente_id = e.id
                                                   AND t.status NOT IN ('CONCLUIDA','CANCELADA'))
                              ORDER BY e.id""", (CORTE,)):
        if e["id"] in triados:
            continue
        criado = _dt(e["created_at"])
        if not criado or dias_uteis_entre(criado.date(), ctx.hoje, eh_util) < 1:
            continue
        achados.append(_achado(
            f"MALOTE_SEM_TRIAGEM:{e['id']}", "AGENTES", "MALOTE_SEM_TRIAGEM", "ATENCAO",
            f"Expediente {e['internal_protocol']} do malote sem triagem e sem tarefa",
            f"«{(e['subject'] or '')[:150]}», cadastrado em {criado:%d/%m/%Y}." + erro_da_ia,
            evidencia=f"expedientes.id={e['id']}",
            o_que_fazer="Ler o expediente e abrir a tarefa, ou conferir por que a triagem não rodou."))
    return achados


def regra_malote_anexo_confere(ctx: Contexto) -> list[dict]:
    """O anexo do expediente do malote está onde a linha diz e é o mesmo
    arquivo (sha256). Segunda medição sobre o agente — que copia o PDF para
    `arquivos/Expedientes/...` — e sobre o cadastro à mão. Expediente do malote
    sem anexo nenhum também aparece: sem o PDF, ninguém cumpre."""
    con = ctx.con
    if not (_tem_tabela(con, "expedientes") and _tem_tabela(con, "attachments")):
        return []
    achados = []
    for e in _linhas(con, """SELECT e.id, e.internal_protocol,
                                    (SELECT count(*) FROM attachments a
                                      WHERE a.entity_type='EXPEDIENTE' AND a.entity_id=e.id) AS n
                               FROM expedientes e
                              WHERE e.source = 'Malote Digital' AND e.created_at >= %s
                              ORDER BY e.id""", (CORTE,)):
        if not e["n"]:
            achados.append(_achado(
                f"MALOTE_SEM_ANEXO:{e['id']}", "AGENTES", "MALOTE_ANEXO_CONFERE", "ATENCAO",
                f"Expediente {e['internal_protocol']} do malote sem nenhum anexo",
                "O documento recebido não está no sistema.", evidencia=f"expedientes.id={e['id']}",
                o_que_fazer="Anexar o PDF do malote ao expediente."))
            continue
        for a in _linhas(con, """SELECT id, original_name, stored_path, sha256 FROM attachments
                                  WHERE entity_type='EXPEDIENTE' AND entity_id=%s
                                  ORDER BY id""", (e["id"],)):
            caminho = Path(a["stored_path"] or "")
            if not caminho.is_file():
                problema = "o arquivo não está no disco"
            elif _hash_do_arquivo(caminho) != a["sha256"]:
                problema = "o arquivo do disco não é o que foi anexado (sha256 diferente)"
            else:
                continue
            achados.append(_achado(
                f"MALOTE_ANEXO:{a['id']}", "AGENTES", "MALOTE_ANEXO_CONFERE", "CRITICO",
                f"Anexo do expediente {e['internal_protocol']}: {problema}",
                f"«{a['original_name']}» em {caminho}", evidencia=f"attachments.id={a['id']}",
                o_que_fazer="Repor o arquivo a partir da cópia do malote (Proton) ou do backup."))
    return achados


REGRAS: tuple[tuple[str, Callable[[Contexto], list[dict]]], ...] = (
    ("AGENDADOR", regra_agendador),
    ("CAIXA_CADEIA", regra_cadeia_do_caixa),
    ("AUDITORIA_CADEIA", regra_cadeia_da_auditoria),
    ("LOG_DA_ROTINA", regra_log_das_rotinas),
    ("GESTOR_EXECUCAO", regra_execucoes_do_gestor),
    ("IA_SEM_RESULTADO", regra_ia_sem_resultado),
    ("CONFIG_DO_MODELO", regra_config_do_modelo),
    ("CONFIG_SEM_RASTRO", regra_config_sem_rastro),
    ("FECHOU_SEM_MEDIR", regra_fechou_sem_medir),
    ("FECHOU_E_REABRIU", regra_fechou_e_reabriu),
    ("COPIA_DIVERGENTE", regra_copia_divergente),
    ("AGENTE_MEXEU", regra_agente_mexeu),
    ("TRIAGEM_DUVIDOSA", regra_triagem_duvidosa),
    ("SERVIDOR", regra_servidor),
    ("COPIAS_DO_BANCO", regra_copias_do_banco),
    ("ENVIO_SEM_PROVA", regra_envio_sem_prova),
    ("QUANTOS_NAO_FECHA", regra_quantos_nao_fecha),
    ("ENVIO_FORA_DO_PRAZO", regra_envio_fora_do_prazo),
    ("NUMERO_REPETIDO", regra_numeracao),
    ("CORRENTE_RI", regra_corrente_ri),
    ("SELO_EM_DOIS_ATOS", regra_selo_em_dois_atos),
    ("MALOTE_PARADO", regra_malote_parado),
    ("MALOTE_SEM_TRIAGEM", regra_malote_sem_triagem),
    ("MALOTE_ANEXO_CONFERE", regra_malote_anexo_confere),
)

AREA_DA_REGRA = {
    "AGENDADOR": "AGENTES", "LOG_DA_ROTINA": "AGENTES", "GESTOR_EXECUCAO": "AGENTES",
    "IA_SEM_RESULTADO": "AGENTES", "CONFIG_DO_MODELO": "AGENTES",
    "CONFIG_SEM_RASTRO": "AGENTES", "FECHOU_SEM_MEDIR": "AGENTES",
    "FECHOU_E_REABRIU": "AGENTES", "COPIA_DIVERGENTE": "AGENTES", "AGENTE_MEXEU": "AGENTES",
    "TRIAGEM_DUVIDOSA": "AGENTES", "SERVIDOR": "AGENTES", "COPIAS_DO_BANCO": "AGENTES",
    "ENVIO_SEM_PROVA": "INFORMACOES", "QUANTOS_NAO_FECHA": "INFORMACOES",
    "ENVIO_FORA_DO_PRAZO": "INFORMACOES",
    "NUMERO_REPETIDO": "ATOS", "CORRENTE_RI": "ATOS", "SELO_EM_DOIS_ATOS": "ATOS",
    "MALOTE_PARADO": "AGENTES", "MALOTE_SEM_TRIAGEM": "AGENTES", "MALOTE_ANEXO_CONFERE": "AGENTES",
}

SCHEMA = (
    """CREATE TABLE IF NOT EXISTS cp_achados (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    chave TEXT NOT NULL UNIQUE,
    area TEXT NOT NULL,
    regra TEXT NOT NULL,
    gravidade TEXT NOT NULL,
    titulo TEXT NOT NULL,
    detalhe TEXT,
    evidencia TEXT,
    fundamento TEXT,
    o_que_fazer TEXT,
    primeiro_visto_em TEXT NOT NULL,
    ultimo_visto_em TEXT NOT NULL,
    resolvido_em TEXT
)""",
    "CREATE INDEX IF NOT EXISTS ix_cp_achados_abertos ON cp_achados (resolvido_em, area)",
    """CREATE TABLE IF NOT EXISTS cp_execucoes (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    iniciada_em TEXT NOT NULL,
    terminada_em TEXT,
    achados INTEGER,
    novos INTEGER,
    resolvidos INTEGER,
    criticos INTEGER,
    nao_mediu INTEGER,
    relatorio TEXT,
    tarefa_id bigint,
    erro TEXT
)""",
    """CREATE TABLE IF NOT EXISTS cp_fotografias (
    chave TEXT PRIMARY KEY,
    valor TEXT,
    tirada_em TEXT NOT NULL
)""",
    """CREATE TABLE IF NOT EXISTS cp_mudancas (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    chave TEXT NOT NULL,
    antes TEXT,
    depois TEXT,
    vista_em TEXT NOT NULL,
    com_rastro INTEGER NOT NULL DEFAULT 0,
    UNIQUE (chave, vista_em)
)""",
)


def init_schema(con: sqlite3.Connection) -> None:
    bd = banco(con)
    for comando in SCHEMA:
        bd.escrever(comando)


def conferir(ctx: Contexto) -> list[dict]:
    """Roda as regras. A que quebra vira NAO_MEDIU com o erro à vista."""
    achados = []
    for nome, regra in REGRAS:
        try:
            achados.extend(regra(ctx))
        except Exception as erro:                        # noqa: BLE001 — vai ao relatório
            achados.append(_achado(
                f"NAO_MEDIU:{nome}", AREA_DA_REGRA.get(nome, "AGENTES"), nome, "NAO_MEDIU",
                f"O compliance não conseguiu medir «{nome}»",
                f"{type(erro).__name__}: {str(erro)[:300]}"))
    return achados


def gravar(con: sqlite3.Connection, achados: list[dict], agora: str) -> dict:
    bd = banco(con)
    vistos, novos = set(), 0
    for a in achados:
        vistos.add(a["chave"])
        r = bd.um("SELECT id FROM cp_achados WHERE chave=%s", (a["chave"],))
        campos = (a["area"], a["regra"], a["gravidade"], a["titulo"], a["detalhe"],
                  a["evidencia"], a["fundamento"], a["o_que_fazer"])
        if r is None:
            novos += 1
            bd.escrever(
                """INSERT INTO cp_achados (area, regra, gravidade, titulo, detalhe, evidencia,
                       fundamento, o_que_fazer, chave, primeiro_visto_em, ultimo_visto_em)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", (*campos, a["chave"], agora, agora))
        else:
            bd.escrever(
                """UPDATE cp_achados SET area=%s, regra=%s, gravidade=%s, titulo=%s, detalhe=%s,
                       evidencia=%s, fundamento=%s, o_que_fazer=%s, ultimo_visto_em=%s,
                       resolvido_em=NULL WHERE id=%s""", (*campos, agora, r["id"]))
    # A REGRA QUE NÃO MEDIU NÃO RESOLVE NADA DELA: é o defeito que este módulo
    # acusa no gestor, e o fiscal não pode cometê-lo.
    sem_medida = {a["regra"] for a in achados if a["gravidade"] == "NAO_MEDIU"}
    resolvidos = 0
    for r in _linhas(con, "SELECT id, chave, regra FROM cp_achados WHERE resolvido_em IS NULL "
                          "ORDER BY id"):
        if r["chave"] not in vistos and r["regra"] not in sem_medida:
            resolvidos += 1
            bd.escrever("UPDATE cp_achados SET resolvido_em=%s WHERE id=%s", (agora, r["id"]))
    return {"novos": novos, "resolvidos": resolvidos}


def _dono(con) -> int | None:
    """O oficial: o titular da Gestão na distribuição do gestor, senão o
    primeiro ADMIN ativo que não é robô."""
    bd = banco(con)
    if _tem_tabela(con, "ge_responsaveis"):
        r = bd.um("SELECT user_id FROM ge_responsaveis WHERE setor='GESTAO' ORDER BY setor LIMIT 1")
        if r:
            return int(r["user_id"])
    cols = _colunas(con, "users")
    robo = "AND COALESCE(eh_robo,0)=0" if "eh_robo" in cols else ""
    r = bd.um(f"SELECT id FROM users WHERE role='ADMIN' AND active=1 {robo} "
              "ORDER BY id LIMIT 1")
    return int(r["id"]) if r else None


def publicar_tarefa(con: sqlite3.Connection, hoje: date, abertos: list[dict]) -> int | None:
    """UMA tarefa por dia ao oficial, e só quando há ponto crítico. A de ontem
    fecha: relatório velho aberto é pilha. Sem crítico, não há tarefa — a ordem
    de 06/10 é não abrir tarefa por controle interno."""
    agora = datetime.now().isoformat(timespec="seconds")
    ref = f"{SOURCE_TYPE}:{hoje.isoformat()}"
    criticos = [a for a in abertos if a["gravidade"] in ("CRITICO", "NAO_MEDIU")]
    bd = banco(con)
    for velha in _linhas(con, """SELECT id, status FROM tasks WHERE source_type=%s AND
                                    status NOT IN ('CONCLUIDA','CANCELADA')
                                    AND (source_ref <> %s OR %s = 0)
                                  ORDER BY id""",
                         (SOURCE_TYPE, ref, len(criticos))):
        bd.escrever("UPDATE tasks SET status='CONCLUIDA', completed_at=%s, updated_at=%s WHERE id=%s",
                    (agora, agora, velha["id"]))
        bd.escrever("""INSERT INTO task_history (task_id, ts, user_id, action, old_value,
                           new_value, note) VALUES (%s,%s,NULL,'ALTEROU_STATUS',%s,'CONCLUIDA',%s)""",
                    (velha["id"], agora, velha["status"],
                     "Substituída pelo relatório de compliance de hoje." if criticos else
                     "O compliance não encontra mais ponto crítico."))
    if not criticos:
        return None
    dono = _dono(con)
    if dono is None:
        return None
    linhas = [f"Relatório do agente de compliance — {hoje:%d/%m/%Y}", "",
              "O compliance fiscaliza os outros agentes e o que a casa informa. "
              "Ele não conserta nada: diz o que achou e como conferir.", ""]
    for a in criticos:
        linhas.append(f"[{a['gravidade']}] {a['titulo']}")
        if a.get("detalhe"):
            linhas.append(f"    {a['detalhe'][:400]}")
        if a.get("o_que_fazer"):
            linhas.append(f"    O que fazer: {a['o_que_fazer']}")
        linhas.append("")
    linhas.append("O relatório completo, com os pontos de atenção, está em "
                  "FERRAMENTAS\\COMPLIANCE\\relatorios.")
    texto = "\n".join(linhas)
    titulo = f"[Compliance] {len(criticos)} ponto(s) crítico(s) — {hoje:%d/%m/%Y}"
    atual = bd.um("SELECT id FROM tasks WHERE source_type=%s AND source_ref=%s ORDER BY id LIMIT 1",
                  (SOURCE_TYPE, ref))
    if atual:
        bd.escrever("""UPDATE tasks SET title=%s, description=%s, status='ABERTA',
                           completed_at=NULL, updated_at=%s WHERE id=%s""",
                    (titulo, texto, agora, atual["id"]))
        return int(atual["id"])
    tarefa_id = bd.escrever(
        """INSERT INTO tasks (source_type, source_ref, title, description, sector, system_name,
               priority, status, start_date, due_date, assigned_user_id, evidence_required,
               created_at, updated_at)
           VALUES (%s,%s,%s,%s,'Gestão','Agente de compliance','ALTA','ABERTA',%s,%s,%s,0,%s,%s)
           RETURNING id""",
        (SOURCE_TYPE, ref, titulo, texto, hoje.isoformat(), hoje.isoformat(), dono, agora, agora))[0]["id"]
    bd.escrever("""INSERT INTO task_history (task_id, ts, user_id, action, note)
                   VALUES (%s,%s,NULL,'CRIADA','Relatório do dia, pelo agente de compliance.')""",
                (tarefa_id, agora))
    return int(tarefa_id)


def relatorio_html(con: sqlite3.Connection, agora: datetime, resumo: dict) -> str:
    e = html.escape
    abertos = _linhas(con, "SELECT * FROM cp_achados WHERE resolvido_em IS NULL ORDER BY id")
    ordem = {g: i for i, g in enumerate(GRAVIDADES)}
    abertos.sort(key=lambda a: (list(AREAS).index(a["area"]) if a["area"] in AREAS else 9,
                                ordem.get(a["gravidade"], 9), a["regra"], a["chave"]))
    hoje = agora.date().isoformat()
    resolvidos = _linhas(con, "SELECT titulo FROM cp_achados WHERE resolvido_em ILIKE %s "
                              "ORDER BY id", (hoje + "%",))
    blocos = []
    for area, nome in AREAS.items():
        itens = [a for a in abertos if a["area"] == area]
        if not itens:
            blocos.append(f"<h2>{e(nome)}</h2><p class='ok'>Nada a apontar.</p>")
            continue
        linhas = "".join(
            f"<tr class='g-{a['gravidade'].lower()}'><td>{e(a['gravidade'])}</td>"
            f"<td><b>{e(a['titulo'])}</b>"
            f"{'<br><small>' + e(a['detalhe']) + '</small>' if a['detalhe'] else ''}"
            f"{'<br><small><i>O que fazer:</i> ' + e(a['o_que_fazer']) + '</small>' if a['o_que_fazer'] else ''}"
            f"</td><td><small>{e(a['evidencia'] or '')}</small>"
            f"{'<br><small>' + e(a['fundamento']) + '</small>' if a['fundamento'] else ''}</td>"
            f"<td><small>{e(str(a['primeiro_visto_em'])[:10])}</small></td></tr>"
            for a in itens)
        blocos.append(f"<h2>{e(nome)} ({len(itens)})</h2><table><tr><th>Gravidade</th>"
                      f"<th>Achado</th><th>Como se mediu</th><th>Desde</th></tr>{linhas}</table>")
    nao = "".join(f"<li>{e(x)}</li>" for x in NAO_MEDE)
    feitos = "".join(f"<li>{e(r['titulo'])}</li>" for r in resolvidos) or "<li>nenhum</li>"
    placar = Counter(a["gravidade"] for a in abertos)
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Compliance {agora:%d/%m/%Y}</title><style>
:root{{--fg:#1d1d1f;--bg:#fff;--linha:#ddd;--fraco:#555;--crit:#b00020;--aten:#8a5300;--ok:#1b6e20}}
@media (prefers-color-scheme:dark){{:root{{--fg:#eee;--bg:#161616;--linha:#333;--fraco:#aaa;--crit:#ff6b7f;--aten:#f0b35a;--ok:#7bd17f}}}}
body{{font:14px system-ui,sans-serif;margin:16px;color:var(--fg);background:var(--bg);max-width:1100px}}
table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid var(--linha);padding:6px;vertical-align:top;text-align:left}}
small{{color:var(--fraco)}}.g-critico td:first-child,.g-nao_mediu td:first-child{{color:var(--crit);font-weight:700}}
.g-atencao td:first-child{{color:var(--aten);font-weight:700}}.ok{{color:var(--ok)}}
</style></head><body>
<h1>Compliance da casa — {agora:%d/%m/%Y %H:%M}</h1>
<p><b>{len(abertos)}</b> ponto(s) em aberto — crítico: {placar.get('CRITICO', 0)} ·
não mediu: {placar.get('NAO_MEDIU', 0)} · atenção: {placar.get('ATENCAO', 0)}.
Novos nesta rodada: {resumo.get('novos', 0)}. Resolvidos: {resumo.get('resolvidos', 0)}.</p>
<p><small>O agente de compliance fiscaliza os outros agentes (o gestor, a IA, as rotinas do
Agendador, os agentes de carga) e confere de novo, pelo próprio caminho, o que a casa pratica e
informa. Ele não conserta nada e não usa a régua de quem fiscaliza. Onde a medição dele e a do
gestor divergem, o achado é sobre o gestor.</small></p>
{''.join(blocos)}
<h2>Resolvidos hoje</h2><ul>{feitos}</ul>
<h2>O que o compliance ainda não mede</h2><ul>{nao}</ul>
</body></html>"""


def rodar(con: sqlite3.Connection, ctx: Contexto, pasta_relatorio: Path | None = None) -> dict:
    bd = banco(con)
    init_schema(con)
    agora = ctx.agora.isoformat(timespec="seconds")
    exe = bd.escrever("INSERT INTO cp_execucoes (iniciada_em) VALUES (%s) RETURNING id",
                      (agora,))[0]["id"]
    con.commit()
    try:
        achados = conferir(ctx)
        resumo = gravar(con, achados, agora)
        abertos = _linhas(con, "SELECT * FROM cp_achados WHERE resolvido_em IS NULL ORDER BY id")
        resumo["achados"] = len(achados)
        resumo["criticos"] = sum(a["gravidade"] == "CRITICO" for a in achados)
        resumo["nao_mediu"] = sum(a["gravidade"] == "NAO_MEDIU" for a in achados)
        resumo["tarefa"] = publicar_tarefa(con, ctx.hoje, abertos)
        caminho = None
        if pasta_relatorio is not None:
            pasta_relatorio.mkdir(parents=True, exist_ok=True)
            caminho = pasta_relatorio / f"compliance_{ctx.hoje.isoformat()}.html"
            caminho.write_text(relatorio_html(con, ctx.agora, resumo), encoding="utf-8")
        resumo["relatorio"] = str(caminho) if caminho else None
        bd.escrever(
            """UPDATE cp_execucoes SET terminada_em=%s, achados=%s, novos=%s, resolvidos=%s,
                   criticos=%s, nao_mediu=%s, relatorio=%s, tarefa_id=%s WHERE id=%s""",
            (datetime.now().isoformat(timespec="seconds"), resumo["achados"], resumo["novos"],
             resumo["resolvidos"], resumo["criticos"], resumo["nao_mediu"],
             resumo["relatorio"], resumo["tarefa"], exe))
        con.commit()
        return resumo
    except Exception as erro:
        con.rollback()
        bd.escrever("UPDATE cp_execucoes SET terminada_em=%s, erro=%s WHERE id=%s",
                    (datetime.now().isoformat(timespec="seconds"),
                     f"{type(erro).__name__}: {erro}", exe))
        con.commit()
        raise
