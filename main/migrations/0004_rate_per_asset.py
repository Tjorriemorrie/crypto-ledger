# Written by hand: makemigrations cannot rename a field or fill a new one in non-interactive
# mode, so it would have dropped and recreated the columns, throwing away the rates already
# downloaded. Every existing row is a BTC price, which is what the added column is set to.

from django.db import migrations, models

import main.models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0003_transaction_occurred_on'),
    ]

    operations = [
        migrations.AlterField(
            model_name='account',
            name='currency',
            field=models.CharField(
                choices=[
                    ('ZAR', 'ZAR — South African rand'),
                    ('BTC', 'BTC — Bitcoin'),
                    ('USDT', 'USDT — Tether'),
                    ('USDC', 'USDC — USD Coin'),
                ],
                default=main.models.Currency['ZAR'],
                help_text='The asset this account holds.',
                max_length=4,
            ),
        ),
        migrations.AlterModelOptions(
            name='exchangerate',
            options={'ordering': ['-date', 'asset']},
        ),
        migrations.RenameField(
            model_name='exchangerate',
            old_name='zar_per_btc',
            new_name='zar_per_unit',
        ),
        migrations.AlterField(
            model_name='exchangerate',
            name='zar_per_unit',
            field=models.DecimalField(
                decimal_places=18,
                help_text='The price of one unit of the asset in ZAR.',
                max_digits=32,
            ),
        ),
        migrations.AlterField(
            model_name='exchangerate',
            name='date',
            field=models.DateField(),
        ),
        migrations.AddField(
            model_name='exchangerate',
            name='asset',
            field=models.CharField(
                choices=[('BTC', 'Bitcoin'), ('USD', 'US dollar')],
                default='BTC',
                max_length=3,
            ),
            preserve_default=False,
        ),
        migrations.AddConstraint(
            model_name='exchangerate',
            constraint=models.UniqueConstraint(
                fields=('date', 'asset'), name='rate_unique_asset_per_date'
            ),
        ),
    ]
