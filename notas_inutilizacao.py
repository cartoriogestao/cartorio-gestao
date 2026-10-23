"""
Inutilizacao da face em branco, impressa junto com o ato.

O QUE O DELEGATARIO PEDIU, E O QUE DA PARA ENTREGAR
    O pedido foi "nao precisar inutilizar folha". Ha dois caminhos para chegar
    la: fazer o branco nao acontecer, ou fazer a inutilizacao nao ser trabalho.

    O PRIMEIRO TEM TETO, e vale dizer por que. Nenhum ato termina exatamente na
    ultima linha da pagina: sempre sobra um pedaco depois do fecho, e esse
    pedaco pede traco de qualquer jeito. Mexer no corpo da letra nao ELIMINA o
    branco — muda o branco de lugar. O que o controle de paridade evita e
    outra coisa, menor e real: uma FACE INTEIRA em branco.

    E encolher quase nunca serve. Passar de tres para duas paginas exige tirar
    um terco do espaco — corpo 12 vira 9,8pt, e livro de notas nao se le em
    9,8pt daqui a quarenta anos.

    O SEGUNDO CAMINHO E O QUE ESTE MODULO FAZ: sobrando a face, ela sai
    impressa JA INUTILIZADA, com o traco, o dizer e a linha de assinatura.
    Ninguem risca nada a mao. Funciona sempre, nao depende de renderizador
    externo, e nao introduz variacao tipografica no livro.

A BANDA DE ENTRELINHA
    O delegatario autorizou mexer SO NA ENTRELINHA, e no maximo 10%. A banda
    esta declarada aqui em `BANDA_ENTRELINHA` e o modulo sabe calcula-la — mas
    NAO A APLICA sozinho, e a razao esta em `sugerir_entrelinha`: para acertar
    contagem de pagina e preciso MEDIR, e o sistema hoje estima por contagem de
    caracteres. Aplicar um ajuste calculado sobre uma estimativa e trocar um
    erro conhecido por um erro invisivel.

    O que o modulo entrega hoje e a SUGESTAO, com a conta a vista, para o
    escrevente decidir. Quando a medicao real entrar — o caminho esta descrito
    em `sugerir_entrelinha` —, e so ligar o fio.

POR QUE O BRANCO NAO PODE FICAR BRANCO
    Art. 795, § 2º, do Codigo de Normas do Foro Extrajudicial do Maranhao
    (Provimento TJMA n. 28, de 23/04/2026): "A escrituracao deve ser seguida,
    sem claros ou espacos em branco." Espaco em branco em livro de notas e o
    lugar por onde se acrescenta o que ninguem declarou.

    O teor deste paragrafo esta conferido — ja era citado em `notas_modelos.py`
    por quem construiu a biblioteca de modelos, e a Secao III (arts. 788 a 797)
    esta confirmada no sumario oficial. O que NAO foi lido e se os arts. 788 a
    794 prescrevem corpo de letra, entrelinha ou numero de linhas por pagina.
    Enquanto nao se ler, a banda deste modulo e uma escolha da serventia, e nao
    uma leitura da norma.
"""
from __future__ import annotations

import re
from typing import Any

import modelos_da_casa as MODELOS
from notas_livro import (PAGINAS_POR_FOLHA, com_algarismos, inteiro,
                         rotulo_folha)
from notas_schema import TIPOS_LIVRO

# Ate onde se pode mexer na entrelinha para fechar o ato em numero par de
# paginas. Definido pelo delegatario em 17/08/2026: SO entrelinha, ate 10%.
#
# So entrelinha porque e a variacao menos visivel no livro encadernado e a
# mais facil de justificar em correicao — corpo de letra diferente entre atos
# vizinhos parece adulteracao, e e disso que a correicao desconfia.
BANDA_ENTRELINHA = 0.10
ENTRELINHA_PADRAO = 1.5


def faces_do_ato(ato: Any) -> list[str]:
    """As faces que o ato ocupa e NAO escreveu. Hoje, no maximo uma.

    Como cada ato comeca em folha nova e ocupa folhas inteiras, o unico branco
    de face inteira possivel e o verso da ultima folha, quando o texto terminou
    na frente dela.
    """
    a = dict(ato)
    if int(a.get("verso_final") or 0):
        return []
    fim = inteiro(a.get("folha_final_num")) or inteiro(a.get("folha_final"))
    return [rotulo_folha(fim, verso=True)] if fim else []


def faces_do_livro(livro: Any) -> list[str]:
    """As faces em branco declaradas no encerramento do livro.

    `folhas_inutilizadas` guarda "181-200": as folhas que sobraram quando o
    livro encerrou. Cada uma tem DUAS faces, e as duas precisam do traco.
    """
    intervalo = str(dict(livro).get("folhas_inutilizadas") or "").strip()
    achado = re.match(r"^(\d+)\s*-\s*(\d+)$", intervalo)
    if not achado:
        return []
    inicio, fim = int(achado.group(1)), int(achado.group(2))
    faces = []
    for n in range(inicio, fim + 1):
        faces.append(rotulo_folha(n))
        faces.append(rotulo_folha(n, verso=True))
    return faces


