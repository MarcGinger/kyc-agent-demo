#!/usr/bin/env python3
"""Cross-check one direct owner and a single intermediate tier; no general graph traversal."""
import argparse
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path

def check(data):
    def pct(value):
        v = Decimal(str(value))
        if not v.is_finite() or not 0 <= v <= 100: raise ValueError('Percentage out of range')
        return v
    tier = pct(data['intermediate']['percent'])
    results = []
    for row in data['owners']:
        stated = pct(row['stated_effective_percent'])
        computed = pct(row['direct_percent']) if row['route'] == 'direct' else tier * pct(row['direct_percent']) / Decimal(100) if row['route'] == 'intermediate' else None
        if computed is None: raise ValueError('Unknown route')
        results.append({'owner': row['owner'], 'calculated_percent': str(computed), 'declared_percent': str(stated),
                        'matches': computed == stated, 'direct_source': row['direct_source'],
                        'intermediate_source': data['intermediate']['source'] if row['route'] == 'intermediate' else None,
                        'declaration_source': row['declaration_source']})
    return {'method':'single-tier arithmetic cross-check; inputs require human verification', 'results': results}

def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('input', type=Path); a = p.parse_args()
    print(json.dumps(check(json.loads(a.input.read_text())), indent=2))

if __name__ == '__main__': main()
