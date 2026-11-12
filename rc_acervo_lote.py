"""Inclusão e complementação do acervo transcrito, pela sessão do sistema."""
from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha256
from pathlib import Path, PureWindowsPath
import json
import re
from datetime import date
from uuid import uuid4

from bd_nativo import banco
import identidade_do_robo as IDR
import importar_padrao as IMP
import rc_digitalizacao as DIG
import rc_matricula as MAT
from pt_schema import normalizar_nome
from storage import hash_file

FORMATO = 'CARTORIO_GESTAO_ACERVO_RCPN_LOTE'
ORIGENS = frozenset({'EOFICIO', 'IMPORTACAO', 'ARQUIVO', 'ACERVO'})
CAMPOS = frozenset({'nome', 'data_ato', 'data_fato', 'matricula', 'dnv',
    'cpf_registrado', 'hora_fato', 'local_fato_nome', 'local_fato_endereco',
    'local_fato_municipio', 'naturalidade_declarada', 'cor_raca', 'teor',
    'teor_formato', 'livro_a_confirmar', 'ibge_local_nascimento', 'ibge_gemeo',
    'registro_tardio', 'gemeo_ordem'})
PESSOA = frozenset({'papel', 'nome', 'sexo', 'data_nascimento',
    'documento_tipo', 'documento_numero', 'documento_orgao', 'idade_no_fato',
    'profissao', 'nacionalidade', 'naturalidade_cidade', 'naturalidade_uf',
    'naturalidade_pais', 'estado_civil', 'endereco', 'bairro', 'cidade', 'uf',
    'cep', 'nome_pos'})


class LoteError(ValueError):
    pass


def _json(valor):
    return json.dumps(valor, ensure_ascii=False, sort_keys=True, default=str)


def volume(valor):
    m = re.fullmatch(r'A\s*[- ]?\s*0*(\d+)', str(valor or '').strip(), re.I)
    return f'A-{int(m[1])}' if m else ''


# O papel antigo não é ato desta casa. A letra é a da espécie (Livro A, B ou C);
# o número é o que está escrito na capa. Origem ARQUIVO: não houve lavratura
# nem selo, e a marca de «assina quem selar» não tem o que assinar.
ORIGEM_DO_PAPEL = 'ARQUIVO'
LETRA_DO_PAPEL = {'NASCIMENTO': 'A', 'CASAMENTO': 'B', 'OBITO': 'C'}
ESPECIES_DO_PAPEL = frozenset(LETRA_DO_PAPEL)
_FOLHA = re.compile(r'^0*(\d+)\s*([vV])?$')
_NOME_DA_ESPECIE = {
    'NASCIMENTO': 'nascimento', 'CASAMENTO': 'casamento', 'OBITO': 'óbito'}


def folha_do_papel(valor) -> str:
    """«48» na frente e «48v» no verso. Só calcula."""
    m = _FOLHA.fullmatch(str(valor if valor is not None else '').strip())
    if not m or int(m.group(1)) < 1:
        raise LoteError(
            'A folha do papel precisa ser o número da folha, com «v» no verso '
            '(exemplo: 48 ou 48v).')
    return f'{int(m.group(1))}{"v" if m.group(2) else ""}'


def livro_do_papel(valor, especie: str) -> str:
    """O volume do papel: A no nascimento, B no casamento, C no óbito.

    «12», «A-12» e «Livro A 12» são o mesmo livro. A letra de outra espécie
    não entra — óbito não se grava no livro de nascimento.
    """
    letra = LETRA_DO_PAPEL.get(str(especie or '').strip().upper())
    if not letra:
        raise LoteError(
            'O livro de papel desta tela é o de nascimento, casamento ou óbito.')
    texto = str(valor or '').strip()
    com_letra = re.fullmatch(
        rf'(?:livro\s+)?{letra}\s*[- ]?\s*0*(\d+)', texto, re.I)
    so_numero = re.fullmatch(r'0*(\d+)', texto)
    achado = com_letra or so_numero
    if not achado or int(achado.group(1)) < 1:
        raise LoteError(
            f'O livro do papel precisa ser o {letra} desta espécie '
            f'(exemplo: {letra}-12 ou 12).')
    return f'{letra}-{int(achado.group(1))}'


