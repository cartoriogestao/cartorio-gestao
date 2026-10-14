"""
Carga do acervo para as atribuicoes novas — Protesto, RCPN, RCPJ/RTD e Livro 3.

DE ONDE ELA LE
    Direto do `acervo_eoficio.sqlite3`, que `acervo_eoficio.py` ja carregou com
    as 229 tabelas do E-Oficio. Os importadores antigos (`ri_import`,
    `notas_import`, `caixa_import`) leem exportacoes JSONL porque nasceram
    antes do acervo existir; hoje o acervo esta no disco e ler dele dispensa
    script de exportacao.

    O acervo e SO LEITURA. Esta carga abre em modo `ro` e nao tem um unico
    INSERT contra ele.

POR QUE UM MODULO E NAO QUATRO
    As quatro cargas tem a mesma forma: ler uma tabela do acervo, mapear campo
    a campo, gravar com `INSERT OR IGNORE` sobre (origem, origem_chave), e
    contar o que entrou e o que sobrou. Escrever isso quatro vezes daria
    quatro versoes divergentes da mesma coisa — a licao do nucleo, aplicada a
    carga.

    O que varia e o MAPEAMENTO, e so ele. Cada atribuicao declara o seu.

REPETIVEL POR CONSTRUCAO
    A chave de origem e o `intChave` da tabela de origem, e todo INSERT e
    `OR IGNORE` sobre `UNIQUE(origem, origem_chave)`. Rodar duas vezes nao
    duplica; o que foi digitado a mao tem `origem='MANUAL'` e chave nula, que
    o UNIQUE do SQLite nao alcanca — logo sobrevive intacto.

NADA ENTRA CALADO, E NADA SAI CALADO
    Cada carga devolve `lidos`, `inseridos`, `repetidos` e `rejeitados`, com o
    motivo de cada rejeicao. A regra da casa vem de um caso real: houve
    contador que relatou 4.060 cartoes numa rodada que inseriu ZERO. Numero
    que a carga informa e numero que ela conferiu no banco depois de gravar.

O QUE ESTA CARGA NAO FAZ
    Nao ocupa lugar em livro pelo nucleo. O ato do acervo JA TEM livro, folha
    e numero — vindos do livro fisico —, e mandar `escrituracao.reservar()`
    achar lugar para ele reescreveria a historia. O lugar do acervo entra como
    esta; o nucleo serve o ato NOVO.

FUNDAMENTO
    LEVANTAMENTO_QUATRO_ATRIBUICOES.md — o acervo medido em 20/08/2026.
    LEVANTAMENTO_PROTESTO.md — o Protesto medido em 21/08/2026.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Callable, Iterable

# `ato_selado` entra so pela LISTA DAS TABELAS DE ATO — e a mesma lista que
# o resto da casa usa para saber onde um selo pode estar amarrado. Escrever
# a lista de novo aqui seria a segunda copia divergindo na primeira tabela
# de ato que alguem criasse.
import ato_selado
import implantacao as IMP
import ibge_schema as IB
from pt_schema import normalizar_nome
# `so_digitos` vem do `ri_schema` porque e a MESMA funcao que guardou os
# documentos das 3.986 partes do Livro 2 — o Livro 3 tem de sair na mesma
# forma, senao a busca por documento acha um e nao acha o outro.
from ri_schema import so_digitos

NOME_ACERVO = "acervo_eoficio.sqlite3"

# O que se escreve onde o acervo nao tem o dado, e ele e obrigatorio. A frase
# aparece na tela e na certidao, e e melhor assim: quem le sabe que a falta e
# do acervo antigo, e nao um erro de digitacao de agora.
SEM_NUMERO = "SEM NÚMERO NO ACERVO"
SEM_ESPECIE = "XXX"          # nao existe no contrato da CRA, e e de proposito


class CargaError(ValueError):
    """Impedimento de carga, com mensagem pronta para a tela."""


# ------------------------------------------------------------- utilidades


def abrir_acervo(caminho: str | Path) -> sqlite3.Connection:
    """Abre o acervo em SO LEITURA. Levanta com frase de balcao se nao houver."""
    p = Path(caminho)
    if p.is_dir():
        p = p / NOME_ACERVO
    if not p.exists():
        raise CargaError(
            f"Não achei o acervo do E-Ofício em {p}. Ele é carregado por "
            f"`acervo_eoficio.carregar()` e fica ao lado do banco do sistema.")
    con = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _tem_tabela(con: sqlite3.Connection, nome: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (nome,)).fetchone() is not None


def _tem_coluna(con: sqlite3.Connection, tabela: str, coluna: str) -> bool:
    """Se aquela coluna existe naquela tabela do acervo. So LE.

    POR QUE ISTO EXISTE, E NAO E ZELO: o E-Oficio mudou de versao ao longo dos
    anos, e nem todo acervo tem as mesmas colunas. `strTipoMorte` e
    `intCodigoLocalNascimento` sao dessa safra — pedir uma coluna que nao existe
    nao devolve vazio: **estoura**, e derruba a carga inteira.
    """
    try:
        return coluna in {r[1] for r in
                          con.execute(f'PRAGMA table_info("{tabela}")')}
    except sqlite3.Error:
        return False


def _colunas_que_existem(con: sqlite3.Connection, tabela: str,
                         pedidas: dict) -> dict:
    """O de-para reduzido ao que aquele acervo realmente tem. So LE."""
    tem = {r[1] for r in con.execute(f'PRAGMA table_info("{tabela}")')}
    return {alvo: origem for alvo, origem in pedidas.items() if origem in tem}


def _txt(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def _data(v: Any) -> str | None:
    """`2022-06-01 00:00:00` -> `2022-06-01`. O acervo grava com hora zerada."""
    s = _txt(v)
    if not s:
        return None
    s = s.replace("T", " ").split(" ")[0]
    return s if len(s) == 10 and s[4] == "-" else None


def _inteiro(v: Any) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _centavos(v: Any) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(round(float(v) * 100))
    except (TypeError, ValueError):
        return None


def _juntar(*partes: str | None) -> str | None:
    """Junta o que existe, separado por ponto. Nada existir devolve None."""
    vivas = [p.strip() for p in partes if p and p.strip()]
    return ". ".join(vivas) or None


# As colunas de `tbPessoa` que a carga le, com o apelido que `_pessoa` procura.
# Escritas uma vez: a consulta principal e a passada que completa o que falta
# leem as MESMAS colunas, e duas listas seriam duas listas para divergir.
_CAMPOS_PESSOA: tuple[tuple[str, str], ...] = (
    ("strRazaoSocial", "nome"), ("strTipoPessoa", "tipo"),
    ("strCGC", "cgc"), ("strCIC", "cic"),
    ("strEndereco", "endereco"), ("strNumero", "numero"),
    ("strBairro", "bairro"), ("strCep", "cep"),
    ("strCidade", "cidade"), ("strUF", "uf"),
)


def _colunas_pessoa(alias: str, prefixo: str) -> str:
    """`d.strRazaoSocial dev_nome, d.strTipoPessoa dev_tipo, ...`"""
    return ", ".join(f"{alias}.{coluna} {prefixo}_{apelido}"
                     for coluna, apelido in _CAMPOS_PESSOA)


def _pessoa(r: sqlite3.Row, prefixo: str) -> dict | None:
    """A pessoa do acervo — devedor ou cedente —, nas colunas do prefixo.

    O TIPO DIZ ONDE ESTA O DOCUMENTO, e nao o tamanho do que estiver escrito.
    Medido em 24/08/2026 nos 1.366 devedores do acervo:

        strTipoPessoa 'F'  ->  11 digitos em strCIC, strCGC vazio   (980)
        strTipoPessoa 'J'  ->  14 digitos em strCGC, strCIC vazio   (386)

    Nenhum sem documento, nenhum com os dois. Onde o tipo nao vier, vale a
    COLUNA em que o documento esta — `strCGC` e o CNPJ e `strCIC` e o CPF —,
    que e leitura do acervo e nao deducao pelo tamanho.
    """
    def campo(nome: str) -> str | None:
        try:
            return _txt(r[f"{prefixo}_{nome}"])
        except (IndexError, KeyError):
            return None

    nome = campo("nome")
    if not nome:
        return None
    cgc, cic = campo("cgc"), campo("cic")
    tipo = (campo("tipo") or "").upper()
    if tipo == "J" and cgc:
        documento_tipo, documento_numero = "CNPJ", cgc
    elif tipo == "F" and cic:
        documento_tipo, documento_numero = "CPF", cic
    elif cgc:
        documento_tipo, documento_numero = "CNPJ", cgc
    elif cic:
        documento_tipo, documento_numero = "CPF", cic
    else:
        documento_tipo, documento_numero = None, None
    endereco = campo("endereco")
    numero = campo("numero")
    if endereco and numero:
        endereco = f"{endereco}, {numero}"
    return {"nome": nome, "documento_tipo": documento_tipo,
            "documento_numero": documento_numero, "endereco": endereco,
            "bairro": campo("bairro"), "cep": campo("cep"),
            "cidade": campo("cidade"), "uf": campo("uf")}


# O TIPO DE LIVRO DENTRO DA MATRICULA DE 32 DIGITOS.
#
#   A estrutura esta medida em `CLAUDE.md`: CNS 6 + acervo 2 + servico 2 +
#   ano 4 + **tipo de livro 1** + livro 5 + folha 3 + termo 7 + DV 2. O digito
#   da posicao 15 (indice 14) e o tipo: `1` Livro A, `2` Livro B, `3`
#   B-Auxiliar, `4` Livro C, `5` C-Auxiliar, `6` Livro D, `7` Livro E.
#
#   Medido nos 192 nascimentos com matricula de 32 digitos: **todos trazem
#   `1`**, inclusive o unico que a coluna `strTipoLivro` marca como 'E'.
TIPO_DE_LIVRO_E_NA_MATRICULA = "7"


def _matricula_diz_livro_e(matricula: Any) -> bool:
    """A matricula concorda que o assento e do Livro E? So calcula.

    Matricula ausente ou de tamanho errado devolve False — e False aqui quer
    dizer «fique na especie da tabela», que e a resposta segura: assento de
    nascimento na serie de nascimento.
    """
    digitos = "".join(c for c in str(matricula or "") if c.isdigit())
    if len(digitos) != 32:
        return False
    return digitos[14] == TIPO_DE_LIVRO_E_NA_MATRICULA


def _natureza_do_titulo(titulo: Any) -> str:
    """A natureza do Livro 3, deduzida do nome do titulo.

    Deduzida e nao inventada: o texto vem do proprio acervo e diz o que o
    titulo e. Onde ele nao diz com clareza, sai `OUTRO` — que e uma natureza
    de verdade do catalogo (art. 178), e nao um rotulo de desistencia.
    """
    texto = (_txt(titulo) or "").upper()
    if "RURAL" in texto or "PIGNORAT" in texto:
        return "CEDULA_CREDITO_RURAL"
    if "BANC" in texto:
        return "CEDULA_CREDITO_BANCARIO"
    if "INDUSTRIAL" in texto:
        return "CEDULA_CREDITO_INDUSTRIAL"
    if "COMERCIAL" in texto:
        return "CEDULA_CREDITO_COMERCIAL"
    if "CONDOM" in texto:
        return "CONVENCAO_CONDOMINIO"
    if "PENHOR" in texto:
        return "CONTRATO_PENHOR_RURAL"
    return "OUTRO"


# --------------------------------------------------------------- o motor


class Carga:
    """O que uma carga fez, em numeros que foram conferidos no banco.

    REJEITADO E AVISADO SAO COISAS DIFERENTES, e misturar os dois faz o
    contador mentir. `rejeitado` nao entrou; `avisado` entrou, com alguma
    coisa anotada — o titulo sem numero, o livro com valor esquisito.

    A primeira versao contava os dois juntos e informava "11 rejeitados"
    numa rodada em que 7 deles tinham entrado. Neste projeto ja houve
    contador que relatou 4.060 cartoes numa rodada que inseriu ZERO, e a
    regra que ficou e esta: numero que a carga informa e numero conferido.
    """

    def __init__(self, nome: str):
        self.nome = nome
        self.lidos = 0
        self.inseridos = 0
        self.repetidos = 0
        self.rejeitados: list[dict] = []
        self.avisos: list[dict] = []
        # Fatos medidos que nao sao rejeicao nem aviso de LINHA: "458 titulos
        # sem cedente no acervo" e um numero sobre a carga inteira, e
        # transformar cada um deles num aviso afogaria os 7 avisos que sao de
        # linha. Nada entra calado — mas cada coisa no seu contador.
        self.contagens: dict[str, int] = {}

    def _nota(self, chave: Any, motivo: str, linha: dict | None) -> dict:
        return {"chave": chave, "motivo": motivo,
                "conteudo": json.dumps(linha or {}, ensure_ascii=False,
                                       default=str)[:2000]}

    def rejeitar(self, chave: Any, motivo: str, linha: dict | None = None) -> None:
        """A linha NAO entrou, e aqui esta por que."""
        self.rejeitados.append(self._nota(chave, motivo, linha))

    def avisar(self, chave: Any, motivo: str, linha: dict | None = None) -> None:
        """A linha ENTROU, com isto anotado."""
        self.avisos.append(self._nota(chave, motivo, linha))

    def contar(self, rotulo: str, quantos: int = 1) -> None:
        """Um fato medido sobre a carga inteira, para a tela informar."""
        self.contagens[rotulo] = self.contagens.get(rotulo, 0) + quantos

    def como_dict(self) -> dict:
        return {"nome": self.nome, "lidos": self.lidos,
                "contagens": dict(self.contagens),
                "inseridos": self.inseridos, "repetidos": self.repetidos,
                "rejeitados": len(self.rejeitados),
                "avisados": len(self.avisos),
                "motivos_da_rejeicao": sorted({r["motivo"] for r in self.rejeitados}),
                "motivos_do_aviso": sorted({r["motivo"] for r in self.avisos})}


def _executar(con: sqlite3.Connection, carga: Carga, tabela: str,
              linhas: Iterable[sqlite3.Row],
              mapear: Callable[[sqlite3.Row], dict | None],
              chave_de: Callable[[sqlite3.Row], Any],
              depois: Callable[[sqlite3.Connection, int, sqlite3.Row], None] | None = None,
              ) -> Carga:
    """O laco comum: mapeia, grava com OR IGNORE, conta o que de fato entrou.

    `mapear` devolve o dicionario de colunas, ou None para rejeitar (e ai ele
    mesmo chama `carga.rejeitar`). `depois` recebe o id gravado, para as
    tabelas filhas.

    A contagem de `inseridos` sai do `lastrowid` mudar, e nao de `rowcount`:
    `INSERT OR IGNORE` que ignora devolve rowcount 0, e e por isso que ele
    serve para distinguir novo de repetido.
    """
    for linha in linhas:
        carga.lidos += 1
        chave = chave_de(linha)
        try:
            dados = mapear(linha)
        except Exception as erro:                    # noqa: BLE001
            carga.rejeitar(chave, f"erro ao mapear: {erro}", dict(linha))
            continue
        if dados is None:
            continue
        colunas = ", ".join(dados)
        marcas = ", ".join("?" * len(dados))
        cur = con.execute(
            f"INSERT OR IGNORE INTO {tabela}({colunas}) VALUES ({marcas})",
            tuple(dados.values()))
        if cur.rowcount:
            carga.inseridos += 1
            if depois:
                depois(con, int(cur.lastrowid), linha)
        else:
            carga.repetidos += 1
    return carga


# ------------------------------------------------------------- o Protesto


def carregar_protesto(con: sqlite3.Connection, acervo: sqlite3.Connection,
                      *, agora: str) -> Carga:
    """Os titulos de `tbAvisoProtesto`, o devedor, o cedente e o apontamento.

    O DEVEDOR E O CEDENTE VEM DE `tbPessoa`, e ate 25/08/2026 nao vinham. O
    titulo entrava sem ninguem, e sem devedor nao se acha protesto por nome
    nem por CPF — que e o que o balcao pede numa certidao. Medido: os 1.366
    titulos que a carga aceita tem devedor, e ele resolve em `tbPessoa` em
    100% deles.

    O apontamento entra com o livro, a folha e o numero de ordem QUE O ACERVO
    JA TEM (`intLivroApontamento`, `intFolhaApontamento`,
    `intNumeroApontamento`) — vindos do livro fisico. Nao se chama o nucleo
    para achar lugar: o lugar existe.

    A situacao sai dos marcadores do acervo, na ordem em que eles se sobrepoem
    na vida do titulo: cancelado vence protestado, e protestado vence apontado.
    """
    carga = Carga("protesto")
    if not _tem_tabela(acervo, "tbAvisoProtesto"):
        raise CargaError("O acervo não tem `tbAvisoProtesto`.")
    # O devedor e o cedente moram em `tbPessoa`. Se ela nao estiver no acervo,
    # o titulo entra do mesmo jeito e sem devedor — carga que para inteira
    # por causa de uma tabela ligada seria pior do que carga incompleta que
    # diz o que faltou.
    # Algumas exportacoes parciais trazem `tbPessoa`, mas a tabela de avisos
    # nao traz as duas chaves de ligacao. Testar so a existencia da tabela
    # montava um JOIN com `a.intCodigoPessoa` inexistente e derrubava a carga
    # inteira. A ligacao existe apenas quando o contrato completo existe.
    tem_pessoa = (
        _tem_tabela(acervo, "tbPessoa")
        and _tem_coluna(acervo, "tbPessoa", "intCodigoPessoa")
        and _tem_coluna(acervo, "tbAvisoProtesto", "intCodigoPessoa")
        and _tem_coluna(acervo, "tbAvisoProtesto", "intCodigoCedente")
    )
    if not tem_pessoa:
        carga.contar("acervo sem `tbPessoa`: títulos entraram sem devedor")
    # A CHAVE DO CENPROT JA ESTA NO ACERVO — coluna medida em 31/08/2026:
    # `tbAvisoProtesto.strChaveUnicaCENPROT` (1.194 de 1.370 preenchidas).
    # `pt_titulos.chave_cenprot` existia desde o comeco e a carga NUNCA a
    # copiava. Nao se inventa chave: so copia o que o acervo trouxe, e so
    # quando a coluna existe naquela exportacao.
    tem_chave_cenprot = _tem_coluna(
        acervo, "tbAvisoProtesto", "strChaveUnicaCENPROT")

    def situacao(r: sqlite3.Row) -> str:
        if r["snCanceladoProtesto"]:
            return "CANCELADO"
        if r["strTipoPG"]:
            return "PAGO"
        if r["snProtestado"]:
            return "PROTESTADO"
        return "APONTADO" if r["intNumeroApontamento"] else "RECEBIDO"

    def mapear(r: sqlite3.Row) -> dict | None:
        numero = _txt(r["intNumero"])
        especie = _txt(r["strEspecie"])
        # ONZE TITULOS DO ACERVO ESTAO SEM NUMERO, E ELES NAO SAO IGUAIS.
        #
        # Sete tem especie, valor e estao protestados: sao protestos que
        # ACONTECERAM e perderam o numero do titulo pelo caminho. Quatro nao
        # tem nada — nem especie, nem valor.
        #
        # A primeira versao recusava os onze, e isso era um defeito grave:
        # protesto que existiu e nao entra faz a certidao dizer que a pessoa
        # esta limpa quando ela nao esta. Certidao que mente e pior que carga
        # que rejeita.
        #
        # Entao: sem numero mas com sinal de vida entra, com o numero marcado
        # como ausente para quem olhar saber que a falta e do acervo e nao da
        # carga. Linha sem sinal de vida nenhum e rejeitada.
        if not numero:
            tem_vida = bool(especie or _centavos(r["curValor"])
                            or _txt(r["strNossoNumero"]))
            if not tem_vida:
                carga.rejeitar(r["intChave"],
                               "linha vazia: sem número, sem espécie e sem valor",
                               dict(r))
                return None
            numero = SEM_NUMERO
            carga.avisar(r["intChave"],
                         "título sem número no acervo — entrou marcado",
                         dict(r))
        # O CEDENTE NAO VEM SEMPRE. `intCodigoCedente` esta preenchido nos
        # 1.366, mas so 908 apontam para linha que existe em `tbPessoa` — os
        # outros 458 apontam para pessoa que o acervo nao tem mais. O titulo
        # entra inteiro de todo jeito: o cedente e quem apresentou, e a falta
        # dele nao apaga o protesto. Fica contado, para a tela dizer quantos.
        cedente = _pessoa(r, "ced") if tem_pessoa else None
        if tem_pessoa and not cedente:
            carga.contar("títulos sem cedente em `tbPessoa` no acervo")
        # 28 titulos apontam a MESMA pessoa como cedente e como devedor. Isso
        # e o acervo dizendo que quem apresentou e quem foi protestado, o que
        # nao acontece na vida real — e provavelmente e digitacao do comeco.
        # A carga copia o que esta la e CONTA; corrigir por conta seria
        # inventar, e este projeto nao inventa.
        if (cedente and _inteiro(r["intCodigoCedente"])
                and _inteiro(r["intCodigoCedente"]) == _inteiro(r["intCodigoPessoa"])):
            carga.contar("títulos em que o acervo traz o mesmo cedente e devedor")

        dados = {
            "especie": especie or SEM_ESPECIE,
            "numero_titulo": numero,
            "nosso_numero": _txt(r["strNossoNumero"]),
            "data_emissao": _data(r["dtmEmissao"]),
            "data_vencimento": _data(r["dtmVencimento"]),
            "valor_centavos": _centavos(r["curValorRealTitulo"]) or 0,
            "saldo_centavos": _centavos(r["curValor"]) or 0,
            "praca_protesto": _txt(r["strPracaPgto"]),
            "tipo_endosso": _txt(r["strEndosso"]),
            "motivo_protesto": _txt(r["intMotivoProtesto"]),
            "situacao": situacao(r),
            "cedente_nome": cedente["nome"] if cedente else None,
            "cedente_documento": cedente["documento_numero"] if cedente else None,
            "cedente_endereco": cedente["endereco"] if cedente else None,
            "cedente_cep": cedente["cep"] if cedente else None,
            "cedente_cidade": cedente["cidade"] if cedente else None,
            "cedente_uf": cedente["uf"] if cedente else None,
            "origem": (_txt(r["canal_entrada"]) or "MANUAL").upper(),
            "origem_chave": f"tbAvisoProtesto:{r['intChave']}",
            "criado_em": agora,
        }
        # SO COPIA: chave presente no acervo. Sem coluna, sem valor, ou
        # string vazia — a coluna do CG fica NULL. Nunca se compoe.
        if tem_chave_cenprot:
            chave = _txt(r["strChaveUnicaCENPROT"])
            if chave:
                dados["chave_cenprot"] = chave
        return dados

    def devedores_que_faltam(c: sqlite3.Connection) -> None:
        """Poe o devedor nos titulos do acervo que ainda nao tem nenhum.

        ELE FICAVA DE FORA, e essa era a falta mais grave da carga: sem
        devedor nao se acha protesto por nome nem por CPF, e certidao de
        protesto e justamente isso que o balcao pede. A ficha do titulo ainda
        dizia "o E-Oficio guardava o devedor noutra tabela" — guardava mesmo,
        em `tbPessoa`, e a carga passava por ela sem entrar.

        POR QUE UMA PASSADA A PARTE, E NAO O `depois` DA LINHA: `_executar` so
        chama o `depois` de quem ENTROU agora. Quem rodou a carga antes de
        25/08/2026 ja tem os titulos gravados — eles voltam como `repetidos`,
        e o devedor nunca chegaria neles. Esta passada olha o que FALTA, e por
        isso serve aos dois casos com um caminho so e pode rodar quantas vezes
        precisar.

        Medido em 25/08/2026: `intCodigoPessoa` resolve em `tbPessoa` nos
        1.366 titulos que a carga aceita — 100%. Nenhum sem nome, nenhum sem
        documento, 16 sem endereco.
        """
        if not tem_pessoa:
            return
        sem_devedor = {
            str(linha["origem_chave"]): int(linha["id"])
            for linha in c.execute(
                """SELECT t.id, t.origem_chave FROM pt_titulos t
                    WHERE t.origem_chave LIKE 'tbAvisoProtesto:%'
                      AND NOT EXISTS (SELECT 1 FROM pt_devedores d
                                       WHERE d.titulo_id = t.id)""")}
        if not sem_devedor:
            return
        for r in acervo.execute(
                f"""SELECT a.intChave chave, {_colunas_pessoa('d', 'dev')}
                      FROM tbAvisoProtesto a
                      JOIN tbPessoa d ON d.intCodigoPessoa = a.intCodigoPessoa"""):
            titulo_id = sem_devedor.get(f"tbAvisoProtesto:{r['chave']}")
            if titulo_id is None:
                continue
            d = _pessoa(r, "dev")
            if not d:
                continue
            if not d["endereco"]:
                carga.contar("devedores sem endereço no acervo")
            c.execute(
                """INSERT INTO pt_devedores(titulo_id, nome, nome_norm,
                       documento_tipo, documento_numero, endereco, bairro,
                       cep, cidade, uf)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (titulo_id, d["nome"], normalizar_nome(d["nome"]),
                 d["documento_tipo"], d["documento_numero"], d["endereco"],
                 d["bairro"], d["cep"], d["cidade"], d["uf"]))
            carga.contar("devedores trazidos do acervo")

    def normalizar_o_que_falta(c: sqlite3.Connection) -> None:
        """Preenche `nome_norm` de quem entrou antes de a coluna existir.

        A coluna e aditiva — `MIGRACOES` so acrescenta, e a linha antiga fica
        com ela vazia. Devedor com `nome_norm` vazio nao aparece na busca por
        nome, e e por nome que a certidao acha a pessoa.
        """
        faltam = c.execute(
            """SELECT id, nome FROM pt_devedores
                WHERE nome_norm IS NULL AND nome IS NOT NULL""").fetchall()
        for linha in faltam:
            c.execute("UPDATE pt_devedores SET nome_norm=? WHERE id=?",
                      (normalizar_nome(linha["nome"]), int(linha["id"])))
        if faltam:
            carga.contar("devedores que ganharam nome de busca")

    def atos(c: sqlite3.Connection, titulo_id: int, r: sqlite3.Row) -> None:
        """Os atos que o acervo guarda do titulo: apontamento, protesto, baixa.

        A CERTIDAO E QUEM COBRA ISTO. Certidao positiva diz "protestado no
        Livro X, fl. Y, em tal data" — e ate 25/08/2026 a carga so trazia o
        apontamento. O livro e a folha do protesto estavam no acervo o tempo
        todo, em `intProtestoLivro` e `intProtestoFolha`.
        """
        chave = f"tbAvisoProtesto:{r['intChave']}"

        ordem = _inteiro(r["intNumeroApontamento"])
        if ordem:                        # titulo recebido e nao apontado: nao ha
            c.execute(
                """INSERT INTO pt_atos(titulo_id, tipo, selo, folha,
                       numero_ordem, data_ato, origem, origem_chave, criado_em)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (titulo_id, "APONTAMENTO", _txt(r["strSelo_Apontamento"]),
                 _inteiro(r["intFolhaApontamento"]), ordem,
                 _data(r["dtmE_Cartorio"]) or agora, "EOFICIO",
                 f"{chave}:APONTAMENTO", agora))

        # O PROTESTO ENTRA SEM NUMERO DE ORDEM, e isso e o fato: o acervo
        # guarda o livro (4 a 9) e a folha (1 a 200), e NENHUMA coluna com o
        # numero. E a mesma falta que faz `PT_PROTESTO` ficar sem contador
        # semeado e o oficial ter de informar o proximo numero a mao.
        #
        # A DATA E `dtmOcorrencia`, e ela foi medida em 25/08/2026: nos 1.164
        # titulos protestados ela e SEMPRE posterior a entrada no cartorio —
        # 1.160 posteriores, nenhuma igual, nenhuma anterior. E a data em que
        # o E-Oficio marcou a ocorrencia do protesto.
        if r["snProtestado"]:
            c.execute(
                """INSERT INTO pt_atos(titulo_id, tipo, folha, data_ato,
                       observacao, detalhe_json, origem, origem_chave,
                       criado_em)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (titulo_id, "PROTESTO", _inteiro(r["intProtestoFolha"]),
                 _data(r["dtmOcorrencia"]) or _data(r["dtmE_Cartorio"]) or agora,
                 "número de ordem não consta do acervo do E-Ofício",
                 json.dumps({"livro_do_acervo": _inteiro(r["intProtestoLivro"]),
                             "ocorrencia_eoficio": _txt(r["intCodigoOcorrencia"])},
                            ensure_ascii=False),
                 "EOFICIO", f"{chave}:PROTESTO", agora))
            if not _inteiro(r["intProtestoLivro"]):
                carga.contar("protestos sem livro e folha no acervo")

        # O CANCELAMENTO tem data e selo nos 56 do acervo — os dois em 100%.
        # A HIPOTESE do catalogo NAO VEM: o acervo tinha um cadastro so, "Erro
        # Material", e metade dos 56 nao diz por que. Inventar a hipotese aqui
        # seria assinar por quem cancelou.
        if r["snCanceladoProtesto"]:
            c.execute(
                """INSERT INTO pt_atos(titulo_id, tipo, selo, data_ato,
                       motivo_cancelamento, observacao, origem, origem_chave,
                       criado_em)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (titulo_id, "CANCELAMENTO", _txt(r["strSelo_Cancelamento"]),
                 _data(r["dtmCancelaProtesto"]) or agora,
                 _txt(r["memObsCancelamento"]),
                 "hipótese do catálogo não consta do acervo",
                 "EOFICIO", f"{chave}:CANCELAMENTO", agora))

    # A ordem por intChave e a ordem em que o E-Oficio criou, e e a que faz o
    # numero de apontamento sair crescente.
    #
    # O DEVEDOR E O CEDENTE VEM NA MESMA CONSULTA, por LEFT JOIN em
    # `tbPessoa`: `intCodigoPessoa` e o devedor (quem foi protestado) e
    # `intCodigoCedente` e o credor. Sao 1.370 linhas — buscar pessoa por
    # pessoa seriam 2.740 consultas a mais para ler a mesma coisa. LEFT e nao
    # INNER porque titulo sem cedente ainda e titulo, e nao pode sumir da
    # carga por causa de uma ligacao quebrada.
    com_pessoa = f"""SELECT a.*, {_colunas_pessoa('d', 'dev')},
                            {_colunas_pessoa('c', 'ced')}
             FROM tbAvisoProtesto a
             LEFT JOIN tbPessoa d ON d.intCodigoPessoa = a.intCodigoPessoa
             LEFT JOIN tbPessoa c ON c.intCodigoPessoa = a.intCodigoCedente
            ORDER BY a.intChave"""
    sem_pessoa = "SELECT a.* FROM tbAvisoProtesto a ORDER BY a.intChave"
    linhas = acervo.execute(com_pessoa if tem_pessoa else sem_pessoa)
    _executar(con, carga, "pt_titulos", linhas, mapear,
              lambda r: r["intChave"], depois=atos)
    devedores_que_faltam(con)
    normalizar_o_que_falta(con)

    def chaves_cenprot_que_faltam(c: sqlite3.Connection) -> None:
        """Preenche `chave_cenprot` nos titulos do acervo que ainda estao
        sem ela.

        MESMA RAZAO DE `devedores_que_faltam`: `_executar` so chama `depois`
        de quem ENTROU agora. Quem rodou a carga antes desta correcao ja tem
        os titulos gravados — eles voltam como `repetidos`, e a chave nunca
        chegaria neles. Esta passada olha o que FALTA, copia so o que o acervo
        tem, e nao sobrescreve chave que ja esta la.
        """
        if not tem_chave_cenprot:
            return
        sem_chave = {
            str(linha["origem_chave"]): int(linha["id"])
            for linha in c.execute(
                """SELECT t.id, t.origem_chave FROM pt_titulos t
                    WHERE t.origem_chave LIKE 'tbAvisoProtesto:%'
                      AND TRIM(COALESCE(t.chave_cenprot,'')) = ''""")
        }
        if not sem_chave:
            return
        for r in acervo.execute(
                """SELECT intChave, strChaveUnicaCENPROT
                      FROM tbAvisoProtesto
                     WHERE strChaveUnicaCENPROT IS NOT NULL
                       AND TRIM(CAST(strChaveUnicaCENPROT AS TEXT)) <> ''"""):
            titulo_id = sem_chave.get(f"tbAvisoProtesto:{r['intChave']}")
            if titulo_id is None:
                continue
            chave = _txt(r["strChaveUnicaCENPROT"])
            if not chave:
                continue
            cur = c.execute(
                """UPDATE pt_titulos SET chave_cenprot=?
                    WHERE id=? AND TRIM(COALESCE(chave_cenprot,'')) = ''""",
                (chave, titulo_id))
            if cur.rowcount:
                carga.contar("chaves CENPROT trazidas do acervo")

    chaves_cenprot_que_faltam(con)
    # A INTIMACAO, pela mesma passada-que-olha-o-que-falta — e ela e o ato do
    # MEIO da vida do titulo, que nunca entrava. Medido na producao em
    # 01/09/2026: **zero** atos de INTIMACAO em 1.366 titulos.
    #
    # Quem cobrou foi o TERMO do protesto, que diz «O Sacado foi intimado por
    # Edital em ‹data›» — e o E-Oficio o escreveu em 1.078 de 1.132. E a
    # certidao cobrando da carga pela QUINTA vez.
    _o_que_o_retorno_precisa(con, acervo, carga=carga, agora=agora)
    return carga


# ------------------------------------------------------------------ o RCPN


# Qual tabela do acervo alimenta cada especie, e onde estao os campos que
# variam de uma para outra. `nome` e `data_fato` mudam de coluna em cada
# tabela, e e por isso que o mapeamento e declarado e nao adivinhado.
FONTES_RCPN: tuple[dict, ...] = (
    {"tabela": "tbRegistroNascimento", "especie": "NASCIMENTO",
     "nome": "strNomeNascido", "data_fato": "dtmDataNascimento",
     "data_ato": "dtmDataAssento", "matricula": "strNumeroMatricula"},
    {"tabela": "tbRegistroCasamento", "especie": "CASAMENTO",
     "nome": "strNomeConjuge1", "data_fato": "dtmDataCelebracaoCasamento",
     "data_ato": "dtmDataRegistroCasamento", "matricula": "strMatricula"},
    {"tabela": "tbRegistroObito", "especie": "OBITO",
     "nome": "strNome", "data_fato": "dtmDataObito",
     "data_ato": "dtmDataRegistro", "matricula": "strMatricula"},
)



def previa_rcpn(con: sqlite3.Connection, acervo: sqlite3.Connection,
                *, amostras: int = 5) -> dict:
    """Conta o que a carga do RCPN faria, SEM gravar. Só lê.

    Existe para a tela do balcão mostrar, ANTES de escrever, quantos
    assentos entrariam, quais espécies e amostras do que já está e do que
    ainda falta. A gravação continua em `carregar_rcpn` — esta função não
    tem um único INSERT.

    Já importado = mesma `origem_chave` com `origem='EOFICIO'` em
    `rc_assentos`. É a mesma chave que `INSERT OR IGNORE` usa para não
    duplicar.
    """
    existentes = {
        str(r["origem_chave"])
        for r in con.execute(
            "SELECT origem_chave FROM rc_assentos "
            "WHERE origem = 'EOFICIO' AND origem_chave IS NOT NULL")
        if r["origem_chave"]
    }
    por_especie: list[dict] = []
    amostras_novos: list[dict] = []
    amostras_ja: list[dict] = []
    amostras_sem_nome: list[dict] = []
    total_no_acervo = 0
    total_novos = 0
    total_ja = 0
    total_sem_nome = 0

    for fonte in FONTES_RCPN:
        bloco = {
            "especie": fonte["especie"],
            "tabela": fonte["tabela"],
            "no_acervo": 0,
            "novos": 0,
            "ja_importados": 0,
            "sem_nome": 0,
            "tabela_ausente": False,
        }
        if not _tem_tabela(acervo, fonte["tabela"]):
            bloco["tabela_ausente"] = True
            por_especie.append(bloco)
            continue
        colunas = {c[1] for c in acervo.execute(
            f'PRAGMA table_info("{fonte["tabela"]}")')}
        nome_col = fonte["nome"]
        tem_numero = "intNumeroRegistro" in colunas
        tem_matricula = fonte["matricula"] in colunas
        tem_data = fonte["data_ato"] in colunas
        selecao = ["intChave", f'"{nome_col}" AS nome']
        if tem_numero:
            selecao.append("intNumeroRegistro AS numero")
        if tem_matricula:
            selecao.append(f'"{fonte["matricula"]}" AS matricula')
        if tem_data:
            selecao.append(f'"{fonte["data_ato"]}" AS data_ato')
        sql = (f'SELECT {", ".join(selecao)} FROM "{fonte["tabela"]}" '
               f'ORDER BY intChave')
        for r in acervo.execute(sql):
            bloco["no_acervo"] += 1
            total_no_acervo += 1
            chave = f'{fonte["tabela"]}:{r["intChave"]}'
            nome = _txt(r["nome"])
            amostra = {
                "especie": fonte["especie"],
                "origem_chave": chave,
                "nome": nome or "(sem nome)",
                "numero": _inteiro(r["numero"]) if tem_numero else None,
                "matricula": _txt(r["matricula"]) if tem_matricula else None,
                "data_ato": _data(r["data_ato"]) if tem_data else None,
            }
            if not nome:
                bloco["sem_nome"] += 1
                total_sem_nome += 1
                if len(amostras_sem_nome) < amostras:
                    amostras_sem_nome.append(amostra)
                continue
            if chave in existentes:
                bloco["ja_importados"] += 1
                total_ja += 1
                if len(amostras_ja) < amostras:
                    amostras_ja.append(amostra)
            else:
                bloco["novos"] += 1
                total_novos += 1
                if len(amostras_novos) < amostras:
                    amostras_novos.append(amostra)
        por_especie.append(bloco)

    ja_no_cartorio = {
        row["especie"]: row["n"]
        for row in con.execute(
            "SELECT especie, COUNT(*) AS n FROM rc_assentos "
            "WHERE origem = 'EOFICIO' GROUP BY especie")
    }
    return {
        "por_especie": por_especie,
        "total_no_acervo": total_no_acervo,
        "total_novos": total_novos,
        "total_ja": total_ja,
        "total_sem_nome": total_sem_nome,
        "amostras_novos": amostras_novos,
        "amostras_ja": amostras_ja,
        "amostras_sem_nome": amostras_sem_nome,
        "ja_no_cartorio": ja_no_cartorio,
        "origem": "EOFICIO",
    }


def carregar_rcpn(con: sqlite3.Connection, acervo: sqlite3.Connection,
                  *, agora: str) -> Carga:
    """Os assentos de nascimento, casamento e obito.

    O que e proprio de cada especie — regime de bens, causa da morte, hora do
    nascimento — vai para `dados_json`, e nao para coluna. E a mesma decisao do
    esquema: o casamento tem 94 colunas no acervo, e uma coluna por campo aqui
    encheria a tabela de vazios para as outras cinco especies.

    O livro e a folha entram como o acervo os tem. Nascimento com
    `strTipoLivro = 'E'` — ha um — vai para a especie OUTRO, porque assento de
    nascimento lancado no Livro E nao e assento do Livro A.
    """
    carga = Carga("rcpn")
    for fonte in FONTES_RCPN:
        if not _tem_tabela(acervo, fonte["tabela"]):
            continue
        colunas = {c[1] for c in acervo.execute(
            f'PRAGMA table_info("{fonte["tabela"]}")')}

        def mapear(r: sqlite3.Row, f=fonte, cols=colunas) -> dict | None:
            nome = _txt(r[f["nome"]])
            if not nome:
                carga.rejeitar(r["intChave"],
                               f"assento de {f['especie'].lower()} sem nome",
                               dict(r))
                return None
            # A MATRICULA DECIDE, E NAO A LETRA — correcao de 27/08/2026.
            #
            #   Eu mandava para a especie OUTRO (Livro E) todo assento com
            #   `strTipoLivro = 'E'`, e ha exatamente UM. Fui conferi-lo: e o
            #   nascimento de IGOR PAIVA DE SOUSA, Livro 9, folha 102,
            #   numero 8686 — um nascimento comum de 1994. **A matricula dele
            #   diz tipo de livro `1`**, que e o Livro A, e a matricula e o
            #   numero nacional impresso na certidao.
            #
            #   Medido: `strTipoLivro` traz 'A' em 192 e 'E' em 1; a matricula
            #   traz `1` em **192 de 192**. A letra e erro de digitacao num
            #   registro, e a carga confiava nela.
            #
            #   O ESTRAGO PASSAVA DO ASSENTO: aquele unico registro semeava o
            #   contador do Livro E em **8687**, com um numero que e de
            #   nascimento. O primeiro ato de Livro E desta casa nasceria com o
            #   numero 8688 — o defeito de 18/08 num livro que ainda nem foi
            #   usado.
            #
            #   A regra passa a ser a que o Livro 3 ja usava: **quem define a
            #   pertinencia e a tabela**, e a letra so muda a especie quando a
            #   MATRICULA concorda. Divergencia vira aviso, e nao silencio.
            especie = f["especie"]
            if "strTipoLivro" in cols and _txt(r["strTipoLivro"]) == "E":
                if _matricula_diz_livro_e(r[f["matricula"]]):
                    especie = "OUTRO"
                else:
                    carga.avisar(
                        r["intChave"],
                        f"o acervo marca este assento como Livro E, mas a "
                        f"matrícula diz Livro {f['especie'].lower()[0].upper()} "
                        f"— entrou como {f['especie'].lower()}, que é o que a "
                        f"matrícula afirma",
                        dict(r))
            proprios = {
                k: r[k] for k in cols
                if k not in ("intChave", f["nome"], f["data_fato"],
                             f["data_ato"], f["matricula"])
                and not k.startswith("mem")          # o teor vai em `teor`
                and r[k] not in (None, "")
            }
            return {
                "serie": {"NASCIMENTO": "RC_A", "CASAMENTO": "RC_B",
                          "OBITO": "RC_C", "OUTRO": "RC_E"}[especie],
                "especie": especie,
                "numero": _inteiro(r["intNumeroRegistro"]),
                "livro_volume": _volume_do_livro(r, cols, especie),
                "matricula": _txt(r[f["matricula"]]),
                "nome": nome,
                "data_ato": _data(r[f["data_ato"]]),
                "data_fato": _data(r[f["data_fato"]]),
                "dados_json": json.dumps(proprios, ensure_ascii=False,
                                         default=str),
                "teor": _txt(r["memTexto"]) if "memTexto" in cols else None,
                "situacao": "ATIVO",
                "origem": "EOFICIO",
                "origem_chave": f'{f["tabela"]}:{r["intChave"]}',
                "criado_em": agora,
            }

        _executar(con, carga, "rc_assentos",
                  acervo.execute(f'SELECT * FROM "{fonte["tabela"]}" '
                                 f'ORDER BY intChave'),
                  mapear, lambda r: r["intChave"])

    # OS PAIS E OS AVOS ENTRAM NUMA PASSADA A PARTE, e nao pelo `depois` da
    # linha — pelo mesmo motivo do devedor do Protesto: `_executar` so chama o
    # `depois` de quem ENTROU AGORA, e quem rodou a carga antes de 26/08/2026
    # tem os assentos gravados. Numa segunda rodada eles voltam como
    # `repetidos`, e a filiacao nunca chegaria neles.
    #
    # A passada olha o que FALTA — um caminho so para os dois casos, e
    # repetivel por construcao.
    carga.contar("pessoas_de_filiacao",
                 _pessoas_que_faltam(con, acervo, carga=carga, agora=agora))
    # O DECLARANTE E AS TESTEMUNHAS, pela mesma passada-que-olha-o-que-falta.
    #
    # O declarante e campo OBRIGATORIO do assento de nascimento e de obito
    # (Lei 6.015/1973, arts. 54 e 80), e a certidao de obito o nomeia. As
    # testemunhas sao o que prova que o ato foi praticado diante de alguem.
    # Nenhum dos dois entrava.
    for papel, quantos in _ligadas_que_faltam(con, acervo, agora=agora).items():
        carga.contar(f"pessoas_{papel.lower()}", quantos)
    # A PESSOA DE QUEM O ASSENTO E — o registrado, os nubentes, o falecido.
    #
    # Faltava a principal: o assento guardava o NOME dela e mais nada. Isso
    # travava a REMESSA DO IBGE (que pede sexo, data de nascimento,
    # naturalidade, residencia e estado civil) e a CERTIDAO de casamento e de
    # obito ao mesmo tempo.
    for papel, quantos in _o_proprio_assento_que_falta(
            con, acervo, carga=carga, agora=agora).items():
        carga.contar(f"pessoas_{papel.lower()}", quantos)
    # O QUE A REMESSA DO IBGE PEDE — local do nascimento, gemeo, DNV, DO e o
    # local do obito. Sem isto o arquivo sai com «ignorado» onde o acervo tem
    # a resposta, e remessa cheia de nove e remessa aceita e inutil.
    for onde, quantos in _campos_do_ibge_que_faltam(
            con, acervo, agora=agora).items():
        carga.contar(f"ibge_{onde}", quantos)
    # O ATO DE REGISTRO, com a folha do livro de papel. A CERTIDAO COBROU pela
    # QUARTA VEZ neste projeto — antes foram o devedor do Protesto, o ato de
    # registro do RCPJ/RTD e a filiacao daqui.
    #
    # Sem ele a certidao imprimia `LIVRO ND / FOLHA ND`: papel que nao diz de
    # onde foi tirado. E, como no RCPJ/RTD, a passada olha o que FALTA — quem
    # rodou a carga antes tem os assentos gravados, e o `depois` da linha nunca
    # os alcancaria.
    carga.contar("atos_de_registro",
                 _registros_que_faltam(con, acervo, agora=agora))
    # PENDENCIA E DECLARADA, NAO ADIVINHADA: ela entra porque a carga a
    # DESCOBRIU no acervo desta casa, com o numero medido na hora.
    _perguntar_do_livro_do_casamento(con, acervo, agora=agora)
    # E MARCA OS ASSENTOS de que a pergunta trata, para o aviso aparecer na
    # ficha de cada um — e nao so numa aba que ninguem abre.
    carga.contar("assentos_com_livro_a_confirmar",
                 _marcar_livro_a_confirmar(con, acervo, agora=agora))
    return carga


# O QUE A MARCA DIZ, quando alguem abre um daqueles assentos. Ela e TEXTO, e
# nao um `1`: quem ler a ficha daqui a cinco anos precisa saber POR QUE o
# livro esta por confirmar, e nao so que esta.
MOTIVO_DO_LIVRO_A_CONFIRMAR = (
    "O E-Ofício guardou este casamento num grupo separado, com numeração "
    "própria (registros 26 a 59, no Livro 1) — o que costuma distinguir o "
    "Livro B-Auxiliar, do casamento religioso com efeito civil. O acervo não "
    "diz qual dos dois é, e o assento ficou como o E-Ofício o guardou, por "
    "decisão do oficial em 26/08/2026. Antes de emitir certidão deste "
    "assento, confira na folha do livro de papel se o livro é o B ou o "
    "B-Auxiliar, e corrija aqui se for o caso."
)


def _marcar_livro_a_confirmar(con: sqlite3.Connection,
                              acervo: sqlite3.Connection, *,
                              agora: str) -> int:
    """Marca os assentos cujo livro esta por conferir no papel. ESCREVE.

    "Deixe como o E-Oficio guardou, PENDENTE DE CONFIRMACAO QUANDO FOREM
    CONSULTADOS EFETIVAMENTE" — o oficial, 26/08/2026. Esta funcao existe por
    causa da segunda metade da frase: deixar como esta nao precisa de codigo;
    avisar no dia da consulta precisa.

    REPETIVEL, e isso exigiu uma coluna a mais. A primeira versao marcava
    todo assento com `livro_a_confirmar IS NULL` — e um assento CONFERIDO
    tambem esta NULL, entao a carga ressuscitava a duvida de quem ja tinha ido
    a estante. NULL queria dizer duas coisas.

    Agora `livro_conferido_em` guarda o terceiro estado, e quem conferiu nunca
    e perguntado de novo. Marca que volta e pior que marca que nunca existiu:
    ela ensina o balcao a ignorar o aviso.
    """
    if not _tem_tabela(acervo, "tbRegistroCasamento"):
        return 0
    colunas = {c[1] for c in acervo.execute(
        'PRAGMA table_info("tbRegistroCasamento")')}
    if "intTipoRegistroLivro" not in colunas:
        return 0
    chaves = {f'tbRegistroCasamento:{r["intChave"]}' for r in acervo.execute(
        "SELECT intChave FROM tbRegistroCasamento "
        "WHERE intTipoRegistroLivro = 1")}
    if not chaves:
        return 0
    marcados = 0
    for chave in sorted(chaves):
        cur = con.execute(
            """UPDATE rc_assentos SET livro_a_confirmar = ?
                WHERE origem = 'EOFICIO' AND origem_chave = ?
                  AND livro_a_confirmar IS NULL
                  AND livro_conferido_em IS NULL""",
            (MOTIVO_DO_LIVRO_A_CONFIRMAR, chave))
        marcados += cur.rowcount
    return marcados


def _perguntar_do_livro_do_casamento(con: sqlite3.Connection,
                                     acervo: sqlite3.Connection, *,
                                     agora: str) -> None:
    """Declara a duvida do Livro B-Auxiliar, se o acervo tiver o segundo grupo.

    SO PERGUNTA SE ACHOU. Declarar a pendencia num acervo onde ela nao existe
    seria alarme que soa sempre — e alarme que soa sempre e alarme que ninguem
    ouve. E a mesma regra das series sem contador.
    """
    if not _tem_tabela(acervo, "tbRegistroCasamento"):
        return
    colunas = {c[1] for c in acervo.execute(
        'PRAGMA table_info("tbRegistroCasamento")')}
    if "intTipoRegistroLivro" not in colunas:
        return
    quantos = acervo.execute(
        "SELECT COUNT(*) n FROM tbRegistroCasamento "
        "WHERE intTipoRegistroLivro = 1").fetchone()[0]
    if quantos:
        IMP.declarar_livro_do_casamento(con, quantos=int(quantos), agora=agora)


def _volume_do_livro(r: sqlite3.Row, cols: set, especie: str) -> str | None:
    """`A` + `22` -> `A-22`. O livro fisico, como a capa dele esta escrita.

    A LETRA SO SAI DE ONDE FOI MEDIDA. No nascimento ela e `strTipoLivro`
    (`A` em 192 de 193, `E` em 1). No casamento e no obito o acervo NAO tem
    coluna com a letra — tem `intTipoRegistroLivro`, que e 0 ou 1 e cujo
    significado nao esta provado —, e por isso ali sai so o numero.

    Escrever `B-1` num casamento sem ter medido que a letra e B seria inventar
    o livro de onde a certidao diz que foi tirada.
    """
    numero = _txt(r["strLivro"]) if "strLivro" in cols else ""
    if not numero:
        return None
    letra = _txt(r["strTipoLivro"]) if "strTipoLivro" in cols else ""
    return f"{letra}-{numero}" if letra else numero


def _registros_que_faltam(con: sqlite3.Connection, acervo: sqlite3.Connection,
                          *, agora: str) -> int:
    """Lavra o ato de REGISTRO dos assentos que ainda nao o tem. ESCREVE.

    O LUGAR VEM DO ACERVO, e nao do nucleo: o assento ja esta escriturado no
    livro de papel, com folha e numero proprios. Mandar `escrituracao.reservar`
    achar lugar reescreveria a historia.
    """
    faltam = [dict(r) for r in con.execute(
        """SELECT a.id, a.especie, a.origem_chave, a.numero, a.data_ato
             FROM rc_assentos a
            WHERE a.origem = 'EOFICIO'
              AND NOT EXISTS (SELECT 1 FROM rc_atos t
                               WHERE t.assento_id = a.id
                                 AND t.tipo = 'REGISTRO')""")]
    if not faltam:
        return 0
    fonte_da_especie = {f["especie"]: f["tabela"] for f in FONTES_RCPN}
    postos = 0
    for a in faltam:
        chave = _chave_do_acervo(a["origem_chave"])
        # A especie OUTRO e o nascimento lancado no Livro E: a fonte dele
        # continua sendo a tabela de nascimento.
        tabela = fonte_da_especie.get(a["especie"]) or "tbRegistroNascimento"
        # A COLUNA SE PERGUNTA ANTES DE LER, como a tabela. `intFolha` esta
        # nas tres do acervo desta casa (193/193, 20/20 e 31/31), e supor que
        # ela existe faria a carga inteira estourar num acervo que nao a tenha
        # — e o ato de registro e acabamento da certidao, nao pode derrubar a
        # carga dos 244 assentos.
        folha = None
        if chave is not None and _tem_tabela(acervo, tabela):
            colunas = {c[1] for c in acervo.execute(
                f'PRAGMA table_info("{tabela}")')}
            if "intFolha" in colunas:
                linha = acervo.execute(
                    f'SELECT intFolha FROM "{tabela}" WHERE intChave=?',
                    (chave,)).fetchone()
                if linha:
                    folha = _inteiro(linha["intFolha"])
        con.execute(
            """INSERT INTO rc_atos(assento_id, tipo, folha, numero_ordem,
                   rotulo, data_ato, origem, origem_chave, criado_em)
               VALUES (?,'REGISTRO',?,?,?,?, 'EOFICIO', ?, ?)""",
            (a["id"], folha, a["numero"],
             str(folha) if folha else None,
             a["data_ato"] or agora[:10],
             f'rc_assento:{a["id"]}', agora))
        postos += 1
    return postos


# Qual tabela do acervo guarda cada papel, e como o codigo dela vira papel.
#
# `tbFiliacao` sao OS PAIS — 2 por registro em 196 de 196 —, e serve as tres
# especies: 392 de nascimento, 48 de casamento, 62 de obito.
#
# `tbProgenitor` sao OS AVOS, e so de nascimento: as 784 linhas tem
# `intTipoRegistro = 1`. A filiacao 1 sao os PATERNOS e a 2 os MATERNOS, e o
# sexo separa avo de avo.
# ------------------- QUEM E PAI E QUEM E MAE: O SEXO DECIDE, E NAO O CODIGO
#
# O QUE EU TINHA ESCRITO AQUI ESTAVA ERRADO, e o ensaio da certidao mostrou.
#     Estava `{1: "PAI", 2: "MAE"}`, com o comentario dizendo que era medido.
#     O que se mediu foram os PARES por registro (2 em 196 de 196), e nao QUEM
#     e quem dentro do par.
#
# MEDIDO AGORA, no acervo inteiro:
#
#     NASCIMENTO  codigo 1 -> 162 masculinos e **30 femininos**
#                 codigo 2 -> 158 femininos e **18 masculinos**
#     OBITO       codigo 1 ->  19 masculinos e **12 femininos**
#                 codigo 2 ->  20 femininos e **8 masculinos**
#
#     E ha o caso que decide: `(1, Feminino, BIANCA PEREIRA GOMES)` com
#     `(2, Masculino, BENTO GOMES DE SAMPAIO)` — **os dois com nome, e
#     trocados**. Nao e mae sozinha ocupando a primeira vaga: e a ordem
#     invertida mesmo.
#
# O ESTRAGO, se o codigo mandasse: **30 certidoes de nascimento e 12 de obito**
# sairiam com a MAE no lugar do PAI. E a remessa do IBGE usa a mae para a
# residencia e para a idade da genitora — com a pessoa errada.
#
# E A MESMA REGRA DA MATRICULA CONTRA A LETRA DO LIVRO, de 27/08: quem define e
# o dado que descreve a coisa, e nao a gaveta em que ele foi guardado. O codigo
# so desempata quando o sexo falta.
#
# NO CASAMENTO SAO QUATRO, e o sistema so lia duas.
#     Medido: codigos 1 e 2 sao os pais do PRIMEIRO conjuge, e 3 e 4 os do
#     SEGUNDO — conferido pelos sobrenomes, que casam um a um. Lendo so 1 e 2,
#     **os pais do segundo conjuge nunca entravam**, e a certidao de casamento
#     mostrava uma filiacao so, como se fosse «a» filiacao.
PAPEL_DA_FILIACAO: dict[int, str] = {1: "PAI", 2: "MAE"}

# De que conjuge sao os pais, no casamento.
CONJUGE_DA_FILIACAO: dict[int, str] = {1: "1", 2: "1", 3: "2", 4: "2"}


FILIACAO_COM_SEXO_REPETIDO = (
    "o acervo diz que pai e mãe são do mesmo sexo — quem é quem saiu do código "
    "do E-Ofício, e vale conferir no livro de papel")


def papeis_da_filiacao(tipo_registro: Any,
                       linhas: list[dict]) -> dict[int, str]:
    """Quem e pai e quem e mae, decidido POR PAR e nao linha a linha.

    O SEXO MANDA, MAS NAO PODE PRODUZIR DOIS PAIS. E a correcao de uma regra
    que eu escrevi meia hora antes e que estava certa em 42 casos e errada em
    um — e o errado era pior que o problema original.

        A primeira versao olhava cada linha sozinha: sexo `M` vira pai, `F`
        vira mae. Isso conserta os **30 nascimentos e 12 obitos** em que o
        acervo guardou a mae na vaga do pai.

        Mas no registro 19532 o acervo marca **as duas pessoas como
        «Masculino»** — WANDERSON e VALQUIANE, e «Valquiane» e nome feminino:
        o sexo e que esta errado ali. Com a regra linha a linha saiam **dois
        pais e nenhuma mae** — e a mae sumia da certidao e da remessa do IBGE.

    ENTAO A INVARIANTE E MAIS FORTE QUE OS DOIS SINAIS: um assento tem UM pai e
    UMA mae. Quando os sexos discordam entre si, eles decidem; quando dizem a
    mesma coisa — ou quando faltam —, o codigo do acervo desempata, porque e o
    unico sinal que resta.

    NO CASAMENTO SAO DOIS PARES: os codigos 1 e 2 sao os pais do primeiro
    conjuge, e 3 e 4 os do segundo — conferido pelos sobrenomes, que casam um a
    um.

    Devolve `({codigo: papel}, [codigos duvidosos])` — os duvidosos sao os
    pares em que o acervo diz que as duas pessoas sao do mesmo sexo, e por isso
    uma das duas esta errada la.
    """
    tipo = _inteiro(tipo_registro)
    por_codigo = {}
    for linha in linhas:
        codigo = _inteiro(linha.get("intCodigoFiliacao"))
        if codigo is not None:
            por_codigo[codigo] = _sexo(linha.get("strSexo"))

    if tipo == TIPO_DO_ACERVO["CASAMENTO"]:
        pares = ((1, 2, "_NUBENTE1"), (3, 4, "_NUBENTE2"))
    else:
        pares = ((1, 2, ""),)

    saida: dict[int, str] = {}
    duvidosos: list[int] = []
    for primeiro, segundo, sufixo in pares:
        a, b = por_codigo.get(primeiro), por_codigo.get(segundo)
        if a in ("M", "F") and b in ("M", "F") and a != b:
            # OS DOIS SEXOS SE CONTRADIZEM E POR ISSO DECIDEM.
            escolha = {primeiro: a, segundo: b}
        elif a in ("M", "F") and b not in ("M", "F"):
            # SO UM TEM SEXO: ele decide, e o outro fica com o que sobra.
            escolha = {primeiro: a, segundo: ("F" if a == "M" else "M")}
        elif b in ("M", "F") and a not in ("M", "F"):
            escolha = {segundo: b, primeiro: ("F" if b == "M" else "M")}
        else:
            # NENHUM SINAL UTIL — ou os dois dizem a mesma coisa. Vale o
            # codigo, que e a convencao do proprio E-Oficio.
            #
            # E ISSO VIRA AVISO, e nao silencio: se os dois se dizem do mesmo
            # sexo, um dos dois esta errado no acervo, e a certidao pode sair
            # com o pai no lugar da mae. Quem for a estante precisa saber quais
            # conferir. E a mesma regra da matricula que desmente a letra do
            # livro: a divergencia se declara.
            if a in ("M", "F") and a == b:
                duvidosos.append(primeiro)
            escolha = {primeiro: "M", segundo: "F"}
        for codigo, letra in escolha.items():
            if codigo in por_codigo:
                saida[codigo] = ("PAI" if letra == "M" else "MAE") + sufixo
    return saida, duvidosos
PAPEL_DO_PROGENITOR: dict[tuple[int, str], str] = {
    (1, "M"): "AVO_PATERNO", (1, "F"): "AVO_PATERNA",
    (2, "M"): "AVO_MATERNO", (2, "F"): "AVO_MATERNA",
}

# O tipo de registro do acervo, para achar o assento certo.
TIPO_DO_ACERVO: dict[str, int] = {"NASCIMENTO": 1, "CASAMENTO": 2, "OBITO": 3}


def _chave_do_acervo(origem_chave: Any) -> int | None:
    """`tbRegistroNascimento:1.0` -> `1`. Devolve None quando nao da.

    O `.0` NAO E ENFEITE: `intChave` e REAL nas tabelas do civil do E-Oficio,
    e por isso a chave de origem sai com a casa decimal. A primeira versao
    desta funcao usava `.isdigit()`, e `"1.0".isdigit()` e False — os 193
    assentos de nascimento eram pulados EM SILENCIO, e a filiacao so chegava
    nos 51 cuja tabela tem chave inteira.
    """
    texto = str(origem_chave or "").split(":")[-1].strip()
    try:
        return int(float(texto))
    except (TypeError, ValueError):
        return None


def _sexo(valor: Any) -> str:
    """`Masculino` -> `M`. O acervo escreve por extenso; o papel usa a letra."""
    s = _txt(valor) or ""
    return "M" if s[:1].upper() == "M" else ("F" if s[:1].upper() == "F" else "")


def _o_que_o_retorno_precisa(con: sqlite3.Connection,
                             acervo: sqlite3.Connection, *,
                             carga: "Carga", agora: str) -> dict:
    """Traz protocolo, apresentante e INTIMAÇÃO dos títulos que não os têm.

    **O RETORNO À CRA NÃO PODIA SER GERADO PARA NENHUM TÍTULO DO ACERVO**, e
    foi o ensaio contra a produção que mostrou — em 01/09/2026, depois de todo
    o módulo passar em teste de mesa. Medido: `pendentes()` devolve 1.211 atos
    que a Central não sabe, e **os 1.211 estão sem protocolo**;
    `apresentantes_pendentes()` devolve **um grupo com código vazio**.

    O sistema já recusava, e com a mensagem certa — *«estão sem número de
    protocolo, e ele é o que volta na posição 448 do arquivo»*. O que ninguém
    tinha medido é que a recusa alcança **todos**.

    SÃO TRÊS COISAS, E ELAS VÊM JUNTAS porque servem ao mesmo arquivo:

      - o **protocolo**, de `tbAvisoProtesto.strCB` — 1.369 de 1.370;
      - o **apresentante** (código e nome), de `tbSDT`, por `intProtocolo` —
        1.357 e 1.360. Sem o código não há cabeçalho nem a letra da posição
        566;
      - a **intimação**, que é o ato do meio da vida do título e nunca
        entrava — e que o TERMO do protesto cobra: ele diz «O Sacado foi
        intimado por Edital em ‹data›», e o E-Ofício o escreveu em 1.078 de
        1.132 protestos.

    **A LIGAÇÃO É `origem_chave`, E NÃO O PROTOCOLO** — que é justamente o que
    falta. `origem` também não serve: ela guarda de onde o TÍTULO veio (CRA,
    CENPROT, MANUAL), e não a fonte da carga.

    **O MODO DA INTIMAÇÃO SAI DO QUE ACONTECEU.** Houve edital publicado?
    `EDITAL`, com a data. Não houve, mas a entrega foi confirmada? `PESSOAL`.
    Nenhum dos dois? **O ato não entra** — inventar uma intimação que não
    consta seria pior que a falta. São 194 assim, e 8 deles protestados:
    buraco do próprio acervo, e que fica visível como tal.

    **A ÚLTIMA PUBLICAÇÃO É A QUE CONTA**: o aviso não é um por título — 1.618
    para 1.361 —, e reemitir é rotina.
    """
    feito = {"protocolo": 0, "apresentante": 0, "intimacao": 0,
             "sem_intimacao": 0}
    # SEM `tbAvisoProtesto` NAO HA O QUE TRAZER, e a passada nao estoura por
    # isso — instalacao sem o Protesto no acervo e acervo de teste sao os dois
    # casos. E CADA TABELA RESPONDE POR UMA PARTE: sem `tbSDT` nao ha
    # apresentante, mas o protocolo continua vindo.
    if not _tem_tabela(acervo, "tbAvisoProtesto"):
        return feito
    # E AS COLUNAS TAMBEM SE CONFEREM, e nao so as tabelas: `strCB` e o
    # protocolo, e sem ele nada aqui tem por onde ligar. Foi o segundo tropeco
    # desta passada — guardei a tabela e supus as colunas dela.
    tem_cb = _tem_coluna(acervo, "tbAvisoProtesto", "strCB")
    tem_prot = _tem_coluna(acervo, "tbAvisoProtesto", "intProtocolo")
    if not (tem_cb or tem_prot):
        return feito
    tem_sdt = _tem_tabela(acervo, "tbSDT") and tem_prot
    tem_edital = _tem_tabela(acervo, "tbEdital")
    tem_aviso = _tem_tabela(acervo, "tbBoletoApto")
    tem_motivo = (_tem_tabela(acervo, "tbBoletoControleNEntrega")
                  and _tem_tabela(acervo, "tbMotivoNEntrega"))

    faltam = [dict(r) for r in con.execute(
        """SELECT id, origem_chave, protocolo, apresentante_codigo
             FROM pt_titulos
            WHERE origem_chave LIKE 'tbAvisoProtesto:%'
              AND (TRIM(COALESCE(protocolo,'')) = ''
                   OR TRIM(COALESCE(apresentante_codigo,'')) = ''
                   OR NOT EXISTS (SELECT 1 FROM pt_atos a
                                   WHERE a.titulo_id = pt_titulos.id
                                     AND a.tipo = 'INTIMACAO'))""")]
    if not faltam:
        return feito

    for t_ in faltam:
        chave = _chave_do_acervo(str(t_["origem_chave"]).split(":", 1)[-1])
        if chave is None:
            continue
        # A CONSULTA SE MONTA COM AS PARTES QUE EXISTEM. Escrever as cinco
        # subconsultas fixas faria a passada estourar num acervo sem uma
        # delas — e foi o que quebrou 19 testes da carga na primeira rodada.
        #
        # `strMotivo`, e nao `strDescricao`: eu inventei o nome e a execucao
        # me corrigiu. E o mesmo `tbMotivoNEntrega` que o aviso ja usa.
        pedacos = ["a.strCB" if tem_cb else "NULL strCB",
                   "a.intProtocolo" if tem_prot else "NULL intProtocolo"]
        pedacos.append(
            "(SELECT s.Campo02 FROM tbSDT s WHERE s.intProtocolo = "
            "a.intProtocolo ORDER BY s.intChave LIMIT 1) cod"
            if tem_sdt else "NULL cod")
        pedacos.append(
            "(SELECT s.Campo04 FROM tbSDT s WHERE s.intProtocolo = "
            "a.intProtocolo ORDER BY s.intChave LIMIT 1) nome"
            if tem_sdt else "NULL nome")
        pedacos.append(
            "(SELECT MAX(e.dtmpublicacao) FROM tbEdital e "
            "WHERE TRIM(e.strcb_ap) = TRIM(a.strCB)) edital_em"
            if (tem_edital and tem_cb) else "NULL edital_em")
        pedacos.append(
            "(SELECT MAX(b.dtmEntregaConfirmada) FROM tbBoletoApto b "
            "WHERE TRIM(b.strCB_AP) = TRIM(a.strCB)) entregue_em"
            if (tem_aviso and tem_cb) else "NULL entregue_em")
        pedacos.append(
            "(SELECT m.strMotivo FROM tbBoletoControleNEntrega n "
            "LEFT JOIN tbMotivoNEntrega m "
            "ON m.intCodigo = n.intCodigoMotivoNaoEntrega "
            "WHERE TRIM(n.strCB_AP) = TRIM(a.strCB) "
            "AND COALESCE(n.bitEntregue, 0) = 0 "
            "ORDER BY n.dtmEntrega DESC LIMIT 1) motivo"
            if (tem_motivo and tem_cb) else "NULL motivo")
        linha = acervo.execute(
            "SELECT " + ", ".join(pedacos)
            + " FROM tbAvisoProtesto a WHERE a.intChave = ?",
            (float(chave),)).fetchone()
        if linha is None:
            continue

        # O PROTOCOLO. `strCB` traz '0' num titulo do acervo — e '0' nao e
        # protocolo: e campo em branco preenchido com zero. Ali fica vazio.
        protocolo = _txt(linha["strCB"])
        if protocolo in ("", "0"):
            protocolo = _txt(_inteiro(linha["intProtocolo"]) or "")
        if protocolo and protocolo != "0" and not _txt(t_["protocolo"]):
            con.execute("UPDATE pt_titulos SET protocolo=? WHERE id=?",
                        (protocolo, int(t_["id"])))
            feito["protocolo"] += 1

        if _txt(linha["cod"]) and not _txt(t_["apresentante_codigo"]):
            con.execute(
                """UPDATE pt_titulos SET apresentante_codigo=?,
                       apresentante_nome=COALESCE(NULLIF(TRIM(?),''),
                                                  apresentante_nome)
                    WHERE id=?""",
                (_txt(linha["cod"]), _txt(linha["nome"]), int(t_["id"])))
            feito["apresentante"] += 1

        ja_tem = con.execute(
            "SELECT 1 FROM pt_atos WHERE titulo_id=? AND tipo='INTIMACAO'",
            (int(t_["id"]),)).fetchone()
        if ja_tem:
            continue
        if linha["edital_em"]:
            modo, quando = "EDITAL", _data(linha["edital_em"])
        elif linha["entregue_em"]:
            modo, quando = "PESSOAL", _data(linha["entregue_em"])
        else:
            feito["sem_intimacao"] += 1
            continue
        detalhe = {"modo": modo}
        # O MOTIVO SO CABE NO EDITAL: ele explica por que a entrega falhou, e
        # numa intimacao em maos ela nao falhou.
        if modo == "EDITAL" and linha["motivo"]:
            detalhe["motivo"] = _txt(linha["motivo"])
        con.execute(
            """INSERT INTO pt_atos(titulo_id, tipo, data_ato, detalhe_json,
                   origem, origem_chave, criado_em)
               VALUES (?,'INTIMACAO',?,?,?,?,?)""",
            (int(t_["id"]), quando or agora,
             json.dumps(detalhe, ensure_ascii=False),
             "EOFICIO", f"{t_['origem_chave']}:INTIMACAO", agora))
        feito["intimacao"] += 1

    for rotulo, quantos in (
            ("protocolos trazidos do acervo", feito["protocolo"]),
            ("apresentantes trazidos do acervo", feito["apresentante"]),
            ("intimações trazidas do acervo", feito["intimacao"])):
        if quantos:
            carga.contar(f"{rotulo} ({quantos})")
    if feito["sem_intimacao"]:
        carga.contar(
            f"títulos sem intimação no acervo do E-Ofício "
            f"({feito['sem_intimacao']}) — a maioria foi paga ou desistida "
            f"antes dela")
    return feito


def _pessoas_que_faltam(con: sqlite3.Connection, acervo: sqlite3.Connection,
                        *, carga: "Carga", agora: str) -> int:
    """Traz pais e avos dos assentos que ainda nao os tem. ESCREVE.

    Devolve QUANTAS pessoas entraram — `Carga.contar` guarda numero, e o
    numero e da RODADA e nao de uma linha. Por isso e `contar`, e nao
    `avisar`: "384 pessoas de filiacao" e um fato sobre a carga inteira, e
    virar 384 avisos de linha afogaria os avisos que sao de linha de verdade.
    """
    from pt_schema import normalizar_nome as _norm

    faltam = [dict(r) for r in con.execute(
        """SELECT a.id, a.especie, a.origem_chave
             FROM rc_assentos a
            WHERE a.origem = 'EOFICIO'
              AND NOT EXISTS (SELECT 1 FROM rc_pessoas p
                               WHERE p.assento_id = a.id)""")]
    if not faltam:
        return 0

    postos = 0
    for a in faltam:
        chave = _chave_do_acervo(a["origem_chave"])
        tipo = TIPO_DO_ACERVO.get(a["especie"])
        if chave is None or not tipo:
            continue
        linhas: list[tuple[str, dict, int]] = []
        if _tem_tabela(acervo, "tbFiliacao"):
            # AS LINHAS SE LEEM TODAS ANTES DE DECIDIR, porque a decisao e do
            # PAR e nao de cada uma: um assento tem um pai e uma mae.
            da_filiacao = [dict(x) for x in acervo.execute(
                "SELECT * FROM tbFiliacao WHERE intChaveRegistro=? "
                "AND intTipoRegistro=? ORDER BY intCodigoFiliacao",
                (chave, tipo))]
            papeis, duvidosos = papeis_da_filiacao(tipo, da_filiacao)
            if duvidosos:
                carga.avisar(
                    a["origem_chave"], FILIACAO_COM_SEXO_REPETIDO,
                    {"nomes": [x.get("strNome") for x in da_filiacao],
                     "sexos": [x.get("strSexo") for x in da_filiacao]})
            for r in da_filiacao:
                papel = papeis.get(_inteiro(r["intCodigoFiliacao"]))
                if papel:
                    # A ORDEM NA CERTIDAO: o pai antes da mae, e o primeiro
                    # conjuge antes do segundo.
                    ordem = (1 if papel.startswith("PAI") else 2)
                    if papel.endswith("NUBENTE2"):
                        ordem += 2
                    linhas.append((papel, dict(r), ordem))
        if tipo == 1 and _tem_tabela(acervo, "tbProgenitor"):
            for r in acervo.execute(
                    "SELECT * FROM tbProgenitor WHERE intChaveRegistro=? "
                    "AND intTipoRegistro=1 ORDER BY intCodigoProgenitor",
                    (chave,)):
                papel = PAPEL_DO_PROGENITOR.get(
                    (_inteiro(r["intCodigoFiliacao"]), _sexo(r["strSexo"])))
                if papel:
                    linhas.append(
                        (papel, dict(r),
                         2 + (_inteiro(r["intCodigoProgenitor"]) or 0)))

        for papel, r, ordem in linhas:
            nome = _txt(r.get("strNome"))
            if not nome:
                continue
            documento = _txt(r.get("strCPF"))
            con.execute(
                """INSERT OR IGNORE INTO rc_pessoas(assento_id, papel, nome,
                       nome_norm, sexo, documento_tipo, documento_numero,
                       profissao, nacionalidade, naturalidade_cidade,
                       naturalidade_uf, data_nascimento, estado_civil,
                       endereco, bairro, cidade, uf, cep, ordem, origem,
                       origem_chave, criado_em)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'EOFICIO',?,?)""",
                (a["id"], papel, nome, _norm(nome), _sexo(r.get("strSexo")),
                 "CPF" if documento else None, documento,
                 _txt(r.get("strProfissao")), _txt(r.get("strNacionalidade")),
                 _txt(r.get("strNaturalidadeCidade")) or _txt(r.get("strMunicipio")),
                 _txt(r.get("strNaturalidadeUF")) or _txt(r.get("strUF")),
                 _data(r.get("dtmDataNascimento")),
                 _txt(r.get("strEstadoCivil")),
                 _txt(r.get("strLogradouroEndereco")),
                 _txt(r.get("strBairroEndereco")),
                 _txt(r.get("strMunicipioEndereco")),
                 _txt(r.get("strUFEndereco")), _txt(r.get("strCep")),
                 ordem,
                 (f'{"tbProgenitor" if papel.startswith("AVO") else "tbFiliacao"}'
                  f':{_inteiro(r.get("intChave"))}'),
                 agora))
            postos += 1
    return postos


# ---------------------------------------- o declarante e as testemunhas
#
# QUEM DECLAROU O NASCIMENTO E QUEM ASSISTIU AO ATO — medido em 27/08/2026, e
# nenhum dos dois entrava:
#
#     tbDeclarante        225 linhas: 194 de nascimento, 31 de obito
#                         (casamento nao tem declarante, e esta certo)
#     tbTestemunhaRCPN    450 linhas: 364 de nascimento, 40 de casamento
#                         (2 por assento nos 20), 46 de obito
#
# POR QUE ISSO IMPORTA, e nao e enfeite: o declarante e **campo obrigatorio do
# assento** de nascimento e de obito (Lei 6.015/1973, arts. 54 e 80), e a
# certidao de obito o nomeia. As testemunhas sao o que prova que o ato foi
# praticado diante de alguem.
#
# SO 120 DOS 225 DECLARANTES TEM NOME no acervo, e os outros 105 estao mesmo
# vazios — `intCodigoDeclarante` e sempre `1`, entao nao e vinculo a resolver
# como foi o devedor do Protesto. Entra quem tem nome; quem nao tem nao vira
# linha vazia.

# ------------------ A PESSOA DE QUEM O ASSENTO E, e nao so os pais dela
#
# O BURACO QUE ISTO FECHA (medido em 28/08/2026)
#     `rc_pessoas` guardava PAI, MAE e AVOS — que a carga trouxe porque a
#     certidao de nascimento os cobrou — e NAO guardava o registrado, os
#     nubentes nem o falecido. O assento tinha o NOME deles e mais nada.
#
#     Duas coisas paravam nisso ao mesmo tempo: a REMESSA DO IBGE, que pede
#     sexo, data de nascimento, naturalidade, residencia e estado civil dessas
#     pessoas; e a CERTIDAO de casamento e a de obito, que descrevem essas
#     mesmas pessoas.
#
# E O ACERVO TEM TUDO, nas proprias tabelas de registro — nao em tabela
# separada como a filiacao. Medido:
#
#     NASCIMENTO  193/193 com sexo e data de nascimento, e com UF e cidade
#     CASAMENTO    20/20 com sexo, data e nome pos-casamento dos dois conjuges
#     OBITO        31/31 com sexo, data, estado civil, naturalidade e residencia
#
# O DE-PARA E POR COLUNA, E NAO POR NOME PARECIDO. As tres tabelas nomeiam a
# mesma coisa de tres jeitos — `strSexo`, `strSexoConjuge1`, `strSexo` — e o
# obito chama a residencia de `strMunicipioFalecido` enquanto o casamento a
# chama de `strMunicipioConjuge1`. Adivinhar pelo sufixo acertaria em algumas e
# erraria calado em outras.
O_PROPRIO_ASSENTO: dict[str, tuple[tuple[str, str, dict], ...]] = {
    # especie -> ((papel, tabela do acervo, de-para de coluna), ...)
    "NASCIMENTO": (
        ("REGISTRADO", "tbRegistroNascimento", {
            "sexo": "strSexo",
            "data_nascimento": "dtmDataNascimento",
            # O LUGAR DO NASCIMENTO E `strUF`/`strCidade`, e nao
            # `strUFNascido`/`strCidadeNascido`: as primeiras estao em 193 de
            # 193, e as segundas em 22. Escolher pelo nome mais parecido teria
            # perdido 171 assentos, em silencio.
            "naturalidade_uf": "strUF",
            "naturalidade_cidade": "strCidade",
        }),
    ),
    "CASAMENTO": (
        ("NUBENTE1", "tbRegistroCasamento", {
            "nome": "strNomeConjuge1",
            "nome_pos": "strNomePosCasamentoConjuge1",
            "sexo": "strSexoConjuge1",
            "data_nascimento": "dtmDataNascimentoConjuge1",
            "profissao": "strProfissaoConjuge1",
            "documento_numero": "strCPFConjuge1",
            "nacionalidade": "strNacionalidadeConjuge1",
            "naturalidade_uf": "strUFNaturalidadeConjuge1",
            "naturalidade_cidade": "strMunicipioNaturalidadeConjuge1",
            "naturalidade_pais": "strCodigoPaisConjuge1",
            "estado_civil": "strEstadoCivilConjuge1",
            "endereco": "strLogradouroConjuge1",
            "bairro": "strBairroConjuge1",
            "uf": "strUFConjuge1",
            "cidade": "strMunicipioConjuge1",
        }),
        ("NUBENTE2", "tbRegistroCasamento", {
            "nome": "strNomeConjuge2",
            "nome_pos": "strNomePosCasamentoConjuge2",
            "sexo": "strSexoConjuge2",
            "data_nascimento": "dtmDataNascimentoConjuge2",
            "profissao": "strProfissaoConjuge2",
            "documento_numero": "strCPFConjuge2",
            "nacionalidade": "strNacionalidadeConjuge2",
            "naturalidade_uf": "strUFNaturalidadeConjuge2",
            "naturalidade_cidade": "strMunicipioNaturalidadeConjuge2",
            "naturalidade_pais": "strCodigoPaisConjuge2",
            "estado_civil": "strEstadoCivilConjuge2",
            "endereco": "strLogradouroConjuge2",
            "bairro": "strBairroConjuge2",
            "uf": "strUFConjuge2",
            "cidade": "strMunicipioConjuge2",
        }),
    ),
    "OBITO": (
        ("FALECIDO", "tbRegistroObito", {
            "sexo": "strSexo",
            "data_nascimento": "dtmDataNascimento",
            "estado_civil": "strEstadoCivil",
            "profissao": "strProfissao",
            "nacionalidade": "strNacionalidade",
            "naturalidade_uf": "strUFNaturalidade",
            "naturalidade_cidade": "strMunicipioNaturalidade",
            "endereco": "strLogradouroFalecido",
            "bairro": "strBairroFalecido",
            "uf": "strUFFalecido",
            "cidade": "strMunicipioFalecido",
        }),
    ),
}

# A ORDEM EM QUE ELES APARECEM. Ela nao e enfeite: a certidao de casamento
# lista o primeiro nubente antes do segundo, e quem lesse sem ordem declarada
# teria de decidir de novo em cada tela.
ORDEM_DO_PAPEL: dict[str, int] = {
    "REGISTRADO": 0, "FALECIDO": 0, "NUBENTE1": 0, "NUBENTE2": 1,
}


# ------------------- O QUE A REMESSA DO IBGE PEDE, e que o acervo tem
#
# O ARQUIVO SO SE GERA COM ISTO, e a comparacao contra o que esta casa exportou
# de verdade provou: sem estes campos, `LOCAL-NASC`, `GEMEO`, `DN`, `NATUREZA`,
# `LOCAL` e `DO` saiam como «ignorado» nas 28 linhas de nascimento e nas 13 de
# obito. O resto da linha ja batia.
#
# O DE-PARA DO LOCAL DO NASCIMENTO NAO E DIRETO, e quase passou batido: o
# E-Oficio numera de 1 a 5 e o IBGE **nao tem 4** — ele pula do 3 para o 5. O
# de-para estava no proprio acervo, com esse nome: `tbRCPN_LocalNascimento` tem
# a coluna `intCodigoIBGE`, e ela diz que o `4` de la («Outros») e o `5` daqui,
# e que o `5` («Ignorado») e o `9`.
#
#   ANTES DE DEDUZIR UM DE-PARA, PROCURE A COLUNA QUE JA O TEM. Ela estava a um
#   `PRAGMA table_info` de distancia, e mandar o codigo de la direto faria o
#   IBGE recusar o trimestre inteiro.
#
# O GEMEO SE COMPOE de duas colunas: `bitGemeos` diz se houve, e
# `intQuantidadeGemeos` diz quantos. O IBGE quer um numero so — 1 nao e gemeo,
# 2 gemeo, 3 trigemeo ou mais.
#
# O LOCAL DO OBITO E TEXTO no acervo (`strTipoLocalObito`), e nao codigo: o
# de-para sai das palavras, e as tres que esta casa usa foram MEDIDAS contra o
# arquivo exportado — Hospital -> 1, Via Publica -> 4, Outros -> 5.
LOCAL_DO_OBITO_POR_PALAVRA: dict[str, int] = {
    # o que a casa escreveu, medido: 4 das 9 descricoes do catalogo do E-Oficio
    "hospital": 1, "via publica": 4, "outro": 5, "outros": 5, "domicilio": 3,
    # as outras cinco do catalogo, pelo que elas sao. NENHUMA tem uso no
    # acervo (zero assentos), e por isso nao ha o que medir — ficam aqui para
    # o dia em que aparecerem, e o comentario diz que sao deducao e nao medicao.
    "posto saude": 2, "outros servicos saude": 2,
    "ambulancia": 5, "samu": 5, "ignorado": 9,
}


# A NATUREZA DO OBITO, medida contra o arquivo que esta casa exportou: os 13
# obitos batem, com «Natural» -> 1 e «Violenta» -> 2. No acervo inteiro sao 27
# naturais e 4 violentas.
NATUREZA_DO_OBITO_POR_PALAVRA: dict[str, int] = {
    "natural": 1, "violenta": 2, "ignorado": 9, "ignorada": 9,
}


def _norm_ibge(texto: Any) -> str:
    from ibge_schema import normalizar_nome as _n
    return _n(texto)


def _local_do_obito(texto: Any) -> int | None:
    """O codigo do IBGE para o local do obito escrito em texto. So calcula."""
    return LOCAL_DO_OBITO_POR_PALAVRA.get(_norm_ibge(texto))


def _gemeo_do_ibge(houve: Any, quantos: Any) -> int:
    """`bitGemeos` + `intQuantidadeGemeos` -> o codigo do IBGE. So calcula."""
    n = _inteiro(quantos) or 0
    if not _inteiro(houve) and n <= 1:
        return 1                       # nao e gemeo
    return 3 if n >= 3 else 2          # trigemeo ou mais / gemeo


def _campos_do_ibge_que_faltam(con: sqlite3.Connection,
                               acervo: sqlite3.Connection, *,
                               agora: str) -> dict[str, int]:
    """Traz local do nascimento, gemeo, DNV, DO, natureza e local do obito.

    PASSADA A PARTE, pelo mesmo motivo das outras tres: ela olha o assento que
    ainda nao tem AQUELE campo, e por isso funciona na primeira rodada e na
    centesima.
    """
    postos: dict[str, int] = {}

    # ---- o de-para do local do nascimento, lido do proprio acervo
    de_para: dict[int, int] = {}
    if _tem_tabela(acervo, "tbRCPN_LocalNascimento"):
        for r in acervo.execute(
                "SELECT id, intCodigoIBGE FROM tbRCPN_LocalNascimento"):
            de, para = _inteiro(r["id"]), _inteiro(r["intCodigoIBGE"])
            if de is not None and para is not None:
                de_para[de] = para

    pedidas_nasc = ", ".join(
        f"{origem} {apelido}" for apelido, origem in
        _colunas_que_existem(acervo, "tbRegistroNascimento", {
            "loc": "intCodigoLocalNascimento", "g": "bitGemeos",
            "qg": "intQuantidadeGemeos",
            "dnv": "strDeclaracaoNascidoVivo"}).items()
    ) if _tem_tabela(acervo, "tbRegistroNascimento") else ""
    # A CONSULTA SE MONTA COM O QUE AQUELE ACERVO TEM, e nao com a lista que eu
    # escrevi: pedir coluna que nao existe **estoura**, e derruba a carga
    # inteira. O E-Oficio mudou de versao ao longo dos anos.
    if pedidas_nasc:
        faltam = [dict(r) for r in con.execute(
            "SELECT id, origem_chave FROM rc_assentos"
            " WHERE origem='EOFICIO' AND especie='NASCIMENTO'"
            "   AND ibge_local_nascimento IS NULL AND ibge_gemeo IS NULL"
            "   AND dnv IS NULL")]
        n = 0
        for a in faltam:
            chave = _chave_do_acervo(a["origem_chave"])
            if chave is None:
                continue
            r = acervo.execute(
                f"SELECT {pedidas_nasc} FROM tbRegistroNascimento"
                f" WHERE intChave=?", (chave,)).fetchone()
            if r is None:
                continue
            r = dict(r)
            con.execute(
                "UPDATE rc_assentos SET ibge_local_nascimento=?, ibge_gemeo=?,"
                " dnv=? WHERE id=?",
                (de_para.get(_inteiro(r.get("loc"))),
                 _gemeo_do_ibge(r.get("g"), r.get("qg")),
                 _txt(r.get("dnv")), a["id"]))
            n += 1
        if n:
            postos["nascimento"] = n

    pedidas_obito = ", ".join(
        f"{origem} {apelido}" for apelido, origem in
        _colunas_que_existem(acervo, "tbRegistroObito", {
            "d": "strNumeroDeclaracaoObito", "l": "strTipoLocalObito",
            "tm": "strTipoMorte"}).items()
    ) if _tem_tabela(acervo, "tbRegistroObito") else ""
    if pedidas_obito:
        faltam = [dict(r) for r in con.execute(
            "SELECT id, origem_chave FROM rc_assentos"
            " WHERE origem='EOFICIO' AND especie='OBITO'"
            "   AND numero_do IS NULL AND ibge_local_obito IS NULL"
            "   AND ibge_natureza_obito IS NULL")]
        n = 0
        for a in faltam:
            chave = _chave_do_acervo(a["origem_chave"])
            if chave is None:
                continue
            r = acervo.execute(
                f"SELECT {pedidas_obito} FROM tbRegistroObito WHERE intChave=?",
                (chave,)).fetchone()
            if r is None:
                continue
            r = dict(r)
            # A NATUREZA DO OBITO ESTAVA NO ACERVO, e eu escrevi aqui, uma
            # hora antes, que ela NAO estava.
            #
            #   Eu havia procurado por `natureza` e por `causa`, nao achei, e
            #   concluí que o E-Oficio deduzia do local ou que alguem digitava
            #   na hora de exportar. A coluna se chama **`strTipoMorte`**, e
            #   traz «Natural» em 27 e «Violenta» em 4 — e o de-para contra o
            #   arquivo exportado fecha em **13 de 13**: Natural -> 1,
            #   Violenta -> 2.
            #
            #   E A MESMA LICAO PELA QUARTA VEZ NESTE PROJETO: o `codigoAto`
            #   que estava no `memJson` e nao na coluna homonima; os dois
            #   contadores do RCPN que estavam em `tbPropriedadeRCPN`; o
            #   de-para do local do nascimento que estava em `intCodigoIBGE`.
            #   **Nao achar a coluna que eu procurei nao prova que o dado nao
            #   existe** — prova que eu procurei pelo nome errado.
            con.execute(
                "UPDATE rc_assentos SET numero_do=?, ibge_local_obito=?,"
                " ibge_natureza_obito=? WHERE id=?",
                (_txt(r.get("d")), _local_do_obito(r.get("l")),
                 NATUREZA_DO_OBITO_POR_PALAVRA.get(_norm_ibge(r.get("tm"))),
                 a["id"]))
            n += 1
        if n:
            postos["obito"] = n
    return postos


NASCE_DEPOIS_DO_ATO = (
    "a data de nascimento do acervo é posterior ao próprio ato — não entrou")


def _nascimento_possivel(nascimento: Any, ato: Any) -> bool:
    """Se aquela data de nascimento pode ser verdade. So calcula.

    NINGUEM NASCE DEPOIS DO ATO QUE O REGISTRA, e no acervo desta casa **21 das
    244 pessoas** nascem: 7 dos 20 casamentos em cada conjuge, 6 dos 193
    nascimentos e 1 dos 31 obitos. O valor guardado nao e a data de nascimento
    — e a data em que alguem digitou o registro antigo, com o campo em branco
    pegando o dia de hoje.

    NAO SE CONSERTA, E NAO SE IMPORTA COMO SE FOSSE VERDADE. A certidao
    imprimiria uma data falsa e o IBGE receberia uma idade absurda; as duas
    coisas sao piores que o campo vazio, porque campo vazio nao afirma nada.

    Quem nao passa aqui entra SEM data, e a carga AVISA com o numero do
    assento — para quem for a estante saber a quais ir.
    """
    n, a = str(nascimento or "")[:10], str(ato or "")[:10]
    if len(n) != 10 or len(a) != 10:
        return True          # sem uma das duas nao ha o que comparar
    return n <= a


def _o_proprio_assento_que_falta(con: sqlite3.Connection,
                                 acervo: sqlite3.Connection, *,
                                 carga: "Carga", agora: str) -> dict[str, int]:
    """Traz o registrado, os nubentes e o falecido. ESCREVE.

    PASSADA A PARTE, PELA TERCEIRA VEZ NESTE MODULO, e pelo mesmo motivo: ela
    procura assento sem pessoa **daquele papel**, e nao assento sem pessoa
    nenhuma. Depois que a filiacao rodou, todo assento tem gente — e uma
    passada que perguntasse «tem alguem?» nunca mais acharia nada.

    O NOME SAI DO ASSENTO quando o acervo nao o traz separado: no nascimento e
    no obito, `rc_assentos.nome` E o nome do registrado e do falecido. No
    casamento nao da — sao dois nomes —, e por isso o de-para os busca.
    """
    from pt_schema import normalizar_nome as _norm

    postos: dict[str, int] = {}
    for especie, papeis in O_PROPRIO_ASSENTO.items():
        tipo = TIPO_DO_ACERVO.get(especie)
        for papel, tabela, de_para in papeis:
            if not _tem_tabela(acervo, tabela) or not tipo:
                continue
            faltam = [dict(r) for r in con.execute(
                "SELECT a.id, a.nome, a.origem_chave, a.data_ato, "
                "       a.data_fato FROM rc_assentos a "
                "WHERE a.origem = 'EOFICIO' AND a.especie = ? "
                "AND NOT EXISTS (SELECT 1 FROM rc_pessoas p "
                "WHERE p.assento_id = a.id AND p.papel = ?)",
                (especie, papel))]
            entraram, ultimo = 0, None
            for a in faltam:
                chave = _chave_do_acervo(a["origem_chave"])
                if chave is None:
                    continue
                r = acervo.execute(
                    'SELECT * FROM "%s" WHERE intChave = ?' % tabela,
                    (chave,)).fetchone()
                if r is None:
                    continue
                bruto = dict(r)
                # SO O QUE AQUELE ACERVO TEM. Coluna ausente vira campo vazio,
                # e nao carga derrubada: o E-Oficio mudou de versao ao longo
                # dos anos, e nem todo acervo traz as mesmas colunas.
                v = {alvo: _txt(bruto.get(origem))
                     for alvo, origem in de_para.items()
                     if origem in bruto}
                nome = v.get("nome") or _txt(a["nome"])
                if not nome:
                    # SEM NOME NAO ENTRA. Linha de pessoa sem nome numa certidao
                    # e pior que ausencia: afirma que ha alguem e nao diz quem.
                    continue
                documento = v.get("documento_numero")
                # A DATA DE NASCIMENTO SE CONFERE CONTRA O PROPRIO ATO.
                #
                #   `data_fato` e a data do nascimento, do casamento ou do
                #   obito; `data_ato` e a do registro. Vale a mais antiga que
                #   existir: quem nasce depois de qualquer uma das duas nao
                #   nasceu naquele dia.
                nascimento = _data(bruto.get(de_para.get("data_nascimento", "")))
                limite = min([d for d in (_data(a["data_fato"]),
                                          _data(a["data_ato"])) if d],
                             default=None)
                if nascimento and not _nascimento_possivel(nascimento, limite):
                    carga.avisar(a["origem_chave"], NASCE_DEPOIS_DO_ATO,
                                 {"papel": papel, "nome": nome,
                                  "no_acervo": nascimento, "ato": limite})
                    nascimento = None
                cur = con.execute(
                    "INSERT OR IGNORE INTO rc_pessoas(assento_id, papel, nome,"
                    " nome_norm, nome_pos, sexo, documento_tipo,"
                    " documento_numero, profissao, nacionalidade,"
                    " naturalidade_cidade, naturalidade_uf, naturalidade_pais,"
                    " data_nascimento, estado_civil, endereco, bairro, cidade,"
                    " uf, ordem, origem, origem_chave, criado_em)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,"
                    "'EOFICIO',?,?)",
                    (a["id"], papel, nome, _norm(nome), v.get("nome_pos"),
                     _sexo(v.get("sexo")),
                     "CPF" if documento else None, documento,
                     v.get("profissao"), v.get("nacionalidade"),
                     v.get("naturalidade_cidade"), v.get("naturalidade_uf"),
                     v.get("naturalidade_pais"),
                     nascimento,
                     v.get("estado_civil"), v.get("endereco"), v.get("bairro"),
                     v.get("cidade"), v.get("uf"),
                     ORDEM_DO_PAPEL.get(papel, 0),
                     # A CHAVE E DA PESSOA, E NAO DO ASSENTO — e isto foi um
                     # defeito meu de cinco minutos, achado pelo ensaio contra
                     # o acervo real. `rc_pessoas` tem `UNIQUE(origem,
                     # origem_chave)`, e os dois nubentes moram na MESMA linha
                     # do acervo: com a chave do assento, o NUBENTE1 entrava e
                     # o NUBENTE2 era ignorado em silencio pelo OR IGNORE.
                     #
                     # A carga dizia «entraram 20» e a tabela tinha ZERO. O
                     # papel entra na chave porque e ele que distingue as duas
                     # pessoas dentro do mesmo registro.
                     f'{a["origem_chave"]}:{papel}', agora))
                # CONTAR O QUE ENTROU, E NAO O QUE SE TENTOU. E a regra da
                # casa (o `lastrowid` mudar, e nao o `rowcount`), e foi ela que
                # deixou o defeito acima visivel em vez de calado.
                if cur.lastrowid and cur.lastrowid != ultimo:
                    ultimo = cur.lastrowid
                    entraram += 1
            if entraram:
                postos[papel] = postos.get(papel, 0) + entraram
    return postos


PESSOAS_LIGADAS_AO_ASSENTO: tuple[tuple[str, str, str, tuple[int, ...]], ...] = (
    # papel          tabela do acervo     coluna da chave       tipos que a tem
    ("DECLARANTE",   "tbDeclarante",      "intChaveRegistro",   (1, 3)),
    ("TESTEMUNHA",   "tbTestemunhaRCPN",  "intChaveRegistro",   (1, 2, 3)),
)


def _ligadas_que_faltam(con: sqlite3.Connection, acervo: sqlite3.Connection,
                        *, agora: str) -> dict[str, int]:
    """Traz declarante e testemunhas dos assentos que ainda nao os tem. ESCREVE.

    PASSADA A PARTE, E NAO DENTRO DA DE FILIACAO — a licao do devedor do
    Protesto, pela segunda vez. Aquela procura assento **sem pessoa nenhuma**;
    um assento que ja tem pai e mae nunca voltaria por la, e o declarante nunca
    chegaria nele. Esta procura assento sem pessoa **daquele papel**, e por
    isso funciona tanto na primeira rodada quanto na centesima.

    Devolve quantos entraram, por papel — numero da RODADA, para `Carga.contar`.
    """
    from pt_schema import normalizar_nome as _norm

    postos: dict[str, int] = {}
    for papel, tabela, coluna, tipos in PESSOAS_LIGADAS_AO_ASSENTO:
        if not _tem_tabela(acervo, tabela):
            continue
        faltam = [dict(r) for r in con.execute(
            """SELECT a.id, a.especie, a.origem_chave
                 FROM rc_assentos a
                WHERE a.origem = 'EOFICIO'
                  AND NOT EXISTS (SELECT 1 FROM rc_pessoas p
                                   WHERE p.assento_id = a.id AND p.papel = ?)""",
            (papel,))]
        entraram = 0
        for a in faltam:
            chave = _chave_do_acervo(a["origem_chave"])
            tipo = TIPO_DO_ACERVO.get(a["especie"])
            if chave is None or tipo not in tipos:
                continue
            for ordem, r in enumerate(acervo.execute(
                    f"SELECT * FROM [{tabela}] WHERE [{coluna}]=? "
                    f"AND intTipoRegistro=? ORDER BY intChave",
                    (chave, tipo)), start=1):
                r = dict(r)
                nome = _txt(r.get("strNome"))
                if not nome:
                    # 105 dos 225 declarantes do acervo estao sem nome. Linha
                    # vazia na certidao e pior que ausencia: ela afirma que ha
                    # um declarante e nao diz quem.
                    continue
                # SO DIGITOS, como no resto da casa: o acervo grava CPF com
                # ponto e traco, e documento com pontuacao nao casa com
                # documento sem.
                documento = "".join(
                    ch for ch in str(r.get("strCPF") or "") if ch.isdigit()) or None
                con.execute(
                    """INSERT OR IGNORE INTO rc_pessoas(assento_id, papel, nome,
                           nome_norm, sexo, documento_tipo, documento_numero,
                           profissao, nacionalidade, naturalidade_cidade,
                           naturalidade_uf, endereco, bairro, cidade, uf,
                           ordem, origem, origem_chave, criado_em)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'EOFICIO',?,?)""",
                    (a["id"], papel, nome, _norm(nome), _sexo(r.get("strSexo")),
                     "CPF" if documento else None, documento,
                     _txt(r.get("strProfissao")),
                     _txt(r.get("strNacionalidade")),
                     _txt(r.get("strMunicipioNaturalidade")),
                     _txt(r.get("strUFNaturalidade")),
                     _txt(r.get("strLogradouro")), _txt(r.get("strBairro")),
                     _txt(r.get("strMunicipio")), _txt(r.get("strUF")),
                     ordem, f'{tabela}:{_inteiro(r.get("intChave"))}', agora))
                entraram += 1
        if entraram:
            postos[papel] = entraram
    return postos


# ------------------------------------------------------------- RCPJ e RTD


def carregar_rcpj_rtd(con: sqlite3.Connection, acervo: sqlite3.Connection,
                      *, agora: str) -> Carga:
    """Os registros de `tbRegistroTD` — 41 do RTD e 31 do RCPJ.

    `strTipoRegistro` diz de qual atribuicao e cada linha: `TD` ou `PJ`. A
    serie sai dele com o livro; onde o livro nao casa com nenhuma serie
    conhecida, a linha e rejeitada em vez de entrar num livro arbitrado.
    """
    carga = Carga("rcpj_rtd")
    if not _tem_tabela(acervo, "tbRegistroTD"):
        raise CargaError("O acervo não tem `tbRegistroTD`.")

    def mapear(r: sqlite3.Row) -> dict | None:
        tipo = (_txt(r["strTipoRegistro"]) or "").upper()
        if tipo not in ("TD", "PJ"):
            carga.rejeitar(r["intChave"],
                           f"tipo de registro desconhecido: {tipo!r}", dict(r))
            return None
        # O acervo grava o livro como '7', '05', '5', '04'. O E-Oficio nao
        # guarda a LETRA do livro (B, C, F do RTD; A, B do RCPJ), so o numero
        # do volume — e sem a letra nao ha como dizer em que serie o ato
        # entrou. Tudo vai para a serie principal de cada atribuicao, e o
        # numero do volume fica em `natureza` para nao se perder.
        serie = "TD_B" if tipo == "TD" else "PJ_A"
        atribuicao = 4 if tipo == "TD" else 3
        return {
            "atribuicao": atribuicao,
            "serie": serie,
            "volume": _txt(r["strLivro"]),
            "numero": _inteiro(r["intNumeroRegistro"]),
            "natureza": _txt(r["strTipoInscricaoMatricula"]),
            "requerente_nome": _txt(r["strApresentante"]),
            "situacao": "ATIVO",
            "teor": _txt(r["memInteiroTeorSemFormatacao"])
                    or _txt(r["memInteiroTeor"]),
            "origem": "EOFICIO",
            "origem_chave": f"tbRegistroTD:{r['intChave']}",
            "criado_em": agora,
        }

    def ato_de_registro(c: sqlite3.Connection, registro_id: int,
                        r: sqlite3.Row) -> None:
        """O ato de REGISTRO, com a folha e a data que o acervo tem.

        A CERTIDAO COBROU ISTO. A certidao de inteiro teor do RCPJ/RTD diz
        "no Livro X, fls. Y, ATO n. Z datada de DD/MM/AAAA", e ate 25/08/2026
        a carga trazia o registro sem ato — sem folha e sem data.

        Medido nos 72 registros do acervo: `dtmData` e `strFolha_DE` estao
        preenchidos em TODOS. `strFolha_DE` e so digitos nos 72 — nenhum traz
        marca de verso —, e `strFolha_ATE` esta vazia nos 72: a faixa de
        folhas que as certidoes antigas mostram ("fls. 030V A 034") foi
        digitada na certidao, e nao guardada. Sai a folha inicial, que e o que
        existe.
        """
        c.execute(
            """INSERT INTO rg_atos(registro_id, tipo, folha, numero_ordem,
                   data_ato, teor, origem, origem_chave, criado_em)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (registro_id, "REGISTRO", _inteiro(r["strFolha_DE"]),
             _inteiro(r["intNumeroRegistro"]),
             _data(r["dtmData"]) or agora,
             _txt(r["memInteiroTeorSemFormatacao"]) or _txt(r["memInteiroTeor"]),
             "EOFICIO", f"tbRegistroTD:{r['intChave']}:REGISTRO", agora))

    linhas = acervo.execute("SELECT * FROM tbRegistroTD ORDER BY intChave")
    return _executar(con, carga, "rg_registros", linhas, mapear,
                     lambda r: r["intChave"], depois=ato_de_registro)


