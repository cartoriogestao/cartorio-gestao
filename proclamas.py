"""
O PROCLAMA QUE VAI À CENTRAL — o domínio entre a habilitação e o e-Proclamas.

    «vamos seguir o cronograma recomendado» — o oficial, 03/09/2026, e o
    primeiro item dele é este.

**ISTO FECHA O BURACO QUE O PRÓPRIO SISTEMA DECLARAVA DESDE 28/08/2026**, em
`habilitacao.registrar_publicacao`: *«O ENVIO À CENTRAL AINDA NÃO É DAQUI.
Enquanto a integração não existir, o escrevente publica no e-Proclamas e anota
o protocolo aqui.»* Era verdade, e a API existe desde 10/04/2025.

O QUE ESTE MÓDULO É, E O QUE ELE NÃO É
    Ele **monta** o proclama na forma do contrato, a partir do que a casa já
    lavrou, e **manda**. `onrcpn_api` é o transporte e não sabe o que é uma
    habilitação; este módulo sabe, e não sabe abrir conexão.

    **ELE NÃO LAVRA ATO, pela sexta vez** — depois do usucapião, das fraudes,
    do CNIB, da CENPROT e da ONRTDPJ. Quem publica o edital é
    `habilitacao.publicar_edital`; quem lança o proclama no Livro D é
    `rc_assento`. Este comunica à Central o que **já** foi decidido e lavrado
    aqui. Há teste que varre os nomes públicos.

A CORRENTE, E CADA ELO EXISTE POR UM MOTIVO
    1. **O edital publicado aqui** — dele saem a data (`data_proclamas`) e o
       prazo. Sem ele não há o que comunicar.
    2. **O assento de proclamas no Livro D** — dele sai a **matrícula de 32
       dígitos**, que é como a Central identifica o proclama e como o recibo
       se busca depois (`GET /api/proclama/recibo/:matricula`).
    3. **O envio**, que grava o que foi mandado e o que voltou.

    **A ORDEM NÃO SE INVERTE**, e a recusa diz em que elo se parou — porque o
    conserto de cada um é num lugar diferente da casa.

DE ONDE SAEM OS DOIS CÔNJUGES, E POR QUE NÃO DO ASSENTO
    Da **habilitação**, e não do assento do Livro D. Medido em 03/09/2026:
    `rc_assento.PAPEIS_DA_ESPECIE` **não tem entrada para `PROCLAMAS`** — um
    assento de proclamas não aceita pessoa nenhuma; `_conferir_papel` recusaria
    `NUBENTE1` dizendo que aquela espécie não tem esse papel.

    **E isso não é defeito a consertar aqui: é o desenho certo.** Os dois
    nubentes já moram em `hc_habilitacoes`, em colunas próprias, e é de lá que
    o edital os descreve. Repetí-los no assento seriam **dois lugares
    guardando o mesmo fato**, que divergem no primeiro conserto — o defeito que
    `inacabados` existe para não cometer.

O QUE A CENTRAL PEDE E A CASA NÃO TEM — declarado, e não preenchido de palpite
    **O ENDEREÇO.** A Central quer seis campos (`cep`, `logradouro`, `numero`,
    `complemento`, `bairro`, `ibge_municipio`); a habilitação guarda **um campo
    de texto livre**, `nubente1_endereco`.

    Partir esse texto por vírgulas poria «Centro» em `logradouro` numa boa
    parte das vezes, e ninguém veria — a Central aceita e o edital sai com o
    endereço trocado de casa. **Campo vazio não afirma nada; campo errado
    afirma**, e é a regra que este projeto já aplicou na filiação do segundo
    cônjuge.

    Então o endereço **não vai**, e `conferir()` diz isso com todas as letras.
    Quando o oficial quiser que vá, o conserto é na tela da habilitação — que
    passa a perguntar os seis campos —, e não aqui.

    **A NATURALIDADE VAI QUANDO SE RESOLVE.** `hc_habilitacoes.naturalidade` é
    texto («Cidade Exemplo/MA»), e a Central quer os **7 dígitos do IBGE**. A
    busca é a de `ibge_geracao.lugar`, com a regra de ambiguidade que
    ela já tem: **sem UF, só vale se o nome for único no Brasil** — há dezenas
    de «Bom Jesus», e escolher o primeiro poria o casal no estado errado.
    Não resolveu, vai vazio, e a conferência conta.

O MESMO PROCLAMA NÃO SE PUBLICA DUAS VEZES
    A publicação **custa** e sai no mundo. A recusa diz quando foi a primeira e
    qual número de lote ela trouxe — quem precisa republicar tem o fato na mão
    para decidir, e o `livro_eletronico` continua podendo ir sozinho depois.

HTTP 200 NÃO QUER DIZER QUE O PROCLAMA SUBIU — e esta foi a correção do dia
    Eu medi o contrato imprimindo só a `description` de cada resposta, li «OK»,
    e **escrevi que o corpo da resposta não era declarado**. Cheguei a montar
    uma função que procurava um campo `protocolo` por vários nomes prováveis,
    «porque o contrato não diz o nome».

    **Ele diz.** A resposta 200 do `enviar` traz
    `proclamas: {batchId, success: [...], error: [...]}` — **duas listas, por
    matrícula** —, e o lote pode voltar aceito pela metade. Com a primeira
    versão, um proclama recusado seria gravado como publicado e o balcão diria
    ao casal que o edital saiu.

    **E não há campo `protocolo` nenhum**: o que a Central devolve é o
    `batchId`, o número do LOTE. A casa guarda esse número e a tela diz que é
    isso — chamá-lo de protocolo seria batizar o que não se mediu.

    A lição é a mesma que este projeto já tinha, na forma nova: **ausência não
    se conclui de uma leitura que só olhou metade do documento.**
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any

import centrais_cred as CRED
import habilitacao as HAB
import ibge_geracao as IBGER
import onrcpn_api as API
import rc_matricula as MATR

# O QUE A CENTRAL CHAMA DE TIPO DE CASAMENTO, a partir do que a casa guarda.
#
#   `hc_habilitacoes.tipo` é `CIVIL`, `RELIGIOSO` ou `CONVERSAO`; o contrato
#   quer minúsculas e sem acento. A quarta palavra dele — `afixacao` — **não
#   tem correspondente aqui**, e não se inventa um: esta casa publica na
#   Central, e não afixa.
TIPO_DA_HABILITACAO: dict[str, str] = {
    "CIVIL": "civil",
    "RELIGIOSO": "religioso",
    "CONVERSAO": "conversao",
}

# A FILIAÇÃO VAI COM O SEXO DO GENITOR, porque o contrato tem o campo.
#
#   A habilitação guarda `nubente1_pai` e `nubente1_mae` — as duas colunas
#   **dizem o sexo pelo nome da coluna**, e é isso que se manda. Não é
#   dedução: é o que o campo declara ser.
SEXO_DO_GENITOR: dict[str, str] = {"pai": "masculino", "mae": "feminino"}


class ProclamaError(ValueError):
    """Erro de regra, com a mensagem pronta para o balcão."""


def _txt(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _linha(con: sqlite3.Connection, habilitacao_id: int) -> sqlite3.Row:
    h = con.execute("SELECT * FROM hc_habilitacoes WHERE id=?",
                    (int(habilitacao_id),)).fetchone()
    if h is None:
        raise ProclamaError(f"Habilitação {habilitacao_id} não existe.")
    return h


def ambiente() -> str:
    """O ambiente da ON-RCPN. **Um só, e é o de homologação.**

    Ver `centrais_cred.AMBIENTES_DA_CENTRAL`: os dois contratos publicados são
    de homologação, e o endereço de produção não está publicado em lugar
    nenhum que esta casa tenha lido.
    """
    return CRED.ambientes_de(CRED.ONRCPN)[0]


# ------------------------------------------------------------- a matrícula


def matricula_do_proclama(con: sqlite3.Connection, h: sqlite3.Row, *,
                          cns: Any) -> dict:
    """A matrícula de 32 dígitos do assento no Livro D. Só LÊ.

    Devolve `{matricula, de_onde, procedencia, motivo}`. **Nunca inventa**: sem
    assento ligado, devolve vazio com o motivo escrito.

    **A GRAVADA MANDA SOBRE A CALCULADA**, como na ficha da matrícula do RI: se
    o escrevente informou uma, é ela que vai — divergência entre as duas é
    assunto do oficial, e não de um `UPDATE`.
    """
    assento_id = h["proclamas_assento_id"]
    if not assento_id:
        return {"matricula": "", "de_onde": "", "procedencia": "",
                "motivo": ("Esta habilitação ainda não tem o registro de "
                           "proclamas lavrado no Livro D — e é dele que sai a "
                           "matrícula de 32 dígitos com que a Central "
                           "identifica o proclama. Lavre em Registro Civil → "
                           "Novo assento, espécie «Proclamas», e amarre-o aqui.")}
    a = con.execute("SELECT * FROM rc_assentos WHERE id=?",
                    (int(assento_id),)).fetchone()
    if a is None:
        return {"matricula": "", "de_onde": "", "procedencia": "",
                "motivo": (f"O assento {assento_id}, ligado a esta habilitação "
                           f"como registro de proclamas, não existe mais.")}
    # **`.keys()` NAO E REDUNDANTE AQUI, e o ruff pede a troca errada.**
    #   Num `sqlite3.Row`, `"matricula" in a` **itera os VALORES**, e nao
    #   as chaves: `"x" in linha` devolve `True` quando `x` e o conteudo de
    #   alguma coluna. Trocar por `in a` faria a leitura acertar por acaso
    #   e errar quando o dado mudasse — o defeito calado.
    gravada = _txt(a["matricula"] if "matricula" in a.keys() else "")  # noqa: SIM118
    if gravada:
        return {"matricula": gravada, "de_onde": "gravada no assento",
                "procedencia": _procedencia(gravada), "motivo": ""}
    try:
        composta = MATR.compor_do_assento(dict(a), cns=cns)
    except MATR.MatriculaError as erro:
        return {"matricula": "", "de_onde": "", "procedencia": "",
                "motivo": (f"Não deu para compor a matrícula do assento "
                           f"{assento_id}: {erro}")}
    return {"matricula": composta, "de_onde": "calculada do assento",
            "procedencia": _procedencia(composta), "motivo": ""}


def _procedencia(matricula: Any) -> str:
    """De onde veio o dígito do LIVRO daquela matrícula. Só lê.

    **A PROCEDÊNCIA SEGUE O NÚMERO, E NÃO O CAMINHO** — e isto foi correção do
    mesmo dia. A primeira versão só a mostrava quando a matrícula era
    *calculada aqui*, e devolvia vazio quando ela vinha **gravada no assento**.

    Só que `rc_assento.lavrar_assento` **compõe e grava a matrícula ao lavrar**
    — logo o caso normal é justamente o gravado, e a procedência nunca
    apareceria. Pior: ela some exatamente onde mais importa, porque o número
    gravado é o que já está no livro.

    Lendo o dígito **de dentro da matrícula**, a resposta é a mesma pelos dois
    caminhos — e continua certa para uma matrícula digitada à mão.
    """
    try:
        tipo = MATR.partes(matricula)["livro_tipo"]
    except MATR.MatriculaError:
        return ""
    return MATR.procedencia_do_livro(tipo)


# ---------------------------------------------------------------- o cônjuge


def _naturalidade(con: sqlite3.Connection, texto: Any) -> dict:
    """O município de naturalidade nos 7 dígitos do IBGE, ou vazio com motivo.

    Aceita «Cidade Exemplo/MA» e «Cidade Exemplo». A régua de ambiguidade é a de
    `ibge_geracao.lugar`, e não uma parecida.
    """
    bruto = _txt(texto)
    if not bruto:
        return {"codigo": "", "motivo": "a habilitação não diz a naturalidade"}
    cidade, uf = bruto, ""
    for marca in ("/", "-", "—"):
        if marca in bruto:
            cidade, _, uf = bruto.partition(marca)
            break
    achado = IBGER.lugar(con, cidade.strip(), uf.strip())
    if not achado.get("achou"):
        return {"codigo": "",
                "motivo": (f"«{bruto}» não bateu com nenhum município do IBGE"
                           + ("" if uf.strip() else
                              " — sem a UF, só vale se o nome for único no "
                              "Brasil"))}
    return {"codigo": achado.get("codigo_ibge") or "", "motivo": ""}


def _conjuge(con: sqlite3.Connection, h: sqlite3.Row, qual: int) -> dict:
    """Um nubente na forma do contrato, do que a habilitação guarda."""
    def col(nome: str) -> str:
        chave = f"nubente{qual}_{nome}"
        # `.keys()` pelo mesmo motivo de `matricula_do_proclama`: em
        # `sqlite3.Row`, `in` olha os valores.
        return _txt(h[chave] if chave in h.keys() else "")  # noqa: SIM118

    natural = _naturalidade(con, col("naturalidade"))
    filiacao = [{"nome_genitor": col(quem), "sexo_genitor": SEXO_DO_GENITOR[quem]}
                for quem in ("pai", "mae") if col(quem)]

    return {
        "cpf": col("documento"),
        "nome": col("nome"),
        "novo_nome": col("nome_pos"),
        "sexo": col("sexo"),
        "data_nascimento": col("nascimento"),
        "estado_civil": col("estado_civil"),
        "ocupacao": col("profissao"),
        # **ESTRANGEIRO NÃO SE DEDUZ DA FALTA DE MUNICÍPIO.** Não achar a
        # cidade no IBGE quer dizer que a busca não achou — e não que a pessoa
        # nasceu fora. Marcar `True` aqui mandaria à Central que o nubente é
        # estrangeiro toda vez que alguém escrevesse o nome da cidade com erro
        # de digitação.
        "naturalidade_estrangeiro": False,
        "ibge_municipio_naturalidade": natural["codigo"],
        "descricao_naturalidade_estrangeiro": "",
        "pais_nascimento": API.BRASIL_M49 if natural["codigo"] else "",
        "nacionalidade": API.BRASIL_M49 if natural["codigo"] else "",
        "domicilio_estrangeiro": False,
        # O ENDEREÇO NÃO VAI — ver o cabeçalho. Seis campos contra um campo de
        # texto livre; partir o texto poria o bairro na rua.
        "endereco_residencia": {},
        "descricao_domicilio_estrangeiro": "",
        "filiacao": filiacao,
    }


# ------------------------------------------------------------- a conferência


def conferir(con: sqlite3.Connection, habilitacao_id: int, *, cns: Any,
             publicacao: bool = True, livro_eletronico: bool = True,
             cpf_fatura: Any = None, nome_fatura: Any = None) -> dict:
    """O que iria, e o que impede. **NÃO GRAVA NADA E NÃO FALA COM NINGUÉM.**

    É a forma de conferir/receber da remessa da CRA, e pela mesma razão: o que
    sobe publica edital e é cobrado. Quem clica em «Enviar» já viu o que vai.
    """
    h = _linha(con, habilitacao_id)
    impedem: list[str] = []
    avisos: list[str] = []

    if not _txt(h["edital_em"]):
        impedem.append(
            "O edital de proclamas ainda não foi publicado aqui — e é dele "
            "que saem a data e o teor que vão para a Central.")

    mat = matricula_do_proclama(con, h, cns=cns)
    if not mat["matricula"]:
        impedem.append(mat["motivo"])

    tipo = TIPO_DA_HABILITACAO.get(_txt(h["tipo"]).upper(), "")
    if not tipo:
        impedem.append(
            f"A Central só conhece {', '.join(sorted(set(TIPO_DA_HABILITACAO.values())))} "
            f"como tipo de casamento, e esta habilitação está como "
            f"«{_txt(h['tipo']) or '(em branco)'}».")

    if not (publicacao or livro_eletronico):
        impedem.append(
            "Marque ao menos uma coisa a fazer: publicar no e-Proclamas, "
            "gerar o Livro D Eletrônico, ou as duas.")

    ja = publicacao_ja_feita(con, habilitacao_id)
    if publicacao and ja:
        impedem.append(
            f"Esta habilitação já foi publicada no e-Proclamas em "
            f"{ja['enviado_em'][:10]}"
            + (f", protocolo {ja['protocolo']}" if ja["protocolo"] else "")
            + ". Publicar de novo é uma segunda publicação, cobrada. Se for "
              "isso mesmo, desmarque a publicação e mande só o Livro D "
              "Eletrônico, ou trate com a Central.")

    proclama = montar(con, habilitacao_id, cns=cns, publicacao=publicacao,
                      livro_eletronico=livro_eletronico,
                      cpf_fatura=cpf_fatura, nome_fatura=nome_fatura,
                      matricula=mat["matricula"], conferindo=True)

    # O QUE FALTA E NÃO IMPEDE — a Central não declara campo obrigatório
    # nenhum, e inventar obrigação seria o erro do outro lado. Mas o balcão
    # precisa ver o que vai em branco ANTES de mandar.
    for numero in (1, 2):
        c = proclama[f"conjuge_{numero}"]
        de_quem = f"o {'primeiro' if numero == 1 else 'segundo'} cônjuge"
        if not c["cpf"]:
            avisos.append(f"{de_quem} vai sem CPF.")
        if not c["ibge_municipio_naturalidade"]:
            qual = _naturalidade(con, h[f"nubente{numero}_naturalidade"])
            avisos.append(f"a naturalidade {de_quem} vai em branco: "
                          f"{qual['motivo']}.")
        if not c["filiacao"]:
            avisos.append(f"{de_quem} vai sem filiação.")
    avisos.append(
        "O endereço dos nubentes NÃO vai: a Central pede seis campos (CEP, "
        "logradouro, número, complemento, bairro e município do IBGE) e a "
        "habilitação guarda um campo de texto só. Mandar o texto partido "
        "poria o bairro no lugar da rua.")

    return {"pronto": not impedem,
            "impedem": impedem,
            "avisos": avisos,
            "matricula": mat,
            "ambiente": ambiente(),
            "tem_credencial": API.tem_credencial(),
            "proclama": proclama}


# ------------------------------------------------------------- a montagem


def montar(con: sqlite3.Connection, habilitacao_id: int, *, cns: Any,
           publicacao: bool = True, livro_eletronico: bool = True,
           cpf_fatura: Any = None, nome_fatura: Any = None,
           matricula: Any = None, conferindo: bool = False) -> dict:
    """O proclama na forma do contrato. Só LÊ.

    `cpf_fatura` e `nome_fatura` são **de quem paga a publicação**, e vêm da
    tela. Quando não vierem, valem os do primeiro cônjuge — que é quem a
    habilitação tem à mão —, e a tela diz que é sugestão: quem paga é resposta
    de balcão, não dedução.

    Com `conferindo=True` as convenções que estouram viram campo vazio, para a
    tela poder MOSTRAR o proclama incompleto em vez de dar erro. **No envio de
    verdade elas estouram**, que é o que impede o dado torto de subir.
    """
    h = _linha(con, habilitacao_id)
    if matricula is None:
        matricula = matricula_do_proclama(con, h, cns=cns)["matricula"]

    c1 = _conjuge(con, h, 1)
    c2 = _conjuge(con, h, 2)
    proclama = {
        "matricula": _txt(matricula),
        "publicacao": bool(publicacao),
        "livro_eletronico": bool(livro_eletronico),
        "data_proclamas": _txt(h["edital_em"]),
        "tipo_casamento": TIPO_DA_HABILITACAO.get(_txt(h["tipo"]).upper(), ""),
        "cpf_fatura": _txt(cpf_fatura) or c1["cpf"],
        "nome_fatura": _txt(nome_fatura) or c1["nome"],
        "conjuge_1": c1,
        "conjuge_2": c2,
    }
    if not conferindo:
        return proclama
    # NA CONFERÊNCIA, MOSTRAR VALE MAIS QUE ESTOURAR. O transporte aplica as
    # convenções e recusa o que não cabe; aqui a recusa viraria uma tela em
    # branco justamente para quem foi conferir o que está torto.
    try:
        return API.conferir_proclama(proclama)
    except API.OnrcpnError:
        return proclama


# --------------------------------------------------------------- o histórico


def publicacao_ja_feita(con: sqlite3.Connection,
                        habilitacao_id: int) -> dict | None:
    """O envio de PUBLICAÇÃO que já deu certo, se houve. Só lê.

    Conta só o do **mesmo ambiente**: um envio de homologação não impede a
    publicação de verdade, e dizer que impede travaria o balcão por causa de
    um teste.
    """
    linha = con.execute(
        "SELECT * FROM hc_eproclamas WHERE habilitacao_id=? AND publicacao=1 "
        "AND ambiente=? AND protocolo IS NOT NULL "
        "ORDER BY id LIMIT 1",
        (int(habilitacao_id), ambiente())).fetchone()
    return dict(linha) if linha else None


def enviados_de(con: sqlite3.Connection, habilitacao_id: int) -> list[dict]:
    """Tudo o que já se mandou desta habilitação, na ordem. Só lê."""
    return [dict(r) for r in con.execute(
        "SELECT * FROM hc_eproclamas WHERE habilitacao_id=? ORDER BY id DESC",
        (int(habilitacao_id),)).fetchall()]


def pendentes(con: sqlite3.Connection) -> list[dict]:
    """As habilitações com edital publicado e sem publicação na Central.

    **O acervo não vira atraso, e aqui isso é de graça**: `hc_habilitacoes`
    nasceu neste sistema em 27/08/2026 e a carga do E-Ofício não a alimenta —
    o acervo não tinha tabela de habilitação nenhuma. Toda linha daqui foi
    lavrada por esta casa.
    """
    onde = ambiente()
    return [dict(r) for r in con.execute(
        "SELECT h.id, h.numero, h.ano, h.tipo, h.edital_em, "
        "       h.edital_prazo_ate, h.nubente1_nome, h.nubente2_nome, "
        "       h.eproclamas_protocolo, h.proclamas_assento_id "
        "  FROM hc_habilitacoes h "
        " WHERE h.edital_em IS NOT NULL AND h.edital_em <> '' "
        "   AND NOT EXISTS (SELECT 1 FROM hc_eproclamas e "
        "                    WHERE e.habilitacao_id = h.id "
        "                      AND e.publicacao = 1 AND e.ambiente = ? "
        "                      AND e.protocolo IS NOT NULL) "
        " ORDER BY h.edital_em, h.id", (onde,)).fetchall()]


# ------------------------------------------------------------------ o envio


def enviar(db, habilitacao_id: int, *, cns: Any, agora: str,
           publicacao: bool = True, livro_eletronico: bool = True,
           cpf_fatura: Any = None, nome_fatura: Any = None,
           usuario: str | None = None, pasta=None) -> dict:
    """Manda o proclama à Central e grava o que foi e o que voltou.

    **RECEBE `db`, E NÃO `con`** — a mesma assinatura de
    `ato_selado.obter_selo` e de `ajuda.consultar`, e pelo mesmo motivo: assim
    não há como chamá-la de dentro de uma transação sem reparar. Uma chamada
    de rede de sessenta segundos segurando o `BEGIN IMMEDIATE` poria todo
    outro balcão no `busy_timeout`.

    A ordem é: **conferir (lendo), mandar (fora de transação), gravar (curta)**.
    """
    # 1. CONFERIR. Numa conexão de leitura, e antes de falar com ninguém.
    with db.connect() as con:
        conferido = conferir(con, habilitacao_id, cns=cns,
                             publicacao=publicacao,
                             livro_eletronico=livro_eletronico,
                             cpf_fatura=cpf_fatura, nome_fatura=nome_fatura)
    if not conferido["pronto"]:
        raise ProclamaError(" ".join(conferido["impedem"]))

    # 2. MANDAR. Fora de qualquer transação, e é o transporte que aplica as
    #    convenções do contrato e recusa o que não cabe.
    resposta = API.enviar(cns, [conferido["proclama"]], pasta=pasta)

    # 3. LER O QUE VOLTOU, ANTES DE GRAVAR QUALQUER COISA.
    #
    #   **HTTP 200 NÃO QUER DIZER QUE O PROCLAMA SUBIU.** O contrato declara
    #   duas listas por matrícula — `success` e `error` —, e o lote pode voltar
    #   aceito pela metade. Gravar como publicado o que a Central recusou faria
    #   a casa dizer ao casal que o edital saiu quando ele não saiu.
    minha = conferido["matricula"]["matricula"]
    recusado = next((r for r in resposta.get("recusados") or []
                     if r.get("matricula") == minha), None)
    aceito = minha in (resposta.get("aceitos") or [])

    # 4. GRAVAR, com o teor congelado — **aceito ou recusado**.
    #
    #   O envio fica registrado nos dois casos: houve chamada, e ela pode ter
    #   sido cobrada. O que muda é o número do lote, que só entra quando a
    #   Central aceitou — sem isso, uma recusa contaria como publicação feita e
    #   a trava contra publicar duas vezes ficaria ligada sobre nada.
    corpo = json.dumps(resposta["corpo_enviado"], ensure_ascii=False,
                       sort_keys=True)
    assinatura = hashlib.sha256(corpo.encode("utf-8")).hexdigest()
    lote = _txt(resposta.get("lote")) if aceito else ""
    with db.transaction() as con:
        con.execute(
            "INSERT INTO hc_eproclamas(habilitacao_id, matricula, publicacao, "
            " livro_eletronico, ambiente, corpo_enviado, corpo_hash, "
            " resposta, protocolo, enviado_em, enviado_por) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (int(habilitacao_id), minha,
             1 if publicacao else 0, 1 if livro_eletronico else 0,
             ambiente(), corpo, assinatura,
             json.dumps(resposta["resposta"], ensure_ascii=False)[:4000],
             lote or None, str(agora), usuario))
        # **O NÚMERO DO LOTE ENTRA POR ONDE O PROTOCOLO JÁ ENTRAVA.**
        # `registrar_publicacao` é quem grava `eproclamas_protocolo` desde
        # 28/08, e continua sendo: dois caminhos escrevendo o mesmo fato
        # divergiriam no primeiro conserto, e o manual continua valendo para
        # quando a Central estiver fora do ar e o escrevente publicar pelo
        # portal.
        if lote and publicacao:
            HAB.registrar_publicacao(con, habilitacao_id, protocolo=lote,
                                     agora=agora, usuario=usuario)

    if recusado:
        raise ProclamaError(
            "A Central RECEBEU o envio e RECUSOU este proclama: "
            + (API.motivo_da_recusa(recusado) or "sem motivo informado")
            + ". O envio ficou registrado; conserte o que ela apontou e mande "
              "de novo.")
    if not aceito:
        # **NÃO SE AFIRMA O QUE NÃO SE ENTENDEU.** A resposta veio com 200 e
        # sem a forma que o contrato declara: dizer «publicado» aqui seria o
        # carimbo que mente, e dizer «recusado» seria acusar a Central do que
        # ela não fez. O que se sabe é que a chamada foi feita.
        raise ProclamaError(
            "A Central respondeu, e a resposta não trouxe esta matrícula nem "
            "entre as aceitas nem entre as recusadas — não dá para afirmar que "
            "o proclama foi publicado. O envio ficou registrado com a resposta "
            "inteira; confira no portal do e-Proclamas antes de mandar de novo.")

    return {"lote": lote, "ambiente": ambiente(), "hash": assinatura,
            "resposta": resposta["resposta"],
            "corpo_enviado": resposta["corpo_enviado"]}
