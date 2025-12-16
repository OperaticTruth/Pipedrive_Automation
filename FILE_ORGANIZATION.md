# File Organization Guide

Here's what each file does, organized by category:

---

## 📋 **Documentation**

### Setup & Reference:
- **`RENDER_DEPLOYMENT.md`** - Complete deployment guide for Render
- **`ARCHITECTURE.md`** - Technical design and architecture
- **`README_SALESFORCE_SYNC.md`** - Quick reference for sync feature
- **`SYNC_REQUIREMENTS_QUESTIONS.md`** - Your answered questions (reference)

---

## ⚙️ **Core Application Files**

### Main Application:
- **`flask_app.py`** - Main Flask app with all routes
  - Pipedrive webhooks (`/webhook/changedeal`, `/webhook/changeperson`)
  - Salesforce sync endpoints (`/sync/poll`, `/sync/initial`, `/webhook/salesforce/cdc`)
  - Health check (`/health`)
- **`config.py`** - Configuration (loads from environment variables)
- **`requirements.txt`** - Python dependencies

### Your Existing Workflows:
- **`workflows/commission.py`** - Commission calculation
- **`workflows/loan_amount_sync.py`** - Loan amount sync
- **`workflows/first_payment_date.py`** - First payment date calculation
- **`workflows/calculate_210_days.py`** - 210 days calculation
- **`workflows/comprehensive_stage_labels.py`** - Stage label management
- **`workflows/loan_number_extract.py`** - Loan number extraction
- **`workflows/birth_month_extract.py`** - Birth month extraction
- **`workflows/average_buy_volume.py`** - Average buy volume
- **`workflows/agent_stage_labels.py`** - Agent stage labels
- **`workflows/utils.py`** - Utility functions for Pipedrive API

### Salesforce Sync Module:
- **`workflows/salesforce_sync/__init__.py`** - Module initialization
- **`workflows/salesforce_sync/salesforce_client.py`** - Salesforce API client (OAuth)
- **`workflows/salesforce_sync/sync_person.py`** - Person sync logic
- **`workflows/salesforce_sync/sync_deal.py`** - Deal sync logic (includes lead conversion)
- **`workflows/salesforce_sync/polling_sync.py`** - Polling-based sync
- **`workflows/salesforce_sync/cdc_listener.py`** - Real-time CDC handler

---

## 📁 **Configuration**

- **`.env`** - Your local environment variables (API keys, field keys, etc.) ⚠️ **Keep this secure!**
  - Not committed to git
  - Copy all variables to Render's Environment tab for production

---

## 🎯 **Current Status:**

✅ **Code Implementation**: Complete
- All field mappings implemented
- Lead conversion logic
- Commission calculation integration
- Upsert logic for deduplication

✅ **Ready for Deployment**: 
- See `RENDER_DEPLOYMENT.md` for step-by-step instructions
- Need to add all environment variables to Render

---

## 📝 **Summary:**

**Production Files:**
- All files in `workflows/` are used in production
- `flask_app.py` is the main entry point
- `config.py` loads environment variables

**Documentation:**
- `RENDER_DEPLOYMENT.md` - Follow this for deployment
- `ARCHITECTURE.md` - Technical reference
- `README_SALESFORCE_SYNC.md` - Quick reference

**Not Needed:**
- Helper scripts (already used during setup)
- Old documentation files (consolidated into main docs)
