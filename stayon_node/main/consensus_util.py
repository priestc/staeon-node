from bitcoin import ecdsa_verify, ecdsa_recover, ecdsa_sign, pubtoaddr, privtoaddr

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
