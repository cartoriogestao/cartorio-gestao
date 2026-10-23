"""
Carga do movimento financeiro e do protocolo geral do E-Oficio.

O QUE O LEVANTAMENTO MOSTROU, E O QUE MUDOU POR CAUSA DISSO

    1. `bitFinalizado` e FALSO nas 21.342 linhas, e `intSituacaoPG` e 1 em
       todas. Os dois campos existem e nunca foram usados. Quem quiser saber o
       que esta em aberto NAO pode olhar para eles — foi a primeira coisa que
       eu ia fazer.

    2. O sinal que funciona e outro: o protocolo tem custas lancadas? tem
       movimento no caixa? Dai sai a situacao:

           sem custas e sem caixa  ->  ABERTO           (640 casos)
           com custas, sem caixa   ->  A PAGAR
           com movimento no caixa  ->  PAGO             (16.755 casos)

    3. `curBaseCalculo` e zero em tudo. O valor real do ato esta nas custas,
       nao no cabecalho do protocolo.

    4. 137 movimentos de caixa apontam para protocolo que nao existe. Vao para
       quarentena, com o numero citado — nao se inventa o protocolo que falta.

NUMEROS DA ORIGEM, PARA CONFERIR DEPOIS DA CARGA
    21.342 protocolos, de 19/03/2020 a 14/08/2026
    18.385 movimentos de caixa: 17.959 entradas e 426 saidas
    R$ 1.661.724,25 de entrada e R$ 25.070,97 de saida
    32.396 lancamentos de custas
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from bd_nativo import banco
from caixa_schema import centavos, reais

# intAtribuicao do E-Oficio -> atribuicao da serventia.
ATRIBUICOES = {
    0: "OUTROS", 1: "FIRMAS", 2: "PROTESTO", 3: "RTD",
    4: "NOTAS", 5: "RI", 6: "RCPN",
}

# strES do caixa.
SENTIDOS = {"E": "ENTRADA", "S": "SAIDA"}

# intCodigoRecebimento de tbCX_Rec -> forma de pagamento.
FORMAS = {
    1: "DINHEIRO", 2: "CHEQUE", 3: "DEBITO", 4: "CREDITO",
    5: "PIX", 6: "TRANSFERENCIA", 7: "BOLETO", 8: "DEPOSITO",
}


def _ler(caminho: Path) -> Iterator[dict]:
    with caminho.open(encoding="utf-8", errors="replace") as fh:
        for linha in fh:
            linha = linha.strip()
            if linha:
                yield json.loads(linha)


def _data(v: Any) -> str | None:
    if not v:
        return None
    s = str(v).strip()
    for formato in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s[:19], formato).date().isoformat()
        except ValueError:
            continue
    return s[:10] or None


def _cent(v: Any) -> int:
    if v is None:
        return 0
    if isinstance(v, (int, float)):
        return int(round(float(v) * 100))
    return centavos(v)


def _texto(v: Any) -> str | None:
    s = ("" if v is None else str(v)).strip()
    return s or None


class Carga:
    """Importa o movimento. Tudo dentro de uma transacao so."""

    def __init__(self, con, pasta: Path, usuario_id: int | None = None):
        self.con = con
        self.bd = banco(con)
        self.pasta = Path(pasta)
        self.usuario_id = usuario_id
        self.agora = datetime.now().isoformat(timespec="seconds")
        self.rel: dict[str, Any] = {
            "protocolos": 0, "custas": 0, "caixas": 0, "lancamentos": 0,
            "recibos": 0, "quarentena": 0, "situacoes": {}, "totais": {},
            # Recarga para trazer o movimento recente: o que ja estava no
            # banco e contado a parte, para o relatorio dizer o que ENTROU
            # agora em vez de repetir o total de sempre.
            "protocolos_ja_existentes": 0, "custas_ja_existentes": 0,
            "lancamentos_ja_existentes": 0,
            "avisos": [],
        }
        self.importacao_id: int | None = None

    # ------------------------------------------------------------- apoio

    def _quarentena(self, entidade: str, chave: str, motivo: str) -> None:
        self.bd.escrever(
            """INSERT INTO cx_rejeitados (importacao_id, entidade, chave_origem,
                                          motivo, conteudo)
               VALUES (%s,%s,%s,%s,%s)""",
            (self.importacao_id, entidade, chave, motivo, None))
        self.rel["quarentena"] += 1

    # ------------------------------------------------------------ etapas

    def executar(self) -> dict:
        novo = self.bd.escrever(
            """INSERT INTO cx_importacoes (arquivo, executada_em, executada_por)
               VALUES (%s,%s,%s) RETURNING id""",
            (str(self.pasta), self.agora, self.usuario_id))
        self.importacao_id = int(novo[0]["id"])

        custas = self._indexar_custas()
        no_caixa = self._protocolos_com_caixa()
        self._protocolos(custas, no_caixa)
        self._custas(custas)
        self._caixa()
        self.bd.escrever("UPDATE cx_importacoes SET relatorio = %s WHERE id = %s",
                         (json.dumps(self.rel, ensure_ascii=False), self.importacao_id))
        return self.rel

    def _indexar_custas(self) -> dict[str, list[dict]]:
        arq = self.pasta / "protocolo_custas.jsonl"
        indice: dict[str, list[dict]] = {}
        if not arq.exists():
            self.rel["avisos"].append("protocolo_custas.jsonl não encontrado.")
            return indice
        for r in _ler(arq):
            numero = _texto(r.get("strProtocoloGeral"))
            if numero:
                indice.setdefault(numero, []).append(r)
        return indice

    def _protocolos_com_caixa(self) -> set[str]:
        arq = self.pasta / "caixa.jsonl"
        if not arq.exists():
            return set()
        return {n for r in _ler(arq)
                if (n := _texto(r.get("strProtocoloGeral")))}

    def _protocolos(self, custas: dict, no_caixa: set[str]) -> None:
        arq = self.pasta / "protocolo_geral.jsonl"
        if not arq.exists():
            self.rel["avisos"].append("protocolo_geral.jsonl não encontrado.")
            return
        situacoes: dict[str, int] = {}
        for r in _ler(arq):
            numero = _texto(r.get("strProtocoloGeral"))
            if not numero:
                self._quarentena("PROTOCOLO", "", "protocolo sem número")
                continue

            # A situacao vem do movimento, nao dos campos que a origem nunca
            # preencheu. Ver o cabecalho deste arquivo.
            tem_custas = numero in custas
            tem_caixa = numero in no_caixa
            if tem_caixa:
                situacao, finalizado = "PAGO", 1
            elif tem_custas:
                situacao, finalizado = "A_PAGAR", 0
            else:
                situacao, finalizado = "ABERTO", 0
            situacoes[situacao] = situacoes.get(situacao, 0) + 1

            soma = sum(_cent(c.get("curv_Emolumento")) + _cent(c.get("curv_Ferc"))
                       + _cent(c.get("curValor_MP")) + _cent(c.get("curValor_DP"))
                       + _cent(c.get("curvalor_ferrfis"))
                       for c in custas.get(numero, []))
            cur_prot = self.bd.escrever(
                """INSERT INTO cx_protocolos
                   (numero, data_abertura, hora, atribuicao, interessado,
                    interessado_documento, telefone, email, assunto, observacao,
                    prazo, situacao, finalizado, gratuito, motivo_gratuidade,
                    deposito_previo, valor_total, origem, origem_chave,
                    importacao_id, criado_em, criado_por)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                           'EOFICIO', %s,%s,%s,%s)
                   ON CONFLICT DO NOTHING
                   RETURNING id""",
                (numero, _data(r.get("dtmData")) or "", _texto(r.get("strHoras")),
                 ATRIBUICOES.get(r.get("intAtribuicao"), "OUTROS"),
                 _texto(r.get("strInteressado")),
                 _texto(r.get("strInteressado_Doc")),
                 _texto(r.get("strTelefoneContato")), _texto(r.get("strEmail")),
                 _texto(r.get("strAssunto")), _texto(r.get("memAnotacao")),
                 _data(r.get("dtmPrazo")), situacao, finalizado,
                 1 if r.get("bitGratuito") else 0, _texto(r.get("strMotivoIsencao")),
                 1 if r.get("bitDepositoPrevio") else 0,
                 reais(soma) if soma else None,
                 numero, self.importacao_id, self.agora, self.usuario_id))
            if cur_prot:
                self.rel["protocolos"] += 1
            else:
                self.rel["protocolos_ja_existentes"] += 1
        self.rel["situacoes"] = situacoes

    def _custas(self, custas: dict) -> None:
        ids = {r["numero"]: r["id"] for r in
               self.bd.ler("SELECT numero, id FROM cx_protocolos ORDER BY id")}
        for numero, linhas in custas.items():
            pid = ids.get(numero)
            if not pid:
                # Uma linha de quarentena por protocolo, dizendo quantos
                # lancamentos ficaram de fora — senao a soma nao fecha e
                # ninguem entende por que faltam tres.
                self._quarentena("CUSTAS", numero,
                                 f"custas de protocolo que não existe no protocolo "
                                 f"geral ({len(linhas)} lançamento(s) descartado(s))")
                self.rel["custas_descartadas"] = (
                    self.rel.get("custas_descartadas", 0) + len(linhas))
                continue
            for c in linhas:
                # A QUANTIDADE MULTIPLICA, E O E-OFICIO NAO A APLICAVA NA
                # COLUNA — medido em 21/09/2026 no acervo inteiro: em **185**
                # pares (codigo do TJ, ano) com mais de uma quantidade o
                # emolumento e' **constante**, e em **zero** ele escala. O
                # `16.39` («arquivamento, POR FOLHA») sai 5,92 tanto na
                # quantidade 1 quanto na 128; os quatro fundos tambem sao os
                # do unitario (4% de 5,92 = 0,23 em todas).
                #
                # Quem multiplicava era a TELA dele. Aqui a coluna se chama
                # `valor_total` e o balcao ja' grava nela `quantidade x
                # unitario` quando acrescenta a mao — **a mesma coluna estava
                # querendo dizer duas coisas conforme a origem da linha**, e a
                # soma do protocolo saia a menos nos que vieram da carga.
                quantidade = int(c.get("intQte") or 1) or 1
                emol = _cent(c.get("curv_Emolumento")) * quantidade
                ferc = _cent(c.get("curv_Ferc")) * quantidade
                femp = _cent(c.get("curValor_MP")) * quantidade
                fadep = _cent(c.get("curValor_DP")) * quantidade
                ferrfis = _cent(c.get("curvalor_ferrfis")) * quantidade
                cur = self.bd.escrever(
                    """INSERT INTO cx_protocolo_atos
                       (protocolo_id, descricao, codigo_ato, quantidade, selo,
                        valor_total, emolumentos, ferc, fadep, femp, ferrfis,
                        gratuito, origem, origem_chave)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, 'EOFICIO', %s)
                       ON CONFLICT DO NOTHING
                       RETURNING id""",
                    (pid, _texto(c.get("strDescDoc")), _texto(c.get("strCodigoTJ")),
                     quantidade, _texto(c.get("curv_Selo")),
                     reais(emol + ferc + femp + fadep + ferrfis),
                     reais(emol), reais(ferc), reais(fadep), reais(femp),
                     reais(ferrfis), 1 if c.get("bitGratuito") else 0,
                     str(c.get("intID"))))
                if cur:
                    self.rel["custas"] += 1
                else:
                    self.rel["custas_ja_existentes"] += 1

    def _caixa(self) -> None:
        arq = self.pasta / "caixa.jsonl"
        if not arq.exists():
            self.rel["avisos"].append("caixa.jsonl não encontrado.")
            return
        prot = {r["numero"]: r["id"] for r in
                self.bd.ler("SELECT numero, id FROM cx_protocolos ORDER BY id")}

        formas: dict[str, str] = {}
        arq_rec = self.pasta / "caixa_recibo.jsonl"
        if arq_rec.exists():
            for r in _ler(arq_rec):
                chave = str(r.get("intChaveCX"))
                if chave not in formas and not r.get("bitEstorno"):
                    formas[chave] = FORMAS.get(r.get("intCodigoRecebimento"), "DINHEIRO")

        caixas: dict[tuple, int] = {}
        entradas = saidas = 0
        for r in _ler(arq):
            data = _data(r.get("dtmData"))
            operador = _texto(r.get("strUSERID_I")) or "(não informado)"
            if not data:
                self._quarentena("CAIXA", str(r.get("intChaveCX")), "movimento sem data")
                continue

            chave = (data, operador)
            if chave not in caixas:
                cur = self.bd.escrever(
                    """INSERT INTO cx_caixas
                       (data, operador_nome, saldo_inicial, aberto_em, situacao)
                       VALUES (%s,%s, '0', %s, 'FECHADO')
                       ON CONFLICT DO NOTHING
                       RETURNING id""",
                    (data, operador, self.agora))
                linha = self.bd.um(
                    """SELECT id FROM cx_caixas
                        WHERE data = %s AND operador_nome = %s
                        ORDER BY id LIMIT 1""",
                    (data, operador))
                caixas[chave] = linha["id"]
                if cur:
                    self.rel["caixas"] += 1

            sentido = SENTIDOS.get(_texto(r.get("strES")) or "E", "ENTRADA")
            valor = _cent(r.get("curValoraPagar"))
            if sentido == "ENTRADA":
                entradas += valor
            else:
                saidas += valor

            numero = _texto(r.get("strProtocoloGeral"))
            pid = prot.get(numero) if numero else None
            if numero and not pid:
                # O numero do protocolo vai na CHAVE, nao no motivo: assim a
                # tela agrupa por motivo e mostra 137 de uma vez, em vez de 137
                # motivos diferentes dizendo a mesma coisa.
                self._quarentena("CAIXA", numero,
                                 "movimento de caixa aponta para protocolo que não "
                                 "existe no protocolo geral")

            cur = self.bd.escrever(
                """INSERT INTO cx_lancamentos
                   (caixa_id, protocolo_id, data, hora, natureza, sentido,
                    forma_pagamento, descricao, valor, origem, origem_chave,
                    importacao_id, criado_em)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s, 'EOFICIO', %s,%s,%s)
                   ON CONFLICT DO NOTHING
                   RETURNING id""",
                (caixas[chave], pid, data, _texto(r.get("strHora")),
                 "RECEBIMENTO" if sentido == "ENTRADA" else "OUTRA_SAIDA",
                 sentido, formas.get(str(r.get("intChaveCX"))),
                 _texto(r.get("strHistorico")), reais(valor),
                 str(r.get("intChaveCX")), self.importacao_id, self.agora))
            if cur:
                self.rel["lancamentos"] += 1
            else:
                self.rel["lancamentos_ja_existentes"] += 1

        self.rel["totais"] = {"entradas": reais(entradas), "saidas": reais(saidas),
                              "saldo": reais(entradas - saidas)}


def importar(con, pasta: Path, usuario_id: int | None = None) -> dict:
    return Carga(con, pasta, usuario_id).executar()
