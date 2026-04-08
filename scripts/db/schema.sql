-- ShopPinkki Central DB Schema
-- PostgreSQL 17 + pgvector  |  Database: shoppinkki

CREATE EXTENSION IF NOT EXISTS vector;

-- ──────────────────────────────────────────────
-- 사용자 / 카드
-- ──────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS users (
    user_id       VARCHAR(50)  NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id)
);

CREATE TABLE IF NOT EXISTS CARD (
    card_id    SERIAL       PRIMARY KEY,
    user_id    VARCHAR(50)  NOT NULL,
    card_alias VARCHAR(50)  NOT NULL DEFAULT '기본 카드',
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- ──────────────────────────────────────────────
-- 구역 / 상품
-- ──────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS ZONE (
    zone_id        INT          NOT NULL,
    zone_name      VARCHAR(100) NOT NULL,
    zone_type      VARCHAR(20)  NOT NULL,   -- 'product' | 'special'
    waypoint_x     DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    waypoint_y     DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    waypoint_theta DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    PRIMARY KEY (zone_id)
);

CREATE TABLE IF NOT EXISTS PRODUCT (
    product_id   SERIAL       PRIMARY KEY,
    product_name VARCHAR(100) NOT NULL,
    zone_id      INT          NOT NULL,
    price        INT          NOT NULL DEFAULT 0,
    FOREIGN KEY (zone_id) REFERENCES ZONE(zone_id),
    UNIQUE (product_name)
);

CREATE TABLE IF NOT EXISTS PRODUCT_TEXT_EMBEDDING (
    id          SERIAL       PRIMARY KEY,
    product_id  INT          NOT NULL,
    text        TEXT         NOT NULL,
    embedding   vector(384)  NULL,
    model_name  VARCHAR(100) NULL,
    FOREIGN KEY (product_id) REFERENCES PRODUCT(product_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ZONE_TEXT_EMBEDDING (
    id          INT          NOT NULL AUTO_INCREMENT,
    zone_id     INT          NOT NULL,
    text        TEXT         NOT NULL,
    embedding   VECTOR(384)  NULL,
    model_name  VARCHAR(100) NULL,
    PRIMARY KEY (id),
    FOREIGN KEY (zone_id) REFERENCES ZONE(zone_id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ──────────────────────────────────────────────
-- 경계 설정
-- ──────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS BOUNDARY_CONFIG (
    id          SERIAL       PRIMARY KEY,
    description VARCHAR(100) NOT NULL,
    x_min       DOUBLE PRECISION NOT NULL,
    x_max       DOUBLE PRECISION NOT NULL,
    y_min       DOUBLE PRECISION NOT NULL,
    y_max       DOUBLE PRECISION NOT NULL,
    UNIQUE (description)
);

-- ──────────────────────────────────────────────
-- 로봇
-- ──────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS ROBOT (
    robot_id         VARCHAR(10)      NOT NULL,
    ip_address       VARCHAR(15)      NOT NULL,
    current_mode     VARCHAR(30)      NOT NULL DEFAULT 'OFFLINE',
    -- 'CHARGING|IDLE|TRACKING|TRACKING_CHECKOUT|GUIDING|SEARCHING|WAITING|LOCKED|RETURNING|HALTED|OFFLINE'
    pos_x            DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    pos_y            DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    battery_level    INT              NOT NULL DEFAULT 100,
    last_seen        TIMESTAMP        NULL,
    active_user_id   VARCHAR(50)      NULL,
    is_locked_return BOOLEAN          NOT NULL DEFAULT FALSE,
    PRIMARY KEY (robot_id),
    FOREIGN KEY (active_user_id) REFERENCES users(user_id) ON DELETE SET NULL,
    UNIQUE (active_user_id)   -- 유저 1명 = 로봇 1대
);

-- ──────────────────────────────────────────────
-- 직원 호출 로그
-- ──────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS STAFF_CALL_LOG (
    log_id      SERIAL      PRIMARY KEY,
    robot_id    VARCHAR(10) NOT NULL,
    user_id     VARCHAR(50) NULL,
    event_type  VARCHAR(20) NOT NULL,   -- 'LOCKED' | 'HALTED'
    occurred_at TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP   NULL,       -- NULL = 미처리
    FOREIGN KEY (robot_id) REFERENCES ROBOT(robot_id)
);

-- ──────────────────────────────────────────────
-- 이벤트 로그
-- ──────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS EVENT_LOG (
    event_id     SERIAL      PRIMARY KEY,
    robot_id     VARCHAR(10) NOT NULL,
    user_id      VARCHAR(50) NULL,
    event_type   VARCHAR(30) NOT NULL,
    -- 'SESSION_START|SESSION_END|FORCE_TERMINATE|LOCKED|HALTED|STAFF_RESOLVED|PAYMENT_SUCCESS|MODE_CHANGE|OFFLINE|ONLINE'
    event_detail TEXT        NULL,
    occurred_at  TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (robot_id) REFERENCES ROBOT(robot_id)
);

-- ──────────────────────────────────────────────
-- 세션 / 장바구니
-- ──────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS SESSION (
    session_id  SERIAL      PRIMARY KEY,
    robot_id    VARCHAR(10) NOT NULL,
    user_id     VARCHAR(50) NOT NULL,
    is_active   BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at  TIMESTAMP   NOT NULL,
    FOREIGN KEY (robot_id) REFERENCES ROBOT(robot_id),
    FOREIGN KEY (user_id)  REFERENCES users(user_id)
);

-- 활성 세션 중 유저 1명 = 세션 1개
CREATE UNIQUE INDEX IF NOT EXISTS uk_active_session_user
    ON SESSION (user_id) WHERE is_active = TRUE;

-- 활성 세션 중 로봇 1대 = 세션 1개
CREATE UNIQUE INDEX IF NOT EXISTS uk_active_session_robot
    ON SESSION (robot_id) WHERE is_active = TRUE;

CREATE TABLE IF NOT EXISTS CART (
    cart_id    SERIAL PRIMARY KEY,
    session_id INT    NOT NULL,
    FOREIGN KEY (session_id) REFERENCES SESSION(session_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS CART_ITEM (
    item_id      SERIAL       PRIMARY KEY,
    cart_id      INT          NOT NULL,
    product_name VARCHAR(100) NOT NULL,
    price        INT          NOT NULL DEFAULT 0,
    quantity     INT          NOT NULL DEFAULT 1,
    scanned_at   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_paid      BOOLEAN      NOT NULL DEFAULT FALSE,
    FOREIGN KEY (cart_id) REFERENCES CART(cart_id) ON DELETE CASCADE
);
