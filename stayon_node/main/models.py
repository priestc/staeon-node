# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import itertools
import os
import hashlib

from django.db import models
from django.conf import settings
from .consensus_util import get_epoch_range


class LedgerEntry(models.Model):
    address = models.CharField(max_length=35, primary_key=True)
    amount = models.FloatField(default=0)
    last_updated = models.DateTimeField()

    class Meta:
        get_latest_by = 'last_updated'

    @classmethod
    def ledger_hash(cls, epoch):
        epoch_start, epoch_end = get_epoch_range(epoch)
        ledgers = LedgerEntry.objects.filter(
            last_updated__lte=epoch_end,
            last_updated__gte=epoch_start,
        ).order_by('last_updated', 'address')
        return hashlib.sha256("".join([
            "%s%.8f" % (x.address, x.amount) for x in ledgers
        ]) + str(epoch)).hexdigest()


class Peer(models.Model):
    domain = models.TextField(primary_key=True)
    reputation = models.FloatField(default=0)
    first_registered = models.DateTimeField()
    payout_address = models.TextField(max_length=40, unique=True)

    def __unicode__(self):
        return "%s (rank %s)" % (self.domain, self.rank())

    @classmethod
    def shuffle(cls, peers, hash, n=0):
        sorter = lambda x: hashlib.sha256(x.domain + hash + str(n)).hexdigest()
        return sorted(peers, key=sorter)

    def nodes_ranked_above(self):
        return Peer.objects.filter(
            models.Q(reputation__gt=self.reputation) |
            (models.Q(reputation=self.reputation) &
            models.Q(first_registered__lt=self.first_registered))
        )

    def nodes_ranked_below(self):
        return Peer.objects.filter(
            models.Q(reputation__lt=self.reputation) |
            (models.Q(reputation=self.reputation) &
            models.Q(first_registered__gt=self.first_registered))
        )

    def rank(self):
        return self.nodes_ranked_above().count()

    def rep_precent(self):
        total_rep = Peer.objects.all().aggregate(x=models.Sum("reputation"))['x']
        return "%.2f%%" % (self.reputation * 100 / total_rep)

    def rep_percentile(self):
        """
        Percentage of all cumulative rep below this node.
        """
        total = self.nodes_ranked_below().aggregate(x=models.Sum('reputation'))['x'] or 0
        total += self.reputation
        return "%.2f%%" % (total / self.total_rep() * 100)

    @classmethod
    def total_rep(cls):
        return cls.objects.all().aggregate(x=models.Sum("reputation"))['x']

    @classmethod
    def consensus_line(cls):
        peers = cls.objects.order_by('reputation', 'first_registered')
        total_rep = peers.aggregate(x=models.Sum("reputation"))['x']
        cumulative_rep = 0
        for peer in peers:
            cumulative_rep += peer.reputation
            if cumulative_rep > total_rep / 2.0:
                return peer.rank()

    @classmethod
    def my_node(cls):
        config = open(os.path.join(settings.BASE_DIR, "../node.conf")).readlines()
        my_domain = config[0].strip()
        return cls.objects.get(domain=my_domain)

    @classmethod
    def get_by_rank(self, rank):
        return Peer.objects.order_by('-reputation', 'first_registered')[rank]

class LedgerHash(models.Model):
    hash = models.CharField(max_length=64)
    epoch = models.IntegerField()

class EpochTransactions(models.Model):
    epoch_number = models.IntegerField()
    transactions = models.TextField()

    def adjustment_for_address(self, address):
        pass
