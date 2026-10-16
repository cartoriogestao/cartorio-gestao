"""
A REMESSA DA CRA — o passo do meio-dia.

O ROTEIRO DO OFICIAL diz, nos passos elementares diarios:

    *** MEIO DIA (das 11h as 13h): 1) recebimento de remessa, confirmacao e
        emissao do aviso; 2) verificacao de desistencias

Recebimento, confirmacao e aviso sao UM movimento so, e nao tres avulsos. Este
modulo faz os dois primeiros; o aviso de intimacao continua na ficha do titulo.

POR QUE ELE E O MAIOR BURACO QUE FALTAVA
    93% dos titulos desta casa entram pela CRA — 7 em seis anos foram
    digitados. `protesto_arquivo.ler()` sabia ler o arquivo desde o comeco, e
    `cadastrar_titulo` sabia gravar; o que nao existia era o lugar onde uma
    coisa vira a outra. Enquanto isso, o balcao nao tinha por onde receber o
    que a Central manda todo dia.

    E o mesmo achado que se repetiu a revisao inteira: funcao de dominio
    pronta e testada que nenhuma tela chama.

O QUE ESTE MODULO DECIDIU, E POR QUE

    **O mesmo arquivo nao entra duas vezes**, e a trava mora no banco:
    `UNIQUE(hash_arquivo)` em `pt_remessas`. Subir a mesma remessa de novo
    apontaria todos os titulos outra vez, e apontamento nao se desfaz — sairia
    protocolo dobrado, folha gasta e dois avisos para o mesmo devedor. O hash
    e do conteudo NORMALIZADO (as linhas validas, unidas por `\\n`), porque o
    mesmo arquivo salvo noutro programa troca CRLF por LF e continua sendo o
    mesmo arquivo.

    **Conferir e receber sao dois passos.** `conferir()` nao grava nada e
    mostra o lote inteiro: o que vem, o que ja entrou, o que o contrato da CRA
    recusa e o que o proprio arquivo nao fecha. So depois `receber()` escreve.
    Lote de cinquenta titulos que entra sem ninguem olhar e cinquenta atos para
    desfazer a mao.

    **Titulo ruim nao derruba o lote.** Os bons entram, os recusados saem
    listados com o motivo. E a mesma regra de `conferir_remessa`: recusar o
    arquivo inteiro porque um titulo de mil veio torto e devolver ao banco mil
    titulos bons junto com o ruim.

    **A CONFIRMACAO confirma o QUE ENTROU**, e isso foi medido, nao suposto.
    Em 138 pares remessa-confirmacao um para um dos arquivos reais desta casa:
    130 confirmacoes trazem exatamente os titulos da remessa, 8 trazem menos e
    NENHUMA traz titulo que nao veio. Confirmacao parcial existe; confirmacao
    que inventa titulo, nao.

    **A chave de origem e a posicao no LOTE**, `CRA:<remessa_id>:<sequencial>`,
    e nao o nosso numero. Medido no acervo: 53 grupos e 111 titulos repetem o
    `strNossoNumero` — 8% da casa. Chavear por ele faria a segunda apresentacao
    de um titulo sumir dentro da primeira, calada.

    **UM ARQUIVO PODE TRAZER MAIS DE UM LOTE**, e de apresentantes
    diferentes. Medido nos 197 arquivos reais: 6 sao multi-lote, e em 3 deles
    os lotes sao de apresentantes distintos — um traz 237, 1LV e 033 juntos.
    Ler so o primeiro cabecalho poria os titulos dos outros dois apresentantes
    no primeiro, e o retorno voltaria para quem nao apresentou. Por isso o
    arquivo se SEPARA em lotes antes de qualquer coisa, e cada lote e uma
    remessa com o seu apresentante, o seu numero e a sua confirmacao.

    **O lote NAO sela e NAO cobra.** Selar cinquenta titulos e cinquenta
    chamadas de rede de 20 s, e `db.transaction()` e `BEGIN IMMEDIATE`: a casa
    inteira ficaria no `busy_timeout` esperando o lote. Eles entram e aparecem
    em `atos_sem_selo` e `atos_sem_cobranca`, que sao as telas do outro lado e
    existem exatamente para isso.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any

import protesto as PT
import protesto_arquivo as PA
import protesto_cra as CRA
import protesto_cra_xml as PCRAXML

# O tipo do arquivo que CHEGA. Note que o codigo nao e o espelho dos outros
# tres: os de saida sao `SDTBFO...` e a remessa e `BFOSDTTPR`. Nao e engano de
# transcricao — e o que vem no cabecalho dos 197 arquivos medidos.
TIPO_DA_REMESSA = "BFOSDTTPR"

# O que a confirmacao devolve, e o que o retorno guarda dela.
TIPO_DA_CONFIRMACAO = "SDTBFOCRT"

# Situacoes em que um titulo ainda esta vivo nesta casa. Titulo vivo com o
# mesmo nosso numero e apresentante nao e recusa — e AVISO, para o escrevente
# olhar antes de apontar dois.
SITUACOES_VIVAS = ("RECEBIDO", "APONTADO", "INTIMADO", "PROTESTADO")


class RemessaError(ValueError):
    """Erro de regra da remessa, com a mensagem pronta para o balcao."""


# ------------------------------------------------------------ o arquivo


def normalizar(conteudo: str | bytes) -> str:
    """O arquivo reduzido ao que ele E: as linhas validas, unidas por `\\n`.

    O mesmo arquivo salvo noutro programa troca CRLF por LF, ou ganha uma
    linha em branco no fim, e passaria pela trava do hash como se fosse outro.
    Normalizar antes de assinar e o que faz a trava valer.
    """
    if isinstance(conteudo, bytes):
        conteudo = conteudo.decode("latin-1")
    linhas = [x for x in conteudo.replace("\r\n", "\n").replace("\r", "\n")
              .split("\n") if x.strip()]
    return "\n".join(linhas)


def separar(conteudo: str | bytes) -> list[str]:
    """O arquivo partido nos LOTES que ele traz. So calcula.

    Um lote e cabecalho (`0`), titulos (`1`) e rodape (`9`). A CRA manda mais
    de um no mesmo arquivo em 6 dos 197 medidos, e em 3 deles os lotes sao de
    APRESENTANTES DIFERENTES — o pior caso, porque o erro nao aparece na
    leitura: os titulos entram, so que atribuidos a quem nao os apresentou, e
    o defeito so se descobre quando o retorno volta para o apresentante errado.

    Arquivo de um lote so — 191 dos 197 — sai daqui como uma lista de um.
    """
    texto = normalizar(conteudo)
    if not texto:
        return []
    lotes: list[list[str]] = []
    atual: list[str] = []
    for linha in texto.split("\n"):
        if linha[:1] == "0" and atual:
            lotes.append(atual)
            atual = []
        atual.append(linha)
        if linha[:1] == "9":
            lotes.append(atual)
            atual = []
    if atual:
        lotes.append(atual)
    return ["\n".join(x) for x in lotes]


def hash_remessa(conteudo: str | bytes) -> str:
    """Impressao digital do arquivo que chegou, ja normalizado."""
    return hashlib.sha256(normalizar(conteudo).encode("latin-1",
                                                      errors="replace")).hexdigest()


def _cabecalho(a: PA.Arquivo) -> dict:
    c = a.cabecalho
    return {
        "apresentante_codigo": str(c.get("codigo_do_apresentante") or "").strip(),
        "apresentante_nome": str(c.get("nome_do_apresentante") or "").strip(),
        "dia": str(c.get("data_do_movimento") or "")[:10],
        "numero_da_remessa": str(c.get("numero_da_remessa") or "").strip(),
        "tipo": a.tipo,
        "nome_do_tipo": a.nome_do_tipo,
    }


def _exigir_remessa(a: PA.Arquivo) -> None:
    """Recusa arquivo que nao e remessa, dizendo o que ele e.

    AS PASTAS DO E-OFICIO MENTEM — ha remessa dentro de `Retorno` —, e por
    isso a tela nao pode confiar no nome nem na pasta. O tipo vem das posicoes
    53-61 do cabecalho, e e ele que manda.
    """
    if a.tipo == TIPO_DA_REMESSA:
        return
    conhecido = PA.TIPOS.get(a.tipo, {})
    if conhecido:
        raise RemessaError(
            f"Este arquivo não é uma remessa: o cabeçalho diz que ele é "
            f"«{conhecido.get('nome')}» ({a.tipo}). A remessa é a que a CRA "
            f"manda com os títulos para apontar. Confira o arquivo que baixou "
            f"— as pastas costumam misturar os quatro tipos.")
    raise RemessaError(
        f"O cabeçalho deste arquivo diz que ele é do tipo «{a.tipo}», que não "
        f"está no catálogo da CRA. A remessa é do tipo {TIPO_DA_REMESSA}.")


# ------------------------------------------------------------ conferir


def remessa_pelo_hash(con: sqlite3.Connection,
                      hash_arquivo: str) -> sqlite3.Row | None:
    """A remessa que ja entrou com esse mesmo arquivo. So LE."""
    return con.execute("SELECT * FROM pt_remessas WHERE hash_arquivo=?",
                       (hash_arquivo,)).fetchone()


def remessa_pela_chave_xml(con: sqlite3.Connection,
                           chave: str) -> sqlite3.Row | None:
    """Lote XML que ja entrou com a mesma chave de idempotencia. So LE."""
    return con.execute(
        "SELECT * FROM pt_remessas WHERE origem_xml_chave=?", (chave,)
    ).fetchone()


def _ambiente_cra(ambiente: str) -> str:
    """O ambiente CRA do lote XML que entra: **sempre PRODUÇÃO desde
    14/10/2026** — ordem do oficial: «tire a opção de funcionar na
    homologação, agora é tudo produção».

    **O QUE O CHAMADOR MANDA NÃO MUDA ISSO, e é de propósito.** A rota de
    receber remessa manda «HOMOLOGACAO» quando o formulário chega sem o campo
    — era o padrão até 13/10 —, e o lote entraria marcado como de
    homologação: a confirmação e o andamento dele seguiriam para a CRA de
    HOMOLOGAÇÃO, com os títulos já apontados no livro de verdade. Medido em
    14/10/2026: a produção ainda não tinha recebido remessa nenhuma
    (`pt_remessas` vazia), e por isso nenhum lote foi atingido.

    Lote antigo gravado como homologação continua como está — dado gravado
    não se reescreve.
    """
    return "PRODUCAO"


def _titulos_vivos_iguais(con: sqlite3.Connection, dados: dict) -> list[dict]:
    """Titulos vivos com o mesmo nosso numero e o mesmo apresentante. So LE.

    NAO E RECUSA, E AVISO. O nosso numero se repete de verdade: 53 grupos e
    111 titulos no acervo desta casa. Pode ser reapresentacao legitima — e
    pode ser o mesmo lote subindo duas vezes por outro caminho. Quem decide e
    quem esta no balcao; o sistema mostra.
    """
    nosso = (dados.get("nosso_numero") or "").strip()
    ap = (dados.get("apresentante_codigo") or "").strip()
    if not nosso or not ap:
        return []
    marcas = ",".join("?" * len(SITUACOES_VIVAS))
    return [dict(r) for r in con.execute(
        f"""SELECT id, numero_titulo, nosso_numero, situacao, protocolo,
                   criado_em
              FROM pt_titulos
             WHERE nosso_numero = ? AND apresentante_codigo = ?
               AND situacao IN ({marcas})
             ORDER BY id DESC LIMIT 5""",
        (nosso, ap, *SITUACOES_VIVAS))]


def conferir(con: sqlite3.Connection, conteudo: str | bytes) -> dict:
    """Le o arquivo inteiro e diz o que vai acontecer. NAO GRAVA NADA.

    E o primeiro dos dois passos, e ele existe para o lote nao entrar sem
    ninguem olhar: lote de cinquenta titulos que entra sem conferencia sao
    cinquenta atos para desfazer a mao.

    Devolve UMA ENTRADA POR LOTE em `lotes` — quase sempre um so —, cada uma
    com o seu apresentante, o que o arquivo nao fecha, e uma linha por titulo
    dizendo se ele e aceito, recusado (com o motivo do contrato da CRA) ou
    aceito com aviso de titulo vivo igual.
    """
    partes = separar(conteudo)
    if not partes:
        raise RemessaError("O arquivo está vazio.")
    lotes = [_conferir_lote(con, parte) for parte in partes]
    apresentantes = sorted({x["apresentante_codigo"] for x in lotes})
    return {
        "lotes": lotes,
        "quantidade_de_lotes": len(lotes),
        "apresentantes": apresentantes,
        "quantidade": sum(x["quantidade"] for x in lotes),
        "aceitos": sum(x["aceitos"] for x in lotes),
        "recusados": sum(x["recusados"] for x in lotes),
        "avisados": sum(x["avisados"] for x in lotes),
        "soma_centavos": sum(x["soma_centavos"] for x in lotes),
        "achados": [a for x in lotes for a in x["achados"]],
        "ja_entrou": [x["ja_entrou"] for x in lotes if x["ja_entrou"]],
    }


def conferir_xml(con: sqlite3.Connection, bruto: str | bytes,
                 ambiente: str) -> dict:
    """Conferencia de remessa XML da CRA. NAO GRAVA NADA.

    Cada lote traz `origem_xml_*` calculados do XML original, nao da projecao
    Latin-1. A duplicidade autoritativa e `origem_xml_chave`, nao `hash_arquivo`.
    """
    ambiente = _ambiente_cra(ambiente)
    previa = PCRAXML.ler(bruto)
    partes = separar(previa.conteudo_fixo)
    if len(partes) != len(previa.hashes_lotes):
        raise RemessaError(
            "A remessa XML não fecha: a quantidade de lotes projetados difere "
            "dos hashes calculados.")
    lotes = [
        _conferir_lote_xml(con, parte, ambiente, hash_lote)
        for parte, hash_lote in zip(partes, previa.hashes_lotes)
    ]
    for lote in lotes:
        lote["achados"] = [
            a for a in lote["achados"]
            if not (a.startswith("O rodapé declara ")
                    and " registro(s)" in a)
        ]
    apresentantes = sorted({x["apresentante_codigo"] for x in lotes})
    return {
        "lotes": lotes,
        "quantidade_de_lotes": len(lotes),
        "apresentantes": apresentantes,
        "quantidade": sum(x["quantidade"] for x in lotes),
        "aceitos": sum(x["aceitos"] for x in lotes),
        "recusados": sum(x["recusados"] for x in lotes),
        "avisados": sum(x["avisados"] for x in lotes),
        "soma_centavos": sum(x["soma_centavos"] for x in lotes),
        "achados": [a for x in lotes for a in x["achados"]],
        "ja_entrou": [x["ja_entrou"] for x in lotes if x["ja_entrou"]],
        "xml_sha256": previa.sha256,
        "nome_arquivo_xml": previa.nome_arquivo,
    }


def _conferir_lote_xml(con: sqlite3.Connection, conteudo: str | bytes,
                       ambiente: str, hash_lote: str) -> dict:
    """Um lote XML conferido, com identidade FEBRABAN do XML original."""
    lote = _conferir_lote(con, conteudo)
    chave = PCRAXML.chave_idempotencia(ambiente, hash_lote)
    ja = remessa_pela_chave_xml(con, chave)
    lote["origem_xml_ambiente"] = ambiente
    lote["origem_xml_hash_lote"] = hash_lote
    lote["origem_xml_chave"] = chave
    # A projecao TXT e igual entre ambientes; `hash_arquivo` segue a chave XML.
    lote["hash_arquivo"] = chave
    lote["ja_entrou"] = dict(ja) if ja else None
    return lote


def _conferir_lote(con: sqlite3.Connection, conteudo: str | bytes) -> dict:
    """Um lote conferido, do cabecalho ao rodape. NAO GRAVA NADA."""
    arquivo = PA.ler(conteudo)
    _exigir_remessa(arquivo)
    cab = _cabecalho(arquivo)
    if not cab["apresentante_codigo"]:
        raise RemessaError(
            "O cabeçalho da remessa não traz o código do apresentante, e sem "
            "ele o retorno não sabe para quem voltar.")

    assinatura = hash_remessa(conteudo)
    ja = remessa_pelo_hash(con, assinatura)

    linhas: list[dict] = []
    aceitos = recusados = avisados = 0
    for i, bruto in enumerate(arquivo.titulos, start=1):
        dados = PA.para_apontamento(bruto)
        # O apresentante do cabecalho vale para o lote inteiro; o do registro
        # e o mesmo em arquivo bem formado, e o do cabecalho e o que a CRA
        # usa para devolver.
        dados["apresentante_codigo"] = (dados.get("apresentante_codigo")
                                        or cab["apresentante_codigo"])
        dados["apresentante_nome"] = (dados.get("apresentante_nome")
                                      or cab["apresentante_nome"])
        faltas = CRA.conferir_titulo(dados)
        iguais = _titulos_vivos_iguais(con, dados)
        devedor = (dados.get("devedores") or [{}])[0]
        linha = {
            "sequencial": i,
            "numero_titulo": dados.get("numero_titulo"),
            "nosso_numero": dados.get("nosso_numero"),
            "especie": dados.get("especie"),
            "especie_nome": CRA.ESPECIES.get(str(dados.get("especie") or ""), ""),
            "saldo": dados.get("saldo"),
            "saldo_centavos": bruto.get("saldo_a_protestar"),
            "devedor": devedor.get("nome"),
            "devedor_documento": devedor.get("CNPJ") or devedor.get("CPF"),
            "cedente": (dados.get("cedente") or {}).get("nome"),
            "faltas": faltas,
            "aceito": not faltas,
            "iguais": iguais,
            "dados": dados,
        }
        linhas.append(linha)
        if faltas:
            recusados += 1
        else:
            aceitos += 1
        if iguais:
            avisados += 1

    return {
        **cab,
        "hash_arquivo": assinatura,
        "achados": list(arquivo.achados),
        "titulos": linhas,
        "quantidade": len(linhas),
        "aceitos": aceitos,
        "recusados": recusados,
        "avisados": avisados,
        "soma_centavos": sum(int(t.get("saldo_a_protestar") or 0)
                             for t in arquivo.titulos),
        "ja_entrou": dict(ja) if ja else None,
        "conteudo": normalizar(conteudo),
    }


# ------------------------------------------------------------- receber


def receber(con: sqlite3.Connection, conteudo: str | bytes, *, agora: str,
            data_extenso: str, sv: dict, nome_arquivo: str | None = None,
            apontar: bool = True, marca: str | None = None,
            confirmar: bool = True, usuario: str | None = None) -> dict:
    """Recebe o arquivo inteiro, lote a lote. ESCREVE.

    NENHUM LOTE ENTRA SE UM DELES JA ENTROU. O arquivo se recebe inteiro ou
    nao se recebe: receber metade deixaria o balcao sem saber o que ficou de
    fora, e o resto so se descobriria pelo titulo que nunca voltou. Quando
    isso acontece a mensagem diz QUAL lote e de quando, para a conversa com a
    Central comecar do lugar certo.
    """
    visto = conferir(con, conteudo)
    return _receber_visto(
        con, visto, agora=agora, data_extenso=data_extenso, sv=sv,
        nome_arquivo=nome_arquivo, apontar=apontar, marca=marca,
        confirmar=confirmar, usuario=usuario)


def receber_xml(con: sqlite3.Connection, bruto: str | bytes, *, ambiente: str,
                agora: str, data_extenso: str, sv: dict,
                nome_arquivo: str | None = None, apontar: bool = True,
                marca: str | None = None, confirmar: bool = True,
                usuario: str | None = None) -> dict:
    """Recebe remessa XML da CRA, lote a lote, na mesma transacao dos titulos."""
    visto = conferir_xml(con, bruto, ambiente)
    if not nome_arquivo and visto.get("nome_arquivo_xml"):
        nome_arquivo = visto["nome_arquivo_xml"]
    return _receber_visto(
        con, visto, agora=agora, data_extenso=data_extenso, sv=sv,
        nome_arquivo=nome_arquivo, apontar=apontar, marca=marca,
        confirmar=confirmar, usuario=usuario, duplicidade_por="origem_xml_chave")


def _receber_visto(con: sqlite3.Connection, visto: dict, *, agora: str,
                   data_extenso: str, sv: dict, nome_arquivo: str | None,
                   apontar: bool, marca: str | None, confirmar: bool,
                   usuario: str | None,
                   duplicidade_por: str = "hash_arquivo") -> dict:
    if visto["ja_entrou"]:
        ja = visto["ja_entrou"][0]
        quantos = len(visto["ja_entrou"])
        parte = ("" if visto["quantidade_de_lotes"] == 1 else
                 f" ({quantos} de {visto['quantidade_de_lotes']} lotes deste "
                 f"arquivo já entraram)")
        if duplicidade_por == "origem_xml_chave":
            motivo = ("é o mesmo lote XML deste ambiente CRA — a chave de "
                      "idempotência bate.")
        else:
            motivo = ("é o mesmo arquivo, caractere por caractere.")
        raise RemessaError(
            f"Esta remessa já entrou em {str(ja['recebida_em'])[:16]}, do "
            f"apresentante {ja['apresentante_codigo']}, com {ja['recebidos']} "
            f"título(s) recebido(s){parte} — {motivo} Subir de novo apontaria "
            f"tudo outra vez, e apontamento não se desfaz. Se a Central mandou "
            f"um lote corrigido, ele vem com conteúdo diferente.")

    chave_dup = duplicidade_por
    vistos: dict[str, int] = {}
    for i, lote in enumerate(visto["lotes"], start=1):
        assinatura = lote.get(chave_dup) or lote["hash_arquivo"]
        anterior = vistos.get(assinatura)
        if anterior:
            raise RemessaError(
                f"Os lotes {anterior} e {i} deste arquivo são idênticos — "
                f"o mesmo apresentante ({lote['apresentante_codigo']}), os "
                f"mesmos títulos. Recebê-los seria apontar tudo duas vezes. "
                f"Confira o arquivo que baixou.")
        vistos[assinatura] = i

    recebidos = []
    for lote in visto["lotes"]:
        recebidos.append(_receber_lote(
            con, lote, agora=agora, data_extenso=data_extenso, sv=sv,
            nome_arquivo=nome_arquivo, apontar=apontar, marca=marca,
            confirmar=confirmar, usuario=usuario))
    return {
        **visto,
        "lotes": recebidos,
        "remessas": [x["remessa_id"] for x in recebidos],
        "recebidos": sum(x["recebidos"] for x in recebidos),
        "apontados": sum(x["apontados"] for x in recebidos),
        "confirmacoes": [x["confirmacao_id"] for x in recebidos
                         if x["confirmacao_id"]],
    }


def _receber_lote(con: sqlite3.Connection, visto: dict, *, agora: str,
                  data_extenso: str, sv: dict, nome_arquivo: str | None,
                  apontar: bool, marca: str | None, confirmar: bool,
                  usuario: str | None) -> dict:
    """Um lote: grava, cadastra, aponta e confirma. ESCREVE.

    A ORDEM E A DO BALCAO, e nao a comoda:

    1. **O lote entra primeiro**, e e ele que da a chave de origem de cada
       titulo (`CRA:<remessa_id>:<sequencial>`). Sem o lote gravado antes, a
       chave nao existe e a carga deixa de ser repetivel.
    2. **Cadastra e aponta titulo a titulo**, pulando os que o contrato recusa.
    3. **A confirmacao sai por ultimo**, com o que entrou — porque so depois
       de gravar se sabe o que entrou de verdade.

    `apontar=False` deixa os titulos em RECEBIDO, para o caso de o lote
    chegar e o apontamento ficar para depois. O padrao e apontar: o roteiro do
    oficial poe o aviso de intimacao no mesmo movimento do recebimento, e nao
    se intima titulo que nao foi apontado.
    """
    cur = con.execute(
        """INSERT INTO pt_remessas(tipo, apresentante_codigo, apresentante_nome,
               dia, numero_da_remessa, nome_arquivo, conteudo, hash_arquivo,
               titulos, recebidos, recusados, apontados, recusas_json,
               achados_json, recebida_em, recebida_por,
               origem_xml_ambiente, origem_xml_hash_lote, origem_xml_chave)
           VALUES (?,?,?,?,?,?,?,?,?,0,?,0,?,?,?,?,?,?,?)""",
        (visto["tipo"], visto["apresentante_codigo"], visto["apresentante_nome"],
         visto["dia"], visto["numero_da_remessa"], nome_arquivo,
         visto["conteudo"], visto["hash_arquivo"], visto["quantidade"],
         visto["recusados"],
         json.dumps([{"sequencial": t["sequencial"],
                      "numero_titulo": t["numero_titulo"],
                      "devedor": t["devedor"], "faltas": t["faltas"]}
                     for t in visto["titulos"] if t["faltas"]],
                    ensure_ascii=False),
         json.dumps(visto["achados"], ensure_ascii=False), agora, usuario,
         visto.get("origem_xml_ambiente"), visto.get("origem_xml_hash_lote"),
         visto.get("origem_xml_chave")))
    remessa_id = int(cur.lastrowid)

    entraram: list[dict] = []
    apontados = 0
    for linha in visto["titulos"]:
        if not linha["aceito"]:
            continue
        titulo_id = PT.cadastrar_titulo(
            con, linha["dados"], origem="CRA",
            origem_chave=f"CRA:{remessa_id}:{linha['sequencial']}",
            usuario=usuario, agora=agora)
        con.execute("UPDATE pt_titulos SET remessa_id=? WHERE id=?",
                    (remessa_id, titulo_id))
        lugar = None
        if apontar:
            lugar = PT.lancar_apontamento(
                con, titulo_id, sv=sv, agora=agora,
                data_extenso=data_extenso, usuario=usuario, origem="CRA")
            apontados += 1
        entraram.append({**linha, "titulo_id": titulo_id, "lugar": lugar})

    confirmacao_id = None
    confirmacao = None
    if confirmar and entraram:
        confirmacao = _confirmar(
            con, remessa_id=remessa_id, visto=visto, entraram=entraram,
            agora=agora, marca=marca, usuario=usuario)
        confirmacao_id = confirmacao["retorno_id"]

    con.execute(
        """UPDATE pt_remessas SET recebidos=?, apontados=?, confirmacao_id=?
            WHERE id=?""",
        (len(entraram), apontados, confirmacao_id, remessa_id))
    return {
        **visto,
        "remessa_id": remessa_id,
        "recebidos": len(entraram),
        "apontados": apontados,
        "entraram": entraram,
        "confirmacao_id": confirmacao_id,
        "confirmacao": confirmacao,
    }



def _confirmar(con: sqlite3.Connection, *, remessa_id: int, visto: dict,
               entraram: list[dict], agora: str, marca: str | None,
               usuario: str | None) -> dict:
    """Monta a confirmacao do recebimento e guarda. ESCREVE.

    ELA CONFIRMA O QUE ENTROU, e nao o que veio. Medido em 138 pares
    remessa-confirmacao um para um dos arquivos reais desta casa: 130 trazem
    exatamente os titulos da remessa, 8 trazem menos, e NENHUMA traz titulo
    que nao veio na remessa. Confirmar um titulo que a casa recusou seria
    dizer a Central que ele foi recebido, e depois nao ter o que devolver.

    Ela mora em `pt_retornos`, com tipo SDTBFOCRT: e arquivo que SAI, e o
    lugar do que sai ja existe. Duas tabelas para arquivo de saida seriam duas
    versoes do mesmo rodape — e foi justamente o rodape que ja enganou uma
    medicao inteira.
    """
    import protesto_retorno as PRE

    # A CONFIRMAÇÃO É O LOTE DA REMESSA DEVOLVIDO, COM O PROTOCOLO DENTRO — e
    # não um arquivo remontado do banco. Correção de 13/10/2026, medida em três
    # frentes que concordam:
    #   - o E-Ofício (C9010510, C1LV0610, CTAB1109 contra as remessas deles):
    #     cabeçalho e rodapé são os da remessa, com BFO/SDT/TPR virando
    #     SDT/BFO/CRT; nos títulos entram t31 «01», t32 o protocolo, t34 a data
    #     dele e zeros onde a remessa tinha branco;
    #   - o exemplo oficial da P21 (EXEMPLO_CONFIRMAÇÃO.xml), na mesma forma;
    #   - a CRA de homologação, que ACEITOU (código 0000) a `C2371609.263`
    #     montada assim, e recusou a remontada do banco.
    # A remontagem antiga punha a data de hoje no cabeçalho, deixava h09–h15 em
    # branco, zerava a quantidade do rodapé e a data do protocolo (t34).
    #
    # CONFIRMA O QUE ENTROU: título recusado sai do arquivo, e os sequenciais
    # (t52 e o t08 do rodapé) se renumeram. As contagens do cabeçalho (h09–h12)
    # e do rodapé (t05, t06) ficam as da remessa — o que a Central espera quando
    # ela mesma manda menos do que confirma não está medido: A CONFERIR na
    # primeira confirmação parcial.
    larg = PCRAXML.LARGURAS["tr"]
    inicio = [sum(larg[:k]) for k in range(len(larg))]

    def campo(linha: str, k: int, valor: str) -> str:
        a, n = inicio[k - 1], larg[k - 1]
        return linha[:a] + str(valor)[:n].ljust(n) + linha[a + n:]

    def zeros_se_branco(linha: str, k: int) -> str:
        a, n = inicio[k - 1], larg[k - 1]
        return linha if linha[a:a + n].strip() else campo(linha, k, "0" * n)

    protocolo_do = {}
    for x in entraram:
        r = con.execute("SELECT protocolo FROM pt_titulos WHERE id=?",
                        (int(x["titulo_id"]),)).fetchone()
        protocolo_do[int(x["sequencial"])] = str((r[0] if r else "") or "").strip()

    # O título do arquivo casa com o da conferência PELA ORDEM: o k-ésimo
    # registro «1» do lote é `visto["titulos"][k]`, e é o `sequencial` DELE
    # (e não os quatro últimos dígitos da linha) que `entraram` carrega.
    ordem = [int(t["sequencial"]) for t in visto["titulos"]]
    saida, sequencial, k = [], 1, 0
    for linha in [x for x in str(visto["conteudo"]).replace("\r", "").split("\n")
                  if x.strip()]:
        if linha[:1] == "0":
            saida.append(linha[:52] + "SDTBFOCRT" + linha[61:])
            continue
        if linha[:1] == "1":
            chave = ordem[k] if k < len(ordem) else None
            k += 1
            if chave not in protocolo_do:
                continue
            prot = protocolo_do[chave]
            data_prot = (f"{prot[4:6]}{prot[2:4]}20{prot[0:2]}"
                         if len(prot) >= 6 and prot[:6].isdigit()
                         else str(agora)[8:10] + str(agora)[5:7] + str(agora)[:4])
            linha = campo(linha, 31, "01")
            linha = campo(linha, 32, prot)
            linha = campo(linha, 33, "")
            linha = campo(linha, 34, data_prot if prot else "0" * 8)
            linha = campo(linha, 35, "0" * 10)
            linha = campo(linha, 37, "0" * 8)
            for k in (43, 44, 45):
                linha = zeros_se_branco(linha, k)
            linha = campo(linha, 50, "0" * 10)
        sequencial += 1
        saida.append(linha[:596] + f"{sequencial:04d}")
    texto = "\r\n".join(saida) + "\r\n"
    titulos = [x for x in saida if x[:1] == "1"]
    nome = PRE.nome_do_arquivo(TIPO_DA_CONFIRMACAO, visto["apresentante_codigo"],
                               visto["dia"] or str(agora)[:10], con=con)
    cur = con.execute(
        """INSERT INTO pt_retornos(tipo, par_id, apresentante_codigo,
               apresentante_nome, dia, numero_da_remessa, marca, titulos,
               soma_centavos, nome_arquivo, conteudo, hash_arquivo, gerado_em,
               gerado_por)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (TIPO_DA_CONFIRMACAO, None, visto["apresentante_codigo"],
         visto["apresentante_nome"], str(agora)[:10],
         _inteiro(visto["numero_da_remessa"]),
         # a letra da 566 é do RETORNO e não existe na confirmação
         None,
         len(titulos),
         sum(_inteiro(t[inicio[17]:inicio[17] + larg[17]], 0) for t in titulos),
         nome, texto, PRE.hash_retorno(texto), agora, usuario))
    return {"retorno_id": int(cur.lastrowid), "nome_arquivo": nome,
            "titulos": len(titulos), "conteudo": texto,
            "remessa_id": remessa_id}


