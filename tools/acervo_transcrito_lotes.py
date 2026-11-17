# -*- coding: utf-8 -*-
r"""Prepara os lotes do acervo transcrito (Livro A) a partir das planilhas.

    «vamos incluir no sistema os registros dos livros que faltam em
     importacoes ... de forma a organizar e preencher todos os requisitos para
     emissao de certidoes fisicas e da crc, e envio de cargas da CRC e Sirc.
     Use o texto transcrito do teor para completar eventuais lacunas. e o que
     nao tivermos informacoes no teor, colocar que nao consta»
    — o oficial, 17/11/2026 (e, no mesmo dia: «resolva os problemas que
     aparecem nos livros que ja foram importados»)

O QUE FAZ
    Lê `Livro_<pasta>_transcricao.xlsx` (aba Termos) de cada livro e escreve,
    numa pasta de destino, os manifestos `CARTORIO_GESTAO_ACERVO_RCPN_LOTE`
    que a tela «Acervo transcrito → Sequência» do principal aplica
    (`rc_acervo_lote`), com o PDF de cada termo ao lado (link físico quando o
    disco deixa, senão cópia) e os índices `CARTORIO_GESTAO_ACERVO_RCPN_
    SEQUENCIA`. Junto, `conferencia.xlsx`: o que ficou fora do lote e por quê,
    e o que merece olho humano.

    **NÃO ESCREVE NO BANCO.** Lê o banco (de preferência a réplica, com usuário
    que só lê) para decidir inclusão × complemento e para não trocar o que já
    está certo. Quem grava é o lote, no principal, com prévia, autoria,
    auditoria e cópia do antes.

AS REGRAS (decisões do oficial em 17/11/2026)
    - Vale o teor transcrito. O nome do sistema só fica quando a diferença é
      pequena — a que pode ser falha da própria transcrição (letra trocada,
      acento, «[?]») — e então vai para a conferência.
    - O que o teor não diz fica VAZIO no assento: é o vazio que faz a CRC
      mandar a tag em branco / «não consta» e o SIRC o `*Ignorado` que o XSD
      aceita. A certidão física escreve «NÃO CONSTA» (`rc_certidao.SEM_DADO`).
      O tipo do local sem indicação no teor é 9 (ignorado, a tabela do IBGE).
    - A lista do que não consta fica no pacote (`dados_json.nao_consta`).
    - Sexo não se adivinha: sem «sexo masculino/feminino» no teor, fica vazio
      e a CRC retém (decisão de 12/09/2026, `crc_carga`).

USO (no Mac da reserva, contra a réplica que só lê)
    python tools/acervo_transcrito_lotes.py \
        --saida "/Volumes/.../importacoes/saida" \
        --destino "/Volumes/.../importacoes/lotes_rcpn_20261117" \
        --dsn "host=127.0.0.1 port=5434 user=cg_leitor dbname=cartorio" --schema producao \
        --livro 07_1968=A-7 --livro A-01_1976-1979=A-1 ...

    Precisa de `openpyxl` (não é dependência do sistema; instale à parte).
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import re
import shutil
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import rc_matricula as MAT  # noqa: E402
from rc_acervo_lote import FORMATO, folha_do_papel, LoteError  # noqa: E402
from rc_acervo_sequencia import FORMATO as FORMATO_SEQUENCIA  # noqa: E402
from rc_campos_do_acervo import codigo_ibge_do_local_escrito  # noqa: E402

POR_LOTE = 100
LOTES_POR_SEQUENCIA = 140
ORIGENS_COMPLEMENTAVEIS = frozenset({'EOFICIO', 'IMPORTACAO', 'ARQUIVO', 'ACERVO'})
IGNORADO_IBGE = 9

# --------------------------------------------------------------- texto


def sem_acento(t) -> str:
    t = unicodedata.normalize('NFKD', str(t or ''))
    return ''.join(c for c in t if not unicodedata.combining(c))


def norm(t) -> str:
    """minúsculas, sem acento, só letras/dígitos e espaço simples."""
    t = sem_acento(t).lower()
    t = re.sub(r'[^a-z0-9]+', ' ', t)
    return ' '.join(t.split())


def iso_entre_parenteses(t) -> str | None:
    """A data ISO que a transcrição pôs entre parênteses. Duas datas
    diferentes («1976-07-19 ou 1976-07-22») é dúvida: nenhuma."""
    datas = set(re.findall(r'\b(\d{4})-(\d{2})-(\d{2})\b', str(t or '')))
    if len(datas) != 1:
        return None
    a, m, d = next(iter(datas))
    try:
        return date(int(a), int(m), int(d)).isoformat()
    except ValueError:
        return None


MESES = {'janeiro': 1, 'fevereiro': 2, 'marco': 3, 'abril': 4, 'maio': 5, 'junho': 6,
         'julho': 7, 'agosto': 8, 'setembro': 9, 'outubro': 10, 'novembro': 11,
         'dezembro': 12}


def primeira_data(t) -> str | None:
    """A primeira data escrita na nota («29/07/2009», «29/07/09», «29 de julho
    de 2009»). Ano de dois dígitos: 00–30 é 20xx, o resto 19xx."""
    s = sem_acento(t).lower()
    candidatos = []
    for m in re.finditer(r'\b(\d{1,2})\s*[/.-]\s*(\d{1,2})\s*[/.-]\s*(\d{2,4})\b', s):
        candidatos.append((m.start(), int(m[1]), int(m[2]), m[3]))
    for m in re.finditer(r'\b(\d{1,2})\s+de\s+([a-z]+)\s+de\s+(\d{4})\b', s):
        if m[2] in MESES:
            candidatos.append((m.start(), int(m[1]), MESES[m[2]], m[3]))
    for _, d, mes, a in sorted(candidatos):
        ano = int(a)
        if len(a) == 2:
            ano += 2000 if ano <= 30 else 1900
        elif len(a) == 3:
            continue
        try:
            return date(ano, mes, d).isoformat()
        except ValueError:
            continue
    return None


# --------------------------------------------------------------- nomes

_MARCA_INCOMPLETA = re.compile(r'\[(?:ileg[ií]vel|rasura|rasgad[oa]|borr[aã]o|apagad[oa])[^\]]*\]', re.I)


def limpar_nome(bruto) -> tuple[str, list[str]]:
    """O nome como vai à ficha, e o que se notou nele. Só calcula.

    Entrelinha entra; riscado sai; «[?]» sai (a dúvida vai para o pacote e a
    conferência); nota entre parênteses sai; «A B digo C» troca só a parte que
    o «digo» corrigiu. «[ilegível]»/«[rasura]» saem e o nome vai à conferência
    como incompleto.
    """
    notas: list[str] = []
    s = str(bruto or '').strip()
    if not s:
        return '', notas
    if '[?]' in s:
        notas.append('leitura duvidosa no nome')
    if _MARCA_INCOMPLETA.search(s):
        notas.append('nome com trecho ilegível ou rasurado')
    s = re.sub(r'\[entrelinha:\s*([^\]]*)\]', r' \1 ', s, flags=re.I)
    s = re.sub(r'\[riscado:[^\]]*\]', ' ', s, flags=re.I)
    s = _MARCA_INCOMPLETA.sub(' ', s)
    s = s.replace('[?]', '')
    s = re.sub(r'\[[^\]]*\]', ' ', s)
    # notas entre parênteses (título, texto, declarante, retificado...)
    for _ in range(3):
        s = re.sub(r'\([^()]*\)', ' ', s)
    s = s.replace('(', ' ').replace(')', ' ')
    s = re.sub(r',?\s*\b(?:j[áa]\s+)?falecid[oa]\b.*$', '', s, flags=re.I)
    s = re.sub(r'^[^A-Za-zÀ-ÿ]+', '', s)
    s = re.sub(r'^(?:retificad|averbad|corrigid)\w*[^:]{0,30}:\s*', '', s, flags=re.I)
    s = re.sub(r'\s*;.*$', '', s)
    partes = re.split(r'[\s,.;]*\bdigo\b[\s,.;:]*', s, flags=re.I)
    if len(partes) > 1:
        notas.append('nome corrigido por «digo» no termo')
        atual = partes[0].split()
        for direita in partes[1:]:
            d = direita.split()
            if not d:
                continue
            if not atual:
                atual = d
            elif norm(d[-1]) == norm(atual[-1]) and len(d) <= len(atual):
                atual = atual[:-len(d)] + d
            else:
                atual = atual[:-1] + d
        s = ' '.join(atual)
    s = re.sub(r'\s+', ' ', s).strip(' .,;:-')
    if ',' in s:   # «Osvaldo Silva Carvalho, OSWALDO SILVA CARVALHO»
        cabeca, resto = s.split(',', 1)
        if len(resto.split()) >= 2 and diferenca_pequena(cabeca, resto):
            s = cabeca.strip()
    return s, notas


_PARTICULAS = {'de', 'da', 'do', 'das', 'dos', 'e', 'd'}


def _tokens(nome) -> list[str]:
    return [t for t in norm(nome).split() if t not in _PARTICULAS]


def _edicoes(a: str, b: str) -> int:
    """Distância de edição (Levenshtein): letras trocadas, faltando ou sobrando."""
    ant = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        atual = [i]
        for j, cb in enumerate(b, 1):
            atual.append(min(ant[j] + 1, atual[j - 1] + 1, ant[j - 1] + (ca != cb)))
        ant = atual
    return ant[-1]


def diferenca_pequena(a, b) -> bool:
    """Diferença que pode ser falha de transcrição: mesmas palavras na mesma
    ordem, cada uma com no máximo duas letras trocadas (ou abreviada), ou a
    mesma sequência com uma palavra a mais/menos. Só calcula."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    if ta == tb:
        return True
    if len(ta) == len(tb):
        for x, y in zip(ta, tb):
            if x == y:
                continue
            if len(x) == 1 or len(y) == 1:   # abreviatura «R.»
                if x[0] != y[0]:
                    return False
                continue
            if _edicoes(x, y) > (2 if min(len(x), len(y)) >= 5 else 1):
                return False
        return True
    curta, longa = sorted((ta, tb), key=len)
    if len(longa) - len(curta) == 1:
        it = iter(longa)
        return all(any(t == u for u in it) for t in curta)
    return False


