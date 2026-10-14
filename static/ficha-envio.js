/* =========================================================================
   ENVIAR AS FICHAS DE FIRMA DIGITALIZADAS — escolher, endireitar, cortar, gravar.

   O QUE FALTAVA, NO COMEÇO
       Cartão de autógrafo aberto no balcão nascia sem autógrafo. As 3.637
       assinaturas do acervo vieram do E-Ofício; para as firmas NOVAS não havia
       botão nenhum — a ficha era assinada, digitalizada, e não tinha por onde
       entrar.

   O DEFEITO QUE ESTA VERSÃO CORRIGE
       A primeira versão aceitava vários arquivos, mas só sabia trabalhar com
       um. Escolhendo frente e verso e girando qualquer um dos dois, o envio
       fazia `FormData.delete("ficha")` e devolvia UM blob só — o outro arquivo
       sumia, sem erro, sem aviso, sem nada na tela.

       Isso é pior do que recusar o segundo arquivo: quem enviou viu os dois na
       tela, apertou Guardar, leu "ficha guardada" e foi embora. O verso do
       cartão simplesmente não existia.

       Agora há uma FILA. Cada arquivo tem o seu próprio giro, ângulo e corte, e
       o envio percorre a fila inteira — o que foi editado vai editado, o que
       não foi vai como veio, e nada some.

   COMO SE MARCA A ÁREA (no template)
       <section data-envio-ficha>
         <form ...>
           <div data-area><input type="file" name="ficha" multiple></div>
           <div data-fila></div>          <- as miniaturas da fila
           <div data-recado></div>
           <div data-editor> ... <canvas></canvas> </div>
           <button data-enviar></button>
         </form>
       </section>

   SEM JAVASCRIPT CONTINUA FUNCIONANDO
       O formulário é um `<form>` de verdade, com `enctype` e botão. Sem este
       arquivo, o operador escolhe os arquivos e envia — perde o endireitar e o
       cortar, não perde a função.

   POR QUE SEM BIBLIOTECA DE FORA
       Há máquina na serventia que não alcança a internet. Biblioteca de CDN
       seria um envio que funciona no escritório e falha no balcão.
   ========================================================================= */
