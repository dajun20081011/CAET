-- User administration controls. Additive only; account history is preserved.
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_updated_at timestamptz;

WITH product AS (SELECT id FROM products WHERE code='cabinlingo')
INSERT INTO permissions(product_id, code, name)
SELECT product.id, item.code, item.name
FROM product CROSS JOIN (VALUES
  ('cabinlingo:user.delete','Deactivate user accounts while preserving history'),
  ('cabinlingo:user.password_reset','Reset user passwords; plaintext is never readable'),
  ('cabinlingo:user.import','Import user accounts from a validated table')
) AS item(code, name)
ON CONFLICT(product_id, code) DO UPDATE SET name=excluded.name;

WITH product AS (SELECT id FROM products WHERE code='cabinlingo')
INSERT INTO role_permissions(role_id, permission_id)
SELECT role.id, permission.id
FROM roles role
JOIN product ON role.product_id=product.id AND role.code='admin'
JOIN permissions permission ON permission.product_id=product.id
WHERE permission.code IN (
  'cabinlingo:user.delete',
  'cabinlingo:user.password_reset',
  'cabinlingo:user.import'
)
ON CONFLICT DO NOTHING;

COMMENT ON COLUMN users.password_hash IS 'PBKDF2-SHA256 password hash; plaintext is forbidden';
COMMENT ON COLUMN users.password_updated_at IS 'Timestamp of the most recent password set/reset';
