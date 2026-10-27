#!/usr/bin/env bash
# Read-only deployment gate. Does not source, print or modify .env; no migrations.
set -euo pipefail
compose_file="${1:-docker-compose.production.yml}"
if [[ ! -f "$compose_file" ]]; then
  echo 'Compose file not found; run in the existing deployment directory.' >&2
  exit 1
fi
inspection=$(docker compose -f "$compose_file" exec -T postgres sh -c 'psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -At' <<'SQL'
SELECT 'courses=' || (to_regclass('public.cl_courses') IS NOT NULL);
SELECT 'tasks=' || (to_regclass('public.cl_practice_assignments') IS NOT NULL);
SELECT 'learning_cards_0017=' || (to_regclass('public.cl_learning_cards') IS NOT NULL);
SELECT 'card_reads_0018=' || (to_regclass('public.cl_learning_card_reads') IS NOT NULL);
SELECT 'card_content_link=' || EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='cl_content_items' AND column_name='learning_card_id');
SELECT 'broadcast_source_0016=' || EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema='public' AND table_name='cl_course_versions' AND column_name='source_broadcast_script_id');
SQL
)
printf '%s\n' "$inspection"
if [[ "$inspection" == *'=false'* ]]; then
  echo 'Required schema is missing. Stop; no migration or deployment was performed.' >&2
  exit 1
fi
echo 'Read-only inspection complete. Any false result requires a reviewed upgrade; this script applies nothing.'
