'use strict';

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const STATUS_LABEL = {
  queued: '排队中', converting: '转码中', running: '转录中',
  done: '已完成', error: '失败', cancelled: '已取消',
};
const SPEAKER_COLORS = ['#6366f1', '#059669', '#d97706', '#dc2626',
  '#7c3aed', '#0891b2', '#db2777', '#65a30d'];
const LANG_LABEL = { zh: '中文', en: 'English' };

let status = null;
let jobs = [];
let selectedFile = null;
let pollTimer = null;

// ---- 基础工具 ----

async function api(path, options) {
  const res = await fetch(path, options);
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try {
      const j = await res.json();
      if (j.detail) msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail);
    } catch { /* 非 JSON 错误体 */ }
    throw new Error(msg);
  }
  return res.json();
}

function toast(message, isError = false) {
  const el = $('toast');
  el.textContent = message;
  el.classList.toggle('error', isError);
  el.hidden = false;
  clearTimeout(el._timer);
  el._timer = setTimeout(() => { el.hidden = true; }, 4000);
}

function fmtBytes(n) {
  if (n >= 1024 ** 3) return (n / 1024 ** 3).toFixed(2) + ' GB';
  if (n >= 1024 ** 2) return (n / 1024 ** 2).toFixed(1) + ' MB';
  if (n >= 1024) return (n / 1024).toFixed(0) + ' KB';
  return n + ' B';
}

// 毫秒 → m:ss / h:mm:ss
function fmtClock(ms) {
  const s = Math.floor(ms / 1000);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  const mm = String(m).padStart(2, '0'), ss = String(sec).padStart(2, '0');
  return h ? `${h}:${mm}:${ss}` : `${m}:${ss}`;
}

function fmtSec(sec) {
  if (sec < 60) return `${sec.toFixed(0)} 秒`;
  const m = Math.floor(sec / 60), s = Math.round(sec % 60);
  return `${m} 分 ${s} 秒`;
}

function fmtMsZh(ms) {
  const s = Math.round(ms / 1000);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  if (h) return `${h} 小时 ${m} 分`;
  if (m) return `${m} 分 ${sec} 秒`;
  return `${sec} 秒`;
}

function speakerColor(id) {
  return SPEAKER_COLORS[(id ?? 0) % SPEAKER_COLORS.length];
}

function speakerName(id) {
  return `说话人 ${id + 1}`;
}

// ---- 轮询 ----

async function poll() {
  try {
    const [st, jr] = await Promise.all([
      api('/api/status'),
      api('/api/jobs').then((r) => r.jobs),
    ]);
    status = st;
    jobs = jr;
    renderStatus();
    renderJobs();
  } catch (e) {
    console.error('轮询失败:', e);
  }
  const busy = (status?.model?.state !== 'ready')
    || jobs.some((j) => ['queued', 'converting', 'running'].includes(j.status));
  pollTimer = setTimeout(poll, busy ? 1000 : 4000);
}

function pollNow() {
  clearTimeout(pollTimer);
  poll();
}

// ---- 状态与设置面板 ----