# ------------------------------------------------- o Registro Auxiliar


def carregar_registro_auxiliar(con: sqlite3.Connection,
                               acervo: sqlite3.Connection, *,
                               agora: str) -> Carga:
    """O Livro 3, de `LivroAuxiliar` — as 14 cedulas, dos registros 1315 a 1636.

    ATENCAO A TABELA CERTA. `tbRI_Auxiliar`, apesar do nome, NAO e o Registro
    Auxiliar: os `strLivro` dela sao volumes do Livro 2 (`2`, `2-A`, `2-C`,
    `2S`). Quem carregar de lá enche o Livro 3 com 1.273 atos do Registro
    Geral. Ver o cabecalho de `ra_schema.py`.

    O QUE ELA TRAZ, DESDE 18/09/2026
        O REGISTRO e o ato R-1 saem daqui; as PARTES e as AVERBACOES saem de
        `_partes_e_averbacoes_do_livro3`, logo abaixo, numa passada que olha o
        que falta — e que por isso alcanca tambem os registros que ja estavam
        gravados antes desta data.
    """
    carga = Carga("registro_auxiliar")
    if not _tem_tabela(acervo, "LivroAuxiliar"):
        raise CargaError("O acervo não tem `LivroAuxiliar`.")

    def mapear(r: sqlite3.Row) -> dict | None:
        numero = _inteiro(r["Registro"])
        if not numero:
            carga.rejeitar(r["Id"], "registro sem número", dict(r))
            return None
        # QUEM DEFINE A PERTINENCIA E A TABELA, E NAO A COLUNA.
        #
        # A primeira versao recusava linha cujo `Livro` nao fosse '3', e isso
        # perdia o registro 1551 — uma cedula de credito bancario com `Livro`
        # gravado como '-'. Estar em `LivroAuxiliar` E ser do Livro 3; a
        # coluna so nem sempre foi preenchida. O valor esquisito fica anotado
        # em `observacao` para nao se perder.
        livro = _txt(r["Livro"])
        estranho = None
        if livro not in ("3", None):
            estranho = f"Livro na origem: {livro!r}"
            carga.avisar(r["Id"], f"Livro gravado como {livro!r} na origem, "
                                  f"e não '3' — entrou como Livro 3", dict(r))
        return {
            "numero": numero,
            "livro": "3",
            "natureza": _natureza_do_titulo(r["Titulo"]),
            "titulo_tipo": _txt(r["Titulo"]),
            "titulo_numero": _txt(r["Numero"]),
            "data_titulo": _data(r["Data"]),
            "valor_centavos": _centavos(r["ValorCompraVenda"]),
            "parcelas": _inteiro(r["Parcelas"]),
            "vencimento_inicial": _data(r["VencimentoInicial"]),
            "vencimento_final": _data(r["VencimentoFinal"]),
            "juros": _txt(r["Juros"]),
            "garantia": _txt(r["Garantia"]),
            "condicoes": _juntar(_txt(r["Condicoes"]), estranho),
            "cnm": _txt(r["strCNM"]),
            "teor": _txt(r["Teor"]),
            "situacao": "ATIVO",
            "origem": "EOFICIO",
            "origem_chave": f"LivroAuxiliar:{r['Id']}",
            "criado_em": agora,
        }

    def ato_de_registro(c: sqlite3.Connection, registro_id: int,
                        r: sqlite3.Row) -> None:
        c.execute(
            """INSERT INTO ra_atos(registro_id, tipo, numero, data_ato, teor,
                   origem, origem_chave, criado_em)
               VALUES (?,?,?,?,?,?,?,?)""",
            (registro_id, "R", 1, _data(r["Data"]) or agora, _txt(r["Teor"]),
             "EOFICIO", f"LivroAuxiliar:{r['Id']}:R1", agora))

    linhas = acervo.execute("SELECT * FROM LivroAuxiliar ORDER BY Registro")
    carga = _executar(con, carga, "ra_registros", linhas, mapear,
                      lambda r: r["Id"], depois=ato_de_registro)

    # AS PARTES E AS AVERBACOES, NUMA PASSADA A PARTE — e nao pelo `depois` da
    # linha, pelo mesmo motivo da filiacao do RCPN e do devedor do Protesto:
    # `_executar` so chama o `depois` de quem ENTROU AGORA. Quem rodou esta
    # carga antes de 18/09/2026 tem os 14 registros gravados, e eles voltam
    # como `repetidos` — as partes e as baixoes nunca chegariam neles.
    for rotulo, quantos in _partes_e_averbacoes_do_livro3(
            con, acervo, agora=agora).items():
        carga.contar(rotulo, quantos)
    return carga


