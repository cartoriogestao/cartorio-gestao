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

# TODOS OS PARES <codigo>/<ocorrencia> DO RELATÓRIO, E NÃO SÓ O PRIMEIRO —
# correção de 28/10/2026. A CRA responde a recusa do retorno com DOIS códigos
# no mesmo `<relatorio>`: primeiro `0000` com o apresentante (em vermelho) e
# DEPOIS `2161 — NENHUM REGISTRO FOI GRAVADO`. Medido na produção nesse dia:
# 6 dos 8 retornos enviados (R9872810, R9012810, R1LV2810, R1MF2810, R2372810,
# R7482810) voltaram assim, e o `search` do primeiro `<codigo>` lia `0000` e
# dava os seis por «enviado». Os dois aceitos (R0012810, R3412810) trazem um
# par só, `0000`, sem cor.
_PAR_DO_RELATORIO = re.compile(
    r"<codigo>\s*(\d+)\s*</codigo>\s*(?:<ocorrencia>(.*?)</ocorrencia>)?",
    re.IGNORECASE | re.DOTALL)
# A MARCA VERMELHA DA CRA. Nos 6 recusados de 28/10/2026 a ocorrência do
# apresentante vem em `<FONT COLOR='RED'>` (escapada no XML); nos 2 aceitos e
# nas confirmações aceitas, nunca. Sozinha ela não traz código, e por isso só
# decide quando o relatório não trouxe código de recusa nenhum.
_EM_VERMELHO = re.compile(
    r"FONT\s+COLOR\s*=\s*(?:&apos;|&quot;|['\"])?\s*RED", re.IGNORECASE)
_MARCACAO = re.compile(r"<[^>]*>")


def _ocorrencia_limpa(texto: str) -> str:
    """A ocorrência como a CRA a escreveu, sem as marcas de HTML. Só calcula.

    A CRA escapa `<FONT COLOR='RED'>` dentro do XML; desfeito o escape, a
    marca sai, e fica a frase dela.
    """
    from xml.sax.saxutils import unescape
    liso = unescape(str(texto or ""), {"&apos;": "'", "&quot;": '"'})
    return " ".join(_MARCACAO.sub(" ", liso).split())


def recusa_no_relatorio(texto: str) -> dict[str, Any] | None:
    """A recusa que o `<relatorio>` da CRA traz, ou `None`. SÓ CALCULA.

    Lê TODOS os pares código/ocorrência: o primeiro código fora de
    `0000`/`0001` é a recusa, com a ocorrência que vem logo depois dele. Sem
    código de recusa, a marca vermelha da Central também recusa (`codigo`
    `None`) — ela só apareceu, medida, em resposta recusada. Devolve
    `{"codigo", "motivo", "ocorrencias"}`.
    """
    bruto = str(texto or "")
    pares = [(c.strip(), _ocorrencia_limpa(o))
             for c, o in _PAR_DO_RELATORIO.findall(bruto)]
    for codigo, ocorrencia in pares:
        if codigo not in _CODIGOS_OK:
            return {"codigo": codigo, "motivo": ocorrencia,
                    "ocorrencias": [o for _c, o in pares if o]}
    if _EM_VERMELHO.search(bruto):
        vermelha = next((o for _c, o in pares if o), "")
        return {"codigo": None,
                "motivo": ("a CRA marcou a resposta em vermelho, sem código "
                           "de recusa" + (f": {vermelha}" if vermelha else "")),
                "ocorrencias": [o for _c, o in pares if o]}
    return None

#: O que da recusa vai à TELA: o motivo da `<ocorrencia>` até este tamanho e um
#: trecho curto do começo da resposta. A resposta INTEIRA vai só para
#: `pt_retornos.cra_envio_erro`, até `CORTE_DO_ERRO` (LH08, revisão do LH07).
TRECHO_NA_TELA = 240
TRECHO_DA_RESPOSTA = 160
CORTE_DO_ERRO = 4000


class CraEnvioError(CRA.CraError):
    """Falha ao enviar arquivo à CRA, com frase para o balcão."""


class CraEnvioRecusado(CraEnvioError):
    """A CRA RECUSOU o arquivo, com código ou motivo dela — 28/10/2026.

    Não é falha de rede: a Central respondeu e não gravou. O arquivo fica
    como recusado (`pt_retornos.cra_recusado_em`), e os atos dele NÃO foram
    informados."""

    def __init__(self, mensagem: str = "", *, codigo: str | None = None,
                 motivo: str | None = None) -> None:
        super().__init__(mensagem)
        self.codigo = codigo
        self.motivo = motivo


