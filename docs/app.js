/* TeleWiki landing interactions.
   Motion decisions (per animation review bar):
   - Hero chat loop: rare/first-view EXPLANATION of the product. JS-sequenced
     because message order/timing is programmatic; entrances stay
     transform+opacity via the CSS .msg keyframe.
   - Scroll reveals: occasional STATE INDICATION, IntersectionObserver +
     CSS transition, 70ms stagger inside grids.
   - Hovers/accordion: near-imperceptible feedback, CSS only.
   Reduced motion: static chat transcript, instant reveals. */

(function () {
  'use strict';

  var reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // Footer year
  var yearEl = document.getElementById('year');
  if (yearEl) yearEl.textContent = String(new Date().getFullYear());

  // Mobile menu
  var toggle = document.querySelector('.nav-toggle');
  var menu = document.getElementById('mobile-menu');
  if (toggle && menu) {
    toggle.addEventListener('click', function () {
      var opening = menu.hasAttribute('hidden');
      if (opening) menu.removeAttribute('hidden');
      else menu.setAttribute('hidden', '');
      toggle.setAttribute('aria-expanded', String(opening));
      var icon = toggle.querySelector('i');
      if (icon) icon.className = opening ? 'bi bi-x' : 'bi bi-list';
    });
    menu.querySelectorAll('a').forEach(function (a) {
      a.addEventListener('click', function () {
        menu.setAttribute('hidden', '');
        toggle.setAttribute('aria-expanded', 'false');
        var icon = toggle.querySelector('i');
        if (icon) icon.className = 'bi bi-list';
      });
    });
  }

  // Scroll reveal (staggered inside grids)
  var revealEls = document.querySelectorAll('.reveal');
  document.querySelectorAll('.cards, .steps, .cmd-grid').forEach(function (grid) {
    Array.prototype.forEach.call(grid.querySelectorAll('.reveal'), function (el, i) {
      el.style.transitionDelay = Math.min(i * 70, 210) + 'ms';
    });
  });
  if ('IntersectionObserver' in window && !reduceMotion) {
    var io = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add('in');
            io.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.15 }
    );
    revealEls.forEach(function (el) { io.observe(el); });
  } else {
    revealEls.forEach(function (el) { el.classList.add('in'); });
  }

  // Nav shadow on scroll
  var nav = document.querySelector('.nav');
  var onScroll = function () {
    nav.classList.toggle('scrolled', window.scrollY > 8);
  };
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  // Hero chat demo — a real /wiki -> /quiz session, looped
  var chat = document.getElementById('chat');
  if (!chat) return;

  var SCRIPT = [
    ['user', '/wiki black holes', 500],
    ['bot', '<b>Black hole</b><br>A region of spacetime where gravity is so strong that nothing escapes.<br>Read more on Wikipedia →', 1400],
    ['user', '/quiz space', 500],
    ['bot', '<b>In which year did humans first land on the Moon?</b><span class="opt">A · 1959</span><span class="opt">B · 1965</span><span class="opt">C · 1969</span><span class="opt">D · 1975</span>', 1400],
    ['user', 'C', 500],
    ['bot', '✅ <b>Correct!</b> +12 pts · streak ×2<br>New round: /quiz', 2600]
  ];

  function sleep(ms) {
    return new Promise(function (resolve) { setTimeout(resolve, ms); });
  }

  function addBubble(kind, html) {
    var div = document.createElement('div');
    div.className = 'msg ' + kind;
    div.innerHTML = html;
    chat.appendChild(div);
    while (chat.children.length > 7) chat.removeChild(chat.firstChild);
    chat.scrollTop = chat.scrollHeight;
    return div;
  }

  function addTyping() {
    var div = document.createElement('div');
    div.className = 'msg bot typing';
    div.innerHTML = '<span></span><span></span><span></span>';
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
    return div;
  }

  if (reduceMotion) {
    // Static transcript: no loop, no typing indicator
    SCRIPT.forEach(function (line) { addBubble(line[0], line[1]); });
    return;
  }

  async function play() {
    // eslint-disable-next-line no-constant-condition
    while (true) {
      for (var i = 0; i < SCRIPT.length; i++) {
        var kind = SCRIPT[i][0];
        var html = SCRIPT[i][1];
        var hold = SCRIPT[i][2];
        var dots = addTyping();
        await sleep(kind === 'user' ? 700 : 1100);
        dots.remove();
        addBubble(kind, html);
        await sleep(hold);
      }
      await sleep(1200);
      chat.innerHTML = '';
    }
  }

  // Start when the hero is visible so the first loop isn't missed
  if ('IntersectionObserver' in window) {
    var heroIO = new IntersectionObserver(function (entries) {
      if (entries[0].isIntersecting) {
        play();
        heroIO.disconnect();
      }
    });
    heroIO.observe(chat);
  } else {
    play();
  }
})();
