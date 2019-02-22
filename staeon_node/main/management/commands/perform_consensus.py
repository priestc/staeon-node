import datetime

from django.core.management.base import BaseCommand, CommandError
from main.models import Peer, LedgerEntry, LedgerHash
from main.consensus_util import get_epoch_number

class Command(BaseCommand):
    help = 'Starts the consensus process. Called every 10 minutes.'

    def add_arguments(self, parser):
        parser.add_argument('--rank', type=int, help='calculate as rank')

    def handle(self, *args, **options):
        if options['rank']:
            rank = options['rank']
            node = Peer.get_by_rank(rank)
        else:
            node = Peer.my_node()
            rank = node.rank()

        epoch = get_epoch_number(datetime.datetime.now())

        if LedgerHash.object.filter(epoch=epoch).exists():
            raise Exception("Epoch consensus already performed")

        ledger_hash = LedgerEntry.ledger_hash(epoch)
        LedgerHash.objects.create(epoch=epoch, hash=ledger_hash)

        peers = list(Peer.objects.all().order_by('reputation', 'first_registered'))

        getting_pulled_from = []
        peers_to_pull_from = []
        for i in range(0, 5):
            shuffled = Peer.shuffle(peers, ledger_hash, n=i)
            peers_to_pull_from.append(shuffled[rank])
            index_of_puller = shuffled.index(node)
            getting_pulled_from.append(peers[index_of_puller])

        getting_pushed_to = []
        peers_to_push_to = []
        for i in range(5, 10):
            shuffled = Peer.shuffle(peers, ledger_hash, n=i)
            peers_to_push_to.append(shuffled[rank])
            index_of_pusher = shuffled.index(node)
            getting_pushed_to.append(peers[index_of_pusher])

        print "Epoch: %s" % epoch
        print "Ledger Hash", ledger_hash
        print "Pulling from:", peers_to_pull_from
        print "Getting pulled from:", getting_pulled_from
        print "Pushing to:", peers_to_push_to
        print "Getting pushed from:", getting_pushed_to

    def apply_to_ledger(self):
        for tx in transactions:
            for input in tx['inputs']:
                entry = LegderEntry.objects.get(address=input['address'])
                entry.amount -= input
                entry.last_updated = ts
                entry.save()

            for output in tx['outputs']:
                address, amount = output
                entry, c = LedgerEntry.objects.get_or_create(address=address)
                entry.amount += output
                entry.last_updated = ts
                entry.save()
