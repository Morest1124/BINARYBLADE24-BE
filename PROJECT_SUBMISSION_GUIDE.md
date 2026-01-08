# Project Submission Feature - Usage Guide

## Overview

The Project Submission system allows freelancers to submit their completed work with secure file uploads, deadline validation, and automatic escrow integration.

## Features

### 1. **Secure File Upload**
- Supports any file type (ZIP, PDF, images, videos, documents, etc.)
- Maximum file size: 2GB per file
- Automatic filename sanitization to prevent security issues
- Files stored securely in Django with proper permissions

### 2. **Deadline & Grace Period**
- Real-time countdown timer
- 24-hour grace period after deadline
- Visual warnings when in grace period
- Automatic blocking after grace period expires

### 3. **Escrow Integration**
- Shows payment breakdown (20% platform, 80% freelancer)
- Automatic escrow status update on submission
- 5-day review period before auto-release
- Real-time escrow status tracking

### 4. **Security Features**
- Filename sanitization (removes dangerous characters)
- File size validation
- Empty file detection
- Permission checks (only assigned freelancer can submit)
- CSRF protection
- JWT authentication

---

## Frontend Implementation

### Basic Usage

```jsx
import ProjectSubmissionPage from './pages/ProjectSubmissionPage';

function FreelancerDashboard() {
  return (
    <ProjectSubmissionPage
      orderId={order.id}
      projectTitle={order.project_title}
      deadline={order.deadline} // ISO 8601 format
      escrowAmount={order.total_amount}
      onUploadSuccess={(result) => {
        console.log('Submission successful:', result);
        // Navigate to dashboard or show success message
        navigate('/dashboard');
      }}
      onNavigateBack={() => {
        navigate('/orders');
      }}
    />
  );
}
```

### Props

| Prop | Type | Required | Description |
|------|------|----------|-------------|
| `orderId` | number | Yes | Order ID to submit deliverables for |
| `projectTitle` | string | No | Project title to display |
| `deadline` | string | Yes | Submission deadline (ISO 8601) |
| `escrowAmount` | number | No | Total escrow amount (default: 0) |
| `onUploadSuccess` | function | No | Callback when submission succeeds |
| `onNavigateBack` | function | No | Callback for "Back" button |

### Example with React Router

```jsx
import { useParams, useNavigate } from 'react-router-dom';
import { useState, useEffect } from 'react';
import { getOrderDetails } from '../api';
import ProjectSubmissionPage from '../pages/ProjectSubmissionPage';

function SubmitWork() {
  const { orderId } = useParams();
  const navigate = useNavigate();
  const [order, setOrder] = useState(null);

  useEffect(() => {
    getOrderDetails(orderId).then(setOrder);
  }, [orderId]);

  if (!order) return <div>Loading...</div>;

  return (
    <ProjectSubmissionPage
      orderId={order.id}
      projectTitle={order.items[0]?.project?.title}
      deadline={order.items[0]?.project?.delivery_days}
      escrowAmount={order.total_amount}
      onUploadSuccess={() => {
        navigate('/dashboard/orders');
      }}
      onNavigateBack={() => {
        navigate(-1);
      }}
    />
  );
}
```

---

## Backend API

### Endpoint: Submit Deliverable

**URL:** `POST /api/orders/orders/{order_id}/submit_deliverable/`

**Authentication:** Required (JWT Bearer token)

**Content-Type:** `multipart/form-data`

**Request Body:**

```
file_0: <File>
file_1: <File>
file_2: <File>
...
delivery_note: "I've completed all the requirements. The source files are in the ZIP..."
order_id: 123
```

**Response (Success - 201):**

```json
{
  "status": "Deliverables submitted successfully",
  "order_id": 123,
  "order_number": "ORD-20260108-ABC123",
  "deliverables": [
    {
      "id": 1,
      "filename": "project_files.zip",
      "size": 52428800,
      "submitted_at": "2026-01-08T17:30:00Z"
    },
    {
      "id": 2,
      "filename": "documentation.pdf",
      "size": 1048576,
      "submitted_at": "2026-01-08T17:30:01Z"
    }
  ],
  "total_files": 2,
  "escrow_status": "SHIPPING",
  "review_period_days": 5,
  "escrow_amount": 1000.0,
  "platform_fee": 200.0,
  "freelancer_amount": 800.0
}
```

**Response (Error - 400/403):**

```json
{
  "error": "Only the assigned freelancer can submit deliverables"
}
```

**Possible Errors:**

- `403 Forbidden` - Not the assigned freelancer
- `400 Bad Request` - Order not in IN_PROGRESS status
- `400 Bad Request` - Grace period expired
- `400 Bad Request` - No files uploaded
- `400 Bad Request` - File exceeds 2GB limit
- `400 Bad Request` - Delivery note missing

---

## Security Measures

### 1. File Sanitization

```python
# Filename sanitization regex
safe_filename = re.sub(r'[^a-zA-Z0-9.-_]', '_', filename)

# Examples:
# "my file.pdf" → "my_file.pdf"
# "../../../etc/passwd" → "______etc_passwd"
# "script<>.exe" → "script__.exe"
```

### 2. File Validation

- **Size Check:** Files larger than 2GB are rejected
- **Empty File Check:** Zero-byte files are rejected
- **Type Check:** All file types accepted (flexibility for freelancers)

### 3. Permission Checks

