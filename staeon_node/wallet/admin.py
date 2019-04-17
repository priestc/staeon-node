# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.contrib import admin
from .models import WalletSeed

class WalletAdmin(admin.ModelAdmin):
    pass

admin.site.register(WalletSeed, WalletAdmin)
