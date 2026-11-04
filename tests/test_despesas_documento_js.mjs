import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const script=readFileSync(new URL('../static/despesas_documento.js',import.meta.url),'utf8');
const candidatos=[{forma:'BOLETO',forma_nome:'Boleto',codigo:'codigo-boleto-ficticio',valor:'123,45',vencimento:'2026-11-10',pagina:1,aviso:'Confira a fatura.'},
  {forma:'PIX_COPIA_E_COLA',forma_nome:'Pix',codigo:'codigo-pix-ficticio',valor:'',vencimento:'',pagina:2,aviso:'Valor dinamico.'}];
function tela(fetch) {
  const ler={addEventListener:(tipo,f)=>{ler[tipo]=f;}};
  const usar={hidden:true,addEventListener:(tipo,f)=>{usar[tipo]=f;}};
  const resultado={}, caixa={hidden:true},anexo={value:'/administrativo/despesas/1/ler-anexo/1'};
  const escolha={value:'0',opcoes:[],replaceChildren(){this.opcoes=[];},append(o){this.opcoes.push(o);}};
  const form={elements:{csrf_token:{value:'csrf-ficticio'},codigo:{value:'anterior'},forma:{value:'PIX_CHAVE'},valor:{value:'100,00'},vencimento:{value:'2026-11-09'}}};
  const seletores={'[data-ler-documento]':ler,'[data-usar-documento]':usar,'[data-resultado-documento]':resultado,
    '[data-opcoes-documento]':caixa,'[data-codigo-documento]':escolha,'[data-anexo-pagamento]':anexo};
  const leitor={dataset:{url:'/administrativo/despesas/ler-documento'},closest:()=>form,querySelector:s=>seletores[s]};
  vm.runInNewContext(script,{document:{querySelectorAll:()=>[leitor],createElement:()=>({})},fetch,FormData});
  return {ler,usar,resultado,form,anexo,escolha};
}
test('alternativas so preenchem o pagamento apos escolha explicita',async()=>{
  const t=tela(async(url,r)=>{
    assert.equal(url,'/administrativo/despesas/1/ler-anexo/1');
    assert.equal(r.body.get('csrf_token'),'csrf-ficticio');
    return {ok:true,json:async()=>({opcoes:candidatos,aviso:'Escolha um codigo.'})};
  });
  await t.ler.click();
  assert.equal(t.form.elements.codigo.value,'anterior');
  assert.equal(t.escolha.opcoes.length,2);
  t.escolha.value='1'; t.usar.click();
  assert.equal(t.form.elements.codigo.value,'codigo-pix-ficticio');
  assert.equal(t.form.elements.valor.value,'100,00');
  assert.equal(t.form.elements.vencimento.value,'2026-11-09');
});
test('troca de anexo depois da leitura impede usar resultado antigo',async()=>{
  const t=tela(async()=>({ok:true,json:async()=>({opcoes:candidatos,aviso:'Escolha.'})}));
  await t.ler.click();t.anexo.value='/outro-anexo';t.usar.click();
  assert.equal(t.form.elements.codigo.value,'anterior');
  assert.match(t.resultado.textContent,/documento mudou/);
});
test('sessao expirada nao fornece alternativas nem altera o formulario',async()=>{
  const t=tela(async()=>({redirected:true}));await t.ler.click();
  assert.equal(t.usar.hidden,true);assert.equal(t.ler.disabled,false);
  assert.equal(t.form.elements.codigo.value,'anterior');
});