- Only the assigned freelancer can submit
- Order must be in `IN_PROGRESS` status
- Deadline and grace period enforced

### 4. Storage Security

- Files stored in `MEDIA_ROOT/deliverables/YYYY/MM/DD/`
- Django FileField handles secure upload
- Proper file permissions set by Django

---

## Deadline & Grace Period Logic

### Timeline Example:

```
Deadline: 2026-01-10 12:00 PM
├─ Before Deadline: ✅ Can submit (green timer)
├─ Deadline Passed: ⚠️  Grace period starts (orange timer)
│  └─ Grace Period: 24 hours
├─ Grace Deadline: 2026-01-11 12:00 PM
└─ After Grace: ❌ Cannot submit (red timer, blocked)
```

### Frontend Timer States:

1. **Normal (Green):** `"2d 14h 30m 45s"` - Before deadline
2. **Grace Period (Orange):** `"GRACE PERIOD: 23h 30m 15s"` - After deadline
3. **Expired (Red):** `"GRACE PERIOD EXPIRED"` - After grace period

---

## Escrow Payment Flow

```
Order Created ($1,000)
    ↓
Payment Made
    ↓
Escrow Created (Status: PENDING)
    ↓
Escrow Funded (Status: FUNDED)
    ↓
Work Delivered (Status: SHIPPING) ← **This step happens on submission**
    ↓
Client Reviews (5 days)
    ↓
Client Approves OR Auto-release after 5 days
    ↓
Funds Disbursed (Status: DISBURSED)
    ├─ Platform: $200 (20%)
    └─ Freelancer: $800 (80%)
```

---

## Testing

### Test Case 1: Successful Submission

```javascript
// Setup
const orderId = 1;
const deadline = new Date(Date.now() + 24 * 60 * 60 * 1000); // Tomorrow

// Test
<ProjectSubmissionPage
  orderId={orderId}
  deadline={deadline.toISOString()}
  escrowAmount={1000}
/>

// Expected:
// - Timer shows remaining time
// - Upload area is enabled
// - Can upload files
// - Can submit successfully
```

### Test Case 2: Grace Period

```javascript
// Setup
const orderId = 1;
const deadline = new Date(Date.now() - 2 * 60 * 60 * 1000); // 2 hours ago

// Expected:
// - Orange warning banner
// - Timer shows "GRACE PERIOD: XXh XXm"
// - Can still submit
```

### Test Case 3: Expired Deadline

```javascript
// Setup
const deadline = new Date(Date.now() - 25 * 60 * 60 * 1000); // 25 hours ago

// Expected:
// - Red error banner
// - Timer shows "GRACE PERIOD EXPIRED"
// - Submit button disabled
// - Error message displayed
```

---

## Customization

### Change Grace Period

**Backend** (`Order/views.py`):
```python
grace_period = timedelta(hours=24)  # Change to desired hours
```

**Frontend** (`ProjectSubmissionPage.jsx`):
```javascript
const GRACE_PERIOD_HOURS = 24; // Match backend
```

### Change Review Period

**Backend** (escrow logic):
```python
REVIEW_PERIOD_DAYS = 5  # Change as needed
```

**Frontend**:
```javascript
const REVIEW_PERIOD_DAYS = 5; // Match backend
```

### Change File Size Limit

**Backend** (`Order/views.py`):
```python
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB
```

**Frontend** (`ProjectSubmissionPage.jsx`):
```javascript
const MAX_FILE_SIZE_GB = 2;
const MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_GB * 1024 * 1024 * 1024;
```

---

## Troubleshooting

### Issue: Files not uploading

**Solution:** Check file size limit and network connection

```javascript
// Add console logging
console.log('File size:', file.size);
console.log('Max allowed:', MAX_FILE_SIZE_BYTES);
```

### Issue: "Grace period expired" error

**Solution:** Verify deadline is in the future

```javascript
const deadline = new Date(order.delivery_days);
const now = new Date();
console.log('Deadline:', deadline);
console.log('Now:', now);
console.log('Time remaining (ms):', deadline - now);
```

### Issue: Permission denied

**Solution:** Ensure user is the assigned freelancer

```javascript
// Check order details
console.log('Order freelancer ID:', order.items[0].freelancer.id);
console.log('Current user ID:', currentUser.id);
```

---

## Best Practices

1. **Always provide deadline:** Set realistic deadlines with buffer time
2. **Inform freelancers:** Send notification when deadline is approaching
3. **Clear delivery notes:** Encourage detailed delivery notes
4. **File organization:** Ask freelancers to zip folders for organization
5. **Test uploads:** Test with various file types and sizes
6. **Monitor storage:** Track media storage usage as files accumulate
7. **Backup strategy:** Implement regular backups of deliverables folder

---

## File Storage Structure

```
MEDIA_ROOT/
└── deliverables/
    └── 2026/
        └── 01/
            └── 08/
                ├── project_files_abc123.zip
                ├── documentation_def456.pdf
                └── screenshots_ghi789.png
```

Files are automatically organized by date (YYYY/MM/DD) by Django's FileField.

---

## Summary

✅ **Secure file uploads** - Sanitized filenames, size validation  
✅ **Deadline enforcement** - 24-hour grace period  
✅ **Escrow integration**  - Automatic status updates  
✅ **All file types** - Maximum flexibility  
✅ **Premium UI** - Matches site theme  
✅ **Real-time feedback** - Progress tracking, errors, success states
