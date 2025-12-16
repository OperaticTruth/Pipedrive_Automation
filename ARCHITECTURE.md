# Salesforce/Jungo → Pipedrive Sync Architecture

## Overview

This document outlines the architecture for syncing loan and contact data from Salesforce/Jungo to Pipedrive, filtering by Loan Officer and maintaining data integrity through upsert operations.

## Architecture Decisions

### 1. **Sync Strategy: Real-time with Polling Fallback**

**Primary Approach: Change Data Capture (CDC)**
- Uses Salesforce Change Data Capture API for real-time updates
- Subscribes to Loan object changes
- Filters events server-side to only process loans where Loan Officer = "Jake Elmendorf"
- Pros: Immediate updates, efficient, no unnecessary API calls
- Cons: Requires proper Salesforce setup and webhook endpoint

**Fallback Approach: Polling**
- Scheduled job runs every 5-15 minutes
- Queries Salesforce for loans modified since last sync
- Uses `LastModifiedDate` field for incremental sync
- Pros: Simple, reliable, no Salesforce CDC setup required
- Cons: Slight delay, more API calls

**Recommendation**: Start with polling for simplicity, then migrate to CDC once stable.

### 2. **Data Flow**

```
Salesforce/Jungo → Sync Service → Pipedrive
     ↓                ↓              ↓
  Loan Object    Filter by LO    Person (upsert)
  Contact Object  Map Fields     Deal (upsert)
```

### 3. **Upsert Logic**

**For Persons:**
1. Query Pipedrive for Person with custom field `Salesforce_Contact_ID` = Contact.Id
2. If found: Update existing Person
3. If not found: Create new Person
4. Store `Salesforce_Contact_ID` in custom field

**For Deals:**
1. Query Pipedrive for Deal with custom field `Salesforce_Loan_ID` = Loan.Id
2. If found: Update existing Deal
3. If not found: Create new Deal
4. Link Deal to Person (from step above)
5. Store `Salesforce_Loan_ID` in custom field

### 4. **Field Mapping Strategy**

**Salesforce → Pipedrive Person:**
- Contact.Name → Person name
- Contact.Email → Person email
- Contact.Phone → Person phone
- Contact.Id → Custom field (for deduplication)

**Salesforce → Pipedrive Deal:**
- Loan.Name → Deal title
- Loan.Amount → Deal value
- Loan.Stage → Deal stage (mapping required)
- Loan.CloseDate → Deal expected close date
- Loan.Id → Custom field (for deduplication)
- Loan → Deal person_id (via Contact lookup)

### 5. **Error Handling & Idempotency**

- All operations are idempotent (safe to retry)
- Failed syncs are logged but don't block future syncs
- Rate limiting respected for both APIs
- Webhook signature verification for CDC events

### 6. **Future Bidirectional Sync Considerations**

- Separate sync direction flags (`sync_to_pipedrive`, `sync_to_salesforce`)
- Activity/Note sync would require:
  - Pipedrive webhook → Salesforce API
  - Permission checks (read-only vs write)
  - Field mapping configuration
  - Conflict resolution strategy

## File Structure

```
Pipedrive_Automation/
├── config.py                    # Existing config
├── flask_app.py                 # Existing Flask app
├── requirements.txt             # Dependencies
├── workflows/
│   ├── commission.py           # Existing
│   ├── utils.py                # Existing Pipedrive utils
│   └── salesforce_sync/        # NEW: Salesforce sync module
│       ├── __init__.py
│       ├── salesforce_client.py    # Salesforce API client
│       ├── sync_person.py          # Person sync logic
│       ├── sync_deal.py             # Deal sync logic
│       ├── cdc_listener.py         # Change Data Capture handler
│       └── polling_sync.py          # Polling-based sync
├── ARCHITECTURE.md              # This file
└── SETUP_SALESFORCE.md          # Salesforce setup guide
```

## Salesforce Object & Field Assumptions

**⚠️ These need to be verified in your Salesforce instance:**

### Loan Object (likely `Loan__c` or similar)
- API Name: `Loan__c` (or `Opportunity` if using standard)
- Fields needed:
  - `Id` - Unique identifier
  - `Name` - Loan name/number
  - `Loan_Officer__c` or `OwnerId` - Loan Officer (filter field)
  - `Primary_Borrower__c` - Lookup to Contact
  - `Amount__c` - Loan amount
  - `Stage__c` - Loan stage
  - `CloseDate__c` - Expected close date
  - `LastModifiedDate` - For polling

### Contact Object (standard)
- API Name: `Contact`
- Fields needed:
  - `Id` - Unique identifier
  - `Name` - Full name
  - `Email` - Email address
  - `Phone` - Phone number

## Implementation Phases

### Phase 1: Foundation (Current)
- ✅ Salesforce authentication
- ✅ Basic query utilities
- ✅ Pipedrive upsert utilities

### Phase 2: Core Sync
- ⏳ Person sync workflow
- ⏳ Deal sync workflow
- ⏳ Field mapping configuration

### Phase 3: Automation
- ⏳ Polling scheduler
- ⏳ CDC webhook handler
- ⏳ Error handling & logging

### Phase 4: Production
- ⏳ Monitoring & alerts
- ⏳ Performance optimization
- ⏳ Documentation

## Best Practices

1. **API Rate Limits**: Implement exponential backoff and respect rate limits
2. **Data Validation**: Validate all data before syncing
3. **Logging**: Comprehensive logging for debugging and audit trails
4. **Configuration**: All field mappings and IDs in environment variables
5. **Testing**: Test with small datasets before full sync
6. **Monitoring**: Track sync success rates and API usage

## Security Considerations

1. **Credentials**: Store Salesforce credentials in environment variables
2. **Webhook Security**: Verify CDC webhook signatures
3. **API Keys**: Rotate Pipedrive API keys regularly
4. **Access Control**: Use least-privilege Salesforce profiles

## Questions to Resolve

1. **Salesforce Object Names**: What is the exact API name of the Loan object?
2. **Loan Officer Field**: Is it a text field or lookup to User?
3. **Primary Borrower Field**: What is the exact API name?
4. **Stage Mapping**: How do Salesforce loan stages map to Pipedrive deal stages?
5. **Custom Fields**: What Pipedrive custom field keys should store Salesforce IDs?

