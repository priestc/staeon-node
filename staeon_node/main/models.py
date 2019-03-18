# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import os
import hashlib
import dateutil.parser
from collections import defaultdict
import json

from django.db import models
from django.conf import settings
from django.core.cache import caches

from staeon.consensus import (
    make_epoch_hashes, get_epoch_range, get_epoch_number, make_matrix,
    validate_ledger_push
)
from staeon.transaction import make_txid
from staeon.network import PROPAGATION_WINDOW_SECONDS

def lucky_address(number):
    index = number % LedgerEntry.objects.count()
    return LedgerEntry.objects.order_by('-last_updated')[index].address

def ledger(address, timestamp):
    try:
        entry = LedgerEntry.objects.get(address=address)
    except LegderEntry.DoesNotExist:
        raise Exception("%s does not exist" % address)

    last_updated = entry.last_updated
    current_balance = entry.amount
    adjusted = ValidatedTransaction.adjusted_balance(address, timestamp)
    spend_this_epoch = ValidatedTransaction.last_spend(address)

    return (current_balance + adjusted), spend_this_epoch or last_updated

def propagate_to_assigned_peers(obj, type):
    return propagate_to_peers(EpochSummary.prop_domains(), obj=obj, type=type)

class LedgerEntry(models.Model):
    address = models.CharField(max_length=35, primary_key=True)
    amount = models.FloatField(default=0)
    last_updated = models.DateTimeField()

    class Meta:
        get_latest_by = 'last_updated'

    @classmethod
    def total_issued(cls):
        return cls.objects.aggregate(s=models.Sum('amount'))['s']

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

    def mine(self):
        my_domain, _ = Peer.my_node_data()
        return self.domain == my_domain

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
            'first_registered': self.first_registered.isoformat()
        }
        if pk:
            my_domain, my_pk = Peer.my_node_data()
            if my_domain == self.domain:
                ret['private_key'] = my_pk
        return ret

class EpochSummary(models.Model):
    epoch_hash = models.CharField(max_length=64)
    dummy_hashes = models.TextField()
    epoch = models.IntegerField()
    transaction_count = models.IntegerField(default=0)

    class Meta:
        get_latest_by = 'epoch'

    def __unicode__(self):
        return str(self.epoch)

    @classmethod
    def prop_domains(cls, epoch=None):
        """
        Returns the list of domains that you propagate you based on the shuffled
        node matrix and your node's current ranking.
        """
        if not epoch: epoch = get_epoch_number() - 1
        cache = caches['default']
        key = "prop-domains"
        domains = cache.get(key)
        if not domains:
            try:
                es = EpochSummary.objects.get(epoch=epoch)
            except EpochSummary.DoesNotExist:
                es = EpochSummary.objects.latest()
            domains = [x.domain for x in es.consensus_nodes()['push_legit_to']]
            cache.set(key, domains)
        return domains

    def calculate_mini_hashes(self, limit=5):
        hash = self.epoch_hash
        mini_hashes = []
        for x in range(limit):
            hash = hashlib.sha256(hash).hexdigest()
            mini_hashes.append(hash[:8])
        return mini_hashes

    @classmethod
    def close_epoch(cls, epoch):
        if cls.objects.filter(epoch=epoch).exists():
            raise Exception("Epoch %s consensus already performed" % epoch)

        txs = ValidatedTransaction.filter_for_epoch(epoch)
        epoch_hash, dummies = make_epoch_hashes(
            [x.txid for x in txs], epoch, lucky_address
        )

        return cls.objects.create(
            epoch_hash=epoch_hash, dummy_hashes="\n".join(dummies),
            transaction_count=txs.count(), epoch=epoch,
        )

    def make_shuffle_matrix(self):
        cache = caches['default']
        key = "matrix-%s" % self.epoch
        matrix = make_matrix(
            Peer.objects.all(), self.epoch_hash, sort_key=lambda x: x.domain
        )
        cache.set(key, matrix)
        return matrix

    def shuffle_matrix(self):
        cache = caches['default']
        key = "matrix-%s" % self.epoch
        matrix = cache.get(key)
        if not matrix:
            matrix = self.make_shuffle_matrix()
        return matrix

    def consensus_nodes(self, domain=None, matrix_depth=5):
        """
        Gets all the appropriate nodes for the consensus process for the
        next epoch for a given node domain.
        """
        peers = list(Peer.objects.all().order_by('reputation', 'first_registered'))
        if not domain:
            node = Peer.my_node()
        else:
            node = Peer.objects.get(domain=domain)

        pushes = {}
        matrix = self.shuffle_matrix()
        for i, column in enumerate(matrix):
            pushes['minihash%s_push_to' % i] = set(row[node.rank()] for row in column)
            pushes['minihash%s_pushed_from' % i] = set(peers[row.index(node)] for row in column)

        return pushes

    def peers_pushing_to_me(self, minihash_index=0):
        """
        All peers that will push a given hash to me.
        """
        return self.consensus_nodes()["minihash%s_pushed_from" % minihash_index]

    def consensus_pushes(self, domain=None):
        work = self.consensus_nodes(domain=domain)
        results = defaultdict(list)
        minihashes = self.calculate_mini_hashes()

        for minihash_index in range(5):
            for node in work["minihash%s_push_to" % minihash_index]:
                results[node.domain].append(minihashes[minihash_index])

        return dict(results)


