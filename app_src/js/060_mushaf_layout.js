  // ── Раскладка мусхафа (23.09.2026) ──────────────────────────────────
  // Переключатель в настройках: «Мединский» / «Дар аль-Маариф (египетский)».
  // Выбор уходит на сервер - по нему считается указатель 40+40, и сервер
  // сам переносит место на ту же строку новой раскладки. Пока висит
  // пересдача, сменить нельзя: долг записан номерами старой книги.
  function markLayout() {
    Array.prototype.forEach.call(
      document.querySelectorAll('#sett-layout button'),
      function (b) { b.classList.toggle('on', b.getAttribute('data-layout') === MUSHAF_LAYOUT); });
  }
  function applyLayout(lay) {
    if (lay !== 'dm') lay = 'madani';
    markLayout();
    if (lay === MUSHAF_LAYOUT) return false;
    MUSHAF_LAYOUT = lay;
    try { localStorage.setItem(LAYOUT_KEY, lay); } catch (e) {}
    markLayout();
    if (typeof loadPage === 'function' && currentPage) loadPage(currentPage);
    return true;
  }
  document.getElementById('sett-layout').addEventListener('click', function (e) {
    var b = e.target.closest('button');
    if (!b) return;
    var lay = b.getAttribute('data-layout');
    if (lay === MUSHAF_LAYOUT) return;
    var hint = document.getElementById('sett-layout-hint');
    var restore = T('layout_hint');
    apiCall('/layout', { method: 'POST', body: { layout: lay } }).then(function (res) {
      var d = res.data || {};
      if (res.status === 409 && d.error === 'retake_pending') {
        settSay(hint, T('layout_retake', { P: d.place || '' }), 'bad', restore);
        return;
      }
      if (res.status !== 200) { settSay(hint, T('layout_failed'), 'bad', restore); return; }
      applyLayout(d.layout);
      // Место 40+40 сервер перенёс на ту же строку новой книги.
      if (d.pointer) {
        hifz.line = d.pointer.line;
        hifz.stage = d.pointer.stage;
        hifzPointerPage = d.pointer.page;
      }
      trail('layout', { n: d.layout });
      settSay(hint, T(d.layout === 'dm' ? 'layout_on_dm' : 'layout_on_madani'), 'ok', restore);
    }).catch(function () { settSay(hint, T('layout_failed'), 'bad', restore); });
  });
  markLayout();
  setTimeout(function () {
    apiCall('/layout').then(function (res) {
      var d = res && res.data;
      if (d && d.layout) applyLayout(d.layout);
    }).catch(function () {});
  }, 0);