(function () {
  "use strict";

  var LADO_MAXIMO = 2400;   // acima disto o arquivo cresce sem o traço melhorar
  var LIMITE_MB = 25;

  document.addEventListener("DOMContentLoaded", function () {
    Array.prototype.forEach.call(
      document.querySelectorAll("[data-envio-ficha]"), ligar);
  });

  function ligar(raiz) {
    /* UMA FILA POR PAINEL, E SÓ UMA.

       Ligar duas vezes o mesmo painel cria DUAS filas rivais: as duas escutam
       o mesmo `drop`, as duas guardam arquivos, e a que desenhar por último
       apaga a tela da outra. O operador solta frente e verso, vê um arquivo só
       aparecer, e não tem como saber que o outro está preso numa fila
       invisível.

       Peguei isso no teste — o jsdom dispara `DOMContentLoaded` uma segunda
       vez — mas o risco é real em qualquer situação que reinicialize a tela: o
       script incluído duas vezes por engano, ou um painel recarregado. Custa
       uma linha impedir, e o defeito que ela impede é mudo. */
    if (raiz.__envioLigado) return;
    raiz.__envioLigado = true;

    var entrada = raiz.querySelector('input[type="file"]');
    var area = raiz.querySelector("[data-area]");
    var faixaFila = raiz.querySelector("[data-fila]");
    var editor = raiz.querySelector("[data-editor]");
    var lona = raiz.querySelector("canvas");
    var recado = raiz.querySelector("[data-recado]");
    var botaoEnviar = raiz.querySelector("[data-enviar]");
    var formulario = raiz.closest("form") || raiz.querySelector("form");
    if (!entrada || !area || !lona || !formulario) return;

    var ctx = lona.getContext("2d");
    var fila = [];          // [{arquivo, imagem, giro, angulo, corte, erro}]
    var atual = -1;         // qual item está no editor
    var arrastandoCorte = null;

    // ------------------------------------------------------------ escolher

    /* ACUMULA, NÃO SUBSTITUI.

       Digitalizar a frente, escolher, digitalizar o verso, escolher de novo é
       o caminho mais comum no balcão — o scanner faz uma folha por vez. Se o
       segundo `escolher` apagasse o primeiro, a pessoa perderia o trabalho sem
       entender por quê. */
    entrada.addEventListener("change", function () {
      receber(entrada.files);
      // O input é zerado para o mesmo arquivo poder ser escolhido de novo
      // depois de removido da fila; a fila é que manda, daqui em diante.
      entrada.value = "";
    });

    area.addEventListener("click", function (e) {
      if (e.target.closest("button, input, label, .fila-item")) return;
      entrada.click();
    });

    ["dragenter", "dragover"].forEach(function (nome) {
      area.addEventListener(nome, function (e) {
        e.preventDefault();
        area.classList.add("sobre");
      });
    });
    ["dragleave", "drop"].forEach(function (nome) {
      area.addEventListener(nome, function (e) {
        e.preventDefault();
        area.classList.remove("sobre");
      });
    });
    area.addEventListener("drop", function (e) {
      if (e.dataTransfer && e.dataTransfer.files) receber(e.dataTransfer.files);
    });

    /* COLAR COM Ctrl+V — o caminho mais curto que existe aqui.
       Digitaliza, recorta na Ferramenta de Captura, cola. Cola de novo para o
       verso: entra como segundo item da fila. */
    document.addEventListener("paste", function (e) {
      if (!raiz.offsetParent) return;                 // painel fechado
      var itens = (e.clipboardData || {}).items || [];
      var achou = [];
      for (var n = 0; n < itens.length; n++) {
        if (itens[n].type && itens[n].type.indexOf("image/") === 0) {
          var f = itens[n].getAsFile();
          if (f) achou.push(f);
        }
      }
      if (achou.length) { receber(achou); e.preventDefault(); }
    });

    function receber(arquivos) {
      Array.prototype.forEach.call(arquivos, function (f) {
        if (!f) return;
        if (f.size > LIMITE_MB * 1024 * 1024) {
          dizer("<strong>" + escapar(f.name) + "</strong> tem " +
                (f.size / 1048576).toFixed(1) + " MB — o limite é " + LIMITE_MB +
                " MB. Digitalize em 200 ou 300 DPI, que basta para firma.", true);
          return;
        }
        var item = { arquivo: f, imagem: null, giro: 0, angulo: 0, corte: null,
                     erro: "" };
        fila.push(item);
        carregarPreview(item);
      });
      if (atual < 0 && fila.length) selecionar(0);
      desenharFila();
      atualizarBotao();
    }

    function ehPdf(f) {
      return /\.pdf$/i.test(f.name) || f.type === "application/pdf";
    }

    function carregarPreview(item) {
      var f = item.arquivo;
      if (ehPdf(f)) {
        item.erro = "pdf";      // o navegador não desenha PDF sem biblioteca
        desenharFila();
        return;
      }
      if (!/^image\//.test(f.type) &&
          !/\.(jpe?g|png|gif|bmp|webp|tiff?)$/i.test(f.name)) {
        item.erro = "tipo";
        desenharFila();
        return;
      }
      var url = URL.createObjectURL(f);
      var img = new Image();
      img.onload = function () {
        URL.revokeObjectURL(url);
        item.imagem = img;
        desenharFila();
        if (fila[atual] === item) mostrar(item);
      };
      img.onerror = function () {
        URL.revokeObjectURL(url);
        // TIFF é o caso: o scanner de mesa grava TIFF e navegador nenhum
        // desenha. Não é erro — o servidor converte — mas quem está na tela
        // precisa saber por que não está vendo a ficha antes de gravar.
        item.erro = "naodesenha";
        desenharFila();
        if (fila[atual] === item) mostrar(item);
      };
      img.src = url;
    }

    // ---------------------------------------------------------------- fila

    function desenharFila() {
      if (!faixaFila) return;
      faixaFila.innerHTML = "";
      faixaFila.hidden = fila.length === 0;
      fila.forEach(function (item, i) {
        var cartao = document.createElement("div");
        cartao.className = "fila-item" + (i === atual ? " atual" : "");
        cartao.tabIndex = 0;

        var mini = document.createElement("div");
        mini.className = "fila-mini";
        if (item.imagem) {
          var c = document.createElement("canvas");
          var w = 108, h = 74;
          c.width = w; c.height = h;
          var cc = c.getContext("2d");
          if (cc) {
            cc.fillStyle = "#fff"; cc.fillRect(0, 0, w, h);
            var escala = Math.min(w / item.imagem.naturalWidth,
                                  h / item.imagem.naturalHeight);
            var dw = item.imagem.naturalWidth * escala;
            var dh = item.imagem.naturalHeight * escala;
            cc.drawImage(item.imagem, (w - dw) / 2, (h - dh) / 2, dw, dh);
          }
          mini.appendChild(c);
        } else {
          mini.classList.add("sem-preview");
          mini.textContent = item.erro === "pdf" ? "PDF"
            : item.erro === "tipo" ? "?" : "TIFF";
        }
        cartao.appendChild(mini);

        var nome = document.createElement("div");
        nome.className = "fila-nome";
        // "frente" e "verso" são o caso de dois arquivos, que é o caso normal
        // de um cartão de autógrafo. Rotular ajuda a conferir antes de gravar.
        var rotulo = fila.length === 2 ? (i === 0 ? "frente · " : "verso · ") : "";
        nome.textContent = rotulo + item.arquivo.name;
        nome.title = item.arquivo.name;
        cartao.appendChild(nome);

        if (item.giro || item.angulo || item.corte) {
          var marca = document.createElement("span");
          marca.className = "fila-editado";
          marca.textContent = "ajustada";
          cartao.appendChild(marca);
        }
        if (item.erro === "tipo") {
          var ruim = document.createElement("span");
          ruim.className = "fila-editado ruim";
          ruim.textContent = "não aceito";
          cartao.appendChild(ruim);
        }

        var tirar = document.createElement("button");
        tirar.type = "button";
        tirar.className = "fila-tirar";
        tirar.innerHTML = "&times;";
        tirar.title = "Tirar da lista";
        tirar.addEventListener("click", function (e) {
          e.stopPropagation();
          fila.splice(i, 1);
          if (atual >= fila.length) atual = fila.length - 1;
          if (fila.length) selecionar(Math.max(0, atual)); else limparEditor();
          desenharFila();
          atualizarBotao();
        });
        cartao.appendChild(tirar);

        cartao.addEventListener("click", function () { selecionar(i); });
        faixaFila.appendChild(cartao);
      });
    }

    function selecionar(i) {
      atual = i;
      desenharFila();
      mostrar(fila[i]);
    }

    function limparEditor() {
      atual = -1;
      editor.hidden = true;
      dizer("");
      recado.hidden = true;
    }

    function mostrar(item) {
      if (!item) return limparEditor();
      if (item.imagem) {
        editor.hidden = false;
        var faixa = raiz.querySelector("[data-angulo]");
        if (faixa) { faixa.value = item.angulo; mostrarAngulo(item.angulo); }
        dizer("<strong>" + escapar(item.arquivo.name) + "</strong> — " +
              item.imagem.naturalWidth + "&times;" + item.imagem.naturalHeight +
              " pontos. Endireite e corte se precisar." +
              (fila.length > 1 ? " Os ajustes valem só para esta; as outras têm "
                                 + "os seus." : ""));
        desenhar();
      } else {
        editor.hidden = true;
        if (item.erro === "pdf") {
          dizer("<strong>" + escapar(item.arquivo.name) + "</strong> é PDF: vai " +
                "como está e o servidor converte para imagem ao guardar. " +
                "Endireitar e cortar só valem para foto ou digitalização em imagem.");
        } else if (item.erro === "tipo") {
          dizer("<strong>" + escapar(item.arquivo.name) + "</strong> não é imagem " +
                "nem PDF, e não vai ser enviada. Tire da lista e envie a ficha em " +
                "JPG, PNG ou PDF.", true);
        } else {
          dizer("Este formato o navegador não desenha, então não dá para " +
                "endireitar aqui — mas <strong>pode guardar assim mesmo</strong>: " +
                "o servidor converte, e a ficha vai aparecer no cartão.");
        }
      }
    }

    function atualizarBotao() {
      if (!botaoEnviar) return;
      var validas = fila.filter(function (i) { return i.erro !== "tipo"; }).length;
      botaoEnviar.disabled = validas === 0;
      botaoEnviar.textContent = validas > 1
        ? "Guardar " + validas + " fichas no cartão"
        : "Guardar no cartão";
    }

    function dizer(html, ruim) {
      if (!recado) return;
      if (!html) { recado.hidden = true; return; }
      recado.innerHTML = html;
      recado.hidden = false;
      recado.classList.toggle("ruim", !!ruim);
    }

    // ------------------------------------------------------------- desenhar

    function medidasGiradas(item) {
      var w = item.imagem.naturalWidth, h = item.imagem.naturalHeight;
      return (item.giro === 90 || item.giro === 270) ? { w: h, h: w } : { w: w, h: h };
    }

    function desenhar() {
      var item = fila[atual];
      if (!item || !item.imagem || !ctx) return;
      var m = medidasGiradas(item);
      var largura = Math.min(lona.parentNode.clientWidth || 700, 700);
      var escala = largura / m.w;
      lona.width = Math.round(m.w * escala);
      lona.height = Math.round(m.h * escala);

      ctx.save();
      ctx.fillStyle = "#fff";
      ctx.fillRect(0, 0, lona.width, lona.height);
      ctx.translate(lona.width / 2, lona.height / 2);
      ctx.rotate((item.giro + item.angulo) * Math.PI / 180);
      ctx.scale(escala, escala);
      ctx.drawImage(item.imagem, -item.imagem.naturalWidth / 2,
                    -item.imagem.naturalHeight / 2);
      ctx.restore();

      if (item.corte) {
        // Escurece o que fica de fora: o olho entende o recorte sem legenda.
        var c = item.corte;
        ctx.save();
        ctx.fillStyle = "rgba(12,20,28,.55)";
        var x = c.x * lona.width, y = c.y * lona.height;
        var w = c.w * lona.width, h = c.h * lona.height;
        ctx.fillRect(0, 0, lona.width, y);
        ctx.fillRect(0, y + h, lona.width, lona.height - y - h);
        ctx.fillRect(0, y, x, h);
        ctx.fillRect(x + w, y, lona.width - x - w, h);
        ctx.strokeStyle = "#7fc0e8";
        ctx.lineWidth = 2;
        ctx.strokeRect(x, y, w, h);
        ctx.restore();
      }
    }

    // ----------------------------------------------------------- ferramentas

    raiz.addEventListener("click", function (e) {
      var b = e.target.closest("[data-acao]");
      if (!b) return;
      e.preventDefault();
      var item = fila[atual];
      if (!item) return;
      var acao = b.getAttribute("data-acao");
      if (acao === "girar") {
        item.giro = (item.giro + 90) % 360;
        item.corte = null;
      } else if (acao === "limpar-corte") {
        item.corte = null;
      } else if (acao === "recomecar") {
        item.giro = 0; item.angulo = 0; item.corte = null;
        var faixa = raiz.querySelector("[data-angulo]");
        if (faixa) { faixa.value = 0; mostrarAngulo(0); }
      }
      desenhar();
      desenharFila();
    });

    var faixaAngulo = raiz.querySelector("[data-angulo]");
    if (faixaAngulo) {
      faixaAngulo.addEventListener("input", function () {
        var item = fila[atual];
        if (!item) return;
        item.angulo = parseFloat(faixaAngulo.value) || 0;
        mostrarAngulo(item.angulo);
        desenhar();
        desenharFila();
      });
    }
    function mostrarAngulo(v) {
      var alvo = raiz.querySelector("[data-angulo-valor]");
      if (alvo) alvo.textContent = (v > 0 ? "+" : "") + Number(v).toFixed(1) + "°";
    }

    // --------------------------------------------------------------- cortar

    function ponto(e) {
      var r = lona.getBoundingClientRect();
      var cx = (e.touches ? e.touches[0].clientX : e.clientX) - r.left;
      var cy = (e.touches ? e.touches[0].clientY : e.clientY) - r.top;
      return {
        x: Math.max(0, Math.min(1, cx / r.width)),
        y: Math.max(0, Math.min(1, cy / r.height))
      };
    }
    function comecarCorte(e) {
      var item = fila[atual];
      if (!item || !item.imagem) return;
      e.preventDefault();
      arrastandoCorte = ponto(e);
      item.corte = null;
    }
    function moverCorte(e) {
      var item = fila[atual];
      if (!arrastandoCorte || !item) return;
      e.preventDefault();
      var p = ponto(e);
      item.corte = {
        x: Math.min(arrastandoCorte.x, p.x), y: Math.min(arrastandoCorte.y, p.y),
        w: Math.abs(p.x - arrastandoCorte.x), h: Math.abs(p.y - arrastandoCorte.y)
      };
      desenhar();
    }
    function terminarCorte() {
      var item = fila[atual];
      if (!arrastandoCorte) return;
      arrastandoCorte = null;
      // Arrasto minúsculo é clique sem querer, e não recorte. Guardar um corte
      // de dois pixels apagaria a ficha inteira sem o operador entender.
      if (item && item.corte && (item.corte.w < 0.02 || item.corte.h < 0.02)) {
        item.corte = null;
      }
      desenhar();
      desenharFila();
    }

    lona.addEventListener("mousedown", comecarCorte);
    window.addEventListener("mousemove", moverCorte);
    window.addEventListener("mouseup", terminarCorte);
    lona.addEventListener("touchstart", comecarCorte, { passive: false });
    lona.addEventListener("touchmove", moverCorte, { passive: false });
    lona.addEventListener("touchend", terminarCorte);
    window.addEventListener("resize", desenhar);

    // --------------------------------------------------------------- enviar

    /* A imagem final, no tamanho de verdade — e não no tamanho da tela.

       O canvas da tela tem 700 pixels de largura porque é o que cabe. Gravar
       ESSE canvas jogaria fora a resolução da digitalização, que é justamente o
       que faz a conferência do traço ser possível. */
    function imagemFinal(item) {
      var m = medidasGiradas(item);
      var lonaCheia = document.createElement("canvas");
      lonaCheia.width = m.w;
      lonaCheia.height = m.h;
      var c = lonaCheia.getContext("2d");
      c.fillStyle = "#fff";
      c.fillRect(0, 0, m.w, m.h);
      c.translate(m.w / 2, m.h / 2);
      c.rotate((item.giro + item.angulo) * Math.PI / 180);
      c.drawImage(item.imagem, -item.imagem.naturalWidth / 2,
                  -item.imagem.naturalHeight / 2);

      var saida = lonaCheia;
      if (item.corte) {
        var r = document.createElement("canvas");
        r.width = Math.max(1, Math.round(item.corte.w * m.w));
        r.height = Math.max(1, Math.round(item.corte.h * m.h));
        r.getContext("2d").drawImage(
          lonaCheia, Math.round(item.corte.x * m.w), Math.round(item.corte.y * m.h),
          r.width, r.height, 0, 0, r.width, r.height);
        saida = r;
      }
      if (saida.width > LADO_MAXIMO || saida.height > LADO_MAXIMO) {
        var razao = LADO_MAXIMO / Math.max(saida.width, saida.height);
        var menor = document.createElement("canvas");
        menor.width = Math.round(saida.width * razao);
        menor.height = Math.round(saida.height * razao);
        menor.getContext("2d").drawImage(saida, 0, 0, menor.width, menor.height);
        saida = menor;
      }
      return saida;
    }

    function editada(item) {
      return item.imagem && (item.giro || item.angulo || item.corte);
    }

    formulario.addEventListener("submit", function (e) {
      var envia = fila.filter(function (i) { return i.erro !== "tipo"; });
      if (!envia.length) return;                 // deixa o navegador reclamar
      if (!envia.some(editada)) {
        // Nada foi ajustado: o caminho normal do navegador serve, MAS a fila
        // pode ter arquivos colados ou acumulados que não estão no input.
        if (envia.length === entrada.files.length) return;
      }

      e.preventDefault();
      if (botaoEnviar) {
        botaoEnviar.disabled = true;
        botaoEnviar.textContent = "Guardando...";
      }

      /* PERCORRE A FILA INTEIRA, e é o ponto desta versão.

         Antes: `dados.delete("ficha")` e um `append` só. Escolhendo frente e
         verso e girando qualquer um, o outro sumia — sem erro e sem aviso. */
      var dados = new FormData(formulario);
      dados.delete("ficha");
      var pendentes = envia.length;

      envia.forEach(function (item) {
        if (!editada(item)) {
          dados.append("ficha", item.arquivo, item.arquivo.name);
          if (--pendentes === 0) mandar(dados);
          return;
        }
        imagemFinal(item).toBlob(function (blob) {
          var nome = (item.arquivo.name || "ficha").replace(/\.[^.]+$/, "")
                     + "-ajustada.png";
          dados.append("ficha", blob, nome);
          if (--pendentes === 0) mandar(dados);
        }, "image/png");
      });
    });

    function mandar(dados) {
      fetch(formulario.action, {
        method: "POST", body: dados, credentials: "same-origin",
        headers: { "X-CSRF-Token": (dados.get("csrf_token") || "") }
      }).then(function (r) {
        window.location = r.redirected ? r.url : window.location.pathname;
      }).catch(function () {
        dizer("Não consegui falar com o servidor. <strong>Nada foi guardado</strong> " +
              "— confira a rede e tente de novo. Os arquivos continuam na lista.", true);
        atualizarBotao();
      });
    }
  }

  function escapar(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
})();
