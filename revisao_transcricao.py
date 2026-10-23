"""A REVISÃO DAS TRANSCRIÇÕES — a IA confere o texto transcrito do livro antigo
contra a página escaneada (LH11).

    «colocar IA pra revisar as certidões transcritas (principalmente as de
     livros antigos) do RI»                — o oficial, 21/10/2026, ~18h20

ONDE MORA O QUE SE CONFERE (medido no código em 21/10/2026)
    O TEXTO é o teor da ficha, `ri_matriculas.teor`: desde 06/10/2026 o teor de
    3.972 fichas é a transcrição da digitalização («vale a digitalização», ver
    `ri_numeros_do_teor`), e nas outras é o texto que veio do E-Ofício ou do
    Word. Os atos do E-Ofício (`ri_atos.origem = 'EOFICIO'`) que o teor ainda
    não conta entram depois dele — são o que a certidão de inteiro teor
    imprime depois do teor (`ri_numeros_do_teor.atos_fora_do_teor`), e a
    pergunta da revisão é «o papel diz o que o livro diz?».
    A PÁGINA é a digitalização oficial (`ri_matriculas.digi_path`) quando há
    arquivo; sem ela, as páginas do E-Ofício (`ri_imagens`, na `ordem`). As
    duas NÃO se somam — é a régua da conferência da ficha (`ri_conferir_
    ficha`): somar seria comparar o texto com uma mistura de versões.

O QUE A IA DEVOLVE
    A lista de DIVERGÊNCIAS: o trecho, o que o texto diz, o que a página diz,
    e a gravidade. GRAVE é nome de parte, CPF/RG, número de matrícula/registro/
    transcrição, área, medida, confrontação, valor, data, ônus, livro/folha;
    LEVE é grafia, pontuação, abreviatura. Página ilegível ou faltando é AVISO,
    e não divergência. A gravidade da categoria grave é regra do CÓDIGO
    (`CATEGORIAS_GRAVES`): a IA que chamar de «leve» um CPF trocado não decide.
    O modelo é o da revisão prévia (o Opus): comparar letra a letra um
    manuscrito é a tarefa cara, e o modelo barato só entra onde já entra — a
    triagem dos anexos —, que aqui não existe.

A IMAGEM DA PÁGINA VAI AO PROVEDOR — DECISÃO DO OFICIAL, 21/10/2026
    «pode mandar a imagem da página» — para ESTA revisão, e só para ela. A
    página tem nomes e documento não se mascara; sem ela, a revisão não vê o
    que tem de conferir. A decisão fica aqui e na tela de Configurações:
    `settings.revisao_transcricao_manda_imagem` (padrão ligado; o ADMIN
    desliga). Desligada, a imagem não sobe, a revisão confere só o texto contra
    a ficha (o cadastro) — com a máscara da revisão, se ela estiver ligada
    (`revisao_mascara`) — e o resultado DIZ que não viu a página.

O QUE NÃO SE PAGA DUAS VEZES
    O resultado se guarda em `ri_transcricao_revisoes` com o sha256 do texto e
    o das páginas: o mesmo texto com as mesmas páginas devolve a revisão que já
    existe. Mudou uma vírgula do teor, ou a varredura nova entrou, é outra
    revisão — a anterior não viu aquilo.

O QUE ELA NÃO FAZ
    - NÃO CORRIGE O TEXTO. A IA aponta; corrigir é pelo caminho que já existe,
      com auditoria (a conferência da ficha, a averbação de retificação), e o
      teor selado não se altera.
    - NÃO TRAVA A CERTIDÃO QUANDO A IA ESTÁ FORA DO AR, como a revisão prévia:
      o balcão parado é pior que a revisão atrasada. A tela diz que a certidão
      saiu sem revisão. O que trava é a divergência GRAVE não resolvida — a
      emissão pede justificativa escrita (a régua da casa, dez letras), que
      fica gravada em `ri_transcricao_emissoes`.
    - NÃO ESCREVE TEXTO NO LOG NEM NA AUDITORIA: só ids, contagens e a
      gravidade. O texto transcrito e o que a IA leu ficam na tabela da
      revisão, que é onde a correição os procura.
    - NO SANDBOX NÃO EXISTE — a ordem do oficial de 13/10/2026 («nao quero ia
      na sandbox»), pela mesma régua da sugestão de ônus.

FALA COM A REDE só em `executar`, com conexão própria e fora de transação de
escrita (a forma de `revisao_previa.executar`).
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import threading
from datetime import datetime
from html import unescape
from pathlib import Path

import banco_pg
import revisao_previa as RP
import tetos_de_entrada as TETO
from bd_nativo import Banco, banco

PROVEDOR = RP.PROVEDOR
#: O MODELO BOM, O MESMO DA REVISÃO PRÉVIA — ordem do LH11.
MODELO = RP.MODELO
MAXIMO_DE_SAIDA = 6000
MINIMO_DA_JUSTIFICATIVA = RP.MINIMO_DA_JUSTIFICATIVA
#: Leitura que passa disto sem terminar é tratada como falha: o servidor pode
#: ter sido reiniciado no meio, e «lendo» para sempre prenderia a certidão.
MINUTOS_PARA_DESISTIR = 15
#: O texto que vai em cada chamada, com folga para a ficha inteira. O que
#: passar disto não sobe, e a revisão diz que leu só o começo.
LIMITE_DO_TEXTO = 80_000
#: As páginas por chamada são as da leitura dos anexos (`revisao_anexos`),
#: pelo mesmo motivo: a página escaneada vai em até 310 KB de JPEG, e três
#: passariam do limite de envio do transporte.
PAGINAS_POR_PEDIDO = 2
#: O teto de páginas de UMA ficha numa revisão — o dos anexos da revisão
#: prévia. O que passar fica de fora, e a revisão diz quais.
TETO_DE_PAGINAS_POR_FICHA = 40

CHAVE_LIGADA = "revisao_transcricao"
CHAVE_IMAGEM = "revisao_transcricao_manda_imagem"
CHAVE_TETO_PAGINAS = "revisao_transcricao_teto_paginas"
CHAVE_TETO_CUSTO = "revisao_transcricao_teto_custo"
#: Os tetos da RODADA do lote, quando a configuração não diz outro. Uma rodada
#: de 300 páginas são umas 150 chamadas ao Opus: medido com a IA de mentira
#: pelo tamanho real dos pedidos (ver abaixo), perto de US$ 6 — o teto de
#: custo fica acima disso, para segurar a ficha de texto longo e a resposta
#: comprida, e não para racionar a rodada.
TETO_DE_PAGINAS_POR_RODADA = 300
TETO_DE_CUSTO_POR_RODADA = 10.0          # dólares, pela tabela de preço da casa

#: A estimativa ANTES de haver uso medido no `ia_uso` — medida em 21/10/2026
#: com a IA de mentira pelo pedido que `executar` monta: instrução (1.856
#: letras), dossiê de uma ficha de 4 mil letras com o cadastro (4.459) e duas
#: páginas A4 de 200 dpi, que sobem com 989 x 1.400 px (~1.532 tokens cada,
#: pela regra publicada do provedor). Dá ~4.900 tokens de entrada; a saída é
#: suposta (um JSON com algumas divergências). Com uso medido, vale a média.
TOKENS_DE_ENTRADA_A_PRIORI = 4900
TOKENS_DE_SAIDA_A_PRIORI = 900

#: O que é GRAVE por definição do pedido do oficial — a IA não rebaixa.
CATEGORIAS_GRAVES = frozenset({
    "nome", "documento", "numero", "area", "medida", "confrontacao", "valor",
    "data", "onus", "livro_folha"})
CATEGORIAS = (*sorted(CATEGORIAS_GRAVES), "grafia", "pontuacao", "abreviatura",
              "outro")

PENDENTE, LENDO, PRONTA, ERRO = "PENDENTE", "LENDO", "PRONTA", "ERRO"

#: (nome, comando): cada tabela e índice se conferem separados — tabela que já
#: existe sem o índice ganha o índice (a régua de `revisao_previa.init_schema`).
SCHEMA = (
    ("ri_transcricao_revisoes", """
