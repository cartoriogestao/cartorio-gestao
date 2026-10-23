"""Os PAPÉIS das certidões do Registro Civil — os `.odt` que o oficial desenha.

    «Atualizar esses modelos no modulo de modelos, para poder editar por la»
                                            — o oficial, 10/09/2026

POR QUE ELES NÃO CABIAM NO CATÁLOGO DE `modelos_da_casa`
    Aquele catálogo guarda **texto**: o corpo do papel, em Jinja ou em chaves,
    numa caixa de edição da tela. Os três moldes da certidão do RCPN não são
    texto — são arquivos `.odt`, com tabelas, larguras de coluna em
    centímetros, estilos de fonte e as duas caixas de selo. O oficial os
    desenha no LibreOffice, e é assim que tem de ser: o Anexo IV do Provimento
    CNJ 182/2024 é um formulário, e formulário não se escreve numa caixa de
    texto.

**O QUE ESTA TABELA CONSERTA, E ELE É MEDIDO.** Até aqui o molde morava só em
disco, em `modelos/certidao_*_modelo.odt`, e a linha 55 do
`ATUALIZAR_SISTEMA.cmd` diz:

    robocopy "%FONTE%\\modelos" "%PROG%\\modelos" /E

**`/E` copia a pasta inteira por cima.** Ou seja: todo ajuste que o oficial
fizesse no molde instalado era apagado na atualização seguinte, sem aviso e
sem como recuperar — e ele não teria por que desconfiar, porque o papel
continuava saindo, só sem o ajuste dele.

A REGRA É A DA CASA, e não uma nova: **o código é o piso; a tabela é o
ajuste.** Sem linha aqui, vale o `.odt` que vem no pacote; com linha, vale o
dele. Isso dá as mesmas três coisas de sempre:

  1. **nada se perde** — o padrão não é apagável, porque não mora no banco;
  2. **«voltar ao padrão» é apagar a linha**;
  3. **instalação nova nasce funcionando**, sem carga de molde nenhuma.

**E A ATUALIZAÇÃO DEIXA DE ATROPELAR O AJUSTE**: o `robocopy` continua
trocando o arquivo do pacote, que é o piso, e o ajuste vive no banco, que ele
não alcança.

O QUE A CONFERÊNCIA RECUSA, E POR QUE CADA UMA
    Ela roda **antes de gravar**, como a dos modelos de texto — o erro tem de
    aparecer para quem edita, e não para o escrevente com o cliente na frente:

      · **não é um `.odt`** — um `.doc`, um PDF ou um arquivo truncado;
      · **marcador que o código não preenche.** É o guarda mais importante
        desta casa sobre este papel: `@` que `rc_certidao_odt.valores()` não
        conhece **não é substituído — sai impresso** numa certidão assinada.
        `tests/test_rc_certidao_molde.py` já varre isso nos moldes do pacote;
        aqui ele passa a valer para o que o oficial enviar;
      · **molde sem a matrícula.** A matrícula de 32 dígitos é a identidade
        nacional da certidão: sem ela o papel não serve, e a falta só
        apareceria quando alguém fosse conferir o registro noutra serventia.
        Já se perdeu uma vez, em 01/09/2026, ao derivar os moldes de casamento
        e óbito do de nascimento.

**ISTO NÃO GUARDA CERTIDÃO, E NÃO GUARDA ATO.** Guarda o papel em branco. A
certidão emitida continua em `rc_certidoes`, com o teor congelado.
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

import tetos_de_entrada as TETO
from bd_nativo import banco

SCHEMA = """
-- O AJUSTE DO OFICIAL NO PAPEL DA CERTIDAO. O CODIGO E O PISO; ESTA TABELA E
-- O AJUSTE — sem linha aqui vale o `.odt` do pacote, e «voltar ao padrao» e
-- apagar a linha. Mesma regra de `mo_modelos`, com uma diferenca que decidiu
-- a tabela: aqui o conteudo e BINARIO (um zip do OpenDocument), e nao texto.
CREATE TABLE IF NOT EXISTS mo_moldes (
    chave TEXT PRIMARY KEY,        -- ver MOLDES, neste modulo
    arquivo BYTEA NOT NULL,         -- o .odt inteiro
    nome_arquivo TEXT,             -- o nome com que ele chegou, para a tela
    tamanho INTEGER NOT NULL,      -- bytes, para a tela dizer o tamanho
    sha256 TEXT NOT NULL,          -- para conferir que e o mesmo arquivo
    atualizado_em TEXT NOT NULL,
    atualizado_por TEXT
);
"""


def init_modelos_moldes_schema(con: sqlite3.Connection) -> None:
    """Cria a tabela do ajuste do molde. Idempotente."""
    banco(con).escrever(SCHEMA)


# ------------------------------------------------------------- o catálogo
#
# **TRES MOLDES, E NAO UM.** O titulo de cada um e texto fixo — «CERTIDAO DE
# NASCIMENTO» —, e nao um marcador: e por isso que ha um arquivo por especie,
# e foi o achado de 01/09/2026 (as tres especies imprimiam no molde de
# nascimento, e uma certidao de obito saia com caixa de DNV e de gemeos).
#
# `especie` amarra cada linha ao molde que `rc_certidao_odt` ja conhece — o
# caminho NAO se escreve aqui, para nao haver duas versoes do mesmo caminho
# divergindo no primeiro conserto. E a mesma decisao do `padrao` de
# `modelos_da_casa`: o catalogo guarda ONDE mora, e nao o conteudo.
MOLDES: tuple[dict[str, Any], ...] = (
    {"chave": "RC_MOLDE_NASCIMENTO",
     "atribuicao": "Registro Civil das Pessoas Naturais",
     "nome": "Papel da certidão de nascimento",
     "especie": "NASCIMENTO",
     "explica": "O formulário do Anexo IV do Provimento CNJ 182/2024, campo "
                "a campo. Baixe, ajuste no LibreOffice e envie de volta."},
    {"chave": "RC_MOLDE_CASAMENTO",
     "atribuicao": "Registro Civil das Pessoas Naturais",
     "nome": "Papel da certidão de casamento",
     "especie": "CASAMENTO",
     "explica": "O Anexo V. Serve também o casamento religioso com efeito "
                "civil, que muda de livro e não de papel."},
    {"chave": "RC_MOLDE_OBITO",
     "atribuicao": "Registro Civil das Pessoas Naturais",
     "nome": "Papel da certidão de óbito",
     "especie": "OBITO",
     "explica": "O Anexo VI."},
)

POR_CHAVE: dict[str, dict] = {m["chave"]: m for m in MOLDES}

# O marcador da matricula de cada especie — a conferencia exige o da especie
# daquele molde, e nao «um deles»: um molde de obito com `@matriculanascido`
# dentro sairia com o campo em branco, porque quem preenche olha o nome.
MATRICULA_DA_ESPECIE: dict[str, str] = {
    "NASCIMENTO": "@matriculanascido",
    "CASAMENTO": "@matriculacasamento",
    "OBITO": "@matriculaobito",
}


class PapelError(ValueError):
    """Erro de regra, com mensagem pronta para o balcão.

    **NÃO SE CHAMA `MoldeError`, e o nome é deliberado.**
    `rc_certidao_odt.MoldeError` já existe e quer dizer outra coisa — «esta
    espécie não tem molde nesta casa». Duas classes com o mesmo nome em
    módulos diferentes é a armadilha que este projeto já pagou no Protesto
    (`cenprot_api.CenprotError` é `RuntimeError` e
    `protesto_cenprot.CenprotError` é `ValueError`): quem apanha uma achando
    que apanha a outra deixa passar justamente a que importa.
    """


def _do_catalogo(chave: str) -> dict:
    m = POR_CHAVE.get(str(chave or "").strip().upper())
    if not m:
        raise PapelError(
            f"«{chave}» não é um papel de certidão desta casa. Os que "
            "existem: " + ", ".join(f"{x['chave']} ({x['nome']})"
                                    for x in MOLDES) + ".")
    return m


def caminho_padrao(chave: str) -> Path:
    """O `.odt` do pacote daquela espécie. Só calcula.

    **PERGUNTADO A QUEM SABE**, e não escrito aqui: quem mapeia espécie para
    arquivo é `rc_certidao_odt`, que é quem o abre para imprimir. Um segundo
    mapa aqui divergiria no dia em que um deles mudasse de nome.
    """
    import rc_certidao_odt as ODT
    return ODT.molde_da_especie(_do_catalogo(chave)["especie"])


def nome_do_arquivo_padrao(chave: str) -> str:
    return caminho_padrao(chave).name


def _linha(con: sqlite3.Connection, chave: str):
    try:
        return banco(con).um(
            "SELECT * FROM mo_moldes WHERE chave = %s", (chave,))
    except sqlite3.OperationalError:
        # Instalacao a meio de migrar: o papel continua saindo do pacote.
        # **Documento que nao sai e pior que documento sem o ajuste novo** — a
        # mesma decisao de `modelos_da_casa.corpo_de`.
        return None


def arquivo_que_vale(con: sqlite3.Connection, chave: str) -> bytes:
    """O molde ajustado, ou o do pacote. Só lê.

    É a regra dos quatro modelos do RI, agora valendo para o papel da
    certidão: sem linha na tabela, sai o de fábrica.
    """
    # Plug do motor (SANDBOX): com USAR_CONTEUDO_PUBLICADO_EDITOR=False o
    # helper devolve (None, vigente) sem consultar o Editor - comportamento
    # identico ao de hoje. Quando a flag e a chave da area forem ligadas,
    # o blob publicado substitui mo_moldes / .odt do pacote.
    import modelos_motor_versao as VERSAO
    c = _do_catalogo(chave)
    blob, _origem = VERSAO.molde_da_certidao(con, c["chave"], area="RCPN")
    if blob:
        return bytes(blob)
    r = _linha(con, c["chave"])
    if r is not None and r["arquivo"]:
        return bytes(r["arquivo"])
    caminho = caminho_padrao(c["chave"])
    if not caminho.is_file():
        raise PapelError(
            f"O papel da certidão de {c['especie'].lower()} não está nesta "
            "instalação, e não há ajuste gravado. Reinstale o sistema ou "
            "envie um molde pela tela de Modelos.")
    return caminho.read_bytes()


def como_esta(con: sqlite3.Connection, chave: str) -> dict:
    """O que a tela mostra sobre um molde. Só lê.

    **A TELA TEM DE DIZER SE ESTÁ AJUSTADO**: «igual ao do pacote» e
    «ajustado por esta casa» parecem a mesma coisa quando o papel sai igual —
    e são diferentes no dia em que o pacote trouxer um molde novo, porque **o
    ajustado não acompanha**. Por isso `ajustado` sai daqui, e não de uma
    função à parte que a tela teria de lembrar de chamar.
    """
    c = _do_catalogo(chave)
    r = _linha(con, c["chave"])
    if r is not None:
        return {**c, "ajustado": True,
                "nome_arquivo": r["nome_arquivo"] or nome_do_arquivo_padrao(c["chave"]),
                "tamanho": int(r["tamanho"] or 0),
                "sha256": r["sha256"] or "",
                "atualizado_em": r["atualizado_em"],
                "atualizado_por": r["atualizado_por"] or ""}
    caminho = caminho_padrao(c["chave"])
    existe = caminho.is_file()
    return {**c, "ajustado": False,
            "nome_arquivo": caminho.name,
            "tamanho": caminho.stat().st_size if existe else 0,
            "sha256": "", "atualizado_em": "", "atualizado_por": "",
            "falta_no_disco": not existe}


def marcadores_de(arquivo: bytes) -> set[str]:
    """Os `@marcador` que aquele `.odt` promete. Só calcula.

    **A TABULAÇÃO SE TRADUZ, E NÃO SE APAGA** — a mesma leitura de
    `tests/test_rc_certidao_molde.py`, e pelo mesmo motivo: tirar as tags sem
    tratar `<text:tab/>` cola dois rótulos e faz um marcador desaparecer da
    conta.
    """
    with zipfile.ZipFile(BytesIO(arquivo)) as z:
        # COM TETO (LX12, LS02 M2): o molde vem do formulário, e o
        # `content.xml` de um `.odt` de 1 KB pode se abrir em gigabytes.
        x = TETO.ler_membro(z, "content.xml").decode("utf-8")
    x = x[x.find("<office:body"):]
    x = re.sub(r"<text:tab/>", " ", x)
    x = re.sub(r"<text:line-break/>", " ", x)
    x = re.sub(r"<text:s[^/]*/>", " ", x)
    x = re.sub(r"<[^>]+>", " ", x)
    return set(re.findall(r"@[A-Za-z_0-9]+", x))


def conferir(chave: str, arquivo: bytes) -> str | None:
    """O que impede este molde de virar papel assinado. Devolve o erro, ou None.

    **VEM ANTES DE GRAVAR, E RECUSA.** Gravar e avisar depois deixaria o molde
    quebrado valendo até alguém voltar na tela, e quem descobre é o escrevente
    na hora de emitir — com o ato já lavrado.
    """
    c = _do_catalogo(chave)
    if not arquivo:
        return "O arquivo chegou vazio."
    try:
        with zipfile.ZipFile(BytesIO(arquivo)) as z:
            nomes = set(z.namelist())
            # A ZIP-BOMBA SE RECUSA AQUI, ANTES DE GRAVAR (LX12, LS02 M2): o
            # índice do pacote diz quanto ele se abre, e `marcadores_de`, logo
            # abaixo, ainda corta a leitura se o índice mentir.
            TETO.conferir_pacote(z)
    except TETO.TetoExcedido as erro:
        return str(erro)
    except zipfile.BadZipFile:
        return ("Este arquivo não é um .odt. Abra o molde no LibreOffice e "
                "grave como «Documento de texto ODF (.odt)».")
    if "content.xml" not in nomes:
        return ("Falta o conteúdo dentro do arquivo (`content.xml`). Ele pode "
                "ter chegado incompleto — envie de novo.")

    # O ÍNDICE QUE MENTE TAMBÉM VOLTA COMO RECUSA (LX20, ressalva do LX12):
    # `conferir_pacote` acima confia no tamanho que o índice DECLARA; o
    # `content.xml` que diz 200 bytes e traz mais só aparece na leitura —
    # `TetoExcedido` do corte, ou `BadZipFile` do CRC que o `zipfile` confere
    # ao parar no tamanho declarado. Sem isto a exceção escapava de
    # `conferir`, e a tela dizia «Não deu para gravar o papel» em vez do
    # motivo.
    try:
        marcadores = marcadores_de(arquivo)
    except TETO.TetoExcedido as erro:
        return str(erro)
    except (zipfile.BadZipFile, UnicodeDecodeError):
        return ("O conteúdo deste .odt não se lê: o arquivo chegou corrompido, "
                "ou o índice do pacote não confere com o que ele traz. Abra o "
                "molde no LibreOffice e grave de novo como «Documento de texto "
                "ODF (.odt)».")

    import rc_certidao_odt as ODT
    vocabulario = set(ODT.valores({}, {}, {}))
    faltando = sorted(marcadores - vocabulario)
    if faltando:
        return ("Este molde usa marcadores que o sistema não sabe preencher, "
                "e eles sairiam escritos na certidão: "
                + ", ".join(faltando) + ".")

    matricula = MATRICULA_DA_ESPECIE[c["especie"]]
    if matricula not in marcadores:
        return (f"O molde está sem a matrícula ({matricula}). Ela é a "
                "identidade nacional da certidão: sem ela o papel não serve "
                "para conferir o registro noutra serventia.")
    return None


def salvar(con: sqlite3.Connection, chave: str, *, arquivo: bytes,
           nome_arquivo: str | None, quem: str | None, agora: str) -> str:
    """Guarda o molde ajustado. Devolve o sha256 do que ficou gravado.

    **CONFERE ANTES**, e levanta `PapelError` com a frase pronta.
    """
    c = _do_catalogo(chave)
    erro = conferir(c["chave"], arquivo)
    if erro:
        raise PapelError(erro)
    resumo = hashlib.sha256(arquivo).hexdigest()
    banco(con).escrever(
        """INSERT INTO mo_moldes (chave, arquivo, nome_arquivo, tamanho,
               sha256, atualizado_em, atualizado_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT(chave) DO UPDATE SET
               arquivo = excluded.arquivo,
               nome_arquivo = excluded.nome_arquivo,
               tamanho = excluded.tamanho,
               sha256 = excluded.sha256,
               atualizado_em = excluded.atualizado_em,
               atualizado_por = excluded.atualizado_por""",
        (c["chave"], bytes(arquivo),
         (nome_arquivo or "").strip() or nome_do_arquivo_padrao(c["chave"]),
         len(arquivo), resumo, agora, quem))
    return resumo


def restaurar(con: sqlite3.Connection, chave: str) -> bool:
    """Joga fora o ajuste e volta ao molde do pacote. Diz se havia ajuste."""
    c = _do_catalogo(chave)
    try:
        apagadas = banco(con).escrever(
            "DELETE FROM mo_moldes WHERE chave = %s RETURNING chave",
            (c["chave"],))
    except sqlite3.OperationalError:
        return False
    return len(apagadas) > 0


def chave_da_especie(especie) -> str | None:
    """A chave do molde daquela espécie, ou None. Só calcula."""
    nome = str(especie or "").strip().upper()
    if nome == "CASAMENTO_RELIGIOSO":
        nome = "CASAMENTO"          # muda de livro, e não de papel
    for m in MOLDES:
        if m["especie"] == nome:
            return m["chave"]
    return None
