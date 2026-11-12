  function pulseColor(kind) {
    // Один тон на всё приложение (правило дизайна проекта): заучивание и
    // повторение — акцент разной плотности, слова — золото маркера мусхафа,
    // разбор устаза — чернила. Не светофор из пяти цветов.
    var cs = getComputedStyle(document.documentElement);
    var acc = cs.getPropertyValue('--accent').trim();
    if (kind === 'r') return 'color-mix(in srgb, ' + acc + ' 62%, transparent)';
    if (kind === 't') return cs.getPropertyValue('--marker-color').trim();
    if (kind === 'review') return cs.getPropertyValue('--ink').trim();
    return acc;
  }
  function pulseWord(kind) {
    return T(kind === 'r' ? 'pulse_rep' : kind === 't' ? 'pulse_word'
           : kind === 'review' ? 'pulse_ustaz' : 'pulse_hifz');
  }
  function pulsePlural(n, one, few, many) {
    var a = Math.abs(n) % 100, b = a % 10;
    return a > 10 && a < 20 ? many : b > 1 && b < 5 ? few : b === 1 ? one : many;
  }
  // Слово после числа (16.10.2026): по-русски три формы, в кыргызском и
  // узбекском после числа слово не меняется - у них одна форма (_one).
  function TP(n, key) {
    return T(key + '_' + (UI_LANG === 'ru' ? pulsePlural(n, 'one', 'few', 'many') : 'one'));
  }
  function pulseFit(cv) {
    var dpr = window.devicePixelRatio || 1, w = cv.clientWidth || 320;
    var h = cv.getAttribute('height') / cv.getAttribute('width') * w;
    if (cv.width !== Math.round(w * dpr)) {
      cv.width = Math.round(w * dpr);
      cv.height = Math.round(h * dpr);
      cv.style.height = h + 'px';
    }
    var ctx = cv.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    return { ctx: ctx, w: w, h: h };
  }

  // Точки внутри сердца: неявная кривая (x²+y²−1)³ − x²y³ ≤ 0, шаг сетки
  // подбираем так, чтобы точек хватило на весь джамаат.
  function pulseHeartShape(n) {
    var pts = [];
    for (var step = 0.075; step > 0.011 && pts.length < n; step -= 0.002) {
      pts = [];
      for (var y = 1.3; y >= -1.4; y -= step)
        for (var x = -1.4; x <= 1.4; x += step * 0.92) {
          var a = x * x + y * y - 1;
          if (a * a * a - x * x * y * y * y <= 0) pts.push([x, y]);
        }
    }
    var out = [], k = pts.length / n;
    for (var i = 0; i < n; i++) out.push(pts[Math.floor(i * k)] || [0, 0]);
    return out;
  }

  function pulseApply(data) {
    var prev = pulse.data;
    pulse.data = data;
    var days = data.days || [];
    pulse.today = days.length - 1;
    if (pulse.view >= days.length || !prev) { pulse.view = pulse.today; pulse.from = pulse.today; }
    pulse.best = 0;
    days.forEach(function (d, i) {
      if (i < days.length - 1 && pulseSum(d) > pulseSum(days[pulse.best])) pulse.best = i;
    });

    var t = data.today || {};
    var totalNow = PULSE_KINDS.reduce(function (a, k) { return a + (t[k] || 0); }, 0);
    if (prev) {
      // Разницу с прошлым ответом ставим в очередь — по событию за раз.
      PULSE_KINDS.forEach(function (k) {
        var was = (prev.today || {})[k] || 0, now = t[k] || 0;
        for (var i = 0; i < Math.min(now - was, 40); i++) pulse.queue.push(k);
      });
      // Перемешиваем, иначе сначала пойдут все «заучил», потом все «слова».
      pulse.queue.sort(function () { return Math.random() - 0.5; });
    } else {
      pulse.shown = totalNow;
    }
    pulse.count = totalNow;
    pulse.tally = {};
    PULSE_KINDS.forEach(function (k) { pulse.tally[k] = t[k] || 0; });

    var people = Math.max(40, Math.min(600, data.people_total || 0));
    if (!pulse.shape || pulse.dots.length !== people) {
      pulse.shape = pulseHeartShape(people);
      pulse.dots = [];
      pulse.ghost = [];
      for (var i = 0; i < people; i++) {
        pulse.dots.push({ v: 0, s: 0, warm: 0, k: 'm' });
        pulse.ghost.push(0);
      }
    }
    pulseWarm(t.people || 0, pulse.dots);
    var yday = days[days.length - 2];
    pulseGhost(yday ? yday.people : 0);
    pulseLabels();
    // 'grid', а не 'flex' (10.09.2026): блок с этого дня раскладывается
    // сеткой - сердце слева, число и разбивка справа. Инлайновый стиль
    // сильнее таблицы стилей, поэтому раскладка задаётся здесь же.
    document.getElementById('dash-pulse').style.display = 'grid';
    if (!prev) pulseIntroStart();       // первое открытие приложения
    pulseStart();
  }

  function pulseSum(day) {
    return (day.total || []).reduce(function (a, b) { return a + b; }, 0);
  }
  function pulseWarm(target, dots) {          // столько людей уже занималось
    var warm = 0, guard = 0;
    dots.forEach(function (d) { if (d.warm) warm++; });
    while (warm > target) {                    // новый день — гасим лишние
      var i = Math.floor(Math.random() * dots.length);
      if (!dots[i].warm) { if (guard++ > 6000) break; continue; }
      dots[i].warm = 0; warm--;
    }
    guard = 0;
    while (warm < Math.min(target, dots.length) && guard++ < 6000) {
      var j = Math.floor(Math.random() * dots.length);
      if (dots[j].warm) continue;
      dots[j].warm = 1;
      dots[j].k = PULSE_KINDS[Math.floor(Math.random() * 3)];
      warm++;
    }
  }
  function pulseGhost(target) {
    var have = 0, guard = 0;
    pulse.ghost.forEach(function (g) { if (g) have++; });
    if (have >= target) return;
    while (have < Math.min(target, pulse.ghost.length) && guard++ < 6000) {
      var i = Math.floor(Math.random() * pulse.ghost.length);
      if (pulse.ghost[i]) continue;
      pulse.ghost[i] = 1; have++;
    }
  }

  function pulseLabels() {
    var d = pulse.data;
    if (!d) return;
    var days = d.days || [], row = days[pulse.view] || { total: [], people: 0 };
    var sum = pulseSum(row);
    var peak = row.total ? row.total.indexOf(Math.max.apply(null, row.total)) : 0;
    var name = pulse.view === pulse.today ? T('pulse_today')
             : pulse.view === pulse.today - 1 ? T('pulse_yesterday')
             : (row.date || '').slice(8) + '.' + (row.date || '').slice(5, 7);
    document.getElementById('pulse-day').textContent = name;
    // Для СЕГОДНЯ эта строка молчит (10.09.2026, поймал пользователь):
    // сегодняшнее число уже стоит крупно в сердце над волной, и «0 действий
    // · 0 человек» повторяло его слово в слово. На других днях повтора нет -
    // там подпись единственный источник, и она остаётся.
    document.getElementById('pulse-sum').innerHTML =
      pulse.view === pulse.today ? '' : T('pulse_day_sum', {
        A: '<b>' + sum + '</b> ' + TP(sum, 'n_act'),
        P: (row.people || 0) + ' ' + TP(row.people || 0, 'n_people')
      });
    document.getElementById('pulse-peak').textContent =
      pulse.view === pulse.best ? T('pulse_best')
      : pulse.view === pulse.today ? T('pulse_running')
      : T('pulse_peak', { H: (peak < 10 ? '0' : '') + peak });
    document.getElementById('pulse-prev').disabled = pulse.view === 0;
    document.getElementById('pulse-next').disabled = pulse.view === pulse.today;
    var dots = document.getElementById('pulse-dots');
    while (dots.children.length > days.length) dots.removeChild(dots.lastChild);
    while (dots.children.length < days.length) dots.appendChild(document.createElement('i'));
    Array.prototype.forEach.call(dots.children, function (el, k) {
      el.className = k === pulse.view ? 'on' : '';
    });
  }

  /* Разгон при открытии (07.09.2026, решение пользователя). Экран не
     появляется готовым: счётчик отсчитывает от нуля до сегодняшнего числа,
     сердце зажигается точка за точкой, волна прочерчивается слева до текущего
     часа, а по дороге всплывают названия действий - «заучил», «повторил»,
     «слова». За пару секунд человек видит не просто число, а из чего оно
     сложилось.

     Темп считаем от величины числа, а не берём фиксированным: маленькое число
     не растягиваем, большое не гоним. Корень сглаживает разницу: 20 → 2.5 с,
     180 → 3.8 с, 600 → 4.8 с (замедлено 07.09.2026 по просьбе пользователя -
     первая версия шла вдвое быстрее и читалась как мельтешение). Подписи в
     любом случае идут ровно три штуки и держатся дольше, чем длится их
     появление, - читать успеваешь. */
  function pulseIntroMs(n) {
    return Math.max(2200, Math.min(4800, 1900 + Math.sqrt(Math.max(0, n)) * 140));
  }
  function pulseIntroStart() {
    var now = (window.performance && performance.now) ? performance.now() : Date.now();
    if (!pulse.data || (pulse.introAt && now - pulse.introAt < PULSE_INTRO_GAP)) return;
    pulse.intro = now;
    pulse.introAt = now;
    pulse.introDur = pulseIntroMs(pulse.count);
    pulse.introWord = 0;
    pulse.queue = [];               // очередь реальных событий подождёт
    pulse.floats = [];
    pulse.ripples = [];
    pulse.dots.forEach(function (d) { d.warm = 0; d.v = 0; });
    pulse.shown = 0;
    pulseStart();
  }
  /* Плавно с обоих концов (smoothstep). Кубический ease-out, стоявший здесь
     сначала, набирал две трети числа за первую треть времени - глаз видел
     рывок и потом медленное доползание. Здесь рост распределён ровнее: экран
     наполняется, а не выстреливает. */
  function pulseEase(x) { return x * x * (3 - 2 * x); }

  function pulseGo(i) {
    var days = (pulse.data || {}).days || [];
    if (i < 0 || i >= days.length || i === pulse.view) return;
    pulse.from = pulse.view; pulse.view = i; pulse.slide = 0;
    pulseLabels();
  }

  function pulseHead() {
    var d = pulse.data;
    if (!d) return;
    var q = d.quiet_min;
    var sub = document.getElementById('pulse-sub');
    if (q != null && q >= 45 && !pulse.queue.length) {
      // В проекте тишина — так и говорим, вместо бодрого счёта ни о чём.
      var txt = q < 90 ? q + ' ' + TP(q, 'n_min')
              : Math.round(q / 60) + ' ' + TP(Math.round(q / 60), 'n_hour');
      sub.textContent = T('pulse_quiet', { T: txt });
    } else {
      var hh = d.hour == null ? '' : (d.hour < 10 ? '0' : '') + d.hour;
      sub.textContent = T('pulse_sub', {
        A: TP(pulse.shown, 'pulse_sub_act'),
        H: hh
      });
    }
    document.getElementById('pulse-count').textContent = pulse.shown;
    var split = document.getElementById('pulse-split'), html = '';
    ['m', 'r', 't', 'review'].forEach(function (k) {
      var n = (pulse.tally || {})[k] || 0;
      if (!n) return;
      html += '<i><u style="background:' + pulseColor(k) + '"></u>' + pulseWord(k) + ' ' + n + '</i>';
    });
    split.innerHTML = html;
  }

  // Ритм часа: чем плотнее этот час на неделе, тем чаще бьётся сердце.
  function pulseBpm(h) {
    var pr = (pulse.data || {}).profile;
    if (!pr) return 60;
    var by = [], i, k;
    for (i = 0; i < 24; i++) {
      var s = 0;
      for (k = 0; k < PULSE_KINDS.length; k++) s += (pr[PULSE_KINDS[k]] || [])[i] || 0;
      by.push(s);
    }
    var mx = Math.max.apply(null, by) || 1;
    return 44 + (by[h] / mx) * 46;
  }
  function pulseBeat(now, h) {
    var ph = (now / 1000) * (pulseBpm(h) / 60); ph -= Math.floor(ph);
    function b(c, w, a) { var d = ph - c; return a * Math.exp(-(d * d) / w); }
    return b(0, 0.0016, 1) + b(0.16, 0.0022, 0.45) + b(1, 0.0016, 1);
  }

  var PULSE_FAJR = 5, PULSE_GHOST_GONE = 10;
  function pulseDrawHeart(now) {
    var cv = document.getElementById('pulse-heart');
    var f = pulseFit(cv), ctx = f.ctx, w = f.w, h = f.h;
    var hour = (pulse.data || {}).hour || 0;
    var sc = Math.min(w / 3.5, h / 3.0)
           * (1 + pulseBeat(now, hour) * 0.05)
           * (1 + Math.sin(now / 2600) * 0.018);   // тихое дыхание между ударами
    var cx = w / 2, cy = h / 2 + h * 0.06;
    function at(i) {
      return [cx + pulse.shape[i][0] * sc, cy - pulse.shape[i][1] * sc];
    }

    if (pulse.intro) {
      var introP = Math.min(1, (now - pulse.intro) / pulse.introDur);
      var e = pulseEase(introP);
      var want = Math.round(((pulse.data.today || {}).people || 0) * e);
      var warm = 0;
      pulse.dots.forEach(function (d) { if (d.warm) warm++; });
      var guard = 0;
      while (warm < want && guard++ < 3000) {
        var wi = Math.floor(Math.random() * pulse.dots.length);
        if (pulse.dots[wi].warm) continue;
        pulse.dots[wi].warm = 1;
        pulse.dots[wi].k = PULSE_KINDS[Math.floor(Math.random() * 3)];
        pulse.dots[wi].v = 0.85;        // свежая точка вспыхивает и оседает
        warm++;
      }
      pulse.shown = Math.round(pulse.count * e);
      var base = pulse.data.today || {};
      PULSE_KINDS.forEach(function (k) {
        pulse.tally[k] = Math.round((base[k] || 0) * e);
      });
      // Три подписи за разгон, на 22 / 50 / 78 процентах пути: реже, чем
      // моргает глаз, и каждая успевает дожить до конца.
      var STOPS = [0.22, 0.50, 0.78], KINDS3 = ['m', 'r', 't'];
      if (pulse.introWord < STOPS.length && introP >= STOPS[pulse.introWord]) {
        var kd = KINDS3[pulse.introWord];
        pulse.introWord++;
        var li = Math.floor(Math.random() * pulse.dots.length);
        pulse.dots[li].warm = 1; pulse.dots[li].k = kd; pulse.dots[li].v = 1;
        pulse.floats.push({ i: li, dy: 8, k: kd, n: pulseWord(kd), life: 1 });
        pulse.ripples.push({ i: li, r: 0, k: kd });
        if (pulse.floats.length > 2) pulse.floats.shift();
      }
      pulseHead();
      if (introP >= 1) {
        pulse.intro = 0;
        // Финальный щелчок: число доехало до сегодняшнего и подмигнуло.
        var cntEl = document.getElementById('pulse-count');
        cntEl.classList.add('hit');
        setTimeout(function () { cntEl.classList.remove('hit'); }, 300);
      }
    }

    // Очередь реальных событий: по одному раз в несколько кадров.
    if (!pulse.intro && pulse.queue.length
        && now - pulse.last > (PULSE_REFRESH_MS / (pulse.queue.length + 4))) {
      pulse.last = now;
      var kind = pulse.queue.shift();
      var idx = Math.floor(Math.random() * pulse.dots.length);
      var d0 = pulse.dots[idx];
      d0.v = 1; d0.k = kind;
      if (kind !== 'review') d0.warm = 1;
      var p = at(idx);
      pulse.ripples.push({ i: idx, r: 0, k: kind });
      var last = pulse.floats[pulse.floats.length - 1];
      if (!last || last.life < 0.55) pulse.floats.push({ i: idx, dy: 8, k: kind, life: 1 });
      if (pulse.floats.length > 2) pulse.floats.shift();
      if (pulse.shown < pulse.count) pulse.shown++;
      var cnt = document.getElementById('pulse-count');
      cnt.classList.add('hit');
      setTimeout(function () { cnt.classList.remove('hit'); }, 220);
      pulseHead();
    }

    /* Мерцание (07.09.2026, пожелание пользователя: «пусть в сердце
       временами даже если никто не сдаёт, идёт мерцание этих точек»).
       Ночью и в дневное затишье очередь событий пуста, и сердце застывало
       ровным полем точек - живого в нём не оставалось ничего, кроме
       медленного дыхания масштаба.

       Искра НЕ считается действием: не зажигает точку насовсем (warm),
       не даёт круга, слова и не двигает счётчик - она только чуть светлее
       на секунду. Иначе тишину было бы не отличить от работы джамаата.
       Пауза между искрами случайная: ровный такт читался бы как индикатор
       загрузки, а не как дыхание. */
    if (!PULSE_REDUCED && !pulse.intro && !pulse.queue.length
        && now - pulse.shimmer > pulse.shimmerGap) {
      pulse.shimmer = now;
      pulse.shimmerGap = 420 + Math.random() * 1100;
      var si = Math.floor(Math.random() * pulse.dots.length);
      pulse.dots[si].s = 0.55 + Math.random() * 0.45;
    }

    pulse.dots.forEach(function (d) {
      d.v *= pulse.intro ? 0.96 : 0.985;
      if (d.s) d.s *= 0.972;
    });
    pulse.ripples.forEach(function (rp) { rp.r += 0.7; });
    pulse.ripples = pulse.ripples.filter(function (rp) { return rp.r < 22; });
    pulse.floats.forEach(function (fl) {
      fl.life -= pulse.intro ? 0.007 : 0.013;   // в разгоне слово живёт дольше
      fl.dy += 0.3;
    });
    pulse.floats = pulse.floats.filter(function (fl) { return fl.life > 0; });

    pulse.ripples.forEach(function (rp) {
      var p = at(rp.i);
      ctx.beginPath(); ctx.arc(p[0], p[1], rp.r, 0, Math.PI * 2);
      ctx.strokeStyle = pulseColor(rp.k);
      ctx.globalAlpha = Math.max(0, 1 - rp.r / 22) * 0.4;
      ctx.lineWidth = 1.3; ctx.stroke(); ctx.globalAlpha = 1;
    });

    var lit = 0, i;
    for (i = 0; i < pulse.dots.length; i++) if (pulse.dots[i].warm) lit++;
    // Тень вчерашнего дня догорает до фаджра: ночью на экране всё равно
    // должно быть на что смотреть, а после утренней молитвы она уступает
    // место новому дню. Заполнение сегодняшнего гасит её и само по себе.
    var afterFajr = hour >= PULSE_GHOST_GONE ? 1
      : hour >= PULSE_FAJR ? (hour - PULSE_FAJR) / (PULSE_GHOST_GONE - PULSE_FAJR) : 0;
    var yday = ((pulse.data || {}).days || [])[((pulse.data || {}).days || []).length - 2];
    var byDay = Math.max(0, 1 - lit / Math.max(1, (yday ? yday.people : 40) * 0.45));
    var gAlpha = Math.min(byDay, 1 - afterFajr) * 0.3;
    if (gAlpha > 0.01) {
      ctx.fillStyle = pulseColor('m');
      for (i = 0; i < pulse.ghost.length; i++) {
        if (!pulse.ghost[i] || pulse.dots[i].warm) continue;
        var pg = at(i);
        ctx.beginPath(); ctx.arc(pg[0], pg[1], 2.3, 0, Math.PI * 2);
        ctx.globalAlpha = gAlpha; ctx.fill(); ctx.globalAlpha = 1;
      }
    }

    var dim = getComputedStyle(document.documentElement).getPropertyValue('--card-border').trim();
    for (i = 0; i < pulse.dots.length; i++) {
      var d = pulse.dots[i], p2 = at(i);
      ctx.beginPath(); ctx.arc(p2[0], p2[1], 2.3 + d.v * 1.9, 0, Math.PI * 2);
      ctx.fillStyle = (d.warm || d.v > 0.05) ? pulseColor(d.k) : dim;
      ctx.globalAlpha = d.warm ? 0.62 + d.v * 0.38 : (d.v > 0.05 ? 0.5 + d.v * 0.5 : 1);
      ctx.fill(); ctx.globalAlpha = 1;
    }

    // Искры рисуем поверх поля: у зажжённой точки это добавочный блик её
    // же цветом, у спящей - едва заметный тёплый отсвет.
    for (i = 0; i < pulse.dots.length; i++) {
      var d3 = pulse.dots[i];
      if (!d3.s || d3.s < 0.03) continue;
      var p4 = at(i);
      ctx.beginPath(); ctx.arc(p4[0], p4[1], 2.3 + d3.s * 1.3, 0, Math.PI * 2);
      ctx.fillStyle = pulseColor(d3.warm ? d3.k : 'm');
      ctx.globalAlpha = d3.s * (d3.warm ? 0.5 : 0.34);
      ctx.fill(); ctx.globalAlpha = 1;
    }

    ctx.font = '600 10.5px -apple-system, BlinkMacSystemFont, sans-serif';
    ctx.textAlign = 'center';
    pulse.floats.forEach(function (fl) {
      var p3 = at(fl.i);
      ctx.globalAlpha = Math.min(1, fl.life * 1.6);
      ctx.fillStyle = pulseColor(fl.k);
      ctx.fillText(pulseWord(fl.k), Math.min(w - 28, Math.max(28, p3[0])), p3[1] - fl.dy);
      ctx.globalAlpha = 1;
    });
    ctx.textAlign = 'left';
  }

  // Волна суток: плавная линия (Catmull-Rom), под ней бледный вчерашний день,
  // пунктиром — рекорд джамаата. Листается стрелками и свайпом.
  function pulseWavePath(ctx, pts) {
    ctx.moveTo(pts[0][0], pts[0][1]);
    for (var i = 0; i < pts.length - 1; i++) {
      var p0 = pts[i - 1] || pts[i], p1 = pts[i], p2 = pts[i + 1], p3 = pts[i + 2] || p2;
      ctx.bezierCurveTo(p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6,
                        p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6,
                        p2[0], p2[1]);
    }
  }
  function pulseDrawWave(now) {
    var d = pulse.data;
    if (!d || !d.days || !d.days.length) return;
    var cv = document.getElementById('pulse-wave');
    var f = pulseFit(cv), ctx = f.ctx, w = f.w, h = f.h, base = h - 12;
    var days = d.days, hour = d.hour || 0;
    var mx = 1;
    days.forEach(function (r) { mx = Math.max(mx, Math.max.apply(null, r.total)); });
    function pointsOf(row, upto) {
      var pad = 3, top = 6, pts = [], last = upto === undefined ? 23 : upto;
      for (var i = 0; i <= last; i++)
        pts.push([pad + (w - pad * 2) * (i / 23), base - (row.total[i] / mx) * (base - top)]);
      return pts;
    }
    function stroke(pts, color, alpha, width) {
      ctx.beginPath(); pulseWavePath(ctx, pts);
      ctx.strokeStyle = color; ctx.globalAlpha = alpha; ctx.lineWidth = width;
      ctx.lineJoin = 'round'; ctx.lineCap = 'round'; ctx.stroke(); ctx.globalAlpha = 1;
    }
    if (pulse.slide < 1) pulse.slide = Math.min(1, pulse.slide + 0.09);

    var cs = getComputedStyle(document.documentElement);
    var muted = cs.getPropertyValue('--muted').trim();
    var accent = cs.getPropertyValue('--accent').trim();
    var gold = cs.getPropertyValue('--marker-color').trim();
    var row = days[pulse.view], prevRow = days[pulse.view - 1];
    var upto = pulse.view === pulse.today ? Math.min(23, hour) : 23;
    if (pulse.intro && pulse.view === pulse.today) {
      // Линия дня прочерчивается слева направо ровно до текущего часа.
      upto = Math.max(1, Math.round(upto * pulseEase(
        Math.min(1, (now - pulse.intro) / pulse.introDur))));
    }

    if (prevRow && pulse.view - 1 !== pulse.best)
      stroke(pointsOf(prevRow), muted, 0.35, 1);
    if (pulse.view !== pulse.best) {
      var bp = pointsOf(days[pulse.best]);
      ctx.setLineDash([3, 3]); stroke(bp, gold, 0.7, 1); ctx.setLineDash([]);
      var ph = days[pulse.best].total.indexOf(Math.max.apply(null, days[pulse.best].total));
      ctx.fillStyle = gold; ctx.globalAlpha = 0.9;
      ctx.font = '9px -apple-system, BlinkMacSystemFont, sans-serif';
      ctx.textAlign = 'center';
      var bd = (days[pulse.best].date || '');
      ctx.fillText(T('pulse_record', {
        D: bd.slice(8) + '.' + bd.slice(5, 7),
        N: pulseSum(days[pulse.best])
      }),
                   Math.min(w - 52, Math.max(52, bp[ph][0])),
                   // Math.max(9, ...) - когда пик рекорда у самого верха,
                   // подпись уезжала за край холста и обрезалась
                   // (10.09.2026; было и раньше, поймано на снимке).
                   Math.max(9, bp[ph][1] - 5));
      ctx.textAlign = 'left'; ctx.globalAlpha = 1;
    }

    var pts = pointsOf(row, upto);
    if (pulse.slide < 1 && days[pulse.from]) {
      var old = pointsOf(days[pulse.from], upto);
      pts = pts.map(function (p, i) {
        var o = old[Math.min(i, old.length - 1)];
        return [p[0], o[1] + (p[1] - o[1]) * pulse.slide];
      });
    }
    var g = ctx.createLinearGradient(0, 0, 0, base);
    g.addColorStop(0, accent); g.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.beginPath(); pulseWavePath(ctx, pts);
    ctx.lineTo(pts[pts.length - 1][0], base); ctx.lineTo(pts[0][0], base); ctx.closePath();
    ctx.fillStyle = g; ctx.globalAlpha = 0.16; ctx.fill(); ctx.globalAlpha = 1;
    stroke(pts, accent, 1, 1.7);
    if (pulse.view === pulse.today) {
      var lastPt = pts[pts.length - 1];
      ctx.beginPath();
      ctx.arc(lastPt[0], lastPt[1], 2.4 + pulseBeat(now, hour) * 1.2, 0, Math.PI * 2);
      ctx.fillStyle = accent; ctx.fill();
    }
    ctx.fillStyle = muted; ctx.font = '9px -apple-system, BlinkMacSystemFont, sans-serif';
    ctx.fillText('00', 2, h - 1);
    ctx.fillText('12', w / 2 - 6, h - 1);
    ctx.fillText('23', w - 13, h - 1);
  }

  // Кадры крутим только когда дашборд реально виден: в мусхафе или тренажёре
  // рисовать невидимый canvas — зря жечь батарею телефона.
  var PULSE_REDUCED = window.matchMedia
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  function pulseVisible() {
    var dash = document.getElementById('dashboard');
    return !document.hidden && dash && dash.style.display !== 'none' && pulse.data;
  }
  function pulseFrame(now) {
    pulse.raf = 0;
    if (!pulseVisible()) return;
    pulseDrawHeart(now);
    pulseDrawWave(now);
    if (!PULSE_REDUCED) pulseStart();
  }
  function pulseStart() {
    if (pulse.raf || !pulseVisible()) return;
    pulse.raf = requestAnimationFrame(pulseFrame);
  }

  function pulseLoad() {
    if (document.hidden) return;
    apiCall('/pulse').then(function (res) {
      if (res.status !== 200 || !res.data || !res.data.days) return;
      pulseApply(res.data);
      pulseHead();
    }).catch(function (err) { console.error('pulse', err); });
  }

  (function pulseInit() {
    document.getElementById('pulse-prev').onclick = function () { pulseGo(pulse.view - 1); };
    document.getElementById('pulse-next').onclick = function () { pulseGo(pulse.view + 1); };
    var wave = document.getElementById('pulse-wave'), x0 = null;
    wave.addEventListener('touchstart', function (e) { x0 = e.touches[0].clientX; }, { passive: true });
    wave.addEventListener('touchend', function (e) {
      if (x0 === null) return;
      var dx = e.changedTouches[0].clientX - x0; x0 = null;
      if (Math.abs(dx) > 30) pulseGo(pulse.view + (dx < 0 ? 1 : -1));
    }, { passive: true });
    document.addEventListener('visibilitychange', function () {
      if (!document.hidden) { pulseStart(); pulseLoad(); pulseIntroStart(); }
    });
    setTimeout(pulseLoad, 0);
    setInterval(pulseLoad, PULSE_REFRESH_MS);
  })();

