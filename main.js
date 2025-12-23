// main.js - 15:10 Crop + Hex Guide Web

const ASPECT_W = 15;
const ASPECT_H = 10;
const ASPECT = ASPECT_W / ASPECT_H;

let images = [];
let imageIndex = 0;
let ignoredIndices = new Set();
let savedCrops = {};
let cropRect = null;
let dragging = false;
let dragStart = {x: 0, y: 0};
let outputDir = null;
let hexRotate = true;
let drawHexOnExport = false;
let sizePercent = 85;

const fileInput = document.getElementById('fileInput');
const prevBtn = document.getElementById('prevBtn');
const nextBtn = document.getElementById('nextBtn');
const exportBtn = document.getElementById('exportBtn');
const ignoreBtn = document.getElementById('ignoreBtn');
const hexRotateCheckbox = document.getElementById('hexRotate');
const drawHexCheckbox = document.getElementById('drawHex');
const sizeRange = document.getElementById('sizeRange');
const infoText = document.getElementById('infoText');
const statusText = document.getElementById('statusText');
const canvas = document.getElementById('mainCanvas');
const ctx = canvas.getContext('2d');
const langBtns = document.querySelectorAll('.lang-btn');
const helpBtn = document.getElementById('helpBtn');
const helpModal = document.getElementById('helpModal');
const helpClose = document.getElementById('helpClose');
const helpText = document.getElementById('helpText');
const slideshow = document.getElementById('exportedSlideshow');

let currentLang = 'hu';
const i18n = {
  hu: {
    prev: 'Előző',
    next: 'Következő',
    export: 'Exportálás',
    ignore: 'Kihagyás',
    hexRotate: 'Hex forgatás 30°',
    drawHex: 'Hex rajzolás exportnál',
    cropSize: 'Crop méret:',
    infoNone: 'Nincs kép betöltve',
    status: 'Fogd meg a crop keretet (vagy a képet) és mozgasd! A crop keret a nyilakkal is mozgatható. Használd a csúszkát és a hex opciókat!',
    ignored: 'Kihagyva:',
    allIgnored: 'Minden kép kihagyva.',
    cropError: 'Hibás crop keret.',
    exported: 'Exportálva:',
    help: 'Hogyan működik?',
    helpContent: `<h2>Mi ez a tool?</h2><p>Ez az eszköz abban segít, hogy 15:10-es arányú képrészleteket tudj kivágni, amelyeket később hexagonális képkeretbe könnyen be tudsz illeszteni. Az exportált képen opcionálisan hexagonális segédvonal is megjeleníthető, így kinyomtatva a kép a segédvonal mentén könnyen kivágható. A vágott képeket letöltheted, és a vágás során a crop keretet mozgathatod, méretezheted.</p><h3>Használat:</h3><ul><li>Tölts fel egy vagy több képet.</li><li>Fogd meg a crop keretet vagy a képet, és mozgasd az egérrel, vagy használd a nyilakat.</li><li>A csúszkával állíthatod a crop méretét.</li><li>Exportáláskor a vágott kép letölthető lesz, és megjelenik a lenti galériában is.</li><li>Beállíthatod, hogy legyen-e hexagon overlay, és hogy az exportált képen is rajzoljon-e hexet.</li></ul>`
  },
  en: {
    prev: 'Previous',
    next: 'Next',
    export: 'Export',
    ignore: 'Ignore',
    hexRotate: 'Hex rotate 30°',
    drawHex: 'Draw hex on export',
    cropSize: 'Crop size:',
    infoNone: 'No image loaded',
    status: 'Grab and move the crop frame (or the image)! You can also use arrow keys. Use the slider and hex options!',
    ignored: 'Ignored:',
    allIgnored: 'All images are ignored.',
    cropError: 'Invalid crop rectangle.',
    exported: 'Exported:',
    help: 'How does it work?',
    helpContent: `<h2>What is this tool?</h2><p>This tool lets you crop images to a 15:10 rectangle and optionally draw a hexagonal guide. You can download the cropped images, and move/resize the crop frame as needed.</p><h3>Usage:</h3><ul><li>Upload one or more images.</li><li>Grab the crop frame or the image and move it with the mouse, or use the arrow keys.</li><li>Use the slider to change crop size.</li><li>On export, the cropped image will be downloadable and shown in the gallery below.</li><li>You can enable hex overlay and drawing on export as well.</li></ul>`
  }
};

