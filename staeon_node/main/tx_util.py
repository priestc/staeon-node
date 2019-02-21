import datetime
import random

from bitcoin import (
    ecdsa_verify, ecdsa_recover, ecdsa_sign, pubtoaddr, privtoaddr, is_address
)

class InvalidTransaction(Exception):
    pass

class InvalidSignature(InvalidTransaction):
    pass

class InvalidAmounts(InvalidTransaction):
    pass

class InvalidAddress(InvalidTransaction):
    pass

class InvalidFee(InvalidTransaction):
    pass

def _cut_to_8(amount):
    "Cut decimals to 8 places"
    return float("%.8f" % amount)

def _process_outputs(outputs, timestamp):
    outs = []
    total_out = 0
    for out in sorted(outputs, key=lambda x: x[0]):
        address, amount = out
        if amount <= 0:
            raise InvalidAmounts("Output can't be zero or negative")
        total_out += _cut_to_8(amount)
        outs.append("%s,%s" % (address, amount))
        if not is_address(address) or not address.startswith("1"):
            raise InvalidAddress("Invalid address: %s" % address)

    outs.append(timestamp)
    return total_out, ";".join(outs)

def make_transaction(inputs, outputs):
    timestamp = datetime.datetime.now().isoformat()
    out_total, out_msg = _process_outputs(outputs, timestamp)

    tx = {'inputs': [], 'outputs': [], 'timestamp': timestamp}

    in_total = 0
    for in_ in inputs:
        address, amount, privkey = in_
        if amount <= 0:
            raise InvalidAmounts("Input can't be zero or negative")

        msg = "%s%s%s" % (address, _cut_to_8(amount), out_msg)
        sig = ecdsa_sign(msg, privkey)
        in_total += amount
        tx['inputs'].append([address, amount, sig])

    if in_total < out_total:
        raise InvalidAmounts("Not enough inputs for outputs")

    random.shuffle(outputs)
    tx['outputs'] = outputs
    return tx

def validate_transaction(tx, min_fee=0.01):
    """
    Validates that the passed in transaction object is valid in terms of
    cryptography. UTXO validation does not happen here.
    """
    out_total, out_msg = _process_outputs(tx['outputs'], tx['timestamp'])

    in_total = 0
    for i, input in enumerate(tx['inputs']):
        address, amount, sig = input
        amount = _cut_to_8(amount)
        if amount <= 0:
            raise InvalidAmounts("Input %s can't be zero or negative" % i)

        message = "%s%s%s" % (address, amount, out_msg)
        in_total += amount
        try:
            pubkey = ecdsa_recover(message, sig)
        except:
            raise InvalidSignature("Signature %s not valid" % i)

        valid_sig = ecdsa_verify(message, sig, pubkey)
        valid_address = pubtoaddr(pubkey) == address
        if not valid_sig or not valid_address:
            raise InvalidSignature("Signature %s not valid" % i)

    if in_total < out_total:
        raise InvalidAmounts("Input amount does not exceed output amount")

    fee = in_total - out_total
    if fee < min_fee:
        raise InvalidFee("Fee of %.8f below min fee of %.8f" % (fee, min_fee))

    return True

def make_txid(tx):
    msg = tx['timestamp']
    for output in tx['outputs']:
        msg += output[0] + output[1]

    for input in tx['inputs']:
        address, amount, sig = input
        msg += "%s%s" % (address, amount)

    return hashlib.sha256(msg).hexdigest()

def make_transaction_authorization(tx, node):
    txid = make_txid(tx)
    msg = "%s%s" % (txid, node['domain'])
    return {
        'domain': node['domain'],
        'signature': ecdsa_sign(msg, node['private_key'])
    }

def validate_transaction_authorization(tx, auth):
    txid = make_txid(tx)
    sig = auth['signature']
    msg = "%s%s" % (txid, auth['domain'])
    auth_pubkey = ecdsa_recover(msg, sig)
    if not pubtoaddr(auth_pubkey) == auth['payout_address']:
        raise Exception("Invalid Authprization: Signing key does not match payout address")
    if not ecdsa_verify(msg, sig, auth_pubkey):
        raise Exception("Invalid authorization: Invalid signature")
    return True

