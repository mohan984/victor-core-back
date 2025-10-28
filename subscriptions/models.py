from django.db import models

# Create your models here.
# subscriptions/models.py

from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import timedelta

class SubscriptionPlan(models.Model):
    """Stores the details of a plan you offer, e.g., '12-Month Access'."""
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=8, decimal_places=2) # e.g., 299.00
    duration_days = models.IntegerField(default=365)
    
    def __str__(self):
        return f"{self.name} (₹{self.price} for {self.duration_days} days)"

class UserSubscription(models.Model):
    """Links a user to a subscription they have purchased."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name="user_subscriptions"
    )
    plan = models.ForeignKey(
        SubscriptionPlan, 
        on_delete=models.PROTECT,  # Don't delete a plan if users have it
        related_name="subscriptions"
    )
    start_date = models.DateTimeField(auto_now_add=True)
    end_date = models.DateTimeField()
    
    def save(self, *args, **kwargs):
        # Set the end_date automatically when creating a new subscription
        if not self.id: # Only on creation
            self.end_date = timezone.now() + timedelta(days=self.plan.duration_days)
        super().save(*args, **kwargs)

    @property
    def is_active(self):
        """A property to check if the subscription is currently valid."""
        return self.end_date > timezone.now()
    
    def __str__(self):
        return f"{self.user.username}'s {self.plan.name} (Expires: {self.end_date.strftime('%Y-%m-%d')})"