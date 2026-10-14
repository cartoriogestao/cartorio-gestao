/* =========================================================================
   COLHER A FOTOGRAFIA DO CADASTRO — webcam no Chrome, no cartao de autografo.

   O QUE FAZ
       Liga a camera na tela do cartao, mostra o video, e o botao Colher
       grava um JPEG e envia no formulario que ja esta na pagina.

   SEM JAVASCRIPT CONTINUA FUNCIONANDO
       O formulario e um <form> de verdade, com arquivo e csrf. Sem este
       arquivo, o operador escolhe um JPEG e envia — perde a webcam, nao
       perde a funcao.

   SO AGE ONDE EXISTE `[data-captura-foto]`.
       Vai no base porque a lupa e o envio da ficha tambem vao. Ligada tela
       a tela, a proxima tela de cadastro nasceria sem camera.

   POR QUE SEM BIBLIOTECA DE FORA
       Ha maquina na serventia que nao alcanca a internet. Biblioteca de CDN
       seria um envio que funciona no escritorio e falha no balcao.
   ========================================================================= */
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    Array.prototype.forEach.call(
      document.querySelectorAll("[data-captura-foto]"), ligar);
  });

  function ligar(raiz) {
    if (raiz.__capturaLigada) return;
    raiz.__capturaLigada = true;

    var video = raiz.querySelector("[data-camera]");
    var lona = raiz.querySelector("[data-quadro]");
    var recado = raiz.querySelector("[data-recado]");
    var botao = raiz.querySelector("[data-colher]");
    var entrada = raiz.querySelector('input[type="file"][name="foto"]');
    var formulario = raiz.closest("form") || raiz.querySelector("form");
    if (!formulario || !entrada) return;

    if (video && navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
      navigator.mediaDevices.getUserMedia({ video: true, audio: false })
        .then(function (fluxo) {
          video.srcObject = fluxo;
        })
        .catch(function (erro) {
          mostrarRecado(recado, recadoDaCamera(erro));
        });
    } else if (recado) {
      mostrarRecado(recado,
        "Este navegador nao oferece camera. Use o Google Chrome e permita " +
        "o acesso a camera nesta pagina.");
    }

    if (botao) {
      botao.addEventListener("click", function (ev) {
        if (video && video.srcObject && lona) {
          ev.preventDefault();
          colherWebcam(video, lona, entrada, formulario, recado);
          return;
        }
        if (entrada.files && entrada.files.length) {
          return;
        }
        ev.preventDefault();
        mostrarRecado(recado,
          "A camera ainda nao esta pronta. No Chrome, permita o acesso a " +
          "camera e espere a imagem aparecer antes de colher.");
      });
    }
  }

  function recadoDaCamera(erro) {
    var nome = (erro && erro.name) || "";
    if (nome === "NotAllowedError" || nome === "PermissionDeniedError") {
      return "O Chrome recusou a camera. Clique no cadeado ao lado do " +
        "endereco, permita o acesso a camera e recarregue a pagina.";
    }
    if (nome === "NotFoundError" || nome === "DevicesNotFoundError") {
      return "Nao achei webcam neste computador. Confira se a camera esta " +
        "ligada e tente de novo.";
    }
    return "Nao consegui ligar a camera. No Chrome, permita o acesso a " +
      "camera nesta pagina e tente de novo.";
  }

  function mostrarRecado(el, texto) {
    if (!el) return;
    el.hidden = false;
    el.textContent = texto;
    el.classList.add("ruim");
  }

  function colherWebcam(video, lona, entrada, formulario, recado) {
    var w = video.videoWidth || 0;
    var h = video.videoHeight || 0;
    if (!w || !h) {
      mostrarRecado(recado,
        "A imagem da camera ainda nao apareceu. Espere um instante e " +
        "colha de novo.");
      return;
    }
    lona.width = w;
    lona.height = h;
    lona.getContext("2d").drawImage(video, 0, 0);
    lona.toBlob(function (blob) {
      if (!blob) {
        mostrarRecado(recado,
          "A fotografia veio vazia. Colha de novo pela webcam e confirme " +
          "que a imagem apareceu na tela antes de gravar.");
        return;
      }
      try {
        var arquivo = new File([blob], "foto.jpg", { type: "image/jpeg" });
        var dt = new DataTransfer();
        dt.items.add(arquivo);
        entrada.files = dt.files;
      } catch (e) {
        mostrarRecado(recado,
          "Nao consegui montar o JPEG para enviar. Tente de novo no Chrome.");
        return;
      }
      formulario.submit();
    }, "image/jpeg", 0.92);
  }
})();