function renderStatus() {
  const m = status.model;
  const chip = $('model-chip');
  chip.className = 'chip ' + m.state;

  if (m.state === 'ready' && m.device) {
    const free = m.device.memory_free ? ` · 空闲 ${fmtBytes(m.device.memory_free)}` : '';
    chip.textContent = `● 已就绪 · ${m.device.name}${free}`;
  } else if (m.state === 'loading') {
    chip.innerHTML = '<span class="spin"></span>模型加载中…';
  } else {
    chip.textContent = `✕ 模型不可用: ${m.error || '未知错误'}`;
  }

  // 设备下拉：仅在设备列表变化时重建，避免打断用户选择
  const sel = $('device-select');
  const sig = status.devices.map((d) => d.index + d.name + d.kind).join('|');
  if (sel.dataset.sig !== sig) {
    sel.dataset.sig = sig;
    const current = sel.value;
    sel.innerHTML = '<option value="auto">自动选择</option>'
      + status.devices.map((d) =>
        `<option value="${d.index}">${esc(d.name)} · ${esc(d.kind)} · ${fmtBytes(d.memory_free)} 空闲</option>`).join('');
    if ([...sel.options].some((o) => o.value === current)) sel.value = current;
  }
  sel.disabled = m.loading;
  $('reload-btn').disabled = m.loading;
  $('device-note').textContent = m.loading ? '模型加载中，加载完成后新任务自动继续…'
    : (m.error ? `提示: ${m.error}` : '');

  // 语言选项跟随模型能力
  const caps = status.capabilities;
  if (caps) {
    const langSel = $('opt-language');
    const cur = langSel.value;
    langSel.innerHTML = caps.languages.map((l) =>
      `<option value="${esc(l)}">${esc(LANG_LABEL[l] || l)} (${esc(l)})</option>`).join('');
    if (caps.languages.includes(cur)) langSel.value = cur;
    const diaSel = $('opt-diarize');
    diaSel.disabled = !caps.supports_diarization;
    diaSel.title = caps.supports_diarization ? '' : '当前模型不支持说话人分离';
  }

  // 运行信息
  const limits = status.limits;
  const info = [];
  info.push(`模型: ${esc(m.variant || '-')}（${esc(m.arch || '-')}）`);
  info.push(`版本: transcribe_cpp ${esc(status.version)} / native ${esc(status.native_version)}`);
  if (limits) info.push(`单次音频上限: 约 ${fmtMsZh(limits.effective_max_audio_ms)}`);
  info.push(`ffmpeg: ${status.ffmpeg ? '已安装（自动转码 16kHz 单声道）' : '未安装（仅支持 16kHz 单声道 WAV）'}`);
  info.push(`当前任务: ${status.active_jobs} 个进行中`);
  $('info-body').innerHTML = info.map((l) => esc(l)).join('<br>');

  updateStartBtn();
}

function updateStartBtn() {
  $('start-btn').disabled = !selectedFile || status?.model?.state !== 'ready';
}

// ---- 上传 ----

function setFile(file) {
  selectedFile = file;
  const chip = $('file-chip');
  if (file) {
    chip.hidden = false;
    $('file-name').textContent = file.name;
    $('file-size').textContent = fmtBytes(file.size);
  } else {
    chip.hidden = true;
    $('file-input').value = '';
  }
  updateStartBtn();
}

async function startTranscribe() {
  if (!selectedFile) return;
  if (status?.model?.state !== 'ready') {
    toast('模型尚未就绪，请稍候', true);
    return;
  }
  const fd = new FormData();
  fd.append('file', selectedFile);
  fd.append('language', $('opt-language').value);
  fd.append('timestamps', $('opt-timestamps').value);
  fd.append('diarize', $('opt-diarize').value);
  fd.append('kv_type', $('opt-kv').value);
  fd.append('n_threads', $('opt-threads').value || '0');
  fd.append('n_ctx', $('opt-ctx').value || '0');
  fd.append('keep_special_tags', $('opt-special').checked ? 'true' : 'false');

  const btn = $('start-btn');
  btn.disabled = true;
  btn.textContent = '提交中…';
  try {
    await api('/api/jobs', { method: 'POST', body: fd });
    setFile(null);
    toast('已加入任务队列');
  } catch (e) {
    toast(`提交失败: ${e.message}`, true);
  } finally {
    btn.textContent = '开始转录';
    updateStartBtn();
    pollNow();
  }
}