# ------------------- o Livro 3: as partes e as averbacoees do acervo
#
# O QUE FALTAVA, MEDIDO NA PRODUCAO EM 18/09/2026
#
#     `carregar_registro_auxiliar` trazia o REGISTRO e o ato R-1, e mais nada.
#     As 25 partes de `LivroAuxiliarPartes` e as 5 averbacoees de
#     `LivroAuxiliarAverbacao` ficavam no acervo: o sistema tinha os 14
#     registros, ZERO partes e nenhuma das baixas e retificacoes que a casa
#     averbou depois de registrar. A ficha do Livro 3 abria sem os emitentes e
#     sem os credores — e o Livro 2, ao lado, entrou com 3.986 partes.
#
# A TABELA DAS PARTES E `tbOrtoga`, E NAO `tbPessoa` — e isto foi medido, nao
# escolhido. `LivroAuxiliarPartes.ParteId` casa com `tbOrtoga.intCodigo`; o
# `tbPessoa` e espaco de id DIFERENTE: medido no acervo desta casa, o id 10018
# e o «BANCO DO BRASIL S/A» no `tbOrtoga` e «DAVI QUEIROZ ARAUJO» no
# `tbPessoa`. Quem escolhesse a tabela pelo nome traria o credor errado para a
# ficha e para o alerta de fraude. Por isso aqui NAO ha queda para o
# `tbPessoa`: parte que o `tbOrtoga` nao resolve e contada e nao entra — nome
# trocado e pior que nome faltando.
#
# A PARTE DA AVERBACAO QUE JA E PARTE DO REGISTRO NAO SE REPETE. Medido nas 10
# linhas de `LivroAuxiliarAverbacaoPartes`: **as 7 pessoas que elas nomeiam ja
# estao entre as 25 partes do registro** — a tabela da averbacao repete o
# registro. Repetir aqui poria a mesma pessoa duas vezes na ficha, e o que a
# averbacao diz de proprio e o TEXTO dela, que entra no ato.
#
# O QUE NAO ENTRA, E FICA DECLARADO
#     - O TIPO da averbacao (`TipoAverbacao`: «AVERBACAO DE BAIXA», «... DE
#       RETIFICACAO»). Ele nao e do vocabulario de `ra_atos.natureza` — que e o
#       de `ra_registro.NATUREZAS` —, e inventar valor em coluna de vocabulario
#       faz o proximo leitor tropecar. As palavras do tipo estao dentro do
#       proprio texto da averbacao, que entra inteiro;
#     - A MARCA DE CANCELADO. Tres das cinco averbacoees sao de BAIXA
#       (registros 1315, 1409 e 1560) e os tres registros continuam `ATIVO`
#       aqui, porque o acervo NAO tem marca de cancelamento — o `LivroAuxiliar`
#       nao tem coluna disso. Mudar a situacao a partir do TEXTO da averbacao
#       seria a maquina decidindo o ato. Fica para o oficial, com os numeros;
#     - O `Credor` (0/1), que e do REGISTRO — as 25 partes dele tem esse campo
#       preenchido de forma inconsistente (as linhas 9 e 10027 trazem 0, e as
#       partes das averbacoees nao tem a coluna). O lado do papel ja esta dito
#       no `papel`.


