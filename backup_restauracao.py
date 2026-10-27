"""O TESTE DE RESTAURAÇÃO — o pacote volta, num banco DESCARTÁVEL, e as contagens batem.

POR QUE ISTO EXISTE (26/10/2026)
    Backup que nunca foi restaurado é uma promessa. O `backup.py` confere o zip,
    o banco dentro dele e o SHA-256 do manifesto — e isso prova que o arquivo
    é o que foi gravado, **não que ele volta a ser um banco**. Até hoje não
    havia um único `pg_restore` no código, embora o guia de segurança da
    implantação dissesse que havia. O Provimento CN/CNJ 213/2026 cobra a cópia
    (art. 12, § 3º, I) e o alerta quando ela falha (§ 10); um backup que não
    restaura é uma cópia que falhou sem ninguém saber.

O QUE ELE FAZ, NESTA ORDEM
    1. pega o pacote automático mais novo da pasta dos backups e calcula o
       SHA-256 dele como está no disco;
    2. confere o pacote (`backup.conferir`; o cifrado é aberto com a senha do
       cofre) e tira de dentro o `pg_dump -Fc` do banco;
    3. CRIA UM BANCO NOVO E VAZIO no servidor — `cg_restauro_<data e hora>_<sorteio>`
       —, prepara nele o `public` (`banco_pg.preparar_banco_vazio`) e roda o
       `pg_restore` NELE;
    4. conta as linhas de cada tabela que voltou e compara com as contagens que
       o manifesto gravou NO MESMO INSTANTÂNEO do pg_dump (`banco_contagens`);
    5. APAGA o banco descartável (mesmo quando algo falhou no meio) e grava o
       resultado em `bk_restauracoes`: data, pacote, SHA-256, contagens,
       divergências e tempo — é o que se mostra na correição.

NUNCA POR CIMA DA PRODUÇÃO — e não por cuidado de quem chama: por construção
    - O `pg_restore` só recebe a conexão do banco que ESTE módulo acabou de
      criar. Não há parâmetro por onde passar outro.
    - Criar e apagar só aceitam nome que case `cg_restauro_AAAAMMDDHHMMSS_xxxxxx`
      (`e_banco_descartavel`) e que não seja o banco da conexão de origem. Um
      nome errado aqui não apaga nada: recusa.
    - As sobras de uma rodada que morreu no meio (o corredor da automação mata o
      trabalho que passou do prazo) são apagadas na rodada seguinte — só as
      com o prefixo, e só as com mais de `SOBRA_VENCIDA` de idade, para não
      derrubar um teste que esteja rodando agora.

O ACHADO QUE ELE JÁ FEZ ANTES DE RODAR NA PRODUÇÃO
    O `pg_dump -n <schema>` do backup **não leva o que o schema da casa pede
    emprestado do `public`**: a collation `cg_nocase`, o `pg_trgm`, o
    `unaccent` e as funções do SQLite. Num banco vazio, o `pg_restore` puro
    falha na primeira tabela com `COLLATE public.cg_nocase`. Quem restaurar num
    servidor novo precisa preparar o `public` antes — este teste faz isso com
    os mesmos comandos do sistema, e `docs/BACKUP.md` diz como.

ONDE O BANCO DESCARTÁVEL NASCE
    No mesmo servidor do banco da casa (a conexão de `CG_PG_DSN`), num banco
    SEPARADO — salvo se `CG_PG_DSN_RESTAURACAO` apontar outro servidor, por
    exemplo o de teste. **A conexão vem SÓ do ambiente do processo, de
    propósito** (revisão de segurança de 26/10/2026, PR #27): os parâmetros do
    processo se editam na tela da automação, e quem escolhesse ali o servidor
    escolheria onde o `pg_restore` roda. Criar banco pede o privilégio
    CREATEDB; sem ele, o teste termina em ERRO dizendo isso. Enquanto roda, ele
    ocupa no servidor o tamanho do banco restaurado — é bom conferir o disco
    antes de ligar o processo.

O QUE ELE RECUSA ANTES DE RESTAURAR (revisão de segurança de 26/10/2026, PR #27)
    O `pg_restore` executa o que o pacote traz — funções, comandos, tudo — com
    o papel da conexão. O banco descartável isola os DADOS; não isola os
    PRIVILÉGIOS desse papel no servidor. Por isso:
    - SÓ SE RESTAURA PACOTE QUE A CASA GEROU. A rodada do backup grava o
      SHA-256 de cada pacote em `bk_pacotes` no instante em que o gera
      (`registrar_pacotes_gerados`), e `testar` recusa o pacote cujo nome e
      SHA-256 não estejam lá. O manifesto de dentro do zip não serve de prova:
      quem fabrica o pacote fabrica o manifesto. Pacote gerado antes desta
      regra é recusado até o próximo backup sair — vira ERRO com a frase.
    - O PAPEL NÃO PODE SER SUPERUSUÁRIO, nem membro de um, nem dos papéis que
      leem/escrevem arquivo e rodam programa no servidor, nem ter CREATEROLE,
      REPLICATION ou BYPASSRLS — conferido no `current_user` E no
      `session_user` (`SET ROLE` não engana). O papel certo é um só com
      `LOGIN CREATEDB`, em `CG_PG_DSN_RESTAURACAO`; ver `docs/BACKUP.md`.
    - O PACOTE ABERTO NÃO FICA NA PASTA DOS BACKUPS. O zip decifrado e o dump
      em claro nascem numa subpasta restrita da PASTA DE DADOS do servidor
      (`restauracao_tmp`), nunca ao lado do pacote — a pasta dos backups é a
      que sai da serventia (disco externo, rede, sincronização), e a cifra
      existe por causa dela. O zip decifrado é apagado assim que o dump sai.
"""
from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import subprocess
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import backup as BKP
import banco_pg

