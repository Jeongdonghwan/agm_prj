// 롤링 배너 공용 헬퍼 — 랜덤 시작 + 주기 페이드 전환
function initRolling(slideSelector, curId, intervalMs) {
  const slides = document.querySelectorAll(slideSelector);
  const cur = document.getElementById(curId);
  if (!slides.length) return;
  let i = Math.floor(Math.random() * slides.length); // 접속마다 랜덤 시작
  slides.forEach((s, idx) => s.classList.toggle('on', idx === i));
  if (cur) cur.textContent = i + 1;
  if (slides.length < 2) return;
  setInterval(() => {
    slides[i].classList.remove('on');
    i = (i + 1) % slides.length;
    slides[i].classList.add('on');
    if (cur) cur.textContent = i + 1;
  }, intervalMs);
}
initRolling('#hero-banner .hero-slide', 'hero-cur', 4000);   // 좌측 히어로
initRolling('#side-banner .side-slide', 'side-cur', 4500);   // 우측 EVENT (B안)

// 통합 콘텐츠 탭 전환 (시안 index.html 스크립트 분리)
document.querySelectorAll('.hub-tabs button').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.hub-tabs button').forEach(b => b.classList.remove('on'));
    document.querySelectorAll('.hub-panel').forEach(p => p.classList.remove('on'));
    btn.classList.add('on');
    document.getElementById(btn.dataset.tab).classList.add('on');
  });
});