def _ortoga_da_parte(acervo: sqlite3.Connection, parte_id: Any,
                     cache: dict) -> dict | None:
    """A pessoa de uma parte do Livro 3, por `tbOrtoga`. Só LÊ.

    O TIPO DIZ ONDE ESTA O DOCUMENTO, e nao o tamanho do que estiver escrito —
    a mesma leitura de `_pessoa` e de `ri_import._pessoa_normalizada`. E o
    documento sai em digitos, que e a forma com que o Livro 2 guardou os dele
    (`so_digitos`): o CNPJ do Banco do Brasil e `00000010000127`, e os zeros a
    esquerda sao parte do numero.
    """
    try:
        chave = int(parte_id)
    except (TypeError, ValueError):
        return None
    if chave in cache:
        return cache[chave]
    linha = acervo.execute(
        "SELECT strTipoPessoa, strNome, PJ_RazaoSocial, strCPF, strCNPJ "
        "FROM tbOrtoga WHERE CAST(intCodigo AS INTEGER)=?", (chave,)).fetchone()
    dado = None
    if linha is not None:
        tipo = (_txt(linha["strTipoPessoa"]) or "").upper()
        razao, nome = _txt(linha["PJ_RazaoSocial"]), _txt(linha["strNome"])
        pessoa = (razao if tipo == "J" else nome) or nome or razao
        if pessoa:
            cpf, cnpj = so_digitos(linha["strCPF"]), so_digitos(linha["strCNPJ"])
            if tipo == "J" and cnpj:
                documento_tipo, documento_numero = "CNPJ", cnpj
            elif tipo == "F" and cpf:
                documento_tipo, documento_numero = "CPF", cpf
            elif cnpj:
                documento_tipo, documento_numero = "CNPJ", cnpj
            elif cpf:
                documento_tipo, documento_numero = "CPF", cpf
            else:
                documento_tipo, documento_numero = None, None
            dado = {"nome": pessoa, "documento_tipo": documento_tipo,
                    "documento_numero": documento_numero}
    cache[chave] = dado
    return dado


