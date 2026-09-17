'use strict';

/* ============================================================
   Persian RSVP Speed Reader — Page UI Application Logic
   
   Isolates page UI (Auth modals, Library modals, inputs, sliders,
   shortcuts) from the RSVP Player abstraction.
   ============================================================ */

import { RSVPPlayer } from './rsvp/player.js';

/* ---------------- Constants ---------------- */
const DEFAULT_WPM = 300;
const MIN_WPM     = 60;
const MAX_WPM     = 1200;
const WPM_STEP    = 10;
const TOKEN_KEY   = 'persian_rsvp_token';

const SAMPLE_TEXT =
  'تندخوانی روشی برای افزایش سرعت مطالعه و درک بهتر متن است. ' +
  'در روش RSVP، کلمات یکی پس از دیگری در یک نقطه ثابت نمایش داده می‌شوند ' +
  'تا حرکت چشم کاهش پیدا کند. هدف این سیستم فراهم آوردن تجربه‌ای روان ' +
  'برای مطالعه متون فارسی به همراه ذخیره‌سازی ابری و شخصی‌سازی تنظیمات است.';

/* ---------------- DOM Elements ---------------- */
const $ = (id) => document.getElementById(id);
const wordEl         = $('word');
const focusEl        = $('focus-area');
const progressTextEl = $('progress-text');
const wpmDisplayEl   = $('wpm-display');
const progressFillEl = $('progress-fill');
const inputEl        = $('input-text');
const wpmInputEl     = $('wpm');
const wpmSliderEl    = $('wpm-slider');
const startBtn       = $('btn-start');
const pauseBtn       = $('btn-pause');
const resetBtn       = $('btn-reset');
const fontSelectEl   = $('font-select');

// Commercialization (§12): server-authoritative quota surface
const usageBadgeEl      = $('usage-badge');
const btnUpgradeEl      = $('btn-upgrade');
const quotaBannerEl     = $('quota-banner');
const quotaBannerTextEl = $('quota-banner-text');
const btnBannerUpgrade  = $('btn-banner-upgrade');
const btnBannerClose    = $('btn-banner-close');

// Auth & Nav
const authGuestEl    = $('auth-guest');
const authMemberEl   = $('auth-member');
const userDisplayEl  = $('user-display');
const btnAuthOpen    = $('btn-auth-open');
const btnLogout      = $('btn-logout');
const modalAuth      = $('modal-auth');
const btnCloseAuth   = $('btn-close-auth');
const tabLogin       = $('tab-login');
const tabRegister    = $('tab-register');
const formLogin      = $('form-login');
const formRegister   = $('form-register');
const authAlert      = $('auth-alert');

// Library
const modalLibrary   = $('modal-library');
const btnLibraryOpen = $('btn-library-open');
const btnCloseLib    = $('btn-close-library');
const btnSaveText    = $('btn-save-text');
const libraryList    = $('library-list');

/* ---------------- State ---------------- */
let currentUser = null;
let currentWpm = DEFAULT_WPM;

function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

function setToken(token) {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
  } else {
    localStorage.removeItem(TOKEN_KEY);
  }
}

async function apiFetch(url, options = {}) {
  const token = getToken();
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {}),
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  return await fetch(url, { ...options, headers });
}

