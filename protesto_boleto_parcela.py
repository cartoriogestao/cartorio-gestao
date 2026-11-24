# -*- coding: utf-8 -*-
"""A COBRANÇA DO DEVEDOR PELA PARCELA EXPRESS — o link que vai com a intimação.

POR QUE EXISTE (PR007, 24/11/2026)
    Pedido do oficial: «Preciso que as intimações já saiam com boleto e Pix
    junto para pagamento», pela Parcela Express — a mesma conta que o caixa já
    usa (`cobranca_parcela`). Este módulo é o TRANSPORTE do boleto do devedor
    (`protesto_boleto`) para a Parcela: a mesma vaga que `boleto_api` deixou
    para o banco do convênio, com os quatro verbos que o protesto já usa —
    `registrar`, `consultar`, `cancelar` e `liquidacoes`.

UM LINK SÓ, COMO NO CAIXA
    A regra está escrita em `cobranca_parcela`: a Parcela cobra por um link
    com Pix, boleto e cartão (`POST /v1/payment-links`), e não se emite boleto
    e Pix separados — seriam duas cobranças do mesmo título, e o devedor
    pagaria as duas. Aqui a regra é a mesma: um link por cobrança, e o
    `protesto_boleto` garante um vivo por título (índice único parcial).

A LINHA DIGITÁVEL E O PIX NÃO VÊM NA CRIAÇÃO
    A criação devolve `{id, url, token, status}`. Logo depois de criar, o
    transporte CONSULTA o link uma vez (a lista do estabelecimento, a mesma de
    `cobranca_parcela`) e guarda o que vier: a linha digitável (`barcode`) e
    o Pix copia-e-cola (`qrcode_data`), quando a Parcela já os gerou. Quando
    não vêm — o boleto do link costuma nascer quando o devedor escolhe a
    forma no checkout —, o papel imprime o LINK e o QR do link
    (`protesto_boleto.bloco_de_pagamento`), e é por ele que se paga.

A BAIXA É POR LISTA, E SÓ DOS NOSSOS
    A Parcela não tem «liquidações do período». O transporte lê a lista de
    links do estabelecimento uma vez e devolve os PAGOS cujo id ou token é
    de um boleto desta casa (`PEDE_OS_NOSSOS`): os links do caixa
    (`cb_cobrancas`) moram na mesma conta e não são do protesto. O evento é a
    VENDA (`sale.id`) — a mesma venda devolvida duas vezes entra uma
    (`pt_boletos_liquidacoes`, índice único).

    O link pago com dado incompleto (sem venda, sem data, sem forma) não vira
    liquidação: vira AVISO na busca, para alguém olhar no portal.

O AMBIENTE
    HOMOLOGAÇÃO fala com o SANDBOX da Parcela; PRODUÇÃO, com a produção. O
    sandbox não tem dinheiro, e mesmo assim nada vale no livro: a homologação
    do `protesto_boleto` não dá baixa no título.

A CHAMADA NUNCA ACONTECE DENTRO DE `db.transaction()` — regra de
`boleto_api`, e quem chama (`protesto_boleto`) a cumpre.
"""
from __future__ import annotations

import json
from typing import Any

import boleto_api as BAPI
import cobranca as CB
import cobranca_parcela as CP
from cobranca_banco import BancoError, Indisponivel, Recusa

# O ambiente do protesto → a base da Parcela. Palavra desconhecida vai ao
# sandbox, como em `cobranca_parcela.ClienteCobrancaParcela`.
AMBIENTE_DA_PARCELA = {"HOMOLOGACAO": "sandbox", "PRODUCAO": "producao"}

# O título do link: é por ele que a busca acha o link que ficou sem resposta,
# e é ele que o portal da Parcela mostra. «Protesto» o separa dos do caixa.
PREFIXO_DO_TITULO = "Protesto"
LIMITE_DE_PAGINAS = 1000


