"""A COBRANÇA PELO BANCO INTER — o «Boleto com Pix» da API Cobrança v3.

O CONTRATO (OpenAPI 3.0.3 servida em developers.inter.co,
`/redocusaurus/swagger-cobranca-bolepix-yaml.yaml`, lida em 27/10/2026)
    Base: `{host}/cobranca/v3`, nos mesmos dois hosts do Banking
    (`despesas_inter.ENDERECOS`), com o mesmo token mTLS de
    `POST /oauth/v2/token` — mas com OUTROS escopos: `boleto-cobranca.read` e
    `boleto-cobranca.write`. A integração da conta precisa ter os dois
    marcados no Internet Banking; sem eles o token é recusado.

    - Emitir: POST /cobrancas {seuNumero(15), valorNominal (NÚMERO, mínimo
      2,50), dataVencimento, numDiasAgenda (0 a 60), pagador{cpfCnpj,
      tipoPessoa FISICA|JURIDICA, nome, endereco, cidade, uf, cep, …},
      mensagem{linha1..5 (78)}, formasRecebimento} → 200 {codigoSolicitacao}.
      É ASSÍNCRONA: a cobrança nasce EM_PROCESSAMENTO.
    - Consultar: GET /cobrancas/{codigoSolicitacao} → {cobranca{situacao,
      valorTotalRecebido, origemRecebimento, dataSituacao…}, boleto{nossoNumero,
      linhaDigitavel(47), codigoBarras(44)}, pix{txid, pixCopiaECola}}.
    - Procurar: GET /cobrancas?dataInicial&dataFinal (OBRIGATÓRIOS) &seuNumero
      &filtrarDataPor=EMISSAO → {cobrancas: [...]} paginado.
    - PDF: GET /cobrancas/{codigoSolicitacao}/pdf → {pdf: base64}.
    - Cancelar: POST /cobrancas/{codigoSolicitacao}/cancelar
      {motivoCancelamento (50)} → 202.

    **O INTER RECUSA A DUPLICATA POR 30 MINUTOS.** A descrição da emissão diz
    que seuNumero + valorNominal + dataVencimento + cpfCnpj do pagador formam
    uma chave de idempotência de 30 minutos. É por isso que o reenvio de quem
    ficou sem resposta PROCURA pelo seu número antes: reenviar devolveria
    erro, e não a cobrança que já existe.

    **«valorNominal» VAI COMO NÚMERO, E «valorTotalRecebido» VOLTA COMO TEXTO**
    (`^\\d{1,10}\\.\\d{2}$`) — e o exemplo do próprio contrato traz o
    valorNominal da resposta como número. `cobranca.centavos_do_banco` lê os
    dois.

    **«MARCADO_RECEBIDO» NÃO PASSOU PELA CONTA** — ver `cobranca`: vira
    BAIXADA, e não RECEBIDA.

    O webhook (`PUT /cobrancas/webhook`) existe e NÃO é usado: ele exige um
    endereço público com TLS que receba o banco, e o servidor desta casa é a
    máquina do balcão. A consulta da automação faz o mesmo papel, mais devagar.
"""
from __future__ import annotations

import base64
import urllib.parse
from collections.abc import Mapping
from typing import Any

import cobranca as CB
import despesas_inter as INTER
from cobranca_banco import (
    BancoError,
    CredencialAusente,
    CredencialTrancada,
    Indisponivel,
    Recusa,
)

ESCOPOS = "boleto-cobranca.read boleto-cobranca.write"

