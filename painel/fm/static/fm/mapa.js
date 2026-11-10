/* Mapa das gestantes: calor classico (verde -> amarelo -> vermelho) pela densidade de PENDENTES, pinos grandes nas UBS
   e pontos pequenos por gestante (cor por situacao ou por UBS). Dados: /mapa/pontos.json (escopo aplicado no servidor). */
(function () {
  const SIT = { aceita: ["#16a34a", "aceita"], sem_cns: ["#d97706", "sem CNS"], fora_bolsa: ["#64748b", "fora do Bolsa"], sem_cpf: ["#dc2626", "sem CPF"], erro_api: ["#2563eb", "erro / aguardando"], pendente: ["#2563eb", "erro / aguardando"], fora_recorte: ["#94a3b8", "fora do recorte (DUM > 1 ano)"] };
  const PALETA = ["#e6194b", "#3cb44b", "#4363d8", "#f58231", "#911eb4", "#42d4f4", "#f032e6", "#bfef45", "#fabed4", "#469990", "#dcbeff", "#9a6324", "#800000", "#aaffc3", "#808000", "#ffd8b1", "#000075", "#a9a9a9", "#ffe119", "#1e40af", "#0f766e", "#be123c"];
  const mapa = L.map("mapa", { zoomControl: true }).setView([-19.47, -42.54], 12);
  mapa.createPane("calor"); mapa.getPane("calor").style.zIndex = 350;   // calor abaixo dos pontos e dos pinos (overlayPane = 400)
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "© OpenStreetMap" }).addTo(mapa);
  const pontos = L.layerGroup(), ubsLayer = L.layerGroup().addTo(mapa);
  let calor = null, dados = { casas: [], ubs: [] }, corUbs = {};
  const el = function (id) { return document.getElementById(id); };
  function corDe(p) { return el("m-cor").value === "ubs" ? (corUbs[p.u] || "#64748b") : (SIT[p.s] || SIT.pendente)[0]; }
  function raio() { const z = mapa.getZoom(); return z >= 16 ? 8 : z >= 14 ? 6 : z >= 13 ? 5 : 4; }
  function pinoUbs(u, cor, desloc) {
    // desloc: UBS no mesmo predio de outra (coordenadas a menos de 3 m) ganha o desenho do pino deslocado em pixels, para os dois ficarem visiveis e clicaveis em qualquer zoom
    const html = '<div class="pino-ubs"><span>' + u.n + "</span></div>", dx = desloc ? -30 : 0;
    const m = L.marker([u.lat, u.lon], { icon: L.divIcon({ className: "pino-ubs-wrap", html: html, iconSize: [34, 44], iconAnchor: [17 + dx, 44], popupAnchor: [-dx, -40] }), zIndexOffset: 1000 + (desloc ? 1 : 0) });
    m.on("add", function () { const e = m.getElement(); if (e) { const d = e.querySelector(".pino-ubs"); if (d) d.style.background = cor; } });
    m.bindTooltip(u.nome.replace(/^Unidade (B[aá]sica )?de Sa[uú]de (d[aeo]s? )?/i, "UBS "), { direction: "top", offset: [0, -42], permanent: mapa.getZoom() >= 14, className: "rotulo-ubs" });
    const pend = u.n - (u.aceita || 0) - (u.fora_recorte || 0), aguard = u.n - (u.no_mapa || 0) - (u.sem_end || 0);
    const rota = "https://www.google.com/maps/dir/?api=1&destination=" + u.lat + "," + u.lon,
          waze = "https://waze.com/ul?ll=" + u.lat + "%2C" + u.lon + "&navigate=yes",
          apple = "https://maps.apple.com/?daddr=" + u.lat + "," + u.lon + "&dirflg=d";
    m.bindPopup('<div class="popup-ubs">' + (u.foto ? '<img class="foto-ubs" src="/ubs/foto/' + u.cnes + '/" alt="Fachada da unidade" loading="lazy">' : "")
      + "<b>" + u.nome + "</b>" + (u.end ? '<div class="end-ubs">' + u.end + "</div>" : "")
      + "<div><b>" + u.n + " gestantes</b> da unidade: " + (u.aceita || 0) + " aceitas · " + pend + " pendentes" + (u.fora_recorte ? " · " + u.fora_recorte + " fora do recorte" : "") + "</div>"
      + "<div>pendentes: sem CNS " + (u.sem_cns || 0) + " · fora do Bolsa " + (u.fora_bolsa || 0) + " · sem CPF " + (u.sem_cpf || 0) + " · erro/aguardando " + ((u.erro_api || 0) + (u.pendente || 0)) + "</div>"
      + "<div>no mapa: " + (u.no_mapa || 0) + " · sem endereço no e-SUS: " + (u.sem_end || 0) + (aguard > 0 ? " · aguardando geocodificação: " + aguard : "") + "</div>"
      + '<div class="rotas-ubs"><span>Como chegar:</span> <a href="' + rota + '" target="_blank" rel="noopener">Google Maps</a> <a href="' + waze + '" target="_blank" rel="noopener">Waze</a> <a href="' + apple + '" target="_blank" rel="noopener">Apple Maps</a>'
      + (u.id ? ' · <a href="/ubs/' + u.id + '/">Detalhe da UBS</a>' : "") + "</div></div>", { maxWidth: 340, minWidth: 260 });
    return m;
  }
  function desenhar() {
    pontos.clearLayers(); ubsLayer.clearLayers();
    if (calor) { mapa.removeLayer(calor); calor = null; }
    const camada = el("m-camada").value, r = raio();
    if (camada !== "calor") {
      dados.casas.forEach(function (p) {
        const m = L.circleMarker([p.lat, p.lon], { radius: p.r ? r + 2 : r, color: p.r ? "#dc2626" : "#fff", weight: p.r ? 2.5 : 1, fillColor: corDe(p), fillOpacity: .9 });
        m.bindPopup("<b>" + (p.u || "") + "</b><br>Situação: " + (SIT[p.s] || SIT.pendente)[1] + "<br>Precisão do ponto: " + (p.p || "") + '<br><a href="/gestantes/' + p.id + '/">Abrir cadastro</a>');
        pontos.addLayer(m);
      });
      if (!mapa.hasLayer(pontos)) pontos.addTo(mapa);
    } else if (mapa.hasLayer(pontos)) mapa.removeLayer(pontos);
    if (camada !== "pontos") {
      const z = mapa.getZoom(), pend = dados.casas.filter(function (p) { return p.s !== "aceita" && p.s !== "fora_recorte"; }).map(function (p) { return [p.lat, p.lon, 0.6]; });
      const rr = parseInt(el("m-raio").value, 10) || 32, op = (100 - (parseInt(el("m-transp").value, 10) || 20)) / 100;
      calor = L.heatLayer(pend, { pane: "calor", radius: z >= 14 ? rr + 8 : rr, blur: Math.round(rr * .8), max: 1.0, minOpacity: Math.max(.05, op * (z >= 16 ? .3 : .5)), gradient: { 0.1: "#2563eb", 0.3: "#06b6d4", 0.5: "#22c55e", 0.7: "#facc15", 0.9: "#ef4444" } }).addTo(mapa);
      if (calor._canvas) calor._canvas.style.opacity = op;
    }
    const vistos = [];
    dados.ubs.forEach(function (u) {
      const perto = vistos.some(function (v) { return Math.abs(v.lat - u.lat) < 0.00003 && Math.abs(v.lon - u.lon) < 0.00003; }); vistos.push(u);
      ubsLayer.addLayer(pinoUbs(u, el("m-cor").value === "ubs" ? (corUbs[u.nome] || "#1e40af") : "#1e40af", perto));
    });
    legenda();
  }
  function legenda() {
    const box = el("m-legenda"); if (!box) return;
    box.textContent = "";
    const cont = {}; dados.casas.forEach(function (p) { cont[p.s] = (cont[p.s] || 0) + 1; });
    function linha(cor, texto, n, cls) {
      const d = document.createElement("div"), i = document.createElement("i"); if (cls) i.className = cls; if (cor) i.style.background = cor;
      d.appendChild(i); d.appendChild(document.createTextNode(texto + " "));
      if (n !== undefined) { const b = document.createElement("b"); b.textContent = n; d.appendChild(b); }
      box.appendChild(d);
    }
    if (el("m-cor").value === "ubs") {
      const porU = {}; dados.casas.forEach(function (p) { porU[p.u] = (porU[p.u] || 0) + 1; });
      Object.keys(porU).sort().forEach(function (u) { linha(corUbs[u] || "#64748b", u.replace(/^Unidade (B[aá]sica )?de Sa[uú]de (d[aeo]s? )?/i, ""), porU[u]); });
    } else {
      ["aceita", "sem_cns", "fora_bolsa", "sem_cpf", "erro_api", "fora_recorte"].forEach(function (s) { linha(SIT[s][0], SIT[s][1], (cont[s] || 0) + (s === "erro_api" ? (cont.pendente || 0) : 0)); });
    }
    const sep = document.createElement("div"); sep.className = "leg-sep"; box.appendChild(sep);
    linha(null, "anel vermelho = gestação de risco (hipertensão, diabetes ou múltipla)", undefined, "leg-risco");
    linha(null, "UBS (número = total de gestantes da unidade; clique para o detalhe)", undefined, "leg-ubs");
    if (el("m-camada").value !== "pontos") { const c = document.createElement("div"); c.className = "leg-calor"; c.appendChild(document.createElement("span")); c.appendChild(document.createTextNode(" densidade de pendentes: baixa → alta")); box.appendChild(c); }
  }
  function carregar() {
    const u = el("m-unidade").value, s = el("m-situacao").value;
    fetch("/mapa/pontos.json?unidade=" + encodeURIComponent(u) + "&situacao=" + encodeURIComponent(s), { credentials: "same-origin" })
      .then(function (r) { return r.json(); }).then(function (d) {
        dados = d; corUbs = {}; let i = 0;
        d.ubs.map(function (x) { return x.nome; }).concat(d.casas.map(function (p) { return p.u; })).filter(function (n, k, a) { return n && a.indexOf(n) === k; }).sort().forEach(function (n) { corUbs[n] = PALETA[i++ % PALETA.length]; });
        desenhar();
        const todos = d.casas.map(function (p) { return [p.lat, p.lon]; }).concat(d.ubs.map(function (x) { return [x.lat, x.lon]; }));
        if (todos.length) mapa.fitBounds(todos, { padding: [20, 20], maxZoom: 14 });
      });
  }
  ["m-unidade", "m-situacao"].forEach(function (id) { el(id).addEventListener("change", carregar); });
  ["m-camada", "m-cor"].forEach(function (id) { el(id).addEventListener("change", desenhar); });
  ["m-raio", "m-transp"].forEach(function (id) { el(id).addEventListener("input", desenhar); });
  mapa.on("zoomend", desenhar);
  carregar();
})();
