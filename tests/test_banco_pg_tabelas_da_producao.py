"""As 20 tabelas da produção que a subida do código não criava — lote LH09, 21/10/2026.

O QUE SE MEDIU (só a estrutura, no Mac, sobre o banco real da produção)
    `relatorios/COMPARACAO_SQLITE_REAL.md`: 20 tabelas do SQLite da produção,
    com dados, não existiam no esquema que `create_app` cria no PostgreSQL —
    cp_* (compliance), ge_* (gestor), mt_* (malote), rc_leituras, ri_onus_sugestoes
    e rv_* (revisão), e `_ping`, vazia. Cada módulo dono criava a sua tabela
    PREGUIÇOSO, na primeira vez que a função rodava; a subida não as criava, e a
    carga da virada não tinha onde pôr as linhas com o tipo que o código grava.

O QUE ESTES TESTES GUARDAM
    - depois da subida num banco vazio, as 19 do sistema existem com as colunas,
      as chaves únicas e os índices do CREATE TABLE da produção, e com tipo PG
      coerente (INTEGER → inteiro, REAL → double precision, TEXT → text);
      coluna que o código tem a mais aceita a linha da produção (NULL ou padrão);
    - `_ping` não nasce: não é do sistema (nenhum código a cria) — a conferência
      da carga a ignora com aviso;
    - a carga das linhas da produção cabe nas tabelas da subida, e a conferência
      fecha;
    - cada módulo dono grava e lê uma linha no PostgreSQL SEM rodar o próprio
      esquema (ele fica desligado no teste): a tabela que ele usa é a da subida.

O ESQUEMA DA PRODUÇÃO vem de `relatorios/ESTRUTURA_TABELAS_FALTANDO.md`, igual,
menos a numeração sem reuso do SQLite (não muda coluna nem tipo). As linhas são
de exemplo, sem dado de pessoa.
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import banco_pg  # noqa: E402
from bd_nativo import banco  # noqa: E402

pytestmark = pytest.mark.skipif(not banco_pg.ativo(),
                                reason="a subida que cria as tabelas é a do PostgreSQL")

AGORA = "2026-10-21T07:30:00"

ESQUEMA_DA_PRODUCAO = """
CREATE TABLE _ping(x);

CREATE TABLE cp_achados (
    id INTEGER PRIMARY KEY,
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
);
CREATE INDEX ix_cp_achados_abertos ON cp_achados (resolvido_em, area);

CREATE TABLE cp_execucoes (
    id INTEGER PRIMARY KEY,
    iniciada_em TEXT NOT NULL,
    terminada_em TEXT,
    achados INTEGER,
    novos INTEGER,
    resolvidos INTEGER,
    criticos INTEGER,
    nao_mediu INTEGER,
    relatorio TEXT,
    tarefa_id INTEGER,
    erro TEXT
);

CREATE TABLE cp_fotografias (
    chave TEXT PRIMARY KEY,
    valor TEXT,
    tirada_em TEXT NOT NULL
);

CREATE TABLE cp_mudancas (
    id INTEGER PRIMARY KEY,
    chave TEXT NOT NULL,
    antes TEXT,
    depois TEXT,
    vista_em TEXT NOT NULL,
    com_rastro INTEGER NOT NULL DEFAULT 0,
    UNIQUE (chave, vista_em)
);

CREATE TABLE ge_achados (
    id INTEGER PRIMARY KEY,
    chave TEXT NOT NULL UNIQUE,
    regra TEXT NOT NULL,
    gravidade TEXT NOT NULL,
    setor TEXT NOT NULL,
    titulo TEXT NOT NULL,
    detalhe TEXT,
    prazo TEXT,
    fundamento TEXT,
    primeiro_visto_em TEXT NOT NULL,
    ultimo_visto_em TEXT NOT NULL,
    resolvido_em TEXT,
    revisado_em TEXT,
    revisado_por TEXT,
    revisao TEXT
);
CREATE INDEX ix_ge_achados_abertos
    ON ge_achados (resolvido_em, regra);

CREATE TABLE ge_envios (
    id INTEGER PRIMARY KEY,
    central TEXT NOT NULL,
    competencia TEXT,
    referencia TEXT,
    canal TEXT NOT NULL DEFAULT 'PORTAL',
    situacao TEXT NOT NULL DEFAULT 'ENVIADO',
    protocolo TEXT,
    recibo_caminho TEXT,
    quantos INTEGER,
    mensagem TEXT,
    enviado_em TEXT NOT NULL,
    registrado_em TEXT NOT NULL,
    registrado_por TEXT NOT NULL,
    origem TEXT NOT NULL DEFAULT 'BALCAO'
);
CREATE INDEX ix_ge_envios_central
    ON ge_envios (central, competencia, referencia);

CREATE TABLE ge_execucoes (
    id INTEGER PRIMARY KEY,
    iniciada_em TEXT NOT NULL,
    terminada_em TEXT,
    hoje TEXT NOT NULL,
    achados INTEGER,
    novos INTEGER,
    resolvidos INTEGER,
    tarefas_criadas INTEGER,
    tarefas_fechadas INTEGER,
    tarefas_cobradas INTEGER,
    nao_mediu INTEGER,
    relatorio TEXT,
    erro TEXT
);

