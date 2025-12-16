"""
Salesforce API Client

Handles authentication and querying Salesforce/Jungo data.
"""

import os
from simple_salesforce import Salesforce
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)


class SalesforceClient:
    """
    Wrapper around simple-salesforce for querying Salesforce data.
    
    Supports both username/password and OAuth authentication.
    """
    
    def __init__(self):
        """Initialize Salesforce connection using environment variables."""
        self.username = os.getenv("SALESFORCE_USERNAME")
        self.password = os.getenv("SALESFORCE_PASSWORD")
        self.security_token = os.getenv("SALESFORCE_SECURITY_TOKEN")
        self.domain = os.getenv("SALESFORCE_DOMAIN", "login")  # 'login' or 'test'
        
        # OAuth credentials (alternative to username/password)
        self.consumer_key = os.getenv("SALESFORCE_CONSUMER_KEY")
        self.consumer_secret = os.getenv("SALESFORCE_CONSUMER_SECRET")
        self.access_token = os.getenv("SALESFORCE_ACCESS_TOKEN")
        
        # Loan Officer filter - can be name or User ID
        self.loan_officer_filter = os.getenv("SALESFORCE_LOAN_OFFICER", "Jake Elmendorf")
        self.loan_officer_user_id = os.getenv("SALESFORCE_LOAN_OFFICER_USER_ID")  # Optional User ID
        
        # Object API names (configurable)
        self.loan_object = os.getenv("SALESFORCE_LOAN_OBJECT", "Loan__c")
        self.loan_officer_field = os.getenv("SALESFORCE_LOAN_OFFICER_FIELD", "Loan_Officer__c")
        self.primary_borrower_field = os.getenv("SALESFORCE_PRIMARY_BORROWER_FIELD", "Primary_Borrower__c")
        
        self.sf = None
        self._connect()
    
    def _connect(self):
        """Establish connection to Salesforce."""
        try:
            # Option 1: OAuth with access token (best for 2FA)
            if self.access_token:
                instance_url = os.getenv("SALESFORCE_INSTANCE_URL")
                if instance_url:
                    logger.info("Connecting to Salesforce with OAuth access token...")
                    self.sf = Salesforce(instance_url=instance_url, session_id=self.access_token)
                    logger.info("✓ Successfully connected to Salesforce via OAuth")
                    return
                else:
                    logger.warning("SALESFORCE_ACCESS_TOKEN provided but SALESFORCE_INSTANCE_URL missing")
            
            # Option 2: OAuth with refresh token (if available)
            refresh_token = os.getenv("SALESFORCE_REFRESH_TOKEN")
            if self.consumer_key and self.consumer_secret and refresh_token:
                logger.info("Attempting OAuth connection with refresh token...")
                try:
                    from simple_salesforce import Salesforce
                    import requests
                    
                    # Get new access token using refresh token
                    token_url = f"https://{self.domain}.salesforce.com/services/oauth2/token"
                    token_data = {
                        "grant_type": "refresh_token",
                        "client_id": self.consumer_key,
                        "client_secret": self.consumer_secret,
                        "refresh_token": refresh_token
                    }
                    
                    resp = requests.post(token_url, data=token_data)
                    resp.raise_for_status()
                    token_response = resp.json()
                    
                    access_token = token_response.get("access_token")
                    instance_url = token_response.get("instance_url")
                    
                    if access_token and instance_url:
                        self.sf = Salesforce(instance_url=instance_url, session_id=access_token)
                        logger.info("✓ Successfully connected to Salesforce via OAuth refresh token")
                        return
                except Exception as e:
                    logger.warning(f"OAuth refresh token failed: {e}. Trying other methods...")
            
            # Option 3: Username/password (may not work with 2FA unless IP is whitelisted)
            if self.username and self.password:
                logger.info("Connecting to Salesforce with username/password...")
                logger.warning("Note: This may fail with 2FA enabled unless your IP is whitelisted")
                try:
                    self.sf = Salesforce(
                        username=self.username,
                        password=self.password,
                        security_token=self.security_token,
                        domain=self.domain
                    )
                    logger.info("✓ Successfully connected to Salesforce")
                    return
                except Exception as e:
                    if "INVALID_LOGIN" in str(e) or "authentication" in str(e).lower():
                        logger.error(
                            "Authentication failed. This is likely due to 2FA.\n"
                            "Solutions:\n"
                            "1. Whitelist your IP in Salesforce (Setup → Network Access)\n"
                            "2. Use OAuth instead (see SALESFORCE_2FA_SETUP.md)\n"
                            "3. Get an access token manually and use SALESFORCE_ACCESS_TOKEN"
                        )
                    raise
            
            raise ValueError(
                "Missing Salesforce credentials. With 2FA enabled, you need:\n"
                "- SALESFORCE_ACCESS_TOKEN + SALESFORCE_INSTANCE_URL (recommended)\n"
                "- OR SALESFORCE_CONSUMER_KEY + SALESFORCE_CONSUMER_SECRET + SALESFORCE_REFRESH_TOKEN\n"
                "- OR Whitelist your IP and use SALESFORCE_USERNAME + SALESFORCE_PASSWORD + SALESFORCE_SECURITY_TOKEN\n"
                "\nSee SALESFORCE_2FA_SETUP.md for detailed instructions."
            )
            
        except Exception as e:
            logger.error(f"Failed to connect to Salesforce: {e}")
            raise
    
    def query(self, soql: str) -> List[Dict[str, Any]]:
        """
        Execute a SOQL query and return results.
        
        Args:
            soql: SOQL query string
            
        Returns:
            List of record dictionaries
        """
        try:
            result = self.sf.query(soql)
            records = result.get('records', [])
            # Remove 'attributes' key from each record
            for record in records:
                record.pop('attributes', None)
            return records
        except Exception as e:
            logger.error(f"Salesforce query failed: {e}\nQuery: {soql}")
            raise
    
    def get_loans_by_loan_officer(
        self, 
        modified_since: Optional[str] = None,
        limit: int = 200
    ) -> List[Dict[str, Any]]:
        """
        Query loans where Loan Officer matches the configured filter.
        
        Args:
            modified_since: ISO datetime string for LastModifiedDate filter
            limit: Maximum number of records to return
            
        Returns:
            List of loan records with related contact data
        """
        # Build WHERE clause
        where_clauses = []
        
        # Filter by Loan Officer
        if self.loan_officer_user_id:
            # If we have a User ID, use it (for lookup fields)
            where_clauses.append(f"{self.loan_officer_field} = '{self.loan_officer_user_id}'")
        else:
            # Otherwise, filter by name (text field)
            where_clauses.append(f"{self.loan_officer_field} = '{self.loan_officer_filter}'")
        
        # Filter by LastModifiedDate if provided
        if modified_since:
            where_clauses.append(f"LastModifiedDate > {modified_since}")
        
        where_clause = " AND ".join(where_clauses)
        
        # Build SOQL query
        # For lookup fields, use __r for relationship name (not __c)
        # e.g., MtgPlanner_CRM__Borrower_Name__c becomes MtgPlanner_CRM__Borrower_Name__r
        borrower_relationship = self.primary_borrower_field.replace("__c", "__r")
        
        soql = f"""
            SELECT 
                Id,
                Name,
                {self.loan_officer_field},
                {self.primary_borrower_field},
                {borrower_relationship}.Id,
                {borrower_relationship}.Name,
                {borrower_relationship}.Email,
                {borrower_relationship}.Phone,
                {borrower_relationship}.Birthdate,
                {borrower_relationship}.MtgPlanner_CRM__Income_Borrower__c,
                {borrower_relationship}.MtgPlanner_CRM__Income_Co_Borrower__c,
                {borrower_relationship}.MtgPlanner_CRM__Co_Borrower_First_Name__c,
                {borrower_relationship}.MtgPlanner_CRM__Co_Borrower_Last_Name__c,
                {borrower_relationship}.MtgPlanner_CRM__Co_Borrower_Email__c,
                {borrower_relationship}.Phone_Co_Borrower__c,
                {borrower_relationship}.MtgPlanner_CRM__Birthdaycoborrower__c,
                MtgPlanner_CRM__Loan_Amount_1st_TD__c,
                Base_Loan_Amount__c,
                P_I_Payment__c,
                Supplemental_Property_Insurance__c,
                MtgPlanner_CRM__Status__c,
                MtgPlanner_CRM__Est_Closing_Date__c,
                Pre_Approval_Sent__c,
                Strategy_Call__c,
                MtgPlanner_CRM__Property_Address__c,
                MtgPlanner_CRM__Property_City__c,
                MtgPlanner_CRM__Property_State__c,
                MtgPlanner_CRM__Property_Postal_Code__c,
                MtgPlanner_CRM__Property_Type__c,
                MtgPlanner_CRM__Loan_Type_1st_TD__c,
                MtgPlanner_CRM__Loan_Purpose__c,
                MtgPlanner_CRM__Occupancy__c,
                MtgPlanner_CRM__Appraised_Value__c,
                MtgPlanner_CRM__Purchase_Price__c,
                MtgPlanner_CRM__Down_Payment__c,
                MtgPlanner_CRM__Rate_1st_TD__c,
                MtgPlanner_CRM__Term_1st_TD__c,
                Funding_Fee__c,
                Middle_Credit_Score_Borrower__c,
                MtgPlanner_CRM__Loan_Program_1st_TD__c,
                MtgPlanner_CRM__Monthly_Payment_1st_TD__c,
                MtgPlanner_CRM__Hazard_Ins_1st_TD__c,
                MtgPlanner_CRM__Property_Tax_1st_TD__c,
                MtgPlanner_CRM__Mortgage_Ins_1st_TD__c,
                MtgPlanner_CRM__HOA_1st_TD__c,
                eConsent__c,
                LE_Due__c,
                LE_Sent__c,
                LE_Received__c,
                Appraisal_Ordered__c,
                Appraisal_Received__c,
                Title_Received__c,
                Insurance_Received__c,
                CD_Sent__c,
                CD_Received__c,
                MtgPlanner_CRM__Loan_1st_TD__c,
                In_Process_or_Paid_Off__c,
                LastModifiedDate,
                CreatedDate
            FROM {self.loan_object}
            WHERE {where_clause}
            ORDER BY LastModifiedDate DESC
            LIMIT {limit}
        """
        
        logger.info(f"Querying loans: {soql[:200]}...")
        return self.query(soql)
    
    def get_loan_by_id(self, loan_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a single loan record by ID.
        
        Args:
            loan_id: Salesforce Loan ID
            
        Returns:
            Loan record dictionary or None
        """
        # Use __r for relationship name
        borrower_relationship = self.primary_borrower_field.replace("__c", "__r")
        
        # Use __r for relationship name
        borrower_relationship = self.primary_borrower_field.replace("__c", "__r")
        
        soql = f"""
            SELECT 
                Id,
                Name,
                {self.loan_officer_field},
                {self.primary_borrower_field},
                {borrower_relationship}.Id,
                {borrower_relationship}.Name,
                {borrower_relationship}.Email,
                {borrower_relationship}.Phone,
                {borrower_relationship}.Birthdate,
                {borrower_relationship}.MtgPlanner_CRM__Income_Borrower__c,
                {borrower_relationship}.MtgPlanner_CRM__Income_Co_Borrower__c,
                {borrower_relationship}.MtgPlanner_CRM__Co_Borrower_First_Name__c,
                {borrower_relationship}.MtgPlanner_CRM__Co_Borrower_Last_Name__c,
                {borrower_relationship}.MtgPlanner_CRM__Co_Borrower_Email__c,
                {borrower_relationship}.Phone_Co_Borrower__c,
                {borrower_relationship}.MtgPlanner_CRM__Birthdaycoborrower__c,
                MtgPlanner_CRM__Loan_Amount_1st_TD__c,
                Base_Loan_Amount__c,
                P_I_Payment__c,
                Supplemental_Property_Insurance__c,
                MtgPlanner_CRM__Status__c,
                MtgPlanner_CRM__Est_Closing_Date__c,
                Pre_Approval_Sent__c,
                Strategy_Call__c,
                MtgPlanner_CRM__Property_Address__c,
                MtgPlanner_CRM__Property_City__c,
                MtgPlanner_CRM__Property_State__c,
                MtgPlanner_CRM__Property_Postal_Code__c,
                MtgPlanner_CRM__Property_Type__c,
                MtgPlanner_CRM__Loan_Type_1st_TD__c,
                MtgPlanner_CRM__Loan_Purpose__c,
                MtgPlanner_CRM__Occupancy__c,
                MtgPlanner_CRM__Appraised_Value__c,
                MtgPlanner_CRM__Purchase_Price__c,
                MtgPlanner_CRM__Down_Payment__c,
                MtgPlanner_CRM__Rate_1st_TD__c,
                MtgPlanner_CRM__Term_1st_TD__c,
                Funding_Fee__c,
                Middle_Credit_Score_Borrower__c,
                MtgPlanner_CRM__Loan_Program_1st_TD__c,
                MtgPlanner_CRM__Monthly_Payment_1st_TD__c,
                MtgPlanner_CRM__Hazard_Ins_1st_TD__c,
                MtgPlanner_CRM__Property_Tax_1st_TD__c,
                MtgPlanner_CRM__Mortgage_Ins_1st_TD__c,
                MtgPlanner_CRM__HOA_1st_TD__c,
                eConsent__c,
                LE_Due__c,
                LE_Sent__c,
                LE_Received__c,
                Appraisal_Ordered__c,
                Appraisal_Received__c,
                Title_Received__c,
                Insurance_Received__c,
                CD_Sent__c,
                CD_Received__c,
                MtgPlanner_CRM__Loan_1st_TD__c,
                In_Process_or_Paid_Off__c,
                LastModifiedDate,
                CreatedDate
            FROM {self.loan_object}
            WHERE Id = '{loan_id}'
            LIMIT 1
        """
        
        results = self.query(soql)
        return results[0] if results else None
    
    def get_contact_by_id(self, contact_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a single contact record by ID.
        
        Args:
            contact_id: Salesforce Contact ID
            
        Returns:
            Contact record dictionary or None
        """
        soql = f"""
            SELECT 
                Id,
                Name,
                Email,
                Phone
            FROM Contact
            WHERE Id = '{contact_id}'
            LIMIT 1
        """
        
        results = self.query(soql)
        return results[0] if results else None
    
    def update_loan_status(self, loan_id: str, status: str) -> bool:
        """
        Update the status field of a Loan record in Salesforce.
        
        Args:
            loan_id: Salesforce Loan ID (e.g., "a0X...")
            status: New status value (e.g., "Cancelled")
            
        Returns:
            True if update was successful, False otherwise
        """
        try:
            if not self.sf:
                logger.error("Salesforce connection not established")
                return False
            
            # Get the loan object API name
            loan_object = self.loan_object
            
            # Update the status field
            status_field = "MtgPlanner_CRM__Status__c"
            
            logger.info(f"Updating {loan_object} {loan_id}: {status_field} = {status}")
            
            # Use simple-salesforce's update method
            # The object is accessed via getattr and then we call update
            obj = getattr(self.sf, loan_object)
            result = obj.update(loan_id, {status_field: status})
            
            # simple-salesforce returns True on success, or raises exception on failure
            if result is True:
                logger.info(f"✓ Successfully updated Loan {loan_id} status to {status}")
                return True
            else:
                logger.warning(f"Update returned unexpected result for Loan {loan_id}: {result}")
                return False
                
        except Exception as e:
            logger.error(f"Error updating Loan {loan_id} status: {e}", exc_info=True)
            return False

