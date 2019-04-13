from django.core.management.base import BaseCommand, CommandError
from main.models import Peer, EpochHash, EpochSummary
from staeon.consensus import get_epoch_number, NodePenalization, propagate_to_peers

class Command(BaseCommand):
    help = "Starts the consensus process. Called every 10 minutes at the start of each epoch."

    def add_arguments(self, parser):
        parser.add_argument('--rank', type=int, help='calculate as rank')

    def handle(self, *args, **options):
        if options['rank']:
            rank = options['rank']
            node = Peer.get_by_rank(rank)
        else:
            node = Peer.my_node()
            my_pk = node.private_key

        # last epoch that just ended
        epoch = 4852 #get_epoch_number() - 1

        not_present, wrong = EpochHash.validate_pulls_for_epoch(epoch)

        for push, correct_hash in wrong:
            penalty = NodePenalization.make(
                epoch, correct_hash, push.as_dict(), my_pk
            )
            #propagate_to_assigned_peers(penalty, 'consensus/penalty')

        #for push, correct_hash in not_present:
        #    penalty = NodePenalization.make(epoch, , push.as_dict(), my_pk)

        print "not present:", not_present
        print "wrong:", wrong
