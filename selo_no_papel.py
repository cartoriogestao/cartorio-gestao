"""O QUE DO SELO VAI IMPRESSO — uma régua para os papéis das seis atribuições.

Pedido do oficial em 01/09/2026: *«aplique a correção do selo (com emolumentos
e demais informações) também para todos demais atos do cartório, inclusive
etiqueta de reconhecimento de firma e autenticação de cópia»*.

**ISTO NASCEU DENTRO DA CERTIDÃO DO RCPN E NÃO PODIA FICAR LÁ.** A régua de
compor a linha de valores foi escrita em `rc_certidao_odt` no mesmo dia, para o
molde daquela certidão; ao alcançar a etiqueta e os demais atos, deixar uma
cópia em cada papel daria **seis versões divergentes** do pedaço que imprime
dinheiro num documento assinado. É a lição do núcleo — o que serve várias
atribuições mora num lugar só — e a da `normalizar_nome`, que este projeto já
pagou quatro vezes.

**E O PRECEDENTE É MEDIDO, não escolhido.** Nos **25.634** selos que esta casa
imprimiu, o texto do selo traz os valores em **25.634** — sem exceção:

    Poder Judiciário – TJMA. Selo: RECFIR000000003M1XKR7TEX6G33,
    06/12/2021 14:38:30, Ato: 13.17.4, Parte(s): TOMAS DOS SANTOS
    RIBEIRO, Rec Firma: Semelhança, Total R$ 18,11 Emol R$ 16,31
    FERC R$ 0,50 FADEP R$ 0,65 FEMP R$ 0,65
    Consulte em https://selo.tjma.jus.br

Quem escreve isso é o **aparelho**, e não este sistema: o valor já vem dentro
do selo. O que faltava era o **papel imprimir o que o selo declara** — a
etiqueta de reconhecimento e a de autenticação saíam com o número e o QR, e sem
uma linha de valor. São 13.664 reconhecimentos e 3.650 autenticações no acervo,
todos com valores no selo.

**A LINHA SE COMPÕE DO QUE O SELO DECLARA, e não de rótulos fixos.** Medido em
4.000 textos: FERC em 4.000, FEMP e FADP em 3.998, **FERRFIS em 396** — um em
cada dez. Com os rótulos escritos no papel, nove em cada dez sairiam com
«FERRFIS R$» e nada depois. **Rótulo sem valor é ruído num papel assinado**, e
zero seria pior, porque afirma.

**E O FUNDO SE PEDE PELA SIGLA CANÔNICA, E NÃO PELO SINÔNIMO.** `FADEP` é
sinônimo; a sigla da casa é `FADP`, e é ela que `selo.ler_texto` devolve — nos
4.000 selos, `FADP` em 3.998 e `FADEP` em **zero**. O papel, porém, escreve
`FADEP`: é o que o selo e a certidão real desta casa imprimem. **A palavra do
cadastro e a do papel são duas, e por isso há uma tradução de uma entrada só.**
"""
from __future__ import annotations

from typing import Any


# OS FUNDOS QUE ENTRAM NO PAPEL SAEM DA TABELA DA CASA, e nao de uma lista
# escrita aqui — `atribuicoes.FUNDOS` e a fonte, e `custas.CAMPOS_NO_TOTAL` diz
# quais sao cobrados (o **ISS nao entra**, medido em 39 selos reais).
def _fundos_do_papel() -> tuple[str, ...]:
    import atribuicoes as ATR
    import custas
    cobrados = {c.upper() for c in custas.CAMPOS_NO_TOTAL}
    saem = []
    for f in ATR.FUNDOS:
        sigla = str(f.get("sigla") or "")
        apelidos = {sigla.upper()} | {
            a.upper() for a in ATR.SINONIMOS_DE_FUNDO.get(sigla, ())}
        if apelidos & cobrados:
            saem.append(sigla)
    return tuple(saem)


FUNDOS_DO_PAPEL: tuple[str, ...] = _fundos_do_papel()

# O ROTULO IMPRESSO E O QUE O SELO E A CERTIDAO REAL ESCREVEM. Uma entrada so,
# e ela existe porque a palavra do papel difere da do cadastro.
ROTULO_NO_PAPEL: dict[str, str] = {"FADP": "FADEP"}


def moeda(v: Any) -> str:
    """Moeda do selo, no jeito brasileiro: 53,58. Espaco quando nao ha."""
    if v is None or v == "":
        return " "
    try:
        n = float(v)
    except (TypeError, ValueError):
        t = str(v).strip()
        return t if t else " "
    return f"{n:.2f}".replace(".", ",")


