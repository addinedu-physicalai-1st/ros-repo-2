/**
 * map.js — 벡터 기반 미니어처 마트 맵 렌더링
 *
 * SLAM 이미지 없이 Canvas 2D로 직접 그림.
 * 구역 블록 + 로봇 마커 + 핀치 줌.
 */

"use strict";

class MapRenderer {
  /* ── 세계 좌표 경계 (미터) ─────────────────────────── */
  static W_MAX_X = 1.20; static W_MIN_X = -0.10;
  static W_MAX_Y = 0.05; static W_MIN_Y = -1.65;
  static W_SPAN_X = MapRenderer.W_MAX_X - MapRenderer.W_MIN_X;
  static W_SPAN_Y = MapRenderer.W_MAX_Y - MapRenderer.W_MIN_Y;

  /* 논리 좌표계 */
  static LW = 420; static LH = 330;

  /* ── 구역 블록 ─────────────────────────────────────── */
  static ZONES = [
    { name: "가전\n제품", icon: "\uD83D\uDD0C", x1: 0.42, y1: 0.02, x2: 0.77, y2: -0.10, bg: "#e0f2fe", fg: "#0369a1" },
    { name: "과자",       icon: "\uD83C\uDF6A", x1: 0.77, y1: 0.02, x2: 1.05, y2: -0.10, bg: "#fef9c3", fg: "#a16207" },
    { name: "해산물",     icon: "\uD83D\uDC1F", x1: 1.05, y1: -0.10, x2: 1.17, y2: -0.50, bg: "#cffafe", fg: "#0e7490" },
    { name: "육류",       icon: "\uD83E\uDD69", x1: 1.05, y1: -0.50, x2: 1.17, y2: -1.06, bg: "#ffe4e6", fg: "#be123c" },
    { name: "채소",       icon: "\uD83E\uDD6C", x1: 1.05, y1: -1.06, x2: 1.17, y2: -1.38, bg: "#dcfce7", fg: "#15803d" },
    { name: "화장실",     icon: "\uD83D\uDEBB", x1: 0.72, y1: -1.43, x2: 0.95, y2: -1.58, bg: "#f1f5f9", fg: "#475569" },
    { name: "결제구역",   icon: "\uD83D\uDCB3", x1: 0.06, y1: -1.28, x2: 0.27, y2: -1.56, bg: "#d1fae5", fg: "#047857" },
    { name: "충전소",     icon: "\u26A1",        x1: -0.06, y1: -0.52, x2: 0.06, y2: -0.93, bg: "#fef9c3", fg: "#a16207" },
  ];

  static getZoneCenter(zoneName) {
    const z = MapRenderer.ZONES.find(v => v.name.replace("\n", "") === zoneName.replace("\n", ""));
    if (z) return [(z.x1 + z.x2) / 2, (z.y1 + z.y2) / 2];
    // 선반 구역도 검색
    const s = MapRenderer.SHELF_ZONES.find(v => (v.a && v.a.name === zoneName) || (v.b && v.b.name === zoneName));
    if (s) return [(s.x1 + s.x2) / 2, (s.y1 + s.y2) / 2];
    return null;
  }

  /* ── 선반 zone (장애물 안 색상) ─────────────────────── */
  static SHELF_ZONES = [
    { x1: 0.424, y1: -0.393, x2: 0.844, y2: -0.493,
      a: { name: "빵", icon: "\uD83C\uDF5E", bg: "#fed7aa", fg: "#9a3412" },
      b: { name: "가공식품", icon: "\uD83E\uDD6B", bg: "#fce7f3", fg: "#9d174d" } },
    { x1: 0.633, y1: -1.023, x2: 0.843, y2: -1.123,
      a: { name: "음료", icon: "\uD83E\uDD64", bg: "#e0e7ff", fg: "#4338ca" },
      b: null },
  ];

  /* ── 장애물 ────────────────────────────────────────── */
  static OBSTACLES = [
    { x1: 0.064, y1: -1.22, x2: 0.264, y2: -1.25 },
  ];

