"""A rodada do backup automático — uma implementação só, para a automação e para o primeiro acesso do dia.

POR QUE ISTO SAIU DE DENTRO DO `app.py` (26/10/2026)
    O backup automático (o diário do banco, o completo semanal e a retenção)
    morava em `automatic_backup_once`, aninhada no `create_app`, e só rodava
    **na primeira requisição** que o servidor atendia: se ninguém abrisse o
    sistema, o backup não saía. E pior do que o levantamento dizia — a marca
    `backup_checked` não era do DIA, era do PROCESSO: com o servidor de pé três
    dias seguidos, só o primeiro dia tinha backup. A falha virava uma linha
    `AUTO_BACKUP_FAILURE` na auditoria, que ninguém lê de manhã.

    O Provimento CN/CNJ 213/2026 pede a cópia na periodicidade da classe (art.
    12, § 3º, I) e o alerta ao responsável quando ela falha (§ 10). Por isso o
    backup passou a ser um PROCESSO da central de automação
    (`backup_automacao.rodar_backup`), que roda no horário pelo Agendador — e
    que avisa no painel, na tarefa e no e-mail quando termina em AVISO ou ERRO,
    pelo canal que a automação já tem.

    O primeiro acesso do dia FICA, como reserva: se a automação estiver
    desligada (ela nasce desligada) ou a máquina tiver passado a madrugada
    desligada, o backup ainda sai. As duas portas chamam ESTA `rodada`: duas
    implementações divergiriam no primeiro conserto, e a divergência seria
    descoberta no dia da restauração.

SEM PACOTE REPETIDO NO MESMO DIA, E SEM DOIS AO MESMO TEMPO
    - o diário se reconhece pelo NOME (`backup_banco_<data>.zip`): quem chega
      depois e o acha pronto não gera outro;
    - o completo se reconhece pelo DIA AGENDADO: ele é devido quando o último
      completo é anterior ao dia da semana configurado mais recente. Isso pega
      o completo perdido (máquina desligada no domingo → sai na segunda) sem
      empurrar a agenda para a frente;
    - a TRAVA (`backup_rodada.trava`, na pasta dos backups) impede que a
      automação e o primeiro acesso gerem o mesmo pacote juntos. Trava com mais
      de `TRAVA_VENCIDA_H` horas é de uma rodada que morreu, e se retoma.

A CÓPIA IMUTÁVEL FORA DA CASA NÃO ESTÁ AQUI — DE PROPÓSITO, E O LUGAR ESTÁ MARCADO
    O espelho fora do servidor (e imutável) é exigência do mesmo provimento, e
    o oficial ainda vai escolher o armazenamento (26/10/2026). Ela entra no
    ponto marcado «A CÓPIA IMUTÁVEL FORA DA CASA» em `rodada`, depois de o
    pacote passar na conferência — e só do pacote conferido. Nenhum serviço foi
    escolhido nem escrito aqui: inventar um seria pior que declarar a falta.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from collections.abc import Callable, Iterator

import backup as BKP

NOME_DA_TRAVA = "backup_rodada.trava"
TRAVA_VENCIDA_H = 6

PADRAO_DIARIO = "backup_banco_*.zip"
PADRAO_COMPLETO = "backup_completo_*.zip"
PADRAO_ANTIGO = "backup_automatico_*.zip"


class RodadaOcupada(RuntimeError):
    """Outra rodada do backup está gerando pacote agora (a trava existe)."""


# ------------------------------------------------------------- o que a casa configurou


def parametros_da_casa(ler: Callable[[str, str], str]) -> dict:
    """As escolhas da tela de configurações, lidas por `ler(chave, padrao)`.

    `ler` é o `db.get_setting` do servidor ou o `Contexto.setting` da
    automação: as duas portas leem as MESMAS chaves com os MESMOS padrões.
    """
    def inteiro(chave: str, padrao: int) -> int:
        try:
            return int(str(ler(chave, str(padrao)) or padrao).strip())
        except (TypeError, ValueError):
            return padrao
    dia = inteiro("backup_completo_dia", 6)
    return {
        "completo_dia": dia if 0 <= dia <= 6 else 6,
        "retencao_banco": max(3, inteiro("backup_retention", 30)),
        "retencao_completo": max(2, inteiro("backup_completo_retencao", 8)),
    }


# ------------------------------------------------------------- os pacotes que já existem


def pacote_diario(pasta: Path, hoje: date) -> Path:
    return Path(pasta) / f"backup_banco_{hoje.isoformat()}.zip"


def pacote_completo(pasta: Path, hoje: date) -> Path:
    return Path(pasta) / f"backup_completo_{hoje.isoformat()}.zip"


def _dia_do_arquivo(p: Path) -> date:
    return datetime.fromtimestamp(p.stat().st_mtime).date()


def ultimo_completo(pasta: Path) -> date | None:
    datas = [_dia_do_arquivo(p) for p in Path(pasta).glob(PADRAO_COMPLETO)]
    return max(datas) if datas else None


def ultimo_dia_agendado(hoje: date, dia_da_semana: int) -> date:
    """O dia mais recente (hoje inclusive) que cai no dia da semana configurado."""
    return hoje - timedelta(days=(hoje.weekday() - dia_da_semana) % 7)


def completo_devido(pasta: Path, hoje: date, dia_da_semana: int) -> bool:
    """O completo é devido quando o último é anterior ao último dia agendado.

    É a regra de antes («no dia configurado, se não houver um dos últimos seis
    dias») com o conserto do dia perdido: se o domingo passou sem completo, a
    segunda o faz — e o domingo seguinte volta a ser o dia dele.
    """
    ultimo = ultimo_completo(pasta)
    return ultimo is None or ultimo < ultimo_dia_agendado(hoje, dia_da_semana)


def ultimo_pacote(pasta: Path, padroes: tuple[str, ...] = (PADRAO_DIARIO, PADRAO_COMPLETO)) -> Path | None:
    """O pacote automático mais novo da pasta (pela data de gravação), ou None."""
    achados = [p for padrao in padroes for p in Path(pasta).glob(padrao) if p.is_file()]
    return max(achados, key=lambda p: p.stat().st_mtime) if achados else None


# ------------------------------------------------------------- a trava


@contextmanager
def trava(pasta: Path, agora: datetime | None = None) -> Iterator[Path]:
    """Uma rodada por vez na pasta dos backups. Levanta `RodadaOcupada`.

    A trava é um arquivo criado com O_EXCL — funciona entre o servidor web e o
    despachante, que são processos diferentes. A que envelheceu mais de
    `TRAVA_VENCIDA_H` horas é de uma rodada que morreu no meio (o corredor da
    automação mata o trabalho que passa do prazo), e se retoma.
    """
    agora = agora or datetime.now()
    caminho = Path(pasta) / NOME_DA_TRAVA
    for tentativa in (1, 2):
        try:
            fd = os.open(caminho, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                idade_h = (agora.timestamp() - caminho.stat().st_mtime) / 3600
            except OSError:
                idade_h = 0.0
            if tentativa == 1 and idade_h > TRAVA_VENCIDA_H:
                caminho.unlink(missing_ok=True)
                continue
            raise RodadaOcupada(
                f"outra rodada do backup está gerando pacote agora (trava de "
                f"{idade_h:.1f} h em {caminho.name})") from None
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(f"pid={os.getpid()} desde={agora.isoformat(timespec='seconds')}\n")
        break
    try:
        yield caminho
    finally:
        caminho.unlink(missing_ok=True)


# ------------------------------------------------------------- a rodada


def _expurgar(pasta: Path, padrao: str, manter: int) -> list[str]:
    achados = sorted(Path(pasta).glob(padrao), key=lambda p: p.stat().st_mtime, reverse=True)
    apagados = []
    for velho in achados[max(1, manter):]:
        velho.unlink(missing_ok=True)
        apagados.append(velho.name)
    return apagados


def _descrever(p: Path, tipo: str) -> dict:
    return {"tipo": tipo, "arquivo": p.name, "bytes": p.stat().st_size,
            "sha256": BKP._sha256(p), "cifrado": BKP.e_cifrado(p)}


def rodada(pasta: Path, gerar: Callable[[Path, bool], Path], *, hoje: date,
           completo_dia: int, retencao_banco: int, retencao_completo: int,
           agora: datetime | None = None) -> dict:
    """O diário do banco (se ainda não saiu hoje), o completo (se devido) e a retenção.

    `gerar(destino, com_arquivos)` é quem monta o pacote — sempre
    `backup.gerar_pacote`, com as opções da casa. Devolve o que foi feito:
    `feitos` (com nome, tamanho e SHA-256), `ja_existiam`, `falhas` (com a
    mensagem) e `expurgados`. Levanta `RodadaOcupada` se outra rodada estiver
    gerando pacote; **falha de um pacote não impede o outro**.
    """
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    saida: dict = {"feitos": [], "ja_existiam": [], "falhas": [], "expurgados": [], "avisos": []}
    with trava(pasta, agora):
        pedidos = [("banco", pacote_diario(pasta, hoje), False, pacote_diario(pasta, hoje).exists())]
        if completo_devido(pasta, hoje, completo_dia):
            pedidos.append(("completo", pacote_completo(pasta, hoje), True, False))
        for tipo, destino, com_arquivos, ja_existe in pedidos:
            if ja_existe:
                saida["ja_existiam"].append({"tipo": tipo, "arquivo": destino.name})
                continue
            try:
                gerar(destino, com_arquivos)
            except Exception as erro:          # noqa: BLE001 — vira falha com a frase
                saida["falhas"].append({"tipo": tipo, "arquivo": destino.name,
                                        "erro": f"{type(erro).__name__}: {erro}"[:600]})
                continue
            saida["feitos"].append(_descrever(destino, tipo))
            # ── A CÓPIA IMUTÁVEL FORA DA CASA ───────────────────────────────
            # É aqui que ela entra, quando o oficial escolher o armazenamento:
            # depois de o pacote passar na conferência (`gerar_pacote` só dá o
            # nome definitivo ao pacote conferido), e só deste pacote. A falha
            # dela vira item de `falhas`, para a automação avisar. NÃO HÁ
            # SERVIÇO ESCOLHIDO (26/10/2026) — nada foi escrito no lugar dele.
        try:
            saida["expurgados"] += _expurgar(pasta, PADRAO_DIARIO, retencao_banco)
            saida["expurgados"] += _expurgar(pasta, PADRAO_COMPLETO, retencao_completo)
            # Formato antigo: um único arquivo com tudo. Some por retenção.
            saida["expurgados"] += _expurgar(pasta, PADRAO_ANTIGO, 2)
        except OSError as erro:
            # A retenção que não apagou não estraga o backup de hoje; vira aviso,
            # porque o disco vai enchendo calado.
            saida["avisos"].append(f"a retenção não apagou os pacotes antigos: {erro}"[:300])
    return saida
