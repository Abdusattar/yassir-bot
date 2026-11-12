  // Общая модалка "да/отмена" (30.08.2026, сейчас только для 🔁
  // "повторение") - showConfirm(текст, колбэк) показывает вопрос, колбэк
  // вызывается только по "Да", по "Отмена"/фону - ничего не происходит.
  var confirmOverlay = document.getElementById('confirm-overlay');
  var confirmOnYes = null;
  function showConfirm(text, onYes) {
    document.getElementById('confirm-text').textContent = text;
    confirmOnYes = onYes;
    confirmOverlay.classList.add('visible');
  }
  function hideConfirm() {
    confirmOverlay.classList.remove('visible');
    confirmOnYes = null;
  }
  document.getElementById('confirm-cancel').addEventListener('click', hideConfirm);
  confirmOverlay.addEventListener('click', function (e) {
    if (e.target === confirmOverlay) hideConfirm();
  });
  document.getElementById('confirm-yes').addEventListener('click', function () {
    var cb = confirmOnYes;
    hideConfirm();
    if (cb) cb();
  });

