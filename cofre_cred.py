"""O COFRE: os segredos que moravam no banco, num `.cred` CIFRADO fora dele
(lote LX14, 19/10/2026; A8 do LS03).

O ACHADO
    As Centrais, o selador e as chaves do Claude já guardavam a senha em
    arquivo na pasta de dados, fora do banco (`centrais_cred`). Duas telas
    tinham ficado para trás e guardavam o segredo NO BANCO, em texto claro:

        robo_config   as chaves de API dos robôs (Grok, GPT, Claude, DeepSeek)
        wa_config     o token e o `app_secret` da Meta, o `verify_token` e o
                      segredo da caixa-postal do WhatsApp

    O banco viaja: todo backup diário (`pg_dump`) as levava, e o backup desta
    serventia já saiu daqui mais de uma vez. Com este módulo, o segredo sai da
    coluna e vai para `robos.cred` e `whatsapp.cred`; a senha opcional da
    cifra do backup mora em `backup.cred`. No banco fica só o que não é
    segredo (o provedor padrão, o `phone_number_id`, a `caixa_url`).

    `avisos.cred` (24/10/2026) guarda a senha do SMTP que a automação usa para
    mandar os alertas por e-mail. Ela NÃO mora no cofre da senha-mestra
    (`automacao_cofre`): depois de religar a máquina, até o oficial digitar a
    senha-mestra, aquele cofre está trancado — e o aviso «o cofre está
    trancado» é justamente um dos que precisam sair por e-mail.

POR QUE CIFRADO, E O QUE A CIFRA NÃO FAZ
    O `.cred` é AES-GCM com uma chave de 256 bits do arquivo `cofre.key`, ao
    lado dele. Isto NÃO protege de quem tem o disco inteiro do servidor — o
    servidor precisa da chave para usar o segredo, e quem tem o disco tem a
    chave (é o que `selador_config` já diz, e continua verdade). O que a
    cifra compra é concreto: um `.cred` copiado sozinho — num pendrive, numa
    pasta espelhada, num anexo — não abre. E o nome do arquivo entra como dado
    associado: o `robos.cred` copiado por cima do `whatsapp.cred` também não
    abre, em vez de entregar a chave de um serviço a outro.

PERDER A CHAVE NÃO TRANCA NADA
    Sem o `cofre.key` (máquina nova, restauração), o cofre lê vazio, as telas
    dizem «não configurado» e o oficial digita o segredo de novo — o mesmo de
    quando os `*.cred` das Centrais não vêm junto. Nada no banco depende dele.

QUEM DESCOBRE A PASTA É A CONEXÃO
    `ler_config(con, chave)` e `gravar_config(con, chave, valor)` dos robôs e
    do WhatsApp não recebiam a pasta, e a assinatura não muda: a conexão da
    ponte sabe onde está o banco (`db_path`), e a pasta de dados é a dele —
    a mesma `DATA_DIR` onde moram `secret.key` e os outros `.cred`.
"""
from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path
from typing import Any, Iterable

import banco_pg
import permissao_local as PERM
from bd_nativo import Banco, banco

LOG = logging.getLogger("cartorio.cofre")

NOME_DA_CHAVE = "cofre.key"
ROBOS = "robos.cred"
WHATSAPP = "whatsapp.cred"
BACKUP = "backup.cred"
AVISOS = "avisos.cred"
# A credencial do Banco Inter (`despesas_inter`): Client Secret e a chave
# privada do certificado. Entrou em 26/10/2026 (revisão de segurança dos PRs
# abertos): a primeira versão a gravava num `.json` em texto claro.
BANCO_INTER = "banco_inter.cred"
# A CHAVE QUE ASSINA O RETRATO DO PAINEL (26/10/2026, `painel_retrato`): a
# privada Ed25519 com que o servidor assina os números agregados que empurra
# para a VPS. Na VPS fica só a pública — quem a lê lá não forja retrato.
PAINEL = "painel.cred"
# O PORTAL DO CLIENTE (26/10/2026): a chave que cifra os códigos de
# acompanhamento dos protocolos (`acompanhamento_cliente`) e o token com que o
# servidor empurra o retrato dos protocolos para a VPS (`portal_cliente`).
PORTAL = "portal.cred"
ARQUIVOS = (ROBOS, WHATSAPP, BACKUP, AVISOS, BANCO_INTER, PAINEL, PORTAL)

