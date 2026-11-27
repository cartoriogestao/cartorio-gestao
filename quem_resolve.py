"""QUEM ESTÁ RESOLVENDO — a marca que impede duas pessoas de fazer o mesmo trabalho.

    «marcar quem está resolvendo cada problema na Checklist do dia e nos
    Projetos, para duas pessoas não fazerem o mesmo trabalho»
                                                — o titular, 26/11/2026

UM MECANISMO SÓ, TRÊS TIPOS DE PROBLEMA
    ROTINA   o vencimento de um item da rotina da serventia (`rotina_da_casa`);
             chave «{rotina_id}:{referência nominal}» — a ocorrência do dia, e
             não o item: amanhã é outra.
    ACHADO   um achado aberto do gestor na Checklist do dia; chave =
             `ge_achados.chave`, a mesma que o «Retirar» usa e que o gestor
             reconhece de uma rodada para a outra.
    FASE     uma fase de um projeto (`dev_projetos`); chave = o id da fase.

UMA PESSOA POR PROBLEMA, E O BANCO GARANTE
    `ge_quem_resolve` tem um índice único parcial em (tipo, chave) onde `ate`
    é nulo: duas marcas abertas para o mesmo problema não cabem, nem quando
    dois cliques chegam juntos. A segunda pessoa é recusada com o nome de
    quem já está e desde quando; o oficial e o gerente podem «assumir no
    lugar» (`tomar=True`), e a marca de antes fecha como TOMADO.

COMO A MARCA FECHA (`ate`, `fim_por`, `motivo_fim`)
    LARGOU   quem estava resolvendo desistiu (`largar`);
    TOMADO   o oficial ou o gerente assumiu no lugar;
    CONCLUIU o problema acabou: o «Feito» da rotina daquela referência, a
             fase CONCLUIDA ou DISPENSADA (`encerrar`, chamado por quem
             conclui, na mesma transação).
    O achado que o gestor fecha some da lista de abertos, e a marca dele some
    junto: a tela só pergunta pelos abertos (limpeza preguiçosa, sem escrever
    no GET). Nada se apaga: a linha fechada fica, com quem e quando.

NÃO É BAIXA, NEM TAREFA
    A marca diz quem está cuidando — e só. Ela não resolve achado, não marca
    «feito», não muda a cor do semáforo nem a situação da fase.

QUEM PODE (a régua das telas; o domínio recusa por dever o que não é pessoa)
    ROTINA: quem pode marcar o «feito» do item (`rotina_da_casa.pode_marcar`).
    ACHADO e FASE: o oficial e o gerente (o TI passa como o oficial).
    Assumir no lugar: o oficial e o gerente. O auditor e a conta de robô nunca.

SÓ DOMÍNIO
    Nada aqui conhece o Flask. A rota (`quem_resolve_web`) confere o papel,
    grava a auditoria (QUEM_RESOLVE_ASSUMIU, _LARGOU, _TOMOU, _CONCLUIU) e
    volta para a tela de onde veio.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Iterable

from bd_nativo import ERROS_DO_BANCO, banco

TABELA = "ge_quem_resolve"

ROTINA, ACHADO, FASE = "ROTINA", "ACHADO", "FASE"
TIPOS = (ROTINA, ACHADO, FASE)
ROTULO_DO_TIPO = {ROTINA: "rotina do dia", ACHADO: "achado da checklist", FASE: "fase do projeto"}

LARGOU, CONCLUIU, TOMADO = "LARGOU", "CONCLUIU", "TOMADO"
MOTIVOS_FIM = (LARGOU, CONCLUIU, TOMADO)

#: Quem assume achado e fase, e quem assume no lugar de outra pessoa.
QUEM_ASSUME_ACHADO_E_FASE = ("ADMIN", "MANAGER")
QUEM_TOMA = ("ADMIN", "MANAGER")
#: Quem nunca assume (confere e não faz).
QUEM_NUNCA = ("AUDITOR",)

NOTA_MAXIMA = 200
CHAVE_MAXIMA = 200


class QuemResolveError(ValueError):
    """A marca que não se grava, com a frase pronta para a tela."""


def _agora(agora: datetime | str | None) -> datetime:
    if isinstance(agora, datetime):
        return agora
    if isinstance(agora, str) and agora.strip():
        try:
            return datetime.fromisoformat(agora.strip()[:19])
        except ValueError:
            pass
    return datetime.now()


def _texto_do_momento(agora: datetime) -> str:
    return agora.isoformat(timespec="seconds")


def chave_da_rotina(rotina_id: int, referencia: str) -> str:
    """A chave de um vencimento da rotina: o item e a data nominal. Só calcula."""
    return f"{int(rotina_id)}:{str(referencia or '')[:10]}"


def _conferir(tipo: str, chave: str) -> tuple[str, str]:
    tipo = str(tipo or "").strip().upper()
    if tipo not in TIPOS:
        raise QuemResolveError("Tipo de problema desconhecido.")
    chave = str(chave or "").strip()
    if not chave or len(chave) > CHAVE_MAXIMA:
        raise QuemResolveError("Problema desconhecido.")
    return tipo, chave


def _pessoa_que_resolve(bd, usuario_id: Any) -> dict:
    """A conta que assume: existe, está ativa, é pessoa e não é auditor."""
    try:
        uid = int(usuario_id)
    except (TypeError, ValueError):
        raise QuemResolveError("Entre com a sua conta para assumir.") from None
    linha = bd.um("SELECT id, full_name, role, active, COALESCE(eh_robo, 0) AS eh_robo "
                  "FROM users WHERE id = %s", (uid,))
    if not linha or not int(linha["active"] or 0):
        raise QuemResolveError("Conta inexistente ou inativa: não assume problema.")
    if int(linha["eh_robo"] or 0):
        raise QuemResolveError("Conta de robô não assume problema: a marca é de uma pessoa.")
    if str(linha["role"] or "").upper() in QUEM_NUNCA:
        raise QuemResolveError("O auditor confere e não assume problema.")
    return linha


def _ativo(bd, tipo: str, chave: str) -> dict | None:
    return bd.um(f"SELECT id, tipo, chave, usuario_id, por, desde, nota FROM {TABELA} "
                 "WHERE tipo = %s AND chave = %s AND ate IS NULL", (tipo, chave))


def _dia_e_hora(texto: str) -> str:
    bruto = str(texto or "")
    return f"{bruto[8:10]}/{bruto[5:7]} às {bruto[11:16]}" if len(bruto) >= 16 else bruto


def _fechar(bd, linha: dict, *, por: str, motivo: str, agora: datetime) -> dict:
    bd.escrever(f"UPDATE {TABELA} SET ate = %s, fim_por = %s, motivo_fim = %s "
                "WHERE id = %s AND ate IS NULL",
                (_texto_do_momento(agora), str(por or "").strip() or "?", motivo, int(linha["id"])))
    return {**dict(linha), "ate": _texto_do_momento(agora), "fim_por": por, "motivo_fim": motivo}


def assumir(con, tipo: str, chave: str, *, usuario_id: int, por: str, nota: str = "",
            tomar: bool = False, agora: datetime | str | None = None) -> dict:
    """Marca que esta pessoa está resolvendo o problema. ESCREVE.

    Devolve {gravou, id, tomado_de}. Se outra pessoa já o tem e `tomar` é
    False, recusa dizendo quem e desde quando; com `tomar=True` (o oficial ou
    o gerente — a rota confere), a marca de antes fecha como TOMADO. Se a
    própria pessoa já o tem, nada muda (`gravou=False`). A disputa de dois
    cliques juntos o índice único decide: o segundo é recusado.
    """
    tipo, chave = _conferir(tipo, chave)
    agora = _agora(agora)
    bd = banco(con)
    pessoa = _pessoa_que_resolve(bd, usuario_id)
    texto = " ".join(str(nota or "").split())
    if len(texto) > NOTA_MAXIMA:
        raise QuemResolveError(f"A nota é curta: até {NOTA_MAXIMA} letras.")
    por = str(por or "").strip() or pessoa["full_name"]
    atual = _ativo(bd, tipo, chave)
    tomado = None
    if atual:
        if int(atual["usuario_id"]) == int(pessoa["id"]):
            return {"gravou": False, "id": int(atual["id"]), "tomado_de": None, "ja_era_seu": True}
        if not tomar:
            raise QuemResolveError(
                f"{atual['por']} já está resolvendo isto desde {_dia_e_hora(atual['desde'])}. "
                "Fale com quem está, ou peça ao oficial ou ao gerente para assumir no lugar.")
        tomado = _fechar(bd, atual, por=por, motivo=TOMADO, agora=agora)
    try:
        with bd.ponto_de_retorno("quem_resolve_assumir"):
            novo = bd.escrever(
                f"INSERT INTO {TABELA} (tipo, chave, usuario_id, por, desde, nota) "
                "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                (tipo, chave, int(pessoa["id"]), por, _texto_do_momento(agora), texto))
    except ERROS_DO_BANCO as erro:                         # a disputa vira frase
        quem = _ativo(bd, tipo, chave)
        if quem:
            raise QuemResolveError(
                f"{quem['por']} acabou de assumir isto ({_dia_e_hora(quem['desde'])}). "
                "Fale com quem está.") from erro
        raise
    return {"gravou": True, "id": int(novo[0]["id"]), "tomado_de": tomado, "ja_era_seu": False}


def largar(con, tipo: str, chave: str, *, usuario_id: int, por: str, motivo: str = LARGOU,
           agora: datetime | str | None = None) -> dict | None:
    """A pessoa deixa de resolver o problema. ESCREVE. Devolve a marca fechada,
    ou None se não havia. Só quem está resolvendo larga."""
    tipo, chave = _conferir(tipo, chave)
    motivo = str(motivo or "").strip().upper()
    if motivo not in MOTIVOS_FIM:
        raise QuemResolveError("Motivo do fim desconhecido.")
    bd = banco(con)
    if not bd.tem_tabela(TABELA):
        return None
    atual = _ativo(bd, tipo, chave)
    if not atual:
        return None
    if str(atual["usuario_id"]) != str(usuario_id):
        raise QuemResolveError(
            f"Quem larga é quem está resolvendo ({atual['por']}). O oficial ou o gerente "
            "podem assumir no lugar.")
    return _fechar(bd, atual, por=por, motivo=motivo, agora=_agora(agora))


def encerrar(con, tipo: str, chave: str, *, por: str,
             agora: datetime | str | None = None) -> dict | None:
    """O problema acabou (o «Feito», a fase concluída): fecha a marca como
    CONCLUIU, de quem quer que seja. ESCREVE. Devolve a marca fechada, ou None.
    No banco sem a tabela, não faz nada."""
    tipo, chave = _conferir(tipo, chave)
    bd = banco(con)
    if not bd.tem_tabela(TABELA):
        return None
    atual = _ativo(bd, tipo, chave)
    if not atual:
        return None
    return _fechar(bd, atual, por=por, motivo=CONCLUIU, agora=_agora(agora))


def ativos(con, tipo: str, chaves: Iterable[str], *,
           agora: datetime | str | None = None) -> dict[str, dict]:
    """Quem está resolvendo cada problema: {chave: {usuario_id, por, desde,
    nota, ha_dias, rotulo}}. Só as chaves pedidas — a tela pergunta pelos
    abertos, e o que não está aberto não aparece. SÓ LÊ; sem a tabela, {}."""
    tipo = str(tipo or "").strip().upper()
    chaves = sorted({str(c) for c in chaves if str(c or "").strip()})
    bd = banco(con)
    if not chaves or tipo not in TIPOS or not bd.tem_tabela(TABELA):
        return {}
    hoje = _agora(agora).date()
    saida = {}
    for r in bd.ler(f"SELECT chave, usuario_id, por, desde, nota FROM {TABELA} "
                    "WHERE tipo = %s AND ate IS NULL AND chave = ANY(%s)", (tipo, chaves)):
        desde = str(r["desde"])
        try:
            dia = date.fromisoformat(desde[:10])
        except ValueError:
            dia = hoje
        ha_dias = max(0, (hoje - dia).days)
        rotulo = (f"desde {desde[11:16]}" if ha_dias == 0
                  else f"desde {desde[8:10]}/{desde[5:7]}, há {ha_dias} dia(s)")
        saida[str(r["chave"])] = {"usuario_id": int(r["usuario_id"]), "por": r["por"],
                                  "desde": desde[:16], "nota": r["nota"] or "",
                                  "ha_dias": ha_dias, "rotulo": rotulo}
    return saida


def pode_assumir(tipo: str, papel: str, *, pode_marcar_a_rotina: bool = False,
                 eh_robo: bool = False) -> bool:
    """Esta pessoa assume este tipo de problema? `papel` é o efetivo. Só calcula."""
    papel = str(papel or "").upper()
    if eh_robo or papel in QUEM_NUNCA:
        return False
    if str(tipo).upper() == ROTINA:
        return bool(pode_marcar_a_rotina)
    return papel in QUEM_ASSUME_ACHADO_E_FASE


def pode_tomar(papel: str, *, eh_robo: bool = False) -> bool:
    """Esta pessoa assume no lugar de outra? Só calcula."""
    return not eh_robo and str(papel or "").upper() in QUEM_TOMA


def marcar(itens: list[dict], quem: dict[str, dict], chave_de, *, papel: str,
           usuario_id: int | None, pode_assumir_item, eh_robo: bool = False) -> int:
    """Põe em cada item da tela a marca e os botões: `quem` (ou None),
    `qr_meu`, `qr_pode_assumir`, `qr_pode_tomar`, `qr_chave`. Devolve quantos
    estão em resolução. Só calcula."""
    n = 0
    for x in itens:
        chave = chave_de(x)
        marca = quem.get(chave)
        meu = bool(marca and usuario_id and int(marca["usuario_id"]) == int(usuario_id))
        x["qr_chave"] = chave
        x["quem"] = marca
        x["qr_meu"] = meu
        x["qr_pode_assumir"] = bool(not marca and pode_assumir_item(x))
        x["qr_pode_tomar"] = bool(marca and not meu and pode_tomar(papel, eh_robo=eh_robo)
                                  and pode_assumir_item(x))
        n += bool(marca)
    return n
