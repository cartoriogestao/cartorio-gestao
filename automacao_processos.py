"""O catálogo da automação — as verificações que o despachante roda, e os processos de fábrica.

O CONTRATO, DE UMA LINHA
    def verificar(contexto) -> {"situacao": "OK"|"AVISO"|"ERRO", "relato": str,
                                "achados": [...], "acoes": [...]}

    `relato` é para gente (é o que vai no e-mail e na tarefa), e por isso fala
    em NÚMEROS e não em nomes: o nome da parte fica nos achados, no banco. As
    `acoes` dizem o que a verificação FEZ — vazias quando ela só olhou.

AS TRÊS REGRAS
    1. **«Não mediu» não é «zero».** A que não conseguiu medir devolve ERRO com
       o motivo. Lista vazia porque a tabela não existe não é casa em ordem.
    2. **Credencial que falta é AVISO, e não queda.** «A credencial da CRA não
       está cadastrada» é trabalho para alguém; não é defeito do programa.
    3. **Quem age só age com `pode_agir`.** Desligado, a verificação lê e
       propõe; ligado, ela pode gravar o que é da casa (baixar a pendência,
       conferir a fila) — e diz em `acoes` o que fez. NADA AQUI LAVRA, SELA,
       COBRA OU MANDA À CENTRAL O QUE A CASA NÃO MANDARIA SOZINHA.

DE ONDE VEM CADA MEDIDA, E O QUE CADA UMA NÃO FAZ
    - CRA: **não chama `RemessaPendente`** — a operação está entre as que podem
      marcar o arquivo como baixado do lado de lá (`cra21_api.
      OPERACOES_QUE_ESCREVEM`). Confere a ligação pela única operação sem
      parâmetro (`diagnostico`) e lê no log das Centrais se alguém baixou hoje.
    - SIRC e CRC: as Centrais não têm consulta de «o que está pendente». A
      medida é a que o sistema JÁ calcula (`sirc_remessa`, `crc_carga`).
    - Backup e minutas do CNIB: rodam fora do pacote, pelo Agendador. Aqui se
      lê o arquivo de estado (ou o log) cujo caminho o oficial configurou.
"""
from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import automacao_schema as SCH
from bd_nativo import banco


# ------------------------------------------------------------------ o contexto


@dataclass
class Contexto:
    """O que a verificação recebe. Ela não precisa saber de onde foi chamada."""
    db: Any
    agora: datetime
    pasta_dados: Path
    raiz: Path
    processo: dict
    execucao_id: int = 0
    _feriados: set | None = field(default=None, repr=False)

    @property
    def hoje(self) -> date:
        return self.agora.date()

    @property
    def parametros(self) -> dict:
        return dict(self.processo.get("parametros") or {})

    @property
    def pode_agir(self) -> bool:
        return bool(self.processo.get("pode_agir"))

    @property
    def estado(self) -> dict:
        return dict(self.processo.get("estado") or {})

    def config(self, chave: str) -> str:
        with self.db.connect() as con:
            return SCH.ler_config(con, chave)

    def setting(self, chave: str, padrao: str = "") -> str:
        with self.db.connect() as con:
            linha = banco(con).um("SELECT value FROM settings WHERE key=%s", (chave,))
        return str(linha["value"]) if linha and linha["value"] is not None else padrao

    def feriados(self) -> set:
        if self._feriados is None:
            from ri_schema import ler_feriados_locais
            self._feriados = ler_feriados_locais(self.setting("ri_feriados_locais", ""))
        return self._feriados

    def credencial(self) -> dict:
        """O segredo do cofre que este processo usa. Só no despachante."""
        import automacao_cofre as COFRE
        nome = self.processo.get("usa_credencial")
        if not nome:
            raise COFRE.CofreError("Este processo não tem credencial do cofre configurada.")
        return COFRE.ler(nome, caminho=COFRE.caminho_do_cofre(self.pasta_dados), quem="despachante",
                         processo=str(self.processo.get("codigo") or ""))


def resultado(situacao: str, relato: str, achados: Any = (), acoes: Any = (), **extra) -> dict:
    return {"situacao": situacao, "relato": relato, "achados": list(achados),
            "acoes": list(acoes), **extra}


def _sem_credencial(central: str, onde: str) -> dict:
    return resultado(SCH.AVISO, f"A credencial da {central} não está cadastrada — a "
                     f"verificação não tem como falar com a Central. Cadastre-a em {onde}.",
                     erro="credencial não cadastrada")


def _nao_mediu(o_que: str, erro: BaseException | str) -> dict:
    motivo = erro if isinstance(erro, str) else f"{type(erro).__name__}: {erro}"
    return resultado(SCH.ERRO, f"Não deu para medir {o_que}: {motivo}"[:600],
                     erro=str(motivo)[:500])


# ------------------------------------------------------------------ Protesto


def verificar_cra(ctx: Contexto) -> dict:
    """A remessa da CRA de hoje foi baixada? E a ligação com a Central responde?

    NÃO BAIXA NADA: `RemessaPendente` pode marcar o arquivo como baixado do
    lado de lá, e baixar sem receber no sistema faria a remessa sumir das duas
    pontas. A medida é o log das Centrais (`centrais_log`), onde toda chamada
    da CRA feita pelo sistema fica anotada.
    """
    import centrais_cred as CRED
    if not CRED.tem(CRED.CRA, CRED.PRODUCAO, ctx.pasta_dados):
        return _sem_credencial("CRA", "Administrativo → Configurações → Centrais")
    achados, acoes = [], []
    if ctx.parametros.get("testar_conexao", True):
        import cra21_api as CRA
        diag = CRA.diagnostico(CRED.PRODUCAO, pasta=ctx.pasta_dados)
        if not diag.get("ok"):
            return resultado(SCH.ERRO, f"A CRA não respondeu como devia: {diag.get('motivo')}"[:600],
                             erro=str(diag.get("motivo"))[:500])
        achados.append({"ligacao": "ok", "motivo": diag.get("motivo")})
    with ctx.db.connect() as con:
        bd = banco(con)
        if not bd.tem_tabela("centrais_log"):
            return _nao_mediu("se a remessa foi baixada", "a tabela centrais_log não existe")
        linha = bd.um(
            """SELECT COUNT(*) AS n, MAX(quando) AS ultima FROM centrais_log
                WHERE central=%s AND operacao IN ('Remessa','RemessaPendente')
                  AND nivel <> 'ERRO' AND quando >= %s""",
            (CRED.CRA, ctx.hoje.isoformat()))
    baixadas = int(linha["n"] or 0)
    achados.append({"baixadas_hoje": baixadas, "ultima": linha["ultima"]})
    if not baixadas:
        return resultado(
            SCH.AVISO,
            f"Ninguém baixou a remessa da CRA hoje até as {ctx.agora:%H:%M}. Pelo roteiro "
            "das Centrais, o retorno e o andamento vão até as 11:30 e a confirmação até as "
            "14:10. Baixe em Protesto → O dia da CRA.", achados, acoes)
    return resultado(SCH.OK, f"A remessa da CRA foi baixada hoje ({baixadas} chamada(s), "
                     f"a última às {str(linha['ultima'])[11:16]}).", achados, acoes)