# --------------------------------------------------------------- campos


def sexo_de(valor, teor) -> str:
    s = norm(valor)
    if s.startswith('m') or re.search(r'\bmas\w*', s):
        return 'M'
    if s.startswith('f') or re.search(r'\bfem\w*', s):
        return 'F'
    t = norm(teor)
    if re.search(r'\bseu filho\b|\bfilho legitimo\b', t) and not re.search(r'\bsua filha\b|\bfilha legitima\b', t):
        return 'M'
    if re.search(r'\bsua filha\b|\bfilha legitima\b', t) and not re.search(r'\bseu filho\b|\bfilho legitimo\b', t):
        return 'F'
    m = re.search(r'\bsexo\s+(m|f)\w*', t)
    if m:
        return 'M' if m[1] == 'm' else 'F'
    if re.search(r'\bo registrando\b|\bnasceu um menino\b', t) and not re.search(r'\ba registranda\b', t):
        return 'M'
    if re.search(r'\ba registranda\b|\bnasceu uma menina\b', t) and not re.search(r'\bo registrando\b', t):
        return 'F'
    return ''


def hora_de(valor) -> str:
    s = sem_acento(valor).lower()
    m = re.search(r'(?<!\d)(\d{1,2})\s*[:h.]\s*(\d{2})(?!\d)', s)
    if not m:
        m = re.search(r'(?<!\d)(\d{1,2})\s*(?:horas?|hs?|hrs?|haras)\b(?:\s*e\s*(\d{1,2})\s*min)?', s)
    if not m:
        return ''
    h, mi = int(m[1]), int(m[2] or 0)
    if not (0 <= h <= 23 and 0 <= mi <= 59):
        return ''
    return f'{h:02d}:{mi:02d}'


def idade_de(valor) -> str:
    """O primeiro número plausível de idade («(16) anos», «[rasura] digo 21 anos»)."""
    for m in re.finditer(r'(?<!\d)(\d{1,2})(?!\d)', str(valor or '')):
        if 8 <= int(m[1]) <= 70:
            return m[1]
    return ''


def dnv_de(valor) -> str:
    d = re.sub(r'\D', '', str(valor or ''))
    return d if 6 <= len(d) <= 11 else ''


def cor_de(valor) -> str:
    s = norm(str(valor or '').replace('[?]', ''))
    for chave, cor in (('moren', 'morena'), ('maren', 'morena'), ('branc', 'branca'),
                       ('pard', 'parda'), ('pret', 'preta'), ('negr', 'preta'),
                       ('indi', 'indígena'), ('amarel', 'amarela')):
        if s.startswith(chave):
            return cor
    return ''


_ADJ_UF = {'maranhens': 'MA', 'piauiens': 'PI', 'cearens': 'CE', 'paraens': 'PA',
           'goian': 'GO', 'baian': 'BA', 'pernambucan': 'PE', 'tocantinens': 'TO',
           'paraiban': 'PB', 'alagoan': 'AL', 'mineir': 'MG', 'paulist': 'SP',
           'potiguar': 'RN', 'norte riograndens': 'RN', 'sergipan': 'SE',
           'capixab': 'ES', 'carioc': 'RJ', 'gauch': 'RS', 'mato grossens': 'MT'}
