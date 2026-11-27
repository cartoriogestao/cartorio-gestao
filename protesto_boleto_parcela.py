# -*- coding: utf-8 -*-
"""A COBRANÇA DO DEVEDOR PELA PARCELA EXPRESS — o boleto híbrido da intimação.

POR QUE EXISTE (PR007, 24 e 25/11/2026)
    Pedido do oficial: «Preciso que as intimações já saiam com boleto e Pix
    junto para pagamento», pela Parcela Express — a mesma conta que o caixa já
    usa (`cobranca_parcela`). Em 25/11 veio a régua que decide a forma: o
    boleto tem de sair JÁ EMITIDO, «importante para aparecer nos avisos da
    conta bancária do devedor» (o DDA), e a taxa fica com quem paga, «sem
    onerar o cartório».

POR QUE O BOLETO HÍBRIDO, E NÃO O LINK
    A primeira versão (#519) criava um link de pagamento (`POST
    /v1/payment-links`). O link não registra boleto nenhum: a Parcela só o
    gera quando o devedor abre o link e escolhe «boleto» — das 7 cobranças do
    caixa pagas por boleto pelo link até 25/11, nenhuma tinha linha digitável
    gravada. Sem boleto registrado no CPF/CNPJ do devedor, nada aparece no DDA.

    O contrato (OpenAPI v2 do sandbox, lida em 25/11/2026) tem o BOLETO
    HÍBRIDO: `POST /v2/billets/{sellerId}/hybrid`, um boleto registrado com o
    QR do Pix no mesmo documento. Continua UMA cobrança só — paga por linha
    digitável ou por Pix —, que é a regra de `cobranca_parcela`: nunca um
    boleto e um Pix separados. E deixa o CARTÃO de fora: no cartão a Parcela
    desconta a taxa do valor (crédito à vista 2,89% na maquininha), e quem
    pagaria seria o cartório.

    - Emitir: POST /v2/billets/{sellerId}/hybrid  [ {value, social_security_number,
      shopper_statement, description, delivery_date, shopper{first_name,
      last_name, billing_address}, protocol, instructions, metadata} ]
      → [ {id, url (o PDF), barcode, barcode_raw, billet_data{qrcode_data,
      nosso_numero, valor}, status, sale_id, metadata} ]
    - Consultar: GET /v1/billets/{id} → o mesmo boleto, com o status.
    - A venda paga: GET /v1/sellers/{sellerId}/sales/{saleId} — a mesma que o
      caixa lê (`cobranca_parcela.ler`).
    - Procurar: GET /v1/sellers/{sellerId}/billets (paginado), pelo `metadata`.
    - Baixar: POST /v1/billets/{sellerId}/{billetId}/void.
    - Pagar no SANDBOX: POST /v1/billets/{billetId}/pay («em ambiente de
      desenvolvimento») — só a cobrança de teste usa.

O VALOR É CONFERIDO NA LINHA DIGITÁVEL
    O contrato não diz se `value` é centavo ou real (a Parcela usa centavo no
    link e na venda, e real na maquininha). A linha digitável diz: os dez
    últimos dígitos são o valor do documento, em centavos (FEBRABAN). Se a
    linha voltar com um valor que não é o pedido — nem o pedido com a taxa
    do boleto por cima, até `TETO_DA_TAXA_DO_DEVEDOR` —, o boleto é BAIXADO na
    hora e a emissão recusada: boleto de valor errado na mão do devedor é
    pior que boleto nenhum.

    A diferença entre a linha e o pedido é a TAXA QUE O DEVEDOR PAGA, e fica
    na `resposta` (`taxa_do_devedor_centavos`): é a prova de que a taxa não
    sai dos emolumentos. Zero quer dizer que a Parcela desconta do cartório —
    e então a «tarifa repassada ao devedor» do Gestor (CN-MA art. 925, § 5º)
    é que a põe no valor.

A BAIXA É POR CONSULTA, UM A UM
    A busca recebe a lista dos nossos (`PEDE_OS_NOSSOS`) e consulta cada
    boleto; o pago traz a venda, e a venda é lida como no caixa. O evento é a
    VENDA (`sale.id`) — a mesma venda devolvida duas vezes entra uma.

O AMBIENTE
    HOMOLOGAÇÃO fala com o SANDBOX da Parcela; PRODUÇÃO, com a produção.

A CHAMADA NUNCA ACONTECE DENTRO DE `db.transaction()` — regra de `boleto_api`.
"""
from __future__ import annotations

