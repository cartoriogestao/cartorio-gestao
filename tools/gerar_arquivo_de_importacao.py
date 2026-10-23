# -*- coding: utf-8 -*-
"""ESCREVE O ARQUIVO QUE O SISTEMA IMPORTA — o último passo da esteira.

    `.docx` → `extrair_rcpn_docx` → `conferir_para_a_crc` → **este** → o botão
    de importar do sistema.

AS PESSOAS VÃO DENTRO DO REGISTRO — decisão do oficial em 12/09/2026
    **E ISTO ERA UM BURACO, e não um detalhe de formato.** `importar_padrao`
    gravava **uma tabela** — `rc_assentos` — e a CRC lê o **sexo** e o
    **município de nascimento** do `REGISTRADO`, e a filiação do `PAI` e da
    `MAE`, que moram em `rc_pessoas`. Sem elas, todo assento importado entraria
    já reprovado: «o sexo do registrado» e «o município de nascimento» são
    faltas que **retêm** o registro na Central — exatamente o que ele pediu
    para evitar.

    Eram dois caminhos, e ele escolheu o primeiro: **ampliar o padrão** para
    aceitar as pessoas junto, em vez de carregá-las numa segunda passada. A
    razão dele vale escrita: dois passos para um fato só é um dia em que alguém
    faz o primeiro, esquece o segundo, e o livro fica pela metade.

    Então este gerador escreve **um arquivo só**, e o botão de importar do
    sistema o lê inteiro — conferido: `importar_padrao.conferir` aceitou os
    343 registros da primeira leva sem uma recusa.

O QUE ENTRA, E O QUE NÃO — decisão do oficial em 12/09/2026
    «os que foram importados sem elemento essencial para a CRC, deixar em
     quarentena pendente de complemento. não entra nas cargas de envio»

    **O INCOMPLETO ENTRA.** Ele vira assento, e a Central não o recebe até
    alguém completar: quem o retém é `crc_carga.montar`, que o deixa fora do
    XML e o devolve em `retidos` — e a tela da carga agora o mostra **antes**
    de montar, em `em_quarentena`. A quarentena é derivada do que falta, e o
    assento sai dela sozinho quando o dado entra.

    **E O ERRADO NÃO ENTRA — a linha é minha, e está aqui para ele corrigir.**
    Faltar e estar errado são coisas diferentes: campo vazio não afirma nada,
    e campo errado afirma. Então fica de fora o que o próprio documento
    desmente:

      · a data do nascimento é DEPOIS da data do registro;
      · o ano de dentro da matrícula não é o ano do registro — a Central
        recusa, e a matrícula certa vai calculada ao lado, para ele decidir.

    Gravar esses seria pôr no livro um ato que contradiz o papel de onde veio,
    com cara de completo. Eles voltam numa lista, com o motivo.

    E **o que `o_que_arrumar` avisa ENTRA**, porque a Central aceita: reter
    aqui seria mais severo que a norma, o erro que este projeto já cometeu
    uma vez com a filiação.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any

RAIZ_DO_SISTEMA = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if RAIZ_DO_SISTEMA not in sys.path:
    sys.path.insert(0, RAIZ_DO_SISTEMA)

import importar_padrao as PADRAO  # noqa: E402
from extrair_rcpn_docx import MARCA_DA_DATA_DERIVADA  # noqa: E402

DE_ONDE_VEIO = "acervo desta serventia, em .docx (certidões e termos)"

# As colunas que o `rc_assentos` NÃO recebe pelo padrão — elas são do sistema,
# e não do arquivo.
NAO_SAO_DO_ARQUIVO = {"id", "criado_em", "criado_por", "importacao_id",
                      "origem"}

# As faltas em que o PAPEL SE CONTRADIZ — e não apenas cala. Estas não entram.
CONTRADIZ_O_PROPRIO_PAPEL = (
    "é depois da data do registro",
    "ano dentro da matrícula",
)


def _campos_da_especie(con) -> set:
    """Os campos que a espécie aceita — **medidos do esquema**, como manda o
    próprio padrão: lista escrita à mão envelhece na tarde em que se escreve."""
    return {c["nome"] for c in PADRAO.campos(con, "RCPN_ASSENTO")}


def montar(con, conferidos: list[dict], atos: list[dict]) -> dict:
    """Os dois arquivos, a partir do que já foi lido e conferido.

    **`atos` É A LISTA JÁ JUNTADA — um por matrícula —, e não a extração
    crua.** Até 12/09/2026 esta função recebia os documentos brutos e os
    reindexava por matrícula com um dicionário: **o ÚLTIMO da lista ganhava**,
    enquanto a conferência da CRC tinha olhado o mais forte
    (`conferir_para_a_crc.juntar_o_mesmo_ato`). Eram duas réguas para «qual
    documento é este ato», e o arquivo podia sair de um papel diferente do que
    foi conferido. A recusa abaixo existe para isso não voltar calado.
    """
    por_matricula: dict[str, dict] = {}
    for e in atos:
        if not e.get("entra"):
            continue
        chave = e["assento"]["matricula"]
        if chave in por_matricula:
            raise ValueError(
                "chegaram DOIS documentos com a matrícula " + chave + " — "
                "esta função monta a partir dos atos já juntados; passe "
                "`conferir_para_a_crc.juntar_o_mesmo_ato(...)` antes, senão o "
                "arquivo sai de um papel e a conferência falou de outro")
        por_matricula[chave] = e
    conhecidos = _campos_da_especie(con)

    obrigatorios = {c["nome"] for c in PADRAO.campos(con, "RCPN_ASSENTO")
                    if c["obrigatorio"]}
    das_pessoas = {c["nome"]
                   for c in PADRAO.campos_da_pessoa(con, "RCPN_ASSENTO")}
    campo_das_pessoas = PADRAO.MODELOS["RCPN_ASSENTO"]["pessoas"]["campo"]

    registros, a_conferir, deixados, quarentena = [], [], [], []
    conferir_a_data = []
    for conferido in conferidos:
        lido = por_matricula.get(conferido["matricula"])
        if not lido:
            continue

        # **O QUE O DOCUMENTO DESMENTE FICA DE FORA; o que apenas falta,
        # entra.** Ver o cabeçalho: campo vazio não afirma nada, campo errado
        # afirma — e o errado aqui é o papel contradizendo a si mesmo.
        #
        # **DATA DERIVADA NÃO CONTRADIZ PAPEL NENHUM.** Quando a data do
        # registro é a do nascimento — porque o livro não a traz —, o ano dela
        # não tem por que bater com o da matrícula, e o desencontro é entre a
        # matrícula e um valor que ESTA FERRAMENTA pôs ali. Tratá-lo como «o
        # papel se contradiz» jogaria fora justamente os assentos que a decisão
        # do oficial mandou trazer. Eles vão para a quarentena, onde a falta
        # fica escrita e alguém a resolve com o livro na mão.
        derivada = MARCA_DA_DATA_DERIVADA in str(
            lido["assento"].get("dados_json") or "")
        errado = [f for f in conferido["o_que_falta"]
                  if any(marca in f for marca in CONTRADIZ_O_PROPRIO_PAPEL)
                  and not (derivada and "ano dentro da matrícula" in f)]
        if errado:
            deixados.append({"matricula": conferido["matricula"],
                             "arquivo": conferido["arquivo"],
                             "porque": conferido["o_que_falta"]})
            continue
        em_falta_para_a_crc = list(conferido["o_que_falta"])
        bruto: dict[str, Any] = {
            PADRAO.CAMPO_DA_CHAVE: lido["assento"]["matricula"]}
        for nome, valor in lido["assento"].items():
            if nome in NAO_SAO_DO_ARQUIVO or nome not in conhecidos:
                continue
            if valor not in (None, ""):
                bruto[nome] = valor

        # **SÓ VÃO OS CAMPOS QUE A PESSOA ACEITA, e a lista é medida do
        # esquema pelo próprio padrão.** Mandar um campo a mais faz o padrão
        # recusar o registro inteiro — e ele recusa com razão: campo
        # desconhecido é o erro mais fácil de cometer e o mais difícil de ver.
        pessoas = []
        for pessoa in lido["pessoas"]:
            limpa = {k: v for k, v in pessoa.items()
                     if k in das_pessoas and v not in (None, "")}
            if limpa.get("nome") and limpa.get("papel"):
                pessoas.append(limpa)
        if pessoas:
            bruto[campo_das_pessoas] = pessoas

        # **HÁ FALTA QUE NEM A QUARENTENA SEGURA: a que o BANCO não admite.**
        # `rc_assentos.nome` é NOT NULL, e com razão — assento sem nome não é
        # assento. A lista de obrigatórios é **medida pelo próprio padrão**, e
        # não escrita aqui: coluna nova entra nela sozinha.
        sem_o_obrigatorio = sorted(
            o for o in obrigatorios if not str(bruto.get(o) or "").strip())
        if sem_o_obrigatorio:
            deixados.append({
                "matricula": conferido["matricula"],
                "arquivo": conferido["arquivo"],
                "porque": [f"o assento não tem {', '.join(sem_o_obrigatorio)}, "
                           f"que o banco exige — nem em quarentena ele entra"]
                          + conferido["o_que_falta"]})
            continue
        if em_falta_para_a_crc:
            quarentena.append({"matricula": conferido["matricula"],
                               "arquivo": conferido["arquivo"],
                               "falta_para_a_crc": em_falta_para_a_crc})
        # O documento traz data de registro e ela não se leu: o assento entrou
        # com a do nascimento, e **isto pede o livro**.
        ilegivel = [d for d in conferido["duvidas_da_leitura"]
                    if "data ilegível" in d]
        if ilegivel:
            conferir_a_data.append({"matricula": conferido["matricula"],
                                    "arquivo": conferido["arquivo"],
                                    "porque": ilegivel})
        registros.append(bruto)

        # **O QUE A CENTRAL AVISA VIAJA SEPARADO DO ARQUIVO**, porque não é
        # dado do assento: é trabalho para alguém. Pô-lo dentro do registro
        # faria o padrão recusar por campo desconhecido, e com razão.
        pendencias = conferido["o_que_arrumar"] + conferido["duvidas_da_leitura"]
        if pendencias:
            a_conferir.append({"chave": lido["assento"]["matricula"],
                               "arquivo": lido["arquivo"],
                               "o_que_conferir": pendencias})

    return {
        "assentos": {
            "formato": PADRAO.FORMATO,
            "versao": PADRAO.VERSAO,
            "especie": "RCPN_ASSENTO",
            "de_onde_veio": DE_ONDE_VEIO,
            "registros": registros,
        },
        "a_conferir": {
            "o_que_e": "o que a régua da CRC avisa e o que a leitura do "
                       "documento deixou em dúvida — o registro ENTRA, e isto "
                       "é o que fica para alguém conferir no livro",
            "assentos": a_conferir,
        },
        "conferir_a_data_no_livro": {
            "o_que_e": "entraram com a data do NASCIMENTO como data de "
                       "registro, mas o documento traz uma data de registro "
                       "que não foi possível ler — quase sempre erro de "
                       "digitação no próprio papel. A frase original está "
                       "gravada no assento; estes pedem uma ida ao livro",
            "assentos": conferir_a_data,
        },
        "em_quarentena": {
            "o_que_e": "entram no livro e NÃO vão para a Central até serem "
                       "completados — a tela da carga da CRC os mostra com o "
                       "que falta, e eles saem da quarentena sozinhos quando "
                       "o dado entrar",
            "assentos": quarentena,
        },
        "ficaram_de_fora": deixados,
    }


if __name__ == "__main__":
    import banco_pg
    import conferir_para_a_crc as CONF

    conferencia, extracao, banco, prefixo = sys.argv[1:5]
    with open(conferencia, encoding="utf-8") as f:
        conferidos = json.load(f)["conferidos"]
    with open(extracao, encoding="utf-8") as f:
        extraidos = json.load(f)
    # **A MESMA RÉGUA DA ESTEIRA, e não uma parecida** — sem isto o dicionário
    # de `montar` recusaria o segundo documento do mesmo ato, que é o certo:
    # quem decide qual papel vale é `juntar_o_mesmo_ato`, num lugar só.
    atos, _ = CONF.juntar_o_mesmo_ato(extraidos)
    # PELA PORTA DO BANCO: `importar_padrao` já é nativo e recusa o `sqlite3`
    # cru, e fora do sistema ninguém instala o desvio do `sqlite3.connect`.
    con = banco_pg.conectar(f"file:{banco}?mode=ro", uri=True)
    try:
        saida = montar(con, conferidos, atos)
    finally:
        con.close()

    for nome in ("assentos", "pessoas"):
        caminho = f"{prefixo}_{nome}.json"
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(saida[nome], f, ensure_ascii=False, indent=2)
        print(f"{nome:10} -> {caminho}")
    print(f"assentos no arquivo : {len(saida['assentos']['registros'])}")
    print(f"ficaram de fora     : {len(saida['ficaram_de_fora'])}")
