"""QUEM VÊ CADA MÓDULO — e o Protesto volta para o oficial em 01/09/2026.

Ordem dele, na mesma noite em que mandou desligá-lo: *«reabilite o protesto
para o administrador, permitindo um botão em configurações habilitar para
todos usuarios»*.

**ISSO MUDOU A PERGUNTA, E NÃO SÓ A RESPOSTA.** A primeira versão era um
interruptor — ligado ou desligado. Agora são **três alcances**, e o do meio é
o que ele pediu:

    NINGUEM · o módulo não abre para ninguém
    ADMIN   · abre só para quem responde pela serventia   ← o Protesto hoje
    TODOS   · abre para o balcão inteiro

**É A MESMA DECISÃO DO ALCANCE DA AJUDA, E PELA MESMA RAZÃO** (`aj_config`,
26/08/2026): *«apenas para o administrador, com opção de expandir»*. A segunda
metade é que muda o desenho — só a primeira seria um `@roles_required` na
rota, e aí abrir para o balcão dependeria de alguém mexer no código. **Quem
decide não deveria depender de quem programa.**

**O ADMIN NUNCA SE TRANCA DO LADO DE FORA.** Quem muda o alcance é o ADMIN, na
tela de configurações; se `NINGUEM` alcançasse também a ele, ele perderia a
porta e a chave ao mesmo tempo — e só uma versão nova o traria de volta.

**A GUARDA É NO SERVIDOR, E NÃO NO MENU.** Tirar o link e deixar a rota de pé
esconde a porta sem trancá-la: quem tiver o endereço nos favoritos entra, e
lavra. O menu não oferece o que aquele operador não pode fazer; a rota recusa
porque é ela que faz.

**A REGRA DE «DE QUE MÓDULO É ESTA TELA» É A DE `modulos.py`, E NÃO UMA
PARECIDA.** Escrever aqui um segundo `endpoint.startswith("protesto")` seria a
segunda régua que diverge no primeiro conserto — o defeito da
`normalizar_nome`, que este projeto já pagou três vezes. Há teste que roda
esta guarda contra **todas** as rotas do sistema.

**E DESLIGAR MÓDULO NUNCA APAGA ATO.** Os 1.366 títulos, os 1.160 protestos, os
56 cancelamentos e os selos continuam onde estão — o que o alcance governa é a
**vista**.
"""
from __future__ import annotations

import unicodedata
from collections.abc import Callable
from typing import Any

# OS TRÊS ALCANCES, do mais fechado ao mais aberto.
NINGUEM, ADMIN, TODOS = "NINGUEM", "ADMIN", "TODOS"
ALCANCES: tuple[str, ...] = (NINGUEM, ADMIN, TODOS)

# QUEM CADA ALCANCE DEIXA ENTRAR. Tupla vazia quer dizer «qualquer um».
#
# O MANAGER **não** entra no alcance ADMIN: o oficial escreveu «para o
# administrador», e ampliar por conta própria seria decidir por ele. Se ele
# quiser o gerente junto, é uma palavra nesta linha.
PAPEIS_DO_ALCANCE: dict[str, tuple[str, ...]] = {
    NINGUEM: ("__ninguem__",),
    ADMIN: ("ADMIN",),
    TODOS: (),
}

# A CHAVE DE CADA MÓDULO EM `settings`. Só existe linha para módulo cujo
# alcance já foi mexido — módulo sem chave é de TODOS, que é o normal.
CHAVE_DA_CONFIGURACAO: dict[str, str] = {
    "PROTESTO": "modulo_protesto_alcance",
    # A APOSTILA DE HAIA (LG03, 19/10/2026) NÃO É UM DOS OITO de `modulos.py`:
    # é um serviço que atravessa quatro atribuições, e as telas dela moram no
    # Administrativo. Por isso a guarda dela não é a do `before_request`, que
    # pergunta pelo módulo da tela, e sim a das próprias rotas
    # (`apostila_web`) — mas a REGRA do alcance é esta, e não uma segunda.
    "APOSTILA": "modulo_apostila_alcance",
}

