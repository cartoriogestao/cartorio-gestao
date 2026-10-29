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
# "3" desde 19/10/2026 (LS03 M2, LX13): os furos medidos pela auditoria — CPF
# com espaço, CNPJ, telefone sem DDD, CEP, «identidade 1234567», «nasceu em»,
# «senha do gov.br: …», causa da morte e o nome solto em minúsculas.
# A versão vai gravada em `aj_consultas.sanitizacao_versao`, e é por ela que se
# separa, depois, o que saiu por uma régua e o que saiu pela outra.
VERSAO_DAS_REGRAS = "3"


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


# O CPF COM ESPAÇO (LS03 M2): «123 456 789 09» é como se dita ao telefone e
# como sai de um PDF mal extraído, e passava inteiro. O espaço é um só, e não
# `\s`: quebra de linha no meio de onze dígitos é tabela, e não CPF.
_CPF = re.compile(r"\b\d{3}[. ]?\d{3}[. ]?\d{3}[- ]?\d{2}\b")
# O CNPJ (LS03 M2) — o do empresário individual é o CPF dele com outra cara. A
# mesma forma que `malote_fraudes._CNPJ` já mascarava no caminho das fraudes.
_CNPJ = re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")
# O TAMANHO DO E-MAIL TEM TETO (CodeQL py/polynomial-redos, 28/10/2026): com
# `+` sem limite, uma fileira de `%` sem `@` fazia cada posição varrer até o
# fim — 50 mil caracteres levavam uns 20 s, e esta barreira lê texto que vem
# de fora. 64 antes do `@` e 255 depois são os limites do próprio e-mail
# (RFC 5321); endereço real nenhum passa deles.
_EMAIL = re.compile(
    r"(?<![\w.+-])[A-Z0-9._%+-]{1,64}@[A-Z0-9.-]{1,255}\.[A-Z]{2,}(?![\w-])",
    re.I,
)
_TELEFONE = re.compile(
    r"(?<!\d)(?:\+?55\s*)?\(?\d{2}\)?\s*(?:9\s*)?\d{4}[-\s]?\d{4}(?!\d)"
)
# O TELEFONE SEM DDD (LS03 M2): «98765-4321» e «3221-4567». Só com o hífen,
# que é o que faz de oito dígitos um telefone: sem ele seria número de
# protocolo. Celular começa com 9 e fixo com 2 a 5; «2010-2020» é intervalo de
# anos, e fica.
_TELEFONE_LOCAL = re.compile(
    r"(?<![\d/.,-])(?!(?:19|20)\d{2}-(?:19|20)\d{2}(?!\d))"
    r"(?:9 ?\d{4}|[2-5]\d{3})-\d{4}(?![\d/-])"
)
# O BRANCO ENTRE O RÓTULO E O VALOR É UM SÓ `\s*` (CodeQL py/polynomial-redos,
# 28/10/2026). Era `\s*[:=]?\s*`: sem os dois pontos, os dois `\s*` ficam
# colados e disputam o mesmo branco, e um rótulo seguido de milhares de
# espaços ou quebras sem valor (texto de PDF recebido de fora, que passa por
# aqui antes de ir ao modelo) custava tempo quadrático — 4 mil brancos, meio
# segundo; 50 mil, minutos. `(?:[:=]\s*)?` casa exatamente o mesmo: o segundo
# branco só existe depois do `:`/`=`, e sem eles o primeiro já o consome.
_TELEFONE_ROTULADO = re.compile(
    r"(?P<inicio>\b(?:telefone|tel|fone|celular|cel|whatsapp|whats|zap)\b\.?"
    r"\s*(?:n[ºo°]\.?\s*)?(?:[:=]\s*)?)"
    r"(?P<valor>\+?\d[\d ().-]{6,18}\d)",
    re.I,
)
# O CEP (LS03 M2): com o hífen, ou com o rótulo.
_CEP = re.compile(r"(?<![\d.,/-])\d{2}\.?\d{3}-\d{3}(?![\d-])")
_CEP_ROTULADO = re.compile(
    r"(?P<inicio>\bCEP\b\.?\s*(?:n[ºo°]\.?\s*)?(?:[:=]\s*)?)"
    r"(?P<valor>\d{2}\.?\d{3}-?\d{3})\b",
    re.I,
)
_IP = re.compile(
    r"(?<!\d)(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}"
    r"(?:25[0-5]|2[0-4]\d|1?\d?\d)(?!\d)"
)
_PROCESSO_CNJ = re.compile(
    r"\b\d{7}-?\d{2}\.?\d{4}\.?\d\.?\d{2}\.?\d{4}\b"
)
# «SENHA DO GOV.BR: …» (LS03 M2): o rótulo com complemento — «senha do
# e-mail», «senha para o portal» — passava, porque a régua exigia os dois
# pontos colados na palavra. E «a senha é Abc@1234» também: com o «é», o valor
# só conta se tiver dígito ou símbolo, senão «a senha é obrigatória» viraria
# segredo.
_COMPLEMENTO_DO_SEGREDO = r"(?:\s+(?:d[aeo]s?|para|no|na)\s+[\w.@/-]{2,30}){0,2}"
_SEGREDO = re.compile(
    r"\b(?:sk-[A-Za-z0-9_-]{8,}|Bearer\s+[A-Za-z0-9._~-]{8,}|"
    r"(?:api[_-]?key|token|senha|password|secret|pin)" + _COMPLEMENTO_DO_SEGREDO
    + r"\s*[:=]\s*[^\s,;]{4,}|"
    r"(?:senha|password|pin)" + _COMPLEMENTO_DO_SEGREDO
    + r"\s+(?:[eé]|era|ficou)\s+(?=[^\s,;]*[\d@#$%!&*])[^\s,;]{4,})",
    re.I,
)
_CAMINHO_USUARIO = re.compile(r"(?P<inicio>\b[A-Z]:\\Users\\)(?P<valor>[^\\\s]+)", re.I)

