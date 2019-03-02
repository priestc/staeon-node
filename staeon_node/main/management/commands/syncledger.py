import datetime
import requests

import dateutil.parser
from django.core.management.base import BaseCommand, CommandError
from main.models import Peer, LedgerEntry

def update(response):
    j = response.json()
    for data in j['data']:
        address, amount, last_updated = data
        le = LedgerEntry.objects.get_or_create(address=address)
        le.amount = balance
        le.last_updated = last_updated
        le.save()
    return last_updated

class Command(BaseCommand):
    help = 'Sync ledger with other nodes. Called when first coming online.'

    def handle(self, *args, **options):
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
                peer.domain, last_update
            )
            print("Trying: %s" % url)
            try:
                last_update = requests.get(url, timeout=3).json()
            except (requests.exceptions.ConnectionError, ValueError)as exc:
                print("fail: %s" % exc)
                continue # try next node

            update(last_update)
