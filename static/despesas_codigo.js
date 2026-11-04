/* Leitura no servidor da casa; nenhum dado vai a site externo. */
(() => {
  'use strict';
  document.querySelectorAll('[data-leitor-pagamento]').forEach((leitor) => {
    const form = leitor.closest('form');
    const botao = leitor.querySelector('[data-ler-codigo]');
    const usar = leitor.querySelector('[data-usar-codigo]');
    const resultado = leitor.querySelector('[data-resultado-codigo]');
    let dados = null;
    let codigoLido = '';
    botao.addEventListener('click', async () => {
      botao.disabled = true;
      usar.hidden = true;
      dados = null;
      codigoLido = form.elements.codigo.value;
      resultado.textContent = 'Conferindo o código…';
      const corpo = new URLSearchParams();
      corpo.set('codigo', codigoLido);
      corpo.set('csrf_token', form.elements.csrf_token.value);
      try {
        const resposta = await fetch(leitor.dataset.url, {
          method: 'POST', credentials: 'same-origin',
          headers: {'Content-Type': 'application/x-www-form-urlencoded'}, body: corpo,
        });
        if (resposta.redirected) throw new Error('Sua sessão expirou. Entre novamente para conferir o código.');
        const lido = await resposta.json();
        if (!resposta.ok) throw new Error(lido.erro || 'Não foi possível ler o código.');
        if (form.elements.codigo.value !== codigoLido) throw new Error('O código mudou. Clique em Ler código novamente.');
        dados = lido;
        resultado.textContent = lido.forma_nome
          + (lido.valor ? ' · R$ ' + lido.valor : ' · valor não disponível no texto')
          + (lido.vencimento ? ' · vencimento sugerido: ' + lido.vencimento.split('-').reverse().join('/') : '')
          + '. ' + lido.aviso;
        usar.hidden = false;
      } catch (erro) {
        resultado.textContent = erro.message || 'Não foi possível ler. Confira sua conexão e tente novamente.';
      } finally { botao.disabled = false; }
    });
    usar.addEventListener('click', () => {
      if (!dados || form.elements.codigo.value !== codigoLido) {
        resultado.textContent = 'O código mudou. Clique em Ler código novamente.';
        usar.hidden = true;
        return;
      }
      form.elements.forma.value = dados.forma;
      if (dados.valor) form.elements.valor.value = dados.valor;
      if (dados.vencimento) form.elements.vencimento.value = dados.vencimento;
      resultado.textContent += ' Dados preenchidos. Confira o favorecido e o vencimento na fatura.';
      usar.hidden = true;
    });
  });
})();