CREATE TABLE ge_leituras (
    id INTEGER PRIMARY KEY,
    tabela TEXT NOT NULL,
    ato_id INTEGER NOT NULL,
    hash_dossie TEXT NOT NULL,
    lido_em TEXT NOT NULL,
    provedor TEXT,
    modelo TEXT,
    achados_json TEXT,
    erro TEXT,
    tokens_entrada INTEGER,
    tokens_saida INTEGER,
    revisado_em TEXT,
    revisado_por TEXT,
    UNIQUE(tabela, ato_id, hash_dossie)
);

CREATE TABLE ge_onr_cargas (
    id INTEGER PRIMARY KEY,
    canal TEXT NOT NULL,              -- IMAGENS | PESSOAL | REAL
    tipo TEXT NOT NULL,               -- COMPLETA | INCREMENTAL | RODADA
    periodo_de TEXT,
    periodo_ate TEXT,
    arquivo TEXT,
    sha256 TEXT,
    quantos INTEGER,
    situacao TEXT NOT NULL,           -- PREPARADO | NA_PASTA | PROCESSADO | SUBSTITUIDO | OK | ERRO
    gerado_em TEXT NOT NULL,
    processado_em TEXT,
    detalhe TEXT
);
CREATE INDEX ix_ge_onr_cargas_canal
    ON ge_onr_cargas (canal, tipo, situacao);

