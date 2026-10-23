"""O agente de minutas do RI e das Notas — ordem do oficial em 23/10/2026.

O PEDIDO, NAS PALAVRAS DELE:

    «agora vamos criar um agente para preparar as minutas dos atos do RI e do
     Notas (escrituras, procurações e atas notariais), nos moldes que temos no
     RCPN, mas com algumas alterações. O agente usaria a API do claude em opus
     high para ler a documentação do sistema presente no protocolo geral e na
     prenotação ligadas à matrícula (usuário poderia selecionar antes de ligar o
     agente) ou própria documentação anexada no momento de pedido ao agente (que
     já seria anexada no arquivamento do ato). Esse agente teria que gerar a
     minuta, mas precisaria ter espaço para instruções iniciais e instruções de
     revisão (caso escrevente precise pedir para mudar alguma coisa).»

O QUE ELE É, E O QUE NÃO É
    É o redator do primeiro texto. Lê os documentos que a pessoa marcou — os da
    prenotação e do protocolo geral, ou os que ela juntou na hora —, lê a
    matrícula ou o ato que já existe, e devolve a MINUTA: o teor, as partes que
    achou, e a lista do que não conseguiu afirmar.

    NÃO LAVRA, NÃO NUMERA, NÃO SELA E NÃO COBRA (Código de Normas do MA, arts.
    169, I, 171 e 176: a IA redige e revisa; quem pratica o ato é a pessoa). A
    minuta pousa onde o sistema já guarda texto que ainda não é ato:

      • RI    → `ri_minutas`, situação A_REVISAR, na ficha da matrícula — a
                mesma fila das minutas importadas; quem lavra é `ri_lavrar_ato`;
      • Notas → o teor do ato EM_LAVRATURA — o mesmo campo que «Montar» e
                «Preencher a partir do modelo» gravam; quem lança no livro é a
                tela de sempre.

O QUE «NOS MOLDES DO RCPN» QUER DIZER, E O QUE MUDOU
    Como no RCPN (`rc_leitura_documentos`): os documentos sobem inteiros, sem
    máscara (documento digitalizado não se mascara — decisão do oficial de
    12/10/2026), a leitura roda num botão da própria tela do ato, e o que volta
    é rascunho para conferir com o original. As alterações pedidas:

      • o modelo é o Opus no esforço alto, e não a triagem barata em lotes;
      • os documentos se ESCOLHEM antes de ligar o agente, entre os que o
        sistema já tem (prenotação e protocolo geral), ou se juntam na hora —
        e o que se junta na hora fica guardado onde o ato o arquiva: na
        prenotação (RI) ou no próprio ato (Notas);
      • há INSTRUÇÕES INICIAIS e INSTRUÇÕES DE REVISÃO. A revisão parte do
        texto ATUAL da minuta — com o que a pessoa já corrigiu à mão —, e não
        do que o agente escreveu da vez anterior.

POR QUE EM SEGUNDO PLANO
    O Opus pensando no esforço alto, com uma escritura de vinte páginas, leva
    minutos. Prender o balcão nesse tempo seria pior que esperar: o pedido
    entra, a tela mostra «preparando» e pergunta de tempos em tempos — a forma
    da revisão prévia (`revisao_previa.executar`).

O QUE NÃO SE SOBRESCREVE CALADO
    A minuta só pousa sozinha se o texto de destino está como estava quando se
    pediu. Se alguém mexeu na minuta (ou no teor do ato) enquanto o agente
    trabalhava, o resultado fica guardado e a tela pergunta antes de trocar —
    escrever por cima do que uma pessoa corrigiu é perder trabalho sem aviso.

TODA VERSÃO FICA
    Cada pedido é uma linha de `mi_pedidos`, com o texto que o agente devolveu.
    A revisão é um pedido novo, apontando para o anterior: a história da minuta
    é a lista de pedidos, e nenhuma versão se apaga.
"""
from __future__ import annotations

import base64
import hashlib
import html
import json
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

import banco_pg
from bd_nativo import Banco, banco

# ------------------------------------------------------------------ o modelo

PROVEDOR = "claude"
#: O MODELO E O ESFORÇO SÃO OS QUE O OFICIAL PEDIU — «claude em opus high».
MODELO = "claude-opus-5-5"
ESFORCO = "high"
#: O pensamento do Opus conta dentro deste teto, e uma escritura longa precisa
#: de espaço para o texto depois de pensar: com pouco, a resposta sai cortada no
#: meio de uma cláusula (`max_tokens`), e a tela diz isso em vez de gravar.
MAXIMO_DE_SAIDA = 32_000
#: Segundos por tentativa. O pedido é um só turno, sem ferramentas, e o tempo é
#: o do modelo lendo e pensando — o padrão de 120 s do transporte não basta.
PRAZO = 900
#: O DESVIO DO PRÓPRIO PROVEDOR quando o modelo recusa o pedido (a categoria da
#: recusa escolhe o modelo de reserva). Sem ele, uma escritura com uma palavra
#: que acenda o filtro pararia o balcão; com ele, a resposta vem de outro modelo
#: — e a tela diz qual modelo respondeu.
BETA_DO_DESVIO = "server-side-fallback-2026-07-01"
#: Até 30 MB por pedido (o teto do provedor é 32 MB). O PDF sobe inteiro, em
#: base64 — um terço maior que o arquivo.
LIMITE_DE_ENVIO = 30_000_000
#: O que se lê do arquivo antes de virar base64: 21 MB de documentos dão ~28 MB
#: de pedido, e o resto é a matrícula e as instruções.
LIMITE_DOS_DOCUMENTOS = 21 * 1024 * 1024
MAXIMO_DE_DOCUMENTOS = 20
#: Leitura que não termina vira ERRO para o balcão — não pode travar a tela.
MINUTOS_PARA_DESISTIR = 25
MINIMO_DA_INSTRUCAO_DE_REVISAO = 10
LIMITE_DO_CONTEXTO = 150_000
#: Quantos atos da casa vão como exemplo de redação.
EXEMPLOS_DE_ESTILO = 2

FINALIDADE = "minuta_ia"
RI, NOTAS = "RI", "NOTAS"
ATRIBUICOES = (RI, NOTAS)

#: As espécies das Notas que o agente prepara — as três famílias do pedido
#: («escrituras, procurações e atas notariais»). Testamento fica de fora: o
#: testamento público se lavra na presença do testador, pelo que ele declara, e
#: não a partir de documento.
TIPOS_DAS_NOTAS = ("ESCRITURA", "PROCURACAO", "PROCURACAO_PREVIDENCIARIA",
                   "SUBSTABELECIMENTO", "REVOGACAO", "ATA", "ATA_USUCAPIAO")

