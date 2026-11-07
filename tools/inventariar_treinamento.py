"""Exporta catálogo e estruturas didáticas de fontes públicas; não abre o banco."""
from pathlib import Path
import sys,ast,json,hashlib,re
import argparse
from html.parser import HTMLParser
DEFAULT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--fonte',type=Path,default=DEFAULT)
parser.add_argument('--saida',type=Path)
parser.add_argument('--sobrepor',type=Path)
opts=parser.parse_args()
R=opts.fonte.resolve()
if R != DEFAULT.resolve() and not opts.saida:
    parser.error('Informe --saida para gerar a partir de outra instalação.')
sys.path.insert(0,str(DEFAULT))
if opts.sobrepor:sys.path.insert(0,str(opts.sobrepor.resolve()))
sys.path.insert(1 if opts.sobrepor else 0,str(R))
from tools.inventariar_telas_manual import route_templates,fields_and_actions,clear_jinja
import tools.inventariar_telas_manual as inventario
inventario.ROOT=R
inventario.TEMPLATES=R/'templates'
def template_path(nome):
    sobre=opts.sobrepor/'templates'/nome if opts.sobrepor else None
    return sobre if sobre and sobre.is_file() else R/'templates'/nome
import navegacao as NAV
import modelos_papeis as P
import ri_modelos_atos as RM
import notas_modelos as NM
from treinamento_roteiros import familia

class TextoDoModelo(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.partes=[]

    def handle_starttag(self, tag, attrs):
        if tag in ('p','br','div','li'):
            self.partes.append('\n')

    def handle_data(self, data):
        self.partes.append(data)

def estrutura_do_modelo(corpo):
    leitor=TextoDoModelo();leitor.feed(corpo)
    texto=''.join(leitor.partes)
    texto=re.sub(r'\{\{\s*(.*?)\s*\}\}',lambda m:'['+m[1].split('|')[0].replace('_',' ').upper()+']',texto)
    texto=re.sub(r'\{%.*?%\}', '', texto, flags=re.S)
    return re.sub(r'\n\s*\n+', '\n\n', texto).strip()

roles={}
for path in [*R.glob('*.py'),*(list(opts.sobrepor.glob('*.py')) if opts.sobrepor else [])]:
    try: tree=ast.parse(path.read_text('utf-8-sig'))
    except (SyntaxError,UnicodeError): continue
    for n in ast.walk(tree):
        if not isinstance(n,ast.FunctionDef): continue
        if not any(isinstance(d,ast.Call) and isinstance(d.func,ast.Attribute) and d.func.attr=='route' for d in n.decorator_list): continue
        rs=None
        for d in n.decorator_list:
            if isinstance(d,ast.Call) and isinstance(d.func,ast.Name) and d.func.id=='roles_required':
                if any(k.arg=='metodos' and 'GET' not in ast.unparse(k.value) for k in d.keywords): continue
                xs=[x.value for x in d.args if isinstance(x,ast.Constant) and isinstance(x.value,str)]
                if xs: rs=xs
                elif any(isinstance(x,ast.Starred) for x in d.args): rs=['ADMIN','MANAGER','USER','AUDITOR'] if any(isinstance(x,ast.Starred) and isinstance(x.value,ast.Name) and x.value.id in ('LEITURA','QUATRO') for x in d.args) else ['ADMIN','MANAGER','USER']
        roles[n.name]=rs or ['ADMIN','MANAGER','USER','AUDITOR']
routes=route_templates()
entries=[]
seen=set()
for m in NAV.MODULOS_DA_BARRA:
    for sec,itens in m['secoes']:
        for e in itens:
            key=e['endpoint']+json.dumps(e.get('args',{}),sort_keys=True)
            if key in seen:continue
            seen.add(key)
            template=routes.get(e['endpoint'])
            fs,bs,ls=fields_and_actions(template_path(template)) if template and template_path(template).is_file() else ([],[],[])
            allowed=set(roles.get(e['endpoint'],['ADMIN']))
            if e.get('papeis'):allowed.intersection_update(e['papeis'])
            if any(x in e['endpoint'] for x in ('pld_','backup_','users','agente_config')):allowed.intersection_update(['ADMIN'])
            entries.append(dict(id='tela-'+hashlib.sha256(key.encode()).hexdigest()[:16],nome=e['rotulo'],
                grupo=m['nome'],secao=sec,endpoint=e['endpoint'],args=e.get('args',{}),
                papeis=sorted(allowed),campos=[re.sub(r' \[[^\]]*\]','',f) for f in fs],
                comandos=bs,template=template or '',familia=familia(e['endpoint'],e['rotulo'],m['nome']),
                assinatura=hashlib.sha256(template_path(template).read_bytes()).hexdigest() if template else '',tipo='funcao'))
# Ler somente a pasta pública de fábrica. NM.minutas() também pode consultar
# a base de modelos em execução; o inventário nunca precisa de conexão.
from modelos_papeis import pasta as pasta_modelos
padroes=pasta_modelos.ler_pasta(R/'modelos_padrao')['padroes']
minutas_notas=[{**m,'nome':padroes[pasta_modelos.chave_normal(m['codigo'])]['nome'],
    'corpo':padroes[pasta_modelos.chave_normal(m['codigo'])]['corpo']} for m in NM.MINUTAS]
for grupo,modelos,endpoint in [('Registro de Imóveis',RM.MODELOS,'ri_minutas'),('Tabelionato de Notas',minutas_notas,'notas_atos')]:
    for m in modelos:
        name=m.get('nome') or m.get('titulo') or m['codigo']
        entries.append(dict(id='ato-'+hashlib.sha256((grupo+m['codigo']).encode()).hexdigest()[:16],nome=name,
            grupo=grupo,endpoint=endpoint,args={},papeis=['ADMIN','MANAGER','USER'],
            campos=[re.sub(r'[_\[\]]',' ',x).strip().capitalize() for x in re.findall(r'\[([A-ZÀ-Ü][A-ZÀ-Ü0-9_ /.-]{2,60})\]',m.get('corpo',''))][:60],
            comandos=['Preparar minuta','Conferir prévia','Praticar ato pela rotina autorizada'],
            familia=familia(endpoint,name,grupo),tipo='ato',modelo=m['codigo'],
            estrutura_modelo=estrutura_do_modelo(m.get('corpo','')),
            assinatura=hashlib.sha256(json.dumps(m,ensure_ascii=False,sort_keys=True).encode()).hexdigest()))
for m in P.CATALOGO:
    entries.append(dict(id='papel-'+m['chave'].lower().replace('_','-'),nome=m['nome'],grupo=m['atribuicao'],
        endpoint='',args={},papeis=['ADMIN','MANAGER','USER'],campos=[x.replace('_',' ').capitalize() for x in m.get('campos',[])],
        comandos=['Localizar registro de origem','Conferir prévia','Emitir pela rotina da atribuição'],
        familia=familia(m['chave'].lower(),m['nome'],m['atribuicao']),tipo='documento',
        explica=m.get('explica',''),assinatura=hashlib.sha256(json.dumps(m,ensure_ascii=False,sort_keys=True,default=str).encode()).hexdigest()))
out=opts.saida or R/'treinamento_inventario.json'
out.write_text(json.dumps({'revisado_em':'2026-11-07','entradas':entries},ensure_ascii=False,indent=2),encoding='utf-8')
print('Aulas inventariadas:',len(entries),'funções:',sum(x['tipo']=='funcao' for x in entries),'atos:',sum(x['tipo']=='ato' for x in entries),'documentos:',sum(x['tipo']=='documento' for x in entries))
