/* ============================================
   Presentation JS — TOC, Video, Fullscreen
   ============================================ */

/* ── Slide loader ── */
var SLIDES = [
  '01-title.html',              // 0
  '02-shopping-time.html',      // 1
  '03-problem.html',            // 2
  '04-we-came.html',            // 3
  '05-shoppinkki-reveal.html',  // 4
  '06-solution.html',           // 5
  '07-idea.html',               // 6
  '08-ux.html',                 // 7
  '09-hardware-intro.html',     // 8
  '10-robot.html',              // 9
  '11-doll.html',               // 10
  '12-doll-25000.html',         // 11
  '13-system-intro.html',       // 12
  '14-architecture.html',       // 13
  '15-techstack.html',          // 14
  '16-structure-overview.html', // 15
  '17-structure-device.html',   // 16
  '18-structure-interface.html',// 17
  '19-structure-mainnode.html', // 18
  '20-structure-server.html',   // 19
  '21-statemachine.html',       // 20
  '22-demoenv-intro.html',      // 21
  '23-environment.html',        // 22
  '24-zones.html',              // 23
  '25-simmap.html',             // 24
  '26-features.html',           // 25
  '27-intro-login.html',        // 26
  '28-login-1.html',            // 27
  '29-login-2.html',            // 28
  '30-login-3.html',            // 29
  '31-login-4.html',            // 30
  '32-intro-tracking.html',     // 31
  '33-tracking.html',           // 32
  '34-tracking-yolo.html',      // 33
  '35-tracking-bytetracker.html', // 34
  '36-tracking-reid-intro.html',  // 35
  '37-tracking-demo.html',      // 36
  '38-tracking-pcontrol.html',  // 37
  '39-intro-guide.html',        // 38
  '40-guide.html',              // 39
  '41-guide-pipeline.html',     // 40
  '42-guide-llm-demo.html',     // 41
  '43-multi-robot.html',        // 42
  '44-openrmf-intro.html',      // 43
  '45-openrmf-setup.html',      // 44
  '46-fleet-map.html',          // 45
  '47-guide-demo.html',         // 46
  '48-multi-robot-demo.html',   // 47
  '49-admin-demo.html',         // 48
  '50-intro-cart.html',         // 49
  '51-cart.html',               // 50
  '52-intro-waiting.html',      // 51
  '53-waiting.html',            // 52
  '54-waiting-demo.html',       // 53
  '55-intro-checkout.html',     // 54
  '56-checkout.html',           // 55
  '57-checkout-demo.html',      // 56
  '58-intro-return.html',       // 57
  '59-return.html',             // 58
  '60-return-demo.html',        // 59
  '61-intro-final-demo.html',   // 60
  '62-final-demo.html',         // 61
  '63-retrospect.html',         // 62
  '64-team.html',               // 63
  '65-qa.html',                 // 64
  '66-references.html',         // 65
  '67-ref-cosine.html',         // 66
  '68-ref-hsv.html',            // 67
  '69-ref-kalman.html',         // 68
  '70-ref-hungarian.html',      // 69
  '71-ref-iou.html',            // 70
];

