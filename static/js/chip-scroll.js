// 칩 줄이 가로 스크롤 상태(모바일)일 때 선택된 칩을 화면 가운데로 당긴다.
// scrollIntoView는 페이지 세로 스크롤까지 건드려서 scrollLeft를 직접 계산한다.
(function () {
  document.querySelectorAll(".cat-chips, .topic-chips").forEach(function (row) {
    var on = row.querySelector("a.on");
    if (!on || row.scrollWidth <= row.clientWidth) return;
    row.scrollLeft = Math.max(0, on.offsetLeft - (row.clientWidth - on.offsetWidth) / 2);
  });
})();
