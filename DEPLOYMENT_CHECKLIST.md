# Deployment Checklist

Your Render service: **https://pipedrive-automation.onrender.com**

---

## ✅ Step 1: Commit Code

```bash
git add .
git commit -m "Salesforce sync production ready"
git push origin main
```

Render will auto-deploy when you push (if GitHub is connected).

---

## ✅ Step 2: Add Environment Variables to Render

**This is the critical step!** You need to copy ALL variables from your local `.env` file to Render.

### How to Add:

1. Go to [Render Dashboard](https://dashboard.render.com)
2. Click on **`pipedrive-automation`** service
3. Click **"Environment"** tab (left sidebar)
4. For each variable in your `.env` file:
   - Click **"Add Environment Variable"**
   - Enter the variable name (exactly as it appears in `.env`)
   - Enter the value
   - Click **"Save Changes"**

### Variables to Add (from your `.env`):

#### Pipedrive:
- `PIPEDRIVE_API_KEY`

#### Salesforce OAuth:
- `SALESFORCE_CONSUMER_KEY`
- `SALESFORCE_CONSUMER_SECRET`
- `SALESFORCE_REFRESH_TOKEN`
- `SALESFORCE_INSTANCE_URL`
- `SALESFORCE_DOMAIN`

#### Salesforce Config:
- `SALESFORCE_LOAN_OBJECT`
- `SALESFORCE_LOAN_OFFICER_FIELD`
- `SALESFORCE_PRIMARY_BORROWER_FIELD`
- `SALESFORCE_LOAN_OFFICER`

#### All Pipedrive Field Keys:
- `LOAN_AMOUNT_KEY`
- `BASE_LOAN_AMOUNT_KEY`
- `PROPERTY_ADDRESS_KEY`
- `LOAN_TYPE_KEY`
- `LOAN_PURPOSE_KEY`
- `OCCUPANCY_KEY`
- `PURCHASE_PRICE_KEY`
- `DOWN_PAYMENT_KEY`
- `DOWN_PAYMENT_PERCENT_KEY`
- `PI_PAYMENT_KEY`
- `SUPPLEMENTAL_PROPERTY_INSURANCE_KEY`
- `SELF_SOURCED_KEY`
- `BRANCH_PRICING_KEY`
- `COMPANY_LEAD_KEY`
- `LOAN_NUMBER_KEY`
- `COMMISSION_KEY`
- `COBORROWER_KEY`
- `BUYER_AGENT_KEY`
- `LISTING_AGENT_KEY`
- ... (add ALL field keys from your `.env`)

#### Salesforce ID Fields:
- `PIPEDRIVE_SALESFORCE_LOAN_ID_KEY`
- `PIPEDRIVE_SALESFORCE_CONTACT_ID_KEY`

#### Stage IDs:
- `APPLICATION_IN_STAGE_ID`
- `PREAPPROVED_STAGE_ID`
- `GETTING_THINGS_ROLLING_STAGE_ID`
- `IN_PROCESS_STAGE_ID`
- `CLEAR_TO_CLOSE_STAGE_ID`

#### Label IDs:
- `LABEL_APPLICATION_ID`
- `LABEL_PREAPPROVED_ID`
- ... (all label IDs)

#### Contact Type/Group:
- `CONTACT_TYPE_KEY`
- `CONTACT_GROUP_KEY`
- `CLIENT_CONTACT_TYPE_ID`
- `BUSINESS_CONTACT_TYPE_ID`
- `LEAD_GROUP_ID`
- `BORROWER_GROUP_ID`
- ... (all group IDs)

#### Occupancy IDs:
- `PRIMARY_OCCUPANCY_ID`
- `SECOND_HOME_OCCUPANCY_ID`
- `INVESTMENT_OCCUPANCY_ID`

**Tip**: Open your `.env` file and go through it line by line, adding each variable to Render.

---

## ✅ Step 3: Verify Service Started

1. Go to Render dashboard → Your service → **"Logs"** tab
2. Look for:
   - "✓ Successfully connected to Salesforce via OAuth refresh token"
   - No error messages
3. Test health endpoint:
   ```bash
   curl https://pipedrive-automation.onrender.com/health
   ```
   Should return: `{"status": "ok"}`

---

## ✅ Step 4: Test Manual Sync

```bash
curl -X POST https://pipedrive-automation.onrender.com/sync/poll?hours_back=1
```

**Check:**
- Response shows `"success": true`
- Render logs show sync activity
- A test deal appears in Pipedrive (if loans exist)

---

## ✅ Step 5: Run Initial Sync

```bash
curl -X POST https://pipedrive-automation.onrender.com/sync/initial?limit=1000
```

**Monitor:**
- Render logs for sync progress
- Pipedrive for new deals
- Check that Salesforce IDs are populated

---

## ✅ Step 6: Set Up Salesforce CDC (Optional)

If you want real-time sync:

1. Salesforce → Setup → Integrations → Change Data Capture
2. Enable for: `MtgPlanner_CRM__Transaction_Property__c`
3. Configure webhook: `https://pipedrive-automation.onrender.com/webhook/salesforce/cdc`

**Note**: If CDC setup is complex, you can use manual sync endpoints instead.

---

## ✅ Step 7: Monitor

- Check Render logs regularly
- Verify deals in Pipedrive
- Watch for any errors
- Test with a real Salesforce update

---

## 🚨 Common Issues

### "Service won't start"
- Check logs for missing environment variables
- Verify all variables are added to Render
- Check for typos in variable names

### "Salesforce connection failed"
- Verify OAuth credentials are correct
- Check `SALESFORCE_INSTANCE_URL` is correct
- Verify refresh token is valid

### "No loans syncing"
- Check Loan Officer filter matches exactly
- Verify loans exist in Salesforce
- Check Render logs for specific errors

---

## 📝 Quick Reference

**Your Service URL**: https://pipedrive-automation.onrender.com

**Endpoints:**
- Health: `GET /health`
- Manual Sync: `POST /sync/poll?hours_back=24`
- Initial Sync: `POST /sync/initial?limit=1000`
- CDC Webhook: `POST /webhook/salesforce/cdc`

**Render Dashboard**: https://dashboard.render.com