import json
from typing import Any

import boleto_api as BAPI
import cobranca as CB
import cobranca_parcela as CP
from cobranca_banco import BancoError, Recusa

AMBIENTE_DA_PARCELA = {"HOMOLOGACAO": "sandbox", "PRODUCAO": "producao"}
LIMITE_DE_PAGINAS = 1000
#: A taxa do boleto que a Parcela soma por cima (plano AA18: R$ 1,10). Acima
#: disto, a linha digitável com valor diferente do pedido é erro, e não taxa.
TETO_DA_TAXA_DO_DEVEDOR = 500
#: A marca no `metadata` do boleto: é por ela que se acha o boleto sem resposta.
CHAVE_DO_METADATA = "protesto"
SITUACAO_DO_BOLETO_PAGA = frozenset({"SUCCEEDED", "PAID", "CAPTURED", "PAID_OUT"})
SITUACAO_DO_BOLETO_MORTA = CP.SITUACAO_CANCELADA | frozenset(
    {"EXPIRED", "FAILED", "ABORT", "REFUSED"})


def _erro(erro: Exception) -> BAPI.BoletoError:
    """A recusa da Parcela na língua do boleto do protesto."""
    if isinstance(erro, Recusa):
        return BAPI.BoletoRecusado(str(erro))
    return BAPI.BoletoError(str(erro))


def _reais(centavos: int) -> str:
    from caixa_schema import reais
    return reais(int(centavos))


def valor_da_linha(linha: Any) -> int | None:
    """O valor do documento na linha digitável (47 dígitos), em centavos. Só calcula."""
    digitos = CB.digitos(linha)
    if len(digitos) != 47:
        return None
    return int(digitos[-10:])


def _metadata(boleto: dict) -> dict:
    meta = boleto.get("metadata")
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except ValueError:
            meta = {}
    return meta if isinstance(meta, dict) else {}


