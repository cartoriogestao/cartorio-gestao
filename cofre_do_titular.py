"""A PARTE DO BACKUP QUE SÓ O TITULAR ABRE — despesas e livro-caixa, cifrados com a chave dele.

Ordem do oficial (31/10/2026): «o balanço deve ser privado do usuário administrador e deve
ficar criptografado no backup da serventia», e «em caso de transferência de delegatário, o
livro-caixa não ficaria aberto para o novo».

POR QUE NÃO É A CIFRA QUE O BACKUP JÁ TEM
    A cifra do pacote (`backup.py`) é da SERVENTIA: a senha mora no cofre do servidor, porque
    o backup sai sozinho de madrugada. Quem recebe o servidor abre tudo. Aqui é ao contrário:
    o servidor guarda só a chave PÚBLICA, que fecha e não abre. A privada só existe cifrada
    pela senha do titular, e a senha não fica em lugar nenhum.

O QUE VAI FECHADO
    As tabelas de `TABELAS` e os anexos das despesas (`arquivos/despesas`), com o Livro Diário
    Auxiliar: «sim, fecha» (oficial, 01/11/2026). As receitas e os selos não: são dos atos, e
    seguem para o sucessor. O livro é cobrado pela Corregedoria (CN-MA, art. 207): o titular que
    sai gera e entrega o que for devido antes de selar.

SEM A CHAVE, NADA MUDA
    O backup sai como sempre, com tudo dentro e aberto, e a tela diz isso. Fechar sem chave
    seria perder o dado no primeiro desastre.

A SENHA ESQUECIDA NÃO SE RECUPERA
    O arquivo fechado se perde; o resto do pacote continua abrindo. É o preço de o sucessor,
    o suporte e quem tem o servidor não abrirem.

A PROVA DE QUE VOLTA
    Ao fechar, decifra-se de novo e compara-se o SHA-256 (a régua de `backup.py`). Isso prova
    a cifra, e não a senha: por isso `backup.py abrir-titular` existe, e o titular deve abrir
    um pacote uma vez depois de criar a chave. A automação não tem como fazer isso por ele.
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import zipfile
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

import backup as BKP

TABELAS = ("dp_despesas", "dp_eventos", "dp_recorrentes", "cl_marcacoes", "cl_lancamentos",
           "ld_despesas", "ld_geracoes")
#: `dp_eventos` aponta para `dp_despesas`, e `cl_marcacoes` para `ld_despesas`: saem antes.
NA_ORDEM_DE_APAGAR = ("dp_eventos", "dp_despesas", "dp_recorrentes", "cl_marcacoes", "cl_lancamentos",
                      "ld_geracoes", "ld_despesas")
#: A pasta dos anexos das despesas dentro de `arquivos` (`despesas_web._pasta`).
PASTA_DOS_ANEXOS = "despesas"
NOME_DAS_TABELAS = "privado_do_titular/tabelas.cgt"
NOME_DOS_ANEXOS = "privado_do_titular/anexos.cgt"

CHAVE_PUBLICA = "titular_chave_publica"
CHAVE_PRIVADA = "titular_chave_privada"
CHAVE_DE_QUEM = "titular_chave_de"
CHAVE_QUANDO = "titular_chave_em"
AS_QUATRO = (CHAVE_PUBLICA, CHAVE_PRIVADA, CHAVE_DE_QUEM, CHAVE_QUANDO)

MINIMO_DA_SENHA = 12
_MAGIA = b"CG-TITULAR-1\n"
_OAEP = padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)


class CofreDoTitularError(ValueError):
    """Impedimento de regra, com a frase pronta para a tela."""


def impressao(publica_pem: str) -> str:
    """O que identifica a chave sem revelar nada. Só calcula."""
    return hashlib.sha256(publica_pem.encode("ascii")).hexdigest()[:16]


def _abrir_privada(privada_pem: str, senha: str):
    try:
        return serialization.load_pem_private_key(privada_pem.encode("ascii"), password=str(senha).encode("utf-8"))
    except (ValueError, TypeError) as erro:
        raise CofreDoTitularError("A senha do titular não abre esta chave.") from erro


def gerar_chave(senha: str, *, de_quem: str, agora: datetime) -> dict[str, str]:
    """O par de chaves, com a privada fechada pela senha. Só calcula. A senha não fica."""
    if len(str(senha or "")) < MINIMO_DA_SENHA:
        raise CofreDoTitularError(f"A senha do titular precisa de ao menos {MINIMO_DA_SENHA} caracteres.")
    privada = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    return {
        CHAVE_PUBLICA: privada.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode("ascii"),
        CHAVE_PRIVADA: privada.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.BestAvailableEncryption(str(senha).encode("utf-8"))).decode("ascii"),
        CHAVE_DE_QUEM: " ".join(str(de_quem or "").split()),
        CHAVE_QUANDO: agora.isoformat(timespec="seconds"),
    }


def criar_chave(db, senha: str, confirmacao: str, *, de_quem: str, agora: datetime,
                senha_atual: str = "") -> str:
    """Grava a chave do titular. ESCREVE. Devolve a impressão.

    Trocar pede a senha atual: quem só tem o login de ADMIN não troca a chave por uma dele,
    e os pacotes seguintes passariam a abrir para ele. Os pacotes antigos continuam abrindo
    com a senha antiga, porque cada um leva a privada da época.
    """
    if senha != confirmacao:
        raise CofreDoTitularError("As duas senhas não são iguais.")
    atual = dados_da_chave(db)
    if atual:
        _abrir_privada(atual[CHAVE_PRIVADA], senha_atual)
    nova = gerar_chave(senha, de_quem=de_quem, agora=agora)
    db.set_settings(nova)
    return impressao(nova[CHAVE_PUBLICA])


def dados_da_chave(db) -> dict[str, str] | None:
    """A chave gravada, ou None. Só LÊ. Banco de teste sem configurações não tem chave."""
    try:
        cfg = db.get_settings()
    except AttributeError:
        return None
    if not (cfg.get(CHAVE_PUBLICA) and cfg.get(CHAVE_PRIVADA)):
        return None
    return {k: cfg.get(k) or "" for k in AS_QUATRO}


def situacao_para_a_tela(db) -> dict[str, Any]:
    chave = dados_da_chave(db)
    if not chave:
        return {"tem": False}
    return {"tem": True, "de": chave[CHAVE_DE_QUEM], "em": chave[CHAVE_QUANDO],
            "impressao": impressao(chave[CHAVE_PUBLICA])}


def fechar(origem: Path, destino: Path, chave: dict[str, str]) -> Path:
    """Cifra `origem` para o titular e confere a volta. ESCREVE EM DISCO."""
    senha_do_arquivo = secrets.token_urlsafe(48)
    publica = serialization.load_pem_public_key(chave[CHAVE_PUBLICA].encode("ascii"))
    cabecalho = json.dumps({
        "embrulhada": base64.b64encode(publica.encrypt(senha_do_arquivo.encode("ascii"), _OAEP)).decode("ascii"),
        "privada": chave[CHAVE_PRIVADA], "de": chave[CHAVE_DE_QUEM], "em": chave[CHAVE_QUANDO],
        "impressao": impressao(chave[CHAVE_PUBLICA]),
    }).encode("ascii")
    with TemporaryDirectory() as tmp:
        cifrado = Path(tmp) / "cifrado"
        BKP.cifrar_arquivo(Path(origem), cifrado, senha_do_arquivo)
        if BKP._sha256_decifrado(cifrado, senha_do_arquivo) != BKP._sha256(Path(origem)):
            raise BKP.BackupInvalido("a parte do titular não abriu de volta depois de cifrada")
        with Path(destino).open("wb") as saida, cifrado.open("rb") as entrada:
            saida.write(_MAGIA + len(cabecalho).to_bytes(4, "big") + cabecalho)
            while bloco := entrada.read(1024 * 1024):
                saida.write(bloco)
    return Path(destino)


def abrir(fechado: Path, destino: Path, senha: str) -> dict[str, str]:
    """Devolve o arquivo original, com a senha do titular. ESCREVE EM DISCO."""
    with Path(fechado).open("rb") as entrada:
        if entrada.read(len(_MAGIA)) != _MAGIA:
            raise CofreDoTitularError("Este arquivo não é a parte do titular de um backup.")
        cabecalho = json.loads(entrada.read(int.from_bytes(entrada.read(4), "big")).decode("ascii"))
        privada = _abrir_privada(cabecalho["privada"], senha)
        try:
            senha_do_arquivo = privada.decrypt(base64.b64decode(cabecalho["embrulhada"]), _OAEP).decode("ascii")
        except ValueError as erro:
            raise CofreDoTitularError("A chave não abre este arquivo: ele se corrompeu.") from erro
        with TemporaryDirectory() as tmp:
            cifrado = Path(tmp) / "cifrado"
            with cifrado.open("wb") as saida:
                while bloco := entrada.read(1024 * 1024):
                    saida.write(bloco)
            BKP.decifrar_arquivo(cifrado, Path(destino), senha_do_arquivo)
    return {"de": cabecalho.get("de", ""), "em": cabecalho.get("em", "")}


def juntar_os_anexos(raiz: Path, destino: Path) -> int:
    """Zipa `arquivos/despesas`. Devolve quantos. ESCREVE EM DISCO."""
    n = 0
    pasta = Path(raiz) / PASTA_DOS_ANEXOS
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as zf:
        if pasta.is_dir():
            for p in sorted(pasta.rglob("*")):
                if p.is_file():
                    zf.write(p, p.relative_to(pasta).as_posix())
                    n += 1
    return n


def e_anexo_privado(relativo: Path) -> bool:
    return bool(relativo.parts) and relativo.parts[0] == PASTA_DOS_ANEXOS


def abrir_do_pacote(pacote_zip: Path, pasta: Path, senha: str) -> list[Path]:
    """Tira a parte do titular do zip do backup, aberta. ESCREVE EM DISCO."""
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    saidas = []
    with zipfile.ZipFile(pacote_zip) as zf, TemporaryDirectory() as tmp:
        nomes = set(zf.namelist())
        if NOME_DAS_TABELAS not in nomes:
            raise CofreDoTitularError("Este pacote não tem parte do titular: os dados vieram abertos no banco.")
        for nome, saida in ((NOME_DAS_TABELAS, "tabelas_do_titular.dump"), (NOME_DOS_ANEXOS, "anexos_do_titular.zip")):
            if nome in nomes:
                fechado = Path(zf.extract(nome, tmp))
                abrir(fechado, pasta / saida, senha)
                saidas.append(pasta / saida)
    return saidas


def apagar_arquivo(caminho: Path) -> None:
    """Apaga o arquivo. Apagar não sobrescreve o disco: quem tiver o disco pode recuperá-lo."""
    Path(caminho).unlink(missing_ok=True)
