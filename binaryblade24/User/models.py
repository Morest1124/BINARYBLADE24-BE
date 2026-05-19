from django.db import models
from django.contrib.auth.models import AbstractUser, Permission, Group
from django.conf import settings # Needed for settings.AUTH_USER_MODEL reference
from django.core.validators import MaxValueValidator, MinValueValidator
from django.contrib.auth.hashers import check_password

from django.db.models import Avg
from decimal import Decimal
from .countries import COUNTRIES

# Generate choices from COUNTRIES list
COUNTRY_CHOICES = [(country['code'], country['name']) for country in COUNTRIES]

class User(AbstractUser):

    # Custom fields added to the core User model
    country_origin = models.CharField(
        max_length=50, 
        blank=False, 
        null=False,
        choices=COUNTRY_CHOICES,
        help_text="Select your country of origin",
        db_index=True  # Index for location-based filtering
    )
    phone_country_code = models.CharField(
        max_length=10,
        blank=True,
        null=True,
        help_text="Phone country code (e.g., +1, +44, +27)"
    )
    email = models.EmailField(blank=False, unique=True)
    phone_number = models.CharField(max_length=15, unique=True, null=True, blank=True)
    identity_number = models.CharField(max_length=255, unique=True, null=False, blank=False)

    # Account management fields
    deactivated_at = models.DateTimeField(
        null=True, 
        blank=True,
        help_text="Timestamp when account was deactivated"
    )
    scheduled_deletion_at = models.DateTimeField(
        null=True,
        blank=True, 
        help_text="Timestamp when account is scheduled for permanent deletion"
    )

    
    # NOTE: profilePicture renamed to profile_picture (snake_case convention)
    profile_picture = models.ImageField(upload_to='profile_pictures/', blank=True, null=True)

    # Verification status
    is_email_verified = models.BooleanField(default=False)
    is_phone_verified = models.BooleanField(default=False)

    # Use 'email' for login:
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'first_name', 'last_name', 'country_origin', 'phone_number', 'identity_number'] 

    # Field overrides (required to avoid Django's default User model conflicts in a custom user model setup)
    groups = models.ManyToManyField(
        Group,
        related_name='custom_user_groups',
        blank=True,
        verbose_name='groups',
    )
    user_permissions = models.ManyToManyField(
        Permission,
        related_name='custom_user_permissions',
        blank=True,
        verbose_name='user permissions',
    )
    roles = models.ManyToManyField('Role', related_name='users')


    def check_identity_number(self, raw_identity_number):
        return check_password(raw_identity_number, self.identity_number)
    
    def get_country_name(self):
        """Get the full country name from the country code."""
        for country in COUNTRIES:
            if country['code'] == self.country_origin:
                return country['name']
        return self.country_origin

    def __str__(self):
        return self.username


class Role(models.Model):
    """Model to represent user roles."""
    name = models.CharField(max_length=20, unique=True)

    def __str__(self):
        return self.name

class OTPCode(models.Model):
    """Stores short-lived OTP codes for email/phone verification."""
    OTP_TYPE_EMAIL = 'email'
    OTP_TYPE_SMS = 'sms'
    OTP_TYPE_CHOICES = [
        (OTP_TYPE_EMAIL, 'Email'),
        (OTP_TYPE_SMS, 'SMS'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='otp_codes'
    )
    code = models.CharField(max_length=6)
    otp_type = models.CharField(max_length=10, choices=OTP_TYPE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)


    def is_valid(self):
        from django.utils import timezone
        return not self.is_used and self.expires_at > timezone.now()

    def __str__(self):
        return f"OTP({self.otp_type}) for {self.user.username} - {'used' if self.is_used else 'active'}"


class Profile(models.Model):

    # One-to-One link to User model
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE, 
        related_name='profile'
    )
    
    # Other non-identity profile fields
    bio = models.TextField(blank=True, null=True)
    address = models.CharField(max_length=255, blank=True, null=True)
    skills = models.CharField(max_length=255, blank=True)
    hourly_rate = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    rating = models.DecimalField(max_digits=2, decimal_places=1, null=True )
    wallet_balance = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0.00'))
    #         validators=[MinValueValidator(0.0), MaxValueValidator(5.0)]),
    avatar = models.ImageField(blank=True)
    show_earnings = models.BooleanField(default=True, help_text="Determine if earnings are shown on public profile")
    
    class SkillLevel(models.TextChoices):
        BEGINNER = 'beginner', 'Beginner'
        JUNIOR = 'junior', 'Junior'
        INTERMEDIATE = 'intermediate', 'Intermediate'
        SENIOR = 'senior', 'Senior'
        EXPERT = 'expert', 'Expert'

    # Field to store the user's skill level for the module
    level = models.CharField(
        max_length=20,
        choices=SkillLevel.choices,
        # Set the default to the lowest tier: 'beginner'
        default=SkillLevel.BEGINNER,
        verbose_name="Module Skill Level",
        db_index=True  # Index for filtering by skill level
    )

    class Availability(models.TextChoices):
        AVAILABLE = 'AVAILABLE', 'Available'
        NOT_AVAILABLE = 'NOT_AVAILABLE', 'Not Available'

    availability = models.CharField(
        max_length=20,
        choices=Availability.choices,
        default=Availability.AVAILABLE,
        db_index=True  # Index for filtering available freelancers
    )

    # Computed properties for convenience / API use
    @property
    def completed_projects(self):
        """Return a queryset of this user's completed projects."""
        from Project.models import Project
        return Project.objects.filter(client=self.user, status=Project.ProjectStatus.COMPLETED)

    @property
    def portfolio(self):
        """Return a list of thumbnails (or Project objects) representing the user's portfolio.

        By default this will return the thumbnails for completed projects. If you need full
        Project objects, use `profile.completed_projects`.
        """
        return list(self.completed_projects.values_list('thumbnail', flat=True))

    @property
    def active_projects(self):
        """Return a queryset of this user's active/in-progress projects."""
        from Project.models import Project
        return Project.objects.filter(client=self.user, status=Project.ProjectStatus.IN_PROGRESS)

    @property
    def projects_posted(self):
        """Return the number of projects this user has posted (created_projects related_name)."""
        return self.user.created_projects.count()

    @property
    def average_rating(self):
        """Return the aggregated average rating calculated from Review records.

        If the `rating` field on Profile is already populated it will be returned as a
        convenience; otherwise the value is computed from Review.reviewee (reviews_received).
        """
        # Use cached rating if present
        if self.rating is not None:
            return float(self.rating)

        # Aggregate from Review model via the user's related name `reviews_received`
        agg = self.user.reviews_received.aggregate(avg=Avg('rating'))
        avg = agg.get('avg')
        return float(avg) if avg is not None else None

    class Meta:
        indexes = [
            models.Index(fields=['user', 'availability']),  # Common query: user's availability status
        ]

    def __str__(self):
        roles = ', '.join([role.name for role in self.user.roles.all()])
        return f"{self.user.username}'s Profile ({roles})"

