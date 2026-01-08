# Escrow API Documentation

## Overview

This API provides complete escrow payment management for the BinaryBlade24 freelancing platform. It implements a **three-way payment split** where:
- **Client** pays the full amount
- **Platform** receives 20% commission
- **Freelancer** receives 80% payout

All escrow transactions are managed through Escrow.com API.

---

## Authentication

All endpoints (except webhooks) require JWT authentication:

```http
Authorization: Bearer <your_jwt_token>
```

---

## Endpoints

### 1. List Escrow Transactions

Get all escrow transactions where the authenticated user is involved (as client or freelancer).

**Endpoint:** `GET /api/escrow/transactions/`

**Response:**
```json
[
  {
    "id": 1,
    "order": 5,
    "order_number": "ORD-20260108-A1B2C3D4",
    "project_title": "Build a Website",
    "client": 2,
    "client_email": "client@example.com",
    "client_name": "John Doe",
    "freelancer": 3,
    "freelancer_email": "freelancer@example.com",
    "freelancer_name": "Jane Smith",
    "escrow_id": "12345ABC",
    "total_amount": "1000.00",
    "platform_fee": "200.00",
    "freelancer_amount": "800.00",
    "platform_fee_percentage_display": "20.00",
    "currency": "USD",
    "status": "FUNDED",
    "status_display": "Funded - Payment Received",
    "created_at": "2026-01-08T10:30:00Z",
    "updated_at": "2026-01-08T11:00:00Z",
    "funded_at": "2026-01-08T11:00:00Z",
    "disbursed_at": null,
    "notes": ""
  }
]
```

---

### 2. Get Escrow Transaction Details

Get details of a specific escrow transaction.

**Endpoint:** `GET /api/escrow/transactions/<id>/`

**Response:** Same as list response (single object)

---

### 3. Get Escrow Summary

Get summary statistics for the authenticated user's escrow transactions.

**Endpoint:** `GET /api/escrow/transactions/summary/`

**Response:**
```json
{
  "total_escrows": 10,
  "total_amount": "5000.00",
  "platform_fees_earned": "1000.00",
  "freelancer_payouts": "4000.00",
  "pending_count": 2,
  "funded_count": 3,
  "disbursed_count": 4,
  "refunded_count": 1,
  "as_freelancer": {
    "total_earned": "3200.00",
    "completed_jobs": 4
  },
  "as_client": {
    "total_spent": "1800.00",
    "completed_orders": 2
  }
}
```

---

### 4. Create Escrow Transaction

Create an escrow transaction for a paid order.

**Endpoint:** `POST /api/escrow/create/`

**Request Body:**
```json
{
  "order_id": 5,
  "currency": "USD",
  "inspection_period": 259200
}
```

**Parameters:**
- `order_id` (required): ID of the paid order
- `currency` (optional): Currency code (default: USD)
- `inspection_period` (optional): Time in seconds for client to inspect work (default: 259200 = 3 days)

**Response:**
```json
{
  "escrow_transaction": {
    "id": 1,
    "order": 5,
    "escrow_id": "12345ABC",
    "total_amount": "1000.00",
    "platform_fee": "200.00",
    "freelancer_amount": "800.00",
    "status": "PENDING",
    ...
  },
  "payment_url": "https://www.escrow-sandbox.com/checkout/12345ABC",
  "message": "Escrow transaction created successfully"
}
```

**Errors:**
- `400` - Order not found, already has escrow, or not in PAID status
- `403` - Only the order client can create escrow
- `500` - Escrow API error

---

### 5. Release Escrow to Freelancer

Client approves the work and releases payment to freelancer.

**Endpoint:** `POST /api/escrow/<id>/release/`

**Request Body:**
```json
{
  "confirm": true,
  "feedback": "Great work!",
  "rating": 5
}
```

**Parameters:**
- `confirm` (required): Must be `true` to confirm release
- `feedback` (optional): Feedback for freelancer
- `rating` (optional): Rating from 1-5 stars

**Response:**
```json
{
  "escrow_transaction": {
    "status": "DISBURSED",
    "disbursed_at": "2026-01-08T12:00:00Z",
    ...
  },
  "message": "Payment released to freelancer successfully",
  "freelancer_received": 800.00
}
```

**Errors:**
- `403` - Only the client can release escrow
- `400` - Escrow cannot be released in current status
- `500` - Escrow API error

---

### 6. Refund Escrow to Client

Cancel the order and refund money to client.

**Endpoint:** `POST /api/escrow/<id>/refund/`

