from django.contrib import admin

# Register your models here.
# subscriptions/admin.py
from django.contrib import admin
from .models import SubscriptionPlan, UserSubscription

admin.site.register(SubscriptionPlan)
admin.site.register(UserSubscription)