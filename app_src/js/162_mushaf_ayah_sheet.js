  // ── Панель аята ──
  var sheetAt = null;   // {s, a}
  function sheetHighlight() {
    Array.prototype.forEach.call(document.querySelectorAll('#ayah-text .ma-hl, #hifz-big-words .ma-hl'),
      function (el) { el.classList.remove('ma-hl'); });
    if (!sheetAt) return;
    Array.prototype.forEach.call(
      document.querySelectorAll('#ayah-text [data-ma="' + sheetAt.s + ':' + sheetAt.a + '"], ' +
        '#hifz-big-words [data-ma="' + sheetAt.s + ':' + sheetAt.a + '"]'),
      function (el) { el.classList.add('ma-hl'); });
  }
  function sheetShow() {
    if (!sheetAt) return;
    var at = sheetAt, src = meaningSrc();
    var row = surahRow(at.s);
    document.getElementById('as-ref').innerHTML =
      '<bdi class="ar" dir="rtl">' + row[1] + '</bdi> ' + at.s + ':' + at.a;
    var text = document.getElementById('as-text');
    text.textContent = T('mr_loading');
    meaningSurah(src, at.s).then(function (t) {
      if (sheetAt !== at || meaningSrc() !== src) return;
      var n = t.length;
      text.textContent = t[at.a - 1] || '';
      text.scrollTop = 0;
      var prev = document.getElementById('as-prev'), next = document.getElementById('as-next');
      prev.disabled = at.s === 1 && at.a === 1;
      next.disabled = at.s === 114 && at.a === n;
      prev.textContent = '‹ ' + (at.a > 1 ? T('ayah_n', { N: at.a - 1 }) : T('mr_surah', { N: at.s - 1 }));
      next.textContent = (at.a < n ? T('ayah_n', { N: at.a + 1 }) : T('mr_surah', { N: at.s + 1 })) + ' ›';
    }, function () {
      if (sheetAt === at) text.textContent = T('mr_offline');
    });
    sheetHighlight();
  }
  function sheetOpen(s, a) {
    sheetAt = { s: s, a: a };
    document.getElementById('ayah-sheet-dim').hidden = false;
    document.getElementById('ayah-sheet').hidden = false;
    sheetShow();
    trail('mhold', { k: s + ':' + a });
  }
  function sheetClose() {
    sheetAt = null;
    document.getElementById('ayah-sheet-dim').hidden = true;
    document.getElementById('ayah-sheet').hidden = true;
    sheetHighlight();
  }
  function sheetStep(d) {
    if (!sheetAt) return;
    var at = sheetAt;
    meaningSurah(meaningSrc(), at.s).then(function (t) {
      if (sheetAt !== at) return;
      if (d > 0) {
        if (at.a < t.length) sheetAt = { s: at.s, a: at.a + 1 };
        else if (at.s < 114) sheetAt = { s: at.s + 1, a: 1 };
        sheetShow();
      } else if (at.a > 1) {
        sheetAt = { s: at.s, a: at.a - 1 }; sheetShow();
      } else if (at.s > 1) {
        meaningSurah(meaningSrc(), at.s - 1).then(function (p) {
          if (sheetAt !== at) return;
          sheetAt = { s: at.s - 1, a: p.length }; sheetShow();
        });
      }
    });
  }
  document.getElementById('ayah-sheet-dim').addEventListener('click', sheetClose);
  document.getElementById('as-close').addEventListener('click', sheetClose);
  document.getElementById('as-prev').addEventListener('click', function () { sheetStep(-1); });
  document.getElementById('as-next').addEventListener('click', function () { sheetStep(1); });

