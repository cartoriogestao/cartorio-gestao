/* =========================================================================
   A LUPA — ver a assinatura de perto, sem sair da tela.

   O PROBLEMA, EM UMA LINHA
       A assinatura aparecia numa miniatura de 200 pixels e era tudo o que
       havia: nao dava para ampliar, e nem clicar.

   POR QUE ISSO IMPORTA NO BALCAO
       Reconhecimento por semelhanca e o tabeliao confrontando o traco com o
       cartao de autografo. O que se confere e a inclinacao, o ponto onde a
       caneta levanta, o laco do sobrenome. Nada disso cabe em 200 pixels —
       e conferir mal e o unico defeito deste sistema que nao tem conserto
       depois, porque a firma ja saiu reconhecida.

   O QUE ESTE ARQUIVO FAZ
       Toda imagem marcada com `class="ampliavel"` passa a abrir sobreposta a
       tela: zoom pela roda do mouse, arrastar para mover, girar, inverter o
       contraste, baixar o original e — quando a pessoa tem mais de uma via no
       cartao — as duas lado a lado, com o mesmo zoom nas duas.

   COMO SE MARCA UMA IMAGEM (no template)
       <img class="ampliavel" src="...miniatura..."
            data-lupa-cheia="...mesma imagem, grande..."   (opcional)
            data-lupa-original="...arquivo como esta no disco..."  (opcional)
            data-lupa-titulo="RF210703-1.JPG"              (opcional)
            data-lupa-grupo="cartao-482">                  (opcional)

       Sem `data-lupa-cheia`, a lupa usa o proprio `src`. O grupo e o que
       liga as vias da mesma pessoa: e dele que saem as setas e o comparar.

   POR QUE SEM BIBLIOTECA DE FORA
       O sistema roda na rede da serventia e ha maquina que nao alcanca a
       internet. Biblioteca de CDN seria uma lupa que funciona no escritorio e
       falha no balcao — que e justamente onde ela precisa funcionar.

   POR QUE `transform` E NAO REDIMENSIONAR A IMAGEM
       `transform: scale()` roda na placa de video e nao pede nada de volta ao
       servidor. Ampliar 8x uma assinatura fica instantaneo mesmo no
       computador do balcao, que nao e novo.
   ========================================================================= */