/* ---------------- RSVP Player Instance ---------------- */
const player = new RSVPPlayer({
  wordElement: wordEl,
  focusElement: focusEl,
  chunkSize: 150,
  prefetchThreshold: 45,
  getAuthToken: () => getToken(),
  onProgress: ({ index, total, pct }) => {
    progressTextEl.textContent = `${total > 0 ? index + 1 : 0} / ${total}`;
    progressFillEl.style.width = `${pct}%`;
  },
  onError: (err) => {
    // 429: quota exhausted (persistent banner + upgrade path) or rate limited
    // (transient notice). 401: expired session — clear it and prompt re-login.
    if (err && err.status === 429) {
      const detail = err.detail || 'محدودیت مصرف اعمال شده است.';
      const isQuota = typeof detail === 'string' && detail.includes('سقف');
      showQuotaBanner(detail, { canUpgrade: !!currentUser });
      if (!isQuota) {
        setTimeout(hideQuotaBanner, 8000); // rate-limit notice is transient
      }
    } else if (err && err.status === 401) {
      setToken(null);
      currentUser = null;
      updateAuthUI();
      showQuotaBanner('نشست شما منقضی شده است؛ لطفاً دوباره وارد شوید.', { canUpgrade: false });
      setTimeout(hideQuotaBanner, 6000);
    }
  },
  onStateChange: (state) => {
    if (state === 'running') {
      pauseBtn.textContent = 'Pause';
    } else if (state === 'paused') {
      pauseBtn.textContent = 'Resume';
    } else if (state === 'done') {
      pauseBtn.textContent = 'Pause';
    }
  },
  onFinish: async (lastIndex) => {
    if (player.currentTextId && currentUser) {
      try {
        await apiFetch(`/api/texts/${player.currentTextId}`, {
          method: 'PUT',
          body: JSON.stringify({
            last_position: lastIndex,
            wpm: currentWpm,
          }),
        });
      } catch (err) {
        console.error('Failed to sync finish position:', err);
      }
    }
  },
});

/* ---------------- UI Synchronization ---------------- */
function setWpm(v, syncWithServer = true) {
  v = Math.round(Number(v) || DEFAULT_WPM);
  currentWpm = Math.min(MAX_WPM, Math.max(MIN_WPM, v));
  player.setWpm(currentWpm);
  wpmInputEl.value = currentWpm;
  wpmSliderEl.value = currentWpm;
  wpmDisplayEl.textContent = `${currentWpm} WPM`;

  if (syncWithServer && currentUser) {
    syncPreferredWpm(currentWpm);
  }
}

let wpmSyncTimeout = null;
function syncPreferredWpm(wpm) {
  clearTimeout(wpmSyncTimeout);
  wpmSyncTimeout = setTimeout(async () => {
    try {
      await apiFetch('/api/auth/me', {
        method: 'PATCH',
        body: JSON.stringify({ preferred_wpm: wpm }),
      });
      if (currentUser) currentUser.preferred_wpm = wpm;
    } catch (e) {
      console.error('Failed to sync WPM with server:', e);
    }
  }, 1000);
}

function updateAuthUI() {
  if (currentUser) {
    authGuestEl.classList.add('hidden');
    authMemberEl.classList.remove('hidden');
    userDisplayEl.innerHTML = `<span>👤</span> <strong>${escapeHtml(currentUser.username)}</strong>`;
    usageBadgeEl.classList.remove('hidden');
    btnUpgradeEl.classList.toggle('hidden', currentUser.plan_tier !== 'free');
    refreshUsage();
  } else {
    authGuestEl.classList.remove('hidden');
    authMemberEl.classList.add('hidden');
    userDisplayEl.textContent = '';
    usageBadgeEl.classList.add('hidden');
    btnUpgradeEl.classList.add('hidden');
  }
}

/* ---------------- Quota & Usage surface (§12) ---------------- */
let lastUsage = null;           // last server-known usage snapshot
let usageFetchInFlight = false; // coalesce parallel callers
let usageFetchAt = 0;           // last completed fetch timestamp
const USAGE_FETCH_MIN_INTERVAL_MS = 30000; // throttles badge refresh

function formatUsageBadge(usage) {
  const pct = usage.quota_limit > 0 ? usage.tokens_used / usage.quota_limit : 0;
  const formatted = `${usage.tokens_used.toLocaleString('fa-IR')} / ${usage.quota_limit.toLocaleString('fa-IR')}`;
  usageBadgeEl.textContent = `⚡ ${formatted} توکن`;
  usageBadgeEl.classList.toggle('warn', pct >= 0.75 && pct < 1);
  usageBadgeEl.classList.toggle('exhausted', pct >= 1);
}

