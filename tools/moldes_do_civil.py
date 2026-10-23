"""OS MOLDES DE CASAMENTO E DE ÓBITO — E, DESDE O LD01, DE NATIMORTO E DO
LIVRO E —, derivados do de nascimento.

Ordem do oficial em 01/09/2026: *«aplique essas correções nas outras certidões
de registro civil também»*. E em 21/10/2026, sobre os defeitos que o LT01
achou: *«corrija tudo»* — o natimorto e o Livro E não tinham papel nenhum.

**HAVIA UM MOLDE SÓ, E AS OUTRAS DUAS ESPÉCIES NÃO IMPRIMIAM NADA.** Desde a
passada da manhã, `ESPECIES_QUE_O_MOLDE_SERVE` recusa casamento e óbito — o
título do molde é texto fixo, «CERTIDÃO DE NASCIMENTO», e uma certidão de óbito
saía com o cabeçalho de nascimento, com caixa de DNV e de gêmeos. A recusa
protegia; ela também deixava o balcão sem papel para as duas.

**A GEOMETRIA É A DO MOLDE QUE O OFICIAL DESENHOU.** Cabeçalho, estilos, cor
preta, larguras de coluna, o fecho e as duas caixas de selo vêm todos do
`certidao_nascimento_modelo.odt`, clonados. Nada é redesenhado: os estilos
automáticos do documento são reaproveitados pelo nome, de modo que a folha de
casamento tem exatamente a mesma coluna da de nascimento.

**OS CAMPOS SÃO OS QUE `rc_certidao` JÁ ESCREVE**, medidos nas 145 certidões
reais desta casa — 18 de casamento e 3 de óbito — e nos requisitos da Lei
6.015/1973 (o regime de bens, art. 70, item 6; o nome que cada cônjuge passou a
utilizar, que é o campo pelo qual a certidão de casamento existe).

**E O QUE NÃO SE MEDIU FICA DITO: a ARRUMAÇÃO é derivada, e não o Anexo.** Os
Anexos V e VI do Provimento CNJ 182/2024 **não estão nesta casa** — o de
nascimento também não estava, e a cor da letra se decidiu medindo um PDF real
(`JADIR MIRANDA DE SOUZA CERTIDÃO.pdf`). Aqui não há PDF de casamento nem de
óbito no modelo nacional para medir a posição dos campos. Então: **o que está
em cada campo é medido; ONDE cada campo está é derivado do molde de
nascimento.** O oficial abre no LibreOffice e ajusta, como fez com o primeiro.

**E POR ISSO ESTE SCRIPT NUNCA SOBRESCREVE UM MOLDE QUE JÁ EXISTA.** Regerar
por cima apagaria o ajuste dele — é o mesmo motivo pelo qual a passada das
notas do desenvolvimento não toca a linha que uma pessoa editou.

Rodar:

    "%PROGRAMDATA%\\CartorioGestao\\runtime\\Scripts\\python.exe" tools\\moldes_do_civil.py
"""
from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
MOLDES = RAIZ / "modelos"
BASE = MOLDES / "certidao_nascimento_modelo.odt"

# AS LINHAS DE CADA MOLDE: (rótulos, marcadores).
#
# O molde é uma sequência de «parágrafo de rótulo + tabela de valor», e é essa
# forma que se repete aqui. O número de rótulos decide de qual par do molde de
# nascimento a linha é clonada — é assim que a largura das colunas vem de lá.
CASAMENTO = (
    (("PRIMEIRO CÔNJUGE", "SEGUNDO CÔNJUGE"), ("@conj1_nome", "@conj2_nome")),
    (("DATA DE NASCIMENTO", "DATA DE NASCIMENTO"),
     ("@conj1_datanascimento", "@conj2_datanascimento")),
    (("NATURALIDADE", "NATURALIDADE"),
     ("@conj1_naturalidade", "@conj2_naturalidade")),
    (("NACIONALIDADE", "NACIONALIDADE"),
     ("@conj1_nacionalidade", "@conj2_nacionalidade")),
    (("ESTADO CIVIL ANTERIOR", "ESTADO CIVIL ANTERIOR"),
     ("@conj1_estadocivil", "@conj2_estadocivil")),
    (("CPF", "CPF"), ("@conj1_cpf", "@conj2_cpf")),
    (("FILIAÇÃO", "FILIAÇÃO"), ("@conj1_filiacao", "@conj2_filiacao")),
    (("NOME QUE CADA CÔNJUGE PASSOU A UTILIZAR",), ("@nomespos",)),
    (("DATA DA CELEBRAÇÃO POR EXTENSO", "REGIME DE BENS DO CASAMENTO"),
     ("@datacelebracaoextenso", "@regimebens")),
)

