/* MSR Mini App
   - Works inside Telegram WebApp
   - User mode: check answers once and get deeplinks
   - Admin mode: enter correct answers and baseline (Rasch)
*/

const $ = (id) => document.getElementById(id);

const qs = new URLSearchParams(window.location.search);
const MODE = (qs.get('mode') || 'user').toLowerCase();
const FIXED_TEST_ID = qs.get('test_id') ? parseInt(qs.get('test_id'), 10) : null;

const state = {
  role: 'user',
  roles: ['user'],
  categories: [],
  tests: [],
  selectedCategory: null,
  selectedTest: null,
  answers: {}, // {q: {choices: string[], manual: string[]}}
  q: 1,
  total: 0,
  adminTab: 'answers', // 'answers' | 'baseline'
  baselineIndex: 1,
  baselineDone: [],
  gate: { required: false, message: '', channel_url: '', group_url: '' },
};

function emptyAnswer() {
  return { choices: [], manual: [] };
}

function hasAnyAnswer(a) {
  if (!a) return false;
  return (Array.isArray(a.choices) && a.choices.length) || (Array.isArray(a.manual) && a.manual.some((x) => (x || '').trim() !== ''));
}

function normalizeAnswerObj(a) {
  const letters = ['A','B','C','D','E','F'];
  const c = Array.isArray(a?.choices) ? a.choices.map((x) => String(x || '').toUpperCase()).filter((x) => letters.includes(x)) : [];
  const uniqC = [...new Set(c)].sort();
  const mRaw = Array.isArray(a?.manual) ? a.manual.map((x) => String(x || '').trim()).filter((x) => x !== '') : [];
  const uniqM = [...new Set(mRaw)];
  return { choices: uniqC, manual: uniqM };
}

function tg() {
  return window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
}

function getInitData() {
  const t = tg();
  if (!t) return '';
  return t.initData || '';
}

function applyTheme(theme) {
  const root = document.documentElement;
  if (theme === 'light') root.setAttribute('data-theme', 'light');
  else root.removeAttribute('data-theme');
  localStorage.setItem('msr_theme', theme);
}

function toggleTheme() {
  const current = localStorage.getItem('msr_theme') || 'dark';
  applyTheme(current === 'dark' ? 'light' : 'dark');
}

function openLink(url) {
  const t = tg();
  if (t && typeof t.openTelegramLink === 'function') {
    t.openTelegramLink(url);
    return;
  }
  window.location.href = url;
}

async function apiGet(path) {
  const initData = getInitData();
  const res = await fetch(path, {
    method: 'GET',
    headers: initData ? { 'X-Telegram-Init-Data': initData } : {},
    credentials: 'same-origin',
  });
  return res;
}

async function apiPost(path, body) {
  const initData = getInitData();
  const res = await fetch(path, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(initData ? { 'X-Telegram-Init-Data': initData } : {}),
    },
    body: JSON.stringify(body || {}),
    credentials: 'same-origin',
  });
  return res;
}

function showGate(required, msg, chUrl, grUrl) {
  state.gate = { required, message: msg || '', channel_url: chUrl || '', group_url: grUrl || '' };
  $('screenGate').hidden = !required;
  $('screenMain').hidden = required;
  if (!required) return;
  $('gateMsg').textContent = msg || "Mini App’dan foydalanish uchun obuna bo‘lish shart.";
  $('gateChannel').href = chUrl || '#';
  $('gateGroup').href = grUrl || '#';
}

function setSubtitle(text) {
  $('subtitle').textContent = text;
}

function setStatus(text) {
  $('pillStatus').textContent = text;
}

function isAdminUI() {
  const r = Array.isArray(state.roles) ? state.roles : [state.role];
  return MODE === 'admin' && (r.includes('admin') || r.includes('ceo'));
}

function setSolveVisible(visible) {
  $('screenSolve').hidden = !visible;
  $('testsList').hidden = visible;
  $('result').hidden = true;
}

function resetAnswersForTest(test) {
  state.answers = {};
  state.q = 1;
  state.total = test ? test.num_questions : 0;
  for (let i = 1; i <= state.total; i++) state.answers[i] = emptyAnswer();
  updateProgress();
  renderNav();
  renderChoices();
}