var SLIDE_TITLES = [
  '쑈삥끼',                                    // 0  01-title
  '우리는 마트에서 얼마나 시간을 보낼까?',    // 1  02-shopping-time
  '쇼핑의 3대 불편',                           // 2  03-problem
  '우리가 왔읍니다',                            // 3  04-we-came
  '쑈삥끼',                                    // 4  05-shoppinkki-reveal
  '쑈삥끼',                                    // 5  06-solution
  '아이디어 - Carrefour Scan\'lib',            // 6  07-idea
  'User Journey',                              // 7  08-ux
  '하드웨어 정보',                             // 8  09-hardware-intro
  'Pinky Pro, Basket Edition',                 // 9  10-robot
  '사용자 인형',                               // 10 11-doll
  '25,000원으로 할 수 있는 일',               // 11 12-doll-25000
  '시스템 구성',                               // 12 13-system-intro
  'System Architecture',                       // 13 14-architecture
  'Tech Stack',                                // 14 15-techstack
  '프로젝트 구조',                             // 15 16-structure-overview
  '프로젝트 구조: device/ 패키지',             // 16 17-structure-device
  'shoppinkki_core — 클래스 관계도',           // 17 18-structure-interface
  'ShoppinkkiMainNode — 실행 흐름',            // 18 19-structure-mainnode
  '프로젝트 구조: server/ 패키지',             // 19 20-structure-server
  'State Diagram',                             // 20 21-statemachine
  '데모 환경',                                 // 21 22-demoenv-intro
  '미니어처 마트',                             // 22 23-environment
  '구역 구성',                                 // 23 24-zones
  '시뮬레이션 맵',                             // 24 25-simmap
  '핵심기능 7가지',                            // 25 26-features
  '로그인',                                    // 26 27-intro-login
  '핵심 기능 1: 로그인',                       // 27 28-login-1
  '핵심 기능 1: 로그인',                       // 28 29-login-2
  '핵심 기능 1: 로그인',                       // 29 30-login-3
  '핵심 기능 1: 로그인',                       // 30 31-login-4
  '추종',                                      // 31 32-intro-tracking
  '핵심 기능 2: 추종',                         // 32 33-tracking
  '추종: 커스텀 YOLOv8',                       // 33 34-tracking-yolo
  '추종: ByteTracker',                         // 34 35-tracking-bytetracker
  '추종: ReID와 HSV란?',                       // 35 36-tracking-reid-intro
  '추종 테스트',                               // 36 37-tracking-demo
  '추종: bbox 기반 PI 제어',                   // 37 38-tracking-pcontrol
  '가이드',                                    // 38 39-intro-guide
  '핵심 기능 3: 가이드',                       // 39 40-guide
  '가이드: 검색 파이프라인',                   // 40 41-guide-pipeline
  '가이드 Demo — 채팅 검색',                  // 41 42-guide-llm-demo
  '가이드: 다중 로봇 제어',                    // 42 43-multi-robot
  '가이드: Open-RMF란?',                       // 43 44-openrmf-intro
  '가이드: Open-RMF 사용을 위한 준비',         // 44 45-openrmf-setup
  '가이드: Fleet 웨이포인트 배치',             // 45 46-fleet-map
  '가이드 Demo — 로봇 1대',                   // 46 47-guide-demo
  '가이드 Demo — 로봇 2대',                   // 47 48-multi-robot-demo
  '가이드 Demo — Admin UI',                   // 48 49-admin-demo
  '장바구니',                                  // 49 50-intro-cart
  '핵심 기능 4: 장바구니',                     // 50 51-cart
  '대기',                                      // 51 52-intro-waiting
  '핵심 기능 5: 대기',                         // 52 53-waiting
  '대기 Demo',                                 // 53 54-waiting-demo
  '결제',                                      // 54 55-intro-checkout
  '핵심 기능 6: 결제',                         // 55 56-checkout
  '결제 Demo',                                 // 56 57-checkout-demo
  '복귀',                                      // 57 58-intro-return
  '핵심 기능 7: 복귀',                         // 58 59-return
  '복귀 Demo',                                 // 59 60-return-demo
  '최종 데모',                                 // 60 61-intro-final-demo
  '',                                          // 61 62-final-demo
  '회고',                                      // 62 63-retrospect
  '팀원 소개',                                 // 63 64-team
  'Q & A',                                    // 64 65-qa
  '참고자료',                                  // 65 66-references
  '참고자료 1: 코사인 유사도란?',              // 66 67-ref-cosine
  '참고자료 2: HSV 히스토그램 상관계수란?',    // 67 68-ref-hsv
  '참고자료 3: Kalman Filter',                 // 68 69-ref-kalman
  '참고자료 4: Hungarian Algorithm',           // 69 70-ref-hungarian
  '참고자료 5: IoU (Intersection over Union)', // 70 71-ref-iou
];

async function loadSlides() {
  var container = document.querySelector('.reveal .slides');
  // Fetch all slides in parallel (53 → 1 round-trip)
  var responses = await Promise.all(
    SLIDES.map(function(name) { return fetch('slides/' + name); })
  );
  var htmls = await Promise.all(responses.map(function(r) { return r.text(); }));
  htmls.forEach(function(html) {
    container.insertAdjacentHTML('beforeend', html);
  });
}

