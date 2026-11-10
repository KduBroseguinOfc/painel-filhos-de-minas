/* Painel Filhos de Minas: tema, menu no celular, contadores, revelar CPF, confirmação. Sem código inline (CSP). */
(function () {
  const html = document.documentElement;
  const LS = "fm-tema";
  function lerTema() { try { return localStorage.getItem(LS) || ""; } catch (e) { return ""; } }
  function aplicar(t) { if (t) html.setAttribute("data-theme", t); else html.removeAttribute("data-theme"); try { if (t) localStorage.setItem(LS, t); else localStorage.removeItem(LS); } catch (e) {} }
  aplicar(lerTema());
  const bt = document.getElementById("tema");
  if (bt) bt.addEventListener("click", function () { const t = lerTema(); aplicar(t === "" ? "dark" : t === "dark" ? "light" : ""); if (window.fmRedesenhar) window.fmRedesenhar(); });

  const menu = document.getElementById("menu"), lateral = document.getElementById("lateral"), sombra = document.getElementById("sombra");
  function fechar() { lateral.classList.remove("aberta"); sombra.hidden = true; menu.setAttribute("aria-expanded", "false"); }
  if (menu) { menu.addEventListener("click", function () { const ab = lateral.classList.toggle("aberta"); sombra.hidden = !ab; menu.setAttribute("aria-expanded", String(ab)); }); sombra.addEventListener("click", fechar); }

  const reduz = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  document.querySelectorAll("[data-contador]").forEach(function (el) {
    const fim = parseInt(el.getAttribute("data-contador"), 10); if (reduz || isNaN(fim) || fim < 20) return;
    const t0 = performance.now(), dur = 700, fmt = new Intl.NumberFormat("pt-BR");
    (function passo(t) { const p = Math.min((t - t0) / dur, 1), e = 1 - Math.pow(1 - p, 3); el.textContent = fmt.format(Math.round(fim * e)); if (p < 1) requestAnimationFrame(passo); })(t0);
  });

  const rev = document.getElementById("revelar");
  if (rev) rev.addEventListener("click", function () {
    if (!window.confirm(rev.getAttribute("data-confirmar"))) return;
    const csrf = (document.cookie.match(/csrftoken=([^;]+)/) || [])[1];
    fetch(rev.getAttribute("data-url"), { method: "POST", headers: { "X-CSRFToken": csrf }, credentials: "same-origin" })
      .then(function (r) { return r.json(); }).then(function (d) { const el = document.getElementById("cpf"); el.textContent = d.cpf.replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, "$1.$2.$3-$4"); const s = document.createElement("small"); s.className = "sub"; s.textContent = " revelado por " + d.usuario + " em " + d.registrado + " (registrado)"; el.after(s); rev.remove(); });
  });

  const pe = document.getElementById("id_por_email"), de = document.getElementById("detalhe-email");
  if (pe && de) { const f = function () { de.hidden = !pe.checked; }; pe.addEventListener("change", f); f(); }
  document.querySelectorAll("[data-largura]").forEach(function (el) { el.style.width = Math.max(0, Math.min(100, parseInt(el.getAttribute("data-largura"), 10) || 0)) + "%"; });
  document.querySelectorAll("form[data-confirmar]").forEach(function (f) { f.addEventListener("submit", function (ev) { if (!window.confirm(f.getAttribute("data-confirmar"))) ev.preventDefault(); }); });
  document.querySelectorAll("a[data-confirmar]").forEach(function (a) { a.addEventListener("click", function (ev) { if (!window.confirm(a.getAttribute("data-confirmar"))) ev.preventDefault(); }); });
  document.querySelectorAll("select[data-recarrega]").forEach(function (s) { s.addEventListener("change", function () { const f = s.form; f.querySelector("[name=equipe]").value = ""; f.submit(); }); });
})();
