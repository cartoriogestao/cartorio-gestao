"""A CHECKLIST DO DIA GANHA UM ATALHO EM TRABALHO, E CONTINUA EM GESTÃO (25/11/2026).

    «coloque o modulo de conferencia por area na aba de trabalho»
    «atalho nela»
    «mantendo no painel»                                       — o oficial

POR QUE ESTE TESTE EXISTE
    A checklist de gestão do dia (`gestor_checklist`) mora em Gestão › Checklist
    do dia, e os cartões do semáforo no painel geral levam a ela. O oficial pediu
    um ATALHO na aba Trabalho, mantendo o resto. Aqui se prova:
    - o atalho aparece em Trabalho para ADMIN, MANAGER, AUDITOR (e TI, que é o
      ADMIN na régua), e não para USER — os mesmos papéis de `CK.QUEM_VE`;
    - a tela continua em Gestão › Checklist do dia, e é lá que ela abre (menu,
      migalhas), mesmo com `?area=` dos cartões;
    - a busca não repete o resultado;
    - **a regra das duas portas continua de pé para o resto**: endereço repetido
      no menu de um mesmo papel só passa se for atalho declarado em
      `NAV.ATALHOS`, com o motivo escrito.

Só calcula: não abre banco nem tela.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import gestor_checklist as CK  # noqa: E402
import navegacao as NAV        # noqa: E402

ENDPOINT = "gestor_checklist"
VEEM = ("ADMIN", "MANAGER", "AUDITOR", "TI")
NAO_VEEM = ("USER",)


def _onde(papel: str) -> list[tuple[str, str, bool]]:
    return [(e["modulo"], e["secao"], bool(e.get("atalho"))) for e in NAV.entradas(papel)
            if e["endpoint"] == ENDPOINT]


def _endereco(rota: str, **args) -> str:
    base = {"gestor_checklist": "/administrativo/gestor/checklist"}.get(rota, f"/{rota}")
    return base + ("?" + "&".join(f"{k}={v}" for k, v in sorted(args.items())) if args else "")


@pytest.mark.parametrize("papel", VEEM + NAO_VEEM)
def test_o_atalho_esta_em_trabalho_e_a_checklist_continua_em_gestao(papel):
    esperado = ([("TRABALHO", "Checklist do dia", True), ("GESTAO", "Checklist do dia", False)]
                if papel in VEEM else [])
    assert _onde(papel) == esperado


def test_o_atalho_tem_os_papeis_da_checklist():
    itens = [i for m in NAV.MODULOS_DA_BARRA for _, its in m["secoes"] for i in its
             if i["endpoint"] == ENDPOINT]
    assert len(itens) == 2
    assert all(set(i["papeis"]) == set(CK.QUEM_VE) for i in itens)
    assert all(i["args"] == {} for i in itens), "o atalho leva ao mesmo endereço, sem filtro"


@pytest.mark.parametrize("args", [{}, {"area": "RI"}])
def test_a_tela_abre_em_gestao_e_nao_no_atalho(args):
    modulo, secao, item = NAV.localizar(ENDPOINT, args, "ADMIN", NAV._flags(True, True, ()))
    assert (modulo, secao) == ("GESTAO", "Checklist do dia")
    assert item is not None and not item.get("atalho")

    casca = NAV.montar(ENDPOINT, args, "MANAGER", _endereco)
    assert casca["modulo"] == "GESTAO"
    assert [m["rotulo"] for m in casca["migalhas"]] == ["Gestão", "Checklist do dia"]


def test_trabalho_continua_abrindo_no_meu_trabalho_e_a_busca_nao_repete():
    casca = NAV.montar("dashboard", {}, "AUDITOR", _endereco)
    trabalho = next(b for b in casca["barra"] if b["chave"] == "TRABALHO")
    assert trabalho["url"] == "/at_meu_trabalho"
    achados = [i for i in casca["indice"] if i["u"] == "/administrativo/gestor/checklist"]
    assert len(achados) == 1 and achados[0]["s"] == "Gestão › Checklist do dia"


@pytest.mark.parametrize("papel", ("ADMIN", "MANAGER", "USER", "AUDITOR", "TI"))
def test_endereco_repetido_no_menu_so_se_for_atalho_declarado(papel):
    """**Duas portas para a mesma sala**, agora no menu novo — relatos #12 e #32."""
    por_endereco: dict[tuple, list[dict]] = defaultdict(list)
    for e in NAV.entradas(papel):
        por_endereco[(e["endpoint"], tuple(sorted(e["args"].items())))].append(e)
    sem_declaracao = {
        k: [f'{e["modulo"]} › {e["secao"]} › {e["rotulo"]}' for e in es]
        for k, es in por_endereco.items() if len(es) > 1 and not (
            k[0] in NAV.ATALHOS and sum(not e.get("atalho") for e in es) == 1)}
    assert not sem_declaracao, (
        "estes endereços têm mais de uma porta no menu e não são atalho declarado:\n"
        + "\n".join(f"  {k}: " + " | ".join(v) for k, v in sem_declaracao.items()))


def test_a_lista_de_atalhos_nao_envelhece():
    """Declaração que ninguém revisa vira licença permanente; e sem motivo, não vale."""
    marcados = {i["endpoint"] for m in NAV.MODULOS_DA_BARRA for _, its in m["secoes"]
                for i in its if i.get("atalho")}
    assert marcados == set(NAV.ATALHOS)
    assert all(len(motivo) >= 40 for motivo in NAV.ATALHOS.values())
