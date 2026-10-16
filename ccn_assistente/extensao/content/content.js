/**
 * CG CCN Assistente — painel na aba do portal do CCN. 13/10/2026.
 *
 * Roda nos dois portais do CCN. A PRODUÇÃO foi ligada em 13/10/2026, quando
 * o oficial conseguiu a chave dela («consegui a chave da ccn, mas eh de
 * producao tbm»): ali o envio grava cadastro de verdade na base nacional, e
 * o painel diz isso em vermelho.
 * As chamadas ao CCN saem DESTA aba, com a sessão que o usuário abriu —
 * a Cloudflare já foi passada por ele. Nada disto contorna o desafio.
 *
 * Duas tarefas:
 *   1. Enviar um lote do Cartório Gestão (pelo código de envio):
 *      upload → importação → acompanhar → erros → resultado de volta ao CG.
 *   2. Consultar na base nacional (exportação). Com o CÓDIGO DA CONSULTA do
 *      Cartório Gestão (15/10/2026): busca quem tem cadastro com o CPF, traz
 *      a ficha atual de cada um e devolve tudo ao Cartório Gestão, que mostra
 *      e completa o cartão de firma. Só com o CPF (sem código), o resultado
 *      aparece aqui e não se grava. Cada chamada leva o seu X-Signature,
 *      assinado pelo A3 no serviço local; o PIN é digitado uma vez por clique.
 */
