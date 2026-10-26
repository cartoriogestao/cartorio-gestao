"""O BACKUP NA CENTRAL DA AUTOMAÇÃO — o pacote no horário, e a prova de que ele volta.

O CONTRATO (o do `automacao_processos`, ramo `automacao-hub`)
    def rodar(contexto) -> {"situacao": "OK"|"AVISO"|"ERRO", "relato": str,
                            "achados": [...], "acoes": [...]}
    O contexto traz `db`, `agora`, `pasta_dados`, `raiz` e `processo`.

OS DOIS PROCESSOS (26/10/2026 — Provimento CN/CNJ 213/2026, art. 12, § 3º, I, e § 10)
    BACKUP_DIARIO             — a rodada do backup (`backup_rotina.rodada`): o
                                pacote do banco do dia, o completo quando devido
                                e a retenção. Roda no horário pelo Agendador, e
                                por isso **não depende de alguém abrir o sistema**.
                                O horário de fábrica é **18h** (decisão do
                                oficial, 26/10/2026: «roda 18h»); a retenção é
                                de 5 dias e nunca apaga o completo-base
                                (`backup_rotina.aplicar_retencao`).
    BACKUP_TESTE_RESTAURACAO  — restaura o pacote mais novo num banco
                                DESCARTÁVEL, confere as contagens contra o
                                manifesto e apaga (`backup_restauracao`). Grava
                                cada rodada em `bk_restauracoes`, para a correição.

    Os dois nascem DESLIGADOS, como todo processo da central: quem liga é o
    oficial, em Automação. São `rodar_*` (como a conferência diária e o envio da
    CENSEC): ligados, eles AGEM — fazer backup é o próprio serviço deles, e o
    «pode agir» não se aplica.

O ALERTA É O DA AUTOMAÇÃO, E NÃO OUTRO
    Terminou em AVISO ou ERRO, a central avisa no painel, abre a tarefa do
    responsável e manda o e-mail (`automacao_avisos`) — e lembra enquanto o
    problema seguir. Este arquivo não manda nada: ele só diz a verdade no
    resultado. Um segundo canal seria um segundo lugar para alguém esquecer de
    configurar.

O PRIMEIRO ACESSO DO DIA CONTINUA COMO RESERVA
    `app.automatic_backup_once` chama a mesma `backup_rotina.rodada`: o pacote
    que este processo já gerou hoje não se repete, e a trava impede os dois ao
    mesmo tempo. A configuração «backup automático» da tela governa só a
    reserva; ligar este processo é a decisão de ter o backup no horário.

A CÓPIA IMUTÁVEL FORA DA CASA
    Não está aqui: o oficial ainda vai escolher o armazenamento. O lugar dela
    está marcado em `backup_rotina.rodada` («A CÓPIA IMUTÁVEL FORA DA CASA»).

PELA LINHA DE COMANDO (para o técnico conferir sem esperar a agenda)
    python backup_automacao.py --testar-restauracao [pacote.zip]
    python backup_automacao.py --historico
    Lê `CARTORIO_GESTAO_DATA`, `CG_PG_DSN` e `CG_PG_BIN`, como o despachante.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import backup as BKP
import backup_restauracao as REST
import backup_rotina as ROT

_TODOS = [0, 1, 2, 3, 4, 5, 6]

# ------------------------------------------------------------- o que os dois precisam


def _pasta_dos_backups(ctx) -> Path:
    import pasta_das_copias
    return pasta_das_copias.pasta_de_backups(Path(ctx.pasta_dados), ctx.setting("backup_dir", ""))


def _versao(ctx) -> str:
    try:
        return (Path(ctx.raiz) / "VERSAO.txt").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _resultado(situacao: str, relato: str, achados: Any = (), acoes: Any = (), **extra) -> dict:
    return {"situacao": situacao, "relato": relato[:3500], "achados": list(achados),
            "acoes": list(acoes), **extra}


def _mb(n: Any) -> str:
    return f"{(int(n or 0)) / 1024 ** 2:,.1f} MB".replace(",", "X").replace(".", ",").replace("X", ".")


# ------------------------------------------------------------- o backup


def registrar_os_feitos(db, feitos: list[dict], *, origem: str, agora: datetime,
                         pasta: Path) -> str:
    """Grava os pacotes gerados em `bk_pacotes` e na auditoria. Devolve o aviso, ou ``""``.

    As DUAS portas da rodada chamam isto (a automação e o primeiro acesso do
    dia, em `app.automatic_backup_once`): pacote que só uma delas registrasse
    seria recusado pelo teste de restauração conforme quem o gerou.
    """
    if not feitos:
        return ""
    try:
        REST.registrar_pacotes_gerados(db, feitos, origem=origem, agora=agora)
    except Exception as erro:                  # noqa: BLE001 — vira aviso com a frase
        return (f"o pacote saiu, mas o registro do SHA-256 dele falhou ({type(erro).__name__}: "
                f"{erro}) — o teste de restauração vai recusá-lo")[:400]
    for f in feitos:
        try:
            db.log(None, "SISTEMA",
                   "AUTO_BACKUP_COMPLETO" if f["tipo"] == "completo" else "AUTO_BACKUP_BANCO",
                   "BACKUP", None,
                   {"path": str(Path(pasta) / f["arquivo"]), "bytes": f["bytes"],
                    "sha256": f["sha256"], "cifrado": f["cifrado"], "origem": origem})
        except Exception:                      # noqa: BLE001 — a auditoria não derruba o backup
            pass
    return ""


#: Quem age em cada porta da rodada, para a auditoria (regra da casa de
#: 26/10/2026: toda gravação sem usuário diz o agente e a mando de quem).
AGENTE_DA_PORTA = {
    "automação": "processo BACKUP_DIARIO da central de automação (backup_automacao.rodar_backup)",
    "primeiro acesso do dia": "reserva do primeiro acesso do dia (app.automatic_backup_once)",
}


def registrar_a_retencao(db, retencao: dict | None, *, origem: str, pasta: Path) -> None:
    """Grava na auditoria o que a retenção apagou (e o que ficou de fora dela).

    Uma linha `AUTO_BACKUP_RETENCAO` por rodada que apagou alguma coisa, ou
    que deixou pacote velho por falta de registro, ou que não conseguiu
    apagar. `db.log` não tem campo próprio de agente: `agente` e `a_mando_de`
    vão no detalhe. A auditoria nunca derruba o backup.
    """
    if not retencao or not (retencao.get("apagados") or retencao.get("sem_registro")
                            or retencao.get("falhas")):
        return
    fora_da_janela = {a: m for a, m in (retencao.get("mantidos") or {}).items()
                      if not m.startswith("dos últimos")}
    try:
        db.log(None, "SISTEMA", "AUTO_BACKUP_RETENCAO", "BACKUP", None,
               {"pasta": str(pasta), "dias": retencao.get("dias"),
                "apagados": retencao.get("apagados") or [],
                "mantidos_fora_da_janela": fora_da_janela,
                "sem_registro_nao_apagados": retencao.get("sem_registro") or [],
                "falhas": retencao.get("falhas") or [], "origem": origem,
                "agente": AGENTE_DA_PORTA.get(origem, origem),
                "a_mando_de": ("oficial — retenção local de "
                               f"{retencao.get('dias')} dias decidida em 26/10/2026 "
                               "(Configurações → backup_retencao_dias)")})
    except Exception:                          # noqa: BLE001 — a auditoria não derruba o backup
        pass


def rodar_backup(ctx) -> dict:
    """A rodada do backup, no horário. ESCREVE na pasta dos backups."""
    pasta_dados = Path(ctx.pasta_dados)
    pasta = _pasta_dos_backups(ctx)
    raiz_dos_arquivos = (Path(ctx.setting("archive_root", "").strip()).expanduser()
                         if ctx.setting("archive_root", "").strip() else pasta_dados / "arquivos")
    sem_acervo = ctx.setting("backup_completo_sem_acervo", "0") == "1"
    acervo = None if sem_acervo else pasta_dados / "acervo_eoficio.sqlite3"
    cifra = BKP.situacao_da_cifra(pasta_dados)
    senha = (BKP.senha_da_cifra(pasta_dados) or None) if cifra == "ligada" else None
    versao = _versao(ctx)

    def gerar(destino: Path, com_arquivos: bool) -> Path:
        # O MESMO `gerar_pacote` da tela e do `full_backup` do servidor, com as
        # mesmas opções da casa (cifra do cofre, acervo no completo).
        return BKP.gerar_pacote(ctx.db, destino, raiz_dos_arquivos, com_arquivos=com_arquivos,
                                versao=versao, acervo=acervo, senha_da_cifra=senha)

    try:
        r = ROT.rodada(pasta, gerar, hoje=ctx.hoje, agora=ctx.agora,
                       registrados=REST.nomes_registrados(ctx.db),
                       **ROT.parametros_da_casa(ctx.setting))
    except ROT.RodadaOcupada as erro:
        return _resultado("AVISO", f"O backup não rodou agora: {erro}. A próxima rodada tenta de novo.",
                          [{"pasta": str(pasta)}])

    # O PACOTE GERADO FICA REGISTRADO, COM O SHA-256 (26/10/2026, PR #27 M1): é
    # a lista que o teste de restauração confere antes de rodar o pg_restore —
    # pacote que não está nela não se restaura. E vai à auditoria, como o
    # primeiro acesso do dia já fazia, agora com o SHA-256.
    aviso_do_registro = registrar_os_feitos(ctx.db, r["feitos"], origem="automação",
                                             agora=ctx.agora, pasta=pasta)
    registrar_a_retencao(ctx.db, r.get("retencao"), origem="automação", pasta=pasta)
    achados = ([{"feito": f} for f in r["feitos"]] + [{"ja_existia": j} for j in r["ja_existiam"]]
               + [{"falha": f} for f in r["falhas"]])
    acoes = [{"acao": f"gerou o pacote {f['arquivo']}", "bytes": f["bytes"], "sha256": f["sha256"]}
             for f in r["feitos"]]
    if r["expurgados"]:
        acoes.append({"acao": "apagou pela retenção", "arquivos": r["expurgados"]})
    if r["falhas"]:
        partes = "; ".join(f"{f['tipo']} ({f['arquivo']}): {f['erro']}" for f in r["falhas"])
        return _resultado("ERRO", f"O BACKUP FALHOU — {partes}", achados, acoes,
                          erro=r["falhas"][0]["erro"][:500])
    avisos = list(r["avisos"])
    if aviso_do_registro:
        avisos.append(aviso_do_registro)
    if cifra == "perdida":
        avisos.append("a senha da cifra do backup está no cofre e não abre (a chave do cofre "
                      "sumiu): o pacote saiu SEM cifra — reconfigure a cifra em Configurações")
    esquecidos = [p.name for p in BKP.parciais(pasta)]
    if esquecidos:
        avisos.append(f"{len(esquecidos)} pacote(s) .parcial esquecido(s) na pasta — backup que "
                      f"começou e não terminou: {', '.join(esquecidos[:5])}")
    feitos = "; ".join(f"{f['arquivo']} ({_mb(f['bytes'])}, SHA-256 {f['sha256'][:16]}…)"
                       for f in r["feitos"])
    ja = ", ".join(j["arquivo"] for j in r["ja_existiam"])
    relato = ("Backup conferido: " + feitos if feitos else "Nada a gerar agora")
    if ja:
        relato += f" — já existia(m) hoje: {ja}"
    if avisos:
        return _resultado("AVISO", relato + ". Atenção: " + "; ".join(avisos) + ".", achados, acoes)
    return _resultado("OK", relato + ".", achados, acoes)


# ------------------------------------------------------------- o teste de restauração


def _principais(contagens: dict) -> dict:
    return {t: contagens[t] for t in REST.TABELAS_PRINCIPAIS if t in contagens}


def rodar_teste_de_restauracao(ctx) -> dict:
    """Restaura o pacote mais novo num banco descartável, confere e registra. NUNCA na produção."""
    pasta_dados = Path(ctx.pasta_dados)
    pasta = _pasta_dos_backups(ctx)
    pacote = ROT.ultimo_pacote(pasta)
    if pacote is None:
        return _resultado("ERRO", "Não há pacote de backup automático na pasta dos backups para "
                          "testar a restauração — o backup não está saindo.", [{"pasta": str(pasta)}],
                          erro="nenhum pacote")
    senha = (BKP.senha_da_cifra(pasta_dados) or None) if BKP.e_cifrado(pacote) else None
    r = REST.testar(pacote, db=ctx.db, pasta_dados=pasta_dados, senha=senha, agora=ctx.agora)
    numero = REST.registrar(ctx.db, r)
    return _relato_do_teste(r, numero, pacote, ctx.agora,
                            int(ctx.parametros.get("idade_maxima_h", 48)))


def _relato_do_teste(r: dict, numero: int, pacote: Path, agora: datetime, idade_maxima_h: int) -> dict:
    idade_h = (agora.timestamp() - pacote.stat().st_mtime) / 3600 if pacote.is_file() else 0.0
    achado = {"restauracao": numero, "pacote": r["pacote"], "tipo": r["pacote_tipo"],
              "criado_em": r["pacote_criado_em"], "sha256": r["pacote_sha256"],
              "bytes": r["pacote_bytes"], "cifrado": r["cifrado"], "situacao": r["situacao"],
              "duracao_s": r["duracao_s"], "tabelas": r["tabelas"], "linhas": r["linhas"],
              "principais": _principais(r["contagens"]), "destino": r["destino"],
              "idade_do_pacote_h": round(idade_h, 1)}
    achados = [achado] + r["divergencias"][:100]
    acoes = []
    if r["destino"]:
        acoes.append({"acao": "restaurou num banco descartável e o apagou", "destino": r["destino"]})
    if r["sobras_apagadas"]:
        acoes.append({"acao": "apagou sobras de teste anterior", "bancos": r["sobras_apagadas"]})
    cabeca = (f"Teste de restauração nº {numero} — pacote {r['pacote']} "
              f"({r['pacote_tipo'] or 'tipo não lido'}, SHA-256 {str(r['pacote_sha256'])[:16]}…)")
    if r["situacao"] == REST.FALHOU:
        return _resultado("ERRO", f"{cabeca}: O BACKUP NÃO VOLTOU — {r['erro']}", achados, acoes,
                          erro=str(r["erro"])[:500])
    corpo = (f"{cabeca}: voltou num banco descartável em {r['duracao_s']:.0f} s, com "
             f"{r['tabelas']} tabelas e {r['linhas']:,} linhas".replace(",", "."))
    if r["situacao"] == REST.DIVERGENTE:
        lista = "; ".join(f"{d['tabela']}: {d['problema']}" for d in r["divergencias"][:10])
        return _resultado("ERRO", f"{corpo} — MAS NÃO BATE com o manifesto: {lista}"
                          + (f" (e mais {len(r['divergencias']) - 10})" if len(r["divergencias"]) > 10 else "")
                          + (f". {r['erro']}" if r["erro"] else "") + ".",
                          achados, acoes, erro="contagens divergentes")
    avisos = []
    if r["situacao"] == REST.SEM_CONTAGENS:
        avisos.append("o pacote é de antes das contagens no manifesto, e por isso o que voltou não "
                      "foi conferido tabela a tabela")
    if idade_h > idade_maxima_h:
        avisos.append(f"o pacote mais novo tem {idade_h:.0f} h (o limite é {idade_maxima_h} h) — "
                      "o backup não está saindo")
    if avisos:
        return _resultado("AVISO", f"{corpo}. Atenção: " + "; ".join(avisos) + ".", achados, acoes)
    return _resultado("OK", f"{corpo}; todas as contagens batem com o manifesto.", achados, acoes)


# ------------------------------------------------------------- o catálogo

#: O que a central semeia (`automacao_processos.MODULOS_COM_PROCESSOS`). O nome
#: da função sai DA FUNÇÃO (`__name__`), e não de um texto escrito à mão: texto
#: envelhece no primeiro conserto, e o processo nasceria apontando para o nada.
CATALOGO = (
    {"codigo": "BACKUP_DIARIO", "nome": "Backup do banco no horário (e o completo semanal)",
     "setor": "TI", "funcao": f"backup_automacao.{rodar_backup.__name__}", "timeout_s": 3 * 3600,
     # 18h: decisão do oficial em 26/10/2026 («roda 18h»). Nasce desligado
     # como todo processo da central; o horário é o de fábrica, e se ajusta
     # na tela da Automação.
     "agenda": {"dias": _TODOS, "horarios": ["18:00"]},
     "descricao": "Gera o pacote do banco do dia (e o completo uma vez por semana, no dia "
                  "configurado), confere, e aplica a retenção de 5 dias — que nunca apaga o "
                  "completo-base do pacote mais novo. Não depende de alguém abrir o sistema; "
                  "falhou, a central avisa. Provimento CN/CNJ 213/2026, art. 12, § 3º, I, e § 10."},
    {"codigo": "BACKUP_TESTE_RESTAURACAO", "nome": "Teste de restauração do backup",
     "setor": "TI", "funcao": f"backup_automacao.{rodar_teste_de_restauracao.__name__}",
     "timeout_s": 3 * 3600, "agenda": {"dias": [6], "horarios": ["04:00"]},
     "parametros": {"idade_maxima_h": 48},
     "descricao": "Restaura o pacote mais novo num banco DESCARTÁVEL (nunca por cima do banco da "
                  "casa), confere as contagens de cada tabela contra o manifesto, apaga o banco "
                  "descartável e registra o resultado para a correição."},
)


# ------------------------------------------------------------- a linha de comando


def main(argv: list[str] | None = None) -> int:
    """`--testar-restauracao [pacote]` e `--historico`. Ver o docstring do módulo."""
    import automacao
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:                          # noqa: BLE001
        pass
    pasta_dados = automacao.pasta_de_dados()
    db = automacao.database_leve(pasta_dados / "cartorio_gestao.sqlite3")
    if argv and argv[0] == "--historico":
        with db.connect() as con:
            for linha in REST.ultimas(con, 20):
                print(f"#{linha['id']} {linha['iniciado_em']} {linha['situacao']:<13} "
                      f"{linha['pacote']} {linha['tabelas']} tabelas {linha['linhas']} linhas "
                      f"{linha['duracao_s']} s {linha['erro'] or ''}")
        return 0
    if argv and argv[0] == "--testar-restauracao":
        import pasta_das_copias
        with db.connect() as con:
            from bd_nativo import banco
            linha = banco(con).um("SELECT value FROM settings WHERE key = 'backup_dir'")
        pasta = pasta_das_copias.pasta_de_backups(pasta_dados, (linha or {}).get("value") or "")
        # O PACOTE ESCOLHIDO À MÃO TAMBÉM PASSA PELA LISTA (26/10/2026, PR #27):
        # `testar` recusa o que a casa não gerou, venha de onde vier. Quem
        # precisa restaurar pacote de fora faz isso à mão, num servidor de
        # teste — não por esta porta, que roda como o papel do sistema.
        pacote = Path(argv[1]) if len(argv) > 1 else ROT.ultimo_pacote(pasta)
        if pacote is None:
            print("Nenhum pacote automático na pasta dos backups.", file=sys.stderr)
            return 1
        senha = (BKP.senha_da_cifra(pasta_dados) or None) if BKP.e_cifrado(pacote) else None
        agora = datetime.now()
        r = REST.testar(pacote, db=db, pasta_dados=pasta_dados, senha=senha, agora=agora)
        numero = REST.registrar(db, r, quem="linha de comando")
        resultado = _relato_do_teste(r, numero, pacote, agora, 10 ** 6)
        print(f"[{resultado['situacao']}] {resultado['relato']}")
        return 0 if resultado["situacao"] != "ERRO" else 1
    print("uso: backup_automacao.py [--testar-restauracao [pacote.zip] | --historico]")
    return 2


if __name__ == "__main__":
    sys.exit(main())
