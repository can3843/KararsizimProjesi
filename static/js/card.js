// "Kararsızlık kartı": sonucu canvas ile PNG olarak indirir. Renkler CSS değişkenlerinden okunur.
(function () {
  var button = document.querySelector("[data-card]");
  var article = document.querySelector(".poll-detail");
  if (!button || !article || !document.createElement("canvas").getContext) return;

  var WIDTH = 1200;
  var HEIGHT = 630;
  var PAD = 64;

  function token(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function resultsVisible() {
    var percent = article.querySelector(".option-row__percent");
    return !!percent && !percent.hidden;
  }

  // Vote.js sonuçları açtıktan sonra da çağrılır.
  window.syncCardButton = function () {
    button.hidden = !resultsVisible();
  };
  window.syncCardButton();

  function readPoll() {
    var rows = Array.prototype.slice.call(article.querySelectorAll(".option-row")).map(function (row) {
      var match = /opt-(\d)/.exec(row.className);
      return {
        index: match ? Number(match[1]) : 0,
        text: row.querySelector(".option-row__text").textContent.trim(),
        percent: parseInt(row.querySelector(".option-row__percent").textContent.replace("%", ""), 10) || 0,
      };
    });
    return {
      question: article.querySelector(".poll-detail__question").textContent.trim(),
      total: article.querySelector("[data-total]").textContent.trim(),
      badge: article.querySelector("[data-badge]").textContent.trim(),
      rows: rows,
    };
  }

  function wrapLines(ctx, text, maxWidth, maxLines) {
    var words = text.split(/\s+/);
    var lines = [];
    var line = "";
    words.forEach(function (word) {
      var candidate = line ? line + " " + word : word;
      if (ctx.measureText(candidate).width <= maxWidth || !line) {
        line = candidate;
      } else {
        lines.push(line);
        line = word;
      }
    });
    if (line) lines.push(line);
    if (lines.length > maxLines) {
      lines = lines.slice(0, maxLines);
      lines[maxLines - 1] = lines[maxLines - 1].replace(/\s*\S{0,3}$/, "") + "…";
    }
    return lines;
  }

  function draw(poll) {
    var canvas = document.createElement("canvas");
    canvas.width = WIDTH;
    canvas.height = HEIGHT;
    var ctx = canvas.getContext("2d");
    var ink = token("--ink");
    var muted = token("--muted");
    var surface = token("--surface");

    ctx.fillStyle = surface;
    ctx.fillRect(0, 0, WIDTH, HEIGHT);

    // Karar çubuğu
    var x = 0;
    poll.rows.forEach(function (row) {
      var width = (WIDTH * row.percent) / 100;
      ctx.fillStyle = token("--opt-" + row.index);
      ctx.fillRect(x, 0, width, 28);
      x += width;
    });

    // Soru
    ctx.fillStyle = ink;
    ctx.textBaseline = "top";
    ctx.font = '800 56px "Bricolage Grotesque", "Inter", sans-serif';
    var lines = wrapLines(ctx, poll.question, WIDTH - PAD * 2, 3);
    var y = 76;
    lines.forEach(function (line) {
      ctx.fillText(line, PAD, y);
      y += 66;
    });

    // Seçenekler
    y += 14;
    var rowHeight = Math.min(56, Math.floor((HEIGHT - 120 - y) / poll.rows.length));
    ctx.font = '500 30px "Inter", sans-serif';
    poll.rows.forEach(function (row) {
      ctx.fillStyle = token("--opt-" + row.index);
      ctx.fillRect(PAD, y + 8, 20, 20);
      ctx.fillStyle = ink;
      var label = row.text.length > 40 ? row.text.slice(0, 39) + "…" : row.text;
      ctx.fillText(label, PAD + 36, y + 4);
      ctx.textAlign = "right";
      ctx.font = '600 30px "JetBrains Mono", monospace';
      ctx.fillText("%" + row.percent, WIDTH - PAD, y + 4);
      ctx.textAlign = "left";
      ctx.font = '500 30px "Inter", sans-serif';
      y += rowHeight;
    });

    // Alt bilgi
    ctx.fillStyle = ink;
    ctx.font = '600 28px "Inter", sans-serif';
    ctx.fillText(poll.badge + " · " + poll.total + " oy", PAD, HEIGHT - 80);
    ctx.fillStyle = muted;
    ctx.font = '500 24px "Inter", sans-serif';
    ctx.fillText("Kararsızım · " + location.host, PAD, HEIGHT - 44);
    return canvas;
  }

  function download(canvas) {
    canvas.toBlob(function (blob) {
      if (!blob) {
        window.showToast("Kart oluşturulamadı.", "error");
        return;
      }
      var link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = "kararsizlik-karti-" + button.dataset.id + ".png";
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(function () { URL.revokeObjectURL(link.href); }, 1000);
      window.showToast("Kart indirildi.", "success");
    }, "image/png");
  }

  button.addEventListener("click", function () {
    var fonts = document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve();
    fonts.then(function () { download(draw(readPoll())); });
  });
})();
