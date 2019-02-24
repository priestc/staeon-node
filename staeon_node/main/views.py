# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import json
import dateutil.parser

from django.shortcuts import render
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
from django.db.models import Q

from .models import LedgerEntry, Peer, ValidatedTransaction
from bitcoin import ecdsa_sign, ecdsa_verify, ecdsa_recover, pubtoaddr
from .tx_util import (
    make_transaction_authorization, validate_transaction_authorization,
    InvalidTransaction, ExpiredTransaction, validate_transaction, make_txid
)
from .consensus_util import validate_timestamp

def ledger(address, timestamp):
    try:
        entry = LedgerEntry.objects.get(address=address)
    except LegderEntry.DoesNotExist:
        raise Exception("%s does not exist" % address)

    last_updated = enter.last_updated
    current_balance = entry.amount
    already_spent = ValidatedTransaction.adjusted_balance(address)
    last_spend = ValidatedTransaction.last_spend(address)

    return current_balance, last_updated

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
    except ExpiredTransaction as exc:
        propagate_rejection(tx, exc)
        return HttpResponseBadRequest("Rejected: %s" % exc.display)

    # save to "mempool"
    ValidatedTransaction.record(tx)

    return HttpResponse("OK")

def pass_on_to_peers(obj):
    peers = Peer.objects.all()

def get_peers(request):
    pass

def add_peer(request):
    try:
        reg = json.loads(request.POST['registration'])
    except Exception as exc:
        return HttpResponseBadRequest("Invalid transaction JSON: %s" % str(exc))

    for item in ['signature', 'timestamp', 'domain', 'payout_address']:
        if item not in reg:
            return HttpResponseBadRequest(
                "%s missing" % item.replace("_", " ").title()
            )

    ts = dateutil.parser.parse(reg['timestamp'])
    if ts - datetime.datetime.now() > datetime.timedelta(seconds=10):
        return HttpResponseBadRequest("Timestamp too old")

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

    pass_on_to_peers(reg)

    return HttpResponse("OK")

def accept_push(request):
    """
    During the consensus process, other nodes will push their ledger hash and
    this view will accept it.
    """
    claimed_ledger_hash = request.POST['ledger_hash']
    signature = request.POST['signature']
    domain = request.POST['domain']
    peer = Peer.objects.get(domain=domain)

    valid = validate_ledger_hash_push(
        peer.payout_address, claimed_ledger_hash, domain, signature
    )
    if valid:
        pass

    return HttpResponse("OK")

def return_pull(request):
    """
    Some nodes will request my ledger hash during the consensus process.
    This view returns that ledger hash. Signing this response is not necessary
    because it is being served via HTTPS.
    """
    return JsonResponse({
        'ledger_hash': get_latest_hash(),
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