# A CHAVE DA PRIMEIRA VERSÃO, LIDA COMO COMPATIBILIDADE.
#
# A 3.6.61 gravava `modulo_protesto_ligado` com `0`/`1`. Se o oficial já a
# aplicou e marcou a caixa, aquele `1` quer dizer «abre para todos» — e perder
# a marcação dele numa atualização seria a tela desfazer o que ele decidiu.
# Some no dia em que o alcance for gravado.
CHAVE_ANTIGA: dict[str, str] = {
    "PROTESTO": "modulo_protesto_ligado",
}

# O ALCANCE DE FÁBRICA — ordem do oficial em 01/09/2026.
#
# Vale para a instalação nova E para esta atualização: sem linha em `settings`,
# quem decide é isto.
ALCANCE_DE_FABRICA: dict[str, str] = {
    "PROTESTO": ADMIN,
    # A serventia não apostila hoje: o módulo chega FECHADO, e quem o abre é o
    # oficial, no Gestor, no dia em que ela for habilitada.
    "APOSTILA": NINGUEM,
}

# O QUE A TELA DIZ A QUEM BATER NA PORTA E NÃO PUDER ENTRAR.
#
# **A frase muda com o alcance**, porque as duas situações são diferentes: um
# módulo fechado para todos e um módulo que existe mas não é daquele operador
# pedem providências diferentes de quem lê.
MOTIVO_POR_ALCANCE: dict[str, dict[str, str]] = {
    "PROTESTO": {
        NINGUEM: ("O módulo de Protesto está fechado nesta serventia, por "
                  "decisão do oficial. Os títulos, os protestos e os selos "
                  "continuam guardados; o que saiu do ar foram as telas. "
                  "Para reabrir: Administrativo → Configurações."),
        ADMIN: ("O módulo de Protesto está aberto apenas para o oficial. "
                "Se você precisa dele para atender, peça a ele — em "
                "Administrativo → Configurações há a opção de liberar para "
                "todos os usuários."),
    },
    "APOSTILA": {
        NINGUEM: ("A Apostila de Haia está desligada nesta serventia: ela só "
                  "é ligada quando a serventia for habilitada a apostilar. "
                  "Para ligar: Administrativo → Apostila de Haia, com o "
                  "oficial."),
        ADMIN: ("A Apostila de Haia está aberta apenas para o oficial. Se "
                "você precisa dela para atender, peça a ele — em "
                "Administrativo → Apostila de Haia há a opção de liberar para "
                "todos os usuários."),
    },
}

MOTIVO_PADRAO = ("Este módulo não está aberto para o seu usuário nesta "
                 "serventia. O que estava lavrado continua guardado.")

# QUEM FICA DE FORA PELA FUNÇÃO, mesmo com o alcance TODOS — ordem do oficial
# em 21/10/2026, ao abrir o Protesto inteiro às escreventes: «[NOME] eh
# auxiliar, nao era pra poder». O auxiliar tem o MESMO papel (USER) da
# escrevente, e por isso a régua é a FUNÇÃO cadastrada na tela Usuários, e não
# o papel. Função em branco não fecha nada — fechar por falta de cadastro
# trancaria a escrevente que ainda não teve a função preenchida. **O ADMIN
# nunca fica de fora**, nem com função de auxiliar (a conta do analista de
# sistemas é assim).
FUNCOES_DE_FORA: dict[str, tuple[str, ...]] = {
    "PROTESTO": ("AUXILIAR",),
}

MOTIVO_DA_FUNCAO: dict[str, str] = {
    "PROTESTO": ("O Protesto é operado pelas escreventes autorizadas e pela "
                 "substituta; a função de auxiliar não o opera. Quem decide "
                 "isso é o oficial."),
}