PREFIXO = "cg_restauro_"
_RE_DESCARTAVEL = re.compile(r"^cg_restauro_(\d{14})_[0-9a-f]{6}$")
SOBRA_VENCIDA = timedelta(hours=6)

#: As tabelas que, se não voltarem, tornam o backup inútil mesmo com o resto
#: batendo — e que o relato da rodada cita pelo nome.
TABELAS_PRINCIPAIS = ("users", "settings", "audit_logs", "attachments",
                      "cx_protocolos", "cx_lancamentos", "sd_selos",
                      "ri_matriculas", "ri_atos", "rc_assentos", "nt_atos", "pt_titulos")

OK = "OK"                       # voltou e todas as contagens bateram
DIVERGENTE = "DIVERGENTE"       # voltou, mas faltou tabela ou contagem não bateu
SEM_CONTAGENS = "SEM_CONTAGENS"  # voltou; o pacote é de antes das contagens
FALHOU = "FALHOU"               # não voltou (pacote ruim, pg_restore falhou, sem privilégio…)

SCHEMA = """
CREATE TABLE IF NOT EXISTS bk_restauracoes (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    iniciado_em TEXT NOT NULL,
    terminado_em TEXT NOT NULL,
    duracao_s DOUBLE PRECISION NOT NULL DEFAULT 0,
    situacao TEXT NOT NULL,
    pacote TEXT NOT NULL DEFAULT '',
    pacote_tipo TEXT,
    pacote_criado_em TEXT,
    pacote_bytes BIGINT,
    pacote_sha256 TEXT,
    cifrado INTEGER NOT NULL DEFAULT 0,
    destino TEXT,
    tabelas INTEGER NOT NULL DEFAULT 0,
    linhas BIGINT NOT NULL DEFAULT 0,
    contagens TEXT NOT NULL DEFAULT '{}',
    divergencias TEXT NOT NULL DEFAULT '[]',
    erro TEXT,
    quem TEXT
);
CREATE INDEX IF NOT EXISTS idx_bk_restauracoes_quando ON bk_restauracoes(iniciado_em);
-- OS PACOTES QUE A CASA GEROU (revisão de segurança de 26/10/2026, PR #27):
-- nome e SHA-256 gravados pela rodada do backup no instante em que gera. Só
-- pacote que está aqui se restaura. Nenhuma tela escreve nesta tabela.
CREATE TABLE IF NOT EXISTS bk_pacotes (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    arquivo TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    bytes BIGINT,
    tipo TEXT,
    cifrado INTEGER NOT NULL DEFAULT 0,
    gerado_em TEXT NOT NULL,
    origem TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bk_pacotes_arquivo ON bk_pacotes(arquivo)
"""


class RestauracaoRecusada(ValueError):
    """O teste não pode rodar como pedido (nome que não é descartável, pacote sem banco…)."""


