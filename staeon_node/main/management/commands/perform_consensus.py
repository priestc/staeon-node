from django.core.management.base import BaseCommand, CommandError
from main.models import Peer, LedgerEntry, EpochSummary
from staeon.consensus import get_epoch_number, make_ledger_push, propagate_to_peers

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

        # close last epoch that just ended
        epoch = get_epoch_number() - 1
        es = EpochSummary.close_epoch(epoch)

        for domain, mini_hashes in es.consensus_pushes().items():
            push = make_ledger_push(epoch, node.domain, node.private_key, mini_hashes)
            propagate_to_peers([domain], push, "consensus")
