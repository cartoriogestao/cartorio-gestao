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
    'cpf_registrado', 'hora_fato', 'local_fato_nome', 'naturalidade_declarada',
    'cor_raca', 'teor', 'teor_formato', 'livro_a_confirmar'})
PESSOA = frozenset({'papel', 'nome', 'sexo', 'data_nascimento',
    'documento_tipo', 'documento_numero', 'idade_no_fato'})


class LoteError(ValueError):
    pass


def _json(valor):
    return json.dumps(valor, ensure_ascii=False, sort_keys=True, default=str)


def volume(valor):
    m = re.fullmatch(r'A\s*[- ]?\s*0*(\d+)', str(valor or '').strip(), re.I)
    return f'A-{int(m[1])}' if m else ''


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
    if set(v) - CAMPOS - {'livro_volume', 'numero', 'dados_json', 'pessoas'}:
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
    for p in v.get('pessoas') or []:
        if not isinstance(p, dict) or set(p) - PESSOA:
            raise LoteError('Pessoa com campo não permitido nesta carga.')
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
    u = bd.um('SELECT * FROM users WHERE id=%s', (int(usuario_id),))
    if not u or not u['active'] or u['role'] not in ('ADMIN', 'MANAGER', 'USER'):
        raise LoteError('Usuário sem permissão para importar acervo.')
    mandante = usuario
    if u.get('eh_robo'):
        responsavel = bd.um('SELECT * FROM users WHERE id=%s', (u.get('robo_responsavel_id'),))
        if not responsavel or not responsavel['active'] or responsavel.get('eh_robo'):
            raise LoteError('O robô precisa de um responsável humano ativo.')
        mandante = responsavel['full_name']
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
    antes = {'manifesto': lote['manifesto'], 'sha256': lote['sha256'], 'por': usuario,
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
                    'especie': 'RCPN_ASSENTO', 'registros': novos}), agora=agora, por=usuario)
        if feito['entraram'] != len(novos):
            raise LoteError('O acervo mudou: nem todos os novos assentos puderam ser incluídos.')
    resultados = []
    for e in q['aceitos']:
        v = e['valores']; atual = e.get('atual')
        if atual:
            aid = atual['id']
            alterados = {k: v[k] for k in CAMPOS if v.get(k) not in (None, '')}
            alterados['livro_volume'] = v['livro_volume']
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
                    bd.escrever('UPDATE rc_pessoas SET ' + ', '.join(f'{c}=%s' for c in cols) + ' WHERE id=%s',
                                [valores[c] for c in cols] + [antigas[0]['id']])
                else:
                    valores.update(assento_id=aid, ordem=1, criado_em=agora, origem='IMPORTACAO',
                                   origem_chave=f"{v['chave']}:{p['papel']}:complemento")
                    cols = sorted(valores)
                    bd.escrever('INSERT INTO rc_pessoas (' + ', '.join(cols) + ') VALUES (' + ', '.join(['%s']*len(cols)) + ')', [valores[c] for c in cols])
        else:
            aid = bd.valor("SELECT id FROM rc_assentos WHERE origem='IMPORTACAO' AND origem_chave=%s", (v['chave'],))
        # A transcrição é a fonte escolhida pelo solicitante; o PDF anterior é preservado.
        digi = DIG.anexar_digitalizacao(con, aid, e['pdf'], usuario,
                  raiz_arquivos=raiz, agora=agora, agente='importação de acervo RCPN pela tela',
                  a_mando_de=mandante, preservar_arquivo_atual=True)
        if digi['sha256'] != e['item']['sha256']:
            raise LoteError('O PDF mudou durante a cópia. O lote foi desfeito; confira o arquivo.')
        IDR.registrar(con, ts=agora, user_id=int(usuario_id), username=usuario,
            action='RCPN_ACERVO_TRANSCRITO', entity_type='rc_assentos', entity_id=aid,
            details={'acao':e['acao'], 'manifesto_sha256':lote['sha256'], 'linha':e['linha'],
                     'backup':str(backup), 'transcricao_prevalece':True, 'digitalizacao':digi['acao']})
        resultados.append({'id':aid, 'acao':e['acao'], 'livro':v['livro_volume'], 'numero':v['numero']})
    return {'incluir':q['incluir'], 'complementar':q['complementar'], 'recusados':q['recusados'],
            'resultados':resultados, 'backup':str(backup), 'sha256':lote['sha256']}
