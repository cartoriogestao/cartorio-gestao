"""Referencia mensal do Portal do Selo, sem criar selos ou ajustes ficticios no livro."""
from __future__ import annotations

import calendar
import hashlib
import json
import re
import zipfile
from datetime import date
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET

import despesas as DP
import identidade_do_robo as IDR
import livro_diario as LD
from bd_nativo import banco

MAX_BYTES=2*1024*1024
NS={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def _xml(z, nome):
    if z.getinfo(nome).file_size>MAX_BYTES:
        raise DP.DespesaError('O relatorio descompactado passa do limite de 2 MB.')
    conteudo=z.read(nome)
    seguro=conteudo.replace(b'\x00', b'').upper()
    if b'<!DOCTYPE' in seguro or b'<!ENTITY' in seguro:
        raise DP.DespesaError('O relatorio contem XML nao permitido.')
    return ET.fromstring(conteudo)


def _centavos(v):
    if v is None or not str(v).strip():
        raise DP.DespesaError('Falta um valor monetario no relatorio do portal.')
    texto=str(v or '0').strip().replace('R$','').strip()
    if ',' in texto: texto=texto.replace('.','').replace(',','.')
    try:
        n=Decimal(texto)
        if not n.is_finite() or n<0 or n>Decimal(1000000000) or n*100!=(n*100).to_integral_value():
            raise ValueError
        return int(n*100)
    except (ValueError,InvalidOperation) as erro:
        raise DP.DespesaError('Valor monetario invalido no relatorio do portal.') from erro


def linhas_xlsx(conteudo: bytes) -> list[dict]:
    if not conteudo or len(conteudo)>MAX_BYTES:
        raise DP.DespesaError('Use um relatorio XLSX de ate 2 MB.')
    try:
        with zipfile.ZipFile(BytesIO(conteudo)) as z:
            if len(z.infolist())>100 or sum(i.file_size for i in z.infolist())>5*MAX_BYTES:
                raise DP.DespesaError('O relatorio compactado excede os limites de leitura.')
            strings=[]
            if 'xl/sharedStrings.xml' in z.namelist():
                strings=[''.join(t.text or '' for t in i.iter('{'+NS['s']+'}t')) for i in _xml(z,'xl/sharedStrings.xml')]
            linhas=[]
            for row in _xml(z,'xl/worksheets/sheet1.xml').findall('.//s:sheetData/s:row',NS):
                linha={}
                for cell in row.findall('s:c',NS):
                    if cell.find('s:f',NS) is not None:
                        raise DP.DespesaError('O relatorio contem formulas. Use a exportacao original do portal.')
                    valor=cell.find('s:v',NS)
                    valor=valor.text if valor is not None else ''.join(t.text or '' for t in cell.findall('.//s:t',NS))
                    if cell.get('t')=='s': valor=strings[int(valor)]
                    linha[re.sub(r'\d','',cell.get('r',''))]=str(valor or '')
                linhas.append(linha)
    except (zipfile.BadZipFile,KeyError,IndexError,ET.ParseError,ValueError) as erro:
        raise DP.DespesaError('Nao reconheci o XLSX do relatorio de faturamento do Portal do Selo.') from erro
    return linhas


def periodo_mensal(linhas: list[dict]) -> tuple[date, date]:
    texto='\n'.join(' '.join(l.values()) for l in linhas)
    periodo=re.search(r'(\d{2}/\d{2}/\d{4})\s+at[eé]\s+(\d{2}/\d{2}/\d{4})',texto,re.IGNORECASE)
    if not periodo: raise DP.DespesaError('O periodo do relatorio nao foi encontrado.')
    try:
        inicio,fim=(date(*reversed([int(p) for p in d.split('/')])) for d in periodo.groups())
    except ValueError as erro: raise DP.DespesaError('Periodo invalido no relatorio.') from erro
    if inicio.day!=1 or fim!=date(inicio.year,inicio.month,calendar.monthrange(inicio.year,inicio.month)[1]):
        raise DP.DespesaError('Exporte um mes completo, do primeiro ao ultimo dia.')
    return inicio,fim


def ler(conteudo: bytes, *, cns: str) -> dict:
    linhas=linhas_xlsx(conteudo)
    texto='\n'.join(' '.join(l.values()) for l in linhas)
    if 'RELATÓRIO DE FATURAMENTO DAS SERVENTIAS' not in texto.upper():
        raise DP.DespesaError('O arquivo nao e o relatorio de faturamento das serventias.')
    inicio,_fim=periodo_mensal(linhas)
    cabecalho=next((l for l in linhas if 'EMOLUMENTO (A)' in l.values() and 'FERJ' in l.values()),None)
    if not cabecalho: raise DP.DespesaError('As colunas de emolumentos e FERJ nao foram encontradas.')
    col={v:k for k,v in cabecalho.items()}
    necessarias=('CNS','Qtde. Atos','Qtde. Cancelados','EMOLUMENTO (A)','RECOLHIMENTO DE PROTESTO DIFERIDO (B)','FATURAMENTO (A+B)','FERJ')
    if any(n not in col for n in necessarias): raise DP.DespesaError('Faltam colunas obrigatorias no relatorio.')
    dados=[l for l in linhas if l.get(col['CNS'],'').zfill(6)==str(cns).zfill(6)]
    if len(dados)!=1: raise DP.DespesaError('O relatorio precisa conter exatamente uma linha para o CNS desta serventia.')
    row=dados[0]
    r={k:_centavos(row.get(col[n])) for k,n in (
        ('bruto','EMOLUMENTO (A)'),('protesto_diferido','RECOLHIMENTO DE PROTESTO DIFERIDO (B)'),
        ('faturamento','FATURAMENTO (A+B)'),('ferj','FERJ'))}
    if r['faturamento']!=r['bruto']+r['protesto_diferido'] or r['ferj']>r['bruto']:
        raise DP.DespesaError('Os totais do relatorio nao conferem. Confira a exportacao.')
    for k,n in (('atos','Qtde. Atos'),('cancelados','Qtde. Cancelados')):
        try:
            v=Decimal(row.get(col[n]) or '-1')
            if not v.is_finite() or v<0 or v>10_000_000 or v!=v.to_integral_value(): raise ValueError
        except (InvalidOperation,ValueError) as erro: raise DP.DespesaError('Quantidade de atos invalida.') from erro
        r[k]=int(v)
    return {**r,'liquido':r['bruto']-r['ferj'],'competencia':inicio.isoformat()[:7],
            'cns':str(cns).zfill(6),'sha256':hashlib.sha256(conteudo).hexdigest()}


def _chave(comp,cns):
    LD.competencia(comp)
    if not re.fullmatch(r'\d{6}',str(cns)): raise DP.DespesaError('CNS da serventia invalido.')
    return f'faturamento_portal.{cns}.{comp}'


def referencia(con, comp: str, *, cns: str) -> dict | None:
    r=banco(con).um('SELECT value FROM settings WHERE key=%s',(_chave(comp,cns),))
    return json.loads(r['value']) if r and r['value'] else None


def cns_da_casa(con) -> str:
    linhas=banco(con).ler("SELECT key,value FROM settings WHERE key IN ('ri_cns','serventia_cns')")
    cfg={r['key']:r['value'] for r in linhas}
    return DP.digitos(cfg.get('ri_cns') or cfg.get('serventia_cns') or '')


def registrar(con, conteudo: bytes, *, cns: str, pasta: Path, por: str, usuario_id: int, agora: str) -> dict:
    r=ler(conteudo,cns=cns); bd=banco(con)
    pessoa=bd.um('SELECT id,username,role,active,eh_robo FROM users WHERE id=%s',(int(usuario_id),))
    if not pessoa or not pessoa['active'] or pessoa['role']!='ADMIN' or pessoa['eh_robo']:
        raise DP.DespesaError('A importacao exige a conta humana do titular.')
    chave=_chave(r['competencia'],cns)
    bd.escrever("INSERT INTO settings(key,value) VALUES(%s,'') ON CONFLICT(key) DO NOTHING",(chave,))
    anterior=bd.um('SELECT value FROM settings WHERE key=%s FOR UPDATE',(chave,))
    antes=json.loads(anterior['value']) if anterior['value'] else None
    if antes and antes.get('sha256')==r['sha256']: return antes
    pasta.mkdir(parents=True,exist_ok=True)
    destino=pasta/f"faturamento-{r['competencia']}-{r['sha256']}.xlsx"
    destino.write_bytes(conteudo)
    r.update(registrado_por=por,registrado_em=agora,fonte=str(destino))
    bd.escrever('UPDATE settings SET value=%s WHERE key=%s',(json.dumps(r,ensure_ascii=False),chave))
    IDR.registrar(con,ts=agora,user_id=pessoa['id'],username=pessoa['username'],action='FATURAMENTO_PORTAL_IMPORTADO',
                  entity_type='settings',entity_id=None,details={'antes':antes,'depois':r})
    return r


def conferencia(con, comp: str, *, cns: str) -> dict:
    local=LD.apurar(con,comp); ref=referencia(con,comp,cns=cns)
    bruto=int(local['receita_bruta']); ferj=int(local['fundos']['FERJ'])
    return {'competencia':comp,'local_bruto':bruto,'local_ferj':ferj,'local_liquido':bruto-ferj,
            'referencia':ref,'sem_valor':local['sem_valor'],
            'diferenca_bruto':ref['bruto']-bruto if ref else None,
            'diferenca_ferj':ref['ferj']-ferj if ref else None,
            'diferenca_liquido':ref['liquido']-(bruto-ferj) if ref else None}