def verificar_cenprot(ctx: Contexto) -> dict:
    """Pedidos de protesto que chegaram pela CENPROT hoje e ainda não estão na casa."""
    import cenprot_api as API
    import cenprot_pendencias as CP
    import centrais_cred as CRED
    import cn_schema as CN
    if not CRED.tem(CRED.CENPROT, CRED.PRODUCAO, ctx.pasta_dados):
        return _sem_credencial("CENPROT", "Administrativo → Configurações → Centrais")
    acoes = []
    try:
        if ctx.pode_agir:
            r = CP.baixar(ctx.db, CN.PEDIDO_PROTESTO, ambiente=CRED.PRODUCAO,
                          quem="AUTOMACAO", pasta=ctx.pasta_dados, data=ctx.hoje.isoformat())
            acoes.append({"acao": "baixou os pedidos de protesto de hoje", **{
                k: r.get(k) for k in ("vieram", "entraram", "repetidas", "sem_titulo")}})
            novos = 0
            vieram = int(r.get("vieram") or 0)
        else:
            # A MESMA LEITURA DA BAIXA (`_lista_da_resposta` e `_procurar`), e não
            # uma parecida: duas leituras da mesma resposta divergiriam.
            itens = CP._lista_da_resposta(API.pedidos_de_protesto(
                CRED.PRODUCAO, data=ctx.hoje.isoformat(), pasta=ctx.pasta_dados))
            campo = CP.CODIGO_DA_ESPECIE[CN.PEDIDO_PROTESTO]
            codigos = {str(CP._procurar(i, campo) or "").strip() for i in itens} - {""}
            with ctx.db.connect() as con:
                ja = {str(x["codigo"]) for x in banco(con).ler(
                    "SELECT codigo FROM cn_pendencias WHERE especie=%s AND ambiente=%s",
                    (CN.PEDIDO_PROTESTO, CRED.PRODUCAO))}
            novos = len(codigos - ja)
            vieram = len(codigos)
    except (API.CenprotError, CRED.CredencialError, CP.PendenciaError) as erro:
        return _nao_mediu("os pedidos da CENPROT", erro)
    with ctx.db.connect() as con:
        painel = {p["especie"]: p for p in CP.painel(con)}
    esperando = int((painel.get(CN.PEDIDO_PROTESTO) or {}).get("esperando") or 0)
    achados = [{"vieram_hoje": vieram, "ainda_nao_baixados": novos, "esperando_resposta": esperando}]
    if novos or esperando:
        partes = []
        if novos:
            partes.append(f"{novos} pedido(s) de protesto chegaram hoje na CENPROT e ainda não "
                          "foram baixados para o sistema")
        if esperando:
            partes.append(f"{esperando} pedido(s) baixados esperam resposta do balcão")
        return resultado(SCH.AVISO, "; ".join(partes) + ". Veja em Protesto → CENPROT.",
                         achados, acoes)
    return resultado(SCH.OK, f"CENPROT em dia: {vieram} pedido(s) hoje, nenhum esperando.",
                     achados, acoes)


# ------------------------------------------------------------------ RI


def verificar_onr_fila(ctx: Contexto) -> dict:
    """O que subiu ao ONR e a fila dele ainda não aceitou (ou recusou)."""
    import centrais_cred as CRED
    import onr_api as API
    import ri_onr_central as ROC
    import ri_onr_central_schema as ESQ
    ambiente = API.ambiente_da_casa()
    if not CRED.tem(CRED.ONR, ambiente, ctx.pasta_dados):
        return _sem_credencial("ONR", "Administrativo → Configurações → Centrais")
    horas = int(ctx.parametros.get("horas_sem_resposta", 24))
    acoes, achados = [], []
    try:
        if ctx.pode_agir:
            r = ROC.conferir_a_fila(ctx.db, agora=ctx.agora.isoformat(timespec="seconds"),
                                    pasta=ctx.pasta_dados)
            acoes.append({"acao": "conferiu a fila do ONR", **r})
        else:
            linhas = API.fila(pasta=ctx.pasta_dados)
            linhas = linhas if isinstance(linhas, list) else ([linhas] if linhas else [])
            recusadas = sum(1 for i in linhas if isinstance(i, dict) and ROC._situacao_da_fila(
                i.get("situacao") or i.get("status")) == ESQ.RECUSADO)
            achados.append({"fila_do_onr": len(linhas), "recusadas_na_fila": recusadas})
    except (API.OnrError, CRED.CredencialError) as erro:
        return _nao_mediu("a fila do ONR", erro)
    limite = (ctx.agora - timedelta(hours=horas)).isoformat(timespec="seconds")
    with ctx.db.connect() as con:
        bd = banco(con)
        if not bd.tem_tabela("ri_onr_envios"):
            return _nao_mediu("os envios ao ONR", "a tabela ri_onr_envios não existe")
        presos = int(bd.valor("SELECT COUNT(*) FROM ri_onr_envios WHERE situacao=%s AND enviado_em < %s",
                              (ESQ.ENVIADO, limite)) or 0)
        recusados = int(bd.valor("SELECT COUNT(*) FROM ri_onr_envios WHERE situacao=%s",
                                 (ESQ.RECUSADO,)) or 0)
    achados.append({"enviados_sem_resposta": presos, "recusados": recusados, "horas": horas})
    recusadas_remotas = sum(int(a.get("recusadas_na_fila") or 0) for a in achados)
    if presos or recusados or recusadas_remotas:
        return resultado(SCH.AVISO,
                         f"ONR: {recusados} envio(s) recusado(s), {presos} sem resposta há mais de "
                         f"{horas} h" + (f", {recusadas_remotas} recusa(s) na fila" if recusadas_remotas else "")
                         + ". Veja em Registro de Imóveis → ONR.", achados, acoes)
    return resultado(SCH.OK, "ONR em dia: nada recusado e nada parado na fila.", achados, acoes)


