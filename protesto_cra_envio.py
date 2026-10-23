"""Envio de arquivos de saída à CRA21 — Confirmação e Retorno (SOAP).

MEDIDO NA HOMOLOGAÇÃO EM 11 E 13/10/2026 — e isto CORRIGE o que estava escrito
aqui desde 30/09, que dizia «medido» sobre um envio que nunca tinha sido feito:

- ``userArq`` é o **nome FEBRABAN** (``C2371609.263``): letra + apresentante +
  DDMM + ``.AA`` + sequência. O nome interno antigo (``SDTBFOCRT-237-…txt``) a
  CRA recusa (código 0002).
- ``userDados`` é o arquivo **em XML** (``protesto_cra_xml.escrever_xml``). O
  texto de 600 posições volta «10000 — 1.5 ARQUIVO XML CORROMPIDO»; o mesmo
  arquivo em XML voltou «0000 — 10 títulos».
- **O andamento vai pela ``TituloComplemento``**, num XML próprio
  (``<complementos>``), e não pela ``Retorno`` — por ela a CRA respondeu vazio e
  não o registrou. O caminho é o do manual da P21 que o oficial trouxe, e os 7
  títulos ensaiados voltaram «2322 — Andamento inserido».
  Ver DOCUMENTACAO/CRA_HOMOLOGACAO_TESTE_2026-10-13.md.

Quem monta é ``protesto_remessa`` / ``protesto_retorno``; este módulo só
converte para XML e transporta.

Produção só envia automaticamente se ``cra_auto_enviar_producao`` estiver ligado.

**DESDE 14/10/2026 O ENVIO É SÓ EM PRODUÇÃO** — ordem do oficial: «tire a
opção de funcionar na homologação, agora é tudo produção». Lote sem ambiente é
de produção; lote gravado como de homologação **não se envia** a lugar nenhum
(`centrais_cred.ambiente_de_uso` recusa com a frase), porque mandar à produção
a confirmação de um lote de teste seria apresentar à Central títulos que ela
não mandou. ``cra_auto_enviar_homolog`` continua gravado em ``settings`` e não
se lê mais por tela nenhuma.
"""
from __future__ import annotations

import re
from typing import Any, Callable

import centrais_cred as CRED
import cra21_api as CRA
import protesto_cra_xml as PCRAXML
import protesto_retorno as PRE
from bd_nativo import banco

# SDTBFOCRT → Confirmacao; retorno final → Retorno; ANDAMENTO → TituloComplemento.
#
# O ANDAMENTO NÃO É hd/tr/tl, e não vai pela `Retorno` — por ela a CRA respondeu
# vazio e não registrou nada (13/10/2026, manhã). O caminho está no manual da P21
# («Cartórios — Webservice — Andamento em XML», trazido pelo oficial no mesmo
# dia): operação `TituloComplemento`, raiz `<complementos>`, um `<titulo>` por
# protocolo com `<andamentos><andamento><codigo>AA</codigo><data>…`. Ensaiado na
# homologação: os 7 títulos do lote 237/000023 voltaram «2322 — Andamento
# inserido», SEM o bloco de emolumentos (que a tabela do manual diz obrigatório
# e a Central não exigiu — por isso não se manda custa que não foi calculada).
OPERACAO_POR_TIPO: dict[str, str] = {
    "SDTBFOCRT": "Confirmacao",
    "SDTBFORTP": "Retorno",
    "SDTBFOAND": "TituloComplemento",
}
TIPO_DO_ANDAMENTO = "SDTBFOAND"
#: O andamento que o sistema informa ao apontar — «AA, Apontado» (manual da P21).
CODIGO_DO_APONTADO = "AA"
#: Respostas por título que querem dizer «entrou» (manual da P21).
_COMPLEMENTO_OK = frozenset({"2322", "2318"})

#: O nome que a CRA aceita: letra, apresentante (3), DDMM, «.», AA e sequência.
NOME_FEBRABAN = re.compile(r"^[CRM][0-9A-Z]{3}\d{4}\.\d{3}$")

_CODIGO_RELATORIO = re.compile(r"<codigo>\s*(\d+)\s*</codigo>", re.IGNORECASE)
_CODIGOS_OK = frozenset({"0000", "0001"})
_OCORRENCIA = re.compile(r"<ocorrencia>(.*?)</ocorrencia>", re.IGNORECASE | re.DOTALL)
_DECLARACAO_XML = re.compile(r"^\s*<\?xml[^>]*\?>", re.IGNORECASE)

