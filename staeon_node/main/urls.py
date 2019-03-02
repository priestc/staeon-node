from django.conf.urls import include, url
from django.views.generic import TemplateView

from views import (
    accept_tx, consensus, peers, network_summary,
    rejections, sync
)

urlpatterns = [
    url(r'^transaction/', accept_tx),
    url(r'^consensus/', consensus),
    url(r'^peers/', peers),
    url(r'^rejections/', rejections, name="rejections"),

    url(r'^sync/', sync),
    url(r'^summary/', network_summary, name="summary"),
]
