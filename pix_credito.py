"""O CRÉDITO DE UM PIX NO EXTRATO DO BANCO — procurar, sem mexer em nada.

POR QUE EXISTE (29/10/2026)
    Um PIX de pagamento de título entrou na conta em 16/10/2026; foi lançado
    na ficha só em 21/10, «por PIX», sem comprovante, e informado à CRA como
    pago com a data do lançamento. Sem comprovante e sem o crédito conferido
    no sistema, o oficial levou 8 dias para conseguir confirmar se o dinheiro
    tinha entrado. A ordem dele: PIX só conta como pago com o comprovante
    anexado E com o crédito localizado no banco. Este módulo é a segunda
    metade — LOCALIZAR o crédito. Quem decide o que fazer com o achado é quem
    o chama (`protesto_pix`); aqui só se lê e se compara.

O QUE O BANCO OFERECE — medido no contrato e no que a casa já usa
    - **Banco Inter, API Banking v2** — `GET /banking/v2/extrato/completo`, o
      mesmo caminho da conciliação das despesas
      (`despesas_inter.ClienteInter.extrato`, que lê os DÉBITOS). Aqui com
      `tipoOperacao=C`: os CRÉDITOS. Cada transação traz `idTransacao`,
      `dataTransacao`, `tipoTransacao`, `valor` (texto, «1765.14») e, no Pix,
      `detalhes.endToEndId` e o pagador. Até 90 dias por consulta, paginado.
    - **O TOKEN DESTA CONFERÊNCIA SÓ LÊ.** O Inter entrega um token por
      conjunto de escopos (a razão de `cobranca_inter._Cliente`), e este pede
      só `extrato.read`: com ele não se paga nem se emite nada.
    - **A credencial é a das despesas** (`despesas_inter.credencial`, item
      «banco_inter» do cofre da automação). O cofre NÃO a entrega dentro de
      uma requisição web (`automacao_cofre.ler`): quem consulta é o processo da
      automação; a tela pede a rodada.
    - **Unicred: não há extrato** na documentação que a casa tem (só cobrança,
      `cobranca_unicred`, 27/10/2026). PIX que caiu na conta da Unicred, ou em
      qualquer conta que não a do Inter, não se acha por aqui — vai à
      confirmação à mão, com afirmação expressa.

COMO SE CASA (`procurar`)
    1. COM O E2E DO COMPROVANTE: o crédito com aquele `endToEndId`. Valor
       diferente → DIVERGE. E2E que já confirmou outro pagamento → JA_USADO.
       E2E que o extrato não tem → NAO_ACHADO, e NÃO se cai para o valor: o
       comprovante descreve uma transação que o banco não conhece.
    2. SEM O E2E: o crédito Pix do MESMO valor no MESMO dia. Um só → ACHADO.
       Mais de um → AMBIGUO: dois pagadores do mesmo valor no mesmo dia não se
       separam pelo valor, e confirmar o errado é o defeito que isto existe
       para impedir. Nenhum → NAO_ACHADO.
    Crédito que já confirmou outro pagamento nunca confirma um segundo.
"""
from __future__ import annotations

import re
import urllib.parse
from typing import Any, Iterable

import despesas_inter as INTER

#: O escopo do token desta conferência — e só ele.
ESCOPO_SO_LEITURA = "extrato.read"
#: O Inter devolve no máximo 90 dias por consulta do extrato.
JANELA_MAXIMA_DIAS = 90

ACHADO = "ACHADO"
DIVERGE = "DIVERGE"
JA_USADO = "JA_USADO"
AMBIGUO = "AMBIGUO"
NAO_ACHADO = "NAO_ACHADO"
RESULTADOS = {
    ACHADO: "crédito localizado",
    DIVERGE: "o E2E do comprovante está no extrato com OUTRO valor",
    JA_USADO: "o crédito já confirmou outro pagamento",
    AMBIGUO: "mais de um crédito do mesmo valor no mesmo dia",
    NAO_ACHADO: "crédito não localizado",
}

# O IDENTIFICADOR DO PIX (end-to-end, manual do Pix do Banco Central): «E»,
# o ISPB do participante que pagou (8 dígitos), a data e a hora em UTC
# (AAAAMMDDHHMM, 12 dígitos) e 11 caracteres alfanuméricos — 32 ao todo.
E2E = re.compile(r"E\d{8}\d{12}[A-Za-z0-9]{11}")
_E2E_INTEIRO = re.compile(r"\A" + E2E.pattern + r"\Z")


def e2e_valido(texto: Any) -> str | None:
    """O E2E digitado, sem espaços, se tem a forma do Banco Central; senão
    None. Só calcula."""
    limpo = "".join(str(texto or "").split())
    if limpo[:1] == "e":
        limpo = "E" + limpo[1:]
    return limpo if _E2E_INTEIRO.match(limpo) else None


