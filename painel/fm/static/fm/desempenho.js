/* Gráficos do desempenho por UBS (Chart.js local). */
(function () {
  const dados = JSON.parse(document.getElementById("dados-graficos").textContent);
  const graficos = [];
  function cor(v) { return getComputedStyle(document.documentElement).getPropertyValue(v).trim(); }
  function desenhar() {
    graficos.splice(0).forEach(function (g) { g.destroy(); });
    Chart.defaults.color = cor("--texto-2"); Chart.defaults.font.family = "Inter, system-ui, sans-serif";
    const reduz = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const opts = { responsive: true, maintainAspectRatio: false, animation: reduz ? false : { duration: 600 }, indexAxis: "y",
      scales: { x: { grid: { color: cor("--grafico-grade") }, ticks: { precision: 0 } }, y: { grid: { display: false } } }, plugins: { legend: { labels: { boxWidth: 12 } } } };
    const el = function (id) { return document.getElementById(id); };
    if (el("g-res")) graficos.push(new Chart(el("g-res"), { type: "bar", data: { labels: dados.nomes, datasets: [{ label: "Resolvidas em 30 dias", data: dados.res30, backgroundColor: cor("--ok") }] }, options: opts }));
    if (el("g-pend")) graficos.push(new Chart(el("g-pend"), { type: "bar", data: { labels: dados.nomes, datasets: [
      { label: "Pendentes em curso", data: dados.curso, backgroundColor: cor("--aviso") },
      { label: "Resolvidas em 30 dias", data: dados.res30, backgroundColor: cor("--ok") }] }, options: opts }));
  }
  window.fmRedesenhar = desenhar;
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", desenhar); else desenhar();
})();
