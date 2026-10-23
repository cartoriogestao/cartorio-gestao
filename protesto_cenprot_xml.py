"""O XML diário que a serventia sobe à CENPROT — escrito, e não só lido.

Pedido do oficial, 15/10/2026: «vamos criar o gerador de arquivo e assinar com
o certificado». Até aqui `DOCUMENTACAO/CENPROT_XML_MEDIDO.md` dizia que ele
«não se constrói», porque a chave única de título novo não se compõe. **A
amostra que o oficial trouxe (28 arquivos desta casa, 66 títulos, pasta
`9. CENPROT\\ARQUIVO XML`) resolveu isso pelo outro lado:** a casa NÃO manda
apontamento — manda só dois arquivos, e os dois falam de título que JÁ TEM a
chave (ela vem da CENPROT, e a tela «Chave do CENPROT» a grava):

    P — os protestos lavrados (ocorrência 2), com o INSTRUMENTO ELETRÔNICO
        assinado dentro, em base64;
    D — o que saiu do protesto ou do apontamento: pago (1), retirado (3),
        cancelado (A, com `data_averbacao`).

**O XML NÃO É ASSINADO — O INSTRUMENTO É.** Medido nos 44 instrumentos da
amostra: `instrumento_eletronico` é um PKCS#7 com o PDF DENTRO (assinatura
anexada), SHA-256 com RSA, atributos assinados de hora, hash e tipo, e o
certificado A3 do oficial. É exatamente o que o serviço local de assinatura
(`a3_servico_local`, rota `/assinar/pdf`) produz.

**O FORMATO É O MEDIDO, CARACTERE A CARACTERE** — versão `1.23-geral`, UTF-8
COM BOM, quebra CRLF, dois espaços de indentação, elemento vazio como
`<tag />`, e o arquivo termina SEM quebra de linha. O escritor é provado pela
ida e volta contra os 28 arquivos reais (ver o roteiro do dia).
"""
from __future__ import annotations

import base64
from typing import Any
from xml.sax.saxutils import escape

VERSAO = "1.23-geral"
BOM = "﻿"
FIM_DE_LINHA = "\r\n"

# A LETRA DE CADA ATO, e a ocorrência que vai com ele — medidas na amostra:
# P só traz ocorrência 2; D traz 1, 3 e A.
LETRA_DO_ATO = {"PROTESTO": "P", "PAGAMENTO": "D", "DESISTENCIA": "D",
                "CANCELAMENTO": "D"}
OCORRENCIA_DO_ATO = {"PROTESTO": "2", "PAGAMENTO": "1", "DESISTENCIA": "3",
                     "CANCELAMENTO": "A"}


class CenprotXmlError(ValueError):
    """Erro de regra do XML da CENPROT, com a frase pronta para o balcão."""


def nome_do_arquivo(*, uf: str, comarca: str, cartorio: str, letra: str,
                    dia: str, sequencial: int = 1) -> str:
    """`UF-IBGE-cartório-letra-AAAAMMDD-seq.xml` — a forma dos 28 da amostra
    (por exemplo `MA-2199999-01-P-20260709-01.xml`)."""
    if letra not in ("P", "D"):
        raise CenprotXmlError(f"Letra de arquivo desconhecida: {letra!r}.")
    return (f"{uf}-{comarca}-{cartorio}-{letra}-{str(dia).replace('-', '')}-"
            f"{int(sequencial):02d}.xml")


def valor(centavos: Any) -> str:
    """O valor como a CENPROT o lê: ponto e QUATRO casas — `1083.6000`
    (medido: `999.9999` em 58 de 58)."""
    c = int(centavos or 0)
    return f"{c // 100}.{c % 100:02d}00"


def logico(v: Any) -> str:
    return "true" if v else "false"


class _Escritor:
    def __init__(self):
        self.linhas: list[str] = []

    def abre(self, nivel: int, tag: str, **attrs) -> None:
        a = "".join(f' {k}="{escape(str(v), {chr(34): "&quot;"})}"'
                    for k, v in attrs.items())
        self.linhas.append(f"{'  ' * nivel}<{tag}{a}>")

    def fecha(self, nivel: int, tag: str) -> None:
        self.linhas.append(f"{'  ' * nivel}</{tag}>")

    def campo(self, nivel: int, tag: str, v: Any) -> None:
        texto = "" if v is None else str(v)
        if texto == "":
            self.linhas.append(f"{'  ' * nivel}<{tag} />")
        else:
            self.linhas.append(f"{'  ' * nivel}<{tag}>{escape(texto)}</{tag}>")