def nome_de_quem_inclui(conta: dict, informado: str, mandante: str) -> str:
    """O nome da pessoa que incluiu. Não é a marca de selo pendente.

    Este caminho não sela. «PENDENTE — assina quem selar» ficaria para sempre
    na auditoria, porque não há selo que troque a marca pelo nome de quem
    assinou. Conta de robô registra o responsável humano.
    """
    import nome_humano as NOMEHUM
    if conta.get('eh_robo'):
        candidato = str(mandante or '').strip()
    else:
        candidato = (str(conta.get('full_name') or '').strip()
                     or str(informado or '').strip())
    if NOMEHUM.eh_rotulo_de_maquina(candidato):
        raise LoteError(
            'A inclusão do livro de papel precisa do nome de quem incluiu. '
            'Esta conta não tem nome de pessoa, e não há selo que assine depois.')
    return candidato


def _conta_que_inclui(bd, usuario_id, usuario):
    u = bd.um('SELECT * FROM users WHERE id=%s', (int(usuario_id),))
    if not u or not u['active'] or u['role'] not in ('ADMIN', 'MANAGER', 'USER'):
        raise LoteError('Usuário sem permissão para importar acervo.')
    mandante = usuario
    if u.get('eh_robo'):
        responsavel = bd.um(
            'SELECT * FROM users WHERE id=%s', (u.get('robo_responsavel_id'),))
        if not responsavel or not responsavel['active'] or responsavel.get('eh_robo'):
            raise LoteError('O robô precisa de um responsável humano ativo.')
        mandante = responsavel['full_name']
    return u, mandante, nome_de_quem_inclui(u, usuario, mandante)


def _naturalidade_da_pessoa(pessoa: dict, declarada, titular) -> dict:
    """A ficha mostra `naturalidade_cidade`. O texto «Cidade/UF» e a
    naturalidade declarada do assento vão para essa coluna quando ela está
    vazia. O que já está escrito na pessoa prevalece."""
    import rc_assento as RC
    p = dict(pessoa)
    texto = p.pop('naturalidade', None)
    if (not str(p.get('naturalidade_cidade') or '').strip()
            and str(texto or '').strip()):
        cidade, uf = RC.municipio_da_naturalidade(texto)
        if cidade:
            p['naturalidade_cidade'] = cidade
        if uf and not str(p.get('naturalidade_uf') or '').strip():
            p['naturalidade_uf'] = uf
    papel = str(p.get('papel') or '').strip().upper()
    if (titular and papel == titular
            and not str(p.get('naturalidade_cidade') or '').strip()
            and str(declarada or '').strip()):
        cidade, uf = RC.municipio_da_naturalidade(declarada)
        if cidade:
            p['naturalidade_cidade'] = cidade
        if uf and not str(p.get('naturalidade_uf') or '').strip():
            p['naturalidade_uf'] = uf
    return p


def _promover_folha_tardio_naturalidade(v: dict, especie: str) -> dict:
    """Folha na ficha, tardio na coluna, naturalidade na pessoa.

    Sem ato de registro, a ficha lê a folha em `dados_json`. O tardio que só
    viaja no JSON deixa a coluna vazia. Campo ausente não entra no dicionário:
    na complementação, o que não veio não apaga o que já estava.
    """
    import rc_assento as RC
    try:
        dados = json.loads(v.get('dados_json') or '{}')
    except (ValueError, TypeError) as erro:
        raise LoteError('Dados da transcrição fora do formato JSON.') from erro
    if not isinstance(dados, dict):
        raise LoteError('Os dados da transcrição precisam ser um objeto.')
    bruto_folha = v.pop('folha', None)
    if bruto_folha not in (None, ''):
        dados['folha'] = folha_do_papel(bruto_folha)
    elif dados.get('folha') not in (None, ''):
        dados['folha'] = folha_do_papel(dados.get('folha'))
    trans = (dados.get('acervo_transcrito')
             if isinstance(dados.get('acervo_transcrito'), dict) else {})
    marca = v.get('registro_tardio')
    if marca in (None, ''):
        for fonte in (dados.get('registro_tardio'), dados.get('bitRegistroTardio'),
                      trans.get('registro_tardio') if isinstance(trans, dict) else None):
            if fonte not in (None, ''):
                marca = fonte
                break
    if marca not in (None, '') and RC.e_tardio(marca):
        v['registro_tardio'] = 1
    declarada = (v.get('naturalidade_declarada')
                 or dados.get('naturalidade_declarada')
                 or (trans.get('naturalidade_declarada') if isinstance(trans, dict) else None))
    titular = RC.TITULAR_DA_NATURALIDADE.get(str(especie or '').strip().upper())
    if v.get('pessoas'):
        v['pessoas'] = [
            _naturalidade_da_pessoa(p, declarada, titular) if isinstance(p, dict) else p
            for p in v['pessoas']]
    v['dados_json'] = _json(dados) if dados else (v.get('dados_json') or '{}')
    return v


