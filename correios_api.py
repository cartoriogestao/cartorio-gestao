# -*- coding: utf-8 -*-
"""O TRANSPORTE DO AR DIGITAL DOS CORREIOS — e, por enquanto, só o simulador.

**O QUE O AR É PARA ESTA CASA.** O aviso de intimação do Protesto se entrega
pela mão do cartório, e os Correios estão desligados desde o E-Ofício
(`protesto_aviso`: as 1.618 entregas do acervo saíram pela casa). O Código de
Normas do MA deixa a remessa ir «por qualquer meio idôneo, desde que o seu
recebimento fique assegurado e comprovado mediante protocolo, aviso de
recebimento - AR, ou documento equivalente» (art. 921), e o AR **digital** é o
mesmo AR com a imagem do canhoto assinado devolvida pela rede, e não pelo
malote.

**NÃO HÁ CONTRATO, E POR ISSO NÃO HÁ TRANSPORTE DE VERDADE.** Em 19/10/2026 a
serventia não tem contrato de AR digital com os Correios. O endereço da API, os
campos da pré-postagem, o caminho da imagem do AR e a tabela dos códigos de
não-entrega vêm no manual do contrato — e **não se inventam**: endereço
inventado é o pior tipo de número inventado, porque quem o usasse acharia que
está postando. `CorreiosDoContrato` existe para dizer isso com todas as letras
a quem tentar, e a tela do Gestor não deixa ligá-lo.

**O SIMULADOR É A HOMOLOGAÇÃO.** `CorreiosFalso` faz o papel dos Correios sem
rede nenhuma: dá número ao objeto, guarda o que «postou» num arquivo ao lado
das credenciais (fora do banco, como o serviço de verdade estaria) e devolve o
AR quando alguém, na tela de homologação, diz como ele voltou. Ele **nunca abre
conexão** — há teste que derruba o `socket` e faz o caminho inteiro.

O QUE VOLTA, NORMALIZADO. Os dois transportes devolvem a mesma forma —
`estado` em `ESTADOS`, `motivo` em `MOTIVOS` —, e é o domínio
(`protesto_ar`) quem traduz o motivo para o catálogo de não-entrega desta casa.
O transporte do contrato fará a tradução dos códigos dos Correios para
`MOTIVOS`; o domínio não precisa saber que códigos são esses.

**A CHAMADA NUNCA ACONTECE DENTRO DE `db.transaction()`** — nenhuma função
daqui recebe `con`. É a regra que existe desde o selador.
"""
from __future__ import annotations

import json
import os
import re
import struct
import tempfile
import threading
import zlib
from pathlib import Path
from typing import Any

import centrais_cred as CRED


class CorreiosError(RuntimeError):
    """Não deu para falar com os Correios, ou eles recusaram."""


class CorreiosSemContrato(CorreiosError):
    """O transporte de verdade não existe enquanto não houver contrato."""


# OS ESTADOS DO OBJETO, do lado desta casa.
POSTADO, ENTREGUE, NAO_ENTREGUE = "POSTADO", "ENTREGUE", "NAO_ENTREGUE"
ESTADOS: tuple[str, ...] = (POSTADO, ENTREGUE, NAO_ENTREGUE)

# OS MOTIVOS DE NÃO-ENTREGA, normalizados. O rótulo é o que a tela mostra; a
# tradução para o catálogo da casa (`protesto_aviso.MOTIVOS_NAO_ENTREGA`) é do
# domínio, em `protesto_ar.MOTIVO_DA_CASA`.
MOTIVOS: dict[str, str] = {
    "AUSENTE": "Ausente",
    "MUDOU_SE": "Mudou-se",
    "ENDERECO_INSUFICIENTE": "Endereço insuficiente",
    "NUMERO_INEXISTENTE": "Não existe o número indicado",
    "RECUSADO": "Recusado",
    "DESCONHECIDO": "Desconhecido",
    "FALECIDO": "Falecido",
    "NAO_PROCURADO": "Não procurado",
    "FORA_DA_AREA": "Fora da área de entrega",
}

FALTA_DO_CONTRATO = (
    "o transporte dos Correios ainda não foi escrito, porque a serventia não "
    "tem contrato de AR digital. Para ligá-lo são precisos: o contrato com o "
    "serviço de AR digital, o cartão de postagem, o usuário do contrato e o "
    "código de acesso às APIs (que se informam em Administrativo → "
    "Configurações, fora do banco), e o MANUAL da API que vem com o contrato — "
    "o endereço, os campos e os códigos de retorno se transcrevem dele, e não "
    "se inventam. Até lá, use a homologação, com o serviço falso.")


# ------------------------------------------------------- a conferência

_SO_DIGITOS = re.compile(r"\D")


def _digitos(valor: Any) -> str:
    return _SO_DIGITOS.sub("", str(valor or ""))