_ESTADO_CIVIL = (('solteir', 'solteir'), ('casad', 'casad'), ('viuv', 'viúv'),
                 ('divorciad', 'divorciad'), ('separad', 'separad'))
_PROFISSOES = ('lavrador', 'lavradora', 'lavradeira', 'agricultor', 'agricultora',
               'domestica', 'do lar', 'servicos domesticos', 'prendas domesticas',
               'professor', 'professora', 'comerciante', 'estudante', 'vaqueiro',
               'pedreiro', 'motorista', 'funcionario publico', 'funcionaria publica',
               'operador de maquinas', 'mecanico', 'carpinteiro', 'pecuarista',
               'fazendeiro', 'enfermeira', 'auxiliar de enfermagem', 'costureira',
               'servidor publico', 'servidora publica', 'autonomo', 'autonoma')


# --------------------------------------------------------------- municípios


class Municipios:
    """O cadastro do IBGE da casa (`ib_municipios`), para achar o município
    escrito num texto. Só devolve o que o cadastro confirma."""

    # Só abreviaturas de escrita, de qualquer cartório. Os apelidos de cada
    # município (a inicial e o resto — «P. Franco» —, o nome emendado) saem
    # do cadastro em `__init__`; a grafia torta fica com a semelhança.
    APELIDOS = {'gov': 'governador', 'pres': 'presidente', 'sen': 'senador',
                'dep': 'deputado', 'sta': 'santa', 'sto': 'santo',
                'segundo': 'ii', 'primeiro': 'i'}
    UFS = {'ma': 'MA', 'maranhao': 'MA', 'to': 'TO', 'tocantins': 'TO', 'pa': 'PA',
           'para': 'PA', 'pi': 'PI', 'piaui': 'PI', 'ce': 'CE', 'ceara': 'CE',
           'go': 'GO', 'goias': 'GO', 'ba': 'BA', 'bahia': 'BA', 'pe': 'PE',
           'pb': 'PB', 'df': 'DF', 'sp': 'SP', 'mg': 'MG'}

    def __init__(self, linhas, cidade_da_casa: str, uf_da_casa: str):
        self.por_nome: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for r in linhas:
            self.por_nome[norm(r['nome'])].append((r['nome'], r['uf']))
        self.casa = (cidade_da_casa, uf_da_casa)
        self.ultimo_por_grafia = ''
        # «C. Exemplo», «P. Franco», «CidadeExemplo»: a inicial do primeiro nome e o
        # resto, ou tudo emendado — quando o apelido é único na UF da casa.
        apelidos: dict[str, list] = defaultdict(list)
        for n, opcoes in list(self.por_nome.items()):
            noUF = [o for o in opcoes if o[1] == uf_da_casa]
            partes = n.split()
            if not noUF or len(partes) < 2 or len(' '.join(partes[1:])) < 4:
                continue
            for apelido in (partes[0][0] + ' ' + ' '.join(partes[1:]), ''.join(partes)):
                apelidos[apelido].append(noUF[0])
        for apelido, opcoes in apelidos.items():
            if len(opcoes) == 1 and apelido not in self.por_nome:
                self.por_nome[apelido] = opcoes

    ESTADOS = (('maranhao', 'MA'), ('piaui', 'PI'), ('ceara', 'CE'), ('para', 'PA'),
               ('pernambuco', 'PE'), ('paraiba', 'PB'), ('minas gerais', 'MG'),
               ('goias', 'GO'), ('bahia', 'BA'), ('tocantins', 'TO'), ('mato grosso', 'MT'),
               ('rio grande do norte', 'RN'), ('alagoas', 'AL'), ('sergipe', 'SE'),
               ('sao paulo', 'SP'), ('distrito federal', 'DF'))

    def uf_do_texto(self, t: str) -> str:
        """A UF que o texto diz («Estado do Ceará», «-PI», «deste Estado»)."""
        for nome, uf in self.ESTADOS:
            if re.search(rf'\b(?:estado d[oae] |e d[oae] |no |)\b{nome}\b', t) and \
                    not re.search(rf'\b\w+ (?:do|de) {nome}\b', t.replace('estado do ' + nome, '')):
                return uf
        for nome, uf in self.ESTADOS:
            if re.search(rf'\b{nome}\b', t):
                return uf
        m = re.search(r'\b(ma|pi|ce|pa|pe|pb|mg|go|ba|to|mt|df|sp)\s*$', t.strip())
        if m:
            return m[1].upper()
        if re.search(r'\b(?:deste|neste|d|n|este|nesse) estado\b', t):
            return self.casa[1]
        return ''

    def _escolher(self, nome_norm: str, uf: str) -> tuple[str, str] | None:
        opcoes = self.por_nome.get(nome_norm) or []
        for preferida in (uf, self.casa[1]):
            for nome, u in opcoes:
                if u == preferida:
                    return nome, u
        return opcoes[0] if len(opcoes) == 1 and not uf else None

    def no_texto(self, texto) -> tuple[str, str] | None:
        """O município que o texto nomeia, confirmado no cadastro."""
        t = ' ' + norm(texto) + ' '
        t = ' ' + ' '.join(self.APELIDOS.get(w, w) for w in t.split()) + ' '
        # «mudicipio», «municipo», «estdo»: a palavra de ligação mal escrita
        t = ' ' + ' '.join(
            'municipio' if (len(w) > 6 and difflib.SequenceMatcher(None, w, 'municipio').ratio() >= 0.8)
            else w for w in t.split()) + ' '
        if not t.strip():
            return None
        uf = self.uf_do_texto(t)
        self.ultimo_por_grafia = ''
        m = re.search(r'\b(?:municipio|m|cidade) de ([a-z ]+?)(?: (?:no |n )?estado\b| deste\b| ma\b|$)', t)
        if m and m[1].strip() != t.strip():
            dito = (self.no_texto(m[1] + (' ' + uf.lower() if uf else ''))
                    if len(m[1].split()) <= 5 else None)
            if dito and dito != self.casa:
                return dito
            self.ultimo_por_grafia = ''
        achados = sorted((n for n in self.por_nome if f' {n} ' in t and len(n) > 3),
                         key=len, reverse=True)
        for n in achados:
            escolhido = self._escolher(n, uf)
            if escolhido and (not uf or escolhido[1] == uf or escolhido == self.casa):
                return escolhido
        # «São Domingos deste Estado do Maranhão» → São Domingos do Maranhão
        if uf:
            estado = next((nome for nome, u in self.ESTADOS if u == uf), '')
            for n, opcoes in self.por_nome.items():
                if n.endswith(' do ' + estado) and any(u == uf for _, u in opcoes):
                    raiz = n[: -len(' do ' + estado)]
                    if len(raiz) > 3 and f' {raiz} ' in t:
                        return self._escolher(n, uf)
        if re.search(r'\b(?:d|n)?(?:e|e)st[ea] (?:municipio|cidade|termo)\b|\bd m\b|\bn m\b'
                     r'|\b(?:d|n) (?:municipio|termo|cidade)\b|\bnesta\b', t):
            return self.casa
        # grafia: a janela de uma a três palavras parecida com um município da UF dita
        uf_busca = uf or self.casa[1]
        nomes = [n for n, v in self.por_nome.items() if any(u == uf_busca for _, u in v)]
        palavras = [p for p in t.split() if p not in ('estado', 'do', 'de', 'no', 'municipio', 'lugar', 'm')]
        for tam in (3, 2, 1):
            for i in range(len(palavras) - tam + 1):
                janela = ' '.join(palavras[i:i + tam])
                if len(janela) < 5:
                    continue
                perto = difflib.get_close_matches(janela, nomes, n=2,
                                                  cutoff=0.8 if tam == 1 and len(janela) >= 6 else 0.86)
                primeira = janela.split()[0]
                if not perto or (perto[0].split()[0] != primeira and any(
                        n.startswith(primeira + ' ') and n != perto[0] for n in nomes)):
                    continue   # «Ribeiro»: Ribeiro Gonçalves? não se escolhe
                if perto:
                    notas = [difflib.SequenceMatcher(None, janela, n).ratio() for n in perto]
                    if len(perto) > 1 and notas[0] - notas[1] < 0.04:
                        continue   # duas cidades parecidas: não se escolhe
                    escolhido = self._escolher(perto[0], uf_busca)
                    if escolhido:
                        self.ultimo_por_grafia = f'«{janela}» lido como {escolhido[0]}/{escolhido[1]}'
                    return escolhido
        return None