def verificar_wsoficio(ctx: Contexto) -> dict:
    """Ofícios e penhoras do Ofício Eletrônico (WSOfício) que chegaram desde a última olhada."""
    import onr_wsoficio as WS
    ambiente = ctx.setting("onr_certidoes_ambiente", WS.PRODUCAO) or WS.PRODUCAO
    ambiente = ambiente if ambiente in WS.BASE else WS.PRODUCAO
    sit = WS.situacao(ambiente, pasta=ctx.pasta_dados)
    if not (sit["tem_chave"] and sit["id_parceiro"] and sit["cpf"] and sit["email"]):
        return _sem_credencial("WSOfício (ID do parceiro, chave, CPF e e-mail)",
                               "Registro de Imóveis → Certidões do ONR")
    dias = int(ctx.parametros.get("dias", 7))
    de = (ctx.hoje - timedelta(days=dias)).isoformat()
    try:
        sessao = WS.Sessao(ambiente=ambiente, pasta=ctx.pasta_dados)
        sessao.entrar()
        oficios = int(sessao.pedidos_de_oficio(de=de, ate=ctx.hoje.isoformat()).get("QtdeRegistros") or 0)
        penhoras = int(sessao.pedidos_de_penhora(de=de, ate=ctx.hoje.isoformat()).get("QtdeRegistros") or 0)
    except (WS.WSOficioError, ValueError, OSError) as erro:
        return _nao_mediu("os ofícios e penhoras do WSOfício", erro)
    antes = ctx.estado
    estado = {"oficios": oficios, "penhoras": penhoras, "dias": dias, "medido_em": ctx.hoje.isoformat()}
    achados = [estado]
    if not antes:
        novos = oficios + penhoras
    else:
        novos = max(0, oficios - int(antes.get("oficios") or 0)) + max(0, penhoras - int(antes.get("penhoras") or 0))
    if novos:
        return resultado(SCH.AVISO,
                         f"WSOfício: {oficios} ofício(s) e {penhoras} penhora(s) nos últimos {dias} dias — "
                         f"{novos} a mais que na última verificação. Confira se foram respondidos.",
                         achados, estado=estado)
    return resultado(SCH.OK, f"WSOfício: {oficios} ofício(s) e {penhoras} penhora(s) nos últimos "
                     f"{dias} dias, nenhum novo desde a última verificação.", achados, estado=estado)


def verificar_cnib(ctx: Contexto) -> dict:
    """Matrículas com parte que bate com ordem ativa da CNIB e ainda sem decisão."""
    import ri_cnib
    with ctx.db.connect() as con:
        if not banco(con).tem_tabela("ri_cnib_decisoes"):
            return _nao_mediu("as pendências da CNIB", "a tabela ri_cnib_decisoes não existe")
        pendentes = ri_cnib.pendentes(con)
    achados = [{"matricula": p.get("matricula_numero"), "criterio": p.get("criterio")}
               for p in pendentes[:200]]
    if pendentes:
        por_doc = sum(1 for p in pendentes if p.get("criterio") == "documento")
        return resultado(SCH.AVISO,
                         f"CNIB: {len(pendentes)} caso(s) sem decisão ({por_doc} pelo documento, "
                         f"{len(pendentes) - por_doc} pelo nome — homônimo é comum). Decida em "
                         "Registro de Imóveis → CNIB.", achados)
    return resultado(SCH.OK, "CNIB: nenhuma ordem ativa sem decisão nas matrículas.")


# ------------------------------------------------------------------ RCPN


def verificar_sirc(ctx: Contexto) -> dict:
    """O que o SIRC ainda não recebeu — prazo de UM dia útil (art. 225).

    A medida é a do sistema (`sirc_remessa`), e não uma consulta ao SIRC: a
    Central não tem por onde perguntar «o que falta». O acervo não entra
    (`pendentes_de_remessa` já o deixa de fora).
    """
    import sirc_remessa as SR
    from ri_schema import dias_uteis_entre
    with ctx.db.connect() as con:
        pendentes = SR.sem_os_ja_enviados(con, SR.pendentes_de_remessa(con))
    feriados = ctx.feriados()
    vencidos, hoje_vence = 0, 0
    achados = []
    for r in pendentes:
        datas = [str(a.get("data_ato") or "")[:10] for a in (r.get("atos") or [])] or \
                [str(r.get("data_ato") or "")[:10]]
        datas = [d for d in datas if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d)]
        if not datas:
            continue
        uteis = dias_uteis_entre(date.fromisoformat(max(datas)), ctx.hoje, feriados)
        if uteis > 1:
            vencidos += 1
        elif uteis == 1:
            hoje_vence += 1
        achados.append({"assento_id": r.get("assento_id"), "tipo": r.get("tipo"),
                        "data": max(datas), "dias_uteis": uteis})
    if vencidos:
        return resultado(SCH.ERRO,
                         f"SIRC: {vencidos} comunicação(ões) com o prazo de 1 dia útil VENCIDO e "
                         f"{len(pendentes) - vencidos} outra(s) pendente(s). Envie em Registro Civil → SIRC.",
                         achados[:300])
    if pendentes:
        return resultado(SCH.AVISO,
                         f"SIRC: {len(pendentes)} comunicação(ões) a enviar"
                         + (f", {hoje_vence} vencendo hoje" if hoje_vence else "") + ".", achados[:300])
    return resultado(SCH.OK, "SIRC em dia: nada pendente de remessa.")


def verificar_crc(ctx: Contexto) -> dict:
    """Assentos recentes que a CRC ainda não recebeu.

    A carga da CRC leva também o acervo histórico (é para isso que ela
    existe), e por isso o total é grande de propósito: a medida que pede gente
    é a dos assentos lavrados nos últimos `dias` (parâmetro, padrão 10).
    """
    import crc_carga as CRC
    dias = int(ctx.parametros.get("dias", 10))
    with ctx.db.connect() as con:
        pendentes = CRC.pendentes_de_carga(con)
    limite = (ctx.hoje - timedelta(days=dias)).isoformat()
    recentes = [p for p in pendentes if str(p.get("data_ato") or "")[:10] >= limite]
    achados = [{"total_pendente": len(pendentes), "recentes": len(recentes), "dias": dias}]
    if recentes:
        return resultado(SCH.AVISO,
                         f"CRC: {len(recentes)} assento(s) dos últimos {dias} dias ainda não foram à "
                         f"carga (no total, com o acervo, são {len(pendentes)}).", achados)
    return resultado(SCH.OK, f"CRC: nenhum assento dos últimos {dias} dias sem carga "
                     f"(o total com o acervo é {len(pendentes)}).", achados)


# ------------------------------------------------------------------ a casa


def verificar_malote(ctx: Contexto) -> dict:
    """O Malote Digital responde? Sem credencial — nunca manda login nem senha."""
    import malote_agente as MA
    r = MA.sondar_malote_digital(timeout=int(ctx.parametros.get("timeout", 20)))
    if not r.get("responde"):
        return resultado(SCH.ERRO, f"O Malote Digital não respondeu: {r.get('erro')}"[:600],
                         [r], erro=str(r.get("erro"))[:500])
    return resultado(SCH.OK, f"O Malote Digital respondeu (versão {r.get('versao') or 'não informada'}).", [r])


