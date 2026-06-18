import requests
from celery import shared_task
import firebase_admin
from firebase_admin import credentials, firestore
from django.conf import settings
import io
import PyPDF2
import os
import json
import boto3

@shared_task(name="trigger_telegram_delivery_task")
def trigger_telegram_delivery_task(order_id):
    print(f"====== CELERY TASK STARTED for Order {order_id} ======")
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
            
    db = firestore.client()
        
    # 1. Look up order configuration from Firestore
    print(f"[{order_id}] Step 1: Looking up order in Firestore...")
    order_ref = db.collection('orders').document(order_id)
    order_doc = order_ref.get()
    
    if not order_doc.exists:
        print(f"[{order_id}] ERROR: Order not found in Firestore!")
        return
        
    print(f"[{order_id}] Order found in Firestore. Updating status to 'Paid'.")
    order_data = order_doc.to_dict()
    
    # Update status to Paid in Firestore
    order_ref.update({"status": "Paid"})
    
    # Extract order details
    storage_path = order_data.get('storage_path', '')
    file_name = order_data.get('file_name', 'document.pdf')
    claimed_pages = int(order_data.get('claimed_pages', 1))
    color_mode = order_data.get('color_mode', 'bw')
    copies = int(order_data.get('copies', 1))
    binding_type = order_data.get('binding_type', 'none')
    price_calculated = order_data.get('price_calculated', 0.0)
    
    # 2. Connect to Backblaze B2 via boto3
    print(f"[{order_id}] Step 2: Connecting to Backblaze B2...")
    b2_endpoint_url = os.environ.get("B2_ENDPOINT_URL")
    b2_key_id = os.environ.get("B2_KEY_ID")
    b2_application_key = os.environ.get("B2_APPLICATION_KEY")
    b2_bucket_name = os.environ.get("B2_BUCKET_NAME")
    
    s3 = boto3.client('s3',
                      endpoint_url=b2_endpoint_url,
                      aws_access_key_id=b2_key_id,
                      aws_secret_access_key=b2_application_key)
    
    # 3. Stream the file directly into memory
    print(f"[{order_id}] Step 3: Downloading file from Backblaze path '{storage_path}'...")
    file_obj = io.BytesIO()
    try:
        s3.download_fileobj(b2_bucket_name, storage_path, file_obj)
        file_data = file_obj.getvalue()
        print(f"[{order_id}] Download successful! File size: {len(file_data)} bytes.")
    except Exception as e:
        print(f"[{order_id}] ERROR downloading file from Backblaze B2: {str(e)}")
        return
    
    # 4. Verify Actual Pages (Trust but Verify)
    print(f"[{order_id}] Step 4: Parsing PDF to verify page count...")
    actual_pages = claimed_pages # default to claimed if parsing fails
    try:
        pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_data))
        actual_pages = len(pdf_reader.pages)
        order_ref.update({"actual_pages": actual_pages})
        print(f"[{order_id}] PDF parsed. Claimed: {claimed_pages}, Actual: {actual_pages}.")
    except Exception as e:
        print(f"[{order_id}] WARNING: Error parsing PDF: {str(e)}")
        
    fraud_alert = ""
    if actual_pages > claimed_pages:
        fraud_alert = (
            "🚨 FRAUD ALERT - DO NOT PRINT 🚨\n"
            f"User paid for: {claimed_pages} pages\n"
            f"Actual file contains: {actual_pages} pages\n"
            "Action required: Collect remaining balance before printing.\n\n"
        )
    
    # 5. Compile the print instruction caption for the shop owner
    caption_text = (
        f"{fraud_alert}"
        f"🖨️ **New Print Order!**\n"
        f"🆔 Order ID: {order_id}\n"
        f"📄 Claimed Pages: {claimed_pages}\n"
        f"📄 Actual Pages: {actual_pages}\n"
        f"🎨 Mode: {color_mode}\n"
        f"📚 Copies: {copies}\n"
        f"📎 Binding: {binding_type}\n"
        f"💵 Amount Paid: ₹{price_calculated}"
    )
    
    # 6. Push to Telegram Bot API
    bot_token = settings.TELEGRAM_BOT_TOKEN
    chat_id = settings.SHOP_TELEGRAM_CHAT_ID
    url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
    
    files = {'document': (file_name, file_data)}
    data = {'chat_id': chat_id, 'caption': caption_text, 'parse_mode': 'Markdown'}
    
    try:
        response = requests.post(url, files=files, data=data)
        
        if response.status_code == 200:
            order_ref.update({"status": "Sent to Printer"})
            print(f"Successfully sent order {order_id} to Telegram.")
        else:
            print(f"Failed to send order {order_id} to Telegram. Status: {response.status_code}, Error: {response.text}")
    except Exception as e:
        print(f"Exception while sending to Telegram for order {order_id}: {str(e)}")