def _documento(e: _Escritor, n: int, pessoa: dict) -> None:
    """`<CNPJ>` ou `<CPF>` — e NADA quando não há documento (medido: o
    cedente sem documento vem sem a tag, e não com ela vazia)."""
    doc = "".join(c for c in str(pessoa.get("documento") or "") if c.isdigit())
    if doc:
        e.campo(n, "CNPJ" if len(doc) == 14 else "CPF", doc)


def _enderecos(e: _Escritor, n: int, end: dict | None) -> None:
    end = end or {}
    e.abre(n, "enderecos", total=1)
    e.abre(n + 1, "endereco", sequencia=1)
    for tag in ("endereco", "complemento", "cep", "bairro", "cidade", "uf"):
        e.campo(n + 2, tag, end.get(tag))
    e.fecha(n + 1, "endereco")
    e.fecha(n, "enderecos")


def _titulo(e: _Escritor, n: int, t: dict, letra: str) -> None:
    e.abre(n, "titulo", id=t["id"])
    for papel in ("cedente", "sacador"):
        p = t.get(papel) or {}
        e.abre(n + 1, papel)
        e.campo(n + 2, "nome", p.get("nome"))
        _documento(e, n + 2, p)
        _enderecos(e, n + 2, p.get("endereco"))
        e.fecha(n + 1, papel)
    for tag in ("nosso_numero", "especie", "numero_titulo", "data_emissao",
                "data_vencimento", "tipo_moeda", "valor", "saldo",
                "praca_protesto", "endosso", "tipo_endosso", "aceite"):
        e.campo(n + 1, tag, t.get(tag))
    devedores = t.get("devedores") or []
    e.abre(n + 1, "devedores", total=len(devedores))
    for i, d in enumerate(devedores, start=1):
        e.abre(n + 2, "devedor", sequencia=i)
        e.campo(n + 3, "nome", d.get("nome"))
        _documento(e, n + 3, d)
        e.campo(n + 3, "intimado", logico(d.get("intimado")))
        e.campo(n + 3, "edital", logico(d.get("edital")))
        e.campo(n + 3, "edital_motivo", d.get("edital_motivo"))
        _enderecos(e, n + 3, d.get("endereco"))
        e.fecha(n + 2, "devedor")
    e.fecha(n + 1, "devedores")
    for tag in ("data_apresentacao", "protocolo", "data_protocolo",
                "ocorrencia", "data_ocorrencia", "tipo_protesto"):
        e.campo(n + 1, tag, t.get(tag))
    if letra == "P":
        # SÓ NO P: motivo e tipo do livro (medido: ausentes nos 7 D).
        e.campo(n + 1, "motivo_protesto", t.get("motivo_protesto"))
        e.campo(n + 1, "tipo_livro", t.get("tipo_livro"))
    for tag in ("num_livro", "num_folha"):
        e.campo(n + 1, tag, t.get(tag))
    e.campo(n + 1, "acervo_herdado", logico(t.get("acervo_herdado")))
    if t.get("data_averbacao"):
        # O CANCELAMENTO leva a data da averbação, depois do acervo_herdado
        # (medido nos 2 D de ocorrência A).
        e.campo(n + 1, "data_averbacao", t["data_averbacao"])
    anuencia = t.get("anuencia")
    if not isinstance(anuencia, dict):
        anuencia = {"flag": bool(anuencia)}
    e.abre(n + 1, "anuencia")
    e.campo(n + 2, "flag", logico(anuencia.get("flag")))
    if anuencia.get("flag") and anuencia.get("origem"):
        # `origem` e `origem_datahora` são opcionais no esquema (v1_22-geral:
        # 1 arquivo da CRA, 2 CENPROT, 3 documento recebido no cartório), e
        # vão quando a casa SABE de onde a anuência veio.
        e.campo(n + 2, "origem", anuencia["origem"])
        e.campo(n + 2, "origem_datahora", anuencia.get("origem_datahora"))
    e.fecha(n + 1, "anuencia")
    if letra == "P" and t.get("instrumento"):
        e.campo(n + 1, "instrumento_eletronico",
                base64.b64encode(bytes(t["instrumento"])).decode("ascii"))
    e.fecha(n, "titulo")