(function () {
  "use strict";
  const PRODUCAO = location.hostname === "pessoas.e-notariado.org.br";
  if (!PRODUCAO && location.hostname !== "pessoas-hml.e-notariado.org.br") return;
  if (document.getElementById("cg-ccn-assistente")) return;

  const ESPERA_MS = 5000;
  const PRAZO_MS = 20 * 60 * 1000;
  const FINAIS = ["Successful", "CompletedWithErrors", "Error", "Halted"];

  function el(tag, attrs, filhos) {
    const n = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([k, v]) => {
      if (k === "text") n.textContent = v;
      else n.setAttribute(k, v);
    });
    (filhos || []).forEach((c) => c && n.appendChild(c));
    return n;
  }
  function campo(rotulo, attrs) {
    const i = el("input", Object.assign({ autocomplete: "off", spellcheck: "false" }, attrs || {}));
    return { rotulo: el("label", { text: rotulo }, [i]), input: i };
  }
  function pedir(msg) {
    return new Promise((ok) =>
      chrome.runtime.sendMessage(msg, (r) =>
        ok(chrome.runtime.lastError ? { ok: false, erro: chrome.runtime.lastError.message } : r || {})
      )
    );
  }
  const dormir = (ms) => new Promise((ok) => setTimeout(ok, ms));

  // ---------------------------------------------------------- o painel
  const painel = el("div", { id: "cg-ccn-assistente" });
  painel.appendChild(el("h1", { text: "CG CCN Assistente" }));
  painel.appendChild(el("p", {
    class: PRODUCAO ? "aviso producao" : "aviso",
    text: PRODUCAO
      ? "PRODUÇÃO (" + location.hostname + "): o que se envia aqui grava cadastro DE VERDADE na base nacional do CCN."
      : "Homologação (" + location.hostname + "). Você já entrou no portal; o envio usa esta aba.",
  }));

  const chave = campo("X-Api-Key (a chave que o CNB deu ao cartório)", { type: "password" });
  const assinatura = campo("X-Subscription (o Id do cartório no CCN)");
  const appToken = campo("AppToken — a chave de exportação (só para consultar)", { type: "password" });
  const lembrar = el("label", { class: "linha" }, [
    el("input", { type: "checkbox", id: "cg-lembrar" }),
    document.createTextNode(" guardar as chaves até fechar o navegador"),
  ]);

  const codigo = campo("Código de envio (da tela do lote)", { placeholder: "12-ABCDEF0123" });
  const btnEnviar = el("button", { type: "button", class: "primario", text: "Enviar ao CCN" });

  const codigoConsulta = campo("Código da consulta (da tela «Consulta ao CCN»)", { placeholder: "C12-ABCDEF0123" });
  const cpf = campo("…ou só o CPF (o resultado fica só aqui)", { inputmode: "numeric" });
  const pin = campo("PIN do certificado A3 (só nesta assinatura — não se grava)", { type: "password" });
  const btnConsultar = el("button", { type: "button", text: "Assinar e consultar" });

  const status = el("pre", { class: "status", text: "Pronto." });
  const btnA3 = el("button", { type: "button", text: "Ver o A3" });
  const btnFechar = el("button", { type: "button", text: "Fechar" });

  [chave.rotulo, assinatura.rotulo, appToken.rotulo, lembrar,
   el("h2", { text: "1. Enviar lote do Cartório Gestão" }),
   codigo.rotulo, el("div", { class: "botoes" }, [btnEnviar]),
   el("h2", { text: "2. Consultar na base nacional (exportação)" }),
   codigoConsulta.rotulo, cpf.rotulo, pin.rotulo, el("div", { class: "botoes" }, [btnConsultar]),
   el("div", { class: "botoes" }, [btnA3, btnFechar]), status].forEach((n) => painel.appendChild(n));
  document.documentElement.appendChild(painel);

  function dizer(t) { status.textContent = t; }
  function mais(t) { status.textContent += "\n" + t; }

  pedir({ tipo: "cred_ler" }).then((c) => {
    if (c && c.ok && c.cred) {
      chave.input.value = c.cred.api_key || "";
      assinatura.input.value = c.cred.subscription || "";
      appToken.input.value = c.cred.app_token || "";
      document.getElementById("cg-lembrar").checked = true;
    }
  });
  function credenciais() {
    const cred = {
      api_key: chave.input.value.trim(),
      subscription: assinatura.input.value.trim(),
      app_token: appToken.input.value.trim(),
    };
    if (document.getElementById("cg-lembrar").checked) pedir({ tipo: "cred_gravar", cred });
    else pedir({ tipo: "cred_apagar" });
    return cred;
  }
  function cabecalhos(cred, extra) {
    const h = Object.assign({ Accept: "application/json" }, extra || {});
    if (cred.api_key) h["X-Api-Key"] = cred.api_key;
    if (cred.subscription) h["X-Subscription"] = cred.subscription;
    return h;
  }
  async function ccn(caminho, opcoes) {
    const r = await fetch(location.origin + caminho, Object.assign({ credentials: "include", cache: "no-store" }, opcoes));
    const texto = await r.text();
    let corpo = null;
    try { corpo = texto ? JSON.parse(texto) : null; } catch (e) { corpo = null; }
    if (!r.ok) {
      const msg = (corpo && (corpo.message || corpo.code)) || texto.slice(0, 300) || r.statusText;
      const erro = new Error("CCN respondeu HTTP " + r.status + " em " + caminho + ": " + msg);
      erro.http = r.status;
      throw erro;
    }
    return corpo;
  }

  // ---------------------------------------------------------- 1. o envio
  btnEnviar.addEventListener("click", async () => {
    const cred = credenciais();
    const cod = codigo.input.value.trim();
    if (!cod) { dizer("Cole o código de envio da tela do lote."); return; }
    dizer("Buscando o lote no Cartório Gestão…");
    const lote = await pedir({ tipo: "cg_lote", codigo: cod });
    if (!lote || lote.ok === false) { dizer("Não deu para buscar o lote: " + (lote && lote.erro)); return; }
    if (lote.host !== location.hostname) {
      dizer("Este lote é do ambiente " + lote.ambiente + " (" + lote.host + "), e esta aba é " +
            location.hostname + ". Abra o portal do ambiente certo.");
      return;
    }
    mais("Lote " + lote.lote_id + ": " + lote.quantidade + " pessoas, " +
         (lote.bytes / 1e6).toFixed(1) + " MB.");
    if (PRODUCAO && !lote.import_id && !window.confirm(
        "PRODUÇÃO: enviar " + lote.quantidade + " cadastro(s) à base nacional do CCN?")) {
      mais("Envio cancelado. Nada foi mandado ao CCN.");
      return;
    }
    const relatar = (dados) => pedir({ tipo: "cg_resultado", dados: Object.assign({ codigo: cod }, dados) });
    let upload = null, importacao = null;
    try {
      if (lote.import_id) {
        mais("Este lote já tem importação no CCN (" + lote.import_id + "). Só acompanho.");
        importacao = await ccn("/api/imports/" + lote.import_id, { headers: cabecalhos(cred) });
      } else {
        mais("Subindo o arquivo…");
        const bytes = Uint8Array.from(atob(lote.conteudo_b64), (c) => c.charCodeAt(0));
        const fd = new FormData();
        fd.append("file", new Blob([bytes], { type: lote.content_type }), lote.arquivo_nome);
        fd.append("name", lote.arquivo_nome);
        fd.append("contentType", lote.content_type);
        upload = await ccn("/api/uploads", { method: "POST", headers: cabecalhos(cred), body: fd });
        mais("Arquivo recebido pelo CCN (" + upload.id + "). Criando a importação…");
        importacao = await ccn("/api/imports", {
          method: "POST",
          headers: cabecalhos(cred, { "Content-Type": "application/json" }),
          body: JSON.stringify({ type: lote.tipo, upload: upload }),
        });
        await relatar({ upload, import: importacao });
      }
      const inicio = Date.now();
      while (!FINAIS.includes(importacao.status) && Date.now() - inicio < PRAZO_MS) {
        mais("Importação " + importacao.status + " — " + (importacao.processedRecords || 0) + "/" +
             (importacao.totalRecords || "?") + "…");
        await dormir(ESPERA_MS);
        importacao = await ccn("/api/imports/" + importacao.id, { headers: cabecalhos(cred) });
      }
      let erros = [];
      if (FINAIS.includes(importacao.status) && importacao.status !== "Successful") {
        erros = (await ccn("/api/imports/" + importacao.id + "/errors", { headers: cabecalhos(cred) })) || [];
      }
      const volta = await relatar({ upload, import: importacao, erros });
      if (!FINAIS.includes(importacao.status)) {
        mais("O CCN ainda está processando (" + importacao.status + "). Rode de novo com o mesmo código mais tarde: eu só acompanho.");
      } else {
        mais("CCN: " + importacao.status + ". No Cartório Gestão: " + (volta.aceitos || 0) + " aceitos, " +
             (volta.recusados || 0) + " recusados, " + (volta.duplicados || 0) + " iguais aos que o CCN já tinha.");
      }
      if (volta.ok === false) mais("O Cartório Gestão não gravou o resultado: " + volta.erro);
    } catch (e) {
      mais(String(e.message || e));
      if (e.http === 401 || e.http === 403) mais("Confira a X-Api-Key e o X-Subscription.");
      const volta = await relatar({ upload, import: importacao, erro: String(e.message || e) });
      if (volta.ok === false) mais("E o Cartório Gestão não gravou a falha: " + volta.erro);
    }
  });

  // ---------------------------------------------------------- 2. a consulta
  // Cada chamada de exportação leva a SUA assinatura: o RequestPath entra no
  // que se assina. O Timestamp segue a forma do exemplo do contrato
  // («…+00:00»), e a ordem dos campos também.
  async function assinadoPara(caminho, senha) {
    const carga = JSON.stringify({ Timestamp: new Date().toISOString().replace("Z", "+00:00"), RequestPath: caminho });
    const sig = await pedir({ tipo: "assinar_cades", payload_utf8: carga, pin: senha });
    if (!sig || sig.ok === false) throw new Error("O A3 não assinou: " + (sig && sig.erro));
    return sig;
  }
  async function exportar(cred, caminho, senha) {
    const sig = await assinadoPara(caminho, senha);
    const h = cabecalhos(cred, { "X-Signature": sig.x_signature_b64 });
    if (cred.app_token) h.Authorization = "AppToken " + cred.app_token;
    return { corpo: await ccn(caminho, { headers: h }), assinante: sig.subject };
  }

  btnConsultar.addEventListener("click", async () => {
    const cred = credenciais();
    let senha = pin.input.value;
    pin.input.value = "";
    const cod = codigoConsulta.input.value.trim();
    let numero = cpf.input.value.replace(/\D/g, "");
    let pedido = null;
    if (cod) {
      dizer("Buscando a consulta no Cartório Gestão…");
      pedido = await pedir({ tipo: "cg_consulta", codigo: cod });
      if (!pedido || pedido.ok === false) { dizer("Não deu para buscar a consulta: " + (pedido && pedido.erro)); senha = ""; return; }
      if (pedido.host !== location.hostname) {
        dizer("Esta consulta é do ambiente " + pedido.ambiente + " (" + pedido.host + "), e esta aba é " +
              location.hostname + ". Abra o portal do ambiente certo.");
        senha = ""; return;
      }
      numero = pedido.cpf;
    }
    if (numero.length !== 11) { dizer("Cole o código da consulta, ou digite o CPF com 11 dígitos."); senha = ""; return; }
    if (!senha) { dizer("Digite o PIN do certificado A3."); return; }
    if (!cred.app_token) mais("Aviso: sem o AppToken (chave de exportação) o CCN deve recusar.");
    const devolver = (dados) => pedido
      ? pedir({ tipo: "cg_resultado", dados: Object.assign({ codigo: cod }, dados) })
      : Promise.resolve({ ok: true });
    try {
      dizer("Assinando no A3 e consultando o CPF…");
      const lista = await exportar(cred, "/api/exports/record-sets/" + numero, senha);
      const achados = lista.corpo || [];
      mais("Assinado por " + lista.assinante + ".");
      if (!achados.length) {
        mais("O CCN não tem cadastro com este CPF.");
        const v = await devolver({ achados: [], registros: [] });
        if (v.ok === false) mais("O Cartório Gestão não gravou: " + v.erro);
        return;
      }
      achados.forEach((a) => mais("• " + (a.name || "?") + " — " +
        ((a.notary && a.notary.name) || a.subscriptionName || "?") + " — atualizado em " +
        String(a.lastUpdate || "").slice(0, 10)));
      if (!pedido) { mais("(Sem código: nada foi gravado no Cartório Gestão.)"); return; }
      const registros = [];
      const teto = pedido.maximo_de_fichas || 5;
      for (const a of achados.slice(0, teto)) {
        mais("Trazendo a ficha de " + ((a.notary && a.notary.name) || a.subscriptionName || a.id) + "…");
        registros.push((await exportar(cred, "/api/exports/record-sets/" + a.id + "/current", senha)).corpo);
      }
      if (achados.length > teto) mais("Há " + achados.length + " cadastros; trouxe os " + teto + " primeiros.");
      const v = await devolver({ achados, registros });
      if (v.ok === false) mais("O Cartório Gestão não gravou: " + v.erro);
      else mais("Pronto: " + registros.length + " ficha(s) no Cartório Gestão. Volte à tela da consulta e atualize.");
    } catch (e) {
      mais(String(e.message || e));
      if (e.http === 401 || e.http === 403) mais("Confira a X-Api-Key, o X-Subscription e o AppToken (chave de exportação).");
      const v = await devolver({ achados: [], registros: [], erro: String(e.message || e) });
      if (v.ok === false) mais("E o Cartório Gestão não gravou a falha: " + v.erro);
    } finally {
      senha = "";
    }
  });

  btnA3.addEventListener("click", async () => {
    dizer("Consultando o serviço A3…");
    const s = await pedir({ tipo: "a3_saude" });
    if (!s.ok) { dizer("O serviço A3 não está no ar: " + s.erro); return; }
    const c = await pedir({ tipo: "a3_certificados" });
    dizer("Serviço A3 no ar. " + (c.certificados && c.certificados.length
      ? "Certificados: " + c.certificados.map((x) => x.subject).join("; ")
      : "Nenhum certificado visível — o token está plugado?"));
  });
  btnFechar.addEventListener("click", () => painel.remove());
})();
