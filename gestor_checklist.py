"""A CHECKLIST DE GESTÃO DO DIA — o que o oficial confere, e onde clicar.

    «não consigo clicar nos itens e não vejo checklist» — o oficial, 19/11/2026,
    diante do semáforo de conformidade do painel geral

O QUE FALTAVA
    O semáforo (`conformidade`) diz a cor de cada área, e só. Os cartões não
    levavam a lugar nenhum, e nenhuma tela listava os achados abertos do
    gestor por área: o Relatório de erros mostra só o que tem autor, e só ao
    ADMIN. Quem via um VERMELHO em Notas não tinha onde clicar para saber o quê.

DUAS METADES NUMA TELA SÓ
    1. OS ACHADOS ABERTOS (`ge_achados`, `resolvido_em IS NULL`), agrupados
       pela MESMA área do semáforo — a régua é `conformidade.area_do_achado`,
       e não uma cópia dela: área escrita duas vezes divergiria no primeiro
       setor novo, e o cartão vermelho levaria a uma lista vazia.
       Cada achado traz gravidade, prazo, regra, dias em aberto e o link da
       tela onde se resolve: a ficha do ato (`gestor_erros.alvo`), ou a tela
       da obrigação (`gestor_didatica.onde_da_regra`) — a mesma que a tarefa
       manda abrir.
    2. AS CONFERÊNCIAS DO DIA: uma lista fixa de telas que alguém precisa
       abrir todo dia (envios, automação, robôs, leituras, caixas, selos,
       gratuidades, problemas, correções, avisos, tarefas), com a contagem
       quando há uma, e o botão «conferido hoje».

«CONFERIDO HOJE» NÃO É BAIXA
    O botão grava quem olhou e quando (`ge_conferencias_do_dia`) — e só. Ele
    não fecha achado, não conclui tarefa e não muda cor de semáforo. O achado
    sai quando a conferência seguinte do gestor vê que foi resolvido: é a
    regra de `gestor_rotina`, e uma tela que a contornasse seria o carimbo
    que mente (a lição da conferência de 02/10/2026).

SEM RODADA VÁLIDA, NADA É «EM DIA»
    Se o gestor não terminou uma rodada válida (`conformidade.medir`), a tela
    diz isso no topo, e nenhuma área nem item aparece como «em dia»: lista
    vazia, num dia sem medição, quer dizer «não sei», e não «nada a fazer».

CONTAGEM QUE QUEBRA NÃO VIRA ZERO
    Cada contagem abre a sua conexão (no PostgreSQL uma consulta que falha
    aborta a transação inteira) e, quando falha, mostra «não deu para contar».
    É a regra de `painel_numeros`: zero medido e zero por engano são coisas
    diferentes.

ROTINA PRIMEIRO, DÉBITO DEPOIS (24/11/2026)
    «vou tentar separar o que é rotina atual do que é erro e débito passado
    [...] vamos dar sempre prioridade na rotina» — o oficial. Em cada área, os
    achados vistos pela primeira vez há até `CF.ROTINA_DIAS_UTEIS` dias úteis
    vêm primeiro, sob «Rotina»; os mais antigos vêm depois, sob «Débito
    passado», recolhidos mas contados (quantos, e quantos fazem a cor). A
    régua da idade é `conformidade.idade_do_achado`, e a cor «só da rotina»
    é `conformidade.medir(so_rotina=True)`: a mesma régua do semáforo, sem o
    débito. A cor oficial da área não muda — o débito não se esconde.

SÓ O QUE A TI E O ADMINISTRADOR RESOLVEM (25/11/2026, G007)
    «Checklist do dia nao serve para pratica de atos do cartorio, nem para
    atos materiais que necessitam estar fisicamente no cartorio» — o oficial.
    A lista dos achados mostra só as regras de destino TI_ADMIN
    (`gestor_destino.DESTINO`, a tabela única regra → destino). O que é do
    escrevente sai da lista e aparece num quadro à parte, uma linha por regra,
    com a tarefa do gestor que o leva ao processo; o débito passado aparece à
    parte, porque quem o acompanha é o agente de compliance. A COR OFICIAL NÃO MUDA: o semáforo conta todos os achados, de
    qualquer destino, e a tela diz isso ao lado do quadro.
O QUE NÃO CABE À GESTÃO (25/11/2026, T019)
    «permitir que retiremos do checklist do dia [...] itens que nao cabem a
    gestao ou admin» — o oficial. O oficial e o gerente retiram um achado da
    lista com motivo obrigatório (`gestao_retirados`); a marca se prende à
    CHAVE do achado, e a rodada seguinte do gestor não o traz de volta como
    novo. O retirado sai da lista e da contagem desta tela e vai para «Ver os
    retirados», com quem, quando e o motivo, e o botão «Devolver à lista».
    A COR OFICIAL DA ÁREA CONTINUA CONTANDO O RETIRADO — é a do painel e do
    retrato, e ninguém a pinta à mão; ao lado dela vem a cor «sem os
    retirados» e quantos são. Nada se apaga em `ge_achados`.

A ROTINA DO DIA VEM PRIMEIRO (26/11/2026)
    «Sobre as conferências por área, serve para rotinas e demandas do dia a
    dia. Não tem nenhuma demanda de rotina cadastrada lá, só débito passado.»
    — o oficial. No alto de cada área vem o bloco «Rotina do dia»: os itens da
    rotina da serventia (`rotina_da_casa`) que vencem hoje ou estão atrasados,
    com o «Como fazer» e o botão «Feito» — e, para a TI, o bloco «TI e
    sistema» (`?area=TI`). O cadastro é «Rotina da serventia». O «feito» não
    toca em `ge_achados` nem na cor oficial: a cor continua a do gestor.

A ROTINA DO ESCREVENTE NÃO ENTRA (27/11/2026, A011)
    «aparecem na Checklist do dia da gestão [...], mas são trabalho de
    escrevente» — o titular. O item da rotina de destino ESCREVENTE
    (`rotina_da_casa.na_checklist_da_gestao`) sai do bloco «Rotina do dia» e
    fica só em «Minha rotina» do responsável e do suplente; a tela diz quantos
    ficaram fora. Volta à lista, marcado, o que ficou sem ninguém ativo para
    fazê-lo — e, se a volta estiver ligada (`volta_apos`, desligada por
    padrão), o muito atrasado. Os achados do gestor não mudam.

O SIGILO DO PLD
    O achado de PLD/COAF diz o número do caso; o detalhe é sigiloso (CNN,
    art. 154) e a tela do PLD é só do ADMIN. Para o gerente e o auditor o
    título sai trocado por «caso sigiloso», e o link não aparece.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Callable

import conformidade as CF
import gestor_destino as GDS
from bd_nativo import banco

#: Quem abre a checklist (a mesma régua do semáforo no painel geral).
QUEM_VE = ("ADMIN", "MANAGER", "AUDITOR")
#: Quem marca «conferido hoje». O auditor vê e não grava — a regra M2 da casa.
QUEM_CONFERE = ("ADMIN", "MANAGER")

#: A ordem em que os achados aparecem dentro de cada área: o que já custa
#: primeiro, o que é só controle interno por último.
ORDEM_DA_GRAVIDADE = ("VENCIDO", "CRITICO", "PRAZO", "NAO_MEDIU", "OUTRA", "ATENCAO")
ROTULO_DA_GRAVIDADE = {"VENCIDO": "Vencido", "CRITICO": "Crítico", "PRAZO": "Prazo",
                       "NAO_MEDIU": "Não mediu", "ATENCAO": "Atenção", "OUTRA": "Outra"}

#: As regras cujo achado é sigiloso: título e link só para o ADMIN.
REGRAS_SIGILOSAS = frozenset({"PLD_COAF"})
TITULO_SIGILOSO = "Caso de PLD/COAF — sigiloso, só o oficial vê o detalhe"

#: Os processos da automação que a checklist destaca pelo código (o id muda de
#: banco para banco; o código, não): a situação do envio à CENSEC e o envio.
PROCESSOS_EM_DESTAQUE = (("CASA_CENSEC", "CENSEC — situação"),
                         ("ROTINA_CENSEC_ENVIO", "CENSEC — envio"))


# ------------------------------------------------------------------ achados


def _dia(texto) -> date | None:
    bruto = str(texto or "")[:10]
    try:
        return date(int(bruto[:4]), int(bruto[5:7]), int(bruto[8:10]))
    except (ValueError, IndexError):
        return None


def _gravidade(texto) -> str:
    g = str(texto or "").upper()
    return g if g in CF.GRAVIDADES_CONHECIDAS else "OUTRA"


def _link_do_achado(con, chave: str, regra: str) -> str | None:
    """A tela onde o achado se resolve: a ficha do ato, ou a da obrigação.

    Achar o ato é melhor que achar a tela — mas o caminho do ato passa por
    tabelas que podem não existir neste banco, e link que falha não derruba
    a lista: cai na tela da regra, ou em nenhum.
    """
    import gestor_didatica as GD
    import gestor_erros as GER
    try:
        alvo = GER.alvo(con, chave)
        if alvo:
            _, link = GER.descrever(con, *alvo)
            if link:
                return link
    except Exception:                                   # noqa: BLE001
        pass
    tela = GD.onde_da_regra(regra)
    return tela[1] if tela else None


def achados_por_area(con, hoje: date, *, papel: str, area: str | None = None,
                     retiradas: dict[str, dict] | None = None) -> dict:
    """Os achados abertos, por área do semáforo, na ordem da tela. SÓ LÊ.

    Devolve `{area: [achado, ...]}` só com as áreas que têm achado (e só a
    pedida, quando há filtro). Tabela que não existe é exceção: quem chama
    mostra «não deu para ler», nunca lista vazia.

    `retiradas` ({chave: retirada}, de `gestao_retirados.ativas`) marca em
    cada achado a retirada que vale (`retirada`), ou None. Quem separa a
    lista dos retirados é a tela (`montar`): aqui eles vêm todos, como a cor
    oficial os conta.
    """
    retiradas = retiradas or {}
    import gestor_didatica as GD
    grupos: dict[str, list[dict]] = {}
    for r in banco(con).ler(
            """SELECT id, chave, regra, gravidade, setor, titulo, prazo,
                      primeiro_visto_em FROM ge_achados
                WHERE resolvido_em IS NULL ORDER BY id"""):
        cod = CF.area_do_achado(r["setor"], r["regra"])
        if area and cod != area:
            continue
        regra = str(r["regra"] or "")
        sigiloso = regra.upper() in REGRAS_SIGILOSAS and papel != "ADMIN"
        desde = _dia(r["primeiro_visto_em"])
        gravidade = _gravidade(r["gravidade"])
        idade = CF.idade_do_achado(r["primeiro_visto_em"], hoje)
        grupos.setdefault(cod, []).append({
            "id": r["id"],
            # a identidade estável do achado (a do «Retirar» e de «quem resolve»);
            # a tela não a mostra — os formulários mandam o id
            "chave": str(r["chave"]),
            "regra": regra,
            "gravidade": gravidade,
            "titulo": TITULO_SIGILOSO if sigiloso else GD.limpar(r["titulo"]),
            "prazo": str(r["prazo"] or "")[:10] or None,
            "desde": desde.isoformat() if desde else None,
            "dias_em_aberto": (hoje - desde).days if desde else None,
            "idade": idade,
            "faz_a_cor": gravidade != "ATENCAO",
            "destino": GDS.destino(regra),
            "link": None if sigiloso else _link_do_achado(con, r["chave"], regra),
            "retirada": retiradas.get(str(r["chave"])),
        })
    for lista in grupos.values():
        lista.sort(key=lambda a: (ORDEM_DA_GRAVIDADE.index(a["gravidade"]),
                                  a["prazo"] or "9999", a["id"]))
    ordem = [c for c, _ in CF.AREAS] + [CF.OUTROS]
    return {c: grupos[c] for c in ordem if c in grupos}


# ------------------------------------------------------------ as conferências
#
# Cada contagem recebe a conexão e devolve `{"n": int | None, "texto": str}`.
# `n` é o que pede atenção (zero é «nada pendente», medido); `texto` explica.


def _conta_envios(con, hoje):
    import gestor_envios as GE
    itens = GE.pendentes(con)
    faltam = sum(1 for i in itens if not i.get("ja_registrado"))
    return {"n": faltam, "texto": f"{faltam} envio(s) cobrado(s) sem registro"
            + (f", {len(itens) - faltam} registrado(s) esperando a conferência"
               if len(itens) > faltam else "")}


def _conta_automacao(con, hoje):
    import automacao as AU
    linhas = AU.painel(con)
    problema = [x for x in linhas if x.get("ativo") and x["luz"] == "problema"]
    por_codigo = {x["codigo"]: x for x in linhas}
    partes = [f"{len(problema)} rotina(s) ligada(s) com problema na última rodada"]
    luz = {"ok": "em dia", "atencao": "com aviso", "problema": "com problema",
           "nunca": "nunca rodou", "rodando": "rodando"}
    for codigo, rotulo in PROCESSOS_EM_DESTAQUE:
        x = por_codigo.get(codigo)
        if x is None:
            partes.append(f"{rotulo}: não cadastrado")
        elif not x.get("ativo"):
            partes.append(f"{rotulo}: desligado")
        else:
            partes.append(f"{rotulo}: {luz.get(x['luz'], x['luz'])}")
    return {"n": len(problema), "texto": " · ".join(partes)}


def _conta_leituras(con, hoje):
    import gestor_leitura as GL
    n = len(GL.revisoes_para_conferir(con))
    if banco(con).tem_tabela("ge_leituras"):
        n += len(GL.achados_vigentes(con))
    return {"n": n, "texto": f"{n} apontamento(s) da IA sem conferir"}


def _conta_caixas(con, hoje):
    import gestor_caixa as GX
    n = len(GX.fila_do_visto(con))
    return {"n": n, "texto": f"{n} caixa(s) fechado(s) esperando o visto"}


def _conta_selos_cancelados(con, hoje):
    import selo_portal as SP
    n = int(SP.nao_comunicados(con)["n"] or 0)
    return {"n": n, "texto": f"{n} selo(s) cancelado(s) sem comunicar ao TJMA"}


def _conta_gratuidades(con, hoje):
    import selo_portal as SP
    n = len(SP.gratuitos(con, situacao="FALTANDO"))
    return {"n": n, "texto": f"{n} gratuidade(s) com o que falta para o Portal do Selo"}


def _conta_problemas(con, hoje):
    import ajuda_problemas as AP
    situacoes = tuple(AP.VISTAS[AP.VISTA_EM_ABERTO]["situacoes"])
    n = int(banco(con).valor(
        f"SELECT count(*) FROM aj_problemas WHERE situacao IN "
        f"({', '.join(['%s'] * len(situacoes))})", situacoes) or 0)
    return {"n": n, "texto": f"{n} problema(s) em aberto"}


def _conta_correcoes(con, hoje):
    import correcoes_de_oficio as CDO
    n = int(CDO.contar_por_situacao(con).get(CDO.PROPOSTA) or 0)
    return {"n": n, "texto": f"{n} correção(ões) proposta(s) esperando decisão"}


def _conta_tarefas(con, hoje):
    linha = banco(con).um(
        """SELECT count(*) AS abertas,
                  sum(CASE WHEN due_date IS NOT NULL AND due_date <> ''
                            AND due_date < %s THEN 1 ELSE 0 END) AS vencidas
             FROM tasks WHERE status NOT IN ('CONCLUIDA', 'CANCELADA')""",
        (hoje.isoformat(),)) or {}
    abertas, vencidas = int(linha.get("abertas") or 0), int(linha.get("vencidas") or 0)
    return {"n": vencidas, "texto": f"{vencidas} vencida(s) de {abertas} aberta(s)"}


def _conta_painel_onr(con, hoje):
    import onr_conformidade as OC
    return OC.contagem_para_a_checklist(con, hoje)


#: A LISTA FIXA DAS CONFERÊNCIAS DO DIA, na ordem em que se faz.
#: (código, rótulo, endpoint, contagem ou None, o que olhar)
#: O código é o que se grava em `ge_conferencias_do_dia`: não muda.
CONFERENCIAS: tuple[tuple[str, str, str, Callable | None, str], ...] = (
    ("ENVIOS", "Envios às Centrais", "gestor_envios", _conta_envios,
     "SIRC, CRC, FUNAI, IBGE, CENSEC, DOI e óbitos: o que saiu tem protocolo registrado?"),
    ("AUTOMACAO", "Automação", "automacao_lista", _conta_automacao,
     "As rotinas rodaram? A situação e o envio da CENSEC, e as rodadas do gestor."),
    ("ROBOS", "Robôs", "robos_lista", None,
     "Os robôs ligados responderam, e nenhum ficou parado."),
    ("PAINEL_ONR", "Painel de conformidade do ONR", "ri_onr_conformidade", _conta_painel_onr,
     "Provimento 143, Provimento 195 e ITN 003: o declarado ao ONR tem lastro? As pendências têm "
     "prazo, protocolo e comprovante?"),
    ("LEITURAS", "Leitura dos textos (IA)", "gestor_leituras", _conta_leituras,
     "O que a IA apontou nas minutas e escrituras, para quem qualifica decidir."),
    ("CAIXAS", "Caixas para o visto", "gestor_caixas", _conta_caixas,
     "Os caixas fechados, com o parecer do agente."),
    ("SELOS_CANCELADOS", "Selos cancelados", "selo_cancelamentos", _conta_selos_cancelados,
     "O cancelamento comunicado ao TJMA."),
    ("GRATUIDADES", "Gratuidades", "selo_gratuidades_portal", _conta_gratuidades,
     "O comprovante de cada ato gratuito, para o Portal do Selo."),
    ("PROBLEMAS", "Problemas do sistema", "ajuda_problemas", _conta_problemas,
     "O que quebrou e ainda espera conserto."),
    ("CORRECOES", "Correções de ofício", "correcoes_de_oficio_lista", _conta_correcoes,
     "As correções propostas que esperam a decisão do oficial."),
    ("AVISOS", "Avisos", "nu_avisos_lista", None,
     "Os avisos da serventia em vigor."),
    ("TAREFAS", "Tarefas", "tasks", _conta_tarefas,
     "As tarefas da casa, a começar pelas vencidas."),
)
CODIGOS = frozenset(c for c, *_ in CONFERENCIAS)

#: Os itens cuja contagem sai do que o gestor gravou (`ge_achados`,
#: `ge_leituras`). Sem rodada válida, o zero deles não quer dizer «em dia».
DEPENDEM_DO_GESTOR = frozenset({"ENVIOS", "LEITURAS"})


def conferidos_hoje(con, hoje: date) -> dict[str, dict]:
    """O «conferido hoje» de cada item: {código: {por, em}}. SÓ LÊ.

    No banco em que a tabela ainda não existe (subida que não rodou), nada
    está conferido — e o GET não a cria.
    """
    bd = banco(con)
    if not bd.tem_tabela("ge_conferencias_do_dia"):
        return {}
    return {r["item"]: {"por": r["conferido_por"], "em": str(r["conferido_em"])[:16]}
            for r in bd.ler(
                "SELECT item, conferido_por, conferido_em FROM ge_conferencias_do_dia "
                "WHERE dia = %s", (hoje.isoformat(),))}


class ChecklistError(ValueError):
    """O pedido de «conferido» que não se grava, com o motivo para a tela."""


def marcar_conferido(con, item: str, hoje: date, *, por: str, usuario_id: int | None,
                     agora: datetime | None = None) -> dict:
    """Grava «conferido hoje» no item. Devolve {gravou, por, em}.

    O primeiro do dia fica: o segundo clique não sobrescreve quem conferiu
    antes — devolve `gravou=False` com o nome de quem já conferiu.
    NÃO toca em `ge_achados` nem em `tasks`: conferir não é resolver.
    """
    if item not in CODIGOS:
        raise ChecklistError("Item da checklist desconhecido.")
    agora = agora or datetime.now()
    bd = banco(con)
    bd.escrever(
        """INSERT INTO ge_conferencias_do_dia (item, dia, conferido_em, conferido_por,
                                               usuario_id)
           VALUES (%s, %s, %s, %s, %s) ON CONFLICT (item, dia) DO NOTHING""",
        (item, hoje.isoformat(), agora.isoformat(timespec="seconds"), por, usuario_id))
    gravou = bool(bd.linhas_afetadas)
    linha = bd.um("""SELECT conferido_por, conferido_em FROM ge_conferencias_do_dia
                      WHERE item = %s AND dia = %s""", (item, hoje.isoformat()))
    return {"gravou": gravou, "por": linha["conferido_por"] if linha else por,
            "em": str(linha["conferido_em"])[:16] if linha else None}


# ------------------------------------------------------------------ a tela


def _rotulos_do_gestor() -> dict[str, str]:
    """O nome de cada regra como o título da tarefa o escreve."""
    try:
        import gestor_rotina as GR
        return dict(GR.ROTULOS)
    except Exception:                                   # noqa: BLE001
        return {}


def _medido(db, fn: Callable, *args) -> tuple[Any, str]:
    """Roda `fn(con, *args)` numa conexão só dela: (resultado, erro)."""
    try:
        with db.connect() as con:
            return fn(con, *args), ""
    except Exception as erro:                           # noqa: BLE001
        return None, str(erro) or erro.__class__.__name__


def montar(db, hoje: date | None = None, *, papel: str, area: str | None = None,
           abre: Callable[[str], bool] = lambda _endpoint: True,
           pode_retirar: bool | None = None, volta_apos: int | None = None) -> dict:
    """Tudo o que a tela mostra. SÓ LÊ.

    `abre(endpoint)` diz se esta pessoa abre a tela do item (a rota manda);
    o item que ela não abre aparece sem link, para não levar à recusa.
    `pode_retirar` vem da rota (o TI passa onde o ADMIN passa); sem ele, vale
    o papel. `volta_apos` (dias úteis) liga a volta à gestão do item do
    escrevente muito atrasado; sem ele vale `rotina_da_casa.VOLTA_A_GESTAO_DIAS_UTEIS`
    (desligada), e 0 desliga.
    """
    import gestao_retirados as GR
    import rotina_da_casa as RT
    hoje = hoje or date.today()
    # A área TI só tem rotina (o semáforo não a mede): o filtro vale para o bloco.
    if area not in {c for c, _ in CF.AREAS} | {CF.OUTROS, RT.TI}:
        area = None
    if pode_retirar is None:
        pode_retirar = papel in GR.QUEM_RETIRA
    medicao, erro_medicao = _medido(db, CF.medir, hoje)
    retiradas, erro_retiradas = _medido(db, GR.ativas, GR.CHECKLIST)
    retiradas = retiradas or {}
    chaves = frozenset(retiradas)
    sem_retirados, _ = (_medido(db, lambda con: CF.medir(con, hoje, excluir_chaves=chaves))
                        if chaves else (None, ""))
    # «Só a rotina» é a fila de trabalho: sem o débito e sem o que não cabe à gestão.
    rotina, _ = _medido(db, lambda con: CF.medir(con, hoje, so_rotina=True,
                                                 excluir_chaves=chaves or None))
    todos, erro_achados = _medido(
        db, lambda con: achados_por_area(con, hoje, papel=papel, area=area,
                                         retiradas=retiradas))
    todos = todos or {}
    # G007 primeiro, T019 depois: a lista é só da TI e do administrador; o que
    # é do escrevente ou débito passado vai ao quadro «fora». Dentro da lista,
    # o retirado à mão sai para «Ver os retirados» (de qualquer destino).
    achados = {a: [x for x in lista if x["destino"] == GDS.TI_ADMIN and not x["retirada"]]
               for a, lista in todos.items()}
    achados = {a: lista for a, lista in achados.items() if lista}
    retirados = {a: [x for x in lista if x["retirada"]] for a, lista in todos.items()}
    retirados = {a: lista for a, lista in retirados.items() if lista}
    vivos = {a: [x for x in lista if not x["retirada"]] for a, lista in todos.items()}
    tarefas, erro_tarefas = _medido(db, GDS.tarefas_do_gestor)
    fora = GDS.fora_da_checklist(vivos, None if erro_tarefas else tarefas,
                                 _rotulos_do_gestor())
    conferidos, _ = _medido(db, conferidos_hoje, hoje)
    # A ROTINA DO DIA (26/11/2026): o que vence hoje e o atrasado, por área.
    # A leitura que quebra diz que quebrou: lista vazia seria «nada a fazer».
    do_dia, erro_rotina = _medido(db, lambda con: RT.do_dia(con, hoje, area=area))
    # A011: o item do escrevente fica só em «Minha rotina» de quem responde.
    if volta_apos is None:
        volta_apos = RT.VOLTA_A_GESTAO_DIAS_UTEIS
    do_dia, do_escrevente = RT.na_checklist_da_gestao(do_dia or [], volta_apos=volta_apos)
    rotina_cadastrada, _ = _medido(db, RT.contar)
    medido = bool(medicao and medicao["gestor"]["medido"])
    itens = []
    for codigo, rotulo, endpoint, conta, olhar in CONFERENCIAS:
        contagem, erro = (_medido(db, conta, hoje) if conta else (None, ""))
        itens.append({"codigo": codigo, "rotulo": rotulo, "endpoint": endpoint,
                      "abre": abre(endpoint), "olhar": olhar, "contagem": contagem,
                      "erro": erro, "conferido": (conferidos or {}).get(codigo),
                      "sem_medicao": codigo in DEPENDEM_DO_GESTOR and not medido})
    return {"hoje": hoje.isoformat(), "area": area, "medicao": medicao,
            "erro_medicao": erro_medicao, "medido": medido,
            "rotina_dias_uteis": CF.ROTINA_DIAS_UTEIS,
            # A cor «só da rotina». A medição que falhou não vira VERDE: some.
            "cor_da_rotina": ({a: (rotina["areas"].get(a) or {"cor": CF.VERDE})["cor"]
                               for a in CF.ROTULO_DA_AREA} if rotina and medido else {}),
            "achados": achados, "erro_achados": erro_achados,
            "total_achados": sum(len(v) for v in achados.values()),
            # G007: o que saiu da lista, por destino — contado, e com a tarefa.
            "fora": fora, "erro_tarefas": erro_tarefas,
            "total_fora": {d: sum(x["n"] for x in v) for d, v in fora.items()},
            "abre_tarefa": abre("task_detail"),
            # O QUE NÃO CABE À GESTÃO (T019): fora da lista e da contagem desta
            # tela, contado e à vista em «Ver os retirados». A cor oficial os
            # conta; a «sem os retirados» não — e a medição que falhou não vira
            # VERDE: some.
            "retirados": retirados, "erro_retiradas": erro_retiradas,
            "total_retirados": sum(len(v) for v in retirados.values()),
            "retirados_por_area": {a: len(v) for a, v in retirados.items()},
            # As áreas que a lista mostra: a que só tem retirado também, para
            # dizer que eles existem e qual seria a cor sem eles.
            "areas_da_lista": [a for a in todos if a in achados or a in retirados],
            "cor_sem_retirados": ({a: (sem_retirados["areas"].get(a) or {"cor": CF.VERDE})["cor"]
                                   for a in CF.ROTULO_DA_AREA}
                                  if sem_retirados and medido else {}),
            "motivos_prontos": GR.MOTIVOS_PRONTOS, "motivo_maximo": GR.MOTIVO_MAXIMO,
            "itens": itens, "pode_conferir": papel in QUEM_CONFERE,
            "pode_retirar": bool(pode_retirar),
            # A ROTINA DO DIA: os itens (a rota põe em cada um o link e o «pode
            # marcar» de quem olha), por área, e quantos o cadastro tem.
            "rotina_itens": do_dia, "rotina": RT.por_area(do_dia),
            "erro_rotina": erro_rotina, "total_rotina": len(do_dia),
            # A011: o que é do escrevente não entra na lista; só se conta.
            "total_rotina_do_escrevente": len(do_escrevente),
            "rotina_volta_apos": volta_apos or None,
            "rotina_cadastrada": rotina_cadastrada,
            "abre_cadastro_rotina": abre("rotina_cadastro")}
