/* =========================================================================
   COLHER A DIGITAL NO LEITOR — HID DigitalPersona, pelo SDK web do fabricante.

   O QUE FAZ
       Na tela do cartao de autografo, o botao «Colher no leitor» de cada dedo
       pede ao leitor uma imagem PNG, poe a imagem no formulario que ja esta
       na pagina (marcado origem=LEITOR) e envia. Quem grava e o servidor, pela
       mesma rota do envio manual.

   QUEM FALA COM O APARELHO NAO E ESTE ARQUIVO
       E o cliente local do fabricante («HID DigitalPersona Lite Client»),
       instalado no Windows do balcao. O SDK web (`Fingerprint.WebApi`, dos
       arquivos que o TI instala no servidor) conversa com ele; este arquivo so
       usa a API do SDK. Sem o SDK carregado, ou sem o cliente respondendo, ou
       sem leitor na USB, a tela DIZ qual dos tres faltou e o botao fica
       desligado — o envio manual continua embaixo, como reserva.

   O QUE NAO SAI DAQUI
       Nada vai para o console nem para o armazenamento do navegador: dado
       biometrico e dado sensivel (LGPD art. 11). A imagem vai direto para o
       formulario, e dali para o servidor.

   SO AGE ONDE EXISTE `[data-leitor-digital]`.
   ========================================================================= */
