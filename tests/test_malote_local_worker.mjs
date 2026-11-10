import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import { janela,origemPermitida,conclusao,executar,gravar,conferirPendente } from '../tools/malote_local_worker.mjs';

const T=new Date('2026-11-10T12:00:00Z');
const pronto={versao_fluxo:1,processo:{ativo:true,pode_agir:true,triagem:true,responsaveis_configurados:true,pedido_pendente:false},despachante_parado:false,execucoes:[]};
async function caso(){const dir=await fs.mkdtemp(path.join(os.tmpdir(),'malote-local-'));return {dir,cfg:{sistema:'https://sistema.example',pastaDados:path.join(dir,'estado'),pastaDocumentos:dir,producaoLiberada:true,prazoRodadaMs:15,intervaloConsultaMs:1}};}
function navegador(resposta){
 const chamadas=[];let consultas=0;
 const json=value=>({ok:()=>true,headers:()=>({'content-type':'application/json'}),json:async()=>value});
 const page={
  goto:async()=>({status:()=>200}),
  url:()=> 'https://sistema.example/automacao/malote/agente',
  locator:()=>({first:()=>({inputValue:async()=> 'csrf-do-teste'})}),
  request:{
   get:async url=>{chamadas.push(['GET',url]);return json(resposta(++consultas));},
   post:async(url,op)=>{
    chamadas.push(['POST',url,op]);
    if(url.endsWith('/rodada'))return json({anterior:5});
    return json({sha256:op.multipart?.grupo,anexos:[1]});
   }
  }
 };
 return {chamadas,abrir:async()=>({newPage:async()=>page,close:async()=>{}})};
}
test('janela usa São Paulo, dias úteis e começa às 08h',()=>{
 assert.equal(janela(new Date('2026-11-10T10:59:00Z')).aberta,false);assert.equal(janela(new Date('2026-11-10T11:00:00Z')).aberta,true);
 assert.equal(janela(new Date('2026-11-14T15:00:00Z')).aberta,false);assert.equal(janela(T).dia,'2026-11-10');
});
test('origem é fixa; HTTP somente Tailscale expressamente habilitado',()=>{
 assert.equal(origemPermitida({sistema:'http://100.65.103.18:8765',httpRedePrivada:true}),'http://100.65.103.18:8765');
 for(const sistema of ['http://evil.example','http://100.128.1.1','http://100.65.1.1.evil.example','https://u:p@sistema.example','https://sistema.example/qualquer'])assert.throws(()=>origemPermitida({sistema,httpRedePrivada:true}));
 assert.throws(()=>origemPermitida({sistema:'http://100.65.103.18:8765'}));
});
test('só conclui rodada manual posterior ao pedido e sem fila pendente',()=>{
 assert.equal(conclusao({...pronto,execucoes:[{id:4,disparo:'MANUAL',situacao:'OK',terminada_em:'agora'}]},5),null);
 assert.equal(conclusao({...pronto,execucoes:[{id:6,disparo:'AGENDA',situacao:'OK',terminada_em:'agora'}]},5),null);
 assert.equal(conclusao({...pronto,execucoes:[{id:6,disparo:'MANUAL',situacao:'RODANDO'}]},5),null);
 assert.equal(conclusao({...pronto,execucoes:[{id:6,disparo:'MANUAL',situacao:'AVISO',terminada_em:'agora',precisa_mfa:true}]},5).estado,'AGUARDANDO_MFA_MALOTE');
});
test('sem liberação e fora de horário não abre navegador',async()=>{
 const {cfg}=await caso();const abrir=()=>{throw Error('não deveria abrir');};
 assert.equal((await executar({...cfg,producaoLiberada:false},'--executar',{abrir})).estado,'AGUARDANDO_IMPLANTACAO');
 assert.equal((await executar(cfg,'--agendado',{agora:new Date('2026-11-14T15:00:00Z'),abrir})).estado,'FORA_DO_HORARIO');
});
test('consulta não posta ciência; dia concluído não abre novamente',async()=>{
 const {cfg}=await caso(),b=navegador(()=>pronto);
 assert.equal((await executar(cfg,'--consultar',{...b,agora:T})).estado,'CONSULTADO');assert.equal(b.chamadas.some(c=>c[0]==='POST'),false);
 await gravar(path.join(cfg.pastaDados,'estado.json'),{dia:'2026-11-10',concluido:true});
 assert.equal((await executar(cfg,'--agendado',{agora:T,abrir:()=>{throw Error('não deve abrir');}})).concluido,true);
});
test('pedido tem intenção durável; resultado tardio é retomado sem novo POST',async()=>{
 const {cfg}=await caso(),b=navegador(i=>i===1?pronto:{...pronto,execucoes:[{id:6,disparo:'MANUAL',situacao:'OK',terminada_em:'agora'}]});
 let intencao;
 const abrir=async()=>{const c=await b.abrir();const p=await c.newPage();const post=p.request.post;
 p.request.post=async(...a)=>{intencao=JSON.parse(await fs.readFile(path.join(cfg.pastaDados,'estado.json')));return post(...a);};return c;};
 const r=await executar(cfg,'--executar',{agora:T,abrir});assert.equal(r.concluido,true);assert.equal(intencao.estado,'PEDINDO_RODADA');
 assert.match(intencao.ticket.chave,/malote-2026-11-10/);
 const outro=await caso();await gravar(path.join(outro.cfg.pastaDados,'estado.json'),{ticket:{chave:'malote-anterior',anterior:5}});
 const b2=navegador(()=>({...pronto,execucoes:[{id:6,disparo:'MANUAL',situacao:'OK',terminada_em:'agora'}]}));
 assert.equal((await executar(outro.cfg,'--executar',{...b2,agora:T})).concluido,true);assert.equal(b2.chamadas.some(c=>c[0]==='POST'),false);
});
test('manifesto impede troca de arquivo, hash divergente e caminho fora da pasta',async()=>{
 const {cfg,dir}=await caso();const data=Buffer.from('%PDF-ficticio');const file=path.join(dir,'ficticio.pdf');await fs.writeFile(file,data);
 const item={grupo:'81000000000001',sha256:crypto.createHash('sha256').update(data).digest('hex'),arquivo:file};
 assert.equal((await conferirPendente(cfg,item)).buffer.toString(),'%PDF-ficticio');
 await assert.rejects(conferirPendente(cfg,{...item,sha256:'a'.repeat(64)}));
 await assert.rejects(conferirPendente({...cfg,pastaDocumentos:cfg.pastaDados},item));
});
test('trava ocupada e falha após a intenção não permitem sucesso fictício',async()=>{
 const {cfg}=await caso();await fs.mkdir(cfg.pastaDados);await fs.writeFile(path.join(cfg.pastaDados,'executor.lock'),'ocupado');
 assert.equal((await executar(cfg,'--executar')).estado,'EXECUTOR_OCUPADO');await fs.unlink(path.join(cfg.pastaDados,'executor.lock'));
 const b=navegador(()=>pronto);const abrir=async()=>{const c=await b.abrir();const p=await c.newPage();p.request.post=async()=>{throw Error('rede indisponível');};return c;};
 const r=await executar(cfg,'--executar',{agora:T,abrir});assert.equal(r.concluido,false);assert.ok(r.ticket.chave);
});

