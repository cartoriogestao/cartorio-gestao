"""OS PAPÉIS DA CASA E O PAPEL TI — a regra num lugar só. Só calcula.

    «criar o papel de usuário TI, com acesso a tudo, menos selar atos»
                                         — decisão do titular, 24/11/2026 (T015)

O TI EQUIVALE AO ADMIN NO ACESSO
    São mais de mil rotas com a lista de papéis escrita (`roles_required`), e
    mais de trezentas condições `user.role` nos modelos. Escrever «TI» em cada
    uma seria a segunda lista que envelhece na tarde em que se escreve. Em vez
    disso a pergunta «este papel passa onde aquele passa?» mora aqui
    (`equivale_a`), e `papel_efetivo` diz o papel que DECIDE o acesso: para o
    TI, o do ADMIN. O `current_user()` do app entrega a linha do usuário com o
    papel efetivo em `role` e o verdadeiro em `papel_real` (`usuario_efetivo`):
    rota, menu, modelo e módulo perguntam pelo `role` e veem o ADMIN; quem
    REGISTRA ou MOSTRA o papel pergunta por `papel_de` e vê o TI.

O TI NÃO SELA — E ISSO NÃO É CONFIGURAÇÃO
    `pode_selar` é a régua; `ato_selado.barrar_quem_nao_sela` é a recusa,
    chamada no ponto mais baixo de cada caminho do selo (`ato_selado.obter_selo`,
    `selador_cliente.selar`, o selo digitado, o vínculo ao ato, a liberação do
    ADMIN e as travas do selo pago). Não há chave em Configurações que a
    desligue, de propósito: a regra que o próprio TI pudesse desligar não seria
    regra — ele equivale ao ADMIN e abre Configurações.

SEM ESCALADA
    O TI não dá a ninguém, nem a si, o papel ADMIN, não troca o próprio papel e
    não mexe na conta de um ADMIN (senha, ativação, papel): por qualquer uma
    dessas portas ele viraria ADMIN e selaria. `recusa_de_papel` diz o porquê.
"""
from __future__ import annotations

from typing import Any, Iterable

ADMIN, MANAGER, USER, AUDITOR, TI = "ADMIN", "MANAGER", "USER", "AUDITOR", "TI"

#: Os papéis do cadastro, na ordem de `app.ROLES` (a tela de Usuários).
PAPEIS: tuple[str, ...] = (ADMIN, MANAGER, USER, AUDITOR, TI)

#: O nome legível de cada papel — a caixa de escolha e as listas da tela.
ROTULOS: dict[str, str] = {
    ADMIN: "ADMIN — administrador",
    TI: "TI — suporte de TI (tudo do ADMIN, menos selar atos)",
    MANAGER: "MANAGER — gerente",
    USER: "USER — escrevente",
    AUDITOR: "AUDITOR — auditor (só confere)",
}

#: Quem passa onde outro passa. Uma entrada só, e é a decisão de 24/11/2026.
EQUIVALE: dict[str, str] = {TI: ADMIN}

#: Os papéis que NÃO selam. Fixo no código: não há configuração que o mude.
NAO_SELAM: frozenset[str] = frozenset({TI})

MSG_NAO_SELA = "O papel TI não sela atos."
MSG_PENDENTE = (" Pendente de selo — o papel TI não sela atos; "
                "o escrevente deve selar.")


class TINaoSela(PermissionError):
    """O papel de quem pediu não sela. A tela responde 403 com `MSG_NAO_SELA`."""

    def __init__(self, mensagem: str = MSG_NAO_SELA):
        super().__init__(mensagem)


def _texto(valor: Any) -> str:
    return str(valor or "").strip().upper()


def papel_de(quem: Any) -> str:
    """O papel VERDADEIRO, em maiúsculas: o que se grava e se mostra. Só calcula.

    Aceita o texto do papel, a linha do banco (`sqlite3.Row`, `Linha` ou dict)
    ou a linha que `usuario_efetivo` entregou — essa guarda o verdadeiro em
    `papel_real`. Sem papel, devolve ''.
    """
    if quem is None:
        return ""
    if isinstance(quem, str):
        return _texto(quem)
    try:
        chaves = list(quem.keys())
    except (AttributeError, TypeError):
        return _texto(getattr(quem, "role", ""))
    if "papel_real" in chaves and quem["papel_real"]:
        return _texto(quem["papel_real"])
    return _texto(quem["role"]) if "role" in chaves else ""


def papel_efetivo(quem: Any) -> str:
    """O papel que DECIDE o acesso: o TI decide como o ADMIN. Só calcula."""
    papel = papel_de(quem)
    return EQUIVALE.get(papel, papel)


def _achatar(papeis: Iterable[Any]) -> set[str]:
    saida: set[str] = set()
    for p in papeis:
        if p is None:
            continue
        if isinstance(p, str):
            saida.add(_texto(p))
        else:
            saida |= _achatar(p)
    return saida


def equivale_a(quem: Any, *papeis: Any) -> bool:
    """Este usuário passa onde algum destes papéis passa? Só calcula.

    `equivale_a(u, "ADMIN")`, `equivale_a(u, "ADMIN", "MANAGER")` ou
    `equivale_a(u, AM)` — a tupla das telas serve como veio.
    """
    aceitos = _achatar(papeis)
    real = papel_de(quem)
    return bool(real) and (real in aceitos or EQUIVALE.get(real, real) in aceitos)


