"""
Escrow.com API Client for Three-Way Payment System
Handles escrow transactions with platform fee (20%) and freelancer payout (80%)
"""

import requests
import hashlib
import hmac
import json
import logging
from decimal import Decimal
from typing import Dict, Optional, Tuple
from django.conf import settings

logger = logging.getLogger(__name__)


class EscrowAPIException(Exception):
    """Custom exception for Escrow API errors"""
    pass


class EscrowClient:
    """
    Client for interacting with Escrow.com API
    Implements three-way payment split: Client → Platform (20%) + Freelancer (80%)
    """
    
    def __init__(self):
        self.base_url = getattr(settings, 'ESCROW_API_URL', 'https://api.escrow-sandbox.com/2017-09-01')
        self.email = getattr(settings, 'ESCROW_API_EMAIL', '')
        self.api_key = getattr(settings, 'ESCROW_API_KEY', '')
        self.webhook_secret = getattr(settings, 'ESCROW_WEBHOOK_SECRET', '')
        
        # Platform fee configuration
        self.platform_fee_percentage = getattr(
            settings, 
            'PLATFORM_FEE_PERCENTAGE', 
            Decimal('0.20')
        )
        self.freelancer_percentage = getattr(
            settings, 
            'FREELANCER_PAYOUT_PERCENTAGE', 
            Decimal('0.80')
        )
        
        if not self.email or not self.api_key:
            logger.warning("Escrow API credentials not configured. Set ESCROW_API_EMAIL and ESCROW_API_KEY in settings.")
    
    def _get_auth(self) -> Tuple[str, str]:
        """Get authentication tuple for API requests"""
        return (self.email, self.api_key)
    
    def _make_request(
        self, 
        method: str, 
        endpoint: str, 
        data: Optional[Dict] = None
    ) -> Dict:
        """
        Make HTTP request to Escrow API
        
        Args:
            method: HTTP method (GET, POST, PATCH, etc.)
            endpoint: API endpoint (e.g., '/transaction')
            data: Request payload
            
        Returns:
            API response as dictionary
            
        Raises:
            EscrowAPIException: If API request fails
        """
        url = f"{self.base_url}{endpoint}"
        
        try:
            response = requests.request(
                method=method,
                url=url,
                auth=self._get_auth(),
                json=data,
                headers={'Content-Type': 'application/json'},
                timeout=30
            )
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.HTTPError as e:
            error_msg = f"Escrow API HTTP Error: {e}"
            try:
                error_detail = response.json()
                error_msg += f" - {error_detail}"
            except:
                pass
            logger.error(error_msg)
            raise EscrowAPIException(error_msg)
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Escrow API Request Failed: {e}"
            logger.error(error_msg)
            raise EscrowAPIException(error_msg)
    
    def calculate_fees(self, total_amount: Decimal) -> Dict[str, Decimal]:
        """
        Calculate platform fee and freelancer payout
        
        Args:
            total_amount: Total order amount
            
        Returns:
            Dictionary with platform_fee and freelancer_amount
        """
        total_amount = Decimal(str(total_amount))
        platform_fee = (total_amount * self.platform_fee_percentage).quantize(Decimal('0.01'))
        freelancer_amount = (total_amount * self.freelancer_percentage).quantize(Decimal('0.01'))
        
        return {
            'total_amount': total_amount,
            'platform_fee': platform_fee,
            'freelancer_amount': freelancer_amount
        }
    
    def create_transaction(
        self,
        order_id: str,
        client_email: str,
        freelancer_email: str,
        total_amount: Decimal,
        project_title: str,
        currency: str = 'usd',
        inspection_period: int = 259200  # 3 days in seconds
    ) -> Dict:
        """
        Create a three-way escrow transaction
        
        Args:
            order_id: Internal order ID for reference
            client_email: Client's email (buyer)
            freelancer_email: Freelancer's email (seller)
            total_amount: Total order amount
            project_title: Project/order title
            currency: Currency code (default: 'usd')
            inspection_period: Time for client to inspect work (default: 3 days)
            
        Returns:
            Escrow API response with transaction ID
        """
        fees = self.calculate_fees(total_amount)
        
        payload = {
            "parties": [
                {
                    "role": "buyer",
                    "customer": client_email
                },
                {
                    "role": "seller",
                    "customer": freelancer_email
                },
                {
                    "role": "broker",
                    "customer": "me"  # Platform account
                }
            ],
            "currency": currency.lower(),
            "description": f"Order #{order_id}: {project_title}",
            "items": [
                # Freelancer payment item (80%)
                {
                    "title": project_title,
                    "description": "Freelance Services",
                    "type": "milestone",
                    "inspection_period": inspection_period,
                    "quantity": 1,
                    "schedule": [
                        {
                            "amount": float(fees['freelancer_amount']),
                            "payer_customer": client_email,
                            "beneficiary_customer": freelancer_email
                        }
                    ]
                },
                # Platform service fee (20%)
                {
                    "title": "Platform Service Fee",
                    "description": f"BinaryBlade24 Platform Fee ({int(self.platform_fee_percentage * 100)}%)",
                    "type": "broker_fee",
                    "quantity": 1,
                    "schedule": [
                        {
                            "amount": float(fees['platform_fee']),
                            "payer_customer": client_email,
                            "beneficiary_customer": "me"
                        }
                    ]
                }
            ]
        }
        
        logger.info(f"Creating escrow transaction for order {order_id}: ${total_amount} (Platform: ${fees['platform_fee']}, Freelancer: ${fees['freelancer_amount']})")
        
        try:
            response = self._make_request('POST', '/transaction', data=payload)
            logger.info(f"Escrow transaction created successfully: {response.get('id')}")
            return response
        except EscrowAPIException as e:
            logger.error(f"Failed to create escrow transaction for order {order_id}: {e}")
            raise
    
    def get_transaction(self, escrow_transaction_id: str) -> Dict:
        """
        Get transaction details
        
        Args:
            escrow_transaction_id: Escrow API transaction ID
            
        Returns:
            Transaction details
        """
        endpoint = f"/transaction/{escrow_transaction_id}"
        return self._make_request('GET', endpoint)
    
    def update_transaction_action(
        self,
        escrow_transaction_id: str,
        action: str,
        extra_data: Optional[Dict] = None
    ) -> Dict:
        """
        Update transaction with an action
        
        Args:
            escrow_transaction_id: Escrow API transaction ID
            action: Action to perform (agree, ship, receive, accept, reject, etc.)
            extra_data: Additional data for specific actions
            
        Returns:
            Updated transaction details
        """
        endpoint = f"/transaction/{escrow_transaction_id}"
        
        payload = {"action": action}
        if extra_data:
            payload.update(extra_data)
        
        logger.info(f"Updating escrow transaction {escrow_transaction_id} with action: {action}")
        return self._make_request('PATCH', endpoint, data=payload)
    
    def agree_to_transaction(self, escrow_transaction_id: str, party: str = 'buyer') -> Dict:
        """
        Party agrees to the transaction terms
        
        Args:
            escrow_transaction_id: Escrow transaction ID
            party: 'buyer' or 'seller'
        """
        return self.update_transaction_action(escrow_transaction_id, 'agree')
    
    def mark_as_shipped(
        self,
        escrow_transaction_id: str,
        carrier: Optional[str] = None,
        tracking_id: Optional[str] = None
    ) -> Dict:
        """
        Mark transaction as shipped (for physical goods)
        For digital services, this can represent work delivery
        
        Args:
            escrow_transaction_id: Escrow transaction ID
            carrier: Shipping carrier (optional)
            tracking_id: Tracking number (optional)
        """
        extra_data = {}
        if carrier and tracking_id:
            extra_data = {
                "shipping_information": {
                    "tracking_information": {
                        "carrier": carrier,
                        "tracking_id": tracking_id
                    }
                }
            }
        
        return self.update_transaction_action(escrow_transaction_id, 'ship', extra_data)
    
    def accept_transaction(self, escrow_transaction_id: str) -> Dict:
        """
        Client accepts the work and releases payment
        This triggers fund disbursement to freelancer and platform
        
        Args:
            escrow_transaction_id: Escrow transaction ID
        """
        logger.info(f"Client accepting transaction {escrow_transaction_id} - funds will be released")
        return self.update_transaction_action(escrow_transaction_id, 'accept')
    
    def reject_transaction(self, escrow_transaction_id: str, reason: str = '') -> Dict:
        """
        Client rejects the work and requests revision
        
        Args:
            escrow_transaction_id: Escrow transaction ID
            reason: Reason for rejection
        """
        extra_data = {'rejection_reason': reason} if reason else {}
        logger.warning(f"Client rejecting transaction {escrow_transaction_id}: {reason}")
        return self.update_transaction_action(escrow_transaction_id, 'reject', extra_data)
    
    def cancel_transaction(self, escrow_transaction_id: str) -> Dict:
        """
        Cancel transaction and refund to client
        
        Args:
            escrow_transaction_id: Escrow transaction ID
        """
        logger.info(f"Cancelling transaction {escrow_transaction_id} - refund initiated")
        return self.update_transaction_action(escrow_transaction_id, 'cancel')
    
    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """
        Verify webhook signature from Escrow.com
        
        Args:
            payload: Raw webhook payload
            signature: Signature from webhook header
            
        Returns:
            True if signature is valid
        """
        if not self.webhook_secret:
            logger.warning("Webhook secret not configured - cannot verify signature")
            return False
        
        expected_signature = hmac.new(
            key=self.webhook_secret.encode('utf-8'),
            msg=payload,
            digestmod=hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(expected_signature, signature)
