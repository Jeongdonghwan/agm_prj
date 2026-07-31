// 휴대폰 번호 자동 하이픈 — name="phone"인 tel 입력에 적용 (01X 형식)
(function () {
  function format(digits) {
    if (!/^01/.test(digits)) return digits; // 휴대폰 형식만 처리
    if (digits.length <= 3) return digits;
    if (digits.length <= 7) return digits.slice(0, 3) + '-' + digits.slice(3);
    if (digits.length <= 10) return digits.slice(0, 3) + '-' + digits.slice(3, 6) + '-' + digits.slice(6);
    return digits.slice(0, 3) + '-' + digits.slice(3, 7) + '-' + digits.slice(7, 11);
  }
  document.querySelectorAll('input[type=tel][name=phone]').forEach(input => {
    input.addEventListener('input', () => {
      const digits = input.value.replace(/\D/g, '');
      const next = format(digits);
      if (input.value !== next) input.value = next;
    });
  });
})();
