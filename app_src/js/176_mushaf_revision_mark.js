  // Отметка "повторение" (30.08.2026) - решение пользователя: подтверждение
  // ПЕРЕД зачётом (студент мог случайно задеть кнопку), засчитывает
  // дневное задание "r" и шлёт сообщение в группу (core/mufradat_bot.py:
  // credit_revision_task) только после явного "Да".
  document.getElementById('btn-revision').addEventListener('click', function (e) {
    var btn = e.currentTarget;
    // Несовершеннолетним (16.09.2026) - не вопрос, а панель записи: читает
    // повторение под запись, запись уходит устазу, зачёт ставит сервер.
    if (meRevisionRecord) { revisionRecOpen(); return; }
    showConfirm(T(meHafiz ? 'revision_ask_hafiz' : 'revision_ask'), function () {
      apiCall('/revision', { method: 'POST' }).then(function (res) {
        if (res.status === 401) return;
        if (res.data && res.data.error === 'record_required') { meRevisionRecord = true; revisionRecOpen(); return; }
        showPopupMessage(btn, res.data && res.data.credited ?
          T('revision_done') : T('revision_already'));
        mushafDoneMarks('r');   // засчитано (сейчас или раньше) - кнопка зелёная
      });
    });
  });

