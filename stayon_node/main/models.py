# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import itertools
import os
import hashlib
import datetime

from django.db import models
from django.conf import settings

genesis = datetime.datetime(2019, 2, 14, 10, 0)

def get_epoch_range(n):
    """
    Given an epoch number, returns the start and end times for that epoch.
    """
    start =  genesis + datetime.timedelta(minutes=10 * n)
    return start, start + datetime.timedelta(minutes=10)

def get_epoch_number(time):
    """
    For a given time, returns which epoch number that date falls in.
    """
    delta = time - genesis
    return int("%d" % (delta.total_seconds() / 600))

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
        return self.domain

    @classmethod
    def shuffle(cls, peers, hash, n=0):
        sorter = lambda x: hashlib.sha256(x.domain + hash + str(n)).hexdigest()
        return sorted(peers, key=sorter)

    def rank(self):
        return Peer.objects.filter(
            models.Q(reputation__gt=self.reputation) |
            (models.Q(reputation=self.reputation) &
            models.Q(first_registered__lt=self.first_registered))
        ).count()

    @classmethod
    def my_node(cls):
        config = open(os.path.join(settings.BASE_DIR, "../node.conf")).readlines()
        my_domain = config[0].strip()
        return cls.objects.get(domain=my_domain)

    @classmethod
    def get_by_rank(self, rank):
        return Peer.objects.order_by('-reputation', 'first_registered')[rank]


class EpochTransactions(models.Model):
    epoch_number = models.IntegerField()
    transactions = models.TextField()

    def adjustment_for_address(self, address):
        pass
