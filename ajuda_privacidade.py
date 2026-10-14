"""Barreira obrigatoria para todo conteudo que sai pela Ajuda.

Este modulo nao fala com a rede. Ele recebe o texto que a Ajuda pretende
enviar, substitui dados pessoais, sensiveis e segredos por marcadores estaveis
e devolve um pacote que o transporte aceita. A separacao e deliberada: uma
caixa escondida na tela nao protege uma chamada feita diretamente no dominio.

Os marcadores sao consistentes dentro da mesma consulta. Se o mesmo nome
aparecer na instrucao e na pergunta, ambos viram ``[PESSOA_01]``. A tabela de
correspondencia existe apenas em memoria durante a sanitizacao e nunca integra
o pacote, o banco ou a chamada externa.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Pattern


# "2" desde 23/09/2026: a pergunta em maiúsculas deixou de virar nome inteira.
# A versão vai gravada em `aj_consultas.sanitizacao_versao`, e é por ela que se
# separa, depois, o que saiu por uma régua e o que saiu pela outra.
VERSAO_DAS_REGRAS = "2"


class PrivacidadeError(ValueError):
    """O conteudo nao pode sair da serventia com seguranca."""


@dataclass(frozen=True)
class PacoteSanitizado:
    """Unica forma aceita pelo transporte da ajuda."""

    instrucao: str
    pergunta: str
    auditavel: str
    sha256: str
    versao: str
    contagens: dict[str, int]

    @property
    def resumo_json(self) -> str:
        return json.dumps(self.contagens, ensure_ascii=False, sort_keys=True)


_CPF = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
_EMAIL = re.compile(
    r"(?<![\w.+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![\w-])",
    re.I,
)
_TELEFONE = re.compile(
    r"(?<!\d)(?:\+?55\s*)?\(?\d{2}\)?\s*(?:9\s*)?\d{4}[-\s]?\d{4}(?!\d)"
)
_IP = re.compile(
    r"(?<!\d)(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}"
    r"(?:25[0-5]|2[0-4]\d|1?\d?\d)(?!\d)"
)
_PROCESSO_CNJ = re.compile(
    r"\b\d{7}-?\d{2}\.?\d{4}\.?\d\.?\d{2}\.?\d{4}\b"
)
_SEGREDO = re.compile(
    r"\b(?:sk-[A-Za-z0-9_-]{8,}|Bearer\s+[A-Za-z0-9._~-]{8,}|"
    r"(?:api[_-]?key|token|senha|password|secret)\s*[:=]\s*"
    r"[^\s,;]{4,})",
    re.I,
)
_CAMINHO_USUARIO = re.compile(r"(?P<inicio>\b[A-Z]:\\Users\\)(?P<valor>[^\\\s]+)", re.I)

_DOCUMENTO_ROTULADO = re.compile(
    r"(?P<inicio>\b(?:RG|CNH|PIS|PASEP|NIS|CTPS|titulo\s+de\s+eleitor|"
    r"t[ií]tulo\s+eleitoral)\s*(?:n[ºo°]\.?\s*)?[:=]?\s*)"
    r"(?P<valor>[A-Z0-9./-]{3,30})",
    re.I,
)
_REFERENCIA_REGISTRAL = re.compile(
    r"(?P<inicio>\b(?:matr[ií]cula|termo|livro|folha|selo|protocolo|"
    r"processo|t[ií]tulo)\s*(?:n[ºo°]\.?\s*)?[:=#-]?\s*)"
    # A REFERÊNCIA TEM DÍGITO ? achado em 08/09/2026, com o sistema ajuda
    # mascarando as próprias perguntas do balcão. "protocolo RCPN" e "titulo
    # RCPJ" caíam aqui: o valor virava [REFERENCIA_REGISTRAL_01] com "RCPN" ?
    # uma sigla de atribuição, não um número de matrícula/livro/folha/selo/
    # protocolo/processo/título, que nesta casa é sempre numérico ou
    # alfanumérico COM dígito (selo, livro "2-A"). Exigir um dígito no valor
    # tira a sigla sem tirar a referência real.
    r"(?=[A-Z0-9./-]*\d)"
    r"(?P<valor>[A-Z0-9][A-Z0-9./-]{1,39})",
    re.I,
)
_DADO_FINANCEIRO = re.compile(
    r"(?P<inicio>\b(?:conta|ag[eê]ncia|chave\s+pix|cart[aã]o|IBAN)\b"
    r"\s*[:=]?\s*)(?P<valor>[^\n;,]{3,100})",
    re.I,
)
_DADO_SENSIVEL = re.compile(
    r"(?P<inicio>\b(?:sa[uú]de|doen[cç]a|diagn[oó]stico\s+m[eé]dico|"
    r"defici[eê]ncia|ra[cç]a|etnia|religi[aã]o|convic[cç][aã]o|"
    r"orienta[cç][aã]o\s+sexual|vida\s+sexual|dado\s+gen[eé]tico|"
    r"biometria|fotografia|impress[aã]o\s+digital)\b\s*[:=]?\s*)"
    r"(?P<valor>[^\n;,]{2,160})",
    re.I,
)
# Caminhos da coleta nova (foto.jpg, digital_1.png). Sem isto, um relatório
# de problema que citasse o arquivo do cadastro sairia com o nome da imagem.
_ARQUIVO_BIOMETRIA = re.compile(
    r"(?:foto\.jpg|digital_[1-9]\d?\.png)",
    re.I,
)
_DATA_PESSOAL = re.compile(
    r"(?P<inicio>\b(?:nascimento|nascido(?:a)?\s+em|data\s+de\s+nascimento|"
    r"[oó]bito\s+em)\b\s*[:=]?\s*)"
    r"(?P<valor>\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
    re.I,
)
_ENDERECO_ROTULADO = re.compile(
    r"(?P<inicio>\b(?:endere[cç]o|domic[ií]lio|resid[eê]ncia)\b\s*[:=]?\s*)"
    r"(?P<valor>[^\n;]{4,180})",
    re.I,
)
_ENDERECO_LIVRE = re.compile(
    r"\b(?:Rua|Avenida|Av\.?|Travessa|Pra[cç]a|Rodovia|Alameda|Estrada)\s+"
    r"[^\n;]{3,160}",
    re.I,
)
_NOME_ROTULADO = re.compile(
    r"(?P<inicio>\b(?:nome|titular|registrando|registrada|registrado|falecida|"
    r"falecido|nubente|devedor(?:a)?|credor(?:a)?|requerente|interessad[oa]|"
    r"outorgante|outorgad[oa]|testemunha|pai|m[aã]e|filia[cç][aã]o|"
    r"c[oô]njuge|companheir[oa])\b\s*[:=]?\s*)"
    r"(?P<valor>[^\n;,.]{2,140})",
    re.I,
)

_PALAVRA_MAIUSCULA = r"[A-ZÁÀÂÃÉÊÍÓÔÕÚÜÇ]{2,}"
_NOME_MAIUSCULO = re.compile(
    rf"(?<![\w\[])\b{_PALAVRA_MAIUSCULA}"
    rf"(?:\s+(?:(?:DA|DE|DO|DAS|DOS|E)\s+)?{_PALAVRA_MAIUSCULA})"
    rf"{{1,5}}\b(?![\w\]])"
)
# A PERGUNTA EM MAIÚSCULAS NÃO É NOME — achado em 23/09/2026, e medido.
#
# `_NOME_MAIUSCULO` via nome de pessoa em toda sequência de duas ou mais
# palavras em maiúsculas — e o balcão desta casa ESCREVE em maiúsculas. Das 51
# consultas da ajuda até esta data, 15 saíram da serventia sem uma palavra da
# pergunta: «COMO FAÇO PRA IMPRIMIR UMA CERTIDÃO DE OBITO» virou
# «[PESSOA_03] [PESSOA_04]», e a ajuda respondeu que não entendeu. Cinco
# pessoas diferentes, de 08/09 a 23/09, e cada consulta paga por nada.
#
# A REGRA MUDOU DENTRO DA SEQUÊNCIA, E NÃO NA SEQUÊNCIA: ela continua sendo
# achada do mesmo jeito, e o que se decide agora é palavra por palavra. A
# palavra que está no vocabulário abaixo é palavra da língua ou do sistema, e
# fica; o que sobra, em trechos seguidos, é mascarado como antes. Assim
# «CERTIDÃO DE JOSÉ DA SILVA» sai «CERTIDÃO DE [PESSOA_01]». O erro, quando
# houver, é para o lado seguro: palavra que não está na lista — inclusive
# digitada errado, «CERTIFDAO» — continua mascarada.
#
# E A LISTA FOI MEDIDA CONTRA OS NOMES DESTA CASA antes de ser escrita: as
# 429 palavras da primeira versão (AO, AOS, DENTRO e FORA entraram depois,
# medidas do mesmo jeito: 82, 63, 3 e 12 vezes em nome, todas por sujeira de
# cadastro) contra os 295.756 nomes de pessoa do banco (Registro Civil,
# Protesto, RI, cartões de firma, CNIB), 77.804 palavras distintas. 201
# aparecem em algum nome, quase todas por sujeira de cadastro ou nome de
# empresa («REGISTRO CIVIL DAS PESSOAS NATURAIS»). Mas NASCIMENTO aparece
# 2.532 vezes e DIAS 2.407: são sobrenome de gente. Por isso há dois níveis.
_VOCABULARIO_COMUM = frozenset("""
A O AS OS AO AOS DENTRO FORA UM UMA UNS UMAS DE DA DO DAS DOS EM NA NO NAS NOS NUM NUMA POR PELA
PELO PELAS PELOS PARA PRA PRO COM SEM SOBRE ATE APOS ENTRE DESDE E OU MAS NEM
QUE SE QUANDO COMO ONDE QUAL QUAIS QUEM QUANTO QUANTOS QUANTA QUANTAS PORQUE
NAO SIM JA AINDA TAMBEM SO APENAS MAIS MENOS MUITO BEM MAL AQUI ALI LA AI
AGORA HOJE ONTEM DEPOIS ANTES SEMPRE NUNCA ESTE ESTA ESSE ESSA ISSO ISTO ESTES
ESTAS ESSES ESSAS MEU MINHA SEU SUA ELE ELA ELES ELAS EU VOCE VOCES ME LHE
TODO TODA TODOS TODAS OUTRO OUTRA CADA ALGUM ALGUMA NENHUM NENHUMA MESMO MESMA
TA TO ENTAO POIS FAVOR OBRIGADO OBRIGADA AJUDA
FAZER FACO FAZ FEZ FIZ FEITO FEITA FAZENDO CONSEGUIR CONSIGO CONSEGUE
CONSEGUINDO CONSEGUI ESTOU ESTAO ESTAVA ESTAR SER SOU FOI ERA SAO TER TEM
TENHO TINHA HA HAVIA PODER POSSO PODE PODEM QUERO QUER QUERIA PRECISO PRECISA
PRECISAR DEVO DEVE IR VOU VAI DAR DEU DEI VER VEJO VI APARECE APARECER
APARECEU SAI SAIR SAIU ENCONTRAR ENCONTRO ACHAR ACHO ACHEI IMPRIMIR IMPRIMI
IMPRIME EMITIR EMITI EMITE EMITIDA EMITIDO GERAR GERO GEREI GERA GERADO GERADA
LANCAR LANCEI LANCADO LANCADA APAGAR APAGUEI EXCLUIR EXCLUI CANCELAR CANCELEI
CANCELADO CANCELADA CORRIGIR CORRIGI EDITAR ALTERAR MUDAR SALVAR SALVEI GRAVAR
ABRIR ABRE ABRIU FECHAR FECHEI ENCERRAR ENVIAR ENVIEI MANDAR BAIXAR BAIXEI
SELAR SELA SELEI SELADO SELADA CALCULAR CALCULO CALCULOS CALCULEI COBRAR
COBROU PUXAR PAGAR PAGO PAGOU RECUPERAR RETIRAR RETIRADO RETIRADA PROCURAR
BUSCAR PESQUISAR CONSULTAR REGISTRAR REGISTREI AVERBAR ANOTAR LAVRAR LAVREI
RECONHECER AUTENTICAR ASSINAR DIGITAR DIGITALIZAR ANEXAR VINCULAR INCLUIR
INSERIR COLOCAR TIRAR USAR FUNCIONA FUNCIONANDO TRAVOU TRAVADO
CERTIDAO CERTIDOES CERTIFICADO SELO SELOS ISENTO ISENTA GRATUITO GRATUITA
DECLARACAO HIPOSSUFICIENCIA OBITO OBITOS NASCIMENTO NASCIMENTOS CASAMENTO
CASAMENTOS REGISTRO REGISTROS ASSENTO ASSENTOS AVERBACAO AVERBACOES ANOTACAO
ANOTACOES RETIFICACAO TERMO LIVRO LIVROS FOLHA FOLHAS FICHA FICHAS MATRICULA
MATRICULAS ATO ATOS PROTOCOLO PROTOCOLOS GERAL PEDIDO PEDIDOS ORCAMENTO
ORCAMENTOS EMOLUMENTO EMOLUMENTOS CUSTAS VALOR VALORES CAIXA RELATORIO
RELATORIOS ENTRADA ENTRADAS SAIDA FINAL DEPOSITO PREVIO RECIBO LANCAMENTO TELA
SISTEMA BOTAO MENU CAMPO ARQUIVO PDF ODT ETIQUETA PAPEL SEGURANCA IMPRESSORA
IMPRESSAO CARTAO CARTOES AUTOGRAFO ORTOGRAFO ASSINATURA FIRMA FIRMAS
RECONHECIMENTO AUTENTICACAO COPIA COPIAS ESCRITURA ESCRITURAS PROCURACAO
PROCURACOES ATA NOTAS TABELIONATO IMOVEIS IMOVEL CIVIL PESSOAS NATURAIS
JURIDICAS TITULOS DOCUMENTOS DOCUMENTO PROTESTO PROTESTOS TITULO DEVEDOR
INTIMACAO EDITAL PRENOTACAO CEDULA HIPOTECA OFICIO OFICIOS CIENCIA ESTADO
MUNICIPIO UNIAO PREFEITURA CARTORIO SERVENTIA OFICIAL ESCREVENTE BALCAO
CLIENTE PARTE PARTES REQUERENTE ERRO ERROS PROBLEMA ENGANO VIA SEGUNDA
PRIMEIRA PRIMEIRO SEGUNDO INTEIRO TEOR RESUMO RELATO MODELO MODELOS CPF RG
CNPJ DADOS DADO NOME ENDERECO CRC SIRC IBGE ONR CRA CENPROT CNIB DOI DNV DIA
DIAS MES ANO
""".split())

# O SEGUNDO NÍVEL: palavra do vocabulário que TAMBÉM é nome de gente aqui —
# 19 ou mais vezes nos nomes do banco, medido em 23/09/2026 (NASCIMENTO
# 2.532, DIAS 2.407, SEGURANCA 2.859, CIVIL 427, …, PRIMEIRO 22, DIA 19). Os
# conectivos e as palavras gramaticais que aparecem em nome (DE, ME, EM,
# PARA) ficam fora desta lista de propósito: estão ali por sujeira de
# cadastro e razão social, e sozinhos não identificam ninguém.
#
# Ela só conta como palavra comum se a palavra anterior (pulando DA, DE, DO…)
# for palavra comum de primeiro nível; quando é a primeira da sequência, olha
# a seguinte. «CERTIDÃO DE NASCIMENTO» passa; «MARIA DO NASCIMENTO» e «JOSÉ
# DIAS» continuam mascarados.
_VOCABULARIO_QUE_TAMBEM_E_NOME = frozenset("""
SEGURANCA NASCIMENTO DIAS CIVIL IMOVEIS GERAL UNIAO PREFEITURA ESTADO VIA
SISTEMA VALORES LIVROS PAPEL CAMPO NATURAIS PESSOAS CPF DADOS AVERBACAO
DEPOSITO RG CAIXA IMPRESSAO SEGUNDO CIENCIA MODELO PRIMEIRA CARTOES PRIMEIRO
DIA
""".split())

_CONECTIVOS_DE_NOME = frozenset({"DA", "DE", "DO", "DAS", "DOS", "E"})


def _chave_da_palavra(palavra: str) -> str:
    """Sem acento e em maiúsculas: «NAÕ» e «NÃO» são a mesma palavra."""
    decomposta = unicodedata.normalize("NFD", palavra)
    return "".join(c for c in decomposta
                   if unicodedata.category(c) != "Mn").upper()


def _trechos_de_nome(sequencia: str) -> list[tuple[int, int]]:
    """Onde, dentro de uma sequência em maiúsculas, mora o nome. Só calcula.

    Devolve (início, fim) de cada trecho a mascarar. Um conectivo (DA, DE…)
    só entra no trecho se estiver ENTRE duas palavras que são nome — é o
    «DA» de «JOSÉ DA SILVA», e não o «DE» de «CERTIDÃO DE JOSÉ».
    """
    palavras = [(m.start(), m.end(), _chave_da_palavra(m.group(0)))
                for m in re.finditer(r"\S+", sequencia)]
    chaves = [p[2] for p in palavras]

    def vizinha(i: int, passo: int) -> str | None:
        j = i + passo
        while 0 <= j < len(chaves) and chaves[j] in _CONECTIVOS_DE_NOME:
            j += passo
        return chaves[j] if 0 <= j < len(chaves) else None

    def firme(chave: str | None) -> bool:
        return (chave in _VOCABULARIO_COMUM
                and chave not in _VOCABULARIO_QUE_TAMBEM_E_NOME)

    comum = []
    for i, chave in enumerate(chaves):
        if chave not in _VOCABULARIO_COMUM:
            comum.append(False)
        elif chave in _VOCABULARIO_QUE_TAMBEM_E_NOME:
            anterior = vizinha(i, -1)
            comum.append(firme(anterior) if anterior is not None
                         else firme(vizinha(i, +1)))
        else:
            comum.append(True)
    for i, chave in enumerate(chaves):
        if chave in _CONECTIVOS_DE_NOME:
            antes = next((not comum[j] for j in range(i - 1, -1, -1)
                          if chaves[j] not in _CONECTIVOS_DE_NOME), False)
            depois = next((not comum[j] for j in range(i + 1, len(chaves))
                           if chaves[j] not in _CONECTIVOS_DE_NOME), False)
            comum[i] = not (antes and depois)

    # Palavras de nome seguidas viram UM trecho — um marcador por pessoa.
    trechos: list[tuple[int, int]] = []
    anterior_era_nome = False
    for (inicio, fim, _chave), e_comum in zip(palavras, comum):
        if e_comum:
            anterior_era_nome = False
        elif anterior_era_nome:
            trechos[-1] = (trechos[-1][0], fim)
        else:
            trechos.append((inicio, fim))
            anterior_era_nome = True
    return trechos


_PALAVRA_CAPITALIZADA = r"[A-ZÁÀÂÃÉÊÍÓÔÕÚÜÇ][a-záàâãéêíóôõúüç]{2,}"
_NOME_CAPITALIZADO = re.compile(
    rf"(?<![\w\[])\b{_PALAVRA_CAPITALIZADA}"
    rf"(?:\s+(?:(?:da|de|do|das|dos|e)\s+)?{_PALAVRA_CAPITALIZADA})"
    rf"{{1,4}}\b(?![\w\]])"
)


def _normalizar(valor: str) -> str:
    texto = unicodedata.normalize("NFKC", valor or "")
    return " ".join(texto.casefold().split())


class _Sanitizador:
    def __init__(self) -> None:
        self._marcadores: dict[tuple[str, str], str] = {}
        self._proximos: dict[str, int] = {}
        self.contagens: dict[str, int] = {}

    def marcador(self, tipo: str, valor: Any) -> str:
        tipo = str(tipo).upper()
        chave = (tipo, _normalizar(str(valor or "")))
        if chave not in self._marcadores:
            numero = self._proximos.get(tipo, 0) + 1
            self._proximos[tipo] = numero
            self._marcadores[chave] = f"[{tipo}_{numero:02d}]"
        self.contagens[tipo] = self.contagens.get(tipo, 0) + 1
        return self._marcadores[chave]

    def simples(self, texto: str, tipo: str, padrao: Pattern[str]) -> str:
        return padrao.sub(lambda m: self.marcador(tipo, m.group(0)), texto)

    def nomes_maiusculos(self, texto: str) -> str:
        """`_NOME_MAIUSCULO`, mascarando só o trecho que é nome (23/09/2026)."""
        def trocar(m: re.Match) -> str:
            sequencia = m.group(0)
            saida, pos = [], 0
            for inicio, fim in _trechos_de_nome(sequencia):
                saida.append(sequencia[pos:inicio])
                saida.append(self.marcador("PESSOA", sequencia[inicio:fim]))
                pos = fim
            saida.append(sequencia[pos:])
            return "".join(saida)
        return _NOME_MAIUSCULO.sub(trocar, texto)

    def rotulado(self, texto: str, tipo: str, padrao: Pattern[str]) -> str:
        return padrao.sub(
            lambda m: f"{m.group('inicio')}{self.marcador(tipo, m.group('valor'))}",
            texto,
        )

    def sanitizar(self, valor: Any, *, nomes_livres: bool = True) -> str:
        texto = str(valor or "")

        # Primeiro os identificadores inequívocos. Assim um segredo ou e-mail
        # nunca chega a ser confundido com nome na passagem mais ampla.
        texto = self.simples(texto, "SEGREDO", _SEGREDO)
        texto = self.simples(texto, "EMAIL", _EMAIL)
        texto = self.simples(texto, "CPF", _CPF)
        texto = self.simples(texto, "TELEFONE", _TELEFONE)
        texto = self.simples(texto, "IP", _IP)
        texto = self.simples(texto, "PROCESSO", _PROCESSO_CNJ)
        texto = _CAMINHO_USUARIO.sub(
            lambda m: f"{m.group('inicio')}{self.marcador('USUARIO', m.group('valor'))}",
            texto,
        )

        texto = self.rotulado(texto, "DOCUMENTO", _DOCUMENTO_ROTULADO)
        texto = self.rotulado(texto, "REFERENCIA_REGISTRAL", _REFERENCIA_REGISTRAL)
        texto = self.rotulado(texto, "DADO_FINANCEIRO", _DADO_FINANCEIRO)
        texto = self.rotulado(texto, "DADO_SENSIVEL", _DADO_SENSIVEL)
        texto = self.simples(texto, "DADO_SENSIVEL", _ARQUIVO_BIOMETRIA)
        texto = self.rotulado(texto, "DATA_PESSOAL", _DATA_PESSOAL)
        texto = self.rotulado(texto, "ENDERECO", _ENDERECO_ROTULADO)
        texto = _ENDERECO_LIVRE.sub(
            lambda m: self.marcador("ENDERECO", m.group(0)), texto
        )
        texto = self.rotulado(texto, "PESSOA", _NOME_ROTULADO)

        # Nomes livres só são procurados no conteúdo escrito pelo operador.
        # A instrução estrutural contém nomes de telas e cabeçalhos como
        # "O MAPA DESTA INSTALAÇÃO"; tratá-los como pessoas inutilizaria a
        # resposta. Identificadores inequívocos e nomes rotulados continuam
        # sendo removidos da instrução.
        if nomes_livres:
            texto = self.nomes_maiusculos(texto)
            texto = self.simples(texto, "PESSOA", _NOME_CAPITALIZADO)
        return texto


_RESIDUAIS = {
    "CPF": _CPF,
    "EMAIL": _EMAIL,
    "TELEFONE": _TELEFONE,
    "IP": _IP,
    "SEGREDO": _SEGREDO,
}


def _conferir_residuos(*textos: str) -> None:
    encontrados = sorted(
        tipo for tipo, padrao in _RESIDUAIS.items()
        if any(padrao.search(texto) for texto in textos)
    )
    if encontrados:
        raise PrivacidadeError(
            "O envio foi bloqueado porque a conferência ainda encontrou: "
            + ", ".join(encontrados)
            + ". A análise deve permanecer local."
        )


def preparar_saida(*, instrucao: Any, pergunta: Any) -> PacoteSanitizado:
    """Sanitiza o envelope inteiro e devolve o único pacote apto à rede."""
    s = _Sanitizador()
    instrucao_segura = s.sanitizar(instrucao, nomes_livres=False)
    pergunta_segura = s.sanitizar(pergunta)
    _conferir_residuos(instrucao_segura, pergunta_segura)
    auditavel = (
        "=== O QUE O SISTEMA CONTA SOBRE ESTA CASA ===\n"
        f"{instrucao_segura}\n"
        "=== A PERGUNTA ===\n"
        f"{pergunta_segura}"
    )
    digital = hashlib.sha256(auditavel.encode("utf-8")).hexdigest()
    return PacoteSanitizado(
        instrucao=instrucao_segura,
        pergunta=pergunta_segura,
        auditavel=auditavel,
        sha256=digital,
        versao=VERSAO_DAS_REGRAS,
        contagens=dict(sorted(s.contagens.items())),
    )


def sanitizar_texto(texto: Any) -> str:
    """Atalho para papéis locais; saídas de rede devem usar preparar_saida."""
    seguro = _Sanitizador().sanitizar(texto)
    _conferir_residuos(seguro)
    return seguro


def sanitizar_para_modelo(texto: Any, *, nomes_livres: bool = True) -> str:
    """A barreira na forma em que o AGENTE devolve ao modelo o que ele leu.

    **Ela existe porque a Ajuda tinha uma porta só, e agora são muitas.** Até
    aqui, o que saía da serventia saía por um lugar: a pergunta do operador,
    montada por `preparar_saida`. O agente lê o banco, lê o código e lê a
    documentação — e cada leitura é uma porta a mais pela qual um dado de
    pessoa pode sair. Uma porta nova sem barreira é a barreira que deixou de
    valer no dia em que se abriu a porta.

    **`nomes_livres=False` É PARA CÓDIGO E DOCUMENTAÇÃO, E A ESCOLHA É
    DECLARADA.** A passagem ampla de nomes come sequências de palavras em
    maiúsculas, e código e comentário são feitos delas: mascarar
    `REGISTRO DE IMOVEIS` deixaria o trecho ilegível, e um diagnóstico feito
    sobre trecho ilegível é um diagnóstico que mente. O que **continua** sendo
    removido com `nomes_livres=False` é tudo o que identifica pessoa — CPF,
    e-mail, telefone, IP, segredo, nome rotulado, documento, endereço e dado
    pessoal. A régua, então, é esta: **dado de pessoa não atravessa; nome de
    código atravessa.**

    `True` é para o que vem do BANCO, que é onde os dados de pessoa moram de
    verdade. Quem chama declara qual dos dois é, ferramenta por ferramenta —
    e o padrão é o mais fechado dos dois usos possíveis, não o mais cômodo.

    Se a conferência ainda achar resíduo, isto **levanta**, como o
    `preparar_saida`: o chamador trata a recusa e devolve ao modelo «este
    resultado não pode ser lido», em vez de deixar passar.
    """
    seguro = _Sanitizador().sanitizar(texto, nomes_livres=nomes_livres)
    _conferir_residuos(seguro)
    return seguro
