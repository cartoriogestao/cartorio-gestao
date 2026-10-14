"""A REVISÃO ANTES DA LAVRATURA — o Opus lê o ato inteiro antes de ele existir.

    «e se a leitura for completa, usando opus 5.5, apenas quando lavrado cada
     ato, em uma etapa intermediaria entre preenchimento e lavratura?»
    «sim, facamos assim» — o oficial, 06/10/2026

ONDE ELA ENTRA
    RI (registro e averbação, pela rota de sempre, `ri_lavrar_ato`) e Notas
    (o lançamento do ato no livro). Entre preencher e lavrar há o botão
    «Revisar com IA»; a leitura roda em segundo plano, e o apontamento aparece
    ao lado do texto.

O QUE ELA LÊ: o ato a lavrar E O CONTEXTO — no RI, a ficha inteira e os
    atos dela (medido em 06/10/2026: ~10 mil tokens por ato); nas Notas, o
    teor e as partes. Passa pela MESMA barreira de privacidade da ajuda: nome e
    CPF vão como marcas, e a conferência de nome contra o cadastro continua
    sendo por regra, no gestor.

O QUE TRAVA, E O QUE NÃO
    - Sem revisão do texto que está sendo lavrado → recusa, dizendo o que fazer.
    - Revisão ainda lendo → recusa («espere a leitura»).
    - Apontamento GRAVE → só lavra com JUSTIFICATIVA escrita (mínimo de dez
      letras, a régua das recusas da casa), e ela fica gravada.
    - A IA não respondeu (rede, chave, provedor) → **a lavratura não para**:
      o balcão parado é pior que a revisão atrasada. O ato entra na leitura
      diária do gestor.
    - Sem chave da IA nesta instalação, ou com `settings.revisao_previa = '0'`
      → a etapa não existe (e é por isso que os testes de lavratura não a veem).

A IA APONTA; NÃO DECIDE. Quem lavra é quem assina, e a justificativa é a
prova de que leu o apontamento.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

PROVEDOR = "claude"
MODELO = "claude-opus-5-5"
MAXIMO_DE_SAIDA = 6000
LIMITE_DO_DOSSIE = 120_000
CHAVE_LIGADA = "revisao_previa"
#: A REVISÃO VAI SEM MÁSCARA — decisão do oficial em 06/10/2026: «liberar
#: revisão sem máscara». Medido no mesmo dia: a máscara trocava também
#: município, nome de fazenda e número de matrícula por marcas, e a revisão
#: ficava cega para confrontação e numeração. Vale para a revisão antes da
#: lavratura, a revisão em lote e a leitura diária do gestor; a triagem do malote
#: (que não revisa ato) continua mascarada. `settings.revisao_mascara = '1'`
#: volta a mascarar sem versão nova.
CHAVE_MASCARA = "revisao_mascara"
#: HOTFIX-2026-10-13-01 (Leidiane, 13/10/2026: «esse modo revisão IA está
#: atrapalhando»). `settings.revisao_previa_modo`: 'consultivo' (padrão) ou
#: 'bloqueante' (regra antiga, de 06-08/10). No consultivo, para gerente/
#: administrador e para ato de ofício/encerramento/isento, a revisão só
#: aconselha: sem revisão ou lendo não trava; GRAVE pede um clique
#: «prosseguir». Para os demais, texto até 80% igual aproveita a revisão
#: anterior sem justificativa.
CHAVE_MODO = "revisao_previa_modo"
SEMELHANCA_AUTOMATICA = 0.80
#: Leitura que passa disto sem terminar é tratada como falha (não trava o balcão).
#: Era 6; com os anexos (07/10/2026) a leitura ganhou a triagem e a transcrição
#: das páginas digitalizadas antes do Opus, e 40 páginas levam alguns minutos.
MINUTOS_PARA_DESISTIR = 12
MINIMO_DA_JUSTIFICATIVA = 10

SCHEMA = """
CREATE TABLE IF NOT EXISTS rv_revisoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
);
CREATE INDEX IF NOT EXISTS ix_rv_revisoes_alvo
    ON rv_revisoes (atribuicao, alvo_id, hash_texto);
"""

#: OS ANEXOS NA REVISÃO (07/10/2026) — ver `revisao_anexos.py`. Colunas novas,
#: acrescentadas ao banco que já existe.
COLUNAS_DOS_ANEXOS = {
    "anexos_origem": "TEXT",        # {"entidade": "NT_ATO"|"RI_PROTOCOLO", "id": n}
    "anexos_assinatura": "TEXT",    # o conjunto de arquivos no pedido
    "anexos_json": "TEXT",          # o resumo para a tela
    "aviso_anexos": "TEXT",
    "tokens_anexos": "INTEGER",
}

INSTRUCAO = """Você é o revisor de qualificação de uma serventia extrajudicial no \
Maranhão (Registro de Imóveis e Tabelionato de Notas), lendo um ato ANTES de ele ser \
lavrado. Nomes e documentos de pessoas vêm mascarados como marcas ([PESSOA_01], \
[CPF_01]); trate marcas iguais como a mesma pessoa e NÃO aponte a máscara como erro.

Você recebe o contexto (no RI: a matrícula inteira e os atos dela; nas Notas: as \
partes cadastradas) e o ATO A LAVRAR. Procure, no ato a lavrar:
- contradição com a matrícula: área, descrição, confrontações, proprietário atual, \
ônus e indisponibilidades vigentes que o ato ignora, título anterior;
- numeração: número do ato e da matrícula citados que não batem;
- valores: número contra extenso, base de cálculo citada de forma incoerente;
- datas impossíveis ou fora de ordem;
- elementos que a lei exige para aquele tipo de ato e que faltam (Lei 6.015/1973, \
arts. 176 e 225 no RI; Código Civil e Lei 7.433/1985 nas escrituras);
- texto de modelo esquecido, frase cortada, parte que aparece no texto e não está \
qualificada.