class Payment(models.Model):
    PAYMENT_METHOD_CHOICES = [
        ('stripe', 'Stripe'),
        ('paypal', 'PayPal'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    project = models.ForeignKey('Project.Project', on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_date = models.DateTimeField(auto_now_add=True)
    transaction_id = models.CharField(max_length=255, db_index=True)  # Index for transaction lookups
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    class PaymentStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        HELD = 'HELD', 'Held (Escrow)'
        RELEASED = 'RELEASED', 'Released'
        REFUNDED = 'REFUNDED', 'Refunded'

    status = models.CharField(
        max_length=20, 
        choices=PaymentStatus.choices, 
        default=PaymentStatus.PENDING,
        db_index=True  # Index for payment status filtering
    )

    class Meta:
        indexes = [
            models.Index(fields=['user', 'status']),  # User payment history
            models.Index(fields=['project', 'status']),  # Project payment tracking
        ]

    def __str__(self):
        return f"Payment of {self.amount} for {self.project.title} by {self.user.username} via {self.get_payment_method_display()}"
class NotificationPreferences(models.Model):
    """Model to store user notification preferences."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notification_preferences'
    )
    
    # Email Notifications
    email_new_message = models.BooleanField(default=True)
    email_payment_received = models.BooleanField(default=True)
    email_proposal_submitted = models.BooleanField(default=True)
    email_system_updates = models.BooleanField(default=True)
    
    # Push Notifications
    push_notifications = models.BooleanField(default=True)
    
    # Marketing
    marketing_emails = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Notification Preferences for {self.user.username}"


class UserPreferences(models.Model):
    """Model to store user application preferences."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='preferences'
    )
    
    # Language & Region
    language = models.CharField(max_length=10, default='en')
    timezone = models.CharField(max_length=50, default='UTC')
    
    # Currency Preference
    preferred_currency = models.CharField(
        max_length=3, 
        default='USD',
        blank=True,
        null=True,
        help_text='ISO 4217 currency code (e.g., USD, EUR, GBP, ZAR)'
    )
    
    # Display Settings
    dark_mode = models.BooleanField(default=False)
    
    # Default View
    default_view = models.CharField(max_length=100, blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Preferences for {self.user.username}"


class FileAttachment(models.Model):
    """Model for storing user-uploaded files of various types."""
    
    CATEGORY_CHOICES = [
        ('profile', 'Profile'),
        ('portfolio', 'Portfolio'),
        ('project', 'Project'),
        ('proposal', 'Proposal'),
        ('deliverable', 'Deliverable'),
        ('certification', 'Certification'),
        ('contract', 'Contract'),
        ('other', 'Other'),
    ]
    
    FILE_TYPE_CHOICES = [
        ('image', 'Image'),
        ('video', 'Video'),
        ('document', 'Document'),
        ('code', 'Code'),
        ('archive', 'Archive'),
        ('audio', 'Audio'),
        ('design', 'Design'),
        ('spreadsheet', 'Spreadsheet'),
        ('presentation', 'Presentation'),
        ('other', 'Other'),
    ]
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='file_attachments'
    )
    file = models.FileField(upload_to='uploads/%Y/%m/%d/')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other')
    file_type = models.CharField(max_length=20, choices=FILE_TYPE_CHOICES, default='other')
    original_filename = models.CharField(max_length=255)
    file_size = models.IntegerField(help_text='File size in bytes')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    description = models.TextField(blank=True, null=True)
    
    # Optional: Link to specific entities
    project_id = models.IntegerField(blank=True, null=True, help_text='Related project ID')
    proposal_id = models.IntegerField(blank=True, null=True, help_text='Related proposal ID')
    
    class Meta:
        ordering = ['-uploaded_at']
        indexes = [
            models.Index(fields=['user', 'category']),
            models.Index(fields=['uploaded_at']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.original_filename} ({self.category})"
    
    def get_file_size_display(self):
        """Return human-readable file size."""
        size = self.file_size
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.2f} {unit}"
            size /= 1024.0
        return f"{size:.2f} TB"
