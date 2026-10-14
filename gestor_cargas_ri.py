"""O agente de cargas do RI — as matrículas, o Indicador Real e o Indicador Pessoal ao ONR.

    «Agente de cargas do RI: esse agente sera o responsavel por viabilizar,
     fiscalizar e manter em dia as cargas do ri, com envio das matriculas,
     indicadores reais e pessoais a ONR» — o oficial, 09/10/2026

SÃO TRÊS CARGAS, POR TRÊS CANAIS, E CADA UMA TEM O SEU «ENVIADO»
    | carga                 | canal                                  | quem sobe            |
    |-----------------------|----------------------------------------|----------------------|
    | imagens do Livro 2    | pasta que o CSL2 lê (TIFF 200 dpi G4)  | o programa CSL2      |
    | Indicador Pessoal     | XML <BANCOLIGHT> na pasta do IPS       | o programa IPS       |
    | Indicador Real        | API do ONR (`ri_onr_central`)          | este agente, por HTTP|

    Nas duas primeiras o agente **entrega na pasta** e confere depois se o
    programa do ONR levou (o IPS move para `Processados`, que é o precedente do
    E-Ofício em `C:\\ARPNET\\C11\\ONR\\INDICADORES`). Na terceira ele **manda**,
    e confere a fila: enviar não é ser aceito.

O QUE ELE FAZ TODO DIA (`rodada`, chamada pela rodada das 07:30 do gestor)
    1. **Imagens** — converte para TIFF a digitalização oficial que mudou de
       sha (`ri_matriculas.digi_sha256` contra o controle da pasta), e baixa a
       marca `digi_onr_pendente`, que até 09/10/2026 ninguém baixava (as duas
       funções de `ri_digitalizacao` estavam sem chamador). **A marca só baixa
       depois que o CSL2 estiver lendo a pasta** (`onr_csl2_desde`): antes
       disso, estar na pasta não é estar no ONR.
    2. **Indicador Pessoal** — enquanto a carga inicial não foi levada pelo IPS,
       mantém a CARGA COMPLETA pronta (e só a regrava quando o conteúdo muda);
       depois dela, gera o incremental do que se lavrou desde o último arquivo,
       com o nome que o E-Ofício usava (`IndicadorPessoal_ddmmaaaa_ddmmaaaa.XML`).
    3. **Indicador Real** — confere a fila do ONR, manda o indicador das
       matrículas novas desta casa, e **reenvia o que mudou**: até aqui, depois
       de ENVIADO, a matrícula nunca voltava à lista, por mais atos que
       recebesse. Agora o corpo de hoje se compara com o `corpo_hash` do que
       subiu, e o que divergiu se corrige pelo PATCH, sem queimar o identificador.

O QUE ELE CONFERE (`conferir`, uma regra do gestor)
    Vira achado — e, no setor do RI, tarefa para quem responde pelas cargas — o
    indicador que não sobe por falta de campo (diz qual), o recusado pelo ONR, o
    que ficou parado na fila, o arquivo que o IPS não levou, e a imagem que não
    converteu. O que é DECISÃO do oficial (credencial, envio desligado, a carga
    inicial esperando a adesão, o indicador real do acervo) vai ao relatório e ao
    despacho, e não vira tarefa de ninguém.

O QUE ELE NÃO FAZ
    Não lavra, não sela, não cobra, não altera ficha. Não digita credencial
    (quem digita é o oficial) e não troca o ambiente do ONR: `onr_api` fala com a
    HOMOLOGAÇÃO até o código mudar — e é por isso que, ligado hoje, ele não
    publica nada no índice nacional de verdade.

    **E não manda o acervo.** `ri_onr_central.a_enviar` deixa de fora a ficha
    ACERVO porque «o E-Ofício já respondia ao ONR». Para o Indicador Real isso
    NÃO se sustenta: medido em 09/10/2026, o único arquivo de indicador real que
    o E-Ofício deixou (`INDICADOREAL\\IndicadorReal_01012025_01022025.json`) tem
    **3** matrículas — 3163, 142 e 3067. A decisão de subir o acervo é do
    oficial, e o agente a mostra com os números em vez de tomá-la.

O PRAZO
    Nenhum prazo normativo de envio ao ONR está lido nesta casa (procurado no
    código e na documentação em 09/10/2026). O que o agente cobra é a rotina do
    `PLANO_ONR_PASSO_A_PASSO.md`, etapa 10 — «ocorrências do IPS e CSL2 devem ser
    verificadas diariamente» —, com as tolerâncias abaixo, que são da casa.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
import threading
from contextlib import closing, contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from gestor_schema import init_gestor_schema

QUEM = "gestor"

# AS PASTAS, E DE ONDE VEIO CADA PADRÃO. Configuração (`settings`) ganha do
# código: trocar de pasta não pode exigir versão nova.
# ORDEM DO OFICIAL, 10/10/2026: «nao poderemos usar essas pastas, sao do sistema
# antigo, precisamos usar as pastas proprias do cartorio gestao». As pastas do
# ONR moram dentro dos arquivos do RI do sistema; o que estava em C:\ARPNET foi
# MOVIDO para cá no mesmo dia (3.984 matrículas de imagens e o controle delas).
# O histórico do E-Ofício (`C:\ARPNET\C11\ONR\INDICADORES\Processados`) ficou lá.
PASTA_CSL2_PADRAO = r"C:\ProgramData\CartorioGestao\arquivos\ri\onr\livro2"
PASTA_IPS_PADRAO = r"C:\ProgramData\CartorioGestao\arquivos\ri\onr\ips"
PASTA_CARGA_INICIAL_PADRAO = r"C:\ProgramData\CartorioGestao\arquivos\ri\onr\carga_inicial"

#: O interruptor do envio pela API. LIGADO por padrão: o pedido foi «com envio»,
#: e o que o segura de verdade é a credencial, que só o oficial digita.
CHAVE_ENVIO = "onr_cargas_envio"

#: Quanto se faz numa rodada. A rodada das 07:30 roda na máquina do balcão:
#: converter mil PDFs ali seria a casa abrir com o servidor ocupado.
TETO_IMAGENS_POR_RODADA = 150
TETO_INDICADORES_POR_RODADA = 30

#: Tolerâncias da casa (ver «O PRAZO» no cabeçalho).
IPS_DIAS_TOLERADOS = 2
FILA_DIAS_TOLERADOS = 3
AGENTE_DIAS_TOLERADOS = 1

#: A ficha arquivada (9040xx) é casca que saiu da sequência: não vai ao ONR.
NUMERO_DE_FICHA_ARQUIVADA = 900000

CANAL_IMAGENS = "IMAGENS"
CANAL_PESSOAL = "PESSOAL"
CANAL_REAL = "REAL"

FUNDAMENTO = ("Rotina permanente do PLANO_ONR_PASSO_A_PASSO.md, etapa 10. O prazo "
              "normativo de envio ao ONR não foi lido nesta casa — A CONFERIR.")

#: As regras que são decisão do oficial: medidas e relatadas, sem tarefa.
REGRAS_DE_DECISAO = frozenset({"ONR_CREDENCIAL", "ONR_ENVIO_DESLIGADO",
                               "ONR_CARGA_INICIAL", "ONR_ACERVO_DECISAO"})

ROTULOS = {
    "ONR_CREDENCIAL": "ONR — Indicador Real parado: falta a credencial",
    "ONR_ENVIO_DESLIGADO": "ONR — envio automático desligado",
    "ONR_CARGA_INICIAL": "ONR — carga inicial pronta, esperando a adesão",
    "ONR_ACERVO_DECISAO": "ONR — Indicador Real do acervo nunca subiu",
    "ONR_INDICADOR_INCOMPLETO": "ONR — matrículas cujo Indicador Real não sobe",
    "ONR_INDICADOR_RECUSADO": "ONR — Indicador Real recusado pelo ONR",
    "ONR_FILA_PARADA": "ONR — Indicador Real sem resposta da fila",
    "ONR_ENVIO_FALHOU": "ONR — envio do Indicador Real falhou",
    "ONR_IPS_NAO_LEVOU": "ONR — arquivo do Indicador Pessoal que o IPS não levou",
    "ONR_IMAGEM_PROBLEMA": "ONR — imagem da matrícula que não foi para a pasta",
    "ONR_AGENTE_PARADO": "ONR — o agente de cargas não rodou",
    "ONR_PASTA": "ONR — pasta de carga inexistente",
}


# ---------------------------------------------------------------- miúdos

def _agora() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _tem_tabela(con, nome: str) -> bool:
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                       (nome,)).fetchone() is not None


def configuracao(con, chave: str, padrao: str = "") -> str:
    if not _tem_tabela(con, "settings"):
        return padrao
    r = con.execute("SELECT value FROM settings WHERE key=?", (chave,)).fetchone()
    return (r[0] or "").strip() if r and (r[0] or "").strip() else padrao


def raiz_dos_arquivos(con, banco: Path | None) -> Path | None:
    """Onde moram os arquivos DESTA casa: `archive_root`, ou `arquivos` ao lado do banco.

    É a regra de `app.archive_root`. Sem o banco na mão (a conferência só recebe
    `con`), devolve `None` e vale o padrão escrito acima.
    """
    configurada = configuracao(con, "archive_root", "")
    if configurada:
        return Path(configurada).expanduser()
    return Path(banco).parent / "arquivos" if banco else None


def pastas(con, banco: Path | None = None) -> dict[str, Path]:
    """As três pastas. Configuração ganha; depois, a árvore de arquivos do banco.

    O PADRÃO SAI DO BANCO QUANDO SE SABE QUAL É — achado em 10/10/2026, ao ligar a
    conversão na hora do envio: com o padrão escrito, o teste de tela que sobe uma
    varredura num banco de ensaio escreveria TIFF **na pasta que o CSL2 da
    produção lê**, por cima das matrículas de verdade. Na produção dá o mesmo
    caminho (o banco mora em `C:\\ProgramData\\CartorioGestao`); no ensaio, a
    pasta do ensaio.
    """
    raiz = raiz_dos_arquivos(con, banco)
    base = raiz / "ri" / "onr" if raiz else None

    def pasta(chave, sub, padrao):
        return Path(configuracao(con, chave, str(base / sub) if base else padrao))

    return {
        "csl2": pasta("onr_csl2_pasta", "livro2", PASTA_CSL2_PADRAO),
        "ips": pasta("onr_ips_pasta", "ips", PASTA_IPS_PADRAO),
        "carga_inicial": pasta("onr_carga_inicial_pasta", "carga_inicial",
                               PASTA_CARGA_INICIAL_PADRAO),
    }


#: Desde quando o programa CSL2 do ONR lê a pasta das imagens. ENQUANTO NÃO HÁ
#: DATA, estar na pasta não é estar no ONR — e a marca `digi_onr_pendente` não
#: baixa: baixá-la diria «enviado» de uma imagem que não saiu da casa. Medido em
#: 09/10/2026: nenhum serviço nem processo IPS/CSL2 nesta máquina.
CHAVE_CSL2_DESDE = "onr_csl2_desde"


def csl2_em_uso(con) -> bool:
    return bool(configuracao(con, CHAVE_CSL2_DESDE, ""))


def envio_ligado(con) -> bool:
    return configuracao(con, CHAVE_ENVIO, "LIGADO").upper() != "DESLIGADO"


def _numero(texto) -> int | None:
    dig = "".join(c for c in str(texto or "") if c.isdigit())
    return int(dig) if dig else None


def _sha_arquivo(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _sha_texto(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _cns(con) -> str:
    return configuracao(con, "ri_cns", "")


def _registrar(con, canal: str, tipo: str, *, situacao: str, arquivo: str = "",
               sha256: str = "", quantos: int | None = None, periodo_de: str = "",
               periodo_ate: str = "", detalhe: Any = None) -> int:
    return int(con.execute(
        """INSERT INTO ge_onr_cargas (canal, tipo, periodo_de, periodo_ate, arquivo,
               sha256, quantos, situacao, gerado_em, detalhe)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (canal, tipo, periodo_de or None, periodo_ate or None, arquivo or None,
         sha256 or None, quantos, situacao, _agora(),
         json.dumps(detalhe, ensure_ascii=False) if detalhe is not None else None)
    ).lastrowid)