  static ENTRANCE_EXIT = [
    { name: "입구", wx: -0.04, wy: -0.057, arrow: "\u25B2", color: "#16a34a" },
    { name: "출구", wx: -0.04, wy: -1.547, arrow: "\u25BC", color: "#dc2626" },
  ];

  static MY_COLOR    = "#2563eb";
  static OTHER_COLOR = "#94a3b8";
  static ROBOT_R     = 9;
  static ROBOT_R_SM  = 7;
  static SHELF_COLOR = "#a8896c";
  static FLOOR_COLOR = "#faf6f0";
  static WALL_COLOR  = "#78716c";

  constructor() {
    this.canvas = null;
    this.ctx = null;
    this.myRobotId = null;
    this.dpr = 1;
    this.myRobot = null;
    this.myPath = [];
    this.otherRobots = [];
    this.scale = 1;
    this.lastDist = null;
    this.visible = false;
    this.animFrameId = null;
    this.pulsePhase = 0;
    this.previewPath = null;

    /* ── 애니메이션/카메라 상태 ── */
    this.scale = 1.0;
    this.camX = MapRenderer.LW / 2;
    this.camY = MapRenderer.LH / 2;
    
    this.targetScale = 1.0;
    this.targetCamX = MapRenderer.LW / 2;
    this.targetCamY = MapRenderer.LH / 2;
    
    this.sequenceState = "IDLE"; // IDLE, WAIT, ZOOM, FOLLOW, RESET
    this.seqTimer = 0;
    this.seqPathIndex = 0;
    
    // 이벤트 핸들러 바인딩
    this.onTouchStart = this.onTouchStart.bind(this);
    this.onTouchMove = this.onTouchMove.bind(this);
    this.onTouchEnd = this.onTouchEnd.bind(this);
  }

  /* ── 초기화 ────────────────────────────────────────── */
  init(canvasId, robotId) {
    this.canvas = document.getElementById(canvasId);
    if (!this.canvas) return;
    this.ctx = this.canvas.getContext("2d");
    this.myRobotId = String(robotId);
    this.sizeBuffer();
    
    // 초기 카메라 위치 설정
    this.camX = MapRenderer.LW / 2;
    this.camY = MapRenderer.LH / 2;
    this.targetCamX = this.camX;
    this.targetCamY = this.camY;

    this.render();
    this.canvas.addEventListener("touchstart", this.onTouchStart, { passive: false });
    this.canvas.addEventListener("touchmove",  this.onTouchMove,  { passive: false });
    this.canvas.addEventListener("touchend",   this.onTouchEnd,   { passive: false });
  }

  sizeBuffer() {
    if (!this.canvas) return;
    this.dpr = Math.min(window.devicePixelRatio || 1, 3);
    var cssW = this.canvas.clientWidth  || 400;
    var cssH = this.canvas.clientHeight || Math.round(cssW * MapRenderer.LH / MapRenderer.LW);
    this.canvas.width  = Math.round(cssW * this.dpr);
    this.canvas.height = Math.round(cssH * this.dpr);
  }

  /* ── 가시성 ────────────────────────────────────────── */
  setVisible(v) {
    this.visible = v;
    if (v) { 
      this.sizeBuffer(); 
      this.render(); 
      this.startAnim(); 
    } else { 
      this.stopAnim(); 
      this.sequenceState = "IDLE";
    }
  }

  startAnim() {
    if (this.animFrameId) return;
    const loop = (ts) => {
      this.pulsePhase = (ts % 2000) / 2000;
      this.update(ts);
      this.render();
      if (this.visible) this.animFrameId = requestAnimationFrame(loop);
      else this.animFrameId = null;
    };
    this.animFrameId = requestAnimationFrame(loop);
  }

  stopAnim() {
    if (this.animFrameId) { 
      cancelAnimationFrame(this.animFrameId); 
      this.animFrameId = null; 
    }
  }

