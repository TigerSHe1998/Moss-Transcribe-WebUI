'use strict';

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const SPEAKER_COLORS = ['#6366f1', '#059669', '#d97706', '#dc2626',
  '#7c3aed', '#0891b2', '#db2777', '#65a30d'];

// ---- 界面语言（i18n）----
// 词典值支持 {token} 占位，t(key, params) 替换。服务端生成的错误详情
// 不翻译（诊断信息）；任务 detail 的少量已知值经 DETAIL_KEYS 映射，
// 未映射原文透传。
let lang = 'zh';
try { if (localStorage.getItem('lang') === 'en') lang = 'en'; } catch { /* 存储被禁 */ }

const I18N = {
  zh: {
    langBtn: 'English', langBtnTitle: '切换界面语言',
    chipInit: '初始化…', chipReady: '● 已就绪 · {name}', chipLoading: '模型加载中…',
    chipError: '✕ 模型不可用: {msg}', unknown: '未知错误',
    memBarText: '已用 {used} / {total}', memBarTitle: '{name} · 可用 {free} ({pct}% 已用)',
    autoSelect: '自动选择', deviceOpt: '{name} · {kind} · {free} 空闲',
    deviceNoteLoading: '模型加载中，加载完成后新任务自动继续…', deviceNoteError: '提示: {msg}',
    diaUnsupported: '当前模型不支持说话人分离',
    h2Device: '推理设备', lblDevice: '设备', btnReload: '切换设备（重载模型）',
    h2Settings: '转录设置', lblTimestamps: '时间戳', optSegment: '分段', optNone: '无',
    lblDiarize: '说话人分离', optOn: '开启', optOff: '关闭',
    lblChunk: '长音频自动分段',
    chunkOff: '关闭', chunk15: '15分钟（推荐显存 8G）', chunk30: '30分钟（推荐显存 12G）',
    chunk45: '45分钟（推荐显存 16G）', chunk60: '60分钟（推荐显存 20G）',
    noteChunk: '显存不足时，可开启音频自动分段降低显存压力；自动分段产生的转录结果之间说话人序号和别名不会同步，需手动设置。',
    advanced: '高级设置', lblKv: 'KV 缓存类型', lblThreads: 'CPU 线程数（0 = 默认）',
    lblCtx: '上下文长度 n_ctx（0 = 默认）',
    noteCtx: 'n_ctx 默认 131072，调小会降低单次音频的时长上限；线程数仅在 CPU 后端生效。',
    h2Info: '运行信息', h2Decl: '声明',
    declBody: '本项目为<strong>完全免费</strong>的 Apache 2.0 协议开源项目，数据不上云，所有计算均在本地进行。唯一发布地址 <a href="https://github.com/TigerSHe1998/Moss-Transcribe-WebUI" target="_blank" rel="noopener">TigerSHe1998/Moss-Transcribe-WebUI</a>，若您从任何渠道付费获取此软件，请立刻申请退款。',
    h2Upload: '上传媒体', lblBatch: '批量模式', titleBatch: '支持文件多选上传', removeFile: '移除',
    dzTitle: '拖拽文件到此处，或点击选择',
    dzHint: '支持音频/视频文件，自动转码为 16kHz 单声道',
    btnStart: '开始转录',
    infoModel: '模型名称: {variant}（{arch}）', infoModelFile: '模型文件: {path}（{size}）',
    infoVersion: '后端版本: transcribe_cpp {v} / native {n}', sizeUnknown: '大小未知',
    infoLimit: '单次音频上限: 约 {dur}（引擎上限，实际请根据可用显存 / 内存判断）',
    infoFfmpegOn: 'ffmpeg: 已激活（{src}）',
    infoFfmpegOff: 'ffmpeg: 未激活（仅支持 16kHz 单声道 WAV，请放入 resources/ffmpeg/）',
    infoJobs: '当前任务: {n} 个进行中',
    stQueued: '排队中', stConverting: '转码中', stRunning: '转录中', stDone: '已完成',
    stError: '失败', stCancelled: '已取消', queuedPos: '排队中 (第 {n} 位)',
    btnCancel: '取消', btnDelete: '删除',
    metaDuration: '时长 {dur}', metaElapsedPrefix: '已用时', metaTook: '耗时 {dur}',
    diarizeOn: '说话人分离', diarizeOff: '无分离',
    detailPartial: '含部分结果', detailTruncated: '输出被截断，仅部分结果',
    detailTranscoding: 'ffmpeg 转码中', detailReadWav: '读取 WAV',
    metaSegs: '{n} 段', metaSpeakers: '{n} 位说话人', metaNoTs: '无时间戳',
    metaDecode: '解码 {v}s', metaEncode: '编码 {v}s',
    btnCopy: '复制全文', btnTxt: '下载 TXT', btnSrt: '下载 SRT', btnJson: '下载 JSON',
    msToggleText: '显示毫秒级时间戳', segPlayTitle: '从此处播放',
    speakerName: '说话人 {n}', tlEditTitle: '修改说话人名称',
    renameTitle: '修改「{name}」的名称', renameAria: '修改说话人名称',
    renamePlaceholder: '留空则恢复默认名称', btnCancelMini: '取消', btnOk: '确认',
    chipMulti: '已选 {n} 个文件',
    uploading: '上传中 {p}%', uploadingN: '上传中 {nth} {p}%',
    btnUploading: '上传中…', btnUploadingN: '上传中 {nth}…',
    processing: '服务器处理中…', processingN: '服务器处理中 {nth}…',
    btnProcessing: '处理中…', btnProcessingN: '处理中 {nth}…',
    toastQueued: '已加入任务队列', toastSplit: '音频已切分为 {n} 个分段任务并加入队列',
    toastBatchDone: '{n} 个文件已加入队列', toastBatchSplit: '（切分后共 {n} 个任务）',
    toastBatchMixed: '{ok} 个成功，{fail} 个失败（{err}）',
    toastSubmitFail: '提交失败: {msg}', toastModelNotReady: '模型尚未就绪，请稍候',
    toastCancelled: '已请求取消', toastCopied: '已复制到剪贴板',
    toastOpFail: '操作失败: {msg}', toastWaitJobs: '请等待任务结束再切换设备',
    toastReloading: '开始重载模型…', toastSwitchFail: '切换失败: {msg}',
    secOnly: '{v} 秒', minSec: '{m} 分 {s} 秒', hourMin: '{h} 小时 {m} 分',
  },
  en: {
    langBtn: '中文', langBtnTitle: 'Switch interface language',
    chipInit: 'Initializing…', chipReady: '● Ready · {name}', chipLoading: 'Loading model…',
    chipError: '✕ Model unavailable: {msg}', unknown: 'unknown error',
    memBarText: '{used} / {total} used', memBarTitle: '{name} · {free} free ({pct}% used)',
    autoSelect: 'Auto select', deviceOpt: '{name} · {kind} · {free} free',
    deviceNoteLoading: 'Model is loading; new jobs will resume automatically once ready…',
    deviceNoteError: 'Note: {msg}',
    diaUnsupported: 'This model does not support speaker diarization',
    h2Device: 'Inference Device', lblDevice: 'Device', btnReload: 'Switch device (reload model)',
    h2Settings: 'Transcription Settings', lblTimestamps: 'Timestamps', optSegment: 'Segments', optNone: 'None',
    lblDiarize: 'Speaker diarization', optOn: 'On', optOff: 'Off',
    lblChunk: 'Auto-split long audio',
    chunkOff: 'Off', chunk15: '15 min (8G VRAM recommended)', chunk30: '30 min (12G VRAM recommended)',
    chunk45: '45 min (16G VRAM recommended)', chunk60: '60 min (20G VRAM recommended)',
    noteChunk: 'If VRAM is insufficient, enable auto-split to reduce memory pressure. Speaker IDs and aliases are not synced across segments — set them manually.',
    advanced: 'Advanced', lblKv: 'KV cache type', lblThreads: 'CPU threads (0 = default)',
    lblCtx: 'Context length n_ctx (0 = default)',
    noteCtx: 'n_ctx defaults to 131072; lowering it reduces the max audio length per run. Threads apply to the CPU backend only.',
    h2Info: 'Runtime Info', h2Decl: 'Notice',
    declBody: 'This project is <strong>completely free</strong> and open-source under the Apache 2.0 license. No data is uploaded to the cloud — all computation runs locally. The only official release is <a href="https://github.com/TigerSHe1998/Moss-Transcribe-WebUI" target="_blank" rel="noopener">TigerSHe1998/Moss-Transcribe-WebUI</a>. If you obtained this software through any paid channel, please request a refund immediately.',
    h2Upload: 'Upload Media', lblBatch: 'Batch mode', titleBatch: 'Select multiple files at once', removeFile: 'Remove',
    dzTitle: 'Drag files here, or click to select',
    dzHint: 'Audio/video files supported; auto-converted to 16kHz mono',
    btnStart: 'Start transcription',
    infoModel: 'Model: {variant} ({arch})', infoModelFile: 'Model file: {path} ({size})',
    infoVersion: 'Backend: transcribe_cpp {v} / native {n}', sizeUnknown: 'unknown size',
    infoLimit: 'Max audio per run: ~{dur} (engine limit; actual capacity depends on available VRAM / RAM)',
    infoFfmpegOn: 'ffmpeg: active ({src})',
    infoFfmpegOff: 'ffmpeg: unavailable (16kHz mono WAV only; put binaries in resources/ffmpeg/)',
    infoJobs: 'Active jobs: {n}',
    stQueued: 'Queued', stConverting: 'Converting', stRunning: 'Transcribing', stDone: 'Done',
    stError: 'Failed', stCancelled: 'Cancelled', queuedPos: 'Queued (#{n})',
    btnCancel: 'Cancel', btnDelete: 'Delete',
    metaDuration: 'Duration {dur}', metaElapsedPrefix: 'Elapsed', metaTook: 'Took {dur}',
    diarizeOn: 'Diarization', diarizeOff: 'No diarization',
    detailPartial: 'with partial result', detailTruncated: 'output truncated, partial result only',
    detailTranscoding: 'transcoding (ffmpeg)', detailReadWav: 'reading WAV',
    metaSegs: '{n} segment{-s}', metaSpeakers: '{n} speaker{-s}', metaNoTs: 'No timestamps',
    metaDecode: 'Decode {v}s', metaEncode: 'Encode {v}s',
    btnCopy: 'Copy all', btnTxt: 'Download TXT', btnSrt: 'Download SRT', btnJson: 'Download JSON',
    msToggleText: 'Show millisecond timestamps', segPlayTitle: 'Play from here',
    speakerName: 'Speaker {n}', tlEditTitle: 'Rename speaker',
    renameTitle: 'Rename "{name}"', renameAria: 'Rename speaker',
    renamePlaceholder: 'Leave empty to reset to default', btnCancelMini: 'Cancel', btnOk: 'OK',
    chipMulti: '{n} files selected',
    uploading: 'Uploading {p}%', uploadingN: 'Uploading {nth} {p}%',
    btnUploading: 'Uploading…', btnUploadingN: 'Uploading {nth}…',
    processing: 'Processing on server…', processingN: 'Processing on server {nth}…',
    btnProcessing: 'Processing…', btnProcessingN: 'Processing {nth}…',
    toastQueued: 'Job queued', toastSplit: 'Audio split into {n} jobs and queued',
    toastBatchDone: '{n} files queued', toastBatchSplit: ' ({n} jobs after splitting)',
    toastBatchMixed: '{ok} succeeded, {fail} failed ({err})',
    toastSubmitFail: 'Submit failed: {msg}', toastModelNotReady: 'Model not ready yet, please wait',
    toastCancelled: 'Cancel requested', toastCopied: 'Copied to clipboard',
    toastOpFail: 'Operation failed: {msg}', toastWaitJobs: 'Wait for running jobs to finish before switching devices',
    toastReloading: 'Reloading model…', toastSwitchFail: 'Switch failed: {msg}',
    secOnly: '{v}s', minSec: '{m}m {s}s', hourMin: '{h}h {m}m',
  },
};

