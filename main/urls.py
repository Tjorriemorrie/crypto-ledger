"""URL routes for the ledger."""

from django.urls import path

from main import views

urlpatterns = [
    path("", views.account_list, name="account-list"),
    path("rate/refresh/", views.rate_refresh, name="rate-refresh"),
    path("rate/chart/", views.price_chart, name="price-chart"),
    path("profit/chart/", views.profit_chart, name="profit-chart"),
    path("cgt/", views.cgt_report, name="cgt-report"),
    path("analysis/", views.analysis, name="analysis"),
    path("analysis/sweep/", views.analysis_sweep, name="analysis-sweep"),
    path("analysis/plan/", views.analysis_plan, name="analysis-plan"),
    path("accounts/new/", views.account_create, name="account-create"),
    path("accounts/<int:pk>/", views.account_detail, name="account-detail"),
    path("accounts/<int:pk>/edit/", views.account_edit, name="account-edit"),
    path(
        "accounts/<int:pk>/transactions/new/",
        views.transaction_create,
        name="transaction-create",
    ),
    path(
        "accounts/<int:pk>/transactions/<int:transaction_pk>/edit/",
        views.transaction_edit,
        name="transaction-edit",
    ),
    path(
        "accounts/<int:pk>/transactions/<int:transaction_pk>/delete/",
        views.transaction_delete,
        name="transaction-delete",
    ),
    path(
        "accounts/<int:pk>/transactions/<int:transaction_pk>/cgt/",
        views.transaction_cgt,
        name="transaction-cgt",
    ),
]
