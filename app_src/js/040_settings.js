  // ── Настройки: открытие экрана и профиль (10.09.2026) ─────────────────
  // Кнопки «Сохранить» нет: поле уходит на сервер по событию change, то
  // есть когда с него ушли или нажали Enter, и отвечает тихой строкой под
  // карточкой. Так устроены настройки на телефоне; кнопку легко не заметить
  // и уйти, думая что сохранил.
  var settBox = document.getElementById('sett');
  var settName = document.getElementById('sett-name');
  var settYear = document.getElementById('sett-year');
  var settPlace = document.getElementById('sett-place');
  var settCountry = document.getElementById('sett-country');
  var nameHint = document.getElementById('sett-name-hint');
  var placeHint = document.getElementById('sett-place-hint');
  var savedProfile = { name: '', birth_year: null, location: '' };
  var profileLoaded = false;

  // Коды приходят от update_profile (core/db.py); текст человеку подбираем
  // здесь - сервер не знает, на каком языке он читает.
  var SAVE_ERRORS = {
    name_empty: 'sett_err_name_empty',
    name_too_long: 'sett_err_name_long',
    name_not_name: 'sett_err_name_not_name',
    birth_year_bad: 'sett_err_year_bad',
    birth_year_locked: 'sett_err_year_locked',
    location_too_long: 'sett_err_place_long'
  };

  function settSay(el, text, cls, restore) {
    el.textContent = text;
    el.className = 's-hint' + (cls ? ' ' + cls : '');
    if (restore) {
      clearTimeout(el._back);
      el._back = setTimeout(function () {
        el.textContent = restore;
        el.className = 's-hint';
      }, 2600);
    }
  }

  function settSave(patch, hint, restore) {
    apiCall('/profile', { method: 'POST', body: patch }).then(function (res) {
      if (res.status === 200 && res.data) {
        savedProfile = res.data;
        settSay(hint, T('sett_saved'), 'ok', restore);
        return;
      }
      var code = res.data && res.data.error;
      settSay(hint, T(SAVE_ERRORS[code] || 'sett_save_failed'), 'bad');
    }).catch(function () {
      settSay(hint, T('sett_save_failed'), 'bad');
    });
  }

  // Место хранится строкой. Если она не совпадает ни с одной областью -
  // значит человек живёт не в Кыргызстане, и строка это название страны.
  function settShowPlace(value) {
    var found = false;
    Array.prototype.forEach.call(settPlace.options, function (o) {
      if (o.value !== '__other' && (o.value || o.text) === value) found = true;
    });
    if (value && !found) {
      settPlace.value = '__other';
      settCountry.value = value;
      settCountry.hidden = false;
    } else {
      settPlace.value = value;
      settCountry.value = '';
      settCountry.hidden = true;
    }
  }

  function settLoadProfile() {
    apiCall('/profile').then(function (res) {
      var d = res && res.data;
      if (!d || !d.name && d.name !== '') return;
      profileLoaded = true;
      savedProfile = d;
      settName.value = d.name || '';
      settYear.value = d.birth_year || '';
      // Год, поставленный устазом (16.09.2026), с экрана не правится - иначе
      // запись повторения снимается одной цифрой.
      settYear.disabled = !!d.birth_year_locked;
      var yearNote = document.querySelector('label[for="sett-year"] i');
      if (yearNote) yearNote.textContent = d.birth_year_locked ? T('sett_year_locked') : T('sett_optional');
      settShowPlace(d.location || '');
    }).catch(function () {});
  }

