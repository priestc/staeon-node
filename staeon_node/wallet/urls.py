from django.conf.urls import url, include
from .views import (
    serv_wallet, accept_remote_registration, register_new_wallet_user, login
)
urlpatterns = [
    url(r'^', serv_wallet, name="wallet"),
    url(r'registration/remote', accept_remote_registration),
    url(r'registration', register_new_wallet_user, name='register_new_wallet_user'),
    url(r'^login', login, name='login'),
]
