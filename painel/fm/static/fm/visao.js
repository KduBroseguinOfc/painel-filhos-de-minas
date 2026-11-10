/* Gráficos da visão geral (Chart.js local). Cores seguem o tema; redesenha ao trocar o modo. */
(function () {
  const dados = JSON.parse(document.getElementById("dados-graficos").textContent);
  const graficos = [];
  function cor(v) { return getComputedStyle(document.documentElement).getPropertyValue(v).trim(); }
  function desenhar() {
    graficos.splice(0).forEach(function (g) { g.destroy(); });
    const texto = cor("--texto-2"), grade = cor("--grafico-grade");
    Chart.defaults.color = texto; Chart.defaults.font.family = "Inter, system-ui, sans-serif";
    const reduz = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const anim = reduz ? false : { duration: 600 };
    const C = { ok: cor("--ok"), aviso: cor("--aviso"), erro: cor("--erro"), neutro: cor("--texto-2"), azul: cor("--azul-med"), info: cor("--info") };
    const opts = function (extra) { return Object.assign({ responsive: true, maintainAspectRatio: false, animation: anim, plugins: { legend: { labels: { boxWidth: 12 } } }, scales: { x: { grid: { color: grade } }, y: { grid: { color: grade }, beginAtZero: true } } }, extra || {}); };
    const el = function (id) { return document.getElementById(id); };
    if (el("g-rosca")) graficos.push(new Chart(el("g-rosca"), { type: "doughnut", data: { labels: ["Sem CNS", "Fora do Bolsa", "Sem CPF", "Erro / aguardando"], datasets: [{ data: dados.rosca, backgroundColor: [C.aviso, C.neutro, C.erro, C.info], borderWidth: 0 }] }, options: { responsive: true, maintainAspectRatio: false, animation: anim, cutout: "65%", plugins: { legend: { position: "right", labels: { boxWidth: 12 } } } } }));
    if (el("g-evolucao")) graficos.push(new Chart(el("g-evolucao"), { type: "line", data: { labels: dados.dias, datasets: [
      { label: "Aceitas", data: dados.aceitas, borderColor: C.ok, backgroundColor: C.ok, tension: .3, pointRadius: 0 },
      { label: "Sem CNS", data: dados.sem_cns, borderColor: C.aviso, backgroundColor: C.aviso, tension: .3, pointRadius: 0 },
      { label: "Fora do Bolsa", data: dados.fora_bolsa, borderColor: C.neutro, backgroundColor: C.neutro, tension: .3, pointRadius: 0 },
      { label: "Sem CPF", data: dados.sem_cpf, borderColor: C.erro, backgroundColor: C.erro, tension: .3, pointRadius: 0 }] }, options: opts({ interaction: { mode: "index", intersect: false } }) }));
    if (el("g-rotinas")) graficos.push(new Chart(el("g-rotinas"), { type: "bar", data: { labels: dados.rotinas_h, datasets: [{ label: "Aceites na rotina", data: dados.rotinas_env, backgroundColor: C.azul, borderRadius: 4 }] }, options: opts({ plugins: { legend: { display: false } } }) }));
    if (el("g-ubs")) graficos.push(new Chart(el("g-ubs"), { type: "bar", data: { labels: dados.ubs_nomes, datasets: [{ label: "Pendentes", data: dados.ubs_pend, backgroundColor: C.aviso, borderRadius: 4 }] }, options: opts({ indexAxis: "y", plugins: { legend: { display: false } } }) }));
  }
  window.fmRedesenhar = desenhar;
  if (document.readyState === "complete") desenhar(); else window.addEventListener("load", desenhar);
})();
