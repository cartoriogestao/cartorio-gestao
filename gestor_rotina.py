"""A rotina do gestor: confere, grava, distribui, cobra e relata.

    «preciso que faça tudo, eu fiscalizo e reviso depois» — o oficial, 06/10/2026

O QUE UMA RODADA FAZ, EM ORDEM
    1. roda `gestor_conferencia.conferir` (só lê);
    2. grava cada achado em `ge_achados` pela chave estável — o que some da
       conferência ganha `resolvido_em`, o que volta perde;
    3. mantém **uma tarefa por regra e setor** (`source_type='GESTOR'`): abre
       quando aparece, atualiza a lista quando muda, fecha sozinha quando a
       conferência não acha mais nada, e **reabre** se alguém a concluiu e o
       achado continua lá — é isso que é cobrar cumprimento;
    4. cobra a tarefa vencida: sobe a prioridade e deixa a cobrança no
       histórico, uma vez por dia;
    5. escreve o relatório do dia — a fila de revisão do oficial.

POR QUE UMA TAREFA POR REGRA, E NÃO POR ACHADO
    Quinze nascimentos fora do SIRC são um serviço só, de uma pessoa, numa
    sentada. Quinze tarefas afogariam o painel do balcão e esconderiam a única
    que importa. O achado individual mora em `ge_achados`; a tarefa carrega a
    lista.

O QUE A RODADA NÃO FAZ
    Não lavra, não sela. O envio entra como passo próprio, por Central: o
    primeiro é o das cargas do RI ao ONR (`gestor_cargas_ri`, 09/10/2026).
"""
from __future__ import annotations

import argparse
import html
import sqlite3
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import agente_notas as AGN
import banco_pg
import gestor_cargas_rcpn as GCRC
import gestor_cargas_ri as GCR
import gestor_conferencia as GC
import gestor_fiscal as GFI
import gestor_protesto as GPT
import gestor_rcpn as GRC
import gestor_rtdpj as GRT
from bd_nativo import banco as _banco
from gestor_schema import init_gestor_schema

QUEM = "gestor"
SOURCE_TYPE = "GESTOR"

#: O nome do setor como as tarefas da casa já o escrevem. Os três de
#: QUALIFICAÇÃO caem na mesma atribuição das tarefas — o que os separa é o
#: responsável, e não a tela onde a tarefa aparece.
SETORES = {
    "RCPN": "RCPN",
    "RI": "Registro de Imóveis",
    "RI_QUALIFICACAO": "Registro de Imóveis",
    "NOTAS": "Notas",
    "NOTAS_QUALIFICACAO": "Notas",
    "RCPJ_RTD": "RCPJ",
    "RCPJ_RTD_QUALIFICACAO": "RCPJ",
    "PROTESTO": "Protesto",
    "GESTAO": "Gestão",
    "TI": "TI",
}

#: Como o setor aparece no relatório.
NOME_DO_SETOR = {
    "RCPN": "Registro Civil",
    "RI": "RI — operacional",
    "RI_QUALIFICACAO": "RI — títulos, atos finais e qualificação",
    "NOTAS": "Notas — operacional",
    "NOTAS_QUALIFICACAO": "Notas — atos finais e qualificação",
    "RCPJ_RTD": "RTD/PJ — operacional",
    "RCPJ_RTD_QUALIFICACAO": "RTD/PJ — títulos, atos finais e qualificação",
    "PROTESTO": "Protesto",
    "GESTAO": "Gestão",
    "TI": "TI",
}

#: A DISTRIBUIÇÃO DA EQUIPE NÃO MORA NO CÓDIGO — sanitização B2, 11/10/2026.
#: O oficial a ditou em 06/10/2026 (quem é titular e quem é substituto de cada
#: setor, e o rodízio do Registro Civil), e ela estava escrita aqui com os
#: logins desta casa. Agora mora em `settings.gestor_distribuicao`, uma lista
#: JSON de `[setor, titular, substituto, rodizio]` (substituto `null` quando
#: não há), que o perfil local da serventia preenche
#: (`tools/migrar_settings_serventia_b0.py`). Ela entra UMA vez por setor, como
#: `origem='OFICIAL'`; depois disso quem muda é a tela, e esta lista não passa
#: por cima. Sem a configuração não se aplica nada, e o gestor infere.
CHAVE_DA_DISTRIBUICAO = "gestor_distribuicao"


def distribuicao_configurada(con) -> tuple:
    """A distribuição gravada em `settings`, como tupla de 4-tuplas.

    Linha torta não derruba a manhã do gestor: é ignorada, e a conferência da
    casa é que a aponta.
    """
    import json
    try:
        linha = _banco(con).um("SELECT value FROM settings WHERE key = %s",
                               (CHAVE_DA_DISTRIBUICAO,))
    except sqlite3.OperationalError:
        return ()
    if not linha or not str(linha["value"] or "").strip():
        return ()
    try:
        bruto = json.loads(linha["value"])
    except ValueError:
        return ()
    saida = []
    for item in bruto if isinstance(bruto, list) else []:
        if not isinstance(item, (list, tuple)) or len(item) != 4:
            continue
        setor, titular, substituto, rodizio = item
        if setor not in NOME_DO_SETOR or not titular:
            continue
        saida.append((str(setor), str(titular), str(substituto) if substituto else None,
                      1 if rodizio else 0))
    return tuple(saida)


#: O nome da regra como o balcão lê no título da tarefa.
ROTULOS = {
    "SIRC": "SIRC — registros não enviados",
    "SIRC_CANCELAMENTO": "SIRC — cancelamentos de termo",
    "FUNAI": "FUNAI — nascimentos indígenas não comunicados",
    "CRC": "CRC — assentos fora da carga",
    "OBITO_MENSAL": "Comunicação mensal de óbitos",
    "IBGE": "IBGE — mapa trimestral",
    "CENSEC": "CENSEC — quinzenas não enviadas",
    "CENSEC_AUTOMATICO": "CENSEC — envio automático com pendência",
    "DOI": "DOI — competências sem recibo",
    "ATO_SEM_SELO": "Atos sem selo",
    "SELO_CANCELADO_LOCAL": "Selos cancelados: confirmar no Portal do Selo",
    "PRENOTACAO_VENCIDA": "Prenotações vencidas ainda abertas",
    "REGISTRO_SEM_CNIB": "Registros com ordem de indisponibilidade no CNIB",
    "CNIB_PARADO": "Cópia local do CNIB parada",
    "BACKUP": "Backup fora do prazo",
    "DIGITALIZACAO_DA_FICHA": "Digitalizar a ficha depois do ato (7 dias)",
    "REVISAO_DO_AGENTE": "Atos já lavrados com apontamento da revisão em lote",
    "DIGITALIZACAO_ATRASADA": "Fichas sem digitalização há mais de 7 dias do ato",
    "PRENOTACAO_A_VENCER": "Prenotações que vencem nos próximos dias",
    "CAIXA_DO_DIA_ABERTO": "Fechar o caixa de hoje — o expediente acabou",
    "DISCO": "Disco do servidor quase cheio",
    "PASTA_DO_BANCO": "Cópia ou rascunho ao lado do banco",
    "DADO_DE_TESTE": "Dado de teste na produção",
    # camada 2
    "NUMERACAO": "Numeração do livro repetida ou com salto",
    "CORRENTE_RI": "Corrente de hash do RI quebrada",
    "ATO_POR_FORA": "Atos do RI sem registro de quem lavrou",
    "REGISTRO_SEM_PRENOTACAO": "Registros sem prenotação amarrada",
    "SELO_ORFAO": "Selos fora do razão ou sem o ato",
    "DOCUMENTO_INVALIDO": "CPF/CNPJ que não fecha o dígito",
    "TEXTO_CONTRA_CADASTRO": "Texto do ato que não bate com o cadastro",
    "LEITURA_DO_TEXTO": "Leitura do texto pela IA",
    "MODELO_NAO_PREENCHIDO": "Texto com campo de modelo não preenchido",
    "MINUTA_EM_FICHA_ENCERRADA": "Minutas em ficha encerrada",
    # camada 3
    "CAIXA_PRONTO_PARA_VISTO": "Caixas que fecham — falta o seu visto",
    "CAIXA_COM_PONTOS": "Caixas fechados com ponto a explicar",
    "CAIXA_DIFERENCA": "Caixas com diferença sem justificativa",
    "CAIXA_ABERTO": "Caixas esquecidos abertos",
    "FECHAMENTO_DO_MES": "Fechamento do mês: selos × caixa",
    "PLD_COAF": "PLD/COAF — casos que esperam análise ou comunicação",
}
# As cargas do RI ao ONR: os rótulos moram com o agente que as faz.
ROTULOS.update(GCR.ROTULOS)
# As cargas do RCPN: os rótulos moram com o agente de cargas do RCPN (09/10/2026).
ROTULOS.update(GCRC.ROTULOS)
# O Tabelionato de Notas: os rótulos e o texto didático moram com o agente das
# Notas (09/10/2026).
ROTULOS.update(AGN.ROTULOS)
AGN.registrar_na_didatica()
# O Protesto: os rótulos moram com o agente do Protesto (09/10/2026).
ROTULOS.update(GPT.ROTULOS)
# O RTD e o RCPJ: os rótulos e o texto didático moram com o agente do RTD/PJ
# (09/10/2026).
ROTULOS.update(GRT.ROTULOS)
GRT.registrar_na_didatica()
# O agente financeiro e das gratuidades (09/10/2026): os rótulos moram com ele.
ROTULOS.update(GFI.ROTULOS)
# O agente do RCPN — o ato e o balcão (09/10/2026): rótulos e texto didático.
ROTULOS.update(GRC.ROTULOS)
GRC.registrar_na_didatica()