OBITO = (
    (("DATA DO ÓBITO POR EXTENSO", "HORA DO ÓBITO"),
     ("@dataobitoextenso", "@horaobito")),
    (("SEXO", "IDADE", "DATA DE NASCIMENTO"),
     ("@sexofalecido", "@idadefalecido", "@datanascimentofalecido")),
    (("NATURALIDADE", "ESTADO CIVIL"),
     ("@naturalidadefalecido", "@estadocivilfalecido")),
    (("NOME DO CÔNJUGE", "CPF"), ("@conjugefalecido", "@cpffalecido")),
    (("FILIAÇÃO",), ("@filiacaofalecido",)),
    (("LOCAL DO ÓBITO", "DECLARANTE"),
     ("@localobito", "@declarantefalecido")),
    (("NATUREZA E CAUSA DA MORTE", "ATESTOU O ÓBITO"),
     ("@causamorte", "@atestouobito")),
    (("LOCAL DO SEPULTAMENTO", "DEIXOU BENS"),
     ("@sepultamento", "@deixoubens")),
    (("DEIXOU FILHOS",), ("@deixoufilhos",)),
)

# O NATIMORTO E O LIVRO E — LD01, 21/10/2026. Os dois não tinham papel, e a
# guarda de `rc_certidao_odt` os recusava (o natimorto não afirma nascimento
# com vida; o Livro E registra seis coisas diferentes entre si). O natimorto
# ganha as caixas do que o assento dele tem — o parto, o lugar, a Declaração
# de Óbito, os pais e o sepultamento —, e não tem CPF (CNN art. 479-A, § 1º).
# O Livro E tem UM papel para as seis espécies, como tem um termo só: a
# espécie, o título registrado e uma caixa com o que a lei pede daquela
# espécie (`rc_certidao.linhas_do_livro_e`); o título do papel é marcador,
# porque muda com a espécie.
NATIMORTO = (
    (("DATA DO PARTO POR EXTENSO", "HORA"),
     ("@dataobitoextenso", "@horaobito")),
    (("LOCAL DO PARTO", "MUNICÍPIO", "UF"),
     ("@localfalecimento", "@municipio_falecimento", "@uf_falecimento")),
    (("SEXO", "NÚMERO DA DECLARAÇÃO DE ÓBITO"),
     ("@sexofalecido", "@numerodo")),
    (("NOME DO(A) GENITOR(ES)",), ("@filiacaofalecido",)),
    (("LOCAL DE SEPULTAMENTO / CREMAÇÃO",), ("@sepultamento",)),
    (("DATA DO REGISTRO",), ("@DATAREGISTROEXTENSOSN",)),
)

LIVRO_E = (
    (("ESPÉCIE DO REGISTRO", "NÚMERO DO CPF"),
     ("@livroe_especie", "@cpfnascido")),
    (("TÍTULO REGISTRADO",), ("@livroe_titulo",)),
    (("O QUE A LEI MANDA CONSTAR",), ("@livroe_indicacoes",)),
    (("DATA DO REGISTRO",), ("@DATAREGISTROEXTENSOSN",)),
)

