(() => {
  'use strict';
  const messages = {
    en: {
      'page.homeTitle': 'naiwa club — Please remain round.',
      'page.sourcesTitle': 'Sources — naiwa club',
      'page.description': 'The Naiwa Club internet collection: expressions, art remixes, outfits, unexpected appearances and a screening room. Every image and film includes its source.',
      'language.label': 'Language', 'language.english': 'Switch to English', 'language.chinese': 'Switch to Chinese',
      'nav.homeAria': 'Naiwa Club home', 'nav.open': 'Open navigation', 'nav.close': 'Close navigation', 'nav.label': 'Main navigation',
      'nav.collection': 'Collection<span>Images & remixes</span>', 'nav.cinema': 'Cinema<span>Moving pictures</span>', 'nav.about': 'About<span>Club & sources</span>',
      'skip': 'Skip to the collection',
      'hero.welcome': "WELCOME BACK. WE'VE NEVER MET.",
      'hero.title': 'Please<br>remain <span>round.</span>',
      'hero.description': 'Welcome to Naiwa Club.<br>A little collection of very peculiar Naiwas.<br><span>Further instructions will not arrive.</span>',
      'hero.enter': 'Explore the collection <span aria-hidden="true">↓</span>',
      'hero.random': 'Meet a random Naiwa <span aria-hidden="true">↗</span>',
      'hero.countImages': 'internet images', 'hero.countCategories': 'odd little corners', 'hero.countVideos': 'short films',
      'hero.stamp': 'STILL<br>HERE.<span>✳</span>', 'hero.figure': 'FIG. 001 / NAIWA, JUST EXISTING.',
      'hero.source': 'Image source <span aria-hidden="true">↗</span>', 'hero.sourceTitle': 'Image source: {name}',
      'ticker.nothoughts': 'NO THOUGHTS. JUST NAIWA.', 'ticker.round': 'PLEASE REMAIN ROUND.', 'ticker.instructions': 'FURTHER INSTRUCTIONS WILL NOT ARRIVE.',
      'collection.eyebrow': 'THE NAIWA COLLECTION', 'collection.title': 'A Naiwa for<br>every state of mind.',
      'collection.intro': 'Find a face. Wander through a painting.<br>Spot a Naiwa somewhere it probably should not be.<br><span>Click an image to explore. Follow its source to go back.</span>',
      'collection.filtersAria': 'Filter images by category', 'collection.searchLabel': 'Search Naiwa images', 'collection.searchPlaceholder': 'Find a Naiwa…',
      'collection.reset': 'Clear filters ↺', 'collection.emptyTitle': 'This Naiwa is somewhere else.',
      'collection.emptyBody': 'Try another word, or take a look at the whole collection.',
      'collection.emptyReset': 'See all images <span aria-hidden="true">↗</span>',
      'collection.noscript': 'Enable JavaScript to browse the collection and films. All media and source lists are also included in the website folder.',
      'cat.all': 'All Naiwas', 'cat.expressions.title': 'Expressions', 'cat.expressions.description': 'Just laughing. Just existing. No particular reason.',
      'cat.art.title': 'Art Remixes', 'cat.art.description': 'Art has no boundaries. Neither does Naiwa.',
      'cat.variants.title': 'Outfits & Variants', 'cat.variants.description': 'A different colour. The same strange energy.',
      'cat.scenes.title': 'Out in the World', 'cat.scenes.description': 'Why is it here? Let us not ask just yet.',
      'results.all': 'All categories', 'results.base': '{category} · {count} images', 'results.search': ' · Search: “{query}”',
      'card.openImage': 'View image: {title}', 'card.sourceTitle': 'View source: {name}', 'card.source': 'Source:', 'card.imageCount': '{count} IMAGES',
      'cinema.eyebrow': '<span class="screen-dot" aria-hidden="true"></span> THE SCREENING ROOM',
      'cinema.title': 'Take a seat.<br>They are moving now.',
      'cinema.intro': 'From still images to moving pictures.<br>Step into a small Naiwa universe.<br><span>Every film includes its collected source.</span>',
      'cinema.footnote': '<span aria-hidden="true">↗</span> Watch here, or visit the source website.',
      'cinema.openVideo': 'Open film: {title}', 'cinema.posterAlt': 'Poster for {title}', 'cinema.filmTag': 'FILM {number}',
      'cinema.noSupport': 'Your browser cannot play this film. Open the original video to watch it.',
      'cinema.failed': 'This browser cannot play this film.', 'cinema.openOriginal': 'Open the original video ↗',
      'about.eyebrow': 'A SMALL CORNER OF THE INTERNET', 'about.title': 'About this<br>very round corner.',
      'about.body': 'The Naiwa Club collection gathers images and films from across the internet into a little corner worth wandering through.',
      'about.absurd': "Welcome back. We've never met.<br>Both things can be true.",
      'sources.eyebrow': 'ON SOURCES', 'sources.noteHeading': 'Every Naiwa<br>has a way back.',
      'sources.noteBody': 'Every image and film has a source link. Open an image or film to find the original asset address and collection notes.',
      'sources.noteAttribution': 'The categories are curated here. Collected sources and original creators are labelled separately; creator information we could not verify is marked “Unverified”.',
      'sources.complete': 'View the complete source list <span aria-hidden="true">↗</span>',
      'sources.galleryLabel': 'Naiwa Art Universe / image & film gallery', 'sources.repoLabel': 'Nailong-Studio / image repository',
      'sources.back': '← <span>Back to collection</span>', 'sources.pageEyebrow': 'THE WAY BACK / WHERE EACH NAIWA CAME FROM',
      'sources.title': 'The complete source list',
      'sources.intro': 'Every collected image and film is listed here with its source page, original asset and creator attribution status. A gallery or repository is not automatically the original creator. Creator details that could not be verified are marked “Unverified”.',
      'sources.count': '{images} images · {videos} films · Categories curated by Naiwa Club',
      'sources.imagesHeading': 'Images', 'sources.videosHeading': 'Films', 'sources.videoType': 'Film',
      'sources.entryMeta': 'Collected from: {source} · Original creator: {creator}',
      'sources.openPage': 'View source page ↗', 'sources.openAsset': 'View original asset ↗',
      'footer.copy': 'Please remain round.<br><span>Further instructions will not arrive.</span>',
      'footer.bottomTag': 'NAIWA CLUB / INTERNET COLLECTION', 'footer.bottomNote': 'Welcome back. Nothing urgent.', 'backTop': 'Back to top',
      'viewer.close': 'Close preview', 'viewer.prev': 'Previous image', 'viewer.next': 'Next image',
      'viewer.imageCategory': 'COLLECTION / {category}', 'viewer.videoCategory': 'SCREENING ROOM / NAIWA FILMS',
      'viewer.imageDescription': 'Collected from the internet · Categories curated by Naiwa Club',
      'viewer.sourceLabel': 'Collected source', 'viewer.creatorLabel': 'Original creator', 'viewer.unverified': 'Unverified',
      'viewer.defaultNote': 'Collected from a public webpage; the original creator has not been verified.',
      'viewer.original': 'Open original asset <span aria-hidden="true">↗</span>'
    },
    'zh-CN': {
      'page.homeTitle': 'naiwa club — 请保持圆润。', 'page.sourcesTitle': '素材来源 — naiwa club',
      'page.description': 'Naiwa Club 的互联网奶蛙收藏室：日常表情、奶蛙名画、穿搭与变体、出没现场，以及独立影像放映室。每件收录附有来源。',
      'language.label': '语言', 'language.english': '切换为英语', 'language.chinese': '切换为中文',
      'nav.homeAria': 'Naiwa Club 首页', 'nav.open': '展开导航', 'nav.close': '收起导航', 'nav.label': '主导航',
      'nav.collection': '奶蛙图库<span>表情与二创</span>', 'nav.cinema': '放映室<span>奶蛙影像</span>', 'nav.about': '关于与来源<span>这个圆润的角落</span>',
      'skip': '跳到奶蛙图库', 'hero.welcome': '欢迎回来。我们从未见过。', 'hero.title': '请保持<br><span>圆润。</span>',
      'hero.description': '欢迎来到 Naiwa Club。<br>这里收集互联网里，各种不太对劲的奶蛙。<br><span>目前没有任何进一步指示。</span>',
      'hero.enter': '进入奶蛙收藏室 <span aria-hidden="true">↓</span>', 'hero.random': '随便遇见一只 <span aria-hidden="true">↗</span>',
      'hero.countImages': '张互联网奶蛙', 'hero.countCategories': '个不明状态分区', 'hero.countVideos': '段奶蛙影像',
      'hero.stamp': '仍在<br>这里。<span>✳</span>', 'hero.figure': '图 001 / 奶蛙，只是在这里。',
      'hero.source': '图像来源 <span aria-hidden="true">↗</span>', 'hero.sourceTitle': '图像来源：{name}',
      'ticker.nothoughts': '没有想法。只有奶蛙。', 'ticker.round': '请保持圆润。', 'ticker.instructions': '目前没有任何进一步指示。',
      'collection.eyebrow': '奶蛙收藏室 / 奶蛙收集计划', 'collection.title': '每一种状态，<br>都有一只奶蛙。',
      'collection.intro': '看看表情，路过名画，<br>再去一些不该出现奶蛙的地方。<br><span>点击图片放大，点击来源回到原页。</span>',
      'collection.filtersAria': '按图片分区筛选', 'collection.searchLabel': '搜索奶蛙图片', 'collection.searchPlaceholder': '寻找一只奶蛙…',
      'collection.reset': '清除筛选 ↺', 'collection.emptyTitle': '这只奶蛙暂时不在这里。', 'collection.emptyBody': '换个关键词，或者看看全部奶蛙。',
      'collection.emptyReset': '回到全部图片 <span aria-hidden="true">↗</span>',
      'collection.noscript': '请启用 JavaScript 来浏览分类图库与视频。所有素材及来源清单均在网站文件夹中。',
      'cat.all': '全部奶蛙', 'cat.expressions.title': '日常表情', 'cat.expressions.description': '笑一笑，发会儿呆。没有特别的原因。',
      'cat.art.title': '奶蛙名画', 'cat.art.description': '艺术没有边界。奶蛙也没有。',
      'cat.variants.title': '穿搭与变体', 'cat.variants.description': '换一种颜色，依然不太对劲。',
      'cat.scenes.title': '出没现场', 'cat.scenes.description': '它为什么在这里？先不要问。',
      'results.all': '全部分区', 'results.base': '{category} · {count} 张图片', 'results.search': ' · 搜索「{query}」',
      'card.openImage': '查看大图：{title}', 'card.sourceTitle': '查看来源：{name}', 'card.source': '来源：', 'card.imageCount': '{count} 张图片',
      'cinema.eyebrow': '<span class="screen-dot" aria-hidden="true"></span> 奶蛙放映室',
      'cinema.title': '请落座。<br>它们开始动了。', 'cinema.intro': '从图像走进影像。<br>点开一段，进入奶蛙的短暂宇宙。<br><span>每段影像均保留收录来源。</span>',
      'cinema.footnote': '<span aria-hidden="true">↗</span> 可以在这里播放，也可以前往来源网站观看。',
      'cinema.openVideo': '打开视频：{title}', 'cinema.posterAlt': '{title}的视频封面', 'cinema.filmTag': '影像 {number}',
      'cinema.noSupport': '当前浏览器无法播放此视频，请打开原始资源观看。', 'cinema.failed': '当前浏览器无法播放这段影像。', 'cinema.openOriginal': '打开原始视频 ↗',
      'about.eyebrow': '互联网里的一个圆润角落', 'about.title': '关于这个<br>圆润的角落。',
      'about.body': 'Naiwa Club 的奶蛙收藏室，把散落在互联网里的图像与影像，整理成一个可以慢慢逛的地方。',
      'about.absurd': '欢迎回来。我们从未见过。<br>这两件事可以同时成立。',
      'sources.eyebrow': '关于来源', 'sources.noteHeading': '每一只奶蛙，<br>都有一条来路。',
      'sources.noteBody': '图片卡片和影像卡片都附有来源链接；打开大图，还可以查看原始资源地址与收录说明。',
      'sources.noteAttribution': '分区是本站的整理方式。收录网站与原创作者分别标注，未能核实的作者信息直接标为「未核实」。',
      'sources.complete': '查看完整素材来源清单 <span aria-hidden="true">↗</span>',
      'sources.galleryLabel': '奶蛙艺术宇宙 / 图像与影像收录页', 'sources.repoLabel': 'Nailong-Studio / 图片素材仓库',
      'sources.back': '← <span>返回收藏室</span>', 'sources.pageEyebrow': '每一只奶蛙的来路', 'sources.title': '完整素材来源清单',
      'sources.intro': '这里逐项列出网站所收录的互联网图像与影像。每项均提供收录来源、原始资源链接与作者标注状态。来源网站或素材仓库不自动等同于原创作者；无法核实的作者信息直接标为「未核实」。',
      'sources.count': '{images} 张图片 · {videos} 段视频 · 分类为本站整理', 'sources.imagesHeading': '图片', 'sources.videosHeading': '影像', 'sources.videoType': '视频',
      'sources.entryMeta': '收录来源：{source} · 原创作者：{creator}', 'sources.openPage': '查看来源网页 ↗', 'sources.openAsset': '查看原始资源 ↗',
      'footer.copy': '请保持圆润。<br><span>目前没有任何进一步指示。</span>', 'footer.bottomTag': 'NAIWA CLUB / 互联网收藏室', 'footer.bottomNote': '欢迎回来。没什么要紧的。', 'backTop': '回到顶部',
      'viewer.close': '关闭预览', 'viewer.prev': '上一张图片', 'viewer.next': '下一张图片',
      'viewer.imageCategory': '奶蛙收藏室 / {category}', 'viewer.videoCategory': '放映室 / 奶蛙影像',
      'viewer.imageDescription': '互联网收录图像 · 分区由本站整理', 'viewer.sourceLabel': '收录来源', 'viewer.creatorLabel': '原创作者', 'viewer.unverified': '未核实',
      'viewer.defaultNote': '收录自公开网页，原创作者未核实。', 'viewer.original': '打开原始资源 <span aria-hidden="true">↗</span>'
    }
  };
  const STORAGE_KEY = 'naiwa-club-language';
  const supported = (value) => value === 'en' || value === 'zh-CN';
  let saved = null;
  let requested = null;
  try { saved = window.localStorage.getItem(STORAGE_KEY); } catch (_) { /* File URLs or private mode may restrict storage. */ }
  try { requested = new URL(window.location.href).searchParams.get('lang'); } catch (_) { /* The initial default remains English. */ }
  let language = supported(requested) ? requested : (supported(saved) ? saved : 'en');
  const t = (key, values = {}) => {
    const template = messages[language][key] ?? messages.en[key] ?? key;
    return template.replace(/\{(\w+)\}/g, (match, name) => values[name] === undefined ? match : String(values[name]));
  };
  const localized = (item, field) => language === 'en' ? (item[`${field}En`] ?? item[field]) : item[field];
  function applyStatic() {
    document.documentElement.lang = language;
    document.title = t(document.body.dataset.page === 'sources' ? 'page.sourcesTitle' : 'page.homeTitle');
    const description = document.querySelector('meta[name="description"]');
    if (description) description.content = t('page.description');
    document.querySelectorAll('[data-i18n]').forEach((node) => { node.textContent = t(node.getAttribute('data-i18n')); });
    document.querySelectorAll('[data-i18n-html]').forEach((node) => { node.innerHTML = t(node.getAttribute('data-i18n-html')); });
    ['aria-label', 'placeholder', 'title'].forEach((attribute) => {
      document.querySelectorAll(`[data-i18n-${attribute}]`).forEach((node) => {
        node.setAttribute(attribute, t(node.getAttribute(`data-i18n-${attribute}`)));
      });
    });
    document.querySelectorAll('[data-language]').forEach((button) => {
      const selected = button.dataset.language === language;
      button.classList.toggle('active', selected);
      button.setAttribute('aria-pressed', String(selected));
    });
    document.querySelectorAll('[data-language-link]').forEach((link) => {
      const base = link.dataset.languageLink;
      const [path, hash] = base.split('#');
      link.setAttribute('href', `${path}?lang=${language}${hash ? `#${hash}` : ''}`);
    });
  }
  function setLanguage(next) {
    if (!supported(next) || next === language) return;
    language = next;
    try { window.localStorage.setItem(STORAGE_KEY, language); } catch (_) { /* Switching still works in memory. */ }
    try {
      const url = new URL(window.location.href);
      url.searchParams.set('lang', language);
      window.history.replaceState(null, '', url.href);
    } catch (_) { /* Cross-page links also carry the selected language. */ }
    applyStatic();
    document.dispatchEvent(new CustomEvent('naiwa:languagechange', { detail: { language } }));
  }
  window.NAIWA_I18N = Object.freeze({ t, localized, applyStatic, setLanguage, get language() { return language; } });
  document.querySelectorAll('[data-language]').forEach((button) => {
    button.addEventListener('click', () => setLanguage(button.dataset.language));
  });
  applyStatic();
})();