function t(key, params) {
  let s = I18N[lang][key] ?? I18N.zh[key] ?? key;
  if (params) for (const [k, v] of Object.entries(params)) s = s.replaceAll(`{${k}}`, v);
  return s;
}

// 英文单复数：{n} 为 1 时去掉复数占位的 -s（zh 词条不含该标记，不受影响）
function tn(key, params) {
  const s = t(key, params);
  return params && Number(params.n) === 1 ? s.replace('{-s}', '') : s.replace('{-s}', 's');
}

const STATUS_KEYS = {
  queued: 'stQueued', converting: 'stConverting', running: 'stRunning',
  done: 'stDone', error: 'stError', cancelled: 'stCancelled',
};
const statusLabel = (s) => (STATUS_KEYS[s] ? t(STATUS_KEYS[s]) : s);

const DETAIL_KEYS = {
  '含部分结果': 'detailPartial',
  '输出被截断，仅部分结果': 'detailTruncated',
  'ffmpeg 转码中': 'detailTranscoding',
  '读取 WAV': 'detailReadWav',
};
const detailLabel = (d) => (DETAIL_KEYS[d] ? t(DETAIL_KEYS[d]) : d);

// 静态文案：index.html 挂 data-i18n / data-i18n-html / data-i18n-title，
// 切换语言时按词典整体重写（词典是可信静态串，innerHTML 直注）
function applyStaticTexts() {
  document.documentElement.lang = lang === 'en' ? 'en' : 'zh-CN';
  document.querySelectorAll('[data-i18n]').forEach((el) => { el.textContent = t(el.dataset.i18n); });
  document.querySelectorAll('[data-i18n-html]').forEach((el) => { el.innerHTML = t(el.dataset.i18nHtml); });
  document.querySelectorAll('[data-i18n-title]').forEach((el) => { el.title = t(el.dataset.i18nTitle); });
  const btn = $('lang-btn');
  btn.textContent = t('langBtn');
  btn.title = t('langBtnTitle');
}

