"""As custas dos títulos à CRA — a operação `CustasTitulo`. 18/11/2026.

Ordem do oficial: «implementar e fazer o sistema usar essa ferramenta» — o
manual da P21, *Cartórios — Webservice — Estrutura de arquivos — Emolumentos
dos títulos* (atualizado em 29/04/2026). É por ela que o apresentante (o
banco) fica sabendo, pela CRA, quanto custa RETIRAR o título apontado e
CANCELAR o protesto lavrado — sem ligar para a casa.

O CONTRATO, MEDIDO NO MANUAL E NO EXEMPLO OFICIAL DA P21 (repositório
público `p21sistemas/manual-cra-21`, `EXEMPLO_CUSTAS_TITULO.zip`):

- operação `CustasTitulo`; `userArq` é o NOME `E000DDMM.AAS` (E, três zeros
  constantes, dia, mês, ponto, ano em dois dígitos e a sequência do dia, de 1
  a 9); `userDados` é o XML, declarado ISO-8859-1 e com conteúdo ASCII;
- raiz `<custas_titulo><apresentantes><apresentante>` com `<codigo>` e
  `<titulos><titulo>`: `protocolo`, `documento_devedor`, `data_protocolo`
  (DD/MM/AAAA), `numero_titulo`, `nosso_numero`, `valor` (ponto, duas casas)
  e `<emolumentos><emolumento>` com `tipo` (1 retirada, 2 cancelamento),
  `vigencia` (DD/MM/AAAA; vazia é «indefinida») e `total`;
- o exemplo oficial manda o tipo 1 com `vigencia` e `total` VAZIOS ao lado do
  tipo 2: é assim que a custa de retirada sai quando o título é protestado;
- a resposta é `<mensagem><codigo>…</codigo><descricao>…</descricao>`: 2291
  «custas do título atualizadas com sucesso», 2196 «título não encontrado»,
  2292 «campos inválidos ou não informados».

DE ONDE SAI CADA NÚMERO — nada aqui inventa tabela:

- RETIRADA (tipo 1), título APONTADO ou INTIMADO: a MESMA custa que o retorno
  já informa à CRA na ocorrência «3» (`protesto_retorno._custa_da_retirada`):
  a constante e a faixa 17.4 da tabela do dia, com
  `protesto_retorno.FOLHAS_DA_RETIRADA_NO_RETORNO` folhas. Dois números para a
  mesma retirada fariam a CRA mostrar ao banco um e o retorno dizer outro.
- CANCELAMENTO (tipo 2), título PROTESTADO: o `cancelamento` de
  `protesto_cenprot.precos_do_titulo`, o mesmo do arquivo de emolumentos da
  CENPROT. A Central nacional e a estadual mostram o mesmo preço.
- VIGÊNCIA: o último dia da tabela de emolumentos do dia (`cx_vigencias.fim`),
  quando a casa o sabe; sem ele vai vazia, que o manual lê como indefinida.

SÓ VAI O QUE MUDOU. `pt_cra_custas_informadas` guarda, por título e tipo, o
último valor que a CRA aceitou (2291); a rodada seguinte manda só o título
novo, o valor que mudou (tabela nova) e a retirada a apagar do título que foi
protestado. Mandar de novo não faz mal — a operação ATUALIZA —, e por isso
ela não está em `cra21_api.OPERACOES_QUE_ESCREVEM`: a falha de rede se repete.

TÍTULO SEM O QUE O CONTRATO PEDE NÃO VAI, e fica dito por quê: sem
apresentante, protocolo, CPF/CNPJ do devedor, data do protocolo, valor, ou sem
faixa na tabela. Zero num campo de dinheiro é afirmação («não custa nada»), e
o devedor viria ao balcão com ela.

A REDE CORRE FORA DE TRANSAÇÃO, como em `protesto_cra_envio`: ler (curta) →
transmitir (sem transação) → gravar o resultado (curta).
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import date, datetime
from typing import Any, Callable
from xml.sax.saxutils import escape, unescape

import centrais_cred as CRED
import cra21_api as CRA
from bd_nativo import banco

OPERACAO = "CustasTitulo"

TIPO_RETIRADA = "1"
TIPO_CANCELAMENTO = "2"
NOME_DO_TIPO = {TIPO_RETIRADA: "retirada", TIPO_CANCELAMENTO: "cancelamento"}

#: Quem tem retirada a informar: o título que ainda pode sair sem protesto.
SITUACOES_DA_RETIRADA = ("APONTADO", "INTIMADO")
#: Quem tem cancelamento a informar: o protesto lavrado e de pé.
SITUACAO_DO_CANCELAMENTO = "PROTESTADO"
#: Só os títulos que a CRA mandou: os da CENPROT e os do balcão a CRA não tem
#: (ela responderia 2196 a cada um).
ORIGEM = "CRA"

# As respostas do manual.
CODIGO_ATUALIZADO = "2291"
CODIGO_NAO_ENCONTRADO = "2196"
CODIGO_CAMPOS_INVALIDOS = "2292"
CODIGOS_DO_MANUAL: dict[str, str] = {
    CODIGO_ATUALIZADO: "Custas do título atualizadas com sucesso.",
    CODIGO_NAO_ENCONTRADO: "Título não encontrado.",
    CODIGO_CAMPOS_INVALIDOS: "Campos inválidos ou não informados.",
}

#: O nome que o manual pede: `E000DDMM.AAS`.
NOME_DO_ARQUIVO = re.compile(r"^E000\d{4}\.\d{3}$")
#: A sequência do dia vai de 1 a 9 (manual).
SEQUENCIA_MAXIMA = 9

#: O que se guarda da resposta da Central, e o que vai à tela.
CORTE_DA_RESPOSTA = 4000
CORTE_DO_MOTIVO = 500

#: A rotina na central de automação.
CODIGO_DA_ROTINA = "PROTESTO_CRA_CUSTAS"
QUEM_ENVIA_PELA_ROTINA = "automação (custas dos títulos à CRA)"
AGENTE = "automação — custas dos títulos à CRA"


class CustasCraError(CRA.CraError):
    """O envio das custas não pôde nem começar, com a frase para o balcão."""


# ------------------------------------------------------------------ formas


def nome_do_arquivo(dia: date, sequencia: int) -> str:
    """`E000DDMM.AAS` — o nome do manual. Só calcula."""
    seq = int(sequencia)
    if not 1 <= seq <= SEQUENCIA_MAXIMA:
        raise CustasCraError(
            f"A CRA aceita no máximo {SEQUENCIA_MAXIMA} arquivos de custas por "
            f"dia (a sequência do nome vai de 1 a 9), e este seria o {seq}º. "
            f"Envie amanhã — o que não foi hoje vai na próxima rodada.")
    return f"E000{dia:%d%m}.{dia:%y}{seq}"


def _ascii(valor: Any) -> str:
    """O texto sem acento e numa linha só — o manual pede conteúdo ASCII."""
    texto = unicodedata.normalize("NFKD", str(valor if valor is not None else ""))
    texto = texto.encode("ascii", "ignore").decode("ascii")
    return " ".join(texto.split())


def _digitos(valor: Any) -> str:
    return "".join(c for c in str(valor or "") if c.isdigit())


def _data_br(valor: Any) -> str:
    """`AAAA-MM-DD…` → `DD/MM/AAAA`; vazio no que não for data. Só calcula."""
    texto = str(valor or "").strip()[:10]
    try:
        return datetime.strptime(texto, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return ""


def data_do_protocolo(data_apontamento: Any, protocolo: Any) -> str:
    """A data do protocolo, em DD/MM/AAAA. Só calcula.

    PRIMEIRO A DO APONTAMENTO, que é a data da protocolização nesta casa (a
    mesma que a certidão e o instrumento leem — `protesto_certidao`). Sem o
    ato (título do acervo), a do próprio protocolo, que desde 2024 é AAMMDD +
    sequencial do dia — é como `protesto_cra_envio.montar_complemento` a monta,
    e a CRA a aceitou. Protocolo de outra forma não vira data inventada.
    """
    pela_data = _data_br(data_apontamento)
    if pela_data:
        return pela_data
    p = _digitos(protocolo)
    if len(p) >= 6:
        try:
            return date(2000 + int(p[0:2]), int(p[2:4]), int(p[4:6])).strftime("%d/%m/%Y")
        except ValueError:
            return ""
    return ""


def _reais(centavos: int) -> str:
    """`96.54` — ponto decimal e duas casas, como no exemplo do manual."""
    c = int(centavos)
    return f"{c // 100}.{c % 100:02d}"


# ------------------------------------------------------------------ a tabela


def tabela_do_dia(con: Any, dia: str) -> dict:
    """O que se precisa da tabela de emolumentos para o dia, lido UMA vez. Só LÊ.

    `precos_do_titulo` relê a tabela a cada título; para mil títulos isso são
    milhares de consultas por abertura de tela. Aqui se lê uma vez, e
    `precos(tabela, valor)` refaz a MESMA conta — há teste que exige as duas
    baterem no centavo.
    """
    import custas
    import protesto_cenprot as CENP
    import protesto_retorno as PRE
    try:
        vig = custas.vigencia_do_dia(con, dia)
    except custas.CustasError as erro:
        return {"erro": str(erro)}
    codigo = int(vig["codigo"])
    base = CENP.constantes(con, codigo)
    folha = CENP._preco_do_item(con, CENP.ITEM_POR_FOLHA, codigo)
    menos = None
    if folha is not None:
        menos = (CENP.FOLHAS_ARQUIVADAS - PRE.FOLHAS_DA_RETIRADA_NO_RETORNO) * int(folha)
    return {
        "erro": None,
        "vigencia": codigo,
        # Só a data que a casa SABE: a vigência de recurso («corrente», sem
        # início nem fim) vai vazia, que o manual lê como indefinida.
        "fim": _data_br(vig.get("fim")) if vig.get("exata") else "",
        "base_retirada": base["retirada"],
        "base_cancelamento": base["cancelamento"],
        "faixas_retirada": CENP._faixas(con, CENP.FAIXA_DA_RETIRADA, codigo),
        "faixas_cancelamento": CENP._faixas(con, CENP.FAIXA_DO_CANCELAMENTO, codigo),
        "folhas_a_menos": menos,
    }


def precos(tabela: dict, valor_centavos: int) -> dict:
    """`{"retirada", "cancelamento"}` em centavos, ou `None`. Só calcula.

    A conta de `protesto_cenprot.precos_do_titulo`, e a retirada com as
    folhas do retorno (`protesto_retorno._custa_da_retirada`).
    """
    if tabela.get("erro"):
        return {"retirada": None, "cancelamento": None}
    valor = int(valor_centavos)

    def na_faixa(base, faixas):
        if base is None:
            return None
        for de, ate, total in faixas:
            if de <= valor <= ate:
                return base + total
        return None

    retirada = na_faixa(tabela["base_retirada"], tabela["faixas_retirada"])
    if retirada is not None:
        retirada = (None if tabela["folhas_a_menos"] is None
                    else retirada - tabela["folhas_a_menos"])
    return {"retirada": retirada,
            "cancelamento": na_faixa(tabela["base_cancelamento"],
                                     tabela["faixas_cancelamento"])}


# ------------------------------------------------------------------ o que vai


def _candidatos(con: Any) -> list[dict]:
    situacoes = SITUACOES_DA_RETIRADA + (SITUACAO_DO_CANCELAMENTO,)
    marcas = ", ".join(["%s"] * len(situacoes))
    return banco(con).ler(
        f"""SELECT t.id, t.situacao, t.apresentante_codigo, t.protocolo,
                   t.numero_titulo, t.nosso_numero, t.valor_centavos,
                   (SELECT d.documento_numero FROM pt_devedores d
                     WHERE d.titulo_id = t.id ORDER BY d.id LIMIT 1) AS documento,
                   (SELECT MIN(a.data_ato) FROM pt_atos a
                     WHERE a.titulo_id = t.id AND a.tipo = 'APONTAMENTO'
                       AND COALESCE(a.cancelado, 0) = 0) AS data_apontamento
              FROM pt_titulos t
             WHERE t.origem = %s AND t.situacao IN ({marcas})
             ORDER BY t.apresentante_codigo, t.protocolo, t.id""",
        (ORIGEM, *situacoes))


def _informadas(con: Any) -> dict[tuple[int, str], dict]:
    return {(int(r["titulo_id"]), str(r["tipo"])): r for r in banco(con).ler(
        "SELECT titulo_id, tipo, total_centavos, vigencia FROM pt_cra_custas_informadas")}


def _o_que_falta(t: dict, data_prot: str) -> str | None:
    if not str(t["apresentante_codigo"] or "").strip():
        return "sem o código do apresentante"
    if not _digitos(t["protocolo"]):
        return "sem protocolo"
    if not _digitos(t["documento"]):
        return "sem CPF/CNPJ do devedor"
    if not data_prot:
        return "sem a data do protocolo (nem o apontamento, nem protocolo AAMMDD)"
    if int(t["valor_centavos"] or 0) <= 0:
        return "sem valor — é dele que sai a faixa da tabela"
    return None


def pendentes(con: Any, *, hoje: str) -> dict:
    """O que a próxima rodada mandaria à CRA. SÓ LÊ.

    Devolve `{"itens", "fora", "vigencia", "fim", "erro", "em_dia"}`: `itens`
    são os títulos com ao menos um emolumento novo ou mudado; `fora`, os que
    não vão, com o motivo; `em_dia`, quantos a CRA já tem certos.
    """
    tabela = tabela_do_dia(con, hoje)
    if tabela.get("erro"):
        return {"itens": [], "fora": [], "vigencia": None, "fim": "",
                "erro": tabela["erro"], "em_dia": 0}
    ja = _informadas(con)
    itens, fora, em_dia = [], [], 0
    for t in _candidatos(con):
        tid = int(t["id"])
        data_prot = data_do_protocolo(t["data_apontamento"], t["protocolo"])
        quem = {"titulo_id": tid, "protocolo": str(t["protocolo"] or "").strip(),
                "numero_titulo": t["numero_titulo"], "situacao": t["situacao"]}
        falta = _o_que_falta(t, data_prot)
        if falta:
            fora.append({**quem, "motivo": falta})
            continue
        p = precos(tabela, int(t["valor_centavos"]))
        desejado: dict[str, tuple[int | None, str]] = {}
        if t["situacao"] == SITUACAO_DO_CANCELAMENTO:
            tipo, total = TIPO_CANCELAMENTO, p["cancelamento"]
            # A RETIRADA QUE A CRA TEM DE ANTES DO PROTESTO SAI — vazia, como
            # no exemplo oficial. Só se ela foi informada: apagar o que nunca
            # se mandou é ruído.
            antes = ja.get((tid, TIPO_RETIRADA))
            if antes is not None and antes["total_centavos"] is not None:
                desejado[TIPO_RETIRADA] = (None, "")
        else:
            tipo, total = TIPO_RETIRADA, p["retirada"]
        if total is None:
            fora.append({**quem, "motivo": (
                f"o valor R$ {int(t['valor_centavos']) / 100:.2f} não cai em "
                f"nenhuma faixa da {NOME_DO_TIPO[tipo]} na tabela "
                f"{tabela['vigencia']}")})
            continue
        desejado[tipo] = (int(total), tabela["fim"])
        mudou = []
        for tp, (tot, vig) in sorted(desejado.items()):
            antes = ja.get((tid, tp))
            if (antes is not None and antes["total_centavos"] == tot
                    and str(antes["vigencia"] or "") == vig):
                continue
            mudou.append({"tipo": tp, "total_centavos": tot, "vigencia": vig})
        if not mudou:
            em_dia += 1
            continue
        itens.append({
            **quem,
            "apresentante_codigo": str(t["apresentante_codigo"]).strip(),
            "documento": _digitos(t["documento"]),
            "data_protocolo": data_prot,
            "nosso_numero": t["nosso_numero"],
            "valor_centavos": int(t["valor_centavos"]),
            "emolumentos": mudou,
        })
    return {"itens": itens, "fora": fora, "vigencia": tabela["vigencia"],
            "fim": tabela["fim"], "erro": None, "em_dia": em_dia}


def montar_xml(itens: list[dict]) -> str:
    """O `userDados`: o XML do exemplo oficial. Só calcula.

    Um `<apresentante>` por código, na ordem em que aparecem; os campos na
    ordem do exemplo. Tudo em ASCII e escapado.
    """
    if not itens:
        raise CustasCraError("Não há custas a informar à CRA.")

    def el(tag: str, valor: Any, recuo: int) -> str:
        return f"{' ' * recuo}<{tag}>{escape(_ascii(valor))}</{tag}>\n"

    grupos: dict[str, list[dict]] = {}
    for item in itens:
        grupos.setdefault(item["apresentante_codigo"], []).append(item)
    partes = ['<?xml version="1.0" encoding="ISO-8859-1"?>\n',
              "<custas_titulo>\n", "  <apresentantes>\n"]
    for codigo, titulos in grupos.items():
        partes += ["    <apresentante>\n", el("codigo", codigo, 6), "      <titulos>\n"]
        for t in titulos:
            partes += ["        <titulo>\n",
                       el("protocolo", t["protocolo"], 10),
                       el("documento_devedor", t["documento"], 10),
                       el("data_protocolo", t["data_protocolo"], 10),
                       el("numero_titulo", t["numero_titulo"], 10),
                       el("nosso_numero", t["nosso_numero"], 10),
                       el("valor", _reais(t["valor_centavos"]), 10),
                       "          <emolumentos>\n"]
            for e in t["emolumentos"]:
                total = ("" if e["total_centavos"] is None
                         else _reais(e["total_centavos"]))
                partes += ["            <emolumento>\n",
                           el("tipo", e["tipo"], 14),
                           el("vigencia", e["vigencia"], 14),
                           el("total", total, 14),
                           "            </emolumento>\n"]
            partes += ["          </emolumentos>\n", "        </titulo>\n"]
        partes += ["      </titulos>\n", "    </apresentante>\n"]
    partes += ["  </apresentantes>\n", "</custas_titulo>\n"]
    return "".join(partes)


# ------------------------------------------------------------------ a resposta

_MENSAGEM = re.compile(r"<mensagem\b[^>]*>(.*?)</mensagem>", re.S | re.I)
_CAMPO = {nome: re.compile(rf"<{nome}\b[^>]*>(.*?)</{nome}>", re.S | re.I)
          for nome in ("codigo", "descricao", "protocolo")}


def _campo(trecho: str, nome: str) -> str:
    achado = _CAMPO[nome].search(trecho)
    return unescape(achado.group(1)).strip() if achado else ""


def interpretar_resposta(texto: str) -> dict:
    """Lê o `<mensagem>` da CRA. Só calcula.

    Todas 2291 → aceito. A mensagem com o protocolo diz de qual título é, e
    então se aceita o que voltou 2291 e se recusa o resto; sem protocolo e com
    algum código fora de 2291, nada se dá por informado (reenviar não faz mal:
    a operação atualiza). Resposta sem `<mensagem>` nenhum, ou recusa geral
    (`<erro>`, `<relatorio>`), vira `CraRecusou`.
    """
    bruto = str(texto or "").strip()
    o_que = "enviar as custas dos títulos"
    if not bruto:
        raise CRA.CraRecusou(f"A CRA respondeu ao {o_que} sem conteúdo.", bruto=bruto)
    mensagens = [{"codigo": _campo(m, "codigo"), "descricao": _campo(m, "descricao"),
                  "protocolo": _digitos(_campo(m, "protocolo"))}
                 for m in _MENSAGEM.findall(bruto)]
    mensagens = [m for m in mensagens if m["codigo"]]
    if not mensagens:
        recusa = CRA.recusa_no_return(bruto)
        if recusa:
            codigo = _campo(bruto, "codigo") or None
            raise CRA.CraRecusou(f"A CRA recusou ao {o_que}: {recusa}",
                                 bruto=bruto, codigo=codigo, motivo=recusa)
        raise CRA.CraRecusou(
            f"A CRA respondeu ao {o_que} fora do esperado: {bruto[:240]}", bruto=bruto)
    aceitos = [m for m in mensagens if m["codigo"] == CODIGO_ATUALIZADO]
    recusados = [m for m in mensagens if m["codigo"] != CODIGO_ATUALIZADO]

    def frase(m: dict) -> str:
        qual = f"protocolo {m['protocolo']}: " if m["protocolo"] else ""
        return (f"{qual}{m['codigo']} "
                f"{m['descricao'] or CODIGOS_DO_MANUAL.get(m['codigo'], '')}").strip()

    por_titulo = all(m["protocolo"] for m in mensagens)
    if recusados and not (por_titulo and aceitos):
        motivo = "; ".join(frase(m) for m in recusados[:10])
        raise CRA.CraRecusou(f"A CRA recusou ao {o_que}: {motivo}", bruto=bruto,
                             codigo=recusados[0]["codigo"], motivo=motivo)
    return {"ok": not recusados,
            "codigo": CODIGO_ATUALIZADO,
            # `None` = vale para o arquivo inteiro; senão, só estes protocolos.
            "protocolos_aceitos": ({m["protocolo"] for m in aceitos}
                                   if por_titulo else None),
            "recusas": [frase(m) for m in recusados],
            "resposta": bruto[:CORTE_DA_RESPOSTA]}


# ------------------------------------------------------------------ o envio


def _agora() -> str:
    return datetime.now().replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%S")


def _reservar_nome(con: Any, dia: date) -> tuple[int | None, str, int]:
    """O nome do arquivo de hoje. SÓ LÊ.

    O ARQUIVO QUE NÃO CHEGOU À CRA REUSA O NOME: a sequência vai só até 9 por
    dia, e uma queda de rede não pode gastar uma. O que a CRA respondeu (com
    qualquer código) já tem nome dela, e o próximo leva a sequência seguinte.
    Devolve `(id do envio a reaproveitar ou None, nome, sequência)`.
    """
    bd = banco(con)
    ultimo = bd.um(
        """SELECT id, sequencia, nome_arquivo, codigo, enviado_em
             FROM pt_cra_custas_envios WHERE dia = %s
            ORDER BY sequencia DESC LIMIT 1""", (dia.isoformat(),))
    if ultimo and not ultimo["codigo"] and not ultimo["enviado_em"]:
        return int(ultimo["id"]), str(ultimo["nome_arquivo"]), int(ultimo["sequencia"])
    seq = int(ultimo["sequencia"]) + 1 if ultimo else 1
    return None, nome_do_arquivo(dia, seq), seq


def enviar(transacao: Callable[[], Any], *, hoje: date | None = None,
           usuario: str | None = None, pasta=None) -> dict:
    """Manda à CRA as custas novas ou mudadas. ESCREVE (no banco e na Central).

    `transacao` abre a transação (`db.transaction`), e não é uma conexão: a
    rede corre entre duas transações curtas. Só produção (14/10/2026).
    Devolve `{"enviado", "nome_arquivo", "titulos", "informados", "recusas",
    "fora", "motivo", "envio_id"}`. Falha de rede ou recusa da Central sobe
    como `CraError`/`CraRecusou` DEPOIS de gravada no envio.
    """
    dia = hoje or date.today()
    qual = CRED.ambiente_de_uso(CRED.CRA, CRED.PRODUCAO)
    if not CRED.tem(CRED.CRA, qual, pasta):
        raise CustasCraError(
            "A credencial de PRODUÇÃO da CRA não está informada — informe-a em "
            "Administrativo → Configurações → Centrais.")
    with transacao() as con:                                 # 1. ler — curta
        p = pendentes(con, hoje=dia.isoformat())
        if p["erro"]:
            raise CustasCraError(p["erro"])
        if not p["itens"]:
            return {"enviado": False, "nome_arquivo": None, "titulos": 0,
                    "informados": 0, "recusas": [], "fora": p["fora"],
                    "em_dia": p["em_dia"], "envio_id": None,
                    "motivo": (f"Nada mudou: a CRA já tem as custas de "
                               f"{p['em_dia']} título(s).")}
        reaproveitar, nome, seq = _reservar_nome(con, dia)
        xml = montar_xml(p["itens"])
        guardado = json.dumps(
            [{"titulo_id": i["titulo_id"], "protocolo": i["protocolo"],
              "emolumentos": i["emolumentos"]} for i in p["itens"]],
            ensure_ascii=False)
        bd = banco(con)
        if reaproveitar:
            bd.escrever(
                """UPDATE pt_cra_custas_envios SET conteudo=%s, titulos=%s,
                       itens_json=%s, gerado_em=%s, gerado_por=%s, erro=NULL
                    WHERE id=%s""",
                (xml, len(p["itens"]), guardado, _agora(), usuario, reaproveitar))
            envio_id = reaproveitar
        else:
            envio_id = int(bd.escrever(
                """INSERT INTO pt_cra_custas_envios(nome_arquivo, dia, sequencia,
                       conteudo, titulos, itens_json, gerado_em, gerado_por, ambiente)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (nome, dia.isoformat(), seq, xml, len(p["itens"]), guardado,
                 _agora(), usuario, qual))[0]["id"])

    lido = erro = None                                       # 2. a rede — sem transação
    try:
        lido = interpretar_resposta(
            CRA.enviar_custas_titulo(nome, xml, qual, pasta=pasta))
    except (CRA.CraError, CRED.CredencialError) as e:
        erro = e

    with transacao() as con:                                 # 3. gravar — curta
        bd = banco(con)
        if erro is not None:
            codigo = getattr(erro, "codigo", None)
            bruto = str(getattr(erro, "bruto", "") or "")
            bd.escrever(
                """UPDATE pt_cra_custas_envios SET codigo=%s, resposta=%s, erro=%s,
                       ambiente=%s WHERE id=%s""",
                (codigo, bruto[:CORTE_DA_RESPOSTA] or None,
                 str(erro)[:CORTE_DO_MOTIVO], qual, envio_id))
        else:
            agora = _agora()
            aceitos = lido["protocolos_aceitos"]
            informados = 0
            for item in p["itens"]:
                if aceitos is not None and _digitos(item["protocolo"]) not in aceitos:
                    continue
                informados += 1
                for e in item["emolumentos"]:
                    bd.escrever(
                        """INSERT INTO pt_cra_custas_informadas(titulo_id, tipo,
                               total_centavos, vigencia, envio_id, informado_em)
                           VALUES (%s,%s,%s,%s,%s,%s)
                           ON CONFLICT (titulo_id, tipo) DO UPDATE SET
                               total_centavos = EXCLUDED.total_centavos,
                               vigencia = EXCLUDED.vigencia,
                               envio_id = EXCLUDED.envio_id,
                               informado_em = EXCLUDED.informado_em""",
                        (item["titulo_id"], e["tipo"], e["total_centavos"],
                         e["vigencia"], envio_id, agora))
            bd.escrever(
                """UPDATE pt_cra_custas_envios SET enviado_em=%s, codigo=%s,
                       resposta=%s, erro=%s, ambiente=%s WHERE id=%s""",
                (agora, lido["codigo"], lido["resposta"],
                 ("; ".join(lido["recusas"])[:CORTE_DO_MOTIVO] or None),
                 qual, envio_id))
    if erro is not None:
        raise erro
    return {"enviado": True, "nome_arquivo": nome, "titulos": len(p["itens"]),
            "informados": informados, "recusas": lido["recusas"],
            "fora": p["fora"], "em_dia": p["em_dia"], "envio_id": envio_id,
            "motivo": (f"{nome}: a CRA atualizou as custas de {informados} de "
                       f"{len(p['itens'])} título(s)"
                       + (f"; recusou {len(lido['recusas'])}" if lido["recusas"] else "")
                       + ".")}


