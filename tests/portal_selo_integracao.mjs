// Harness de teste: navegador simulado, API Flask real e dados fictícios.
import { executar } from '../tools/portal_selo_worker.mjs';
import { navegadorFicticio } from './apoio_portal_selo_worker.mjs';
let entrada = '';
for await (const parte of process.stdin) entrada += parte;
const p = JSON.parse(entrada), cfg = { sistema: p.origem, httpRedePrivada: true,
  pastaDados: p.pastaDados, producaoLiberada: true };
let posts = 0;
const post = async (url, opts) => {
  posts++;
  const form = new FormData();
  form.append('documento', new Blob([opts.multipart.documento.buffer], { type: 'application/pdf' }), 'guia.pdf');
  form.append('conferir', opts.multipart.conferir);
  const r = await fetch(url, { method: 'POST', body: form, redirect: 'manual',
    headers: { ...opts.headers, Cookie: p.cookie } });
  return { ok: () => r.ok, status: () => r.status, headers: () => Object.fromEntries(r.headers), json: () => r.json() };
};
const linhas = [{ fundo: p.fundo, pdf: p.pdf }];
const nav = navegadorFicticio({ linhas, origem: p.origem, csrf: p.csrf, post });
const primeiro = await executar(cfg, '--executar', nav);
const outra = navegadorFicticio({ linhas, origem: p.origem, csrf: p.csrf,
  post: () => { throw Error('Retomada não deve repetir o cadastro.'); } });
const segundo = await executar(cfg, '--executar', outra);
console.log(JSON.stringify({ primeiro, segundo, posts,
  emissoes: nav.dados.emissoes + outra.dados.emissoes }));