let status = null;
let jobs = [];
let selectedFiles = [];  // 批量模式下可同时持有多个待上传文件
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

// 毫秒级版本：分段时间轴与悬浮提示用；播放器读数仍用秒级（timeupdate 粒度粗，毫秒只会闪跳）
function fmtClockMs(ms, showMs = true) {
  return showMs ? `${fmtClock(ms)}.${String(Math.floor(ms % 1000)).padStart(3, '0')}` : fmtClock(ms);
}

function fmtSec(sec) {
  if (sec < 60) return t('secOnly', { v: sec.toFixed(0) });
  return t('minSec', { m: Math.floor(sec / 60), s: Math.round(sec % 60) });
}

function fmtMsZh(ms) {
  const s = Math.round(ms / 1000);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  if (h) return t('hourMin', { h, m });
  if (m) return t('minSec', { m, s: sec });
  return t('secOnly', { v: sec });
}

// 后端 speaker_id 从 1 起且可能不连续；按出现顺序映射为 1..N 的连续显示编号
function buildSpeakerMap(r) {
  const ids = new Set(r.segments.map((s) => s.speaker_id));
  for (const s of r.speaker_segments || []) ids.add(s.speaker_id);
  const map = new Map();
  [...ids].filter((id) => id >= 0).sort((a, b) => a - b)
    .forEach((id, i) => map.set(id, i + 1));
  return map;
}

function speakerColor(num) {
  return SPEAKER_COLORS[(num - 1) % SPEAKER_COLORS.length];
}

function speakerName(map, id, aliases) {
  const alias = aliases?.get(id);
  return alias || t('speakerName', { n: map.get(id) ?? id });
}

// 说话人别名：按任务 id 存 localStorage（按原始 speaker_id）；
// 页面刷新不丢；任务删除时清键；服务重启后任务为内存态，键自然作废
function loadAliases(jobId) {
  try {
    return new Map(JSON.parse(localStorage.getItem(`spk-${jobId}`) || '[]'));
  } catch {
    return new Map();
  }
}

function saveAliases(jobId, map) {
  try {
    localStorage.setItem(`spk-${jobId}`, JSON.stringify([...map]));
  } catch { /* 隐私模式等存储被禁时静默降级为会话内 */ }
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
  pollTimer = setTimeout(poll, busy ? 1000 : 2000);
}

function pollNow() {
  clearTimeout(pollTimer);
  poll();
}

// ---- 状态与设置面板 ----

// 顶栏显存进度条：device 为 null 时隐藏（模型未就绪/加载中无归属设备）
function renderMemBar(device) {
  const bar = $('mem-bar');
  if (!device || !device.memory_total) {
    bar.hidden = true;
    return;
  }
  bar.hidden = false;
  const used = Math.max(device.memory_total - device.memory_free, 0);
  const pct = Math.min(used / device.memory_total * 100, 100);
  const fill = $('mem-fill');
  fill.style.width = pct.toFixed(1) + '%';
  fill.classList.toggle('warn', pct >= 70 && pct < 90);
  fill.classList.toggle('crit', pct >= 90);
  $('mem-text').textContent = t('memBarText', { used: fmtGiB(used), total: fmtGiB(device.memory_total) });
  bar.title = t('memBarTitle', { name: device.name, free: fmtGiB(device.memory_free), pct: pct.toFixed(0) });
}

function fmtGiB(n) {
  return (n / 1024 ** 3).toFixed(2) + 'G';
}

