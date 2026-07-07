// 히어로 롤링 배너 — 4초 간격 페이드 전환
(function () {
  const slides = document.querySelectorAll('#hero-banner .hero-slide');
  const cur = document.getElementById('hero-cur');
  if (slides.length < 2) return;
  let i = 0;
  setInterval(() => {
    slides[i].classList.remove('on');
    i = (i + 1) % slides.length;
    slides[i].classList.add('on');
    if (cur) cur.textContent = i + 1;
  }, 4000);
})();

// 통합 콘텐츠 탭 전환 (시안 index.html 스크립트 분리)
document.querySelectorAll('.hub-tabs button').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.hub-tabs button').forEach(b => b.classList.remove('on'));
    document.querySelectorAll('.hub-panel').forEach(p => p.classList.remove('on'));
    btn.classList.add('on');
    document.getElementById(btn.dataset.tab).classList.add('on');
  });
});
