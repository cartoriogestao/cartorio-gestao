"""O envio do cadastro de pessoas ao CCN — o lote, a ponte e o resultado.

    «vamos construir o submodulo de envio para o CCN e assinador a3
     acessorio» — o oficial, 13/10/2026

O QUE O CCN É, E O QUE ESTE MÓDULO FAZ
    O Cadastro Único de Clientes do Notariado (Prov. CNJ 149/2023, art. 166)
    recebe o cadastro das pessoas que a casa atende, em até 15 dias da
    abertura ou da atualização. No vocabulário do CNB, mandar daqui para lá
    é **importar** (`CcnPessoaFisica`). Esta casa guarda o cadastro no cartão
    de firma (`nt_cartoes`) — não há tabela de pessoas nas Notas.

    Este módulo diz quem falta mandar, transforma cada cartão no cadastro do
    CCN, junta num lote e guarda o que o CCN respondeu. **Ele não fala com o
    CCN**, e a razão está medida (`DOCUMENTACAO/O_CCN_E_AS_DUAS_PAREDES.md`):
    o host da API está atrás de um desafio da Cloudflare que só um navegador
    passa. Quem envia é a extensão «CG CCN Assistente», NA ABA em que o
    escrevente já entrou no portal — decisão do oficial de 05/10/2026
    (`CCN_FLUXO_ACESSO_MANUAL_ENVIO_ABA.md`).

A PONTE ENTRE O LOTE E A EXTENSÃO
    A extensão não tem a sessão do Cartório Gestão, e não deve ter. Cada lote
    tem um **código de envio** (HMAC do número do lote com a chave secreta da
    instalação): quem o digita na extensão recebe AQUELE lote, e devolve o
    resultado dele. A rota só responde a quem está na própria máquina
    (127.0.0.1) — é lá que o navegador do envio roda.

O QUE NÃO SE INVENTA
    O formato do arquivo é o XSD v4 do CNB (`ccn_xml.py`). O que o cartão não
    diz vai em branco, e o que a casa grava de um jeito que o CCN não aceita —
    celular sem DDD, nacionalidade estrangeira sem a tabela de países do CNB —
    **não vai**, e aparece na lista do que ficou de fora.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import sqlite3
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

SCHEMA = """
CREATE TABLE IF NOT EXISTS nt_ccn_lotes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ambiente TEXT NOT NULL,                  -- HOMOLOGACAO | PRODUCAO
    situacao TEXT NOT NULL DEFAULT 'GERADO', -- GERADO | ENVIADO | CONCLUIDO | COM_ERROS | FALHOU | DESCARTADO
    arquivo_nome TEXT NOT NULL,
    caminho TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    bytes INTEGER NOT NULL,
    quantidade INTEGER NOT NULL,
    gerado_em TEXT NOT NULL,
    gerado_por TEXT,
    upload_id TEXT,
    import_id TEXT,
    import_status TEXT,
    processados INTEGER,
    falhas INTEGER,
    resposta_json TEXT,
    enviado_em TEXT,
    concluido_em TEXT,
    erro TEXT,
    descartado_motivo TEXT
);
CREATE TABLE IF NOT EXISTS nt_ccn_itens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lote_id INTEGER NOT NULL REFERENCES nt_ccn_lotes(id),
    cartao_id INTEGER NOT NULL REFERENCES nt_cartoes(id),
    cpf TEXT NOT NULL,
    versao TEXT NOT NULL,                    -- sha256 do cadastro como foi enviado
    posicao INTEGER NOT NULL,                -- ordem no arquivo (o CCN devolve erro por posição)
    situacao TEXT NOT NULL DEFAULT 'NO_LOTE',-- NO_LOTE | ACEITO | RECUSADO | DUPLICADO
    erro TEXT,
    UNIQUE(lote_id, cartao_id)
);
CREATE INDEX IF NOT EXISTS ix_nt_ccn_itens_cartao ON nt_ccn_itens(cartao_id, situacao);
"""

AMBIENTES = {
    "HOMOLOGACAO": "pessoas-hml.e-notariado.org.br",
    "PRODUCAO": "pessoas.e-notariado.org.br",
}
#: A documentação do CNB põe o teto em 30.000 KB por requisição; o multipart
#: soma cabeçalhos ao arquivo, e por isso o lote para antes.
LIMITE_DO_ARQUIVO = 25_000_000
PRAZO_DO_PROVIMENTO_DIAS = 15                 # Prov. CNJ 149/2023, art. 166, § 1º
STATUS_FINAIS = {"Successful", "CompletedWithErrors", "Error", "Halted"}

#: O estado civil da casa → o domínio do CCN (documentação técnica, «Tabelas
#: Domínio»). A casa escreve de várias formas (medido em 13/10/2026:
#: «Solteiro(a)», «SOLTEIRO(A)», «Viúvo(a)» …); compara-se sem acento e caixa.
ESTADO_CIVIL = {
    "SOLTEIRO": "Solteiro", "CASADO": "Casado",
    "SEPARADO JUDICIALMENTE": "SeparadoJudicialmente", "DIVORCIADO": "Divorciado",
    "VIUVO": "Viuvo", "UNIAO ESTAVEL": "UniaoEstavel", "DESQUITADO": "Desquitado",
    "SEPARADO EXTRAJUDICIALMENTE": "SeparadoExtrajudicialmente",
    # no feminino, como a casa também escreve (medido em 13/10/2026: «CASADA»,
    # «SOLTEIRA», «VIUVA»)
    "SOLTEIRA": "Solteiro", "CASADA": "Casado", "DIVORCIADA": "Divorciado", "VIUVA": "Viuvo",
    "SEPARADA JUDICIALMENTE": "SeparadoJudicialmente", "DESQUITADA": "Desquitado",
    "SEPARADA EXTRAJUDICIALMENTE": "SeparadoExtrajudicialmente",
}


class CcnError(ValueError):
    """Erro de regra do envio ao CCN, com a frase pronta para o balcão."""


# ----------------------------------------------------------------- utilidades

def init_schema(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA)


def tem_tabelas(con: sqlite3.Connection) -> bool:
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                       "AND name='nt_ccn_lotes'").fetchone() is not None


def _norm(texto: Any) -> str:
    t = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^A-Za-z0-9 ]", " ", t).upper().split())


def _digitos(texto: Any) -> str:
    return re.sub(r"\D", "", str(texto or ""))


def cpf_valido(documento: Any) -> str | None:
    """O CPF com 11 dígitos e dígitos verificadores certos, ou None."""
    d = _digitos(documento)
    if len(d) != 11 or d == d[0] * 11:
        return None
    for n in (9, 10):
        soma = sum(int(d[i]) * (n + 1 - i) for i in range(n))
        dv = (soma * 10) % 11 % 10
        if dv != int(d[n]):
            return None
    return d


def _data(texto: Any) -> str | None:
    t = str(texto or "").strip()[:10]
    try:
        return datetime.strptime(t, "%Y-%m-%d").date().isoformat()
    except ValueError:
        return None


def _estado_civil(texto: Any) -> str | None:
    t = re.sub(r"\bA\b", "", _norm(texto)).strip()       # «SOLTEIRO A» de «SOLTEIRO(A)»
    t = " ".join(t.split())
    return ESTADO_CIVIL.get(t)


def _celular(texto: Any) -> str | None:
    """+55DDNNNNNNNNN. Sem DDD não vai: o DDD não se adivinha."""
    d = _digitos(texto)
    if d.startswith("55") and len(d) in (12, 13):
        d = d[2:]
    if len(d) in (10, 11):
        return "+55" + d
    return None


def _municipio(con: sqlite3.Connection, nome: Any, uf: Any) -> int | None:
    if not nome or not uf:
        return None
    try:
        linha = con.execute("SELECT codigo_ibge FROM ib_municipios WHERE uf=? AND nome_norm=?",
                            (str(uf).upper(), _norm(nome).lower())).fetchone()
    except sqlite3.Error:
        return None
    return int(linha[0]) if linha else None


def _cidade_e_uf(texto: Any) -> tuple[str | None, str | None]:
    """«CIDADE EXEMPLO/MA» → ('CIDADE EXEMPLO', 'MA'); sem barra, a UF não se deduz."""
    t = str(texto or "").strip()
    if not t:
        return None, None
    m = re.match(r"^(.*?)\s*[/\-]\s*([A-Za-z]{2})\.?$", t)
    if m:
        return m.group(1).strip() or None, m.group(2).upper()
    return t, None


# ----------------------------------------------------------------- o cadastro

def pessoa_do_cartao(con: sqlite3.Connection, cartao: dict, pasta_arquivos: Path) -> dict:
    """O cartão de firma no vocabulário do CCN. Só LÊ.

    Devolve `{"campos": {...}, "imagens": {...}, "fora": [...]}`: `campos` são
    os dados com o nome da documentação técnica do CNB; `imagens` são caminhos
    em disco (o arquivo só é lido quando o lote é montado); `fora` é o que a
    casa tem e não foi, com o motivo.
    """
    c = dict(cartao)
    fora: list[str] = []
    cpf = cpf_valido(c.get("documento"))
    if not cpf:
        raise CcnError(f"cartão {c.get('id')}: sem CPF válido — o CCN exige CPF e nome")
    nome = " ".join(str(c.get("nome") or "").split())
    if not nome:
        raise CcnError(f"cartão {c.get('id')}: sem nome — o CCN exige CPF e nome")

    campos: dict[str, Any] = {"cpf": cpf, "nome": nome,
                              "dataRegistro": _data(c.get("abertura") or c.get("criado_em"))}
    if (c.get("sexo") or "").upper() in ("M", "F"):
        campos["sexo"] = c["sexo"].upper()
    ec = _estado_civil(c.get("estado_civil"))
    if ec:
        campos["estadoCivil"] = ec
    elif c.get("estado_civil"):
        fora.append(f"estado civil «{c['estado_civil']}» não tem par no domínio do CCN")
    nac = _norm(c.get("nacionalidade"))
    if nac.startswith("BRASIL"):
        campos["nacionalidade"] = "BRASIL"
        campos["nacionalidadeTipo"] = "Brasileiro Nato"
    elif nac:
        # A tabela de países do CNB (anexo «Tabela Países.xlsx») não está na
        # casa, e o tipo (nato, naturalizado) o cartão não guarda.
        fora.append(f"nacionalidade «{c['nacionalidade']}» — falta a tabela de países do CNB")
    cid, uf = _cidade_e_uf(c.get("naturalidade"))
    if cid:
        ibge = _municipio(con, cid, uf)
        if ibge:
            campos["ibgeCidadeNaturalidade"] = str(ibge)
        campos["cidadeNaturalidade"] = cid
        if uf:
            campos["ufNaturalidade"] = uf
    for chave, coluna in (("mae", "mae"), ("pai", "pai"), ("profissao", "profissao"),
                          ("email", "email")):
        valor = " ".join(str(c.get(coluna) or "").split())
        if valor:
            campos[chave] = valor
    nasc = _data(c.get("nascimento"))
    if nasc:
        campos["dataNascimento"] = nasc
    cel = _celular(c.get("celular"))
    if cel:
        campos["celular"] = cel
    elif c.get("celular"):
        fora.append("celular sem DDD — não se adivinha o DDD")
    tel = _celular(c.get("telefone"))
    if tel:
        campos["telefone"] = tel

    end = {k: " ".join(str(c.get(col) or "").split()) or None for k, col in
           (("endereco", "endereco"), ("numero", "endereco_numero"),
            ("complemento", "endereco_complemento"), ("bairro", "bairro"),
            ("cidade", "cidade"), ("uf", "uf"))}
    cep = _digitos(c.get("cep"))
    end["cep"] = cep if len(cep) == 8 else None
    ibge = _municipio(con, end["cidade"], end["uf"])
    end["ibgeCidade"] = str(ibge) if ibge else None
    if any(end.values()):
        campos["endereco"] = {k: v for k, v in end.items() if v}
        if not end["ibgeCidade"]:
            # O XSD v4 EXIGE ibgeCidade dentro de <endereco>.
            fora.append("endereço sem código IBGE da cidade — o CCN exige; não vai")

    if c.get("rg"):
        campos["documento"] = {k: v for k, v in {
            "tipo": "RG", "docIdentidade": str(c["rg"]).strip(),
            "orgaoEmissor": (c.get("rg_orgao") or "").strip() or None,
            "ufOrgaoEmissor": (c.get("rg_uf") or "").strip().upper() or None,
            "dataEmissao": _data(c.get("rg_emissao")),
        }.items() if v}
    if campos.get("documento") and not campos["documento"].get("dataEmissao"):
        # O XSD v4 EXIGE docIdentidade, orgaoEmissor e dataEmissao; a data de
        # emissão do RG está vazia em 4.098 de 4.098 cartões (13/10/2026).
        fora.append("RG sem data de emissão (ou sem órgão) — o CCN exige; não vai")
    campos["politicamenteexposta"] = bool(c.get("pessoa_exposta"))
    campos["investigadaAcusadaTerrorismo"] = bool(c.get("restricao_terrorismo"))
    campos["fichaBloqueada"] = bool(c.get("bloqueado"))
    if c.get("bloqueado") and c.get("motivo_bloqueio"):
        campos["observacao"] = str(c["motivo_bloqueio"]).strip()

    imagens: dict[str, Any] = {"ficha": [], "foto": None, "digitais": []}
    for img in con.execute(
            """SELECT caminho_interno, caminho, nome_arquivo FROM nt_cartao_imagens
                WHERE cartao_id=? ORDER BY COALESCE(favorita,0) DESC, ordem, id""", (c["id"],)):
        arq = _arquivo(pasta_arquivos, img[0], img[1], img[2])
        if arq:
            imagens["ficha"].append(str(arq))
        else:
            fora.append(f"imagem da ficha «{img[2]}» não está no disco")
    if con.execute("SELECT 1 FROM sqlite_master WHERE name='nt_cadastro_imagens'").fetchone():
        for esp, dedo, caminho, presencial in con.execute(
                """SELECT especie, dedo, caminho, presencial FROM nt_cadastro_imagens
                    WHERE cartao_id=? ORDER BY especie, dedo""", (c["id"],)):
            if not Path(caminho).is_file():
                fora.append(f"{esp.lower()} cadastrada e o arquivo não está no disco")
            elif esp == "FOTO":
                imagens["foto"] = {"caminho": caminho, "verificada": bool(presencial)}
            elif esp == "DIGITAL" and dedo:
                imagens["digitais"].append({"dedo": int(dedo), "caminho": caminho})
    if not imagens["ficha"]:
        fora.append("ficha de firma sem imagem — o CCN exige a imagem; não vai")
    campos["ficha"] = {k: v for k, v in {
        "dataficha": _data(c.get("abertura")),
        "numeroFicha": str(c["numero"]) if c.get("numero") else None,
    }.items() if v}
    return {"cartao_id": c["id"], "cpf": cpf, "campos": campos, "imagens": imagens,
            "fora": fora}


def _arquivo(pasta_arquivos: Path, interno: Any, pasta: Any, nome: Any) -> Path | None:
    for cand in ([pasta_arquivos / str(interno)] if interno else []) + \
                ([Path(str(pasta)) / str(nome)] if pasta and nome else []):
        if cand.is_file():
            return cand
    return None


def versao(pessoa: dict) -> str:
    """O cadastro como impressão digital: mudou um campo ou uma imagem, mudou a versão.

    As imagens entram pelo conteúdo (sha256 do arquivo), e não pelo caminho —
    a foto refeita com o mesmo nome de arquivo é cadastro novo para o CCN.
    """
    def _sha(caminho):
        try:
            return hashlib.sha256(Path(caminho).read_bytes()).hexdigest()
        except OSError:
            return None
    img = pessoa["imagens"]
    corpo = {"campos": pessoa["campos"],
             "ficha": [_sha(p) for p in img["ficha"]],
             "foto": _sha(img["foto"]["caminho"]) if img.get("foto") else None,
             "digitais": [(d["dedo"], _sha(d["caminho"])) for d in img["digitais"]]}
    return hashlib.sha256(json.dumps(corpo, sort_keys=True, ensure_ascii=False)
                          .encode("utf-8")).hexdigest()


# ----------------------------------------------------------------- quem falta

def _cartoes_candidatos(con: sqlite3.Connection) -> list[dict]:
    """Um cartão por CPF — o mais recente —, pessoa física e ativo."""
    con.row_factory = sqlite3.Row
    por_cpf: dict[str, dict] = {}
    for r in con.execute("""SELECT * FROM nt_cartoes
                             WHERE COALESCE(tipo_pessoa,'F')='F' AND COALESCE(ativo,1)=1
                          ORDER BY COALESCE(atualizado_em, criado_em, abertura), id"""):
        cpf = cpf_valido(r["documento"])
        if cpf:
            por_cpf[cpf] = dict(r)
    return list(por_cpf.values())


def _ultimo_aceito(con: sqlite3.Connection, ambiente: str) -> dict[int, str]:
    if not tem_tabelas(con):
        return {}
    return {r[0]: r[1] for r in con.execute(
        """SELECT i.cartao_id, i.versao FROM nt_ccn_itens i
             JOIN nt_ccn_lotes l ON l.id = i.lote_id
            WHERE i.situacao IN ('ACEITO','DUPLICADO') AND l.ambiente = ?
         ORDER BY i.id""", (ambiente,))}


def resumo(con: sqlite3.Connection, ambiente: str = "PRODUCAO") -> dict:
    """Os números do painel. Só LÊ, e não lê imagem nenhuma."""
    con.row_factory = sqlite3.Row
    cands = _cartoes_candidatos(con)
    total = con.execute("SELECT count(*) FROM nt_cartoes").fetchone()[0]
    aceitos = set()
    if tem_tabelas(con):
        aceitos = {r[0] for r in con.execute(
            """SELECT DISTINCT i.cartao_id FROM nt_ccn_itens i JOIN nt_ccn_lotes l
                 ON l.id=i.lote_id WHERE i.situacao IN ('ACEITO','DUPLICADO')
                AND l.ambiente=?""", (ambiente,))}
    return {"cartoes": total, "com_cpf": len(cands),
            "sem_cpf": total - len(cands),
            "nunca_enviados": sum(1 for c in cands if c["id"] not in aceitos),
            "ambiente": ambiente}


def lotes(con: sqlite3.Connection, limite: int = 50) -> list[dict]:
    if not tem_tabelas(con):
        return []
    con.row_factory = sqlite3.Row
    return [dict(r) for r in con.execute(
        "SELECT * FROM nt_ccn_lotes ORDER BY id DESC LIMIT ?", (limite,))]


# ----------------------------------------------------------------- o lote

def gerar_lote(con: sqlite3.Connection, pasta_dados: Path, *, ambiente: str,
               usuario: str, agora: str, montar: Callable[[list[dict]], bytes],
               maximo: int = 500, cartao_ids: list[int] | None = None,
               limite_bytes: int = LIMITE_DO_ARQUIVO) -> dict:
    """Junta os pendentes num arquivo e o grava em disco. ESCREVE (chame em transação).

    `montar` é `ccn_xml.montar` — recebido, para o lote não depender de qual
    versão do XSD está valendo. O arquivo para antes do teto: quem não coube
    fica para o próximo lote, e não é cortado do arquivo pela metade.
    """
    if ambiente not in AMBIENTES:
        raise CcnError(f"ambiente desconhecido: {ambiente}")
    init_schema(con)
    aceito = _ultimo_aceito(con, ambiente)
    em_aberto = {r[0] for r in con.execute(
        """SELECT i.cartao_id FROM nt_ccn_itens i JOIN nt_ccn_lotes l ON l.id=i.lote_id
            WHERE l.situacao IN ('GERADO','ENVIADO') AND l.ambiente=?""", (ambiente,))}
    pasta_arquivos = pasta_dados / "arquivos"
    escolhidos, ficaram_fora = [], []
    for c in _cartoes_candidatos(con):
        if cartao_ids is not None and c["id"] not in cartao_ids:
            continue
        if c["id"] in em_aberto:
            continue
        p = pessoa_do_cartao(con, c, pasta_arquivos)
        p["versao"] = versao(p)
        if aceito.get(c["id"]) == p["versao"]:
            continue
        escolhidos.append(p)
        if len(escolhidos) >= maximo:
            break
    if not escolhidos:
        raise CcnError("nenhum cadastro pendente de envio neste ambiente")

    # Corta pelo tamanho: monta, mede, e tira do fim o que passou do teto.
    while True:
        conteudo = montar(escolhidos)
        if len(conteudo) <= limite_bytes or len(escolhidos) == 1:
            break
        corte = max(1, int(len(escolhidos) * limite_bytes / len(conteudo) * 0.95))
        ficaram_fora.extend(escolhidos[corte:])
        escolhidos = escolhidos[:corte]
    if len(conteudo) > limite_bytes:
        raise CcnError("o cadastro de uma pessoa sozinho passa do teto de 30.000 KB do "
                       "CCN — confira o tamanho das imagens da ficha")

    sha = hashlib.sha256(conteudo).hexdigest()
    nome = f"CCN{agora[:10].replace('-', '')}-{sha[:8]}.xml"
    destino = pasta_dados / "arquivos" / "notas" / "ccn" / nome
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(conteudo)
    lote_id = con.execute(
        """INSERT INTO nt_ccn_lotes (ambiente, arquivo_nome, caminho, sha256, bytes,
               quantidade, gerado_em, gerado_por) VALUES (?,?,?,?,?,?,?,?)""",
        (ambiente, nome, str(destino), sha, len(conteudo), len(escolhidos), agora,
         usuario)).lastrowid
    for pos, p in enumerate(escolhidos):
        con.execute("""INSERT INTO nt_ccn_itens (lote_id, cartao_id, cpf, versao, posicao)
                       VALUES (?,?,?,?,?)""", (lote_id, p["cartao_id"], p["cpf"], p["versao"], pos))
    return {"lote_id": lote_id, "quantidade": len(escolhidos), "bytes": len(conteudo),
            "arquivo": nome, "ficaram_para_o_proximo": len(ficaram_fora),
            "fora": {p["cpf"]: p["fora"] for p in escolhidos if p["fora"]}}


def descartar(con: sqlite3.Connection, lote_id: int, motivo: str, agora: str) -> None:
    """Lote que não vai ser enviado. Não apaga nada: o arquivo e as linhas ficam."""
    texto = " ".join((motivo or "").split())
    if len(texto) < 10:
        raise CcnError("escreva o motivo do descarte (dez letras, pelo menos)")
    r = con.execute("SELECT situacao FROM nt_ccn_lotes WHERE id=?", (lote_id,)).fetchone()
    if r is None:
        raise CcnError("lote não encontrado")
    if r[0] != "GERADO":
        raise CcnError("só se descarta lote que ainda não foi enviado")
    con.execute("""UPDATE nt_ccn_lotes SET situacao='DESCARTADO', descartado_motivo=?,
                       concluido_em=? WHERE id=?""", (texto, agora, lote_id))


# ----------------------------------------------------------------- a ponte

def codigo_do_lote(segredo: str, lote_id: int) -> str:
    """O código que o escrevente digita na extensão. Derivado, e não guardado."""
    mac = hmac.new(str(segredo).encode("utf-8"), f"ccn-lote:{int(lote_id)}".encode(),
                   hashlib.sha256).hexdigest()
    return f"{int(lote_id)}-{mac[:10].upper()}"


def lote_pelo_codigo(con: sqlite3.Connection, segredo: str, codigo: str) -> dict:
    """O lote que aquele código abre — ou recusa. Só LÊ."""
    m = re.fullmatch(r"\s*(\d+)-([0-9A-Fa-f]{10})\s*", str(codigo or ""))
    if not m or not hmac.compare_digest(codigo_do_lote(segredo, int(m.group(1))),
                                        f"{int(m.group(1))}-{m.group(2).upper()}"):
        raise CcnError("código de envio não confere — copie de novo da tela do lote")
    if not tem_tabelas(con):
        raise CcnError("lote não encontrado")
    con.row_factory = sqlite3.Row
    r = con.execute("SELECT * FROM nt_ccn_lotes WHERE id=?", (int(m.group(1)),)).fetchone()
    if r is None:
        raise CcnError("lote não encontrado")
    return dict(r)


def registrar_resultado(con: sqlite3.Connection, lote: dict, dados: dict, agora: str) -> dict:
    """O que a extensão viu do CCN, gravado no lote e nos itens. ESCREVE.

    `dados`: `{"upload": {...}, "import": {...ImportModel}, "erros": [FailedImportModel],
    "erro": "texto"}`. **O status vem do CCN, e só ele fecha o lote**: `Successful`
    aceita todos; `CompletedWithErrors` aceita os que não estão na lista de erros
    (que vem POR POSIÇÃO no arquivo); `Error`/`Halted` não aceita ninguém.
    """
    if lote["situacao"] in ("CONCLUIDO", "DESCARTADO"):
        raise CcnError(f"o lote {lote['id']} já está {lote['situacao'].lower()}")
    imp = dados.get("import") or {}
    up = dados.get("upload") or {}
    status = imp.get("status")
    situacao = lote["situacao"]
    if dados.get("erro") and not imp:
        situacao = "FALHOU"
    elif imp:
        situacao = "ENVIADO"
    if status in STATUS_FINAIS:
        situacao = {"Successful": "CONCLUIDO", "CompletedWithErrors": "COM_ERROS"}.get(status, "FALHOU")
    con.execute(
        """UPDATE nt_ccn_lotes SET situacao=?, upload_id=COALESCE(?,upload_id),
               import_id=COALESCE(?,import_id), import_status=COALESCE(?,import_status),
               processados=COALESCE(?,processados), falhas=COALESCE(?,falhas),
               resposta_json=?, enviado_em=COALESCE(enviado_em,?),
               concluido_em=CASE WHEN ? THEN ? ELSE concluido_em END, erro=?
         WHERE id=?""",
        (situacao, up.get("id"), imp.get("id"), status, imp.get("processedRecords"),
         imp.get("failedRecords"), json.dumps(dados, ensure_ascii=False)[:200_000], agora,
         status in STATUS_FINAIS, agora, (dados.get("erro") or None), lote["id"]))
    aceitos = recusados = duplicados = 0
    if status in STATUS_FINAIS:
        por_posicao = {}
        for e in dados.get("erros") or []:
            msgs = "; ".join(str(x.get("message") or x.get("code") or "")
                             for x in (e.get("errors") or [])) or e.get("errorCode") or "erro"
            por_posicao[e.get("position")] = (msgs, str(e.get("identifier") or ""))
        dup = {str(d.get("cpf")) for d in (imp.get("duplicateRecords") or [])}
        for item_id, pos, cpf in con.execute(
                "SELECT id, posicao, cpf FROM nt_ccn_itens WHERE lote_id=?", (lote["id"],)).fetchall():
            # A documentação não diz se a posição começa em 0 ou em 1; casa-se
            # pela posição E pelo CPF quando o CCN devolve o identificador.
            erro = next((m for p, (m, ident) in por_posicao.items()
                         if (ident and ident == cpf) or (not ident and p in (pos, pos + 1))), None)
            if status in ("Error", "Halted"):
                novo, msg = "RECUSADO", f"importação {status}"
            elif erro:
                novo, msg = "RECUSADO", erro
            elif cpf in dup:
                novo, msg = "DUPLICADO", "o CCN já tinha este cadastro igual"
            else:
                novo, msg = "ACEITO", None
            con.execute("UPDATE nt_ccn_itens SET situacao=?, erro=? WHERE id=?",
                        (novo, msg, item_id))
            aceitos += novo == "ACEITO"
            recusados += novo == "RECUSADO"
            duplicados += novo == "DUPLICADO"
    return {"situacao": situacao, "status": status, "aceitos": aceitos,
            "recusados": recusados, "duplicados": duplicados}


def para_a_extensao(lote: dict, codigo: str) -> dict:
    """O que a extensão recebe para enviar AQUELE lote. Lê o arquivo do disco."""
    if lote["situacao"] not in ("GERADO", "ENVIADO", "FALHOU"):
        raise CcnError(f"o lote {lote['id']} está {lote['situacao'].lower()} — nada a enviar")
    conteudo = Path(lote["caminho"]).read_bytes()
    if hashlib.sha256(conteudo).hexdigest() != lote["sha256"]:
        raise CcnError("o arquivo do lote mudou no disco depois de gerado — gere outro lote")
    import base64
    return {"lote_id": lote["id"], "codigo": codigo, "ambiente": lote["ambiente"],
            "host": AMBIENTES[lote["ambiente"]], "arquivo_nome": lote["arquivo_nome"],
            "quantidade": lote["quantidade"], "bytes": lote["bytes"],
            "import_id": lote.get("import_id"),
            "conteudo_b64": base64.b64encode(conteudo).decode("ascii"),
            "tipo": "CcnPessoaFisica", "content_type": "text/xml"}
