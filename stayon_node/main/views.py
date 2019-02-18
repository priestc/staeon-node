# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import json
import dateutil.parser

from django.shortcuts import render
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
from django.db.models import Q

from .models import LedgerEntry, Peer
from bitcoin import ecdsa_sign, ecdsa_verify, ecdsa_recover, pubtoaddr
from .tx_util import InvalidTransaction, validate_transaction

def send_tx(request):
    return render(request, "send_tx.html")

def accept_tx(request):
    try:
        tx = json.loads(request.POST['tx'])
    except:
        return HttpResponseBadRequest("Invalid transaction JSON")

    ts = dateutil.parser.parse(datetime.tx['timestamp'])

    if ts - datetime.datetime.now() < datetime.timedelta(seconds=10):
        return HttpResponseBadRequest("Transaction expired")

    for i, input in enumerate(tx['inputs']):
        address, amount, sig = input

        try:
            entry = LedgerEntry.objects.get(address=address)
        except LegderEntry.DoesNotExist:
            return HttpResponseBadRequest(
                "Address %s does not exist" % address
            )
        if entry.amount <= amount:
            return HttpResponseBadRequest(
                "Address %s does not have enough balance" % address
            )
        if entry.last_updated > ts:
            return HttpResponseBadRequest(
                "Timestamp in the past for input %s" % i
            )

    for output in tx['outputs']:
        address, amount = output

        try:
            entry = LedgerEntry.objects.get(address=address)
        except LegderEntry.DoesNotExist:
            continue

    try:
        validate_transaction(tx)
    except InvalidTransaction as exc:
        return HttpResponseBadRequest("Transaction Invalid: %s" % str(exc))

    for input in tx['inputs']:
        entry = LegderEntry.objects.get(address=input['address'])
        entry.amount -= input
        entry.last_updated = ts
        entry.save()

    for output in tx['outputs']:
        address, amount = output
        entry, c = LedgerEntry.objects.get_or_create(address=address)
        entry.amount += output
        entry.last_updated = ts
        entry.save()

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

def ping(request):
    pass

def sync(request):
    start = dateutil.parser.parse(request.GET['start'])
    ledgers = LedgerEntry.objects.filter(last_updated__gte=start).order_by('-last_updated')
    return JsonResponse({
        'data': [x.address, "%.8f" % x.amount, x.last_updated.isoformat()]
    })

def network_summary(request):
    peers = Peer.objects.all()
    return render(request, "stayon_summary.html", locals())
