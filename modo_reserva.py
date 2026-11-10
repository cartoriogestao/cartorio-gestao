"""O SERVIDOR RESERVA — o Cartório Gestão rodando como cópia de consulta do servidor principal.

POR QUE EXISTE — 07/11/2026, pedido do oficial: um servidor extra, num macOS, «como backup do
servidor original, em uma porta diferente, mas com banco de dados sincronizado». Decidido com ele:
a reserva SÓ LÊ enquanto o principal está no ar, e ASSUME (vira o principal) se ele cair.

POR QUE SÓ LÊ: os números do cartório (protocolo, selo, folha, ato) saem de sequências do banco.
Dois servidores lançando ao mesmo tempo dariam o mesmo número duas vezes, um em cada lado, e o
banco só se acertaria depois — o que no livro não tem conserto.

COMO SE LIGA: `CG_MODO_RESERVA=1` no ambiente do processo (o LaunchDaemon do macOS põe). Sem a
variável, nada muda — o servidor principal nunca lê este módulo de outro jeito.

O QUE MUDA COM ELE LIGADO
    - o banco: a conexão não cria nem migra nada (o esquema chega pela réplica) — `banco_pg`;
    - o app: não grava ao subir (fotografia da ajuda, vigias), não responde à descoberta na rede
      (os balcões não podem achar a reserva no lugar do principal), recusa todo formulário e
      mostra a faixa «SERVIDOR RESERVA»;
    - a porta e a pasta dos arquivos vêm do ambiente, e não do banco: o que está no banco é a
      configuração do PRINCIPAL (porta 8765, `C:\\...`), que chega pela réplica.

A TRAVA DE VERDADE é o banco: o usuário do banco da reserva só tem SELECT (ver
`docs/SERVIDOR_RESERVA_MACOS.md`). O que este módulo faz é o sistema saber disso e se comportar —
sem ele, cada tela que grava um rastro cairia com «permission denied».
"""
from __future__ import annotations

import os
from pathlib import Path

#: A porta padrão da reserva. Diferente da do principal (8765) de propósito: se alguém digitar o
#: endereço errado, cai numa tela que diz «reserva», e não numa que parece a de sempre.
PORTA_PADRAO = 8775

#: Os únicos formulários (POST) que a reserva aceita: entrar — a senha E o código da verificação
#: em duas etapas, sem o qual quem a tem ativa parava no meio da entrada — e sair. O código é
#: conferido sem gravar (`dois_fatores.conferir_so_leitura`).
FORMULARIOS_LIBERADOS = frozenset({"login", "login_dois_fatores", "logout"})


def ativo() -> bool:
    """O processo é o servidor reserva? Só lê o ambiente."""
    return (os.environ.get("CG_MODO_RESERVA") or "").strip() == "1"


def porta() -> int:
    """A porta da reserva: `CG_RESERVA_PORTA`, ou a padrão. Nunca a do banco (é a do principal)."""
    try:
        valor = int((os.environ.get("CG_RESERVA_PORTA") or "").strip() or PORTA_PADRAO)
    except ValueError:
        return PORTA_PADRAO
    return valor if 0 < valor < 65536 else PORTA_PADRAO


def raiz_dos_arquivos() -> Path | None:
    """A cópia local da pasta de arquivos do principal (`CG_RESERVA_ARQUIVOS`), se configurada."""
    texto = (os.environ.get("CG_RESERVA_ARQUIVOS") or "").strip()
    return Path(texto).expanduser() if texto else None


AVISO = ("Servidor reserva: só consulta. Os lançamentos continuam no servidor principal; "
         "se ele cair, o oficial manda a reserva assumir.")
