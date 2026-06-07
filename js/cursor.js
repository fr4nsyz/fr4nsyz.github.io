const canvas = document.getElementById('cursor-canvas');
const isDesktop = window.matchMedia('(hover: hover) and (pointer: fine)').matches;
if (!isDesktop) {
  canvas.style.display = 'none';
} else {
  const ctx = canvas.getContext('2d', { alpha: true });

  let W = window.innerWidth;
  let H = window.innerHeight;

  function resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    W = window.innerWidth;
    H = window.innerHeight;
    canvas.width = W * dpr;
    canvas.height = H * dpr;
    canvas.style.width = W + 'px';
    canvas.style.height = H + 'px';
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  resize();
  window.addEventListener('resize', resize, { passive: true });

  const trail = [];
  const TRAIL_LENGTH = 20;
  let mouseX = W / 2;
  let mouseY = H / 2;
  let targetX = mouseX;
  let targetY = mouseY;

  document.addEventListener('mousemove', (e) => {
    targetX = e.clientX;
    targetY = e.clientY;
  });

  function bleedNoise(t) {
    return Math.sin(t * 0.1) * 0.5 + Math.sin(t * 0.2) * 0.3 + Math.sin(t * 0.3) * 0.2;
  }

  function drawCursor(x, y, t) {
    const size = 6 + Math.sin(t * 0.5) * 2;
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(t * 0.3);

    const grd = ctx.createRadialGradient(0, 0, 0, 0, 0, size * 3);
    grd.addColorStop(0, 'rgba(255, 42, 42, 0.6)');
    grd.addColorStop(0.5, 'rgba(180, 10, 10, 0.2)');
    grd.addColorStop(1, 'rgba(100, 0, 0, 0)');
    ctx.fillStyle = grd;
    ctx.fillRect(-size * 3, -size * 3, size * 6, size * 6);

    ctx.beginPath();
    ctx.moveTo(0, -size);
    ctx.lineTo(size * 0.6, 0);
    ctx.lineTo(0, size);
    ctx.lineTo(-size * 0.6, 0);
    ctx.closePath();
    ctx.fillStyle = 'rgba(255, 50, 50, 0.9)';
    ctx.fill();

    ctx.restore();
  }

  function drawTrail() {
    if (trail.length < 2) return;

    for (let i = 1; i < trail.length; i++) {
      const curr = trail[i];
      const prev = trail[i - 1];
      const progress = i / trail.length;
      const alpha = progress * 0.5;
      const width = progress * 3 + 1;

      const wobble = bleedNoise(Date.now() * 0.001 + i * 0.5) * 2;

      ctx.beginPath();
      ctx.moveTo(prev.x + wobble, prev.y);
      ctx.lineTo(curr.x + wobble, curr.y);
      ctx.strokeStyle = 'rgba(200, 20, 20, ' + alpha + ')';
      ctx.lineWidth = width;
      ctx.lineCap = 'round';
      ctx.stroke();
    }
  }

  function update() {
    const t = Date.now() * 0.001;

    mouseX += (targetX - mouseX) * 0.15;
    mouseY += (targetY - mouseY) * 0.15;

    ctx.clearRect(0, 0, W, H);

    trail.push({ x: mouseX, y: mouseY });
    if (trail.length > TRAIL_LENGTH) trail.shift();

    drawTrail();
    drawCursor(mouseX, mouseY, t);
  }

  function run() {
    update();
    requestAnimationFrame(run);
  }

  run();
}