function renderStatus() {
  const m = status.model;
  const chip = $('model-chip');
  chip.className = 'chip ' + m.state;

  if (m.state === 'ready' && m.device) {
    chip.textContent = t('chipReady', { name: m.device.name });
    renderMemBar(m.device);
  } else if (m.state === 'loading') {
    chip.innerHTML = '<span class="spin"></span>' + t('chipLoading');
    renderMemBar(null);
  } else {
    chip.textContent = t('chipError', { msg: m.error || t('unknown') });
    renderMemBar(null);
  }

  // 设备下拉：仅在设备列表或语言变化时重建，避免打断用户选择
  const sel = $('device-select');
  const sig = status.devices.map((d) => d.index + d.name + d.kind).join('|') + '|' + lang;
  if (sel.dataset.sig !== sig) {
    sel.dataset.sig = sig;
    const current = sel.value;
    sel.innerHTML = `<option value="auto">${esc(t('autoSelect'))}</option>`
      + status.devices.map((d) =>
        `<option value="${d.index}">${esc(t('deviceOpt', { name: d.name, kind: d.kind, free: fmtBytes(d.memory_free) }))}</option>`).join('');
    if ([...sel.options].some((o) => o.value === current)) sel.value = current;
  }
  sel.disabled = m.loading;
  $('reload-btn').disabled = m.loading;
  $('device-note').textContent = m.loading ? t('deviceNoteLoading')
    : (m.error ? t('deviceNoteError', { msg: m.error }) : '');

  // 说话人分离选项跟随模型能力
  const caps = status.capabilities;
  if (caps) {
    const diaSel = $('opt-diarize');
    diaSel.disabled = !caps.supports_diarization;
    diaSel.title = caps.supports_diarization ? '' : t('diaUnsupported');
  }

  // 运行信息
  const limits = status.limits;
  const info = [];
  info.push(t('infoModel', { variant: m.variant || '-', arch: m.arch || '-' }));
  if (m.path) {
    info.push(t('infoModelFile', { path: m.path, size: m.size_bytes ? fmtBytes(m.size_bytes) : t('sizeUnknown') }));
  }
  info.push(t('infoVersion', { v: status.version, n: status.native_version }));
  if (limits) info.push(t('infoLimit', { dur: fmtMsZh(limits.effective_max_audio_ms) }));
  if (status.ffmpeg) {
    const src = status.ffmpeg_source === 'bundled' ? 'bundled' : 'PATH';
    info.push(t('infoFfmpegOn', { src }));
  } else {
    info.push(t('infoFfmpegOff'));
  }
  info.push(t('infoJobs', { n: status.active_jobs }));
  $('info-body').innerHTML = info.map((l) => esc(l)).join('<br>');

  updateStartBtn();
}

function updateStartBtn() {
  $('start-btn').disabled = !selectedFiles.length || status?.model?.state !== 'ready';
}

// ---- 上传 ----

// files: File 数组（单个也走数组，统一状态）；null 等价清空
function setFiles(files) {
  selectedFiles = files ? [...files] : [];
  const chip = $('file-chip');
  if (selectedFiles.length === 1) {
    chip.hidden = false;
    $('file-name').textContent = selectedFiles[0].name;
    $('file-size').textContent = fmtBytes(selectedFiles[0].size);
    chip.title = '';
  } else if (selectedFiles.length > 1) {
    chip.hidden = false;
    const total = selectedFiles.reduce((a, f) => a + f.size, 0);
    $('file-name').textContent = t('chipMulti', { n: selectedFiles.length });
    $('file-size').textContent = fmtBytes(total);
    chip.title = selectedFiles.map((f) => f.name).join('\n'); // 悬浮看清单
  } else {
    chip.hidden = true;
    $('file-name').textContent = '';
    $('file-size').textContent = '';
    chip.title = '';
    $('file-input').value = '';
  }
  updateStartBtn();
}

// fetch 拿不到上传进度，提交大文件必须用 XHR 的 upload.onprogress
function uploadWithProgress(fd, onProgress, onUploaded) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/jobs');
    xhr.responseType = 'json';
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(e.loaded / e.total);
    };
    // 上传完毕后服务器可能还要分段/预检几秒（开启自动分段的长音频），
    // 提示语从"上传中"切换过去，避免进度条停在 100% 干等
    if (onUploaded) xhr.upload.onload = () => onUploaded();
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(xhr.response);
      } else {
        const d = xhr.response?.detail;
        reject(new Error(typeof d === 'string' ? d : (d ? JSON.stringify(d) : `${xhr.status} ${xhr.statusText}`)));
      }
    };
    xhr.onerror = () => reject(new Error('网络错误'));
    xhr.onabort = () => reject(new Error('已取消'));
    xhr.send(fd);
  });
}

