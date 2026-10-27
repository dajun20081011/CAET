-- Non-destructive production authentication migration.
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS token_version integer NOT NULL DEFAULT 1;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_at timestamptz;

CREATE TABLE IF NOT EXISTS role_permissions (
  role_id uuid NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
  permission_id uuid NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
  PRIMARY KEY(role_id, permission_id)
);

CREATE INDEX IF NOT EXISTS idx_product_memberships_user_status
  ON product_memberships(user_id, status);
CREATE INDEX IF NOT EXISTS idx_user_roles_user ON user_roles(user_id);

COMMENT ON COLUMN users.password_hash IS 'PBKDF2-SHA256 password hash; plaintext is forbidden';
