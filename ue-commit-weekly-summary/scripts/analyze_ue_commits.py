#!/usr/bin/env python3
"""Analyze UE branch commits from JSON files and produce structured analysis.

Usage:
    python3 analyze_ue_commits.py [--input-dir DIR] [--output FILE] [--branch NAME]

Options:
    --input-dir DIR    Directory containing commit JSON pages (default: /tmp)
    --output FILE      Output analysis JSON path (default: /tmp/ue_commits_analysis.json)
    --branch NAME      Branch name label for the report (default: auto-detect from filenames)

Input files should be named like: commits_p1.json, commits_p2.json, ...
Each file is a JSON array of commit objects with at least: message/title, author_name, authored_date.
"""

import json
import re
import sys
import argparse
from collections import defaultdict
from pathlib import Path


def extract_modules(message):
    """Extract module names from commit message first line."""
    modules = []
    first_line = message.split('\n')[0].split('\r')[0].strip()
    # Pattern 1: [Module] or [Module/SubModule]
    bracket_matches = re.findall(r'\[([^\]]+)\]', first_line)
    for m in bracket_matches:
        upper = m.upper()
        if any(skip in upper for skip in ['CL ', 'REVIEW', 'FYI', 'BACKOUT', ' AT]', 'SYNCED', 'LOCKDOWN']):
            continue
        if re.match(r'^(CL|at)\s', m, re.IGNORECASE):
            continue
        modules.append(m.strip())

    if not modules:
        colon_match = re.match(r'^([A-Z][A-Za-z0-9/]+)\s*[-:]\s', first_line)
        if colon_match:
            modules.append(colon_match.group(1).strip())

    if not modules:
        modules.append("Other")

    return modules


BUGFIX_KW = ['fix', 'bug', 'crash', 'issue', 'error', 'broken', 'regression', 'revert', 'backout']
FEATURE_KW = ['add', 'new', 'implement', 'support', 'enable', 'introduce']
REFACTOR_KW = ['refactor', 'cleanup', 'clean up', 'reorganize', 'rename', 'move', 'remove', 'deprecat']
OPTIMIZE_KW = ['optim', 'perf', 'speed', 'fast', 'improv', 'reduce', 'memory']


def classify_commit(title):
    t = title.lower()
    if any(k in t for k in BUGFIX_KW):
        return 'Bug修复'
    elif any(k in t for k in FEATURE_KW):
        return '新功能/增强'
    elif any(k in t for k in REFACTOR_KW):
        return '重构/清理'
    elif any(k in t for k in OPTIMIZE_KW):
        return '优化/性能'
    else:
        return '其他更新'


def load_commits(input_dir):
    """Load commits from paginated JSON files in input_dir."""
    all_commits = []
    input_path = Path(input_dir)
    for page in range(1, 100):
        # Try multiple naming conventions
        candidates = [
            input_path / f"commits_p{page}.json",
            input_path / f"ue5_commits_p{page}.json",
            input_path / f"ue6_commits_p{page}.json",
        ]
        found = False
        for fp in candidates:
            if fp.exists():
                with open(fp) as f:
                    data = json.load(f)
                    if not data:
                        continue
                    all_commits.extend(data)
                    found = True
                    break
        if not found:
            break
    return all_commits


def analyze(all_commits):
    """Analyze commits and return structured result dict."""
    if not all_commits:
        return {"stats": {"total_commits": 0, "total_modules": 0, "total_authors": 0, "date_range": "N/A"}, "modules": []}

    module_data = defaultdict(lambda: {
        'commits': [],
        'authors': defaultdict(int),
        'messages': [],
        'count': 0
    })
    author_total = defaultdict(int)

    for commit in all_commits:
        msg = commit.get('message', '') or commit.get('title', '')
        author = commit.get('author_name', 'Unknown')
        date = commit.get('authored_date', '')[:10]
        title = commit.get('title', msg.split('\n')[0].split('\r')[0])

        modules = extract_modules(msg)
        author_total[author] += 1

        for module in modules:
            mod = module_data[module]
            mod['count'] += 1
            mod['authors'][author] += 1
            mod['messages'].append({
                'title': title[:150],
                'author': author,
                'date': date
            })

    sorted_modules = sorted(module_data.items(), key=lambda x: x[1]['count'], reverse=True)

    result = {
        'stats': {
            'total_commits': len(all_commits),
            'total_modules': len(sorted_modules),
            'total_authors': len(author_total),
            'date_range': f"{all_commits[-1]['authored_date'][:10]} ~ {all_commits[0]['authored_date'][:10]}"
        },
        'modules': []
    }

    for module, data in sorted_modules:
        sorted_mod_authors = sorted(data['authors'].items(), key=lambda x: x[1], reverse=True)[:5]
        cat_commits = defaultdict(list)
        for m in data['messages']:
            cat = classify_commit(m['title'])
            cat_commits[cat].append(m['title'][:150])

        mod_info = {
            'name': module,
            'count': data['count'],
            'authors': [{'name': a, 'count': c} for a, c in sorted_mod_authors],
            'categories': {}
        }
        for cat, titles in sorted(cat_commits.items(), key=lambda x: len(x[1]), reverse=True):
            mod_info['categories'][cat] = {
                'count': len(titles),
                'titles': titles
            }
        result['modules'].append(mod_info)

    return result


def main():
    parser = argparse.ArgumentParser(description='Analyze UE branch commits')
    parser.add_argument('--input-dir', default='/tmp', help='Directory containing commit JSON pages')
    parser.add_argument('--output', default='/tmp/ue_commits_analysis.json', help='Output analysis JSON path')
    parser.add_argument('--branch', default='', help='Branch name label')
    args = parser.parse_args()

    all_commits = load_commits(args.input_dir)

    if not all_commits:
        print("No commits found. Check that commit JSON files exist in:", args.input_dir)
        sys.exit(1)

    print(f"Total commits loaded: {len(all_commits)}")
    print(f"Date range: {all_commits[-1]['authored_date'][:10]} ~ {all_commits[0]['authored_date'][:10]}")

    result = analyze(all_commits)
    if args.branch:
        result['stats']['branch'] = args.branch

    output_path = Path(args.output)
    with open(output_path, 'w') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\nAnalysis JSON saved to {output_path}")
    print(f"Stats: {result['stats']}")
    print(f"Top modules: {', '.join(m['name'] + '(' + str(m['count']) + ')' for m in result['modules'][:15])}")


if __name__ == '__main__':
    main()
