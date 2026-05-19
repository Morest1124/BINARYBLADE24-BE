import random
import string
from django.utils import timezone
from datetime import timedelta
from django.core.mail import send_mail
from django.conf import settings
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from .models import OTPCode


def generate_otp(length=6):
    """Generate a random numeric OTP code."""
    return ''.join(random.choices(string.digits, k=length))


class SendOTPView(APIView):
    """
    Sends a 6-digit OTP to the user's email address for verification.
    POST /api/auth/send-otp/
    Body: { "type": "email" }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        otp_type = request.data.get('type', 'email')

        if otp_type not in ['email', 'sms']:
            return Response({'detail': 'Invalid type. Must be "email" or "sms".'}, status=status.HTTP_400_BAD_REQUEST)

        user = request.user

        # Rate limiting: prevent spamming — check if an OTP was sent in the last 60 seconds
        recent_otp = OTPCode.objects.filter(
            user=user,
            otp_type=otp_type,
            is_used=False,
            created_at__gte=timezone.now() - timedelta(seconds=60)
        ).exists()

        if recent_otp:
            return Response(
                {'detail': 'Please wait 60 seconds before requesting a new code.'},
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        # Invalidate any previous unused OTPs for this user/type
        OTPCode.objects.filter(user=user, otp_type=otp_type, is_used=False).update(is_used=True)

        # Create new OTP
        code = generate_otp()
        expires_at = timezone.now() + timedelta(minutes=10)
        OTPCode.objects.create(user=user, code=code, otp_type=otp_type, expires_at=expires_at)

        if otp_type == 'email':
            if not user.email:
                return Response({'detail': 'No email address on your account.'}, status=status.HTTP_400_BAD_REQUEST)

            try:
                send_mail(
                    subject='BinaryBlade24 — Your Verification Code',
                    message=(
                        f'Hi {user.first_name or user.username},\n\n'
                        f'Your email verification code is:\n\n'
                        f'  {code}\n\n'
                        f'This code expires in 10 minutes. Do not share it with anyone.\n\n'
                        f'— The BinaryBlade24 Team'
                    ),
                    html_message=(
                        f'<div style="font-family:Arial,sans-serif;max-width:480px;margin:0 auto;padding:32px;background:#f8fafc;border-radius:12px;">'
                        f'  <h2 style="color:#1e293b;">Email Verification</h2>'
                        f'  <p style="color:#475569;">Hi <strong>{user.first_name or user.username}</strong>,</p>'
                        f'  <p style="color:#475569;">Your verification code is:</p>'
                        f'  <div style="font-size:40px;font-weight:bold;letter-spacing:12px;color:#25B9D3;text-align:center;padding:20px;background:white;border-radius:8px;border:2px solid #25B9D3;margin:20px 0;">{code}</div>'
                        f'  <p style="color:#94a3b8;font-size:13px;">This code expires in <strong>10 minutes</strong>. Do not share it with anyone.</p>'
                        f'  <hr style="border:none;border-top:1px solid #e2e8f0;margin:20px 0;">'
                        f'  <p style="color:#94a3b8;font-size:12px;">— The BinaryBlade24 Team</p>'
                        f'</div>'
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user.email],
                    fail_silently=False,
                )
            except Exception as e:
                return Response(
                    {'detail': f'Failed to send email: {str(e)}'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

            return Response({'detail': f'Verification code sent to {user.email}.'})

        # SMS placeholder (not implemented yet)
        return Response({'detail': 'SMS verification is not yet configured.'}, status=status.HTTP_501_NOT_IMPLEMENTED)


class VerifyOTPView(APIView):
    """
    Verifies a submitted OTP code.
    POST /api/auth/verify-otp/
    Body: { "type": "email", "code": "123456" }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        otp_type = request.data.get('type', 'email')
        submitted_code = request.data.get('code', '').strip()

        if not submitted_code:
            return Response({'detail': 'Code is required.'}, status=status.HTTP_400_BAD_REQUEST)

        user = request.user

        # Find the latest valid OTP for this user and type
        otp = OTPCode.objects.filter(
            user=user,
            otp_type=otp_type,
            is_used=False,
            expires_at__gt=timezone.now()
        ).order_by('-created_at').first()

        if not otp:
            return Response(
                {'detail': 'No valid code found. Please request a new one.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if otp.code != submitted_code:
            return Response({'detail': 'Incorrect code. Please try again.'}, status=status.HTTP_400_BAD_REQUEST)

        # Mark OTP as used
        otp.is_used = True
        otp.save()

        # Mark user as verified
        if otp_type == 'email':
            user.is_email_verified = True
        elif otp_type == 'sms':
            user.is_phone_verified = True
        user.save()

        return Response({'detail': 'Verification successful!', 'verified': True})


class VerificationStatusView(APIView):
    """Returns the current email and phone verification status for the user."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({
            'is_email_verified': request.user.is_email_verified,
            'is_phone_verified': request.user.is_phone_verified,
        })
