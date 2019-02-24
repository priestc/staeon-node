import datetime
from bitcoin import ecdsa_verify, ecdsa_recover, ecdsa_sign, pubtoaddr, privtoaddr

genesis = datetime.datetime(2019, 2, 14, 10, 0)
epoch_lengh_seconds = 600
epoch_closing_seconds = 10
propagation_window_seconds = 10

class ExpiredTimestamp(Exception):
    pass

def get_epoch_range(n):
    """
    Given an epoch number, returns the start and end times for that epoch.
    """
    start =  genesis + datetime.timedelta(seconds=epoch_lengh_seconds * n)
    return start, start + datetime.timedelta(minutes=10)

def get_epoch_number(time):
    """
    For a given time, returns which epoch number that date falls in.
    """
    delta = time - genesis
    return int("%d" % (delta.total_seconds() / epoch_lengh_seconds))

def seconds_til_next_epoch(t):
    """
    How many seconds from passed in datetime object does the next epoch start?
    """
    return epoch_lengh_seconds - (
        ((t.minute % 10) * 60) + t.second + (t.microsecond / 1000000.0)
    )

def validate_timestamp(ts, now=None):
    if seconds_til_next_epoch(ts) < epoch_closing_seconds:
        raise ExpiredTimestamp("Within closing interval")
    if not now:
        now = datetime.datetime.now()
    if ts - now < datetime.timedelta(seconds=propagation_window_seconds):
        raise ExpiredTimestamp("Propagation window exceeded")
    return True


def validate_ledger_hash_push(payout_address, ledger_hash, domain, sig):
    """
    Validates that the ledger hash push is indeed signed by the pusher.
    """
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
