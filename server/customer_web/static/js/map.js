/**
 * map.js — Canvas 기반 미니어처 마트 맵 렌더링
 *
 * shop.yaml 설정:
 *   resolution : 미터/픽셀 (예: 0.05)
 *   origin     : [x, y, theta] 맵 원점 (미터)
 *
 * 좌표 변환 (맵 PNG 90도 CCW 회전 후):
 *   px = logicalW  - (pos_y - origin_y) / resolution
 *   py = logicalH - (pos_x - origin_x) / resolution
 *
 * 핀치 줌 지원 (모바일).
 */

"use strict";

const MapRenderer = (() => {
  const MAP_CONFIG = {
    resolution: window.MAP_RESOLUTION || 0.05,
    originX:    window.MAP_ORIGIN_X   || -0.1,
    originY:    window.MAP_ORIGIN_Y   || -0.1,
    imageUrl:   window.MAP_IMAGE_URL  || "/static/map/shop.png",
  };

  let canvas, ctx;
  let mapImage = null;
  let mapImageRotated = null;
  let myRobotId = null;
  let logicalW = 0;
  let logicalH = 0;
  let dpr = 1;

  let myRobot = null;
  let otherRobots = [];

  let scale = 1;
  let lastDist = null;

  /** 정사각형 마커: 한 변 길이 = 2 * MARKER_HALF_PX (논리 픽셀) */
  const MARKER_HALF_PX = 8;
  const MY_ROBOT_COLOR = "#0369a1";
  const OTHER_ROBOT_COLOR = "#7dd3fc";

  function init(canvasId, robotId) {
    canvas = document.getElementById(canvasId);
    if (!canvas) return;
    ctx = canvas.getContext("2d");
    myRobotId = String(robotId);

    mapImage = new Image();
    mapImage.onload = () => {
      const off = document.createElement("canvas");
      off.width = mapImage.naturalHeight;
      off.height = mapImage.naturalWidth;
      const offCtx = off.getContext("2d");
      offCtx.translate(0, off.height);
      offCtx.rotate(-Math.PI / 2);
      offCtx.drawImage(mapImage, 0, 0);
      mapImageRotated = off;

      logicalW = off.width;
      logicalH = off.height;
      applyCanvasBufferSize();
      render();
    };
    mapImage.onerror = () => {
      logicalW = 400;
      logicalH = 300;
      applyCanvasBufferSize();
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.fillStyle = "#1e293b";
      ctx.fillRect(0, 0, logicalW, logicalH);
      ctx.fillStyle = "#94a3b8";
      ctx.font = "14px sans-serif";
      ctx.textAlign = "center";
      ctx.fillText("맵 이미지를 불러올 수 없습니다.", logicalW / 2, logicalH / 2);
    };
    mapImage.src = MAP_CONFIG.imageUrl;

    function applyCanvasBufferSize() {
      /* 상한 3: 고해상도 패널에서 마커·테두리 번짐 완화 (맵 디테일은 PNG에 의존) */
      dpr = Math.min(window.devicePixelRatio || 1, 3);
      canvas.width = Math.round(logicalW * dpr);
      canvas.height = Math.round(logicalH * dpr);
    }

    canvas.addEventListener("touchstart", onTouchStart, { passive: false });
    canvas.addEventListener("touchmove", onTouchMove, { passive: false });
    canvas.addEventListener("touchend", onTouchEnd, { passive: false });
  }

  function updateFromStatus(statusMsg) {
    if (statusMsg.my_robot) {
      myRobot = statusMsg.my_robot;
    } else if (
      statusMsg.robot_id != null &&
      statusMsg.pos_x != null &&
      statusMsg.pos_y != null &&
      myRobotId != null &&
      String(statusMsg.robot_id) === myRobotId
    ) {
      myRobot = {
        robot_id: String(statusMsg.robot_id),
        pos_x: statusMsg.pos_x,
        pos_y: statusMsg.pos_y,
      };
    }
    if (Array.isArray(statusMsg.other_robots)) {
      otherRobots = statusMsg.other_robots;
    }
    if (canvas && mapImage && mapImage.complete) {
      render();
    }
  }

  function render() {
    if (!canvas || !ctx || !logicalW || !logicalH) return;

    ctx.save();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const cx = logicalW / 2;
    const cy = logicalH / 2;
    ctx.translate(cx, cy);
    ctx.scale(scale, scale);
    ctx.translate(-cx, -cy);

    if (mapImageRotated) {
      ctx.drawImage(mapImageRotated, 0, 0);
    }

    ctx.globalAlpha = 0.55;
    otherRobots.forEach((r) => {
      const [px, py] = worldToCanvas(r.pos_x, r.pos_y);
      drawRobotMarker(px, py, OTHER_ROBOT_COLOR, MARKER_HALF_PX);
    });

    ctx.globalAlpha = 1.0;
    if (myRobot) {
      const [px, py] = worldToCanvas(myRobot.pos_x, myRobot.pos_y);
      drawRobotMarker(px, py, MY_ROBOT_COLOR, MARKER_HALF_PX);
    }

    ctx.restore();
  }

  function drawRobotMarker(px, py, fillColor, half) {
    const s = half * 2;
    const x = px - half;
    const y = py - half;
    ctx.fillStyle = fillColor;
    ctx.fillRect(x, y, s, s);
    ctx.strokeStyle = "rgba(255, 255, 255, 0.9)";
    ctx.lineWidth = 1.5;
    ctx.strokeRect(x, y, s, s);
  }

  function worldToCanvas(wx, wy) {
    const px = logicalW - (wy - MAP_CONFIG.originY) / MAP_CONFIG.resolution;
    const py = logicalH - (wx - MAP_CONFIG.originX) / MAP_CONFIG.resolution;
    return [px, py];
  }

  function getTouchDist(touches) {
    const dx = touches[0].clientX - touches[1].clientX;
    const dy = touches[0].clientY - touches[1].clientY;
    return Math.hypot(dx, dy);
  }

  function onTouchStart(e) {
    if (e.touches.length === 2) {
      e.preventDefault();
      lastDist = getTouchDist(e.touches);
    }
  }

  function onTouchMove(e) {
    if (e.touches.length === 2) {
      e.preventDefault();
      const dist = getTouchDist(e.touches);
      if (lastDist) {
        const ratio = dist / lastDist;
        scale = Math.max(0.5, Math.min(5, scale * ratio));
        render();
      }
      lastDist = dist;
    }
  }

  function onTouchEnd(e) {
    if (e.touches.length < 2) lastDist = null;
  }

  return { init, updateFromStatus };
})();