def escrever(*, letra: str, uf: str, comarca: str, cartorio: str,
             apresentantes: list[dict]) -> bytes:
    """O arquivo inteiro, em bytes, na forma medida. Só calcula.

    `apresentantes` é a lista de `{codigo, nome, documento,
    tipo_apresentante, titulos: [...]}`, e cada título traz os campos com o
    nome da tag do XML (mais `cedente`, `sacador` e `devedores` como dicts, e
    `instrumento` como os bytes do `.p7s`).
    """
    if letra not in ("P", "D"):
        raise CenprotXmlError(f"Letra de arquivo desconhecida: {letra!r}.")
    if not apresentantes or not any(a.get("titulos") for a in apresentantes):
        raise CenprotXmlError("Não há título para o arquivo.")
    e = _Escritor()
    e.linhas.append('<?xml version="1.0" encoding="utf-8"?>')
    e.abre(0, "estados", total=1, versao=VERSAO)
    e.abre(1, "estado", uf=uf)
    e.abre(2, "cartorios", total=1)
    e.abre(3, "cartorio", codigo=cartorio, comarca=comarca)
    e.abre(4, "apresentantes", total=len(apresentantes))
    for a in apresentantes:
        e.abre(5, "apresentante", codigo=a["codigo"])
        e.campo(6, "nome", a.get("nome"))
        _documento(e, 6, a)
        e.campo(6, "tipo_apresentante", a.get("tipo_apresentante"))
        e.abre(6, "titulos", total=len(a["titulos"]))
        for t in a["titulos"]:
            _titulo(e, 7, t, letra)
        e.fecha(6, "titulos")
        e.fecha(5, "apresentante")
    e.fecha(4, "apresentantes")
    e.fecha(3, "cartorio")
    e.fecha(2, "cartorios")
    e.fecha(1, "estado")
    e.fecha(0, "estados")
    return (BOM + FIM_DE_LINHA.join(e.linhas)).encode("utf-8")


# ============================================================================
# DE ONDE VEM CADA CAMPO — 15/10/2026
#
# Medido nos 66 títulos da amostra contra o acervo (64 casaram pela chave):
#
#   apresentante   o código vem do título; nome, CNPJ e tipo vêm do CADASTRO
#                  (`pt_apresentantes`, trazido de `tbCobrador`);
#   cedente        o nome é o da posição 20 do registro da CRA; CNPJ e
#                  endereço só quando o cedente É o sacador;
#   sacador        nome na posição 65, documento na 110, endereço da 124 à 198
#                  — os campos que este sistema chama `cedente_*` são DELE;
#   endosso        H quando cedente e sacador são pessoas diferentes, G quando
#                  são a mesma;
#   intimado       verdadeiro só na intimação em mãos;
#   edital         verdadeiro quando o edital foi publicado — DECISÃO DO
#                  OFICIAL em 15/10/2026: o E-Ofício mandava sempre falso, e
#                  aqui não se imita isso;
#   protocolo      o da casa, e as duas datas de entrada são a do apontamento;
#   livro e folha  os do protesto no P; zero no D.
#
# O REGISTRO DA CRA vem de dois lugares: da remessa guardada em
# `pt_remessas` (o título que entrou por este sistema) ou de `tbSDT` no
# acervo, onde `CampoN` é o N-ésimo campo do registro ATÉ O 30 — conferido em
# 1.394 de 1.394 linhas (o tipo «1», a UF, o CEP, a espécie, o aceite e o
# motivo caem todos no lugar). Depois do 30 o E-Ofício reparte os campos
# reservados do seu jeito, e o bairro do devedor mora no `Campo39`.
#
# O DEVEDOR VAI COMO VEIO NO ARQUIVO, e é o que o E-Ofício fazia: medido na
# amostra, nome e endereço do devedor no XML são os do registro da CRA. O
# endereço do cedente e do sacador, não: o E-Ofício mandava o do cadastro
# dele, corrigido à mão (metade diverge do arquivo). Este sistema não tem esse
# cadastro, e manda o do arquivo — a diferença está medida e declarada.
# ============================================================================

import json
import re
import sqlite3

from bd_nativo import banco

ATOS_DA_LETRA = {"P": ("PROTESTO",),
                 "D": ("PAGAMENTO", "DESISTENCIA", "CANCELAMENTO")}
LIVRO_DO_PROTESTO = "G"


def _so_digitos(v: Any) -> str:
    return re.sub(r"\D", "", str(v or ""))


def _txt(v: Any) -> str:
    return str(v or "").strip()


def _mesmo_nome(a: Any, b: Any) -> bool:
    return re.sub(r"\s+", " ", _txt(a)).upper() == re.sub(r"\s+", " ", _txt(b)).upper()