# ================================================================ 1. IMAGENS
#
# O formato é o de `instrucoes_imagens_livro2.pdf`, que `onr_carga.conferir_imagens`
# confere: `NNNNNNNN.PPPP`, pasta de 8 dígitos de mil em mil, 200 × 200 dpi, 1 bit,
# CCITT Group 4. A conversão MORA AQUI desde 09/10/2026; a ferramenta
# `FERRAMENTAS\exportar_imagens_onr.py` passou a chamá-la, para o formato não ter
# duas casas.

DPI = 200


def otsu(cinza) -> int:
    """Limiar de Otsu: separa tinta de papel página a página (papel amarelado não vira borrão)."""
    import numpy as np
    hist = np.bincount(cinza.ravel(), minlength=256).astype(np.float64)
    total = cinza.size
    soma = np.dot(np.arange(256), hist)
    peso_b = soma_b = 0.0
    melhor, limiar = -1.0, 128
    for t in range(256):
        peso_b += hist[t]
        if peso_b == 0:
            continue
        peso_f = total - peso_b
        if peso_f == 0:
            break
        soma_b += t * hist[t]
        mb, mf = soma_b / peso_b, (soma - soma_b) / peso_f
        entre = peso_b * peso_f * (mb - mf) ** 2
        if entre > melhor:
            melhor, limiar = entre, t
    return limiar


def pagina_em_tiff(pagina, destino: Path) -> None:
    import numpy as np
    import pymupdf
    from PIL import Image
    pix = pagina.get_pixmap(dpi=DPI, colorspace=pymupdf.csGRAY, alpha=False)
    cinza = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    t = otsu(cinza)
    bw = Image.fromarray(((cinza > t) * 255).astype(np.uint8)).convert(
        "1", dither=Image.Dither.NONE)
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_name(destino.name + ".tmp")
    bw.save(tmp, format="TIFF", compression="group4", dpi=(DPI, DPI))
    tmp.replace(destino)


def caminho_do_controle(destino: Path) -> Path:
    """O controle mora FORA da pasta que o CSL2 lê: lá dentro só pode haver imagem."""
    return Path(destino).with_name(Path(destino).name + "_controle") / "_controle.json"


def ler_controle(destino: Path) -> dict:
    c = caminho_do_controle(destino)
    return json.loads(c.read_text(encoding="utf-8")) if c.exists() else {}


def _gravar_controle(destino: Path, feito: dict) -> None:
    c = caminho_do_controle(destino)
    c.parent.mkdir(parents=True, exist_ok=True)
    tmp = c.with_name(c.name + ".tmp")
    tmp.write_text(json.dumps(feito, ensure_ascii=False), encoding="utf-8")
    tmp.replace(c)


# DOIS ESCRITORES NA MESMA PASTA, desde 10/10/2026: a rodada das 07:30 (outro
# processo) e a conversão na hora do envio (uma linha dentro do servidor). Até
# então o controle era lido no começo da rodada e regravado INTEIRO no fim — com
# dois escritores, o último apagaria o que o outro acabou de fazer. Agora cada um
# grava SÓ o que fez, sob trava, e a linha mais nova ganha (`em`).
TRAVA_VELHA_SEGUNDOS = 15 * 60
TRAVA_ESPERA_SEGUNDOS = 10 * 60