async function startTranscribe() {
  if (!selectedFiles.length) return;
  if (status?.model?.state !== 'ready') {
    toast(t('toastModelNotReady'), true);
    return;
  }
  const files = [...selectedFiles];
  const multi = files.length > 1;
  const formVals = {
    timestamps: $('opt-timestamps').value,
    diarize: $('opt-diarize').value,
    kv_type: $('opt-kv').value,
    n_threads: $('opt-threads').value || '0',
    n_ctx: $('opt-ctx').value || '0',
    chunk_min: $('opt-chunk').value || '0',
  };

  const btn = $('start-btn');
  const bar = $('upload-progress');
  const fill = $('upload-fill');
  const label = $('upload-label');
  btn.disabled = true;
  bar.hidden = false;

  let okCount = 0, failCount = 0, jobTotal = 0, lastErr = null;
  for (let i = 0; i < files.length; i++) {
    const nth = multi ? `(${i + 1}/${files.length})` : '';
    btn.textContent = t('btnUploading' + (multi ? 'N' : ''), { nth });
    const paint = (pct) => {
      fill.style.width = (pct * 100).toFixed(1) + '%';
      label.textContent = t('uploading' + (multi ? 'N' : ''), { nth, p: (pct * 100).toFixed(0) });
    };
    paint(0);

    const fd = new FormData();
    fd.append('file', files[i]);
    for (const [k, v] of Object.entries(formVals)) fd.append(k, v);

    try {
      const r = await uploadWithProgress(fd, paint, () => {
        paint(1);
        label.textContent = t('processing' + (multi ? 'N' : ''), { nth });
        btn.textContent = t('btnProcessing' + (multi ? 'N' : ''), { nth });
      });
      okCount++;
      jobTotal += r.count || 1;
    } catch (e) {
      failCount++; // 单个失败不中断，继续传后续文件
      lastErr = e;
    }
  }

  setFiles(null);
  if (!failCount) {
    if (multi) toast(t('toastBatchDone', { n: okCount }) + (jobTotal > okCount ? t('toastBatchSplit', { n: jobTotal }) : ''));
    else toast(jobTotal > 1 ? t('toastSplit', { n: jobTotal }) : t('toastQueued'));
  } else if (!okCount) {
    toast(t('toastSubmitFail', { msg: lastErr?.message || t('unknown') }), true);
  } else {
    toast(t('toastBatchMixed', { ok: okCount, fail: failCount, err: lastErr?.message || t('unknown') }), true);
  }
  bar.hidden = true;
  fill.style.width = '0';
  btn.textContent = t('btnStart');
  updateStartBtn();
  pollNow();
}

async function switchDevice() {
  // 有任务进行时不切换后端，仅提示；点击时取最新状态，避免轮询间隙的竞态
  let active = jobs.some((j) => ['queued', 'converting', 'running'].includes(j.status));
  if (!active) {
    try {
      active = (await api('/api/status')).active_jobs > 0;
    } catch { /* 状态查询失败时按本地任务列表判断 */ }
  }
  if (active) {
    toast(t('toastWaitJobs'), true);
    return;
  }
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
    toast(t('toastReloading'));
  } catch (e) {
    toast(t('toastSwitchFail', { msg: e.message }), true);
  }
  pollNow();
}

// ---- 任务渲染 ----
// 键控增量渲染：内容未变的卡片复用已有 DOM。整体 innerHTML 重建会重置
// 分段列表的滚动位置（曾经的 bug），且打断用户阅读。
const jobEls = new Map(); // job id -> { el, sig }

function jobSig(j) {
  // lang 入签：切换语言时所有卡片全量重建（含进行中任务）
  return JSON.stringify([j.status, j.detail, j.error, j.queue_position,
    j.audio_ms, j.has_audio, j.result ? j.result.segments.length : -1, lang]);
}

// ---- 回听播放器 ----
// 每张结果卡片一个隐藏 <audio>（preload=none，不点不下载）；进度条用
// input[type=range]（原生支持拖拽）；播放中按当前时间高亮对应分段并
// 保持其在列表内可见；同一时刻只允许一个卡片发声
let activeAudio = null;

