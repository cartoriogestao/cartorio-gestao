# -*- coding: utf-8 -*-
"""As páginas digitalizadas que estão no disco e o banco não conhece.

    «precisamos criar uma ferramenta para subir matrículas antigas, com
     digitalização, indicadores e etc»        — o oficial, 04/09/2026

O QUE JÁ ESTAVA FEITO, e foi medido antes de escrever qualquer linha
    A digitalização **já está dentro do sistema**: `ri_imagens` tem 3.667
    linhas, todas com `caminho_interno` e copiadas em 13/08/2026. E
    `ri_imagens.py` resolve o casamento nome-do-banco → arquivo-no-disco, com
    a armadilha do `.0001` — que é **número de página, e não extensão** — já
    tratada.

    > **E eu quase disse ao oficial que o sistema não sabia das imagens.**
    > Procurei em `attachments`, achei zero, e concluí. Elas moram em
    > `ri_imagens`. **Sétima vez neste projeto que procurar pelo nome errado
    > produz a conclusão errada** — e desta vez eu ia dizer a ele.

O BURACO DE VERDADE, MEDIDO EM 04/09/2026
    | | |
    |---|---|
    | páginas no disco | **10.227** |
    | páginas no banco | **3.667** |
    | **faltando** | **6.560** |
    | matrículas digitalizadas | 1.626 |
    | **completas no sistema** | **420** |
    | **INCOMPLETAS** | **1.206** |

    A matrícula 5 tem **60 páginas no disco e 6 no sistema**. Quem a abre no
    balcão lê um décimo dela — **e nada na tela diz que falta o resto.**

POR QUE FALTAVA, e não é defeito da importação
    `ri_import.importar_imagens` grava o que a **exportação do E-Ofício
    listou**; o disco tem arquivos que aquela lista não trazia. A tela de
    resolver imagens, por sua vez, só olha o que já está em `ri_imagens` — de
    modo que **página que o banco não conhece nunca aparece em tela nenhuma**.

    É a lição «a coluna não é onde o dado está», agora entre a lista e o disco:
    **aqui a fonte de verdade da digitalização é o disco.**

O QUE ESTE MÓDULO NÃO FAZ
    **Não casa no escuro.** O número do arquivo é o número da matrícula —
    conferido em 3.667 de 3.667 —, mas há **dois números repetidos** nesta
    casa (`067` e `8`, com duas matrículas cada). Ali a página **não entra**, e
    aparece na conferência com o motivo: ligar a ficha ao imóvel errado é o
    tipo de engano que ninguém desconfia, porque a ficha abre.
"""
from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path
from typing import Any

import ri_imagens as RIMG
from bd_nativo import banco


class FichaDoDiscoError(ValueError):
    """Erro de regra, com frase pronta para o balcão."""


# O NOME DE ARQUIVO DESTA CASA: oito dígitos de matrícula, ponto, quatro de
# página — `00003744.0069`. Medido em 10.227 arquivos.
NOME = re.compile(r"^(\d{1,10})\.(\d{1,6})$")

# O QUE SE ACEITA COMO SUFIXO. No disco os arquivos são `.TIF` depois do número
# da página; `ri_imagens.chaves` já trata isso, e aqui a régua é a mesma.
def partir(nome: str) -> tuple[str, int] | None:
    """`00003744.0069.TIF` → («3744», 69). Só calcula.

    Devolve `None` para o que não tem esta forma — e **não se adivinha**: um
    arquivo com outro nome não é página de ficha desta casa.
    """
    limpo = str(nome or "").strip()
    # tira um sufixo de extensão de verdade, se houver (`.TIF`, `.tif`)
    partes = limpo.split(".")
    if len(partes) >= 3 and not partes[-1].isdigit():
        limpo = ".".join(partes[:-1])
    achado = NOME.match(limpo)
    if not achado:
        return None
    return str(int(achado.group(1))), int(achado.group(2))