@contextmanager
def _trava_da_pasta(destino: Path):
    """Trava ENTRE PROCESSOS: um arquivo criado com O_EXCL ao lado do controle.

    Trava de processo que morreu não segura a casa para sempre: passados
    `TRAVA_VELHA_SEGUNDOS` ela é tida por abandonada. Uma matrícula se converte
    em segundos; quinze minutos é folga de sobra.
    """
    import os
    import time
    trava = caminho_do_controle(destino).with_name("_controle.trava")
    trava.parent.mkdir(parents=True, exist_ok=True)
    inicio = time.monotonic()
    while True:
        try:
            fd = os.open(str(trava), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"{os.getpid()} {_agora()}".encode())
            os.close(fd)
            break
        except FileExistsError:
            try:
                idade = time.time() - trava.stat().st_mtime
            except FileNotFoundError:
                continue
            if idade > TRAVA_VELHA_SEGUNDOS:
                trava.unlink(missing_ok=True)
                continue
            if time.monotonic() - inicio > TRAVA_ESPERA_SEGUNDOS:
                raise TimeoutError(f"a pasta do CSL2 está ocupada há mais de "
                                   f"{TRAVA_ESPERA_SEGUNDOS // 60} minutos ({trava})")
            time.sleep(0.2)
    try:
        yield
    finally:
        trava.unlink(missing_ok=True)


def _juntar_ao_controle(destino: Path, novos: dict) -> None:
    """Grava no controle SÓ o que este escritor fez; a linha mais nova ganha. Chame sob trava."""
    if not novos:
        return
    feito = ler_controle(destino)
    for num, linha in novos.items():
        atual = feito.get(num) or {}
        if (atual.get("em") or "") > (linha.get("em") or ""):
            continue
        feito[num] = linha
    _gravar_controle(destino, feito)


# A SITUAÇÃO DE CADA MATRÍCULA que a ficha mostra — «convertendo» e «não
# converteu, por quê». Mora AO LADO do controle, e não no banco: é estado da
# pasta, e escrever coluna nova em `ri_matriculas` seria mexer no esquema do RI,
# que tem dono. O que já está na pasta não precisa de linha aqui: o controle diz.
def caminho_da_situacao(destino: Path) -> Path:
    return caminho_do_controle(destino).with_name("_situacao.json")


def ler_situacao(destino: Path) -> dict:
    c = caminho_da_situacao(destino)
    try:
        return json.loads(c.read_text(encoding="utf-8")) if c.exists() else {}
    except (OSError, ValueError):
        return {}


def _marcar_situacao(destino: Path, num: int, linha: dict | None) -> None:
    """Grava (ou apaga, com `None`) a situação de uma matrícula. Chame sob trava."""
    s = ler_situacao(destino)
    if linha is None:
        if str(num) not in s:
            return
        s.pop(str(num), None)
    else:
        s[str(num)] = linha
    c = caminho_da_situacao(destino)
    c.parent.mkdir(parents=True, exist_ok=True)
    tmp = c.with_name(c.name + ".tmp")
    tmp.write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8")
    tmp.replace(c)


def imagens_pendentes(con, destino: Path, *, somente: set[str] | None = None) -> dict:
    """O que falta pôr na pasta do CSL2. SÓ LÊ.

    `pendentes`: digitalização cujo sha não está no controle (nova ou trocada).
    `so_baixar`: já está na pasta com o sha de hoje, e a marca ficou levantada.
    `problemas`: o que não dá para converter sem alguém olhar.
    """
    feito = ler_controle(destino)
    por_numero: dict[int, list] = {}
    for r in con.execute(
            "SELECT id, numero, digi_path, digi_sha256, digi_onr_pendente "
            "FROM ri_matriculas WHERE digi_path IS NOT NULL AND TRIM(digi_path) <> ''"):
        num = _numero(r[1])
        if num is None or num >= NUMERO_DE_FICHA_ARQUIVADA:
            continue
        por_numero.setdefault(num, []).append(tuple(r))
    pendentes, so_baixar, problemas = [], [], []
    for num in sorted(por_numero):
        if somente and str(num) not in somente:
            continue
        regs = por_numero[num]
        if len({r[3] for r in regs}) > 1:
            problemas.append({"numero": num, "matricula_id": regs[0][0],
                              "motivo": f"{len(regs)} fichas com o número {num} e "
                                        "digitalizações diferentes"})
            continue
        mid, _, caminho, sha, marca = regs[0]
        if feito.get(str(num), {}).get("sha") == sha:
            if any(r[4] for r in regs):
                so_baixar.extend(r[0] for r in regs)
            continue
        pendentes.append({"numero": num, "matricula_id": mid, "caminho": caminho,
                          "sha": sha, "ids": [r[0] for r in regs]})
    return {"pendentes": pendentes, "so_baixar": so_baixar, "problemas": problemas,
            "na_pasta": len(feito)}


def _converter_uma(pdf: Path, destino: Path, num: int) -> int:
    """Troca as páginas de UMA matrícula na pasta do CSL2. Devolve quantas são."""
    import pymupdf
    if not pdf.exists():
        raise FileNotFoundError(str(pdf))
    pasta = destino / f"{num // 1000:08d}"
    doc = pymupdf.open(pdf)
    try:
        n = doc.page_count
        for velho in pasta.glob(f"{num:08d}.*"):
            velho.unlink()
        for i, pagina in enumerate(doc, 1):
            pagina_em_tiff(pagina, pasta / f"{num:08d}.{i:04d}")
    finally:
        doc.close()
    return n


def _baixar_marca(con, ids) -> None:
    import ri_digitalizacao
    for mid in ids:
        ri_digitalizacao.marcar_onr_enviada(con, int(mid))


def exportar_imagens(con, destino: Path, *, limite: int | None = TETO_IMAGENS_POR_RODADA,
                     somente: set[str] | None = None, baixar_marca: bool = True,
                     escrever=None) -> dict:
    """Põe na pasta do CSL2 o que mudou. Um PDF ruim não para os outros.

    A marca `digi_onr_pendente` baixa quando a imagem do sha de hoje está na
    pasta — que, na modalidade (b) do ONR, É o canal. Estar na pasta ainda não
    é estar no Bucket: isso é o CSL2 que faz, e o relatório diz se ele existe.
    """
    destino = Path(destino)
    medida = imagens_pendentes(con, destino, somente=somente)
    convertidas = paginas = 0
    problemas = list(medida["problemas"])
    if baixar_marca and medida["so_baixar"]:
        _baixar_marca(con, medida["so_baixar"])
    if medida["problemas"]:
        with _trava_da_pasta(destino):
            for x in medida["problemas"]:
                _marcar_situacao(destino, x["numero"], {"situacao": "ERRO",
                                                        "motivo": x["motivo"], "em": _agora()})
    fila = medida["pendentes"][:limite] if limite else medida["pendentes"]
    for p in fila:
        num = p["numero"]
        # A TRAVA É POR MATRÍCULA, e não pela rodada inteira: a rodada leva
        # minutos, e o balcão que acabou de enviar uma varredura esperaria por
        # ela. Assim cada um espera, no máximo, a conversão de UMA ficha.
        with _trava_da_pasta(destino):
            try:
                n = _converter_uma(Path(p["caminho"]), destino, num)
            except Exception as erro:                   # noqa: BLE001
                motivo = (f"arquivo da digitalização não encontrado ({p['caminho']})"
                          if isinstance(erro, FileNotFoundError)
                          else f"{type(erro).__name__}: {erro}")
                problemas.append({"numero": num, "matricula_id": p["matricula_id"],
                                  "motivo": motivo})
                _marcar_situacao(destino, num, {"situacao": "ERRO", "sha": p["sha"],
                                                "motivo": motivo, "em": _agora()})
                continue
            _juntar_ao_controle(destino, {str(num): {
                "sha": p["sha"], "paginas": n, "matricula_id": p["matricula_id"],
                "em": _agora()}})
            _marcar_situacao(destino, num, None)
        convertidas += 1
        paginas += n
        if baixar_marca:
            _baixar_marca(con, p["ids"])
        if convertidas % 50 == 0 and escrever:
            escrever(f"    … {convertidas} matrículas, {paginas} páginas")
    destino.mkdir(parents=True, exist_ok=True)
    if somente is None:
        # O arquivo de problemas é o retrato da RODADA; a conversão de uma ficha
        # só não pode apagá-lo com a lista curta dela.
        # A pasta do controle nasce aqui quando nada se converteu — antes ela
        # nascia do controle regravado inteiro, que deixou de existir.
        caminho_do_controle(destino).parent.mkdir(parents=True, exist_ok=True)
        (caminho_do_controle(destino).parent / "_problemas.txt").write_text(
            "\n".join(f"{x['numero']}: {x['motivo']}" for x in problemas) + "\n",
            encoding="utf-8")
    if baixar_marca:
        con.commit()
    return {"convertidas": convertidas, "paginas": paginas,
            "restam": max(0, len(medida["pendentes"]) - len(fila)),
            # Contava as ELEGÍVEIS mesmo sem baixar nada — em 10/10/2026 disse
            # «2.800 baixadas» numa conversão em que nenhuma marca mudou.
            "marcas_baixadas": len(medida["so_baixar"]) if baixar_marca else 0,
            "problemas": problemas}