#: O que da recusa vai à TELA: o motivo da `<ocorrencia>` até este tamanho e um
#: trecho curto do começo da resposta. A resposta INTEIRA vai só para
#: `pt_retornos.cra_envio_erro`, até `CORTE_DO_ERRO` (LH08, revisão do LH07).
TRECHO_NA_TELA = 240
TRECHO_DA_RESPOSTA = 160
CORTE_DO_ERRO = 4000


class CraEnvioError(CRA.CraError):
    """Falha ao enviar arquivo à CRA, com frase para o balcão."""


def ambiente_da_remessa(lote: dict, *, padrao: str = CRED.PRODUCAO) -> str:
    """HOMOLOGACAO/PRODUCAO a partir do lote XML, ou padrão para TXT.

    O padrão é PRODUÇÃO desde 14/10/2026 (até 13/10, homologação). O lote que
    disser homologação é devolvido como tal — e o envio o recusa —, em vez de
    ser trocado por produção em silêncio.
    """
    bruto = str(lote.get("origem_xml_ambiente") or "").strip().upper()
    return bruto if bruto in CRED.AMBIENTES else padrao


def auto_envio_ligado(ambiente: str, ler_config: Callable[[str, str], str]) -> bool:
    """Se o envio automático pós-receber deve rodar neste ambiente."""
    qual = str(ambiente or "").strip().upper() or CRED.PRODUCAO
    if qual == CRED.PRODUCAO:
        return ler_config("cra_auto_enviar_producao", "0") == "1"
    return ler_config("cra_auto_enviar_homolog", "1") == "1"


def user_dados_do_arquivo(conteudo: str, tipo: str = "SDTBFOCRT") -> str:
    """O ``userDados`` medido: o arquivo inteiro, em XML (medido em 13/10/2026)."""
    if not str(conteudo or "").strip():
        raise CraEnvioError(
            "O arquivo está vazio — a CRA não aceita confirmação ou retorno "
            "sem conteúdo.")
    try:
        return PCRAXML.escrever_xml(conteudo, tipo)
    except PCRAXML.RemessaXmlError as erro:
        raise CraEnvioError(str(erro)) from erro


def _trecho(texto: str, limite: int = TRECHO_NA_TELA) -> str:
    """O texto numa linha só, cortado em `limite` com «…» quando passa. Só calcula."""
    liso = " ".join(str(texto or "").split())
    return liso if len(liso) <= limite else liso[:limite - 1].rstrip() + "…"


def interpretar_resposta_envio(texto: str, *, o_que: str) -> dict[str, Any]:
    """Lê ``<codigo>`` do retorno SOAP quando existir; senão aceita texto livre."""
    bruto = str(texto or "").strip()
    if not bruto:
        raise CRA.CraRecusou(
            f"A CRA respondeu ao {o_que} sem conteúdo — confira na Central "
            f"se o arquivo entrou antes de repetir.")
    achado = _CODIGO_RELATORIO.search(bruto)
    if achado:
        codigo = achado.group(1)
        if codigo in _CODIGOS_OK:
            return {"ok": True, "codigo": codigo, "resposta": bruto}
        explicacao = CRA.CODIGOS_MEDIDOS.get(codigo)
        if explicacao:
            raise CRA.CraRecusou(
                f"A CRA recusou ao {o_que} (código {codigo}): {explicacao}",
                bruto=bruto)
        # A explicação da CRA mora em <ocorrencia>, DEPOIS do cabeçalho do
        # relatório; os 240 primeiros caracteres eram só o cabeçalho, e o
        # código 2154 do retorno RTAB2110.261 (21/10/2026) ficou gravado sem
        # o motivo. Vai o motivo primeiro, e um trecho curto do começo da
        # resposta (o nome do arquivo que ela cita). O bruto INTEIRO ia junto
        # na frase — para a tela, o `flash` no cookie da sessão e a auditoria
        # (revisão do LH07); agora vai à parte, só para o campo de erro.
        ocorrencia = _OCORRENCIA.search(bruto)
        motivo = (_trecho(ocorrencia.group(1)) if ocorrencia
                  else "a resposta não traz <ocorrencia>")
        inicio = _trecho(_DECLARACAO_XML.sub("", bruto), TRECHO_DA_RESPOSTA)
        raise CRA.CraRecusou(
            f"A CRA recusou ao {o_que} (código {codigo}): {motivo}. "
            f"Início da resposta: {inicio}", bruto=bruto)
    upper = bruto.upper()
    if "INVÁLIDO" in upper or "INVALIDO" in upper or "CORROMPIDO" in upper:
        raise CRA.CraRecusou(f"A CRA recusou ao {o_que}: {bruto[:240]}",
                             bruto=bruto)
    return {"ok": True, "codigo": None, "resposta": bruto}