async function initPresentation() {
  await loadSlides();

  Reveal.initialize({
    hash: true,
    center: false,
    slideNumber: 'c/t',
    width: 1280,
    height: 720,
    margin: 0.04,
    minScale: 0.1,
    maxScale: 2.0,
    transition: 'none',
    transitionSpeed: 'fast',
    plugins: [RevealNotes, RevealHighlight],
    keyboard: {
      80: function() { toggleVideo(); },   // P
      70: function() { toggleFullscreen(); }, // F
    }
  });

  // Force center-align (vertically)
  function forceCenterAlign() {
    var slideHeight = 720; // from Reveal.initialize
    document.querySelectorAll('.reveal .slides section').forEach(function(s) {
      var sectionHeight = s.offsetHeight;
      var topOffset = (slideHeight - sectionHeight) / 2;
      s.style.top = topOffset + 'px';
    });
  }
  Reveal.on('ready', function() {
    // Hide loading screen
    var loadingScreen = document.getElementById('loading-screen');
    if (loadingScreen) {
      loadingScreen.style.transition = 'opacity 0.4s';
      loadingScreen.style.opacity = '0';
      setTimeout(function() { loadingScreen.remove(); }, 400);
    }
    initLoginPipelines();
    initVideoControls();
    forceCenterAlign();
    // Make slide number indicator clickable
    var slideNum = document.querySelector('.reveal .slide-number');
    if (slideNum) {
      slideNum.addEventListener('click', function(e) {
        e.stopPropagation();
        toggleSlidePanel();
      });
    }
  });
  Reveal.on('slidechanged', function(event) {
    forceCenterAlign();
    // Update active state in panel if open
    var panel = document.getElementById('slide-panel');
    if (panel && !panel.classList.contains('hidden')) {
      updateSlidePanelActive();
    }
    // Auto-pause demo video when leaving demo slide
    var video = document.getElementById('demo-video');
    var container = document.getElementById('video-container');
    if (video && event.currentSlide.id !== 'demo-slide') {
      video.pause();
      if (container) container.classList.remove('playing');
    }
    // Re-play all autoplay looping videos on the current slide
    event.currentSlide.querySelectorAll('video[autoplay]').forEach(function(v) {
      v.currentTime = 0;
      v.play();
    });
  });
}

/* ── Video play/pause ── */
function toggleVideo() {
  var video = document.getElementById('demo-video');
  var container = document.getElementById('video-container');
  if (!video || (!video.src && !video.querySelector('source[src]'))) return;
  if (video.paused) {
    video.play();
    container.classList.add('playing');
  } else {
    video.pause();
    container.classList.remove('playing');
  }
}

/* ── Slide link (뒤로가기 지원) ── */
function goToSlide(index) {
  var cur = Reveal.getIndices().h;
  history.pushState(null, '', '#/' + cur);
  Reveal.slide(index);
}

/* ── Fullscreen ── */
function toggleFullscreen() {
  if (!document.fullscreenElement) {
    document.documentElement.requestFullscreen();
  } else {
    document.exitFullscreen();
  }
}

function updateFullscreenHint() {
  var hint = document.getElementById('fullscreen-hint');
  if (!hint) return;
  if (document.fullscreenElement) {
    hint.innerHTML = 'Press <kbd style="background:#112236;border:1px solid #1E3A5A;border-radius:4px;padding:1px 5px;font-size:0.9em;color:#7BA5C8">ESC</kbd> to minimize';
  } else {
    hint.innerHTML = 'Press <kbd style="background:#112236;border:1px solid #1E3A5A;border-radius:4px;padding:1px 5px;font-size:0.9em;color:#7BA5C8">F</kbd> for fullscreen';
  }
}
document.addEventListener('fullscreenchange', updateFullscreenHint);

