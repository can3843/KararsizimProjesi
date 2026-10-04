// Paylaş butonu: destekleyen tarayıcıda sistem paylaşım menüsü, yoksa bağlantıyı panoya kopyalar.
// JS kapalıyken buton gizli kalır (sayfa adresi zaten adres çubuğunda).
(function () {
  var button = document.querySelector("[data-share]");
  if (!button) return;

  function copyFallback(url) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(url);
    }
    return Promise.reject(new Error("clipboard unavailable"));
  }

  button.hidden = false;
  button.addEventListener("click", function () {
    var url = button.dataset.url;
    var title = button.dataset.title;

    if (navigator.share) {
      navigator.share({ title: title, url: url }).catch(function (error) {
        // Kullanıcı menüyü kapattıysa sessiz kal; başka hatada panoya düş.
        if (error && error.name === "AbortError") return;
        copyFallback(url).then(
          function () { window.showToast("Bağlantı kopyalandı.", "success"); },
          function () { window.showToast("Bağlantı paylaşılamadı.", "error"); }
        );
      });
      return;
    }

    copyFallback(url).then(
      function () { window.showToast("Bağlantı kopyalandı.", "success"); },
      function () { window.showToast("Bağlantı kopyalanamadı. Adres çubuğundan kopyalayabilirsin.", "error"); }
    );
  });
})();