def init_backup_restauracao_schema(con) -> None:
    """Cria `bk_restauracoes`. Idempotente."""
    from bd_nativo import banco
    bd = banco(con)
    for comando in SCHEMA.split(";"):
        if comando.strip():
            bd.escrever(comando)


# ------------------------------------------------------------- a conexão


def _conninfo(base: str, **trocas) -> str:
    from psycopg.conninfo import make_conninfo
    return make_conninfo(base, **trocas)


def _banco_da_conexao(base: str) -> str:
    from psycopg.conninfo import conninfo_to_dict
    return str(conninfo_to_dict(base).get("dbname") or "")


def _onde(base: str) -> str:
    """`host:porta` da conexão — sem usuário e sem senha, para gravar e mostrar."""
    from psycopg.conninfo import conninfo_to_dict
    d = conninfo_to_dict(base)
    return f"{d.get('host') or 'local'}:{d.get('port') or '5432'}"


def _sem_senha(texto: str) -> str:
    return re.sub(r"(password\s*=\s*)\S+", r"\1«omitida»", str(texto or ""), flags=re.IGNORECASE)


def conexao_de_origem() -> str:
    """A conexão do servidor onde o banco descartável nasce. SÓ DO AMBIENTE.

    Até 26/10/2026 aceitava um `dsn` de quem chamasse; ninguém o passava, e o
    docstring do módulo prometia que viria «do parâmetro do processo» — que se
    edita na tela. Saiu: quem escolhe onde o `pg_restore` roda é quem configura
    o serviço, e não a tela.
    """
    base = (os.environ.get("CG_PG_DSN_RESTAURACAO") or banco_pg.dsn() or "").strip()
    if not base:
        raise RestauracaoRecusada("não há conexão do PostgreSQL (CG_PG_DSN) para criar o "
                                  "banco descartável do teste")
    return base


def e_banco_descartavel(nome: str) -> bool:
    """O nome é de um banco que ESTE módulo cria e pode apagar?"""
    return bool(_RE_DESCARTAVEL.match(str(nome or "")))


def _novo_nome(agora: datetime) -> str:
    return f"{PREFIXO}{agora:%Y%m%d%H%M%S}_{secrets.token_hex(3)}"


def _conferir_nome(base: str, nome: str) -> None:
    if not e_banco_descartavel(nome) or nome == _banco_da_conexao(base):
        raise RestauracaoRecusada(f"«{nome}» não é um banco descartável do teste de "
                                  "restauração — nada foi criado nem apagado")


def _criar_banco(base: str, nome: str) -> None:
    import psycopg
    _conferir_nome(base, nome)
    with psycopg.connect(base, autocommit=True) as pg, pg.cursor() as c:
        c.execute(f'CREATE DATABASE "{nome}" TEMPLATE template0')


def _apagar_banco(base: str, nome: str) -> None:
    import psycopg
    _conferir_nome(base, nome)
    with psycopg.connect(base, autocommit=True) as pg, pg.cursor() as c:
        c.execute(f'DROP DATABASE IF EXISTS "{nome}" WITH (FORCE)')


def bancos_descartaveis(base: str) -> list[str]:
    """Os bancos do teste que existem agora no servidor (só LÊ)."""
    import psycopg
    with psycopg.connect(base, autocommit=True) as pg, pg.cursor() as c:
        c.execute("SELECT datname FROM pg_database WHERE datname LIKE %s ORDER BY datname",
                  (PREFIXO + "%",))
        return [n for (n,) in c.fetchall() if e_banco_descartavel(n)]


def apagar_sobras(base: str, agora: datetime) -> list[str]:
    """Apaga os bancos do teste deixados por uma rodada que morreu no meio."""
    apagados = []
    for nome in bancos_descartaveis(base):
        nasceu = datetime.strptime(_RE_DESCARTAVEL.match(nome).group(1), "%Y%m%d%H%M%S")
        if agora - nasceu > SOBRA_VENCIDA:
            _apagar_banco(base, nome)
            apagados.append(nome)
    return apagados


# O PAPEL QUE RESTAURA NÃO PODE TER PODER NO SERVIDOR (26/10/2026, PR #27 M1).
#
#   O `pg_restore` roda o que o pacote traz com o papel da conexão. Com
#   superusuário, um pacote forjado faria `ALTER ROLE`, `COPY ... TO PROGRAM`
#   (programa no sistema operacional) ou leria arquivo do servidor. Os três
#   papéis `pg_*_server_*` dão isso sem superusuário, e por isso também contam.
#   Confere-se o `session_user` além do `current_user`: um `SET ROLE` na
#   conexão mudaria um e não o outro, e o pacote poderia voltar com `RESET ROLE`.
_PAPEIS_QUE_ALCANCAM_O_SERVIDOR = ("pg_execute_server_program", "pg_write_server_files",
                                   "pg_read_server_files")