FORMATO = "cg-cofre-1"
CODIFICACAO = "utf-8-sig"


class CofreError(RuntimeError):
    """O cofre não pôde ser lido ou gravado, com a frase pronta."""


# ---------------------------------------------------------------- a pasta


def pasta_do_banco(con: Any) -> Path:
    """A pasta de dados daquele banco — onde moram `secret.key` e os `.cred`."""
    alvo = con._ponte if isinstance(con, Banco) else con
    caminho = getattr(alvo, "db_path", None)
    if not caminho:
        raise CofreError(
            "Não sei onde fica a pasta de dados desta conexão; o cofre precisa "
            "da conexão do sistema (a de `db.connect()`).")
    return Path(banco_pg._caminho_e_modo(caminho)[0]).parent


# ---------------------------------------------------------------- a chave


def _chave(pasta: Path, criar: bool) -> bytes | None:
    caminho = Path(pasta) / NOME_DA_CHAVE
    if not caminho.exists():
        if not criar:
            return None
        caminho.parent.mkdir(parents=True, exist_ok=True)
        try:
            # `xb`: duas gravações ao mesmo tempo não criam duas chaves.
            with open(caminho, "xb") as f:
                f.write(base64.b64encode(os.urandom(32)))
        except FileExistsError:
            pass
        PERM.restringir(caminho, pasta=False)
    try:
        chave = base64.b64decode(caminho.read_bytes().strip())
    except (OSError, ValueError):
        return None
    return chave if len(chave) == 32 else None


def _ler_bruto(pasta: Path, nome: str) -> dict | None:
    """O conteúdo decifrado; {} se não há arquivo; None se há e não abre."""
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    caminho = Path(pasta) / nome
    if not caminho.is_file():
        return {}
    try:
        envelope = json.loads(caminho.read_text(encoding=CODIFICACAO)) or {}
        chave = _chave(pasta, criar=False)
        if envelope.get("formato") != FORMATO or chave is None:
            return None
        bruto = base64.b64decode(str(envelope.get("cifra") or ""))
        claro = AESGCM(chave).decrypt(bruto[:12], bruto[12:], nome.encode("ascii"))
        dados = json.loads(claro.decode("utf-8"))
    except (OSError, ValueError, InvalidTag):
        return None
    return {str(k): str(v) for k, v in dados.items()} if isinstance(dados, dict) else None


# ---------------------------------------------------------------- ler e gravar


def ler(pasta: Any, nome: str) -> dict[str, str]:
    """Os segredos daquele arquivo. Vazio quando não há — ou quando não abre.

    Arquivo que não abre (chave perdida, arquivo de outra máquina) vira vazio,
    e não erro: a tela diz «não configurado» e o oficial digita de novo.
    """
    return _ler_bruto(Path(pasta), nome) or {}


def situacao(pasta: Any, nome: str) -> str:
    """`"vazio"`, `"ok"` ou `"nao_abre"` — sem devolver segredo nenhum."""
    bruto = _ler_bruto(Path(pasta), nome)
    if bruto is None:
        return "nao_abre"
    return "ok" if bruto else "vazio"


