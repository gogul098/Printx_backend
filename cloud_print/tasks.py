import requests
from celery import shared_task
import firebase_admin
from firebase_admin import credentials, storage
from django.conf import settings
from .models import PrintOrder
import io
import PyPDF2
import os
import json

@shared_task(name="trigger_telegram_delivery_task")
def trigger_telegram_delivery_task(order_id):
    # Ensure Firebase is initialized
    if not firebase_admin._apps:
        # Note: In production, pass the correct credentials object to initialize_app
        firebase_json_str = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
        if firebase_json_str:
            cred_dict = json.loads(firebase_json_str)
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
        else:
            # Fallback to default/local setup if needed
            firebase_admin.initialize_app()
        
    # 1. Look up order configuration from DB
    order = PrintOrder.objects.get(razorpay_order_id=order_id)
    order.status = "Paid"
    order.save()
    
    # 2. Connect to Firebase Storage bucket
    # Replace 'your-bucket-name' with your actual bucket name or configure it in settings
    bucket = storage.bucket('your-bucket-name.appspot.com')
    blob = bucket.blob(order.firebase_file_path)
    
    # 3. Stream the file directly into memory or a temporary file
    file_data = blob.download_as_bytes()
    
    # 4. Verify Actual Pages (Trust but Verify)
    actual_pages = order.claimed_pages # default to claimed if parsing fails
    try:
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_data))
        actual_pages = len(pdf_reader.pages)
        order.actual_pages = actual_pages
        order.save()
    except Exception as e:
        print(f"Error parsing PDF for order {order.id}: {str(e)}")
        
    fraud_alert = ""
    if actual_pages > order.claimed_pages:
        fraud_alert = (
            "🚨 FRAUD ALERT - DO NOT PRINT 🚨\n"
            f"User paid for: {order.claimed_pages} pages\n"
            f"Actual file contains: {actual_pages} pages\n"
            "Action required: Collect remaining balance before printing.\n\n"
        )
    
    # 5. Compile the print instruction caption for the shop owner
    caption_text = (
        f"{fraud_alert}"
        f"🖨️ **New Print Order!**\n"
        f"🆔 Order ID: {order.id}\n"
        f"📄 Claimed Pages: {order.claimed_pages}\n"
        f"📄 Actual Pages: {actual_pages}\n"
        f"🎨 Mode: {order.color_mode}\n"
        f"📚 Copies: {order.copies}\n"
        f"📎 Binding: {order.binding_type}\n"
        f"💵 Amount Paid: ₹{order.price_calculated}"
    )
    
    # 6. Push to Telegram Bot API
    bot_token = settings.TELEGRAM_BOT_TOKEN
    chat_id = settings.SHOP_TELEGRAM_CHAT_ID
    url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
    
    files = {'document': (order.file_name, file_data)}
    data = {'chat_id': chat_id, 'caption': caption_text, 'parse_mode': 'Markdown'}
    
    response = requests.post(url, files=files, data=data)
    
    if response.status_code == 200:
        order.status = "Sent to Printer"
        order.save()
