// 전화/카톡 클릭 수 기록 — 링크 이동은 그대로 진행 (sendBeacon)
document.querySelectorAll('.contact-click').forEach(el => {
  el.addEventListener('click', () => {
    const payload = JSON.stringify({ type: el.dataset.type });
    const url = `/api/lawyers/${el.dataset.id}/contact-click`;
    if (navigator.sendBeacon) {
      navigator.sendBeacon(url, new Blob([payload], { type: 'application/json' }));
    } else {
      fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: payload, keepalive: true });
    }
  });
});
