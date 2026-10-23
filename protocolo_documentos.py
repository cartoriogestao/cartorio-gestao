"""Os documentos para qualificação, guardados no Protocolo Geral — relato #135.

O RELATO, DE 15/10/2026, ABERTO DA TAREFA 386 PELA ESCREVENTE DO RI E DAS NOTAS:

    «CRIAR NO PROTOCOLO GERAL OU EM NOTAS ABA DE ANEXAR DOCUMENTOS PARA FIM
     DE QUALIFICAÇÃO»

O QUE A TAREFA 386 MOSTROU. Ela é um parecer de qualificação registral da
prenotação 11.573 (escritura de inventário), e a descrição dela é um CAMINHO DE
PASTA no Proton Drive — «15. PROCESSOS PROTOCOLADOS\\RI\\REGISTRO ESCRITURAS\\
11573-…». Os documentos que sustentam a qualificação moravam fora do sistema,
numa pasta compartilhada que o backup da casa não alcança e que nenhuma tela
mostra a quem qualifica.

POR QUE NO PROTOCOLO GERAL, E NÃO NUMA TABELA NOVA. O protocolo do balcão
(`cx_protocolos`) é a porta por onde o cliente entrega papel nas seis
atribuições, e `ri_documentos` já declarava a entidade dele (`PROTOCOLO`) sem
que rota nenhuma gravasse com ela. O arquivo vai para a MESMA `attachments` do
expediente, da tarefa, da prenotação e do ato das Notas — uma segunda tabela de
anexo seria um segundo lugar onde procurar o mesmo papel.

O QUE ESTE MÓDULO ACRESCENTA À `attachments`, E SÓ ISTO:
    • o TIPO do documento (identidade, certidão, procuração anterior,
      matrícula…), porque quem qualifica procura o papel pelo que ele é;
    • a RETIRADA COM MOTIVO, em vez do `DELETE`: documento que sustentou uma
      qualificação não some do rastro. Quem retirou, quando e por quê ficam na
      própria linha, e o arquivo continua no disco.

O ATO VÊ O QUE O PROTOCOLO GUARDOU. A ponte é a chave do protocolo, e não o
nome do interessado: no RI, `cx_protocolos.ri_protocolo_id` (que o balcão
escolhe na tela do protocolo); nas Notas, `nt_atos.protocolo_id`, coluna que
existia desde a importação e estava vazia em 280 de 280 atos (medido em
15/10/2026 na produção, só leitura).
"""
from __future__ import annotations

import ri_documentos as RDOC
from bd_nativo import banco

ENTIDADE = RDOC.ENTIDADE_GERAL          # "PROTOCOLO" — a do protocolo do balcão

# O TIPO É ESCOLHA, E NÃO TEXTO LIVRE. Os exemplos são os do relato (identidade,
# certidão, procuração anterior, matrícula) e os papéis que a qualificação de
# escritura e de registro pede todo dia. «Outro» existe porque a lista não fecha
# — e aí a descrição é obrigatória, senão o arquivo vira «um documento».
TIPOS_DE_DOCUMENTO: tuple[tuple[str, str], ...] = (
    ("IDENTIDADE", "Documento de identidade (RG, CNH, CPF)"),
    ("CERTIDAO", "Certidão (nascimento, casamento, óbito, negativas)"),
    ("PROCURACAO", "Procuração anterior"),
    ("MATRICULA", "Matrícula ou certidão de ônus do imóvel"),
    ("TITULO", "Título apresentado (escritura, contrato, formal)"),
    ("TRIBUTO", "Guia ou quitação de tributo (ITBI, ITCMD, IPTU, ITR)"),
    ("COMPROVANTE", "Comprovante de endereço"),
    ("OUTRO", "Outro documento"),
)
ROTULO_DO_TIPO = dict(TIPOS_DE_DOCUMENTO)