# ------------------------------------------------------------ o registro


def registro_da_cra(con, titulo: dict,
                    acervo: sqlite3.Connection | None = None) -> dict | None:
    """O registro de 600 posições do título, lido. Só LÊ.

    Primeiro a remessa que este sistema recebeu (o título tem `remessa_id` e
    a chave `CRA:<remessa>:<posição no lote>`); senão o acervo do E-Ofício,
    pelo protocolo. Sem nenhum dos dois devolve None — e quem chama recusa,
    porque cedente e sacador não se adivinham.
    """
    import protesto_arquivo as PA
    bd = banco(con)
    chave = _txt(titulo.get("origem_chave"))
    if titulo.get("remessa_id") and chave.startswith("CRA:"):
        linha = bd.um("SELECT conteudo FROM pt_remessas WHERE id = %s",
                      (titulo["remessa_id"],))
        try:
            posicao = int(chave.rsplit(":", 1)[1])
        except ValueError:
            posicao = 0
        if linha and posicao > 0:
            lido = PA.ler(linha["conteudo"])
            if posicao <= len(lido.titulos):
                return lido.titulos[posicao - 1]
    protocolo = _txt(titulo.get("protocolo"))
    if acervo is not None and protocolo.isdigit():
        # O acervo do E-Ofício é um arquivo SQLite à parte, em só leitura: o
        # SQL dele continua o do SQLite.
        linha = acervo.execute(
            "SELECT * FROM tbSDT WHERE intProtocolo = :protocolo"
            " ORDER BY intChave LIMIT 1",
            {"protocolo": int(protocolo)}).fetchone()
        if linha is not None:
            nomes = [c[0] for c in acervo.execute(
                "SELECT * FROM tbSDT LIMIT 0").description]
            dados = dict(zip(nomes, linha))
            reg = {c.nome: _txt(dados.get(f"Campo{i:02d}"))
                   for i, c in enumerate(PA.TITULO_NA_REMESSA[:30], start=1)}
            reg["devedor_bairro"] = _txt(dados.get("Campo39"))
            return reg
    return None


def _cedente_e_sacador(reg: dict) -> tuple[dict, dict, str]:
    sacador = {"nome": _txt(reg.get("cedente_nome_2")),
               "documento": _so_digitos(reg.get("cedente_documento")),
               "endereco": {"endereco": _txt(reg.get("cedente_endereco")),
                            "complemento": "",
                            "cep": _so_digitos(reg.get("cedente_cep")),
                            "bairro": "",
                            "cidade": _txt(reg.get("cedente_cidade")),
                            "uf": _txt(reg.get("cedente_uf")).upper()}}
    nome_cedente = _txt(reg.get("cedente_nome"))
    if not sacador["nome"] or _mesmo_nome(nome_cedente, sacador["nome"]):
        sacador["nome"] = sacador["nome"] or nome_cedente
        return dict(sacador, nome=nome_cedente), sacador, "G"
    return {"nome": nome_cedente, "endereco": {}}, sacador, "H"


# ------------------------------------------------------- os apresentantes


def apresentante(con, codigo: Any) -> dict | None:
    return banco(con).um("SELECT * FROM pt_apresentantes WHERE codigo = %s",
                         (_txt(codigo),))


def apresentantes(con) -> list[dict]:
    return banco(con).ler("SELECT * FROM pt_apresentantes ORDER BY codigo")


def gravar_apresentante(con, *, codigo: Any, nome: Any,
                        documento: Any, tipo_apresentante: Any, agora: str,
                        usuario: str | None = None,
                        endereco: Any = None) -> None:
    """Cadastra ou corrige um apresentante. ESCREVE.

    O ENDEREÇO (LD08, 21/10/2026) é o que o registro e o instrumento do
    protesto levam (Lei 9.492/1997, art. 22, II), e o CNPJ o aviso leva (CN-MA
    art. 923) — o arquivo da CRA não traz nenhum dos dois. Ler é
    `protesto.apresentante_do_titulo`. Quem corrige o cadastro manda a linha
    inteira: endereço vazio apaga o de antes.
    """
    codigo, nome = _txt(codigo), _txt(nome)
    documento, tipo = _so_digitos(documento), _txt(tipo_apresentante)
    if not codigo or not nome:
        raise CenprotXmlError("Informe o código e o nome do apresentante.")
    if len(documento) not in (11, 14):
        raise CenprotXmlError(
            f"O documento do apresentante {codigo} tem de ser um CNPJ (14 "
            f"dígitos) ou um CPF (11).")
    if not tipo.isdigit():
        raise CenprotXmlError(
            f"Informe o tipo do apresentante {codigo} (o número que o XML da "
            f"CENPROT usa: na amostra desta casa aparecem 0, 1, 3 e 4).")
    banco(con).escrever(
        """INSERT INTO pt_apresentantes(codigo, nome, documento,
               tipo_apresentante, endereco, origem, atualizado_em,
               atualizado_por)
           VALUES (%s, %s, %s, %s, %s, 'MANUAL', %s, %s)
           ON CONFLICT(codigo) DO UPDATE SET nome=excluded.nome,
               documento=excluded.documento,
               tipo_apresentante=excluded.tipo_apresentante,
               endereco=excluded.endereco,
               origem='MANUAL', atualizado_em=excluded.atualizado_em,
               atualizado_por=excluded.atualizado_por""",
        (codigo, nome, documento, tipo, _txt(endereco) or None, agora, usuario))