# O ENVIO TEM TRÊS FASES, E SÓ A DO MEIO FALA COM A REDE — correção de
# 13/10/2026. Até aqui a rota abria `db.transaction()` (BEGIN IMMEDIATE) e,
# dentro dela, chamava a CRA (prazo de 180 s por chamada): a casa inteira ficava
# no `busy_timeout` enquanto a Central respondia, que é exatamente o que a regra
# da casa proíbe. Agora: ler (transação curta) → transmitir (sem transação) →
# gravar o resultado (transação curta).


def montar_complemento(con: Any, andamento_id: int,
                       quando: str) -> str:
    """O andamento no XML da `TituloComplemento`. SÓ LÊ.

    Os títulos são os dos atos que o andamento levou (`pt_atos.retorno_id`).
    Datas `dd/mm/aaaa`, a do andamento `dd/mm/aaaa HH:MM:SS`, valores com ponto
    — é o que o exemplo do manual da P21 mostra, e o que a homologação aceitou.
    """
    from xml.sax.saxutils import escape

    # O andamento que sai EM PAR com um retorno fala de pagamento, protesto ou
    # desistência — e o código de cada um no `<complementos>` não foi medido.
    # Só o andamento do apontamento («AA») foi ensaiado; o outro não se inventa.
    bd = banco(con)
    if bd.um("SELECT 1 FROM pt_retornos WHERE par_id = %s",
             (int(andamento_id),)):
        raise CraEnvioError(
            f"O andamento #{andamento_id} acompanha um retorno, e o código de "
            f"andamento de pagamento/protesto/desistência não foi medido na CRA — "
            f"envie-o pelo portal da Central.")

    def el(tag: str, valor: Any) -> str:
        return f"<{tag}>{escape(str(valor if valor is not None else ''))}</{tag}>"

    linhas = bd.ler(
        """SELECT t.apresentante_codigo, t.protocolo, t.numero_titulo,
                  t.nosso_numero, t.valor_centavos, t.saldo_centavos,
                  (SELECT d.documento_numero FROM pt_devedores d
                    WHERE d.titulo_id = t.id ORDER BY d.id LIMIT 1) AS documento
             FROM pt_atos a JOIN pt_titulos t ON t.id = a.titulo_id
            WHERE a.retorno_id = %s ORDER BY a.id""", (int(andamento_id),))
    if not linhas:
        raise CraEnvioError(
            f"O andamento #{andamento_id} não tem título nenhum — gere-o de novo "
            f"a partir do apontamento.")
    q = str(quando or "")
    data_hora = f"{q[8:10]}/{q[5:7]}/{q[:4]} {q[11:19] or '00:00:00'}"
    titulos = []
    for r in linhas:
        prot = str(r["protocolo"] or "").strip()
        titulos.append(
            "<titulo>" + el("protocolo", prot)
            + el("documento_devedor", "".join(c for c in str(r["documento"] or "")
                                              if c.isdigit()))
            + el("data_protocolo", f"{prot[4:6]}/{prot[2:4]}/20{prot[0:2]}")
            + el("numero_titulo", r["numero_titulo"])
            + el("nosso_numero", r["nosso_numero"])
            + el("valor", f"{int(r['valor_centavos'] or 0) / 100:.2f}")
            + el("saldo", f"{int(r['saldo_centavos'] or 0) / 100:.2f}")
            + "<andamentos><andamento>" + el("codigo", CODIGO_DO_APONTADO)
            + el("data", data_hora) + "</andamento></andamentos></titulo>")
    return ('<?xml version="1.0" encoding="ISO-8859-1"?>'
            "<complementos><apresentantes><apresentante>"
            + el("codigo", linhas[0]["apresentante_codigo"]) + "<titulos>"
            + "".join(titulos) + "</titulos></apresentante></apresentantes></complementos>")