function updateProgress() {
  const total = state.total || 0;
  const done = Object.values(state.answers).filter((v) => hasAnyAnswer(v)).length;
  const pct = total ? Math.round((done / total) * 100) : 0;
  $('bar').style.width = `${pct}%`;
  $('progressText').textContent = `${done} / ${total}`;
}

function renderNav() {
  const wrap = $('qnav');
  wrap.innerHTML = '';
  const total = state.total || 0;
  for (let i = 1; i <= total; i++) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'qbtn' + (state.q === i ? ' active' : '') + (hasAnyAnswer(state.answers[i]) ? ' done' : '');
    b.textContent = String(i);
    b.onclick = () => { state.q = i; renderNav(); renderChoices(); };
    wrap.appendChild(b);
  }
}

function renderChoices() {
  $('qnum').textContent = String(state.q);
  const wrap = $('choices');
  wrap.innerHTML = '';

  const current = normalizeAnswerObj(state.answers[state.q] || emptyAnswer());
  state.answers[state.q] = current;

  const letters = ['A','B','C','D','E','F'];
  const row = document.createElement('div');
  row.className = 'choicesRow';

  letters.forEach((ch) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    const active = current.choices.includes(ch);
    btn.className = 'choice' + (active ? ' active' : '');
    btn.textContent = ch;
    btn.onclick = () => {
      const set = new Set(current.choices);
      if (set.has(ch)) set.delete(ch); else set.add(ch);
      current.choices = [...set].sort();
      state.answers[state.q] = current;
      renderChoices();
      renderNav();
      updateProgress();
    };
    row.appendChild(btn);
  });

  const clearBtn = document.createElement('button');
  clearBtn.type = 'button';
  clearBtn.className = 'choice empty' + (!hasAnyAnswer(current) ? ' active' : '');
  clearBtn.textContent = '—';
  clearBtn.onclick = () => {
    state.answers[state.q] = emptyAnswer();
    renderChoices();
    renderNav();
    updateProgress();
  };
  row.appendChild(clearBtn);
  wrap.appendChild(row);

  // manual answers (multiple)
  const manualBox = document.createElement('div');
  manualBox.className = 'manualBox';

  const label = document.createElement('div');
  label.className = 'muted small';
  label.textContent = '✍ Manual javob(lar):';
  manualBox.appendChild(label);

  const list = document.createElement('div');
  list.className = 'manualList';
  (current.manual || []).forEach((val, idx) => {
    const chip = document.createElement('div');
    chip.className = 'mchip';
    const txt = document.createElement('div');
    txt.className = 'mtext';
    txt.textContent = val;
    const x = document.createElement('button');
    x.type = 'button';
    x.className = 'mx';
    x.textContent = '✕';
    x.onclick = () => {
      const next = current.manual.filter((_, i) => i !== idx);
      current.manual = next;
      state.answers[state.q] = normalizeAnswerObj(current);
      renderChoices();
      renderNav();
      updateProgress();
    };
    chip.appendChild(txt);
    chip.appendChild(x);
    list.appendChild(chip);
  });
  manualBox.appendChild(list);

  const addRow = document.createElement('div');
  addRow.className = 'manualAdd';
  const inp = document.createElement('input');
  inp.type = 'text';
  inp.maxLength = 128;
  inp.placeholder = 'masalan: 2**2, sqrt(16), 4x+3 ...';
  const add = document.createElement('button');
  add.type = 'button';
  add.className = 'ghost dots';
  add.textContent = '...';
  const doAdd = () => {
    const v = (inp.value || '').trim();
    if (!v) return;
    current.manual = [...(current.manual || []), v];
    inp.value = '';
    state.answers[state.q] = normalizeAnswerObj(current);
    renderChoices();
    renderNav();
    updateProgress();
  };
  add.onclick = doAdd;
  inp.onkeydown = (e) => {
    if (e.key === 'Enter') { e.preventDefault(); doAdd(); }
  };
  addRow.appendChild(inp);
  addRow.appendChild(add);
  manualBox.appendChild(addRow);

  wrap.appendChild(manualBox);
}

function goPrev() {
  if (state.q > 1) state.q -= 1;
  renderNav();
  renderChoices();
}

function goNext() {
  if (state.q < state.total) state.q += 1;
  renderNav();
  renderChoices();
}

