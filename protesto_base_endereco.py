"""A base nacional de endereços da CENPROT, a partir do aviso — 15/10/2026.

Pedido do oficial: «construa o cadastrar endereço do devedor se tivermos algum
benefício em consultar esse banco de dados nacional». O contrato (swagger
2.1.0, `/base-endereco`) responde que tem:

  CONSULTAR (POST, o documento na query) devolve os endereços que a CENPROT e
  os cartórios já cadastraram para o CPF/CNPJ — com TELEFONE, CELULAR e
  E-MAIL, a origem e a data. O contrato mesmo diz o uso: «localizar devedores
  antes de processar protestos». Aqui ele entra onde a pergunta nasce: o aviso
  que voltou sem entrega, ANTES do edital. Um endereço novo permite reemitir o
  aviso; um telefone ou e-mail é o que a Intimação Digital precisa.

  CADASTRAR (PUT) devolve à base o endereço em que a casa ENTREGOU o aviso —
  o único endereço que a casa sabe que é bom. Só insere; não corrige.

O QUE ESTE MÓDULO NÃO FAZ: não reemite aviso, não troca o endereço do
devedor, não lavra nada e não decide o edital. Ele pergunta, guarda a
resposta e mostra; quem decide o que fazer com um endereço novo é o balcão.

E NADA SAI SEM CLIQUE: consultar manda o CPF do devedor para fora, e
cadastrar manda o endereço dele. Cada vez fica em `pt_base_endereco`, com
quem fez e quando.
"""
from __future__ import annotations

import json
import re
from typing import Any

from bd_nativo import banco

CONSULTA = "CONSULTA"
CADASTRO = "CADASTRO"


class BaseEnderecoError(ValueError):
    """Erro de regra da base de endereços, com a frase do balcão."""


def _so_digitos(v: Any) -> str:
    return re.sub(r"\D", "", str(v or ""))


def _norma(v: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(v or "").upper())


def aviso(con: Any, aviso_id: int) -> dict:
    r = banco(con).um("SELECT * FROM pt_avisos WHERE id = %s", (int(aviso_id),))
    if r is None:
        raise BaseEnderecoError(f"Aviso {aviso_id} não encontrado.")
    return dict(r)


def documento(av: dict) -> str:
    """O CPF/CNPJ do devedor do aviso, só dígitos — ou recusa."""
    doc = _so_digitos(av.get("devedor_documento"))
    if len(doc) not in (11, 14):
        raise BaseEnderecoError(
            "O aviso não tem CPF ou CNPJ do devedor — sem documento não há o "
            "que procurar na base da CENPROT.")
    return doc


def _mascara(doc: str) -> str:
    """A forma do exemplo do contrato: `123.456.789-10`."""
    if len(doc) == 11:
        return f"{doc[:3]}.{doc[3:6]}.{doc[6:9]}-{doc[9:]}"
    return f"{doc[:2]}.{doc[2:5]}.{doc[5:8]}/{doc[8:12]}-{doc[12:]}"


def _partir_numero(endereco: str) -> tuple[str, str]:
    """`RUA GRANDE, 10` → (`RUA GRANDE`, `10`). Sem número no fim, «sn» —
    que é o exemplo do próprio contrato."""
    texto = str(endereco or "").strip()
    m = re.match(r"^(.*?)[,\s]+(?:N[º°O.]?\s*)?(\d+[A-Z]?)\s*$", texto, re.I)
    if m and m.group(1).strip():
        return m.group(1).strip(" ,"), m.group(2)
    return texto, "sn"


def corpo_do_cadastro(av: dict) -> dict:
    """O que vai no `PUT`, montado do aviso ENTREGUE. Só calcula."""
    if str(av.get("situacao") or "") != "ENTREGUE":
        raise BaseEnderecoError(
            "Só se cadastra na base o endereço em que o aviso FOI ENTREGUE — "
            "é o único que a casa sabe que é bom.")
    doc = documento(av)
    rua, numero = _partir_numero(av.get("endereco"))
    cep = _so_digitos(av.get("cep"))
    return {"nm_usuario": str(av.get("devedor_nome") or "").strip(),
            "nm_nr_cpfcnpj": _mascara(doc),
            "nm_email": "", "nm_nr_telefone": "", "nm_nr_celular": "",
            "nm_nr_cep": f"{cep[:5]}-{cep[5:]}" if len(cep) == 8 else cep,
            "nm_endereco": rua, "nm_nr_endereco": numero,
            "nm_complemento": "",
            "nm_bairro": str(av.get("bairro") or "").strip(),
            "nm_cidade": str(av.get("cidade") or "").strip(),
            "sg_uf": str(av.get("uf") or "").strip().upper()}


def registrar(con: Any, av: dict, *, acao: str, ambiente: str,
              agora: str, usuario: str | None = None, enviado: Any = None,
              resposta: Any = None) -> int:
    """Guarda o que se perguntou ou mandou. ESCREVE (só a casa)."""
    if acao not in (CONSULTA, CADASTRO):
        raise BaseEnderecoError(f"Ação desconhecida: {acao!r}.")
    achados = len(resposta) if acao == CONSULTA and isinstance(resposta, list) else 0
    return int(banco(con).escrever(
        """INSERT INTO pt_base_endereco(aviso_id, titulo_id, acao, ambiente,
               documento, enviado, resposta, achados, feito_em, feito_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (int(av["id"]), int(av["titulo_id"]), acao, ambiente, documento(av),
         None if enviado is None else json.dumps(enviado, ensure_ascii=False),
         None if resposta is None else json.dumps(resposta, ensure_ascii=False),
         achados, agora, usuario))[0]["id"])


def _do_aviso(av: dict, achado: dict) -> bool:
    """O endereço achado é o MESMO do aviso? Compara CEP e rua sem pontuação."""
    cep = _so_digitos(achado.get("nm_nr_cep"))
    rua = _norma(achado.get("nm_endereco"))
    return (bool(cep) and cep == _so_digitos(av.get("cep"))
            and bool(rua) and rua[:12] in _norma(av.get("endereco")))


def ultima_consulta(con: Any, av: dict) -> dict | None:
    """A consulta mais recente deste aviso, com cada endereço marcado como
    «novo» (diferente do aviso) ou não. Só LÊ."""
    r = banco(con).um(
        """SELECT feito_em, feito_por, resposta, achados FROM pt_base_endereco
            WHERE aviso_id = %s AND acao = %s ORDER BY id DESC LIMIT 1""",
        (int(av["id"]), CONSULTA))
    if r is None:
        return None
    lista = json.loads(r["resposta"] or "[]")
    for x in lista:
        x["novo"] = not _do_aviso(av, x)
    return {"feito_em": r["feito_em"], "feito_por": r["feito_por"], "achados": lista,
            "novos": sum(1 for x in lista if x["novo"]),
            "com_contato": sum(1 for x in lista
                               if any(str(x.get(k) or "").strip() for k in
                                      ("nm_email", "nm_nr_telefone",
                                       "nm_nr_celular")))}


def cadastro(con: Any, aviso_id: int) -> dict | None:
    """Quando o endereço deste aviso foi cadastrado na base, se foi. Só LÊ."""
    r = banco(con).um(
        """SELECT feito_em, feito_por FROM pt_base_endereco
            WHERE aviso_id = %s AND acao = %s ORDER BY id DESC LIMIT 1""",
        (int(aviso_id), CADASTRO))
    return {"feito_em": r["feito_em"], "feito_por": r["feito_por"]} if r else None
