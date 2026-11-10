"""A COBRANÇA PELA PARCELA EXPRESS — boleto, Pix e cartão no mesmo link.

O CONTRATO (OpenAPI de parceiros em docs.parcelaexpress.com.br, lida em
05/11/2026)
    Base de teste: https://sandbox.parcelaexpress.com.br
    Base de produção: https://api-prod.parcelaexpress.com.br
    (o portal CartExpress, cartorios.parcelaexpress.com.br, usa essa base)
    Toda chamada depois do login leva `Authorization: Bearer` com JWT.

    - Login: POST /v2/auth/login {email, password} → access_token (ou token).
      Este caminho NÃO está no OpenAPI público, que começa já com o JWT. É o
      login de e-mail e senha do portal de parceiros. Se a Parcela responder
      404, a frase traz o caminho: não se troca o endereço em silêncio.
    - Cobrança do protocolo: POST /v1/payment-links
      {amount em centavos, description, expires_in, payer, seller_id,
      payment_methods: pix, billet e card}
      → {id, url, token, status}. Um link só: o cliente escolhe Pix, boleto
      ou cartão. Não se emite um boleto e um Pix separados — seriam duas
      cobranças do mesmo ato.
    - Consultar: GET /v1/sellers/{sellerId}/payment-links (autenticado).
    - Cancelar: POST /v1/payment-links/sellers/{sellerId}/{id}/cancel.

    O PDF do boleto não vem neste link. A tela mostra o endereço. A linha
    digitável e o Pix copia-e-cola entram na ficha quando a consulta os traz
    (billet_data ou o bloco do Pix). Sem eles, o pagamento é o link.

NADA AQUI LANÇA NO CAIXA. A Parcela paga entra no caixa geral em
`cobranca.entrar_no_caixa_geral`, quando a resposta é gravada.
"""
from __future__ import annotations

import json
import re
import ssl
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any

import cobranca as CB
from cobranca_banco import (
    BancoError,
    CredencialAusente,
    CredencialTrancada,
    Indisponivel,
    Recusa,
)
from despesas_inter import Resposta

ENDERECOS = {
    "producao": "https://api-prod.parcelaexpress.com.br",
    "sandbox": "https://sandbox.parcelaexpress.com.br",
}
CAMINHO_DO_TOKEN = "/v2/auth/login"
NOME_NO_COFRE = "banco_parcela"
ARQUIVO_DA_CREDENCIAL = "banco_parcela.cred"
CAMPOS_DA_CREDENCIAL = ("email", "senha", "seller_id")
CAMPO_DA_MAQUININHA = "terminal_id"
ROTULOS_DA_CREDENCIAL = {
    "email": "E-mail do portal Parcela Express",
    "senha": "Senha do portal Parcela Express",
    "seller_id": "sellerId do estabelecimento",
    "terminal_id": "Código da maquininha (terminal_id)",
}
PRAZO_SEGUNDOS = 30
VIDA_DO_TOKEN = 50 * 60
FORMAS = ("pix", "billet", "card")

SITUACAO_PAGA = frozenset({
    "PAID", "SUCCEEDED", "CAPTURED", "PAID_OUT",
})
SITUACAO_CANCELADA = frozenset({"CANCELED", "CANCELLED", "VOIDED", "INACTIVE"})
SITUACAO_BAIXADA = frozenset({"EXPIRED", "EXPIRADO"})
FORMA = {
    "PIX": "PIX",
    "PIX_POS": "PIX",
    "BILLET": "BOLETO",
    "BOLETO": "BOLETO",
    "CREDIT": "CARTAO",
    "DEBIT": "CARTAO",
    "CARD": "CARTAO",
}

Transporte = Callable[..., Resposta]


def _pasta(pasta: Any = None):
    from pathlib import Path
    if pasta:
        return Path(pasta)
    import centrais_cred
    return centrais_cred.pasta_de_dados()


def _cofre():
    try:
        import automacao_cofre  # type: ignore
    except ImportError:
        return None
    return automacao_cofre


