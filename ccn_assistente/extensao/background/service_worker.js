/**
 * CG CCN Assistente — service worker (MV3). 13/10/2026.
 *
 * Fala com DOIS endereços desta máquina, e só com eles:
 *   - o serviço A3 local (127.0.0.1:8766), que assina o X-Signature;
 *   - a ponte do Cartório Gestão (127.0.0.1:8765, ou 8899 no SANDBOX), que
 *     entrega o lote (ou a consulta, desde 15/10/2026) pelo código e recebe o resultado.
 * O CCN NÃO se chama daqui: quem chama é o content script, de dentro da aba
 * do portal — é lá que estão a Cloudflare já passada e a sessão do usuário.
 *
 * O PIN passa por aqui uma vez, vai ao serviço A3 e é apagado; não se grava.
 */

const A3_BASE = "http://127.0.0.1:8766";
const CG_PADRAO = "http://127.0.0.1:8765";
const CG_PERMITIDOS = ["http://127.0.0.1:8765", "http://127.0.0.1:8899"];

async function json(resposta, onde) {
  const texto = await resposta.text();
  try {
    return JSON.parse(texto);
  } catch (e) {
    throw new Error("resposta que não é JSON de " + onde + " (HTTP " + resposta.status + ")");
  }
}

async function cgBase() {
  const { cg_base } = await chrome.storage.local.get("cg_base");
  return CG_PERMITIDOS.includes(cg_base) ? cg_base : CG_PADRAO;
}

async function a3Saude() {
  const r = await fetch(A3_BASE + "/saude", { cache: "no-store" });
  return json(r, "serviço A3");
}

async function a3Certificados() {
  const r = await fetch(A3_BASE + "/certificados", { cache: "no-store" });
  return json(r, "serviço A3");
}

async function assinarCades(msg) {
  const corpo = {
    payload_utf8: msg.payload_utf8 || "",
    pin: msg.pin || "",
    thumbprint: msg.thumbprint || null,
    anexado: true,
  };
  msg.pin = "";
  let r;
  try {
    r = await fetch(A3_BASE + "/assinar/cades", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(corpo),
      cache: "no-store",
    });
  } finally {
    corpo.pin = "";
  }
  const dados = await json(r, "serviço A3");
  if (!r.ok || dados.ok === false) {
    return { ok: false, erro: dados.erro || ("HTTP " + r.status) };
  }
  return dados;
}

async function cgLote(codigo) {
  const base = await cgBase();
  const r = await fetch(base + "/ccn/ponte/lote?codigo=" + encodeURIComponent(codigo), {
    cache: "no-store",
    credentials: "omit",
  });
  return json(r, "Cartório Gestão");
}

async function cgConsulta(codigo) {
  const base = await cgBase();
  const r = await fetch(base + "/ccn/ponte/consulta?codigo=" + encodeURIComponent(codigo), {
    cache: "no-store",
    credentials: "omit",
  });
  return json(r, "Cartório Gestão");
}

async function cgResultado(dados) {
  const base = await cgBase();
  const r = await fetch(base + "/ccn/ponte/resultado", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(dados),
    cache: "no-store",
    credentials: "omit",
  });
  return json(r, "Cartório Gestão");
}

chrome.runtime.onMessage.addListener((msg, _sender, responder) => {
  (async () => {
    try {
      switch (msg && msg.tipo) {
        case "a3_saude":
          responder({ ok: true, dados: await a3Saude() });
          return;
        case "a3_certificados":
          responder(await a3Certificados());
          return;
        case "assinar_cades":
          responder(await assinarCades(msg));
          return;
        case "cg_lote":
          responder(await cgLote(msg.codigo || ""));
          return;
        case "cg_consulta":
          responder(await cgConsulta(msg.codigo || ""));
          return;
        case "cg_resultado":
          responder(await cgResultado(msg.dados || {}));
          return;
        case "cg_base":
          responder({ ok: true, base: await cgBase() });
          return;
        // As chaves do CCN ficam em storage.session: memória do navegador,
        // que se apaga ao fechá-lo. Não vão a disco nem ao Cartório Gestão.
        case "cred_ler": {
          const { ccn_cred } = await chrome.storage.session.get("ccn_cred");
          responder({ ok: true, cred: ccn_cred || null });
          return;
        }
        case "cred_gravar":
          await chrome.storage.session.set({ ccn_cred: msg.cred || {} });
          responder({ ok: true });
          return;
        case "cred_apagar":
          await chrome.storage.session.remove("ccn_cred");
          responder({ ok: true });
          return;
        default:
          responder({ ok: false, erro: "pedido desconhecido: " + (msg && msg.tipo) });
      }
    } catch (e) {
      responder({ ok: false, erro: (e && e.message) || String(e) });
    }
  })();
  return true;
});