def conferir_destinatario(destinatario: Any) -> dict:
    """O que a postagem exige do destinatário, conferido AQUI. Só calcula.

    **O CEP DE OITO DÍGITOS NÃO É ENFEITE**: é por ele que o objeto anda, e
    pré-postagem com CEP torto volta como «endereço insuficiente» depois de
    três dias — o tríduo inteiro (CN-MA art. 921, § 2º). Recusar antes custa um
    clique; recusar depois custa o prazo.
    """
    d = dict(destinatario or {})
    faltas = []
    if not str(d.get("nome") or "").strip():
        faltas.append("o nome do destinatário")
    if not str(d.get("endereco") or "").strip():
        faltas.append("o endereço (rua e número)")
    if len(_digitos(d.get("cep"))) != 8:
        faltas.append("o CEP com oito dígitos")
    if not str(d.get("cidade") or "").strip():
        faltas.append("a cidade")
    if len(str(d.get("uf") or "").strip()) != 2:
        faltas.append("a UF com duas letras")
    if faltas:
        raise CorreiosError(
            "A postagem não sai sem " + ", ".join(faltas[:-1])
            + (" e " if len(faltas) > 1 else "") + faltas[-1]
            + ". Corrija o endereço e emita um aviso novo — o endereço congela "
              "no aviso.")
    d["cep"] = _digitos(d["cep"])
    d["uf"] = str(d["uf"]).strip().upper()
    return d


def digito_do_objeto(oito: str) -> int:
    """O dígito verificador do número de objeto (oito algarismos). Só calcula.

    Pesos 8-6-4-2-3-5-9-7, módulo 11; resto 0 dá 5 e resto 1 dá 0.
    """
    pesos = (8, 6, 4, 2, 3, 5, 9, 7)
    resto = sum(int(d) * p for d, p in zip(oito, pesos)) % 11
    if resto == 0:
        return 5
    if resto == 1:
        return 0
    return 11 - resto


# ------------------------------------------------------ o serviço falso

_TRAVA_DO_ARQUIVO = threading.Lock()


def _ler_estado(arquivo: Path) -> dict:
    if not arquivo.is_file():
        return {"seq": 0, "objetos": {}}
    try:
        return json.loads(arquivo.read_text(encoding="utf-8")) or {
            "seq": 0, "objetos": {}}
    except (OSError, ValueError):
        return {"seq": 0, "objetos": {}}


def _gravar_estado(arquivo: Path, estado: dict) -> None:
    """Grava inteiro e troca de uma vez: dois cliques ao mesmo tempo não deixam
    o arquivo pela metade."""
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(arquivo.parent), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False)
    os.replace(tmp, arquivo)


def _png_do_ar(texto: str) -> bytes:
    """Uma imagem PNG pequena e válida, com o texto num comentário. Só calcula.

    É o «AR digitalizado» do simulador. Ela tem de ser PNG de verdade porque o
    comprovante do aviso confere a assinatura do arquivo
    (`protesto_aviso.ASSINATURA_DO_COMPROVANTE`), e tem de ser diferente de um
    objeto para outro porque o comprovante recusa o mesmo arquivo duas vezes.
    """
    largura = altura = 8
    cru = (b"\x00" + b"\xff\xff\xff" * largura) * altura

    def bloco(tipo: bytes, dados: bytes) -> bytes:
        return (struct.pack(">I", len(dados)) + tipo + dados
                + struct.pack(">I", zlib.crc32(tipo + dados) & 0xFFFFFFFF))

    cabeca = struct.pack(">IIBBBBB", largura, altura, 8, 2, 0, 0, 0)
    comentario = b"Comment\x00" + texto.encode("latin-1", "replace")
    return (b"\x89PNG\r\n\x1a\n" + bloco(b"IHDR", cabeca)
            + bloco(b"tEXt", comentario) + bloco(b"IDAT", zlib.compress(cru))
            + bloco(b"IEND", b""))