# ============================================== 1b. NA HORA DO ENVIO, PELO BALCÃO
#
#     «nao existe outra forma que o sistema processe e crie a copia em tiff?»
#                                                       — o oficial, 10/10/2026
#
# O balcão sobe a varredura em PDF (é o que o certificado da casa e a certidão
# por reprodução pedem), e o ONR quer TIFF. Até aqui a cópia só nascia na rodada
# das 07:30 — no máximo um dia de atraso, e 150 fichas por manhã. Agora ela nasce
# LOGO DEPOIS do envio, numa linha à parte do servidor: o escrevente não espera
# a conversão, e a ficha diz em que pé ela está. A rodada das 07:30 continua de
# pé, como rede de segurança: o que falhar aqui ela refaz, porque o critério é o
# mesmo (o sha da digitalização contra o controle da pasta).
#
# O PDF DO BALCÃO NÃO É TOCADO: a cópia é outra coisa, noutra pasta.

#: Uma conversão por vez dentro do servidor — e é o que torna o pymupdf seguro:
#: ele não é feito para duas linhas mexendo ao mesmo tempo.
_UMA_DE_CADA_VEZ = threading.Lock()

#: «Convertendo» mais velho que isto é sobra de servidor que caiu no meio.
CONVERTENDO_VELHO_SEGUNDOS = TRAVA_VELHA_SEGUNDOS


def _numero_da_matricula(con, matricula_id: int) -> int | None:
    r = con.execute("SELECT numero FROM ri_matriculas WHERE id=?",
                    (int(matricula_id),)).fetchone()
    if r is None:
        raise ValueError("Matrícula não encontrada.")
    return _numero(r[0])


def converter_matricula(con, matricula_id: int, banco: Path | None = None) -> dict:
    """Põe agora na pasta do CSL2 a digitalização de UMA matrícula. ESCREVE.

    É `exportar_imagens` com o recorte de uma ficha — e não uma segunda
    conversão: duas casas para o formato do ONR divergiriam no primeiro conserto.
    """
    num = _numero_da_matricula(con, matricula_id)
    if num is None or num >= NUMERO_DE_FICHA_ARQUIVADA:
        return {"convertidas": 0, "fora": True, "problemas": []}
    return exportar_imagens(con, pastas(con, banco)["csl2"], limite=None, somente={str(num)},
                            baixar_marca=csl2_em_uso(con))


def converter_em_segundo_plano(db, matricula_id: int):
    """Começa a conversão numa linha à parte e volta NA HORA. NUNCA ESTOURA.

    A digitalização já está gravada quando isto é chamado; a cópia ao ONR é
    consequência dela. Um erro aqui não pode virar erro na tela de quem enviou —
    ele fica na situação da matrícula, que a ficha mostra, e a rodada das 07:30
    tenta de novo. Devolve a linha (os testes esperam por ela) ou `None`.
    """
    banco = Path(db.db_path)
    try:
        with closing(db.connect()) as con:
            num = _numero_da_matricula(con, matricula_id)
            if num is None or num >= NUMERO_DE_FICHA_ARQUIVADA:
                return None
            destino = pastas(con, banco)["csl2"]
        with _trava_da_pasta(destino):
            _marcar_situacao(destino, num, {"situacao": "CONVERTENDO", "em": _agora()})
    except Exception:                                   # noqa: BLE001
        return None

    def trabalhar():
        with _UMA_DE_CADA_VEZ:
            try:
                with closing(db.connect()) as con:
                    r = converter_matricula(con, matricula_id, banco)
                    con.commit()
                if not r.get("convertidas") and not r.get("problemas"):
                    # Nada a converter (já estava na pasta com o mesmo sha):
                    # o «convertendo» que marcamos acima não pode ficar.
                    with _trava_da_pasta(destino):
                        _marcar_situacao(destino, num, None)
            except Exception as erro:                   # noqa: BLE001
                try:
                    with _trava_da_pasta(destino):
                        _marcar_situacao(destino, num, {
                            "situacao": "ERRO", "em": _agora(),
                            "motivo": f"{type(erro).__name__}: {erro}"})
                except Exception:                       # noqa: BLE001
                    pass

    linha = threading.Thread(target=trabalhar, name=f"onr-imagem-{int(matricula_id)}",
                             daemon=True)
    linha.start()
    return linha


def situacao_da_imagem(con, matricula_id: int, banco: Path | None = None) -> dict:
    """Em que pé está a cópia desta matrícula para o ONR. SÓ LÊ.

    `estado`: SEM_DIGITALIZACAO · FORA (ficha arquivada) · NA_PASTA ·
    CONVERTENDO · ERRO · AGUARDANDO. O que manda é o CONTROLE: se o sha de hoje
    está nele, a imagem está na pasta, diga a situação o que disser.
    """
    r = con.execute("SELECT numero, digi_path, digi_sha256, digi_onr_pendente "
                    "FROM ri_matriculas WHERE id=?", (int(matricula_id),)).fetchone()
    if r is None or not (r[1] or "").strip():
        return {"estado": "SEM_DIGITALIZACAO"}
    num = _numero(r[0])
    if num is None or num >= NUMERO_DE_FICHA_ARQUIVADA:
        return {"estado": "FORA"}
    destino = pastas(con, banco)["csl2"]
    base = {"numero": num, "pasta": str(destino), "csl2_em_uso": csl2_em_uso(con),
            "marca_pendente": bool(r[3])}
    linha = ler_controle(destino).get(str(num)) or {}
    if r[2] and linha.get("sha") == r[2]:
        return {**base, "estado": "NA_PASTA", "paginas": linha.get("paginas"),
                "em": linha.get("em")}
    s = ler_situacao(destino).get(str(num)) or {}
    if s.get("situacao") == "CONVERTENDO":
        try:
            idade = (datetime.now() - datetime.fromisoformat(s["em"])).total_seconds()
        except (KeyError, ValueError):
            idade = CONVERTENDO_VELHO_SEGUNDOS + 1
        if idade <= CONVERTENDO_VELHO_SEGUNDOS:
            return {**base, "estado": "CONVERTENDO", "em": s.get("em")}
    if s.get("situacao") == "ERRO" and s.get("sha") in (None, r[2]):
        return {**base, "estado": "ERRO", "motivo": s.get("motivo"), "em": s.get("em")}
    return {**base, "estado": "AGUARDANDO"}


