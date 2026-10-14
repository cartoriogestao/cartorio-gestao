"""Ligar o selador de mentira numa bancada, numa linha.

POR QUE ISTO NASCEU — 16/09/2026, item 1 da ordem do oficial sobre o relato
#77: «se falhar o selo, **sempre** suspender o ato para corrigir o problema»,
inclusive quando o aparelho **não foi apontado**. Até então a casa sem selador
configurado lavrava e o ato ia para a lista de atos sem selo; agora ele volta
para a minuta.

Isso mudou o que uma bancada precisa ter para lavrar qualquer coisa. Dezenas
de testes deste projeto não falam de selo nenhum — falam de numeração, de
teor, de partes, de encerramento — e montavam o banco do zero, **sem
selador**, porque até ontem isso bastava. Sem uma peça comum, cada um deles
ganharia a sua cópia das cinco linhas que apontam o aparelho, e **cinco linhas
copiadas em vinte arquivos divergem no primeiro conserto** — a lição que este
projeto já pagou com a `normalizar_nome`.

O APARELHO É DE VERDADE, e isto é decisão antiga da casa (`selador_falso.py`):
servidor HTTP com TLS próprio numa porta local, e não um `mock`. «O que este
cliente tem de difícil não é montar JSON — é o transporte.» O selador desta
serventia é uma máquina da rede local com certificado próprio, e é isso que a
bancada imita.

    with ligar_o_selador(cg_casa) as aparelho:
        ...                      # aqui o ato sela e fica de pé
        aparelho.recusar_com = (400, {"message": "recusado"})
        ...                      # e aqui ele é suspenso e vira minuta

A CREDENCIAL NÃO VAI PARA O BANCO nem aqui: `gravar_credencial` a põe no
arquivo próprio da pasta de dados da bancada, que é a mesma regra da casa —
o banco viaja no backup.
"""
from __future__ import annotations

import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

AGORA = "2026-09-16T09:00:00"


def tem_cryptography() -> bool:
    """O selador de mentira precisa dela para o TLS."""
    try:
        import cryptography              # noqa: F401
    except ImportError:
        return False
    return True


@contextmanager
def ligar_o_selador(cg_casa, *, tabela_custas_em: str = "2026-01-01",
                    cns: str = "000000"):
    """Sobe o aparelho, aponta-o nesta instalação, e desliga no fim.

    Devolve o `SeladorFalso`, para quem quiser mandá-lo **recusar** —
    `aparelho.recusar_com = (400, {...})` — que é o caso em que o ato se
    suspende e volta a ser minuta.

    A DATA DA TABELA DE CUSTAS VAI JUNTO porque sem ela o selo não sai, e a
    falha seria de outra espécie: «falta dizer de que data é a tabela», que é
    coisa do cadastro e **não** suspende ato nenhum. Bancada que esquece isso
    prova o contrário do que quer.

    **E O QUE A BANCADA JÁ ESCOLHEU NÃO SE SOBRESCREVE.** A primeira versão
    gravava as duas configurações sempre, e apagou a escolha de quem já as
    tinha: `test_rcpj_rtd_selo_automatico` grava a data como `20260101` e esta
    peça a trocava por `2026-01-01`, de modo que o selo passava a falhar por
    um motivo novo — e a bancada que eu vinha consertar ficava vermelha por
    minha causa, num lugar que não tem nada a ver com o que ela mede.
    """
    import pytest

    if not tem_cryptography():
        pytest.skip("o selador de mentira precisa de `cryptography`")
    import selador_cliente as CL
    import selador_config as SC
    from selador_falso import SeladorFalso, impressao_digital

    faltando = {chave: valor
                for chave, valor in (("ri_cns", cns),
                                     ("selo_tabela_custas_em", tabela_custas_em))
                if not str(cg_casa["db"].get_setting(chave, "") or "").strip()}
    if faltando:
        cg_casa["db"].set_settings(faltando)
    aparelho = SeladorFalso()
    aparelho.__enter__()
    try:
        SC.gravar_credencial(cg_casa["dados"], "fulano.detal123", "abcde123",
                             agora=AGORA)
        CL.esquecer_tokens()
        con = sqlite3.connect(cg_casa["banco"])
        try:
            with con:
                SC.gravar(con, base_url=aparelho.base,
                          usuario="fulano.detal123", agora=AGORA)
                CL.fixar_certificado(con, aparelho.base,
                                     sha256=impressao_digital(), agora=AGORA,
                                     usuario="TESTE")
        finally:
            con.close()
        yield aparelho
    finally:
        aparelho.__exit__(None, None, None)
        CL.esquecer_tokens()