def gravar(pasta: Any, nome: str, valores: dict[str, Any]) -> Path:
    """Junta `valores` ao que já está no arquivo e grava cifrado. ESCREVE EM DISCO.

    Valor vazio TIRA a chave. Grava num `.tmp` e troca, para que uma queda no
    meio não deixe meio arquivo — e meio arquivo não abre, o que apagaria
    todos os segredos dele de uma vez.
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    if nome not in ARQUIVOS:
        raise CofreError(f"O cofre não conhece o arquivo «{nome}».")
    base = Path(pasta)
    atual = _ler_bruto(base, nome) or {}
    for chave, valor in valores.items():
        texto = str(valor or "").strip()
        if texto:
            atual[str(chave)] = texto
        else:
            atual.pop(str(chave), None)
    chave_aes = _chave(base, criar=True)
    if chave_aes is None:
        raise CofreError(f"«{base / NOME_DA_CHAVE}» não tem uma chave válida.")
    nonce = os.urandom(12)
    cifra = AESGCM(chave_aes).encrypt(
        nonce, json.dumps(atual, ensure_ascii=False).encode("utf-8"),
        nome.encode("ascii"))
    destino = base / nome
    provisorio = base / (nome + ".tmp")
    provisorio.write_text(json.dumps({
        "formato": FORMATO,
        "cifra": base64.b64encode(nonce + cifra).decode("ascii"),
    }), encoding="utf-8")
    PERM.restringir(provisorio, pasta=False, de_novo=True)
    provisorio.replace(destino)
    PERM.restringir(destino, pasta=False, de_novo=True)
    return destino


def ler_segredo(con: Any, nome: str, chave: str) -> str:
    """Um segredo, pela conexão do sistema. Vazio quando não há."""
    return ler(pasta_do_banco(con), nome).get(chave, "")


def gravar_segredo(con: Any, nome: str, chave: str, valor: Any) -> None:
    """Um segredo, pela conexão do sistema. Vazio apaga."""
    gravar(pasta_do_banco(con), nome, {chave: valor})


# ---------------------------------------------------------------- a migração


def migrar_da_tabela(con: Any, tabela: str, chaves: Iterable[str],
                     nome: str) -> list[str]:
    """Tira os segredos de `tabela` (chave, valor) e os põe no cofre. ESCREVE.

    Roda a cada subida (`init_robo_schema`, `init_wa_schema`) e é idempotente:
    depois da primeira vez a coluna está vazia e não há o que mover.

    A ORDEM É A QUE NÃO PERDE SEGREDO: grava no cofre, LÊ DE VOLTA, e só então
    esvazia a coluna — e só das chaves que voltaram iguais. Disco cheio ou
    pasta sem permissão deixam o segredo no banco, onde estava, com um aviso no
    log; a subida não cai por isso.

    O QUE JÁ ESTÁ NO COFRE GANHA. Depois desta versão ninguém grava segredo no
    banco; se a coluna voltar a ter um, ele veio de um BACKUP ANTIGO
    restaurado — e o do cofre é o mais novo. A coluna é esvaziada do mesmo
    jeito, e o restaurar não é impedido: só não troca a chave nova pela velha.

    Devolve os NOMES das chaves que saíram da coluna — nunca o valor.
    """
    bd = banco(con)
    lista = list(chaves)
    bd._escrita()
    linhas = bd.ler(
        f"SELECT chave, valor FROM {tabela} "
        "WHERE chave = ANY(%s) AND coalesce(valor, '') <> '' "
        "ORDER BY chave FOR UPDATE", (lista,))
    if not linhas:
        return []
    try:
        pasta = pasta_do_banco(con)
        guardado = _ler_bruto(pasta, nome)
        if guardado is None:
            # O arquivo existe e não abre (chave perdida): o segredo do banco
            # é o único legível, e grava-se por cima.
            guardado = {}
        novos = {l["chave"]: str(l["valor"]).strip() for l in linhas
                 if not guardado.get(l["chave"])}
        if novos:
            gravar(pasta, nome, novos)
        conferido = ler(pasta, nome)
    except (OSError, CofreError) as erro:
        LOG.warning("SEGREDOS DE %s FICARAM NO BANCO: o cofre não gravou (%s: %s)",
                    tabela, type(erro).__name__, erro)
        return []
    saiu = [l["chave"] for l in linhas if conferido.get(l["chave"])]
    for chave in saiu:
        bd.escrever(f"UPDATE {tabela} SET valor = '' WHERE chave = %s", (chave,))
    if saiu:
        LOG.info("SEGREDOS DE %s MOVIDOS PARA %s: %s",
                    tabela, nome, ", ".join(saiu))
    return saiu
