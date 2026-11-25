# -*- coding: utf-8 -*-
"""O BOLETO DO DEVEDOR PELO BANCO INTER OU PELA UNICRED — os adaptadores do caixa.

POR QUE EXISTE (PR007, 25/11/2026)
    Pedido do oficial: a intimação sai com o boleto JÁ REGISTRADO (para cair
    no DDA do banco do devedor), com o Pix junto, e a casa escolhe «oportuna-
    mente o mais vantajoso» entre a Parcela Express, a Unicred e o Banco Inter.

    O caixa já fala com os dois bancos (`cobranca_inter`, `cobranca_unicred`),
    pelo contrato comum de `cobranca_banco`: `emitir`, `consultar`, `procurar`,
    `cancelar`. Este módulo é o TRANSPORTE do boleto do protesto
    (`boleto_api`) por cima deles — a mesma credencial, os mesmos endereços,
    a mesma leitura da resposta. Escrever outro cliente seria uma segunda
    versão da parte que decide se o devedor recebe um boleto ou dois.

UM BOLETO SÓ, COM PIX DENTRO
    O Inter emite o «Boleto com Pix» (`formasRecebimento: BOLETO e PIX`) e a
    Unicred devolve o `qrCodePix` na consulta do título: é UMA cobrança
    registrada, paga por linha digitável ou por Pix, e não duas.

A EMISSÃO É ASSÍNCRONA NOS DOIS
    O banco devolve o número da solicitação (Inter) ou o id do título
    (Unicred); a linha digitável e o Pix chegam quando o registro na CIP
    termina. `registrar` consulta algumas vezes, curtas; o que não chegou
    `ler_registro` busca depois (`protesto_boleto.completar_linha`, chamado
    antes de imprimir o aviso).

    O NOSSO NÚMERO DESTA CASA É O ID DO BANCO (codigoSolicitacao ou id_titulo):
    é por ele que se consulta, cancela e concilia. O nosso número FEBRABAN do
    banco vai na `resposta`.

A BAIXA É POR CONSULTA, UM A UM
    Nenhum dos dois tem, nos documentos, «liquidações do período» de que este
    sistema dependa. A busca recebe a lista dos nossos (`PEDE_OS_NOSSOS`) e
    consulta cada um. O evento é «<BANCO>:<id>» — um boleto se paga uma vez.
    A consulta que falha vira AVISO e o boleto fica para a próxima busca.

A CONFERÊNCIA DO QUE FICOU SEM RESPOSTA
    O Inter procura pelo «seu número»; a Unicred não tem essa busca nos
    documentos (`cobranca_unicred.procurar` devolve None). **Sem busca não se
    diz «não tem»** — recusa, porque «não tem» libera outra cobrança e o
    devedor veria duas.

O AMBIENTE
    HOMOLOGAÇÃO fala com o sandbox/homologação do banco; PRODUÇÃO, com a
    produção. A credencial é a do caixa (Cobrança → Configuração e
    Administrativo → Configurações), e a do teste é outra: o banco recusa a
    de produção no sandbox.

A CHAMADA NUNCA ACONTECE DENTRO DE `db.transaction()` — regra de `boleto_api`.
"""
from __future__ import annotations

import json
import time
from datetime import date, timedelta
from typing import Any, Callable

import boleto_api as BAPI
import cobranca as CB
from cobranca_banco import BancoError, Recusa

AMBIENTE_DO_BANCO = {"HOMOLOGACAO": "sandbox", "PRODUCAO": "producao"}
#: Quantas vezes `registrar` pergunta pela linha digitável, e a pausa entre elas.
TENTATIVAS_DA_LINHA = 3
PAUSA_DA_LINHA = 2.0
#: A janela da busca pelo «seu número» (Inter: as datas são obrigatórias).
JANELA_DA_BUSCA_DIAS = 60

NOMES = {CB.INTER: "Banco Inter", CB.UNICRED: "Unicred"}


def _erro(erro: Exception) -> BAPI.BoletoError:
    """A recusa do banco na língua do boleto do protesto."""
    if isinstance(erro, Recusa):
        return BAPI.BoletoRecusado(str(erro))
    return BAPI.BoletoError(str(erro))