ESPECIES = {
    "casamento": {
        "arquivo": "certidao_casamento_modelo.odt",
        "titulo": "CERTIDÃO DE CASAMENTO",
        "nome_rotulo": "NOMES:",
        "nome_marca": "@nomesconjuges",
        "matricula_marca": "@matriculacasamento",
        "linhas": CASAMENTO,
    },
    "obito": {
        "arquivo": "certidao_obito_modelo.odt",
        "titulo": "CERTIDÃO DE ÓBITO",
        "nome_rotulo": "NOME:",
        "nome_marca": "@nomefalecido",
        "matricula_marca": "@matriculaobito",
        "linhas": OBITO,
    },
    "natimorto": {
        "arquivo": "certidao_natimorto_modelo.odt",
        "titulo": "CERTIDÃO DE NATIMORTO",
        "nome_rotulo": "NOME:",
        "nome_marca": "@nomefalecido",
        "matricula_marca": "@matriculaobito",
        "linhas": NATIMORTO,
    },
    "livro_e": {
        "arquivo": "certidao_livro_e_modelo.odt",
        "titulo": "@titulolivroe",
        "nome_rotulo": "NOME:",
        "nome_marca": "@nomenascido",
        "matricula_marca": "@matriculanascido",
        "linhas": LIVRO_E,
    },
}


def _fim_de(xml: str, inicio: int, tag: str) -> int:
    return xml.find("</" + tag + ">", inicio) + len(tag) + 3


def _pedacos(corpo: str) -> list[tuple[str, int, int]]:
    """Os parágrafos e tabelas de primeiro nível, em ordem de documento."""
    saida, pos = [], 0
    padrao = re.compile(r"<(text:p|table:table)\b")
    while True:
        m = padrao.search(corpo, pos)
        if not m:
            return saida
        tag = m.group(1)
        fim = _fim_de(corpo, m.start(), tag)
        saida.append((tag, m.start(), fim))
        pos = fim


def _so_texto(xml: str) -> str:
    s = re.sub(r"<text:line-break/>", " ", xml)
    s = re.sub(r"<text:tab/>", "\t", s)
    return re.sub(r"<[^>]+>", "", s)


def _troca_textos(xml: str, novos: list[str]) -> str:
    """Troca, em ordem, os textos soltos entre etiquetas pelos `novos`.

    **Só mexe no TEXTO**: nenhum atributo, nenhum estilo, nenhuma tabela. É o
    que faz o clone herdar a fonte, a cor e a largura da coluna do original.
    """
    fila = list(novos)
    saida, pos = [], 0
    for m in re.finditer(r">([^<>]+)<", xml):
        if not m.group(1).strip():
            continue
        saida.append(xml[pos:m.start() + 1])
        saida.append(fila.pop(0) if fila else "")
        pos = m.end() - 1
    saida.append(xml[pos:])
    return "".join(saida)


