"""O que a carga grava e o que a especie declara tem de ser a mesma coisa.

O DEFEITO, MEDIDO EM 31/08/2026
    `acervo_carga.papeis_da_filiacao` devolvia, no casamento, **quatro** papeis
    — `PAI_NUBENTE1`, `MAE_NUBENTE1`, `PAI_NUBENTE2`, `MAE_NUBENTE2` — e
    `rc_assento.PAPEIS_DA_ESPECIE["CASAMENTO"]` declarava tres:
    `("NUBENTE1", "NUBENTE2", "TESTEMUNHA")`.

    A carga gravava o que a especie nao reconhecia, e **a tela de lavrar
    casamento nao oferecia filiacao nenhuma** — sendo que o art. 70 da Lei
    6.015/1973 a exige e o termo desta casa a marca como campo exigido.

    E o mesmo defeito que o nascimento teve: peca pronta de um lado, e o outro
    lado sem saber dela. **Sexta vez neste projeto que duas listas que deviam
    dizer a mesma coisa divergem** — a `normalizar_nome`, o menu, as cargas, os
    campos do `INSERT`, as cores, e agora os papeis.

POR QUE ESTE TESTE E DIFERENTE DE OLHAR AS DUAS LISTAS
    Ele **roda a carga** com filiacao de verdade e compara o que ela produz com
    o que a especie aceita. Comparar as duas listas escritas exigiria que eu
    soubesse quais papeis a carga produz — e foi justamente isso que ninguem
    soube por duas semanas.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import acervo_carga as AC                                        # noqa: E402
import rc_assento as RA                                          # noqa: E402

# OS TIPOS DO ACERVO, e a especie de cada um.
TIPOS = (
    (1, "NASCIMENTO", 2),      # tipo, espécie, quantas linhas de filiação
    (2, "CASAMENTO", 4),
    (3, "OBITO", 2),
)


def _linhas(quantas: int) -> list[dict]:
    """Filiação como o acervo a traz: código e sexo, alternando."""
    return [{"intCodigoFiliacao": i,
             "strSexo": "Masculino" if i % 2 else "Feminino"}
            for i in range(1, quantas + 1)]


@pytest.mark.parametrize("tipo,especie,quantas", TIPOS)
def test_todo_papel_que_a_carga_grava_a_especie_declara(tipo, especie, quantas):
    """**A carga gravava o que a espécie não reconhecia.**

    E o efeito não aparecia na carga — aparecia na tela de lavrar, que não
    oferecia o papel, meses depois.
    """
    papeis, _ = AC.papeis_da_filiacao(tipo, _linhas(quantas))
    declarados = set(RA.PAPEIS_DA_ESPECIE[especie])
    faltam = sorted(set(papeis.values()) - declarados)
    assert not faltam, (
        f"a carga grava estes papéis em {especie} e a espécie não os declara: "
        + ", ".join(faltam)
        + " — a tela de lavrar não vai oferecê-los, e o dado carregado fica "
          "sem lugar na ficha")


def test_o_casamento_tem_as_DUAS_filiacoes():
    """**São quatro pessoas**, e o art. 70 exige a filiação dos dois nubentes.

    No acervo há 48 linhas de filiação de casamento — 12 de cada código 1, 2,
    3 e 4 —, e os códigos 3 e 4 são os pais do segundo cônjuge.
    """
    papeis = RA.PAPEIS_DA_ESPECIE["CASAMENTO"]
    for quem in ("PAI_NUBENTE1", "MAE_NUBENTE1",
                 "PAI_NUBENTE2", "MAE_NUBENTE2"):
        assert quem in papeis, f"o casamento não aceita {quem}"


@pytest.mark.parametrize("papel", ["PAI_NUBENTE1", "MAE_NUBENTE1",
                                   "PAI_NUBENTE2", "MAE_NUBENTE2"])
def test_todo_papel_novo_tem_rotulo_prefixo_e_ordem(papel):
    """Papel sem rótulo aparece na tela como a chave crua; sem prefixo, o
    formulário não sabe montar o campo; sem ordem, ele cai no fim da lista."""
    assert RA.ROTULO_DO_PAPEL.get(papel), f"{papel} sem rótulo"
    assert RA.PREFIXO_DO_PAPEL.get(papel), f"{papel} sem prefixo"
    assert RA.ORDEM_DO_PAPEL.get(papel) is not None, f"{papel} sem ordem"


def test_os_rotulos_seguem_a_convencao_do_oficial():
    """«Filiação 1 e 2, indicando a 1 para mãe entre parênteses» — decisão dele
    em 30/08/2026."""
    assert "Filiação 1" in RA.ROTULO_DO_PAPEL["MAE_NUBENTE1"]
    assert "(mãe)" in RA.ROTULO_DO_PAPEL["MAE_NUBENTE1"]
    assert "Filiação 2" in RA.ROTULO_DO_PAPEL["PAI_NUBENTE1"]
    assert "(pai)" in RA.ROTULO_DO_PAPEL["PAI_NUBENTE1"]


def test_a_ordem_poe_o_primeiro_nubente_antes_do_segundo():
    """É a ordem do termo e da certidão."""
    o = RA.ORDEM_DO_PAPEL
    assert o["MAE_NUBENTE1"] < o["MAE_NUBENTE2"]
    assert o["PAI_NUBENTE1"] < o["PAI_NUBENTE2"]


def test_todo_papel_declarado_em_qualquer_especie_tem_rotulo():
    """**O piso.** Papel novo que nasça sem rótulo aparece na tela como a chave
    crua — `PAI_NUBENTE2` na cara de quem atende."""
    sem = []
    for especie, papeis in RA.PAPEIS_DA_ESPECIE.items():
        for p in papeis:
            if not RA.ROTULO_DO_PAPEL.get(p):
                sem.append(f"{especie}.{p}")
    assert not sem, "papéis sem rótulo: " + ", ".join(sem)