def _inteiro(valor: Any, padrao: int = 1) -> int:
    try:
        return int(str(valor).strip())
    except (TypeError, ValueError):
        return padrao


# `_para_registro` (o título relido do banco no vocabulário de 600 posições) foi
# APAGADO em 13/10/2026: ele existia porque «copiar o registro de entrada
# esconderia o que a gravação tivesse mudado». O argumento era bom e a medição o
# desmentiu — a Central quer o lote dela de volta (é o que o E-Ofício fazia e o
# que ela aceitou), e a remontagem perdia campos que o banco não guarda (t16,
# t36, h13…). O que a casa decidiu sobre o título vai no bloco do protocolo.


# --------------------------------------------------------------- consultas


def remessa(con: sqlite3.Connection, remessa_id: int) -> sqlite3.Row | None:
    """A remessa recebida, com o arquivo inteiro. So LE."""
    return con.execute("SELECT * FROM pt_remessas WHERE id=?",
                       (int(remessa_id),)).fetchone()


def listar(con: sqlite3.Connection, limite: int = 60) -> list[dict]:
    """As remessas recebidas, da mais nova para a mais velha. So LE."""
    return [dict(r) for r in con.execute(
        """SELECT r.id, r.tipo, r.apresentante_codigo, r.apresentante_nome,
                  r.dia, r.numero_da_remessa, r.nome_arquivo, r.titulos,
                  r.recebidos, r.recusados, r.apontados, r.confirmacao_id,
                  r.hash_arquivo, r.recebida_em, r.recebida_por,
                  c.nome_arquivo confirmacao_nome
             FROM pt_remessas r
             LEFT JOIN pt_retornos c ON c.id = r.confirmacao_id
            ORDER BY r.id DESC LIMIT ?""", (int(limite),))]


def titulos_da_remessa(con: sqlite3.Connection, remessa_id: int) -> list[dict]:
    """Que titulos entraram naquela remessa. So LE."""
    return [dict(r) for r in con.execute(
        """SELECT t.id, t.numero_titulo, t.nosso_numero, t.especie,
                  t.saldo_centavos, t.situacao, t.protocolo,
                  d.nome devedor_nome
             FROM pt_titulos t
             LEFT JOIN pt_devedores d ON d.titulo_id = t.id
            WHERE t.remessa_id = ? ORDER BY t.id""", (int(remessa_id),))]


def recusas(linha: sqlite3.Row | dict) -> list[dict]:
    """Os titulos que a remessa trouxe e o contrato recusou. So LE.

    Guardados no proprio lote, e nao so mostrados na hora: quando o
    apresentante ligar perguntando por que aquele titulo nao voltou, e esta a
    resposta.
    """
    bruto = (linha["recusas_json"] if not isinstance(linha, dict)
             else linha.get("recusas_json"))
    try:
        return json.loads(bruto) if bruto else []
    except (TypeError, ValueError):
        return []
