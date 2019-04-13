# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import datetime
import random
import os
import hashlib
import dateutil.parser
from collections import defaultdict
import json

from django.db import models
from django.conf import settings
from django.core.cache import caches

from staeon.consensus import (
    make_epoch_seed, get_epoch_range, get_epoch_number, make_matrix,
    EpochHashPush, make_mini_hashes
)
from staeon.transaction import make_txid
from staeon.network import PROPAGATION_WINDOW_SECONDS

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

    def __unicode__(self):
        return "%s %s" % (self.address[:8], self.amount)

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
    epoch = models.IntegerField(primary_key=True)
    epoch_seed = models.CharField(max_length=64)
    transaction_count = models.IntegerField(default=0)

    # statistics
    count_duration = models.DurationField()
    apply_duration = models.DurationField()
    seed_duration = models.DurationField()

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
        return make_mini_hashes(self.epoch_seed, limit)

    @classmethod
    def close_epoch(cls, epoch):
        if cls.objects.filter(epoch=epoch).exists():
            raise Exception("Epoch %s consensus already performed" % epoch)

        stat_start = datetime.datetime.now()
        txs = ValidatedTransaction.filter_for_epoch(epoch)
        tx_count = txs.count()
        stat_count_end = datetime.datetime.now()

        ValidatedTransaction.apply_to_ledger(epoch)
        stat_apply_end = datetime.datetime.now()

        epoch_seed = make_epoch_seed(
            tx_count, LedgerEntry.objects.count(),
            LedgerEntry.objects.order_by('-amount', 'address'),
            lambda x: x.address
        )
        stat_epoch_seed_end = datetime.datetime.now()

        return cls.objects.create(
            epoch_seed=epoch_seed, transaction_count=tx_count, epoch=epoch,
            count_duration=(stat_count_end - stat_start),
            apply_duration=(stat_apply_end - stat_count_end),
            seed_duration=(stat_epoch_seed_end - stat_apply_end)
        )

    def make_shuffle_matrix(self):
        cache = caches['default']
        key = "matrix-%s" % self.epoch
        matrix = make_matrix(
            Peer.objects.all(), self.epoch_seed, sort_key=lambda x: x.domain
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
        """
        Constructs the minihash that goes to each domain for the consensus process.
        """
        work = self.consensus_nodes(domain=domain)
        results = defaultdict(list)
        minihashes = self.calculate_mini_hashes()

        for minihash_index in range(5):
            for node in work["minihash%s_push_to" % minihash_index]:
                results[node.domain].append(minihashes[minihash_index])
                random.shuffle(results[node.domain])

        return {key: ''.join(data) for key, data in results.items()}

    def consensus_pulls(self, domain=None):
        work = self.consensus_nodes(domain=domain)
        results = defaultdict(list)
        minihashes = self.calculate_mini_hashes()

        for minihash_index in range(5):
            for node in work["minihash%s_pushed_from" % minihash_index]:
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

    @classmethod
    def variable_length_short_txid(cls, min_length=0):
        def get_unique(txid, min_length=0):
            unique = '' if min_length == 0 else txid[:min_length - 1]
            for char in txid[min_length-1:]:
                unique += char
                if cls.objects.filter(txid__startswith=unique).count() == 1:
                    return unique

        short_ids = []
        t0 = datetime.datetime.now()
        for tx in cls.objects.all():
            short_ids.append(get_unique(tx.txid, min_length))
        print("took: %s" % (datetime.datetime.now() - t0))

        total_size = sum(len(x) for x in short_ids)
        count = len(short_ids)

        print("total transactions: %s" % count)
        print("avg bytes per tx: %s" % (float(total_size) / count))
        return short_ids

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
        for movement in movements:
            try:
                le = LedgerEntry.objects.get(address=movement.address)
                le.amount=le.amount + movement.amount
                le.last_updated=movement.tx.timestamp
                le.save()
            except LedgerEntry.DoesNotExist:
                LedgerEntry.objects.create(
                    address=movement.address,
                    amount=movement.amount,
                    last_updated=movement.tx.timestamp
                )

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
    def save_push(cls, from_peer, epoch, hashes, sig):
        my_domain = Peer.my_node_data()[0]
        EpochHashPush(obj={
            'from_domain': from_peer.domain, 'epoch': epoch,
            'hashes': hashes, 'signature': sig, 'to_domain': my_domain
        }).validate(from_peer.payout_address)

        return cls.objects.create(
            peer=from_peer, epoch=epoch, hashes=hashes,
            signature=sig
        )

    def as_dict(self):
        return {
            'epoch': self.epoch,
            'from_domain': self.peer.domain,
            'to_domain': Peer.my_node_data()[0],
            'hashes': self.hashes,
            'signature': self.signature,
        }

    @classmethod
    def validate_pulls_for_epoch(cls, epoch):
        es = EpochSummary.objects.get(epoch=epoch)
        pulls_received = cls.objects.filter(epoch=epoch)
        domains_received = pulls_received.values_list('peer__domain', flat=True)

        not_present = []
        wrong = []
        for domain, minihashes in es.consensus_pulls().items():
            try:
                pull = pulls_received.get(peer__domain=domain)
            except cls.DoesNotExist:
                not_present.append([domain, minihashes[0]])
                continue

            for mh in minihashes:
                if mh not in pull.hashes:
                    wrong.append([pull, mh])
                    break

        return not_present, wrong


class NodePenaltyVote(models.Model):
    epoch = models.ForeignKey(EpochSummary)
    penalized_peer = models.ForeignKey(Peer, related_name="penalization_subject")
    vote_for = models.BooleanField(default=False)
    voting_peer = models.ForeignKey(Peer, related_name="penalization_vote")

    @classmethod
    def make_vote(cls, penalty_obj):
        """
        penalty_obj is the object that is returned from NodePenaltyVote.make from
        staeonlib.
        """
        correct_hash = penalty['correct_hash']
        to_domain = penalty_obj['push']['to_domain']
        from_domain = penalty_obj['push']['from_domain']
        epoch = penalty_obj['push']['epoch']
        es = EpochSummary.objects.get(epoch=epoch)
        pushes = es.consensus_pulls(domain=to_domain)

        accusee = Peer.objects.get(domain=from_domain)
        accuser = Peer.objects.get(domain=to_domain)
        penalty = NodePenalization(obj, accuser.payout_address).validate(
            accusee.payout_address
        )

        vote_for = (
            from_domain not in pushes.keys() or
            correct_hash not in pushes[from_domain]
        )

        return cls.objects.create(
            voting_peer=accuser, vote_for=vote_for,
            penalized_peer=accusee, epoch=epoch
        )