PENDENTE, LENDO, PRONTA, ERRO = "PENDENTE", "LENDO", "PRONTA", "ERRO"

#: A origem da minuta do RI preparada aqui — ao lado de IMPORTACAO, MANUAL e
#: DESFEITO_DE_ATO, em `ri_minuta`.
ORIGEM_DA_MINUTA = "AGENTE_IA"

SCHEMA = (
    ("mi_pedidos", """
CREATE TABLE IF NOT EXISTS mi_pedidos (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    atribuicao TEXT NOT NULL,              -- RI | NOTAS
    alvo_id bigint NOT NULL,               -- ri_matriculas.id (RI) ou nt_atos.id (Notas)
    anterior_id bigint,                    -- o pedido revisado, quando é revisão
    versao INTEGER NOT NULL DEFAULT 1,
    minuta_id bigint,                      -- RI: a minuta em que pousou
    tipo_ato TEXT,                         -- RI: R | AV; Notas: o tipo do ato
    natureza TEXT,
    prenotacao_id bigint,                  -- RI: a prenotação de onde vem o título
    instrucao TEXT,                        -- as instruções iniciais
    revisao TEXT,                          -- as instruções de revisão
    documentos_json TEXT NOT NULL,         -- [{anexo_id, nome, sha256, origem}]
    alvo_hash_antes TEXT,                  -- o texto de destino quando se pediu
    situacao TEXT NOT NULL DEFAULT 'PENDENTE',  -- PENDENTE | LENDO | PRONTA | ERRO
    pedido_em TEXT NOT NULL,
    pedido_por TEXT,
    terminado_em TEXT,
    modelo TEXT,
    esforco TEXT,
    teor TEXT,                             -- o que o agente escreveu
    resultado_json TEXT,                   -- partes, pendências, fontes, observações
    aplicado_em TEXT,                      -- quando pousou na minuta ou no ato
    texto_substituido TEXT,                -- o que estava lá antes de pousar
    aplicado_por TEXT,
    nao_aplicado_motivo TEXT,
    tokens_entrada bigint,
    tokens_saida bigint,
    segundos INTEGER,
    erro TEXT
)"""),
    ("ix_mi_pedidos_alvo", """
CREATE INDEX IF NOT EXISTS ix_mi_pedidos_alvo
    ON mi_pedidos (atribuicao, alvo_id, id)"""),
)


class MinutaIAError(ValueError):
    """Erro de regra, com mensagem pronta para o balcão."""


def init_schema(con) -> None:
    bd = banco(con)
    for nome, comando in SCHEMA:
        if not bd.tem_tabela(nome):
            bd.escrever(comando)


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _texto(v) -> str:
    return str(v or "").strip()


def texto_corrido(valor: str | None) -> str:
    """O texto sem HTML, com os parágrafos preservados. Só LÊ.

    `revisao_previa.normalizar` junta tudo numa linha — bom para comparar, ruim
    para ler: o modelo que vê uma escritura sem parágrafos devolve uma escritura
    sem parágrafos.
    """
    t = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</h\d>", "\n", valor or "")
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    linhas = (" ".join(l.split()) for l in t.splitlines())
    return "\n".join(l for l in linhas if l)


def hash_do_texto(texto: str | None) -> str:
    return hashlib.sha256(texto_corrido(texto).encode("utf-8")).hexdigest()


# ------------------------------------------------------- o alvo e o destino


def alvo(con, atribuicao: str, alvo_id: int) -> dict:
    """A matrícula (RI) ou o ato (Notas), conferidos. Só LÊ."""
    bd = banco(con)
    if atribuicao == RI:
        m = bd.um("""SELECT id, numero, livro, situacao, encerrada, teor
                       FROM ri_matriculas WHERE id = %s""", (int(alvo_id),))
        if not m:
            raise MinutaIAError("Matrícula não encontrada.")
        if m["encerrada"]:
            raise MinutaIAError(
                f"A matrícula {m['numero']} está encerrada: não recebe ato novo, e "
                "por isso não há minuta a preparar nela.")
        return dict(m)
    if atribuicao == NOTAS:
        a = bd.um("""SELECT id, tipo, natureza, situacao, teor, modelo_codigo, data,
                            livro, protocolo_id
                       FROM nt_atos WHERE id = %s""", (int(alvo_id),))
        if not a:
            raise MinutaIAError("Ato das Notas não encontrado.")
        if (a["situacao"] or "") != "EM_LAVRATURA":
            raise MinutaIAError(
                "Este ato já foi lançado no livro: o teor dele não muda mais, e o "
                "agente não prepara minuta para ele.")
        if (a["tipo"] or "").upper() not in TIPOS_DAS_NOTAS:
            raise MinutaIAError(
                "O agente prepara escritura, procuração (e substabelecimento e "
                "revogação) e ata notarial. Este ato é de outra espécie.")
        return dict(a)
    raise MinutaIAError(f"«{atribuicao}» não é atribuição do agente de minutas.")


def texto_do_destino(con, pedido: dict) -> str | None:
    """O texto que a minuta tem AGORA — None quando ainda não há minuta. Só LÊ.

    No RI é o teor da minuta em que o pedido pousou (a revisão pousa na mesma);
    nas Notas, o teor do ato.
    """
    bd = banco(con)
    if pedido["atribuicao"] == NOTAS:
        return bd.valor("SELECT teor FROM nt_atos WHERE id = %s", (int(pedido["alvo_id"]),))
    if pedido.get("minuta_id"):
        return bd.valor("SELECT teor FROM ri_minutas WHERE id = %s",
                        (int(pedido["minuta_id"]),))
    return None


# ------------------------------------------------------- os documentos


def _anexo(d: dict, origem: str) -> dict:
    return {"anexo_id": int(d["id"]), "nome": d.get("original_name") or "",
            "sha256": d.get("sha256") or "", "tamanho": d.get("size_bytes") or 0,
            "tipo": d.get("tipo_rotulo") or d.get("description") or "",
            "origem": origem}


def prenotacoes_da_matricula(con, matricula_id: int) -> list[dict]:
    """As prenotações daquela matrícula, das mais novas para as mais velhas. Só LÊ."""
    return banco(con).ler(
        """SELECT id, numero, data_prenotacao, natureza_titulo, apresentante, situacao
             FROM ri_protocolos WHERE matricula_id = %s
            ORDER BY (situacao = 'ABERTO') DESC, id DESC""", (int(matricula_id),))