CREATE TABLE IF NOT EXISTS ri_transcricao_revisoes (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    matricula_id bigint NOT NULL,
    hash_texto TEXT NOT NULL,
    hash_paginas TEXT NOT NULL,
    com_imagem boolean NOT NULL,
    paginas bigint NOT NULL DEFAULT 0,
    paginas_vistas bigint NOT NULL DEFAULT 0,
    paginas_json TEXT,                  -- [{n, fonte, imagem_id, quadro, falta}]
    situacao TEXT NOT NULL DEFAULT 'PENDENTE',   -- PENDENTE | LENDO | PRONTA | ERRO
    origem TEXT NOT NULL DEFAULT 'CERTIDAO',     -- CERTIDAO | LOTE
    lote_id bigint,
    pedido_em TEXT NOT NULL,
    pedido_por TEXT,
    terminado_em TEXT,
    provedor TEXT,
    modelo TEXT,
    chamadas bigint NOT NULL DEFAULT 0,
    resultado_json TEXT,
    graves bigint NOT NULL DEFAULT 0,
    leves bigint NOT NULL DEFAULT 0,
    avisos bigint NOT NULL DEFAULT 0,
    erro TEXT,
    tokens_entrada bigint NOT NULL DEFAULT 0,
    tokens_saida bigint NOT NULL DEFAULT 0
)"""),
    ("ix_ri_transcricao_revisoes_ficha", """
CREATE INDEX IF NOT EXISTS ix_ri_transcricao_revisoes_ficha
    ON ri_transcricao_revisoes (matricula_id, hash_texto, id)"""),
    # A CERTIDÃO E A REVISÃO QUE ELA TINHA — uma linha por certidão de inteiro
    # teor emitida com a revisão ligada: em que pé estava a revisão, quantas
    # graves estavam pendentes e a justificativa de quem emitiu assim mesmo.
    ("ri_transcricao_emissoes", """
CREATE TABLE IF NOT EXISTS ri_transcricao_emissoes (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    certidao_id bigint NOT NULL,
    matricula_id bigint NOT NULL,
    revisao_id bigint,
    situacao TEXT NOT NULL,             -- PRONTA | SEM_REVISAO | ERRO
    graves_pendentes bigint NOT NULL DEFAULT 0,
    justificativa TEXT,
    emitida_por TEXT,
    emitida_em TEXT NOT NULL
)"""),
    ("ix_ri_transcricao_emissoes_certidao", """