def interpretar_resposta_complemento(texto: str, *, o_que: str) -> dict[str, Any]:
    """A resposta da `TituloComplemento` vem POR TÍTULO, dentro de `<mensagens>`.
    Entra só se todos os títulos voltarem 2322/2318; recusa geral (`<relatorio>`)
    e título recusado viram `CraRecusou`, com o código e o protocolo."""
    bruto = str(texto or "").strip()
    if not bruto:
        raise CRA.CraRecusou(f"A CRA respondeu ao {o_que} sem conteúdo.")
    import xml.etree.ElementTree as ET
    try:
        raiz = ET.fromstring(bruto.encode("latin-1", errors="replace"))
    except ET.ParseError:
        raise CRA.CraRecusou(f"A CRA respondeu ao {o_que} fora do XML: {bruto[:240]}",
                             bruto=bruto)
    if raiz.tag == "relatorio":
        return interpretar_resposta_envio(bruto, o_que=o_que)
    recusas, aceitos = [], 0
    for titulo in raiz.iter("titulo"):
        for msg in titulo.iter("mensagens"):
            for item in msg:
                codigo = (item.findtext("codigo") or "").strip()
                if codigo in _COMPLEMENTO_OK:
                    aceitos += 1
                else:
                    recusas.append(f"{titulo.findtext('protocolo')}: {codigo} "
                                   f"{(item.findtext('descricao') or '').strip()}")
    if recusas or not aceitos:
        raise CRA.CraRecusou(
            f"A CRA recusou ao {o_que}: " + ("; ".join(recusas[:10])
                                             or "nenhum título confirmado"),
            bruto=bruto)
    return {"ok": True, "codigo": "2322", "resposta": bruto[:500]}


def _preparar(linha: Any, *, con: Any | None = None,
              forcar: bool = False) -> dict[str, Any]:
    """Confere o arquivo gravado e o deixa pronto para a rede. SÓ LÊ."""
    retorno_id = linha["id"]
    if linha["cra_enviado_em"] and not forcar:
        raise CraEnvioError(
            f"«{linha['nome_arquivo']}» já foi enviado à CRA em "
            f"{str(linha['cra_enviado_em'])[:16]}. Não repita sem conferir "
            f"na Central — envio duplicado pode registrar duas vezes.")
    tipo = str(linha["tipo"] or "").strip()
    operacao = OPERACAO_POR_TIPO.get(tipo)
    if not operacao:
        raise CraEnvioError(
            f"O tipo «{linha['tipo']}» não tem operação SOAP de envio medida.")
    if not NOME_FEBRABAN.match(str(linha["nome_arquivo"] or "")):
        raise CraEnvioError(
            f"«{linha['nome_arquivo']}» não está no nome que a CRA aceita "
            f"(como C2371609.263) — é um arquivo gerado antes de 13/10/2026. "
            f"Gere-o de novo; a CRA recusa nome fora do padrão (código 0002).")
    if tipo == TIPO_DO_ANDAMENTO:
        if con is None:
            raise CraEnvioError("O andamento se monta dos títulos — falta a conexão.")
        dados = montar_complemento(con, int(retorno_id), str(linha["gerado_em"] or ""))
    else:
        dados = user_dados_do_arquivo(linha["conteudo"], tipo)
    return {"retorno_id": int(retorno_id), "operacao": operacao,
            "nome_arquivo": linha["nome_arquivo"], "dados": dados}


def _transmitir(preparado: dict, qual: str, pasta=None) -> dict[str, Any]:
    """Fala com a CRA. NÃO TOCA NO BANCO — é chamada fora de transação."""
    o_que = (f"enviar o {'andamento' if preparado['operacao'] == 'TituloComplemento' else preparado['operacao'].lower()} "
             f"«{preparado['nome_arquivo']}»")
    if preparado["operacao"] == "TituloComplemento":
        bruto = CRA.chamar("TituloComplemento", qual, o_que=o_que, pasta=pasta,
                           userArq=preparado["nome_arquivo"],
                           userDados=preparado["dados"])
        return interpretar_resposta_complemento(bruto, o_que=o_que)
    enviar = (CRA.enviar_confirmacao if preparado["operacao"] == "Confirmacao"
              else CRA.enviar_retorno)
    bruto = enviar(preparado["nome_arquivo"], preparado["dados"], qual, pasta=pasta)
    return interpretar_resposta_envio(bruto, o_que=o_que)