#: As regras cujos achados caem em mais de um setor (o setor sai da tabela do
#: ato ou do selo).
REGRAS_QUE_SE_REPARTEM = ("CAIXA_ABERTO", "CAIXA_DO_DIA_ABERTO",
                          "ATO_SEM_SELO", "SELO_CANCELADO_LOCAL", "NUMERACAO",
                          "SELO_ORFAO", "DOCUMENTO_INVALIDO", "TEXTO_CONTRA_CADASTRO",
                          "LEITURA_DO_TEXTO")

#: ORDEM DO OFICIAL, 06/10/2026: «mantenha apenas tarefas para os problemas que possa
#: gerar problemas que culminem em responsabilidade civil». O critério é o do art. 22
#: da Lei 8.935/1994 — DANO A TERCEIRO (usuário, credor, INSS) que o delegatário
#: indeniza. O que é sanção administrativa, multa de órgão, controle interno ou
#: dinheiro da própria casa não vira tarefa. A conferência CONTINUA medindo e gravando
#: estes achados (relatório, despacho, painéis); só a tarefa deixa de existir.
REGRAS_SEM_TAREFA = frozenset({
    "FUNAI",                  # comunicação administrativa, sem dano a terceiro
    "CRC",                    # carga de legado: cobrança da Corregedoria
    "OBITO_MENSAL",           # juiz eleitoral, Receita, Junta: sanção administrativa
    "IBGE",                   # multa do art. 224, não indenização
    "DOI",                    # multa da Receita, não indenização
    "DIGITALIZACAO_DA_FICHA",  # rotina interna (o aviso vermelho da tela continua)
    "DIGITALIZACAO_ATRASADA",
    "CAIXA_DO_DIA_ABERTO",    # dinheiro da casa (o aviso vermelho da tela continua)
    "CAIXA_ABERTO",
    "CAIXA_COM_PONTOS",
    "CAIXA_DIFERENCA",
    "CAIXA_PRONTO_PARA_VISTO",
    "FECHAMENTO_DO_MES",
    "DADO_DE_TESTE",
    "PLD_COAF",               # sigilo do art. 154 do CNN: vai ao despacho do oficial
}) | GCR.REGRAS_DE_DECISAO   # ONR: credencial, envio desligado, carga inicial, acervo —
#                              decisões do oficial, que vão ao despacho e não a tarefa
REGRAS_SEM_TAREFA |= GRC.REGRAS_SEM_TAREFA   # RCPN: dado complementar do assento e
#                                              estoque de folha — rotina, sem dano a terceiro
REGRAS_SEM_TAREFA |= GCRC.REGRAS_DE_DECISAO  # cargas do RCPN: o IBGE que atravessa a
#                                              troca do E-Ofício é decisão do oficial
REGRAS_SEM_TAREFA |= AGN.REGRAS_SEM_TAREFA   # Notas: rascunho sobrando e PDF por
#                                              anexar são controle interno
REGRAS_SEM_TAREFA |= GRT.REGRAS_SEM_TAREFA   # RTD/PJ: livro, termo do dia, dinheiro,
#                                              acervo repetido e o que o agente corrigiu
REGRAS_SEM_TAREFA |= GPT.REGRAS_SEM_TAREFA   # Protesto: ato já praticado fora do prazo,
#                         o modelo do termo (decisão do oficial) e o acervo antes do corte
REGRAS_SEM_TAREFA |= GFI.REGRAS_SEM_TAREFA   # Fiscal: divergência de valor, gratuidade em
#        análise, selos fora do sistema — dinheiro da casa. Ficam com tarefa o selo que o TJ
#        não conhece ou cancelou (papel inválido na mão do usuário) e a gratuidade
#        indeferida, que tem prazo de recurso e é decisão do oficial (setor Gestão)
REGRAS_QUE_SE_REPARTEM += ("FISCAL_SELO_FORA_DO_PORTAL", "FISCAL_CANCELADO_NO_PORTAL")
#: FICAM (podem virar indenização): SIRC e cancelamento no SIRC (ação regressiva do
#: INSS), CENSEC (testamento e procuração revogada que ninguém acha), ato sem selo,
#: prenotação (prioridade perdida), CNIB e cópia do CNIB parada (registro sobre bem
#: indisponível), backup e disco (perda do acervo), numeração e corrente do RI, CPF
#: errado em assento, erro grave no texto do ato selado e o texto/minuta que vai ao
#: livro (marcador, texto contra o cadastro, minuta em ficha encerrada).

#: AS CENTRAIS E AS CARGAS NÃO SÃO TAREFA DE ESCREVENTE — ordem do oficial em
#: 13/10/2026: «as centrais e cargas automático, não crie mais tarefas para os
#: escreventes, eu vou centralizar elas com envio automático por agentes. retire
#: essas tarefas automáticas» e «quero aviso pra mim apenas, consolidado, não um
#: por tarefa». A conferência CONTINUA medindo e gravando os achados; o aviso é a
#: seção «Centrais» do despacho do dia (Relatos do dia, só para o oficial), e a
#: tarefa que estiver aberta fecha sozinha na rodada seguinte, com a nota do porquê.
REGRAS_DAS_CENTRAIS = frozenset({
    "SIRC", "SIRC_CANCELAMENTO", "CENSEC", "CENSEC_AUTOMATICO", "CRC", "FUNAI",
    "IBGE", "DOI", "OBITO_MENSAL",
}) | frozenset(GCR.ROTULOS) | frozenset(GCRC.ROTULOS)
REGRAS_SEM_TAREFA |= REGRAS_DAS_CENTRAIS

PRIORIDADE = {"CRITICO": "CRITICA", "VENCIDO": "CRITICA", "NAO_MEDIU": "CRITICA",
              "PRAZO": "ALTA", "ATENCAO": "MEDIA"}
ORDEM_PRIORIDADE = ("CRITICA", "ALTA", "MEDIA", "BAIXA")

#: De onde se infere quem responde por cada setor: quem mais lançou ali.
QUEM_LANCA = {
    "RCPN": "SELECT criado_por FROM rc_atos WHERE criado_em >= %s ORDER BY id",
    "RI": "SELECT lavrado_por FROM ri_atos WHERE lavrado_em >= %s AND COALESCE(acervo,0)=0 ORDER BY id",
    "NOTAS": "SELECT criado_por FROM nt_atos WHERE criado_em >= %s ORDER BY id",
    "RCPJ_RTD": "SELECT criado_por FROM rg_atos WHERE criado_em >= %s ORDER BY id",
    "PROTESTO": "SELECT criado_por FROM pt_atos WHERE criado_em >= %s ORDER BY id",
}


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _pg(sql: str) -> str:
    """O pedaço de WHERE que `tarefa_suspensao` (ainda na ponte) devolve com `?`."""
    return sql.replace("?", "%s")