CREATE INDEX IF NOT EXISTS ix_ri_transcricao_emissoes_certidao
    ON ri_transcricao_emissoes (certidao_id)"""),
)


class TranscricaoError(ValueError):
    """Erro de regra, com a frase pronta para a tela."""


class TranscricaoPendente(TranscricaoError):
    """A certidão não sai assim — a frase diz o que fazer.

    Leva `graves` e `revisao_id` para a auditoria da recusa (só números)."""

    def __init__(self, frase: str, *, graves: int = 0, revisao_id: int | None = None):
        super().__init__(frase)
        self.graves, self.revisao_id = graves, revisao_id


class RecusaGuardada:
    """Guarda a recusa que nasce DENTRO da transação da emissão, para a rota a
    dar POR FORA dela (LH12): `with guarda, db.transaction() as con:`.

    A transação volta atrás sem nada gravado, e a guarda fica com a recusa
    (`erro`). A auditoria vem depois do `with`: dentro dele, ela esperaria a
    trava que a própria emissão segura — `Database.log` desiste em 800 ms — e
    a recusa sairia da tabela de auditoria, indo só para o log do servidor."""

    def __init__(self) -> None:
        self.erro: TranscricaoPendente | None = None

    def __enter__(self) -> "RecusaGuardada":
        return self

    def __exit__(self, tipo, valor, rastro) -> bool:
        if isinstance(valor, TranscricaoPendente):
            self.erro = valor
            return True
        return False


def init_schema(con) -> None:
    """Cria o que falta. Só escreve quando falta: a tela da ficha lê sem passar
    por aqui, e DDL no PostgreSQL trava a tabela até o fim da transação.

    RODA NA SUBIDA (LH12): `database.Database.init_schema` o chama, pelo
    `revisao_transcricao_lote.init_schema`. A emissão da certidão conta com
    isso e não o chama — o DDL viria depois do número, na transação que o
    segura. `pedir` e `executar` ainda o chamam, para o banco que não subiu."""
    bd = banco(con)
    for nome, comando in SCHEMA:
        if not bd.tem_tabela(nome):
            bd.escrever(comando)


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _config(con, chave: str) -> str | None:
    bd = banco(con)
    if not bd.tem_tabela("settings"):
        return None
    linha = bd.um("SELECT value FROM settings WHERE key = %s", (chave,))
    return None if linha is None or linha["value"] is None else str(linha["value"]).strip()


def manda_imagem(con) -> bool:
    """A decisão do oficial de 21/10/2026: liga por padrão, e só '0' desliga."""
    return _config(con, CHAVE_IMAGEM) != "0"


def _numero(texto, padrao, *, tipo=int):
    try:
        valor = tipo(str(texto).replace(",", "."))
    except (TypeError, ValueError):
        return padrao
    return valor if valor > 0 else padrao


def configuracao(con) -> dict:
    """O que a tela de Configurações mostra e o lote usa. SÓ LÊ."""
    return {"manda_imagem": manda_imagem(con),
            "teto_paginas": _numero(_config(con, CHAVE_TETO_PAGINAS),
                                    TETO_DE_PAGINAS_POR_RODADA),
            "teto_custo": _numero(_config(con, CHAVE_TETO_CUSTO),
                                  TETO_DE_CUSTO_POR_RODADA, tipo=float)}


def no_sandbox(con) -> bool:
    import ri_onus_ia as RONIA
    return RONIA.no_sandbox(con)


def ligada(con, pasta_dados: Path) -> bool:
    """Com a chave do provedor da revisão prévia, sem `revisao_transcricao =
    '0'` e fora do SANDBOX. SÓ LÊ."""
    import agente_provedores as AP
    if no_sandbox(con):
        return False
    if _config(con, CHAVE_LIGADA) == "0":
        return False
    return AP.tem_chave(pasta_dados, PROVEDOR)


# ------------------------------------------------------------------ o texto

def _corrido(teor) -> str:
    """O texto sem a marcação, com um parágrafo por linha — a IA lê melhor com
    as quebras, e é por elas que o teor separa os atos."""
    t = re.sub(r"(?i)<\s*(br|/?p|/?div|li|/?h\d|tr)\b[^>]*>", "\n", str(teor or ""))
    t = unescape(re.sub(r"(?s)<[^>]+>", " ", t))
    return "\n".join(" ".join(ln.split()) for ln in t.split("\n") if ln.strip())


def texto_da_ficha(con, matricula_id: int) -> dict:
    """O texto transcrito que a certidão de inteiro teor imprime, e o cadastro
    da ficha. SÓ LÊ. `texto` vazio quando a ficha não tem o que conferir."""
    import ri_numeros_do_teor as NUMT
    bd = banco(con)
    m = bd.um("""SELECT id, numero, cnm, livro, folha, data_abertura, teor, area_valor,
                        area_unidade, descricao_perimetro, confrontacoes, registro_anterior,
                        logradouro, cidade, uf
                   FROM ri_matriculas WHERE id = %s""", (matricula_id,))
    if m is None:
        raise TranscricaoError("Matrícula não encontrada.")
    partes = [_corrido(m["teor"])] if _corrido(m["teor"]) else []
    atos = bd.ler(
        """SELECT id, tipo, numero, data_ato, teor, selo_texto FROM ri_atos
            WHERE matricula_id = %s AND origem = 'EOFICIO' AND COALESCE(cancelado, 0) = 0
              AND COALESCE(teor, '') <> '' ORDER BY numero, id""", (matricula_id,))
    fora = NUMT.atos_fora_do_teor(m["teor"] or "", atos, matricula=m)
    for a in fora:
        partes.append(f"[{a['tipo']}-{a['numero']} — ato do E-Ofício, impresso depois do "
                      f"teor]\n{_corrido(a['teor'])}")
    donos = bd.ler(
        """SELECT nome, documento_numero, papel FROM ri_partes WHERE matricula_id = %s
            ORDER BY proprietario_ativo DESC, nome, id""", (matricula_id,))
    cadastro = [f"Matrícula nº {m['numero']} — livro {m['livro'] or '2'}, folha "
                f"{m['folha'] or '—'}, CNM {m['cnm'] or '—'}, aberta em "
                f"{m['data_abertura'] or '—'}",
                f"Área: {m['area_valor'] or '—'} {m['area_unidade'] or ''}".rstrip(),
                f"Perímetro: {m['descricao_perimetro'] or '—'}",
                f"Confrontações: {m['confrontacoes'] or '—'}",
                f"Registro anterior: {m['registro_anterior'] or '—'}",
                f"Endereço: {m['logradouro'] or '—'}, {m['cidade'] or '—'}/{m['uf'] or '—'}",
                "Partes cadastradas: " + ("; ".join(
                    f"{p['nome']} ({p['documento_numero'] or 'sem documento'}, "
                    f"{p['papel'] or 'sem papel'})" for p in donos) or "nenhuma")]
    texto = "\n\n".join(partes)
    return {"numero": m["numero"], "livro": m["livro"], "texto": texto,
            "atos_do_acervo": len(fora), "cadastro": "\n".join(cadastro)}


def hash_do_texto(texto: str) -> str:
    """A identidade do texto: o espaço não conta, a vírgula conta."""
    return hashlib.sha256(RP.normalizar(texto).encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ as páginas
#
# O PDFIUM NÃO PODE SER USADO POR DUAS LINHAS DE EXECUÇÃO AO MESMO TEMPO (derruba
# o processo, que é o servidor do balcão — ver `revisao_anexos.transcrever`).
# O lote e o botão da certidão rodam em linhas diferentes; a trava é desta casa.
_PDFIUM = threading.Lock()


def _caminho_da_pagina(raiz: Path, linha: dict) -> Path | None:
    """A cópia do sistema primeiro (a origem é do E-Ofício e pode sumir) — a
    régua da rota que mostra a ficha (`ri_imagem`)."""
    if linha.get("caminho_interno"):
        interno = Path(raiz) / linha["caminho_interno"]
        if interno.is_file():
            return interno
    if linha.get("caminho") and Path(linha["caminho"]).is_file():
        return Path(linha["caminho"])
    return None


def _quadros(caminho: Path) -> tuple[str, int]:
    """(«pdf» | «imagem», quantas páginas), sem desenhar nenhuma.

    O ARQUIVO DO E-OFÍCIO NÃO TEM EXTENSÃO (`00003967.0001`: o `.0001` é a
    página — ver `ri_imagens`). O que decide é o começo do arquivo."""
    with open(caminho, "rb") as f:
        pdf = f.read(5).startswith(b"%PDF")
    if pdf:
        import pypdfium2 as pdfium
        with _PDFIUM:
            doc = pdfium.PdfDocument(str(caminho))
            try:
                n = len(doc)
            finally:
                doc.close()
        TETO.conferir_paginas(n, "o PDF da digitalização")
        return "pdf", n
    from PIL import Image
    with Image.open(caminho) as im:
        n = int(getattr(im, "n_frames", 1) or 1)
    TETO.conferir_paginas(n, "a digitalização")
    return "imagem", n


def _desenhar(caminho: Path, tipo: str, quadro: int) -> str:
    """A página como JPEG em base64, no tamanho da leitura dos anexos."""
    import revisao_anexos as RA
    import ri_digitalizacao as RDIGI
    if tipo == "pdf":
        import pypdfium2 as pdfium
        with _PDFIUM:
            doc = pdfium.PdfDocument(str(caminho))
            try:
                largura, altura = doc[quadro].get_size()
                escala = RA.LADO_MAIOR_PX / max(largura, altura, 1)
                return RA._jpeg(doc[quadro].render(scale=escala, grayscale=True).to_pil())
            finally:
                doc.close()
    from PIL import Image
    with Image.open(caminho) as im:
        if quadro:
            im.seek(quadro)
        RDIGI._conferir_area(*im.size)
        return RA._jpeg(im)


def paginas_da_ficha(con, raiz: Path, matricula_id: int) -> list[dict]:
    """As páginas escaneadas da ficha, na ordem: `[{n, fonte, imagem_id,
    quadro, sha, falta, motivo, imagem()}]`. SÓ LÊ; nenhuma imagem se desenha
    aqui — `imagem` é função, chamada só na leitura."""
    from storage import hash_file
    bd = banco(con)
    m = bd.um("SELECT digi_path, digi_sha256 FROM ri_matriculas WHERE id = %s",
              (matricula_id,))
    if m is None:
        return []
    arquivos: list[tuple[dict, Path | None, str]] = []
    if m["digi_path"] and Path(m["digi_path"]).is_file():
        arquivos.append(({"fonte": "DIGITALIZACAO", "imagem_id": None},
                         Path(m["digi_path"]), m["digi_sha256"] or ""))
    else:
        for r in bd.ler("""SELECT id, nome_arquivo, caminho, caminho_interno, sha256
                             FROM ri_imagens WHERE matricula_id = %s
                            ORDER BY ordem NULLS FIRST, id""", (matricula_id,)):
            arquivos.append(({"fonte": "EOFICIO", "imagem_id": r["id"]},
                             _caminho_da_pagina(raiz, r), r["sha256"] or ""))
    paginas: list[dict] = []
    for base, caminho, sha in arquivos:
        if caminho is None:
            paginas.append({**base, "quadro": 0, "sha": f"falta:{base['imagem_id']}",
                            "falta": True, "motivo": "o arquivo não está na pasta",
                            "imagem": None})
            continue
        try:
            tipo, n = _quadros(caminho)
            sha = sha or hash_file(caminho)
        except Exception as erro:              # noqa: BLE001 — vira aviso, e não erro
            paginas.append({**base, "quadro": 0, "sha": f"ilegivel:{base['imagem_id']}",
                            "falta": True, "imagem": None,
                            "motivo": f"o arquivo não abre ({type(erro).__name__})"})
            continue
        for q in range(n):
            paginas.append({**base, "quadro": q, "sha": sha, "falta": False, "motivo": "",
                            "imagem": (lambda c=caminho, t=tipo, q=q: _desenhar(c, t, q))})
    for i, p in enumerate(paginas, start=1):
        p["n"] = i
    return paginas


def hash_das_paginas(paginas: list[dict]) -> str:
    """A identidade do conjunto de páginas: varredura nova é outra revisão."""
    return hashlib.sha256("|".join(f"{p['sha']}:{p['quadro']}" for p in paginas)
                          .encode("utf-8")).hexdigest()


def _paginas_para_guardar(paginas: list[dict]) -> str:
    return json.dumps([{k: p[k] for k in ("n", "fonte", "imagem_id", "quadro", "falta")}
                       for p in paginas])


# ------------------------------------------------------------------ o pedido

def pedir(con, matricula_id: int, *, raiz: Path, usuario: str = "",
          origem: str = "CERTIDAO", lote_id: int | None = None) -> tuple[int, bool]:
    """(id, nova). ESCREVE. O mesmo texto com as mesmas páginas, já revisado
    (ou lendo), devolve a revisão que existe — e não paga de novo.

    A TRAVA VEM ANTES DA PROCURA: o botão da certidão e o lote podem pedir a
    mesma ficha ao mesmo tempo, e sem ela os dois achariam «não tem» e pagariam
    duas leituras."""
    bd = banco(con)
    init_schema(bd)
    ficha = texto_da_ficha(bd, matricula_id)
    if not ficha["texto"].strip():
        raise TranscricaoError("Esta ficha não tem texto transcrito para revisar.")
    com_imagem = manda_imagem(bd)
    paginas = paginas_da_ficha(bd, raiz, matricula_id)
    hash_texto = hash_do_texto(ficha["texto"])
    hash_paginas = hash_das_paginas(paginas)
    bd.travar("ri_transcricao_revisoes.matricula")
    ja = bd.um(
        """SELECT id FROM ri_transcricao_revisoes
            WHERE matricula_id = %s AND hash_texto = %s AND hash_paginas = %s
              AND com_imagem = %s AND situacao IN ('PENDENTE', 'LENDO', 'PRONTA')
         ORDER BY id DESC LIMIT 1""",
        (matricula_id, hash_texto, hash_paginas, com_imagem))
    if ja:
        return int(ja["id"]), False
    novo = bd.escrever(
        """INSERT INTO ri_transcricao_revisoes (matricula_id, hash_texto, hash_paginas,
               com_imagem, paginas, paginas_json, origem, lote_id, pedido_em, pedido_por)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (matricula_id, hash_texto, hash_paginas, com_imagem, len(paginas),
         _paginas_para_guardar(paginas), origem, lote_id, _agora(), usuario or None))
    return int(novo[0]["id"]), True


