#accounts/models.py
from django.db import models
from django.conf import settings 
from django.utils import timezone
from subscriptions.models import UserSubscription # <-- IMPORT THIS

# Create your models here.

# Create your models here.
class UserProfile(models.Model):
    """
    Stores extra data for each user, like reward points.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        # This related_name is how we'll access this from the User object (e.g., user.profile)
        related_name="profile" 
    )
    reward_points = models.PositiveIntegerField(default=0, help_text="Total reward points accumulated by the user.")

    def __str__(self):
        return f"{self.user.username}'s Profile"
    
    # --- ADD THESE TWO PROPERTIES ---

    @property
    def has_active_subscription(self):
        """Checks if the user has ANY active subscription."""
        return UserSubscription.objects.filter(
            user=self.user,
            end_date__gt=timezone.now()
        ).exists()
    
    @property
    def active_subscription_end_date(self):
        """Gets the end date of the *latest* active subscription."""
        latest_sub = UserSubscription.objects.filter(
            user=self.user,
            end_date__gt=timezone.now()
        ).order_by('-end_date').first()
        return latest_sub.end_date if latest_sub else None
