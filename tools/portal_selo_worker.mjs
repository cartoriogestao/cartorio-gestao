// Executor fixo: o LLM só solicita a rotina; nunca fornece código, URLs ou regras bancárias.
import fs from 'node:fs/promises';
import { realpathSync } from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

export const PORTAL = 'https://portalselo.tjma.jus.br';
export const FUNDOS = new Set(['FERJ', 'FERC', 'FADEP', 'FEMP', 'FERRFIS']);
export function centavos(s) {
  const m = String(s).match(/R\$\s*([\d.]+),(\d{2})/);
  if (!m) throw Error('Valor monetário não reconhecido.');
  return Number(m[1].replaceAll('.', '')) * 100 + Number(m[2]);
}
export function periodo(s) {
  const m = s.match(/(\d{2})\/(\d{2})\s+a\s+(\d{2})\/(\d{2}).*?(\d{4})/);
  if (!m) throw Error('Período não reconhecido.');
  const ano = Number(m[5]), anterior = Number(m[2]) > Number(m[4]) ? ano - 1 : ano;
  return { inicio: `${anterior}-${m[2]}-${m[1]}`, fim: `${ano}-${m[4]}-${m[3]}` };
}
export function confereLinha(g, linha) {
  return g.fundo === linha.fundo && g.inicio === linha.inicio && g.fim === linha.fim &&
    g.vencimento === linha.vencimento && g.valor_centavos === linha.valor;
}
export function janelaSegunda(agora = new Date()) {
  const p = new Intl.DateTimeFormat('en-US', { timeZone: 'America/Sao_Paulo', weekday: 'short',
    year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', hourCycle: 'h23' })
    .formatToParts(agora).reduce((a, x) => ({ ...a, [x.type]: x.value }), {});
  return { aberta: p.weekday === 'Mon' && Number(p.hour) >= 8, chave: `${p.year}-${p.month}-${p.day}` };
}
const dormir = ms => new Promise(r => setTimeout(r, ms));
async function gravar(file, obj) {
  const temp = file + '.tmp';
  await fs.writeFile(temp, JSON.stringify(obj, null, 2) + '\n', { mode: 0o600 });
  await fs.rename(temp, file);
}
async function autenticado(page, sistema = false) {
  if (sistema) return await page.locator('input[name="csrf_token"]').count() > 0 &&
    page.url().includes('/despesas/portal-selo');
  return await page.getByRole('link', { name: /SAIR/ }).count() > 0;
}
async function api(page, url, csrf, arquivo, conferir) {
  const r = await page.request.post(url, { headers: { Accept: 'application/json', 'X-CSRF-Token': csrf },
    multipart: { documento: { name: path.basename(arquivo), mimeType: 'application/pdf',
      buffer: await fs.readFile(arquivo) }, conferir: conferir ? '1' : '0' }, maxRedirects: 0 });
  if (!r.ok() || !(r.headers()['content-type'] || '').includes('application/json'))
    throw Error(`Importação recusada pelo sistema (HTTP ${r.status()}); confira a sessão e a atualização instalada.`);
  const data = await r.json();
  if (data.erro) throw Error('Importação recusada pelo sistema.');
  return data;
}

export async function executar(cfg, modo = '--consultar') {
  const require = createRequire(realpathSync(cfg.playwrightMcp));
  const { chromium } = require('playwright');
  const base = new URL(cfg.sistema);
  // Não recebe destino do modelo. HTTP local apenas com opção expressa na configuração.
  if (base.protocol !== 'https:' && !(cfg.httpRedePrivada === true &&
      /^(127\.0\.0\.1|localhost|100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.)/.test(base.hostname + '.')))
    throw Error('Use HTTPS ou configure expressamente o endereço privado da serventia.');
  const raiz = path.resolve(cfg.pastaDados);
  await fs.mkdir(raiz, { recursive: true, mode: 0o700 });
  const lock = path.join(raiz, 'executor.lock');
  let dono;
  try { dono = await fs.open(lock, 'wx', 0o600); }
  catch (e) { throw Error('Outra execução usa o perfil, ou há trava de execução interrompida. Confira antes de retomar.'); }
  await dono.writeFile(String(process.pid));
  let contexto;
  try {
    contexto = await chromium.launchPersistentContext(path.resolve(cfg.perfil), {
      channel: 'chrome', headless: false, acceptDownloads: true,
      ignoreDefaultArgs: ['--use-mock-keychain', '--password-store=basic']
    });
    const portal = await contexto.newPage(), sistema = await contexto.newPage();
    const destino = new URL('/administrativo/despesas/portal-selo', base).href;
    await Promise.all([portal.goto(PORTAL, { waitUntil: 'domcontentloaded' }),
      sistema.goto(destino, { waitUntil: 'domcontentloaded' })]);
    async function pronto() {
      // Usa apenas autofill já presente. Nunca lê ou exporta o valor da senha.
      if (!await autenticado(portal) && await portal.locator('input[type="password"]').count()) {
        const preenchida = await portal.locator('input[type="password"]').evaluate(el => Boolean(el.value));
        if (preenchida) await portal.getByRole('button', { name: 'Entrar', exact: true }).click();
      }
      return await autenticado(portal) && await autenticado(sistema, true);
    }
    if (modo === '--autenticar') {
      console.error('Conclua SafeID e os dois logins nas janelas do Chrome. Não envie senhas ao agente.');
      for (let n = 0; n < 360 && !await pronto(); n++) await dormir(5000);
    }
    // No modo agendado, o launchd tenta novamente em 30 min. Não fica preso entre semanas.
    if (!await pronto()) return { estado: 'AGUARDANDO_AUTORIZACAO', concluido: false };
    if (modo === '--autenticar') return { estado: 'AUTENTICADO', concluido: false };
    await portal.goto(PORTAL + '/#/gestao-fundos/repasses-pendentes');
    await portal.getByRole('table').waitFor({ timeout: 60000 });
    const linhas = [], resultados = [];
    for (const row of await portal.getByRole('row').all()) {
      const c = await row.locator('td').allTextContents();
      if (c.length < 10 || !FUNDOS.has(c[0].trim()) || c[1].trim() !== 'Normal') continue;
      const d = c[3].trim().split('/');
      linhas.push({ fundo: c[0].trim(), periodoPortal: c[2].trim(), ...periodo(c[2]), vencimento: `${d[2]}-${d[1]}-${d[0]}`,
        valor: centavos(c[7]), disponivel: await row.getByRole('button', { name: 'Emitir guia', exact: true }).count() > 0,
        existente: await row.getByRole('button', { name: 'Ver Guias', exact: true }).count() > 0 });
    }
    if (modo === '--consultar') return { estado: 'CONSULTA', linhas, concluido: false };
    const csrf = await sistema.locator('input[name="csrf_token"]').inputValue();
    for (const linha of linhas) {
      if (!linha.disponivel && !linha.existente) continue;
      const chave = `${linha.fundo}_${linha.inicio}_${linha.fim}`;
      const journal = path.join(raiz, chave + '.json'), pdf = path.join(raiz, chave + '.pdf');
      let estado = await fs.readFile(journal, 'utf8').then(JSON.parse).catch(e => {
        if (e.code === 'ENOENT') return {}; throw e;
      });
      if (estado.cadastrado) { resultados.push({ ...linha, id: estado.id, estado: 'JA_CADASTRADA' }); continue; }
      let temPdf = await fs.stat(pdf).then(x => x.isFile()).catch(() => false);
      if (!temPdf && estado.emissaoIniciada && !linha.existente) {
        resultados.push({ ...linha, estado: 'CONSULTAR_GUIA_EXISTENTE' }); continue;
      }
      if (!temPdf) {
        const row = portal.getByRole('row').filter({ has: portal.getByRole('cell', { name: linha.fundo, exact: true }) })
          .filter({ has: portal.getByRole('cell', { name: linha.periodoPortal, exact: true }) });
        if (await row.count() !== 1) throw Error('Linha da guia ambígua. Emissão interrompida para conferência.');
        let baixar;
        if (linha.existente) {
          // Fluxo medido: Ver Guias -> linha Pendente -> menu de ações -> 2ª Via.
          await row.getByRole('button', { name: 'Ver Guias', exact: true }).click();
          const tabela = portal.getByRole('table').filter({ has: portal.getByRole('columnheader', { name: 'Nº da guia', exact: true }) });
          await tabela.waitFor({ timeout: 90000 });
          const pendente = tabela.getByRole('row').filter({ has: portal.getByRole('cell', { name: 'Pendente', exact: true }) });
          if (await pendente.count() !== 1) {
            await portal.getByRole('button', { name: 'Fechar', exact: true }).click();
            resultados.push({ ...linha, estado: 'CONSULTAR_GUIA_EXISTENTE' }); continue;
          }
          await pendente.getByRole('button').click();
          baixar = portal.getByRole('link', { name: '2ª Via', exact: true });
        } else {
          // Intenção durável ANTES do efeito externo. Retomada incerta nunca reemite.
          await gravar(journal, { ...linha, emissaoIniciada: true });
          baixar = row.getByRole('button', { name: 'Emitir guia', exact: true });
        }
        const nova = contexto.waitForEvent('page', { timeout: 90000 });
        await baixar.click();
        const pagina = await nova;
        await pagina.waitForURL(u => u.href.startsWith('blob:' + PORTAL + '/'), { timeout: 90000 });
        const bytes = await pagina.evaluate(async () => {
          const b = await (await fetch(location.href)).arrayBuffer();
          if (b.byteLength > 2 * 1024 * 1024) throw Error('PDF excedeu 2 MB');
          return Array.from(new Uint8Array(b));
        });
        const conteudo = Buffer.from(bytes);
        if (!conteudo.subarray(0, 4).equals(Buffer.from('%PDF'))) throw Error('A resposta não é PDF.');
        await fs.writeFile(pdf, conteudo, { flag: 'wx', mode: 0o600 });
        await pagina.close();
        if (linha.existente) await portal.getByRole('button', { name: 'Fechar', exact: true }).click();
      }
      const lido = await api(sistema, destino, csrf, pdf, true);
      if (!confereLinha(lido, linha)) throw Error('PDF difere da linha do portal; cadastro interrompido.');
      const feito = await api(sistema, destino, csrf, pdf, false);
      estado = { ...linha, cadastrado: true, id: feito.id, situacao: feito.situacao,
        envio_solicitado: feito.envio_solicitado, atualizado: new Date().toISOString() };
      await gravar(journal, estado);
      resultados.push(estado);
    }
    const incompletos = resultados.some(r => r.estado === 'CONSULTAR_GUIA_EXISTENTE');
    return { estado: incompletos ? 'CONFERENCIA_NECESSARIA' : 'CONCLUIDO', resultados, concluido: !incompletos };
  } finally {
    if (contexto) await contexto.close();
    await dono.close(); await fs.unlink(lock);
  }
}

async function main() {
  const [arquivo, modo = '--consultar'] = process.argv.slice(2);
  if (!arquivo || !['--consultar', '--executar', '--autenticar', '--agendado'].includes(modo))
    throw Error('Uso: node portal_selo_worker.mjs configuracao.json [--consultar|--executar|--autenticar|--agendado]');
  const cfg = JSON.parse(await fs.readFile(arquivo, 'utf8'));
  if (['--executar', '--agendado'].includes(modo) && cfg.producaoLiberada !== true)
    return console.log(JSON.stringify({ estado: 'AGUARDANDO_ATUALIZACAO_E_VALIDACAO', concluido: false }));
  if (modo === '--agendado') {
    const janela = janelaSegunda();
    if (!janela.aberta) return console.log(JSON.stringify({ estado: 'FORA_DA_AGENDA' }));
    const marker = path.join(cfg.pastaDados, 'ultima-segunda.json');
    const anterior = await fs.readFile(marker, 'utf8').then(JSON.parse).catch(() => ({}));
    if (anterior.chave === janela.chave && anterior.concluido) return;
    const r = await executar(cfg, modo);
    await gravar(marker, { ...r, chave: janela.chave });
    console.log(JSON.stringify(r));
  } else console.log(JSON.stringify(await executar(cfg, modo)));
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url))
  main().catch(() => { console.error('ERRO_EXECUTOR: confira a sessão, o perfil e o diário local; não repita uma emissão incerta.'); process.exitCode = 1; });