# ------------------------------------------------------------------ a leitura

INSTRUCAO = """Você confere, para o Registro de Imóveis de uma serventia extrajudicial \
do Maranhão, a TRANSCRIÇÃO de uma ficha de livro antigo contra a IMAGEM da página \
escaneada do livro. O texto transcrito é o que a certidão de inteiro teor imprime; a \
página é o original.

Você recebe o TEXTO TRANSCRITO da ficha inteira, o CADASTRO dela no sistema e as imagens \
de algumas páginas, na ordem, com o número de cada uma. Compare o texto com o que está \
ESCRITO NAS PÁGINAS QUE VOCÊ VÊ. Trecho do texto que pertence a outra página não é \
divergência: a outra página vai em outra conferência.

Aponte cada DIVERGÊNCIA entre o texto e a página: o trecho do texto, o que o texto diz e \
o que a página diz. A gravidade:
- GRAVE: nome de parte; CPF, RG ou outro documento; número de matrícula, registro ou \
transcrição; área; medida; confrontação; valor; data; ônus; livro ou folha — inclusive \
quando um desses elementos está na página e falta no texto, ou o contrário;
- LEVE: grafia, acentuação, pontuação, abreviatura, maiúscula e palavra a mais ou a menos \
que não muda o sentido.

Página ilegível (ou o pedaço dela), página que falta, carimbo ou assinatura que não se lê: \
é AVISO, e não divergência — não adivinhe o que está escrito. «[rubrica]», «[assinatura]» e \
a marca de página da transcrição («[Ficha — Matrícula … — página N de M]») são da \
transcrição: não aponte.

Você NÃO corrige o texto: só aponta. Não invente: se a página não deixa ler, é aviso.

Responda SÓ com JSON, sem texto em volta:
{"divergencias": [{"gravidade": "GRAVE" | "LEVE", "o_que": "nome | documento | numero | \
area | medida | confrontacao | valor | data | onus | livro_folha | grafia | pontuacao | \
abreviatura | outro", "pagina": N, "trecho": "...", "texto_diz": "...", "pagina_diz": \
"..."}], "avisos": [{"pagina": N, "o_que": "..."}], "parecer": "uma ou duas frases"}
Sem divergência, lista vazia."""

INSTRUCAO_SEM_IMAGEM = """Você confere, para o Registro de Imóveis de uma serventia \
extrajudicial do Maranhão, a TRANSCRIÇÃO de uma ficha de livro antigo. Você NÃO recebe a \
imagem da página: a serventia desligou o envio dela. Confira o TEXTO TRANSCRITO contra o \
CADASTRO da ficha no sistema (número, livro, folha, área, perímetro, confrontações, registro \
anterior, partes) e contra ele mesmo (número por extenso e em algarismos, datas fora de \
ordem, área ou confrontação que muda de um ato para outro sem ato que a mude).

A divergência é entre o texto e o cadastro (ou entre dois trechos do texto): em \
«texto_diz» o que o texto diz, e em «pagina_diz» o que o cadastro (ou o outro trecho) diz. \
A gravidade: GRAVE em nome de parte, documento, número de matrícula/registro/transcrição, \
área, medida, confrontação, valor, data, ônus, livro ou folha; LEVE em grafia, pontuação e \
abreviatura. Não aponte o que só a página poderia dizer. Nomes podem vir como marcas \
([PESSOA_01]): marcas iguais são a mesma pessoa, e a máscara não é erro.

Responda SÓ com JSON, sem texto em volta:
{"divergencias": [{"gravidade": "GRAVE" | "LEVE", "o_que": "nome | documento | numero | \
area | medida | confrontacao | valor | data | onus | livro_folha | grafia | pontuacao | \
abreviatura | outro", "pagina": null, "trecho": "...", "texto_diz": "...", "pagina_diz": \
"..."}], "avisos": [], "parecer": "uma ou duas frases"}
Sem divergência, lista vazia."""