Se vierem DOCUMENTOS ANEXADOS, confira o ato contra eles: nomes e documentos das \
partes, estado civil, valores, área, descrição, confrontações, datas, número de \
matrícula e de título. A transcrição de página digitalizada pode ter erro de leitura: \
divergência que só aparece nela é ATENCAO, dizendo que vem da leitura da imagem.

NÃO são problemas: a máscara de nomes; união estável descrita junto do estado civil; \
área em ha/a/ca; preço diferente da base de cálculo; abreviações usuais do cartório; \
a falta de selo, de emolumentos ou do número do selo no texto (o selo é gerado DEPOIS \
da lavratura, pelo sistema); «Livro nº 2 – Registro Geral» citado de forma genérica \
para matrícula de livro 2-A, 2-B… 2-F (é o mesmo Livro 2); data do ato diferente da \
data de hoje; divergência entre a numeração/texto do livro físico, da transcrição \
digitalizada ou de certidões antigas (não é objeto do ato a lavrar); o campo «Tipo» \
do formulário quando o próprio texto identifica o ato (AV/R). Em ATO DE OFÍCIO e em \
ENCERRAMENTO DE MATRÍCULA por mudança da técnica de escrituração (transposição para \
nova matrícula, sem transmissão), NÃO exija partes, valor, base de cálculo, \
descrição do remanescente ou qualificação: basta número do ato, motivo, matrícula \
de destino, fundamento, data e assinatura.

Responda SÓ com JSON, sem texto em volta:
{"achados": [{"gravidade": "GRAVE" | "ATENCAO", "o_que": "...", "trecho": "...", \
"por_que": "..."}], "parecer": "uma ou duas frases"}
GRAVE é o que, lavrado, exige averbação de retificação ou anula o ato. Na dúvida, \
ATENCAO. Sem achado, lista vazia. Não invente: se o texto não permite concluir, não \
aponte."""


#: O REVISOR DA PROCURAÇÃO É O SONNET — ordem do oficial em 13/10/2026:
#: «coloque revisor de procuracao pelo sonnet, obrigando que todos campos do ato
#: sejam preenchidos no sistema, para nao ocorrer esse problema de novo». O
#: caso: a procuração 791 foi lavrada com o procurador só no termo impresso; o
#: texto do sistema ficou com o colchete do modelo e o cadastro, sem o
#: procurador. Os campos obrigatórios são TRAVA FIXA em `notas_web`
#: (`_travas_da_procuracao`); aqui o Sonnet confere o TEXTO contra o cadastro.
MODELO_DA_PROCURACAO = "claude-sonnet-5-5"
TIPOS_DA_PROCURACAO = ("PROCURACAO", "PROCURACAO_PREVIDENCIARIA", "SUBSTABELECIMENTO")

INSTRUCAO_DA_PROCURACAO = """Você é o revisor de PROCURAÇÕES PÚBLICAS de uma serventia \
extrajudicial no Maranhão, lendo a procuração ANTES de ela ser lavrada. Recebe as partes \
CADASTRADAS no sistema (com qualificação, documento, estado civil, profissão, endereço) e o \
TEXTO A LAVRAR. O texto e o cadastro têm de dizer a mesma coisa: o que for lavrado com \
diferença vira escritura de retificação.

Confira, um a um:
- TODA parte cadastrada aparece no texto com o mesmo nome e o mesmo documento, na qualidade \
cadastrada (outorgante, outorgado/procurador, assina a rogo, interveniente, testemunha);
- TODA pessoa qualificada no texto está no cadastro — procurador citado só no texto é GRAVE;
- o texto nomeia o(s) procurador(es) com qualificação completa (nome, nacionalidade, estado \
civil, profissão, documento, endereço) — colchete, «QUALIFIQUE», «[NOME…]» ou campo em \
branco é GRAVE;
- o outorgante tem qualificação completa e capacidade; quem não sabe ou não pode assinar \
precisa de quem assine a rogo, qualificado (Código Civil, art. 215, § 2º);
- os poderes: coerentes com a finalidade declarada; poder para alienar, onerar, receber e dar \
quitação, transigir ou representar em banco precisa ser expresso e específico; venda de \
imóvel ou veículo precisa identificar o bem; prazo de validade, quando houver, legível;
- quem lavra (perante mim, …) e o fecho com quem assina batem com as partes;
- data por extenso coerente com a data em algarismos.

NÃO são problemas: a falta de selo, emolumentos ou número do selo (saem DEPOIS da lavratura); \
a falta de livro, folha e termo (o sistema numera na lavratura); abreviações usuais.