def carregar_apresentantes(con, acervo: sqlite3.Connection,
                           *, agora: str) -> dict:
    """Traz os apresentantes de `tbCobrador`. ESCREVE.

    Só os que têm o código da CRA (`strCodigoBanco`). **O que alguém já
    corrigiu à mão não se sobrescreve**: a correção é mais nova que o acervo.
    """
    bd = banco(con)
    entraram = mantidos = sem_codigo = 0
    for r in acervo.execute(
            """SELECT strCodigoBanco, strRazaoSocial, strCGC, strCIC,
                      intTipoApresentante FROM tbCobrador"""):
        codigo = _txt(r[0])
        if not codigo:
            sem_codigo += 1
            continue
        if bd.um("SELECT 1 AS um FROM pt_apresentantes WHERE codigo = %s",
                 (codigo,)):
            mantidos += 1
            continue
        tipo = r[4]
        # Quem cadastra à mão no meio da carga não derruba a carga: fica o
        # cadastro dele, como se já estivesse lá.
        bd.escrever(
            """INSERT INTO pt_apresentantes(codigo, nome, documento,
                   tipo_apresentante, origem, atualizado_em)
               VALUES (%s, %s, %s, %s, 'EOFICIO', %s)
               ON CONFLICT(codigo) DO NOTHING""",
            (codigo, _txt(r[1]), _so_digitos(r[2]) or _so_digitos(r[3]),
             "" if tipo is None else str(int(tipo)), agora))
        if not bd.linhas_afetadas:
            mantidos += 1
            continue
        entraram += 1
    return {"entraram": entraram, "mantidos": mantidos,
            "sem_codigo": sem_codigo}


# ------------------------------------------------------------ o título


def _intimacao(con, titulo_id: int) -> tuple[bool, bool]:
    """(intimado, edital), pela última intimação lavrada e não cancelada."""
    linha = banco(con).um(
        """SELECT detalhe_json FROM pt_atos WHERE titulo_id = %s AND
               tipo='INTIMACAO' AND cancelado=0 ORDER BY id DESC LIMIT 1""",
        (titulo_id,))
    if not linha:
        return False, False
    modo = _txt(json.loads(linha["detalhe_json"] or "{}").get("modo")).upper()
    return modo == "PESSOAL", modo == "EDITAL"


def _data_de_entrada(con, titulo: dict) -> str:
    linha = banco(con).um(
        """SELECT data_ato FROM pt_atos WHERE titulo_id = %s AND
               tipo='APONTAMENTO' AND cancelado=0 ORDER BY id LIMIT 1""",
        (titulo["id"],))
    if linha and linha["data_ato"]:
        return str(linha["data_ato"])[:10]
    p = _so_digitos(titulo.get("protocolo"))
    if len(p) >= 6:
        return f"20{p[:2]}-{p[2:4]}-{p[4:6]}"
    return ""


def _livro_e_folha(con, ato: dict) -> tuple[str, str]:
    detalhe = json.loads(ato.get("detalhe_json") or "{}")
    livro = ""
    if ato.get("livro_id"):
        r = banco(con).um("SELECT numero FROM nu_livros WHERE id = %s",
                          (ato["livro_id"],))
        livro = _txt(r["numero"]) if r else ""
    livro = livro or _txt(detalhe.get("livro_do_acervo"))
    return _so_digitos(livro), _so_digitos(ato.get("folha"))


