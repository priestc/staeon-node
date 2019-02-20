import datetime
from bitcoin import ecdsa_verify, ecdsa_recover, ecdsa_sign, pubtoaddr, privtoaddr

genesis = datetime.datetime(2019, 2, 14, 10, 0)

def get_epoch_range(n):
    """
    Given an epoch number, returns the start and end times for that epoch.
    """
    start =  genesis + datetime.timedelta(minutes=10 * n)
    return start, start + datetime.timedelta(minutes=10)

def get_epoch_number(time):
    """
    For a given time, returns which epoch number that date falls in.
    """
    delta = time - genesis
    return int("%d" % (delta.total_seconds() / 600))

def validate_ledger_hash_push(payout_address, ledger_hash, domain, sig):
    msg = "%s%s" % (ledger_hash, domain)
    try:
        pubkey = ecdsa_recover(msg, sig)
    except:
        raise Exception("Can't recover pubkey from signature")

    if not pubtoaddr(pubkey) == payout_address:
        raise Exception("Incorrect signing key")

    if not ecdsa_verify(msg, sig, pubkey):
        raise Excception("Invalid Signature")

    return True
