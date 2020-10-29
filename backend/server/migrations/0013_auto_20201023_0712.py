# Generated by Django 3.1.2 on 2020-10-23 07:12

import django.core.validators
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('server', '0012_auto_20200614_0106'),
    ]

    operations = [
        migrations.AddField(
            model_name='match',
            name='margin',
            field=models.IntegerField(blank=True, null=True, validators=[django.core.validators.MinValueValidator(0)]),
        ),
        migrations.AddField(
            model_name='match',
            name='winner',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='server.team'),
        ),
    ]