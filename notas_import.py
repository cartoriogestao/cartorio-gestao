"""
Carga do acervo do Tabelionato de Notas, a partir da exportacao do E-Oficio.

ORDEM DA CARGA, E POR QUE ELA IMPORTA
    1. dominios das centrais   (nao dependem de ninguem)
    2. cartoes de autografo    (o reconhecimento e o ato de livro apontam para ca)
    3. imagens das assinaturas (dependem do cartao)
    4. reconhecimentos e presencas
    5. autenticacoes
    6. livros e modelos
    7. atos de livro e suas partes

    Inverter isso quebra chave estrangeira. Ja aconteceu: na carga da tabela de
    emolumentos as vigencias entraram por ultimo e a producao recusou tudo,
    porque la o PRAGMA foreign_keys esta LIGADO e no teste estava desligado.
    Desde entao a ordem e explicita e o teste roda com a trava ligada.

REPETIVEL POR CONSTRUCAO
    Todo INSERT e OR IGNORE contra um indice unico parcial sobre
    (origem, origem_chave). Rodar duas vezes nao duplica, e o que foi digitado
    a mao — que tem origem MANUAL e fica fora do indice — sobrevive intacto.

O QUE NAO ENTRA CALADO
    Linha que nao da para aproveitar vai para nt_rejeitados com o motivo e o
    conteudo original. Carga que descarta em silencio e pior do que carga que
    falha: ninguem descobre o que ficou para tras.
"""
from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from notas_schema import init_notas_schema

# Nome do arquivo exportado -> o que ele contem. Os nomes vem do
# EXPORTAR_NOTAS.ps1 e do EXPORTAR_NOTAS_2.ps1.
ARQUIVOS = {
    "cartoes": "firma_cartao.jsonl",
    "imagens": "firma_imagem.jsonl",
    "reconhecimentos": "reconhecimento.jsonl",
    "reconhecimento_partes": "reconhecimento_pessoas.jsonl",
    "presencas": "reconhecimento_presenca.jsonl",
    "autenticacoes": "autenticacao.jsonl",
    "procuracoes": "procuracao.jsonl",
    "outorgantes": "procuracao_outorgante.jsonl",
    "outorgados": "procuracao_outorgado.jsonl",
    "testemunhas": "procuracao_testemunha.jsonl",
    "escrituras": "escritura.jsonl",
    "escritura_partes": "escritura_parte.jsonl",
    "escritura_testemunhas": "escritura_testemunha.jsonl",
    "livros": "livro_escritura.jsonl",
    "modelos_procuracao": "dom_tipo_procuracao.jsonl",
    "modelos_escritura": "dom_tipo_escritura.jsonl",
    "censec_tipos": "censec_tipo_ato.jsonl",
    "censec_naturezas": "censec_natureza_escritura.jsonl",
    "censec_qualificacoes": "censec_qualificacao.jsonl",
    "doi_transacoes": "doi_tipo_transacao.jsonl",
    "doi_tipos_imovel": "doi_tipo_imovel.jsonl",
}


# ------------------------------------------------------------- leitura

def _ler(caminho: Path) -> Iterator[dict]:
    if not caminho.exists():
        return
    with caminho.open(encoding="utf-8", errors="replace") as fh:
        for linha in fh:
            linha = linha.strip()
            if linha:
                try:
                    yield json.loads(linha)
                except json.JSONDecodeError:
                    continue