class BancoDaCobranca:
    """O transporte do boleto do devedor por um adaptador de `cobranca_banco`."""

    E_SIMULADOR = False
    PEDE_OS_NOSSOS = True
    CANCELA_COM_MOTIVO = True
    PAGA_POR_LINK = False

    def __init__(self, banco: str, ambiente: Any = "HOMOLOGACAO", pasta: Any = None, *,
                 cliente: Any = None, transporte: Any = None,
                 dormir: Callable[[float], None] = time.sleep,
                 hoje: Callable[[], date] = date.today):
        if banco not in NOMES:
            raise BAPI.BoletoError(f"Banco sem transporte do protesto: «{banco}».")
        self.banco = banco
        self.nome = NOMES[banco]
        self.ambiente = str(ambiente or "HOMOLOGACAO").upper()
        self.pasta = pasta
        self._cliente = cliente
        self._transporte = transporte
        self._dormir = dormir
        self._hoje = hoje
        self.avisos: list[str] = []

    # ------------------------------------------------------------ o cliente

    def cliente(self):
        """O adaptador do caixa, com a credencial do caixa. Criado na 1ª chamada."""
        if self._cliente is None:
            import cobranca_banco
            cfg = {"cobranca_ambiente": AMBIENTE_DO_BANCO.get(self.ambiente, "sandbox")}
            try:
                self._cliente = cobranca_banco.cliente_da_casa(
                    cfg, banco_codigo=self.banco, pasta=self.pasta,
                    transporte=self._transporte)
            except (BancoError, CB.CobrancaError) as erro:
                raise BAPI.BoletoError(f"{self.nome}: {erro}") from erro
        return self._cliente

    # ------------------------------------------------------------ a forma

    @staticmethod
    def _c(pedido: dict) -> dict:
        """O pedido do protesto na forma de uma linha de `cb_cobrancas`. Só calcula."""
        p = BAPI.conferir_pedido(pedido)
        pagador = dict(p.get("pagador") or {})
        endereco = {"logradouro": str(pagador.get("endereco") or "").strip(),
                    "bairro": str(pagador.get("bairro") or "").strip(),
                    "cidade": str(pagador.get("cidade") or "").strip(),
                    "uf": str(pagador.get("uf") or "").strip().upper(),
                    "cep": CB.digitos(pagador.get("cep"))}
        return {"valor": int(p["valor_centavos"]),
                "vencimento": str(p["vencimento"])[:10],
                "pagador_nome": str(pagador.get("nome") or "").strip(),
                "pagador_documento": CB.digitos(pagador.get("documento")),
                "pagador_endereco": json.dumps(
                    {k: v for k, v in endereco.items() if v}, ensure_ascii=False),
                "pagador_email": "",
                "mensagem": p.get("mensagem") or "",
                "seu_numero": str(p.get("identificador") or "")[:CB.LIMITE_SEU_NUMERO],
                # O protesto não recebe depois do prazo: o título é lavrado.
                "dias_apos_vencimento": 0}

    def _registro(self, banco_id: str, lido: dict | None) -> dict:
        lido = lido or {}
        return {"nosso_numero": banco_id, "id_no_provedor": banco_id,
                "linha_digitavel": lido.get("linha_digitavel") or "",
                "codigo_barras": lido.get("codigo_barras") or "",
                "pix_copia_e_cola": lido.get("pix_copia_e_cola") or "",
                "link_pagamento": "",
                "situacao": lido.get("situacao") or CB.EMITINDO,
                "resposta": {"banco": self.banco,
                             "banco_status": lido.get("banco_status") or "",
                             "nosso_numero_do_banco": lido.get("nosso_numero") or ""}}

    # -------------------------------------------------------------- verbos

    def registrar(self, pedido: dict) -> dict:
        """Emite o boleto com Pix e espera a linha um pouco. ESCREVE LÁ."""
        c = self._c(pedido)
        cli = self.cliente()
        try:
            banco_id = str(cli.emitir(c) or "").strip()
        except BancoError as erro:
            raise _erro(erro) from erro
        if not banco_id:
            raise BAPI.BoletoError(f"O {self.nome} aceitou e não disse o número do boleto.")
        lido = None
        for vez in range(TENTATIVAS_DA_LINHA):
            if vez:
                self._dormir(PAUSA_DA_LINHA)
            try:
                lido = cli.consultar({**c, "banco_id": banco_id})
            except BancoError:
                # O boleto foi pedido e o banco tem o número: a linha vem depois.
                lido = None
            if lido and lido.get("linha_digitavel"):
                break
        return self._registro(banco_id, lido)

    def ler_registro(self, nosso_numero: Any) -> dict | None:
        """A linha e o Pix que o banco já gerou, ou None se ainda processa. LÊ LÁ."""
        banco_id = str(nosso_numero or "").strip()
        if not banco_id:
            return None
        try:
            lido = self.cliente().consultar({"banco_id": banco_id})
        except BancoError as erro:
            raise _erro(erro) from erro
        return self._registro(banco_id, lido) if lido else None

    def consultar(self, identificador: Any) -> dict | None:
        """O boleto daquele «seu número», ou None. LÊ LÁ."""
        seu = str(identificador or "").strip()[:CB.LIMITE_SEU_NUMERO]
        hoje = self._hoje()
        try:
            achado = self.cliente().procurar(
                {"seu_numero": seu},
                data_inicial=(hoje - timedelta(days=JANELA_DA_BUSCA_DIAS)).isoformat(),
                data_final=hoje.isoformat())
        except BancoError as erro:
            raise _erro(erro) from erro
        if achado is None and self.banco == CB.UNICRED:
            raise BAPI.BoletoError(
                "A Unicred não procura boleto pelo seu número, e sem essa busca não dá "
                f"para saber se «{seu}» foi registrado. Confira no internet banking da "
                "cooperativa antes de emitir outro.")
        if not achado:
            return None
        return self.ler_registro(achado) or self._registro(str(achado), None)

    def cancelar(self, nosso_numero: Any, motivo: str = "") -> dict:
        """Pede a baixa do boleto. ESCREVE LÁ. Na Unicred é um PEDIDO (assíncrono)."""
        try:
            instrucao = self.cliente().cancelar({"banco_id": str(nosso_numero or "")},
                                                motivo or "cancelado no protesto")
        except BancoError as erro:
            raise _erro(erro) from erro
        return {"nosso_numero": str(nosso_numero or ""), "situacao": "CANCELADO",
                "instrucao": instrucao or ""}

    def liquidacoes(self, desde: str, ate: str, *, nossos: Any = None) -> list[dict]:
        """Os boletos PAGOS desta casa no período, consultados um a um. LÊ LÁ."""
        self.avisos = []
        de, a = str(desde or "")[:10], str(ate or "")[:10]
        fora: list[dict] = []
        for nosso in sorted({str(n).strip() for n in (nossos or []) if str(n or "").strip()}):
            try:
                lido = self.cliente().consultar({"banco_id": nosso})
            except BancoError as erro:
                self.avisos.append(f"Boleto {nosso}: {erro}")
                continue
            if not lido or lido.get("situacao") != CB.RECEBIDA:
                continue
            valor = lido.get("valor_recebido")
            pago_em = str(lido.get("data_pagamento") or "")[:10]
            if not valor or not pago_em:
                self.avisos.append(f"Boleto {nosso}: o {self.nome} diz pago, sem o valor "
                                   "ou a data. Confira no internet banking.")
                continue
            if not (de <= pago_em <= a):
                continue
            fora.append({"evento_id": f"{self.banco}:{nosso}", "nosso_numero": nosso,
                         "valor_pago_centavos": int(valor), "pago_em": pago_em,
                         "creditado_em": pago_em,
                         "forma": "PIX" if str(lido.get("forma_recebida") or "").upper()
                         == "PIX" else "BOLETO"})
        return fora

    def diagnostico(self) -> dict:
        try:
            cli = self.cliente()
            token = getattr(cli, "token", None) or getattr(getattr(cli, "_c", None), "token")
            token()
        except (BancoError, BAPI.BoletoError, AttributeError) as erro:
            return {"ok": False, "motivo": f"{self.nome}: {erro}"}
        except Exception as erro:  # o adaptador do Inter fala a língua das despesas
            return {"ok": False, "motivo": f"{self.nome}: {erro}"}
        return {"ok": True, "motivo": (
            f"{self.nome} ({AMBIENTE_DO_BANCO.get(self.ambiente, 'sandbox')}): "
            "autenticação aceita.")}


def fabrica(banco: str, ambiente: Any, pasta: Any) -> BancoDaCobranca:
    """O que `boleto_api.PROVEDORES` chama. Uma indireção para o teste trocar."""
    return BancoDaCobranca(banco, ambiente, pasta)
