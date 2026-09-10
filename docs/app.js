/* TeleWiki landing interactions.
   Motion language: one hero explanation (tabbed chat replay),
   occasional scroll reveals, near-invisible hover feedback.
   Everything honours prefers-reduced-motion. */

(function () {
  'use strict';

  var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

  /* ── Dates ── */
  var yearEl = document.getElementById('year');
  if (yearEl) yearEl.textContent = String(new Date().getFullYear());
  var stamp = document.getElementById('today-stamp');
  if (stamp) {
    stamp.textContent = new Date().toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  }
  var sheetDate = document.getElementById('sheet-date');
  if (sheetDate) {
    var now = new Date();
    var hh = String(now.getUTCHours()).padStart(2, '0');
    sheetDate.textContent = now.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) + ' · ' + hh + ':00 UTC';
  }

  /* ── Toast ── */
  var toast = document.getElementById('toast');
  var toastTimer = null;
  function showToast(msg) {
    if (!toast) return;
    toast.textContent = msg;
    toast.hidden = false;
    requestAnimationFrame(function () { toast.classList.add('show'); });
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      toast.classList.remove('show');
      setTimeout(function () { toast.hidden = true; }, 280);
    }, 1800);
  }

  /* ── Copy buttons ── */
  function flashCopied(btn) {
    btn.classList.add('show');
    setTimeout(function () { btn.classList.remove('show'); }, 1400);
  }
  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (e) {
      var ta = document.createElement('textarea');
      ta.value = text;
      ta.setAttribute('readonly', '');
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      var ok = false;
      try { ok = document.execCommand('copy'); } catch (err) { ok = false; }
      ta.remove();
      return ok;
    }
  }
  document.querySelectorAll('[data-copy]').forEach(function (btn) {
    btn.addEventListener('click', async function () {
      var text = btn.getAttribute('data-copy') || '';
      var ok = await copyText(text);
      flashCopied(btn);
      showToast(ok ? 'Copied ' + text : 'Copy: ' + text);
    });
  });

  /* ── Mobile menu ── */
  var toggle = document.querySelector('.nav-toggle');
  var menu = document.getElementById('mobile-menu');
  if (toggle && menu) {
    toggle.addEventListener('click', function () {
      var opening = menu.hasAttribute('hidden');
      if (opening) menu.removeAttribute('hidden');
      else menu.setAttribute('hidden', '');
      toggle.setAttribute('aria-expanded', String(opening));
      toggle.setAttribute('aria-label', opening ? 'Close menu' : 'Open menu');
      var icon = toggle.querySelector('i');
      if (icon) icon.className = opening ? 'bi bi-x' : 'bi bi-list';
    });
    menu.querySelectorAll('a').forEach(function (a) {
      a.addEventListener('click', function () {
        menu.setAttribute('hidden', '');
        toggle.setAttribute('aria-expanded', 'false');
        toggle.setAttribute('aria-label', 'Open menu');
        var icon = toggle.querySelector('i');
        if (icon) icon.className = 'bi bi-list';
      });
    });
  }

  /* ── Nav shadow + scrollspy ── */
  var nav = document.querySelector('.nav');
  var spyLinks = Array.prototype.slice.call(document.querySelectorAll('.nav-links a'));
  var spySections = spyLinks
    .map(function (a) { return document.querySelector(a.getAttribute('href')); })
    .filter(Boolean);
  function onScroll() {
    if (nav) nav.classList.toggle('scrolled', window.scrollY > 8);
    if (!spySections.length || !('IntersectionObserver' in window)) return;
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();
  if ('IntersectionObserver' in window && spySections.length) {
    var spy = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (!en.isIntersecting) return;
        var id = '#' + en.target.id;
        spyLinks.forEach(function (a) {
          a.classList.toggle('active', a.getAttribute('href') === id);
        });
      });
    }, { rootMargin: '-40% 0px -55% 0px' });
    spySections.forEach(function (s) { spy.observe(s); });
  }

  /* ── Scroll reveals ── */
  var revealEls = document.querySelectorAll('.reveal');
  document.querySelectorAll('.pain-list, .timeline, .mode-grid, .bento').forEach(function (grid) {
    Array.prototype.forEach.call(grid.querySelectorAll('.reveal'), function (el, i) {
      el.style.transitionDelay = Math.min(i * 80, 240) + 'ms';
    });
  });
  if ('IntersectionObserver' in window && !reduceMotion) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) { en.target.classList.add('in'); io.unobserve(en.target); }
      });
    }, { threshold: 0.12, rootMargin: '0px 0px -6% 0px' });
    revealEls.forEach(function (el) { io.observe(el); });
  } else {
    revealEls.forEach(function (el) { el.classList.add('in'); });
  }

  /* ── Hero tabbed chat replay ── */
  var chat = document.getElementById('demo-panel');
  var caption = document.getElementById('demo-caption');
  var hint = document.getElementById('phone-hint');
  var tabs = Array.prototype.slice.call(document.querySelectorAll('[data-demo]'));

  var SCRIPTS = {
    wiki: {
      caption: 'Live replay — a real /wiki lookup, answers and all.',
      hint: 'Message',
      lines: [
        ['user', '/wiki black holes', 600],
        ['bot', '<b>Black hole</b><br>A region of spacetime where gravity is so strong that nothing escapes.<br><span class="src">Wikipedia · photo included →</span><span class="kbd">🎲 Quiz me on this</span>', 1700],
        ['user', 'Mercury? no — /wiki mercury', 500],
        ['bot', '🤔 <b>Mercury</b> could mean several things — pick one:<br><span class="opt">📖 Mercury (planet)</span><span class="opt">📖 Mercury (element)</span><span class="opt">📖 Mercury (mythology)</span>', 2600]
      ]
    },
    quiz: {
      caption: 'Live replay — tap answers in the tour below, or watch here.',
      hint: 'C',
      lines: [
        ['user', '/quiz space', 600],
        ['bot', '<b>In which year did humans first land on the Moon?</b><span class="opt">A · 1959</span><span class="opt">B · 1965</span><span class="opt">C · 1969</span><span class="opt">D · 1975</span>', 1700],
        ['user', 'C', 500],
        ['bot', '✅ <b>Correct!</b> +12 pts · streak 🔥×3<br><span class="opt">Next question coming… (/stop to end)</span>', 2600]
      ]
    },
    digest: {
      caption: 'Live replay — tomorrow’s briefing, matched to your topics.',
      hint: 'Message',
      lines: [
        ['user', '/digest add physics space 08:00', 600],
        ['bot', '✅ Subscribed: <b>physics, space</b><br>Digest arrives daily at <b>08:00</b> UTC.', 1500],
        ['bot', '📰 <b>Your daily digest</b><br>🌟 Featured: Black hole<br>📅 On this day: Apollo 11 (1969) · Einstein (1915)<br><span class="opt">Topics: physics, space</span>', 2800]
      ]
    }
  };

  var currentDemo = 'wiki';
  var runToken = 0;

  function addBubble(kind, html) {
    var div = document.createElement('div');
    div.className = 'msg ' + kind;
    div.innerHTML = html;
    chat.appendChild(div);
    while (chat.children.length > 7) chat.removeChild(chat.firstChild);
    chat.scrollTop = chat.scrollHeight;
  }
  function addTyping() {
    var div = document.createElement('div');
    div.className = 'msg bot typing';
    div.innerHTML = '<span></span><span></span><span></span>';
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
    return div;
  }
  function renderStatic(key) {
    chat.innerHTML = '';
    SCRIPTS[key].lines.forEach(function (l) { addBubble(l[0], l[1]); });
    if (caption) caption.textContent = SCRIPTS[key].caption;
  }
  async function playDemo(key, token) {
    chat.innerHTML = '';
    var script = SCRIPTS[key].lines;
    if (caption) caption.textContent = SCRIPTS[key].caption;
    if (hint) hint.textContent = SCRIPTS[key].hint;
    // eslint-disable-next-line no-constant-condition
    while (true) {
      if (token !== runToken) return;
      for (var i = 0; i < script.length; i++) {
        if (token !== runToken) return;
        var kind = script[i][0], html = script[i][1], hold = script[i][2];
        var dots = addTyping();
        await sleep(kind === 'user' ? 650 : 1050);
        if (token !== runToken) return;
        dots.remove();
        addBubble(kind, html);
        await sleep(hold);
        if (token !== runToken) return;
      }
      await sleep(1400);
      if (token !== runToken) return;
      chat.innerHTML = '';
    }
  }
  function selectDemo(key, focus) {
    currentDemo = key;
    runToken += 1;
    var token = runToken;
    tabs.forEach(function (t) {
      var on = t.getAttribute('data-demo') === key;
      t.setAttribute('aria-selected', String(on));
      t.tabIndex = on ? 0 : -1;
      if (on && focus) t.focus();
    });
    if (!chat) return;
    if (reduceMotion) renderStatic(key);
    else playDemo(key, token);
  }
  if (chat && tabs.length) {
    tabs.forEach(function (t, i) {
      t.addEventListener('click', function () { selectDemo(t.getAttribute('data-demo'), false); });
      t.addEventListener('keydown', function (e) {
        var next = null;
        if (e.key === 'ArrowRight') next = tabs[(i + 1) % tabs.length];
        if (e.key === 'ArrowLeft') next = tabs[(i - 1 + tabs.length) % tabs.length];
        if (e.key === 'Home') next = tabs[0];
        if (e.key === 'End') next = tabs[tabs.length - 1];
        if (next) { e.preventDefault(); selectDemo(next.getAttribute('data-demo'), true); }
      });
    });
    var started = false;
    function start() {
      if (started) return;
      started = true;
      selectDemo(currentDemo, false);
    }
    if (reduceMotion || !('IntersectionObserver' in window)) start();
    else {
      var heroIO = new IntersectionObserver(function (entries) {
        if (entries[0].isIntersecting) { start(); heroIO.disconnect(); }
      });
      heroIO.observe(chat);
    }
  }

  /* ── Lookup demo: disambiguation switcher ── */
  var ARTICLES = {
    hole: {
      tag: 'Black hole · M87*',
      title: 'Black hole',
      text: 'A region of spacetime where gravity is so strong that nothing — not even light — escapes. Stellar-mass holes form when massive stars collapse.',
      note: 'Photo from Wikipedia when available. Tap a match to swap the summary — like the bot’s buttons.'
    },
    film: {
      tag: 'Film · 1979 · Disney',
      title: 'The Black Hole (film)',
      text: 'A 1979 Disney sci-fi film: the crew of the Palomino encounters the USS Cygnus, lost near a black hole and commanded by the obsessive Dr. Reinhardt.',
      note: 'Disambiguation handled — the bot asks instead of guessing wrong.'
    },
    interstellar: {
      tag: 'Film · 2014 · Nolan',
      title: 'Interstellar',
      text: 'A 2014 film following explorers through a wormhole near Saturn. Its black hole Gargantua was rendered with real relativistic equations.',
      note: 'Close match, right article. One tap on “Quiz me” turns this into a round.'
    }
  };
  var wikiPhoto = document.querySelector('#wiki-demo .article-photo');
  var wikiTitle = document.getElementById('wiki-demo-title');
  var wikiText = document.getElementById('wiki-demo-text');
  var wikiNote = document.getElementById('wiki-demo-note');
  var wikiQuizBtn = document.getElementById('wiki-quiz-btn');
  document.querySelectorAll('#wiki-picks .pick').forEach(function (btn) {
    btn.addEventListener('click', function () {
      document.querySelectorAll('#wiki-picks .pick').forEach(function (b) { b.classList.remove('is-active'); });
      btn.classList.add('is-active');
      var a = ARTICLES[btn.getAttribute('data-article')] || ARTICLES.hole;
      if (wikiPhoto) {
        wikiPhoto.setAttribute('data-variant', btn.getAttribute('data-article') === 'hole' ? '' : btn.getAttribute('data-article'));
        wikiPhoto.querySelector('span').textContent = a.tag;
      }
      if (wikiTitle) wikiTitle.textContent = a.title;
      if (wikiText) wikiText.textContent = a.text;
      if (wikiNote) wikiNote.textContent = a.note;
    });
  });
  if (wikiQuizBtn) {
    wikiQuizBtn.addEventListener('click', function () {
      var title = wikiTitle ? wikiTitle.textContent : 'this topic';
      showToast('In Telegram this opens a quiz on “' + title + '”');
      document.getElementById('quiz-demo').scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'center' });
    });
  }

  /* ── Digest demo: topic filter ── */
  var chips = document.querySelectorAll('#digest-chips .chip');
  var events = document.querySelectorAll('#digest-events li');
  chips.forEach(function (chip) {
    chip.addEventListener('click', function () {
      chips.forEach(function (c) { c.classList.remove('is-on'); c.setAttribute('aria-pressed', 'false'); });
      chip.classList.add('is-on');
      chip.setAttribute('aria-pressed', 'true');
      var topic = chip.getAttribute('data-topic');
      events.forEach(function (li) {
        var show = topic === 'all' || (li.getAttribute('data-topics') || '').split(' ').indexOf(topic) !== -1;
        li.classList.toggle('hide', !show);
      });
    });
  });

  /* ── Quiz demo: playable ── */
  var quizOpts = document.querySelectorAll('#quiz-demo .quiz-opts button');
  var quizResult = document.getElementById('quiz-result');
  var quizReset = document.getElementById('quiz-reset');
  var quizDone = false;
  quizOpts.forEach(function (btn) {
    btn.addEventListener('click', function () {
      if (quizDone) return;
      quizDone = true;
      var right = btn.getAttribute('data-correct') === 'true';
      quizOpts.forEach(function (b) {
        b.disabled = true;
        if (b.getAttribute('data-correct') === 'true') b.classList.add('right');
      });
      if (!right) btn.classList.add('wrong');
      if (quizResult) {
        quizResult.textContent = right
          ? '✅ Correct! +12 pts · streak 🔥×3 — just like the bot scores it.'
          : '❌ Not quite — the answer is C · 1969. In groups, anyone can still jump in.';
        quizResult.className = 'quiz-result ' + (right ? 'good' : 'bad');
      }
      if (quizReset) quizReset.hidden = false;
    });
  });
  if (quizReset) {
    quizReset.addEventListener('click', function () {
      quizDone = false;
      quizOpts.forEach(function (b) { b.disabled = false; b.classList.remove('right', 'wrong'); });
      if (quizResult) {
        quizResult.textContent = 'Pick an answer — the bot scores it instantly.';
        quizResult.className = 'quiz-result';
      }
      quizReset.hidden = true;
    });
  }

  /* ── Command filter ── */
  var filter = document.getElementById('cmd-filter');
  var cmdItems = document.querySelectorAll('#cmd-list li');
  var cmdEmpty = document.getElementById('cmd-empty');
  if (filter) {
    filter.addEventListener('input', function () {
      var q = filter.value.trim().toLowerCase();
      var visible = 0;
      cmdItems.forEach(function (li) {
        var hit = !q || (li.getAttribute('data-keys') + ' ' + li.textContent.toLowerCase()).indexOf(q) !== -1;
        li.classList.toggle('hide', !hit);
        if (hit) visible += 1;
      });
      if (cmdEmpty) cmdEmpty.hidden = visible !== 0;
    });
  }
})();