def _funcao(valor: Any) -> str:
    """Sem acento e em maiúsculas — «Auxiliar», «AUXILIAR» e «auxiliar» são a
    mesma função."""
    s = unicodedata.normalize("NFKD", str(valor or ""))
    return "".join(c for c in s if not unicodedata.combining(c)).strip().upper()


def fora_pela_funcao(modulo: Any, papel: Any = None, funcao: Any = None) -> bool:
    """A função cadastrada tira este operador deste módulo? Só calcula."""
    if _nome(papel) == ADMIN:
        return False
    f = _funcao(funcao)
    return bool(f) and any(f.startswith(x) for x in FUNCOES_DE_FORA.get(_nome(modulo), ()))


def _nome(chave: Any) -> str:
    return str(chave or "").strip().upper()


def _verdadeiro(valor: Any) -> bool:
    """Lê a marca antiga como o resto da casa lê: `1`, `sim`, `true` ligam."""
    return str(valor).strip().lower() in ("1", "sim", "s", "true", "on")


def alcance(get_setting: Callable[..., Any], chave: Any) -> str:
    """Até onde aquele módulo vai. Só LÊ.

    Recebe a **função** de ler configuração, e não a conexão, para que esta
    guarda possa ser chamada de dentro do `before_request` sem abrir transação
    nenhuma — é a mesma razão de `ato_selado.obter_selo` receber `db`.
    """
    nome = _nome(chave)
    if not nome:
        return TODOS
    config = CHAVE_DA_CONFIGURACAO.get(nome)
    if config is None:
        # Módulo cujo alcance nunca foi mexido não tem chave, e é de todos.
        # Não se inventa configuração para os oito.
        return TODOS
    padrao = ALCANCE_DE_FABRICA.get(nome, TODOS)
    escrito = _nome(get_setting(config, ""))
    if escrito in ALCANCES:
        return escrito
    antiga = CHAVE_ANTIGA.get(nome)
    if antiga:
        marca = get_setting(antiga, "")
        if str(marca).strip():
            return TODOS if _verdadeiro(marca) else NINGUEM
    return padrao


def pode_entrar(get_setting: Callable[..., Any], modulo_da_tela: Any,
                papel: Any = None, funcao: Any = None) -> bool:
    """Este operador pode abrir esta tela? Só LÊ.

    `modulo_da_tela` é o que `modulos.modulo_da_tela(endpoint)` devolveu —
    recebido pronto, de propósito: quem decide de que módulo é a tela é aquele
    módulo, e não este.
    """
    if fora_pela_funcao(modulo_da_tela, papel, funcao):
        return False
    ate_onde = alcance(get_setting, modulo_da_tela)
    permitidos = PAPEIS_DO_ALCANCE.get(ate_onde, ())
    if not permitidos:
        return True
    return _nome(papel) in permitidos


def escondidos(get_setting: Callable[..., Any],
               papel: Any = None, funcao: Any = None) -> frozenset[str]:
    """Os módulos que o menu NÃO oferece a este operador. Só LÊ.

    **O nome mudou de `desligados` para `escondidos`** quando o interruptor
    virou alcance: a resposta deixou de ser sobre o módulo e passou a ser
    sobre quem está olhando. Nome que diz uma coisa e responde outra é o
    defeito que este projeto já pagou três vezes.
    """
    return frozenset(nome for nome in CHAVE_DA_CONFIGURACAO
                     if not pode_entrar(get_setting, nome, papel, funcao))


def motivo(chave: Any, ate_onde: Any = None, papel: Any = None,
           funcao: Any = None) -> str:
    """A frase para quem bateu na porta. Só calcula."""
    nome = _nome(chave)
    if fora_pela_funcao(nome, papel, funcao) and nome in MOTIVO_DA_FUNCAO:
        return MOTIVO_DA_FUNCAO[nome]
    por_alcance = MOTIVO_POR_ALCANCE.get(nome) or {}
    return por_alcance.get(_nome(ate_onde)) or MOTIVO_PADRAO