class ValidatedRejection(models.Model):
    tx = models.ForeignKey("ValidatedTransaction")
    peer = models.ForeignKey("Peer")

    @classmethod
    def validate_rejection_from_peer(self, peer, txid, signature):
        validate_rejection_authorization(
            peer.domain, txid, signature, peer.payout_address
        )
        tx,c = ValidatedTransaction.objects.get_or_create(txid=txid)
        ValidatedRejection.objects.create(tx=tx, peer=node)
        propagate_to_assigned_peers(rejection, type="rejections")


class ValidatedTransaction(models.Model):
    txid = models.CharField(max_length=64, primary_key=True)
    timestamp = models.DateTimeField()
    applied = models.BooleanField(default=False)

    def validate_raw_tx(cls, tx):
        if ValidatedTransaction.objects.filter(txid=tx['txid']).exists():
            return
        try:
            validate_transaction(tx, ledger=ledger)
        except RejectedTransaction as exc:
            reject = make_transaction_rejection(
                tx, exc, Peer.my_node().as_dict(pk=True),
                [x.as_dict() for x in Peer.object.all()]
            )
            propagate_to_assigned_peers(obj=reject, type="rejections")
            cls.record(tx, as_reject=True)
            return

        cls.record(tx)
        propagate_to_assigned_peers(obj=tx, type="transaction")

    @classmethod
    def record(cls, tx, as_reject=False):
        if 'txid' not in tx: tx['txid'] = make_txid(tx)
        obj = cls.objects.create(
            txid=tx['txid'],
            timestamp=dateutil.parser.parse(tx['timestamp'])
        )
        for address, amount, sig in tx['inputs']:
            ValidatedMovement.objects.create(
                tx=obj, address=address, amount=(amount * -1)
            )

        for address, amount in tx['outputs']:
            ValidatedMovement.objects.create(
                tx=obj, address=address, amount=amount
            )

        if as_reject:
            ValidatedRejection.objects.create(tx=obj, peer=Peer.my_node())

    def __unicode__(self):
        return self.txid[:8]

    @classmethod
    def filter_for_epoch(cls, epoch=None):
        if not epoch: epoch = get_epoch_number()
        epoch_start, epoch_end = get_epoch_range(epoch)
        return cls.objects.filter(
            timestamp__lte=epoch_end, timestamp__gte=epoch_start,
        )

    @classmethod
    def adjusted_balance(cls, address, timestamp, epoch=None):
        d = timestamp - datetime.timedelta(seconds=PROPAGATION_WINDOW_SECONDS)
        vtx = cls.filter_for_epoch(epoch)
        records = vtx.objects.filter(
            validatedmovement__address=address, timestamp__lt=d
        )

        total_adjusted = 0
        for record in records:
            total_adjusted += record.amount

        return total_adjusted

    def epoch(self):
        return get_epoch_number(self.timestamp)

    def rejected_reputation_percent(self):
        rejects = ValidatedRejection.objects.filter(tx=self)
        total_percentile = 0
        for r in rejects:
            total_percentile += r.peer.rep_percent()
        return total_percentile

    def fee(self):
        fee = 0
        for m in self.validatedmovement_set.all():
            fee += m.amount * -1
        return float("%.8f" % fee)

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

class EpochHash(models.Model):
    epoch = models.IntegerField()
    peer = models.ForeignKey(Peer)
    hashes = models.TextField()
    signature = models.CharField(max_length=50)

    def __unicode__(self):
        return "%s %s" % (self.peer.domain, self.epoch)

    @classmethod
    def save_push(cls, peer, epoch, hashes, sig):
        validate_ledger_push(
            peer.domain, epoch, hashes, sig, peer.payout_address
        )
        return cls.objects.create(
            peer=peer, epoch=epoch, hashes=json.dumps(hashes),
            signature=sig
        )

    def is_valid(self):
        """
        Returns True if this push is a valid push. Either legit or dummy hash.
        """
        es = EpochSummary.objects.get(epoch=epoch)

        for type in ['legit', 'dummy1', 'dummy2', 'dummy3']:
            if self.peer.rank() in es.ranks_pushing_to_me(type):
                mini_hash = es.get_mini_hash(type)
                if es.epoch_hash.startswith(mini_hash):
                    pass

            for mini_hash in json.loads(self.hashes):
                return True

        return False

    def as_json(self):
        return json.dumps({
            'epoch': self.epoch,
            'domain': self.peer.domain,
            'hashes': json.loads(self.hashes),
            'signature': self.signature,
        })
