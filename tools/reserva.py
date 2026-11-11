"""O SERVIDOR RESERVA NO macOS — a réplica do banco do principal, de ponta a ponta.

Pedido do oficial, 07/11/2026: um servidor extra no macOS, «backup do servidor original, em
uma porta diferente, mas com banco de dados sincronizado». Decidido com ele: a reserva só lê
enquanto o principal está no ar, e assume se ele cair. O roteiro está em
`docs/SERVIDOR_RESERVA_MACOS.md`; aqui ficam as ferramentas que ele chama.

POR QUE RÉPLICA LÓGICA (publicação/assinatura do PostgreSQL), e não a física: a física copia o
disco do banco byte a byte e exige o mesmo sistema operacional — o principal é Windows, a
reserva é macOS, e o banco do Windows grava o idioma em nome de Windows (`Portuguese_Brazil`),
que o macOS não tem. A lógica manda LINHAS, e linha não tem sistema operacional.

O QUE A RÉPLICA LÓGICA NÃO LEVA, e quem leva aqui:
    - o ESQUEMA (tabela e coluna novas de uma versão nova): `esquema`, que roda sozinho de
      tempos em tempos (o LaunchAgent da sincronia) e antes de cada atualização;
    - as SEQUÊNCIAS (o próximo id de cada tabela): `assumir` acerta cada uma pelo maior id.

COMANDOS
    sql-do-principal   imprime o SQL que se roda UMA vez no principal (psql, no Windows)
    montar             cria o banco da reserva, copia o esquema do principal e liga a assinatura
    situacao           a réplica está em dia? (sai 1 se não estiver)
    conferir           conta as linhas de cada tabela nos dois lados
    esquema            acrescenta na reserva as tabelas e colunas novas do principal
    assumir            a reserva vira o principal (o principal caiu e não volta hoje)
    emergencia         o botão: trava a escrita do principal se ele responder, desliga a
                       assinatura, despeja a reserva e promove (é o que o assumir.sh chama)
    voltar             devolve ao principal o que a reserva gravou e religa a réplica
    chave-da-reserva   sorteia o par de chaves da reserva (uma vez) e mostra a pública
    chaves             abre o pacote de segredos que o principal cifrou para a reserva
    pastas             copia as pastas configuradas FORA da pasta de arquivos (--apontar: assumir)

AS CONEXÕES (nunca com senha na linha: a senha vai no `~/.pgpass`, como no principal — ver
`docs/SEGURANCA_REDE.md`, item 3):
    CG_RESERVA_PRINCIPAL_DSN   o banco do principal, pelo usuário `cg_replica`
    CG_RESERVA_LOCAL_DSN       o banco da reserva, pelo dono dele (`cg`)
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_RAIZ = Path(__file__).resolve().parent
sys.path.insert(0, str(_RAIZ.parent))
sys.path.insert(0, str(_RAIZ))
import reserva_chaves as RCH  # noqa: E402
import trava_producao as TRAVA  # noqa: E402
import contingencia as CONT  # noqa: E402

try:
    import psycopg
    from psycopg import sql as S
except ImportError:  # pragma: no cover
    sys.exit("falta o psycopg: rode com o Python do sistema (venv) — ver o roteiro")

PUBLICACAO = "cg_reserva"
ASSINATURA = "cg_reserva"
PAPEL_DA_REPLICA = "cg_replica"
PAPEL_DE_LEITURA = "cg_leitor"
#: O teto do log que o principal guarda para a reserva desligada. Sem teto, um Mac fora do ar
#: por uma semana encheria o disco do PRINCIPAL. Passou dele, a réplica se perde e se remonta
#: (`montar --refazer`) — o que custa minutos, e não o expediente.
TETO_DO_LOG = "20GB"
#: A réplica está «em dia» se a última mensagem do principal chegou há menos disto.
ATRASO_TOLERADO_S = 300
FRASE_DE_ASSUMIR = "ASSUMIR"


# ------------------------------------------------------------------ o SQL do principal

def sql_do_principal(schema: str, dono: str, publica: str = "") -> str:
    """O SQL que se roda uma vez no banco do principal, com `psql -v senha=...`.

    Tudo é idempotente: rodar de novo não desfaz nem duplica nada. O que exige reiniciar o
    serviço do PostgreSQL (`wal_level`) só vale depois do reinício — o roteiro diz quando.
    """
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", schema) or not re.fullmatch(r"[a-z_][a-z0-9_]*", dono):
        raise ValueError("schema e dono: só minúsculas, dígitos e _")
    if publica and not (re.fullmatch(r"[A-Za-z0-9+/]{43}=", publica) and RCH.publica_valida(publica)):
        raise ValueError("a chave pública da reserva não é X25519 em base64")
    if publica:
        chaves = (f"-- 6. A chave PÚBLICA da reserva: o principal cifra para ela os segredos da pasta de\n"
                  f"--    dados (reserva_chaves.py). Só a privada, que não sai do Mac, abre o pacote.\n"
                  f"INSERT INTO {schema}.settings(key, value) VALUES ('{RCH.CHAVE_PUBLICA}', '{publica}')\n"
                  f"    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;\n")
    else:
        chaves = ("-- 6. SEM a chave da reserva: os segredos da pasta de dados NÃO vão. Rode no Mac\n"
                  "--    `reserva.py chave-da-reserva` e gere este SQL de novo.\n")
    return f"""\\set ON_ERROR_STOP on
-- Servidor reserva (docs/SERVIDOR_RESERVA_MACOS.md): o lado do PRINCIPAL. Rode com
--   psql -h 127.0.0.1 -p 5434 -U {dono} -d cartorio -v senha=<senha do cg_replica> -f principal.sql

DO $$ BEGIN
  IF current_setting('server_version_num')::int < 150000 THEN
    RAISE EXCEPTION 'a réplica por schema pede PostgreSQL 15 ou mais novo (este é %)', version();
  END IF;
END $$;

-- 1. O log passa a levar linhas (vale depois de reiniciar o serviço) e tem teto: a reserva
--    desligada por dias não enche o disco do principal.
ALTER SYSTEM SET wal_level = 'logical';
ALTER SYSTEM SET max_slot_wal_keep_size = '{TETO_DO_LOG}';
SELECT pg_reload_conf();   -- o teto vale já; o wal_level, só depois de reiniciar

-- 2. O usuário da réplica: entra, replica e LÊ — mais nada.
SELECT 'CREATE ROLE {PAPEL_DA_REPLICA} LOGIN REPLICATION'
 WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{PAPEL_DA_REPLICA}') \\gexec