def _anuencia(con, titulo_id: int) -> dict:
    """Há anuência registrada para este título? Só LÊ.

    O esquema diz o que o campo é: «aponta se existe anuência registrada no
    cartório para este título». A casa a registra de dois jeitos, e cada um
    tem a sua origem no esquema: a pendência de anuência da CENPROT aprovada
    (2) e o cancelamento lavrado pela hipótese ANUENCIA_CREDOR, à vista da
    carta (3). Sem nenhum dos dois o campo vai falso — nada afirma anuência.
    """
    bd = banco(con)
    for r in bd.ler(
            """SELECT decisao, decidida_em FROM cn_pendencias
                WHERE titulo_id = %s AND especie='ANUENCIA'
                  AND situacao IN ('DECIDIDA','ENVIADA') ORDER BY id DESC""",
            (titulo_id,)):
        try:
            decisao = json.loads(r["decisao"] or "{}")
        except ValueError:
            decisao = {}
        if decisao.get("ic_aprovado") is True:
            return {"flag": True, "origem": "2",
                    "origem_datahora": _txt(r["decidida_em"])[:10]}
    for r in bd.ler(
            """SELECT data_ato, detalhe_json FROM pt_atos WHERE titulo_id = %s
                 AND tipo='CANCELAMENTO' AND cancelado=0 ORDER BY id DESC""",
            (titulo_id,)):
        if json.loads(r["detalhe_json"] or "{}").get("hipotese") == "ANUENCIA_CREDOR":
            return {"flag": True, "origem": "3",
                    "origem_datahora": _txt(r["data_ato"])[:10]}
    return {"flag": False}


def _devedores(con, titulo_id: int, reg: dict,
               intimado: bool, edital: bool) -> list[dict]:
    gravados = banco(con).ler(
        "SELECT * FROM pt_devedores WHERE titulo_id = %s ORDER BY id",
        (titulo_id,))
    if len(gravados) == 1 and _txt(reg.get("devedor_nome")):
        # Um devedor só: vai o do arquivo, como o E-Ofício mandava. O
        # documento tem 14 posições também para CPF, e é o TIPO que diz quantos
        # dígitos valem — a regra mora em `protesto_arquivo` (no acervo o tipo
        # vem «001»/«002», e no arquivo lido vem 1/2).
        import protesto_arquivo as PA
        doc = PA.documento_do_devedor({
            "devedor_documento": reg.get("devedor_documento"),
            "devedor_tipo_de_documento":
                _so_digitos(reg.get("devedor_tipo_de_documento")).lstrip("0")})
        gravados = [{"nome": reg.get("devedor_nome"),
                     "documento_numero": next(iter(doc.values())),
                     "endereco": reg.get("devedor_endereco"),
                     "bairro": reg.get("devedor_bairro"),
                     "cep": reg.get("devedor_cep"),
                     "cidade": reg.get("devedor_cidade"),
                     "uf": reg.get("devedor_uf")}]
    # O MOTIVO DO EDITAL vai quando houve edital — texto livre de até 200
    # caracteres no esquema. O E-Ofício o mandava vazio; o oficial pediu que
    # fosse (15/10/2026). A regra de onde ele mora é a do edital eletrônico.
    motivo = ""
    if edital:
        import protesto_cenprot as PCEN
        motivo = PCEN._motivo_do_edital(con, titulo_id)[:200]
    return [{"nome": _txt(d["nome"]),
             "documento": _so_digitos(d["documento_numero"]),
             "intimado": intimado, "edital": edital, "edital_motivo": motivo,
             "endereco": {"endereco": _txt(d["endereco"]), "complemento": "",
                          "cep": _so_digitos(d["cep"]),
                          "bairro": _txt(d["bairro"]),
                          "cidade": _txt(d["cidade"]),
                          "uf": _txt(d["uf"]).upper()}}
            for d in gravados]


