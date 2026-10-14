"""Camada 4b do gestor: a IA lê o texto do ato e aponta o que não fecha.

    «revise minutas» — o oficial, 06/10/2026, no pedido do gestor

O QUE ELA LÊ
    Registros (R) do RI desde o corte, minutas do RI esperando revisão, e
    escrituras/procurações/atas das Notas com texto. Minuta primeiro: é onde o
    defeito ainda se conserta sem averbação.

O QUE SAI DA SERVENTIA, E COMO
    O texto passa por `ajuda_privacidade.sanitizar_para_modelo` — a MESMA
    barreira da ajuda e do agente — antes de ir ao provedor que o oficial
    escolheu na tela do agente (`ag_config.provedor_padrao`), com a chave
    guardada fora do banco. CPF e nome saem como marcas.

    **E POR ISSO ELA NÃO CONFERE NOME NEM DOCUMENTO**: medido em 06/10, a
    máscara troca «JOSE» e «JOSÉ» por marcas diferentes. Isso é a camada 4a
    (`gestor_conferencia.regra_texto_contra_cadastro`), por regra, aqui dentro.
    A IA olha o que a máscara não estraga: valor em número contra valor por
    extenso, datas, área, elementos que o tipo de ato exige, contradição
    interna do texto.

O QUE ELA NÃO FAZ
    Não decide, não lavra, não corrige. O que ela aponta vira achado ATENÇÃO
    para quem qualifica, e quem decide é gente.

O QUANTO ELA GASTA
    Um texto é lido uma vez por versão (o hash do dossiê): minuta que não
    mudou não volta à IA. Teto diário de leituras, e a rede nunca dentro de
    transação.
"""
from __future__ import annotations

import hashlib
import html as _html
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from gestor_conferencia import IMPLANTACAO

TETO_POR_DIA = 40
LIMITE_DO_TEXTO = 20000
#: O provedor pode «pensar» antes de responder, e o pensamento come deste teto.
MAXIMO_DE_SAIDA = 8000
#: Em ordem de preferência; o primeiro com chave guardada é o que lê.
PROVEDORES_DA_LEITURA = ("claude",)

SCHEMA = """
CREATE TABLE IF NOT EXISTS ge_leituras (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
"""

INSTRUCAO = """Você confere atos de um cartório brasileiro (registro de imóveis e notas).
Recebe os DADOS ESTRUTURADOS que o sistema guardou e o TEXTO do ato.
Marcas entre colchetes, como [PESSOA_01], [CPF_02] ou [REFERENCIA_REGISTRAL_01], são
dados mascarados de propósito: NÃO os confira e NÃO aponte nada sobre eles.

Aponte SOMENTE problemas objetivos e verificáveis no próprio texto:
- valor em algarismos diferente do valor por extenso; área em algarismos diferente da por extenso;
- datas impossíveis ou contraditórias entre si; data do ato diferente da data dos dados;
- valor, área ou natureza do texto diferente dos DADOS ESTRUTURADOS;
- elemento essencial do tipo de ato que falta (ex.: num registro de compra e venda,
  o valor do negócio; numa procuração, os poderes; numa escritura, o objeto);
- contradição interna (o mesmo bem ou a mesma pessoa descritos de dois jeitos).
Não opine sobre direito, estilo, ortografia ou formatação. Não invente.

NÃO SÃO problemas (já foram apontados por engano e conferidos):
- «solteiro» (ou divorciado, viúvo) e «convivente em união estável» juntos: a união
  estável não muda o estado civil, e o texto está certo;
- área rural escrita em hectares, ares e centiares (ex.: 30,77,70 ha) — é a forma do livro;
- campo dos DADOS ESTRUTURADOS vazio: ausência de dado no sistema não é erro do texto;
- marcas de pessoa diferentes ([PESSOA_06] num lugar, [PESSOA_24] noutro): a máscara dá
  marca nova a cada grafia, e a mesma pessoa pode aparecer com nome de solteira, abreviado
  ou com acento — nunca aponte identidade de pessoas;
- preço diferente de base de cálculo ou de valor de avaliação: são valores distintos por lei.

Responda APENAS com JSON, sem texto em volta, no formato:
{"achados": [{"gravidade": "GRAVE" ou "ATENCAO", "o_que": "frase curta", "trecho": "até 120 caracteres do texto"}]}
Se não houver nada: {"achados": []}"""


def init_leitura_schema(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA)


