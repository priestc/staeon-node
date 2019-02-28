from django.conf.urls import include, url
from django.views.generic import TemplateView

from views import (
    accept_tx, accept_push, return_pull, get_peers, network_summary,
    rejections
)

urlpatterns = [
    url(r'^accept_tx/', accept_tx),
    url(r'^push/', accept_push),
    url(r'^pull/', return_pull),
    url(r'^peerlist/', get_peers),
    url(r'^summary/', network_summary, name="summary"),
    url(r'^rejections/', rejections, name="rejections")
]