# ------------------------------------------------------------ responsáveis

def _admin(con) -> int | None:
    r = _banco(con).um(
        """SELECT id FROM users WHERE role = 'ADMIN' AND active = 1
              AND COALESCE(eh_robo,0) = 0 ORDER BY id LIMIT 1""")
    return r["id"] if r else None


def _pessoas(con) -> dict[str, int]:
    """Login e nome completo, em maiúsculas, apontando para o id ativo."""
    pessoas = {}
    for r in _banco(con).ler(
            """SELECT id, username, full_name FROM users
                WHERE active = 1 AND COALESCE(eh_robo,0) = 0 ORDER BY id"""):
        for nome in (r["username"], r["full_name"]):
            if nome:
                pessoas[nome.strip().upper()] = r["id"]
    return pessoas


def aplicar_distribuicao(con,
                         distribuicao=None,
                         *, por: str = "oficial") -> list[str]:
    """Grava a distribuição do oficial. Devolve o que não deu para gravar.

    **SÓ ENTRA ONDE O OFICIAL AINDA NÃO DEFINIU.** O que estiver com
    `origem='OFICIAL'` é decisão dele, talvez mais nova que esta lista — e a
    lista roda toda manhã. O que estiver `INFERIDO` é palpite do gestor, e a
    decisão dele passa por cima.

    **LOGIN QUE NÃO EXISTE NÃO VIRA PALPITE.** O setor fica como estava e o
    motivo volta, para aparecer no relatório: trocar a pessoa escolhida pelo
    admin em silêncio daria a tarefa a quem o oficial não escolheu.

    Sem `distribuicao`, vale a de `settings.gestor_distribuicao`.
    """
    if distribuicao is None:
        distribuicao = distribuicao_configurada(con)
    pessoas = _pessoas(con)
    bd = _banco(con)
    oficiais = {r["setor"] for r in bd.ler(
        "SELECT setor FROM ge_responsaveis WHERE origem = 'OFICIAL' ORDER BY setor")}
    faltou = []
    for setor, titular, substituto, rodizio in distribuicao:
        if setor in oficiais:
            continue
        tid = pessoas.get(titular.upper())
        sid = pessoas.get(substituto.upper()) if substituto else None
        if tid is None or (substituto and sid is None):
            ausente = titular if tid is None else substituto
            faltou.append(f"{NOME_DO_SETOR.get(setor, setor)}: o usuário "
                          f"«{ausente}» não existe ou está inativo")
            continue
        bd.escrever(
            """INSERT INTO ge_responsaveis (setor, user_id, substituto_id,
                   rodizio, origem, definido_em, definido_por)
               VALUES (%s, %s, %s, %s, 'OFICIAL', %s, %s)
               ON CONFLICT(setor) DO UPDATE SET user_id=excluded.user_id,
                   substituto_id=excluded.substituto_id,
                   rodizio=excluded.rodizio, origem='OFICIAL',
                   definido_em=excluded.definido_em,
                   definido_por=excluded.definido_por""",
            (setor, tid, sid, int(rodizio), _agora(), por))
    return faltou


def inferir_responsaveis(con) -> dict[str, dict]:
    """Quem responde por cada setor: {setor: {titular, substituto, rodizio}}.

    Só preenche o setor que ninguém definiu, e o que o oficial definiu
    (`origem='OFICIAL'`) nunca é sobrescrito. O setor de qualificação sem
    dono herda o titular do operacional da mesma atribuição — melhor que o
    admin, que não é quem lavra.
    """
    pessoas = _pessoas(con)
    bd = _banco(con)
    definidos = {r["setor"]: r for r in bd.ler("SELECT * FROM ge_responsaveis ORDER BY setor")}
    admin = _admin(con)
    for setor in SETORES:
        if setor in definidos:
            continue
        escolhido = None
        base = setor.replace("_QUALIFICACAO", "")
        sql = QUEM_LANCA.get(base)
        if sql:
            contagem: dict[int, int] = {}
            try:
                for linha in bd.ler(sql, (GC.IMPLANTACAO,)):
                    nome = next(iter(linha.values()))
                    uid = pessoas.get(str(nome or "").strip().upper())
                    if uid:
                        contagem[uid] = contagem.get(uid, 0) + 1
            except sqlite3.OperationalError:
                contagem = {}
            if contagem:
                escolhido = max(contagem, key=contagem.get)
        escolhido = escolhido or admin
        if escolhido:
            bd.escrever(
                """INSERT INTO ge_responsaveis
                       (setor, user_id, origem, definido_em, definido_por)
                   VALUES (%s, %s, 'INFERIDO', %s, %s)""",
                (setor, escolhido, _agora(), QUEM))
    return {r["setor"]: {"titular": r["user_id"], "substituto": r["substituto_id"],
                         "rodizio": bool(r["rodizio"]), "origem": r["origem"]}
            for r in bd.ler("SELECT * FROM ge_responsaveis ORDER BY setor")}


def _carga_aberta(con, user_id: int) -> int:
    return int(_banco(con).valor(
        """SELECT count(*) FROM tasks WHERE assigned_user_id = %s
              AND status NOT IN ('CONCLUIDA','CANCELADA')""", (user_id,)))


def _pessoa(setor: str) -> int | None:
    """«PESSOA:7» é a tarefa que é de alguém, e não de um setor (o caixa)."""
    if (setor or "").startswith("PESSOA:") and setor[7:].isdigit():
        return int(setor[7:])
    return None


def _nome_do_setor(con, setor: str) -> str:
    pessoa = _pessoa(setor)
    if pessoa is not None:
        r = _banco(con).um("SELECT full_name FROM users WHERE id = %s", (pessoa,))
        return r["full_name"] if r else setor
    return NOME_DO_SETOR.get(setor, setor)


def escolher_responsavel(con, responsaveis: dict[str, dict],
                         setor: str) -> tuple[int | None, int | None]:
    """(responsável, substituto) para uma tarefa NOVA daquele setor.

    No RODÍZIO a tarefa vai para quem dos dois tem menos tarefa aberta agora, e
    o outro fica de substituto — «quando uma for responsável, a outra fica como
    substituta». Empate vai para o titular, e é isso que faz a próxima ir para
    a outra: a primeira tarefa desempata a balança.
    """
    pessoa = _pessoa(setor)
    if pessoa is not None:
        return pessoa, _admin(con)
    r = responsaveis.get(setor)
    if not r:
        return _admin(con), None
    titular, substituto = r["titular"], r["substituto"]
    if r["rodizio"] and substituto:
        if _carga_aberta(con, substituto) < _carga_aberta(con, titular):
            return substituto, titular
    return titular, substituto


# ---------------------------------------------------------------- achados