async function switchDevice() {
  const v = $('device-select').value;
  let body = { backend: 'auto', device_index: null };
  if (v !== 'auto') {
    const dev = status.devices.find((d) => String(d.index) === v);
    if (dev) body = { backend: dev.kind, device_index: dev.index };
  }
  try {
    await api('/api/model', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    toast('开始重载模型（等待当前任务结束）…');
  } catch (e) {
    toast(`切换失败: ${e.message}`, true);
  }
  pollNow();
}

// ---- 任务渲染 ----

function renderJobs() {
  const wrap = $('jobs');
  wrap.innerHTML = jobs.map(jobCard).join('');
}

function jobCard(j) {
  const active = ['queued', 'converting', 'running'].includes(j.status);
  const label = STATUS_LABEL[j.status] || j.status;
  const badgeText = j.status === 'queued' && j.queue_position > 1
    ? `排队中 (第 ${j.queue_position} 位)` : label + (j.detail ? ` · ${j.detail}` : '');

  const meta = [];
  if (j.audio_ms) meta.push(`时长 ${fmtMsZh(j.audio_ms)}`);
  if (j.status === 'running' && j.started) meta.push(`已用时 ${fmtSec((Date.now() / 1000) - j.started)}`);
  if (j.status === 'done' && j.started && j.finished) meta.push(`耗时 ${fmtSec(j.finished - j.started)}`);
  meta.push(`${LANG_LABEL[j.params.language] || j.params.language} · ${j.params.diarize === 'on' ? '说话人分离' : '无分离'}`);

  let actions = '';
  if (active) actions = `<button class="btn mini danger" data-action="cancel">取消</button>`;
  else actions = `<button class="btn mini" data-action="delete">删除</button>`;

  return `
  <div class="card job" data-id="${j.id}">
    <div class="job-head">
      <div class="job-title" title="${esc(j.filename)}">📁 ${esc(j.filename)}</div>
      <span class="badge ${j.status}">${esc(badgeText)}</span>
      ${actions}
    </div>
    <div class="job-meta">${meta.map((m) => `<span class="dot">${esc(m)}</span>`).join('')}</div>
    ${j.error ? `<div class="error-box">${esc(j.error)}</div>` : ''}
    ${j.result ? resultBlock(j) : ''}
  </div>`;
}

function resultBlock(j) {
  const r = j.result;
  const withDiarize = j.params.diarize === 'on';
  const speakers = new Set(r.segments.map((s) => s.speaker_id));

  const meta = [
    `${r.segments.length} 段`,
    withDiarize ? `${speakers.size} 位说话人` : null,
    `解码 ${(r.timings.decode_ms / 1000).toFixed(1)}s`,
    `编码 ${(r.timings.encode_ms / 1000).toFixed(1)}s`,
  ].filter(Boolean).join(' · ');

  const segs = r.segments.length ? r.segments.map((s) => `
    <div class="seg">
      <span class="seg-time">${fmtClock(s.t0_ms)} → ${fmtClock(s.t1_ms)}</span>
      ${withDiarize ? `<span class="seg-speaker" style="--sp:${speakerColor(s.speaker_id)}">${esc(speakerName(s.speaker_id))}</span>` : ''}
      <span class="seg-text">${esc(s.text)}</span>
    </div>`).join('')
    : `<div class="seg"><span class="seg-text">${esc(r.text)}</span></div>`;

  return `
  <div class="result">
    <div class="result-meta">${esc(LANG_LABEL[j.params.language] || j.params.language)} · ${esc(meta)}${j.detail ? ` · ${esc(j.detail)}` : ''}</div>
    ${withDiarize ? timeline(r) : ''}
    <div class="result-actions">
      <button class="btn mini" data-action="copy">复制全文</button>
      <button class="btn mini" data-action="txt">下载 TXT</button>
      <button class="btn mini" data-action="srt">下载 SRT</button>
      <button class="btn mini" data-action="json">下载 JSON</button>
    </div>
    <div class="seg-list">${segs}</div>
  </div>`;
}

function timeline(r) {
  const segs = r.speaker_segments || [];
  if (!segs.length) return '';
  const dur = Math.max(...segs.map((s) => s.t1_ms), 1);
  const rows = new Map();
  for (const s of segs) {
    if (!rows.has(s.speaker_id)) rows.set(s.speaker_id, []);
    rows.get(s.speaker_id).push(s);
  }
  const bars = [...rows.entries()].sort((a, b) => a[0] - b[0]).map(([sid, list]) => `
    <div class="tl-row">
      <div class="tl-label">${esc(speakerName(sid))}</div>
      <div class="tl-track">${list.map((s) =>
        `<div class="tl-bar" style="left:${(s.t0_ms / dur * 100).toFixed(2)}%;width:${Math.max((s.t1_ms - s.t0_ms) / dur * 100, 0.3).toFixed(2)}%;background:${speakerColor(sid)}"
              title="${fmtClock(s.t0_ms)} – ${fmtClock(s.t1_ms)}${s.p != null ? `（置信度 ${(s.p * 100).toFixed(0)}%）` : ''}"></div>`).join('')}</div>
    </div>`).join('');
  return `<div class="timeline">${bars}</div>`;
}

// ---- 导出 ----

function segLine(s, withDiarize) {
  const time = `[${fmtClock(s.t0_ms)} → ${fmtClock(s.t1_ms)}]`;
  const sp = withDiarize ? `${speakerName(s.speaker_id)}: ` : '';
  return `${time} ${sp}${s.text}`;
}

function fullText(j) {
  if (!j.result.segments.length) return j.result.text;
  return j.result.segments.map((s) => segLine(s, j.params.diarize === 'on')).join('\n');
}

function srtTime(ms) {
  const h = Math.floor(ms / 3600000), m = Math.floor(ms % 3600000 / 60000);
  const s = Math.floor(ms % 60000 / 1000), milli = Math.round(ms % 1000);
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')},${String(milli).padStart(3, '0')}`;
}

function toSRT(j) {
  const withDiarize = j.params.diarize === 'on';
  return j.result.segments.map((s, i) => {
    const sp = withDiarize ? `${speakerName(s.speaker_id)}: ` : '';
    return `${i + 1}\n${srtTime(s.t0_ms)} --> ${srtTime(s.t1_ms)}\n${sp}${s.text}\n`;
  }).join('\n');
}

function download(name, text) {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }));
  a.download = name;
  a.click();
  URL.revokeObjectURL(a.href);
}

