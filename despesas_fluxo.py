"""Leitura assistida e correcao auditada de despesas ainda nao pagas. Sem rede."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from typing import Any

import cpf_cnpj
import despesas as DP
import identidade_do_robo as IDR
from bd_nativo import banco

CAMPOS = ('forma', 'codigo', 'codigo_barras', 'valor', 'vencimento',
          'beneficiario_nome', 'beneficiario_documento')


def ler_codigo(codigo: Any, *, hoje: date) -> dict:
    """Dados contidos no codigo, nunca uma consulta ou ordem ao banco."""
    texto = str(codigo or '').strip()
    if not texto or len(texto) > 4096:
        raise DP.DespesaError('Cole o codigo completo, com ate 4096 caracteres.')
    if texto.startswith('000201'):
        lido = DP.ler_pix_copia_e_cola(texto)
        forma = DP.PIX_COPIA_E_COLA
        valor = lido['valor_centavos']
        datas = []
        aviso = ('Este Pix e dinamico: o valor da cobranca nao esta no texto. '
                 'Confira o valor na fatura; o banco ainda vai valida-lo.'
                 if lido['dinamico'] and valor is None else
                 'Confira o favorecido e o valor na fatura antes de autorizar.')
    elif len(DP.digitos(texto)) in (44, 47, 48) and '@' not in texto:
        lido = DP.ler_codigo_de_barras(texto)
        forma, valor, datas = lido['tipo'], lido['valor_centavos'], lido['vencimentos']
        aviso = 'Confira o vencimento na fatura. Esta leitura nao consulta o titulo registrado no banco.'
    else:
        DP.normalizar_chave_pix(texto)
        forma, valor, datas = DP.PIX_CHAVE, None, []
        aviso = 'Informe e confira o CPF/CNPJ e o nome do favorecido. Ler a chave nao identifica seu titular no banco.'
    sugestao = min(datas, key=lambda d: abs((date.fromisoformat(d) - hoje).days)) if datas else ''
    return {'forma': forma, 'forma_nome': DP.FORMAS[forma],
            'valor': DP.reais(valor) if valor is not None else '',
            'vencimento': sugestao, 'aviso': aviso}


def revisao(d: dict) -> str:
    """Detecta formulario antigo; autorizacao e estado bancario tambem contam."""
    campos = ('id', *CAMPOS, 'situacao', 'autorizada_em', 'autorizada_por',
              'acima_do_teto', 'enviada_em', 'tentativas', 'banco_codigo',
              'banco_e2e', 'banco_status', 'paga_em', 'extrato_id')
    return hashlib.sha256(json.dumps({k: d.get(k) for k in campos},
                                    sort_keys=True, default=str).encode()).hexdigest()


def pode_corrigir(d: dict) -> bool:
    """Resposta incerta ou referencia bancaria exige consulta, nunca novo envio."""
    if d.get('situacao') not in (DP.AGUARDANDO, DP.AUTORIZADA, DP.FALHOU):
        return False
    if d.get('forma') == DP.MANUAL or d.get('banco_codigo') or d.get('banco_e2e'):
        return False
    if d.get('paga_em') or d.get('extrato_id'):
        return False
    status = d.get('banco_status') or ''
    if status not in ('', 'RECUSADO'):
        return False
    if not (d.get('tentativas') or d.get('enviada_em')):
        return True
    # RECUSADO tambem pode esconder conflito/duplicidade. So as recusas de
    # validacao conhecidas sao recuperadas aqui; o resto exige conferencia.
    mensagem = str(d.get('mensagem') or '').lower()
    return status == 'RECUSADO' and any(p in mensagem for p in (
        'data de vencimento', 'pixp123', 'dct29', 'chave em formato inv',
    ))


def conferir_revisao(con, despesa_id: int, versao: str) -> None:
    d = DP._prender(banco(con), despesa_id)
    if not versao or versao != revisao(d):
        raise DP.DespesaError('Os dados da despesa mudaram ou a tela e antiga. Recarregue e confira favorecido, codigo, valor e vencimento antes de autorizar.')


def orientacao(d: dict) -> str:
    status = str(d.get('banco_status') or '').upper()
    msg = str(d.get('mensagem') or '').lower()
    if d.get('situacao') == DP.ENVIADA:
        if status == 'AGENDADO':
            return ('Pagamento agendado no banco para ' + DP._br(str(d.get('data_pagamento') or d['vencimento']))
                    + '. Ainda nao e pagamento confirmado. Consulte o andamento; nao cadastre outra despesa para pagar de novo.')
        return 'O banco ja recebeu a solicitacao ou ainda pode processa-la. Consulte o andamento e o extrato antes de qualquer nova tentativa.'
    if 'vencimento' in msg and d.get('situacao') == DP.FALHOU:
        return ('Confira o vencimento na fatura e no codigo. Se os dois estao certos, peca ao emissor um boleto atualizado ou o Pix da mesma fatura. '
                'Nao troque a data por tentativa. Use Corrigir dados do pagamento para manter a mesma despesa e seu historico.')
    if 'pixp123' in msg or ('valor' in msg and ('qrcode' in msg or 'qr code' in msg)):
        return ('O valor informado difere do cobrado pelo QR Code. No Pix dinamico esse valor pode nao estar no texto copiado. '
                'Confira a fatura e corrija o valor nesta mesma despesa; sera necessaria nova autorizacao.')
    if d.get('situacao') == DP.FALHOU and pode_corrigir(d):
        return 'O banco recusou a solicitacao. Confira o motivo abaixo e corrija os dados nesta mesma despesa, sem cancelar e cadastrar tudo de novo.'
    if d.get('situacao') == DP.FALHOU:
        return 'Confira o resultado no banco e no extrato antes de tentar novamente. Esta despesa tem referencia bancaria ou resposta incerta.'
    return ''


def corrigir(con, despesa_id: int, *, dados: Any, motivo: str, versao: str,
             agora: datetime, por: str, papel: str, usuario_id: int) -> dict:
    """Prende a linha, valida tudo e revoga a autorizacao na mesma transacao do rastro."""
    if papel != 'ADMIN':
        raise DP.DespesaError('So o oficial corrige dados de pagamento.')
    motivo = DP._texto(motivo, 500)
    if len(motivo) < 10:
        raise DP.DespesaError('Explique a correcao em pelo menos 10 caracteres.')
    bd = banco(con)
    d = DP._prender(bd, despesa_id)
    if not pode_corrigir(d):
        raise DP.DespesaError('Nao e seguro alterar esta despesa: confira primeiro o resultado no banco e no extrato.')
    if not versao or versao != revisao(d):
        raise DP.DespesaError('A despesa mudou depois que a tela foi aberta. Recarregue e confira os dados.')
    pessoa = bd.um('SELECT id,username,role,active,eh_robo FROM users WHERE id=%s', (int(usuario_id),))
    if not pessoa or not pessoa['active'] or pessoa['role'] != 'ADMIN' or pessoa['eh_robo']:
        raise DP.DespesaError('A correcao exige a conta humana do oficial.')
    novo = {k: dados.get(k) for k in CAMPOS if k != 'codigo_barras'}
    novo['forma'] = str(novo['forma'] or '')
    if novo['forma'] not in (DP.BOLETO, DP.ARRECADACAO, DP.PIX_COPIA_E_COLA, DP.PIX_CHAVE):
        raise DP.DespesaError('Escolha boleto, conta/guia ou Pix para pagamento pelo banco.')
    novo['valor'] = DP.centavos_da_tela(novo['valor'])
    if novo['valor'] <= 0:
        raise DP.DespesaError('Informe um valor maior que zero.')
    novo['vencimento'] = DP._data(novo['vencimento'], 'Vencimento')
    novo['beneficiario_nome'] = DP._texto(novo['beneficiario_nome'], 150)
    if len(novo['beneficiario_nome']) < DP.MINIMO_DA_DESCRICAO:
        raise DP.DespesaError('Informe o nome do favorecido.')
    novo['beneficiario_documento'] = DP.digitos(novo['beneficiario_documento'])
    if novo['beneficiario_documento'] and cpf_cnpj.documento_valido(novo['beneficiario_documento']) is not True:
        raise DP.DespesaError('O CPF/CNPJ do favorecido nao confere.')
    lido = DP.conferir_pagamento(novo['forma'], novo['codigo'], novo['valor'], novo['vencimento'])
    novo.update(codigo=lido['codigo'], codigo_barras=lido['barras'])
    if novo['forma'] == DP.PIX_CHAVE:
        DP.conferir_favorecido_pix(bd, chave=novo['codigo'], documento=novo['beneficiario_documento'],
                                  nome=novo['beneficiario_nome'], sem_despesa=int(despesa_id))
    antes = {k: d.get(k) for k in CAMPOS}
    if novo == antes:
        raise DP.DespesaError('Nenhum dado de pagamento mudou.')
    divergencia = ''
    if d.get('valor_esperado') is not None and int(d['valor_esperado']) != novo['valor']:
        divergencia = f"O sistema calculou R$ {DP.reais(int(d['valor_esperado']))} e a guia traz R$ {DP.reais(novo['valor'])}."
    bd.escrever("""UPDATE dp_despesas SET forma=%s,codigo=%s,codigo_barras=%s,valor=%s,
        vencimento=%s,beneficiario_nome=%s,beneficiario_documento=%s,divergencia=%s,
        situacao='AGUARDANDO_AUTORIZACAO',autorizada_em=NULL,autorizada_por=NULL,
        autorizada_pela_regra='',acima_do_teto=0,ambiente=NULL,enviada_em=NULL,
        tentativas=0,banco_status='',mensagem='' WHERE id=%s""",
        (*[novo[k] for k in CAMPOS], divergencia, int(despesa_id)))
    quando = DP._carimbo(agora)
    DP._evento(bd, despesa_id, 'CORRIGIR_PAGAMENTO', 'aguarda nova autorizacao', motivo, por, quando)
    IDR.registrar(con, ts=quando, user_id=pessoa['id'], username=pessoa['username'],
                  action='DESPESA_PAGAMENTO_CORRIGIDO', entity_type='dp_despesas',
                  entity_id=int(despesa_id), details={'motivo': motivo, 'antes': antes, 'depois': novo,
                  'banco_anterior': {k: d.get(k) for k in ('banco_status','mensagem','tentativas','enviada_em')},
                  'autorizacao_revogada': {'por': d.get('autorizada_por'), 'em': d.get('autorizada_em')}})
    return DP.despesa(bd, despesa_id)
