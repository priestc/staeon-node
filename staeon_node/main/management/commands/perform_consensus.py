import datetime

from django.core.management.base import BaseCommand, CommandError
from main.models import Peer, LedgerEntry, LedgerHash
from staeon.consensus import get_epoch_number

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

        # close last epoch that just ended
        epoch = get_epoch_number(datetime.datetime.now()) - 1
        es = EpochSummary.close_epoch(epoch)
        nodes = es.consensus_nodes()
        print nodes
        return

        print "Epoch: %s" % epoch
        print "Ledger Hash", ledger_hash
        print "Pulling from:", nodes['legit_push_to']
        print "Getting pulled from:", getting_pulled_from
        print "Pushing to:", peers_to_push_to
        print "Getting pushed from:", getting_pushed_to