# --------------------------------------------------------------- margem


def atos_da_margem(averbacoes) -> list[dict]:
    """As notas da coluna «averbacoes», uma por « | », como `rc_atos`."""
    saida = []
    for parte in re.split(r'\s+\|\s+', str(averbacoes or '').strip()):
        teor = parte.strip()
        if len(norm(teor)) < 8:
            continue
        t = norm(teor)
        tipo, natureza = 'ANOTACAO', None
        if 'cpf' in t and ('averb' in t or 'inscrit' in t):
            tipo, natureza = 'AVERBACAO', 'cpf_347'
        elif re.search(r'reconhec\w* (?:de )?(?:paternidade|maternidade|filiacao)|reconheceu\w* (?:como )?(?:seu )?filh', t) \
                or 'reconhecimento de paternidade' in t:
            tipo, natureza = 'AVERBACAO', 'reconhecimento_filiacao'
        elif 'retific' in t:
            tipo, natureza = 'AVERBACAO', 'retificacao'
        elif re.search(r'\b(?:faleceu|falecid|obito)\b', t) or re.search(r'\bcasou\w*|\bcasamento\b', t):
            tipo, natureza = 'ANOTACAO', None
        elif re.search(r'\bpassou a (?:se )?chamar|\bpassara a chamar|\balteracao de nome', t):
            tipo, natureza = 'AVERBACAO', 'alteracao_nome'
        elif re.search(r'\baverb|\bav ?\d', t):
            tipo, natureza = 'AVERBACAO', 'outra'
        saida.append({'tipo': tipo, 'natureza': natureza, 'teor': teor,
                      'data_ato': primeira_data(teor)})
    return saida


# --------------------------------------------------------------- o registro


def trecho_do_nascimento(teor: str) -> str:
    """O pedaço do termo que fala de onde nasceu — e não o endereço do
    cartório, nem o dos avós. Só calcula."""
    t = str(teor or '')
    m = re.search(r'(declar\w+ que|nasceu)(.{0,260})', t, re.I | re.S)
    return m[0] if m else ''


