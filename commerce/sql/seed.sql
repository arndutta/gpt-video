-- Named parameterized DML; commerce.seed binds generated data in a transaction.
-- name: products
INSERT INTO products (
    sku, name, category, family_id, size, currency, cost, map_price,
    min_price, max_price, max_change_pct, minimum_margin_pct, rounding_increment
) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?);

-- name: prices
INSERT INTO prices (sku, current_price, price_version, updated_at) VALUES (?,?,?,?);

-- name: inventory
INSERT INTO inventory (sku, on_hand, updated_at) VALUES (?,?,?);

-- name: sales
INSERT INTO sales (sku, date, price, units, promotion, seasonal_index) VALUES (?,?,?,?,?,?);

-- name: truth
INSERT INTO evaluation_truth (sku, elasticity, baseline_demand) VALUES (?,?,?);

-- name: metadata
INSERT INTO metadata (key, value) VALUES (?,?);