def verificar_censec(ctx: Contexto) -> dict:
    """O envio automático à CENSEC: ligado? falhou? o que ficou impedido?"""
    import censec_automatico as AUTO
    ligado = AUTO.envio_ligado(ctx.db)
    desde = (ctx.agora - timedelta(days=3)).isoformat(timespec="seconds")
    with ctx.db.connect() as con:
        bd = banco(con)
        achados = AUTO.regra(con, ctx.hoje)
        ultimo_ok = bd.valor("SELECT MAX(ts) FROM audit_logs WHERE action=%s AND ts >= %s",
                             (AUTO.ACAO_ENVIOU, desde))
        ultima_falha = bd.valor("SELECT MAX(ts) FROM audit_logs WHERE action=%s AND ts >= %s",
                                (AUTO.ACAO_FALHOU, desde))
    resumo = [{"chave": a["chave"], "gravidade": a["gravidade"], "titulo": a["titulo"]} for a in achados]
    if ultima_falha and (not ultimo_ok or str(ultima_falha) > str(ultimo_ok)):
        return resultado(SCH.ERRO, f"CENSEC: o último envio automático FALHOU ({str(ultima_falha)[:16]}).",
                         resumo)
    vencidos = sum(1 for a in achados if a["gravidade"] == "VENCIDO")
    if vencidos:
        return resultado(SCH.ERRO, f"CENSEC: {vencidos} ponto(s) com prazo vencido e "
                         f"{len(achados) - vencidos} outro(s).", resumo)
    if achados or not ligado:
        texto = f"CENSEC: {len(achados)} ponto(s) a resolver" if achados else "CENSEC"
        if not ligado:
            texto += " — e o envio automático está DESLIGADO nas configurações"
        return resultado(SCH.AVISO, texto + ".", resumo)
    return resultado(SCH.OK, "CENSEC em dia: envio automático ligado e nada impedido.")


# O ARQUIVO QUE A VERIFICAÇÃO LÊ TEM DE MORAR NAS PASTAS DA CASA (revisão de
# segurança de 26/10/2026, PR #11, achado M3). Os caminhos do estado do backup
# e do log do CNIB vêm da tela de configuração, e até aqui valia QUALQUER
# arquivo da máquina: quem gravasse ali o `pgpass.conf`, o `guardiao.json` do
# cofre ou o lançador do servidor, com `padrao_erro` «.», via o fim do arquivo
# em `detalhe_tecnico` — que o gerente lê. Agora:
#   - só arquivo DENTRO da pasta de dados do servidor ou da raiz das cópias
#     (a de fábrica — a `backup_dir` da tela não conta, porque ela também se
#     edita pela tela), e nunca dentro da pasta do cofre;
#   - o estado do backup tem de se chamar `ESTADO_DO_BACKUP.json`, e o log
#     tem de ser .log ou .txt;
#   - o texto do log NÃO vai mais para a tela: vai só quantas linhas bateram.
NOME_DO_ESTADO_DO_BACKUP = "ESTADO_DO_BACKUP.json"
SUFIXOS_DE_LOG = (".log", ".txt")


def _raizes_de_leitura(ctx: Contexto) -> list[Path]:
    from pasta_das_copias import raiz_das_copias
    raizes = [Path(ctx.pasta_dados)]
    try:
        raizes.append(raiz_das_copias(Path(ctx.pasta_dados)))
    except Exception:                          # noqa: BLE001 — sem a raiz das cópias, vale só a de dados
        pass
    return [r.resolve() for r in raizes]


def arquivo_de_leitura_permitido(ctx: Contexto, caminho: str, *, sufixos: tuple[str, ...] = (),
                                 nome: str | None = None) -> Path:
    """O caminho configurado, se ele mora nas pastas da casa. Senão, `ValueError` com a frase."""
    import automacao_cofre as COFRE
    alvo = Path(str(caminho or "").strip()).expanduser().resolve()
    dentro = False
    for raiz in _raizes_de_leitura(ctx):
        try:
            alvo.relative_to(raiz)
            dentro = True
            break
        except ValueError:
            continue
    if not dentro:
        raise ValueError("o arquivo configurado está fora da pasta de dados do servidor e da pasta "
                         "das cópias — a verificação só lê arquivo de lá")
    if COFRE.NOME_DA_PASTA in [p.lower() for p in alvo.parts]:
        raise ValueError("a pasta do cofre não se lê por esta verificação")
    if nome and alvo.name.lower() != nome.lower():
        raise ValueError(f"o arquivo tem de se chamar {nome}")
    if sufixos and alvo.suffix.lower() not in sufixos:
        raise ValueError("o arquivo tem de ser " + " ou ".join(sufixos))
    return alvo


def verificar_backup(ctx: Contexto) -> dict:
    """O backup da noite terminou bem? Lê o `ESTADO_DO_BACKUP.json` configurado."""
    caminho = ctx.config(SCH.CHAVE_BACKUP_ESTADO).strip()
    if not caminho:
        return resultado(SCH.AVISO, "O caminho do estado do backup não está configurado — informe "
                         "em Automação → Configuração.", erro="caminho não configurado")
    try:
        alvo = arquivo_de_leitura_permitido(ctx, caminho, nome=NOME_DO_ESTADO_DO_BACKUP)
    except ValueError as recusa:
        return resultado(SCH.AVISO, f"O caminho do estado do backup não vale: {recusa}. Corrija em "
                         "Automação → Configuração.", erro="caminho fora das pastas permitidas")
    if not alvo.is_file():
        return _nao_mediu("o backup", f"o arquivo de estado não existe ({alvo.name})")
    try:
        estado = json.loads(alvo.read_text(encoding="utf-8"))
    except (OSError, ValueError) as erro:
        return _nao_mediu("o backup", erro)
    horas = int(ctx.parametros.get("horas", 26))
    terminou = estado.get("terminou") or estado.get("quando")
    try:
        idade = (ctx.agora - datetime.fromisoformat(str(terminou)[:19])).total_seconds() / 3600
    except ValueError:
        return _nao_mediu("o backup", "o arquivo de estado não diz quando terminou")
    achados = [{"terminou": terminou, "horas": round(idade, 1), "ok": estado.get("ok"),
                "ok_local": estado.get("ok_local"), "ok_fora": estado.get("ok_fora"),
                "avisos": estado.get("avisos") or []}]
    if idade > horas:
        return resultado(SCH.ERRO, f"O último backup terminou há {idade:.0f} h (o limite é {horas} h).", achados)
    if estado.get("erro"):
        return resultado(SCH.ERRO, f"O backup da noite FALHOU: {estado['erro']}"[:600], achados)
    if not estado.get("ok"):
        if estado.get("ok_local"):
            return resultado(SCH.AVISO, "O backup local está OK, mas a cópia fora da casa ficou pendente.", achados)
        return resultado(SCH.ERRO, "O backup da noite não terminou bem.", achados)
    if estado.get("avisos"):
        return resultado(SCH.AVISO, "Backup OK, com aviso(s): " + "; ".join(map(str, estado["avisos"]))[:500], achados)
    return resultado(SCH.OK, f"Backup OK (terminou há {idade:.0f} h, local e fora).", achados)


