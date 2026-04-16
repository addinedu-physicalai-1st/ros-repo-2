/**
 * map.js — 벡터 기반 미니어처 마트 맵 렌더링
 *
 * SLAM 이미지 없이 Canvas 2D로 직접 그림.
 * 구역 블록 + 로봇 마커 + 핀치 줌.
 */

"use strict";

const MapRenderer = (() => {
  /* ── 세계 좌표 경계 (미터) ─────────────────────────── */
  const W_MAX_X = 1.20, W_MIN_X = -0.10;
  const W_MAX_Y = 0.05, W_MIN_Y = -1.65;
  const W_SPAN_X = W_MAX_X - W_MIN_X;
  const W_SPAN_Y = W_MAX_Y - W_MIN_Y;

  /* 논리 좌표계 (고정 비율, 실제 버퍼는 CSS 크기에 맞춤) */
  const LW = 420, LH = 330;

  /* ── 구역 블록 (세계 좌표) ─────────────────────────── */
  const ZONES = [
    /* 상단 행 */
    { name: "가전제품", x1: 0.36, y1: 0.03, x2: 0.85, y2: -0.12, bg: "#dbeafe", fg: "#2563eb" },
    { name: "과자",     x1: 0.88, y1: 0.03, x2: 1.17, y2: -0.12, bg: "#fef3c7", fg: "#b45309" },
    /* 우측 열 */
    { name: "해산물",   x1: 1.03, y1: -0.14, x2: 1.17, y2: -0.44, bg: "#cffafe", fg: "#0e7490" },
    { name: "육류",     x1: 1.03, y1: -0.46, x2: 1.17, y2: -1.06, bg: "#fee2e2", fg: "#dc2626" },
    { name: "채소",     x1: 1.03, y1: -1.08, x2: 1.17, y2: -1.37, bg: "#dcfce7", fg: "#16a34a" },
    /* 중앙 선반 (실제 크기에 맞춤) */
    { name: "빵",       x1: 0.43, y1: -0.24, x2: 0.76, y2: -0.37, bg: "#ffedd5", fg: "#c2410c" },
    { name: "가공식품", x1: 0.43, y1: -0.53, x2: 0.76, y2: -0.66, bg: "#fce7f3", fg: "#be185d" },
    { name: "음료",     x1: 0.62, y1: -0.83, x2: 0.76, y2: -1.15, bg: "#ede9fe", fg: "#7c3aed" },
    /* 하단 */
    { name: "화장실",   x1: 0.95, y1: -1.39, x2: 1.17, y2: -1.58, bg: "#f1f5f9", fg: "#475569" },
    { name: "결제",     x1: 0.10, y1: -1.38, x2: 0.30, y2: -1.55, bg: "#ccfbf1", fg: "#0d9488" },
    { name: "충전",     x1: -0.07, y1: -0.50, x2: 0.08, y2: -0.95, bg: "#fefce8", fg: "#a16207" },
  ];

  const ENTRANCE_EXIT = [
    { name: "입구", wx: -0.04, wy: -0.057, arrow: "\u25B2" },
    { name: "출구", wx: -0.04, wy: -1.547, arrow: "\u25BC" },
  ];

  /* ── 상태 ──────────────────────────────────────────── */
  let canvas, ctx;
  let myRobotId = null;
  let dpr = 1;

  let myRobot = null;
  let otherRobots = [];

  let scale = 1, lastDist = null;
  let visible = false;
  let animFrameId = null;
  let pulsePhase = 0;

  const MY_COLOR    = "#3b82f6";
  const OTHER_COLOR = "#94a3b8";
  const ROBOT_R     = 9;
  const ROBOT_R_SM  = 7;

  /* ── 초기화 ────────────────────────────────────────── */
  function init(canvasId, robotId) {
    canvas = document.getElementById(canvasId);
    if (!canvas) return;
    ctx = canvas.getContext("2d");
    myRobotId = String(robotId);
    sizeBuffer();
    render();
    canvas.addEventListener("touchstart", onTouchStart, { passive: false });
    canvas.addEventListener("touchmove",  onTouchMove,  { passive: false });
    canvas.addEventListener("touchend",   onTouchEnd,   { passive: false });
  }

  /** canvas 버퍼를 CSS 표시 크기 × DPR에 맞춰 선명하게 */
  function sizeBuffer() {
    dpr = Math.min(window.devicePixelRatio || 1, 3);
    const cssW = canvas.clientWidth  || 400;
    const cssH = canvas.clientHeight || Math.round(cssW * LH / LW);
    canvas.width  = Math.round(cssW * dpr);
    canvas.height = Math.round(cssH * dpr);
  }

  /* ── 가시성 ────────────────────────────────────────── */
  function setVisible(v) {
    visible = v;
    if (v) { sizeBuffer(); render(); startAnim(); }
    else   { stopAnim(); }
  }

  function startAnim() {
    if (animFrameId) return;
    (function loop(ts) {
      pulsePhase = (ts % 2000) / 2000;
      render();
      if (visible) animFrameId = requestAnimationFrame(loop);
    })(performance.now());
  }

  function stopAnim() {
    if (animFrameId) { cancelAnimationFrame(animFrameId); animFrameId = null; }
  }

  /* ── 데이터 업데이트 ───────────────────────────────── */
  function updateFromStatus(statusMsg) {
    if (statusMsg.my_robot) {
      myRobot = statusMsg.my_robot;
    } else if (
      statusMsg.robot_id != null && statusMsg.pos_x != null &&
      myRobotId != null && String(statusMsg.robot_id) === myRobotId
    ) {
      myRobot = {
        robot_id: String(statusMsg.robot_id),
        pos_x: statusMsg.pos_x, pos_y: statusMsg.pos_y,
        yaw: statusMsg.yaw || 0,
      };
    }
    if (Array.isArray(statusMsg.other_robots)) otherRobots = statusMsg.other_robots;
    if (!animFrameId && canvas) render();
  }

  /* ── 렌더링 ────────────────────────────────────────── */
  function render() {
    if (!canvas || !ctx) return;

    /* 논리 좌표(LW×LH)를 실제 버퍼에 매핑 */
    const sx = canvas.width  / LW;
    const sy = canvas.height / LH;

    ctx.save();
    ctx.setTransform(sx, 0, 0, sy, 0, 0);

    const cx = LW / 2, cy = LH / 2;
    ctx.translate(cx, cy);
    ctx.scale(scale, scale);
    ctx.translate(-cx, -cy);

    ctx.fillStyle = "#0f172a";
    ctx.fillRect(-10, -10, LW + 20, LH + 20);

    drawFloor();
    drawZones();
    drawEntranceExit();

    /* 다른 로봇 (반투명 + ID) */
    ctx.globalAlpha = 0.4;
    otherRobots.forEach(r => {
      const [px, py] = worldToCanvas(r.pos_x, r.pos_y);
      drawRobotMarker(px, py, r.yaw || 0, OTHER_COLOR, ROBOT_R_SM);
      drawRobotLabel(px, py, String(r.robot_id), ROBOT_R_SM);
    });
    ctx.globalAlpha = 1.0;

    /* 내 로봇 */
    if (myRobot) {
      const [px, py] = worldToCanvas(myRobot.pos_x, myRobot.pos_y);
      drawMyRobotMarker(px, py, myRobot.yaw || 0);
    }

    ctx.restore();
  }

  /* ── 마트 바닥 ─────────────────────────────────────── */
  function drawFloor() {
    const pad = 8;
    roundRect(pad, pad, LW - 2 * pad, LH - 2 * pad, 10);
    ctx.fillStyle = "#f1f5f9";
    ctx.fill();
    ctx.strokeStyle = "#475569";
    ctx.lineWidth = 2.5;
    ctx.stroke();
  }

  /* ── 구역 블록 ─────────────────────────────────────── */
  function drawZones() {
    ZONES.forEach(z => {
      const [px1, py1] = worldToCanvas(z.x2, z.y1);
      const [px2, py2] = worldToCanvas(z.x1, z.y2);
      const w = px2 - px1, h = py2 - py1;

      roundRect(px1 + 1, py1 + 1, w - 2, h - 2, 5);
      ctx.fillStyle = z.bg;
      ctx.fill();
      ctx.strokeStyle = z.fg + "30";
      ctx.lineWidth = 1;
      ctx.stroke();

      const maxFs = Math.min(w * 0.8 / Math.max(z.name.length, 1), h * 0.45);
      const fs = Math.max(5, Math.min(13, maxFs) / scale);
      ctx.font = `700 ${fs}px "Pretendard", system-ui, sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillStyle = z.fg;
      ctx.fillText(z.name, px1 + w / 2, py1 + h / 2);
    });
  }

  /* ── 입구/출구 ─────────────────────────────────────── */
  function drawEntranceExit() {
    ENTRANCE_EXIT.forEach(m => {
      const [px, py] = worldToCanvas(m.wx, m.wy);
      const fs = Math.max(5, 8 / scale);
      ctx.font = `600 ${fs}px "Pretendard", system-ui, sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillStyle = "#475569";
      ctx.fillText(m.arrow + " " + m.name, px, py);
    });
  }

  /* ── 로봇 마커 (공통) ──────────────────────────────── */
  function drawRobotMarker(px, py, yaw, color, r) {
    const angle = -yaw - Math.PI / 2;

    ctx.beginPath();
    ctx.arc(px, py, r, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();
    ctx.strokeStyle = "rgba(255,255,255,0.9)";
    ctx.lineWidth = 1.5;
    ctx.stroke();

    const tipLen = r + 4;
    const tipX = px + Math.cos(angle) * tipLen;
    const tipY = py + Math.sin(angle) * tipLen;
    const baseOff = Math.PI * 0.72;
    ctx.beginPath();
    ctx.moveTo(tipX, tipY);
    ctx.lineTo(px + Math.cos(angle + baseOff) * r * 0.7,
               py + Math.sin(angle + baseOff) * r * 0.7);
    ctx.lineTo(px + Math.cos(angle - baseOff) * r * 0.7,
               py + Math.sin(angle - baseOff) * r * 0.7);
    ctx.closePath();
    ctx.fillStyle = color;
    ctx.fill();
  }

  /* ── 로봇 ID 라벨 (공통) ───────────────────────────── */
  function drawRobotLabel(px, py, id, r) {
    const fs = Math.max(5, 7 / scale);
    ctx.font = `700 ${fs}px "Pretendard", system-ui, sans-serif`;
    ctx.textAlign = "center";
    ctx.textBaseline = "bottom";
    ctx.shadowColor = "rgba(0,0,0,0.6)";
    ctx.shadowBlur = 3;
    ctx.fillStyle = "#fff";
    ctx.fillText("#" + id, px, py - r - 3);
    ctx.shadowColor = "transparent";
    ctx.shadowBlur = 0;
  }

  /* ── 내 로봇 마커 ──────────────────────────────────── */
  function drawMyRobotMarker(px, py, yaw) {
    const pulse = Math.sin(pulsePhase * Math.PI * 2);

    ctx.beginPath();
    ctx.arc(px, py, ROBOT_R + 5 + 5 * pulse, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(59,130,246," + (0.12 + 0.18 * pulse).toFixed(2) + ")";
    ctx.fill();

    ctx.beginPath();
    ctx.arc(px, py, ROBOT_R + 2, 0, Math.PI * 2);
    ctx.strokeStyle = "rgba(59,130,246,0.5)";
    ctx.lineWidth = 1;
    ctx.stroke();

    drawRobotMarker(px, py, yaw, MY_COLOR, ROBOT_R);
    drawRobotLabel(px, py, myRobotId, ROBOT_R);
  }

  /* ── 좌표 변환 (90도 CCW 회전) ─────────────────────── */
  function worldToCanvas(wx, wy) {
    return [
      (W_MAX_Y - wy) / W_SPAN_Y * LW,
      (W_MAX_X - wx) / W_SPAN_X * LH,
    ];
  }

  /* ── 유틸 ──────────────────────────────────────────── */
  function roundRect(x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.lineTo(x + w - r, y);
    ctx.quadraticCurveTo(x + w, y, x + w, y + r);
    ctx.lineTo(x + w, y + h - r);
    ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    ctx.lineTo(x + r, y + h);
    ctx.quadraticCurveTo(x, y + h, x, y + h - r);
    ctx.lineTo(x, y + r);
    ctx.quadraticCurveTo(x, y, x + r, y);
    ctx.closePath();
  }

  /* ── 핀치 줌 ───────────────────────────────────────── */
  function getTouchDist(t) {
    return Math.hypot(t[0].clientX - t[1].clientX, t[0].clientY - t[1].clientY);
  }
  function onTouchStart(e) {
    if (e.touches.length === 2) { e.preventDefault(); lastDist = getTouchDist(e.touches); }
  }
  function onTouchMove(e) {
    if (e.touches.length === 2) {
      e.preventDefault();
      const d = getTouchDist(e.touches);
      if (lastDist) { scale = Math.max(0.5, Math.min(5, scale * d / lastDist)); }
      lastDist = d;
    }
  }
  function onTouchEnd(e) { if (e.touches.length < 2) lastDist = null; }

  return { init, updateFromStatus, setVisible };
})();
