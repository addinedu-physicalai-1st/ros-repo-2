-- ShopPinkki AI Schema (PostgreSQL 17)
CREATE EXTENSION IF NOT EXISTS vector;

DROP TABLE IF EXISTS PRODUCT_TEXT_EMBEDDING;
DROP TABLE IF EXISTS ZONE_TEXT_EMBEDDING;
DROP TABLE IF EXISTS PRODUCT;
DROP TABLE IF EXISTS ZONE;

CREATE TABLE ZONE (
    zone_id     INT PRIMARY KEY,
    zone_name   VARCHAR(100) NOT NULL UNIQUE,
    zone_type   VARCHAR(50)  NOT NULL,
    waypoint_x  FLOAT        NOT NULL,
    waypoint_y  FLOAT        NOT NULL,
    waypoint_theta FLOAT     NOT NULL
);

CREATE TABLE PRODUCT (
    product_id   SERIAL PRIMARY KEY,
    product_name VARCHAR(200) NOT NULL UNIQUE,
    zone_id      INT          NOT NULL REFERENCES ZONE(zone_id),
    price        DECIMAL(10,2)
);

CREATE TABLE PRODUCT_TEXT_EMBEDDING (
    id           SERIAL PRIMARY KEY,
    product_id   INT NOT NULL REFERENCES PRODUCT(product_id),
    text         TEXT NOT NULL,
    embedding    VECTOR(384),
    model_name   VARCHAR(100) NOT NULL
);

CREATE TABLE ZONE_TEXT_EMBEDDING (
    id           SERIAL PRIMARY KEY,
    zone_id      INT NOT NULL REFERENCES ZONE(zone_id),
    text         TEXT NOT NULL,
    embedding    VECTOR(384),
    model_name   VARCHAR(100) NOT NULL
);
