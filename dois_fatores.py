"""A VERIFICAÇÃO EM DUAS ETAPAS (TOTP) — lote LG02, 19/10/2026.

O QUE ELA RESOLVE
    Até aqui a entrada no sistema era usuário e senha, e só. Senha anotada no
    monitor, repetida de outro serviço ou vista por cima do ombro no balcão
    abre o acervo inteiro, e o rastro sai no nome de quem a perdeu — que é o
    contrário do que o Código de Normas do MA pede: controle de acesso lógico
    «com identificação pessoal e intransferível, que permita a auditoria das
    ações realizadas» (Prov. COGEX 28/2026, art. 159, V). Com o segundo fator,
    a senha sozinha não entra: falta o código de seis dígitos que o aplicativo
    autenticador do celular da pessoa mostra.

POR QUE O ALGORITMO É ESCRITO AQUI, E NÃO O `pyotp`
    A especificação manda não trazer dependência nova, e o `pyotp` não está no
    `requirements.txt`. O TOTP é curto — um HMAC-SHA1 sobre o número do passo
    de 30 segundos (RFC 4226, § 5.3; RFC 6238, § 4) — e os testes conferem os
    vetores oficiais das duas RFCs, que é o que o `pyotp` faria por nós.

O SEGREDO É CIFRADO, E A CHAVE NÃO MORA NO BANCO
    O segredo do TOTP é o que o celular guarda: quem o tiver gera o código.
    Ele vai para o banco cifrado (AES-GCM, da `cryptography`, que já é
    exigida), e a chave fica no arquivo `dois_fatores.key` da pasta de dados —
    ao lado do `secret.key`, onde o backup não alcança. **O backup desta
    serventia já saiu daqui** (ver `centrais_cred`): um segredo em claro
    viajaria nele. O dado associado da cifra é o id do usuário, e por isso o
    segredo de um copiado para a linha de outro não abre.

    Perder o arquivo da chave (máquina nova, restauração de backup) não tranca
    ninguém: os códigos de recuperação não dependem dela, e o Gestor zera a
    verificação de quem ficou sem nenhum dos dois.

OS CÓDIGOS DE RECUPERAÇÃO SÃO HASH, E DE USO ÚNICO
    Dez, mostrados uma vez só, na ativação. O banco guarda o PBKDF2 de cada um,
    com sal próprio — como a senha (`security.py`) —, e não o código. O uso
    marca a linha com um `UPDATE ... WHERE usado_em = ''`: duas abas com o
    mesmo código não entram as duas.

O BLOQUEIO
    Cinco códigos errados seguidos travam a verificação daquele usuário por
    quinze minutos; durante a trava nem o código certo entra. A contagem lê e
    grava a mesma linha, e por isso é `FOR UPDATE` (MANUAL_DA_CONVERSAO). O
    mesmo código também não vale duas vezes (RFC 6238, § 5.2): o último passo
    aceito fica gravado, e só passo posterior a ele entra.

A HORA É DO PYTHON (regra da casa), e vem de `relogio` — o teste o troca.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import struct
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

from bd_nativo import banco

# ------------------------------------------------------------- os números

# O passo, os dígitos e o algoritmo que TODO aplicativo autenticador entende
# sem configuração (Google Authenticator, Microsoft Authenticator, FreeOTP).
# SHA-256/512 a RFC permite, mas há aplicativo que os ignora calado e mostra
# código que nunca confere — a pior forma de falhar.
PASSO_SEGUNDOS = 30
DIGITOS = 6
ALGORITMO = "sha1"

# Um passo para cada lado: o relógio do celular e o do servidor raramente
# batem no segundo, e a RFC 6238, § 6, recomenda no máximo um passo de folga.
JANELA = 1

QUANTOS_CODIGOS = 10
MAX_FALHAS = 5
BLOQUEIO_MINUTOS = 15

# Quanto tempo quem acertou a senha tem para digitar o código. Depois disso a
# meia-sessão morre e volta a pedir a senha.
PRAZO_DO_SEGUNDO_PASSO = 300

# O PBKDF2 dos códigos de recuperação. Menos que o da senha (310 mil) porque
# o código já tem 50 bits de acaso — a senha é escolhida por gente — e porque
# conferir um código percorre os dez que restam.
ITERACOES_DO_CODIGO = 60_000

# Sem 0/o, 1/l/i: o código é copiado do papel, à mão.
ALFABETO_DO_CODIGO = "abcdefghjkmnpqrstuvwxyz23456789"
TAMANHO_DO_CODIGO = 10

EMISSOR = "Cartorio Gestao"
NOME_DA_CHAVE = "dois_fatores.key"
CHAVE_DA_EXIGENCIA = "dois_fatores_papeis_exigidos"

NENHUM, PENDENTE, ATIVO = "NENHUM", "PENDENTE", "ATIVO"
TOTP, RECUPERACAO = "TOTP", "RECUPERACAO"

relogio: Callable[[], float] = time.time


class DoisFatoresError(ValueError):
    """Recusa que o balcão lê: a mensagem vai para a tela como está."""


# ----------------------------------------------------------- o algoritmo


def hotp(chave: bytes, contador: int, digitos: int = DIGITOS,
         algoritmo: str = ALGORITMO) -> str:
    """O código HOTP do `contador` (RFC 4226, § 5.3). Só calcula."""
    mac = hmac.new(chave, struct.pack(">Q", int(contador)), algoritmo).digest()
    deslocamento = mac[-1] & 0x0F
    numero = struct.unpack(">I", mac[deslocamento:deslocamento + 4])[0] & 0x7FFFFFFF
    return str(numero % (10 ** digitos)).zfill(digitos)


def passo_de(instante: float, passo: int = PASSO_SEGUNDOS) -> int:
    """O número do passo de 30 s em que o `instante` cai (RFC 6238, T0 = 0)."""
    return int(instante // passo)


def totp(chave: bytes, instante: float, digitos: int = DIGITOS,
         algoritmo: str = ALGORITMO, passo: int = PASSO_SEGUNDOS) -> str:
    """O código TOTP do `instante` (RFC 6238, § 4). Só calcula."""
    return hotp(chave, passo_de(instante, passo), digitos, algoritmo)


def novo_segredo() -> bytes:
    """160 bits de acaso, o tamanho que a RFC 4226, § 4, recomenda."""
    return secrets.token_bytes(20)


def em_base32(chave: bytes) -> str:
    """A chave como o aplicativo a pede digitada: base32 sem o `=` do fim."""
    return base64.b32encode(chave).decode("ascii").rstrip("=")


def de_base32(texto: str) -> bytes:
    """O inverso de `em_base32`, tolerante a espaço e caixa."""
    limpo = "".join(str(texto or "").split()).upper()
    return base64.b32decode(limpo + "=" * (-len(limpo) % 8))


def endereco_do_aplicativo(chave: bytes, conta: str, emissor: str = EMISSOR) -> str:
    """O `otpauth://` que o QR leva ao aplicativo autenticador.

    Os parâmetros vão escritos mesmo sendo o padrão: há aplicativo que não
    assume o padrão quando eles faltam.
    """
    rotulo = quote(f"{emissor}:{conta}", safe=":@")
    return (f"otpauth://totp/{rotulo}?secret={em_base32(chave)}"
            f"&issuer={quote(emissor)}&algorithm={ALGORITMO.upper()}"
            f"&digits={DIGITOS}&period={PASSO_SEGUNDOS}")


def qr_em_svg(endereco: str) -> str:
    """O QR do endereço, em SVG para pôr direto na tela. Vazio sem o `segno`.

    Sem o `segno` a ativação continua possível: a tela mostra a chave para
    digitar no aplicativo. Tela não cai por causa de desenho.
    """
    try:
        import segno
    except ImportError:
        return ""
    return segno.make(endereco, error="m").svg_inline(scale=4)


def chave_agrupada(chave: bytes) -> str:
    """A chave em grupos de quatro, para ditar ou digitar sem se perder."""
    b32 = em_base32(chave)
    return " ".join(b32[i:i + 4] for i in range(0, len(b32), 4))


def so_digitos(codigo: Any) -> str:
    return "".join(c for c in str(codigo or "") if c.isdigit())


def passo_aceito(chave: bytes, codigo: Any, instante: float,
                 ultimo_passo: int = 0) -> int | None:
    """O passo em que o código confere, dentro da janela e depois do último.

    Devolve None quando não confere. **Passo já usado não volta a valer**: é o
    que impede quem viu o código na tela de outro de usá-lo no mesmo minuto.
    """
    digitado = so_digitos(codigo)
    if len(digitado) != DIGITOS:
        return None
    agora = passo_de(instante)
    for passo in range(agora - JANELA, agora + JANELA + 1):
        if passo <= int(ultimo_passo or 0):
            continue
        if hmac.compare_digest(hotp(chave, passo), digitado):
            return passo
    return None


# --------------------------------------------------- os códigos de recuperação


def novos_codigos_de_recuperacao(quantos: int = QUANTOS_CODIGOS) -> list[str]:
    """Os códigos como a pessoa os anota: `abcde-fghjk`."""
    codigos = []
    while len(codigos) < quantos:
        bruto = "".join(secrets.choice(ALFABETO_DO_CODIGO)
                        for _ in range(TAMANHO_DO_CODIGO))
        # Só dígitos seria lido como código do aplicativo (`parece_recuperacao`)
        # e nunca entraria. Acontece uma vez em ~800 mil; sorteia de novo.
        if bruto.isdigit():
            continue
        codigos.append(f"{bruto[:5]}-{bruto[5:]}")
    return codigos


def normalizar_codigo(codigo: Any) -> str:
    """Sem hífen, sem espaço, em minúscula — como foi gravado o hash."""
    return "".join(c for c in str(codigo or "").lower() if c.isalnum())


def parece_recuperacao(codigo: Any) -> bool:
    limpo = normalizar_codigo(codigo)
    return len(limpo) == TAMANHO_DO_CODIGO and not limpo.isdigit()


def hash_do_codigo(codigo: str, sal: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", normalizar_codigo(codigo).encode("ascii"),
                               sal, ITERACOES_DO_CODIGO).hex()


# ------------------------------------------------------------- a cifra


def _caminho_da_chave(pasta: Any) -> Path:
    if pasta in (None, ""):
        raise DoisFatoresError("quem chamou não disse a pasta de dados")
    return Path(pasta) / NOME_DA_CHAVE


def chave_do_cofre(pasta: Any, criar: bool = True) -> bytes | None:
    """A chave AES de 256 bits, do arquivo da pasta de dados.

    Nasce na primeira ativação, com `open(..., "xb")`: duas máquinas ativando
    ao mesmo tempo não gravam duas chaves — a segunda acha o arquivo pronto e
    o lê. Sem `criar`, devolve None quando ela não existe.
    """
    caminho = _caminho_da_chave(pasta)
    if not caminho.exists():
        if not criar:
            return None
        caminho.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(caminho, "xb") as f:
                f.write(base64.b64encode(os.urandom(32)))
            try:
                os.chmod(caminho, 0o600)
            except OSError:
                pass
        except FileExistsError:
            pass
    chave = base64.b64decode(caminho.read_bytes().strip())
    if len(chave) != 32:
        raise DoisFatoresError(f"{NOME_DA_CHAVE} não tem uma chave válida")
    return chave


def _associado(user_id: int) -> bytes:
    return f"cg-dois-fatores:{int(user_id)}".encode("ascii")


def cifrar(segredo: bytes, user_id: int, pasta: Any) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = os.urandom(12)
    corpo = AESGCM(chave_do_cofre(pasta)).encrypt(nonce, segredo, _associado(user_id))
    return "v1." + base64.urlsafe_b64encode(nonce + corpo).decode("ascii")


def decifrar(cifrado: str, user_id: int, pasta: Any) -> bytes | None:
    """O segredo, ou None quando a chave sumiu ou não é a que cifrou."""
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if not str(cifrado or "").startswith("v1."):
        return None
    chave = chave_do_cofre(pasta, criar=False)
    if chave is None:
        return None
    try:
        bruto = base64.urlsafe_b64decode(str(cifrado)[3:].encode("ascii"))
        return AESGCM(chave).decrypt(bruto[:12], bruto[12:], _associado(user_id))
    except (InvalidTag, ValueError):
        return None


# ------------------------------------------------------------ a hora


def agora_iso() -> str:
    return datetime.fromtimestamp(relogio()).replace(microsecond=0).isoformat()


def _somar_minutos(iso: str, minutos: int) -> str:
    return (datetime.fromisoformat(iso) + timedelta(minutes=minutos)).isoformat()


# ------------------------------------------------------------- o esquema

# TABELA NOVA, UM COMANDO POR OBJETO, E CADA UM SÓ SE O OBJETO FALTA — o
# `to_regclass` acha tabela e índice (o padrão do `ia_uso`).
SCHEMA: tuple[tuple[str, str], ...] = (
    ("dois_fatores", """
        CREATE TABLE IF NOT EXISTS dois_fatores (
            user_id bigint PRIMARY KEY REFERENCES users(id),
            situacao TEXT NOT NULL CHECK (situacao IN ('PENDENTE', 'ATIVO')),
            segredo_cifrado TEXT NOT NULL,
            ultimo_passo bigint NOT NULL DEFAULT 0,
            falhas integer NOT NULL DEFAULT 0,
            bloqueado_ate TEXT NOT NULL DEFAULT '',
            criado_em TEXT NOT NULL,
            ativado_em TEXT NOT NULL DEFAULT ''
        )"""),
    ("dois_fatores_recuperacao", """
        CREATE TABLE IF NOT EXISTS dois_fatores_recuperacao (
            id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            user_id bigint NOT NULL REFERENCES users(id),
            sal TEXT NOT NULL,
            hash TEXT NOT NULL,
            criado_em TEXT NOT NULL,
            usado_em TEXT NOT NULL DEFAULT ''
        )"""),
    ("ix_dois_fatores_recuperacao_user",
     "CREATE INDEX IF NOT EXISTS ix_dois_fatores_recuperacao_user "
     "ON dois_fatores_recuperacao (user_id, id)"),
)


def init_dois_fatores_schema(con) -> None:
    """Cria as duas tabelas e o índice que faltarem. Idempotente."""
    bd = banco(con)
    for nome, comando in SCHEMA:
        if not bd.tem_tabela(nome):
            bd.escrever(comando)


# ------------------------------------------------------------ a exigência


def papeis_exigidos(get_setting: Callable[..., str]) -> list[str]:
    """Os papéis para os quais o Gestor exigiu o segundo fator. Só LÊ.

    De fábrica, nenhum: a verificação é opcional por usuário até o Gestor
    exigi-la — ligar sozinho trancaria do lado de fora quem não tem celular
    cadastrado no dia da atualização.
    """
    try:
        papeis = json.loads(get_setting(CHAVE_DA_EXIGENCIA, "") or "[]")
    except (TypeError, ValueError):
        return []
    return [str(p) for p in papeis if str(p).strip()] if isinstance(papeis, list) else []


def exigido(get_setting: Callable[..., str], papel: Any) -> bool:
    return str(papel or "") in papeis_exigidos(get_setting)


# --------------------------------------------------------------- a leitura


def situacao(con, user_id: int, agora: str | None = None) -> dict:
    """Em que pé está a verificação do usuário. Só LÊ.

    `estado` é NENHUM, PENDENTE (chave gerada, código ainda não conferido) ou
    ATIVO. `bloqueado_ate` só vem preenchido enquanto a trava vale.
    """
    bd = banco(con)
    linha = bd.um("SELECT situacao, bloqueado_ate, ativado_em, falhas "
                  "FROM dois_fatores WHERE user_id = %s", (user_id,))
    restantes = int(bd.valor(
        "SELECT count(*) AS n FROM dois_fatores_recuperacao "
        "WHERE user_id = %s AND usado_em = ''", (user_id,)) or 0)
    if not linha:
        return {"estado": NENHUM, "restantes": 0, "bloqueado_ate": "",
                "ativado_em": "", "falhas": 0}
    agora = agora or agora_iso()
    bloqueio = linha["bloqueado_ate"] if (linha["bloqueado_ate"] or "") > agora else ""
    return {"estado": linha["situacao"], "restantes": restantes,
            "bloqueado_ate": bloqueio, "ativado_em": linha["ativado_em"] or "",
            "falhas": int(linha["falhas"] or 0)}


def segredo_pendente(con, user_id: int, pasta: Any) -> bytes | None:
    """A chave da ativação em curso, para a tela desenhar o QR. Só LÊ.

    Só a PENDENTE: depois de ativada, a chave nunca mais sai na tela.
    """
    linha = banco(con).um(
        "SELECT segredo_cifrado FROM dois_fatores "
        "WHERE user_id = %s AND situacao = 'PENDENTE'", (user_id,))
    return decifrar(linha["segredo_cifrado"], user_id, pasta) if linha else None


def resumo_da_casa(con, agora: str | None = None) -> list[dict]:
    """Cada usuário e a situação da verificação dele, para o Gestor. Só LÊ."""
    agora = agora or agora_iso()
    linhas = banco(con).ler(
        """SELECT u.id, u.username, u.full_name, u.role, u.active,
                  coalesce(d.situacao, 'NENHUM') AS estado,
                  coalesce(d.bloqueado_ate, '') AS bloqueado_ate,
                  coalesce(d.ativado_em, '') AS ativado_em,
                  (SELECT count(*) FROM dois_fatores_recuperacao r
                    WHERE r.user_id = u.id AND r.usado_em = '') AS restantes
             FROM users u
             LEFT JOIN dois_fatores d ON d.user_id = u.id
            ORDER BY u.full_name COLLATE public.cg_nocase, u.id""")
    for linha in linhas:
        linha["restantes"] = int(linha["restantes"] or 0)
        if linha["bloqueado_ate"] <= agora:
            linha["bloqueado_ate"] = ""
    return linhas


# --------------------------------------------------------------- a escrita


def iniciar(con, user_id: int, *, pasta: Any, agora: str | None = None) -> bytes:
    """Gera a chave e a guarda PENDENTE, cifrada. ESCREVE.

    Recomeçar uma ativação pendente troca a chave (o QR antigo deixa de
    valer). Com a verificação ATIVA, recusa: trocar de celular é desativar —
    com senha e código — e ativar de novo.
    """
    agora = agora or agora_iso()
    segredo = novo_segredo()
    gravou = banco(con).escrever(
        """INSERT INTO dois_fatores (user_id, situacao, segredo_cifrado, criado_em)
           VALUES (%s, 'PENDENTE', %s, %s)
           ON CONFLICT (user_id) DO UPDATE
              SET segredo_cifrado = excluded.segredo_cifrado,
                  criado_em = excluded.criado_em,
                  ultimo_passo = 0, falhas = 0, bloqueado_ate = ''
            WHERE dois_fatores.situacao = 'PENDENTE'
        RETURNING user_id""",
        (user_id, cifrar(segredo, user_id, pasta), agora))
    if not gravou:
        raise DoisFatoresError(
            "A verificação em duas etapas já está ativa. Para trocar de "
            "celular, desative-a (senha e código) e ative de novo.")
    return segredo


def cancelar(con, user_id: int) -> bool:
    """Desiste da ativação PENDENTE. ESCREVE. A ativa não se apaga por aqui."""
    return bool(banco(con).escrever(
        "DELETE FROM dois_fatores WHERE user_id = %s AND situacao = 'PENDENTE' "
        "RETURNING user_id", (user_id,)))


def preparar_codigos(quantos: int = QUANTOS_CODIGOS) -> list[tuple[str, str, str]]:
    """Os códigos novos já com sal e hash: `(código, sal, hash)`. Só CALCULA.

    CHAME ANTES DE `db.transaction()` (LX20, ressalva do LG02). São dez PBKDF2
    de 60 mil iterações — centenas de milissegundos —, e a transação da rota
    abre com a trava de escrita do banco inteiro: calculados lá dentro, a
    casa toda esperava a pessoa trocar de códigos. Aqui fora, só ela espera.
    """
    prontos = []
    for codigo in novos_codigos_de_recuperacao(quantos):
        sal = os.urandom(16)
        prontos.append((codigo, sal.hex(), hash_do_codigo(codigo, sal)))
    return prontos


def _gravar_codigos(bd, user_id: int, agora: str,
                    prontos: list[tuple[str, str, str]] | None = None) -> list[str]:
    """Troca os códigos de recuperação do usuário por dez novos. ESCREVE.

    Sem `prontos` (quem chama não os calculou fora), calcula aqui — certo,
    mas segurando a trava; as rotas os mandam prontos.
    """
    prontos = prontos or preparar_codigos()
    bd.escrever("DELETE FROM dois_fatores_recuperacao WHERE user_id = %s", (user_id,))
    for _codigo, sal, hash_ in prontos:
        bd.escrever(
            "INSERT INTO dois_fatores_recuperacao (user_id, sal, hash, criado_em) "
            "VALUES (%s, %s, %s, %s)",
            (user_id, sal, hash_, agora))
    return [codigo for codigo, _sal, _hash in prontos]


def confirmar(con, user_id: int, codigo: Any, *, pasta: Any,
              instante: float | None = None, agora: str | None = None,
              prontos: list[tuple[str, str, str]] | None = None) -> list[str]:
    """Confere o primeiro código e ATIVA. Devolve os dez códigos de recuperação.

    É o primeiro código que prova que o celular guardou a chave certa: ativar
    sem ele trancaria do lado de fora quem leu o QR torto. `prontos` vem de
    `preparar_codigos`, calculado fora da transação.
    """
    instante = relogio() if instante is None else instante
    agora = agora or agora_iso()
    bd = banco(con)
    bd._escrita()
    linha = bd.um("SELECT segredo_cifrado FROM dois_fatores "
                  "WHERE user_id = %s AND situacao = 'PENDENTE' FOR UPDATE",
                  (user_id,))
    if not linha:
        raise DoisFatoresError("Não há ativação em curso. Comece de novo.")
    segredo = decifrar(linha["segredo_cifrado"], user_id, pasta)
    if segredo is None:
        raise DoisFatoresError("A chave desta ativação não abre mais. Comece de novo.")
    passo = passo_aceito(segredo, codigo, instante)
    if passo is None:
        raise DoisFatoresError(
            "O código não confere. Confira se o relógio do celular está certo "
            "e digite o código que estiver na tela agora.")
    bd.escrever("UPDATE dois_fatores SET situacao = 'ATIVO', ultimo_passo = %s, "
                "falhas = 0, bloqueado_ate = '', ativado_em = %s WHERE user_id = %s",
                (passo, agora, user_id))
    return _gravar_codigos(bd, user_id, agora, prontos)


def conferir(con, user_id: int, codigo: Any, *, pasta: Any,
             instante: float | None = None, agora: str | None = None,
             achado: int | None = None) -> dict:
    """Confere o segundo fator de quem tem a verificação ATIVA. ESCREVE.

    `achado` é o `achar_codigo` calculado fora da transação (as rotas o
    mandam); sem ele, o código de recuperação é procurado aqui dentro.

    **NÃO LEVANTA, E É DE PROPÓSITO**: a falha também se grava (a contagem do
    bloqueio), e quem chama a confirma junto com o resto — uma exceção aqui
    desfaria a contagem no `rollback` e o bloqueio nunca chegaria.

    Devolve `{"ok", "meio", "motivo", "bloqueado_ate", "bloqueou_agora",
    "restantes", "cofre_ilegivel"}`. `meio` é TOTP ou RECUPERACAO; `motivo`,
    quando não ok, é `sem_dois_fatores`, `bloqueado` ou `codigo`.
    """
    instante = relogio() if instante is None else instante
    agora = agora or agora_iso()
    resultado = {"ok": False, "meio": "", "motivo": "", "bloqueado_ate": "",
                 "bloqueou_agora": False, "restantes": 0, "cofre_ilegivel": False}
    bd = banco(con)
    bd._escrita()
    linha = bd.um("SELECT segredo_cifrado, ultimo_passo, falhas, bloqueado_ate "
                  "FROM dois_fatores WHERE user_id = %s AND situacao = 'ATIVO' "
                  "FOR UPDATE", (user_id,))
    if not linha:
        resultado["motivo"] = "sem_dois_fatores"
        return resultado
    if (linha["bloqueado_ate"] or "") > agora:
        resultado.update(motivo="bloqueado", bloqueado_ate=linha["bloqueado_ate"])
        return resultado

    segredo = decifrar(linha["segredo_cifrado"], user_id, pasta)
    resultado["cofre_ilegivel"] = segredo is None
    passo = None
    if segredo is not None and not parece_recuperacao(codigo):
        passo = passo_aceito(segredo, codigo, instante, int(linha["ultimo_passo"] or 0))
    if passo is not None:
        bd.escrever("UPDATE dois_fatores SET ultimo_passo = %s, falhas = 0, "
                    "bloqueado_ate = '' WHERE user_id = %s", (passo, user_id))
        resultado.update(ok=True, meio=TOTP)
    elif parece_recuperacao(codigo) and _usar_codigo(bd, user_id, codigo, agora, achado):
        bd.escrever("UPDATE dois_fatores SET falhas = 0, bloqueado_ate = '' "
                    "WHERE user_id = %s", (user_id,))
        resultado.update(ok=True, meio=RECUPERACAO)
    else:
        falhas = int(linha["falhas"] or 0) + 1
        if falhas >= MAX_FALHAS:
            ate = _somar_minutos(agora, BLOQUEIO_MINUTOS)
            bd.escrever("UPDATE dois_fatores SET falhas = 0, bloqueado_ate = %s "
                        "WHERE user_id = %s", (ate, user_id))
            resultado.update(motivo="bloqueado", bloqueado_ate=ate, bloqueou_agora=True)
        else:
            bd.escrever("UPDATE dois_fatores SET falhas = %s WHERE user_id = %s",
                        (falhas, user_id))
            resultado["motivo"] = "codigo"
    resultado["restantes"] = int(bd.valor(
        "SELECT count(*) AS n FROM dois_fatores_recuperacao "
        "WHERE user_id = %s AND usado_em = ''", (user_id,)) or 0)
    return resultado


def _achar(bd, user_id: int, codigo: Any) -> int:
    """O id do código de recuperação que confere, entre os que restam; 0 se nenhum."""
    linhas = bd.ler("SELECT id, sal, hash FROM dois_fatores_recuperacao "
                    "WHERE user_id = %s AND usado_em = '' ORDER BY id", (user_id,))
    for linha in linhas:
        try:
            sal = bytes.fromhex(linha["sal"])
        except ValueError:
            continue
        if hmac.compare_digest(hash_do_codigo(codigo, sal), linha["hash"]):
            return int(linha["id"])
    return 0


def achar_codigo(con, user_id: int, codigo: Any, agora: str | None = None) -> int:
    """Qual código de recuperação o digitado é — o id, ou 0. Só LÊ.

    CHAME ANTES DE `db.transaction()` e passe o resultado ao `conferir`
    (`achado=`), pelo mesmo motivo de `preparar_codigos`: conferir um código
    é até dez PBKDF2, e dentro da transação a casa inteira esperava. Ler sem
    prender não abre brecha: quem decide é o `UPDATE ... WHERE usado_em = ''`
    do `conferir`, e um código trocado no meio simplesmente não grava.
    Bloqueado não calcula nada — o `conferir` vai recusar de qualquer jeito.
    """
    if not parece_recuperacao(codigo):
        return 0
    bd = banco(con)
    bloqueio = bd.valor("SELECT bloqueado_ate FROM dois_fatores "
                        "WHERE user_id = %s AND situacao = 'ATIVO'", (user_id,))
    if bloqueio is None or (bloqueio or "") > (agora or agora_iso()):
        return 0
    return _achar(bd, user_id, codigo)


def _usar_codigo(bd, user_id: int, codigo: Any, agora: str,
                 achado: int | None = None) -> bool:
    """Gasta o código de recuperação, se ele for um dos que restam. ESCREVE.

    O `WHERE usado_em = ''` do `UPDATE` é que decide: duas abas com o mesmo
    código, uma só entra. `achado` é o `achar_codigo` feito fora da
    transação; sem ele, a procura (e o PBKDF2) acontece aqui.
    """
    if achado is None:
        achado = _achar(bd, user_id, codigo)
    if not achado:
        return False
    return bool(bd.escrever(
        "UPDATE dois_fatores_recuperacao SET usado_em = %s "
        "WHERE id = %s AND user_id = %s AND usado_em = '' RETURNING id",
        (agora, achado, user_id)))


def desativar(con, user_id: int) -> bool:
    """Apaga a verificação e os códigos do usuário. ESCREVE.

    Quem chama já conferiu a senha e o código (tela do usuário) ou a senha do
    Gestor e o motivo (tela do Gestor). Aqui só se apaga.

    PRENDE A LINHA ANTES DE APAGAR (LX20, ressalva do LG02), como `confirmar`,
    `conferir` e `trocar_codigos`. Sem isso, a conta do usuário trocando de
    códigos e o Gestor zerando a mesma conta se cruzavam: ou cada um segurava
    o que o outro esperava (deadlock), ou os dez códigos novos chegavam depois
    do `DELETE` e ficavam órfãos — «restantes = 10» na tela do Gestor para
    uma conta sem verificação. Presa a linha, um espera o outro terminar, e o
    `DELETE` dos códigos, que vem depois, já vê os que o outro gravou.
    """
    bd = banco(con)
    bd._escrita()
    bd.um("SELECT user_id FROM dois_fatores WHERE user_id = %s FOR UPDATE", (user_id,))
    bd.escrever("DELETE FROM dois_fatores_recuperacao WHERE user_id = %s", (user_id,))
    return bool(bd.escrever("DELETE FROM dois_fatores WHERE user_id = %s "
                            "RETURNING user_id", (user_id,)))


def trocar_codigos(con, user_id: int, agora: str | None = None,
                   prontos: list[tuple[str, str, str]] | None = None) -> list[str]:
    """Dez códigos novos; os antigos deixam de valer. ESCREVE.

    Quem chama já conferiu a senha e o código. A linha da verificação fica
    presa até o fim: duas abas trocando ao mesmo tempo, sem isso, apagariam
    uma antes de a outra gravar, e sobrariam vinte códigos valendo. `prontos`
    vem de `preparar_codigos`, calculado fora da transação.
    """
    bd = banco(con)
    bd._escrita()
    if not bd.um("SELECT user_id FROM dois_fatores WHERE user_id = %s "
                 "AND situacao = 'ATIVO' FOR UPDATE", (user_id,)):
        raise DoisFatoresError("A verificação em duas etapas não está ativa.")
    return _gravar_codigos(bd, user_id, agora or agora_iso(), prontos)


def desbloquear(con, user_id: int) -> bool:
    """Tira a trava das tentativas (o Gestor, com a pessoa na frente). ESCREVE."""
    return bool(banco(con).escrever(
        "UPDATE dois_fatores SET falhas = 0, bloqueado_ate = '' "
        "WHERE user_id = %s RETURNING user_id", (user_id,)))
