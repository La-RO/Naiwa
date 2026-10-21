(() => {
  'use strict';
  const images = Array.isArray(window.NAIWA_IMAGES) ? window.NAIWA_IMAGES : [];
  const videos = Array.isArray(window.NAIWA_VIDEOS) ? window.NAIWA_VIDEOS : [];
  const { t, localized } = window.NAIWA_I18N;
  const categories = [
    { id: 'expressions' }, { id: 'art' }, { id: 'variants' }, { id: 'scenes' }
  ];
  const categoryTitle = (id) => t(`cat.${id}.title`);
  const $ = (selector) => document.querySelector(selector);
  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };
  const external = (href, className, text) => {
    const link = el('a', className, text);
    if (/^https:\/\//i.test(href || '')) link.href = href;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    return link;
  };
  const sourceLink = (item) => {
    const link = external(item.sourceUrl, 'source-link');
    link.title = t('card.sourceTitle', { name: localized(item, 'sourceName') });
    link.append(el('span', 'source-label', t('card.source')), el('span', 'source-name', localized(item, 'sourceName')), el('span', '', '↗'));
    return link;
  };
  const pad = (num) => String(num).padStart(2, '0');
  const sourceSummary = (item) => localized(item, 'sourceNote') || t('viewer.defaultNote');

  if (document.body.dataset.page === 'sources') {
    function renderSources() {
    $('#source-count').textContent = t('sources.count', { images: images.length, videos: videos.length });
    const addEntries = (items, container, isVideo) => {
      container.replaceChildren();
      items.forEach((item) => {
        const entry = el('article', 'source-entry');
        const thumbnail = el('img');
        thumbnail.src = isVideo ? item.poster : item.src;
        thumbnail.alt = isVideo ? t('cinema.posterAlt', { title: localized(item, 'title') }) : localized(item, 'alt');
        thumbnail.loading = 'lazy';
        const details = el('div');
        details.append(el('h3', '', `${localized(item, 'title')} / ${isVideo ? t('sources.videoType') : categoryTitle(item.category)}`));
        details.append(el('p', '', t('sources.entryMeta', { source: localized(item, 'sourceName'), creator: localized(item, 'creator') || t('viewer.unverified') })));
        const links = el('div', 'source-entry-links');
        links.append(external(item.sourceUrl, '', t('sources.openPage')), external(isVideo ? item.originalVideoUrl : item.originalImageUrl, '', t('sources.openAsset')));
        details.append(links, el('p', '', sourceSummary(item)));
        entry.append(thumbnail, details);
        container.append(entry);
      });
    };
    addEntries(images, $('#image-sources'), false);
    addEntries(videos, $('#video-sources'), true);
    }
    renderSources();
    document.addEventListener('naiwa:languagechange', renderSources);
    return;
  }

  let selectedCategory = 'all';
  let query = '';
  let visibleImages = [...images];
  let viewerImages = [...images];
  let currentIndex = 0;
  let viewerMode = 'image';
  let viewerItem = null;
  const dialog = $('#media-viewer');
  const media = $('#viewer-media');
  $('#image-count').textContent = images.length;
  $('#category-count').textContent = categories.filter((c) => images.some((image) => image.category === c.id)).length;
  $('#video-count').textContent = videos.length;

  const hero = images.find((item) => item.id === 'expressions-l-18') || images[0];
  if (hero) {
    $('#hero-image').src = hero.src;
    $('#hero-image').alt = localized(hero, 'alt');
    $('#hero-source').href = hero.sourceUrl;
    $('#hero-source').title = t('hero.sourceTitle', { name: localized(hero, 'sourceName') });
  }

  function renderFilters() {
    const filterRoot = $('#category-filters');
    filterRoot.replaceChildren();
    [{ id: 'all' }, ...categories].forEach((category) => {
      const count = category.id === 'all' ? images.length : images.filter((item) => item.category === category.id).length;
      const button = el('button', `filter-button${selectedCategory === category.id ? ' active' : ''}`, category.id === 'all' ? t('cat.all') : categoryTitle(category.id));
      button.type = 'button';
      button.dataset.category = category.id;
      button.setAttribute('aria-pressed', String(selectedCategory === category.id));
      button.append(el('span', '', pad(count)));
      button.addEventListener('click', () => {
        selectedCategory = category.id;
        renderFilters();
        renderGallery();
        const active = [...filterRoot.children].find((node) => node.dataset.category === selectedCategory);
        if (active) active.focus({ preventScroll: true });
      });
      filterRoot.append(button);
    });
  }

  function renderGallery() {
    visibleImages = images.filter((item) => {
      const matchesCategory = selectedCategory === 'all' || item.category === selectedCategory;
      const content = `${item.title} ${item.titleEn || ''} ${item.alt} ${item.altEn || ''} ${item.categoryLabel} ${categoryTitle(item.category)} ${item.sourceName} ${item.sourceNameEn || ''}`.toLocaleLowerCase();
      return matchesCategory && (!query || content.includes(query));
    });
    const sections = $('#gallery-sections');
    sections.replaceChildren();
    categories.forEach((category, categoryIndex) => {
      const items = visibleImages.filter((item) => item.category === category.id);
      if (!items.length) return;
      const section = el('section', 'gallery-section');
      section.id = `gallery-${category.id}`;
      section.setAttribute('aria-labelledby', `title-${category.id}`);
      const header = el('div', 'gallery-section-heading');
      const headingLeft = el('div');
      const headingTitle = el('div', 'gallery-heading-title');
      const h3 = el('h3', '', categoryTitle(category.id));
      h3.id = `title-${category.id}`;
      headingTitle.append(el('span', 'section-index', pad(categoryIndex + 1)), h3);
      headingLeft.append(headingTitle, el('p', 'gallery-subtitle', t(`cat.${category.id}.description`)));
      header.append(headingLeft, el('span', 'section-total', t('card.imageCount', { count: pad(items.length) })));
      const grid = el('div', 'gallery-grid');
      items.forEach((item) => {
        const card = el('article', 'image-card');
        const openButton = el('button', 'image-open');
        openButton.type = 'button';
        openButton.setAttribute('aria-label', t('card.openImage', { title: localized(item, 'title') }));
        openButton.dataset.imageId = item.id;
        const img = el('img');
        img.src = item.src;
        img.alt = localized(item, 'alt');
        img.loading = 'lazy';
        img.decoding = 'async';
        if (item.width && item.height) { img.width = item.width; img.height = item.height; }
        openButton.append(img);
        openButton.addEventListener('click', () => openImage(item.id));
        const description = el('div', 'card-description');
        const titleLine = el('div', 'card-title-line');
        titleLine.append(el('h4', 'card-title', localized(item, 'title')), el('span', 'card-number', String(images.indexOf(item) + 1).padStart(3, '0')));
        description.append(titleLine, sourceLink(item));
        card.append(openButton, description);
        grid.append(card);
      });
      section.append(header, grid);
      sections.append(section);
    });
    const categoryLabel = selectedCategory === 'all' ? t('results.all') : categoryTitle(selectedCategory);
    $('#results-summary').textContent = t('results.base', { category: categoryLabel, count: visibleImages.length }) + (query ? t('results.search', { query: $('#search-input').value.trim() }) : '');
    $('#reset-filters').hidden = !query && selectedCategory === 'all';
    $('#empty-state').hidden = visibleImages.length !== 0;
  }

  function renderVideos() {
    const root = $('#video-grid');
    root.replaceChildren();
    videos.forEach((item, index) => {
      const card = el('article', 'video-card');
      const button = el('button', 'video-open');
      button.type = 'button';
      button.setAttribute('aria-label', t('cinema.openVideo', { title: localized(item, 'title') }));
      button.dataset.videoId = item.id;
      const poster = el('img');
      poster.src = item.poster;
      poster.alt = t('cinema.posterAlt', { title: localized(item, 'title') });
      poster.loading = 'lazy';
      const play = el('span', 'play-icon', '▶');
      play.setAttribute('aria-hidden', 'true');
      button.append(poster, play, el('span', 'video-tag', t('cinema.filmTag', { number: pad(index + 1) })));
      if (item.duration) button.append(el('span', 'video-duration', `${Math.floor(item.duration / 60)}:${pad(Math.floor(item.duration % 60))}`));
      button.addEventListener('click', () => openVideo(item));
      card.append(button, el('h3', 'video-title', localized(item, 'title')), el('p', 'video-description', localized(item, 'description')), sourceLink(item));
      root.append(card);
    });
  }

  function fillDetails(item, mode) {
    viewerItem = item;
    $('#viewer-category').textContent = mode === 'image' ? t('viewer.imageCategory', { category: categoryTitle(item.category) }) : t('viewer.videoCategory');
    $('#viewer-title').textContent = localized(item, 'title');
    $('#viewer-description').textContent = mode === 'image' ? t('viewer.imageDescription') : localized(item, 'description');
    $('#viewer-source').textContent = `${localized(item, 'sourceName')} ↗`;
    $('#viewer-source').href = item.sourceUrl;
    $('#viewer-creator').textContent = localized(item, 'creator') || t('viewer.unverified');
    $('#viewer-note').textContent = sourceSummary(item);
    $('#viewer-original').href = mode === 'image' ? item.originalImageUrl : item.originalVideoUrl;
    $('#viewer-pagination').hidden = mode !== 'image';
  }

  function showDialog() {
    if (!dialog.open) dialog.showModal();
    document.body.classList.add('modal-open');
  }

  function paintImage() {
    const item = viewerImages[currentIndex];
    const img = el('img');
    img.src = item.src;
    img.alt = localized(item, 'alt');
    media.replaceChildren(img);
    fillDetails(item, 'image');
    $('#viewer-position').textContent = `${pad(currentIndex + 1)} / ${pad(viewerImages.length)}`;
    $('#viewer-prev').disabled = viewerImages.length < 2;
    $('#viewer-next').disabled = viewerImages.length < 2;
  }

  function openImage(id) {
    viewerMode = 'image';
    viewerImages = visibleImages.some((item) => item.id === id) ? [...visibleImages] : [...images];
    currentIndex = viewerImages.findIndex((item) => item.id === id);
    if (currentIndex < 0) return;
    paintImage();
    showDialog();
  }

  function openVideo(item) {
    viewerMode = 'video';
    const video = el('video');
    video.controls = true;
    video.playsInline = true;
    video.preload = 'metadata';
    video.poster = item.poster;
    video.src = item.src;
    video.setAttribute('aria-label', localized(item, 'title'));
    video.append(document.createTextNode(t('cinema.noSupport')));
    video.addEventListener('error', () => {
      const fallback = el('p', 'media-fallback', t('cinema.failed'));
      fallback.append(el('br'), external(item.originalVideoUrl, '', t('cinema.openOriginal')));
      media.replaceChildren(fallback);
    }, { once: true });
    media.replaceChildren(video);
    fillDetails(item, 'video');
    showDialog();
  }

  function navigateImage(direction) {
    if (!viewerImages.length) return;
    currentIndex = (currentIndex + direction + viewerImages.length) % viewerImages.length;
    paintImage();
  }
  $('#viewer-prev').addEventListener('click', () => navigateImage(-1));
  $('#viewer-next').addEventListener('click', () => navigateImage(1));
  $('.viewer-close').addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', (event) => {
    if (event.target !== dialog) return;
    const bounds = dialog.getBoundingClientRect();
    if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) dialog.close();
  });
  dialog.addEventListener('close', () => {
    const video = media.querySelector('video');
    if (video) { video.pause(); video.removeAttribute('src'); video.load(); }
    media.replaceChildren();
    document.body.classList.remove('modal-open');
  });
  document.addEventListener('keydown', (event) => {
    if (dialog.open && viewerMode === 'image') {
      if (event.key === 'ArrowRight') { event.preventDefault(); navigateImage(1); }
      if (event.key === 'ArrowLeft') { event.preventDefault(); navigateImage(-1); }
    }
    if (event.key === '/' && !dialog.open && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName || '')) {
      event.preventDefault();
      $('#search-input').focus();
      $('#collection').scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
    }
  });
  function resetFilters() {
    query = '';
    selectedCategory = 'all';
    $('#search-input').value = '';
    renderFilters();
    renderGallery();
  }
  $('#search-input').addEventListener('input', (event) => { query = event.target.value.trim().toLocaleLowerCase(); renderGallery(); });
  $('#reset-filters').addEventListener('click', resetFilters);
  $('#empty-reset').addEventListener('click', resetFilters);
  $('#random-naiwa').addEventListener('click', () => {
    if (images.length) openImage(images[Math.floor(Math.random() * images.length)].id);
  });
  const menu = $('.menu-toggle');
  menu.addEventListener('click', () => {
    const expanded = menu.getAttribute('aria-expanded') !== 'true';
    menu.setAttribute('aria-expanded', String(expanded));
    menu.setAttribute('aria-label', t(expanded ? 'nav.close' : 'nav.open'));
    $('#main-nav').classList.toggle('open', expanded);
  });
  $('#main-nav').addEventListener('click', (event) => {
    if (!event.target.closest('a')) return;
    menu.setAttribute('aria-expanded', 'false');
    menu.setAttribute('aria-label', t('nav.open'));
    $('#main-nav').classList.remove('open');
  });
  function renderSourceLinks() {
  const sourceRoot = $('#source-links');
  sourceRoot.replaceChildren();
  [
    ['https://nailong-studio.github.io/NaiLong-Universe/', t('sources.galleryLabel')],
    ['https://github.com/Nailong-Studio/wallpaper', t('sources.repoLabel')]
  ].forEach(([url, name]) => {
    const link = external(url, '', '');
    link.append(el('span', '', name), el('span', '', '↗'));
    sourceRoot.append(link);
  });
  }
  document.addEventListener('naiwa:languagechange', () => {
    renderFilters();
    renderGallery();
    renderVideos();
    renderSourceLinks();
    if (hero) {
      $('#hero-image').alt = localized(hero, 'alt');
      $('#hero-source').title = t('hero.sourceTitle', { name: localized(hero, 'sourceName') });
    }
    menu.setAttribute('aria-label', t(menu.getAttribute('aria-expanded') === 'true' ? 'nav.close' : 'nav.open'));
    if (dialog.open && viewerItem) {
      fillDetails(viewerItem, viewerMode);
      const image = media.querySelector('img');
      const video = media.querySelector('video');
      if (image) image.alt = localized(viewerItem, 'alt');
      if (video) {
        video.setAttribute('aria-label', localized(viewerItem, 'title'));
        video.textContent = t('cinema.noSupport');
      }
      const fallback = media.querySelector('.media-fallback');
      if (fallback) {
        fallback.replaceChildren(document.createTextNode(t('cinema.failed')), el('br'), external(viewerItem.originalVideoUrl, '', t('cinema.openOriginal')));
      }
    }
  });
  renderFilters();
  renderGallery();
  renderVideos();
  renderSourceLinks();
})();
