from django.shortcuts import render,redirect

# Create your views here.
# subscriptions/views.py
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.http import HttpResponse
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.contrib.auth.models import User
import razorpay
import hmac
import hashlib
import json

from .models import SubscriptionPlan, UserSubscription
from .serializers import SubscriptionPlanSerializer, UserSubscriptionSerializer

# Initialize Razorpay client
try:
    razorpay_client = razorpay.Client(
        auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
    )
except Exception as e:
    print(f"Could not initialize Razorpay client: {e}")
    razorpay_client = None

class SubscriptionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Handles listing plans and creating payment orders.
    """
    queryset = SubscriptionPlan.objects.all()
    serializer_class = SubscriptionPlanSerializer
    permission_classes = [IsAuthenticated] # Only logged-in users can see plans

    @action(detail=True, methods=['post'])
    def create_order(self, request, pk=None):
        """
        Create a Razorpay order for the selected plan (pk).
        """
        if not razorpay_client:
             return Response(
                {'error': 'Payment gateway is not configured.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
            
        try:
            plan = self.get_object()
        except SubscriptionPlan.DoesNotExist:
            return Response({'error': 'Plan not found.'}, status=status.HTTP_404_NOT_FOUND)

        user = request.user
        
        # Prevent buying a new plan if one is already active
        if user.profile.has_active_subscription:
            return Response(
                {'error': 'You already have an active subscription.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        amount_in_paise = int(plan.price * 100) # Razorpay requires amount in paise

        try:
            order_data = {
                "amount": amount_in_paise,
                "currency": "INR",
                "receipt": f"sub_{plan.id}_user_{user.id}_{timezone.now().timestamp()}",
                "notes": {
                    "plan_id": plan.id,
                    "user_id": user.id,
                    "email": user.email
                }
            }
            order = razorpay_client.order.create(data=order_data)
            
            return Response({
                "order_id": order['id'],
                "amount": order['amount'],
                "currency": order['currency'],
                "razorpay_key": settings.RAZORPAY_KEY_ID,
                "plan_name": plan.name,
                "user_name": user.username,
                "user_email": user.email
            }, status=status.HTTP_201_CREATED)
        
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['post'])
    def verify_payment(self, request):
        """
        1. Verifies the signature sent from the client-side handler.
        2. Activates the subscription.
        (Alternative to Webhook for immediate feedback)
        """
        if not razorpay_client:
             return Response(
                {'error': 'Payment gateway is not configured.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )

        data = request.data
        razorpay_payment_id = data.get('razorpay_payment_id')
        razorpay_order_id = data.get('razorpay_order_id')
        razorpay_signature = data.get('razorpay_signature')
        
        # 1. VERIFY SIGNATURE
        try:
            razorpay_client.utility.verify_payment_signature({
                'razorpay_order_id': razorpay_order_id,
                'razorpay_payment_id': razorpay_payment_id,
                'razorpay_signature': razorpay_signature
            })
        except Exception as e:
            # Payment failed verification (tampering or invalid data)
            return Response({'error': f'Signature verification failed: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

        # 2. GET USER/PLAN DETAILS from the Order (must be done AFTER verification)
        try:
            order = razorpay_client.order.fetch(razorpay_order_id)
            notes = order['notes']
            user_id = notes.get('user_id')
            plan_id = notes.get('plan_id')

            user = User.objects.get(id=user_id)
            plan = SubscriptionPlan.objects.get(id=plan_id)
            
            # 3. ACTIVATE THE SUBSCRIPTION
            # Use get_or_create to prevent duplicates if the webhook fires later
            UserSubscription.objects.get_or_create(
                user=user,
                plan=plan,
                defaults={
                    'razorpay_order_id': razorpay_order_id,
                    'razorpay_payment_id': razorpay_payment_id,
                    # start_date and end_date will be set by the model
                }
            )
            
            return Response({'message': 'Payment successfully verified and subscription activated.'}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({'error': f'Subscription activation failed: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    

    @action(detail=False, methods=['get'])
    def my_subscription(self, request):
        """
        Get the user's current active subscription status.
        """
        subscription = UserSubscription.objects.filter(
            user=request.user,
            end_date__gt=timezone.now()
        ).order_by('-end_date').first()
        
        if subscription:
            serializer = UserSubscriptionSerializer(subscription)
            return Response(serializer.data)
        else:
            # Return a consistent object even if no subscription
            return Response({
                'id': None,
                'plan': None,
                'start_date': None,
                'end_date': None,
                'is_active': False
            }, status=status.HTTP_200_OK)


# --- WEBHOOK ---
# This is a separate function, NOT in the ViewSet.
# It must be exempt from CSRF checks as it comes from Razorpay.

@csrf_exempt
def razorpay_webhook(request):
    """
    Handles the webhook from Razorpay after a successful payment.
    This is what *actually* activates the subscription.
    """
    if request.method != "POST":
        return HttpResponse(status=405) # 405 Method Not Allowed

    body = request.body.decode('utf-8')
    received_signature = request.headers.get('X-Razorpay-Signature')

    # 1. Verify the signature
    try:
        secret = settings.RAZORPAY_WEBHOOK_SECRET
        
        # 💡 CHANGE 2: Robust signature calculation and comparison
        calculated_signature = hmac.new(
            secret.encode('utf-8'),
            body.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        if not hmac.compare_digest(calculated_signature, received_signature):
            print("WEBHOOK SIGNATURE MISMATCH")
            # 💡 CHANGE 3: Use HttpResponse and integer status code
            return HttpResponse('Invalid signature', status=400) 
            
    except Exception as e:
        # Catch errors during signature verification (e.g., secret missing)
        print(f"WEBHOOK SIGNATURE ERROR: {e}")
        # 💡 CHANGE 4: Use HttpResponse and integer status code
        return HttpResponse('Internal signature verification error', status=500)

    # 2. Process the event
    try:
        event_data = json.loads(body)
        event_type = event_data['event']
        
        # Extract payment IDs outside the conditional, just in case needed for logging/other events
        payment_entity = event_data.get('payload', {}).get('payment', {}).get('entity', {})
        razorpay_order_id = payment_entity.get('order_id')
        razorpay_payment_id = payment_entity.get('id')

        if event_type == 'payment.captured':
            notes = payment_entity['notes']
            
            user_id = notes.get('user_id')
            plan_id = notes.get('plan_id')

            if not user_id or not plan_id:
                print("WEBHOOK ERROR: Missing user_id or plan_id in notes")
                # 💡 CHANGE 5: Use HttpResponse and integer status code
                return HttpResponse('Missing notes data', status=400)

            # 3. ACTIVATE THE SUBSCRIPTION
            user = User.objects.get(id=user_id)
            plan = SubscriptionPlan.objects.get(id=plan_id)
            
            # 💡 CHANGE 6: Use get_or_create for idempotency (prevents duplicates on retries)
            UserSubscription.objects.get_or_create(
                user=user,
                plan=plan,
                # Use a field that can be constrained to prevent duplicate records (e.g., order ID)
                defaults={
                    'razorpay_order_id': razorpay_order_id,
                    'razorpay_payment_id': razorpay_payment_id,
                }
            )
            
            print(f"SUCCESS: Subscription activated for user {user.id} with plan {plan.id}")
            
        # 💡 CHANGE 7: Final return statement is NOW outside the IF block, but inside the main TRY block.
        # This ensures a 200 OK for ALL successfully processed events (including non-captured ones).
        return HttpResponse(status=200)

    except (User.DoesNotExist, SubscriptionPlan.DoesNotExist):
        # 💡 CHANGE 8: Catch specific DNE errors and return a 404/400.
        print("WEBHOOK PROCESSING ERROR: User or Plan not found")
        return HttpResponse('User or Plan not found', status=404)
        
    except Exception as e:
        # Catch all other unexpected errors during event processing.
        print(f"WEBHOOK PROCESSING ERROR: {e}")
        # 💡 CHANGE 9: Use HttpResponse and integer status code
        return HttpResponse({'error': 'Internal server error'}, status=500)
   
# The function should no longer reach this line due to the initial check and final 200.
# The original final line was deleted: return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED)

# subscriptions/views.py (Add this new function)

@csrf_exempt
def payment_callback(request):
    """
    Handles the redirection from Razorpay's callback_url (CRITICAL for UPI on mobile).
    Razorpay sends this as a GET request with payment details.
    """
    if request.method == "GET":
        razorpay_payment_id = request.GET.get('razorpay_payment_id')
        razorpay_order_id = request.GET.get('razorpay_order_id')
        razorpay_signature = request.GET.get('razorpay_signature')
        
        # ⚠️ NOTE: The signature may be missing or invalid on some mobile redirects.
        # It is safer to rely on the payment_id and fetch its status from Razorpay API here.
        
        # 1. Fetch Payment Status
        try:
            payment_info = razorpay_client.payment.fetch(razorpay_payment_id)
            status_info = payment_info.get('status')
            
            if status_info == 'captured':
                # 2. Get User/Plan details (from the order notes)
                order = razorpay_client.order.fetch(razorpay_order_id)
                notes = order['notes']
                user_id = notes.get('user_id')
                plan_id = notes.get('plan_id')
                
                user = User.objects.get(id=user_id)
                plan = SubscriptionPlan.objects.get(id=plan_id)
                
                # 3. ACTIVATE THE SUBSCRIPTION (Same logic as verify_payment)
                UserSubscription.objects.get_or_create(
                    user=user,
                    plan=plan,
                    defaults={
                        'razorpay_order_id': razorpay_order_id,
                        'razorpay_payment_id': razorpay_payment_id,
                    }
                )

                # 4. FINAL REDIRECT TO FRONTEND DASHBOARD
                # 💡 Add a query param so the frontend can display a success toast
                return redirect(f"https://victor-frontend-blush.vercel.app/dashboard?payment=success") # ⚠️ **Update domain!**
            
            else:
                # Payment was failed, authorized, or another status
                return redirect(f"https://victor-frontend-blush.vercel.app/dashboard/price?payment=failed") # ⚠️ **Update domain!**

        except Exception as e:
            # Log the error and redirect back to the pricing page with an error
            print(f"PAYMENT CALLBACK ERROR: {e}")
            return redirect(f"https://victor-frontend-blush.vercel.app/dashboard/price?payment=error") # ⚠️ **Update domain!**
    
    return HttpResponse(status=405)