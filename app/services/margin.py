"""
Margin model: SINGLE 6.5% spread embedded in the customer rate.

How it works:
    raw_rate      = market mid-rate (from rate_engine)
    customer_rate = raw_rate × (1 - margin_pct)     ← 6.5% spread
    gross         = amount × customer_rate
    net_to_cust   = gross                            ← no separate fee

The platform's revenue = amount × raw_rate × margin_pct.
"""

def calculate_margin(amount: float, customer_rate: float, margin_pct: float = 0.065) -> dict:
    """
    amount        : from_amount in the source currency
    customer_rate : the rate the customer sees (already includes spread)
    margin_pct    : platform margin already baked into customer_rate

    Returns the breakdown. Note: `net_to_customer` equals `gross` because
    the spread has already been applied to the rate. The `platform_fee`
    is shown for accounting, but it is NOT deducted a second time.
    """
    gross = amount * customer_rate

    # Effective fee embedded in the rate (informational only — not re-deducted)
    platform_fee = gross * (margin_pct / (1 - margin_pct))

    return {
        'converted_gross': round(gross, 8),
        'margin':          round(platform_fee, 8),
        'total_fee':       round(platform_fee, 8),
        'net_to_customer': round(gross, 8),          # spread already applied
        'margin_pct':      margin_pct,
    }