def verificar_log(ctx: Contexto) -> dict:
    """Uma rotina de fora do pacote, julgada pelo log que ela deixa.

    Parâmetros: `chave_config` (a configuração que guarda o caminho), `horas`,
    `padrao_ok` e `padrao_erro` (expressões procuradas nas últimas linhas).
    """
    p = ctx.parametros
    chave = p.get("chave_config") or SCH.CHAVE_CNIB_LOG
    caminho = ctx.config(chave).strip()
    nome = p.get("nome", "a rotina")
    if not caminho:
        return resultado(SCH.AVISO, f"O caminho do log de {nome} não está configurado — informe "
                         "em Automação → Configuração.", erro="caminho não configurado")
    try:
        alvo = arquivo_de_leitura_permitido(ctx, caminho, sufixos=SUFIXOS_DE_LOG)
    except ValueError as recusa:
        return resultado(SCH.AVISO, f"O caminho do log de {nome} não vale: {recusa}. Corrija em "
                         "Automação → Configuração.", erro="caminho fora das pastas permitidas")
    if not alvo.is_file():
        return _nao_mediu(nome, f"o log não existe ({alvo.name})")
    horas = int(p.get("horas", 26))
    idade = (ctx.agora.timestamp() - alvo.stat().st_mtime) / 3600
    with alvo.open("rb") as f:
        f.seek(max(0, alvo.stat().st_size - 64 * 1024))
        fim = f.read().decode("utf-8", "replace").splitlines()[-int(p.get("linhas", 40)):]
    texto = "\n".join(fim)
    achados = [{"horas_desde_a_ultima_escrita": round(idade, 1)}]
    if idade > horas:
        return resultado(SCH.ERRO, f"O log de {nome} não é escrito há {idade:.0f} h (limite {horas} h): "
                         "a rotina não está rodando.", achados)
    # Só a CONTAGEM vai para a tela (26/10/2026, M3): o texto do arquivo não sai daqui.
    if p.get("padrao_erro") and re.search(p["padrao_erro"], texto):
        bateram = sum(1 for linha in fim if re.search(p["padrao_erro"], linha))
        return resultado(SCH.ERRO, f"A última rodada de {nome} registrou erro no log.", achados,
                         detalhe_tecnico=f"{bateram} linha(s) das últimas {len(fim)} do log bateram com o "
                                         f"padrão de erro. Abra o log na máquina do servidor para ler.")
    if p.get("padrao_ok") and not re.search(p["padrao_ok"], texto):
        return resultado(SCH.AVISO, f"A última rodada de {nome} não registrou o fim esperado.", achados,
                         detalhe_tecnico=f"Nenhuma das últimas {len(fim)} linhas do log bateu com o padrão "
                                         f"de fim. Abra o log na máquina do servidor para ler.")
    return resultado(SCH.OK, f"{nome[:1].upper() + nome[1:]}: rodou há {idade:.0f} h e terminou bem.", achados)


def verificar_disco(ctx: Contexto) -> dict:
    """Espaço livre: menos de 20 GB pede atenção, menos de 5 GB é crítico."""
    p = ctx.parametros
    alvo = Path(p.get("caminho") or ctx.pasta_dados)
    try:
        livre = shutil.disk_usage(alvo).free / 1024 ** 3
    except OSError as erro:
        return _nao_mediu("o espaço do disco", erro)
    aviso, critico = float(p.get("aviso_gb", 20)), float(p.get("critico_gb", 5))
    achados = [{"livre_gb": round(livre, 1), "aviso_gb": aviso, "critico_gb": critico}]
    if livre < critico:
        return resultado(SCH.ERRO, f"Disco com {livre:.1f} GB livres — CRÍTICO (menos de {critico:.0f} GB). "
                         "O backup e o banco podem parar.", achados)
    if livre < aviso:
        return resultado(SCH.AVISO, f"Disco com {livre:.1f} GB livres (menos de {aviso:.0f} GB).", achados)
    return resultado(SCH.OK, f"Disco com {livre:.1f} GB livres.", achados)


def verificar_selador(ctx: Contexto) -> dict:
    """O selador responde, e é a mesma máquina conferida? Não pede token, não sela."""
    import selador_cliente as SCL
    import selador_config as SC
    with ctx.db.connect() as con:
        estado = SC.situacao(con, ctx.pasta_dados)
        fixado = SCL.certificado_fixado(con)
    if estado.get("faltas"):
        return resultado(SCH.AVISO, "O selador não está configurado: " + " ".join(estado["faltas"]),
                         erro="selador não configurado")
    try:
        visto = SCL.espiar_certificado(estado["base_em_uso"], int(ctx.parametros.get("prazo", 20)))
    except SCL.SeladorIndisponivel as erro:
        return resultado(SCH.ERRO, f"O selador não respondeu: {erro}"[:600], erro=str(erro)[:500])
    if not fixado:
        return resultado(SCH.AVISO, "O selador respondeu, mas o certificado dele ainda não foi "
                         "conferido e fixado (Administrativo → Selador).")
    if fixado != visto.sha256:
        return resultado(SCH.ERRO, "O certificado do selador MUDOU desde a conferência — o sistema "
                         "não sela até alguém conferir de novo.", erro="certificado mudou")
    return resultado(SCH.OK, "O selador respondeu, com o certificado conferido.")


def verificar_validade_do_cofre(ctx: Contexto) -> dict:
    """As credenciais do cofre com validade: avisa `dias_antes` (90) dias antes de vencer.

    Lê só os metadados — funciona com o cofre trancado. O certificado do banco
    vale um ano; o aviso de 90 dias dá tempo de pedir o novo.
    """
    import automacao_cofre as COFRE
    dias_antes = int(ctx.parametros.get("dias_antes", 90))
    itens = [i for i in COFRE.listar(caminho=COFRE.caminho_do_cofre(ctx.pasta_dados)) if i.get("validade")]
    vencidas = [i for i in itens if i["dias_para_vencer"] is not None and i["dias_para_vencer"] < 0]
    perto = [i for i in itens if i["dias_para_vencer"] is not None and 0 <= i["dias_para_vencer"] <= dias_antes]
    achados = [{"nome": i["nome"], "validade": i["validade"], "dias": i["dias_para_vencer"]} for i in vencidas + perto]
    if vencidas:
        return resultado(SCH.ERRO, "Cofre: " + ", ".join(f"«{i['nome']}» venceu em {i['validade']}" for i in vencidas)
                         + ". Troque a credencial em Automação → Cofre.", achados)
    if perto:
        return resultado(SCH.AVISO, "Cofre: " + ", ".join(f"«{i['nome']}» vence em {i['dias_para_vencer']} dias "
                                                          f"({i['validade']})" for i in perto)
                         + ". Peça a nova antes do vencimento.", achados)
    return resultado(SCH.OK, f"Cofre: nenhuma credencial vence nos próximos {dias_antes} dias "
                     f"({len(itens)} com validade cadastrada).", achados)


