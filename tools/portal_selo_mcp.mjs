// MCP stdio estreito, compartilhável por Qwen, Claude e GPT com cliente MCP local.
import { createInterface } from 'node:readline';
import { execFile } from 'node:child_process';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const config = path.resolve(process.argv[2] || 'configuracao.json');
const worker = fileURLToPath(new URL('./portal_selo_worker.mjs', import.meta.url));
const nomes = { consultar_guias: '--consultar', executar_guias: '--executar', autenticar_navegador: '--autenticar' };
const tools = [
  { name: 'consultar_guias', description: 'Lê fundos e períodos disponíveis, sem emitir nem cadastrar.' },
  { name: 'executar_guias', description: 'Executa o fluxo autorizado: emitir PDF e cadastrar. O servidor aplica a regra FERJ/FERC; os fundos do Banco do Brasil ficam só cadastrados.' },
  { name: 'autenticar_navegador', description: 'Abre Chrome local para o usuário autorizar SafeID e os logins; nenhuma senha é devolvida ao modelo.' },
  { name: 'estado_rotina', description: 'Lê o resultado local da última segunda-feira, sem abrir navegador.' }
].map(t => ({ ...t, inputSchema: { type: 'object', properties: {}, additionalProperties: false } }));
let ocupada = false;
async function chamada(name, args) {
  if (!tools.some(t => t.name === name) || Object.keys(args || {}).length) throw Error('Ferramenta ou argumentos recusados.');
  if (name === 'estado_rotina') {
    const cfg = JSON.parse(await readFile(config, 'utf8'));
    return readFile(path.join(cfg.pastaDados, 'ultima-segunda.json'), 'utf8')
      .then(JSON.parse).catch(e => { if (e.code === 'ENOENT') return { estado: 'AINDA_NAO_EXECUTADA' }; throw e; });
  }
  if (ocupada) throw Error('O executor já está em uso.');
  ocupada = true;
  try {
    return await new Promise((resolve, reject) => execFile(process.execPath,
      [worker, config, nomes[name]], { timeout: name === 'autenticar_navegador' ? 1900000 : 900000, maxBuffer: 1024 * 1024 },
      (erro, stdout) => {
        if (erro) return reject(Error('A rotina não concluiu. Confira o estado e o diário local antes de repetir.'));
        try { resolve(JSON.parse(stdout)); } catch { reject(Error('Resposta inválida do executor.')); }
      }));
  } finally { ocupada = false; }
}
const send = obj => process.stdout.write(JSON.stringify(obj) + '\n');
createInterface({ input: process.stdin }).on('line', async line => {
  let p;
  try {
    p = JSON.parse(line);
    if (p.id === undefined) return;
    let result;
    if (p.method === 'initialize') result = { protocolVersion: p.params.protocolVersion,
      capabilities: { tools: {} }, serverInfo: { name: 'cartorio-guias', version: '1.0.0' } };
    else if (p.method === 'ping') result = {};
    else if (p.method === 'tools/list') result = { tools };
    else if (p.method === 'tools/call') {
      try { result = { content: [{ type: 'text', text: JSON.stringify(await chamada(p.params.name, p.params.arguments)) }] }; }
      catch { result = { isError: true, content: [{ type: 'text', text: 'Execução recusada ou incompleta. Confira a sessão e o diário local; não repita emissão incerta.' }] }; }
    } else return send({ jsonrpc: '2.0', id: p.id, error: { code: -32601, message: 'Método não disponível.' } });
    send({ jsonrpc: '2.0', id: p.id, result });
  } catch { if (p?.id !== undefined) send({ jsonrpc: '2.0', id: p.id, error: { code: -32602, message: 'Pedido inválido.' } }); }
});
