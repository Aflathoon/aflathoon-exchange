"""Stubs — wire to real providers before going live."""
def screen_sanctions(name, country):
    return {'status':'clear','matches':[]}
def check_pep(name):
    return {'status':'clear','is_pep':False}
def assess_transaction_risk(amount, from_cur, to_cur):
    score, flags = 0, []
    if amount > 10000: score += 20; flags.append('high_value')
    if from_cur == to_cur: score += 10; flags.append('same_currency')
    return {'score': min(score,100), 'flags': flags,
            'level':'low' if score < 30 else 'medium'}
