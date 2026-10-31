"""A FILA DE CORREÇÕES DE OFÍCIO — quem propõe, quem aprova, quem executa.

DECISÃO DO OFICIAL, 29/10/2026:

    - a leitura do banco fica livre para os robôs e os agentes;
    - a escrita é feita apenas pelo sistema, com usuário;
    - as correções de ofício — as que até aqui se faziam por script direto no
      banco — passam a ir por uma fila no sistema: o agente ou a escrevente
      PROPÕE; o oficial APROVA, com afirmação expressa; o SERVIDOR executa.

O QUE SE FAZIA POR SCRIPT NA SEMANA DE 29/10/2026 (lido nos scripts, que não
foram rodados para escrever isto):

    - as duas parcelas do mesmo protocolo, com o pagamento lançado na errada:
      tornar sem efeito o protesto e a intimação de uma e o pagamento da outra
      (`pt_atos.cancelado = 1` com `motivo_cancelamento`), lançar um PAGAMENTO
      de correção na certa copiando o `detalhe_json` do original
      (`origem = 'CORRECAO'`, com a data do original), e trocar a situação das
      duas;
    - o título que ficou PAGO com o pagamento desfeito pelo selo voltar à
      situação que os atos válidos sustentam (PAGO → APONTADO);
    - o cedente dos títulos da carga do acervo corrigido em lote, só onde o
      valor de hoje era o que a carga errada gravou;
    - o apresentante de dois títulos TAB, pela função da tela.

    A troca de uma chave de configuração (o fim do expediente do caixa) NÃO
    entra aqui: é configuração de cobrança, e tem caminho próprio.

O CATÁLOGO É FECHADO, E NÃO HÁ SQL LIVRE. Cada tipo é uma classe com as
suas partes, e o SQL de cada uma está escrito nela — nome de tabela e de
coluna só sai de constante deste arquivo, nunca do que o formulário mandou:

    PREPARAR (só lê) — normaliza o pedido, lê o «antes», confere a
        pré-condição e calcula o «depois». A recusa diz tudo o que falta de
        uma vez: quem pede tem de ler tudo antes de pedir de novo.
    EXECUTAR (escreve, no servidor, na transação da aprovação) — só o
        «depois» que foi mostrado, e só se o «antes» ainda é o que está no
        banco: cada UPDATE leva o valor de antes no WHERE.
    CONFERIR (só lê, na mesma transação) — relê o banco e confere que ficou
        como o «depois» dizia. Se não ficou, nada fica gravado (SAVEPOINT) e
        a proposta fica FALHOU, com o motivo.

QUEM FAZ O QUÊ:

    PROPOR — ADMIN, MANAGER e USER, e a conta de robô (papel USER): propor é
        PREPARAR, e não altera nada além da própria fila. A proposta grava o
        «antes» lido do banco naquele momento e vira tarefa para o oficial,
        sem e-mail.
    APROVAR — só ADMIN, e só gente: conta de robô nunca aprova, com o papel
        que tiver. Com a afirmação expressa no contrato comum (`afirmo`
        marcado e pelo menos 30 letras — `protesto_selo_previo.
        validar_afirmacao`, o mesmo da correção de ofício da situação). A
        execução confere de novo o «antes»: se mudou, nada se executa e a
        proposta fica FALHOU, dizendo o que mudou.
    RECUSAR — só ADMIN, com o motivo; a proposta fica no histórico.

A AUDITORIA vai junto com a execução, na MESMA transação
(`identidade_do_robo.registrar`): uma linha `CORRECAO_DE_OFICIO_EXECUTADA`
por linha tocada, com o antes e o depois dela, e a `AFIRMACAO_EXPRESSA` do
oficial (regra `CORRECAO_DE_OFICIO`). Correção executada sem a auditoria dela
seria o script direto no banco outra vez.

O CATÁLOGO COMEÇA PELO PROTESTO e é extensível: um tipo novo é uma subclasse
de `Tipo`, com a atribuição dele, registrada em `CATALOGO`. A fila, as telas,
a tarefa, a auditoria e a conferência do «antes» não mudam.
"""
from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

import identidade_do_robo as IDR
from bd_nativo import ERROS_DO_BANCO, banco

# ------------------------------------------------------------- as situações

PROPOSTA = "PROPOSTA"
APROVADA_EXECUTADA = "APROVADA_EXECUTADA"
RECUSADA = "RECUSADA"
FALHOU = "FALHOU"
SITUACOES = (PROPOSTA, APROVADA_EXECUTADA, RECUSADA, FALHOU)
#: O nome de cada aba da tela.
ROTULO_DA_SITUACAO = {PROPOSTA: "Propostas", APROVADA_EXECUTADA: "Executadas",
                      RECUSADA: "Recusadas", FALHOU: "Falhas"}

# ------------------------------------------------------------- quem faz

#: Quem vê a fila e a ficha. O AUDITOR confere; não propõe nem decide.
QUEM_VE = ("ADMIN", "MANAGER", "USER", "AUDITOR")
#: Quem propõe — a escrevente e a conta de robô (papel USER). Propor é
#: PREPARAR: não muda nada fora da fila.
QUEM_PROPOE = ("ADMIN", "MANAGER", "USER")
#: Quem decide. Só o oficial — e só gente (`eh_robo` recusa, qualquer papel).
QUEM_APROVA = ("ADMIN",)

# ------------------------------------------------------------- os nomes

ACAO_PROPOSTA = "CORRECAO_DE_OFICIO_PROPOSTA"
ACAO_EXECUTADA = "CORRECAO_DE_OFICIO_EXECUTADA"
ACAO_RECUSADA = "CORRECAO_DE_OFICIO_RECUSADA"
ACAO_FALHOU = "CORRECAO_DE_OFICIO_FALHOU"
ACAO_ANEXO = "CORRECAO_DE_OFICIO_ANEXO"
#: O contrato comum da afirmação expressa: a ação e a regra desta trava.
ACAO_DA_AFIRMACAO = "AFIRMACAO_EXPRESSA"
REGRA_DA_AFIRMACAO = "CORRECAO_DE_OFICIO"

#: A tabela da fila, e o `entity_type` da auditoria da proposta.
ENTIDADE = "correcoes_de_oficio"
#: O `entity_type` dos anexos (a prova). A tela que o oferece é a ficha.
ENTIDADE_DO_ANEXO = "CORRECAO_DE_OFICIO"
#: A origem da tarefa do oficial (`tasks.source_type`).
ORIGEM_DA_TAREFA = "CORRECAO_DE_OFICIO"
#: A origem do ato lançado por correção — a do precedente de 29/10/2026.
ORIGEM_DO_ATO = "CORRECAO"

MINIMO_DE_LETRAS_DO_MOTIVO = 20
MINIMO_DE_LETRAS_DA_RECUSA = 10
#: O teto da lista de cada aba. Passou, a tela diz que cortou.
LIMITE_DA_LISTA = 500
#: O teto das pendências que o roteiro lê — o mesmo de `protesto_selo_previo`.
LIMITE_DAS_PENDENCIAS = 200
#: O teto das linhas «antes → depois» que a ficha desenha.
LIMITE_DAS_LINHAS = 300

ATRIBUICAO_PROTESTO = "PROTESTO"
NOME_DA_ATRIBUICAO = {ATRIBUICAO_PROTESTO: "Protesto"}


class _Falha(Exception):
    """A execução não fechou. A frase é desta casa, e não do banco."""

    def __init__(self, frase: str):
        super().__init__(frase)
        self.frase = frase


# ================================================================ o esquema
#
# Um comando por objeto, cada um só se o objeto falta (o padrão de
# `ouvidoria`). Sem chave estrangeira: o alvo mora em tabela de outra
# atribuição (o nome dela vai como TEXTO em `alvo_tabela`), e quem propôs ou
# decidiu é vínculo informativo — apagar um usuário não leva a proposta.
SCHEMA: tuple[tuple[str, str], ...] = (
    (ENTIDADE, """
        CREATE TABLE IF NOT EXISTS correcoes_de_oficio (
            id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            atribuicao TEXT NOT NULL,
            tipo TEXT NOT NULL,
            alvo_tabela TEXT NOT NULL,
            alvo_ids TEXT NOT NULL DEFAULT '[]',
            titulo_ids TEXT NOT NULL DEFAULT '[]',
            parametros_json TEXT NOT NULL DEFAULT '{}',
            antes_json TEXT NOT NULL,
            depois_json TEXT NOT NULL,
            avisos_json TEXT NOT NULL DEFAULT '[]',
            resumo TEXT NOT NULL DEFAULT '',
            motivo TEXT NOT NULL,
            situacao TEXT NOT NULL DEFAULT 'PROPOSTA' CHECK (situacao IN (
                'PROPOSTA', 'APROVADA_EXECUTADA', 'RECUSADA', 'FALHOU')),
            proposta_em TEXT NOT NULL,
            proposta_por_id bigint,
            proposta_por TEXT,
            agente TEXT,
            a_mando_de TEXT,
            decidida_em TEXT,
            decidida_por_id bigint,
            decidida_por TEXT,
            afirmacao TEXT,
            motivo_da_recusa TEXT,
            resultado_json TEXT,
            falha TEXT,
            tarefa_id bigint
        )"""),
    ("ix_correcoes_de_oficio_situacao",
     ("CREATE INDEX IF NOT EXISTS ix_correcoes_de_oficio_situacao "
      "ON correcoes_de_oficio (situacao, id)")),
)


def init_correcoes_de_oficio_schema(con) -> None:
    """Cria a tabela e o índice que faltarem. Idempotente."""
    bd = banco(con)
    for nome, comando in SCHEMA:
        if not bd.tem_tabela(nome):
            bd.escrever(comando)


# ============================================================ auxiliares

def _letras(texto: Any) -> int:
    return sum(1 for c in str(texto or "") if c.isalpha())


def _corrido(texto: Any) -> str:
    return " ".join(str(texto or "").split())


def _txt(valor: Any) -> str | None:
    """O valor do banco como a comparação o vê: sem espaço nas pontas, e o
    vazio igual a nulo (a forma de `corrigir_cedentes_acervo`)."""
    if valor is None:
        return None
    s = str(valor).strip()
    return s or None


def _json(valor: Any) -> str:
    return json.dumps(valor, ensure_ascii=False, sort_keys=True, default=str)


def _ler_json(texto: Any, padrao: Any) -> Any:
    try:
        lido = json.loads(texto or "")
    except (TypeError, ValueError):
        return padrao
    return lido if isinstance(lido, type(padrao)) else padrao


def _sim(valor: Any, padrao: bool) -> bool:
    if valor is None:
        return padrao
    if isinstance(valor, bool):
        return valor
    return str(valor).strip().lower() in ("1", "on", "true", "sim", "s", "yes")


def _ids(valor: Any) -> tuple[list[int], list[str]]:
    """Os números pedidos, na ordem e sem repetir, e o que não é número.

    Aceita lista (do JSON) ou texto separado por vírgula, ponto e vírgula ou
    espaço (do formulário). «4120a» não vira 4120: vai para os ruins.
    """
    if valor is None:
        return [], []
    if isinstance(valor, (list, tuple)):
        pedacos = [str(x).strip() for x in valor]
    else:
        pedacos = re.split(r"[,;\s]+", str(valor))
    ids: list[int] = []
    ruins: list[str] = []
    for p in pedacos:
        if not p:
            continue
        if p.isdigit() and int(p) > 0:
            if int(p) not in ids:
                ids.append(int(p))
        else:
            ruins.append(p[:20])
    return ids, ruins


def _data_br(texto: Any) -> str:
    bruto = str(texto or "")[:10]
    if len(bruto) == 10 and bruto[4] == "-" and bruto[7] == "-":
        return f"{bruto[8:10]}/{bruto[5:7]}/{bruto[0:4]}"
    return bruto or "—"


def _numero(numero: int | None) -> str:
    return f"nº {numero}" if numero else "nº (o desta proposta)"


def _diferencas(guardado: Any, agora: Any, caminho: str = "") -> list[str]:
    """O que mudou entre o «antes» guardado e o lido agora. Só calcula.

    A frase diz ONDE e DE QUÊ PARA QUÊ — «mudou» sem dizer o quê faria o
    oficial ir ao banco descobrir.
    """
    if isinstance(guardado, dict) and isinstance(agora, dict):
        saida: list[str] = []
        for chave in sorted(set(guardado) | set(agora), key=str):
            onde = f"{caminho}.{chave}" if caminho else str(chave)
            if chave not in agora:
                saida.append(f"{onde}: sumiu")
            elif chave not in guardado:
                saida.append(f"{onde}: apareceu ({_curto(agora[chave])})")
            else:
                saida += _diferencas(guardado[chave], agora[chave], onde)
        return saida
    if _json(guardado) == _json(agora):
        return []
    return [f"{caminho or 'o antes'}: era {_curto(guardado)}, está {_curto(agora)}"]


def _curto(valor: Any) -> str:
    texto = _json(valor)
    return texto if len(texto) <= 80 else texto[:77] + "..."