def montar(d: dict, livro: str, pasta: str, linha: int, ctx) -> dict:
    """Um registro do lote a partir de uma linha da planilha. Só calcula.

    Devolve {'valores', 'margem', 'avisos', 'nao_consta', 'numero', 'pdf',
    'situacao_papel'}."""
    avisos: list[str] = []
    teor = str(d.get('texto_integral') or '').strip()
    numero = int(re.sub(r'\D', '', str(d.get('termo') or '')) or 0)
    nome, notas = limpar_nome(d.get('nome_registrado'))
    avisos += [f'registrado: {n}' for n in notas]
    notas_nome = {'REGISTRADO': notas}
    data_ato = iso_entre_parenteses(d.get('data_registro')) or primeira_data(d.get('data_registro'))
    data_fato = iso_entre_parenteses(d.get('data_nascimento')) or primeira_data(d.get('data_nascimento'))
    if not data_ato:
        avisos.append('data do registro não lida na transcrição')
    if not data_fato:
        avisos.append('data do nascimento não lida na transcrição')
    if data_ato and data_fato and data_fato > data_ato:
        avisos.append(f'nascimento ({data_fato}) depois do registro ({data_ato}) na transcrição')
    try:
        folha = folha_do_papel(re.sub(r'[^0-9vV]', '', str(d.get('folha') or '')))
    except LoteError:
        folha = ''
        avisos.append(f'folha ilegível na transcrição: {d.get("folha")!r}')
    sexo = sexo_de(d.get('sexo'), teor)
    hora = hora_de(d.get('hora_nascimento'))
    local = re.sub(r'\[\?\]', '', str(d.get('local_nascimento') or '')).strip(' .;,')
    mun = ctx.municipios.no_texto(local) if local else None
    if not mun:
        mun = ctx.municipios.no_texto(trecho_do_nascimento(teor))
    if mun and ctx.municipios.ultimo_por_grafia:
        avisos.append('município do nascimento por semelhança de grafia: '
                      + ctx.municipios.ultimo_por_grafia)
    codigo_local = codigo_ibge_do_local_escrito(local) or \
        codigo_ibge_do_local_escrito(trecho_do_nascimento(teor))
    nao_consta = []
    v: dict = {'livro_volume': livro, 'numero': numero, 'nome': nome,
               'teor': teor, 'teor_formato': 'texto'}
    if data_ato:
        v['data_ato'] = data_ato
    if data_fato:
        v['data_fato'] = data_fato
    if hora:
        v['hora_fato'] = hora
    else:
        nao_consta.append('hora do nascimento')
    if local:
        v['local_fato_nome'] = local
    else:
        nao_consta.append('local do nascimento')
    if mun:
        v['local_fato_municipio'] = f'{mun[0]}/{mun[1]}'
    else:
        nao_consta.append('município do nascimento')
        if local:
            avisos.append(f'município do nascimento não achado no IBGE: «{local}»')
    if codigo_local:
        v['ibge_local_nascimento'] = codigo_local
    else:
        v['ibge_local_nascimento'] = IGNORADO_IBGE
        nao_consta.append('tipo do local do nascimento (hospital/domicílio/outro)')
    # A coluna «naturalidade» da planilha traz de tudo («dêste Estado»,
    # «retificada por averbação…»). Só vira naturalidade o município que o
    # IBGE confirma; o texto fica no pacote (`acervo_transcrito`).
    naturalidade = re.sub(r'\[\?\]', '', str(d.get('naturalidade') or '')).strip()
    nat = ctx.municipios.no_texto(naturalidade) if naturalidade else None
    if nat and not re.search(r'averba|retific', naturalidade, re.I):
        v['naturalidade_declarada'] = f'{nat[0]}/{nat[1]}'
    else:
        nat = None
    cor = cor_de(d.get('cor'))
    if cor:
        v['cor_raca'] = cor
    else:
        nao_consta.append('cor')
    dnv = dnv_de(d.get('dnv'))
    if dnv:
        v['dnv'] = dnv
    else:
        nao_consta.append('DNV')
    cpf = re.sub(r'\D', '', str(d.get('cpf_registrado') or ''))
    if len(cpf) == 11:
        v['cpf_registrado'] = cpf
    if data_ato and data_fato:
        dias = (date.fromisoformat(data_ato) - date.fromisoformat(data_fato)).days
        if dias > 90:
            v['registro_tardio'] = 1
    elif norm(d.get('tipo_registro')).startswith('tardio'):
        v['registro_tardio'] = 1
    if not sexo:
        nao_consta.append('sexo')
        avisos.append('sexo do registrado não consta no teor (a CRC retém)')
    # matrícula: CNS + 01 + 55 + ano + 1 + livro + folha + termo + DV
    matricula = ''
    if data_ato and folha and ctx.cns:
        try:
            matricula = MAT.compor(cns=ctx.cns, ano=int(data_ato[:4]), livro_tipo='1',
                                   livro=int(livro.split('-')[1]),
                                   folha=int(re.sub(r'\D', '', folha)), termo=numero)
        except Exception as erro:  # noqa: BLE001 - vai para a conferência
            avisos.append(f'matrícula não composta: {erro}')
    if matricula:
        v['matricula'] = matricula
    natural = nat or mun
    pessoas = [{'papel': 'REGISTRADO', 'nome': nome, **({'sexo': sexo} if sexo else {}),
                **({'naturalidade_cidade': natural[0], 'naturalidade_uf': natural[1]} if natural else {})}]
    for papel, campo, qual, sx in (('MAE', 'mae', 'mae_qualificacao', 'F'),
                                   ('PAI', 'pai', 'pai_qualificacao', 'M')):
        bruto = str(d.get(campo) or '').strip()
        if not bruto or norm(bruto) in ('ignorado', 'ignorada', 'nao consta', 'nao declarado', '') \
                or norm(bruto).startswith(('ignorad', 'nao consta', 'nao declar')):
            nao_consta.append('pai' if papel == 'PAI' else 'mãe')
            continue
        n, notas = limpar_nome(bruto)
        if not n:
            continue
        avisos += [f'{papel.lower()}: {x}' for x in notas]
        notas_nome[papel] = notas
        p = {'papel': papel, 'nome': n, 'sexo': sx}
        q = str(d.get(qual) or '')
        p.update(qualificacao(q, ctx))
        if papel == 'MAE':
            idade = idade_de(d.get('idade_mae_no_parto'))
            if idade:
                p['idade_no_fato'] = idade
        pessoas.append(p)
    if not str(d.get('avos_paternos') or '').strip():
        nao_consta.append('avós paternos')
    if not str(d.get('avos_maternos') or '').strip():
        nao_consta.append('avós maternos')
    if '[?]' in teor:
        avisos.append('teor com leituras duvidosas [?] — conferir no original')
    v['pessoas'] = pessoas
    transcrito = {k: (str(x) if isinstance(x, (int, float)) else x) for k, x in d.items()}
    dados = {'acervo_transcrito': transcrito,
             'proveniencia_transcricao': {'planilha': f'Livro_{pasta}_transcricao.xlsx',
                                          'aba': 'Termos', 'linha': linha,
                                          'pdf': d.get('arquivo_pdf')},
             'nao_consta': nao_consta}
    if folha:
        v['folha'] = folha
    v['dados_json'] = json.dumps(dados, ensure_ascii=False, sort_keys=True, default=str)
    situacao = norm(d.get('tipo_registro'))
    return {'valores': v, 'margem': atos_da_margem(d.get('averbacoes')), 'avisos': avisos,
            'notas_nome': notas_nome, 'nome_bruto': d.get('nome_registrado'),
            'nao_consta': nao_consta, 'numero': numero, 'pdf': d.get('arquivo_pdf'),
            'sem_efeito': bool(re.search(r'\bsem efeito\b|\binutilizad|\bcancelad|\banulad'
                                         r'|\btermo incompleto\b', situacao))}


def qualificacao(texto: str, ctx) -> dict:
    """Nacionalidade, naturalidade, estado civil e profissão escritos na
    qualificação do genitor. Só o que está escrito; o resto fica vazio."""
    t = norm(texto)
    p: dict = {}
    if not t:
        return p
    uf = next((u for k, u in _ADJ_UF.items() if re.search(rf'\b{k}[ae]?s?\b', t)), '')
    if 'brasileir' in t or uf or 'natural deste estado' in t or 'natural de ste estado' in t:
        p['nacionalidade'] = 'brasileira' if re.search(r'brasileira\b|maranhense|\ba \d', t) else 'brasileiro'
    m = re.search(r'natural (?:de|da|do) ([a-z ]{3,40})', t)
    if m and not m[1].startswith(('ste', 'este')):
        mun = ctx.municipios.no_texto(m[1])
        if mun:
            p['naturalidade_cidade'], p['naturalidade_uf'] = mun
    elif re.search(r'natural (?:desta|deste) (?:cidade|municipio)', t):
        p['naturalidade_cidade'], p['naturalidade_uf'] = ctx.municipios.casa
    if not p.get('naturalidade_uf'):
        if uf:
            p['naturalidade_uf'] = uf
        elif re.search(r'natural de ?ste estado|natural deste estado', t):
            p['naturalidade_uf'] = ctx.municipios.casa[1]
    for raiz, saida in _ESTADO_CIVIL:
        mm = re.search(rf'\b{raiz}([ao])s?\b', t)
        if mm:
            p['estado_civil'] = saida + mm[1]
            break
    for prof in _PROFISSOES:
        if re.search(rf'\b{prof}\b', t):
            p['profissao'] = {'domestica': 'doméstica', 'servicos domesticos': 'serviços domésticos',
                              'prendas domesticas': 'prendas domésticas',
                              'funcionario publico': 'funcionário público',
                              'funcionaria publica': 'funcionária pública',
                              'mecanico': 'mecânico', 'autonomo': 'autônomo',
                              'autonoma': 'autônoma'}.get(prof, prof)
            break
    return p


