# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models
from django import forms
from django.contrib import admin
from .models import LedgerEntry, Peer, ValidatedTransaction, EpochSummary

class PeerAdmin(admin.ModelAdmin):
    list_display = (
        'domain', 'reputation', 'payout_address', 'first_registered',
        'rank', 'disp_rep_percent', 'disp_rep_percentile'
    )
    ordering = ('-reputation', 'first_registered')
    formfield_overrides = {
        models.TextField: {'widget': forms.TextInput(attrs={'size': 40})},
    }

    def disp_rep_percentile(self, obj):
        return "%.2f%%" % obj.rep_percentile()

    def disp_rep_percent(self, obj):
        return "%.2f%%" % obj.rep_percent()

class LedgerAdmin(admin.ModelAdmin):
    list_display = ('address', 'amount', 'last_updated')

class ValidatedTransactionAdmin(admin.ModelAdmin):
    list_display = (
        'txid', 'epoch', 'timestamp', 'rejected_reputation_percent',
        'column_movements'
    )
    readonly_fields = (
        'readonly_movements', 'epoch', 'timestamp', 'txid',
        'rejected_reputation_percent', 'fee'
    )
    ordering = ('-timestamp', )

    def column_movements(self, obj):
        movements = ""
        for mov in obj.validatedmovement_set.all():
            movements += "%s<br>" % str(mov)
        return movements
    column_movements.allow_tags = True

    def readonly_movements(self, obj):
        movements = ""
        for mov in obj.validatedmovement_set.all():
            movements += "%s %s<br>" % (mov.address, mov.disp_amount)
        return movements
    readonly_movements.allow_tags = True
    readonly_movements.short_description = "Movements"

class EpochSummaryAdmin(admin.ModelAdmin):
    list_display = ('epoch', 'transaction_count', 'ledger_hash')
    ordering = ('-epoch', )
    readonly_fields = ('epoch', 'transaction_count', 'ledger_hash')

admin.site.register(Peer, PeerAdmin)
admin.site.register(LedgerEntry, LedgerAdmin)
admin.site.register(ValidatedTransaction, ValidatedTransactionAdmin)
admin.site.register(EpochSummary, EpochSummaryAdmin)
