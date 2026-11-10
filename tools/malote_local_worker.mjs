// Orquestrador fixo: o modelo não fornece código, URL, pessoa ou documento.
import fs from 'node:fs/promises';
import { realpathSync } from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

export function janela(agora = new Date()) {
  const p = new Intl.DateTimeFormat('en-US', { timeZone: 'America/Sao_Paulo', weekday: 'short',
    year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })
    .formatToParts(agora).reduce((a,x) => ({ ...a, [x.type]: x.value }), {});
  return { aberta: ['Mon','Tue','Wed','Thu','Fri'].includes(p.weekday) && Number(p.hour) >= 8,
    dia: `${p.year}-${p.month}-${p.day}`, faixa: `${p.hour}${Number(p.minute)<30 ? '00':'30'}` };
}
export function origemPermitida(cfg) {
  const u = new URL(cfg.sistema);
  const p = u.hostname.split('.').map(Number);
  const tailscale = p.length === 4 && p.every(n => Number.isInteger(n) && n>=0 && n<=255) && p[0]===100 && p[1]>=64 && p[1]<=127;
  if (u.username || u.password || u.search || u.hash || !['','/'].includes(u.pathname) ||
      (u.protocol !== 'https:' && !(u.protocol==='http:' && cfg.httpRedePrivada===true && tailscale)))
    throw Error('ORIGEM_RECUSADA');
  return u.origin;
}
export function conclusao(estado, anterior, execucaoId=null) {
  // Só um resultado manual posterior ao pedido, sem outra rodada pendente.
  const rodadas = (estado.execucoes || []).filter(e => execucaoId!==null ? e.id===execucaoId : e.id > anterior && e.disparo==='MANUAL').sort((a,b)=>a.id-b.id);
  const e = rodadas[0];
  if (!e || !e.terminada_em || e.situacao === 'RODANDO' || estado.processo?.pedido_pendente) return null;
  return { estado: e.precisa_mfa ? 'AGUARDANDO_MFA_MALOTE' : e.cofre_trancado ? 'COFRE_TRANCADO' : e.situacao==='OK' ? 'CONCLUIDO' : 'PENDENCIA_NO_SISTEMA',
    concluido: e.situacao==='OK', execucao: e.id };
}
export async function gravar(alvo, valor) {
  await fs.mkdir(path.dirname(alvo), { recursive:true, mode:0o700 });
  const tmp=alvo+'.'+crypto.randomUUID()+'.tmp';
  await fs.writeFile(tmp,JSON.stringify(valor,null,2)+'\n',{mode:0o600});
  await fs.rename(tmp,alvo);
}
export async function lerEstado(cfg) {
  try { return JSON.parse(await fs.readFile(path.join(cfg.pastaDados,'estado.json'),'utf8')); }
  catch(e) { if(e.code==='ENOENT')return {estado:'AINDA_NAO_EXECUTADO',concluido:false}; throw e; }
}
export async function conferirPendente(cfg, item) {
  if (!/^[0-9]{14}$/.test(item.grupo||'') || !/^[0-9a-f]{64}$/.test(item.sha256||'')) throw Error('MANIFESTO_INVALIDO');
  const raiz=await fs.realpath(cfg.pastaDocumentos), file=await fs.realpath(item.arquivo);
  const relativo=path.relative(raiz,file);
  if (relativo.startsWith('..') || path.isAbsolute(relativo) || path.extname(file).toLowerCase()!=='.pdf') throw Error('ARQUIVO_RECUSADO');
  const stat=await fs.stat(file);if(stat.size>16*1024*1024)throw Error('ARQUIVO_RECUSADO');
  const data=await fs.readFile(file);
  if(data.subarray(0,5).toString()!=='%PDF-' || crypto.createHash('sha256').update(data).digest('hex')!==item.sha256)throw Error('HASH_DIVERGENTE');
  return {name:path.basename(file),mimeType:'application/pdf',buffer:data};
}
const pausa = ms => new Promise(r=>setTimeout(r,ms));
export async function executar(cfg, modo='--consultar', dependencias={}) {
  const origin=origemPermitida(cfg), j=janela(dependencias.agora);
  if (modo==='--estado') return lerEstado(cfg);
  if (!['--consultar','--executar','--agendado','--anexos-pendentes','--autenticar'].includes(modo))throw Error('MODO_RECUSADO');
  if (['--executar','--agendado','--anexos-pendentes'].includes(modo) && cfg.producaoLiberada!==true)
    return {estado:'AGUARDANDO_IMPLANTACAO',concluido:false};
  if (modo==='--agendado' && !j.aberta) return {estado:'FORA_DO_HORARIO',concluido:false};
  let anterior=await lerEstado(cfg);
  if (modo==='--agendado' && anterior.dia===j.dia && anterior.concluido===true)return anterior;
  if (modo!=='--autenticar' && anterior.estado==='LOGIN_RECUSADO')return anterior;
  await fs.mkdir(cfg.pastaDados,{recursive:true,mode:0o700});
  const lock=path.join(cfg.pastaDados,'executor.lock');let fd;
  try { fd=await fs.open(lock,'wx',0o600); }catch{ return {estado:'EXECUTOR_OCUPADO',concluido:false}; }
  await fd.writeFile(JSON.stringify({pid:process.pid,desde:new Date().toISOString()}));
  let context;let parar=false;const interromper=()=>{parar=true;};
  process.once('SIGTERM',interromper);process.once('SIGINT',interromper);
  const salvar = async r => {const s={...r,dia:j.dia,atualizado_em:new Date().toISOString()};await gravar(path.join(cfg.pastaDados,'estado.json'),s);return s;};
  try {
    if(dependencias.abrir) context=await dependencias.abrir();
    else {
      const require=createRequire(realpathSync(cfg.playwrightMcp));const { chromium }=require('playwright');
      context=await chromium.launchPersistentContext(path.resolve(cfg.perfil),{channel:'chrome',headless:false,
        ignoreDefaultArgs:['--use-mock-keychain','--password-store=basic']});
    }
    const page=await context.newPage();const url=origin+'/automacao/malote/agente';
    const nav=await page.goto(url,{waitUntil:'domcontentloaded'});
    if(nav?.status()===404)return salvar({estado:'AGUARDANDO_ATUALIZACAO',concluido:false});
    let enviouLogin=false;
    const pronto=async()=>{
      const here=new URL(page.url());if(here.origin!==origin)throw Error('REDIRECIONAMENTO_RECUSADO');
      if(here.pathname==='/automacao/malote/agente')return true;
      // Não consulta valores. Só envia uma vez se o Chrome reconhece ambos
      // os campos como preenchidos pelo gerenciador de senhas deste perfil.
      if(here.pathname==='/login' && !enviouLogin){
        const salvo=await page.locator('input[name="username"]:is(:autofill, :-webkit-autofill)').count() &&
          await page.locator('input[name="password"]:is(:autofill, :-webkit-autofill)').count();
        if(salvo){enviouLogin=true;await page.getByRole('button',{name:'Entrar',exact:true}).click();}
      }
      return false;
    };
    if(!await pronto()){
      const recusado=await page.getByText('Usuário ou senha inválidos.',{exact:false}).count();
      if(recusado)return salvar({...anterior,estado:'LOGIN_RECUSADO',concluido:false});
      if(modo!=='--autenticar')return salvar({...anterior,estado:'AGUARDANDO_LOGIN_SISTEMA',concluido:false});
      const fim=Date.now()+(cfg.prazoAutenticacaoMs||1800000);
      while(Date.now()<fim && !parar && !await pronto())await pausa(1000);
      if(!await pronto())return salvar({...anterior,estado:'AGUARDANDO_LOGIN_SISTEMA',concluido:false});
    }
    const csrf=await page.locator('input[name="csrf_token"]').first().inputValue();
    if(!csrf)throw Error('SESSAO_INVALIDA');
    const api=async(caminho,form)=>{
      const options={headers:{Accept:'application/json',...(form?{'X-CSRF-Token':csrf}:{})},maxRedirects:0};
      const r=form?await page.request.post(origin+caminho,{...options,multipart:form}):await page.request.get(origin+caminho,options);
      if(!r.ok() || !(r.headers()['content-type']||'').includes('application/json')){
        if([301,302,303,401,403].includes(r.status()))throw Error('SESSAO_INVALIDA');
        if(r.status()===404)throw Error('ATUALIZACAO_AUSENTE');
        throw Error('PEDIDO_RECUSADO');
      }
      const d=await r.json();if(d.erro)throw Error('PEDIDO_RECUSADO');return d;
    };
    const estado=await api('/automacao/malote/agente');
    if(estado.versao_fluxo!==1)throw Error('ATUALIZACAO_AUSENTE');
    if(modo==='--consultar'||modo==='--autenticar')return salvar({...anterior,estado:'CONSULTADO',configuracao:estado,concluido:anterior.dia===j.dia && anterior.concluido===true});
    const enviados={...(anterior.anexos_enviados||{})};
    for(const item of cfg.anexosPendentes||[]){
      if(enviados[item.sha256])continue;
      const arquivo=await conferirPendente(cfg,item);
      const resultado=await api('/automacao/malote/documentos',{documento:arquivo,grupo:item.grupo});
      if(resultado.sha256!==item.sha256 || !resultado.anexos?.length)throw Error('ANEXO_NAO_CONFIRMADO');
      enviados[item.sha256]={codigo:resultado.codigo,anexos:resultado.anexos,alertas:resultado.alertas};
      await salvar({...anterior,estado:'ANEXANDO',concluido:false,anexos_enviados:enviados});
    }
    if(modo==='--anexos-pendentes')return salvar({...anterior,estado:'ANEXOS_CONFIRMADOS',anexos_enviados:enviados,concluido:false});
    if(!estado.processo?.ativo || !estado.processo?.pode_agir || !estado.processo?.triagem || !estado.processo?.responsaveis_configurados)
      return salvar({estado:'CONFIGURACAO_PENDENTE',concluido:false,anexos_enviados:enviados});
    if(estado.despachante_parado)return salvar({estado:'DESPACHANTE_PARADO',concluido:false,anexos_enviados:enviados});
    const ultima=(estado.execucoes||[])[0];
    if(modo==='--agendado' && ultima?.iniciada_em?.startsWith(j.dia) && Number(ultima.iniciada_em.slice(11,13))>=8 &&
       ultima.situacao==='OK' && ultima.fluxo_com_triagem)
      return salvar({estado:'CONCLUIDO',concluido:true,execucao:ultima.id,anexos_enviados:enviados});
    const rodando=(estado.execucoes||[]).find(e=>e.situacao==='RODANDO');
    if(estado.processo.pedido_pendente && !rodando)
      return salvar({...anterior,estado:'AGUARDANDO_RODADA',concluido:false,anexos_enviados:enviados});
    let ticket=anterior.ticket;
    if(rodando)ticket={chave:`acompanhar-${rodando.id}`,anterior:rodando.id-1,execucao:rodando.id};
    else if(!ticket || anterior.execucao){ticket={chave:`malote-${j.dia}-${j.faixa}`};}
    // A intenção fica em disco ANTES do POST. Resposta perdida retoma a mesma
    // chave no servidor; não cria outro pedido por incerteza de transporte.
    await salvar({estado:'PEDINDO_RODADA',concluido:false,ticket,anexos_enviados:enviados});
    if(ticket.anterior===undefined){
      const r=await api('/automacao/malote/agente/rodada',{chave:ticket.chave,modo:'executar'});
      ticket={...ticket,anterior:r.anterior};
      await salvar({estado:'AGUARDANDO_RODADA',concluido:false,ticket,anexos_enviados:enviados});
    }
    const fim=Date.now()+(cfg.prazoRodadaMs||2100000);
    while(Date.now()<fim && !parar){
      const s=await api('/automacao/malote/agente');const r=conclusao(s,ticket.anterior,ticket.execucao??null);
      if(r)return salvar({...r,ticket,anexos_enviados:enviados});
      await pausa(cfg.intervaloConsultaMs||10000);
    }
    return salvar({estado:'AGUARDANDO_RODADA',concluido:false,ticket,anexos_enviados:enviados});
  } catch(e){
    const atual=await lerEstado(cfg);
    const nomes={'SESSAO_INVALIDA':'AGUARDANDO_LOGIN_SISTEMA','ATUALIZACAO_AUSENTE':'AGUARDANDO_ATUALIZACAO'};
    return salvar({...atual,estado:nomes[e.message]||'FALHA_PENDENTE',concluido:false});
  } finally {
    process.removeListener('SIGTERM',interromper);process.removeListener('SIGINT',interromper);
    try{if(context)await context.close();}finally{await fd.close();await fs.unlink(lock);}
  }
}
const direto=process.argv[1] && path.resolve(process.argv[1])===fileURLToPath(import.meta.url);
if(direto){
  try{const cfg=JSON.parse(await fs.readFile(process.argv[2],'utf8'));console.log(JSON.stringify(await executar(cfg,process.argv[3]||'--consultar')));}
  catch{console.log(JSON.stringify({estado:'CONFIGURACAO_INVALIDA',concluido:false}));process.exitCode=1;}
}