def _sustentada(tipos: list[str]) -> str:
    """A situação que estes atos válidos sustentam, na ordem dos ids. Só
    calcula.

    É A REGRA DE `protesto_selo_previo.situacao_sustentada` (a correção de
    ofício da situação, #109), com as MESMAS constantes de lá, aplicada a uma
    lista em vez do banco: o «depois» de quem torna um ato sem efeito ou lança
    um ato novo se calcula ANTES de executar. A conferência, depois de
    executar, pergunta à função de lá — se as duas divergirem, nada fica.
    """
    import protesto_selo_previo as PSELO
    finais = [PSELO.SITUACAO_DO_ATO[t] for t in tipos
              if PSELO.SITUACAO_DO_ATO.get(t) in PSELO.SITUACOES_FINAIS]
    if finais:
        return finais[-1]
    alcancadas = {PSELO.SITUACAO_DO_ATO.get(t) for t in tipos}
    for situacao in reversed(PSELO.ORDEM_DO_CAMINHO):
        if situacao in alcancadas:
            return situacao
    return "RECEBIDO"


# ------------------------------------------------- o título, como o antes vê

def _titulos(bd, ids: list[int], *, travar: bool) -> dict[str, dict]:
    """A situação de cada título e os atos válidos dele. Só LÊ (e prende as
    linhas dos títulos, com `travar`, até o fim da transação da aprovação).

    Os atos válidos entram no «antes» porque é deles que o «depois» da
    situação se calcula: um ato lançado entre a proposta e a aprovação muda
    a conta, e a aprovação tem de ver isso.
    """
    if not ids:
        return {}
    trava = " FOR UPDATE" if travar else ""
    saida: dict[str, dict] = {}
    for t in bd.ler(f"SELECT id, situacao FROM pt_titulos WHERE id = ANY(%s) "
                    f"ORDER BY id{trava}", ([int(i) for i in ids],)):
        validos = bd.ler(
            """SELECT id, tipo FROM pt_atos
                WHERE titulo_id = %s AND COALESCE(cancelado, 0) = 0
                ORDER BY id""", (int(t["id"]),))
        saida[str(int(t["id"]))] = {
            "situacao": str(t["situacao"] or ""),
            "atos_validos": [[int(a["id"]), str(a["tipo"])] for a in validos]}
    return saida


def _rotulos_dos_titulos(bd, ids: list[int]) -> dict[str, dict]:
    """Número e protocolo de cada título, para a tela. Só LÊ — e não entra no
    «antes»: o rótulo é para quem lê, e não condição de nada."""
    if not ids:
        return {}
    return {str(int(r["id"])): {"numero_titulo": r["numero_titulo"],
                                "protocolo": r["protocolo"]}
            for r in bd.ler("SELECT id, numero_titulo, protocolo FROM pt_titulos "
                            "WHERE id = ANY(%s)", ([int(i) for i in ids],))}


def _situacao_depois(titulos: dict[str, dict], *, sem: set[int] = frozenset(),
                     mais: dict[str, list[str]] | None = None) -> dict[str, dict]:
    """Os títulos cuja situação muda quando os atos `sem` deixam de valer e os
    tipos de `mais` entram, cada um no seu título. Só calcula."""
    saida: dict[str, dict] = {}
    for tid, t in titulos.items():
        tipos = [tipo for aid, tipo in t["atos_validos"] if int(aid) not in sem]
        tipos += list((mais or {}).get(tid, []))
        nova = _sustentada(tipos)
        if nova != t["situacao"]:
            saida[tid] = {"situacao": nova}
    return saida


def _trocar_situacoes(bd, antes: dict, depois: dict) -> list[int]:
    """Grava a situação nova de cada título, só se ela ainda é a de antes.
    ESCREVE."""
    trocados = []
    for tid, d in sorted((depois.get("titulos") or {}).items(), key=lambda x: int(x[0])):
        era = antes["titulos"][tid]["situacao"]
        feito = bd.escrever(
            "UPDATE pt_titulos SET situacao = %s WHERE id = %s AND situacao = %s "
            "RETURNING id", (d["situacao"], int(tid), era))
        if not feito:
            raise _Falha(f"o título {tid} mudou de situação no meio da execução "
                         f"(era {era}) — nada foi gravado")
        trocados.append(int(tid))
    return trocados


def _conferir_situacoes(bd, depois: dict) -> list[str]:
    """Relê a situação de cada título trocado e pergunta à regra do #109 se é
    a que os atos válidos sustentam. Só LÊ."""
    import protesto_selo_previo as PSELO
    problemas = []
    for tid, d in sorted((depois.get("titulos") or {}).items(), key=lambda x: int(x[0])):
        gravada = bd.valor("SELECT situacao FROM pt_titulos WHERE id = %s", (int(tid),))
        if gravada != d["situacao"]:
            problemas.append(f"o título {tid} ficou {gravada}, e o depois dizia "
                             f"{d['situacao']}")
            continue
        sustentada = PSELO.situacao_sustentada(bd, int(tid))
        if sustentada != d["situacao"]:
            problemas.append(f"o título {tid} ficou {gravada}, mas os atos válidos "
                             f"dele sustentam {sustentada}")
    return problemas


def _mudancas_de_situacao(antes: dict, depois: dict) -> list[dict]:
    return [{"tabela": "pt_titulos", "id": int(tid), "titulo_id": int(tid),
             "rotulo": f"título {tid}",
             "antes": {"situacao": antes["titulos"][tid]["situacao"]},
             "depois": {"situacao": d["situacao"]}}
            for tid, d in sorted((depois.get("titulos") or {}).items(), key=lambda x: int(x[0]))]


