#!/usr/bin/env python3
"""Read-only synthetic fixture lookup; never submits real subjects to a provider."""
import argparse
import json
from pathlib import Path

FIXTURE = Path(__file__).with_name('screening_fixtures.json')
TYPES = ('sanctions', 'pep', 'adverse_media')
ALLOWED = {'SIMULATED_POTENTIAL_MATCH', 'SIMULATED_NO_MATCH', 'INCOMPLETE', 'NOT_PERFORMED'}

def lookup(subject, fixtures):
    entry = fixtures['subjects'].get(subject, {})
    coverage = {}
    for kind in TYPES:
        status = entry.get(kind, 'NOT_PERFORMED')
        if status not in ALLOWED:
            raise ValueError('Invalid fixture status')
        coverage[kind] = status
    return {'mode': 'SIMULATED', 'fixture_version': fixtures['fixture_version'], 'subject_fixture': subject,
            'coverage': coverage, 'notice': 'Fixture output only; not real screening, identity verification or an onboarding decision.'}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--subject-fixture', required=True, help='Synthetic fixture ID, never a real subject name')
    a = p.parse_args()
    print(json.dumps(lookup(a.subject_fixture, json.loads(FIXTURE.read_text())), indent=2))

if __name__ == '__main__': main()
