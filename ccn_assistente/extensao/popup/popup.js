const sel = document.getElementById("cg");
chrome.storage.local.get("cg_base").then(({ cg_base }) => {
  if (cg_base) sel.value = cg_base;
});
sel.addEventListener("change", () => chrome.storage.local.set({ cg_base: sel.value }));

document.getElementById("btn").addEventListener("click", function () {
  const out = document.getElementById("out");
  out.textContent = "Consultando…";
  chrome.runtime.sendMessage({ tipo: "a3_saude" }, function (resp) {
    if (chrome.runtime.lastError) {
      out.textContent = chrome.runtime.lastError.message;
      return;
    }
    if (!resp || !resp.ok) {
      out.textContent = "O serviço A3 não respondeu: " + ((resp && resp.erro) || "?");
      return;
    }
    const d = resp.dados || {};
    out.textContent = "No ar. Driver: " + (d.driver || "—") + "\nCAdES: " + (d.cades ? "sim" : "não");
  });
});