def ultimos_envios(con: Any, limite: int = 10) -> list[dict]:
    """Os últimos arquivos de custas, para a tela. SÓ LÊ."""
    bd = banco(con)
    if not bd.tem_tabela("pt_cra_custas_envios"):
        return []
    return bd.ler(
        """SELECT id, nome_arquivo, dia, titulos, gerado_em, gerado_por,
                  enviado_em, codigo, erro
             FROM pt_cra_custas_envios ORDER BY id DESC LIMIT %s""", (int(limite),))


def envio(con: Any, envio_id: int) -> dict | None:
    """Um arquivo de custas, com o conteúdo. SÓ LÊ."""
    return banco(con).um("SELECT * FROM pt_cra_custas_envios WHERE id=%s",
                         (int(envio_id),))


# ------------------------------------------------------------------ a rotina

CATALOGO = (
    {"codigo": CODIGO_DA_ROTINA,
     "nome": "CRA — custas dos títulos (retirada e cancelamento)",
     "setor": "PROTESTO", "robo_oficial": "PROTESTO",
     "funcao": "protesto_cra_custas.rodar",
     "timeout_s": 300,
     "agenda": {"dias": [0, 1, 2, 3, 4], "horarios": ["12:00", "17:30"]},
     "descricao": (
         "Informa à CRA (operação CustasTitulo) quanto custa retirar cada título "
         "apontado e cancelar cada protesto — só os novos e os que mudaram. Com "
         "«pode agir», envia; desligado, conta o que iria. Os valores são os da "
         "tabela do dia, os mesmos do retorno e do arquivo da CENPROT.")},
)


