// 통합 콘텐츠 탭 전환 (시안 index.html 스크립트 분리)
document.querySelectorAll('.hub-tabs button').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.hub-tabs button').forEach(b => b.classList.remove('on'));
    document.querySelectorAll('.hub-panel').forEach(p => p.classList.remove('on'));
    btn.classList.add('on');
    document.getElementById(btn.dataset.tab).classList.add('on');
  });
});