  /* ── 애니메이션 상태 업데이트 ────────────────────────── */
  update(ts) {
    if (this.sequenceState === "IDLE") {
        // 부드러운 카메라 추적 (대상 지정 시)
        this.scale += (this.targetScale - this.scale) * 0.1;
        this.camX += (this.targetCamX - this.camX) * 0.1;
        this.camY += (this.targetCamY - this.camY) * 0.1;
        return;
    }

    // LERP (부드러운 이동) - 속도를 0.08에서 0.04로 대폭 낮춤
    const lerpSpeed = 0.04;
    this.scale += (this.targetScale - this.scale) * lerpSpeed;
    this.camX += (this.targetCamX - this.camX) * lerpSpeed;
    this.camY += (this.targetCamY - this.camY) * lerpSpeed;

    // 시퀀스 상태 머신
    const now = Date.now();
    switch(this.sequenceState) {
        case "WAIT": // 1.2초로 대기 시간 연장 (전체 맵 인지)
            if (now > this.seqTimer) {
                this.sequenceState = "ZOOM";
                // 줌 타겟 설정 (로봇 위치)
                if (this.myRobot) {
                    const p = this.worldToCanvas(this.myRobot.pos_x, this.myRobot.pos_y);
                    this.targetCamX = p[0];
                    this.targetCamY = p[1];
                }
                this.targetScale = 1.6; // 살짝 확대
                this.seqTimer = now + 1200; // 줌 완료 대기 시간 연장
            }
            break;
        case "ZOOM":
            if (now > this.seqTimer) {
                this.sequenceState = "FOLLOW";
                this.seqPathIndex = 0;
            }
            break;
        case "FOLLOW":
            if (this.previewPath && this.previewPath.length > 0) {
                const targetPoint = this.previewPath[this.seqPathIndex];
                const p = this.worldToCanvas(targetPoint.x, targetPoint.y);
                this.targetCamX = p[0];
                this.targetCamY = p[1];

                // 목표 지점에 가까워지면 다음 포인트로 (속도가 느려졌으므로 판정 거리는 유지)
                const dist = Math.hypot(this.camX - p[0], this.camY - p[1]);
                if (dist < 10) {
                    this.seqPathIndex++;
                    if (this.seqPathIndex >= this.previewPath.length) {
                        this.sequenceState = "RESET";
                        this.seqTimer = now + 2500; // 목적지 도착 후 확인 시간 연장
                    }
                }
            } else {
                this.sequenceState = "RESET";
            }
            break;
        case "RESET":
            if (now > this.seqTimer) {
                this.startPreviewSequence(this.previewPath); // 무한 루프 재시작
            }
            break;
    }
  }

  /* ── 시퀀스 애니메이션 시작 ── */
  startPreviewSequence(path) {
    if (!path || path.length < 2) return;
    this.previewPath = path;
    
    // 1단계: 전체 화면으로 셋팅
    this.sequenceState = "WAIT";
    this.targetScale = 1.0;
    this.targetCamX = MapRenderer.LW / 2;
    this.targetCamY = MapRenderer.LH / 2;
    
    this.seqTimer = Date.now() + 1000; // 1초 대기 시작
  }

  /* ── 데이터 업데이트 ───────────────────────────────── */
  updateFromStatus(statusMsg) {
    if (statusMsg.my_robot) {
      this.myRobot = statusMsg.my_robot;
    } else if (
      statusMsg.robot_id != null && statusMsg.pos_x != null &&
      this.myRobotId != null && String(statusMsg.robot_id) === this.myRobotId
    ) {
      this.myRobot = {
        robot_id: String(statusMsg.robot_id),
        pos_x: statusMsg.pos_x, pos_y: statusMsg.pos_y,
        yaw: statusMsg.yaw || 0,
      };
    }
    if (statusMsg.my_robot && Array.isArray(statusMsg.my_robot.path)) {
      this.myPath = statusMsg.my_robot.path;
    } else if (Array.isArray(statusMsg.path)) {
      this.myPath = statusMsg.path;
    }
    if (Array.isArray(statusMsg.other_robots)) this.otherRobots = statusMsg.other_robots;
    
    // 루프 시퀀스가 없는데 로봇이 있으면 카메라 추적 (메인 지도 대응 등)
    if (this.sequenceState === "IDLE" && this.myRobot) {
        // 필요 시 자동 추적 로직 추가 가능
    }

    if (!this.animFrameId && this.canvas) this.render();
  }

