-- Management P0 fields. Additive only; safe to run on an existing staging database.
ALTER TABLE cl_broadcasts ADD COLUMN IF NOT EXISTS updated_by uuid REFERENCES users(id);
ALTER TABLE cl_broadcasts ADD COLUMN IF NOT EXISTS updated_at timestamptz;
ALTER TABLE cl_broadcasts ADD COLUMN IF NOT EXISTS archived_at timestamptz;
ALTER TABLE cl_broadcasts ADD COLUMN IF NOT EXISTS archived_by uuid REFERENCES users(id);
ALTER TABLE users ADD COLUMN IF NOT EXISTS employee_no text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS organization_id uuid REFERENCES organizations(id);
ALTER TABLE users ADD COLUMN IF NOT EXISTS department_id uuid REFERENCES departments(id);
ALTER TABLE users ADD COLUMN IF NOT EXISTS class_id uuid REFERENCES classes(id);
ALTER TABLE users ADD COLUMN IF NOT EXISTS deactivated_reason text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at timestamptz;
ALTER TABLE cl_recordings ADD COLUMN IF NOT EXISTS audio_ref text;
ALTER TABLE cl_recordings ADD COLUMN IF NOT EXISTS processing_status text NOT NULL DEFAULT 'uploaded';
CREATE INDEX IF NOT EXISTS idx_users_employee_no ON users(employee_no);
CREATE INDEX IF NOT EXISTS idx_users_class_id ON users(class_id);