def montar_titulo(con, ato_id: int, *,
                  acervo: sqlite3.Connection | None = None,
                  com_instrumento: bool = True) -> dict:
    """O título do XML para um ato lavrado, e o apresentante dele. Só LÊ.

    Recusa (CenprotXmlError) com a frase do que falta, em vez de mandar à
    Central um título pela metade.
    """
    import protesto_instrumento as PI
    bd = banco(con)
    ato = bd.um("SELECT * FROM pt_atos WHERE id = %s", (ato_id,))
    if ato is None:
        raise CenprotXmlError(f"Ato {ato_id} não encontrado.")
    letra = LETRA_DO_ATO.get(ato["tipo"])
    if letra is None:
        raise CenprotXmlError(f"O ato {ato['tipo']} não vai ao XML da CENPROT.")
    titulo = dict(bd.um("SELECT * FROM pt_titulos WHERE id = %s",
                        (ato["titulo_id"],)))
    chave = _so_digitos(titulo.get("chave_cenprot"))
    if len(chave) != 23:
        raise CenprotXmlError(
            "o título não tem a chave do CENPROT — ela vem do XML que a "
            "Central devolve (tela «Chave do CENPROT»)")
    apr = apresentante(bd, titulo.get("apresentante_codigo"))
    if not apr or not apr.get("documento") or not _txt(apr.get("tipo_apresentante")):
        raise CenprotXmlError(
            f"o apresentante {titulo.get('apresentante_codigo') or '(sem código)'} "
            f"não está cadastrado com CNPJ e tipo — cadastre-o nesta tela")
    reg = registro_da_cra(bd, titulo, acervo)
    if reg is None:
        raise CenprotXmlError(
            "o registro da CRA deste título não está no sistema nem no acervo "
            "— sem ele não se sabe quem é o cedente e quem é o sacador")
    cedente, sacador, endosso = _cedente_e_sacador(reg)
    intimado, edital = _intimacao(bd, titulo["id"])
    entrada = _data_de_entrada(bd, titulo)
    t = {"id": chave, "cedente": cedente, "sacador": sacador,
         "nosso_numero": _txt(titulo.get("nosso_numero")),
         "especie": _txt(titulo.get("especie")),
         "numero_titulo": _txt(titulo.get("numero_titulo")),
         "data_emissao": _txt(titulo.get("data_emissao"))[:10],
         "data_vencimento": _txt(titulo.get("data_vencimento"))[:10],
         "tipo_moeda": (_so_digitos(titulo.get("tipo_moeda")) or "1").zfill(3),
         "valor": valor(titulo.get("valor_centavos")),
         "saldo": valor(titulo.get("saldo_centavos")),
         "praca_protesto": _txt(titulo.get("praca_protesto")),
         "endosso": endosso,
         "tipo_endosso": (_txt(titulo.get("tipo_endosso")).upper()
                          if _txt(titulo.get("tipo_endosso")).upper() in ("M", "T")
                          else "S"),
         "aceite": ("A" if (_txt(titulo.get("aceite"))
                            or _txt(reg.get("aceite"))).upper() == "A" else "N"),
         "devedores": _devedores(bd, titulo["id"], reg, intimado, edital),
         "data_apresentacao": entrada,
         "protocolo": _txt(titulo.get("protocolo")),
         "data_protocolo": entrada,
         "ocorrencia": OCORRENCIA_DO_ATO[ato["tipo"]],
         "data_ocorrencia": _txt(ato.get("data_ato"))[:10],
         "tipo_protesto": _txt(titulo.get("tipo_protesto")).upper() or "C",
         "acervo_herdado": False,
         "anuencia": _anuencia(bd, titulo["id"])}
    if not t["devedores"]:
        raise CenprotXmlError("o título não tem devedor gravado")
    if letra == "P":
        livro, folha = _livro_e_folha(bd, ato)
        if not livro or not folha:
            raise CenprotXmlError("o protesto não tem livro e folha gravados")
        motivo = _txt(titulo.get("motivo_protesto"))
        if not motivo:
            raise CenprotXmlError("o título não tem o motivo do protesto")
        t.update(motivo_protesto=motivo, tipo_livro=LIVRO_DO_PROTESTO,
                 num_livro=livro, num_folha=folha)
        if com_instrumento:
            p7s = PI.assinado_do_titulo(bd, titulo["id"])
            if not p7s:
                raise CenprotXmlError(
                    "o instrumento do protesto ainda não foi assinado com o "
                    "A3 — assine-o na tela dos instrumentos")
            t["instrumento"] = p7s
    else:
        t.update(num_livro="0", num_folha="0")
        if ato["tipo"] == "CANCELAMENTO":
            t["data_averbacao"] = t["data_ocorrencia"]
    return {"letra": letra, "titulo": t,
            "apresentante": {"codigo": _txt(apr["codigo"]),
                             "nome": _txt(apr["nome"]),
                             "documento": apr["documento"],
                             "tipo_apresentante": _txt(apr["tipo_apresentante"])}}


# ------------------------------------------------- o que falta mandar