def _inserir_ato(bd, novo: dict, contexto: dict) -> int:
    """Grava o ato do «depois» e devolve o número dele. ESCREVE."""
    feito = bd.escrever(
        """INSERT INTO pt_atos (titulo_id, tipo, data_ato, detalhe_json,
               observacao, origem, origem_chave, criado_em, criado_por)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (novo["titulo_id"], novo["tipo"], novo["data_ato"], novo["detalhe_json"],
         novo["observacao"], novo["origem"], novo["origem_chave"],
         contexto["agora"], contexto["quem"]))
    return int(feito[0]["id"])


# ================================================================ os tipos

class Tipo:
    """Um tipo do catálogo. A subclasse diz o que lê, o que confere, o que
    grava e como relê. Nenhum método recebe SQL de fora."""

    chave = ""
    atribuicao = ""
    rotulo = ""
    descricao = ""
    alvo_tabela = ""
    #: Os campos do formulário: (nome, rótulo, widget, ajuda). O widget é
    #: `ids`, `numero`, `data`, `caixa` (marcada de saída) ou `cadastro`.
    campos: tuple[tuple[str, str, str, str], ...] = ()

    # -- o pedido
    def do_formulario(self, form) -> dict:
        """O pedido como o formulário o manda. A caixa desmarcada não vem."""
        saida: dict[str, Any] = {}
        for nome, _rotulo, widget, _ajuda in self.campos:
            if widget == "caixa":
                saida[nome] = form.get(nome) == "1"
            else:
                saida[nome] = form.get(nome)
        return saida

    def normalizar(self, pedido: dict) -> tuple[dict, list[str]]:
        raise NotImplementedError

    # -- o antes, a regra e o depois
    def ler_antes(self, bd, parametros: dict, *, travar: bool) -> dict:
        raise NotImplementedError

    def conferir_pedido(self, bd, parametros: dict, antes: dict
                        ) -> tuple[dict, list[str], list[str]]:
        """(parâmetros finais, recusas, avisos). Os parâmetros finais podem
        ser mais estreitos que os pedidos — o que já está certo sai."""
        raise NotImplementedError

    def calcular_depois(self, parametros: dict, antes: dict, *, motivo: str,
                        numero: int | None) -> dict:
        raise NotImplementedError

    def alvos(self, parametros: dict, antes: dict) -> tuple[list[int], list[int]]:
        """(ids do alvo, ids dos títulos tocados)."""
        raise NotImplementedError

    def resumo(self, parametros: dict, antes: dict, depois: dict) -> str:
        raise NotImplementedError

    def mudancas(self, antes: dict, depois: dict, resultado: dict | None
                 ) -> list[dict]:
        """Cada linha tocada: tabela, id, rótulo, antes e depois dela."""
        raise NotImplementedError

    # -- a execução
    def executar(self, bd, parametros: dict, antes: dict, depois: dict,
                 contexto: dict) -> dict:
        raise NotImplementedError

    def conferir_execucao(self, bd, parametros: dict, antes: dict, depois: dict,
                          resultado: dict) -> list[str]:
        raise NotImplementedError


# ---------------------------------------------- 1. tornar ato sem efeito

class AtoSemEfeito(Tipo):
    """Torna atos sem efeito (`cancelado = 1`, com o motivo no ato) — e, se
    pedido, volta a situação dos títulos à que os atos que restam sustentam.

    NÃO DESFAZ O QUE ESTÁ FORA DO BANCO, e a prévia diz: o selo do ato (o
    pedido de cancelamento ao TJMA é outra tela), a Central que já foi
    informada (o retorno à CRA, o XML da CENPROT), o papel entregue.
    """

    chave = "PT_ATO_SEM_EFEITO"
    atribuicao = ATRIBUICAO_PROTESTO
    rotulo = "Tornar ato sem efeito"
    descricao = ("Marca o ato como sem efeito (cancelado), com o motivo no "
                 "próprio ato. Não apaga nada: o ato continua na ficha, riscado.")
    alvo_tabela = "pt_atos"
    LIMITE = 50
    campos = (
        ("ato_ids", "Os atos (números do sistema, separados por vírgula)", "ids",
         "o número que a ficha do título mostra em cada ato"),
        ("ajustar_situacao", ("E voltar a situação dos títulos à que os atos "
                              "válidos restantes sustentam"), "caixa",
         "desmarque só se a situação vai ser tratada noutra proposta"),
    )

    def normalizar(self, pedido):
        ids, ruins = _ids(pedido.get("ato_ids"))
        recusas = []
        if ruins:
            recusas.append(f"Não é número de ato: {', '.join(ruins)}.")
        if not ids:
            recusas.append("Informe pelo menos um ato.")
        if len(ids) > self.LIMITE:
            recusas.append(f"São {len(ids)} atos; o teto de uma proposta é "
                           f"{self.LIMITE}.")
        return ({"ato_ids": ids,
                 "ajustar_situacao": _sim(pedido.get("ajustar_situacao"), True)},
                recusas)

    def _atos(self, bd, ids, *, travar):
        trava = " FOR UPDATE" if travar else ""
        return bd.ler(
            f"""SELECT id, titulo_id, tipo, data_ato, cancelado,
                       motivo_cancelamento, selo, origem, retorno_id,
                       cenprot_xml_id
                  FROM pt_atos WHERE id = ANY(%s) ORDER BY id{trava}""",
            ([int(i) for i in ids],))

    def ler_antes(self, bd, parametros, *, travar):
        ids = parametros["ato_ids"]
        # A ORDEM DAS TRAVAS É A DA CASA: o título primeiro
        # (`protesto.titulo_para_gravar`), o ato depois.
        titulo_ids = sorted({int(a["titulo_id"]) for a in self._atos(bd, ids, travar=False)})
        titulos = _titulos(bd, titulo_ids, travar=travar)
        atos = {str(int(a["id"])): {
                    "titulo_id": int(a["titulo_id"]), "tipo": str(a["tipo"]),
                    "data_ato": str(a["data_ato"] or ""),
                    "cancelado": int(a["cancelado"] or 0),
                    "motivo_cancelamento": a["motivo_cancelamento"],
                    "selo": a["selo"], "origem": a["origem"],
                    "retorno_id": a["retorno_id"],
                    "cenprot_xml_id": a["cenprot_xml_id"]}
                for a in self._atos(bd, ids, travar=travar)}
        instrumentos: dict[str, int] = {}
        if titulo_ids and bd.tem_tabela("pt_instrumentos"):
            for r in bd.ler("""SELECT titulo_id, count(*) AS n FROM pt_instrumentos
                                WHERE titulo_id = ANY(%s) GROUP BY titulo_id""",
                            (titulo_ids,)):
                instrumentos[str(int(r["titulo_id"]))] = int(r["n"])
        return {"atos": atos, "titulos": titulos, "instrumentos": instrumentos}

    def conferir_pedido(self, bd, parametros, antes):
        recusas, avisos = [], []
        for aid in parametros["ato_ids"]:
            a = antes["atos"].get(str(aid))
            if a is None:
                recusas.append(f"O ato {aid} não existe.")
                continue
            if a["cancelado"]:
                recusas.append(f"O ato {aid} ({a['tipo']}) já está sem efeito.")
                continue
            tid = str(a["titulo_id"])
            if a["tipo"] == "PROTESTO" and antes["instrumentos"].get(tid):
                recusas.append(
                    f"O título {tid} já tem instrumento de protesto: tornar o "
                    f"protesto {aid} sem efeito com o instrumento emitido não "
                    "tem precedente nesta casa — o oficial decide fora da fila.")
            if _txt(a["selo"]):
                avisos.append(
                    f"O ato {aid} tem o selo {a['selo']}: o pedido de "
                    "cancelamento do selo ao TJMA não é feito por esta correção "
                    "(Administrativo → Selos cancelados).")
            if a["retorno_id"]:
                avisos.append(
                    f"A CRA já foi informada do ato {aid} (retorno "
                    f"{a['retorno_id']}): esta correção não avisa a Central — a "
                    "retificação lá é pelo suporte.")
            if a["cenprot_xml_id"]:
                avisos.append(
                    f"A CENPROT já foi informada do ato {aid} (XML "
                    f"{a['cenprot_xml_id']}): esta correção não avisa a Central.")
        if not recusas and not parametros["ajustar_situacao"]:
            sem = set(parametros["ato_ids"])
            for tid, d in _situacao_depois(antes["titulos"], sem=sem).items():
                avisos.append(
                    f"O título {tid} vai ficar {antes['titulos'][tid]['situacao']} "
                    f"sem o ato que a sustente (os atos que restam sustentam "
                    f"{d['situacao']}): proponha também a situação, ou marque "
                    "«e voltar a situação».")
        return parametros, recusas, avisos

    def _motivo_no_ato(self, motivo, numero):
        return (f"TORNADO SEM EFEITO — correção de ofício {_numero(numero)}, "
                f"aprovada pelo oficial: {motivo}")

    def calcular_depois(self, parametros, antes, *, motivo, numero):
        texto = self._motivo_no_ato(motivo, numero)
        depois = {"atos": {str(aid): {"cancelado": 1, "motivo_cancelamento": texto}
                           for aid in parametros["ato_ids"]},
                  "titulos": {}}
        if parametros["ajustar_situacao"]:
            depois["titulos"] = _situacao_depois(
                antes["titulos"], sem=set(parametros["ato_ids"]))
        return depois

    def alvos(self, parametros, antes):
        return (list(parametros["ato_ids"]),
                sorted({a["titulo_id"] for a in antes["atos"].values()}))

    def resumo(self, parametros, antes, depois):
        partes = [f"{a['tipo']} {aid} (título {a['titulo_id']})"
                  for aid, a in sorted(antes["atos"].items(), key=lambda x: int(x[0]))]
        frase = "Tornar sem efeito: " + ", ".join(partes)
        if depois.get("titulos"):
            frase += "; situação: " + ", ".join(
                f"título {tid} {antes['titulos'][tid]['situacao']} → {d['situacao']}"
                for tid, d in sorted(depois["titulos"].items(), key=lambda x: int(x[0])))
        return frase + "."

    def mudancas(self, antes, depois, resultado):
        linhas = []
        for aid, d in sorted(depois["atos"].items(), key=lambda x: int(x[0])):
            a = antes["atos"].get(aid) or {}
            linhas.append({"tabela": "pt_atos", "id": int(aid),
                           "titulo_id": a.get("titulo_id"),
                           "rotulo": f"ato {aid} ({a.get('tipo', '?')})",
                           "antes": {"cancelado": a.get("cancelado"),
                                     "motivo_cancelamento": a.get("motivo_cancelamento")},
                           "depois": dict(d)})
        return linhas + _mudancas_de_situacao(antes, depois)

    def executar(self, bd, parametros, antes, depois, contexto):
        for aid, d in sorted(depois["atos"].items(), key=lambda x: int(x[0])):
            feito = bd.escrever(
                """UPDATE pt_atos SET cancelado = 1, motivo_cancelamento = %s
                    WHERE id = %s AND COALESCE(cancelado, 0) = 0 RETURNING id""",
                (d["motivo_cancelamento"], int(aid)))
            if not feito:
                raise _Falha(f"o ato {aid} já não estava válido na execução — "
                             "nada foi gravado")
        return {"atos_sem_efeito": sorted(int(a) for a in depois["atos"]),
                "titulos_com_situacao_nova": _trocar_situacoes(bd, antes, depois)}

    def conferir_execucao(self, bd, parametros, antes, depois, resultado):
        problemas = []
        for aid, d in depois["atos"].items():
            r = bd.um("SELECT cancelado, motivo_cancelamento FROM pt_atos WHERE id = %s",
                      (int(aid),))
            if not r or int(r["cancelado"] or 0) != 1 \
                    or r["motivo_cancelamento"] != d["motivo_cancelamento"]:
                problemas.append(f"o ato {aid} não ficou sem efeito com o motivo")
        return problemas + _conferir_situacoes(bd, depois)


# ------------------------------- 2. a situação que os atos válidos sustentam

class SituacaoSustentada(Tipo):
    """Volta a situação do título à que os atos VÁLIDOS sustentam.

    É a correção de ofício do #109 (`protesto_selo_previo`, regra
    `SITUACAO_SEM_ATO`), pela fila: a régua é a MESMA
    (`situacao_sustentada`), e a explicação do porquê também
    (`situacao_sem_ato`). Não lavra ato nenhum e não toca nos atos.
    """

    chave = "PT_SITUACAO_SUSTENTADA"
    atribuicao = ATRIBUICAO_PROTESTO
    rotulo = "Voltar a situação à que os atos válidos sustentam"
    descricao = ("Troca só a situação do título, para a que os atos válidos dele "
                 "sustentam — a régua da conferência «situação sem ato».")
    alvo_tabela = "pt_titulos"
    LIMITE = 200
    campos = (
        ("titulo_ids", "Os títulos (números do sistema, separados por vírgula)",
         "ids", "o número do título no sistema (o da ficha), e não o do papel"),
    )

    def normalizar(self, pedido):
        ids, ruins = _ids(pedido.get("titulo_ids"))
        recusas = []
        if ruins:
            recusas.append(f"Não é número de título: {', '.join(ruins)}.")
        if not ids:
            recusas.append("Informe pelo menos um título.")
        if len(ids) > self.LIMITE:
            recusas.append(f"São {len(ids)} títulos; o teto é {self.LIMITE}.")
        return {"titulo_ids": ids}, recusas

    def ler_antes(self, bd, parametros, *, travar):
        return {"titulos": _titulos(bd, parametros["titulo_ids"], travar=travar)}

    def conferir_pedido(self, bd, parametros, antes):
        import protesto_selo_previo as PSELO
        recusas, avisos = [], []
        for tid in parametros["titulo_ids"]:
            t = antes["titulos"].get(str(tid))
            if t is None:
                recusas.append(f"O título {tid} não existe.")
                continue
            nova = _sustentada([tipo for _aid, tipo in t["atos_validos"]])
            if nova == t["situacao"]:
                recusas.append(f"Nada a corrigir no título {tid}: a situação "
                               f"{t['situacao']} é a que os atos válidos sustentam.")
                continue
            # A RÉGUA É UMA SÓ: a conta desta lista tem de dar o mesmo que a
            # do #109 pelo banco. Se divergirem, é defeito de programa — e a
            # proposta não nasce com um «depois» que a conferência recusaria.
            pelo_banco = PSELO.situacao_sustentada(bd, tid)
            if pelo_banco != nova:
                recusas.append(f"Título {tid}: a conta da fila dá {nova} e a da "
                               f"conferência «situação sem ato» dá {pelo_banco}. "
                               "Isto é defeito do sistema: avise o desenvolvimento.")
                continue
            achado = PSELO.situacao_sem_ato(bd, tid)
            if achado:
                avisos.append(f"Título {tid}: {achado['explicacao']}")
        return parametros, recusas, avisos

    def calcular_depois(self, parametros, antes, *, motivo, numero):
        return {"titulos": _situacao_depois(antes["titulos"])}

    def alvos(self, parametros, antes):
        ids = sorted(int(t) for t in antes["titulos"])
        return ids, ids

    def resumo(self, parametros, antes, depois):
        return "Situação: " + ", ".join(
            f"título {tid} {antes['titulos'][tid]['situacao']} → {d['situacao']}"
            for tid, d in sorted(depois["titulos"].items(), key=lambda x: int(x[0]))) + "."

    def mudancas(self, antes, depois, resultado):
        return _mudancas_de_situacao(antes, depois)

    def executar(self, bd, parametros, antes, depois, contexto):
        return {"titulos_com_situacao_nova": _trocar_situacoes(bd, antes, depois)}

    def conferir_execucao(self, bd, parametros, antes, depois, resultado):
        return _conferir_situacoes(bd, depois)


# ------------------------------------------- 3. o cadastro do título

#: OS CAMPOS DO CADASTRO QUE A CORREÇÃO ALCANÇA — e só eles. A lista é a
#: guarda: a rota não confia em nome de campo que o formulário mandou, e o SQL
#: só leva nome que sai daqui.
#:
#: FICAM DE FORA, de propósito: número do título, protocolo, espécie, valor,
#: saldo, datas, situação (tem tipo próprio), origem e chave de origem, o
#: código do apresentante (é por ele que o retorno volta à Central), e o NOME
#: e o DOCUMENTO do devedor — trocar quem é o devedor não é corrigir cadastro.
CAMPOS_DO_CADASTRO: dict[str, tuple[tuple[str, str], ...]] = {
    "pt_titulos": (
        ("cedente_nome", "Cedente (credor) — nome"),
        ("cedente_documento", "Cedente — CPF/CNPJ"),
        ("cedente_endereco", "Cedente — endereço, com o número"),
        ("cedente_cep", "Cedente — CEP"),
        ("cedente_cidade", "Cedente — cidade"),
        ("cedente_uf", "Cedente — UF"),
        ("apresentante_nome", "Apresentante — nome"),
        ("apresentante_documento", "Apresentante — CPF/CNPJ"),
        ("apresentante_endereco", "Apresentante — endereço"),
        ("apresentante_tipo", "Apresentante — tipo no XML da CENPROT"),
    ),
    "pt_devedores": (
        ("endereco", "Devedor — endereço"),
        ("bairro", "Devedor — bairro"),
        ("cep", "Devedor — CEP"),
        ("cidade", "Devedor — cidade"),
        ("uf", "Devedor — UF"),
    ),
}
#: No formulário (e no pedido curto do JSON), o campo do devedor leva este
#: prefixo, para não se confundir com o do cedente.
PREFIXO_DO_DEVEDOR = "devedor_"
#: Os do apresentante só valem no título cujo apresentante é DO TÍTULO (o
#: TAB), a mesma regra de `protesto_cenprot_xml.gravar_apresentante_do_titulo`:
#: nos outros ele é do cadastro dos apresentantes, pelo código.
CAMPOS_DO_APRESENTANTE = ("apresentante_nome", "apresentante_documento",
                          "apresentante_endereco", "apresentante_tipo")


def _campos_de(tabela: Any) -> tuple[str, tuple[str, ...]] | None:
    """O nome da tabela COMO ESTÁ AQUI e os campos dela — ou None. O texto que
    vai ao SQL é o da constante, e não o que veio no pedido."""
    for nome, campos in CAMPOS_DO_CADASTRO.items():
        if nome == str(tabela or ""):
            return nome, tuple(c for c, _ in campos)
    return None


def _valor_do_campo(campo: str, valor: Any) -> tuple[str | None, str | None]:
    """(valor normalizado, recusa). Vazio vira nulo — limpar é corrigir."""
    if valor is None:
        return None, None
    bruto = _corrido(valor)
    if not bruto:
        return None, None
    if campo.endswith("uf"):
        uf = bruto.upper()
        if not re.fullmatch(r"[A-Z]{2}", uf):
            return None, f"«{bruto}» não é UF (duas letras)"
        return uf, None
    if campo.endswith("cep"):
        digitos = re.sub(r"\D", "", bruto)
        if len(digitos) != 8:
            return None, f"«{bruto}» não é CEP (oito dígitos)"
        return digitos, None
    if campo == "apresentante_documento":
        digitos = re.sub(r"\D", "", bruto)
        if len(digitos) not in (11, 14):
            return None, "o documento do apresentante é CPF (11 dígitos) ou CNPJ (14)"
        return digitos, None
    if campo == "apresentante_tipo":
        if not re.fullmatch(r"\d{1,2}", bruto):
            return None, ("o tipo do apresentante é o número do XML da CENPROT "
                          "(0, 1, 4…)")
        return bruto, None
    if len(bruto) > 300:
        return None, f"o campo {campo} passa de 300 letras"
    return bruto, None


class CadastroDoTitulo(Tipo):
    """Corrige campos do cadastro de um ou de vários títulos — e o endereço do
    devedor —, numa lista fechada (`CAMPOS_DO_CADASTRO`).

    O LOTE É DO PRECEDENTE: o cedente da carga do acervo corrigido em 1.409
    títulos, cada um com o seu valor, e SÓ onde o valor de hoje era o que a
    carga errada gravou. Por isso cada item pode dizer o `esperado`: o item
    cujo valor de hoje não é o esperado é recusado na proposta (quem propõe
    o tira), e não «corrigido por cima».

    NÃO TOCA EM ATO NENHUM: o termo do protesto, o aviso e o edital
    congelaram o que estava no cadastro quando foram lavrados, e a prévia diz
    quantos títulos têm ato assim.
    """

    chave = "PT_CADASTRO_DO_TITULO"
    atribuicao = ATRIBUICAO_PROTESTO
    rotulo = "Corrigir o cadastro do título (cedente, apresentante, endereço do devedor)"
    descricao = ("Troca campos do cadastro numa lista fechada, em um ou vários "
                 "títulos. Não toca nos atos já lavrados.")
    alvo_tabela = "pt_titulos"
    LIMITE = 2000
    campos = (
        ("titulo_ids", "Os títulos (números do sistema, separados por vírgula)",
         "ids", ("o mesmo valor vai para todos; lote com um valor por título só "
                 "pelo pedido em JSON")),
        ("devedor_ordem", "Só para o endereço do devedor: qual devedor do título",
         "numero", "1 = o primeiro devedor da ficha"),
        ("campos", "Os campos a corrigir", "cadastro",
         "marque o campo e escreva o valor certo; marcado e vazio, ele fica vazio"),
    )

    def do_formulario(self, form):
        campos = {}
        for tabela, lista in CAMPOS_DO_CADASTRO.items():
            prefixo = PREFIXO_DO_DEVEDOR if tabela == "pt_devedores" else ""
            for campo, _rotulo in lista:
                nome = prefixo + campo
                if form.get(f"corrigir__{nome}") == "1":
                    campos[nome] = form.get(nome, "")
        return {"titulo_ids": form.get("titulo_ids"),
                "devedor_ordem": form.get("devedor_ordem"), "campos": campos}

    def _itens_do_pedido_curto(self, pedido, recusas):
        ids, ruins = _ids(pedido.get("titulo_ids"))
        if ruins:
            recusas.append(f"Não é número de título: {', '.join(ruins)}.")
        if not ids:
            recusas.append("Informe pelo menos um título.")
        campos = pedido.get("campos") if isinstance(pedido.get("campos"), dict) else {}
        esperado = pedido.get("esperado") if isinstance(pedido.get("esperado"), dict) else {}
        do_titulo = {k: v for k, v in campos.items() if not str(k).startswith(PREFIXO_DO_DEVEDOR)}
        do_devedor = {str(k)[len(PREFIXO_DO_DEVEDOR):]: v for k, v in campos.items()
                      if str(k).startswith(PREFIXO_DO_DEVEDOR)}
        esp_titulo = {k: v for k, v in esperado.items() if not str(k).startswith(PREFIXO_DO_DEVEDOR)}
        esp_devedor = {str(k)[len(PREFIXO_DO_DEVEDOR):]: v for k, v in esperado.items()
                       if str(k).startswith(PREFIXO_DO_DEVEDOR)}
        ordem = 1
        if do_devedor:
            bruto = str(pedido.get("devedor_ordem") or "1").strip()
            if not bruto.isdigit() or int(bruto) < 1:
                recusas.append("O devedor do título se diz pelo número dele na "
                               "ficha: 1, 2, 3…")
            else:
                ordem = int(bruto)
        itens = []
        for tid in ids:
            if do_titulo:
                itens.append({"tabela": "pt_titulos", "id": tid, "campos": do_titulo,
                              "esperado": esp_titulo or None})
            if do_devedor:
                itens.append({"tabela": "pt_devedores", "titulo_id": tid,
                              "ordem": ordem, "campos": do_devedor,
                              "esperado": esp_devedor or None})
        if ids and not campos:
            recusas.append("Marque pelo menos um campo a corrigir.")
        return itens

    def normalizar(self, pedido):
        recusas: list[str] = []
        brutos = pedido.get("itens")
        if brutos is None:
            brutos = self._itens_do_pedido_curto(pedido, recusas)
        if not isinstance(brutos, list):
            return {"itens": []}, ["Os itens vêm em lista."]
        itens, vistos = [], set()
        for n, bruto in enumerate(brutos, start=1):
            if not isinstance(bruto, dict):
                recusas.append(f"Item {n}: fora da forma (tabela, id, campos).")
                continue
            achada = _campos_de(bruto.get("tabela"))
            if achada is None:
                recusas.append(f"Item {n}: a tabela «{bruto.get('tabela')}» não está "
                               "no catálogo (pt_titulos ou pt_devedores).")
                continue
            tabela, permitidos = achada
            campos = bruto.get("campos") if isinstance(bruto.get("campos"), dict) else {}
            fora = sorted(str(k) for k in campos if k not in permitidos)
            if fora:
                recusas.append(f"Item {n}: campo fora da lista fechada: "
                               f"{', '.join(fora)}.")
                continue
            if not campos:
                recusas.append(f"Item {n}: nenhum campo a corrigir.")
                continue
            novos, erros = {}, []
            for campo in permitidos:          # o nome sai da constante
                if campo in campos:
                    valor, erro = _valor_do_campo(campo, campos[campo])
                    if erro:
                        erros.append(erro)
                    novos[campo] = valor
            if erros:
                recusas.append(f"Item {n}: {'; '.join(erros)}.")
                continue
            esperado = bruto.get("esperado")
            esperado = ({c: _txt(esperado[c]) for c in permitidos if c in esperado}
                        if isinstance(esperado, dict) else None)
            item = {"tabela": tabela, "campos": novos, "esperado": esperado or None}
            if tabela == "pt_devedores" and not str(bruto.get("id") or "").isdigit():
                tid, ordem = str(bruto.get("titulo_id") or ""), str(bruto.get("ordem") or "1")
                if not tid.isdigit() or not ordem.isdigit() or int(ordem) < 1:
                    recusas.append(f"Item {n}: o devedor se diz pelo id, ou pelo "
                                   "título e a ordem dele (1, 2…).")
                    continue
                item.update({"titulo_id": int(tid), "ordem": int(ordem)})
                chave = (tabela, "t", int(tid), int(ordem))
            else:
                if not str(bruto.get("id") or "").isdigit():
                    recusas.append(f"Item {n}: falta o id.")
                    continue
                item["id"] = int(bruto["id"])
                chave = (tabela, "i", int(bruto["id"]))
            if chave in vistos:
                recusas.append(f"Item {n}: a mesma linha veio duas vezes.")
                continue
            vistos.add(chave)
            itens.append(item)
        if len(itens) > self.LIMITE:
            recusas.append(f"São {len(itens)} itens; o teto de uma proposta é "
                           f"{self.LIMITE}.")
        if not itens and not recusas:
            recusas.append("Nada a corrigir: nenhum item.")
        return {"itens": itens}, recusas

    def ler_antes(self, bd, parametros, *, travar):
        """O valor de hoje de cada campo pedido, e o código do apresentante
        do título (a regra do TAB depende dele)."""
        trava = " FOR UPDATE" if travar else ""
        itens = parametros["itens"]
        _, campos_t = _campos_de("pt_titulos")
        _, campos_d = _campos_de("pt_devedores")
        ids_devedor = [i["id"] for i in itens if i["tabela"] == "pt_devedores" and "id" in i]
        tits_devedor = [i["titulo_id"] for i in itens
                        if i["tabela"] == "pt_devedores" and "titulo_id" in i]
        # LISTA VAZIA NÃO VAI AO `ANY`: o PostgreSQL não sabe o tipo de um
        # vetor vazio sem nada ao lado, e a pergunta não tem resposta mesmo.
        devedores = bd.ler(
            f"""SELECT id, titulo_id, {', '.join(campos_d)} FROM pt_devedores
                 WHERE id = ANY(%s) OR titulo_id = ANY(%s)
                 ORDER BY titulo_id, id""", (ids_devedor or [0], tits_devedor or [0])
        ) if (ids_devedor or tits_devedor) else []
        por_titulo: dict[int, list[dict]] = {}
        for d in devedores:
            por_titulo.setdefault(int(d["titulo_id"]), []).append(d)
        por_id = {int(d["id"]): d for d in devedores}
        titulo_ids = sorted({i["id"] for i in itens if i["tabela"] == "pt_titulos"}
                            | {int(d["titulo_id"]) for d in devedores})
        titulos = {int(t["id"]): t for t in bd.ler(
            f"""SELECT id, apresentante_codigo, {', '.join(campos_t)} FROM pt_titulos
                 WHERE id = ANY(%s) ORDER BY id{trava}""", (titulo_ids,))
        } if titulo_ids else {}
        if travar and devedores:
            bd.ler("SELECT id FROM pt_devedores WHERE id = ANY(%s) ORDER BY id FOR UPDATE",
                   ([int(d["id"]) for d in devedores],))
        saida = []
        for i in itens:
            if i["tabela"] == "pt_titulos":
                linha, tid = titulos.get(i["id"]), i["id"]
            elif "id" in i:
                linha = por_id.get(i["id"])
                tid = int(linha["titulo_id"]) if linha else None
            else:
                lista = por_titulo.get(i["titulo_id"], [])
                linha = lista[i["ordem"] - 1] if len(lista) >= i["ordem"] else None
                tid = i["titulo_id"]
            if linha is None:
                saida.append({"tabela": i["tabela"], "pedido": _pedido_do_item(i),
                              "achado": False})
                continue
            # O VALOR CRU, como está no banco: é ele que vai no WHERE da
            # execução. A comparação com o pedido é que passa por `_txt`.
            saida.append({"tabela": i["tabela"], "id": int(linha["id"]),
                          "titulo_id": tid, "achado": True,
                          "campos": {c: linha[c] for c in i["campos"]}})
        codigos = {str(tid): _txt(t["apresentante_codigo"]) for tid, t in titulos.items()}
        return {"itens": saida, "apresentante_codigo": codigos}

    def conferir_pedido(self, bd, parametros, antes):
        import protesto_cenprot_xml as X
        recusas, avisos = [], []
        finais, ja_certos, fora_do_esperado = [], 0, []
        for pedido, lido in zip(parametros["itens"], antes["itens"]):
            if not lido["achado"]:
                recusas.append(f"Não achei {lido['pedido']}.")
                continue
            tid = lido["titulo_id"]
            esperado = pedido.get("esperado") or {}
            diverge = [c for c in esperado
                       if c in lido["campos"] and _txt(lido["campos"][c]) != esperado[c]]
            if diverge:
                fora_do_esperado.append(f"{lido['tabela']} {lido['id']} "
                                        f"({', '.join(diverge)})")
                continue
            if lido["tabela"] == "pt_titulos" and any(
                    c in CAMPOS_DO_APRESENTANTE for c in pedido["campos"]):
                codigo = antes["apresentante_codigo"].get(str(tid))
                if codigo not in X.APRESENTANTES_DO_TITULO:
                    recusas.append(
                        f"Título {tid}: o apresentante {codigo or '(sem código)'} "
                        "é do cadastro dos apresentantes, e não do título — "
                        "corrija-o lá.")
                    continue
            mudam = {c: v for c, v in pedido["campos"].items()
                     if _txt(lido["campos"].get(c)) != v}
            if not mudam:
                ja_certos += 1
                continue
            finais.append({"tabela": lido["tabela"], "id": lido["id"], "campos": mudam})
        if fora_do_esperado:
            recusas.append(
                f"Em {len(fora_do_esperado)} item(ns) o valor de hoje não é o "
                "esperado — alguém mexeu depois; tire-os da proposta: "
                + "; ".join(fora_do_esperado[:20])
                + (" …" if len(fora_do_esperado) > 20 else "") + ".")
        if not finais and not recusas:
            recusas.append("Nada a corrigir: os valores pedidos já são os de hoje.")
        if ja_certos:
            avisos.append(f"{ja_certos} item(ns) já estavam com o valor pedido e "
                          "ficaram de fora.")
        titulos = sorted({lido["titulo_id"] for lido in antes["itens"]
                          if lido["achado"] and lido["titulo_id"]})
        if finais and not recusas and titulos:
            lavrados = bd.valor(
                """SELECT count(DISTINCT titulo_id) FROM pt_atos
                    WHERE titulo_id = ANY(%s) AND COALESCE(cancelado, 0) = 0
                      AND tipo IN ('INTIMACAO', 'PROTESTO', 'CANCELAMENTO')""",
                (titulos,))
            if lavrados:
                avisos.append(
                    f"{lavrados} título(s) já têm intimação, protesto ou "
                    "cancelamento lavrado: o que esses atos congelaram (termo, "
                    "aviso, edital) não muda com esta correção.")
        return {"itens": finais}, recusas, avisos

    def calcular_depois(self, parametros, antes, *, motivo, numero):
        return {"itens": [dict(i) for i in parametros["itens"]]}

    def alvos(self, parametros, antes):
        ids = [i["id"] for i in parametros["itens"]]
        por_linha = {(lido["tabela"], lido.get("id")): lido.get("titulo_id")
                     for lido in antes["itens"]}
        titulos = sorted({por_linha[(i["tabela"], i["id"])] for i in parametros["itens"]})
        return ids, titulos

    def resumo(self, parametros, antes, depois):
        campos = sorted({c for i in parametros["itens"] for c in i["campos"]})
        titulos = len({(i["tabela"], i["id"]) for i in parametros["itens"]})
        return (f"Cadastro: {', '.join(campos)} em {titulos} linha(s) "
                f"({', '.join(sorted({i['tabela'] for i in parametros['itens']}))}).")

    def mudancas(self, antes, depois, resultado):
        lidos = {(lido["tabela"], lido.get("id")): lido for lido in antes["itens"]}
        linhas = []
        for i in depois["itens"]:
            lido = lidos.get((i["tabela"], i["id"])) or {"campos": {}}
            nome = "título" if i["tabela"] == "pt_titulos" else "devedor"
            linhas.append({"tabela": i["tabela"], "id": i["id"],
                           "titulo_id": lido.get("titulo_id"),
                           "rotulo": f"{nome} {i['id']}",
                           "antes": {c: lido["campos"].get(c) for c in i["campos"]},
                           "depois": dict(i["campos"])})
        return linhas

    def executar(self, bd, parametros, antes, depois, contexto):
        lidos = {(lido["tabela"], lido.get("id")): lido for lido in antes["itens"]}
        feitos = 0
        for i in depois["itens"]:
            tabela, permitidos = _campos_de(i["tabela"])
            cols = [c for c in permitidos if c in i["campos"]]
            era = lidos[(i["tabela"], i["id"])]["campos"]
            sets = ", ".join(f"{c} = %s" for c in cols)
            onde = " AND ".join(f"{c} IS NOT DISTINCT FROM %s" for c in cols)
            feito = bd.escrever(
                f"UPDATE {tabela} SET {sets} WHERE id = %s AND {onde} RETURNING id",
                [i["campos"][c] for c in cols] + [int(i["id"])] + [era[c] for c in cols])
            if not feito:
                raise _Falha(f"{tabela} {i['id']} mudou no meio da execução — "
                             "nada foi gravado")
            feitos += 1
        return {"linhas_corrigidas": feitos}

    def conferir_execucao(self, bd, parametros, antes, depois, resultado):
        problemas = []
        for i in depois["itens"]:
            tabela, permitidos = _campos_de(i["tabela"])
            cols = [c for c in permitidos if c in i["campos"]]
            r = bd.um(f"SELECT {', '.join(cols)} FROM {tabela} WHERE id = %s",
                      (int(i["id"]),))
            if not r or any(r[c] != i["campos"][c] for c in cols):
                problemas.append(f"{tabela} {i['id']} não ficou como o depois dizia")
        return problemas


def _pedido_do_item(item: dict) -> str:
    if "id" in item:
        return f"{item['tabela']} {item['id']}"
    return f"o devedor nº {item['ordem']} do título {item['titulo_id']}"


# ------------------------------------- 4. o ato de correção, copiado de outro

#: OS TIPOS DE ATO QUE SE COPIAM — só os que têm precedente. O PAGAMENTO é o
#: das duas parcelas do mesmo protocolo (29/10/2026). Protesto, intimação e
#: cancelamento têm livro, folha e selo: cópia deles seria lavratura sem
#: livro, e isso não tem precedente — fica de fora até o oficial decidir.
TIPOS_QUE_SE_COPIAM = ("PAGAMENTO",)


class AtoDeCorrecao(Tipo):
    """Lança no título certo um ato copiado de outro (`origem = 'CORRECAO'`),
    com a data do original e o vínculo `correcao_de` no `detalhe_json` — e,
    se pedido, volta a situação do título à que os atos sustentam.

    O ORIGINAL NÃO SE MEXE AQUI: se ele está no título errado, a proposta de
    torná-lo sem efeito é outra (e a prévia avisa).
    """

    chave = "PT_ATO_DE_CORRECAO"
    atribuicao = ATRIBUICAO_PROTESTO
    rotulo = "Lançar ato de correção copiando outro ato"
    descricao = ("Copia um ato (hoje só o PAGAMENTO) para o título certo, com a "
                 "data do original, origem CORRECAO e o vínculo correcao_de.")
    alvo_tabela = "pt_atos"
    campos = (
        ("ato_origem_id", "O ato que se copia (número do sistema)", "numero", ""),
        ("titulo_id", "O título que recebe a cópia (número do sistema)", "numero", ""),
        ("pix_id", "O PIX de crédito conferido, se o pagamento foi por PIX", "numero",
         "sem número, vale o PIX ligado ao ato copiado; sem crédito conferido, a "
         "proposta se recusa"),
        ("ajustar_situacao", ("E voltar a situação do título à que os atos "
                              "válidos sustentam"), "caixa", ""),
    )

    def normalizar(self, pedido):
        recusas = []
        origem, ruins_o = _ids(pedido.get("ato_origem_id"))
        destino, ruins_d = _ids(pedido.get("titulo_id"))
        if ruins_o or len(origem) != 1:
            recusas.append("Informe UM ato de origem, pelo número do sistema.")
        if ruins_d or len(destino) != 1:
            recusas.append("Informe UM título que recebe a cópia.")
        pix, ruins_p = _ids(pedido.get("pix_id"))
        if ruins_p or len(pix) > 1:
            recusas.append("Informe no máximo UM PIX, pelo número do sistema.")
        return ({"ato_origem_id": origem[0] if len(origem) == 1 else None,
                 "titulo_id": destino[0] if len(destino) == 1 else None,
                 "pix_id": pix[0] if len(pix) == 1 else None,
                 "ajustar_situacao": _sim(pedido.get("ajustar_situacao"), True)},
                recusas)

    def ler_antes(self, bd, parametros, *, travar):
        titulos = _titulos(bd, [parametros["titulo_id"]], travar=travar)
        origem = bd.um(
            """SELECT id, titulo_id, tipo, data_ato, cancelado, detalhe_json,
                      origem, selo
                 FROM pt_atos WHERE id = %s""", (int(parametros["ato_origem_id"]),))
        por_pix, pix = self._o_pix(bd, parametros, origem, travar=travar)
        repasses = []
        if origem and bd.tem_tabela("pt_repasses"):
            repasses = [[int(r["id"]), str(r["situacao"])] for r in bd.ler(
                "SELECT id, situacao FROM pt_repasses WHERE ato_id = %s ORDER BY id",
                (int(origem["id"]),))]
        return {"ato_origem": ({"id": int(origem["id"]),
                                "titulo_id": int(origem["titulo_id"]),
                                "tipo": str(origem["tipo"]),
                                "data_ato": str(origem["data_ato"] or ""),
                                "cancelado": int(origem["cancelado"] or 0),
                                "detalhe_json": origem["detalhe_json"],
                                "origem": origem["origem"], "selo": origem["selo"]}
                               if origem else None),
                "repasses_da_origem": repasses, "titulos": titulos,
                "por_pix": por_pix, "pix": pix}

    def _o_pix(self, bd, parametros, origem, *, travar):
        """O pagamento copiado é por PIX? E qual PIX o sustenta? Só LÊ.

        O número vem do formulário ou, sem ele, do próprio ato copiado. As
        colunas são fixas de propósito: `ultima_consulta` muda a cada leitura do
        extrato, e entrar no «antes» derrubaria a aprovação por nada.
        """
        import protesto_pix as PIX
        detalhe = _ler_json((origem or {}).get("detalhe_json"), {})
        forma = str(detalhe.get("forma_pagamento") or "").strip().upper()
        ligado = (detalhe.get("pix") or {}) if isinstance(detalhe.get("pix"), dict) else {}
        por_pix = forma in PIX.FORMAS_QUE_ESPERAM_O_CREDITO or bool(ligado)
        numero = parametros.get("pix_id") or ligado.get("pix_id")
        if not por_pix or not str(numero or "").isdigit() or not bd.tem_tabela("pt_pix"):
            return por_pix, None
        trava = " FOR UPDATE" if travar else ""
        linha = bd.um(
            f"""SELECT id, titulo_id, situacao, ato_id, valor_centavos, data_pix,
                       credito_id, credito_data, credito_e2eid, e2eid,
                       confirmacao_modo, confirmado_por
                  FROM pt_pix WHERE id = %s{trava}""", (int(numero),))
        return por_pix, (dict(linha) if linha else None)

    def _recusas_do_pix(self, bd, parametros, antes) -> list[str]:
        """PIX SÓ COM O CRÉDITO CONFERIDO, também na cópia (decisão do oficial,
        30/10/2026). E, como em `protesto.lancar_pagamento`, com PIX do título
        ainda esperando o crédito, nenhum outro pagamento entra."""
        import protesto_pix as PIX
        o, pix = antes["ato_origem"], antes.get("pix")
        recusas = []
        if antes.get("por_pix"):
            if not pix:
                recusas.append(
                    f"O pagamento {o['id']} foi por PIX e não tem crédito conferido "
                    "ligado a ele. PIX NÃO É PAGAMENTO ATÉ O CRÉDITO SER CONFERIDO: "
                    "registre o PIX no título, confira o crédito e proponha de novo, "
                    "informando o número do PIX.")
            else:
                try:
                    PIX.para_o_pagamento_de_correcao(
                        bd, pix["id"], titulo_id=parametros["titulo_id"],
                        titulo_de_origem_id=o["titulo_id"])
                except PIX.PixError as erro:
                    recusas.append(str(erro))
                pago = _ler_json(o.get("detalhe_json"), {}).get("valor_pago_centavos")
                if pago not in (None, "") and int(pago) != int(pix["valor_centavos"]):
                    recusas.append(
                        f"O valor pago tem de ser o do crédito conferido: R$ "
                        f"{PIX.reais(int(pix['valor_centavos']))}.")
        try:
            PIX.recusar_se_esperando(bd, parametros["titulo_id"],
                                     "o pagamento de correção",
                                     exceto_pix_id=pix["id"] if pix else None)
        except PIX.PixError as erro:
            recusas.append(str(erro))
        return recusas

    def conferir_pedido(self, bd, parametros, antes):
        from gestor_conferencia import IMPLANTACAO
        recusas, avisos = [], []
        o = antes["ato_origem"]
        destino = str(parametros["titulo_id"])
        if o is None:
            recusas.append(f"O ato {parametros['ato_origem_id']} não existe.")
        elif o["tipo"] not in TIPOS_QUE_SE_COPIAM:
            recusas.append(
                f"O ato {o['id']} é {o['tipo']}: só se copia "
                f"{', '.join(TIPOS_QUE_SE_COPIAM)} — é o que tem precedente. Ato com "
                "livro, folha e selo não se copia.")
        if destino not in antes["titulos"]:
            recusas.append(f"O título {destino} não existe.")
        if recusas:
            return parametros, recusas, avisos
        if o["titulo_id"] == int(destino):
            recusas.append("A cópia vai para OUTRO título; no mesmo título, o ato "
                           "se lança pela ficha, com selo.")
        vivo = [aid for aid, tipo in antes["titulos"][destino]["atos_validos"]
                if tipo == o["tipo"]]
        if vivo:
            recusas.append(f"O título {destino} já tem {o['tipo']} válido (ato "
                           f"{vivo[0]}).")
        repassados = [r for r in antes["repasses_da_origem"] if r[1] != "CANCELADO"]
        if repassados:
            recusas.append(
                f"O pagamento {o['id']} já tem repasse ({repassados[0][1]}): a "
                "cópia pediria outro. O repasse se decide antes.")
        if o["tipo"] == "PAGAMENTO":
            recusas += self._recusas_do_pix(bd, parametros, antes)
        if not o["cancelado"]:
            avisos.append(
                f"O ato {o['id']} continua válido no título {o['titulo_id']}: "
                "se ele está no título errado, proponha também torná-lo sem "
                "efeito — senão o fato fica nos dois.")
        if o["data_ato"][:10] >= IMPLANTACAO:
            avisos.append("A cópia é de depois da implantação: ela entra na lista "
                          "do repasse do Protesto.")
        avisos.append("O ato novo nasce sem estar informado à Central: no título "
                      "da CRA ele entra no próximo retorno; no da CENPROT, no "
                      "próximo XML. E não tem selo, livro nem folha — é cópia, e "
                      "não lavratura.")
        return parametros, recusas, avisos

    def _detalhe(self, o, motivo, numero, pix=None):
        try:
            detalhe = json.loads(o["detalhe_json"] or "{}")
        except (TypeError, ValueError):
            detalhe = {"detalhe_original": o["detalhe_json"]}
        if not isinstance(detalhe, dict):
            detalhe = {"detalhe_original": detalhe}
        detalhe.update({"correcao_de": o["id"], "correcao_de_oficio": numero,
                        "origem_da_correcao": motivo})
        if pix:
            import protesto_pix as PIX
            detalhe.update({"forma_pagamento": "PIX",
                            "valor_pago_centavos": int(pix["valor_centavos"]),
                            "pix": PIX.para_o_detalhe(pix),
                            "data_do_pagamento": PIX.data_do_pagamento(pix)})
        return json.dumps(detalhe, ensure_ascii=False)

    def calcular_depois(self, parametros, antes, *, motivo, numero):
        o = antes["ato_origem"]
        destino = str(parametros["titulo_id"])
        novo = {"titulo_id": int(destino), "tipo": o["tipo"], "data_ato": o["data_ato"],
                "origem": ORIGEM_DO_ATO,
                "origem_chave": f"correcao_de_oficio:{numero or 0}",
                "observacao": (f"Correção de ofício {_numero(numero)}: cópia do ato "
                               f"{o['id']} ({o['tipo']} do título {o['titulo_id']}). "
                               f"{motivo}"),
                "detalhe_json": self._detalhe(o, motivo, numero, antes.get("pix"))}
        titulos = {}
        if parametros["ajustar_situacao"]:
            titulos = _situacao_depois({destino: antes["titulos"][destino]},
                                       mais={destino: [o["tipo"]]})
        return {"ato_novo": novo, "titulos": titulos}

    def alvos(self, parametros, antes):
        return [int(parametros["titulo_id"])], [int(parametros["titulo_id"])]

    def resumo(self, parametros, antes, depois):
        o = antes["ato_origem"]
        frase = (f"Lançar no título {parametros['titulo_id']} um {o['tipo']} de "
                 f"correção, cópia do ato {o['id']} (título {o['titulo_id']}, de "
                 f"{_data_br(o['data_ato'])})")
        if depois.get("titulos"):
            frase += "; situação: " + ", ".join(
                f"{antes['titulos'][tid]['situacao']} → {d['situacao']}"
                for tid, d in sorted(depois["titulos"].items(), key=lambda x: int(x[0])))
        return frase + "."

    def mudancas(self, antes, depois, resultado):
        novo = depois["ato_novo"]
        aid = (resultado or {}).get("ato_novo_id")
        return [{"tabela": "pt_atos", "id": aid, "titulo_id": novo["titulo_id"],
                 "rotulo": f"ato novo ({novo['tipo']})" + (f" {aid}" if aid else ""),
                 "antes": {},
                 "depois": {k: novo[k] for k in ("tipo", "data_ato", "origem",
                                                 "origem_chave", "observacao")}}
                ] + self._mudanca_do_pix(antes, novo, aid) + _mudancas_de_situacao(antes, depois)

    def _mudanca_do_pix(self, antes, novo, aid) -> list[dict]:
        pix = antes.get("pix")
        if not pix:
            return []
        return [{"tabela": "pt_pix", "id": int(pix["id"]), "titulo_id": novo["titulo_id"],
                 "rotulo": f"PIX {pix['id']}",
                 "antes": {"titulo_id": pix["titulo_id"], "ato_id": pix["ato_id"]},
                 "depois": {"titulo_id": novo["titulo_id"], "ato_id": aid}}]

    def executar(self, bd, parametros, antes, depois, contexto):
        import protesto_pix as PIX
        novo = depois["ato_novo"]
        pix = antes.get("pix")
        if antes.get("por_pix"):
            # A TRAVA DE NOVO, COM A LINHA PRESA: o crédito pode ter sido usado
            # entre a proposta e a aprovação.
            try:
                if not pix:
                    raise PIX.PixError("o pagamento é por PIX e não há crédito "
                                       "conferido ligado a ele")
                PIX.para_o_pagamento_de_correcao(
                    bd, pix["id"], titulo_id=novo["titulo_id"],
                    titulo_de_origem_id=antes["ato_origem"]["titulo_id"], prender=True)
            except PIX.PixError as erro:
                raise _Falha(f"a trava do PIX recusou, e nada foi gravado: {erro}") from erro
        ato_id = _inserir_ato(bd, novo, contexto)
        if pix:
            PIX.levar_ao_pagamento_de_correcao(bd, int(pix["id"]),
                                               titulo_id=novo["titulo_id"], ato_id=ato_id)
        return {"ato_novo_id": ato_id,
                "titulos_com_situacao_nova": _trocar_situacoes(bd, antes, depois)}

    def conferir_execucao(self, bd, parametros, antes, depois, resultado):
        novo = depois["ato_novo"]
        r = bd.um("""SELECT titulo_id, tipo, data_ato, origem, cancelado, detalhe_json
                       FROM pt_atos WHERE id = %s""", (resultado["ato_novo_id"],))
        problemas = []
        if not r or int(r["titulo_id"]) != novo["titulo_id"] or r["tipo"] != novo["tipo"] \
                or str(r["data_ato"]) != novo["data_ato"] or r["origem"] != ORIGEM_DO_ATO \
                or int(r["cancelado"] or 0) != 0:
            problemas.append("o ato novo não ficou como o depois dizia")
        elif _ler_json(r["detalhe_json"], {}).get("correcao_de") \
                != antes["ato_origem"]["id"]:
            problemas.append("o ato novo ficou sem o vínculo correcao_de")
        pix = antes.get("pix")
        if pix:
            lido = bd.um("SELECT titulo_id, ato_id FROM pt_pix WHERE id = %s", (int(pix["id"]),))
            if not lido or int(lido["titulo_id"]) != novo["titulo_id"] \
                    or int(lido["ato_id"] or 0) != resultado["ato_novo_id"]:
                problemas.append(f"o PIX {pix['id']} não ficou ligado ao ato novo")
        return problemas + _conferir_situacoes(bd, depois)


# ---------------------------------------------- 5. o título devolvido

#: O ATO QUE SUSTENTA A SITUAÇÃO DEVOLVIDO. Não é lavratura: sem selo, livro nem
#: folha, e fora do retorno e do XML (que têm a lista fechada dos atos deles).
ATO_DA_DEVOLUCAO = "DEVOLUCAO"
#: As situações em que o título pode estar. O PAGO entra pelo caso medido: a carga
#: deixou os títulos 52, 776 e 777 PAGO sem pagamento nenhum. O ato válido é que
#: decide (`ATOS_QUE_IMPEDEM_A_DEVOLUCAO`).
SITUACOES_QUE_SE_DEVOLVEM = ("RECEBIDO", "APONTADO", "INTIMADO", "PAGO")
#: Com um destes válido, o título teve vida: desfaz-se primeiro, em outra proposta.
ATOS_QUE_IMPEDEM_A_DEVOLUCAO = ("PROTESTO", "PAGAMENTO", "DESISTENCIA", "RETIRADA",
                                "CANCELAMENTO")


def _data_iso(valor: Any) -> str | None:
    """`AAAA-MM-DD` ou `DD/MM/AAAA`, como `AAAA-MM-DD`. O resto é None. Só calcula."""
    texto = str(valor or "").strip()
    if re.fullmatch(r"\d{2}/\d{2}/\d{4}", texto):
        texto = f"{texto[6:10]}-{texto[3:5]}-{texto[0:2]}"
    try:
        return date.fromisoformat(texto).isoformat()
    except ValueError:
        return None


class TituloDevolvido(Tipo):
    """Marca o título como DEVOLVIDO — decisão do oficial, 30/10/2026.

    Dois casos, e o motivo diz qual: o título devolvido por irregularidade
    (código 5 da CRA) e a entrada em DUPLICIDADE (o mesmo título apontado duas
    vezes), em que o motivo diz qual é a primeira entrada.

    Lança o ato DEVOLUCAO na data da ocorrência do E-Ofício e troca a situação.
    É ele que sustenta a situação, e tornar esse ato sem efeito é o caminho de
    volta. Um título por proposta: cada um tem a sua data.
    """

    chave = "PT_TITULO_DEVOLVIDO"
    atribuicao = ATRIBUICAO_PROTESTO
    rotulo = "Marcar o título como DEVOLVIDO"
    descricao = ("Título devolvido por irregularidade (código 5 da CRA) ou entrada "
                 "em duplicidade: o motivo diz qual é o caso e, na duplicidade, qual "
                 "é a primeira entrada. Ele sai do fluxo: não vai a protesto, "
                 "intimação, repasse nem XML.")
    alvo_tabela = "pt_titulos"
    campos = (
        ("titulo_id", "O título (número do sistema)", "numero",
         "o número do título no sistema (o da ficha), e não o do papel"),
        ("data_ocorrencia", "A data da ocorrência no E-Ofício", "data", ""),
    )

    def normalizar(self, pedido):
        recusas = []
        ids, ruins = _ids(pedido.get("titulo_id"))
        if ruins or len(ids) != 1:
            recusas.append("Informe UM título, pelo número do sistema.")
        data = _data_iso(pedido.get("data_ocorrencia"))
        if data is None:
            recusas.append("Informe a data da ocorrência no E-Ofício.")
        elif data > date.today().isoformat():
            recusas.append(f"A data da ocorrência ({_data_br(data)}) é futura.")
        return {"titulo_id": ids[0] if len(ids) == 1 else None,
                "data_ocorrencia": data}, recusas

    def ler_antes(self, bd, parametros, *, travar):
        import protesto_pix as PIX
        tid = int(parametros["titulo_id"])
        instrumentos = 0
        if bd.tem_tabela("pt_instrumentos"):
            instrumentos = int(bd.valor(
                "SELECT count(*) FROM pt_instrumentos WHERE titulo_id = %s", (tid,)) or 0)
        ativo = PIX.ativo_do_titulo(bd, tid)
        return {"titulos": _titulos(bd, [tid], travar=travar), "instrumentos": instrumentos,
                "pix_esperando": int(ativo["id"]) if ativo else None}

    def conferir_pedido(self, bd, parametros, antes):
        tid = str(parametros["titulo_id"])
        t = antes["titulos"].get(tid)
        if t is None:
            return parametros, [f"O título {tid} não existe."], []
        recusas, avisos = [], []
        if t["situacao"] == "DEVOLVIDO":
            recusas.append(f"O título {tid} já está DEVOLVIDO.")
        elif t["situacao"] not in SITUACOES_QUE_SE_DEVOLVEM:
            recusas.append(
                f"O título {tid} está {t['situacao']}: só se devolve título em "
                f"{', '.join(SITUACOES_QUE_SE_DEVOLVEM)}. O {t['situacao']} tem caminho "
                "próprio, e não é a devolução.")
        for aid, tipo in t["atos_validos"]:
            if tipo in ATOS_QUE_IMPEDEM_A_DEVOLUCAO:
                recusas.append(
                    f"O título {tid} tem {tipo} válido (ato {aid}): torne-o sem "
                    "efeito antes, em outra proposta, com o motivo dele.")
        if antes["instrumentos"]:
            recusas.append(f"O título {tid} tem instrumento de protesto emitido: "
                           "devolvê-lo não tem precedente nesta casa, e o oficial "
                           "decide fora da fila.")
        if antes["pix_esperando"]:
            recusas.append(f"O título {tid} tem o PIX nº {antes['pix_esperando']} sem "
                           "virar pagamento: resolva o PIX antes de devolver.")
        tipos = [tipo for _aid, tipo in t["atos_validos"]]
        if "INTIMACAO" in tipos:
            avisos.append(f"O título {tid} tem intimação válida: a devolução não a "
                          "desfaz, e ela continua na ficha.")
        sustacoes = [tipo for tipo in tipos if tipo in ("SUSTACAO", "REVOGACAO_SUSTACAO")]
        if sustacoes and sustacoes[-1] == "SUSTACAO":
            avisos.append(f"O título {tid} está sustado: confira a ordem antes de "
                          "aprovar.")
        for r in self._outras_entradas(bd, int(tid)):
            avisos.append(f"Mesmo número e mesmo valor: título {r['id']} ({r['situacao']}, "
                          f"protocolo {r['protocolo'] or '—'}). Na duplicidade, o motivo "
                          "diz qual é a primeira entrada.")
        avisos.append("Esta correção não avisa a Central: o título devolvido não entra "
                      "no retorno à CRA nem no XML da CENPROT.")
        return parametros, recusas, avisos

    def _outras_entradas(self, bd, titulo_id: int) -> list[dict]:
        """As outras linhas com o mesmo número e valor: a ajuda de quem decide
        na duplicidade. Só LÊ, e fica fora do «antes»: a situação da outra
        entrada mudar não invalida esta proposta."""
        return bd.ler(
            """SELECT o.id, o.situacao, o.protocolo
                 FROM pt_titulos t JOIN pt_titulos o
                   ON o.numero_titulo = t.numero_titulo
                  AND o.valor_centavos = t.valor_centavos AND o.id <> t.id
                WHERE t.id = %s ORDER BY o.id LIMIT 5""", (titulo_id,))

    def calcular_depois(self, parametros, antes, *, motivo, numero):
        tid = str(parametros["titulo_id"])
        data = parametros["data_ocorrencia"]
        detalhe = {"data_da_ocorrencia": data, "correcao_de_oficio": numero,
                   "motivo": motivo}
        novo = {"titulo_id": int(tid), "tipo": ATO_DA_DEVOLUCAO, "data_ato": data,
                "origem": ORIGEM_DO_ATO, "origem_chave": f"correcao_de_oficio:{numero or 0}",
                "observacao": (f"Correção de ofício {_numero(numero)}: título devolvido, "
                               f"ocorrência de {_data_br(data)} no E-Ofício. {motivo}"),
                "detalhe_json": json.dumps(detalhe, ensure_ascii=False)}
        return {"ato_novo": novo,
                "titulos": _situacao_depois({tid: antes["titulos"][tid]},
                                            mais={tid: [ATO_DA_DEVOLUCAO]})}

    def alvos(self, parametros, antes):
        return [int(parametros["titulo_id"])], [int(parametros["titulo_id"])]

    def resumo(self, parametros, antes, depois):
        tid = str(parametros["titulo_id"])
        return (f"Marcar o título {tid} como DEVOLVIDO ({antes['titulos'][tid]['situacao']} → "
                f"DEVOLVIDO), ocorrência de {_data_br(parametros['data_ocorrencia'])}.")

    def mudancas(self, antes, depois, resultado):
        novo = depois["ato_novo"]
        aid = (resultado or {}).get("ato_novo_id")
        return [{"tabela": "pt_atos", "id": aid, "titulo_id": novo["titulo_id"],
                 "rotulo": "ato novo (DEVOLUCAO)" + (f" {aid}" if aid else ""),
                 "antes": {},
                 "depois": {k: novo[k] for k in ("tipo", "data_ato", "origem",
                                                 "origem_chave", "observacao")}}
                ] + _mudancas_de_situacao(antes, depois)

    def executar(self, bd, parametros, antes, depois, contexto):
        return {"ato_novo_id": _inserir_ato(bd, depois["ato_novo"], contexto),
                "titulos_com_situacao_nova": _trocar_situacoes(bd, antes, depois)}

    def conferir_execucao(self, bd, parametros, antes, depois, resultado):
        novo = depois["ato_novo"]
        r = bd.um("""SELECT titulo_id, tipo, data_ato, origem, cancelado FROM pt_atos
                      WHERE id = %s""", (resultado["ato_novo_id"],))
        problemas = []
        if not r or int(r["titulo_id"]) != novo["titulo_id"] \
                or r["tipo"] != ATO_DA_DEVOLUCAO or str(r["data_ato"]) != novo["data_ato"] \
                or int(r["cancelado"] or 0) != 0:
            problemas.append("o ato da devolução não ficou como o depois dizia")
        return problemas + _conferir_situacoes(bd, depois)


#: O CATÁLOGO FECHADO. Tipo novo entra aqui, com a atribuição dele.
CATALOGO: dict[str, Tipo] = {t.chave: t for t in (
    AtoSemEfeito(), SituacaoSustentada(), CadastroDoTitulo(), AtoDeCorrecao(),
    TituloDevolvido())}


def tipos_disponiveis() -> list[dict]:
    """O catálogo, para a tela: chave, atribuição, rótulo, descrição e os
    campos do formulário. Só calcula."""
    return [{"chave": t.chave, "atribuicao": t.atribuicao,
             "nome_da_atribuicao": NOME_DA_ATRIBUICAO.get(t.atribuicao, t.atribuicao),
             "rotulo": t.rotulo, "descricao": t.descricao,
             "campos": [{"nome": n, "rotulo": r, "widget": w, "ajuda": a}
                        for n, r, w, a in t.campos]}
            for t in CATALOGO.values()]


def campos_do_cadastro() -> list[dict]:
    """Os campos do tipo 3, com o nome do formulário, para a tela."""
    saida = []
    for tabela, lista in CAMPOS_DO_CADASTRO.items():
        prefixo = PREFIXO_DO_DEVEDOR if tabela == "pt_devedores" else ""
        saida += [{"nome": prefixo + campo, "rotulo": rotulo, "tabela": tabela}
                  for campo, rotulo in lista]
    return saida


def parametros_do_formulario(tipo: Any, form) -> dict:
    """O pedido do formulário da tela, na forma que `propor` recebe."""
    t = CATALOGO.get(str(tipo or ""))
    return t.do_formulario(form) if t else {}


# ================================================================ propor

def _quem_propoe(quem: Any) -> str | None:
    if not quem:
        return "Entre com a sua conta para propor."
    if str(quem.get("role") or "") not in QUEM_PROPOE:
        return ("Propor correção de ofício é do balcão (escrevente, gerente ou "
                "oficial); o seu papel só confere.")
    return None


def propor(con, *, tipo: Any, parametros: Any, motivo: Any, quem: dict | None,
           agora: str, previa: bool = False, agente: Any = None,
           ip: Any = None) -> dict:
    """Prepara a correção e, sem `previa`, grava a PROPOSTA. Não altera nada
    fora da fila: a proposta, a tarefa do oficial e a auditoria dela.

    Devolve {"ok", "recusas", "avisos", "antes", "depois", "linhas", "resumo",
    "id"}. A recusa NÃO é exceção: é a lista de frases, todas de uma vez, que
    a tela (ou o agente, pelo JSON) mostra.
    """
    saida: dict[str, Any] = {"ok": False, "id": None, "recusas": [], "avisos": [],
                             "antes": None, "depois": None, "linhas": [],
                             "resumo": "", "tipo": str(tipo or "")}
    recusa = _quem_propoe(quem)
    if recusa:
        saida["recusas"] = [recusa]
        return saida
    t = CATALOGO.get(str(tipo or ""))
    if t is None:
        saida["recusas"] = [f"O tipo «{tipo}» não está no catálogo. Os tipos são: "
                            + ", ".join(CATALOGO) + "."]
        return saida
    motivo = _corrido(motivo)
    recusas = []
    if _letras(motivo) < MINIMO_DE_LETRAS_DO_MOTIVO:
        recusas.append(f"Escreva o motivo — o que aconteceu e de onde se sabe —, "
                       f"com pelo menos {MINIMO_DE_LETRAS_DO_MOTIVO} letras.")
    params, recusas_do_pedido = t.normalizar(parametros if isinstance(parametros, dict) else {})
    recusas += recusas_do_pedido
    if recusas:
        saida["recusas"] = recusas
        return saida
    bd = banco(con)
    antes = t.ler_antes(bd, params, travar=False)
    params, recusas, avisos = t.conferir_pedido(bd, params, antes)
    saida["avisos"] = avisos
    if recusas:
        saida["recusas"] = recusas
        return saida
    # O «antes» é o das linhas que vão mudar: o tipo pode ter estreitado o
    # pedido (o que já estava certo sai), e a aprovação relê exatamente isto.
    antes = t.ler_antes(bd, params, travar=False)
    depois = t.calcular_depois(params, antes, motivo=motivo, numero=None)
    alvo_ids, titulo_ids = t.alvos(params, antes)
    saida.update({"antes": antes, "depois": depois, "resumo": t.resumo(params, antes, depois),
                  "linhas": t.mudancas(antes, depois, None)[:LIMITE_DAS_LINHAS],
                  "titulo_ids": titulo_ids})
    if previa:
        saida["ok"] = True
        return saida
    ident = IDR.identidade(bd, quem["id"], agente=agente)
    novo = bd.escrever(
        """INSERT INTO correcoes_de_oficio (atribuicao, tipo, alvo_tabela, alvo_ids,
               titulo_ids, parametros_json, antes_json, depois_json, avisos_json,
               resumo, motivo, situacao, proposta_em, proposta_por_id, proposta_por,
               agente, a_mando_de)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           RETURNING id""",
        (t.atribuicao, t.chave, t.alvo_tabela, _json(alvo_ids), _json(titulo_ids),
         _json(params), _json(antes), _json(depois), _json(avisos), saida["resumo"],
         motivo, PROPOSTA, agora, int(quem["id"]), quem.get("username"),
         ident["agente"], ident["a_mando_de"]))
    numero = int(novo[0]["id"])
    # O NÚMERO DA PROPOSTA VAI NO «DEPOIS» (o motivo no ato, a observação do
    # ato novo): do ato se acha a proposta. Só se sabe depois do INSERT.
    depois = t.calcular_depois(params, antes, motivo=motivo, numero=numero)
    tarefa = _abrir_tarefa(bd, numero, t, saida["resumo"], motivo, quem, ident, agora)
    bd.escrever("UPDATE correcoes_de_oficio SET depois_json = %s, tarefa_id = %s "
                "WHERE id = %s", (_json(depois), tarefa, numero))
    IDR.registrar(bd, ts=agora, user_id=int(quem["id"]), username=quem.get("username"),
                  action=ACAO_PROPOSTA, entity_type=ENTIDADE, entity_id=numero,
                  details={"tipo": t.chave, "resumo": saida["resumo"], "motivo": motivo,
                           "alvo_tabela": t.alvo_tabela, "alvo_ids": alvo_ids[:200],
                           "titulo_ids": titulo_ids[:200], "tarefa_id": tarefa},
                  ip_address=ip, agente=agente)
    saida.update({"ok": True, "id": numero, "depois": depois,
                  "linhas": t.mudancas(antes, depois, None)[:LIMITE_DAS_LINHAS]})
    return saida


def _abrir_tarefa(bd, numero: int, t: Tipo, resumo: str, motivo: str, quem: dict,
                  ident: dict, agora: str) -> int | None:
    """A proposta vira tarefa do oficial — SEM E-MAIL (ordem de 28/10/2026:
    nada de e-mail por evento dos robôs). ESCREVE."""
    import oficial_pauta as OP
    dono = OP.dono_da_mesa(bd)
    quem_propos = quem.get("full_name") or quem.get("username") or "?"
    if ident.get("agente"):
        quem_propos = IDR.frase(ident["agente"], ident["a_mando_de"]) or quem_propos
    descricao = (f"Correção de ofício nº {numero} — {t.rotulo}.\n\n{resumo}\n\n"
                 f"Motivo: {motivo}\n\nProposta por: {quem_propos}.\n\n"
                 "Decida em Administrativo → Correções de ofício "
                 f"(/administrativo/correcoes-de-oficio/{numero}): aprovar, com a "
                 "afirmação expressa, ou recusar, com o motivo. A tarefa fecha "
                 "sozinha com a decisão.")
    hoje = str(agora)[:10]
    novo = bd.escrever(
        """INSERT INTO tasks (source_type, source_ref, title, description, sector,
               system_name, priority, status, start_date, due_date,
               assigned_user_id, evidence_required, created_by, created_at,
               updated_at)
           VALUES (%s, %s, %s, %s, %s, 'Correções de ofício', 'ALTA', 'ABERTA',
                   %s, %s, %s, 0, %s, %s, %s)
           RETURNING id""",
        (ORIGEM_DA_TAREFA, f"{ORIGEM_DA_TAREFA}:{numero}",
         f"Correção de ofício nº {numero}: {t.rotulo}"[:200], descricao,
         NOME_DA_ATRIBUICAO.get(t.atribuicao, t.atribuicao), hoje, hoje, dono,
         int(quem["id"]), agora, agora))
    tarefa = int(novo[0]["id"])
    bd.escrever("""INSERT INTO task_history (task_id, ts, user_id, action, new_value, note)
                   VALUES (%s, %s, %s, 'CRIADA', 'ABERTA', %s)""",
                (tarefa, agora, int(quem["id"]),
                 f"Aberta pela fila de correções de ofício (proposta nº {numero})."))
    return tarefa


def _fechar_tarefa(bd, linha: dict, quem: dict, agora: str, nota: str) -> None:
    if not linha.get("tarefa_id"):
        return
    feito = bd.escrever(
        """UPDATE tasks SET status = 'CONCLUIDA', completed_at = %s, completed_by = %s,
               updated_at = %s
            WHERE id = %s AND status NOT IN ('CONCLUIDA', 'CANCELADA') RETURNING id""",
        (agora, int(quem["id"]), agora, int(linha["tarefa_id"])))
    if feito:
        bd.escrever("""INSERT INTO task_history (task_id, ts, user_id, action, old_value,
                           new_value, note)
                       VALUES (%s, %s, %s, 'ALTEROU_STATUS', 'ABERTA', 'CONCLUIDA', %s)""",
                    (int(linha["tarefa_id"]), agora, int(quem["id"]), nota))


# ================================================================ decidir

def _quem_aprova(quem: Any) -> str | None:
    """Só gente, e só o oficial. Robô nunca — com o papel que tiver."""
    if not quem:
        return "Entre com a sua conta para decidir."
    try:
        robo = int(quem.get("eh_robo") or 0) == 1
    except (TypeError, ValueError):
        robo = True
    if robo:
        return ("Conta de robô não decide correção de ofício: quem aprova e quem "
                "recusa é o oficial.")
    if str(quem.get("role") or "") not in QUEM_APROVA:
        return ("Só o oficial (ADMIN) decide correção de ofício. Quem propõe é o "
                "balcão; quem aprova responde pela serventia.")
    return None


def _afirmacao(afirmo: Any, afirmacao: Any) -> tuple[str | None, str | None]:
    """O contrato comum (`protesto_selo_previo.validar_afirmacao`): (texto,
    recusa). Sem afirmação nenhuma, também é recusa — aqui ela é a condição."""
    import protesto_selo_previo as PSELO
    try:
        texto = PSELO.validar_afirmacao(afirmo, afirmacao)
    except PSELO.SituacaoError as erro:
        return None, str(erro)
    if texto is None:
        return None, ("A aprovação exige a afirmação expressa: marque «Afirmo» e "
                      "escreva por quê, com pelo menos "
                      f"{PSELO.MINIMO_DE_LETRAS_DA_AFIRMACAO} letras, começando por "
                      f"«{PSELO.MODELO_DA_AFIRMACAO}».")
    return texto, None


def _presa(bd, correcao_id: Any) -> dict | None:
    if not str(correcao_id or "").isdigit():
        return None
    return bd.um("SELECT * FROM correcoes_de_oficio WHERE id = %s FOR UPDATE",
                 (int(correcao_id),))


def _gravar_decisao(bd, linha: dict, situacao: str, quem: dict, agora: str, *,
                    afirmacao: str | None = None, motivo_da_recusa: str | None = None,
                    resultado: dict | None = None, falha: str | None = None) -> None:
    feito = bd.escrever(
        """UPDATE correcoes_de_oficio
              SET situacao = %s, decidida_em = %s, decidida_por_id = %s,
                  decidida_por = %s, afirmacao = %s, motivo_da_recusa = %s,
                  resultado_json = %s, falha = %s
            WHERE id = %s AND situacao = %s RETURNING id""",
        (situacao, agora, int(quem["id"]), quem.get("username"), afirmacao,
         motivo_da_recusa, _json(resultado) if resultado is not None else None,
         falha, int(linha["id"]), PROPOSTA))
    if not feito:
        raise _Falha("a proposta já tinha sido decidida")


def aprovar(con, correcao_id: Any, *, aprovador: dict | None, afirmo: Any,
            afirmacao: Any, agora: str, ip: Any = None) -> dict:
    """O oficial aprova, e o SERVIDOR executa — nesta transação. ESCREVE.

    1. quem aprova é ADMIN e é gente; a afirmação expressa cumpre o contrato.
       Faltando, nada muda: a proposta continua PROPOSTA;
    2. a proposta é presa (FOR UPDATE) e tem de estar PROPOSTA;
    3. o «antes» é relido do banco, com as linhas presas, e comparado com o
       guardado. Mudou: nada se executa, e a proposta fica FALHOU dizendo o
       quê;
    4. a execução e a conferência rodam num SAVEPOINT: a conferência que não
       fecha desfaz a execução inteira, e a proposta fica FALHOU;
    5. executada, grava a auditoria (`CORRECAO_DE_OFICIO_EXECUTADA` por linha
       tocada, e a `AFIRMACAO_EXPRESSA`) e fecha a tarefa.

    Devolve {"ok", "situacao", "recusa" | "falha", "resultado"}. Recusa
    (passo 1 e 2) e falha (3 e 4) não são exceção: a falha fica GRAVADA, e a
    transação de quem chama tem de ser confirmada.
    """
    recusa = _quem_aprova(aprovador)
    if recusa:
        return {"ok": False, "situacao": None, "recusa": recusa}
    texto, recusa = _afirmacao(afirmo, afirmacao)
    if recusa:
        return {"ok": False, "situacao": None, "recusa": recusa}
    bd = banco(con)
    linha = _presa(bd, correcao_id)
    if linha is None:
        return {"ok": False, "situacao": None,
                "recusa": f"A proposta {correcao_id} não existe."}
    if linha["situacao"] != PROPOSTA:
        return {"ok": False, "situacao": linha["situacao"],
                "recusa": f"A proposta {linha['id']} já foi decidida "
                          f"({linha['situacao']})."}
    t = CATALOGO.get(linha["tipo"])
    params = _ler_json(linha["parametros_json"], {})
    antes = _ler_json(linha["antes_json"], {})
    depois = _ler_json(linha["depois_json"], {})
    nome = aprovador.get("full_name") or aprovador.get("username") or "oficial"

    def falhar(frase: str) -> dict:
        _gravar_decisao(bd, linha, FALHOU, aprovador, agora, afirmacao=texto, falha=frase)
        IDR.registrar(bd, ts=agora, user_id=int(aprovador["id"]),
                      username=aprovador.get("username"), action=ACAO_FALHOU,
                      entity_type=ENTIDADE, entity_id=int(linha["id"]),
                      details={"tipo": linha["tipo"], "falha": frase,
                               "afirmacao": texto}, ip_address=ip)
        _fechar_tarefa(bd, linha, aprovador, agora,
                       f"A correção de ofício nº {linha['id']} falhou: {frase}")
        return {"ok": False, "situacao": FALHOU, "falha": frase}

    if t is None:
        return falhar(f"o tipo {linha['tipo']} saiu do catálogo — nada foi executado")
    agora_lido = t.ler_antes(bd, params, travar=True)
    mudou = _diferencas(antes, agora_lido)
    if mudou:
        return falhar("o «antes» mudou entre a proposta e a aprovação, e nada foi "
                      "executado — " + "; ".join(mudou[:10])
                      + (f" (e mais {len(mudou) - 10})" if len(mudou) > 10 else "")
                      + ". Confira e proponha de novo.")
    contexto = {"numero": int(linha["id"]), "quem": nome, "agora": agora}
    try:
        with bd.ponto_de_retorno("correcao_de_oficio"):
            resultado = t.executar(bd, params, antes, depois, contexto)
            problemas = t.conferir_execucao(bd, params, antes, depois, resultado)
            if problemas:
                raise _Falha("a conferência depois de executar não fechou, e nada "
                             "ficou gravado: " + "; ".join(problemas[:10]))
    except _Falha as erro:
        return falhar(erro.frase)
    except ERROS_DO_BANCO as erro:
        return falhar(f"o banco recusou a execução, e nada ficou gravado "
                      f"({type(erro).__name__}: {str(erro)[:300]})")
    _gravar_decisao(bd, linha, APROVADA_EXECUTADA, aprovador, agora,
                    afirmacao=texto, resultado=resultado)
    for m in t.mudancas(antes, depois, resultado):
        IDR.registrar(bd, ts=agora, user_id=int(aprovador["id"]),
                      username=aprovador.get("username"), action=ACAO_EXECUTADA,
                      entity_type=m["tabela"], entity_id=m["id"],
                      details={"correcao_de_oficio": int(linha["id"]),
                               "tipo": linha["tipo"], "antes": m["antes"],
                               "depois": m["depois"], "motivo": linha["motivo"]},
                      ip_address=ip)
    IDR.registrar(bd, ts=agora, user_id=int(aprovador["id"]),
                  username=aprovador.get("username"), action=ACAO_DA_AFIRMACAO,
                  entity_type=ENTIDADE, entity_id=int(linha["id"]),
                  details={"regra": REGRA_DA_AFIRMACAO, "afirmacao": texto,
                           "o_que_faltava": (f"a decisão do oficial sobre a correção "
                                             f"de ofício nº {linha['id']}: "
                                             f"{linha['resumo']}")},
                  ip_address=ip)
    _fechar_tarefa(bd, linha, aprovador, agora,
                   f"Correção de ofício nº {linha['id']} aprovada e executada.")
    return {"ok": True, "situacao": APROVADA_EXECUTADA, "resultado": resultado}


def recusar(con, correcao_id: Any, *, aprovador: dict | None, motivo: Any,
            agora: str, ip: Any = None) -> dict:
    """O oficial recusa, com o motivo. A proposta fica no histórico. ESCREVE
    (só a fila, a tarefa e a auditoria)."""
    recusa = _quem_aprova(aprovador)
    if recusa:
        return {"ok": False, "recusa": recusa}
    motivo = _corrido(motivo)
    if _letras(motivo) < MINIMO_DE_LETRAS_DA_RECUSA:
        return {"ok": False, "recusa": f"Diga por que recusa, com pelo menos "
                                       f"{MINIMO_DE_LETRAS_DA_RECUSA} letras."}
    bd = banco(con)
    linha = _presa(bd, correcao_id)
    if linha is None:
        return {"ok": False, "recusa": f"A proposta {correcao_id} não existe."}
    if linha["situacao"] != PROPOSTA:
        return {"ok": False, "recusa": f"A proposta {linha['id']} já foi decidida "
                                       f"({linha['situacao']})."}
    _gravar_decisao(bd, linha, RECUSADA, aprovador, agora, motivo_da_recusa=motivo)
    IDR.registrar(bd, ts=agora, user_id=int(aprovador["id"]),
                  username=aprovador.get("username"), action=ACAO_RECUSADA,
                  entity_type=ENTIDADE, entity_id=int(linha["id"]),
                  details={"tipo": linha["tipo"], "motivo": motivo}, ip_address=ip)
    _fechar_tarefa(bd, linha, aprovador, agora,
                   f"Correção de ofício nº {linha['id']} recusada: {motivo}")
    return {"ok": True, "situacao": RECUSADA}


# ================================================================ ler

def _da_linha(linha: dict) -> dict:
    d = dict(linha)
    t = CATALOGO.get(d["tipo"])
    d["rotulo_do_tipo"] = t.rotulo if t else d["tipo"]
    d["nome_da_atribuicao"] = NOME_DA_ATRIBUICAO.get(d["atribuicao"], d["atribuicao"])
    d["rotulo_da_situacao"] = ROTULO_DA_SITUACAO.get(d["situacao"], d["situacao"])
    d["frase_do_agente"] = IDR.frase(d.get("agente"), d.get("a_mando_de"))
    return d


def atribuicao_do_filtro(valor: Any) -> str | None:
    """A atribuição do filtro da tela, se é uma que o catálogo conhece; senão
    nenhuma (todas). Só calcula."""
    texto = str(valor or "").strip().upper()
    return texto if texto in NOME_DA_ATRIBUICAO else None


def listar(con, *, situacao: Any = PROPOSTA, atribuicao: Any = None,
           limite: int = LIMITE_DA_LISTA) -> dict:
    """As propostas de uma aba — de todas as atribuições, ou de uma —, da mais
    nova para a mais antiga. Só LÊ."""
    situacao = situacao if situacao in SITUACOES else PROPOSTA
    atribuicao = atribuicao_do_filtro(atribuicao)
    filtro, args = "", [situacao]
    if atribuicao:
        filtro, args = " AND atribuicao = %s", args + [atribuicao]
    linhas = banco(con).ler(
        f"""SELECT id, atribuicao, tipo, resumo, motivo, situacao, proposta_em,
                   proposta_por, agente, a_mando_de, decidida_em, decidida_por,
                   falha, motivo_da_recusa, titulo_ids
              FROM correcoes_de_oficio WHERE situacao = %s{filtro}
             ORDER BY id DESC LIMIT %s""", args + [int(limite) + 1])
    return {"situacao": situacao, "atribuicao": atribuicao,
            "cortado": len(linhas) > limite,
            "linhas": [_da_linha(r) for r in linhas[:limite]]}


def contar_por_situacao(con, *, atribuicao: Any = None) -> dict[str, int]:
    """Quantas propostas em cada aba. Só LÊ."""
    atribuicao = atribuicao_do_filtro(atribuicao)
    filtro, args = "", []
    if atribuicao:
        filtro, args = " WHERE atribuicao = %s", [atribuicao]
    contagem = dict.fromkeys(SITUACOES, 0)
    for r in banco(con).ler(f"SELECT situacao, count(*) AS n FROM correcoes_de_oficio"
                            f"{filtro} GROUP BY situacao", args):
        contagem[r["situacao"]] = int(r["n"])
    return contagem


def contar(con) -> int | None:
    """Quantas propostas esperam o oficial — o contador do painel. `None`
    sem a tabela (o zero medido e o zero por engano são coisas diferentes)."""
    bd = banco(con)
    if not bd.tem_tabela(ENTIDADE):
        return None
    return int(bd.valor("SELECT count(*) FROM correcoes_de_oficio WHERE situacao = %s",
                        (PROPOSTA,)) or 0)


def uma(con, correcao_id: Any) -> dict | None:
    """A proposta inteira, para a ficha: o pedido, o antes, o depois, as
    linhas «antes → depois», os avisos e a decisão. Só LÊ."""
    if not str(correcao_id or "").isdigit():
        return None
    bd = banco(con)
    linha = bd.um("SELECT * FROM correcoes_de_oficio WHERE id = %s", (int(correcao_id),))
    if linha is None:
        return None
    d = _da_linha(linha)
    for coluna, padrao in (("parametros_json", {}), ("antes_json", {}),
                           ("depois_json", {}), ("avisos_json", []),
                           ("resultado_json", {}), ("alvo_ids", []), ("titulo_ids", [])):
        d[coluna.removesuffix("_json")] = _ler_json(d.get(coluna), padrao)
    t = CATALOGO.get(d["tipo"])
    linhas = []
    if t is not None:
        try:
            linhas = t.mudancas(d["antes"], d["depois"], d["resultado"] or None)
        except (KeyError, TypeError, ValueError):
            linhas = []
    d["total_de_linhas"] = len(linhas)
    d["linhas"] = linhas[:LIMITE_DAS_LINHAS]
    d["rotulos"] = _rotulos_dos_titulos(bd, d["titulo_ids"][:LIMITE_DAS_LINHAS])
    return d


def propostas_do_titulo(con, titulo_id: int, *, tipo: str | None = None) -> list[dict]:
    """As propostas do Protesto que esperam o oficial e tocam este título, para
    a ficha e para o botão não propor duas vezes o mesmo. Só LÊ."""
    bd = banco(con)
    if not bd.tem_tabela(ENTIDADE):
        return []
    saida = []
    for p in bd.ler("""SELECT id, tipo, resumo, proposta_em, proposta_por, titulo_ids
                         FROM correcoes_de_oficio
                        WHERE situacao = %s AND atribuicao = %s ORDER BY id""",
                    (PROPOSTA, ATRIBUICAO_PROTESTO)):
        if int(titulo_id) in _ler_json(p["titulo_ids"], []) \
                and (tipo is None or p["tipo"] == tipo):
            saida.append(dict(p))
    return saida


def pendentes(con, *, limite: int = LIMITE_DAS_PENDENCIAS) -> list[dict]:
    """AS PROPOSTAS DO PROTESTO QUE ESPERAM O OFICIAL, uma linha por título —
    para o roteiro do dia. Só LÊ.

    O contrato é o dos outros ganchos do roteiro (`protesto_roteiro.GANCHOS`):
    cada linha traz `titulo_id`, `numero_titulo`, `protocolo` e `explicacao`
    (a frase pronta), e mais `correcao_id` e `tipo`. A proposta em lote
    entra com um título por linha, até o teto.
    """
    bd = banco(con)
    if not bd.tem_tabela(ENTIDADE):
        return []
    propostas = bd.ler(
        """SELECT id, tipo, resumo, proposta_em, proposta_por, agente, a_mando_de,
                  titulo_ids
             FROM correcoes_de_oficio
            WHERE situacao = %s AND atribuicao = %s ORDER BY id""",
        (PROPOSTA, ATRIBUICAO_PROTESTO))
    pares = []
    for p in propostas:
        for tid in _ler_json(p["titulo_ids"], []):
            if str(tid).isdigit():
                pares.append((p, int(tid)))
            if len(pares) >= limite:
                break
        if len(pares) >= limite:
            break
    rotulos = _rotulos_dos_titulos(bd, sorted({tid for _p, tid in pares}))
    saida = []
    for p, tid in pares:
        t = CATALOGO.get(p["tipo"])
        quem = IDR.frase(p["agente"], p["a_mando_de"]) or (p["proposta_por"] or "?")
        r = rotulos.get(str(tid), {})
        saida.append({
            "titulo_id": tid, "numero_titulo": r.get("numero_titulo"),
            "protocolo": r.get("protocolo"), "correcao_id": int(p["id"]),
            "tipo": p["tipo"],
            "explicacao": (f"Correção de ofício nº {p['id']} "
                           f"({t.rotulo if t else p['tipo']}), proposta em "
                           f"{_data_br(p['proposta_em'])} por {quem}: "
                           f"{p['resumo']} Espera a decisão do oficial em "
                           "Administrativo → Correções de ofício.")})
    return saida
