// Portal e sessão fictícios: nenhum acesso ao TJMA, Chrome, cofre ou banco.
import { PORTAL } from '../tools/portal_selo_worker.mjs';
export function navegadorFicticio({ linhas = [], post, origem = 'http://127.0.0.1:8765',
  autenticado = true, csrf = 'csrf-ficticio', falharClique = false } = {}) {
  const dados = { emissoes: 0, segundasVias: 0, posts: 0, fechou: false };
  let resolver, novas = 0, corrente;
  const paginas = [];
  const abrirPdf = linha => {
    const p = { fechada: false, url: () => 'blob:' + PORTAL + '/ficticio',
      isClosed: () => p.fechada, waitForURL: async () => {},
      evaluate: async () => Array.from(Buffer.from(linha.pdf || '%PDF-ficticio', linha.pdf ? 'base64' : 'utf8')),
      close: async () => { p.fechada = true; } };
    paginas.push(p); resolver(p);
  };
  const botao = (linha, nome) => ({
    count: async () => nome === 'Emitir guia' ? Number(!linha.existente && linha.disponivel !== false) :
      nome === 'Ver Guias' ? Number(Boolean(linha.existente)) : 1,
    click: async () => {
      corrente = linha;
      if (nome === 'Emitir guia') {
        dados.emissoes++;
        if (falharClique) throw Error('CLIQUE_INTERROMPIDO');
        linha.existente = true; abrirPdf(linha);
      }
    }
  });
  const row = l => ({
    locator: () => ({ allTextContents: async () => [l.fundo, 'Normal', l.periodo || '01/10 a 31/10 (Outubro/2026)',
      '10/11/2026', '', '', '', l.valor || 'R$ 123,45', '', ''] }),
    getByRole: (_, { name } = {}) => botao(l, name),
  });
  const colecao = registros => ({
    all: async () => registros.map(row), count: async () => registros.length,
    getByRole: (...args) => row(registros[0]).getByRole(...args),
    filter: ({ has }) => colecao(registros.filter(l => has.name === l.fundo ||
      has.name === (l.periodo || '01/10 a 31/10 (Outubro/2026)') || has.name === 'Pendente')),
  });
  const portal = { endereco: PORTAL, url: () => portal.endereco, isClosed: () => false,
    goto: async u => { portal.endereco = u; return { status: () => 200 }; },
    getByRole: (role, opts = {}) => {
      if (role === 'cell' || role === 'columnheader') return opts;
      if (role === 'row') return colecao(linhas);
      if (role === 'button') return { click: async () => {} };
      return { waitFor: async () => {}, filter: () => ({ waitFor: async () => {},
        getByRole: () => colecao([corrente]) }) };
    },
    getByText: () => ({ click: async () => { dados.segundasVias++; abrirPdf(corrente); } }),
  };
  const sistema = { endereco: origem, url: () => sistema.endereco, isClosed: () => false,
    goto: async u => { sistema.endereco = autenticado ? new URL(new URL(u).pathname, origem).href : origem + '/login'; return { status: () => 200 }; },
    locator: () => ({ count: async () => Number(autenticado), inputValue: async () => csrf }),
    request: { post: async (...args) => { dados.posts++; return post(...args); } },
  };
  const context = { newPage: async () => { const p = novas++ === 0 ? portal : sistema; paginas.push(p); return p; },
    pages: () => paginas, waitForEvent: () => new Promise(r => { resolver = r; }),
    close: async () => { dados.fechou = true; } };
  return { dados, portal, sistema, abrir: async () => context,
    examinarPortal: async p => ({ autenticado: p === portal }) };
}