CREATE TABLE ge_responsaveis (
    setor TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    origem TEXT NOT NULL DEFAULT 'INFERIDO',
    definido_em TEXT NOT NULL,
    definido_por TEXT NOT NULL,
    substituto_id INTEGER,
    rodizio INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE ge_triagens (
    id INTEGER PRIMARY KEY,
    expediente_id INTEGER NOT NULL,
    hash_dossie TEXT NOT NULL,
    lido_em TEXT NOT NULL,
    provedor TEXT,
    modelo TEXT,
    resultado_json TEXT,
    erro TEXT,
    tarefa_id INTEGER,
    UNIQUE (expediente_id, hash_dossie)
);

CREATE TABLE mt_alertas_propostos (
    id INTEGER PRIMARY KEY,
    nome TEXT,
    documento TEXT,
    papel TEXT NOT NULL,
    trecho TEXT,                 -- a frase do documento que justifica
    -- A REFERÊNCIA DO AVISO, inteira (pedido do oficial, 13/10/2026)
    codigo_malote TEXT,
    documento_malote TEXT,       -- o nome do PDF no malote
    assunto TEXT,
    remetente TEXT,
    enviado_em TEXT,
    processos TEXT,              -- os números de processo citados, separados por «; »
    arquivo TEXT,                -- onde o PDF está guardado nesta casa
    resumo TEXT,                 -- o que a comunicação diz
    situacao TEXT NOT NULL DEFAULT 'PROPOSTO',
    revisado_por TEXT,
    revisado_em TEXT,
    motivo TEXT,                 -- por que se descartou, quando se descartou
    alerta_id INTEGER,           -- fr_alertas.id, depois de aplicada
    criado_em TEXT NOT NULL,
    UNIQUE (codigo_malote, nome, documento, papel)
);

CREATE TABLE mt_arquivos (
    id INTEGER PRIMARY KEY,
    sha256 TEXT NOT NULL UNIQUE,
    caminho TEXT NOT NULL,
    visto_em TEXT NOT NULL,
    situacao TEXT NOT NULL,
    expediente_id INTEGER,
    nota TEXT
);

CREATE TABLE mt_execucoes (
    id INTEGER PRIMARY KEY,
    iniciada_em TEXT NOT NULL,
    terminada_em TEXT,
    confirmou INTEGER NOT NULL DEFAULT 0,
    resumo_json TEXT,
    erro TEXT
);

CREATE TABLE mt_fraude_leituras (
    id INTEGER PRIMARY KEY,
    grupo TEXT NOT NULL,             -- o arquivo ou a subpasta do malote
    codigo_malote TEXT,
    hash_texto TEXT NOT NULL,
    lido_em TEXT NOT NULL,
    provedor TEXT,
    modelo TEXT,
    tokens_entrada INTEGER,
    tokens_saida INTEGER,
    resultado_json TEXT,
    erro TEXT
);

CREATE TABLE rc_leituras (
    id INTEGER PRIMARY KEY,
    especie TEXT NOT NULL,
    situacao TEXT NOT NULL DEFAULT 'LIDA',   -- LIDA | FALHOU | NO_RASCUNHO
    arquivos_json TEXT NOT NULL,             -- [{attachment_id, nome, sha256}]
    paginas_json TEXT,                       -- triagem: [{arquivo, n, tipo}]
    documentos_json TEXT,                    -- o que cada página disse
    registro_json TEXT,                      -- o registro no padrão da casa
    conferencia_json TEXT,                   -- o que não fecha, e onde
    envios_json TEXT,                        -- o que saiu, a que modelo, quanto
    custo_estimado REAL,
    erro TEXT,
    rascunho_id INTEGER,
    criada_em TEXT NOT NULL,
    criada_por TEXT,
    rascunho_em TEXT,
    rascunho_por TEXT
);

CREATE TABLE ri_onus_sugestoes (
    id INTEGER PRIMARY KEY,
    matricula_id INTEGER NOT NULL,
    hash_ficha TEXT NOT NULL,
    dossie TEXT NOT NULL,
    situacao TEXT NOT NULL DEFAULT 'PENDENTE',   -- PENDENTE | LENDO | PRONTA | ERRO
    pedido_em TEXT NOT NULL,
    pedido_por TEXT,
    terminado_em TEXT,
    provedor TEXT,
    modelo TEXT,
    resultado_json TEXT,
    erro TEXT,
    tokens_entrada INTEGER,
    tokens_saida INTEGER
);
CREATE INDEX ix_ri_onus_sugestoes_matricula
    ON ri_onus_sugestoes (matricula_id, hash_ficha);

CREATE TABLE rv_anexos_lidos (
    sha256 TEXT PRIMARY KEY,
    nome TEXT,
    paginas INTEGER,
    paginas_texto INTEGER,
    paginas_imagem INTEGER,
    tipo TEXT,
    importante INTEGER,
    motivo TEXT,
    transcricao TEXT,
    paginas_lidas INTEGER,
    situacao TEXT NOT NULL,            -- LIDO | TRIADO | ERRO
    modelo TEXT,
    tokens_entrada INTEGER NOT NULL DEFAULT 0,
    tokens_saida INTEGER NOT NULL DEFAULT 0,
    lido_em TEXT,
    erro TEXT
);

CREATE TABLE rv_revisoes (
    id INTEGER PRIMARY KEY,
    atribuicao TEXT NOT NULL,          -- RI | NOTAS
    alvo_id INTEGER NOT NULL,          -- matrícula (RI) ou nt_atos.id (Notas)
    hash_texto TEXT NOT NULL,
    rotulo TEXT,
    dossie TEXT NOT NULL,
    situacao TEXT NOT NULL DEFAULT 'PENDENTE',   -- PENDENTE | LENDO | PRONTA | ERRO
    pedido_em TEXT NOT NULL,
    pedido_por TEXT,
    terminado_em TEXT,
    provedor TEXT,
    modelo TEXT,
    resultado_json TEXT,
    graves INTEGER NOT NULL DEFAULT 0,
    erro TEXT,
    tokens_entrada INTEGER,
    tokens_saida INTEGER,
    justificativa TEXT,
    justificado_por TEXT,
    justificado_em TEXT,
    origem TEXT NOT NULL DEFAULT 'BALCAO'        -- BALCAO | AGENTE (revisão em lote)
, anexos_origem TEXT, anexos_assinatura TEXT, anexos_json TEXT, aviso_anexos TEXT, tokens_anexos INTEGER);
CREATE INDEX ix_rv_revisoes_alvo
    ON rv_revisoes (atribuicao, alvo_id, hash_texto);
"""

#: As chaves únicas de cada uma (a primária e as UNIQUE), na ordem das colunas.
UNICAS_DA_PRODUCAO = {
    "cp_achados": {("id",), ("chave",)},
    "cp_execucoes": {("id",)},
    "cp_fotografias": {("chave",)},
    "cp_mudancas": {("id",), ("chave", "vista_em")},
    "ge_achados": {("id",), ("chave",)},
    "ge_envios": {("id",)},
    "ge_execucoes": {("id",)},
    "ge_leituras": {("id",), ("tabela", "ato_id", "hash_dossie")},
    "ge_onr_cargas": {("id",)},
    "ge_responsaveis": {("setor",)},
    "ge_triagens": {("id",), ("expediente_id", "hash_dossie")},
    "mt_alertas_propostos": {("id",), ("codigo_malote", "nome", "documento", "papel")},
    "mt_arquivos": {("id",), ("sha256",)},
    "mt_execucoes": {("id",)},
    "mt_fraude_leituras": {("id",)},
    "rc_leituras": {("id",)},
    "ri_onus_sugestoes": {("id",)},
    "rv_anexos_lidos": {("sha256",)},
    "rv_revisoes": {("id",)},
}

#: O tipo do SQLite e os tipos PG que guardam o mesmo valor sem perder nada
#: (REAL em `real`/float4 perderia o centavo de valor grande).
TIPO_PG = {"INTEGER": {"integer", "bigint"}, "TEXT": {"text"}, "REAL": {"double precision"}}

#: Uma linha de exemplo por tabela, com os tipos da produção (o REAL com
#: centavo acima de 131.072, onde o float4 já arredonda).
LINHAS_DA_PRODUCAO = {
    "cp_achados": dict(id=11, chave="GESTOR:parado", area="AGENTES", regra="GESTOR_EXECUCAO",
                       gravidade="CRITICO", titulo="O gestor não conferiu a casa",
                       detalhe="Nenhuma rodada.", evidencia="ge_execucoes.iniciada_em",
                       fundamento="", o_que_fazer="Ligar o gestor.",
                       primeiro_visto_em=AGORA, ultimo_visto_em=AGORA, resolvido_em=None),
    "cp_execucoes": dict(id=12, iniciada_em=AGORA, terminada_em=AGORA, achados=3, novos=1,
                         resolvidos=0, criticos=1, nao_mediu=0,
                         relatorio="compliance_2026-10-21.html", tarefa_id=70, erro=None),
    "cp_fotografias": dict(chave="settings.exemplo", valor="1", tirada_em=AGORA),
    "cp_mudancas": dict(id=13, chave="settings.exemplo", antes="0", depois="1",
                        vista_em=AGORA, com_rastro=1),
    "ge_achados": dict(id=14, chave="IBGE:2026-T3", regra="ENVIO", gravidade="ATENCAO",
                       setor="RCPN", titulo="IBGE do 3º trimestre", detalhe="", prazo="2026-10-31",
                       fundamento="Lei 6.015/1973, art. 49", primeiro_visto_em=AGORA,
                       ultimo_visto_em=AGORA, resolvido_em=None, revisado_em=None,
                       revisado_por=None, revisao=None),
    "ge_envios": dict(id=15, central="IBGE", competencia="2026-T3", referencia=None,
                      canal="PORTAL", situacao="ENVIADO", protocolo="IBGE-EXEMPLO-1",
                      recibo_caminho=None, quantos=1, mensagem=None, enviado_em=AGORA,
                      registrado_em=AGORA, registrado_por="mario", origem="BALCAO"),
    "ge_execucoes": dict(id=16, iniciada_em=AGORA, terminada_em=AGORA, hoje="2026-10-21",
                         achados=40, novos=2, resolvidos=1, tarefas_criadas=2,
                         tarefas_fechadas=1, tarefas_cobradas=0, nao_mediu=0,
                         relatorio="conferencia_2026-10-21.html", erro=None),
    "ge_leituras": dict(id=17, tabela="ri_atos", ato_id=9001, hash_dossie="a" * 64,
                        lido_em=AGORA, provedor="claude", modelo="modelo-de-exemplo",
                        achados_json="[]", erro=None, tokens_entrada=1200, tokens_saida=80,
                        revisado_em=None, revisado_por=None),
    "ge_onr_cargas": dict(id=18, canal="PESSOAL", tipo="COMPLETA", periodo_de="2026-01-01",
                          periodo_ate="2026-09-30", arquivo="carga_exemplo.xml",
                          sha256="b" * 64, quantos=12, situacao="PROCESSADO",
                          gerado_em=AGORA, processado_em=AGORA, detalhe=None),
    "ge_responsaveis": dict(setor="RCPN", user_id=2, origem="DEFINIDO", definido_em=AGORA,
                            definido_por="mario", substituto_id=3, rodizio=1),
    "ge_triagens": dict(id=19, expediente_id=5, hash_dossie="c" * 64, lido_em=AGORA,
                        provedor="claude", modelo="modelo-de-exemplo",
                        resultado_json='{"tipo": "CIENCIA"}', erro=None, tarefa_id=None),
    "mt_alertas_propostos": dict(
        id=20, nome="FULANO DE TAL EXEMPLO", documento="00000004421", papel="VITIMA",
        trecho="documento de exemplo", codigo_malote="2026000001",
        documento_malote="aviso_exemplo.pdf", assunto="Aviso de exemplo",
        remetente="Vara de exemplo", enviado_em="2026-10-20", processos="0000000-00.2026.8.10.0001",
        arquivo="malote/aviso_exemplo.pdf", resumo="Comunicação de exemplo.",
        situacao="PROPOSTO", revisado_por=None, revisado_em=None, motivo=None,
        alerta_id=None, criado_em=AGORA),
    "mt_arquivos": dict(id=21, sha256="d" * 64, caminho="malote/aviso_exemplo.pdf",
                        visto_em=AGORA, situacao="CADASTRADO", expediente_id=5, nota=None),
    "mt_execucoes": dict(id=22, iniciada_em=AGORA, terminada_em=AGORA, confirmou=1,
                         resumo_json="{}", erro=None),
    "mt_fraude_leituras": dict(id=23, grupo="aviso_exemplo.pdf", codigo_malote="2026000001",
                               hash_texto="e" * 64, lido_em=AGORA, provedor="claude",
                               modelo="modelo-de-exemplo", tokens_entrada=900,
                               tokens_saida=60, resultado_json="{}", erro=None),
    "rc_leituras": dict(id=24, especie="NASCIMENTO", situacao="LIDA", arquivos_json="[]",
                        paginas_json="[]", documentos_json="[]", registro_json="{}",
                        conferencia_json="[]", envios_json="[]", custo_estimado=131072.37,
                        erro=None, rascunho_id=None, criada_em=AGORA, criada_por="mario",
                        rascunho_em=None, rascunho_por=None),
    "ri_onus_sugestoes": dict(id=25, matricula_id=9001, hash_ficha="f" * 64,
                              dossie="dossiê de exemplo", situacao="PRONTA", pedido_em=AGORA,
                              pedido_por="mario", terminado_em=AGORA, provedor="claude",
                              modelo="modelo-de-exemplo", resultado_json="{}", erro=None,
                              tokens_entrada=3000, tokens_saida=200),
    "rv_anexos_lidos": dict(sha256="9" * 64, nome="titulo_exemplo.pdf", paginas=3,
                            paginas_texto=2, paginas_imagem=1, tipo="escritura", importante=1,
                            motivo="fundamenta o ato", transcricao="[página 1] exemplo",
                            paginas_lidas=3, situacao="LIDO", modelo="modelo-de-exemplo",
                            tokens_entrada=500, tokens_saida=900, lido_em=AGORA, erro=None),
    "rv_revisoes": dict(id=26, atribuicao="NOTAS", alvo_id=901, hash_texto="1" * 64,
                        rotulo="Escritura de exemplo", dossie="=== ATO A LAVRAR ===\nexemplo",
                        situacao="PRONTA", pedido_em=AGORA, pedido_por="mario",
                        terminado_em=AGORA, provedor="claude", modelo="modelo-de-exemplo",
                        resultado_json='{"achados": [], "parecer": "ok"}', graves=0, erro=None,
                        tokens_entrada=4000, tokens_saida=300, justificativa=None,
                        justificado_por=None, justificado_em=None, origem="BALCAO",
                        anexos_origem=None, anexos_assinatura=None, anexos_json=None,
                        aviso_anexos=None, tokens_anexos=None),
}


# ------------------------------------------------------------ o esquema da produção

def _corpos() -> dict[str, str]:
    """O corpo de cada CREATE TABLE do esquema da produção (sem os comentários:
    o de `mt_alertas_propostos.processos` tem um «;»)."""
    sem_comentario = re.sub(r"--[^\n]*", "", ESQUEMA_DA_PRODUCAO)
    return dict(re.findall(r"CREATE TABLE (\w+)\s*\(([^;]*)\)\s*;", sem_comentario))


def _colunas_da_producao(corpo: str) -> tuple[dict[str, str], set[str]]:
    """({coluna: tipo do SQLite}, colunas NOT NULL ou chave primária)."""
    tipos, obrigatorias = {}, set()
    for linha in corpo.splitlines():
        for pedaco in linha.split("--")[0].split(","):
            m = re.match(r"\s*(\w+)\s+(INTEGER|TEXT|REAL)\b(.*)", pedaco)
            if m:
                tipos[m[1]] = m[2]
                if "NOT NULL" in m[3] or "PRIMARY KEY" in m[3]:
                    obrigatorias.add(m[1])
    return tipos, obrigatorias


def _indices_da_producao() -> dict[str, tuple[str, str]]:
    return {nome: (tabela, " ".join(colunas.split()))
            for nome, tabela, colunas in re.findall(
                r"CREATE INDEX (\w+)\s+ON (\w+) \(([^)]*)\)", ESQUEMA_DA_PRODUCAO)}


DO_SISTEMA = sorted(t for t in _corpos() if t != "_ping")


def _arquivo_da_producao(pasta: Path) -> Path:
    """O SQLite com o esquema da produção e uma linha de exemplo em cada tabela
    (a `_ping` fica vazia, como lá)."""
    arquivo = pasta / "copia_da_producao.sqlite3"
    sq = banco_pg._CONNECT_ORIGINAL(arquivo)
    try:
        sq.executescript(ESQUEMA_DA_PRODUCAO)
        for tabela, linha in LINHAS_DA_PRODUCAO.items():
            sq.execute(f"INSERT INTO {tabela} ({', '.join(linha)}) "
                       f"VALUES ({', '.join(':' + c for c in linha)})", linha)
        sq.commit()
    finally:
        sq.close()
    return arquivo


# ------------------------------------------------------------ o que o PG tem

def _colunas_no_pg(bd, tabela: str) -> dict[str, dict]:
    return {r["column_name"]: r for r in bd.ler(
        """SELECT column_name, data_type, is_nullable, column_default, is_identity
             FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = %s
            ORDER BY ordinal_position""", (tabela,))}


def _unicas_no_pg(bd, tabela: str) -> set[tuple[str, ...]]:
    linhas = bd.ler(
        """SELECT x.indexrelid AS indice, a.attname AS coluna, k.n AS ordem
             FROM pg_index x
             JOIN LATERAL unnest(x.indkey) WITH ORDINALITY AS k(attnum, n) ON true
             JOIN pg_attribute a ON a.attrelid = x.indrelid AND a.attnum = k.attnum
            WHERE x.indrelid = to_regclass(%s) AND x.indisunique
            ORDER BY x.indexrelid, k.n""", (tabela,))
    por_indice: dict = {}
    for r in linhas:
        por_indice.setdefault(r["indice"], []).append(r["coluna"])
    return {tuple(c) for c in por_indice.values()}


def _indice_no_pg(bd, nome: str) -> str | None:
    return bd.valor("SELECT indexdef FROM pg_indexes WHERE schemaname = current_schema() "
                    "AND indexname = %s", (nome,))


@pytest.fixture()
def con(cg_casa):
    """A conexão (da ponte, como a da rota) com o banco que `create_app` criou
    num DATA_DIR vazio — o `cg_casa`."""
    c = sqlite3.connect(cg_casa["banco"])
    try:
        yield c
    finally:
        c.close()


@pytest.fixture()
def bd(con):
    return banco(con)


# ------------------------------------------------------------ a subida

def test_a_lista_do_teste_e_a_do_relatorio_da_producao():
    assert len(DO_SISTEMA) == 19 and set(DO_SISTEMA) == set(LINHAS_DA_PRODUCAO)
    assert set(DO_SISTEMA) == set(UNICAS_DA_PRODUCAO)


def test_depois_da_subida_num_banco_vazio_as_19_existem_com_as_colunas_da_producao(bd):
    faltam, tipo_errado, recusaria = {}, {}, {}
    for tabela, corpo in _corpos().items():
        if tabela == "_ping":
            continue
        tipos, obrigatorias = _colunas_da_producao(corpo)
        no_pg = _colunas_no_pg(bd, tabela)
        assert no_pg, f"a subida não criou {tabela}"
        if set(tipos) - set(no_pg):
            faltam[tabela] = sorted(set(tipos) - set(no_pg))
        for coluna, tipo in tipos.items():
            if coluna in no_pg and no_pg[coluna]["data_type"] not in TIPO_PG[tipo]:
                tipo_errado[f"{tabela}.{coluna}"] = (tipo, no_pg[coluna]["data_type"])
        # A LINHA DA PRODUÇÃO TEM DE CABER: coluna obrigatória no PG que lá
        # aceitava NULL (ou que lá nem existe, sem padrão) recusaria a carga.
        for coluna, c in no_pg.items():
            obrigatoria = c["is_nullable"] == "NO" and c["column_default"] is None \
                and c["is_identity"] != "YES"
            if obrigatoria and coluna not in obrigatorias:
                recusaria[f"{tabela}.{coluna}"] = "NOT NULL no PG e não na produção"
    assert faltam == {}, faltam
    assert tipo_errado == {}, tipo_errado
    assert recusaria == {}, recusaria


def test_as_chaves_unicas_sao_as_da_producao_nem_mais_nem_menos(bd):
    """Faltar chave deixa entrar repetido; sobrar recusaria linha da produção."""
    diferentes = {t: {"producao": sorted(u), "pg": sorted(_unicas_no_pg(bd, t))}
                  for t, u in UNICAS_DA_PRODUCAO.items() if _unicas_no_pg(bd, t) != u}
    assert diferentes == {}, diferentes


def test_os_indices_da_producao_existem_com_o_mesmo_nome_e_as_mesmas_colunas(bd):
    indices = _indices_da_producao()
    assert len(indices) == 6
    for nome, (tabela, colunas) in indices.items():
        definicao = _indice_no_pg(bd, nome)
        assert definicao is not None, f"falta o índice {nome}"
        assert f" ON {bd.valor('SELECT current_schema()')}.{tabela} " in definicao, definicao
        assert definicao.endswith(f"({colunas})"), definicao


def test_ping_nao_e_do_sistema_e_a_subida_nao_a_cria(bd):
    assert not bd.tem_tabela("_ping")
    assert "_ping" in banco_pg.TABELAS_FORA_DA_CARGA
    # nenhum código a cria, nem na raiz nem nas ferramentas
    cria = re.compile(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[\"']?_ping\b", re.I)
    criam = sorted(str(p.relative_to(RAIZ)) for p in [*RAIZ.glob("*.py"), *RAIZ.glob("tools/*.py")]
                   if cria.search(p.read_text(encoding="utf-8", errors="replace")))
    assert criam == [], criam


# ------------------------------------------------------------ a carga

def _carregar(arquivo: Path, con) -> None:
    """A carga num banco que o código já subiu: cada tabela do arquivo recebe as
    linhas pelas colunas que existem dos dois lados. A `_ping` fica de fora,
    como a conferência manda; tabela do sistema que falta é defeito."""
    bd = banco(con)
    sq = banco_pg._CONNECT_ORIGINAL(arquivo)
    try:
        for tabela in _corpos():
            if tabela in banco_pg.TABELAS_FORA_DA_CARGA:
                continue
            assert bd.tem_tabela(tabela), f"a subida não criou {tabela}: a carga não tem onde pôr"
            tem = set(_colunas_no_pg(bd, tabela))
            cursor = sq.execute(f"SELECT * FROM {tabela} ORDER BY 1")
            colunas = [d[0] for d in cursor.description if d[0] in tem]
            for linha in cursor.fetchall():
                valores = dict(zip([d[0] for d in cursor.description], linha))
                bd.escrever(f"INSERT INTO {tabela} ({', '.join(colunas)}) "
                            f"VALUES ({', '.join(['%s'] * len(colunas))})",
                            [valores[c] for c in colunas])
        con.commit()
    finally:
        sq.close()


def test_a_carga_da_producao_cabe_nas_tabelas_da_subida_e_a_conferencia_fecha(
        cg_casa, con, bd, tmp_path):
    arquivo = _arquivo_da_producao(tmp_path)
    _carregar(arquivo, con)
    feito = banco_pg.conferir_carga_de_sqlite(arquivo, cg_casa["banco"])
    assert feito["ok"], feito
    assert feito["tabelas_ignoradas"] == {"_ping": banco_pg.TABELAS_FORA_DA_CARGA["_ping"]}
    assert not bd.tem_tabela("_ping")
    # o REAL chega inteiro (em float4 viria 131072.38 ou 131072.0)
    assert bd.valor("SELECT custo_estimado FROM rc_leituras WHERE id = 24") == 131072.37


def test_sem_as_tabelas_da_subida_a_conferencia_diz_quais_nao_vieram(tmp_path):
    """O que a conferência dizia antes do LH09: num banco em que nenhuma das 19
    nasceu, ela as lista todas — e a `_ping` só no aviso. Banco solto, e não o
    do `cg_casa`: o esquema dele é do módulo, e tabela apagada não volta."""
    arquivo = _arquivo_da_producao(tmp_path)
    con = conexao_de_teste()
    try:
        feito = banco_pg.conferir_carga_de_sqlite(arquivo, con.db_path)
    finally:
        con.close()
    assert not feito["ok"]
    assert feito["tabelas_que_nao_vieram"] == DO_SISTEMA
    assert feito["tabelas_ignoradas"] == {"_ping": banco_pg.TABELAS_FORA_DA_CARGA["_ping"]}


def test_a_linha_de_comando_avisa_a_ping_ignorada_e_sai_com_0(cg_casa, con, tmp_path, capsys):
    arquivo = _arquivo_da_producao(tmp_path)
    _carregar(arquivo, con)
    assert banco_pg.main(["conferir-carga", str(arquivo), str(cg_casa["banco"])]) == 0
    saida = capsys.readouterr()
    assert json.loads(saida.out)["tabelas_ignoradas"] == {
        "_ping": banco_pg.TABELAS_FORA_DA_CARGA["_ping"]}
    assert "AVISO: a tabela _ping do arquivo ficou fora da conferência" in saida.err


# ------------------------------------------------------------ cada módulo dono
# O ESQUEMA PREGUIÇOSO DE CADA MÓDULO FICA DESLIGADO: se a função gravar, a
# tabela que ela usou é a que a subida criou.

@pytest.fixture()
def sem_esquema_do_modulo(monkeypatch):
    import gestor_envios
    import gestor_leitura
    import malote_agente
    import malote_fraudes
    import rc_leitura_documentos
    import revisao_previa
    import ri_onus_ia

    def _nao_cria(*_a, **_k):
        return None

    for modulo, nome in ((gestor_envios, "init_gestor_schema"),
                         (gestor_leitura, "init_leitura_schema"),
                         (malote_agente, "init_schema"),
                         (malote_fraudes, "init_schema"),
                         (malote_fraudes, "init_schema_ia"),
                         (rc_leitura_documentos, "init_schema"),
                         (revisao_previa, "init_schema"),
                         (ri_onus_ia, "init_schema")):
        monkeypatch.setattr(modulo, nome, _nao_cria)


def test_compliance_grava_e_le_o_achado(con, bd, sem_esquema_do_modulo):
    import compliance as CP
    achado = CP._achado("GESTOR:parado", "AGENTES", "GESTOR_EXECUCAO", "CRITICO",
                        "O gestor não conferiu a casa", "Nenhuma rodada registrada.")
    assert CP.gravar(con, [achado], AGORA) == {"novos": 1, "resolvidos": 0}
    con.commit()
    linha = bd.um("SELECT chave, gravidade, primeiro_visto_em, resolvido_em FROM cp_achados")
    assert linha == {"chave": "GESTOR:parado", "gravidade": "CRITICO",
                     "primeiro_visto_em": AGORA, "resolvido_em": None}


def test_gestor_registra_e_le_o_envio(con, sem_esquema_do_modulo):
    import gestor_envios as GE
    ids = GE.registrar(con, "IBGE", protocolo="IBGE-EXEMPLO-1", registrado_por="mario",
                       competencia="2026-T3")
    assert len(ids) == 1
    [linha] = GE.recentes(con)
    assert (linha["central"], linha["competencia"], linha["protocolo"]) == (
        "IBGE", "2026-T3", "IBGE-EXEMPLO-1")


def test_a_triagem_do_malote_grava_e_le_a_ciencia(cg_casa, con, bd, sem_esquema_do_modulo):
    import gestor_expedientes as GX
    uid = cg_casa["db"].create_user("mario", "MARIO EXEMPLO DOS SANTOS", "Senha#12345", "ADMIN")
    eid = bd.escrever(
        """INSERT INTO expedientes (internal_protocol, source, sender, subject, category,
               received_at, stage, created_by, created_at, updated_at)
           VALUES ('EXP-1', 'Malote Digital', 'Vara de exemplo', 'Circular de exemplo',
                   'Circulares', '2026-10-20', 'RECEBIDO', %s, %s, %s) RETURNING id""",
        (uid, AGORA, AGORA))[0]["id"]
    GX._regravar_triagem(bd, eid, "c" * 64, AGORA, "claude", modelo="modelo-de-exemplo",
                         resultado_json=json.dumps({"tipo": "CIENCIA", "resumo": "Aviso."}))
    con.commit()
    [ciencia] = GX.para_ciencia(con)
    assert ciencia["id"] == eid


def test_a_leitura_do_gestor_grava_e_le_o_apontamento(con, bd, sem_esquema_do_modulo,
                                                      monkeypatch, tmp_path):
    import agente_provedores as AP
    import gestor_leitura as GL
    monkeypatch.setattr(AP, "tem_chave", lambda pasta, prov=None: True)
    mid = bd.escrever("INSERT INTO ri_matriculas (numero, criado_em) VALUES ('9001', %s) "
                      "RETURNING id", (AGORA,))[0]["id"]
    bd.escrever(
        """INSERT INTO ri_atos (matricula_id, tipo, numero, hash_ato, lavrado_em, teor,
               natureza_titulo, data_ato, selo_texto)
           VALUES (%s, 'R', 1, 'h', %s, %s, 'COMPRA E VENDA', '2026-09-20',
                   'MATRIC000000AAAAAAAAAAAAAAAA')""",
        (mid, AGORA, "<p>R-1/9001 - COMPRA E VENDA. Valor: R$ 120.000,00 (cento e vinte "
                     "mil reais). Matrícula 9001.</p>"))
    con.commit()

    def ia(pasta, **_pedido):
        return {"texto": '{"achados": [{"gravidade": "GRAVE", "o_que": "valor de exemplo", '
                         '"trecho": "R$ 120.000,00"}]}',
                "entrada": 1200, "saida": 80, "modelo": "modelo-de-exemplo"}

    assert GL.ler_pendentes(con, tmp_path, conversar=ia)["lidos"] == 1
    [apontamento] = GL.achados_vigentes(con)
    assert apontamento["grave"] and apontamento["o_que"] == "valor de exemplo"
    assert bd.valor("SELECT tokens_entrada FROM ge_leituras") == 1200


def test_o_agente_do_malote_grava_e_le_a_rodada(con, bd, sem_esquema_do_modulo, tmp_path):
    import malote_agente as MA
    MA.rodada(con, tmp_path, pasta_malote=None, fraudes=False)
    linha = bd.um("SELECT confirmou, terminada_em, resumo_json, erro FROM mt_execucoes")
    assert linha["confirmou"] == 0 and linha["terminada_em"] and linha["erro"] is None
    assert json.loads(linha["resumo_json"])["cadastrados"] == 0


def test_as_fraudes_do_malote_gravam_e_leem_a_proposta_e_a_leitura(con, bd, sem_esquema_do_modulo):
    import malote_fraudes as MF
    proposta = {"nome": "FULANO DE TAL EXEMPLO", "documento": "000.000.044-21",
                "papel": "VITIMA", "codigo_malote": "2026000001",
                "documento_malote": "aviso_exemplo.pdf", "trecho": "documento de exemplo"}
    assert MF.carregar(con, [proposta], AGORA) == {"novas": 1, "repetidas": 0}
    assert MF.carregar(con, [proposta], AGORA) == {"novas": 0, "repetidas": 1}
    MF._registrar_leitura(con, grupo="aviso_exemplo.pdf", codigo="2026000001",
                          texto="texto de exemplo", agora=AGORA,
                          lida={"provedor": "claude", "modelo": "modelo-de-exemplo",
                                "entrada": 900, "saida": 60})
    linha = bd.um("SELECT documento, situacao FROM mt_alertas_propostos")
    assert linha == {"documento": "00000004421", "situacao": "PROPOSTO"}
    assert bd.valor("SELECT tokens_saida FROM mt_fraude_leituras") == 60


def test_a_leitura_de_documentos_do_civil_grava_e_le(con, sem_esquema_do_modulo):
    import rc_leitura_documentos as RL
    lid = RL.abrir(con, especie="NASCIMENTO", agora=AGORA, por="mario")
    envios = [{"modelo": modelo, "entrada": 120_000, "saida": 9_000}
              for modelo in RL.PRECO_POR_MILHAO][:1]
    RL.concluir(con, lid, arquivos=[{"nome": "dnv_exemplo.pdf", "sha256": "0" * 64}],
                lido={"envios": envios}, erro="a rede caiu (exemplo)")
    con.commit()
    leitura = RL.uma(con, lid)
    assert leitura["situacao"] == "FALHOU" and leitura["arquivos"][0]["nome"] == "dnv_exemplo.pdf"
    esperado = round(sum(RL.custo(e["modelo"], e["entrada"], e["saida"]) for e in envios), 4)
    assert leitura["custo_estimado"] == esperado


def test_o_onus_pela_ia_grava_e_le_o_pedido(con, bd, sem_esquema_do_modulo):
    import ri_onus_ia as RO
    mid = bd.escrever("INSERT INTO ri_matriculas (numero, criado_em) VALUES ('9002', %s) "
                      "RETURNING id", (AGORA,))[0]["id"]
    sid, nova = RO.pedir(con, mid, usuario="mario")
    assert nova
    con.commit()
    ultima = RO.ultima(con, mid)
    assert ultima["id"] == sid and ultima["pedido_por"] == "mario" and ultima["vale"]
    assert RO.pedir(con, mid, usuario="mario") == (sid, False)


def test_a_revisao_previa_grava_e_le_o_pedido(con, sem_esquema_do_modulo):
    import revisao_previa as RV
    rid, nova = RV.pedir(con, "NOTAS", 901, "1" * 64, "=== ATO A LAVRAR ===\nexemplo",
                         rotulo="Escritura de exemplo", usuario="mario")
    assert nova
    con.commit()
    revisao = RV.mostrar(con, rid)
    assert revisao["id"] == rid and revisao["situacao"] == "PENDENTE"
    assert revisao["graves"] == 0 and revisao["achados"] == []


def test_os_anexos_da_revisao_gravam_e_leem_a_transcricao(con, sem_esquema_do_modulo):
    import revisao_anexos as RA
    linha = dict(LINHAS_DA_PRODUCAO["rv_anexos_lidos"], paginas_triadas=2)
    RA._guardar(con, linha)
    guardado = RA._guardado(con, "9" * 64)
    assert guardado["transcricao"] == "[página 1] exemplo"
    assert (guardado["paginas_triadas"], guardado["tokens_saida"]) == (2, 900)
