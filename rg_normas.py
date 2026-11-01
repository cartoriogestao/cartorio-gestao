"""O QUE CONFERIR NA QUALIFICAÇÃO DO RCPJ E DO RTD, com o artigo ao lado. SÓ LÊ.

    «[...] nos termos da Lei 6015, código nacional de normas e código de normas
     do TJMA.»                                         — o oficial, 01/11/2026

A LISTA LEMBRA; QUEM DECIDE É QUEM QUALIFICA. Nada aqui recusa título: os avisos saem
do que está escrito na natureza e no nome, e palavra em texto não decide ato. Quem lê o
papel é a pessoa. É a régua do CNIB e do usucapião, e por isso o módulo não grava nada.

OS ARTIGOS SÃO OS DO CÓDIGO DE NORMAS DA CGJ/TJMA (CN-MA), lido em 01/11/2026, e os da
Lei 6.015/1973. A norma é estadual: quem usa o sistema noutro estado confere a dele.
"""
from __future__ import annotations

from typing import Any

from pt_schema import normalizar_nome

RCPJ, RTD = 3, 4


def _regra(artigo: str, texto: str) -> dict:
    return {"artigo": artigo, "texto": texto}


# Geral é o que vale para qualquer título daquela atribuição.
GERAL: dict[int, tuple[dict, ...]] = {
    RCPJ: (
        _regra("CN-MA art. 402, § 1º",
               "É vedado, na mesma comarca, registrar pessoa jurídica com nome idêntico ou "
               "semelhante a outro já existente, que possa causar dúvida aos usuários."),
        _regra("CN-MA art. 407, II",
               "Se o funcionamento depende de aprovação de autoridade, só se registra depois "
               "de apresentada a autorização."),
        _regra("CN-MA art. 407, III",
               "Atividade privativa de profissional habilitado: comprovar antes a qualificação "
               "no órgão de classe."),
        _regra("CN-MA art. 407, IV",
               "O contrato ou estatuto leva a participação de advogado, com o número da OAB, "
               "ressalvado o art. 9º, § 2º, da Lei Complementar 123/2006."),
        _regra("CN-MA art. 407, V",
               "Ato de pessoa jurídica cujos atos constitutivos não estejam registrados nesta "
               "serventia não se registra."),
        _regra("CN-MA art. 407, VI",
               "Filial de outra circunscrição: antes, a averbação à margem do registro de "
               "origem, por certidão de inteiro teor de até 30 dias."),
        _regra("CN-MA art. 407, VII",
               "A denominação não pode conter tribunal, cartório, registro, notário, "
               "tabelionato, ofício, derivações, nem o que induza a erro sobre a atividade."),
        _regra("CN-MA art. 407, IX",
               "A sede tem de ter endereço completo: não basta a comarca ou a cidade."),
        _regra("CN-MA art. 421",
               "Alteração da pessoa jurídica se averba em oito dias da apresentação, cada ato "
               "com requerimento próprio."),
    ),
    RTD: (
        _regra("CN-MA art. 966",
               "Lançar no Protocolo a data, a natureza, a espécie de lançamento (integral, "
               "extrato ou averbação) e o apresentante, e reproduzir no título o número, a "
               "data e a espécie."),
        _regra("CN-MA art. 968", "Depois de lançar, anotar no Protocolo o número do registro."),
        _regra("CN-MA art. 958, §§ 4º e 5º",
               "Vinte dias da assinatura para apresentar, no domicílio dos contratantes; depois "
               "disso ainda se registra, com efeito contra terceiros desde a apresentação."),
        _regra("CN-MA art. 959",
               "Cópia, mesmo autenticada, não se registra, salvo para guarda e conservação ou "
               "como anexo de documento original."),
        _regra("CN-MA art. 957, §§ 2º e 3º",
               "Ato de RCPJ não se lança no RTD, e ato constitutivo de sociedade não registrada "
               "no RCPJ não se registra aqui, salvo disposição legal."),
        _regra("CN-MA art. 974, § 1º",
               "O recibo traz a data da apresentação, o número de ordem e a data prevista "
               "para a entrega."),
        _regra("CN-MA art. 975",
               "A recusa vai em nota devolutiva fundamentada. Com suspeita de falsificação, o "
               "registro pode ser sobrestado depois de protocolar: siga os §§ 1º a 3º."),
    ),
}

# (palavras que, na natureza, puxam a regra), atribuição, regra.
POR_NATUREZA: tuple[tuple[tuple[str, ...], int, dict], ...] = (
    (("cooperativa", "factoring", "fomento mercantil", "firma individual"), RCPJ, _regra(
        "CN-MA art. 407, I",
        "É vedado o registro de sociedade cooperativa, de empresa de factoring e de firma "
        "individual.")),
    (("conservacao", "facultativo", "livro f"), RTD, _regra(
        "CN-MA art. 957, §§ 4º e 5º",
        "O registro facultativo só conserva e autentica data e conteúdo: não dá publicidade "
        "nem efeito contra terceiros, e isso se esclarece antes ao interessado.")),
    (("busca e apreensao", "consolidacao"), RTD, _regra(
        "CN-MA arts. 955 e 956",
        "Consolidação fiduciária e busca e apreensão têm procedimento próprio, que este "
        "sistema ainda não conduz: siga o artigo à mão.")),
    (("imovel", "imoveis"), RTD, _regra(
        "CN-MA art. 962",
        "Aquisição ou alienação de imóvel por instrumento particular se comunica à Receita "
        "Federal (DOI), e o comprovante se arquiva com o ato.")),
    (("notificacao",), RTD, _regra(
        "CN-MA arts. 986 a 993", "A notificação tem tela própria, depois do registro.")),
)

PALAVRAS_RESERVADAS = ("tribunal", "cartorio", "registro", "notario", "tabelionato", "oficio")


def regras_gerais(atribuicao: int) -> tuple[dict, ...]:
    """O que se confere em todo título daquela atribuição."""
    return GERAL[int(atribuicao)]


def para_a_natureza(atribuicao: int, natureza: Any) -> list[dict]:
    """As regras que a natureza escrita puxa. Sem natureza, nenhuma."""
    texto = normalizar_nome(natureza) or ""
    return [regra for palavras, atrib, regra in POR_NATUREZA
            if atrib == int(atribuicao) and any(p in texto for p in palavras)]


def avisos_do_nome(nome: Any) -> list[str]:
    """As palavras reservadas do art. 407, VII, achadas num nome. Lembrete: não recusa."""
    palavras = (normalizar_nome(nome) or "").split()
    return [p for p in PALAVRAS_RESERVADAS if p in palavras]


def nomes_parecidos(con, nome: Any, *, registro_id: int | None = None) -> list[dict]:
    """Pessoas jurídicas desta serventia com o mesmo nome (CN-MA art. 402, § 1º). Só LÊ.

    Compara em Python, com a `normalizar_nome` da casa. Só o idêntico depois de
    normalizar: o «semelhante» do artigo é juízo de quem qualifica, e outra serventia
    da mesma comarca (§ 2º) este sistema não enxerga.
    """
    from bd_nativo import banco
    alvo = normalizar_nome(nome) or ""
    if not alvo:
        return []
    saida = []
    for r in banco(con).ler(
            """SELECT id, numero, requerente_nome FROM rg_registros
                WHERE atribuicao = %s AND serie = 'PJ_A'""", (RCPJ,)):
        if registro_id is not None and int(r["id"]) == int(registro_id):
            continue
        if (normalizar_nome(r["requerente_nome"]) or "") == alvo:
            saida.append(dict(r))
    return saida