# ======================================================= 2. INDICADOR PESSOAL
#
# A DATA DE CADA ATO, e não a de abertura: as partes tiradas do teor (13 mil em
# 06/10/2026) não têm ato_id, e com `COALESCE(data_ato, data_abertura)` quem
# comprou em 2010 sairia dono desde 1978. A data e a natureza estão na
# `qualificacao` («R-2 · 12/03/2010 · compra e venda»). Era a lógica de
# `FERRAMENTAS\gerar_indicador_pessoal_onr.py`, que passou a chamar esta.

RE_QUAL = re.compile(
    r"^\s*([A-Z]{1,3}[-.\s]?\d+|ABERTURA)\s*·\s*(\d{2})/(\d{2})/(\d{4})\s*·\s*([^·]*)", re.I)


def vinculos(con, *, desde: str | None = None) -> list[dict]:
    """Os vínculos pessoa × matrícula do Indicador Pessoal. SÓ LÊ.

    Com `desde` (data-hora ISO), o INCREMENTAL: as partes de ato lavrado por
    este sistema depois dela, e as das matrículas abertas depois dela. **O que
    entra por importação de acervo (partes do teor) não aparece no incremental**
    — não tem data de lançamento —, e vai na carga completa.
    """
    sql = """SELECT p.nome, p.documento_numero AS documento, m.numero AS matricula,
                    p.origem, p.qualificacao, a.natureza_titulo, a.tipo, a.data_ato,
                    m.data_abertura
               FROM ri_partes p JOIN ri_matriculas m ON m.id = p.matricula_id
               LEFT JOIN ri_atos a ON a.id = p.ato_id
              WHERE TRIM(COALESCE(p.nome,'')) <> ''"""
    args: tuple = ()
    if desde:
        sql += """ AND ((a.id IS NOT NULL AND COALESCE(a.acervo,0) = 0
                         AND a.lavrado_em >= ?)
                     OR (p.ato_id IS NULL AND m.criado_em >= ?))"""
        args = (desde, desde)
    sql += " ORDER BY m.numero, p.nome"
    saida = []
    for r in con.execute(sql, args):
        num = _numero(r[2])
        if num is not None and num >= NUMERO_DE_FICHA_ARQUIVADA:
            continue
        nat, tipo_ato, data = r[5], r[6], r[7]
        tipo = nat or "MATRICULA"
        if not data:
            m = RE_QUAL.match(r[4] or "") if r[3] == "TEOR_TRANSCRICAO" else None
            if m:
                ato, d, mes, ano, natureza = m.groups()
                data = f"{ano}-{mes}-{d}"
                natureza = natureza.strip().upper()
                tipo = ("MATRICULA" if ato.upper() == "ABERTURA" or not natureza
                        or natureza == "ABERTURA" else natureza)
            else:
                data = r[8]
        saida.append({"nome": r[0], "documento": r[1],
                      "matricula": str(num) if num is not None else r[2],
                      "tipo_ato": (tipo or "MATRICULA")[:60], "data_ato": data,
                      "data_venda": data})
    # A ordem é a numérica da matrícula, como a ferramenta de 06/10 gerava
    # (CAST no SQL); ordenar aqui deixa o SQL sem conversão e o arquivo igual.
    saida.sort(key=lambda v: (_numero(v["matricula"]) or 0, v["nome"] or ""))
    return saida


def xml_do_pessoal(con, lista: list[dict]) -> str:
    import ri_onr
    return ri_onr.gerar_indicador_pessoal(lista, _cns(con))


def _arquivos_do_ips(pasta: Path) -> dict[str, tuple[Path, str]]:
    """sha256 -> (arquivo, onde) dos XML da pasta do IPS e de `Processados`."""
    achados: dict[str, tuple[Path, str]] = {}
    for onde, raiz in (("PROCESSADO", pasta / "Processados"), ("NA_PASTA", pasta)):
        if not raiz.is_dir():
            continue
        for f in raiz.glob("*.XML"):
            try:
                achados.setdefault(_sha_arquivo(f), (f, onde))
            except OSError:
                continue
    return achados


def _conferir_o_ips(con, pasta_ips: Path) -> int:
    """Marca PROCESSADO o arquivo nosso que o IPS levou (achado pelo sha)."""
    abertos = con.execute(
        "SELECT id, sha256 FROM ge_onr_cargas WHERE canal=? AND sha256 IS NOT NULL "
        "AND situacao IN ('PREPARADO','NA_PASTA')", (CANAL_PESSOAL,)).fetchall()
    if not abertos:
        return 0
    no_disco = _arquivos_do_ips(pasta_ips)
    mudou = 0
    for rid, sha in abertos:
        if sha in no_disco:
            arq, onde = no_disco[sha]
            quando = datetime.fromtimestamp(arq.stat().st_mtime).replace(
                microsecond=0).isoformat()
            con.execute("UPDATE ge_onr_cargas SET situacao=?, processado_em=? WHERE id=?",
                        (onde, quando if onde == "PROCESSADO" else None, rid))
            mudou += 1
    return mudou


def _completa_levada(con):
    if not _tem_tabela(con, "ge_onr_cargas"):
        return None
    return con.execute(
        "SELECT * FROM ge_onr_cargas WHERE canal=? AND tipo='COMPLETA' "
        "AND situacao='PROCESSADO' ORDER BY id DESC LIMIT 1", (CANAL_PESSOAL,)).fetchone()


def cuidar_do_pessoal(con, hoje: date, banco: Path | None = None) -> dict:
    """Mantém o Indicador Pessoal em dia. Grava arquivo e o livro de cargas."""
    p = pastas(con, banco)
    levados = _conferir_o_ips(con, p["ips"])
    agora = _agora()
    if _completa_levada(con) is None:
        # ANTES DA ADESÃO: a carga completa fica pronta, e só se regrava quando muda.
        lista = vinculos(con)
        xml = xml_do_pessoal(con, lista)
        sha = _sha_texto(xml)
        ultima = con.execute(
            "SELECT id, sha256, arquivo FROM ge_onr_cargas WHERE canal=? AND tipo='COMPLETA' "
            "AND situacao IN ('PREPARADO','NA_PASTA') ORDER BY id DESC LIMIT 1",
            (CANAL_PESSOAL,)).fetchone()
        if ultima and ultima["sha256"] == sha:
            con.commit()
            return {"fase": "CARGA_INICIAL", "acao": "sem mudança", "vinculos": len(lista),
                    "levados": levados}
        pasta = p["carga_inicial"]
        pasta.mkdir(parents=True, exist_ok=True)
        arq = pasta / f"IndicadorPessoal_CARGA_COMPLETA_{hoje.isoformat()}.XML"
        arq.write_bytes(xml.encode("utf-8"))
        for velho in con.execute(
                "SELECT id, arquivo FROM ge_onr_cargas WHERE canal=? AND tipo='COMPLETA' "
                "AND situacao='PREPARADO'", (CANAL_PESSOAL,)).fetchall():
            v = Path(velho["arquivo"] or "")
            if v.parent == pasta and v != arq and v.exists():
                v.unlink()
            con.execute("UPDATE ge_onr_cargas SET situacao='SUBSTITUIDO' WHERE id=?",
                        (velho["id"],))
        sem_doc = sum(1 for v in lista
                      if len(re.sub(r"\D", "", v["documento"] or "")) not in (11, 14))
        _registrar(con, CANAL_PESSOAL, "COMPLETA", situacao="PREPARADO", arquivo=str(arq),
                   sha256=sha, quantos=len(lista), periodo_de="1976-01-01",
                   periodo_ate=agora, detalhe={"sem_documento": sem_doc})
        con.commit()
        return {"fase": "CARGA_INICIAL", "acao": "carga completa regravada",
                "arquivo": str(arq), "vinculos": len(lista), "levados": levados}
    # DEPOIS DA ADESÃO: o incremental do que se lavrou desde o último arquivo.
    desde = con.execute(
        "SELECT MAX(periodo_ate) FROM ge_onr_cargas WHERE canal=? "
        "AND situacao IN ('PROCESSADO','NA_PASTA')", (CANAL_PESSOAL,)).fetchone()[0]
    lista = vinculos(con, desde=desde)
    if not lista:
        con.commit()
        return {"fase": "INCREMENTAL", "acao": "nada novo", "desde": desde,
                "levados": levados}
    if not p["ips"].is_dir():
        con.commit()
        return {"fase": "INCREMENTAL", "acao": "pasta do IPS não existe",
                "pasta": str(p["ips"]), "vinculos": len(lista), "levados": levados}
    import ri_onr
    inicio = date.fromisoformat(desde[:10])
    arq = p["ips"] / ri_onr.nome_arquivo("PESSOAL", inicio, hoje)
    if arq.exists():
        arq = arq.with_name(arq.stem + f"_{datetime.now():%H%M%S}" + arq.suffix)
    xml = xml_do_pessoal(con, lista)
    arq.write_bytes(xml.encode("utf-8"))
    _registrar(con, CANAL_PESSOAL, "INCREMENTAL", situacao="NA_PASTA", arquivo=str(arq),
               sha256=_sha_texto(xml), quantos=len(lista), periodo_de=desde,
               periodo_ate=agora)
    con.commit()
    return {"fase": "INCREMENTAL", "acao": "arquivo gerado", "arquivo": str(arq),
            "vinculos": len(lista), "levados": levados}