ALTER ROLE {PAPEL_DA_REPLICA} WITH LOGIN REPLICATION PASSWORD :'senha';
SELECT format('GRANT CONNECT ON DATABASE %I TO {PAPEL_DA_REPLICA}', current_database()) \\gexec
GRANT USAGE ON SCHEMA {schema}, public TO {PAPEL_DA_REPLICA};
GRANT SELECT ON ALL TABLES IN SCHEMA {schema}, public TO {PAPEL_DA_REPLICA};
ALTER DEFAULT PRIVILEGES FOR ROLE {dono} IN SCHEMA {schema} GRANT SELECT ON TABLES TO {PAPEL_DA_REPLICA};

-- 3. TABELA SEM CHAVE: com a publicação ligada, o PostgreSQL RECUSARIA UPDATE e DELETE nela no
--    próprio principal. Nenhuma tabela da casa é assim (medido em 07/11/2026: 320 de 320 com
--    chave); se a carga antiga deixou alguma, ela passa a mandar a linha inteira.
SELECT format('ALTER TABLE %I.%I REPLICA IDENTITY FULL', n.nspname, k.relname)
  FROM pg_class k JOIN pg_namespace n ON n.oid = k.relnamespace
 WHERE n.nspname = '{schema}' AND k.relkind = 'r' AND k.relreplident = 'd'
   AND NOT EXISTS (SELECT 1 FROM pg_index i WHERE i.indrelid = k.oid AND i.indisprimary) \\gexec

-- 4. A publicação: o schema inteiro, com as tabelas que as versões novas criarem.
--    Só linha nova, linha mudada e linha apagada. Esvaziar a tabela no principal
--    não viaja: a reserva não perde o acervo por um comando desses.
SELECT 'CREATE PUBLICATION {PUBLICACAO} FOR TABLES IN SCHEMA {schema} WITH (publish = ''insert, update, delete'')'
 WHERE NOT EXISTS (SELECT 1 FROM pg_publication WHERE pubname = '{PUBLICACAO}') \\gexec
ALTER PUBLICATION {PUBLICACAO} SET (publish = 'insert, update, delete');

-- 5. Conferência: o que falta para a reserva conectar.
SELECT name, setting, CASE WHEN pending_restart THEN 'REINICIE O SERVIÇO' ELSE 'ok' END AS estado
  FROM pg_settings WHERE name IN ('wal_level', 'max_slot_wal_keep_size', 'listen_addresses');