# --------------------------------------------------------------- o banco


class Banco:
    """A fotografia do banco que o gerador precisa. Só lê."""

    def __init__(self, dsn: str, schema: str):
        import psycopg
        from psycopg.rows import dict_row
        con = psycopg.connect(dsn, row_factory=dict_row, autocommit=True,
                              options=f'-c search_path={schema} -c default_transaction_read_only=on')
        cur = con.cursor()
        cfg = {r['key']: r['value'] for r in cur.execute(
            "SELECT key, value FROM settings WHERE key IN ('ri_cns','ri_cidade','ri_uf')")}
        self.cns = re.sub(r'\D', '', cfg.get('ri_cns') or '')
        self.cidade, self.uf = cfg.get('ri_cidade') or '', cfg.get('ri_uf') or ''
        self.municipios = list(cur.execute('SELECT nome, uf FROM ib_municipios'))
        self.assentos = list(cur.execute(
            """SELECT id, numero, livro_volume, nome, matricula, origem, origem_chave,
                      situacao, data_ato, data_fato, hora_fato, ibge_local_nascimento,
                      local_fato_municipio
                 FROM rc_assentos WHERE especie='NASCIMENTO'"""))
        self.pessoas = defaultdict(lambda: defaultdict(list))
        for p in cur.execute(
                """SELECT p.assento_id, p.papel, p.nome, p.sexo, p.naturalidade_cidade, p.idade_no_fato
                     FROM rc_pessoas p JOIN rc_assentos a ON a.id=p.assento_id
                    WHERE a.especie='NASCIMENTO' ORDER BY p.id"""):
            self.pessoas[p['assento_id']][p['papel']].append(p)
        self.naturezas = defaultdict(set)
        for a in cur.execute(
                """SELECT assento_id, tipo, natureza FROM rc_atos
                    WHERE assento_id IN (SELECT id FROM rc_assentos WHERE especie='NASCIMENTO')"""):
            self.naturezas[a['assento_id']].add(a['natureza'] or a['tipo'])
        self.enviados_crc = {r['assento_id'] for r in cur.execute(
            'SELECT DISTINCT assento_id FROM rc_crc_lote_assentos')}
        con.close()


def _nome_lote(nome) -> str:
    """O nome como `rc_acervo_lote` o compara (`pt_schema.normalizar_nome`)."""
    from pt_schema import normalizar_nome
    return normalizar_nome(nome)


def _volume(valor) -> str:
    m = re.fullmatch(r'A\s*[- ]?\s*0*(\d+)', str(valor or '').strip(), re.I)
    return f'A-{int(m[1])}' if m else ''


class Achador:
    """A mesma identificação de `rc_acervo_lote.conferir`, para decidir aqui
    o que será inclusão e o que será complemento — e o nome que vai."""

    def __init__(self, banco: Banco):
        self.b = banco
        self.por_chave = defaultdict(list)
        self.sem_livro = defaultdict(list)
        self.por_numero = defaultdict(list)
        self.impedidas: dict[tuple, dict] = {}
        for e in banco.assentos:
            b = _volume(e['livro_volume'])
            m = MAT.confere(e['matricula']) if e.get('matricula') else {}
            p = m.get('partes') or {}
            if p.get('cns') and len(banco.cns) == 6 and p['cns'] != banco.cns:
                continue
            if m.get('ok') and p.get('livro_tipo') == '1':
                bm = f"A-{int(p['livro'])}"
                if int(p['termo']) != e['numero']:
                    self.impedidas[(bm, int(p['termo']))] = e
                    self.impedidas[(b or bm, e['numero'])] = e
                    continue
                if b and b != bm:
                    self.impedidas[(b, e['numero'])] = e
                    self.impedidas[(bm, e['numero'])] = e
                    continue
                b = b or bm
            self.por_numero[e['numero']].append(e)
            if b:
                self.por_chave[(b, e['numero'])].append(e)
            elif not str(e.get('livro_volume') or '').strip():
                self.sem_livro[e['numero']].append(e)

    def achar(self, v: dict) -> tuple[list[dict], str]:
        """Os assentos que o lote vai complementar, e o motivo de recusa que
        `rc_acervo_lote.conferir` daria (vazio quando não recusa)."""
        chave = (v['livro_volume'], v['numero'])
        if chave in self.impedidas:
            e = self.impedidas[chave]
            return [], (f"o cadastro do sistema contradiz a matrícula neste livro e termo: assento "
                        f"{e['id']} «{e['nome']}» (livro {e['livro_volume'] or '—'}, matrícula "
                        f"{e['matricula']}) — conferir qual é o termo certo")
        ano = (v.get('data_ato') or '')[:4]
        cands = []
        for e in self.por_chave[chave]:
            m = MAT.confere(e['matricula']) if e.get('matricula') else {}
            if m.get('ok') and ano and (m.get('partes') or {}).get('ano') != ano \
                    and _nome_lote(e['nome']) != _nome_lote(v['nome']):
                continue
            cands.append(e)
        if not cands:
            cands = [x for x in self.sem_livro[v['numero']] if _nome_lote(x['nome']) == _nome_lote(v['nome'])]
        if cands:
            return cands, ''
        if self.sem_livro[v['numero']]:
            e = self.sem_livro[v['numero']][0]
            return [], (f"há assento com este termo sem livro e com outro nome: {e['id']} «{e['nome']}»")
        outro = [x for x in self.por_numero[v['numero']] if _nome_lote(x['nome']) == _nome_lote(v['nome'])]
        if outro:
            e = outro[0]
            return [], (f"o mesmo termo e nome estão no sistema em outro livro: assento {e['id']} "
                        f"(livro {e['livro_volume'] or '—'}, matrícula {e['matricula']}) — conferir o volume")
        return [], ''


# --------------------------------------------------------------- complemento


def mesma_pessoa(nome_sistema, nome_teor) -> bool:
    """O assento do sistema é desta pessoa? O prenome decide: a grafia do
    sobrenome muda entre cadastros; o prenome de outro filho, não."""
    a = _tokens(limpar_nome(nome_sistema)[0] or nome_sistema)
    b = _tokens(nome_teor)
    if not a or not b:
        return True
    if a[0] == b[0] or (min(len(a[0]), len(b[0])) > 1 and
                        difflib.SequenceMatcher(None, a[0], b[0]).ratio() >= 0.7):
        return True
    return diferenca_pequena(nome_sistema, nome_teor)


