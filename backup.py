"""
O pacote de backup — gerar, e provar que presta.

POR QUE ISTO SAIU DE DENTRO DO app.py
    Estava numa funcao aninhada em `create_app`, alcancavel so pela tela. Para
    fazer um backup era preciso subir o servidor, entrar como ADMIN e clicar.
    Agora e um modulo: a tela chama, e o `BACKUP_AGORA.cmd` tambem — sem
    administrador e sem navegador.

    Uma implementacao so. Duas fariam a do script divergir da da tela, e a que
    divergisse seria descoberta no dia da restauracao.

BACKUP QUE MENTE E PIOR QUE BACKUP QUE FALTA
    O diario do projeto registra isto desde a primeira tentativa, que gravou
    direto no nome final, foi interrompida, e deixou 158 MB de arquivo
    corrompido com cara de backup bom.

    A correcao estava anotada no diario e NAO ESTAVA NO CODIGO — o `app.py`
    seguia escrevendo direto em `target`. Aqui esta, e desta vez com teste:

      1. grava em `<nome>.parcial`
      2. FECHA o arquivo
      3. REABRE e confere: o zip esta integro? o banco esta la dentro? o
         SHA-256 do banco bate com o que o manifesto diz?
      4. so entao renomeia para o nome final

    Interrompeu no meio? Fica um `.parcial`, que ninguem confunde com backup
    pronto. Deu erro na conferencia? O `.parcial` fica para exame e o nome bom
    nao aparece.

DUAS MODALIDADES, PORQUE OS DADOS TEM NATUREZAS DIFERENTES
    banco     muda o tempo todo e e pequeno   -> copia diaria
    arquivos  digitalizacoes sao imutaveis    -> copia semanal
              e pesam cerca de 161 MB

    Guardar trinta copias identicas de 161 MB gastaria uns 4,8 GB para
    proteger exatamente o mesmo conteudo que uma copia ja protege.

A CIFRA DO PACOTE E OPCIONAL, E NASCE DESLIGADA (LX14, 19/10/2026; A7 do LS03)
    O zip leva o banco inteiro e, no completo, o acervo do E-Oficio — com a
    senha do selador e o `Secret_Code` do CNIB em texto claro, dentro dele. E
    o backup sai da serventia (o espelho fora do servidor e exigencia do
    Provimento CN-CNJ 213/2026). Com a senha da cifra gravada no cofre
    (`backup.cred`, ver `cofre_cred`), o pacote sai cifrado: AES-256-GCM em
    blocos de 1 MiB, chave derivada da senha por scrypt. Sem a senha, o
    pacote e o zip de sempre.

    O NOME NAO MUDA (`backup_banco_<data>.zip`): a retencao, a conferencia do
    dia e o espelho procuram por ele. Quem diz se e cifrado sao os primeiros
    bytes (`MAGIA_DA_CIFRA`).

    A RESTAURACAO ACEITA OS DOIS, e e a regra que nao se negocia: o backup e o
    caminho de volta da virada, e nada aqui pode impedir de abrir um backup
    antigo. `abrir()` (e `python backup.py abrir <pacote> <saida.zip>`) devolve
    sempre o zip de sempre — copiado, se ja era, ou decifrado, se nao era. Ver
    `docs/BACKUP.md`.

    A conferencia do pacote cifrado nao confia na cifra: decifra de novo e
    compara o SHA-256 com o do zip que ja tinha passado na conferencia. So
    entao o nome definitivo aparece.

A CONFERENCIA PROVA O ARQUIVO; SO A RESTAURACAO PROVA O BANCO (26/10/2026)
    Zip integro e SHA-256 batendo dizem que o pacote e o que foi gravado — e
    nao que ele volta a ser um banco. Por isso o manifesto leva agora o
    formato do banco (`banco_formato`) e as linhas de cada tabela contadas no
    MESMO instantaneo do pg_dump (`banco_contagens`), e o teste de restauracao
    (`backup_restauracao`, processo da automacao) restaura num banco
    descartavel e confere contra elas. A rodada automatica (o diario, o
    completo e a retencao) mora em `backup_rotina`.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

NOME_BANCO = "banco/cartorio_gestao.sqlite3"
NOME_MANIFESTO = "manifesto.json"

# O PACOTE CIFRADO. Os primeiros bytes dizem que ele e cifrado; depois vem uma
# linha de cabecalho (JSON) com o sal e os parametros do scrypt; depois os
# blocos, cada um com o tamanho na frente. O cabecalho, o numero do bloco e a
# marca de «ultimo» entram como dado associado: trocar bloco de lugar, tirar o
# fim ou mexer no cabecalho faz a abertura recusar, em vez de devolver um zip
# truncado com cara de bom.
MAGIA_DA_CIFRA = b"CG-BACKUP-CIFRADO\n"
FORMATO_DA_CIFRA = "cg-backup-cifrado-1"
BLOCO_DA_CIFRA = 1024 * 1024
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 15, 8, 1
# O QUE O CABECALHO PODE PEDIR (LX20, observacao da revisao do LX14). Os
# parametros do scrypt e o tamanho do bloco vem do proprio pacote, e sao lidos
# ANTES de a senha ser conferida: um pacote fabricado com `n` enorme fazia o
# `abrir` gastar memoria e CPU sem fim antes de recusar. O teto fica bem
# acima do que esta casa grava (n = 2**15, bloco de 1 MiB).
TETO_SCRYPT_N, TETO_SCRYPT_R, TETO_SCRYPT_P = 2 ** 20, 16, 4
TETO_DO_BLOCO = 16 * BLOCO_DA_CIFRA
MINIMO_DA_SENHA = 12


class BackupInvalido(RuntimeError):
    """O pacote foi gerado mas nao passou na conferencia."""


def _sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as fh:
        for bloco in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


#: Os primeiros bytes do `pg_dump -Fc` e do arquivo do SQLite. O nome do banco
#: dentro do pacote continua `cartorio_gestao.sqlite3` desde a migração (ver
#: `docs/BACKUP.md`); quem diz o que ele é são estes bytes.
MAGIA_DO_PG_DUMP = b"PGDMP"
MAGIA_DO_SQLITE = b"SQLite format 3\x00"
FORMATO_PG_DUMP = "pg_dump-Fc"
FORMATO_SQLITE = "sqlite"


def formato_do_banco(arquivo: Path) -> str:
    """`pg_dump-Fc`, `sqlite` ou `desconhecido` — pelos primeiros bytes."""
    with Path(arquivo).open("rb") as fh:
        inicio = fh.read(len(MAGIA_DO_SQLITE))
    if inicio.startswith(MAGIA_DO_PG_DUMP):
        return FORMATO_PG_DUMP
    if inicio.startswith(MAGIA_DO_SQLITE):
        return FORMATO_SQLITE
    return "desconhecido"


def _aceita_contagens(db) -> bool:
    """O `backup_database` deste banco sabe devolver as contagens?"""
    import inspect
    try:
        return "contagens" in inspect.signature(db.backup_database).parameters
    except (TypeError, ValueError, AttributeError):
        return False


# ------------------------------------------------------------- a cifra


def e_cifrado(pacote: Path) -> bool:
    """O pacote comeca pela marca da cifra? So le os primeiros bytes."""
    try:
        with Path(pacote).open("rb") as fh:
            return fh.read(len(MAGIA_DA_CIFRA)) == MAGIA_DA_CIFRA
    except OSError:
        return False


def _aes(senha: str, sal: bytes, n: int, r: int, p: int):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    chave = Scrypt(salt=sal, length=32, n=n, r=r, p=p).derive(
        str(senha).encode("utf-8"))
    return AESGCM(chave)


def _associado(cabecalho: bytes, i: int, ultimo: bool) -> bytes:
    return cabecalho + i.to_bytes(8, "big") + (b"\x01" if ultimo else b"\x00")


def cifrar_arquivo(origem: Path, destino: Path, senha: str) -> Path:
    """Grava em `destino` a versao cifrada de `origem`. ESCREVE EM DISCO."""
    if not str(senha or ""):
        raise BackupInvalido("a cifra precisa de uma senha")
    sal, prefixo = os.urandom(16), os.urandom(8)
    cabecalho = MAGIA_DA_CIFRA + json.dumps({
        "formato": FORMATO_DA_CIFRA, "kdf": "scrypt",
        "n": SCRYPT_N, "r": SCRYPT_R, "p": SCRYPT_P,
        "sal": base64.b64encode(sal).decode("ascii"),
        "prefixo": base64.b64encode(prefixo).decode("ascii"),
        "bloco": BLOCO_DA_CIFRA,
    }, sort_keys=True).encode("ascii") + b"\n"
    aes = _aes(senha, sal, SCRYPT_N, SCRYPT_R, SCRYPT_P)
    with Path(origem).open("rb") as fo, Path(destino).open("wb") as fd:
        fd.write(cabecalho)
        atual, i = fo.read(BLOCO_DA_CIFRA), 0
        while True:
            proximo = fo.read(BLOCO_DA_CIFRA)
            ultimo = not proximo
            corpo = aes.encrypt(prefixo + i.to_bytes(4, "big"), atual,
                                _associado(cabecalho, i, ultimo))
            fd.write(len(corpo).to_bytes(4, "big") + corpo)
            if ultimo:
                break
            atual, i = proximo, i + 1
    return Path(destino)


def _decifrar(origem: Path, senha: str, escrever) -> None:
    """Decifra `origem` bloco a bloco, entregando cada um a `escrever`.

    Levanta `BackupInvalido` com a frase do problema: senha que nao abre,
    pacote truncado ou adulterado. Nada e entregue de um bloco que nao passou
    na autenticacao.
    """
    from cryptography.exceptions import InvalidTag
    if not str(senha or ""):
        raise BackupInvalido("o pacote é cifrado: informe a senha da cifra")
    with Path(origem).open("rb") as fh:
        if fh.read(len(MAGIA_DA_CIFRA)) != MAGIA_DA_CIFRA:
            raise BackupInvalido("o arquivo não é um pacote cifrado")
        linha = fh.readline(4096)
        try:
            meta = json.loads(linha.decode("ascii"))
            sal = base64.b64decode(meta["sal"])
            prefixo = base64.b64decode(meta["prefixo"])
            bloco = int(meta["bloco"])
            n, r, p = int(meta["n"]), int(meta["r"]), int(meta["p"])
            if not (0 < n <= TETO_SCRYPT_N and 0 < r <= TETO_SCRYPT_R
                    and 0 < p <= TETO_SCRYPT_P and 0 < bloco <= TETO_DO_BLOCO):
                raise BackupInvalido(
                    "o cabeçalho do pacote cifrado pede parâmetros fora do que "
                    "esta casa grava")
            aes = _aes(senha, sal, n, r, p)
        except (ValueError, KeyError, TypeError) as erro:
            raise BackupInvalido(
                f"o cabeçalho do pacote cifrado não se lê: {erro}") from erro
        if meta.get("formato") != FORMATO_DA_CIFRA:
            raise BackupInvalido(
                f"formato de cifra desconhecido: {meta.get('formato')!r}")
        cabecalho = MAGIA_DA_CIFRA + linha
        i = 0
        while True:
            tamanho = fh.read(4)
            if len(tamanho) < 4:
                raise BackupInvalido(
                    "o pacote cifrado está truncado: acabou antes do último bloco")
            n = int.from_bytes(tamanho, "big")
            if not 16 <= n <= bloco + 16:
                raise BackupInvalido("o pacote cifrado está corrompido")
            corpo = fh.read(n)
            if len(corpo) < n:
                raise BackupInvalido(
                    "o pacote cifrado está truncado: acabou no meio de um bloco")
            nonce = prefixo + i.to_bytes(4, "big")
            ultimo = False
            try:
                claro = aes.decrypt(nonce, corpo, _associado(cabecalho, i, False))
            except InvalidTag:
                try:
                    claro = aes.decrypt(nonce, corpo, _associado(cabecalho, i, True))
                    ultimo = True
                except InvalidTag:
                    raise BackupInvalido(
                        "a senha não abre este pacote — ou ele foi adulterado"
                    ) from None
            escrever(claro)
            if ultimo:
                if fh.read(1):
                    raise BackupInvalido(
                        "o pacote cifrado tem bytes depois do último bloco")
                return
            i += 1


def decifrar_arquivo(origem: Path, destino: Path, senha: str) -> Path:
    """Grava em `destino` o zip de dentro de um pacote cifrado. ESCREVE EM DISCO."""
    with Path(destino).open("wb") as fd:
        _decifrar(Path(origem), senha, fd.write)
    return Path(destino)


def _sha256_decifrado(origem: Path, senha: str) -> str:
    h = hashlib.sha256()
    _decifrar(Path(origem), senha, h.update)
    return h.hexdigest()


# ------------------------------------------- a senha da cifra, no cofre


def senha_da_cifra(pasta_de_dados: Path) -> str:
    """A senha da cifra do backup, do cofre; vazio = cifra desligada."""
    import cofre_cred as COFRE
    return COFRE.ler(pasta_de_dados, COFRE.BACKUP).get("senha", "")


def guardar_senha_da_cifra(pasta_de_dados: Path, senha: str) -> None:
    """Liga a cifra. ESCREVE no cofre, nunca no banco nem no log."""
    import cofre_cred as COFRE
    senha = str(senha or "")
    if len(senha) < MINIMO_DA_SENHA:
        raise BackupInvalido(
            f"a senha da cifra precisa de pelo menos {MINIMO_DA_SENHA} "
            "caracteres — é ela que protege o banco inteiro fora daqui")
    COFRE.gravar(pasta_de_dados, COFRE.BACKUP, {"senha": senha})


def apagar_senha_da_cifra(pasta_de_dados: Path) -> None:
    """Desliga a cifra: os próximos pacotes saem sem ela. ESCREVE no cofre."""
    import cofre_cred as COFRE
    COFRE.gravar(pasta_de_dados, COFRE.BACKUP, {"senha": ""})


def situacao_da_cifra(pasta_de_dados: Path) -> str:
    """`"desligada"`, `"ligada"` ou `"perdida"` — sem devolver a senha.

    «Perdida» é o `backup.cred` que existe e não abre (a `cofre.key` sumiu):
    o backup continua saindo, sem cifra, e a tela avisa.
    """
    import cofre_cred as COFRE
    estado = COFRE.situacao(pasta_de_dados, COFRE.BACKUP)
    if estado == "nao_abre":
        return "perdida"
    return "ligada" if senha_da_cifra(pasta_de_dados) else "desligada"


# ------------------------------------------------------------- o pacote


def gerar_pacote(db, destino: Path, archive_root: Path,
                 com_arquivos: bool = True, app_nome: str = "CartorioGestao",
                 versao: str = "", acervo: Path | None = None,
                 senha_da_cifra: str | None = None) -> Path:
    """Monta o pacote e SO ENTAO lhe da o nome definitivo.

    `db` precisa ter `backup_database(caminho)` — a copia consistente do SQLite,
    que respeita transacao em andamento. Copiar o arquivo com `shutil` enquanto
    o servidor escreve produziria um banco meio gravado.

    Com `senha_da_cifra`, o pacote conferido e cifrado, decifrado de novo para
    conferir, e so entao ganha o nome — o mesmo nome de sempre.
    """
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_suffix(destino.suffix + ".parcial")
    parcial.unlink(missing_ok=True)
    cifrando = destino.with_suffix(destino.suffix + ".cifrado.parcial")
    cifrando.unlink(missing_ok=True)

    with TemporaryDirectory() as tmp:
        instantaneo = Path(tmp) / "cartorio_gestao.sqlite3"
        # AS CONTAGENS DO MESMO INSTANTÂNEO VÃO NO MANIFESTO (26/10/2026): é
        # contra elas que o teste de restauração (`backup_restauracao`) confere
        # o que voltou. Quem não sabe contar (o banco de mentira dos testes
        # antigos) gera o pacote como antes, sem elas.
        contagens: dict | None = {} if _aceita_contagens(db) else None
        if contagens is None:
            db.backup_database(instantaneo)
        else:
            db.backup_database(instantaneo, contagens=contagens)
        sha_banco = _sha256(instantaneo)
        formato_banco = formato_do_banco(instantaneo)

        arquivos: list[dict] = []
        raiz = Path(archive_root)
        sha_acervo = None
        with zipfile.ZipFile(parcial, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(instantaneo, NOME_BANCO)
            zf.writestr(NOME_BANCO + ".sha256", sha_banco)

            # O ACERVO MORTO DO E-OFICIO ENTRA AQUI, E QUASE NAO ENTRAVA.
            #     Ele mora na pasta de dados, ao lado do banco — e nao dentro
            #     de `arquivos`, que e a unica pasta que este backup varre. Eu
            #     havia dito a serventia que "fica na pasta de dados, entao o
            #     backup ja o alcanca", e nao alcancava: 364 MB com a copia
            #     integral do sistema antigo ficariam de fora.
            #
            #     Vai so no backup COMPLETO. E copia fiel de um banco que nao
            #     muda mais: repeti-lo todo dia gastaria disco sem aumentar
            #     protecao nenhuma, exatamente como as digitalizacoes.
            if com_arquivos and acervo and Path(acervo).is_file():
                acervo = Path(acervo)
                sha_acervo = _sha256(acervo)
                zf.write(acervo, f"acervo/{acervo.name}")
                zf.writestr(f"acervo/{acervo.name}.sha256", sha_acervo)
            if com_arquivos and raiz.is_dir():
                for p in sorted(raiz.rglob("*")):
                    if not p.is_file():
                        continue
                    try:
                        rel = p.relative_to(raiz)
                    except ValueError:
                        continue
                    zf.write(p, str(Path("arquivos") / rel))
                    arquivos.append({
                        "caminho": str(rel).replace("\\", "/"),
                        "bytes": p.stat().st_size,
                        "sha256": _sha256(p),
                    })
            zf.writestr(NOME_MANIFESTO, json.dumps({
                "app": app_nome,
                "version": versao,
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "archive_root": str(raiz),
                "tipo": "completo" if com_arquivos else "banco",
                "cifrado": bool(senha_da_cifra),
                "banco_sha256": sha_banco,
                "banco_formato": formato_banco,
                "banco_contagens": contagens,
                "acervo_eoficio": bool(sha_acervo),
                "acervo_sha256": sha_acervo,
                "arquivos_incluidos": len(arquivos),
                "arquivos_bytes": sum(a["bytes"] for a in arquivos),
                "arquivos": arquivos,
            }, ensure_ascii=False, indent=2))

    # A conferencia acontece com o arquivo JA FECHADO. Conferir o que ainda
    # esta aberto para escrita seria conferir a nossa propria intencao.
    problema = conferir(parcial)
    if problema:
        raise BackupInvalido(f"{problema} — o pacote ficou em {parcial.name} "
                             "para exame, e o nome definitivo não foi criado.")

    if senha_da_cifra:
        cifrar_arquivo(parcial, cifrando, senha_da_cifra)
        try:
            igual = _sha256_decifrado(cifrando, senha_da_cifra) == _sha256(parcial)
        except BackupInvalido as erro:
            raise BackupInvalido(
                f"o pacote cifrado não abriu de volta ({erro}) — ficou em "
                f"{cifrando.name} para exame, e o nome definitivo não foi "
                "criado.") from erro
        if not igual:
            raise BackupInvalido(
                f"o pacote cifrado não devolve o zip conferido — ficou em "
                f"{cifrando.name} para exame, e o nome definitivo não foi "
                "criado.")
        parcial.unlink(missing_ok=True)
        parcial = cifrando

    destino.unlink(missing_ok=True)
    parcial.replace(destino)
    return destino


def conferir(pacote: Path, senha: str | None = None) -> str | None:
    """Devolve o problema encontrado, ou None se o pacote presta.

    Confere tres coisas, e nesta ordem: o zip abre; o banco esta dentro; e o
    SHA-256 do banco bate com o que o manifesto declara. A terceira e a que
    pega corrupcao silenciosa — as duas primeiras so pegam truncamento.

    O pacote cifrado e decifrado numa pasta temporaria e conferido igual;
    sem a senha, a resposta e que falta a senha — e nao que ele presta.
    """
    pacote = Path(pacote)
    if not pacote.is_file():
        return "o arquivo não existe"
    if pacote.stat().st_size == 0:
        return "o arquivo está vazio"
    if e_cifrado(pacote):
        if not senha:
            return "o pacote é cifrado: para conferi-lo é preciso a senha da cifra"
        with TemporaryDirectory() as tmp:
            claro = Path(tmp) / "pacote.zip"
            try:
                decifrar_arquivo(pacote, claro, senha)
            except BackupInvalido as erro:
                return str(erro)
            return conferir(claro)
    try:
        with zipfile.ZipFile(pacote) as zf:
            ruim = zf.testzip()
            if ruim:
                return f"o arquivo {ruim} dentro do pacote está corrompido"
            nomes = set(zf.namelist())
            if NOME_BANCO not in nomes:
                return "o banco não está dentro do pacote"
            if NOME_MANIFESTO not in nomes:
                return "falta o manifesto"
            manifesto = json.loads(zf.read(NOME_MANIFESTO).decode("utf-8"))
            declarado = manifesto.get("banco_sha256")
            if declarado:
                real = hashlib.sha256(zf.read(NOME_BANCO)).hexdigest()
                if real != declarado:
                    return ("o SHA-256 do banco não bate com o do manifesto — "
                            "o pacote se corrompeu")
    except zipfile.BadZipFile:
        return "o arquivo não é um zip válido"
    except (OSError, ValueError, KeyError) as erro:
        return f"não consegui ler o pacote: {type(erro).__name__}: {erro}"
    return None


def resumo(pacote: Path, senha: str | None = None) -> dict:
    """O que tem dentro, para a tela mostrar sem descompactar."""
    pacote = Path(pacote)
    dados = {"nome": pacote.name, "bytes": pacote.stat().st_size if pacote.is_file() else 0,
             "cifrado": e_cifrado(pacote), "problema": conferir(pacote, senha)}
    if dados["problema"]:
        return dados
    if dados["cifrado"]:
        with TemporaryDirectory() as tmp:
            claro = decifrar_arquivo(pacote, Path(tmp) / "pacote.zip", senha)
            with zipfile.ZipFile(claro) as zf:
                manifesto = json.loads(zf.read(NOME_MANIFESTO).decode("utf-8"))
    else:
        with zipfile.ZipFile(pacote) as zf:
            manifesto = json.loads(zf.read(NOME_MANIFESTO).decode("utf-8"))
    dados.update({
        "tipo": manifesto.get("tipo"),
        "criado_em": manifesto.get("created_at"),
        "versao": manifesto.get("version"),
        "arquivos": manifesto.get("arquivos_incluidos", 0),
        "arquivos_bytes": manifesto.get("arquivos_bytes", 0),
    })
    return dados


def parciais(pasta: Path) -> list[Path]:
    """Os `.parcial` esquecidos — backup que começou e não terminou.

    Ninguem confunde um `.parcial` com backup pronto, mas o acumulo diz que
    algo esta interrompendo a rotina, e isso a tela deve mostrar.
    """
    return sorted(Path(pasta).glob("*.parcial"))


# ------------------------------------------------------- a restauracao


def abrir(pacote: Path, destino: Path, senha: str | None = None) -> Path:
    """O zip de sempre, a partir de qualquer pacote — cifrado ou nao.

    E O PRIMEIRO PASSO DA RESTAURACAO, e por isso aceita tudo o que este
    modulo ja gerou: o zip de antes do LX14, o zip sem cifra de depois, e o
    cifrado. Devolve `destino` so depois de conferi-lo (zip integro, banco
    dentro, SHA-256 do manifesto); senao levanta `BackupInvalido` e nao deixa
    `destino` com cara de bom.
    """
    pacote, destino = Path(pacote), Path(destino)
    if not pacote.is_file():
        raise BackupInvalido(f"o arquivo {pacote} não existe")
    destino.parent.mkdir(parents=True, exist_ok=True)
    provisorio = destino.with_suffix(destino.suffix + ".parcial")
    provisorio.unlink(missing_ok=True)
    if e_cifrado(pacote):
        decifrar_arquivo(pacote, provisorio, senha or "")
    elif pacote.resolve() == destino.resolve():
        problema = conferir(pacote)
        if problema:
            raise BackupInvalido(problema)
        return destino
    else:
        shutil.copyfile(pacote, provisorio)
    problema = conferir(provisorio)
    if problema:
        raise BackupInvalido(f"{problema} — ficou em {provisorio.name} para exame")
    provisorio.replace(destino)
    return destino


def main(argv: list[str] | None = None) -> int:
    """`python backup.py abrir <pacote> <saida.zip>` e `conferir <pacote>`.

    A senha vem do cofre da pasta de dados (`--pasta-de-dados`), ou e
    perguntada — nunca na linha de comando, que fica no historico do console.
    """
    import getpass
    leitor = argparse.ArgumentParser(
        prog="backup.py", description="Abre ou confere um pacote de backup.")
    acoes = leitor.add_subparsers(dest="acao", required=True)
    a = acoes.add_parser("abrir", help="grava o zip de sempre a partir do pacote")
    a.add_argument("pacote")
    a.add_argument("saida")
    a.add_argument("--pasta-de-dados", default="")
    c = acoes.add_parser("conferir", help="confere o pacote sem abrir no disco")
    c.add_argument("pacote")
    c.add_argument("--pasta-de-dados", default="")
    args = leitor.parse_args(argv)
    senha = None
    if e_cifrado(Path(args.pacote)):
        if args.pasta_de_dados:
            senha = senha_da_cifra(Path(args.pasta_de_dados)) or None
        if not senha:
            senha = getpass.getpass("Senha da cifra do backup: ")
    try:
        if args.acao == "abrir":
            saida = abrir(Path(args.pacote), Path(args.saida), senha)
            print(f"Pronto: {saida} é o zip do backup, conferido.")
            return 0
        problema = conferir(Path(args.pacote), senha)
    except BackupInvalido as erro:
        print(f"Não deu: {erro}", file=sys.stderr)
        return 1
    if problema:
        print(f"O pacote não presta: {problema}", file=sys.stderr)
        return 1
    print("O pacote presta.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
