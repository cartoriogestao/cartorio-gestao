# -*- coding: utf-8 -*-
"""O TRANSPORTE DO BOLETO DO DEVEDOR — o provedor configurável, e o simulador.

**O BOLETO JÁ FOI DESTA CASA, E SAIU DE PROPÓSITO.** O aviso do E-Ofício era
também um boleto, com banco `000` e um verificador de nosso número que ninguém
conseguiu reproduzir (`protesto_aviso`, cabeçalho): «código de barras errado é
boleto que o leitor aceita e o dinheiro cai no lugar errado — não se chuta».
Este módulo não monta código de barras nenhum. **Quem gera a linha digitável,
o código de barras e o PIX é o BANCO**, na cobrança registrada; daqui sai o
pedido e volta o que ele devolveu.

**O PROVEDOR É CONFIGURÁVEL, E HOJE SÓ HÁ O FALSO.** Cada banco tem a sua API
de cobrança (e o seu manual, e a sua homologação); qual será o desta casa é
decisão do oficial, e em 19/10/2026 não há convênio. `BancoDoContrato` é a vaga
dele: recusa tudo dizendo o que falta. `BancoFalso` é a homologação: registra,
«paga» quando alguém manda na tela de ensaio, e devolve as liquidações como um
banco devolveria — **sem rede**, com o estado num arquivo ao lado das
credenciais.

**O QUE O SIMULADOR DEVOLVE NÃO SE PAGA.** A linha digitável e o PIX dele são
texto com letras — `HOMOLOGACAO NAO PAGAR …` —, que nenhum leitor de banco
aceita. Um ensaio que gerasse número com cara de boleto acabaria impresso e
pago por alguém.

O CN-MA (Prov. COGEX 28/2026) é a base: art. 925, § 2º (boleto e PIX entre os
meios eletrônicos de pagamento), § 4º (o prazo-limite é o dia previsto para a
lavratura — é o vencimento do boleto) e § 5º (o custo do boleto que acompanha
a intimação pode ser repassado).

**A CHAMADA NUNCA ACONTECE DENTRO DE `db.transaction()`.**
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import threading
from datetime import date
from pathlib import Path
from typing import Any

import centrais_cred as CRED


class BoletoError(RuntimeError):
    """Não deu para falar com o banco, ou ele recusou."""


class BoletoRecusado(BoletoError):
    """O banco respondeu, e a resposta é recusa: nada ficou registrado."""


class BoletoSemContrato(BoletoError):
    """O transporte de verdade não existe enquanto não houver convênio."""


FALTA_DO_CONTRATO = (
    "nenhum banco tem transporte escrito, porque a serventia não tem convênio "
    "de cobrança registrada. Para ligar são precisos: a escolha do banco pelo "
    "oficial, o convênio de cobrança (com PIX, se o banco oferecer), o "
    "client_id e o client secret da API (que se informam em Administrativo → "
    "Configurações, fora do banco de dados) e o MANUAL da API do banco — os "
    "endereços, os campos e a forma da liquidação se transcrevem dele. Até "
    "lá, use a homologação, com o serviço falso.")

_SO_DIGITOS = re.compile(r"\D")
_TRAVA_DO_ARQUIVO = threading.Lock()


def _digitos(valor: Any) -> str:
    return _SO_DIGITOS.sub("", str(valor or ""))


def conferir_pedido(pedido: Any) -> dict:
    """O que a cobrança registrada exige, conferido AQUI. Só calcula.

    **O PAGADOR VAI COM CPF OU CNPJ E COM ENDEREÇO**: boleto registrado sem
    eles o banco recusa — e recusa depois de a tela dizer «emitindo».
    """
    p = dict(pedido or {})
    faltas = []
    try:
        valor = int(p.get("valor_centavos") or 0)
    except (TypeError, ValueError):
        valor = 0
    if valor <= 0:
        faltas.append("um valor maior que zero")
    try:
        date.fromisoformat(str(p.get("vencimento") or "")[:10])
    except ValueError:
        faltas.append("o vencimento")
    pagador = dict(p.get("pagador") or {})
    if not str(pagador.get("nome") or "").strip():
        faltas.append("o nome do devedor")
    if len(_digitos(pagador.get("documento"))) not in (11, 14):
        faltas.append("o CPF ou CNPJ do devedor")
    if not str(pagador.get("endereco") or "").strip():
        faltas.append("o endereço do devedor")
    if len(_digitos(pagador.get("cep"))) != 8:
        faltas.append("o CEP do devedor com oito dígitos")
    if not str(pagador.get("cidade") or "").strip() or \
            len(str(pagador.get("uf") or "").strip()) != 2:
        faltas.append("a cidade e a UF do devedor")
    if faltas:
        raise BoletoRecusado(
            "O boleto não se registra sem " + ", ".join(faltas[:-1])
            + (" e " if len(faltas) > 1 else "") + faltas[-1] + ".")
    p["valor_centavos"] = valor
    return p


# ------------------------------------------------------ o serviço falso


def _ler_estado(arquivo: Path) -> dict:
    if not arquivo.is_file():
        return {"seq": 0, "eventos": 0, "boletos": {}}
    try:
        return json.loads(arquivo.read_text(encoding="utf-8")) or {
            "seq": 0, "eventos": 0, "boletos": {}}
    except (OSError, ValueError):
        return {"seq": 0, "eventos": 0, "boletos": {}}


def _gravar_estado(arquivo: Path, estado: dict) -> None:
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(arquivo.parent), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False)
    os.replace(tmp, arquivo)


class BancoFalso:
    """O SERVIÇO FALSO — o banco da homologação, sem rede."""

    E_SIMULADOR = True
    ARQUIVO = "simulador_boletos.json"

    def __init__(self, ambiente: Any = CRED.HOMOLOGACAO, pasta: Any = None):
        self.ambiente = str(ambiente or CRED.HOMOLOGACAO)
        # O ESTADO MORA AO LADO DAS CREDENCIAIS, fora do banco de dados — é
        # onde o serviço de verdade estaria: do lado de fora da casa.
        pasta_do_simulador = (Path(pasta) if pasta
                              else CRED.pasta_de_dados() / "simuladores")
        self.arquivo = pasta_do_simulador / self.ARQUIVO

    @staticmethod
    def _devolver(nosso: str, b: dict) -> dict:
        return {"nosso_numero": nosso, "id_no_provedor": f"FALSO-{nosso}",
                "identificador": b.get("identificador") or "",
                "linha_digitavel": f"HOMOLOGACAO NAO PAGAR {nosso}",
                "codigo_barras": "",
                "pix_copia_e_cola": f"HOMOLOGACAO-NAO-PAGAR-{nosso}",
                "situacao": b.get("situacao") or "ABERTO",
                "resposta": {"simulador": True, "nosso_numero": nosso}}

    def registrar(self, pedido: dict) -> dict:
        """Registra o boleto. O mesmo identificador devolve o mesmo boleto —
        é o que um banco faz com o «seu número» repetido."""
        p = conferir_pedido(pedido)
        ident = str(p.get("identificador") or "").strip()
        with _TRAVA_DO_ARQUIVO:
            estado = _ler_estado(self.arquivo)
            boletos = estado.setdefault("boletos", {})
            for nosso, b in sorted(boletos.items()):
                if ident and b.get("identificador") == ident:
                    return self._devolver(nosso, b)
            estado["seq"] = int(estado.get("seq") or 0) + 1
            nosso = f"{estado['seq']:010d}"
            boletos[nosso] = {"identificador": ident,
                              "valor_centavos": p["valor_centavos"],
                              "vencimento": str(p["vencimento"])[:10],
                              "situacao": "ABERTO"}
            _gravar_estado(self.arquivo, estado)
            return self._devolver(nosso, boletos[nosso])

    def consultar(self, identificador: Any) -> dict | None:
        """O boleto daquele «seu número», ou None se o banco não o tem."""
        ident = str(identificador or "").strip()
        with _TRAVA_DO_ARQUIVO:
            boletos = _ler_estado(self.arquivo).get("boletos") or {}
        for nosso, b in sorted(boletos.items()):
            if ident and b.get("identificador") == ident:
                return self._devolver(nosso, b)
        return None

    def cancelar(self, nosso_numero: Any) -> dict:
        """Dá baixa no boleto aberto — o pedido de baixa ao banco."""
        nosso = str(nosso_numero or "").strip()
        with _TRAVA_DO_ARQUIVO:
            estado = _ler_estado(self.arquivo)
            b = (estado.get("boletos") or {}).get(nosso)
            if b is None:
                raise BoletoRecusado(f"O banco não conhece o boleto {nosso}.")
            if b.get("situacao") == "PAGO":
                raise BoletoRecusado(
                    f"O boleto {nosso} já foi PAGO — não se cancela; a "
                    f"liquidação chega na próxima busca de pagamentos.")
            b["situacao"] = "BAIXADO"
            _gravar_estado(self.arquivo, estado)
        return {"nosso_numero": nosso, "situacao": "BAIXADO"}

    def liquidacoes(self, desde: str, ate: str) -> list[dict]:
        """Os pagamentos do período, como o banco os devolve. Só lê."""
        de, a = str(desde or "")[:10], str(ate or "")[:10]
        with _TRAVA_DO_ARQUIVO:
            boletos = _ler_estado(self.arquivo).get("boletos") or {}
        fora = []
        for nosso, b in sorted(boletos.items()):
            if b.get("situacao") != "PAGO":
                continue
            if de <= str(b.get("pago_em") or "") <= a:
                fora.append({"evento_id": b["evento_id"], "nosso_numero": nosso,
                             "valor_pago_centavos": int(b["valor_pago_centavos"]),
                             "pago_em": b["pago_em"],
                             "creditado_em": b["pago_em"]})
        return fora

    def simular_pagamento(self, nosso_numero: Any, *, pago_em: str,
                          valor_centavos: Any = None) -> dict:
        """O que, no banco de verdade, é o devedor pagando. Só no simulador."""
        nosso = str(nosso_numero or "").strip()
        with _TRAVA_DO_ARQUIVO:
            estado = _ler_estado(self.arquivo)
            b = (estado.get("boletos") or {}).get(nosso)
            if b is None:
                raise BoletoRecusado(f"O banco não conhece o boleto {nosso}.")
            if b.get("situacao") != "ABERTO":
                raise BoletoRecusado(
                    f"O boleto {nosso} está {b.get('situacao')} — não se paga.")
            estado["eventos"] = int(estado.get("eventos") or 0) + 1
            b.update({"situacao": "PAGO", "pago_em": str(pago_em)[:10],
                      "valor_pago_centavos": int(valor_centavos
                                                 if valor_centavos is not None
                                                 else b["valor_centavos"]),
                      "evento_id": f"EV{estado['eventos']:08d}"})
            _gravar_estado(self.arquivo, estado)
        return {"nosso_numero": nosso, "evento_id": b["evento_id"]}

    def diagnostico(self) -> dict:
        return {"ok": True, "motivo": "Serviço falso desta casa: não usa rede."}


class BancoDoContrato:
    """A VAGA DO BANCO DE VERDADE. Recusa tudo, com a lista do que falta."""

    E_SIMULADOR = False

    def __init__(self, ambiente: Any = CRED.PRODUCAO, pasta: Any = None):
        self.ambiente = str(ambiente or CRED.PRODUCAO)
        self.pasta = pasta

    def registrar(self, pedido: dict) -> dict:
        raise BoletoSemContrato("Banco: " + FALTA_DO_CONTRATO)

    def consultar(self, identificador: Any) -> dict | None:
        raise BoletoSemContrato("Banco: " + FALTA_DO_CONTRATO)

    def cancelar(self, nosso_numero: Any) -> dict:
        raise BoletoSemContrato("Banco: " + FALTA_DO_CONTRATO)

    def liquidacoes(self, desde: str, ate: str) -> list[dict]:
        raise BoletoSemContrato("Banco: " + FALTA_DO_CONTRATO)

    def diagnostico(self) -> dict:
        return {"ok": False, "motivo": "Banco: " + FALTA_DO_CONTRATO}


PROVEDORES: dict[str, dict[str, Any]] = {
    "FALSO": {"nome": "Serviço falso desta casa (homologação, sem rede)",
              "falso": True, "pronto": True, "falta": "",
              "fabrica": lambda ambiente, pasta: BancoFalso(ambiente, pasta)},
    "BANCO": {"nome": "Banco do convênio de cobrança (a escolher)",
              "falso": False, "pronto": False, "falta": FALTA_DO_CONTRATO,
              "fabrica": lambda ambiente, pasta: BancoDoContrato(ambiente, pasta)},
}
