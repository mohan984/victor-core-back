# accounts/serializers.py
from rest_framework import serializers
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from exams.models import TestSubmission
from django.db.models import Avg
from django.utils import timezone
from datetime import timedelta
from .models import UserProfile

class SignupSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        required=True,
        validators=[validate_password],
        style={'input_type': 'password'}
    )
    confirm_password = serializers.CharField(
        write_only=True,
        required=True,
        style={'input_type': 'password'}
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'confirm_password']

    def validate(self, attrs):
        if attrs['password'] != attrs['confirm_password']:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        return attrs

    def create(self, validated_data):
        # Remove confirm_password; not needed in User model
        validated_data.pop('confirm_password')

        # Create the user safely (hashes password automatically)
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data.get('email'),
            password=validated_data['password']
        )

        # Optionally, update any UserProfile fields here (reward_points, etc.)
        # The profile already exists because the post_save signal creates it
        profile = user.profile
        profile.reward_points = 0  # or any default value you want
        profile.save()

        return user



# users/serializers.py
class UserProfileSerializer(serializers.ModelSerializer):

    # This pulls 'reward_points' from the related UserProfile model
    reward_points = serializers.IntegerField(source='profile.reward_points', read_only=True) 
    # --- ADD THESE TWO LINES ---
    has_active_subscription = serializers.BooleanField(source='profile.has_active_subscription', read_only=True)
    subscription_end_date = serializers.DateTimeField(source='profile.active_subscription_end_date', read_only=True)

    completed_tests_today = serializers.SerializerMethodField()
    average_score_today = serializers.SerializerMethodField()
    current_streak = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "email", "completed_tests_today", "average_score_today", "current_streak", "reward_points"
                  ,"has_active_subscription", "subscription_end_date" ] # <-- ADD

    def get_completed_tests_today(self, obj):
        today = timezone.now().date()
        return obj.submissions.filter(status="completed", finished_at__date=today).count()

    def get_average_score_today(self, obj):
        today = timezone.now().date()
        return (
            obj.submissions.filter(status="completed", finished_at__date=today)
            .aggregate(avg=Avg("score"))["avg"] or 0
        )


     # ... inside your UserSerializer class

    def get_current_streak(self, obj):
        today = timezone.now().date()
        
        # Check if the user has completed at least 5 tests today
        tests_today = obj.submissions.filter(status="completed", finished_at__date=today).count()

        # Determine the starting date for the streak calculation
        if tests_today >= 5:
            # If the goal is met today, the streak includes today.
            # Start checking from today and go backwards.
            check_date = today
        else:
            # If the goal isn't met today, the streak is based on previous days.
            # Start checking from yesterday and go backwards.
            check_date = today - timedelta(days=1)

        streak = 0
        while True:
            # Count completed tests for the check_date
            tests_on_day = obj.submissions.filter(status="completed", finished_at__date=check_date).count()

            if tests_on_day >= 5:
                streak += 1
                # Move to the previous day
                check_date -= timedelta(days=1)
            else:
                # The streak is broken, so stop counting
                break
                
        return streak