def _txt(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _digitos(v: Any) -> str | None:
    d = "".join(c for c in str(v or "") if c.isdigit())
    return d or None


def _data(v: Any) -> str | None:
    """Devolve AAAA-MM-DD. O E-Oficio exporta 'AAAA-MM-DD HH:MM:SS'."""
    s = _txt(v)
    if not s:
        return None
    return s[:10] if len(s) >= 10 and s[4] == "-" else None


def _hora(v: Any) -> str | None:
    s = _txt(v)
    if s and len(s) >= 19:
        return s[11:19]
    return s if s and ":" in s else None


def _sim(v: Any) -> int:
    return 1 if v in (True, 1, "1", "True", "true", "S", "SIM") else 0


def _centavos(v: Any) -> int | None:
    """Dinheiro em CENTAVOS inteiros. Ponto flutuante em dinheiro erra."""
    if v in (None, "", 0):
        return None
    try:
        return int(round(float(v) * 100))
    except (TypeError, ValueError):
        return None


def _censec_do_modelo(r: dict) -> tuple[str | None, int | None, int | None, int | None]:
    """De que central e o modelo, e o que o codigo dele significa.

    POR QUE NAO E UM `r.get()` DIRETO
        O E-Oficio tem DUAS colunas de nome quase igual em `tbTipoEscritura`:
        `intNaturezaOperacaoCENSEC` e `intNaturezaOperacao_CENSEC`, com
        sublinhado. A primeira e nula nas cinco linhas; o valor esta na
        segunda. A carga lia a errada, e por isso os 258 atos do acervo
        ficaram todos sem natureza da CENSEC.

    O CODIGO MUDA DE SIGNIFICADO CONFORME A CENTRAL
        Na CEP e natureza de escritura; na CESDI e tipo de ato; no RCTO e tipo
        de testamento. Confere com o dominio: o modelo CERRADO/RCTO traz 2, que
        e `Cerrado`, e o ADITAMENTO/RCTO traz 1, que e `Aditamento`. Guardar os
        tres na mesma coluna poria numero certo no lugar errado.

    O QUE ISSO NAO RESOLVE
        Os 40 atos do modelo generico "Escritura" cairiam todos em natureza 1,
        ACORDO EXTRAJUDICIAL, que e marcacao de fabrica do E-Oficio e nao o que
        os atos sao. Classificar cada escritura e do tabeliao — o sistema mede
        e mostra, nao adivinha.
    """
    central = _txt(r.get("strCENSEC"))
    codigo = r.get("intNaturezaOperacao_CENSEC")
    if codigo is None:
        codigo = r.get("intNaturezaOperacaoCENSEC")
    if codigo is None or not central:
        return central, None, None, None
    central = central.upper()
    if central == "CESDI":
        return central, None, int(codigo), None
    if central == "RCTO":
        return central, None, None, int(codigo)
    return central, int(codigo), None, None


def normalizar(texto: Any) -> str | None:
    """Forma sem acento e sem caixa, para busca."""
    s = _txt(texto)
    if not s:
        return None
    t = unicodedata.normalize("NFD", s.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", t).strip() or None


# --------------------------------------------------------------- RTF

# Grupos do RTF que NAO sao o teor. Entrando num destes, tudo dentro dele e
# descartado, inclusive o que estiver aninhado mais fundo.
#
# `pict` e `shppict` sao os que mais estragavam: a imagem vem como hexadecimal
# puro e virava vinte mil caracteres de `ffd8ffe000104a4649...` na frente do
# ato.
_RTF_MUDOS = frozenset("""
    fonttbl colortbl stylesheet info generator listtable listoverridetable
    rsidtbl pict shppict nonshppict themedata colorschememapping latentstyles
    datastore xmlnstbl pntext pntxta pntxtb objdata mmathPr wgrffmtfilter
    panose falt fname filetbl bkmkstart bkmkend
""".split())


def rtf_para_texto(bruto: Any) -> str | None:
    """Tira o texto de um RTF sem biblioteca externa.

    O E-Oficio guarda o teor do ato em RTF (`memProcuracao`, `memEscritura`).
    Nao interpreta formatacao: o que interessa e o TEOR, e a formatacao
    original nao e o ato — o ato e o que esta escrito no livro.

    POR QUE ISTO CONTA CHAVES EM VEZ DE USAR EXPRESSAO REGULAR
        A primeira versao removia os grupos com regex. Regex nao casa estrutura
        aninhada, e a tabela de fontes do E-Oficio tem DOIS niveis:

            {\\fonttbl{\\f0\\fswiss{\\*\\panose 020B06...}Arial;}...}

        O padrao descia um nivel so. Resultado: as 45 escrituras do acervo
        comecavam com "Arial; Calibri; Times New Roman; Symbol; Normal;
        [Normal];No Spacing;caption;" seguidos do hexadecimal de uma imagem
        embutida — CERCA DE 19 MIL CARACTERES DE LIXO antes da primeira palavra
        do ato. Ia assim para o traslado e para a certidao.

        Contando chaves, o aninhamento deixa de importar: entrou num grupo mudo,
        sai tudo dele, na profundidade que for.
    """
    s = _txt(bruto)
    if not s or not s.lstrip().startswith("{\\rtf"):
        return s

    saida: list[str] = []
    # Uma pilha de "estou dentro de grupo que deve ser descartado?".
    mudo = [False]
    i, n = 0, len(s)
    while i < n:
        c = s[i]

        if c == "{":
            mudo.append(mudo[-1])
            i += 1
            continue

        if c == "}":
            if len(mudo) > 1:
                mudo.pop()
            i += 1
            continue

        if c == "\\":
            # \* marca destino que o leitor pode ignorar inteiro.
            if i + 1 < n and s[i + 1] == "*":
                mudo[-1] = True
                i += 2
                continue
            # \'e9 — byte escapado
            m = re.match(r"\\'([0-9a-fA-F]{2})", s[i:])
            if m:
                if not mudo[-1]:
                    saida.append(bytes([int(m.group(1), 16)]).decode("cp1252", "replace"))
                i += m.end()
                continue
            # \uNNNN — unicode, seguido de um caractere de reposicao
            m = re.match(r"\\u(-?\d+)\s?\??", s[i:])
            if m:
                if not mudo[-1]:
                    saida.append(chr(int(m.group(1)) % 65536))
                i += m.end()
                continue
            # palavra de controle
            m = re.match(r"\\([a-zA-Z]+)(-?\d+)?[ ]?", s[i:])
            if m:
                palavra = m.group(1)
                if palavra in _RTF_MUDOS:
                    mudo[-1] = True
                elif not mudo[-1]:
                    if palavra in ("par", "line", "sect", "pard"):
                        saida.append("\n")
                    elif palavra == "tab":
                        saida.append("\t")
                i += m.end()
                continue
            # \\ \{ \} — caractere literal
            if i + 1 < n:
                if not mudo[-1]:
                    saida.append(s[i + 1])
                i += 2
                continue
            i += 1
            continue

        if not mudo[-1]:
            saida.append(c)
        i += 1

    linhas = [re.sub(r"[ \t]+", " ", l).strip() for l in "".join(saida).split("\n")]
    texto = "\n".join(l for l in linhas if l)
    return texto or None


def texto_para_html(texto: Any) -> str | None:
    t = _txt(texto)
    if not t:
        return None
    esc = lambda s: s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return "\n".join(f"<p>{esc(l)}</p>" for l in t.split("\n") if l.strip())


# ------------------------------------------------------------- a carga

class Carga:
    """Roda a carga inteira e conta tudo o que aconteceu."""

    def __init__(self, con: sqlite3.Connection, pasta: Path,
                 progresso=None) -> None:
        self.con = con
        self.pasta = Path(pasta)
        self.progresso = progresso
        self.agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.contas: dict[str, int] = {}
        self.importacao_id: int | None = None
        self.cartao_por_codigo: dict[int, int] = {}

    # ---- utilidades internas

    def _conta(self, chave: str, n: int = 1) -> None:
        if n:
            self.contas[chave] = self.contas.get(chave, 0) + n

    def _contar_insert(self, cur, chave: str) -> bool:
        """Conta pelo rowcount do proprio INSERT OR IGNORE.

        Na primeira versao eu contava por `con.total_changes`, que e CUMULATIVO
        na conexao: a segunda carga relatou 4.060 cartoes importados tendo
        inserido zero. O numero do relatorio tem de ser o que aconteceu, senao
        a carga incremental fica impossivel de conferir.
        """
        if cur.rowcount:
            self._conta(chave)
            return True
        self._conta(f"{chave}_ja_existentes")
        return False

    def _aviso(self, texto: str) -> None:
        if self.progresso:
            self.progresso(texto)

    def _rejeita(self, tabela: str, chave: Any, motivo: str, linha: dict) -> None:
        self.con.execute(
            """INSERT INTO nt_rejeitados
               (importacao_id, tabela, chave, motivo, conteudo, criado_em)
               VALUES (?,?,?,?,?,?)""",
            (self.importacao_id, tabela, str(chave), motivo,
             json.dumps(linha, ensure_ascii=False)[:4000], self.agora))
        self._conta(f"rejeitados_{tabela}")

    def _arq(self, chave: str) -> Path:
        return self.pasta / ARQUIVOS[chave]

    # ---- 1. dominios

    def dominios(self) -> None:
        self._aviso("domínios das centrais")
        for r in _ler(self._arq("censec_tipos")):
            self.con.execute(
                "INSERT OR REPLACE INTO nt_censec_tipos(central,codigo,descricao) VALUES (?,?,?)",
                (_txt(r.get("tipo")), r.get("codigo"), _txt(r.get("descricao"))))
            self._conta("censec_tipos")
        for r in _ler(self._arq("censec_naturezas")):
            self.con.execute(
                "INSERT OR REPLACE INTO nt_censec_naturezas(codigo,tipo_ato,descricao) VALUES (?,?,?)",
                (r.get("intCodigoNaturezaEscritura"), r.get("intCodigoTipoAto"),
                 _txt(r.get("strDescricao"))))
            self._conta("censec_naturezas")
        for r in _ler(self._arq("censec_qualificacoes")):
            self.con.execute(
                "INSERT OR REPLACE INTO nt_censec_qualificacoes(codigo,central,descricao) VALUES (?,?,?)",
                (r.get("intCodigo"), _txt(r.get("strCENSEC")), _txt(r.get("strDescricao"))))
            self._conta("censec_qualificacoes")
        for r in _ler(self._arq("doi_transacoes")):
            self.con.execute(
                "INSERT OR REPLACE INTO nt_doi_transacoes(codigo,descricao,ativo) VALUES (?,?,?)",
                (r.get("intCodigoDOI"), _txt(r.get("strDescricao")), _sim(r.get("bitativo"))))
            self._conta("doi_transacoes")
        for r in _ler(self._arq("doi_tipos_imovel")):
            # Esta tabela do E-Oficio foge do padrao das outras: a chave se
            # chama "Id" e a descricao vem em minuscula. Descoberto lendo o
            # arquivo, depois de a primeira carga trazer zero linhas.
            cod = (r.get("Id") or r.get("intCodigoDOI")
                   or r.get("codigo") or r.get("intCodigo"))
            desc = _txt(r.get("strDescricao") or r.get("descricao"))
            if cod is None or not desc:
                continue
            self.con.execute(
                "INSERT OR REPLACE INTO nt_doi_tipos_imovel(codigo,descricao) VALUES (?,?)",
                (cod, desc))
            self._conta("doi_tipos_imovel")

    # ---- 2. cartoes de autografo

    def cartoes(self) -> None:
        self._aviso("cartões de autógrafo")
        for r in _ler(self._arq("cartoes")):
            codigo = r.get("intCodigoFirma")
            nome = _txt(r.get("strNome"))
            if codigo is None or not nome:
                self._rejeita("nt_cartoes", codigo, "sem código ou sem nome", r)
                continue
            cur = self.con.execute(
                """INSERT OR IGNORE INTO nt_cartoes
                   (numero, nome, nome_norm, tipo_pessoa, documento, rg, rg_orgao,
                    rg_uf, rg_emissao, nascimento, sexo, nacionalidade, naturalidade,
                    estado_civil, conjuge, profissao, pai, mae, endereco,
                    endereco_numero, endereco_complemento, bairro, cidade, uf, cep,
                    telefone, celular, email, local_trabalho, endereco_trabalho,
                    como_assina, pessoa_exposta, restricao_terrorismo, bloqueado,
                    motivo_bloqueio, somente_autenticidade, ativo, biometria,
                    biometria_dedo, selo_abertura, observacao, abertura,
                    origem, origem_chave, importacao_id, criado_em)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                           ?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'EOFICIO', ?, ?, ?)""",
                (codigo, nome, normalizar(nome),
                 (_txt(r.get("strTipoPessoa")) or "F")[:1],
                 _digitos(r.get("strCPF")) or _digitos(r.get("strCNPJ")),
                 _txt(r.get("strCI")), _txt(r.get("strRG_orgaoEmissor")),
                 _txt(r.get("strRG_ufOrgaoEmissor")), _data(r.get("dtmRG_Emissao")),
                 _data(r.get("dtmDNasc")), _txt(r.get("strSexo")),
                 _txt(r.get("strNacionalidade")), _txt(r.get("strNaturalidade")),
                 _txt(r.get("strEstadoCivil")), _txt(r.get("strConjuge")),
                 _txt(r.get("strProfissao")), _txt(r.get("strPai")), _txt(r.get("strMae")),
                 _txt(r.get("strEndereco")), _txt(r.get("strEndereco_Numero")),
                 _txt(r.get("strEndereco_Complemento")), _txt(r.get("strBairro")),
                 _txt(r.get("strCidade")), _txt(r.get("strUF")), _digitos(r.get("strCep")),
                 _digitos(r.get("strFone")), _digitos(r.get("strCelular")),
                 _txt(r.get("strEmail")), _txt(r.get("strLocalTrabalho")),
                 _txt(r.get("strEndProfissao")), _txt(r.get("strQueAssina")),
                 _sim(r.get("bitPPE")), _sim(r.get("biTerrorista")),
                 _sim(r.get("bitBloqueado")), _txt(r.get("strMotivoBloq")),
                 _sim(r.get("bitRecSomenteAutenticidade")),
                 _sim(r.get("bitAtivo")) if r.get("bitAtivo") is not None else 1,
                 # A DIGITAL ENTRA COMO ESTA, E O DEDO NAO ENTRA — medido em
                 # 27/08/2026, e as duas metades merecem explicacao.
                 #
                 #   O DEDO: eu lia `intDedoPadraoBiometria`, que e propriedade
                 #   da SERVENTIA (mora em `tbPropRFirma`, uma linha so) e nunca
                 #   existe na linha da pessoa. O codigo parecia importar o dedo
                 #   e importava None em 462 de 462. O dedo de verdade esta em
                 #   `tbBiometria.intIDdedo` — 436 de 436, polegar direito em
                 #   433 —, que este importador nao le: ele le arquivo
                 #   exportado, e aquela tabela so existe no acervo.
                 #
                 #   Deixar None honesto e melhor que ler o campo errado: o
                 #   campo errado da a impressao de que o dado foi buscado.
                 #
                 #   A DIGITAL: entra como esta, e esta DANIFICADA na origem.
                 #   Dos 436 templates de `tbBiometria`, **so 2 sao base64
                 #   valido**; o resto tem asteriscos no meio (mediana de 5,
                 #   maximo 18) e comprimento que nao fecha. Trocar o asterisco
                 #   por `+` ou por `/` recupera 36%, o que nao e recuperacao:
                 #   e chute com aparencia de conserto. Guardar o texto como
                 #   veio preserva a chance de alguem que conheca o formato
                 #   original recupera-lo; reescrever agora fecharia essa porta.
                 _txt(r.get("memDigital")), None,
                 _txt(r.get("strSeloFirma")), _txt(r.get("memObs")),
                 _data(r.get("dtmAbertura")), str(codigo), self.importacao_id, self.agora))
            self._contar_insert(cur, "cartoes")
        # indice de tradução: codigo do E-Oficio -> id nosso
        self.cartao_por_codigo = {
            int(r[0]): int(r[1]) for r in self.con.execute(
                "SELECT origem_chave, id FROM nt_cartoes WHERE origem='EOFICIO'")
            if str(r[0]).isdigit()}

    # ---- 3. imagens

    def imagens(self) -> None:
        self._aviso("imagens das assinaturas")
        for r in _ler(self._arq("imagens")):
            codigo = r.get("intCodigoFirma")
            cartao = self.cartao_por_codigo.get(codigo)
            nome = _txt(r.get("strNomeDigital"))
            if not cartao:
                self._rejeita("nt_cartao_imagens", codigo, "cartão não encontrado", r)
                continue
            if not nome:
                self._rejeita("nt_cartao_imagens", codigo, "sem nome de arquivo", r)
                continue
            # a ordem sai do sufixo: RF210703-2.JPG e a segunda via
            m = re.search(r"-(\d+)\.[A-Za-z]+$", nome)
            cur = self.con.execute(
                """INSERT OR IGNORE INTO nt_cartao_imagens
                   (cartao_id, ordem, nome_arquivo, caminho, favorita, data, criado_em)
                   VALUES (?,?,?,?,?,?,?)""",
                (cartao, int(m.group(1)) if m else 1, nome, _txt(r.get("strPath")),
                 _sim(r.get("bitFavorito")), _data(r.get("dtmData")), self.agora))
            self._contar_insert(cur, "imagens")

    # ---- 4. reconhecimentos

    def reconhecimentos(self) -> None:
        self._aviso("reconhecimentos de firma")
        # As pessoas do reconhecimento se ligam pelo SELO, nao por um id: e
        # assim no E-Oficio, e conferi que casam 13.198 dos 13.199.
        partes: dict[str, list[dict]] = {}
        for r in _ler(self._arq("reconhecimento_partes")):
            selo = _txt(r.get("strSelo"))
            if selo:
                partes.setdefault(selo, []).append(r)

        for r in _ler(self._arq("reconhecimentos")):
            chave = r.get("intID")
            data = _data(r.get("dtmData"))
            if chave is None or not data:
                self._rejeita("nt_reconhecimentos", chave, "sem chave ou sem data", r)
                continue
            texto = _txt(r.get("strTextoMontado")) or ""
            especie = "AUTENTICIDADE" if "AUTENTICIDADE" in texto.upper() else "SEMELHANCA"
            selo = _txt(r.get("strselo")) or _txt(r.get("strSelo"))
            ligadas = partes.get(selo or "", [])
            servico = ligadas[0].get("intCodigoServico") if ligadas else None
            cur = self.con.execute(
                """INSERT OR IGNORE INTO nt_reconhecimentos
                   (data, especie, selo, codigo_seguranca, servico_codigo,
                    quantidade, documento_descricao, veiculo_placa,
                    conteudo_financeiro, sinal_publico, texto, oficial,
                    origem, origem_chave, importacao_id, criado_em)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?, 'EOFICIO', ?, ?, ?)""",
                (data, especie, selo, _txt(r.get("strCodigoSeguranca")), servico,
                 r.get("intQtosporEtiqueta") or 1, _txt(r.get("strDescDoc")),
                 _txt(r.get("strPlaca")), 1 if servico == 416 else 0,
                 1 if ligadas and _sim(ligadas[0].get("bitSinalPublico")) else 0,
                 texto or None, _txt(r.get("strOficial")),
                 str(chave), self.importacao_id, self.agora))
            if not cur.rowcount:
                self._conta("reconhecimentos_ja_existentes")
                continue
            self._conta("reconhecimentos")
            rid = int(cur.lastrowid)
            for p in ligadas:
                cartao = self.cartao_por_codigo.get(p.get("intCodigoFirma"))
                if not cartao:
                    self._rejeita("nt_reconhecimento_partes", selo,
                                  "cartão não encontrado", p)
                    continue
                self.con.execute(
                    """INSERT INTO nt_reconhecimento_partes
                       (reconhecimento_id, cartao_id, criado_em) VALUES (?,?,?)""",
                    (rid, cartao, self.agora))
                self._conta("reconhecimento_partes")

    def presencas(self) -> None:
        self._aviso("termos de presença")
        for r in _ler(self._arq("presencas")):
            chave = r.get("intChave")
            nome = _txt(r.get("strNome"))
            data = _data(r.get("dtmData"))
            if chave is None or not nome or not data:
                self._rejeita("nt_presencas", chave, "sem chave, nome ou data", r)
                continue
            selo = _txt(r.get("strSelo"))
            rec = self.con.execute(
                "SELECT id FROM nt_reconhecimentos WHERE selo=? LIMIT 1", (selo,)).fetchone()
            cur = self.con.execute(
                """INSERT OR IGNORE INTO nt_presencas
                   (data, ordem, nome, documento, reconhecimento_id, selo,
                    quantidade, conteudo, oficial, origem, origem_chave,
                    importacao_id, criado_em)
                   VALUES (?,?,?,?,?,?,?,?,?, 'EOFICIO', ?, ?, ?)""",
                (data, r.get("intOrdem"), nome, _digitos(r.get("strCPF")),
                 rec[0] if rec else None, selo, r.get("intQte") or 1,
                 _txt(r.get("strConteudo")), _txt(r.get("strUserid")),
                 str(chave), self.importacao_id, self.agora))
            self._contar_insert(cur, "presencas")

    # ---- 5. autenticacoes

    def autenticacoes(self) -> None:
        self._aviso("autenticações de cópia")
        for r in _ler(self._arq("autenticacoes")):
            chave = r.get("intID")
            data = _data(r.get("dtmData"))
            if chave is None or not data:
                self._rejeita("nt_autenticacoes", chave, "sem chave ou sem data", r)
                continue
            cur = self.con.execute(
                """INSERT OR IGNORE INTO nt_autenticacoes
                   (data, tipo, selo, codigo_seguranca, servico_codigo, folhas,
                    documento_descricao, documento_tipo, texto, oficial,
                    origem, origem_chave, importacao_id, criado_em)
                   VALUES (?,?,?,?,?,?,?,?,?,?, 'EOFICIO', ?, ?, ?)""",
                (data,
                 "INTERNET" if r.get("intCodigoTextoImpresso") == 2 else "PADRAO",
                 _txt(r.get("strSelo")), _txt(r.get("strCodigoSeguranca")),
                 r.get("intCodigoServico"), r.get("intQte") or 1,
                 _txt(r.get("strDescDoc")), _txt(r.get("strTipoDoc")),
                 _txt(r.get("strTextoMontado")), _txt(r.get("strOficial")),
                 str(chave), self.importacao_id, self.agora))
            self._contar_insert(cur, "autenticacoes")

    # ---- 6. livros e modelos

    def livros(self) -> None:
        self._aviso("livros")
        for r in _ler(self._arq("livros")):
            numero = r.get("intLivro")
            if numero is None:
                continue
            desc = (_txt(r.get("strDescricaoLivro")) or "").upper()
            tipo = "ESCRITURA" if "ESCRITURA" in desc else "PROCURACAO"
            comp = _txt(r.get("strLivroComp")) or ""
            cur = self.con.execute(
                """INSERT OR IGNORE INTO nt_livros
                   (tipo, numero, complemento, descricao, folhas, folha_atual,
                    abertura, ativo, criado_em)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (tipo, str(numero), comp, _txt(r.get("strDescricaoLivro")),
                 r.get("intNFL"), r.get("intFolha"), _data(r.get("dtmDataAbertura")),
                 _sim(r.get("bitAtivo")), self.agora))
            self._contar_insert(cur, "livros")

    def modelos(self) -> None:
        self._aviso("biblioteca de modelos")
        for r in _ler(self._arq("modelos_procuracao")):
            chave = r.get("intChave")
            nome = _txt(r.get("strProcuracao"))
            corpo = rtf_para_texto(r.get("memTexto"))
            if chave is None or not nome:
                continue
            if not corpo:
                self._rejeita("nt_modelos", chave, "modelo sem texto", r)
                continue
            cur = self.con.execute(
                """INSERT OR IGNORE INTO nt_modelos
                   (codigo, tipo, nome, nome_norm, corpo, tipo_ato_censec,
                    fins_previdenciarios, ativo, origem, origem_chave, criado_em)
                   VALUES (?, 'PROCURACAO', ?,?,?,?,?,?, 'EOFICIO', ?, ?)""",
                (f"PROC-{chave}", nome, normalizar(nome), texto_para_html(corpo),
                 3 if _sim(r.get("bitFinsPrevidenciarios")) else 2,
                 _sim(r.get("bitFinsPrevidenciarios")),
                 _sim(r.get("bitAtivo")), f"PROC:{chave}", self.agora))
            self._contar_insert(cur, "modelos_procuracao")
        for r in _ler(self._arq("modelos_escritura")):
            chave = r.get("intChave")
            nome = _txt(r.get("strEscritura"))
            corpo = rtf_para_texto(r.get("memTexto"))
            if chave is None or not nome:
                continue
            if not corpo:
                # Antes isso era um `continue` calado, e tres dos cinco modelos
                # sumiam sem que ninguem soubesse. Carga que descarta em
                # silencio e pior que carga que falha.
                self._rejeita("nt_modelos", chave, "modelo de escritura sem texto", r)
                continue
            central, natureza, cesdi, testamento = _censec_do_modelo(r)
            cur = self.con.execute(
                """INSERT OR IGNORE INTO nt_modelos
                   (codigo, tipo, nome, nome_norm, corpo, central_censec,
                    natureza_censec, tipo_cesdi, tipo_testamento,
                    tipo_ato_censec, doi_transacao, com_imovel, ativo,
                    origem, origem_chave, criado_em)
                   VALUES (?, 'ESCRITURA', ?,?,?,?,?,?,?,?,?,?,1, 'EOFICIO', ?, ?)""",
                (f"ESC-{chave}", nome, normalizar(nome), texto_para_html(corpo),
                 central, natureza, cesdi, testamento,
                 r.get("intTipoCEP"), r.get("intTipoTransacaoDOI"),
                 _sim(r.get("bitComImovel")), f"ESC:{chave}", self.agora))
            self._contar_insert(cur, "modelos_escritura")

    # ---- 7. atos de livro

    def _livro_id(self, tipo: str, numero: Any) -> int | None:
        if numero in (None, ""):
            return None
        r = self.con.execute(
            "SELECT id FROM nt_livros WHERE tipo=? AND numero=? LIMIT 1",
            (tipo, str(numero))).fetchone()
        return int(r[0]) if r else None

    def procuracoes(self) -> None:
        self._aviso("procurações")
        tipos = {r["intChave"]: r for r in _ler(self._arq("modelos_procuracao"))}
        partes: dict[int, list[tuple[int, str]]] = {}
        for arq, papel in (("outorgantes", "OUTORGANTE"),
                           ("outorgados", "OUTORGADO"),
                           ("testemunhas", "TESTEMUNHA")):
            campo = {"outorgantes": "intCodigoOutorgante",
                     "outorgados": "intCodigoOutorgado",
                     "testemunhas": "intCodigoParte"}[arq]
            for r in _ler(self._arq(arq)):
                prot = r.get("intProtocolo")
                cod = r.get(campo)
                if prot is not None and cod is not None:
                    partes.setdefault(prot, []).append((cod, papel))

        for r in _ler(self._arq("procuracoes")):
            prot = r.get("intProtocolo")
            data = _data(r.get("dtmData"))
            if prot is None or not data:
                self._rejeita("nt_atos", prot, "procuração sem protocolo ou data", r)
                continue
            tipo_mod = tipos.get(r.get("intCodigoTipoProcuracao"), {})
            teor = rtf_para_texto(r.get("memProcuracao"))
            cur = self.con.execute(
                """INSERT OR IGNORE INTO nt_atos
                   (tipo, numero_ordem, livro_id, livro, folha, folha_final, data,
                    hora, situacao, natureza, modelo_codigo, interessado, teor,
                    teor_formato, traslado, folhas, assinado_serventia,
                    dispensou_testemunha, local_assinatura, acervo,
                    sem_efeito_motivo, revogado_em, observacao,
                    origem, origem_chave, importacao_id, criado_em)
                   VALUES ('PROCURACAO', ?,?,?,?,?,?,?,?,?,?,?,?, 'html',
                           ?,?,?,?,?,?,?,?,?, 'EOFICIO', ?, ?, ?)""",
                (r.get("intNumeroOrdem_Notas"),
                 self._livro_id("PROCURACAO", r.get("intLivro")),
                 _txt(r.get("intLivro")), _txt(r.get("intFolha")),
                 _txt(r.get("intFolhaFinal")), data, _txt(r.get("strHora")),
                 "SEM_EFEITO" if _txt(r.get("memMotivoSemEfeito"))
                 else ("REVOGADO" if _data(r.get("dtmDataRevogacao")) else "LAVRADO"),
                 _txt(tipo_mod.get("strProcuracao")),
                 f"PROC-{r.get('intCodigoTipoProcuracao')}"
                 if r.get("intCodigoTipoProcuracao") else None,
                 _txt(r.get("strInteressado")), texto_para_html(teor),
                 texto_para_html(rtf_para_texto(r.get("memTraslado"))),
                 r.get("intNumeroFolhas"), _sim(r.get("bitAssinadaServentia")),
                 _sim(r.get("bitDispensouTestemunha")), _txt(r.get("strLocalAssinatura")),
                 _sim(r.get("bitAcervo")), _txt(r.get("memMotivoSemEfeito")),
                 _data(r.get("dtmDataRevogacao")), _txt(r.get("memObs")),
                 f"PROC:{prot}", self.importacao_id, self.agora))
            if not cur.rowcount:
                self._conta("procuracoes_ja_existentes")
                continue
            self._conta("procuracoes")
            self._gravar_partes(int(cur.lastrowid), partes.get(prot, []))

    def _partes_de_escritura(self) -> tuple[dict, dict]:
        """As partes de cada escritura, e quantas escrituras cada protocolo tem.

        POR QUE VEM COM UMA CONTAGEM JUNTO
            `tbESC_Partes` liga a escritura pelo `strProtocolo`, e o protocolo
            NAO identifica a escritura: sao 40 protocolos para 45 escrituras.
            Tres deles cobrem 8 atos — o 2020.08.219 rendeu quatro, e o
            2020.08.163 e o 2022.03.311 renderam dois cada, na MESMA folha.

            Pendurar as mesmas partes em todas as escrituras do protocolo seria
            inventar quem compareceu a cada ato. Entao o protocolo ambiguo vai
            para a quarentena com o motivo, e o registrador resolve.

        A PARTE APONTA O CARTAO DE AUTOGRAFO
            `intCodigoParte` resolve contra `intCodigoFirma`: 72 de 72 codigos
            do acervo. Conferido antes de construir, e nao suposto pelo nome —
            os 72 nao batem com `tbOrtoga` (2 de 72) nem com `tbParte` (0).
            E boa noticia: a qualificacao completa da parte, que a CESDI e o
            RCTO exigem, ja vem do cartao.
        """
        por_protocolo: dict[str, list[tuple[int, str]]] = {}
        for arq, papel_padrao in (("escritura_partes", None),
                                  ("escritura_testemunhas", "TESTEMUNHA")):
            for r in _ler(self._arq(arq)):
                prot = _txt(r.get("strProtocolo")) or _txt(r.get("strPG"))
                cod = r.get("intCodigoParte")
                if prot is None or cod is None:
                    continue
                papel = papel_padrao or _txt(r.get("strQualificacao")) or "PARTE"
                por_protocolo.setdefault(prot, []).append((int(cod), papel))

        quantas: dict[str, int] = {}
        for r in _ler(self._arq("escrituras")):
            prot = _txt(r.get("strProtocolo"))
            if prot:
                quantas[prot] = quantas.get(prot, 0) + 1
        return por_protocolo, quantas

    def escrituras(self) -> None:
        self._aviso("escrituras")
        tipos = {r["intChave"]: r for r in _ler(self._arq("modelos_escritura"))}
        partes_esc, escrituras_do_protocolo = self._partes_de_escritura()
        for r in _ler(self._arq("escrituras")):
            # A chave e o `id`, nao o protocolo: um mesmo protocolo gera varias
            # escrituras em sequencia — 2020.08.219 rendeu quatro, nas folhas
            # 48, 53, 58 e 63 do livro 28. Usando o protocolo, cinco das 45
            # escrituras eram descartadas em silencio pelo INSERT OR IGNORE.
            chave = _txt(r.get("id")) or _txt(r.get("strProtocolo"))
            data = _data(r.get("dtmData"))
            if not chave or not data:
                self._rejeita("nt_atos", chave, "escritura sem protocolo ou data", r)
                continue
            tipo_mod = tipos.get(r.get("intCodigoTipoEscritura"), {})
            _, natureza_cep, tipo_cesdi, tipo_testamento = _censec_do_modelo(tipo_mod)
            teor = rtf_para_texto(r.get("memEscritura"))
            cur = self.con.execute(
                """INSERT OR IGNORE INTO nt_atos
                   (tipo, numero_ordem, livro_id, livro, folha, folha_final, data,
                    situacao, natureza, natureza_censec, tipo_cesdi, tipo_testamento,
                    modelo_codigo, interessado,
                    teor, teor_formato, traslado, folhas, selo, selo_arquivamento,
                    valor_transacao, valor_lavrado, base_itbi, assinado_serventia,
                    dispensou_testemunha, local_assinatura,
                    anterior_livro, anterior_folha, anterior_data, anterior_cartorio,
                    anterior_uf, casamento_data, regime_bens, filhos_menores,
                    filhos_maiores, responsavel_menores, responsavel_maiores,
                    doi_transacao, doi_endereco, com_imovel, acervo, observacao,
                    doi_matricula, anterior_livro_complemento,
                    anterior_folha_complemento,
                    origem, origem_chave, importacao_id, criado_em)
                   VALUES ('ESCRITURA', ?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'html',
                           ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,
                           ?,?,?, 'EOFICIO', ?, ?, ?)""",
                (r.get("intNumeroOrdem_Notas"),
                 self._livro_id("ESCRITURA", r.get("intLivroRegistro")),
                 _txt(r.get("strLivro_Registro")), _txt(r.get("strFolha_Registro")),
                 _txt(r.get("strFolhaFinal_Registro")), data,
                 "LAVRADO", _txt(tipo_mod.get("strEscritura")),
                 natureza_cep, tipo_cesdi, tipo_testamento,
                 f"ESC-{r.get('intCodigoTipoEscritura')}"
                 if r.get("intCodigoTipoEscritura") else None,
                 _txt(r.get("strApresentante")), texto_para_html(teor),
                 texto_para_html(rtf_para_texto(r.get("memTraslado"))),
                 r.get("intNumerosFolhas"), _txt(r.get("strSelo_Padrao")),
                 _txt(r.get("strSelo_Arquivamento")),
                 _centavos(r.get("curValorTransacao")), _centavos(r.get("curValorLavrado")),
                 _centavos(r.get("curDOI_BaseCalculoITBI")),
                 _sim(r.get("bitAssinadaServentia")), _sim(r.get("bitDispensouTestemunha")),
                 _txt(r.get("strLocalAssinatura")),
                 _txt(r.get("strLivro_AtoAnterior")), _txt(r.get("strFolha_AtoAnterior")),
                 _data(r.get("dtmCENSEC_DataAtoAnteriorLavrado")),
                 _txt(r.get("strCartorio_AtoAnterior")), _txt(r.get("strUF_AtoAnterior")),
                 _data(r.get("dtmCasamento")) or _data(r.get("dtmCENSEC_DataCasamento")),
                 _txt(r.get("strRegimeBens")) or _txt(r.get("strCENSEC_RegimeBens")),
                 r.get("intQteFilhosMenores"), r.get("intQteFilhosMaiores"),
                 _txt(r.get("strResponsavelFilhosMenores")),
                 _txt(r.get("strResponsavelFilhosMaiores")),
                 r.get("intDOI_Alienacao_Forma"),
                 _txt(r.get("strDOI_Endereco_logradouro")),
                 _sim(tipo_mod.get("bitComImovel")), _sim(r.get("bitAcervo")),
                 _txt(r.get("memObs")), _txt(r.get("strProtocoloGeral")),
                 # A CENSEC identifica o ato anterior pela chave completa: sem
                 # o complemento, dois atos na mesma folha viram duplicidade.
                 _txt(r.get("strLivroComp_AtoAnterior"))
                 or _txt(r.get("strCENSEC_REFERENTELIVROCOMPLEMENTO")),
                 _txt(r.get("strFolhaComp_AtoAnterior"))
                 or _txt(r.get("strCENSEC_REFERENTEFOLHACOMPLEMENTO")),
                 f"ESC:{chave}", self.importacao_id, self.agora))
            if not self._contar_insert(cur, "escrituras"):
                continue

            prot = _txt(r.get("strProtocolo"))
            lista = partes_esc.get(prot or "", [])
            if not lista:
                continue
            if escrituras_do_protocolo.get(prot, 0) > 1:
                # Ambiguo por construcao: o protocolo rendeu mais de uma
                # escritura e as partes nao dizem qual. Separar e mostrar, nao
                # adivinhar.
                self._rejeita(
                    "nt_ato_partes", prot,
                    f"protocolo {prot} rende "
                    f"{escrituras_do_protocolo[prot]} escrituras — não dá para "
                    "saber quais das partes compareceram a este ato",
                    # Guarda o cartao junto com o papel: a tela que resolve a
                    # duvida precisa oferecer PESSOAS, e nao so o rotulo.
                    {"ato_id": int(cur.lastrowid),
                     "livro": _txt(r.get("strLivro_Registro")),
                     "folha": _txt(r.get("strFolha_Registro")),
                     "partes": [{"cartao_id": self.cartao_por_codigo.get(codigo),
                                 "codigo": codigo, "papel": papel}
                                for codigo, papel in lista]})
                self._conta("escritura_partes_ambiguas")
                continue
            self._gravar_partes(int(cur.lastrowid), lista)

    def _gravar_partes(self, ato_id: int, lista: list[tuple[int, str]]) -> None:
        for ordem, (codigo, papel) in enumerate(lista, 1):
            cartao = self.cartao_por_codigo.get(codigo)
            dados = self.con.execute(
                "SELECT nome, documento, tipo_pessoa FROM nt_cartoes WHERE id=?",
                (cartao,)).fetchone() if cartao else None
            if not dados:
                self._rejeita("nt_ato_partes", codigo,
                              "parte aponta cartão inexistente",
                              {"ato_id": ato_id, "codigo": codigo, "papel": papel})
                continue
            self.con.execute(
                """INSERT INTO nt_ato_partes
                   (ato_id, cartao_id, nome, nome_norm, documento, tipo_pessoa,
                    qualificacao, testemunha, ordem, criado_em)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (ato_id, cartao, dados[0], normalizar(dados[0]), dados[1],
                 dados[2] or "F", papel, 1 if papel == "TESTEMUNHA" else 0,
                 ordem, self.agora))
            self._conta("ato_partes")

    # ---- orquestracao

    def rodar(self) -> dict:
        init_notas_schema(self.con)
        cur = self.con.execute(
            """INSERT INTO nt_importacoes (iniciada_em, origem, pasta, situacao)
               VALUES (?, 'EOFICIO', ?, 'EM_ANDAMENTO')""",
            (self.agora, str(self.pasta)))
        self.importacao_id = int(cur.lastrowid)

        self.dominios()
        self.cartoes()
        self.imagens()
        self.reconhecimentos()
        self.presencas()
        self.autenticacoes()
        self.livros()
        self.modelos()
        self.procuracoes()
        self.escrituras()

        self.con.execute(
            """UPDATE nt_importacoes SET terminada_em=?, resumo=?, situacao='CONCLUIDA'
               WHERE id=?""",
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
             json.dumps(self.contas, ensure_ascii=False), self.importacao_id))
        return dict(self.contas)


def importar(con: sqlite3.Connection, pasta: str | Path, progresso=None) -> dict:
    """Carrega o acervo de notas. Pode rodar quantas vezes precisar."""
    return Carga(con, Path(pasta), progresso).rodar()