function setLang(lang) {
  currentLang = lang;
  langBtns.forEach(btn => btn.classList.toggle('active', btn.dataset.lang === lang));
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.getAttribute('data-i18n');
    if (i18n[lang][key]) el.textContent = i18n[lang][key];
  });
  helpBtn.title = i18n[lang].help;
  helpText.innerHTML = i18n[lang].helpContent;
  updateInfo();
  updateStatus();
}

langBtns.forEach(btn => {
  btn.addEventListener('click', () => setLang(btn.dataset.lang));
});

helpBtn.addEventListener('click', () => {
  helpModal.style.display = 'flex';
});
helpClose.addEventListener('click', () => {
  helpModal.style.display = 'none';
});
window.addEventListener('click', (e) => {
  if (e.target === helpModal) helpModal.style.display = 'none';
});

function resetState() {
  images = [];
  imageIndex = 0;
  ignoredIndices = new Set();
  savedCrops = {};
  cropRect = null;
}

fileInput.addEventListener('change', (e) => {
  resetState();
  const files = Array.from(e.target.files);
  if (!files.length) return;
  Promise.all(files.map(f => loadImageFile(f))).then(imgs => {
    images = imgs;
    imageIndex = 0;
    cropRect = null;
    updateCropRect();
    redraw();
    updateInfo();
    updateStatus();
  });
});

function loadImageFile(file) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve({img, name: file.name});
    img.onerror = reject;
    img.src = URL.createObjectURL(file);
  });
}

prevBtn.addEventListener('click', () => {
  saveCurrentCrop();
  let idx = findNextIndex(imageIndex, -1);
  if (idx !== null) {
    imageIndex = idx;
    cropRect = null;
    updateCropRect();
    redraw();
    updateInfo();
  }
});

nextBtn.addEventListener('click', () => {
  saveCurrentCrop();
  let idx = findNextIndex(imageIndex, 1);
  if (idx !== null) {
    imageIndex = idx;
    cropRect = null;
    updateCropRect();
    redraw();
    updateInfo();
  }
});

ignoreBtn.addEventListener('click', () => {
  saveCurrentCrop();
  ignoredIndices.add(imageIndex);
  statusText.textContent = `${i18n[currentLang].ignored} ${images[imageIndex]?.name || ''}`;
  let idx = findNextIndex(imageIndex, 1);
  if (idx !== null) {
    imageIndex = idx;
    cropRect = null;
    updateCropRect();
    redraw();
    updateInfo();
    updateStatus();
  } else {
    infoText.textContent = i18n[currentLang].allIgnored;
  }
});

function findNextIndex(start, step) {
  if (!images.length) return null;
  let n = images.length;
  let idx = start;
  for (let i = 0; i < n; ++i) {
    idx = (idx + step + n) % n;
    if (!ignoredIndices.has(idx)) return idx;
  }
  return null;
}

hexRotateCheckbox.addEventListener('change', () => {
  hexRotate = hexRotateCheckbox.checked;
  clampCropToHex();
  redraw();
  updateInfo();
});
drawHexCheckbox.addEventListener('change', () => {
  drawHexOnExport = drawHexCheckbox.checked;
});
sizeRange.addEventListener('input', () => {
  sizePercent = parseInt(sizeRange.value);
  updateCropRect();
  redraw();
  updateInfo();
});


// Egér események
canvas.addEventListener('mousedown', (e) => {
  if (!cropRect) return;
  const rect = canvas.getBoundingClientRect();
  const x = e.clientX - rect.left;
  const y = e.clientY - rect.top;
  if (pointInRect(x, y, cropRect) || pointInRect(x, y, {left:0,top:0,right:canvas.width,bottom:canvas.height})) {
    dragging = true;
    dragStart.x = x;
    dragStart.y = y;
    canvas.style.cursor = 'grabbing';
  }
});
canvas.addEventListener('mousemove', (e) => {
  if (!dragging || !cropRect) return;
  const rect = canvas.getBoundingClientRect();
  const x = e.clientX - rect.left;
  const y = e.clientY - rect.top;
  const dx = x - dragStart.x;
  const dy = y - dragStart.y;
  dragStart.x = x;
  dragStart.y = y;
  cropRect.left += dx;
  cropRect.right += dx;
  cropRect.top += dy;
  cropRect.bottom += dy;
  clampCropToHex();
  redraw();
  updateInfo();
});
canvas.addEventListener('mouseup', () => {
  dragging = false;
  canvas.style.cursor = 'default';
});
canvas.addEventListener('mouseleave', () => {
  dragging = false;
  canvas.style.cursor = 'default';
});

