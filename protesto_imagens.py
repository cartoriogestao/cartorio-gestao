"""
AS IMAGENS DOS TÍTULOS QUE A CRA ENTREGA.

O QUE ELAS SÃO, e por que o módulo faltava
    A CRA entrega o título em duas partes: o **registro** de 600 posições, que
    o sistema já lê, e a **imagem** do papel — a duplicata, a nota, a certidão
    de dívida —, que vem num `.zip` à parte.

    O menu da CRA21 pede as duas: «Download remessa» e **«Download imagens»**,
    lado a lado na lista de pendências. O sistema fazia a primeira e ignorava a
    segunda.

    E a imagem não é enfeite: **é o título**. O que se protesta é o documento,
    e é ele que o devedor pede para ver quando vem ao balcão discutir a dívida.

O NOME DO ARQUIVO É A CHAVE, E ELE FOI MEDIDO
    `49000005243_00000002135_01.pdf`, dentro de uma pasta com o código do
    apresentante (`1LV/`).

        · **nosso número** do título — `49000005243`
        · **documento do devedor** — `00000002135`
        · **sequencial** da imagem naquele título — `01`

    Conferido contra a produção em 31/08/2026: as duas primeiras partes
    apontam para o **mesmo título** (#1331, de JOSE VALE DOS SANTOS ROCHEDO).
    Não é coincidência de número solto: são dois caminhos independentes que
    chegam ao mesmo lugar, e é isso que torna o nome confiável como chave.

O DOCUMENTO CONFERE, E NÃO SÓ ACHA
    Casar só pelo nosso número acharia o título; casar também pelo documento do
    devedor **prova** que é aquele. Nosso número se repete entre apresentantes
    — o acervo tem 53 grupos e 111 títulos repetindo o mesmo —, e anexar a
    imagem de um título ao título de outra pessoa é pior que não anexar: o
    balcão mostraria ao devedor a dívida de um terceiro.

    Quando o documento não bate, a imagem **não entra** e o pacote diz por quê.

CONFERIR E GUARDAR SÃO DOIS PASSOS
    O primeiro não grava nada. É a mesma disciplina da remessa, e pelo mesmo
    motivo: cinquenta imagens que entram sem ninguém olhar são cinquenta
    anexos para desfazer à mão.

O MESMO ARQUIVO NÃO ENTRA DUAS VEZES
    A trava é o **sha256** do conteúdo, e não o nome: a CRA reenvia o pacote
    quando alguém pede de novo, e o mesmo PDF chegaria com o mesmo nome. Anexo
    repetido não estraga nada — só faz a ficha do título crescer com cópias da
    mesma folha, e quem abre não sabe qual olhar.
"""
from __future__ import annotations

import hashlib
import re
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any

import tetos_de_entrada as TETO
from bd_nativo import banco

# A ENTIDADE DOS ANEXOS DO TÍTULO. `attachments` é a tabela geral da casa —
# ela já serve expediente e tarefa —, e o que separa um dono do outro é este
# par. Criar uma tabela própria daria uma segunda forma de guardar arquivo.
ENTIDADE = "PT_TITULO"

# O NOME MEDIDO: `<nosso numero>_<documento do devedor>_<sequencial>.pdf`.
#
#   Os separadores são `_`, e o nosso número REAL pode ter barra
#   (`17375280/041` aparece em 46 registros de 2026) — mas no nome do arquivo
#   ele vem só com dígitos. Por isso a comparação é feita **por dígitos**, e
#   não pelo texto cru.
#
# **O SEQUENCIAL É OPCIONAL — correção de 15/10/2026.** O pacote de
# 15/07/2026 trazia `<nosso>_<documento>_01.pdf`, e foi por ele que o nome se
# mediu; o de 07/10/2026 traz os CINCO arquivos sem ele
# (`<nosso>_<documento>.pdf`), e com o sequencial obrigatório nenhum dos cinco
# casava — o pacote inteiro voltava «não casa com título nenhum». A dupla
# chave (nosso número + documento) continua inteira nos dois formatos; o
# sequencial só separava a frente do verso, e quem o perde é o nome, não o
# título.
NOME_DA_IMAGEM = re.compile(
    r"^(?P<nosso_numero>[^_]+)_(?P<documento>[^_.]+)"
    r"(?:_(?P<sequencia>[^_.]+))?"
    r"\.(?P<extensao>[A-Za-z0-9]+)$")