  /* ── 렌더링 ────────────────────────────────────────── */
  render() {
    if (!this.canvas || !this.ctx) return;
    var sx = this.canvas.width / MapRenderer.LW, sy = this.canvas.height / MapRenderer.LH;
    this.ctx.save();
    this.ctx.setTransform(sx, 0, 0, sy, 0, 0);

    // 카메라 기반 좌표계 변환
    var vpw = MapRenderer.LW, vph = MapRenderer.LH;
    this.ctx.translate(vpw / 2, vph / 2);
    this.ctx.scale(this.scale, this.scale);
    this.ctx.translate(-this.camX, -this.camY);

    /* 배경 */
    this.ctx.fillStyle = "#1c1917";
    this.ctx.fillRect(-500, -500, MapRenderer.LW + 1000, MapRenderer.LH + 1000);

    this.drawFloor();
    this.drawObstacles();
    this.drawShelfZones();
    this.drawZones();
    this.drawEntranceExit();
    this.drawPath();

    this.ctx.globalAlpha = 0.4;
    this.otherRobots.forEach((r) => {
      var p = this.worldToCanvas(r.pos_x, r.pos_y);
      this.drawRobotMarker(p[0], p[1], r.yaw || 0, MapRenderer.OTHER_COLOR, MapRenderer.ROBOT_R_SM);
      this.drawRobotLabel(p[0], p[1], String(r.robot_id), MapRenderer.ROBOT_R_SM);
    });
    this.ctx.globalAlpha = 1.0;

    if (this.myRobot) {
      var p = this.worldToCanvas(this.myRobot.pos_x, this.myRobot.pos_y);
      this.drawMyRobotMarker(p[0], p[1], this.myRobot.yaw || 0);
    }

    this.ctx.restore();
  }

  /* ── 마트 바닥 ─────────────────────────────────────── */
  drawFloor() {
    var pad = 8;
    this.ctx.shadowColor = "rgba(0,0,0,0.4)";
    this.ctx.shadowBlur = 14;
    this.ctx.shadowOffsetX = 2; this.ctx.shadowOffsetY = 2;
    this.roundRect(pad, pad, MapRenderer.LW - 2 * pad, MapRenderer.LH - 2 * pad, 6);
    this.ctx.fillStyle = MapRenderer.FLOOR_COLOR;
    this.ctx.fill();
    this.ctx.shadowColor = "transparent"; this.ctx.shadowBlur = 0;
    this.ctx.shadowOffsetX = 0; this.ctx.shadowOffsetY = 0;

    this.ctx.strokeStyle = "rgba(168,137,108,0.07)";
    this.ctx.lineWidth = 0.4;
    var step = 16;
    for (var gx = pad + step; gx < MapRenderer.LW - pad; gx += step) {
      this.ctx.beginPath(); this.ctx.moveTo(gx, pad); this.ctx.lineTo(gx, MapRenderer.LH - pad); this.ctx.stroke();
    }
    for (var gy = pad + step; gy < MapRenderer.LH - pad; gy += step) {
      this.ctx.beginPath(); this.ctx.moveTo(pad, gy); this.ctx.lineTo(MapRenderer.LW - pad, gy); this.ctx.stroke();
    }

    this.roundRect(pad, pad, MapRenderer.LW - 2 * pad, MapRenderer.LH - 2 * pad, 6);
    this.ctx.strokeStyle = MapRenderer.WALL_COLOR;
    this.ctx.lineWidth = 3.5;
    this.ctx.stroke();
  }

  drawObstacles() {
    MapRenderer.OBSTACLES.forEach((o) => {
      var p1 = this.worldToCanvas(o.x2, o.y1), p2 = this.worldToCanvas(o.x1, o.y2);
      var ow = p2[0] - p1[0], oh = p2[1] - p1[1];
      this.ctx.fillStyle = MapRenderer.SHELF_COLOR;
      this.ctx.fillRect(p1[0], p1[1], ow, Math.max(oh, 2.5));
    });
  }