def ler(texto: Any) -> dict:
    """O selo lido. So calcula — devolve `{}` quando nao ha texto."""
    import selo as SELO
    t = str(texto or "").strip()
    return SELO.ler_texto(t) if t else {}


def linha_de_valores(texto: Any) -> str:
    """`Total R$ … Emol R$ … FERC R$ …`, so com o que o selo declara.

    Devolve **texto vazio** quando o selo nada declara — e nao uma linha de
    rotulos secos. Quem chama decide se esconde a linha ou o quadro; afirmar
    zero sobre ato oneroso e que nao serve.
    """
    lido = ler(texto)
    if not lido:
        return ""
    fundos = lido.get("fundos") or {}
    partes = [("Total R$", moeda(lido.get("total"))),
              ("Emol R$", moeda(lido.get("emolumentos")))]
    for sigla in FUNDOS_DO_PAPEL:
        partes.append((f"{ROTULO_NO_PAPEL.get(sigla, sigla)} R$",
                       moeda(fundos.get(sigla))))
    return " ".join(f"{rot} {val}" for rot, val in partes if val.strip())


def detalhe(texto: Any) -> str:
    """`Ato: 13.17.4, 06/12/2021 14:38:30, FULANA DE TAL`. So calcula."""
    lido = ler(texto)
    if not lido:
        return ""
    pedacos = []
    if lido.get("ato"):
        pedacos.append(f"Ato: {lido['ato']}")
    if lido.get("data"):
        pedacos.append(f"{lido['data']} {lido.get('hora') or ''}".strip())
    if lido.get("partes"):
        pedacos.append(str(lido["partes"]))
    return ", ".join(pedacos)


def consulta(texto: Any) -> str:
    """O endereço para consultar o selo — `https://selo.tjma.jus.br`, do

    jeito que o próprio aparelho escreve. Texto vazio quando o selo não o
    declara (selo digitado à mão, sem o texto completo do aparelho).
    """
    lido = ler(texto)
    return str(lido.get("consulta") or "").strip()


def do_papel(item: Any) -> dict[str, str]:
    """Tudo o que um selo poe no papel, pronto para o modelo. So calcula.

    Aceita o dicionario de `sd_selos` (`numero`, `texto`) ou so o texto.
    Os valores com `_` na frente sao os **numeros**, para quem precisa somar —
    o texto formatado nao se soma.
    """
    if isinstance(item, dict):
        texto = item.get("texto")
        numero = str(item.get("numero") or "").strip()
    else:
        texto, numero = item, ""
    lido = ler(texto)
    fundos = lido.get("fundos") or {}
    fora = {
        "numero": numero or str(lido.get("codigo") or "").strip(),
        "detalhe": detalhe(texto),
        "valores": linha_de_valores(texto),
        "consulta": str(lido.get("consulta") or "").strip(),
        "total": moeda(lido.get("total")),
        "emol": moeda(lido.get("emolumentos")),
        "_total_n": lido.get("total"),
        "_emol_n": lido.get("emolumentos"),
    }
    for sigla in FUNDOS_DO_PAPEL:
        chave = ROTULO_NO_PAPEL.get(sigla, sigla).lower()
        fora[chave] = moeda(fundos.get(sigla))
        fora[f"_{chave}_n"] = fundos.get(sigla)
    return fora


# ===================================================== O QUE O CARIMBO DIZ
#
# **DOIS FEITIOS, E UMA REGUA SO** — 17/09/2026, ordem do oficial: «preciso
# que o carimbo das certidoes (todas) saia com data e hora da emissao,
# emolumentos, qr code, link de acesso ao tj, requerente».
#
# O que muda entre o carimbo do ATO e o da CERTIDAO esta declarado aqui, e
# nao espalhado por quem desenha o papel: `ri_odt` monta o ODF e o molde do
# RCPN preenche marcadores `@`, e os dois perguntam a esta funcao o que dizer.

ATO = "ato"
CERTIDAO = "certidao"


def marcas(texto: Any) -> str:
    """`Selo Isento`, `Diferido` — o que o aparelho escreveu. So calcula.

    Medido no razao inteiro em 17/09/2026: **172 selos isentos e 53
    diferidos**, em 25.839 com texto. **Elas nao se deduzem do valor** — o
    selo isento desta casa traz os emolumentos escritos, e um carimbo que
    imprima so os numeros afirma que se cobrou.
    """
    lido = ler(texto)
    return " · ".join(lido.get("marcas") or [])


