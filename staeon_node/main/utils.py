import uuid
import random
import datetime

from moneywagon import generate_keypair
from main.models import LedgerEntry, ValidatedTransaction
from staeon.transaction import make_transaction

def make_keys():
    keys = generate_keypair('btc', uuid.uuid4().hex)
    return keys['public']['address'], keys['private']['wif']

def make_test_tx(fee=0.01):
    spend_addr, spend_priv = make_keys()
    receive_addr, _ = make_keys()

    seed_value = random.random() * 5 + 0.1
    spend_value = seed_value - (seed_value * 0.5)
    lu = datetime.datetime.now() - datetime.timedelta(hours=1)

    LedgerEntry.objects.create(
        address=spend_addr, amount=float("%.8f" % seed_value), last_updated=lu
    )
    return make_transaction(
        [
            [spend_addr, float("%.8f" % spend_value), spend_priv]
        ],
        [
            [receive_addr, float("%.8f" % (spend_value - fee))]
        ]
    )

def benchmark_validation(n):
    txs = []
    for i in range(n):
        txs.append(make_test_tx())

    t0 = datetime.datetime.now()
    for tx in txs:
        ValidatedTransaction.record(tx)

    total = (datetime.datetime.now() - t0).total_seconds()
    print("%s transactions took %s seconds" % (n, total))
    print("Bitcoin blocksize equivalent: %s MB" % (n * 266 / (1024.0**2)))
    print("Total speed of %.3f tx/sec" % (n / total))


def blocksize_limit_for_txs(txps, txsize=226):
    """
    Given a transactions per second figure, calculate the equivalent bitcoin
    blocksize.
    """
    mbs = (txps * txsize) / (1024 * 1024.0) # megabytes per second
    return mbs * 600.0 # megabytes per 10 minutes

from hashlib import sha256
def make_txid(seed=''):
    return sha256(str(random.random()) + str(seed)).hexdigest()

def duplicates_for_shortid(txidsize, mempoolsize_mb=32, mempoolsize_kb=None):
    if mempoolsize_kb:
        n = int(mempoolsize_kb * 1024.0 / 266)
    else:
        n = int(mempoolsize_mb * 1024.0 * 1024.0 / 266)

    txids = set()
    for i in xrange(n):
        txid = make_txid(i)
        txids.add(txid[:txidsize])
    dup_count = n - len(txids)
    return dup_count

def simulate_decode_failures(txidsize, iterations=100, mempoolsize_mb=4, mempoolsize_kb=None):
    failures = 0
    for i in xrange(iterations):
        dups = duplicates_for_shortid(txidsize, mempoolsize_mb, mempoolsize_kb)
        if dups:
            print(dups)
            failures += 1

    return "%d failures out of %d blocks (%.3f%%)" % (
        failures, iterations, 100.0 * failures / iterations
    )

import hashlib
import random
def megabytes_until_duplicate(length):
    i = 0
    s = set()
    while True:
        s.add(hashlib.sha256(str(random.random()+i)).hexdigest()[:length])
        if len(s) < i:
            return i * 266.0 / 1024 / 1024 # megabytes until duplicate
        i += 1
