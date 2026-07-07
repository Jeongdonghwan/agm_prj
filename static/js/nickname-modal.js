// 닉네임 설정 모달 — 실시간 중복 확인 + 설정 완료 후 작성 이어서 진행
(function () {
  const bg = document.getElementById('nick-modal');
  if (!bg) return;
  const input = document.getElementById('nick-input');
  const msg = document.getElementById('nick-msg');
  const save = document.getElementById('nick-save');
  let timer = null;

  window.openNicknameModal = () => { bg.classList.add('on'); input.focus(); };
  document.getElementById('nick-close').addEventListener('click', () => bg.classList.remove('on'));

  input.addEventListener('input', () => {
    save.disabled = true;
    msg.className = 'check-msg';
    msg.textContent = '';
    clearTimeout(timer);
    const value = input.value.trim();
    if (!value) return;
    timer = setTimeout(async () => {
      const res = await fetch(`/api/me/nickname/check?value=${encodeURIComponent(value)}`);
      const data = await res.json();
      msg.className = 'check-msg ' + (data.available ? 'ok' : 'bad');
      msg.textContent = data.available ? '사용 가능한 닉네임입니다.' : data.reason;
      save.disabled = !data.available;
    }, 300);
  });

  save.addEventListener('click', async () => {
    const res = await fetch('/api/me/nickname', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ value: input.value.trim() }),
    });
    const data = await res.json();
    if (res.ok) {
      bg.classList.remove('on');
      // 작성 이어서 진행: 대기 중인 폼이 있으면 제출
      if (window.nicknamePendingForm) window.nicknamePendingForm.submit();
      else location.reload();
    } else {
      msg.className = 'check-msg bad';
      msg.textContent = data.error ? data.error.message : '설정에 실패했습니다.';
    }
  });

  // data-need-nickname 폼: 닉네임 없으면 모달부터
  document.querySelectorAll('form[data-need-nickname="1"]').forEach(form => {
    form.addEventListener('submit', e => {
      e.preventDefault();
      window.nicknamePendingForm = form;
      window.openNicknameModal();
    });
  });
})();
