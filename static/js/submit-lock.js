// Çift gönderimi engeller: gönderirken düğme pasifleşir ve metni değişir.
(function () {
  var forms = document.querySelectorAll("form[data-submit-lock]");

  forms.forEach(function (form) {
    form.addEventListener("submit", function () {
      var button = form.querySelector("button[type=submit]");
      if (!button || button.disabled) return;
      button.dataset.label = button.textContent;
      button.textContent = form.dataset.loadingText || "Gönderiliyor…";
      button.setAttribute("aria-busy", "true");
      // Pasifleştirme submit olayı bittikten sonra yapılır, yoksa form gönderilmez.
      setTimeout(function () { button.disabled = true; }, 0);
    });
  });

  // Geri tuşuyla dönüldüğünde (bfcache) düğme kilitli kalmasın.
  window.addEventListener("pageshow", function (event) {
    if (!event.persisted) return;
    forms.forEach(function (form) {
      var button = form.querySelector("button[type=submit]");
      if (!button) return;
      button.disabled = false;
      button.removeAttribute("aria-busy");
      if (button.dataset.label) button.textContent = button.dataset.label;
    });
  });
})();