function mountAdminToolbar() {
  // Inject admin toolbar into solveMeta area
  const meta = $('solveMeta');
  const exists = document.getElementById('adminToolbar');
  if (exists) exists.remove();
  if (!isAdminUI()) return;

  const box = document.createElement('div');
  box.id = 'adminToolbar';
  box.className = 'adminToolbar';

  const tabs = document.createElement('div');
  tabs.className = 'adminTabs';

  const tabAnswers = document.createElement('button');
  tabAnswers.type = 'button';
  tabAnswers.className = 'ghost';
  tabAnswers.textContent = '✅ To‘g‘ri javoblar';
  tabAnswers.onclick = async () => {
    state.adminTab = 'answers';
    await refreshBaselineStatus();
    renderAdminHints();
  };

  const tabBaseline = document.createElement('button');
  tabBaseline.type = 'button';
  tabBaseline.className = 'ghost';
  tabBaseline.textContent = '🧪 Baseline (10 ta)';
  tabBaseline.onclick = async () => {
    state.adminTab = 'baseline';
    await refreshBaselineStatus();
    renderAdminHints();
  };

  tabs.appendChild(tabAnswers);
  tabs.appendChild(tabBaseline);

  const baselineRow = document.createElement('div');
  baselineRow.className = 'baselineRow';

  const sel = document.createElement('select');
  sel.id = 'baselineSelect';
  for (let i = 1; i <= 10; i++) {
    const opt = document.createElement('option');
    opt.value = String(i);
    opt.textContent = `Fake user #${i}`;
    sel.appendChild(opt);
  }
  sel.value = String(state.baselineIndex);
  sel.onchange = () => {
    state.baselineIndex = parseInt(sel.value, 10) || 1;
  };

  baselineRow.appendChild(sel);

  box.appendChild(tabs);
  box.appendChild(baselineRow);

  meta.appendChild(box);
}

function renderAdminHints() {
  const meta = $('solveMeta');
  const hintId = 'adminHint';
  const old = document.getElementById(hintId);
  if (old) old.remove();
  if (!isAdminUI() || !state.selectedTest) return;

  const hint = document.createElement('div');
  hint.id = hintId;
  hint.className = 'tag ' + ((state.selectedTest.is_rasch && state.baselineDone.length < 10) ? 'warn' : 'ok');

  if (state.selectedTest.is_rasch && state.baselineDone.length < 10) {
    hint.textContent = `⚠️ Rasch test: Baseline kerak (${state.baselineDone.length}/10)`;
  } else {
    hint.textContent = '✅ Test sozlamalari';
  }

  meta.appendChild(hint);

  // Update submit button label
  const btn = $('btnSubmit');
  if (state.adminTab === 'answers') btn.textContent = '💾 Javoblarni saqlash';
  else btn.textContent = '💾 Baseline saqlash';
}

async function refreshBaselineStatus() {
  if (!isAdminUI() || !state.selectedTest || !state.selectedTest.is_rasch) {
    state.baselineDone = [];
    return;
  }
  try {
    const res = await apiGet(`/api/admin/baseline_status?test_id=${encodeURIComponent(state.selectedTest.id)}`);
    const data = await res.json();
    if (res.ok) {
      state.baselineDone = data.done || [];
    }
  } catch (_) {
    // ignore
  }
}

function startSolve(test) {
  state.selectedTest = test;
  setSolveVisible(true);

  $('solveName').textContent = test.name;
  $('solveMeta').textContent = `${test.num_questions} ta savol${test.is_rasch ? ' • Rasch' : ''}`;

  if (isAdminUI()) {
    setSubtitle('Admin panel');
  } else {
    setSubtitle('Test tekshirish');
  }

  resetAnswersForTest(test);
  mountAdminToolbar();
  refreshBaselineStatus().then(() => renderAdminHints());
}

function backToTests() {
  state.selectedTest = null;
  setSolveVisible(false);
  setSubtitle(isAdminUI() ? 'Admin panel' : 'Test tekshirish');
}

function renderCategories() {
  const wrap = $('catChips');
  wrap.innerHTML = '';
  state.categories.forEach((c) => {
    const el = document.createElement('div');
    el.className = 'chip' + (state.selectedCategory === c.key ? ' active' : '');
    el.textContent = c.label;
    el.onclick = () => selectCategory(c.key);
    wrap.appendChild(el);
  });
}