  drawShelfZones() {
    MapRenderer.SHELF_ZONES.forEach((s) => {
      var p1 = this.worldToCanvas(s.x2, s.y1), p2 = this.worldToCanvas(s.x1, s.y2);
      var w = p2[0] - p1[0], h = p2[1] - p1[1];
      this.roundRect(p1[0] - 1, p1[1] - 1, w + 2, h + 2, 3);
      this.ctx.fillStyle = MapRenderer.SHELF_COLOR;
      this.ctx.fill();

      if (s.b) {
        var hw = w / 2;
        this.roundRect(p1[0] + 1, p1[1] + 1, hw - 1.5, h - 2, 2);
        this.ctx.fillStyle = s.a.bg; this.ctx.fill();
        this.roundRect(p1[0] + hw + 0.5, p1[1] + 1, hw - 1.5, h - 2, 2);
        this.ctx.fillStyle = s.b.bg; this.ctx.fill();
        var fs = Math.max(6, Math.min(11, h * 0.8) / this.scale);
        this.ctx.font = "700 " + fs + 'px "Pretendard", sans-serif';
        this.ctx.textAlign = "center"; this.ctx.textBaseline = "bottom";
        this.ctx.fillStyle = s.a.fg;
        this.ctx.fillText(s.a.icon + " " + s.a.name, p1[0] + hw / 2 - 3, p1[1] - 3);
        this.ctx.textBaseline = "top"; this.ctx.fillStyle = s.b.fg;
        this.ctx.fillText(s.b.icon + " " + s.b.name, p1[0] + hw + hw / 2 + 8, p2[1] + 3);
      } else {
        this.roundRect(p1[0] + 1, p1[1] + 1, w - 2, h - 2, 2);
        this.ctx.fillStyle = s.a.bg; this.ctx.fill();
        var fs2 = Math.max(5, Math.min(10, w * 0.7) / this.scale);
        this.ctx.font = "700 " + fs2 + 'px "Pretendard", sans-serif';
        this.ctx.textAlign = "center"; this.ctx.textBaseline = "middle";
        this.ctx.fillStyle = s.a.fg;
        this.ctx.fillText(s.a.icon, p1[0] + w / 2, p1[1] + h / 2 - fs2 * 0.6);
        this.ctx.fillText(s.a.name, p1[0] + w / 2, p1[1] + h / 2 + fs2 * 0.5);
      }
    });
  }

  drawZones() {
    MapRenderer.ZONES.forEach((z) => {
      var p1 = this.worldToCanvas(z.x2, z.y1), p2 = this.worldToCanvas(z.x1, z.y2);
      var w = p2[0] - p1[0], h = p2[1] - p1[1];
      this.ctx.shadowColor = "rgba(0,0,0,0.06)";
      this.ctx.shadowBlur = 3; this.ctx.shadowOffsetY = 1;
      this.roundRect(p1[0] + 1, p1[1] + 1, w - 2, h - 2, 4);
      this.ctx.fillStyle = z.bg; this.ctx.fill();
      this.ctx.shadowColor = "transparent"; this.ctx.shadowBlur = 0; this.ctx.shadowOffsetY = 0;
      this.ctx.strokeStyle = z.fg + "20"; this.ctx.lineWidth = 0.7; this.ctx.stroke();

      var lines = z.name.split("\n");
      var longest = Math.max.apply(null, lines.map(l => l.length));
      var maxFs = Math.min(w * 0.7 / Math.max(longest, 1), h * 0.38 / lines.length);
      var fs = Math.max(5, Math.min(13, maxFs) / this.scale);
      this.ctx.font = "700 " + fs + 'px "Pretendard", sans-serif';
      this.ctx.textAlign = "center"; this.ctx.textBaseline = "middle";
      this.ctx.fillStyle = z.fg;

      if (lines.length > 1) {
        var lh = fs * 1.1, totalH = lh * lines.length + fs;
        var startY = p1[1] + h / 2 - totalH / 2;
        this.ctx.fillText(z.icon, p1[0] + w / 2, startY + fs * 0.5);
        lines.forEach((ln, i) => this.ctx.fillText(ln, p1[0] + w / 2, startY + fs + lh * (i + 0.5)));
      } else {
        if (h > fs * 2.5) {
          this.ctx.fillText(z.icon, p1[0] + w / 2, p1[1] + h / 2 - fs * 0.5);
          this.ctx.fillText(z.name, p1[0] + w / 2, p1[1] + h / 2 + fs * 0.6);
        } else this.ctx.fillText(z.icon + " " + z.name, p1[0] + w / 2, p1[1] + h / 2);
      }
    });
  }