AVISO_SEM_IMAGEM = ("A revisão NÃO viu a página: o envio da imagem está desligado "
                    "(Configurações, revisao_transcricao_manda_imagem). Ela conferiu só o "
                    "texto contra o cadastro da ficha.")


def dossie(ficha: dict) -> str:
    return "\n".join([
        f"FICHA: matrícula nº {ficha['numero']} (livro {ficha['livro'] or '2'})", "",
        "=== CADASTRO DA FICHA NO SISTEMA ===", ficha["cadastro"], "",
        "=== TEXTO TRANSCRITO (o que a certidão imprime) ===",
        ficha["texto"][:LIMITE_DO_TEXTO]])


def _curto(valor, limite: int = 600) -> str:
    return " ".join(str(valor or "").split())[:limite]


def _pagina(valor, validas: set[int]) -> int | None:
    try:
        n = int(valor)
    except (TypeError, ValueError):
        return None
    return n if n in validas else None


def ler_resposta(texto: str, paginas_vistas: list[int]) -> dict:
    """O JSON da IA, com a gravidade conferida pela régua do código."""
    m = re.search(r"\{.*\}", texto or "", re.S)
    if not m:
        raise ValueError("a resposta não trouxe JSON")
    d = json.loads(m.group(0))
    validas = set(paginas_vistas)
    divergencias = []
    for x in d.get("divergencias") or []:
        if not isinstance(x, dict):
            continue
        o_que = str(x.get("o_que") or "outro").strip().lower()
        o_que = o_que if o_que in CATEGORIAS else "outro"
        grave = str(x.get("gravidade") or "").upper() == "GRAVE" or o_que in CATEGORIAS_GRAVES
        divergencias.append({"gravidade": "GRAVE" if grave else "LEVE", "o_que": o_que,
                             "pagina": _pagina(x.get("pagina"), validas),
                             "trecho": _curto(x.get("trecho")),
                             "texto_diz": _curto(x.get("texto_diz")),
                             "pagina_diz": _curto(x.get("pagina_diz"))})
    avisos = [{"pagina": _pagina(a.get("pagina"), validas), "o_que": _curto(a.get("o_que"))}
              for a in d.get("avisos") or [] if isinstance(a, dict) and a.get("o_que")]
    return {"divergencias": divergencias, "avisos": avisos,
            "parecer": _curto(d.get("parecer"))}


def _juntar(partes: list[dict]) -> dict:
    """As chamadas de uma ficha viram um resultado; a mesma divergência
    apontada em duas chamadas conta uma vez."""
    vistos, divergencias, avisos, pareceres = set(), [], [], []
    for p in partes:
        for d in p["divergencias"]:
            chave = (d["trecho"], d["texto_diz"], d["pagina_diz"])
            if chave not in vistos:
                vistos.add(chave)
                divergencias.append(d)
        avisos += p["avisos"]
        if p["parecer"]:
            pareceres.append(p["parecer"])
    # O GRAVE PRIMEIRO, na ordem das páginas: é por ele que quem confere começa.
    divergencias.sort(key=lambda d: (d["gravidade"] != "GRAVE", d["pagina"] or 0))
    return {"divergencias": divergencias, "avisos": avisos,
            "parecer": " ".join(pareceres)[:1200]}


def executar(banco_caminho, pasta_dados: Path, revisao_id: int, *, raiz: Path,
             conversar=None) -> None:
    """Lê. FALA COM A REDE, com conexão própria e fora de transação de escrita.

    Cada chamada leva o texto inteiro e até duas páginas; o resultado só se
    grava inteiro. A IA que falha numa chamada deixa a revisão em ERRO — e a
    certidão sai, dizendo que saiu sem revisão."""
    import agente_provedores as AP
    from gestor_expedientes import desmascarar
    conversar = conversar or AP.conversar
    con = banco_pg.conectar(str(banco_caminho), timeout=30)
    try:
        bd = Banco(con)
        init_schema(bd)
        r = bd.um("""SELECT matricula_id, hash_texto, hash_paginas, com_imagem
                       FROM ri_transcricao_revisoes WHERE id = %s""", (revisao_id,))
        if r is None:
            return
        bd.escrever("UPDATE ri_transcricao_revisoes SET situacao = 'LENDO', provedor = %s, "
                    "modelo = %s WHERE id = %s", (PROVEDOR, MODELO, revisao_id))
        con.commit()
        entrada = saida = chamadas = vistas = 0
        modelo_usado = MODELO
        try:
            ficha = texto_da_ficha(bd, r["matricula_id"])
            if hash_do_texto(ficha["texto"]) != r["hash_texto"]:
                raise TranscricaoError("o texto da ficha mudou depois do pedido")
            paginas = paginas_da_ficha(bd, raiz, r["matricula_id"])
            if hash_das_paginas(paginas) != r["hash_paginas"]:
                raise TranscricaoError("as páginas da ficha mudaram depois do pedido")
            avisos = [{"pagina": p["n"], "o_que": f"Página {p['n']}: {p['motivo']}."}
                      for p in paginas if p["falta"]]
            legiveis = [p for p in paginas if not p["falta"]]
            if len(legiveis) > TETO_DE_PAGINAS_POR_FICHA:
                fora = legiveis[TETO_DE_PAGINAS_POR_FICHA:]
                legiveis = legiveis[:TETO_DE_PAGINAS_POR_FICHA]
                avisos.append({"pagina": None, "o_que": (
                    f"A ficha tem {len(paginas)} páginas, acima do teto de "
                    f"{TETO_DE_PAGINAS_POR_FICHA} por revisão: ficaram de fora as páginas "
                    f"{fora[0]['n']} a {fora[-1]['n']}. Confira essas à mão.")})
            texto_base = dossie(ficha)
            if len(ficha["texto"]) > LIMITE_DO_TEXTO:
                avisos.append({"pagina": None, "o_que": (
                    f"O texto transcrito passa de {LIMITE_DO_TEXTO} letras: a revisão leu "
                    "só o começo dele. Confira o resto à mão.")})
            partes = []
            if r["com_imagem"] and legiveis:
                total = len(paginas)
                for i in range(0, len(legiveis), PAGINAS_POR_PEDIDO):
                    grupo = legiveis[i:i + PAGINAS_POR_PEDIDO]
                    # A IMAGEM SE DESENHA AQUI, UMA A UMA (o PDFium não aceita duas
                    # linhas de execução), e vai sem máscara — a decisão de 21/10.
                    imagens = [{"mime": "image/jpeg", "base64": p["imagem"]()} for p in grupo]
                    numeros = [p["n"] for p in grupo]
                    pergunta = (texto_base + "\n\n=== AS PÁGINAS DESTA CONFERÊNCIA ===\n"
                                + "; ".join(f"a {k}ª imagem é a página {n} de {total}"
                                            for k, n in enumerate(numeros, start=1)))
                    # O REGISTRO DO USO DE IA (LF01): a revisão e a ficha, sem texto.
                    resposta = conversar(pasta_dados, provedor=PROVEDOR, sistema=INSTRUCAO,
                                         conversa=[{"tipo": "user", "texto": pergunta,
                                                    "imagens": imagens}],
                                         ferramentas=[], modelo=MODELO,
                                         maximo_de_saida=MAXIMO_DE_SAIDA,
                                         modulo="revisao_transcricao",
                                         finalidade="revisao_transcricao", atribuicao="RI",
                                         referencia=f"ri_transcricao_revisoes:{revisao_id}",
                                         mascarado=False)
                    partes.append(ler_resposta(resposta.get("texto") or "", numeros))
                    entrada += int(resposta.get("entrada") or 0)
                    saida += int(resposta.get("saida") or 0)
                    modelo_usado = resposta.get("modelo") or modelo_usado
                    chamadas += 1
                    vistas += len(grupo)
            else:
                avisos.append({"pagina": None, "o_que": (
                    AVISO_SEM_IMAGEM if not r["com_imagem"] else
                    "A ficha não tem página escaneada que se leia: a revisão conferiu só "
                    "o texto contra o cadastro da ficha.")})
                seguro, mapa = RP.preparar_para_ia(bd, texto_base)
                resposta = conversar(pasta_dados, provedor=PROVEDOR,
                                     sistema=INSTRUCAO_SEM_IMAGEM,
                                     conversa=[{"tipo": "user", "texto": seguro}],
                                     ferramentas=[], modelo=MODELO,
                                     maximo_de_saida=MAXIMO_DE_SAIDA,
                                     modulo="revisao_transcricao",
                                     finalidade="revisao_transcricao", atribuicao="RI",
                                     referencia=f"ri_transcricao_revisoes:{revisao_id}",
                                     mascarado=bool(mapa) or RP.mascarar_na_revisao(bd))
                partes.append(desmascarar(ler_resposta(resposta.get("texto") or "", []),
                                          mapa))
                entrada += int(resposta.get("entrada") or 0)
                saida += int(resposta.get("saida") or 0)
                modelo_usado = resposta.get("modelo") or modelo_usado
                chamadas += 1
            res = _juntar(partes)
            res["avisos"] = avisos + res["avisos"]
            graves = sum(d["gravidade"] == "GRAVE" for d in res["divergencias"])
            bd.escrever(
                """UPDATE ri_transcricao_revisoes
                      SET situacao = 'PRONTA', terminado_em = %s, resultado_json = %s,
                          graves = %s, leves = %s, avisos = %s, modelo = %s,
                          chamadas = %s, paginas_vistas = %s, tokens_entrada = %s,
                          tokens_saida = %s
                    WHERE id = %s""",
                (_agora(), json.dumps(res, ensure_ascii=False), graves,
                 len(res["divergencias"]) - graves, len(res["avisos"]), modelo_usado,
                 chamadas, vistas, entrada, saida, revisao_id))
        except Exception as erro:                       # noqa: BLE001 — vai à tabela
            # O ERRO GUARDA O TIPO E A FRASE CURTA, e não a resposta do provedor:
            # ela pode trazer de volta um pedaço do que subiu.
            bd.escrever(
                """UPDATE ri_transcricao_revisoes
                      SET situacao = 'ERRO', terminado_em = %s, erro = %s, chamadas = %s,
                          paginas_vistas = %s, tokens_entrada = %s, tokens_saida = %s
                    WHERE id = %s""",
                (_agora(), f"{type(erro).__name__}: {str(erro)[:200]}", chamadas, vistas,
                 entrada, saida, revisao_id))
        con.commit()
    finally:
        con.close()