def _escapa(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _pares_do_molde(corpo: str, pedacos: list) -> dict[int, tuple[str, str]]:
    """Um par «rótulo + tabela» por número de colunas, tirado do original."""
    por_colunas: dict[int, tuple[str, str]] = {}
    for i, (tag, a, b) in enumerate(pedacos):
        if tag != "table:table" or i == 0:
            continue
        bloco = corpo[a:b]
        # A tabela dos selos é desenho próprio, e as de texto livre não são
        # «rótulo + valor»: nenhuma das duas serve de forma para clonar.
        if "@selo1" in bloco or "@averbacoes" in bloco or "@anotacoes" in bloco:
            continue
        colunas = bloco.count("<table:table-column")
        rotulo_tag, ra, rb = pedacos[i - 1]
        if rotulo_tag != "text:p" or colunas in por_colunas:
            continue
        por_colunas[colunas] = (corpo[ra:rb], bloco)
    return por_colunas


def montar(especie: str) -> bytes:
    """O `content.xml` do molde daquela espécie. Não escreve arquivo nenhum."""
    cfg = ESPECIES[especie]
    with zipfile.ZipFile(BASE) as z:
        xml = z.read("content.xml").decode("utf-8")
    corte = xml.find("<office:text")
    cabeca, corpo = xml[:corte], xml[corte:]
    pedacos = _pedacos(corpo)
    modelo = _pares_do_molde(corpo, pedacos)

    faltando = {len(r) for r, _ in cfg["linhas"]} - set(modelo)
    if faltando:
        raise SystemExit(
            "o molde de nascimento nao tem par com "
            + str(sorted(faltando)) + " coluna(s) para clonar; tem "
            + str(sorted(modelo)))

    # A REGIÃO QUE MUDA: do rótulo «CPF» até a tabela da DNV. O que vem antes
    # (título, nome, matrícula) e o que vem depois (averbações, anotações,
    # fecho, selos) fica igual — é o desenho do oficial.
    # O RÓTULO VIROU «NÚMERO DO CPF» no molde que o oficial ajustou (o desta
    # ferramenta escrevia «CPF»): a região começa no rótulo que termina em CPF.
    primeiro = next(i for i, (t, a, b) in enumerate(pedacos)
                    if t == "text:p"
                    and _so_texto(corpo[a:b]).strip().endswith("CPF"))
    ultimo = next(i for i, (t, a, b) in enumerate(pedacos)
                  if t == "table:table" and "@declaracaonascidovivo" in corpo[a:b])

    # A MATRICULA FICA, E ELA QUASE SE PERDEU. No molde de nascimento o bloco
    # dela vem DEPOIS do CPF — «NOME, CPF, MATRICULA, data...» —, e o corte que
    # comeca no rotulo «CPF» a levava junto. **A matricula de 32 digitos e a
    # identidade nacional da certidao**: o papel sem ela nao serve, e a falta
    # so apareceria quando alguem fosse conferir o registro em outra
    # serventia. Apanhado conferindo o molde gerado, e nao relendo o script.
    matricula = ""
    for i, (tag, a, b) in enumerate(pedacos):
        if tag == "text:p" and _so_texto(corpo[a:b]).strip().startswith("MATRÍCULA"):
            matricula = corpo[a:pedacos[i + 1][2]]
            break
    if not matricula:
        raise SystemExit("nao achei o bloco da matricula no molde de origem")

    novas = [matricula]
    for n, (rotulos, marcas) in enumerate(cfg["linhas"], start=1):
        rotulo_xml, tabela_xml = modelo[len(rotulos)]
        novas.append(_troca_textos(rotulo_xml, [_escapa(r) for r in rotulos]))
        tabela = _troca_textos(tabela_xml, list(marcas))
        # `table:name` e unico no documento; o `table:style-name` nao precisa
        # ser, e e justamente por reaproveita-lo que a largura vem do original.
        tabela = re.sub(r'table:name="[^"]+"',
                        'table:name="' + especie.capitalize() + str(n) + '"',
                        tabela, count=1)
        novas.append(tabela)

    corpo = (corpo[:pedacos[primeiro][1]] + "".join(novas)
             + corpo[pedacos[ultimo][2]:])

    # O TÍTULO É TEXTO FIXO NO MOLDE, e era ele que fazia a certidão de óbito
    # sair com o cabeçalho de nascimento.
    corpo = corpo.replace("CERTIDÃO DE NASCIMENTO", _escapa(cfg["titulo"]), 1)
    corpo = corpo.replace("@nomenascido", cfg["nome_marca"])
    corpo = corpo.replace("@matriculanascido", cfg["matricula_marca"])
    corpo = corpo.replace(">NOME:<", ">" + _escapa(cfg["nome_rotulo"]) + "<", 1)
    return (cabeca + corpo).encode("utf-8")


def gerar(especie: str) -> Path:
    """Escreve o `.odt` daquela espécie. **Nunca sobrescreve** um que exista."""
    destino = MOLDES / ESPECIES[especie]["arquivo"]
    if destino.exists():
        print("  " + destino.name + ": ja existe — nao foi tocado")
        return destino
    conteudo = montar(especie)
    # Reescreve o zip trocando so o `content.xml`: as imagens do QR, os
    # estilos e o `meta.xml` do molde do oficial ficam como estao.
    with zipfile.ZipFile(BASE) as origem:
        itens = [(i, origem.read(i.filename)) for i in origem.infolist()]
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as saida:
        for info, dados in itens:
            saida.writestr(
                info, conteudo if info.filename == "content.xml" else dados)
    print("  " + destino.name + ": gerado (" + str(destino.stat().st_size)
          + " bytes)")
    return destino


if __name__ == "__main__":
    if not BASE.exists():
        raise SystemExit("nao achei o molde de nascimento em " + str(BASE))
    quais = sys.argv[1:] or list(ESPECIES)
    for qual in quais:
        if qual not in ESPECIES:
            raise SystemExit("especie desconhecida: " + qual)
        gerar(qual)
