"""Conferencia mensal por selo. Importar nao cancela atos nem cria receitas."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

import custas
import despesas as DP
import faturamento_portal as FP
import identidade_do_robo as IDR
import selo as SL
from bd_nativo import banco

MAX_SELOS = 20000
TIPOS = {
    'ausente_local': 'Selo ausente do cadastro local',
    'fora_portal': 'Selo local ausente do analítico',
    'cancelamento': 'Cancelamento divergente',
    'competencia': 'Mês de uso divergente',
    'emolumentos': 'Emolumentos divergentes ou ausentes',
    'gratuidade': 'Isenção/gratuidade divergente',
    'diferimento': 'Diferimento divergente',
    'ato': 'Código do ato divergente',
    'quantidade': 'Quantidade a conferir',
    'arredondamento_ferj': 'FERJ: arredondamento por unidade',
    'ferj': 'FERJ divergente',
}


def _hash(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def _quantidade(v):
    try:
        n = Decimal(str(v))
        if not n.is_finite() or not 1 <= n <= 1000000 or n != n.to_integral_value():
            raise ValueError
        return int(n)
    except (ValueError, InvalidOperation) as erro:
        raise DP.DespesaError('Quantidade invalida no analitico.') from erro


def _sim(v):
    texto = str(v).strip().casefold()
    if texto not in ('sim', 'não', 'nao'):
        raise DP.DespesaError('Marca de cancelamento/isencao/gratuidade/diferimento ilegivel.')
    return texto == 'sim'


def _dia(v):
    try:
        if re.fullmatch(r'\d+(?:\.\d+)?', v):
            return date(1899, 12, 30) + timedelta(days=int(Decimal(v)))
        if re.match(r'^\d{2}/\d{2}/\d{4}', v):
            return date(*reversed([int(x) for x in v[:10].split('/')]))
        return date.fromisoformat(v[:10])
    except (ValueError, InvalidOperation, OverflowError) as erro:
        raise DP.DespesaError('Data da selagem invalida no analitico.') from erro


def ler(conteudo: bytes, *, cns: str) -> dict:
    if not re.fullmatch(r'\d{6}', cns):
        raise DP.DespesaError('CNS da serventia invalido.')
    linhas = FP.linhas_xlsx(conteudo)
    if not any('RELATÓRIO DE FISCALIZAÇÃO DE SELOS' in ' '.join(r.values()).upper() for r in linhas):
        raise DP.DespesaError('Use o relatorio de fiscalizacao de selos, com a relacao analitica.')
    inicio, fim = FP.periodo_mensal(linhas)
    nomes = ('CNS', 'NÚMERO DO SELO', 'DATA DA SELAGEM', 'ATO', 'QTDE.',
             'CANCELADO', 'ISENTO', 'GRATUITO', 'DIFERIDO', 'EMOLUMENTO', 'FERJ')
    cab = next((r for r in linhas if 'NÚMERO DO SELO' in r.values()), None)
    if not cab or any(list(cab.values()).count(n) != 1 for n in nomes):
        raise DP.DespesaError('Faltam colunas obrigatorias ou ha colunas repetidas no analitico.')
    col = {v: k for k, v in cab.items()}
    registros = []
    vistos = set()
    for r in linhas[linhas.index(cab) + 1:]:
        numero = r.get(col['NÚMERO DO SELO'], '').strip().upper()
        if not numero:
            if any(v.strip() for v in r.values()):
                raise DP.DespesaError('Ha linha incompleta no analitico, sem numero de selo.')
            continue
        try:
            codigo = SL.ler_codigo(numero)
        except SL.SeloError as erro:
            raise DP.DespesaError('Codigo de selo invalido no analitico.') from erro
        if r.get(col['CNS'], '').strip().zfill(6) != cns or (codigo.cns and codigo.cns != cns):
            raise DP.DespesaError('O analitico contem selo de outra serventia.')
        if numero in vistos:
            raise DP.DespesaError('O analitico contem selo repetido; nenhuma linha foi importada.')
        vistos.add(numero)
        dia = _dia(r.get(col['DATA DA SELAGEM'], '').strip())
        if not inicio <= dia <= fim:
            raise DP.DespesaError('Ha selo fora do mes informado no analitico.')
        emol, ferj = (FP._centavos(r.get(col[n])) for n in ('EMOLUMENTO', 'FERJ'))
        if ferj > emol:
            raise DP.DespesaError('O FERJ de um selo supera seu emolumento.')
        registros.append({
            'numero': numero, 'dia': dia.isoformat(), 'ato': r.get(col['ATO'], '').strip(),
            'quantidade': _quantidade(r.get(col['QTDE.'])), 'emolumentos': emol, 'ferj': ferj,
            **{k: _sim(r.get(col[n])) for k, n in (
                ('cancelado', 'CANCELADO'), ('isento', 'ISENTO'), ('gratuito', 'GRATUITO'), ('diferido', 'DIFERIDO'))},
        })
        if len(registros) > MAX_SELOS:
            raise DP.DespesaError('O analitico excede 20 mil selos.')
    if not registros:
        raise DP.DespesaError('O analitico nao tem selos; nao foi registrado como mes sem movimento.')
    return {'cns': cns, 'competencia': inicio.isoformat()[:7], 'registros': registros,
            'sha256': hashlib.sha256(conteudo).hexdigest()}


def _chave(comp, cns):
    return FP._chave(comp, cns).replace('faturamento_portal.', 'conferencia_selos.', 1)


def referencia(con, comp, *, cns):
    row = banco(con).um('SELECT value FROM settings WHERE key=%s', (_chave(comp, cns),))
    return json.loads(row['value']) if row and row['value'] else None


def _titular(con, usuario_id):
    pessoa = banco(con).um('SELECT id,username,role,active,eh_robo FROM users WHERE id=%s', (int(usuario_id),))
    if not pessoa or not pessoa['active'] or pessoa['role'] != 'ADMIN' or pessoa['eh_robo']:
        raise DP.DespesaError('Esta conferencia exige a conta humana do titular.')
    return pessoa


def _meta(ref):
    return {k: v for k, v in ref.items() if k != 'registros'} if ref else None


def registrar(con, conteudo, *, cns, pasta: Path, usuario_id, por, agora):
    pessoa = _titular(con, usuario_id)
    ref = ler(conteudo, cns=cns)
    bd = banco(con)
    chave = _chave(ref['competencia'], cns)
    bd.travar(chave)
    antes = referencia(con, ref['competencia'], cns=cns)
    if antes and antes['sha256'] == ref['sha256']:
        return antes
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"analitico-{ref['competencia']}-{ref['sha256']}.xlsx"
    if destino.exists():
        if hashlib.sha256(destino.read_bytes()).hexdigest() != ref['sha256']:
            raise DP.DespesaError('O original arquivado nao confere; preserve-o para revisao.')
    else:
        with destino.open('xb') as f:
            f.write(conteudo)
    ref.update(fonte=str(destino), registrado_por=por, registrado_em=agora)
    bd.escrever('INSERT INTO settings(key,value) VALUES(%s,%s) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value',
                (chave, json.dumps(ref, ensure_ascii=False)))
    IDR.registrar(con, ts=agora, user_id=pessoa['id'], username=pessoa['username'],
                  action='CONFERENCIA_SELOS_IMPORTADA', entity_type='settings', entity_id=None,
                  details={'antes': _meta(antes), 'depois': _meta(ref), 'selos': len(ref['registros'])})
    return ref


def _cobrado(s):
    return not any(s[k] for k in ('cancelado', 'isento', 'gratuito', 'diferido'))


def conferir(con, comp, *, cns):
    import livro_diario as LD
    bd = banco(con)
    inicio, fim = LD._limites(LD.competencia(comp))
    ref = referencia(con, comp, cns=cns)
    fonte = {s['numero']: s for s in ref['registros']} if ref else {}
    linhas = bd.ler('''SELECT id,numero,texto,tabela,ato_id,usado_em,cancelado_em,quantidade
                       FROM sd_selos WHERE ambiente='PRODUCAO'
                       AND ((usado_em >= %s AND usado_em < %s) OR numero=ANY(%s)) ORDER BY id''',
                    (inicio, fim, list(fonte)))
    for linha in linhas:
        linha['cancelado_em'] = str(linha['cancelado_em'] or '').strip() or None
    local = {s['numero']: s for s in linhas}
    pct = custas.percentual_ferj_da_casa(con)
    diferencas, candidatos = [], []
    for numero in sorted(set(fonte) | set(local)):
        p, l = fonte.get(numero), local.get(numero)
        problemas = []
        lido = SL.ler_texto(l['texto']) if l else None
        emol = LD._cent(lido['emolumentos']) if lido else None
        marcas = ' '.join(lido['marcas']).upper() if lido else ''
        ferj_local = custas.ferj_do_emolumento(emol, pct, quantidade=l['quantidade']) if emol is not None else None
        if ref:
            if not l:
                problemas.append('ausente_local')
            elif not p:
                problemas.append('fora_portal')
            else:
                if bool(str(l['cancelado_em'] or '').strip()) != p['cancelado']:
                    problemas.append('cancelamento')
                if str(l['usado_em'] or '')[:7] != comp:
                    problemas.append('competencia')
                if emol != p['emolumentos']:
                    problemas.append('emolumentos')
                if ('ISENT' in marcas) != (p['isento'] or p['gratuito']):
                    problemas.append('gratuidade')
                if ('DIFERID' in marcas) != p['diferido']:
                    problemas.append('diferimento')
                if lido['ato'] and lido['ato'] != p['ato']:
                    problemas.append('ato')
                if l['quantidade'] != p['quantidade'] and (l['quantidade'] is not None or p['quantidade'] > 1):
                    problemas.append('quantidade')
                if _cobrado(p) and not l['cancelado_em'] and ferj_local != p['ferj']:
                    unitario = custas.ferj_do_emolumento(p['emolumentos'], pct, quantidade=p['quantidade'])
                    problemas.append('arredondamento_ferj' if unitario == p['ferj'] and p['quantidade'] > 1 else 'ferj')
                if (l['quantidade'] is None and p['quantidade'] > 1 and _cobrado(p)
                        and p['emolumentos'] % p['quantidade'] == 0
                        and not set(problemas) - {'quantidade', 'arredondamento_ferj'}
                        and custas.ferj_do_emolumento(p['emolumentos'], pct, quantidade=p['quantidade']) == p['ferj']):
                    candidatos.append({'id': l['id'], 'numero': numero, 'quantidade': p['quantidade'],
                                       'quantidade_antes': None, 'ferj_antes': ferj_local, 'ferj_depois': p['ferj']})
        if problemas:
            diferencas.append({'numero': numero, 'tipos': problemas, 'portal': p,
                               'local': l, 'emol_local': emol, 'ferj_local': ferj_local})
    resumo = FP.conferencia(con, comp, cns=cns)
    totais = None
    if ref:
        cob = [s for s in fonte.values() if _cobrado(s)]
        bruto, ferj = sum(s['emolumentos'] for s in cob), sum(s['ferj'] for s in cob)
        totais = {'bruto': bruto, 'ferj': ferj, 'liquido': bruto - ferj,
                  'selos': len(fonte), 'cancelados': sum(s['cancelado'] for s in fonte.values()),
                  'unidades_canceladas': sum(s['quantidade'] for s in fonte.values() if s['cancelado'])}
    consolidado = resumo['referencia']
    dif_relatorios = {k: consolidado[k] - totais[k] for k in ('bruto', 'ferj', 'liquido')} if totais and consolidado else None
    contagens = {k: sum(k in d['tipos'] for d in diferencas) for k in TIPOS}
    contagem_confere = bool(totais and consolidado and totais['selos'] == consolidado['atos']
                           and totais['unidades_canceladas'] == consolidado['cancelados'])
    fechado = bool(ref and consolidado and not diferencas and contagem_confere and
                   all(resumo['diferenca_' + k] == 0 and dif_relatorios[k] == 0 for k in ('bruto', 'ferj', 'liquido')))
    return {'competencia': comp, 'referencia': _meta(ref), 'totais': totais, 'resumo': resumo,
            'diferencas': diferencas, 'contagens': contagens, 'candidatos': candidatos,
            'diferenca_relatorios': dif_relatorios, 'contagem_confere': contagem_confere,
            'conferido': fechado, 'revisao': _hash({'fonte': ref['sha256'] if ref else None, 'local': linhas, 'pct': pct})}


def aplicar_quantidades(con, comp, *, cns, revisao, motivo, usuario_id, agora):
    pessoa = _titular(con, usuario_id)
    if len(str(motivo or '')) > 1000:
        raise DP.DespesaError('O motivo deve ter ate mil caracteres.')
    if len(str(motivo or '').strip()) < 10:
        raise DP.DespesaError('Informe o motivo da conferencia, com pelo menos dez letras.')
    bd = banco(con)
    bd.travar(_chave(comp, cns))
    # Bloquear as linhas antes de recalcular a revisao e o efeito financeiro.
    inicio, fim = FP.LD._limites(FP.LD.competencia(comp))
    bd.ler("SELECT id FROM sd_selos WHERE ambiente='PRODUCAO' AND usado_em >= %s AND usado_em < %s FOR UPDATE", (inicio, fim))
    atual = conferir(con, comp, cns=cns)
    if revisao != atual['revisao']:
        raise DP.DespesaError('A conferencia mudou. Reabra a tela antes de confirmar as quantidades.')
    candidatos = atual['candidatos']
    if not candidatos:
        raise DP.DespesaError('Nao ha quantidades verificadas para completar.')
    for c in candidatos:
        bd.escrever('UPDATE sd_selos SET quantidade=%s WHERE id=%s AND quantidade IS NULL', (c['quantidade'], c['id']))
    IDR.registrar(con, ts=agora, user_id=pessoa['id'], username=pessoa['username'],
                  action='CONFERENCIA_SELOS_QUANTIDADES', entity_type='settings', entity_id=None,
                  details={'competencia': comp, 'fonte': atual['referencia']['sha256'],
                           'motivo': str(motivo).strip(), 'alteracoes': candidatos})
    return len(candidatos)