def _sha256(caminho: Path, limite: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as f:
        for pedaco in iter(lambda: f.read(limite), b""):
            h.update(pedaco)
    return h.hexdigest()


def _numeros_das_matriculas(con: Any) -> dict[str, list[int]]:
    """De número de matrícula para os `id` que o têm. Só lê.

    **É uma LISTA, e não um id.** Duas matrículas com o mesmo número existem
    nesta casa, e é por isso que o casamento devolve todos: quem decide o que
    fazer com dois é quem chamou, e a resposta é não casar.
    """
    fora: dict[str, list[int]] = {}
    for linha in banco(con).ler("SELECT id, numero FROM ri_matriculas ORDER BY id"):
        numero = str(linha["numero"] or "").strip()
        if not numero:
            continue
        try:
            chave = str(int(re.sub(r"\D", "", numero) or 0))
        except ValueError:
            continue
        if chave == "0":
            continue
        fora.setdefault(chave, []).append(int(linha["id"]))
    return fora


def conferir(con: Any, raiz: Any) -> dict:
    """O que há no disco, o que o banco já tem, e o que falta. **SÓ LÊ.**

    Não grava nada e não copia nada — é o passo que se pode repetir à vontade,
    como o «conferir» da remessa da CRA.
    """
    pasta = Path(raiz)
    if not RIMG.e_pasta(pasta):
        raise FichaDoDiscoError(
            f"A pasta {pasta} não existe ou o servidor não consegue abri-la. "
            f"Lembre que ele roda como SYSTEM: caminho local funciona, unidade "
            f"mapeada não.")

    ja_no_banco = {str(r["nome_arquivo"] or "").strip().lower()
                   for r in banco(con).ler(
                       "SELECT nome_arquivo FROM ri_imagens "
                       "WHERE nome_arquivo IS NOT NULL")}
    por_numero = _numeros_das_matriculas(con)

    novas: list[dict] = []
    sem_matricula: list[str] = []
    ambiguas: list[str] = []
    fora_do_padrao: list[str] = []
    ja_tem = 0

    for caminho in pasta.rglob("*"):
        if not caminho.is_file():
            continue
        partido = partir(caminho.name)
        if partido is None:
            fora_do_padrao.append(caminho.name)
            continue
        numero, pagina = partido
        # o nome como o banco o guarda: sem o sufixo de extensão
        nome_no_banco = f"{caminho.name.split('.')[0]}.{caminho.name.split('.')[1]}"
        if nome_no_banco.lower() in ja_no_banco:
            ja_tem += 1
            continue
        ids = por_numero.get(numero) or []
        if not ids:
            sem_matricula.append(caminho.name)
            continue
        if len(ids) > 1:
            # **DUAS MATRÍCULAS COM O MESMO NÚMERO.** Escolher uma seria pôr a
            # ficha de um imóvel na de outro — e ninguém desconfia de uma ficha
            # que abre.
            ambiguas.append(f"{caminho.name} (nº {numero} está em "
                            f"{len(ids)} matrículas)")
            continue
        novas.append({"matricula_id": ids[0], "numero": numero,
                      "pagina": pagina, "nome": nome_no_banco,
                      "caminho": str(caminho)})

    novas.sort(key=lambda x: (x["matricula_id"], x["pagina"]))
    return {"raiz": str(pasta), "no_disco": ja_tem + len(novas)
            + len(sem_matricula) + len(ambiguas) + len(fora_do_padrao),
            "ja_no_banco": ja_tem, "novas": novas,
            "quantas_novas": len(novas),
            "matriculas_alcancadas": len({x["matricula_id"] for x in novas}),
            "sem_matricula": sem_matricula, "ambiguas": ambiguas,
            "fora_do_padrao": fora_do_padrao}


def candidatas(con: Any, raiz: Any) -> list[dict]:
    """As páginas que não casam sozinhas, com as matrículas possíveis. SÓ LÊ.

    **AVISO SEM SAÍDA É AVISO QUE FICA PARA SEMPRE** — a lição do livro a
    confirmar. Sem esta lista, as páginas de número repetido ficariam paradas
    para sempre, aparecendo na conferência todo dia sem ninguém poder resolver.

    **E a escolha é de quem assina.** Medido em 04/09/2026, os dois casos desta
    casa são de naturezas diferentes:

      · o nº **8** são **dois imóveis de verdade** — Livro `2S` de 1977 e Livro
        `2-A` de 2022 —, e os volumes do Livro 2 têm os números entrelaçados. O
        nome do arquivo não diz o livro, e **nenhum programa pode escolher**;
      · o nº **67** aparece como `067` e `67`, os dois no Livro `2-A`, folha
        71, com chaves de origem diferentes: tem cara de **duplicata de dado**,
        e fundir matrícula não é ato de programa.
    """
    achado = conferir(con, raiz)
    if not achado["ambiguas"]:
        return []

    por_numero = _numeros_das_matriculas(con)
    pasta = Path(achado["raiz"])
    fora: list[dict] = []
    for caminho in sorted(pasta.rglob("*")):
        if not caminho.is_file():
            continue
        partido = partir(caminho.name)
        if partido is None:
            continue
        numero, pagina = partido
        ids = por_numero.get(numero) or []
        if len(ids) < 2:
            continue
        nome_no_banco = (f"{caminho.name.split('.')[0]}."
                         f"{caminho.name.split('.')[1]}")
        marcas = ",".join("%s" for _ in ids)
        opcoes = [dict(x) for x in banco(con).ler(
            f"""SELECT m.id, m.numero, m.livro, m.folha, m.tipo_ficha,
                       m.data_abertura,
                       (SELECT COUNT(*) FROM ri_imagens i
                         WHERE i.matricula_id = m.id) AS paginas
                  FROM ri_matriculas m WHERE m.id IN ({marcas})
                 ORDER BY m.id""", ids)]
        fora.append({"nome": nome_no_banco, "arquivo": caminho.name,
                     "caminho": str(caminho), "numero": numero,
                     "pagina": pagina, "opcoes": opcoes})
    return fora


def resolver(db, nome: str, matricula_id: int, *, raiz: Any,
             quem: str = "") -> dict:
    """Liga uma página ambígua à matrícula que o oficial escolheu. **GRAVA.**

    **Confere que a escolha é uma das candidatas** — e não qualquer matrícula.
    Um número digitado na barra do navegador poria a ficha de um imóvel na de
    outro, que é justamente o engano que esta tela existe para evitar.
    """
    alvo = str(nome or "").strip()
    if not alvo:
        raise FichaDoDiscoError("Não veio o nome da página.")

    with db.connect() as con:
        pendentes = {x["nome"]: x for x in candidatas(con, raiz)}
    item = pendentes.get(alvo)
    if item is None:
        raise FichaDoDiscoError(
            f"A página «{alvo}» não está esperando escolha — ou já foi "
            f"resolvida, ou casa sozinha.")
    permitidas = {int(o["id"]) for o in item["opcoes"]}
    if int(matricula_id) not in permitidas:
        raise FichaDoDiscoError(
            f"A matrícula escolhida não é uma das candidatas desta página. "
            f"As possíveis são: "
            + ", ".join(f"{o['numero']} (Livro {o['livro']})"
                        for o in item["opcoes"]) + ".")

    origem = Path(item["caminho"])
    pasta = pasta_interna(db) / str(int(matricula_id))
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / origem.name
    try:
        shutil.copy2(origem, destino)
        tamanho = destino.stat().st_size
        assinatura = _sha256(destino)
    except OSError as erro:
        raise FichaDoDiscoError(
            f"Não consegui copiar {origem.name}: {erro}") from erro

    relativo = str(Path("ri") / "fichas" / str(int(matricula_id))
                   / origem.name)
    agora = db.now()
    with db.transaction() as con:
        banco(con).escrever(
            """INSERT INTO ri_imagens
                   (matricula_id, nome_arquivo, caminho, ordem, sha256,
                    ficha_digitalizada, caminho_interno, copiado_em, bytes)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (int(matricula_id), item["nome"], str(origem), item["pagina"],
             assinatura, 1, relativo, agora, tamanho))
    return {"nome": item["nome"], "matricula_id": int(matricula_id),
            "pagina": item["pagina"]}


def quadro(con: Any) -> dict:
    """Quantas fichas estão completas, e quantas não. SÓ LÊ.

    **A conta é por matrícula, e não por página** — o que o balcão precisa
    saber é «esta ficha está inteira?», e não quantos arquivos há.
    """
    bd = banco(con)
    total = int(bd.valor(
        "SELECT COUNT(*) FROM ri_matriculas"))
    com_imagem = int(bd.valor(
        "SELECT COUNT(DISTINCT matricula_id) FROM ri_imagens"))
    paginas = int(bd.valor(
        "SELECT COUNT(*) FROM ri_imagens"))
    copiadas = int(bd.valor(
        "SELECT COUNT(*) FROM ri_imagens "
        "WHERE COALESCE(caminho_interno,'') <> ''"))
    return {"matriculas": total, "com_ficha": com_imagem,
            "sem_ficha": total - com_imagem, "paginas": paginas,
            "copiadas": copiadas}


def trazer(db, raiz: Any, *, quem: str = "", limite: int = 0) -> dict:
    """Traz as páginas que faltam. **GRAVA, e copia para dentro do sistema.**

    **RECEBE `db`, E COPIA FORA DA TRANSAÇÃO.** Copiar 453 MB dentro de um
    `BEGIN IMMEDIATE` poria toda a casa no `busy_timeout` — é a regra do
    selador aplicada ao disco.

    **A cópia vem antes do registro.** Gravar a linha e copiar depois deixaria
    o banco afirmando uma ficha que não está lá; o contrário deixa, no pior
    caso, um arquivo copiado sem linha — que a próxima passada reaproveita.
    """
    with db.connect() as con:
        achado = conferir(con, raiz)

    novas = achado["novas"]
    if limite:
        novas = novas[:int(limite)]
    if not novas:
        return {**achado, "trazidas": 0, "falhas": [],
                "porque": "não há página nova no disco"}

    destino_raiz = pasta_interna(db)
    agora = db.now()
    trazidas, falhas = 0, []

    for item in novas:
        origem = Path(item["caminho"])
        pasta = destino_raiz / str(item["matricula_id"])
        try:
            pasta.mkdir(parents=True, exist_ok=True)
            destino = pasta / origem.name
            shutil.copy2(origem, destino)
            tamanho = destino.stat().st_size
            assinatura = _sha256(destino)
        except OSError as erro:
            # **UMA PÁGINA QUE NÃO COPIA NÃO DERRUBA AS OUTRAS.** São milhares;
            # parar na primeira faria a passada inteira depender do pior
            # arquivo da pasta.
            falhas.append({"nome": item["nome"], "porque": str(erro)})
            continue

        relativo = str(Path("ri") / "fichas" / str(item["matricula_id"])
                       / origem.name)
        with db.transaction() as con:
            banco(con).escrever(
                """INSERT INTO ri_imagens
                       (matricula_id, nome_arquivo, caminho, ordem, sha256,
                        ficha_digitalizada, caminho_interno, copiado_em, bytes)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (item["matricula_id"], item["nome"], str(origem),
                 item["pagina"], assinatura, 1, relativo, agora, tamanho))
        trazidas += 1

    return {**achado, "trazidas": trazidas, "falhas": falhas, "porque": ""}


def pasta_interna(db) -> Path:
    """Onde o sistema guarda a própria cópia.

    **Dentro da pasta de arquivos que o backup já varre** — a cópia entra no
    backup sem mexer na rotina existente. É o mesmo lugar que a tela de copiar
    imagens já usa; duas pastas para a mesma coisa fariam metade das fichas
    sumir do backup sem ninguém ver.
    """
    raiz = Path(str(db.get_setting("archive_root", "") or "").strip()
                or (Path(db.db_path).parent / "arquivos"))
    destino = raiz / "ri" / "fichas"
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def incompletas(con: Any, raiz: Any,
                *, limite: int = 50) -> list[dict]:
    """As fichas que têm no disco mais páginas do que no sistema. SÓ LÊ.

    **É a lista que responde «esta ficha está inteira?»** — e ela existe
    porque a resposta hoje é não em 1.206 de 1.626, sem que nada avise.
    """
    achado = conferir(con, raiz)
    por_matricula: dict[int, int] = {}
    for item in achado["novas"]:
        por_matricula[item["matricula_id"]] = (
            por_matricula.get(item["matricula_id"], 0) + 1)
    if not por_matricula:
        return []

    ids = list(por_matricula)[:int(limite)]
    marcas = ",".join("%s" for _ in ids)
    linhas = banco(con).ler(
        f"""SELECT m.id, m.numero, m.livro,
                   (SELECT COUNT(*) FROM ri_imagens i
                     WHERE i.matricula_id = m.id) AS tem
              FROM ri_matriculas m WHERE m.id IN ({marcas})
             ORDER BY m.id""", ids)
    return sorted(
        [{**dict(x), "faltam": por_matricula[int(x["id"])]} for x in linhas],
        key=lambda x: -x["faltam"])