# ------------------------------------------------------------------ as rotinas que já existiam


def rodar_conferencia_diaria(ctx: Contexto) -> dict:
    """A conferência diária do gestor (`gestor_rotina.rodada_diaria`), pelo despachante."""
    import gestor_rotina
    linhas: list[str] = []
    pasta_rel = ctx.parametros.get("pasta_relatorio")
    codigo = gestor_rotina.rodada_diaria(
        Path(ctx.db.db_path), ctx.pasta_dados,
        (ctx.pasta_dados / pasta_rel) if pasta_rel else None,
        hoje=ctx.hoje, escrever=lambda t: linhas.append(str(t)))
    fim = "\n".join(linhas)[-3000:]
    if codigo != 0:
        return resultado(SCH.ERRO, f"A conferência diária terminou com o código {codigo}.",
                         erro=(linhas[-1] if linhas else "sem saída")[:500], detalhe_tecnico=fim)
    return resultado(SCH.OK, "A conferência diária rodou: " + " · ".join(l.strip() for l in linhas[-4:])[:800],
                     acoes=[{"acao": "rodou a conferência diária do gestor"}], detalhe_tecnico=fim)


def rodar_compliance(ctx: Contexto) -> dict:
    """A rodada do compliance (`compliance.rodar`), pelo despachante."""
    import compliance as CP
    try:
        versao = (ctx.raiz / "VERSAO.txt").read_text(encoding="utf-8").strip()
    except OSError:
        versao = None
    pasta_rel = ctx.parametros.get("pasta_relatorio")
    with ctx.db.connect() as con:
        resumo = CP.rodar(con, CP.Contexto(con=con, agora=ctx.agora, pasta_dados=ctx.pasta_dados,
                                           versao_instalada=versao),
                          (ctx.pasta_dados / pasta_rel) if pasta_rel else None)
    achado = {k: resumo.get(k) for k in ("achados", "novos", "resolvidos", "criticos", "nao_mediu", "tarefa")}
    acoes = [{"acao": "rodou o compliance", "tarefa": resumo.get("tarefa")}]
    if resumo.get("criticos") or resumo.get("nao_mediu"):
        return resultado(SCH.AVISO, f"Compliance: {resumo.get('criticos')} crítico(s) e "
                         f"{resumo.get('nao_mediu')} regra(s) sem medir.", [achado], acoes)
    return resultado(SCH.OK, f"Compliance sem ponto crítico ({resumo.get('achados')} achado(s)).", [achado], acoes)


def rodar_censec_envio(ctx: Contexto) -> dict:
    """O envio automático à CENSEC (`censec_automatico.enviar`) — ESTE ENVIA."""
    import censec_automatico as AUTO
    from serventia import dados as dados_da_serventia
    cns = ctx.setting("ri_cns", "") or dados_da_serventia(ctx.db.get_settings)["ri_cns"]
    resultados = AUTO.enviar(ctx.db, ctx.hoje, cns=cns)
    falhas = [r for r in resultados if r.get("situacao") in ("FALHOU", "RECUSADA")]
    enviados = [r for r in resultados if r.get("situacao") not in ("FALHOU", "RECUSADA", "NADA_A_ENVIAR",
                                                                  AUTO.DESLIGADO)]
    resumo = [{k: r.get(k) for k in ("ano", "mes", "quinzena", "situacao", "motivo")} for r in resultados]
    acoes = [{"acao": "enviou à CENSEC", **{k: r.get(k) for k in ("ano", "mes", "quinzena", "situacao")}}
             for r in enviados]
    if any(r.get("situacao") == AUTO.DESLIGADO for r in resultados):
        return resultado(SCH.AVISO, "O envio automático à CENSEC está desligado nas configurações.", resumo)
    if falhas:
        return resultado(SCH.ERRO, f"CENSEC: {len(falhas)} quinzena(s) falharam no envio.", resumo, acoes)
    return resultado(SCH.OK, f"CENSEC: {len(enviados)} quinzena(s) enviada(s), nenhuma falha.", resumo, acoes)


# ------------------------------------------------------------------ o agente de IA


def rodar_agente(ctx: Contexto) -> dict:
    """O processo do tipo AGENTE_IA: o pedido vai ao agente do sistema.

    `pode_agir` desligado → o agente roda SÓ LENDO (as ferramentas de escrita
    nem são oferecidas) e propõe; ligado → ele escreve sem esperar o clique, e
    tudo o que mudou vem para o relatório. **Nenhum segredo do cofre vai ao
    modelo**: processo de IA não pode ter credencial (`automacao.salvar`).
    """
    import agente as AGT
    import agente_schema as AGS
    pedido = str(ctx.processo.get("alvo") or "").strip()
    if not pedido:
        return resultado(SCH.ERRO, "O processo de IA não tem pedido escrito.")
    try:
        with AGS.escrita_do_processo(ligada=ctx.pode_agir, sem_confirmacao=ctx.pode_agir):
            retrato = AGT.pedir(ctx.db, pedido=pedido, pasta_de_dados=ctx.pasta_dados, raiz=ctx.raiz,
                                agora=lambda: datetime.now().isoformat(timespec="seconds"),
                                usuario="automacao", onde=f"automação: {ctx.processo.get('codigo')}")
    except AGT.AgenteRecusado as erro:
        return resultado(SCH.AVISO, f"O agente não rodou: {erro}"[:600], erro=str(erro)[:500])
    sessao = retrato.get("sessao") or {}
    textos = [p for p in retrato.get("passos") or [] if p.get("tipo") == AGS.TEXTO]
    relato = (textos[-1].get("conteudo") if textos else "") or "(o agente não escreveu conclusão)"
    acoes = [{"acao": "mudança do agente", "ferramenta": m.get("ferramenta"), "alvo": m.get("alvo"),
              "situacao": m.get("situacao"), "reversivel": bool(m.get("reversivel"))}
             for m in retrato.get("mudancas") or []]
    achados = [{"sessao_do_agente": sessao.get("id"), "estado": sessao.get("estado"),
                "pode_agir": ctx.pode_agir, "turnos": sessao.get("turnos")}]
    estado = sessao.get("estado")
    situacao = {AGS.CONCLUIDA: SCH.OK, AGS.LIMITE: SCH.AVISO}.get(estado, SCH.ERRO)
    return resultado(situacao, relato[:3500], achados, acoes,
                     erro=(sessao.get("erro") or None) if situacao == SCH.ERRO else None)


# ------------------------------------------------------------------ o catálogo