function renderTests() {
  const list = $('testsList');
  list.innerHTML = '';

  if (!state.selectedCategory) {
    setStatus('Kategoriya tanlang');
    return;
  }

  if (!state.tests.length) {
    setStatus('Test topilmadi');
    const empty = document.createElement('div');
    empty.className = 'muted';
    empty.textContent = 'Hozircha test yo‘q.';
    list.appendChild(empty);
    return;
  }

  setStatus(`${state.tests.length} ta test`);

  state.tests.forEach((t) => {
    const item = document.createElement('div');
    item.className = 'item';

    const left = document.createElement('div');
    left.className = 'itemLeft';
    const title = document.createElement('div');
    title.className = 'itemTitle';
    title.textContent = t.name;
    const meta = document.createElement('div');
    meta.className = 'itemMeta';
    meta.textContent = `${t.num_questions} ta savol${t.is_rasch ? ' • Rasch' : ''}`;
    left.appendChild(title);
    left.appendChild(meta);

    const right = document.createElement('div');
    right.className = 'itemRight';

    const btn = document.createElement('button');
    btn.className = 'btn primary';
    btn.type = 'button';
    btn.textContent = isAdminUI() ? 'Ochish' : 'Boshlash';
    btn.onclick = () => startSolve(t);

    // In user mode, hide non-ready rasch tests (server already filters for_check=1)
    if (!isAdminUI() && t.is_rasch && !t.baseline_ready) {
      btn.className = 'btn';
      btn.textContent = 'Tayyor emas';
      btn.disabled = true;
    }

    right.appendChild(btn);
    item.appendChild(left);
    item.appendChild(right);
    list.appendChild(item);
  });
}

async function selectCategory(catKey) {
  state.selectedCategory = catKey;
  state.tests = [];
  state.selectedTest = null;
  setSolveVisible(false);

  renderCategories();
  setStatus('Yuklanmoqda…');

  try {
    const forCheck = isAdminUI() ? '' : '&for_check=1';
    const res = await apiGet(`/api/tests?category=${encodeURIComponent(catKey)}${forCheck}`);
    const data = await res.json();

    if (res.status === 403 && data.join_required) {
      showGate(true, data.message, data.channel_url, data.group_url);
      return;
    }

    state.tests = data.tests || [];
    showGate(false);
    renderTests();
  } catch (e) {
    setStatus('Xatolik');
  }
}

async function loadCategories() {
  try {
    const res = await apiGet('/api/categories');
    const data = await res.json();
    if (res.status === 403 && data.join_required) {
      showGate(true, data.message, data.channel_url, data.group_url);
      return false;
    }
    state.categories = data.categories || [];
    renderCategories();
    return true;
  } catch (_) {
    return false;
  }
}

async function loadMe() {
  try {
    const res = await apiGet('/api/me');
    const data = await res.json();
    if (res.ok) {
      state.roles = Array.isArray(data.roles) ? data.roles : [data.role || 'user'];
      state.role = state.roles.includes('ceo') ? 'ceo' : state.roles.includes('admin') ? 'admin' : 'user';
    }
  } catch (_) {}
}

function showResult(data) {
  $('result').hidden = false;
  $('mCorrect').textContent = `${data.result.raw_correct} / ${data.result.total}`;
  $('mPercent').textContent = `${data.result.score_text}`;

  if (data.result.extra_label && data.result.extra_value) {
    $('mExtraWrap').hidden = false;
    $('mExtraLabel').textContent = data.result.extra_label;
    $('mExtra').textContent = data.result.extra_value;
  } else {
    $('mExtraWrap').hidden = true;
  }

  $('btnPdf').onclick = () => data.deeplinks.pdf ? openLink(data.deeplinks.pdf) : null;
  const certId = data.certificate_id || data.certificateId || 0;
  $('btnCert').onclick = async () => {
    if (!certId) return;
    $('btnCert').disabled = true;
    try {
      const r = await apiPost('/api/send_certificate', { certificate_id: certId });
      const j = await r.json();
      if (!r.ok) {
        alert(j.error || 'Xatolik');
        return;
      }
      alert('✅ Sertifikat bot chatiga yuborildi');
    } finally {
      $('btnCert').disabled = false;
    }
  };
  $('btnAgain').onclick = () => { backToTests(); };
}

