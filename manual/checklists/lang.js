(function () {
  var key = "cinema-player-manual-lang";

  function applyLang(code) {
    var lang = code === "de" ? "de" : "en";
    document.documentElement.lang = lang;
    try { localStorage.setItem(key, lang); } catch (e) {}
    var title = document.body.getAttribute(lang === "de" ? "data-title-de" : "data-title-en");
    if (title) document.title = title;
  }

  document.querySelectorAll("[data-set-lang]").forEach(function (button) {
    button.addEventListener("click", function () {
      applyLang(button.getAttribute("data-set-lang"));
    });
  });
  var printButton = document.querySelector("[data-print]");
  if (printButton) printButton.addEventListener("click", function () { window.print(); });

  var saved = null;
  try { saved = localStorage.getItem(key); } catch (e) {}
  var query = null;
  try { query = new URLSearchParams(location.search).get("lang"); } catch (e) {}
  if (query === "de" || query === "en") applyLang(query);
  else if (saved === "de" || saved === "en") applyLang(saved);
  else applyLang((navigator.language || "").toLowerCase().indexOf("de") === 0 ? "de" : "en");
})();
