# subscriptions/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'plans', views.SubscriptionViewSet, basename='subscription')

urlpatterns = [
    path('', include(router.urls)),
    # This is the URL you will give to Razorpay Dashboard
    path('webhook/razorpay/', views.razorpay_webhook, name='razorpay-webhook'), 
]