def _papel_da_qualificacao(acervo: sqlite3.Connection, qual_id: Any,
                           cache: dict) -> str | None:
    """O papel por extenso de um `QualificacaoId` do acervo. Só LÊ.

    A palavra e a do acervo — «CREDOR(A)», «Emitente/Creditado»,
    «Proprietario(a)» —, e nao uma traducao minha: e ela que o balcao le na
    ficha hoje, e reescreve-la faria o livro do sistema discordar do livro de
    papel na unica coisa que o identifica.
    """
    try:
        chave = int(qual_id)
    except (TypeError, ValueError):
        return None
    if chave in cache:
        return cache[chave]
    linha = acervo.execute(
        "SELECT strDescricao FROM tbQualificacaoPartes "
        "WHERE CAST(intChave AS INTEGER)=?", (chave,)).fetchone()
    cache[chave] = _txt(linha["strDescricao"]) if linha is not None else None
    return cache[chave]


def _partes_e_averbacoes_do_livro3(con: sqlite3.Connection,
                                   acervo: sqlite3.Connection, *,
                                   agora: str) -> dict[str, int]:
    """As partes e as averbacoees do Livro 3 do acervo. ESCREVE (e a carga).

    Devolve os numeros medidos, para o `contar` da carga — como as outras
    passadas que olham o que falta. O que ela devolve sao FATOS, e nao
    tentativas: o mesmo molde de `_pessoas_que_faltam`.

    Repetivel por construcao, e por tres chaves diferentes:
      - `ra_registros.origem_chave` -> a qual registro a linha pertence;
      - `ra_partes.origem_chave` e `ra_atos.origem_chave` -> o que ja entrou;
      - e, para a parte da averbacao, a propria pessoa (nome + documento +
        papel) ja presente no registro.
    """
    numeros: dict[str, int] = {}

    def contar(rotulo: str, quantos: int = 1) -> None:
        numeros[rotulo] = numeros.get(rotulo, 0) + quantos

    # 1. de `origem_chave` para o id que o registro tem aqui.
    por_chave: dict[str, int] = {}
    for r in con.execute("SELECT id, origem_chave FROM ra_registros "
                         "WHERE origem='EOFICIO' AND origem_chave IS NOT NULL"):
        chave = _txt(r["origem_chave"])
        if chave and chave.startswith("LivroAuxiliar:"):
            por_chave[chave] = int(r["id"])

    partes_ja = {_txt(r["origem_chave"]) for r in con.execute(
        "SELECT origem_chave FROM ra_partes "
        "WHERE origem='EOFICIO' AND origem_chave IS NOT NULL")}
    atos_ja = {_txt(r["origem_chave"]): int(r["id"]) for r in con.execute(
        "SELECT id, origem_chave FROM ra_atos "
        "WHERE origem='EOFICIO' AND origem_chave IS NOT NULL")}

    # O QUE A FICHA JA MOSTRA, por registro: (nome, documento, papel). Serve
    # para nao por a mesma pessoa duas vezes — e e por pessoa, e nao por
    # `ParteId`, porque quem le a ficha le o nome.
    pessoas_do_registro: dict[int, set[tuple]] = {}
    if por_chave:
        ids = tuple(sorted(set(por_chave.values())))
        marcadores = ",".join("?" * len(ids))
        for r in con.execute(
                f"SELECT registro_id, nome, documento_numero, papel "
                f"FROM ra_partes WHERE registro_id IN ({marcadores})", ids):
            pessoas_do_registro.setdefault(int(r["registro_id"]), set()).add(
                (_txt(r["nome"]), _txt(r["documento_numero"]), _txt(r["papel"])))

    tem_ortoga = _tem_tabela(acervo, "tbOrtoga")
    tem_qualificacao = _tem_tabela(acervo, "tbQualificacaoPartes")
    cache_pessoa: dict[int, dict | None] = {}
    cache_papel: dict[int, str | None] = {}

    def gravar_parte(registro_id: int, ato_id: int | None, chave: str,
                     parte_id: Any, qual_id: Any,
                     ja_no_registro: bool = False) -> bool:
        """Grava uma parte, se ela ainda nao estiver. Devolve se entrou.

        A razao de nao ter entrado ja fica CONTADA aqui dentro: quem chama
        trata o `False` do mesmo jeito nos tres casos, e a contagem — que e o
        que a carga informa — sai certa de qualquer um deles.
        """
        if chave in partes_ja:
            contar("partes que já estavam no Livro 3")
            return False
        if not tem_ortoga:
            contar("partes sem `tbOrtoga` no acervo (não entraram)")
            return False
        pessoa = _ortoga_da_parte(acervo, parte_id, cache_pessoa)
        if not pessoa:
            contar("partes que o `tbOrtoga` não resolveu (não entraram)")
            return False
        papel = (_papel_da_qualificacao(acervo, qual_id, cache_papel)
                 if tem_qualificacao else None)
        if ja_no_registro:
            # A mesma pessoa, com o mesmo papel, ja esta na ficha daquele
            # registro: pô-la de novo faria a ficha mostra-la duas vezes.
            repetida = (pessoa["nome"], pessoa["documento_numero"], papel)
            if repetida in pessoas_do_registro.get(registro_id, set()):
                contar("partes das averbações que já eram parte do registro "
                       "(não repetidas)")
                return False
        con.execute(
            """INSERT INTO ra_partes(registro_id, ato_id, nome,
                   documento_tipo, documento_numero, papel, origem,
                   origem_chave)
               VALUES (?,?,?,?,?,?,?,?)""",
            (registro_id, ato_id, pessoa["nome"], pessoa["documento_tipo"],
             pessoa["documento_numero"], papel, "EOFICIO", chave))
        partes_ja.add(chave)
        pessoas_do_registro.setdefault(registro_id, set()).add(
            (pessoa["nome"], pessoa["documento_numero"], papel))
        return True

    # 2. AS PARTES DO REGISTRO.
    if _tem_tabela(acervo, "LivroAuxiliarPartes"):
        for r in acervo.execute(
                "SELECT * FROM LivroAuxiliarPartes "
                "ORDER BY CAST(LivroAuxiliarId AS INTEGER), CAST(Id AS INTEGER)"):
            registro_id = por_chave.get(f"LivroAuxiliar:{r['LivroAuxiliarId']}")
            if registro_id is None:
                contar("partes de registro que não está no Livro 3 do sistema")
                continue
            if gravar_parte(registro_id, None, f"LivroAuxiliarPartes:{r['Id']}",
                            r["ParteId"], r["QualificacaoId"]):
                contar("partes do registro")
    else:
        contar("acervo sem `LivroAuxiliarPartes`: as partes não entraram")

    # 3. AS AVERBACOES — cada uma e um ato, com o numero que o acervo ja deu.
    #
    # O NUMERO DO ATO VEM DO ACERVO (`Averbacao`), e nao do `MAX+1` daqui: a
    # averbacao diz o proprio numero no texto («AV-01/1.315»), e renumerar
    # faria o sistema discordar do papel. As cinco do acervo sao AV-1.
    ids_das_averbacoes: dict[int, int] = {}      # av_id -> ato_id aqui
    registro_da_averbacao: dict[int, int] = {}   # av_id -> registro_id aqui
    tem_averbacao = _tem_tabela(acervo, "LivroAuxiliarAverbacao")
    if tem_averbacao:
        for r in acervo.execute(
                "SELECT * FROM LivroAuxiliarAverbacao "
                "ORDER BY CAST(LivroAuxiliarId AS INTEGER), CAST(Averbacao AS INTEGER)"):
            registro_id = por_chave.get(f"LivroAuxiliar:{r['LivroAuxiliarId']}")
            if registro_id is None:
                contar("averbações de registro que não está no Livro 3 do sistema")
                continue
            registro_da_averbacao[int(r["Id"])] = registro_id
            chave = f"LivroAuxiliarAverbacao:{r['Id']}"
            if chave in atos_ja:
                contar("averbações que já estavam")
                ids_das_averbacoes[int(r["Id"])] = atos_ja[chave]
                continue
            numero = _inteiro(r["Averbacao"]) or 1
            cur = con.execute(
                """INSERT OR IGNORE INTO ra_atos(registro_id, tipo, numero,
                       data_ato, teor, origem, origem_chave, criado_em)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (registro_id, "AV", numero, _data(r["Data"]) or agora,
                 _txt(r["Teor"]), "EOFICIO", chave, agora))
            if cur.rowcount:
                contar("averbações")
                atos_ja[chave] = int(cur.lastrowid)
                ids_das_averbacoes[int(r["Id"])] = int(cur.lastrowid)
            else:
                # O `UNIQUE(registro_id, tipo, numero)` barrou: ja ha um AV-N
                # nesta ficha por outro caminho. O ato do balcao fica como
                # esta — ato lavrado nao se renumera —, e a averbacao do
                # acervo nao entra, com o motivo contado.
                contar("averbações que não entraram: o número do ato já estava "
                       "ocupado nesta ficha")
                linha = con.execute(
                    "SELECT id FROM ra_atos WHERE registro_id=? AND tipo='AV' "
                    "AND numero=?", (registro_id, numero)).fetchone()
                if linha is not None:
                    ids_das_averbacoes[int(r["Id"])] = int(linha["id"])
    else:
        contar("acervo sem `LivroAuxiliarAverbacao`: as averbações não entraram")

    # 4. AS PARTES DAS AVERBACOES — ligadas ao ato delas, e sem repetir o que
    # o registro ja mostra.
    if tem_averbacao and _tem_tabela(acervo, "LivroAuxiliarAverbacaoPartes"):
        for r in acervo.execute(
                "SELECT * FROM LivroAuxiliarAverbacaoPartes "
                "ORDER BY CAST(LivroAuxiliarAverbacaoId AS INTEGER), "
                "CAST(Id AS INTEGER)"):
            av_id = int(r["LivroAuxiliarAverbacaoId"])
            registro_id = registro_da_averbacao.get(av_id)
            if registro_id is None:
                contar("partes de averbação que não está no Livro 3 do sistema")
                continue
            if gravar_parte(registro_id, ids_das_averbacoes.get(av_id),
                            f"LivroAuxiliarAverbacaoPartes:{r['Id']}",
                            r["ParteId"], r["QualificacaoId"],
                            ja_no_registro=True):
                contar("partes das averbações")
    return numeros


def previa_registro_auxiliar(con: sqlite3.Connection,
                             acervo: sqlite3.Connection, *,
                             amostras: int = 5) -> dict:
    """Conta o que a carga do Livro 3 faria, SEM gravar. Só LÊ.

    Existe pelo mesmo motivo da `previa_rcpn`, e com a mesma forma: a tela do
    balcão mostra, ANTES de escrever, quantos registros entram, quantas
    averbações e quantas partes — e amostras do que já está e do que ainda
    falta. Não tem um único INSERT.

    Já importado = mesma `origem_chave` com `origem='EOFICIO'`, em
    `ra_registros`, `ra_atos` e `ra_partes`. São as mesmas chaves que o
    `INSERT OR IGNORE` usa para não duplicar.

    As PARTES contadas aqui são as do registro; as das averbações que já são
    parte dele não entram na conta de propósito, porque a carga também não as
    grava — quem quiser o número exato o vê ao rodar.

    E VEM SEPARADO O QUE NUNCA VAI ENTRAR: `partes_sem_pessoa` conta as que o
    `tbOrtoga` não resolve. Sem esse número, uma parte sem pessoa faria a tela
    dizer «1 parte nova» PARA SEMPRE — e aviso que soa sempre é aviso que
    ninguém ouve.

    POR ISSO `partes_novas` NÃO É O NÚMERO DO BOTÃO, e `faltam` é. Aquele conta
    todas as linhas que ainda não estão aqui, inclusive as que não entram hoje
    nem nunca; somá-las faria a tela pedir «faltam 1» para sempre. `partes_que_
    entram` é o que sobra depois de tirar as sem pessoa, e `faltam` é a soma que
    o botão mostra — o número que o clique realmente alcança.
    """
    ja_no_cartorio = int(con.execute(
        "SELECT COUNT(*) FROM ra_registros WHERE origem='EOFICIO' "
        "AND origem_chave LIKE 'LivroAuxiliar:%'").fetchone()[0])
    existentes = {_txt(r["origem_chave"]) for r in con.execute(
        "SELECT origem_chave FROM ra_registros "
        "WHERE origem='EOFICIO' AND origem_chave IS NOT NULL")}

    total_no_acervo = total_novos = total_ja = 0
    amostras_novos: list[dict] = []
    amostras_ja: list[dict] = []
    if _tem_tabela(acervo, "LivroAuxiliar"):
        for r in acervo.execute(
                "SELECT Id, Registro, Titulo, Numero, Data FROM LivroAuxiliar "
                "ORDER BY CAST(Registro AS INTEGER)"):
            total_no_acervo += 1
            chave = f"LivroAuxiliar:{r['Id']}"
            amostra = {
                "origem_chave": chave,
                "numero": _inteiro(r["Registro"]),
                "titulo": _txt(r["Titulo"]),
                "numero_do_titulo": _txt(r["Numero"]),
                "data": _data(r["Data"]),
            }
            if chave in existentes:
                total_ja += 1
                if len(amostras_ja) < amostras:
                    amostras_ja.append(amostra)
            else:
                total_novos += 1
                if len(amostras_novos) < amostras:
                    amostras_novos.append(amostra)

    atos_ja = {_txt(r["origem_chave"]) for r in con.execute(
        "SELECT origem_chave FROM ra_atos "
        "WHERE origem='EOFICIO' AND origem_chave IS NOT NULL")}
    averbacoes = averbacoes_novas = 0
    if _tem_tabela(acervo, "LivroAuxiliarAverbacao"):
        for r in acervo.execute("SELECT Id FROM LivroAuxiliarAverbacao"):
            averbacoes += 1
            if f"LivroAuxiliarAverbacao:{r['Id']}" not in atos_ja:
                averbacoes_novas += 1

    partes_ja = {_txt(r["origem_chave"]) for r in con.execute(
        "SELECT origem_chave FROM ra_partes "
        "WHERE origem='EOFICIO' AND origem_chave IS NOT NULL")}
    partes = partes_novas = partes_sem_pessoa = 0
    tem_ortoga = _tem_tabela(acervo, "tbOrtoga")
    if _tem_tabela(acervo, "LivroAuxiliarPartes"):
        for r in acervo.execute(
                "SELECT Id, ParteId FROM LivroAuxiliarPartes"):
            partes += 1
            if f"LivroAuxiliarPartes:{r['Id']}" not in partes_ja:
                partes_novas += 1
        if tem_ortoga:
            partes_sem_pessoa = int(acervo.execute(
                """SELECT COUNT(*) FROM LivroAuxiliarPartes p
                    WHERE NOT EXISTS (SELECT 1 FROM tbOrtoga o
                                       WHERE CAST(o.intCodigo AS INTEGER)
                                           = CAST(p.ParteId AS INTEGER))"""
            ).fetchone()[0])
        else:
            # SEM O `tbOrtoga` NÃO HÁ DE ONDE TIRAR NOME, e a carga não grava
            # parte nenhuma (há teste que a manda recusar). Contar «0 sem
            # pessoa» aqui faria a tela prometer seis partes que não entram.
            partes_sem_pessoa = partes_novas

    # O NÚMERO QUE O BOTÃO MOSTRA. Ele conta o que a carga ALCANÇA: registro,
    # averbação e parte que tem pessoa para nomear.
    partes_que_entram = max(0, partes_novas - partes_sem_pessoa)

    return {
        "total_no_acervo": total_no_acervo,
        "total_novos": total_novos,
        "total_ja": total_ja,
        "ja_no_cartorio": ja_no_cartorio,
        "averbacoes_no_acervo": averbacoes,
        "averbacoes_novas": averbacoes_novas,
        "partes_no_acervo": partes,
        "partes_novas": partes_novas,
        "partes_que_entram": partes_que_entram,
        "partes_sem_pessoa": partes_sem_pessoa,
        "faltam": total_novos + averbacoes_novas + partes_que_entram,
        "tem_ortoga": tem_ortoga,
        "amostras_novos": amostras_novos,
        "amostras_ja": amostras_ja,
        "origem": "EOFICIO",
    }


# ------------------------------------------------------------- tudo junto


# ------------------------------------- as folhas de seguranca do RCPN


def carregar_papel(con: sqlite3.Connection, acervo: sqlite3.Connection, *,
                   agora: str) -> Carga:
    """Traz o estoque de folhas de seguranca do E-Oficio. ESCREVE.

    POR QUE ELA EXISTE
        O modulo do papel nasceu em 27/08/2026 com o estoque VAZIO, e a casa
        tem 349 folhas em branco na gaveta. Sem esta carga, o oficial teria de
        digitar cinco faixas a mao — e, pior, o sistema nao saberia quais das
        510 ja foram gastas, e ofereceria como proxima uma folha que ja esta
        numa certidao no mundo.

    O QUE ELA TRAZ, MEDIDO EM 27/08/2026
        510 folhas em 5 remessas e 3 series (HA 371, BA 136, GB 3), das quais
        **161 usadas e 349 em branco**.

    A FOLHA USADA ENTRA USADA, e sem ato amarrado: o E-Oficio guardava o
    protocolo geral (`strProtocoloGeral`), e nao a chave do ato. Amarrar por
    aproximacao seria dizer que a folha esta num ato que talvez nao seja o
    dela. Entra como usada, com o protocolo anotado — que e a verdade que o
    acervo tem.
    """
    carga = Carga("papel")
    if not _tem_tabela(acervo, "tbPapelMoedaRCPN"):
        raise CargaError("O acervo não tem `tbPapelMoedaRCPN`.")

    # A REMESSA DO ACERVO VIRA UMA REMESSA AQUI, e as folhas dela penduram
    # nela. Sem isso a folha nao teria de onde ter vindo.
    remessas: dict[Any, int] = {}
    for linha in acervo.execute(
            """SELECT intCodigoRemessa r, strSerie s, COUNT(*) n,
                      MIN(CAST(strCodigo AS INTEGER)) de,
                      MAX(CAST(strCodigo AS INTEGER)) ate
                 FROM tbPapelMoedaRCPN GROUP BY 1, 2"""):
        cur = con.execute(
            """INSERT INTO pp_remessas(fornecedor, serie, tipo, codigo_de,
                   codigo_ate, quantas, observacao, recebida_em, recebida_por)
               VALUES ('ARPENBRASIL',?,?,?,?,?,?,?,'CARGA')""",
            (linha["s"], "Papel de Segurança - ARPEN", str(linha["de"]),
             str(linha["ate"]), int(linha["n"]),
             f"Remessa {linha['r']} do E-Ofício, trazida pela carga.", agora))
        remessas[(linha["r"], linha["s"])] = int(cur.lastrowid)

    for r in acervo.execute("SELECT * FROM tbPapelMoedaRCPN ORDER BY intChave"):
        carga.lidos += 1
        codigo = _txt(r["strCodigo"])
        if not codigo:
            carga.rejeitar(r["intChave"], "folha sem número no acervo", dict(r))
            continue
        if con.execute("SELECT 1 FROM pp_folhas WHERE codigo=?",
                       (codigo,)).fetchone():
            carga.repetidos += 1
            continue
        usada = bool(r["bitUtilizado"])
        con.execute(
            """INSERT INTO pp_folhas(codigo, serie, remessa_id, situacao,
                   tabela, ato_id, usada_em, usada_por, criada_em)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (codigo, _txt(r["strSerie"]) or None,
             remessas.get((r["intCodigoRemessa"], r["strSerie"])) or
             next(iter(remessas.values()), None),
             "USADA" if usada else "EM BRANCO",
             # SEM ATO AMARRADO: o acervo guarda o protocolo geral, e nao a
             # chave do ato. Amarrar por aproximacao seria dizer que a folha
             # esta num ato que talvez nao seja o dela.
             None, None, agora if usada else None,
             _txt(r["strProtocoloGeral"]) or None if usada else None, agora))
        carga.inseridos += 1
        carga.contar("usadas" if usada else "em_branco")
    return carga