function wirePlayer(card, j) {
  const audio = card.querySelector('.job-audio');
  if (!audio) return;
  const toggle = card.querySelector('.player-toggle');
  const seek = card.querySelector('.player-seek');
  const timeEl = card.querySelector('.player-time');
  const segList = card.querySelector('.seg-list');
  const segEls = [...card.querySelectorAll('.seg')];
  const noTs = j.params.timestamps === 'none';
  const bounds = noTs ? [] : (j.result ? j.result.segments.map((s) => [s.t0_ms, s.t1_ms]) : []);
  let pendingSeek = null; // preload=none 下 metadata 未加载时先记住目标位置

  const paintBar = (pct) => {
    seek.style.background = `linear-gradient(to right, var(--green) ${pct}%, #e5e7eb ${pct}%)`;
  };
  paintBar(0);

  const setTimeText = (ms) => {
    timeEl.textContent = `${fmtClock(ms)} / ${fmtClock(audio.duration * 1000 || j.audio_ms)}`;
  };

  const setActive = (ms, forceScroll = false) => {
    if (!bounds.length) return;
    let idx = -1;
    for (let i = 0; i < bounds.length; i++) {
      if (ms >= bounds[i][0] && ms < bounds[i][1]) { idx = i; break; }
    }
    if (idx < 0 && ms >= bounds[bounds.length - 1][1]) idx = bounds.length - 1;
    segEls.forEach((el, i) => el.classList.toggle('active', i === idx));
    // 播放中持续跟随；forceScroll 供点击跳转（暂停时也要滚到位）
    if (idx >= 0 && (forceScroll || !audio.paused)) {
      const top = segEls[idx].offsetTop;
      if (top < segList.scrollTop + 8 || top > segList.scrollTop + segList.clientHeight - 36) {
        segList.scrollTop = top - segList.clientHeight / 2;
      }
    }
  };

  // 音频跳到 t0（ms），同步进度条/时间文本/高亮；不改变播放状态
  const jumpTo = (ms) => {
    if (audio.readyState >= 1) audio.currentTime = ms / 1000;
    else {
      // preload=none 且从未播放：主动加载 metadata，让 pendingSeek 尽快落地
      // （否则要等用户点播放，届时才跳转会显得"从 0 开始又跳走"）
      pendingSeek = ms / 1000;
      audio.load();
    }
    seek.value = Math.round(ms);
    setTimeText(ms);
    paintBar(seek.max ? (ms / +seek.max) * 100 : 0);
    setActive(ms, true);
  };

  toggle.addEventListener('click', () => {
    if (audio.paused) audio.play().catch(() => {});
    else audio.pause();
  });

  card.querySelectorAll('.seg-play').forEach((btn) => {
    btn.addEventListener('click', () => {
      jumpTo(+btn.dataset.t0);
      audio.play().catch(() => {});
    });
  });

  // 说话人时间轴色块：跳到色块起始时间，转录条目按时间落点高亮；
  // 播放状态保持原样（播放则继续播，暂停则保持暂停）
  card.querySelectorAll('.tl-bar').forEach((bar) => {
    bar.addEventListener('click', () => {
      const t0 = +bar.dataset.t0;
      // 说话人段与转录分段时间未必对齐：落在色块区间内、否则其后最近的一段
      let idx = bounds.findIndex(([a, b]) => t0 >= a && t0 < b);
      if (idx === -1) {
        for (let i = 0; i < bounds.length; i++) {
          if (bounds[i][0] >= t0) { idx = i; break; }
        }
      }
      if (idx === -1) idx = bounds.length - 1;
      jumpTo(bounds[idx][0]);
    });
  });

  seek.addEventListener('input', () => jumpTo(+seek.value));

  audio.addEventListener('loadedmetadata', () => {
    if (audio.duration && isFinite(audio.duration)) seek.max = Math.round(audio.duration * 1000);
    if (pendingSeek != null) {
      audio.currentTime = pendingSeek;
      pendingSeek = null;
    }
  });
  audio.addEventListener('timeupdate', () => {
    const ms = audio.currentTime * 1000;
    seek.value = Math.round(ms);
    setTimeText(ms);
    paintBar(seek.max ? (ms / +seek.max) * 100 : 0);
    setActive(ms);
  });
  audio.addEventListener('play', () => {
    toggle.textContent = '⏸';
    if (activeAudio && activeAudio !== audio) activeAudio.pause();
    activeAudio = audio;
  });
  audio.addEventListener('pause', () => { toggle.textContent = '▶'; });
  audio.addEventListener('ended', () => {
    toggle.textContent = '▶';
    seek.value = 0;
    paintBar(0);
    segEls.forEach((el) => el.classList.remove('active'));
  });

  // 毫秒开关：只改写时间文本（DOM 不动，播放/滚动/高亮天然保持）。
  // 原始毫秒值在渲染时存于 data-t0/t1，置信度存于 data-p
  const msToggle = card.querySelector('.ms-toggle');
  if (msToggle) {
    msToggle.addEventListener('change', () => {
      const on = msToggle.querySelector('input[type="checkbox"]').checked;
      msToggle.classList.toggle('on', on);
      card.querySelectorAll('.seg-time').forEach((el) => {
        el.textContent = `${fmtClockMs(+el.dataset.t0, on)} → ${fmtClockMs(+el.dataset.t1, on)}`;
      });
      card.querySelectorAll('.tl-bar').forEach((el) => {
        const conf = el.dataset.p != null ? `（置信度 ${(el.dataset.p * 100).toFixed(0)}%）` : '';
        el.title = `${fmtClockMs(+el.dataset.t0, on)} – ${fmtClockMs(+el.dataset.t1, on)}${conf}`;
      });
    });
  }

  // 说话人别名：点 ✎ 弹小窗改名；确认后就地改写该说话人的所有徽章
  // （不重建卡片），别名存 localStorage 供导出与刷新后渲染使用
  card.querySelectorAll('.tl-edit').forEach((btn) => {
    btn.addEventListener('click', () => {
      const label = btn.closest('.tl-label');
      const sid = +label.dataset.sid;
      const current = speakerName(buildSpeakerMap(j.result), sid, loadAliases(j.id));

      const overlay = document.createElement('div');
      overlay.className = 'name-dialog-overlay';
      overlay.innerHTML = `
        <div class="name-dialog" role="dialog" aria-label="${esc(t('renameAria'))}">
          <div class="name-dialog-title">${esc(t('renameTitle', { name: current }))}</div>
          <input class="name-dialog-input" type="text" maxlength="24"
                 placeholder="${esc(t('renamePlaceholder'))}">
          <div class="name-dialog-actions">
            <button class="btn mini name-dialog-cancel">${esc(t('btnCancelMini'))}</button>
            <button class="btn mini primary name-dialog-ok">${esc(t('btnOk'))}</button>
          </div>
        </div>`;
      document.body.appendChild(overlay);
      const input = overlay.querySelector('.name-dialog-input');
      input.value = loadAliases(j.id).get(sid) ?? '';
      input.focus();
      input.select();

      const close = () => overlay.remove();
      const commit = () => {
        const val = input.value.trim();
        const aliases = loadAliases(j.id);
        if (val) aliases.set(sid, val);
        else aliases.delete(sid);
        saveAliases(j.id, aliases);
        const name = speakerName(buildSpeakerMap(j.result), sid, aliases);
        label.querySelector('.tl-name').textContent = name;
        card.querySelectorAll(`.seg-speaker[data-sid="${sid}"]`)
          .forEach((el) => { el.textContent = name; });
        close();
      };
      overlay.querySelector('.name-dialog-ok').addEventListener('click', commit);
      overlay.querySelector('.name-dialog-cancel').addEventListener('click', close);
      overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
      overlay.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') commit();
        else if (e.key === 'Escape') close();
      });
    });
  });
}

function renderJobs() {
  const wrap = $('jobs');
  const seen = new Set();
  for (const j of jobs) {
    seen.add(j.id);
    const sig = jobSig(j);
    let entry = jobEls.get(j.id);
    if (!entry || entry.sig !== sig) {
      // 毫秒开关是纯 UI 状态（不在 jobSig 里）：重建卡片时从旧 DOM 继承
      const prevMs = entry ? entry.el.querySelector('.ms-toggle input')?.checked : false;
      const holder = document.createElement('div');
      holder.innerHTML = jobCard(j, prevMs);
      const card = holder.firstElementChild;
      if (entry) entry.el.replaceWith(card);
      else wrap.appendChild(card);
      entry = { el: card, sig };
      jobEls.set(j.id, entry);
      wirePlayer(card, j);
    } else {
      // 已用时是唯一每秒变化的字段，单独更新文本节点
      const elapsed = entry.el.querySelector('[data-elapsed]');
      if (elapsed && j.started) {
        elapsed.textContent = fmtSec((Date.now() / 1000) - j.started);
      }
    }
  }
  for (const [id, entry] of jobEls) {
    if (!seen.has(id)) {
      entry.el.remove();
      jobEls.delete(id);
    }
  }
  // 顺序变化时才移动节点（移动不重置滚动）
  const current = [...wrap.children];
  const desired = jobs.map((j) => jobEls.get(j.id)?.el).filter(Boolean);
  if (desired.length === current.length && desired.some((el, i) => el !== current[i])) {
    for (const el of desired) wrap.appendChild(el);
  }
}