def _recusar_duplicado(bd, especie: str, livro: str, numero: int) -> None:
    """Livro + termo na mesma espécie é o mesmo assento de papel."""
    linhas = bd.ler(
        """SELECT id, livro_volume, situacao FROM rc_assentos
            WHERE especie=%s AND numero=%s ORDER BY id""",
        (especie, int(numero)))
    for linha in linhas:
        try:
            mesmo = livro_do_papel(linha.get('livro_volume'), especie) == livro
        except LoteError:
            mesmo = False
        if not mesmo:
            continue
        situacao = str(linha.get('situacao') or '').strip()
        extra = '' if situacao == 'ATIVO' else f' (situação {situacao.lower()})'
        raise LoteError(
            f'Já existe um assento de {_NOME_DA_ESPECIE[especie]} no '
            f'Livro {livro}, termo {numero}{extra}. Nada foi incluído.')


def carregar(caminho: Path) -> dict:
    caminho = Path(caminho)
    if caminho.stat().st_size > 20 * 1024 * 1024:
        raise LoteError('O manifesto excede 20 MB. Divida o livro em lotes menores.')
    try:
        conteudo = caminho.read_bytes()
        d = json.loads(conteudo.decode('utf-8'))
    except (ValueError, UnicodeError) as e:
        raise LoteError('O manifesto não é um JSON UTF-8 válido.') from e
    if not isinstance(d, dict) or d.get('formato') != FORMATO or d.get('versao') != 1:
        raise LoteError('Formato de lote de acervo RCPN não reconhecido.')
    if not isinstance(d.get('registros'), list) or not 1 <= len(d['registros']) <= 1500:
        raise LoteError('Cada lote precisa ter de 1 a 1.500 registros.')
    return {'dados': d, 'pasta': caminho.parent.resolve(), 'manifesto': str(caminho.resolve()),
            'sha256': sha256(conteudo).hexdigest()}


def _pdf(lote, item):
    nome = str(item.get('pdf') or '')
    win = PureWindowsPath(nome)
    if not nome or win.drive or nome.startswith(('/', '\\')) or '..' in win.parts:
        raise LoteError('O PDF precisa estar dentro da pasta deste lote.')
    p = (lote['pasta'] / nome).resolve()
    if not p.is_relative_to(lote['pasta']) or p.suffix.lower() != '.pdf':
        raise LoteError('Caminho do PDF fora do lote ou formato diferente de PDF.')
    if not p.is_file() or p.stat().st_size != item.get('bytes'):
        raise LoteError('PDF ausente ou com tamanho diferente do manifesto.')
    if not re.fullmatch('[0-9a-f]{64}', str(item.get('sha256') or '')):
        raise LoteError('Falta o SHA-256 do PDF.')
    with p.open('rb') as f:
        if not f.read(1024).lstrip().startswith(b'%PDF-'):
            raise LoteError('O arquivo indicado não contém um PDF.')
    return p


