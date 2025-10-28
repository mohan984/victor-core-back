# accounts/signals.py

from django.db.models.signals import post_save
from django.contrib.auth.models import User
from django.dispatch import receiver
from .models import UserProfile

@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    """
    Creates a UserProfile when a new User is created and saves it on subsequent updates.
    """
    if created:
        # Safely create the profile only if it doesn't already exist.
        UserProfile.objects.get_or_create(user=instance)
    
    # Save the profile every time the user object is saved.
    instance.profile.save()