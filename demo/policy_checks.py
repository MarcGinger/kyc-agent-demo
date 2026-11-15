"""Date boundaries and rule scope for DEMO-1.0; not a factual assessment."""
import calendar
from datetime import date

def applicable_rules(policy, pack_type):
    if pack_type not in ('person', 'company'):
        raise ValueError('invalid pack type')
    return [rule for rule in policy['rules'] if rule['applies_to'] in (pack_type, 'both')]

def three_month_window(assessment_date):
    month = assessment_date.month - 3
    year = assessment_date.year
    if month <= 0:
        month += 12
        year -= 1
    day = min(assessment_date.day, calendar.monthrange(year, month)[1])
    return date(year, month, day), assessment_date

def expired(expiry, assessment_date):
    return None if expiry is None else expiry < assessment_date