def dizer(faces: list[str], serie: str, numero: Any, sv: dict,
          data_extenso: str, motivo: str | None = None, *, con: Any = None) -> str:
    """O texto que sai na face inutilizada.

    Diz o que e, por que esta em branco, e que nada mais entra ali. As tres
    coisas, porque uma face riscada sem dizer nenhum obriga quem le a supor.

    O TEXTO MORA NA BASE DESDE O LF06D (`NOTAS_INUTILIZACAO`, com a declaracao
    de uma face ou de varias como peca); o singular e o plural sao decididos
    aqui.
    """
    textos = MODELOS.textos(con)
    quantas = len(faces)
    livro = TIPOS_LIVRO.get(serie, serie)
    if quantas == 1:
        declaracao = textos.preencher(
            "NOTAS_INUTILIZACAO__uma_face", face=faces[0], livro=livro, numero=numero,
            quantas=com_algarismos(quantas),
            razao=(motivo or "").strip() or textos("NOTAS_INUTILIZACAO__razao_uma"))
    else:
        primeira, ultima = faces[0], faces[-1]
        declaracao = textos.preencher(
            "NOTAS_INUTILIZACAO__varias_faces", primeira=primeira, ultima=ultima,
            livro=livro, numero=numero, quantas=com_algarismos(quantas),
            razao=(motivo or "").strip() or textos("NOTAS_INUTILIZACAO__razao_varias"))
    return textos.preencher(
        "NOTAS_INUTILIZACAO", declaracao=declaracao,
        cidade=sv.get('ri_cidade', ''), uf=sv.get('ri_uf', ''),
        data_extenso=data_extenso, titular=sv.get('serventia_titular', ''),
        titulo=sv.get('serventia_titulo', ''))


# O traco. Nao e enfeite: e o que impede a linha em branco de receber texto
# depois. Sai repetido, cobrindo a altura util da face.
_RISCO = "/" * 78
LINHAS_DE_RISCO = 24


def html_da_face(face: str, serie: str, numero: Any, sv: dict,
                 data_extenso: str, texto: str, *, con: Any = None) -> str:
    """Uma face inutilizada, pronta para imprimir sobre a folha do livro.

    A folha mora na base desde o LF06D (`NOTAS_INUTILIZACAO_FACE`); o traco,
    que e regra (cobrir a altura util da face), entra pronto no claro
    `{riscos}`.
    """
    riscos = "".join(f'<p align="center">{_RISCO}</p>' for _ in range(LINHAS_DE_RISCO))
    return MODELOS.textos(con).preencher(
        "NOTAS_INUTILIZACAO_FACE", livro=TIPOS_LIVRO.get(serie, serie),
        numero=numero, face=face, riscos=riscos, texto=texto,
        titular=sv.get("serventia_titular", ""), titulo=sv.get("serventia_titulo", ""))


def sugerir_entrelinha(paginas_texto: Any,
                       entrelinha: float = ENTRELINHA_PADRAO,
                       banda: float = BANDA_ENTRELINHA) -> dict:
    """Quanto de entrelinha fecharia o ato em numero PAR de paginas.

    A CONTA
        O texto ocupa `paginas_texto` faces. Terminando em face impar, sobra
        um verso. Para o texto ALCANCAR a face seguinte, ele precisa crescer na
        proporcao do que falta — e o quanto falta depende de quao cheia esta a
        ultima pagina, que e justamente o que uma contagem de caracteres NAO
        SABE.

        O melhor caso: a ultima pagina esta quase cheia, e 2% de entrelinha
        resolvem. O pior: ela esta com um paragrafo, e nem 10% chegam perto —
        e se chegassem, a face nova sairia quase vazia, que e o mesmo problema
        de volta, agora numa face criada por nos.

    POR QUE ISTO NAO APLICA NADA SOZINHO
        Para acertar contagem de pagina e preciso MEDIR. Hoje o sistema estima
        por numero de caracteres (`notas_livro.estimar_paginas`), e quem decide
        a quebra de verdade e o LibreOffice ao abrir o .odt. Aplicar um ajuste
        calculado sobre estimativa trocaria um erro que se ve — a face em
        branco — por um que nao se ve: o ato que saiu com entrelinha diferente
        dos vizinhos e mesmo assim nao fechou em par.

        O CAMINHO PARA MEDIR JA ESTA QUASE MONTADO NESTA CASA:
          - `ri_doc_extrair.SOFFICE` ja sabe achar o LibreOffice, em tres
            caminhos, incluindo o Program Files (x86);
          - `ri_web` ja sabe dizer quando ele nao esta na maquina;
          - `pypdfium2` ja e dependencia declarada e conta paginas.
        Gerar o .odt, converter com `soffice --headless --convert-to pdf`,
        contar, subir um degrau da banda e repetir. Ai o ajuste passa a ser
        medido, e este modulo pode aplica-lo.

    Devolve a sugestao e o porque, para a tela mostrar e o escrevente decidir.
    """
    paginas = inteiro(paginas_texto) or 0
    if paginas < 1:
        return {"precisa": False, "motivo": "sem páginas informadas"}
    if paginas % PAGINAS_POR_FOLHA == 0:
        return {"precisa": False, "motivo": "o texto já termina no verso"}

    # Quanto o texto teria de crescer para transbordar da ultima face.
    # Limite inferior: uma face a mais sobre as que ele ja ocupa.
    crescimento = 1.0 / paginas
    cabe = crescimento <= banda
    return {
        "precisa": True,
        "paginas_texto": paginas,
        "entrelinha_atual": round(entrelinha, 2),
        "entrelinha_sugerida": round(entrelinha * (1 + min(crescimento, banda)), 2),
        "crescimento_necessario": round(crescimento * 100, 1),
        "banda": round(banda * 100),
        "cabe_na_banda": cabe,
        "medido": False,
        "motivo": (
            f"o texto teria de crescer cerca de {crescimento * 100:.0f}% para "
            f"alcançar o verso; a banda de entrelinha autorizada é de "
            f"{banda * 100:.0f}%"
            + ("" if cabe else " — não cabe, inutilize a face")),
    }