def ajustar_complemento(r: dict, atual: dict, banco: Banco, conferir: list) -> None:
    """O registro que complementa um assento existente: o que fica do sistema.

    - nome (registrado, mãe, pai): vale o teor, salvo diferença pequena;
    - matrícula válida do sistema fica (é a chave na CRC); só a ausente ou
      com dígito errado é trocada;
    - local do nascimento já informado (1/2/3/5) não volta a «ignorado».
    """
    v = r['valores']
    rot = f"{v['livro_volume']} termo {v['numero']}"
    filiacao_averbada = bool(banco.naturezas[atual['id']] & {'reconhecimento_filiacao', 'retificacao'})
    for papel, chave in (('REGISTRADO', 'nome'), ('MAE', None), ('PAI', None)):
        nova = next((p for p in v['pessoas'] if p['papel'] == papel), None)
        if papel == 'REGISTRADO':
            antigo, novo = atual['nome'], v['nome']
        else:
            antigas = banco.pessoas[atual['id']].get(papel) or []
            if not nova or not antigas:
                continue
            antigo, novo = antigas[0]['nome'], nova['nome']
        # O nome do sistema pode vir sujo da carga antiga («X (AV-01: Y)»,
        # «(AV-1) X», «A digo B»): o que se compara, e o que fica, é ele limpo.
        limpo = limpar_nome(antigo)[0] or str(antigo or '').strip()
        teor_incompleto = any('ilegível' in n for n in r.get('notas_nome', {}).get(papel, []))
        if norm(limpo) == norm(novo):
            fica = antigo if norm(antigo) == norm(limpo) else novo
            if fica != antigo:
                conferir.append((rot, papel, 'nome do sistema limpo (nota da carga antiga retirada)',
                                 antigo, fica, atual['id']))
        elif papel == 'REGISTRADO' and banco.naturezas[atual['id']] & {'alteracao_nome'}:
            fica = limpo
            conferir.append((rot, papel, 'nome mantido: há averbação de alteração de nome',
                             antigo, novo, atual['id']))
        elif papel in ('MAE', 'PAI') and filiacao_averbada:
            fica = limpo
            conferir.append((rot, papel, 'filiação do sistema mantida: há averbação de reconhecimento '
                             'ou retificação — conferir', antigo, novo, atual['id']))
        elif teor_incompleto:
            fica = limpo
            conferir.append((rot, papel, 'nome do sistema mantido: o teor tem trecho ilegível no nome',
                             antigo, novo, atual['id']))
        elif diferenca_pequena(limpo, novo):
            fica = limpo
            conferir.append((rot, papel, 'nome do sistema mantido (diferença pequena)',
                             antigo, novo, atual['id']))
        else:
            fica = novo
            conferir.append((rot, papel, 'nome trocado pelo do teor', antigo, novo, atual['id']))
        if papel == 'REGISTRADO' and re.search(
                r'\bAV[- ]?\d|averba|passou a chamar|passar[áa] a chamar|retific',
                f"{antigo} {r.get('nome_bruto') or ''}", re.I):
            conferir.append((rot, papel, 'nome com averbação de alteração/retificação: conferir qual '
                             'nome a ficha mostra (ficou o de nascimento)', antigo,
                             r.get('nome_bruto') or novo, atual['id']))
        if papel == 'REGISTRADO':
            v['nome'] = fica
            for p in v['pessoas']:
                if p['papel'] == 'REGISTRADO':
                    p['nome'] = fica
        else:
            nova['nome'] = fica
    # A idade da mãe gravada como texto («26 anos») a CRC não aceita; quando o
    # teor não a traz, fica o número do que já estava escrito.
    maes = banco.pessoas[atual['id']].get('MAE') or []
    idade_velha = str((maes[0].get('idade_no_fato') if maes else '') or '')
    if idade_velha and not idade_velha.isdigit() and idade_de(idade_velha):
        mae = next((p for p in v['pessoas'] if p['papel'] == 'MAE'), None)
        if mae is None:
            v['pessoas'].append({'papel': 'MAE', 'nome': maes[0]['nome'],
                                 'idade_no_fato': idade_de(idade_velha)})
        elif not mae.get('idade_no_fato'):
            mae['idade_no_fato'] = idade_de(idade_velha)
    m = MAT.confere(atual['matricula']) if atual.get('matricula') else {}
    calculada = v.get('matricula')
    if m.get('ok') and (not calculada or calculada == atual['matricula']):
        v.pop('matricula', None)
    elif m.get('ok'):
        a, b = m['partes'], MAT.partes(calculada)
        o_que = [k for k in ('ano', 'livro', 'folha', 'termo') if a.get(k) != b.get(k)]
        conferir.append((rot, 'MATRÍCULA', 'matrícula corrigida pelo teor (' + ', '.join(o_que) + ')'
                         + (' — já enviada à CRC com a antiga' if atual['id'] in banco.enviados_crc else ''),
                         atual['matricula'], calculada, atual['id']))
    elif atual.get('matricula') and calculada:
        conferir.append((rot, 'MATRÍCULA', 'matrícula do sistema inválida, trocada pela calculada',
                         atual['matricula'], calculada, atual['id']))
    if v.get('ibge_local_nascimento') == IGNORADO_IBGE and atual.get('ibge_local_nascimento') not in (None, ''):
        v.pop('ibge_local_nascimento')


# --------------------------------------------------------------- a saída