def _texto_plano(t) -> str:
    t = _html.unescape(re.sub(r"<[^>]+>", " ", str(t or "")))
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n", t)).strip()


def candidatos(con: sqlite3.Connection) -> list[dict]:
    """O que pode ser lido, minuta primeiro. Só lê."""
    con.row_factory = sqlite3.Row
    saida = []
    for m in con.execute(
            """SELECT n.id, n.tipo, n.numero_pretendido, n.teor, n.natureza_titulo,
                      n.data_pretendida, x.numero AS mat, x.area_valor, x.area_unidade
                 FROM ri_minutas n LEFT JOIN ri_matriculas x ON x.id = n.matricula_id
                WHERE n.situacao = 'A_REVISAR' AND COALESCE(n.teor,'') <> ''"""):
        saida.append({"tabela": "ri_minutas", "id": m["id"], "setor": "RI_QUALIFICACAO",
                      "rotulo": f"minuta {m['tipo']}-{m['numero_pretendido'] or '?'}",
                      "dados": {"tipo de ato": m["tipo"], "natureza": m["natureza_titulo"],
                                "data pretendida": m["data_pretendida"]},
                      # A ÁREA DO CADASTRO SAIU EM 06/10/2026: ela está gravada
                      # em hectare inteiro («16» onde o livro diz 16,6335 ha —
                      # 1.298 fichas assim) e a IA acusava a diferença.
                      "teor": m["teor"]})
    for a in con.execute(
            """SELECT id, tipo, data, natureza, valor_transacao, valor_lavrado, teor, situacao
                 FROM nt_atos WHERE (data >= ? OR situacao = 'EM_LAVRATURA')
                  AND tipo IN ('ESCRITURA','PROCURACAO','ATA') AND COALESCE(teor,'') <> ''
             ORDER BY situacao = 'LAVRADO', id DESC""", (IMPLANTACAO,)):
        item = {"tabela": "nt_atos", "id": a["id"], "setor": "NOTAS_QUALIFICACAO",
                "rotulo": f"{a['tipo'].lower()} {a['id']} ({a['situacao'].lower()})",
                "dados": {"tipo de ato": a["tipo"], "data": a["data"],
                          "natureza": a["natureza"], "valor da transação": a["valor_transacao"],
                          "valor lavrado": a["valor_lavrado"]},
                "teor": a["teor"]}
        # A PROCURAÇÃO SE LÊ COMO NO BOTÃO — ordem do oficial em 13/10/2026
        # («atualiza o gestor»): o mesmo Sonnet, a mesma instrução e o mesmo
        # dossiê com o cadastro inteiro das partes. Duas réguas para o mesmo
        # ato divergiriam — o botão aprovando o que a leitura diária acusa.
        import revisao_previa as RV
        if a["tipo"] in RV.TIPOS_DA_PROCURACAO:
            item.update(dossie_pronto=RV.dossie_notas(con, a["id"]),
                        instrucao=RV.INSTRUCAO_DA_PROCURACAO,
                        modelo_claude=RV.MODELO_DA_PROCURACAO)
        saida.append(item)
    import revisao_previa as RV
    revistos = set()
    if con.execute("SELECT 1 FROM sqlite_master WHERE name='rv_revisoes'").fetchone():
        revistos = {(r[0], r[1]) for r in con.execute(
            "SELECT alvo_id, hash_texto FROM rv_revisoes WHERE atribuicao='RI' "
            "AND situacao='PRONTA'")}
    for a in con.execute(
            """SELECT a.id, a.matricula_id, a.tipo, a.numero, a.data_ato, a.natureza_titulo,
                      a.teor FROM ri_atos a
                WHERE a.lavrado_em >= ? AND COALESCE(a.acervo,0) = 0 AND a.tipo IN ('R','AV')
                  AND COALESCE(a.cancelado,0) = 0 AND COALESCE(a.teor,'') <> ''
             ORDER BY a.id DESC""", (IMPLANTACAO,)):
        # AS AVERBAÇÕES ENTRARAM EM 06/10/2026, com a ficha como contexto (o
        # ato se lê contra a matrícula). O que já passou pela revisão antes da
        # lavratura não se relê: o Opus já leu aquele mesmo texto.
        if (a["matricula_id"], RV.hash_do_ato(a["tipo"], a["teor"])) in revistos:
            continue
        saida.append({"tabela": "ri_atos", "id": a["id"], "setor": "RI_QUALIFICACAO",
                      "rotulo": f"{a['tipo']}-{a['numero']}",
                      "dossie_pronto": RV.dossie_ri_lavrado(con, a["id"]),
                      "dados": {}, "teor": a["teor"]})
    for a in con.execute(
            """SELECT id, tipo, numero, data_ato, natureza_titulo, teor FROM ra_atos
                WHERE COALESCE(data_ato, criado_em, '') >= ? AND COALESCE(teor,'') <> ''
             ORDER BY id DESC""", (IMPLANTACAO,)):
        saida.append({"tabela": "ra_atos", "id": a["id"], "setor": "RI_QUALIFICACAO",
                      "rotulo": f"Livro 3, {a['tipo'] or 'ato'} {a['numero'] or a['id']}",
                      "dados": {"data do ato": a["data_ato"], "natureza": a["natureza_titulo"]},
                      "teor": a["teor"]})
    return saida


