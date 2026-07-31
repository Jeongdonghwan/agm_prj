// 파일첨부 공용 컴포넌트 — .filebox 안의 input[type=file]을 미리보기 UI로 감싼다.
// data-max: 최대 개수(다중일 때), data-label: 버튼 문구
(function () {
  const CLIP = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>';

  document.querySelectorAll('.filebox').forEach(box => {
    const input = box.querySelector('input[type=file]');
    if (!input) return;
    const multiple = input.multiple;
    const max = parseInt(box.dataset.max || '0', 10) || (multiple ? 10 : 1);
    const label = box.dataset.label || (multiple ? '파일 선택 — 클릭해서 추가' : '파일 선택');

    input.classList.add('fb-native'); // display:none이면 required 검증이 막히므로 시각적 숨김만
    const trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.className = 'fb-trigger';
    trigger.innerHTML = CLIP + '<span>' + label + '</span>';
    const list = document.createElement('div');
    list.className = 'fb-list';
    box.appendChild(trigger);
    box.appendChild(list);

    let files = [];
    trigger.addEventListener('click', () => input.click());

    input.addEventListener('change', () => {
      const picked = Array.from(input.files);
      if (!multiple) {
        files = picked.slice(0, 1);
      } else {
        for (const f of picked) {
          if (files.some(x => x.name === f.name && x.size === f.size)) continue;
          if (files.length >= max) { alert('최대 ' + max + '개까지 첨부할 수 있습니다.'); break; }
          files.push(f);
        }
      }
      sync();
    });

    function sync() {
      const dt = new DataTransfer();
      files.forEach(f => dt.items.add(f));
      input.files = dt.files;
      render();
    }

    function render() {
      list.innerHTML = '';
      files.forEach((f, i) => {
        const isImg = /^image\//.test(f.type);
        const item = document.createElement('div');
        item.className = 'fb-item ' + (isImg ? 'img' : 'doc');
        if (isImg) {
          const img = document.createElement('img');
          img.src = URL.createObjectURL(f);
          img.onload = () => URL.revokeObjectURL(img.src);
          item.appendChild(img);
        } else {
          const ext = (f.name.split('.').pop() || '').toUpperCase().slice(0, 5);
          const b = document.createElement('span'); b.className = 'ext'; b.textContent = ext;
          const nm = document.createElement('span'); nm.className = 'nm'; nm.textContent = f.name;
          item.appendChild(b); item.appendChild(nm);
        }
        const x = document.createElement('button');
        x.type = 'button'; x.className = 'fb-x'; x.textContent = '×'; x.title = '제거';
        x.addEventListener('click', () => { files.splice(i, 1); sync(); });
        item.appendChild(x);
        list.appendChild(item);
      });
    }
  });
})();
