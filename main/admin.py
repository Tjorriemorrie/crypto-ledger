"""Admin registration, useful for correcting data the UI deliberately keeps simple."""

from django.contrib import admin

from main.models import Account, Entry, ExchangeRate, Match, Transaction


class EntryInline(admin.TabularInline):
    model = Entry
    extra = 0


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ["name", "currency", "created_at"]
    search_fields = ["name", "currency"]


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ["occurred_on", "description"]
    date_hierarchy = "occurred_on"
    inlines = [EntryInline]


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ["debit", "credit", "quantity", "created_at"]


@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    list_display = ["date", "asset", "zar_per_unit", "fetched_at"]
    list_filter = ["asset"]
    date_hierarchy = "date"
