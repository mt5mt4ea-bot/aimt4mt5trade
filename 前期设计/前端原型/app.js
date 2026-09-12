(() => {
  const pad = n => String(n).padStart(2, '0');
  const updateClock = () => {
    const now = new Date();
    const text = `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
    document.querySelectorAll('[data-clock]').forEach(el => el.textContent = text);
  };
  updateClock();
  setInterval(updateClock, 1000);

  let latency = 118;
  setInterval(() => {
    latency = Math.max(84, Math.min(190, latency + Math.round((Math.random() - .5) * 18)));
    document.querySelectorAll('[data-latency]').forEach(el => el.textContent = `${latency} ms`);
  }, 2200);

  let expires = 18;
  setInterval(() => {
    expires = expires > 1 ? expires - 1 : 18;
    document.querySelectorAll('[data-expires]').forEach(el => el.textContent = `${expires}s`);
  }, 1000);

  const toast = document.querySelector('.toast');
  const notify = message => {
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add('show');
    clearTimeout(window.__toastTimer);
    window.__toastTimer = setTimeout(() => toast.classList.remove('show'), 2600);
  };

  document.querySelectorAll('[data-mode]').forEach(button => {
    button.addEventListener('click', () => {
      const requested = button.dataset.mode;
      document.querySelectorAll('[data-mode]').forEach(item => item.classList.remove('active'));
      button.classList.add('active');
      notify(requested === 'OBSERVE' ? '已切换为观察模式（原型演示）' : `${requested} 模式需要二次认证；原型未执行变更`);
    });
  });

  document.querySelectorAll('[data-action]').forEach(button => {
    button.addEventListener('click', () => {
      const label = button.textContent.trim();
      notify(`${label}：这是界面原型，未连接真实账户，也不会提交交易。`);
    });
  });
})();