def documentos_disponiveis(con, atribuicao: str, alvo_id: int) -> list[dict]:
    """Os documentos que o sistema já guarda para aquele ato. Só LÊ.

    RI: os da prenotação (o título apresentado) e os do protocolo geral ligado a
    ela, de cada prenotação da matrícula. Notas: os do próprio ato (o que vai ao
    arquivamento) e os do protocolo geral ligado a ele. A escolha é de quem
    pede — e ela é conferida contra esta lista, para que nenhum outro arquivo da
    casa suba por um número digitado.
    """
    import protocolo_documentos as PDOC
    import ri_documentos as RDOC
    saida: list[dict] = []
    if atribuicao == RI:
        for p in prenotacoes_da_matricula(con, alvo_id):
            rotulo = f"prenotação {p['numero']}"
            for d in RDOC.documentos_de(con, RDOC.ENTIDADE_RI, p["id"]):
                if not d.get("retirado_em"):
                    saida.append(_anexo(d, rotulo) | {"prenotacao_id": p["id"]})
            for d in PDOC.da_prenotacao(con, p["id"])["ativos"]:
                saida.append(_anexo(d, f"protocolo geral {d.get('protocolo_numero')} "
                                       f"(da {rotulo})") | {"prenotacao_id": p["id"]})
    elif atribuicao == NOTAS:
        tudo = PDOC.anexos_do_ato_de_notas(con, alvo_id)
        for d in tudo["do_ato"]:
            saida.append(_anexo(d, "documentos do ato"))
        p = tudo["protocolo"]
        for d in tudo["do_protocolo"]:
            saida.append(_anexo(d, f"protocolo geral {p['numero'] if p else ''}"))
    # O mesmo arquivo pode estar em dois lugares (anexado na prenotação e no
    # protocolo): sobe uma vez só.
    vistos, unicos = set(), []
    for d in saida:
        chave = d["sha256"] or f"id:{d['anexo_id']}"
        if chave not in vistos:
            vistos.add(chave)
            unicos.append(d)
    return unicos


def _ler_arquivo(caminho: Path, nome: str) -> dict:
    """{documentos, imagens, texto} prontos para o transporte, de um arquivo.

    PDF sobe inteiro, como documento: o provedor lê o texto e a imagem de cada
    página. Foto vai como imagem, reduzida (`revisao_anexos._jpeg`). Word e ODT
    viram texto aqui mesmo. O resto não se lê, e a tela diz que ficou de fora.
    """
    import revisao_anexos as RA
    ext = Path(nome or str(caminho)).suffix.lower()
    if ext == ".pdf":
        return {"documentos": [{"mime": "application/pdf", "titulo": nome,
                                "base64": base64.b64encode(caminho.read_bytes())
                                .decode("ascii")}]}
    if ext in RA.EXTENSOES_DE_IMAGEM:
        paginas = RA.paginas_do_arquivo(caminho, nome)
        return {"imagens": [{"mime": "image/jpeg", "base64": paginas[0]["imagem"]()}],
                "texto": f"[a imagem a seguir é o arquivo «{nome}»]"}
    if ext in (".docx", ".odt"):
        return {"texto": f"=== DOCUMENTO «{nome}» (texto do arquivo) ===\n"
                         + RA.texto_de_editor(caminho, ext)}
    raise MinutaIAError(f"o formato {ext or 'sem extensão'} não é lido pelo agente")


# ------------------------------------------------------- o contexto


def _exemplos_ri(bd, tipo: str, matricula_id: int) -> list[str]:
    linhas = bd.ler(
        """SELECT a.tipo, a.numero, a.teor, m.numero AS mat FROM ri_atos a
             JOIN ri_matriculas m ON m.id = a.matricula_id
            WHERE a.tipo = %s AND a.origem = 'MANUAL' AND a.matricula_id <> %s
              AND COALESCE(a.cancelado, 0) = 0 AND a.teor IS NOT NULL
            ORDER BY a.id DESC LIMIT %s""", (tipo, int(matricula_id), EXEMPLOS_DE_ESTILO))
    return [f"--- {x['tipo']}-{x['numero']} da matrícula {x['mat']} ---\n"
            f"{texto_corrido(x['teor'])[:6000]}" for x in linhas]


def contexto_ri(con, matricula_id: int, tipo: str, prenotacao_id=None) -> str:
    """O que o agente precisa saber da ficha, em texto. Só LÊ.

    A ficha inteira (descrição do imóvel e atos), os donos de hoje, o próximo
    número da ficha e dois atos desta casa da mesma espécie, como exemplo de
    redação — «na dúvida, faça como a casa faz».
    """
    bd = banco(con)
    m = bd.um("""SELECT id, numero, livro, situacao, tipo_imovel, rural_urbano,
                        logradouro, bairro, cidade, uf, area_valor, area_unidade,
                        teor FROM ri_matriculas WHERE id = %s""", (int(matricula_id),))
    partes = [f"MATRÍCULA nº {m['numero']} (livro {m['livro'] or '2'}), "
              f"{m['tipo_imovel'] or 'imóvel'} {m['rural_urbano'] or ''}".strip(),
              "", "TEOR DA FICHA:", texto_corrido(m["teor"]) or "(a ficha não tem teor)",
              "", "ATOS DA FICHA:"]
    atos = bd.ler("""SELECT tipo, numero, data_ato, teor FROM ri_atos
                      WHERE matricula_id = %s AND COALESCE(cancelado, 0) = 0
                      ORDER BY numero, id""", (int(matricula_id),))
    for x in atos:
        partes.append(f"{x['tipo']}-{x['numero']} ({x['data_ato'] or '—'}): "
                      f"{texto_corrido(x['teor'])}")
    if not atos:
        partes.append("(nenhum ato no sistema — os atos antigos podem estar dentro "
                      "do teor da ficha)")
    donos = bd.ler("""SELECT nome, documento_numero, qualificacao FROM ri_partes
                       WHERE matricula_id = %s AND proprietario_ativo = 1
                       ORDER BY id""", (int(matricula_id),))
    partes += ["", "PROPRIETÁRIOS ATUAIS (cadastro do sistema):"]
    partes += [f"- {p['nome']} ({p['documento_numero'] or 'sem documento'})"
               f"{': ' + p['qualificacao'] if p['qualificacao'] else ''}"
               for p in donos] or ["(nenhum marcado)"]
    try:
        import ri_numeros_do_teor as NUMT
        proximo = NUMT.piso_do_proximo(bd, int(matricula_id))["proximo"]
        partes += ["", f"PRÓXIMO NÚMERO DE ATO NESTA FICHA: {proximo} "
                       f"(a numeração é contínua entre R e AV)"]
    except Exception:                                # noqa: BLE001 — só informativo
        pass
    if prenotacao_id:
        p = bd.um("""SELECT numero, data_prenotacao, natureza_titulo, apresentante
                       FROM ri_protocolos WHERE id = %s""", (int(prenotacao_id),))
        if p:
            partes += ["", f"PRENOTAÇÃO DO TÍTULO: nº {p['numero']}, de "
                           f"{p['data_prenotacao']}, {p['natureza_titulo'] or ''}, "
                           f"apresentante {p['apresentante'] or '—'}"]
    exemplos = _exemplos_ri(bd, tipo, matricula_id)
    if exemplos:
        partes += ["", "=== EXEMPLOS DE REDAÇÃO DESTA SERVENTIA (só a forma; os dados "
                       "são de OUTRAS matrículas e não se copiam) ==="] + exemplos
    return "\n".join(partes)[-LIMITE_DO_CONTEXTO:]


