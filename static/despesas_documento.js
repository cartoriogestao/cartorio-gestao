(() => {
  'use strict';
  document.querySelectorAll('[data-leitor-documento]').forEach((leitor) => {
    const form = leitor.closest('form');
    const ler = leitor.querySelector('[data-ler-documento]');
    const usar = leitor.querySelector('[data-usar-documento]');
    const resultado = leitor.querySelector('[data-resultado-documento]');
    const caixa = leitor.querySelector('[data-opcoes-documento]');
    const escolha = leitor.querySelector('[data-codigo-documento]');
    const anexo = leitor.querySelector('[data-anexo-pagamento]');
    let opcoes = [], origem = null;
    const atual = () => anexo ? anexo.value : form.elements.documento?.files?.[0];
    ler.addEventListener('click', async () => {
      opcoes = []; usar.hidden = caixa.hidden = true;
      origem = atual();
      if (!origem) { resultado.textContent = 'Escolha o documento da despesa primeiro.'; return; }
      ler.disabled = true; resultado.textContent = 'Lendo o documento e conferindo os códigos…';
      const corpo = new FormData();
      corpo.set('csrf_token', form.elements.csrf_token.value);
      if (!anexo) corpo.set('documento', origem);
      try {
        const resposta = await fetch(anexo ? origem : leitor.dataset.url,
          {method: 'POST', credentials: 'same-origin', body: corpo});
        if (resposta.redirected) throw new Error('Sua sessão expirou. Entre novamente.');
        const dados = await resposta.json();
        if (!resposta.ok) throw new Error(dados.erro || 'Não foi possível ler o documento.');
        if (origem !== atual()) throw new Error('O documento mudou. Leia novamente.');
        opcoes = dados.opcoes;
        escolha.replaceChildren();
        opcoes.forEach((item, indice) => {
          const option = document.createElement('option');
          option.value = String(indice);
          option.textContent = item.forma_nome + ' · página ' + item.pagina
            + (item.valor ? ' · R$ ' + item.valor : ' · valor não disponível no código');
          escolha.append(option);
        });
        resultado.textContent = dados.aviso;
        usar.hidden = caixa.hidden = !opcoes.length;
      } catch (erro) { resultado.textContent = erro.message || 'Falha na leitura. Tente novamente.'; }
      finally { ler.disabled = false; }
    });
    usar.addEventListener('click', () => {
      const item = opcoes[Number(escolha.value)];
      if (!item || origem !== atual()) {
        resultado.textContent = 'O documento mudou. Leia novamente.';
        usar.hidden = true; return;
      }
      form.elements.codigo.value = item.codigo;
      form.elements.forma.value = item.forma;
      if (item.valor) form.elements.valor.value = item.valor;
      if (item.vencimento) form.elements.vencimento.value = item.vencimento;
      resultado.textContent = 'Código preenchido. ' + item.aviso + ' Confira o favorecido antes de salvar e autorizar.';
      usar.hidden = true;
    });
  });
})();