def credencial(pasta: Any = None) -> dict:
    cofre = _cofre()
    if cofre is not None:
        try:
            campos = cofre.ler(NOME_NO_COFRE)
        except Exception as erro:
            if getattr(erro, "cofre_trancado", False) or "Trancad" in type(erro).__name__:
                raise CredencialTrancada(
                    "O cofre está trancado: o oficial precisa desbloqueá-lo "
                    "para a cobrança andar.") from erro
            campos = None
        if campos:
            return dict(campos)
    import cofre_cred
    campos = cofre_cred.ler(_pasta(pasta), ARQUIVO_DA_CREDENCIAL)
    if campos:
        return dict(campos)
    raise CredencialAusente(
        "A credencial da Parcela Express não foi cadastrada "
        "(Cobrança → Configuração).")


def conferir_credencial(campos: Mapping[str, Any]) -> dict:
    limpos = {c: str(campos.get(c) or "").strip() for c in CAMPOS_DA_CREDENCIAL}
    faltam = [ROTULOS_DA_CREDENCIAL[c] for c, v in limpos.items() if not v]
    if faltam:
        raise CB.CobrancaError(
            "Faltam na credencial da Parcela Express: " + "; ".join(faltam) + ".")
    if "@" not in limpos["email"] or len(limpos["email"]) < 6:
        raise CB.CobrancaError("O e-mail da Parcela Express não está completo.")
    if len(limpos["seller_id"]) < 8:
        raise CB.CobrancaError("O sellerId da Parcela Express está curto demais.")
    maquina = str(campos.get(CAMPO_DA_MAQUININHA) or "").strip()
    if maquina and not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", maquina):
        raise CB.CobrancaError(
            "O código da maquininha só pode ter letras, números, _ e -.")
    limpos[CAMPO_DA_MAQUININHA] = maquina
    return limpos


def gravar_credencial(campos: Mapping[str, Any], pasta: Any = None) -> dict:
    limpos = conferir_credencial(campos)
    if not limpos.get(CAMPO_DA_MAQUININHA):
        try:
            anterior = credencial(pasta)
        except BancoError:
            anterior = {}
        limpos[CAMPO_DA_MAQUININHA] = str(anterior.get(CAMPO_DA_MAQUININHA) or "").strip()
    cofre = _cofre()
    if cofre is not None:
        try:
            cofre.gravar(NOME_NO_COFRE, limpos, tipo="API", por="cobranca")
        except Exception as erro:
            raise CB.CobrancaError(
                f"O cofre não gravou a credencial da Parcela Express: {erro}") from erro
        return {"onde": "cofre", "terminal_id": limpos.get(CAMPO_DA_MAQUININHA, "")}
    import cofre_cred
    base = _pasta(pasta)
    base.mkdir(parents=True, exist_ok=True)
    try:
        cofre_cred.gravar(base, ARQUIVO_DA_CREDENCIAL, limpos)
        conferido = cofre_cred.ler(base, ARQUIVO_DA_CREDENCIAL)
    except (OSError, cofre_cred.CofreError) as erro:
        raise CB.CobrancaError(
            f"A credencial da Parcela Express não foi gravada: {erro}.") from erro
    if any(conferido.get(k, "") != v for k, v in limpos.items()):
        raise CB.CobrancaError(
            "A credencial da Parcela Express não voltou igual na conferência.")
    return {"onde": "arquivo cifrado da pasta de dados",
            "terminal_id": limpos.get(CAMPO_DA_MAQUININHA, "")}


def resumo_da_credencial(pasta: Any = None) -> dict | None:
    cofre = _cofre()
    if cofre is not None:
        try:
            cofre.metadados(NOME_NO_COFRE)
        except Exception as erro:
            if type(erro).__name__ == "ItemInexistente":
                return None
            return {"erro": str(erro)}
        return {"onde": "cofre"}
    try:
        campos = credencial(pasta)
    except BancoError:
        return None
    return {"onde": "arquivo cifrado", "email": campos.get("email", ""),
            "terminal_id": campos.get(CAMPO_DA_MAQUININHA, "")}