function jobCard(j, msPrecision = false) {
  const active = ['queued', 'converting', 'running'].includes(j.status);
  const label = statusLabel(j.status);
  const badgeText = j.status === 'queued' && j.queue_position > 1
    ? t('queuedPos', { n: j.queue_position }) : label + (j.detail ? ` · ${detailLabel(j.detail)}` : '');

  const meta = [];
  if (j.audio_ms) meta.push(t('metaDuration', { dur: fmtMsZh(j.audio_ms) }));
  if (j.status === 'running' && j.started) {
    meta.push({ html: `${esc(t('metaElapsedPrefix'))} <span data-elapsed>${fmtSec((Date.now() / 1000) - j.started)}</span>` });
  }
  if (j.status === 'done' && j.started && j.finished) meta.push(t('metaTook', { dur: fmtSec(j.finished - j.started) }));
  meta.push(j.params.diarize === 'on' ? t('diarizeOn') : t('diarizeOff'));

  let actions = '';
  if (active) actions = `<button class="btn mini danger" data-action="cancel">${esc(t('btnCancel'))}</button>`;
  else actions = `<button class="btn mini" data-action="delete">${esc(t('btnDelete'))}</button>`;

  return `
  <div class="card job" data-id="${j.id}">
    <div class="job-head">
      <div class="job-title" title="${esc(j.filename)}">📁 ${esc(j.filename)}</div>
      <span class="badge ${j.status}">${esc(badgeText)}</span>
      ${actions}
    </div>
    <div class="job-meta">${meta.map((m) => `<span class="dot">${typeof m === 'string' ? esc(m) : m.html}</span>`).join('')}</div>
    ${j.error ? `<div class="error-box">${esc(j.error)}</div>` : ''}
    ${j.result ? resultBlock(j, msPrecision) : ''}
  </div>`;
}

function resultBlock(j, cardMs = false) {
  const r = j.result;
  const withDiarize = j.params.diarize === 'on';
  // timestamps='none' 时后端返回全零时间戳：隐藏时间列/时间轴/SRT，导出去掉时间前缀
  const noTs = j.params.timestamps === 'none';
  const hasAudio = !!j.has_audio;
  const spMap = buildSpeakerMap(r);
  const aliases = loadAliases(j.id);

  const meta = [
    tn('metaSegs', { n: r.segments.length }),
    noTs ? t('metaNoTs') : null,
    withDiarize && spMap.size ? tn('metaSpeakers', { n: spMap.size }) : null,
    t('metaDecode', { v: (r.timings.decode_ms / 1000).toFixed(1) }),
    t('metaEncode', { v: (r.timings.encode_ms / 1000).toFixed(1) }),
  ].filter(Boolean).join(' · ');

  const segs = r.segments.length ? r.segments.map((s) => `
    <div class="seg">
      ${hasAudio && !noTs ? `<button class="seg-play" data-t0="${s.t0_ms}" title="${esc(t('segPlayTitle'))}">▶</button>` : ''}
      ${noTs ? '' : `<span class="seg-time" data-t0="${s.t0_ms}" data-t1="${s.t1_ms}">${fmtClockMs(s.t0_ms, cardMs)} → ${fmtClockMs(s.t1_ms, cardMs)}</span>`}
      ${withDiarize ? `<span class="seg-speaker" data-sid="${s.speaker_id}" style="--sp:${speakerColor(spMap.get(s.speaker_id) ?? 1)}">${esc(speakerName(spMap, s.speaker_id, aliases))}</span>` : ''}
      <span class="seg-text">${esc(s.text)}</span>
    </div>`).join('')
    : `<div class="seg"><span class="seg-text">${esc(r.text)}</span></div>`;

  return `
  <div class="result">
    <div class="result-meta">${esc(meta)}${j.detail ? ` · ${esc(detailLabel(j.detail))}` : ''}</div>
    ${hasAudio ? `
    <div class="player">
      <button class="btn mini player-toggle" title="Play/Pause">▶</button>
      <input class="player-seek" type="range" min="0" max="${j.audio_ms || 0}" value="0" step="50">
      <span class="player-time">0:00 / ${fmtClock(j.audio_ms || 0)}</span>
      <audio class="job-audio" src="/api/jobs/${esc(j.id)}/audio" preload="none"></audio>
    </div>` : ''}
    ${withDiarize && !noTs ? timeline(r, spMap, cardMs, aliases) : ''}
    <div class="result-actions">
      <button class="btn mini" data-action="copy">${esc(t('btnCopy'))}</button>
      <button class="btn mini" data-action="txt">${esc(t('btnTxt'))}</button>
      ${noTs || !r.segments.length ? '' : `<button class="btn mini" data-action="srt">${esc(t('btnSrt'))}</button>`}
      <button class="btn mini" data-action="json">${esc(t('btnJson'))}</button>
      ${noTs || !r.segments.length ? '' : `
      <label class="ms-toggle${cardMs ? ' on' : ''}" title="Timestamp precision">
        <span class="ms-toggle-track"><span class="ms-toggle-knob"></span></span>
        <span class="ms-toggle-text">${esc(t('msToggleText'))}</span>
        <input type="checkbox"${cardMs ? ' checked' : ''} hidden>
      </label>`}
    </div>
    <div class="seg-list">${segs}</div>
  </div>`;
}

