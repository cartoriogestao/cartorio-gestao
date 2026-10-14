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
"""
from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

NOME_BANCO = "banco/cartorio_gestao.sqlite3"
NOME_MANIFESTO = "manifesto.json"


class BackupInvalido(RuntimeError):
    """O pacote foi gerado mas nao passou na conferencia."""


def _sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as fh:
        for bloco in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def gerar_pacote(db, destino: Path, archive_root: Path,
                 com_arquivos: bool = True, app_nome: str = "CartorioGestao",
                 versao: str = "", acervo: Path | None = None) -> Path:
    """Monta o pacote e SO ENTAO lhe da o nome definitivo.

    `db` precisa ter `backup_database(caminho)` — a copia consistente do SQLite,
    que respeita transacao em andamento. Copiar o arquivo com `shutil` enquanto
    o servidor escreve produziria um banco meio gravado.
    """
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    parcial = destino.with_suffix(destino.suffix + ".parcial")
    parcial.unlink(missing_ok=True)

    with TemporaryDirectory() as tmp:
        instantaneo = Path(tmp) / "cartorio_gestao.sqlite3"
        db.backup_database(instantaneo)
        sha_banco = _sha256(instantaneo)

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
                "banco_sha256": sha_banco,
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

    destino.unlink(missing_ok=True)
    parcial.replace(destino)
    return destino


def conferir(pacote: Path) -> str | None:
    """Devolve o problema encontrado, ou None se o pacote presta.

    Confere tres coisas, e nesta ordem: o zip abre; o banco esta dentro; e o
    SHA-256 do banco bate com o que o manifesto declara. A terceira e a que
    pega corrupcao silenciosa — as duas primeiras so pegam truncamento.
    """
    pacote = Path(pacote)
    if not pacote.is_file():
        return "o arquivo não existe"
    if pacote.stat().st_size == 0:
        return "o arquivo está vazio"
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


def resumo(pacote: Path) -> dict:
    """O que tem dentro, para a tela mostrar sem descompactar."""
    pacote = Path(pacote)
    dados = {"nome": pacote.name, "bytes": pacote.stat().st_size if pacote.is_file() else 0,
             "problema": conferir(pacote)}
    if dados["problema"]:
        return dados
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
