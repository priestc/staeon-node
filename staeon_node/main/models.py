# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import itertools
import os
import hashlib

import dateutil.parser
from django.db import models
from django.conf import settings
from staeon.consensus import get_epoch_range, get_epoch_number
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
        config = open(os.path.join(settings.BASE_DIR, "../node.conf")).readlines()
        my_domain = config[0].strip()
        my_pk = config[1].strip()
        return my_domain, my_pk

    @classmethod
    def get_by_rank(self, rank):
        return Peer.objects.order_by('-reputation', 'first_registered')[rank]

    def as_dict(self):
        my_domain, my_pk = Peer.my_node_data()
        return {
            'domain': self.domain,
            'reputation': self.reputation,
            'rank': self.rank(),
            'percent': self.rep_precent(),
            'payout_address': self.payout_address,
            'private_key': my_pk if my_domain == self.domain else None
        }


class LedgerHash(models.Model):
    hash = models.CharField(max_length=64)
    epoch = models.IntegerField()

class ValidatedTransaction(models.Model):
    txid = models.CharField(max_length=64, primary_key=True)
    timestamp = models.DateTimeField()
    rejected_reputation_percentile = models.FloatField(default=0)

    @classmethod
    def record(cls, tx):
        if not 'txid' in tx: tx['txid'] = make_txid(tx)

        tx = cls.objects.create(
            txid=tx['txid'],
            timestamp=dateutil.parser.parse(tx['timestamp'])
        )
        for address, amount, sig in tx['inputs']:
            ValidatedMovement.objects.create(
                tx=tx, address=address, amount=(amount * -1)
            )

        for address, amount in tx['outputs']:
            ValidatedMovement.objects.create(
                tx=tx, address=address, amount=amount
            )

    @classmethod
    def ledger_hash(cls, epoch):
        epoch_start, epoch_end = get_epoch_range(epoch)
        transactions = cls.objects.filter(
            timestamp__lte=epoch_end,
            timestamp__gte=epoch_start,
        ).order_by('last_updated', 'txid')

        return hashlib.sha256("".join([
            tx.txid for tx in transactions
        ]) + str(epoch)).hexdigest()

    @classmethod
    def adjusted_balance(cls, address, epoch):
        epoch_start, epoch_end = get_epoch_range(epoch)
        records = ValidatedTransaction.objects.filter(
            (Q(spent_inputs__contains=address) | Q(outputs__contains=address))
            & (Q(timestamp__gt=epoch_start) & Q(timestamp__lt=epoch_end))
        )
        total_adjusted = 0
        for record in records:
            total_adjusted += record.amount_for_address(address)

        return total_adjusted

    def epoch(self):
        return get_epoch_number(self.timestamp)

    def amount_for_address(self, address):
        amount = 0
        for input in self.spent_inputs.split("\n"):
            in_address, in_amount = input.split(",")
            if in_address == address:
                amount -= float(in_amount)

        for output in self.outputs.split("\n"):
            out_address, out_amount = output.split(",")
            if out_address == address:
                amount += float(out_amount)

        return amount

class ValidatedMovement(models.Model):
    """
    Represents either an Input or an Output of a validated transaction.
    Inputs will have a negative value, outputs will always be positive.
    """
    tx = models.ForeignKey(ValidatedTransaction)
    address = models.CharField(max_length=35)
    amount = models.FloatField()
