"""Validate rule-result structure, not the truth of any outcome."""

def validate_outcomes(outcomes, policy, pack_type):
    if not isinstance(outcomes, list):
        raise ValueError('rule_outcomes must be a list')
    rules = {r['id']: r for r in policy['rules']}
    expected = {r['id'] for r in policy['rules'] if r['applies_to'] in (pack_type, 'both')}
    seen = {}
    for item in outcomes:
        if not isinstance(item, dict): raise ValueError('Invalid rule outcome')
        rid, status = item.get('rule_id'), item.get('outcome')
        if rid not in rules: raise ValueError('Unknown rule ID')
        if rid in seen: raise ValueError('Duplicate rule outcome')
        if rid not in expected: raise ValueError('Inapplicable rule outcome')
        if status not in ('satisfied', 'gap', 'unknown'): raise ValueError('Invalid outcome')
        if not isinstance(item.get('explanation'), str) or not item['explanation'].strip(): raise ValueError('Missing explanation')
        seen[rid] = item
    if set(seen) != expected: raise ValueError('Missing applicable rule outcomes')
    result = [seen[r['id']] if r['id'] in seen else {'rule_id':r['id'], 'outcome':'not_applicable', 'explanation':'Rule does not apply to this pack type.'} for r in policy['rules']]
    return result, [item for item in result if item['outcome'] == 'gap']
