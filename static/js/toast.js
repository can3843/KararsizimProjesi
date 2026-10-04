document.querySelectorAll("#toast-region .toast").forEach(function (toast) {
  setTimeout(function () {
    toast.remove();
  }, 3000);
});