_DOCUMENTO_ROTULADO = re.compile(
    r"(?P<inicio>\b(?:RG|CNH|PIS|PASEP|NIS|CTPS|titulo\s+de\s+eleitor|"
    r"t[ií]tulo\s+eleitoral)\s*(?:n[ºo°]\.?\s*)?(?:[:=]\s*)?)"
    r"(?P<valor>[A-Z0-9./-]{3,30})",
    re.I,
)
# «IDENTIDADE 1234567» (LS03 M2). O valor precisa de dígito: «identidade
# dele» não é número de documento.
_IDENTIDADE = re.compile(
    r"(?P<inicio>\b(?:carteira\s+de\s+identidade|c[eé]dula\s+de\s+identidade|"
    r"identidade|passaporte|RNE|RNM)\s*(?:n[ºo°]\.?\s*)?(?:[:=]\s*)?)"
    r"(?=[A-Z0-9./-]*\d)(?P<valor>[A-Z0-9][A-Z0-9./-]{2,29})",
    re.I,
)
_REFERENCIA_REGISTRAL = re.compile(
    r"(?P<inicio>\b(?:matr[ií]cula|termo|livro|folha|selo|protocolo|"
    r"processo|t[ií]tulo)\s*(?:n[ºo°]\.?\s*)?(?:[:=#-]\s*)?)"
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
    r"\s*(?:[:=]\s*)?)(?P<valor>[^\n;,]{3,100})",
    re.I,
)
_DADO_SENSIVEL = re.compile(
    r"(?P<inicio>\b(?:sa[uú]de|doen[cç]a|diagn[oó]stico\s+m[eé]dico|"
    r"defici[eê]ncia|ra[cç]a|etnia|religi[aã]o|convic[cç][aã]o|"
    r"orienta[cç][aã]o\s+sexual|vida\s+sexual|dado\s+gen[eé]tico|"
    r"biometria|fotografia|impress[aã]o\s+digital|"
    # A CAUSA DA MORTE (LS03 M2): está na DO e no assento de óbito, e é dado
    # de saúde como qualquer outro.
    r"causa\s+(?:da\s+morte|do\s+[oó]bito|mortis)|causa\s+morte|"
    r"motivo\s+do\s+[oó]bito|CID-?10)\b\s*(?:[:=]\s*)?)"
    r"(?P<valor>[^\n;,]{2,160})",
    re.I,
)
# E a causa dita sem rótulo: «faleceu de», «veio a óbito em decorrência de».
# «Certidão de óbito de» fica fora de propósito: o que vem depois é o nome, e
# o nome tem a régua dele.
_CAUSA_DA_MORTE = re.compile(
    r"(?P<inicio>\b(?:faleceu|morreu|veio\s+a\s+(?:[oó]bito|falecer)|"
    r"vindo\s+a\s+(?:[oó]bito|falecer))\s+(?:de|por|em\s+decorr[eê]ncia\s+de|"
    r"v[ií]tima\s+de|devido\s+a|em\s+raz[aã]o\s+de)\s+)"
    r"(?P<valor>[^\n;,.]{3,120})",
    re.I,
)
# Caminhos da coleta nova (foto.jpg, digital_1.png). Sem isto, um relatório
# de problema que citasse o arquivo do cadastro sairia com o nome da imagem.
_ARQUIVO_BIOMETRIA = re.compile(
    r"(?:foto\.jpg|digital_[1-9]\d?\.png)",
    re.I,
)
# «NASCEU EM» (LS03 M2): a régua tinha «nascido em» e não o verbo, e não
# conhecia a data por extenso («12 de março de 1980»).
_DATA_PESSOAL = re.compile(
    # «nasceu em» termina num branco só (`em\s`, e não `em\s+`): o `\s*` logo
    # adiante já toma o resto, e dois quantificadores colados no mesmo branco
    # eram o retrocesso quadrático da nota de `_TELEFONE_ROTULADO`.
    r"(?P<inicio>\b(?:nascimento|nascid[oa]\s+em|nasceu\s+(?:no\s+dia\s|em\s)|"
    r"data\s+de\s+nascimento|[oó]bito\s+em|faleceu\s+(?:no\s+dia\s|em\s)|"
    r"falecid[oa]\s+em)\s*(?:[:=]\s*)?)"
    r"(?P<valor>\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}|"
    r"\d{1,2}º?\s+de\s+[a-zç]{4,9}\s+de\s+\d{4})",
    re.I,
)
_ENDERECO_ROTULADO = re.compile(
    r"(?P<inicio>\b(?:endere[cç]o|domic[ií]lio|resid[eê]ncia)\b\s*(?:[:=]\s*)?)"
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
    r"c[oô]njuge|companheir[oa])\b\s*(?:[:=]\s*)?)"
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


# O NOME SOLTO, EM MINÚSCULAS OU SOZINHO (LS03 M2). As duas réguas de cima
# pedem duas palavras em maiúsculas ou capitalizadas; «a certidão da maria das
# dores» e «o José pediu» saíam inteiros. Sem maiúscula não há forma que
# separe nome de palavra, e por isso esta régua parte de uma LISTA de prenomes
# comuns e segue o nome palavra a palavra até a primeira que é da língua.
#
# A LISTA FOI ESCRITA, E NÃO MEDIDA contra os nomes do banco (a auditoria não
# leu dado de pessoa). Ficaram de fora os prenomes que também são palavra
# comum — ROSA, LUZ, GLORIA, CLARA, VITORIA, PAZ, CRUZ, GRACA, AURORA,
# ESPERANCA, FE, SOL, DIVINA, NATAL: mascará-los estragaria a frase, e a régua
# das maiúsculas continua pegando quem os tem no nome completo. O erro, quando
# houver, é para o lado seguro: o que vem colado ao prenome, fora da língua,
# vai junto.
_PRENOMES_COMUNS = frozenset("""
MARIA JOSE ANA JOAO ANTONIO FRANCISCO CARLOS PAULO PEDRO LUCAS LUIZ LUIS MARCOS
GABRIEL RAFAEL DANIEL MARCELO BRUNO EDUARDO FELIPE RAIMUNDO RODRIGO MANOEL
MANUEL SEBASTIAO JORGE ANDRE FERNANDO FABIO LEONARDO GUSTAVO GUILHERME RICARDO
TIAGO THIAGO DIEGO SERGIO CLAUDIO MARCIO ROBERTO EDSON MATEUS VITOR
VICTOR HUGO JULIO CESAR ALEXANDRE RENATO JEFERSON JEFFERSON MAURICIO ALAN
WELLINGTON WESLEY ADRIANO GERALDO BENEDITO DOMINGOS JOAQUIM SAMUEL ISAAC ARTHUR
ARTUR HEITOR DAVI DAVID ENZO MIGUEL BERNARDO LORENZO NICOLAS VINICIUS IGOR
OTAVIO EMANUEL EMANOEL ELIAS ISRAEL JOSUE MOISES ABRAAO VALDIR VALDECI EDIVALDO
FRANCISCA ANTONIA ADRIANA JULIANA MARCIA FERNANDA PATRICIA ALINE SANDRA CAMILA
AMANDA BRUNA JESSICA LETICIA JULIA LUCIANA MARIANA GABRIELA VERA
RAIMUNDA SEBASTIANA JOSEFA TEREZA TERESA LUCIA RITA CONCEICAO HELENA BEATRIZ
LARISSA CAROLINA RAQUEL SIMONE DANIELA ELIANE CRISTINA KATIA SONIA REGINA
ROSANGELA ROSANA ROSILENE SUELI SUELY IVONE IRACEMA MARLENE MARINALVA
MARILENE LUZIA ANTONIETA EDILEUZA EDINEIA DEBORA SARA SARAH ISABEL ISABELA
ISABELLA LAURA ALICE VALENTINA HELOISA MANUELA SOFIA SOPHIA LIVIA LORENA
YASMIN JAQUELINE TATIANE TATIANA PRISCILA CLAUDIA ANDREA RENATA
FABIANA SILVIA CELIA ODETE NAIR ZILDA DALVA NEIDE MARTA MARTHA MIRIAM
""".split())

# A palavra que vem depois do prenome e não é nome, quando não está no
# vocabulário de cima: o verbo do balcão («a maria PEDIU»). E o que vem ANTES
# e faz do prenome um lugar: «São Paulo», «Rua João Pessoa».
_NAO_E_SOBRENOME = frozenset("""
PEDIU PEDE VEIO VEM DISSE DIZ CHEGOU LIGOU FALOU ESTEVE NASCEU FALECEU CASOU
SOLICITOU SOLICITA TROUXE TRAZ APRESENTOU ASSINOU COMPARECEU MORA MOROU FICOU
MANDOU RECEBEU COMPROU VENDEU DEIXOU VOLTOU ENTROU RETIROU REQUEREU INFORMOU
DECLAROU ESQUECEU PERDEU QUEREM ESTA ESTAVAM SABE NAO PEDIRAM VIERAM
DISSERAM CHEGARAM LIGARAM FORAM ESTAVA ESTIVERAM TROUXERAM ASSINARAM
""".split())
_ANTES_DE_LUGAR = frozenset("""
SAO SANTA SANTO RUA AVENIDA TRAVESSA PRACA BAIRRO VILA POVOADO FAZENDA ESCOLA
COLEGIO HOSPITAL CIDADE MUNICIPIO RODOVIA ALAMEDA ESTRADA CONJUNTO
""".split())
_PALAVRA = re.compile(r"[^\W\d_]+")
_MARCA = re.compile(r"\[[A-Z_]+_\d+\]")


def _trechos_de_nome_solto(texto: str) -> list[tuple[int, int]]:
    """Onde mora o nome que começa por um prenome comum. Só calcula.

    O trecho vai do prenome até a última palavra que não é da língua, na mesma
    linha; um conectivo (da, de, dos…) só entra entre duas palavras de nome.
    """
    marcas = [m.span() for m in _MARCA.finditer(texto)]
    palavras = [m for m in _PALAVRA.finditer(texto)
                if not any(a <= m.start() < b for a, b in marcas)]
    chaves = [_chave_da_palavra(m.group(0)) for m in palavras]

    def colada(i: int) -> bool:
        entre = texto[palavras[i - 1].end():palavras[i].start()]
        return bool(entre) and entre.isspace() and "\n" not in entre

    def de_nome(i: int) -> bool:
        c = chaves[i]
        return (len(c) >= 2 and c not in _NAO_E_SOBRENOME
                and c not in _CONECTIVOS_DE_NOME
                and (c not in _VOCABULARIO_COMUM
                     or c in _VOCABULARIO_QUE_TAMBEM_E_NOME))

    trechos: list[tuple[int, int]] = []
    i = 0
    while i < len(palavras):
        if (chaves[i] not in _PRENOMES_COMUNS
                or (i and colada(i) and chaves[i - 1] in _ANTES_DE_LUGAR)):
            i += 1
            continue
        fim, j = palavras[i].end(), i + 1
        while j < len(palavras) and colada(j):
            if (chaves[j] in _CONECTIVOS_DE_NOME and j + 1 < len(palavras)
                    and colada(j + 1) and de_nome(j + 1)):
                fim, j = palavras[j + 1].end(), j + 2
            elif de_nome(j):
                fim, j = palavras[j].end(), j + 1
            else:
                break
        trechos.append((palavras[i].start(), fim))
        i = j
    return trechos


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

    def nomes_soltos(self, texto: str) -> str:
        """`_trechos_de_nome_solto`: o prenome comum em minúsculas ou sozinho."""
        saida, pos = [], 0
        for inicio, fim in _trechos_de_nome_solto(texto):
            saida.append(texto[pos:inicio])
            saida.append(self.marcador("PESSOA", texto[inicio:fim]))
            pos = fim
        saida.append(texto[pos:])
        return "".join(saida)

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
        texto = self.simples(texto, "CNPJ", _CNPJ)
        texto = self.simples(texto, "CPF", _CPF)
        texto = self.simples(texto, "TELEFONE", _TELEFONE)
        texto = self.rotulado(texto, "TELEFONE", _TELEFONE_ROTULADO)
        texto = self.simples(texto, "TELEFONE", _TELEFONE_LOCAL)
        texto = self.rotulado(texto, "CEP", _CEP_ROTULADO)
        texto = self.simples(texto, "CEP", _CEP)
        texto = self.simples(texto, "IP", _IP)
        texto = self.simples(texto, "PROCESSO", _PROCESSO_CNJ)
        texto = _CAMINHO_USUARIO.sub(
            lambda m: f"{m.group('inicio')}{self.marcador('USUARIO', m.group('valor'))}",
            texto,
        )

        texto = self.rotulado(texto, "DOCUMENTO", _DOCUMENTO_ROTULADO)
        texto = self.rotulado(texto, "DOCUMENTO", _IDENTIDADE)
        texto = self.rotulado(texto, "REFERENCIA_REGISTRAL", _REFERENCIA_REGISTRAL)
        texto = self.rotulado(texto, "DADO_FINANCEIRO", _DADO_FINANCEIRO)
        texto = self.rotulado(texto, "DADO_SENSIVEL", _DADO_SENSIVEL)
        texto = self.rotulado(texto, "DADO_SENSIVEL", _CAUSA_DA_MORTE)
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
            texto = self.nomes_soltos(texto)
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
