import uuid
import random
import datetime

from moneywagon import generate_keypair
from main.models import LedgerEntry
from staeon.transaction import make_transaction

def make_keys():
    keys = generate_keypair('btc', uuid.uuid4().hex)
    return keys['public']['address'], keys['private']['wif']

def make_test_tx(fee=0.01):
    spend_addr, spend_priv = make_keys()
    receive_addr, _ = make_keys()

    seed_value = random.random() * 5
    spend_value = seed_value - (seed_value * 0.27)
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
