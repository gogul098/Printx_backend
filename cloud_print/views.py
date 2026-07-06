import hmac
import hashlib
import json
import razorpay
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
from .tasks import trigger_telegram_delivery_task

@csrf_exempt
def create_order(request):
    try:
        # 1. Print the raw data exactly as Android sent it
        print("📥 INCOMING DATA FROM ANDROID:", request.body.decode('utf-8'))
        
        data = json.loads(request.body)
        
        claimed_pages = int(data.get('claimed_pages', 1))
        copies = int(data.get('copies', 1))
        color_mode = data.get('color_mode', 'bw')
        sides = data.get('sides', 'single')
        binding = data.get('binding', 'none')
        
        # Exact price calculation rules:
        if color_mode == 'color' and sides == 'single':
            per_page_price = 10.0
        elif color_mode == 'color' and sides == 'double':
            per_page_price = 7.5
        elif color_mode == 'bw' and sides == 'single':
            per_page_price = 3.0
        elif color_mode == 'bw' and sides == 'double':
            per_page_price = 2.0
        else:
            per_page_price = 3.0
            
        printing_cost = claimed_pages * copies * per_page_price
        
        if binding.lower() == 'soft binding':
            binding_cost = 60.0
        elif binding.lower() == 'spiral binding':
            binding_cost = 80.0
        else:
            binding_cost = 0.0
            
        total_price = printing_cost + binding_cost
        
        # Generate Razorpay Order
        razorpay_client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        razorpay_order = razorpay_client.order.create(dict(
            amount=int(total_price * 100),
            currency='INR',
            payment_capture='1'
        ))
        
        # We no longer save to the local SQL database here.
        # The frontend will save the order details directly to Firebase.
        

        return JsonResponse({
            'order_id': razorpay_order['id'],
            'amount': total_price,
            'currency': 'INR'
        })
    except KeyError as e:
        print(f"🚨 MISSING FIELD IN JSON: {e}")
        return JsonResponse({'error': f"Missing field: {e}"}, status=400)
    except Exception as e:
        print(f"🚨 CRITICAL ERROR: {e}")
        return JsonResponse({'error': str(e)}, status=400)

@csrf_exempt
def verify_payment(request):
    if request.method != "POST":
        return HttpResponseBadRequest("Invalid Request Method")
    
    try:
        data = json.loads(request.body)
        razorpay_payment_id = data.get('razorpay_payment_id')
        razorpay_order_id = data.get('razorpay_order_id')
        razorpay_signature = data.get('razorpay_signature')
        
        if not razorpay_payment_id or not razorpay_order_id or not razorpay_signature:
            return HttpResponseBadRequest("Missing required fields")
            
        generated_signature = hmac.new(
            settings.RAZORPAY_KEY_SECRET.encode('utf-8'),
            f"{razorpay_order_id}|{razorpay_payment_id}".encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        if hmac.compare_digest(generated_signature, razorpay_signature):
            return JsonResponse({'status': 'success', 'message': 'Payment verified successfully'})
        else:
            return HttpResponseBadRequest("Signature mismatch")
            
    except Exception as e:
        return HttpResponseBadRequest(f"Error verifying payment: {str(e)}")

@csrf_exempt
def razorpay_webhook(request):
    print("====== RAZORPAY WEBHOOK RECEIVED ======")
    if request.method != "POST":
        print("Webhook Error: Invalid Request Method")
        return HttpResponseBadRequest("Invalid Request Method")
        
    # 1. Get the signature sent by Razorpay
    webhook_signature = request.headers.get('X-Razorpay-Signature')
    webhook_secret = settings.RAZORPAY_WEBHOOK_SECRET
    
    if not webhook_signature:
        print("Webhook Error: Missing Signature in headers")
        return HttpResponseBadRequest("Missing Signature")
    
    # 2. Recompute the hash using your secret and the raw request body
    raw_body = request.body
    expected_signature = hmac.new(
        webhook_secret.encode('utf-8'),
        raw_body,
        hashlib.sha256
    ).hexdigest()
    
    # 3. Check for equivalence
    if not hmac.compare_digest(expected_signature, webhook_signature):
        print("Webhook Error: Invalid Signature (secrets do not match)")
        return HttpResponseBadRequest("Invalid Signature")
        
    # 4. Parse payload securely
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        print("Webhook Error: Invalid JSON Payload")
        return HttpResponseBadRequest("Invalid JSON Payload")
        
    event = payload.get('event')
    print(f"Webhook Success: Valid signature! Event type: {event}")
    
    if event == "payment.captured":
        try:
            order_id = payload['payload']['payment']['entity']['order_id']
            print(f"Payment Captured successfully for Order: {order_id}. Running Task Synchronously...")
            # Run directly to avoid Celery background worker memory limits on Render Free Tier
            trigger_telegram_delivery_task(order_id) 
            print(f"Task finished successfully for Order: {order_id}")
        except KeyError:
            print("Webhook Error: Invalid Event Payload Structure (missing order_id)")
            return HttpResponseBadRequest("Invalid Event Payload Structure")
            
    return HttpResponse(status=200)
