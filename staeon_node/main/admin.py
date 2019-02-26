# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models
from django import forms
from django.contrib import admin
from .models import LedgerEntry, Peer, ValidatedTransaction

class PeerAdmin(admin.ModelAdmin):
    list_display = (
        'domain', 'reputation', 'payout_address', 'first_registered',
        'rank', 'disp_rep_precent', 'disp_rep_percentile'
    )
    ordering = ('-reputation', 'first_registered')
    formfield_overrides = {
        models.TextField: {'widget': forms.TextInput(attrs={'size': 40})},
    }

    def disp_rep_percentile(self, obj):
        return "%.2f%%" % obj.rep_percentile()

    def disp_rep_precent(self, obj):
        return "%.2f%%" % obj.rep_percent()

class LedgerAdmin(admin.ModelAdmin):
    list_display = ('address', 'amount', 'last_updated')

class ValidatedTransactionAdmin(admin.ModelAdmin):
    list_display = ('txid', 'epoch', 'timestamp')

admin.site.register(Peer, PeerAdmin)
admin.site.register(LedgerEntry, LedgerAdmin)
admin.site.register(ValidatedTransaction, ValidatedTransactionAdmin)