def ler_em_segundo_plano(banco_caminho, pasta_dados: Path, revisao_id: int, *,
                         raiz: Path) -> None:
    threading.Thread(target=executar, args=(Path(banco_caminho), Path(pasta_dados),
                                            revisao_id),
                     kwargs={"raiz": Path(raiz)}, daemon=True,
                     name=f"revisao-transcricao-{revisao_id}").start()


# ------------------------------------------------------------------ o que se mostra

def _situacao_viva(situacao: str, pedido_em: str | None) -> str:
    """Leitura que não termina vira ERRO para a tela — não pode prender a certidão."""
    if situacao in (PENDENTE, LENDO) and pedido_em:
        try:
            idade = (datetime.now() - datetime.fromisoformat(pedido_em)).total_seconds()
        except ValueError:
            idade = 0
        if idade > MINUTOS_PARA_DESISTIR * 60:
            return ERRO
    return situacao


def custo(modelo: str | None, entrada: int, saida: int) -> float:
    """Dólares estimados — a tabela de preço da casa (`rc_leitura_documentos`)."""
    import rc_leitura_documentos as RL
    return RL.custo(modelo or MODELO, entrada, saida)


def mostrar(con, revisao_id: int) -> dict | None:
    """A revisão para a tela. SÓ LÊ (e não cria a tabela)."""
    bd = banco(con)
    if not bd.tem_tabela("ri_transcricao_revisoes"):
        return None
    r = bd.um("SELECT * FROM ri_transcricao_revisoes WHERE id = %s", (revisao_id,))
    if r is None:
        return None
    resultado = (json.loads(r["resultado_json"]) if r["resultado_json"]
                 else {"divergencias": [], "avisos": [], "parecer": ""})
    saida = {k: r[k] for k in ("id", "matricula_id", "hash_texto", "hash_paginas",
                               "com_imagem", "paginas", "paginas_vistas", "origem",
                               "lote_id", "pedido_em", "pedido_por", "terminado_em",
                               "modelo", "chamadas", "graves", "leves", "erro",
                               "tokens_entrada", "tokens_saida")}
    # `avisos` é a LISTA do resultado (a coluna é só a conta dela, para o lote).
    saida.update(resultado)
    saida["situacao"] = _situacao_viva(r["situacao"], r["pedido_em"])
    saida["lista_de_paginas"] = json.loads(r["paginas_json"]) if r["paginas_json"] else []
    saida["custo"] = custo(r["modelo"], r["tokens_entrada"], r["tokens_saida"])
    saida["graves_pendentes"] = graves_pendentes(saida)
    return saida


def graves_pendentes(revisao: dict | None) -> int:
    """As divergências GRAVES que ninguém deu por conferidas."""
    if not revisao or revisao.get("situacao") != PRONTA:
        return 0
    return sum(1 for d in revisao.get("divergencias") or []
               if d.get("gravidade") == "GRAVE" and not d.get("conferida"))


#: A revisão que VALE para um texto e um conjunto de páginas. É uma régua só
#: para a tela (`vigente`) e para a emissão (`reconferir_na_emissao`, que a
#: lê com a linha presa): duas réguas escritas à parte divergiriam.
_SQL_DA_VIGENTE = """SELECT id FROM ri_transcricao_revisoes
                      WHERE matricula_id = %s AND hash_texto = %s
                        AND (NOT com_imagem OR hash_paginas = %s)
                   ORDER BY id DESC LIMIT 1"""


