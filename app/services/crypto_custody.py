"""
CRITICAL WARNING #2: NEVER store crypto private keys on this server.

This module is deliberately a stub. Any real signing must go through:
  - Fireblocks / BitGo / Copper (custody APIs), or
  - Hardware Security Module (HSM), or
  - Multi-signature wallet with keys held by independent operators.

The web app ONLY calls this module to REQUEST signatures. It never sees keys.
"""
import os

CUSTODY_MODE = os.getenv('CRYPTO_CUSTODY_MODE','external_multisig')
PROVIDER     = os.getenv('CRYPTO_CUSTODY_PROVIDER','none')
HOT_MAX_USD  = float(os.getenv('CRYPTO_HOT_WALLET_MAX_USD','5000'))

class CustodyNotConfigured(RuntimeError): pass

def request_withdrawal(address, amount, asset, usd_value):
    if PROVIDER == 'none':
        raise CustodyNotConfigured(
            'No custody provider configured. Set CRYPTO_CUSTODY_PROVIDER '
            'and wire the real API before enabling withdrawals.')
    if usd_value > HOT_MAX_USD:
        # Force multi-sig approval workflow
        return {'status':'pending_multisig','requires_approvals':2}
    # Call provider API here
    return {'status':'submitted'}

def health_check():
    return {'mode': CUSTODY_MODE, 'provider': PROVIDER,
            'hot_wallet_max_usd': HOT_MAX_USD,
            'on_server_private_keys': False}