def dossie(c: dict) -> str:
    if c.get("dossie_pronto"):
        return c["dossie_pronto"]
    dados = "\n".join(f"- {k}: {v}" for k, v in c["dados"].items() if v not in (None, ""))
    texto = _texto_plano(c["teor"])[:LIMITE_DO_TEXTO]
    return f"ATO: {c['rotulo']}\n\nDADOS ESTRUTURADOS:\n{dados}\n\nTEXTO DO ATO:\n{texto}"


def _instrucao(c: dict) -> str:
    """A régua do candidato: a da procuração (13/10/2026) ou a geral."""
    return c.get("instrucao") or INSTRUCAO


def _hash(t: str, instrucao: str = INSTRUCAO) -> str:
    """O texto enviado E a instrução: mudou a régua, relê-se — a escritura 778
    ficou com um apontamento velho porque só o texto entrava na conta."""
    return hashlib.sha256((instrucao + "\n\n" + t).encode("utf-8")).hexdigest()


def _ler_json(texto: str) -> list[dict]:
    """O JSON da resposta. Resposta que não é JSON vira erro, e não «nada achado»."""
    bruto = (texto or "").strip()
    inicio, fim = bruto.find("{"), bruto.rfind("}")
    if inicio < 0 or fim <= inicio:
        raise ValueError(f"resposta sem JSON: {bruto[:120]!r}")
    dados = json.loads(bruto[inicio:fim + 1])
    achados = dados.get("achados")
    if not isinstance(achados, list):
        raise ValueError("JSON sem a lista «achados»")
    return [a for a in achados if isinstance(a, dict) and a.get("o_que")]