def vigente(con, raiz: Path, matricula_id: int, *, ficha: dict | None = None,
            paginas: list[dict] | None = None) -> dict:
    """A revisão que vale para a ficha COMO ESTÁ, e a última de todas. SÓ LÊ.

    Vale a mais nova com o mesmo texto e — se ela viu a página — as mesmas
    páginas: a revisão sem imagem não depende da varredura. Quem já leu a
    ficha e as páginas as passa (`painel`), e elas não se leem duas vezes."""
    bd = banco(con)
    if not bd.tem_tabela("ri_transcricao_revisoes"):
        return {"vale": None, "ultima": None}
    ficha = ficha or texto_da_ficha(bd, matricula_id)
    hash_texto = hash_do_texto(ficha["texto"])
    hash_paginas = hash_das_paginas(paginas if paginas is not None
                                    else paginas_da_ficha(bd, raiz, matricula_id))
    linha = bd.um(_SQL_DA_VIGENTE, (matricula_id, hash_texto, hash_paginas))
    ultima = bd.um("""SELECT id FROM ri_transcricao_revisoes WHERE matricula_id = %s
                     ORDER BY id DESC LIMIT 1""", (matricula_id,))
    vale = mostrar(bd, linha["id"]) if linha else None
    return {"vale": vale,
            "ultima": vale if (vale and ultima and vale["id"] == ultima["id"])
            else (mostrar(bd, ultima["id"]) if ultima else None)}


def painel(con, pasta_dados: Path, raiz: Path, matricula_id: int) -> dict | None:
    """O que a ficha mostra no quadro da certidão. SÓ LÊ. None quando a etapa
    não existe nesta casa (sem IA, desligada, SANDBOX) — como a revisão prévia,
    que some da tela sem a chave — ou quando a ficha não tem texto transcrito."""
    if not ligada(con, pasta_dados):
        return None
    try:
        ficha = texto_da_ficha(con, matricula_id)
    except TranscricaoError:
        return None
    if not ficha["texto"].strip():
        return None
    paginas = paginas_da_ficha(con, raiz, matricula_id)
    revisoes = vigente(con, raiz, matricula_id, ficha=ficha, paginas=paginas)
    return {"manda_imagem": manda_imagem(con), "paginas": len(paginas),
            "faltando": sum(1 for p in paginas if p["falta"]),
            "atos_do_acervo": ficha["atos_do_acervo"],
            "vale": revisoes["vale"], "ultima": revisoes["ultima"],
            "graves_pendentes": graves_pendentes(revisoes["vale"])}


# ------------------------------------------------------------------ o resolvido

PAPEIS_QUE_CONFEREM = RP.PAPEIS_QUE_SUPREM


def conferir_divergencias(con, revisao_id: int, itens, *, usuario: str = "",
                          papel: str | None = None) -> list[dict]:
    """Dá divergências por CONFERIDAS NO LIVRO — o texto está certo, e foi a
    leitura da página que errou (ou a correção já foi feita por outro
    caminho). ESCREVE `resultado_json`. `itens` = [(índice, observação)].

    É a régua do «já verificado/suprido» da revisão prévia: a GRAVE só o
    gerente ou o administrador dá por conferida, com observação de dez letras.
    Tudo se confere antes de gravar."""
    bd = banco(con)
    bd._escrita()
    linha = bd.um("""SELECT situacao, resultado_json FROM ri_transcricao_revisoes
                      WHERE id = %s FOR UPDATE""", (int(revisao_id),))
    if linha is None:
        raise TranscricaoError("Revisão não encontrada.")
    if linha["situacao"] != PRONTA or not linha["resultado_json"]:
        raise TranscricaoError("Só se dá por conferida a divergência de revisão terminada.")
    if (papel or "").upper() not in PAPEIS_QUE_CONFEREM:
        raise TranscricaoError("Dar divergência por conferida é do gerente ou do "
                               "administrador.")
    d = json.loads(linha["resultado_json"])
    divergencias = d.get("divergencias") or []
    feitos, agora = [], _agora()
    for indice, obs in itens:
        indice = int(indice)
        if not 0 <= indice < len(divergencias):
            raise TranscricaoError(f"A divergência {indice + 1} não existe nesta revisão.")
        x = divergencias[indice]
        obs = " ".join((obs or "").split())[:600]
        if x.get("gravidade") == "GRAVE" and len(obs) < MINIMO_DA_JUSTIFICATIVA:
            raise TranscricaoError("Para dar uma divergência GRAVE por conferida, escreva "
                                   "como ela foi conferida no livro (mínimo de dez letras).")
        if x.get("conferida"):
            continue
        x["conferida"] = {"por": usuario, "papel": papel, "em": agora, "obs": obs}
        feitos.append({"indice": indice, "gravidade": x.get("gravidade")})
    if feitos:
        d["divergencias"] = divergencias
        bd.escrever("UPDATE ri_transcricao_revisoes SET resultado_json = %s WHERE id = %s",
                    (json.dumps(d, ensure_ascii=False), int(revisao_id)))
    return feitos


# ------------------------------------------------------------------ a certidão

def conferir_para_emitir(con, pasta_dados: Path, raiz: Path, matricula_id: int, *,
                         justificativa: str = "") -> dict:
    """Diz se a certidão de inteiro teor (ou a reprográfica) pode sair, e
    como. SÓ LÊ — é a conferência de ANTES, que recusa cedo, antes de montar
    o papel. Dentro da transação que numera, `reconferir_na_emissao` aplica a
    mesma régua com a linha da revisão presa, e quem grava a decisão dela é
    `gravar_na_certidao`.

    Devolve `{"situacao": ...}`: DESLIGADA (sem IA nesta casa: a etapa não
    existe), SEM_TEXTO (ficha sem transcrição), SEM_REVISAO, ERRO (a IA não
    respondeu) ou PRONTA. RECUSA (`TranscricaoPendente`) só em dois casos: a
    leitura ainda em andamento, e a divergência GRAVE não resolvida sem
    justificativa de dez letras. Com a etapa, a decisão leva `hash_texto` e
    `hash_paginas` — o texto e as páginas que ela leu, e que a reconferência
    usa sem abrir arquivo nenhum."""
    bd = banco(con)
    if not ligada(bd, pasta_dados):
        return {"situacao": "DESLIGADA"}
    try:
        ficha = texto_da_ficha(bd, matricula_id)
    except TranscricaoError:
        return {"situacao": "SEM_TEXTO"}
    if not ficha["texto"].strip():
        return {"situacao": "SEM_TEXTO"}
    paginas = paginas_da_ficha(bd, raiz, matricula_id)
    lido = {"hash_texto": hash_do_texto(ficha["texto"]),
            "hash_paginas": hash_das_paginas(paginas)}
    r = vigente(bd, raiz, matricula_id, ficha=ficha, paginas=paginas)["vale"]
    return _decidir(r, justificativa) | lido


