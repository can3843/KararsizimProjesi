(function () {
  var region = document.getElementById("toast-region");
  if (!region) return;

  function dismissLater(toast) {
    setTimeout(function () {
      toast.remove();
    }, 3000);
  }

  window.showToast = function (message, level) {
    var toast = document.createElement("div");
    toast.className = "toast toast--" + (level || "info");
    toast.setAttribute("role", "status");
    toast.textContent = message;
    region.appendChild(toast);
    dismissLater(toast);
  };

  region.querySelectorAll(".toast").forEach(dismissLater);
})();
