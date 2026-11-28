"""Extrait l'île de données RunResult d'un rapport et résume les agrégats."""
import re, sys, json, html as H
s = open(sys.argv[1]).read()
for m in re.finditer(r'<script([^>]*)>(.*?)</script>', s, re.S):
    if 'json' in m.group(1):
        try:
            d = json.loads(m.group(2))
        except Exception as e:
            continue
        if isinstance(d, dict) and 'pipelines' in d:
            print("schema", d.get('schema_version'), "policy", d['manifest'].get('failure_policy'))
            for p in d['pipelines']:
                print(p['pipeline'], p['view'], [(x['metric'], x.get('value'), x.get('support'), x.get('expected')) for x in p['conditional_aggregate']][:3])
            json.dump(d, open(sys.argv[2], 'w'), indent=1, sort_keys=True) if len(sys.argv) > 2 else None
            break
