import { createInterface } from 'node:readline';
import { execFile } from 'node:child_process';
import { fileURLToPath } from 'node:url';
const config=process.argv[2];
const worker=fileURLToPath(new URL('./malote_local_worker.mjs',import.meta.url));
const MODOS={estado_malote:'--estado',consultar_malote:'--consultar',executar_malote:'--executar',
  enviar_anexos_pendentes:'--anexos-pendentes',autenticar_sistema:'--autenticar'};
const descricoes={estado_malote:'Lê apenas o estado local, sem abrir navegador.',consultar_malote:'Consulta a configuração do Malote no sistema; não solicita ciência.',
  executar_malote:'Solicita o fluxo do Malote já autorizado no sistema, sem fornecer regras ou pessoas ao robô.',
  enviar_anexos_pendentes:'Vincula somente os PDFs e hashes do manifesto aprovado aos alertas existentes; não cadastra pessoas.',
  autenticar_sistema:'Abre o perfil próprio para o operador concluir o login/MFA; não devolve credenciais.'};
const tools=Object.keys(MODOS).map(name=>({name,description:descricoes[name],inputSchema:{type:'object',properties:{},additionalProperties:false}}));
let ocupado=false;
const send=x=>process.stdout.write(JSON.stringify(x)+'\n');
createInterface({input:process.stdin}).on('line',async line=>{
 let p;
 try{
  p=JSON.parse(line);if(p.id===undefined)return;
  let result;
  if(p.method==='initialize')result={protocolVersion:p.params.protocolVersion,capabilities:{tools:{}},serverInfo:{name:'cartorio-malote',version:'1.0.0'}};
  else if(p.method==='ping')result={};
  else if(p.method==='tools/list')result={tools};
  else if(p.method==='tools/call'){
   const a=p.params?.arguments;
   if(!Object.hasOwn(MODOS,p.params?.name)||(a!==undefined && (a===null||typeof a!=='object'||Array.isArray(a)||Object.keys(a).length))||ocupado)
    result={isError:true,content:[{type:'text',text:'Pedido recusado ou executor ocupado.'}]};
   else{
    ocupado=true;
    try{const r=await new Promise((resolve,reject)=>execFile(process.execPath,[worker,config,MODOS[p.params.name]],
     {timeout:2200000,maxBuffer:1024*1024},(erro,stdout)=>{if(erro)return reject(erro);try{resolve(JSON.parse(stdout));}catch(e){reject(e);}}));
     result={content:[{type:'text',text:JSON.stringify(r)}]};
    }catch{result={isError:true,content:[{type:'text',text:'Não concluiu. Confira o estado local antes de repetir.'}]};}
    finally{ocupado=false;}
   }
  }else return send({jsonrpc:'2.0',id:p.id,error:{code:-32601,message:'Método não disponível.'}});
  send({jsonrpc:'2.0',id:p.id,result});
 }catch{if(p?.id!==undefined)send({jsonrpc:'2.0',id:p.id,error:{code:-32602,message:'Pedido inválido.'}});}
});
