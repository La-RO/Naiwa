(() => {
  'use strict';
  const images = Array.isArray(window.NAIWA_IMAGES) ? window.NAIWA_IMAGES : [];
  const videos = Array.isArray(window.NAIWA_VIDEOS) ? window.NAIWA_VIDEOS : [];
  const categories = [
    { id: 'expressions', title: '日常表情', english: 'JUST EXISTING', description: '笑一笑，发会儿呆。没有特别的原因。' },
    { id: 'art', title: '奶蛙名画', english: 'ART, APPARENTLY', description: '艺术没有边界。奶蛙也没有。' },
    { id: 'variants', title: '穿搭与变体', english: 'SAME FROG, DIFFERENT DAY', description: '换一种颜色，依然不太对劲。' },
    { id: 'scenes', title: '出没现场', english: 'FOUND SOMEWHERE', description: '它为什么在这里？先不要问。' }
  ];
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
    link.title = `查看来源：${item.sourceName}`;
    link.append(el('span', 'source-label', '来源：'), el('span', 'source-name', item.sourceName), el('span', '', '↗'));
    return link;
  };
  const pad = (num) => String(num).padStart(2, '0');
  const sourceSummary = (item) => item.sourceNote || '收录自公开网页，原创作者未核实。';

  if (document.body.dataset.page === 'sources') {
    $('#source-count').textContent = `${images.length} 张图片 · ${videos.length} 段视频 · 分类为本站整理`;
    const addEntries = (items, container, isVideo) => {
      items.forEach((item) => {
        const entry = el('article', 'source-entry');
        const thumbnail = el('img');
        thumbnail.src = isVideo ? item.poster : item.src;
        thumbnail.alt = isVideo ? `${item.title}的视频封面` : item.alt;
        thumbnail.loading = 'lazy';
        const details = el('div');
        details.append(el('h3', '', `${item.title}${isVideo ? ' / 视频' : ` / ${item.categoryLabel}`}`));
        details.append(el('p', '', `收录来源：${item.sourceName} · 原创作者：${item.creator || '未核实'}`));
        const links = el('div', 'source-entry-links');
        links.append(external(item.sourceUrl, '', '查看来源网页 ↗'), external(isVideo ? item.originalVideoUrl : item.originalImageUrl, '', '查看原始资源 ↗'));
        details.append(links, el('p', '', sourceSummary(item)));
        entry.append(thumbnail, details);
        container.append(entry);
      });
    };
    addEntries(images, $('#image-sources'), false);
    addEntries(videos, $('#video-sources'), true);
    return;
  }

  let selectedCategory = 'all';
  let query = '';
  let visibleImages = [...images];
  let viewerImages = [...images];
  let currentIndex = 0;
  let viewerMode = 'image';
  const dialog = $('#media-viewer');
  const media = $('#viewer-media');
  $('#image-count').textContent = images.length;
  $('#category-count').textContent = categories.filter((c) => images.some((image) => image.category === c.id)).length;
  $('#video-count').textContent = videos.length;

  const hero = images.find((item) => item.id === 'expressions-l-18') || images[0];
  if (hero) {
    $('#hero-image').src = hero.src;
    $('#hero-image').alt = hero.alt;
    $('#hero-source').href = hero.sourceUrl;
    $('#hero-source').title = `图像来源：${hero.sourceName}`;
  }

  function renderFilters() {
    const filterRoot = $('#category-filters');
    filterRoot.replaceChildren();
    [{ id: 'all', title: '全部奶蛙' }, ...categories].forEach((category) => {
      const count = category.id === 'all' ? images.length : images.filter((item) => item.category === category.id).length;
      const button = el('button', `filter-button${selectedCategory === category.id ? ' active' : ''}`, category.title);
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
      const content = `${item.title} ${item.alt} ${item.categoryLabel} ${item.sourceName}`.toLocaleLowerCase();
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
      const h3 = el('h3', '', category.title);
      h3.id = `title-${category.id}`;
      headingTitle.append(el('span', 'section-index', pad(categoryIndex + 1)), h3);
      headingLeft.append(headingTitle, el('p', 'gallery-subtitle', category.description));
      header.append(headingLeft, el('span', 'section-total', `${pad(items.length)} IMAGES`));
      const grid = el('div', 'gallery-grid');
      items.forEach((item) => {
        const card = el('article', 'image-card');
        const openButton = el('button', 'image-open');
        openButton.type = 'button';
        openButton.setAttribute('aria-label', `查看大图：${item.title}`);
        openButton.dataset.imageId = item.id;
        const img = el('img');
        img.src = item.src;
        img.alt = item.alt;
        img.loading = 'lazy';
        img.decoding = 'async';
        if (item.width && item.height) { img.width = item.width; img.height = item.height; }
        openButton.append(img);
        openButton.addEventListener('click', () => openImage(item.id));
        const description = el('div', 'card-description');
        const titleLine = el('div', 'card-title-line');
        titleLine.append(el('h4', 'card-title', item.title), el('span', 'card-number', String(images.indexOf(item) + 1).padStart(3, '0')));
        description.append(titleLine, sourceLink(item));
        card.append(openButton, description);
        grid.append(card);
      });
      section.append(header, grid);
      sections.append(section);
    });
    const categoryLabel = selectedCategory === 'all' ? '全部分区' : categories.find((c) => c.id === selectedCategory)?.title;
    $('#results-summary').textContent = `${categoryLabel} · ${visibleImages.length} 张图片${query ? ` · 搜索「${$('#search-input').value.trim()}」` : ''}`;
    $('#reset-filters').hidden = !query && selectedCategory === 'all';
    $('#empty-state').hidden = visibleImages.length !== 0;
  }

  function renderVideos() {
    const root = $('#video-grid');
    videos.forEach((item, index) => {
      const card = el('article', 'video-card');
      const button = el('button', 'video-open');
      button.type = 'button';
      button.setAttribute('aria-label', `打开视频：${item.title}`);
      button.dataset.videoId = item.id;
      const poster = el('img');
      poster.src = item.poster;
      poster.alt = `${item.title}的视频封面`;
      poster.loading = 'lazy';
      const play = el('span', 'play-icon', '▶');
      play.setAttribute('aria-hidden', 'true');
      button.append(poster, play, el('span', 'video-tag', `FILM ${pad(index + 1)}`));
      if (item.duration) button.append(el('span', 'video-duration', `${Math.floor(item.duration / 60)}:${pad(Math.floor(item.duration % 60))}`));
      button.addEventListener('click', () => openVideo(item));
      card.append(button, el('h3', 'video-title', item.title), el('p', 'video-description', item.description), sourceLink(item));
      root.append(card);
    });
  }

  function fillDetails(item, mode) {
    $('#viewer-category').textContent = mode === 'image' ? `COLLECTION / ${item.categoryLabel}` : 'SCREENING ROOM / 奶蛙影像';
    $('#viewer-title').textContent = item.title;
    $('#viewer-description').textContent = mode === 'image' ? '互联网收录图像 · 分区由本站整理' : item.description;
    $('#viewer-source').textContent = `${item.sourceName} ↗`;
    $('#viewer-source').href = item.sourceUrl;
    $('#viewer-creator').textContent = item.creator || '未核实';
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
    img.alt = item.alt;
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
    video.setAttribute('aria-label', item.title);
    video.append(document.createTextNode('当前浏览器无法播放此视频，请打开原始资源观看。'));
    video.addEventListener('error', () => {
      const fallback = el('p', 'media-fallback', '当前浏览器无法播放这段影像。');
      fallback.append(el('br'), external(item.originalVideoUrl, '', '打开原始视频 ↗'));
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
    if (event.key === '/' && !dialog.open && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) {
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
    menu.setAttribute('aria-label', expanded ? '收起导航' : '展开导航');
    $('#main-nav').classList.toggle('open', expanded);
  });
  $('#main-nav').addEventListener('click', (event) => {
    if (!event.target.closest('a')) return;
    menu.setAttribute('aria-expanded', 'false');
    menu.setAttribute('aria-label', '展开导航');
    $('#main-nav').classList.remove('open');
  });
  const sourceRoot = $('#source-links');
  [
    ['https://nailong-studio.github.io/NaiLong-Universe/', '奶蛙艺术宇宙 / 图像与影像收录页'],
    ['https://github.com/Nailong-Studio/wallpaper', 'Nailong-Studio / 图片素材仓库']
  ].forEach(([url, name]) => {
    const link = external(url, '', '');
    link.append(el('span', '', name), el('span', '', '↗'));
    sourceRoot.append(link);
  });
  renderFilters();
  renderGallery();
  renderVideos();
})();
