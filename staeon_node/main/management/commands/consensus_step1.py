from django.core.management.base import BaseCommand, CommandError
from main.models import Peer, LedgerEntry, EpochSummary
from staeon.consensus import get_epoch_number, EpochHashPush, propagate_to_peers

class Command(BaseCommand):
    help = "Perform consensus part 1. Called every 10 minutes at the start of each epoch."

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
            push = EpochHashPush.make(
                epoch, node.domain, domain, node.private_key, mini_hashes
            )
            propagate_to_peers([domain], push, "epoch hash")