def _exemplos_notas(bd, tipo: str, ato_id: int) -> list[str]:
    linhas = bd.ler(
        """SELECT id, natureza, teor FROM nt_atos
            WHERE tipo = %s AND id <> %s AND situacao <> 'EM_LAVRATURA'
              AND COALESCE(acervo, 0) = 0 AND teor IS NOT NULL
            ORDER BY id DESC LIMIT %s""", (tipo, int(ato_id), EXEMPLOS_DE_ESTILO))
    return [f"--- {tipo} {x['natureza'] or ''} (ato {x['id']}) ---\n"
            f"{texto_corrido(x['teor'])[:12000]}" for x in linhas]


def contexto_notas(con, ato_id: int) -> str:
    """O ato em lavratura, as partes cadastradas, o modelo e dois exemplos. Só LÊ."""
    import notas_schema as NS
    bd = banco(con)
    a = bd.um("""SELECT id, tipo, natureza, data, livro, modelo_codigo, teor,
                        valor_transacao, regime_bens FROM nt_atos WHERE id = %s""",
              (int(ato_id),))
    tipo = (a["tipo"] or "").upper()
    partes = [f"ATO DAS NOTAS: {NS.TIPOS_ATO.get(tipo, tipo)} — natureza "
              f"«{a['natureza'] or 'não informada'}», data {a['data'] or '—'}",
              "", "PARTES CADASTRADAS NO ATO:"]
    pessoas = bd.ler("""SELECT nome, documento, qualificacao, estado_civil,
                               nacionalidade, profissao, endereco, identidade,
                               filiacao, regime_bens, conjuge, testemunha
                          FROM nt_ato_partes WHERE ato_id = %s ORDER BY testemunha, ordem, id""",
                     (int(ato_id),))
    for p in pessoas:
        campos = [f"{k}: {p[k]}" for k in ("documento", "identidade", "nacionalidade",
                                            "estado_civil", "regime_bens", "conjuge",
                                            "profissao", "endereco", "filiacao")
                  if p.get(k)]
        partes.append(f"- {p['nome']} — {p['qualificacao'] or 'qualificação não informada'}"
                      f"{' (testemunha)' if p['testemunha'] else ''}; " + "; ".join(campos))
    if not pessoas:
        partes.append("(nenhuma parte cadastrada ainda — tire as partes dos documentos)")
    if a["valor_transacao"]:
        partes.append(f"\nVALOR DA TRANSAÇÃO CADASTRADO: {a['valor_transacao']}")
    if a["modelo_codigo"]:
        mod = bd.um("SELECT nome, corpo FROM nt_modelos WHERE codigo = %s",
                    (a["modelo_codigo"],))
        if mod and mod["corpo"]:
            partes += ["", f"=== MODELO ESCOLHIDO PARA O ATO: «{mod['nome']}» (siga a "
                           "estrutura e as cláusulas; os marcadores entre colchetes ou "
                           "chaves são lugares a preencher) ===",
                       texto_corrido(mod["corpo"])[:20000]]
    exemplos = _exemplos_notas(bd, tipo, ato_id)
    if exemplos:
        partes += ["", "=== EXEMPLOS DE REDAÇÃO DESTA SERVENTIA (só a forma; os dados "
                       "são de OUTROS atos e não se copiam) ==="] + exemplos
    return "\n".join(partes)[-LIMITE_DO_CONTEXTO:]


# ------------------------------------------------------- a instrução

INSTRUCAO_COMUM = """Você é o redator de minutas desta serventia extrajudicial. \
Você prepara o PRIMEIRO TEXTO de um ato, a \
partir dos documentos apresentados; uma pessoa da serventia confere tudo com os \
originais antes de praticar o ato. Você não pratica o ato, não decide se ele é \
cabível e não dispensa exigência.

REGRAS QUE NÃO SE QUEBRAM
1. Todo dado do texto sai dos documentos ou do cadastro que você recebeu. Não invente \
nome, número de documento, data, valor, área, medida, confrontação, matrícula nem \
cláusula. O que faltar ou estiver ilegível vai no texto como [COMPLETAR: o que falta] \
e na lista de pendências.
2. Divergência entre documentos (um nome grafado de dois jeitos, áreas diferentes, \
estado civil que não bate com a certidão) não se resolve escolhendo um lado: use o \
dado do documento mais forte (certidão e documento de identidade valem mais que \
declaração) e ponha a divergência nas pendências, dizendo onde está cada versão.
3. Siga a forma dos exemplos de redação desta serventia e do modelo, quando houver — \
ordem das partes, maneira de qualificar, fecho. Os exemplos são de outros atos: a \
forma se imita, os dados não se copiam.
4. Escreva em português formal de cartório, por extenso onde a casa escreve por \
extenso (datas e valores no corpo do ato), sem enfeites, sem markdown, sem asteriscos. \
Parágrafos separados por uma linha em branco.
5. Não escreva selo, emolumentos, número de folha, livro ou termo: o sistema os põe \
quando o ato for praticado.
6. As fontes dizem de que documento (e página, quando houver) saiu cada dado \
importante — quem confere vai direto ao papel.
7. As instruções da pessoa da serventia valem sobre a sua preferência de redação, \
mas não sobre as regras 1, 2 e 5: se ela pedir para afirmar algo que os documentos \
não sustentam, escreva [COMPLETAR] e explique nas pendências."""

