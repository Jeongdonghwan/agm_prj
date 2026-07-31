// 커뮤니티 본문 간이 에디터 — contenteditable + 이미지 즉시 업로드 삽입.
// 저장 형식: 순수 텍스트 + [img]/uploads/community/…[/img] 토큰 (hidden input에 직렬화)
(function () {
  const editor = document.getElementById('body-editor');
  const hidden = document.getElementById('body-hidden');
  const photoBtn = document.getElementById('btn-add-photo');
  const photoInput = document.getElementById('editor-img-input');
  if (!editor || !hidden) return;
  const uploadUrl = editor.dataset.uploadUrl;

  // ── 토큰 텍스트 → 에디터 HTML (초기 로드: 수정 모드/재렌더) ──
  function esc(s) {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }
  function toHtml(text) {
    return esc(text)
      .replace(/\[img\](\/uploads\/community\/[\w/.\-]+)\[\/img\]/g,
        '<img src="$1" alt="">')
      .replace(/\n/g, '<br>');
  }

  // ── 에디터 DOM → 토큰 텍스트 ──
  function serialize(node) {
    let out = '';
    node.childNodes.forEach(ch => {
      if (ch.nodeType === Node.TEXT_NODE) {
        out += ch.textContent;
      } else if (ch.nodeName === 'IMG') {
        const src = ch.getAttribute('src') || '';
        out += '\n[img]' + src + '[/img]\n';
      } else if (ch.nodeName === 'BR') {
        out += '\n';
      } else if (ch.nodeType === Node.ELEMENT_NODE) {
        const inner = serialize(ch);
        // div/p 블록은 줄바꿈으로
        out += (/^(DIV|P)$/.test(ch.nodeName) && out && !out.endsWith('\n') ? '\n' : '') + inner;
        if (/^(DIV|P)$/.test(ch.nodeName) && !inner.endsWith('\n')) out += '\n';
      }
    });
    return out;
  }
  function sync() {
    hidden.value = serialize(editor).replace(/\n{3,}/g, '\n\n').trim();
  }

  // 초기값 복원 (hidden에 토큰 텍스트가 들어있음)
  if (hidden.value.trim()) editor.innerHTML = toHtml(hidden.value);

  // 입력 시마다 동기화 — 닉네임 모달의 form.submit()(네이티브)이 submit 리스너를
  // 우회하므로 항상 최신 상태를 유지해야 한다
  editor.addEventListener('input', sync);
  sync();

  // 붙여넣기는 서식 제거 후 텍스트만
  editor.addEventListener('paste', e => {
    e.preventDefault();
    const text = (e.clipboardData || window.clipboardData).getData('text/plain');
    document.execCommand('insertText', false, text);
  });

  // ── 사진 삽입 ──
  let savedRange = null;
  editor.addEventListener('blur', () => {
    const sel = window.getSelection();
    if (sel.rangeCount && editor.contains(sel.anchorNode)) savedRange = sel.getRangeAt(0).cloneRange();
  });

  function insertImage(url) {
    const img = document.createElement('img');
    img.src = url;
    img.alt = '';
    editor.focus();
    const sel = window.getSelection();
    if (savedRange) {
      sel.removeAllRanges();
      sel.addRange(savedRange);
    }
    if (sel.rangeCount && editor.contains(sel.anchorNode)) {
      const range = sel.getRangeAt(0);
      range.deleteContents();
      range.insertNode(img);
      range.setStartAfter(img);
      range.collapse(true);
      sel.removeAllRanges();
      sel.addRange(range);
    } else {
      editor.appendChild(img);
    }
    savedRange = null;
    sync();
  }

  if (photoBtn && photoInput) {
    photoBtn.addEventListener('click', () => photoInput.click());
    photoInput.addEventListener('change', async () => {
      const f = photoInput.files[0];
      photoInput.value = '';
      if (!f) return;
      photoBtn.disabled = true;
      try {
        const fd = new FormData();
        fd.append('image', f);
        const res = await fetch(uploadUrl, { method: 'POST', body: fd });
        const data = await res.json().catch(() => null);
        if (res.ok && data && data.url) insertImage(data.url);
        else alert((data && data.error && data.error.message) || '이미지 업로드에 실패했습니다.');
      } finally {
        photoBtn.disabled = false;
      }
    });
  }

  // 제출 검증 — 내용 비어있으면 차단
  const form = editor.closest('form');
  if (form) {
    form.addEventListener('submit', e => {
      sync();
      if (!hidden.value.trim()) {
        e.preventDefault();
        alert('내용을 입력해주세요.');
        editor.focus();
      }
    });
  }
})();