def _registro(item):
    if not isinstance(item, dict) or not isinstance(item.get('valores'), dict):
        raise LoteError('Registro fora do formato esperado.')
    v = dict(item['valores'])
    if set(v) - CAMPOS - {'livro_volume', 'numero', 'dados_json', 'pessoas', 'folha'}:
        raise LoteError('O registro contém campo não permitido nesta carga.')
    b, n = volume(v.get('livro_volume')), v.get('numero')
    if not b or type(n) is not int or n < 1:
        raise LoteError('Livro A e número de termo precisam estar identificados.')
    if not str(v.get('nome') or '').strip() or not str(v.get('teor') or '').strip():
        raise LoteError('Nome e transcrição integral precisam estar preenchidos.')
    try:
        dados = json.loads(v.get('dados_json') or '{}')
    except (ValueError, TypeError) as e:
        raise LoteError('Dados da transcrição fora do formato JSON.') from e
    if not isinstance(dados, dict):
        raise LoteError('Os dados da transcrição precisam ser um objeto.')
    for campo in ('data_ato', 'data_fato'):
        if v.get(campo):
            try:
                date.fromisoformat(v[campo])
            except (ValueError, TypeError) as erro:
                raise LoteError(f'Data inválida em {campo}.') from erro
    pessoas = []
    for p in v.get('pessoas') or []:
        if isinstance(p, dict) and 'naturalidade' in p:
            p = _naturalidade_da_pessoa(p, '', None)
        pessoas.append(p)
    if v.get('pessoas') is not None:
        v['pessoas'] = pessoas
    for p in v.get('pessoas') or []:
        if not isinstance(p, dict) or set(p) - PESSOA:
            raise LoteError('Pessoa com campo não permitido nesta carga.')
    _promover_folha_tardio_naturalidade(v, 'NASCIMENTO')
    v.update(livro_volume=b, especie='NASCIMENTO', serie='RC_A',
             chave=f'ACERVO_TRANSCRITO:NASCIMENTO:{b}:{n}')
    return v


def conferir(con, lote):
    bd = banco(con)
    existentes = bd.ler('SELECT * FROM rc_assentos ORDER BY id')
    por_chave, sem_livro, por_numero = defaultdict(list), defaultdict(list), defaultdict(list)
    cns = re.sub(r'[^0-9]', '', str(bd.valor("SELECT value FROM settings WHERE key='ri_cns'") or ''))
    impedidas = set()
    for e in existentes:
        if e['especie'] != 'NASCIMENTO':
            continue
        b = volume(e.get('livro_volume'))
        m = MAT.confere(e.get('matricula')) if e.get('matricula') else {}
        p = m.get('partes') or {}
        # A matrícula identifica também o cartório. Não misturar acervo de
        # outra serventia só porque livro e termo coincidem.
        if len(cns) == 6 and p.get('cns') and p['cns'] != cns:
            continue
        if m.get('ok') and len(cns) == 6 and p.get('cns') == cns and p.get('livro_tipo') == '1':
            b_matricula = f"A-{int(p['livro'])}"
            if int(p['termo']) != e['numero']:
                impedidas.add((b_matricula, int(p['termo'])))
                impedidas.add((b or b_matricula, e['numero']))
                continue
            if not b:
                b = b_matricula
            elif b != b_matricula:
                impedidas.add((b, e['numero']))
                impedidas.add((b_matricula, e['numero']))
                continue
        por_numero[e['numero']].append(e)
        if b:
            por_chave[(b, e['numero'])].append(e)
        elif not str(e.get('livro_volume') or '').strip():
            sem_livro[e['numero']].append(e)
    entradas, recusados = [], []
    for linha, item in enumerate(lote['dados']['registros'], 1):
        try:
            v = _registro(item)
            p = _pdf(lote, item)
            entradas.append({'linha': linha, 'item': item, 'valores': v, 'pdf': p})
        except (LoteError, OSError) as e:
            recusados.append({'linha': linha, 'porque': str(e)})
    quantas = Counter((e['valores']['livro_volume'], e['valores']['numero']) for e in entradas)
    aceitos, vistos = [], set()
    estado = []
    for e in entradas:
        v = e['valores']; chave = (v['livro_volume'], v['numero'])
        motivo = None
        candidatos = por_chave[chave]
        if not candidatos:
            candidatos = [x for x in sem_livro[v['numero']]
                          if normalizar_nome(x['nome']) == normalizar_nome(v['nome'])]
        if chave in impedidas:
            motivo = 'Livro ou termo do cadastro contradiz a matrícula. Conferir a identificação antes de complementar.'
        elif quantas[chave] > 1:
            motivo = 'Livro e termo repetidos no lote: conferir os dois originais.'
        elif len(candidatos) > 1:
            motivo = 'Mais de um assento corresponde a este livro e termo.'
        elif candidatos:
            atual = candidatos[0]
            if atual['id'] in vistos:
                motivo = 'Dois registros do lote apontam para o mesmo assento.'
            elif atual['origem'] not in ORIGENS or atual['situacao'] != 'ATIVO':
                motivo = 'Assento lavrado no sistema ou cancelado: use a ficha própria.'
            else:
                e['atual'] = atual
                vistos.add(atual['id'])
                estado.append(atual)
        elif sem_livro[v['numero']]:
            motivo = 'Há assento com este termo sem volume e com nome diferente. Conferir antes de incluir.'
        elif any(normalizar_nome(x['nome']) == normalizar_nome(v['nome'])
                 for x in por_numero[v['numero']]):
            motivo = 'O mesmo termo e nome aparecem em outro livro. Conferir o volume.'
        if motivo:
            recusados.append({'linha': e['linha'], 'livro': chave[0], 'numero': chave[1], 'porque': motivo})
        else:
            e['acao'] = 'COMPLEMENTAR' if e.get('atual') else 'INCLUIR'
            aceitos.append(e)
    # O importador nativo confere também campos, datas e papéis das pessoas.
    if aceitos:
        arquivo = _json({'formato': IMP.FORMATO, 'versao': IMP.VERSAO,
                         'especie': 'RCPN_ASSENTO', 'registros': [e['valores'] for e in aceitos]})
        q = IMP.conferir(con, arquivo)
        ruins = {r['linha']: r['porque'] for r in q['recusados']}
        for n, e in enumerate(aceitos, 1):
            if n in ruins:
                recusados.append({'linha': e['linha'], 'porque': ruins[n]})
        aceitos = [e for n, e in enumerate(aceitos, 1) if n not in ruins]
    ids = [e['atual']['id'] for e in aceitos if e.get('atual')]
    if ids:
        pessoas = bd.ler('SELECT * FROM rc_pessoas WHERE assento_id=ANY(%s) ORDER BY id', (ids,))
        estado.append(pessoas)
        contagem = Counter((p['assento_id'], p['papel']) for p in pessoas)
        com_duplicados = {e['atual']['id'] for e in aceitos if e.get('atual')
                          and any(contagem[(e['atual']['id'], p['papel'])] > 1
                                  for p in e['valores'].get('pessoas', []))}
        for e in aceitos:
            if e.get('atual', {}).get('id') in com_duplicados:
                recusados.append({'linha': e['linha'], 'porque':'Há pessoas repetidas no mesmo papel; conferir a ficha antes de complementar.'})
        aceitos = [e for e in aceitos if e.get('atual', {}).get('id') not in com_duplicados]
    estado.append([{'id': x['id'], 'livro': x.get('livro_volume'), 'numero': x['numero'],
                    'nome': x['nome'], 'origem': x['origem']} for x in existentes])
    assinatura = sha256(_json([lote['sha256'], estado]).encode()).hexdigest()
    return {'aceitos': aceitos, 'recusados': recusados,
            'incluir': sum(e['acao'] == 'INCLUIR' for e in aceitos),
            'complementar': sum(e['acao'] == 'COMPLEMENTAR' for e in aceitos),
            'lidos': len(lote['dados']['registros']), 'assinatura': assinatura}