  drawEntranceExit() {
    MapRenderer.ENTRANCE_EXIT.forEach((m) => {
      var p = this.worldToCanvas(m.wx, m.wy);
      var fs = Math.max(5, 7 / this.scale);
      this.ctx.font = "700 " + fs + 'px "Pretendard", sans-serif';
      var label = m.arrow + " " + m.name;
      var tw = this.ctx.measureText(label).width + 10;
      var th = fs + 7;
      this.roundRect(p[0] - tw / 2, p[1] - th / 2, tw, th, th / 2);
      this.ctx.fillStyle = m.color + "18"; this.ctx.fill();
      this.ctx.strokeStyle = m.color + "50"; this.ctx.lineWidth = 0.7; this.ctx.stroke();
      this.ctx.textAlign = "center"; this.ctx.textBaseline = "middle";
      this.ctx.fillStyle = m.color; this.ctx.fillText(label, p[0], p[1]);
    });
  }

  drawRobotMarker(px, py, yaw, color, r) {
    var angle = -yaw - Math.PI / 2;
    this.ctx.beginPath();
    this.ctx.ellipse(px + 1, py + 2, r * 0.9, r * 0.5, 0, 0, Math.PI * 2);
    this.ctx.fillStyle = "rgba(0,0,0,0.15)"; this.ctx.fill();
    this.ctx.beginPath(); this.ctx.arc(px, py, r, 0, Math.PI * 2);
    this.ctx.fillStyle = color; this.ctx.fill();
    this.ctx.strokeStyle = "#fff"; this.ctx.lineWidth = 1.5; this.ctx.stroke();
    var tipLen = r + 4, tipX = px + Math.cos(angle) * tipLen, tipY = py + Math.sin(angle) * tipLen, off = Math.PI * 0.72;
    this.ctx.beginPath(); this.ctx.moveTo(tipX, tipY);
    this.ctx.lineTo(px + Math.cos(angle + off) * r * 0.7, py + Math.sin(angle + off) * r * 0.7);
    this.ctx.lineTo(px + Math.cos(angle - off) * r * 0.7, py + Math.sin(angle - off) * r * 0.7);
    this.ctx.closePath(); this.ctx.fillStyle = color; this.ctx.fill();
    var ifs = Math.max(4, r * 0.9);
    this.ctx.font = ifs + "px sans-serif";
    this.ctx.textAlign = "center"; this.ctx.textBaseline = "middle";
    this.ctx.fillStyle = "#fff"; this.ctx.fillText("\uD83D\uDED2", px, py);
  }

  drawRobotLabel(px, py, id, r) {
    var fs = Math.max(5, 7 / this.scale);
    this.ctx.font = "700 " + fs + 'px "Pretendard", sans-serif';
    this.ctx.textAlign = "center"; this.ctx.textBaseline = "bottom";
    var tw = this.ctx.measureText("#" + id).width + 6, th = fs + 3;
    var lx = px - tw / 2, ly = py - r - 5 - th;
    this.roundRect(lx, ly, tw, th, th / 2);
    this.ctx.fillStyle = "rgba(0,0,0,0.55)"; this.ctx.fill();
    this.ctx.fillStyle = "#fff"; this.ctx.textBaseline = "middle";
    this.ctx.fillText("#" + id, px, ly + th / 2);
  }

  drawMyRobotMarker(px, py, yaw) {
    var pulse = Math.sin(this.pulsePhase * Math.PI * 2);
    this.ctx.beginPath();
    this.ctx.arc(px, py, MapRenderer.ROBOT_R + 5 + 5 * pulse, 0, Math.PI * 2);
    this.ctx.fillStyle = "rgba(37,99,235," + (0.10 + 0.15 * pulse) + ")";
    this.ctx.fill();
    this.ctx.beginPath();
    this.ctx.arc(px, py, MapRenderer.ROBOT_R + 2.5, 0, Math.PI * 2);
    this.ctx.strokeStyle = "rgba(37,99,235,0.45)"; this.ctx.lineWidth = 1.2; this.ctx.stroke();
    this.drawRobotMarker(px, py, yaw, MapRenderer.MY_COLOR, MapRenderer.ROBOT_R);
    this.drawRobotLabel(px, py, this.myRobotId, MapRenderer.ROBOT_R);
  }

