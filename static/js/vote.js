// JS kapalıyken form normal POST + yönlendirme ile çalışır; bu dosya yalnızca onu zenginleştirir.
(function () {
  var form = document.querySelector("[data-vote-form]");
  var article = document.querySelector(".poll-detail");
  if (!form || !article) return;

  var submitButton = form.querySelector("button[type=submit]");
  var token = form.querySelector("input[name=csrfmiddlewaretoken]").value;

  function selectedInput() {
    return form.querySelector("input[name=option_id]:checked");
  }

  var idleLabel = submitButton.textContent;

  function syncButton() {
    submitButton.disabled = !selectedInput();
  }

  function setBusy(busy) {
    submitButton.textContent = busy ? "Oy veriliyor…" : idleLabel;
    submitButton.toggleAttribute("aria-busy", busy);
    submitButton.disabled = busy || !selectedInput();
  }

  function setPercent(optionId, percent) {
    var row = article.querySelector('.option-row[data-option-id="' + optionId + '"]');
    var segment = article.querySelector('.decision-bar__segment[data-option-id="' + optionId + '"]');
    if (segment) segment.style.width = percent + "%";
    if (!row) return;
    var fill = row.querySelector(".option-row__fill");
    var label = row.querySelector(".option-row__percent");
    fill.style.width = percent + "%";
    fill.hidden = false;
    label.textContent = "%" + percent;
    label.hidden = false;
  }

  function showResults(data) {
    var labels = [];
    data.options.forEach(function (option) {
      if (option.percent === null) return;
      setPercent(option.id, option.percent);
      labels.push(option.text + " %" + option.percent);
      var row = article.querySelector('.option-row[data-option-id="' + option.id + '"]');
      if (!row) return;
      var voted = option.id === data.voted_option_id;
      row.classList.toggle("option-row--voted", voted);
      row.querySelector(".option-row__check").hidden = !voted;
    });

    article.querySelector("[data-bar]").setAttribute("aria-label", labels.join(", "));
    article.querySelector("[data-total]").textContent = data.total;
    var badge = article.querySelector("[data-badge]");
    badge.className = "badge badge--" + data.badge.level;
    badge.textContent = data.badge.text;
    var status = article.querySelector("[data-vote-status]");
    status.textContent = data.voted_option_id !== null ? "Oyunu verdin." : "Bu anket kapandı.";

    // Oy verildi ya da anket kapandı: seçim kontrollerini kaldır.
    article.querySelectorAll(".option-row__input").forEach(function (input) { input.remove(); });
    article.querySelectorAll(".option-row--votable").forEach(function (row) {
      row.classList.remove("option-row--votable");
    });
    form.querySelector(".vote-actions").hidden = true;

    // Odaktaki düğme kaybolacağı için klavye ve ekran okuyucu kullanıcısını sonuca taşı.
    status.setAttribute("tabindex", "-1");
    status.focus({ preventScroll: true });
  }

  form.addEventListener("change", syncButton);
  syncButton();

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    if (!selectedInput()) {
      window.showToast("Geçerli bir seçenek seç.", "error");
      return;
    }

    // Gövde, alanlar pasifleşmeden önce okunmalı: pasif alanlar forma dahil edilmez.
    var body = new FormData(form);
    setBusy(true);
    form.querySelectorAll("input[name=option_id]").forEach(function (input) { input.disabled = true; });
    fetch(form.action, {
      method: "POST",
      body: body,
      credentials: "same-origin",
      headers: {
        "X-CSRFToken": token,
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json",
      },
    })
      .then(function (response) {
        // JSON olmayan cevap (ör. süresi dolmuş CSRF jetonu için HTML 403 sayfası) boş veri sayılır.
        return response.json().catch(function () { return {}; }).then(function (data) {
          return { status: response.status, data: data };
        });
      })
      .then(function (result) {
        var data = result.data;
        if (result.status === 200) {
          showResults(data);
          window.showToast(data.message, "success");
        } else if (data.options && (data.voted_option_id !== null || !data.is_open)) {
          // 403/409: oy zaten verilmiş ya da anket kapanmış; sunucu güncel sonuçları döndürür.
          showResults(data);
          window.showToast(data.error, "error");
        } else {
          enableChoices();
          window.showToast(
            data.error || (result.status === 403
              ? "Oturum doğrulanamadı. Sayfayı yenileyip tekrar dene."
              : "Bir şeyler ters gitti. Tekrar dene."),
            "error"
          );
        }
      })
      .catch(function () {
        enableChoices();
        window.showToast("Bağlantı kurulamadı. İnternetini kontrol edip tekrar dene.", "error");
      });
  });

  function enableChoices() {
    form.querySelectorAll("input[name=option_id]").forEach(function (input) { input.disabled = false; });
    setBusy(false);
  }
})();
