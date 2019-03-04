# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import json
import dateutil.parser

from django.shortcuts import render
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
from django.db.models import Q

from .models import LedgerEntry, Peer, ValidatedTransaction
from bitcoin import ecdsa_sign, ecdsa_verify, ecdsa_recover, pubtoaddr

from staeon.peer_registration import validate_peer_registration
from staeon.transaction import validate_transaction, make_txid
from staeon.consensus import (
    validate_rejection_authorization, get_epoch_number, get_epoch_range,
    propagate_to_peers, make_transaction_rejection
)
from staeon.exceptions import InvalidTransaction, RejectedTransaction

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

def send_tx(request):
    return render(request, "send_tx.html")

def accept_tx(request):
    try:
        tx = json.loads(request.POST['tx'])
    except ValueError:
        return HttpResponseBadRequest("Invalid transaction JSON")

    tx['txid'] = make_txid(tx)

    try:
        validate_transaction(tx)
    except InvalidTransaction as exc:
        return HttpResponseBadRequest("Invalid: %s " % exc.display)
    except RejectedTransaction as exc:
        ValidatedTransaction.record(tx, reject=True)
        reject = make_transaction_rejection(
            tx, exc, Peer.my_node().as_dict(pk=True),
            [x.as_dict() for x in Peer.object.all()]
        )
        propagate_to_assigned_peers(obj=reject, type="rejections")
        return HttpResponseBadRequest("Rejected: %s" % exc.display)

    # save to "mempool"
    ValidatedTransaction.record(tx)
    propagate_to_assigned_peers(obj=tx, type="transaction")

    return HttpResponse("OK")

def rejections(request):
    if request.POST:
        domain = request.POST['domain']
        txid = request.POST['txid']
        rejecting_node = Peer.objects.get(domain=domain)

        rejection = {
            'domain': domain,
            'txid': txid,
            'signature': request.POST['signature']
        }
        try:
            validate_rejection_authorization(rejection)
        except Exception as exc:
            return HttpResponseBadRequest("Invalid Rejection: %s" % exc.display)
        tx,c = ValidatedTransaction.objects.get_or_create(txid=txid)
        tx.rejected_reputation_percentile += rejecting_node.rep_percentile()
        tx.save()
        propagate_to_assigned_peers(rejection, type="rejections")
    else:
        # rendering the rejections page
        if 'epoch' in request.GET:
            epoch = int(request.GET['epoch'])
        else:
            epoch = get_epoch_number()

        epoch_start, epoch_end = get_epoch_range(epoch)
        rejected = ValidatedTransaction.objects.filter(
            rejected_reputation_percentile__gt=0,
            timestamp__gt=epoch_start, timestamp__lt=epoch_end
        )
        if 'json' in request.GET:
            return JsonResponse({'rejections': [
                (tx.txid, tx.rejected_reputation_percentile) for tx in rejected
            ]})
        return render(request, "rejections.html", locals())

def peers(request):
    if request.GET:
        peers = Peer.objects.all()
        peers = [x.as_dict() for x in peers]

        if 'top' in request.GET:
            peers = filter(lambda x: x['percentile'] > 50, peers)

        return JsonResponse({
            'peers': peers
        })
    else:
        # handling new peer registration
        try:
            reg = json.loads(request.POST['registration'])
        except Exception as exc:
            return HttpResponseBadRequest("Invalid registration JSON: %s" % str(exc))

        for item in ['signature', 'timestamp', 'domain', 'payout_address']:
            if item not in reg:
                return HttpResponseBadRequest(
                    "%s missing" % item.replace("_", " ").title()
                )

        try:
            validate_peer_registration(reg)
        except Exception as exc:
            return HttpResponseBadRequest("Registration Invalid: %s" % exc)

        try:
            p = Peer.objects.get(
                Q(domain=reg['domain']) | Q(payout_address=reg['payout_address'])
            )
            p.domain = reg['domain']
            p.payout_address = reg['payout_address']
            p.save()
        except Peer.DoesNotExist:
            Peer.objects.create(
                domain=reg['domain'],
                payout_address=reg['payout_address'],
                first_registered=ts
            )

        propagate_to_assigned_peers(reg, "peers")

        return HttpResponse("OK")

def consensus(request):
    """
    During the consensus process, other nodes will push their ledger hash and
    this view will accept it. Also handles ledger hash pulls via GET.
    """
    if request.POST:
        # accepting push
        claimed_ledger_hash = request.POST['ledger_hash']
        epoch = int(request.POST['epoch'])
        signature = request.POST['signature']
        domain = request.POST['domain']
        peer = Peer.objects.get(domain=domain)

        try:
            validate_ledger_hash_push(
                peer.payout_address, claimed_ledger_hash, domain, signature
            )
        except InvalidObject:
            pass
        except RejectedObject:
            pass

        ConsensusResult.objects.create(
            epoch=epoch,
            domain=domain,
            claimed_ledger_hash=claimed_ledger_hash
        )

        return HttpResponse("OK")
    else:
        # returning pull
        latest = LedgerHash.objects.latest()
        return JsonResponse({
            'ledger_hash': latest.ledger_hash,
            'epoch': latest.epoch
        })


def sync(request):
    start = dateutil.parser.parse(request.GET['start'])
    ledgers = LedgerEntry.objects.filter(last_updated__gt=start).order_by('-last_updated')
    return JsonResponse({
        'data': [
            [x.address, "%.8f" % x.amount, x.last_updated.isoformat()]
            for x in ledgers[:500]
        ]
    })

def network_summary(request):
    peers = Peer.objects.all()
    return render(request, "staeon_summary.html", locals())
