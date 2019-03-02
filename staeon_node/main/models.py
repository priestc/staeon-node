# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import itertools
import os
import hashlib

import dateutil.parser
from django.db import models
from django.conf import settings
from staeon.consensus import get_epoch_range, get_epoch_number, deterministic_shuffle
from staeon.transaction import make_txid

class LedgerEntry(models.Model):
    address = models.CharField(max_length=35, primary_key=True)
    amount = models.FloatField(default=0)
    last_updated = models.DateTimeField()

    class Meta:
        get_latest_by = 'last_updated'


class Peer(models.Model):
    domain = models.TextField(primary_key=True)
    reputation = models.FloatField(default=0)
    first_registered = models.DateTimeField()
    payout_address = models.TextField(max_length=40, unique=True)

    def __unicode__(self):
        return "%s (rank %s)" % (self.domain, self.rank())

    @classmethod
    def shuffle(cls, peers=None, n=0):
        seed = LedgerHash.objects.latest()
        if not peers: peers = Peer.objects.all()
        return deterministic_shuffle(
            peers, n=n, sort_key=lambda x: x.domain, seed=seed
        )

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

    def rep_percent(self):
        total_rep = Peer.objects.all().aggregate(x=models.Sum("reputation"))['x']
        return (self.reputation * 100 / total_rep)

    def rep_percentile(self):
        """
        Percentage of all cumulative rep below this node.
        """
        total = self.nodes_ranked_below().aggregate(x=models.Sum('reputation'))['x'] or 0
        total += self.reputation
        return total / self.total_rep() * 100

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
        my_domain, my_pk = cls.my_node_data()
        obj = cls.objects.get(domain=my_domain)
        obj.private_key = my_pk
        return obj

    @classmethod
    def my_node_data(cls):
        config = open("/etc/staeon-node.conf").readlines()
        my_domain = config[0].strip()
        my_pk = config[1].strip()
        return my_domain, my_pk

    @classmethod
    def get_by_rank(self, rank):
        return Peer.objects.order_by('-reputation', 'first_registered')[rank]

    def as_dict(self, pk=False):
        ret = {
            'domain': self.domain,
            'reputation': self.reputation,
            'rank': self.rank(),
            'percent': self.rep_percent(),
            'percentile': self.rep_percentile(),
            'payout_address': self.payout_address,
        }
        if pk:
            my_domain, my_pk = Peer.my_node_data()
            if my_domain == self.domain:
                ret['private_key'] = my_pk
        return ret

class EpochSummary(models.Model):
    ledger_hash = models.CharField(max_length=64)
    epoch = models.IntegerField()
    transaction_count = models.IntegerField(default=0)
    propagation_order = models.TextField()

    class Meta:
        get_latest_by = 'epoch'

    @classmethod
    def close_epoch(cls, epoch=None):
        if not epoch: epoch = get_epoch_number()
        transactions = ValidatedTransaction.filter_for_epoch(epoch)
        ledger_hash = hashlib.sha256("".join([
            tx.txid for tx in transactions
        ]) + str(epoch)).hexdigest()

        peers = []
        for i in range(5):
            peers.append(Peer.shuffle(n=i))

        cls.objects.create(
            epoch=epoch, ledger_hash=ledger_hash,
            transaction_count=transactions.count(),
            propagation_order=" ".join([x.domain for x in peers])
        )
        return ledger_hash

    @classmethod
    def propagation_peers(cls, obj=None, type="transaction"):
        prop_domains = self.propagation_order.split(" ")
        propagate_to_peers(prop_domains, obj, type)

class ValidatedTransaction(models.Model):
    txid = models.CharField(max_length=64, primary_key=True)
    timestamp = models.DateTimeField()
    rejected_reputation_percentile = models.FloatField(default=0)
    applied = models.BooleanField(default=False)

    @classmethod
    def record(cls, tx, as_reject=False):
        if not 'txid' in tx: tx['txid'] = make_txid(tx)

        obj = cls.objects.create(
            txid=tx['txid'],
            timestamp=dateutil.parser.parse(tx['timestamp']),
            rejected_reputation_percentile=(
                Peer.my_node().rep_percent() if as_reject else 0
            )
        )
        for address, amount, sig in tx['inputs']:
            ValidatedMovement.objects.create(
                tx=obj, address=address, amount=(amount * -1)
            )

        for address, amount in tx['outputs']:
            ValidatedMovement.objects.create(
                tx=obj, address=address, amount=amount
            )

    def __unicode__(self):
        return self.txid[:8]

    @classmethod
    def filter_for_epoch(self, epoch=None):
        if not epoch: epoch = get_epoch_number()
        epoch_start, epoch_end = get_epoch_range(epoch)
        return cls.objects.filter(
            timestamp__lte=epoch_end, timestamp__gte=epoch_start,
        ).order_by('txid')

    @classmethod
    def adjusted_balance(cls, address, epoch=None):
        vtx = cls.filter_for_epoch(epoch)
        records = vtx.objects.filter(validatedmovement__address=address)

        total_adjusted = 0
        for record in records:
            total_adjusted += record.amount

        return total_adjusted

    def epoch(self):
        return get_epoch_number(self.timestamp)

    @classmethod
    def apply_to_ledger(cls, epoch):
        """
        Called at the begining of end of each epoch. Applies all valid
        transactions into the LedgerEntry table.
        """
        movements = ValidatedMovement.objects.filter(
            tx__in=cls.filter_for_epoch(epoch)
        )
        for tx in movements:
            le, c = LedgerEntry.objects.get_or_create(address=movement.address)
            le.amount += mobement.amount
            le.applied = True
            le.save()

class ValidatedMovement(models.Model):
    """
    Represents either an Input or an Output of a validated transaction.
    Inputs will have a negative value, outputs will always be positive.
    """
    tx = models.ForeignKey(ValidatedTransaction)
    address = models.CharField(max_length=35)
    amount = models.FloatField()

    @property
    def disp_amount(self):
        sign = ""
        if self.amount > 0:
            sign = "+"
        return "%s%.8f" % (sign, self.amount)

    def __unicode__(self):
        return "%s %s" % (self.address[:8], self.disp_amount)
