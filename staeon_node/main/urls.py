from django.conf.urls import include, url
from django.views.generic import TemplateView

from views import (
    accept_tx, consensus_push, consensus_penalty, peers, network_summary,
    rejections, ledger
)

urlpatterns = [
    url(r'^transaction/', accept_tx),
    url(r'^consensus/push', consensus_push),
    url(r'^consensus/penalty', consensus_penalty),
    #url(r'^consensus/push', consensus_push),
    url(r'^peers/', peers),
    url(r'^rejections/', rejections, name="rejections"),

    url(r'^ledger/', ledger),
    url(r'^summary/', network_summary, name="summary"),
]