/* ── Slide Panel ── */
function buildSlidePanel() {
  var list = document.getElementById('slide-panel-list');
  list.innerHTML = '';
  var sections = document.querySelectorAll('.reveal .slides > section');
  var current = Reveal.getIndices().h;

  sections.forEach(function(section, i) {
    var item = document.createElement('div');
    item.className = 'slide-thumb-item' + (i === current ? ' active' : '');
    item.dataset.index = i;

    var preview = document.createElement('div');
    preview.className = 'slide-thumb-preview';
    var inner = document.createElement('div');
    inner.className = 'slide-thumb-inner';
    inner.innerHTML = section.innerHTML;
    preview.appendChild(inner);

    var meta = document.createElement('div');
    meta.className = 'slide-thumb-meta';
    meta.innerHTML = '<span class="slide-thumb-num">' + (i + 1) + '</span>'
                   + '<span class="slide-thumb-title">' + (SLIDE_TITLES[i] || '') + '</span>';

    item.appendChild(meta);
    item.appendChild(preview);
    item.addEventListener('click', function() {
      Reveal.slide(i);
      closeSlidePanel();
    });
    list.appendChild(item);
  });
}

function updateSlidePanelActive() {
  var current = Reveal.getIndices().h;
  document.querySelectorAll('.slide-thumb-item').forEach(function(el, i) {
    el.classList.toggle('active', i === current);
  });
  // Scroll active item into view
  var activeEl = document.querySelector('.slide-thumb-item.active');
  if (activeEl) activeEl.scrollIntoView({ block: 'nearest' });
}

function toggleSlidePanel() {
  var panel = document.getElementById('slide-panel');
  if (!panel.classList.contains('hidden')) {
    closeSlidePanel();
  } else {
    buildSlidePanel();
    panel.classList.remove('hidden');
    panel.classList.add('flex');
    document.getElementById('slide-panel-overlay').classList.remove('hidden');
    // Scroll active item into view
    setTimeout(function() {
      var activeEl = document.querySelector('.slide-thumb-item.active');
      if (activeEl) activeEl.scrollIntoView({ block: 'center' });
    }, 50);
  }
}

function closeSlidePanel() {
  var panel = document.getElementById('slide-panel');
  panel.classList.add('hidden');
  panel.classList.remove('flex');
  document.getElementById('slide-panel-overlay').classList.add('hidden');
}

document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') closeSlidePanel();
});

/* ── Login Pipeline Component ── */
var LOGIN_STEPS = [
  { icon: 'qr_code_scanner', title: 'QR 스캔',        sub: '로봇 LCD' },
  { icon: 'smartphone',      title: '웹앱 접속',      sub: 'Flask + SocketIO' },
  { icon: 'smart_toy',       title: '주인 등록',      sub: '로봇 Pi 카메라' },
  { icon: 'person_pin_circle', title: 'TRACKING 시작', sub: 'IDLE → TRACKING' },
];

function renderLoginPipeline(activeIndex) {
  var html = '<div class="flex items-center justify-between w-full">';
  LOGIN_STEPS.forEach(function(step, i) {
    var isActive = i === activeIndex;
    var bg = isActive
      ? 'background:#0E2840;border:2px solid #38BDF8;box-shadow:0 0 20px rgba(56,189,248,0.25)'
      : 'background:#112236;border:1px solid #1E3A5A;opacity:0.45';
    var titleColor = isActive ? 'color:#FFFFFF' : 'color:#7BA5C8';
    var subColor = isActive ? 'color:#38BDF8' : 'color:#3A5A7A';
    var iconColor = isActive ? 'color:#38BDF8' : 'color:#3A5A7A';
    html += '<div class="rounded-xl px-2 py-2 text-center flex-1" style="' + bg + ';transition:all 0.3s">'
          + '<span class="material-icons-round text-em-xs block leading-none" style="' + iconColor + '">' + step.icon + '</span>'
          + '<div class="font-bold text-em-3xs mt-0.5" style="' + titleColor + '">' + step.title + '</div>'
          + '<div class="text-[0.35em]" style="' + subColor + '">' + step.sub + '</div>'
          + '</div>';
    if (i < LOGIN_STEPS.length - 1) {
      var arrowColor = (i === activeIndex || i + 1 === activeIndex) ? 'color:#38BDF8' : 'color:#1E3A5A';
      html += '<div class="pipeline-arrow text-em-2xl" style="' + arrowColor + '"></div>';
    }
  });
  html += '</div>';
  return html;
}

