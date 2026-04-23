"""
Fetch SWE-bench Lite instances for our 3 target repos:
  - Small:  pallets/flask (3 instances) + pallets/click (our existing 15)
  - Medium: pytest-dev/pytest (17 instances) 
  - Large:  django/django (114 instances, pick 15)

Even single-file fixes are valid: we measure which FILES the retriever 
surfaces. MRR shows if GraphRAG ranks the correct file higher.
"""
import urllib.request, json, re

ALL = []
for offset in range(0, 400, 100):
    url = f"https://datasets-server.huggingface.co/rows?dataset=princeton-nlp%2FSWE-bench_Lite&config=default&split=test&offset={offset}&length=100"
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=30) as resp:
            data = json.loads(resp.read().decode())
            ALL.extend(row['row'] for row in data.get('rows', []))
    except:
        break

print(f"Fetched {len(ALL)} total instances\n")

def extract_py_files(patch):
    return sorted(set(
        m.group(2) for m in re.finditer(r'diff --git a/(.*?) b/(.*?)(?:\n|$)', patch)
        if m.group(2).endswith('.py')
    ))

TARGET_REPOS = ['django/django', 'pytest-dev/pytest', 'scikit-learn/scikit-learn']
selected = {}

for inst in ALL:
    repo = inst['repo']
    if repo not in TARGET_REPOS:
        continue
    
    py_files = extract_py_files(inst.get('patch', ''))
    if not py_files:
        continue
    
    if repo not in selected:
        selected[repo] = []
    
    selected[repo].append({
        'instance_id': inst['instance_id'],
        'repo': repo,
        'base_commit': inst['base_commit'],
        'problem_statement': inst['problem_statement'],
        'relevant_files': py_files,
        'num_files': len(py_files),
        'difficulty': inst.get('difficulty', 'unknown'),
        # Convert to our evaluation format
        'question': inst['problem_statement'][:500],
        'category': 'swebench_lite',
    })

# Pick 15 from django (most diverse), all from smaller repos
for repo in selected:
    if len(selected[repo]) > 15:
        # Pick diverse: sort by files touched, take first 15
        selected[repo] = selected[repo][:15]

print("=== SELECTED INSTANCES ===\n")
total = 0
for repo, instances in sorted(selected.items()):
    print(f"{repo} ({len(instances)} instances):")
    for inst in instances:
        files_str = ', '.join(inst['relevant_files'])
        q = inst['problem_statement'][:80].replace('\n', ' ')
        print(f"  [{inst['instance_id']}]")
        print(f"    Q: {q}...")
        print(f"    Files: {files_str}")
    total += len(instances)
    print()

print(f"Total selected: {total} instances across {len(selected)} repos")

# Save in our evaluation format
output = {
    'metadata': {
        'source': 'SWE-bench Lite (princeton-nlp)',
        'selection_criteria': 'All Python-file instances from target repos, max 15 per repo',
        'repos': list(selected.keys()),
    },
    'instances': {}
}
for repo, instances in selected.items():
    output['instances'][repo] = instances

with open('data/swebench/swebench_lite_selected.json', 'w') as f:
    json.dump(output, f, indent=2)
print(f"\nSaved to data/swebench/swebench_lite_selected.json")