INSTRUCAO_RI = """

O ATO É DO REGISTRO DE IMÓVEIS (Lei 6.015/1973 e Código de Normas do Foro \
Extrajudicial do Maranhão). Você recebe a ficha da matrícula com os atos já \
praticados e o título apresentado. Escreva o TEOR do registro (R) ou da averbação (AV) \
como ele vai à ficha, começando pela identificação do ato na forma dos exemplos da \
casa (por exemplo «R-5/1.234 – Protocolo nº …» ou «AV-3/1.234 – …»), usando o próximo \
número da ficha informado no contexto. Num registro: o título (espécie, data, \
serventia ou juízo que o expediu, livro e folhas quando for escritura), o \
transmitente e o adquirente com a qualificação completa, o objeto (o imóvel desta \
matrícula, ou a parte ideal), o valor e a forma de pagamento, o imposto de \
transmissão com o número da guia, as certidões e as condições do título. Numa \
averbação: o que se averba, à vista de qual documento. Diga em «tipo_ato» se é R ou \
AV, e em «natureza_titulo» a natureza do título em poucas palavras (como «Escritura \
pública de compra e venda»). Em «partes», as pessoas do ato com o papel delas: \
transmitente, adquirente, credor, devedor, interveniente, anuente ou cônjuge."""

INSTRUCAO_NOTAS = """

O ATO É DO TABELIONATO DE NOTAS (Lei 8.935/1994, Código Civil art. 215 e Código de \
Normas do Foro Extrajudicial do Maranhão). Escreva o INSTRUMENTO COMPLETO como ele vai \
ao livro: o preâmbulo (data por extenso, lugar, a serventia), o comparecimento e a \
qualificação completa de cada parte (nome, nacionalidade, estado civil e regime de \
bens, profissão, documento de identidade, CPF, endereço), a declaração de que as \
partes foram reconhecidas pelos documentos apresentados, o objeto e as cláusulas, as \
declarações que a espécie exige e o fecho com a leitura e a assinatura. Na \
procuração: outorgante, outorgado e os poderes, com a finalidade escrita; no \
substabelecimento e na revogação, a procuração anterior identificada (livro, folha, \
data e serventia). Na escritura com imóvel: a descrição do imóvel pela matrícula, o \
valor, o ITBI ou o ITCMD com a guia, as certidões e a declaração sobre a \
indisponibilidade de bens (CNIB). Na ata notarial: o que foi constatado, quando, onde \
e por quem, narrado em primeira pessoa pelo tabelião, sem juízo de valor. Em \
«tipo_ato» repita a espécie recebida; em «natureza_titulo» a natureza do ato em \
poucas palavras."""

ESQUEMA_DA_RESPOSTA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["teor", "tipo_ato", "natureza_titulo", "partes", "pendencias",
                 "fontes", "observacoes"],
    "properties": {
        "teor": {"type": "string"},
        "tipo_ato": {"type": "string"},
        "natureza_titulo": {"type": "string"},
        "partes": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["nome", "documento", "papel", "qualificacao"],
            "properties": {"nome": {"type": "string"}, "documento": {"type": "string"},
                           "papel": {"type": "string"},
                           "qualificacao": {"type": "string"}}}},
        "pendencias": {"type": "array", "items": {"type": "string"}},
        "fontes": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["dado", "documento", "pagina"],
            "properties": {"dado": {"type": "string"}, "documento": {"type": "string"},
                           "pagina": {"type": "string"}}}},
        "observacoes": {"type": "string"},
    },
}


def instrucao_de(atribuicao: str) -> str:
    return INSTRUCAO_COMUM + (INSTRUCAO_RI if atribuicao == RI else INSTRUCAO_NOTAS)


# ------------------------------------------------------- o pedido


def em_andamento(con, atribuicao: str, alvo_id: int) -> dict | None:
    """O pedido que ainda está sendo preparado naquele alvo, ou None. Só LÊ."""
    bd = banco(con)
    if not bd.tem_tabela("mi_pedidos"):
        return None
    r = bd.um("""SELECT id, situacao, pedido_em FROM mi_pedidos
                  WHERE atribuicao = %s AND alvo_id = %s AND situacao IN ('PENDENTE','LENDO')
                  ORDER BY id DESC LIMIT 1""", (atribuicao, int(alvo_id)))
    if r and _situacao_viva(r["situacao"], r["pedido_em"]) in (PENDENTE, LENDO):
        return dict(r)
    return None


