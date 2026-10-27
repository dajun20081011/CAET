#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root_dir"

grep -q -- '--focus-ring' frontend/src/styles/index.css
grep -q 'prefers-reduced-motion' frontend/src/styles/index.css
! grep -R -n 'fonts.googleapis.com' frontend/src
for component in PageState AiScoreCard AudioEvidencePlayer FeedbackCard BottomNav; do
  test -f "frontend/src/components/${component}.vue"
done
grep -q '/student/tasks' frontend/src/components/BottomNav.vue
grep -q '<AiScoreCard' frontend/src/views/EvaluatorView.vue
grep -q '<FeedbackCard' frontend/src/views/RecordView.vue

cd frontend
npm run build

echo 'PHASE6_DESIGN_SYSTEM=PASS'
echo 'PHASE6_RESPONSIVE=PASS'
echo 'PHASE6_FRONTEND_BUILD=PASS'
echo '>>> CABINLINGO PHASE6 UI VERIFY GO <<<'
