-- ShopPinkki Central DB Schema (PostgreSQL 17 + pgvector)
-- control_service + AI embeddings. seed.sh 1번은 DB를 새로 만들므로 빈 DB에 적용된다.

CREATE EXTENSION IF NOT EXISTS vector;

DROP TABLE IF EXISTS fleet_lane CASCADE;
DROP TABLE IF EXISTS fleet_waypoint CASCADE;
DROP TABLE IF EXISTS cart_item CASCADE;
DROP TABLE IF EXISTS cart CASCADE;
DROP TABLE IF EXISTS session CASCADE;
DROP TABLE IF EXISTS staff_call_log CASCADE;
DROP TABLE IF EXISTS event_log CASCADE;
DROP TABLE IF EXISTS robot CASCADE;
DROP TABLE IF EXISTS card CASCADE;
DROP TABLE IF EXISTS users CASCADE;
DROP TABLE IF EXISTS boundary_config CASCADE;
DROP TABLE IF EXISTS product_text_embedding CASCADE;
DROP TABLE IF EXISTS zone_text_embedding CASCADE;
DROP TABLE IF EXISTS product CASCADE;
DROP TABLE IF EXISTS zone CASCADE;

CREATE TABLE users (
    user_id       VARCHAR(50)  NOT NULL PRIMARY KEY,
    password_hash VARCHAR(255) NOT NULL,
    created_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE card (
    card_id    SERIAL PRIMARY KEY,
    user_id    VARCHAR(50)  NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    card_alias VARCHAR(50)  NOT NULL DEFAULT '기본 카드',
    UNIQUE (user_id, card_alias)
);

CREATE TABLE zone (
    zone_id        INT PRIMARY KEY,
    zone_name      VARCHAR(100) NOT NULL UNIQUE,
    zone_type      VARCHAR(50)  NOT NULL,
    waypoint_x     DOUBLE PRECISION NOT NULL,
    waypoint_y     DOUBLE PRECISION NOT NULL,
    waypoint_theta DOUBLE PRECISION NOT NULL
);

CREATE TABLE product (
    product_id   SERIAL PRIMARY KEY,
    product_name VARCHAR(200) NOT NULL UNIQUE,
    zone_id      INT NOT NULL REFERENCES zone(zone_id),
    price        INT NOT NULL DEFAULT 0
);

CREATE TABLE product_text_embedding (
    id          SERIAL PRIMARY KEY,
    product_id  INT NOT NULL UNIQUE REFERENCES product(product_id) ON DELETE CASCADE,
    text        TEXT NOT NULL,
    embedding   vector(384),
    model_name  VARCHAR(100) NOT NULL
);

CREATE TABLE zone_text_embedding (
    id          SERIAL PRIMARY KEY,
    zone_id     INT NOT NULL UNIQUE REFERENCES zone(zone_id) ON DELETE CASCADE,
    text        TEXT NOT NULL,
    embedding   vector(384),
    model_name  VARCHAR(100) NOT NULL
);

CREATE TABLE boundary_config (
    id          SERIAL PRIMARY KEY,
    description VARCHAR(100) NOT NULL UNIQUE,
    x_min       DOUBLE PRECISION NOT NULL,
    x_max       DOUBLE PRECISION NOT NULL,
    y_min       DOUBLE PRECISION NOT NULL,
    y_max       DOUBLE PRECISION NOT NULL
);

CREATE TABLE robot (
    robot_id         VARCHAR(10) NOT NULL PRIMARY KEY,
    ip_address       VARCHAR(45) NOT NULL,
    current_mode     VARCHAR(30) NOT NULL DEFAULT 'OFFLINE',
    pos_x            DOUBLE PRECISION NOT NULL DEFAULT 0,
    pos_y            DOUBLE PRECISION NOT NULL DEFAULT 0,
    battery_level    INT NOT NULL DEFAULT 100,
    last_seen        TIMESTAMP,
    active_user_id   VARCHAR(50) REFERENCES users(user_id) ON DELETE SET NULL,
    is_locked_return BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (active_user_id)
);

CREATE TABLE staff_call_log (
    log_id      SERIAL PRIMARY KEY,
    robot_id    VARCHAR(10) NOT NULL REFERENCES robot(robot_id),
    user_id     VARCHAR(50),
    event_type  VARCHAR(20) NOT NULL,
    occurred_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP
);

CREATE TABLE event_log (
    event_id     SERIAL PRIMARY KEY,
    robot_id     VARCHAR(10) NOT NULL REFERENCES robot(robot_id),
    user_id      VARCHAR(50),
    event_type   VARCHAR(30) NOT NULL,
    event_detail TEXT,
    occurred_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE session (
    session_id SERIAL PRIMARY KEY,
    robot_id   VARCHAR(10) NOT NULL REFERENCES robot(robot_id),
    user_id    VARCHAR(50) NOT NULL REFERENCES users(user_id),
    is_active  BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL
);

CREATE UNIQUE INDEX uk_active_session_user ON session (user_id) WHERE is_active;
CREATE UNIQUE INDEX uk_active_session_robot ON session (robot_id) WHERE is_active;

CREATE TABLE cart (
    cart_id    SERIAL PRIMARY KEY,
    session_id INT NOT NULL UNIQUE REFERENCES session(session_id) ON DELETE CASCADE
);

CREATE TABLE cart_item (
    item_id      SERIAL PRIMARY KEY,
    cart_id      INT NOT NULL REFERENCES cart(cart_id) ON DELETE CASCADE,
    product_name VARCHAR(200) NOT NULL,
    price        INT NOT NULL DEFAULT 0,
    quantity     INT NOT NULL DEFAULT 1,
    scanned_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_paid      BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX idx_cart_item_cart ON cart_item(cart_id);

CREATE TABLE fleet_waypoint (
    idx            INT PRIMARY KEY,
    name           VARCHAR(50)      NOT NULL,
    x              DOUBLE PRECISION NOT NULL,
    y              DOUBLE PRECISION NOT NULL,
    theta          DOUBLE PRECISION NOT NULL DEFAULT 0,
    zone_id        INT REFERENCES zone(zone_id),
    is_charger     BOOLEAN NOT NULL DEFAULT FALSE,
    is_parking     BOOLEAN NOT NULL DEFAULT FALSE,
    pickup_zone    BOOLEAN NOT NULL DEFAULT FALSE,
    holding_point  BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE fleet_lane (
    from_idx INT NOT NULL REFERENCES fleet_waypoint(idx),
    to_idx   INT NOT NULL REFERENCES fleet_waypoint(idx),
    PRIMARY KEY (from_idx, to_idx)
);
