"""Execução de blocos do acervo no servidor, com autoria e recibos por bloco."""
from __future__ import annotations

from pathlib import Path, PureWindowsPath
from threading import Thread
from uuid import uuid4
import json
import os

import rc_acervo_lote as L
import rc_digitalizacao as D
from storage import hash_file

FORMATO = 'CARTORIO_GESTAO_ACERVO_RCPN_SEQUENCIA'


def carregar(caminho):
    p=Path(caminho)
    if p.stat().st_size>1024*1024:
        raise L.LoteError('O índice da sequência excede 1 MB.')
    dados=json.loads(p.read_text(encoding='utf-8'))
    if not isinstance(dados,dict) or dados.get('formato')!=FORMATO or dados.get('versao')!=1:
        raise L.LoteError('Índice de sequência não reconhecido.')
    entradas=dados.get('lotes')
    if not isinstance(entradas,list) or not 1<=len(entradas)<=150:
        raise L.LoteError('A sequência precisa conter de 1 a 150 blocos.')
    vistos=set();lotes=[]
    for e in entradas:
        if not isinstance(e,dict):
            raise L.LoteError('Bloco da sequência fora do formato esperado.')
        nome=str(e.get('manifesto') or '')
        w=PureWindowsPath(nome)
        if w.drive or nome.startswith(('/', '\\')) or '..' in w.parts:
            raise L.LoteError('Manifesto fora da pasta da sequência.')
        alvo=(p.parent/nome).resolve()
        if not alvo.is_relative_to(p.parent.resolve()):
            raise L.LoteError('Manifesto fora da pasta da sequência.')
        if alvo in vistos:
            raise L.LoteError('Manifesto repetido na sequência.')
        vistos.add(alvo)
        lote=L.carregar(alvo)
        if lote['sha256']!=e.get('sha256'):
            raise L.LoteError('Um manifesto mudou depois da preparação. Confira o índice.')
        lotes.append({'manifesto':str(alvo),'sha256':lote['sha256'],
                      'registros':len(lote['dados']['registros']), 'livro':str(e.get('livro') or '')})
    return {'lotes':lotes, 'registros':sum(l['registros'] for l in lotes)}


def _pasta(db,identificador):
    if len(identificador)!=32 or any(c not in '0123456789abcdef' for c in identificador):
        raise L.LoteError('Identificador da execução inválido.')
    return D.raiz_arquivos(db)/'rc'/'acervo_lotes'/'execucoes'/identificador


def _salvar(p,dados):
    p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_name(p.name+'.tmp')
    tmp.write_text(json.dumps(dados,ensure_ascii=False,indent=2),encoding='utf-8')
    os.replace(tmp,p)


def estado(db,identificador):
    return json.loads((_pasta(db,identificador)/'andamento.json').read_text(encoding='utf-8'))


def executar(db,identificador):
    p=_pasta(db,identificador)/'andamento.json'
    d=json.loads(p.read_text(encoding='utf-8'))
    try:
        for n,item in enumerate(d['lotes'],1):
            d.update(atual=n,livro_atual=item['livro']);_salvar(p,d)
            lote=L.carregar(Path(item['manifesto']))
            if lote['sha256']!=item['sha256']:
                raise L.LoteError('O manifesto mudou durante a execução.')
            recibo=D.raiz_arquivos(db)/'rc'/'acervo_lotes'/lote['sha256']/'resultado.json'
            if recibo.is_file():
                resultado=json.loads(recibo.read_text(encoding='utf-8'))
                if resultado.get('sha256')!=lote['sha256']:
                    raise L.LoteError('O recibo não corresponde ao manifesto deste bloco.')
                reaproveitado=True
            else:
                with db.transaction() as con:
                    q=L.conferir(con,lote)
                    resultado=L.aplicar(con,lote,assinatura=q['assinatura'],
                        raiz=D.raiz_arquivos(db),usuario_id=d['usuario_id'],usuario=d['usuario'],agora=db.now())
                _salvar(recibo,resultado)
                reaproveitado=False
            d['resultados'].append({'livro':item['livro'],'manifesto':item['manifesto'],
                'sha256':lote['sha256'],'incluidos':resultado['incluir'],
                'complementados':resultado['complementar'],'recusados':resultado['recusados'],
                'recibo_anterior':reaproveitado})
            d['incluidos']+=resultado['incluir'];d['complementados']+=resultado['complementar']
            d['recusados']+=len(resultado['recusados']);d['concluidos']=n
            _salvar(p,d)
        d['situacao']='CONCLUIDA'
    except Exception as exc:
        d['situacao']='INTERROMPIDA'
        d['erro']='O bloco atual não foi confirmado ou seu recibo precisa ser conferido. Os recibos dos blocos anteriores foram preservados. '+(str(exc) if isinstance(exc,L.LoteError) else type(exc).__name__)
    finally:
        d['atualizado_em']=db.now();_salvar(p,d)


def iniciar(db,indice,*,usuario_id,usuario):
    identificador=uuid4().hex
    d={'id':identificador,'situacao':'EM_EXECUCAO','usuario_id':int(usuario_id),'usuario':usuario,
       'lotes':indice['lotes'],'total':len(indice['lotes']),'concluidos':0,'atual':0,
       'incluidos':0,'complementados':0,'recusados':0,'resultados':[],'criado_em':db.now()}
    _salvar(_pasta(db,identificador)/'andamento.json',d)
    Thread(target=executar,args=(db,identificador),name='rcpn-acervo-'+identificador[:8],daemon=True).start()
    return identificador