# ------------------------------------------- o razao dos selos


def carregar_selos(con: sqlite3.Connection, acervo: sqlite3.Connection, *,
                   agora: str) -> Carga:
    """Traz os 26.130 selos do E-Oficio para o razao `sd_selos`. ESCREVE.

    POR QUE ELA EXISTE, E POR QUE ELA FALTAVA
        O inventario do acervo (27/08/2026) achou o unico buraco de verdade da
        migracao: a carga do Protesto grava o numero do selo DENTRO do ato
        (`pt_atos.selo`), o que esta certo — mas o RAZAO, que e a tabela que
        responde «este selo ja foi usado, e em que?», comecava VAZIO.

        Com o razao vazio, `registrar_selo_obtido_a_mao` nao tinha contra o que
        comparar: um selo de 2023 podia ser digitado hoje como novo, e nada
        recusava. A trava existia e nao tinha memoria.

    O QUE ELA AMARRA, E O QUE ELA NAO AMARRA
        Onde o numero do selo do acervo bate com o `selo` de um ato ja
        carregado, os dois se amarram — e a amarracao e EXATA, porque o numero
        do selo e unico (conferido: zero repetidos nos 26.130).

        Onde nao bate, o selo entra sem ato. Nao e falta: sao os selos de
        atribuicoes cujo acervo ainda nao foi carregado, e os 1.304 orfaos que
        o E-Oficio deixou — que continuam orfaos, e e assim que eles aparecem
        na tela de «selo obtido e nao usado».

    A ATRIBUICAO VEM DO CAMINHO, e nao de uma traducao minha: `/selo/civil/...`
    entra como CIVIL, que e a palavra do selador. Traduzi-la para «RCPN» aqui
    faria o razao historico falar uma lingua e o razao novo, outra.
    """
    carga = Carga("selos")
    if not _tem_tabela(acervo, "tbSeloIndividual"):
        raise CargaError("O acervo não tem `tbSeloIndividual`.")

    for r in acervo.execute(
            """SELECT * FROM tbSeloIndividual
                WHERE strSelo IS NOT NULL AND TRIM(strSelo) <> ''
                ORDER BY intChave"""):
        carga.lidos += 1
        numero = _txt(r["strSelo"])
        if con.execute("SELECT 1 FROM sd_selos WHERE numero=?",
                       (numero,)).fetchone():
            carga.repetidos += 1
            continue
        # `_txt` DEVOLVE None PARA VAZIO, e nem todo selo do acervo tem
        # caminho: os mais antigos foram gravados antes de o E-Oficio guardar
        # o `strURLAto`. Selo sem caminho entra do mesmo jeito — o que importa
        # dele e o numero.
        caminho = _txt(r["strURLAto"]) or ""
        # `/selo/civil/nascimento` -> CIVIL. A palavra e do selador.
        partes = [x for x in caminho.split("/") if x]
        atribuicao = partes[1].upper() if len(partes) > 1 else None
        cancelado = bool(r["bitSeloCancelado"])
        usado = bool(r["bitUtilizado"])
        con.execute(
            """INSERT INTO sd_selos(numero, texto, caminho, atribuicao,
                   referencia, data_geracao, obtido_em, obtido_por, usado_em,
                   cancelado_em, motivo_cancelamento, qr_token, ambiente)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,'PRODUCAO')""",
            (numero, _txt(r["strTextoSelo"]) or None, caminho or None,
             atribuicao, f"tbSeloIndividual:{r['intChave']}",
             _txt(r["dtmdata_selo"]) or None, _txt(r["dtmData"]) or agora,
             _txt(r["strUserid_Selou"]) or None,
             _txt(r["dtmData"]) if usado else None,
             _txt(r["dtmData"]) if cancelado else None,
             "cancelado no E-Ofício" if cancelado else None,
             # O TOKEN DO QR — 25.642 dos 26.130 selos o tem. Ele nao e URL e
             # nao e o numero do selo: e o que o portal do TJMA resolve.
             #
             # LIDO COM `.get`, e nao pelo indice: acervo de outra versao do
             # E-Oficio pode nao ter a coluna, e pedir coluna que nao existe
             # **estoura** e derruba a carga inteira.
             _txt(dict(r).get("strvalorQRCode")) or None))
        carga.inseridos += 1
        if _txt(dict(r).get("strvalorQRCode")):
            carga.contar("com_token_de_qr")
        if cancelado:
            carga.contar("cancelados")
        if not usado:
            carga.contar("obtidos_e_nao_usados")

    # A AMARRACAO AO ATO, por tabela — e nao selo a selo. Vinte e seis mil
    # consultas seriam vinte e seis mil viagens ao banco; oito comandos fazem
    # o mesmo, e o numero do selo e unico.
    # A COLUNA DO SELO NAO SE CHAMA `selo` EM TODA TABELA — conserto de
    # 16/09/2026, por ordem do oficial, e o defeito era CALADO.
    #
    #   Esta consulta procurava `a.selo` escrito a mao. Medido em 16/09,
    #   `PRAGMA table_info` das dezesseis tabelas de ato: **quatro nao tem
    #   essa coluna** —
    #
    #     | tabela            | a coluna e |
    #     |-------------------|------------|
    #     | `nt_cartoes`      | `selo_abertura` |
    #     | `ri_atos`         | `selo_texto` |
    #     | `ri_certidoes`    | `selo_texto` |
    #     | `ri_protocolos`   | `selo_prenotacao` |
    #
    #   Para essas quatro o `UPDATE` estourava com `no such column: selo`, o
    #   `except sqlite3.Error` logo abaixo engolia, e **a amarracao nunca
    #   acontecia**. O efeito medido no razao: **9.141 selos com `tabela`
    #   nula** — entre eles os 2.108 do Registro de Imoveis, que e a
    #   atribuicao inteira.
    #
    #   `ato_selado.COLUNA_DO_SELO` existe exatamente para isto, e ja era
    #   consultada pelo outro lado do ciclo (`vincular_ao_ato`, desde 27/08).
    #   E a MESMA familia do defeito de `registrar_selo_obtido_a_mao`,
    #   consertado em 15/09: `UPDATE {tabela} SET selo=?` com a coluna
    #   escrita a mao.
    #
    #   E O `except` CONTINUA, porque a razao dele e outra: instalacao que
    #   ainda nao tem a tabela. O que ele nao pode e esconder coluna errada.
    for tabela in sorted(ato_selado.TABELAS_DE_ATO):
        coluna = ato_selado.COLUNA_DO_SELO.get(tabela, "selo")
        try:
            cur = con.execute(
                f"""UPDATE sd_selos
                       SET tabela=?,
                           ato_id=(SELECT a.id FROM {tabela} a
                                    WHERE a.{coluna} = sd_selos.numero),
                           usado_em=COALESCE(usado_em, ?)
                     WHERE ato_id IS NULL
                       AND EXISTS (SELECT 1 FROM {tabela} a
                                    WHERE a.{coluna} = sd_selos.numero)""",
                (tabela, agora))
        except sqlite3.Error:
            continue      # tabela de ato que este banco ainda nao tem
        if cur.rowcount:
            carga.contar(f"amarrados_a_{tabela}", cur.rowcount)
    return carga


