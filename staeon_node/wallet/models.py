# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import datetime
from django.db import models

class WalletSeed(models.Model):
    user = models.ForeignKey('auth.User')
    encrypted_mnemonic = models.CharField(max_length=172)

class FailedLogin(models.Model):
    username = models.CharField(max_length=64, db_index=True)
    time = models.DateTimeField(default=datetime.datetime.now)

    class Meta:
        get_latest_by = 'time'