def _campo_da_linha(linha: Any, campo: str) -> Any:
    """O campo da linha de `pt_retornos`, ou `None` se ela não o tem. Só lê.

    Linha montada à mão (sem as colunas de 28/10/2026) não estoura aqui."""
    try:
        return linha[campo]
    except (KeyError, IndexError):
        return None


def _recusa_da_central(erro: BaseException) -> dict[str, Any] | None:
    """`{codigo, motivo}` quando a CRA disse NÃO com todas as letras. Só calcula.

    Só `CraRecusou` com código ou motivo conta: a resposta vazia, fora do
    XML ou a falha SOAP não dizem o que a Central gravou, e ficam como erro de
    envio, que se pode repetir depois de conferir.
    """
    if not isinstance(erro, CRA.CraRecusou):
        return None
    codigo = getattr(erro, "codigo", None)
    motivo = getattr(erro, "motivo", None)
    if not (codigo or motivo):
        return None
    return {"codigo": codigo, "motivo": motivo or ""}


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
        # O PRIMEIRO `<codigo>` NÃO DECIDE SOZINHO — 28/10/2026. Ver
        # `_PAR_DO_RELATORIO`: a recusa do retorno vem como `0000` +
        # `2161`, e ler só o primeiro dava por enviados seis arquivos que
        # a Central não gravou.
        recusa = recusa_no_relatorio(bruto)
        if recusa is None:
            return {"ok": True, "codigo": achado.group(1), "resposta": bruto}
        codigo = recusa["codigo"]
        explicacao = CRA.CODIGOS_MEDIDOS.get(codigo or "")
        if explicacao:
            raise CRA.CraRecusou(
                f"A CRA recusou ao {o_que} (código {codigo}): {explicacao}",
                bruto=bruto, codigo=codigo,
                motivo=recusa["motivo"] or explicacao)
        # A explicação da CRA mora em <ocorrencia>, DEPOIS do cabeçalho do
        # relatório; os 240 primeiros caracteres eram só o cabeçalho, e o
        # código 2154 do retorno RTAB2110.261 (21/10/2026) ficou gravado sem
        # o motivo. Vai o motivo primeiro, e um trecho curto do começo da
        # resposta (o nome do arquivo que ela cita). O bruto INTEIRO ia junto
        # na frase — para a tela, o `flash` no cookie da sessão e a auditoria
        # (revisão do LH07); agora vai à parte, só para o campo de erro.
        # O ponto final da CRA sai: a frase põe o dela (28/10/2026).
        motivo = (_trecho(recusa["motivo"]).rstrip(".") if recusa["motivo"]
                  else "a resposta não traz <ocorrencia>")
        inicio = _trecho(_DECLARACAO_XML.sub("", bruto), TRECHO_DA_RESPOSTA)
        qual = f" (código {codigo})" if codigo else ""
        raise CRA.CraRecusou(
            f"A CRA recusou ao {o_que}{qual}: {motivo}. "
            f"Início da resposta: {inicio}", bruto=bruto,
            codigo=codigo, motivo=motivo)
    upper = bruto.upper()
    if "INVÁLIDO" in upper or "INVALIDO" in upper or "CORROMPIDO" in upper:
        raise CRA.CraRecusou(f"A CRA recusou ao {o_que}: {bruto[:240]}",
                             bruto=bruto, motivo=_trecho(bruto))
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
    recusas, aceitos, primeiro_codigo = [], 0, None
    for titulo in raiz.iter("titulo"):
        for msg in titulo.iter("mensagens"):
            for item in msg:
                codigo = (item.findtext("codigo") or "").strip()
                if codigo in _COMPLEMENTO_OK:
                    aceitos += 1
                else:
                    primeiro_codigo = primeiro_codigo or codigo
                    recusas.append(f"{titulo.findtext('protocolo')}: {codigo} "
                                   f"{(item.findtext('descricao') or '').strip()}")
    if recusas:
        # TÍTULO RECUSADO COM CÓDIGO É RECUSA DA CENTRAL (28/10/2026): leva
        # código e motivo, e o arquivo fica como recusado, e não como «erro
        # de envio» a repetir.
        motivo = "; ".join(recusas[:10])
        raise CRA.CraRecusou(f"A CRA recusou ao {o_que}: {motivo}",
                             bruto=bruto, codigo=primeiro_codigo,
                             motivo=motivo)
    if not aceitos:
        # Sem título confirmado e sem título recusado não se sabe o que a
        # Central gravou: fica como erro, sem código, e não como recusa.
        raise CRA.CraRecusou(
            f"A CRA recusou ao {o_que}: nenhum título confirmado",
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
    # O ARQUIVO RECUSADO CUJOS ATOS VOLTARAM À FILA NÃO SE REENVIA (28/10/2026).
    # Os atos dele já estão esperando o próximo retorno; mandar este de novo
    # informaria duas vezes o que o arquivo seguinte também vai levar.
    recusado_em = _campo_da_linha(linha, "cra_recusado_em")
    if (recusado_em and con is not None and tipo != "SDTBFOCRT"
            and int(_campo_da_linha(linha, "titulos") or 0) > 0
            and not banco(con).um(
                "SELECT 1 FROM pt_atos WHERE retorno_id = %s LIMIT 1",
                (int(retorno_id),))):
        raise CraEnvioError(
            f"A CRA recusou «{linha['nome_arquivo']}» em "
            f"{str(recusado_em)[:16]}, e os atos dele já voltaram à fila de "
            f"«Esperando retorno». Gere um retorno novo em vez de reenviar "
            f"este.")
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
        # Aceito agora, a recusa de uma tentativa anterior deixa de valer: o
        # arquivo ESTÁ na Central, e a tela não pode dizer as duas coisas.
        """UPDATE pt_retornos SET cra_enviado_em=%s, cra_enviado_ambiente=%s,
               cra_envio_resumo=%s, cra_enviado_por=%s, cra_envio_erro=NULL,
               cra_recusado_em=NULL, cra_recusa_codigo=NULL,
               cra_recusa_motivo=NULL
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


#: O motivo da recusa que vai à TELA, gravado à parte do erro inteiro.
CORTE_DO_MOTIVO = 500


def _registrar_recusa(con: Any, retorno_id: int, *, ambiente: str,
                      erro: str, recusa: dict[str, Any],
                      agora: str | None = None) -> None:
    """A CRA RECUSOU: situação própria, e o arquivo NÃO é «enviado». ESCREVE.

    O ARQUIVO RECUSADO ERA DADO POR ENVIADO — 28/10/2026. Seis retornos
    recusados com 2161 «NENHUM REGISTRO FOI GRAVADO» ficaram com
    `cra_enviado_em` preenchido, e a tela os mostrou como enviados. Agora a
    recusa tem colunas próprias (quando, o código e o motivo da Central), o
    `cra_enviado_em` fica vazio, e `cra_envio_erro` guarda a frase e a
    resposta inteira, como já guardava para o erro de envio.

    OS ATOS DO ARQUIVO NÃO SE SOLTAM AQUI. Eles continuam presos a ele (e
    portanto fora de `protesto_retorno.pendentes`), e a tela diz que NÃO
    foram informados; quem os devolve à fila é o balcão, depois de ler o
    motivo (`protesto_retorno.devolver_atos_do_recusado`). Medido em
    28/10/2026: os 16 atos dos seis recusados são PROTESTOS relavrados de
    títulos cujo protesto anterior (desfeito) já tinha sido informado — a CRA
    recusou porque já sabia. Devolvê-los sozinha faria o próximo retorno
    levá-los de novo, e ser recusado de novo.
    """
    banco(con).escrever(
        """UPDATE pt_retornos SET cra_enviado_em=NULL, cra_recusado_em=%s,
               cra_recusa_codigo=%s, cra_recusa_motivo=%s,
               cra_envio_erro=%s, cra_enviado_ambiente=%s
           WHERE id=%s""",
        (agora or _agora_local(), recusa.get("codigo"),
         str(recusa.get("motivo") or "")[:CORTE_DO_MOTIVO],
         str(erro)[:CORTE_DO_ERRO], str(ambiente or "")[:20],
         int(retorno_id)))


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
    # O quinto elemento é a recusa da Central (`_recusa_da_central`), quando
    # houve: ela se grava como RECUSA, e não como erro de envio (28/10/2026).
    resultados: list[tuple[dict, dict | None, str | None, str | None,
                           dict | None]] = []
    confirmacao_falhou = any(f["operacao"] == "Confirmacao" for f in falhas)
    for preparado in preparados:                   # 2. a rede — sem transação
        if preparado["operacao"] == "TituloComplemento" and confirmacao_falhou:
            # O andamento fala de protocolos que a confirmação apresenta; sem
            # ela a Central recusaria título a título. Espera o reenvio.
            espera = ("A confirmação do lote não entrou na CRA; o "
                      "andamento espera por ela.")
            resultados.append((preparado, None, espera, espera, None))
            continue
        try:
            resultados.append((preparado, _transmitir(preparado, qual, pasta),
                               None, None, None))
        except (CRA.CraError, CRED.CredencialError) as erro:
            resultados.append((preparado, None, str(erro),
                               _o_que_se_guarda(erro),
                               _recusa_da_central(erro)))
            if preparado["operacao"] == "Confirmacao":
                confirmacao_falhou = True

    enviados: list[dict] = []
    with transacao() as con:                       # 3. gravar — curta
        for falha in falhas:                       # as da preparação
            _registrar_falha(con, falha["retorno_id"], ambiente=qual,
                             erro=falha["erro"])
        for preparado, lido, erro, guardado, recusa in resultados:
            if erro is None:
                enviados.append(_gravar_envio(con, preparado, lido, qual=qual,
                                              usuario=usuario))
            elif recusa is not None:
                _registrar_recusa(con, preparado["retorno_id"], ambiente=qual,
                                  erro=guardado, recusa=recusa)
                falhas.append({"retorno_id": preparado["retorno_id"],
                               "operacao": preparado["operacao"], "erro": erro,
                               "recusado": True,
                               "codigo": recusa.get("codigo")})
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
    erro = guardado = recusa = None
    try:                                           # 2. a rede — sem transação
        lido = _transmitir(preparado, qual, pasta)
    except (CRA.CraError, CRED.CredencialError) as e:
        lido, erro, guardado = None, str(e), _o_que_se_guarda(e)
        recusa = _recusa_da_central(e)
    with transacao() as con:                       # 3. gravar — curta
        if erro is None:
            return _gravar_envio(con, preparado, lido, qual=qual, usuario=usuario)
        if recusa is not None:
            _registrar_recusa(con, int(retorno_id), ambiente=qual,
                              erro=guardado, recusa=recusa)
        else:
            _registrar_falha(con, int(retorno_id), ambiente=qual, erro=guardado)
    if recusa is not None:
        # A frase é a mesma do erro gravado (a tela acrescenta o que a
        # recusa quer dizer para os atos).
        raise CraEnvioRecusado(erro, codigo=recusa.get("codigo"),
                               motivo=recusa.get("motivo"))
    raise CraEnvioError(erro)


def reclassificar_recusas_gravadas(con: Any) -> int:
    """Relê a resposta GRAVADA dos arquivos dados por enviados. ESCREVE.

    OS SEIS DE 28/10/2026 FICARAM COMO «ENVIADO», e a resposta que os recusa
    está gravada neles (`cra_envio_resumo`, os 500 primeiros caracteres): o
    `<relatorio>` com `0000` e depois `2161 — NENHUM REGISTRO FOI GRAVADO`.
    Esta passada lê essa resposta com a régua de agora e passa a RECUSADO o
    arquivo que ela PROVA recusado — por código de recusa, e só por ele: a
    marca vermelha sozinha não basta aqui, porque o resumo pode ter sido
    cortado antes do código (é o caso do R1LV2310.261, de 23/10/2026, medido:
    vermelho e cortado, sem código à vista; fica como está, a conferir na
    Central). Idempotente: o que já é recusado não volta a ser lido.

    NÃO MEXE NOS ATOS. Eles continuam presos ao arquivo, e a tela diz que
    não foram informados; devolvê-los à fila é do balcão.
    """
    bd = banco(con)
    linhas = bd.ler(
        """SELECT id, nome_arquivo, cra_enviado_em, cra_envio_resumo
             FROM pt_retornos
            WHERE cra_enviado_em IS NOT NULL AND cra_recusado_em IS NULL
              AND cra_envio_resumo LIKE %s""", ("%<relatorio%",))
    feitos = 0
    for linha in linhas:
        resumo = str(linha["cra_envio_resumo"] or "")
        recusa = recusa_no_relatorio(resumo)
        if not recusa or not recusa["codigo"]:
            continue
        # O resumo guarda 500 caracteres, e pode cortar a ocorrência no meio
        # (R1MF2810.261, medido em 28/10/2026: o código 2161 à vista, o
        # motivo cortado). O código basta para provar a recusa.
        motivo = _trecho(recusa["motivo"]
                         or "o resumo gravado foi cortado antes do motivo "
                            "da CRA").rstrip(".")
        bd.escrever(
            """UPDATE pt_retornos SET cra_recusado_em=cra_enviado_em,
                   cra_enviado_em=NULL, cra_recusa_codigo=%s,
                   cra_recusa_motivo=%s, cra_envio_erro=%s
               WHERE id=%s AND cra_enviado_em IS NOT NULL""",
            (recusa["codigo"], motivo[:CORTE_DO_MOTIVO],
             (f"A CRA recusou «{linha['nome_arquivo']}» (código "
              f"{recusa['codigo']}): {motivo}. O sistema o dera por enviado; "
              f"reclassificado pela resposta gravada (28/10/2026). Resposta: "
              f"{resumo}")[:CORTE_DO_ERRO],
             int(linha["id"])))
        feitos += 1
    return feitos
