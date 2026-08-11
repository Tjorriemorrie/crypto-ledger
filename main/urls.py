"""URL routes for the ledger."""

from django.urls import path

from main import views

urlpatterns = [
    path("", views.account_list, name="account-list"),
    path("rate/refresh/", views.rate_refresh, name="rate-refresh"),
    path("accounts/new/", views.account_create, name="account-create"),
    path("accounts/<int:pk>/", views.account_detail, name="account-detail"),
    path("accounts/<int:pk>/edit/", views.account_edit, name="account-edit"),
    path(
        "accounts/<int:pk>/transactions/new/",
        views.transaction_create,
        name="transaction-create",
    ),
    path(
        "accounts/<int:pk>/transactions/<int:transaction_pk>/delete/",
        views.transaction_delete,
        name="transaction-delete",
    ),
    path("entries/<int:pk>/match/", views.entry_match, name="entry-match"),
]
