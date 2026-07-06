from django.contrib import admin
from django.urls import path
from cloud_print.views import razorpay_webhook, create_order, verify_payment

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/webhooks/razorpay/", razorpay_webhook, name="razorpay_webhook"),
    path("api/orders/create/", create_order, name="create_order"),
    path("api/verify-payment/", verify_payment, name="verify_payment"),
]
