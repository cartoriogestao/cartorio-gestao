"""As nove comunicações que o Registro Civil deve, num painel só.

    «o cartório está precisando do sistema pronto e amadurecido para o quanto
     antes» — o oficial, 29/08/2026

SÃO SEIS LINHAS E NOVE DESTINOS, E O NOVE SE CONTA
    A linha do art. 226 sozinha vale por quatro — juiz eleitoral, Ministério da
    Economia, Receita Federal e Instituto de Identificação do MA —, porque as
    quatro saem no mesmo movimento e com o mesmo prazo. **O número nove não está
    escrito em lugar nenhum deste módulo: ele é a soma dos destinos de cada
    linha**, e há teste que a confere. Número escrito à mão envelhece na tarde em
    que se escreve — foi o que o menu já custou a este projeto.

POR QUE UM PAINEL, E NÃO SEIS TELAS
    Elas já têm as suas telas — e é justamente esse o problema. **São nove
    destinos com cinco prazos diferentes**, de um dia útil a trimestral, e quem
    chega de manhã não vai abrir seis telas para saber se alguma venceu.
    Abriria uma, a que lembrasse; e a que se esquece é a que não tem trabalho
    para lembrá-la — a declaração de mês sem movimento, a relação da Junta
    Militar num mês em que não morreu ninguém.

    Este módulo **não faz nenhuma comunicação**. Ele pergunta a cada módulo
    quantas estão esperando e mostra as nove lado a lado, com o artigo, o prazo
    e a sanção. Onde há trabalho, ele leva à tela que o faz.

O QUE ELE NÃO FAZ, E POR QUÊ
    **Não engole erro.** Se um módulo não souber responder, a linha diz «não deu
    para medir» e o erro aparece — nunca zero. `ajuda_projeto` já cometeu esse
    defeito: um `except Exception: return []` transformou uma função que não
    existia em «zero pendências», quando eram nove. **Zero medido e zero por
    engano são a mesma tela e coisas diferentes.**

    **Não marca nada como resolvido.** Resolver é o clique de quem fez.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Callable


class ObrigacoesError(ValueError):
    """Erro de regra, com mensagem pronta para o balcao."""


# ------------------------------------------------------------- as nove
#
# CADA UMA COM O ARTIGO E O PRAZO MEDIDOS, e a sancao onde ela existe. A ordem e
# a do APERTO: o de um dia util vem primeiro, o trimestral por ultimo — porque e
# nessa ordem que se decide o que fazer agora.
OBRIGACOES: tuple[dict, ...] = (
    {"chave": "SIRC",
     "destino": "SIRC / INSS",
     "o_que": "tudo — nascimento, natimorto, casamento, óbito, e ainda "
              "averbação, anotação e retificação",
     "artigo": "art. 225 do Código de Normas do TJMA",
     "prazo": "1 dia útil",
     "aperto": 1,
     "sancao": "art. 92 da Lei nº 8.212/1991 e ação regressiva do INSS, "
               "inclusive por informação inexata (§ 4º)",
     "destinos": 1,
     "tela": "rcpn_sirc",
     "modulo": "sirc_remessa"},
    {"chave": "FUNAI",
     "destino": "FUNAI",
     "o_que": "o assento de nascimento de pessoa indígena",
     "artigo": "art. 253, § 2º",
     "prazo": "imediatamente",
     "aperto": 2,
     "sancao": "",
     "destinos": 1,
     "tela": "rcpn_funai",
     "modulo": "rc_funai"},
    # A CARGA E A ANOTACAO SAO A MESMA LINHA porque saem pelo mesmo canal: o
    # art. 367 manda anotar «preferencialmente pela CRC», e o art. 243 manda que
    # toda comunicacao entre serventias va por ela. Duas linhas dariam a
    # impressao de dois destinos, e e um so.
    {"chave": "CRC",
     "destino": "CRC Nacional",
     "o_que": "a carga dos registros e as anotações a outras serventias",
     "artigo": "arts. 243 e 367",
     "prazo": "5 dias",
     "aperto": 3,
     "sancao": "",
     "destinos": 1,
     "tela": "rcpn_crc",
     "tambem": ("rcpn_anotacoes", "As anotações devidas"),
     "modulo": "crc_carga"},
    {"chave": "OBITO_MENSAL",
     "destino": "juiz eleitoral, Ministério da Economia, Receita Federal e "
                "Instituto de Identificação do MA",
     "o_que": "os óbitos do mês, cada destino com o seu filtro",
     "artigo": "art. 226",
     "prazo": "5º dia útil do mês seguinte",
     "aperto": 4,
     "sancao": "art. 293 do Código Eleitoral para o eleitoral; "
               "responsabilização do titular (§ 2º)",
     # QUATRO DESTINOS NUMA LINHA SO, porque saem no mesmo movimento e com o
     # mesmo prazo — mas cada um tem o SEU filtro, e os filtros sao da norma.
     "destinos": 4,
     "tela": "rcpn_comunicacoes",
     "modulo": "rc_comunicacoes"},
    {"chave": "JUNTA_MILITAR",
     "destino": "Junta de Serviço Militar",
     "o_que": "os óbitos de homens de 17 a 45 anos",
     "artigo": "Lei nº 4.375/1964",
     "prazo": "mensal",
     "aperto": 5,
     "sancao": "",
     "destinos": 1,
     "tela": "rcpn_comunicacoes",
     "modulo": "rc_comunicacoes"},
    {"chave": "IBGE",
     "destino": "IBGE",
     "o_que": "o mapa trimestral de nascimentos, casamentos e óbitos",
     "artigo": "art. 224",
     "prazo": "dia 8 de janeiro, abril, julho e outubro",
     "aperto": 6,
     "sancao": "multa de 1 a 5 salários mínimos, «sem prejuízo da ação penal»",
     "destinos": 1,
     # ESTA LINHA NAO SE MEDE POR CONTAGEM, E ISSO E UM BURACO DECLARADO.
     # As outras cinco contam o que espera porque cada ato pendente e uma
     # linha; a do IBGE e um mapa TRIMESTRAL, e saber se ele ja foi mandado
     # exige guardar o que saiu — coisa que este sistema **nao guarda**.
     #
     # Poderia sair daqui uma contagem de atos do trimestre, que teria cara de
     # medicao e responderia outra pergunta. Em vez disso a linha mostra o
     # **prazo** e diz, com todas as letras, que o envio nao e acompanhado.
     # Numero que responde a pergunta errada e pior que numero nenhum.
     # ESTA LINHA MOSTRA PRAZO **E** CONTAGEM, e e a unica assim.
     #
     # As outras cinco contam o que espera porque cada ato pendente e uma linha.
     # A do IBGE e um mapa TRIMESTRAL: ela conta **trimestres que deviam ter
     # sido entregues e nao foram**, e mostra tambem quando vence o proximo —
     # porque num prazo trimestral saber que faltam zero hoje nao diz quando
     # falta comecar a montar o de amanha.
     #
     # **ATE 30/08/2026 ELA SO MOSTRAVA O PRAZO**, e declarava o buraco: o
     # sistema montava o mapa e nao guardava o que saiu. `ib_entregas` fechou
     # isso, e o campo `buraco` saiu junto — **buraco fechado que continua
     # declarado e o carimbo que mente outra vez**.
     "mede": "PRAZO",
     "tela": "rcpn_ibge",
     "modulo": "ibge_geracao"},
)

# **A JUNTA MILITAR NAO ESTA NO CODIGO DE NORMAS**, e por isso quase se perdeu:
# quem le so o Codigo nao a encontra. Ela e da Lei 4.375/1964, e esta aqui para
# que ninguem precise se lembrar dela sozinho.
FORA_DO_CODIGO_DE_NORMAS = ("JUNTA_MILITAR",)

# O DIA DO MES EM QUE O IBGE VENCE, e os meses em que ele vence. Art. 224.
IBGE_DIA = 8
IBGE_MESES = (1, 4, 7, 10)


def quantos_destinos() -> int:
    """Quantos órgãos esperam papel desta casa. Só soma.

    **O NÚMERO NÃO ESTÁ ESCRITO EM LUGAR NENHUM**: ele é a soma dos destinos de
    cada linha. Escrevê-lo à mão faria o painel dizer «nove» no dia em que
    virassem dez — é o defeito do menu, e o do carimbo da versão que mentia.

    Escrevendo esta função eu me corrigi: o cabeçalho dizia sete linhas, e são
    seis. Foi a soma que respondeu, e não a minha contagem.
    """
    return sum(int(x.get("destinos", 0)) for x in OBRIGACOES)


def por_aperto() -> tuple[dict, ...]:
    """As obrigações do prazo mais curto para o mais longo. Só ordena.

    **É NESSA ORDEM QUE SE DECIDE O QUE FAZER AGORA**, e não na ordem em que os
    módulos foram escritos.
    """
    return tuple(sorted(OBRIGACOES, key=lambda x: x["aperto"]))


def _quantas(modulo: str, con: sqlite3.Connection) -> dict:
    """Quantas esperam naquele módulo — ou por que não deu para medir.

    **NÃO ENGOLE ERRO.** `ajuda_projeto` chamava uma função que não existia e um
    `except Exception: return []` transformava isso em «zero pendências», quando
    eram nove. Zero medido e zero por engano são a mesma tela e coisas
    diferentes: aqui, o que não se mediu volta com o motivo à vista.
    """
    import importlib
    try:
        alvo = importlib.import_module(modulo)
    except ImportError as erro:
        return {"quantas": None, "erro": f"o módulo {modulo} não carregou: {erro}"}
    for nome in ("quantas_pendentes", "pendentes", "pendentes_de_remessa",
                 "pendentes_de_carga"):
        funcao: Callable[..., Any] | None = getattr(alvo, nome, None)
        if funcao is None:
            continue
        try:
            resposta = funcao(con)
        except Exception as erro:            # noqa: BLE001 — o motivo vai à tela
            return {"quantas": None,
                    "erro": f"{modulo}.{nome} não respondeu: {erro}"}
        return {"quantas": resposta if isinstance(resposta, int)
                else len(resposta), "erro": ""}
    return {"quantas": None,
            "erro": f"o módulo {modulo} não tem por onde contar o que espera"}


def painel(con: sqlite3.Connection, *, hoje: str = "") -> list[dict]:
    """As seis linhas, do prazo mais curto ao mais longo, com o que espera.

    SÓ LÊ, e **não faz comunicação nenhuma**: pergunta a cada módulo quantas
    estão esperando. Onde há trabalho, a linha leva à tela que o faz.
    """
    saida = []
    for o in por_aperto():
        linha = dict(o)
        linha.update(_quantas(o["modulo"], con))
        if o.get("mede") == "PRAZO" and hoje:
            # O PRAZO VEM POR CIMA DA CONTAGEM, e nao no lugar dela: as duas
            # respondem perguntas diferentes — quantos trimestres estao em
            # atraso, e quando vence o proximo.
            linha.update(ibge_vence_em(hoje))
        linha["fora_do_codigo"] = o["chave"] in FORA_DO_CODIGO_DE_NORMAS
        saida.append(linha)
    return saida


def ibge_vence_em(hoje: str) -> dict:
    """Quando vence o mapa do IBGE, e se já passou. Só calcula.

    **O IBGE É O ÚNICO COM MULTA EM DINHEIRO** — de 1 a 5 salários mínimos, «sem
    prejuízo da ação penal» (art. 224) — e era o único cujo prazo o sistema não
    conhecia: `ibge_geracao` monta o mapa e não sabia que existia um dia 8.
    """
    from datetime import date
    bruto = _texto(hoje)[:10]
    if len(bruto) != 10 or bruto[4] != "-" or bruto[7] != "-":
        raise ObrigacoesError("Diga a data de hoje no formato AAAA-MM-DD.")
    try:
        agora = date(int(bruto[:4]), int(bruto[5:7]), int(bruto[8:10]))
    except ValueError as erro:
        raise ObrigacoesError(f"Essa data não existe: {bruto}.") from erro
    for ano in (agora.year, agora.year + 1):
        for mes in IBGE_MESES:
            venc = date(ano, mes, IBGE_DIA)
            if venc >= agora:
                # O TRIMESTRE QUE VENCE NAO E O TRIMESTRE QUE SE REPORTA. O dia
                # 8 de outubro entrega julho, agosto e setembro — o trimestre
                # **anterior**. Rotular o vencimento com o trimestre em que ele
                # cai poria o arquivo com o periodo errado numa obrigacao que
                # tem multa em dinheiro.
                trimestre = IBGE_MESES.index(mes)          # 0=jan, 1=abr, ...
                reportado = trimestre or 4                 # jan reporta o 4o
                ano_reportado = ano - 1 if mes == 1 else ano
                return {"vence_em": venc.isoformat(),
                        "faltam": (venc - agora).days,
                        "trimestre_reportado": reportado,
                        "ano_reportado": ano_reportado,
                        "meses_reportados": _meses_do_trimestre(reportado)}
    raise ObrigacoesError("Não deu para achar o próximo vencimento do IBGE.")


def _texto(v: Any) -> str:
    """O valor como texto, e vazio quando não há. Nunca `str(v or "")`."""
    if v is None:
        return ""
    return str(v).strip()


def _meses_do_trimestre(trimestre: int) -> tuple[int, int, int]:
    """Os três meses que aquele trimestre cobre. Só calcula."""
    primeiro = (trimestre - 1) * 3 + 1
    return (primeiro, primeiro + 1, primeiro + 2)