#: As verificações que a tela oferece. O nome é o que vai em `alvo`.
CATALOGO: dict[str, Any] = {
    "automacao_processos:verificar_cra": verificar_cra,
    "automacao_processos:verificar_cenprot": verificar_cenprot,
    "automacao_processos:verificar_onr_fila": verificar_onr_fila,
    "automacao_processos:verificar_wsoficio": verificar_wsoficio,
    "automacao_processos:verificar_cnib": verificar_cnib,
    "automacao_processos:verificar_sirc": verificar_sirc,
    "automacao_processos:verificar_crc": verificar_crc,
    "automacao_processos:verificar_malote": verificar_malote,
    "automacao_processos:verificar_censec": verificar_censec,
    "automacao_processos:verificar_backup": verificar_backup,
    "automacao_processos:verificar_log": verificar_log,
    "automacao_processos:verificar_disco": verificar_disco,
    "automacao_processos:verificar_selador": verificar_selador,
    "automacao_processos:verificar_validade_do_cofre": verificar_validade_do_cofre,
    "automacao_processos:rodar_conferencia_diaria": rodar_conferencia_diaria,
    "automacao_processos:rodar_compliance": rodar_compliance,
    "automacao_processos:rodar_censec_envio": rodar_censec_envio,
}

_UTEIS = [0, 1, 2, 3, 4]
_TODOS = [0, 1, 2, 3, 4, 5, 6]

#: OS PROCESSOS DE FÁBRICA — todos nascem DESLIGADOS, e quem liga é o oficial.
#: As rotinas que já têm tarefa própria no Agendador (gestor, compliance,
#: CENSEC) entram aqui para poderem ser movidas depois; ligar as duas ao mesmo
#: tempo faria a rotina rodar duas vezes.
SEMENTES: tuple[dict, ...] = (
    {"codigo": "PROTESTO_CRA", "nome": "CRA — a remessa do dia foi baixada?", "setor": "PROTESTO",
     "alvo": "automacao_processos:verificar_cra", "robo_oficial": "PROTESTO", "timeout_s": 120,
     "agenda": {"dias": _UTEIS, "horarios": ["11:30", "14:10"]},
     "descricao": "Às 11:30 e 14:10 (os prazos da CRA): confere a ligação com a CRA e se a remessa "
                  "de hoje foi baixada no sistema. Não baixa nada sozinho."},
    {"codigo": "PROTESTO_CENPROT", "nome": "CENPROT — pedidos de protesto pendentes", "setor": "PROTESTO",
     "alvo": "automacao_processos:verificar_cenprot", "robo_oficial": "PROTESTO", "timeout_s": 180,
     "agenda": {"dias": _UTEIS, "intervalo_min": 60, "janela": ["08:00", "17:00"]},
     "descricao": "De hora em hora: pedidos que chegaram na CENPROT e ainda não foram baixados, e os "
                  "que esperam resposta. Com «pode agir», baixa os de hoje para o sistema."},
    {"codigo": "RI_ONR_FILA", "nome": "ONR — fila dos envios", "setor": "RI",
     "alvo": "automacao_processos:verificar_onr_fila", "robo_oficial": "CARGAS_RI", "timeout_s": 180,
     "agenda": {"dias": _UTEIS, "horarios": ["09:00", "15:00"]},
     "descricao": "Envios ao ONR recusados ou sem resposta. Com «pode agir», confere a fila e atualiza "
                  "a situação dos envios."},
    {"codigo": "RI_WSOFICIO", "nome": "WSOfício — ofícios e penhoras", "setor": "RI",
     "alvo": "automacao_processos:verificar_wsoficio", "robo_oficial": "RI", "timeout_s": 300,
     "parametros": {"dias": 7}, "agenda": {"dias": _UTEIS, "horarios": ["08:30", "13:30"]},
     "descricao": "Entra no Ofício Eletrônico e conta os ofícios e penhoras dos últimos dias; avisa "
                  "quando chegou coisa nova. Usa o certificado configurado no WSOfício."},
    {"codigo": "RI_CNIB", "nome": "CNIB — ordens sem decisão", "setor": "RI",
     "alvo": "automacao_processos:verificar_cnib", "robo_oficial": "RI", "timeout_s": 900,
     "agenda": {"dias": _UTEIS, "horarios": ["07:45"]},
     "descricao": "Matrículas com parte que bate com ordem ativa de indisponibilidade e ainda sem "
                  "decisão do cartório."},
    {"codigo": "RI_CNIB_MINUTAS", "nome": "CNIB — minutas diárias (rotina de fora)", "setor": "RI",
     "alvo": "automacao_processos:verificar_log", "robo_oficial": None, "timeout_s": 60,
     "parametros": {"chave_config": SCH.CHAVE_CNIB_LOG, "nome": "as minutas do CNIB", "horas": 26,
                    "padrao_ok": r"FEITO:", "padrao_erro": r"Traceback|ERRO:"},
     "agenda": {"dias": _UTEIS, "horarios": ["09:15"]},
     "descricao": "Lê o log da rotina de minutas do CNIB (que roda no Agendador, fora do pacote) e "
                  "diz se ela rodou e terminou bem."},
    {"codigo": "RCPN_SIRC", "nome": "SIRC — comunicações pendentes (1 dia útil)", "setor": "RCPN",
     "alvo": "automacao_processos:verificar_sirc", "robo_oficial": "CARGAS_RCPN", "timeout_s": 300,
     "agenda": {"dias": _UTEIS, "horarios": ["08:00", "16:00"]},
     "descricao": "O que o SIRC ainda não recebeu, medido pelo sistema; prazo de 1 dia útil."},
    {"codigo": "RCPN_CRC", "nome": "CRC — carga dos assentos recentes", "setor": "RCPN",
     "alvo": "automacao_processos:verificar_crc", "robo_oficial": "CARGAS_RCPN", "timeout_s": 300,
     "parametros": {"dias": 10}, "agenda": {"dias": _UTEIS, "horarios": ["08:10"]},
     "descricao": "Assentos lavrados nos últimos dias que ainda não foram à carga da CRC."},
    {"codigo": "CASA_MALOTE", "nome": "Malote Digital responde?", "setor": "GESTAO",
     "alvo": "automacao_processos:verificar_malote", "timeout_s": 60,
     "agenda": {"dias": _UTEIS, "intervalo_min": 120, "janela": ["08:00", "18:00"]},
     "descricao": "Sonda a porta do Malote Digital, sem login nem senha."},
    {"codigo": "CASA_CENSEC", "nome": "CENSEC — situação do envio automático", "setor": "NOTAS",
     "alvo": "automacao_processos:verificar_censec", "robo_oficial": "NOTAS", "timeout_s": 300,
     "agenda": {"dias": _TODOS, "horarios": ["07:40"]},
     "descricao": "O envio automático da madrugada falhou? Há ato impedido ou quinzena vencendo?"},
    {"codigo": "CASA_BACKUP", "nome": "Backup da noite", "setor": "TI",
     "alvo": "automacao_processos:verificar_backup", "timeout_s": 60, "parametros": {"horas": 26},
     "agenda": {"dias": _TODOS, "horarios": ["07:15"]},
     "descricao": "Lê o ESTADO_DO_BACKUP.json (caminho em Configuração) e diz se o backup terminou bem e há quanto tempo."},
    {"codigo": "CASA_DISCO", "nome": "Espaço livre no disco", "setor": "TI",
     "alvo": "automacao_processos:verificar_disco", "timeout_s": 30,
     "parametros": {"aviso_gb": 20, "critico_gb": 5},
     "agenda": {"dias": _TODOS, "intervalo_min": 60},
     "descricao": "Menos de 20 GB livres pede atenção; menos de 5 GB é crítico."},
    {"codigo": "CASA_SELADOR", "nome": "Selador responde?", "setor": "TI",
     "alvo": "automacao_processos:verificar_selador", "timeout_s": 60,
     "agenda": {"dias": _UTEIS, "intervalo_min": 30, "janela": ["07:30", "18:00"]},
     "descricao": "O aparelho do selo responde e é a mesma máquina conferida. Não pede selo nem token."},
    {"codigo": "COFRE_VALIDADE", "nome": "Cofre — validade das credenciais", "setor": "TI",
     "alvo": "automacao_processos:verificar_validade_do_cofre", "timeout_s": 30,
     "parametros": {"dias_antes": 90}, "agenda": {"dias": _TODOS, "horarios": ["07:20"]},
     "descricao": "Avisa 90 dias antes de vencer o certificado ou a chave guardada no cofre (o "
                  "certificado do banco vale um ano). Lê só os metadados: roda com o cofre trancado."},
    {"codigo": "ROTINA_CONFERENCIA_DIARIA", "nome": "Conferência diária do gestor (rotina)", "setor": "GESTAO",
     "alvo": "automacao_processos:rodar_conferencia_diaria", "timeout_s": 1800,
     "agenda": {"dias": _TODOS, "horarios": ["07:30", "14:00", "14:30"]},
     "descricao": "A mesma rodada da tarefa «Conferência diária» do Agendador. NÃO ligue aqui enquanto "
                  "a tarefa do Agendador estiver ligada — rodaria duas vezes."},
    {"codigo": "ROTINA_COMPLIANCE", "nome": "Compliance (rotina)", "setor": "GESTAO",
     "alvo": "automacao_processos:rodar_compliance", "robo_oficial": "COMPLIANCE", "timeout_s": 1800,
     "agenda": {"dias": _TODOS, "horarios": ["08:00", "15:00"]},
     "descricao": "A mesma rodada da tarefa do compliance no Agendador. NÃO ligue aqui enquanto a "
                  "tarefa do Agendador estiver ligada."},
    {"codigo": "ROTINA_CENSEC_ENVIO", "nome": "Envio automático à CENSEC (rotina)", "setor": "NOTAS",
     "alvo": "automacao_processos:rodar_censec_envio", "timeout_s": 1800,
     "agenda": {"dias": _TODOS, "horarios": ["02:00"]},
     "descricao": "ESTE ENVIA à CENSEC — o mesmo envio da tarefa «CENSEC-Envio» do Agendador. NÃO ligue "
                  "aqui enquanto a tarefa do Agendador estiver ligada."},
)