# PDF E IMAGEM, E SÓ. A extensão sozinha não prova nada — renomear um `.exe`
# para `.pdf` leva um segundo —, e por isso o começo do arquivo também se
# confere. É a mesma lista curta que o navegador abre na tela
# (`ri_documentos.e_imagem`), menos o que o balcão não digitaliza.
ASSINATURAS: dict[str, tuple[bytes, ...]] = {
    ".pdf": (b"%PDF",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
}

# 25 MB POR ARQUIVO — o mesmo teto da ficha de firma, do comprovante do
# Protesto e da imagem do título (`notas_web.LIMITE_DA_FICHA`,
# `protesto_aviso.LIMITE_DO_COMPROVANTE`). Um teto diferente aqui faria o mesmo
# papel caber numa tela e não na vizinha.
LIMITE_POR_ARQUIVO = 25 * 1024 * 1024

# O piso do motivo é o mesmo da recusa de certidão e do fechamento de relato:
# dez letras. «erro» não diz a quem lê depois o que estava errado.
MOTIVO_MINIMO = 10

# AS COLUNAS ACRESCENTADAS À `attachments`. Só `ADD COLUMN`, idempotente: o
# banco da produção migra ao subir, e coluna que já existe não se toca.
MIGRACOES: tuple[tuple[str, str, str], ...] = (
    ("attachments", "documento_tipo", "TEXT"),
    ("attachments", "retirado_em", "TEXT"),
    ("attachments", "retirado_por", "TEXT"),
    ("attachments", "retirado_motivo", "TEXT"),
)

# Quem pode anexar e retirar: os perfis do balcão que trabalham o protocolo. O
# AUDITOR vê a lista e abre o arquivo, e não mexe — a mesma régua da rota que
# retira anexo do ato das Notas.
PAPEIS_QUE_ANEXAM = ("ADMIN", "MANAGER", "USER")


class DocumentoError(RDOC.DocumentoError):
    """Erro de regra, com mensagem pronta para o balcão."""


def init_protocolo_documentos_schema(con) -> None:
    """Acrescenta as colunas do tipo e da retirada. Idempotente.

    Banco mínimo de teste sem `attachments` passa calado: sem a tabela não há
    o que migrar, e ela nasce com o resto do esquema da casa.

    AS COLUNAS SE PERGUNTAM AO CATÁLOGO (`bd.tem_coluna`): módulo de domínio
    entra com teto zero de pergunta ao esquema do SQLite
    (`tests/test_portabilidade.py`).
    """
    bd = banco(con)
    for tabela, coluna, tipo in MIGRACOES:
        if not bd.tem_tabela(tabela):
            continue                                  # a tabela ainda não existe
        if not bd.tem_coluna(tabela, coluna):
            bd.escrever(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")


# ------------------------------------------------------------ o arquivo


def conferir_arquivo(nome: str, cabeca: bytes, tamanho: int) -> str:
    """Recusa o que não é PDF, JPG ou PNG, ou passa do teto. Devolve a extensão.

    Recebe só o começo do arquivo e o tamanho — quem chama mede sem gravar, e
    por isso nada chega ao disco antes de os arquivos do lote passarem todos.
    """
    nome = str(nome or "").strip()
    pos = nome.rfind(".")
    ext = nome[pos:].lower() if pos >= 0 else ""
    if ext not in ASSINATURAS:
        raise DocumentoError(
            f"«{nome or 'arquivo sem nome'}» não é PDF, JPG nem PNG. "
            "Digitalize o documento num desses formatos e anexe de novo.")
    if int(tamanho or 0) <= 0:
        raise DocumentoError(f"«{nome}» chegou vazio. Escolha o arquivo de novo.")
    if int(tamanho) > LIMITE_POR_ARQUIVO:
        mb = int(tamanho) / (1024 * 1024)
        raise DocumentoError(
            f"«{nome}» tem {mb:.1f} MB, e o limite é 25 MB por arquivo. "
            "Digitalize em resolução menor ou divida o documento.")
    if not any(bytes(cabeca or b"").startswith(a) for a in ASSINATURAS[ext]):
        raise DocumentoError(
            f"«{nome}» tem extensão {ext}, mas o conteúdo não é {ext[1:].upper()}. "
            "Abra o arquivo no computador e salve de novo no formato certo.")
    return ext


def medir_envio(arquivo) -> tuple[str, bytes, int]:
    """Nome, começo e tamanho de um arquivo enviado pelo formulário. Não grava.

    Lê o fluxo e volta ao começo, para quem grava depois receber o arquivo
    inteiro — e nenhum identificador de arquivo fica aberto no Windows.
    """
    fluxo = arquivo.stream
    fluxo.seek(0, 2)
    tamanho = int(fluxo.tell())
    fluxo.seek(0)
    cabeca = fluxo.read(16)
    fluxo.seek(0)
    return (arquivo.filename or ""), cabeca, tamanho


# ------------------------------------------------------------ o protocolo


def protocolo(con, protocolo_id) -> dict | None:
    """O protocolo do balcão, ou None. Só LÊ."""
    return banco(con).um("SELECT * FROM cx_protocolos WHERE id = %s",
                         (int(protocolo_id),))


def _exigir_protocolo_aberto(con, protocolo_id) -> dict:
    import caixa_protocolo as CXP
    p = protocolo(con, protocolo_id)
    if not p:
        raise DocumentoError("Protocolo não encontrado.")
    # PROTOCOLO ENCERRADO NÃO RECEBE PAPEL NOVO. Encerrar diz que o atendimento
    # terminou; documento chegando depois disso é sinal de que ele não
    # terminou — e o caminho é reabrir, que deixa rastro com motivo.
    if CXP.esta_encerrado(p.get("situacao")):
        raise DocumentoError(
            f"O protocolo {p['numero']} está encerrado. Reabra-o (com o motivo) "
            "antes de anexar ou retirar documento.")
    return p


def registrar(con, protocolo_id, info: dict, *,
              tipo: str, descricao: str | None, usuario_id, agora: str) -> int:
    """Grava um arquivo JÁ SALVO no disco como documento do protocolo.

    `info` é o que `storage.save_upload` devolve. Chamar dentro da transação
    da rota: o lote entra inteiro ou não entra.
    """
    bd = banco(con)
    _exigir_protocolo_aberto(bd, protocolo_id)
    tipo = (tipo or "").strip().upper()
    if tipo not in ROTULO_DO_TIPO:
        raise DocumentoError("Escolha o tipo do documento.")
    descricao = (descricao or "").strip() or None
    if tipo == "OUTRO" and not descricao:
        raise DocumentoError(
            "Para «Outro documento», escreva na descrição o que ele é — "
            "senão quem qualifica abre um arquivo sem saber o que procura.")
    novo = bd.escrever(
        """INSERT INTO attachments(entity_type, entity_id, original_name,
               stored_name, stored_path, sha256, size_bytes, description,
               uploaded_by, uploaded_at, documento_tipo)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           RETURNING id""",
        (ENTIDADE, int(protocolo_id), info["original_name"], info["stored_name"],
         info["stored_path"], info["sha256"], int(info["size_bytes"]),
         descricao, int(usuario_id) if usuario_id else None, agora, tipo))
    return int(novo[0]["id"])


def retirar(con, protocolo_id, anexo_id, *, motivo: str,
            por: str, agora: str) -> dict:
    """Tira o documento da lista, SEM apagar: marca quem, quando e por quê.

    O arquivo fica no disco e a linha fica no banco. Documento que sustentou
    uma qualificação e some sem rastro é a pergunta que a correição faz e
    ninguém sabe responder.
    """
    bd = banco(con)
    _exigir_protocolo_aberto(bd, protocolo_id)
    motivo = (motivo or "").strip()
    if len(motivo) < MOTIVO_MINIMO:
        raise DocumentoError(
            "Diga por que o documento sai (pelo menos dez letras) — por exemplo "
            "«digitalizado de cabeça para baixo» ou «documento de outro cliente».")
    bd._escrita()
    r = bd.um("SELECT * FROM attachments WHERE id = %s FOR UPDATE", (int(anexo_id),))
    if (not r or r["entity_type"] != ENTIDADE
            or int(r["entity_id"]) != int(protocolo_id)):
        raise DocumentoError("Este documento não é deste protocolo.")
    if r["retirado_em"]:
        raise DocumentoError(
            f"«{r['original_name']}» já foi retirado em {r['retirado_em'][:16]}.")
    bd.escrever(
        """UPDATE attachments SET retirado_em = %s, retirado_por = %s,
                  retirado_motivo = %s
            WHERE id = %s""", (agora, por or None, motivo, int(anexo_id)))
    return dict(r) | {"retirado_em": agora, "retirado_por": por,
                      "retirado_motivo": motivo}


def _enfeitar(d: dict) -> dict:
    tipo = d.get("documento_tipo")
    d["tipo_rotulo"] = ROTULO_DO_TIPO.get(tipo or "", "") if tipo else ""
    d["abre_na_tela"] = RDOC.e_imagem(d.get("original_name"))
    return d


def documentos(con, protocolo_id) -> dict:
    """`{ativos, retirados}` do protocolo, do mais novo ao mais velho. Só LÊ.

    Lê pela mesma `ri_documentos.documentos_de` que a prenotação usa — e só
    separa as duas listas. Os retirados continuam à vista, com o motivo:
    sumir da tela seria o `DELETE` com outra cara.
    """
    todos = [_enfeitar(dict(d)) for d in
             RDOC.documentos_de(con, ENTIDADE, int(protocolo_id))]
    return {"ativos": [d for d in todos if not d.get("retirado_em")],
            "retirados": [d for d in todos if d.get("retirado_em")]}


# ------------------------------------------------------------ as pontes


def protocolo_do_ato_de_notas(con, ato_id) -> dict | None:
    """O protocolo do balcão ligado ao ato das Notas, ou None. Só LÊ."""
    bd = banco(con)
    a = bd.um("SELECT protocolo_id FROM nt_atos WHERE id = %s", (int(ato_id),))
    if not a or not a["protocolo_id"]:
        return None
    return protocolo(bd, a["protocolo_id"])


def anexos_do_ato_de_notas(con, ato_id) -> dict:
    """TODOS os papéis à vista de quem lavra o ato das Notas. Só LÊ.

    Devolve `{"do_ato": [...], "do_protocolo": [...], "protocolo": dict|None}`.
    Cada anexo é a linha de `attachments` (com `stored_path`, `original_name`,
    `size_bytes`, `sha256`) — o caminho do arquivo está ali, para quem precisa
    abri-lo (a contagem de folhas do arquivamento, por exemplo).

    `do_protocolo` traz só os ATIVOS: o retirado com motivo não é papel do ato.
    """
    bd = banco(con)
    do_ato = [_enfeitar(dict(r)) for r in bd.ler(
        """SELECT a.*, u.full_name AS enviado_por_nome
             FROM attachments a LEFT JOIN users u ON u.id = a.uploaded_by
            WHERE a.entity_type = 'NT_ATO' AND a.entity_id = %s
            ORDER BY a.id""", (int(ato_id),))]
    do_ato = [d for d in do_ato if not d.get("retirado_em")]
    p = protocolo_do_ato_de_notas(bd, ato_id)
    do_protocolo = documentos(bd, p["id"])["ativos"] if p else []
    return {"do_ato": do_ato, "do_protocolo": do_protocolo, "protocolo": p}


def da_prenotacao(con, ri_protocolo_id) -> dict:
    """Os documentos do(s) protocolo(s) geral(is) ligado(s) a uma prenotação do RI.

    A ponte é `cx_protocolos.ri_protocolo_id`, que o balcão escolhe na tela do
    protocolo — nunca o nome do apresentante. Devolve
    `{"protocolos": [...], "ativos": [...]}`; cada documento leva
    `protocolo_numero`, para quem lê saber de que atendimento veio. Só os
    ativos: o retirado com motivo não é papel do ato. Só LÊ.
    """
    if ri_protocolo_id is None or not str(ri_protocolo_id).strip().isdigit():
        return {"protocolos": [], "ativos": []}
    bd = banco(con)
    protocolos = bd.ler(
        "SELECT * FROM cx_protocolos WHERE ri_protocolo_id = %s ORDER BY id",
        (int(ri_protocolo_id),))
    ativos = []
    for p in protocolos:
        for d in documentos(bd, p["id"])["ativos"]:
            ativos.append(d | {"protocolo_numero": p["numero"]})
    return {"protocolos": protocolos, "ativos": ativos}


# QUALQUER ATRIBUIÇÃO SE LIGA AO ATO DAS NOTAS — decisão do oficial em
# 15/10/2026, respondendo ao relato #135. A primeira versão aceitava só
# protocolo NOTAS, por cautela contra número digitado errado; ele decidiu que
# o atendimento pode ter sido aberto em qualquer atribuição (o cliente que
# protocolou no RI e lavra a escritura aqui, por exemplo). O que protege contra
# o engano agora é a tela: ela mostra o número, a atribuição e o interessado do
# protocolo ligado, e a ligação só muda enquanto o ato está em lavratura.


def vincular_ato_de_notas(con, ato_id, numero: str) -> dict:
    """Liga o ato das Notas ao protocolo do balcão pelo NÚMERO. Devolve o protocolo.

    Só enquanto o ato está em lavratura: depois de lançado, trocar a origem dos
    papéis seria reescrever de onde veio o que fundamentou o ato.
    """
    bd = banco(con)
    bd._escrita()
    a = bd.um("SELECT id, situacao, protocolo_id FROM nt_atos WHERE id = %s FOR UPDATE",
              (int(ato_id),))
    if not a:
        raise DocumentoError("Ato não encontrado.")
    if (a["situacao"] or "") != "EM_LAVRATURA":
        raise DocumentoError(
            "O ato já foi lançado no livro; o protocolo ligado a ele não muda mais.")
    if a["protocolo_id"]:
        raise DocumentoError(
            "Este ato já está ligado a um protocolo. Desfaça a ligação antes de "
            "ligar outro.")
    numero = (numero or "").strip()
    if not numero:
        raise DocumentoError("Digite o número do protocolo, por exemplo 2026.10.42.")
    p = bd.um("SELECT * FROM cx_protocolos WHERE numero = %s ORDER BY id LIMIT 1",
              (numero,))
    if not p:
        raise DocumentoError(f"Não há protocolo nº {numero}.")
    bd.escrever("UPDATE nt_atos SET protocolo_id = %s WHERE id = %s",
                (int(p["id"]), int(ato_id)))
    return dict(p)


def desvincular_ato_de_notas(con, ato_id) -> dict | None:
    """Desfaz a ligação, ainda em lavratura. Devolve o protocolo que saiu."""
    bd = banco(con)
    bd._escrita()
    a = bd.um("SELECT id, situacao, protocolo_id FROM nt_atos WHERE id = %s FOR UPDATE",
              (int(ato_id),))
    if not a:
        raise DocumentoError("Ato não encontrado.")
    if (a["situacao"] or "") != "EM_LAVRATURA":
        raise DocumentoError(
            "O ato já foi lançado no livro; o protocolo ligado a ele não muda mais.")
    if not a["protocolo_id"]:
        raise DocumentoError("Este ato não está ligado a protocolo nenhum.")
    p = protocolo(bd, a["protocolo_id"])
    bd.escrever("UPDATE nt_atos SET protocolo_id = NULL WHERE id = %s", (int(ato_id),))
    return p
