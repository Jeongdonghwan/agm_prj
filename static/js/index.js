// 배너 공용 헬퍼 — 접속마다 랜덤 배너 선택, 컨테이너에 data-static="1"이면
// 슬라이딩 없이 랜덤 1장 고정, 아니면 주기 페이드 롤링
function initRolling(containerSel, slideClass, curId, intervalMs) {
  const container = document.querySelector(containerSel);
  if (!container) return;
  const slides = container.querySelectorAll(slideClass);
  const cur = document.getElementById(curId);
  if (!slides.length) return;
  let i = Math.floor(Math.random() * slides.length); // 페이지 진입마다 랜덤
  slides.forEach((s, idx) => s.classList.toggle('on', idx === i));
  if (cur) cur.textContent = i + 1;
  if (slides.length < 2 || container.dataset.static === '1') return;
  setInterval(() => {
    slides[i].classList.remove('on');
    i = (i + 1) % slides.length;
    slides[i].classList.add('on');
    if (cur) cur.textContent = i + 1;
  }, intervalMs);
}
initRolling('#hero-banner', '.hero-slide', 'hero-cur', 4000); // 히어로 (B안은 data-static 랜덤 고정)
initRolling('#side-banner', '.side-slide', 'side-cur', 4500); // 우측 EVENT 롤링 (B안)

// 가로 슬라이더 — 화살표 스크롤 + 끝단 버튼 비활성
document.querySelectorAll('.hs-wrap').forEach(wrap => {
  const track = wrap.querySelector('.hscroll');
  const prev = wrap.querySelector('.hs-prev');
  const next = wrap.querySelector('.hs-next');
  if (!track || !prev || !next) return;
  const step = () => Math.max(track.clientWidth * 0.8, 220);
  function update() {
    prev.disabled = track.scrollLeft <= 4;
    next.disabled = track.scrollLeft >= track.scrollWidth - track.clientWidth - 4;
  }
  prev.addEventListener('click', () => track.scrollBy({ left: -step(), behavior: 'smooth' }));
  next.addEventListener('click', () => track.scrollBy({ left: step(), behavior: 'smooth' }));
  track.addEventListener('scroll', update, { passive: true });
  window.addEventListener('resize', update);
  update();
});

// 통합 파인더 — 분야로/지역으로 찾기 패널 전환
document.querySelectorAll('.finder-tabs button').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.finder-tabs button').forEach(b => b.classList.remove('on'));
    document.querySelectorAll('.finder-panel').forEach(p => p.classList.remove('on'));
    btn.classList.add('on');
    document.getElementById(btn.dataset.panel).classList.add('on');
  });
});

// 통합 콘텐츠 탭 전환 (시안 index.html 스크립트 분리)
document.querySelectorAll('.hub-tabs button').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.hub-tabs button').forEach(b => b.classList.remove('on'));
    document.querySelectorAll('.hub-panel').forEach(p => p.classList.remove('on'));
    btn.classList.add('on');
    document.getElementById(btn.dataset.tab).classList.add('on');
  });
});