def aplicar(con, lote, *, assinatura, raiz, usuario_id, usuario, agora):
    bd = banco(con)
    u, mandante, quem = _conta_que_inclui(bd, usuario_id, usuario)
    bd.valor("SELECT pg_advisory_xact_lock(hashtextextended('rc_acervo_lote', 0))")
    q = conferir(con, lote)
    if assinatura != q['assinatura']:
        raise LoteError('O acervo mudou depois da prévia. Confira novamente antes de importar.')
    if not q['aceitos']:
        raise LoteError('Nenhum registro aprovado para este lote.')
    for e in q['aceitos']:
        if hash_file(e['pdf']) != e['item']['sha256']:
            raise LoteError(f"O PDF da linha {e['linha']} mudou depois da preparação.")
    ids = [e['atual']['id'] for e in q['aceitos'] if e.get('atual')]
    if ids:
        bd.ler('SELECT id FROM rc_assentos WHERE id=ANY(%s) ORDER BY id FOR UPDATE', (ids,))
    # Reconfere sob a trava das linhas para não substituir edição concorrente.
    if conferir(con, lote)['assinatura'] != assinatura:
        raise LoteError('Um assento foi alterado durante a conferência. Confira novamente.')
    antes = {'manifesto': lote['manifesto'], 'sha256': lote['sha256'], 'por': quem,
             'em': agora, 'assentos': [e['atual'] for e in q['aceitos'] if e.get('atual')],
             'pessoas': bd.ler('SELECT * FROM rc_pessoas WHERE assento_id=ANY(%s) ORDER BY id', (ids,)) if ids else []}
    pasta = Path(raiz) / 'rc' / 'acervo_lotes' / lote['sha256']
    pasta.mkdir(parents=True, exist_ok=True)
    backup = pasta / f'antes-{re.sub(r"[^0-9]", "", agora)}-{uuid4().hex}.json'
    with backup.open('x', encoding='utf-8') as f:
        f.write(_json(antes))
    novos = [e['valores'] for e in q['aceitos'] if e['acao'] == 'INCLUIR']
    if novos:
        feito = IMP.importar(con, _json({'formato': IMP.FORMATO, 'versao': IMP.VERSAO,
                    'especie': 'RCPN_ASSENTO', 'registros': novos}), agora=agora, por=quem,
                    origem=ORIGEM_DO_PAPEL)
        if feito['entraram'] != len(novos):
            raise LoteError('O acervo mudou: nem todos os novos assentos puderam ser incluídos.')
    resultados = []
    for e in q['aceitos']:
        v = e['valores']; atual = e.get('atual')
        if atual:
            aid = atual['id']
            alterados = {k: v[k] for k in CAMPOS if v.get(k) not in (None, '')}
            alterados['livro_volume'] = v['livro_volume']
            # O lote antigo gravava IMPORTACAO. A transcrição do papel é ARQUIVO:
            # não houve lavratura. EOFICIO e ACERVO continuam com a origem que
            # a carga deles já tinha.
            if atual.get('origem') == 'IMPORTACAO':
                alterados['origem'] = ORIGEM_DO_PAPEL
            try:
                dados = json.loads(atual.get('dados_json') or '{}')
            except ValueError as erro:
                raise LoteError(f'Assento {aid} com dados JSON inválidos; conferir pela ficha.') from erro
            dados.update(json.loads(v.get('dados_json') or '{}'))
            alterados['dados_json'] = _json(dados)
            cols = sorted(alterados)
            bd.escrever('UPDATE rc_assentos SET ' + ', '.join(f'{c}=%s' for c in cols)
                         + ' WHERE id=%s', [alterados[c] for c in cols] + [aid])
            for p in v.get('pessoas') or []:
                antigas = bd.ler('SELECT * FROM rc_pessoas WHERE assento_id=%s AND papel=%s ORDER BY id FOR UPDATE', (aid, p['papel']))
                if len(antigas) > 1:
                    raise LoteError(f"Assento {aid} com mais de uma pessoa no papel {p['papel']}; conferir na ficha.")
                valores = {k: x for k, x in p.items() if x not in (None, '')}
                valores['nome_norm'] = normalizar_nome(p['nome'])
                cols = sorted(valores)
                if antigas:
                    if antigas[0].get('origem') == 'IMPORTACAO':
                        valores['origem'] = ORIGEM_DO_PAPEL
                        cols = sorted(valores)
                    bd.escrever('UPDATE rc_pessoas SET ' + ', '.join(f'{c}=%s' for c in cols) + ' WHERE id=%s',
                                [valores[c] for c in cols] + [antigas[0]['id']])
                else:
                    valores.update(assento_id=aid, ordem=1, criado_em=agora, origem=ORIGEM_DO_PAPEL,
                                   origem_chave=f"{v['chave']}:{p['papel']}:complemento")
                    cols = sorted(valores)
                    bd.escrever('INSERT INTO rc_pessoas (' + ', '.join(cols) + ') VALUES (' + ', '.join(['%s']*len(cols)) + ')', [valores[c] for c in cols])
        else:
            aid = bd.valor(
                "SELECT id FROM rc_assentos WHERE origem=%s AND origem_chave=%s",
                (ORIGEM_DO_PAPEL, v['chave']))
        # A transcrição é a fonte escolhida pelo solicitante; o PDF anterior é preservado.
        digi = DIG.anexar_digitalizacao(con, aid, e['pdf'], quem,
                  raiz_arquivos=raiz, agora=agora, agente='importação de acervo RCPN pela tela',
                  a_mando_de=mandante, preservar_arquivo_atual=True)
        if digi['sha256'] != e['item']['sha256']:
            raise LoteError('O PDF mudou durante a cópia. O lote foi desfeito; confira o arquivo.')
        IDR.registrar(con, ts=agora, user_id=int(usuario_id), username=quem,
            action='RCPN_ACERVO_TRANSCRITO', entity_type='rc_assentos', entity_id=aid,
            details={'acao':e['acao'], 'manifesto_sha256':lote['sha256'], 'linha':e['linha'],
                     'backup':str(backup), 'transcricao_prevalece':True, 'digitalizacao':digi['acao']})
        resultados.append({'id':aid, 'acao':e['acao'], 'livro':v['livro_volume'], 'numero':v['numero']})
    return {'incluir':q['incluir'], 'complementar':q['complementar'], 'recusados':q['recusados'],
            'resultados':resultados, 'backup':str(backup), 'sha256':lote['sha256']}


