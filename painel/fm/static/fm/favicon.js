/* Favicon do painel: logotipo do municipio com um ponto de estado no canto (verde = rotina e coleta em dia; amarelo = atencao;
   vermelho pulsando = rotina parada ou coleta falhou). O estado vem de <body data-estado="ok|alerta|erro">, calculado no
   servidor. Pulsa so no vermelho, para quando a aba esta em segundo plano e respeita "reduzir movimento". */
(function () {
  const link = document.querySelector("link[rel='icon']"); if (!link) return;
  const estado = document.body.getAttribute("data-estado") || "ok";
  const cores = { ok: "#16a34a", alerta: "#f59e0b", erro: "#dc2626" };
  const reduz = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const img = new Image(); img.src = link.getAttribute("data-base") || link.getAttribute("href");
  img.onload = function () {
    const c = document.createElement("canvas"); c.width = 32; c.height = 32; const x = c.getContext("2d");
    function quadro(raio, alfa) {
      x.clearRect(0, 0, 32, 32); x.drawImage(img, 0, 0, 32, 32);
      if (raio > 0) { x.save(); x.globalAlpha = alfa; x.beginPath(); x.arc(25, 25, raio, 0, Math.PI * 2); x.fillStyle = cores[estado] || cores.ok; x.fill();
        x.lineWidth = 1.5; x.strokeStyle = "#fff"; x.stroke(); x.restore(); }
      return c.toDataURL("image/png");
    }
    const fixo = quadro(5.5, 1); link.setAttribute("href", fixo); link.setAttribute("type", "image/png");
    if (estado !== "erro" || reduz) return;
    const quadros = [quadro(5.5, 1), quadro(6.5, .9), quadro(7.5, .7), quadro(6.5, .9), quadro(5.5, 1), quadro(5.5, 1)];
    let i = 0, timer = null;
    function liga() { if (!timer) timer = setInterval(function () { link.setAttribute("href", quadros[i]); i = (i + 1) % quadros.length; }, 220); }
    function desliga() { if (timer) { clearInterval(timer); timer = null; } link.setAttribute("href", fixo); }
    document.addEventListener("visibilitychange", function () { document.hidden ? desliga() : liga(); });
    liga();
  };
})();