// Touch események mobilhoz
canvas.addEventListener('touchstart', (e) => {
  if (!cropRect) return;
  if (e.touches.length !== 1) return;
  const rect = canvas.getBoundingClientRect();
  const touch = e.touches[0];
  const x = touch.clientX - rect.left;
  const y = touch.clientY - rect.top;
  if (pointInRect(x, y, cropRect) || pointInRect(x, y, {left:0,top:0,right:canvas.width,bottom:canvas.height})) {
    dragging = true;
    dragStart.x = x;
    dragStart.y = y;
    e.preventDefault();
  }
}, {passive: false});
canvas.addEventListener('touchmove', (e) => {
  if (!dragging || !cropRect) return;
  if (e.touches.length !== 1) return;
  const rect = canvas.getBoundingClientRect();
  const touch = e.touches[0];
  const x = touch.clientX - rect.left;
  const y = touch.clientY - rect.top;
  const dx = x - dragStart.x;
  const dy = y - dragStart.y;
  dragStart.x = x;
  dragStart.y = y;
  cropRect.left += dx;
  cropRect.right += dx;
  cropRect.top += dy;
  cropRect.bottom += dy;
  clampCropToHex();
  redraw();
  updateInfo();
  e.preventDefault();
}, {passive: false});
canvas.addEventListener('touchend', () => {
  dragging = false;
});

function pointInRect(x, y, rect) {
  return x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom;
}

function saveCurrentCrop() {
  if (!images.length || !cropRect) return;
  savedCrops[imageIndex] = {...cropRect};
}

function updateCropRect() {
  if (!images.length) return;
  const {img} = images[imageIndex];
  const w = img.width;
  const h = img.height;
  const maxCrop = maxCropWH(w, h);
  const scale = sizePercent / 100.0;
  const cropW = maxCrop.w * scale;
  const cropH = maxCrop.h * scale;
  const cx = w / 2;
  const cy = h / 2;
  cropRect = {
    left: cx - cropW / 2,
    right: cx + cropW / 2,
    top: cy - cropH / 2,
    bottom: cy + cropH / 2
  };
  clampCropToHex();
}

function maxCropWH(w, h) {
  if (w / h >= ASPECT) {
    return {w: h * ASPECT, h: h};
  } else {
    return {w: w, h: w / ASPECT};
  }
}

function clampCropToHex() {
  if (!images.length || !cropRect) return;
  const {img} = images[imageIndex];
  const w = img.width;
  const h = img.height;
  let rectW = cropRect.right - cropRect.left;
  let rectH = cropRect.bottom - cropRect.top;
  let cx = (cropRect.left + cropRect.right) / 2;
  let cy = (cropRect.top + cropRect.bottom) / 2;
  let r = hexRFromRect(rectW, rectH);
  let rGlobalMax = hexRGlobalMax(w, h);
  if (r > rGlobalMax && r > 0) {
    let factor = rGlobalMax / r;
    rectW *= factor;
    rectH *= factor;
    r = hexRFromRect(rectW, rectH);
  }
  [cx, cy] = clampCenterForHex(cx, cy, r, w, h);
  cropRect.left = cx - rectW / 2;
  cropRect.right = cx + rectW / 2;
  cropRect.top = cy - rectH / 2;
  cropRect.bottom = cy + rectH / 2;
}