function timeline(r, spMap, ms = false, aliases = null) {
  const segs = r.speaker_segments || [];
  if (!segs.length) return '';
  const dur = Math.max(...segs.map((s) => s.t1_ms), 1);
  const rows = new Map();
  for (const s of segs) {
    if (!rows.has(s.speaker_id)) rows.set(s.speaker_id, []);
    rows.get(s.speaker_id).push(s);
  }
  const bars = [...rows.entries()].sort((a, b) => a[0] - b[0]).map(([sid, list]) => {
    const num = spMap.get(sid) ?? 1;
    return `
    <div class="tl-row">
      <div class="tl-label" data-sid="${sid}"><span class="tl-name">${esc(speakerName(spMap, sid, aliases))}</span><button class="tl-edit" title="${esc(t('tlEditTitle'))}">✎</button></div>
      <div class="tl-track">${list.map((s) =>
        `<div class="tl-bar" style="left:${(s.t0_ms / dur * 100).toFixed(2)}%;width:${Math.max((s.t1_ms - s.t0_ms) / dur * 100, 0.3).toFixed(2)}%;background:${speakerColor(num)}"
              data-t0="${s.t0_ms}" data-t1="${s.t1_ms}"${s.p != null ? ` data-p="${s.p}"` : ''}
              title="${fmtClockMs(s.t0_ms, ms)} – ${fmtClockMs(s.t1_ms, ms)}${s.p != null ? `（置信度 ${(s.p * 100).toFixed(0)}%）` : ''}"></div>`).join('')}</div>
    </div>`;
  }).join('');
  return `<div class="timeline">${bars}</div>`;
}

// ---- 导出 ----
// ms：跟随结果卡片的毫秒开关（按钮所在卡片的 data-ms）

function segLine(s, withDiarize, spMap, noTs, ms = false, aliases = null) {
  const time = noTs ? '' : `[${fmtClockMs(s.t0_ms, ms)} → ${fmtClockMs(s.t1_ms, ms)}] `;
  const sp = withDiarize ? `${speakerName(spMap, s.speaker_id, aliases)}: ` : '';
  return `${time}${sp}${s.text}`;
}

function fullText(j, ms = false) {
  if (!j.result.segments.length) return j.result.text;
  const withDiarize = j.params.diarize === 'on';
  const noTs = j.params.timestamps === 'none';
  const spMap = buildSpeakerMap(j.result);
  const aliases = loadAliases(j.id);
  return j.result.segments.map((s) => segLine(s, withDiarize, spMap, noTs, ms, aliases)).join('\n');
}

function srtTime(ms) {
  const h = Math.floor(ms / 3600000), m = Math.floor(ms % 3600000 / 60000);
  const s = Math.floor(ms % 60000 / 1000), milli = Math.round(ms % 1000);
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')},${String(milli).padStart(3, '0')}`;
}

function toSRT(j) {
  const withDiarize = j.params.diarize === 'on';
  const spMap = buildSpeakerMap(j.result);
  const aliases = loadAliases(j.id);
  return j.result.segments.map((s, i) => {
    const sp = withDiarize ? `${speakerName(spMap, s.speaker_id, aliases)}: ` : '';
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

// 批量模式：开关只决定"能否一次选多个"；多选后逐个走同样的上传队列
const batchToggle = $('batch-toggle');
const batchInput = batchToggle.querySelector('input');
batchInput.addEventListener('change', () => {
  batchToggle.classList.toggle('on', batchInput.checked);
  $('file-input').multiple = batchInput.checked;
});

$('dropzone').addEventListener('click', () => $('file-input').click());
$('file-input').addEventListener('change', (e) => {
  const list = [...e.target.files];
  if (!list.length) return setFiles(null);
  setFiles(batchInput.checked ? list : [list[0]]);
});
$('file-clear').addEventListener('click', () => setFiles(null));
$('start-btn').addEventListener('click', startTranscribe);
$('reload-btn').addEventListener('click', switchDevice);

const dz = $('dropzone');
['dragenter', 'dragover'].forEach((ev) =>
  dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add('drag'); }));
['dragleave', 'drop'].forEach((ev) =>
  dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove('drag'); }));
dz.addEventListener('drop', (e) => {
  const list = [...e.dataTransfer.files];
  if (!list.length) return;
  setFiles(batchInput.checked ? list : [list[0]]);
});

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
        toast(t('toastCancelled'));
        break;
      case 'delete':
        await api(`/api/jobs/${id}/delete`, { method: 'POST' });
        try { localStorage.removeItem(`spk-${id}`); } catch { /* 存储被禁 */ }
        break;
      case 'copy':
        await navigator.clipboard.writeText(fullText(job, btn.closest('.result')?.querySelector('.ms-toggle input')?.checked));
        toast(t('toastCopied'));
        break;
      case 'txt':
        download(`${baseName(job)}.txt`, fullText(job, btn.closest('.result')?.querySelector('.ms-toggle input')?.checked));
        break;
      case 'srt':
        download(`${baseName(job)}.srt`, toSRT(job));
        break;
      case 'json':
        download(`${baseName(job)}.json`, JSON.stringify(job, null, 2));
        break;
    }
  } catch (err) {
    toast(t('toastOpFail', { msg: err.message }), true);
  }
  pollNow();
});

// ---- 启动 ----

// 语言切换：重写静态文案并全量重建动态卡片（jobSig 加 lang，卡片必刷新）
$('lang-btn').addEventListener('click', () => {
  lang = lang === 'zh' ? 'en' : 'zh';
  try { localStorage.setItem('lang', lang); } catch { /* 存储被禁 */ }
  applyStaticTexts();
  if (status) renderStatus();
  renderJobs(); // jobSig 已含 lang，所有卡片自动按新语言重建
});

$('dz-hint').textContent = t('dzHint');
applyStaticTexts();
poll();