async function refreshUsage(force = false) {
  if (!currentUser) return;
  if (usageFetchInFlight) return;
  if (!force && Date.now() - usageFetchAt < USAGE_FETCH_MIN_INTERVAL_MS) return;

  usageFetchInFlight = true;
  try {
    const res = await apiFetch('/api/account/usage');
    if (res.ok) {
      lastUsage = await res.json();
      usageFetchAt = Date.now();
      formatUsageBadge(lastUsage);
    } else if (res.status === 401) {
      setToken(null);
      currentUser = null;
      updateAuthUI();
    }
  } catch (err) {
    console.error('Failed to fetch usage:', err);
  } finally {
    usageFetchInFlight = false;
  }
}

function showQuotaBanner(message, { canUpgrade = false } = {}) {
  quotaBannerTextEl.textContent = message;
  btnBannerUpgrade.classList.toggle('hidden', !canUpgrade);
  quotaBannerEl.classList.remove('hidden');
}

function hideQuotaBanner() {
  quotaBannerEl.classList.add('hidden');
}

async function upgradeSubscription() {
  if (!currentUser) return;
  btnUpgradeEl.disabled = true;
  if (btnBannerUpgrade) btnBannerUpgrade.disabled = true;
  try {
    const res = await apiFetch('/api/account/subscription', {
      method: 'PATCH',
      body: JSON.stringify({ plan_tier: 'paid' }),
    });
    if (res.ok) {
      currentUser = await res.json();
      updateAuthUI();
      hideQuotaBanner();
      await refreshUsage(true);
    } else {
      const data = await res.json().catch(() => ({}));
      showQuotaBanner(data.detail || 'ارتقای اشتراک ناموفق بود.', { canUpgrade: false });
    }
  } catch (err) {
    showQuotaBanner('برقراری ارتباط با سرور ممکن نشد.', { canUpgrade: false });
  } finally {
    btnUpgradeEl.disabled = false;
    if (btnBannerUpgrade) btnBannerUpgrade.disabled = false;
  }
}

btnUpgradeEl.addEventListener('click', upgradeSubscription);
if (btnBannerUpgrade) btnBannerUpgrade.addEventListener('click', upgradeSubscription);
btnBannerClose.addEventListener('click', hideQuotaBanner);

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

async function checkAuth() {
  const token = getToken();
  if (!token) {
    updateAuthUI();
    return;
  }
  try {
    const res = await apiFetch('/api/auth/me');
    if (res.ok) {
      currentUser = await res.json();
      if (currentUser.preferred_wpm) {
        setWpm(currentUser.preferred_wpm, false);
      }
    } else {
      setToken(null);
      currentUser = null;
    }
  } catch (err) {
    console.error('Failed to check auth status:', err);
  } finally {
    updateAuthUI();
  }
}

/* ---------------- Event Listeners ---------------- */
startBtn.addEventListener('click', async () => {
  startBtn.blur();
  const text = inputEl.value.trim();
  if (text !== player.currentText) {
    await player.loadPlan(text, null);
  }
  player.start();
  refreshUsage(); // throttled; keeps the usage badge current during reading
});

pauseBtn.addEventListener('click', () => {
  pauseBtn.blur();
  if (player.state === 'running') {
    player.pause();
  } else if (player.state === 'paused') {
    player.resume();
  }
});

resetBtn.addEventListener('click', () => {
  resetBtn.blur();
  player.reset();
});

wpmInputEl.addEventListener('input', () => setWpm(wpmInputEl.value));
wpmSliderEl.addEventListener('input', () => setWpm(wpmSliderEl.value));
if (fontSelectEl) {
  fontSelectEl.addEventListener('change', () => {
    player.setFontFamily(fontSelectEl.value);
  });
}