# O que a CRA manda. PDF em 1 de 1 medido; os outros entram porque imagem de
# título escaneado também chega assim, e recusar por extensão faria o balcão
# não ter o documento por causa do formato.
EXTENSOES = ("pdf", "png", "jpg", "jpeg", "tif", "tiff")

LIMITE_DO_PACOTE = 200 * 1024 * 1024        # 200 MB
LIMITE_DE_UMA_IMAGEM = 25 * 1024 * 1024     # 25 MB


class ImagemError(ValueError):
    """Erro de regra das imagens, com a mensagem pronta para o balcão."""


def so_digitos(valor: Any) -> str:
    return "".join(c for c in str(valor or "") if c.isdigit())


def _sha256(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()


# ------------------------------------------------------------- ler o pacote


def ler_pacote(conteudo: bytes) -> list[dict]:
    """Abre o `.zip` e devolve o que há dentro. NÃO grava e NÃO decide nada.

    Cada item traz o nome como veio, as três partes decodificadas e o conteúdo.
    O que não tem forma de nome de imagem entra com `partes=None` — e não é
    descartado aqui: quem decide o que fazer com ele é `conferir`, que tem o
    banco na mão para dizer por quê.
    """
    if not conteudo:
        raise ImagemError("O arquivo está vazio.")
    if len(conteudo) > LIMITE_DO_PACOTE:
        raise ImagemError(
            f"O pacote tem {len(conteudo) // 1024 // 1024} MB, acima do limite "
            f"de {LIMITE_DO_PACOTE // 1024 // 1024} MB. Baixe da CRA em partes "
            f"menores.")
    try:
        pacote = zipfile.ZipFile(BytesIO(conteudo))
    except zipfile.BadZipFile as erro:
        raise ImagemError(
            "Este arquivo não é um pacote .zip de imagens da CRA. Baixe de "
            "novo em «Download imagens» e mande o arquivo como ele veio."
        ) from erro
    # O ÍNDICE SE CONFERE ANTES DE LER (LX12, LS02 M2, 19/10/2026): o limite
    # de 200 MB acima é do arquivo COMPACTADO; um zip de 200 MB pode se abrir
    # em muito mais, e cada membro era lido inteiro antes de o teto de 25 MB
    # por imagem recusá-lo.
    try:
        TETO.conferir_pacote(pacote)
    except TETO.TetoExcedido as erro:
        raise ImagemError(str(erro)) from erro

    itens: list[dict] = []
    for info in pacote.infolist():
        if info.is_dir():
            continue
        caminho = info.filename.replace("\\", "/")
        nome = caminho.rsplit("/", 1)[-1]
        # A PASTA É O APRESENTANTE — `1LV/49000005243_...`. Ela não decide
        # nada (o título já diz de quem é), mas fica registrada: quando a CRA
        # mandar um pacote com dois apresentantes, é por ela que se separa.
        pasta = caminho.rsplit("/", 1)[0] if "/" in caminho else ""
        achado = NOME_DA_IMAGEM.match(nome)
        partes = None
        if achado and achado.group("extensao").lower() in EXTENSOES:
            partes = {
                "nosso_numero": achado.group("nosso_numero"),
                "documento": achado.group("documento"),
                "sequencia": achado.group("sequencia") or "",
                "extensao": achado.group("extensao").lower(),
            }
        tamanho, conteudo = _ler_ate_o_limite(pacote, info)
        itens.append({"nome": nome, "apresentante_pasta": pasta,
                      "tamanho": tamanho, "partes": partes,
                      "conteudo": conteudo})
    if not itens:
        raise ImagemError("O pacote não tem nenhum arquivo dentro.")
    return itens


def _ler_ate_o_limite(pacote: zipfile.ZipFile, info: zipfile.ZipInfo) -> tuple[int, bytes]:
    """(tamanho, conteúdo) do membro; acima de `LIMITE_DE_UMA_IMAGEM`, o
    conteúdo fica VAZIO e não se lê (LX12, LS02 M2).

    A imagem grande demais já era recusada por `_por_que_nao_entra` — mas
    depois de lida inteira para a memória. Agora nem se lê: o tamanho
    declarado basta para a recusa, e a leitura corta em limite+1, porque o
    cabeçalho do zip pode mentir para baixo.
    """
    if info.file_size > LIMITE_DE_UMA_IMAGEM:
        return info.file_size, b""
    partes: list[bytes] = []
    lidos = 0
    with pacote.open(info) as fonte:
        while lidos <= LIMITE_DE_UMA_IMAGEM:
            pedaco = fonte.read(min(1024 * 1024, LIMITE_DE_UMA_IMAGEM + 1 - lidos))
            if not pedaco:
                break
            partes.append(pedaco)
            lidos += len(pedaco)
    if lidos > LIMITE_DE_UMA_IMAGEM:
        return lidos, b""
    return lidos, b"".join(partes)


# --------------------------------------------------------------- conferir


def conferir(con: Any, conteudo: bytes) -> dict:
    """Diz o que entraria, e o que não entraria e por quê. Só LÊ.

    NÃO GRAVA NADA — é o primeiro dos dois passos. Quem olha esta lista está
    prestes a anexar documento à ficha de títulos de gente de verdade.
    """
    bd = banco(con)
    itens = ler_pacote(conteudo)
    entram, ficam_de_fora, repetidas = [], [], []

    for item in itens:
        motivo = _por_que_nao_entra(bd, item)
        if motivo:
            ficam_de_fora.append({**_sem_conteudo(item), "motivo": motivo})
            continue
        titulo = _titulo_do_item(bd, item)
        ja = bd.um(
            """SELECT id FROM attachments
                WHERE entity_type=%s AND entity_id=%s AND sha256=%s""",
            (ENTIDADE, titulo["id"], _sha256(item["conteudo"])))
        destino = repetidas if ja else entram
        destino.append({**_sem_conteudo(item),
                        "titulo_id": titulo["id"],
                        "numero_titulo": titulo["numero_titulo"],
                        "devedor": titulo["devedor"]})

    return {"total": len(itens), "entram": entram,
            "repetidas": repetidas, "fora": ficam_de_fora}


def _sem_conteudo(item: dict) -> dict:
    """A tela mostra a lista; ela não precisa dos megabytes junto."""
    return {k: v for k, v in item.items() if k != "conteudo"}


def _titulo_do_item(con: Any, item: dict) -> dict | None:
    """Acha o título pelo nosso número E confere pelo documento do devedor.

    OS DOIS JUNTOS, e não um deles. O nosso número se repete entre
    apresentantes — 53 grupos e 111 títulos no acervo —, e anexar a imagem ao
    título de outra pessoa faria o balcão mostrar ao devedor a dívida de um
    terceiro.
    """
    partes = item.get("partes")
    if not partes:
        return None
    nosso = so_digitos(partes["nosso_numero"])
    documento = so_digitos(partes["documento"])
    if not nosso:
        return None
    bd = banco(con)
    linha = bd.um(
        """SELECT t.id, t.numero_titulo, d.nome devedor
             FROM pt_titulos t
             JOIN pt_devedores d ON d.titulo_id = t.id
            WHERE digitos(t.nosso_numero) = %s
              AND digitos(d.documento_numero) = %s
            ORDER BY t.id, d.id LIMIT 1""", (nosso, documento))
    return dict(linha) if linha else None


def _por_que_nao_entra(con: Any, item: dict) -> str:
    """A frase de balcão, ou vazio quando entra."""
    if item["tamanho"] > LIMITE_DE_UMA_IMAGEM:
        return (f"tem {item['tamanho'] // 1024 // 1024} MB, acima do limite de "
                f"{LIMITE_DE_UMA_IMAGEM // 1024 // 1024} MB por imagem")
    if not item.get("partes"):
        return ("o nome não tem a forma que a CRA usa "
                "(nosso número, documento do devedor e sequência)")
    bd = banco(con)
    if _titulo_do_item(bd, item) is not None:
        return ""
    partes = item["partes"]
    # A RECUSA DIZ QUAL DAS DUAS PARTES FALHOU, porque o conserto é diferente:
    # título que não existe aqui é remessa que não foi recebida; documento que
    # não bate é imagem de outro título com o mesmo nosso número.
    existe = bd.um(
        "SELECT id FROM pt_titulos WHERE digitos(nosso_numero)=%s ORDER BY id LIMIT 1",
        (so_digitos(partes["nosso_numero"]),))
    if not existe:
        return (f"não há título com o nosso número {partes['nosso_numero']} — "
                f"a remessa dele ainda não foi recebida")
    return (f"o título {partes['nosso_numero']} existe, mas o devedor dele não "
            f"tem o documento {partes['documento']} — esta imagem é de outro "
            f"título com o mesmo nosso número")


# --------------------------------------------------------------- guardar


def guardar(con: Any, conteudo: bytes, *, pasta_de_arquivos: Any,
            agora: str, usuario_id: int | None = None,
            origem: str | None = None) -> dict:
    """Anexa as imagens aos títulos. ESCREVE, e grava arquivo em disco.

    O QUE NÃO ENTRA NÃO DERRUBA O PACOTE. Uma imagem sem título casado é uma;
    as outras quarenta e cinco continuam sendo o trabalho do dia — é a mesma
    regra do lote da remessa, em que título ruim não impede os bons de entrar.
    """
    bd = banco(con)
    conferencia = conferir(bd, conteudo)
    if not conferencia["entram"]:
        raise ImagemError(
            f"Nenhuma das {conferencia['total']} imagens deste pacote entra: "
            f"{len(conferencia['repetidas'])} já estão anexadas e "
            f"{len(conferencia['fora'])} não casam com título nenhum.")

    itens = {i["nome"]: i for i in ler_pacote(conteudo)}
    raiz = Path(pasta_de_arquivos) / "Protesto" / "Titulos"
    guardadas = []
    for previsto in conferencia["entram"]:
        item = itens[previsto["nome"]]
        titulo_id = previsto["titulo_id"]
        destino = raiz / str(titulo_id)
        destino.mkdir(parents=True, exist_ok=True)
        arquivo = destino / previsto["nome"]
        # NÃO SOBRESCREVE ARQUIVO COM O MESMO NOME E CONTEÚDO DIFERENTE: a
        # CRA pode reenviar a imagem corrigida, e apagar a anterior apagaria o
        # que a serventia recebeu antes. A segunda vira `…_2.pdf`.
        if arquivo.exists() and _sha256(arquivo.read_bytes()) != _sha256(item["conteudo"]):
            base, ponto, ext = previsto["nome"].rpartition(".")
            n = 2
            while (destino / f"{base}_{n}{ponto}{ext}").exists():
                n += 1
            arquivo = destino / f"{base}_{n}{ponto}{ext}"
        arquivo.write_bytes(item["conteudo"])

        novo = bd.escrever(
            """INSERT INTO attachments(entity_type, entity_id, original_name,
                   stored_name, stored_path, sha256, size_bytes, description,
                   uploaded_by, uploaded_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               RETURNING id""",
            (ENTIDADE, titulo_id, previsto["nome"], arquivo.name,
             str(arquivo), _sha256(item["conteudo"]), item["tamanho"],
             "Imagem do título recebida da CRA"
             + (f" ({origem})" if origem else ""),
             usuario_id, agora))
        guardadas.append({"anexo_id": int(novo[0]["id"]),
                          "titulo_id": titulo_id,
                          "nome": previsto["nome"]})

    return {"guardadas": guardadas,
            "repetidas": len(conferencia["repetidas"]),
            "fora": conferencia["fora"],
            "total": conferencia["total"]}


# --------------------------------------------------------------- consultas


def imagens_do_titulo(con: Any, titulo_id: int) -> list[dict]:
    """As imagens anexadas àquele título, da mais nova. Só LÊ."""
    return [dict(r) for r in banco(con).ler(
        """SELECT id, original_name, stored_path, sha256, size_bytes,
                  description, uploaded_at
             FROM attachments WHERE entity_type=%s AND entity_id=%s
            ORDER BY id DESC""", (ENTIDADE, int(titulo_id)))]


def quantas(con: Any, titulo_id: int) -> int:
    """Quantas imagens o título tem. Só LÊ — a ficha pergunta isso sempre."""
    linha = banco(con).um(
        "SELECT COUNT(*) AS c FROM attachments WHERE entity_type=%s AND entity_id=%s",
        (ENTIDADE, int(titulo_id)))
    return int(linha["c"] if linha else 0)


def titulos_sem_imagem(con: Any, limite: int = 100) -> list[dict]:
    """Os títulos vivos que não têm imagem nenhuma. Só LÊ.

    É a lista de trabalho: cada um deles é um título que a casa apontou sem ter
    o documento à mão. Ela não acusa o acervo — os 1.366 que vieram do E-Ofício
    têm imagem em papel, na pasta, e a CRA não os reenvia.
    """
    return [dict(r) for r in banco(con).ler(
        """SELECT t.id, t.numero_titulo, t.nosso_numero, t.situacao,
                  t.criado_em
             FROM pt_titulos t
            WHERE t.origem <> 'EOFICIO'
              AND NOT EXISTS (SELECT 1 FROM attachments a
                               WHERE a.entity_type = %s AND a.entity_id = t.id)
            ORDER BY t.id DESC LIMIT %s""", (ENTIDADE, int(limite)))]
