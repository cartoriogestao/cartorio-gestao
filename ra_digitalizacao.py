"""A DIGITALIZAÇÃO DO REGISTRO DO LIVRO 3.

    «digitalizacao de imagens deve ter igual ao livro 2»
                                        — o oficial, 21/09/2026

**AS REGRAS DE ARQUIVO SÃO AS DO LIVRO 2, E LIDAS DE LÁ.** As extensões
aceitas, o hash do arquivo, o nome seguro, o caminho único e a miniatura vêm
de `ri_digitalizacao` — escrevê-las de novo aqui daria duas versões do pedaço
que decide o que o balcão pode subir, e elas divergiriam no primeiro conserto.

**O QUE MUDA É A TABELA E UMA COISA A MENOS: O ONR.** No Livro 2 o envio
marca `digi_onr_pendente`, porque o índice que o país consulta é de **imóvel**.
O Livro 3 registra **título de crédito** — não há para onde enviar, e levar
aquelas duas colunas junto seria prometer um envio que não existe. Ver
`ra_schema.MIGRACOES`, onde a ausência está declarada.

**O ARQUIVO ANTERIOR NÃO SOME**: vai para `historico/` com carimbo de tempo,
para auditoria se a varredura nova estiver errada. É a regra do Livro 2, e
existe porque a segunda varredura às vezes é a errada.
"""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from bd_nativo import banco

# AS REGRAS DE ARQUIVO SÃO AS DO LIVRO 2 — ver o cabeçalho.
from ri_digitalizacao import (  # noqa: F401
    EXTENSOES_OK,
    hash_file,
    miniatura_png,
    # O PAPEL DA CERTIDAO POR REPRODUCAO E O MESMO DO LIVRO 2 — 21/09/2026.
    # `odt_da_digitalizacao` ja recebe o caminho, o selo e o nome; um segundo
    # montador daria duas versoes do papel que reproduz o livro.
    odt_da_digitalizacao,
    paginas_png,
    raiz_arquivos,
    safe_component,
    unique_path,
)


class DigitalizacaoError(ValueError):
    """Erro de regra, com frase pronta para o balcão."""


def pasta_do_registro(raiz: Path, registro_id: int) -> Path:
    """Onde mora a digitalização daquele registro.

    **Pasta própria, e não a do Livro 2**: os números dos dois livros se
    cruzam — há matrícula 1.243 e registro 1.243 —, e uma pasta só faria a
    varredura de um sobrescrever a do outro.
    """
    return Path(raiz) / "livro3" / f"registro-{int(registro_id)}"


def atual(con: Any, registro_id: int) -> dict | None:
    """O arquivo oficial de hoje daquele registro, ou `None`. Só lê."""
    linha = banco(con).um(
        """SELECT digi_path, digi_nome, digi_sha256, digi_em, digi_por
             FROM ra_registros WHERE id=%s""", (int(registro_id),))
    if not linha or not linha["digi_path"]:
        return None
    return dict(linha)


def gravar_upload(db, *, registro_id: int, arquivo, usuario: Any) -> dict:
    """Substitui a digitalização oficial do registro. ESCREVE.

    **Recebe `db`, e não `con`** — ela grava em disco antes de tocar no banco,
    e a transação é curta e no fim: segurar o `BEGIN IMMEDIATE` durante a
    cópia de um PDF de dezenas de megabytes poria todo outro balcão a esperar.
    """
    if arquivo is None or not getattr(arquivo, "filename", None):
        raise DigitalizacaoError(
            "Escolha o arquivo da digitalização (PDF, TIFF, PNG ou JPEG).")
    nome = Path(arquivo.filename or "digitalizacao").name
    ext = Path(nome).suffix.lower()
    if ext not in EXTENSOES_OK:
        raise DigitalizacaoError(
            "Formato não aceito. Use PDF, TIFF, PNG ou JPEG — é a mesma lista "
            "do Livro 2.")

    with db.connect() as con:
        bd = banco(con)
        anterior = bd.um(
            "SELECT digi_path, digi_nome FROM ra_registros WHERE id=%s",
            (int(registro_id),))
        if anterior is None:
            raise DigitalizacaoError("Registro do Livro 3 não encontrado.")

    pasta = pasta_do_registro(raiz_arquivos(db), registro_id)
    pasta.mkdir(parents=True, exist_ok=True)
    historico = pasta / "historico"
    historico.mkdir(exist_ok=True)

    # O ARQUIVO ANTERIOR VAI PARA O HISTÓRICO ANTES DE A NOVA ENTRAR.
    if anterior and anterior["digi_path"]:
        velho = Path(anterior["digi_path"])
        if velho.is_file():
            carimbo = datetime.now().strftime("%Y%m%d-%H%M%S")  # noqa: DTZ005
            destino = unique_path(
                historico,
                f"{carimbo}_{safe_component(anterior['digi_nome'] or velho.name)}")
            shutil.copy2(velho, destino)

    estavel = pasta / f"atual{ext}"
    if estavel.exists():
        estavel.unlink()
    arquivo.save(estavel)
    sha = hash_file(estavel)
    agora = db.now()

    with db.transaction() as con:
        banco(con).escrever(
            """UPDATE ra_registros
                  SET digi_path=%s, digi_nome=%s, digi_sha256=%s, digi_em=%s,
                      digi_por=%s
                WHERE id=%s""",
            (str(estavel.resolve()), nome, sha, agora, str(usuario or ""),
             int(registro_id)))
    return {"path": str(estavel.resolve()), "nome": nome, "sha256": sha,
            "em": agora}