# ========================================================= 3. INDICADOR REAL

class _Banco:
    """O `db` que `ri_onr_central` pede (connect + transaction), sobre um caminho.

    Não é `database.Database` de propósito: aquele roda o esquema inteiro ao
    nascer, e o agente só fala com o ONR.
    """

    def __init__(self, caminho: Path):
        self.caminho = Path(caminho)

    def connect(self) -> sqlite3.Connection:
        c = sqlite3.connect(str(self.caminho), timeout=60)
        c.row_factory = sqlite3.Row
        return c

    @contextmanager
    def transaction(self):
        c = self.connect()
        try:
            c.execute("BEGIN IMMEDIATE")
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise
        finally:
            c.close()


def _ultimos_envios(con) -> list[dict]:
    """O envio mais novo de cada matrícula, no ambiente da casa."""
    import ri_onr_central as ONR
    import ri_onr_central_schema as ESQ
    if not _tem_tabela(con, "ri_onr_envios"):
        return []
    return [dict(r) for r in con.execute(
        """SELECT e.*, m.numero FROM ri_onr_envios e
             JOIN ri_matriculas m ON m.id = e.matricula_id
            WHERE e.especie = ? AND e.ambiente = ?
              AND e.id = (SELECT MAX(x.id) FROM ri_onr_envios x
                           WHERE x.matricula_id = e.matricula_id
                             AND x.especie = e.especie AND x.ambiente = e.ambiente)""",
        (ESQ.INDICADOR, ONR.ambiente()))]


def indicadores_pendentes(con) -> dict:
    """O que o ONR ainda não tem como está no livro. SÓ LÊ (monta, não manda).

    `novos`: matrícula desta casa sem indicador aceito ou em andamento.
    `mudaram`: subiu, e o corpo de hoje já não é o que subiu (ato novo, dono
    novo, endereço corrigido) — vai pelo PATCH.
    `incompletos`: não sobe — e o `impedem` diz por quê.
    `recusados`: o ONR recusou e nada mudou desde então: reenviar daria a mesma
    recusa.
    """
    import ri_onr_central as ONR
    import ri_onr_central_schema as ESQ
    if not _tem_tabela(con, "ri_onr_envios"):
        ESQ.init_ri_onr_central_schema(con)
    cns = _cns(con)
    ultimos = {e["matricula_id"]: e for e in _ultimos_envios(con)}
    novos, mudaram, incompletos, recusados, parados = [], [], [], [], []

    def montar(mid):
        try:
            return ONR.montar_indicador(con, mid, cns=cns)
        except Exception as erro:                      # noqa: BLE001
            return {"impedem": [f"{type(erro).__name__}: {erro}"], "corpo": None}

    for m in ONR.a_enviar(con, limite=100000):
        mid = int(m["id"])
        num = _numero(m["numero"])
        if num is not None and num >= NUMERO_DE_FICHA_ARQUIVADA:
            continue
        montado = montar(mid)
        anterior = ultimos.get(mid)
        if montado["impedem"]:
            incompletos.append({"matricula_id": mid, "numero": m["numero"],
                                "impedem": montado["impedem"]})
        elif anterior and anterior["situacao"] == ESQ.RECUSADO \
                and anterior["corpo_hash"] == ONR._hash(montado["corpo"]):
            recusados.append(anterior)
        else:
            novos.append({"matricula_id": mid, "numero": m["numero"]})
    hoje = date.today()
    for mid, e in ultimos.items():
        if e["situacao"] not in (ESQ.ENVIADO, ESQ.ACEITO):
            continue
        if e["situacao"] == ESQ.ENVIADO and (e["enviado_em"] or "") < (
                hoje - timedelta(days=FILA_DIAS_TOLERADOS)).isoformat():
            parados.append(e)
        montado = montar(mid)
        if montado["impedem"]:
            if montado["corpo"] is not None:
                incompletos.append({"matricula_id": mid, "numero": e["numero"],
                                    "impedem": montado["impedem"], "ja_subiu": True})
            continue
        if ONR._hash(montado["corpo"]) != e["corpo_hash"]:
            mudaram.append({"matricula_id": mid, "numero": e["numero"], "envio_id": e["id"]})
    return {"novos": novos, "mudaram": mudaram, "incompletos": incompletos,
            "recusados": recusados, "parados": parados}


def cuidar_do_real(con, banco: Path, *, pasta_cred=None) -> dict:
    """Confere a fila, manda o novo e corrige o que mudou. Rede fora de transação."""
    import onr_api as API
    import ri_onr_central as ONR
    import ri_onr_central_schema as ESQ
    ESQ.init_ri_onr_central_schema(con)
    con.commit()
    saida: dict[str, Any] = {"ambiente": ONR.ambiente(), "enviados": 0, "atualizados": 0,
                             "erros": [], "fila": None}
    if not envio_ligado(con):
        saida["parado"] = "envio desligado nas configurações"
        return saida
    if not API.tem_credencial(pasta=pasta_cred):
        saida["parado"] = f"sem credencial do ONR ({ONR.ambiente()})"
        return saida
    db = _Banco(banco)
    agora = _agora()
    if con.execute("SELECT 1 FROM ri_onr_envios WHERE situacao=? AND ambiente=?",
                   (ESQ.ENVIADO, ONR.ambiente())).fetchone():
        try:
            saida["fila"] = ONR.conferir_a_fila(db, agora=agora, pasta=pasta_cred)
        except Exception as erro:                      # noqa: BLE001
            saida["erros"].append({"onde": "fila", "erro": f"{type(erro).__name__}: {erro}"})
    pend = indicadores_pendentes(con)
    con.commit()          # nenhuma transação aberta daqui enquanto a rede fala
    cns = _cns(con)
    feitos = 0
    for item in pend["mudaram"]:
        if feitos >= TETO_INDICADORES_POR_RODADA:
            break
        try:
            ONR.atualizar_indicador(db, item["envio_id"], cns=cns, agora=agora,
                                    usuario=QUEM, pasta=pasta_cred)
            saida["atualizados"] += 1
        except Exception as erro:                      # noqa: BLE001
            saida["erros"].append({"matricula": item["numero"], "onde": "atualizar",
                                   "erro": f"{type(erro).__name__}: {erro}"})
        feitos += 1
    for item in pend["novos"]:
        if feitos >= TETO_INDICADORES_POR_RODADA:
            break
        try:
            ONR.enviar_indicador(db, item["matricula_id"], cns=cns, agora=agora,
                                 usuario=QUEM, pasta=pasta_cred)
            saida["enviados"] += 1
        except Exception as erro:                      # noqa: BLE001
            saida["erros"].append({"matricula": item["numero"], "onde": "enviar",
                                   "erro": f"{type(erro).__name__}: {erro}"})
        feitos += 1
    saida["restam"] = max(0, len(pend["novos"]) + len(pend["mudaram"]) - feitos)
    return saida