class CorreiosFalso:
    """O SERVIÇO FALSO — os Correios da homologação, sem rede.

    Prefixo `ZZ` nos objetos, escolhido para o simulador: o número tem a forma
    e o dígito dos de verdade (a tela e o banco os tratam igual), e a tela de
    homologação marca cada um como ensaio.
    """

    E_SIMULADOR = True
    ARQUIVO = "simulador_correios.json"
    PREFIXO = "ZZ"

    def __init__(self, ambiente: Any = CRED.HOMOLOGACAO, pasta: Any = None):
        self.ambiente = str(ambiente or CRED.HOMOLOGACAO)
        # O ESTADO MORA AO LADO DAS CREDENCIAIS, fora do banco de dados — é
        # onde o serviço de verdade estaria: do lado de fora da casa.
        pasta_do_simulador = (Path(pasta) if pasta
                              else CRED.pasta_de_dados() / "simuladores")
        self.arquivo = pasta_do_simulador / self.ARQUIVO

    def postar(self, pedido: dict) -> dict:
        """«Posta» o aviso: dá número ao objeto e guarda o destinatário."""
        destino = conferir_destinatario((pedido or {}).get("destinatario"))
        with _TRAVA_DO_ARQUIVO:
            estado = _ler_estado(self.arquivo)
            estado["seq"] = int(estado.get("seq") or 0) + 1
            oito = f"{estado['seq']:08d}"[-8:]
            codigo = f"{self.PREFIXO}{oito}{digito_do_objeto(oito)}BR"
            estado.setdefault("objetos", {})[codigo] = {
                "identificador": str((pedido or {}).get("identificador") or ""),
                "cep": destino["cep"], "estado": POSTADO}
            _gravar_estado(self.arquivo, estado)
        return {"codigo_objeto": codigo, "tarifa_centavos": None,
                "resposta": {"simulador": True, "codigo": codigo}}

    def consultar(self, codigo: Any) -> dict:
        """O estado do objeto e, se voltou, o AR com a imagem."""
        chave = str(codigo or "").strip().upper()
        with _TRAVA_DO_ARQUIVO:
            obj = (_ler_estado(self.arquivo).get("objetos") or {}).get(chave)
        if obj is None:
            raise CorreiosError(
                f"O simulador não conhece o objeto {chave or '(vazio)'}.")
        fora = {"codigo_objeto": chave, "estado": obj.get("estado") or POSTADO,
                "data": obj.get("data") or "", "recebedor": obj.get("recebedor") or "",
                "motivo": obj.get("motivo") or "", "imagem": None,
                "imagem_nome": "", "resposta": {"simulador": True,
                                                "estado": obj.get("estado")}}
        if fora["estado"] in (ENTREGUE, NAO_ENTREGUE):
            fora["imagem"] = _png_do_ar(
                f"AR SIMULADO {chave} {fora['estado']} {fora['data']}")
            fora["imagem_nome"] = f"AR-{chave}.png"
        return fora

    def simular_retorno(self, codigo: Any, *, entregue: bool, data: str,
                        recebedor: str = "", motivo: str = "") -> dict:
        """O que, nos Correios de verdade, é o carteiro: diz como o AR voltou.

        Só existe no simulador, e só a tela de homologação o chama.
        """
        chave = str(codigo or "").strip().upper()
        qual = str(motivo or "").strip().upper()
        if not entregue and qual not in MOTIVOS:
            raise CorreiosError(
                "Diga o motivo da não-entrega: " + ", ".join(MOTIVOS.values()) + ".")
        with _TRAVA_DO_ARQUIVO:
            estado = _ler_estado(self.arquivo)
            obj = (estado.get("objetos") or {}).get(chave)
            if obj is None:
                raise CorreiosError(
                    f"O simulador não conhece o objeto {chave or '(vazio)'}.")
            obj.update({"estado": ENTREGUE if entregue else NAO_ENTREGUE,
                        "data": str(data or "")[:10],
                        "recebedor": str(recebedor or "").strip() if entregue else "",
                        "motivo": "" if entregue else qual})
            _gravar_estado(self.arquivo, estado)
        return {"codigo_objeto": chave, "estado": obj["estado"]}

    def diagnostico(self) -> dict:
        return {"ok": True, "motivo": "Serviço falso desta casa: não usa rede."}


class CorreiosDoContrato:
    """A VAGA DO TRANSPORTE DE VERDADE. Recusa tudo, com a lista do que falta.

    Ele existe para a recusa ter um lugar e uma frase só, e para o dia do
    contrato: `postar`, `consultar` e `diagnostico` são os do simulador (o
    `simular_retorno` não, que é o carteiro de mentira), e é aqui que a
    tradução dos códigos dos Correios para `MOTIVOS` vai morar.
    """

    E_SIMULADOR = False

    def __init__(self, ambiente: Any = CRED.PRODUCAO, pasta: Any = None):
        self.ambiente = str(ambiente or CRED.PRODUCAO)
        self.pasta = pasta

    def postar(self, pedido: dict) -> dict:
        raise CorreiosSemContrato("Correios: " + FALTA_DO_CONTRATO)

    def consultar(self, codigo: Any) -> dict:
        raise CorreiosSemContrato("Correios: " + FALTA_DO_CONTRATO)

    def diagnostico(self) -> dict:
        return {"ok": False, "motivo": "Correios: " + FALTA_DO_CONTRATO}


# OS PROVEDORES, como a tela do Gestor os oferece. `pronto` diz se o transporte
# existe; `falso`, se as respostas são inventadas.
PROVEDORES: dict[str, dict[str, Any]] = {
    "FALSO": {"nome": "Serviço falso desta casa (homologação, sem rede)",
              "falso": True, "pronto": True, "falta": "",
              "fabrica": lambda ambiente, pasta: CorreiosFalso(ambiente, pasta)},
    "CORREIOS": {"nome": "Correios — API do contrato de AR digital",
                 "falso": False, "pronto": False, "falta": FALTA_DO_CONTRATO,
                 "fabrica": lambda ambiente, pasta: CorreiosDoContrato(ambiente, pasta)},
}
