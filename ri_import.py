"""
Registro de Imoveis - importador do acervo do E-Oficio.

Le os arquivos JSON Lines produzidos por EXPORTAR_RI.cmd e grava no banco do
sistema. Nada e descartado em silencio: o que nao entra vai para ri_rejeitados
com o motivo, para que a migracao possa ser auditada depois.

Decisoes da serventia aplicadas aqui:

  - Matricula sem numero: quarentena (10 casos conhecidos no acervo).
  - Numero duplicado no mesmo livro e complemento: fica a mais completa
    (maior teor); empate resolve pela data mais recente e, por fim, pela
    chave maior. As perdedoras vao para quarentena registrando quem venceu.
  - tipo_ficha nao vem do bitAcervoAntigo, e sim do fato de a matricula ter
    ou nao atos destacados. E isso que muda o que o usuario pode fazer.
  - Toda matricula importada nasce com conferido=0. O livro fisico continua
    sendo a fonte legal ate alguem conferir.

Uso:
    python ri_import.py --origem PASTA_EXPORT [--banco caminho.sqlite3] [--simular]
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import datetime

# tbRI_TipoImovel do E-Oficio: intID -> descricao. Os codigos do ONR e da DOI
# ficam em ri_onr.TIPO_IMOVEL_ONR e em ri_ctp.TIPO_IMOVEL; aqui guardamos o
# nome, que e o que a tela mostra.
TIPO_IMOVEL_EOFICIO = {
    0: "Casa", 1: "Apartamento", 2: "Loja", 3: "Sala/Conjunto", 4: "Terreno/fração",
    5: "Galpão", 6: "Prédio comercial", 7: "Prédio residencial",
    8: "Fazenda/Sítio/Chácara", 9: "Outros",
}
from pathlib import Path

import banco_pg
from bd_nativo import banco
from ri_schema import (
    hash_ato,
    init_ri_schema,
    norm,
    norm_livro,
    normalizar_busca,
    matricula_de_acervo,
    so_digitos,
    valida_cpf_cnpj,
)

AGORA = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


# ------------------------------------------------------------------ leitura


def ler_jsonl(caminho: Path) -> list[dict]:
    if not caminho.exists():
        return []
    linhas = []
    with caminho.open(encoding="utf-8") as fh:
        for n, linha in enumerate(fh, 1):
            linha = linha.strip()
            if not linha:
                continue
            try:
                linhas.append(json.loads(linha))
            except json.JSONDecodeError as erro:
                print(f"  aviso: {caminho.name} linha {n} ilegivel ({erro})")
    return linhas


def data_iso(valor) -> str | None:
    """'2002-06-20 00:00:00' -> '2002-06-20'."""
    texto = norm(valor)
    if not texto:
        return None
    return texto.split(" ")[0]


TAG = re.compile(r"<[^>]+>")
ESPACO = re.compile(r"[ \t\r\f\v]+")


def texto_puro(xhtml: str | None) -> str:
    """Extrai o texto do teor para busca. O XHTML original e preservado."""
    if not xhtml:
        return ""
    corpo = re.sub(r"(?is)<head.*?</head>", " ", xhtml)
    corpo = re.sub(r"(?i)</p>|<br\s*/?>", "\n", corpo)
    corpo = TAG.sub(" ", corpo)
    corpo = html.unescape(corpo)
    corpo = ESPACO.sub(" ", corpo)
    return "\n".join(l.strip() for l in corpo.splitlines() if l.strip())


def chave_matricula(numero, complemento, livro) -> tuple[str, str, str]:
    """A ligacao no E-Oficio e por texto em char(10), que vem com espacos a
    direita. Sem normalizar isso, o vinculo se perde."""
    return (norm(numero), norm(complemento), norm_livro(livro))


# ------------------------------------------------------------- importacao


class Importador:
    def __init__(self, con, usuario_id: int | None = None):
        self.con = con
        self.bd = banco(con)
        self.usuario_id = usuario_id
        self.rejeitados: list[tuple] = []
        self.contagem = {
            "matriculas_lidas": 0, "matriculas_gravadas": 0,
            "atos_lidos": 0, "atos_gravados": 0,
            "partes_lidas": 0, "partes_gravadas": 0,
            "imagens_gravadas": 0, "protocolos_gravados": 0,
            "cnib_ordens": 0, "cnib_pessoas": 0, "certidoes": 0,
            "certidoes_com_teor": 0, "rejeitados": 0,
            # DUAS CONTAGENS A PARTE, E ELAS NAO SAO DETALHE — 18/09/2026.
            # Desde que o atualizador do CNIB existe, a carga do E-Oficio pode
            # topar com linha que a Central ja trouxe. Ela nao a sobrescreve (o
            # dado da Central e mais novo), e por isso essas linhas nao entram
            # em `cnib_ordens` — que e o que a carga GRAVOU. Somar as duas
            # coisas faria a tela dizer que a carga trouxe o que ela deixou
            # intacto, que e o carimbo que mente na forma de contador.
            "cnib_ordens_preservadas": 0, "cnib_pessoas_preservadas": 0,
        }
        self.importacao_id: int | None = None
        self.id_por_chave: dict[tuple, int] = {}
        self.id_por_origem: dict[str, int] = {}

    # -- quarentena ---------------------------------------------------

    def rejeitar(self, entidade: str, chave_origem, motivo: str, conteudo=None):
        self.rejeitados.append((
            entidade, str(chave_origem), motivo,
            json.dumps(conteudo, ensure_ascii=False, default=str)[:4000] if conteudo else None,
        ))
        self.contagem["rejeitados"] += 1

    # -- matriculas ---------------------------------------------------

    def escolher_entre_duplicatas(self, grupo: list[dict]) -> tuple[dict, list[dict]]:
        """Mais completa (maior teor), depois mais recente, depois chave maior."""
        def peso(m):
            return (
                len(m.get("memTeorFichaFormatado") or "") + len(m.get("memTextoFicha") or ""),
                norm(m.get("dtmData")),
                int(m.get("intChave") or 0),
            )
        ordenado = sorted(grupo, key=peso, reverse=True)
        return ordenado[0], ordenado[1:]

    def importar_matriculas(self, registros: list[dict], atos: list[dict]) -> None:
        self.contagem["matriculas_lidas"] = len(registros)

        # Quem tem ato destacado e ficha estruturada; o resto e acervo em bloco.
        com_ato = {chave_matricula(a.get("strMatricula"), a.get("StrComp"), None)[:2]
                   for a in atos}

        grupos: dict[tuple, list[dict]] = {}
        for m in registros:
            numero = norm(m.get("strMatricula"))
            if not numero:
                self.rejeitar("matricula", m.get("intChave"),
                              "Matricula sem numero no acervo do E-Oficio",
                              {"intChave": m.get("intChave"), "livro": m.get("strLivro"),
                               "cnm": m.get("strCNM"), "data": m.get("dtmData")})
                continue
            grupos.setdefault(chave_matricula(numero, m.get("strComp"), m.get("strLivro")), []).append(m)

        for chave, grupo in grupos.items():
            escolhida = grupo[0]
            if len(grupo) > 1:
                escolhida, perdedoras = self.escolher_entre_duplicatas(grupo)
                for p in perdedoras:
                    self.rejeitar(
                        "matricula", p.get("intChave"),
                        f"Numero duplicado no mesmo livro. Prevaleceu a chave "
                        f"{escolhida.get('intChave')} (mais completa/recente)",
                        {"intChave": p.get("intChave"), "numero": p.get("strMatricula"),
                         "livro": p.get("strLivro"),
                         "bytes_teor": len(p.get("memTeorFichaFormatado") or "")},
                    )
            self.gravar_matricula(escolhida, chave, com_ato)

    def gravar_matricula(self, m: dict, chave: tuple, com_ato: set) -> None:
        teor = m.get("memTeorFichaFormatado") or m.get("memTextoFicha") or ""
        # Abaixo de 4.015 e acervo por definicao da serventia. A separacao de
        # atos feita pelo sistema anterior nao transforma a ficha historica
        # em abertura nova nem autoriza recompor seu fecho.
        estruturada = chave[:2] in com_ato and not matricula_de_acervo(chave[0])
        confront = " | ".join(
            norm(m.get(c)) for c in
            ("strConfrontacao", "strConfrontacao_N", "strConfrontacao_S",
             "strConfrontacao_L", "strConfrontacao_O")
            if norm(m.get(c))
        )
        novo = self.bd.escrever(
            """INSERT INTO ri_matriculas
               (numero, complemento, cnm, livro, livro_norm, folha, folha_complemento,
                data_abertura, tipo_ficha, situacao, conferido, encerrada,
                motivo_encerramento, data_encerramento, rural_urbano, tipo_imovel,
                logradouro, numero_predial, complemento_endereco, bairro, cidade, uf, cep,
                area_valor, area_unidade, descricao_perimetro, confrontacoes,
                car, nirf, incra, sigef, ccir, cmc, inscricao_municipal, iptu,
                registro_anterior, observacao, teor, teor_formato,
                origem, origem_chave, importacao_id, criado_em, criado_por)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,0,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                       'EOFICIO',%s,%s,%s,%s)
               RETURNING id""",
            (
                chave[0], chave[1], norm(m.get("strCNM")) or None,
                norm(m.get("strLivro")) or None, chave[2],
                norm(m.get("strFolha")) or None, norm(m.get("strFolhaComp")) or None,
                data_iso(m.get("dtmData")),
                "ESTRUTURADA" if estruturada else "ACERVO",
                "ENCERRADA" if m.get("bitEncerrada") else "ATIVA",
                1 if m.get("bitEncerrada") else 0,
                norm(m.get("strMotivoEncerramento")) or None,
                data_iso(m.get("dtmDataEncerramento")),
                norm(m.get("strTipoImovelRU")) or None,
                # tbRI.intTipoImovel esta preenchido em 1.689 das 1.721
                # matriculas do acervo, e a carga anterior o descartou. E o
                # dado que alimenta o Indicador Real do ONR e o tipo do imovel
                # na CTP - sem ele, os dois saem no padrao generico.
                TIPO_IMOVEL_EOFICIO.get(m.get("intTipoImovel")),
                norm(m.get("strLogradouro")) or norm(m.get("strEndereco")) or None,
                norm(m.get("strNumero")) or None, norm(m.get("strComplemento")) or None,
                norm(m.get("strBairro")) or None, norm(m.get("strCidade")) or None,
                norm(m.get("strUF")) or None, norm(m.get("strCep")) or None,
                norm(m.get("intArea")) or None, norm(m.get("strTipoArea")) or None,
                norm(m.get("strDescricaoPerimetro")) or None, confront or None,
                norm(m.get("strCAR")) or None, norm(m.get("strNIRF")) or None,
                norm(m.get("strINCRA")) or None, norm(m.get("strSIGEF")) or None,
                norm(m.get("strCCIR")) or None, norm(m.get("strCMC")) or None,
                norm(m.get("strInscMunicipal")) or None, norm(m.get("strNumeroIPTU")) or None,
                norm(m.get("memRegAnterior")) or None, norm(m.get("strObservacao")) or None,
                teor or None, "html" if teor.lstrip().startswith("<?xml") else "texto",
                str(m.get("intChave")), self.importacao_id, AGORA, self.usuario_id,
            ),
        )
        novo_id = int(novo[0]["id"])
        self.id_por_chave[chave] = novo_id
        self.id_por_chave.setdefault(chave[:2], novo_id)
        self.id_por_origem[str(m.get("intChave"))] = novo_id
        self.contagem["matriculas_gravadas"] += 1

    # -- atos ---------------------------------------------------------

    def importar_atos(self, registros: list[dict]) -> None:
        self.contagem["atos_lidos"] = len(registros)

        def ordem(a):
            return (norm(a.get("strMatricula")), data_iso(a.get("dtmData")) or "",
                    int(a.get("strNReg") or 0))

        ultimo_hash: dict[int, str] = {}
        vistos: set[tuple] = set()

        for a in sorted(registros, key=ordem):
            chave = chave_matricula(a.get("strMatricula"), a.get("StrComp"), None)[:2]
            matricula_id = self.id_por_chave.get(chave)
            if matricula_id is None:
                self.rejeitar("ato", a.get("intChave"),
                              f"Ato sem matricula correspondente (numero {norm(a.get('strMatricula'))})",
                              {"intChave": a.get("intChave"), "tipo": a.get("strTipoReg"),
                               "nreg": a.get("strNReg")})
                continue

            tipo = norm(a.get("strTipoReg")).upper() or "R"
            numero = int(a.get("strNReg") or 0)
            if (matricula_id, tipo, numero) in vistos:
                self.rejeitar("ato", a.get("intChave"),
                              f"Ato {tipo}-{numero} repetido na mesma matricula",
                              {"intChave": a.get("intChave")})
                continue
            vistos.add((matricula_id, tipo, numero))

            teor = a.get("memTeorFichaFormatado") or a.get("memTexto") or ""
            data = data_iso(a.get("dtmData"))
            anterior = ultimo_hash.get(matricula_id)
            h = hash_ato(chave[0], tipo, numero, data or "", teor, anterior)

            self.bd.escrever(
                """INSERT INTO ri_atos
                   (matricula_id, tipo, numero, data_ato, protocolo, prenotacao,
                    teor, teor_formato, cancelado, acervo, origem, origem_chave,
                    importacao_id, hash_ato, hash_anterior, lavrado_em, lavrado_por)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'EOFICIO',%s,%s,%s,%s,%s,%s)""",
                (matricula_id, tipo, numero, data,
                 norm(a.get("strProtocoloGeral")) or None,
                 norm(a.get("intNumeroPrenotacao")) or None,
                 teor or None, "html" if teor.lstrip().startswith("<?xml") else "texto",
                 1 if a.get("bitCancelado") else 0,
                 1 if a.get("bitAcervo") else 0,
                 str(a.get("intChave")), self.importacao_id, h, anterior,
                 AGORA, self.usuario_id),
            )
            ultimo_hash[matricula_id] = h
            self.contagem["atos_gravados"] += 1

    # -- partes -------------------------------------------------------

    @staticmethod
    def _pessoa_normalizada(p: dict) -> dict:
        """Unifica tbOrtoga (a tabela real das partes) e tbPessoa (residual).

        tbOrtoga guarda pessoa fisica em strNome e juridica em PJ_RazaoSocial,
        e traz estado civil, profissao e nacionalidade - que juntos formam a
        qualificacao que sai na ficha.
        """
        if "intCodigo" in p:
            juridica = norm(p.get("strTipoPessoa")).upper() == "J"
            nome = norm(p.get("PJ_RazaoSocial")) if juridica else norm(p.get("strNome"))
            nome = nome or norm(p.get("strNome")) or norm(p.get("PJ_RazaoSocial"))
            qualificacao = ", ".join(
                t for t in (
                    norm(p.get("strNacionalidade")),
                    norm(p.get("strEstadoCivil")),
                    norm(p.get("strProfissao")),
                ) if t
            )
            return {
                "nome": nome,
                "cpf": so_digitos(p.get("strCPF")),
                "cnpj": so_digitos(p.get("strCNPJ")),
                "qualificacao": qualificacao or None,
            }
        return {
            "nome": norm(p.get("strRazaoSocial")) or norm(p.get("strNomeFantasia")),
            "cpf": so_digitos(p.get("strCIC")),
            "cnpj": so_digitos(p.get("strCGC")),
            "qualificacao": norm(p.get("strNacionalidade")) or None,
        }

    def importar_partes(self, registros: list[dict], pessoas: list[dict]) -> None:
        self.contagem["partes_lidas"] = len(registros)
        indice = {}
        for p in pessoas:
            codigo = p.get("intCodigo", p.get("intCodigoPessoa"))
            if codigo is not None:
                indice[str(codigo)] = self._pessoa_normalizada(p)

        atos = {}
        for row in self.bd.ler("SELECT id, matricula_id, tipo, numero FROM ri_atos ORDER BY id"):
            atos[(row["matricula_id"], row["tipo"], int(row["numero"]))] = row["id"]

        for p in registros:
            chave = chave_matricula(p.get("strMatricula"), p.get("StrComp"), None)[:2]
            matricula_id = self.id_por_chave.get(chave)
            if matricula_id is None:
                self.rejeitar("parte", p.get("intChave"),
                              f"Parte sem matricula correspondente (numero {norm(p.get('strMatricula'))})",
                              {"intChave": p.get("intChave")})
                continue

            pessoa = indice.get(str(p.get("intCodigoParte"))) or {}
            nome = pessoa.get("nome") or ""
            if not nome:
                self.rejeitar("parte", p.get("intChave"),
                              f"Parte sem pessoa cadastrada (codigo {p.get('intCodigoParte')})",
                              {"intChave": p.get("intChave")})
                continue

            cpf = pessoa.get("cpf") or ""
            cnpj = pessoa.get("cnpj") or ""
            doc_tipo, doc_num = ("CPF", cpf) if len(cpf) == 11 else (
                ("CNPJ", cnpj) if len(cnpj) == 14 else (None, cpf or cnpj or ""))

            tipo = norm(p.get("strTipoReg")).upper()
            numero = int(p.get("strNReg") or 0)
            ato_id = atos.get((matricula_id, tipo, numero))

            self.bd.escrever(
                """INSERT INTO ri_partes
                   (matricula_id, ato_id, nome, documento_tipo, documento_numero,
                    documento_valido, qualificacao, papel, proprietario,
                    proprietario_ativo, participacao, origem, origem_chave)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'EOFICIO',%s)""",
                (matricula_id, ato_id, nome, doc_tipo, doc_num or None,
                 1 if doc_num and valida_cpf_cnpj(doc_num) else 0,
                 pessoa.get("qualificacao"),
                 "proprietario" if p.get("bitProprietario") else None,
                 1 if p.get("bitProprietario") else 0,
                 1 if p.get("bitProprietarioAtivo") else 0,
                 norm(p.get("curParticipacaoDOI")) or None,
                 str(p.get("intChave"))),
            )
            self.contagem["partes_gravadas"] += 1

    # -- imagens ------------------------------------------------------

    def importar_imagens(self, registros: list[dict]) -> None:
        for i in registros:
            chave = chave_matricula(i.get("strMatricula"), i.get("strComp"), None)[:2]
            matricula_id = self.id_por_chave.get(chave)
            if matricula_id is None:
                self.rejeitar("imagem", i.get("id"), "Imagem sem matricula correspondente")
                continue
            self.bd.escrever(
                """INSERT INTO ri_imagens
                   (matricula_id, nome_arquivo, ordem, ficha_digitalizada)
                   VALUES (%s,%s,%s,%s)""",
                (matricula_id, norm(i.get("strNomeDigital")) or None,
                 i.get("intOrdem"), 1 if i.get("bitFichaDigitalizada") else 0),
            )
            self.contagem["imagens_gravadas"] += 1

    # -- protocolo ----------------------------------------------------

    def importar_protocolos(self, registros: list[dict]) -> None:
        """Livro 1 - Protocolo.

        Aviso sobre o que vem do E-Oficio: apresentante, documento e matricula
        estao vazios em 100% dos 782 registros. Sobra o objeto em texto livre,
        o selo de prenotacao e a data limite. Importamos o que existe e a tela
        mostra o que falta, em vez de fingir um livro completo.
        """
        por_numero: dict[tuple, dict] = {}
        for p in registros:
            numero = int(p.get("intProtocolo") or 0)
            livro = norm(p.get("strLivro")) or "1A"
            if numero <= 0:
                self.rejeitar("protocolo", p.get("intChave"), "Protocolo sem numero")
                continue
            chave = (livro, numero)
            if chave in por_numero:
                self.rejeitar("protocolo", p.get("intChave"),
                              f"Protocolo {numero} repetido no livro {livro}")
                continue
            por_numero[chave] = p

        for (livro, numero), p in sorted(por_numero.items()):
            data = data_iso(p.get("dtmData"))
            limite = data_iso(p.get("dtmDataLimite"))
            cancelado = bool(p.get("bitCancelado"))
            mat = norm(p.get("strMatricula"))
            matricula_id = self.id_por_chave.get((mat, "")) if mat else None
            situacao = "CANCELADO" if cancelado else "ENCERRADO"
            self.bd.escrever(
                """INSERT INTO ri_protocolos
                   (numero, livro, data_prenotacao, hora, apresentante, apresentante_documento,
                    natureza_titulo, objeto, matricula_id, matricula_numero, data_limite,
                    data_reingresso, situacao, selo_prenotacao, suscitacao_duvida, anotacao,
                    origem, origem_chave, importacao_id, criado_em)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, 'EOFICIO',%s,%s,%s)""",
                (numero, livro, data or "", norm(p.get("strHoras")) or None,
                 norm(p.get("strApresentante")) or None, norm(p.get("strDoc")) or None,
                 None, norm(p.get("memObjeto")) or None,
                 matricula_id, mat or None, limite,
                 data_iso(p.get("dtmDataReingresso")), situacao,
                 norm(p.get("strSeloPrenotacao")) or None,
                 norm(p.get("memSuscitacaoDuvida")) or None,
                 norm(p.get("memAnotacao")) or None,
                 str(p.get("intChave")), self.importacao_id, AGORA),
            )
            self.contagem["protocolos_gravados"] = self.contagem.get("protocolos_gravados", 0) + 1

    # -- CNIB ---------------------------------------------------------

    def importar_cnib(self, ordens: list[dict], pessoas: list[dict]) -> None:
        """Copia local da Central Nacional de Indisponibilidade de Bens.

        'ativa' e derivada: ordem com cancelamento registrado deixou de valer.

        A CARGA NAO SOBRESCREVE O QUE A CENTRAL TROUXE — 18/09/2026. O espelho
        passou a ter duas origens quando o atualizador do CNIB nasceu: `EOFICIO`
        (as 50.054 que a carga trouxe, retrato de 19/03/2023) e `CNIB` (o que a
        Central respondeu depois). Quando as duas falam da mesma ordem, **manda
        a mais nova** — e e por isso que o `DO UPDATE` tem guarda: ele so escreve
        sobre linha que ainda e `EOFICIO`.

        DELA VEM O `id`, E ELE NAO SE PEGA PELO ULTIMO ID INSERIDO. Um INSERT que
        virou UPDATE nao move esse ultimo id, e a pessoa seria pendurada na
        ordem errada — em silencio. O `RETURNING` responde: devolve o `id` quando
        escreveu, e **nao devolve linha nenhuma quando a guarda barra**. Isso e o
        que faz esta funcao saber, sem adivinhar, quais ordens ela reescreveu.
        (Medido no runtime desta casa, SQLite 3.38.4, nos tres casos.)
        """
        # So as ordens que ESTA carga escreveu recebem pessoas. Nas preservadas,
        # as partes que valem sao as que a Central mandou.
        reescritas: dict[str, int] = {}   # chave no arquivo -> id local
        preservadas: set[str] = set()     # chave no arquivo -> ficou como estava

        for o in ordens:
            protocolo = norm(o.get("PROTOCOLOINDISPONIBILIDADE"))
            if not protocolo:
                # O protocolo e a identidade da ordem: e por ele que a Central
                # casa o cancelamento, e e ele que o UNIQUE guarda. Ordem sem
                # protocolo nao tem chave — entra-la seria criar linha que nada
                # acha, e a SEGUNDA estouraria a carga inteira.
                self.rejeitar("cnib_ordem", o.get("id"), "Ordem sem protocolo")
                continue

            cancelamento = norm(o.get("CANCELAMENTODEINDISPONIBILIDADE"))
            chave_arquivo = str(o.get("id"))
            linha = self.bd.escrever(
                """INSERT INTO ri_cnib_ordens
                   (protocolo_cnib, data_pedido, processo, instituicao, forum_vara,
                    solicitante, cancelamento_protocolo, cancelamento_data, ativa,
                    origem_chave, origem)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'EOFICIO')
                   ON CONFLICT(protocolo_cnib) DO UPDATE SET
                       data_pedido=excluded.data_pedido,
                       processo=excluded.processo,
                       instituicao=excluded.instituicao,
                       forum_vara=excluded.forum_vara,
                       solicitante=excluded.solicitante,
                       cancelamento_protocolo=excluded.cancelamento_protocolo,
                       cancelamento_data=excluded.cancelamento_data,
                       ativa=excluded.ativa,
                       origem_chave=excluded.origem_chave
                   WHERE ri_cnib_ordens.origem='EOFICIO'
                   RETURNING id""",
                (protocolo, data_iso(o.get("DATAPEDIDO")),
                 norm(o.get("NUMERODOPROCESSO")) or None, norm(o.get("NOMEINSTITUICAO")) or None,
                 norm(o.get("FORUMVARA")) or None, norm(o.get("USUARIO")) or None,
                 cancelamento or None, data_iso(o.get("CANCELAMENTO_DATA")),
                 0 if cancelamento else 1, chave_arquivo),
            )

            # `bd.escrever` devolve lista: vazia (e nao None) quando a guarda barra.
            if not linha:
                # Esta ordem ja e dado da Central, e o arquivo e mais velho que
                # ela. Nao se toca — nem nela, nem nas pessoas dela.
                preservadas.add(chave_arquivo)
                self.contagem["cnib_ordens_preservadas"] += 1
                continue

            ordem_id = int(linha[0]["id"])
            reescritas[chave_arquivo] = ordem_id
            # As pessoas desta ordem saem ANTES das novas entrarem. O `substituir`
            # da tela ja apagou as de origem `EOFICIO`, mas a funcao nao pode
            # depender de quem a chamou ter feito isso: sem esta linha, chama-la
            # de outro lugar somaria as partes do arquivo as que ja estao la.
            self.bd.escrever("DELETE FROM ri_cnib_pessoas WHERE ordem_id=%s", (ordem_id,))
            self.contagem["cnib_ordens"] += 1

        for p in pessoas:
            chave_arquivo = str(p.get("id_Registro"))
            if chave_arquivo in preservadas:
                # NAO E REJEICAO. E a ordem que a Central ja atualizou, e cujas
                # partes foram trocadas pelas dela de proposito — contar isto
                # como pessoa sem ordem faria a tela mostrar quarentena onde
                # houve decisao.
                self.contagem["cnib_pessoas_preservadas"] += 1
                continue
            ordem_id = reescritas.get(chave_arquivo)
            if ordem_id is None:
                self.rejeitar("cnib_pessoa", p.get("id"), "Pessoa sem ordem correspondente")
                continue
            self.bd.escrever(
                """INSERT INTO ri_cnib_pessoas(ordem_id, nome, nome_norm,
                       documento, origem_chave, origem)
                   VALUES (%s,%s,%s,%s,%s,'EOFICIO')""",
                # `nome_norm` GRAVADO NA ENTRADA, e nao calculado na consulta:
                # e por ele que a busca por nome acha a pessoa, e sem ele a
                # importacao de amanha entraria muda — achada por documento e
                # invisivel por nome.
                (ordem_id, norm(p.get("NOME")) or None,
                 normalizar_busca(p.get("NOME")) or None,
                 so_digitos(p.get("CPFCNPJ")) or None, str(p.get("id"))),
            )
            self.contagem["cnib_pessoas"] += 1

    # -- certidoes ----------------------------------------------------

    def importar_certidoes(self, registros: list[dict],
                           teores: list[dict] | None = None) -> None:
        """Certidoes ja emitidas no E-Oficio.

        O corpo nao veio na exportacao (a coluna memCertidao nao foi extraida),
        entao entram como registro historico do livro: numero, data, selo e
        matricula. Serve para a serventia saber o que ja foi expedido.
        """
        # O teor vem de exportacao separada (certidoes_teor.jsonl), porque a
        # coluna memCertidao ficou de fora da primeira extracao.
        por_id = {str(t.get("intID")): t for t in (teores or [])}

        # A identidade no E-Oficio e (protocolo, sequencia), nao a sequencia
        # sozinha - ela so numera as vias dentro de um mesmo protocolo.
        vistos: set[tuple] = set()
        for c in registros:
            data = data_iso(c.get("dtmData"))
            ano = int((data or "0000")[:4]) or 0
            numero = int(c.get("intSeq") or 0)
            protocolo = norm(c.get("strProtocoloGeral"))
            chave = (protocolo, numero)
            if not numero:
                self.rejeitar("certidao", c.get("intID"), "Certidao sem sequencia")
                continue
            if chave in vistos:
                self.rejeitar("certidao", c.get("intID"),
                              f"Certidao repetida: protocolo {protocolo}, sequencia {numero}")
                continue
            vistos.add(chave)
            mat = norm(c.get("strMatricula"))
            extra = por_id.get(str(c.get("intID")), {})
            corpo = extra.get("memCertidao") or extra.get("memCertidaoSF")
            formato = "html" if (corpo or "").lstrip().startswith("<?xml") else "texto"
            self.bd.escrever(
                """INSERT INTO ri_certidoes
                   (numero, ano, tipo, matricula_id, matricula_numero, data_emissao,
                    protocolo, selo_texto, corpo, corpo_formato, cancelada,
                    origem, origem_chave, importacao_id, emitida_em)
                   VALUES (%s,%s, 'INTEIRO_TEOR', %s,%s,%s,%s,%s,%s, %s, 0,
                           'EOFICIO', %s,%s,%s)""",
                (numero, ano, self.id_por_chave.get((mat, "")), mat or None, data or "",
                 protocolo or None,
                 norm(c.get("strSelo_Certidao")) or None,
                 corpo or norm(c.get("strDadosInformativo")) or None,
                 formato,
                 str(c.get("intID")), self.importacao_id, AGORA),
            )
            self.contagem["certidoes"] = self.contagem.get("certidoes", 0) + 1
            if corpo:
                self.contagem["certidoes_com_teor"] = self.contagem.get("certidoes_com_teor", 0) + 1

    # -- numeracao ----------------------------------------------------

    def fixar_numeracao(self) -> list[tuple[str, int]]:
        """Fixa o proximo numero por livro a partir do maior em uso."""
        # Le o maior e grava o proximo: a mesma trava de quem numera a
        # matricula (`ri_correcoes`, abertura em `ri_web`).
        self.bd.travar("ri_numeracao.livro")
        resultado = []
        for linha in self.bd.ler(
            """SELECT livro_norm, MAX(substring(numero FROM '^[0-9]+')::bigint) AS maior
               FROM ri_matriculas
               WHERE numero ~ '^[0-9]' GROUP BY livro_norm ORDER BY livro_norm"""
        ):
            livro, maior = linha["livro_norm"], int(linha["maior"] or 0)
            self.bd.escrever(
                """INSERT INTO ri_numeracao(livro, proximo_numero, maior_em_uso, fixado_em, fixado_por, observacao)
                   VALUES (%s,%s,%s,%s,%s,%s)
                   ON CONFLICT(livro) DO UPDATE SET
                     proximo_numero=excluded.proximo_numero,
                     maior_em_uso=excluded.maior_em_uso,
                     fixado_em=excluded.fixado_em""",
                (livro, maior + 1, maior, AGORA, self.usuario_id,
                 "Fixado automaticamente na importacao do acervo do E-Oficio"),
            )
            resultado.append((livro, maior + 1))
        return resultado

    # -- orquestracao -------------------------------------------------

    def executar(self, pasta: Path) -> dict:
        novo = self.bd.escrever(
            """INSERT INTO ri_importacoes(iniciada_em, usuario_id, origem, arquivo)
               VALUES (%s,%s,'EOFICIO',%s) RETURNING id""",
            (AGORA, self.usuario_id, str(pasta)),
        )
        self.importacao_id = int(novo[0]["id"])

        matriculas = ler_jsonl(pasta / "matriculas.jsonl")
        atos = ler_jsonl(pasta / "atos.jsonl")
        partes = ler_jsonl(pasta / "partes.jsonl")
        # tbOrtoga e a tabela real das partes do RI: cobre 100% dos codigos.
        # tbPessoa entra so como complemento dos poucos casos residuais.
        pessoas = ler_jsonl(pasta / "ortoga.jsonl") + ler_jsonl(pasta / "pessoas.jsonl")
        imagens = ler_jsonl(pasta / "imagens.jsonl")

        self.importar_matriculas(matriculas, atos)
        self.importar_atos(atos)
        self.importar_partes(partes, pessoas)
        self.importar_imagens(imagens)
        self.importar_protocolos(ler_jsonl(pasta / "protocolos.jsonl"))
        self.importar_cnib(ler_jsonl(pasta / "cnib_registro.jsonl"),
                           ler_jsonl(pasta / "cnib_individuo.jsonl"))
        self.importar_certidoes(ler_jsonl(pasta / "certidoes.jsonl"),
                                ler_jsonl(pasta / "certidoes_teor.jsonl"))
        numeracao = self.fixar_numeracao()

        for entidade, chave, motivo, conteudo in self.rejeitados:
            self.bd.escrever(
                """INSERT INTO ri_rejeitados(importacao_id, entidade, chave_origem, motivo, conteudo)
                   VALUES (%s,%s,%s,%s,%s)""",
                (self.importacao_id, entidade, chave, motivo, conteudo),
            )

        relatorio = dict(self.contagem)
        relatorio["numeracao"] = {l: n for l, n in numeracao}
        self.bd.escrever(
            """UPDATE ri_importacoes SET concluida_em=%s, matriculas_lidas=%s, matriculas_gravadas=%s,
                 atos_lidos=%s, atos_gravados=%s, partes_lidas=%s, partes_gravadas=%s,
                 rejeitados=%s, relatorio=%s WHERE id=%s""",
            (datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
             self.contagem["matriculas_lidas"], self.contagem["matriculas_gravadas"],
             self.contagem["atos_lidos"], self.contagem["atos_gravados"],
             self.contagem["partes_lidas"], self.contagem["partes_gravadas"],
             self.contagem["rejeitados"],
             json.dumps(relatorio, ensure_ascii=False), self.importacao_id),
        )
        return relatorio


def main() -> int:
    ap = argparse.ArgumentParser(description="Importa o acervo de RI do E-Oficio.")
    ap.add_argument("--origem", required=True, help="pasta com os arquivos .jsonl")
    ap.add_argument("--banco", default="ri_teste.sqlite3")
    ap.add_argument("--simular", action="store_true", help="nao grava; so relata")
    args = ap.parse_args()

    pasta = Path(args.origem)
    if not pasta.is_dir():
        print(f"Pasta nao encontrada: {pasta}")
        return 2

    con = banco_pg.conectar(args.banco)
    banco(con).escrever("CREATE TABLE IF NOT EXISTS users(id bigint PRIMARY KEY)")
    init_ri_schema(con)

    imp = Importador(con)
    relatorio = imp.executar(pasta)

    if args.simular:
        con.rollback()
        print("\n[SIMULACAO] nada foi gravado.")
    else:
        con.commit()

    print("\n===== RELATORIO DA IMPORTACAO =====")
    for chave in ("matriculas_lidas", "matriculas_gravadas", "atos_lidos", "atos_gravados",
                  "partes_lidas", "partes_gravadas", "imagens_gravadas", "protocolos_gravados",
                  "cnib_ordens", "cnib_pessoas", "certidoes", "certidoes_com_teor",
                  "rejeitados"):
        print(f"  {chave:22s} {relatorio[chave]:>7}")
    print("\n  Numeracao fixada por livro:")
    for livro, prox in sorted(relatorio["numeracao"].items()):
        print(f"    {livro:8s} proximo numero: {prox}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
