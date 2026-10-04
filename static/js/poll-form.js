// JS kapalıyken 5 satırın hepsi görünür; boş satırlar sunucuda yok sayılır.
(function () {
  var list = document.getElementById("option-list");
  var addButton = document.getElementById("add-option");
  if (!list || !addButton) return;

  var rows = Array.prototype.slice.call(list.querySelectorAll(".option-field"));
  var REQUIRED_ROWS = 2;

  function visibleCount() {
    return rows.filter(function (row) { return !row.hidden; }).length;
  }

  function refresh() {
    addButton.disabled = visibleCount() >= rows.length;
  }

  rows.forEach(function (row, index) {
    if (index < REQUIRED_ROWS) return;
    var input = row.querySelector("input");
    var remove = row.querySelector(".option-field__remove");

    remove.hidden = false;
    row.hidden = !input.value.trim();
    remove.addEventListener("click", function () {
      input.value = "";
      row.hidden = true;
      refresh();
      addButton.focus();
    });
  });

  addButton.hidden = false;
  addButton.addEventListener("click", function () {
    var next = rows.find(function (row) { return row.hidden; });
    if (!next) return;
    next.hidden = false;
    next.querySelector("input").focus();
    refresh();
  });

  refresh();
})();