def e2e_do_comprovante(conteudo: bytes, extensao: str) -> str | None:
    """O E2E escrito no comprovante em PDF, se der para ler. Só calcula.

    Imagem não se lê (não há OCR aqui), e PDF escaneado também não: a falta
    não é erro — o E2E é opcional, e sem ele a conferência casa pelo valor e
    pelo dia.
    """
    if str(extensao or "").lower() != ".pdf" or not conteudo:
        return None
    textos: list[str] = []
    try:
        import io

        import pypdf
        leitor = pypdf.PdfReader(io.BytesIO(bytes(conteudo)))
        for pagina in leitor.pages[:3]:
            textos.append(pagina.extract_text() or "")
    except Exception:                       # noqa: BLE001 — PDF torto: sem E2E
        pass
    textos.append(bytes(conteudo).decode("latin-1", errors="ignore"))
    for texto in textos:
        achado = E2E.search("".join(texto.split()))
        if achado:
            return achado.group(0)
    return None


def centavos_do_banco(valor: Any) -> int | None:
    """«1765.14», «1765,14» ou 1765.14 → 176514. None se não é valor. Só calcula."""
    if valor is None or isinstance(valor, bool):
        return None
    texto = str(valor).strip()
    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")
    else:
        texto = texto.replace(",", ".")
    try:
        return round(abs(float(texto)) * 100)
    except ValueError:
        return None


def _detalhes(t: dict) -> dict:
    d = t.get("detalhes")
    return d if isinstance(d, dict) else {}


def e2e_da_transacao(t: dict) -> str:
    """O end-to-end da transação do extrato, ou vazio. Só calcula."""
    d = _detalhes(t)
    for chave in ("endToEndId", "endToEnd", "e2eId", "e2eid"):
        valor = str(d.get(chave) or t.get(chave) or "").strip()
        if valor:
            return valor
    return ""


def id_da_transacao(t: dict) -> str:
    return str(t.get("idTransacao") or "").strip()


def dia_da_transacao(t: dict) -> str:
    return str(t.get("dataTransacao") or t.get("dataInclusao") or "")[:10]


def e_credito_pix(t: dict) -> bool:
    """Crédito, e por Pix. Só calcula."""
    if str(t.get("tipoOperacao") or "C").upper() != "C":
        return False
    tipo = str(t.get("tipoTransacao") or "").upper()
    detalhe = str(_detalhes(t).get("tipoDetalhe") or "").upper()
    return tipo == "PIX" or detalhe == "PIX" or bool(e2e_da_transacao(t))


#: Os créditos que a conciliação ao contrário lê: o PIX e a transferência
#: (TED). O boleto de cobrança fica de fora — é o depósito prévio do balcão
#: (`cobranca`), e tem conferência própria.
TIPOS_DA_CONCILIACAO = {"PIX": "PIX", "TRANSFERENCIA": "TED", "TED": "TED"}


def tipo_do_credito(t: dict) -> str | None:
    """«PIX», «TED», ou None quando o crédito não é nenhum dos dois. Só calcula."""
    if str(t.get("tipoOperacao") or "C").upper() != "C":
        return None
    for chave in (str(t.get("tipoTransacao") or "").upper(),
                  str(_detalhes(t).get("tipoDetalhe") or "").upper()):
        if chave in TIPOS_DA_CONCILIACAO:
            return TIPOS_DA_CONCILIACAO[chave]
    return "PIX" if e2e_da_transacao(t) else None


def documento_do_pagador(t: dict) -> str:
    """Só os dígitos do CPF/CNPJ de quem pagou — para COMPARAR com o devedor,
    e não para guardar. Só calcula."""
    d = _detalhes(t)
    bruto = str(d.get("cpfCnpjPagador") or d.get("cpfCnpjRemetente")
                or d.get("cpfCnpj") or "")
    return "".join(c for c in bruto if c.isdigit())


def nome_do_pagador(t: dict) -> str:
    d = _detalhes(t)
    return str(d.get("nomePagador") or d.get("nomeEmpresaPagador")
               or d.get("nomeRemetente") or "").strip()[:120]


def resumo_do_credito(t: dict) -> dict:
    """O que se guarda do crédito achado. O documento do pagador NÃO: o nome
    basta para conferir, e o CPF de quem pagou não é da conta da casa."""
    return {"id": id_da_transacao(t), "dia": dia_da_transacao(t),
            "valor_centavos": centavos_do_banco(t.get("valor")),
            "e2eid": e2e_da_transacao(t), "pagador": nome_do_pagador(t),
            "tipo": tipo_do_credito(t)}


def _mesmo_e2e(a: str, b: str) -> bool:
    return bool(a) and bool(b) and a.strip().upper() == b.strip().upper()