**Request Body:**
```json
{
  "reason": "Client cancelled the project",
  "confirm": true
}
```

**Parameters:**
- `reason` (required): Reason for refund
- `confirm` (required): Must be `true` to confirm refund

**Response:**
```json
{
  "escrow_transaction": {
    "status": "REFUNDED",
    ...
  },
  "message": "Refund initiated successfully",
  "refund_amount": 1000.00
}
```

**Errors:**
- `403` - Only client or freelancer can request refund
- `400` - Cannot refund already disbursed escrow
- `500` - Escrow API error

---

### 7. Escrow Webhook (No Auth Required)

Handle status updates from Escrow.com API.

**Endpoint:** `POST /api/escrow/webhook/`

**Headers:**
```
X-Escrow-Signature: <webhook_signature>
```

**Request Body:**
```json
{
  "event_type": "transaction.funded",
  "transaction": {
    "id": "12345ABC",
    ...
  }
}
```

**Supported Events:**
- `transaction.funded` - Payment received
- `transaction.shipped` - Work delivered
- `transaction.disbursed` - Funds released
- `transaction.cancelled` - Transaction cancelled
- `transaction.refunded` - Funds refunded

**Response:**
```json
{
  "status": "received"
}
```

---

## Payment Flow

### Complete Order-to-Payment Flow:

1. **Client creates order** → Order status: `PENDING`

2. **Client pays** → Order status: `PAID`

3. **Create escrow transaction**
   ```http
   POST /api/escrow/create/
   {
     "order_id": 5
   }
   ```
   - Escrow status: `PENDING`
   - Order status: `IN_PROGRESS`
   - Platform receives payment URL for client

4. **Client pays via Escrow.com** → Escrow status: `FUNDED` (via webhook)

5. **Freelancer delivers work** → Escrow status: `SHIPPING`

6. **Client approves and releases payment**
   ```http
   POST /api/escrow/1/release/
   {
     "confirm": true
   }
   ```
   - Escrow status: `DISBURSED`
   - Order status: `COMPLETED`
   - Freelancer receives 80% ($800)
   - Platform receives 20% ($200)

### Cancellation Flow:

At any point before disbursement:

```http
POST /api/escrow/1/refund/
{
  "reason": "Project cancelled",
  "confirm": true
}
```
- Escrow status: `REFUNDED`
- Order status: `REFUNDED`
- Client receives full refund

---

## Fee Calculation

The platform automatically calculates fees:

```
Total Amount: $1,000
├── Platform Fee (20%): $200
└── Freelancer Payout (80%): $800
```

These percentages are configurable in `settings.py`:
```python
PLATFORM_FEE_PERCENTAGE = Decimal('0.20')
FREELANCER_PAYOUT_PERCENTAGE = Decimal('0.80')
```

---

## Status Codes

### Escrow Transaction Status:

- `PENDING` - Created, awaiting payment
- `FUNDED` - Payment received, held in escrow
- `SHIPPING` - Work delivered, awaiting approval
- `DISBURSED` - Funds released to freelancer and platform
- `CANCELLED` - Transaction cancelled
- `REFUNDED` - Funds refunded to client
- `DISPUTED` - Under dispute

---

## Error Handling

All endpoints return standard HTTP status codes:

- `200 OK` - Success
- `201 Created` - Resource created successfully
- `400 Bad Request` - Invalid request data
- `401 Unauthorized` - Invalid/missing authentication
- `403 Forbidden` - Insufficient permissions
- `404 Not Found` - Resource not found
- `500 Internal Server Error` - Server/API error

Error response format:
```json
{
  "error": "Detailed error message"
}
```

---

## Testing

### Test Credentials (Sandbox)

Add to your `.env` file:
```bash
ESCROW_API_URL=https://api.escrow-sandbox.com/2017-09-01
ESCROW_API_EMAIL=test@example.com
ESCROW_API_KEY=test_api_key_123456789
ESCROW_WEBHOOK_SECRET=test_webhook_secret
```

### Sample Test Flow

```bash
# 1. Create an order (via Order API)
POST /api/orders/

# 2. Mark order as PAID
PATCH /api/orders/1/

# 3. Create escrow
POST /api/escrow/create/
{
  "order_id": 1
}

# 4. View escrow details
GET /api/escrow/transactions/1/

# 5. Release payment
POST /api/escrow/1/release/
{
  "confirm": true,
  "rating": 5
}
```

---

## Support

For issues or questions:
- Check Django logs: `binaryblade24/debug.log`
- Review webhook logs in Django admin: `/admin/escrow/escrowwebhooklog/`
- Contact platform support
