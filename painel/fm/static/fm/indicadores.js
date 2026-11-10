(function () {
  const d = JSON.parse(document.getElementById("dados-graficos").textContent);
  const cor = function (v) { return getComputedStyle(document.documentElement).getPropertyValue(v).trim(); };
  const graficos = [];
  function desenhar() {
    graficos.splice(0).forEach(function (g) { g.destroy(); });
    const texto = cor("--texto-2"), grade = cor("--grafico-grade");
    Chart.defaults.color = texto; Chart.defaults.font.family = "Inter, system-ui, sans-serif";
    const reduz = window.matchMedia("(prefers-reduced-motion: reduce)").matches, anim = reduz ? false : { duration: 600 };
    const C = { ok: cor("--ok"), aviso: cor("--aviso"), erro: cor("--erro"), neutro: cor("--texto-2"), azul: cor("--azul-med"), info: cor("--info"), dourado: cor("--dourado") };
    const base = function (extra) { return Object.assign({ responsive: true, maintainAspectRatio: false, animation: anim, plugins: { legend: { labels: { boxWidth: 12 } } }, scales: { x: { grid: { color: grade } }, y: { grid: { color: grade }, beginAtZero: true } } }, extra || {}); };
    const el = function (id) { return document.getElementById(id); };
    if (el("g-funil")) graficos.push(new Chart(el("g-funil"), { type: "bar", data: { labels: d.funil_rotulos, datasets: [{ data: d.funil, backgroundColor: [C.azul, C.azul, C.azul, C.info, C.ok], borderRadius: 6 }] }, options: base({ indexAxis: "y", plugins: { legend: { display: false } } }) }));
    if (el("g-capt")) graficos.push(new Chart(el("g-capt"), { type: "doughnut", data: { labels: d.capt_rotulos, datasets: [{ data: d.capt, backgroundColor: [C.ok, C.dourado, C.aviso, C.erro], borderWidth: 0 }] }, options: { responsive: true, maintainAspectRatio: false, animation: anim, cutout: "60%", plugins: { legend: { position: "right", labels: { boxWidth: 12 } } } } }));
    if (el("g-cons")) graficos.push(new Chart(el("g-cons"), { type: "bar", data: { labels: d.cons_rotulos, datasets: [{ label: "Gestantes", data: d.cons, backgroundColor: C.azul, borderRadius: 4 }] }, options: base({ plugins: { legend: { display: false } }, scales: { x: { title: { display: true, text: "consultas de pré-natal" }, grid: { color: grade } }, y: { grid: { color: grade }, beginAtZero: true } } }) }));
    if (el("g-fx")) graficos.push(new Chart(el("g-fx"), { type: "bar", data: { labels: d.fx_rotulos, datasets: [{ label: "Total", data: d.fx_total, backgroundColor: C.azul, borderRadius: 4 }, { label: "Pendentes", data: d.fx_pend, backgroundColor: C.aviso, borderRadius: 4 }] }, options: base() }));
    if (el("g-tri")) graficos.push(new Chart(el("g-tri"), { type: "bar", data: { labels: d.tri_rotulos, datasets: [{ label: "Total", data: d.tri_total, backgroundColor: C.azul, borderRadius: 4 }, { label: "Pendentes", data: d.tri_pend, backgroundColor: C.aviso, borderRadius: 4 }] }, options: base({ indexAxis: "y" }) }));
    if (el("g-tempo")) graficos.push(new Chart(el("g-tempo"), { type: "doughnut", data: { labels: d.tempo_rotulos, datasets: [{ data: d.tempo, backgroundColor: [C.ok, C.dourado, C.aviso, C.erro], borderWidth: 0 }] }, options: { responsive: true, maintainAspectRatio: false, animation: anim, cutout: "60%", plugins: { legend: { position: "right", labels: { boxWidth: 12 } } } } }));
    if (el("g-mes")) graficos.push(new Chart(el("g-mes"), { type: "bar", data: { labels: d.mes_rotulos, datasets: [{ label: "Entradas no painel", data: d.mes_entradas, backgroundColor: C.azul, borderRadius: 4 }, { label: "Aceites", data: d.mes_aceitas, backgroundColor: C.ok, borderRadius: 4 }] }, options: base() }));
    document.querySelectorAll(".cel-calor").forEach(function (c) { const i = parseFloat(c.getAttribute("data-int")) || 0; c.style.background = "rgba(30,64,175," + (0.08 + 0.72 * i).toFixed(2) + ")"; c.style.color = i > 0.45 ? "#fff" : ""; });
  }
  window.fmRedesenhar = desenhar;
  if (document.readyState === "complete") desenhar(); else window.addEventListener("load", desenhar);
  const sel = document.querySelector("select[data-submit]"); if (sel) sel.addEventListener("change", function () { sel.form.submit(); });
})();