(function () {
  "use strict";

  var ZOOM_MIN = 0.2;      // menor que isto ninguem consegue enxergar nada
  var ZOOM_MAX = 12;       // 12x ja mostra o grao do escaner; alem disso e ruido
  var PASSO = 1.25;        // quanto cada clique em + ou - multiplica

  var caixa = null;        // a sobreposicao inteira, construida uma vez so
  var paineis = [];        // os visores: um normal, dois no comparar
  var grupo = [];          // as imagens irmas (mesma pessoa, varias vias)
  var atual = 0;           // qual delas esta no painel da esquerda
  var comparando = false;

  var zoom = 1;            // multiplicador sobre o "cabe na tela" de cada painel
  var giro = 0;            // 0, 90, 180, 270
  var invertido = false;
  var arrastX = 0, arrastY = 0;

  // ---------------------------------------------------------------- coleta

  /* As imagens irmas da que foi clicada.

     Sem grupo declarado, a imagem e sozinha — e o comparar e as setas somem
     em vez de aparecerem sem servir para nada. */
  function irmas(img) {
    var g = img.getAttribute("data-lupa-grupo");
    if (!g) return [img];
    var achadas = document.querySelectorAll(
      '.ampliavel[data-lupa-grupo="' + g.replace(/"/g, '\\"') + '"]');
    return Array.prototype.slice.call(achadas);
  }

  function dados(img) {
    return {
      cheia: img.getAttribute("data-lupa-cheia") || img.getAttribute("src"),
      original: img.getAttribute("data-lupa-original") || "",
      titulo: img.getAttribute("data-lupa-titulo") ||
              img.getAttribute("alt") || "imagem"
    };
  }

  // -------------------------------------------------------------- montagem

  function botao(rotulo, dica, aoClicar, classe) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = "lupa-botao" + (classe ? " " + classe : "");
    b.innerHTML = rotulo;
    b.title = dica;
    b.setAttribute("aria-label", dica);
    b.addEventListener("click", function (e) {
      e.preventDefault();
      e.stopPropagation();
      aoClicar();
    });
    return b;
  }

  function montar() {
    if (caixa) return;

    caixa = document.createElement("div");
    caixa.className = "lupa";
    caixa.setAttribute("role", "dialog");
    caixa.setAttribute("aria-modal", "true");
    caixa.hidden = true;

    var barra = document.createElement("div");
    barra.className = "lupa-barra";

    var titulo = document.createElement("div");
    titulo.className = "lupa-titulo";
    barra.appendChild(titulo);

    var ferramentas = document.createElement("div");
    ferramentas.className = "lupa-ferramentas";

    ferramentas.appendChild(botao("&#8722;", "Afastar (tecla -)", function () {
      aplicarZoom(zoom / PASSO);
    }));

    var marcador = document.createElement("span");
    marcador.className = "lupa-marcador";
    ferramentas.appendChild(marcador);

    ferramentas.appendChild(botao("+", "Aproximar (tecla +)", function () {
      aplicarZoom(zoom * PASSO);
    }));
    ferramentas.appendChild(botao("Ajustar", "Voltar ao tamanho que cabe na tela (tecla 0)",
      ajustar));
    ferramentas.appendChild(botao("Girar", "Girar 90 graus (tecla G)", girarNoventa));

    var btInverter = botao("Contraste", "Inverter claro e escuro (tecla C)", function () {
      invertido = !invertido;
      btInverter.classList.toggle("ligado", invertido);
      desenhar();
    });
    ferramentas.appendChild(btInverter);

    var btComparar = botao("Comparar", "Ver duas vias lado a lado (tecla D)", function () {
      comparando = !comparando;
      btComparar.classList.toggle("ligado", comparando);
      zoom = 1;
      arrastX = arrastY = 0;
      montarPaineis();
    });
    btComparar.classList.add("lupa-comparar");
    ferramentas.appendChild(btComparar);

    var btBaixar = document.createElement("a");
    btBaixar.className = "lupa-botao lupa-baixar";
    btBaixar.textContent = "Baixar";
    btBaixar.title = "Salvar o arquivo como esta no disco";
    btBaixar.addEventListener("click", function (e) { e.stopPropagation(); });
    ferramentas.appendChild(btBaixar);

    ferramentas.appendChild(botao("&times;", "Fechar (Esc)", fechar, "lupa-fechar"));
    barra.appendChild(ferramentas);
    caixa.appendChild(barra);

    var palco = document.createElement("div");
    palco.className = "lupa-palco";
    caixa.appendChild(palco);

    var rodape = document.createElement("div");
    rodape.className = "lupa-rodape";
    rodape.innerHTML =
      '<span>Roda do mouse amplia &middot; arraste para mover &middot; ' +
      'duplo clique alterna 100% e ajustar &middot; setas trocam de via &middot; Esc fecha</span>';
    caixa.appendChild(rodape);

    var anterior = botao("&#8249;", "Via anterior (seta esquerda)", function () { andar(-1); }, "lupa-seta lupa-seta-esq");
    var proxima = botao("&#8250;", "Proxima via (seta direita)", function () { andar(1); }, "lupa-seta lupa-seta-dir");
    caixa.appendChild(anterior);
    caixa.appendChild(proxima);

    caixa.refs = {
      titulo: titulo, marcador: marcador, palco: palco, baixar: btBaixar,
      comparar: btComparar, inverter: btInverter,
      anterior: anterior, proxima: proxima
    };

    // Clicar no fundo fecha. No palco nao: ali se arrasta a imagem, e fechar
    // no fim de um arrasto seria a lupa se fechando sozinha.
    caixa.addEventListener("mousedown", function (e) {
      if (e.target === caixa) fechar();
    });

    document.body.appendChild(caixa);
    ligarTeclado();
  }

  // ---------------------------------------------------------------- visores

  /* Um visor: a moldura, a imagem, e o recado de quando ela nao abre. */
  function criarPainel(indice) {
    var painel = document.createElement("div");
    painel.className = "lupa-painel";

    var img = document.createElement("img");
    img.className = "lupa-imagem";
    img.alt = "";
    img.draggable = false;

    var recado = document.createElement("div");
    recado.className = "lupa-recado";
    recado.hidden = true;

    var etiqueta = document.createElement("div");
    etiqueta.className = "lupa-etiqueta";

    painel.appendChild(img);
    painel.appendChild(recado);
    painel.appendChild(etiqueta);

    var p = { el: painel, img: img, recado: recado, etiqueta: etiqueta,
              indice: indice, base: 1 };

    /* Arquivo que nao abre no navegador tem que dizer isso. Antes ficava o
       quadrado quebrado, e o operador nao sabia se era o cartao, a rede ou o
       sistema — que foi como as 3.637 assinaturas viraram "nao abre". */
    img.addEventListener("error", function () {
      var d = dados(grupo[p.indice]);
      img.hidden = true;
      recado.hidden = false;
      recado.innerHTML =
        "<strong>Este arquivo o navegador nao desenha.</strong><br>" +
        "<span class='lupa-nome'>" + escapar(d.titulo) + "</span><br>" +
        (d.original
          ? "<a class='lupa-botao' href='" + escapar(d.original) +
            "' target='_blank' rel='noopener'>Abrir o arquivo</a>"
          : "");
    });
    img.addEventListener("load", function () {
      img.hidden = false;
      recado.hidden = true;
      medir(p);
      desenhar();
    });

    return p;
  }

  function montarPaineis() {
    var palco = caixa.refs.palco;
    palco.innerHTML = "";
    paineis = [];

    var quantos = comparando && grupo.length > 1 ? 2 : 1;
    palco.classList.toggle("lupa-duplo", quantos === 2);

    for (var n = 0; n < quantos; n++) {
      // No comparar, o segundo painel comeca na via seguinte: e o que a
      // pessoa quer ver quando pede duas ao mesmo tempo.
      var indice = (atual + n) % grupo.length;
      var p = criarPainel(indice);
      paineis.push(p);
      palco.appendChild(p.el);
    }
    carregar();
  }

  function carregar() {
    paineis.forEach(function (p) {
      var d = dados(grupo[p.indice]);
      p.img.hidden = false;
      p.recado.hidden = true;
      p.img.src = d.cheia;
      p.etiqueta.textContent = d.titulo +
        (grupo.length > 1 ? "  (via " + (p.indice + 1) + " de " + grupo.length + ")" : "");
    });
    atualizarBarra();
  }

  function atualizarBarra() {
    var d = dados(grupo[atual]);
    var r = caixa.refs;
    r.titulo.textContent = d.titulo;
    if (d.original) {
      r.baixar.href = d.original;
      r.baixar.setAttribute("download", "");
      r.baixar.hidden = false;
    } else {
      r.baixar.hidden = true;
    }
    var varias = grupo.length > 1;
    r.comparar.hidden = !varias;
    r.anterior.hidden = !varias || comparando;
    r.proxima.hidden = !varias || comparando;
  }

  // ----------------------------------------------------------------- medida

  /* Quanto a imagem precisa encolher para caber inteira no painel.

     E POR PAINEL, E NAO UM SO PARA OS DOIS.
         Comparando duas vias de tamanhos diferentes, uma escala unica deixaria
         a menor num canto e a maior estourando a moldura. Cada painel tem a
         sua base; o zoom e um multiplicador sobre ela. Assim "2x" quer dizer
         "duas vezes o que cabe" nas duas imagens ao mesmo tempo, que e o que
         o olho espera quando compara. */
  function medir(p) {
    var caixaLargura = p.el.clientWidth - 24;
    var caixaAltura = p.el.clientHeight - 24;
    var w = p.img.naturalWidth || 1;
    var h = p.img.naturalHeight || 1;
    if (giro === 90 || giro === 270) { var t = w; w = h; h = t; }
    p.base = Math.min(caixaLargura / w, caixaAltura / h, 1);
    if (!isFinite(p.base) || p.base <= 0) p.base = 1;
  }

  function desenhar() {
    paineis.forEach(function (p) {
      var escala = p.base * zoom;
      p.img.style.transform =
        "translate(" + arrastX + "px," + arrastY + "px) " +
        "scale(" + escala + ") rotate(" + giro + "deg)";
      p.img.style.filter = invertido ? "invert(1)" : "";
      p.img.style.cursor = zoom > 1 ? "grab" : "zoom-in";
    });
    caixa.refs.marcador.textContent = Math.round(zoom * 100) + "%";
  }

  function aplicarZoom(novo, ancoraX, ancoraY) {
    novo = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, novo));
    if (novo === zoom) return;

    /* Ampliar mirando o ponteiro, e nao o centro.

       Sem isto, aproximar num canto da assinatura joga esse canto para fora
       da tela e a pessoa passa o zoom inteiro procurando de volta o traco que
       queria olhar. */
    if (ancoraX !== undefined) {
      var razao = novo / zoom;
      arrastX = ancoraX - (ancoraX - arrastX) * razao;
      arrastY = ancoraY - (ancoraY - arrastY) * razao;
    }
    zoom = novo;
    desenhar();
  }

  function ajustar() {
    zoom = 1;
    arrastX = arrastY = 0;
    desenhar();
  }

  /* Girar 90 graus — e MEDIR DE NOVO, que é a metade fácil de esquecer.

     Ficha deitada girada para a vertical passa a caber de outro jeito: o que
     era 900x320 vira 320x900. Sem refazer a conta do "cabe na tela", a imagem
     girada aparece cortada em cima e embaixo, e a pessoa acha que girar
     estragou alguma coisa.

     Era o que acontecia pelo botão. Pela tecla G, não — dois caminhos para a
     mesma ação, um deles certo. Agora é um só, e os dois chamam ele. */
  function girarNoventa() {
    giro = (giro + 90) % 360;
    arrastX = arrastY = 0;
    paineis.forEach(medir);
    desenhar();
  }

  function andar(passo) {
    if (grupo.length < 2) return;
    atual = (atual + passo + grupo.length) % grupo.length;
    paineis[0].indice = atual;
    zoom = 1; arrastX = arrastY = 0;
    carregar();
  }

  // ------------------------------------------------------------- interacao

  function ligarPalco() {
    var palco = caixa.refs.palco;

    palco.addEventListener("wheel", function (e) {
      e.preventDefault();
      var caixaPalco = palco.getBoundingClientRect();
      var cx = e.clientX - caixaPalco.left - caixaPalco.width / 2;
      var cy = e.clientY - caixaPalco.top - caixaPalco.height / 2;
      aplicarZoom(zoom * (e.deltaY < 0 ? PASSO : 1 / PASSO), cx, cy);
    }, { passive: false });

    var arrastando = false, partiuX = 0, partiuY = 0, moveu = false;

    palco.addEventListener("mousedown", function (e) {
      if (e.button !== 0) return;
      arrastando = true; moveu = false;
      partiuX = e.clientX - arrastX;
      partiuY = e.clientY - arrastY;
      palco.classList.add("arrastando");
      e.preventDefault();
    });

    window.addEventListener("mousemove", function (e) {
      if (!arrastando) return;
      arrastX = e.clientX - partiuX;
      arrastY = e.clientY - partiuY;
      moveu = true;
      desenhar();
    });

    window.addEventListener("mouseup", function () {
      if (!arrastando) return;
      arrastando = false;
      palco.classList.remove("arrastando");
      // Clique parado (sem arrastar) aproxima. E o gesto que todo mundo
      // tenta antes de procurar o botao.
      if (!moveu && zoom <= 1) aplicarZoom(2);
    });

    palco.addEventListener("dblclick", function (e) {
      e.preventDefault();
      if (zoom > 1) { ajustar(); }
      else { aplicarZoom(1 / (paineis[0] ? paineis[0].base : 1)); }  // 100% real
    });

    // Toque: um dedo arrasta, dois dedos ampliam.
    var toqueX = 0, toqueY = 0, distancia0 = 0, zoom0 = 1;
    palco.addEventListener("touchstart", function (e) {
      if (e.touches.length === 1) {
        toqueX = e.touches[0].clientX - arrastX;
        toqueY = e.touches[0].clientY - arrastY;
      } else if (e.touches.length === 2) {
        distancia0 = separacao(e.touches);
        zoom0 = zoom;
      }
    }, { passive: true });

    palco.addEventListener("touchmove", function (e) {
      if (e.touches.length === 1) {
        arrastX = e.touches[0].clientX - toqueX;
        arrastY = e.touches[0].clientY - toqueY;
        desenhar();
        e.preventDefault();
      } else if (e.touches.length === 2 && distancia0) {
        aplicarZoom(zoom0 * (separacao(e.touches) / distancia0));
        e.preventDefault();
      }
    }, { passive: false });
  }

  function separacao(toques) {
    var dx = toques[0].clientX - toques[1].clientX;
    var dy = toques[0].clientY - toques[1].clientY;
    return Math.sqrt(dx * dx + dy * dy);
  }

  function ligarTeclado() {
    document.addEventListener("keydown", function (e) {
      if (!caixa || caixa.hidden) return;
      var t = e.key;
      if (t === "Escape") { fechar(); }
      else if (t === "+" || t === "=") { aplicarZoom(zoom * PASSO); }
      else if (t === "-" || t === "_") { aplicarZoom(zoom / PASSO); }
      else if (t === "0") { ajustar(); }
      else if (t === "ArrowRight") { andar(1); }
      else if (t === "ArrowLeft") { andar(-1); }
      else if (t === "g" || t === "G") { girarNoventa(); }
      else if (t === "c" || t === "C") { caixa.refs.inverter.click(); }
      else if (t === "d" || t === "D") { if (grupo.length > 1) caixa.refs.comparar.click(); }
      else { return; }
      e.preventDefault();
    });
  }

  // ------------------------------------------------------------ abrir/fechar

  function abrir(img) {
    montar();
    grupo = irmas(img);
    atual = Math.max(0, grupo.indexOf(img));
    comparando = false;
    zoom = 1; giro = 0; invertido = false; arrastX = arrastY = 0;
    caixa.refs.inverter.classList.remove("ligado");
    caixa.refs.comparar.classList.remove("ligado");

    caixa.hidden = false;
    document.body.classList.add("lupa-aberta");
    montarPaineis();
    if (!caixa.ligado) { ligarPalco(); caixa.ligado = true; }
    desenhar();
  }

  function fechar() {
    if (!caixa) return;
    caixa.hidden = true;
    document.body.classList.remove("lupa-aberta");
  }

  function escapar(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  // ----------------------------------------------------------------- ligacao

  /* Um ouvinte so, no documento inteiro, e nao um por imagem.

     A tela de reconhecimento monta a lista depois da busca, e as telas do
     Registro de Imoveis carregam ficha por ficha. Ligando imagem por imagem
     na carga da pagina, tudo o que aparecesse depois ficaria sem lupa —
     silenciosamente, que e o pior jeito de nao funcionar. */
  document.addEventListener("click", function (e) {
    var img = e.target.closest && e.target.closest("img.ampliavel");
    if (!img) return;
    e.preventDefault();
    abrir(img);
  });

  // Recalcula o "cabe na tela" quando a janela muda de tamanho.
  window.addEventListener("resize", function () {
    if (!caixa || caixa.hidden) return;
    paineis.forEach(medir);
    desenhar();
  });
})();