def transporte_https(prazo: int = PRAZO_SEGUNDOS) -> Transporte:
    contexto = ssl.create_default_context()
    contexto.minimum_version = ssl.TLSVersion.TLSv1_2

    def chamar(metodo: str, url: str, *, json_corpo: Any = None,
               cabecalhos: dict | None = None) -> Resposta:
        cab = dict(cabecalhos or {})
        dados = None
        if json_corpo is not None:
            dados = json.dumps(json_corpo).encode("utf-8")
            cab["Content-Type"] = "application/json"
        pedido = urllib.request.Request(url, data=dados, method=metodo, headers=cab)
        try:
            with urllib.request.urlopen(pedido, timeout=prazo, context=contexto) as r:
                status, tipo, bruto = r.status, r.headers.get("Content-Type", ""), r.read()
        except urllib.error.HTTPError as erro:
            status, tipo, bruto = erro.code, erro.headers.get("Content-Type", ""), erro.read()
        except urllib.error.URLError as erro:
            raise Indisponivel(f"A Parcela Express não respondeu: {erro.reason}.") from erro
        if re.search(r"json", tipo or "", re.I) or (bruto[:1:] in (b"{", b"[")):
            try:
                return Resposta(status, json.loads(bruto.decode("utf-8") or "{}"), tipo)
            except ValueError:
                return Resposta(status, bruto, tipo)
        return Resposta(status, bruto, tipo)

    return chamar


def _frase(corpo: Any) -> str:
    """Mensagens de validação, limitadas; não expõe target/value/headers."""
    fila = [corpo]
    partes = []
    for _ in range(40):
        if not fila:
            break
        atual = fila.pop(0)
        if isinstance(atual, dict):
            for chave in ("message", "error", "erro", "detail", "errors"):
                if atual.get(chave):
                    fila.append(atual[chave])
            if isinstance(atual.get("constraints"), dict):
                fila.extend(list(atual["constraints"].values())[:10])
        elif isinstance(atual, list):
            fila.extend(atual[:10])
        elif isinstance(atual, str):
            frase = CB._texto(atual, 300)
            if frase and frase not in partes:
                partes.append(frase)
    return " · ".join(partes)[:600]


def _primeiro(corpo: Mapping[str, Any], *chaves: str) -> str:
    fila: list[Any] = [corpo]
    vistos = 0
    while fila and vistos < 40:
        atual = fila.pop(0)
        vistos += 1
        if not isinstance(atual, dict):
            continue
        for chave in chaves:
            if atual.get(chave) not in (None, ""):
                return str(atual[chave])
        for valor in atual.values():
            if isinstance(valor, dict):
                fila.append(valor)
    return ""