test('rejeição de login não é repetida pela agenda nem pelo modelo',async()=>{
 const {cfg}=await caso();await gravar(path.join(cfg.pastaDados,'estado.json'),{estado:'LOGIN_RECUSADO',concluido:false});
 const abrir=()=>{throw Error('não deve abrir');};
 assert.equal((await executar(cfg,'--executar',{abrir})).estado,'LOGIN_RECUSADO');
 assert.equal((await executar(cfg,'--agendado',{agora:T,abrir})).estado,'LOGIN_RECUSADO');
});

test('a agenda do Mac acompanha a rodada do sistema sem criar outra',async()=>{
 const {cfg}=await caso(),exec={id:6,disparo:'AGENDA',situacao:'OK',terminada_em:'agora',iniciada_em:'2026-11-10T08:00:00',fluxo_com_triagem:true};
 const b=navegador(()=>({...pronto,execucoes:[exec]}));
 assert.equal((await executar(cfg,'--agendado',{...b,agora:T})).concluido,true);assert.equal(b.chamadas.some(c=>c[0]==='POST'),false);
 const outro=await caso(),b2=navegador(i=>({...pronto,execucoes:[i===1?{...exec,situacao:'RODANDO',terminada_em:null}:exec]}));
 assert.equal((await executar(outro.cfg,'--agendado',{...b2,agora:T})).concluido,true);assert.equal(b2.chamadas.some(c=>c[0]==='POST'),false);
});