// Auto-render login pipelines after Reveal is ready
function initLoginPipelines() {
  document.querySelectorAll('[data-login-step]').forEach(function(el) {
    var step = parseInt(el.getAttribute('data-login-step'));
    el.innerHTML = renderLoginPipeline(step);
  });
}

/* ── Video Controls Component ── */
function initVideoControls() {
  document.querySelectorAll('[data-video-controls]').forEach(function(el) {
    var videoId = el.getAttribute('data-video-controls');
    var speeds = [1.0, 1.5, 2.0, 3.0];
    var scopeAttr = 'data-speed-' + videoId;
    var seekBarId = 'seek-' + videoId;
    var timeId = 'time-' + videoId;

    var btnsHtml = speeds.map(function(s, i) {
      var active = i === 0;
      var border = active ? '#38BDF8' : '#1E3A5A';
      var color  = active ? '#38BDF8' : '#E2E8F0';
      return '<button'
        + ' onclick="(function(b){document.getElementById(\'' + videoId + '\').playbackRate=' + s + ';'
        + 'document.querySelectorAll(\'[' + scopeAttr + ']\').forEach(function(x){x.style.borderColor=\'#1E3A5A\';x.style.color=\'#E2E8F0\'});'
        + 'b.style.borderColor=\'#38BDF8\';b.style.color=\'#38BDF8\'})(this)"'
        + ' ' + scopeAttr
        + ' class="rounded-xl px-3 text-em-3xs font-bold"'
        + ' style="background:#0A1929;border:1px solid ' + border + ';color:' + color + ';height:28px">'
        + s + '×'
        + '</button>';
    }).join('');

    el.innerHTML = ''
      // 시크바
      + '<div class="flex items-center gap-2 px-1 mb-1">'
      + '<span id="' + timeId + '" class="text-em-3xs font-mono shrink-0" style="color:#475569;min-width:70px">0:00 / 0:00</span>'
      + '<input id="' + seekBarId + '" type="range" min="0" max="100" value="0" step="0.1"'
      + ' style="flex:1;height:4px;accent-color:#38BDF8;cursor:pointer;background:#1E3A5A;border-radius:4px"'
      + ' oninput="(function(s){var v=document.getElementById(\'' + videoId + '\');v.currentTime=v.duration*(s.value/100);})(this)">'
      + '</div>'
      // 버튼
      + '<div class="flex items-center justify-center gap-3">'
      + '<button'
      + ' onclick="(function(btn){var v=document.getElementById(\'' + videoId + '\');var icon=btn.querySelector(\'.material-icons-round\');if(v.paused){v.play();icon.textContent=\'pause\';}else{v.pause();icon.textContent=\'play_arrow\';}})(this)"'
      + ' class="flex items-center justify-center rounded-xl px-8 text-em-3xs font-bold"'
      + ' style="background:#0A1929;border:1px solid #1E3A5A;color:#E2E8F0;min-width:120px;height:28px">'
      + '<span class="material-icons-round" style="font-size:0.9em;line-height:1">pause</span>'
      + '</button>'
      + btnsHtml
      + '</div>';

    // 시크바 업데이트
    var video = document.getElementById(videoId);
    if (video) {
      video.addEventListener('timeupdate', function() {
        var bar = document.getElementById(seekBarId);
        var timeEl = document.getElementById(timeId);
        if (bar && video.duration) {
          bar.value = (video.currentTime / video.duration) * 100;
        }
        if (timeEl && video.duration) {
          var fmt = function(t) {
            var m = Math.floor(t / 60);
            var s = Math.floor(t % 60);
            return m + ':' + (s < 10 ? '0' : '') + s;
          };
          timeEl.textContent = fmt(video.currentTime) + ' / ' + fmt(video.duration);
        }
      });
    }
  });
}

// Boot
initPresentation();