class ClienteCobrancaParcela:
    """A API de links da Parcela Express, por um transporte injetável."""

    banco = CB.PARCELA
    fornece_pdf = False

    def __init__(self, ambiente: str, transporte: Transporte, campos: dict):
        self.ambiente = ambiente if ambiente in ENDERECOS else "sandbox"
        self.base = ENDERECOS[self.ambiente]
        self._transporte = transporte
        self._campos = conferir_credencial(campos)
        self._token = ""
        self._token_ate = 0.0

    def _cab(self) -> dict:
        return {"Authorization": f"Bearer {self._token_de_acesso()}",
                "Accept": "application/json"}

    def _token_de_acesso(self) -> str:
        if self._token and time.time() < self._token_ate:
            return self._token
        r = self._transporte(
            "POST", self.base + CAMINHO_DO_TOKEN,
            json_corpo={"email": self._campos["email"],
                        "password": self._campos["senha"]},
            cabecalhos={"Accept": "application/json"})
        if r.status >= 500 or r.status == 429:
            raise Indisponivel(
                f"A Parcela Express não entregou o token (HTTP {r.status}).")
        if r.status == 404:
            raise Recusa(
                "A Parcela Express não tem o login em "
                f"{CAMINHO_DO_TOKEN} (HTTP 404). O OpenAPI público não "
                "documenta esse caminho; confirme o endereço com o portal.")
        if r.status not in (200, 201) or not isinstance(r.corpo, dict):
            raise Recusa(_frase(r.corpo) or
                         f"A Parcela Express recusou o login (HTTP {r.status}).")
        token = str(r.corpo.get("access_token") or r.corpo.get("token")
                    or r.corpo.get("id_token") or "").strip()
        if not token:
            raise Recusa("A Parcela Express aceitou o login sem devolver o token.")
        vida = r.corpo.get("expires_in") or r.corpo.get("expiresIn") or VIDA_DO_TOKEN
        try:
            segundos = min(int(vida), 8 * 3600)
        except (TypeError, ValueError):
            segundos = VIDA_DO_TOKEN
        self._token = token
        self._token_ate = time.time() + max(60, segundos - 60)
        return token

    def _ir(self, metodo: str, caminho: str, **kw) -> Resposta:
        try:
            return self._transporte(metodo, self.base + caminho,
                                    cabecalhos=self._cab(), **kw)
        except Indisponivel:
            raise
        except Recusa:
            raise

    def corpo(self, c: Mapping[str, Any]) -> dict:
        end = CB.endereco(c)
        pagador: dict[str, Any] = {
            "name": CB._texto(c["pagador_nome"], 80),
            "document": c["pagador_documento"],
        }
        if c.get("pagador_email"):
            pagador["email"] = c["pagador_email"]
        if end.get("logradouro") and end.get("cep"):
            pagador["address"] = {
                "street": CB._texto(end.get("logradouro"), 80),
                "number": CB._texto(end.get("numero") or "S/N", 10),
                "zipcode": CB.digitos(end.get("cep"))[:8],
                "city": CB._texto(end.get("cidade"), 40),
                "state": CB._texto(end.get("uf"), 2),
                "district": CB._texto(end.get("bairro"), 40),
                "complement": CB._texto(end.get("complemento"), 40),
            }
        return {
            "amount": int(c["valor"]),
            "description": CB._texto(c.get("mensagem") or f"Protocolo {c.get('seu_numero')}", 180),
            "expires_in": f"{c['vencimento']}T23:59:59Z",
            "payer": pagador,
            "payment_methods": list(FORMAS),
            "seller_id": self._campos["seller_id"],
            "link_title": f"Protocolo {c.get('seu_numero') or ''}".strip(),
        }

    def emitir(self, c: Mapping[str, Any]) -> str:
        if str(c.get("forma_pedida") or "").upper() in CB.FORMAS_NA_MAQUINA:
            return self._emitir_na_maquina(c)
        r = self._ir("POST", "/v1/payment-links", json_corpo=self.corpo(c))
        if r.status in (200, 201) and isinstance(r.corpo, dict):
            achado = str(r.corpo.get("token") or r.corpo.get("id") or "").strip()
            if achado:
                return achado
        if r.status >= 500:
            raise Indisponivel(f"A Parcela Express não emitiu (HTTP {r.status}).")
        raise Recusa(_frase(r.corpo) or
                     f"A Parcela Express recusou a emissão (HTTP {r.status}).")

    def _emitir_na_maquina(self, c: Mapping[str, Any]) -> str:
        """Manda o valor para a maquininha. Pix, crédito ou débito."""
        maquina = str(self._campos.get(CAMPO_DA_MAQUININHA) or "").strip()
        if not maquina:
            raise Recusa(
                "Cadastre o código da maquininha em Pix, boleto e cartão → "
                "Configuração, no campo da Parcela Express.")
        forma = str(c.get("forma_pedida") or "").upper()
        servico = _service_id(c)
        r = self._ir(
            "POST", f"/v1/pos/payments/{urllib_quote(self._campos['seller_id'])}",
            json_corpo={
                "terminal_id": maquina,
                "amount": int(c["valor"]),
                "is_debit": forma == "DEBITO",
                "instalments": 1 if forma == "CREDITO" else 0,
                "service_id": servico,
                "is_pix": forma == "PIX",
                "description": CB._texto(c.get("mensagem") or servico, 80),
                "document": CB.digitos(c.get("pagador_documento")),
                "pre_capture": False,
            })
        if r.status in (200, 201):
            ident = ""
            if isinstance(r.corpo, dict):
                ident = str(r.corpo.get("id") or r.corpo.get("sale_id")
                            or r.corpo.get("saleId") or "").strip()
            return "pos:" + (ident or servico)
        if r.status >= 500:
            raise Indisponivel(f"A maquininha não respondeu (HTTP {r.status}).")
        detalhe = _frase(r.corpo)
        raise Recusa(f"A Parcela Express não enviou à maquininha (HTTP {r.status}). {detalhe}".strip())

    def consultar(self, c: Mapping[str, Any]) -> dict | None:
        ident = str(c.get("banco_id") or "").strip()
        if ident.startswith("pos:"):
            return self._consultar_maquina(ident[4:])
        corpo = self._link_do_estabelecimento(ident)
        if corpo is None:
            return None
        lido = ler(corpo)
        if lido.get("situacao") == CB.RECEBIDA and (
                lido.get("valor_recebido") != int(c["valor"]) or _centavos(corpo.get("amount")) != int(c["valor"])):
            venda = corpo.get("sale") or {}
            # Apenas números do link já identificado, para conferir principal e
            # encargos. Nunca registra corpo completo, credencial ou pagador.
            valores = {k: v if isinstance(v, (int, float)) or (
                       isinstance(v, str) and re.fullmatch(r"\d{1,15}(?:\.\d{1,4})?", v)) else None
                       for k, v in {"link_amount": corpo.get("amount"),
                                    "sale_amount": venda.get("amount"),
                                    "sale_original_amount": venda.get("original_amount")}.items()}
            raise Recusa("O valor pago na Parcela difere da cobrança. "
                         f"Esperado {int(c['valor'])} centavos; campos numéricos da API: {json.dumps(valores)}. "
                         "Confira principal e encargos antes de lançar.")
        return lido

    def _link_do_estabelecimento(self, ident: str) -> dict | None:
        """O checkout público recusa links pagos/expirados. Nunca é conciliação.

        A API guarda tanto id como token; instalações antigas guardam token.
        Percorre a paginação inteira, sem escolher por valor/nome ou emitir de novo.
        """
        if not ident:
            return None
        achado = None
        for pagina in range(1, 1001):
            caminho = (f"/v1/sellers/{urllib_quote(self._campos['seller_id'])}/payment-links"
                       f"?limit=100&current_page={pagina}")
            r = self._ir("GET", caminho)
            if r.status >= 500 or r.status == 429:
                raise Indisponivel(f"A Parcela Express não consultou (HTTP {r.status}).")
            if r.status != 200 or not isinstance(r.corpo, dict):
                raise Recusa(_frase(r.corpo) or "A Parcela recusou a consulta do estabelecimento.")
            linhas = r.corpo.get("results")
            if not isinstance(linhas, list) or any(not isinstance(v, dict) for v in linhas):
                raise Recusa("A Parcela devolveu uma lista de cobranças incompleta.")
            for v in linhas:
                if ident not in (str(v.get("id") or ""), str(v.get("token") or "")):
                    continue
                seller = v.get("seller") or {}
                if not isinstance(seller, dict) or (seller.get("id") and
                        str(seller["id"]) != self._campos["seller_id"]):
                    raise Recusa("A cobrança retornada pertence a outro estabelecimento.")
                if achado is not None:
                    raise Recusa("A Parcela retornou cobranças duplicadas. Confira a identificação.")
                achado = v
            if r.corpo.get("has_more") is False:
                return achado
            try:
                total = int(r.corpo["total_pages"])
                atual = int(r.corpo["current_page"])
            except (KeyError, ValueError, TypeError):
                raise Recusa("A Parcela não informou a paginação completa.") from None
            if atual != pagina or total < pagina:
                raise Recusa("A paginação da Parcela está inconsistente.")
            if pagina == total:
                return achado
        raise Recusa("A consulta da Parcela excedeu o limite de páginas; nenhuma baixa foi feita.")

    def procurar(self, c: Mapping[str, Any], *, data_inicial: str, data_final: str) -> None:
        return None

    def pdf(self, c: Mapping[str, Any]) -> bytes:
        raise Recusa(
            "A Parcela Express entrega o pagamento no link, não num PDF. "
            "Abra o link da cobrança.")

    def _consultar_maquina(self, venda: str) -> dict | None:
        if not venda:
            return {"situacao": CB.ABERTA, "banco_status": "NA_MAQUINA",
                    "banco_motivo": "Aguardando o pagamento na maquininha."}
        r = self._ir(
            "GET",
            f"/v1/sellers/{urllib_quote(self._campos['seller_id'])}/sales/"
            f"{urllib_quote(venda)}")
        if r.status == 404:
            return {"situacao": CB.ABERTA, "banco_status": "NA_MAQUINA",
                    "banco_motivo": "Aguardando o pagamento na maquininha."}
        if r.status == 200 and isinstance(r.corpo, dict):
            lido = ler(r.corpo if isinstance(r.corpo.get("sale"), dict)
                       else {"sale": r.corpo, "status": r.corpo.get("status")})
            lido.setdefault("banco_motivo", "Pagamento na maquininha.")
            return lido
        if r.status >= 500:
            raise Indisponivel(f"A Parcela Express não consultou a maquininha (HTTP {r.status}).")
        raise Recusa(_frase(r.corpo) or
                     f"A Parcela Express recusou a consulta da maquininha (HTTP {r.status}).")

    def cancelar(self, c: Mapping[str, Any], motivo: str) -> str:
        ident = str(c.get("banco_id") or "").strip()
        if ident.startswith("pos:"):
            servico = _service_id(c)
            r = self._ir(
                "POST", f"/v1/pos/cancel_sale/{urllib_quote(self._campos['seller_id'])}",
                json_corpo={
                    "terminal_id": self._campos.get(CAMPO_DA_MAQUININHA) or "",
                    "abort_reason": CB._texto(motivo, 80) or "cancelado no caixa",
                    "service_id": servico,
                    "cancel_sale_id": ident[4:],
                    "cancel_service_id": servico,
                })
            if r.status in (200, 201, 204):
                return ""
            raise Recusa(_frase(r.corpo) or
                         f"A maquininha não cancelou (HTTP {r.status}).")
        atual = self._link_do_estabelecimento(ident)
        if not atual or not atual.get("id"):
            raise Recusa("A Parcela não localizou a cobrança para cancelar.")
        if str(atual.get("status") or "").upper() == "PAID":
            raise Recusa("A cobrança já foi paga; consulte o pagamento antes de qualquer cancelamento.")
        identificador = str(atual["id"])
        caminho = (f"/v1/payment-links/sellers/{self._campos['seller_id']}/"
                   f"{urllib_quote(identificador)}/cancel")
        r = self._ir("POST", caminho, json_corpo={})
        if r.status in (200, 201, 204):
            return ""
        raise Recusa(_frase(r.corpo) or
                     f"A Parcela Express recusou o cancelamento (HTTP {r.status}).")