def acervo_sem_indicador(con) -> dict:
    """Os números da decisão sobre o Indicador Real do acervo. SÓ LÊ."""
    total = con.execute(
        "SELECT COUNT(*) FROM ri_matriculas WHERE tipo_ficha='ACERVO' "
        "AND COALESCE(encerrada,0)=0").fetchone()[0]
    ids = {r[0] for r in con.execute(
        "SELECT id, numero FROM ri_matriculas WHERE tipo_ficha='ACERVO' "
        "AND COALESCE(encerrada,0)=0") if (_numero(r[1]) or 0) < NUMERO_DE_FICHA_ARQUIVADA}
    com_ato_novo = {r[0] for r in con.execute(
        "SELECT DISTINCT a.matricula_id FROM ri_atos a JOIN ri_matriculas m "
        "ON m.id = a.matricula_id WHERE m.tipo_ficha='ACERVO' AND COALESCE(a.acervo,0)=0 "
        "AND a.lavrado_em >= ?", ("2026-09-10",))}
    return {"ativas": len(ids), "registradas": total,
            "com_ato_desta_casa_desde_10_09": len(com_ato_novo & ids),
            "precedente_eoficio": 3}


# ================================================================ A RODADA

def rodada(con: sqlite3.Connection, banco: Path, hoje: date | None = None, *,
           imagens: bool = True, escrever=print, pasta_cred=None) -> dict:
    """A rodada do agente: imagens, Indicador Pessoal e Indicador Real.

    Cada canal tem o seu `try`: um que quebra não segura os outros, e a quebra
    fica gravada no livro de cargas — é ela que a conferência lê depois.
    """
    import traceback
    hoje = hoje or date.today()
    con.row_factory = sqlite3.Row
    init_gestor_schema(con)
    con.commit()
    resumo: dict[str, Any] = {}
    canais = []
    if imagens:
        canais.append((CANAL_IMAGENS, lambda: exportar_imagens(
            con, pastas(con, banco)["csl2"], escrever=escrever,
            baixar_marca=csl2_em_uso(con))))
    canais += [(CANAL_PESSOAL, lambda: cuidar_do_pessoal(con, hoje, banco)),
               (CANAL_REAL, lambda: cuidar_do_real(con, banco, pasta_cred=pasta_cred))]
    for canal, fazer in canais:
        try:
            r = fazer()
            resumo[canal] = r
            _registrar(con, canal, "RODADA", situacao="OK", detalhe=r)
        except Exception as erro:                      # noqa: BLE001
            con.rollback()
            resumo[canal] = {"erro": f"{type(erro).__name__}: {erro}"}
            _registrar(con, canal, "RODADA", situacao="ERRO",
                       detalhe={"erro": resumo[canal]["erro"],
                                "rastro": traceback.format_exc()[-2000:]})
        con.commit()
        escrever(f"  cargas ONR — {canal}: {_curto(resumo[canal])}")
    return resumo


def _curto(r: dict) -> str:
    r = dict(r)
    if isinstance(r.get("problemas"), list):
        r["problemas"] = len(r["problemas"])
    if isinstance(r.get("erros"), list):
        r["erros"] = len(r["erros"])
    return json.dumps(r, ensure_ascii=False)[:400]


# ============================================================ A CONFERÊNCIA

def _achado(chave, regra, gravidade, setor, titulo, detalhe="", prazo=None) -> dict:
    return {"chave": chave, "regra": regra, "gravidade": gravidade, "setor": setor,
            "titulo": titulo, "detalhe": detalhe,
            "prazo": prazo.isoformat() if isinstance(prazo, date) else prazo,
            "fundamento": FUNDAMENTO}


def _ultima_rodada(con, canal: str):
    return con.execute(
        "SELECT * FROM ge_onr_cargas WHERE canal=? AND tipo='RODADA' "
        "ORDER BY id DESC LIMIT 1", (canal,)).fetchone()


