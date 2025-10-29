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
    # New API endpoint for client-side handler verification
    path('verify_payment/', views.SubscriptionViewSet.as_view({'post': 'verify_payment'}), name='verify-payment'),
    # New View for Razorpay mobile redirect (callback_url)
    path('payment_callback/', views.payment_callback, name='razorpay-callback'),
]