def ler_pendentes(con: sqlite3.Connection, pasta_dados: Path, *,
                  teto: int = TETO_POR_DIA, conversar=None) -> dict:
    """Lê o que ainda não foi lido nesta versão. FALA COM A REDE, fora de transação."""
    import agente_provedores as AP
    import agente_schema as AS
    from ajuda_privacidade import sanitizar_para_modelo
    conversar = conversar or AP.conversar
    con.row_factory = sqlite3.Row
    init_leitura_schema(con)
    con.commit()
    # O CLAUDE PRIMEIRO, E A ESCOLHA É MEDIDA: em 06/10/2026 o DeepSeek
    # (o padrão da tela do agente) devolveu texto VAZIO em 2 de 3 minutas
    # curtas — gastou os 8.000 de saída pensando. A tela do agente continua com
    # o que o oficial escolheu; esta leitura usa o que respondeu.
    configurado = AS.ler_config(con, AS.CHAVE_PROVEDOR) or "claude"
    provedor = next((p for p in PROVEDORES_DA_LEITURA if AP.tem_chave(pasta_dados, p)),
                    configurado)
    modelo = None if provedor != configurado else (AS.ler_config(con, AS.CHAVE_MODELO) or None)
    if not AP.tem_chave(pasta_dados, provedor):
        return {"lidos": 0, "sem_chave": provedor}

    def modelo_do(c: dict):
        # O Sonnet da procuração só vale no Claude: noutro provedor o nome
        # do modelo não existe, e vale o modelo da leitura.
        return c.get("modelo_claude") if provedor == "claude" and c.get("modelo_claude") else modelo
    hoje = datetime.now().date().isoformat()
    feitos_hoje = con.execute(
        "SELECT count(*) FROM ge_leituras WHERE lido_em LIKE ?", (hoje + "%",)).fetchone()[0]
    lidos = erros = 0
    for c in candidatos(con):
        if feitos_hoje + lidos + erros >= teto:
            break
        texto = dossie(c)
        h = _hash(texto, _instrucao(c))
        if con.execute("""SELECT 1 FROM ge_leituras WHERE tabela=? AND ato_id=?
                             AND hash_dossie=? AND erro IS NULL""",
                       (c["tabela"], c["id"], h)).fetchone():
            continue
        agora = datetime.now().isoformat(timespec="seconds")
        # SEM MÁSCARA, por decisão do oficial (06/10/2026) — ver revisao_previa.
        import revisao_previa as RV
        enviado = sanitizar_para_modelo(texto) if RV.mascarar_na_revisao(con) else texto
        try:
            resposta = conversar(pasta_dados, provedor=provedor, sistema=_instrucao(c),
                                 conversa=[{"tipo": "user", "texto": enviado}],
                                 ferramentas=[], modelo=modelo_do(c),
                                 maximo_de_saida=MAXIMO_DE_SAIDA)
            if not (resposta.get("texto") or "").strip():
                # MEDIDO EM 06/10/2026: com 1.500 de saída o DeepSeek gastava
                # tudo pensando e devolvia texto VAZIO nos dossiês longos.
                raise ValueError(f"resposta vazia (parou: {resposta.get('parou')}, "
                                 f"saída {resposta.get('saida')})")
            achados = _ler_json(resposta.get("texto"))
            con.execute(
                """INSERT OR REPLACE INTO ge_leituras (tabela, ato_id, hash_dossie, lido_em,
                       provedor, modelo, achados_json, tokens_entrada, tokens_saida)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (c["tabela"], c["id"], h, agora, provedor,
                 resposta.get("modelo") or modelo_do(c),
                 json.dumps(achados, ensure_ascii=False),
                 resposta.get("entrada"), resposta.get("saida")))
            lidos += 1
        except Exception as erro:                       # noqa: BLE001 — vai à tabela
            con.execute(
                """INSERT OR REPLACE INTO ge_leituras (tabela, ato_id, hash_dossie, lido_em,
                       provedor, modelo, erro) VALUES (?,?,?,?,?,?,?)""",
                (c["tabela"], c["id"], h, agora, provedor, modelo_do(c),
                 f"{type(erro).__name__}: {str(erro)[:300]}"))
            erros += 1
        con.commit()
    return {"lidos": lidos, "erros": erros, "provedor": provedor}


def achados_vigentes(con: sqlite3.Connection) -> list[dict]:
    """O que as leituras apontaram e ainda vale: a versão atual, não revisada.

    Para a minuta, só enquanto ela espera revisão — lavrada ou descartada, o
    apontamento sobre o rascunho deixa de ser assunto. E só a leitura do texto
    de HOJE: texto que mudou depois da leitura não herda o apontamento velho.
    """
    con.row_factory = sqlite3.Row
    init_leitura_schema(con)
    atuais = {(c["tabela"], c["id"]): (c, _hash(dossie(c), _instrucao(c))) for c in candidatos(con)}
    saida = []
    for r in con.execute(
            """SELECT * FROM ge_leituras WHERE erro IS NULL AND revisado_em IS NULL
                  AND achados_json IS NOT NULL AND achados_json <> '[]'"""):
        atual = atuais.get((r["tabela"], r["ato_id"]))
        if atual is None or atual[1] != r["hash_dossie"]:
            continue
        c = atual[0]
        for i, a in enumerate(json.loads(r["achados_json"])):
            saida.append({"chave": f"LEITURA:{r['tabela']}:{r['ato_id']}:{r['hash_dossie'][:8]}:{i}",
                          "leitura_id": r["id"],
                          "setor": c["setor"], "rotulo": c["rotulo"],
                          "grave": str(a.get("gravidade", "")).upper() == "GRAVE",
                          "o_que": str(a.get("o_que"))[:200],
                          "trecho": str(a.get("trecho") or "")[:160],
                          "provedor": r["provedor"]})
    return saida


def marcar_revisado(con: sqlite3.Connection, leitura_id: int, por: str) -> None:
    """Quem conferiu o apontamento e o deu por resolvido. O achado sai na próxima rodada."""
    con.execute("UPDATE ge_leituras SET revisado_em=?, revisado_por=? WHERE id=?",
                (datetime.now().isoformat(timespec="seconds"), por, leitura_id))
    con.commit()