def usuario_efetivo(linha: Any) -> Any:
    """A linha do usuário com o papel EFETIVO em `role` e o real em `papel_real`.

    Só o papel que equivale a outro muda; a linha dos demais volta como veio
    (o mesmo objeto). Só calcula.
    """
    if not linha:
        return linha
    real = papel_de(linha)
    if real not in EQUIVALE:
        return linha
    copia = dict(linha)
    copia["papel_real"] = real
    copia["role"] = EQUIVALE[real]
    return copia


def para_o_registro(papel: Any) -> Any:
    """O papel que a AUDITORIA grava: o verdadeiro de quem está logado. Só lê.

    As rotas passam adiante o papel EFETIVO (`usuario_papel`), que decide o
    acesso; para o TI ele é «ADMIN». Onde esse papel vira registro do autor
    (o «papel» do detalhe da auditoria, o «por/papel» de uma conferência), ele
    passa por aqui, e o TI aparece como TI. Outro papel volta como veio.
    """
    real = papel_da_sessao()
    if real and real in EQUIVALE and papel_de(papel) == EQUIVALE[real]:
        return real
    return papel


# ------------------------------------------------------------------ o selo


def pode_selar(quem: Any) -> bool:
    """Este papel sela? Só calcula. Sem papel conhecido a régua não decide —
    quem decide é a trava do robô e a do escrevente humano (`selo_robo`)."""
    return papel_de(quem) not in NAO_SELAM


def papel_da_sessao() -> str | None:
    """O papel VERDADEIRO de quem está logado, ou None fora de requisição.

    É como o ponto mais baixo do selo — que recebe o nome do escrevente, e
    não a conta — sabe quem pediu. Lê pela extensão `usuario_papel_real` do
    app, a mesma que a auditoria usa.
    """
    try:
        from flask import current_app, has_request_context
        if not has_request_context():
            return None
        ler = current_app.extensions.get("usuario_papel_real")
        return ler() if ler else None
    except Exception:  # noqa: BLE001 — fora do Flask a régua não tem o que ler
        return None


def sessao_pode_selar() -> bool:
    """A conta logada sela? Fora de requisição, sim (a régua não decide)."""
    return pode_selar(papel_da_sessao())


#: A REDE DE CIMA (T015): o POST destas rotas sela — além de toda rota cujo
#: nome tem «selar». A recusa de verdade mora no ponto mais baixo do selo; esta
#: rede responde 403 antes de a rota começar, para o caminho que grava o NÚMERO
#: do selo direto na coluna do ato, sem passar pelo razão (o selo digitado do
#: reconhecimento e da autenticação, o da apostila) — e para o que vier depois.
ROTAS_QUE_SELAM: frozenset[str] = frozenset({
    "apostila_selo",                  # grava o selo que chegou depois
    "notas_autenticacao_selo",        # anota o selo digitado na autenticação
    "rcpn_certidao_eletronica_selo",  # sela a certidão eletrônica da CRC
    "protesto_selo_que_faltou",       # emite o selo que faltou no ato
    "rcpj_rtd_etiquetas_selos_externos",  # reimprime a etiqueta do selo
    "notas_veiculo_comunicar",        # «Selar e comunicar» (DETRAN)
    "rcpj_rtd_livro_contabil_autenticar",  # «Autenticar e selar» o livro
})

#: Os campos do selo DIGITADO: com algum deles preenchido, o POST grava selo.
CAMPOS_DO_SELO: tuple[str, ...] = ("selo", "selo_texto", "selo_a_mao")


def rota_sela(endpoint: Any, formulario: Any = None) -> bool:
    """Este POST sela (ou grava o número de um selo)? Só calcula."""
    nome = str(endpoint or "")
    if "selar" in nome or nome in ROTAS_QUE_SELAM:
        return True
    if formulario is None:
        return False
    try:
        return any(str(formulario.get(c) or "").strip() for c in CAMPOS_DO_SELO)
    except AttributeError:
        return False


# ----------------------------------------------------------- sem escalada


def recusa_de_papel(ator: Any, *, alvo: Any = None, papel_novo: Any = None,
                    mexe_na_conta: bool = False) -> str | None:
    """O ator pode dar `papel_novo` ao `alvo` (ou mexer na conta dele)? Só calcula.

    Devolve a frase da recusa, ou None. Só o TI tem trava aqui:
      - não dá o papel ADMIN a ninguém, nem a si;
      - não troca o próprio papel;
      - não mexe na conta de um ADMIN (papel, senha, ativação, marca de robô):
        tomada a conta, ele selaria por ela.
    Criar e editar usuários dos outros papéis, inclusive TI, continua dele.
    """
    if papel_de(ator) != TI:
        return None
    novo = _texto(papel_novo)
    alvo_papel = papel_de(alvo) if alvo is not None else ""
    if alvo is not None and alvo_papel == ADMIN and (mexe_na_conta or novo):
        return ("O papel TI não altera a conta de um ADMIN (papel, senha, "
                "ativação, função ou marca de robô). Peça ao oficial.")
    if novo == ADMIN:
        return ("O papel TI não dá o papel ADMIN a ninguém, nem a si mesmo. "
                "Peça ao oficial.")
    eu = _id(ator)
    if (novo and alvo is not None and eu is not None and _id(alvo) == eu
            and novo != papel_de(ator)):
        return "O papel TI não troca o próprio papel. Peça ao oficial."
    return None


def _id(quem: Any) -> int | None:
    try:
        return int(quem["id"])
    except (KeyError, IndexError, TypeError, ValueError):
        return None
