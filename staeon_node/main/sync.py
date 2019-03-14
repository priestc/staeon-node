from __future__ import print_function

import datetime
import requests

import dateutil.parser
from main.models import Peer, LedgerEntry
from staeon.network import SEED_NODES

def _update_ledger(response):
    j = response.json()
    for data in j['data']:
        address, amount, last_updated = data
        le,c = LedgerEntry.objects.get_or_create(address=address)
        le.amount = balance
        le.last_updated = last_updated
        le.save()
    return last_updated

def sync_ledger():
    try:
        last_update = LedgerEntry.objects.latest().last_updated
    except LedgerEntry.DoesNotExist:
        last_update = None

    print("Last updated: %s" % (
        "%s (%s ago)" % (
            last_update, datetime.datetime.now() - last_update
        ) if last_update else "Never"
    ))

    peers = Peer.objects.all().order_by("?")
    for peer in peers:
        url = "https://%s/staeon/sync?start=%s" % (
            peer.domain, last_update or "None"
        )
        print("Trying: %s" % url)
        try:
            response = requests.get(url, timeout=3).json()
        except (requests.exceptions.ConnectionError, ValueError)as exc:
            print("fail: %s" % exc)
            continue # try next node

        _update_ledger(response)

def _update_peers(j):
    """
    Extracts the peers from seed node and enters them into the database.
    Returns True when it fetches the last page.
    """
    if not j['peers']:
        return True # empty list, fetching complete
    for peer in j['peers']:
        p, c = Peer.objects.get_or_create(domain=peer['domain'])
        p.reputation = peer['reputaion']
        p.payout_address = peer['payout_address']
        p.first_registered = dateutil.parser.parse(peer['first_registered'])
        p.save()
    return False

def _sync_from_seed(seed_domain):
    while True:
        url = "https://%s/staeon/peers?page=%s" % (seed_domain, page)
        try:
            response = requests.get(url).json()
        except (requests.exceptions.ConnectionError, ValueError) as exc:
            print("fail: %s" % exc)
            return False # seed is down, try another seed

        if _update_peers(response):
            return True
        else:
            page += 1

def sync_peers():
    page = 1
    for seed_domain in SEED_NODES:
        if _sync_from_seed(seed_domain):
            break # break when sync completes
    else:
        print "peer sync not complete, try again later"
        return False
    return True