def _agora_local() -> str:
    """A hora LOCAL, na forma de `database.now()` (`AAAA-MM-DDTHH:MM:SS`).

    **ERA A FUNÇÃO `datetime` DO SQLITE COM «now» ATÉ 14/10/2026, e isso é
    UTC** — três horas
    à frente do Maranhão —, enquanto `pt_retornos.gerado_em` é hora local: o
    arquivo aparecia «enviado» antes de ter sido gerado. Achado pela frente do
    painel do dia. A hora agora sai do Python, como em todo o resto da casa
    (e sem acoplar data calculada ao SQLite).
    """
    from datetime import datetime
    return datetime.now().replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%S")


def _gravar_envio(con: Any, preparado: dict, lido: dict, *,
                  qual: str, usuario: str | None,
                  agora: str | None = None) -> dict[str, Any]:
    agora = agora or _agora_local()
    banco(con).escrever(
        """UPDATE pt_retornos SET cra_enviado_em=%s, cra_enviado_ambiente=%s,
               cra_envio_resumo=%s, cra_enviado_por=%s, cra_envio_erro=NULL
           WHERE id=%s""",
        (agora, qual, (lido.get("resposta") or "")[:500], usuario,
         int(preparado["retorno_id"])))
    return {"retorno_id": int(preparado["retorno_id"]),
            "operacao": preparado["operacao"],
            "nome_arquivo": preparado["nome_arquivo"], "ambiente": qual, **lido}


def _o_que_se_guarda(erro: BaseException) -> str:
    """A frase da tela e, atrás dela, a resposta inteira da Central, quando a
    recusa a trouxe (`CraRecusou.bruto`). É o que vai para o campo de erro do
    arquivo — e só para ele. Só calcula."""
    bruto = str(getattr(erro, "bruto", "") or "")
    return f"{erro} Resposta: {bruto}" if bruto else str(erro)


def _registrar_falha(con: Any, retorno_id: int, *,
                     ambiente: str, erro: str) -> None:
    banco(con).escrever(
        """UPDATE pt_retornos SET cra_envio_erro=%s, cra_enviado_ambiente=%s
           WHERE id=%s""",
        (str(erro)[:CORTE_DO_ERRO], str(ambiente or "")[:20], int(retorno_id)))


def enviar_pos_remessa(
        transacao: Callable[[], Any], *,
        lotes: list[dict],
        andamentos: list[tuple[str, dict]],
        ambiente: str,
        ler_config: Callable[[str, str], str],
        pasta=None,
        usuario: str | None = None) -> dict[str, Any]:
    """A confirmação de cada lote e, DEPOIS dela, o andamento de cada
    apresentante — se o envio automático estiver ligado.

    `transacao` é quem abre a transação — `db.transaction` na rota —, e NÃO uma
    conexão já aberta: a rede corre entre duas transações curtas, nunca dentro
    de uma. A ordem importa: o andamento fala de protocolos que só a
    confirmação apresenta à Central.
    """
    # SÓ PRODUÇÃO (14/10/2026): vazio é produção, e lote de homologação é
    # recusado aqui, com a frase, antes de qualquer leitura ou rede.
    qual = CRED.ambiente_de_uso(CRED.CRA, ambiente)
    if not auto_envio_ligado(qual, ler_config):
        return {
            "auto": False,
            "ambiente": qual,
            "motivo": ("Envio automático à CRA desligado nas configurações "
                       f"para {qual.lower()}."),
            "enviados": [],
            "falhas": [],
        }
    if not CRED.tem(CRED.CRA, qual, pasta):
        return {
            "auto": True,
            "ambiente": qual,
            "motivo": ("Credencial de PRODUÇÃO da CRA não informada — envio "
                       "manual na Central, ou informe-a em Administrativo → "
                       "Configurações → Centrais."),
            "enviados": [],
            "falhas": [],
        }

    ids = ([(int(x["confirmacao_id"]), "Confirmacao") for x in lotes
            if x.get("confirmacao_id")]
           + [(int(a["andamento_id"]), "TituloComplemento")
              for _codigo, a in andamentos if a.get("andamento_id")])
    preparados: list[dict] = []
    falhas: list[dict] = []
    with transacao() as con:                       # 1. ler — curta
        for rid, operacao in ids:
            linha = PRE.retorno(con, rid)
            try:
                if not linha:
                    raise CraEnvioError(f"Arquivo #{rid} não existe.")
                preparados.append(_preparar(linha, con=con))
            except CraEnvioError as erro:
                falhas.append({"retorno_id": rid, "operacao": operacao,
                               "erro": str(erro)})

    # (preparado, o que a CRA respondeu, a frase da tela, o que vai ao campo de
    # erro) — a frase é curta; o campo de erro leva também a resposta (LH08).
    resultados: list[tuple[dict, dict | None, str | None, str | None]] = []
    confirmacao_falhou = any(f["operacao"] == "Confirmacao" for f in falhas)
    for preparado in preparados:                   # 2. a rede — sem transação
        if preparado["operacao"] == "TituloComplemento" and confirmacao_falhou:
            # O andamento fala de protocolos que a confirmação apresenta; sem
            # ela a Central recusaria título a título. Espera o reenvio.
            espera = ("A confirmação do lote não entrou na CRA; o "
                      "andamento espera por ela.")
            resultados.append((preparado, None, espera, espera))
            continue
        try:
            resultados.append((preparado, _transmitir(preparado, qual, pasta),
                               None, None))
        except (CRA.CraError, CRED.CredencialError) as erro:
            resultados.append((preparado, None, str(erro),
                               _o_que_se_guarda(erro)))
            if preparado["operacao"] == "Confirmacao":
                confirmacao_falhou = True

    enviados: list[dict] = []
    with transacao() as con:                       # 3. gravar — curta
        for falha in falhas:                       # as da preparação
            _registrar_falha(con, falha["retorno_id"], ambiente=qual,
                             erro=falha["erro"])
        for preparado, lido, erro, guardado in resultados:
            if erro is None:
                enviados.append(_gravar_envio(con, preparado, lido, qual=qual,
                                              usuario=usuario))
            else:
                _registrar_falha(con, preparado["retorno_id"], ambiente=qual,
                                 erro=guardado)
                falhas.append({"retorno_id": preparado["retorno_id"],
                               "operacao": preparado["operacao"], "erro": erro})

    return {
        "auto": True,
        "ambiente": qual,
        "motivo": "",
        "enviados": enviados,
        "falhas": falhas,
    }