class BancoParcela:
    """O transporte do boleto do devedor pela Parcela Express (boleto híbrido)."""

    E_SIMULADOR = False
    # A busca de pagamentos manda a lista dos nossos (`protesto_boleto`).
    PEDE_OS_NOSSOS = True
    CANCELA_COM_MOTIVO = True
    PAGA_POR_LINK = False
    # O sandbox paga o boleto pela API: a cobrança de teste usa.
    PAGA_NO_SANDBOX = True

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

    def _seller(self) -> str:
        return CP.urllib_quote(self.cliente()._campos["seller_id"])

    def _ir(self, metodo: str, caminho: str, **kw):
        try:
            return self.cliente()._ir(metodo, caminho, **kw)
        except BancoError as erro:
            raise _erro(erro) from erro

    @staticmethod
    def _falha(r, padrao: str) -> BAPI.BoletoError:
        if r.status >= 500 or r.status == 429:
            return BAPI.BoletoError(f"{padrao} (HTTP {r.status}).")
        return BAPI.BoletoRecusado(CP._frase(r.corpo) or f"{padrao} (HTTP {r.status}).")

    # ------------------------------------------------------------ a forma

    def corpo(self, pedido: dict) -> dict:
        """O pedido do protesto na forma do boleto híbrido. Só calcula."""
        p = BAPI.conferir_pedido(pedido)
        pagador = dict(p.get("pagador") or {})
        nome = " ".join(str(pagador.get("nome") or "").split())
        primeiro, _, resto = nome.partition(" ")
        ident = str(p.get("identificador") or "").strip()
        mensagem = CB._texto(p.get("mensagem") or f"Protesto {ident}", 180)
        return {
            "value": int(p["valor_centavos"]),
            "social_security_number": CB.digitos(pagador.get("documento")),
            "shopper_statement": CB._texto(f"Protesto {ident}", 22),
            "description": mensagem,
            "instructions": mensagem,
            # Meio-dia em UTC: a data do vencimento não escorrega de dia no fuso.
            "delivery_date": f"{str(p['vencimento'])[:10]}T12:00:00.000Z",
            "protocol": ident,
            "shopper": {
                "first_name": CB._texto(primeiro, 40),
                "last_name": CB._texto(resto or primeiro, 80),
                "billing_address": {
                    "street": CB._texto(pagador.get("endereco"), 80),
                    "house_number_or_name": "S/N",
                    "district": CB._texto(pagador.get("bairro") or "Não informado", 40),
                    "city": CB._texto(pagador.get("cidade"), 40),
                    "state_or_province": CB._texto(pagador.get("uf"), 2).upper(),
                    "postal_code": CB.digitos(pagador.get("cep"))[:8],
                },
            },
            "metadata": {CHAVE_DO_METADATA: ident},
        }

    @staticmethod
    def _do_boleto(boleto: dict, *, pedido_centavos: int | None = None) -> dict:
        """O que o protesto guarda de um boleto da Parcela. Só calcula."""
        dados = boleto.get("billet_data") if isinstance(boleto.get("billet_data"), dict) else {}
        linha = str(boleto.get("barcode") or "").strip()
        resposta = {"id": boleto.get("id"), "status": boleto.get("status"),
                    "sale_id": boleto.get("sale_id"),
                    "nosso_numero_do_banco": dados.get("nosso_numero"),
                    "banco": dados.get("banco"),
                    "expira_em": boleto.get("expires_at")}
        no_papel = valor_da_linha(linha)
        if no_papel is not None:
            resposta["valor_da_linha_centavos"] = no_papel
            if pedido_centavos is not None:
                resposta["taxa_do_devedor_centavos"] = no_papel - int(pedido_centavos)
        return {"nosso_numero": str(boleto.get("id") or "").strip(),
                "id_no_provedor": str(boleto.get("id") or "").strip(),
                "linha_digitavel": linha,
                "codigo_barras": str(boleto.get("barcode_raw") or "").strip(),
                "pix_copia_e_cola": str(dados.get("qrcode_data") or "").strip(),
                # O endereço do PDF do boleto, para a tela; o papel imprime a
                # linha e o QR do Pix.
                "link_pagamento": str(boleto.get("url") or "").strip(),
                "situacao": str(boleto.get("status") or "").upper(),
                "resposta": {k: v for k, v in resposta.items() if v is not None}}

    # -------------------------------------------------------------- verbos

    def registrar(self, pedido: dict) -> dict:
        """Emite o boleto híbrido e confere o valor da linha. ESCREVE LÁ."""
        corpo = self.corpo(pedido)
        r = self._ir("POST", f"/v2/billets/{self._seller()}/hybrid", json_corpo=[corpo])
        if r.status not in (200, 201):
            raise self._falha(r, "A Parcela Express não emitiu o boleto")
        lista = r.corpo if isinstance(r.corpo, list) else [r.corpo]
        boletos = [b for b in lista if isinstance(b, dict) and b.get("id")]
        if len(boletos) != 1:
            # Pedido um, voltaram zero ou vários: a resposta não se lê com
            # segurança. Fica SEM RESPOSTA (quem chama), para conferir.
            raise BAPI.BoletoError("A Parcela respondeu à emissão sem um boleto só.")
        registro = self._do_boleto(boletos[0], pedido_centavos=corpo["value"])
        if not registro["linha_digitavel"]:
            try:
                lido = self.ler_registro(registro["nosso_numero"])
            except BAPI.BoletoError:
                lido = None
            if lido and lido.get("linha_digitavel"):
                lido["resposta"] = {**registro["resposta"], **lido["resposta"]}
                no_papel = valor_da_linha(lido["linha_digitavel"])
                if no_papel is not None:
                    lido["resposta"]["taxa_do_devedor_centavos"] = no_papel - corpo["value"]
                registro = lido
        self._conferir_valor(registro, corpo["value"])
        return registro

    def _conferir_valor(self, registro: dict, pedido: int) -> None:
        no_papel = valor_da_linha(registro.get("linha_digitavel"))
        if no_papel is None or 0 <= no_papel - int(pedido) <= TETO_DA_TAXA_DO_DEVEDOR:
            return
        motivo = (f"a linha digitável da Parcela traz R$ {_reais(no_papel)}, e o boleto "
                  f"pedido era de R$ {_reais(pedido)}")
        try:
            self.cancelar(registro["nosso_numero"], "valor divergente do pedido")
        except BAPI.BoletoError as erro:
            raise BAPI.BoletoError(
                f"{motivo}. A baixa automática falhou ({erro}): baixe o boleto "
                f"{registro['nosso_numero']} no portal da Parcela.") from erro
        raise BAPI.BoletoRecusado(f"{motivo}. O boleto foi baixado na hora.")

    def ler_registro(self, nosso_numero: Any) -> dict | None:
        """O boleto como a Parcela o tem agora, ou None. LÊ LÁ."""
        ident = str(nosso_numero or "").strip()
        if not ident:
            return None
        r = self._ir("GET", f"/v1/billets/{CP.urllib_quote(ident)}")
        if r.status == 404:
            return None
        if r.status not in (200, 201) or not isinstance(r.corpo, dict):
            raise self._falha(r, "A Parcela Express não consultou o boleto")
        return self._do_boleto(r.corpo)

    def _boletos(self) -> list[dict]:
        """Todos os boletos do estabelecimento, página por página. LÊ LÁ."""
        todos: list[dict] = []
        for pagina in range(1, LIMITE_DE_PAGINAS + 1):
            r = self._ir("GET", f"/v1/sellers/{self._seller()}/billets"
                                f"?limit=100&current_page={pagina}")
            if r.status != 200 or not isinstance(r.corpo, dict):
                raise self._falha(r, "A Parcela Express não listou os boletos")
            linhas = r.corpo.get("results")
            if not isinstance(linhas, list) or any(not isinstance(v, dict) for v in linhas):
                raise BAPI.BoletoError("A Parcela devolveu uma lista de boletos incompleta.")
            todos.extend(linhas)
            if r.corpo.get("has_more") is False:
                return todos
            try:
                total, atual = int(r.corpo["total_pages"]), int(r.corpo["current_page"])
            except (KeyError, ValueError, TypeError):
                raise BAPI.BoletoError("A Parcela não informou a paginação completa.") from None
            if atual != pagina or total < pagina:
                raise BAPI.BoletoError("A paginação da Parcela está inconsistente.")
            if pagina == total:
                return todos
        raise BAPI.BoletoError("A lista da Parcela passou do limite de páginas.")

    def consultar(self, identificador: Any) -> dict | None:
        """O boleto daquele «seu número» (`PT<título>-<n>`), ou None. LÊ LÁ.

        **Se a Parcela não devolve o `metadata` dos boletos, não se diz «não
        tem»** — recusa, porque None libera outra cobrança e o devedor veria
        duas.
        """
        alvo = str(identificador or "").strip()
        boletos = self._boletos()
        if boletos and not any("metadata" in b for b in boletos):
            raise BAPI.BoletoError(
                "A Parcela não devolve o metadata dos boletos, e sem ele não dá para "
                "saber se a cobrança foi emitida. Confira no portal da Parcela.")
        achados = [b for b in boletos if str(_metadata(b).get(CHAVE_DO_METADATA) or "") == alvo]
        vivos = [b for b in achados
                 if str(b.get("status") or "").upper() not in SITUACAO_DO_BOLETO_MORTA]
        if len(vivos) > 1:
            raise BAPI.BoletoError(
                f"A Parcela tem mais de um boleto vivo de «{alvo}». Baixe o que sobra "
                f"no portal antes de continuar.")
        if not achados:
            return None
        return self._do_boleto((vivos or achados)[0])

    def cancelar(self, nosso_numero: Any, motivo: str = "") -> dict:
        """Baixa o boleto. ESCREVE LÁ. Boleto pago não se baixa."""
        ident = str(nosso_numero or "").strip()
        r = self._ir("POST", f"/v1/billets/{self._seller()}/{CP.urllib_quote(ident)}/void")
        if r.status not in (200, 201, 204):
            raise self._falha(r, "A Parcela Express não baixou o boleto")
        return {"nosso_numero": ident, "situacao": "CANCELADO"}

    def _venda(self, venda_id: str) -> dict | None:
        r = self._ir("GET", f"/v1/sellers/{self._seller()}/sales/{CP.urllib_quote(venda_id)}")
        if r.status == 404:
            return None
        if r.status != 200 or not isinstance(r.corpo, dict):
            raise self._falha(r, "A Parcela Express não consultou a venda")
        return r.corpo

    def liquidacoes(self, desde: str, ate: str, *, nossos: Any = None) -> list[dict]:
        """Os boletos PAGOS desta casa no período, consultados um a um. LÊ LÁ."""
        self.avisos = []
        de, a = str(desde or "")[:10], str(ate or "")[:10]
        fora: list[dict] = []
        for nosso in sorted({str(n).strip() for n in (nossos or []) if str(n or "").strip()}):
            try:
                r = self._ir("GET", f"/v1/billets/{CP.urllib_quote(nosso)}")
                if r.status not in (200, 201) or not isinstance(r.corpo, dict):
                    raise self._falha(r, "A Parcela Express não consultou o boleto")
                boleto = r.corpo
                if str(boleto.get("status") or "").upper() not in SITUACAO_DO_BOLETO_PAGA:
                    continue
                venda = self._venda(str(boleto["sale_id"])) if boleto.get("sale_id") else None
            except BAPI.BoletoError as erro:
                self.avisos.append(f"Boleto {nosso}: {erro}")
                continue
            if not venda:
                self.avisos.append(f"Boleto {nosso}: a Parcela diz pago, sem a venda. "
                                   "Confira no portal.")
                continue
            try:
                lido = CP.ler({"status": "paid", "sale": venda})
            except Recusa as erro:
                self.avisos.append(f"Boleto {nosso}: {erro}")
                continue
            pago_em = str(lido.get("data_pagamento") or "")[:10]
            if lido.get("situacao") != CB.RECEBIDA or not (de <= pago_em <= a):
                continue
            fora.append({"evento_id": "VENDA:" + str(lido["banco_pagamento_id"]),
                         "nosso_numero": nosso,
                         "valor_pago_centavos": int(lido["valor_recebido"]),
                         "pago_em": pago_em, "creditado_em": pago_em,
                         "forma": lido.get("forma_recebida") or ""})
        return fora

    def pagar_no_sandbox(self, nosso_numero: Any) -> None:
        """O devedor do SANDBOX pagando. Recusa fora do sandbox. ESCREVE LÁ."""
        if AMBIENTE_DA_PARCELA.get(self.ambiente) != "sandbox":
            raise BAPI.BoletoError("Só se paga pela API no sandbox da Parcela.")
        r = self._ir("POST", f"/v1/billets/{CP.urllib_quote(str(nosso_numero or ''))}/pay")
        if r.status not in (200, 201, 204):
            raise self._falha(r, "O sandbox da Parcela não pagou o boleto")

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
