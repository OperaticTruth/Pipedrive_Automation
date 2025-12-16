# Render Deployment Guide

Your Render service: **https://pipedrive-automation.onrender.com**

---

## Step 1: Commit and Push to GitHub

1. Make sure all your changes are committed:
   ```bash
   git add .
   git commit -m "Salesforce sync production ready"
   git push origin main
   ```

2. **Render will auto-deploy** when you push (if GitHub is connected)

---

## Step 2: Update Environment Variables in Render

**This is the most important step!** You need to add ALL your `.env` variables to Render.

### How to Add Environment Variables:

1. Go to [Render Dashboard](https://dashboard.render.com)
2. Click on your **`pipedrive-automation`** service
3. Go to **"Environment"** tab (left sidebar)
4. Click **"Add Environment Variable"** for each variable

### Required Variables (Copy from your `.env` file):

#### Pipedrive:
```
PIPEDRIVE_API_KEY=your_api_key
```

#### Salesforce OAuth (you already have these):
```
SALESFORCE_CONSUMER_KEY=your_consumer_key
SALESFORCE_CONSUMER_SECRET=your_consumer_secret
SALESFORCE_REFRESH_TOKEN=your_refresh_token
SALESFORCE_INSTANCE_URL=your_instance_url
SALESFORCE_DOMAIN=login
```

#### Salesforce Configuration:
```
SALESFORCE_LOAN_OBJECT=MtgPlanner_CRM__Transaction_Property__c
SALESFORCE_LOAN_OFFICER_FIELD=MtgPlanner_CRM__Loan_Officer__c
SALESFORCE_PRIMARY_BORROWER_FIELD=MtgPlanner_CRM__Borrower_Name__c
SALESFORCE_LOAN_OFFICER=Jake Elmendorf
```

#### Pipedrive Field Keys (ALL of them from your .env):
```
LOAN_AMOUNT_KEY=...
BASE_LOAN_AMOUNT_KEY=...
PROPERTY_ADDRESS_KEY=...
LOAN_TYPE_KEY=...
LOAN_PURPOSE_KEY=...
OCCUPANCY_KEY=...
PURCHASE_PRICE_KEY=...
DOWN_PAYMENT_KEY=...
DOWN_PAYMENT_PERCENT_KEY=...
PI_PAYMENT_KEY=...
SUPPLEMENTAL_PROPERTY_INSURANCE_KEY=...
# ... (add ALL field keys from your .env)
```

#### Pipedrive Custom Field Keys for Salesforce IDs:
```
PIPEDRIVE_SALESFORCE_LOAN_ID_KEY=...
PIPEDRIVE_SALESFORCE_CONTACT_ID_KEY=...
```

#### Pipedrive Stage IDs, Label IDs, etc.:
```
APPLICATION_IN_STAGE_ID=...
PREAPPROVED_STAGE_ID=...
# ... (all stage and label IDs)
```

#### Contact Type and Group IDs:
```
CONTACT_TYPE_KEY=...
CONTACT_GROUP_KEY=...
CLIENT_CONTACT_TYPE_ID=...
BUSINESS_CONTACT_TYPE_ID=...
LEAD_GROUP_ID=...
BORROWER_GROUP_ID=...
# ... (all group and contact type IDs)
```

**Important**: 
- Copy EVERY variable from your local `.env` file
- Double-check for typos
- After adding variables, Render will automatically restart the service

---

## Step 3: Verify Service is Running

1. **Health Check**:
   ```bash
   curl https://pipedrive-automation.onrender.com/health
   ```
   Should return: `{"status": "ok"}`

2. **Check Logs**:
   - Go to Render dashboard → Your service → **"Logs"** tab
   - Look for any startup errors
   - Should see "✓ Successfully connected to Salesforce via OAuth refresh token"

---

## Step 4: Test Manual Sync

Before setting up CDC, test with a manual sync:

```bash
# Test with 1 hour lookback (small test)
curl -X POST https://pipedrive-automation.onrender.com/sync/poll?hours_back=1
```

**Check the response:**
- Should return JSON with `"success": true`
- Check Render logs to see sync activity
- Verify a test deal appears in Pipedrive

---

## Step 5: Run Initial Sync (One-Time)

After testing works, run a full initial sync to bring in existing loans:

```bash
curl -X POST https://pipedrive-automation.onrender.com/sync/initial?limit=1000
```

**Note**: 
- This syncs up to 1000 loans
- Adjust `limit` if you have more loans
- Monitor Render logs during sync
- Check Pipedrive for new deals

---

## Step 6: Set Up Salesforce Change Data Capture (Real-time Sync)

**Note**: This sync uses real-time CDC events from Salesforce, NOT polling/CRON jobs.

### Configure Salesforce CDC:

1. In Salesforce, go to **Setup → Integrations → Change Data Capture**
2. Find your Loan object: `MtgPlanner_CRM__Transaction_Property__c`
3. Click **"Enable"** next to it
4. Set up a Platform Event subscription or webhook:
   - **Webhook URL**: `https://pipedrive-automation.onrender.com/webhook/salesforce/cdc`
   - **Method**: POST

**Alternative**: If CDC setup is complex, you can use the manual sync endpoints periodically instead.

---

## Step 7: Monitor and Verify

1. **Check Render Logs**:
   - Watch for sync activity
   - Look for any errors
   - Verify Salesforce connection is working

2. **Check Pipedrive**:
   - Verify deals are being created/updated
   - Check that Salesforce IDs are populated
   - Verify all fields are mapping correctly
   - Check commission calculations

3. **Test a Real Update**:
   - Update a loan in Salesforce (where you're the Loan Officer)
   - Wait for CDC event (or trigger manual sync)
   - Verify the deal updates in Pipedrive

---

## Available Endpoints

- `GET /health` - Health check
- `POST /sync/poll?hours_back=24` - Manual polling sync
- `POST /sync/initial?limit=1000` - Full initial sync
- `POST /webhook/changedeal` - Pipedrive webhook (existing)
- `POST /webhook/changeperson` - Pipedrive webhook (existing)
- `POST /webhook/salesforce/cdc` - Salesforce CDC webhook

---

## Troubleshooting

### Service won't start:
- Check logs in Render dashboard
- Verify all environment variables are set
- Check that `flask_app.py` is the start command
- Look for import errors or missing dependencies

### Sync not working:
- Check Render logs for errors
- Verify Salesforce OAuth credentials are correct
- Test the `/health` endpoint first
- Try manual sync: `/sync/poll?hours_back=1`
- Verify Loan Officer filter matches exactly

### Environment variables not loading:
- Make sure they're set in Render's Environment tab (not in code)
- Restart the service after adding variables
- Check for typos in variable names
- Verify values match your local `.env` file

### Salesforce connection errors:
- Verify OAuth credentials (Consumer Key, Secret, Refresh Token)
- Check that `SALESFORCE_INSTANCE_URL` is correct
- Verify OAuth scopes include "api" and "refresh_token"
- Check Render logs for specific error messages

---

## Quick Checklist

- [ ] Code committed and pushed to GitHub
- [ ] All environment variables added to Render
- [ ] Service restarted and health check passes
- [ ] Manual sync test successful
- [ ] Initial sync completed
- [ ] Salesforce CDC configured (or using manual sync)
- [ ] Monitoring logs for errors
- [ ] Verified data in Pipedrive

---

## Next Steps After Deployment

1. Monitor logs for the first few days
2. Verify sync is working correctly
3. Check for any duplicate records (shouldn't happen with upsert)
4. Watch for Salesforce API rate limits
5. Adjust sync frequency if needed (if using manual sync)

---

## Support

If you encounter issues:
1. Check Render logs first
2. Review `ARCHITECTURE.md` for design details
3. Test Salesforce queries in Developer Console
4. Verify all configuration matches your setup