def enviar_arquivo(transacao: Callable[[], Any], retorno_id: int, *,
                   pasta=None, usuario: str | None = None,
                   forcar: bool = False) -> dict[str, Any]:
    """Envia à CRA UM arquivo já gerado — o retorno das 11h30, a confirmação
    que falhou, o andamento do apontamento. É o botão «Enviar à CRA».

    ATÉ 14/10/2026 O RETORNO NÃO TINHA BOTÃO: o envio só rodava junto com a
    remessa (`enviar_pos_remessa`, confirmação e andamento), e o retorno — que
    a homologação aceitou pela operação `Retorno` em 13/10 (código 0000) — se
    baixava para subir à mão no portal. As mesmas três fases: ler (transação
    curta) → a rede (sem transação) → gravar (transação curta). Só produção.
    """
    qual = CRED.ambiente_de_uso(CRED.CRA, CRED.PRODUCAO)
    if not CRED.tem(CRED.CRA, qual, pasta):
        raise CraEnvioError(
            "A credencial de PRODUÇÃO da CRA não está informada — informe-a em "
            "Administrativo → Configurações → Centrais, ou suba o arquivo no "
            "portal da CRA.")
    with transacao() as con:                       # 1. ler — curta
        linha = PRE.retorno(con, int(retorno_id))
        if not linha:
            raise CraEnvioError(f"O arquivo #{retorno_id} não existe.")
        if str(linha["cra_enviado_ambiente"] or "") == "EOFICIO":
            raise CraEnvioError(
                "Esta linha não é um arquivo: é o registro de que o sistema antigo já "
                "informou a CRA antes da virada (14/10/2026). Não há o que enviar.")
        preparado = _preparar(linha, con=con, forcar=forcar)
    erro = guardado = None
    try:                                           # 2. a rede — sem transação
        lido = _transmitir(preparado, qual, pasta)
    except (CRA.CraError, CRED.CredencialError) as e:
        lido, erro, guardado = None, str(e), _o_que_se_guarda(e)
    with transacao() as con:                       # 3. gravar — curta
        if erro is None:
            return _gravar_envio(con, preparado, lido, qual=qual, usuario=usuario)
        _registrar_falha(con, int(retorno_id), ambiente=qual, erro=guardado)
    raise CraEnvioError(erro)