(function () {
  "use strict";

  // O formato de imagem PNG no SDK web (`Fingerprint.SampleFormat.PngImage`).
  // Lido do proprio SDK quando ele existe; o 5 e so o reserva.
  var PNG_DO_SDK = 5;

  function iniciar() {
    Array.prototype.forEach.call(
      document.querySelectorAll("[data-leitor-digital]"), ligar);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", iniciar);
  } else {
    iniciar();
  }

  function ligar(raiz) {
    if (raiz.__leitorLigado) return;
    raiz.__leitorLigado = true;

    var estadoEl = raiz.querySelector("[data-leitor-estado]");
    var recadoEl = raiz.querySelector("[data-leitor-recado]");
    var pararBtn = raiz.querySelector("[data-leitor-parar]");
    var botoes = raiz.querySelectorAll("[data-leitor-colher]");
    var form = raiz.querySelector("form[data-leitor-form]");
    var campoDedo = form && form.querySelector('input[name="dedo"]');
    var campoDisp = form && form.querySelector('input[name="dispositivo"]');
    var campoArq = form && form.querySelector('input[type="file"][name="digital"]');

    var st = { api: null, uid: null, dedo: null, nome: null, colhendo: false };

    function estado(texto, classe) {
      if (!estadoEl) return;
      estadoEl.textContent = texto;
      estadoEl.setAttribute("data-situacao", classe || "");
    }

    function recado(texto, ruim) {
      if (!recadoEl) return;
      recadoEl.hidden = !texto;
      recadoEl.textContent = texto || "";
      recadoEl.classList.toggle("ruim", !!ruim);
    }

    function habilitar(sim) {
      Array.prototype.forEach.call(botoes, function (b) {
        b.disabled = !sim;
      });
    }

    habilitar(false);

    var FP = window.Fingerprint;
    if (!form || !campoArq || !campoDedo) {
      estado("A tela do leitor está incompleta. Use o envio manual.", "ruim");
      return;
    }
    if (!FP || typeof FP.WebApi !== "function") {
      estado(
        "Programa do leitor não carregado nesta tela: o SDK web do " +
        "fabricante não está instalado no servidor. Use o envio manual " +
        "abaixo de cada dedo.", "sem-sdk");
      return;
    }
    if (FP.SampleFormat && FP.SampleFormat.PngImage) {
      PNG_DO_SDK = FP.SampleFormat.PngImage;
    }

    var api;
    try {
      api = new FP.WebApi();
    } catch (e) {
      estado(semCliente(), "sem-cliente");
      return;
    }
    st.api = api;
    estado("Procurando o leitor...", "procurando");

    api.onDeviceConnected = function () { procurar(); };
    api.onDeviceDisconnected = function () {
      st.uid = null;
      st.colhendo = false;
      mostrarParar(false);
      procurar();
    };
    api.onCommunicationFailed = function () {
      st.uid = null;
      st.colhendo = false;
      mostrarParar(false);
      habilitar(false);
      estado(semCliente(), "sem-cliente");
    };
    api.onQualityReported = function (e) {
      if (!st.colhendo || !e) return;
      var nome = (FP.QualityCode && FP.QualityCode[e.quality]) || "";
      if (nome && nome !== "Good") {
        recado("A leitura não saiu boa (" + nome + "). Limpe o vidro do " +
          "leitor e o dedo, e ponha o " + st.nome + " de novo, sem apertar " +
          "demais.", true);
      }
    };
    api.onErrorOccurred = function () {
      st.colhendo = false;
      mostrarParar(false);
      recado("O leitor informou um erro na captura. Tente de novo; se " +
        "persistir, desligue e ligue o leitor na USB.", true);
    };
    api.onSamplesAcquired = function (s) { recebido(s); };

    procurar();

    Array.prototype.forEach.call(botoes, function (b) {
      b.addEventListener("click", function (ev) {
        ev.preventDefault();
        colher(b.getAttribute("data-dedo"), b.getAttribute("data-nome"));
      });
    });
    if (pararBtn) {
      pararBtn.addEventListener("click", function (ev) {
        ev.preventDefault();
        parar("Captura cancelada.");
      });
    }

    function semCliente() {
      return "O cliente do leitor (HID DigitalPersona) não respondeu neste " +
        "computador. Confira se ele está instalado e aberto, e recarregue a " +
        "página. Enquanto isso, use o envio manual.";
    }

    function procurar() {
      var p;
      try {
        p = api.enumerateDevices();
      } catch (e) {
        estado(semCliente(), "sem-cliente");
        return;
      }
      Promise.resolve(p).then(function (lista) {
        lista = lista || [];
        if (!lista.length) {
          st.uid = null;
          habilitar(false);
          estado("Leitor não conectado. Ligue o leitor na USB deste " +
            "computador; a tela percebe sozinha.", "sem-leitor");
          return;
        }
        st.uid = lista[0];
        if (campoDisp) campoDisp.value = String(st.uid).slice(0, 120);
        habilitar(!st.colhendo);
        estado("Leitor conectado. Escolha o dedo e clique em «Colher no " +
          "leitor».", "pronto");
      }, function () {
        st.uid = null;
        habilitar(false);
        estado(semCliente(), "sem-cliente");
      });
    }

    function colher(dedo, nome) {
      if (!st.uid) {
        recado("Não há leitor conectado: ligue o leitor na USB, ou use o " +
          "envio manual.", true);
        return;
      }
      if (st.colhendo) {
        recado("Já há uma captura em andamento (" + st.nome + "). Termine " +
          "ou cancele antes de colher outro dedo.", true);
        return;
      }
      st.dedo = dedo;
      st.nome = nome || ("dedo " + dedo);
      st.colhendo = true;
      habilitar(false);
      mostrarParar(true);
      recado("");
      estado("Ponha o " + st.nome + " no leitor...", "colhendo");
      Promise.resolve(api.startAcquisition(PNG_DO_SDK, st.uid)).then(
        null,
        function () {
          st.colhendo = false;
          mostrarParar(false);
          habilitar(!!st.uid);
          estado("O leitor não começou a captura. Tente de novo.", "ruim");
        });
    }

    function parar(texto) {
      var era = st.colhendo;
      st.colhendo = false;
      mostrarParar(false);
      if (era) {
        try { Promise.resolve(api.stopAcquisition(st.uid)).then(null, function () {}); }
        catch (e) { /* o leitor ja parou */ }
      }
      habilitar(!!st.uid);
      if (texto) estado(texto, "pronto");
    }

    function mostrarParar(sim) {
      if (pararBtn) pararBtn.hidden = !sim;
    }

    function recebido(s) {
      if (!st.colhendo) return;
      var b64 = null;
      try {
        var amostras = typeof s.samples === "string"
          ? JSON.parse(s.samples) : s.samples;
        var primeira = amostras && amostras[0];
        if (primeira && typeof primeira === "object" && primeira.Data) {
          primeira = primeira.Data;
        }
        b64 = urlParaBase64(String(primeira || ""));
      } catch (e) {
        b64 = null;
      }
      var dedo = st.dedo, nome = st.nome;
      parar(null);
      var bytes = b64 ? base64ParaBytes(b64) : null;
      if (!bytes || bytes.length < 8 || bytes[0] !== 0x89 || bytes[1] !== 0x50) {
        estado("A imagem do " + nome + " não veio como PNG. Colha de novo.",
          "ruim");
        return;
      }
      try {
        var arquivo = new File([bytes], "digital_" + dedo + ".png",
          { type: "image/png" });
        var dt = new DataTransfer();
        dt.items.add(arquivo);
        campoArq.files = dt.files;
      } catch (e) {
        estado("Não consegui montar a imagem para enviar. Use o Google " +
          "Chrome, ou o envio manual.", "ruim");
        return;
      }
      campoDedo.value = dedo;
      estado("Gravando a digital do " + nome + "...", "enviando");
      form.submit();
    }
  }

  // O SDK devolve a amostra em base64 «de URL» (- e _ no lugar de + e /, sem
  // o = do fim). O navegador decodifica o base64 comum.
  function urlParaBase64(s) {
    var b = s.replace(/-/g, "+").replace(/_/g, "/");
    while (b.length % 4) b += "=";
    return b;
  }

  function base64ParaBytes(b64) {
    var bin = atob(b64);
    var out = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out;
  }
})();
