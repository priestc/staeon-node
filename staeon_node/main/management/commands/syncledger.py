from django.core.management.base import BaseCommand, CommandError
from main.sync import sync_ledger


class Command(BaseCommand):
    help = 'Sync ledger with other nodes. Called when first coming online.'

    def handle(self, *args, **options):
        sync_ledger()