def reconferir_na_emissao(con, decisao: dict | None, *, matricula_id: int,
                          justificativa: str = "") -> dict | None:
    """A régua outra vez, DENTRO da transação que numera a certidão e ANTES
    do número, com a linha da revisão presa (`FOR UPDATE`). É a decisão daqui
    que `gravar_na_certidao` grava, e a recusa daqui vem antes do número e do
    selo, como a de antes. Não grava nada: só prende a linha.

    POR QUE DUAS VEZES (LH12, a ressalva 2 da revisão do LH11). A conferência
    de antes lê numa conexão à parte, sem prender nada. Entre ela e o número,
    a divergência pode ser dada por conferida no livro, e a leitura que passou
    de 15 minutos (que a tela já mostra como ERRO) pode terminar com GRAVE: a
    certidão sairia pela decisão velha, e `ri_transcricao_emissoes` gravaria
    as graves da hora da leitura. Com a linha presa, quem dá a divergência por
    conferida (`conferir_divergencias`, que também a prende) espera a certidão
    sair, ou a certidão espera por ele — e a conta gravada é a lida aqui.

    NÃO RELÊ O TEXTO NEM AS PÁGINAS: abrir arquivo da digitalização dentro da
    transação que segura o número pararia o balcão. Vale a revisão do texto e
    das páginas que a conferência de antes leu (os `hash_*` da decisão).

    QUEM CHAMA JÁ TEM A TRAVA DO NÚMERO, E CHAMA NUM SAVEPOINT (LH15). A trava
    de assunto (`ri_certidoes.numero`) vem antes da linha, a ordem da casa; e o
    erro de banco aqui (a linha presa além do `lock_timeout`, o deadlock) não
    pode condenar a transação que numera — `ri_emitir_certidao` o roda em
    `bd.ponto_de_retorno`, e a certidão sai «sem revisão».

    Sem a etapa (DESLIGADA, SEM_TEXTO), ou com a conferência de antes
    quebrada (a decisão sem os `hash_*`), não há o que reconferir: a decisão
    volta como veio."""
    if not decisao or not decisao.get("hash_texto"):
        return decisao
    lido = {"hash_texto": decisao["hash_texto"], "hash_paginas": decisao["hash_paginas"]}
    bd = banco(con)
    bd._escrita()
    linha = bd.um(_SQL_DA_VIGENTE + " FOR UPDATE",
                  (int(matricula_id), lido["hash_texto"], lido["hash_paginas"]))
    return _decidir(mostrar(bd, linha["id"]) if linha else None, justificativa) | lido


def _decidir(r: dict | None, justificativa: str) -> dict:
    """A régua da emissão sobre a revisão que vale (como `mostrar` a dá), ou
    sobre nenhuma. É uma só para a conferência de antes e para a de dentro da
    transação. SÓ LÊ; recusa com `TranscricaoPendente`."""
    if r is None:
        return {"situacao": "SEM_REVISAO", "revisao_id": None,
                "recado": "ninguém pediu a revisão deste texto (ou ele mudou depois dela)"}
    if r["situacao"] in (PENDENTE, LENDO):
        raise TranscricaoPendente(
            "A revisão da transcrição ainda está lendo a ficha. Espere o resultado "
            "aparecer no quadro da certidão e emita em seguida (se a IA não responder em "
            f"{MINUTOS_PARA_DESISTIR} minutos, a certidão sai sem ela).",
            revisao_id=r["id"])
    if r["situacao"] == ERRO:
        return {"situacao": "ERRO", "revisao_id": r["id"],
                "recado": "a IA não respondeu"}
    pendentes = graves_pendentes(r)
    if not pendentes:
        return {"situacao": PRONTA, "revisao_id": r["id"], "graves_pendentes": 0}
    texto = " ".join((justificativa or "").split())
    if len(texto) < MINIMO_DA_JUSTIFICATIVA:
        raise TranscricaoPendente(
            f"A revisão da transcrição apontou {pendentes} divergência(s) GRAVE(S) entre "
            "o texto e a página, ainda não resolvida(s). Confira no livro: se o texto "
            "estiver errado, corrija-o pelo caminho de correção e revise de novo; se ele "
            "estiver certo, escreva por que a certidão sai assim mesmo (mínimo de dez "
            "letras) — a justificativa fica gravada com a certidão.",
            graves=pendentes, revisao_id=r["id"])
    return {"situacao": PRONTA, "revisao_id": r["id"], "graves_pendentes": pendentes,
            "justificativa": texto}


def gravar_na_certidao(con, decisao: dict | None, *, certidao_id: int, matricula_id: int,
                       usuario: str = "") -> None:
    """Grava em que pé estava a revisão quando a certidão saiu — a decisão de
    `reconferir_na_emissao`, lida com a linha presa. ESCREVE, na transação da
    emissão. Sem IA ou sem transcrição não há o que gravar.

    NÃO CRIA A TABELA (LH12): ela nasce na subida (`init_schema`). Aqui o DDL
    viria depois do número, na transação que o segura, e prenderia a trava do
    catálogo até o fim dela — na primeira certidão, que é quando a tabela
    ainda faltava."""
    if not decisao or decisao.get("situacao") in ("DESLIGADA", "SEM_TEXTO"):
        return
    bd = banco(con)
    bd.escrever(
        """INSERT INTO ri_transcricao_emissoes (certidao_id, matricula_id, revisao_id,
               situacao, graves_pendentes, justificativa, emitida_por, emitida_em)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
        (int(certidao_id), int(matricula_id), decisao.get("revisao_id"),
         decisao["situacao"], int(decisao.get("graves_pendentes") or 0),
         decisao.get("justificativa") or None, usuario or None, _agora()))


def recado_da_emissao(decisao: dict | None) -> str:
    """A frase que a tela acrescenta depois de emitir: a certidão saiu sem a
    revisão, ou com a justificativa. Vazia quando a etapa não existe."""
    if not decisao:
        return ""
    situacao = decisao.get("situacao")
    if situacao in ("SEM_REVISAO", "ERRO"):
        return (" A certidão saiu SEM a revisão da transcrição pela IA ("
                f"{decisao.get('recado') or 'sem revisão'}).")
    if situacao == PRONTA and decisao.get("justificativa"):
        return (f" A revisão da transcrição apontou {decisao['graves_pendentes']} "
                "divergência(s) grave(s); a justificativa ficou gravada com a certidão.")
    return ""


# ------------------------------------------------------------------ a estimativa

def chamadas_previstas(paginas: int) -> int:
    """Quantas chamadas ao provedor uma ficha custa: duas páginas por chamada,
    e a ficha sem página legível ainda faz uma (só o texto)."""
    return max(1, math.ceil(min(int(paginas or 0), TETO_DE_PAGINAS_POR_FICHA)
                            / PAGINAS_POR_PEDIDO))


def media_por_chamada(con) -> dict:
    """Os tokens médios de uma chamada desta revisão, MEDIDOS no `ia_uso` —
    ou o piso a priori, enquanto não há uso. SÓ LÊ."""
    bd = banco(con)
    if bd.tem_tabela("ia_uso"):
        r = bd.um("""SELECT count(*) AS n, avg(tokens_entrada)::float8 AS entrada,
                            avg(tokens_saida)::float8 AS saida
                       FROM ia_uso WHERE finalidade = %s AND resultado = 'ok'""",
                  ("revisao_transcricao",))
        if r and int(r["n"] or 0) > 0:
            return {"entrada": float(r["entrada"]), "saida": float(r["saida"]),
                    "medido": int(r["n"])}
    return {"entrada": float(TOKENS_DE_ENTRADA_A_PRIORI),
            "saida": float(TOKENS_DE_SAIDA_A_PRIORI), "medido": 0}


def estimativa(con, paginas_por_ficha: list[int]) -> dict:
    """O custo previsto para revisar estas fichas. SÓ LÊ."""
    media = media_por_chamada(con)
    chamadas = sum(chamadas_previstas(n) for n in paginas_por_ficha)
    return {"fichas": len(paginas_por_ficha), "paginas": sum(paginas_por_ficha),
            "chamadas": chamadas, "medido": media["medido"],
            "custo": chamadas * custo(MODELO, round(media["entrada"]),
                                      round(media["saida"]))}