def gravar_achados(con, achados: list[dict],
                   hoje: date) -> dict:
    bd = _banco(con)
    agora = _agora()
    vistos = set()
    novos = 0
    for a in achados:
        vistos.add(a["chave"])
        linha = bd.um("SELECT id, resolvido_em FROM ge_achados WHERE chave = %s",
                      (a["chave"],))
        if linha is None:
            novos += 1
            bd.escrever(
                """INSERT INTO ge_achados (chave, regra, gravidade, setor, titulo,
                       detalhe, prazo, fundamento, primeiro_visto_em, ultimo_visto_em)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (a["chave"], a["regra"], a["gravidade"], a["setor"], a["titulo"],
                 a["detalhe"], a["prazo"], a["fundamento"], agora, agora))
        else:
            # A REGRA TAMBÉM SE ATUALIZA: em 06/10/2026 «caixa não conferido»
            # virou «pronto para o visto» / «com ponto» com a MESMA chave, e a
            # linha ficou com o nome velho — o despacho, que conta por regra,
            # dizia «0 caixas para o visto» com 42 esperando.
            bd.escrever(
                """UPDATE ge_achados SET regra=%s, gravidade=%s, setor=%s, titulo=%s,
                       detalhe=%s, prazo=%s, fundamento=%s, ultimo_visto_em=%s,
                       resolvido_em=NULL WHERE id=%s""",
                (a["regra"], a["gravidade"], a["setor"], a["titulo"], a["detalhe"],
                 a["prazo"], a["fundamento"], agora, linha["id"]))
    resolvidos = 0
    for r in bd.ler("SELECT id, chave FROM ge_achados WHERE resolvido_em IS NULL "
                    "ORDER BY id"):
        if r["chave"] not in vistos:
            resolvidos += 1
            bd.escrever("UPDATE ge_achados SET resolvido_em=%s WHERE id=%s",
                        (agora, r["id"]))
    return {"novos": novos, "resolvidos": resolvidos}


# ---------------------------------------------------------------- tarefas

def _historico(con, task_id: int, acao: str, *, antes=None, depois=None,
               nota: str = "") -> None:
    _banco(con).escrever(
        """INSERT INTO task_history (task_id, ts, user_id, action, old_value,
               new_value, note) VALUES (%s, %s, NULL, %s, %s, %s, %s)""",
        (task_id, _agora(), acao, antes, depois, nota))


def _descricao(itens: list[dict]) -> str:
    linhas = ["Lista mantida pelo gestor; atualiza a cada conferência e a tarefa "
              "fecha sozinha quando a lista zerar.", ""]
    for a in sorted(itens, key=lambda x: (GC.GRAVIDADES.index(x["gravidade"]),
                                          x["prazo"] or "9999")):
        prazo = f" — prazo {a['prazo']}" if a["prazo"] else ""
        linhas.append(f"[{a['gravidade']}] {a['titulo']}{prazo}")
        if a["detalhe"]:
            linhas.append(f"    {a['detalhe']}")
    return "\n".join(linhas)


def sincronizar_tarefas(con, achados: list[dict],
                        responsaveis: dict[str, dict], hoje: date) -> dict:
    grupos: dict[tuple[str, str], list[dict]] = {}
    for a in achados:
        if a["regra"] in REGRAS_SEM_TAREFA:
            continue
        grupos.setdefault((a["regra"], a["setor"]), []).append(a)

    bd = _banco(con)
    abertas = {r["source_ref"]: r for r in bd.ler(
        """SELECT * FROM tasks WHERE source_type = %s ORDER BY id""", (SOURCE_TYPE,))}
    criadas = fechadas = reabertas = 0
    agora = _agora()
    tocadas = set()

    for (regra, setor), itens in grupos.items():
        ref = f"GESTOR:{regra}:{setor}"
        tocadas.add(ref)
        prioridade = min((PRIORIDADE[a["gravidade"]] for a in itens),
                         key=ORDEM_PRIORIDADE.index)
        prazos = sorted(a["prazo"] for a in itens if a["prazo"])
        vencimento = prazos[0] if prazos else None
        # A REGRA QUE SE REPARTE ENTRE SETORES LEVA O SETOR NO TÍTULO: sem
        # isso, a mesma pessoa via duas tarefas «Atos sem selo (1)» e não
        # sabia qual era de qual livro (medido na cópia de 06/10/2026).
        onde = (f" — {_nome_do_setor(con, setor)}"
                if regra in REGRAS_QUE_SE_REPARTEM else "")
        # 13/10/2026, o oficial: «simplificar e deixar objetivo e entendível».
        # Sem o prefixo «[Gestor]»: a origem já aparece na lista de Processos.
        titulo = f"{ROTULOS.get(regra, regra)}{onde} ({len(itens)})"
        # O TEXTO DIDÁTICO (06/10/2026, pedido do oficial): por que existe, como
        # resolver e onde abrir cada ato — `gestor_didatica`. Sem ele (versão
        # instalada antiga), cai na lista seca de antes.
        try:
            import gestor_didatica
            descricao = gestor_didatica.descricao(con, regra, itens, list(GC.GRAVIDADES))
        except ImportError:
            descricao = _descricao(itens)
        fundamento = "; ".join(sorted({a["fundamento"] for a in itens if a["fundamento"]}))
        tarefa = abertas.get(ref)
        if tarefa is None:
            dono, substituto = escolher_responsavel(con, responsaveis, setor)
            novo_id = bd.escrever(
                """INSERT INTO tasks (source_type, source_ref, title, description,
                       sector, system_name, priority, status, start_date, due_date,
                       assigned_user_id, backup_user_id, evidence_required,
                       legal_ref, created_at, updated_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,'ABERTA',%s,%s,%s,%s,0,%s,%s,%s)
                   RETURNING id""",
                (SOURCE_TYPE, ref, titulo, descricao,
                 "Caixa" if _pessoa(setor) is not None else SETORES.get(setor, setor),
                 f"Conferência diária — {_nome_do_setor(con, setor)}",
                 prioridade, hoje.isoformat(), vencimento, dono, substituto,
                 fundamento, agora, agora))[0]["id"]
            _historico(con, novo_id, "CRIADA",
                       nota=f"Aberta pela conferência: {len(itens)} pendência(s).")
            criadas += 1
            continue
        # A DISTRIBUIÇÃO MUDOU E A TAREFA FICOU COM QUEM NÃO RESPONDE MAIS PELO
        # SETOR: passa adiante. No rodízio, estar com qualquer uma das duas é
        # estar certo — trocar de mão a cada manhã seria cobrar de quem não
        # começou o serviço.
        r = responsaveis.get(setor) or {}
        do_setor = {r.get("titular"), r.get("substituto")} - {None}
        if do_setor and tarefa["assigned_user_id"] not in do_setor:
            dono, substituto = escolher_responsavel(con, responsaveis, setor)
            bd.escrever(
                """UPDATE tasks SET assigned_user_id=%s, backup_user_id=%s, updated_at=%s
                    WHERE id=%s""", (dono, substituto, agora, tarefa["id"]))
            _historico(con, tarefa["id"], "PASSAGEM",
                       antes=str(tarefa["assigned_user_id"]), depois=str(dono),
                       nota="Passada pela distribuição do oficial de 06/10/2026.")
        if tarefa["status"] in ("CONCLUIDA", "CANCELADA"):
            bd.escrever(
                """UPDATE tasks SET status='ABERTA', completed_at=NULL,
                       completed_by=NULL, updated_at=%s WHERE id=%s""",
                (agora, tarefa["id"]))
            _historico(con, tarefa["id"], "REABERTA", antes=tarefa["status"],
                       depois="ABERTA",
                       nota=f"A conferência ainda encontra {len(itens)} pendência(s).")
            reabertas += 1
        if (tarefa["description"] != descricao or tarefa["title"] != titulo
                or tarefa["priority"] != prioridade
                or tarefa["due_date"] != vencimento):
            bd.escrever(
                """UPDATE tasks SET title=%s, description=%s, priority=%s, due_date=%s,
                       legal_ref=%s, updated_at=%s WHERE id=%s""",
                (titulo, descricao, prioridade, vencimento, fundamento, agora,
                 tarefa["id"]))
            if tarefa["priority"] != prioridade:
                _historico(con, tarefa["id"], "ALTEROU_PRIORITY",
                           antes=tarefa["priority"], depois=prioridade)
            _historico(con, tarefa["id"], "NOTA",
                       nota=f"Lista atualizada pela conferência: {len(itens)} "
                            "pendência(s).")

    for ref, tarefa in abertas.items():
        if ref in tocadas or tarefa["status"] in ("CONCLUIDA", "CANCELADA"):
            continue
        bd.escrever(
            """UPDATE tasks SET status='CONCLUIDA', completed_at=%s, updated_at=%s
                WHERE id=%s""", (agora, agora, tarefa["id"]))
        # Fechar porque a regra deixou de gerar tarefa NÃO é «não há mais pendência»:
        # a pendência pode continuar, e a nota tem de dizer a razão verdadeira.
        partes = (ref or "").split(":")
        sem_tarefa = len(partes) > 1 and partes[1] in REGRAS_SEM_TAREFA
        _historico(con, tarefa["id"], "ALTEROU_STATUS", antes=tarefa["status"],
                   depois="CONCLUIDA",
                   nota=("Fechada por ordem do oficial (13/10/2026): as Centrais e as cargas "
                         "passam ao envio automático pelos agentes, e o oficial recebe o aviso "
                         "consolidado no despacho do dia — não é tarefa de escrevente."
                         if len(partes) > 1 and partes[1] in REGRAS_DAS_CENTRAIS else
                         "Fechada por ordem do oficial (06/10/2026): só vira tarefa o que "
                         "pode gerar responsabilidade civil. A conferência continua medindo "
                         "isto no relatório." if sem_tarefa else
                         "Fechada pela conferência: não há mais pendência."))
        fechadas += 1
    return {"criadas": criadas, "fechadas": fechadas, "reabertas": reabertas}


#: As origens de tarefa que o agente cobra (06/10/2026: «um agente que faça
#: todo trabalho do oficial» — cobrar a equipe é trabalho dele). As do ADMIN
#: ficam de fora, menos as do próprio gestor: as do oficial vão no despacho, e não em nota.
ORIGENS_COBRADAS = ("GESTOR", "EXPEDIENTE", "MANUAL", "INSPECAO")


def cobrar_vencidas(con, hoje: date) -> int:
    """A cobrança do dia das tarefas vencidas da equipe — UM RELATO POR PESSOA.

    Até 12/10/2026 era uma NOTA em cada tarefa vencida, todo dia (208 notas do
    robô na história das tarefas, medido). Ordem do oficial nessa data: «os
    relatos diários ficarem num campo próprio». Agora a cobrança é o relato
    «Cobrança do dia» de cada responsável, em `relatos_diarios`, renovado a cada
    rodada; a tarefa fica limpa para o andamento de quem a cumpre.

    A PRIORIDADE SÓ SOBE NA TAREFA DO PRÓPRIO GESTOR: a que o oficial criou à
    mão tem a prioridade que ele deu, e o agente não a muda.
    """
    import relatos_diarios as RD
    import tarefa_suspensao as TS
    # A SUSPENSA NÃO SE COBRA — relato #132, 15/10/2026: a suspensão existe
    # para isto, e a prioridade dela também não sobe enquanto espera.
    nao_suspensa, params_suspensao = TS.condicao_nao_suspensa("t", hoje, con=con)
    bd = _banco(con)
    cobradas = 0
    por_pessoa: dict[int, list[str]] = {}
    for t in bd.ler(
            f"""SELECT t.id, t.priority, t.due_date, t.backup_user_id, t.source_type,
                      t.title, t.assigned_user_id
                  FROM tasks t JOIN users u ON u.id = t.assigned_user_id
                 WHERE t.source_type IN ({','.join(['%s'] * len(ORIGENS_COBRADAS))})
                   AND t.status NOT IN ('CONCLUIDA','CANCELADA')
                   AND (u.role <> 'ADMIN' OR t.source_type = 'GESTOR')
                   AND t.due_date IS NOT NULL AND t.due_date < %s
                   AND {_pg(nao_suspensa)}
                 ORDER BY t.id""",
            (*ORIGENS_COBRADAS, hoje.isoformat(), *params_suspensao)):
        dias = (hoje - GC._dia(t["due_date"])).days
        if t["priority"] != "CRITICA" and t["source_type"] == SOURCE_TYPE:
            bd.escrever("UPDATE tasks SET priority='CRITICA', updated_at=%s WHERE id=%s",
                        (_agora(), t["id"]))
            _historico(con, t["id"], "ALTEROU_PRIORITY", antes=t["priority"],
                       depois="CRITICA")
        quem_cobre = ""
        if t["backup_user_id"]:
            nome = bd.um("SELECT full_name FROM users WHERE id = %s",
                         (t["backup_user_id"],))
            if nome:
                quem_cobre = f" Na falta do responsável, cobre: {nome['full_name']}."
        por_pessoa.setdefault(t["assigned_user_id"], []).append(
            f"   #{t['id']} [{t['priority']}] {t['title']} — vencida há {dias} dia(s).{quem_cobre}")
        cobradas += 1
    for uid, linhas in por_pessoa.items():
        RD.publicar(con, dia=hoje, origem="GESTOR_COBRANCA", destinatario_id=uid,
                    titulo=f"Cobrança do dia — {len(linhas)} tarefa(s) vencida(s)",
                    corpo="\n".join([f"Tarefas vencidas com você em {hoje:%d/%m/%Y}. Resolva hoje "
                                      "ou registre o impedimento no andamento de cada uma.", ""]
                                     + linhas),
                    itens=len(linhas))
    # Quem resolveu as vencidas entre uma rodada e outra não pode continuar lendo
    # a cobrança da manhã: o relato do dia passa a dizer que está em dia.
    RD.init_schema(con)
    for r in bd.ler(
            "SELECT destinatario_id FROM rd_relatos WHERE dia=%s AND origem='GESTOR_COBRANCA' "
            "ORDER BY id", (hoje.isoformat(),)):
        uid = r["destinatario_id"]
        if uid not in por_pessoa:
            RD.publicar(con, dia=hoje, origem="GESTOR_COBRANCA", destinatario_id=uid,
                        titulo="Cobrança do dia — nenhuma tarefa vencida agora",
                        corpo="As tarefas vencidas da rodada anterior foram resolvidas ou "
                              "remarcadas. Nada a cobrar nesta rodada.", itens=0)
    return cobradas


# --------------------------------------------------------------- relatório

def relatorio_html(con, hoje: date, resumo: dict) -> str:
    bd = _banco(con)
    nomes = {r["id"]: r["full_name"] for r in bd.ler("SELECT id, full_name FROM users ORDER BY id")}
    resp = {r["setor"]: (nomes.get(r["user_id"], "?"), r["origem"],
                         nomes.get(r["substituto_id"]) if r["substituto_id"] else None,
                         bool(r["rodizio"]))
            for r in bd.ler(
                """SELECT setor, user_id, origem, substituto_id, rodizio
                     FROM ge_responsaveis ORDER BY setor""")}
    abertos = bd.ler(
        """SELECT * FROM ge_achados WHERE resolvido_em IS NULL ORDER BY id""")
    abertos = sorted(abertos, key=lambda a: (GC.GRAVIDADES.index(a["gravidade"]),
                                             a["prazo"] or "9999", a["regra"]))
    resolvidos = bd.ler(
        """SELECT * FROM ge_achados WHERE resolvido_em LIKE %s ORDER BY id""",
        (hoje.isoformat() + "%",))
    e = html.escape
    linhas = "".join(
        f"<tr class='g-{a['gravidade'].lower()}'><td>{e(a['gravidade'])}</td>"
        f"<td>{e(a['regra'])}</td><td>{e(NOME_DO_SETOR.get(a['setor'], a['setor']))}"
        f"<br><small>{e(resp.get(a['setor'], ('—',))[0])}</small></td>"
        f"<td><b>{e(a['titulo'])}</b><br><small>{e(a['detalhe'] or '')}</small></td>"
        f"<td>{e(a['prazo'] or '')}</td><td>{e(str(a['primeiro_visto_em'])[:10])}</td></tr>"
        for a in abertos)
    feitos = "".join(f"<li>{e(a['titulo'])}</li>" for a in resolvidos) or "<li>nenhum</li>"
    def _linha_pessoa(s, n, o, sub, rod):
        if rod and sub:
            quem = f"{e(n)} e {e(sub)}, em rodízio — uma responde, a outra substitui"
        else:
            quem = e(n) + (f" · substituto(a): {e(sub)}" if sub else "")
        marca = " <i>(inferido — troque se não for)</i>" if o == "INFERIDO" else ""
        return f"<li>{e(NOME_DO_SETOR.get(s, s))}: {quem}{marca}</li>"
    pessoas = "".join(_linha_pessoa(s, *v) for s, v in
                      sorted(resp.items(), key=lambda kv: list(NOME_DO_SETOR).index(kv[0])
                             if kv[0] in NOME_DO_SETOR else 99))
    faltou = "".join(f"<li>{e(f)}</li>" for f in resumo.get("distribuicao_faltou") or [])
    if faltou:
        pessoas += f"</ul><p><b>Não deu para aplicar:</b></p><ul>{faltou}"
    contagem = {}
    for a in abertos:
        contagem[a["gravidade"]] = contagem.get(a["gravidade"], 0) + 1
    placar = " · ".join(f"{g}: {contagem.get(g, 0)}" for g in GC.GRAVIDADES)
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Conferência {hoje:%d/%m/%Y}</title><style>
body{{font:14px system-ui,sans-serif;margin:16px;color:#222;background:#fff}}
table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid #ddd;padding:6px;vertical-align:top;text-align:left}}
small{{color:#555}}.g-critico td:first-child,.g-vencido td:first-child,.g-nao_mediu td:first-child{{color:#b00020;font-weight:700}}
.g-prazo td:first-child{{color:#a15c00;font-weight:700}}
</style></head><body>
<h1>Conferência da casa — {hoje:%d/%m/%Y}</h1>
<p><b>{len(abertos)}</b> achado(s) em aberto ({placar}). Novos hoje: {resumo.get('novos', 0)}.
Resolvidos hoje: {resumo.get('resolvidos', 0)}. Tarefas abertas: {resumo.get('criadas', 0)},
fechadas: {resumo.get('fechadas', 0)}, reabertas: {resumo.get('reabertas', 0)},
cobradas: {resumo.get('cobradas', 0)}.</p>
<p><small>O gestor só lê os atos; o que ele escreve são tarefas, cobranças e este
relatório. «Sem registro de envio» quer dizer que o envio não foi registrado no
sistema — registre o protocolo em ge_envios e o achado some.</small></p>
<table><tr><th>Gravidade</th><th>Regra</th><th>Setor</th><th>Achado</th><th>Prazo</th><th>Desde</th></tr>
{linhas}</table>
<h2>Resolvidos hoje</h2><ul>{feitos}</ul>
<h2>Responsáveis</h2><ul>{pessoas}</ul>
</body></html>"""


# ------------------------------------------------------------------ rodada

# ------------------------------------------------------- o despacho do oficial
#
# «um agente completo que faça todo trabalho do oficial» (06/10/2026). O que o
# agente não pode fazer por ele — dar visto, decidir qualificação, responder à
# COGEX — chega numa tarefa SÓ, toda manhã, com o que o agente já fez ao lado.
# Uma tarefa por dia, e a de ontem fecha: despacho velho aberto é pilha.

DESPACHO = "DESPACHO"


def despacho_do_oficial(con, hoje: date, resumo: dict,
                        dono: int | None) -> str:
    import gestor_expedientes as GX
    bd = _banco(con)
    linhas = [f"Despacho do agente gestor — {hoje:%d/%m/%Y}", ""]
    import tarefa_suspensao as TS
    # A SUSPENSA FICA FORA DO DESPACHO (relato #132): ela não pede decisão
    # enquanto espera, e não é vencida de ninguém.
    nao_suspensa, params_suspensao = TS.condicao_nao_suspensa(None, hoje, con=con)
    nao_suspensa_t, params_suspensao_t = TS.condicao_nao_suspensa("t", hoje, con=con)
    if dono is not None:
        minhas = bd.ler(
            f"""SELECT id, title, priority, due_date FROM tasks
                WHERE assigned_user_id = %s AND status NOT IN ('CONCLUIDA','CANCELADA')
                  AND source_type <> %s AND {_pg(nao_suspensa)}
                ORDER BY CASE priority WHEN 'CRITICA' THEN 0 WHEN 'ALTA' THEN 1
                         WHEN 'MEDIA' THEN 2 ELSE 3 END, due_date NULLS FIRST, id""",
            (dono, DESPACHO, *params_suspensao))
        linhas.append(f"1. O QUE SÓ VOCÊ DECIDE ({len(minhas)} tarefa(s) com você)")
        for m in minhas[:25]:
            prazo = f" — prazo {m['due_date'][8:10]}/{m['due_date'][5:7]}" if m["due_date"] else ""
            vencida = " — VENCIDA" if m["due_date"] and m["due_date"] < hoje.isoformat() else ""
            linhas.append(f"   #{m['id']} [{m['priority']}] {m['title']}{prazo}{vencida}")
        linhas.append("")
    def conta(regra):
        return int(bd.valor("SELECT count(*) FROM ge_achados WHERE regra = %s "
                            "AND resolvido_em IS NULL", (regra,)))
    # O PLD/COAF VEM AQUI, E NÃO EM TAREFA (23/10/2026): o caso é sigiloso
    # (CNN, art. 154) e a tarefa se vê na lista da equipe. O despacho é do
    # oficial; ele diz quantos esperam e manda à tela, que é só do ADMIN.
    pld = conta("PLD_COAF")
    if pld:
        if dono is None:
            linhas.append("1. O QUE SÓ VOCÊ DECIDE")
        linhas += [f"   PLD/COAF: {pld} caso(s) com prazo vencido ou perto de vencer — "
                   "Administrativo → PLD/COAF (sigiloso).", ""]
    linhas += ["2. CAIXAS",
               f"   {conta('CAIXA_PRONTO_PARA_VISTO')} fecham e esperam o seu visto; "
               f"{conta('CAIXA_COM_PONTOS')} têm ponto a explicar; "
               f"{conta('CAIXA_ABERTO')} esquecido(s) aberto(s).", ""]
    ciencia = GX.para_ciencia(con)
    linhas.append(f"3. MALOTE PARA CIÊNCIA ({len(ciencia)}) — o agente leu; nada pedem à casa")
    for c in ciencia[:20]:
        linhas.append(f"   {c['protocolo'] or '#' + str(c['id'])}: {c['resumo'] or c['assunto']}")
    linhas.append("")
    linhas.append("4. A EQUIPE — tarefas abertas e vencidas de cada um")
    for r in bd.ler(
            f"""SELECT u.full_name AS nome, count(*)::int AS abertas,
                      sum(CASE WHEN t.due_date < %s THEN 1 ELSE 0 END)::int AS vencidas
                 FROM tasks t JOIN users u ON u.id = t.assigned_user_id
                WHERE t.status NOT IN ('CONCLUIDA','CANCELADA') AND t.source_type <> %s
                  AND {_pg(nao_suspensa_t)}
                GROUP BY u.id ORDER BY 3 DESC, 2 DESC, u.id""",
            (hoje.isoformat(), DESPACHO, *params_suspensao_t)):
        linhas.append(f"   {r['nome']}: {r['abertas']} aberta(s), {r['vencidas'] or 0} vencida(s)")
    linhas.append("")
    envios = bd.ler(
        f"""SELECT regra, count(*)::int AS n FROM ge_achados WHERE resolvido_em IS NULL
             AND regra IN ({','.join(['%s'] * len(_REGRAS_DE_CENTRAL))}) GROUP BY regra
             ORDER BY regra""",
        _REGRAS_DE_CENTRAL)
    linhas.append("5. CENTRAIS — o que ainda não foi registrado como enviado")
    linhas += [f"   {ROTULOS.get(e['regra'], e['regra'])}: {e['n']}" for e in envios] or ["   nada pendente"]
    linhas += ["", "6. O QUE O AGENTE FEZ NESTA RODADA",
               f"   {resumo.get('novos', 0)} achado(s) novo(s), {resumo.get('resolvidos', 0)} "
               f"resolvido(s); {resumo.get('criadas', 0)} tarefa(s) aberta(s), "
               f"{resumo.get('fechadas', 0)} fechada(s), {resumo.get('cobradas', 0)} cobrada(s)."]
    triagem = resumo.get("triagem") or {}
    if triagem.get("triados"):
        linhas.append(f"   Malote: {triagem['triados']} expediente(s) lido(s), "
                      f"{triagem.get('tarefas', 0)} tarefa(s) aberta(s) para quem cumpre.")
    linhas += [""] + _fraudes_entradas_pela_ia(con, hoje)
    linhas += ["", "Lembrete: credenciais de produção da CRA e CENPROT, ONR, ON-RCPN e "
               "Resolve, e o login nos portais da CRC, CENSEC, DOI/e-CAC e SIRC-Web.",
               "", "Este relato se renova a cada rodada; o de ontem fica no histórico."]
    return "\n".join(linhas)


def _fraudes_entradas_pela_ia(con, hoje: date) -> list[str]:
    """A seção 7 do despacho: a lista diária do que a IA pôs em Fraudes (LX13, A4-b).

    DESDE A RODADA ANTERIOR que terminou, e não desde ontem: sem rodada no fim
    de semana, «ontem» perderia o sábado. A primeira rodada olha sete dias. A
    janela começa no INÍCIO da rodada anterior — o que entrou durante ela sai
    nas duas listas, e repetir é melhor que perder."""
    import malote_fraudes as MF
    anterior = _banco(con).valor(
        """SELECT max(iniciada_em) AS m FROM ge_execucoes
            WHERE hoje < %s AND terminada_em IS NOT NULL AND erro IS NULL""",
        (hoje.isoformat(),))
    desde = anterior or (hoje - timedelta(days=7)).isoformat()
    entradas = MF.entradas_pela_ia(con, desde)
    linhas = [f"7. FRAUDES ENTRADAS PELA IA ({len(entradas)}) — sem revisão antes, por sua ordem "
              "de 13/10/2026; confira em Fraudes e inative o que estiver errado"]
    for a in entradas[:40]:
        quem = a["nome"] or a["documento"] or "?"
        linhas.append(f"   #{a['id']} {quem} — {MF._ROTULO.get(a['papel'], a['papel'])} — {a['origem']}")
    if len(entradas) > 40:
        linhas.append(f"   … e mais {len(entradas) - 40}: veja a tela de Fraudes")
    if not entradas:
        linhas.append("   nenhuma desde a rodada anterior")
    return linhas


_REGRAS_DE_CENTRAL = tuple(sorted(REGRAS_DAS_CENTRAIS))


def publicar_despacho(con, hoje: date, resumo: dict) -> int | None:
    """O despacho do dia do oficial — num RELATO, e não numa tarefa.

    Ordem do oficial em 12/10/2026: «não acho interessante todo dia criar um
    relatório geral em tarefa para o gestor, se ele não conseguir vencer num
    dia, fica acumulando». O despacho vai para `relatos_diarios` (janela no
    painel); a tarefa-despacho que estiver aberta fecha, com a nota do porquê.
    Devolve o id do relato. A carga da equipe sai junto, noutro relato.
    """
    import carga_da_equipe as CARGA
    import relatos_diarios as RD
    responsaveis = inferir_responsaveis(con)
    dono = (responsaveis.get("GESTAO") or {}).get("titular") or _admin(con)
    if dono is None:
        return None
    texto = despacho_do_oficial(con, hoje, resumo, dono)
    RD.aposentar_tarefas_diarias(con, DESPACHO, "O despacho do dia passou a ser um relato "
                                 "(painel → Relatos do dia), por ordem do oficial em 12/10/2026.")
    rid = RD.publicar(con, dia=hoje, origem="GESTOR_DESPACHO", destinatario_id=RD.GESTAO,
                      setor="GESTAO", titulo=f"Despacho do gestor — {hoje:%d/%m/%Y}", corpo=texto)
    corpo_carga, itens = CARGA.texto_do_relato(con, hoje)
    RD.publicar(con, dia=hoje, origem="CARGA_DA_EQUIPE", destinatario_id=RD.GESTAO,
                setor="GESTAO", titulo=f"A carga da equipe — {hoje:%d/%m/%Y}", corpo=corpo_carga,
                itens=itens)
    return rid



def rodar(con, hoje: date, *, pasta_dados: Path | None = None,
          pasta_relatorio: Path | None = None, triagem: dict | None = None) -> dict:
    bd = _banco(con)
    init_gestor_schema(con)
    exe = bd.escrever(
        "INSERT INTO ge_execucoes (iniciada_em, hoje) VALUES (%s, %s) RETURNING id",
        (_agora(), hoje.isoformat()))[0]["id"]
    try:
        achados = GC.conferir(con, hoje, pasta_dados=pasta_dados)
        faltou = aplicar_distribuicao(con)
        responsaveis = inferir_responsaveis(con)
        resumo = gravar_achados(con, achados, hoje)
        resumo["distribuicao_faltou"] = faltou
        resumo.update(sincronizar_tarefas(con, achados, responsaveis, hoje))
        resumo["cobradas"] = cobrar_vencidas(con, hoje)
        resumo["achados"] = len(achados)
        resumo["nao_mediu"] = sum(a["gravidade"] == "NAO_MEDIU" for a in achados)
        resumo["triagem"] = triagem or {}
        resumo["despacho"] = publicar_despacho(con, hoje, resumo)
        # O DIA DO REGISTRO CIVIL (09/10/2026): depois dos achados gravados,
        # para o boletim ler a fila de hoje e não a de ontem.
        resumo["boletim_rcpn"] = GRC.publicar_boletim(con, hoje)
        caminho = None
        if pasta_relatorio is not None:
            pasta_relatorio.mkdir(parents=True, exist_ok=True)
            caminho = pasta_relatorio / f"conferencia_{hoje.isoformat()}.html"
            caminho.write_text(relatorio_html(con, hoje, resumo), encoding="utf-8")
        resumo["relatorio"] = str(caminho) if caminho else None
        bd.escrever(
            """UPDATE ge_execucoes SET terminada_em=%s, achados=%s, novos=%s,
                   resolvidos=%s, tarefas_criadas=%s, tarefas_fechadas=%s,
                   tarefas_cobradas=%s, nao_mediu=%s, relatorio=%s WHERE id=%s""",
            (_agora(), resumo["achados"], resumo["novos"], resumo["resolvidos"],
             resumo["criadas"], resumo["fechadas"], resumo["cobradas"],
             resumo["nao_mediu"], resumo["relatorio"], exe))
        con.commit()
        return resumo
    except Exception as erro:
        con.rollback()
        bd.escrever(
            "UPDATE ge_execucoes SET terminada_em=%s, erro=%s WHERE id=%s",
            (_agora(), f"{type(erro).__name__}: {erro}", exe))
        con.commit()
        raise


def rodada_diaria(banco: Path, pasta_dados: Path | None, pasta_relatorio: Path | None,
                  hoje: date | None = None, escrever=print) -> int:
    """A rodada das 07:30, inteira: a IA lê os textos, a conferência roda, e
    saem o financeiro e o resumo da semana. Devolve o código de saída.

    MORA AQUI, E NÃO NO SCRIPT DO AGENDADOR, desde 06/10/2026: lá ela ficava
    fora do pacote, e o varredor de função sem tela não achava quem chamava a
    leitura — nem o pacote levaria a ordem das três coisas.

    A ORDEM IMPORTA. A leitura vem antes, porque a conferência transforma o que
    a IA apontou em tarefa; se a leitura falhar, a conferência roda igual. O
    financeiro vem depois e abre o banco SÓ PARA LER: o erro de um relatório
    não desfaz as tarefas do dia.
    """
    import traceback
    hoje = hoje or date.today()
    banco = Path(banco)
    if not banco.exists():
        escrever(f"ERRO: banco não encontrado em {banco}")
        return 2
    # O `timeout` da conexão JÁ É a espera pela trava; nenhum ajuste extra
    # da conexão é preciso aqui.
    # PELA PORTA (`banco_pg.conectar`), e não pelo `sqlite3.connect`: o
    # Agendador roda fora do sistema, ninguém instala o desvio, e o acesso
    # nativo recusa o sqlite3 cru. Vale também para as leituras do fim.
    con = banco_pg.conectar(str(banco), timeout=60)
    try:
        import gestor_leitura
        lido = gestor_leitura.ler_pendentes(con, pasta_dados or banco.parent)
        escrever(f"  leitura do texto: {lido}")
    except Exception:                                   # noqa: BLE001
        escrever("AVISO: a leitura do texto pela IA não rodou (a conferência roda).")
        escrever(traceback.format_exc())
    # O MALOTE DEPOIS DA LEITURA E ANTES DA CONFERÊNCIA: as tarefas que a
    # triagem abre entram no despacho da mesma rodada.
    triagem: dict = {}
    try:
        import gestor_expedientes
        triagem = gestor_expedientes.triar_pendentes(con, pasta_dados or banco.parent, hoje)
        escrever(f"  triagem do malote: {triagem}")
    except Exception:                                   # noqa: BLE001
        escrever("AVISO: a triagem do malote não rodou (a conferência roda).")
        escrever(traceback.format_exc())
    # AS CARGAS DO RI AO ONR ANTES DA CONFERÊNCIA (09/10/2026): o agente de
    # cargas entrega e manda; a conferência, logo depois, cobra o que sobrou.
    try:
        GCR.rodada(con, banco, hoje, escrever=escrever)
    except Exception:                                   # noqa: BLE001
        escrever("AVISO: o agente de cargas do RI não rodou (a conferência roda).")
        escrever(traceback.format_exc())
    # AS CARGAS DO RCPN TAMBÉM ANTES DA CONFERÊNCIA (09/10/2026): o agente
    # prepara os arquivos do dia; a conferência os transforma na tarefa
    # «o que subir hoje» do Registro Civil.
    try:
        GCRC.rodada(con, banco, hoje, escrever=escrever)
    except Exception:                                   # noqa: BLE001
        escrever("AVISO: o agente de cargas do RCPN não rodou (a conferência roda).")
        escrever(traceback.format_exc())
    # O AGENTE DO RCPN RESOLVE O OBJETIVO ANTES DA CONFERÊNCIA (09/10/2026): a
    # anotação devida por assento cancelado não chega a virar tarefa.
    try:
        GRC.rodada(con, banco, hoje, escrever=escrever)
    except Exception:                                   # noqa: BLE001
        escrever("AVISO: o agente do RCPN não rodou (a conferência roda).")
        escrever(traceback.format_exc())
    # O AGENTE DO RTD/PJ CONSERTA O QUE É MECÂNICO ANTES DA CONFERÊNCIA
    # (09/10/2026): o título já atendido e o selo da prenotação na coluna do
    # ato. O que ele mudou volta no relatório, para o oficial revisar.
    try:
        # O INTERRUPTOR (revisão de 22/10/2026, M19): a correção escreve em
        # ato lavrado sem clique; agora o oficial a desliga nas configurações.
        _lig = _banco(con).um("SELECT value FROM settings WHERE key = %s",
                              ("rtdpj_corrigir_automatico",))
        if str((_lig["value"] if _lig else "LIGADO") or "LIGADO").strip().upper() == "DESLIGADO":
            escrever("  agente do RTD/PJ: correção automática DESLIGADA nas "
                     "configurações — nada foi mudado.")
        else:
            with con:
                feito = GRT.corrigir(con, hoje, escrever=escrever)
            escrever(f"  agente do RTD/PJ: {feito}")
    except Exception:                                   # noqa: BLE001
        escrever("AVISO: o agente do RTD/PJ não corrigiu nada (a conferência roda).")
        escrever(traceback.format_exc())
    # O AGENTE FINANCEIRO PERGUNTA AO PORTAL DO SELO ANTES DA CONFERÊNCIA
    # (09/10/2026): a conferência compara o que o TJ respondeu; sem rede, ela
    # roda igual e diz quantos selos ficaram sem resposta.
    try:
        escrever(f"  portal do selo: {GFI.consultar_portal(con, hoje)}")
    except Exception:                                   # noqa: BLE001
        escrever("AVISO: a consulta ao Portal do Selo não rodou (a conferência roda).")
        escrever(traceback.format_exc())
    # A SELEÇÃO DO PLD/COAF ANTES DA CONFERÊNCIA (23/10/2026): até aqui ela só
    # rodava quando alguém clicava «Selecionar» na tela do ADMIN, e o prazo do
    # art. 151 (30 dias para a espécie, 60 para a análise) corria sem ninguém
    # olhar. A conferência, logo depois, cobra do oficial o caso que espera.
    try:
        import pld_coaf
        with con:
            escrever(f"  seleção do PLD/COAF: {pld_coaf.selecionar(con)}")
    except Exception:                                   # noqa: BLE001
        escrever("AVISO: a seleção do PLD/COAF não rodou (a conferência roda).")
        escrever(traceback.format_exc())
    try:
        resumo = rodar(con, hoje, pasta_dados=pasta_dados,
                       pasta_relatorio=pasta_relatorio, triagem=triagem)
    except Exception:                                   # noqa: BLE001
        escrever("ERRO: a conferência não terminou. Nada pela metade ficou gravado.")
        escrever(traceback.format_exc())
        return 1
    finally:
        con.close()
    for chave in ("achados", "novos", "resolvidos", "criadas", "fechadas",
                  "reabertas", "cobradas", "nao_mediu", "distribuicao_faltou",
                  "despacho", "relatorio"):
        escrever(f"  {chave}: {resumo.get(chave)}")
    if pasta_relatorio is None:
        return 0
    try:
        import gestor_financeiro
        leitura = banco_pg.conectar(f"file:{banco}?mode=ro", uri=True, timeout=60)
        try:
            for caminho in gestor_financeiro.escrever(leitura, hoje, pasta_relatorio):
                escrever(f"  relatório: {caminho}")
        finally:
            leitura.close()
    except Exception:                                   # noqa: BLE001
        escrever("AVISO: o relatório financeiro/semanal não saiu (a conferência saiu).")
        escrever(traceback.format_exc())
    # O RELATÓRIO DE ERROS, POR QUEM PRATICOU — pedido do oficial em 06/10/2026.
    # A tela mora no pacote; até ele subir, o arquivo do dia é o caminho.
    try:
        import gestor_erros
        leitura = banco_pg.conectar(f"file:{banco}?mode=ro", uri=True, timeout=60)
        try:
            caminho = gestor_erros.escrever_html(leitura, hoje or date.today(), pasta_relatorio)
            escrever(f"  relatório: {caminho}")
        finally:
            leitura.close()
    except Exception:                                   # noqa: BLE001
        escrever("AVISO: o relatório de erros não saiu (a conferência saiu).")
        escrever(traceback.format_exc())
    # O PAINEL DAS NOTAS (09/10/2026): minutas com a revisão, livros, termos e a
    # CENSEC por quinzena. Abre o banco só para ler, como os dois de cima.
    try:
        leitura = banco_pg.conectar(f"file:{banco}?mode=ro", uri=True, timeout=60)
        try:
            caminho = AGN.escrever_relatorio(leitura, hoje or date.today(), pasta_relatorio)
            escrever(f"  relatório: {caminho}")
        finally:
            leitura.close()
    except Exception:                                   # noqa: BLE001
        escrever("AVISO: o painel das Notas não saiu (a conferência saiu).")
        escrever(traceback.format_exc())
    # O RELATÓRIO FISCAL (09/10/2026): selos × Portal do Selo, gratuidades e o
    # saldo do selador, do mês corrente e do anterior. Só lê.
    try:
        leitura = banco_pg.conectar(f"file:{banco}?mode=ro", uri=True, timeout=60)
        try:
            for caminho in GFI.escrever_relatorio(leitura, hoje or date.today(), pasta_relatorio):
                escrever(f"  relatório: {caminho}")
        finally:
            leitura.close()
    except Exception:                                   # noqa: BLE001
        escrever("AVISO: o relatório fiscal não saiu (a conferência saiu).")
        escrever(traceback.format_exc())
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Conferência diária do gestor.")
    p.add_argument("--banco", required=True)
    p.add_argument("--hoje", default=date.today().isoformat())
    p.add_argument("--pasta-dados", default=None,
                   help="pasta de dados (backups e chaves da IA)")
    p.add_argument("--relatorio", default=None, help="pasta dos relatórios HTML")
    a = p.parse_args(argv)
    return rodada_diaria(Path(a.banco),
                         Path(a.pasta_dados) if a.pasta_dados else None,
                         Path(a.relatorio) if a.relatorio else None,
                         GC._dia(a.hoje))


if __name__ == "__main__":
    sys.exit(main())