def incluir_avulso(con, *, especie: str, livro, folha, termo, nome: str,
                   usuario_id, agora: str, extras: dict | None = None,
                   pessoas: list | None = None, usuario: str = '') -> dict:
    """Grava um assento de livro de papel, sem lavrar e sem selo.

    É a mesma inclusão do lote (origem ARQUIVO, livro e termo do papel, sem
    avançar `nu_numeracao`), para um registro digitado na tela. Não cria ato
    de REGISTRO: sem ato não há selo nem numeração da casa.
    """
    import rc_assento as RC
    bd = banco(con)
    _conta, _mandante, quem = _conta_que_inclui(bd, usuario_id, usuario)
    especie = str(especie or '').strip().upper()
    livro_n = livro_do_papel(livro, especie)
    folha_n = folha_do_papel(folha)
    try:
        numero = int(str(termo).strip())
    except (TypeError, ValueError):
        numero = 0
    if numero < 1:
        raise LoteError(
            'O termo do papel precisa ser o número escrito no livro.')
    nome_limpo = str(nome or '').strip()
    if not nome_limpo:
        raise LoteError(
            'Informe o nome de quem é o assento, como está no papel.')
    bd.valor("SELECT pg_advisory_xact_lock(hashtextextended('rc_acervo_lote', 0))")
    _recusar_duplicado(bd, especie, livro_n, numero)
    valores = {
        'especie': especie,
        'serie': RC.SERIE_DA_ESPECIE[especie],
        'livro_volume': livro_n,
        'numero': numero,
        'nome': nome_limpo,
        'chave': f'PAPEL:{especie}:{livro_n}:{numero}',
        'dados_json': '{}',
        'pessoas': [dict(p) for p in (pessoas or [])],
    }
    for chave, valor in (extras or {}).items():
        if chave in CAMPOS and valor not in (None, ''):
            valores[chave] = valor
    valores['folha'] = folha_n
    _promover_folha_tardio_naturalidade(valores, especie)
    try:
        feito = IMP.importar(
            con, _json({'formato': IMP.FORMATO, 'versao': IMP.VERSAO,
                        'especie': 'RCPN_ASSENTO', 'registros': [valores]}),
            agora=agora, por=quem, origem=ORIGEM_DO_PAPEL)
    except IMP.ImportacaoError as erro:
        raise LoteError(str(erro)) from erro
    if feito.get('entraram') != 1:
        recusa = (feito.get('recusados') or [None])[0]
        if recusa and recusa.get('porque'):
            raise LoteError(recusa['porque'])
        raise LoteError(
            f'Já existe um assento de {_NOME_DA_ESPECIE[especie]} no '
            f'Livro {livro_n}, termo {numero}. Nada foi incluído.')
    aid = bd.valor(
        "SELECT id FROM rc_assentos WHERE origem=%s AND origem_chave=%s",
        (ORIGEM_DO_PAPEL, valores['chave']))
    IDR.registrar(
        con, ts=agora, user_id=int(usuario_id), username=quem,
        action='RCPN_ACERVO_PAPEL', entity_type='rc_assentos', entity_id=aid,
        details={'especie': especie, 'livro': livro_n, 'folha': folha_n,
                 'termo': numero, 'sem_selo': True, 'sem_lavratura': True})
    return {'id': aid, 'livro': livro_n, 'folha': folha_n, 'numero': numero,
            'quem': quem}
