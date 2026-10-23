# -*- coding: utf-8 -*-
"""O que os testes do LG06 (AR digital, boleto, painel do devedor) usam juntos.

DADOS FICTÍCIOS (LGPD): o CPF `000.000.001-91` e o CNPJ `00.000.043/0001-77`
são os de exemplo que todo manual usa — fecham o dígito e não são de ninguém
desta casa. Nomes e endereços são de Cidade Exemplo.

OS DUBLÊS DE PRODUÇÃO. O serviço falso não vale em produção, e é de propósito
(`protesto_integracoes`). Para provar o que a PRODUÇÃO faz com o que volta —
lavrar a intimação, dar baixa no pagamento —, os testes usam o mesmo simulador
com a marca de simulador desligada: são as respostas que os Correios e o banco
dariam, conhecidas, e sem rede.
"""
from __future__ import annotations

import boleto_api as BAPI
import correios_api as CAPI
import protesto as PT
import protesto_aviso as AV
from bd_nativo import banco

SV = {"unit_name": "SERVENTIA EXTRAJUDICIAL DE CIDADE EXEMPLO",
      "serventia_titular": "TABELIÃO EXEMPLO",
      "serventia_titulo": "Tabelião e Oficial de Registro",
      "ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA"}

CPF = "00000000191"
CNPJ_CREDOR = "00000043000177"

HOMOLOGACAO = {"modo": "HOMOLOGACAO", "ambiente": "HOMOLOGACAO",
               "provedor": "FALSO", "tarifa_centavos": 0}
PRODUCAO = {"modo": "PRODUCAO", "ambiente": "PRODUCAO",
            "provedor": "DUBLE", "tarifa_centavos": 0}


class CorreiosDeTeste(CAPI.CorreiosFalso):
    """As respostas dos Correios, conhecidas — o dublê da produção."""
    E_SIMULADOR = False


class BancoDeTeste(BAPI.BancoFalso):
    """As respostas do banco, conhecidas — o dublê da produção."""
    E_SIMULADOR = False


class Relogio:
    """O RELÓGIO DO ROTEIRO, e não o da máquina: `db.now()` no dia que o teste diz.

    Os testes dão `hoje` às funções (emitido em 19/10, pago em 20/10, buscado
    em 21/10), mas o boleto grava `emitido_em = db.now()`, e a busca começa no
    boleto vivo mais antigo (`protesto_boleto.buscar_pagamentos`). Com o
    relógio da máquina, a partir de 21/10/2026 o boleto «nasce» depois do
    pagamento, e a busca não o acha mais: o vermelho era o dia em que a suíte
    rodava, e não o código. `ir_para` anda o relógio para o dia do passo
    seguinte, como anda no balcão.
    """

    def __init__(self, db, monkeypatch, dia: str = "2026-10-19"):
        self.agora = ""
        self.ir_para(dia)
        monkeypatch.setattr(db, "now", lambda: self.agora)

    def ir_para(self, dia: str) -> None:
        self.agora = f"{str(dia)[:10]}T10:00:00"


def titulo_apontado(db, *, numero: str = "LG06/1", cpf: str = CPF,
                    nome: str = "FULANO DE TAL EXEMPLO",
                    protocolo: str = "2610190001", saldo: str = "1310.45",
                    cep: str = "65000-000", chave: str = "") -> int:
    """Um título apontado, com o protocolo escolhido pelo teste.

    O protocolo da casa é AAMMDD + sequencial, e é dele que sai o prazo-limite
    (`protesto_aviso.prazo_limite`) — por isso o teste o escolhe, em vez de
    depender do dia em que roda.
    """
    agora = db.now()
    with db.transaction() as con:
        tid = PT.cadastrar_titulo(con, {
            "apresentante_codigo": "001", "apresentante_nome": "BANCO EXEMPLO",
            "especie": "DMI", "numero_titulo": numero,
            "nosso_numero": "NN" + numero, "data_emissao": "2026-01-05",
            "data_vencimento": "2026-02-05", "valor": "1200.00",
            "saldo": saldo, "praca_protesto": "CIDADE EXEMPLO",
            "cedente": {"nome": "LOJA EXEMPLO LTDA", "documento": CNPJ_CREDOR},
            "devedores": [{"nome": nome, "CPF": cpf,
                           "enderecos": [{"endereco": "RUA EXEMPLO, 100",
                                          "bairro": "CENTRO", "cep": cep,
                                          "cidade": "Cidade Exemplo",
                                          "uf": "MA"}]}],
        }, origem="CRA", origem_chave=f"lg06:{numero}", agora=agora)
        PT.lancar_apontamento(con, tid, sv=SV, agora=agora,
                              data_extenso="dezenove de outubro")
        banco(con).escrever("UPDATE pt_titulos SET protocolo=%s, chave_cenprot=%s "
                            "WHERE id=%s", (protocolo, chave or None, tid))
    return tid


def aviso_emitido(db, titulo_id: int) -> int:
    with db.transaction() as con:
        r = AV.emitir(con, titulo_id, hoje="2026-10-19", agora=db.now(),
                      usuario="escrevente")
    return int(r["aviso_id"])


def prazo(db, titulo_id: int) -> str:
    with db.connect() as con:
        return AV.prazo_limite(con, PT.titulo(con, titulo_id))


def um(db, sql: str, args=()) -> dict | None:
    with db.connect() as con:
        return banco(con).um(sql, args)


def ler(db, sql: str, args=()) -> list[dict]:
    with db.connect() as con:
        return banco(con).ler(sql, args)
