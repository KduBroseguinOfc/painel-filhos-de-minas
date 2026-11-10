(function () {
  const d = JSON.parse(document.getElementById("dados-graficos").textContent);
  const cor = function (v) { return getComputedStyle(document.documentElement).getPropertyValue(v).trim(); };
  let g = null;
  function desenhar() {
    if (g) g.destroy();
    const texto = cor("--texto-2"), grade = cor("--grafico-grade"); Chart.defaults.color = texto; Chart.defaults.font.family = "Inter, system-ui, sans-serif";
    const reduz = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    g = new Chart(document.getElementById("g-rot"), { data: { labels: d.rotulos, datasets: [
      { type: "bar", label: "Aceites", data: d.enviados, backgroundColor: cor("--ok"), borderRadius: 4, yAxisID: "y" },
      { type: "line", label: "Duração (min)", data: d.minutos, borderColor: cor("--azul-med"), backgroundColor: cor("--azul-med"), tension: .3, pointRadius: 2, yAxisID: "y2" }] },
      options: { responsive: true, maintainAspectRatio: false, animation: reduz ? false : { duration: 600 }, interaction: { mode: "index", intersect: false },
        scales: { x: { grid: { color: grade } }, y: { grid: { color: grade }, beginAtZero: true, title: { display: true, text: "aceites" } }, y2: { position: "right", grid: { drawOnChartArea: false }, beginAtZero: true, title: { display: true, text: "minutos" } } } } });
  }
  window.fmRedesenhar = desenhar;
  if (document.readyState === "complete") desenhar(); else window.addEventListener("load", desenhar);
})();