# -------------------------------------------- processos que outros módulos trazem

#: Módulos que trazem processos próprios para a central: cada um expõe
#: `CATALOGO`, uma lista de {codigo, nome, setor, funcao («modulo.funcao»),
#: e opcionalmente descricao, agenda, timeout_s e parametros}. O primeiro é o das despesas
#: e do Banco Inter (agente financeiro, 24/10/2026). O import é protegido:
#: o PR de um pode entrar antes do outro, e módulo ausente só não semeia.
#: O terceiro é o dos avisos de andamento ao cliente (26/10/2026), que traz
#: também os `parametros` de fábrica (os dias antes do vencimento). O quarto,
#: o do backup (26/10/2026): o pacote no horário e o teste de restauração
#: (`backup_automacao`) — que não substituem o `CASA_BACKUP` daqui, o leitor do
#: estado de uma rotina de backup que roda FORA do pacote.
#: Os dois últimos (27/10/2026, na instalação da VPS): o envio do portal do
#: cliente e a busca na caixa-postal do WhatsApp, que só aconteciam no botão.
#: E o robô do malote (29/10/2026): a ciência diária das 8h, com a senha do cofre.
MODULOS_COM_PROCESSOS = ("despesas_automacao", "onr_certidoes_auto", "andamento_avisos",
                         "backup_automacao", "satisfacao_envio", "cobranca_automacao",
                         "portal_cliente", "wa_puxar", "malote_robo")

#: A agenda sugerida por quem escreveu o processo, para quando o catálogo
#: dele não trouxer uma. O processo nasce DESLIGADO do mesmo jeito.
AGENDA_SUGERIDA = {
    "DESPESAS_PAGAR": {"dias": _UTEIS, "intervalo_min": 15, "janela": ["08:00", "17:00"]},
    "DESPESAS_CONCILIAR": {"dias": _UTEIS, "horarios": ["09:00", "16:00"]},
}


def _alvo_de(funcao: str) -> str:
    """«despesas_automacao.pagar» → «despesas_automacao:pagar», a forma do `alvo`."""
    funcao = str(funcao or "").strip()
    if ":" in funcao:
        return funcao
    modulo, _, nome = funcao.rpartition(".")
    return f"{modulo}:{nome}" if modulo else funcao


def sementes_de_outros_modulos() -> list[dict]:
    """As sementes que os módulos de `MODULOS_COM_PROCESSOS` declaram, se instalados."""
    import importlib
    saida: list[dict] = []
    for nome_modulo in MODULOS_COM_PROCESSOS:
        try:
            modulo = importlib.import_module(nome_modulo)
        except ImportError:
            continue
        for item in getattr(modulo, "CATALOGO", None) or ():
            codigo = str(item.get("codigo") or "").strip()
            alvo = _alvo_de(item.get("funcao") or item.get("alvo") or "")
            if not codigo or ":" not in alvo:
                continue
            saida.append({
                "codigo": codigo,
                "nome": item.get("nome") or codigo,
                "setor": item.get("setor") or "GESTAO",
                "alvo": alvo,
                "descricao": item.get("descricao") or f"Processo trazido por «{nome_modulo}».",
                "agenda": item.get("agenda") or AGENDA_SUGERIDA.get(codigo)
                          or {"dias": _UTEIS, "horarios": ["09:00"]},
                "timeout_s": int(item.get("timeout_s") or 600),
                # Os parâmetros de fábrica que o módulo declarar (26/10/2026, o
                # limite de idade do teste de restauração). Sem eles a semente
                # nascia com `{}` e o processo dependia só do padrão do código.
                "parametros": dict(item.get("parametros") or {}),
            })
    return saida


def todas_as_sementes() -> list[dict]:
    """As de fábrica mais as dos outros módulos, sem repetir código."""
    vistas = {s["codigo"] for s in SEMENTES}
    return list(SEMENTES) + [s for s in sementes_de_outros_modulos() if s["codigo"] not in vistas]