def pendentes(con, letra: str, *,
              acervo: sqlite3.Connection | None = None) -> dict:
    """Os atos lavrados POR ESTE SISTEMA que a Central ainda não recebeu. Só LÊ.

    O que veio do E-Ofício já foi mandado por ele. Devolve `entram` (prontos)
    e `fora` (com o motivo de cada um) — o que não entra aparece, e não some.
    """
    if letra not in ATOS_DA_LETRA:
        raise CenprotXmlError(f"Letra de arquivo desconhecida: {letra!r}.")
    bd = banco(con)
    marcas = ", ".join(["%s"] * len(ATOS_DA_LETRA[letra]))
    atos = bd.ler(
        f"""SELECT a.id, a.tipo, a.data_ato, t.id AS titulo_id, t.protocolo,
                   t.apresentante_codigo
              FROM pt_atos a JOIN pt_titulos t ON t.id = a.titulo_id
             WHERE a.tipo IN ({marcas}) AND a.cancelado = 0
               AND a.cenprot_xml_id IS NULL
               AND COALESCE(a.origem, '') <> 'EOFICIO'
             ORDER BY a.data_ato, a.id""", ATOS_DA_LETRA[letra])
    entram, fora = [], []
    for a in atos:
        base = {"ato_id": a["id"], "tipo": a["tipo"], "data_ato": a["data_ato"],
                "titulo_id": a["titulo_id"], "protocolo": a["protocolo"]}
        try:
            entram.append(dict(base, **montar_titulo(bd, a["id"], acervo=acervo)))
        except CenprotXmlError as erro:
            fora.append(dict(base, motivo=str(erro)))
    return {"entram": entram, "fora": fora}


def gerar(con, letra: str, *, uf: str, comarca: str,
          cartorio: str, dia: str, agora: str, usuario: str | None = None,
          acervo: sqlite3.Connection | None = None) -> dict:
    """Escreve o arquivo do dia com o que está pronto, guarda e marca. ESCREVE.

    Cada ato que entra ganha `cenprot_xml_id` na MESMA transação em que o
    arquivo é guardado: o que foi para um arquivo não entra no seguinte.
    """
    bd = banco(con)
    # A TRAVA VEM ANTES DA LISTA: duas gerações da mesma letra ao mesmo tempo
    # leriam os mesmos atos pendentes, e o segundo arquivo levaria de novo o
    # que o primeiro já levou.
    bd.travar("pt_cenprot_xml.sequencial")
    lista = pendentes(bd, letra, acervo=acervo)
    if not lista["entram"]:
        raise CenprotXmlError(
            "Não há ato pronto para este arquivo"
            + (f" — {len(lista['fora'])} esperam o que falta (veja a lista)."
               if lista["fora"] else "."))
    grupos: dict[str, dict] = {}
    for item in lista["entram"]:
        a = item["apresentante"]
        grupos.setdefault(a["codigo"], dict(a, titulos=[]))["titulos"].append(
            item["titulo"])
    sequencial = 1 + int(bd.valor(
        "SELECT COUNT(*) AS n FROM pt_cenprot_xml WHERE letra = %s AND dia = %s",
        (letra, dia)))
    nome = nome_do_arquivo(uf=uf, comarca=comarca, cartorio=cartorio,
                           letra=letra, dia=dia, sequencial=sequencial)
    conteudo = escrever(letra=letra, uf=uf, comarca=comarca, cartorio=cartorio,
                        apresentantes=list(grupos.values()))
    import hashlib
    xml_id = int(bd.escrever(
        """INSERT INTO pt_cenprot_xml(letra, dia, sequencial, nome_arquivo,
               conteudo, sha256, titulos, gerado_em, gerado_por)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
        (letra, dia, sequencial, nome, conteudo,
         hashlib.sha256(conteudo).hexdigest(), len(lista["entram"]), agora,
         usuario))[0]["id"])
    bd.escrever("UPDATE pt_atos SET cenprot_xml_id = %s WHERE id = ANY(%s)",
                (xml_id, [i["ato_id"] for i in lista["entram"]]))
    return {"id": xml_id, "nome": nome, "titulos": len(lista["entram"]),
            "fora": lista["fora"]}


def arquivos(con, limite: int = 60) -> list[dict]:
    return banco(con).ler(
        """SELECT id, letra, dia, sequencial, nome_arquivo, sha256, titulos,
                  gerado_em, gerado_por FROM pt_cenprot_xml
            ORDER BY id DESC LIMIT %s""", (int(limite),))


def arquivo(con, xml_id: int) -> dict | None:
    return banco(con).um("SELECT * FROM pt_cenprot_xml WHERE id = %s",
                         (int(xml_id),))
