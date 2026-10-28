"""O XML do CENPROT que VOLTA — e a chave unica que ele devolve.

**A SERVENTIA NAO GERA A CHAVE, E NAO PRECISA.** Foi o oficial quem decidiu
isto em 26/08/2026, e por muito tempo ficou registrado neste projeto como um
buraco: `CENPROT_XML_MEDIDO.md` dizia que a chave de 23 digitos tem um
«verificador que nao se explica», e que isso impedia gerar o arquivo.

**O QUE SE EXPLICOU FOI O FIM DELA: os seis ultimos digitos sao a DATA DO
PROTOCOLO.** Medido em 01/09/2026 no arquivo que o oficial gerou, e conferido
contra o `<data_protocolo>` que o proprio XML declara — **175 de 175**. Duas
fontes dentro do mesmo arquivo.

    2198765   01412433     01    260417
    IBGE(7)   CENPROT(8) cart(2) AAMMDD(6)

**E EU LI O MEIO ERRADO NA PRIMEIRA VEZ.** Escrevi que as posicoes 8 e 9 sao o
numero do cartorio, porque aqui sao `01` em **175 de 175**. **Nao sao**: o
`CENPROT_XML_MEDIDO.md` deste projeto mediu 2.376 chaves de OUTRA serventia e
registra `2801405|0005640|2|01|200330` — com **`00`** naquelas duas posicoes.
O `01` daqui e o comeco do numero da Central, e nao o cartorio.

**Regularidade forte dentro de uma casa parece lei ate alguem olhar outra
casa** — e a outra casa ja estava medida, na nossa propria documentacao. E a
licao da posicao 566, pela segunda vez.

Entao o bloco 8–15 sao **oito digitos da Central**, e a leitura de la os separa
em protocolo(7) + verificador(1). **Aqui essa separacao nao se confirma**: o
nosso protocolo e `2604170001` e o bloco e `01412433`. Fica como esta —
`sequencial_cenprot`, sem afirmar o que ha dentro.

O que se confirma nas duas casas: **IBGE nas 1–7** e **cartorio nas 16–17**.

**E NAO PRECISAM SER COMPOSTOS**, porque cada `<titulo>` traz o `id` (a chave)
ao lado do `<protocolo>`, que e o nosso. Em 175 de 175. O arquivo entrega a
chave de graca; o que faltava era alguem le-la.

    `pt_titulos.chave_cenprot` existe desde o comeco e esta vazia nos 1.366.

**O CASAMENTO E POR DUAS PARTES, e nao so pelo protocolo.** A consequencia de
errar aqui e escrever no titulo de uma pessoa a chave do titulo de outra — e
essa chave viaja para a Central. E a mesma regra de `protesto_imagens`, e pelo
mesmo motivo: prender pela metade da chave mostra a divida de um terceiro.

**ESTE MODULO SO LE O ARQUIVO E PREENCHE A CHAVE.** Ele nao lavra ato, nao
muda situacao e nao toca em valor: o XML e uma FOTOGRAFIA do que a Central tem,
e deixar que ela reescrevesse o nosso livro seria inverter quem responde pelo
registro.

**E O ARQUIVO DE EMOLUMENTOS SE GERA — correcao do mesmo dia.** Ficou escrito
aqui, por algumas horas, que os valores «nao se reproduzem» e que faltavam
R$ 45,71 por titulo. Errado nas duas metades: a faixa era outra (eu somava a do
17.4 onde ia a do 17.1), e o resto era constante. Ver o bloco «o arquivo de
emolumentos», no fim deste modulo, e
`DOCUMENTACAO/CENPROT_OS_DOIS_ARQUIVOS_MEDIDOS.md`.

**O que desfez a conclusao errada nao foi releitura**: foi o oficial gerar o
arquivo do ANO INTEIRO e um print da tela de orcamento. **O que fecha lacuna de
layout e mais amostra**, pela quinta vez neste projeto.
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

import custas
from bd_nativo import banco

# A CHAVE, DECOMPOSTA — medido em 175 de 175 titulos.
TAMANHO_DA_CHAVE = 23
_SO_DIGITOS = re.compile(r"\D+")

# A versao que este arquivo trouxe. O contrato desta casa carrega a 1.22, e os
# XSDs de `arquivos\eoficio\CRA\Remessa` sao de 2017: a 1.23 NAO esta na casa. Ler um
# arquivo mais novo do que o contrato e seguro para os campos que lemos — o que
# nao se pode e GERAR na versao que ninguem conferiu.
VERSAO_MEDIDA = "1.23-geral"


class CenprotError(ValueError):
    """Erro de regra, com mensagem pronta para o balcao."""


def so_digitos(valor) -> str:
    return _SO_DIGITOS.sub("", str(valor or ""))


# ------------------------------------------------------------------ a chave


def decompor_chave(chave) -> dict | None:
    """Reparte a chave de 23 digitos nas quatro partes medidas.

    Devolve `None` para o que nao tem a forma — e nao estoura: quem chama esta
    lendo arquivo de fora, e arquivo de fora vem torto.
    """
    c = so_digitos(chave)
    if len(c) != TAMANHO_DA_CHAVE:
        return None
    # `sequencial_cenprot` sao OITO digitos e nao se abre mais que isso. A
    # leitura de Sergipe os separa em protocolo(7) + verificador(1); aqui essa
    # separacao nao se confirma, e afirmar o que nao se mediu e o que este
    # projeto chama de «carimbo que mente».
    return {"chave": c,
            "ibge": c[0:7],
            "sequencial_cenprot": c[7:15],
            "cartorio": c[15:17],
            "data_protocolo": c[17:23]}          # AAMMDD



# Pastas onde o E-Oficio guarda `.p7s` assinados (IPDigital). Medido em
# DOCUMENTACAO/REFERENCIAS_EOFICIO_BOOKC.md — so o nome do arquivo importa
# aqui: chave de 23 digitos + `.p7s`. Nao se abre nem se valida o PKCS#7.
# Hotfix de 16/10/2026: a cópia da casa, `<arquivos>/eoficio/IPDigital`, e não
# mais a pasta do E-Ofício nem o compartilhamento do servidor antigo.
def pastas_ipdigital(*, banco=None, archive_root: str | None = None) -> tuple[Path, ...]:
    import pastas_da_casa as PDC
    return (PDC.do_eoficio("IPDigital", banco=banco, archive_root=archive_root),)


def casar_ipdigital_por_chave(
    chaves,
    *,
    pastas: tuple[Path, ...] | list[Path] | None = None,
) -> list[dict]:
    """Casa `.p7s` cujo nome (sem extensao) e uma chave ja no banco. So LE.

    Devolve `{chave, caminho}` — caminho absoluto do arquivo, chave de 23
    digitos. Nao abre o `.p7s`, nao valida assinatura e nao inventa chave:
    so lista o que bate por nome com o que ja esta em `pt_titulos`.
    """
    queridas = {
        so_digitos(c) for c in (chaves or [])
        if len(so_digitos(c)) == TAMANHO_DA_CHAVE
    }
    if not queridas:
        return []
    saida: list[dict] = []
    vistos: set[str] = set()
    for pasta in (pastas if pastas is not None else pastas_ipdigital()):
        raiz = Path(pasta)
        if not raiz.is_dir():
            continue
        try:
            arquivos = list(raiz.glob("*.p7s")) + list(raiz.glob("*.P7S"))
        except OSError:
            continue
        for arq in arquivos:
            chave = so_digitos(arq.stem)
            if chave not in queridas or chave in vistos:
                continue
            vistos.add(chave)
            saida.append({"chave": chave, "caminho": str(arq.resolve())})
    saida.sort(key=lambda x: x["chave"])
    return saida


def data_do_protocolo(chave) -> str | None:
    """A data que a chave carrega, em AAAA-MM-DD. `None` se nao der para ler.

    O seculo NAO se adivinha por regra geral: o protesto desta casa comeca nos
    anos 2000, e `20` + AA e o que os 175 titulos medidos mostram. Se um dia
    chegar chave de 1900, ela aparece com data errada — e por isso quem usa
    isto **confere contra o protocolo**, que e o dado de verdade.
    """
    partes = decompor_chave(chave)
    if not partes:
        return None
    aa, mm, dd = (partes["data_protocolo"][0:2],
                  partes["data_protocolo"][2:4],
                  partes["data_protocolo"][4:6])
    if not ("01" <= mm <= "12" and "01" <= dd <= "31"):
        return None
    return f"20{aa}-{mm}-{dd}"


# ------------------------------------------------------------------ ler


def ler(conteudo) -> dict:
    """Le o XML e devolve o cabecalho e os titulos. So LE.

    O arquivo vem com BOM (o `\\ufeff` antes do `<?xml`), e o `ElementTree`
    estoura com ele na frente quando se passa texto.
    """
    if isinstance(conteudo, bytes):
        texto = conteudo.decode("utf-8-sig", errors="replace")
    else:
        texto = str(conteudo).lstrip("\ufeff")
    # O arquivo vem de fora (baixado da Central). DTD e entidade declarada nao
    # existem no XML do CENPROT, e sao o caminho da "bomba" de expansao de
    # entidades - a mesma recusa que a remessa XML da CRA ja faz
    # (protesto_cra_xml.ler).
    if "<!DOCTYPE" in texto.upper() or "<!ENTITY" in texto.upper():
        raise CenprotError(
            "Este arquivo traz DTD ou entidade declarada, e o XML do CENPROT "
            "nao tem nenhum dos dois. Confira se e o arquivo certo.")
    try:
        raiz = ET.fromstring(texto)
    except ET.ParseError as e:
        raise CenprotError(
            "Este arquivo nao e um XML do CENPROT que o sistema saiba ler: "
            f"{e}. Confira se e o arquivo certo — o do protesto tem a letra «P» "
            "no nome, como em MA-2198765-01-P-20260831-01.xml."
        ) from e

    titulos = []
    for apresentante in raiz.iter("apresentante"):
        codigo = (apresentante.get("codigo") or "").strip()
        nome = (apresentante.findtext("nome") or "").strip()
        for t in apresentante.iter("titulo"):
            titulos.append(_um_titulo(t, codigo, nome))
    return {"versao": (raiz.get("versao") or "").strip(),
            "uf": _atributo(raiz, "estado", "uf"),
            "comarca": _atributo(raiz, "cartorio", "comarca"),
            "cartorio": _atributo(raiz, "cartorio", "codigo"),
            "titulos": titulos}


def _atributo(raiz, tag: str, nome: str) -> str:
    for no in raiz.iter(tag):
        return (no.get(nome) or "").strip()
    return ""


def _um_titulo(t, apresentante_codigo: str, apresentante_nome: str) -> dict:
    """O que interessa de cada titulo — e nao o XML inteiro.

    NAO SE LE O QUE NAO SE VAI USAR. O XML traz endereco, cedente, sacador e os
    devedores todos; guardar tudo aqui daria a impressao de que este modulo
    atualiza o titulo, e ele nao atualiza: ele preenche UMA coluna.
    """
    return {"chave": (t.get("id") or "").strip(),
            "protocolo": (t.findtext("protocolo") or "").strip(),
            "data_protocolo": (t.findtext("data_protocolo") or "").strip(),
            "nosso_numero": (t.findtext("nosso_numero") or "").strip(),
            "numero_titulo": (t.findtext("numero_titulo") or "").strip(),
            "valor": (t.findtext("valor") or "").strip(),
            "apresentante_codigo": apresentante_codigo,
            "apresentante_nome": apresentante_nome}


# ------------------------------------------------------------------ conferir


def identidade_da_casa(config: dict) -> dict:
    """Quem e esta serventia, no vocabulario do CENPROT. So LE a configuracao.

    A COMARCA DO CENPROT E O CODIGO IBGE DO MUNICIPIO, e a casa ja o tem
    repartido em dois: `ibge_uf` (`21`) mais `ibge_municipio` (`98765`) dao
    `2198765`, que e exatamente o `comarca` do cabecalho do XML. **As duas
    fontes se conferem sozinhas**, e foi isso que permitiu usar a configuracao
    do IBGE aqui sem acreditar nela isoladamente.

    A regra mora NUM LUGAR SO. Montada na rota, ela divergiria desta no
    primeiro conserto — e o que ela decide e se o arquivo e desta casa.
    """
    faltando = [rotulo for chave, rotulo in
                (("ibge_uf", "o codigo da UF"),
                 ("ibge_municipio", "o codigo do municipio"),
                 ("ibge_cartorio", "o numero desta serventia"))
                if not str(config.get(chave) or "").strip()]
    if faltando:
        raise CenprotError(
            f"O sistema nao sabe {', '.join(faltando)}, e sem isso nao da para "
            f"conferir se o arquivo e desta casa. Isso se informa em "
            f"Administrativo — Configuracoes.")
    return {"comarca": (str(config["ibge_uf"]).strip().zfill(2)
                        + str(config["ibge_municipio"]).strip().zfill(5)),
            "cartorio": str(config["ibge_cartorio"]).strip().zfill(2)}


def conferir_a_casa(lido: dict, *, comarca: str, cartorio: str) -> None:
    """Recusa arquivo que NAO E DESTA SERVENTIA. Estoura, e e para estourar.

    **ESTE GUARDA NASCEU AO CONSTRUIR A TELA**, e ele fecha o unico jeito de o
    casamento por duas partes errar: dois arquivos de casas diferentes podem
    ter o mesmo protocolo e o mesmo nosso numero, porque nenhum dos dois e
    nacional. Sem isto, carregar o arquivo da serventia vizinha escreveria
    chaves ALHEIAS nos titulos daqui — e elas viajam para a Central.

    O cabecalho do XML declara os dois, e a casa sabe quem e: `ibge_uf` +
    `ibge_municipio` dao a comarca (`21` + `98765` = `2198765`) e
    `ibge_cartorio` da o cartorio. **Sao as mesmas quatro configuracoes que a
    remessa do IBGE ja usa**, e as duas fontes se conferem sozinhas.

    E ele NAO E OPCIONAL: quem chama `conferir` tem de dizer de quem e a casa.
    Guarda que se pode esquecer de pedir e guarda que um dia nao e pedido.
    """
    comarca, cartorio = so_digitos(comarca), so_digitos(cartorio)
    if not comarca or not cartorio:
        raise CenprotError(
            "O sistema nao sabe o codigo IBGE nem o numero desta serventia, e "
            "sem eles nao da para conferir se o arquivo e desta casa. "
            "Informe-os em Administrativo — configuracoes do IBGE.")
    do_arquivo = (so_digitos(lido["comarca"]), so_digitos(lido["cartorio"]))
    if do_arquivo != (comarca, cartorio):
        raise CenprotError(
            f"Este arquivo NAO e desta serventia: ele e da comarca "
            f"{lido['comarca']}, cartorio {lido['cartorio']}, e esta casa e a "
            f"comarca {comarca}, cartorio {cartorio}. Carregar arquivo de "
            f"outra casa escreveria nos nossos titulos as chaves dos titulos "
            f"dela.")


def conferir(con: Any, conteudo, *, comarca: str,
             cartorio: str) -> dict:
    """Diz quais chaves entrariam, quais nao, e por que. NAO GRAVA NADA.

    E o primeiro dos dois passos, como na remessa e no pacote de imagens: quem
    olha esta lista esta prestes a escrever, no titulo de gente de verdade, a
    chave com que a Central o conhece.
    """
    lido = ler(conteudo)
    conferir_a_casa(lido, comarca=comarca, cartorio=cartorio)
    entram, ja_tem, fora, divergem = [], [], [], []

    for item in lido["titulos"]:
        motivo = _por_que_nao_entra(item)
        if motivo:
            fora.append({**item, "motivo": motivo})
            continue
        achado = _titulo_do_item(con, item)
        if achado is None:
            fora.append({**item, "motivo":
                         "nenhum titulo desta casa tem o protocolo "
                         "{}".format(item["protocolo"])})
            continue
        if achado.get("divergencia"):
            divergem.append({**item, "titulo_id": achado["id"],
                             "motivo": achado["divergencia"]})
            continue
        atual = (achado.get("chave_cenprot") or "").strip()
        linha = {**item, "titulo_id": achado["id"],
                 "numero_do_sistema": achado["numero_titulo"],
                 "chave_atual": atual}
        if atual == item["chave"]:
            ja_tem.append(linha)
        elif atual:
            divergem.append({**linha, "motivo":
                             "este titulo ja tem a chave {}, e o arquivo traz "
                             "{}".format(atual, item["chave"])})
        else:
            entram.append(linha)

    return {"versao": lido["versao"],
            "versao_conhecida": lido["versao"] == VERSAO_MEDIDA,
            "comarca": lido["comarca"], "cartorio": lido["cartorio"],
            "total": len(lido["titulos"]), "entram": entram,
            "ja_tem": ja_tem, "divergem": divergem, "fora": fora}


def _por_que_nao_entra(item: dict) -> str:
    if not decompor_chave(item["chave"]):
        return ("a chave «{}» nao tem os {} digitos do CENPROT"
                .format(item["chave"], TAMANHO_DA_CHAVE))
    if not item["protocolo"]:
        return "o arquivo nao diz o protocolo deste titulo"
    return ""


def _titulo_do_item(con: Any, item: dict) -> dict | None:
    """Acha o titulo pelo protocolo E confere por uma segunda coisa.

    OS DOIS JUNTOS. O protocolo e o numero desta casa e deveria bastar — mas
    «deveria bastar» e exatamente a suposicao que este projeto ja pagou caro (a
    posicao 566, o nosso numero das imagens). A chave que se escreve aqui
    **viaja para a Central**: se o protocolo casar com outro titulo, a casa
    passa a chamar o titulo de A pelo nome do titulo de B.

    A segunda parte e o **nosso numero** quando os dois lados o tem; sem ele, o
    **valor**. Nao havendo nenhum dos dois para conferir, o titulo entra em
    divergencia em vez de entrar calado — e a recusa **diz qual parte falhou**,
    porque o conserto de cada uma e diferente.
    """
    protocolo = so_digitos(item["protocolo"])
    if not protocolo:
        return None
    achados = banco(con).ler(
        """SELECT id, numero_titulo, nosso_numero, valor_centavos, chave_cenprot
             FROM pt_titulos
            WHERE digitos(coalesce(protocolo,'')) = %s ORDER BY id""", (protocolo,))
    if not achados:
        return None
    if len(achados) > 1:
        return {"id": achados[0]["id"],
                "numero_titulo": achados[0]["numero_titulo"],
                "divergencia":
                    "{} titulos desta casa tem o protocolo {} — o arquivo nao "
                    "diz qual deles e".format(len(achados), item["protocolo"])}

    achado = achados[0]
    nosso_arquivo = so_digitos(item["nosso_numero"])
    nosso_casa = so_digitos(achado["nosso_numero"])
    if nosso_arquivo and nosso_casa:
        if nosso_arquivo != nosso_casa:
            achado["divergencia"] = (
                "o protocolo {} bate, mas o nosso numero nao: o arquivo diz "
                "{} e o titulo desta casa e {}".format(
                    item["protocolo"], item["nosso_numero"],
                    achado["nosso_numero"]))
        return achado

    centavos = _centavos(item["valor"])
    if centavos is not None and achado["valor_centavos"]:
        if centavos != achado["valor_centavos"]:
            achado["divergencia"] = (
                "o protocolo {} bate, mas o valor nao: o arquivo diz "
                "R$ {:.2f} e o titulo desta casa e R$ {:.2f}".format(
                    item["protocolo"], centavos / 100,
                    achado["valor_centavos"] / 100))
        return achado

    achado["divergencia"] = (
        "o protocolo {} bate, e nao ha nosso numero nem valor para conferir se "
        "e o mesmo titulo".format(item["protocolo"]))
    return achado


def _centavos(valor) -> int | None:
    """`2007.8500` — o XML escreve com ponto e quatro casas."""
    try:
        return round(float(str(valor).replace(",", ".")) * 100)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------ guardar


def guardar(con: Any, conteudo, *, comarca: str,
            cartorio: str) -> dict:
    """Preenche `chave_cenprot` nos titulos que casaram. ESCREVE.

    **NAO RECEBE `agora`, e isso foi correcao do primeiro ensaio.** Eu havia
    escrito `SET chave_cenprot=?, atualizado_em=?` — e `pt_titulos` **nao tem**
    coluna `atualizado_em`: ela tem `criado_em`, e nenhum modulo desta casa
    carimba atualizacao. O nome era plausivel, que e o que mais se parece com
    medicao sem ser; quem me corrigiu foi rodar contra o banco de verdade.
    Parametro que nao e usado e pior que parametro nenhum: ele promete um
    carimbo que ninguem escreve.

    **O QUE NAO CASA NAO DERRUBA O ARQUIVO** — a mesma regra do lote da
    remessa: um titulo sem par sao 174 que continuam sendo o trabalho do dia.

    **E NAO SOBRESCREVE CHAVE QUE JA ESTA LA.** Titulo que ja tem chave
    diferente vai para `divergem` e espera o oficial: a chave e como a Central
    conhece o titulo, e trocar a que ja foi usada num arquivo enviado faria os
    dois lados falarem de titulos diferentes com o mesmo nome.
    """
    conferencia = conferir(con, conteudo, comarca=comarca, cartorio=cartorio)
    if not conferencia["entram"]:
        raise CenprotError(
            "Nenhuma chave deste arquivo entra: dos {} titulos, {} ja tem a "
            "mesma chave, {} divergem e {} nao casam com titulo nenhum desta "
            "casa.".format(conferencia["total"], len(conferencia["ja_tem"]),
                           len(conferencia["divergem"]),
                           len(conferencia["fora"])))

    bd = banco(con)
    for linha in conferencia["entram"]:
        # A GUARDA DO `WHERE` REPETE A DE `conferir`, DE PROPOSITO: entre
        # conferir e gravar pode ter passado outro balcao. Onde a regra pode
        # morar no banco, ela mora no banco.
        bd.escrever(
            """UPDATE pt_titulos SET chave_cenprot = %s
                WHERE id = %s AND trim(coalesce(chave_cenprot,'')) = ''""",
            (linha["chave"], linha["titulo_id"]))
    return {**conferencia, "gravadas": len(conferencia["entram"])}


# ------------------------------------------------------------------ o outro lado


def titulos_sem_chave(con: Any, limite: int = 200) -> list[dict]:
    """Os titulos que a Central conhece por uma chave que a casa nao tem.

    E o par de `conferir`, do lado de ca: sem a chave, o titulo existe nos dois
    lugares e os dois nao sabem que e o mesmo.
    """
    return banco(con).ler(
        """SELECT id, protocolo, numero_titulo, nosso_numero, situacao
             FROM pt_titulos
            WHERE trim(coalesce(chave_cenprot,'')) = ''
              AND trim(coalesce(protocolo,'')) <> ''
            ORDER BY id DESC LIMIT %s""", (limite,))


def quantos_sem_chave(con: Any) -> dict:
    """Quantos tem chave, quantos nao tem, e quantos nem protocolo tem.

    OS TRES NUMEROS, E NAO UM. «Faltam 1.366» esconde que a maioria falta por
    um motivo que este modulo nao resolve — sem protocolo nao ha por onde
    casar, e o protocolo vem da carga do acervo.
    """
    linha = banco(con).um(
        """SELECT count(*)::int AS total,
                  sum(CASE WHEN trim(coalesce(chave_cenprot,'')) <> ''
                           THEN 1 ELSE 0 END)::int AS com_chave,
                  sum(CASE WHEN trim(coalesce(protocolo,'')) = ''
                           THEN 1 ELSE 0 END)::int AS sem_protocolo
             FROM pt_titulos""")
    total, com_chave, sem_protocolo = (linha["total"] or 0,
                                       linha["com_chave"] or 0,
                                       linha["sem_protocolo"] or 0)
    return {"total": total, "com_chave": com_chave,
            "sem_protocolo": sem_protocolo,
            "a_preencher": total - com_chave - sem_protocolo}


# ------------------------------------------------- o arquivo de emolumentos
#
# O QUE O DEVEDOR PAGA PARA LIMPAR O NOME, e a Central publica para ele saber
# antes de vir ao balcao. Sao dois valores por titulo: **retirada** (paga antes
# de o protesto ser lavrado) e **cancelamento** (paga depois).
#
# O FORMATO E O MAIS SIMPLES DE TODOS os arquivos deste modulo — seis campos
# separados por `|`, com linha de cabecalho:
#
#   nm_chave|vl_retirada|vl_cancelamento|cd_ibge|nr_cartorio|dt_movimento
#   21987650120701501241219|96.54|248.26|2198765|01|20260831
#
# **E OS VALORES SE EXPLICARAM EM 01/09/2026**, depois de o oficial gerar o
# arquivo do ANO INTEIRO (375 titulos, dez/24 a dez/25) e um print da tela de
# orcamento do E-Oficio. Medido contra ele: **166 de 173** titulos que deu para
# casar com o acervo batem NO CENTAVO, nos dois valores.
#
#   retirada     = 82,64  + faixa 17.4 (pelo valor do titulo)
#   cancelamento = 224,68 + faixa 17.1 (pelo valor do titulo)
#
# **E as duas faixas sao o que a norma diz que sao**: o item 17.4 e «quando,
# apos o apontamento e antes ou depois da intimacao, ocorrer a **liquidacao do
# titulo ou a desistencia**» — a retirada; e o 17.1 e «**protesto** de titulo de
# credito (sobre o valor do titulo)» — o que se cancela. As fronteiras batem no
# centavo: R$ 220,00 cai na 17.4.2 (68,03 a 220,07) e R$ 233,25 na 17.4.3
# (220,08 a 413,47), e o preco muda exatamente ali.
#
# **AS CONSTANTES NAO SE DECOMPOEM, E EU DISSE QUE SIM.** Escrevi que cada uma
# fechava de um jeito so, a partir dos seis itens do print — e a unicidade vinha
# de eu ter escolhido os seis. Com todos os 18 itens fixos do grupo 17 sao
# **9 combinacoes** para os 82,64 e **42** para os 224,68. Somar itens de tabela
# ate dar o numero sempre fecha: e a armadilha da busca exaustiva que ja falhou
# no verificador do boleto e no da matricula de 32 digitos, e ali eu soube
# parar.
#
# Quem me desmentiu foi `tbAvisoProtesto.curArquivamento_Valor`, que o oficial
# mandou procurar: ela e **zero nos 167 titulos que casei**, e o preco deles
# carrega a constante inteira. Logo a constante nao e arquivamento.

# E A DECOMPOSICAO SE CONFIRMOU — pelo arquivo de EDITAL, que nomeia os itens.
#
# Eu tinha proposto esta receita a partir do print do orcamento, depois me
# corrigi dizendo que era numerologia (9 somas dao 82,64), e a correcao e que
# estava errada: `E140826.XML` traz, por titulo, um bloco `<custas>` com um
# `<encargo>` por item, **com o nome por extenso**. Nao e busca combinatoria:
# e o E-Oficio dizendo o que cobrou.
#
#   <encargo><nome>Distribuicao extrajudicial de titulos…</nome><valor>11.85</valor>
#   <encargo><nome>Intimacao ou edital por titulo…</nome><valor>10.58</valor>
#   <encargo><nome>Quando, apos o apontamento (…) liquidacao…</nome><valor>17.93</valor>
#   <encargo><nome>Arquivamento, por folha do documento</nome><valor>26.76</valor>
#   <encargo><nome>Diligencia para entrega de intimacao</nome><valor>26.02</valor>
#
# **O ARQUIVO DE EDITAL ESCREVE OS ITENS SEM O FERRFIS**, e e isso que explica
# a diferenca: 11,85 = 11,96 − 0,11; 17,93 = 18,09 − 0,16. Reconstruido item a
# item, ele bate em **6 de 6** titulos, no centavo. O arquivo de EMOLUMENTOS,
# esse, leva o total inteiro.
#
# **E O `17.9` E POR FOLHA**: 26,76 = 4 x 6,69. Os titulos do edital tem
# QUATRO folhas; os do arquivo de emolumentos do ano tem CINCO (166 de 173).
# Nao e contradicao — e o que a norma diz que o item e.
#
# TERCEIRA VEZ NESTE FIO QUE MAIS DADO MUDA A CONCLUSAO, e a segunda em que a
# correcao que eu fiz era pior que o original. **Quando a duvida for entre
# «medi errado» e «nao ha como saber», o caminho e pedir outro arquivo.**

# Os itens, medidos e nomeados. A constante NAO e mais escrita: ela se calcula
# da tabela, e por isso acompanha a proxima vigencia sozinha.
ITENS_FIXOS_DA_RETIRADA = ("17.7", "17.2", "17.10.1")
ITEM_POR_FOLHA = "17.9"
ITENS_A_MAIS_DO_CANCELAMENTO = ("17.3", "17.5.1", "17.5.1")   # a certidao, 2x
FOLHAS_ARQUIVADAS = 5           # medido no arquivo do ano: 166 de 173

# O que a conta TEM de dar na vigencia em que foi medida. Se um dia divergir,
# o teste fica vermelho — que e melhor que o arquivo sair errado calado.
CONSTANTE_RETIRADA_MEDIDA = 8264
CONSTANTE_CANCELAMENTO_MEDIDA = 22468
VIGENCIA_MEDIDA = 10022
FAIXA_DA_RETIRADA = "17.4"
FAIXA_DO_CANCELAMENTO = "17.1"

CABECALHO_EMOLUMENTOS = ("nm_chave|vl_retirada|vl_cancelamento|cd_ibge"
                         "|nr_cartorio|dt_movimento")


def _faixas(con: Any, grupo: str, vigencia: int) -> list[tuple]:
    """As bandas de valor de um item, em centavos. So LE."""
    def centavos(texto) -> int:
        return round(float(str(texto).replace(".", "").replace(",", ".")) * 100)

    linhas = banco(con).ler(
        """SELECT de, ate, total FROM cx_faixas
            WHERE vigencia = %s AND codigo_tj ILIKE %s ORDER BY id""",
        (vigencia, grupo + ".%"))
    return [(centavos(r["de"]), centavos(r["ate"]), centavos(r["total"]))
            for r in linhas]


def _preco_do_item(con: Any, codigo_tj: str,
                   vigencia: int) -> int | None:
    """O total de um item da tabela, em centavos — com os quatro fundos."""
    def centavos(texto) -> int:
        return round(float(str(texto).replace(".", "").replace(",", ".")) * 100)

    linha = banco(con).um(
        """SELECT v.total FROM cx_servicos s
             JOIN cx_servico_valores v ON v.servico = s.codigo
            WHERE v.vigencia = %s AND s.codigo_tj = %s
            ORDER BY v.id LIMIT 1""",
        (vigencia, codigo_tj))
    return centavos(linha["total"]) if linha and linha["total"] else None


def constantes(con: Any, vigencia: int) -> dict:
    """A parte FIXA dos dois precos, somada da tabela. So LE.

    **NAO SE ESCREVE O NUMERO: SOMA-SE.** Escrito, ele ficaria parado na
    vigencia em que foi medido, e o arquivo publicaria na Central o preco do
    ano passado no dia em que o TJMA mudasse a tabela — sem ninguem perceber,
    porque um numero fixo nao tem como avisar que envelheceu.

    Devolve `None` no que a tabela nao souber responder: item que falta e
    tabela carregada pela metade, e ali o certo e parar.
    """
    fixos = [_preco_do_item(con, c, vigencia) for c in ITENS_FIXOS_DA_RETIRADA]
    folha = _preco_do_item(con, ITEM_POR_FOLHA, vigencia)
    a_mais = [_preco_do_item(con, c, vigencia)
              for c in ITENS_A_MAIS_DO_CANCELAMENTO]
    if None in fixos or folha is None:
        return {"retirada": None, "cancelamento": None, "faltando": True}
    retirada = sum(fixos) + folha * FOLHAS_ARQUIVADAS
    if None in a_mais:
        return {"retirada": retirada, "cancelamento": None, "faltando": True}
    return {"retirada": retirada, "cancelamento": retirada + sum(a_mais),
            "faltando": False}


def precos_do_titulo(con: Any, valor_centavos: int, *,
                     vigencia: int) -> dict:
    """O que o devedor paga para retirar e para cancelar. So LE.

    **A FAIXA E PELO VALOR DO TITULO**, e valor sem faixa nao devolve zero:
    devolve `None`, e quem chama trata. Zero num arquivo de precos e uma
    afirmacao — «nao custa nada» —, e o devedor viria ao balcao com ela.
    """
    base = constantes(con, vigencia)
    r = c = None
    if base["retirada"] is not None:
        for de, ate, total in _faixas(con, FAIXA_DA_RETIRADA, vigencia):
            if de <= valor_centavos <= ate:
                r = base["retirada"] + total
                break
    if base["cancelamento"] is not None:
        for de, ate, total in _faixas(con, FAIXA_DO_CANCELAMENTO, vigencia):
            if de <= valor_centavos <= ate:
                c = base["cancelamento"] + total
                break
    return {"retirada": r, "cancelamento": c}


def _reais(centavos: int) -> str:
    """`96.54` — o arquivo usa PONTO decimal, e nao virgula.

    Medido nas 375 linhas: `138.96`, `319.54`. Escrever no formato brasileiro
    faria a Central ler outro numero, ou nenhum.
    """
    return f"{centavos // 100}.{centavos % 100:02d}"


def nome_do_arquivo(*, uf: str, comarca: str, cartorio: str, data: str,
                    sequencial: int = 1) -> str:
    """`MA-2198765-01-E-20260831-01.txt` — a forma medida do nome.

    A letra **E** e a do arquivo de emolumentos; o de protestados leva **P**.
    """
    return (f"{uf}-{so_digitos(comarca)}-{so_digitos(cartorio)}-E-"
            f"{so_digitos(data)}-{sequencial:02d}.txt")


def titulos_do_arquivo(con: Any) -> list[dict]:
    """Os titulos que entram: **protesto vivo, e com chave da Central**.

    MEDIDO NO ARQUIVO REAL: os 173 que deu para casar sao todos `snProtestado=1`
    e `snCanceladoProtesto=0` — **protesto lavrado e ainda nao cancelado**. Faz
    sentido: o arquivo diz ao devedor quanto custa limpar o nome, e nao ha o que
    limpar num titulo que nunca foi protestado nem num que ja foi cancelado.

    **E SEM A CHAVE NAO HA LINHA**, porque ela e o primeiro campo. E por isso
    que este arquivo depende do importador do XML: e la que a chave entra.
    """
    return banco(con).ler(
        """SELECT id, chave_cenprot, valor_centavos, numero_titulo, protocolo
             FROM pt_titulos
            WHERE situacao = 'PROTESTADO'
              AND trim(coalesce(chave_cenprot,'')) <> ''
            ORDER BY chave_cenprot, id""")


def gerar_emolumentos(con: Any, *, comarca: str, cartorio: str,
                      uf: str, data: str, sequencial: int = 1) -> dict:
    """Monta o arquivo de emolumentos do CENPROT. So LE.

    **ELE SEGUE A TABELA DO DIA, e isso mudou depois de o oficial subir o
    arquivo de edital.** Enquanto a receita da constante era desconhecida, este
    modulo **recusava** gerar em qualquer vigencia que nao a 10022 — porque um
    numero fixo publicaria na Central o preco do ano passado. Agora a constante
    se **soma da tabela** (`constantes`), e acompanha a virada sozinha.

    **O QUE FICA GUARDADO E A CONFERENCIA**: ha teste que exige a soma bater
    com os valores medidos na 10022. Se um dia divergir, o vermelho aparece
    aqui e nao no balcao.

    **O QUE NAO TEM FAIXA NAO VIRA LINHA COM ZERO** — sai da lista com o
    motivo. Zero num arquivo de precos e uma afirmacao: «nao custa nada».
    """
    # A EXCECAO DE `custas` NAO ATRAVESSA ESTE MODULO. Quem chama aqui trata
    # `CenprotError`; obrigar a rota a conhecer tambem a de custas e como uma
    # rota deixa de tratar um erro de regra e devolve HTTP 500 ao balcao.
    try:
        vigente = custas.vigencia_do_dia(con, data)
    except custas.CustasError as erro:
        raise CenprotError(str(erro)) from erro
    vigencia = int(vigente["codigo"])
    if constantes(con, vigencia)["faltando"]:
        raise CenprotError(
            f"A tabela de emolumentos {vigencia} nao tem todos os itens que "
            f"este arquivo cobra ({', '.join(ITENS_FIXOS_DA_RETIRADA)}, "
            f"{ITEM_POR_FOLHA}, "
            f"{', '.join(sorted(set(ITENS_A_MAIS_DO_CANCELAMENTO)))}). "
            f"Importe a tabela do sistema antigo de novo antes de gerar — arquivo de "
            f"precos com item faltando publica na Central um valor menor que o "
            f"que a casa cobra.")

    linhas, fora = [], []
    for t in titulos_do_arquivo(con):
        precos = precos_do_titulo(con, int(t["valor_centavos"] or 0),
                                  vigencia=vigencia)
        if precos["retirada"] is None or precos["cancelamento"] is None:
            fora.append({**t, "motivo":
                         f"o valor R$ {(t['valor_centavos'] or 0) / 100:.2f} "
                         f"nao cai em nenhuma faixa da tabela"})
            continue
        linhas.append("|".join((
            t["chave_cenprot"], _reais(precos["retirada"]),
            _reais(precos["cancelamento"]), so_digitos(comarca),
            so_digitos(cartorio), so_digitos(data))))

    # FIM DE LINHA CRLF, E SEM BOM — medido no arquivo real, byte a byte. O
    # `\n` sozinho pareceria igual em qualquer editor daqui e chegaria
    # diferente na Central, que e o pior tipo de diferenca: a que so aparece
    # do lado de la.
    return {"nome": nome_do_arquivo(uf=uf, comarca=comarca, cartorio=cartorio,
                                    data=data, sequencial=sequencial),
            "conteudo": "\r\n".join([CABECALHO_EMOLUMENTOS, *linhas]) + "\r\n",
            "linhas": len(linhas), "fora": fora,
            "vigencia": vigencia}


# ------------------------------------------- o EDITAL ELETRONICO do CENPROT
#
# O TERCEIRO ARQUIVO, medido em 01/09/2026 nos dois exemplares que o oficial
# salvou. Ele e o que se MANDA para a Central publicar o edital — e nao se
# confunde com `protesto_aviso`, que lavra o ATO. Aqui so se escreve o arquivo.
#
#   Edital_Eletronico_2198765_14082026_001.xml
#   ^nome fixo         ^comarca ^DDMMAAAA      ^sequencial
#
# CADA `<edital>` TEM OS MESMOS 18 CAMPOS, em 6 de 6 — uma forma so.
#
# **O `documento` VAI COM MASCARA** (`000.000.020-54`), ao contrario de todo o
# resto deste modulo. E a unica coisa deste arquivo que contraria o costume da
# casa, e por isso esta escrita aqui: quem puser `so_digitos` ali quebra o
# arquivo sem ver.
#
# **E O VALOR VAI DE DUAS FORMAS, NO MESMO REGISTRO**: `valortitulo` com
# VIRGULA (`243,4400`) e `valorfinal` com PONTO (`243.4400`), os dois com
# quatro casas. Nao e engano do exemplar: e assim nos 6.
#
# **`finalidade` E O MOTIVO DA NAO-ENTREGA**, literal do catalogo do E-Oficio:
# «Falecido» (codigo 4) e «Ausente» (11) sao os dois que aparecem, e os dois
# estao em `tbMotivoNEntrega.strMotivo` com essa grafia. E o que justifica o
# edital existir — sem ele, a Central publica sem dizer por que.
#
# **E `numerotitulo` E O NUMERO DO TITULO, e nao o nosso numero** — decidido
# por UM titulo, o unico dos seis em que os dois diferem: o protocolo
# 2608110001 tem numero `00123` e nosso numero `009620400000035`, e o edital
# publica **`00123`**. Nos outros cinco os dois sao iguais e nao decidiriam
# nada. **Um caso que separa vale mais que cinco que concordam.**

CAMPOS_DO_EDITAL = ("nome", "documento", "cep", "numres", "bairro", "cidade",
                    "estado", "numerotitulo", "valortitulo", "emissaotitulo",
                    "vencimentotitulo", "Especie", "Protocolo",
                    "dataApresentacao", "valorfinal", "nomecredor",
                    "doccredor", "finalidade")


def _mascara_do_documento(numero, tipo) -> str:
    """`000.000.020-54` — o edital vai COM mascara, e so ele.

    NAO SE INVENTA A MASCARA PELO TAMANHO: quem diz se e CPF ou CNPJ e o
    `documento_tipo` do devedor, que a carga ja traz medido do acervo — «o tipo
    diz onde esta o documento, e nao o tamanho do que esta escrito». Documento
    que nao tem o tamanho da sua especie sai **como esta**: melhor um numero
    cru que um numero remontado errado.
    """
    d = so_digitos(numero)
    especie = str(tipo or "").strip().upper()
    if especie in ("CPF", "F") and len(d) == 11:
        return f"{d[0:3]}.{d[3:6]}.{d[6:9]}-{d[9:11]}"
    if especie in ("CNPJ", "J") and len(d) == 14:
        return f"{d[0:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:14]}"
    return str(numero or "").strip()


def _valor_do_edital(centavos, *, separador: str) -> str:
    """`243,4400` e `243.4400` — quatro casas, e os dois no mesmo registro."""
    inteiro, resto = divmod(int(centavos or 0), 100)
    return f"{inteiro}{separador}{resto:02d}00"


def nome_do_edital(*, comarca: str, dia: str, sequencial: int = 1) -> str:
    """`Edital_Eletronico_2198765_14082026_001.xml` — a forma medida.

    A data vai **DDMMAAAA**, ao contrario do arquivo de emolumentos, que a
    escreve AAAAMMDD. Sao dois arquivos da mesma Central com duas convencoes, e
    trocar uma pela outra faz o nome parecer certo e a data ficar errada.
    """
    d = str(dia)[:10].split("-")
    return (f"Edital_Eletronico_{so_digitos(comarca)}_"
            f"{d[2]}{d[1]}{d[0]}_{sequencial:03d}.xml")


def _motivo_do_edital(con: Any, titulo_id: int) -> str:
    """Por que este titulo foi a edital. So LE.

    Sai do ato de INTIMACAO por edital, onde a carga guardou o motivo do
    acervo. **Sem motivo o campo fica VAZIO, e nao inventado** — a Central
    publica assim mesmo, e um motivo errado no edital afirma sobre a pessoa
    uma coisa que ninguem apurou.
    """
    bd = banco(con)
    linha = bd.um(
        """SELECT detalhe_json FROM pt_atos
            WHERE titulo_id = %s AND tipo = 'INTIMACAO'
            ORDER BY id DESC LIMIT 1""", (int(titulo_id),))
    if not linha:
        return ""
    try:
        detalhe = json.loads(linha["detalhe_json"] or "{}")
    except (TypeError, ValueError):
        detalhe = {}
    motivo = str(detalhe.get("motivo") or "").strip()
    if motivo:
        return motivo
    # O EDITAL QUE ESTE SISTEMA PUBLICA guarda o motivo no AVISO, e não no ato
    # — achado em 15/10/2026, ao levar o motivo ao XML diário: até aqui o
    # edital eletrônico dos editais novos sairia com este campo vazio. Ele
    # vem do catálogo medido (`tbMotivoNEntrega`), como «Ausente».
    import protesto_aviso as AV
    aviso = bd.um(
        """SELECT motivo FROM pt_avisos WHERE titulo_id = %s AND
               situacao = 'EDITAL' AND motivo IS NOT NULL
            ORDER BY id DESC LIMIT 1""", (int(titulo_id),))
    return AV.motivo_rotulo(aviso["motivo"]) if aviso else ""


def gerar_edital_eletronico(con: Any, *, dia: str,
                            comarca: str, sequencial: int = 1) -> dict:
    """Monta o XML do edital eletronico do dia. So LE.

    A FONTE SAO OS EDITAIS JA PUBLICADOS NAQUELE DIA — `pt_editais` —, e nao
    uma lista de «quem precisa de edital». O ato vem antes do arquivo: publicar
    e do modulo do aviso, que numera, congela o teor e o amarra ao aviso. Aqui
    so se escreve o que ja foi lavrado.

    **TITULO SEM DEVEDOR NAO VIRA REGISTRO EM BRANCO** — sai da lista com o
    motivo. O edital identifica uma pessoa; um registro sem nome publicaria um
    aviso sobre ninguem.
    """
    import protesto_aviso as PA

    bd = banco(con)
    linhas, fora = [], []
    for e in PA.editais_do_dia(con, dia):
        t = bd.um(
            """SELECT id, numero_titulo, especie, protocolo, valor_centavos,
                      data_emissao, data_vencimento, cedente_nome,
                      cedente_documento
                 FROM pt_titulos WHERE id = %s""", (e["titulo_id"],))
        d = bd.um(
            """SELECT nome, documento_tipo, documento_numero, bairro, cep,
                      cidade, uf FROM pt_devedores
                WHERE titulo_id = %s ORDER BY id LIMIT 1""",
            (e["titulo_id"],))
        if t is None or d is None or not str(d["nome"] or "").strip():
            fora.append({"edital": e["numero"], "titulo_id": e["titulo_id"],
                         "motivo": "o titulo nao tem devedor com nome, e o "
                                   "edital identifica uma pessoa"})
            continue
        campos = {
            "nome": d["nome"],
            "documento": _mascara_do_documento(d["documento_numero"],
                                               d["documento_tipo"]),
            "cep": so_digitos(d["cep"]),
            "numres": "",
            "bairro": d["bairro"],
            "cidade": d["cidade"],
            "estado": d["uf"],
            "numerotitulo": t["numero_titulo"],
            "valortitulo": _valor_do_edital(t["valor_centavos"],
                                            separador=","),
            "emissaotitulo": str(t["data_emissao"] or "")[:10],
            "vencimentotitulo": str(t["data_vencimento"] or "")[:10],
            "Especie": t["especie"],
            "Protocolo": t["protocolo"],
            "dataApresentacao": str(e["publicado_em"] or "")[:10],
            "valorfinal": _valor_do_edital(t["valor_centavos"],
                                           separador="."),
            "nomecredor": t["cedente_nome"],
            "doccredor": t["cedente_documento"],
            "finalidade": _motivo_do_edital(con, e["titulo_id"]),
        }
        corpo = []
        for campo in CAMPOS_DO_EDITAL:
            valor = escape(str(campos.get(campo) or "").strip())
            # CAMPO VAZIO SAI FECHADO EM SI (`<numres />`), que e como o
            # arquivo real escreve os seis `numres` e os dois `doccredor`.
            corpo.append(f"      <{campo}>{valor}</{campo}>" if valor
                         else f"      <{campo} />")
        linhas.append("    <edital>\r\n" + "\r\n".join(corpo)
                      + "\r\n    </edital>")

    conteudo = ('<?xml version="1.0" encoding="utf-8"?>\r\n  <editais>\r\n'
                + "\r\n".join(linhas) + ("\r\n" if linhas else "")
                + "  </editais>\r\n")
    return {"nome": nome_do_edital(comarca=comarca, dia=dia,
                                   sequencial=sequencial),
            "conteudo": conteudo, "editais": len(linhas), "fora": fora}