function baseName(j) {
  return j.filename.replace(/\.[^.]+$/, '') || 'transcript';
}

// ---- 事件绑定 ----

$('dropzone').addEventListener('click', () => $('file-input').click());
$('file-input').addEventListener('change', (e) => setFile(e.target.files[0] || null));
$('file-clear').addEventListener('click', () => setFile(null));
$('start-btn').addEventListener('click', startTranscribe);
$('reload-btn').addEventListener('click', switchDevice);

const dz = $('dropzone');
['dragenter', 'dragover'].forEach((ev) =>
  dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add('drag'); }));
['dragleave', 'drop'].forEach((ev) =>
  dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove('drag'); }));
dz.addEventListener('drop', (e) => setFile(e.dataTransfer.files[0] || null));

$('jobs').addEventListener('click', async (e) => {
  const btn = e.target.closest('button[data-action]');
  if (!btn) return;
  const card = btn.closest('.job');
  const id = card.dataset.id;
  const job = jobs.find((j) => j.id === id);
  if (!job) return;

  try {
    switch (btn.dataset.action) {
      case 'cancel':
        await api(`/api/jobs/${id}/cancel`, { method: 'POST' });
        toast('已请求取消');
        break;
      case 'delete':
        await api(`/api/jobs/${id}/delete`, { method: 'POST' });
        break;
      case 'copy':
        await navigator.clipboard.writeText(fullText(job));
        toast('已复制到剪贴板');
        break;
      case 'txt':
        download(`${baseName(job)}.txt`, fullText(job));
        break;
      case 'srt':
        download(`${baseName(job)}.srt`, toSRT(job));
        break;
      case 'json':
        download(`${baseName(job)}.json`, JSON.stringify(job, null, 2));
        break;
    }
  } catch (err) {
    toast(`操作失败: ${err.message}`, true);
  }
  pollNow();
});

// ---- 启动 ----

$('dz-hint').textContent = '支持音频/视频文件，自动转码为 16kHz 单声道';
poll();
