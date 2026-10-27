-- Phase 14: original course documents and optional audio/video attachments.
-- Additive only: existing content and training history are preserved.

ALTER TABLE cl_content_items ADD COLUMN IF NOT EXISTS document_file_id uuid REFERENCES files(id);
ALTER TABLE cl_content_items ADD COLUMN IF NOT EXISTS document_page_no integer;
ALTER TABLE cl_content_items ADD COLUMN IF NOT EXISTS document_page_count integer;

CREATE INDEX IF NOT EXISTS idx_cl_content_items_document_file
  ON cl_content_items(document_file_id) WHERE document_file_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_cl_content_assets_content
  ON cl_content_assets(content_item_id, created_at);

ALTER TABLE cl_content_assets ADD COLUMN IF NOT EXISTS asset_role text NOT NULL DEFAULT 'attachment';
