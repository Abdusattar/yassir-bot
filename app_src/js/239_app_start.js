  window.addEventListener('resize', function () {
    var turned = mushafOrientationApply();
    var share = mushafScrollShare;
    var resized = mushafViewSize !== window.innerWidth + 'x' + window.innerHeight;
    mushafViewSize = window.innerWidth + 'x' + window.innerHeight;
    var keys = Object.keys(cache);
    if (keys.length) mushafFitSchedule();
    if (typeof hifzRecPad === 'function') hifzRecPad();
    // После поворота (и любой смены размера лёжа) кегль и высота листа
    // другие - возвращаем читающего на ту же долю листа, а не в начало.
    // Повторно - после поздних перемеров.
    if (turned || (resized && mushafWasLand)) {
      var restores = [0].concat(MUSHAF_REFIT_DELAYS.map(function (ms) { return ms + 50; }));
      mushafRestoreUntil = Date.now() + restores[restores.length - 1] + 100;
      restores.forEach(function (ms) {
        setTimeout(function () {
          var span = pageWrap.scrollHeight - pageWrap.clientHeight;
          if (span > 0) pageWrap.scrollTop = share * span;
        }, ms);
      });
    }
  });
  mushafOrientationApply();
  if (window.MutationObserver) {
    var landWatch = new MutationObserver(function () {
      // Режим сменился не поворотом (вкладка, заучивание) - потолок кегля
      // другой, лист надо перемерить.
      // Закрытый мусхаф не меряем: скрытый лист дал бы ложный кегль, при
      // открытии режим сменится ещё раз и перемер будет уже на виду.
      if (mushafOrientationApply() && Object.keys(cache).length &&
          document.getElementById('app').style.display !== 'none') mushafFitSchedule();
    });
    // style - закрытие/открытие мусхафа (display), см. mushafOrientationApply.
    landWatch.observe(document.getElementById('app'), { attributes: true, attributeFilter: ['class', 'style'] });
    landWatch.observe(document.getElementById('view-page'), { attributes: true, attributeFilter: ['class'] });
  }

  var startPage = FIRST_PAGE;
  try {
    var saved = parseInt(localStorage.getItem('yassir_mushaf_page'), 10);
    if (saved >= FIRST_PAGE && saved <= LAST_PAGE) startPage = saved;
  } catch (e) {}
  loadPage(startPage);
  // «rec aac» - телефон умеет писать сдачу сразу в AAC/mp4, который играют
  // все телефоны без перекодировки (12.10.2026, разведка: стоит ли уходить
  // с opus на Android). chNNN - версия Chrome, от неё это и зависит.
  var recCaps = '';
  try {
    var mrT = window.MediaRecorder && MediaRecorder.isTypeSupported;
    recCaps = ' rec ' + (!mrT ? '-' : MediaRecorder.isTypeSupported('audio/mp4;codecs=mp4a.40.2') ? 'aac'
      : MediaRecorder.isTypeSupported('audio/mp4') ? 'mp4' : 'opus');
    var chV = /Chrome\/(\d+)/.exec(navigator.userAgent);
    if (chV) recCaps += ' ch' + chV[1];
  } catch (e) {}
  trail('open', { p: startPage,
                  n: ((tg && tg.initData) ? 'tg' : 'web') + ' ' + window.innerWidth + 'x' + window.innerHeight + recCaps });