function hexRotationDegrees() {
  return hexRotate ? 30 : 0;
}
function hexUnitVectors() {
  const rot = hexRotationDegrees();
  let vecs = [];
  for (let k = 0; k < 6; ++k) {
    let angle = (-90 + rot + k * 60) * Math.PI / 180;
    vecs.push([Math.cos(angle), Math.sin(angle)]);
  }
  return vecs;
}
function hexRFromRect(rectW, rectH) {
  const rot = hexRotationDegrees();
  if (Math.abs(rot - 30) < 1e-6) {
    return Math.min(rectW / 2, rectH / Math.sqrt(3));
  }
  return Math.min(rectH / 2, rectW / Math.sqrt(3));
}
function hexRGlobalMax(w, h) {
  const rot = hexRotationDegrees();
  if (Math.abs(rot - 30) < 1e-6) {
    return Math.min(w / 2, h / Math.sqrt(3));
  }
  return Math.min(h / 2, w / Math.sqrt(3));
}
function clampCenterForHex(cx, cy, r, w, h) {
  let minCx = 0, maxCx = w, minCy = 0, maxCy = h;
  for (const [ux, uy] of hexUnitVectors()) {
    if (ux > 1e-12) {
      minCx = Math.max(minCx, r * ux);
      maxCx = Math.min(maxCx, w - r * ux);
    } else if (ux < -1e-12) {
      minCx = Math.max(minCx, -r * ux);
      maxCx = Math.min(maxCx, w + r * ux);
    }
    if (uy > 1e-12) {
      minCy = Math.max(minCy, r * uy);
      maxCy = Math.min(maxCy, h - r * uy);
    } else if (uy < -1e-12) {
      minCy = Math.max(minCy, -r * uy);
      maxCy = Math.min(maxCy, h + r * uy);
    }
  }
  if (minCx > maxCx) minCx = maxCx = w / 2;
  if (minCy > maxCy) minCy = maxCy = h / 2;
  cx = Math.min(Math.max(cx, minCx), maxCx);
  cy = Math.min(Math.max(cy, minCy), maxCy);
  return [cx, cy];
}

function redraw() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!images.length) {
    ctx.fillStyle = '#ccc';
    ctx.font = '16px Segoe UI';
    ctx.fillText('Tölts fel képeket…', 20, 40);
    return;
  }
  const {img} = images[imageIndex];
  // Méretezzük a canvas-t a képhez
  canvas.width = img.width;
  canvas.height = img.height;
  ctx.drawImage(img, 0, 0);
  if (!cropRect) return;
  // Crop rect
  ctx.save();
  ctx.strokeStyle = '#fff';
  ctx.lineWidth = 2;
  ctx.strokeRect(cropRect.left, cropRect.top, cropRect.right - cropRect.left, cropRect.bottom - cropRect.top);
  ctx.setLineDash([4, 4]);
  ctx.strokeStyle = '#bbb';
  ctx.lineWidth = 1;
  ctx.strokeRect(cropRect.left, cropRect.top, cropRect.right - cropRect.left, cropRect.bottom - cropRect.top);
  ctx.setLineDash([]);
  // Dim outside crop
  ctx.globalAlpha = 0.5;
  ctx.fillStyle = '#000';
  ctx.beginPath();
  ctx.rect(0, 0, canvas.width, cropRect.top);
  ctx.rect(0, cropRect.bottom, canvas.width, canvas.height - cropRect.bottom);
  ctx.rect(0, cropRect.top, cropRect.left, cropRect.bottom - cropRect.top);
  ctx.rect(cropRect.right, cropRect.top, canvas.width - cropRect.right, cropRect.bottom - cropRect.top);
  ctx.fill();
  ctx.globalAlpha = 1.0;
  // Hex guide
  drawHexGuide(cropRect.left, cropRect.top, cropRect.right, cropRect.bottom);
  ctx.restore();
}

function drawHexGuide(x0, y0, x1, y1) {
  const cx = (x0 + x1) / 2;
  const cy = (y0 + y1) / 2;
  const w = x1 - x0;
  const h = y1 - y0;
  const r = hexRFromRect(w, h);
  const rot = hexRotationDegrees();
  let pts = [];
  for (let k = 0; k < 6; ++k) {
    let angle = (-90 + rot + k * 60) * Math.PI / 180;
    pts.push([cx + r * Math.cos(angle), cy + r * Math.sin(angle)]);
  }
  ctx.save();
  ctx.strokeStyle = '#d0d0d0';
  ctx.lineWidth = 2;
  ctx.setLineDash([6, 4]);
  ctx.beginPath();
  ctx.moveTo(pts[0][0], pts[0][1]);
  for (let i = 1; i < pts.length; ++i) ctx.lineTo(pts[i][0], pts[i][1]);
  ctx.closePath();
  ctx.stroke();
  ctx.restore();
}