def _service_id(c: Mapping[str, Any]) -> str:
    """Até 10 letras ou números, como a maquininha exige."""
    bruto = re.sub(r"[^A-Za-z0-9]", "", str(c.get("seu_numero") or "CG"))
    return (bruto or "CG")[:10]


def _centavos(valor: Any) -> int | None:
    """Inteiro da Parcela Express é centavo. Texto com ponto é real."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        from decimal import Decimal
        numero = Decimal(str(valor))
        return int(numero) if numero.is_finite() and numero == numero.to_integral_value() else None
    texto = str(valor).strip()
    if texto.isdigit():
        return int(texto)
    return CB.centavos_do_banco(valor)


def urllib_quote(valor: str) -> str:
    import urllib.parse
    return urllib.parse.quote(str(valor or ""), safe="")


def ler(corpo: Mapping[str, Any]) -> dict:
    """A consulta do link → a forma comum de `cobranca.gravar_resposta`."""
    venda = corpo.get("sale") if isinstance(corpo.get("sale"), dict) else {}
    status_venda = str(venda.get("status") or "").upper()
    status_link = str(corpo.get("status") or "").upper()
    forma_bruta = str(venda.get("form_payment") or venda.get("type") or "").upper()
    saida = {
        "banco_status": status_venda or status_link,
        "banco_id": str(corpo.get("token") or corpo.get("id") or ""),
        "link_pagamento": str(corpo.get("url") or ""),
        "linha_digitavel": _primeiro(corpo, "barcode", "linha_digitavel", "linhaDigitavel"),
        "codigo_barras": _primeiro(corpo, "barcode_raw", "codBarras"),
        "pix_copia_e_cola": _primeiro(corpo, "qrcode_data", "qrCodeData", "pixCopiaECola"),
        "nosso_numero": _primeiro(corpo, "nosso_numero", "nossoNumero"),
    }
    if status_venda in SITUACAO_PAGA or status_link == "PAID":
        # Link pago sem venda liquidada, método, data ou valor não é prova
        # suficiente para gerar caixa. Não usar data de consulta nem BOLETO por padrão.
        from datetime import datetime
        forma = FORMA.get(forma_bruta)
        # amount é o valor da venda. original_amount pode incluir acréscimos
        # ao pagador. O link e a venda devem bater com o principal cadastrado.
        valor = _centavos(venda.get("amount"))
        quando = str(venda.get("updated_at") or "")
        try:
            dt = datetime.fromisoformat(quando.replace("Z", "+00:00"))
        except ValueError:
            raise Recusa("A Parcela informou pagamento sem data válida de liquidação.") from None
        if not venda.get("id") or status_venda not in SITUACAO_PAGA or not forma or not valor or valor <= 0:
            raise Recusa("A Parcela informou pagamento sem os dados da venda liquidada. Confira no portal.")
        if dt.tzinfo is not None:
            from datetime import timedelta, timezone
            dt = dt.astimezone(timezone(timedelta(hours=-3)))
        saida["situacao"] = CB.RECEBIDA
        saida["banco_pagamento_id"] = str(venda["id"])
        saida["forma_recebida"] = forma
        saida["valor_recebido"] = valor
        saida["data_pagamento"] = dt.date().isoformat()
        original = _centavos(venda.get("original_amount"))
        if original is not None and original != valor:
            from caixa_schema import reais
            saida["banco_motivo"] = (f"Valor da venda: R$ {reais(valor)}; campo original_amount da Parcela: "
                                     f"R$ {reais(original)}. Diferença fora do principal da cobrança: "
                                     f"R$ {reais(original - valor)}; não somada ao recebimento.")
    elif status_venda in SITUACAO_CANCELADA or status_link in SITUACAO_CANCELADA:
        saida["situacao"] = CB.CANCELADA
    elif status_venda in SITUACAO_BAIXADA or status_link in SITUACAO_BAIXADA:
        saida["situacao"] = CB.BAIXADA
    elif status_link in ("ACTIVE", "PENDING", "") or status_venda in ("PENDING", "WAITING", ""):
        saida["situacao"] = CB.ABERTA
    return saida


def cliente_da_casa(cfg: Mapping[str, str], *, pasta: Any = None,
                    transporte: Transporte | None = None) -> ClienteCobrancaParcela:
    return ClienteCobrancaParcela(cfg.get("cobranca_ambiente") or "sandbox",
                                  transporte or transporte_https(), credencial(pasta))