_SQL_PAPEL = """
SELECT r.rolname, r.rolsuper, r.rolcreaterole, r.rolreplication, r.rolbypassrls
  FROM pg_roles r
 WHERE r.rolname IN (current_user, session_user)
    OR ((r.rolsuper OR r.rolname = ANY(%s))
        AND (pg_has_role(session_user, r.oid, 'MEMBER')
             OR pg_has_role(current_user, r.oid, 'MEMBER')))
"""


def _poder_do_papel(base: str) -> list[str]:
    """O que o papel da conexão pode no servidor além de criar banco. Vazio = ok. Só LÊ."""
    import psycopg
    with psycopg.connect(base, autocommit=True) as pg, pg.cursor() as c:
        c.execute("SELECT current_user, session_user")
        proprios = set(c.fetchone())
        c.execute(_SQL_PAPEL, (list(_PAPEIS_QUE_ALCANCAM_O_SERVIDOR),))
        linhas = c.fetchall()
    poderes = []
    for nome, sup, cria_papel, replica, fura_rls in linhas:
        if nome in proprios:
            poderes += [f"{nome}: {o_que}" for o_que, tem in
                        (("SUPERUSER", sup), ("CREATEROLE", cria_papel),
                         ("REPLICATION", replica), ("BYPASSRLS", fura_rls)) if tem]
        else:
            poderes.append(f"membro de {nome}")
    return sorted(set(poderes))


def conferir_o_papel(base: str) -> None:
    """Recusa (`RestauracaoRecusada`) o papel com poder no servidor. Só LÊ."""
    poderes = _poder_do_papel(base)
    if poderes:
        raise RestauracaoRecusada(
            "o papel da conexão tem poder demais no servidor para rodar o pg_restore de um "
            f"pacote ({'; '.join(poderes)}) — crie um papel só com LOGIN CREATEDB e aponte "
            "CG_PG_DSN_RESTAURACAO para ele (docs/BACKUP.md). Nada foi restaurado")


# ------------------------------------------------------------- o pacote