# ============================================================ o termo
#
# **A DIGITALIZACAO DO TERMO NAO E A DO REGISTRO** — ordem do oficial em
# 21/09/2026: «precisa ter digitalizacao do termo».
#
#   A do REGISTRO e a varredura da ficha inteira. A do TERMO e o papel
#   daquele ato: o instrumento de baixa que o credor expediu, a procuracao
#   que o representou, o aditivo que a averbacao registrou. Sao dois papeis
#   diferentes, e guardar os dois no mesmo lugar faria a segunda apagar a
#   primeira.


def pasta_do_ato(raiz: Path, registro_id: int, ato_id: int) -> Path:
    """Onde mora a digitalização daquele termo.

    **Dentro da pasta do registro, e não ao lado**: o papel do ato pertence à
    ficha, e quem for à pasta procurar o registro acha os termos dele junto.
    """
    return pasta_do_registro(raiz, registro_id) / f"termo-{int(ato_id)}"


def atual_do_ato(con: Any, ato_id: int) -> dict | None:
    """O papel daquele termo, ou `None`. Só lê."""
    linha = banco(con).um(
        """SELECT digi_path, digi_nome, digi_sha256, digi_em, digi_por
             FROM ra_atos WHERE id=%s""", (int(ato_id),))
    if not linha or not linha["digi_path"]:
        return None
    return dict(linha)


def gravar_upload_do_ato(db, *, ato_id: int, arquivo, usuario: Any) -> dict:
    """Guarda o papel do termo. ESCREVE.

    **As mesmas regras da varredura do registro** — extensões, hash, nome
    seguro e o histórico —, porque o que muda é onde o arquivo mora, e não o
    que o balcão pode subir.
    """
    if arquivo is None or not getattr(arquivo, "filename", None):
        raise DigitalizacaoError(
            "Escolha o arquivo do termo (PDF, TIFF, PNG ou JPEG).")
    nome = Path(arquivo.filename or "termo").name
    ext = Path(nome).suffix.lower()
    if ext not in EXTENSOES_OK:
        raise DigitalizacaoError(
            "Formato não aceito. Use PDF, TIFF, PNG ou JPEG — é a mesma lista "
            "do Livro 2.")

    with db.connect() as con:
        a = banco(con).um(
            "SELECT registro_id, digi_path, digi_nome FROM ra_atos WHERE id=%s",
            (int(ato_id),))
    if a is None:
        raise DigitalizacaoError("Ato do Livro 3 não encontrado.")

    pasta = pasta_do_ato(raiz_arquivos(db), a["registro_id"], ato_id)
    pasta.mkdir(parents=True, exist_ok=True)
    historico = pasta / "historico"
    historico.mkdir(exist_ok=True)
    if a["digi_path"]:
        velho = Path(a["digi_path"])
        if velho.is_file():
            carimbo = datetime.now().strftime("%Y%m%d-%H%M%S")  # noqa: DTZ005
            shutil.copy2(velho, unique_path(
                historico,
                f"{carimbo}_{safe_component(a['digi_nome'] or velho.name)}"))

    estavel = pasta / f"termo{ext}"
    if estavel.exists():
        estavel.unlink()
    arquivo.save(estavel)
    sha = hash_file(estavel)
    agora = db.now()
    with db.transaction() as con:
        banco(con).escrever(
            """UPDATE ra_atos SET digi_path=%s, digi_nome=%s, digi_sha256=%s,
                   digi_em=%s, digi_por=%s WHERE id=%s""",
            (str(estavel.resolve()), nome, sha, agora, str(usuario or ""),
             int(ato_id)))
    return {"path": str(estavel.resolve()), "nome": nome, "sha256": sha,
            "em": agora, "registro_id": a["registro_id"]}