Responda SÓ com JSON, sem texto em volta:
{"achados": [{"gravidade": "GRAVE" | "ATENCAO", "o_que": "...", "trecho": "...", \
"por_que": "..."}], "parecer": "uma ou duas frases"}
GRAVE é o que, lavrado, exige retificação ou invalida a procuração. Na dúvida, ATENCAO. \
Sem achado, lista vazia. Não invente."""


def modelo_e_instrucao(con: sqlite3.Connection, atribuicao: str,
                       alvo_id: int) -> tuple[str, str]:
    """Quem lê e com que instrução: a procuração tem revisor próprio (Sonnet)."""
    if atribuicao == "NOTAS" and _tem_tabela(con, "nt_atos"):
        linha = con.execute("SELECT tipo FROM nt_atos WHERE id = ?", (alvo_id,)).fetchone()
        if linha and (linha[0] or "") in TIPOS_DA_PROCURACAO:
            return MODELO_DA_PROCURACAO, INSTRUCAO_DA_PROCURACAO
    return MODELO, INSTRUCAO


class RevisaoPendente(ValueError):
    """Erro de regra, com a frase pronta para o balcão."""


def init_schema(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA)
    # As colunas pela descrição do cursor, e não por PRAGMA: módulo de domínio
    # não pergunta o esquema ao banco (teto de portabilidade da casa).
    tem = {d[0] for d in con.execute("SELECT * FROM rv_revisoes LIMIT 0").description}
    for nome, tipo in COLUNAS_DOS_ANEXOS.items():
        if nome not in tem:
            con.execute(f"ALTER TABLE rv_revisoes ADD COLUMN {nome} {tipo}")


def _tem_tabela(con, nome: str) -> bool:
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                       (nome,)).fetchone() is not None


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def normalizar(texto: str | None) -> str:
    """Sem marcação de HTML e com as entidades traduzidas (`&#x27;` vira «'»)."""
    import html
    sem_tags = html.unescape(re.sub(r"<[^>]+>", " ", texto or ""))
    return " ".join(sem_tags.split())


def hash_do_ato(tipo: str | None, teor: str | None) -> str:
    """A identidade do TEXTO que se lavra: vírgula mudada é outra revisão."""
    return hashlib.sha256(f"{(tipo or '').upper()}|{normalizar(teor)}".encode("utf-8")
                          ).hexdigest()


def ligada(con: sqlite3.Connection, pasta_dados: Path) -> bool:
    import agente_provedores as AP
    linha = con.execute("SELECT value FROM settings WHERE key = ?",
                        (CHAVE_LIGADA,)).fetchone() if _tem_tabela(con, "settings") else None
    if linha and str(linha[0]).strip() == "0":
        return False
    return AP.tem_chave(pasta_dados, PROVEDOR)


def mascarar_na_revisao(con: sqlite3.Connection) -> bool:
    if not _tem_tabela(con, "settings"):
        return False
    linha = con.execute("SELECT value FROM settings WHERE key = ?", (CHAVE_MASCARA,)).fetchone()
    return bool(linha and str(linha[0]).strip() == "1")


def preparar_para_ia(con: sqlite3.Connection, texto: str) -> tuple[str, dict[str, str]]:
    """O texto que vai à IA e o mapa para trazer os nomes de volta (vazio sem máscara)."""
    if not mascarar_na_revisao(con):
        return texto, {}
    from gestor_expedientes import mascarar
    return mascarar(texto)


# ------------------------------------------------------------------ dossiês


def dossie_ri_lavrado(con: sqlite3.Connection, ato_id: int) -> str:
    """O ato JÁ lavrado, com a ficha e os atos ANTERIORES a ele — para a revisão
    em lote e para a leitura diária. Os posteriores ficam de fora: o ato se
    julga pelo que havia quando foi lavrado."""
    a = con.execute("""SELECT matricula_id, tipo, numero, teor, natureza_titulo
                         FROM ri_atos WHERE id = ?""", (ato_id,)).fetchone()
    m = con.execute("SELECT numero, livro, teor FROM ri_matriculas WHERE id = ?",
                    (a[0],)).fetchone()
    partes = [f"MATRÍCULA nº {m[0]} (livro {m[1] or '2'})", "", "TEOR DA FICHA:",
              normalizar(m[2]) or "(sem teor)", "", "ATOS ANTERIORES DA FICHA:"]
    for t, n, d, texto in con.execute(
            """SELECT tipo, numero, data_ato, teor FROM ri_atos WHERE matricula_id = ?
                  AND id <> ? AND numero < ? AND COALESCE(cancelado,0) = 0
                ORDER BY numero""", (a[0], ato_id, a[2] or 0)):
        partes.append(f"{t}-{n} ({d or '—'}): {normalizar(texto)}")
    partes += ["", "=== ATO JÁ LAVRADO, A REVISAR ===", f"Tipo: {a[1]}-{a[2]}",
               f"Natureza do título: {a[4] or '—'}", normalizar(a[3])]
    return "\n".join(partes)[-LIMITE_DO_DOSSIE:]

def dossie_ri(con: sqlite3.Connection, matricula_id: int, tipo: str, teor: str,
              natureza: str | None = None) -> str:
    m = con.execute("SELECT numero, livro, situacao, teor FROM ri_matriculas WHERE id = ?",
                    (matricula_id,)).fetchone()
    if m is None:
        raise RevisaoPendente("Matrícula não encontrada.")
    partes = [f"MATRÍCULA nº {m[0]} (livro {m[1] or '2'}, situação {m[2] or '—'})",
              "", "TEOR DA FICHA:", normalizar(m[3]) or "(sem teor)", "", "ATOS DA FICHA:"]
    for t, n, d, texto in con.execute(
            """SELECT tipo, numero, data_ato, teor FROM ri_atos WHERE matricula_id = ?
                  AND COALESCE(cancelado,0) = 0 ORDER BY numero""", (matricula_id,)):
        partes.append(f"{t}-{n} ({d or '—'}): {normalizar(texto)}")
    partes += ["", "=== ATO A LAVRAR ===", f"Tipo: {tipo}",
               f"Natureza do título: {natureza or '—'}", normalizar(teor)]
    return "\n".join(partes)[-LIMITE_DO_DOSSIE:]


def dossie_notas(con: sqlite3.Connection, ato_id: int) -> str:
    a = con.execute("SELECT tipo, natureza, livro, teor FROM nt_atos WHERE id = ?",
                    (ato_id,)).fetchone()
    if a is None:
        raise RevisaoPendente("Ato das Notas não encontrado.")
    partes = [f"ATO DAS NOTAS: {a[0]} — {a[1] or '—'} (livro {a[2] or '—'})", "",
              "PARTES CADASTRADAS:"]
    if _tem_tabela(con, "nt_ato_partes"):
        # O cadastro inteiro de cada parte (13/10/2026): o revisor da procuração
        # compara o texto com ele, campo a campo.
        for nome, qualif, civil, documento, nac, prof, end, test in con.execute(
                """SELECT nome, qualificacao, estado_civil, documento, nacionalidade,
                          profissao, endereco, testemunha FROM nt_ato_partes
                    WHERE ato_id = ? ORDER BY ordem, id""", (ato_id,)):
            partes.append(f"- {nome} ({documento or 'sem documento'}): "
                          f"{qualif or 'SEM QUALIFICAÇÃO'}; {civil or 'estado civil ?'}; "
                          f"{nac or 'nacionalidade ?'}; {prof or 'profissão ?'}; "
                          f"{end or 'endereço ?'}" + ("; testemunha" if test else ""))
    partes += ["", "=== ATO A LAVRAR ===", normalizar(a[3])]
    return "\n".join(partes)[-LIMITE_DO_DOSSIE:]


# -------------------------------------------------------------- o pedido

def pedir(con: sqlite3.Connection, atribuicao: str, alvo_id: int, hash_texto: str,
          dossie: str, *, rotulo: str = "", usuario: str = "",
          origem: str = "BALCAO", anexos_origem: dict | None = None) -> tuple[int, bool]:
    """(id, nova). O mesmo texto já revisado (ou lendo) não se lê de novo.

    «O mesmo» inclui OS ANEXOS: anexar o título depois da revisão pede revisão
    nova — a anterior não o viu. Os anexos se LEEM depois, na leitura em
    segundo plano; aqui só se guarda de onde eles vêm.
    """
    import revisao_anexos as RA
    init_schema(con)
    assinatura = RA.assinatura(RA.anexos(con, anexos_origem)) if anexos_origem else ""
    ja = con.execute(
        """SELECT id FROM rv_revisoes WHERE atribuicao=? AND alvo_id=? AND hash_texto=?
              AND COALESCE(anexos_assinatura, '') = ?
              AND situacao IN ('PENDENTE','LENDO','PRONTA') ORDER BY id DESC""",
        (atribuicao, alvo_id, hash_texto, assinatura)).fetchone()
    if ja:
        return int(ja[0]), False
    cur = con.execute(
        """INSERT INTO rv_revisoes (atribuicao, alvo_id, hash_texto, rotulo, dossie,
               pedido_em, pedido_por, origem, anexos_origem, anexos_assinatura)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (atribuicao, alvo_id, hash_texto, rotulo, dossie, _agora(), usuario, origem,
         json.dumps(anexos_origem) if anexos_origem else None, assinatura or None))
    return int(cur.lastrowid), True


MARCA_DO_ATO = "=== ATO A LAVRAR ==="


def _com_os_anexos(dossie: str, bloco: str) -> str:
    """Os documentos entram ANTES do ato: o corte do dossiê guarda o fim, e o fim
    é o ato — anexo grande não pode empurrar o próprio ato para fora."""
    if not bloco:
        return dossie
    titulo = ("=== DOCUMENTOS ANEXADOS (transcrição; página digitalizada pode ter "
              "erro de leitura) ===\n")
    if MARCA_DO_ATO in dossie:
        return dossie.replace(MARCA_DO_ATO, titulo + bloco + "\n\n" + MARCA_DO_ATO, 1)
    return titulo + bloco + "\n\n" + dossie


def _ler_json(texto: str) -> dict:
    m = re.search(r"\{.*\}", texto or "", re.S)
    if not m:
        raise ValueError("a resposta não trouxe JSON")
    d = json.loads(m.group(0))
    achados = [a for a in (d.get("achados") or []) if isinstance(a, dict)]
    for a in achados:
        a["gravidade"] = "GRAVE" if str(a.get("gravidade", "")).upper() == "GRAVE" else "ATENCAO"
    return {"achados": achados, "parecer": str(d.get("parecer") or "")[:600]}


def executar(banco: Path, pasta_dados: Path, revisao_id: int, conversar=None) -> None:
    """Lê. FALA COM A REDE, com conexão própria e fora de transação de escrita."""
    import agente_provedores as AP
    from gestor_expedientes import desmascarar
    conversar = conversar or AP.conversar
    con = sqlite3.connect(str(banco), timeout=30)
    try:
        init_schema(con)
        linha = con.execute("SELECT dossie, anexos_origem, rotulo, atribuicao, alvo_id "
                            "FROM rv_revisoes WHERE id = ?", (revisao_id,)).fetchone()
        if linha is None:
            return
        modelo, instrucao = modelo_e_instrucao(con, linha[3], linha[4])
        con.execute("UPDATE rv_revisoes SET situacao='LENDO', provedor=?, modelo=? WHERE id=?",
                    (PROVEDOR, modelo, revisao_id))
        con.commit()
        try:
            dossie = linha[0]
            if linha[1]:
                # OS ANEXOS NÃO DERRUBAM A REVISÃO: falhou a leitura deles, o ato
                # se revisa sem eles, e a tela diz que eles ficaram de fora.
                import revisao_anexos as RA
                try:
                    lido = RA.ler(con, pasta_dados, json.loads(linha[1]),
                                  contexto=linha[2] or "", conversar=conversar,
                                  mascarada=mascarar_na_revisao(con))
                except Exception as erro:               # noqa: BLE001 — vai à tela
                    lido = {"bloco": "", "resumo": [], "tokens": 0,
                            "aviso": f"Os anexos não foram lidos desta vez "
                                     f"({type(erro).__name__}); revise de novo mais tarde."}
                dossie = _com_os_anexos(dossie, lido["bloco"])
                con.execute("""UPDATE rv_revisoes SET anexos_json=?, aviso_anexos=?,
                                   tokens_anexos=? WHERE id=?""",
                            (json.dumps(lido["resumo"], ensure_ascii=False),
                             lido["aviso"] or None, lido["tokens"], revisao_id))
                con.commit()
            seguro, mapa = preparar_para_ia(con, dossie)
            resposta = conversar(pasta_dados, provedor=PROVEDOR, sistema=instrucao,
                                 conversa=[{"tipo": "user", "texto": seguro}],
                                 ferramentas=[], modelo=modelo,
                                 maximo_de_saida=MAXIMO_DE_SAIDA)
            r = desmascarar(_ler_json(resposta.get("texto") or ""), mapa)
            graves = sum(a["gravidade"] == "GRAVE" for a in r["achados"])
            con.execute(
                """UPDATE rv_revisoes SET situacao='PRONTA', terminado_em=?, resultado_json=?,
                       graves=?, modelo=?, tokens_entrada=?, tokens_saida=? WHERE id=?""",
                (_agora(), json.dumps(r, ensure_ascii=False), graves,
                 resposta.get("modelo") or modelo, resposta.get("entrada"),
                 resposta.get("saida"), revisao_id))
        except Exception as erro:                       # noqa: BLE001 — vai à tabela
            con.execute("UPDATE rv_revisoes SET situacao='ERRO', terminado_em=?, erro=? "
                        "WHERE id=?",
                        (_agora(), f"{type(erro).__name__}: {str(erro)[:300]}", revisao_id))
        con.commit()
    finally:
        con.close()


def ler_em_segundo_plano(banco: Path, pasta_dados: Path, revisao_id: int) -> None:
    threading.Thread(target=executar, args=(Path(banco), Path(pasta_dados), revisao_id),
                     daemon=True, name=f"revisao-previa-{revisao_id}").start()


def mostrar(con: sqlite3.Connection, revisao_id: int) -> dict | None:
    if not _tem_tabela(con, "rv_revisoes"):
        return None
    init_schema(con)
    r = con.execute("""SELECT id, situacao, resultado_json, graves, erro, pedido_em,
                              anexos_json, aviso_anexos
                         FROM rv_revisoes WHERE id = ?""", (revisao_id,)).fetchone()
    if r is None:
        return None
    resultado = json.loads(r[2]) if r[2] else {"achados": [], "parecer": ""}
    return {"id": r[0], "situacao": _situacao_viva(r[1], r[5]), "graves": r[3],
            "erro": r[4], "anexos": json.loads(r[6]) if r[6] else [],
            "aviso_anexos": r[7] or "", **resultado}


def ultima(con: sqlite3.Connection, atribuicao: str, alvo_id: int,
           hash_atual: str | None = None, *, depois_de: str | None = None) -> dict | None:
    """A última revisão pedida para este ato, para a tela mostrar de novo ao abrir.

    PEDIDO DO OFICIAL, 07/10/2026: «a revisão do ato no sistema não fica salva no
    ato, se atualiza a página perde a resposta». Ela FICAVA salva (`rv_revisoes`);
    a tela é que só a mostrava no clique. Com o texto atual conhecido (Notas: o teor
    guardado), vale a revisão desse texto e, sem ela, a mais nova com
    `texto_mudou=True`. No RI o texto está no formulário (`hash_atual=None`), e
    `depois_de` corta a revisão de um ato que já foi lavrado depois dela.
    """
    if not _tem_tabela(con, "rv_revisoes"):
        return None
    r = None
    if hash_atual:
        r = con.execute("""SELECT id, hash_texto, pedido_em, pedido_por FROM rv_revisoes
                            WHERE atribuicao=? AND alvo_id=? AND hash_texto=?
                         ORDER BY id DESC LIMIT 1""", (atribuicao, alvo_id, hash_atual)).fetchone()
    if r is None:
        r = con.execute("""SELECT id, hash_texto, pedido_em, pedido_por FROM rv_revisoes
                            WHERE atribuicao=? AND alvo_id=? ORDER BY id DESC LIMIT 1""",
                        (atribuicao, alvo_id)).fetchone()
    if r is None or (depois_de and (r[2] or "") < depois_de):
        return None
    saida = mostrar(con, r[0]) or {}
    saida.update({"pedido_em": r[2], "pedido_por": r[3],
                  "texto_mudou": None if hash_atual is None else r[1] != hash_atual})
    return saida


def _situacao_viva(situacao: str, pedido_em: str) -> str:
    """Leitura que não termina vira ERRO para o balcão — não pode travar."""
    if situacao in ("PENDENTE", "LENDO"):
        try:
            idade = (datetime.now() - datetime.fromisoformat(pedido_em)).total_seconds()
        except ValueError:
            idade = 0
        if idade > MINUTOS_PARA_DESISTIR * 60:
            return "ERRO"
    return situacao


# ---------------------------------------------------------- a trava

def exigir_para_lavrar(con: sqlite3.Connection, pasta_dados: Path, atribuicao: str,
                       alvo_id: int, hash_texto: str, *, justificativa: str = "",
                       usuario: str = "", papel: str | None = None,
                       usar_revisao_anterior: bool = False,
                       justificativa_anterior: str = "",
                       texto_atual: str | None = None, tipo: str | None = None,
                       contexto_oficio: bool = False, prosseguir: bool = False) -> str:
    """Diz se o texto pode ser lavrado. Devolve como: «desligada», «falhou», «ok»
    ou «anterior:<id>:<semelhança>» (gerente lavrando com a revisão anterior).

    Grava a justificativa quando ela é o que libera. Erro de regra sobe como
    `RevisaoPendente`, com a frase para o balcão.

    HOTFIX-2026-10-08-07 (pedido da Beatriz, 08/10/2026 - AV-8/1196):
      - aviso de ATENÇÃO nunca travou e continua não travando;
      - GRAVE marcado como «já verificado/suprido» (gerente/administrador, com
        observação) não conta mais como pendente - nem nesta revisão, nem numa
        revisão nova do mesmo ato (`anotar_supridos`);
      - texto que mudou POUCO depois da revisão: o gerente/administrador pode
        lavrar com a revisão anterior, com justificativa escrita, se o texto
        continuar ao menos 90% igual e sem GRAVE pendente. Fica gravado na
        revisão (`liberacoes`) e na auditoria da rota.
    """
    if not ligada(con, pasta_dados):
        return "desligada"
    if modo(con) == "consultivo":
        como = _exigir_consultivo(con, atribuicao, alvo_id, hash_texto,
                                  justificativa=justificativa, usuario=usuario,
                                  papel=papel, texto_atual=texto_atual, tipo=tipo,
                                  contexto_oficio=contexto_oficio,
                                  prosseguir=prosseguir)
        if como is not None:
            return como
    if not _tem_tabela(con, "rv_revisoes"):
        raise RevisaoPendente("Antes de lavrar, clique em «Revisar com IA»: a revisão "
                              "lê o ato com a matrícula e aponta o que não fecha.")
    r = con.execute(
        """SELECT id, situacao, graves, pedido_em FROM rv_revisoes
            WHERE atribuicao=? AND alvo_id=? AND hash_texto=? ORDER BY id DESC""",
        (atribuicao, alvo_id, hash_texto)).fetchone()
    pode = (papel or "").upper() in PAPEIS_QUE_SUPREM
    liberacao = None
    if r is None:
        if not usar_revisao_anterior:
            raise RevisaoPendente(
                "Antes de lavrar, clique em «Revisar com IA». Se o texto mudou depois "
                "da revisão, ela vale para o texto antigo — revise de novo"
                + (" (ou, se a mudança foi pequena, marque «Lavrar com a revisão "
                   "anterior» e escreva o porquê)" if pode else "") + ".")
        if not pode:
            raise RevisaoPendente("Lavrar com a revisão anterior é só do gerente ou do "
                                  "administrador. Clique em «Revisar com IA».")
        texto_j = " ".join((justificativa_anterior or "").split())
        if len(texto_j) < MINIMO_DA_JUSTIFICATIVA:
            raise RevisaoPendente("Para lavrar com a revisão anterior, escreva por que a "
                                  "mudança no texto não pede revisão nova (mínimo de dez "
                                  "letras).")
        ant, semelhanca = _revisao_anterior(con, atribuicao, alvo_id, texto_atual, tipo)
        r = (ant[0], ant[1], None, ant[2])
        liberacao = {"tipo": "REVISAO_ANTERIOR", "por": usuario, "papel": papel,
                     "em": _agora(), "justificativa": texto_j,
                     "semelhanca": round(semelhanca, 3), "hash_lavrado": hash_texto}
    situacao = _situacao_viva(r[1], r[3])
    if situacao in ("PENDENTE", "LENDO"):
        raise RevisaoPendente("A revisão ainda está lendo o ato. Espere o resultado "
                              "aparecer ao lado do texto e lavre em seguida.")
    if situacao == "ERRO":
        return "falhou"
    pendentes = graves_pendentes(con, r[0])
    if pendentes:
        if liberacao is not None:
            raise RevisaoPendente(
                f"A revisão anterior tem {pendentes} apontamento(s) grave(s) não "
                "suprido(s). Marque-os como «Já verificado/suprido» ou revise de novo.")
        texto = " ".join((justificativa or "").split())
        if len(texto) < MINIMO_DA_JUSTIFICATIVA:
            raise RevisaoPendente(
                f"A revisão apontou {pendentes} problema(s) grave(s) ainda não "
                "suprido(s). Corrija o texto e revise de novo, marque como «Já "
                "verificado/suprido» (gerente), ou escreva por que lavra assim mesmo "
                "- a justificativa fica gravada com o ato.")
        con.execute("""UPDATE rv_revisoes SET justificativa=?, justificado_por=?,
                           justificado_em=? WHERE id=?""", (texto, usuario, _agora(), r[0]))
    if liberacao is not None:
        _anotar_liberacao(con, r[0], liberacao)
        return f"anterior:{r[0]}:{liberacao['semelhanca']:.3f}"
    return "ok"


# ------------------------------------- «JÁ VERIFICADO/SUPRIDO» - HOTFIX-2026-10-08-07
#
# Pedido da Beatriz em 08/10/2026, lavrando o AV-8/1196: cada apontamento da
# revisão pode ser marcado como «já verificado/suprido», com observação. A marca
# mora no próprio `resultado_json` da revisão (sem tabela nova) e vale também
# para as revisões seguintes do MESMO ato: no RI, as marcadas depois do último
# ato lavrado na matrícula; nas Notas, as do mesmo ato. O assunto se reconhece
# pelas palavras do «o_que» (a IA reescreve a frase a cada leitura).
# ATENÇÃO suprida não cobre GRAVE; GRAVE só o gerente/administrador supre, com
# observação de no mínimo dez letras.

PAPEIS_QUE_SUPREM = ("ADMIN", "MANAGER")
SEMELHANCA_MINIMA_DO_TEXTO = 0.90
_PARADAS = {"para", "pela", "pelo", "pelas", "pelos", "entre", "antes", "depois",
            "sobre", "como", "mais", "este", "esta", "esse", "essa", "deste", "desta",
            "desse", "dessa", "nova", "novo", "ainda", "quando", "onde", "pois",
            "isso", "isto", "seja", "sendo", "numa", "outro", "outra", "qual",
            "forma", "modo", "ser", "estar", "sem", "com", "nao", "dos", "das"}


def _sem_acento(texto: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", texto or "")
                   if not unicodedata.combining(c)).lower()


def chave_do_achado(o_que: str | None) -> list[str]:
    """As palavras que dizem o assunto (raiz de 5 letras, sem acento)."""
    palavras = re.findall(r"[a-z0-9]+", _sem_acento(o_que or ""))
    return sorted({p[:5] for p in palavras if len(p) >= 4 and p not in _PARADAS})


def mesmo_assunto(a, b) -> bool:
    A, B = set(a or ()), set(b or ())
    if not A or not B:
        return False
    comum = len(A & B)
    return comum >= min(2, len(A), len(B)) and comum / min(len(A), len(B)) >= 0.6


def _desde(con: sqlite3.Connection, atribuicao: str, alvo_id: int) -> str:
    """No RI a marca vale para o ato em preparo: só depois do último ato lavrado."""
    if atribuicao != "RI" or not _tem_tabela(con, "ri_atos"):
        return ""
    linha = con.execute("SELECT MAX(lavrado_em) FROM ri_atos WHERE matricula_id = ?",
                        (int(alvo_id),)).fetchone()
    return (linha[0] or "") if linha else ""


def supridos_do_alvo(con: sqlite3.Connection, atribuicao: str, alvo_id: int) -> list[dict]:
    desde = _desde(con, atribuicao, alvo_id)
    saida = []
    for rid, texto in con.execute(
            """SELECT id, resultado_json FROM rv_revisoes WHERE atribuicao=? AND alvo_id=?
                  AND situacao='PRONTA' AND resultado_json IS NOT NULL ORDER BY id""",
            (atribuicao, int(alvo_id))):
        try:
            d = json.loads(texto)
        except ValueError:
            continue
        for a in d.get("achados") or []:
            s = a.get("suprido") if isinstance(a, dict) else None
            if isinstance(s, dict) and not s.get("herdado") and (s.get("em") or "") >= desde:
                saida.append({"revisao_id": rid, "gravidade": a.get("gravidade"),
                              "o_que": a.get("o_que"),
                              "chave": chave_do_achado(a.get("o_que")), **s})
    return saida


def _cobre(suprido: dict, achado: dict) -> bool:
    if achado.get("gravidade") == "GRAVE" and suprido.get("gravidade") != "GRAVE":
        return False
    return mesmo_assunto(suprido["chave"], chave_do_achado(achado.get("o_que")))


def anotar_supridos(con: sqlite3.Connection, r: dict | None) -> dict | None:
    """Põe em cada achado a marca de suprido (desta revisão ou herdada de outra do
    mesmo ato) e conta `graves_pendentes`. Só lê."""
    if not r or not r.get("id"):
        return r
    linha = con.execute("SELECT atribuicao, alvo_id FROM rv_revisoes WHERE id = ?",
                        (r["id"],)).fetchone()
    if linha is None:
        return r
    anteriores = supridos_do_alvo(con, linha[0], linha[1])
    pendentes = 0
    for a in r.get("achados") or []:
        if not isinstance(a.get("suprido"), dict):
            herdado = next((s for s in reversed(anteriores)
                            if s["revisao_id"] != r["id"] and _cobre(s, a)), None)
            if herdado:
                a["suprido"] = {"por": herdado.get("por"), "papel": herdado.get("papel"),
                                "em": herdado.get("em"), "obs": herdado.get("obs"),
                                "herdado": True, "revisao_id": herdado["revisao_id"],
                                "o_que_original": herdado.get("o_que")}
        if a.get("gravidade") == "GRAVE" and not a.get("suprido"):
            pendentes += 1
    r["graves_pendentes"] = pendentes
    return r


def graves_pendentes(con: sqlite3.Connection, revisao_id: int) -> int:
    r = mostrar(con, revisao_id)
    if not r:
        return 0
    return int(anotar_supridos(con, r).get("graves_pendentes") or 0)


def suprir(con: sqlite3.Connection, revisao_id: int, itens, *, usuario: str = "",
           papel: str | None = None) -> list[dict]:
    """Marca apontamentos como «já verificado/suprido». ESCREVE `resultado_json`.
    `itens` = [(índice, observação)]. Tudo é conferido antes de gravar."""
    linha = con.execute("SELECT situacao, resultado_json FROM rv_revisoes WHERE id = ?",
                        (int(revisao_id),)).fetchone()
    if linha is None:
        raise RevisaoPendente("Revisão não encontrada.")
    if linha[0] != "PRONTA" or not linha[1]:
        raise RevisaoPendente("Só se marca apontamento de revisão já terminada.")
    d = json.loads(linha[1])
    achados = d.get("achados") or []
    pode = (papel or "").upper() in PAPEIS_QUE_SUPREM
    feitos, agora = [], _agora()
    for indice, obs in itens:
        indice = int(indice)
        if not 0 <= indice < len(achados):
            raise RevisaoPendente(f"O apontamento {indice + 1} não existe nesta revisão.")
        a = achados[indice]
        obs = " ".join((obs or "").split())[:600]
        if a.get("gravidade") == "GRAVE":
            if not pode:
                raise RevisaoPendente("Apontamento GRAVE só o gerente ou o administrador "
                                      "marca como suprido.")
            if len(obs) < MINIMO_DA_JUSTIFICATIVA:
                raise RevisaoPendente("Para marcar um apontamento GRAVE como suprido, "
                                      "escreva na observação como ele foi suprido "
                                      "(mínimo de dez letras).")
        if isinstance(a.get("suprido"), dict) and not a["suprido"].get("herdado"):
            continue
        a["suprido"] = {"por": usuario, "papel": papel, "em": agora, "obs": obs}
        feitos.append({"indice": indice, "gravidade": a.get("gravidade"),
                       "o_que": a.get("o_que"), "obs": obs})
    if feitos:
        d["achados"] = achados
        con.execute("UPDATE rv_revisoes SET resultado_json = ? WHERE id = ?",
                    (json.dumps(d, ensure_ascii=False), int(revisao_id)))
    return feitos


def _texto_revisado(dossie: str) -> tuple[str | None, str]:
    """(tipo, texto) do ato que a revisão leu - o fim do dossiê."""
    marca = "=== ATO A LAVRAR ==="
    if marca not in (dossie or ""):
        return None, ""
    linhas = dossie.rsplit(marca, 1)[1].strip("\n").split("\n")
    tipo, corpo = None, []
    for linha in linhas:
        if not corpo and linha.startswith("Tipo:"):
            tipo = linha[5:].strip()
            continue
        if not corpo and linha.startswith("Natureza do título:"):
            continue
        corpo.append(linha)
    return tipo, "\n".join(corpo).strip()


def _revisao_anterior(con: sqlite3.Connection, atribuicao: str, alvo_id: int,
                      texto_atual: str | None, tipo: str | None):
    import difflib
    r = con.execute(
        """SELECT id, situacao, pedido_em, dossie FROM rv_revisoes
            WHERE atribuicao=? AND alvo_id=? AND situacao='PRONTA' AND pedido_em >= ?
         ORDER BY id DESC LIMIT 1""",
        (atribuicao, int(alvo_id), _desde(con, atribuicao, alvo_id))).fetchone()
    if r is None:
        raise RevisaoPendente("Não há revisão anterior deste ato para aproveitar. "
                              "Clique em «Revisar com IA».")
    tipo_rev, texto_rev = _texto_revisado(r[3])
    if tipo and tipo_rev and tipo_rev.upper() != str(tipo).upper():
        raise RevisaoPendente("A última revisão é de outro tipo de ato. Clique em "
                              "«Revisar com IA».")
    a, b = normalizar(texto_rev), normalizar(texto_atual)
    semelhanca = (difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()
                  if a and b else 0.0)
    if semelhanca < SEMELHANCA_MINIMA_DO_TEXTO:
        raise RevisaoPendente(
            f"O texto mudou demais desde a última revisão ({semelhanca:.0%} igual; "
            f"para aproveitá-la é preciso {SEMELHANCA_MINIMA_DO_TEXTO:.0%}). "
            "Clique em «Revisar com IA».")
    return r, semelhanca


def _anotar_liberacao(con: sqlite3.Connection, revisao_id: int, liberacao: dict) -> None:
    linha = con.execute("SELECT resultado_json FROM rv_revisoes WHERE id = ?",
                        (int(revisao_id),)).fetchone()
    try:
        d = json.loads(linha[0]) if linha and linha[0] else {"achados": [], "parecer": ""}
    except ValueError:
        d = {"achados": [], "parecer": ""}
    d.setdefault("liberacoes", []).append(liberacao)
    con.execute("UPDATE rv_revisoes SET resultado_json = ? WHERE id = ?",
                (json.dumps(d, ensure_ascii=False), int(revisao_id)))


# ----------------------------------------- MODO CONSULTIVO - HOTFIX-2026-10-13-01

def modo(con: sqlite3.Connection) -> str:
    """'consultivo' (padrão) ou 'bloqueante'. Reversível por settings."""
    if not _tem_tabela(con, "settings"):
        return "consultivo"
    linha = con.execute("SELECT value FROM settings WHERE key = ?", (CHAVE_MODO,)).fetchone()
    valor = str(linha[0]).strip().lower() if linha and linha[0] is not None else ""
    return "bloqueante" if valor == "bloqueante" else "consultivo"


def _exigir_consultivo(con, atribuicao, alvo_id, hash_texto, *, justificativa, usuario,
                       papel, texto_atual, tipo, contexto_oficio, prosseguir):
    """None = segue a regra antiga; texto = liberado (e como)."""
    privilegiado = (papel or "").upper() in PAPEIS_QUE_SUPREM or bool(contexto_oficio)
    tem = _tem_tabela(con, "rv_revisoes")
    r = con.execute(
        """SELECT id, situacao, graves, pedido_em FROM rv_revisoes
            WHERE atribuicao=? AND alvo_id=? AND hash_texto=? ORDER BY id DESC""",
        (atribuicao, alvo_id, hash_texto)).fetchone() if tem else None
    if r is None:
        if privilegiado:
            return "consultivo:sem_revisao"
        if not tem:
            return None
        try:
            ant, semelhanca = _revisao_anterior_auto(con, atribuicao, alvo_id, texto_atual, tipo)
        except RevisaoPendente:
            return None
        if graves_pendentes(con, ant[0]):
            return None
        _anotar_liberacao(con, ant[0], {"tipo": "REVISAO_ANTERIOR_AUTOMATICA", "por": usuario,
                                        "papel": papel, "em": _agora(),
                                        "semelhanca": round(semelhanca, 3),
                                        "hash_lavrado": hash_texto})
        return f"anterior:{ant[0]}:{semelhanca:.3f}"
    situacao = _situacao_viva(r[1], r[3])
    if situacao in ("PENDENTE", "LENDO"):
        return "consultivo:lendo" if privilegiado else None
    if situacao == "ERRO":
        return "falhou"
    pendentes = graves_pendentes(con, r[0])
    if not pendentes:
        return "ok"
    if not privilegiado:
        return None
    texto = " ".join((justificativa or "").split())
    if not prosseguir and len(texto) < MINIMO_DA_JUSTIFICATIVA:
        raise RevisaoPendente(
            f"A revisão apontou {pendentes} problema(s) grave(s). Confira e, se estiver "
            "certo, marque «Prosseguir mesmo assim» e clique em lavrar de novo "
            "(os campos continuam preenchidos).")
    con.execute("""UPDATE rv_revisoes SET justificativa=?, justificado_por=?,
                       justificado_em=? WHERE id=?""",
                (texto or "Prosseguiu (revisão consultiva).", usuario, _agora(), r[0]))
    return "consultivo:prosseguiu"


def _revisao_anterior_auto(con, atribuicao, alvo_id, texto_atual, tipo):
    import difflib
    r = con.execute(
        """SELECT id, situacao, pedido_em, dossie FROM rv_revisoes
            WHERE atribuicao=? AND alvo_id=? AND situacao='PRONTA' AND pedido_em >= ?
         ORDER BY id DESC LIMIT 1""",
        (atribuicao, int(alvo_id), _desde(con, atribuicao, alvo_id))).fetchone()
    if r is None:
        raise RevisaoPendente("sem revisão anterior")
    _tipo_rev, texto_rev = _texto_revisado(r[3])
    a, b = normalizar(texto_rev), normalizar(texto_atual)
    semelhanca = (difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()
                  if a and b else 0.0)
    if semelhanca < SEMELHANCA_AUTOMATICA:
        raise RevisaoPendente("mudou demais")
    return r, semelhanca