window.addEventListener('keydown', (e) => {
  const t = e.target;
  if (t && (t.tagName === 'TEXTAREA' || t.tagName === 'INPUT')) return;
  if (!modalAuth.classList.contains('hidden') || !modalLibrary.classList.contains('hidden')) {
    if (e.key === 'Escape') closeModals();
    return;
  }

  switch (e.code) {
    case 'Space':
      e.preventDefault();
      if (player.state === 'running') {
        player.pause();
      } else if (player.state === 'paused') {
        player.resume();
      } else if (player.state === 'idle') {
        startBtn.click();
      }
      break;
    case 'ArrowUp':
      e.preventDefault();
      setWpm(currentWpm + WPM_STEP);
      break;
    case 'ArrowDown':
      e.preventDefault();
      setWpm(currentWpm - WPM_STEP);
      break;
    case 'KeyR':
      player.reset();
      break;
  }
});

/* ---------------- Modals & Auth Handlers ---------------- */
function closeModals() {
  modalAuth.classList.add('hidden');
  modalLibrary.classList.add('hidden');
  clearAuthAlert();
}

function showAuthAlert(msg, type = 'error') {
  authAlert.textContent = msg;
  authAlert.className = `alert alert-${type}`;
  authAlert.classList.remove('hidden');
}

function clearAuthAlert() {
  authAlert.textContent = '';
  authAlert.classList.add('hidden');
}

btnAuthOpen.addEventListener('click', () => {
  clearAuthAlert();
  modalAuth.classList.remove('hidden');
  $('login-username').focus();
});

btnCloseAuth.addEventListener('click', closeModals);
btnCloseLib.addEventListener('click', closeModals);

modalAuth.addEventListener('click', (e) => { if (e.target === modalAuth) closeModals(); });
modalLibrary.addEventListener('click', (e) => { if (e.target === modalLibrary) closeModals(); });

tabLogin.addEventListener('click', () => {
  tabLogin.classList.add('active');
  tabRegister.classList.remove('active');
  formLogin.classList.remove('hidden');
  formRegister.classList.add('hidden');
  clearAuthAlert();
});

tabRegister.addEventListener('click', () => {
  tabRegister.classList.add('active');
  tabLogin.classList.remove('active');
  formRegister.classList.remove('hidden');
  formLogin.classList.add('hidden');
  clearAuthAlert();
});

formLogin.addEventListener('submit', async (e) => {
  e.preventDefault();
  clearAuthAlert();
  const username = $('login-username').value.trim();
  const password = $('login-password').value;

  try {
    const res = await apiFetch('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    });
    const data = await res.json();
    if (!res.ok) {
      showAuthAlert(data.detail || 'خطا در ورود به حساب کاربری.');
      return;
    }

    setToken(data.access_token);
    currentUser = data.user;
    if (currentUser.preferred_wpm) {
      setWpm(currentUser.preferred_wpm, false);
    }
    updateAuthUI();
    closeModals();
    formLogin.reset();
  } catch (err) {
    showAuthAlert('برقراری ارتباط با سرور ناموفق بود.');
  }
});

formRegister.addEventListener('submit', async (e) => {
  e.preventDefault();
  clearAuthAlert();
  const username = $('reg-username').value.trim();
  const email = $('reg-email').value.trim() || null;
  const password = $('reg-password').value;

  try {
    const res = await apiFetch('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ username, email, password }),
    });
    const data = await res.json();
    if (!res.ok) {
      showAuthAlert(data.detail || 'خطا در ثبت‌نام.');
      return;
    }

    setToken(data.access_token);
    currentUser = data.user;
    updateAuthUI();
    closeModals();
    formRegister.reset();
  } catch (err) {
    showAuthAlert('برقراری ارتباط با سرور ناموفق بود.');
  }
});

btnLogout.addEventListener('click', () => {
  setToken(null);
  currentUser = null;
  player.currentTextId = null;
  lastUsage = null;
  usageFetchAt = 0;
  hideQuotaBanner();
  updateAuthUI();
});