def pedir(con, atribuicao: str, alvo_id: int, *, anexos_ids, tipo_ato: str = "",
          instrucao: str = "", revisao: str = "", anterior_id=None,
          prenotacao_id=None, usuario: str = "") -> int:
    """Guarda o pedido e devolve o id. ESCREVE (só `mi_pedidos`).

    A rede é depois, em segundo plano (`executar`). Aqui só se confere o que o
    balcão pode corrigir na hora: alvo, espécie, documentos e a instrução de
    revisão.
    """
    bd = banco(con)
    init_schema(bd)
    a = alvo(bd, atribuicao, alvo_id)
    ja = em_andamento(bd, atribuicao, alvo_id)
    if ja:
        raise MinutaIAError(
            f"O agente ainda está preparando o pedido nº {ja['id']} deste ato. "
            "Espere ele terminar antes de pedir outro.")

    anterior = None
    if anterior_id:
        anterior = bd.um("SELECT * FROM mi_pedidos WHERE id = %s", (int(anterior_id),))
        if (not anterior or anterior["atribuicao"] != atribuicao
                or int(anterior["alvo_id"]) != int(alvo_id)):
            raise MinutaIAError("A minuta a revisar não é deste ato.")
        if anterior["situacao"] != PRONTA:
            raise MinutaIAError("Só se revisa a minuta que o agente terminou.")
        if len(_texto(revisao)) < MINIMO_DA_INSTRUCAO_DE_REVISAO:
            raise MinutaIAError(
                "Escreva o que o agente deve mudar na minuta — a instrução de "
                "revisão é o pedido.")
        # A MINUTA DO RI QUE JÁ VIROU ATO (ou foi descartada) NÃO SE REVISA: ela
        # é a procedência do que está no livro (`ri_minuta.atualizar`).
        if atribuicao == RI and anterior["minuta_id"]:
            situacao = bd.valor("SELECT situacao FROM ri_minutas WHERE id = %s",
                                (int(anterior["minuta_id"]),))
            if situacao and situacao != "A_REVISAR":
                raise MinutaIAError(
                    "Esta minuta já saiu da fila de revisão (foi lavrada ou "
                    "descartada). Para outro ato, peça uma minuta nova.")

    if atribuicao == RI:
        tipo = (_texto(tipo_ato) or (anterior or {}).get("tipo_ato") or "").upper()
        if tipo not in ("R", "AV"):
            raise MinutaIAError("Escolha se o ato é registro (R) ou averbação (AV).")
    else:
        tipo = (a["tipo"] or "").upper()

    disponiveis = {d["anexo_id"]: d for d in documentos_disponiveis(bd, atribuicao, alvo_id)}
    if anexos_ids is None and anterior:
        escolhidos = [d["anexo_id"] for d in json.loads(anterior["documentos_json"])]
    else:
        escolhidos = [int(x) for x in (anexos_ids or [])]
    fora = [x for x in escolhidos if x not in disponiveis]
    if fora:
        raise MinutaIAError(
            "Um dos documentos marcados não é deste ato (nem da prenotação, nem do "
            "protocolo ligado a ele). Atualize a tela e marque de novo.")
    if not escolhidos:
        raise MinutaIAError(
            "Marque ao menos um documento (ou junte um agora): sem documento o "
            "agente não tem de onde tirar os dados.")
    if len(escolhidos) > MAXIMO_DE_DOCUMENTOS:
        raise MinutaIAError(
            f"São {len(escolhidos)} documentos marcados; o agente lê até "
            f"{MAXIMO_DE_DOCUMENTOS} por pedido. Marque os que fundamentam o ato.")
    docs = [disponiveis[x] for x in escolhidos]
    total = sum(int(d["tamanho"] or 0) for d in docs)
    if total > LIMITE_DOS_DOCUMENTOS:
        raise MinutaIAError(
            f"Os documentos marcados somam {total / 1048576:.1f} MB, e o agente lê até "
            f"{LIMITE_DOS_DOCUMENTOS / 1048576:.0f} MB por pedido. Desmarque o que não "
            "fundamenta o ato (comprovante de pagamento, cópia repetida).")

    if prenotacao_id is None:
        prenotacao_id = (anterior or {}).get("prenotacao_id")
        if prenotacao_id is None and atribuicao == RI:
            ligadas = {d.get("prenotacao_id") for d in docs if d.get("prenotacao_id")}
            prenotacao_id = ligadas.pop() if len(ligadas) == 1 else None

    destino = texto_do_destino(bd, {"atribuicao": atribuicao, "alvo_id": alvo_id,
                                    "minuta_id": (anterior or {}).get("minuta_id")})
    novo = bd.escrever(
        """INSERT INTO mi_pedidos (atribuicao, alvo_id, anterior_id, versao, minuta_id,
               tipo_ato, prenotacao_id, instrucao, revisao, documentos_json,
               alvo_hash_antes, situacao, pedido_em, pedido_por, modelo, esforco)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (atribuicao, int(alvo_id), int(anterior["id"]) if anterior else None,
         (int(anterior["versao"]) + 1) if anterior else 1,
         (anterior or {}).get("minuta_id"), tipo,
         int(prenotacao_id) if prenotacao_id else None,
         _texto(instrucao) or ((anterior or {}).get("instrucao") or None),
         _texto(revisao) or None,
         json.dumps([{k: d[k] for k in ("anexo_id", "nome", "sha256", "origem")}
                     for d in docs], ensure_ascii=False),
         hash_do_texto(destino) if destino is not None else None,
         PENDENTE, _agora(), usuario or None, MODELO, ESFORCO))
    return int(novo[0]["id"])


# ------------------------------------------------------- a execução


def _montar_conversa(bd, pedido: dict) -> tuple[list[dict], list[str]]:
    """O turno do usuário (documentos + contexto + pedido) e o que ficou de fora."""
    documentos: list[dict] = []
    imagens: list[dict] = []
    textos: list[str] = []
    fora: list[str] = []
    for d in json.loads(pedido["documentos_json"]):
        linha = bd.um("SELECT original_name, stored_path FROM attachments WHERE id = %s",
                      (int(d["anexo_id"]),))
        caminho = Path((linha or {}).get("stored_path") or "")
        if not linha or not caminho.is_file():
            fora.append(f"{d['nome']}: o arquivo não está mais no disco")
            continue
        try:
            lido = _ler_arquivo(caminho, linha["original_name"] or caminho.name)
        except Exception as erro:                     # noqa: BLE001 — vira linha na tela
            fora.append(f"{d['nome']}: {erro}")
            continue
        documentos += lido.get("documentos", [])
        imagens += lido.get("imagens", [])
        if lido.get("texto"):
            textos.append(lido["texto"])

    if pedido["atribuicao"] == RI:
        contexto = contexto_ri(bd, pedido["alvo_id"], pedido["tipo_ato"],
                               pedido.get("prenotacao_id"))
    else:
        contexto = contexto_notas(bd, pedido["alvo_id"])
    blocos = ["=== CONTEXTO DO SISTEMA ===", contexto]
    if textos:
        blocos += ["", *textos]
    blocos += ["", "=== O PEDIDO ===",
               f"Atribuição: {'Registro de Imóveis' if pedido['atribuicao'] == RI else 'Notas'}."
               f" Espécie: {pedido['tipo_ato']}."]
    nomes = [d["nome"] for d in json.loads(pedido["documentos_json"])]
    blocos.append("Documentos anexados a este pedido: " + "; ".join(nomes) + ".")
    if pedido.get("instrucao"):
        blocos += ["", "INSTRUÇÕES INICIAIS DA SERVENTIA:", pedido["instrucao"]]
    if pedido.get("anterior_id"):
        atual = texto_do_destino(bd, pedido) or ""
        if not atual:
            anterior = bd.um("SELECT teor FROM mi_pedidos WHERE id = %s",
                             (int(pedido["anterior_id"]),))
            atual = (anterior or {}).get("teor") or ""
        blocos += ["", "=== A MINUTA COMO ESTÁ AGORA (com o que a serventia já "
                       "corrigiu à mão — preserve essas correções) ===",
                   texto_corrido(atual),
                   "", "INSTRUÇÕES DE REVISÃO (o que mudar):", pedido.get("revisao") or "",
                   "", "Devolva a minuta INTEIRA revisada, e não só o trecho mudado."]
    else:
        blocos += ["", "Prepare a minuta."]
    return ([{"tipo": "user", "texto": "\n".join(blocos),
              "documentos": documentos, "imagens": imagens}], fora)


def _ler_resposta(texto: str) -> dict:
    """O JSON da resposta, conferido. O formato vem travado do provedor; esta
    leitura existe para a resposta do modelo de reserva, que pode vir sem ele."""
    m = re.search(r"\{.*\}", texto or "", re.S)
    if not m:
        raise ValueError("a resposta não trouxe a minuta no formato combinado")
    d = json.loads(m.group(0))
    teor = _texto(d.get("teor"))
    if len(teor) < 20:
        raise ValueError("a resposta veio sem o texto da minuta")
    return {"teor": teor,
            "tipo_ato": _texto(d.get("tipo_ato")).upper(),
            "natureza_titulo": _texto(d.get("natureza_titulo"))[:200],
            "partes": [p for p in (d.get("partes") or []) if isinstance(p, dict)
                       and _texto(p.get("nome"))][:40],
            "pendencias": [_texto(p) for p in (d.get("pendencias") or []) if _texto(p)][:60],
            "fontes": [f for f in (d.get("fontes") or []) if isinstance(f, dict)][:80],
            "observacoes": _texto(d.get("observacoes"))[:2000]}


def executar(banco_caminho, pasta_dados: Path, pedido_id: int, conversar=None,
             usuario: str = "") -> None:
    """Prepara a minuta. FALA COM A REDE, com conexão própria e fora de transação
    de escrita — e grava o resultado, e pousa a minuta se ninguém mexeu nela."""
    import agente_provedores as AP
    import ia_uso as USO
    conversar = conversar or AP.conversar
    con = banco_pg.conectar(str(banco_caminho), timeout=30)
    inicio = datetime.now()
    try:
        bd = Banco(con)
        init_schema(bd)
        pedido = bd.um("SELECT * FROM mi_pedidos WHERE id = %s", (int(pedido_id),))
        if pedido is None or pedido["situacao"] != PENDENTE:
            return
        pedido = dict(pedido)
        bd.escrever("UPDATE mi_pedidos SET situacao = 'LENDO' WHERE id = %s", (pedido_id,))
        con.commit()
        try:
            passou = USO.passou_do_teto(bd, FINALIDADE)
            if passou:
                raise RuntimeError(passou)
            conversa, fora = _montar_conversa(bd, pedido)
            if not conversa[0]["documentos"] and not conversa[0]["imagens"] and \
                    "=== DOCUMENTO" not in conversa[0]["texto"]:
                raise RuntimeError("nenhum dos documentos marcados pôde ser lido: "
                                   + "; ".join(fora))
            resposta = conversar(
                pasta_dados, provedor=PROVEDOR, sistema=instrucao_de(pedido["atribuicao"]),
                conversa=conversa, ferramentas=[], modelo=MODELO,
                maximo_de_saida=MAXIMO_DE_SAIDA, prazo=PRAZO,
                extras={"output_config": {"effort": ESFORCO,
                                          "format": {"type": "json_schema",
                                                     "schema": ESQUEMA_DA_RESPOSTA}},
                        "fallbacks": "default"},
                betas=[BETA_DO_DESVIO], limite_de_envio=LIMITE_DE_ENVIO,
                # A FINALIDADE VAI ESCRITA, e não pela constante: o varredor do
                # catálogo de IA (tests/test_ia_uso.py) lê o literal da chamada.
                modulo="minuta_ia", finalidade="minuta_ia",
                atribuicao=pedido["atribuicao"], usuario=pedido.get("pedido_por") or "",
                referencia=f"mi_pedidos:{pedido_id}", mascarado=False)
            parou = resposta.get("parou") or ""
            if "[SIMULADOR DO SANDBOX]" in str(resposta.get("texto") or ""):
                # A marca é a de `rc_leitura_documentos.MARCA_DO_SIMULADOR`.
                raise RuntimeError("no sistema de teste a IA é simulada e não lê "
                                   "documento: o agente só prepara minuta de verdade "
                                   "na produção")
            if parou == "refusal":
                raise RuntimeError("o modelo recusou preparar esta minuta (e o desvio "
                                   "também); prepare o texto à mão")
            if parou == "max_tokens":
                raise RuntimeError("a minuta passou do tamanho que o agente escreve de "
                                   "uma vez e veio cortada; divida o pedido ou peça de novo "
                                   "com instruções mais curtas")
            r = _ler_resposta(resposta.get("texto") or "")
            if fora:
                r["pendencias"] = [f"Não foi lido: {x}" for x in fora] + r["pendencias"]
            bd.escrever(
                """UPDATE mi_pedidos SET situacao='PRONTA', terminado_em=%s, teor=%s,
                       resultado_json=%s, natureza=%s, modelo=%s, tokens_entrada=%s,
                       tokens_saida=%s, segundos=%s WHERE id=%s""",
                (_agora(), r["teor"], json.dumps(r, ensure_ascii=False),
                 r["natureza_titulo"] or None, resposta.get("modelo") or MODELO,
                 resposta.get("entrada"), resposta.get("saida"),
                 int((datetime.now() - inicio).total_seconds()), pedido_id))
            con.commit()
            # A MINUTA PRONTA JÁ ESTÁ GRAVADA: o que der errado ao pousá-la (a
            # recusa da minuta do RI é `ValueError` também) vira motivo na tela, e
            # nunca devolve o pedido a ERRO — a versão do agente não se perde.
            try:
                pousar(bd, pedido_id, usuario=pedido.get("pedido_por") or "agente")
            except ValueError as erro:
                con.rollback()
                bd.escrever("UPDATE mi_pedidos SET nao_aplicado_motivo=%s WHERE id=%s",
                            (str(erro)[:500], pedido_id))
            con.commit()
            return
        except Exception as erro:                     # noqa: BLE001 — vai à tabela
            con.rollback()
            bd.escrever("""UPDATE mi_pedidos SET situacao='ERRO', terminado_em=%s, erro=%s,
                               segundos=%s WHERE id=%s""",
                        (_agora(), f"{str(erro)[:400]}",
                         int((datetime.now() - inicio).total_seconds()), pedido_id))
        con.commit()
    finally:
        con.close()


def preparar_em_segundo_plano(banco_caminho, pasta_dados: Path, pedido_id: int) -> None:
    threading.Thread(target=executar, args=(banco_caminho, Path(pasta_dados), pedido_id),
                     daemon=True, name=f"minuta-ia-{pedido_id}").start()


# ------------------------------------------------------- pousar a minuta


def _documento_da_parte(doc: str) -> tuple[str | None, str | None]:
    digitos = re.sub(r"\D", "", doc or "")
    if len(digitos) == 11:
        return "CPF", digitos
    if len(digitos) == 14:
        return "CNPJ", digitos
    return None, (doc or None)


def teor_em_html(teor: str) -> str:
    """O texto da minuta como o teor das Notas é guardado: parágrafos `<p>`.

    O texto vem do modelo e vai ao navegador com `|safe` na tela do ato — por
    isso ESCAPA antes de virar HTML: nenhuma marcação que o modelo escreva
    chega à tela como marcação.
    """
    paragrafos = [p.strip() for p in re.split(r"\n\s*\n", teor or "") if p.strip()]
    return "".join("<p>" + html.escape(p).replace("\n", "<br>") + "</p>"
                   for p in paragrafos)


def pousar(con, pedido_id: int, *, usuario: str, forcar: bool = False) -> str:
    """Põe a minuta pronta no lugar dela. ESCREVE. Devolve o que fez, em frase.

    Recusa (sem `forcar`) quando o texto de destino mudou depois do pedido: a
    pessoa pode ter corrigido à mão enquanto o agente trabalhava.
    """
    import ri_minuta as RIMIN
    bd = banco(con)
    p = bd.um("SELECT * FROM mi_pedidos WHERE id = %s", (int(pedido_id),))
    if not p:
        raise MinutaIAError("Pedido não encontrado.")
    p = dict(p)
    if p["situacao"] != PRONTA:
        raise MinutaIAError("A minuta ainda não está pronta.")
    if p["aplicado_em"]:
        raise MinutaIAError("Esta versão já foi posta na minuta.")
    r = json.loads(p["resultado_json"] or "{}")
    agora = _agora()
    # O QUE ESTAVA LÁ FICA GUARDADO NO PEDIDO: o teor que a pessoa montou do
    # modelo, ou a minuta que ela já tinha corrigido, não some quando a versão
    # do agente pousa — «toda versão fica» vale também para a versão de gente.
    atual = texto_do_destino(bd, p)
    bd.escrever("UPDATE mi_pedidos SET texto_substituido=%s WHERE id=%s",
                (atual or None, int(pedido_id)))
    if not forcar:
        if atual is not None and p["alvo_hash_antes"] and \
                hash_do_texto(atual) != p["alvo_hash_antes"]:
            raise MinutaIAError(
                "O texto da minuta mudou enquanto o agente trabalhava (alguém o "
                "corrigiu à mão). A versão do agente ficou guardada: confira e use "
                "«Usar esta versão» se quiser trocar.")
        if atual is not None and not p["alvo_hash_antes"] and texto_corrido(atual):
            raise MinutaIAError(
                "O ato já tinha texto quando o agente terminou. A versão do agente "
                "ficou guardada: confira e use «Usar esta versão» se quiser trocar.")

    if p["atribuicao"] == RI:
        partes = []
        for x in r.get("partes") or []:
            tipo_doc, numero = _documento_da_parte(x.get("documento"))
            partes.append({"nome": _texto(x.get("nome")).upper(), "documento_tipo": tipo_doc,
                           "documento_numero": numero,
                           "qualificacao": _texto(x.get("qualificacao")),
                           "papel": _texto(x.get("papel")).lower()})
        tipo = r.get("tipo_ato") if r.get("tipo_ato") in ("R", "AV") else p["tipo_ato"]
        prenot = None
        if p.get("prenotacao_id"):
            prenot = bd.valor("SELECT numero FROM ri_protocolos WHERE id = %s",
                              (int(p["prenotacao_id"]),))
        minuta_id = p.get("minuta_id")
        if minuta_id and bd.valor("SELECT situacao FROM ri_minutas WHERE id = %s",
                                  (int(minuta_id),)) == RIMIN.A_REVISAR:
            RIMIN.atualizar(bd, int(minuta_id), teor=p["teor"], agora=agora, tipo=tipo,
                            natureza_titulo=r.get("natureza_titulo") or None,
                            partes=partes, usuario=usuario)
            frase = f"Minuta nº {minuta_id} revisada pelo agente (versão {p['versao']})."
        else:
            minuta_id = RIMIN.criar(
                bd, matricula_id=int(p["alvo_id"]), tipo=tipo, teor=p["teor"], agora=agora,
                natureza_titulo=r.get("natureza_titulo") or None,
                prenotacao=str(prenot) if prenot else None,
                origem=ORIGEM_DA_MINUTA, origem_chave=f"mi_pedidos:{pedido_id}",
                observacao=("Preparada pelo agente de minutas (IA) a partir dos "
                            "documentos — conferir com os originais antes de lavrar."),
                usuario=usuario)
            RIMIN.guardar_partes(bd, minuta_id, partes)
            frase = f"Minuta nº {minuta_id} criada na ficha, a revisar."
        bd.escrever("""UPDATE mi_pedidos SET minuta_id=%s, aplicado_em=%s, aplicado_por=%s,
                           nao_aplicado_motivo=NULL WHERE id=%s""",
                    (int(minuta_id), agora, usuario, int(pedido_id)))
        return frase

    feito = bd.escrever(
        "UPDATE nt_atos SET teor=%s, teor_formato='html' "
        "WHERE id=%s AND situacao='EM_LAVRATURA' RETURNING id",
        (teor_em_html(p["teor"]), int(p["alvo_id"])))
    if not feito:
        raise MinutaIAError("O ato já foi lançado no livro: o teor não muda mais.")
    bd.escrever("""UPDATE mi_pedidos SET aplicado_em=%s, aplicado_por=%s,
                       nao_aplicado_motivo=NULL WHERE id=%s""",
                (agora, usuario, int(pedido_id)))
    return f"Teor do ato preenchido pelo agente (versão {p['versao']})."


# ------------------------------------------------------- a tela


def _situacao_viva(situacao: str, pedido_em: str) -> str:
    if situacao in (PENDENTE, LENDO):
        try:
            idade = (datetime.now() - datetime.fromisoformat(pedido_em)).total_seconds()
        except (TypeError, ValueError):
            idade = 0
        if idade > MINUTOS_PARA_DESISTIR * 60:
            return ERRO
    return situacao


def mostrar(con, pedido_id: int) -> dict | None:
    """Um pedido, como a tela o mostra. Só LÊ."""
    bd = banco(con)
    if not bd.tem_tabela("mi_pedidos"):
        return None
    p = bd.um("SELECT * FROM mi_pedidos WHERE id = %s", (int(pedido_id),))
    if not p:
        return None
    d = dict(p)
    d["situacao"] = _situacao_viva(d["situacao"], d["pedido_em"])
    if d["situacao"] == ERRO and not d.get("erro"):
        d["erro"] = (f"o agente não terminou em {MINUTOS_PARA_DESISTIR} minutos "
                     "(o sistema pode ter sido reiniciado); peça de novo")
    d["documentos"] = json.loads(d["documentos_json"] or "[]")
    d["resultado"] = json.loads(d["resultado_json"]) if d.get("resultado_json") else {}
    return d


def historico(con, atribuicao: str, alvo_id: int, limite: int = 12) -> list[dict]:
    """Os pedidos daquele alvo, do mais novo ao mais velho. Só LÊ."""
    bd = banco(con)
    if not bd.tem_tabela("mi_pedidos"):
        return []
    ids = bd.ler("""SELECT id FROM mi_pedidos WHERE atribuicao = %s AND alvo_id = %s
                     ORDER BY id DESC LIMIT %s""", (atribuicao, int(alvo_id), int(limite)))
    return [mostrar(bd, x["id"]) for x in ids]
