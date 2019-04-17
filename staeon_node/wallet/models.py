# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import datetime
from django.db import models

class WalletSeed(models.Model):
    user = models.ForeignKey('auth.User')
    encrypted_mnemonic = models.CharField(max_length=172)
    change_balances = models.TextField(default='', blank=True)
    deposit_balances = models.TextField(default='', blank=True)

    def __unicode__(self):
        return self.user.username

    def get_settings(self):
        return {
            'change_balances': self.change_balances,
            'deposit_balances': self.deposit_balances
        }

class FailedLogin(models.Model):
    username = models.CharField(max_length=64, db_index=True)
    time = models.DateTimeField(default=datetime.datetime.now)

    class Meta:
        get_latest_by = 'time'
