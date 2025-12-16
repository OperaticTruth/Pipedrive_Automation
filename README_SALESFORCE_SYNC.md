# Salesforce/Jungo → Pipedrive Sync

This integration syncs loan and contact data from Salesforce/Jungo to Pipedrive, automatically filtering by Loan Officer and maintaining data integrity through upsert operations.

## Quick Start

1. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure Environment Variables**
   All configuration is done via environment variables. See `RENDER_DEPLOYMENT.md` for deployment setup.

   Required variables include:
   - Salesforce OAuth credentials (Consumer Key, Secret, Refresh Token)
   - Pipedrive API key
   - Field mapping keys for custom Pipedrive fields
   - Salesforce object and field API names

3. **Sync Modes**

   **Real-time (Recommended)**: Uses Salesforce Change Data Capture (CDC)
   - Configure CDC webhook in Salesforce pointing to: `https://pipedrive-automation.onrender.com/webhook/salesforce/cdc`
   - Syncs immediately when loans are created or updated

   **Manual Testing**: Use these endpoints for testing
   ```bash
   # Health check
   curl https://pipedrive-automation.onrender.com/health
   
   # Manual polling sync (last 24 hours)
   curl -X POST https://pipedrive-automation.onrender.com/sync/poll?hours_back=24
   
   # Initial full sync (first 1000 loans)
   curl -X POST https://pipedrive-automation.onrender.com/sync/initial?limit=1000
   ```

## How It Works

1. **Filter by Loan Officer**: Only loans where Loan Officer = "Jake Elmendorf" are synced
2. **Skip Cancelled**: Loans with Status = "Cancelled" are not synced
3. **Sync Contact First**: For each loan, the associated Contact is synced to a Pipedrive Person
4. **Upsert Logic**: 
   - Searches for existing Person/Deal by Salesforce ID
   - Updates if found, creates if not found
5. **Lead Conversion**: If an active Lead exists for the Person, converts it to a Deal
6. **Field Mapping**: Maps all Salesforce fields to Pipedrive fields (configurable)
7. **Commission Calculation**: Automatically calculates commission after deal sync

## API Endpoints

### `/health` (GET)
Health check endpoint.

**Example:**
```
GET /health
```

### `/sync/poll` (GET/POST)
Trigger a manual polling sync.

**Query Parameters:**
- `hours_back` (default: 24) - How many hours to look back

**Example:**
```
POST /sync/poll?hours_back=48
```

### `/sync/initial` (GET/POST)
Run an initial full sync (no time filter).

**Query Parameters:**
- `limit` (default: 1000) - Maximum number of loans to sync

**Example:**
```
POST /sync/initial?limit=500
```

### `/webhook/salesforce/cdc` (POST)
Receive Change Data Capture events from Salesforce.

**Note:** Requires Salesforce CDC to be configured. See deployment guide.

### `/webhook/changedeal` (POST)
Existing Pipedrive webhook for deal changes (commission, labels, etc.)

### `/webhook/changeperson` (POST)
Existing Pipedrive webhook for person changes

## Sync Behavior

### When Sync Fires:
- ✅ New Deal Created: Loan Officer = "Jake Elmendorf" AND Status ≠ "Cancelled"
- ✅ Deal Updated: Loan Officer = "Jake Elmendorf" AND Status ≠ "Cancelled" AND fields changed

### What Gets Synced:
- Primary Borrower Contact → Pipedrive Person
- Co-Borrower Contact → Pipedrive Person (if exists)
- Loan Record → Pipedrive Deal
- All mapped fields (loan amount, property address, occupancy, down payment %, etc.)
- Commission calculation runs after sync
- Contact Type set to "Client" (unless already "Business")
- Group updated to "Borrower" (removes "Lead" if present)

### What Does NOT Sync:
- ❌ Loans where Loan Officer ≠ "Jake Elmendorf"
- ❌ Loans where Status = "Cancelled"
- ❌ DELETE events (not implemented)

## Files

- `workflows/salesforce_sync/` - Core sync module
  - `salesforce_client.py` - Salesforce API client with OAuth
  - `sync_person.py` - Person sync logic
  - `sync_deal.py` - Deal sync logic (includes lead conversion)
  - `polling_sync.py` - Polling-based sync
  - `cdc_listener.py` - Real-time CDC handler
- `ARCHITECTURE.md` - Detailed architecture documentation
- `RENDER_DEPLOYMENT.md` - Deployment guide

## Troubleshooting

### No loans found
- Verify Loan Officer filter matches exactly
- Check if Loan Officer field is a lookup (use User ID instead of name)
- Test SOQL query in Salesforce Developer Console

### Sync fails
- Check Render logs for detailed error messages
- Verify all environment variables are set in Render
- Test Salesforce connection independently
- Verify Pipedrive API key is valid

### Duplicate records
- Ensure custom fields for Salesforce IDs are created in Pipedrive
- Verify field keys in environment variables match Pipedrive field keys
- Check that upsert logic is finding existing records correctly

## Deployment

See `RENDER_DEPLOYMENT.md` for complete deployment instructions.