def _ligar(origem: Path, destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists():
        return
    try:
        os.link(origem, destino)
    except OSError:
        shutil.copy2(origem, destino)


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open('rb') as f:
        for bloco in iter(lambda: f.read(1 << 20), b''):
            h.update(bloco)
    return h.hexdigest()


def gerar(args) -> dict:
    import openpyxl
    banco = Banco(args.dsn, args.schema)

    class Ctx:
        cns = banco.cns
        municipios = Municipios(banco.municipios, banco.cidade, banco.uf)
    achador = Achador(banco)
    saida, destino = Path(args.saida), Path(args.destino)
    destino.mkdir(parents=True, exist_ok=True)
    # Rodar de novo refaz os manifestos: os de uma rodada anterior (só os
    # arquivos que este gerador escreve) saem, para nenhum índice velho
    # apontar para lote que mudou. Os PDFs ficam — são os mesmos.
    for velho in list(destino.glob('sequencia_*.json')) + list(destino.glob('*/lote_*.json')):
        velho.unlink()
    fora, avisos, conferir, resumo, sequencias = [], [], [], [], defaultdict(list)
    for item in args.livro:
        pasta, livro = item.split('=')
        grupo = 'novos' if pasta in args.novos else 'correcoes'
        planilha = saida / pasta / f'Livro_{pasta}_transcricao.xlsx'
        ws = openpyxl.load_workbook(planilha, read_only=True)['Termos']
        linhas = list(ws.iter_rows(values_only=True))
        cab = linhas[0]
        registros = [montar(dict(zip(cab, r)), livro, pasta, i, Ctx)
                     for i, r in enumerate(linhas[1:], 2) if any(r)]
        repetidos = {n for n, c in Counter(r['numero'] for r in registros).items() if c > 1}
        aceitos, cont = [], Counter()
        for r in registros:
            v = r['valores']
            rot = f"{livro} termo {r['numero']}"
            for a in r['avisos']:
                avisos.append((rot, a, v.get('nome')))
            pdf = saida / pasta / 'registros' / str(r['pdf'] or '')
            motivo = None
            if not r['numero']:
                motivo = 'termo sem número'
            elif r['numero'] in repetidos:
                motivo = 'número de termo repetido no livro: os dois assentos precisam de decisão (o sistema guarda um por livro e termo)'
            elif r['sem_efeito']:
                motivo = 'termo sem efeito / inutilizado / cancelado no papel'
            elif not v['nome']:
                motivo = 'nome do registrado ilegível'
            elif not r['pdf'] or not pdf.is_file():
                motivo = 'PDF do termo não encontrado'
            cands = []
            if not motivo:
                cands, motivo = achador.achar(v)
                motivo = motivo or None
            if not motivo and len(cands) > 1:
                motivo = 'mais de um assento no sistema com este livro e termo'
            if not motivo and cands:
                atual = cands[0]
                if atual['origem'] not in ORIGENS_COMPLEMENTAVEIS or atual['situacao'] != 'ATIVO':
                    motivo = f"assento {atual['id']} lavrado no sistema ou cancelado — usar a ficha"
                elif len((banco.pessoas[atual['id']].get('MAE') or [])) > 1 or \
                        len((banco.pessoas[atual['id']].get('PAI') or [])) > 1 or \
                        len((banco.pessoas[atual['id']].get('REGISTRADO') or [])) > 1:
                    motivo = f"assento {atual['id']} com pessoa repetida no mesmo papel — conferir a ficha"
                elif not mesma_pessoa(atual['nome'], v['nome']):
                    motivo = (f"o assento {atual['id']} do sistema neste livro e termo é de outra pessoa: "
                              f"«{atual['nome']}» — conferir qual termo é o dele (cadastro antigo)")
                else:
                    ajustar_complemento(r, atual, banco, conferir)
                    r['acao'] = 'COMPLEMENTAR'
                    r['assento_id'] = atual['id']
                    r['ja_na_crc'] = atual['id'] in banco.enviados_crc
            elif not motivo:
                r['acao'] = 'INCLUIR'
            if motivo:
                fora.append((rot, motivo, v.get('nome'), r['pdf']))
                cont['fora'] += 1
                continue
            cont[r['acao']] += 1
            r['pdf_caminho'] = pdf
            aceitos.append(r)
        # escrever os lotes do livro
        dlivro = destino / pasta
        for n in range(0, len(aceitos), POR_LOTE):
            bloco = aceitos[n:n + POR_LOTE]
            itens = []
            for r in bloco:
                alvo = dlivro / 'registros' / r['pdf_caminho'].name
                _ligar(r['pdf_caminho'], alvo)
                valores = dict(r['valores'])
                if r['margem']:
                    valores['atos_a_margem'] = r['margem']
                itens.append({'pdf': f'registros/{alvo.name}', 'bytes': alvo.stat().st_size,
                              'sha256': _sha256(alvo), 'valores': valores})
            arq = dlivro / f'lote_{n // POR_LOTE + 1:03d}.json'
            conteudo = json.dumps({'formato': FORMATO, 'versao': 1, 'registros': itens},
                                  ensure_ascii=False, indent=1)
            arq.write_text(conteudo, encoding='utf-8')
            sequencias[grupo].append({'manifesto': f'{pasta}/{arq.name}', 'livro': livro,
                                      'sha256': hashlib.sha256(conteudo.encode('utf-8')).hexdigest()})
        resumo.append((pasta, livro, grupo, len(registros), cont['INCLUIR'], cont['COMPLEMENTAR'],
                       cont['fora'], sum(1 for r in aceitos if r.get('ja_na_crc')),
                       sum(len(r['margem']) for r in aceitos)))
        print(f'{pasta:16} {livro:5} lidos {len(registros):5}  incluir {cont["INCLUIR"]:5}  '
              f'complementar {cont["COMPLEMENTAR"]:5}  fora {cont["fora"]:4}', flush=True)
        for r in aceitos:
            if r.get('ja_na_crc'):
                conferir.append((f"{livro} termo {r['numero']}", 'CRC',
                                 'já enviado à CRC: reenviar depois do complemento',
                                 '', '', r['assento_id']))
    indices = []
    for grupo, lotes in sequencias.items():
        for k in range(0, len(lotes), LOTES_POR_SEQUENCIA):
            nome = f'sequencia_{grupo}_{k // LOTES_POR_SEQUENCIA + 1}.json'
            (destino / nome).write_text(json.dumps(
                {'formato': FORMATO_SEQUENCIA, 'versao': 1,
                 'lotes': lotes[k:k + LOTES_POR_SEQUENCIA]}, ensure_ascii=False, indent=1),
                encoding='utf-8')
            indices.append(nome)
    _planilha(destino / 'conferencia.xlsx', resumo, fora, conferir, avisos)
    return {'indices': indices, 'resumo': resumo, 'fora': len(fora),
            'conferir': len(conferir), 'avisos': len(avisos)}


def _planilha(caminho: Path, resumo, fora, conferir, avisos) -> None:
    import openpyxl
    from openpyxl.styles import Font
    wb = openpyxl.Workbook()
    abas = (('Resumo', ('pasta', 'livro', 'grupo', 'termos lidos', 'incluir', 'complementar',
                        'fora do lote', 'já na CRC (reenviar)', 'atos à margem'), resumo),
            ('Fora do lote', ('livro/termo', 'motivo', 'nome', 'pdf'), fora),
            ('Conferir', ('livro/termo', 'quem', 'o que', 'no sistema', 'no teor', 'assento'), conferir),
            ('Avisos', ('livro/termo', 'aviso', 'nome'), avisos))
    for i, (titulo, cab, linhas) in enumerate(abas):
        ws = wb.active if i == 0 else wb.create_sheet()
        ws.title = titulo
        ws.append(cab)
        for c in ws[1]:
            c.font = Font(bold=True)
        for linha in linhas:
            ws.append(list(linha))
        ws.freeze_panes = 'A2'
    wb.save(caminho)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--saida', required=True, help='pasta com <livro>/Livro_<livro>_transcricao.xlsx')
    ap.add_argument('--destino', required=True)
    ap.add_argument('--dsn', required=True, help='banco para ler (de preferência a réplica)')
    ap.add_argument('--schema', default='producao')
    ap.add_argument('--livro', action='append', required=True, help='pasta=A-n (repetir)')
    ap.add_argument('--novos', action='append', default=[],
                    help='pastas dos livros que ainda não estão no sistema (o resto é correção)')
    args = ap.parse_args(argv)
    r = gerar(args)
    print(json.dumps({k: v for k, v in r.items() if k != 'resumo'}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
