import os
import boto3
import firebase_admin
from firebase_admin import credentials, firestore
import json
from dotenv import load_dotenv

load_dotenv()

def test_firebase():
    print("Testing Firebase...")
    try:
        firebase_json_str = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
        if not firebase_json_str:
            print("FIREBASE_SERVICE_ACCOUNT_JSON not found in env")
            return
            
        cred_dict = json.loads(firebase_json_str)
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
        
        db = firestore.client()
        # Just try to get collections
        collections = db.collections()
        print("Firebase connection successful! Collections available:")
        for coll in collections:
            print(f" - {coll.id}")
            
    except Exception as e:
        print(f"Firebase connection failed: {e}")

def test_b2():
    print("\nTesting Backblaze B2...")
    try:
        b2_endpoint_url = os.environ.get("B2_ENDPOINT_URL")
        b2_key_id = os.environ.get("B2_KEY_ID")
        b2_application_key = os.environ.get("B2_APPLICATION_KEY")
        b2_bucket_name = os.environ.get("B2_BUCKET_NAME")
        
        s3 = boto3.client('s3',
                          endpoint_url=b2_endpoint_url,
                          aws_access_key_id=b2_key_id,
                          aws_secret_access_key=b2_application_key)
        
        # Try to list objects in the bucket (max 5)
        response = s3.list_objects_v2(Bucket=b2_bucket_name, MaxKeys=5)
        print("Backblaze B2 connection successful!")
        if 'Contents' in response:
            print("Sample files found in bucket:")
            for obj in response['Contents']:
                print(f" - {obj['Key']}")
        else:
            print("Bucket is empty or no files found.")
            
    except Exception as e:
        print(f"Backblaze connection failed: {e}")

if __name__ == "__main__":
    test_firebase()
    test_b2()