def registrar_pacotes_gerados(db, feitos: list[dict], *, origem: str,
                              agora: datetime | None = None) -> int:
    """Grava em `bk_pacotes` o nome e o SHA-256 dos pacotes que a rodada acabou de gerar.

    `feitos` é o `backup_rotina.rodada(...)["feitos"]` (cada um com `arquivo`,
    `sha256`, `bytes`, `tipo`, `cifrado`). Chamada pelas DUAS portas da rodada —
    a automação e o primeiro acesso do dia — logo depois de gerar. ESCREVE no
    banco da casa; devolve quantos gravou.
    """
    from bd_nativo import banco
    quando = (agora or datetime.now()).isoformat(timespec="seconds")
    n = 0
    with db.connect() as con:
        init_backup_restauracao_schema(con)
        bd = banco(con)
        for f in feitos or ():
            if not f.get("arquivo") or not f.get("sha256"):
                continue
            bd.escrever(
                """INSERT INTO bk_pacotes (arquivo, sha256, bytes, tipo, cifrado, gerado_em, origem)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                (str(f["arquivo"]), str(f["sha256"]), f.get("bytes"), f.get("tipo"),
                 1 if f.get("cifrado") else 0, quando, str(origem)[:60]))
            n += 1
    return n


def nomes_registrados(db) -> set[str]:
    """Os nomes de pacote que a rodada gravou em `bk_pacotes`. Só LÊ.

    Serve à retenção (26/10/2026): ela só apaga pacote recente que esteja
    aqui. Se a tabela não existe ou a leitura falha, devolve o conjunto VAZIO,
    e não None — o lado seguro: sem registro legível, nada recente se apaga
    (o pacote de antes do registro continua reconhecido pelo nome).
    """
    from bd_nativo import banco
    try:
        with db.connect() as con:
            bd = banco(con)
            if not bd.tem_tabela("bk_pacotes"):
                return set()
            return {str(r["arquivo"]) for r in bd.ler("SELECT DISTINCT arquivo FROM bk_pacotes")}
    except Exception:                          # noqa: BLE001 — o lado seguro é não apagar
        return set()


def _conferir_que_a_casa_gerou(db, pacote: Path, sha256: str | None) -> None:
    """Recusa o pacote cujo nome e SHA-256 a rodada do backup não gravou. Só LÊ."""
    from bd_nativo import banco
    with db.connect() as con:
        bd = banco(con)
        achado = bd.tem_tabela("bk_pacotes") and bd.um(
            "SELECT id FROM bk_pacotes WHERE arquivo = %s AND sha256 = %s LIMIT 1",
            (pacote.name, str(sha256 or "")))
    if not achado:
        raise RestauracaoRecusada(
            f"o pacote {pacote.name} não consta entre os que o sistema gerou (nome e SHA-256 "
            "em bk_pacotes) — ou foi gerado antes desta conferência (26/10/2026), ou foi "
            "trocado na pasta dos backups. Só se restaura pacote que a casa gerou; o próximo "
            "backup automático já entra na lista")


NOME_DA_PASTA_DE_TRABALHO = "restauracao_tmp"


def _pasta_de_trabalho(pasta_dados: Path, pacote: Path) -> Path:
    """Onde o pacote é aberto: na pasta de DADOS do servidor, restrita — nunca na dos backups.

    Revisão de segurança de 26/10/2026 (PR #27, M2): a pasta dos backups é a
    que sai da serventia, e o pacote decifrado e o dump em claro ficavam nela
    durante a rodada inteira (até 3 h). Se a pasta de dados estiver DENTRO da
    pasta dos backups (configuração torta), recusa em vez de abrir lá.
    """
    pasta = Path(pasta_dados).resolve() / NOME_DA_PASTA_DE_TRABALHO
    dos_backups = Path(pacote).resolve().parent
    if pasta == dos_backups or dos_backups in pasta.parents:
        raise RestauracaoRecusada(
            "a pasta de dados do servidor fica dentro da pasta dos backups, e o pacote aberto "
            "(sem cifra) ficaria nela — aponte a pasta dos backups para outro lugar em "
            "Configurações")
    pasta.mkdir(parents=True, exist_ok=True)
    import permissao_local
    permissao_local.restringir(pasta, pasta=True)
    return pasta


def _tirar_o_dump(pacote: Path, tmp: Path, senha: str | None) -> tuple[Path, dict]:
    """O `pg_dump` de dentro do pacote e o manifesto. Levanta `RestauracaoRecusada`."""
    try:
        if BKP.e_cifrado(pacote):
            claro = BKP.abrir(pacote, tmp / "pacote.zip", senha)
        else:
            problema = BKP.conferir(pacote)
            if problema:
                raise BKP.BackupInvalido(problema)
            claro = pacote
    except BKP.BackupInvalido as erro:
        raise RestauracaoRecusada(f"o pacote não passou na conferência: {erro}") from erro
    dump = tmp / "banco.dump"
    with zipfile.ZipFile(claro) as zf:
        manifesto = json.loads(zf.read(BKP.NOME_MANIFESTO).decode("utf-8"))
        with zf.open(BKP.NOME_BANCO) as origem, dump.open("wb") as destino:
            shutil.copyfileobj(origem, destino, 1024 * 1024)
    if claro != pacote:
        claro.unlink(missing_ok=True)
    formato = BKP.formato_do_banco(dump)
    if formato != BKP.FORMATO_PG_DUMP:
        raise RestauracaoRecusada(
            f"o banco dentro do pacote não é um pg_dump (formato: {formato}) — é pacote de "
            "antes da migração para o PostgreSQL, e se restaura pela carga da migração")
    return dump, manifesto


def _restaurar(base: str, nome: str, dump: Path) -> tuple[str, dict[str, int]]:
    """Prepara o banco descartável, roda o pg_restore NELE e conta o que voltou."""
    import psycopg
    alvo = _conninfo(base, dbname=nome)
    with psycopg.connect(alvo, autocommit=True) as pg, pg.cursor() as c:
        banco_pg.preparar_banco_vazio(c)
    exe = banco_pg.binario_do_postgres("pg_restore")
    # A SENHA NÃO VAI NA LINHA DE COMANDO (26/10/2026, BAIXA da revisão): se a
    # conexão a trouxer, ela segue por PGPASSWORD no ambiente do filho, e não
    # na lista de processos que qualquer conta da máquina lê.
    from psycopg.conninfo import conninfo_to_dict
    partes = conninfo_to_dict(alvo)
    senha = partes.pop("password", None)
    ambiente = dict(os.environ)
    if senha:
        ambiente["PGPASSWORD"] = str(senha)
    proc = subprocess.run([str(exe), "--no-owner", "--no-privileges", "--exit-on-error",
                           "-d", _conninfo("", **partes), str(dump)],
                          capture_output=True, text=True, check=False, env=ambiente)
    if proc.returncode != 0:
        raise RestauracaoRecusada("o pg_restore falhou: "
                                  + _sem_senha(proc.stderr or proc.stdout)[-600:])
    with psycopg.connect(alvo, autocommit=True) as pg, pg.cursor() as c:
        c.execute("SELECT nspname FROM pg_namespace WHERE nspname <> 'public' "
                  "AND nspname <> 'information_schema' AND nspname NOT LIKE 'pg\\_%' "
                  "ORDER BY nspname")
        esquemas = [n for (n,) in c.fetchall()]
        if len(esquemas) != 1:
            raise RestauracaoRecusada(f"esperava um schema restaurado e vieram {len(esquemas)}")
        return esquemas[0], banco_pg.contar_linhas(c, esquemas[0])


def comparar(esperado: dict | None, restaurado: dict[str, int]) -> list[dict]:
    """As diferenças entre o manifesto e o que voltou. Lista vazia = bateu."""
    saida = [{"tabela": t, "problema": "tabela principal não voltou"}
             for t in TABELAS_PRINCIPAIS if t not in restaurado]
    if esperado is None:
        return saida
    principais = {d["tabela"] for d in saida}
    for tabela, n in sorted(esperado.items()):
        if tabela in principais:
            continue
        if tabela not in restaurado:
            saida.append({"tabela": tabela, "problema": "não voltou", "esperado": int(n)})
        elif int(restaurado[tabela]) != int(n):
            saida.append({"tabela": tabela, "problema": "contagem diferente",
                          "esperado": int(n), "restaurado": int(restaurado[tabela])})
    for tabela in sorted(set(restaurado) - set(esperado)):
        saida.append({"tabela": tabela, "problema": "voltou sem estar no manifesto",
                      "restaurado": int(restaurado[tabela])})
    return saida


def testar(pacote: Path, *, db, pasta_dados: Path, senha: str | None = None,
           agora: datetime | None = None) -> dict:
    """Restaura `pacote` num banco descartável, confere e apaga. NÃO grava no banco da casa.

    Devolve o resultado (o que vai para `bk_restauracoes` e para o relato da
    automação). Não levanta por falha de restauração: a falha é o resultado
    `FALHOU`, com o motivo — «não restaurou» é exatamente o que se quer saber.

    `db` é o banco da casa, só LIDO aqui (`bk_pacotes`: o pacote é um que a
    casa gerou?); `pasta_dados` é a pasta de dados do servidor, onde o pacote
    é aberto. As duas são obrigatórias desde 26/10/2026 (PR #27) — sem padrão,
    para que nenhum chamador as esqueça e caia na pasta dos backups.
    """
    agora = agora or datetime.now()
    pacote = Path(pacote)
    inicio = time.monotonic()
    r: dict[str, Any] = {
        "iniciado_em": agora.isoformat(timespec="seconds"), "pacote": pacote.name,
        "pacote_tipo": None, "pacote_criado_em": None,
        "pacote_bytes": pacote.stat().st_size if pacote.is_file() else None,
        "pacote_sha256": BKP._sha256(pacote) if pacote.is_file() else None,
        "cifrado": BKP.e_cifrado(pacote), "destino": None, "situacao": FALHOU,
        "tabelas": 0, "linhas": 0, "contagens": {}, "divergencias": [], "erro": None,
        "sobras_apagadas": [],
    }
    nome = None
    base = None
    try:
        if not pacote.is_file():
            raise RestauracaoRecusada(f"o pacote {pacote.name} não existe")
        # AS RECUSAS ANTES DE TUDO (26/10/2026, PR #27): pacote que a casa não
        # gerou, papel com poder no servidor, e pasta de trabalho dentro da
        # dos backups. Nenhuma cria nem apaga banco.
        _conferir_que_a_casa_gerou(db, pacote, r["pacote_sha256"])
        base = conexao_de_origem()
        conferir_o_papel(base)
        trabalho = _pasta_de_trabalho(pasta_dados, pacote)
        with TemporaryDirectory(prefix="restauracao_", dir=str(trabalho)) as tmp:
            # O QUE SE RESTAURA É A CÓPIA QUE SE CONFERIU: o pacote vem para a
            # pasta de trabalho e a conferência se refaz NELA — trocar o
            # arquivo na pasta dos backups depois do primeiro SHA-256 não
            # passa a outro conteúdo para o pg_restore.
            copia = Path(tmp) / "recebido.pacote"
            shutil.copyfile(pacote, copia)
            r["pacote_sha256"] = BKP._sha256(copia)
            r["pacote_bytes"] = copia.stat().st_size
            _conferir_que_a_casa_gerou(db, pacote, r["pacote_sha256"])
            r["sobras_apagadas"] = apagar_sobras(base, agora)
            dump, manifesto = _tirar_o_dump(copia, Path(tmp), senha)
            copia.unlink(missing_ok=True)
            r["pacote_tipo"] = manifesto.get("tipo")
            r["pacote_criado_em"] = manifesto.get("created_at")
            nome = _novo_nome(agora)
            r["destino"] = f"{_onde(base)}/{nome}"
            _criar_banco(base, nome)
            _schema, contagens = _restaurar(base, nome, dump)
        r["contagens"] = contagens
        r["tabelas"] = len(contagens)
        r["linhas"] = sum(contagens.values())
        esperado = manifesto.get("banco_contagens")
        r["divergencias"] = comparar(esperado, contagens)
        if r["divergencias"]:
            r["situacao"] = DIVERGENTE
        elif esperado is None:
            r["situacao"] = SEM_CONTAGENS
        else:
            r["situacao"] = OK
    except RestauracaoRecusada as erro:
        r["erro"] = str(erro)[:1000]
    except Exception as erro:                  # noqa: BLE001 — o motivo vai no resultado
        r["erro"] = _sem_senha(f"{type(erro).__name__}: {erro}")[:1000]
    finally:
        if nome and base:
            try:
                _apagar_banco(base, nome)
            except Exception as erro:          # noqa: BLE001
                r["erro"] = ((r["erro"] + " · ") if r["erro"] else "") + _sem_senha(
                    f"o banco descartável {nome} NÃO foi apagado: {erro}")[:500]
                if r["situacao"] == OK:
                    r["situacao"] = DIVERGENTE
    r["duracao_s"] = round(time.monotonic() - inicio, 1)
    r["terminado_em"] = (agora + timedelta(seconds=r["duracao_s"])).isoformat(timespec="seconds")
    return r


# ------------------------------------------------------------- o registro


def registrar(db, r: dict, quem: str = "automação") -> int:
    """Grava a rodada em `bk_restauracoes` e devolve o número dela. ESCREVE no banco da casa."""
    from bd_nativo import banco
    with db.connect() as con:
        init_backup_restauracao_schema(con)
        linhas = banco(con).escrever(
            """INSERT INTO bk_restauracoes (iniciado_em, terminado_em, duracao_s, situacao,
                   pacote, pacote_tipo, pacote_criado_em, pacote_bytes, pacote_sha256, cifrado,
                   destino, tabelas, linhas, contagens, divergencias, erro, quem)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (r["iniciado_em"], r["terminado_em"], float(r["duracao_s"]), r["situacao"],
             r["pacote"], r["pacote_tipo"], r["pacote_criado_em"], r["pacote_bytes"],
             r["pacote_sha256"], 1 if r["cifrado"] else 0, r["destino"], int(r["tabelas"]),
             int(r["linhas"]), json.dumps(r["contagens"], sort_keys=True),
             json.dumps(r["divergencias"], ensure_ascii=False), r["erro"], quem))
    return int(linhas[0]["id"])


def ultimas(con, limite: int = 10) -> list[dict]:
    """As últimas rodadas do teste, da mais nova para a mais velha (só LÊ)."""
    from bd_nativo import banco
    bd = banco(con)
    if not bd.tem_tabela("bk_restauracoes"):
        return []
    return bd.ler("""SELECT id, iniciado_em, duracao_s, situacao, pacote, pacote_sha256,
                            tabelas, linhas, erro
                       FROM bk_restauracoes ORDER BY id DESC LIMIT %s""", (int(limite),))
