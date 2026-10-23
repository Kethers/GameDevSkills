#!/usr/bin/env bash
# Fetch UE branch commits from GitHub (public EpicGames/UnrealEngine) as fallback
# when the internal Gongfeng mirror is unavailable.
#
# Usage:
#   bash fetch_github_commits.sh <branch> [days] [output_dir] [github_token]
#
# Arguments:
#   branch        Branch name, e.g. ue5-main or ue6-main
#   days          How many days back to fetch (default: 7)
#   output_dir    Where to save commit JSON pages (default: /tmp)
#   github_token  GitHub Personal Access Token (or set GITHUB_TOKEN env var)
#
# Prerequisites:
#   - GitHub PAT with repo access to EpicGames/UnrealEngine (private repo)
#   - Set GITHUB_TOKEN env var or pass as 4th argument
#
# Note: EpicGames/UnrealEngine is a PRIVATE repo. You need:
#   1. A GitHub account linked to your Epic Games account
#   2. Access granted at https://www.unrealengine.com/ue-on-github
#   3. A PAT (classic) with 'repo' scope, or a fine-grained PAT with read access
#
# Output:
#   /tmp/commits_p1.json, /tmp/commits_p2.json, ...

set -euo pipefail

BRANCH="${1:?Usage: fetch_github_commits.sh <branch> [days] [output_dir] [github_token]}"
DAYS="${2:-7}"
OUTPUT_DIR="${3:-/tmp}"
TOKEN="${4:-${GITHUB_TOKEN:-}}"

if [ -z "${TOKEN}" ]; then
    echo "ERROR: GitHub token is required."
    echo ""
    echo "EpicGames/UnrealEngine is a private repository. To access it:"
    echo "  1. Link your GitHub account to Epic Games at:"
    echo "     https://www.unrealengine.com/ue-on-github"
    echo "  2. Create a Personal Access Token (PAT) at:"
    echo "     https://github.com/settings/tokens"
    echo "     - Classic PAT: select 'repo' scope"
    echo "     - Fine-grained PAT: grant read access to EpicGames/UnrealEngine"
    echo "  3. Set the GITHUB_TOKEN environment variable:"
    echo "     export GITHUB_TOKEN='ghp_your_token_here'"
    echo "  4. Or pass it as the 4th argument to this script."
    echo ""
    exit 1
fi

OWNER="EpicGames"
REPO="UnrealEngine"
API_BASE="https://api.github.com/repos/${OWNER}/${REPO}"

# Calculate since date (ISO 8601)
SINCE="$(date -d "-${DAYS} days" '+%Y-%m-%dT00:00:00Z' 2>/dev/null || date -v-${DAYS}d '+%Y-%m-%dT00:00:00Z')"

echo "=== Fetching commits from GitHub ==="
echo "Repo:    ${OWNER}/${REPO}"
echo "Branch:  ${BRANCH}"
echo "Since:   ${SINCE}"
echo "Output:  ${OUTPUT_DIR}"
echo ""

# Clean old commit pages
rm -f "${OUTPUT_DIR}"/commits_p*.json

PAGE=1
TOTAL=0
while true; do
    OUTPUT_FILE="${OUTPUT_DIR}/commits_p${PAGE}.json"
    echo "Fetching page ${PAGE}..."

    HTTP_CODE=$(curl -s -w "%{http_code}" -o "${OUTPUT_FILE}" \
        -H "Authorization: Bearer ${TOKEN}" \
        -H "Accept: application/vnd.github+json" \
        -H "X-GitHub-Api-Version: 2022-11-28" \
        "${API_BASE}/commits?sha=${BRANCH}&since=${SINCE}&per_page=100&page=${PAGE}")

    if [ "${HTTP_CODE}" != "200" ]; then
        echo "ERROR: GitHub API returned HTTP ${HTTP_CODE}"
        if [ "${HTTP_CODE}" = "401" ] || [ "${HTTP_CODE}" = "403" ]; then
            echo "Authentication failed. Check your GitHub token and repo access."
            echo "Ensure your GitHub account is linked to Epic Games:"
            echo "  https://www.unrealengine.com/ue-on-github"
        elif [ "${HTTP_CODE}" = "404" ]; then
            echo "Repository or branch not found. Check branch name: ${BRANCH}"
        fi
        cat "${OUTPUT_FILE}" 2>/dev/null || true
        rm -f "${OUTPUT_FILE}"
        exit 1
    fi

    # GitHub returns a different commit format; normalize to match Gongfeng format
    python3 -c "
import json, sys

with open('${OUTPUT_FILE}') as f:
    data = json.load(f)

if not isinstance(data, list) or len(data) == 0:
    with open('${OUTPUT_FILE}', 'w') as f:
        json.dump([], f)
    print('0')
    sys.exit(0)

normalized = []
for c in data:
    commit = c.get('commit', {})
    author = commit.get('author', {})
    normalized.append({
        'id': c.get('sha', ''),
        'short_id': c.get('sha', '')[:8],
        'title': commit.get('message', '').split(chr(10))[0].split(chr(13))[0],
        'message': commit.get('message', ''),
        'author_name': author.get('name', c.get('author', {}).get('login', 'Unknown')),
        'author_email': author.get('email', ''),
        'authored_date': author.get('date', ''),
        'web_url': c.get('html_url', '')
    })

with open('${OUTPUT_FILE}', 'w') as f:
    json.dump(normalized, f, ensure_ascii=False)
print(len(normalized))
" 2>/dev/null
    COUNT=$(python3 -c "import json; print(len(json.load(open('${OUTPUT_FILE}'))))" 2>/dev/null || echo "0")

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

    # GitHub rate limit: be polite
    sleep 1
done

echo ""
echo "=== Done: ${TOTAL} commits fetched across $((PAGE)) page(s) ==="
echo "Files saved to: ${OUTPUT_DIR}/commits_p*.json"