def _auditar(contexto, r: dict) -> None:
    log = getattr(contexto.db, "log", None)
    if log is None or not r.get("envio_id"):
        return
    import identidade_do_robo as IDR
    log(None, "automação", "PROTESTO_CRA_CUSTAS_ENVIADAS", "pt_cra_custas_envios",
        int(r["envio_id"]),
        {"nome_arquivo": r.get("nome_arquivo"), "titulos": r.get("titulos"),
         "informados": r.get("informados"), "recusas": len(r.get("recusas") or []),
         "pela_rotina": CODIGO_DA_ROTINA},
        agente=AGENTE, a_mando_de=IDR.PELO_RESPONSAVEL)


def rodar(contexto) -> dict:
    """O processo PROTESTO_CRA_CUSTAS. Envia (com `pode_agir`) ou conta."""
    pode_agir = bool((getattr(contexto, "processo", None) or {}).get("pode_agir"))
    pasta = getattr(contexto, "pasta_dados", None)
    hoje = contexto.agora.date()
    if not CRED.tem(CRED.CRA, CRED.PRODUCAO, pasta):
        return {"situacao": "AVISO", "erro": "credencial não cadastrada",
                "relato": ("A credencial da CRA não está cadastrada — as custas "
                           "não têm como ir. Cadastre-a em Administrativo → "
                           "Configurações → Centrais."),
                "achados": [], "acoes": []}
    if not pode_agir:
        try:
            with contexto.db.connect() as con:
                p = pendentes(con, hoje=hoje.isoformat())
        except Exception as erro:  # noqa: BLE001 — «não mediu» não é «zero»
            return {"situacao": "ERRO", "erro": f"{type(erro).__name__}: {erro}"[:500],
                    "relato": f"Não deu para medir as custas a informar: {erro}"[:600],
                    "achados": [], "acoes": []}
        if p["erro"]:
            return {"situacao": "ERRO", "erro": p["erro"][:500],
                    "relato": f"As custas não se calculam: {p['erro']}"[:600],
                    "achados": [], "acoes": []}
        achados = [{"a_informar": len(p["itens"]), "fora": len(p["fora"]),
                    "em_dia": p["em_dia"]}]
        if p["itens"]:
            return {"situacao": "AVISO", "achados": achados, "acoes": [],
                    "relato": (f"{len(p['itens'])} título(s) com custas a informar "
                               f"à CRA ({len(p['fora'])} sem dado para ir). Ligue "
                               f"«pode agir» para a rotina enviar, ou envie em "
                               f"Protesto → CRA pela API.")}
        return {"situacao": "OK", "achados": achados, "acoes": [],
                "relato": f"A CRA tem as custas em dia ({p['em_dia']} título(s))."}
    try:
        r = enviar(contexto.db.transaction, hoje=hoje,
                   usuario=QUEM_ENVIA_PELA_ROTINA, pasta=pasta)
    except Exception as erro:  # noqa: BLE001 — a falha vira ERRO com o motivo
        return {"situacao": "ERRO", "erro": f"{type(erro).__name__}: {erro}"[:500],
                "relato": (f"As custas NÃO foram à CRA: {erro}. Veja em "
                           f"Protesto → CRA pela API.")[:600],
                "achados": [], "acoes": []}
    _auditar(contexto, r)
    achados = [{"titulos": r["titulos"], "informados": r["informados"],
                "recusas": r["recusas"][:20], "fora": len(r["fora"]),
                "em_dia": r["em_dia"]}]
    acoes = ([{"acao": "enviou as custas à CRA", "arquivo": r["nome_arquivo"],
               "titulos": r["titulos"], "informados": r["informados"]}]
             if r["enviado"] else [])
    situacao = "AVISO" if (r["recusas"] or r["fora"]) else "OK"
    relato = r["motivo"]
    if r["fora"]:
        relato += f" {len(r['fora'])} título(s) ficaram de fora por falta de dado."
    return {"situacao": situacao, "relato": relato[:600],
            "achados": achados, "acoes": acoes}
