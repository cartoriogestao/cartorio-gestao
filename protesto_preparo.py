"""Preenchimento do protesto e comprovantes na ficha; nao lavra atos."""
from __future__ import annotations
import json
from bd_nativo import banco
import rascunho_de_tela as RASC
import protesto_prova as PROVA
import protesto_aviso as AV

TELA = 'protesto_titulo'
CAMPOS = ('motivo_atraso', 'afirmacao', 'afirmacao_prova',
          'afirmacao_cenprot', 'afirmacao_irmaos', 'afirmacao_selo')


def chave(titulo_id, usuario_id):
    return f'protesto:{int(titulo_id)}:usuario:{int(usuario_id)}'


def ler(con, titulo_id, usuario_id):
    if not usuario_id:
        return None
    linha = banco(con).um(
        'SELECT id FROM rascunhos_de_tela WHERE tela=%s AND chave=%s ORDER BY id DESC LIMIT 1',
        (TELA, chave(titulo_id, usuario_id)))
    return RASC.ler(con, linha['id']) if linha else None


def salvar(con, titulo_id, usuario_id, dados, *, agora, por):
    titulo = banco(con).um('SELECT numero_titulo,situacao FROM pt_titulos WHERE id=%s', (int(titulo_id),))
    if not titulo or titulo['situacao'] != 'INTIMADO':
        raise RASC.RascunhoError('O preenchimento do protesto so se salva para titulo intimado.')
    if not usuario_id:
        raise RASC.RascunhoError('Entre com seu usuario para salvar o preenchimento.')
    campos = {k: str(dados.get(k) or '') for k in CAMPOS}
    if any(len(v) > 10000 for v in campos.values()):
        raise RASC.RascunhoError('Cada texto pode ter no maximo 10000 caracteres.')
    if not any(v.strip() for v in campos.values()):
        raise RASC.RascunhoError('Preencha um motivo ou uma afirmacao antes de salvar.')
    # Caixas de confirmacao nao se guardam: a pessoa as marca ao lancar.
    atual = ler(con, titulo_id, usuario_id)
    return RASC.salvar(con, tela=TELA, chave=chave(titulo_id, usuario_id),
                       dados={'ato': 'PROTESTO', **campos},
                       titulo=f'Protesto {titulo["numero_titulo"]} - preenchimento',
                       agora=agora, por=por, rascunho_id=atual['id'] if atual else None)


def concluir(con, titulo_id, usuario_id, preparo_id, *, agora, por, endereco):
    atual = ler(con, titulo_id, usuario_id)
    if atual and str(atual['id']) == str(preparo_id or ''):
        RASC.virou_ato(con, atual['id'], endereco=endereco, agora=agora, por=por)
        return atual['id']
    return None


def edital_da_ficha(con, titulo_id, prova):
    if not prova or prova.get('modo') != 'EDITAL' or not prova.get('intimacao_id'):
        return None
    bd = banco(con)
    ato = bd.um('SELECT detalhe_json FROM pt_atos WHERE id=%s AND titulo_id=%s',
                (prova['intimacao_id'], int(titulo_id)))
    if not ato:
        return None
    try:
        detalhe = json.loads(ato['detalhe_json'] or '{}')
    except (TypeError, ValueError):
        detalhe = {}
    edital = PROVA._edital_da_intimacao(bd, titulo_id, prova['intimacao_id'], detalhe)
    if not edital:
        return None
    edital['anexos'] = bd.ler(
        'SELECT id,original_name,uploaded_at FROM attachments WHERE entity_type=%s AND entity_id=%s ORDER BY id',
        (AV.ENTIDADE_DO_ENVIO_DO_EDITAL, edital['id']))
    return edital
