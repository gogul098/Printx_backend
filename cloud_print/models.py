from django.db import models

class PrintOrder(models.Model):
    razorpay_order_id = models.CharField(max_length=255, unique=True)
    status = models.CharField(max_length=50, default="Pending")
    firebase_file_path = models.CharField(max_length=500)
    file_name = models.CharField(max_length=255)
    
    # Trust but Verify fields
    claimed_pages = models.IntegerField(default=1)
    actual_pages = models.IntegerField(null=True, blank=True)
    price_calculated = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    
    color_mode = models.CharField(max_length=50)
    copies = models.IntegerField(default=1)
    binding_type = models.CharField(max_length=100)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Order {self.id} - {self.status}"
