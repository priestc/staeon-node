# -*- coding: utf-8 -*-
# Generated by Django 1.11.18 on 2019-04-16 18:34
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('wallet', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='walletseed',
            name='change_balances',
            field=models.TextField(default=''),
        ),
        migrations.AddField(
            model_name='walletseed',
            name='deposit_balances',
            field=models.TextField(default=''),
        ),
    ]