def retirar_upload(db, *, registro_id: int | None = None,
                   ato_id: int | None = None, motivo: str,
                   usuario: Any) -> dict:
    """Retira o arquivo ativo da ficha, preservando cópia recuperável.

    Só toca no arquivo do próprio registro/ato e não apaga certidões por
    reprodução já emitidas, cujas imagens foram congeladas em outra pasta.
    """
    if (registro_id is None) == (ato_id is None):
        raise DigitalizacaoError("Informe exatamente um registro ou um ato.")
    motivo = str(motivo or "").strip()
    if len(motivo) < 5:
        raise DigitalizacaoError("Informe o motivo da retirada (ao menos 5 letras).")
    tabela = "ra_atos" if ato_id is not None else "ra_registros"
    chave = int(ato_id if ato_id is not None else registro_id)
    with db.connect() as con:
        linha = banco(con).um(
            f"SELECT * FROM {tabela} WHERE id=%s", (chave,))
    if not linha or not linha["digi_path"]:
        raise DigitalizacaoError("Não há arquivo ativo para retirar.")
    rid = int(linha["registro_id"] if ato_id is not None else chave)
    pasta = (pasta_do_ato(raiz_arquivos(db), rid, chave)
             if ato_id is not None else pasta_do_registro(raiz_arquivos(db), rid))
    atual_path = Path(linha["digi_path"]).resolve()
    if atual_path.parent != pasta.resolve():
        raise DigitalizacaoError("O caminho do arquivo não pertence a esta ficha; retirada recusada.")
    destino = None
    if atual_path.is_file():
        historico = pasta / "historico"
        historico.mkdir(parents=True, exist_ok=True)
        carimbo = datetime.now().strftime("%Y%m%d-%H%M%S")
        destino = unique_path(
            historico,
            f"{carimbo}_retirado_{safe_component(linha['digi_nome'] or atual_path.name)}")
        shutil.copy2(atual_path, destino)
    with db.transaction() as con:
        alterado = banco(con).escrever(
            f"""UPDATE {tabela} SET digi_path=NULL, digi_nome=NULL,
                       digi_sha256=NULL, digi_em=NULL, digi_por=NULL
                 WHERE id=%s AND digi_path=%s RETURNING id""",
            (chave, str(linha["digi_path"])))
        if len(alterado) != 1:
            raise DigitalizacaoError(
                "O arquivo mudou durante a retirada; atualize a ficha e tente novamente.")
    if (destino is not None and atual_path.is_file()
            and hash_file(atual_path) == linha["digi_sha256"]):
        atual_path.unlink()
    return {"registro_id": rid, "ato_id": ato_id,
            "nome": linha["digi_nome"], "sha256": linha["digi_sha256"],
            "historico": str(destino) if destino else None,
            "motivo": motivo, "usuario": str(usuario or "")}


# ================================================ a cópia congelada da certidão
#
# **A CERTIDÃO POR REPRODUÇÃO GUARDA O ARQUIVO COMO ELE ESTAVA** — é a regra do
# teor congelado aplicada à imagem: a varredura trocada amanhã não pode mudar a
# certidão que saiu hoje, e é a via de hoje que alguém vai conferir.


def pasta_snapshot_da_certidao(raiz: Path, certidao_id: int) -> Path:
    """Onde mora a cópia congelada daquela certidão do Livro 3.

    **PASTA PRÓPRIA, E NÃO A DO LIVRO 2 — e isto é a lição da chave pela
    metade.** `ri_digitalizacao.pasta_snapshot_certidao` chaveia por
    `certidao_id` sozinho, e `ri_certidoes` e `at_certidoes` são **tabelas
    diferentes, com sequências de id independentes**: a certidão 7 do Registro
    de Imóveis e a 7 do Livro 3 cairiam na mesma pasta, e a segunda apagaria a
    varredura que a primeira congelou. A chave é **tabela mais id**, como no
    selo.
    """
    return Path(raiz) / "livro3" / "certidoes" / str(int(certidao_id))


def congelar_para_certidao(db, *, certidao_id: int, origem: Path) -> dict:
    """Copia a varredura de hoje para a pasta daquela certidão. ESCREVE em disco.

    Não toca no banco: quem grava o caminho é a rota, na transação dela.
    """
    origem = Path(origem)
    if not origem.is_file():
        raise DigitalizacaoError(
            "Não há digitalização deste registro no disco. Envie o arquivo na "
            "ficha antes de emitir a certidão por reprodução.")
    pasta = pasta_snapshot_da_certidao(raiz_arquivos(db), certidao_id)
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"digitalizacao{origem.suffix.lower()}"
    if destino.exists():
        destino.unlink()
    shutil.copy2(origem, destino)
    return {"path": str(destino.resolve()), "sha256": hash_file(destino),
            "nome": origem.name}