def procurar(creditos: Iterable[dict], *, valor_centavos: int, dia: str,
             e2eid: str | None = None,
             ja_usados: Iterable[str] = ()) -> dict:
    """Procura o crédito de UM PIX no extrato. Só calcula — ver o cabeçalho.

    `ja_usados` são os `idTransacao` e os E2E que já confirmaram outro
    pagamento. Devolve `resultado`, `credito` (o resumo, quando há um),
    `candidatos` e `motivo` (a frase para a tela e para a afirmação).
    """
    usados = {str(u).strip().upper() for u in ja_usados if str(u or "").strip()}
    pix = [t for t in creditos if isinstance(t, dict) and e_credito_pix(t)]
    valor = int(valor_centavos)
    dia = str(dia or "")[:10]

    def _usado(t: dict) -> bool:
        return (id_da_transacao(t).upper() in usados
                or e2e_da_transacao(t).upper() in usados)

    if e2eid:
        pelo_e2e = [t for t in pix if _mesmo_e2e(e2e_da_transacao(t), e2eid)]
        if not pelo_e2e:
            return {"resultado": NAO_ACHADO, "credito": None, "candidatos": 0,
                    "motivo": (f"o E2E do comprovante ({e2eid}) não está entre "
                               f"os créditos Pix do extrato")}
        t = pelo_e2e[0]
        resumo = resumo_do_credito(t)
        if _usado(t):
            return {"resultado": JA_USADO, "credito": resumo, "candidatos": 1,
                    "motivo": (f"o crédito do E2E {e2eid} já confirmou outro "
                               f"pagamento")}
        if resumo["valor_centavos"] != valor:
            return {"resultado": DIVERGE, "credito": resumo, "candidatos": 1,
                    "motivo": (f"o E2E {e2eid} está no extrato com outro valor "
                               f"({resumo['valor_centavos']} centavos)")}
        return {"resultado": ACHADO, "credito": resumo, "candidatos": 1,
                "motivo": f"crédito do E2E {e2eid} no extrato, valor e E2E iguais"}

    mesmos = [t for t in pix if not _usado(t)
              and centavos_do_banco(t.get("valor")) == valor
              and dia_da_transacao(t) == dia]
    if len(mesmos) == 1:
        return {"resultado": ACHADO, "credito": resumo_do_credito(mesmos[0]),
                "candidatos": 1,
                "motivo": "um só crédito Pix do mesmo valor no mesmo dia"}
    if len(mesmos) > 1:
        return {"resultado": AMBIGUO, "credito": None, "candidatos": len(mesmos),
                "motivo": (f"{len(mesmos)} créditos Pix do mesmo valor no mesmo "
                           f"dia — sem o E2E do comprovante, não há como saber "
                           f"qual é este")}
    return {"resultado": NAO_ACHADO, "credito": None, "candidatos": 0,
            "motivo": "nenhum crédito Pix do mesmo valor no mesmo dia no extrato"}


# ------------------------------------------------------------- o cliente


class ClienteExtrato(INTER.ClienteInter):
    """O extrato do Inter, com um token que SÓ LÊ (`extrato.read`)."""

    escopos = ESCOPO_SO_LEITURA

    def creditos(self, data_inicio: str, data_fim: str) -> list[dict]:
        """Os CRÉDITOS do período, todas as páginas. Só GET."""
        transacoes, pagina = [], 0
        while True:
            consulta = urllib.parse.urlencode({
                "dataInicio": data_inicio, "dataFim": data_fim, "pagina": pagina,
                "tamanhoPagina": 500, "tipoOperacao": "C"})
            r = self._ir("GET", f"{self.base}/banking/v2/extrato/completo?{consulta}",
                         cabecalhos=self._cab())
            if r.status != 200 or not isinstance(r.corpo, dict):
                raise INTER.Recusa(INTER._frase(r.corpo)
                                   or f"Extrato recusado (HTTP {r.status}).")
            transacoes += list(r.corpo.get("transacoes") or [])
            if r.corpo.get("ultimaPagina", True) or pagina > 200:
                return transacoes
            pagina += 1


def cliente_da_casa(cfg: dict, *, pasta: Any = None,
                    transporte: INTER.Transporte | None = None) -> ClienteExtrato:
    """O cliente do extrato, com a credencial e o ambiente das despesas.

    Fora da web: com o cofre da automação instalado, a credencial só sai para
    o processo que roda fora do servidor."""
    campos = INTER.credencial(pasta)
    if transporte is None:
        transporte = INTER.transporte_https(campos)
    return ClienteExtrato(cfg.get("despesas_ambiente") or "sandbox", transporte, campos)


def com_cofre() -> bool:
    """Se a credencial do banco mora no cofre da automação — e então só o
    processo da automação fala com o banco. Só calcula."""
    return INTER._cofre() is not None