if __name__ == '__main__':

    def assert_raises(call, exception, msg):
        try:
            call()
        except exception:
            return
        assert False, msg

    # testing make_transaction makes a valid transaction
    i = [
        ['18pvhMkv1MZbZZEncKucAmVDLXZsD9Dhk6', 3.2, 'KwuVvv359oft9TfzyYLAQBgpPyCFpcTSrV9ZgJF9jKdT8jd7XLH2'],
        ['14ZiHtrmT6Mi4RT2Liz51WKZMeyq2n5tgG', 0.5, 'KxWoW9Pj45UzUH1d5p3wPe7zxbdJqU7HHkDQF1YQS1AiQg9qeZ9H']
    ]
    o = [
        ['16ViwyAVeKtz4vbTXWRSYgadT5w3Rj3yuq', 2.2],
        ['18pPTxvTc9rJZfD2tM1bNYHFhAcZjgqEdQ', 1.4]
    ]
    assert validate_transaction(make_transaction(i, o)), "Basic transaction creation fails"

    # testing invalid signature fails
    bad_sig = make_transaction(i, o)
    bad_sig['inputs'][0][2] = "23784623kjhdfkjashdfkj837242387"
    assert_raises(
        lambda: validate_transaction(bad_sig), InvalidSignature,
        "Invalid Signature not happening when sig is edited"
    )

    # testing changing values within already made transaction fails validation
    bad_tx = make_transaction(i, o)
    bad_tx['inputs'][0][1] = 0.2
    assert_raises(
        lambda: validate_transaction(bad_tx), InvalidSignature,
        "Invalid Signature not happening when amount is changed"
    )

    # testing make_transaction fails when you make a tx with more outputs than inputs
    bad_o = [
        ['16ViwyAVeKtz4vbTXWRSYgadT5w3Rj3yuq', 2.2],
        ['18pPTxvTc9rJZfD2tM1bNYHFhAcZjgqEdQ', 9.4]
    ]
    assert_raises(
        lambda: make_transaction(i, bad_o), InvalidAmounts,
        "Invalid Amount not happening when outputs exceed inputs when making new trasnaction"
    )

    # testing make_transaction fails when you add a zero input
    bad_o = [
        ['16ViwyAVeKtz4vbTXWRSYgadT5w3Rj3yuq', 0],
        ['18pPTxvTc9rJZfD2tM1bNYHFhAcZjgqEdQ', 9.4]
    ]
    assert_raises(
        lambda: make_transaction(i, bad_o), InvalidAmounts,
        "Invalid Amount not happening when zero input is tried"
    )

    # testing make_transaction fails when you add a negative input
    bad_o = [
        ['16ViwyAVeKtz4vbTXWRSYgadT5w3Rj3yuq', -42.07],
        ['18pPTxvTc9rJZfD2tM1bNYHFhAcZjgqEdQ', 9.4]
    ]
    assert_raises(
        lambda: make_transaction(i, bad_o), InvalidAmounts,
        "Invalid Amount not happening when negative input is tried on transaction creation"
    )

    # testing transaction with valid signatures, but invalid amounts are caught as invalid
    bad_tx = {
        'inputs': [
            ['18pvhMkv1MZbZZEncKucAmVDLXZsD9Dhk6',3.2,'ILgSi/FsQX2pL5MPoqxvVOAk5o8Njl7a8+ruXXXgU4UIfMyYXx+yytSevMD55ZNceC+1ReVWZgXuFu8iUtOkz2k='],
            ['14ZiHtrmT6Mi4RT2Liz51WKZMeyq2n5tgG',0.5,'IEcFAR6XEdvNmivQDrCEg1DBMiYkwGR+KgB3sVZXdcVTbBD8qfR310m/p/Q5UFRFQ57Cc2mnY+bw8Qr0GQge8So=']
        ],
        'outputs': [
            ['18pPTxvTc9rJZfD2tM1bNYHFhAcZjgqEdQ', 9.4],
            ['16ViwyAVeKtz4vbTXWRSYgadT5w3Rj3yuq', 2.2]
        ],
        'timestamp': '2019-02-13T19:14:27.882253'
    }
    assert_raises(
        lambda: validate_transaction(bad_tx), InvalidAmounts,
        "Invalid Amount not happening when outputs exceed inputs when validating"
    )

    # valid signatures, but negative amounts
    bad_tx = {
        'inputs': [
            ['18pvhMkv1MZbZZEncKucAmVDLXZsD9Dhk6',3.2,'H/vTjUELpBg7uB08QOprZCxkbnZTMefq5VJqgZPzzpLtFeBKClAFEPhzYtYQl5tcK6oq0V+GqIrE8dPUR2teLSg='],
            ['14ZiHtrmT6Mi4RT2Liz51WKZMeyq2n5tgG',0.5,'H5qfLufve25jEf8H2qydWKPG9haSgrFfNYct0G9pmqDZeq1fM1fdZzoMJ8e2H9YMVr6t9wpgJpYwEoWA4I4gJl8=']
        ],
        'outputs': [
            ['18pPTxvTc9rJZfD2tM1bNYHFhAcZjgqEdQ', -9.4],
            ['16ViwyAVeKtz4vbTXWRSYgadT5w3Rj3yuq', 2.2]
        ],
        'timestamp': '2019-02-13T19:47:07.354060'
    }
    assert_raises(
        lambda: validate_transaction(bad_tx), InvalidAmounts,
        "Invalid Amount not happening when outputs is negative when validating"
    )

    # testing that a transaction made with a valid signature but invalid address is caught
    bad_tx = {
        'inputs': [
            ['18pvhMkv1MZbZZEncKucAmVDLXZsD9Dhk6',3.2,'IGFbFxYvnBuYh/b5f6C7BeM8hYABOY/yTON0aEKV0XyPZgkmVkdKrqS/a+4p5tiIC1N4R1y3CyR3fydhWc/WDyc='],
            ['14ZiHtrmT6Mi4RT2Liz51WKZMeyq2n5tgG',0.5,'IF8niJ+u11k3H/JUTWt3dRlmZ8v3Ou8gfwHuuLRPlUHGSc4O2TxgULqBGaQO1BcaAMW/zk89f85se3Rcq+guQNc=']],
        'outputs': [
            ['YYY', 2.2], ['XXX', 1.4]
        ],
        'timestamp': '2019-02-17T12:02:41.843542'
    }
    assert_raises(
        lambda: validate_transaction(bad_tx), InvalidAddress,
        "Invalid address not being caught."
    )

    # testing make_transaction fails on trying to use a "3" address
    i = [
        ['18pvhMkv1MZbZZEncKucAmVDLXZsD9Dhk6', 3.2, 'KwuVvv359oft9TfzyYLAQBgpPyCFpcTSrV9ZgJF9jKdT8jd7XLH2'],
        ['14ZiHtrmT6Mi4RT2Liz51WKZMeyq2n5tgG', 0.5, 'KxWoW9Pj45UzUH1d5p3wPe7zxbdJqU7HHkDQF1YQS1AiQg9qeZ9H']
    ]
    o = [['3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy', 2.2]]
    assert_raises(
        lambda: make_transaction(i, o), InvalidAddress,
        "3 addresses not caught as invalid"
    )

    print("all tests pass")
