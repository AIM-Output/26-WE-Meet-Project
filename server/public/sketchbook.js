/* 스케치북 — 넓은 화면에서는 넘기는 책, 좁은 화면에서는 옆으로 미는 낱장.
   쪽 순서는 index.html 의 .leaf(종이 한 장 = 앞쪽·뒤쪽) 순서 그대로다. 장 수는 여기서 세지 않고 HTML 에서 읽는다.
   이 파일이 없어도 페이지는 낱장 모드로 읽힌다. */
(() => {
  const root = document.documentElement;
  root.classList.add('js');

  const TURN = 560;
  const TURN_FAST = 420;
  const STAGGER = 80;

  const start = () => {
    const book = document.querySelector('[data-book]');
    if (!book) return;

    const leaves = [...book.querySelectorAll('.leaf')];
    const pages = [...book.querySelectorAll('.page:not(.page--blank)')];
    const edges = [...book.querySelectorAll('[data-edge]')];
    const pager = document.querySelector('[data-pager]');
    const prevButton = document.querySelector('[data-prev]');
    const nextButton = document.querySelector('[data-next]');
    const rail = document.querySelector('[data-rail]');
    const live = document.querySelector('[data-live]');

    const wide = matchMedia('(min-width: 960px)');
    const calm = matchMedia('(prefers-reduced-motion: reduce)');
    const lastSpread = leaves.length - 1;
    const spreadOf = (pageIndex) => Math.floor(pageIndex / 2) + 1;
    const clamp = (value, min, max) => Math.max(min, Math.min(max, value));

    let mode = '';
    let spread = 1; // 책: 지금 펼친 면 (1 = 표지 안쪽 + 첫 그림)
    let pageIndex = 0; // 낱장: 지금 가운데 있는 쪽
    let observer = null;
    let inkTimer = 0;

    // 펜으로 그려지는 순서 — 선마다 번호를 매기고 길이를 1로 맞춘다(CSS 의 ink-draw 가 쓴다)
    for (const group of book.querySelectorAll('.ink')) {
      group.querySelectorAll('path').forEach((path, order) => {
        path.setAttribute('pathLength', '1');
        path.style.setProperty('--k', String(order));
      });
    }
    const ink = (page) => page.classList.add('is-inked');

    rail.replaceChildren(
      ...pages.map((page) => {
        const tick = document.createElement('span');
        if (page.classList.contains('plate--draft')) tick.className = 'is-draft';
        return tick;
      }),
    );
    const ticks = [...rail.children];

    const shown = () => (mode === 'book' ? [2 * spread - 2, 2 * spread - 1] : [pageIndex]);

    const render = () => {
      const on = shown();
      const atStart = on[0] === 0;
      const atEnd = on[on.length - 1] === pages.length - 1;
      ticks.forEach((tick, i) => tick.classList.toggle('is-on', on.includes(i)));
      prevButton.disabled = atStart;
      nextButton.disabled = atEnd;
      for (const edge of edges) {
        edge.hidden = mode !== 'book' || (edge.dataset.edge === 'prev' ? atStart : atEnd);
      }
      const numbers = on.map((i) => i + 1).join(', ');
      const titles = on.map((i) => pages[i].dataset.title).join(', ');
      live.textContent = `${pages.length}쪽 가운데 ${numbers}쪽. ${titles}`;
    };

    // ---------- 책 ----------
    const applyBook = (from) => {
      const changed = leaves.filter((leaf, i) => leaf.classList.contains('is-flipped') !== i < spread);
      const animated = book.classList.contains('is-ready') && !calm.matches;
      const forward = spread >= from;
      const duration = changed.length > 1 ? TURN_FAST : TURN;
      book.style.setProperty('--turn', `${duration}ms`);

      leaves.forEach((leaf, i) => {
        const order = changed.indexOf(leaf);
        // 앞으로 넘길 때는 위에 있는 종이부터, 되넘길 때는 마지막에 넘긴 종이부터
        const step = order < 0 ? 0 : forward ? order : changed.length - 1 - order;
        leaf.style.setProperty('--d', `${step * STAGGER}ms`);
        if (order >= 0 && animated) leaf.classList.add('is-turning');
        leaf.classList.toggle('is-flipped', i < spread);
      });

      // 지금 펼친 두 쪽만 조작·읽기 대상이다
      pages.forEach((page, i) => {
        page.inert = spreadOf(i) !== spread;
      });

      const wait = animated && changed.length ? (changed.length - 1) * STAGGER + duration * 0.5 : 0;
      clearTimeout(inkTimer);
      inkTimer = setTimeout(() => shown().forEach((i) => ink(pages[i])), wait);
      render();
    };

    const goSpread = (target, { remember = true } = {}) => {
      const next = clamp(target, 1, lastSpread);
      if (next === spread) return;
      const from = spread;
      spread = next;
      pageIndex = 2 * spread - 2;
      applyBook(from);
      if (remember) history.replaceState(null, '', `#${pages[pageIndex].id}`);
    };

    // ---------- 낱장 ----------
    const goPage = (target, smooth = true) => {
      const page = pages[clamp(target, 0, pages.length - 1)];
      book.scrollTo({
        left: page.offsetLeft - (book.clientWidth - page.offsetWidth) / 2,
        behavior: smooth && !calm.matches ? 'smooth' : 'instant',
      });
    };

    const watchStrip = () => {
      observer = new IntersectionObserver(
        (entries) => {
          for (const entry of entries) {
            if (!entry.isIntersecting) continue;
            ink(entry.target);
            if (entry.intersectionRatio >= 0.6) {
              pageIndex = pages.indexOf(entry.target);
              render();
            }
          }
        },
        { root: book, threshold: [0.2, 0.6] },
      );
      pages.forEach((page) => observer.observe(page));
    };

    const step = (direction) => {
      if (mode === 'book') goSpread(spread + direction);
      else goPage(pageIndex + direction);
    };

    // ---------- 책 ↔ 낱장 ----------
    const setMode = () => {
      const next = wide.matches ? 'book' : 'strip';
      if (next === mode) return;
      mode = next;

      if (mode === 'book') {
        observer?.disconnect();
        observer = null;
        spread = spreadOf(pageIndex);
        book.classList.remove('is-ready');
        book.classList.add('is-book');
        book.scrollLeft = 0;
        book.style.setProperty('--n', String(leaves.length));
        leaves.forEach((leaf, i) => {
          leaf.style.setProperty('--i', String(i));
          leaf.classList.remove('is-turning');
        });
        applyBook(spread);
        // 처음 펼친 상태는 넘김 없이 놓고, 그다음부터 넘긴다
        requestAnimationFrame(() => requestAnimationFrame(() => book.classList.add('is-ready')));
      } else {
        clearTimeout(inkTimer);
        book.classList.remove('is-book', 'is-ready');
        leaves.forEach((leaf) => leaf.classList.remove('is-flipped', 'is-turning'));
        pages.forEach((page) => {
          page.inert = false;
        });
        pageIndex = 2 * spread - 2;
        watchStrip();
        if (pageIndex > 0) goPage(pageIndex, false);
        render();
      }
    };

    // ---------- 조작 ----------
    prevButton.addEventListener('click', () => step(-1));
    nextButton.addEventListener('click', () => step(1));
    for (const edge of edges) {
      edge.addEventListener('click', () => step(edge.dataset.edge === 'prev' ? -1 : 1));
    }

    book.addEventListener('transitionend', (event) => {
      if (event.propertyName === 'transform' && event.target.classList.contains('leaf')) {
        event.target.classList.remove('is-turning');
      }
    });

    // ← → 로 넘긴다. 글자를 치는 중이 아닐 때, 초점이 책 근처이거나 아무 데도 없을 때만
    const stage = book.closest('.stage');
    document.addEventListener('keydown', (event) => {
      if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
      const target = event.target;
      const free = target === document.body || stage.contains(target);
      if (!free || target.closest?.('input, textarea, select, [contenteditable]')) return;
      if (event.key === 'ArrowRight') step(1);
      else if (event.key === 'ArrowLeft') step(-1);
      else return;
      event.preventDefault();
    });

    // 터치로 책을 쓸어 넘기기 (낱장 모드는 브라우저의 가로 스크롤이 한다)
    let touch = null;
    book.addEventListener('pointerdown', (event) => {
      touch = mode === 'book' && event.pointerType !== 'mouse' ? { id: event.pointerId, x: event.clientX, y: event.clientY } : null;
    });
    book.addEventListener('pointerup', (event) => {
      if (!touch || touch.id !== event.pointerId) return;
      const dx = event.clientX - touch.x;
      const dy = event.clientY - touch.y;
      touch = null;
      if (Math.abs(dx) > 48 && Math.abs(dx) > Math.abs(dy) * 1.5) step(dx < 0 ? 1 : -1);
    });
    book.addEventListener('pointercancel', () => {
      touch = null;
    });

    // 차례의 링크(#calendar …) · 주소의 # · 뒤로 가기 → 그 장을 편다.
    // 낱장 모드에서는 브라우저가 알아서 그 쪽으로 민다.
    const pageOfHash = (hash) => pages.findIndex((page) => `#${page.id}` === decodeURIComponent(hash));
    const openHash = (hash) => {
      const index = pageOfHash(hash);
      if (index >= 0 && mode === 'book') goSpread(spreadOf(index), { remember: false });
    };
    addEventListener('hashchange', () => openHash(location.hash));
    document.addEventListener('click', (event) => {
      const link = event.target.closest?.('a[href^="#"]');
      if (link) openHash(link.getAttribute('href'));
    });

    wide.addEventListener('change', setMode);

    const first = pageOfHash(location.hash);
    if (first > 0) pageIndex = first;
    pager.hidden = false;
    setMode();
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true });
  else start();
})();