def carregar_ibge(con: sqlite3.Connection, acervo: sqlite3.Connection, *,
                  agora: str) -> Carga:
    """Traz o de-para de municipio do IBGE e o cabecalho desta serventia. ESCREVE.

    POR QUE ELA EXISTE
        `ibge_remessa.py` sabe o layout do arquivo, e o layout pede CODIGO de
        municipio e de UF — `21` e `98765` — enquanto o sistema guarda NOME de
        cidade em texto. Sem o de-para, cada municipio teria de ser digitado em
        codigo pelo escrevente, e codigo digitado a mao numa remessa
        estatistica e erro que ninguem confere: ninguem le o arquivo depois.

    QUAL DAS DUAS TABELAS DO ACERVO, E POR QUE (medido em 28/08/2026)
        `tbMunicipio` tem 5.638 linhas e **5.570 codigos distintos** — que e
        exatamente o numero de municipios do Brasil. `MUNICIPIOS` tem 5.444:
        faltam 126. Fica a primeira.

        As 68 linhas SEM codigo entram assim mesmo. Elas ainda casam pelo nome,
        e achar o nome sem o codigo e melhor que nao achar nada — quem monta a
        remessa ve o municipio e sabe o que falta. Sao restos de municipio
        renomeado ou desmembrado.

    O CABECALHO SAI DE `tbIBGE_Propriedades`, e nao se adivinha: e o que esta
    casa mandava de verdade — UF `21`, municipio `98765`, distrito `05`,
    cartorio `01`. Ele vira CONFIGURACAO (`settings`), como o CNS: e resposta
    sobre quem a casa e, e nao dado de movimento.

    NAO SE APAGA O QUE JA FOI RESPONDIDO. Se o oficial ja informou o codigo do
    cartorio na tela, a carga nao o sobrescreve com o do acervo: o que a pessoa
    respondeu vale mais que o que o programa antigo guardava.
    """
    carga = Carga("ibge")
    if not _tem_tabela(acervo, "tbMunicipio"):
        raise CargaError("O acervo não tem `tbMunicipio`.")

    for linha in acervo.execute(
            """SELECT strEstado uf, intEstadoIBGE cod_uf,
                      strMunicipio nome, intMunicipioIBGE cod
                 FROM tbMunicipio"""):
        carga.lidos += 1
        nome = (linha["nome"] or "").strip()
        uf = (linha["uf"] or "").strip().upper()
        if not nome or not uf:
            carga.rejeitar(linha["cod"], "linha sem nome ou sem UF")
            continue
        if not linha["cod"]:
            # SEM CODIGO ELA NAO ENTRA, e por isso e REJEICAO e nao contagem:
            # `lidos = inseridos + rejeitados` e a conta que faz o numero da
            # tela nao mentir, e ela ja cobrou o preco uma vez neste projeto —
            # a carga que informava «11 rejeitados» numa rodada em que 7
            # tinham entrado.
            carga.rejeitar(nome, "município sem código do IBGE no acervo",
                           {"uf": uf, "nome": nome})
            continue
        codigo = int(linha["cod"])
        cod_uf = int(linha["cod_uf"] or (codigo // 100000))
        # OR REPLACE, E NAO OR IGNORE: o IBGE renomeia municipio, e rodar a
        # carga de novo tem de trazer o nome novo. Mas quem ja estava conta
        # como REPETIDO, e nao como inserido — senao a segunda rodada diria
        # que trouxe 5.570 municipios que ja estavam la, e o numero da tela
        # deixaria de significar «o que entrou agora».
        ja = con.execute("SELECT 1 FROM ib_municipios WHERE codigo_ibge=?",
                         (codigo,)).fetchone()
        con.execute(
            """INSERT OR REPLACE INTO ib_municipios
                   (codigo_ibge, codigo_uf, codigo_mun, uf, nome, nome_norm,
                    origem, criado_em)
               VALUES (?,?,?,?,?,?,'ACERVO',?)""",
            (codigo, cod_uf, f"{codigo % 100000:05d}", uf, nome,
             IB.normalizar_nome(nome), agora))
        if ja:
            carga.repetidos += 1
        else:
            carga.inseridos += 1

    # ------------------------------------------------ o cabecalho da casa
    if _tem_tabela(acervo, "tbIBGE_Propriedades"):
        p = acervo.execute(
            "SELECT strUF, strMunicipio, strDistrito, strCodigo "
            "FROM tbIBGE_Propriedades LIMIT 1").fetchone()
        if p:
            for chave, valor in (("ibge_uf", p["strUF"]),
                                 ("ibge_municipio", p["strMunicipio"]),
                                 ("ibge_distrito", p["strDistrito"]),
                                 ("ibge_cartorio", p["strCodigo"])):
                valor = (valor or "").strip()
                if not valor:
                    continue
                ja = con.execute(
                    "SELECT value FROM settings WHERE key=?", (chave,)).fetchone()
                if ja and (ja["value"] or "").strip():
                    carga.contar("cabecalho_ja_respondido")
                    continue
                con.execute(
                    "INSERT OR REPLACE INTO settings(key, value) VALUES (?,?)",
                    (chave, valor))
                carga.contar("cabecalho_do_acervo")
    else:
        carga.contar("acervo_sem_tbIBGE_Propriedades")
    return carga



def instalar_acervo_de_pasta(pasta: str | Path, destino: str | Path) -> dict:
    """Monta ou refaz o `acervo_eoficio.sqlite3` a partir da pasta JSONL.

    É o mesmo caminho de `acervo_eoficio.carregar`: a tela do RCPN só
    empacota pasta/zip/sqlite e chama isto. Não interpreta registro civil —
    só deixa o acervo no disco para a prévia e a carga.
    """
    import acervo_eoficio as AE
    pasta = Path(pasta)
    destino = Path(destino)
    if destino.is_dir():
        destino = destino / AE.NOME_BANCO
    return AE.carregar(pasta, destino)


def instalar_acervo_de_sqlite(origem: str | Path, destino: str | Path) -> dict:
    """Copia um `acervo_eoficio.sqlite3` pronto para a pasta de dados.

    Conferência mínima: o arquivo abre e tem ao menos uma tabela das fontes
    do RCPN (ou qualquer tabela). Não roda carga de atribuição.
    """
    import shutil
    import acervo_eoficio as AE
    origem = Path(origem)
    destino = Path(destino)
    if destino.is_dir():
        destino = destino / AE.NOME_BANCO
    if not origem.is_file():
        raise CargaError(f"Não achei o arquivo do acervo em {origem}.")
    # Conferir que abre como SQLite antes de substituir o da casa.
    try:
        probe = sqlite3.connect(f"file:{origem}?mode=ro", uri=True)
        probe.row_factory = sqlite3.Row
        n = probe.execute(
            "SELECT COUNT(*) AS n FROM sqlite_master WHERE type='table'"
        ).fetchone()["n"]
        probe.close()
    except sqlite3.Error as erro:
        raise CargaError(
            f"O arquivo não parece um acervo SQLite válido: {erro}") from erro
    if n < 1:
        raise CargaError("O arquivo SQLite não tem tabelas.")
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(destino.suffix + ".parcial")
    if tmp.exists():
        tmp.unlink()
    shutil.copy2(origem, tmp)
    if destino.exists():
        destino.unlink()
    tmp.rename(destino)
    return {
        "arquivo": str(destino),
        "tabelas": n,
        "linhas": None,
        "origem_sqlite": str(origem),
        "divergentes": [],
    }


def instalar_acervo_de_zip(arquivo_zip: str | Path, destino: str | Path,
                           pasta_trabalho: str | Path) -> dict:
    """Extrai o ZIP da exportação E-Ofício e monta o acervo.

    O ZIP deve trazer os `.jsonl` da exportação (com ou sem pasta-raiz).
    Depois chama `instalar_acervo_de_pasta`.
    """
    import zipfile
    import shutil
    arquivo_zip = Path(arquivo_zip)
    pasta_trabalho = Path(pasta_trabalho)
    pasta_trabalho.mkdir(parents=True, exist_ok=True)
    if not arquivo_zip.is_file():
        raise CargaError(f"Não achei o ZIP em {arquivo_zip}.")
    extraindo = pasta_trabalho / "export_eoficio_upload"
    if extraindo.exists():
        shutil.rmtree(extraindo)
    extraindo.mkdir(parents=True)
    try:
        with zipfile.ZipFile(arquivo_zip, "r") as zf:
            zf.extractall(extraindo)
    except zipfile.BadZipFile as erro:
        raise CargaError(
            f"O arquivo não é um ZIP válido: {erro}") from erro
    # Achar a pasta que tem os jsonl (pode ter um único diretório-raiz).
    candidatos = [extraindo]
    candidatos.extend(p for p in extraindo.rglob("*") if p.is_dir())
    pasta_jsonl = None
    for cand in candidatos:
        jsonls = [p for p in cand.glob("*.jsonl")
                  if p.name not in {"ESQUEMA.jsonl", "MANIFESTO.jsonl"}]
        if jsonls:
            pasta_jsonl = cand
            break
    if pasta_jsonl is None:
        # Talvez o ZIP traga o sqlite pronto.
        sqlites = list(extraindo.rglob("*.sqlite3")) + list(
            extraindo.rglob("*.db"))
        if sqlites:
            return instalar_acervo_de_sqlite(sqlites[0], destino)
        raise CargaError(
            "No ZIP não achei nem os .jsonl da exportação do E-Ofício "
            "nem um acervo .sqlite3.")
    return instalar_acervo_de_pasta(pasta_jsonl, destino)


CARGAS: dict[str, Callable] = {
    "protesto": carregar_protesto,
    "rcpn": carregar_rcpn,
    "rcpj_rtd": carregar_rcpj_rtd,
    "registro_auxiliar": carregar_registro_auxiliar,
    # O PAPEL VEM DEPOIS DO RCPN: e a folha em que a certidao dele e impressa.
    "papel": carregar_papel,
    # O IBGE NAO SE AMARRA A NADA: e cadastro oficial de municipio mais o
    # cabecalho da casa. Podia rodar em qualquer lugar da fila — e por isso
    # entra ANTES dos selos, e nao depois: quem tanto faz cede o lugar a quem
    # a ordem importa. Ha teste que exige `selos` no fim.
    "ibge": carregar_ibge,
    # OS SELOS VEM POR ULTIMO, e e de proposito: eles se amarram aos atos que
    # as cargas anteriores acabaram de trazer.
    "selos": carregar_selos,
}


# O NOME DE CADA CARGA NO BALCAO, E ESTA E A LISTA DE QUE A TELA SAI.
#
# O DEFEITO QUE ISTO CONSERTA, relatado pelo escrevente em 27/08/2026 as 16h16:
# «nao encontrou livro3 no e-oficio para importar».
#
#     A tela da carga montava as caixinhas a partir de `atribuicoes_web.PAINEIS`
#     — que e a lista das TELAS —, e ali o Livro 3 se chama `livro3`. Aqui a
#     carga dele se chama `registro_auxiliar`. Duas listas que precisavam
#     concordar, e que divergiram caladas.
#
#     O estrago passou do nome: `carregar_tudo` recusa carga desconhecida, e a
#     recusa derruba a TRANSACAO INTEIRA. Marcar tudo e mandar nao trazia nada.
#     E as duas cargas novas da 3.6.17 — `papel` e `selos` — nao tinham
#     caixinha nenhuma, porque nao ha painel de tela para elas: ficaram em ZERO
#     no servidor sem ninguem ver.
#
# A LISTA MORA JUNTO DA CARGA, e nao na tela. E a licao do menu outra vez: lista
# escrita a mao noutro arquivo envelhece na tarde em que se escreve.
TITULO_DA_CARGA: dict[str, str] = {
    "protesto": "Protesto — títulos, devedores e atos",
    "rcpn": "Registro Civil — assentos, pessoas e atos",
    "rcpj_rtd": "RCPJ e RTD — registros e atos",
    "registro_auxiliar": "Livro 3 — Registro Auxiliar do RI",
    "papel": "Folhas de segurança do RCPN — o estoque",
    "ibge": "IBGE — os 5.570 municípios e o cabeçalho desta serventia",
    "selos": "Selos emitidos — o razão dos 26.130",
}


# ------------------------------------------- semear o contador do nucleo
#
# O DEFEITO QUE O ENSAIO DE 25/08/2026 ACHOU, E QUE E O DE 18/08 OUTRA VEZ
#     A carga NAO chama o nucleo, de proposito: o ato do acervo ja tem livro,
#     folha e numero do livro fisico. Estava certo — e incompleto. O CONTADOR
#     do nucleo (`nu_numeracao`) ficava vazio, porque `escrituracao._semente()`
#     o le de `nu_lugares`, e a carga escreve em `pt_atos`.
#
#     Resultado, medido contra copia do banco de producao: a casa tem
#     apontamentos ate a ordem 2.156, e o primeiro protesto lavrado no sistema
#     novo saiu com o numero 1. E exatamente o 18/08 outra vez — numero de
#     ordem que repete o que a serventia ja usou.
#
#     Semear o contador e a peca que faltava, e o proprio esquema ja a previa:
#     `nu_numeracao.semeado_de` existe para dizer de onde o valor veio.
#
# DE ONDE SAI O MAIOR NUMERO DE CADA SERIE
#     Do que a carga acabou de trazer, e nao de uma tabela de contador do
#     E-Oficio: o que vale e o que ENTROU, porque e sobre ele que o proximo
#     numero tem de passar. Conferido contra o levantamento: RC_A 19.552,
#     RC_C 1.976, PJ_A 372, TD_B 1.508 — os mesmos numeros que
#     `tbPropriedadeRCPN` e `tbTD_Propriedade` declaram.

# Onde procurar o maior numero de cada serie, no banco VIVO, depois da carga.
FONTES_DO_CONTADOR: tuple[tuple[str, str], ...] = (
    ("PT_APONTAMENTO",
     "SELECT MAX(numero_ordem) m FROM pt_atos WHERE tipo='APONTAMENTO'"),
    ("RC_A", "SELECT MAX(numero) m FROM rc_assentos WHERE serie='RC_A'"),
    ("RC_B", "SELECT MAX(numero) m FROM rc_assentos WHERE serie='RC_B'"),
    ("RC_C", "SELECT MAX(numero) m FROM rc_assentos WHERE serie='RC_C'"),
    ("RC_E", "SELECT MAX(numero) m FROM rc_assentos WHERE serie='RC_E'"),
    ("PJ_A", "SELECT MAX(numero) m FROM rg_registros WHERE serie='PJ_A'"),
    ("PJ_B", "SELECT MAX(numero) m FROM rg_registros WHERE serie='PJ_B'"),
    ("TD_B", "SELECT MAX(numero) m FROM rg_registros WHERE serie='TD_B'"),
    ("TD_C", "SELECT MAX(numero) m FROM rg_registros WHERE serie='TD_C'"),
    ("TD_F", "SELECT MAX(numero) m FROM rg_registros WHERE serie='TD_F'"),
)

# As series em que o acervo NAO guarda o numero de ordem, e por isso o contador
# nao se semeia: `tbAvisoProtesto` tem `intProtestoLivro` (4 a 9) e
# `intProtestoFolha` (1 a 200), e NENHUMA coluna com o numero do protesto.
#
# Nao invento: fica dito que nao se semeou, e o oficial informa o proximo
# numero pela tela de numeracao (`escrituracao.fixar_numeracao`). Deixar em 1
# em silencio seria o defeito de 18/08 de novo.
SEM_CONTADOR_NO_ACERVO: dict[str, str] = {
    "PT_PROTESTO":
        "o acervo guarda livro (4 a 9) e folha (1 a 200) do protesto, mas "
        "nenhuma coluna com o número de ordem dele. Informe o próximo número "
        "antes de lavrar o primeiro protesto.",
    "PT_PAGAMENTO":
        "o Livro de Registro de Pagamentos do acervo tem uma linha só, sem "
        "faixa de ordem aproveitável. Informe o próximo número antes de "
        "lavrar o primeiro pagamento.",
    "PT_PROTOCOLO":
        "numeração diária: reinicia sozinha a cada dia, e não tem contador a "
        "semear.",
    # AS TRES DO RCPN FICAVAM CALADAS ate 26/08/2026, e caladas e pior que
    # pendentes: `rc_assento.SERIE_DA_ESPECIE` manda casamento religioso,
    # natimorto e proclamas para elas, e sem contador o primeiro assento de
    # cada uma nasceria com o numero 1. Ninguem seria avisado.
    #
    # O motivo e medido: o acervo do E-Oficio tem TRES tabelas do civil —
    # `tbRegistroNascimento`, `tbRegistroCasamento` e `tbRegistroObito` — e
    # mais nenhuma. Esses tres livros nunca existiram nele.
    # DUAS DESTAS TRES DEIXARAM DE SER PENDENCIA EM 27/08/2026, e o motivo
    # merece ficar escrito porque e o mesmo erro de metodo pela terceira vez.
    #
    #   Eu havia concluido que o acervo «nao tem tabela de proclamas nem de
    #   natimortos — so nascimento, casamento e obito». A conclusao sobre as
    #   TABELAS estava certa, e a conclusao sobre os NUMEROS estava errada:
    #   `tbPropriedadeRCPN` guarda o contador de cada serie, e la estao
    #   `intRegistroAtualRegistroProclamas = 1358` e
    #   `intObito_Numero_Registro_CAuxiliar = 12`.
    #
    #   E a mesma licao do `codigoAto` e da coluna `intCodigoAto`: **ausencia
    #   de tabela nao prova ausencia de dado**; prova que aquela tabela nao e
    #   onde ele fica. Procurei o registro e nao procurei o contador.
    #
    #   Ficam duas pendencias de verdade, e as duas com a mesma prova: o
    #   `tbPropriedadeRCPN` tem LIVRO para as duas (2 e 2) e NAO tem numero de
    #   registro — o campo nem existe na tabela.
    # ESTAS DUAS O ACERVO COSTUMA RESPONDER, e por isso elas continuam na
    # lista: quem for semeado sai daqui antes de virar pendencia (ver
    # `semear_numeracao`). Tira-las da lista faria o caso em que o acervo NAO
    # responde ficar calado — que e o defeito que esta lista existe para
    # impedir. Pendencia se declara e se apaga quando resolvida; nao se remove
    # da lista porque costuma ser resolvida.
    # SEM JARGAO: quem le estas mensagens e o oficial, na tela de pendencias.
    # O nome da tabela do E-Oficio nao diz nada a ele, e o que ele precisa saber
    # e de onde o numero costuma vir e o que fazer quando nao veio.
    "RC_D":
        "o próximo número de proclamas costuma vir da configuração do "
        "E-Ofício, e desta vez não veio — o acervo pode estar ausente ou ser de "
        "outra versão. Informe o próximo número, que sai do livro físico, antes "
        "do primeiro proclama.",
    "RC_C_AUXILIAR":
        "o próximo número de natimortos costuma vir da configuração do "
        "E-Ofício, e desta vez não veio — o acervo pode estar ausente ou ser de "
        "outra versão. Informe o próximo número, que sai do livro físico, antes "
        "do primeiro natimorto.",
    "RC_B_AUXILIAR":
        "o E-Ofício guarda o livro do casamento religioso (Livro 2) e não "
        "guarda o número do registro — esse campo não existe lá. O próximo "
        "número só sai do livro físico.",
    "RC_E":
        "o E-Ofício guarda o livro e a folha do Livro E (livro 2, folha 39) e "
        "não guarda o número do registro — esse campo não existe lá. O próximo "
        "número só sai do livro físico.",
}


# OS CONTADORES QUE O ACERVO GUARDA FORA DAS TABELAS DE REGISTRO.
#
#   `tbPropriedadeRCPN` e uma linha so, com o estado da numeracao de CADA serie
#   do civil. Para nascimento, casamento e obito ela apenas confirma o que a
#   carga ja apura dos assentos — e os numeros batem: 19.552, 39 e 1.976.
#
#   Para PROCLAMAS e NATIMORTOS ela e a UNICA fonte, porque o acervo nao tem
#   tabela de registro dessas duas. Sem ela, o oficial teria de ir ao livro de
#   papel buscar dois numeros que o E-Oficio ja sabia.
#
#   O valor e o ULTIMO USADO, e nao o proximo: conferido contra o que a carga
#   apura dos assentos — `intRegistroAtualNascimento` = 19.552 = o maior numero
#   de `rc_assentos` da serie RC_A.
CONTADOR_NA_PROPRIEDADE_DO_RCPN: dict[str, str] = {
    "RC_D": "intRegistroAtualRegistroProclamas",
    "RC_C_AUXILIAR": "intObito_Numero_Registro_CAuxiliar",
}

# O CONTADOR DO E-OFICIO PARA AS TRES ESPECIES QUE ELE MESMO NUMERAVA.
#
# Ele NAO entra como fonte de semeadura — entra como **conferencia**: compara-se
# o que a carga trouxe com o que o E-Oficio dizia, e a divergencia vira pergunta
# ao oficial em vez de um `max()` calado.
CONTADOR_DECLARADO_PELO_EOFICIO: dict[str, str] = {
    "RC_A": "intRegistroAtualNascimento",
    "RC_B": "intRegistroAtualCasamento",
    "RC_C": "intRegistroAtualObito",
}

# Medido em 29/08/2026, e e o motivo desta conferencia existir:
#
#   | especie    | a carga semearia | o E-Oficio dizia |
#   |------------|------------------|------------------|
#   | nascimento |           19.552 |           19.552 |  bate
#   | obito      |            1.976 |            1.976 |  bate
#   | CASAMENTO  |            1.011 |               39 |  NAO BATE
#
# E o porque aparece na FOLHA: no nascimento o registro e 19.552 e a folha 166;
# no obito, 1.976 contra 275 — o numero corre pela SERIE e a folha reinicia a
# cada livro. **No casamento registro e folha sao os dois 39**, e os numeros dos
# casamentos do acervo reiniciam a cada livro (o livro 01 vai de 315 a 405; o
# livro 6, de 111 a 659).
#
# Ou seja: no casamento desta casa o numero parece ser POR LIVRO, e nas outras
# duas e por serie. Se for isso, semear pelo maior poria o proximo casamento em
# **1012** onde deveria ser **40** — o defeito de 18/08 outra vez, e do lado
# caro: numero alto demais nao repete nada, mas **pula 972 numeros no livro**, e
# livro com salto e o que a correicao pergunta.
#
# NAO SE DECIDE ISSO MEDINDO. Quem sabe e quem tem o livro de papel na mao.


def _contadores_da_propriedade_do_rcpn(
        acervo: sqlite3.Connection | None) -> dict[str, int]:
    """O ultimo numero de proclamas e de natimortos, do acervo. SO LE.

    Devolve vazio quando nao ha acervo aberto ou quando a tabela nao existe —
    e vazio aqui quer dizer «continua pendencia», que e a verdade.

    NAO ESTOURA: a carga inteira nao pode morrer porque uma tabela de
    propriedade mudou de forma entre versoes do E-Oficio.
    """
    if acervo is None or not _tem_tabela(acervo, "tbPropriedadeRCPN"):
        return {}
    try:
        acervo.row_factory = sqlite3.Row
        linha = acervo.execute("SELECT * FROM tbPropriedadeRCPN").fetchone()
    except sqlite3.Error:
        return {}
    if not linha:
        return {}
    colunas = set(linha.keys())
    achados: dict[str, int] = {}
    for serie, coluna in CONTADOR_NA_PROPRIEDADE_DO_RCPN.items():
        if coluna not in colunas:
            continue
        valor = _inteiro(linha[coluna])
        if valor:
            achados[serie] = valor
    return achados


def _divergencias_do_contador_do_rcpn(
        con: sqlite3.Connection,
        acervo: sqlite3.Connection | None) -> list[dict]:
    """Onde o contador do E-Ofício discorda do que a carga trouxe. SÓ LÊ.

    NAO ESTOURA, pelo mesmo motivo do leitor de contadores: a carga inteira nao
    pode morrer porque uma tabela de propriedade mudou de forma entre versoes.
    """
    if acervo is None or not _tem_tabela(acervo, "tbPropriedadeRCPN"):
        return []
    try:
        acervo.row_factory = sqlite3.Row
        prop = acervo.execute("SELECT * FROM tbPropriedadeRCPN").fetchone()
    except sqlite3.Error:
        return []
    if not prop:
        return []
    colunas = set(prop.keys())

    achadas: list[dict] = []
    for serie, coluna in CONTADOR_DECLARADO_PELO_EOFICIO.items():
        if coluna not in colunas:
            continue
        declarado = _inteiro(prop[coluna])
        if not declarado:
            continue
        linha = con.execute("SELECT * FROM nu_numeracao WHERE serie=?",
                            (serie,)).fetchone()
        if not linha:
            continue
        maior = _inteiro(linha["maior_em_uso"])
        if not maior or maior == declarado:
            continue
        achadas.append({"serie": serie, "do_acervo": maior,
                        "do_eoficio": declarado,
                        "semeado": _inteiro(linha["proximo"])})
    return achadas


def semear_numeracao(con: sqlite3.Connection, *, agora: str,
                     usuario: str | None = None,
                     acervo: sqlite3.Connection | None = None) -> dict:
    """Põe o contador do núcleo à frente do que o acervo já usou. ESCREVE.

    Chamar DEPOIS da carga. NUNCA BAIXA um contador: se alguém já lavrou ato
    novo, o número dele vale mais que o do acervo — baixar faria o próximo ato
    repetir número, que é o defeito que isto existe para impedir.

    Devolve o que semeou e o que **não** semeou, com o motivo — série sem
    contador semeado é série em que o primeiro ato nasceria com número 1, e
    isso tem de estar dito e não descoberto depois.
    """
    semeadas, pendentes = [], []
    fontes = list(FONTES_DO_CONTADOR)
    # O QUE VEM DE `tbPropriedadeRCPN` ENTRA COMO MAIS UMA FONTE, e nao como um
    # caminho a parte: assim ele passa pela MESMA regra de nao baixar contador
    # que o resto. Duas maneiras de semear divergiriam no primeiro conserto.
    do_acervo = _contadores_da_propriedade_do_rcpn(acervo)
    for serie, maior in do_acervo.items():
        fontes.append((serie, f"SELECT {int(maior)} m"))
    for serie, consulta in fontes:
        linha = con.execute(consulta).fetchone()
        maior = _inteiro(linha["m"] if linha else None)
        if not maior:
            continue
        atual = con.execute("SELECT * FROM nu_numeracao WHERE serie=?",
                            (serie,)).fetchone()
        if atual and int(atual["proximo"]) > maior:
            continue                      # já está à frente; não se baixa
        con.execute(
            """INSERT INTO nu_numeracao(serie, proximo, maior_em_uso,
                   semeado_de, fixado_em, fixado_por, observacao)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(serie) DO UPDATE SET
                   proximo=excluded.proximo,
                   maior_em_uso=MAX(COALESCE(maior_em_uso,0), excluded.maior_em_uso),
                   semeado_de=excluded.semeado_de,
                   fixado_em=excluded.fixado_em,
                   observacao=excluded.observacao""",
            (serie, maior + 1, maior, "acervo do E-Ofício", agora, usuario,
             f"semeado da carga do acervo: o maior número em uso é {maior}"))
        semeadas.append({"serie": serie, "maior_em_uso": maior,
                         "proximo": maior + 1})
    # AS PENDENCIAS SE DECLARAM, e nao so se devolvem. Devolver uma lista que
    # aparece na tela da carga e em lugar nenhum depois e o mesmo que nao
    # avisar: quem roda a carga le a lista, e quem informa o numero e o
    # oficial, semanas depois. `implantacao.declarar_numeracao` e repetivel —
    # rodar a carga duas vezes nao reabre o que ja foi resolvido.
    # A DIVERGENCIA ENTRE O QUE A CARGA TROUXE E O QUE O E-OFICIO DIZIA.
    #
    #   Semear pelo maior e a regra certa quando as duas fontes concordam — e
    #   no nascimento e no obito elas concordam **exatamente**. No casamento
    #   nao: a carga traz 1.011 e o E-Oficio diz 39.
    #
    #   Um `max()` calado resolveria o conflito escolhendo um lado sem dizer que
    #   havia conflito. **Zero medido e zero por engano sao a mesma tela e
    #   coisas diferentes** — e aqui vale igual: 1012 escolhido e 1012 imposto
    #   por um `max()` sao o mesmo numero e coisas diferentes.
    #
    #   O contador continua sendo semeado (a casa nao pode ficar sem numero),
    #   **e a divergencia vira pendencia declarada** — com os dois numeros, para
    #   o oficial abrir o livro e dizer qual vale.
    divergencias = _divergencias_do_contador_do_rcpn(con, acervo)
    for d in divergencias:
        IMP.declarar_numeracao(
            con, d["serie"],
            f"o acervo traz atos até o número {d['do_acervo']}, mas o contador "
            f"do próprio E-Ofício diz {d['do_eoficio']}. O sistema semeou pelo "
            f"maior ({d['semeado']}), que é a regra segura contra repetir "
            f"número — mas se o certo for {d['do_eoficio'] + 1}, o livro "
            f"pularia {d['semeado'] - d['do_eoficio'] - 1} números. "
            "Confira no livro de papel qual é o próximo e informe aqui.",
            agora=agora, usuario=usuario)
        pendentes.append({"serie": d["serie"],
                          "motivo": "o contador do E-Ofício e o maior número da "
                                    "carga discordam — ver a pendência"})

    for serie, motivo in SEM_CONTADOR_NO_ACERVO.items():
        # SERIE SEMEADA NAO E PENDENCIA. Se o acervo respondeu, nao se pergunta
        # ao oficial — perguntar o que o sistema ja sabe e o tipo de aviso que
        # faz o proximo ser ignorado.
        if any(x["serie"] == serie for x in semeadas):
            continue
        pendentes.append({"serie": serie, "motivo": motivo})
        IMP.declarar_numeracao(con, serie, motivo, agora=agora,
                               usuario=usuario)
    IMP.declarar_catalogo(con, agora=agora, usuario=usuario)
    return {"semeadas": semeadas, "pendentes": pendentes}


def carregar_tudo(con: sqlite3.Connection, acervo: sqlite3.Connection, *,
                  agora: str, quais: Iterable[str] | None = None) -> dict:
    """Roda as cargas pedidas e devolve o que cada uma fez. ESCREVE.

    Uma carga que estoura nao derruba as outras: o motivo entra no resultado
    com o nome dela. Perder a carga do Protesto porque a do RCPN achou tabela
    faltando seria desperdicar as duas.
    """
    saida: dict[str, Any] = {}
    pedidas = set(quais) if quais is not None else set(CARGAS)
    for nome in pedidas:
        if nome not in CARGAS:
            raise CargaError(
                f"Carga desconhecida: {nome!r}. As que existem são: "
                f"{', '.join(CARGAS)}.")
    # A ORDEM E A DE `CARGAS`, E NAO A ORDEM EM QUE PEDIRAM.
    #
    # Ela nao e arbitraria: o papel vem depois do RCPN, e os selos vem por
    # ultimo porque se amarram aos atos que as outras acabaram de trazer.
    # Obedecer a ordem do formulario deixaria isso na mao do navegador.
    for nome in CARGAS:
        if nome not in pedidas:
            continue
        try:
            saida[nome] = CARGAS[nome](con, acervo, agora=agora).como_dict()
        except CargaError as erro:
            saida[nome] = {"nome": nome, "erro": str(erro)}
    # SEMEAR O CONTADOR É PARTE DA CARGA, e não um passo que alguém lembra.
    #
    # Sem isto o primeiro ato lavrado nasce com o número 1 sobre um acervo que
    # já chegou a 2.156 — foi o que o ensaio contra o banco de produção achou
    # em 25/08/2026, e é o defeito de 18/08 outra vez.
    saida["numeracao"] = semear_numeracao(con, agora=agora, acervo=acervo)
    return saida