def _titulo_do_link(identificador: str) -> str:
    return f"{PREFIXO_DO_TITULO} {identificador}".strip()


def _erro(erro: Exception) -> BAPI.BoletoError:
    """A recusa da Parcela na língua do boleto do protesto."""
    if isinstance(erro, Recusa):
        return BAPI.BoletoRecusado(str(erro))
    return BAPI.BoletoError(str(erro))


class BancoParcela:
    """O transporte do boleto do devedor pela Parcela Express."""

    E_SIMULADOR = False
    # A busca de pagamentos manda a lista dos nossos (`protesto_boleto`).
    PEDE_OS_NOSSOS = True
    # A tela diz que o pagamento é um link, e não um PDF.
    PAGA_POR_LINK = True

    def __init__(self, ambiente: Any = "HOMOLOGACAO", pasta: Any = None, *,
                 transporte: Any = None, campos: dict | None = None):
        self.ambiente = str(ambiente or "HOMOLOGACAO").upper()
        self.pasta = pasta
        self._transporte = transporte
        self._campos = campos
        self._cliente: CP.ClienteCobrancaParcela | None = None
        self.avisos: list[str] = []

    # ------------------------------------------------------------ o cliente

    def cliente(self) -> CP.ClienteCobrancaParcela:
        """O cliente da Parcela, criado na primeira chamada. A credencial é a
        do caixa (`cobranca_parcela.credencial`): a mesma conta."""
        if self._cliente is None:
            try:
                campos = self._campos if self._campos is not None \
                    else CP.credencial(self.pasta)
                self._cliente = CP.ClienteCobrancaParcela(
                    AMBIENTE_DA_PARCELA.get(self.ambiente, "sandbox"),
                    self._transporte or CP.transporte_https(), campos)
            except (BancoError, CB.CobrancaError) as erro:
                raise BAPI.BoletoError(f"Parcela Express: {erro}") from erro
        return self._cliente

    def _links(self) -> list[dict]:
        """Todos os links do estabelecimento, página por página. LÊ LÁ.

        A mesma régua de `ClienteCobrancaParcela._link_do_estabelecimento`:
        paginação incompleta ou inconsistente recusa — lista pela metade
        deixaria pagamento sem baixa sem ninguém saber.
        """
        cli = self.cliente()
        seller = cli._campos["seller_id"]
        todos: list[dict] = []
        for pagina in range(1, LIMITE_DE_PAGINAS + 1):
            caminho = (f"/v1/sellers/{CP.urllib_quote(seller)}/payment-links"
                       f"?limit=100&current_page={pagina}")
            try:
                r = cli._ir("GET", caminho)
            except BancoError as erro:
                raise _erro(erro) from erro
            if r.status >= 500 or r.status == 429:
                raise BAPI.BoletoError(
                    f"A Parcela Express não consultou (HTTP {r.status}).")
            if r.status != 200 or not isinstance(r.corpo, dict):
                raise BAPI.BoletoRecusado(
                    CP._frase(r.corpo) or "A Parcela recusou a consulta dos links.")
            linhas = r.corpo.get("results")
            if not isinstance(linhas, list) or any(not isinstance(v, dict) for v in linhas):
                raise BAPI.BoletoError("A Parcela devolveu uma lista de links incompleta.")
            for v in linhas:
                vendedor = v.get("seller") or {}
                if isinstance(vendedor, dict) and vendedor.get("id") and \
                        str(vendedor["id"]) != seller:
                    raise BAPI.BoletoError(
                        "A Parcela devolveu um link de outro estabelecimento.")
            todos.extend(linhas)
            if r.corpo.get("has_more") is False:
                return todos
            try:
                total = int(r.corpo["total_pages"])
                atual = int(r.corpo["current_page"])
            except (KeyError, ValueError, TypeError):
                raise BAPI.BoletoError(
                    "A Parcela não informou a paginação completa.") from None
            if atual != pagina or total < pagina:
                raise BAPI.BoletoError("A paginação da Parcela está inconsistente.")
            if pagina == total:
                return todos
        raise BAPI.BoletoError("A lista da Parcela passou do limite de páginas.")

    @staticmethod
    def _do_link(link: dict) -> dict:
        """O que o protesto guarda de um link. Só calcula. Os mesmos campos
        que `cobranca_parcela.ler` procura, sem decidir se está pago."""
        ident = str(link.get("token") or link.get("id") or "").strip()
        return {"nosso_numero": ident,
                "id_no_provedor": str(link.get("id") or ident),
                "linha_digitavel": CP._primeiro(link, "barcode", "linha_digitavel",
                                                "linhaDigitavel"),
                "codigo_barras": CP._primeiro(link, "barcode_raw", "codBarras"),
                "pix_copia_e_cola": CP._primeiro(link, "qrcode_data", "qrCodeData",
                                                 "pixCopiaECola"),
                "link_pagamento": str(link.get("url") or ""),
                "resposta": json.loads(CP.evidencia(link))}

    # -------------------------------------------------------------- verbos

    def corpo(self, pedido: dict) -> dict:
        """O pedido do protesto na forma da cobrança da Parcela. Só calcula."""
        p = BAPI.conferir_pedido(pedido)
        pagador = dict(p.get("pagador") or {})
        endereco = {"logradouro": pagador.get("endereco") or "",
                    "numero": "S/N", "bairro": pagador.get("bairro") or "",
                    "cidade": pagador.get("cidade") or "",
                    "uf": pagador.get("uf") or "",
                    "cep": CB.digitos(pagador.get("cep"))}
        c = {"valor": int(p["valor_centavos"]),
             "vencimento": str(p["vencimento"])[:10],
             "pagador_nome": pagador.get("nome") or "",
             "pagador_documento": CB.digitos(pagador.get("documento")),
             "pagador_endereco": json.dumps(endereco, ensure_ascii=False),
             "mensagem": p.get("mensagem") or "",
             "seu_numero": p.get("identificador") or ""}
        corpo = self.cliente().corpo(c)
        corpo["link_title"] = _titulo_do_link(str(p.get("identificador") or ""))
        return corpo

    def registrar(self, pedido: dict) -> dict:
        """Cria o link (Pix, boleto e cartão) e o lê de volta. ESCREVE LÁ."""
        corpo = self.corpo(pedido)
        cli = self.cliente()
        try:
            r = cli._ir("POST", "/v1/payment-links", json_corpo=corpo)
        except BancoError as erro:
            raise _erro(erro) from erro
        if r.status in (200, 201) and isinstance(r.corpo, dict):
            ident = str(r.corpo.get("token") or r.corpo.get("id") or "").strip()
            if ident:
                criado = self._do_link(r.corpo)
                # A LINHA E O PIX VÊM NA CONSULTA, quando vêm: lê-se uma vez,
                # já. Se a consulta falhar, o link está criado e vale — fica
                # o que a criação devolveu (o endereço do link).
                try:
                    achado = self._achar(ident)
                except BAPI.BoletoError:
                    achado = None
                if achado:
                    lido = self._do_link(achado)
                    criado.update({k: v for k, v in lido.items() if v})
                    criado["nosso_numero"] = ident
                return criado
        if r.status >= 500 or r.status == 429:
            raise BAPI.BoletoError(f"A Parcela Express não criou a cobrança (HTTP {r.status}).")
        raise BAPI.BoletoRecusado(
            CP._frase(r.corpo) or f"A Parcela Express recusou a cobrança (HTTP {r.status}).")

    def _achar(self, ident: str) -> dict | None:
        ident = str(ident or "").strip()
        if not ident:
            return None
        achados = [v for v in self._links()
                   if ident in (str(v.get("id") or ""), str(v.get("token") or ""))]
        if len(achados) > 1:
            raise BAPI.BoletoError("A Parcela devolveu o mesmo link duas vezes.")
        return achados[0] if achados else None

    def consultar(self, identificador: Any) -> dict | None:
        """O link daquele «seu número» (`PT<título>-<n>`), ou None. LÊ LÁ.

        É a conferência do boleto que ficou SEM RESPOSTA: procura pelo título
        do link. **Se a Parcela não devolve o título dos links, não se diz
        «não tem»** — recusa, porque None libera outra cobrança e o devedor
        veria duas.
        """
        alvo = _titulo_do_link(str(identificador or "").strip())
        links = self._links()
        if links and not any("link_title" in v or "title" in v for v in links):
            raise BAPI.BoletoError(
                "A Parcela não devolve o título dos links, e sem ele não dá para "
                "saber se a cobrança foi criada. Confira no portal da Parcela.")
        achados = [v for v in links
                   if str(v.get("link_title") or v.get("title") or "").strip() == alvo]
        vivos = [v for v in achados if str(v.get("status") or "").upper()
                 not in CP.SITUACAO_CANCELADA]
        if len(vivos) > 1:
            raise BAPI.BoletoError(
                f"A Parcela tem mais de um link «{alvo}» vivo. Cancele o que "
                f"sobra no portal antes de continuar.")
        if not achados:
            return None
        return self._do_link((vivos or achados)[0])

    def cancelar(self, nosso_numero: Any, motivo: str = "") -> dict:
        """Cancela o link. ESCREVE LÁ. Link pago não se cancela."""
        try:
            self.cliente().cancelar({"banco_id": str(nosso_numero or "")},
                                    motivo or "cancelado no protesto")
        except BancoError as erro:
            raise _erro(erro) from erro
        return {"nosso_numero": str(nosso_numero or ""), "situacao": "CANCELADO"}

    def liquidacoes(self, desde: str, ate: str, *, nossos: Any = None) -> list[dict]:
        """Os links PAGOS desta casa no período. LÊ LÁ.

        `nossos` é a lista dos nossos números que o protesto conhece; sem ela,
        nada volta (os links do caixa moram na mesma conta).
        """
        conhecidos = {str(n) for n in (nossos or []) if str(n or "").strip()}
        self.avisos = []
        if not conhecidos:
            return []
        de, a = str(desde or "")[:10], str(ate or "")[:10]
        fora: list[dict] = []
        for link in self._links():
            ids = {str(link.get("id") or ""), str(link.get("token") or "")} - {""}
            meu = sorted(ids & conhecidos)
            if not meu:
                continue
            try:
                lido = CP.ler(link)
            except Recusa as erro:
                self.avisos.append(f"Link {meu[0]}: {erro}")
                continue
            if lido.get("situacao") != CB.RECEBIDA:
                continue
            pago_em = str(lido.get("data_pagamento") or "")[:10]
            if not (de <= pago_em <= a):
                continue
            fora.append({"evento_id": "VENDA:" + str(lido["banco_pagamento_id"]),
                         "nosso_numero": meu[0],
                         "valor_pago_centavos": int(lido["valor_recebido"]),
                         "pago_em": pago_em, "creditado_em": pago_em,
                         "forma": lido.get("forma_recebida") or ""})
        return fora

    def diagnostico(self) -> dict:
        try:
            self.cliente()._token_de_acesso()
        except (BancoError, BAPI.BoletoError) as erro:
            return {"ok": False, "motivo": f"Parcela Express: {erro}"}
        return {"ok": True, "motivo": (
            f"Parcela Express ({AMBIENTE_DA_PARCELA.get(self.ambiente, 'sandbox')}): "
            "login aceito.")}


def fabrica(ambiente: Any, pasta: Any) -> BancoParcela:
    """O que `boleto_api.PROVEDORES` chama. Uma indireção para o teste trocar."""
    return BancoParcela(ambiente, pasta)
