  // ── Отдельное чтение смысла ──
  var mr = { s: 1, here: null, saveTimer: null, sentKey: '' };
  function mrLocalPos() {
    try {
      var p = JSON.parse(localStorage.getItem(MPOS_KEY) || 'null');
      if (p && p.s >= 1 && p.s <= 114 && p.a >= 1) return p;
    } catch (e) {}
    return null;
  }
  function mrTopAyah() {
    var box = document.getElementById('mr-scroll');
    var top = box.getBoundingClientRect().top;
    var rows = document.querySelectorAll('#mr-text .mr-a');
    for (var i = 0; i < rows.length; i++) {
      if (rows[i].getBoundingClientRect().bottom > top + 24) {
        return { s: mr.s, a: parseInt(rows[i].getAttribute('data-a'), 10) };
      }
    }
    return { s: mr.s, a: 1 };
  }
  function mrSave() {
    var p = mrTopAyah(), now = Date.now();
    p.t = now;
    try { localStorage.setItem(MPOS_KEY, JSON.stringify(p)); } catch (e) {}
    var key = p.s + ':' + p.a;
    if (key === mr.sentKey) return;
    mr.sentKey = key;
    apiCall('/meaning_pos', { method: 'POST', quiet: true, body: { surah: p.s, ayah: p.a } })
      .catch(function () { mr.sentKey = ''; });
  }
  function mrRender(at, here) {
    mr.s = at.s;
    var box = document.getElementById('mr-text'), scroll = document.getElementById('mr-scroll');
    var row = surahRow(at.s), src = meaningSrc();
    box.innerHTML = '<div class="mr-msg">' + T('mr_loading') + '</div>';
    var prev = document.getElementById('mr-prev'), next = document.getElementById('mr-next');
    prev.disabled = at.s <= 1; next.disabled = at.s >= 114;
    // <bdi> - арабское имя изолировано от номера: без этого WebKit
    // переставлял «20. طه» в «طه .20» (снимок 02.11.2026).
    prev.innerHTML = at.s > 1 ? '‹ ' + (at.s - 1) + '. <bdi class="ar" dir="rtl">' + surahRow(at.s - 1)[1] + '</bdi>' : '';
    next.innerHTML = at.s < 114 ? (at.s + 1) + '. <bdi class="ar" dir="rtl">' + surahRow(at.s + 1)[1] + '</bdi> ›' : '';
    meaningSurah(src, at.s).then(function (t) {
      if (mr.s !== at.s || meaningSrc() !== src) return;
      var html = '<div class="mr-sura"><div class="ar">سُورَةُ ' + row[1] + '</div>' +
        '<div class="num">' + T('mr_surah', { N: at.s }) + '</div></div>';
      t.forEach(function (txt, i) {
        if (here && here === i + 1) html += '<div class="mr-here" id="mr-here">' + T('mr_here') + '</div>';
        html += '<div class="mr-a" data-a="' + (i + 1) + '"><span class="n">' + (i + 1) + '</span><span></span></div>';
      });
      if (at.s < 114) {
        html += '<button type="button" class="mr-next" id="mr-next-surah">' + T('mr_next') + ': ' +
          (at.s + 1) + '. <bdi dir="rtl">' + surahRow(at.s + 1)[1] + '</bdi></button>';
      }
      box.innerHTML = html;
      // Текст перевода - через textContent: это данные, не разметка.
      var spans = box.querySelectorAll('.mr-a span:last-child');
      t.forEach(function (txt, i) { spans[i].textContent = txt; });
      var target = at.a > 1 ? box.querySelector('[data-a="' + (here ? here : at.a) + '"]') : null;
      var mark = document.getElementById('mr-here');
      scroll.scrollTop = target ? (mark || target).offsetTop - 8 : 0;
      if (mark) setTimeout(function () { mark.classList.add('gone'); }, 2500);
      var ns = document.getElementById('mr-next-surah');
      if (ns) ns.addEventListener('click', function () { mrRender({ s: at.s + 1, a: 1 }); mrSave(); });
    }, function () {
      if (mr.s !== at.s) return;
      box.innerHTML = '<div class="mr-msg"></div>';
      var msg = box.firstChild;
      msg.textContent = T('mr_offline');
      msg.addEventListener('click', function () { mrRender(at, here); });
    });
  }
  function mrOpen() {
    sheetClose();
    document.getElementById('mreader').hidden = false;
    mrMarkSeg();
    var local = mrLocalPos();
    var start = local || { s: 1, a: 1 };
    mrRender(start, local && (local.s > 1 || local.a > 1) ? local.a : null);
    trail('mread', { k: start.s + ':' + start.a });
    // Сервер - место с другого устройства (Telegram/иконка). Новее - прыгаем.
    apiCall('/meaning_pos', { quiet: true }).then(function (res) {
      var d = res && res.status === 200 ? res.data : null;
      if (!d || !d.surah || document.getElementById('mreader').hidden) return;
      var st = Date.parse(d.updated_at || '') || 0;
      if (local && local.t && local.t >= st) return;
      if (local && local.s === d.surah && local.a === d.ayah) return;
      mr.sentKey = d.surah + ':' + d.ayah;
      mrRender({ s: d.surah, a: d.ayah }, d.surah > 1 || d.ayah > 1 ? d.ayah : null);
    }).catch(function () {});
  }
  function mrClose() {
    if (document.getElementById('mreader').hidden) return;
    if (document.querySelector('#mr-text .mr-a')) mrSave();
    document.getElementById('mreader').hidden = true;
  }
  document.getElementById('mr-scroll').addEventListener('scroll', function () {
    clearTimeout(mr.saveTimer);
    mr.saveTimer = setTimeout(mrSave, 1500);
  }, { passive: true });
  document.getElementById('mr-back').addEventListener('click', mrClose);
  document.getElementById('mr-prev').addEventListener('click', function () {
    if (mr.s > 1) { mrRender({ s: mr.s - 1, a: 1 }); mrSave(); }
  });
  document.getElementById('mr-next').addEventListener('click', function () {
    if (mr.s < 114) { mrRender({ s: mr.s + 1, a: 1 }); mrSave(); }
  });
  document.addEventListener('visibilitychange', function () {
    if (document.hidden && !document.getElementById('mreader').hidden) mrSave();
  });
  document.getElementById('btn-meaning').addEventListener('click', mrOpen);

