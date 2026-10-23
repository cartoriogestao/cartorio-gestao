"""O que a CRC e o SIRC exigem, conferido NA LAVRATURA do assento novo.

    «não deixar lavrar registro de nascimento, casamento e óbitos, e demais
     rcpn, se todos os campos para envio da CRC e SIRC não estejam
     preenchidos» — relato #130 do oficial, 14/10/2026, na tela
     `rcpn_assento_editar` (3.6.291), reiterando «a falha de não conseguir
     enviar a carga porque falta algum campo».

O DEFEITO ERA DE ORDEM, E NÃO DE RÉGUA
    As duas réguas já existiam e funcionavam: `crc_carga.o_que_falta` retém o
    assento que a CRC recusaria, e `sirc_remessa.o_que_falta` o que o SIRC
    recusaria. O problema é QUANDO elas rodavam — na hora de montar a carga,
    dias depois, com o assento já no livro, numerado, com folha e selo. O que
    faltava então só se consertava pela tela de editar, e o declarante já não
    estava no balcão.

    Este módulo **não escreve uma terceira lista de campos**. Ele chama as duas
    réguas da carga sobre o assento recém-montado, DENTRO da transação da
    lavratura e antes do commit. Uma lista própria divergiria da carga no
    primeiro conserto — e o balcão lavraria o que a carga depois retém, que é
    exatamente o defeito relatado.

SÓ O ATO NOVO DO BALCÃO
    `rc_assento.lavrar_assento` só chama a recusa quando a origem é MANUAL. A
    carga do acervo (EOFICIO, IMPORTACAO, ARQUIVO, ACERVO digitado) traz o que
    o livro de papel já tem: recusá-la não completaria o papel — só deixaria o
    assento fora do sistema. Para esses, a tela de editar AVISA o que falta
    (`o_que_falta`, sem recusar), para o balcão completar os antigos.

ESPÉCIES
    CRC: as de `crc_carga.MOVIMENTO_DA_ESPECIE` (nascimento, natimorto,
    casamento, casamento religioso, óbito). SIRC: as de
    `sirc_remessa.ESPECIES_PRONTAS_PARA_O_SIRC` (as mesmas cinco). As do Livro
    E, proclamas e «outro» não têm carga em nenhuma das duas, e ficam como
    estavam.
"""
from __future__ import annotations

from typing import Any

import rc_conferencia_dados as CONF
from bd_nativo import banco
from rc_assento import ConferenciaError

CRC = "CRC"
SIRC = "SIRC"

#: O código do problema no formato de `rc_conferencia_dados` — a tela de
#: conferência já desenha a lista, e a recusa entra no mesmo caminho.
CODIGO_DA_CENTRAL = {CRC: "FALTA_PARA_A_CRC", SIRC: "FALTA_PARA_O_SIRC"}

NOME_DA_CENTRAL = {CRC: "a CRC Nacional", SIRC: "o SIRC (INSS)"}


class FaltaParaAsCentraisError(ConferenciaError):
    """A lavratura recusada porque falta o que a CRC ou o SIRC exigem.

    É `ConferenciaError` (e portanto `ValueError`) de propósito: a rota já
    devolve a conferência com tudo o que foi digitado guardado quando recebe
    uma, e a transação volta atrás — nada fica no livro, nem número, nem folha.
    """


def _texto(v: Any) -> str:
    return "" if v is None else str(v).strip()


def o_que_falta(con, assento_id: int, *,
                para_lavratura: bool = False) -> list[dict]:
    """O que impede este assento de ir à CRC e ao SIRC. SÓ LÊ.

    Cada item: `{"central": "CRC"|"SIRC", "falta": <frase da régua da carga>}`.

    `para_lavratura=True` confere as duas centrais sempre (é ato novo, e vai às
    duas). Sem ele — a tela de editar —, o SIRC só é conferido para o que a
    remessa do SIRC alcança: o acervo do E-Ofício e o arquivo não vão a ele
    (`ORIGENS_QUE_NAO_SE_REMETEM`), salvo a carga do acervo em .docx
    (`ORIGENS_DA_CARGA_DO_ACERVO`). Avisar do SIRC num assento que nunca irá
    ao SIRC seria o alarme que soa sempre.
    """
    import crc_carga as CRCM
    import sirc_remessa as SIRCM

    linha = banco(con).um("SELECT * FROM rc_assentos WHERE id = %s",
                          (int(assento_id),))
    if not linha:
        return []
    assento = dict(linha)
    especie = _texto(assento.get("especie")).upper()
    faltas: list[dict] = []

    # A CRC — a mesma chamada de `crc_carga.montar`, com as pessoas
    # montadas pela mesma função que ela usa.
    if especie in CRCM.MOVIMENTO_DA_ESPECIE:
        pessoas = CRCM._pessoas_do_assento(con, assento["id"])
        for frase in CRCM.o_que_falta(con, assento, pessoas):
            faltas.append({"central": CRC, "falta": frase})

    # O SIRC — o registro com a forma de `sirc_remessa.pendentes_de_remessa`
    # (`tipo` é a espécie, `assento_id` o id). A linha inteira vai junto:
    # `o_que_falta` lê `ibge_local_nascimento` dela quando a tem.
    origem = _texto(assento.get("origem")).upper()
    vai_ao_sirc = (para_lavratura
                   or origem not in SIRCM.ORIGENS_QUE_NAO_SE_REMETEM
                   or origem in SIRCM.ORIGENS_DA_CARGA_DO_ACERVO)
    if especie in SIRCM.ESPECIES_PRONTAS_PARA_O_SIRC and vai_ao_sirc:
        registro = {**assento, "assento_id": assento["id"],
                    "tipo": especie, "onde": "rc_assentos"}
        for frase in SIRCM.o_que_falta(con, registro):
            faltas.append({"central": SIRC, "falta": frase})
    return faltas


def problemas(faltas: list[dict]) -> list[dict]:
    """As faltas no formato de `rc_conferencia_dados` — gravidade BLOQUEIA."""
    return [{"gravidade": CONF.BLOQUEIA,
             "codigo": CODIGO_DA_CENTRAL[f["central"]],
             "mensagem": f"Para {NOME_DA_CENTRAL[f['central']]}: {f['falta']}.",
             "campo": ""}
            for f in faltas]


def mensagem_de_recusa(faltas: list[dict]) -> str:
    """O texto da recusa, em português de balcão: cada campo, e para qual
    central."""
    partes = []
    for central in (CRC, SIRC):
        frases = [f["falta"] for f in faltas if f["central"] == central]
        if frases:
            partes.append(f"para {NOME_DA_CENTRAL[central]} falta: "
                          + "; ".join(frases))
    return ("O assento não foi lavrado: ele iria ao livro sem o que as "
            "centrais exigem, e a carga o recusaria depois — "
            + " — ".join(partes)
            + ". Preencha no formulário («Voltar e editar») e lavre de novo. "
              "Nada foi gravado: nem número, nem folha, nem selo.")