  drawPath() {
    // 실제 경로(this.myPath)가 있으면 우선적으로 그리고, 없으면 가상 경로(this.previewPath)를 그림
    const path = (this.myPath && this.myPath.length >= 2) ? this.myPath : this.previewPath;
    if (!path || path.length < 2) return;
    
    this.ctx.save(); this.ctx.setLineDash([4, 3]); this.ctx.lineWidth = 2;
    this.ctx.strokeStyle = (path === this.previewPath) ? "rgba(37,99,235,0.3)" : "rgba(37,99,235,0.5)"; 
    this.ctx.beginPath();
    for (var i = 0; i < path.length; i++) {
      var p = this.worldToCanvas(path[i].x, path[i].y);
      if (i === 0) this.ctx.moveTo(p[0], p[1]);
      else this.ctx.lineTo(p[0], p[1]);
    }
    this.ctx.stroke(); this.ctx.setLineDash([]);
    var last = path[path.length - 1], lp = this.worldToCanvas(last.x, last.y);
    this.ctx.beginPath(); this.ctx.arc(lp[0], lp[1], 4, 0, Math.PI * 2);
    this.ctx.fillStyle = "rgba(37,99,235,0.7)"; this.ctx.fill();
    this.ctx.strokeStyle = "#fff"; this.ctx.lineWidth = 1.2; this.ctx.stroke();
    this.ctx.restore();
  }

  worldToCanvas(wx, wy) {
    return [
      (MapRenderer.W_MAX_Y - wy) / MapRenderer.W_SPAN_Y * MapRenderer.LW,
      (MapRenderer.W_MAX_X - wx) / MapRenderer.W_SPAN_X * MapRenderer.LH,
    ];
  }

  roundRect(x, y, w, h, r) {
    this.ctx.beginPath(); this.ctx.moveTo(x + r, y);
    this.ctx.lineTo(x + w - r, y); this.ctx.quadraticCurveTo(x + w, y, x + w, y + r);
    this.ctx.lineTo(x + w, y + h - r); this.ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    this.ctx.lineTo(x + r, y + h); this.ctx.quadraticCurveTo(x, y + h, x, y + h - r);
    this.ctx.lineTo(x, y + r); this.ctx.quadraticCurveTo(x, y, x + r, y);
    this.ctx.closePath();
  }

  /* ── 자동 줌 (Fit to Points) ── */
  fitToPoints(wx1, wy1, wx2, wy2) {
    if (wx1 == null || wx2 == null) return;
    const p1 = this.worldToCanvas(wx1, wy1);
    const p2 = this.worldToCanvas(wx2, wy2);
    const dx = Math.abs(p1[0] - p2[0]), dy = Math.abs(p1[1] - p2[1]);
    const margin = 100; 
    const sX = (MapRenderer.LW - margin) / (dx || 1);
    const sY = (MapRenderer.LH - margin) / (dy || 1);
    this.scale = Math.max(1, Math.min(2.5, Math.min(sX, sY)));
    this.render();
  }

  getTouchDist(t) { return Math.hypot(t[0].clientX - t[1].clientX, t[0].clientY - t[1].clientY); }
  onTouchStart(e) { if (e.touches.length === 2) { e.preventDefault(); this.lastDist = this.getTouchDist(e.touches); } }
  onTouchMove(e) {
    if (e.touches.length === 2) {
      e.preventDefault(); var d = this.getTouchDist(e.touches);
      if (this.lastDist) this.scale = Math.max(0.5, Math.min(5, this.scale * d / this.lastDist));
      this.lastDist = d; this.render();
    }
  }
  onTouchEnd(e) { if (e.touches.length < 2) this.lastDist = null; }
}