{chaves}"""


# ------------------------------------------------------------------ as conexões

def _dsn(variavel: str, dado: str | None) -> str:
    valor = (dado or os.environ.get(variavel) or "").strip()
    if not valor:
        sys.exit(f"falta a conexão: --{variavel.lower()} ou a variável {variavel}")
    if re.search(r"password\s*=", valor, re.I):
        sys.exit("a senha não vai na conexão (ela aparece na lista de processos): use o ~/.pgpass")
    return valor


def _abrir(dsn: str):
    return psycopg.connect(dsn, autocommit=True, connect_timeout=10)


def _binario(nome: str) -> str:
    pasta = (os.environ.get("CG_PG_BIN") or "").strip()
    caminho = os.path.join(pasta, nome) if pasta else shutil.which(nome)
    if not caminho or not os.path.exists(caminho):
        sys.exit(f"não achei o {nome}: ponha a pasta dos binários do PostgreSQL 18 em CG_PG_BIN")
    return caminho


def _colunas(c, schema: str) -> dict[str, dict[str, str]]:
    """{tabela: {coluna: tipo}} das tabelas comuns do schema."""
    c.execute("""SELECT k.relname, a.attname, format_type(a.atttypid, a.atttypmod)
                   FROM pg_attribute a JOIN pg_class k ON k.oid = a.attrelid
                   JOIN pg_namespace n ON n.oid = k.relnamespace
                  WHERE n.nspname = %s AND k.relkind = 'r' AND a.attnum > 0 AND NOT a.attisdropped
                  ORDER BY k.relname, a.attnum""", (schema,))
    saida: dict[str, dict[str, str]] = {}
    for tabela, coluna, tipo in c.fetchall():
        saida.setdefault(tabela, {})[coluna] = tipo
    return saida


# ------------------------------------------------------------------ montar

def montar(principal: str, local: str, schema: str, refazer: bool) -> None:
    """Cria a reserva: o esquema inteiro do principal (com as funções do `public`), os papéis, e a
    assinatura, que copia as linhas e depois segue o principal sozinha."""
    TRAVA.recusar_montar(local, principal, schema)
    with _abrir(local) as pg, pg.cursor() as c:
        existe = c.execute("SELECT 1 FROM pg_subscription WHERE subname=%s", (ASSINATURA,)).fetchone()
        if existe and not refazer:
            sys.exit("a reserva já está montada (use `situacao`; para começar do zero, `montar --refazer`)")
        if existe:
            _largar_assinatura(c, principal_vivo=True)
        # O banco da reserva é só dela: o schema da casa E o `public` (as funções, a collation e
        # as extensões da casa) vêm inteiros do principal, sem sobra de tentativa ou versão velha.
        c.execute(S.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(S.Identifier(schema)))
        c.execute("DROP SCHEMA IF EXISTS public CASCADE")
        c.execute("CREATE SCHEMA public")
        _extensoes_do_principal(principal, c)
    print("copiando o esquema do principal (sem linhas)…")
    dump = subprocess.run(
        [_binario("pg_dump"), "--schema-only", "--no-owner", "--no-privileges",
         "--no-publications", "--no-subscriptions", "-n", schema, "-n", "public", "-d", principal],
        capture_output=True, text=True, check=False)
    if dump.returncode != 0:
        sys.exit(f"pg_dump do principal falhou:\n{dump.stderr[-2000:]}")
    # «CREATE SCHEMA public» já existe em todo banco novo
    texto = re.sub(r"^CREATE SCHEMA public;$", "", dump.stdout, flags=re.M)
    carga = subprocess.run([_binario("psql"), "-X", "-q", "-v", "ON_ERROR_STOP=1", "-d", local],
                           input=texto, capture_output=True, text=True, check=False)
    if carga.returncode != 0:
        sys.exit(f"a carga do esquema na reserva falhou:\n{carga.stderr[-2000:]}")
    with _abrir(local) as pg, pg.cursor() as c:
        _papel_de_leitura(c, schema)
        print("ligando a assinatura (a primeira cópia das linhas corre em segundo plano)…")
        c.execute(S.SQL("CREATE SUBSCRIPTION {} CONNECTION {} PUBLICATION {} "
                        "WITH (copy_data = true, disable_on_error = false)").format(
            S.Identifier(ASSINATURA), S.Literal(principal), S.Identifier(PUBLICACAO)))
    print("pronto. Acompanhe com: reserva.py situacao")


def _extensoes_do_principal(principal: str, c_local) -> None:
    """As extensões do principal (pg_trgm, unaccent…), criadas antes do esquema: o `pg_dump -n` não
    as leva, e o índice que usa `gin_trgm_ops` não nasce sem elas."""
    with _abrir(principal) as p, p.cursor() as cp:
        extensoes = cp.execute("SELECT e.extname, n.nspname FROM pg_extension e "
                               "JOIN pg_namespace n ON n.oid = e.extnamespace "
                               "WHERE e.extname <> 'plpgsql' ORDER BY 1").fetchall()
    for nome, nsp in extensoes:
        c_local.execute(S.SQL("CREATE EXTENSION IF NOT EXISTS {} SCHEMA {}").format(
            S.Identifier(nome), S.Identifier(nsp)))


def _papel_de_leitura(c, schema: str) -> None:
    """O usuário com que o SISTEMA da reserva entra no banco: só SELECT. É a trava de verdade do
    «a reserva só lê» — o `modo_reserva` do sistema só faz a recusa vir com a frase certa."""
    if not c.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (PAPEL_DE_LEITURA,)).fetchone():
        c.execute(S.SQL("CREATE ROLE {} LOGIN").format(S.Identifier(PAPEL_DE_LEITURA)))
    papel = S.Identifier(PAPEL_DE_LEITURA)
    c.execute(S.SQL("GRANT USAGE ON SCHEMA {}, public TO {}").format(S.Identifier(schema), papel))
    c.execute(S.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA {}, public TO {}").format(S.Identifier(schema), papel))
    c.execute(S.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA {} GRANT SELECT ON TABLES TO {}").format(
        S.Identifier(schema), papel))


def _largar_assinatura(c, *, principal_vivo: bool) -> None:
    c.execute(S.SQL("ALTER SUBSCRIPTION {} DISABLE").format(S.Identifier(ASSINATURA)))
    if not principal_vivo:
        # Sem o principal, o DROP tentaria apagar o slot lá e falharia. O slot que fica no
        # principal morto se apaga quando ele voltar (roteiro, «a volta do principal»).
        c.execute(S.SQL("ALTER SUBSCRIPTION {} SET (slot_name = NONE)").format(S.Identifier(ASSINATURA)))
    c.execute(S.SQL("DROP SUBSCRIPTION {}").format(S.Identifier(ASSINATURA)))


# ------------------------------------------------------------------ situação

@dataclass
class Situacao:
    ligada: bool
    atraso_s: float | None
    tabelas_copiando: int
    erros: int
    tabelas: int

    @property
    def em_dia(self) -> bool:
        return (self.ligada and self.tabelas_copiando == 0 and self.atraso_s is not None
                and self.atraso_s <= ATRASO_TOLERADO_S)


def ler_situacao(c) -> Situacao | None:
    linha = c.execute("SELECT s.subenabled, (SELECT count(*) FROM pg_subscription_rel r "
                      "  WHERE r.srsubid = s.oid AND r.srsubstate <> 'r'), "
                      "(SELECT count(*) FROM pg_subscription_rel r WHERE r.srsubid = s.oid) "
                      "FROM pg_subscription s WHERE s.subname = %s", (ASSINATURA,)).fetchone()
    if linha is None:
        return None
    ligada, copiando, tabelas = linha
    atraso = c.execute("SELECT extract(epoch FROM now() - max(last_msg_receipt_time)) "
                       "FROM pg_stat_subscription WHERE subname = %s", (ASSINATURA,)).fetchone()[0]
    erros = c.execute("SELECT coalesce(apply_error_count + sync_error_count, 0) "
                      "FROM pg_stat_subscription_stats WHERE subname = %s", (ASSINATURA,)).fetchone()
    return Situacao(ligada, float(atraso) if atraso is not None else None, copiando,
                    int(erros[0]) if erros else 0, tabelas)


def situacao(local: str) -> int:
    with _abrir(local) as pg, pg.cursor() as c:
        s = ler_situacao(c)
    if s is None:
        print("a reserva não está montada (nenhuma assinatura). Ver `montar`.")
        return 1
    atraso = "sem notícia do principal" if s.atraso_s is None else f"última notícia há {s.atraso_s:.0f} s"
    print(f"assinatura: {'ligada' if s.ligada else 'DESLIGADA'}; {atraso}; "
          f"{s.tabelas - s.tabelas_copiando} de {s.tabelas} tabelas em dia; erros acumulados: {s.erros}")
    if s.tabelas_copiando:
        print(f"  {s.tabelas_copiando} tabela(s) ainda na primeira cópia — normal na primeira hora")
    if s.erros and not s.em_dia:
        print("  houve erro na réplica: rode `reserva.py esquema` (versão nova no principal?) e veja o "
              "log do PostgreSQL da reserva")
    print("EM DIA" if s.em_dia else "ATRASADA")
    return 0 if s.em_dia else 1


# ------------------------------------------------------------------ conferir

def conferir(principal: str, local: str, schema: str) -> int:
    """Conta as linhas de cada tabela nos dois lados. Diferença pequena numa tabela movimentada é
    o lançamento que ainda vem a caminho — rode de novo; a que persiste é defeito."""
    with _abrir(principal) as p, p.cursor() as cp, _abrir(local) as l, l.cursor() as cl:
        tabelas = sorted(_colunas(cp, schema))
        locais = set(_colunas(cl, schema))
        diferentes = 0
        for t in tabelas:
            consulta = S.SQL("SELECT count(*) FROM {}.{}").format(S.Identifier(schema), S.Identifier(t))
            n_p = cp.execute(consulta).fetchone()[0]
            n_l = cl.execute(consulta).fetchone()[0] if t in locais else None
            if n_p != n_l:
                diferentes += 1
                print(f"  {t}: principal {n_p}, reserva {'(não existe)' if n_l is None else n_l}")
    print(f"{len(tabelas)} tabelas; {diferentes} com contagem diferente")
    return 1 if diferentes else 0


# ------------------------------------------------------------------ esquema

def diferenca_de_esquema(principal_col: dict, local_col: dict) -> tuple[list[str], list[tuple[str, str, str]]]:
    """(tabelas que faltam na reserva, [(tabela, coluna, tipo)] que faltam). Só o que FALTA: a
    réplica cai por coluna ausente, e não por coluna a mais (a versão velha que sobrou)."""
    faltam = sorted(t for t in principal_col if t not in local_col)
    colunas = [(t, col, tipo) for t, cols in sorted(principal_col.items()) if t in local_col
               for col, tipo in cols.items() if col not in local_col[t]]
    return faltam, colunas


def esquema(principal: str, local: str, schema: str, aplicar: bool) -> int:
    """Versão nova no principal = tabela ou coluna nova, que a réplica lógica não traz. Sem elas,
    a reserva PARA na primeira linha que as usa. Aqui elas entram — antes das linhas."""
    with _abrir(principal) as p, p.cursor() as cp, _abrir(local) as l, l.cursor() as cl:
        faltam, colunas = diferenca_de_esquema(_colunas(cp, schema), _colunas(cl, schema))
        if not faltam and not colunas:
            print("esquema igual ao do principal")
            return 0
        for t in faltam:
            print(f"  tabela nova: {t}")
        for t, col, tipo in colunas:
            print(f"  coluna nova: {t}.{col} ({tipo})")
        if not aplicar:
            print("(nada aplicado: use --aplicar)")
            return 1
        for t, col, tipo in colunas:
            # Sem DEFAULT nem NOT NULL: a linha chega pela réplica já com o valor.
            cl.execute(S.SQL("ALTER TABLE {}.{} ADD COLUMN IF NOT EXISTS {} " + tipo).format(
                S.Identifier(schema), S.Identifier(t), S.Identifier(col)))
    if faltam:
        dump = subprocess.run(
            [_binario("pg_dump"), "--schema-only", "--no-owner", "--no-privileges", "-d", principal]
            + [a for t in faltam for a in ("-t", f"{schema}.{t}")],
            capture_output=True, text=True, check=False)
        if dump.returncode != 0:
            sys.exit(f"pg_dump das tabelas novas falhou:\n{dump.stderr[-2000:]}")
        carga = subprocess.run([_binario("psql"), "-X", "-q", "-v", "ON_ERROR_STOP=1", "-d", local],
                               input=dump.stdout, capture_output=True, text=True, check=False)
        if carga.returncode != 0:
            sys.exit(f"a criação das tabelas novas falhou:\n{carga.stderr[-2000:]}")
    with _abrir(local) as l, l.cursor() as cl:
        _papel_de_leitura(cl, schema)
        if faltam and cl.execute("SELECT 1 FROM pg_subscription WHERE subname=%s", (ASSINATURA,)).fetchone():
            cl.execute(S.SQL("ALTER SUBSCRIPTION {} REFRESH PUBLICATION WITH (copy_data = true)").format(
                S.Identifier(ASSINATURA)))
    print("esquema acertado")
    return 0


# ------------------------------------------------------------------ assumir

def assumir(local: str, schema: str, confirmacao: str, principal_vivo: bool) -> int:
    """A reserva vira o principal. Sem volta pelo mesmo caminho: depois disto, o servidor
    Windows NÃO PODE voltar a lançar — dois principais dariam o mesmo número duas vezes."""
    if confirmacao != FRASE_DE_ASSUMIR:
        print(f"para assumir, repita com --confirmo {FRASE_DE_ASSUMIR}. Antes, confira:\n"
              "  1. o servidor Windows está DESLIGADO (ou o serviço do Cartório Gestão parado lá);\n"
              "  2. `reserva.py situacao` mostrava a réplica em dia antes da queda.")
        return 2
    with _abrir(local) as pg, pg.cursor() as c:
        s = ler_situacao(c)
        if s is not None:
            _largar_assinatura(c, principal_vivo=principal_vivo)
            print("assinatura desligada: a reserva não recebe mais nada do principal")
        acertadas = acertar_sequencias(c, schema)
    print(f"{acertadas} sequência(s) acertadas pelo maior id de cada tabela")
    print("agora troque o sistema da reserva para o modo principal: `assumir.sh` (roteiro, passo «assumir»)")
    return 0


def acertar_sequencias(c, schema: str) -> int:
    """O próximo id de cada tabela = o maior id + 1. A réplica lógica traz as linhas, e não as
    sequências: sem isto, o primeiro lançamento na reserva bateria num id que já existe."""
    c.execute("""SELECT n.nspname, k.relname, a.attname, pg_get_serial_sequence(format('%%I.%%I', n.nspname, k.relname), a.attname)
                   FROM pg_attribute a JOIN pg_class k ON k.oid = a.attrelid
                   JOIN pg_namespace n ON n.oid = k.relnamespace
                  WHERE n.nspname = %s AND k.relkind = 'r' AND a.attnum > 0 AND NOT a.attisdropped
                    AND pg_get_serial_sequence(format('%%I.%%I', n.nspname, k.relname), a.attname) IS NOT NULL""",
              (schema,))
    feitas = 0
    for nsp, tabela, coluna, sequencia in c.fetchall():
        c.execute(S.SQL("SELECT setval({}, greatest(coalesce((SELECT max({}) FROM {}.{}), 0), 1), "
                        "(SELECT max({}) FROM {}.{}) IS NOT NULL)").format(
            S.Literal(sequencia), S.Identifier(coluna), S.Identifier(nsp), S.Identifier(tabela),
            S.Identifier(coluna), S.Identifier(nsp), S.Identifier(tabela)))
        feitas += 1
    return feitas


# ------------------------------------------------------------------ as chaves (os segredos)

def _caminho_da_chave(dado: str | None) -> Path:
    valor = (dado or os.environ.get("CG_RESERVA_CHAVE") or "").strip()
    if not valor:
        sys.exit("falta o caminho da chave da reserva: --chave ou a variável CG_RESERVA_CHAVE")
    return Path(valor).expanduser()


def receber_chaves(local: str, schema: str, privada: Path, pasta_dados: Path) -> int:
    """Abre o pacote que o principal cifrou para esta reserva e grava os segredos na pasta de
    dados. Só regrava quando o pacote mudou (a impressão fica em `.reserva-impressao`)."""
    with _abrir(local) as pg, pg.cursor() as c:
        if c.execute("SELECT to_regclass(format('%%I.%%I', %s::text, %s::text))",
                     (schema, RCH.TABELA)).fetchone()[0] is None:
            print("chaves: o principal ainda não publicou o pacote (falta a chave pública lá: "
                  "roteiro, passo A2)")
            return 0
        linha = c.execute(S.SQL("SELECT impressao, pacote FROM {}.{} WHERE id = 1").format(
            S.Identifier(schema), S.Identifier(RCH.TABELA))).fetchone()
    if not linha:
        print("chaves: a tabela chegou, o pacote ainda não")
        return 0
    marca = pasta_dados / ".reserva-impressao"
    if marca.exists() and marca.read_text(encoding="ascii").strip() == linha[0]:
        print("chaves: em dia")
        return 0
    try:
        arquivos = RCH.decifrar(linha[1], privada)
    except ValueError as erro:
        print(f"chaves: {erro} — a pública no principal é a deste Mac? (`chave-da-reserva`)")
        return 1
    gravados = RCH.gravar(pasta_dados, arquivos)
    marca.write_text(linha[0] + "\n", encoding="ascii")
    print(f"chaves: {len(gravados)} arquivo(s) recebidos ({', '.join(gravados)})")
    return 0


# ------------------------------------------------------------------ as pastas fora dos arquivos

#: As pastas que o oficial escolhe em Configurações e que podem ficar FORA da pasta de arquivos.
#: O `backup_dir` fica de fora de propósito: o backup do principal é do banco do principal, e a
#: reserva tem o banco em dia pela réplica (copiar os backups dobraria o disco do Mac à toa).
PASTAS_DA_CONFIGURACAO = ("ri_pasta_matriculas_doc", "nt_pasta_firmas", "nt_pasta_export",
                          "gratuidade_pasta", "pastas_de_importacao")


def _normal(caminho: str) -> str:
    return caminho.strip().replace("/", "\\").rstrip("\\").lower()


def dentro_de(caminho: str, raiz: str) -> bool:
    """`caminho` (do Windows) fica em `raiz` ou abaixo dela? Sem diferença de maiúsculas."""
    c, r = _normal(caminho), _normal(raiz)
    return bool(r) and (c == r or c.startswith(r + "\\"))


def ler_mapa(texto: str) -> list[tuple[str, str]]:
    """`CG_RESERVA_SMB_PASTAS`: «C:\\Pasta=//usuario@ip/compartilhamento», separados por «;».
    A origem pode ser também uma pasta local (o ensaio usa assim)."""
    mapa = []
    for parte in re.split(r"[;\n]", texto or ""):
        raiz, sinal, origem = parte.strip().rpartition("=")
        if sinal and raiz.strip() and origem.strip():
            mapa.append((raiz.strip(), origem.strip()))
    # a raiz mais longa primeiro: «C:\\A\\B» ganha de «C:\\A»
    return sorted(mapa, key=lambda m: -len(_normal(m[0])))


def pastas_fora(config: dict[str, str], arquivos: str) -> list[tuple[str, str]]:
    """(chave, caminho) de cada pasta configurada fora da pasta de arquivos."""
    fora = []
    for chave in PASTAS_DA_CONFIGURACAO:
        for linha in (config.get(chave) or "").splitlines():
            linha = linha.strip()
            if linha and not (arquivos and dentro_de(linha, arquivos)):
                fora.append((chave, linha))
    return fora


def raiz_que_cobre(caminho: str, mapa: list[tuple[str, str]]) -> tuple[str, str] | None:
    return next((m for m in mapa if dentro_de(caminho, m[0])), None)


def destino_de(raiz: str, base: Path) -> Path:
    """Onde a cópia de `raiz` mora no Mac: «C:\\Matriculas» → <base>/C_Matriculas."""
    return base / (re.sub(r"[\\/:]+", "_", raiz.strip()).strip("_") or "raiz")


def _ler_config(c, schema: str) -> dict[str, str]:
    c.execute(S.SQL("SELECT key, value FROM {}.settings WHERE key = ANY(%s)").format(
        S.Identifier(schema)), (list(PASTAS_DA_CONFIGURACAO) + ["archive_root"],))
    return {k: v or "" for k, v in c.fetchall()}


def _montado(ponto: Path) -> bool:
    saida = subprocess.run(["mount"], capture_output=True, text=True, check=False).stdout
    return f" on {ponto} (" in saida


def copiar_pastas(local: str, schema: str, base: Path, mapa_texto: str) -> int:
    """Copia cada pasta configurada fora da pasta de arquivos, do compartilhamento dela para
    `<base>/<nome>`. Como a pasta de arquivos: só acrescenta e atualiza, nunca apaga."""
    with _abrir(local) as pg, pg.cursor() as c:
        config = _ler_config(c, schema)
    mapa = ler_mapa(mapa_texto)
    usadas: dict[str, str] = {}
    for chave, caminho in pastas_fora(config, config.get("archive_root", "")):
        m = raiz_que_cobre(caminho, mapa)
        if m is None:
            print(f"pastas: FALTA COMPARTILHAR {caminho} ({chave}) — ver o roteiro, passo B3")
        else:
            usadas[m[0]] = m[1]
    erros = 0
    for raiz, origem in usadas.items():
        destino = destino_de(raiz, base)
        destino.mkdir(parents=True, exist_ok=True)
        if origem.startswith("//"):
            ponto = base / ".montagens" / destino.name
            ponto.mkdir(parents=True, exist_ok=True)
            if not _montado(ponto):
                subprocess.run(["mount_smbfs", origem, str(ponto)], check=False)
            if not _montado(ponto):
                print(f"pastas: não montei {origem} ({raiz})")
                erros += 1
                continue
            fonte = ponto
        else:
            fonte = Path(origem)
        r = subprocess.run(["rsync", "-rt", "--partial", "--exclude", "~$*", "--exclude", "*.tmp",
                            f"{fonte}/", f"{destino}/"], capture_output=True, text=True, check=False)
        if r.returncode != 0:
            print(f"pastas: a cópia de {raiz} parou com erro: {r.stderr.strip()[-500:]}")
            erros += 1
        else:
            print(f"pastas: {raiz} em dia")
    return 1 if erros else 0


def apontar_pastas(local: str, schema: str, base: Path, mapa_texto: str) -> int:
    """No `assumir`: cada pasta configurada que tem cópia neste Mac passa a apontar para ela."""
    mapa = ler_mapa(mapa_texto)
    trocadas = 0
    with _abrir(local) as pg, pg.cursor() as c:
        for chave, valor in _ler_config(c, schema).items():
            if chave == "archive_root":
                continue
            linhas = []
            for linha in valor.splitlines():
                m = raiz_que_cobre(linha.strip(), mapa) if linha.strip() else None
                if m:
                    resto = linha.strip()[len(m[0].rstrip("\\/")):].replace("\\", "/").strip("/")
                    linha = str(destino_de(m[0], base) / resto) if resto else str(destino_de(m[0], base))
                linhas.append(linha)
            novo = "\n".join(linhas)
            if novo != valor:
                c.execute(S.SQL("UPDATE {}.settings SET value = %s WHERE key = %s").format(
                    S.Identifier(schema)), (novo, chave))
                trocadas += 1
    print(f"pastas: {trocadas} configuração(ões) apontadas para as cópias deste Mac")
    return 0


# ------------------------------------------------------------------ emergência e volta

FRASE_DE_EMERGENCIA = "EMERGENCIA"
FRASE_DE_VOLTA = "VOLTAR"
PUBLICAR = "insert, update, delete"


@dataclass(frozen=True)
class Retrato:
    """Uma tabela, dos dois lados: quantas linhas, o maior id, e o hash das linhas."""
    contagem: int
    max_id: int | None
    resumo: str


def confirmou_emergencia(frase: str) -> bool:
    return frase in {FRASE_DE_EMERGENCIA, FRASE_DE_ASSUMIR}


def executar_emergencia(*, confirmacao: str, principal_alcancavel: bool, tem_assinatura: bool,
                        travar_principal, desligar, despejar, promover) -> int:
    """A ordem que não deixa dois gravando.

    Se o principal responde, a trava de escrita vem primeiro (ela fica em `public`,
    fora da publicação). Depois a assinatura para, o despejo guarda a reserva como
    está, e só então as sequências avançam para ela poder lançar.
    """
    if not confirmou_emergencia(confirmacao):
        return 2
    if principal_alcancavel:
        travar_principal()
    if tem_assinatura:
        desligar()
    despejar()
    promover()
    return 0


def comparar(principal: dict[str, Retrato], reserva: dict[str, Retrato]) -> list[str]:
    """Onde a contagem, o maior id ou o hash não batem."""
    falhas = []
    for tabela in sorted(set(principal) | set(reserva)):
        a, b = principal.get(tabela), reserva.get(tabela)
        if a is None or b is None or a != b:
            falhas.append(tabela)
    return falhas


def tabelas_a_levar(principal: dict[str, Retrato], reserva: dict[str, Retrato]) -> list[str]:
    """Tabelas em que a reserva tem linha nova (id maior) ou conteúdo diferente."""
    return comparar(principal, reserva)


def executar_volta(*, confirmacao: str, principal: dict[str, Retrato],
                   reserva: dict[str, Retrato], copiar, reler, acertar,
                   remontar, soltar, remonta: bool) -> int:
    """Leva para o principal o que a reserva gravou. Só solta a trava se a conferência fecha.

    `reler` devolve os retratos depois da cópia. Divergência para aqui: a assinatura
    não religa e o principal continua somente leitura.
    """
    if confirmacao != FRASE_DE_VOLTA:
        return 2
    copiar(tabelas_a_levar(principal, reserva))
    falhas = comparar(*reler())
    if falhas:
        return 1
    acertar()
    if remonta:
        remontar()
    soltar()
    return 0


def _schema_valido(schema: str) -> str:
    nome = (schema or "").strip()
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", nome):
        raise ValueError("schema: só minúsculas, dígitos e _")
    return nome


def _tabela_valida(nome: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", nome):
        raise ValueError("tabela inválida")
    return nome


def sql_linhas_novas(schema: str, tabela: str, max_id: int) -> str:
    """As linhas cujo id a reserva criou depois que o principal parou."""
    schema, tabela = _schema_valido(schema), _tabela_valida(tabela)
    teto = int(max_id)
    return (f'COPY (SELECT * FROM "{schema}"."{tabela}" WHERE id > {teto}) TO STDOUT')


def comandos_de_remontar(principal_dsn: str) -> list[str]:
    """Recria a assinatura `cg_reserva` depois que as tabelas do principal foram recriadas.

    `copy_data = false`: a volta já levou as linhas. A assinatura só segue o que vier depois.
    A senha não entra na conexão (ela iria parar no catálogo da reserva).
    """
    if re.search(r"password\s*=", principal_dsn or "", re.I):
        raise ValueError("a senha não vai na conexão (use o pgpass)")
    if not principal_dsn or re.search(r"[\n;']", principal_dsn):
        raise ValueError("conexão inválida")
    return [
        f"ALTER SUBSCRIPTION {ASSINATURA} DISABLE",
        f"ALTER SUBSCRIPTION {ASSINATURA} SET (slot_name = NONE)",
        f"DROP SUBSCRIPTION IF EXISTS {ASSINATURA}",
        f"ALTER PUBLICATION {PUBLICACAO} SET (publish = '{PUBLICAR}')",
        (f"CREATE SUBSCRIPTION {ASSINATURA} CONNECTION '{principal_dsn}' "
         f"PUBLICATION {PUBLICACAO} "
         "WITH (copy_data = false, create_slot = true, disable_on_error = false)"),
        f"ALTER SUBSCRIPTION {ASSINATURA} ENABLE",
    ]


def desligar_assinatura(c) -> None:
    """Para a réplica sem apagar a assinatura. A volta ainda pode remontá-la."""
    c.execute(S.SQL("ALTER SUBSCRIPTION {} DISABLE").format(S.Identifier(ASSINATURA)))


def marcar_somente_leitura(c) -> None:
    for comando in CONT.sql_de_travar().split(";\n"):
        texto = comando.strip().rstrip(";")
        if texto:
            c.execute(texto)


def soltar_somente_leitura(c) -> None:
    c.execute(CONT.sql_de_soltar().rstrip(";"))


def comando_de_despejo(binario: str, dsn: str, schema: str, destino: Path) -> list[str]:
    if re.search(r"password\s*=", dsn or "", re.I):
        raise TRAVA.ProducaoProtegida("a senha não vai no pg_dump")
    _schema_valido(schema)
    return [binario, "--format=custom", "--no-password", "-n", schema, "-f", str(destino), dsn]


def retratos(c, schema: str) -> dict[str, Retrato]:
    """Contagem, maior id e hash das linhas de cada tabela do schema."""
    schema = _schema_valido(schema)
    c.execute("""SELECT k.relname FROM pg_class k
                   JOIN pg_namespace n ON n.oid = k.relnamespace
                  WHERE n.nspname = %s AND k.relkind = 'r' ORDER BY 1""", (schema,))
    nomes = [r[0] for r in c.fetchall()]
    saida: dict[str, Retrato] = {}
    for nome in nomes:
        _tabela_valida(nome)
        alvo = S.SQL("{}.{}").format(S.Identifier(schema), S.Identifier(nome))
        c.execute(S.SQL("SELECT count(*) FROM {}").format(alvo))
        contagem = int(c.fetchone()[0])
        c.execute("""SELECT 1 FROM information_schema.columns
                      WHERE table_schema = %s AND table_name = %s AND column_name = 'id'""",
                  (schema, nome))
        if c.fetchone():
            c.execute(S.SQL("SELECT max(id) FROM {}").format(alvo))
            bruto = c.fetchone()[0]
            max_id = None if bruto is None else int(bruto)
            c.execute(S.SQL("SELECT md5(coalesce(string_agg(md5(t::text), '' ORDER BY t.id), '')) "
                            "FROM {} AS t").format(alvo))
            resumo = c.fetchone()[0] or ""
        else:
            max_id = None
            c.execute(S.SQL("SELECT md5(count(*)::text) FROM {}").format(alvo))
            resumo = c.fetchone()[0] or ""
        saida[nome] = Retrato(contagem, max_id, resumo)
    return saida


def _principal_responde(principal: str) -> bool:
    try:
        with _abrir(principal) as pg, pg.cursor() as c:
            c.execute("SELECT 1")
        return True
    except Exception:  # noqa: BLE001 — inalcançável é o caso do botão
        return False


def _tem_assinatura(c) -> bool:
    return c.execute("SELECT 1 FROM pg_subscription WHERE subname=%s", (ASSINATURA,)).fetchone() is not None


def emergencia(local: str, principal: str, schema: str, confirmacao: str, destino: Path) -> int:
    """O botão. Não conecta no destino errado: a produção não é a reserva."""
    if not confirmou_emergencia(confirmacao):
        print(f"para a emergência, repita com --confirmo {FRASE_DE_EMERGENCIA}. "
              "O servidor Windows, se ainda responder, fica somente leitura.")
        return 2
    TRAVA.recusar_emergencia_no_principal(local, principal)
    schema = _schema_valido(schema)
    alcancavel = _principal_responde(principal)

    def travar() -> None:
        with _abrir(principal) as pg, pg.cursor() as c:
            marcar_somente_leitura(c)
        print("principal somente leitura")

    def desligar() -> None:
        with _abrir(local) as pg, pg.cursor() as c:
            desligar_assinatura(c)
        print("assinatura desligada")

    def despejar() -> None:
        destino.parent.mkdir(parents=True, exist_ok=True)
        argv = comando_de_despejo(_binario("pg_dump"), local, schema, destino)
        feito = subprocess.run(argv, capture_output=True, text=True, check=False)
        if feito.returncode != 0:
            raise SystemExit(f"o despejo da reserva falhou:\n{feito.stderr[-2000:]}")
        print(f"despejo em {destino}")

    def promover() -> None:
        with _abrir(local) as pg, pg.cursor() as c:
            n = acertar_sequencias(c, schema)
        print(f"{n} sequência(s) acertadas pelo maior id")
        print("troque o sistema da reserva para o modo principal: emergencia.sh (ou assumir.sh)")

    with _abrir(local) as pg, pg.cursor() as c:
        tem = _tem_assinatura(c)
    return executar_emergencia(
        confirmacao=confirmacao, principal_alcancavel=alcancavel, tem_assinatura=tem,
        travar_principal=travar, desligar=desligar, despejar=despejar, promover=promover)


def voltar(local: str, principal: str, schema: str, confirmacao: str, *, remonta: bool) -> int:
    """Devolve ao principal o que a reserva gravou, confere, e pode remontar a assinatura."""
    if confirmacao != FRASE_DE_VOLTA:
        print(f"para voltar, repita com --confirmo {FRASE_DE_VOLTA}. "
              "Nada é copiado sem essa frase.")
        return 2
    schema = _schema_valido(schema)

    def ler() -> tuple[dict[str, Retrato], dict[str, Retrato]]:
        with _abrir(principal) as p, p.cursor() as cp, _abrir(local) as r, r.cursor() as cr:
            return retratos(cp, schema), retratos(cr, schema)

    def copiar(tabelas: list[str]) -> None:
        if not tabelas:
            print("nada a copiar")
            return
        _copiar_tabelas(local, principal, schema, tabelas, principal_antes)

    principal_antes, reserva_antes = ler()
    return executar_volta(
        confirmacao=confirmacao, principal=principal_antes, reserva=reserva_antes,
        copiar=copiar, reler=ler, acertar=lambda: _acertar_no(principal, schema),
        remontar=lambda: _remontar(local, principal), soltar=lambda: _soltar(principal),
        remonta=remonta)


def _copiar_tabelas(local: str, principal: str, schema: str, tabelas: list[str],
                    antes: dict[str, Retrato]) -> None:
    with _abrir(local) as origem, origem.cursor() as co, _abrir(principal) as dest, dest.cursor() as cd:
        for tabela in tabelas:
            foto = antes.get(tabela)
            if foto is None or foto.max_id is None:
                print(f"  {tabela}: sem coluna id; a conferência acusa se o conteúdo divergir")
                continue
            pedacos = []
            with co.copy(sql_linhas_novas(schema, tabela, foto.max_id)) as copiado:
                while True:
                    bloco = copiado.read()
                    if not bloco:
                        break
                    pedacos.append(bloco)
            dados = b"".join(pedacos)
            if not dados:
                continue
            with cd.copy(f'COPY "{schema}"."{_tabela_valida(tabela)}" FROM STDIN') as gravar:
                gravar.write(dados)
            print(f"  {tabela}: linhas com id > {foto.max_id}")


def _acertar_no(dsn: str, schema: str) -> None:
    with _abrir(dsn) as pg, pg.cursor() as c:
        n = acertar_sequencias(c, schema)
    print(f"{n} sequência(s) acertadas no principal")


def _soltar(principal: str) -> None:
    with _abrir(principal) as pg, pg.cursor() as c:
        soltar_somente_leitura(c)
    print("principal pode gravar de novo")


def _remontar(local: str, principal: str) -> None:
    """Roda na reserva. A publicação no principal já tem de existir (sql-do-principal)."""
    for comando in comandos_de_remontar(principal):
        if comando.startswith("ALTER PUBLICATION"):
            try:
                with _abrir(principal) as pg, pg.cursor() as c:
                    c.execute(comando)
            except Exception as erro:  # noqa: BLE001 — publicação ausente: o SQL do principal a recria
                print(f"publicação não ajustada ({erro}). Rode antes `sql-do-principal` no Windows.")
            continue
        try:
            with _abrir(local) as pg, pg.cursor() as c:
                c.execute(comando)
        except Exception as erro:  # noqa: BLE001 — assinatura já caída: segue para recriar
            if comando.startswith("CREATE SUBSCRIPTION") or comando.startswith("ALTER SUBSCRIPTION") and "ENABLE" in comando:
                raise
            print(f"passo já feito ou sem assinatura antiga: {comando.split()[0]} ({erro})")
    print("assinatura cg_reserva recriada, sem copiar de novo as linhas já conferidas")


# ------------------------------------------------------------------ linha de comando

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--schema", default=os.environ.get("CG_PG_SCHEMA") or "producao")
    ap.add_argument("--principal", help="conexão do principal (ou CG_RESERVA_PRINCIPAL_DSN)")
    ap.add_argument("--local", help="conexão da reserva, como dono (ou CG_RESERVA_LOCAL_DSN)")
    sub = ap.add_subparsers(dest="comando", required=True)
    p = sub.add_parser("sql-do-principal")
    p.add_argument("--dono", default="cg", help="o dono das tabelas no principal")
    p.add_argument("--chave", help="a chave privada da reserva (ou CG_RESERVA_CHAVE): vai só a pública")
    p = sub.add_parser("chave-da-reserva")
    p.add_argument("--chave", help="onde fica a privada (ou CG_RESERVA_CHAVE)")
    p = sub.add_parser("chaves")
    p.add_argument("--chave", help="a privada da reserva (ou CG_RESERVA_CHAVE)")
    p.add_argument("--dados", help="a pasta de dados da reserva (ou CARTORIO_GESTAO_DATA)")
    p = sub.add_parser("pastas")
    p.add_argument("--base", help="onde ficam as cópias (ou CG_RESERVA_PASTAS)")
    p.add_argument("--apontar", action="store_true",
                   help="no assumir: as configurações passam a apontar para as cópias")
    p = sub.add_parser("montar")
    p.add_argument("--refazer", action="store_true", help="apaga a reserva e copia tudo de novo")
    sub.add_parser("situacao")
    sub.add_parser("conferir")
    p = sub.add_parser("esquema")
    p.add_argument("--aplicar", action="store_true")
    p = sub.add_parser("assumir")
    p.add_argument("--confirmo", default="")
    p.add_argument("--principal-vivo", action="store_true",
                   help="o principal está no ar (troca planejada): o slot de lá também se apaga")
    p = sub.add_parser("emergencia")
    p.add_argument("--confirmo", default="")
    p.add_argument("--dump", default="", help="arquivo do pg_dump da reserva")
    p = sub.add_parser("voltar")
    p.add_argument("--confirmo", default="")
    p.add_argument("--remontar", action="store_true",
                   help="recria a assinatura cg_reserva (tabelas do principal foram recriadas)")
    a = ap.parse_args(argv)

    if a.comando == "sql-do-principal":
        caminho = Path(a.chave or os.environ.get("CG_RESERVA_CHAVE") or "").expanduser()
        publica = RCH.publica_de(caminho) if str(caminho) not in {"", "."} and caminho.is_file() else ""
        sys.stdout.write(sql_do_principal(a.schema, a.dono, publica))
        return 0
    if a.comando == "chave-da-reserva":
        print(RCH.gerar_par(_caminho_da_chave(a.chave)))
        return 0
    local = _dsn("CG_RESERVA_LOCAL_DSN", a.local)
    if a.comando == "situacao":
        return situacao(local)
    if a.comando == "assumir":
        return assumir(local, a.schema, a.confirmo, a.principal_vivo)
    if a.comando == "emergencia":
        principal = _dsn("CG_RESERVA_PRINCIPAL_DSN", a.principal)
        pasta = (a.dump or os.environ.get("CARTORIO_GESTAO_DATA") or "").strip()
        if not pasta:
            sys.exit("falta onde guardar o despejo: --dump ou CARTORIO_GESTAO_DATA")
        destino = Path(pasta)
        if destino.suffix.lower() not in {".dump", ".backup"}:
            destino = destino / "contingencia" / "reserva.dump"
        try:
            return emergencia(local, principal, a.schema, a.confirmo, destino)
        except TRAVA.ProducaoProtegida as erro:
            print(f"Recuso: {erro}", file=sys.stderr)
            return 2
    if a.comando == "voltar":
        principal = _dsn("CG_RESERVA_PRINCIPAL_DSN", a.principal)
        try:
            return voltar(local, principal, a.schema, a.confirmo, remonta=a.remontar)
        except TRAVA.ProducaoProtegida as erro:
            print(f"Recuso: {erro}", file=sys.stderr)
            return 2
    if a.comando == "chaves":
        dados = (a.dados or os.environ.get("CARTORIO_GESTAO_DATA") or "").strip()
        if not dados:
            sys.exit("falta a pasta de dados: --dados ou CARTORIO_GESTAO_DATA")
        return receber_chaves(local, a.schema, _caminho_da_chave(a.chave), Path(dados).expanduser())
    if a.comando == "pastas":
        base = (a.base or os.environ.get("CG_RESERVA_PASTAS") or "").strip()
        if not base:
            sys.exit("falta onde ficam as cópias: --base ou CG_RESERVA_PASTAS")
        mapa = os.environ.get("CG_RESERVA_SMB_PASTAS", "")
        if a.apontar:
            return apontar_pastas(local, a.schema, Path(base).expanduser(), mapa)
        return copiar_pastas(local, a.schema, Path(base).expanduser(), mapa)
    principal = _dsn("CG_RESERVA_PRINCIPAL_DSN", a.principal)
    if a.comando == "montar":
        try:
            montar(principal, local, a.schema, a.refazer)
        except TRAVA.ProducaoProtegida as erro:
            print(f"Recuso: {erro}", file=sys.stderr)
            return 2
        return 0
    if a.comando == "conferir":
        return conferir(principal, local, a.schema)
    if a.comando == "esquema":
        return esquema(principal, local, a.schema, a.aplicar)
    return 2


if __name__ == "__main__":
    sys.exit(main())