exportBtn.addEventListener('click', () => {
  if (!images.length || !cropRect) return;
  const {img, name} = images[imageIndex];
  const left = Math.round(cropRect.left);
  const top = Math.round(cropRect.top);
  const right = Math.round(cropRect.right);
  const bottom = Math.round(cropRect.bottom);
  if (right <= left || bottom <= top) {
    statusText.textContent = i18n[currentLang].cropError;
    return;
  }
  const outW = right - left;
  const outH = bottom - top;
  // Fehér háttér
  const outCanvas = document.createElement('canvas');
  outCanvas.width = outW;
  outCanvas.height = outH;
  const outCtx = outCanvas.getContext('2d');
  outCtx.fillStyle = '#fff';
  outCtx.fillRect(0, 0, outW, outH);
  // Kép beillesztése
  outCtx.drawImage(img, left, top, outW, outH, 0, 0, outW, outH);
  // Hex rajzolás
  if (drawHexOnExport) {
    const cx = outW / 2;
    const cy = outH / 2;
    const r = hexRFromRect(outW, outH);
    const rot = hexRotationDegrees();
    let pts = [];
    for (let k = 0; k < 6; ++k) {
      let angle = (-90 + rot + k * 60) * Math.PI / 180;
      pts.push([cx + r * Math.cos(angle), cy + r * Math.sin(angle)]);
    }
    outCtx.save();
    outCtx.strokeStyle = '#c8c8c8';
    outCtx.lineWidth = Math.max(2, Math.round(Math.min(outW, outH) / 400));
    outCtx.beginPath();
    outCtx.moveTo(pts[0][0], pts[0][1]);
    for (let i = 1; i < pts.length; ++i) outCtx.lineTo(pts[i][0], pts[i][1]);
    outCtx.closePath();
    outCtx.stroke();
    outCtx.restore();
  }
  // Letöltés
  outCanvas.toBlob(blob => {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `${name.replace(/\.[^.]+$/, '')}_15x10.png`;
    a.click();
    statusText.textContent = `${i18n[currentLang].exported} ${a.download}`;
    // Slideshow-hoz hozzáadjuk
    const imgEl = document.createElement('img');
    imgEl.src = a.href;
    imgEl.alt = a.download;
    slideshow.appendChild(imgEl);
    // Automatikusan odagörgetünk a slideshow végére
    slideshow.scrollLeft = slideshow.scrollWidth;
  }, 'image/png');
});

function updateInfo() {
  if (!images.length || !cropRect) {
    infoText.textContent = i18n[currentLang].infoNone;
    return;
  }
  const {img, name} = images[imageIndex];
  const w = img.width;
  const h = img.height;
  const cw = Math.round(cropRect.right - cropRect.left);
  const ch = Math.round(cropRect.bottom - cropRect.top);
  infoText.textContent = `${name}  (${imageIndex + 1}/${images.length})   ${currentLang === 'hu' ? 'kép' : 'image'}: ${w}×${h}   crop: ${cw}×${ch}`;
}

function updateStatus() {
  statusText.textContent = i18n[currentLang].status;
}

window.addEventListener('keydown', (e) => {
  if (!cropRect) return;
  let dx = 0, dy = 0;
  if (e.key === 'ArrowLeft') dx = -10;
  if (e.key === 'ArrowRight') dx = 10;
  if (e.key === 'ArrowUp') dy = -10;
  if (e.key === 'ArrowDown') dy = 10;
  if (dx || dy) {
    cropRect.left += dx;
    cropRect.right += dx;
    cropRect.top += dy;
    cropRect.bottom += dy;
    clampCropToHex();
    redraw();
    updateInfo();
  }
});

// Első betöltéskor
setLang('hu');
redraw();
updateInfo();
updateStatus();
