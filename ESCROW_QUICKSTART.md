# Quick Start Guide - Escrow Integration

## ⚡ Quick Setup (5 Minutes)

### 1. Apply Database Migrations
```bash
cd binaryblade24
python manage.py migrate escrow
```

### 2. Add Escrow Credentials to .env

Open your `.env` file and add these lines (replace with your real credentials):

```bash
# Escrow API Configuration
ESCROW_API_URL=https://api.escrow-sandbox.com/2017-09-01
ESCROW_API_EMAIL=your-escrow-email@example.com
ESCROW_API_KEY=your_actual_api_key_here
ESCROW_WEBHOOK_SECRET=your_webhook_secret_here

# Platform Fees (already configured, but you can adjust)
PLATFORM_FEE_PERCENTAGE=0.20
FREELANCER_PAYOUT_PERCENTAGE=0.80
```

### 3. Test the API

Start your server:
```bash
python manage.py runserver
```

Test escrow creation (requires a paid order):
```bash
curl -X POST http://localhost:8000/api/escrow/create/ \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"order_id": 1}'
```

---

## 📋 Key Endpoints

| Action | Method | Endpoint |
|--------|--------|----------|
| List escrows | GET | `/api/escrow/transactions/` |
| Get details | GET | `/api/escrow/transactions/<id>/` |
| Get summary | GET | `/api/escrow/transactions/summary/` |
| Create escrow | POST | `/api/escrow/create/` |
| Release payment | POST | `/api/escrow/<id>/release/` |
| Refund | POST | `/api/escrow/<id>/refund/` |
| Webhook | POST | `/api/escrow/webhook/` |

---

## 💰 How Payment Split Works

**Example Order: $1,000**
```
When order is paid:
├── Create escrow transaction
├── Platform receives: $200 (20%)
└── Freelancer receives: $800 (80%)
```

**Automatic Process:**
1. Client pays order
2. Call: `POST /api/escrow/create/` with order_id
3. Escrow holds funds
4. Freelancer delivers work
5. Client approves: `POST /api/escrow/<id>/release/`
6. Funds automatically distributed (80% to freelancer, 20% to platform)

---

## 🔐 Getting Escrow.com Credentials

### Sandbox (Testing):
1. Go to: https://sandbox.escrow.com
2. Create developer account
3. Navigate to API settings
4. Copy API Email and API Key
5. Generate webhook secret

### Production:
1. Go to: https://www.escrow.com/developer
2. Apply for API access
3. Get production credentials
4. Update `.env` with production URL and keys

---

## 🧪 Quick Test Flow

### Test Complete Payment Flow:

```python
# 1. Create a paid order (via your Order API)
order = Order.objects.create(
    client=client_user,
    status='PAID',
    total_amount=1000
)

# 2. Create escrow transaction
POST /api/escrow/create/
{
    "order_id": order.id
}

# Response includes payment URL for client

# 3. After work is delivered, release payment
POST /api/escrow/1/release/
{
    "confirm": true,
    "rating": 5,
    "feedback": "Great work!"
}

# Result: Freelancer gets $800, Platform gets $200
```

---

## 📊 View in Admin

Access Django admin to view transactions:
```
http://localhost:8000/admin/escrow/escrowtransaction/
http://localhost:8000/admin/escrow/escrowwebhooklog/
```

Filter by:
- Status (PENDING, FUNDED, DISBURSED, etc.)
- Client or Freelancer
- Date range
- Escrow ID

---

## 🚨 Common Issues

### Issue: "Escrow API credentials not configured"
**Solution**: Add `ESCROW_API_EMAIL` and `ESCROW_API_KEY` to `.env`

### Issue: "Order must be in PAID status"
**Solution**: Update order status to PAID before creating escrow

### Issue: "Escrow transaction already exists"
**Solution**: Each order can only have one escrow transaction

### Issue: Webhook signature invalid
**Solution**: Verify `ESCROW_WEBHOOK_SECRET` matches Escrow.com settings

---

## 📖 Full Documentation

- **API Reference**: See [ESCROW_API.md](file:///c:/Users/mores/Downloads/FREELANING/BINARYBLADE24-BE/ESCROW_API.md)
- **Implementation Details**: See [walkthrough.md](file:///C:/Users/mores/.gemini/antigravity/brain/5f754f5a-8885-48de-9bce-227c052bb294/walkthrough.md)
- **Environment Template**: See [.env.example](file:///c:/Users/mores/Downloads/FREELANING/BINARYBLADE24-BE/.env.example)

---

## ✅ Checklist

- [ ] Migrations applied (`python manage.py migrate escrow`)
- [ ] `.env` updated with Escrow credentials
- [ ] Server running without errors
- [ ] Tested creating escrow for a paid order
- [ ] Checked admin interface
- [ ] Configured webhook URL in Escrow.com dashboard
- [ ] Tested payment release flow
- [ ] Tested refund flow

---

## 🎯 Next Steps

1. **Testing**: Test all endpoints in sandbox mode
2. **Production**: Get production credentials from Escrow.com
3. **Webhook**: Configure webhook URL: `https://your-domain.com/api/escrow/webhook/`
4. **Monitor**: Check webhook logs regularly in admin
5. **Deploy**: Deploy to production with production credentials

---

## 💡 Tips

- Always test in **sandbox mode** first
- Monitor webhook logs for debugging
- Platform fee percentage is configurable in settings
- Escrow transactions are **immutable** for audit trails
- All sensitive data is stored in `.env` (never commit to git!)