# A situação do Inter → a nossa. O que não está aqui fica como estava:
# situação desconhecida não vira «pago» nem «falhou».
SITUACAO = {
    "EM_PROCESSAMENTO": CB.EMITINDO,
    "A_RECEBER": CB.ABERTA,
    "ATRASADO": CB.ABERTA,
    "PROTESTO": CB.ABERTA,
    "RECEBIDO": CB.RECEBIDA,
    "MARCADO_RECEBIDO": CB.BAIXADA,
    "EXPIRADO": CB.BAIXADA,
    "CANCELADO": CB.CANCELADA,
    "FALHA_EMISSAO": CB.FALHOU,
}
MOTIVO = {
    "MARCADO_RECEBIDO": "Marcada como recebida no Internet Banking: o dinheiro NÃO passou "
                        "pela conta. Confira como o cliente pagou antes de lançar no caixa.",
    "EXPIRADO": "Passou o prazo de pagamento depois do vencimento, e o Inter a expirou.",
    "PROTESTO": "O título está em protesto no Inter.",
    "FALHA_EMISSAO": "O Inter não conseguiu emitir o boleto.",
}


class _Cliente(INTER.ClienteInter):
    escopos = ESCOPOS


class ClienteCobrancaInter:
    """A API Cobrança v3 do Inter, por um transporte injetável."""

    banco = CB.INTER

    def __init__(self, ambiente: str, transporte: INTER.Transporte, campos: dict):
        try:
            self._c = _Cliente(ambiente, transporte, campos)
        except INTER.InterError as erro:
            raise BancoError(str(erro)) from erro
        self.ambiente = ambiente
        self.base = f"{self._c.base}/cobranca/v3"

    def _ir(self, metodo: str, caminho: str, **kw) -> INTER.Resposta:
        try:
            return self._c._ir(metodo, f"{self.base}{caminho}", cabecalhos=self._c._cab(), **kw)
        except INTER.Indisponivel as erro:
            raise Indisponivel(str(erro)) from erro
        except INTER.InterError as erro:
            raise Recusa(str(erro)) from erro

    @staticmethod
    def _recusa(r: INTER.Resposta, padrao: str) -> Recusa:
        frase = INTER._frase(r.corpo)
        if isinstance(r.corpo, dict):
            violacoes = [f"{v.get('propriedade') or ''}: {v.get('razao') or ''}".strip(": ")
                         for v in (r.corpo.get("violacoes") or []) if isinstance(v, dict)]
            if violacoes:
                frase = (frase + " — " if frase else "") + "; ".join(violacoes)[:300]
        return Recusa(frase or f"{padrao} (HTTP {r.status}).")

    # --------------------------------------------------------- as operações

    def corpo(self, c: Mapping[str, Any]) -> dict:
        """A emissão, montada da linha de `cb_cobrancas`. Só calcula."""
        end = CB.endereco(c)
        pagador = {
            "cpfCnpj": c["pagador_documento"],
            "tipoPessoa": "FISICA" if len(c["pagador_documento"]) == 11 else "JURIDICA",
            "nome": c["pagador_nome"],
            "endereco": end.get("logradouro", ""),
            "cidade": end.get("cidade", ""),
            "uf": end.get("uf", ""),
            "cep": end.get("cep", ""),
        }
        for chave, campo in (("numero", "numero"), ("complemento", "complemento"),
                             ("bairro", "bairro")):
            if end.get(chave):
                pagador[campo] = end[chave]
        if c.get("pagador_email"):
            pagador["email"] = c["pagador_email"]
        corpo = {"seuNumero": c["seu_numero"], "valorNominal": round(int(c["valor"]) / 100, 2),
                 "dataVencimento": c["vencimento"],
                 "numDiasAgenda": int(c.get("dias_apos_vencimento") or 0),
                 "pagador": pagador, "formasRecebimento": ["BOLETO", "PIX"]}
        linhas = CB.linhas_da_mensagem(c.get("mensagem"), largura=78, maximo=5)
        if linhas:
            corpo["mensagem"] = {f"linha{i}": t for i, t in enumerate(linhas, start=1)}
        return corpo

    def emitir(self, c: Mapping[str, Any]) -> str:
        r = self._ir("POST", "/cobrancas", json_corpo=self.corpo(c))
        if r.status in (200, 201) and isinstance(r.corpo, dict) and r.corpo.get("codigoSolicitacao"):
            return str(r.corpo["codigoSolicitacao"])
        raise self._recusa(r, "O Inter recusou a emissão")

    def consultar(self, c: Mapping[str, Any]) -> dict | None:
        r = self._ir("GET", f"/cobrancas/{urllib.parse.quote(str(c['banco_id']))}")
        if r.status == 200 and isinstance(r.corpo, dict):
            return ler(r.corpo)
        if r.status == 404:
            return None
        raise self._recusa(r, "O Inter recusou a consulta")

    def procurar(self, c: Mapping[str, Any], *, data_inicial: str, data_final: str) -> str | None:
        """O codigoSolicitacao da cobrança com este seu número, se o Inter a tem."""
        consulta = urllib.parse.urlencode({
            "dataInicial": data_inicial, "dataFinal": data_final,
            "filtrarDataPor": "EMISSAO", "seuNumero": c["seu_numero"]})
        r = self._ir("GET", f"/cobrancas?{consulta}")
        if r.status == 404:
            return None
        if r.status != 200 or not isinstance(r.corpo, dict):
            raise self._recusa(r, "O Inter recusou a busca")
        for item in r.corpo.get("cobrancas") or []:
            dados = (item or {}).get("cobranca") or {}
            if str(dados.get("seuNumero") or "") == str(c["seu_numero"]):
                return str(dados.get("codigoSolicitacao") or "") or None
        return None

    def pdf(self, c: Mapping[str, Any]) -> bytes:
        r = self._ir("GET", f"/cobrancas/{urllib.parse.quote(str(c['banco_id']))}/pdf")
        if r.status == 200 and isinstance(r.corpo, dict) and r.corpo.get("pdf"):
            try:
                return base64.b64decode(r.corpo["pdf"], validate=False)
            except ValueError as erro:
                raise Recusa("O PDF do Inter veio ilegível.") from erro
        raise self._recusa(r, "O Inter não entregou o PDF")

    def cancelar(self, c: Mapping[str, Any], motivo: str) -> str:
        r = self._ir("POST", f"/cobrancas/{urllib.parse.quote(str(c['banco_id']))}/cancelar",
                     json_corpo={"motivoCancelamento": CB._texto(motivo, 50)})
        if r.status in (200, 202, 204):
            return ""
        raise self._recusa(r, "O Inter recusou o cancelamento")