def conferir(con: sqlite3.Connection, hoje: date, *, pasta_cred=None) -> list[dict]:
    """O que está fora do dia nas três cargas. SÓ LÊ (fora as tabelas que nascem)."""
    import onr_api as API
    import ri_onr_central as ONR
    con.row_factory = sqlite3.Row
    init_gestor_schema(con)
    achados: list[dict] = []

    # O AGENTE RODOU? Sem rodada recente, tudo o que segue mede o que ninguém cuidou.
    for canal in (CANAL_IMAGENS, CANAL_PESSOAL, CANAL_REAL):
        r = _ultima_rodada(con, canal)
        if r is None or (r["gerado_em"] or "")[:10] < (
                hoje - timedelta(days=AGENTE_DIAS_TOLERADOS)).isoformat():
            achados.append(_achado(
                f"ONR_AGENTE:{canal}", "ONR_AGENTE_PARADO", "CRITICO", "TI",
                f"O agente de cargas não rodou o canal {canal} desde "
                f"{(r['gerado_em'] or '')[:10] if r else 'nunca'}",
                "A rodada das 07:30 chama gestor_cargas_ri.rodada; veja o "
                "CONFERENCIA_DIARIA.log."))
        elif r["situacao"] == "ERRO":
            erro = (json.loads(r["detalhe"] or "{}") or {}).get("erro", "")
            achados.append(_achado(
                f"ONR_AGENTE:{canal}", "ONR_AGENTE_PARADO", "CRITICO", "TI",
                f"O agente de cargas quebrou no canal {canal}", erro))

    # INDICADOR REAL
    tem_cred = API.tem_credencial(pasta=pasta_cred)
    pend = indicadores_pendentes(con)
    esperando = len(pend["novos"]) + len(pend["mudaram"])
    if not tem_cred:
        achados.append(_achado(
            "ONR_CREDENCIAL", "ONR_CREDENCIAL", "ATENCAO", "GESTAO",
            "Indicador Real parado: falta a credencial do ONR (client_id/secret)",
            f"{esperando} matrícula(s) desta casa esperando subir; ambiente "
            f"{ONR.ambiente()}. Quem digita a credencial é o oficial, na tela de "
            "credenciais das Centrais."))
    if not envio_ligado(con):
        achados.append(_achado(
            "ONR_ENVIO_DESLIGADO", "ONR_ENVIO_DESLIGADO", "ATENCAO", "GESTAO",
            "O envio automático do Indicador Real está desligado",
            f"Configuração «{CHAVE_ENVIO}» = DESLIGADO; {esperando} esperando."))
    for i in pend["incompletos"]:
        achados.append(_achado(
            f"ONR_IR:{i['matricula_id']}", "ONR_INDICADOR_INCOMPLETO", "ATENCAO", "RI",
            f"Matrícula {i['numero']}: o Indicador Real não sobe"
            + (" (a versão que subiu ficou velha)" if i.get("ja_subiu") else ""),
            " · ".join(i["impedem"])))
    for e in pend["recusados"]:
        achados.append(_achado(
            f"ONR_RECUSA:{e['id']}", "ONR_INDICADOR_RECUSADO", "CRITICO", "RI",
            f"Matrícula {e['numero']}: o ONR recusou o Indicador Real",
            f"Fila: {e.get('fila_situacao') or '—'}. O motivo está em "
            f"/ri/onr/envio/{e['id']}/porque; corrija a ficha e o agente reenvia."))
    for e in pend["parados"]:
        achados.append(_achado(
            f"ONR_FILA:{e['id']}", "ONR_FILA_PARADA", "ATENCAO", "RI",
            f"Matrícula {e['numero']}: enviada em {(e['enviado_em'] or '')[:10]} e "
            "ainda sem resposta da fila do ONR",
            f"Mais de {FILA_DIAS_TOLERADOS} dias ENVIADO, sem ACEITO nem RECUSADO."))
    real = _ultima_rodada(con, CANAL_REAL)
    if real is not None and real["situacao"] == "OK":
        for e in (json.loads(real["detalhe"] or "{}") or {}).get("erros", []):
            achados.append(_achado(
                f"ONR_ENVIO:{e.get('matricula') or e.get('onde')}", "ONR_ENVIO_FALHOU",
                "ATENCAO", "RI",
                f"Indicador Real da matrícula {e.get('matricula') or '—'}: o "
                f"{e.get('onde')} falhou", e.get("erro", "")))
    acervo = acervo_sem_indicador(con)
    enviados_acervo = con.execute(
        "SELECT COUNT(DISTINCT e.matricula_id) FROM ri_onr_envios e JOIN ri_matriculas m "
        "ON m.id = e.matricula_id WHERE m.tipo_ficha='ACERVO'").fetchone()[0] \
        if _tem_tabela(con, "ri_onr_envios") else 0
    if acervo["ativas"] and not enviados_acervo:
        achados.append(_achado(
            "ONR_ACERVO", "ONR_ACERVO_DECISAO", "ATENCAO", "GESTAO",
            f"O Indicador Real das {acervo['ativas']} fichas ativas do acervo nunca subiu",
            f"O E-Ofício deixou um único arquivo de indicador real, com "
            f"{acervo['precedente_eoficio']} matrículas. {acervo['com_ato_desta_casa_desde_10_09']}"
            " delas já receberam ato desta casa desde 10/09. Decisão do oficial: subir o "
            "acervo (todo, ou só o que recebe ato novo) ou mantê-lo fora."))

    # INDICADOR PESSOAL
    if _completa_levada(con) is None:
        prep = con.execute(
            "SELECT arquivo, quantos, detalhe FROM ge_onr_cargas WHERE canal=? "
            "AND tipo='COMPLETA' AND situacao IN ('PREPARADO','NA_PASTA') "
            "ORDER BY id DESC LIMIT 1", (CANAL_PESSOAL,)).fetchone()
        if prep:
            sem = (json.loads(prep["detalhe"] or "{}") or {}).get("sem_documento")
            achados.append(_achado(
                "ONR_CARGA_INICIAL", "ONR_CARGA_INICIAL", "ATENCAO", "GESTAO",
                "Indicador Pessoal: a carga completa está pronta e espera a adesão ao ONR",
                f"{prep['quantos']} vínculo(s), {sem} sem CPF/CNPJ; arquivo {prep['arquivo']}. "
                "Ela é regravada sozinha quando o livro muda; no dia da instalação do IPS, "
                "é ela que vai."
                + ("" if csl2_em_uso(con) else
                   " As imagens já vão para a pasta do CSL2; no dia em que ele for "
                   f"instalado, informe a data em «{CHAVE_CSL2_DESDE}» para a marca de "
                   "pendência baixar.")))
    limite = (hoje - timedelta(days=IPS_DIAS_TOLERADOS)).isoformat()
    for r in con.execute(
            "SELECT id, arquivo, gerado_em FROM ge_onr_cargas WHERE canal=? "
            "AND tipo='INCREMENTAL' AND situacao='NA_PASTA' AND gerado_em < ?",
            (CANAL_PESSOAL, limite)):
        achados.append(_achado(
            f"ONR_IPS:{r['id']}", "ONR_IPS_NAO_LEVOU", "ATENCAO", "RI",
            f"O IPS não levou o Indicador Pessoal gerado em {r['gerado_em'][:10]}",
            f"{Path(r['arquivo']).name} continua na pasta, fora de Processados. Confira se "
            "o programa IPS está rodando e veja o e-mail de ocorrências do ONR."))

    # IMAGENS
    p = pastas(con)
    if not p["csl2"].is_dir():
        achados.append(_achado(
            "ONR_PASTA:CSL2", "ONR_PASTA", "CRITICO", "TI",
            f"A pasta das imagens do ONR não existe: {p['csl2']}"))
    else:
        for x in imagens_pendentes(con, p["csl2"])["problemas"]:
            achados.append(_achado(
                f"ONR_IMG:{x['numero']}", "ONR_IMAGEM_PROBLEMA", "ATENCAO", "RI",
                f"Matrícula {x['numero']}: a imagem não foi para a pasta do ONR",
                x["motivo"]))
        problemas = caminho_do_controle(p["csl2"]).parent / "_problemas.txt"
        if problemas.exists():
            vistos = {a["chave"] for a in achados}
            for linha in problemas.read_text(encoding="utf-8").splitlines():
                num, _, motivo = linha.partition(":")
                if num.strip().isdigit() and f"ONR_IMG:{num.strip()}" not in vistos:
                    achados.append(_achado(
                        f"ONR_IMG:{num.strip()}", "ONR_IMAGEM_PROBLEMA", "ATENCAO", "RI",
                        f"Matrícula {num.strip()}: a imagem não foi para a pasta do ONR",
                        motivo.strip()))
    return achados


# ================================================================ o painel

def painel(con: sqlite3.Connection) -> dict:
    """Os números das três cargas, para o relatório. SÓ LÊ."""
    p = pastas(con)
    img = imagens_pendentes(con, p["csl2"]) if p["csl2"].is_dir() else None
    real = indicadores_pendentes(con)
    return {
        "imagens": {"na_pasta": img["na_pasta"] if img else 0,
                    "pendentes": len(img["pendentes"]) if img else None,
                    "problemas": len(img["problemas"]) if img else None},
        "pessoal": dict(_completa_levada(con) or {}) or {"fase": "CARGA_INICIAL"},
        "real": {k: len(v) for k, v in real.items()},
        "acervo": acervo_sem_indicador(con),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="O agente de cargas do RI ao ONR.")
    ap.add_argument("--banco", required=True)
    ap.add_argument("--hoje", default=date.today().isoformat())
    ap.add_argument("--so-medir", action="store_true",
                    help="não grava nem manda nada: só a conferência e o painel")
    ap.add_argument("--sem-imagens", action="store_true")
    a = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:                                   # noqa: BLE001
        pass
    hoje = date.fromisoformat(a.hoje)
    if a.so_medir:
        con = sqlite3.connect(f"file:{a.banco}?mode=ro", uri=True, timeout=60)
        con.row_factory = sqlite3.Row
        try:
            if not _tem_tabela(con, "ge_onr_cargas"):
                print("(o livro de cargas ainda não existe nesta base: o agente nunca rodou)")
            print(json.dumps(painel(con), ensure_ascii=False, indent=1, default=str))
        finally:
            con.close()
        return 0
    con = sqlite3.connect(a.banco, timeout=60)
    try:
        rodada(con, Path(a.banco), hoje, imagens=not a.sem_imagens)
        for x in conferir(con, hoje):
            print(f"  [{x['gravidade']}] {x['titulo']}")
        con.commit()
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