def requerente(texto: Any, rotulo: str = "Requerente") -> str:
    """`Requerente: FULANO DE TAL`, do que o selo declara. So calcula.

    **O SELO CHAMA O CAMPO DE `Parte(s)`**, e o rotulo daqui e escolha de quem
    imprime. Na certidao ele e fiel: medido nos 691 selos de certidao desta
    casa, **687 trazem o campo e em todos vem nome de pessoa** — nenhum traz o
    numero da matricula, que e o que o sistema manda quando nao ha requerente.
    """
    lido = ler(texto)
    nome = str(lido.get("partes") or "").strip()
    return f"{rotulo}: {nome}" if nome else ""


def link_de_consulta(numero: Any, texto: Any = "") -> str:
    """O endereco que abre ESTE selo no portal do TJMA. So calcula.

    **E melhor que o do aparelho, e de proposito.** Ele escreve
    `https://selo.tjma.jus.br` seco — o mesmo em 25.839 de 25.839 —, e quem
    recebe o papel tem de digitar o codigo de 28 caracteres a mao. O nosso
    leva `#/resumo/<codigo>` — **a rota da consulta daquele selo**, medida no
    portal em 24/09/2026 —, e e o mesmo endereco do QR: papel e leitura otica
    dizendo a mesma coisa. (Ate 24/09 ele levava `?selo=<codigo>`, que abre a
    tela de digitar, vazia.)

    Sem codigo, devolve o que o selo declarou — que ainda serve a quem digita.
    """
    codigo = str(numero or "").strip()
    if not codigo:
        codigo = str(ler(texto).get("codigo") or "").strip()
    if codigo:
        try:
            import notas_selo as NSELO
            endereco = NSELO.conteudo(NSELO.MODELO_PADRAO, codigo, "")
        except Exception:                                    # noqa: BLE001
            endereco = ""
        if endereco:
            return endereco
    return str(ler(texto).get("consulta") or "").strip()


def linhas_do_carimbo(texto: Any, numero: Any = "",
                      feitio: str = ATO) -> list[str]:
    """As linhas do carimbo, na ordem em que se leem. So calcula.

    Nao inclui o rotulo nem o link: aquele e de quem chama (ha carimbo de ato
    e carimbo de certidao no mesmo papel), e o link tem forma propria em cada
    desenho — no ODF e uma linha de texto, no molde do RCPN e um hiperlink.

    **O NUMERO VEM DE FORA quando quem chama ja o decidiu** — e o caso da
    etiqueta que o leitor nao reconhece, em que o carimbo sai com o texto cru
    em vez de sair vazio.
    """
    codigo = (str(numero or "").strip()
              or str(ler(texto).get("codigo") or "").strip())
    return [x for x in (
        codigo,
        ato_e_data(texto, feitio),
        requerente(texto) if feitio == CERTIDAO else "",
        valores_com_marcas(texto),
    ) if x]


def ato_e_data(texto: Any, feitio: str = ATO) -> str:
    """A segunda linha do carimbo: o item da tabela e quando o selo saiu.

    **DUAS FORMAS, E A DIFERENCA E DE LEITOR.** No ato, o carimbo esta dentro
    do livro e ao lado do proprio ato — `Ato: 16.24.4 · 17/09/2026 16:30:36`
    basta, e cada caractere ali custa espaco de livro. Na certidao, quem le e
    o banco, o comprador ou o juiz, e o papel diz por extenso o que afirma:
    `Ato 16.24.4 · emitida em 17/09/2026 às 16:30:36`.
    """
    lido = ler(texto)
    dia, hora = lido.get("data"), lido.get("hora")
    if feitio == CERTIDAO:
        quando = (f"emitida em {dia}" + (f" às {hora}" if hora else "")
                  if dia else "")
        pedacos = [f"Ato {lido['ato']}" if lido.get("ato") else "", quando]
    else:
        pedacos = [f"Ato: {lido['ato']}" if lido.get("ato") else "",
                   " ".join(x for x in (dia, hora) if x)]
    return " · ".join(x for x in pedacos if x)


def valores_com_marcas(texto: Any) -> str:
    """A linha do dinheiro, com o que o aparelho escreveu ao lado dela.

    **A MARCA ANDA COLADA NO NUMERO QUE ELA QUALIFICA.** O selo isento desta
    casa traz os emolumentos escritos — `Total R$ 115,44 … Selo Isento` —, e a
    marca numa linha propria, separada por um branco, deixaria de qualificar
    coisa nenhuma. Sem valores ela fica sozinha, porque continua sendo verdade.
    """
    partes = [x for x in (linha_de_valores(texto), marcas(texto)) if x]
    return " · ".join(partes)