/* ---------------- Saved Texts / Library ---------------- */
btnLibraryOpen.addEventListener('click', async () => {
  modalLibrary.classList.remove('hidden');
  await loadLibrary();
});

async function loadLibrary() {
  libraryList.innerHTML = '<div class="library-empty">در حال دریافت متون...</div>';
  try {
    const res = await apiFetch('/api/texts');
    if (!res.ok) {
      libraryList.innerHTML = '<div class="library-empty">خطا در دریافت لیست متن‌ها.</div>';
      return;
    }
    const texts = await res.json();
    if (texts.length === 0) {
      libraryList.innerHTML = '<div class="library-empty">هنوز متنی ذخیره نکرده‌اید. با زدن دکمه «ذخیره متن» متن فعلی را ذخیره کنید.</div>';
      return;
    }

    libraryList.innerHTML = '';
    texts.forEach((item) => {
      const el = document.createElement('div');
      el.className = 'library-item';
      const approxCount = item.content.trim().split(/\s+/).length;
      el.innerHTML = `
        <div class="library-info">
          <div class="library-item-title">${escapeHtml(item.title)}</div>
          <div class="library-item-meta">
            <span>تعداد کلمات تقریبی: ${approxCount}</span>
            <span>سرعت: ${item.wpm} WPM</span>
            <span>پیشرفت: کلمه ${item.last_position}</span>
          </div>
        </div>
        <div class="library-actions">
          <button class="btn-nav btn-read" data-id="${item.id}">خواندن</button>
          <button class="btn-nav btn-danger btn-del" data-id="${item.id}">حذف</button>
        </div>
      `;

      el.querySelector('.btn-read').addEventListener('click', async () => {
        if (item.wpm) setWpm(item.wpm, false);
        inputEl.value = item.content;
        closeModals();
        await player.loadPlan(item.content, item.id, item.last_position || 0);
        refreshUsage();
      });

      el.querySelector('.btn-del').addEventListener('click', async () => {
        if (!confirm(`آیا از حذف متن «${item.title}» مطمئن هستید؟`)) return;
        try {
          const dRes = await apiFetch(`/api/texts/${item.id}`, { method: 'DELETE' });
          if (dRes.ok) {
            if (player.currentTextId === item.id) player.currentTextId = null;
            await loadLibrary();
          }
        } catch (e) {
          alert('خطا در حذف متن');
        }
      });

      libraryList.appendChild(el);
    });
  } catch (err) {
    libraryList.innerHTML = '<div class="library-empty">خطا در بارگذاری کتابخانه.</div>';
  }
}

btnSaveText.addEventListener('click', async () => {
  const content = inputEl.value.trim();
  if (!content) {
    alert('ابتدا متنی در کادر وارد کنید.');
    return;
  }

  const firstWords = content.split(/\s+/).slice(0, 5).join(' ');
  const defaultTitle = firstWords.length > 30 ? firstWords.slice(0, 30) + '...' : firstWords;
  const title = prompt('عنوان متن را وارد کنید:', defaultTitle || 'متن جدید');
  if (!title) return;

  try {
    const res = await apiFetch('/api/texts', {
      method: 'POST',
      body: JSON.stringify({
        title,
        content,
        wpm: currentWpm,
      }),
    });
    if (res.ok) {
      const saved = await res.json();
      player.currentTextId = saved.id;
      alert('متن با موفقیت در کتابخانه شما ذخیره شد!');
    } else {
      const err = await res.json();
      alert(err.detail || 'خطا در ذخیره متن.');
    }
  } catch (e) {
    alert('برقراری ارتباط با سرور ممکن نشد.');
  }
});

/* ---------------- Initialization ---------------- */
setWpm(DEFAULT_WPM, false);
checkAuth();
inputEl.value = SAMPLE_TEXT;
player.loadPlan(SAMPLE_TEXT, null);
