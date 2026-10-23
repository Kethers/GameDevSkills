#!/usr/bin/env bash
# Fetch UE branch commits from Gongfeng (internal GitLab mirror) via mcporter-internal.
#
# Usage:
#   bash fetch_gongfeng_commits.sh <branch> [days] [output_dir]
#
# Arguments:
#   branch      Branch name, e.g. ue5-main or ue6-main
#   days        How many days back to fetch (default: 7)
#   output_dir  Where to save commit JSON pages (default: /tmp)
#
# Prerequisites:
#   - mcporter-internal installed and gongfeng service healthy
#   - Run `mcporter-internal list` to verify
#
# Output:
#   /tmp/commits_p1.json, /tmp/commits_p2.json, ...

set -euo pipefail

BRANCH="${1:?Usage: fetch_gongfeng_commits.sh <branch> [days] [output_dir]}"
DAYS="${2:-7}"
OUTPUT_DIR="${3:-/tmp}"

PROJECT_ID="UnrealEngine/UnrealEngine-1"

# Calculate date range (Beijing time +0800)
SINCE="$(date -d "-${DAYS} days" '+%Y-%m-%dT00:00:00+08:00' 2>/dev/null || date -v-${DAYS}d '+%Y-%m-%dT00:00:00+08:00')"
UNTIL="$(date '+%Y-%m-%dT23:59:59+08:00')"

echo "=== Fetching commits from Gongfeng ==="
echo "Project: ${PROJECT_ID}"
echo "Branch:  ${BRANCH}"
echo "Range:   ${SINCE} ~ ${UNTIL}"
echo "Output:  ${OUTPUT_DIR}"
echo ""

# Clean old commit pages
rm -f "${OUTPUT_DIR}"/commits_p*.json

PAGE=1
TOTAL=0
while true; do
    OUTPUT_FILE="${OUTPUT_DIR}/commits_p${PAGE}.json"
    echo "Fetching page ${PAGE}..."

    mcporter-internal call "gongfeng.get_commits_list(project_id: '${PROJECT_ID}', ref_name: '${BRANCH}', per_page: '100', page: '${PAGE}', since: '${SINCE}', until: '${UNTIL}')" > "${OUTPUT_FILE}" 2>/dev/null

    # Extract JSON array from mcporter output (it may have extra text)
    # Try to parse the file as JSON; if it fails, try extracting the JSON array
    if python3 -c "import json; d=json.load(open('${OUTPUT_FILE}')); assert isinstance(d, list)" 2>/dev/null; then
        COUNT=$(python3 -c "import json; print(len(json.load(open('${OUTPUT_FILE}'))))")
    else
        # Try to extract JSON array from the output
        python3 -c "
import json, re, sys
text = open('${OUTPUT_FILE}').read()
# Find the first [ and last ]
start = text.find('[')
end = text.rfind(']')
if start >= 0 and end > start:
    try:
        data = json.loads(text[start:end+1])
        with open('${OUTPUT_FILE}', 'w') as f:
            json.dump(data, f, ensure_ascii=False)
        print(len(data))
        sys.exit(0)
    except json.JSONDecodeError:
        pass
print('0')
sys.exit(0)
" 2>/dev/null
        COUNT=$(python3 -c "import json; print(len(json.load(open('${OUTPUT_FILE}'))))" 2>/dev/null || echo "0")
    fi

    if [ "${COUNT}" = "0" ]; then
        rm -f "${OUTPUT_FILE}"
        echo "Page ${PAGE}: empty, done."
        break
    fi

    TOTAL=$((TOTAL + COUNT))
    echo "Page ${PAGE}: ${COUNT} commits (total so far: ${TOTAL})"

    if [ "${COUNT}" -lt 100 ]; then
        echo "Last page reached."
        break
    fi

    PAGE=$((PAGE + 1))
done

echo ""
echo "=== Done: ${TOTAL} commits fetched across $((PAGE)) page(s) ==="
echo "Files saved to: ${OUTPUT_DIR}/commits_p*.json"
