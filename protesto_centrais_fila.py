"""A FILA COMUM DAS CENTRAIS, DO LADO DO PROTESTO — só homologação.

Construído em 05/10/2026, marco (b) da base comum das integrações (dono:
RCPN/Protesto). `centrais_fila` guarda e entrega; **quem manda é o domínio**,
pela função `enviar` passada a `processar_proximo`. Este módulo é esse
domínio para a CENPROT e a CRA.

**NESTE MARCO SÓ PASSA PELA FILA O QUE É TESTE OU CONSULTA.** A ordem do
oficial para a etapa é «homologação só consulta/teste, sem dados reais de
pessoas»: por isso a única operação daqui é o **teste de conexão**
(`DIAGNOSTICO`), que na CENPROT só pede o token e na CRA só chama
`BuscarApresentante` — a única operação sem parâmetro, que não marca nada do
lado de lá. Anuência, certidão, confirmação e retorno continuam saindo pela
rota que o operador clicou, direto, como sempre; entram na fila num marco
seguinte, com massa de teste sintética.

**PRODUÇÃO NÃO ENTRA AQUI, E POR DOIS CADEADOS.** `testar_pela_fila` recusa
ambiente que não seja homologação (ou `TESTES`), e `processar_proximo` é
chamado sem `permitir_producao` — de modo que nem item de produção posto à mão
na tabela sairia por este caminho.

**A REDE FICA FORA DA TRANSAÇÃO**, porque quem a chama é `processar_proximo`
(pega numa transação curta, chama `enviar` sem transação, anota noutra). As
chamadas de rede ficam no log das Centrais pelo próprio transporte
(`cenprot_api._bater` / `cra21_api._bater`); a fila anota ENFILEIRADO,
ENVIADO, CONFIRMADO ou FALHA, e o painel `/centrais/status` mostra os dois.
"""
from __future__ import annotations

from typing import Any, Callable

import centrais_cred as CRED
import centrais_fila as FILA
import centrais_schema as SCH
import cenprot_api as API
import cra21_api as CRA

DIAGNOSTICO = "DIAGNOSTICO"

# OS AMBIENTES QUE ENTRAM NA FILA NESTE MARCO. Produção, não.
AMBIENTES_DA_FILA: tuple[str, ...] = (FILA.HOMOLOGACAO, CRED.TESTES)

# QUANTOS ITENS UM CLIQUE PROCESSA, no máximo. O item do clique pode ter um
# mais antigo à frente (um que o painel reprocessou); processa-se até chegar
# nele, e não a fila inteira — tudo aqui é teste de conexão em homologação.
LIMITE_POR_CLIQUE = 5

# O QUE CADA (central, operação) CHAMA. Só calcula; quem chama é `_enviar`.
_DIAGNOSTICO_DA_CENTRAL: dict[str, Callable[..., dict]] = {
    CRED.CENPROT: API.diagnostico,
    CRED.CRA: CRA.diagnostico,
}


def _ambiente_da_fila(ambiente: Any) -> str:
    qual = str(ambiente or "").strip().upper() or FILA.HOMOLOGACAO
    if qual not in AMBIENTES_DA_FILA:
        raise FILA.FilaError(
            "Pela fila das Centrais, neste momento, só passa o teste de "
            "conexão em homologação. Em produção o teste continua direto, "
            "pela tela da própria Central.")
    return qual


def _enviar(item: dict, resultados: dict[int, dict]) -> str:
    """Executa um item da fila. Chamado por `processar_proximo`, SEM transação.

    Devolve o `resposta_ref` curto (sem segredo e sem dado de gente).
    Levanta `FalhaDefinitiva` quando a Central respondeu «não» ou falta a
    credencial — repetir sozinho não muda nada disso.
    """
    central = str(item.get("central") or "").upper()
    operacao = str(item.get("operacao") or "")
    ambiente = str(item.get("ambiente") or "").upper()
    if ambiente not in AMBIENTES_DA_FILA:
        # O segundo cadeado: item de produção posto à mão não sai daqui.
        raise FILA.FalhaDefinitiva(
            "Item de produção não sai pela fila neste marco.")
    if operacao != DIAGNOSTICO or central not in _DIAGNOSTICO_DA_CENTRAL:
        raise FILA.FalhaDefinitiva(
            f"A fila do Protesto não sabe executar «{central}/{operacao}».")
    d = _DIAGNOSTICO_DA_CENTRAL[central](ambiente)
    resultados[int(item["id"])] = d
    if not d.get("ok"):
        raise FILA.FalhaDefinitiva(str(d.get("motivo") or "falhou"))
    return "conexão ok"


def testar_pela_fila(db: Any, central: str, ambiente: Any = FILA.HOMOLOGACAO,
                     *, por: str | None = None) -> dict:
    """O teste de conexão da Central, passando pela fila comum. ESCREVE.

    Enfileira um `DIAGNOSTICO`, processa com `processar_proximo` e, se a
    Central respondeu, marca o item como CONFIRMADO (numa consulta, a
    resposta completa É a confirmação). Devolve o dicionário de `diagnostico`
    da Central, com `fila_id` e `situacao` do item.
    """
    qual = str(central or "").strip().upper()
    if qual not in _DIAGNOSTICO_DA_CENTRAL:
        raise FILA.FilaError(f"Central sem teste pela fila: «{central}».")
    amb = _ambiente_da_fila(ambiente)
    with db.transaction() as con:
        meu = FILA.enfileirar(con, qual, DIAGNOSTICO, f"diagnostico:{amb}",
                              ambiente=amb, max_tentativas=1, por=por)
    resultados: dict[int, dict] = {}
    final: dict | None = None
    for _ in range(LIMITE_POR_CLIQUE):
        feito = FILA.processar_proximo(
            db, lambda item: _enviar(item, resultados),
            central=qual, operacao=DIAGNOSTICO)
        if feito is None:
            break
        if feito.get("status") == SCH.ENVIADO:
            with db.transaction() as con:
                FILA.marcar_confirmado(con, int(feito["id"]))
                feito = FILA.item(con, int(feito["id"])) or feito
        if int(feito["id"]) == meu:
            final = feito
            break
    if final is None:
        with db.transaction() as con:
            final = FILA.item(con, meu) or {"id": meu, "status": "?"}
    d = dict(resultados.get(meu) or {
        "ok": False, "ambiente": amb,
        "motivo": (final.get("erro") or
                   "O teste ficou na fila e não rodou agora; veja em "
                   "Configurações → Centrais → status.")})
    d["fila_id"] = meu
    d["situacao"] = final.get("status")
    return d