def ler(corpo: Mapping[str, Any]) -> dict:
    """A resposta da consulta → a forma comum de `cobranca.gravar_resposta`. Só calcula."""
    dados = corpo.get("cobranca") or {}
    boleto = corpo.get("boleto") or {}
    pix = corpo.get("pix") or {}
    status = str(dados.get("situacao") or "").upper()
    saida = {
        "banco_status": status,
        "banco_motivo": MOTIVO.get(status, ""),
        "nosso_numero": boleto.get("nossoNumero") or "",
        "linha_digitavel": boleto.get("linhaDigitavel") or "",
        "codigo_barras": boleto.get("codigoBarras") or "",
        "pix_copia_e_cola": pix.get("pixCopiaECola") or "",
    }
    if status in SITUACAO:
        saida["situacao"] = SITUACAO[status]
    if status == "RECEBIDO":
        saida["valor_recebido"] = CB.centavos_do_banco(dados.get("valorTotalRecebido"))
        saida["data_pagamento"] = str(dados.get("dataSituacao") or "")[:10]
        saida["forma_recebida"] = str(dados.get("origemRecebimento") or "BOLETO").upper()
    return saida


def cliente_da_casa(cfg: Mapping[str, str], *, pasta: Any = None,
                    transporte: INTER.Transporte | None = None) -> ClienteCobrancaInter:
    """O cliente configurado, com a credencial do Inter (a mesma das despesas)."""
    try:
        campos = INTER.credencial(pasta)
    except INTER.CredencialTrancada as erro:
        raise CredencialTrancada(str(erro)) from erro
    except INTER.CredencialAusente as erro:
        raise CredencialAusente(str(erro)) from erro
    if transporte is None:
        transporte = INTER.transporte_https(campos)
    return ClienteCobrancaInter(cfg.get("cobranca_ambiente") or "sandbox", transporte, campos)
