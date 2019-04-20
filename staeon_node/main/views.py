# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import json
import dateutil.parser
from bitcoin import ecdsa_sign, ecdsa_verify, ecdsa_recover, pubtoaddr

from django.shortcuts import render
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
from django.views.decorators.csrf import ensure_csrf_cookie, csrf_exempt
from django.db.models import Q

from .models import (
    LedgerEntry, Peer, ValidatedTransaction, ValidatedRejection, EpochHash,
    ValidatedMovement
)

from staeon.peer_registration import validate_peer_registration
from staeon.transaction import validate_transaction, make_txid
from staeon.consensus import (
    validate_rejection_authorization, get_epoch_number, get_epoch_range,
    propagate_to_peers, make_transaction_rejection
)
from staeon.exceptions import InvalidTransaction, RejectedTransaction

def send_tx(request):
    return render(request, "send_tx.html")

@csrf_exempt
def accept_tx(request):
    try:
        tx = json.loads(request.POST['tx'])
    except ValueError:
        return HttpResponseBadRequest("Invalid transaction JSON")

    if 'txid' not in tx: tx['txid'] = make_txid(tx)

    try:
        ValidatedTransaction.validate_raw_tx(tx)
    except InvalidTransaction as exc:
        return HttpResponseBadRequest("Invalid: %s " % exc.display())

    return HttpResponse("OK")

def rejections(request):
    if request.POST:
        try:
            node = Peer.objects.get(domain=request.POST['domain'])
        except Peer.DoesNotExist:
            return HttpResponseBadRequest("Unregistered peer")
        try:
            ValidatedRejection.validate_rejection_from_peer(
                peer, request.POST['txid'], request.POST['signature']
            )
        except Exception as exc:
            return HttpResponseBadRequest("Invalid Rejection: %s" % exc.display())
    else:
        # rendering the rejections page
        if 'epoch' in request.GET:
            epoch = int(request.GET['epoch'])
        else:
            epoch = get_epoch_number()

        epoch_start, epoch_end = get_epoch_range(epoch)
        rejected = ValidatedTransaction.objects.filter(
            validatedrejection__isnull=False,
            timestamp__gt=epoch_start, timestamp__lt=epoch_end
        ).distinct()

        if 'json' in request.GET:
            return JsonResponse({'rejections': [
                (tx.txid, tx.rejected_reputation_percent()) for tx in rejected
            ]})
        return render(request, "rejections.html", locals())

def peers(request):
    page_size = 5
    if request.method == 'GET':
        peers = Peer.objects.order_by("first_registered")

        if 'top' in request.GET:
            peers = filter(lambda x: x['percentile'] > 50, peers)
        elif 'page' in request.GET:
            page = int(request.GET['page'])
            print "peers[%s:%s]" % (page_size * (page - 1), page_size * page)
            peers = peers[page_size * (page - 1):page_size * page]
        else:
            peers = peers[:page_size]

        return JsonResponse({
            'peers': [x.as_dict() for x in peers]
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

def consensus_penalty(request):
    if request.POST:
        obj = json.loads(request.POST['obj'])
        NodePenaltyVote.make_vote(obj)

    return HttpResponse("OK")

def consensus_push(request):
    """
    During the consensus process, other nodes will push their ledger hash and
    this view will accept it. Also handles ledger hash pulls via GET.
    """
    if request.POST:
        # accepting push
        obj = json.loads(request.POST['obj'])
        peer = Peer.objects.get(domain=obj['domain'])

        try:
            EpochHash.save_push(
                peer, obj['epoch'], obj['hashes'], obj['signature'],
            )
        except InvalidObject as exc:
            return HttpResponseBadRequest("Invalid Epoch Hash Push: %s" % exc)
        except RejectedObject as exc:
            return HttpResponseBadRequest("Rejected Epoch Hash Push: %s" % exc)
        return HttpResponse("OK")
    # else:
    #     # returning pull
    #     latest = EpochSummary.objects.latest()
    #     domain = request.GET['domain']
    #
    #     return JsonResponse({
    #         'epoch_hash': latest.epoch_hash,
    #         'epoch': latest.epoch
    #     })


def ledger(request):
    if "sync_start" in request.GET:
        start = dateutil.parser.parse(request.GET['sync_start'])
        ledgers = LedgerEntry.objects.filter(last_updated__gt=start).order_by('-last_updated')
        return JsonResponse({
            'data': [
                [x.address, "%.8f" % x.amount, x.last_updated.isoformat()]
                for x in ledgers[:500]
            ]
        })
    elif 'address' in request.GET:
        address = request.GET['address']
        try:
            balance = LedgerEntry.objects.get(address=address).amount
        except LedgerEntry.DoesNotExist:
            balance = 0

        adjusted_balance = (
            balance + ValidatedMovement.adjusted_balance(
                address, epoch=get_epoch_number()
            )
        )
        return HttpResponse(str(adjusted_balance))

def network_summary(request):
    peers = Peer.objects.order_by('-reputation')
    total_issued = LedgerEntry.total_issued()
    epoch = get_epoch_number()
    return render(request, "staeon_summary.html", locals())