async function submitUser() {
  if (!state.selectedTest) return;
  $('btnSubmit').disabled = true;
  try {
    const res = await apiPost('/api/submit', {
      test_id: state.selectedTest.id,
      answers: Object.fromEntries(Object.entries(state.answers).map(([k,v]) => [String(k), normalizeAnswerObj(v || emptyAnswer())])),
    });
    const data = await res.json();

    if (res.status === 403 && data.join_required) {
      showGate(true, data.message, data.channel_url, data.group_url);
      return;
    }

    if (!res.ok) {
      alert(data.error || 'Xatolik');
      return;
    }

    showResult(data);
  } finally {
    $('btnSubmit').disabled = false;
  }
}

async function saveAdminAnswers() {
  if (!state.selectedTest) return;
  $('btnSubmit').disabled = true;
  try {
    const res = await apiPost('/api/admin/save_answers', {
      test_id: state.selectedTest.id,
      answers: Object.fromEntries(Object.entries(state.answers).map(([k,v]) => [String(k), normalizeAnswerObj(v || emptyAnswer())])),
    });
    const data = await res.json();
    if (!res.ok) {
      alert(data.error || 'Xatolik');
      return;
    }
    await refreshBaselineStatus();
    renderAdminHints();
    alert('✅ Saqlandi');
  } finally {
    $('btnSubmit').disabled = false;
  }
}

async function saveAdminBaseline() {
  if (!state.selectedTest) return;
  $('btnSubmit').disabled = true;
  try {
    const res = await apiPost('/api/admin/baseline_submit', {
      test_id: state.selectedTest.id,
      baseline_index: state.baselineIndex,
      answers: Object.fromEntries(Object.entries(state.answers).map(([k,v]) => [String(k), normalizeAnswerObj(v || emptyAnswer())])),
    });
    const data = await res.json();
    if (!res.ok) {
      alert(data.error || 'Xatolik');
      return;
    }
    state.baselineDone = data.done || state.baselineDone;
    renderAdminHints();
    alert(`✅ Baseline saqlandi (${data.have}/10)`);
  } finally {
    $('btnSubmit').disabled = false;
  }
}

async function bootFixedTest() {
  try {
    const res = await apiGet(`/api/test?test_id=${encodeURIComponent(FIXED_TEST_ID)}`);
    const data = await res.json();
    if (!res.ok) {
      alert(data.error || 'Test topilmadi');
      return;
    }
    // Hide sidebar categories panel for direct open
    document.querySelector('.panel').style.display = 'none';
    $('testsTitle').textContent = isAdminUI() ? 'Admin: Test' : 'Test';
    setStatus('—');
    setSolveVisible(true);
    startSolve(data.test);
  } catch (e) {
    alert('Xatolik');
  }
}

async function init() {
  const t = tg();
  if (t) {
    try { t.ready(); } catch (_) {}
    try { t.expand(); } catch (_) {}
  }

  applyTheme(localStorage.getItem('msr_theme') || 'dark');
  $('btnTheme').onclick = toggleTheme;

  $('gateCheck').onclick = async () => {
    // Re-check by reloading categories
    await loadCategories();
  };

  $('btnBack').onclick = backToTests;
  $('btnHome').onclick = () => {
    // Return to main list view
    state.selectedTest = null;
    state.q = 1;
    setSolveVisible(false);
    $('result').hidden = true;
    setSubtitle(isAdminUI() ? 'Admin panel' : 'Test tekshirish');
  };
  $('btnPrev').onclick = goPrev;
  $('btnNext').onclick = goNext;

  await loadMe();

  if (isAdminUI()) {
    setSubtitle('Admin panel');
    $('btnPdf').hidden = true;
    $('btnCert').hidden = true;
    $('btnAgain').hidden = true;
  } else {
    setSubtitle('Test tekshirish');
  }

  $('btnSubmit').onclick = async () => {
    if (isAdminUI()) {
      if (state.adminTab === 'baseline') await saveAdminBaseline();
      else await saveAdminAnswers();
    } else {
      await submitUser();
    }
  };

  const ok = await loadCategories();
  if (!ok) return;

  if (FIXED_TEST_ID) {
    await bootFixedTest();
    return;
  }

  // Select first category by default
  if (state.categories.length) {
    await selectCategory(state.categories[0].key);
  }
}

init();
